"""Isolated finite fixture and refusal checks; no stores, workers or providers."""
import copy
import itertools
import json
import unittest
from fractions import Fraction
from unittest.mock import patch

from symblic.experiments import structure as E


def example(name):
    return next(row['example'] for row in E.catalog() if row['id'] == name)


class StructureExperimentsTests(unittest.TestCase):
    def refuse(self, name, data, code=None):
        with self.assertRaises(ValueError) as caught:
            E.run(name, data)
        if code:
            self.assertEqual(str(caught.exception), code)
        self.assertRegex(str(caught.exception), r'^[a-z_]+$')

    def test_all_catalog_examples_are_json_safe_pure_and_independently_checked(self):
        self.assertEqual(len(E.catalog()), 3)
        for row in E.catalog():
            with self.subTest(experiment=row['id']):
                original = copy.deepcopy(row['example'])
                result = E.run(row['id'], row['example'])
                self.assertTrue(all(result['checks'].values()))
                self.assertEqual(result, json.loads(json.dumps(result)))
                self.assertEqual(original, row['example'])
                result['sources'][0]['title'] = 'changed'
                self.assertNotEqual(E.catalog()[0]['sources'][0]['title'], 'changed')

    def test_uniform_matroid_known_rank_and_basis(self):
        answer = E.run('finite-matroid', example('finite-matroid'))['results']
        self.assertEqual(answer['rank'], 2)
        self.assertEqual(answer['query_rank'], 2)
        self.assertFalse(answer['query_independent'])
        self.assertEqual(answer['greedy']['basis'], ['a', 'b'])
        self.assertEqual(answer['greedy']['weight'], 9)
        self.assertEqual(answer['exhaustive_baseline']['optimal_bases'], [['a', 'b']])
        self.assertEqual(answer['work']['exhaustive_bases_scored'], 6)

    def test_partition_matroid_negative_weights_and_ties(self):
        # At most one of a/b and at most one of c/d. Basis must include a negative weight.
        data = {'ground': ['a', 'b', 'c', 'd'], 'independent_sets': [[], ['a'], ['b'],
                ['c'], ['d'], ['a', 'c'], ['a', 'd'], ['b', 'c'], ['b', 'd']],
                'weights': {'a': '3/2', 'b': '3/2', 'c': -2, 'd': -3},
                'query': ['a', 'b'], 'weight_unit': 'score'}
        answer = E.run('finite-matroid', data)['results']
        self.assertEqual(answer['query_rank'], 1)
        self.assertEqual(answer['greedy']['basis'], ['a', 'c'])
        self.assertEqual(answer['greedy']['weight'], '-1/2')
        self.assertEqual(answer['exhaustive_baseline']['optimal_bases'], [['a', 'c'], ['b', 'c']])

    def test_matroid_loops_zero_rank_and_full_eight_element_bound(self):
        data = {'ground': ['a', 'b'], 'independent_sets': [[]], 'weights': {'a': 4, 'b': 5},
                'query': ['a'], 'weight_unit': 'score'}
        result = E.run('finite-matroid', data)['results']
        self.assertEqual(result['rank'], 0)
        self.assertEqual(result['greedy']['basis'], [])
        ground = list('abcdefgh')
        data = {'ground': ground, 'independent_sets': [list(combo) for size in range(9)
                for combo in itertools.combinations(ground, size)],
                'weights': {key: -1 for key in ground}, 'query': ground, 'weight_unit': 'score'}
        result = E.run('finite-matroid', data)['results']
        self.assertEqual(result['rank'], 8)
        self.assertEqual(result['greedy']['weight'], -8)
        self.assertEqual(result['independent_set_count'], 256)

    def test_invalid_matroid_axioms_and_duplicate_set_refuse(self):
        base = {'ground': ['a', 'b', 'c'], 'weights': {'a': 1, 'b': 2, 'c': 3},
                'query': [], 'weight_unit': 'score'}
        for family, code in [([['a']], 'matroid_empty'),
                             ([[], ['a', 'b']], 'matroid_hereditary'),
                             ([[], ['a'], ['b'], ['c'], ['a', 'b']], 'matroid_exchange'),
                             ([[], ['a', 'b'], ['b', 'a']], 'duplicate_set')]:
            with self.subTest(code=code):
                self.refuse('finite-matroid', dict(base, independent_sets=family), code)

    def test_matroid_bounds_unknowns_and_numeric_types_before_axiom_work(self):
        changes = [('ground', list('abcdefghi')), ('ground', ['a', 'a']),
                   ('independent_sets', [[]] * 17), ('query', ['unknown']),
                   ('weights', {'a': True, 'b': 4, 'c': 2, 'd': -1}),
                   ('weights', {'a': 1.0, 'b': 4, 'c': 2, 'd': -1}),
                   ('weights', {'a': '1/0', 'b': 4, 'c': 2, 'd': -1})]
        with patch.object(E, '_validate_matroid', side_effect=AssertionError('expensive work')):
            for key, value in changes:
                with self.subTest(key=key, value=value):
                    data = example('finite-matroid')
                    data[key] = value
                    self.refuse('finite-matroid', data)

    def test_graph_cut_known_bottleneck_and_region_complement(self):
        data = example('boundary-graph-cut')
        answer = E.run('boundary-graph-cut', data)['results']
        self.assertEqual(answer['min_cut_capacity'], 2)
        self.assertEqual(answer['max_flow_value'], 2)
        self.assertEqual(answer['source_side'], ['A', 'u'])
        self.assertEqual(answer['crossing_edges'], [{'u': 'u', 'v': 'v', 'weight': 2}])
        self.assertEqual(answer['work']['exhaustive_bulk_assignments'], 4)
        data['region'] = ['B', 'C']
        complement = E.run('boundary-graph-cut', data)['results']
        self.assertEqual(complement['min_cut_capacity'], 2)
        self.assertEqual(complement['source_side'], ['B', 'C', 'v'])

    def test_graph_cut_parallel_paths_fractional_weights_and_zero_edges(self):
        data = {'boundary': ['A', 'B'], 'bulk': ['u', 'v'], 'region': ['A'],
                'weight_unit': 'capacity', 'edges': [
                    {'u': 'A', 'v': 'u', 'weight': '1/2'},
                    {'u': 'u', 'v': 'B', 'weight': '1/3'},
                    {'u': 'A', 'v': 'v', 'weight': 2},
                    {'u': 'v', 'v': 'B', 'weight': 1},
                    {'u': 'A', 'v': 'B', 'weight': '1/7'},
                    {'u': 'u', 'v': 'v', 'weight': 0}]}
        result = E.run('boundary-graph-cut', data)['results']
        self.assertEqual(Fraction(result['min_cut_capacity']), Fraction(31, 21))
        self.assertEqual(result['work']['augmentations'], 3)
        data['edges'] = []
        result = E.run('boundary-graph-cut', data)['results']
        self.assertEqual(result['min_cut_capacity'], 0)
        self.assertEqual(result['exhaustive_baseline']['tied_minimum_partitions'], 4)
        self.assertEqual(result['work']['augmentations'], 0)

    def test_all_unweighted_four_vertex_graphs_agree_with_independent_cut_enumeration(self):
        names = ['A', 'B', 'u', 'v']
        pairs = list(itertools.combinations(names, 2))
        for graph_mask in range(1 << len(pairs)):
            edges = [{'u': u, 'v': v, 'weight': 1} for i, (u, v) in enumerate(pairs)
                     if graph_mask & (1 << i)]
            data = {'boundary': ['A', 'B'], 'bulk': ['u', 'v'], 'edges': edges,
                    'region': ['A'], 'weight_unit': 'capacity'}
            expected = min(sum((edge['u'] in side) != (edge['v'] in side) for edge in edges)
                           for side in ({'A'}, {'A', 'u'}, {'A', 'v'}, {'A', 'u', 'v'}))
            self.assertEqual(E.run('boundary-graph-cut', data)['results']['min_cut_capacity'], expected)

    def test_graph_cut_bulk_limit_no_bulk_and_all_assignment_bound(self):
        data = {'boundary': ['A', 'B'], 'bulk': [], 'edges': [
            {'u': 'A', 'v': 'B', 'weight': 4}], 'region': ['A'], 'weight_unit': 'capacity'}
        result = E.run('boundary-graph-cut', data)['results']
        self.assertEqual(result['min_cut_capacity'], 4)
        self.assertEqual(result['work']['exhaustive_bulk_assignments'], 1)
        data['bulk'] = [f'u{i}' for i in range(10)]
        result = E.run('boundary-graph-cut', data)['results']
        self.assertEqual(result['exhaustive_baseline']['tied_minimum_partitions'], 1024)

    def test_graph_flow_can_reassign_an_earlier_path(self):
        data = {'boundary': ['A', 'B'], 'bulk': ['a', 'b', 'c', 'd'],
                'region': ['A'], 'weight_unit': 'capacity',
                'edges': [{'u': u, 'v': v, 'weight': 1} for u, v in
                          [('A', 'a'), ('A', 'b'), ('a', 'c'), ('a', 'd'),
                           ('b', 'c'), ('c', 'B'), ('d', 'B')]]}
        result = E.run('boundary-graph-cut', data)['results']
        self.assertEqual(result['min_cut_capacity'], 2)
        self.assertEqual(result['max_flow_value'], 2)
        self.assertEqual(result['work']['augmentations'], 2)

    def test_invalid_graphs_refused_before_flow_or_exhaustive_work(self):
        changes = [('bulk', [f'u{i}' for i in range(11)]), ('bulk', ['A']),
                   ('boundary', list('ABCDEFG')), ('region', ['A', 'B', 'C']),
                   ('region', ['unknown']), ('edges', [{'u': 'A', 'v': 'A', 'weight': 1}]),
                   ('edges', [{'u': 'A', 'v': 'u', 'weight': -1}]),
                   ('edges', [{'u': 'A', 'v': 'u', 'weight': 1.0}]),
                   ('edges', [{'u': 'A', 'v': 'u', 'weight': True}]),
                   ('edges', [{'u': 'A', 'v': 'u', 'weight': 1},
                              {'u': 'u', 'v': 'A', 'weight': 2}]),
                   ('edges', [{'u': 'A', 'v': 'u', 'weight': 1}] * 65)]
        with patch.object(E, '_mincut', side_effect=AssertionError('flow invoked')), \
                patch.object(E, '_enumerate_cuts', side_effect=AssertionError('enumeration invoked')):
            for key, value in changes:
                with self.subTest(key=key, value=value):
                    data = example('boundary-graph-cut')
                    data[key] = value
                    self.refuse('boundary-graph-cut', data)

    def test_sequence_smoothing_has_known_trajectory_and_unchanged_baseline(self):
        data = example('graph-smoothing')
        result = E.run('graph-smoothing', data)['results']
        self.assertEqual(result['original_values'], [0, 4, 0])
        self.assertEqual(result['unsmoothed_baseline']['values'], [0, 4, 0])
        self.assertEqual([row['values'] for row in result['trajectory']],
                         [[0, 4, 0], [1, 2, 1], ['5/4', '3/2', '5/4']])
        self.assertEqual([row['energy'] for row in result['trajectory']], [16, 1, '1/16'])
        self.assertEqual([row['sum'] for row in result['trajectory']], [4, 4, 4])
        self.assertEqual(result['trajectory'][1]['squared_distance_from_original'], 6)
        self.assertEqual(result['units']['energy'], '(amplitude)^2')
        self.assertEqual(result['work']['edge_flux_updates'], 4)

    def test_weighted_graph_smoothing_conserves_separate_components(self):
        data = {'mode': 'graph', 'vertices': ['a', 'b', 'c', 'd'], 'values': [0, 2, -4, 8],
                'edges': [{'u': 'a', 'v': 'b', 'weight': 2},
                          {'u': 'c', 'v': 'd', 'weight': 1}], 'alpha': '1/4', 'steps': 3,
                'units': {'value': 'K', 'edge_weight': 'dimensionless', 'step': 'dimensionless'}}
        result = E.run('graph-smoothing', data)['results']
        self.assertEqual(result['trajectory'][1]['values'], [1, 1, -1, 5])
        for row in result['trajectory']:
            values = list(map(Fraction, row['values']))
            self.assertEqual(sum(values[:2]), 2)
            self.assertEqual(sum(values[2:]), 4)
        self.assertEqual(result['trajectory'][0]['energy'], 76)
        self.assertEqual(result['trajectory'][1]['energy'], 18)

    def test_smoothing_zero_steps_zero_alpha_singleton_and_max_steps(self):
        for changes in ({'steps': 0}, {'alpha': 0, 'steps': 64},
                        {'values': ['1/3'], 'alpha': 1, 'steps': 64}):
            data = example('graph-smoothing')
            data.update(changes)
            result = E.run('graph-smoothing', data)['results']
            self.assertEqual(result['final_values'], data['values'])
            self.assertEqual(len(result['trajectory']), data['steps'] + 1)
        data = example('graph-smoothing')
        data['steps'] = 64
        result = E.run('graph-smoothing', data)['results']
        self.assertEqual(len(result['trajectory']), 65)
        self.assertEqual(result['trajectory'][-1]['sum'], 4)

    def test_smoothing_instability_shapes_and_units_refused_before_updates(self):
        changes = [('alpha', '1/3'), ('alpha', -1), ('alpha', True), ('alpha', 0.25),
                   ('steps', 65), ('steps', True), ('values', [0] * 17), ('values', [1.5]),
                   ('values', [True]), ('units', {'value': 'm', 'edge_weight': 'kg',
                                               'step': 'dimensionless'})]
        with patch.object(E, '_energy', side_effect=AssertionError('updates invoked')):
            for key, value in changes:
                with self.subTest(key=key, value=value):
                    data = example('graph-smoothing')
                    data[key] = value
                    self.refuse('graph-smoothing', data)

    def test_arithmetic_growth_is_refused_without_input_change_or_partial_result(self):
        data = example('graph-smoothing')
        data.update(alpha='1/999983', steps=64)
        original = copy.deepcopy(data)
        self.refuse('graph-smoothing', data, 'arithmetic_bound')
        self.assertEqual(data, original)

    def test_global_invalid_envelopes_cycles_bounds_and_codes(self):
        self.refuse('missing', {}, 'experiment_id')
        self.refuse([], {}, 'experiment_id')
        data = example('finite-matroid')
        data['private-extra'] = 'never echoed'
        self.refuse('finite-matroid', data, 'fields')
        cyclic = []
        cyclic.append(cyclic)
        self.refuse('finite-matroid', cyclic, 'structure_bound')
        self.refuse('finite-matroid', {'x': 1 << 10000}, 'integer_bound')
        self.refuse('finite-matroid', {'x': '\ud800'}, 'unicode')
        self.refuse('finite-matroid', {'x': float('nan')}, 'json_type')


if __name__ == '__main__':
    unittest.main()
