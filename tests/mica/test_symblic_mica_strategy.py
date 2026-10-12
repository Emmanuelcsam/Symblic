"""Bounded policy + real native fake-provider journeys; no live stores/models."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.mica import search as M
from symblic.mica import contracts as C
from symblic.mica import strategy as Q
from tests.mica.test_symblic_mica_execution import FakeApps, inventory, proposal, request


def admitted(req, ident='one', *, models=(), policy='refine_or_escalate'):
    plan = M.proposal_to_plan(req, proposal(), ident)
    raw = {'id': ident, 'contracts': copy.deepcopy(plan['contracts']), 'assumptions': plan['assumptions']}
    for contract in raw['contracts']:
        contract.pop('content_hash', None)
        contract['model_eligibility']['models'] = list(models)
        contract['failure_policy']['action'] = policy
    return C.validate_plan(req, raw)


def workers():
    # Equal-cost alternatives are finally ordered by candidate id, a hash that includes the node names. These names
    # keep the order test_return_to_older_graph_records_selected_parent_and_trigger walks through (older graph first).
    return [{**inventory((node,))[0], 'model': model, 'estimated_cost_units': cost,
             'estimated_latency_ms': latency} for node, model, cost, latency in
            [('worker-a', 'costly', 100, 1000), ('worker-b', 'cheap', 1, 10)]]


class PolicyTests(unittest.TestCase):
    def test_joint_graph_worker_choice_and_unknown_overheads(self):
        req = request(max_candidates=4)
        expensive = admitted(req, 'costlyGraph', models=['costly'])
        cheap = admitted(req, 'cheapGraph', models=['cheap'])
        decision = Q.decide(req, [{'plan': expensive, 'depth': 0}, {'plan': cheap, 'depth': 0}],
                            [], workers(), [], 'mica', 0)
        self.assertEqual(decision['selected']['plan_sha256'], cheap['content_hash'])
        self.assertEqual(decision['selected']['routes']['increment']['model'], 'cheap')
        self.assertEqual(decision['ranking_dimension'], 'milliseconds')
        score = decision['selected']['score']
        self.assertIsNone(score['joint_success_probability'])
        self.assertEqual(score['per_child_success_bounds'], [None])
        self.assertIsNone(score['dimensions']['milliseconds']['complete_component_sum'])
        self.assertFalse(score['measured'])

    def test_mixed_units_are_not_compared_and_ties_replay_exactly(self):
        req = request(max_candidates=4); plan = admitted(req)
        inv = workers(); inv[0]['estimated_latency_ms'] = None; inv[1]['estimated_cost_units'] = None
        first = Q.decide(req, [{'plan': plan, 'depth': 0}], [], inv, [], 'mica', 0)
        second = Q.decide(req, [{'plan': plan, 'depth': 0}], [], list(reversed(inv)), [], 'mica', 0)
        self.assertIsNone(first['ranking_dimension'])
        self.assertEqual(first, second)

    def test_and_graph_covers_all_children_and_bounded_pruning_is_visible(self):
        req = request(max_candidates=2)
        plan = admitted(req)
        inv = [{**inventory((f'node{i:02}',))[0], 'model': f'model{i}'} for i in range(1, 12)]
        decision = Q.decide(req, [{'plan': plan, 'depth': 0}], [], inv, [], 'mica', 0)
        self.assertLessEqual(len(decision['candidates']), 2)
        self.assertEqual(decision['selected']['and_contracts'], plan['order'])
        self.assertTrue(any(r['reason'] == 'route_width_bound' for r in decision['pruned']))
        self.assertEqual(decision['limits']['candidate_lifecycles'], 2)
        self.assertEqual(decision['limits']['expansions_per_lifecycle'], 1)

    def test_refinement_and_escalation_policy_and_depth_are_exact(self):
        req = request(max_candidates=4, max_depth=1)
        plan = admitted(req, policy='refine')
        chosen = Q.decide(req, [{'plan': plan, 'depth': 1}], [], workers(), [], 'mica', 0)['selected']
        result = {'status': 'failed', 'contract': 'increment', 'failure': 'TEST_FAILURE', 'failure_policy': 'refine'}
        history = [{'choice': chosen, 'plan': plan, 'result': result}]
        decision = Q.decide(req, [{'plan': plan, 'depth': 1}], history, workers(), [], 'mica', 1)
        self.assertIsNone(decision['selected'])
        self.assertEqual({r['reason'] for r in decision['rejected']},
                         {'failure_policy_does_not_allow_worker_escalation', 'original_depth_bound'})

    def test_search_ablation_does_not_gain_empirical_worker_frontier(self):
        req = request(max_candidates=4); plan = admitted(req)
        inv = workers(); inv[0]['estimated_latency_ms'] = 1; inv[1]['estimated_latency_ms'] = 1000
        decision = Q.decide(req, [{'plan': plan, 'depth': 0}], [], inv, [], 'search', 0)
        self.assertEqual(len(decision['candidates']), 1)
        self.assertEqual(decision['selected']['routes']['increment']['model'], 'cheap')
        self.assertIsNone(decision['ranking_dimension'])

    def test_unresolved_or_terminal_history_cannot_authorize_another_choice(self):
        req = request(max_candidates=4); plan = admitted(req)
        choice = Q.decide(req, [{'plan': plan, 'depth': 0}], [], workers(), [], 'mica', 0)['selected']
        for status in ('unknown', 'stopped', 'blocked', 'exhausted', 'done'):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'cannot authorize'):
                Q.decide(req, [{'plan': plan, 'depth': 0}],
                         [{'choice': choice, 'plan': plan, 'result': {'status': status}}], workers(), [], 'mica', 1)

    def test_invalid_proposal_feedback_is_retained_in_next_expansion(self):
        req = request(max_candidates=2)
        first = Q.decide(req, [], [], workers(), [], 'mica', 0)['selected']
        failure = {'status': 'failed', 'failure': 'INVALID_CONTRACT', 'error': 'unknown dependency fixture'}
        next_choice = Q.decide(req, [], [{'choice': first, 'plan': None, 'result': failure}], workers(), [], 'mica', 1)['selected']
        self.assertEqual(next_choice['trigger']['failure'], 'INVALID_CONTRACT')
        self.assertEqual(next_choice['trigger']['error'], failure['error'])


class StrategyJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-frontier-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'run'

    def execute(self, req, apps, plans=None, inv=None):
        return M.MicaRun(req, self.root, apps, workers() if inv is None else inv).execute('mica', initial_plans=plans)

    def test_policy_actually_selects_graph_and_model_then_replays_without_call(self):
        req = request(max_candidates=4)
        plans = [admitted(req, 'costlyGraph', models=['costly']), admitted(req, 'cheapGraph', models=['cheap'])]
        apps = FakeApps()
        first = self.execute(req, apps, plans)
        self.assertEqual(first['status'], 'done', first)
        self.assertEqual(apps.requests[0]['app']['model'], 'cheap')
        self.assertEqual(first['attempts'][0]['plan_sha256'], plans[1]['content_hash'])
        second = self.execute(req, apps, plans)
        self.assertEqual(first, second)
        self.assertEqual(len(apps.requests), 1)
        receipt = M._read(self.root, 'strategy-000.json')
        self.assertEqual(len(receipt['candidates']), 2)
        self.assertEqual(M._read(self.root, 'branch-000.json')['strategy_sha256'], receipt['sha256'])

    def test_one_candidate_includes_plan_and_build_with_original_calls(self):
        req = request(max_candidates=1, max_calls=2)
        apps = FakeApps(lambda req, n: json.dumps(proposal()) if 'output_format' in req['prompt'] else
                        'function inc(x) { return x + 1; }')
        result = self.execute(req, apps)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 2)
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(result['attempts'][0]['status'], 'done')
        self.assertEqual(result['strategy']['decisions'][0]['kind'], 'propose')

    def test_plan_then_build_has_one_frozen_proposal_and_one_slot(self):
        req = request(max_candidates=2, max_calls=2)
        apps = FakeApps(lambda req, n: json.dumps(proposal()) if 'output_format' in req['prompt'] else
                        'function inc(x) { return x + 1; }')
        planned = M.MicaRun(req, self.root, apps, workers()).plan('mica')
        self.assertEqual(planned['status'], 'planned', planned)
        result = self.execute(req, apps)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 2)
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual([r['kind'] for r in result['strategy']['decisions']], ['propose', 'build'])

    def test_unknown_never_selects_another_alternative_or_dispatches(self):
        req = request(max_candidates=4)
        apps = FakeApps(lambda req, n: RuntimeError('lost acknowledgement'))
        plan = admitted(req)
        first = self.execute(req, apps, [plan])
        second = self.execute(req, apps, [plan])
        self.assertEqual(first['status'], 'unknown', first)
        self.assertEqual(second['status'], 'unknown', second)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(len(list(self.root.glob('strategy-*.json'))), 1)

    def test_crash_after_choice_uses_same_route_and_no_wider_authority(self):
        class Crash(BaseException): pass
        req = request(max_candidates=3); plan = admitted(req); apps = FakeApps()
        with mock.patch.object(M.MicaRun, '_build', side_effect=Crash):
            with self.assertRaises(Crash): self.execute(req, apps, [plan])
        frozen = M._read(self.root, 'strategy-000.json')
        self.assertFalse(apps.requests)
        result = self.execute(req, apps, [plan])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(apps.requests[0]['app']['model'], frozen['selected']['routes']['increment']['model'])
        tampered = {k: v for k, v in frozen.items() if k != 'sha256'}
        tampered['selected']['routes']['increment']['node'] = 'node31'
        M.D._write_json(self.root, 'strategy-000.json', M.D._seal(tampered))
        with self.assertRaisesRegex(M.MicaError, 'Retained strategy differs'):
            self.execute(req, apps, [plan])
        self.assertEqual(len(apps.requests), 1)

    def test_crash_between_choice_file_and_ledger_anchor_recovers_without_reranking(self):
        class Crash(BaseException): pass
        req = request(max_candidates=2); plan = admitted(req); apps = FakeApps()
        original = M.MicaRun._event
        def emit(run, kind, **fields):
            if kind == 'strategy_choice': raise Crash()
            return original(run, kind, **fields)
        with mock.patch.object(M.MicaRun, '_event', new=emit):
            with self.assertRaises(Crash): self.execute(req, apps, [plan])
        frozen = M._read(self.root, 'strategy-000.json')
        self.assertFalse(apps.requests)
        result = self.execute(req, apps, [plan])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(M._read(self.root, 'strategy-000.json'), frozen)
        self.assertEqual(len(apps.requests), 1)

    def test_newer_observation_cannot_rebind_anchored_pending_choice(self):
        class Crash(BaseException): pass
        req = request(max_candidates=2); plan = admitted(req); apps = FakeApps()
        run = M.MicaRun(req, self.root, apps, workers())
        with mock.patch.object(M.MicaRun, '_build', side_effect=Crash):
            with self.assertRaises(Crash): run.execute('mica', initial_plans=[plan])
        observation = {'observation_id': 'later', 'engine': 'ollama', 'model': 'cheap', 'node': 'worker-b',
                       'digest': None, 'task_class': 'implementation', 'status': 'failed', 'cached': False}
        run._event('observation', observation=observation)
        events = run._events()
        replacement = Q.decide(req, [{'plan': plan, 'depth': 0}], [], workers(), [observation], 'mica', 0)
        replacement.update(event_prefix={'count': len(events), 'head': events[-1]['sha256']},
                           inventory_sha256=M.R.digest(run.inventory), history_sha256=M.D._hash([]))
        M.D._write_json(self.root, 'strategy-000.json', M.D._seal(replacement))
        with self.assertRaisesRegex(M.MicaError, 'ledger anchor'):
            self.execute(req, apps, [plan])
        self.assertFalse(apps.requests)

    def test_failed_root_original_check_cannot_be_replaced_by_unit_success(self):
        req = request(max_candidates=2)
        # The unit's example is weaker; the original root example stays binding.
        plan = admitted(req)
        raw = {'id': 'weak', 'contracts': copy.deepcopy(plan['contracts'])}
        raw['contracts'][0].pop('content_hash')
        raw['contracts'][0]['unit']['examples'] = [['inc(0)', '1']]
        plan = C.validate_plan(req, raw)
        apps = FakeApps(lambda req, n: 'function inc(x) { return 1; }')
        result = self.execute(req, apps, [plan])
        self.assertNotEqual(result['status'], 'done')
        self.assertEqual(result['attempts'][0]['failure'], 'INTEGRATION_FAILURE')

    def test_independent_accepted_child_reuses_while_failed_child_changes_worker(self):
        req = request(max_candidates=4, max_calls=6)
        req['requirements'].append({'id': 'identity', 'text': 'Return x unchanged.', 'acceptance': 'TESTED'})
        req['exports'].append({'name': 'identity', 'signature': 'identity(x)'})
        req['tests'].append({'requirement_ids': ['identity'], 'call': 'identity(4)', 'expected': '4'})
        prop = proposal()
        prop['units'].append({'id': 'keep', 'names': ['identity'], 'heading': 'identity(x)',
                              'body': 'Return x unchanged.', 'uses': [], 'examples': [['identity(4)', '4']],
                              'requirements': ['identity']})
        plan = M.proposal_to_plan(req, prop, 'independent')
        raw = {'id': 'independent', 'contracts': copy.deepcopy(plan['contracts'])}
        for contract in raw['contracts']:
            contract.pop('content_hash')
            contract['failure_policy']['action'] = 'escalate'
        plan = C.validate_plan(req, raw)
        def callback(req, number):
            if 'identity(x)' in req['prompt']:
                return 'function identity(x) { return x; }'
            return ('function inc(x) { return x + 1; }' if req['app']['model'] == 'costly' else
                    'function inc(x) { return x - 1; }')
        apps = FakeApps(callback)
        result = self.execute(req, apps, [plan])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(sum('identity(x)' in r['prompt'] for r in apps.requests), 1)
        self.assertTrue(any(d['reused'] for a in result['attempts'][1:] for d in a['decisions']))
        self.assertEqual([r['app']['model'] for r in apps.requests if 'identity(x)' not in r['prompt']],
                         ['cheap', 'costly'])
        self.assertLessEqual(result['calls'], req['budget']['max_calls'])

    def test_return_to_older_graph_records_selected_parent_and_trigger(self):
        req = request(max_candidates=3, max_calls=6)
        older = admitted(req, 'older', models=['cheap'], policy='refine')
        newer = admitted(req, 'newer', models=['cheap'], policy='escalate')
        original = older['contracts'][0]
        refined = {'units': [
            {'id': 'increment', 'names': ['inc'], 'heading': original['unit']['heading'],
             'body': original['unit']['body'], 'uses': ['plusOne'], 'examples': [], 'requirements': ['increment']},
            {'id': 'helper', 'names': ['plusOne'], 'heading': 'plusOne(x)', 'body': 'Return x plus one.',
             'uses': [], 'examples': [['plusOne(2)', '3']], 'requirements': ['increment']} ]}
        def callback(req, number):
            if number <= 2:
                return 'function inc(x) { return x - 1; }'
            if 'output_format' in req['prompt']:
                return json.dumps(refined)
            return ('function inc(x) { return plusOne(x); }' if 'inc(x)' in req['prompt'] else
                    'function plusOne(x) { return x + 1; }')
        apps = FakeApps(callback)
        result = self.execute(req, apps, [older, newer])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual([a['plan_sha256'] for a in result['attempts'][:2]],
                         [older['content_hash'], newer['content_hash']])
        selected = M._read(self.root, 'strategy-002.json')['selected']
        branch = M._read(self.root, 'branch-002.json')
        self.assertEqual(selected['kind'], 'refine')
        self.assertEqual(branch['parent_plan'], older['content_hash'])
        self.assertEqual(branch['trigger'], selected['trigger'])
        self.assertEqual(branch['trigger']['failure_policy'], 'refine')
        self.assertEqual(branch['depth'], selected['depth'])
        self.assertEqual(self.execute(req, apps, [older, newer]), result)
        self.assertEqual(len(apps.requests), 5)
        # A resealed misleading lineage is rejected, even with unchanged code/result.
        branch['parent_plan'] = newer['content_hash']
        M.D._write_json(self.root, 'branch-002.json', M.D._seal({k:v for k,v in branch.items() if k != 'sha256'}))
        with self.assertRaisesRegex(M.MicaError, 'Retained branch differs'):
            self.execute(req, apps, [older, newer])
        self.assertEqual(len(apps.requests), 5)

    def test_refinement_keeps_original_wrapper_and_uses_existing_refiner(self):
        req = request(max_candidates=2, max_calls=5)
        plan = admitted(req, policy='refine')
        original = plan['contracts'][0]
        refined = {'units': [
            {'id': 'increment', 'names': ['inc'], 'heading': original['unit']['heading'],
             'body': original['unit']['body'], 'uses': ['plusOne'], 'examples': [], 'requirements': ['increment']},
            {'id': 'helper', 'names': ['plusOne'], 'heading': 'plusOne(x)', 'body': 'Return x plus one.',
             'uses': [], 'examples': [['plusOne(2)', '3']], 'requirements': ['increment']} ]}
        def callback(req, number):
            if 'output_format' in req['prompt']:
                return json.dumps(refined)
            if number == 1:
                return 'function inc(x) { return x - 1; }'
            if 'inc(x)' in req['prompt']:
                return 'function inc(x) { return plusOne(x); }'
            return 'function plusOne(x) { return x + 1; }'
        apps = FakeApps(callback)
        result = self.execute(req, apps, [plan], inventory())
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual([r['kind'] for r in result['strategy']['decisions']], ['build', 'refine', 'build'])
        new = M._read(self.root, 'branch-001.json')['plan']
        wrapper = next(c for c in new['contracts'] if c['contract_id'] == 'increment')
        for field in ('body', 'heading', 'names'):
            self.assertEqual(wrapper['unit'][field], original['unit'][field])
        self.assertIn(original['unit']['examples'][0], wrapper['unit']['examples'])
        self.assertEqual(len(apps.requests), 4)


if __name__ == '__main__':
    unittest.main()
