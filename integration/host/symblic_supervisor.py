"""HOST-ONLY: durable workflows over pinned native runs of the original host's runner and scheduler.

Why it is host-only: every step is executed by the host's program runner (`host_runner`, with its planning
history `host_planner`), and every timer or event trigger lives in the host's scheduler (`host_sched`,
`host_triggers`, `host_tools`). None of those modules is part of this repository. The workflow format itself
(steps, state, deadlines, simulation) is pure and is described in docs/reference/SUPERVISOR.md.

This is a finite orchestration format, not a change to Symblic's grammar. No
worker, clock, model, tool or network call starts on import. The host scheduler owns timers;
the host runner owns every native execution, effect journal and admission decision.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

VERSION = 1
MAX_BYTES = 4_000_000
MAX_STEPS = 32
MAX_JOBS = 100
MAX_EVENTS = 1500
MAX_DURATION = 604800
ID = re.compile(r'^[a-zA-Z0-9_-]{1,80}$')
TERMINAL = frozenset({'done', 'failed', 'skipped'})
clock = time.time


class SupervisorError(ValueError):
    pass


class Conflict(SupervisorError):
    pass


def clone(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(raw.encode()) > MAX_BYTES:
            raise SupervisorError('The workflow exceeds the four megabyte limit.')
        return json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise SupervisorError('Expected bounded finite JSON: ' + str(exc)[:180]) from None


def digest(value):
    return hashlib.sha256(json.dumps(clone(value), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise SupervisorError('An identifier must contain 1–80 letters, digits, hyphens or underscores.')
    return value


def root():
    from integration.host import symblic_engine as E
    base = Path(E.root())
    path = base / 'supervisors'
    path.mkdir(mode=0o700, exist_ok=True)
    # E.root may itself have just created the private Symblic parent. Persist
    # both directory entries before a first workflow can submit a native child.
    for directory in (base.parent, base):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return path


@contextmanager
def locked(ident):
    ident = identifier(ident)
    base = root()
    with open(os.open(base / (ident + '.lock'), os.O_RDWR | os.O_CREAT, 0o600), 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield base / (ident + '.json')
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read(path):
    try:
        if path.is_symlink():
            raise SupervisorError('A workflow record cannot be a symbolic link.')
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            raise SupervisorError('The workflow record exceeds its finite limit.')
        row = json.loads(data)
        if type(row) is not dict or row.get('version') != VERSION:
            raise SupervisorError('The workflow record is damaged or has an unsupported version.')
        return row
    except (OSError, ValueError) as exc:
        raise SupervisorError('Cannot read the saved workflow: ' + str(exc)[:180]) from None


def save(path, row):
    raw = json.dumps(clone(row), ensure_ascii=False, sort_keys=True).encode()
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temp.exists():
            temp.unlink()


def event(row, kind, **details):
    row['events'].append({'sequence': row.get('event_sequence', 0) + 1, 'at': clock(), 'kind': kind, **details})
    row['event_sequence'] = row['events'][-1]['sequence']
    row['events'] = row['events'][-MAX_EVENTS:]
    row['revision'] += 1
    row['updated'] = clock()


def number(value, name, lo=0, hi=MAX_DURATION):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise SupervisorError(f'{name} must be a finite number from {lo} to {hi}.')
    return value


def condition(value, ids=None):
    if type(value) is not dict:
        raise SupervisorError('A condition is an explicit state comparison or native step status.')
    if set(value) == {'state', 'equals'}:
        identifier(value['state'])
        clone(value['equals'])
    elif set(value) == {'step', 'status'}:
        identifier(value['step'])
        if ids is not None and value['step'] not in ids:
            raise SupervisorError('The condition names an unknown step.')
        if value['status'] not in ('done', 'failed', 'running'):
            raise SupervisorError('A status condition can test done, failed or running.')
    else:
        raise SupervisorError('Use {state: name, equals: JSON} or {step: id, status: done|failed|running}.')
    return clone(value)


def validate(spec):
    spec = clone(spec)
    if type(spec) is not dict or spec.get('version') != VERSION:
        raise SupervisorError('A workflow needs version: 1.')
    if set(spec) - {'version', 'name', 'steps', 'state', 'max_parallel'}:
        raise SupervisorError('Unknown workflow fields; source text belongs in a native run step.')
    if not isinstance(spec.get('name'), str) or not 1 <= len(spec['name']) <= 120:
        raise SupervisorError('Give this workflow a name of 1–120 characters.')
    steps = spec.get('steps')
    if type(steps) is not list or not 1 <= len(steps) <= MAX_STEPS:
        raise SupervisorError('A workflow needs 1–32 steps.')
    ids = [identifier(s.get('id')) if type(s) is dict else identifier(None) for s in steps]
    if len(set(ids)) != len(ids):
        raise SupervisorError('Step IDs must be unique.')
    limit = spec.setdefault('max_parallel', 2)
    if type(limit) is not int or not 1 <= limit <= 4:
        raise SupervisorError('max_parallel is 1–4 independent native runs.')
    state = spec.setdefault('state', {})
    if type(state) is not dict or len(state) > 64:
        raise SupervisorError('Persistent state is an object of at most 64 owner-defined keys.')
    for key in state:
        identifier(key)
    graph = {}
    for step in steps:
        kind = step.get('kind')
        fields = {'id', 'kind', 'after', 'when', 'on_failure'}
        fields |= {'run': {'source', 'inputs', 'options', 'deadline_s'}, 'wait': {'until', 'within_s'},
                   'delay': {'seconds'}, 'set': {'changes'}, 'join': set()}.get(kind, set())
        if kind not in ('run', 'wait', 'delay', 'set', 'join') or set(step) - fields:
            raise SupervisorError('Use run, wait, delay, set or join with its documented fields.')
        after = step.setdefault('after', [])
        if type(after) is not list or len(after) != len(set(after)) or not set(after) <= set(ids):
            raise SupervisorError('after must be a unique list of known step IDs.')
        dependencies = set(after)
        if 'on_failure' in step:
            if step['on_failure'] not in ids:
                raise SupervisorError('on_failure must name a native or wait step.')
            dependencies.add(step['on_failure'])
        if 'when' in step:
            step['when'] = condition(step['when'], ids)
            if 'step' in step['when']:
                dependencies.add(step['when']['step'])
        graph[step['id']] = dependencies
        if kind == 'run':
            if not isinstance(step.get('source'), str) or not 1 <= len(step['source']) <= 200000:
                raise SupervisorError('A run needs exact native Symblic source, at most 200000 characters.')
            if type(step.setdefault('inputs', {})) is not dict:
                raise SupervisorError('Run inputs must be an object.')
            opts = step.setdefault('options', {})
            if type(opts) is not dict or set(opts) - {'by', 'model_policy', 'mode', 'side_effects', 'max_effects'}:
                raise SupervisorError('Run options accept by, model_policy, mode, side_effects and max_effects only.')
            if 'mode' in opts and opts['mode'] not in ('full', 'guarded'):
                raise SupervisorError('mode must be full or guarded.')
            if 'side_effects' in opts and type(opts['side_effects']) is not bool:
                raise SupervisorError('side_effects must be Boolean.')
            if 'by' in opts and not isinstance(opts['by'], str):
                raise SupervisorError('by must be the exact applicator specification.')
            number(step.setdefault('deadline_s', 3600), 'deadline_s', 1)
        elif kind == 'wait':
            step['until'] = condition(step.get('until'), ids)
            number(step.get('within_s'), 'within_s', 1)
        elif kind == 'delay':
            number(step.get('seconds'), 'seconds', 0)
        elif kind == 'set':
            changes = step.get('changes')
            if type(changes) is not dict or not 1 <= len(changes) <= 64:
                raise SupervisorError('A set step needs 1–64 state changes.')
            for key, operation in changes.items():
                identifier(key)
                if type(operation) is not dict or set(operation) not in ({'set'}, {'increment'}):
                    raise SupervisorError('A state change is {set: JSON} or {increment: number}.')
                if 'increment' in operation:
                    number(operation['increment'], 'increment', -1e12, 1e12)
    def visit(key, visiting, seen):
        if key in visiting:
            raise SupervisorError('Dependency cycles are refused; a workflow is a bounded DAG.')
        if key in seen:
            return
        for parent in graph[key]:
            visit(parent, visiting | {key}, seen)
        seen.add(key)
    seen = set()
    for key in ids:
        visit(key, set(), seen)
    return spec


def freeze(spec):
    """Metadata and exact checks only; no model, native run or capability execution."""
    import host_runner as C
    import host_planner as CP
    from symblic.kernel import execution_pins as X
    from symblic.kernel import effects as FX
    spec = validate(spec)
    rows = C.catalogue_rows()
    conf = C.settings()
    hashes = {name: hashlib.sha256((X.BASE / name).read_bytes()).hexdigest()
              for name in X.PYTHON_FILES | X.LIBRARY_FILES.keys()}
    frozen = {}
    for step in spec['steps']:
        if step['kind'] != 'run':
            continue
        check = FX.check(step['source'], rows)
        if not check.get('ok'):
            raise SupervisorError('Step ' + step['id'] + ' does not check: ' + str(check.get('errors'))[:500])
        inputs = CP.clock_inputs(step['source'], step['inputs'])
        missing = [r['name'] for r in check.get('inputs', []) if r.get('required') and r['name'] not in inputs]
        if missing:
            raise SupervisorError('Missing native inputs for ' + step['id'] + ': ' + ', '.join(missing))
        opts = clone(step['options'])
        policy = C._model_policy(conf)
        if 'model_policy' in opts:
            policy = C._lowered_policy(policy, opts['model_policy'])
        # Freeze the current ceiling; future runs may lower it, never silently regain authority.
        opts['model_policy'] = policy
        opts['mode'] = 'guarded' if conf['mode'] == 'guarded' or opts.get('mode') == 'guarded' else 'full'
        opts['side_effects'] = bool(conf['side_effects']) and opts.get('side_effects', True) is not False
        limit = opts.get('max_effects', conf['max_effects'])
        if type(limit) is not int or not 1 <= limit <= 500:
            raise SupervisorError('max_effects must be a whole number from 1 to 500.')
        opts['max_effects'] = min(conf['max_effects'], limit)
        if opts.get('by') not in (None, '', 'auto'):
            C._explicit_route(opts['by'], conf, policy)
        opts['execution_pins'] = X.build(step['source'], inputs, hashes, capabilities=rows)
        frozen[step['id']] = {'source': step['source'], 'inputs': inputs, 'options': opts,
                              'clock_inputs': sorted(set(inputs) - set(step['inputs']))}
    return spec, frozen


def _request(value):
    return identifier(value)


def create(spec, request_id):
    request_id = _request(request_id)
    ident = 'w_' + digest({'request': request_id})[:24]
    with locked(ident) as path:
        if path.exists():
            row = read(path)
            if row['request_digest'] != digest(spec):
                raise Conflict('This creation identity already belongs to another workflow.')
            return row
        try:
            clean, frozen = freeze(spec)
        except Exception as exc:
            raise SupervisorError(str(exc)[:600]) from None
        row = {'version': VERSION, 'id': ident, 'request_id': request_id, 'request_digest': digest(spec),
               'definition': clean, 'definition_sha256': digest(clean), 'frozen': frozen,
               'state': clone(clean['state']), 'revision': 0, 'events': [], 'jobs': [],
               'created': clock(), 'updated': clock(), 'paused': False, 'schedule': None, 'pulse': None,
               'operations': {}, 'event_triggers': {}}
        event(row, 'created', definition_sha256=row['definition_sha256'])
        save(path, row)
        return row


def view(ident):
    with locked(ident) as path:
        return read(path)


def listing():
    rows = []
    for path in sorted(root().glob('w_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        try:
            row = read(path)
            rows.append({k: row[k] for k in ('id', 'revision', 'created', 'updated', 'paused')})
            rows[-1].update(name=row['definition']['name'], jobs=len(row['jobs']),
                            last_status=row['jobs'][-1]['status'] if row['jobs'] else None)
        except SupervisorError:
            rows.append({'id': path.stem, 'error': 'Saved record cannot be read.'})
    return {'workflows': rows}


def _job(row, job_id):
    for job in row['jobs']:
        if job['id'] == job_id:
            return job
    raise SupervisorError('No such recorded firing.')


def _active(row):
    return [job for job in row['jobs'] if job['status'] not in TERMINAL]


def _fire(row, identity, origin):
    key = digest(identity)
    for job in row['jobs']:
        if job['identity_sha256'] == key:
            return job
    if len(row['jobs']) >= MAX_JOBS:
        raise SupervisorError('This workflow has 100 recorded firings; create a new saved workflow to continue.')
    status = 'skipped' if row['paused'] or _active(row) else 'running'
    job = {'id': 'f_' + key[:24], 'identity_sha256': key, 'origin': clone(origin), 'created': clock(),
           'definition_sha256': row['definition_sha256'], 'status': status, 'steps': {}}
    if status == 'skipped':
        job['reason'] = 'workflow_paused' if row['paused'] else 'previous_firing_unfinished'
    else:
        job['steps'] = {s['id']: {'status': 'pending'} for s in row['definition']['steps']}
    row['jobs'].append(job)
    event(row, 'firing', firing=job['id'], status=status, origin=origin)
    return job


def start(ident, request_id):
    with locked(ident) as path:
        row = read(path)
        _fire(row, {'owner_request': _request(request_id)}, {'kind': 'owner'})
        save(path, row)
    return tick(ident, restore_clock=True)


def _matches(test, state, job):
    if 'state' in test:
        return test['state'] in state and digest(state[test['state']]) == digest(test['equals'])
    return job['steps'][test['step']]['status'] == test['status']


def _native_bytes(path, limit=16_000_000):
    if path.is_symlink():
        raise SupervisorError('Native evidence cannot be a symbolic link.')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise SupervisorError('Native evidence exceeds its inspection limit.')
    return raw


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON field')
            result[key] = value
        return result
    def constant(_value):
        raise ValueError('nonfinite JSON value')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def _native_view(native_id):
    """UI summary plus exact identity; unreadable metadata cannot become empty defaults."""
    import host_runner as C
    folder = Path(C.run_dir(native_id))
    meta = _strict_json(_native_bytes(folder / 'meta.json'))
    if type(meta) is not dict or type(meta.get('options')) is not dict or type(meta.get('inputs')) is not dict:
        raise SupervisorError('Native submission metadata is incomplete.')
    return {**C.run_view(native_id), 'prompt': meta.get('prompt'), 'inputs': meta['inputs'],
            'source': _native_bytes(folder / 'program.sym').decode('utf-8'), 'options': meta['options']}


def _native_status(native):
    """Strict, read-only authority. UI projections deliberately skip damaged ledger rows."""
    import host_runner as C
    from symblic.kernel import run as SR
    folder = Path(C.run_dir(native['id']))
    active = C.launcher['active'](C.run_unit(native['id']))
    try:
        raw = _native_bytes(folder / 'state.json')
    except FileNotFoundError:
        return 'running' if active is True else 'unknown'
    state = _strict_json(raw)
    if type(state) is not dict or state.get('status') not in ('queued', 'new', 'running', 'done', 'failed', 'stopped'):
        raise SupervisorError('Native terminal status is missing or unrecognized.')
    status = state['status']
    if status in ('queued', 'new', 'running'):
        return 'running' if active is True else 'unknown'
    if status not in ('done', 'failed') or active is not False:
        return 'unknown'
    if isinstance(state.get('error'), dict) and state['error'].get('kind') in ('uncertain', 'unknown'):
        return 'unknown'
    evidence, absent = [], []
    for filename, key in SR.EFFECT_LEDGERS:
        path = folder / filename
        try:
            data = _native_bytes(path)
        except FileNotFoundError:
            absent.append(path)
            continue
        if data and not data.endswith(b'\n'):
            raise SupervisorError('Native journal has an unfinished tail: ' + filename)
        latest = {}
        for line in data.splitlines():
            if not line.strip():
                continue
            record = _strict_json(line)
            if type(record) is not dict or not isinstance(record.get(key), str) or not record[key] or \
                    record.get('phase') not in ('intent', 'done', 'failed', 'unknown'):
                raise SupervisorError('Native journal has an invalid record: ' + filename)
            latest[record[key]] = record
        if any(record['phase'] not in ('done', 'failed') for record in latest.values()):
            return 'unknown'
        evidence.append((path, data))
    # A concurrent resume or append cannot turn an earlier failed snapshot into
    # authority for a compensating run. Never repair or truncate these files.
    if C.launcher['active'](C.run_unit(native['id'])) is not False or _native_bytes(folder / 'state.json') != raw:
        return 'unknown'
    if any(path.exists() for path in absent) or any(_native_bytes(path) != data for path, data in evidence):
        return 'unknown'
    return status


def _body(row, step_id, record):
    body = clone(row['frozen'][step_id])
    body.pop('clock_inputs', None)
    body.update(record['submission'])
    return body


def _same_native(row, step_id, record, native):
    body = _body(row, step_id, record)
    opts = native.get('options') or {}
    saved = body['options']
    actual = opts.get('model_policy')
    if type(actual) is not dict or set(actual) != {'max_calls', 'repairs', 'allow_cloud'}:
        return False
    if type(actual['allow_cloud']) is not bool or (actual['allow_cloud'] and not saved['model_policy']['allow_cloud']):
        return False
    for key in ('max_calls', 'repairs'):
        if type(actual[key]) is not int or not 0 <= actual[key] <= saved['model_policy'][key]:
            return False
    if type(opts.get('max_calls')) is not int or not 0 <= opts['max_calls'] <= actual['max_calls']:
        return False
    if opts.get('mode') not in ('full', 'guarded') or (saved['mode'] == 'guarded' and opts['mode'] != 'guarded'):
        return False
    if type(opts.get('side_effects')) is not bool or (opts['side_effects'] and not saved['side_effects']):
        return False
    if type(opts.get('max_effects')) is not int or not 1 <= opts['max_effects'] <= saved['max_effects']:
        return False
    return (native.get('prompt') == body['prompt'] and native.get('source') == body['source'] and
            digest(native.get('inputs')) == digest(body['inputs']) and
            digest(opts.get('execution_pins')) == digest(saved['execution_pins']) and
            (saved['by'] == opts.get('by') if saved.get('by') not in (None, '', 'auto') else opts.get('by') in (None, 'auto')))


def _poll(row, job, step, record):
    import host_runner as C
    try:
        native = _native_view(record['native_id'])
        if not _same_native(row, step['id'], record, native):
            raise SupervisorError('The native handle no longer matches this exact submission.')
        status = _native_status(native)
        record['native_status'] = native.get('status')
        record['native_error'] = str(native.get('error') or '')[:500]
        if status in ('done', 'failed'):
            record['status'] = status
            record['finished'] = clock()
            event(row, 'native_finished', firing=job['id'], step=step['id'], status=status,
                  native_id=record['native_id'])
        elif clock() >= record['deadline_at']:
            if record['status'] != 'overdue':
                event(row, 'native_deadline', firing=job['id'], step=step['id'], native_id=record['native_id'])
            record['status'] = 'overdue'
            record['error'] = 'Deadline exceeded; native effects are not classified as failed. Inspect the native run.'
        else:
            record['status'] = status
    except Exception as exc:  # read failures cannot justify another submission
        record['status'] = 'unknown'
        record['error'] = 'Native status unknown: ' + str(exc)[:400]


def _ready(step, record, job, state):
    if record['status'] != 'pending':
        return False
    statuses = job['steps']
    failed = step.get('on_failure')
    if failed:
        status = statuses[failed]['status']
        if status in ('done', 'skipped'):
            record.update(status='skipped', reason='failure_handler_not_needed')
            return False
        if status != 'failed':
            return False
    parents = [statuses[k]['status'] for k in step['after']]
    if any(p in ('failed', 'skipped') for p in parents):
        record.update(status='skipped', reason='dependency_did_not_succeed')
        return False
    if not all(p == 'done' for p in parents):
        return False
    if 'when' in step and not _matches(step['when'], state, job):
        record.update(status='skipped', reason='precondition_false')
        return False
    return True


def _state_change(state, changes):
    result = clone(state)
    for key, operation in changes.items():
        if 'set' in operation:
            result[key] = clone(operation['set'])
        else:
            before = result.get(key, 0)
            number(before, 'state increment target', -1e12, 1e12)
            result[key] = number(before + operation['increment'], 'state increment result', -1e12, 1e12)
    if len(result) > 64:
        raise SupervisorError('Persistent state exceeds 64 keys.')
    return result


def _advance(path, row):
    import host_runner as C
    for job in _active(row):
        definitions = row['definition']['steps']
        for step in definitions:
            rec = job['steps'][step['id']]
            if rec.get('native_id') and rec['status'] not in TERMINAL:
                _poll(row, job, step, rec)
            elif rec['status'] == 'submitting':
                rec.update(status='unknown', error='The process stopped during native handoff. Reconcile its exact handle; do not resubmit.')
                event(row, 'handoff_unknown', firing=job['id'], step=step['id'])
        # Bounded fixed point permits pure state/join chains without minute-long
        # delays, while polling and launching each child at most once per tick.
        for _ in range(MAX_STEPS + 1):
            before = digest({'steps': job['steps'], 'state': row['state']})
            for step in definitions:
                rec = job['steps'][step['id']]
                if rec['status'] == 'waiting':
                    if step['kind'] == 'delay' and clock() >= rec['until_at']:
                        rec.update(status='done', finished=clock())
                    elif step['kind'] == 'wait':
                        if _matches(step['until'], row['state'], job):
                            rec.update(status='done', finished=clock())
                        elif clock() >= rec['until_at']:
                            rec.update(status='failed', finished=clock(), error='Bounded wait expired; no native action was dispatched by this wait.')
                if not _ready(step, rec, job, row['state']):
                    continue
                kind = step['kind']
                if kind == 'run':
                    busy = sum(1 for s in definitions if s['kind'] == 'run' and
                               job['steps'][s['id']]['status'] in ('running', 'submitting', 'unknown', 'overdue'))
                    if busy >= row['definition']['max_parallel']:
                        continue
                    frozen = row['frozen'][step['id']]
                    try:
                        # These are pure metadata/pin checks before submission.
                        # A refusal here is known to have started no child.
                        C._checked_pins(frozen['options']['execution_pins'], frozen['source'], frozen['inputs'])
                        conf = C.settings()
                        policy = C._lowered_policy(C._model_policy(conf), frozen['options']['model_policy'])
                        if frozen['options'].get('by') not in (None, '', 'auto'):
                            C._explicit_route(frozen['options']['by'], conf, policy)
                    except Exception as exc:
                        rec.update(status='failed', finished=clock(), refused_before_submission=True,
                                   error='Native preflight refused before submission: ' + str(exc)[:400])
                        event(row, 'native_refused', firing=job['id'], step=step['id'])
                        continue
                    body = clone(frozen)
                    body.pop('clock_inputs', None)
                    body.update(title=row['definition']['name'] + ' · ' + step['id'],
                                prompt=f"Symblic supervisor {row['id']}/{job['id']}/{step['id']} submission {secrets.token_hex(12)}")
                    rec.update(status='submitting', started=clock(), deadline_at=clock() + step['deadline_s'],
                               submission={k: body[k] for k in ('title', 'prompt')}, submission_sha256=digest(body))
                    event(row, 'native_intent', firing=job['id'], step=step['id'], request_sha256=rec['submission_sha256'])
                    save(path, row)  # durable BEFORE the first possible native effect
                    try:
                        answer = C.start_run(body, warm=False)
                        if not isinstance(answer, dict) or not re.fullmatch(r'[a-f0-9]{12}', str(answer.get('id') or '')):
                            raise SupervisorError('The host runner did not return a native handle.')
                        rec.update(status='running', native_id=answer['id'])
                        event(row, 'native_submitted', firing=job['id'], step=step['id'], native_id=answer['id'])
                    except Exception as exc:
                        rec.update(status='unknown', error='Native handoff outcome unknown: ' + str(exc)[:400])
                        event(row, 'handoff_unknown', firing=job['id'], step=step['id'])
                    save(path, row)
                elif kind == 'set':
                    try:
                        row['state'] = _state_change(row['state'], step['changes'])
                        rec.update(status='done', finished=clock())
                    except SupervisorError as exc:
                        rec.update(status='failed', error=str(exc), finished=clock())
                    event(row, 'state_step', firing=job['id'], step=step['id'], status=rec['status'])
                elif kind == 'join':
                    rec.update(status='done', finished=clock())
                else:
                    rec.update(status='waiting', started=clock(),
                               until_at=clock() + (step['seconds'] if kind == 'delay' else step['within_s']))
            if before == digest({'steps': job['steps'], 'state': row['state']}):
                break
        statuses = [r['status'] for r in job['steps'].values()]
        if all(s in TERMINAL for s in statuses):
            job['status'] = 'failed' if 'failed' in statuses else 'done'
            job['finished'] = clock()
            event(row, 'firing_finished', firing=job['id'], status=job['status'])
        elif any(s in ('unknown', 'overdue') for s in statuses):
            job['status'] = 'needs_attention'
        else:
            job['status'] = 'running'


def _scheduler():
    import host_runner as C
    return C.scheduler


def _trigger(row, key, tool, args, *, kind='cron', spec=None):
    return {'key': key, 'name': 'Symblic: ' + row['definition']['name'], 'kind': kind,
            'spec': spec or {'expr': '* * * * *'},
            'action': {'type': 'mission.start', 'kind': 'single', 'title': 'Symblic workflow',
                       'goal': 'Advance the recorded owner-defined Symblic workflow.',
                       'spec': {'tool': tool, 'args': args},
                       'policy': {'release': 'local', 'tools': 'none', 'external_send': False}},
            'misfire': {'policy': 'late_within', 'grace_s': 120, 'until_day_end': False}}


def _pulse(path, row, restore=False):
    """A minute pulse exists only while bounded work can advance automatically."""
    pending = any(job['status'] == 'running' for job in _active(row)) or any(rec['status'] in ('waiting', 'running') or
                  (rec.get('native_id') and rec['status'] == 'unknown' and clock() < rec['deadline_at'])
                  for job in _active(row) for rec in job['steps'].values())
    key = 'symblic.pulse.' + row['id']
    sched = _scheduler()
    if pending and not row['paused']:
        have = sched['get'](key)
        if row.get('pulse') and row['pulse'].get('enabled') and (not have or not have.get('enabled')) and not restore:
            raise SupervisorError('The operator disabled or removed the scheduler pulse. Resume this workflow to restore its clock.')
        if have and have.get('enabled'):
            expected = _trigger(row, key, 'runner.supervisor_tick', {'workflow': row['id']})
            if any(digest(have.get(k)) != digest(expected.get(k)) for k in ('kind', 'spec', 'action', 'misfire')) or \
                    have.get('max_fires') or have.get('expires_at'):
                raise SupervisorError('The scheduler recovery pulse changed. Restore its exact saved action and timing before advancing.')
            row['pulse'] = {'key': key, 'trigger': sched['id'](key), 'enabled': True, 'status': 'installed'}
            return
        row['pulse'] = {'key': key, 'trigger': sched['id'](key), 'enabled': True, 'status': 'intent'}
        save(path, row)  # the trusted firing identity precedes installation
        definition = _trigger(row, key, 'runner.supervisor_tick', {'workflow': row['id']})
        result = sched['ensure'](definition)
        if result.get('errors'):
            raise SupervisorError('The scheduler could not install the workflow pulse: ' + str(result['errors'])[:250])
        if not sched['enable'](key, True):
            raise SupervisorError('The scheduler could not enable the workflow pulse.')
        row['pulse']['status'] = 'installed'
    elif row.get('pulse') and row['pulse'].get('enabled'):
        if not sched['enable'](key, False) and sched['get'](key):
            raise SupervisorError('The scheduler could not disable the completed workflow pulse.')
        row['pulse']['enabled'] = False


def tick(ident, *, restore_clock=False):
    with locked(ident) as path:
        row = read(path)
        # Install the recovery clock before the first native handoff. A process
        # death after submission then leaves both the intent and its wakeup.
        try:
            _pulse(path, row, restore_clock)
        except Exception as exc:
            row['clock_error'] = str(exc)[:400]
            event(row, 'clock_unavailable', active=len(_active(row)))
            save(path, row)
            return row
        if not row['paused']:
            _advance(path, row)
        try:
            _pulse(path, row, restore_clock)
            row.pop('clock_error', None)
        except Exception as exc:
            row['clock_error'] = str(exc)[:400]
        event(row, 'tick', active=len(_active(row)))
        save(path, row)
        return row


def mutate(ident, revision, request_id, operation, payload):
    """Revision-checked owner state/pause changes with durable retry identity."""
    token = _request(request_id)
    request = digest({'operation': operation, 'payload': payload})
    with locked(ident) as path:
        row = read(path)
        previous = row['operations'].get(token)
        if previous:
            if previous != request:
                raise Conflict('This operation identity already belongs to another change.')
            return row
        if type(revision) is not int or revision != row['revision']:
            raise Conflict('This workflow changed. Refresh it before editing.')
        if len(row['operations']) >= 1000:
            raise SupervisorError('The workflow operation ledger is full; create a new workflow.')
        if operation == 'state':
            if type(payload) is not dict or not 1 <= len(payload) <= 64:
                raise SupervisorError('State changes must be a bounded object.')
            for key in payload:
                identifier(key)
            row['state'] = _state_change(row['state'], {key: {'set': value} for key, value in payload.items()})
        elif operation == 'pause':
            if type(payload) is not bool:
                raise SupervisorError('paused is a Boolean.')
            row['paused'] = payload
        else:
            raise SupervisorError('Unknown workflow mutation.')
        row['operations'][token] = request
        event(row, operation, request_id=token)
        save(path, row)
    return tick(ident, restore_clock=operation == 'pause' and payload is False)


def reconcile(ident, job_id, step_id, native_id):
    import host_runner as C
    with locked(ident) as path:
        row = read(path)
        job = _job(row, identifier(job_id))
        rec = job['steps'].get(identifier(step_id))
        if not rec or 'submission' not in rec or rec['status'] not in ('unknown', 'submitting', 'running', 'overdue'):
            raise SupervisorError('That step has no unresolved native handoff.')
        native = _native_view(native_id)
        if rec.get('native_id') not in (None, native_id) or not _same_native(row, step_id, rec, native):
            raise SupervisorError('The native run does not match the exact source, inputs, pins and submission identity.')
        rec.update(native_id=native_id, status='running')
        event(row, 'native_reconciled', firing=job_id, step=step_id, native_id=native_id)
        save(path, row)
    return tick(ident)


def schedule(ident, cron, enabled, revision):
    import host_triggers as T
    if not isinstance(cron, str) or len(cron) > 120:
        raise SupervisorError('Use a bounded five-field cron expression.')
    T.parse_cron(cron)
    if type(enabled) is not bool:
        raise SupervisorError('enabled must be a Boolean.')
    with locked(ident) as path:
        row = read(path)
        if type(revision) is not int or revision != row['revision']:
            raise Conflict('This workflow changed. Refresh before editing its schedule.')
        key = 'symblic.fire.' + ident
        row['schedule'] = {'key': key, 'trigger': _scheduler()['id'](key), 'cron': cron,
                           'enabled': enabled, 'status': 'intent'}
        event(row, 'schedule_intent', cron=cron, enabled=enabled)
        save(path, row)
        try:
            definition = _trigger(row, key, 'runner.supervise', {'workflow': ident}, spec={'expr': cron})
            definition['enabled'] = enabled
            result = _scheduler()['ensure'](definition)
            if result.get('errors'):
                raise SupervisorError(str(result['errors']))
            if not _scheduler()['enable'](key, enabled):
                raise SupervisorError('The scheduler did not confirm the schedule enable/disable operation.')
            row['schedule']['status'] = 'installed'
        except Exception as exc:
            row['schedule'].update(status='unknown', error=str(exc)[:400])
        event(row, 'schedule_recorded', status=row['schedule']['status'])
        save(path, row)
        return row



def lookup_trigger(trigger_id):
    import host_sched
    return host_sched.store().get('triggers', trigger_id)


def _event_contract(trigger, ident):
    if not isinstance(trigger, dict) or trigger.get('kind') not in ('email_reply', 'email_match', 'calendar', 'file', 'webhook'):
        raise SupervisorError('Select an existing scheduler event trigger, with its real watcher or producer configured.')
    action = trigger.get('action') or {}
    spec = action.get('spec') or {}
    if action.get('type') != 'mission.start' or action.get('kind') != 'single' or spec.get('tool') != 'runner.supervise' or spec.get('args') != {'workflow': ident}:
        raise SupervisorError('The event trigger must start a single runner.supervise step with only this workflow ID.')
    return digest({'kind': trigger['kind'], 'spec': trigger.get('spec'), 'action': action})


def bind_trigger(ident, trigger_id, revision):
    if not isinstance(trigger_id, str) or not re.fullmatch(r't_[a-f0-9]{12}', trigger_id):
        raise SupervisorError('Use the existing scheduler trigger ID (t_ plus 12 hex digits).')
    with locked(ident) as path:
        row = read(path)
        if type(revision) is not int or revision != row['revision']:
            raise Conflict('This workflow changed. Refresh before attaching its event trigger.')
        trigger = lookup_trigger(trigger_id)
        contract = _event_contract(trigger, ident)
        subscriptions = row.setdefault('event_triggers', {})
        if trigger_id not in subscriptions and len(subscriptions) >= 8:
            raise SupervisorError('A workflow can attach at most eight existing event triggers.')
        subscriptions[trigger_id] = {'contract_sha256': contract, 'kind': trigger['kind'], 'bound_at': clock()}
        event(row, 'event_trigger_attached', trigger=trigger_id, contract_sha256=contract)
        save(path, row)
        return row

def fire_tool(args, ctx=None, *, advance=False):
    """Only scheduler-minted context can claim a timer firing. Payload is never an input."""
    import host_tools as bt
    ctx = ctx if type(ctx) is dict else {}
    try:
        ident = identifier((args or {}).get('workflow'))
        with locked(ident) as path:
            row = read(path)
            expected = row.get('pulse' if advance else 'schedule') or {}
            trusted = bool(ctx.get('trigger')) and ctx.get('trigger') == expected.get('trigger')
            if not advance and not trusted:
                subscription = row.get('event_triggers', {}).get(ctx.get('trigger'))
                if subscription:
                    trusted = _event_contract(lookup_trigger(ctx['trigger']), ident) == subscription['contract_sha256']
            if not trusted or not ctx.get('step') or not ctx.get('mission'):
                raise SupervisorError('This tool needs the workflow’s recorded scheduler timer or attached event context. Start manually in Symblic or its CLI.')
            origin = {key: str(ctx[key])[:100] for key in ('trigger', 'step', 'mission')}
            if advance:
                event(row, 'pulse_firing', **origin)
            else:
                _fire(row, {'scheduler_step': origin['step'], 'mission': origin['mission']}, {'kind': 'scheduler', **origin})
            save(path, row)
        result = tick(ident)
        return bt.result('Workflow tick recorded.', {'id': ident, 'revision': result['revision'],
                                                    'status': result['jobs'][-1]['status'] if result['jobs'] else 'idle'})
    except Exception as exc:
        return {'ok': False, 'text': str(exc)[:500], 'json': None, 'meta': {}}


def simulate(spec, outcomes=None):
    """Explicitly synthetic model of the DAG: no stores, clocks, native execution or timers."""
    spec = validate(spec)
    outcomes = clone(outcomes or {})
    if type(outcomes) is not dict or any(v not in ('done', 'failed', 'unknown') for v in outcomes.values()):
        raise SupervisorError('Simulation outcomes are explicit done, failed or unknown values keyed by step ID.')
    state = clone(spec['state'])
    job = {'steps': {s['id']: {'status': 'pending'} for s in spec['steps']}}
    elapsed = 0
    for _ in range(MAX_STEPS + 1):
        before = digest(job)
        for step in spec['steps']:
            rec = job['steps'][step['id']]
            if not _ready(step, rec, job, state):
                continue
            kind = step['kind']
            if kind == 'run':
                rec['status'] = outcomes.get(step['id'], 'unknown')
            elif kind == 'set':
                state = _state_change(state, step['changes'])
                rec['status'] = 'done'
            elif kind == 'wait':
                rec['status'] = 'done' if _matches(step['until'], state, job) else 'failed'
                if rec['status'] == 'failed':
                    elapsed += step['within_s']
            else:
                rec['status'] = 'done'
                if kind == 'delay':
                    elapsed += step['seconds']
        if before == digest(job):
            break
    return {'simulation': True, 'executed': False, 'assumptions': outcomes, 'steps': job['steps'], 'state': state,
            'serial_wait_seconds': elapsed,
            'notice': 'Synthetic control-flow exercise only. Native programs, observations, models, effects and real elapsed time were not executed or validated.'}
