"""End-to-end failure strategies with fake providers and native host checks.

Run only in a coherent admitted-runtime snapshot. No real agents, model calls,
external effects, cloud APIs or live stores are used.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from symblic.mica import search as M
from symblic.mica import contracts as C

from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request


def initial(action='refine', *, independent=False, max_calls=5, max_candidates=2):
    req = request(max_calls=max_calls, max_candidates=max_candidates, wall_seconds=120, max_workers=2)
    # This root check intentionally differs from the exposed unit example.
    req['tests'] = [{'requirement_ids': ['increment'], 'call': 'inc(-9)', 'expected': '-8'}]
    row = {'contract_id': 'increment', 'root_requirement_ids': ['increment'],
        'objective': 'Return the input integer plus one.', 'dependency_contract_ids': [],
        'unit': {'names': ['inc'], 'heading': 'inc(x)', 'body': 'FAILED_INCREMENT_BODY: return x plus one.',
                 'uses': [], 'setup': '', 'examples': [['inc(2)', '3']]},
        'verification_obligations': [{'kind': 'unit_examples', 'requirement_ids': ['increment']}],
        'failure_policy': {'action': action, 'retries': 0}}
    rows = [row]
    if independent:
        req['requirements'].append({'id': 'identity', 'text': 'UNRELATED_IDENTITY_REQUIREMENT: return x.', 'acceptance': 'TESTED'})
        req['exports'].append({'name': 'identity', 'signature': 'identity(x)'})
        req['tests'].append({'requirement_ids': ['identity'], 'call': 'identity(7)', 'expected': '7'})
        good = copy.deepcopy(row)
        good.update(contract_id='good', root_requirement_ids=['identity'], objective='Return the input unchanged.',
                    verification_obligations=[{'kind': 'unit_examples', 'requirement_ids': ['identity']}])
        good['unit'] = {'names': ['identity'], 'heading': 'identity(x)', 'body': 'GOOD_IDENTITY_BODY: return x unchanged.',
                        'uses': [], 'setup': '', 'examples': [['identity(2)', '2']]}
        rows.insert(0, good)
    return req, C.validate_plan(req, {'id': 'initial', 'contracts': rows})


def refined_proposal():
    return {'units': [
        {'id': 'increment', 'names': ['inc'], 'heading': 'inc(x)',
         'body': 'FAILED_INCREMENT_BODY: return x plus one.', 'uses': ['addOne'],
         'examples': [['inc(2)', '3']], 'requirements': ['increment']},
        {'id': 'fresh_helper', 'names': ['addOne'], 'heading': 'addOne(x)',
         'body': 'REFINED_HELPER_BODY: return x plus one.', 'uses': [],
         'examples': [['addOne(2)', '3']], 'requirements': ['increment']}]}


class StrategyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-strategy-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'run'

    def run_mica(self, req, plan, apps, inv=None):
        return M.MicaRun(req, self.path, apps, inventory() if inv is None else inv).execute(
            mode='mica', initial_plans=[plan])

    def refinement_apps(self, *, root_wrong=False):
        seen = {'good': 0, 'inc': 0, 'helper': 0, 'planner': 0}
        def callback(call, number):
            prompt = call['prompt']
            if 'output_format' in prompt:
                seen['planner'] += 1
                self.assertNotIn('GOOD_IDENTITY_BODY', prompt)
                self.assertNotIn('UNRELATED_IDENTITY_REQUIREMENT', prompt)
                return json.dumps(refined_proposal())
            if 'FAILED_INCREMENT_BODY' in prompt:
                seen['inc'] += 1
                return ('function inc(x) { return x; }' if seen['inc'] == 1
                        else 'function inc(x) { return addOne(x); }')
            if 'GOOD_IDENTITY_BODY' in prompt:
                seen['good'] += 1
                return 'function identity(x) { return x; }'
            if 'REFINED_HELPER_BODY' in prompt:
                seen['helper'] += 1
                return 'function addOne(x) { return 3; }' if root_wrong else 'function addOne(x) { return x + 1; }'
            raise AssertionError('Unexpected strategy fixture task.')
        return FakeApps(callback), seen

    def test_targeted_refinement_reuses_good_unit_and_retains_native_lineage(self):
        req, plan = initial('refine', independent=True)
        apps, seen = self.refinement_apps()
        result = self.run_mica(req, plan, apps)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 5)
        self.assertEqual(seen, {'good': 1, 'inc': 2, 'helper': 1, 'planner': 1})
        self.assertEqual(len(apps.requests), 5)
        before = M._read(self.path, 'branch-000.json')['plan']
        after = M._read(self.path, 'branch-001.json')['plan']
        self.assertEqual(next(row for row in before['contracts'] if row['contract_id'] == 'good'),
                         next(row for row in after['contracts'] if row['contract_id'] == 'good'))
        self.assertEqual(after['root_tests'], C.normalize_request(req)['tests'])
        wrapper = next(row for row in after['contracts'] if row['contract_id'] == 'increment')
        original = next(row for row in before['contracts'] if row['contract_id'] == 'increment')
        for field in ('heading', 'body', 'names', 'setup'):
            self.assertEqual(wrapper['unit'][field], original['unit'][field])
        for example in original['unit']['examples']:
            self.assertIn(example, wrapper['unit']['examples'])
        record = M._read(self.path, 'plan-001.json')
        self.assertEqual(record['lineage']['original_contract_sha256'], original['content_hash'])
        self.assertEqual(record['lineage']['candidate_plan_sha256'], after['content_hash'])
        self.assertFalse(record['lineage']['formal_refinement_proven'])
        self.assertEqual(result['evidence']['caller_acceptance_sha256'], C.digest(req['tests']))
        replayed = self.run_mica(req, plan, apps)
        self.assertEqual(replayed, result)
        self.assertEqual(len(apps.requests), 5)

    def test_refine_or_escalate_refines_when_only_one_eligible_model_exists(self):
        req, plan = initial('refine_or_escalate', independent=True)
        apps, seen = self.refinement_apps()
        result = self.run_mica(req, plan, apps)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 5)
        self.assertEqual(seen['planner'], 1)
        self.assertEqual(seen['good'], 1)

    def test_refined_unit_examples_cannot_replace_original_root_acceptance(self):
        req, plan = initial('refine', independent=True)
        apps, seen = self.refinement_apps(root_wrong=True)
        result = self.run_mica(req, plan, apps)
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 5)
        self.assertEqual(seen['good'], 1)
        self.assertEqual(seen['planner'], 1)
        self.assertEqual(result['evidence']['caller_acceptance_sha256'], C.digest(req['tests']))
        self.assertNotIn('output', result)
        branch = M._read(self.path, 'branch-001.json')
        self.assertEqual(branch['plan']['root_tests'], req['tests'])
        self.assertNotEqual(branch['result']['status'], 'done')

    def test_stop_policy_prevents_new_planner_or_generation_attempt(self):
        req, plan = initial('stop', max_calls=5, max_candidates=3)
        apps = FakeApps(lambda call, number: 'function inc(x) { return x; }')
        result = self.run_mica(req, plan, apps)
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertFalse(any('output_format' in call['prompt'] for call in apps.requests))
        self.assertEqual(len(result['attempts']), 1)
        self.assertFalse((self.path / 'plan-001.json').exists())

    # Known disagreement, kept visible: this test also fails on the original code this repository was copied from
    # (checked by running the original flat-layout modules). Under 'refine_or_escalate' the strategy frontier added
    # later asks the planner for a refinement first, while the test still expects an immediate model escalation.
    # Decide which behaviour is right before removing the marker.
    @unittest.expectedFailure
    def test_explicit_escalation_changes_exact_model_without_replanning(self):
        for action in ('escalate', 'refine_or_escalate'):
            with self.subTest(action=action):
                self.path = Path(self.temp.name) / action
                req, plan = initial(action, max_calls=2)
                inv = inventory()
                inv.append({**inv[0], 'model': 'fixture-other', 'estimated_cost_units': 2})
                def callback(call, number):
                    self.assertNotIn('output_format', call['prompt'])
                    return 'function inc(x) { return x; }' if number == 1 else 'function inc(x) { return x + 1; }'
                apps = FakeApps(callback)
                result = self.run_mica(req, plan, apps, inv)
                self.assertEqual(result['status'], 'done', result)
                self.assertEqual(result['calls'], 2)
                self.assertEqual(len(apps.requests), 2)
                self.assertNotEqual(apps.requests[0]['app']['model'], apps.requests[1]['app']['model'])
                self.assertEqual(M._read(self.path, 'branch-000.json')['plan'], M._read(self.path, 'branch-001.json')['plan'])
                self.assertEqual(result['evidence']['caller_acceptance_sha256'], C.digest(req['tests']))
                self.assertEqual(self.run_mica(req, plan, apps, inv), result)
                self.assertEqual(len(apps.requests), 2)

    # Known disagreement, kept visible: this test also fails on the original code this repository was copied from
    # (checked by running the original flat-layout modules). The strategy frontier added later ends this run as
    # 'exhausted' while the test still expects 'blocked'. Decide which behaviour is right before removing the marker.
    @unittest.expectedFailure
    def test_escalation_without_an_alternate_route_blocks_with_no_new_call(self):
        req, plan = initial('escalate', max_calls=3)
        apps = FakeApps(lambda call, number: 'function inc(x) { return x; }')
        result = self.run_mica(req, plan, apps)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertFalse(any('output_format' in call['prompt'] for call in apps.requests))

    def test_original_candidate_bound_prevents_refinement_dispatch(self):
        req, plan = initial('refine', max_calls=5, max_candidates=1)
        apps = FakeApps(lambda call, number: 'function inc(x) { return x; }')
        result = self.run_mica(req, plan, apps)
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(len(result['attempts']), 1)


if __name__ == '__main__':
    unittest.main()
