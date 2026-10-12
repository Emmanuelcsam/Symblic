import copy
import unittest

from symblic.mica.contracts import ContractError
from symblic.mica import routing as R


def model(name='small', node='node-a', sha='a'):
    return {'engine': 'ollama', 'model': name, 'node': node, 'digest': sha * 64 if sha else None,
            'ready': True, 'available': True, 'context_chars': 24000, 'estimated_cost_units': 1}


def observation(i, name='small', status='success', sha='a'):
    return {'observation_id': str(i), 'engine': 'ollama', 'model': name, 'node': 'node-a',
            'digest': sha * 64 if sha else None, 'task_class': 'javascript_unit', 'status': status,
            'contract_hash': 'c' * 64, 'checker_hash': 'd' * 64}


class RoutingTest(unittest.TestCase):
    def test_cold_inventory_never_invents_readiness(self):
        value = R.normalize_inventory([{'engine': 'ollama', 'model': 'small', 'node': 'node-a'}])[0]
        self.assertFalse(value['ready']); self.assertFalse(value['available'])
        self.assertIsNone(value['digest']); self.assertIsNone(value['estimated_cost_units'])
        self.assertEqual(R.rank_models({}, [value], []), [])

    def test_local_exact_identities_only(self):
        for row in ({**model(), 'engine': 'claude'}, {**model(), 'digest': 'fake'}, {**model(), 'node': '../host'}):
            with self.assertRaises(ContractError): R.normalize_inventory([row])
        with self.assertRaises(ContractError): R.normalize_inventory([model(), model()])
        with self.assertRaises(ContractError): R.normalize_inventory([{**model(), 'ready': 1}])

    def test_missing_counters_stay_unknown(self):
        rows = [observation(1), {**observation(2, status='failed'), 'calls': 2}]
        result = R.summarize(rows)['groups'][0]
        self.assertEqual(result['observations'], 2)
        self.assertEqual(result['success_rate'], 0.5)
        calls = result['measured_counters']['calls']
        self.assertEqual(calls, {'known_sum': 2, 'known_observations': 1, 'unknown_observations': 1, 'complete_sum': None})
        self.assertIsNone(result['measured_counters']['latency_ms']['complete_sum'])
        self.assertEqual(result['independence'], 'not_established')

    def test_exact_observation_ids_deduplicate_but_conflicts_refuse(self):
        one = observation(1)
        self.assertEqual(R.summarize([one, copy.deepcopy(one)])['unique_observations'], 1)
        with self.assertRaises(ContractError): R.summarize([one, {**one, 'status': 'failed'}])

    def test_cached_results_are_not_new_observations(self):
        report = R.summarize([{**observation(1), 'cached': True}])['groups'][0]
        self.assertEqual(report['observations'], 0)
        self.assertEqual(report['cached_observations'], 1)
        self.assertIsNone(report['wilson_lower_bound'])

    def test_wilson_reduces_small_sample_overconfidence(self):
        rows = [observation('one', name='one')]
        rows += [observation(i, name='many', status='success' if i < 9 else 'failed') for i in range(10)]
        ranked = R.rank_models({}, [model('one'), model('many')], rows)
        self.assertEqual([r['model'] for r in ranked], ['many', 'one'])
        self.assertLess(ranked[1]['ranking_lower_bound'], 0.21)
        self.assertFalse(ranked[0]['cost_estimate']['measured'])

    def test_digest_node_and_class_drift_do_not_borrow_success(self):
        rows = [observation(i) for i in range(5)]
        for candidate in (model(sha='b'), model(node='node-b'), model(sha=None)):
            selected = R.rank_models({}, [candidate], rows)[0]
            self.assertTrue(selected['cold_start']); self.assertIsNone(selected['statistics'])
        selected = R.rank_models({'model_eligibility': {'task_class': 'different'}}, [model()], rows)[0]
        self.assertTrue(selected['cold_start'])

    def test_explicit_restrictions_capacity_and_unknowns(self):
        inventory = [model(), model('other', 'node-b', 'b')]
        contract = {'model_eligibility': {'models': ['other'], 'nodes': ['node-b'], 'digests': ['b' * 64]}}
        self.assertEqual([r['model'] for r in R.rank_models(contract, inventory, [])], ['other'])
        contract = {'resource_budget': {'context_chars': 30000}}
        self.assertEqual(R.rank_models(contract, inventory, []), [])
        inventory[0]['context_chars'] = None
        self.assertEqual(R.rank_models(contract, inventory, [])[0]['context_capacity_status'], 'unknown')
        contract = {'model_eligibility': {'min_observations': 1}}
        self.assertEqual(R.rank_models(contract, inventory, []), [])

    def test_unknown_outcomes_are_not_successes(self):
        row = R.summarize([observation(1), observation(2, status='unknown')])['groups'][0]
        self.assertEqual(row['successes'], 1)
        self.assertEqual(row['statuses']['unknown'], 1)
        self.assertEqual(row['observations'], 2)

    def test_expected_total_cost_can_favor_a_faster_less_reliable_model(self):
        slow = model('slow'); fast = model('fast')
        for row in (slow, fast):
            row['verifier_ms'] = 5; row['scheduler_ms'] = 2
        rows = [{**observation('s' + str(i), name='slow'), 'latency_ms': 1000} for i in range(10)]
        rows += [{**observation('f' + str(i), name='fast', status='success' if i < 8 else 'failed'),
                  'latency_ms': 100} for i in range(10)]
        ranked = R.rank_models({}, [slow, fast], rows)
        self.assertEqual(ranked[0]['model'], 'fast')
        self.assertEqual(ranked[0]['ranking_cost_unit'], 'milliseconds')
        cost = ranked[0]['expected_costs']['milliseconds']
        self.assertEqual(cost['base'], 100)
        self.assertAlmostEqual(cost['expected_total_cost'], 107 / ranked[0]['ranking_lower_bound'])
        self.assertEqual(cost['source'], 'complete_observed_mean_latency')

    def test_missing_overhead_and_cold_start_do_not_invent_total_cost(self):
        row = model(); row['estimated_latency_ms'] = 20
        cold = R.rank_models({}, [row], [])[0]
        self.assertIsNone(cold['ranking_expected_cost'])
        learned = R.rank_models({}, [row], [observation(1)])[0]
        costs = learned['expected_costs']['milliseconds']
        self.assertIsNone(costs['expected_total_cost'])
        self.assertGreater(costs['expected_known_component_cost'], 20)
        self.assertIsNone(costs['verifier'])

    def test_estimated_cost_tie_break_never_becomes_measured(self):
        small = model(); large = model('large'); large['estimated_cost_units'] = 10
        ranked = R.rank_models({}, [large, small], [])
        self.assertEqual(ranked[0]['model'], 'small')
        self.assertTrue(all(r['statistics'] is None for r in ranked))


if __name__ == '__main__':
    unittest.main()
