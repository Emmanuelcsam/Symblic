"""Constructor journal: durable intent and outcome records for constructor attempts, one stream per run folder.

What it is for
    It keeps one strict, append-only record stream per run folder, constructor-events.jsonl, so that the bridge
    (symblic.constructor.core) can:
    - announce an attempt durably (fsynced intent) before it dispatches anything: Journal.begin;
    - record how the attempt ended (fsynced outcome) before it adopts a value: Journal.complete;
    - resume or replay from the record: an accepted value is reused exactly, any other recorded disposition is
      replayed without a new search, and an intent without an outcome is refused as uncertain, never dispatched
      again by itself.
    The operator's tools are reconcile() (record that an uncertain attempt was abandoned: a decision, not proof
    that nothing ran) and repair_torn_tail() (cut an interrupted last row after keeping its bytes in a
    quarantine slot).

How it is written
    Every row is canonical ASCII JSON (sorted keys, no floats, no duplicate keys) carrying its sequence number,
    the previous row's hash and its own domain-separated hash. A reader refuses a torn, malformed,
    non-canonical, reordered, oversized or contradictory record; it never skips one. The `open` row pins the run
    (source, inputs, kernel, constructor configuration, mode, selection policy) and its original allowance, so a
    resume can neither grow the allowance nor reuse a record under other pins. Hashes give integrity and exact
    references, not authority. The recorded owner of a row (host name, pid, process start, boot id, token) is a
    diagnostic of which process wrote it; it grants nothing.

    Inert: importing reads, creates and starts nothing. A Journal touches the disk only when called, never
    creates the run folder, never takes the run Store's locks, and holds its own lock for one short transaction,
    never while a worker runs.

Depends on: the standard library (symblic.kernel.identity records the import identity). Used by:
symblic.constructor.core, .records and .inspect. Status: prototype; tested with real child processes that crash
at chosen points (tests/constructor/test_symblic_constructor_journal*.py).
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import contextlib
import copy
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import socket
import stat
import threading
import time
import uuid

VERSION = 3                             # v3: durable fixed quarantine slots include interrupted repairs
FILE = 'constructor-events.jsonl'
LOCK_FILE = '.constructor-events.lock'
MAX_ATTEMPTS = 64                       # intents in one run's journal (design candidate)
MAX_JOURNAL_BYTES = 8 * 1024 * 1024     # design candidate: 8 MiB of constructor records per run
MAX_ROW_BYTES = 256 * 1024
MAX_ATTEMPT_MS = 5000                   # one attempt's whole deadline (the helper's MAX_SECONDS)
MAX_TOTAL_MS = MAX_ATTEMPTS * MAX_ATTEMPT_MS
MAX_RESOURCE_LIMIT = 1_000_000          # the helper's MAX_WORK
MAX_ADDRESS_SPACE = 1 << 40
MAX_ELAPSED_MS = 3_600_000
MAX_CANDIDATES = 2
MAX_VALUE_BYTES = 65536                 # one candidate, effective_limits or evidence, canonically encoded
MAX_VALUE_NODES = 4096
MAX_VALUE_DEPTH = 16
MAX_NOTE = 512
MAX_REPAIRS = 8                         # fixed on-disk slots, including unfinished and unaudited repairs
MAX_INT = 2**53 - 1
LOCK_WAIT_SECONDS = 2.0                 # the longest any call waits for the journal; never past an attempt's deadline
LOCK_POLL_SECONDS = 0.01
KINDS = ('smt_linear',)
MODES = ('linear_diagnose', 'linear')
SELECTION_POLICIES = ('canonical_min_v1',)
DISPOSITIONS = ('accepted', 'diagnosed', 'no_candidate', 'unsupported', 'unavailable', 'timeout', 'unknown',
                'stopped', 'cleanup_failed')
STATUSES = ('sat', 'unsat', 'unknown', 'timeout', 'unsupported', 'unavailable')
DETERMINATIONS = ('unassessed', 'underdetermined')
PIN_FIELDS = ('source_sha256', 'input_sha256', 'kernel_id', 'kind', 'mode', 'selection_policy',
              'implementation_sha256', 'worker_sha256', 'configuration_sha256', 'allowance')
REQUEST_FIELDS = ('occurrence', 'item', 'contract_sha256', 'constants_sha256', 'dependencies_sha256', 'limits')
LIMIT_FIELDS = ('milliseconds', 'resource_limit', 'address_space_bytes')
OUTCOME_FIELDS = ('disposition', 'dispatched', 'reaped', 'status', 'reason', 'determination', 'candidates',
                  'raw_sha256', 'effective_limits', 'costs', 'evidence')
COST_FIELDS = ('elapsed_ms', 'solver_rlimit', 'validation_steps')
# Refusals that mean the file itself cannot be trusted: nothing new is performed from it until the owner looks.
DAMAGE = frozenset({'unreadable', 'unsafe_file', 'oversized_journal', 'oversized_row', 'torn_tail', 'malformed',
                    'noncanonical', 'schema', 'sequence', 'chain', 'state', 'budget_record'})
GENESIS = '0' * 64
_DOMAIN = {name: f'symblic.constructor.{name}.v{VERSION}\0'.encode('ascii')
           for name in ('row', 'pins', 'key', 'candidate')}
_ROW_BASE = ('v', 'seq', 'prev', 'event', 'at_ms', 'sha256')
_EVENT_FIELDS = {
    'open': ('pins', 'pins_sha256'),
    'intent': ('attempt', 'key', 'request', 'reserve', 'charged_before', 'continues', 'deadline_at_ms', 'owner'),
    'outcome': ('attempt', 'key', 'outcome', 'selected', 'selected_sha256', 'owner'),
    'reconcile': ('attempt', 'verdict', 'note', 'forced', 'owner'),
    'repair': ('truncated_bytes', 'torn_sha256', 'quarantine', 'owner'),
}
_ROW_NODES = 6 * MAX_VALUE_NODES
_ROW_DEPTH = MAX_VALUE_DEPTH + 4
_CONTINUABLE = ('stopped', 'abandoned')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/#-]{0,159}\Z')
_KERNEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z')
_CODE = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')
_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_BOOT = re.compile(r'[0-9a-f-]{1,64}\Z')


class JournalError(Exception):
    """A typed refusal: `code` names it (DAMAGE codes mean the file cannot be trusted), `details` is small JSON."""

    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


# ---------------------------------------------------------------------------
# Exact values, canonical text and hashes
# ---------------------------------------------------------------------------

def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _hex(value):
    return type(value) is str and _SHA.match(value) is not None


def _measure(value, max_nodes, max_depth, max_bytes):
    """The exact length of a value's canonical text, computed without building it. Exact JSON only (null, bool, int,
    text, list, object with text keys). Refuses (ValueError) as soon as a node, depth or byte bound is passed:
    brackets, commas and colons are charged before a container is walked, and a text is encoded only when it could
    still fit, so no input, however large, shared or repeated, costs more than its bounds."""
    left = [max_nodes, max_bytes]

    def charge(size):
        left[1] -= size
        if left[1] < 0:
            raise ValueError(f'its canonical text is larger than {max_bytes} bytes')

    def text(item):
        if len(item) + 2 > left[1]:         # every character encodes to at least one byte
            raise ValueError(f'its canonical text is larger than {max_bytes} bytes')
        charge(len(json.dumps(item, ensure_ascii=True)))

    def walk(item, depth):
        left[0] -= 1
        if left[0] < 0 or depth > max_depth:
            raise ValueError('the value exceeds its node or depth bound')
        kind = type(item)
        if item is None or kind is bool:
            charge(5 if item is False else 4)
        elif kind is int:
            if not -(1 << 256) < item < (1 << 256):
                raise ValueError('an integer is out of range')
            charge(len(str(item)))
        elif kind is str:
            text(item)
        elif kind is list:
            charge(1 + max(1, len(item)))   # brackets and commas
            for child in item:
                walk(child, depth + 1)
        elif kind is dict:
            charge(1 + max(1, len(item)) + len(item))     # braces, commas and colons
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError('object keys must be texts')
                text(key)
                walk(child, depth + 1)
        else:
            raise ValueError(f'{kind.__name__} is not exact JSON (no floats)')
    walk(value, 0)
    return max_bytes - left[1]


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def canonical(value):
    """The one text a value is stored and hashed as: sorted keys, compact, ASCII, exact (floats are refused)."""
    try:
        _measure(value, _ROW_NODES, _ROW_DEPTH, MAX_ROW_BYTES)
    except ValueError as exc:
        raise JournalError('invalid_value', str(exc)) from None
    return _dump(value)


def _sha(domain, value):
    return hashlib.sha256(_DOMAIN[domain] + _dump(value).encode('ascii')).hexdigest()


def _value_problem(value):
    try:
        _measure(value, MAX_VALUE_NODES, MAX_VALUE_DEPTH, MAX_VALUE_BYTES)
    except ValueError as exc:
        return str(exc)
    return ''


def _differs(a, b, fields):
    return [name for name in fields if _dump(a[name]) != _dump(b[name])]


# ---------------------------------------------------------------------------
# Pins, requests, outcomes, owners
# ---------------------------------------------------------------------------

def _pins_problem(pins):
    if type(pins) is not dict or set(pins) != set(PIN_FIELDS):
        return 'pins have exactly the fields ' + ', '.join(PIN_FIELDS)
    for name in ('source_sha256', 'input_sha256', 'implementation_sha256', 'worker_sha256', 'configuration_sha256'):
        if not _hex(pins[name]):
            return f'{name} must be a lowercase sha256'
    if type(pins['kernel_id']) is not str or not _KERNEL.match(pins['kernel_id']):
        return 'kernel_id must be a kernel identity'
    for name, allowed in (('kind', KINDS), ('mode', MODES), ('selection_policy', SELECTION_POLICIES)):
        if type(pins[name]) is not str or pins[name] not in allowed:
            return f'{name} must be one of ' + ', '.join(allowed)
    allowance = pins['allowance']
    if type(allowance) is not dict or set(allowance) != {'attempts', 'milliseconds'} \
            or not _int(allowance['attempts'], 1, MAX_ATTEMPTS) or not _int(allowance['milliseconds'], 1, MAX_TOTAL_MS):
        return f'allowance is {{attempts: 1..{MAX_ATTEMPTS}, milliseconds: 1..{MAX_TOTAL_MS}}} as exact integers'
    return ''


def _request_problem(request):
    if type(request) is not dict or set(request) != set(REQUEST_FIELDS):
        return 'a request has exactly the fields ' + ', '.join(REQUEST_FIELDS)
    if type(request['occurrence']) is not str or not _ID.match(request['occurrence']):
        return 'occurrence must be a stable identifier'
    if request['item'] is not None and (type(request['item']) is not str or not _ID.match(request['item'])):
        return 'item must be null or a stable identifier'
    for name in ('contract_sha256', 'constants_sha256', 'dependencies_sha256'):
        if not _hex(request[name]):
            return f'{name} must be a lowercase sha256'
    limits = request['limits']
    if type(limits) is not dict or set(limits) != set(LIMIT_FIELDS) \
            or not _int(limits['milliseconds'], 1, MAX_ATTEMPT_MS) \
            or not _int(limits['resource_limit'], 1, MAX_RESOURCE_LIMIT) \
            or not _int(limits['address_space_bytes'], 1, MAX_ADDRESS_SPACE):
        return (f'limits are {{milliseconds: 1..{MAX_ATTEMPT_MS}, resource_limit: 1..{MAX_RESOURCE_LIMIT}, '
                'address_space_bytes}} as exact integers')
    return ''


def _outcome_problem(mode, o):
    """'' when `o` is a well-formed outcome for this mode, else why not. One rule set for writer and reader."""
    if type(o) is not dict or set(o) != set(OUTCOME_FIELDS):
        return 'an outcome has exactly the fields ' + ', '.join(OUTCOME_FIELDS)
    d, dispatched, reaped, status = o['disposition'], o['dispatched'], o['reaped'], o['status']
    if type(d) is not str or d not in DISPOSITIONS:
        return 'unknown disposition'
    if type(dispatched) is not bool or (reaped is not None and type(reaped) is not bool):
        return 'dispatched is a bool and reaped a bool or null'
    if status is not None and (type(status) is not str or status not in STATUSES):
        return 'unknown solver status'
    if o['reason'] is not None and (type(o['reason']) is not str or not _CODE.match(o['reason'])):
        return 'reason is null or a short code'
    if o['determination'] is not None and (type(o['determination']) is not str
                                           or o['determination'] not in DETERMINATIONS):
        return 'unknown determination'
    if o['raw_sha256'] is not None and not _hex(o['raw_sha256']):
        return 'raw_sha256 is null or a lowercase sha256'
    for name in ('effective_limits', 'evidence'):
        if o[name] is not None and (type(o[name]) is not dict or _value_problem(o[name])):
            return f'{name} is null or a bounded exact JSON object'
    costs = o['costs']
    if type(costs) is not dict or set(costs) != set(COST_FIELDS) or not _int(costs['elapsed_ms'], 0, MAX_ELAPSED_MS) \
            or any(costs[n] is not None and not _int(costs[n], 0, MAX_INT)
                   for n in ('solver_rlimit', 'validation_steps')):
        return 'costs are {elapsed_ms, solver_rlimit, validation_steps} as exact counts (the last two may be null)'
    candidates = o['candidates']
    if type(candidates) is not list or len(candidates) > MAX_CANDIDATES:
        return f'candidates is a list of at most {MAX_CANDIDATES}'
    for candidate in candidates:
        problem = _value_problem(candidate)
        if problem:
            return 'a candidate is not a bounded exact value: ' + problem
    if len({_dump(c) for c in candidates}) != len(candidates):
        return 'candidates must be distinct'
    n = len(candidates)
    if d == 'cleanup_failed':
        if not dispatched or reaped is not False:
            return 'cleanup_failed is a dispatched worker that could not be reaped'
    elif reaped is not (True if dispatched else None):
        return 'a dispatched worker is reaped before its outcome is recorded; an undispatched one has reaped null'
    if d in ('accepted', 'diagnosed'):
        if (d == 'accepted') != (mode == 'linear'):
            return f'{d} is not an outcome of mode {mode}'
        if status != 'sat' or not n or not dispatched:
            return f'{d} needs status sat, one or two candidates and a dispatched worker'
        if o['determination'] != ('underdetermined' if n == 2 else 'unassessed'):
            return 'two distinct candidates are underdetermined; one is unassessed'
    elif d == 'no_candidate':
        if status != 'unsat' or n or not dispatched or o['determination'] != 'unassessed':
            return 'no_candidate is a dispatched worker that reported unsat, with no candidate'
    elif d in ('unsupported', 'unavailable', 'timeout', 'unknown'):
        if status != d or n or o['determination'] != 'unassessed':
            return f'{d} has status {d} and no candidate'
    elif status is not None or n or o['determination'] is not None:
        return f'{d} records no solver status, determination or candidate'
    if d in ('accepted', 'diagnosed', 'no_candidate') and (o['raw_sha256'] is None or o['effective_limits'] is None):
        return 'a worker reply is recorded with its raw hash and effective limits'
    return ''


def _owner_problem(owner):
    if type(owner) is not dict or set(owner) != {'host', 'pid', 'start', 'boot', 'token'}:
        return 'an owner is {host, pid, start, boot, token}'
    if type(owner['host']) is not str or not 1 <= len(owner['host']) <= 255 or not _int(owner['pid'], 1, 2**31) \
            or (owner['start'] is not None and not _int(owner['start'], 0, 2**63)) \
            or (owner['boot'] is not None and (type(owner['boot']) is not str or not _BOOT.match(owner['boot']))) \
            or type(owner['token']) is not str or not _TOKEN.match(owner['token']):
        return 'invalid owner fields'
    return ''


def _proc_start(pid):
    """The process start time (clock ticks after boot) from /proc/<pid>/stat, or None."""
    try:
        with open(f'/proc/{pid}/stat', 'rb') as stream:
            raw = stream.read(4096)
        return int(raw[raw.rindex(b')') + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _boot_id():
    try:
        with open('/proc/sys/kernel/random/boot_id', encoding='ascii') as stream:
            text = stream.read(64).strip()
    except (OSError, UnicodeError):
        return None
    return text if _BOOT.match(text) else None


def _process():
    return {'host': (socket.gethostname() or 'unknown')[:255], 'pid': os.getpid(), 'start': _proc_start('self'),
            'boot': _boot_id(), 'token': uuid.uuid4().hex}


def owner_live(owner):
    """Diagnostic only: does a recorded owner look like a process still running here (same host and boot, same pid
    and process start time)? A reused pid has another start time. This grants nothing and resolves nothing."""
    if _owner_problem(owner) or owner['start'] is None or owner['boot'] is None:
        return False
    if owner['host'] != (socket.gethostname() or 'unknown')[:255] or owner['boot'] != _boot_id():
        return False
    return _proc_start(owner['pid']) == owner['start']


def attempt_key(pins, request):
    """The identity of one constructor request under one run's pins: domain-separated, versioned canonical JSON of
    every pinned and requested field. Coordinates or a contract hash alone are not an identity."""
    problem = _pins_problem(pins)
    if problem:
        raise JournalError('invalid_pins', problem)
    problem = _request_problem(request)
    if problem:
        raise JournalError('invalid_request', problem)
    return _sha('key', {'pins': pins, 'request': request})


def select(candidates, policy):
    """The pinned choice among recorded, distinct, native-checked candidates: canonical_min_v1 takes the one whose
    canonical text sorts first. The choice from THIS recorded set is deterministic; it proves nothing about other
    solutions, a least solution or what a new solver run would return."""
    if policy not in SELECTION_POLICIES or type(candidates) is not list or not candidates:
        raise JournalError('invalid_outcome', 'nothing to select, or an unknown selection policy')
    texts = [_dump(c) for c in candidates]
    return min(range(len(texts)), key=texts.__getitem__)


# ---------------------------------------------------------------------------
# Reading: the whole stream, strictly
# ---------------------------------------------------------------------------

class _State:
    def __init__(self):
        self.pins = None
        self.attempts = {}          # attempt id (its intent's seq) -> {'intent', 'outcome', 'reconcile'}
        self.slots = {}             # (occurrence, item) -> [attempt ids, in order]
        self.charged = [0, 0]       # attempts, milliseconds
        self.intents = 0
        self.seq = 0
        self.last = GENESIS
        self.size = 0
        self.quarantined = set()    # quarantine files a repair row names
        self.repairs = 0

    def charged_view(self):
        return {'attempts': self.charged[0], 'milliseconds': self.charged[1]}


def _phase(entry):
    if entry['reconcile'] is not None:
        return 'abandoned'
    row = entry['outcome']
    if row is None:
        return 'open'                       # announced, no recorded end: it may have run
    disposition = row['outcome']['disposition']
    if disposition == 'cleanup_failed':
        return 'blocked'
    if disposition in ('stopped', 'accepted'):
        return disposition
    return 'recorded'


def _damage(code, message, details=None):
    return JournalError(code, message, details)


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate key')
        out[key] = value
    return out


def _no_float(text):
    raise ValueError('a float is not exact')


def _no_constant(text):
    raise ValueError('a non-finite constant is not JSON')


def _parse_row(raw, at):
    if len(raw) + 1 > MAX_ROW_BYTES:
        raise _damage('oversized_row', f'the row at byte {at} is larger than {MAX_ROW_BYTES} bytes', {'at': at})
    try:
        text = raw.decode('ascii')
        row = json.loads(text, object_pairs_hook=_no_duplicates, parse_float=_no_float, parse_constant=_no_constant)
        _measure(row, _ROW_NODES, _ROW_DEPTH, MAX_ROW_BYTES)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _damage('malformed', f'the row at byte {at} is not a strict exact JSON row', {'at': at}) from None
    if type(row) is not dict:
        raise _damage('malformed', f'the row at byte {at} is not an object', {'at': at})
    if _dump(row) != text:
        raise _damage('noncanonical', f'the row at byte {at} is not in canonical form', {'at': at})
    return row


def _apply(state, row, at):
    """Check one row against everything before it and add it to the state. Writer and reader share these rules."""
    def bad(code, message):
        raise _damage(code, f'row {row.get("seq")!r} at byte {at}: {message}', {'at': at, 'seq': row.get('seq')})
    event = row.get('event')
    fields = _EVENT_FIELDS.get(event) if type(event) is str else None
    if fields is None:
        bad('schema', 'unknown event')
    if set(row) != set(_ROW_BASE) | set(fields):
        bad('schema', 'unexpected or missing fields')
    if type(row['v']) is not int or row['v'] != VERSION:
        bad('schema', 'unknown journal version')
    if not _int(row['seq'], 1, MAX_INT) or row['seq'] != state.seq + 1:
        bad('sequence', 'out of sequence')
    if row['prev'] != state.last:
        bad('chain', 'does not follow the previous row')
    if not _int(row['at_ms'], 0, MAX_INT):
        bad('schema', 'invalid time')
    if not _hex(row['sha256']) or row['sha256'] != _sha('row', {k: v for k, v in row.items() if k != 'sha256'}):
        bad('chain', 'its hash differs')
    if event != 'open':
        problem = _owner_problem(row['owner'])
        if problem:
            bad('schema', problem)
    if event == 'open':
        if state.pins is not None:
            bad('state', 'a second open row')
        problem = _pins_problem(row['pins'])
        if problem:
            bad('schema', problem)
        if row['pins_sha256'] != _sha('pins', row['pins']):
            bad('schema', 'pins_sha256 differs')
        state.pins = row['pins']
    elif event == 'intent':
        if state.pins is None:
            bad('state', 'an intent before the open row')
        if type(row['attempt']) is not int or row['attempt'] != row['seq']:
            bad('schema', 'an attempt is named by its intent row')
        request = row['request']
        problem = _request_problem(request)
        if problem:
            bad('schema', problem)
        if row['key'] != _sha('key', {'pins': state.pins, 'request': request}):
            bad('schema', "the key is not this request's key under the journal's pins")
        ms = request['limits']['milliseconds']
        if _dump(row['reserve']) != _dump({'attempts': 1, 'milliseconds': ms}):
            bad('schema', 'an intent reserves one attempt and its milliseconds')
        if _dump(row['charged_before']) != _dump(state.charged_view()):
            bad('budget_record', 'charged_before differs from the record')
        allowance = state.pins['allowance']
        if state.charged[0] + 1 > allowance['attempts'] or state.charged[1] + ms > allowance['milliseconds'] \
                or state.intents >= MAX_ATTEMPTS:
            bad('budget_record', 'it reserves beyond the allowance or journal')
        if type(row['deadline_at_ms']) is not int or not row['at_ms'] < row['deadline_at_ms'] <= row['at_ms'] + ms:
            bad('schema', 'deadline_at_ms is the time left of the reservation after at_ms')
        cont = row['continues']
        if cont is not None and type(cont) is not int:
            bad('schema', 'continues is null or an attempt')
        slot = (request['occurrence'], request['item'])
        prior = state.slots.get(slot)
        if prior:
            if _dump(state.attempts[prior[0]]['intent']['request']) != _dump(request):
                bad('state', "a slot's request changed")
            if cont != prior[-1] or _phase(state.attempts[prior[-1]]) not in _CONTINUABLE:
                bad('state', 'a second attempt must continue a stopped or abandoned last attempt')
        elif cont is not None:
            bad('state', 'it continues an attempt of another slot')
        state.attempts[row['attempt']] = {'intent': row, 'outcome': None, 'reconcile': None}
        state.slots.setdefault(slot, []).append(row['attempt'])
        state.charged[0] += 1
        state.charged[1] += ms
        state.intents += 1
    elif event == 'outcome':
        entry = state.attempts.get(row['attempt']) if type(row['attempt']) is int else None
        if entry is None:
            bad('state', 'an outcome for no intent')
        if entry['outcome'] is not None or entry['reconcile'] is not None:
            bad('state', 'a second terminal record for one attempt')
        if row['key'] != entry['intent']['key']:
            bad('state', "the key is not its intent's")
        if _dump(row['owner']) != _dump(entry['intent']['owner']):
            bad('state', 'an outcome written by another execution')
        out = row['outcome']
        problem = _outcome_problem(state.pins['mode'], out)
        if problem:
            bad('schema', problem)
        if out['disposition'] == 'accepted':
            index = select(out['candidates'], state.pins['selection_policy'])
            if type(row['selected']) is not int or row['selected'] != index \
                    or row['selected_sha256'] != _sha('candidate', out['candidates'][index]):
                bad('schema', "the selection is not the pinned policy's")
        elif row['selected'] is not None or row['selected_sha256'] is not None:
            bad('schema', 'only an accepted outcome selects')
        entry['outcome'] = row
        if out['dispatched'] is False:      # nothing ran: its own execution gives the reservation back
            state.charged[0] -= 1
            state.charged[1] -= entry['intent']['request']['limits']['milliseconds']
    elif event == 'reconcile':
        entry = state.attempts.get(row['attempt']) if type(row['attempt']) is int else None
        if entry is None or _phase(entry) not in ('open', 'blocked'):
            bad('state', 'only an unknown or blocked attempt is reconciled')
        if row['verdict'] != 'abandoned' or type(row['note']) is not str or len(row['note']) > MAX_NOTE \
                or type(row['forced']) is not bool:
            bad('schema', 'a reconcile row is {verdict: abandoned, note, forced}')
        entry['reconcile'] = row
    else:                                   # repair
        if not _int(row['truncated_bytes'], 1, MAX_ROW_BYTES) or not _hex(row['torn_sha256']) \
                or row['quarantine'] not in tuple(_quarantine_name(i) for i in range(MAX_REPAIRS)):
            bad('schema', 'a repair row names the bytes it cut (at most one row) and where they were kept')
        if row['quarantine'] in state.quarantined:
            bad('state', 'a quarantine slot cannot record two repairs')
        if state.repairs >= MAX_REPAIRS:
            bad('state', f'more than {MAX_REPAIRS} repairs')
        state.repairs += 1
        state.quarantined.add(row['quarantine'])
    state.seq = row['seq']
    state.last = row['sha256']


def _validate(data):
    end = data.rfind(b'\n') + 1
    if end != len(data):
        torn = data[end:]
        raise _damage('torn_tail', 'the journal ends inside a row (an interrupted write); the owner repairs it',
                      {'complete_bytes': end, 'torn_bytes': len(torn),
                       'torn_sha256': hashlib.sha256(torn).hexdigest()})
    state = _State()
    pos = 0
    while pos < len(data):
        nl = data.index(b'\n', pos)
        _apply(state, _parse_row(data[pos:nl], pos), pos)
        pos = nl + 1
    state.size = len(data)
    return state


def _cleanup(action, primary=None, stream=None):
    """Cleanup cannot replace an in-flight exception; a new failure still propagates."""
    try:
        action()
    except BaseException as exc:
        message = f'journal cleanup failed ({type(exc).__name__}); this object performs nothing further'
        if stream is not None:
            stream._poisoned = message
        if primary is not None:
            try:
                primary.add_note(message)
            except BaseException:
                pass
        elif isinstance(exc, OSError):
            raise JournalError('durability', message) from exc
        else:
            raise


@contextlib.contextmanager
def _closing(fd, stream=None):
    primary = None
    try:
        yield fd
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if fd is not None:
            _cleanup(lambda: os.close(fd), primary, stream)


def _open_regular(path, flags):
    """Open a run-folder file without following a link and without blocking: a FIFO, device or socket is refused,
    never waited on (O_NONBLOCK; lstat before, fstat after, same inode). OSError propagates for the caller to type."""
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        before = None
    if before is not None and not stat.S_ISREG(before.st_mode):
        raise _damage('unsafe_file', f'{os.path.basename(path)} is not a regular file')
    fd = os.open(path, flags | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (before is not None and
                                                (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)):
            raise _damage('unsafe_file', f'{os.path.basename(path)} changed while opened or is not a regular file')
    except BaseException as exc:
        _cleanup(lambda: os.close(fd), exc)
        raise
    return fd


def _opening_error(exc, what):
    code = 'unsafe_file' if exc.errno in (errno.ELOOP, errno.ENXIO) else 'unreadable'
    return _damage(code, f'{what} cannot be opened ({exc.strerror})')


def _read_bytes(path):
    """The whole file, bounded; b'' when absent."""
    try:
        fd = _open_regular(path, os.O_RDONLY)
    except FileNotFoundError:
        return b''
    except OSError as exc:
        raise _opening_error(exc, os.path.basename(path)) from None
    with _closing(fd):
        return _read_open_bytes(fd, path)


def _read_open_bytes(fd, path):
    try:
        if os.fstat(fd).st_size > MAX_JOURNAL_BYTES:
            raise _damage('oversized_journal', f'the journal is larger than {MAX_JOURNAL_BYTES} bytes')
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_JOURNAL_BYTES:
                raise _damage('oversized_journal', f'the journal is larger than {MAX_JOURNAL_BYTES} bytes')
            chunks.append(chunk)
        return b''.join(chunks)
    except OSError as exc:
        raise _damage('unreadable', f'{os.path.basename(path)} cannot be read ({exc.strerror})') from None


def _open_lock(folder, create):
    try:
        return _open_regular(os.path.join(folder, LOCK_FILE), (os.O_RDWR | os.O_CREAT) if create else os.O_RDONLY)
    except FileNotFoundError:
        if create:
            raise JournalError('no_folder', 'the run folder does not exist') from None
        return None
    except OSError as exc:
        raise _opening_error(exc, 'the journal lock') from None


def _wait(take, until, check_stop=None):
    """Try take() until it succeeds or `until` (monotonic) passes, every LOCK_POLL_SECONDS. check_stop runs after
    every failed try, the last one included, so a pending stop always wins over a timeout; its exception propagates
    unchanged and nothing has been taken. False when the time ran out. (v2, review J1: both the object lock and the
    folder lock wait here.)"""
    while True:
        if take():
            return True
        if check_stop is not None:
            check_stop()
        left = until - time.monotonic()
        if left <= 0:
            return False
        time.sleep(min(LOCK_POLL_SECONDS, left))


def _flock(fd, kind, until, check_stop=None):
    def take():
        try:
            fcntl.flock(fd, kind | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
        except OSError as exc:
            raise _damage('unreadable', f'the journal lock failed ({exc.strerror})') from None
    return _wait(take, until, check_stop)


def _shared_state(folder, until):
    """A consistent read that writes nothing: under a shared lock when a writer has ever been here."""
    fd = _open_lock(folder, False)
    if fd is None and os.path.lexists(os.path.join(folder, FILE)):
        fd = _open_lock(folder, False)      # a writer appeared meanwhile (or a copied folder has no lock)
    with _closing(fd):
        if fd is not None and not _flock(fd, fcntl.LOCK_SH, until):
            raise JournalError('busy', 'a writer held the journal; nothing was read')
        return _validate(_read_bytes(os.path.join(folder, FILE)))


def _quarantine_name(slot):
    return f'constructor-events.torn-{slot}.bin'


def _sync_folder(folder):
    directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    with _closing(directory):
        os.fsync(directory)


def _write_all(fd, data):
    view = memoryview(data)
    while view:                             # a short write is continued, never left as half a row
        count = os.write(fd, view)
        if count <= 0:
            raise OSError(errno.EIO, 'journal write made no progress')
        view = view[count:]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

class _Stream:
    """One run folder's journal and lock, and the write path shared by Journal and the owner's tools."""

    def __init__(self, folder):
        if type(folder) is not str or not folder or '\0' in folder:
            raise JournalError('no_folder', 'a run folder path is required')
        self.folder = folder
        self.path = os.path.join(folder, FILE)
        self._lock = threading.Lock()       # one transaction of this object at a time; never taken twice
        self._owner = _process()            # one execution identity per object (reads /proc, not the run folder)
        self._poisoned = ''

    def _me(self):
        if self._owner['pid'] != os.getpid():
            raise JournalError('not_owner', 'a journal object belongs to the process that made it (not across fork)')
        return self._owner

    @staticmethod
    def _expired(deadline):
        if deadline is not None and time.monotonic() >= deadline:
            return JournalError('budget', "the attempt's deadline passed while waiting for the journal; "
                                'nothing was announced')
        return JournalError('busy', 'the journal stayed locked; nothing was done')

    @contextlib.contextmanager
    def _object_lock(self, until, deadline, check_stop=None):
        if not _wait(lambda: self._lock.acquire(blocking=False), until, check_stop):
            raise self._expired(deadline)
        primary = None
        try:
            if self._poisoned:
                raise JournalError('durability', self._poisoned)
            if not os.path.isdir(self.folder):
                raise JournalError('no_folder', 'the run folder does not exist (the journal never creates it)')
            yield
        except BaseException as exc:
            primary = exc
            raise
        finally:
            _cleanup(self._lock.release, primary, self)

    @contextlib.contextmanager
    def _held(self, *, deadline=None, check_stop=None):
        """This object's lock, then the folder's exclusive flock, each waited for at most LOCK_WAIT_SECONDS and never
        past `deadline` ('budget' when it passed, else 'busy'; nothing is done). Not re-entered; never held while
        a worker runs."""
        until = time.monotonic() + LOCK_WAIT_SECONDS
        if deadline is not None:
            until = min(until, deadline)
        with self._object_lock(until, deadline, check_stop):
            fd = _open_lock(self.folder, True)
            with _closing(fd, self):
                if not _flock(fd, fcntl.LOCK_EX, until, check_stop):
                    raise self._expired(deadline)
                yield

    @contextlib.contextmanager
    def _locked(self, exclusive, *, deadline=None, check_stop=None):
        """One transaction over the validated journal: exclusive for a writer, shared for a reader."""
        if exclusive:
            with self._held(deadline=deadline, check_stop=check_stop):
                yield _validate(_read_bytes(self.path))
            return
        until = time.monotonic() + LOCK_WAIT_SECONDS
        with self._object_lock(until, None):
            yield _shared_state(self.folder, until)

    def _append(self, state, events):
        """Seal each (event, fields) against the state, check it with the reader's rules, then write the rows whole
        and fsync them and the folder before returning. Call inside _held."""
        before, now, lines, rows = state.size, int(time.time() * 1000), [], []
        for event, fields in events:
            if callable(fields):
                fields = fields(state, now)
            row = {'v': VERSION, 'seq': state.seq + 1, 'prev': state.last, 'event': event, 'at_ms': now, **fields}
            row['sha256'] = _sha('row', row)
            line = _dump(row) + '\n'
            if len(line) > MAX_ROW_BYTES:
                raise JournalError('oversized_row', f'a {event} row would be larger than {MAX_ROW_BYTES} bytes')
            try:
                _apply(state, row, state.size)
            except JournalError as exc:
                raise JournalError('internal', f'the journal refused its own {event} row: {exc}') from None
            state.size += len(line)
            lines.append(line)
            rows.append(row)
        if state.size > MAX_JOURNAL_BYTES:
            raise JournalError('journal_full', f'the journal would exceed {MAX_JOURNAL_BYTES} bytes')
        data = ''.join(lines).encode('ascii')
        written = False
        try:
            try:
                fd = _open_regular(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                fd = _open_regular(self.path, os.O_WRONLY | os.O_APPEND)
        except OSError as exc:
            raise JournalError('durability', f'the journal cannot be opened for writing ({exc.strerror})') from None
        with _closing(fd, self):
            if os.fstat(fd).st_size != before:
                raise _damage('state', 'the journal changed outside its lock')
            # v2 (review J2): latched BEFORE the first byte and cleared only once the rows and the folder are synced,
            # so no interruption anywhere (a stop, a signal, a second interruption during the rollback below) can
            # leave this object able to announce anything again.
            self._poisoned = 'a journal write did not finish; this object performs nothing further'
            try:
                _write_all(fd, data)
                written = True
                os.fsync(fd)
                # v2 (review J3): the folder is synced after EVERY write, not only by the object that created the
                # file: a file left by an interrupted first write was never confirmed in its directory.
                _sync_folder(self.folder)
            except BaseException as exc:
                # Nothing unsynced is announced. An unfinished row is cut back (what cannot be cut stays a torn tail,
                # which every reader refuses); a whole but unsynced row stays and reads as possibly done. Priority:
                # the first stop or interruption is what propagates; a failure while cutting back is noted on it. An
                # interruption during the cut outranks only an I/O error (it then propagates with that as context).
                self._poisoned = f'a journal write was interrupted ({type(exc).__name__}); nothing further is done'
                if not written:
                    try:
                        os.ftruncate(fd, before)
                        os.fsync(fd)
                    except OSError as cleanup:
                        exc.add_note(f'cutting back the unfinished row failed ({cleanup.strerror}); a torn tail may '
                                     'remain, which every reader refuses')
                    except BaseException as cleanup:
                        if isinstance(exc, OSError):
                            raise
                        exc.add_note(f'cutting back the unfinished row was interrupted ({type(cleanup).__name__})')
                if isinstance(exc, OSError):
                    failure = JournalError('durability', f'{self._poisoned}: {exc.strerror}')
                    for note in getattr(exc, '__notes__', ()):
                        failure.add_note(note)
                    raise failure from None
                raise
        self._poisoned = ''                 # successful close is part of the write, not cleanup after success
        return rows


class Attempt:
    """A begun attempt. Process-local: its deadline is this process's monotonic clock, and only the execution that
    began it may complete it. It is never persisted as authority."""
    __slots__ = ('folder', 'attempt', 'key', 'request', 'milliseconds', 'deadline', 'token', 'continues')

    def __init__(self, **fields):
        for name in self.__slots__:
            setattr(self, name, fields[name])

    def remaining(self):
        """Seconds left of this attempt's one deadline (preflight, wait, worker and validation); never reset."""
        return max(0.0, self.deadline - time.monotonic())


def _unresolved(state):
    return [aid for aid, entry in state.attempts.items() if _phase(entry) in ('open', 'blocked')]


class Journal(_Stream):
    """The constructor journal of one run folder under fixed pins. replay=True only reads: it never writes, launches
    or creates a file, and a slot without a record is `missing`, not something to attempt."""

    def __init__(self, folder, pins, *, replay=False):
        super().__init__(folder)
        problem = _pins_problem(pins)
        if problem:
            raise JournalError('invalid_pins', problem)
        if type(replay) is not bool:
            raise JournalError('invalid_pins', 'replay is a bool')
        self.pins = copy.deepcopy(pins)
        self.replay = replay

    def _slot(self, state, request):
        """The slot's attempt ids after the drift checks; [] for a slot (or journal) without a record."""
        if state.pins is None:
            return []
        drift = _differs(state.pins, self.pins, PIN_FIELDS)
        if drift:
            raise JournalError('drift', 'the journal was opened under other pins: ' + ', '.join(drift),
                               {'fields': drift})
        prior = state.slots.get((request['occurrence'], request['item']), [])
        if prior:
            drift = _differs(state.attempts[prior[0]]['intent']['request'], request, REQUEST_FIELDS)
            if drift:
                raise JournalError('drift', 'this slot was attempted under another request: ' + ', '.join(drift),
                                   {'fields': drift, 'attempt': prior[0]})
        return prior

    @staticmethod
    def _refuse_open(entry, aid):
        phase = _phase(entry)
        if phase == 'open':
            intent = entry['intent']
            raise JournalError('uncertain', f'attempt {aid} was announced and has no recorded outcome, so it may have '
                               'run; the owner reconciles it, it is never dispatched again by itself',
                               {'attempt': aid, 'at_ms': intent['at_ms'], 'owner_live': owner_live(intent['owner'])})
        if phase == 'blocked':
            raise JournalError('blocked', f"attempt {aid}'s worker could not be reaped; the owner resolves it first",
                               {'attempt': aid})
        return phase

    def lookup(self, request):
        """What the record decides for this request's slot. Never writes or creates a file. Raises JournalError for
        uncertain, blocked, drift, busy and damage; otherwise returns a decision:

        kind fresh (live, no record) -> action attempt; missing (replay, no record) -> refuse;
        accepted -> adopt `value` (after the caller's native recheck); recorded -> fallback (no new search);
        stopped -> stop (a live run may explicitly continue it); abandoned -> refuse (likewise).
        `unresolved` lists the run's unknown or blocked attempts in other slots: begin refuses while any remain."""
        problem = _request_problem(request)
        if problem:
            raise JournalError('invalid_request', problem)
        with self._locked(False) as state:
            prior = self._slot(state, request)
            out = {'kind': None, 'action': None, 'attempt': None, 'disposition': None, 'value': None,
                   'record': None, 'continuable': False, 'replay': self.replay, 'unresolved': _unresolved(state),
                   'allowance': copy.deepcopy(self.pins['allowance']), 'charged': state.charged_view()}
            if not prior:
                if self.replay:
                    out.update(kind='missing', action='refuse')
                else:
                    out.update(kind='fresh', action='attempt')
                return out
            aid = prior[-1]
            entry = state.attempts[aid]
            phase = self._refuse_open(entry, aid)
            row = entry['reconcile'] if phase == 'abandoned' else entry['outcome']
            out.update(attempt=aid, record=copy.deepcopy(row))
            if phase == 'abandoned':
                out.update(kind='abandoned', action='refuse', continuable=not self.replay)
                return out
            result = row['outcome']
            out['disposition'] = result['disposition']
            if phase == 'accepted':
                out.update(kind='accepted', action='adopt',
                           value=copy.deepcopy(result['candidates'][row['selected']]))
            elif phase == 'stopped':
                out.update(kind='stopped', action='stop', continuable=not self.replay)
            else:
                out.update(kind='recorded', action='fallback')
            return out

    def begin(self, request, *, continues=None, started=None, check_stop=None):
        """Reserve one attempt and announce it durably. Returns only once the intent row is synced: dispatch after
        this returns, never before. The attempt has ONE deadline, `started` (this process's monotonic clock, default
        now) plus its milliseconds, covering preflight, the journal wait, the worker and validation: the wait never
        passes it, it is checked again once the lock is held, and the intent records the time actually left.
        `check_stop` is called before, during and after the wait; its exception propagates and nothing is written.
        Refuses instead of writing when a record decides the slot, any attempt of the run is unknown or blocked
        (one attempt at a time per run), the pins drifted, the allowance or journal is spent, or this is a replay."""
        if self.replay:
            raise JournalError('replay', 'a replay never starts an attempt')
        problem = _request_problem(request)
        if problem:
            raise JournalError('invalid_request', problem)
        if continues is not None and not _int(continues, 1, MAX_INT):
            raise JournalError('continuation', 'continues names an attempt')
        if check_stop is not None and not callable(check_stop):
            raise JournalError('invalid_request', 'check_stop is a callable or None')
        now = time.monotonic()
        if started is None:
            started = now
        elif type(started) not in (int, float) or not started <= now:
            raise JournalError('invalid_request', "started is this process's monotonic time, not later than now")
        request = copy.deepcopy(request)
        ms = request['limits']['milliseconds']
        deadline = started + ms / 1000
        if now >= deadline:
            raise JournalError('budget', "the attempt's deadline passed before dispatch; nothing was announced")
        if check_stop is not None:
            check_stop()
        key = attempt_key(self.pins, request)
        owner = self._me()
        with self._locked(True, deadline=deadline, check_stop=check_stop) as state:
            prior = self._slot(state, request)
            if prior:
                phase = self._refuse_open(state.attempts[prior[-1]], prior[-1])
                if phase not in _CONTINUABLE:
                    raise JournalError('recorded', f'this slot has a recorded {phase} outcome; it is replayed, '
                                       'never searched again', {'attempt': prior[-1]})
                if continues != prior[-1]:
                    raise JournalError('continuation', f'the last attempt ({prior[-1]}) was {phase}; a new attempt '
                                       f'is explicit: continues={prior[-1]}', {'attempt': prior[-1]})
            elif continues is not None:
                raise JournalError('continuation', 'there is no attempt to continue in this slot')
            unresolved = _unresolved(state)
            if unresolved:
                raise JournalError('unresolved', 'an attempt of this run is unknown or blocked; one constructor '
                                   'attempt runs at a time per run, so the owner resolves it first',
                                   {'attempts': unresolved})
            allowance, charged = self.pins['allowance'], state.charged_view()
            if charged['attempts'] + 1 > allowance['attempts'] \
                    or charged['milliseconds'] + ms > allowance['milliseconds']:
                raise JournalError('budget', "the run's constructor allowance is spent",
                                   {'allowance': allowance, 'charged': charged, 'requested': ms})
            if state.intents >= MAX_ATTEMPTS:
                raise JournalError('journal_full', f'the journal holds its limit of {MAX_ATTEMPTS} attempts')
            if check_stop is not None:
                check_stop()
            events = [] if state.pins is not None else [('open', {'pins': self.pins,
                                                                  'pins_sha256': _sha('pins', self.pins)})]

            def intent(current, at_ms):       # after any open row: its sequence number, charges and time left
                left = math.floor((deadline - time.monotonic()) * 1000)
                if left < 1:
                    raise JournalError('budget', "the attempt's deadline passed before its intent was written; "
                                       'nothing was announced')
                return {'attempt': current.seq + 1, 'key': key, 'request': request,
                        'reserve': {'attempts': 1, 'milliseconds': ms}, 'charged_before': current.charged_view(),
                        'continues': continues, 'deadline_at_ms': at_ms + min(left, ms), 'owner': owner}
            events.append(('intent', intent))
            row = self._append(state, events)[-1]
        return Attempt(folder=self.folder, attempt=row['attempt'], key=key, request=request, milliseconds=ms,
                       deadline=deadline, token=owner['token'], continues=continues)

    def complete(self, attempt, outcome):
        """Record how a begun attempt ended and return {'record', 'value', 'adoptable'} only once the row is synced.
        Adopt only `value`, and only when adoptable (an accepted outcome, selected by the pinned policy). A refusal
        ('busy' included) records nothing: the attempt stays unknown and nothing may be adopted from it."""
        if self.replay:
            raise JournalError('replay', 'a replay never records an outcome')
        owner = self._me()
        if not isinstance(attempt, Attempt) or attempt.folder != self.folder or attempt.token != owner['token']:
            raise JournalError('not_owner', 'only the execution that began an attempt completes it')
        problem = _outcome_problem(self.pins['mode'], outcome)
        if problem:
            raise JournalError('invalid_outcome', problem)
        outcome = copy.deepcopy(outcome)
        with self._locked(True) as state:
            self._slot(state, attempt.request)
            entry = state.attempts.get(attempt.attempt)
            if entry is None or entry['intent']['key'] != attempt.key:
                raise _damage('state', f'attempt {attempt.attempt} is not announced in this journal')
            if entry['intent']['owner']['token'] != owner['token']:
                raise JournalError('not_owner', 'only the execution that began an attempt completes it')
            if _phase(entry) != 'open':
                raise JournalError('conflict', f'attempt {attempt.attempt} already has a terminal record',
                                   {'attempt': attempt.attempt})
            selected = selected_sha = None
            if outcome['disposition'] == 'accepted':
                selected = select(outcome['candidates'], self.pins['selection_policy'])
                selected_sha = _sha('candidate', outcome['candidates'][selected])
            row = self._append(state, [('outcome', {'attempt': attempt.attempt, 'key': attempt.key,
                                                    'outcome': outcome, 'selected': selected,
                                                    'selected_sha256': selected_sha, 'owner': owner})])[0]
        value = None if selected is None else copy.deepcopy(outcome['candidates'][selected])
        return {'record': copy.deepcopy(row), 'value': value, 'adoptable': selected is not None}


# ---------------------------------------------------------------------------
# The owner's tools and read-only views
# ---------------------------------------------------------------------------

def reconcile(folder, attempt, *, note='', force=False):
    """The owner's word on an attempt whose outcome is unknown (announced, never ended) or whose worker could not be
    reaped (cleanup_failed): it is abandoned. Its reservation stays charged and nothing about its result is assumed;
    a later attempt in its slot must name it explicitly. An unknown attempt is refused while the process that began
    it still looks alive (it may be running it), unless forced; a blocked one was ended by that process itself."""
    if not _int(attempt, 1, MAX_INT) or type(note) is not str or len(note) > MAX_NOTE or type(force) is not bool:
        raise JournalError('invalid_request', 'reconcile(folder, attempt id, note=text, force=bool)')
    stream = _Stream(folder)
    owner = stream._me()
    with stream._locked(True) as state:
        entry = state.attempts.get(attempt)
        if entry is None:
            raise JournalError('state', f'there is no attempt {attempt} in this journal')
        phase = _phase(entry)
        if phase not in ('open', 'blocked'):
            raise JournalError('state', f'attempt {attempt} is {phase}; '
                               'only an unknown or blocked attempt is abandoned')
        if phase == 'open' and owner_live(entry['intent']['owner']) and not force:
            raise JournalError('owner_live', f'the process that began attempt {attempt} still looks alive',
                               {'attempt': attempt})
        row = stream._append(state, [('reconcile', {'attempt': attempt, 'verdict': 'abandoned', 'note': note,
                                                    'forced': force, 'owner': owner})])[0]
    return copy.deepcopy(row)


def _keep(folder, name, data):
    """Reserve a fixed slot durably before its first byte; retain interrupted writes in that same slot.

    There is no temporary quarantine file outside the eight slots. Partial or empty slots remain occupied and
    consume capacity. A complete existing match is resynced before the journal may be cut.
    """
    if name not in tuple(_quarantine_name(i) for i in range(MAX_REPAIRS)) or not 1 <= len(data) <= MAX_ROW_BYTES:
        raise JournalError('state', 'invalid quarantine slot or byte count')
    path = os.path.join(folder, name)
    if os.path.lexists(path):
        if _read_bytes(path) != data:
            raise JournalError('state', f'{name} exists with other bytes')
        with _closing(_open_regular(path, os.O_RDONLY)) as fd:
            os.fsync(fd)
    else:
        with _closing(_open_regular(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)) as fd:
            os.fsync(fd)                    # reservation inode
            _sync_folder(folder)           # reservation name before any retained byte
            _write_all(fd, data)
            os.fsync(fd)
    _sync_folder(folder)


def _quarantined(folder, state, sha):
    """Find an unaudited complete match among eight fixed paths; partial reservations stay occupied."""
    match = None
    for slot in range(MAX_REPAIRS):
        name = _quarantine_name(slot)
        path = os.path.join(folder, name)
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            if name in state.quarantined:
                raise JournalError('state', f'recorded quarantine slot {name} is missing') from None
            continue
        if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_ROW_BYTES:
            raise JournalError('state', f'{name} is not a bounded quarantine slot')
        if name in state.quarantined:
            continue
        data = _read_bytes(path)
        if len(data) != info.st_size or len(data) > MAX_ROW_BYTES:
            raise JournalError('state', f'{name} changed while read')
        if data and hashlib.sha256(data).hexdigest() == sha and match is None:
            match = (name, len(data))
    return match


def _free_quarantine(folder, state):
    for slot in range(MAX_REPAIRS):
        name = _quarantine_name(slot)
        if name not in state.quarantined and not os.path.lexists(os.path.join(folder, name)):
            return name
    raise JournalError('repair_limit', f'all {MAX_REPAIRS} quarantine slots are occupied; explicit review is required')


def repair_torn_tail(folder, torn_sha256):
    """The owner's repair of a journal that ends inside a row (a crash or failed write mid-row). `torn_sha256` is the
    hash the torn_tail refusal reported: the owner confirms exactly what is cut. Order, each step durable before the
    next: the torn bytes are kept in a quarantine file (synced, named, folder synced), the journal is cut back to
    its last whole row (synced), and a repair row records the cut. A crash before the cut leaves the journal torn and
    the repair can simply run again; a crash after the cut leaves a sound journal and the quarantine file, and running
    the repair again with the same hash writes the missing repair row. Cutting never hides work: a torn intent was
    never synced, so nothing was dispatched after it; a torn outcome leaves its intent without an end, which stays
    uncertain. Any other damage is evidence and stays refused."""
    if not _hex(torn_sha256):
        raise JournalError('invalid_request', 'torn_sha256 is the hash the torn_tail refusal reported')
    stream = _Stream(folder)
    owner = stream._me()
    with stream._held():
        data = _read_bytes(stream.path)
        end = data.rfind(b'\n') + 1
        torn = data[end:]
        state = _validate(data[:end])           # the whole rows must be sound; other damage is not repaired
        if state.repairs >= MAX_REPAIRS:
            raise JournalError('repair_limit', f'this journal already records {MAX_REPAIRS} repairs; the owner '
                               'reviews the run folder by hand')
        try:
            if not torn:
                pending = _quarantined(folder, state, torn_sha256)
                if pending is None:
                    raise JournalError('state', 'the journal does not end inside a row, and no unrecorded repair '
                                       'of these bytes is pending')
                name, size = pending
            else:
                if hashlib.sha256(torn).hexdigest() != torn_sha256:
                    raise JournalError('state', 'the torn bytes are not the ones confirmed')
                if len(torn) > MAX_ROW_BYTES:
                    raise JournalError('state', 'the torn bytes are longer than any row this journal writes')
                pending = _quarantined(folder, state, torn_sha256)
                name, size = pending or (_free_quarantine(folder, state), len(torn))
                _keep(folder, name, torn)
                journal = _open_regular(stream.path, os.O_WRONLY)
                with _closing(journal, stream):
                    os.ftruncate(journal, end)
                    os.fsync(journal)
        except OSError as exc:
            raise JournalError('durability', f'the repair could not be completed ({exc.strerror})') from None
        row = stream._append(state, [('repair', {'truncated_bytes': size, 'torn_sha256': torn_sha256,
                                                 'quarantine': name, 'owner': owner})])[0]
    return copy.deepcopy(row)


def work_count(folder):
    """Attempts announced in a run folder's journal, for work detection (kernel_gate style). A journal that cannot be
    read, or stays locked, counts at least once: something may have been done. Reads only."""
    if not os.path.lexists(os.path.join(folder, FILE)):
        return 0
    try:
        return _shared_state(folder, time.monotonic() + LOCK_WAIT_SECONDS).intents
    except JournalError:
        return 1


def summary(folder):
    """A bounded, typed view for result and lock APIs. Reads only; a damaged or locked journal is reported."""
    out = {'version': VERSION, 'file': FILE, 'present': os.path.lexists(os.path.join(folder, FILE)),
           'problem': None, 'attempts': 0, 'events': 0, 'bytes': 0, 'allowance': None, 'charged': None,
           'phases': {}, 'dispositions': {}, 'uncertain': [], 'blocked': []}
    try:
        state = _shared_state(folder, time.monotonic() + LOCK_WAIT_SECONDS)
    except JournalError as exc:
        out['problem'] = {'code': exc.code, 'message': str(exc)[:256]}
        return out
    out.update(attempts=state.intents, events=state.seq, bytes=state.size, charged=state.charged_view(),
               allowance=None if state.pins is None else copy.deepcopy(state.pins['allowance']))
    for aid, entry in state.attempts.items():
        phase = _phase(entry)
        out['phases'][phase] = out['phases'].get(phase, 0) + 1
        if entry['outcome'] is not None:
            disposition = entry['outcome']['outcome']['disposition']
            out['dispositions'][disposition] = out['dispositions'].get(disposition, 0) + 1
        if phase == 'open':
            out['uncertain'].append(aid)
        elif phase == 'blocked':
            out['blocked'].append(aid)
    return out
