"""Exact Ising ground states by exhaustive enumeration; no stores, workers, services or model calls."""
import copy
import importlib.util
import itertools
import os
import random
import re
import unittest
from decimal import Decimal
from fractions import Fraction as F
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.adapters import discrete as D
from symblic.kernel import run as SR

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE = S.Node('call', 1, 1, fn='ising_minimize', args=[], kwargs={})


def kernel(steps=S.MAX_STEPS):
    return S.Kernel(S.Env(), S.KB(), S.Budget(steps))


def minimize(h, J, k=None):
    return D.FUNCTIONS['ising_minimize'](k or kernel(), NODE, h, J)


def energy(h, J, s, k=None):
    return D.FUNCTIONS['ising_energy'](k or kernel(), NODE, h, J, s)


def zeros(n):
    return [[0] * n for _ in range(n)]


def chain(n, coupling):
    J = zeros(n)
    for i in range(n - 1):
        J[i][i + 1] = J[i + 1][i] = coupling
    return J


def flip(state):
    return tuple(-x for x in state)


def brute_force(h, J):
    """Independent reference: every state from itertools.product (lexicographic, -1 before 1), each
    energy from the formula with exact fractions. Returns (minimum, ground states in order, all energies)."""
    n = len(h)
    table = {}
    for s in itertools.product((-1, 1), repeat=n):
        e = F(0)
        for i in range(n):
            e -= F(h[i]) * s[i]
            for j in range(i + 1, n):
                e -= F(J[i][j]) * s[i] * s[j]
        table[s] = e
    low = min(table.values())
    return low, [s for s, e in table.items() if e == low], table


def random_instance(rng, n, zero_field, sparse):
    """Small rationals with many repeats and zeros, so ties (and, when sparse, truncation) occur."""
    numerators = (-1, 1) + (0,) * 8 if sparse else (-2, -1, 0, 1, 2)

    def pick():
        return F(rng.choice(numerators), rng.choice((1, 2, 3)))
    h = [0] * n if zero_field else [pick() for _ in range(n)]
    J = zeros(n)
    for i in range(n):
        for j in range(i + 1, n):
            J[i][j] = J[j][i] = pick()
    return h, J


def mattis(pattern):
    """J[i][j] = t[i]*t[j]: with h = 0 the ground states are exactly t and -t (planted)."""
    n = len(pattern)
    return [[0 if i == j else pattern[i] * pattern[j] for j in range(n)] for i in range(n)]


class HandChecked(unittest.TestCase):
    def test_ferromagnetic_chain_has_two_ground_states(self):
        result = minimize([0, 0, 0, 0], chain(4, 1))
        self.assertEqual(result, {'energy': -3, 'degeneracy': 2,
                                  'states': ((-1, -1, -1, -1), (1, 1, 1, 1)),
                                  'truncated': False, 'spins': 4, 'method': 'exhaustive'})

    def test_antiferromagnetic_triangle_is_frustrated_with_six_ground_states(self):
        J = [[0, -1, -1], [-1, 0, -1], [-1, -1, 0]]
        result = minimize([0, 0, 0], J)
        self.assertEqual(result['energy'], -1)
        self.assertEqual(result['degeneracy'], 6)
        self.assertEqual(result['states'], ((-1, -1, 1), (-1, 1, -1), (-1, 1, 1),
                                            (1, -1, -1), (1, -1, 1), (1, 1, -1)))
        for s in result['states']:     # frustrated: every ground state leaves exactly one bond unsatisfied
            self.assertEqual(sum(s[i] * s[j] == 1 for i, j in ((0, 1), (0, 2), (1, 2))), 1)

    def test_a_field_makes_the_ground_state_unique(self):
        result = minimize([F(1, 2), 0, 0, 0], chain(4, 1))
        self.assertEqual(result['energy'], F(-7, 2))
        self.assertEqual(result['degeneracy'], 1)
        self.assertEqual(result['states'], ((1, 1, 1, 1),))
        # on the frustrated triangle the same field only halves the count
        result = minimize([F(1, 2), 0, 0], [[0, -1, -1], [-1, 0, -1], [-1, -1, 0]])
        self.assertEqual((result['energy'], result['degeneracy']), (F(-3, 2), 3))
        self.assertEqual(result['states'], ((1, -1, -1), (1, -1, 1), (1, 1, -1)))

    def test_rational_coefficients_give_exact_fractions(self):
        h, J = [F(1, 3), F(-1, 5)], [[0, F(2, 7)], [F(2, 7), 0]]
        result = minimize(h, J)
        self.assertEqual(result['energy'], F(-44, 105))
        self.assertEqual((result['degeneracy'], result['states']), (1, ((1, 1),)))
        # E(s) = -s1/3 + s2/5 - 2*s1*s2/7, worked by hand over the common denominator 105
        for s, expected in (((-1, -1), F(-16, 105)), ((-1, 1), F(86, 105)),
                            ((1, -1), F(-26, 105)), ((1, 1), F(-44, 105))):
            with self.subTest(s=s):
                self.assertEqual(energy(h, J, s), expected)

    def test_one_spin(self):
        self.assertEqual(minimize([2], [[0]])['states'], ((1,),))
        self.assertEqual(minimize([-2], [[0]])['states'], ((-1,),))
        free = minimize([0], [[0]])
        self.assertEqual((free['energy'], free['degeneracy'], free['states']), (0, 2, ((-1,), (1,))))

    def test_every_reported_state_has_the_reported_energy(self):
        for h, J in (([0, 0, 0, 0], chain(4, 1)), ([F(1, 2), 0, 0], [[0, -1, -1], [-1, 0, -1], [-1, -1, 0]]),
                     ([F(1, 3), F(-1, 5)], [[0, F(2, 7)], [F(2, 7), 0]]), ([0] * 5, zeros(5))):
            result = minimize(h, J)
            for s in result['states']:
                with self.subTest(h=h, s=s):
                    self.assertEqual(energy(h, J, s), result['energy'])


class Degeneracy(unittest.TestCase):
    def test_zero_field_gives_even_degeneracy_closed_under_flip(self):
        rng = random.Random(7031)
        for n in range(1, 9):
            for _ in range(3):
                _, J = random_instance(rng, n, zero_field=True, sparse=n % 2 == 0)
                result = minimize([0] * n, J)
                with self.subTest(n=n, J=J):
                    self.assertEqual(result['degeneracy'] % 2, 0)
                    if not result['truncated']:
                        self.assertEqual(set(result['states']), {flip(s) for s in result['states']})

    def test_truncation_at_sixteen_states_keeps_the_true_degeneracy(self):
        result = minimize([0] * 5, zeros(5))
        self.assertEqual((result['energy'], result['degeneracy'], result['truncated']), (0, 32, True))
        self.assertEqual(len(result['states']), D.MAX_STATES)
        self.assertEqual(result['states'], tuple(itertools.product((-1, 1), repeat=5))[:16])
        self.assertTrue(all(s[0] == -1 for s in result['states']))

    def test_exactly_sixteen_ground_states_are_not_truncated(self):
        result = minimize([0] * 4, zeros(4))
        self.assertEqual((result['degeneracy'], len(result['states']), result['truncated']), (16, 16, False))
        self.assertEqual(result['states'], tuple(itertools.product((-1, 1), repeat=4)))

    def test_truncated_states_are_the_lexicographically_first(self):
        # The walk visits states in Gray-code order. With h[1] = 1 every ground state has spin 1 at +1, and the
        # walk reaches the 16 with spin 2 at +1 before the 16 with spin 2 at -1, which come first in the result.
        for h, J in (([1, 0, 0, 0, 0, 0], zeros(6)), ([0] * 8, zeros(8)), ([0, 0, 0, 0, 0, 1], zeros(6)),
                     ([0] * 7, chain(7, 0)), ([0, 1, 0, 0, 0, 0, 0], chain(7, 0))):
            result = minimize(h, J)
            low, ground, _ = brute_force(h, J)
            with self.subTest(n=len(h)):
                self.assertEqual(result['energy'], low)
                self.assertEqual(result['degeneracy'], len(ground))
                self.assertEqual(result['states'], tuple(ground[:16]))
                self.assertEqual(result['truncated'], len(ground) > 16)


class BruteForce(unittest.TestCase):
    def test_forty_random_rational_instances_agree_with_brute_force(self):
        rng = random.Random(20261003)
        seen = {'degenerate': 0, 'truncated': 0, 'fraction': 0, 'unique': 0}
        for index in range(40):
            n = 1 + index % 8
            h, J = random_instance(rng, n, zero_field=index % 4 == 3, sparse=index % 5 == 4)
            result = minimize(h, J)
            low, ground, table = brute_force(h, J)
            with self.subTest(index=index, n=n):
                self.assertEqual(result['energy'], low)
                self.assertEqual(result['degeneracy'], len(ground))
                self.assertEqual(result['states'], tuple(ground[:D.MAX_STATES]))
                self.assertEqual(result['truncated'], len(ground) > D.MAX_STATES)
                self.assertEqual(result['spins'], n)
                if index % 4 == 3:
                    self.assertEqual(result['degeneracy'] % 2, 0)
                for s in result['states']:
                    self.assertEqual(energy(h, J, s), low)
                for s in rng.sample(sorted(table), min(3, len(table))):
                    self.assertEqual(energy(h, J, s), table[s])
            seen['degenerate'] += result['degeneracy'] > 1
            seen['unique'] += result['degeneracy'] == 1
            seen['truncated'] += result['truncated']
            seen['fraction'] += type(result['energy']) is F
        # the generated set exercises every branch of the result, not only easy cases
        self.assertTrue(all(seen.values()), seen)


class Limits(unittest.TestCase):
    PATTERN = (1, -1, -1, 1, 1, 1, -1, 1, -1, -1, 1, -1, 1, 1, -1, -1)

    def test_sixteen_spins_find_the_planted_ground_states(self):
        J = mattis(self.PATTERN)
        result = minimize([0] * 16, J)
        self.assertEqual((result['energy'], result['degeneracy'], result['spins']), (-120, 2, 16))
        self.assertEqual(result['states'], tuple(sorted((self.PATTERN, flip(self.PATTERN)))))
        pulled = minimize([F(t, 17) for t in self.PATTERN], J)
        self.assertEqual(pulled['energy'], F(-2056, 17))          # -120 - 16/17
        self.assertEqual((pulled['degeneracy'], pulled['states']), (1, (self.PATTERN,)))
        self.assertEqual(energy([F(t, 17) for t in self.PATTERN], J, self.PATTERN), F(-2056, 17))

    def test_zero_and_seventeen_spins_are_refused(self):
        for fn, args, kind in ((minimize, ([], []), 'type'), (energy, ([], [], []), 'type'),
                               (minimize, ([0] * 17, zeros(17)), 'budget'),
                               (energy, ([0] * 17, zeros(17), [1] * 17), 'budget')):
            with self.subTest(fn=fn.__name__, n=len(args[0])):
                with self.assertRaises(D.DiscreteError) as caught:
                    fn(*args)
                self.assertEqual(caught.exception.kind, kind)

    def test_bit_limit_boundary(self):
        widest = (1 << D.MAX_BITS) - 1
        self.assertEqual(minimize([widest], [[0]])['energy'], -widest)
        self.assertEqual(minimize([F(1, widest)], [[0]])['energy'], F(-1, widest))
        for h in ([1 << D.MAX_BITS], [F(1, 1 << D.MAX_BITS)], [-(1 << D.MAX_BITS)]):
            with self.subTest(bits=D.MAX_BITS + 1), self.assertRaises(D.DiscreteError) as caught:
                minimize(h, [[0]])
            self.assertEqual(caught.exception.kind, 'budget')

    def test_common_denominator_and_scaled_coefficient_limits(self):
        # each entry is within the limit; their common denominator is not (coprime odd numbers)
        h = [F(1, (1 << 4000) + 1), F(1, (1 << 4000) + 3)]
        with self.assertRaisesRegex(D.DiscreteError, 'common denominator') as caught:
            minimize(h, zeros(2))
        self.assertEqual(caught.exception.kind, 'budget')
        # within the limit before clearing denominators, above it after
        with self.assertRaisesRegex(D.DiscreteError, 'times the common denominator') as caught:
            energy([1 << 4000, F(1, 1 << 200)], zeros(2), [1, 1])
        self.assertEqual(caught.exception.kind, 'budget')


class Refusals(unittest.TestCase):
    def assertRefused(self, kind, fn, *args):
        with self.assertRaises(D.DiscreteError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.kind, kind, caught.exception.message)
        return caught.exception

    def test_asymmetric_coupling_is_refused_not_symmetrized(self):
        error = self.assertRefused('check', minimize, [0, 0], [[0, 1], [2, 0]])
        self.assertIn('symmetric', error.message)
        self.assertRefused('check', minimize, [0, 0, 0], [[0, F(1, 3), 0], [F(1, 3), 0, 1], [0, F(999, 1000), 0]])
        self.assertRefused('check', energy, [0, 0], [[0, 1], [-1, 0]], [1, 1])

    def test_nonzero_diagonal_is_refused(self):
        for J in ([[1, 0], [0, 0]], [[0, 0], [0, F(-1, 2)]]):
            with self.subTest(J=J):
                error = self.assertRefused('check', minimize, [0, 0], J)
                self.assertIn('diagonal', error.message)
                self.assertRefused('check', energy, [0, 0], J, [1, 1])
        self.assertRefused('check', minimize, [0], [[3]])

    def test_floats_bools_and_other_kinds_are_refused(self):
        class IntSubclass(int):
            pass
        for bad in (True, False, 1.0, 0.0, float('inf'), float('nan'), Decimal(1), 1j, '1', None,
                    IntSubclass(1), (1,), {'a': 1}):
            for h, J in (([bad, 0], zeros(2)), ([0, 0], [[0, bad], [bad, 0]]), ([0, 0], [[bad, 0], [0, 0]])):
                with self.subTest(value=repr(bad), h=h):
                    self.assertRefused('type', minimize, h, J)
                    self.assertRefused('type', energy, h, J, [1, 1])

    def test_wrong_lengths_and_shapes_are_refused(self):
        for h, J in (([0, 0], [[0, 0]]), ([0, 0], [[0, 0], [0, 0], [0, 0]]), ([0, 0], [[0, 0], [0]]),
                     ([0, 0], [[0, 0], [0, 0, 0]]), ([0], []), ([0], [0]), ([0], 0), ([0], '0'),
                     ([0], {'row': [0]}), ([0], [S.ValueSet([0])]), (S.ValueSet([0, 1]), zeros(2)),
                     ({'a': 0}, [[0]]), ('0', [[0]]), (None, [[0]]), (0, [[0]])):
            with self.subTest(h=h, J=J):
                self.assertRefused('type', minimize, h, J)
        for s in ([1], [1, 1, 1], (), None, S.ValueSet([1, -1]), '11', {'s': 1}):
            with self.subTest(s=s):
                self.assertRefused('type', energy, [0, 0], zeros(2), s)

    def test_huge_integers_are_refused(self):
        huge = 1 << 5000
        for case, (h, J, s) in enumerate((([huge, 0], zeros(2), [1, 1]), ([0, 0], [[0, huge], [huge, 0]], [1, 1]),
                                          ([F(1, huge), 0], zeros(2), [1, 1]),
                                          ([0, 0], [[0, F(-1, huge)], [F(-1, huge), 0]], [1, 1]),
                                          ([0, 0], zeros(2), [huge, 1]))):
            with self.subTest(case=case):
                if s == [1, 1]:
                    self.assertRefused('budget', minimize, h, J)
                self.assertRefused('budget', energy, h, J, s)

    def test_spins_must_be_minus_one_or_one(self):
        for s in ((0, 1), (2, 1), (1, -2), (F(1, 2), 1), (F(-1, 3), 1)):
            with self.subTest(s=s):
                self.assertRefused('check', energy, [0, 0], zeros(2), s)
        for s in ((True, 1), (1, False), (1.0, 1), ('1', 1), (None, 1), ((1,), 1)):
            with self.subTest(s=s):
                self.assertRefused('type', energy, [0, 0], zeros(2), s)
        self.assertEqual(energy([1, 0], zeros(2), (F(1), -1)), -1)    # an exact 1 written as a fraction

    def test_corrupted_fraction_internals_are_refused(self):
        for numerator, denominator in ((1, 0), (1, -2), (2, 4), (True, 2), ('1', 2)):
            corrupted = F(1, 2)
            corrupted._numerator, corrupted._denominator = numerator, denominator
            with self.subTest(numerator=numerator, denominator=denominator):
                self.assertRefused('type', minimize, [corrupted], [[0]])
                self.assertRefused('type', energy, [0, 0], zeros(2), [corrupted, 1])

    def test_a_kernel_without_a_budget_is_refused(self):
        for k in (None, object()):
            with self.subTest(kernel=k):
                with self.assertRaises(D.DiscreteError):
                    D.FUNCTIONS['ising_minimize'](k, NODE, [0], [[0]])
                with self.assertRaises(D.DiscreteError):
                    D.FUNCTIONS['ising_energy'](k, NODE, [0], [[0]], [1])
        self.assertRefused('type', lambda: D.minimize_ising([0], [[0]], budget=10))


class Budget(unittest.TestCase):
    def test_exact_charges(self):
        n, k = 10, kernel(100_000)
        minimize([0] * n, chain(n, 1), k)
        self.assertEqual(100_000 - k.budget.left, n + n * n + 2 ** n)
        k = kernel(100_000)
        energy([0] * n, chain(n, 1), [1] * n, k)
        self.assertEqual(100_000 - k.budget.left, 2 * n + n * n + n + n * (n - 1) // 2)

    def test_the_walk_is_paid_for_before_it_starts(self):
        n = 10
        exact = n + n * n + 2 ** n
        with patch.object(D, '_walk', side_effect=AssertionError('the walk must not start')):
            with self.assertRaisesRegex(S.SymblicError, 'step budget'):
                minimize([0] * n, chain(n, 1), kernel(exact - 1))
        k = kernel(exact)
        self.assertEqual(minimize([0] * n, chain(n, 1), k)['degeneracy'], 2)
        self.assertEqual(k.budget.left, 0)

    def test_entries_are_paid_for_before_they_are_read(self):
        n = 6
        with patch.object(D, '_entries', side_effect=AssertionError('entries must not be read')):
            with self.assertRaises(S.SymblicError):
                minimize([0] * n, zeros(n), kernel(n + n * n - 1))
            with self.assertRaises(S.SymblicError):
                energy([0] * n, zeros(n), [1] * n, kernel(2 * n + n * n - 1))

    def test_sizes_are_checked_before_any_charge(self):
        for args, fn in ((([0] * 17, zeros(17)), minimize), ((([0] * 3, zeros(2))), minimize),
                         (([0] * 3, zeros(3), [1]), energy)):
            k = kernel(1000)
            with self.subTest(fn=fn.__name__), self.assertRaises(D.DiscreteError):
                fn(*args, k=k)
            self.assertEqual(k.budget.left, 1000)


class CanonicalForm(unittest.TestCase):
    def test_results_are_canonical_kernel_values(self):
        result = minimize([F(1, 3), F(-1, 5)], [[0, F(2, 7)], [F(2, 7), 0]])
        self.assertEqual(set(result), set(D.FIELDS))
        self.assertEqual(S.canon_json(result), '{"degeneracy":1,"energy":{"#q":"-44/105"},"method":"exhaustive",'
                                               '"spins":2,"states":[[1,1]],"truncated":false}')
        self.assertRegex(S.fingerprint(result), '^[0-9a-f]{16}$')
        for h, J in (([0] * 5, zeros(5)), ([F(1, 2), 0, 0, 0], chain(4, 1)), ([2, 0], chain(2, F(4, 2)))):
            result = minimize(h, J)
            with self.subTest(h=h):
                S.canon(result)
                self.assertIs(type(result['states']), tuple)
                self.assertTrue(all(type(s) is tuple and all(type(x) is int and x in (-1, 1) for x in s)
                                    for s in result['states']))
                self.assertIs(type(result['truncated']), bool)
                self.assertIs(type(result['degeneracy']), int)
                self.assertIs(type(result['spins']), int)
                value = result['energy']
                self.assertTrue(type(value) is int or (type(value) is F and value.denominator != 1))
        self.assertIs(type(minimize([2, 0], chain(2, F(4, 2)))['energy']), int)
        self.assertIs(type(energy([F(1, 2), F(1, 2)], zeros(2), [1, 1])), int)
        S.canon(energy([F(1, 3), 0], zeros(2), [1, 1]))

    def test_same_problem_same_fingerprint_however_written(self):
        h, J = [F(1, 2), -1, 0], [[0, 2, F(-1, 3)], [2, 0, 0], [F(-1, 3), 0, 0]]
        written = (minimize(h, J), minimize(tuple(h), tuple(tuple(r) for r in J)),
                   minimize([F(1, 2), F(-1), F(0)], [[F(0), F(2), F(-1, 3)], [F(2), 0, 0], [F(-1, 3), 0, 0]]),
                   minimize(h, J))
        self.assertEqual(len({S.fingerprint(r) for r in written}), 1)
        self.assertEqual(len({S.canon_json(r) for r in written}), 1)

    def test_inputs_are_not_mutated(self):
        h, J = [F(1, 2), 0, 0], [[0, -1, -1], [-1, 0, -1], [-1, -1, 0]]
        before = copy.deepcopy((h, J))
        result = minimize(h, J)
        energy(h, J, list(result['states'][0]))
        self.assertEqual((h, J), before)


class Audit(unittest.TestCase):
    def test_a_defective_walk_is_caught_before_a_result_is_returned(self):
        original = D._walk

        def wrong_minimum(n, fields, couplings):
            best, count, codes, code, final = original(n, fields, couplings)
            return best - 1, count, codes, code, final

        def wrong_final(n, fields, couplings):
            best, count, codes, code, final = original(n, fields, couplings)
            return best, count, codes, code, final + 1

        for defect in (wrong_minimum, wrong_final):
            with self.subTest(defect=defect.__name__), patch.object(D, '_walk', side_effect=defect):
                with self.assertRaises(D.DiscreteError) as caught:
                    minimize([F(1, 3), 0, 1], [[0, 1, 0], [1, 0, -2], [0, -2, 0]])
                self.assertEqual(caught.exception.kind, 'runtime')


def evaluate(source, **bindings):
    env = S.Env()
    for name, value in bindings.items():
        env.vars[name] = S.Binding(name, value)
    parser = S.Parser(S.tokenize(source), 1)
    node = parser.expr()
    parser.finish()
    k = kernel()
    k.functions.update(D.FUNCTIONS)
    return k.eval(node, env)


def run_program(source, **options):
    """A kernel-only run with no folder (nothing is written) and no applicators (no model can be called)."""
    run = SR.Run(source, options=options)
    run.kernel.functions.update(D.FUNCTIONS)       # the host's registration; a builtin of the same name wins
    return run.execute(), run


class KernelPrograms(unittest.TestCase):
    def test_expressions_evaluate_through_the_kernel(self):
        self.assertEqual(evaluate('ising_minimize([0, 0], [[0, 1], [1, 0]]).degeneracy'), 2)
        self.assertEqual(evaluate('ising_minimize([1/3, -1/5], [[0, 2/7], [2/7, 0]]).energy'), F(-44, 105))
        self.assertIs(evaluate('ising_minimize([0, 0], [[0, -1], [-1, 0]]).states = [[-1, 1], [1, -1]]'), True)
        self.assertEqual(evaluate('ising_energy(h, J, [1, -1])', h=(1, 0), J=((0, 2), (2, 0))), 1)

    def test_documented_example_checks_runs_and_prints_its_documented_output(self):
        with open(os.path.join(ROOT, 'docs', 'reference', 'DISCRETE.md'), encoding='utf-8') as stream:
            text = stream.read()
        programs = re.findall(r'```symblic\n(.*?)```', text, re.S)
        outputs = re.findall(r'```text\n(.*?)```', text, re.S)
        self.assertEqual((len(programs), len(outputs)), (1, 1))
        self.assertTrue(S.check(programs[0])['ok'], S.check(programs[0])['errors'])
        report, _ = run_program(programs[0])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual((report['asks'], report['calls']), (0, 0))
        self.assertEqual([row['text'] for row in report['outputs']], outputs[0].strip().split('\n'))

    def test_a_refusal_reaches_the_program_with_its_kind_and_line(self):
        report, _ = run_program('let J = [[0, 1], [2, 0]].\nlet r = ising_minimize([0, 0], J).\n')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual((report['error']['kind'], report['error']['line']), ('check', 2))

    def test_budget_exhaustion_fails_the_run_at_the_call(self):
        row = '[' + ', '.join(['0'] * 10) + ']'
        setup = f'let h = {row}.\nlet J = [' + ', '.join([row] * 10) + '].\n'
        _, run = run_program(setup)
        used = S.MAX_STEPS - run.kernel.budget.left
        # room for the setup, not for the call's 10 + 100 + 1024 steps
        report, _ = run_program(setup + 'let r = ising_minimize(h, J).\n', max_steps=used + 500)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['line'], 3)
        self.assertIn('step budget', report['error']['message'])

    def test_import_is_inert_and_the_names_are_fixed(self):
        before = dict(S.BUILTINS)
        spec = importlib.util.spec_from_file_location('_discrete_inert_fixture', D.__file__)
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)
        self.assertEqual(S.BUILTINS, before)
        self.assertEqual(set(D.FUNCTIONS), {'ising_minimize', 'ising_energy'})
        self.assertFalse(set(D.FUNCTIONS) & (set(S.KEYWORDS) | S.WORD_OPS))
        self.assertEqual((D.VERSION, D.MAX_SPINS, D.MAX_STATES, D.METHOD), (1, 16, 16, 'exhaustive'))
        self.assertTrue(issubclass(D.DiscreteError, S.SymblicError))


if __name__ == '__main__':
    unittest.main()
