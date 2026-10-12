"""MICA benchmark: frozen six-mode evaluations graded by evaluator-owned hidden JavaScript tests.

What it is for
    Freezes every public request, hidden case, mode/repeat assignment, budget and implementation identity before
    the first construction, runs each assignment once through an injected runner, grades the result with hidden
    tests the construction never saw, and reports every assignment in the denominator (unknown and failed ones
    included).

Status: measured machinery (tested with fake runners). No mode comparison result is claimed.

Depends on: symblic.bench.eval_protocol, symblic.policy.store (private immutable files), symblic.js.check,
contracts.py, bundle.py, checkpack_link.py. Run by cli.py (`benchmark`, `report`).

Details
    Frozen six-mode MICA evaluations, with evaluator-owned hidden JavaScript tests.

    No provider or worker is started here. The host injects a trusted runner; it receives
    only the public request and declared controls. The host retains the freeze hash.
    Unknown dispatches are never replayed. Hashes establish integrity relative to that
    pin, not authentication against the host. Repeated cases are not independent trials.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import fcntl
import hashlib
import json
import math
import os
import stat
from collections import Counter
from contextlib import contextmanager
from itertools import combinations
from pathlib import Path

from symblic.bench import eval_protocol as E
from symblic.policy import store as S

from symblic.mica import contracts as C

VERSION = 1
MODES = ('direct', 'static', 'decompose_on_failure', 'capability', 'search', 'mica')
MODE_FACTORS = {
    'direct': {'initial': 'whole_program', 'empirical_routing': False, 'alternative_plans': False},
    'static': {'initial': 'generated_decomposition', 'empirical_routing': False, 'alternative_plans': False},
    'decompose_on_failure': {'initial': 'whole_program', 'empirical_routing': False, 'alternative_plans': True},
    'capability': {'initial': 'generated_decomposition', 'empirical_routing': True, 'alternative_plans': False},
    'search': {'initial': 'generated_decomposition', 'empirical_routing': False, 'alternative_plans': True},
    'mica': {'initial': 'generated_decomposition', 'empirical_routing': True, 'alternative_plans': True},
}
STATES = ('done', 'failed', 'blocked', 'exhausted', 'unknown', 'stopped')
COSTS = ('input_tokens', 'output_tokens', 'latency_ms', 'provider_ms', 'wall_seconds',
         'cpu_seconds', 'memory_bytes', 'usd')
COST_UNITS = {'input_tokens': 'tokens', 'output_tokens': 'tokens', 'latency_ms': 'end_to_end_milliseconds',
              'provider_ms': 'provider_milliseconds', 'wall_seconds': 'end_to_end_seconds',
              'cpu_seconds': 'cpu_seconds', 'memory_bytes': 'reported_bytes_not_additive', 'usd': 'USD'}
from symblic.mica import source_identity as I

# The files whose exact bytes a frozen benchmark records, keyed by repository path.
_FILES = (__file__, E.__file__, C.__file__, S.__file__, S.P.__file__)
_IMPORTED = {I.relative_path(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in _FILES}


class BenchmarkError(ValueError):
    """Finite diagnostic code; never includes source or private evaluator inputs."""


def _fail(code):
    raise BenchmarkError(code)


def _implementation():
    current = {I.relative_path(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in _FILES}
    if (not _symblic_import_identity.get('matched')
            or _symblic_import_identity.get('sha256') != current[I.relative_path(__file__)]):
        _fail('implementation_loaded_source')
    if current != _IMPORTED:
        _fail('implementation_changed_use_fresh_worker')
    return current


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _write(path, value):
    """Reuse the integer-only policy store with lossless finite-JSON chunks.

    Native measured durations are floats and candidate sources may exceed that
    store's per-string limit. The envelope preserves their exact canonical JSON
    without weakening its private-file, atomic publication or immutability rules.
    """
    pin = E.digest(value)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    S._write_immutable(path, {'encoding': 'mica-finite-json-v1', 'payload_sha256': pin,
                             'chunks': [raw[i:i+16000] for i in range(0, len(raw), 16000)]})
    return pin


def _read(path):
    box = S._read(path)
    if (type(box) is not dict or set(box) != {'encoding', 'payload_sha256', 'chunks'}
            or box['encoding'] != 'mica-finite-json-v1' or type(box['chunks']) is not list
            or not 1 <= len(box['chunks']) <= 128
            or any(type(chunk) is not str or not chunk or len(chunk) > 16000 for chunk in box['chunks'])):
        _fail('storage_encoding')
    raw = ''.join(box['chunks'])
    try:
        value = json.loads(raw, object_pairs_hook=E._pairs)
        pin = E.digest(value)
    except (ValueError, UnicodeError, RecursionError):
        _fail('storage_json')
    if (pin != box['payload_sha256'] or raw != json.dumps(value, sort_keys=True, ensure_ascii=False,
                                                         separators=(',', ':'), allow_nan=False)):
        _fail('storage_payload_pin')
    return value


def _hidden(cases):
    if type(cases) is not list or not 1 <= len(cases) <= 200:
        _fail('hidden_cases')
    for row in cases:
        if type(row) is not list or len(row) != 2:
            _fail('hidden_case')
        C._text(row[0], 'hidden_call', 4000)
        C._expected(row[1])
    E.digest(cases)
    return copy.deepcopy(cases)


def js_evaluator_identity():
    """Pin the existing isolated JS checker without executing any candidate."""
    from symblic.js import check as JS
    from symblic.mica import bundle as MB
    return {'kind': 'symblic.js.check.test', 'adapter': JS.ADAPTER,
            'implementation_sha256': hashlib.sha256(Path(JS.__file__).read_bytes()).hexdigest(),
            'runtime': JS.VERSION, 'assets': JS.asset_hashes(), 'scope': 'finite_hidden_tests',
            'modules': MB._module_runtime(None)}


def _js_evaluate(source, cases):
    from symblic.js import check as JS
    return JS.test(source, cases)


class MicaBenchmark:
    """Private, immutable experiment. Call freeze once, retain its returned pin.

    Runner signature: runner(request=..., mode=..., assignment=..., seed=...,
    controls=...). It returns the MicaRun result, optionally observed_controls
    with fingerprints of actually enforced control declarations. Merely repeating
    declared fingerprints is a host attestation, not independent verification.
    """

    def __init__(self, root, ident, freeze_sha256):
        S._id(ident)
        S._sha(freeze_sha256)
        self.path = Path(root) / ident
        self.ident = ident
        self.freeze_sha256 = freeze_sha256
        S._directory(Path(root))
        S._directory(self.path)

    @classmethod
    def freeze(cls, root, ident, fixtures, *, model, budget, repetitions=1,
               order_seed=0, split='heldout', exposures=(), controls_overrides=None,
               evaluator_identity=None):
        """Freeze *all* case/arm/repeat assignments before the first runner call.

        A fixture has id, family, split, request, hidden_tests, and optionally a
        private checked checkpack linkage. Budget is one full
        caller budget for every request/mode; inconsistent request budgets fail.
        Overrides may expose scientific confounds, but cannot change the budget.
        """
        S._id(ident)
        root = Path(root)
        S._directory(root, create=True)
        path = root / ident
        S._directory(path, create=True)
        S._directory(path / 'runs', create=True)
        normalized_budget = C._budget(budget)
        if normalized_budget['max_calls'] < 1:
            _fail('benchmark_needs_positive_call_budget')
        if type(fixtures) is not list or not fixtures:
            _fail('fixtures')
        evaluator_identity = copy.deepcopy(evaluator_identity or js_evaluator_identity())
        if type(evaluator_identity) is not dict or not evaluator_identity:
            _fail('evaluator_identity')
        E.digest(evaluator_identity)
        cases, hidden, links = [], {}, {}
        for fixture in fixtures:
            if type(fixture) is not dict or set(fixture) - {'checkpack'} != {'id', 'family', 'split', 'request', 'hidden_tests'}:
                _fail('fixture_schema')
            S._id(fixture['id'])
            if fixture['id'] in hidden:
                _fail('duplicate_fixture')
            request = C.normalize_request(fixture['request'])
            if request['budget'] != normalized_budget:
                _fail('unequal_caller_budgets')
            cases.append({'id': fixture['id'], 'family': fixture['family'],
                          'split': fixture['split'], 'input': request,
                          'rubric': {'mode': 'typed_json', 'expected': True}})
            hidden[fixture['id']] = _hidden(fixture['hidden_tests'])
            if 'checkpack' in fixture:
                from symblic.mica import checkpack_link as H
                try:
                    links[fixture['id']] = H.validate_fixture(fixture, current_checker=evaluator_identity)
                except (ValueError, TypeError, KeyError):
                    _fail('checkpack_fixture_link')
        checkpacks = {'version': 1, 'links': links} if links else None
        if checkpacks is not None:
            E.digest(checkpacks)  # Aggregate bound: refuse, never drop linked cases.
        controls = {'model': model,
                    'information': {'public_cases_sha256': E.digest([c['input'] for c in cases]),
                                    'hidden_cases_available': False},
                    'budget': {'provider_calls': normalized_budget['max_calls'],
                               'caller_budget': normalized_budget},
                    'feedback': {'policy': 'public_checks_only', 'hidden_repair_feedback': False},
                    'validator': evaluator_identity}
        overrides = controls_overrides or {}
        if type(overrides) is not dict or set(overrides) - set(MODES):
            _fail('control_override_mode')
        arms = []
        for mode in MODES:
            override = overrides.get(mode, {})
            if type(override) is not dict or set(override) - set(E.AXES):
                _fail('control_override_axis')
            if 'budget' in override and override['budget'] != controls['budget']:
                _fail('unequal_caller_budgets')
            arms.append(E.make_arm(mode, mode, **{**controls, **override}))
        plan = E.make_plan(cases, arms, split=split, repetitions=repetitions,
                           exposures=exposures, order_seed=order_seed)
        # Files are immutable and the manifest is published last. A failed freeze
        # cannot dispatch because constructing an object requires the final pin.
        files = {'plan.json': _write(path / 'plan.json', plan),
                 'hidden.json': _write(path / 'hidden.json', hidden)}
        if checkpacks is not None:
            files['checkpacks.json'] = _write(path / 'checkpacks.json', checkpacks)
        frozen = {'version': VERSION, 'experiment': ident, 'files': files,
                  'implementation': _implementation(), 'evaluator': evaluator_identity}
        pin = _write(path / 'frozen.json', frozen)
        return cls(root, ident, pin)

    @contextmanager
    def _lock(self):
        S._directory(self.path)
        descriptor = os.open(self.path / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                _fail('lock_file')
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _load(self, *, current=False):
        S._directory(self.path / 'runs')
        manifest = _read(self.path / 'frozen.json')
        if E.digest(manifest) != self.freeze_sha256:
            _fail('freeze_pin')
        if (manifest.get('version') != VERSION or manifest.get('experiment') != self.ident
                or set(manifest.get('files', {})) not in ({'plan.json', 'hidden.json'},
                    {'plan.json', 'hidden.json', 'checkpacks.json'})):
            _fail('manifest_schema')
        if current and manifest['implementation'] != _implementation():
            _fail('implementation_pin')
        files = {}
        for name, pin in manifest['files'].items():
            files[name] = _read(self.path / name)
            if E.digest(files[name]) != pin:
                _fail('file_pin')
        E._check_plan(files['plan.json'])
        if 'checkpacks.json' in files:
            from symblic.mica import checkpack_link as H
            packs = files['checkpacks.json']
            cases = {case['id']: case for case in files['plan.json']['cases']}
            if (type(packs) is not dict or set(packs) != {'version', 'links'}
                    or type(packs['version']) is not int or packs['version'] != 1
                    or type(packs['links']) is not dict or not packs['links']
                    or not set(packs['links']) <= set(cases)):
                _fail('checkpack_sidecar_schema')
            for ident, link in packs['links'].items():
                case = cases[ident]
                fixture = {key: case[key] for key in ('id', 'family', 'split')}
                fixture.update(request=case['input'], hidden_tests=files['hidden.json'].get(ident), checkpack=link)
                try:
                    H.validate_fixture(fixture, current_checker=manifest['evaluator'], require_current=current)
                except (ValueError, TypeError, KeyError):
                    _fail('checkpack_fixture_link')
        return manifest, files['plan.json'], files['hidden.json']

    def assignments(self):
        with self._lock():
            return copy.deepcopy(self._load()[1]['assignments'])

    def _row(self, plan, assignment_id):
        S._sha(assignment_id)
        found = [a for a in plan['assignments'] if a['id'] == assignment_id]
        if not found:
            _fail('unknown_assignment')
        return found[0]

    def _intent(self, assignment, request, arm, plan):
        # Same block seed across arms; placement seed is frozen independently.
        seed = int(E.digest({'order_seed': plan['order']['seed'],
                             'case_id': assignment['case_id'], 'repeat': assignment['repeat']})[:15], 16)
        return {'version': VERSION, 'freeze_sha256': self.freeze_sha256,
                'assignment': assignment, 'request_sha256': E.digest(request),
                'controls_sha256': E.digest(arm['controls']), 'seed': seed}

    def run_assignment(self, assignment_id, runner, *, evaluator=None, evaluator_identity=None):
        """At-most-once dispatch. Interrupted/unknown intent is returned, not retried.

        The callback runs outside the store lock. Concurrent callers see the durable
        intent and return unknown. A hidden grade is persisted only after construction.
        """
        with self._lock():
            manifest, plan, hidden = self._load(current=True)
            assignment = self._row(plan, assignment_id)
            case = next(c for c in plan['cases'] if c['id'] == assignment['case_id'])
            arm = next(a for a in plan['arms'] if a['id'] == assignment['arm_id'])
            folder = self.path / 'runs' / assignment_id
            S._directory(folder, create=True)
            intent = self._intent(assignment, case['input'], arm, plan)
            if (folder / 'outcome.json').exists():
                return self._outcome(folder, intent)
            if (folder / 'intent.json').exists():
                if _read(folder / 'intent.json') != intent:
                    _fail('intent_pin')
                return {'assignment_id': assignment_id, 'status': 'unknown',
                        'reason': 'dispatch_intent_without_outcome', 'replayed': False}
            actual_identity = evaluator_identity if evaluator is not None else js_evaluator_identity()
            if actual_identity != manifest['evaluator']:
                _fail('evaluator_pin')
            # Passing a non-default evaluator without its independent host identity
            # is deliberately rejected; tests and alternate graders must be declared.
            _write(folder / 'intent.json', intent)
        try:
            result = runner(request=copy.deepcopy(case['input']), mode=assignment['arm_id'],
                            assignment=copy.deepcopy(assignment), seed=intent['seed'],
                            controls=copy.deepcopy(arm['controls']))
        except Exception:  # noqa: BLE001 - trusted callback may fail after external dispatch
            # Provider may have seen the request: keep intent with no outcome.
            return {'assignment_id': assignment_id, 'status': 'unknown',
                    'reason': 'runner_exception', 'replayed': False}
        try:
            retained = self._validate_result(result, case['input']['budget'])
            if retained['status'] == 'done' and case['input']['artifact_format'] == 'javascript_modules':
                from symblic.mica import bundle as MB
                MB.verify_bundle(retained.get('bundle'))
                if retained['bundle']['request'] != case['input'] or retained['output'] != retained['bundle']['spec_manifest']['output']:
                    _fail('bundle_request')
        except (BenchmarkError, E.ProtocolError, ValueError, TypeError, OverflowError):
            # A malformed receipt cannot justify replay or zero-cost accounting.
            return {'assignment_id': assignment_id, 'status': 'unknown',
                    'reason': 'invalid_runner_receipt', 'replayed': False}
        grade = {'status': 'not_evaluated', 'passed': None, 'scope': 'finite_hidden_tests'}
        if retained['status'] == 'done':
            if 'checkpacks.json' in manifest['files']:
                # Runner executes outside the lock. Revalidate retained private
                # authority and actual checker again before any hidden grading.
                try:
                    with self._lock():
                        checked_manifest, _, checked_hidden = self._load(current=True)
                        actual_identity = evaluator_identity if evaluator is not None else js_evaluator_identity()
                        if checked_manifest != manifest or checked_hidden != hidden or actual_identity != manifest['evaluator']:
                            _fail('checkpack_pregrade_pin')
                except (ValueError, OSError, TypeError, KeyError):
                    return {'assignment_id': assignment_id, 'status': 'unknown',
                            'reason': 'checkpack_provenance_revalidation_failed', 'replayed': False}
            try:
                cases = copy.deepcopy(hidden[case['id']])
                if case['input']['artifact_format'] == 'javascript_modules':
                    if evaluator is not None:
                        evaluated = evaluator(copy.deepcopy(retained['bundle']), cases)
                    else:
                        observed = MB.check_cases(retained['bundle'], cases)
                        if observed['status'] not in ('passed', 'failed'):
                            _fail('module_evaluator_inconclusive')
                        evaluated = {**observed, 'failed': sum(not c['passed'] for c in observed['module_checks'])}
                else:
                    evaluated = (evaluator or _js_evaluate)(retained['output']['text'], cases)
                if (type(evaluated) is not dict or type(evaluated.get('passed')) is not bool
                        or type(evaluated.get('total')) is not int
                        or evaluated['total'] != len(hidden[case['id']])
                        or type(evaluated.get('failed')) is not int
                        or not 0 <= evaluated['failed'] <= evaluated['total']
                        or evaluated['passed'] != (evaluated['failed'] == 0)):
                    _fail('evaluator_receipt')
                E.digest(evaluated)
                grade = {'status': 'tested' if evaluated['passed'] else 'failed',
                         'passed': evaluated['passed'], 'scope': 'finite_hidden_tests',
                         'result': copy.deepcopy(evaluated)}
            except Exception:  # noqa: BLE001 - grader infrastructure failure is inconclusive
                grade = {'status': 'unknown', 'passed': None, 'reason': 'evaluator_unavailable',
                         'scope': 'finite_hidden_tests'}
        receipt = {'version': VERSION, 'assignment_id': assignment_id,
                   'freeze_sha256': self.freeze_sha256, 'intent_sha256': E.digest(intent),
                   'status': retained['status'], 'runner': retained, 'grade': grade,
                   'evaluator_sha256': E.digest(manifest['evaluator'])}
        with self._lock():
            self._load(current=True)
            if _read(folder / 'intent.json') != intent:
                _fail('intent_pin')
            _write(folder / 'outcome.json', receipt)
        return copy.deepcopy(receipt)

    @staticmethod
    def _validate_result(result, budget):
        E.digest(result)
        if type(result) is not dict or result.get('status') not in STATES:
            _fail('runner_status')
        calls = result.get('calls')
        if type(calls) is not int or not 0 <= calls <= 10**15:
            _fail('runner_calls')
        attempts = result.get('attempts')
        if type(attempts) is not list:
            _fail('runner_attempts')
        if type(result.get('costs')) is not dict or type(result.get('evidence')) not in (list, dict):
            _fail('runner_evidence')
        costs = result['costs']
        for name in COSTS:
            value = costs.get(name)
            if value is not None and (type(value) not in (int, float) or not 0 <= value <= 10**15 or not math.isfinite(value)):
                _fail('runner_cost')
        if result['status'] == 'done':
            output = result.get('output')
            if type(output) is not dict or type(output.get('text')) is not str:
                _fail('runner_output')
            if len(output['text'].encode('utf-8')) > 400000 or output.get('sha256') != _sha(output['text']):
                _fail('runner_output_hash')
        retained = copy.deepcopy(result)
        retained['budget_violation'] = calls > budget['max_calls']
        return retained

    def _outcome(self, folder, intent):
        receipt = _read(folder / 'outcome.json')
        if (receipt.get('version') != VERSION or receipt.get('freeze_sha256') != self.freeze_sha256
                or receipt.get('intent_sha256') != E.digest(intent)
                or receipt.get('assignment_id') != intent['assignment']['id']
                or _read(folder / 'intent.json') != intent):
            _fail('outcome_pin')
        return receipt

    def run_all(self, runner, **kwargs):
        """Honor frozen counterbalanced order, retain every assigned denominator."""
        for assignment in self.assignments():
            self.run_assignment(assignment['id'], runner, **kwargs)
        return self.report()

    def report(self):
        """Reports include grade status, never hidden cases or private reports."""
        with self._lock():
            manifest, plan, _ = self._load()
            provenance = {}
            if 'checkpacks.json' in manifest['files']:
                from symblic.mica import checkpack_link as H
                retained_links = _read(self.path / 'checkpacks.json')
                if E.digest(retained_links) != manifest['files']['checkpacks.json']:
                    _fail('file_pin')
                links = retained_links['links']
                provenance = {'checkpack_provenance': [H.public_receipt(ident, link)
                               for ident, link in sorted(links.items())]}
            arms = {a['id']: a for a in plan['arms']}
            cases = {c['id']: c for c in plan['cases']}
            rows, receipts = [], {}
            for assignment in plan['assignments']:
                folder = self.path / 'runs' / assignment['id']
                status, receipt = 'pending', None
                if folder.exists():
                    S._directory(folder)
                    intent = self._intent(assignment, cases[assignment['case_id']]['input'],
                                          arms[assignment['arm_id']], plan)
                    if (folder / 'outcome.json').exists():
                        try:
                            receipt = self._outcome(folder, intent)
                            status = receipt['status']
                        except (BenchmarkError, S.PolicyStoreError, KeyError, TypeError):
                            status = 'damaged'
                    elif (folder / 'intent.json').exists():
                        status = 'unknown'
                success = bool(receipt and status == 'done' and receipt['grade']['passed'] is True
                               and not receipt['runner']['budget_violation'])
                row = {'assignment_id': assignment['id'], 'case_id': assignment['case_id'],
                       'mode': assignment['arm_id'], 'repeat': assignment['repeat'],
                       'position': assignment['position'], 'status': status, 'success': success,
                       'grade_status': receipt['grade']['status'] if receipt else None,
                       'receipt_sha256': E.digest(receipt) if receipt else None}
                rows.append(row)
                if receipt:
                    receipts[assignment['id']] = receipt
        groups = {}
        for mode in MODES:
            selected = [r for r in rows if r['mode'] == mode]
            observed = [receipts[r['assignment_id']]['runner'] for r in selected
                        if r['assignment_id'] in receipts]
            n, k = len(selected), sum(r['success'] for r in selected)
            groups[mode] = {'assigned': n, 'successes': k, 'success_rate': k / n if n else None,
                            'statuses': dict(Counter(r['status'] for r in selected)),
                            'grade_statuses': dict(Counter(r['grade_status'] or 'missing' for r in selected)),
                            'calls': {'observed_total': sum(r['calls'] for r in observed),
                                      'observed_runs': len(observed), 'unobserved_runs': n - len(observed)},
                            'costs': {}}
            for name in COSTS:
                values = [r['costs'][name] for r in observed if r['costs'].get(name) is not None]
                groups[mode]['costs'][name] = {'unit': COST_UNITS[name],
                                               'observed_total': sum(values) if values and name != 'memory_bytes' else None,
                                               'observed_mean': sum(values)/len(values) if values else None,
                                               'observed_max': max(values) if values else None,
                                               'observed_runs': len(values), 'unobserved_runs': n - len(values)}
        declared = E.compare_arms(plan['arms'])
        confounds = [{'kind': 'declared_control_difference', 'axis': a} for a in declared['mismatched_axes']]
        for row in rows:
            receipt = receipts.get(row['assignment_id'])
            if not receipt:
                continue
            run = receipt['runner']
            observed = run.get('observed_controls')
            if observed is None:
                confounds.append({'kind': 'runtime_controls_unobserved', 'assignment_id': row['assignment_id']})
            elif observed != arms[row['mode']]['fingerprints']:
                confounds.append({'kind': 'runtime_control_difference', 'assignment_id': row['assignment_id']})
            if run['budget_violation']:
                confounds.append({'kind': 'budget_exceeded', 'assignment_id': row['assignment_id']})
        paired = []
        for left, right in combinations(MODES, 2):
            pairs = {}
            for row in rows:
                if row['mode'] in (left, right):
                    pairs.setdefault((row['case_id'], row['repeat']), {})[row['mode']] = row
            complete = [v for v in pairs.values() if all(v[m]['status'] not in
                         ('pending', 'unknown', 'damaged', 'blocked', 'stopped') and v[m]['grade_status'] != 'unknown'
                         for m in (left, right))]
            paired.append({'left': left, 'right': right, 'planned_pairs': len(pairs),
                           'resolved_pairs': len(complete),
                           'left_only_success': sum(v[left]['success'] and not v[right]['success'] for v in complete),
                           'right_only_success': sum(v[right]['success'] and not v[left]['success'] for v in complete)})
        return {'version': VERSION, 'freeze_sha256': self.freeze_sha256, 'plan_sha256': E.digest(plan), **provenance,
                'assigned': len(rows), 'completed_receipts': len(receipts), 'modes': groups,
                'mode_factors': copy.deepcopy(MODE_FACTORS),
                'declared_matching': declared, 'confounds': confounds,
                'runtime_matching': 'unobserved' if len(receipts) < len(rows) or confounds else 'host_attested',
                'order': plan['order'], 'assignments': rows, 'paired': paired,
                'limitations': ['Finite hidden tests establish TESTED, never PROVEN.',
                                'Repeated cases and task families are dependent; rates are descriptive.',
                                'Counterbalanced order does not eliminate cache, hardware or time effects.',
                                'Control matching is declared or host-attested, not independently verified.',
                                'No formal-refinement ablation is established; generated plans may contain only executable examples.',
                                'Missing outcomes remain in every planned denominator.']}
