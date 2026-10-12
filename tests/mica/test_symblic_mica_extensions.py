"""Cross-run calibration and actual module output through native construction."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.graph import run as G
from symblic.mica import search as M
from symblic.mica import bundle as B
from symblic.mica import bench as Bench
from symblic.mica import calibration as H
from symblic.mica import contracts as C
from symblic.mica import project as P
from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request, proposed_unit
from tests.mica.test_symblic_mica_project import OBJECTIVE, fixture_reply


class ExtensionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mica-extensions-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_script_cannot_silently_ignore_additional_outputs(self):
        req = request(); req['allowed_outputs'].append('ignored.js')
        with self.assertRaises(C.ContractError): C.normalize_request(req)
        req['artifact_format'] = 'javascript_modules'
        self.assertEqual(C.normalize_request(req)['artifact_format'], 'javascript_modules')

    def test_planner_can_assign_declared_module_paths_without_file_authority(self):
        req = {**request(), 'artifact_format': 'javascript_modules',
               'allowed_outputs': ['package/index.mjs', 'package/helpers/increment.mjs']}
        unit = proposed_unit('increment', 'inc', 'Return x plus one.', [['inc(2)', '3']])
        unit['output_path'] = 'package/helpers/increment.mjs'
        plan = M.proposal_to_plan(req, {'units': [unit]})
        self.assertEqual(plan['contracts'][0]['output_artifacts'], [unit['output_path']])
        for path in ('outside.js', 'package/index.mjs', '/tmp/increment.js'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                M.proposal_to_plan(req, {'units': [{**unit, 'output_path': path}]})
        apps = FakeApps()
        result = M.MicaRun(req, self.root / 'named', apps, inventory()).execute('static', initial_plans=[plan])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual({f['path'] for f in result['bundle']['files']}, set(req['allowed_outputs']))

    def test_benchmark_scores_actual_modules_with_hidden_cases_outside_construction(self):
        req = C.normalize_request({**request(), 'artifact_format': 'javascript_modules'})
        apps = FakeApps()
        result = M.MicaRun(req, self.root / 'scored', apps, inventory()).execute('direct')
        self.assertEqual(result['status'], 'done', result)
        fixture = {'id': 'module-inc', 'family': 'integer', 'split': 'heldout', 'request': req,
                   'hidden_tests': [['inc(8675309)', '8675310']]}
        bench = Bench.MicaBenchmark.freeze(self.root / 'benchmarks', 'module-check', [fixture],
                  model={'primary': ['fixture-small'], 'fallback': [], 'stronger_fallback': [], 'settings': {}},
                  budget=req['budget'])
        with mock.patch.object(Bench, '_js_evaluate', side_effect=AssertionError('flattened scorer called')):
            graded = bench.run_assignment(bench.assignments()[0]['id'], lambda **kwargs: result)
        self.assertEqual(graded['grade']['status'], 'tested', graded)
        self.assertEqual(graded['grade']['result']['scope'], 'finite_external_strict_module_examples')
        self.assertNotIn('8675309', json.dumps(apps.requests))

    def test_actual_multifile_dependency_graph_and_replay(self):
        req = {**request(), 'artifact_format': 'javascript_modules'}
        plan = M.proposal_to_plan(req, {'units': [
            proposed_unit('base', 'base', 'Return x.', [['base(2)', '2']]),
            proposed_unit('increment', 'inc', 'Use base(x), then add one.', [['inc(2)', '3']], ['base'])]})
        apps = FakeApps(lambda req, n: 'function base(x) { return x; }' if n == 1 else
                        'function inc(x) { return base(x) + 1; }')
        folder = self.root / 'bundle'
        result = M.MicaRun(req, folder, apps, inventory()).execute('static', initial_plans=[plan])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 2)
        bundle = result['bundle']
        self.assertEqual({f['path'] for f in bundle['files']}, {'result.js', 'units/base.js', 'units/increment.js'})
        self.assertTrue(result['module_checks']['passed'])
        self.assertTrue(B.verify_bundle(bundle, runtime_identity=M.implementation_identity())['ok'])
        self.assertEqual(B.archive(bundle), B.archive(copy.deepcopy(bundle)))
        held_out = B.check_cases(bundle, [['inc(-8)', '-7'], ['typeof base', '"undefined"']])
        self.assertTrue(held_out['passed'], held_out)
        self.assertEqual(M.MicaRun(req, folder, apps, inventory()).execute('static', initial_plans=[plan]), result)
        self.assertEqual(len(apps.requests), 2)

    def test_modules_project_retains_exact_format_and_read_only_bundle(self):
        apps = FakeApps(fixture_reply)
        folder = self.root / 'project'
        run = P.MicaProject(OBJECTIVE, folder, apps, inventory(),
                            {'max_calls': 3, 'wall_seconds': 120}, ['result.js'], artifact_format='javascript_modules')
        result = run.execute('direct')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['request']['artifact_format'], 'javascript_modules')
        self.assertEqual(len(result['bundle']['files']), 2)
        with mock.patch.object(B.subprocess, 'Popen', side_effect=AssertionError('reader executed a child')):
            self.assertEqual(P.read_project_result(folder), result)
        self.assertEqual(len(apps.requests), 2)

    def test_frozen_calibration_counts_only_current_calls_and_exports_only_new_evidence(self):
        first = self.root / 'first'
        M.MicaRun(request(), first, FakeApps(), inventory()).execute('direct')
        seed = H.freeze([first])
        apps = FakeApps()
        second = self.root / 'second'
        result = M.MicaRun(request(), second, apps, inventory(), calibration=seed).execute('direct')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['calibration'], {'sha256': seed['sha256'], 'seed_observations': 1, 'fresh_observations': 1})
        next_seed = H.freeze([second])
        self.assertEqual(next_seed['counts']['observations'], 1)
        self.assertEqual(next_seed['sources'][0]['seed_observations'], 1)
        self.assertNotEqual(next_seed['observations'][0]['observation_id'], seed['observations'][0]['observation_id'])
        with self.assertRaises(ValueError):
            M.MicaRun(request(), second, apps, inventory()).execute('direct')
        self.assertEqual(len(apps.requests), 1)

    def test_historical_digest_does_not_promote_a_cold_current_inventory(self):
        run = M.MicaRun(request(), self.root / 'cold', FakeApps(), inventory())
        contract = M.direct_plan(C.normalize_request(request()))['contracts'][0]
        run.observations = [{'observation_id': 'cal/' + 'b' * 64 + '/build-000-whole',
            'engine': 'ollama', 'model': 'fixture-small', 'node': 'node-a', 'digest': 'a' * 64,
            'task_class': contract['model_eligibility']['task_class'], 'status': 'success',
            'contract_hash': contract['content_hash'], 'checker_hash': G._hash(M.implementation_identity()),
            'calls': 1, 'cached': False, 'input_tokens': None, 'output_tokens': None, 'latency_ms': None}]
        self.assertIsNone(run._routes(contract, 'mica')[0]['digest'])

    def test_equal_millisecond_independent_runs_have_distinct_frozen_identities(self):
        fixed = M.time.time()
        with mock.patch.object(M.time, 'time', return_value=fixed):
            for name in ('one', 'two'):
                M.MicaRun(request(), self.root / name, FakeApps(), inventory()).execute('direct')
        seed = H.freeze([self.root / 'one', self.root / 'two'])
        self.assertEqual(seed['counts']['observations'], 2)
        self.assertEqual(len({s['manifest_sha256'] for s in seed['sources']}), 2)


if __name__ == '__main__':
    unittest.main()
