"""Constructor inspection: read-only recovery evidence for one run folder (`tools/symblic constructor inspect`).

What it is for
    After a crash or a lost context, another agent (or a person) needs to know what happened in a run folder
    that used the constructor, and what it may safely do next. inspect(folder) reads a fixed list of bounded
    paths inside the folder and returns a compact, deterministic JSON report: a classification (for example
    'attempts_settled', 'attempt_uncertain', 'journal_torn', 'records_damaged', 'history_unknowable') and the
    next steps, each tagged with who may take it: 'agent' (any automated caller), 'owner' (the person who
    operates the run folder: only they may reconcile or repair) or 'none'.

    python3 -m symblic.constructor.inspect inspect FOLDER [--agent-json]   (exit 0, or 1 when nothing is there)

What it never does
    It never lists a directory, follows a symlink, opens a FIFO or special file, takes or creates the journal
    lock, imports or inventories a solver, launches a model or worker, repairs, truncates, renames or deletes
    anything, or writes the folder. A report is one snapshot: paths are lstat-ed before and after, and any
    change is reported as 'snapshot_inconsistent'. Hashes identify exact bytes for a handoff; they do not
    authenticate anything. 'authorizes_retry' is always false.

Depends on: symblic.kernel (language, evidence, run) and symblic.constructor (journal, records). Used by:
tools/symblic constructor. Status: prototype with unit tests, including the command line in a child process
(tests/constructor/test_symblic_constructor_inspect.py).
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import argparse
import hashlib
import json
import os
import stat
import sys

from symblic.kernel import language as S
from symblic.constructor import journal as J
from symblic.constructor import records as R
from symblic.kernel import evidence as E
from symblic.kernel import run as SR

SCHEMA = 'symblic.constructor.inspect'
VERSION = 1
BRIDGE_MARKER = 2                     # the only snapshot marker value this reader treats as checkpointed history
HISTORY_BYTES = 16 * 1024 * 1024      # state.json, trace.jsonl and meta.json: the native history/preflight bounds
TRACE_ROWS = 32768
TRACE_ROW_BYTES = 4 * 1024 * 1024
KERNEL_BYTES = 65536
MAX_TRACE_KERNELS = 8
SCOPE = ('Snapshot evidence read from fixed paths; not authenticated host state. It grants no permission to '
         'retry, reconcile, repair or delete; an uncertain attempt may have run.')
RECORD_FILES = {                       # key -> (fixed name, byte bound); nothing outside this list is read
    'program': ('program.sym', 4 * S.MAX_SOURCE),
    'meta': ('meta.json', HISTORY_BYTES),
    'kernel_record': (SR.KERNEL_RECORD, KERNEL_BYTES),
    'state': ('state.json', HISTORY_BYTES),
    'trace': ('trace.jsonl', HISTORY_BYTES),
    'config': (R.CONFIG_FILE, R.MAX_CONFIG_BYTES),
    'journal': (J.FILE, J.MAX_JOURNAL_BYTES),
}
PRESENCE_ONLY = {'lock': J.LOCK_FILE, 'calls': 'calls.jsonl', 'portable_lock': 'run.lock.json'}
SLOTS = tuple(J._quarantine_name(slot) for slot in range(J.MAX_REPAIRS))
# Highest first: the first label whose condition holds is the classification. Every condition is also a reason.
CLASSIFICATIONS = ('folder_absent', 'folder_unsafe', 'snapshot_inconsistent', 'records_damaged', 'journal_torn',
                   'repair_unfinished', 'attempt_blocked', 'attempt_uncertain', 'records_incomplete',
                   'history_unknowable', 'attempts_settled', 'no_attempt_recorded', 'no_constructor_history',
                   'inspection_failed')


def _kind(info):
    if info is None:
        return 'absent'
    mode = info.st_mode
    return ('regular' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else
            'directory' if stat.S_ISDIR(mode) else 'fifo' if stat.S_ISFIFO(mode) else 'special')


def _lstat(path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _signature(info):
    if info is None:
        return None
    return (info.st_mode, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(folder, name, limit):
    """(observation, raw bytes or None). Reuses the strict records reader: regular files only, O_NOFOLLOW and
    O_NONBLOCK, same inode before and after opening, bounded before and while reading."""
    info = _lstat(os.path.join(folder, name))
    kind = _kind(info)
    seen = {'name': name, 'kind': kind}
    if kind == 'absent':
        return seen, None
    if kind != 'regular':
        seen['problem'] = 'unsafe'
        return seen, None
    if info.st_size > limit:
        seen.update(bytes=info.st_size, problem='oversized')
        return seen, None
    try:
        raw = R._regular_bytes(os.path.join(folder, name), limit)
    except R.RecordsError as exc:
        seen['problem'] = {'unsafe_file': 'unsafe', 'size': 'oversized'}.get(exc.code, 'unreadable')
        return seen, None
    if raw is None:                    # removed between lstat and open: a writer is active
        seen.update(kind='absent', problem='vanished')
        return seen, None
    seen.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return seen, raw


def _strict_json(raw):
    """Bounded strict JSON object (duplicate keys and non-finite numbers refused) via the native history parser."""
    return SR._constructor_history_json(raw)


def _marker(row):
    if 'constructor_bridge' not in row:
        return 'absent'
    value = row['constructor_bridge']
    if type(value) is not int:         # bool, float, text, null or a container asserts nothing
        return 'malformed'
    return 'current' if value == BRIDGE_MARKER else 'unsupported'


def _activity(row):
    if 'constructor_activity' not in row:
        return 'absent'
    value = row['constructor_activity']
    if type(value) is dict and set(value) == {'version', 'attempt_possible'} and type(value['version']) is int \
            and value['version'] == 1 and value['attempt_possible'] is True:
        return 'valid'
    return 'malformed'


def _status(row):
    value = row.get('status')
    return value if type(value) is str and 1 <= len(value) <= 32 and value.isascii() and value.isalpha() else None


def _kernel_ref(kernel, reasons):
    """A recorded kernel identity, only when it is a bounded identity text (never an arbitrary long value)."""
    kid, lang = SR._kernel_pair(kernel)
    if kid is None:
        return None
    if not J._KERNEL.match(kid) or (lang is not None and not J._KERNEL.match(lang)):
        reasons.add('kernel_identity_malformed')
        return None
    return {'id': kid, 'lang': lang}


def _history(state_raw, trace_raw, reasons):
    """Constructor history retained in state.json/trace.jsonl, using the native evidence rules."""
    out = {'status': None, 'marker': None, 'activity': None, 'evidence': None, 'kernel': None,
           'trace_rows': 0, 'trace_constructor_rows': 0, 'trace_unreadable_rows': 0, 'trace_kernels': []}
    if state_raw is not None:
        try:
            row = _strict_json(state_raw)
            out.update(status=_status(row), marker=_marker(row), activity=_activity(row))
            out['kernel'] = _kernel_ref(row.get('kernel'), reasons)
            try:
                out['evidence'] = SR._constructor_history_evidence(row, state=True) or 'none'
            except (ValueError, TypeError):
                out['evidence'] = 'malformed'
                reasons.add('history_breadcrumb_malformed')
        except (ValueError, TypeError, RecursionError, UnicodeError):
            out['status'] = None
            reasons.add('state_unreadable')
    if trace_raw:
        lines = trace_raw.split(b'\n', TRACE_ROWS)
        if lines and lines[-1] == b'':
            lines.pop()
        if len(lines) > TRACE_ROWS:
            reasons.add('trace_unreadable')
            lines = lines[:TRACE_ROWS]
        kernels = set()
        for line in lines:
            out['trace_rows'] += 1
            try:
                if len(line) > TRACE_ROW_BYTES:
                    raise ValueError('row bound')
                row = _strict_json(line)
                if SR._constructor_history_evidence(row) == 'work':
                    out['trace_constructor_rows'] += 1
                if row.get('kind') not in SR.RECEIPT_ROW_KINDS:
                    ref = _kernel_ref(row.get('kernel'), reasons)
                    if ref is not None and len(kernels) < MAX_TRACE_KERNELS:
                        kernels.add((ref['id'], ref['lang'] or ''))
            except (ValueError, TypeError, RecursionError, UnicodeError):
                out['trace_unreadable_rows'] += 1
        out['trace_kernels'] = [{'id': kid, 'lang': lang or None} for kid, lang in sorted(kernels)]
        if out['trace_unreadable_rows']:
            reasons.add('trace_unreadable')
    return out


def _mode(meta_raw, config, pins, reasons):
    out = {'selected': None, 'selected_limits': None, 'config': None, 'journal': None, 'consistent': None}
    if meta_raw is None:
        reasons.add('meta_absent')
    else:
        try:
            meta = _strict_json(meta_raw)
            options = meta.get('options')
            if type(options) is not dict:
                raise ValueError('options')
            policy = SR.validate_constructor_options(options)
            out.update(selected=policy['mode'], selected_limits=policy['limits'] if policy['mode'] != 'off' else None)
        except (ValueError, TypeError, RecursionError, UnicodeError, S.SymblicError):
            reasons.add('meta_invalid')
    if config is not None:
        out['config'] = config['mode']
    if pins is not None:
        out['journal'] = pins['mode']
    known = [value for value in (out['selected'], out['config'], out['journal']) if value is not None]
    if out['selected'] is None:
        reasons.add('mode_unknown')
    if known:
        out['consistent'] = len(set(known)) == 1 and (out['selected'] is None or out['config'] is None
                                                      or out['selected_limits'] == config['limits'])
        if not out['consistent']:
            reasons.add('mode_differs')
    return out


def _kernel(current, kernel_raw, kernel_seen, pins, history, reasons):
    out = {'current': current, 'recorded': [], 'compatibility': 'unknown'}
    unreadable = False
    if kernel_raw is not None:
        try:
            record = _strict_json(kernel_raw)
            ref = _kernel_ref(record, reasons)
            if type(record.get('version')) is not int or record['version'] != SR.KERNEL_RECORD_VERSION or ref is None:
                raise ValueError('kernel record')
            out['recorded'].append({'source': SR.KERNEL_RECORD, **ref})
        except (ValueError, TypeError, RecursionError, UnicodeError):
            unreadable = True
    elif kernel_seen['kind'] != 'absent':
        unreadable = True
    if unreadable:
        reasons.add('kernel_record_unreadable')
        out['recorded'].append({'source': SR.KERNEL_RECORD, 'id': None, 'lang': None})
    if pins is not None:
        out['recorded'].append({'source': 'journal_pins', 'id': pins['kernel_id'], 'lang': None})
    if history['kernel'] is not None:
        out['recorded'].append({'source': 'state.json', **history['kernel']})
    for row in history['trace_kernels']:
        out['recorded'].append({'source': 'trace.jsonl', **row})
    if current is None:
        reasons.add('current_kernel_unavailable')
        return out
    if unreadable:
        out['compatibility'] = 'unreadable'
    elif any(row['id'] != current['id'] or row['lang'] not in (None, current['lang']) for row in out['recorded']):
        out['compatibility'] = 'changed'
        reasons.add('kernel_changed')
    elif out['recorded']:
        out['compatibility'] = 'same'
    else:
        reasons.add('kernel_unrecorded')
    return out


def _journal(raw, seen, reasons):
    """Parse the exact snapshot without the lock (a lock would block or be created by a writer)."""
    out = {'readable': False, 'problem': None, 'complete_rows_only': False}
    if raw is None:
        if seen['kind'] != 'absent':
            out['problem'] = seen.get('problem', 'unreadable')
            reasons.add('journal_' + out['problem'])
        return out, None
    if not raw:
        out['problem'] = 'empty'
        reasons.add('journal_empty')
        return out, None
    try:
        state = J._validate(raw)
    except J.JournalError as exc:
        out['problem'] = exc.code
        reasons.add('journal_' + exc.code)
        if exc.code != 'torn_tail':
            return out, None
        details = exc.details
        out['torn'] = {key: details.get(key) for key in ('complete_bytes', 'torn_bytes', 'torn_sha256')}
        try:                           # the whole rows a repair would keep
            state = J._validate(raw[:details['complete_bytes']])
            out['complete_rows_only'] = True
        except (J.JournalError, ValueError, RecursionError, KeyError, TypeError):
            reasons.add('journal_prefix_damaged')
            return out, None
    except (ValueError, RecursionError):
        out['problem'] = 'malformed'
        reasons.add('journal_malformed')
        return out, None
    if state.pins is None:
        out['problem'] = out['problem'] or 'no_open_row'
        reasons.add('journal_no_open_row')
        return out, state
    out['readable'] = out['problem'] is None
    attempts, phases = [], {}
    for aid in sorted(state.attempts):
        entry = state.attempts[aid]
        phase = J._phase(entry)
        phases[phase] = phases.get(phase, 0) + 1
        intent, row = entry['intent'], entry['outcome']
        item = {'attempt': aid, 'phase': phase, 'occurrence': intent['request']['occurrence'],
                'key': intent['key'], 'contract_sha256': intent['request']['contract_sha256'],
                'continues': intent['continues'], 'reserved_ms': intent['request']['limits']['milliseconds'],
                'disposition': None, 'dispatched': None, 'selected_sha256': None}
        if row is not None:
            item.update(disposition=row['outcome']['disposition'], dispatched=row['outcome']['dispatched'],
                        selected_sha256=row['selected_sha256'])
        if phase in ('open', 'blocked'):
            item['owner_appears_live'] = J.owner_live(intent['owner'])   # diagnostic only; grants nothing
            if item['owner_appears_live']:
                reasons.add('owner_appears_live')
        attempts.append(item)
    allowance = state.pins['allowance']
    charged = state.charged_view()
    out.update(events=state.seq, bytes=state.size, last_row_sha256=state.last, pins=dict(state.pins),
               pins_sha256=J._sha('pins', state.pins), allowance=dict(allowance), charged=charged,
               remaining={key: allowance[key] - charged[key] for key in allowance},
               phases=dict(sorted(phases.items())), attempts=attempts,
               repairs=state.repairs, quarantined=sorted(state.quarantined))
    if any(item['phase'] == 'open' for item in attempts):
        reasons.add('attempt_uncertain')
    if any(item['phase'] == 'blocked' for item in attempts):
        reasons.add('attempt_blocked')
    return out, state


def _slots(folder, state, reasons):
    out, recorded = [], state.quarantined if state is not None else set()
    for slot, name in enumerate(SLOTS):
        seen, raw = _read(folder, name, J.MAX_ROW_BYTES)
        seen = {'slot': slot, **seen, 'recorded': name in recorded}
        if seen['kind'] == 'absent':
            if seen['recorded']:
                reasons.add('quarantine_recorded_missing')
            if seen.get('problem') == 'vanished':
                reasons.add('snapshot_changed')
            seen.pop('problem', None)
        elif raw is None:
            reasons.add('quarantine_unsafe')
        elif not seen['recorded']:
            reasons.add('quarantine_unrecorded' if raw else 'quarantine_empty_reservation')
        out.append(seen)
    if all(item['kind'] != 'absent' for item in out):
        reasons.add('quarantine_full')
    return out


def _gate(folder, mode):
    """The native missing-record gate's verdict for the folder's selected mode (it reads only)."""
    if mode is None:
        return None
    try:
        present = SR.constructor_records_gate(folder, mode=mode)
    except S.SymblicError as exc:
        return {'mode': mode, 'verdict': 'refused', 'kind': getattr(exc, 'kind', None), 'message': str(exc)[:256]}
    except (OSError, ValueError, RecursionError) as exc:
        return {'mode': mode, 'verdict': 'error', 'kind': type(exc).__name__, 'message': str(exc)[:256]}
    return {'mode': mode, 'verdict': 'records_present' if present else 'no_records'}


def _current_kernel():
    try:
        kernel = S.kernel_id()
        return {'id': kernel['id'], 'lang': kernel.get('lang')}
    except Exception:                  # identity is evidence here, not a precondition
        return None


def _classify(reasons, records, history, mode):
    has = reasons.__contains__
    config_state = records['config']['kind']
    journal_state = records['journal']['kind']
    pair = [config_state != 'absent', journal_state != 'absent']
    damaged = any(has(code) for code in ('config_invalid', 'config_unsafe', 'config_oversized', 'config_unreadable',
                                         'journal_empty', 'journal_unsafe', 'journal_oversized',
                                         'journal_no_open_row', 'journal_prefix_damaged',
                                         'journal_pins_differ', 'journal_evidence_invalid', 'quarantine_unsafe',
                                         'quarantine_recorded_missing', 'lock_unsafe', 'mode_differs',
                                         'records_with_mode_off', 'source_differs', 'inputs_differ')) \
        or any(code.startswith('journal_') and code[8:] in J.DAMAGE and code != 'journal_torn_tail' for code in reasons)
    if has('snapshot_changed'):
        return 'snapshot_inconsistent'
    if damaged:
        return 'records_damaged'
    if has('journal_torn_tail'):
        return 'journal_torn'
    if has('quarantine_unrecorded') or has('quarantine_empty_reservation'):
        return 'repair_unfinished'
    if has('attempt_blocked'):
        return 'attempt_blocked'
    if has('attempt_uncertain'):
        return 'attempt_uncertain'
    if any(pair) and not all(pair):
        return 'records_incomplete'
    if all(pair):
        return 'attempts_settled' if records['journal_summary'].get('attempts') else 'no_attempt_recorded'
    leftovers = records['lock']['kind'] != 'absent' or any(s['kind'] != 'absent' for s in records['quarantine'])
    if leftovers or history['retained']:
        return 'history_unknowable'
    return 'no_constructor_history'


def _retained(history, mode_selected, reasons):
    """Why retained history makes a missing-record folder unknowable (native rules, strict marker)."""
    found = []
    if history['activity'] in ('valid', 'malformed'):
        found.append('history_activity_' + history['activity'])
    if history['evidence'] == 'work' or history['trace_constructor_rows']:
        found.append('history_constructor_work')
    if history['evidence'] in ('ambiguous', 'malformed'):
        found.append('history_ambiguous')
    unfinished = history['status'] != 'done'
    state_present = history['marker'] is not None
    if state_present and unfinished and history['marker'] != 'current' and mode_selected != 'off':
        found.append('history_marker_' + history['marker'])   # legacy, malformed or future: no checkpoint assertion
    unreadable = 'state_unreadable' in reasons or 'trace_unreadable' in reasons
    if unreadable and mode_selected != 'off':
        found.append('history_unreadable')
    if state_present and unfinished and mode_selected is None and not unreadable:
        found.append('history_mode_unknown')
    return sorted(set(found))


NEXT_STEPS = {
    'folder_absent': [('agent', 'check_path', 'Check the run folder path; nothing was found there.')],
    'folder_unsafe': [('owner', 'review_folder', 'The path is not a plain directory; nothing inside was read.')],
    'inspection_failed': [('none', 'do_not_act', 'The inspector stopped unexpectedly; this is no evidence either way.')],
    'snapshot_inconsistent': [
        ('agent', 'inspect_again', 'A writer changed the folder during the read. Inspect again after it stops; '
                                   'do not act on this snapshot.')],
    'records_damaged': [
        ('owner', 'review_records', 'Records are damaged or contradictory. Resume and export refuse until the '
                                    'owner reviews the folder; do not delete records to obtain a fresh history.'),
        ('agent', 'new_run_new_folder', 'Start a new run in a NEW folder (it asks everything again).')],
    'journal_torn': [
        ('owner', 'repair_torn_tail', 'The journal ends inside a row. The owner may confirm the reported '
                                      'journal.torn.torn_sha256 with symblic.constructor.journal.repair_torn_tail; '
                                      'it keeps the bytes in a quarantine slot before cutting.'),
        ('agent', 'new_run_new_folder', 'Or start a new run in a NEW folder.')],
    'repair_unfinished': [
        ('owner', 'finish_repair', 'A quarantine slot holds bytes no repair row records (an interrupted repair). '
                                   'The owner reruns repair_torn_tail with that slot\'s sha256 to write the audit '
                                   'row; export refuses meanwhile. An empty slot is a reservation and needs review.')],
    'attempt_blocked': [
        ('owner', 'review_cleanup', 'A dispatched worker was not confirmed reaped. The owner checks the host; only '
                                    'the owner may record an abandonment (reconcile).')],
    'attempt_uncertain': [
        ('none', 'do_not_retry', 'An announced attempt has no recorded end: it may have run. This report does not '
                                 'authorize a retry; resume refuses it.'),
        ('owner', 'reconcile', 'Only the owner may record it abandoned (symblic.constructor.journal.reconcile); '
                               'that records a decision, not proof that nothing ran.'),
        ('agent', 'new_run_new_folder', 'Or start a new run in a NEW folder (it asks everything again).')],
    'records_incomplete': [
        ('owner', 'explicit_recovery', 'Only one of the constructor configuration and journal exists. Resume '
                                       'refuses; the owner decides recovery.'),
        ('agent', 'new_run_new_folder', 'Or start a new run in a NEW folder.')],
    'history_unknowable': [
        ('owner', 'explicit_recovery', 'Constructor records are missing but retained history or journal byproducts '
                                       'show possible earlier activity, or cannot rule it out. Whether an attempt '
                                       'ran is unknowable from this folder.'),
        ('agent', 'new_run_new_folder', 'Start a new run in a NEW folder; do not delete evidence to resume here.')],
    'attempts_settled': [
        ('agent', 'resume_exact_command', 'Every recorded attempt has an end. Repeating the exact original run '
                                          'command (same source, inputs and options) reuses recorded outcomes.'),
        ('agent', 'replay', 'tools/symblic replay RUN_FOLDER --agent-json reruns from records with no model or '
                            'solver.')],
    'no_attempt_recorded': [
        ('agent', 'resume_exact_command', 'Records exist with no announced attempt. Repeating the exact original run '
                                          'command continues under its recorded policy.')],
    'no_constructor_history': [
        ('agent', 'run_or_resume', 'No constructor records, byproducts or retained constructor activity were '
                                   'found. This is absence of evidence, not proof: deleting every artifact would '
                                   'look the same.')],
}
KERNEL_STEP = ('agent', 'same_deployment', 'Recorded kernel identity differs from or cannot be matched to this '
                                           'deployment; resume refuses here. Continue on the recording deployment, '
                                           'or start a new run in a NEW folder.')


def _steps(classification, kernel):
    steps = list(NEXT_STEPS[classification])
    if kernel is not None and kernel['compatibility'] in ('changed', 'unreadable') \
            and classification in ('attempts_settled', 'no_attempt_recorded', 'no_constructor_history'):
        steps.insert(0, KERNEL_STEP)
    return [{'authority': who, 'action': action, 'note': note} for who, action, note in steps]


def inspect(folder, *, current_kernel=None):
    """The report for `folder` (see the module docstring). `current_kernel` overrides kernel_id() for tests."""
    folder = os.path.abspath(folder)
    report = {'schema': SCHEMA, 'version': VERSION, 'folder': folder, 'classification': None, 'reasons': [],
              'authorizes_retry': False, 'scope': SCOPE}
    info = _lstat(folder)
    if info is None or not stat.S_ISDIR(info.st_mode):
        kind = _kind(info)
        report.update(classification='folder_absent' if kind == 'absent' else 'folder_unsafe',
                      reasons=['folder_' + kind], next_steps=_steps('folder_absent' if kind == 'absent'
                                                                    else 'folder_unsafe', None))
        return report
    names = [name for name, _limit in RECORD_FILES.values()] + list(PRESENCE_ONLY.values()) + list(SLOTS)
    before = {name: _signature(_lstat(os.path.join(folder, name))) for name in names}
    before['.'] = _signature(info)
    reasons = set()
    records, raw = {}, {}
    for key, (name, limit) in RECORD_FILES.items():
        records[key], raw[key] = _read(folder, name, limit)
        if records[key].get('problem') == 'vanished':
            reasons.add('snapshot_changed')
    for key, name in PRESENCE_ONLY.items():
        records[key] = {'name': name, 'kind': _kind(_lstat(os.path.join(folder, name)))}
    if records['lock']['kind'] not in ('absent', 'regular'):
        reasons.add('lock_unsafe')
    config = None
    if raw['config'] is not None:
        try:
            config = R.parse_config(raw['config'].decode('ascii'))
            records['config'].update(mode=config['mode'], limits=config['limits'],
                                     configuration_sha256=R.config_hash(config),
                                     implementation_sha256=R.implementation_hash(config))
        except (R.RecordsError, UnicodeError):
            reasons.add('config_invalid')
    elif records['config']['kind'] != 'absent':
        reasons.add('config_' + records['config'].get('problem', 'unreadable'))
    journal, state = _journal(raw['journal'], records['journal'], reasons)
    pins = state.pins if state is not None else None
    if state is not None and pins is not None and config is not None:
        try:
            R.bind_journal(state, config, source_sha256=pins['source_sha256'], input_sha256=pins['input_sha256'],
                           kernel_id=pins['kernel_id'])
        except R.RecordsError as exc:
            reasons.add('journal_pins_differ' if exc.code == 'pins' else 'journal_evidence_invalid')
    if pins is not None:
        bindings = {'source': None, 'inputs': None}
        if raw['program'] is not None:
            bindings['source'] = hashlib.sha256(raw['program']).hexdigest() == pins['source_sha256']
        if raw['meta'] is not None:
            try:
                meta = _strict_json(raw['meta'])
                if 'inputs' in meta:
                    bindings['inputs'] = E.digest(meta['inputs']) == pins['input_sha256']
            except (ValueError, TypeError, RecursionError, UnicodeError):
                pass
        for name, match in bindings.items():
            if match is False:
                reasons.add(name + '_differs')
        journal['bindings'] = bindings
    history = _history(raw['state'], raw['trace'], reasons)
    for key in ('state', 'trace', 'meta', 'program', 'kernel_record'):
        if records[key].get('problem') in ('unsafe', 'oversized', 'unreadable'):
            reasons.add(key + '_unreadable' if key in ('state', 'trace') else key + '_' + records[key]['problem'])
    mode = _mode(raw['meta'], config, pins, reasons)
    if mode['selected'] == 'off' and (config is not None or records['journal']['kind'] != 'absent'):
        reasons.add('records_with_mode_off')
    history['retained'] = _retained(history, mode['selected'], reasons)
    pair = records['config']['kind'] != 'absent', records['journal']['kind'] != 'absent'
    if not all(pair):                  # with both primary records present, the journal is the authority
        reasons.update(history['retained'])
    kernel = _kernel(current_kernel if current_kernel is not None else _current_kernel(),
                     raw['kernel_record'], records['kernel_record'], pins, history, reasons)
    records['quarantine'] = _slots(folder, state, reasons)
    gate = _gate(folder, mode['selected'])
    after = {name: _signature(_lstat(os.path.join(folder, name))) for name in names}
    after['.'] = _signature(_lstat(folder))
    changed = sorted(name for name in before if before[name] != after[name])
    if changed:
        reasons.add('snapshot_changed')
    if records['lock']['kind'] != 'absent' and not all(pair):
        reasons.add('lock_leftover')
    records['journal_summary'] = {'attempts': len(journal.get('attempts', []))}
    classification = _classify(reasons, records, history, mode)
    records.pop('journal_summary')
    report.update(classification=classification, reasons=sorted(reasons),
                  snapshot={'consistent': not changed and 'snapshot_changed' not in reasons, 'changed': changed},
                  mode=mode, kernel=kernel, records=records, journal=journal, history=history, native_gate=gate,
                  next_steps=_steps(classification, kernel))
    return report


def dumps(report):
    return json.dumps(report, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def main(argv):
    parser = argparse.ArgumentParser(prog='symblic constructor', description='Read-only constructor run evidence.')
    sub = parser.add_subparsers(dest='cmd', required=True)
    one = sub.add_parser('inspect', help='classify one run folder from fixed bounded paths; writes nothing')
    one.add_argument('folder', metavar='RUN_FOLDER')
    one.add_argument('--agent-json', action='store_true', help='one compact JSON object on stdout')
    args = parser.parse_args(argv)
    try:
        report = inspect(args.folder)
    except Exception as exc:           # still one machine-readable object; never a partial report
        report = {'schema': SCHEMA, 'version': VERSION, 'folder': os.path.abspath(args.folder),
                  'classification': 'inspection_failed', 'reasons': ['internal_' + type(exc).__name__],
                  'authorizes_retry': False, 'scope': SCOPE, 'next_steps': _steps('inspection_failed', None)}
    if args.agent_json:
        print(dumps(report))
    else:
        print(f'{report["classification"]}: {", ".join(report["reasons"]) or "no reasons"}')
        for step in report['next_steps']:
            print(f'  [{step["authority"]}] {step["action"]}: {step["note"]}')
        print('  ' + SCOPE)
    return 1 if report['classification'] in ('folder_absent', 'folder_unsafe', 'inspection_failed') else 0


if __name__ == '__main__':          # pragma: no cover - tools/symblic is the usual entry point
    sys.exit(main(sys.argv[1:]))
