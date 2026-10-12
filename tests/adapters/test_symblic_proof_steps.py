"""Independent nested-proof translation and adversarial flat-DAG scope checks."""
import copy
import itertools
import json
import unittest
from unittest.mock import patch

from symblic.adapters import proof as P
from symblic.adapters import proof_steps as W
from tests.adapters.test_symblic_proof import truth

A, B, C = [['atom', name] for name in ('A', 'B', 'C')]
F = ['false']


def step(ident, rule, *args, formula=None):
    return {'id': ident, 'rule': rule, 'args': list(args), 'formula': formula}


def certificate(*steps, result=None):
    return {'version': 1, 'steps': list(steps), 'result': result or steps[-1]['id']}


def nested(cert, premises):
    """Independent expansion with alpha-renaming; no flat checker internals used."""
    nodes = {row['id']: row for row in cert['steps']}
    counter = itertools.count()
    def fresh():
        while True:
            name = 'flat_h_' + str(next(counter))
            if name not in premises:
                return name
    def build(ident, bindings):
        row = nodes[ident]
        op, args = row['rule'], row['args']
        if op == 'premise':
            return ['premise', args[0]]
        if op == 'assume':
            return ['hypothesis', bindings.get(ident, 'unbound_' + ident)]
        if op == 'implies_intro':
            name = fresh()
            return [op, name, nodes[args[0]]['formula'], build(args[1], {**bindings, args[0]: name})]
        if op == 'or_elim':
            left, right = fresh(), fresh()
            return [op, build(args[0], bindings), left, build(args[2], {**bindings, args[1]: left}),
                    right, build(args[4], {**bindings, args[3]: right})]
        result = [op] + [build(arg, bindings) for arg in args]
        if op in ('or_left', 'or_right', 'false_elim'):
            result.append(row['formula'])
        return result
    return {'version': 1, 'proof': build(cert['result'], {})}


class ProofSteps(unittest.TestCase):
    def accepted(self, premises, goal, cert):
        result = W.verify(premises, goal, cert)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['conclusion'], goal)
        self.assertEqual(result['open_assumptions'], [])
        self.assertEqual(result['consistency'], 'not_checked')
        self.assertTrue(result['conditional_on_premises'])
        independent = P.verify(premises, goal, nested(cert, premises))
        self.assertTrue(independent['ok'], independent)
        self.assertEqual(independent['used_premises'], result['used_premises'])
        for values in itertools.product((False, True), repeat=3):
            valuation = dict(zip(('A', 'B', 'C'), values))
            if all(truth(formula, valuation) for formula in premises.values()):
                self.assertTrue(truth(goal, valuation))
        return result

    def rejected(self, premises, goal, cert, error=None):
        result = W.verify(premises, goal, cert)
        self.assertFalse(result['ok'], result)
        self.assertIsNone(result['conclusion'])
        self.assertEqual(result['hashes'], {})
        if error:
            self.assertEqual(result['error'], error)
        return result

    def test_modus_ponens_three_flat_lines(self):
        cert = certificate(step('p', 'premise', 'if_a'), step('q', 'premise', 'a'),
                           step('r', 'implies_elim', 'p', 'q'))
        result = self.accepted({'if_a': ['implies', A, B], 'a': A}, B, cert)
        self.assertEqual(result['checks'], 3)
        self.assertEqual(result['used_premises'], ['a', 'if_a'])

    def test_all_rules_and_branch_discharge(self):
        self.accepted({}, ['implies', A, A], certificate(step('a', 'assume', formula=A),
                                                       step('out', 'implies_intro', 'a', 'a')))
        pair = [step('a', 'premise', 'a'), step('b', 'premise', 'b'), step('ab', 'and_intro', 'a', 'b')]
        self.accepted({'a': A, 'b': B}, ['and', A, B], certificate(*pair))
        for rule, target in (('and_left', A), ('and_right', B)):
            self.accepted({'a': A, 'b': B}, target, certificate(*pair, step('out', rule, 'ab')))
        for rule, target in (('or_left', ['or', A, B]), ('or_right', ['or', B, A])):
            self.accepted({'a': A}, target, certificate(step('a', 'premise', 'a'), step('out', rule, 'a', formula=B)))
        self.accepted({'absurd': F}, C, certificate(step('f', 'premise', 'absurd'), step('out', 'false_elim', 'f', formula=C)))
        cert = certificate(step('d', 'premise', 'choice'), step('ac', 'premise', 'ac'), step('bc', 'premise', 'bc'),
                           step('a', 'assume', formula=A), step('ca', 'implies_elim', 'ac', 'a'),
                           step('b', 'assume', formula=B), step('cb', 'implies_elim', 'bc', 'b'),
                           step('out', 'or_elim', 'd', 'a', 'ca', 'b', 'cb'))
        self.accepted({'choice': ['or', A, B], 'ac': ['implies', A, C], 'bc': ['implies', B, C]}, C, cert)

    def test_shared_dag_and_nested_reuse_alpha_renamed_for_independent_checker(self):
        self.accepted({}, ['and', ['implies', A, A], ['implies', A, A]], certificate(
            step('h', 'assume', formula=A), step('identity', 'implies_intro', 'h', 'h'),
            step('out', 'and_intro', 'identity', 'identity')))
        self.accepted({}, ['implies', A, ['implies', A, A]], certificate(
            step('h', 'assume', formula=A), step('identity', 'implies_intro', 'h', 'h'),
            step('out', 'implies_intro', 'h', 'identity')))

    def test_vacuous_discharge_and_unused_open_assumptions(self):
        cert = certificate(step('p', 'premise', 'a'), step('h', 'assume', formula=B),
                           step('unused', 'assume', formula=C), step('unused_p', 'premise', 'unused'),
                           step('out', 'implies_intro', 'h', 'p'))
        result = self.accepted({'a': A, 'unused': C}, ['implies', B, A], cert)
        self.assertEqual(result['used_premises'], ['a'])
        # Both branches can ignore their local assumption without gaining it as a premise.
        self.accepted({'choice': ['or', A, B], 'c': C}, C, certificate(
            step('d', 'premise', 'choice'), step('c', 'premise', 'c'),
            step('l', 'assume', formula=A), step('r', 'assume', formula=B),
            step('out', 'or_elim', 'd', 'l', 'c', 'r', 'c')))

    def test_assumption_escape_and_discharge_by_formula_not_identity_are_rejected(self):
        result = self.rejected({}, A, certificate(step('h', 'assume', formula=A)), 'open_assumptions')
        self.assertEqual(result['open_assumptions'], ['h'])
        self.rejected({}, ['and', ['implies', A, A], A], certificate(
            step('h', 'assume', formula=A), step('i', 'implies_intro', 'h', 'h'),
            step('out', 'and_intro', 'i', 'h')), 'open_assumptions')
        self.rejected({}, ['implies', A, A], certificate(
            step('h', 'assume', formula=A), step('other', 'assume', formula=A),
            step('out', 'implies_intro', 'other', 'h')), 'open_assumptions')
        self.rejected({'a': A}, ['implies', A, A], certificate(
            step('p', 'premise', 'a'), step('out', 'implies_intro', 'p', 'p')), 'assumption_reference')

    def test_branch_scope_mutants_and_escaping_hypotheses(self):
        premises = {'d': ['or', A, B]}
        cert = certificate(step('d', 'premise', 'd'), step('l', 'assume', formula=A),
                           step('left', 'or_right', 'l', formula=B), step('r', 'assume', formula=B),
                           step('right', 'or_left', 'r', formula=A),
                           step('out', 'or_elim', 'd', 'l', 'left', 'r', 'right'))
        self.accepted(premises, ['or', B, A], cert)
        for index, field, value in ((2, 'args', ['r']), (4, 'args', ['l']),
                                    (5, 'args', ['d', 'l', 'left', 'l', 'right']),
                                    (1, 'formula', C), (5, 'args', ['d', 'd', 'left', 'r', 'right']),
                                    (5, 'args', ['d', 'l', 'l', 'r', 'r'])):
            bad = copy.deepcopy(cert)
            bad['steps'][index][field] = value
            self.rejected(premises, ['or', B, A], bad)
        escape = copy.deepcopy(cert)
        escape['steps'].append(step('escape', 'and_intro', 'out', 'r'))
        escape['result'] = 'escape'
        self.rejected(premises, ['and', ['or', B, A], B], escape, 'open_assumptions')
        # Equal branch formulas must not hide cross-branch dependence.
        self.rejected({'d': ['or', A, A]}, ['implies', A, A], certificate(
            step('d', 'premise', 'd'), step('l', 'assume', formula=A), step('r', 'assume', formula=A),
            step('bad', 'or_elim', 'd', 'l', 'r', 'r', 'r'),
            step('out', 'implies_intro', 'r', 'bad')), 'branch_scope')

    def test_forward_cycle_duplicate_and_missing_ids(self):
        for cert in (certificate(step('out', 'and_left', 'later'), step('later', 'premise', 'a'), result='out'),
                     certificate(step('out', 'and_left', 'out')),
                     certificate(step('x', 'premise', 'a'), step('x', 'premise', 'a')),
                     certificate(step('x', 'premise', 'a'), result='missing')):
            self.rejected({'a': A}, A, cert)
        self.rejected({}, A, certificate(step('a', 'premise', 'a')), 'unknown_premise')

    def test_no_premise_goal_or_inferred_formula_forgery(self):
        good = certificate(step('x', 'premise', 'a'))
        for key in ('premises', 'goal', 'conclusion', 'checks'):
            bad = dict(good, **{key: A})
            self.rejected({'a': B}, A, bad, 'certificate_shape')
        self.rejected({'a': B}, A, good, 'goal_mismatch')
        self.rejected({'a': B}, A, certificate(step('x', 'premise', 'a', formula=A)), 'unexpected_formula')
        self.rejected({'a': A}, B, certificate(step('x', 'premise', 'a'), step('out', 'false_elim', 'x', formula=B)), 'false_expected')
        self.rejected({'a': A}, A, certificate(step('x', 'excluded_middle', formula=A)), 'rule')

    def test_uniform_shape_schema_types_and_invalid_unused_lines(self):
        good = certificate(step('x', 'premise', 'a'))
        for version in (True, 1.0, '1', None, 2):
            self.rejected({'a': A}, A, dict(good, version=version))
        for row in ({'id': 'x', 'rule': 'premise', 'args': ['a']},
                    dict(good['steps'][0], extra=True), step('x', 'premise', 'a', 'a'),
                    step('bad-id', 'premise', 'a'), step('x', 'assume', formula=['atom', 3])):
            self.rejected({'a': A}, A, certificate(row))
        bad = copy.deepcopy(good)
        bad['steps'].append(step('unused', 'assume', formula=['unknown']))
        self.rejected({'a': A}, A, bad, 'formula_shape')
        self.rejected({'a': A, 'bad_unused': None}, A, good, 'formula_shape')
        schema = W.certificate_schema()
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['properties']['steps']['items']['required']), {'id', 'rule', 'args', 'formula'})
        schema['properties']['steps']['items']['properties']['rule']['enum'].clear()
        self.assertIn('premise', W.certificate_schema()['properties']['steps']['items']['properties']['rule']['enum'])

    def test_generated_small_formulas_translate_to_nested_checker(self):
        formulas = [A, B, F] + [[op, A, B] for op in ('and', 'or', 'implies')]
        for left, right in itertools.product(formulas, repeat=2):
            self.accepted({'f': ['implies', left, right], 'x': left}, right, certificate(
                step('p', 'premise', 'f'), step('x', 'premise', 'x'), step('out', 'implies_elim', 'p', 'x')))
            self.accepted({'d': ['or', left, right]}, ['or', right, left], certificate(
                step('d', 'premise', 'd'), step('l', 'assume', formula=left),
                step('left', 'or_right', 'l', formula=right), step('r', 'assume', formula=right),
                step('right', 'or_left', 'r', formula=left),
                step('out', 'or_elim', 'd', 'l', 'left', 'r', 'right')))

    def test_rule_and_reference_mutants_agree_with_independent_checker_when_accepted(self):
        premises = {'a': A, 'b': B, 'f': ['implies', A, C]}
        initial = [step('a', 'premise', 'a'), step('b', 'premise', 'b'), step('f', 'premise', 'f')]
        goals = [A, B, C, F] + [[op, left, right] for op in ('and', 'or', 'implies')
                              for left in (A, B, C) for right in (A, B, C)]
        candidates = [step('out', op, ref) for op in ('and_left', 'and_right') for ref in ('a', 'b', 'f')]
        candidates += [step('out', op, left, right) for op in ('implies_elim', 'and_intro')
                       for left in ('a', 'b', 'f') for right in ('a', 'b', 'f')]
        accepted = rejected = 0
        for row, target in itertools.product(candidates, goals):
            cert = certificate(*initial, row)
            result = W.verify(premises, target, cert)
            if result['ok']:
                self.accepted(premises, target, cert)
                accepted += 1
            else:
                rejected += 1
        self.assertGreater(accepted, 4)
        self.assertGreater(rejected, 700)

    def test_full_preflight_cycles_custom_types_and_host_budget(self):
        good = certificate(step('x', 'premise', 'a'))
        cycle = []
        cycle.append(cycle)
        result = self.rejected({'a': A, 'unused': cycle}, A, good, 'cycle')
        self.assertEqual(result['checks'], 0)
        class EvilList(list):
            def __iter__(self):
                raise AssertionError('custom iteration must not run')
        self.rejected({'a': EvilList(A)}, A, good, 'input_type')
        for value, error in ((['atom', 'x' * (W.MAX_TEXT + 1)], 'text_limit'),
                             (['atom', '\ud800'], 'unicode'), ([A] * (W.MAX_NODES + 1), 'node_limit')):
            self.rejected({'a': A, 'unused': value}, A, good, error)
        ticks = []
        W.verify({'a': A}, A, good, tick=lambda: ticks.append(1))
        self.assertGreater(len(ticks), len(json.dumps(good).split()))
        class HostBudget(Exception):
            pass
        def exhausted():
            raise HostBudget()
        with self.assertRaises(HostBudget):
            W.verify({'a': A}, A, good, tick=exhausted)

    def test_inferred_exponential_growth_and_aggregate_work_are_bounded(self):
        rows = [step('s0', 'premise', 'a')]
        for index in range(1, 20):
            rows.append(step('s' + str(index), 'and_intro', 's' + str(index - 1), 's' + str(index - 1)))
        result = self.rejected({'a': A}, A, certificate(*rows))
        self.assertIn(result['error'], ('node_limit', 'work_limit', 'byte_limit'))
        with patch.object(W, 'MAX_WORK', 1):
            result = self.rejected({'a': A}, A, certificate(step('x', 'premise', 'a')), 'work_limit')
            self.assertEqual(result['checks'], 0)
        with patch.object(W, 'MAX_STEPS', 1):
            self.rejected({'a': A}, A, certificate(step('a', 'premise', 'a'), step('b', 'premise', 'a')), 'step_limit')
        with patch.object(W, 'MAX_PREMISES', 1):
            self.rejected({'a': A, 'b': B}, A, certificate(step('a', 'premise', 'a')), 'premise_limit')

    def test_receipt_determinism_detachment_and_unused_contract_pins(self):
        premises = {'a': A, 'unused': B}
        cert = certificate(step('a', 'premise', 'a'))
        result = self.accepted(premises, A, cert)
        self.assertEqual(result, W.verify(dict(reversed(list(premises.items()))), A, cert))
        changed = W.verify(dict(premises, unused=C), A, cert)
        self.assertNotEqual(result['hashes']['judgment'], changed['hashes']['judgment'])
        result['conclusion'][1] = 'changed'
        self.assertEqual(A, ['atom', 'A'])
        json.dumps(result)


if __name__ == '__main__':
    unittest.main()
