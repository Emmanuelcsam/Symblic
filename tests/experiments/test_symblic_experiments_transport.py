"""Independent exact finite references and adversarial contract boundaries."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
import unittest
from unittest.mock import patch

from symblic.experiments import transport as T


def example(name):
    return next(row['example'] for row in T.catalog() if row['id'] == name)


class SheafTests(unittest.TestCase):
    def test_restrictions_not_raw_vector_equality_decide_compatibility(self):
        result = T.run('cellular-sheaf', example('cellular-sheaf'))
        r = result['results']
        self.assertEqual(r['coboundary_matrix'], [[-1, -1, 1]])
        self.assertEqual(r['assignment'], [1, 2, 3])
        self.assertEqual(r['coboundary_residual'], [0])
        self.assertTrue(r['global_section'])
        self.assertEqual(r['squared_discrepancy'], 0)
        self.assertEqual(r['edge_checks'][0]['tail_image'], [3])
        self.assertEqual(r['units']['squared_discrepancy'], '(signal)^2')

    def test_incompatible_assignment_has_residual_and_orientation_covariance(self):
        data = example('cellular-sheaf')
        data['vertices'][1]['value'] = [4]
        first = T.run('cellular-sheaf', data)
        self.assertFalse(first['results']['global_section'])
        self.assertFalse(first['checks']['supplied_assignment_is_global_section'])
        self.assertEqual(first['results']['coboundary_residual'], [1])
        self.assertEqual(first['results']['squared_discrepancy'], 1)
        edge = data['edges'][0]
        edge['tail'], edge['head'] = edge['head'], edge['tail']
        edge['tail_map'], edge['head_map'] = edge['head_map'], edge['tail_map']
        flipped = T.run('cellular-sheaf', data)['results']
        self.assertEqual(flipped['coboundary_residual'], [-1])
        self.assertEqual(flipped['squared_discrepancy'], 1)

    def test_rational_multiedge_and_disconnected_reference(self):
        data = {'vertices': [{'id': 'a', 'value': ['1/2']}, {'id': 'b', 'value': ['3/2']},
                             {'id': 'free', 'value': [99, -11]}], 'value_unit': 'voltage',
                'edges': [{'id': 'e', 'tail': 'a', 'head': 'b', 'dimension': 2,
                           'tail_map': [[1], [2]], 'head_map': [[1], [0]]},
                          {'id': 'parallel', 'tail': 'a', 'head': 'b', 'dimension': 1,
                           'tail_map': [[-3]], 'head_map': [[-1]]}]}
        r = T.run('cellular-sheaf', data)['results']
        self.assertEqual(r['coboundary_residual'], [1, -1, 0])
        self.assertEqual(r['squared_discrepancy'], 2)
        self.assertTrue(r['edge_checks'][1]['compatible'])
        data['edges'] = []
        r = T.run('cellular-sheaf', data)['results']
        self.assertEqual(r['coboundary_matrix'], [])
        self.assertEqual(r['squared_discrepancy'], 0)
        self.assertTrue(r['global_section'])

    def test_independent_edge_check_catches_corrupt_coboundary(self):
        original = T._coboundary
        def corrupt(*args):
            rows, columns, labels = original(*args)
            rows[0][0] += 1
            return rows, columns, labels
        with patch.object(T, '_coboundary', side_effect=corrupt), self.assertRaisesRegex(ValueError, 'coboundary_internal_check'):
            T.run('cellular-sheaf', example('cellular-sheaf'))

    def test_bad_contract_refuses_before_any_matrix_work(self):
        for change in ('bool', 'float', 'unreduced_big', 'dimension', 'shape', 'endpoint', 'loop',
                       'duplicate', 'vertex_count', 'edge_count', 'unit'):
            data = example('cellular-sheaf')
            if change == 'bool': data['vertices'][0]['value'][0] = True
            if change == 'float': data['vertices'][0]['value'][0] = 0.5
            if change == 'unreduced_big': data['vertices'][0]['value'][0] = '1000001/1000001'
            if change == 'dimension': data['edges'][0]['dimension'] = 4
            if change == 'shape': data['edges'][0]['tail_map'] = [[1]]
            if change == 'endpoint': data['edges'][0]['head'] = 'missing'
            if change == 'loop': data['edges'][0]['head'] = 'a'
            if change == 'duplicate': data['edges'] *= 2
            if change == 'vertex_count': data['vertices'] *= 5
            if change == 'edge_count': data['edges'] *= 17
            if change == 'unit': data['value_unit'] = 'x<script>'
            with self.subTest(change=change), patch.object(T, '_coboundary', side_effect=AssertionError('work')), self.assertRaises(ValueError):
                T.run('cellular-sheaf', data)

    def test_declared_maximum_shapes_and_preflight_arithmetic_limits(self):
        data = {'vertices': [{'id': f'v{i}', 'value': [1, 2, 3]} for i in range(8)],
                'edges': [{'id': f'e{i}', 'tail': f'v{i%8}', 'head': f'v{(i+1)%8}', 'dimension': 3,
                           'tail_map': [[1,0,0],[0,1,0],[0,0,1]], 'head_map': [[1,0,0],[0,1,0],[0,0,1]]}
                          for i in range(16)], 'value_unit': 'dimensionless'}
        r = T.run('cellular-sheaf', data)['results']
        self.assertTrue(r['global_section'])
        self.assertEqual(len(r['coboundary_matrix']), 48)
        self.assertEqual(len(r['coboundary_matrix'][0]), 24)
        self.assertLess(r['work']['arithmetic_operations'], T.MAX_WORK)
        work = T._Work()
        with self.assertRaisesRegex(ValueError, 'arithmetic_bits_bound'):
            work.mul(F(2**300), F(2**300))
        work.used = T.MAX_WORK
        with self.assertRaisesRegex(ValueError, 'arithmetic_work_bound'):
            work.add(F(1), F(1))


class SchemaTests(unittest.TestCase):
    def test_bijection_predicate_and_naturality_reference(self):
        result = T.run('finite-schema-transport', example('finite-schema-transport'))
        r = result['results']
        self.assertTrue(r['left_inverse'] and r['right_inverse'])
        self.assertTrue(r['predicate_preserved'] and r['square_commutes'])
        self.assertEqual(r['pullback_B_to_A'], {'a0': True, 'a1': False})
        self.assertEqual(r['existential_A_to_B'], {'b0': True, 'b1': False})
        self.assertEqual(r['universal_A_to_B'], r['existential_A_to_B'])
        self.assertTrue(all(result['checks'].values()))

    def test_lossy_maps_and_empty_fibers_are_explicit(self):
        data = example('finite-schema-transport')
        data['maps']['forward']['a1'] = 'b0'
        r = T.run('finite-schema-transport', data)['results']
        self.assertFalse(r['left_inverse'] or r['right_inverse'])
        self.assertEqual(r['fibers'], {'b0': ['a0', 'a1'], 'b1': []})
        self.assertEqual(r['existential_A_to_B'], {'b0': True, 'b1': False})
        self.assertEqual(r['universal_A_to_B'], {'b0': False, 'b1': True})
        self.assertFalse(r['predicate_preserved'])
        self.assertFalse(r['square_commutes'])

    def test_square_and_predicate_counterexamples_remain_results(self):
        data = example('finite-schema-transport')
        data['maps']['bottom']['c1'] = 'd0'
        result = T.run('finite-schema-transport', data)
        self.assertFalse(result['checks']['supplied_square_commutes'])
        witness = result['results']['naturality_square'][1]
        self.assertEqual((witness['element'], witness['right_after_forward'], witness['bottom_after_left']), ('a1','d1','d0'))
        data['predicates']['B']['b0'] = False
        self.assertFalse(T.run('finite-schema-transport', data)['checks']['supplied_predicate_preserved'])

    def test_fiber_adjunctions_for_every_small_predicate_pair(self):
        # Independent finite subset identities include non-surjective and non-injective maps.
        for destinations in product(('b0', 'b1'), repeat=2):
            for bits in product((False, True), repeat=4):
                data = example('finite-schema-transport')
                data['maps']['forward'] = dict(zip(('a0', 'a1'), destinations))
                data['predicates'] = {'A': dict(zip(('a0','a1'), bits[:2])), 'B': dict(zip(('b0','b1'), bits[2:]))}
                r = T.run('finite-schema-transport', data)['results']
                true_a = {a for a, value in data['predicates']['A'].items() if value}
                true_b = {b for b, value in data['predicates']['B'].items() if value}
                image = {data['maps']['forward'][a] for a in true_a}
                pullback = {a for a, b in data['maps']['forward'].items() if b in true_b}
                self.assertEqual({b for b, value in r['existential_A_to_B'].items() if value}, image)
                self.assertEqual(image <= true_b, true_a <= pullback)
                self.assertEqual(r['predicate_adjunctions']['pullback_subset_A'], pullback <= true_a)

    def test_map_domain_codomain_and_predicate_types_refuse(self):
        for change in ('missing', 'extra', 'target', 'boolean', 'duplicate', 'oversize', 'code'):
            data = example('finite-schema-transport')
            if change == 'missing': del data['maps']['forward']['a0']
            if change == 'extra': data['maps']['forward']['other'] = 'b0'
            if change == 'target': data['maps']['forward']['a0'] = 'd0'
            if change == 'boolean': data['predicates']['A']['a0'] = 1
            if change == 'duplicate': data['sets']['A'] = ['a0','a0']
            if change == 'oversize': data['sets']['A'] = [f'a{i}' for i in range(9)]
            if change == 'code': data['maps']['forward'] = 'lambda x: eval(x)'
            with self.subTest(change=change), self.assertRaises(ValueError):
                T.run('finite-schema-transport', data)

    def test_detached_catalog_input_preservation_and_json_bounds(self):
        data = example('cellular-sheaf'); before = deepcopy(data)
        first = T.run('cellular-sheaf', data)
        self.assertEqual(first, T.run('cellular-sheaf', data))
        self.assertEqual(before, data)
        json.dumps(first, allow_nan=False)
        T.catalog()[0]['example']['vertices'][0]['value'][0] = 999
        self.assertEqual(example('cellular-sheaf')['vertices'][0]['value'][0], 1)
        cyclic = {}; cyclic['cycle'] = cyclic
        for bad in (cyclic, {'x': 'x'*4097}, {'x': 0.2}, {'x': 2**513}, {'x': '\ud800'}):
            with self.subTest(bad=str(bad)[:50]), self.assertRaises(ValueError):
                T.run('cellular-sheaf', bad)
        with self.assertRaisesRegex(ValueError, 'byte_bound'):
            T._bounded({'x': 'abcdef'}, 3)
        with self.assertRaisesRegex(ValueError, 'experiment_id'):
            T.run('execute', {})


if __name__ == '__main__':
    unittest.main()
