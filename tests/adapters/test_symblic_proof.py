"""Pure isolated checks; Boolean models are a test oracle, never the verifier."""
import copy
import itertools
import json
import unittest
from unittest.mock import patch

from symblic.adapters import proof as P

A, B, C = [['atom', name] for name in ('A', 'B', 'C')]
F = ['false']


def check(premises, goal, term):
    return P.verify(premises, goal, {'version': 1, 'proof': term})


def truth(formula, valuation):
    """Independent Boolean interpretation (necessary, not sufficient for IPL)."""
    op, *args = formula
    if op == 'atom':
        return valuation[args[0]]
    if op == 'false':
        return False
    left, right = (truth(x, valuation) for x in args)
    return {'and': left and right, 'or': left or right,
            'implies': not left or right}[op]


class ProofTests(unittest.TestCase):
    def accepted(self, premises, goal, term):
        receipt = check(premises, goal, term)
        self.assertTrue(receipt['ok'], receipt)
        self.assertEqual(receipt['conclusion'], goal)
        self.assertEqual(receipt['open_assumptions'], [])
        self.assertTrue(receipt['conditional_on_premises'])
        self.assertEqual(receipt['consistency'], 'not_checked')
        for values in itertools.product((False, True), repeat=3):
            valuation = dict(zip(('A', 'B', 'C'), values))
            if all(truth(f, valuation) for f in premises.values()):
                self.assertTrue(truth(goal, valuation))
        return receipt

    def rejected(self, premises, goal, term, error=None):
        receipt = check(premises, goal, term)
        self.assertFalse(receipt['ok'], receipt)
        self.assertIsNone(receipt['conclusion'])
        self.assertEqual(receipt['hashes'], {})
        if error:
            self.assertEqual(receipt['error'], error)
        return receipt

    def test_all_rules(self):
        self.accepted({}, ['implies', A, A],
                      ['implies_intro', 'a', A, ['hypothesis', 'a']])
        self.accepted({'f': ['implies', A, B], 'a': A}, B,
                      ['implies_elim', ['premise', 'f'], ['premise', 'a']])
        for op, goal in [('and_left', A), ('and_right', B)]:
            self.accepted({'a': A, 'b': B}, goal,
                          [op, ['and_intro', ['premise', 'a'], ['premise', 'b']]])
        for op, goal in [('or_left', ['or', A, B]), ('or_right', ['or', B, A])]:
            self.accepted({'a': A}, goal, [op, ['premise', 'a'], B])
        self.accepted({'absurd': F}, C, ['false_elim', ['premise', 'absurd'], C])
        self.accepted({'choice': ['or', A, B], 'ac': ['implies', A, C],
                       'bc': ['implies', B, C]}, C,
                      ['or_elim', ['premise', 'choice'], 'a',
                       ['implies_elim', ['premise', 'ac'], ['hypothesis', 'a']], 'b',
                       ['implies_elim', ['premise', 'bc'], ['hypothesis', 'b']]])

    def test_generated_small_formulas_and_proofs_exhaustive_boolean_oracle(self):
        base = [A, B, F]
        formulas = base + [[op, a, b] for op in ('and', 'or', 'implies')
                           for a in base for b in base]
        for a in formulas:
            self.accepted({}, ['implies', a, a],
                          ['implies_intro', 'h', a, ['hypothesis', 'h']])
            for b in formulas:
                # All 900 formula pairs; conditional proofs, all 8 valuations.
                self.accepted({'a': a, 'b': b}, ['and', a, b],
                              ['and_intro', ['premise', 'a'], ['premise', 'b']])
                self.accepted({'f': ['implies', a, b], 'a': a}, b,
                              ['implies_elim', ['premise', 'f'], ['premise', 'a']])
                self.accepted({'d': ['or', a, b]}, ['or', b, a],
                              ['or_elim', ['premise', 'd'], 'l',
                               ['or_right', ['hypothesis', 'l'], b], 'r',
                               ['or_left', ['hypothesis', 'r'], a]])

    def test_discharge_and_scope_attacks(self):
        self.rejected({}, A, ['hypothesis', 'a'], 'unknown_hypothesis')
        self.rejected({}, A, ['premise', 'invented'], 'unknown_premise')
        self.rejected({'a': A}, A, ['hypothesis', 'a'], 'unknown_hypothesis')
        self.rejected({}, ['implies', A, A],
                      ['implies_intro', 'a', A, ['premise', 'a']], 'unknown_premise')
        self.rejected({'a': B}, ['implies', A, A],
                      ['implies_intro', 'a', A, ['hypothesis', 'a']], 'shadowing')
        self.rejected({}, ['implies', A, ['implies', B, B]],
                      ['implies_intro', 'h', A,
                       ['implies_intro', 'h', B, ['hypothesis', 'h']]], 'shadowing')
        self.rejected({}, ['and', ['implies', A, A], A],
                      ['and_intro', ['implies_intro', 'h', A, ['hypothesis', 'h']],
                       ['hypothesis', 'h']], 'unknown_hypothesis')
        # Vacuous discharge and reuse in disjoint scopes are legitimate.
        self.accepted({'a': A}, ['implies', B, A],
                      ['implies_intro', 'h', B, ['premise', 'a']])
        identity = ['implies_intro', 'h', A, ['hypothesis', 'h']]
        self.accepted({}, ['and', ['implies', A, A], ['implies', A, A]],
                      ['and_intro', identity, identity])

    def test_or_elimination_mutations(self):
        premises = {'d': ['or', A, B]}
        term = ['or_elim', ['premise', 'd'], 'l',
                ['or_right', ['hypothesis', 'l'], B], 'r',
                ['or_left', ['hypothesis', 'r'], A]]
        goal = ['or', B, A]
        self.accepted(premises, goal, term)
        mutations = [(3, ['hypothesis', 'l']), (5, ['hypothesis', 'r']),
                     (3, ['or_right', ['hypothesis', 'r'], B]),
                     (5, ['or_left', ['hypothesis', 'l'], A]),
                     (4, 'l'), (2, 'd'), (1, ['false_elim', ['premise', 'd'], goal])]
        for index, replacement in mutations:
            bad = copy.deepcopy(term)
            bad[index] = replacement
            self.rejected(premises, goal, bad)
        self.rejected(premises, ['and', goal, B],
                      ['and_intro', term, ['hypothesis', 'r']], 'unknown_hypothesis')

    def test_rule_mismatches_and_classical_shortcuts(self):
        for term in (['and_left', ['premise', 'a']], ['and_right', ['premise', 'a']],
                     ['implies_elim', ['premise', 'a'], ['premise', 'a']],
                     ['false_elim', ['premise', 'a'], B], ['excluded_middle', A],
                     ['double_negation_elim', ['premise', 'a']]):
            self.rejected({'a': A}, B, term)
        self.rejected({'f': ['implies', A, B], 'c': C}, B,
                      ['implies_elim', ['premise', 'f'], ['premise', 'c']])
        self.rejected({'a': A}, B, ['premise', 'a'], 'goal_mismatch')

    def test_envelope_types_unknown_keys_and_malformed_nodes(self):
        good = {'version': 1, 'proof': ['premise', 'a']}
        for version in (True, False, 1.0, '1', None, 0, 2, 10**10000):
            self.assertFalse(P.verify({'a': A}, A, dict(good, version=version))['ok'])
        for key in ('premises', 'goal', 'conclusion', 'checks'):
            self.assertFalse(P.verify({'a': A}, A, dict(good, **{key: A}))['ok'])
        for term in ({'rule': 'premise', 'name': 'a'}, ['premise', 'a', A],
                     [], [True], ['premise', []], ['implies_intro', '', A, ['premise', 'a']]):
            self.rejected({'a': A}, A, term)
        for formula in (['atom'], ['atom', 1], ['false', A], ['and', A],
                        ['forall', 'x', A], ('atom', 'A'), {'atom': 'A'}):
            self.rejected({'a': A, 'unused': formula}, A, ['premise', 'a'])
        class EvilList(list):
            def __iter__(self):
                raise AssertionError('must not invoke custom methods')
        self.rejected({'a': EvilList(A)}, A, ['premise', 'a'], 'input_type')

    def test_resource_limits_cover_unused_inputs_and_cycles(self):
        cycle = []
        cycle.append(cycle)
        self.rejected({'a': A, 'unused': cycle}, A, ['premise', 'a'], 'cycle')
        cyclic_dict = {}
        cyclic_dict['x'] = cyclic_dict
        self.assertEqual(P.verify({}, A, cyclic_dict)['error'], 'cycle')
        deep = A
        for _ in range(2000):
            deep = ['and', A, deep]
        self.rejected({'a': A, 'unused': deep}, A, ['premise', 'a'], 'depth_limit')
        self.rejected({'a': A, 'unused': ['atom', 'x' * (P.MAX_TEXT + 1)]},
                      A, ['premise', 'a'], 'text_limit')
        self.rejected({'a': A, 'unused': ['atom', '\ud800']}, A, ['premise', 'a'], 'unicode')
        self.rejected({'a': A, 'unused': [A] * (P.MAX_NODES + 1)},
                      A, ['premise', 'a'], 'node_limit')
        with patch.object(P, 'MAX_BYTES', 100):
            self.rejected({'a': A, 'unused': ['atom', 'x' * 101]},
                          A, ['premise', 'a'], 'byte_limit')
        with patch.object(P, 'MAX_WORK', 1):
            self.rejected({'a': A}, A, ['premise', 'a'], 'work_limit')
        dag = A
        for _ in range(16):
            dag = ['and', dag, dag]
        self.rejected({'a': A, 'unused': dag}, A, ['premise', 'a'], 'node_limit')

    def test_inferred_growth_and_aggregate_work_are_bounded(self):
        formula = A
        for _ in range(55):
            formula = ['implies', A, formula]
        term = ['premise', 'p']
        for i in range(12):
            term = ['implies_intro', str(i), A, term]
        # Each input fits, but the inferred implication chain exceeds depth.
        self.rejected({'p': formula}, A, term, 'depth_limit')
        formula = A
        for _ in range(8):
            formula = ['and', formula, formula]
        term = ['premise', 'p']
        for _ in range(7):
            term = ['and_left', ['and_intro', term, term]]
        # Repeated bounded formulas consume real aggregate work, no mocked cap.
        self.rejected({'p': formula}, A, term, 'work_limit')

    def test_generated_term_mutations_against_boolean_models(self):
        # Enumerate all shallow proof trees over three premise leaves, including
        # ill-typed trees. Every accepted judgment must satisfy all valuations.
        premises = {'a': A, 'b': B, 'f': ['implies', A, C]}
        leaves = [['premise', n] for n in premises]
        terms = list(leaves)
        terms += [[op, x] for op in ('and_left', 'and_right') for x in leaves]
        terms += [[op, x, y] for op in ('and_intro', 'implies_elim')
                  for x in leaves for y in leaves]
        terms += [[op, x, f] for op in ('or_left', 'or_right', 'false_elim')
                  for x in leaves for f in (A, B, C, F)]
        goals = [A, B, C, F] + [[op, a, b] for op in ('and', 'or', 'implies')
                               for a in (A, B, C, F) for b in (A, B, C, F)]
        accepted = rejected = 0
        for term in terms:
            for goal in goals:
                if check(premises, goal, term)['ok']:
                    accepted += 1
                    self.accepted(premises, goal, term)
                else:
                    rejected += 1
        self.assertGreater(accepted, 20)
        self.assertGreater(rejected, 3000)

    def test_receipt_hashes_determinism_and_detachment(self):
        premises = {'unused': B, 'a': A}
        term = ['premise', 'a']
        r = self.accepted(premises, A, term)
        self.assertEqual(r['used_premises'], ['a'])
        self.assertEqual(r['checks'], 1)
        self.assertEqual(r, check(dict(reversed(list(premises.items()))), A, term))
        changed = check({'unused': C, 'a': A}, A, term)
        self.assertNotEqual(r['hashes']['premises'], changed['hashes']['premises'])
        self.assertNotEqual(r['hashes']['judgment'], changed['hashes']['judgment'])
        r['conclusion'][1] = 'changed'
        self.assertEqual(A, ['atom', 'A'])
        json.dumps(r)


class TextTests(unittest.TestCase):
    def test_precedence_and_association(self):
        self.assertEqual(P.parse_formula('not "A" and "B" or "C" implies "A" implies "B"'),
                         ['implies', ['or', ['and', ['implies', A, F], B], C],
                          ['implies', A, B]])
        self.assertEqual(P.parse_formula('"A" and "B" and "C"'), ['and', ['and', A, B], C])
        self.assertEqual(P.parse_formula('not not "A"'), ['implies', ['implies', A, F], F])

    def test_roundtrip_and_opaque_predicate_text(self):
        formulas = [A, B, F, ['atom', ''], ['atom', '∀x P(x) implies true'],
                    ['atom', 'line\nquote"\\雪'], ['atom', 'false']]
        formulas += [[op, a, b] for op in ('and', 'or', 'implies')
                     for a in list(formulas) for b in list(formulas)]
        for formula in formulas:
            self.assertEqual(P.parse_formula(P.render_formula(formula)), formula)
        self.assertEqual(P.parse_formula('"P(x)"'), ['atom', 'P(x)'])
        self.assertFalse(check({'p': ['atom', 'P(x)']}, ['atom', 'P(y)'], ['premise', 'p'])['ok'])

    def test_syntax_and_limits(self):
        for text in ('', 'A', 'forall x P(x)', '"A" "B"', '"A" and', '()',
                     '("A"', '"A")', '"bad\\q"', 'true', 'notable', '\ud800',
                     'not ' * 10000 + '"A"', '(' * 10000 + '"A"' + ')' * 10000,
                     '"A" and ' * 1000 + '"A"'):
            with self.subTest(text=text[:40]), self.assertRaises(P.ProofError):
                P.parse_formula(text)
        cycle = ['and', A]
        cycle.append(cycle)
        with self.assertRaises(P.ProofError):
            P.render_formula(cycle)


if __name__ == '__main__':
    unittest.main()
