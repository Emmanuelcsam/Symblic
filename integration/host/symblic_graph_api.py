"""HOST-ONLY: the host's `graph/` routes and graph-job worker; needs its store, systemd units and owner gate.

What it did: operator-only HTTP routes that check, start, follow, stop and resume agent-graph jobs
(symblic/graph/: typed groups of model steps with code checks) inside the host's private Symblic store. A
job ran in its own transient systemd user unit (`python -m integration.host.symblic_graph_api job ...`)
started through integration/host/symblic_engine.py. The graph planner and runner themselves
(symblic/graph/) work without the host; `tools/symblic graph ...` composes graphs locally.


Import is inert. Only the explicit job entrypoint constructs registered Apps;
checks and read views never dispatch. Per-job locks serialize launch controls,
and GraphRun owns its intent/outcome recovery within each runtime subfolder.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
import re
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
import weakref

from symblic.kernel import language as S
from symblic.graph import planner as G
from symblic.graph import run as R

# A worker runs this file as __main__; its loaded identity is pinned like the
# other graph modules (symblic.graph.run checks every loaded copy).
_SOURCE_SHA256, _SOURCE_LOADED = G._import_identity(__file__, sys._getframe(0).f_code)
# A worker holds WORKER_LOCK from begin_job until it finishes or dies, so no newer
# generation can be reserved while it may still dispatch. A Stop holds STOP_LOCK
# until its signal has settled, so Resume cannot start a newer generation that
# the Stop's signal to the stable unit name would reach. The kernel drops both
# flocks when their holder exits, so a crash never leaves either one held.
WORKER_LOCK, STOP_LOCK = '.worker.lock', '.stop.lock'
WORKER_LOCK_WAIT = 10.0
STOP_CONFIRM_WAIT = 10.0
_HELD = {}
_HELD_LOCK = threading.Lock()

SCOPE = 'Completion means the declared node checks passed; premises and model proposals remain conditional.'


class ApiError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _engine():
    from integration.host import symblic_engine as symblic_engine
    return symblic_engine


def _root():
    path = Path(_engine().root()) / 'graphs'
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def _folder(ident):
    if type(ident) is not str or not _engine().ID_RX.fullmatch(ident):
        raise ApiError('No such graph.', 404)
    folder = _root() / ident
    if folder.is_symlink() or not folder.is_dir():
        raise ApiError('No such graph.', 404)
    return folder


def _save(folder, name, value):
    R._write_json(Path(folder), name, value)


@contextmanager
def _control(folder):
    path = folder / '.control.lock'
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def unit(ident):
    return 'symblic-graph-' + ident


def _launch(ident, folder, generation):
    return _engine()._launch_unit(unit(ident), ['-m', 'integration.host.symblic_graph_api', 'job', '--id', ident,
                                              '--folder', str(folder), '--generation', generation])


def liveness(unit_name):
    """'active', 'inactive' or 'unknown' for a transient job unit (graph or policy)."""
    try:
        result = subprocess.run(['systemctl', '--user', 'is-active', unit_name + '.service'],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return 'unknown'
    state = result.stdout.strip()
    if state in ('active', 'activating', 'deactivating', 'reloading', 'refreshing'):
        return 'active'
    return 'inactive' if state in ('inactive', 'failed') else 'unknown'


def _active(ident):
    # A failed probe is not evidence the worker stopped: unknown counts as active,
    # so no new generation is reserved and Stop still signals the unit.
    return liveness(unit(ident)) != 'inactive'


def _stop(ident):
    return _engine()._systemd_stop(ident, unit(ident))


launcher = {'launch': _launch, 'active': _active, 'stop': _stop}


def _acquire(path, wait):
    """Exclusive flock on a private lock file; waits up to `wait` seconds (None: no limit)."""
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    deadline = None if wait is None else time.monotonic() + wait
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return {'fd': descriptor}
        except BlockingIOError:
            if deadline is not None and time.monotonic() >= deadline:
                os.close(descriptor)
                return None
            time.sleep(0.02)


def _release(holder):
    descriptor = holder.pop('fd', None) if holder else None
    if descriptor is not None:
        os.close(descriptor)  # closing the description releases its flock


def _held(path):
    """Another open description holds this lock. Unreadable lock state counts as held."""
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(descriptor)


def worker_alive(folder):
    """A worker of this job still holds its lifetime lock (independent of systemd's answer)."""
    return _held(Path(folder) / WORKER_LOCK)


def stop_settling(folder):
    """A Stop of this job is still recording or signalling its unit."""
    return _held(Path(folder) / STOP_LOCK)


def _release_worker(folder, generation):
    with _HELD_LOCK:
        holder = _HELD.pop((str(Path(folder)), generation), None)
    _release(holder)


def _forget(key, holder):
    """Finalizer of a JobStop that was never released: drop its lease and registry entry."""
    with _HELD_LOCK:
        if _HELD.get(key) is holder:
            del _HELD[key]
    _release(holder)


def example():
    """A useful zero-model two-node composition; route matters only for asks."""
    route = {'id': 'Local', 'provider': 'ollama', 'model': 'qwen3:4b-instruct', 'node': 'node-a', 'local': True}
    allowed = {'routes': ['Local'], 'providers': ['ollama'], 'models': [route['model']],
               'nodes': ['node-a'], 'local_only': True}
    common = {'output_binding': 'answer', 'output_schema': {'type': 'integer'}, 'allowed': allowed,
              'join': 'require_all', 'effect_risk': 'none', 'retries': 0, 'call_limit': 1,
              'max_calls': 1, 'max_iterations': 1}
    a = {**common, 'id': 'Measure', 'inputs': {},
         'source': 'use profile=verified.\nlet answer = 6.\nshow answer.',
         'contract': 'The declared input is six units.', 'checks': ['answer = 6'],
         'assumptions': ['Six is an owner-supplied example value, not an observed measurement.']}
    b = {**common, 'id': 'Double', 'inputs': {'x': {'node': 'Measure'}},
         'source': 'use profile=verified.\ngiven x: Int.\nlet answer = x * 2.\nshow answer.',
         'contract': 'Double the input under exact integer arithmetic.', 'checks': ['answer = x * 2']}
    return {'graph': {'id': 'DoubleExample', 'nodes': [a, b], 'iterations': 1, 'max_calls': 2},
            'policy': {'version': 1, 'routes': [route], 'order': ['Local']},
            'description': 'Two checked nodes pass an exact value along an edge. This example makes zero model calls. '
                           'Replace node source with explicit asks to use the exact registered route, and review its call cap.'}


def _freeze(body):
    if type(body) is not dict or set(body) - {'graph', 'policy', 'expected_graph_hash', 'expected_policy_hash'}:
        raise ApiError('Supply graph and policy objects, with optional reviewed hashes.')
    frozen = G.freeze_graph(body.get('graph'), body.get('policy'))
    for field in ('graph_hash', 'policy_hash'):
        if 'expected_' + field in body and body['expected_' + field] != frozen[field]:
            raise ApiError('The graph or policy differs from the checked version. Check this document again.', 409)
    # This web job does not inject an effect host. Existing Python GraphRun users
    # may supply their own pinned host; never silently create one from JSON.
    for node in frozen['graph']['nodes']:
        if node['effect_risk'] != 'none':
            raise ApiError('This graph job has no effect host. Use the existing pinned GraphRun host integration for effects.')
        R._route(node, frozen['policy'])
        R._schema(node['output_schema'])
        if 'output_binding' not in node:
            raise ApiError('Each executable graph node needs output_binding.')
        bridge = G.compile_node(node, {name: None for name in node['inputs']})
        checked = S.check(bridge['source'], execution_profile='verified')
        if not checked['ok']:
            raise ApiError('Node ' + node['id'] + ': ' + checked['errors'][0]['message'])
    return frozen


def check(body):
    frozen = _freeze(body)
    state = G.derive(frozen, [])
    attempts = G.worst_case_attempts(frozen['graph'])
    return {'ok': True, 'graph_hash': frozen['graph_hash'], 'policy_hash': frozen['policy_hash'],
            'nodes': frozen['graph']['nodes'], 'iterations': frozen['graph']['iterations'],
            'max_calls': frozen['graph']['max_calls'], 'ready': state['ready'], 'scope': SCOPE,
            'capacity': {'worst_case_attempts': attempts, 'worst_case_events': 2 * attempts + 1,
                         'event_limit': G.MAX_EVENTS, 'ledger_bytes': R.LEDGER_FILE_BYTES,
                         'note': 'Ledger bytes depend on outputs. A run stops before dispatch, recording '
                         'capacity, when another completion could not be recorded.'}}


def compose(body):
    """Expand inline fragments and enforce this web host's existing admission."""
    try:
        from symblic.graph import compose as C
    except ImportError as error:
        raise ApiError('Graph composition is unavailable; refresh after the server update.', 503) from error
    result = C.compose(body)
    checked = check(result['draft'])
    # A returned draft still needs its explicit Check/Run handoff. The manifest
    # describes expansion only and is never passed to the runtime as authority.
    result['check'] = {key: value for key, value in checked.items() if key != 'nodes'}
    result['check']['nodes'] = len(checked['nodes'])
    result['scope'] = 'authoring_only; web execution admission checked; explicitly check and run the flat draft'
    return G.snapshot(result)


def start(body):
    frozen = _freeze(body)
    ident = secrets.token_hex(6)
    folder = _root() / ident
    folder.mkdir(mode=0o700)
    _save(folder, 'frozen.json', frozen)
    _save(folder, 'meta.json', {'id': ident, 'title': frozen['graph']['id'], 'created': time.time(),
                               'version': S.VERSION, 'graph_hash': frozen['graph_hash'],
                               'policy_hash': frozen['policy_hash'], 'scope': SCOPE})
    launch_job(ident, folder, launcher)
    return {'id': ident}


def read_job(folder, *, missing=False):
    value = R._read(Path(folder) / 'job.json', missing=missing)
    if value is None and missing:
        return {}
    states = {'starting', 'running', 'stopping', 'stopped', 'failed', 'succeeded', 'unresolved', 'canceled', 'done'}
    if (type(value) is not dict or type(value.get('status')) is not str or value['status'] not in states
            or type(value.get('updated')) not in (int, float)
            or type(value.get('generation')) is not str or not re.fullmatch(r'[0-9a-f]{24}', value['generation'])
            or type(value.get('cancel_requested', False)) is not bool
            or (value['status'] == 'stopping' and not value.get('cancel_requested'))):
        raise ApiError('The job control record is invalid; reconcile its recorded generation.', 409)
    return value


def launch_job(ident, folder, hooks):
    """Reserve one generation, then call the launcher outside the control lock."""
    folder = Path(folder)
    with _control(folder):
        prior = read_job(folder, missing=True) or {}
        if stop_settling(folder):
            raise ApiError('A Stop of this graph is still settling. Resume after it finishes.', 409)
        # Generation ownership is a lease: while any worker of this job lives, no
        # newer generation is reserved, whatever the unit liveness probe reports.
        if hooks['active'](ident) or worker_alive(folder):
            return {'ok': True, 'id': ident, 'already_active': True}
        if (prior.get('status') == 'starting' and not prior.get('cancel_requested')
                and time.time() - prior.get('updated', 0) < 30):
            return {'ok': True, 'id': ident, 'already_starting': True}
        # A confirmed inactive stopping generation is still fenced by its
        # cancellation marker; an explicit Resume may reserve a new generation.
        generation = secrets.token_hex(12)
        _save(folder, 'job.json', {'status': 'starting', 'generation': generation, 'updated': time.time()})
    result = hooks['launch'](ident, str(folder), generation)
    if not result.get('ok'):
        message = str(result.get('error') or 'The worker could not start.')[:1000]
        with _control(folder):
            current = read_job(folder)
            if current.get('generation') == generation and not current.get('cancel_requested'):
                _save(folder, 'job.json', {**current, 'status': 'failed', 'error': message, 'updated': time.time()})
        raise ApiError(message, 503)
    return {'ok': True, 'id': ident}


def stop_job(ident, folder, hooks):
    folder = Path(folder)
    # Held from recording this Stop until its signal has settled: launch_job
    # refuses meanwhile, so the signal to the stable unit name can only reach
    # the generation recorded here. Concurrent Stops queue behind it.
    guard = _acquire(folder / STOP_LOCK, None)
    try:
        with _control(folder):
            current = read_job(folder, missing=True) or {}
            if current.get('status') in ('done', 'succeeded', 'unresolved', 'canceled'):
                return {'ok': True, 'id': ident, 'terminal': True}
            generation = current.get('generation') or secrets.token_hex(12)
            current = {**current, 'generation': generation}
            _save(folder, '.cancel-' + generation, {'generation': generation})
            _save(folder, 'job.json', {**current, 'cancel_requested': True, 'status': 'stopping',
                                       'updated': time.time()})
        # Never hold the control lock while waiting for a worker which must finish
        # under that same lock. A delayed worker sees its persisted cancellation.
        if hooks['active'](ident) or worker_alive(folder):
            with _control(folder):
                ours = (read_job(folder, missing=True) or {}).get('generation') == generation
            if ours and (not hooks['stop'](ident) or not _stopped(folder)):
                raise ApiError('The worker did not stop; its cancellation remains recorded.', 503)
        with _control(folder):
            current = read_job(folder)
            if current.get('generation') == generation:
                _save(folder, 'job.json', {**current, 'status': 'stopped', 'updated': time.time()})
        return {'ok': True, 'id': ident}
    finally:
        _release(guard)


def _stopped(folder):
    """After a successful unit stop, confirm the worker gave up its lifetime lock."""
    deadline = time.monotonic() + STOP_CONFIRM_WAIT
    while worker_alive(folder):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


class JobStop:
    """Stop signal of one launch generation.

    is_set(): stop dispatching (a signal, the owner's marker, or supersession).
    cancel_requested(): the owner's persisted Stop for this generation, and only
    for jobs whose cancellation is final (graph jobs). A bare signal, such as a
    host shutdown, interrupts and leaves the run resumable.
    fence(): hold the job control lock while this generation is still current;
    otherwise mark the stop superseded and raise R.Superseded. Admission is the
    durable record written under it; the worker lifetime lock taken by begin_job
    keeps the generation current until this worker releases it, so an admitted
    dispatch is never issued by a superseded generation.
    """
    def __init__(self, folder, generation, event, *, final=False, holder=None):
        self.folder = Path(folder)
        self.generation = generation
        self.marker = self.folder / ('.cancel-' + generation)
        self.event, self.final = event, final
        self.superseded = False
        self._holder = holder if holder is not None else {}
        if holder is not None:
            key = (str(self.folder), generation)
            with _HELD_LOCK:
                _HELD[key] = holder
            weakref.finalize(self, _forget, key, holder)
    def release(self):
        """Give up the worker lifetime lock: this worker dispatches and commits nothing more."""
        _release_worker(self.folder, self.generation)
        _release(self._holder)
    def is_set(self):
        return self.superseded or self.event.is_set() or self.marker.exists()
    def cancel_requested(self):
        return self.final and self.marker.exists()
    @contextmanager
    def fence(self):
        with _control(self.folder):
            try:
                current = read_job(self.folder).get('generation')
            except (ValueError, OSError):
                current = None
            if current != self.generation:
                self.superseded = True
                raise R.Superseded('a newer launch generation owns this job')
            yield
    def set(self):
        self.event.set()
    def wait(self, timeout=None):
        if timeout is None:
            while not self.is_set():
                self.event.wait(.2)
            return True
        deadline = time.monotonic() + timeout
        while not self.is_set() and time.monotonic() < deadline:
            self.event.wait(min(.2, max(0, deadline - time.monotonic())))
        return self.is_set()


def begin_job(folder, generation, event, *, final=False):
    """Start one reserved generation; the returned JobStop holds the worker lifetime lock."""
    folder = Path(folder)
    holder = _acquire(folder / WORKER_LOCK, WORKER_LOCK_WAIT)
    if holder is None:
        return None, generation  # another worker of this job is still alive
    try:
        with _control(folder):
            job = read_job(folder)
            generation = generation or job.get('generation')
            if (not generation or job.get('generation') != generation or job.get('cancel_requested')
                    or job.get('status') != 'starting'):
                _release(holder)
                return None, generation
            _save(folder, 'job.json', {**job, 'status': 'running', 'updated': time.time()})
    except BaseException:
        _release(holder)
        raise
    return JobStop(folder, generation, event, final=final, holder=holder), generation


def finish_job(folder, generation, status, error=None, *, reserved_calls=None):
    """Record a worker's final status, then release its lifetime lock."""
    folder = Path(folder)
    try:
        with _control(folder):
            prior = read_job(folder)
            if prior.get('generation') != generation:
                return
            record = {**prior, 'status': status, 'error': error, 'updated': time.time()}
            if type(reserved_calls) is int:
                record['reserved_calls'] = reserved_calls
            _save(folder, 'job.json', record)
    finally:
        _release_worker(folder, generation)


class NoDispatch:
    def call(self, _request):
        raise AssertionError('A read-only audit attempted to dispatch.')


def _identity(folder, ident):
    meta, frozen = R._read(folder / 'meta.json'), R._read(folder / 'frozen.json')
    if (type(meta) is not dict or type(frozen) is not dict or meta.get('id') != ident
            or type(meta.get('title')) is not str or type(meta.get('created')) not in (int, float)
            or any(meta.get(key) != frozen.get(key) for key in ('graph_hash', 'policy_hash'))):
        raise ApiError('Graph metadata differs from the frozen job identity.', 409)
    return meta, frozen


def view(ident, *, audit=True):
    folder = _folder(ident)
    meta, frozen = _identity(folder, ident)
    job = read_job(folder, missing=True) or {}
    active = bool(launcher['active'](ident)) or worker_alive(folder)
    settling = stop_settling(folder)
    try:
        events = R._read(folder / 'runtime' / 'graph-events.jsonl', lines=True, missing=True)
        state = G.derive(frozen, events)
        if audit and state['status'] in ('succeeded', 'unresolved', 'canceled'):
            if not (folder / 'runtime' / 'graph-pins.json').is_file():
                raise G.GraphError('Completed graph lacks durable runtime pins.')
            runner = R.GraphRun(frozen, folder / 'runtime', NoDispatch())
            with runner._locked():
                state = runner._prepare()
        status = state['status']
        if status == 'running' and not active:
            status = job.get('status', 'lost')
            if status in ('running', 'starting'):
                status = 'starting' if time.time() - job.get('updated', 0) < 30 else 'lost'
        # The polled payload carries the ledger once: per-node histories repeat
        # the event rows, and a second 'states' copy repeated every node.
        nodes = [{key: value for key, value in row.items() if key != 'history'} for row in state['states']]
        state = {**{key: value for key, value in state.items() if key != 'states'}, 'status': status, 'nodes': nodes}
        return {'id': ident, 'meta': meta, 'state': state, 'events': events, 'active': active,
                'error': job.get('error'), 'scope': SCOPE,
                'can_resume': not active and not settling and status in ('lost', 'failed', 'stopped', 'starting', 'stopping'),
                'runtime_audited': audit and state['status'] in ('succeeded', 'unresolved', 'canceled')}
    except (G.GraphError, S.SymblicError) as error:
        return {'id': ident, 'meta': meta, 'state': {'status': 'unavailable', 'nodes': [], 'ready': []},
                'events': [], 'active': active, 'error': str(error), 'scope': SCOPE, 'can_resume': False}


def list_runs():
    """Recorded job status only: no ledger read, derivation or recompilation per row."""
    rows = []
    folders = sorted(_root().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for folder in folders[:200]:
        if folder.is_symlink() or not folder.is_dir() or not _engine().ID_RX.fullmatch(folder.name):
            continue
        try:
            meta, _ = _identity(folder, folder.name)
            job = read_job(folder, missing=True) or {}
            status = job.get('status', 'lost')
            if status in ('running', 'starting') and not (launcher['active'](folder.name) or worker_alive(folder)):
                status = 'starting' if time.time() - job.get('updated', 0) < 30 else 'lost'
            row = {**meta, 'status': status, 'error': job.get('error'),
                   'assurance': 'Recorded status; open the run to derive and audit its runtime receipts.'}
            if type(job.get('reserved_calls')) is int:
                row['reserved_calls'] = job['reserved_calls']
            rows.append(row)
        except (ValueError, OSError) as error:
            rows.append({'id': folder.name, 'title': folder.name, 'status': 'unavailable', 'error': str(error)[:300]})
    return rows


def resume(ident):
    folder = _folder(ident)
    current = view(ident)
    if current['state']['status'] in ('canceled', 'succeeded', 'unresolved'):
        return {'ok': True, 'id': ident, 'terminal': True}
    if current['state']['status'] == 'unavailable':
        raise ApiError(current['error'], 409)
    return launch_job(ident, folder, launcher)


def stop(ident):
    return stop_job(ident, _folder(ident), launcher)


def run_job(folder, *, applicators, stop_event=None, generation=None):
    """Injected host bridge, also used in isolated API tests. No provider default."""
    folder = Path(folder)
    stop_event = stop_event if stop_event is not None else threading.Event()
    # Graph cancellation is final, but only the owner's persisted Stop cancels.
    stopped, generation = begin_job(folder, generation, stop_event, final=True)
    if stopped is None:
        return {'status': 'not_started', 'reason': 'canceled, completed, superseded or already running'}
    try:
        try:
            frozen = R._read(folder / 'frozen.json')
            state = R.GraphRun(frozen, folder / 'runtime', applicators, stop=stopped).execute()
        except R.Superseded:
            # A newer generation owns the job record and the graph: write nothing.
            return {'status': 'superseded', 'reason': 'a newer launch generation owns this graph job'}
        except R.Interrupted:
            finish_job(folder, generation, 'stopped', 'Interrupted before completion. Resume continues the open '
                                                      'attempt; answered calls are replayed, interrupted ones are '
                                                      'asked again.')
            return {'status': 'stopped', 'reason': 'interrupted'}
        except Exception as error:
            finish_job(folder, generation, 'failed', str(error)[:1000])
            raise
        finish_job(folder, generation, state['status'], reserved_calls=state['reserved_calls'])
        return state
    finally:
        stopped.release()


def handle(handler, method, route, data):
    if route.startswith('policy/'):
        from integration.host import symblic_policy_api as symblic_policy_api
        return symblic_policy_api.handle(handler, method, route, data)
    if not route.startswith('graph/'):
        return False
    if not handler.identity().is_owner:
        handler.send_json({'error': 'Owner access is required.'}, 403)
        return True
    try:
        if method == 'POST' and type(data) is not dict:
            raise ApiError('Request body must be an object.')
        if method == 'GET' and route == 'graph/example':
            value = example()
        elif method == 'GET' and route == 'graph/composition-example':
            try:
                from symblic.graph import compose as C
            except ImportError as error:
                raise ApiError('Graph composition is unavailable; refresh after the server update.', 503) from error
            value = C.example()
        elif method == 'GET' and route == 'graph/runs':
            value = {'runs': list_runs()}
        elif method == 'GET' and route == 'graph/run':
            value = view(handler.get_query_param('id'))
        elif method == 'POST' and route == 'graph/check':
            value = check(data)
        elif method == 'POST' and route == 'graph/compose':
            value = compose(data)
        elif method == 'POST' and route == 'graph/run':
            value = start(data)
        elif method == 'POST' and route in ('graph/stop', 'graph/resume'):
            value = (stop if route.endswith('/stop') else resume)(data.get('id'))
        else:
            return False
        handler.send_json(value)
    except (ApiError, G.GraphError, S.SymblicError, OSError) as error:
        handler.send_json({'error': str(error)}, getattr(error, 'status', 400))
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['job'])
    parser.add_argument('--folder', required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--generation', required=True)
    args = parser.parse_args()
    # Fixed entrypoint, no dynamic callback/provider imports from request data.
    if not _engine().ID_RX.fullmatch(args.id) or Path(args.folder).name != args.id:
        parser.error('invalid graph job identity')
    from symblic.providers.applicators import Applicators
    apps = Applicators(owner_label='operator (Symblic graph ' + args.id + ')',
                       run_id='graph-' + args.id, allow_web=False, thermal=True)
    stopped = threading.Event()
    def interrupt(_signum, _frame):
        # A signal (host shutdown, unit stop) interrupts; only the owner's
        # persisted marker turns the stop into a durable graph cancellation.
        stopped.set()
        apps.cancel_all()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    run_job(args.folder, applicators=apps, stop_event=stopped, generation=args.generation)


if __name__ == '__main__':
    main()
