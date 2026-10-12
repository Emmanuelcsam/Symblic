"""Operational graph-policy experiments with fake Apps and private temp stores."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.graph import run as R
from symblic.js import check as JS
from symblic.policy import graph as W
from symblic.policy import learning as P
from symblic.policy import store as E
from tests.graph.test_symblic_graph_run import FakeApps, graph, node, policy


def plan(root):
    policies = []
    for model in ('small', 'large'):
        route = policy()
        route['routes'][0]['model'] = model
        policies.append(route)
    fixtures = []
    for split in ('training', 'heldout'):
        n = node('A', source='note ' + split + '.\nask answer: Int "answer" with effort=low, retries=0, budget=20000.')
        n['allowed']['models'].append('large')
        g = graph(n, max_calls=3)['graph']
        value = {'graph': g, 'output_node': 'A'}
        fixtures.append(E.case_fixture(value, 42, family_hash=P.digest(split)))
    tp = {'version': 1, 'candidates': [{'sha256': P.digest(p), 'policy': p} for p in policies],
          'baseline': P.digest(policies[0]), 'cases': [fixtures[0]['case']],
          'budget': {'max_calls': 3, 'max_cost_units': 3},
          'objective': {'max_score': 10, 'score_weight': 10, 'call_weight': 1, 'cost_weight': 1,
                        'unknown_cost': 'reject', 'tie_break': 'policy_sha256_ascending', 'min_heldout_gain': 1}}
    hp = {'version': 1, 'training_plan_hash': P.digest(tp), 'cases': [fixtures[1]['case']]}
    exp = E.PolicyExperiment.freeze(root, 'experiment', tp, hp, [fixtures[0]], [fixtures[1]], cost_unit=W.COST_UNIT)
    return exp, policies, fixtures


class PolicyGraph(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)

    def test_complete_route_learning_journey_and_completed_recovery(self):
        exp, policies, _ = plan(self.root / 'experiments')
        apps = FakeApps(lambda req: 42 if req['app']['model'] == 'large' else 0)
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps)
        for stage in ('training', 'heldout'):
            for assignment in exp.assignments(stage):
                row = exp.run_assignment(stage, assignment['candidate_sha256'], assignment['case_hash'], runner=runner)
                self.assertEqual(row['record']['attempts'], [{'calls': 1, 'cost_units': 1}])
            if stage == 'training':
                selected = exp.seal_training()
                self.assertEqual(selected['selected']['sha256'], P.digest(policies[1]))
        self.assertTrue(exp.seal_heldout()['improvement'])
        self.assertEqual(len(apps.calls), 4)
        intent = next(exp.path.glob('assignment-*/intent.json'))
        request = E._read(intent)
        resolved = runner.resolve(request)
        self.assertTrue(resolved['complete'])
        self.assertEqual(len(apps.calls), 4)
        self.assertEqual(len(resolved['checks']), 2)
        self.assertEqual(resolved['checks'][1]['scope'], 'encoded_predicate')

    def test_preflight_rejects_effects_missing_output_and_insufficient_budget(self):
        exp, policies, fixtures = plan(self.root / 'experiments')
        value = fixtures[0]['input']
        self.assertEqual(W.validate_case(value, policies[0], budget={'max_calls': 3, 'max_cost_units': 3})['policy'], policies[0])
        for bad in (dict(value, output_node='Missing'), dict(value, extra=True)):
            with self.assertRaises((E.PolicyStoreError, R.G.GraphError)):
                W.validate_case(bad, policies[0])
        with self.assertRaisesRegex(E.PolicyStoreError, 'policy_graph_budget'):
            W.validate_case(value, policies[0], budget={'max_calls': 2, 'max_cost_units': 3})
        effectful = copy.deepcopy(value)
        effectful['graph']['nodes'][0]['effect_risk'] = 'read'
        with self.assertRaisesRegex(E.PolicyStoreError, 'effects_unsupported'):
            W.validate_case(effectful, policies[0])
        self.assertEqual(exp.status()['stage'], 'training')

    def test_uncertain_call_and_resolver_never_redispatch(self):
        exp, _, _ = plan(self.root / 'experiments')
        def disconnected(_):
            raise RuntimeError('disconnected after dispatch')
        apps = FakeApps(disconnected)
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps)
        assignment = exp.assignments('training')[0]
        args = ('training', assignment['candidate_sha256'], assignment['case_hash'])
        with self.assertRaisesRegex(E.PolicyStoreError, 'incomplete_outcome'):
            exp.run_assignment(*args, runner=runner)
        request = E._read(next(exp.path.glob('assignment-*/intent.json')))
        resolved = runner.resolve(request)
        self.assertFalse(resolved['complete'])
        self.assertEqual(resolved['attempts'][0]['calls'], 1)
        self.assertEqual(resolved['status'], 'uncertain')
        self.assertEqual(len(apps.calls), 1)
        with self.assertRaisesRegex(E.PolicyStoreError, 'incomplete_outcome'):
            exp.reconcile_assignment(*args, resolver=runner.resolve)
        self.assertEqual(len(apps.calls), 1)

    def test_policy_store_crash_after_graph_done_reconciles_without_new_model_call(self):
        exp, _, _ = plan(self.root / 'experiments')
        apps = FakeApps(42)
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps)
        assignment = exp.assignments('training')[0]
        args = ('training', assignment['candidate_sha256'], assignment['case_hash'])
        def interrupted(request):
            runner(request)
            raise RuntimeError('host crashed before returning completed result')
        with self.assertRaisesRegex(E.PolicyStoreError, 'runner_unresolved'):
            exp.run_assignment(*args, runner=interrupted)
        result = exp.reconcile_assignment(*args, resolver=runner.resolve)
        self.assertEqual(result['record']['score'], 10)
        self.assertEqual(len(apps.calls), 1)

    def test_forged_request_identity_and_cost_unit_refused_before_dispatch(self):
        exp, _, _ = plan(self.root / 'experiments')
        captured = []
        assignment = exp.assignments('training')[0]
        def capture(request):
            captured.append(request)
            raise RuntimeError()
        with self.assertRaises(E.PolicyStoreError):
            exp.run_assignment('training', assignment['candidate_sha256'], assignment['case_hash'], runner=capture)
        apps = FakeApps()
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps)
        for key, value in (('assignment_id', '0' * 64), ('candidate_sha256', '0' * 64), ('cost_unit', 'dollars')):
            altered = dict(captured[0], **{key: value})
            with self.assertRaises(E.PolicyStoreError):
                runner(altered)
        self.assertFalse(apps.calls)

    def test_failed_attempt_and_retry_both_count_toward_exact_call_cost(self):
        n = node('A', retries=1, call_limit=1, max_calls=2)
        value = {'graph': graph(n, max_calls=2)['graph'], 'output_node': 'A'}
        candidate = policy()
        fixture = E.case_fixture(value, 42, family_hash=P.digest('retry'))
        frozen = P.digest('frozen-test')
        case, ch = fixture['case']['case_hash'], P.digest(candidate)
        request = {'version': 1, 'assignment_id': P.digest([frozen, 'training', ch, case]),
                   'experiment_sha256': frozen, 'stage': 'training', 'candidate_sha256': ch,
                   'case_hash': case, 'policy': candidate, 'input': value,
                   'budget': {'max_calls': 2, 'max_cost_units': 2}, 'cost_unit': W.COST_UNIT}
        replies = iter([-1, 42])
        apps = FakeApps(lambda _: next(replies))
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps)
        result = runner(request)
        self.assertEqual(result['status'], 'done')
        self.assertEqual(result['output'], 42)
        self.assertEqual([row['status'] for row in result['attempts']], ['failed', 'done'])
        self.assertEqual(sum(row['calls'] for row in result['attempts']), 2)
        self.assertEqual(sum(row['cost_units'] for row in result['attempts']), 2)
        self.assertEqual(runner.resolve(request), result)
        self.assertEqual(len(apps.calls), 2)

    def test_stop_interrupted_assignment_never_graded_failure_and_resumes_cleanly(self):
        exp, policies, _ = plan(self.root / 'experiments')
        class Interrupted(BaseException):
            pass

        def stop_before_call(stage, action):
            if stage == 'started':
                raise Interrupted('stopped without owner cancel before dispatch')

        runner = W.GraphPolicyRunner(self.root / 'graphs', FakeApps(42))
        assignment = exp.assignments('training')[0]
        args = ('training', assignment['candidate_sha256'], assignment['case_hash'])
        with patch.object(R.GraphRun, '_observe', side_effect=stop_before_call):
            with self.assertRaises(Interrupted):
                exp.run_assignment(*args, runner=runner)
        # Assignment is not terminal and not graded as failed score 0
        self.assertEqual(exp.assignments('training')[0]['state'], 'inflight')
        # Resolved is incomplete/uncertain, not complete
        request = E._read(next(exp.path.glob('assignment-*/intent.json')))
        self.assertFalse(runner.resolve(request)['complete'])
        self.assertEqual(runner.resolve(request)['status'], 'uncertain')
        # Now on resume, fresh app succeeds with 42
        fresh_apps = FakeApps(42)
        fresh_runner = W.GraphPolicyRunner(self.root / 'graphs', fresh_apps)
        res = exp.reconcile_assignment(*args, resolver=fresh_runner.recover)
        self.assertEqual(res['record']['score'], 10)
        self.assertEqual(res['record']['status'], 'success')
        self.assertEqual(len(fresh_apps.calls), 1)

    def test_terminal_canceled_assignment_cannot_auto_reset(self):
        exp, policies, _ = plan(self.root / 'experiments')
        stop = W.threading.Event()
        def canceling_app(req):
            stop.set()
            return {'ok': False, 'error': 'stopped'}
        apps = FakeApps(canceling_app)
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps, stop=stop)
        assignment = exp.assignments('training')[0]
        args = ('training', assignment['candidate_sha256'], assignment['case_hash'])
        with self.assertRaises(E.PolicyStoreError):
            exp.run_assignment(*args, runner=runner)
        self.assertEqual(exp.assignments('training')[0]['state'], 'inflight')
        request = E._read(next(exp.path.glob('assignment-*/intent.json')))
        fresh_runner = W.GraphPolicyRunner(self.root / 'graphs', FakeApps(42))
        recoverable, reason = fresh_runner.is_recoverable(request)
        self.assertFalse(recoverable)
        self.assertIn('canceled', reason)
        with self.assertRaisesRegex(E.PolicyStoreError, 'canceled'):
            fresh_runner.recover(request)

    def test_crash_mid_assignment_with_zero_calls_resumes_without_uncertainty(self):
        exp, _, _ = plan(self.root / 'experiments')
        apps = FakeApps(42)
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps)
        assignment = exp.assignments('training')[0]
        args = ('training', assignment['candidate_sha256'], assignment['case_hash'])
        # Simulate crash at stage 'started' before any provider call
        def crash_on_start(stage, action):
            if stage == 'started':
                raise BaseException('crash mid-assignment before provider call')
        with patch.object(R.GraphRun, '_observe', side_effect=crash_on_start):
            with self.assertRaises(BaseException):
                exp.run_assignment(*args, runner=runner)
        self.assertEqual(exp.assignments('training')[0]['state'], 'inflight')
        self.assertEqual(len(apps.calls), 0)
        request = E._read(next(exp.path.glob('assignment-*/intent.json')))
        recoverable, reason = runner.is_recoverable(request)
        self.assertTrue(recoverable)
        self.assertIsNone(reason)
        # Reconcile recovers native execution exactly once
        result = exp.reconcile_assignment(*args, resolver=runner.recover)
        self.assertEqual(result['record']['score'], 10)
        self.assertEqual(len(apps.calls), 1)

    def test_crash_mid_assignment_with_uncertain_call_refuses_continuation(self):
        exp, _, _ = plan(self.root / 'experiments')
        def disconnected(_):
            raise RuntimeError('disconnected after dispatch')
        apps = FakeApps(disconnected)
        runner = W.GraphPolicyRunner(self.root / 'graphs', apps)
        assignment = exp.assignments('training')[0]
        args = ('training', assignment['candidate_sha256'], assignment['case_hash'])
        with self.assertRaisesRegex(E.PolicyStoreError, 'incomplete_outcome'):
            exp.run_assignment(*args, runner=runner)
        request = E._read(next(exp.path.glob('assignment-*/intent.json')))
        recoverable, reason = runner.is_recoverable(request)
        self.assertFalse(recoverable)
        self.assertIn('unfinished external intent', reason)
        with self.assertRaisesRegex(E.PolicyStoreError, 'resolver_unresolved'):
            exp.reconcile_assignment(*args, resolver=runner.recover)
        self.assertEqual(len(apps.calls), 1)


if __name__ == '__main__':
    unittest.main()
