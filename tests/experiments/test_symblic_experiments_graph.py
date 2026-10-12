"""Isolated native arithmetic graphs; no providers, stores or live capabilities."""
import copy
import json
import unittest
from unittest.mock import patch

from symblic.experiments import graph as E
from symblic.graph import planner as G
from symblic.policy import learning as P


class GraphAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = E.run(E.EXPERIMENT, E.EXAMPLE)

    def test_generated_topology_native_execution_and_exact_heldout(self):
        r = self.result['results']
        train = r['training']
        self.assertEqual([8, 15], [row['candidate_count'] for row in train['rounds']])
        self.assertEqual(train['rounds'][0]['selected'], train['rounds'][1]['parent'])
        selected = train['selection']['selected']['sha256']
        chosen = train['candidates'][selected]
        self.assertEqual(2, len(chosen['nodes']))
        first = chosen['nodes'][0]
        self.assertIn((first['op'], tuple(first['args'])), {('square', ('X',)), ('multiply', ('X', 'X'))})
        self.assertEqual('add', chosen['nodes'][1]['op'])
        self.assertEqual(['N1', 'Y'], chosen['nodes'][1]['args'])
        actual = [row for row in r['heldout_observations'] if row['candidate'] == selected]
        self.assertEqual([7, 10, 18], [row['value'] for row in actual])
        self.assertTrue(all(row['exact'] for row in actual))
        self.assertTrue(r['heldout']['improvement'])
        self.assertEqual('host_declared_not_verified', r['heldout']['measurement_status'])
        self.assertEqual(r['native_selected_graph'], G.freeze_graph(
            r['native_selected_graph']['graph'], r['native_selected_graph']['policy']))
        self.assertEqual(0, self.result['checks']['provider_calls'])
        # Cost accounting includes every evaluated rejected candidate, not just the winner.
        self.assertEqual(63, r['work']['training_arithmetic_nodes'])
        self.assertEqual(153, r['work']['training_native_nodes'])

    def test_heldout_cannot_reselect_even_when_training_winner_loses(self):
        data = {'training': [{'x': 2, 'y': 0}, {'x': 3, 'y': 0}],
                'heldout': [{'x': -2, 'y': -6}, {'x': -3, 'y': -12}]}
        result = E.run(E.EXPERIMENT, data)['results']
        choice = result['training']['selection']['selected']['sha256']
        nodes = result['training']['candidates'][choice]['nodes']
        self.assertEqual(1, len(nodes))
        self.assertIn((nodes[0]['op'], tuple(nodes[0]['args'])), {('square', ('X',)), ('multiply', ('X', 'X'))})
        self.assertFalse(result['heldout']['improvement'])
        self.assertLess(result['heldout']['utility_gain']['numerator'], 0)
        changed = copy.deepcopy(data)
        changed['heldout'] = [{'x': -4, 'y': 0}]
        other = E.run(E.EXPERIMENT, changed)['results']
        self.assertEqual(result['freeze'], other['freeze'])
        self.assertEqual(result['training'], other['training'])
        self.assertEqual(choice, other['heldout']['selected_hash'])

    def test_malformed_or_wrong_split_refuses_before_execution(self):
        bad = []
        for change in ({'heldout': [{'x': 2, 'y': 3}]}, {'training': [{'x': -2, 'y': 0}]},
                       {'training': [{'x': True, 'y': 0}]}, {'training': [{'x': 2.0, 'y': 0}]},
                       {'training': [{'x': 21, 'y': 0}]}, {'heldout': []},
                       {'training': [{'x': 2, 'y': 0}]*9}, {'heldout': [{'x': -2, 'y': 0}]*2},
                       {'heldout': [{'x': -2, 'y': 0, 'answer': 4}]}, {'route': 'cloud'}):
            bad.append({**copy.deepcopy(E.EXAMPLE), **change})
        cyclic = {}
        cyclic['training'] = cyclic
        bad.append(cyclic)
        with patch.object(E, '_execute', side_effect=AssertionError('executed invalid input')):
            for value in bad:
                with self.subTest(value=str(value)[:80]), self.assertRaises(E.ExperimentError):
                    E.run(E.EXPERIMENT, value)
            with self.assertRaises(E.ExperimentError):
                E.run('provider-call', E.EXAMPLE)

    def test_selector_pins_refuse_changed_record_or_heldout_leak(self):
        r = self.result['results']
        training = r['training']
        changed = copy.deepcopy(training['records'])
        changed[0]['score'] -= 1
        with self.assertRaisesRegex(P.PolicyError, 'pin_mismatch'):
            P.select(training['plan'], changed, expected_plan_hash=r['freeze']['training_plan'],
                     expected_records_hash=r['freeze']['training_records'])
        plan = copy.deepcopy(training['plan'])
        plan['heldout_cases'] = r['heldout_plan']['cases']
        with self.assertRaisesRegex(P.PolicyError, 'schema'):
            P.select(plan, training['records'], expected_plan_hash=P.digest(plan),
                     expected_records_hash=P.digest(training['records']))
        overlapped = copy.deepcopy(r['heldout_plan'])
        overlapped['cases'][0]['family_hash'] = training['plan']['cases'][0]['family_hash']
        pins = {**r['heldout']['pins'], 'heldout_plan': P.digest(overlapped)}
        with self.assertRaisesRegex(P.PolicyError, 'split_overlap_family_hash'):
            P.evaluate_heldout(training['plan'], training['records'], training['selection'],
                               overlapped, r['heldout_records'], pins=pins)

    def test_native_graph_and_run_are_used_without_provider(self):
        chosen = self.result['results']['training']['selection']['selected']['policy_json']
        candidate = json.loads(chosen)
        with patch.object(E._NoCalls, 'call', side_effect=AssertionError('provider used')) as calls, \
             patch.object(G, 'compile_node', wraps=G.compile_node) as compile_node, \
             patch.object(E.Run, 'execute', autospec=True, wraps=None) as execute:
            # A fake native failure cannot be replaced by a hidden Python answer.
            execute.return_value = {'status': 'failed', 'calls': 0, 'outputs': []}
            with self.assertRaisesRegex(E.ExperimentError, 'native_arithmetic_execution_failed'):
                E._execute(candidate, {'x': 4, 'y': 5})
            self.assertTrue(compile_node.called)
            self.assertTrue(execute.called)
            calls.assert_not_called()

    def test_catalog_and_output_are_detached_bounded_exact_json(self):
        P.digest(self.result)
        wire = json.dumps(self.result, allow_nan=False)
        self.assertLess(len(wire.encode()), 250_000)
        first = E.catalog()
        first[0]['example']['training'][0]['x'] = 999
        self.assertEqual(2, E.catalog()[0]['example']['training'][0]['x'])
        self.assertEqual({'arithmetic', 'results', 'checks', 'limits', 'sources'}, set(self.result))
        self.assertTrue(any('same known arithmetic target' in text for text in self.result['limits']))
        self.assertTrue(all(row['provider_calls'] == 0 for row in
                            self.result['results']['training']['observations']))


if __name__ == '__main__':
    unittest.main()
