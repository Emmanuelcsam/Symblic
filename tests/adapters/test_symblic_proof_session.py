"""Incremental one-inference proof sessions: pure API, prefix agreement and native bridge (fakes only)."""
import copy
import itertools
import json
import random
import unittest
from fractions import Fraction
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import embed as embed
from symblic.js import check as JS
from symblic.adapters import proof as P
from symblic.adapters import proof_adapter as adapter
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W
from symblic.kernel.run import Run
from tests.adapters.test_symblic_proof import truth
from tests.adapters.test_symblic_proof_steps import certificate, nested, step

A, B, C = [['atom', name] for name in ('A', 'B', 'C')]
F = ['false']
MP = {'if_a': ['implies', A, B], 'a': A}
NAMES = ('proof_session_start', 'proof_session_append', 'proof_session_frontier')


def cand(rule, *args, formula=None):
    return {'rule': rule, 'args': list(args), 'formula': formula}


def play(premises, goal, *candidates, tick=None):
    """Append candidates in order, keeping only accepted states; returns final state and results."""
    state, results = R.start(premises, goal, tick=tick), []
    for candidate in candidates:
        results.append(R.append(premises, goal, state, candidate, tick=tick))
        if results[-1]['valid']:
            state = results[-1]['state']
    return state, results


def registered():
    """Root registers the builtins in symblic.ADAPTERS; tests add them only while absent."""
    return patch.dict(S.BUILTINS, {name: S._adapter('symblic_proof_adapter', 'proof-term checking', name)
                                   for name in NAMES if name not in S.BUILTINS})


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)


class SessionApi(unittest.TestCase):
    def test_modus_ponens_one_host_numbered_inference_per_call_and_verify_receipt(self):
        state = R.start(MP, B)
        self.assertEqual((state['version'], state['format'], state['certificate_version']), (1, R.FORMAT, W.VERSION))
        self.assertEqual(state['steps'], [])
        self.assertEqual(state['hashes'], {'premises': P._hash(MP), 'goal': P._hash(B)})
        self.assertEqual(R.frontier(state), {'goal': B, 'premises': {'a': A, 'if_a': ['implies', A, B]},
                                             'lines': [], 'next_id': 's1', 'complete': False,
                                             'steps_left': W.MAX_STEPS})
        expected = [('premise', ['if_a'], ['implies', A, B]), ('premise', ['a'], A), ('implies_elim', ['s1', 's2'], B)]
        for index, (rule, args, formula) in enumerate(expected):
            result = R.append(MP, B, state, cand(rule, *args))
            self.assertTrue(result['valid'], result)
            self.assertIsNone(result['rejected'])
            self.assertIsNone(result['error'])
            ident = 's' + str(index + 1)
            self.assertEqual(result['step'], {'id': ident, 'rule': rule, 'args': args, 'formula': None})
            self.assertEqual(result['line'], {'id': ident, 'rule': rule, 'formula': formula, 'free': []})
            self.assertEqual(result['state']['steps'], state['steps'] + [result['step']])
            self.assertEqual(result['frontier'], R.frontier(result['state']))
            self.assertEqual(result['scope'], 'derivation_from_declared_premises')
            self.assertEqual((result['conditional_on_premises'], result['consistency']), (True, 'not_checked'))
            state = result['state']
        self.assertTrue(result['complete'])
        self.assertIsNone(result['next_id'])
        self.assertEqual(result['certificate'], certificate(step('s1', 'premise', 'if_a'), step('s2', 'premise', 'a'),
                                                            step('s3', 'implies_elim', 's1', 's2')))
        self.assertEqual(result['receipt'], W.verify(MP, B, result['certificate']))
        self.assertTrue(result['receipt']['ok'])
        self.assertEqual(result['receipt']['used_premises'], ['a', 'if_a'])
        self.assertTrue(R.frontier(state)['complete'])
        self.assertIsNone(R.frontier(state)['next_id'])

    def test_invalid_candidate_keeps_prior_state_and_returns_finite_diagnostic(self):
        state, _ = play(MP, B, cand('premise', 'if_a'))
        prior = copy.deepcopy(state)
        cases = ((cand('implies_elim', 's1', 's1'), 'implies_elim_mismatch'),
                 (cand('premise', 'invented'), 'unknown_premise'),
                 (cand('and_left', 's2'), 'unknown_or_forward_reference'),
                 (cand('and_left', 's9'), 'unknown_or_forward_reference'),
                 (cand('and_left', 's1'), 'and_expected'),
                 (cand('excluded_middle', formula=A), 'rule'),
                 (cand('premise', 'a', 'if_a'), 'rule_arity'),
                 (cand('premise', 'a', formula=A), 'unexpected_formula'),
                 (cand('assume', formula=['atom']), 'formula_shape'),
                 (cand('implies_intro', 's1', 's1'), 'assumption_reference'),
                 (cand('false_elim', 's1', formula=C), 'false_expected'))
        for candidate, error in cases:
            with self.subTest(error=error):
                result = R.append(MP, B, state, candidate)
                self.assertFalse(result['valid'])
                self.assertEqual((result['rejected'], result['error'], result['rejected_step']), ('candidate', error, 1))
                self.assertEqual(result['hint'], R.HINTS[error])
                self.assertEqual(result['state'], prior)
                self.assertEqual(result['frontier'], R.frontier(prior))
                self.assertEqual(result['next_id'], 's2')
                self.assertIsNone(result['step'])
                self.assertIsNone(result['line'])
                self.assertIsNone(result['certificate'])
                self.assertFalse(result['complete'])
        self.assertEqual(state, prior)
        result = R.append(MP, B, state, cand('premise', 'a'))
        self.assertEqual(result['step']['id'], 's2')

    def test_detached_deterministic_order_independent_and_json_safe(self):
        state, results = play(MP, B, cand('premise', 'if_a'), cand('premise', 'a'))
        reordered = dict(reversed(list(MP.items())))
        self.assertEqual(R.start(reordered, B), R.start(MP, B))
        again = R.append(reordered, B, results[0]['state'], cand('premise', 'a'))
        self.assertEqual(again, results[1])
        for value in (state, results[1]):
            json.dumps(value)
        self.assertFalse([item for item in walk(state) if type(item) not in (dict, list, str, int, type(None))])
        self.assertFalse([item for item in walk(state) if type(item) is bool])
        premises, candidate = copy.deepcopy(MP), cand('implies_elim', 's1', 's2')
        result = R.append(premises, B, state, candidate)
        premises['a'][1] = 'changed'
        candidate['args'].append('s9')
        result['line']['formula'][1] = 'changed'
        self.assertEqual(result['state']['premises']['a'], A)
        self.assertEqual(result['step']['args'], ['s1', 's2'])
        self.assertEqual(result['frontier']['lines'][-1]['formula'], B)
        self.assertEqual(result['certificate']['steps'][-1]['args'], ['s1', 's2'])
        self.assertEqual(R.append(MP, B, state, cand('implies_elim', 's1', 's2'))['receipt'], result['receipt'])

    def test_rules_schema_and_candidate_type_are_generic_detached_and_contain_no_task(self):
        rules = R.rules()
        rules['rules'].clear()
        self.assertTrue(R.rules()['rules'])
        self.assertEqual([row['rule'] for row in R.rules()['rules']], list(W.ARITIES))
        for row in R.rules()['rules']:
            self.assertEqual(len(row['args']), W.ARITIES[row['rule']])
            self.assertEqual(row['formula'] is None, row['rule'] not in W.FORMULA_RULES)
        example = R.rules()['unrelated_example']
        sample = {'sample': ['atom', 'An unrelated sample flag']}
        self.assertEqual(example['frontier'], R.frontier(R.start(sample, sample['sample'])))
        self.assertTrue(R.append(sample, sample['sample'], R.start(sample, sample['sample']),
                                 example['candidate'])['complete'])
        self.assertFalse(R.append(MP, B, R.start(MP, B), example['candidate'])['valid'])
        schema = R.candidate_schema()
        self.assertEqual(schema['required'], ['rule', 'args', 'formula'])
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['properties']['rule']['enum'], list(W.ARITIES))
        schema['properties']['rule']['enum'].clear()
        self.assertTrue(R.candidate_schema()['properties']['rule']['enum'])
        checked = S.check('use profile=verified.\ngiven f: Any.\nask c: ' + R.CANDIDATE_TYPE
                          + ' "Next inference." from f with effort=low\nshow c.\n', execution_profile='verified')
        self.assertTrue(checked['ok'], checked)
        self.assertEqual(set(R.HINTS) & {'state_hash', 'sequent_mismatch'}, set())
        for text in list(R.HINTS.values()) + [R.STATE_HINT]:
            self.assertLess(len(text), 400)


class SessionRules(unittest.TestCase):
    def test_implication_discharge_across_calls_and_open_goal_line_is_not_complete(self):
        goal = ['implies', ['and', A, B], ['and', B, A]]
        state, results = play({}, goal, cand('assume', formula=['and', A, B]), cand('and_right', 's1'),
                              cand('and_left', 's1'), cand('and_intro', 's2', 's3'))
        self.assertTrue(all(row['valid'] for row in results))
        self.assertEqual(results[-1]['line'], {'id': 's4', 'rule': 'and_intro', 'formula': ['and', B, A], 'free': ['s1']})
        self.assertFalse(results[-1]['complete'])
        final = R.append({}, goal, state, cand('implies_intro', 's1', 's4'))
        self.assertTrue(final['complete'], final)
        self.assertEqual(final['line']['free'], [])
        self.assertEqual(final['receipt'], W.verify({}, goal, final['certificate']))
        # A line with the goal formula and a free assumption leaves the session open.
        state, results = play({}, A, cand('assume', formula=A))
        self.assertTrue(results[0]['valid'])
        self.assertFalse(results[0]['complete'])
        self.assertEqual(R.frontier(state)['lines'], [{'id': 's1', 'rule': 'assume', 'formula': A, 'free': ['s1']}])
        # Discharge is by assumption identity, not by an equal formula.
        state, results = play({}, ['implies', A, A], cand('assume', formula=A), cand('assume', formula=A),
                              cand('implies_intro', 's2', 's1'))
        self.assertTrue(results[-1]['valid'])
        self.assertEqual(results[-1]['line'], {'id': 's3', 'rule': 'implies_intro', 'formula': ['implies', A, A],
                                               'free': ['s1']})
        self.assertFalse(results[-1]['complete'])
        closed = R.append({}, ['implies', A, A], state, cand('implies_intro', 's1', 's1'))
        self.assertTrue(closed['complete'])
        self.assertEqual(closed['certificate']['result'], 's4')

    def test_free_lists_follow_line_order_not_text_order(self):
        rows = [cand('assume', formula=A)] + [cand('premise', 'b') for _ in range(9)] + [cand('assume', formula=C)]
        rows.append(cand('and_intro', 's11', 's1'))
        state, results = play({'b': B}, ['and', C, A], *rows)
        self.assertEqual(results[-1]['line']['free'], ['s1', 's11'])
        self.assertEqual(R.frontier(state)['lines'][-1]['free'], ['s1', 's11'])

    def test_disjunction_branch_scope_vacuous_discharge_and_false_elimination(self):
        premises, goal = {'d': ['or', A, B]}, ['or', B, A]
        prefix = [cand('premise', 'd'), cand('assume', formula=A), cand('or_right', 's2', formula=B),
                  cand('assume', formula=B), cand('or_left', 's4', formula=A)]
        state, results = play(premises, goal, *prefix)
        self.assertTrue(all(row['valid'] for row in results))
        self.assertEqual(results[2]['line']['free'], ['s2'])
        for args, error in ((('s1', 's2', 's5', 's4', 's3'), 'branch_scope'),
                            (('s1', 's2', 's2', 's4', 's4'), 'or_elim_mismatch'),
                            (('s1', 's4', 's3', 's2', 's5'), 'branch_assumption_mismatch'),
                            (('s1', 's2', 's3', 's2', 's5'), 'branch_assumption_collision'),
                            (('s1', 's3', 's3', 's4', 's5'), 'assumption_reference'),
                            (('s2', 's2', 's3', 's4', 's5'), 'or_expected')):
            with self.subTest(args=args):
                result = R.append(premises, goal, state, cand('or_elim', *args))
                self.assertEqual((result['rejected'], result['error']), ('candidate', error))
                self.assertEqual(result['state'], state)
        final = R.append(premises, goal, state, cand('or_elim', 's1', 's2', 's3', 's4', 's5'))
        self.assertTrue(final['complete'])
        self.assertEqual(final['receipt'], W.verify(premises, goal, final['certificate']))
        # Equal branch formulas do not hide cross-branch dependence.
        state, _ = play({'d': ['or', A, A]}, ['implies', A, A], cand('premise', 'd'), cand('assume', formula=A),
                        cand('assume', formula=A))
        result = R.append({'d': ['or', A, A]}, ['implies', A, A], state, cand('or_elim', 's1', 's2', 's3', 's3', 's3'))
        self.assertEqual((result['rejected'], result['error']), ('candidate', 'branch_scope'))
        _, results = play({'a': A}, ['implies', B, A], cand('premise', 'a'), cand('assume', formula=B),
                          cand('implies_intro', 's2', 's1'))
        self.assertTrue(results[-1]['complete'])
        self.assertEqual(results[-1]['receipt']['used_premises'], ['a'])
        _, results = play({'x': F}, C, cand('premise', 'x'), cand('false_elim', 's1', formula=C))
        self.assertTrue(results[-1]['complete'])

    def test_complete_session_refuses_more_inferences_but_returns_its_verified_certificate(self):
        state, results = play({'a': A}, A, cand('premise', 'a'))
        self.assertTrue(results[0]['complete'])
        result = R.append({'a': A}, A, state, cand('premise', 'a'))
        self.assertEqual((result['valid'], result['rejected'], result['error']), (False, 'session', 'session_complete'))
        self.assertTrue(result['complete'])
        self.assertEqual(result['state'], state)
        self.assertEqual(result['certificate'], results[0]['certificate'])
        self.assertTrue(result['receipt']['ok'])
        self.assertIsNone(result['next_id'])
        self.assertIsNone(result['rejected_step'])


class SessionForgery(unittest.TestCase):
    def setUp(self):
        self.state, _ = play(MP, B, cand('premise', 'if_a'), cand('premise', 'a'))

    def refused_state(self, state, error, premises=MP, goal=B, index=None):
        result = R.append(premises, goal, state, cand('implies_elim', 's1', 's2'))
        self.assertFalse(result['valid'])
        self.assertEqual((result['rejected'], result['error']), ('state', error), result)
        self.assertEqual(result['rejected_step'], index)
        self.assertEqual(result['hint'], R.STATE_HINT)
        for key in ('state', 'frontier', 'certificate', 'receipt', 'next_id', 'step', 'line'):
            self.assertIsNone(result[key])
        return result

    def test_candidate_cannot_carry_ids_sequents_state_or_conclusions(self):
        good = cand('implies_elim', 's1', 's2')
        for key in ('id', 'premises', 'goal', 'state', 'steps', 'result', 'conclusion', 'version', 'free'):
            with self.subTest(key=key):
                result = R.append(MP, B, self.state, dict(good, **{key: 's3' if key == 'id' else A}))
                self.assertEqual((result['rejected'], result['error']), ('candidate', 'candidate_shape'))
                self.assertEqual(result['state'], self.state)
        for bad in ({'rule': 'premise', 'args': ['a']}, ['implies_elim', ['s1', 's2'], None], 'implies_elim', None, 1):
            self.assertEqual(R.append(MP, B, self.state, bad)['error'], 'candidate_shape')

    def test_stored_prefix_is_rechecked_on_every_import(self):
        forged = copy.deepcopy(self.state)
        forged['steps'][1] = {'id': 's2', 'rule': 'implies_elim', 'args': ['s1', 's1'], 'formula': None}
        self.refused_state(forged, 'implies_elim_mismatch', index=1)
        with self.assertRaisesRegex(P.ProofError, 'implies_elim_mismatch'):
            R.frontier(forged)
        forged = copy.deepcopy(self.state)
        forged['steps'][0]['conclusion'] = B
        self.refused_state(forged, 'step_shape', index=0)
        forged = copy.deepcopy(self.state)
        forged['steps'][1] = {'id': 's2', 'rule': 'assume', 'args': [], 'formula': A}
        result = R.append(MP, B, forged, cand('implies_elim', 's1', 's2'))
        self.assertTrue(result['valid'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['line']['free'], ['s2'])

    def test_host_ids_envelope_and_hashes_bind_the_ledger(self):
        for mutate, error in ((lambda s: s['steps'][1].update(id='s9'), 'state_step_id'),
                              (lambda s: s['steps'].reverse(), 'state_step_id'),
                              (lambda s: s['steps'][0].update(id='h'), 'state_step_id'),
                              (lambda s: s['steps'].__setitem__(0, 'step'), 'state_step_id'),
                              (lambda s: s['hashes'].update(goal='0' * 64), 'state_hash'),
                              (lambda s: s['hashes'].update(premises=None), 'state_hash'),
                              (lambda s: s.update(extra=1), 'state_shape'),
                              (lambda s: s.pop('hashes'), 'state_shape'),
                              (lambda s: s.update(steps={}), 'state_shape'),
                              (lambda s: s['hashes'].update(extra='x'), 'state_shape'),
                              (lambda s: s.update(version=2), 'state_version'),
                              (lambda s: s.update(version=True), 'state_version'),
                              (lambda s: s.update(format='other'), 'state_version'),
                              (lambda s: s.update(certificate_version=0), 'state_version'),
                              (lambda s: s['premises'].update(a=B), 'state_hash'),
                              (lambda s: s.update(goal=A), 'state_hash')):
            with self.subTest(error=error):
                forged = copy.deepcopy(self.state)
                mutate(forged)
                self.refused_state(forged, error)
                with self.assertRaisesRegex(P.ProofError, error):
                    R.frontier(forged)
        for value in (None, [], 'state', {'steps': []}):
            self.refused_state(value, 'state_shape')

    def test_caller_sequent_is_authoritative_and_bound_by_hashes(self):
        # A self-consistent ledger for another sequent shows its own task card but never binds this caller.
        other = R.start({'if_a': ['implies', A, B], 'a': B}, B)
        self.assertEqual(R.frontier(other)['premises']['a'], B)
        self.refused_state(other, 'sequent_mismatch')
        self.refused_state(self.state, 'sequent_mismatch', premises=dict(MP, extra=C))
        self.refused_state(self.state, 'sequent_mismatch', goal=A)
        self.refused_state(self.state, 'sequent_mismatch', premises=[])
        rebound = copy.deepcopy(self.state)
        rebound['goal'] = A
        rebound['hashes']['goal'] = P._hash(A)
        self.refused_state(rebound, 'sequent_mismatch')
        self.assertEqual(R.frontier(rebound)['goal'], A)

    def test_a_ledger_continued_past_completion_is_refused(self):
        state, results = play(MP, B, cand('premise', 'if_a'), cand('premise', 'a'), cand('implies_elim', 's1', 's2'))
        self.assertTrue(results[-1]['complete'])
        forged = copy.deepcopy(state)
        forged['steps'].append({'id': 's4', 'rule': 'premise', 'args': ['a'], 'formula': None})
        self.refused_state(forged, 'state_after_complete')
        with self.assertRaisesRegex(P.ProofError, 'state_after_complete'):
            R.frontier(forged)

    def test_invalid_sequents_refuse_to_start(self):
        for premises, goal, error in (([], A, 'premises_shape'), ({'': A}, A, 'name'), ({'a': ['atom']}, A, 'formula_shape'),
                                      ({'a': A}, ['bad'], 'formula_shape'), ({'a': True}, A, 'input_type'),
                                      ({'a': A}, ('atom', 'A'), 'input_type')):
            with self.subTest(error=error), self.assertRaisesRegex(P.ProofError, error):
                R.start(premises, goal)
        cycle = []
        cycle.append(cycle)
        with self.assertRaisesRegex(P.ProofError, 'cycle'):
            R.start({'a': cycle}, A)
        forged = copy.deepcopy(R.start(MP, B))
        forged['premises']['a'] = cycle
        self.assertEqual(R.append(MP, B, forged, cand('premise', 'a'))['error'], 'cycle')


class SessionLimits(unittest.TestCase):
    def test_step_limit_is_a_session_refusal_with_the_prefix_intact(self):
        with patch.object(W, 'MAX_STEPS', 2):
            state, results = play(MP, ['and', A, A], cand('premise', 'a'), cand('premise', 'a'))
            self.assertTrue(all(row['valid'] for row in results))
            self.assertEqual((results[-1]['next_id'], results[-1]['frontier']['steps_left']), (None, 0))
            result = R.append(MP, ['and', A, A], state, cand('and_intro', 's1', 's2'))
            self.assertEqual((result['rejected'], result['error']), ('session', 'step_limit'))
            self.assertEqual(result['state'], state)
            self.assertEqual(R.append(MP, ['and', A, A], state, 'malformed')['error'], 'step_limit')
            with patch.object(W, 'MAX_STEPS', 1):
                self.assertEqual(R.append(MP, ['and', A, A], state, cand('premise', 'a'))['error'], 'step_limit')
                self.assertEqual(R.append(MP, ['and', A, A], state, cand('premise', 'a'))['rejected'], 'state')

    def test_candidate_bounds_and_inferred_growth_are_candidate_refusals(self):
        state = R.start({'a': A}, B)
        deep = A
        for _ in range(W.MAX_DEPTH + 2):
            deep = ['and', deep, A]
        cycle = []
        cycle.append(cycle)
        for candidate, error in ((cand('assume', formula=deep), 'depth_limit'),
                                 (cand('assume', formula=['atom', 'x' * (W.MAX_TEXT + 1)]), 'text_limit'),
                                 (cand('assume', formula=['atom', '\ud800']), 'unicode'),
                                 (cand('assume', formula=True), 'input_type'),
                                 (cand('assume', formula=['atom', 1.5]), 'input_type'),
                                 (cand('assume', formula=cycle), 'cycle'),
                                 (cand('premise', *(['a'] * (W.MAX_NODES + 1))), 'node_limit')):
            with self.subTest(error=error):
                result = R.append({'a': A}, B, state, candidate)
                self.assertEqual((result['rejected'], result['error']), ('candidate', error))
                self.assertEqual(result['state'], state)
        rows = [cand('premise', 'a')] + [cand('and_intro', 's%d' % index, 's%d' % index) for index in range(1, 20)]
        state, results = play({'a': A}, B, *rows)
        refused = [row for row in results if not row['valid']]
        self.assertTrue(refused)
        self.assertTrue(all(row['rejected'] == 'candidate' for row in refused))
        self.assertIn(refused[0]['error'], ('node_limit', 'work_limit', 'byte_limit', 'output_limit'))
        self.assertLessEqual(len(json.dumps(R.frontier(state))), 2 * W.MAX_BYTES)

    def test_prefix_output_limit_and_session_refusal(self):
        premises = {'a': ['atom', 'x' * 2000]}
        steps = [step('s%d' % index, 'premise', 'a') for index in range(1, 6)]
        self.assertTrue(W.check_prefix(premises, A, steps)['ok'])
        self.assertEqual(W.check_prefix(premises, A, steps, max_bytes=5000)['error'], 'output_limit')
        state, _ = play(premises, A, *[cand('premise', 'a')] * 4)
        with patch.object(W, 'MAX_BYTES', 9000):
            self.assertEqual(R.frontier(state)['next_id'], 's5')
            result = R.append(premises, A, state, cand('premise', 'a'))
            self.assertEqual((result['rejected'], result['error']), ('candidate', 'output_limit'))
            self.assertEqual(result['state'], state)

    def test_host_budget_ticks_propagate_from_every_entry_point(self):
        class HostBudget(Exception):
            pass
        counts = {}
        for name, call in (('start', lambda tick: R.start(MP, B, tick=tick)),
                           ('frontier', lambda tick: R.frontier(play(MP, B, cand('premise', 'a'))[0], tick=tick)),
                           ('append', lambda tick: R.append(MP, B, play(MP, B, cand('premise', 'a'))[0],
                                                            cand('premise', 'if_a'), tick=tick)),
                           ('complete', lambda tick: R.append(MP, B, play(MP, B, cand('premise', 'if_a'),
                                                                         cand('premise', 'a'))[0],
                                                              cand('implies_elim', 's1', 's2'), tick=tick))):
            ticks = []
            call(lambda ticks=ticks: ticks.append(1))
            counts[name] = len(ticks)
            self.assertGreater(len(ticks), 0, name)
            for limit in sorted({1, len(ticks) // 2 or 1, len(ticks)}):
                seen = []

                def exhausted(seen=seen, limit=limit):
                    seen.append(1)
                    if len(seen) >= limit:
                        raise HostBudget()
                with self.subTest(name=name, limit=limit), self.assertRaises(HostBudget):
                    call(exhausted)
        # Completion re-runs the existing verifier on the final certificate.
        self.assertGreater(counts['complete'], counts['append'])

    def test_work_limit_refuses_without_partial_acceptance(self):
        state, _ = play(MP, B, cand('premise', 'if_a'))
        for limit in (1, 20, 40):
            with self.subTest(limit=limit), patch.object(W, 'MAX_WORK', limit):
                result = R.append(MP, B, state, cand('premise', 'a'))
                self.assertFalse(result['valid'])
                self.assertEqual(result['error'], 'work_limit')
                self.assertIsNone(result['step'])
                self.assertEqual(result['state'], None if result['rejected'] == 'state' else state)


class PrefixAgreement(unittest.TestCase):
    """check_prefix and sessions agree with verify; accepted sessions pass the independent nested checker."""

    def certificates(self):
        rows = [
            ({'if_a': ['implies', A, B], 'a': A}, B,
             certificate(step('p', 'premise', 'if_a'), step('q', 'premise', 'a'), step('r', 'implies_elim', 'p', 'q'))),
            ({}, ['and', ['implies', A, A], ['implies', A, A]],
             certificate(step('h', 'assume', formula=A), step('i', 'implies_intro', 'h', 'h'),
                         step('out', 'and_intro', 'i', 'i'))),
            ({}, ['implies', A, ['implies', A, A]],
             certificate(step('h', 'assume', formula=A), step('i', 'implies_intro', 'h', 'h'),
                         step('out', 'implies_intro', 'h', 'i'))),
            ({'choice': ['or', A, B], 'ac': ['implies', A, C], 'bc': ['implies', B, C]}, C,
             certificate(step('d', 'premise', 'choice'), step('ac', 'premise', 'ac'), step('bc', 'premise', 'bc'),
                         step('a', 'assume', formula=A), step('ca', 'implies_elim', 'ac', 'a'),
                         step('b', 'assume', formula=B), step('cb', 'implies_elim', 'bc', 'b'),
                         step('out', 'or_elim', 'd', 'a', 'ca', 'b', 'cb'))),
            ({'a': A, 'unused': C}, ['implies', B, A],
             certificate(step('p', 'premise', 'a'), step('h', 'assume', formula=B), step('u', 'assume', formula=C),
                         step('up', 'premise', 'unused'), step('out', 'implies_intro', 'h', 'p'))),
            ({'choice': ['or', A, B], 'c': C}, C,
             certificate(step('d', 'premise', 'choice'), step('c', 'premise', 'c'), step('l', 'assume', formula=A),
                         step('r', 'assume', formula=B), step('out', 'or_elim', 'd', 'l', 'c', 'r', 'c'))),
            ({'absurd': F}, C, certificate(step('f', 'premise', 'absurd'), step('out', 'false_elim', 'f', formula=C))),
        ]
        formulas = [A, B, F] + [[op, A, B] for op in ('and', 'or', 'implies')]
        for left, right in itertools.product(formulas, repeat=2):
            rows.append(({'d': ['or', left, right]}, ['or', right, left], certificate(
                step('d', 'premise', 'd'), step('l', 'assume', formula=left),
                step('left', 'or_right', 'l', formula=right), step('r', 'assume', formula=right),
                step('right', 'or_left', 'r', formula=left), step('out', 'or_elim', 'd', 'l', 'left', 'r', 'right'))))
        return rows

    def renamed(self, cert):
        """The certificate's lines under host IDs s1, s2, ... (premise names are not step IDs)."""
        names = {row['id']: 's' + str(index + 1) for index, row in enumerate(cert['steps'])}
        return [step(names[row['id']], row['rule'], *(row['args'] if row['rule'] == 'premise' else
                                                      [names[arg] for arg in row['args']]), formula=row['formula'])
                for row in cert['steps']], names

    def test_existing_accepted_certificates_replay_one_inference_at_a_time(self):
        for premises, goal, cert in self.certificates():
            self.assertTrue(W.verify(premises, goal, cert)['ok'])
            rows, names = self.renamed(cert)
            lines = W.check_prefix(premises, goal, rows)['lines']
            first = next(index for index, line in enumerate(lines) if not line['free'] and line['formula'] == goal)
            state, results = play(premises, goal, *[cand(row['rule'], *row['args'], formula=row['formula'])
                                                    for row in rows])
            with self.subTest(goal=goal):
                # The session ends at the first closed goal line and refuses every later line.
                self.assertTrue(all(row['valid'] for row in results[:first + 1]))
                self.assertTrue(all(row['error'] == 'session_complete' for row in results[first + 1:]))
                final = results[first]
                self.assertTrue(final['complete'])
                self.assertTrue(all(not row['complete'] for row in results[:first]))
                self.assertEqual(final['certificate'], certificate(*rows[:first + 1]))
                self.assertEqual(final['receipt'], W.verify(premises, goal, final['certificate']))
                if first == len(rows) - 1:
                    self.assertEqual(final['certificate']['result'], names[cert['result']])
                    self.assertEqual(final['receipt']['used_premises'], W.verify(premises, goal, cert)['used_premises'])
                independent = P.verify(premises, goal, nested(final['certificate'], premises))
                self.assertTrue(independent['ok'], independent)
                self.assertEqual(state, final['state'])

    def test_check_prefix_matches_verify_inference_errors_and_counts(self):
        premises = {'a': A, 'b': B, 'f': ['implies', A, C]}
        initial = [step('a', 'premise', 'a'), step('b', 'premise', 'b'), step('f', 'premise', 'f')]
        candidates = [step('out', op, ref) for op in ('and_left', 'and_right') for ref in ('a', 'b', 'f', 'zz')]
        candidates += [step('out', op, left, right) for op in ('implies_elim', 'and_intro')
                       for left in ('a', 'b', 'f') for right in ('a', 'b', 'f', 'out')]
        candidates += [step('out', 'assume', formula=value) for value in (A, ['bad'], None)]
        for row in candidates:
            steps = initial + [row]
            prefix = W.check_prefix(premises, C, steps)
            for goal in (A, C, ['and', A, B]):
                whole = W.verify(premises, goal, {'version': 1, 'steps': steps, 'result': 'out'})
                if prefix['ok']:
                    last = prefix['lines'][-1]
                    self.assertEqual(whole['ok'], not last['free'] and last['formula'] == goal)
                    self.assertEqual(prefix['checks'], whole['checks'])
                else:
                    self.assertFalse(whole['ok'])
                    self.assertEqual((prefix['error'], prefix.get('rejected_step')),
                                     (whole['error'], whole.get('rejected_step')))
        empty = W.check_prefix(premises, C, [])
        self.assertEqual((empty['ok'], empty['lines'], empty['checks']), (True, [], 0))
        self.assertEqual(W.check_prefix([], C, [])['error'], 'premises_shape')
        with patch.object(W, 'MAX_STEPS', 1):
            self.assertEqual(W.check_prefix(premises, C, initial)['error'], 'step_limit')
        result = W.check_prefix(premises, C, initial)
        result['lines'][0]['formula'][1] = 'changed'
        self.assertEqual(premises['a'], A)
        json.dumps(result)

    def walk(self, rng, premises, count):
        """Mostly well-formed random candidates built from the shown lines; a test oracle, not session search."""
        pool = [A, B, C, F, ['and', A, B], ['or', A, B], ['implies', A, B], ['implies', B, C]]
        goal = ['atom', 'An unreached test goal']
        state, accepted, lines, rows = R.start(premises, goal), [], [], []
        for _ in range(count):
            ids = [line['id'] for line in lines]
            pick = lambda test=lambda line: True: [line['id'] for line in lines if test(line)]
            choices = [cand('premise', rng.choice(list(premises)))] if premises else []
            choices.append(cand('assume', formula=rng.choice(pool)))
            if ids:
                choices += [cand('and_intro', rng.choice(ids), rng.choice(ids)),
                            cand(rng.choice(('or_left', 'or_right')), rng.choice(ids), formula=rng.choice(pool))]
                assumed = pick(lambda line: line['rule'] == 'assume')
                if assumed:
                    choices.append(cand('implies_intro', rng.choice(assumed), rng.choice(ids)))
                pairs = pick(lambda line: line['formula'][0] == 'and')
                if pairs:
                    choices.append(cand(rng.choice(('and_left', 'and_right')), rng.choice(pairs)))
                for line in lines:
                    if line['formula'][0] == 'implies':
                        matches = pick(lambda other, line=line: other['formula'] == line['formula'][1])
                        if matches:
                            choices.append(cand('implies_elim', line['id'], rng.choice(matches)))
                    if line['formula'] == F:
                        choices.append(cand('false_elim', line['id'], formula=rng.choice(pool)))
                    if line['formula'][0] == 'or':
                        left = pick(lambda other, line=line: other['rule'] == 'assume' and other['formula'] == line['formula'][1])
                        right = pick(lambda other, line=line: other['rule'] == 'assume' and other['formula'] == line['formula'][2])
                        if left and right:
                            choices.append(cand('or_elim', line['id'], rng.choice(left), rng.choice(ids),
                                                rng.choice(right), rng.choice(ids)))
            if rng.random() < 0.25:
                rule = rng.choice(list(W.ARITIES))
                refs = ids + ['s' + str(len(ids) + 1), 'zz'] + list(premises)
                candidate = cand(rule, *[rng.choice(refs) for _ in range(W.ARITIES[rule])],
                                 formula=rng.choice(pool + [None, ['bad']]))
            else:
                candidate = rng.choice(choices)
            result = R.append(premises, goal, state, candidate)
            expected = W.check_prefix(premises, goal, accepted + [dict(candidate, id='s' + str(len(accepted) + 1))])
            self.assertEqual(result['valid'], expected['ok'], (accepted, candidate, result['error'], expected))
            self.assertFalse(result['complete'])
            if result['valid']:
                self.assertEqual(result['line'], dict(expected['lines'][-1], free=result['line']['free']))
                self.assertEqual(sorted(result['line']['free']), expected['lines'][-1]['free'])
                state, lines = result['state'], lines + [result['line']]
                accepted.append(result['step'])
                rows.append(candidate)
            else:
                self.assertEqual((result['rejected'], result['error']), ('candidate', expected['error']))
                self.assertEqual(result['state'], state)
        return rows, lines

    def test_generated_sessions_agree_with_prefix_checker_verify_and_boolean_oracle(self):
        rng = random.Random(20261004)
        sequents = [{'a': A, 'f': ['implies', A, B]}, {'d': ['or', A, B]}, {}, {'p': ['and', A, B]}, {'x': F},
                    {'a': A, 'b': B}, {'g': ['implies', B, C], 'f': ['implies', A, B]}]
        completed = 0
        for _ in range(250):
            premises = rng.choice(sequents)
            rows, lines = self.walk(rng, premises, rng.randint(1, 9))
            closed = [index for index, line in enumerate(lines) if not line['free']]
            if not closed:
                continue
            goal = lines[rng.choice(closed)]['formula']
            first = next(index for index, line in enumerate(lines) if not line['free'] and line['formula'] == goal)
            state, results = play(premises, goal, *rows)
            self.assertTrue(all(row['valid'] and not row['complete'] for row in results[:first]))
            final = results[first]
            self.assertTrue(final['valid'] and final['complete'], final)
            self.assertTrue(all(row['error'] == 'session_complete' for row in results[first + 1:]))
            self.assertEqual(final['receipt'], W.verify(premises, goal, final['certificate']))
            self.assertTrue(final['receipt']['ok'])
            self.assertTrue(P.verify(premises, goal, nested(final['certificate'], premises))['ok'])
            for values in itertools.product((False, True), repeat=3):
                valuation = dict(zip('ABC', values))
                if all(truth(value, valuation) for value in premises.values()):
                    self.assertTrue(truth(goal, valuation))
            completed += 1
        self.assertGreater(completed, 100)


class NativeBridge(unittest.TestCase):
    def setUp(self):
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)
        process = patch('subprocess.Popen', side_effect=AssertionError('no external process in session tests'))
        process.start()
        self.addCleanup(process.stop)

    def test_entry_points_versions_and_language_value_round_trip(self):
        self.assertTrue(set(NAMES) <= set(adapter.FUNCTIONS))
        self.assertEqual(adapter.VERSION, 4)
        self.assertEqual(S.kernel_id()['proof'], adapter.VERSION)
        self.assertEqual(S.kernel_id()['proof_steps'], W.VERSION)
        kernel, node = S.Kernel(), S.Node('call', 1, 1)
        state = adapter.proof_session_start(kernel, node, S.from_json(MP), S.from_json(B))
        self.assertIsInstance(state['steps'], tuple)
        self.assertEqual(adapter.proof_session_frontier(kernel, node, state), S.from_json(R.frontier(R.start(MP, B))))
        for candidate in (cand('premise', 'if_a'), cand('premise', 'a'), cand('implies_elim', 's1', 's2')):
            result = adapter.proof_session_append(kernel, node, S.from_json(MP), S.from_json(B), state,
                                                  S.from_json(candidate))
            self.assertTrue(result['valid'], result)
            state = result['state']
        self.assertTrue(result['complete'])
        pure = R.append(MP, B, R.start(MP, B), cand('premise', 'if_a'))
        self.assertEqual(adapter.proof_session_append(kernel, node, S.from_json(MP), S.from_json(B),
                                                      S.from_json(R.start(MP, B)),
                                                      S.from_json(cand('premise', 'if_a'))), S.from_json(pure))
        checked = adapter.proof_steps_check(kernel, node, S.from_json(MP), S.from_json(B), result['certificate'])
        self.assertTrue(checked['valid'])

    def test_unrepresentable_candidate_values_are_finite_refusals_not_run_errors(self):
        kernel, node = S.Kernel(), S.Node('call', 1, 1)
        state = adapter.proof_session_start(kernel, node, S.from_json(MP), S.from_json(B))
        deep = ('atom', 'A')
        for _ in range(W.MAX_DEPTH + 3):
            deep = (deep,)
        for formula, error in ((True, 'input_type'), (False, 'input_type'), (Fraction(1, 2), 'input_type'),
                               (frozenset({1}), 'input_type'), (deep, 'depth_limit'), (Fraction(4, 1), 'input_type')):
            with self.subTest(error=error, formula=type(formula).__name__):
                result = adapter.proof_session_append(kernel, node, S.from_json(MP), S.from_json(B), state,
                                                      {'rule': 'assume', 'args': (), 'formula': formula})
                self.assertEqual((result['valid'], result['rejected'], result['error']), (False, 'candidate', error))
                self.assertEqual(result['state'], state)
        result = adapter.proof_session_append(kernel, node, S.from_json(MP), S.from_json(B), state,
                                              {'rule': 'assume', 'args': (), 'formula': Fraction(1, 1)})
        self.assertEqual(result['error'], 'formula_shape')

    def test_invalid_start_or_frontier_is_a_check_error_and_host_budget_raises(self):
        kernel, node = S.Kernel(), S.Node('call', 1, 1)
        with self.assertRaisesRegex(S.SymblicError, 'proof session: formula_shape') as raised:
            adapter.proof_session_start(kernel, node, S.from_json(MP), ('bad',))
        self.assertEqual(raised.exception.kind, 'check')
        forged = S.from_json(dict(R.start(MP, B), version=2))
        with self.assertRaisesRegex(S.SymblicError, 'proof session: state_version'):
            adapter.proof_session_frontier(kernel, node, forged)
        result = adapter.proof_session_append(kernel, node, S.from_json(MP), S.from_json(B), forged,
                                              S.from_json(cand('premise', 'a')))
        self.assertEqual((result['rejected'], result['error'], result['state']), ('state', 'state_version', None))
        shared = ['atom', 'A']
        for _ in range(12):
            shared = ['and', shared, shared]
        for call in (lambda k: adapter.proof_session_start(k, node, {'a': shared}, S.from_json(A)),
                     lambda k: adapter.proof_session_frontier(k, node, S.from_json(R.start(MP, B))),
                     lambda k: adapter.proof_session_append(k, node, S.from_json(MP), S.from_json(B),
                                                           S.from_json(R.start(MP, B)), S.from_json(cand('premise', 'a')))):
            budget = S.Kernel(budget=S.Budget(40))
            with self.assertRaisesRegex(S.SymblicError, 'budget'):
                call(budget)
            self.assertLess(budget.budget.left, 0)

    def test_kernel_program_threads_state_without_model_calls(self):
        source = ('use profile=verified.\ngiven premises: Any.\ngiven goal: Any.\n'
                  'given c1: Any.\ngiven c2: Any.\ngiven bad: Any.\ngiven c3: Any.\n'
                  'let s0 = proof_session_start(premises, goal).\n'
                  'let a1 = proof_session_append(premises, goal, s0, c1).\n'
                  'let a2 = proof_session_append(premises, goal, a1.state, c2).\n'
                  'let refused = proof_session_append(premises, goal, a2.state, bad).\n'
                  'assert not refused.valid and refused.state = a2.state and refused.error = "implies_elim_mismatch".\n'
                  'let a3 = proof_session_append(premises, goal, refused.state, c3).\n'
                  'assert a3.complete and a3.receipt.ok.\n'
                  'let verification = proof_steps_check(premises, goal, a3.certificate).\n'
                  'assert verification.valid.\n'
                  'let card = proof_session_frontier(a2.state).\n'
                  'assert card.next_id = "s3" and len(card.lines) = 2.\n')
        inputs = {'premises': MP, 'goal': B, 'c1': cand('premise', 'if_a'), 'c2': cand('premise', 'a'),
                  'bad': cand('implies_elim', 's2', 's1'), 'c3': cand('implies_elim', 's1', 's2')}
        with registered(), patch.object(S.KB, 'derive', side_effect=AssertionError('no proof search')):
            report = embed.run(source, inputs=inputs)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)

    def test_fresh_context_ask_ensure_loop_repairs_one_inference_at_a_time(self):
        def block(index, prior):
            card = 'proof_session_frontier(s0)' if index == 1 else f'a{index - 1}.frontier'
            return (f'let f{index} = {card}.\n'
                    f'ask c{index}: {R.CANDIDATE_TYPE} "Propose exactly one next inference for frontier. '
                    f'Follow proof_rules." from f{index}, proof_rules with effort=low, route=escalate, retries=2\n'
                    f'let a{index} = proof_session_append(premises, goal, {prior}, c{index}).\n'
                    f'ensure a{index}.valid else retry because "Propose one inference the checker accepts.".\n')
        source = ('program Construct a derivation one inference at a time.\nuse profile=verified.\n'
                  'given premises: Any.\ngiven goal: Any.\ngiven proof_rules: Any.\n'
                  'let s0 = proof_session_start(premises, goal).\n'
                  + block(1, 's0') + block(2, 'a1.state') + block(3, 'a2.state')
                  + 'assert a3.complete.\nlet verification = proof_steps_check(premises, goal, a3.certificate).\n'
                    'assert verification.valid.\nshow verification.\n')
        marker = 'A rejected marker proposition'
        answers = [cand('implies_intro', 's9', 's1', formula=['atom', marker]), cand('premise', 'if_a'),
                   cand('premise', 'a'), cand('implies_elim', 's1', 's2')]

        class Apps:
            def __init__(self):
                self.requests = []

            def call(self, request):
                self.requests.append(request)
                return {'ok': True, 'json': {'answer': copy.deepcopy(answers[len(self.requests) - 1])}}
        apps = Apps()
        inputs = {'premises': MP, 'goal': B, 'proof_rules': R.rules()}
        with registered(), patch.object(S.KB, 'derive', side_effect=AssertionError('checker must not search')):
            self.assertTrue(S.check(source, execution_profile='verified')['ok'])
            report = Run(source, inputs, apps, {'profile': 'verified', 'max_calls': 4, 'parallel': 1,
                                                'by': 'fake:constructor'}).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual((report['calls'], len(apps.requests)), (4, 4))
        verification = next(row['value'] for row in report['bindings'] if row['name'] == 'verification')
        self.assertTrue(verification['valid'])
        self.assertEqual(verification['format'], W.FORMAT)
        for request in apps.requests:
            fields = request['schema']['properties']['answer']
            self.assertEqual(set(fields['properties']), {'rule', 'args', 'formula'})
            self.assertEqual(fields['properties']['rule']['enum'], list(W.ARITIES))
            self.assertFalse(fields['additionalProperties'])
        # The repair re-asks the same inference; later asks see only their own task card.
        self.assertIn(marker, apps.requests[1]['prompt'])
        for request in apps.requests[2:]:
            self.assertNotIn(marker, request['prompt'])
        self.assertIn('"next_id": "s2"', apps.requests[2]['prompt'])
        self.assertNotIn('"s3"', apps.requests[2]['prompt'])
        self.assertNotIn('implies_elim", "args": ["s1", "s2"]', apps.requests[0]['prompt'])
        # A shared call budget too small for every inference fails rather than accepting a partial proof.
        apps = Apps()
        with registered():
            report = Run(source, inputs, apps, {'profile': 'verified', 'max_calls': 3, 'parallel': 1,
                                                'by': 'fake:constructor'}).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('verification', [row['name'] for row in report['bindings']])


if __name__ == '__main__':
    unittest.main()
