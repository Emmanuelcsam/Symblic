"""HOST-ONLY: the host's graph-policy experiment routes and jobs; needs its graph-job store and systemd units.

Why it is host-only: experiments run as host graph jobs (integration/host/symblic_graph_api.py) in transient
systemd units under the host's private store. The policy learning itself is pure: symblic/policy/.


Inputs and evaluator-owned expected outputs freeze before any dispatch. Selection
sees training only; heldout comparison cannot modify it. No worker starts on import.
"""
from __future__ import annotations

import fcntl
import hashlib
import heapq
import json
import os
import secrets
import signal
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

from integration.host import symblic_graph_api as A
from symblic.graph import run as R
from symblic.policy import learning as P
from symblic.policy import store as PS

SCOPE = ('Finite routing candidate selection with exact declared outcomes. '
         'A selected policy applies only when explicitly copied into a future graph; ongoing runs keep their pins.')


def runtime_identity():
    """Verify current loaded native implementation before pinning experiment work."""
    from symblic.kernel import execution_pins as X
    files = {name: hashlib.sha256(X._read(name)).hexdigest()
             for name in sorted(X.PYTHON_FILES | X.LIBRARY_FILES.keys()) if (X.BASE / name).is_file()}
    pins = X.build('show 0.', {}, files)
    return {'kind': 'graph_policy_native_runtime_v1', 'kernel': pins['kernel_id'],
            'files': files, 'execution_sha256': pins['sha256']}


def _root(*, create=True):
    path = Path(A._engine().root()) / 'policies'
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    if path.exists() or path.is_symlink():
        PS._directory(path)
    return path


def _folder(ident):
    if type(ident) is not str or not A._engine().ID_RX.fullmatch(ident):
        raise A.ApiError('No such policy experiment.', 404)
    folder = _root() / ident
    if folder.is_symlink() or not folder.is_dir():
        raise A.ApiError('No such policy experiment.', 404)
    return folder


def unit(ident):
    return 'symblic-policy-' + ident


def _launch(ident, folder, generation):
    return A._engine()._launch_unit(unit(ident), ['-m', 'integration.host.symblic_policy_api', 'job', '--id', ident,
                                                '--folder', str(folder), '--generation', generation])


def _active(ident):
    u = unit(ident)
    if callable(getattr(A, 'liveness', None)):
        return A.liveness(u) in ('active', 'unknown')
    return bool(A._engine()._systemd_active(ident, u))


def liveness(ident):
    u = unit(ident)
    if callable(getattr(A, 'liveness', None)):
        return A.liveness(u)
    return 'active' if A._engine()._systemd_active(ident, u) else 'stopped'


launcher = {'launch': _launch,
            'active': _active,
            'stop': lambda ident: A._engine()._systemd_stop(ident, unit(ident)),
            'liveness': liveness}


def example():
    base = A.example()
    training_graph = base['graph']
    heldout_graph = json.loads(json.dumps(training_graph))
    heldout_graph['id'] = 'HeldoutDouble'
    heldout_graph['nodes'][0]['source'] = 'use profile=verified.\nlet answer = 9.\nshow answer.'
    heldout_graph['nodes'][0]['checks'] = ['answer = 9']
    heldout_graph['nodes'][0]['contract'] = 'The declared heldout input is nine units.'
    heldout_graph['nodes'][0]['assumptions'] = ['Nine is an owner-supplied example value.']
    return {'title': 'Routing experiment example', 'candidates': [base['policy']], 'baseline_index': 0,
            'training': [{'family': 'example-six', 'input': {'graph': training_graph, 'output_node': 'Double'}, 'expected': 12}],
            'heldout': [{'family': 'example-nine', 'input': {'graph': heldout_graph, 'output_node': 'Double'}, 'expected': 18}],
            'budget': {'max_calls': 2, 'max_cost_units': 2},
            'objective': {'max_score': 1, 'score_weight': 100, 'call_weight': 1, 'cost_weight': 0,
                          'unknown_cost': 'reject', 'tie_break': 'policy_sha256_ascending', 'min_heldout_gain': 1}}


MAX_REGISTRY_ENTRIES = 5000
MAX_REGISTRY_ROOT_ENTRIES = 15032


@contextmanager
def _heldout_lock(root_dir):
    PS._directory(root_dir)
    fd = os.open(root_dir / '.heldout_registry.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise A.ApiError('Invalid held-out registry lock.', 409)
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _heldout_registry_path(root_dir=None):
    return (root_dir if root_dir is not None else _root()) / '.heldout_registry.json'


def _registry(reg):
    """A finite append-only exposure index; legacy rows remain readable."""
    P._scan(reg)
    if type(reg) is not list or len(reg) > MAX_REGISTRY_ENTRIES:
        raise A.ApiError('Held-out registry capacity reached; history was retained.', 409)
    seen = set()
    for row in reg:
        if (type(row) is not dict or set(row) != {'experiment', 'cases', 'families', 'inputs', 'exposures'}
                or type(row['experiment']) is not str or not A._engine().ID_RX.fullmatch(row['experiment'])
                or row['experiment'] in seen):
            raise A.ApiError('Held-out registry format is invalid.', 409)
        seen.add(row['experiment'])
        for field in ('cases', 'families', 'inputs', 'exposures'):
            values = row[field]
            maximum = P.MAX_CASES * P.MAX_CASES if field == 'exposures' else P.MAX_CASES
            if type(values) is not list or len(values) > maximum:
                raise A.ApiError('Held-out registry format is invalid.', 409)
            for value in values:
                PS._sha(value)
        if not row['cases'] or not len(row['cases']) == len(row['families']) == len(row['inputs']):
            raise A.ApiError('Held-out registry format is invalid.', 409)
    return reg


def _registry_row(ident, cases):
    P._cases(cases)
    return {'experiment': ident, 'cases': [c['case_hash'] for c in cases],
            'families': [c['family_hash'] for c in cases], 'inputs': [c['input_hash'] for c in cases],
            'exposures': [value for c in cases for value in c['exposure_hashes']]}


def _write_heldout_registry_durable(root_dir, reg):
    _registry(reg)  # refuse capacity before replacing; never truncate prior exposure
    raw = json.dumps(reg, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(raw) > PS.MAX_FILE:
        raise A.ApiError('Held-out registry byte capacity reached; history was retained.', 409)
    R._write_file(root_dir, '.heldout_registry.json', raw)


def _reconciled_row(folder):
    """Recover a freeze published before its registry update, with its exact pins."""
    PS._directory(folder)
    manifest = PS._read(folder / 'frozen.json')
    PS._fields(manifest, 'version selector_version experiment scorer cost_unit implementation host_identity files')
    if (manifest['experiment'] != folder.name or type(manifest['version']) is not int
            or manifest['version'] != PS.VERSION or type(manifest['selector_version']) is not int
            or manifest['selector_version'] != P.VERSION or manifest['scorer'] != PS.SCORER):
        raise A.ApiError('Frozen held-out experiment identity is invalid.', 409)
    if (folder / 'meta.json').exists():
        meta = R._read(folder / 'meta.json')
        if type(meta) is not dict or meta.get('id') != folder.name or meta.get('freeze_sha256') != P.digest(manifest):
            raise A.ApiError('Frozen held-out experiment metadata differs.', 409)
    files = manifest['files']
    if type(files) is not dict or set(files) != {'training-plan.json', 'heldout-plan.json', 'training-cases.json', 'heldout-cases.json'}:
        raise A.ApiError('Frozen held-out experiment files are invalid.', 409)
    for value in files.values():
        PS._sha(value)
    plan, hp = PS._read(folder / 'training-plan.json'), PS._read(folder / 'heldout-plan.json')
    if P.digest(plan) != files['training-plan.json'] or P.digest(hp) != files['heldout-plan.json']:
        raise A.ApiError('Frozen held-out plan differs from its manifest.', 409)
    P._plan(plan)
    PS._fields(hp, 'version training_plan_hash cases')
    if type(hp['version']) is not int or hp['version'] != P.VERSION or hp['training_plan_hash'] != P.digest(plan):
        raise A.ApiError('Frozen held-out plan identity is invalid.', 409)
    P.validate_split(plan['cases'], hp['cases'])
    return _registry_row(folder.name, hp['cases'])


def _reconcile_and_read_heldout_registry(root_dir):
    path = _heldout_registry_path(root_dir)
    try:
        reg = _registry(PS._read(path)) if path.exists() or path.is_symlink() else []
    except (ValueError, OSError) as error:
        raise A.ApiError('Heldout registry is corrupt or exceeds its finite limits.', 500) from error
    seen = {row['experiment'] for row in reg}
    reconciled = False
    with os.scandir(root_dir) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_REGISTRY_ROOT_ENTRIES:
                raise A.ApiError('Held-out registry directory capacity reached; history was retained.', 409)
            if not A._engine().ID_RX.fullmatch(entry.name) or not entry.is_dir(follow_symlinks=False):
                continue
            folder = Path(entry.path)
            if entry.name not in seen and (folder / 'frozen.json').exists():
                if len(reg) >= MAX_REGISTRY_ENTRIES:
                    raise A.ApiError('Held-out registry capacity reached; history was retained.', 409)
                reg.append(_reconciled_row(folder))
                seen.add(entry.name)
                reconciled = True
                _registry(reg)  # cumulative structure/byte bounds apply during recovery
    if reconciled:
        _write_heldout_registry_durable(root_dir, reg)
    return reg


def _reuse(reg, heldout_fixtures, current_ident=None):
    current = _registry_row(current_ident or '0' * 12, [c['case'] for c in heldout_fixtures])
    names = ('cases', 'families', 'inputs', 'exposures')
    resources = {value for key in names for value in current[key]}
    return sorted({row['experiment'] for row in reg if row['experiment'] != current_ident
                   and resources.intersection(value for key in names for value in row[key])})


def _find_heldout_reuse(heldout_fixtures, current_ident=None):
    root_dir = _root(create=False)
    if not root_dir.exists():
        return []
    with _heldout_lock(root_dir):
        return _reuse(_reconcile_and_read_heldout_registry(root_dir), heldout_fixtures, current_ident)


def _reserve_heldout_use(ident, heldout_fixtures, *, acknowledge):
    """Atomic check-and-reserve before freeze/launch. Failed starts retain the reservation.

    A reservation conservatively records possible exposure, not proof that a model
    or held-out evaluation ran. It is never silently removed after an interruption.
    """
    if type(acknowledge) is not bool:
        raise A.ApiError('acknowledge_heldout_reuse must be a boolean.')
    root_dir = _root()
    with _heldout_lock(root_dir):
        reg = _reconcile_and_read_heldout_registry(root_dir)
        prior = _reuse(reg, heldout_fixtures, ident)
        if prior and not acknowledge:
            raise A.ApiError('Held-out cases have prior experiment reservations or uses. Check and acknowledge held-out reuse.', 409)
        row = _registry_row(ident, [c['case'] for c in heldout_fixtures])
        existing = next((item for item in reg if item['experiment'] == ident), None)
        if existing is not None and existing != row:
            raise A.ApiError('Held-out reservation identity differs.', 409)
        if existing is None:
            _write_heldout_registry_durable(root_dir, reg + [row])
        return prior


def prepare(body, *, for_start=False):
    from symblic.policy.graph import validate_case
    allowed_keys = {'title', 'candidates', 'baseline_index', 'training', 'heldout',
                    'budget', 'objective', 'expected_plan_hash', 'acknowledge_heldout_reuse'}
    if type(body) is not dict or set(body) - allowed_keys:
        raise A.ApiError('Supply candidates, baseline_index, training, heldout, budget and objective.')
    P._scan(body)
    if 'acknowledge_heldout_reuse' in body and type(body['acknowledge_heldout_reuse']) is not bool:
        raise A.ApiError('acknowledge_heldout_reuse must be a boolean.')
    candidates = body.get('candidates')
    if type(candidates) is not list or not 1 <= len(candidates) <= P.MAX_CANDIDATES:
        raise A.ApiError('Supply a bounded nonempty list of candidate routing policies.')
    candidate_hashes = []
    seen_candidates = set()
    for candidate in candidates:
        ch = P.digest(candidate)
        if ch in seen_candidates:
            raise A.ApiError('Candidate policies must be unique.')
        seen_candidates.add(ch)
        candidate_hashes.append(ch)
    baseline = body.get('baseline_index', 0)
    if type(baseline) is not int or not 0 <= baseline < len(candidates):
        raise A.ApiError('baseline_index must name a candidate.')
    training_rows = body.get('training')
    heldout_rows = body.get('heldout')
    if type(training_rows) is not list or not 1 <= len(training_rows) <= P.MAX_CASES:
        raise A.ApiError('Both training and heldout need nonempty case lists.')
    if type(heldout_rows) is not list or not 1 <= len(heldout_rows) <= P.MAX_CASES:
        raise A.ApiError('Both training and heldout need nonempty case lists.')
    if len(training_rows) * len(candidates) > P.MAX_ASSIGNMENTS:
        raise A.ApiError('The training cases and candidate count exceed MAX_ASSIGNMENTS.')
    budget = body.get('budget')
    if type(budget) is not dict or set(budget) != {'max_calls', 'max_cost_units'}:
        raise A.ApiError('Supply a budget with max_calls and max_cost_units.')
    for v in budget.values():
        if type(v) is not int or not 0 <= v <= P.MAX_INT:
            raise A.ApiError('Budget values must be integers.')
    assignments = len(candidates) * len(training_rows) + min(2, len(candidates)) * len(heldout_rows)
    cap = assignments * budget['max_calls']
    if cap > 10000:
        raise A.ApiError('This experiment exceeds the web job limit of 10,000 reserved provider calls.')
    objective = body.get('objective')
    if type(objective) is not dict:
        raise A.ApiError('Supply an objective.')
    fixtures = {}
    freeze_cache = {}
    for stage, rows in (('training', training_rows), ('heldout', heldout_rows)):
        fixtures[stage] = []
        for row in rows:
            if type(row) is not dict or set(row) - {'family', 'input', 'expected', 'exposure_hashes'} or not {'family','input','expected'} <= row.keys():
                raise A.ApiError('Each case needs family, input and expected; exposure_hashes is optional.')
            if type(row['family']) is not str or not row['family'].strip():
                raise A.ApiError('Each case needs an explicit family identity.')
            input_digest = P.digest(row['input'])
            for candidate, ch in zip(candidates, candidate_hashes):
                cache_key = (input_digest, ch)
                if cache_key in freeze_cache:
                    continue
                frozen = validate_case(row['input'], candidate, budget=budget)
                A._freeze({'graph': frozen['graph'], 'policy': frozen['policy']})
                freeze_cache[cache_key] = True
            fixtures[stage].append(PS.case_fixture(row['input'], row['expected'], family_hash=P.digest(row['family']),
                                                 exposure_hashes=row.get('exposure_hashes', [])))
    plan = {'version': P.VERSION, 'candidates': [{'sha256': ch, 'policy': p} for ch, p in zip(candidate_hashes, candidates)],
            'baseline': candidate_hashes[baseline], 'cases': [f['case'] for f in fixtures['training']],
            'budget': budget, 'objective': objective}
    P._plan(plan)
    hp = {'version': P.VERSION, 'training_plan_hash': P.digest(plan), 'cases': [f['case'] for f in fixtures['heldout']]}
    P.validate_split(plan['cases'], hp['cases'])
    prior_uses = _find_heldout_reuse(fixtures['heldout'])
    ack = body.get('acknowledge_heldout_reuse', False)
    if for_start and prior_uses and not ack:
        raise A.ApiError('Held-out evaluation set reuses cases from ' + str(len(prior_uses)) +
                         ' prior experiment(s) (' + ', '.join(prior_uses) + '). Acknowledge held-out reuse to proceed.')
    identity = P.digest({'training': plan, 'heldout': hp})
    if 'expected_plan_hash' in body and body['expected_plan_hash'] != identity:
        raise A.ApiError('The experiment differs from the checked version. Check it again.', 409)
    check_receipt = {'ok': True, 'plan_hash': identity, 'candidates': len(candidates),
                     'training_cases': len(fixtures['training']), 'heldout_cases': len(fixtures['heldout']),
                     'max_assignments': assignments, 'max_provider_calls': cap, 'cost_unit': 'provider_calls',
                     'prior_heldout_uses': prior_uses, 'scope': SCOPE}
    return plan, hp, fixtures, check_receipt


def check(body):
    return prepare(body, for_start=False)[3]


def _open(ident):
    folder = _folder(ident)
    meta = R._read(folder / 'meta.json')
    if type(meta) is not dict or meta.get('id') != ident:
        raise A.ApiError('Invalid experiment metadata.', 409)
    PS._sha(meta.get('freeze_sha256'))
    return PS.PolicyExperiment(folder.parent, ident, expected_freeze_hash=meta['freeze_sha256']), meta


def start(body):
    plan, hp, fixtures, checked = prepare(body, for_start=True)
    ident = secrets.token_hex(6)
    host = runtime_identity()
    prior_uses = _reserve_heldout_use(ident, fixtures['heldout'], acknowledge=body.get('acknowledge_heldout_reuse', False))
    checked = {**checked, 'prior_heldout_uses': prior_uses}
    exp = PS.PolicyExperiment.freeze(_root(), ident, plan, hp, fixtures['training'], fixtures['heldout'], cost_unit='provider_calls',
                                     host_identity=host)
    A._save(exp.path, 'meta.json', {'id': ident, 'title': str(body.get('title') or 'Routing experiment')[:120],
                                  'created': time.time(), 'freeze_sha256': exp.freeze_hash, 'checked': checked,
                                  'prior_heldout_uses': prior_uses})
    A.launch_job(ident, exp.path, launcher)
    return {'id': ident, 'freeze_sha256': exp.freeze_hash}


def audit_runtime(exp, stages=('training',)):
    """Verify completed graph receipts still match each store-owned outcome."""
    from symblic.policy.graph import GraphPolicyRunner
    runner = GraphPolicyRunner(exp.path / 'graph-runtime', A.NoDispatch())
    for stage in stages:
        for assignment in exp.assignments(stage):
            if assignment['state'] != 'terminal':
                continue
            folder = exp.path / ('assignment-' + assignment['assignment_id'])
            result = PS._read(folder / 'result.json')
            request = PS._read(folder / 'intent.json')
            actual = runner.resolve(request)
            expected = PS._read(folder / result['outcome_file'])
            if P.digest(actual) != P.digest(expected):
                raise A.ApiError('Native graph evidence differs from the experiment outcome.', 409)


def view(ident, *, audit=True):
    exp, meta = _open(ident)
    active = bool(launcher['active'](ident)) or A.worker_alive(exp.path)
    settling = A.stop_settling(exp.path)
    job = A.read_job(exp.path, missing=True) or {}
    try:
        state = exp.status(audit_implementation=audit)
        if audit:
            exp.assert_host_identity(runtime_identity())
        if audit:
            audit_runtime(exp, ('training', 'heldout') if state['stage'] == 'evaluated' else ('training',))
        status = 'done' if state['stage'] == 'evaluated' else job.get('status', 'lost')
        if status in ('running', 'starting') and not active and time.time()-job.get('updated', 0) >= 30:
            status = 'lost'
        can_resume = not active and not settling and status != 'done'
        resume_error = None
        if can_resume and audit:
            from symblic.policy.graph import GraphPolicyRunner
            grunner = GraphPolicyRunner(exp.path / 'graph-runtime', A.NoDispatch())
            stages_to_check = ['training']
            if (exp.path / 'selection.json').exists():
                stages_to_check.append('heldout')
            for stage in stages_to_check:
                for asgn in exp.assignments(stage, require_current_implementation=False):
                    if asgn['state'] == 'inflight':
                        folder = exp.path / ('assignment-' + asgn['assignment_id'])
                        if (folder / 'intent.json').is_file():
                            req = PS._read(folder / 'intent.json')
                            rec, reason = grunner.is_recoverable(req)
                            if not rec:
                                can_resume = False
                                resume_error = reason
                                break
                if not can_resume:
                    break
        err = resume_error or job.get('error')
        assurance = state.get('assurance', 'verified' if audit else 'recorded')
        return {'id': ident, 'meta': meta, 'state': state, 'status': status, 'active': active,
                'assurance': assurance,
                'error': err, 'can_resume': can_resume, 'scope': SCOPE}
    except (ValueError, OSError) as error:
        return {'id': ident, 'meta': meta, 'state': {}, 'status': 'unavailable', 'active': active,
                'error': str(error), 'can_resume': False, 'scope': SCOPE}


def list_runs():
    """Recorded metadata only; never replay assignments or inspect graph journals."""
    rows = []
    newest = []
    with os.scandir(_root()) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_REGISTRY_ROOT_ENTRIES:
                raise A.ApiError('Experiment directory capacity reached.', 409)
            if not A._engine().ID_RX.fullmatch(entry.name) or not entry.is_dir(follow_symlinks=False):
                continue
            item = (entry.stat(follow_symlinks=False).st_mtime_ns, entry.name, Path(entry.path))
            heapq.heappush(newest, item)
            if len(newest) > 200:
                heapq.heappop(newest)
    for _stamp, _name, folder in sorted(newest, reverse=True):
        try:
            meta = R._read(folder / 'meta.json')
            if type(meta) is not dict or meta.get('id') != folder.name:
                raise A.ApiError('Invalid experiment metadata.', 409)
            PS._sha(meta.get('freeze_sha256'))
            job = A.read_job(folder, missing=True) or {}
            status = job.get('status', 'lost')
            if status in ('running', 'starting') and not (launcher['active'](folder.name) or A.worker_alive(folder)):
                status = 'starting' if time.time() - job.get('updated', 0) < 30 else 'lost'
            rows.append({**meta, 'status': status, 'error': job.get('error'),
                         'assurance': 'Recorded status; open the experiment for an explicit audit.'})
        except (ValueError, OSError) as error:
            rows.append({'id': folder.name, 'title': folder.name, 'status': 'unavailable', 'error': str(error)[:300]})
    return rows


def resume(ident):
    exp, _meta = _open(ident)
    current = view(ident)
    if current['status'] == 'done':
        return {'ok': True, 'id': ident, 'terminal': True}
    if not current.get('can_resume', True) or current['status'] == 'unavailable':
        raise A.ApiError(current['error'] or 'This experiment cannot resume.', 409)
    return A.launch_job(ident, exp.path, launcher)


def stop(ident):
    exp, _meta = _open(ident)
    return A.stop_job(ident, exp.path, launcher)


def selected(ident):
    exp, _meta = _open(ident)
    exp.assert_host_identity(runtime_identity())
    receipt = exp.selection()
    audit_runtime(exp)
    chosen = receipt['selected']
    policy = json.loads(chosen['policy_json'])
    if P.digest(policy) != chosen['sha256']:
        raise A.ApiError('Selected policy identity differs.', 409)
    return {'id': ident, 'freeze_sha256': exp.freeze_hash, 'policy': policy,
            'policy_hash': chosen['sha256'], 'selection': receipt, 'scope': SCOPE}


def run_job(folder, *, applicators, stop_event=None, generation=None):
    from symblic.policy.graph import GraphPolicyRunner, Interrupted
    folder = Path(folder)
    meta = R._read(folder / 'meta.json')
    exp = PS.PolicyExperiment(folder.parent, folder.name, expected_freeze_hash=meta['freeze_sha256'])
    event = stop_event if stop_event is not None else threading.Event()
    try:
        stopped, generation = A.begin_job(folder, generation, event, final=False)
    except TypeError:
        stopped, generation = A.begin_job(folder, generation, event)
    if stopped is None:
        return {'status': 'not_started', 'reason': 'canceled, completed or superseded launch'}
    try:
        runner = GraphPolicyRunner(folder / 'graph-runtime', applicators, stop=stopped)
        exp.assert_host_identity(runtime_identity())
        for stage in ('training', 'heldout'):
            for assignment in exp.assignments(stage):
                if stopped.is_set():
                    A.finish_job(folder, generation, 'stopped')
                    return exp.status()
                exp.assert_host_identity(runtime_identity())
                if assignment['state'] == 'terminal':
                    continue
                args = (stage, assignment['candidate_sha256'], assignment['case_hash'])
                if assignment['state'] == 'inflight':
                    exp.reconcile_assignment(*args, resolver=runner.recover)
                else:
                    exp.run_assignment(*args, runner=runner)
            if stopped.is_set():
                A.finish_job(folder, generation, 'stopped')
                return exp.status()
            (exp.seal_training if stage == 'training' else exp.seal_heldout)()
        A.finish_job(folder, generation, 'done')
        return exp.status()
    except (Interrupted, Exception) as error:
        if stopped.is_set() or isinstance(error, Interrupted) or str(error) == 'stopped':
            A.finish_job(folder, generation, 'stopped')
            return exp.status()
        A.finish_job(folder, generation, 'failed', str(error)[:1000])
        raise
    finally:
        # A traceback may retain JobStop after any exception, including during
        # runner construction. Never leave generation ownership to finalization.
        stopped.release()


def handle(handler, method, route, data):
    if not route.startswith('policy/'):
        return False
    if not handler.identity().is_owner:
        handler.send_json({'error': 'Owner access is required.'}, 403)
        return True
    try:
        if method == 'POST' and type(data) is not dict:
            raise A.ApiError('Request body must be an object.')
        if method == 'GET' and route == 'policy/example': value = example()
        elif method == 'GET' and route == 'policy/runs': value = {'runs': list_runs()}
        elif method == 'GET' and route == 'policy/run':
            audit_param = handler.get_query_param('audit')
            value = view(handler.get_query_param('id'), audit=(audit_param not in ('0', 'false')))
        elif method == 'GET' and route == 'policy/selected': value = selected(handler.get_query_param('id'))
        elif method == 'POST' and route == 'policy/check': value = check(data)
        elif method == 'POST' and route == 'policy/run': value = start(data)
        elif method == 'POST' and route == 'policy/resume': value = resume(data.get('id'))
        elif method == 'POST' and route == 'policy/stop': value = stop(data.get('id'))
        else: return False
        handler.send_json(value)
    except ImportError:
        handler.send_json({'error': 'The policy experiment bridge needs the server update and restart.'}, 503)
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
    if not A._engine().ID_RX.fullmatch(args.id) or Path(args.folder).name != args.id:
        parser.error('invalid policy job identity')
    from symblic.providers.applicators import Applicators
    apps = Applicators(owner_label='operator (Symblic policy ' + args.id + ')',
                       run_id='policy-' + args.id, allow_web=False, thermal=True)
    stopped = threading.Event()
    def cancel(_signum, _frame):
        stopped.set()
        apps.cancel_all()
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    run_job(args.folder, applicators=apps, stop_event=stopped, generation=args.generation)


if __name__ == '__main__':
    main()
