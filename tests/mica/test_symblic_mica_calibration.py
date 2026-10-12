"""Frozen cross-run evidence: no providers, global stores or training.

Audit fixtures use real seals, call-journal validation, contract validation and
component manifests. Only executable identity validation is substituted in the
pure class, so it is independent of the machine's JavaScript sandbox. The final
class exercises real native fixtures in a coherent runtime snapshot.
"""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.graph import run as G
from symblic.mica import search as M
from symblic.mica import calibration as A
from symblic.mica import contracts as C
from symblic.mica import native as N
from symblic.mica import routing as R
from symblic.spec import contracts as SC
from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request, proposal


IDENTITY = {'version': 1, 'fixture': 'a' * 64}
NATIVE_IDENTITY = {'version': 1, 'fixture': 'b' * 64}


class CalibrationPureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-calibration-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for patch in (mock.patch.object(M, 'implementation_identity', return_value=IDENTITY),
                      mock.patch.object(N, '_identity', return_value=NATIVE_IDENTITY),
                      mock.patch.object(N.X, 'validate', side_effect=lambda pins, source, inputs: pins)):
            patch.start(); self.addCleanup(patch.stop)
        self.checker = G._hash(IDENTITY)

    def put(self, path, value):
        path.write_text(json.dumps(G._seal(value)))

    def events(self, path, bodies):
        rows = []
        for body in bodies:
            rows.append(G._seal({'sequence': len(rows), 'previous': rows[-1]['sha256'] if rows else None, **body}))
        (path / 'mica-events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def fixture(self, name='run', success=True, *, ungraded=False):
        path = self.root / name; path.mkdir()
        for sub in ('attempts', 'components', 'decisions', 'unit-states'):
            (path / sub).mkdir()
        (path / '.mica.lock').touch()
        req = C.normalize_request(request(max_candidates=1))
        route = {'provider': 'ollama', 'model': 'fixture-small', 'node': 'node-a', 'local': True, 'digest': None}
        manifest = {'version': 1, 'request': req, 'inventory': R.normalize_inventory(inventory()),
                    'mode': 'direct', 'initial_plans': [], 'identity': IDENTITY, 'library': None,
                    'started_ms': 100 + len(list(self.root.iterdir()))}
        self.put(path / 'mica-manifest.json', manifest)
        plan = M.proposal_to_plan(req, proposal(), 'direct')
        contract = plan['contracts'][0]
        ident = 'build-000-increment'
        attempt = path / 'attempts' / ident; attempt.mkdir()
        (attempt / '.mica-native.lock').touch()
        source = 'program Fixture.\n'
        pins = {'version': 1, 'source': source, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'inputs': {}, 'route': route, 'limit': 1, 'output_binding': 'candidate', 'options': {},
                'identity': NATIVE_IDENTITY, 'execution_pins': {'capabilities': {}}}
        self.put(attempt / 'mica-native-pins.json', pins)
        (attempt / 'program.sym').write_bytes(source.encode())
        common = {'version': 1, 'context': {'mica_native': G._hash(pins)}, 'index': 1,
                  'key': 'fixture-call', 'request_hash': 'c' * 64}
        reply = {'ok': success, 'model': 'fixture-small', 'node': 'node-a', 'ms': 7}
        if not success:
            reply['error'] = 'encoded test failed'
        journal = [G._seal({**common, 'kind': 'intent'}), G._seal({**common, 'kind': 'outcome', 'reply': reply})]
        (attempt / 'graph-calls.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in journal))
        measured = G._seal({'version': 1, 'request_key': 'fixture-call',
                           'observed': {'model': 'fixture-small', 'node': 'node-a', 'ms': 7}})
        (attempt / 'mica-provider-evidence.jsonl').write_text(json.dumps(measured) + '\n')
        code = 'function inc(x) { return x + 1; }'
        native = {'version': 1, 'pins_sha256': G._hash(pins), 'status': 'done' if success else 'failed',
                  'calls': 1, 'output': code if success else None, 'error': None if success else 'encoded test failed',
                  'provider_evidence': [measured]}
        self.put(attempt / 'mica-native-result.json', native)
        decision = {'contract': 'increment', 'attempt': ident, 'status': native['status'], 'calls': 1,
                    'reused': False, 'route': route, 'strategy': 'local_model', 'kernel_failure': None}
        result = {'status': native['status'], 'decisions': [decision]}
        if success:
            runtime = M.MicaRun(req, path, None, inventory())
            spec = runtime._sheet_plan(plan)
            uid = spec['units'][0]['id']
            artifact = SC.record_artifact(spec, uid, code, {}, runtime_identity=IDENTITY,
                                          checks=[{'scope': 'fixture_host_check', 'passed': True,
                                                   'subject_sha256': SC.code_hash(code)}])
            self.put(path / 'components' / 'one.json', {'key': 'fixture', 'runtime': IDENTITY,
                     'code': code, 'artifact': artifact, 'origin_attempt': ident, 'decision': decision})
            self.put(path / 'decisions' / (ident + '.json'), decision)
            result.update(manifest=SC.artifact_manifest(spec, {uid: artifact}, runtime_identity=IDENTITY), checks={'passed': True})
            result['output'] = result['manifest']['output']
        else:
            result.update(failure='TEST_FAILURE', contract='increment')
        self.put(path / 'branch-000.json', {'plan': plan, 'result': result, 'depth': 0,
                 'parent_plan': None, 'trigger': None, 'root_request_sha256': C.digest(req)})
        obs = A._projection(ident, contract, route, native, success)
        bodies = [{'kind': 'reserve', 'attempt': ident, 'limit': 1, 'route': route},
                  {'kind': 'settled', 'attempt': ident, 'calls': 1, 'status': native['status']}]
        if not ungraded:
            bodies.append({'kind': 'observation', 'observation': obs})
        self.events(path, bodies)
        measurements = A._measurements(1, [measured['observed']])
        report = {'version': 1, **result, 'calls': 1, 'calls_reserved_or_spent': 1,
                  'manifest_sha256': G._hash(manifest), 'request_sha256': C.digest(req),
                  'attempts': [{'branch': 0, 'plan_sha256': plan['content_hash'], 'status': result['status'],
                                'failure': result.get('failure'), 'decisions': [decision]}],
                  'routing_observations': R.summarize([] if ungraded else [obs]), 'measurements': measurements,
                  'costs': {'provider_calls': 1, 'input_tokens': None, 'output_tokens': None, 'provider_ms': 7},
                  'evidence': {'caller_acceptance_sha256': C.digest(req['tests'])}}
        self.put(path / 'mica-result.json', report)
        return path

    def reseal(self, path, change):
        value = G._read(path); value.pop('sha256'); change(value); self.put(path, value)

    def test_success_and_failure_are_namespaced_and_frozen_without_fabricating_counters(self):
        good = self.fixture('good'); bad = self.fixture('bad', False)
        snapshot = A.freeze([good, bad])
        self.assertEqual(snapshot['counts']['provider_calls'], 2)
        self.assertEqual(snapshot['counts']['observations'], 2)
        self.assertEqual({r['status'] for r in snapshot['observations']}, {'success', 'failed'})
        self.assertEqual(len({r['observation_id'] for r in snapshot['observations']}), 2)
        self.assertTrue(all(r['digest'] is None and r['input_tokens'] is None for r in snapshot['observations']))
        self.assertEqual(A.freeze([bad, good]), snapshot)
        self.temp.cleanup()
        with mock.patch.object(G, '_read', side_effect=AssertionError('consumer read history')):
            self.assertEqual(A.normalize(snapshot, self.checker), snapshot)

    def test_checker_mismatch_count_tamper_and_duplicate_selections_refuse(self):
        path = self.fixture(); snapshot = A.freeze([path])
        with self.assertRaises(A.CalibrationError): A.normalize(snapshot, 'e' * 64)
        corrupt = copy.deepcopy(snapshot); corrupt['counts']['observations'] = 4
        with self.assertRaises(ValueError): A.normalize(corrupt, self.checker)
        with self.assertRaises(A.CalibrationError): A.freeze([path, path])
        self.reseal(path / 'mica-manifest.json', lambda r: r.update(identity={'other': 1}))
        with self.assertRaises(A.CalibrationError): A.freeze([path])

    def test_event_chain_native_journal_and_unknown_delivery_refuse(self):
        for case in ('chain', 'outcome', 'unknown'):
            with self.subTest(case=case):
                path = self.fixture(case, False)
                if case == 'chain':
                    eventfile = path / 'mica-events.jsonl'; rows = eventfile.read_text().splitlines()
                    eventfile.write_text('\n'.join(rows[::-1]) + '\n')
                else:
                    attempt = path / 'attempts' / 'build-000-increment'
                    journal = attempt / 'graph-calls.jsonl'
                    if case == 'unknown':
                        journal.write_text(journal.read_text().splitlines()[0] + '\n')
                        (attempt / 'mica-native-result.json').unlink()
                    else:
                        rows = [json.loads(r) for r in journal.read_text().splitlines()]
                        rows[-1]['reply']['ok'] = True
                        journal.write_text(''.join(json.dumps(r) + '\n' for r in rows))
                with self.assertRaises(ValueError): A.freeze([path])

    def test_native_call_measurement_and_success_provenance_conflicts_refuse(self):
        for case in ('calls', 'measurement', 'component', 'rootlink'):
            with self.subTest(case=case):
                path = self.fixture(case)
                if case == 'calls':
                    self.reseal(path / 'mica-result.json', lambda r: r.update(calls=0))
                elif case == 'measurement':
                    (path / 'attempts' / 'build-000-increment' / 'mica-provider-evidence.jsonl').write_text('')
                elif case == 'component':
                    (path / 'components' / 'one.json').unlink()
                else:
                    self.reseal(path / 'mica-result.json', lambda r: r.update(request_sha256='f' * 64))
                with self.assertRaises(ValueError): A.freeze([path])
        path = self.fixture('root-assembly-check')
        with mock.patch.object(M, 'verify_result_artifacts', side_effect=M.MicaError('Detached module receipt')) as verify:
            with self.assertRaises(ValueError): A.freeze([path])
        self.assertEqual(verify.call_count, 1)

    def test_ungraded_calls_remain_visible_and_capacity_never_drops_evidence(self):
        path = self.fixture(success=False, ungraded=True)
        snapshot = A.freeze([path])
        self.assertEqual(snapshot['counts']['ungraded_provider_calls'], 1)
        self.assertEqual(snapshot['observations'], [])
        with mock.patch.object(A, 'MAX_ATTEMPTS', 0):
            with self.assertRaises(ValueError): A.freeze([path])
        with mock.patch.object(A, 'MAX_BYTES', 100):
            with self.assertRaises(ValueError): A.normalize(snapshot, self.checker)

    def test_retained_program_bytes_must_equal_pinned_source_and_be_regular_bounded(self):
        for case in ('changed', 'missing', 'symlink', 'fifo', 'oversized'):
            with self.subTest(case=case):
                path = self.fixture(case)
                program = path / 'attempts' / 'build-000-increment' / 'program.sym'
                if case == 'changed':
                    program.write_text('program Changed source.\n')
                elif case == 'oversized':
                    program.write_bytes(b'x' * 256)
                    with mock.patch.object(G, 'MAX_FILE_BYTES', 128):
                        with self.assertRaises(ValueError): A._program_bytes(program)
                    continue
                else:
                    program.unlink()
                    if case == 'symlink': program.symlink_to(path / 'mica-manifest.json')
                    if case == 'fifo': os.mkfifo(program)
                with self.assertRaises(ValueError): A.freeze([path])

    def test_symlink_busy_lock_and_copied_manifest_refuse_without_writing(self):
        path = self.fixture(); alias = self.root / 'alias'; alias.symlink_to(path, target_is_directory=True)
        with self.assertRaises(A.CalibrationError): A.freeze([alias])
        fd = os.open(path / '.mica.lock', os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(A.CalibrationError): A.freeze([path])
        finally:
            os.close(fd)
        import shutil
        twin = self.root / 'twin'; shutil.copytree(path, twin)
        with self.assertRaises(A.CalibrationError): A.freeze([path, twin])
        cache = path / 'attempts' / 'build-000-increment' / 'calls.jsonl'
        os.mkfifo(cache)
        with self.assertRaises(A.CalibrationError): A.freeze([path])

    def test_terminal_failed_project_root_is_accounted_without_inventing_a_grade(self):
        from symblic.mica import project as P
        path = self.root / 'project'; path.mkdir(); (path / '.mica-project.lock').touch()
        (path / 'root-attempts').mkdir()
        donor = self.fixture('donor', False)
        (donor / 'attempts' / 'build-000-increment').rename(path / 'root-attempts' / 'root-000')
        manifest = {'version': P.VERSION, 'objective': 'Implement increment.',
                    'budget': C.normalize_request(request())['budget'], 'allowed_outputs': ['result.js'],
                    'inventory': R.normalize_inventory(inventory()), 'mode': 'direct', 'library': None,
                    'started_ms': 100, 'identity': {'project_fixture': True}}
        self.put(path / P.MANIFEST, manifest)
        view = P.MicaProject.__new__(P.MicaProject); view.objective = manifest['objective']
        report = {'version': P.VERSION, 'manifest_sha256': G._hash(manifest), 'status': 'exhausted',
                  'objective': manifest['objective'], 'request': None, 'request_sha256': None,
                  'provenance': P.MicaProject._provenance(view, None), 'child': None,
                  'root_calls': 1, 'construction_calls': 0, 'calls': 1,
                  'costs': {'provider_calls': 1}, 'measurements': A._measurements(1, [{'ms': 7}])}
        self.put(path / P.RESULT, report)
        with mock.patch.object(P, '_identity', return_value={'project_fixture': True}):
            snapshot = A.freeze([path])
        self.assertEqual(snapshot['counts']['provider_calls'], 1)
        self.assertEqual(snapshot['counts']['ungraded_provider_calls'], 1)
        self.assertEqual(snapshot['observations'], [])
        self.assertEqual(snapshot['sources'][0]['native_attempts'][0]['role'], 'root_specification')

    def test_native_lock_excludes_direct_adapter_races_through_final_snapshot(self):
        path = self.fixture()
        lock = path / 'attempts' / 'build-000-increment' / '.mica-native.lock'
        fd = os.open(lock, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(A.CalibrationError): A.freeze([path])
            fcntl.flock(fd, fcntl.LOCK_UN)
            normalize = A.normalize
            def checked_normalize(value, checker):
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return normalize(value, checker)
            with mock.patch.object(A, 'normalize', side_effect=checked_normalize):
                A.freeze([path])
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)

    def test_seed_is_frozen_provenance_and_never_reexported_as_fresh_success(self):
        original = self.fixture('original')
        seed = A.freeze([original])
        later = self.fixture('later', False)
        self.reseal(later / 'mica-manifest.json', lambda r: r.update(calibration=seed))
        manifest = G._read(later / 'mica-manifest.json')
        own = [r['observation'] for r in G._read(later / 'mica-events.jsonl', lines=True) if r['kind'] == 'observation']
        self.reseal(later / 'mica-result.json', lambda r: r.update(manifest_sha256=manifest['sha256'],
                     routing_observations=R.summarize(seed['observations'] + own)))
        snapshot = A.freeze([later])
        self.assertEqual(snapshot['counts']['observations'], 1)
        self.assertEqual(snapshot['observations'][0]['status'], 'failed')
        self.assertNotEqual(snapshot['observations'][0]['observation_id'], seed['observations'][0]['observation_id'])
        self.assertEqual(snapshot['sources'][0]['seed_calibration_sha256'], seed['sha256'])
        self.assertEqual(snapshot['sources'][0]['seed_observations'], 1)


class CalibrationNativeTest(unittest.TestCase):
    """Run only with all native sources from one coherent source snapshot."""
    def test_actual_failed_unit_and_planner_grade_import_with_all_dispatches(self):
        with tempfile.TemporaryDirectory(prefix='mica-calibration-native-') as tmp:
            path = Path(tmp) / 'run'
            apps = FakeApps(lambda req, n: json.dumps(proposal()) if 'output_format' in req['prompt']
                            else 'function inc(x) { return 0; }')
            report = M.MicaRun(request(max_calls=2, max_candidates=1), path, apps, inventory()).execute()
            self.assertNotEqual(report['status'], 'done', report)
            frozen = A.freeze([path])
            self.assertEqual(frozen['counts']['provider_calls'], 2)
            self.assertEqual({r['task_class'] for r in frozen['observations']}, {'planning', 'javascript_unit'})
            self.assertEqual({r['status'] for r in frozen['observations']}, {'success', 'failed'})
            self.assertEqual(A.normalize(frozen, G._hash(M.implementation_identity())), frozen)

    def test_actual_direct_success_replay_not_new_measurement(self):
        with tempfile.TemporaryDirectory(prefix='mica-calibration-native-') as tmp:
            path = Path(tmp) / 'run'; apps = FakeApps()
            run = M.MicaRun(request(), path, apps, inventory())
            self.assertEqual(run.execute('direct')['status'], 'done')
            before = A.freeze([path]); run.execute('direct'); after = A.freeze([path])
            self.assertEqual(before, after)
            self.assertEqual(before['counts']['observations'], 1)
            self.assertEqual(len(apps.requests), 1)


if __name__ == '__main__':
    unittest.main()
