"""Exact knowledge on finite state spaces (symblic_knowledge): Aumann's partition model and the announcement process
of Geanakoplos and Polemarchakis. Kernel only: no model, no network, no stores, no services."""
import importlib.util
import random
import re
import unittest
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import run as SR
from symblic.adapters import knowledge as K

DOC = Path(__file__).resolve().parents[2] / 'docs' / 'reference' / 'KNOWLEDGE.md'
NAMES = ('knows_event', 'common_partition', 'common_knowledge', 'posterior_given', 'agreement_process')


class _Node:
    line = 0
    col = 0


def call(name, *args, steps=200_000):
    """A builtin through FUNCTIONS with a real kernel, as the kernel calls it."""
    return K.FUNCTIONS[name](S.Kernel(S.Env(), S.KB(), S.Budget(steps)), _Node, *args)


def used(name, *args):
    """How many kernel steps one call charges."""
    budget = S.Budget(200_000)
    K.FUNCTIONS[name](S.Kernel(S.Env(), S.KB(), budget), _Node, *args)
    return 200_000 - budget.left


# The nine-state example of Geanakoplos and Polemarchakis (1982): states 1..9, a uniform common prior, the event
# A = {3, 4}. Agent 1 sees {1,2,3} {4,5,6} {7,8,9}; agent 2 sees {1,2,3,4} {5,6,7,8} {9}.
NINE_1 = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
NINE_2 = [[1, 2, 3, 4], [5, 6, 7, 8], [9]]
NINE_A = [3, 4]
UNIFORM_9 = [1] * 9

# Two processes longer than 64 announcements. In both: states 1..64, a uniform common prior, A = the odd states.
# A pair cell holds one odd and one even state (posterior 1/2); a cell cut down to one state gives 0 or 1.
ODD = [w for w in range(1, 65) if w % 2]
PAIRS = [[2 * j - 1, 2 * j] for j in range(1, 33)]                      # {1,2} {3,4} ... {63,64}
SHIFTED = [[1]] + [[2 * j, 2 * j + 1] for j in range(1, 32)] + [[64]]   # {1} {2,3} ... {62,63} {64}

# The fixture of the independent pre-freeze review: agents 1-4 see PAIRS, agents 5-8 see SHIFTED, true state 32.
# Agents 1-4 remove nothing at first. Removal k happens at announcement 4k + 1, by agent 5 when k is odd and by
# agent 1 when k is even: removal 1 takes agent 5's one-state cells {1} and {64}; each later removal takes the two
# cells that the previous removal cut, one at each end. After removal k, W = {k + 1, ..., 64 - k}; the three agents
# after each remover share its partition and remove nothing. Removal 32 (announcement 129, agent 1) finds
# W = {32, 33}: its cells {32} (posterior 0) and {33} (posterior 1), so W = {32} and it says 0. Eight quiet
# announcements follow: the process converges at announcement 137 with every posterior 0. At announcement 64
# (W = {16, ..., 49}) every current posterior is 1/2: equal, but not converged.
REVIEW = [PAIRS] * 4 + [SHIFTED] * 4

# A second long process, true state 1. Agents 1 and 2 share the cell {1, 2} (posterior 1/2) and on 3..64 form a
# chain: agent 1 sees {3,4} ... {63,64}, agent 2 sees {3} {4,5} ... {62,63} {64}. Agents 3..8 see nothing (one
# cell). Agent 1 removes nothing first; agent 2 removes 3 and 64; then agent 1 and agent 2 each remove the cut cell
# at both ends of what is left of the chain, and agents 3..8 remove nothing. So every 8 announcements remove 4
# states: the 60 states 4..63 are gone after announcement 122 and it converges at announcement 130, all at 1/2.
CHAIN_1 = PAIRS
CHAIN_2 = [[1, 2], [3]] + [[2 * j, 2 * j + 1] for j in range(2, 32)] + [[64]]
CHAIN = [CHAIN_1, CHAIN_2] + [[list(range(1, 65))]] * 6


# ---------------------------------------------------------------------------------------------------------------
# Independent brute-force references (they share no code with the module)
# ---------------------------------------------------------------------------------------------------------------

def random_partition(rng, n):
    labels = [rng.randrange(rng.randint(1, n)) for _ in range(n)]
    groups = {}
    for state, label in enumerate(labels, 1):
        groups.setdefault(label, []).append(state)
    cells = [rng.sample(cell, len(cell)) for cell in groups.values()]
    rng.shuffle(cells)
    return cells


def set_partitions(items):
    """Every partition of a list of items (Bell-number many)."""
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for smaller in set_partitions(rest):
        for k in range(len(smaller)):
            yield smaller[:k] + [[first] + smaller[k]] + smaller[k + 1:]
        yield [[first]] + smaller


def refines(fine, coarse):
    return all(any(set(cell) <= set(big) for big in coarse) for cell in fine)


def knowledge(cells, target):
    """K_i(E): the states at which the agent's cell lies inside E."""
    return {w for cell in cells if set(cell) <= target for w in cell}


def iterated_common_knowledge(partitions, event):
    """E, everyone knows E, everyone knows that, ... until nothing changes (the hierarchy, not the meet)."""
    level = set(event)
    while True:
        deeper = set.intersection(*(knowledge(cells, level) for cells in partitions))
        if deeper == level:
            return level
        level = deeper


def refinement_process(weights, partitions, event, truth, rounds):
    """The announcement process as refinement of whole partitions: every announcement function is defined at
    EVERY state, and every agent's partition is joined with its level sets. Needs positive weights. Returns the
    full history, each agent's posterior given its final cell, whether m quiet announcements ended it, and W."""
    n = len(weights[0])
    m = len(partitions)
    states = range(1, n + 1)
    cell_of = [{w: frozenset(cell) for cell in cells for w in cell} for cells in partitions]
    public = set(states)
    history, quiet, converged = [], 0, False
    for turn in range(rounds):
        i = turn % m
        said = {w: F(sum(weights[i][v - 1] for v in cell_of[i][w] if v in event),
                     sum(weights[i][v - 1] for v in cell_of[i][w])) for w in states}
        history.append(said[truth])
        for j in range(m):
            cell_of[j] = {w: frozenset(v for v in cell_of[j][w] if said[v] == said[w]) for w in states}
        kept = {w for w in public if said[w] == said[truth]}
        if kept == public:
            quiet += 1
            if quiet == m:
                converged = True
                break
        else:
            quiet, public = 0, kept
    final = [F(sum(weights[i][v - 1] for v in cell_of[i][truth] if v in event),
               sum(weights[i][v - 1] for v in cell_of[i][truth])) for i in range(m)]
    return history, final, converged, public


# ---------------------------------------------------------------------------------------------------------------
# Hand-checked models
# ---------------------------------------------------------------------------------------------------------------

class PartitionKnowledge(unittest.TestCase):
    def test_known_by_both_but_not_common_knowledge(self):
        # States 1..4. Agent 1 sees {1,2} {3,4}; agent 2 sees {1} {2,3} {4}. E = {1,2,3}, true state 1.
        # Agent 1's cell {1,2} and agent 2's cell {1} lie inside E: both know E at 1. The meet links 1-2 (agent 1),
        # 2-3 (agent 2) and 3-4 (agent 1), so it is the single cell {1,2,3,4}, which is not inside E.
        # By hand: K1(E) = {1,2}, K2(E) = {1,2,3}; everyone knows E on {1,2}; K1({1,2}) = {1,2} and K2({1,2}) = {1},
        # so everyone knows that on {1} only; K1({1}) is empty, so the third level fails at every state.
        p1, p2, event = [[1, 2], [3, 4]], [[1], [2, 3], [4]], [1, 2, 3]
        self.assertIs(call('knows_event', p1, event, 1), True)
        self.assertIs(call('knows_event', p2, event, 1), True)
        self.assertEqual([call('knows_event', p1, event, w) for w in range(1, 5)], [True, True, False, False])
        self.assertEqual([call('knows_event', p2, event, w) for w in range(1, 5)], [True, True, True, False])
        self.assertEqual(call('common_partition', [p1, p2]), ((1, 2, 3, 4),))
        self.assertIs(call('common_knowledge', [p1, p2], event, 1), False)
        everyone = [1, 2]
        self.assertTrue(call('knows_event', p1, everyone, 1) and call('knows_event', p2, everyone, 1))
        self.assertIs(call('knows_event', p1, [1], 1), False)                 # the third level fails at 1

    def test_common_knowledge_when_the_meet_cell_lies_inside_the_event(self):
        # Agent 1 sees {1,2} {3,4}; agent 2 sees {1} {2} {3,4}: the meet is {1,2} {3,4}. E = {1,2,3}.
        # At 1 and 2 the meet cell {1,2} lies inside E: common knowledge. At 3 both agents' cell is {3,4}, which
        # is not inside E, so neither knows E there although 3 is in E.
        partitions, event = [[[1, 2], [3, 4]], [[1], [2], [3, 4]]], [1, 2, 3]
        self.assertEqual(call('common_partition', partitions), ((1, 2), (3, 4)))
        self.assertEqual([call('common_knowledge', partitions, event, w) for w in range(1, 5)],
                         [True, True, False, False])
        self.assertIs(call('knows_event', partitions[1], event, 2), True)
        self.assertIs(call('knows_event', partitions[0], event, 3), False)
        self.assertIs(call('knows_event', partitions[1], event, 3), False)

    def test_meet_of_two_partitions_by_hand(self):
        # {1,2} {3} {4,5} {6} and {1} {2,3} {4} {5,6}: 1-2 and 4-5 by the first, 2-3 and 5-6 by the second.
        first, second = [[1, 2], [3], [4, 5], [6]], [[1], [2, 3], [4], [5, 6]]
        self.assertEqual(call('common_partition', [first, second]), ((1, 2, 3), (4, 5, 6)))
        shuffled = [[[6], S.ValueSet([5, 4]), [3], [2, 1]], [[6, 5], [4], S.ValueSet([3, 2]), [1]]]
        self.assertEqual(call('common_partition', shuffled), ((1, 2, 3), (4, 5, 6)))

    def test_meet_cells_are_sorted_and_ordered_by_smallest_state(self):
        # {1,3} {2,4} {5} and {1} {2} {3} {4,5}: 1-3 by the first; 2-4 by the first and 4-5 by the second.
        self.assertEqual(call('common_partition', [[[1, 3], [2, 4], [5]], [[1], [2], [3], [4, 5]]]),
                         ((1, 3), (2, 4, 5)))

    def test_meet_of_three_partitions_and_the_trivial_cases(self):
        # {1,2} links 1-2, {2,3} links 2-3, {3,4} links 3-4; state 5 stays alone.
        three = [[[1, 2], [3], [4], [5]], [[1], [2], [3, 4], [5]], [[1], [2, 3], [4], [5]]]
        self.assertEqual(call('common_partition', three), ((1, 2, 3, 4), (5,)))
        p = [[1, 2], [3], [4, 5]]
        discrete, trivial = [[w] for w in range(1, 6)], [[1, 2, 3, 4, 5]]
        self.assertEqual(call('common_partition', [p]), ((1, 2), (3,), (4, 5)))
        self.assertEqual(call('common_partition', [p, discrete]), ((1, 2), (3,), (4, 5)))
        self.assertEqual(call('common_partition', [p, trivial]), ((1, 2, 3, 4, 5),))
        self.assertEqual(call('common_partition', [[[1]]]), ((1,),))

    def test_sets_and_lists_give_the_same_answers(self):
        p1, p2 = [S.ValueSet([2, 1]), S.ValueSet([4, 3])], [[1], [3, 2], [4]]
        for event in ([1, 2, 3], [3, 2, 1], S.ValueSet([1, 2, 3]), frozenset({1, 2, 3}), (1, 2, 3)):
            with self.subTest(event=event):
                self.assertIs(call('knows_event', p1, event, 2), True)
                self.assertIs(call('common_knowledge', [p1, p2], event, 1), False)

    def test_empty_event_and_whole_space(self):
        p = [[1, 2], [3]]
        self.assertIs(call('knows_event', p, [], 3), False)
        self.assertIs(call('knows_event', p, S.ValueSet(), 1), False)
        self.assertIs(call('common_knowledge', [p, [[1], [2, 3]]], [1, 2, 3], 2), True)
        self.assertIs(call('common_knowledge', [p, [[1], [2, 3]]], [], 2), False)


class Posteriors(unittest.TestCase):
    def test_exact_fractions_by_hand(self):
        # Prior [1, 2, 3, 4] normalises to 1/10, 2/10, 3/10, 4/10. Given {2,3,4}, the event {1,3} has 3/(2+3+4).
        self.assertEqual(call('posterior_given', [1, 2, 3, 4], [2, 3, 4], [3, 1]), F(1, 3))
        # Prior [1/2, 1/3, 1/6]: given {1,2}, P({2}) = (1/3) / (1/2 + 1/3) = 2/5.
        self.assertEqual(call('posterior_given', [F(1, 2), F(1, 3), F(1, 6)], [1, 2], [2]), F(2, 5))
        # The nine-state example: agent 2 at state 1, cell {1,2,3,4}, A = {3,4}: 2/4.
        self.assertEqual(call('posterior_given', UNIFORM_9, [1, 2, 3, 4], NINE_A), F(1, 2))
        self.assertEqual(call('posterior_given', UNIFORM_9, S.ValueSet([1, 2, 3]), S.ValueSet(NINE_A)), F(1, 3))

    def test_the_prior_is_normalised(self):
        for prior in ([1, 2, 3, 4], [10, 20, 30, 40], [F(1, 10), F(1, 5), F(3, 10), F(2, 5)],
                      [F(7, 3), F(14, 3), 7, F(28, 3)]):
            with self.subTest(prior=prior):
                self.assertEqual(call('posterior_given', prior, [2, 3, 4], [1, 3]), F(1, 3))

    def test_certain_and_impossible_are_kernel_integers(self):
        one = call('posterior_given', [1, 2, 3], [1, 2], [1, 2, 3])
        zero = call('posterior_given', [1, 2, 3], [1, 2], [3])
        self.assertEqual((one, zero), (1, 0))
        self.assertIs(type(one), int)
        self.assertIs(type(zero), int)

    def test_a_state_without_weight_inside_a_weighted_cell_is_allowed(self):
        self.assertEqual(call('posterior_given', [0, 1, 1], [1, 2], [1]), 0)
        self.assertEqual(call('posterior_given', [0, 1, 1], [1, 2, 3], [1, 3]), F(1, 2))

    def test_a_cell_of_zero_weight_is_refused(self):
        for prior, cell in (([0, 0, 1], [1, 2]), ([1, 2, 3], []), ([0, 0, 1], S.ValueSet())):
            with self.subTest(prior=prior, cell=cell), self.assertRaises(K.KnowledgeError) as caught:
                call('posterior_given', prior, cell, [1])
            self.assertEqual(caught.exception.kind, 'check')
            self.assertIn('zero prior weight', caught.exception.message)


class Agreement(unittest.TestCase):
    def test_nine_state_example_posteriors_change_before_they_agree(self):
        # True state 1.
        #  1. agent 1, cell {1,2,3}: P(A) = 1/3. Its cells give 1/3, 1/3, 0, so {7,8,9} leaves: S = {1..6}.
        #  2. agent 2, cell {1,2,3,4}: 2/4 = 1/2. Its current cells are {1,2,3,4} (1/2) and {5,6} (0): S = {1,2,3,4}.
        #  3. agent 1, cell {1,2,3}: 1/3. Its current cells are {1,2,3} (1/3) and {4} (1): S = {1,2,3}.
        #  4. agent 2, current cell {1,2,3}: 1/3. Nothing leaves.
        #  5. agent 1: 1/3. Nothing leaves: two consecutive announcements removed nothing, so it stops.
        # Agent 2 said 1/2 and then 1/3: the announced posteriors change before they agree.
        result = call('agreement_process', UNIFORM_9, [NINE_1, NINE_2], NINE_A, 1)
        self.assertEqual(result, {'posteriors': (F(1, 3), F(1, 3)), 'agreed': True, 'announcements': 5,
                                  'history': (F(1, 3), F(1, 2), F(1, 3), F(1, 3), F(1, 3)),
                                  'history_truncated': False, 'common_prior': True, 'converged': True})
        # Before anyone speaks the two posteriors differ, and A is not common knowledge at 1.
        self.assertNotEqual(call('posterior_given', UNIFORM_9, [1, 2, 3], NINE_A),
                            call('posterior_given', UNIFORM_9, [1, 2, 3, 4], NINE_A))
        self.assertEqual(call('common_partition', [NINE_1, NINE_2]), (tuple(range(1, 10)),))

    def test_nine_state_example_at_other_true_states(self):
        # True state 4: agent 1 says 1/3 (S = {1..6}); agent 2 says 1/2 (S = {1,2,3,4}); agent 1's cell is now
        # {4}, so it says 1 and {1,2,3} (1/3) leaves (S = {4}); then both say 1 and nothing leaves.
        # True state 5: agent 1 says 1/3 (S = {1..6}); agent 2's cell {5,6} gives 0 (S = {5,6}); both say 0.
        # True state 9: agent 1 says 0 and only {7,8,9} gives 0 (S = {7,8,9}); agent 2's cells {7,8} and {9}
        # both give 0, nothing leaves; agent 1 says 0 again.
        for state, history in ((4, (F(1, 3), F(1, 2), 1, 1, 1)), (5, (F(1, 3), 0, 0, 0)), (9, (0, 0, 0))):
            with self.subTest(state=state):
                result = call('agreement_process', UNIFORM_9, [NINE_1, NINE_2], NINE_A, state)
                self.assertEqual(result['history'], history)
                self.assertEqual(result['posteriors'], (history[-1], history[-1]))
                self.assertTrue(result['agreed'] and result['converged'] and result['common_prior'])

    def test_a_common_prior_may_be_given_once_per_agent(self):
        for priors in ([UNIFORM_9, UNIFORM_9], [UNIFORM_9, [2] * 9], [[F(1, 9)] * 9, [5] * 9]):
            with self.subTest(priors=priors):
                result = call('agreement_process', priors, [NINE_1, NINE_2], NINE_A, 1)
                self.assertIs(result['common_prior'], True)
                self.assertEqual(result['history'], (F(1, 3), F(1, 2), F(1, 3), F(1, 3), F(1, 3)))

    def test_different_priors_without_private_information_do_not_agree(self):
        # States 1, 2; neither agent can tell them apart (one cell each); A = {1}; agent 1's prior is (1/2, 1/2),
        # agent 2's is (1/4, 3/4). Agent 1 says 1/2, agent 2 says 1/4; each has one cell, so nothing ever leaves.
        # After two quiet announcements the posteriors are common knowledge and still differ.
        result = call('agreement_process', [[1, 1], [1, 3]], [[[1, 2]], [[1, 2]]], [1], 1)
        self.assertEqual(result, {'posteriors': (F(1, 2), F(1, 4)), 'agreed': False, 'announcements': 2,
                                  'history': (F(1, 2), F(1, 4)), 'history_truncated': False,
                                  'common_prior': False, 'converged': True})

    def test_different_priors_after_talking_still_do_not_agree(self):
        # The nine-state model, true state 1, but agent 2's prior puts weight 2 on state 3 (1 elsewhere).
        #  1. agent 1 (uniform): 1/3; S = {1..6}.
        #  2. agent 2: cell {1,2,3,4} has weight 5, A = {3,4} has 2 + 1: 3/5. {5,6} gives 0: S = {1,2,3,4}.
        #  3. agent 1: 1/3; {4} gives 1 and leaves: S = {1,2,3}.
        #  4. agent 2: cell {1,2,3} has weight 4, A has 2: 1/2. Nothing leaves.
        #  5. agent 1: 1/3. Nothing leaves. Both cells are now S itself, so each posterior is common knowledge,
        #     and they differ, because the priors differ.
        result = call('agreement_process', [UNIFORM_9, [1, 1, 2, 1, 1, 1, 1, 1, 1]], [NINE_1, NINE_2], NINE_A, 1)
        self.assertEqual(result, {'posteriors': (F(1, 3), F(1, 2)), 'agreed': False, 'announcements': 5,
                                  'history': (F(1, 3), F(3, 5), F(1, 3), F(1, 2), F(1, 3)),
                                  'history_truncated': False, 'common_prior': False, 'converged': True})

    def test_three_agents_speak_in_turn(self):
        # The nine-state model plus agent 3, who sees nothing (one cell). True state 1.
        #  1. agent 1: 1/3; S = {1..6}.      2. agent 2: 1/2; S = {1,2,3,4}.
        #  3. agent 3, cell S: 2/4 = 1/2; one cell, nothing leaves.
        #  4. agent 1: 1/3; {4} gives 1 and leaves: S = {1,2,3}.
        #  5. agent 2: 1/3.  6. agent 3: 1/3.  7. agent 1: 1/3. Three quiet announcements in a row: it stops.
        result = call('agreement_process', UNIFORM_9, [NINE_1, NINE_2, [list(range(1, 10))]], NINE_A, 1)
        self.assertEqual(result['history'], (F(1, 3), F(1, 2), F(1, 2), F(1, 3), F(1, 3), F(1, 3), F(1, 3)))
        self.assertEqual(result['posteriors'], (F(1, 3),) * 3)
        self.assertTrue(result['agreed'] and result['converged'])

    def test_a_single_agent(self):
        # One agent sees {1,2} {3}; uniform prior; A = {1,3}; true state 1. It says 1/2 and {3} (1) leaves;
        # then it says 1/2 again and nothing leaves.
        result = call('agreement_process', [1, 1, 1], [[[1, 2], [3]]], [1, 3], 1)
        self.assertEqual(result, {'posteriors': (F(1, 2),), 'agreed': True, 'announcements': 2,
                                  'history': (F(1, 2), F(1, 2)), 'history_truncated': False,
                                  'common_prior': True, 'converged': True})

    def test_a_current_cell_without_weight_is_refused(self):
        # Agent 1 (prior 1, 1, 1, 0) sees {1,2} {3,4}; agent 2 (uniform) sees {1,4} {2} {3}. A = {1,2,3}, true 1.
        #  1. agent 1: {1,2} gives 1 and {3,4} gives 1 (state 4 has no weight): nothing leaves.
        #  2. agent 2: {1,4} gives 1/2, {2} and {3} give 1: S = {1,4}.
        #  3. agent 1's current cells are {1} and {4}; {4} has no weight under its prior: undefined.
        with self.assertRaises(K.KnowledgeError) as caught:
            call('agreement_process', [[1, 1, 1, 0], [1, 1, 1, 1]], [[[1, 2], [3, 4]], [[1, 4], [2], [3]]],
                 [1, 2, 3], 1)
        self.assertEqual(caught.exception.kind, 'check')
        self.assertIn('announcement 3, agent 1', caught.exception.message)
        self.assertIn('[4]', caught.exception.message)
        with self.assertRaises(K.KnowledgeError) as caught:     # a cell without weight before anyone learns
            call('agreement_process', [1, 1, 0], [[[1, 2], [3]], [[1, 2, 3]]], [1], 1)
        self.assertIn('announcement 1, agent 1', caught.exception.message)

    def test_the_review_fixture_converges_after_137_announcements(self):
        # The independent reference of the pre-freeze review reports 137 announcements and every posterior 0 at
        # convergence; at announcement 64 its posteriors were all 1/2 (equal, not converged). See REVIEW above.
        result = call('agreement_process', [1] * 64, REVIEW, ODD, 32)
        self.assertEqual(result, {'posteriors': (0,) * 8, 'agreed': True, 'announcements': 137,
                                  'history': (F(1, 2),) * 64, 'history_truncated': True,
                                  'common_prior': True, 'converged': True})
        history, final, converged, public = refinement_process([[1] * 64] * 8, REVIEW, set(ODD), 32, 512)
        self.assertEqual((len(history), tuple(final), converged, public), (137, (0,) * 8, True, {32}))
        self.assertEqual(history[:128], [F(1, 2)] * 128)        # 1/2 until agent 1 isolates state 32
        self.assertEqual(history[128:], [0] * 9)
        self.assertEqual(result['history'], tuple(history[:64]))

    def test_a_long_process_with_silent_agents_converges_after_130_announcements(self):
        result = call('agreement_process', [1] * 64, CHAIN, ODD, 1)
        self.assertEqual(result, {'posteriors': (F(1, 2),) * 8, 'agreed': True, 'announcements': 130,
                                  'history': (F(1, 2),) * 64, 'history_truncated': True,
                                  'common_prior': True, 'converged': True})
        history, final, converged, public = refinement_process([[1] * 64] * 8, CHAIN, set(ODD), 1, 512)
        self.assertEqual((len(history), tuple(final), converged, public), (130, (F(1, 2),) * 8, True, {1, 2}))

    def test_the_bound_of_n_times_m_announcements_is_never_exceeded(self):
        # Seeded random models, including different priors; the count is compared with the bound n * m and with
        # the independent refinement process run far past the bound.
        rng = random.Random(512)
        longest = 0
        for case in range(200):
            n, m = rng.randint(1, 8), rng.randint(1, 5)
            partitions = [random_partition(rng, n) for _ in range(m)]
            priors = [[F(rng.randint(1, 4), rng.randint(1, 3)) for _ in range(n)] for _ in range(m)]
            if case % 2:
                priors = priors[0]
            event = [w for w in range(1, n + 1) if rng.random() < 0.5]
            truth = rng.randint(1, n)
            with self.subTest(case=case):
                result = call('agreement_process', priors, partitions, event, truth)
                weights = [priors] * m if case % 2 else priors
                history = refinement_process(weights, partitions, set(event), truth, 10 * n * m)[0]
                self.assertTrue(result['converged'])
                self.assertEqual(result['announcements'], len(history))
                self.assertLessEqual(result['announcements'], n * m)
                longest = max(longest, result['announcements'] / (n * m))
        self.assertGreater(longest, 0.5)        # some runs come well past half of the bound
        for partitions in (REVIEW, CHAIN):
            self.assertLessEqual(call('agreement_process', [1] * 64, partitions, ODD, 1)['announcements'], 64 * 8)

    def test_an_unconverged_process_is_never_reported(self):
        # If the proven bound were ever reached without m quiet announcements, the call must fail, not return
        # posteriors or `agreed` for an unfinished process. Simulate that defect by lowering the bound.
        with patch.object(K, '_announcement_bound', lambda n, m: 2):
            with self.assertRaises(S.SymblicError) as caught:
                call('agreement_process', UNIFORM_9, [NINE_1, NINE_2], NINE_A, 1)
        self.assertNotIsInstance(caught.exception, K.KnowledgeError)
        self.assertEqual(caught.exception.kind, 'runtime')
        self.assertIn('internal defect', caught.exception.message)
        with patch.object(K, '_announcement_bound', lambda n, m: 5):    # exactly enough: the stop is at 5
            self.assertTrue(call('agreement_process', UNIFORM_9, [NINE_1, NINE_2], NINE_A, 1)['converged'])


# ---------------------------------------------------------------------------------------------------------------
# Refusals and limits
# ---------------------------------------------------------------------------------------------------------------

class Refusals(unittest.TestCase):
    def assert_refused(self, kind, name, *args, text=None):
        with self.assertRaises(K.KnowledgeError) as caught:
            call(name, *args)
        self.assertEqual(caught.exception.kind, kind, caught.exception.message)
        if text is not None:
            self.assertIn(text, caught.exception.message)

    def test_a_cell_twice_and_a_state_in_two_cells(self):
        for partition in ([[1, 2], [1, 2], [3]], [[1, 2], [2, 3]], [[1, 1], [2]], [[2], S.ValueSet([1, 2])]):
            with self.subTest(partition=partition):
                self.assert_refused('check', 'knows_event', partition, [1], 1, text='appears twice')
                self.assert_refused('check', 'common_partition', [[[1, 2, 3]], partition], text='appears twice')

    def test_a_missing_state(self):
        self.assert_refused('check', 'knows_event', [[1], [3]], [1], 1, text='no cell for state 2')
        self.assert_refused('check', 'common_partition', [[[1], [2], [3]], [[1, 2]]], text='covers the states 1..2')
        self.assert_refused('check', 'common_partition', [[[1, 2]], [[1], [2], [3]]], text='covers the states 1..3')
        self.assert_refused('check', 'agreement_process', [1, 1, 1], [[[1, 2, 3]], [[1], [2]]], [1], 1)

    def test_a_state_out_of_range(self):
        p = [[1, 2], [3]]
        for args in ((p, [4], 1), (p, [0], 1), (p, [1], 0), (p, [1], 4), (p, [1], -2), ([[0, 1], [2]], [1], 1),
                     ([[-3], [1]], [1], 1)):
            with self.subTest(args=args):
                self.assert_refused('check', 'knows_event', *args)
        self.assert_refused('check', 'common_knowledge', [p], [1, 2, 3, 4], 1, text='outside the states 1..3')
        self.assert_refused('check', 'posterior_given', [1, 1, 1], [1, 4], [1], text='outside the states 1..3')
        self.assert_refused('check', 'posterior_given', [1, 1, 1], [1], [0])
        self.assert_refused('check', 'agreement_process', [1, 1, 1], [p], [1], 9)
        self.assert_refused('check', 'knows_event', p, [1], 10 ** 5000, text='a very large number')

    def test_a_state_listed_twice_in_an_event_or_a_cell(self):
        self.assert_refused('check', 'knows_event', [[1, 2], [3]], [1, 1], 1, text='lists state 1 twice')
        self.assert_refused('check', 'posterior_given', [1, 1, 1], [1, 2, 2], [1], text='lists state 2 twice')

    def test_an_empty_partition_list_and_empty_parts(self):
        self.assert_refused('check', 'common_partition', [], text='empty')
        self.assert_refused('check', 'common_knowledge', [], [1], 1)
        self.assert_refused('check', 'agreement_process', [1], [], [1], 1)
        self.assert_refused('check', 'knows_event', [], [1], 1, text='no cells')
        self.assert_refused('check', 'knows_event', [[1], []], [1], 1, text='empty cell')
        self.assert_refused('check', 'posterior_given', [], [1], [1], text='empty')
        self.assert_refused('check', 'agreement_process', [], [[[1]]], [1], 1, text='empty')

    def test_more_than_eight_agents(self):
        nine = [[[1, 2]]] * 9
        self.assertEqual(call('common_partition', nine[:8]), ((1, 2),))
        self.assert_refused('budget', 'common_partition', nine, text='at most 8 agents')
        self.assert_refused('budget', 'common_knowledge', nine, [1], 1)
        self.assert_refused('budget', 'agreement_process', [1, 1], nine, [1], 1)

    def test_more_than_64_states(self):
        full = [list(range(1, 65))]
        self.assertEqual(call('common_partition', [full]), (tuple(range(1, 65)),))
        self.assertEqual(call('posterior_given', [1] * 64, list(range(1, 65)), [64]), F(1, 64))
        for partition in ([list(range(1, 66))], [[w] for w in range(1, 66)], [[1, 65]], [full[0], [65]]):
            with self.subTest(size=len(partition)):
                self.assert_refused('budget', 'common_partition', [partition], text='at most 64 states')
        self.assert_refused('budget', 'knows_event', full, S.ValueSet(range(1, 66)), 1, text='at most 64 states')
        self.assert_refused('budget', 'knows_event', full, list(range(1, 66)), 1)
        self.assert_refused('budget', 'posterior_given', [1] * 65, [1], [1], text='at most 64 states')
        self.assert_refused('budget', 'agreement_process', [1] * 65, [full], [1], 1)

    def test_prior_values(self):
        self.assert_refused('check', 'posterior_given', [1, -1, 2], [1], [1], text='negative')
        self.assert_refused('check', 'posterior_given', [1, F(-1, 3), 2], [1], [1], text='negative')
        self.assert_refused('check', 'posterior_given', [0, 0, 0], [1], [1], text='sums to zero')
        self.assert_refused('check', 'agreement_process', [[1, 1], [0, 0]], [[[1, 2]], [[1], [2]]], [1], 1,
                            text='prior 2 sums to zero')
        self.assert_refused('check', 'agreement_process', [[1, 1], [1, -1]], [[[1, 2]], [[1], [2]]], [1], 1,
                            text='prior 2, entry 2, is negative')

    def test_priors_that_do_not_match_the_model(self):
        two = [[[1, 2]], [[1], [2]]]
        self.assert_refused('check', 'agreement_process', [1, 1, 1], two, [1], 1, text='3 entries')
        self.assert_refused('check', 'agreement_process', [[1, 1], [1, 1], [1, 1]], two, [1], 1,
                            text='3 priors for 2 agents')
        self.assert_refused('check', 'agreement_process', [[1, 1], [1, 1, 1]], two, [1], 1, text='3 entries')
        self.assert_refused('type', 'agreement_process', [[1, 1], 1], two, [1], 1, text='one prior')

    def test_floats_and_bools_are_refused_everywhere(self):
        p = [[1, 2], [3]]
        for bad in (True, False, 1.0, 2.5, float('nan'), float('inf')):
            with self.subTest(value=bad):
                self.assert_refused('type', 'knows_event', p, [1], bad)
                self.assert_refused('type', 'knows_event', p, [1, bad], 1)
                self.assert_refused('type', 'knows_event', [[1, bad], [3]], [1], 1)
                self.assert_refused('type', 'common_partition', [[[1, 2], [bad]]])
                self.assert_refused('type', 'posterior_given', [1, bad, 1], [1], [1])
                self.assert_refused('type', 'posterior_given', [1, 1, 1], [bad], [1])
                self.assert_refused('type', 'agreement_process', [1, 1, bad], [p], [1], 1)
                self.assert_refused('type', 'agreement_process', [1, 1, 1], [p], [1], bad)
        self.assert_refused('type', 'knows_event', p, S.ValueSet([1, True]), 1, text='not Bool')
        self.assert_refused('type', 'knows_event', p, frozenset({1, 2.5}), 1, text='not float')

    def test_other_values_of_the_wrong_kind(self):
        p = [[1, 2], [3]]
        for bad in ('1', None, F(3, 2), Decimal(1), (1,), {'state': 1}):
            with self.subTest(state=bad):
                self.assert_refused('type', 'knows_event', p, [1], bad)
        for container in ('123', 7, {'cells': p}, None):
            with self.subTest(container=container):
                self.assert_refused('type', 'knows_event', container, [1], 1)
                self.assert_refused('type', 'knows_event', p, container, 1)
                self.assert_refused('type', 'knows_event', [[1, 2], container], [1], 1)
                self.assert_refused('type', 'common_partition', container)
                self.assert_refused('type', 'posterior_given', container, [1], [1])
                self.assert_refused('type', 'agreement_process', container, [p], [1], 1)
        self.assert_refused('type', 'common_partition', S.ValueSet([1, 2]), text='list of partitions')
        self.assert_refused('type', 'posterior_given', S.ValueSet([1, 2]), [1], [1], text='list of numbers')
        self.assert_refused('type', 'posterior_given', [1, '2'], [1], [1], text='exact number')
        self.assert_refused('type', 'posterior_given', [1, Decimal(2)], [1], [1], text='exact number')
        self.assert_refused('type', 'knows_event', p, [1, F(3, 2)], 1, text='whole number')

    def test_huge_integers_are_refused(self):
        self.assert_refused('budget', 'posterior_given', [1, 1 << 5000], [1], [1], text='4096 bits')
        self.assert_refused('budget', 'posterior_given', [1, F(1, 1 << 5000)], [1], [1], text='4096 bits')
        # Each entry fits, but the common denominator 3^900 * 5^700 * 7^600 needs about 4738 bits.
        self.assert_refused('budget', 'posterior_given', [F(1, 3 ** 900), F(1, 5 ** 700), F(1, 7 ** 600)], [1], [1],
                            text='common denominator')
        # Each entry fits, but clearing the denominator 2^4000 turns 2^4000 into 2^8000.
        self.assert_refused('budget', 'posterior_given', [F(1, 1 << 4000), 1 << 4000], [1], [1],
                            text='denominators are cleared')
        self.assertEqual(call('posterior_given', [F(1, 1 << 4000), F(1, 1 << 4000)], [1, 2], [1]), F(1, 2))

    def test_corrupted_fraction_internals_are_refused(self):
        for numerator, denominator in ((1, 0), (1, -2), (2, 4), (True, 2), ('1', 2)):
            corrupted = F(1, 2)
            corrupted._numerator, corrupted._denominator = numerator, denominator
            with self.subTest(numerator=numerator, denominator=denominator):
                self.assert_refused('type', 'posterior_given', [1, corrupted], [1], [1])
        state = F(2)
        state._denominator = True
        self.assert_refused('type', 'knows_event', [[1, 2]], [1], state)

    def test_odd_python_values_are_refused_without_rendering_them(self):
        # Not kernel values, but a Python caller can pass them: a cyclic list and a fraction too long to print.
        cyclic = []
        cyclic.append(cyclic)
        huge = F(10 ** 5000 + 1, 2)
        for bad in (cyclic, huge, 'x' * 1000):
            with self.subTest(kind=type(bad).__name__):
                self.assert_refused('type', 'knows_event', [[1, 2]], [1, bad], 1)
                self.assert_refused('type', 'knows_event', [[1, 2], [bad]], [1], 1)
                self.assert_refused('type', 'posterior_given', [1, 1], [1, bad], [1])
        self.assert_refused('type', 'knows_event', [[1, 2]], [True], 1, text='Bool true')
        self.assert_refused('type', 'knows_event', [[1, 2]], [F(3, 2)], 1, text='Number 3/2')

    def test_a_budget_argument_must_be_a_kernel_budget(self):
        with self.assertRaises(K.KnowledgeError) as caught:
            K.knows_event([[1]], [1], 1, budget=5)
        self.assertEqual(caught.exception.kind, 'type')

    def test_errors_are_symblic_errors_with_kernel_codes(self):
        self.assertTrue(issubclass(K.KnowledgeError, S.SymblicError))
        with self.assertRaises(S.SymblicError) as caught:
            call('knows_event', [[1], [1]], [1], 1)
        self.assertEqual(caught.exception.as_dict()['code'], 'SYM_CHECK')


class KernelBudget(unittest.TestCase):
    CASES = (('knows_event', ([[1, 2], [3]], [1, 2], 1)),
             ('common_partition', ([NINE_1, NINE_2],)),
             ('common_knowledge', ([NINE_1, NINE_2], NINE_A, 1)),
             ('posterior_given', (UNIFORM_9, [1, 2, 3, 4], NINE_A)),
             ('agreement_process', (UNIFORM_9, [NINE_1, NINE_2], NINE_A, 1)))

    def test_every_builtin_charges_the_kernel_budget_and_stops_at_its_end(self):
        for name, args in self.CASES:
            with self.subTest(name=name):
                steps = used(name, *args)
                self.assertGreater(steps, 0)
                call(name, *args, steps=steps)                      # exactly enough
                with self.assertRaises(S.SymblicError) as caught:
                    call(name, *args, steps=steps - 1)
                self.assertNotIsInstance(caught.exception, K.KnowledgeError)
                self.assertIn('step budget', caught.exception.message)

    def test_the_charge_grows_with_the_work(self):
        small = used('common_partition', [[[1, 2], [3]], [[1], [2, 3]]])
        large = used('common_partition', [CHAIN_1, CHAIN_2])
        self.assertLess(small, large)
        # The process is charged before each announcement in proportion to the states still in W.
        short = used('agreement_process', UNIFORM_9, [NINE_1, NINE_2], NINE_A, 1)          # 5 announcements
        long = used('agreement_process', [1] * 64, REVIEW, ODD, 32)                       # 137 announcements
        self.assertGreater(long, 137 * 3)                           # every announcement keeps at least 1 state
        self.assertLess(short * 10, long)

    def test_a_tiny_budget_refuses_before_any_work(self):
        for name, args in self.CASES:
            with self.subTest(name=name), self.assertRaises(S.SymblicError):
                call(name, *args, steps=0)


# ---------------------------------------------------------------------------------------------------------------
# Brute-force cross-checks on seeded random instances
# ---------------------------------------------------------------------------------------------------------------

class BruteForce(unittest.TestCase):
    def test_the_meet_is_the_finest_common_coarsening(self):
        rng = random.Random(20261003)
        for case in range(40):
            n, m = rng.randint(1, 6), rng.randint(1, 4)
            partitions = [random_partition(rng, n) for _ in range(m)]
            with self.subTest(case=case, partitions=partitions):
                coarsenings = [q for q in set_partitions(list(range(1, n + 1)))
                               if all(refines(p, q) for p in partitions)]
                finest = [q for q in coarsenings if all(refines(q, other) for other in coarsenings)]
                self.assertEqual(len(finest), 1)
                expected = tuple(sorted(tuple(sorted(cell)) for cell in finest[0]))
                self.assertEqual(call('common_partition', partitions), expected)

    def test_common_knowledge_matches_the_knowledge_hierarchy(self):
        rng = random.Random(1976)
        for case in range(40):
            n, m = rng.randint(1, 10), rng.randint(1, 4)
            partitions = [random_partition(rng, n) for _ in range(m)]
            event = [w for w in range(1, n + 1) if rng.random() < 0.7]
            rng.shuffle(event)
            common = iterated_common_knowledge(partitions, set(event))
            with self.subTest(case=case, partitions=partitions, event=event):
                for state in range(1, n + 1):
                    self.assertEqual(call('common_knowledge', partitions, event, state), state in common)
                    for cells in partitions:
                        self.assertEqual(call('knows_event', cells, event, state),
                                         state in knowledge(cells, set(event)))

    def test_posteriors_match_a_direct_computation(self):
        rng = random.Random(4096)
        for case in range(40):
            n = rng.randint(1, 12)
            prior = [F(rng.randint(0, 6), rng.randint(1, 5)) for _ in range(n)]
            prior[rng.randrange(n)] = F(rng.randint(1, 6), rng.randint(1, 5))     # a positive sum
            normal = [p / sum(prior) for p in prior]
            cell = [w for w in range(1, n + 1) if rng.random() < 0.6] or [rng.randint(1, n)]
            event = [w for w in range(1, n + 1) if rng.random() < 0.5]
            weight = sum(normal[w - 1] for w in cell)
            with self.subTest(case=case, prior=prior, cell=cell, event=event):
                if weight == 0:
                    with self.assertRaises(K.KnowledgeError):
                        call('posterior_given', prior, cell, event)
                    continue
                expected = sum(normal[w - 1] for w in cell if w in event) / weight
                self.assertEqual(call('posterior_given', prior, cell, event), expected)

    def test_the_process_matches_partition_refinement_and_the_theorem(self):
        rng = random.Random(1982)
        changed = disagreed = 0
        for case in range(60):
            n, m = rng.randint(2, 9), rng.randint(1, 4)
            partitions = [random_partition(rng, n) for _ in range(m)]
            common = case % 2 == 0
            priors = ([F(rng.randint(1, 5), rng.randint(1, 4)) for _ in range(n)] if common else
                      [[F(rng.randint(1, 5), rng.randint(1, 4)) for _ in range(n)] for _ in range(m)])
            weights = [priors] * m if common else priors
            event = [w for w in range(1, n + 1) if rng.random() < 0.5]
            truth = rng.randint(1, n)
            history, final, converged, public = refinement_process(weights, partitions, set(event), truth, 512)
            with self.subTest(case=case, partitions=partitions, priors=priors, event=event, truth=truth):
                result = call('agreement_process', priors, partitions, event, truth)
                self.assertEqual(result['history'], tuple(history[:64]))
                self.assertIs(result['history_truncated'], len(history) > 64)
                self.assertEqual(result['posteriors'], tuple(final))
                self.assertEqual(result['announcements'], len(history))
                self.assertIs(converged, True)
                self.assertIs(result['converged'], True)
                self.assertLessEqual(len(history), n * m)
                self.assertIs(result['agreed'], len(set(final)) == 1)
                self.assertIs(result['common_prior'],
                              len({tuple(p / sum(w) for p in w) for w in weights}) == 1)
                if common:                                          # the theorem: a common prior agrees,
                    self.assertIs(result['agreed'], True)           # at the posterior given the final set
                    target = sum(priors[w - 1] for w in public if w in event) / sum(priors[w - 1] for w in public)
                    self.assertEqual(result['posteriors'], (target,) * m)
                else:
                    disagreed += not result['agreed']
                for agent in range(m):
                    if len(set(history[agent::m])) > 1:
                        changed += 1
                        break
        self.assertGreater(changed, 5)          # many runs revise a posterior before they stop
        self.assertGreater(disagreed, 0)        # some runs with different priors end apart


# ---------------------------------------------------------------------------------------------------------------
# Canonical form, determinism and the kernel program
# ---------------------------------------------------------------------------------------------------------------

def _no_unnormalised_numbers(value):
    if type(value) is F:
        return value.denominator != 1
    if isinstance(value, (tuple, list)):
        return all(_no_unnormalised_numbers(v) for v in value)
    if isinstance(value, dict):
        return all(_no_unnormalised_numbers(v) for v in value.values())
    return True


class CanonicalForm(unittest.TestCase):
    def test_results_are_canonical_kernel_values(self):
        results = [call('knows_event', NINE_1, NINE_A, 1), call('common_partition', [NINE_1, NINE_2]),
                   call('common_knowledge', [NINE_1, NINE_2], NINE_A, 1),
                   call('posterior_given', UNIFORM_9, [1, 2, 3, 4], NINE_A),
                   call('posterior_given', UNIFORM_9, [1, 2], NINE_A),
                   call('agreement_process', UNIFORM_9, [NINE_1, NINE_2], NINE_A, 1),
                   call('agreement_process', [1] * 64, CHAIN, ODD, 1)]
        for result in results:
            with self.subTest(result=S.show(result, 80)):
                self.assertTrue(S.canon_json(result))
                self.assertRegex(S.fingerprint(result), r'^[0-9a-f]{16}$')
                self.assertTrue(_no_unnormalised_numbers(result))
        record = results[5]
        self.assertEqual(set(record), {'posteriors', 'agreed', 'announcements', 'history', 'history_truncated',
                                       'common_prior', 'converged'})
        self.assertIs(type(record['history']), tuple)
        self.assertIs(type(record['posteriors']), tuple)
        self.assertIs(type(record['announcements']), int)
        self.assertEqual(S.canon(record)['history'], [{'#q': '1/3'}, {'#q': '1/2'}, {'#q': '1/3'}, {'#q': '1/3'},
                                                      {'#q': '1/3'}])
        self.assertEqual(S.canon(results[1]), [list(range(1, 10))])
        self.assertIs(type(results[4]), int)

    def test_the_order_of_cells_and_the_kind_of_container_do_not_matter(self):
        rng = random.Random(7)
        base = call('agreement_process', UNIFORM_9, [NINE_1, NINE_2], NINE_A, 1)
        meet = call('common_partition', [NINE_1, NINE_2])
        for _ in range(10):
            shuffled = []
            for cells in (NINE_1, NINE_2):
                copy = [rng.sample(cell, len(cell)) for cell in cells]
                rng.shuffle(copy)
                shuffled.append([S.ValueSet(cell) if rng.random() < 0.5 else tuple(cell) for cell in copy])
            event = S.ValueSet(NINE_A) if rng.random() < 0.5 else NINE_A[::-1]
            self.assertEqual(S.fingerprint(call('agreement_process', tuple(UNIFORM_9), shuffled, event, 1)),
                             S.fingerprint(base))
            self.assertEqual(call('common_partition', shuffled), meet)

    def test_set_refusals_name_the_same_problem_on_every_run(self):
        # A set has no order; the message names the kinds found, sorted, not one member chosen by hashing.
        with self.assertRaises(K.KnowledgeError) as caught:
            call('knows_event', [[1, 2]], S.ValueSet(['b', 'a', True, (1,)]), 1)
        self.assertIn('not Bool, List, Text', caught.exception.message)
        with self.assertRaises(K.KnowledgeError) as caught:
            call('knows_event', [[1, 2]], S.ValueSet([7, 9, 8]), 1)
        self.assertIn('state 7', caught.exception.message)          # the smallest offending state


class KernelProgram(unittest.TestCase):
    def run_program(self, source):
        run = SR.Run(source)
        run.kernel.functions.update(K.FUNCTIONS)
        return run.execute()

    def test_the_documented_example_prints_the_documented_output(self):
        text = DOC.read_text(encoding='utf-8')
        program = re.search(r'```symblic\n(.*?)```', text, re.S).group(1)
        expected = re.search(r'Expected output[^\n]*\n+```text\n(.*?)```', text, re.S).group(1).strip().splitlines()
        self.assertTrue(S.check(program)['ok'], S.check(program)['errors'])
        report = self.run_program(program)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual((report['asks'], report['calls']), (0, 0))
        self.assertEqual([f'{row["label"]}: {row["text"]}' for row in report['outputs']], expected)

    def test_a_refusal_fails_the_run_at_its_line(self):
        report = self.run_program('let a = [1].\nlet model = knows_event([[1, 2], [2]], a, 1).\n')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual((report['error']['kind'], report['error']['line']), ('check', 2))
        self.assertIn('appears twice', report['error']['message'])

    def test_the_builtin_names_and_an_inert_import(self):
        self.assertEqual(tuple(K.FUNCTIONS), NAMES)
        self.assertEqual(K.VERSION, 1)
        self.assertEqual((K.MAX_STATES, K.MAX_AGENTS, K.MAX_HISTORY, K.MAX_ANNOUNCEMENTS, K.MAX_BITS),
                         (64, 8, 64, 512, 4096))
        self.assertFalse(hasattr(K, 'MAX_ROUNDS'))          # replaced by the proven bound n * m
        before = dict(S.BUILTINS)
        spec = importlib.util.spec_from_file_location('_knowledge_inert_fixture', K.__file__)
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)
        self.assertEqual(S.BUILTINS, before)
        self.assertEqual(tuple(isolated.FUNCTIONS), NAMES)


if __name__ == '__main__':
    unittest.main()
