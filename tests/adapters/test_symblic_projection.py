"""Exact finite projection contracts; no stores, workers or provider calls."""
import copy
import importlib.util
import random
import unittest
from decimal import Decimal
from fractions import Fraction as F
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.adapters import projection as P
from symblic.adapters import variational as V


def reference_kkt(x, C, d, weights):
    """Independent full KKT Gauss-Jordan solve, never forming C W^-1 C^T."""
    n, m = len(x), len(C)
    rows = [[F(weights[i] if i == j else 0) for j in range(n)]
            + [F(C[j][i]) for j in range(m)] + [weights[i] * x[i]] for i in range(n)]
    rows += [[F(v) for v in C[i]] + [F(0)] * m + [F(d[i])] for i in range(m)]
    for col in range(n + m):
        pivot = next(j for j in range(n + m - 1, col - 1, -1) if rows[j][col])
        rows[pivot], rows[col] = rows[col], rows[pivot]
        diagonal = rows[col][col]
        rows[col] = [v / diagonal for v in rows[col]]
        for row in range(n + m):
            if row != col:
                factor = rows[row][col]
                rows[row] = [a - factor * b for a, b in zip(rows[row], rows[col])]
    return tuple(row[-1] for row in rows[:n])


def call(x, C, d, weights=None, steps=1_000_000):
    kernel = S.Kernel(S.Env(), S.KB(), S.Budget(steps))
    return P.FUNCTIONS['reconcile'](kernel, None, x, C, d, weights)


class ExactProjection(unittest.TestCase):
    def test_percentages_sum_to_one_hundred(self):
        receipt = call([40, 35, 30], [[1, 1, 1]], [100])
        self.assertEqual(receipt, {'value': (F(115, 3), F(100, 3), F(85, 3)), 'moved': F(25, 3),
                                  'residual': (5,), 'satisfied': False, 'method': 'exact-affine-projection'})

    def test_two_independent_debit_credit_balances(self):
        receipt = call([10, 8, 4, 5], [[1, -1, 0, 0], [0, 0, 1, -1]], [0, 0])
        self.assertEqual(receipt['value'], (9, 9, F(9, 2), F(9, 2)))
        self.assertEqual(receipt['moved'], F(5, 2))
        self.assertEqual(receipt['residual'], (2, -1))

    def test_positive_weights_move_less_trusted_value_more(self):
        receipt = call([0, 10], [[1, 1]], [12], [3, 1])
        self.assertEqual(receipt['value'], (F(1, 2), F(23, 2)))
        self.assertEqual(receipt['moved'], 3)

    def test_already_satisfied_and_full_rank_constraints(self):
        receipt = call([1, 2], [[1, 1]], [3])
        self.assertEqual(receipt['value'], (1, 2))
        self.assertEqual(receipt['moved'], 0)
        self.assertEqual(receipt['residual'], (0,))
        self.assertIs(receipt['satisfied'], True)
        full = call([7, 8], [[1, 1], [1, -1]], [5, 1], [2, 9])
        self.assertEqual(full['value'], (3, 2))

    def test_seeded_rational_instances_against_independent_full_kkt(self):
        rng = random.Random(38081)
        for _ in range(48):
            n = rng.randint(1, 6)
            m = rng.randint(1, n)
            C = [[F(int(i == j)) if j < m else F(rng.randint(-3, 3), rng.randint(1, 4))
                  for j in range(n)] for i in range(m)]
            x = [F(rng.randint(-5, 5), rng.randint(1, 4)) for _ in range(n)]
            d = [F(rng.randint(-5, 5), rng.randint(1, 4)) for _ in range(m)]
            weights = [F(rng.randint(1, 6), rng.randint(1, 4)) for _ in range(n)]
            expected = reference_kkt(x, C, d, weights)
            with self.subTest(n=n, m=m, x=x):
                receipt = call(x, C, d, weights)
                self.assertEqual(receipt['value'], expected)
                self.assertEqual(receipt['moved'], sum(w * (a - b) ** 2 for w, a, b in zip(weights, expected, x)))
                self.assertEqual(tuple(sum(a * b for a, b in zip(row, expected)) for row in C), tuple(d))

    def test_unique_minimum_on_independent_finite_feasible_grid(self):
        x, C, d, weights = [F(1, 2), 4, -1], [[1, 1, 1]], [2], [1, 2, 3]
        receipt = call(x, C, d, weights)
        y = receipt['value']
        # Every displacement (a,b,-a-b) preserves this constraint.
        for a in range(-3, 4):
            for b in range(-3, 4):
                moved = sum(w * (v + delta - original) ** 2
                            for w, v, delta, original in zip(weights, y, (F(a, 2), F(b, 3), -F(a, 2) - F(b, 3)), x))
                self.assertGreaterEqual(moved, receipt['moved'])
                self.assertEqual(moved == receipt['moved'], a == b == 0)

    def test_row_order_and_nonzero_scaling_do_not_change_repair(self):
        x, C, d = [3, 7, -2], [[1, 2, 0], [0, -1, 1]], [4, 3]
        expected = call(x, C, d)
        reordered = call(x, [[0, 3, -3], [2, 4, 0]], [-9, 8])
        self.assertEqual(reordered['value'], expected['value'])
        self.assertEqual(reordered['moved'], expected['moved'])
        self.assertEqual(reordered['residual'], (-3 * expected['residual'][1], 2 * expected['residual'][0]))

    def test_inputs_preserved_and_canonical_form_accepted(self):
        args = ([2, F(3, 2)], [[1, 1]], [4], [1, 2])
        original = copy.deepcopy(args)
        receipt = call(*args)
        self.assertEqual(args, original)
        self.assertEqual(S.canon(receipt), S.canon(call(*args)))
        self.assertEqual(S.fingerprint(receipt), S.fingerprint(call(*args)))
        self.assertIs(type(receipt['value']), tuple)

    def test_maximum_dimension(self):
        size = P.MAX_DIMENSION
        identity = [[int(i == j) for j in range(size)] for i in range(size)]
        receipt = call([0] * size, identity, [1] * size)
        self.assertEqual(receipt['value'], (1,) * size)
        self.assertEqual(receipt['moved'], size)


class ProjectionRefusals(unittest.TestCase):
    def test_wrong_shapes_and_dimension(self):
        cases = (([], [], []), ([0] * 33, [[1] * 33], [1]), ([1], [], []),
                 ([1], [[1], [2]], [1, 2]), ([1, 2], [[1]], [1]),
                 ([1, 2], [[1, 1]], []), ([1, 2], [[1, 1]], [1], [1]),
                 ('1', [[1]], [1]), ([1], {0: [1]}, [1]), ([1], [[1]], '1'))
        for args in cases:
            with self.subTest(args=args), self.assertRaises(P.ProjectionError):
                call(*args)

    def test_dependent_rows_refuse_even_when_feasible(self):
        for C, d in (([[1, 2], [2, 4]], [1, 2]), ([[1, 2], [2, 4]], [1, 3]),
                     ([[0, 0]], [0]), ([[0, 0]], [1])):
            with self.subTest(C=C, d=d), self.assertRaises(P.ProjectionError) as caught:
                call([0, 0], C, d)
            self.assertEqual(caught.exception.kind, 'check')

    def test_weight_positivity(self):
        for weight in (0, -1, F(-1, 3)):
            with self.subTest(weight=weight), self.assertRaises(P.ProjectionError) as caught:
                call([0], [[1]], [1], [weight])
            self.assertEqual(caught.exception.kind, 'check')

    def test_only_native_exact_numbers_in_every_input(self):
        class IntSubclass(int):
            pass
        for bad in (True, False, 1.0, float('nan'), float('inf'), Decimal(1), None, '1', 1j, IntSubclass(1)):
            for args in (([bad], [[1]], [1]), ([0], [[bad]], [1]), ([0], [[1]], [bad]),
                         ([0], [[1]], [1], [bad])):
                with self.subTest(bad=type(bad).__name__, args=args), self.assertRaises(P.ProjectionError):
                    call(*args)

    def test_corrupted_fraction_refused(self):
        for numerator, denominator in ((2, 4), (1, 0), (1, -2), (True, 2)):
            forged = object.__new__(F)
            forged._numerator, forged._denominator = numerator, denominator
            with self.subTest(pair=(numerator, denominator)), self.assertRaises(P.ProjectionError):
                call([forged], [[1]], [1])

    def test_strict_local_limits_and_intermediate_bounds(self):
        for name, ceiling in (('max_dimension', P.MAX_DIMENSION), ('max_bits', P.MAX_BITS), ('max_work', P.MAX_WORK)):
            for value in (True, 0, 1.0, ceiling + 1):
                with self.subTest(name=name, value=value), self.assertRaises(P.ProjectionError):
                    P.reconcile([0], [[1]], [1], **{name: value})
        for args, bits in ((([8], [[1]], [0]), 3), (([0], [[7]], [1]), 3)):
            with self.subTest(args=args), self.assertRaises(P.ProjectionError) as caught:
                P.reconcile(*args, max_bits=bits)
            self.assertEqual(caught.exception.kind, 'budget')
        with self.assertRaises(P.ProjectionError):
            call([1 << P.MAX_BITS], [[1]], [0])
        with self.assertRaises(P.ProjectionError):
            P.reconcile([0], [[1]], [1], max_work=1)

    def test_shared_budget_is_charged_and_failure_propagates(self):
        with self.assertRaises(S.SymblicError) as caught:
            call([0], [[1]], [1], steps=1)
        self.assertNotIsInstance(caught.exception, P.ProjectionError)
        budgets = [S.Budget(10000), S.Budget(10000)]
        for budget in budgets:
            P.reconcile([0, 1], [[1, 1]], [3], budget=budget)
        self.assertEqual(budgets[0].left, budgets[1].left)
        self.assertLess(budgets[0].left, 10000)

    def test_bad_solver_output_is_not_returned_as_a_repair(self):
        with patch.object(P, '_solve', return_value=(F(0),)), self.assertRaisesRegex(P.ProjectionError, 'feasibility'):
            call([0, 0], [[1, 1]], [2])
        # Feasible y alone does not establish the minimum. The independent
        # stationarity check also rejects a feasible but nonminimal candidate.
        work = V._Work(2, 4096, 200000)
        with self.assertRaisesRegex(P.ProjectionError, 'stationarity'):
            P._checked_moved((F(0), F(0)), ((F(1), F(1)),), (F(2),), (F(1), F(1)),
                             (F(2), F(0)), (F(-1),), work)

    def test_import_does_not_register_or_replace_functions(self):
        before = S.BUILTINS.copy()
        spec = importlib.util.spec_from_file_location('_projection_inert_probe', P.__file__)
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)
        self.assertEqual(S.BUILTINS, before)
        self.assertEqual(set(P.FUNCTIONS), {'reconcile'})


if __name__ == '__main__':
    unittest.main()
