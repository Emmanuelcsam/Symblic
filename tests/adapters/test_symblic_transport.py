"""Finite exact transport checks; no providers, stores or worker launches."""
import copy
import importlib.util
import itertools
import random
import unittest
from decimal import Decimal
from fractions import Fraction as F

from symblic.kernel import language as S
from symblic.kernel import run as SR
from symblic.adapters import transport as T


def atoms(*pairs):
    return [{'at': at, 'mass': mass} for at, mass in pairs]


def empirical(values):
    return atoms(*((value, 1) for value in values))


def assignment_minimum(left, right):
    """Enumerate all assignments of equal-mass particles, not a CDF sweep."""
    assert len(left) == len(right)
    return min(sum(abs(x - y) for x, y in zip(left, permutation))
               for permutation in itertools.permutations(right)) / F(len(left))


class ExactTransport(unittest.TestCase):
    def test_known_distances_and_exact_rationals(self):
        cases = ((atoms((0, 1)), atoms((3, 7)), 3),
                 (atoms((0, 1), (2, 1)), atoms((1, 1)), 1),
                 (atoms((0, 1), (3, 2)), atoms((1, 1), (4, 3)), F(5, 4)),
                 (atoms((F(1, 3), F(2, 7))), atoms((F(2, 5), F(5, 9))), F(1, 15)))
        for left, right, expected in cases:
            with self.subTest(left=left, right=right):
                actual = T.wasserstein1(left, right)
                self.assertEqual(actual, expected)
                self.assertIn(type(actual), (int, F))

    def test_independent_exhaustive_assignment_reference(self):
        rng = random.Random(90173)
        for size in range(1, 7):
            for _ in range(6):
                left = [F(rng.randint(-6, 6), rng.randint(1, 4)) for _ in range(size)]
                right = [F(rng.randint(-6, 6), rng.randint(1, 4)) for _ in range(size)]
                with self.subTest(size=size, left=left, right=right):
                    self.assertEqual(T.wasserstein1(empirical(left), empirical(right)),
                                     assignment_minimum(left, right))

    def test_independent_weighted_couplings_via_expanded_particles(self):
        # The normalized weights have denominator six. Every coupling optimum
        # has an integral six-particle representative; enumerate all assignments.
        left = atoms((-2, 2), (1, 3), (5, 1))
        right = atoms((-1, F(1, 6)), (2, F(1, 2)), (4, F(1, 3)))
        expected = assignment_minimum([-2, -2, 1, 1, 1, 5], [-1, 2, 2, 2, 4, 4])
        self.assertEqual(T.wasserstein1(left, right), expected)

    def test_equal_medians_can_still_have_different_distributions(self):
        # Both medians are one. W1 retains the encoded dispersion difference.
        self.assertEqual(T.wasserstein1(empirical([0, 1, 2]), empirical([1, 1, 1])), F(2, 3))

    def test_symmetry_translation_scaling_and_triangle(self):
        distributions = [atoms((-2, 2), (1, 3), (4, 1)), atoms((0, 5), (8, 2)),
                         atoms((-3, 1), (F(2, 3), 1), (2, 1))]
        for left, right in itertools.product(distributions, repeat=2):
            distance = T.wasserstein1(left, right)
            self.assertEqual(distance, T.wasserstein1(right, left))
            for scale, shift in ((1, F(7, 3)), (-2, 5), (F(2, 3), 0), (0, 9)):
                def transform(items, scale=scale, shift=shift):
                    return atoms(*((scale * item['at'] + shift, item['mass']) for item in items))
                self.assertEqual(T.wasserstein1(transform(left), transform(right)), abs(scale) * distance)
            for middle in distributions:
                self.assertLessEqual(distance, T.wasserstein1(left, middle) + T.wasserstein1(middle, right))

    def test_split_duplicate_reorder_zero_and_independent_mass_scaling(self):
        left = atoms((0, 1), (2, 3))
        split = atoms((2, F(1, 3)), (0, F(1, 2)), (2, F(2, 3)), (99, 0),
                      (0, F(1, 2)), (2, 2))
        for order in (split, list(reversed(split))):
            self.assertEqual(T.wasserstein1(left, order), 0)
        right = atoms((-1, 2), (7, 5))
        scaled = atoms(*((v['at'], v['mass'] * 11) for v in right))
        self.assertEqual(T.wasserstein1(left, right), T.wasserstein1(left, scaled))

    def test_input_not_mutated(self):
        left, right = atoms((2, 3), (0, 1)), atoms((1, 1))
        original = copy.deepcopy((left, right))
        T.wasserstein1(left, right)
        self.assertEqual((left, right), original)

    def test_maximum_atom_count_has_bounded_exact_result(self):
        left = empirical(range(T.MAX_ATOMS))
        right = empirical(range(1, T.MAX_ATOMS + 1))
        self.assertEqual(T.wasserstein1(left, right), 1)


class Refusals(unittest.TestCase):
    def test_shapes_and_extra_fields(self):
        for bad in ([], (), {}, None, '0', [0], [{'at': 1}], [{'mass': 1}],
                    [{'at': 0, 'mass': 1, 'unit': 'm'}], [{0: 1, 'mass': 1}]):
            with self.subTest(bad=bad), self.assertRaises(T.TransportError):
                T.wasserstein1(bad, atoms((0, 1)))

    def test_nonnegative_positive_total_and_validation_of_zero_mass_atoms(self):
        for bad in (atoms((0, -1)), atoms((0, 1), (1, -1)), atoms((1, 0)),
                    atoms((float('inf'), 0), (1, 1))):
            with self.subTest(bad=bad), self.assertRaises(T.TransportError):
                T.wasserstein1(bad, atoms((0, 1)))

    def test_only_native_exact_numbers(self):
        class IntSubclass(int):
            pass
        for bad in (True, False, 1.0, float('inf'), float('-inf'), float('nan'),
                    Decimal(1), '1', None, 1j, IntSubclass(1)):
            for field in ('at', 'mass'):
                value = {'at': 0, 'mass': 1, field: bad}
                with self.subTest(bad=type(bad).__name__, field=field), self.assertRaises(T.TransportError):
                    T.wasserstein1([value], atoms((0, 1)))

    def test_forged_fraction_is_rejected(self):
        for numerator, denominator in ((2, 4), (1, 0), (1, -2), (True, 2)):
            forged = object.__new__(F)
            forged._numerator, forged._denominator = numerator, denominator
            with self.subTest(pair=(numerator, denominator)), self.assertRaises(T.TransportError):
                T.wasserstein1(atoms((forged, 1)), atoms((0, 1)))

    def test_limits_are_strict_and_input_atom_bound_counts_zero_entries(self):
        for option, ceiling in (('max_atoms', T.MAX_ATOMS), ('max_bits', T.MAX_BITS),
                                ('max_work', T.MAX_WORK)):
            for bad in (True, 0, -1, 1.0, ceiling + 1):
                with self.subTest(option=option, value=bad), self.assertRaises(T.TransportError):
                    T.wasserstein1(atoms((0, 1)), atoms((1, 1)), **{option: bad})
        with self.assertRaises(T.TransportError):
            T.wasserstein1(atoms((0, 1), (1, 0)), atoms((0, 1)), max_atoms=1)

    def test_bit_bounds_cover_inputs_mass_sum_width_and_sort_intermediates(self):
        cases = ((atoms((8, 1)), atoms((0, 1)), 3),
                 (atoms((0, 7), (1, 7)), atoms((0, 1)), 3),
                 (atoms((-7, 1)), atoms((7, 1)), 3),
                 # These positions fit in four bits, but ordering via exact
                 # rational subtraction needs an oversized intermediate.
                 (atoms((F(7, 11), 1), (F(8, 13), 1)), atoms((0, 1)), 4))
        for left, right, bits in cases:
            with self.subTest(bits=bits, left=left), self.assertRaises(T.TransportError) as caught:
                T.wasserstein1(left, right, max_bits=bits)
            self.assertEqual(caught.exception.kind, 'budget')

    def test_local_work_exhaustion_and_global_kernel_budget(self):
        with self.assertRaisesRegex(T.TransportError, 'work budget'):
            T.wasserstein1(atoms((0, 1)), atoms((1, 1)), max_work=1)
        with self.assertRaises(S.SymblicError) as caught:
            T.wasserstein1(atoms((0, 1)), atoms((1, 1)), budget=S.Budget(1))
        self.assertNotIsInstance(caught.exception, T.TransportError)
        first, second = S.Budget(10000), S.Budget(10000)
        for budget in (first, second):
            T.wasserstein1(atoms((0, 1), (3, 2)), atoms((1, 1)), budget=budget)
        self.assertEqual(first.left, second.left)
        self.assertLess(first.left, 10000)


class KernelAttachment(unittest.TestCase):
    def test_import_is_inert(self):
        before = S.BUILTINS.copy()
        spec = importlib.util.spec_from_file_location('_transport_inert_probe', T.__file__)
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)
        self.assertEqual(S.BUILTINS, before)

    def test_exact_program_via_explicit_registration_without_calls(self):
        source = '''let left = [{at: 0, mass: 1}, {at: 2, mass: 1}].
let right = [{at: 1, mass: 3}].
let distance = wasserstein1(left, right).
assert distance = 1.
show distance.
'''
        run = SR.Run(source)
        self.assertIs(T.register(run.kernel), run.kernel)
        T.register(run.kernel)
        report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)
        self.assertEqual(run.kernel.env.lookup('distance').value, 1)

    def test_existing_name_not_overwritten(self):
        kernel = S.Kernel()
        existing = lambda *_args: 3
        kernel.functions['wasserstein1'] = existing
        with self.assertRaises(T.TransportError):
            T.register(kernel)
        self.assertIs(kernel.functions['wasserstein1'], existing)
        with self.assertRaises(T.TransportError):
            T.register({})


if __name__ == '__main__':
    unittest.main()
