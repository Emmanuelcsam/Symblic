"""HOST-ONLY: the host's `mica/` routes and MICA job launcher; needs its store, fleet records and systemd units.

What it did: the operator-only HTTP routes that check, start, follow and stop MICA construction jobs
(symblic/mica/: bounded construction of small JavaScript programs from contracts) under the host's private
Symblic store. Inventory came from the host's cached fleet records (`host_fleet`, `host_agents`); a job ran in
its own transient systemd user unit started through integration/host/symblic_engine.py. Without the host, use
`tools/symblic mica ...` (symblic/mica/cli.py), which runs the same construction locally with your own
applicators.

Import starts no worker or provider. Each launch generation uses the existing
graph-job lifetime/stop fences; native calls retain their own at-most-once journal.
The trusted caller supplies task/inventory data, never executors or absolute paths.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import base64
import hashlib
import re
import secrets
import signal
import threading
import time
from pathlib import Path

from symblic.mica import contracts as C
from symblic.mica import routing as R

from integration.host import symblic_graph_api as J
from symblic.graph import run as G
from symblic.policy import store as PS

VERSION = 1
MODES = ('direct', 'static', 'decompose_on_failure', 'capability', 'search', 'mica')
FORMATS = ('javascript_script', 'javascript_modules')
SCOPE = 'Generated specifications/tests are model proposals; passing finite checks establishes TESTED, not formal correctness.'


def _engine():
    return J._engine()


def _host_ok():
    import worker_health
    return worker_health.host_ok('FLEET_HOST')


def _root():
    path = Path(_engine().root()) / 'mica'
    PS._directory(path, create=True)
    return path


def _folder(ident):
    if type(ident) is not str or not _engine().ID_RX.fullmatch(ident):
        raise J.ApiError('No such MICA job.', 404)
    folder = _root() / ident
    if not folder.exists() and not folder.is_symlink():
        raise J.ApiError('No such MICA job.', 404)
    PS._directory(folder)
    return folder


def _put(folder, name, value):
    path = Path(folder) / name
    sealed = G._seal(value)
    if path.exists() or path.is_symlink():
        if G._unseal(G._read(path)) != sealed:
            raise J.ApiError('An immutable job record changed.', 409)
    else:
        G._write_json(folder, name, sealed)
    return sealed['sha256']


def _read(folder, name):
    row = G._unseal(G._read(Path(folder) / name))
    return {k: v for k, v in row.items() if k != 'sha256'}


def _forge_store():
    from symblic.forge.store import Store
    return Store()


def _implementation():
    from symblic.mica import search as M
    from symblic.mica import project as P
    from symblic.mica import forge as F
    own = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    problems = _symblic_identity.audit(Path(__file__).parent, (Path(__file__).name,),
                                       {Path(__file__).name: own})
    if problems or not _symblic_import_identity['matched'] or _symblic_import_identity['sha256'] != own:
        raise J.ApiError('MICA API source differs from its loaded implementation.', 409)
    return {'api_version': VERSION, 'api_sha256': own, 'construction': M.implementation_identity(),
            'project_sha256': P._identity()['project'], 'proposal_encoding': P._identity()['proposal_encoding'],
            'forge_adapter': F.implementation_identity()}


def _spec(body):
    if type(body) is not dict or set(body) - {'request', 'objective', 'budget', 'allowed_outputs', 'inventory',
            'mode', 'title', 'reuse_components', 'expected_sha256', 'idempotency_key', 'artifact_format', 'calibration', 'forge'}:
        raise J.ApiError('Supply one request, objective or frozen Forge binding, inventory and bounded controls.')
    if sum(key in body for key in ('request', 'objective', 'forge')) != 1:
        raise J.ApiError('Supply exactly one explicit request, objective or frozen Forge binding.')
    mode = body.get('mode', 'mica')
    if mode not in MODES:
        raise J.ApiError('Unknown construction mode.')
    inventory = R.normalize_inventory(body.get('inventory', []))
    if any(row['node'] in ('host', 'workstation', 'standby') for row in inventory):
        raise J.ApiError('Only physical fleet workers are eligible for construction.')
    reuse = body.get('reuse_components', False)
    if type(reuse) is not bool:
        raise J.ApiError('reuse_components must be a boolean.')
    if 'forge' in body:
        from symblic.mica import forge as F
        forge = body['forge']
        if type(forge) is not dict or set(forge) != {'project', 'handoff', 'binding'}:
            raise J.ApiError('Forge construction requires exact project, handoff and executable binding fields.')
        if mode != 'mica' or reuse or any(k in body for k in ('budget', 'allowed_outputs', 'artifact_format', 'calibration')):
            raise J.ApiError('The frozen Forge binding owns its budget, output format and fixed plan; reuse and calibration are unsupported.')
        prepared = F.prepare(forge['project'], forge['handoff'], forge['binding'], db=_forge_store())
        task = {'kind': 'forge', 'prepared': prepared, 'request': prepared['request']}
    elif 'request' in body:
        if 'budget' in body or 'allowed_outputs' in body or 'artifact_format' in body:
            raise J.ApiError('The explicit request already fixes its budget, allowed outputs and artifact format.')
        task = {'kind': 'request', 'request': C.normalize_request(body['request'])}
    else:
        if 'budget' not in body:
            raise J.ApiError('Objective synthesis requires an explicit total budget.')
        objective = C._text(body['objective'], 'objective', 12000)
        artifact_format = body.get('artifact_format', 'javascript_script')
        if artifact_format not in FORMATS:
            raise J.ApiError('Choose javascript_script or javascript_modules.')
        outputs = C._strings(body.get('allowed_outputs', ['index.mjs'] if artifact_format == 'javascript_modules' else ['result.js']),
                             'allowed_outputs', nonempty=True)
        for name in outputs:
            C._path(name)
        if artifact_format == 'javascript_script' and len(outputs) != 1:
            raise J.ApiError('Script output requires exactly one file.')
        if artifact_format == 'javascript_modules' and any(not p.endswith(('.js', '.mjs')) or p == '__symblic_test__.mjs' for p in outputs):
            raise J.ApiError('Module output paths must use .js/.mjs and exclude the verifier name.')
        if any(a != b and b.startswith(a + '/') for a in outputs for b in outputs):
            raise J.ApiError('Allowed output files cannot be ancestors of one another.')
        task = {'kind': 'objective', 'objective': objective, 'budget': C._budget(body['budget']),
                'allowed_outputs': outputs, 'artifact_format': artifact_format}
    title = C._text(body.get('title', task.get('objective') or task['request']['objective']), 'title', 12000)[:160]
    result = {'version': VERSION, 'task': task, 'inventory': inventory, 'mode': mode,
              'title': title, 'reuse_components': reuse}
    if 'calibration' in body:
        from symblic.mica import search as M
        from symblic.mica import calibration as H
        # API callers supply the sealed bounded value; never scan server paths.
        result['calibration'] = H.normalize(body['calibration'], G._hash(M.implementation_identity()))
    pin = G._hash(result)
    if body.get('expected_sha256', pin) != pin:
        raise J.ApiError('The construction request differs from its checked version.', 409)
    key = body.get('idempotency_key')
    if key is not None and (type(key) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]{1,96}', key)):
        raise J.ApiError('Invalid idempotency key.')
    return result


def check(body):
    spec = _spec(body)
    return {'ok': True, 'spec': spec, 'sha256': G._hash(spec), 'scope': SCOPE,
            'eligible_snapshot': sum(row['ready'] and row['available'] for row in spec['inventory']),
            'admission': 'Live fleet fences and resource limits are checked separately before every launch.'}


def discover_inventory():
    """Read cached fleet facts only; this action never probes, wakes or launches."""
    import host_agents
    import host_fleet
    rows, diagnostics = [], []
    for node in host_fleet.nodes(refresh=False):
        ident = node['id']
        if ident in ('host', 'workstation', 'standby') or node.get('role') == 'cloud':
            continue
        caps = node.get('agents') or {}
        info = caps.get('ollama') or {}
        ready = (node.get('online') is True and not node.get('stale') and caps.get('online') is True
                 and info.get('installed') is True and info.get('login') is not False)
        available = (ready and node.get('power') != 'serving' and not node.get('guest_busy')
                     and not host_fleet._draining(ident)
                     and not host_agents.active_runs(node=ident, kind='ollama'))
        models = info.get('models') or []
        if not models or not ready:
            diagnostics.append({'node': ident, 'reason': 'Cached model/readiness facts are absent or stale.'})
        elif not available:
            diagnostics.append({'node': ident, 'reason': 'Cached readiness exists; capacity or power fence excludes this node.'})
        for model in models:
            if type(model) is not str or not model or 'embed' in model or model.startswith('symblic-ctx8192-'):
                continue
            rows.append({'engine': 'ollama', 'model': model, 'node': ident, 'digest': None,
                         'ready': ready, 'available': available})
    return {'inventory': R.normalize_inventory(rows), 'observed_at': time.time(),
            'diagnostics': diagnostics, 'source': 'cached_fleet_and_admission_records',
            'scope': 'Cached snapshot, not a reservation. Refresh the underlying probes on the host; every launch rechecks admission. Model digest and context capacity remain unknown until separately observed.'}


def unit(ident):
    return 'symblic-mica-' + ident


def _launch(ident, folder, generation):
    if not _host_ok():
        return {'ok': False, 'error': 'MICA workers are fenced to the configured fleet host.'}
    return _engine()._launch_unit(unit(ident), ['-m', 'integration.host.symblic_mica_api', 'job', '--id', ident,
                                             '--folder', str(folder), '--generation', generation])


launcher = {'launch': _launch, 'active': lambda ident: J.liveness(unit(ident)) != 'inactive',
            'stop': lambda ident: _engine()._systemd_stop(ident, unit(ident))}


def _open(ident):
    folder = _folder(ident)
    meta, frozen = _read(folder, 'meta.json'), _read(folder, 'frozen.json')
    if (meta.get('id') != ident or meta.get('frozen_sha256') != G._hash(frozen)
            or frozen.get('version') != VERSION or frozen.get('initial_action') not in ('plan', 'execute')
            or frozen.get('spec_sha256') != G._hash(frozen['spec'])):
        raise J.ApiError('Job metadata differs from the frozen construction.', 409)
    return folder, meta, frozen


def _launch_action(ident, folder, frozen, action):
    if action not in ('plan', 'execute'):
        raise J.ApiError('Unknown job action.')
    def launch(job_id, directory, generation):
        _put(Path(directory), 'launch-' + generation + '.json',
             {'generation': generation, 'action': action, 'frozen_sha256': G._hash(frozen)})
        return launcher['launch'](job_id, directory, generation)
    return J.launch_job(ident, folder, {**launcher, 'launch': launch})


def start(body, *, action='execute'):
    if action not in ('plan', 'execute'):
        raise J.ApiError('Unknown job action.')
    spec = _spec(body)
    if not any(row['ready'] and row['available'] for row in spec['inventory']):
        raise J.ApiError('No ready worker with available capacity in the explicit inventory.', 409)
    if not _host_ok():
        raise J.ApiError('Construction is available only on the configured fleet host.', 409)
    frozen = {'version': VERSION, 'spec': spec, 'spec_sha256': G._hash(spec),
              'initial_action': action, 'implementation': _implementation()}
    key = body.get('idempotency_key')
    key_hash = hashlib.sha256(key.encode()).hexdigest() if key is not None else None
    ident = key_hash[:12] if key_hash else secrets.token_hex(6)
    root = _root()
    with J._control(root):
        folder = root / ident
        if folder.exists() or folder.is_symlink():
            _, meta, prior = _open(ident)
            if key_hash is None or meta.get('idempotency_sha256') != key_hash or prior != frozen:
                raise J.ApiError('Idempotency key conflicts with an existing frozen job.', 409)
            return {'ok': True, 'id': ident, 'existing': True, 'scope': SCOPE}
        if sum(1 for _ in root.iterdir()) >= 5001:
            raise J.ApiError('MICA job registry is full; retain/export old evidence before creating more.', 409)
        PS._directory(folder, create=True)
        _put(folder, 'frozen.json', frozen)
        _put(folder, 'meta.json', {'id': ident, 'title': spec['title'], 'created': time.time(),
             'frozen_sha256': G._hash(frozen), 'idempotency_sha256': key_hash})
    _launch_action(ident, folder, frozen, action)
    return {'ok': True, 'id': ident, 'scope': SCOPE}


def _outcome(folder, generation, frozen):
    path = folder / ('outcome-' + generation + '.json')
    if not path.exists() and not path.is_symlink():
        return None
    receipt = _read(folder, path.name)
    if receipt.get('generation') != generation or receipt.get('frozen_sha256') != G._hash(frozen):
        raise J.ApiError('Worker outcome belongs to another frozen job.', 409)
    return receipt['result']


def view(ident):
    folder, meta, frozen = _open(ident)
    job = J.read_job(folder, missing=True)
    active = launcher['active'](ident) or J.worker_alive(folder)
    settling = J.stop_settling(folder)
    outcome = _outcome(folder, job['generation'], frozen) if job else None
    status = outcome.get('status') if outcome else job.get('status', 'lost')
    if not active and status in ('running', 'starting'):
        status = 'starting' if time.time() - job.get('updated', 0) < 30 else 'lost'
    terminal = status in ('done', 'unknown', 'blocked', 'exhausted', 'missing_decisions')
    return {'id': ident, 'meta': meta, 'status': status, 'active': active, 'job': job,
            'spec': frozen['spec'], 'result': outcome, 'error': job.get('error'), 'scope': SCOPE,
            'can_resume': not active and not settling and not terminal and status != 'planned',
            'can_execute': not active and not settling and status == 'planned',
            'audit_scope': 'sealed_job_receipts; native_journals_revalidated_on_execution'}


def list_runs():
    rows = []
    folders = [p for p in _root().iterdir() if _engine().ID_RX.fullmatch(p.name)]
    if len(folders) > 5000:
        raise J.ApiError('MICA registry exceeds its bounded listing size.', 409)
    for folder in sorted(folders, key=lambda p: p.lstat().st_mtime, reverse=True)[:200]:
        try:
            _, meta, frozen = _open(folder.name)
            job = J.read_job(folder, missing=True)
            outcome = _outcome(folder, job['generation'], frozen) if job else None
            control_status = job.get('status', 'lost')
            rows.append({**meta, 'status': outcome.get('status', control_status) if outcome else control_status,
                         'control_status': control_status,
                         'assurance': 'Sealed result status when retained; open the job for native evidence and current liveness.'})
        except (ValueError, OSError):
            rows.append({'id': folder.name, 'status': 'unavailable'})
    return rows


def resume(ident, *, execute=False):
    folder, _, frozen = _open(ident)
    current = view(ident)
    if current['status'] in ('done', 'unknown', 'blocked', 'exhausted', 'missing_decisions'):
        return {'ok': True, 'id': ident, 'terminal': True, 'status': current['status']}
    if current['active'] or J.stop_settling(folder):
        return {'ok': True, 'id': ident, 'already_active': True}
    job = J.read_job(folder, missing=True)
    previous = _read(folder, 'launch-' + job['generation'] + '.json') if job else {'action': 'execute'}
    action = 'execute' if execute else previous['action']
    if current['status'] == 'planned' and action == 'plan':
        return {'ok': True, 'id': ident, 'planned': True}
    if frozen['implementation'] != _implementation():
        raise J.ApiError('Construction implementation changed; this frozen job cannot be relabelled.', 409)
    return _launch_action(ident, folder, frozen, action)


def stop(ident):
    return J.stop_job(ident, _folder(ident), launcher)


def _verify_result(result, request, runtime, folder):
    from symblic.mica import search as M
    try:
        M.verify_result_artifacts(result, request, runtime)
        M.verify_host_costs(result, folder, runtime)
    except ValueError as error:
        raise J.ApiError(str(error), 409) from error


def artifacts(ident, *, include_text=False, include_archive=False):
    current = view(ident)
    result = current['result'] or {}
    rows = []
    if result.get('status') == 'done':
        from symblic.mica import search as M
        folder, _, frozen = _open(ident)
        task = frozen['spec']['task']
        runtime = frozen['implementation']['construction']
        if task['kind'] == 'objective':
            if type(result.get('child')) is not dict or type(result.get('request')) is not dict:
                raise J.ApiError('Project result lacks its accepted request or construction receipt.', 409)
            _verify_result(result['child'], result['request'], runtime, folder/'runtime'/'construction')
            if result.get('output') != result['child'].get('output') or result.get('bundle') != result['child'].get('bundle'):
                raise J.ApiError('Project artifacts differ from its construction receipt.', 409)
        else:
            if task['kind'] == 'forge':
                from symblic.mica import forge as F
                F.verify_result_origin(result, task['prepared'], folder/'runtime', frozen['spec']['inventory'], 'mica-' + ident)
            _verify_result(result, task['request'], runtime, folder/'runtime')
        if result.get('bundle') is not None:
            from symblic.mica import bundle as B
            bundle = result['bundle']
            B.verify_bundle(bundle, runtime_identity=runtime)
            checks = result.get('module_checks') or {}
            if checks.get('passed') is not True or checks.get('bundle_sha256') != bundle['sha256']:
                raise J.ApiError('Completed bundle lacks matching successful module checks.', 409)
            for file in bundle['files']:
                row = {'file': file['path'], 'sha256': file['sha256'], 'bytes': file['utf8_bytes'],
                       'role': file['role'], 'assurance': result.get('assurance'), 'provenance': result.get('provenance')}
                if include_text:
                    row['text'] = file['text']
                rows.append(row)
            response = {'id': ident, 'status': current['status'], 'artifacts': rows,
                        'bundle_sha256': bundle['sha256'], 'scope': SCOPE}
            if include_archive:
                raw = B.archive(bundle)
                response['archive'] = {'file': 'symblic-modules.zip', 'mime_type': 'application/zip',
                                       'sha256': hashlib.sha256(raw).hexdigest(),
                                       'bytes': len(raw), 'base64': base64.b64encode(raw).decode('ascii')}
            return response
        if include_archive:
            raise J.ApiError('ZIP export requires a completed JavaScript module bundle.')
        output = result.get('output')
        if (type(output) is not dict or type(output.get('text')) is not str
                or output.get('sha256') != hashlib.sha256(output['text'].encode()).hexdigest()):
            raise J.ApiError('Artifact bytes differ from the retained digest.', 409)
        row = {'file': output['file'], 'sha256': output['sha256'], 'bytes': len(output['text'].encode()),
               'assurance': result.get('assurance'), 'provenance': result.get('provenance')}
        if include_text:
            row['text'] = output['text']
        rows.append(row)
    return {'id': ident, 'status': current['status'], 'artifacts': rows, 'scope': SCOPE}


def run_job(folder, *, applicators, stop_event=None, generation=None, runtime_factory=None, project_factory=None, forge_factory=None):
    """Explicit worker entry, with injected host interfaces in isolated tests."""
    if not _host_ok():
        return {'status': 'not_started', 'reason': 'worker_host_fence'}
    folder = Path(folder)
    canonical, _, frozen = _open(folder.name)
    if folder.absolute() != canonical.absolute():
        raise J.ApiError('Worker folder differs from the private job registry.', 409)
    event = stop_event if stop_event is not None else threading.Event()
    stopped, generation = J.begin_job(folder, generation, event, final=False)
    if stopped is None:
        return {'status': 'not_started', 'reason': 'canceled, superseded or already running'}
    try:
        launch = _read(folder, 'launch-' + generation + '.json')
        if (launch.get('generation') != generation or launch.get('frozen_sha256') != G._hash(frozen)
                or launch.get('action') not in ('plan', 'execute')):
            raise J.ApiError('Worker action differs from its reserved generation.', 409)
        if frozen['implementation'] != _implementation():
            raise J.ApiError('Construction implementation changed after this job was frozen.', 409)
        spec, task = frozen['spec'], frozen['spec']['task']
        library = _root() / '_components' if spec['reuse_components'] else None
        options = {'calibration': spec['calibration']} if 'calibration' in spec else {}
        if task['kind'] == 'forge':
            if forge_factory is None:
                from symblic.mica.forge import ForgeMicaRun
                forge_factory = ForgeMicaRun
            if (spec['mode'] != 'mica' or library is not None or options or
                    task['request'] != task['prepared']['request'] or
                    task['prepared']['origin']['identity'] != frozen['implementation']['forge_adapter']):
                raise J.ApiError('Forge worker controls differ from the frozen accepted binding.', 409)
            run = forge_factory(task['prepared'], folder/'runtime', applicators, spec['inventory'],
                                db=_forge_store(), request_id='mica-' + folder.name, stop=stopped)
        elif task['kind'] == 'objective':
            if project_factory is None:
                from symblic.mica.project import MicaProject
                project_factory = MicaProject
            if task.get('artifact_format', 'javascript_script') != 'javascript_script':
                options['artifact_format'] = task['artifact_format']
            run = project_factory(task['objective'], folder/'runtime', applicators, spec['inventory'],
                                  task['budget'], task['allowed_outputs'], stop=stopped, library=library, **options)
        else:
            if runtime_factory is None:
                from symblic.mica.search import MicaRun
                runtime_factory = MicaRun
            run = runtime_factory(task['request'], folder/'runtime', applicators, spec['inventory'],
                                  stop=stopped, library=library, **options)
        with stopped.fence():
            already_stopped = stopped.is_set()
        if already_stopped:
            J.finish_job(folder, generation, 'stopped')
            return {'status': 'stopped'}
        if task['kind'] == 'forge':
            result = run.plan() if launch['action'] == 'plan' else run.execute()
        else:
            result = run.plan(mode=spec['mode']) if launch['action'] == 'plan' else run.execute(mode=spec['mode'])
        with stopped.fence():
            _put(folder, 'outcome-' + generation + '.json',
                 {'generation': generation, 'frozen_sha256': G._hash(frozen), 'result': result})
        status = result.get('status')
        control_status = ('done' if status in ('done', 'planned') else 'unresolved' if status == 'unknown'
                          else 'stopped' if status == 'stopped' or stopped.is_set() else 'failed')
        J.finish_job(folder, generation, control_status, reserved_calls=result.get('calls'))
        return result
    except G.Superseded:
        return {'status': 'superseded'}
    except Exception as error:
        J.finish_job(folder, generation, 'stopped' if stopped.is_set() else 'failed', str(error)[:1000])
        raise
    finally:
        stopped.release()


def handle(handler, method, route, data):
    if not route.startswith('mica/'):
        return False
    if not handler.identity().is_owner:
        handler.send_json({'error': 'Owner access is required.'}, 403)
        return True
    try:
        if method == 'POST' and type(data) is not dict:
            raise J.ApiError('Request body must be an object.')
        if method == 'GET' and route == 'mica/capabilities':
            from symblic.mica.bench import MODE_FACTORS
            value = {'version': VERSION, 'modes': list(MODES), 'mode_factors': MODE_FACTORS,
                     'language': 'javascript', 'task_sources': ['objective', 'request', 'forge'],
                     'forge': 'Accepted frozen pure-function handoff plus explicit finite bindings; fixed original units, no automatic acceptance.',
                     'budget_defaults': C.DEFAULT_BUDGET,
                     'budget_limits': C.BUDGET_LIMITS, 'artifact_formats': list(FORMATS),
                     'calibration': 'Optional sealed snapshot object; exact checker identity, no server path scan or automatic history discovery.',
                     'archive': 'Explicit artifacts?archive=1 returns a verified module bundle as deterministic base64 ZIP; no host output writes.',
                     'scope': SCOPE}
        elif method == 'GET' and route == 'mica/inventory': value = discover_inventory()
        elif method == 'POST' and route == 'mica/check': value = check(data)
        elif method == 'POST' and route in ('mica/run', 'mica/plan'):
            value = start(data, action='plan' if route.endswith('/plan') else 'execute')
        elif method == 'GET' and route == 'mica/runs': value = {'runs': list_runs()}
        elif method == 'GET' and route == 'mica/run': value = view(handler.get_query_param('id'))
        elif method == 'POST' and route in ('mica/resume', 'mica/execute'):
            value = resume(data.get('id'), execute=route.endswith('/execute'))
        elif method == 'POST' and route == 'mica/stop': value = stop(data.get('id'))
        elif method == 'GET' and route == 'mica/artifacts':
            value = artifacts(handler.get_query_param('id'), include_text=handler.get_query_param('text') == '1',
                              include_archive=handler.get_query_param('archive') == '1')
        else: return False
        handler.send_json(value)
    except ImportError:
        handler.send_json({'error': 'MICA needs the server update and restart.'}, 503)
    except (ValueError, OSError) as error:
        handler.send_json({'error': str(error)}, getattr(error, 'status', 400))
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['job'])
    parser.add_argument('--id', required=True)
    parser.add_argument('--folder', required=True)
    parser.add_argument('--generation', required=True)
    args = parser.parse_args()
    if not _host_ok():
        parser.exit(3, 'MICA worker host fence refused this process.\n')
    if (not _engine().ID_RX.fullmatch(args.id) or Path(args.folder).name != args.id
            or Path(args.folder).absolute() != _folder(args.id).absolute()):
        parser.error('Invalid MICA job identity or private folder.')
    from symblic.providers.applicators import Applicators
    apps = Applicators(owner_label='owner (Symblic MICA ' + args.id + ')', run_id='mica-' + args.id,
                       allow_web=False, thermal=True)
    event = threading.Event()
    def interrupt(_signal, _frame):
        event.set()
        apps.cancel_all()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        run_job(args.folder, applicators=apps, stop_event=event, generation=args.generation)
    finally:
        apps.cancel_all()


if __name__ == '__main__':
    main()
