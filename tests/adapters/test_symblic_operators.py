"""Exact finite operators and ordered questions; no stores, workers, services or model calls."""
import copy
import importlib.util
import os
import random
import re
import unittest
from decimal import Decimal
from fractions import Fraction as F
from itertools import product
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.adapters import operators as O
from symblic.kernel import run as SR

DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'docs', 'reference', 'OPERATORS.md')
NAMES = ('is_projector', 'commutator', 'commutes', 'ordered_probability')
STEPS = 10 ** 6


def make_kernel(steps=STEPS):
    return S.Kernel(S.Env(), S.KB(), S.Budget(steps))


def call(name, *args, **kwargs):
    """A builtin as the kernel calls it: FUNCTIONS[name](kernel, node, ...) on a fresh real Kernel."""
    return O.FUNCTIONS[name](make_kernel(), None, *args, **kwargs)


def charge(name, *args):
    kernel = make_kernel()
    O.FUNCTIONS[name](kernel, None, *args)
    return STEPS - kernel.budget.left


# -- an independent reference: plain Fraction arithmetic; matrices are multiplied before they are applied ----

def identity(n):
    return [[F(int(i == j)) for j in range(n)] for i in range(n)]


def diag(*values):
    return [[F(values[i]) if i == j else F(0) for j in range(len(values))] for i in range(len(values))]


def matmul(A, B):
    return [[sum((F(A[i][m]) * B[m][j] for m in range(len(B))), F(0)) for j in range(len(B[0]))]
            for i in range(len(A))]


def minus(A, B):
    return [[F(a) - b for a, b in zip(ra, rb)] for ra, rb in zip(A, B)]


def combine(*terms):
    """The sum of coefficient * matrix over (coefficient, matrix) pairs."""
    n = len(terms[0][1])
    return [[sum((F(c) * M[i][j] for c, M in terms), F(0)) for j in range(n)] for i in range(n)]


def rank_one(v):
    """v v^T / (v . v): the orthogonal projector onto the line through a non-zero rational vector v."""
    norm = sum(F(x) * x for x in v)
    return [[F(a) * b / norm for b in v] for a in v]


def span_projector(vectors, n):
    """The orthogonal projector onto the span of `vectors`: Gram-Schmidt without normalising stays rational."""
    basis = []
    for w in vectors:
        u = [F(x) for x in w]
        for b in basis:
            c = sum(x * y for x, y in zip(u, b)) / sum(y * y for y in b)
            u = [x - c * y for x, y in zip(u, b)]
        if any(u):
            basis.append(u)
    P = [[F(0)] * n for _ in range(n)]
    for b in basis:
        P = [[p + q for p, q in zip(rp, rq)] for rp, rq in zip(P, rank_one(b))]
    return P


def reference_is_projector(P):
    P = [[F(x) for x in row] for row in P]
    n = len(P)
    return all(P[i][j] == P[j][i] for i in range(n) for j in range(n)) and matmul(P, P) == P


def reference_probability(state, answers):
    """T = M_k ... M_1 as one matrix, then applied once: another association order than the module's."""
    n = len(state)
    T = identity(n)
    for answer in answers:
        P = answer['projector']
        T = matmul(P if answer['yes'] else minus(identity(n), P), T)
    image = [sum((row[j] * state[j] for j in range(n)), F(0)) for row in T]
    return sum(x * x for x in image) / sum(F(x) * x for x in state)


def quadratic(X, v):
    """v^T X v / v^T v."""
    return sum(F(v[i]) * X[i][j] * v[j] for i in range(len(v)) for j in range(len(v))) / sum(F(x) * x for x in v)


def random_projector(rng, n, low=0):
    rank = rng.randint(low, n)
    return span_projector([[rng.randint(-3, 3) for _ in range(n)] for _ in range(rank)], n)


def random_state(rng, n):
    while True:
        state = [F(rng.randint(-4, 4), rng.randint(1, 3)) for _ in range(n)]
        if any(state):
            return state


def ask(P, yes):
    return {'projector': P, 'yes': yes}


def joint(state, A, B, first):
    """{(answer to A, answer to B): probability} when `first` ('A' or 'B') is asked first. Labels follow the
    question, not the position: with B first, (True, False) is the sequence B no, then A yes."""
    table = {}
    for a, b in product((True, False), repeat=2):
        sequence = [ask(A, a), ask(B, b)] if first == 'A' else [ask(B, b), ask(A, a)]
        table[a, b] = call('ordered_probability', state, sequence)
    return table


def a_yes(table):
    return table[True, True] + table[True, False]


def b_yes(table):
    return table[True, True] + table[False, True]


def differ(table):
    return table[True, False] + table[False, True]


def probe_states(n):
    """e_i and e_i + e_j: for a non-zero symmetric X one of them has v^T X v != 0."""
    units = [[int(i == m) for m in range(n)] for i in range(n)]
    return units + [[a + b for a, b in zip(units[i], units[j])] for i in range(n) for j in range(i + 1, n)]


def states_for(n):
    return probe_states(n) + [[F((m + 2) * (-1) ** m, 3) for m in range(n)], [3] + [F(-1, 2)] * (n - 1)]


E1 = [[1, 0], [0, 0]]
HALF = rank_one([1, 1])                                   # [[1/2, 1/2], [1/2, 1/2]]
U1, U2, U3 = [1, 2, 2], [2, 1, -2], [2, -2, 1]           # pairwise orthogonal
NONCOMMUTING = (
    ('a coordinate line and the diagonal', E1, HALF),
    ('two lines in the plane', rank_one([3, 4]), rank_one([1, 2])),
    ('a line and a plane in space', rank_one(U1), span_projector([[1, 0, 0], [0, 1, 2]], 3)),
    ('two planes in space', span_projector([[1, 1, 0], [0, 1, 1]], 3), span_projector([[1, 0, 1], [1, -1, 2]], 3)),
    ('two planes in four dimensions', span_projector([[1, 0, 1, 0], [0, 1, 0, 1]], 4),
     span_projector([[1, 2, 0, 1], [0, 1, 1, -1]], 4)),
)
COMMUTING = (
    ('diagonal', diag(1, 0, 1), diag(1, 1, 0)),
    ('perpendicular lines', rank_one(U1), rank_one(U2)),
    ('a line inside a plane', rank_one(U1), span_projector([U1, U2], 3)),
    ('one eigenbasis, not diagonal', span_projector([U1, U2], 3), span_projector([U2, U3], 3)),
    ('a projector and its complement', rank_one([3, 4]), minus(identity(2), rank_one([3, 4]))),
    ('a projector and itself', rank_one(U1), rank_one(U1)),
)


class HandChecked(unittest.TestCase):
    def test_projectors_and_non_projectors(self):
        for P in (identity(1), [[0]], identity(3), [[0, 0], [0, 0]], E1, HALF,
                  [[F(9, 25), F(12, 25)], [F(12, 25), F(16, 25)]],
                  [[F(1, 9), F(2, 9), F(2, 9)], [F(2, 9), F(4, 9), F(4, 9)], [F(2, 9), F(4, 9), F(4, 9)]]):
            with self.subTest(P=P):
                self.assertIs(call('is_projector', P), True)
        for P in ([[1, 1], [0, 0]],                      # P*P = P but not symmetric: an oblique projector
                  [[2]], [[F(1, 2)]], [[-1]],
                  [[1, 0], [0, -1]], [[0, 1], [1, 0]],   # symmetric, P*P = I
                  [[F(1, 2), F(1, 2)], [F(1, 2), F(1, 3)]]):
            with self.subTest(P=P):
                self.assertIs(call('is_projector', P), False)

    def test_commutators(self):
        self.assertEqual(call('commutator', [[0, 1], [0, 0]], [[0, 0], [1, 0]]), ((1, 0), (0, -1)))
        self.assertEqual(call('commutator', E1, HALF), ((0, F(1, 2)), (F(-1, 2), 0)))
        self.assertEqual(call('commutator', HALF, E1), ((0, F(-1, 2)), (F(1, 2), 0)))
        self.assertEqual(call('commutator', diag(1, 2, 3), diag(4, 5, 6)), ((0, 0, 0),) * 3)
        self.assertIs(call('commutes', E1, HALF), False)
        self.assertIs(call('commutes', diag(1, 2, 3), diag(F(1, 2), 0, -7)), True)
        self.assertIs(call('commutes', [[1, 2], [3, 4]], [[1, 2], [3, 4]]), True)

    def test_one_question_is_s_p_s_over_s_s(self):
        P = rank_one([3, 4])
        self.assertEqual(call('ordered_probability', [1, 0], [ask(P, True)]), F(9, 25))
        self.assertEqual(call('ordered_probability', [1, 0], [ask(P, False)]), F(16, 25))
        self.assertEqual(call('ordered_probability', [7, 0], [ask(P, True)]), F(9, 25))   # need not be normalised
        self.assertEqual(call('ordered_probability', [F(-3, 7), F(-4, 7)], [ask(P, True)]), 1)
        self.assertEqual(call('ordered_probability', [4, -3], [ask(P, True)]), 0)

    def test_two_questions_every_joint_probability(self):
        state = [2, 1]
        ab, ba = joint(state, E1, HALF, 'A'), joint(state, E1, HALF, 'B')
        self.assertEqual(ab, {(True, True): F(2, 5), (True, False): F(2, 5),
                              (False, True): F(1, 10), (False, False): F(1, 10)})
        self.assertEqual(ba, {(True, True): F(9, 20), (True, False): F(1, 20),
                              (False, True): F(9, 20), (False, False): F(1, 20)})
        self.assertEqual((a_yes(ab), a_yes(ba)), (F(4, 5), F(1, 2)))       # the order changes P(yes to A)
        self.assertEqual((b_yes(ab), b_yes(ba)), (F(1, 2), F(9, 10)))      # and P(yes to B)
        self.assertEqual((differ(ab), differ(ba)), (F(1, 2), F(1, 2)))     # but not P(the answers differ)


class OrderEffectsAndQQ(unittest.TestCase):
    def test_order_can_change_p_yes_to_a_by_the_predicted_amount(self):
        for name, A, B in NONCOMMUTING:
            n = len(A)
            AB, BA = matmul(A, B), matmul(B, A)
            effect = combine((1, AB), (1, BA), (-2, matmul(BA, B)))
            with self.subTest(pair=name):
                self.assertIs(call('commutes', A, B), False)
                changes = []
                for state in states_for(n):
                    change = a_yes(joint(state, A, B, 'A')) - a_yes(joint(state, A, B, 'B'))
                    self.assertEqual(change, quadratic(effect, state))
                    changes.append(change)
                self.assertTrue(any(changes[:len(probe_states(n))]))     # some e_i or e_i + e_j shows it

    def test_qq_equality_on_noncommuting_pairs(self):
        for name, A, B in NONCOMMUTING:
            n = len(A)
            agree = combine((1, identity(n)), (-1, A), (-1, B), (1, matmul(A, B)), (1, matmul(B, A)))
            effects = 0
            for state in states_for(n):
                with self.subTest(pair=name, state=state):
                    ab, ba = joint(state, A, B, 'A'), joint(state, A, B, 'B')
                    self.assertEqual(differ(ab), differ(ba))
                    self.assertEqual(1 - differ(ab), quadratic(agree, state))
                    effects += a_yes(ab) != a_yes(ba) or b_yes(ab) != b_yes(ba)
            with self.subTest(pair=name):
                self.assertGreater(effects, 0)        # the equality holds where the order does matter

    def test_commuting_pairs_give_every_joint_probability_in_both_orders(self):
        for name, A, B in COMMUTING:
            with self.subTest(pair=name):
                self.assertIs(call('commutes', A, B), True)
                self.assertEqual(call('commutator', A, B), tuple((0,) * len(A) for _ in A))
                for state in states_for(len(A)):
                    self.assertEqual(joint(state, A, B, 'A'), joint(state, A, B, 'B'))

    def test_the_four_joint_probabilities_of_one_order_sum_to_one(self):
        for name, A, B in NONCOMMUTING + COMMUTING:
            for state in states_for(len(A)):
                for first in 'AB':
                    with self.subTest(pair=name, state=state, first=first):
                        table = joint(state, A, B, first)
                        self.assertEqual(sum(table.values()), 1)
                        self.assertTrue(all(0 <= p <= 1 for p in table.values()))

    def test_unequal_conditionals_without_any_order_effect(self):
        A, B, state = diag(1, 1, 0), diag(1, 0, 0), [1, 1, 1]
        ab, ba = joint(state, A, B, 'A'), joint(state, A, B, 'B')
        self.assertEqual(ab, ba)
        both = ab[True, True]
        self.assertEqual((both / a_yes(ab), both / b_yes(ab)), (F(1, 2), 1))     # P(B|A) != P(A|B)


class GeneratedInstances(unittest.TestCase):
    def test_forty_seeded_instances_against_the_independent_computation(self):
        rng = random.Random(20261003)
        seen = {True: 0, False: 0}
        for trial in range(40):
            n = rng.randint(1, 4)
            A, B, C = (random_projector(rng, n) for _ in range(3))
            state = random_state(rng, n)
            sequence = [ask(rng.choice((A, B, C)), rng.choice((True, False))) for _ in range(rng.randint(1, 5))]
            with self.subTest(trial=trial, n=n):
                for P in (A, B, C):
                    self.assertIs(call('is_projector', P), True)
                expected = minus(matmul(A, B), matmul(B, A))
                self.assertEqual(call('commutator', A, B), tuple(map(tuple, expected)))
                commuting = not any(map(any, expected))
                self.assertIs(call('commutes', A, B), commuting)
                seen[commuting] += 1
                p = call('ordered_probability', state, sequence)
                self.assertEqual(p, reference_probability(state, sequence))
                self.assertTrue(0 <= p <= 1)
                self.assertEqual(call('ordered_probability', [F(-5, 3) * x for x in state], sequence), p)
                ab, ba = joint(state, A, B, 'A'), joint(state, A, B, 'B')
                self.assertEqual((sum(ab.values()), sum(ba.values())), (1, 1))
                self.assertEqual(differ(ab), differ(ba))
                if commuting:
                    self.assertEqual(ab, ba)
                bumped = [list(row) for row in A]
                i, j = rng.randrange(n), rng.randrange(n)
                bumped[i][j] += F(rng.choice((-1, 1)), rng.randint(1, 4))
                self.assertIs(call('is_projector', bumped), reference_is_projector(bumped))
        self.assertGreater(seen[True], 0)
        self.assertGreater(seen[False], 0)

    def test_largest_admitted_call_against_the_independent_computation(self):
        rng = random.Random(3)
        projectors = [random_projector(rng, O.MAX_DIMENSION, low=2) for _ in range(3)]
        state = random_state(rng, O.MAX_DIMENSION)
        answers = [ask(projectors[m % 3], m % 4 != 3) for m in range(O.MAX_ANSWERS)]
        p = call('ordered_probability', state, answers)
        self.assertEqual(p, reference_probability(state, answers))
        self.assertTrue(0 < p < 1)


class Refusals(unittest.TestCase):
    def refused(self, kind, name, *args, **kwargs):
        with self.assertRaises(O.OperatorError) as caught:
            call(name, *args, **kwargs)
        self.assertIsInstance(caught.exception, S.SymblicError)
        self.assertEqual(caught.exception.kind, kind, caught.exception.message)
        return caught.exception

    def test_matrices_are_square_of_dimension_one_to_eight(self):
        for bad in ([], (), [[]], [[1, 0]], [[1], [0]], [[1, 0], [0]], [1, 0], [[1, 0], [0, 1], [0, 0]],
                    'P', None, 1, {'rows': [[1]]}, S.ValueSet([1]), [S.ValueSet([1])], identity(9)):
            with self.subTest(bad=bad):
                self.refused('type', 'is_projector', bad)
                self.refused('type', 'commutator', bad, identity(2))
                self.refused('type', 'commutes', identity(2), bad)
                self.refused('type', 'ordered_probability', [1, 0], [ask(bad, True)])

    def test_dimensions_agree(self):
        self.refused('type', 'commutator', identity(2), identity(3))
        self.refused('type', 'commutes', identity(3), identity(2))
        self.refused('type', 'ordered_probability', [1, 0], [ask(identity(3), True)])
        self.refused('type', 'ordered_probability', [1, 0, 0], [ask(identity(3), True), ask(identity(2), False)])
        self.refused('type', 'ordered_probability', [1] * 9, [ask(identity(9), True)])

    def test_answers_are_one_to_eight_records_with_exactly_projector_and_yes(self):
        good = ask(E1, True)
        self.assertEqual(call('ordered_probability', [1, 0], [good] * O.MAX_ANSWERS), 1)
        for bad in ([], (), [good] * (O.MAX_ANSWERS + 1), {'first': good}, good, 'yes', None):
            with self.subTest(answers=bad):
                self.refused('type', 'ordered_probability', [1, 0], bad)
        for bad in ((E1, True), [E1, True], {'projector': E1}, {'yes': True},
                    {'projector': E1, 'yes': True, 'question': 'A'}, {'projector': E1, 'yes': 1},
                    {'projector': E1, 'yes': 'yes'}, {'projector': E1, 'yes': None}, {0: E1, 'yes': True}):
            with self.subTest(answer=bad):
                self.refused('type', 'ordered_probability', [1, 0], [good, bad])

    def test_answer_matrices_must_be_orthogonal_projectors(self):
        for matrix, reason in (([[1, 1], [0, 0]], 'not symmetric'),
                               ([[1, 0], [0, F(1, 2)]], 'P*P = P'),
                               ([[0, 1], [1, 0]], 'P*P = P'),
                               ([[2, 0], [0, 0]], 'P*P = P')):
            with self.subTest(matrix=matrix):
                error = self.refused('check', 'ordered_probability', [1, 2], [ask(E1, True), ask(matrix, False)])
                self.assertIn('answer 2', error.message)
                self.assertIn(reason, error.message)
                self.assertIs(call('is_projector', matrix), False)

    def test_zero_state(self):
        for state in ([0], [0, 0], (F(0), 0, F(0, 5))):
            with self.subTest(state=state):
                self.refused('check', 'ordered_probability', state, [ask(identity(len(state)), True)])

    def test_only_exact_numbers(self):
        class IntSubclass(int):
            pass
        for bad in (True, False, 1.0, 0.5, float('nan'), float('inf'), float('-inf'), Decimal(1), 1j, '1', None,
                    IntSubclass(1), [1]):
            with self.subTest(bad=repr(bad)):
                self.refused('type', 'is_projector', [[bad]])
                self.refused('type', 'is_projector', [[1, 0], [0, bad]])
                self.refused('type', 'commutator', [[bad]], [[1]])
                self.refused('type', 'commutes', [[1]], [[bad]])
                self.refused('type', 'ordered_probability', [bad, 1], [ask(E1, True)])
                self.refused('type', 'ordered_probability', [1, 1], [ask([[1, 0], [0, bad]], True)])

    def test_forged_fractions(self):
        for numerator, denominator in ((2, 4), (1, 0), (1, -2), (True, 2), ('1', 2)):
            forged = object.__new__(F)
            forged._numerator, forged._denominator = numerator, denominator
            with self.subTest(pair=(numerator, denominator)):
                self.refused('type', 'is_projector', [[forged]])
                self.refused('type', 'ordered_probability', [forged], [ask([[1]], True)])

    def test_huge_integers(self):
        huge = 1 << 5000
        for name, args in (('is_projector', ([[huge]],)), ('is_projector', ([[F(1, huge)]],)),
                           ('commutator', ([[huge]], [[1]])), ('commutes', ([[1]], [[F(-1, huge)]])),
                           ('ordered_probability', ([huge, 1], [ask(E1, True)])),
                           ('ordered_probability', ([1, 1], [ask([[1, 0], [0, huge]], True)]))):
            with self.subTest(name=name, args=len(args)):
                self.refused('budget', name, *args)
        # Inputs inside the limit whose products would not be: refused before the product is built.
        big = 1 << 3000
        self.refused('budget', 'is_projector', [[big]])
        self.refused('budget', 'commutator', [[big, 0], [0, 0]], [[big, 1], [0, 0]])
        self.refused('budget', 'ordered_probability', [big, 1], [ask(E1, True)])

    def test_bit_limit_boundary(self):
        edge = (1 << O.MAX_BITS) - 1
        self.assertEqual(call('commutator', [[edge]], [[0]]), ((0,),))
        self.assertEqual(call('commutator', [[F(1, edge)]], [[0]]), ((0,),))
        for bad in (1 << O.MAX_BITS, F(1, 1 << O.MAX_BITS)):
            with self.subTest(bits=O.MAX_BITS + 1):
                self.refused('budget', 'commutator', [[bad]], [[0]])

    def test_builtin_arguments_are_fixed_and_positional(self):
        kernel = make_kernel()
        for name, args in (('is_projector', ()), ('is_projector', (E1, E1)), ('commutator', (E1,)),
                           ('commutes', (E1, E1, E1)), ('ordered_probability', ([1, 0],))):
            with self.subTest(name=name, args=len(args)), self.assertRaises(O.OperatorError) as caught:
                O.FUNCTIONS[name](kernel, None, *args)
            self.assertEqual(caught.exception.kind, 'type')
        self.refused('type', 'is_projector', E1, strict=True)
        self.refused('type', 'ordered_probability', [1, 0], [ask(E1, True)], budget=S.Budget(STEPS))
        self.assertEqual(kernel.budget.left, STEPS)


class BudgetAndLimits(unittest.TestCase):
    def test_charge_is_the_documented_formula_whatever_the_values(self):
        for n in range(1, O.MAX_DIMENSION + 1):
            I = identity(n)
            with self.subTest(n=n):
                self.assertEqual(charge('is_projector', I), n * n * (n + 2))
                self.assertEqual(charge('commutator', I, I), 2 * n * n + 4 * n ** 3)
                self.assertEqual(charge('commutes', I, I), 2 * n * n + 4 * n ** 3)
                for k in (1, 3, O.MAX_ANSWERS):
                    self.assertEqual(charge('ordered_probability', [1] * n, [ask(I, k % 2 == 0)] * k),
                                     5 * n + 1 + k * (n ** 3 + 4 * n * n + n))
        # Early exits and the answers given do not change the charge.
        self.assertEqual(charge('is_projector', [[1, 1], [0, 0]]), charge('is_projector', identity(2)))
        self.assertEqual(charge('commutes', E1, HALF), charge('commutes', E1, E1))
        self.assertEqual(charge('ordered_probability', [2, 1], [ask(E1, True)]),
                         charge('ordered_probability', [2, 1], [ask(HALF, False)]))
        largest = O._probability_cost(O.MAX_DIMENSION, O.MAX_ANSWERS)
        self.assertEqual(largest, 6249)
        self.assertLessEqual(max(largest, O._commutator_cost(O.MAX_DIMENSION),
                                 O._projector_cost(O.MAX_DIMENSION)), O.MAX_WORK)

    def test_charge_is_taken_before_any_entry_is_read(self):
        cost = 5 * 3 + 1 + 2 * (3 ** 3 + 4 * 3 * 3 + 3)
        with patch.object(O._Work, 'scalar', side_effect=AssertionError('an entry was read')):
            for steps in (0, cost - 1):
                with self.subTest(steps=steps), self.assertRaises(S.SymblicError) as caught:
                    O.FUNCTIONS['ordered_probability'](make_kernel(steps), None, [1, 2, 3],
                                                       [ask(identity(3), True)] * 2)
                self.assertNotIsInstance(caught.exception, O.OperatorError)
                self.assertIn('step budget', caught.exception.message)

    def test_the_exact_budget_suffices_and_exhaustion_carries_the_call_position(self):
        kernel = make_kernel(16)                                 # is_projector, n = 2: 2*2*(2+2)
        self.assertIs(O.FUNCTIONS['is_projector'](kernel, None, HALF), True)
        self.assertEqual(kernel.budget.left, 0)
        node = S.Node('call', 7, 3, fn='is_projector', args=[], kwargs={})
        with self.assertRaises(S.SymblicError) as caught:
            O.FUNCTIONS['is_projector'](make_kernel(15), node, HALF)
        self.assertNotIsInstance(caught.exception, O.OperatorError)
        self.assertEqual((caught.exception.line, caught.exception.col), (7, 3))

    def test_counted_work_never_exceeds_the_charge(self):
        made = []

        class Recording(O._Work):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                made.append(self)
        n, k = O.MAX_DIMENSION, O.MAX_ANSWERS
        with patch.object(O, '_Work', Recording):
            call('ordered_probability', [1] * n, [ask(identity(n), False)] * k)    # every answer no: full charge
            call('ordered_probability', [1] * n, [ask(identity(n), True)] * k)     # every answer yes: n fewer each
            call('is_projector', identity(n))
            call('commutator', identity(n), identity(n))
            call('commutes', E1, HALF)                                             # stops at a non-zero entry
        every_no, every_yes, projector, pair, early = made
        self.assertEqual(every_no.used, every_no.charged)
        self.assertEqual(every_yes.used, every_yes.charged - k * n)
        self.assertEqual(projector.used, projector.charged)
        self.assertEqual(pair.used, pair.charged)
        self.assertLess(early.used, early.charged)

    def test_work_ceiling_refuses_before_charging_the_kernel(self):
        kernel = make_kernel()
        with patch.object(O, 'MAX_WORK', 100):
            with self.assertRaises(O.OperatorError) as caught:
                O.FUNCTIONS['commutator'](kernel, None, identity(4), identity(4))       # 2*16 + 4*64 = 288
        self.assertEqual(caught.exception.kind, 'budget')
        self.assertEqual(kernel.budget.left, STEPS)

    def test_a_wrong_cost_formula_cannot_run_uncharged_work(self):
        with patch.object(O, '_projector_cost', lambda n: n * n):
            with self.assertRaises(O.OperatorError) as caught:
                call('is_projector', identity(2))
        self.assertEqual(caught.exception.kind, 'runtime')

    def test_python_callers_may_omit_the_budget_but_not_pass_another_kind(self):
        self.assertIs(O.is_projector(HALF), True)
        self.assertEqual(O.ordered_probability([2, 1], [ask(E1, True)]), F(4, 5))
        with self.assertRaises(O.OperatorError) as caught:
            O.is_projector(HALF, budget=100)
        self.assertEqual(caught.exception.kind, 'type')


class CanonicalForm(unittest.TestCase):
    def test_results_are_kernel_values_accepted_by_canon_and_fingerprint(self):
        values = {'projector': call('is_projector', HALF), 'oblique': call('is_projector', [[1, 1], [0, 0]]),
                  'commutes': call('commutes', E1, HALF), 'commutator': call('commutator', E1, HALF),
                  'zero commutator': call('commutator', identity(3), identity(3)),
                  'fraction': call('ordered_probability', [2, 1], [ask(E1, True)]),
                  'one': call('ordered_probability', [1, 0], [ask(E1, True)]),
                  'zero': call('ordered_probability', [0, 1], [ask(E1, True)])}
        for name, value in values.items():
            with self.subTest(value=name):
                self.assertEqual(len(S.fingerprint(value)), 16)
                self.assertEqual(S.canon_json(value), S.canon_json(copy.deepcopy(value)))
        self.assertIs(values['projector'], True)
        self.assertIs(values['oblique'], False)
        self.assertIs(values['commutes'], False)
        self.assertEqual(S.canon(values['commutator']), [[0, {'#q': '1/2'}], [{'#q': '-1/2'}, 0]])
        for matrix in (values['commutator'], values['zero commutator']):
            self.assertIs(type(matrix), tuple)
            for row in matrix:
                self.assertIs(type(row), tuple)
                for entry in row:
                    self.assertIn(type(entry), (int, F))
                    self.assertTrue(type(entry) is int or entry.denominator != 1)
        self.assertIs(type(values['fraction']), F)
        self.assertEqual(values['fraction'], F(4, 5))
        self.assertIs(type(values['one']), int)
        self.assertIs(type(values['zero']), int)

    def test_lists_and_tuples_give_the_same_canonical_result(self):
        frozen = lambda M: tuple(map(tuple, M))          # noqa: E731
        self.assertEqual(
            S.canon_json(call('ordered_probability', [2, 1], [ask(E1, True), ask(HALF, False)])),
            S.canon_json(call('ordered_probability', (2, 1), (ask(frozen(E1), True), ask(frozen(HALF), False)))))
        self.assertEqual(S.fingerprint(call('commutator', E1, HALF)),
                         S.fingerprint(call('commutator', frozen(E1), frozen(HALF))))

    def test_inputs_are_not_mutated(self):
        state, answers = [2, 1], [ask(copy.deepcopy(E1), True), ask(copy.deepcopy(HALF), False)]
        before = copy.deepcopy((state, answers))
        call('ordered_probability', state, answers)
        call('commutator', answers[0]['projector'], answers[1]['projector'])
        call('is_projector', answers[1]['projector'])
        self.assertEqual((state, answers), before)


PROGRAM = '''let A = [[1, 0], [0, 0]].
let B = [[1/2, 1/2], [1/2, 1/2]].
let state = [2, 1].
assert is_projector(A) and is_projector(B) and not is_projector([[1, 1], [0, 0]]).
assert not commutes(A, B) and commutes(A, A).
assert commutator(A, B) = [[0, 1/2], [-1/2, 0]].
let a_first = ordered_probability(state, [{projector: A, yes: true}]).
let a_yes = {projector: A, yes: true}.
let a_no = {projector: A, yes: false}.
let b_yes = {projector: B, yes: true}.
let b_no = {projector: B, yes: false}.
let a_second = ordered_probability(state, [b_yes, a_yes]) + ordered_probability(state, [b_no, a_yes]).
let differ_ab = ordered_probability(state, [a_yes, b_no]) + ordered_probability(state, [a_no, b_yes]).
let differ_ba = ordered_probability(state, [b_no, a_yes]) + ordered_probability(state, [b_yes, a_no]).
assert a_first = 4/5.
assert a_second = 1/2.
assert differ_ab = differ_ba.
show [a_first, a_second, differ_ab].
'''


class KernelIntegration(unittest.TestCase):
    def test_the_builtins_are_this_modules_functions(self):
        self.assertEqual(tuple(O.FUNCTIONS), NAMES)
        for name in NAMES:
            self.assertEqual(S.BUILTINS[name]._symblic_adapter, ('symblic.adapters.operators', name))
        kernel = make_kernel()
        self.assertIs(S.BUILTINS['is_projector'](kernel, None, HALF), True)
        self.assertEqual(S.BUILTINS['ordered_probability'](kernel, None, [2, 1], [ask(E1, True)]), F(4, 5))
        self.assertEqual(STEPS - kernel.budget.left, 16 + (5 * 2 + 1 + (8 + 16 + 2)))

    def test_program_runs_through_the_kernel_without_models(self):
        self.assertTrue(S.check(PROGRAM)['ok'])
        run = SR.Run(PROGRAM, None, None, {'by': 'kernel'})
        report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual((report['asks'], report['calls']), (0, 0))
        self.assertEqual(run.kernel.env.lookup('a_first').value, F(4, 5))
        self.assertEqual(run.kernel.env.lookup('differ_ba').value, F(1, 2))
        self.assertEqual([o['text'] for o in report['outputs']], ['[0.8, 0.5, 0.5]'])

    def test_program_refusals_carry_kind_and_line(self):
        for source, kind, line in (
                ('let s = [1, 0].\nlet p = ordered_probability(s, [{projector: [[1, 1], [0, 0]], yes: true}]).\n',
                 'check', 2),
                ('let p = ordered_probability([0, 0], [{projector: [[1, 0], [0, 0]], yes: true}]).\n', 'check', 1),
                ('let x = 1.\nlet c = commutator([[1, 0]], [[1]]).\n', 'type', 2),
                ('let p = is_projector([[1/2, 1/2], [1/2, true]]).\n', 'type', 1),
                ('let p = ordered_probability([1], [{projector: [[1]], yes: 1}]).\n', 'type', 1),
                ('let p = ordered_probability([1], {projector: [[1]], yes: true}).\n', 'type', 1),
                ('let p = is_projector([[1]], strict=true).\n', 'type', 1),
                ('let p = is_projector([[2^3000]]).\n', 'budget', 1)):
            with self.subTest(source=source):
                report = SR.Run(source, None, None, {'by': 'kernel'}).execute()
                self.assertEqual(report['status'], 'failed')
                self.assertEqual((report['error']['kind'], report['error']['line']), (kind, line))
                self.assertEqual(report['calls'], 0)

    def test_document_example_runs_as_documented(self):
        with open(DOC, encoding='utf-8') as stream:
            text = stream.read()
        source = re.search(r'```symblic\n(.*?)```', text, re.S).group(1)
        expected = re.search(r'```text\n(.*?)```', text, re.S).group(1).strip().splitlines()
        self.assertTrue(S.check(source)['ok'])
        report = SR.Run(source, None, None, {'by': 'kernel'}).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual((report['asks'], report['calls']), (0, 0))
        shown = [f'{o["kind"]} {o["label"]} (line {o["line"]}): {o["text"]}' for o in report['outputs']]
        self.assertEqual(shown, expected)

    def test_kernel_identity_pins_the_adapter_version(self):
        original = S.kernel_id()
        self.assertEqual((original['operators'], O.VERSION), (1, 1))
        with patch.object(O, 'VERSION', O.VERSION + 1):
            changed = S.kernel_id()
        self.assertNotEqual(original['id'], changed['id'])
        self.assertEqual(original, S.kernel_id())

    def test_a_missing_module_refuses_as_unavailable(self):
        original = S.kernel_id()
        with patch.dict('sys.modules', {'symblic.adapters.operators': None}):
            changed = S.kernel_id()
            report = SR.Run('let c = commutes([[1]], [[1]]).', None, None, {'by': 'kernel'}).execute()
        self.assertIsNone(changed['operators'])
        self.assertNotEqual(original['id'], changed['id'])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'unavailable')

    def test_import_is_inert(self):
        before = dict(S.BUILTINS)
        spec = importlib.util.spec_from_file_location('_operators_inert_probe', O.__file__)
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)
        self.assertEqual(S.BUILTINS, before)
        self.assertEqual(tuple(isolated.FUNCTIONS), NAMES)


if __name__ == '__main__':
    unittest.main()
