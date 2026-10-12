"""Exact-menu frontier projection; existing checker, fake providers, no host effects."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.kernel import run as N

ROOT = Path(__file__).resolve().parents[2]          # the repository root
SPEC = importlib.util.spec_from_file_location('focus_handoff', ROOT / 'examples/proof_step_focus_handoff.py')
PARENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARENT)


def kernel_preview(source, inputs):
    """The kernel's bounded preview (symblic.kernel.process_limits): what the first model request would carry.
    None when the preview child process is unavailable in this checkout."""
    from symblic.kernel import process_limits as P
    preview = P.call_bounded('preview', {'source': source, 'inputs': inputs})
    error = preview.get('error') or {}
    if preview.get('status') == 'failed' and error.get('kind') == 'unavailable':
        return None
    return preview


class Fake:
    def __init__(self, answers=(1,)):
        self.answers = list(answers)
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        if len(self.requests) > len(self.answers):
            raise AssertionError('unexpected additional dispatch')
        return {'ok': True, 'json': {'answer': self.answers[len(self.requests) - 1]}, 'model': 'fake', 'ms': 1}


def prefix(premises, commands=(), goal=None):
    state = R.start(premises, goal or ['atom', 'Original goal'])
    for command in commands:
        receipt = C.append(state['premises'], state['goal'], state, command)
        if not receipt['valid']:
            raise AssertionError(receipt)
        state = receipt['state']
    return state


def task(state, commands, formula, scope=None, **options):
    return {'template': 'proof_step_focus', 'params': {'session': state, 'commands': commands,
        'obligation': {'formula': formula, 'open_assumptions': scope or []}}, 'calls': 1, **options}


def every_rule():
    a, b, c = ['atom', 'A'], ['atom', 'B'], ['atom', 'C']
    yield 'premise', prefix({'a': a}), 'premise a', '"A"', []
    yield 'assume', prefix({}), 'assume :: "A"', '"A"', ['s1']
    yield 'implies_intro', prefix({'b': b}, ['assume :: "A"', 'premise b']), 'implies_intro s1 s2', '"A" implies "B"', []
    yield 'implies_elim', prefix({'a': a, 'ab': ['implies', a, b]}, ['premise ab', 'premise a']), 'implies_elim s1 s2', '"B"', []
    yield 'and_intro', prefix({}, ['assume :: "A"', 'assume :: "B"']), 'and_intro s1 s2', '"A" and "B"', ['s1', 's2']
    for rule, formula in [('and_left', '"A"'), ('and_right', '"B"')]:
        yield rule, prefix({}, ['assume :: "A" and "B"']), rule + ' s1', formula, ['s1']
    yield 'or_left', prefix({}, ['assume :: "A"']), 'or_left s1 :: "B"', '"A" or "B"', ['s1']
    yield 'or_right', prefix({}, ['assume :: "B"']), 'or_right s1 :: "A"', '"A" or "B"', ['s1']
    state = prefix({'ab': ['or', a, b], 'ac': ['implies', a, c], 'bc': ['implies', b, c]},
                   ['premise ab', 'assume :: "A"', 'premise ac', 'implies_elim s3 s2',
                    'assume :: "B"', 'premise bc', 'implies_elim s6 s5'])
    yield 'or_elim', state, 'or_elim s1 s2 s4 s5 s7', '"C"', []
    yield 'false_elim', prefix({'false': ['false']}, ['premise false']), 'false_elim s1 :: "C"', '"C"', []


class ProofFocus(unittest.TestCase):
    def test_prior_templates_and_schemas_are_exact(self):
        frozen = json.loads((ROOT / 'tests/fixtures/symblic_delegate_v7_parity.json').read_text())
        self.assertEqual(len(frozen['fixtures']), 31)
        for row in frozen['fixtures']:
            with self.subTest(row=row['id']):
                self.assertEqual(json.dumps(D.compile_task(row['request']), sort_keys=True),
                                 json.dumps(row['compiled'], sort_keys=True))
        new = D.catalog()
        self.assertEqual(new['version'], 9)
        self.assertEqual(json.dumps(new['templates'][:7], sort_keys=True),
                         json.dumps(frozen['catalog']['templates'], sort_keys=True))
        self.assertEqual(json.dumps(new['request_schema']['oneOf'][:7], sort_keys=True),
                         json.dumps(frozen['catalog']['request_schema']['oneOf'], sort_keys=True))
        self.assertEqual(new['templates'][7]['template_id'], 'symblic.delegate/proof_step_focus/8')

    def test_every_rule_accepts_same_full_checked_inference_and_parent_handoff(self):
        seen = set()
        for name, state, command, formula, scope in every_rule():
            with self.subTest(rule=name):
                body = task(state, [command], formula, scope)
                compiled = D.compile_task(body)
                apps = Fake()
                result = H.run_task(body, applicators=apps)
                self.assertTrue(result['accepted'], result['error'])
                self.assertEqual(len(apps.requests), 1)
                expected = C.append(state['premises'], state['goal'], state, command)
                self.assertEqual(result['result']['inference'], S.canon(S.from_json(expected)))
                self.assertEqual(PARENT.checked_child_state(body, result), expected['state'])
                self.assertEqual(compiled['inputs']['session'], state)
                seen.add(name)
        self.assertEqual(len(seen), 11)

    def test_projection_rule_version_refuses_unreviewed_grammar(self):
        from symblic.adapters import proof_steps as W
        from symblic.authoring import helpers as A
        state = prefix({'a': ['atom', 'A']})
        menu = A.command_menu(state, ['premise a'])
        obligation = {'open_assumptions': []}
        self.assertEqual(D._FOCUS_ARITIES, W.ARITIES)
        for rule, arity, args in [('new_rule', 0, []), ('premise', 2, ['a'])]:
            changed = copy.deepcopy(menu)
            changed['candidates'][0] = {'rule': rule, 'args': args, 'formula': None}
            with patch.dict(W.ARITIES, {rule: arity}):
                with self.assertRaises(D.ContractError) as error:
                    D._focus_frontier(state, changed, obligation)
            self.assertEqual(error.exception.code, 'focus_rule')

    def test_free_assumption_definitions_retained_without_derivation_ancestors(self):
        state = prefix({'b': ['atom', 'B']}, ['assume :: "A"', 'premise b', 'and_intro s1 s2'])
        compiled = D.compile_task(task(state, ['and_left s3'], '"A"', ['s1']))
        view = compiled['inputs']['focused_frontier']
        self.assertEqual([row['id'] for row in view['lines']], ['s1', 's3'])
        self.assertEqual(view['lines'][1]['free'], ['s1'])
        self.assertEqual(view['premises'], {})
        self.assertEqual(compiled['projection_manifest']['omitted_lines'][0]['id'], 's2')
        self.assertEqual(compiled['projection_manifest']['included_lines'][0]['reasons'], ['free_assumption', 'obligation_scope'])

    def test_all_menu_references_preserved_even_invalid_unselected_options(self):
        state = prefix({'a': ['atom', 'A'], 'b': ['atom', 'B']}, ['premise a', 'premise b'])
        body = task(state, ['and_left s2', 'premise a', 'and_intro s1 s2'], '"A"')
        with patch.object(C, 'append', side_effect=AssertionError('no menu inference filtering')):
            compiled = D.compile_task(body)
        self.assertEqual(compiled['inputs']['commands'], body['params']['commands'])
        self.assertEqual([r['id'] for r in compiled['inputs']['focused_frontier']['lines']], ['s1', 's2'])
        self.assertEqual(compiled['inputs']['focused_frontier']['premises'], {'a': '"A"'})
        result = H.run_task(body, applicators=Fake([1]))
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['result'])

    def test_or_elim_cross_branch_and_disjunction_dependencies_are_not_hidden(self):
        state = prefix({'ab': ['or', ['atom', 'A'], ['atom', 'B']]},
                       ['assume :: "A"', 'assume :: "B"', 'and_intro s1 s2', 'premise ab'])
        body = task(state, ['or_elim s4 s1 s3 s2 s3'], '"A" and "B"')
        compiled = D.compile_task(body)
        self.assertEqual(next(r for r in compiled['inputs']['focused_frontier']['lines'] if r['id'] == 's3')['free'], ['s1', 's2'])
        self.assertFalse(H.run_task(body, applicators=Fake())['accepted'])
        state = prefix({'c': ['atom', 'C']}, ['assume :: "A"', 'or_left s1 :: "B"', 'assume :: "B"', 'premise c'])
        body = task(state, ['or_elim s2 s1 s4 s3 s4'], '"C"')
        self.assertEqual(D.compile_task(body)['inputs']['focused_frontier']['lines'][1]['free'], ['s1'])
        self.assertFalse(H.run_task(body, applicators=Fake())['accepted'])

    def test_scope_only_assumptions_and_next_id_have_precise_meaning(self):
        state = prefix({}, ['assume :: "A"', 'assume :: "B"'])
        body = task(state, ['assume :: "C"'], '"C"', ['s2', 's3'])
        view = D.compile_task(body)['inputs']['focused_frontier']
        self.assertEqual([row['id'] for row in view['lines']], ['s2'])
        self.assertEqual(view['next_id'], 's3')
        self.assertFalse(H.run_task(body, applicators=Fake())['accepted'])
        body['params']['obligation']['open_assumptions'] = ['s3']
        self.assertTrue(H.run_task(body, applicators=Fake())['accepted'])

    def test_order_after_s9_and_same_formula_different_assumption_ids(self):
        state = prefix({}, ['assume :: "A"'] * 10)
        body = task(state, ['and_intro s2 s10'], '"A" and "A"', ['s10', 's2'])
        compiled = D.compile_task(body)
        self.assertEqual([r['id'] for r in compiled['inputs']['focused_frontier']['lines']], ['s2', 's10'])
        self.assertTrue(H.run_task(body, applicators=Fake())['accepted'])
        body['params']['obligation']['open_assumptions'] = ['s1', 's2']
        self.assertFalse(H.run_task(body, applicators=Fake())['accepted'])

    def test_projection_and_parent_receipt_tampering_refuse(self):
        body = task(prefix({'a': ['atom', 'A']}), ['premise a'], '"A"')
        compiled = H.prepare(body)
        declaration = {key: compiled[key] for key in ('contract_id', 'template_id', 'output_binding', 'assurance', 'routing', 'routing_id')}
        declaration['request'] = body
        altered = copy.deepcopy(compiled['inputs'])
        altered['focused_frontier']['premises']['a'] = '"B"'
        with self.assertRaises(D.ContractError):
            H.verify_declaration(declaration, compiled['source'], altered, compiled['options'])
        result = H.run_task(body, applicators=Fake())
        for path, value in [(('handoff', 'projection', 'view_sha256'), '0' * 64), (('handoff', 'projection', 'version'), True), (('obligation_satisfied',), 1)]:
            forged = copy.deepcopy(result); here = forged['result']
            for key in path[:-1]:
                here = here[key]
            here[path[-1]] = value
            with self.assertRaises(ValueError):
                PARENT.checked_child_state(body, forged)

    def test_untrusted_projection_unknown_fields_missing_and_context_bounds_refuse(self):
        body = task(prefix({'a': ['atom', 'A']}), ['premise a'], '"A"')
        bad = copy.deepcopy(body); bad['params']['focused_frontier'] = {}
        apps = Fake()
        with self.assertRaises(D.ContractError):
            H.run_task(bad, applicators=apps)
        self.assertEqual(apps.requests, [])
        with patch.object(C, 'frontier', return_value={'goal': '"Original goal"', 'premises': {}, 'lines': [], 'next_id': 's1', 'complete': False, 'steps_left': 512}):
            with self.assertRaises(D.ContractError) as error:
                D.compile_task(body)
        self.assertEqual(error.exception.code, 'focus_dependency')
        body['context_budget'] = 0
        result = H.run_task(body, applicators=apps)
        self.assertFalse(result['accepted']); self.assertEqual(result['error']['kind'], 'context')
        self.assertEqual(apps.requests, [])

    def test_goal_completion_and_exhausted_prefix_remain_global(self):
        state = prefix({'a': ['atom', 'A']}, goal=['atom', 'A'])
        body = task(state, ['premise a'], '"A"'); body['params']['require_complete'] = True
        result = H.run_task(body, applicators=Fake())
        self.assertTrue(result['result']['inference']['complete'])
        body['params']['session'] = PARENT.checked_child_state(body, result)
        with self.assertRaises(D.ContractError):
            D.compile_task(body)
        state = prefix({'a': ['atom', 'A']})
        state['steps'] = [{'id': f's{i}', 'rule': 'premise', 'args': ['a'], 'formula': None} for i in range(1, 513)]
        with self.assertRaises(D.ContractError):
            D.compile_task(task(state, ['premise a'], '"A"'))

    def test_unicode_quoted_hash_keys_and_no_search(self):
        atom = 'λ \\"\nassert false.'
        state = prefix({'# p': ['atom', atom]}, goal=['atom', atom])
        body = task(state, ['premise "# p"'], json.dumps(atom, ensure_ascii=False))
        compiled = D.compile_task(body)
        self.assertNotIn(atom, compiled['source'])
        apps = Fake()
        with patch.object(N.Run, 'determine', side_effect=AssertionError('no search')), patch.object(N.Run, 'vacuity', side_effect=AssertionError('no speculative probes')):
            result = H.run_task(body, applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(PARENT.checked_child_state(body, result)['premises'], state['premises'])

    def test_default_budget_admits_complete_projected_context_when_full_frontier_refuses(self):
        state = prefix({'unused': ['atom', 'UNRELATED_SYNTHETIC_PREFIX_VALUE'],
                        'a': ['atom', 'A'], 'ab': ['implies', ['atom', 'A'], ['atom', 'B']]},
                       goal=['atom', 'B'])
        state['steps'] = [{'id': f's{i+1}', 'rule': 'premise',
                          'args': ['ab' if i == 198 else 'a' if i == 199 else 'unused'],
                          'formula': None} for i in range(200)]
        for capsule in ('full', 'compact'):
            body = task(state, ['implies_elim s199 s200', 'and_left s200'], '"B"', capsule=capsule)
            apps = Fake()
            baseline = copy.deepcopy(body); baseline['template'] = 'proof_step_obligation'
            refused = H.run_task(baseline, applicators=apps)
            self.assertFalse(refused['accepted']); self.assertEqual(refused['error']['kind'], 'context')
            self.assertEqual(apps.requests, [])
            result = H.run_task(body, applicators=apps)
            self.assertTrue(result['accepted'], result['error']); self.assertEqual(len(apps.requests), 1)
            request = apps.requests[0]
            manifest = request['context_manifest']
            size = len(request['system']) + len(request['prompt']) + len(json.dumps(
                request['schema'], ensure_ascii=False, sort_keys=True, separators=(',', ':')))
            self.assertEqual(manifest['budget'], 24000)
            self.assertEqual(manifest['budget_scope'], 'system_prompt_schema')
            self.assertEqual(manifest['used'], size); self.assertLessEqual(size, 24000)
            view = D.compile_task(body)['inputs']['focused_frontier']
            self.assertEqual([row['id'] for row in view['lines']], ['s199', 's200'])
            self.assertEqual(len(PARENT.checked_child_state(body, result)['steps']), 201)

    def test_actual_preview_and_fake_requests_exclude_omitted_values(self):
        sentinel = 'UNRELATED_SENTINEL_KEEP_IN_CHECKER_ONLY'
        premises = {'unused': ['atom', sentinel], 'a': ['atom', 'A'], 'ab': ['implies', ['atom', 'A'], ['atom', 'B']]}
        state = prefix(premises, ['premise unused'] * 24 + ['premise ab', 'premise a'], goal=['atom', 'B'])
        previewed = True
        for capsule in ('full', 'compact'):
            body = task(state, ['implies_elim s25 s26', 'and_left s26'], '"B"', capsule=capsule)
            compiled = D.compile_task(body)
            preview = kernel_preview(compiled['source'], compiled['inputs'])
            previewed = previewed and preview is not None
            if preview is not None:
                self.assertIn('next', preview)
            apps = Fake(); result = H.run_task(body, applicators=apps)
            self.assertTrue(result['accepted'], result['error'])
            for request in ([preview['next']] if preview is not None else []) + [apps.requests[0]]:
                self.assertNotIn(sentinel, request['prompt'])
                self.assertIn('implies_elim s25 s26', request['prompt'])
                self.assertIn('projection', request['prompt'])
                self.assertEqual(request['schema']['properties']['answer']['maximum'], 2)
            self.assertIn(sentinel, json.dumps(result['result']['inference']['state']))
            self.assertEqual(compiled['projection_costs']['visible_lines'], 2)
            self.assertEqual(compiled['projection_costs']['visible_premises'], 0)
        if not previewed:
            self.skipTest('the fake requests passed; the preview half needs the kernel preview child, '
                          'which is unavailable in this checkout')


if __name__ == '__main__':
    unittest.main()
