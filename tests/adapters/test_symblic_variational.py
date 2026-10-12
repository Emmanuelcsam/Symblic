"""Finite exact quadratic witnesses; no stores, workers, services or model calls."""
import copy
import importlib.util
import random
import unittest
from decimal import Decimal
from fractions import Fraction as F
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import run as SR
from symblic.adapters import variational as V


def spd_problem(size, seed):
    """Independent known witness generator, not the implementation's factor/solve."""
    rng = random.Random(seed)
    lower = [[F(int(i == j)) if i <= j else F(rng.randint(-2, 2), rng.randint(1, 3))
              for j in range(size)] for i in range(size)]
    diagonal = [F(rng.randint(1, 5), rng.randint(1, 3)) for _ in range(size)]
    matrix = [[sum(lower[i][k] * diagonal[k] * lower[j][k] for k in range(size))
               for j in range(size)] for i in range(size)]
    answer = [F(rng.randint(-4, 4), rng.randint(1, 4)) for _ in range(size)]
    rhs = [sum(a * x for a, x in zip(row, answer)) for row in matrix]
    return matrix, rhs, tuple(answer), tuple(tuple(row) for row in lower), tuple(diagonal)


class ExactMinimum(unittest.TestCase):
    def test_known_two_dimensional_solution(self):
        A, b = [[4, 1], [1, 3]], [1, 2]
        receipt = V.minimize_quadratic(A, b)
        self.assertEqual(receipt['x'], (F(1, 11), F(7, 11)))
        self.assertEqual(receipt['min_energy'], F(-15, 22))
        self.assertEqual(receipt['L'], ((1, 0), (F(1, 4), 1)))
        self.assertEqual(receipt['D'], (4, F(11, 4)))
        self.assertEqual(receipt['residual'], (0, 0))
        self.assertTrue(V.verify_quadratic(A, b, receipt))

    def test_scalar_and_fractional_inputs(self):
        for A, b, x, energy in (([[2]], [6], (3,), -9),
                                ([[F(1, 3)]], [F(2, 5)], (F(6, 5),), F(-6, 25)),
                                ([[5]], [0], (0,), 0)):
            with self.subTest(A=A, b=b):
                receipt = V.minimize_quadratic(A, b)
                self.assertEqual(receipt['x'], x)
                self.assertEqual(receipt['min_energy'], energy)
                self.assertTrue(V.verify_quadratic(A, b, receipt))

    def test_seeded_constructed_spd_and_energy_gap(self):
        for size in range(1, 9):
            for seed in (143, 891):
                with self.subTest(size=size, seed=seed):
                    A, b, expected, lower, diagonal = spd_problem(size, seed)
                    receipt = V.minimize_quadratic(A, b)
                    self.assertEqual(receipt['x'], expected)
                    self.assertEqual(receipt['L'], lower)
                    self.assertEqual(receipt['D'], diagonal)
                    self.assertEqual(receipt['min_energy'], -sum(q * x for q, x in zip(b, expected)) / 2)
                    self.assertTrue(V.verify_quadratic(A, b, receipt))
                    shifted = [x + 1 for x in expected]
                    direct = sum(shifted[i] * A[i][j] * shifted[j]
                                 for i in range(size) for j in range(size)) / 2 - sum(q * x for q, x in zip(b, shifted))
                    self.assertGreater(direct, receipt['min_energy'])

    def test_input_is_copied_into_native_immutable_vectors(self):
        A, b = [[2]], [6]
        receipt = V.minimize_quadratic(A, b)
        A[0][0], b[0] = 4, 1
        self.assertEqual(receipt['A'], ((2,),))
        self.assertEqual(receipt['b'], (6,))
        self.assertFalse(V.verify_quadratic(A, b, receipt))

    def test_same_problem_has_same_exact_canonical_receipt(self):
        A, b, *_ = spd_problem(5, 77)
        self.assertEqual(S.canon_json(V.minimize_quadratic(A, b)), S.canon_json(V.minimize_quadratic(A, b)))


class Refusals(unittest.TestCase):
    def test_indefinite_and_singular_stationary_points_do_not_certify(self):
        for A, b in (([[-1]], [0]), ([[1, 2], [2, 1]], [0, 0]),
                     ([[1, -1], [-1, 1]], [0, 0]), ([[0]], [1]), ([[0]], [0])):
            with self.subTest(A=A, b=b), self.assertRaises(V.VariationalError):
                V.minimize_quadratic(A, b)

    def test_nonsymmetric_not_silently_symmetrized(self):
        with self.assertRaisesRegex(V.VariationalError, 'symmetric'):
            V.minimize_quadratic([[2, 1], [0, 2]], [1, 1])

    def test_exact_numbers_only(self):
        class IntSubclass(int):
            pass
        for bad in (True, False, 1.0, float('inf'), float('-inf'), float('nan'),
                    Decimal(1), 1j, '1', None, IntSubclass(1)):
            for A, b in (([[bad]], [1]), ([[1]], [bad])):
                with self.subTest(value=type(bad).__name__), self.assertRaises(V.VariationalError):
                    V.minimize_quadratic(A, b)

    def test_shapes_and_dimension(self):
        for A, b in (([], []), ([1], [1]), ([[1, 0], [0]], [1, 1]), ([[1]], []),
                     ([[1]], [1, 2]), ({'a': 1}, [1]), ([[1]], {'b': 1}),
                     ([[1] * 33] * 33, [1] * 33)):
            with self.subTest(A=A), self.assertRaises(V.VariationalError):
                    V.minimize_quadratic(A, b)

    def test_corrupted_fraction_internals_fail_closed(self):
        receipt = V.minimize_quadratic([[1]], [1])
        for numerator, denominator in ((1, 0), (1, -2), (2, 4), (True, 2), ('1', 2)):
            corrupted = F(1, 2)
            corrupted._numerator, corrupted._denominator = numerator, denominator
            with self.subTest(numerator=numerator, denominator=denominator):
                with self.assertRaises(V.VariationalError):
                    V.minimize_quadratic([[corrupted]], [1])
                self.assertFalse(V.verify_quadratic([[1]], [1], {**receipt, 'x': (corrupted,)}))

    def test_limits_cannot_be_bool_fraction_or_above_hard_ceiling(self):
        for kwargs in ({'max_dimension': True}, {'max_dimension': 33}, {'max_bits': 4097},
                       {'max_bits': F(4)}, {'max_work': 0}, {'max_work': 200001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(V.VariationalError):
                V.minimize_quadratic([[1]], [1], **kwargs)

    def test_dimension_work_and_bit_limits_fail_closed(self):
        for A, b, kwargs in (([[1, 0], [0, 1]], [1, 1], {'max_dimension': 1}),
                             ([[1]], [1], {'max_work': 1}),
                             ([[1 << 5000]], [1], {}),
                             ([[1]], [15], {'max_bits': 4}),
                             ([[15]], [1], {'max_bits': 4})):
            with self.subTest(kwargs=kwargs), self.assertRaises(V.VariationalError):
                V.minimize_quadratic(A, b, **kwargs)
        receipt = V.minimize_quadratic([[2]], [6])
        self.assertFalse(V.verify_quadratic([[2]], [6], receipt, max_work=1))

    def test_multiply_preflight_and_cross_cancellation(self):
        work = V._Work(1, 8, 100)
        self.assertEqual(work.mul(F(127, 128), F(128, 127)), 1)
        with self.assertRaisesRegex(V.VariationalError, 'intermediate'):
            work.mul(F(255), F(2))
        with self.assertRaisesRegex(V.VariationalError, 'intermediate'):
            work.add(F(255), F(1))
        self.assertEqual(work.add(F(255), F(-254)), 1)


class WitnessVerification(unittest.TestCase):
    def setUp(self):
        self.A, self.b = [[4, 1], [1, 3]], [1, 2]
        self.receipt = V.minimize_quadratic(self.A, self.b)

    def test_verifier_does_not_call_solver_or_factorization(self):
        with patch.object(V, '_ldlt', side_effect=AssertionError('must not refactor')), \
             patch.object(V, '_solve', side_effect=AssertionError('must not solve')):
            self.assertTrue(V.verify_quadratic(self.A, self.b, self.receipt))

    def test_tamper_each_proof_field(self):
        changes = {'A': ((5, 1), (1, 3)), 'b': (2, 2), 'x': (0, 0),
                   'L': ((1, 1), (F(1, 4), 1)), 'D': (4, -1), 'residual': (1, 0),
                   'min_energy': 0, 'schema': 'new', 'method': 'claimed-trusted-solver', 'scope': 'physical-proof'}
        for key, value in changes.items():
            with self.subTest(field=key):
                altered = {**self.receipt, key: value}
                self.assertFalse(V.verify_quadratic(self.A, self.b, altered))

    def test_lower_triangular_positive_witness_must_reconstruct_matrix(self):
        altered = {**self.receipt, 'L': ((1, 0), (F(1, 2), 1))}
        self.assertFalse(V.verify_quadratic(self.A, self.b, altered))
        altered = {**self.receipt, 'D': (4, F(13, 4))}
        self.assertFalse(V.verify_quadratic(self.A, self.b, altered))

    def test_stationarity_alone_does_not_prove_a_minimum(self):
        receipt = V.minimize_quadratic([[1]], [0])
        receipt.update(A=((-1,),), D=(-1,))
        self.assertFalse(V.verify_quadratic([[-1]], [0], receipt))

    def test_claimed_checks_do_not_substitute_for_math_and_bool_is_strict(self):
        changed = copy.deepcopy(self.receipt)
        changed['x'] = (0, 0)
        self.assertFalse(V.verify_quadratic(self.A, self.b, changed))
        changed = copy.deepcopy(self.receipt)
        changed['checks']['unique_minimum'] = 1
        self.assertFalse(V.verify_quadratic(self.A, self.b, changed))
        changed = copy.deepcopy(self.receipt)
        changed['x'] = (True, F(7, 11))
        self.assertFalse(V.verify_quadratic(self.A, self.b, changed))

    def test_missing_extra_cyclic_nonfinite_and_oversized_data(self):
        missing = dict(self.receipt)
        missing.pop('D')
        cyclic = []
        cyclic.append(cyclic)
        for receipt in (None, [], missing, {**self.receipt, 'extra': True},
                        {**self.receipt, 'x': cyclic}, {**self.receipt, 'min_energy': float('nan')},
                        {**self.receipt, 'D': (1 << 5000, 1)}, {**self.receipt, 'L': ()}):
            with self.subTest(kind=type(receipt).__name__):
                self.assertFalse(V.verify_quadratic(self.A, self.b, receipt))


class KernelAttachment(unittest.TestCase):
    def test_default_builtins_execute_without_explicit_attachment(self):
        source = '''let answer = quadratic_minimize([[2]], [6]).
assert answer.x = [3].
assert quadratic_verify([[2]], [6], answer).
assert not quadratic_verify([[2]], [7], answer).
'''
        self.assertTrue(S.check(source)['ok'])
        report = SR.Run(source).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)

    def test_adapter_version_changes_semantic_kernel_identity(self):
        original = S.kernel_id()
        self.assertEqual(original['variational'], V.VERSION)
        self.assertEqual(original['canon'], 3)
        with patch.object(V, 'VERSION', V.VERSION + 1):
            changed = S.kernel_id()
        self.assertNotEqual(original['id'], changed['id'])
        self.assertEqual(original, S.kernel_id())

    def test_optional_missing_module_refuses_and_has_distinct_identity(self):
        original = S.kernel_id()
        with patch.dict('sys.modules', {'symblic.adapters.variational': None}):
            changed = S.kernel_id()
            report = SR.Run('let answer = quadratic_minimize([[2]], [6]).').execute()
        self.assertIsNone(changed['variational'])
        self.assertNotEqual(original['id'], changed['id'])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'unavailable')

    def test_import_does_not_register_or_change_global_builtins(self):
        before = dict(S.BUILTINS)
        spec = importlib.util.spec_from_file_location('_variational_inert_fixture', V.__file__)
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)
        self.assertEqual(S.BUILTINS, before)

    def test_explicit_attachment_executes_exact_program_without_models(self):
        source = '''let A = [[4, 1], [1, 3]].
let b = [1, 2].
let answer = quadratic_minimize(A, b).
assert quadratic_verify(A, b, answer).
assert answer.x = [1/11, 7/11].
assert answer.min_energy = -15/22.
show answer.x.
'''
        run = SR.Run(source)
        V.register(run.kernel)
        V.register(run.kernel)
        report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)
        self.assertEqual(run.kernel.env.lookup('answer').value['x'], (F(1, 11), F(7, 11)))

    def test_global_kernel_budget_exhaustion_is_not_swallowed_by_verifier(self):
        receipt = V.minimize_quadratic([[2]], [6])
        for fn, args in ((V.minimize_quadratic, ([[2]], [6])),
                         (V.verify_quadratic, ([[2]], [6], receipt))):
            with self.subTest(fn=fn.__name__), self.assertRaises(S.SymblicError):
                fn(*args, budget=S.Budget(1))

    def test_existing_function_not_overwritten(self):
        kernel = S.Kernel()
        existing = lambda *_args: 3
        kernel.functions['quadratic_minimize'] = existing
        with self.assertRaises(V.VariationalError):
            V.register(kernel)
        self.assertIs(kernel.functions['quadratic_minimize'], existing)
        self.assertNotIn('quadratic_verify', kernel.functions)


if __name__ == '__main__':
    unittest.main()
