"""Independent small full-vector checks for ideal search, with resource bounds."""
from fractions import Fraction as F
import itertools
import unittest

from symblic.experiments import resources as R


class ResourceTests(unittest.TestCase):
    def test_known_two_qubit_one_iteration(self):
        result = R.run('grover-query-comparison', {'qubits': 2, 'marked': 1, 'iterations': 1})['results']
        self.assertEqual(F(result['selected']['ideal_success_probability']), 1)
        self.assertEqual(F(result['selected']['classical_success_probability']), F(1, 2))
        self.assertEqual(result['selected']['total_quantum_queries'], 2)
        self.assertIsNone(result['physical_gate_count'])

    def test_full_vector_and_exhaustive_classical(self):
        for qubits in (1, 2, 3):
            size = 2**qubits
            for marked in range(1, size+1):
                result = R.search({'qubits': qubits, 'marked': marked, 'iterations': 5})
                state = [F(1)]*size
                for row in result['results']['trajectory']:
                    self.assertEqual(row['ideal_success_probability'], sum(v*v for v in state[:marked])/size)
                    budget = row['classical_query_budget']
                    subsets = list(itertools.combinations(range(size), budget))
                    success = sum(any(x < marked for x in subset) for subset in subsets)
                    self.assertEqual(row['classical_success_probability'], F(success, len(subsets)))
                    oracle = [-v if i < marked else v for i, v in enumerate(state)]
                    mean = sum(oracle)/size
                    state = [2*mean-v for v in oracle]

    def test_overshooting_retained(self):
        result = R.search({'qubits': 2, 'marked': 1, 'iterations': 2})['results']
        self.assertEqual(result['selected']['ideal_success_probability'], F(1, 4))
        self.assertEqual(result['best_within_supplied_iteration_range']['iterations'], 1)

    def test_bounds_before_calculation(self):
        for key, value in [('qubits',21),('marked',0),('iterations',65),('marked',5),('qubits',True)]:
            data = {'qubits':2,'marked':1,'iterations':1};data[key]=value
            with self.assertRaises(ValueError): R.search(data)
        self.assertEqual(len(R.search({'qubits':20,'marked':1,'iterations':64})['results']['trajectory']),65)


if __name__ == '__main__':
    unittest.main()
