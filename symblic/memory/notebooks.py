"""Notebooks: durable, revisioned memory for Symblic claims.

What it is for
    A notebook keeps a set of claims (the claim records of symblic.kernel.epistemic) between runs, so that a
    later task can be given exactly the support it depends on and nothing else. You can add, revise and
    withdraw claims, record a disagreement between claims and resolve it, and attach a canonical value to a
    claim that only carries the value's hash. context() returns a bounded context pack for a selected set of
    claims and their complete dependency closure; it refuses when any of that support is withdrawn,
    contested, stale or has incomplete lineage.

    Public functions: create(path, ...), view(path), change(path, command), context(path, ...).
    Errors are MemoryError with a stable .code (for example 'conflict', 'idempotency_conflict', 'corrupt').

How it stores data
    One directory per notebook (mode 0700, owned by the current user) with one canonical notebook.json that
    holds an append-only, hash-chained event list, plus a lock file. Every change is a compare-and-swap on the
    current head hash (expected_head) and carries an operation ID: repeating the same operation returns the
    recorded result instead of applying it twice. flock serializes processes; an atomic replace commits a
    complete, bounded document. If the directory fsync after a replace fails, the outcome is reported as
    uncertain: retry the same operation ID to learn whether it was applied.

Trust
    The caller chooses the directory and decides who may call these functions; there is no authentication
    here. Only create(trusted_claims=...) can import claims that already carry origins and check receipts
    (for example the claims a finished run recorded). Claims added later with change() are always recorded
    with origin 'owner_premise' (a premise stated by the notebook's user, the vocabulary of
    symblic.kernel.epistemic) and can never claim a check receipt or a truth status. The hashes are integrity
    references, not signatures: whoever can write the files can rewrite them. Every snapshot says
    'empirical_truth': 'not_established'.

Depends on: the Python standard library (POSIX: fcntl, file modes) and symblic.kernel.epistemic.
Used by: the host's notebook API (integration/host/symblic_memory_api.py), which imports claims from finished
runs; nothing in this package starts a worker, calls a model or touches the network. Status: prototype; tested
by tests/memory with temporary directories only.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from symblic.kernel import epistemic as EP

VERSION = 1
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 2048
MAX_HISTORY = 4096
MAX_CLAIMS = EP.MAX_CLAIMS
MAX_NODES = 500000
MAX_TOTAL_ROOTS = 32768
STORE_FILE = 'notebook.json'
LOCK_FILE = 'notebook.lock'
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


class MemoryError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}

    def as_dict(self):
        return {'code': self.code, 'message': str(self), 'details': self.details}


def _fail(code, message, details=None):
    raise MemoryError(code, message, details)


def _json(value):
    stack = [(iter((value,)), None)]; active = set(); nodes = characters = 0
    while stack:
        try:
            item = next(stack[-1][0])
        except StopIteration:
            _, ident = stack.pop()
            if ident is not None:
                active.remove(ident)
            continue
        nodes += 1
        if nodes > MAX_NODES or len(stack) > 40:
            _fail('limit', 'Notebook JSON exceeds its structure limit.')
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active or len(item) > MAX_NODES:
                _fail('limit', 'Cyclic or oversized notebook JSON.')
            if kind is dict:
                for key in item:
                    if type(key) is not str or len(key) > EP.MAX_BYTES:
                        _fail('json', 'Object keys must be bounded text.')
                    characters += len(key)
                children = iter(item.values())
            else:
                children = iter(item)
            active.add(id(item)); stack.append((children, id(item)))
        elif kind is str:
            characters += len(item)
        elif kind is int:
            if item.bit_length() > 4096:
                _fail('limit', 'Integer exceeds 4096 bits.')
        elif kind not in (bool, type(None)):
            _fail('json', 'Only exact JSON values are supported; use canonical values for rationals.')
        if characters > MAX_FILE_BYTES:
            _fail('limit', 'Notebook exceeds the file bound.')
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError):
        _fail('json', 'Invalid exact JSON encoding.')
    if len(raw) > MAX_FILE_BYTES:
        _fail('limit', 'Notebook exceeds the 8 MiB file bound.')
    return raw


def _hash(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _exact_keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        _fail('schema', 'Missing or unknown fields.', {'required': list(required), 'optional': list(optional)})


def _ident(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail('id', 'IDs must be 1..160 ASCII identifier characters.')
    return value


def _text(value, maximum, label):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        _fail('schema', f'{label} must be nonempty text of at most {maximum} characters.')
    _json(value)
    return value


def _ep(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except EP.EpistemicError as error:
        _fail('epistemic_' + error.code, str(error), error.details)


def _directory(path, create=False):
    path = Path(path)
    if create:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError:
            _fail('private_directory', 'The notebook directory could not be created.')
    try:
        info = path.lstat()
    except FileNotFoundError:
        _fail('not_found', 'Notebook directory does not exist.')
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        _fail('private_directory', 'Notebook directory must be owned by this user and private (0700).')
    return path


def _private_file(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or info.st_nlink != 1):
        _fail('private_file', 'Notebook files must be regular private files owned by this user.')


@contextmanager
def _locked(path, *, create=False, shared=False):
    path = _directory(path, create=create)
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0)
    try:
        fd = os.open(path / LOCK_FILE, flags, 0o600)
    except OSError:
        _fail('lock_unavailable', 'Notebook lock is unavailable.')
    try:
        _private_file(os.fstat(fd))
        operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        until = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(fd, operation | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= until:
                    _fail('busy', 'Notebook is busy; retry the same operation ID.')
                time.sleep(0.01)
        yield path
    finally:
        os.close(fd)


def _read(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                _fail('corrupt', 'Duplicate JSON key in notebook.')
            out[key] = value
        return out
    try:
        fd = os.open(path / STORE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno()); _private_file(info)
            if info.st_size > MAX_FILE_BYTES:
                _fail('limit', 'Notebook file exceeds 8 MiB.')
            raw = handle.read(MAX_FILE_BYTES + 1)
        data = json.loads(raw, object_pairs_hook=pairs)
        if _json(data) != raw:
            _fail('corrupt', 'Notebook file is not canonical exact JSON.')
        return data
    except FileNotFoundError:
        _fail('not_found', 'Notebook document does not exist.')
    except (OSError, ValueError, RecursionError) as error:
        if isinstance(error, MemoryError):
            raise
        _fail('corrupt', 'Notebook cannot be read; existing data was not replaced.')


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write(path, ledger):
    raw = _json(ledger)
    try:
        descriptor, temporary = tempfile.mkstemp(prefix='.notebook-pending-', dir=path)
    except OSError:
        _fail('write_failed', 'Notebook temporary file could not be created; prior data was not replaced.')
    replaced = False
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path / STORE_FILE); replaced = True
        _sync_directory(path)
    except OSError:
        if replaced:
            _fail('durability_uncertain', 'Replacement occurred but directory sync failed; reread or retry the same operation ID.',
                  {'operation_head': ledger['head']})
        _fail('write_failed', 'Notebook was not replaced; retry the same operation ID.')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _ids(ids, *, allow_empty=True):
    if type(ids) is not list or len(ids) > MAX_CLAIMS or (not allow_empty and not ids):
        _fail('selection', 'Expected a bounded list of claim IDs.')
    for ident in ids:
        _ident(ident)
    if len(set(ids)) != len(ids):
        _fail('duplicate', 'Claim IDs must not repeat.')
    return ids


def _closure(rows, selected, *, allow_missing=False):
    found = set(); pending = list(selected)
    while pending:
        ident = pending.pop()
        if ident in found:
            continue
        if ident not in rows:
            if allow_missing:
                continue
            _fail('missing', 'A selected claim or dependency is unavailable.', {'id': ident})
        found.add(ident)
        pending.extend(ref['id'] for ref in rows[ident]['dependencies'])
    return sorted(found)


def _references(rows, ids):
    _ids(ids)
    if len(ids) > EP.MAX_REFS:
        _fail('limit', 'At most 64 direct dependencies are supported.')
    if any(ident not in rows for ident in ids):
        _fail('missing', 'Dependency claim does not exist.')
    return sorted((_ep(EP.reference, rows[ident]) for ident in ids), key=lambda ref: ref['id'])


def _attach(state, ident, value):
    row = state['current'].get(_ident(ident))
    if row is None:
        _fail('missing', 'Claim does not exist.')
    content = row['content']
    expected = content.get('value_sha256') if type(content) is dict else None
    if type(expected) is not str or not _SHA.fullmatch(expected):
        _fail('value_reference', 'This claim has full content rather than a canonical value hash reference.')
    if _ep(EP.digest, value) != expected:
        _fail('value_mismatch', 'Canonical value does not match the exact recorded value hash.')
    state['values'][row['sha256']] = {'ref': _ep(EP.reference, row), 'value_sha256': expected, 'value': copy.deepcopy(value)}


def _append_claim(state, claim):
    row = _ep(EP.validate_claim, claim)
    if len(state['history']) >= MAX_HISTORY:
        _fail('limit', 'Retained claim history is full; no revisions were removed.')
    state['history'].append(row); state['current'][row['id']] = row
    if len(state['current']) > MAX_CLAIMS:
        _fail('limit', 'Notebook has too many current claims.')


def _apply(state, command, sequence):
    action = command.get('action')
    base = ('operation_id', 'expected_head', 'action')
    if action in ('add', 'revise'):
        _exact_keys(command, (*base, 'claim_id', 'content'), ('depends_on',))
        ident = _ident(command['claim_id']); old = state['current'].get(ident)
        if (action == 'add' and old is not None) or (action == 'revise' and old is None):
            _fail('exists' if old else 'missing', 'Use add for a new claim and revise for an existing claim.')
        row = _ep(EP.make_claim, ident, command['content'], origin='owner_premise',
                  revision=old['revision'] + 1 if old else 1,
                  dependencies=_references(state['current'], command.get('depends_on', [])), checks=[], status='unknown')
        _append_claim(state, row)
    elif action == 'withdraw':
        _exact_keys(command, (*base, 'claim_id'))
        row = state['current'].get(_ident(command['claim_id']))
        if row is None:
            _fail('missing', 'Claim does not exist.')
        _append_claim(state, _ep(EP.make_claim, row['id'], row['content'], origin=row['origin'],
            revision=row['revision'] + 1, dependencies=row['dependencies'], checks=row['checks'],
            status=row['status'], withdrawn=True))
    elif action == 'disagree':
        _exact_keys(command, (*base, 'disagreement_id', 'claim_ids'))
        ident = _ident(command['disagreement_id'])
        if ident in state['disagreements']:
            _fail('exists', 'Disagreement IDs are retained and cannot be reused.')
        refs = _references(state['current'], command['claim_ids'])
        if len(refs) < 2 or any(state['current'][ref['id']]['withdrawn'] for ref in refs):
            _fail('disagreement', 'A disagreement needs at least two current, nonwithdrawn claims.')
        state['disagreements'][ident] = {'id': ident, 'claims': refs, 'opened_event': sequence,
                                       'closed_event': None, 'reason': None}
    elif action == 'resolve':
        _exact_keys(command, (*base, 'disagreement_id'), ('reason',))
        ident = _ident(command['disagreement_id']); row = state['disagreements'].get(ident)
        if row is None or row['closed_event'] is not None:
            _fail('disagreement', 'Only an active disagreement can be resolved.')
        reason = command.get('reason', 'owner_marked_resolved')
        row.update(closed_event=sequence, reason=_text(reason, 4096, 'Resolution reason'))
    elif action == 'attach_value':
        _exact_keys(command, (*base, 'claim_id', 'value'))
        _attach(state, command['claim_id'], command['value'])
    else:
        _fail('action', 'Unknown notebook change action.')
    # A historical disagreement never silently moves to a different revision.
    for row in state['disagreements'].values():
        if row['closed_event'] is not None:
            continue
        if any(state['current'][ref['id']]['withdrawn'] or EP.reference(state['current'][ref['id']]) != ref
               for ref in row['claims']):
            row.update(closed_event=sequence, reason='claim_revision_or_withdrawal')


def _assess(state):
    current = list(state['current'].values())
    # Bound aggregate root expansion before EP produces its full assessment rows.
    rows, order = _ep(EP._index, current)
    roots = {}; total = 0
    for ident in order:
        row = rows[ident]; held = set()
        for ref in row['dependencies']:
            held.update(roots.get(ref['id'], ()))
        if row['origin'] != 'derived':
            held.add(ident)
        total += len(held)
        if total > MAX_TOTAL_ROOTS:
            _fail('limit', 'Aggregate conditional-root expansion exceeds 32768 references.')
        roots[ident] = held
    active = [{'id': row['id'], 'claims': row['claims']} for row in state['disagreements'].values()
              if row['closed_event'] is None]
    return _ep(EP.evaluate, current, disagreements=active)


def _replay(ledger):
    _exact_keys(ledger, ('version', 'title', 'source', 'events', 'head'))
    if type(ledger['version']) is not int or ledger['version'] != VERSION:
        _fail('version', 'Unknown notebook version.')
    events = ledger['events']
    if type(events) is not list or not 1 <= len(events) <= MAX_EVENTS:
        _fail('limit', 'Notebook event count is invalid.')
    state = {'current': {}, 'history': [], 'values': {}, 'disagreements': {}, 'operations': {}}
    previous = None
    for sequence, event in enumerate(events, 1):
        _exact_keys(event, ('sequence', 'operation_id', 'request_sha256', 'previous_head', 'at_ms', 'payload', 'sha256'))
        if (type(event['sequence']) is not int or event['sequence'] != sequence or event['previous_head'] != previous
                or type(event['at_ms']) is not int or not 0 <= event['at_ms'] <= 2**53 - 1):
            _fail('corrupt', 'Notebook sequence, time or previous head is invalid.')
        ident = _ident(event['operation_id'])
        if ident in state['operations']:
            _fail('corrupt', 'Repeated operation ID in notebook.')
        if _hash({key: value for key, value in event.items() if key != 'sha256'}) != event['sha256']:
            _fail('corrupt', 'Notebook event hash differs.')
        payload = event['payload']
        if type(payload) is not dict:
            _fail('corrupt', 'Notebook event payload must be an object.')
        if _hash(payload) != event['request_sha256']:
            _fail('corrupt', 'Notebook request hash differs.')
        if sequence == 1:
            _exact_keys(payload, ('action', 'title', 'source', 'claims', 'values'))
            if payload['action'] != 'create' or payload['title'] != ledger['title'] or payload['source'] != ledger['source']:
                _fail('corrupt', 'Notebook genesis metadata differs.')
            _text(payload['title'], 256, 'Title')
            if type(payload['claims']) is not list or len(payload['claims']) > MAX_CLAIMS or type(payload['values']) is not dict:
                _fail('corrupt', 'Invalid imported claim/value collection.')
            for claim in payload['claims']:
                row = _ep(EP.validate_claim, claim)
                if row['id'] in state['current']:
                    _fail('duplicate', 'Imported claim IDs repeat.')
                _append_claim(state, row)
            for claim_id, value in payload['values'].items():
                _attach(state, claim_id, value)
        else:
            if payload.get('operation_id') != ident or payload.get('expected_head') != previous:
                _fail('corrupt', 'Stored command does not match its operation/head.')
            _apply(state, payload, sequence)
        state['operations'][ident] = {'request_sha256': event['request_sha256'], 'operation_head': event['sha256']}
        previous = event['sha256']
    if ledger['head'] != previous:
        _fail('corrupt', 'Notebook head differs from its retained history.')
    state['assessments'] = _assess(state)
    return state


def _snapshot(ledger, state):
    current = state['current']; values = {}; availability = {}
    for ident, row in current.items():
        attached = state['values'].get(row['sha256'])
        if attached:
            values[ident] = attached
        hashed = type(row['content']) is dict and 'value_sha256' in row['content']
        availability[ident] = 'attached' if attached else 'hash_only' if hashed else 'full_content'
    return copy.deepcopy({'version': VERSION, 'title': ledger['title'], 'head': ledger['head'],
        'event_count': len(ledger['events']), 'source': ledger['source'],
        'claims': [current[key] for key in sorted(current)], 'history': state['history'],
        'assessments': state['assessments'], 'values': values, 'value_availability': availability,
        'disagreements': {'active': [row for row in state['disagreements'].values() if row['closed_event'] is None],
                          'historical': [row for row in state['disagreements'].values() if row['closed_event'] is not None]},
        'events': [{key: event[key] for key in ('sequence', 'operation_id', 'previous_head', 'at_ms', 'sha256')}
                   | {'action': event['payload']['action']} for event in ledger['events']],
        'empirical_truth': 'not_established'})


def _event(payload, operation_id, previous, sequence):
    body = {'sequence': sequence, 'operation_id': operation_id, 'request_sha256': _hash(payload),
            'previous_head': previous, 'at_ms': time.time_ns() // 1000000, 'payload': copy.deepcopy(payload)}
    return {**body, 'sha256': _hash(body)}


def create(path, *, title, operation_id, trusted_claims=None, selected_ids=None, trusted_values=None, source=None):
    """Import a host-selected closure, preserving origins/receipts; no wire envelope upload."""
    title = _text(title, 256, 'Title'); _ident(operation_id)
    claims = [] if trusted_claims is None else trusted_claims
    if type(claims) is not list or len(claims) > MAX_CLAIMS:
        _fail('limit', 'Trusted host claims must be a bounded list.')
    rows = {}
    for claim in claims:
        row = _ep(EP.validate_claim, claim)
        if row['id'] in rows:
            _fail('duplicate', 'Trusted claim IDs repeat.')
        rows[row['id']] = row
    selected = _ids([] if selected_ids is None else selected_ids)
    if any(ident not in rows for ident in selected):
        _fail('missing', 'Selected imported claim does not exist.')
    closure = _closure(rows, selected, allow_missing=True)
    imported = [rows[ident] for ident in closure]
    values = {} if trusted_values is None else trusted_values
    if type(values) is not dict or set(values) - set(closure):
        _fail('value_reference', 'Trusted values must belong to the imported selection closure.')
    payload = {'action': 'create', 'title': title, 'source': source, 'claims': imported, 'values': values}
    _json(payload)
    with _locked(path, create=True) as directory:
        if os.path.lexists(directory / STORE_FILE):
            ledger = _read(directory); state = _replay(ledger)
            old = state['operations'].get(operation_id)
            if old is None or old['request_sha256'] != _hash(payload):
                _fail('exists', 'Notebook exists with a different creation operation.')
            return {**_snapshot(ledger, state), 'operation_id': operation_id, 'idempotent': True,
                    'operation_head': old['operation_head']}
        event = _event(payload, operation_id, None, 1)
        ledger = {'version': VERSION, 'title': title, 'source': source, 'events': [event], 'head': event['sha256']}
        state = _replay(ledger); _write(directory, ledger)
        return {**_snapshot(ledger, state), 'operation_id': operation_id, 'idempotent': False, 'operation_head': ledger['head']}


def view(path):
    with _locked(path, shared=True) as directory:
        ledger = _read(directory)
        return _snapshot(ledger, _replay(ledger))


def change(path, command):
    """CAS mutation. Reusing an operation ID requires the exact original command."""
    _json(command)
    if type(command) is not dict:
        _fail('schema', 'Notebook command must be an object.')
    operation_id = _ident(command.get('operation_id'))
    expected = command.get('expected_head')
    if type(expected) is not str or not _SHA.fullmatch(expected):
        _fail('head', 'expected_head must be a full current SHA-256 head.')
    request_hash = _hash(command)
    with _locked(path) as directory:
        ledger = _read(directory); state = _replay(ledger)
        old = state['operations'].get(operation_id)
        if old:
            if old['request_sha256'] != request_hash:
                _fail('idempotency_conflict', 'Operation ID was already used for a different command.')
            return {**_snapshot(ledger, state), 'operation_id': operation_id, 'idempotent': True,
                    'operation_head': old['operation_head']}
        if expected != ledger['head']:
            _fail('conflict', 'Notebook changed; inspect its current head before issuing a new operation.',
                  {'expected_head': expected, 'head': ledger['head']})
        if len(ledger['events']) >= MAX_EVENTS:
            _fail('limit', 'Event history is full; no events were removed.')
        _apply(state, command, len(ledger['events']) + 1); state['assessments'] = _assess(state)
        event = _event(command, operation_id, ledger['head'], len(ledger['events']) + 1)
        ledger['events'].append(event); ledger['head'] = event['sha256']
        _write(directory, ledger)
        return {**_snapshot(ledger, state), 'operation_id': operation_id, 'idempotent': False, 'operation_head': ledger['head']}


def context(path, *, selected_ids, budget, prefix='', suffix='', fixed_parts=(), unit='characters', expected_head=None):
    """Fresh selected support with complete recorded closure, scoped origins and value availability."""
    if type(fixed_parts) not in (list, tuple) or any(type(part) is not str for part in fixed_parts):
        _fail('schema', 'Fixed context parts must be a list or tuple of exact strings.')
    with _locked(path, shared=True) as directory:
        ledger = _read(directory); state = _replay(ledger)
        if expected_head is not None and expected_head != ledger['head']:
            _fail('conflict', 'Notebook context head changed.', {'head': ledger['head']})
        selected = _ids(selected_ids)
        closure = _closure(state['current'], selected)
        unavailable = []
        for ident in closure:
            row = state['current'][ident]; assessment = state['assessments'][ident]; content = row['content']
            incomplete = (type(content) is dict and (content.get('kind') == 'bounded_lineage_summary'
                          or content.get('lineage_complete') is False))
            if not assessment['admissible'] or incomplete:
                unavailable.append({'id': ident, 'issues': assessment['issues'], 'incomplete_lineage': incomplete})
        if unavailable:
            _fail('unavailable_support', 'Selected support is withdrawn, contested, refuted, stale or incomplete.',
                  {'claims': unavailable})
        snapshot = _snapshot(ledger, state)
        materialization = {ident: snapshot['value_availability'][ident] for ident in closure}
        values = {ident: snapshot['values'][ident] for ident in closure if ident in snapshot['values']}
        supplement = '\nVALUE AVAILABILITY (a hash is not its underlying value):\n' + _json(materialization).decode()
        if values:
            supplement += '\nVERIFIED CANONICAL VALUE ATTACHMENTS:\n' + _json(values).decode()
        supplement += '\n'
        if type(suffix) is not str:
            _fail('schema', 'Context suffix must be text.')
        # Unselected notebook content is neither rendered nor sent to the next task.
        # Every active conflict touching this closure has already caused refusal.
        manifest = _ep(EP.context_manifest, [state['current'][ident] for ident in closure], required=selected, optional=[],
            budget=budget, prefix=prefix, suffix=supplement + suffix, fixed_parts=list(fixed_parts), unit=unit,
            disagreements=[])
        return {'version': VERSION, 'head': ledger['head'], 'selected_ids': selected, 'closure_ids': closure,
                'claims': [state['current'][ident] for ident in closure],
                'assessments': {ident: state['assessments'][ident] for ident in closure},
                'values': values, 'value_availability': materialization,
                'all_referenced_values_available': all(kind != 'hash_only' for kind in materialization.values()),
                'manifest': manifest, 'empirical_truth': 'not_established'}
