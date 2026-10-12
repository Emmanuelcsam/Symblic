"""Exact intermediate proof obligations, caller-owned scope, fake providers only."""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W
from symblic.kernel import run as N
from tests.delegate.test_symblic_delegate_proof_step import Fake, PREMISES, GOAL, prefix, request as step_request

EXAMPLE = Path(__file__).resolve().parents[2] / 'examples/proof_step_obligation_handoff.py'
SPEC = importlib.util.spec_from_file_location('proof_obligation_handoff_example', EXAMPLE)
HANDOFF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HANDOFF)


def request(formula='"B"', *, scope=None, **options):
    task = step_request(**options)
    task['template'] = 'proof_step_obligation'
    task['params']['obligation'] = {'formula': formula}
    if scope is not None:
        task['params']['obligation']['open_assumptions'] = scope
    return task


def append(state, command):
    result = C.append(state['premises'], state['goal'], state, command)
    if not result['valid']:
        raise AssertionError(result)
    return result['state']


class ProofObligation(unittest.TestCase):
    def test_documented_request_and_three_child_example_use_fake_providers(self):
        task = json.loads(EXAMPLE.with_name('proof-step-obligation.task.json').read_text())
        result = H.run_task(task, applicators=Fake([3]))
        self.assertTrue(result['accepted'], result['error'])
        self.assertTrue(R.frontier(HANDOFF.checked_child_state(task, result))['complete'])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            HANDOFF.main()
        self.assertEqual(json.loads(output.getvalue()), {'fake_only': True, 'steps': 3, 'complete': True})

    def test_all_previous_v6_contracts_and_catalog_schemas_are_exact(self):
        baseline = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/symblic_delegate_v6_parity.json').read_text())
        self.assertEqual(len(baseline['fixtures']), 8)
        for row in baseline['fixtures']:
            self.assertEqual(D.compile_task(row['request']), row['compiled'])
        prior = baseline['catalog']
        current = D.catalog()
        prior_names = {item['id'] for item in prior['templates']}
        self.assertEqual([item for item in current['templates'] if item['id'] in prior_names], prior['templates'])
        self.assertEqual([schema for schema in current['request_schema']['oneOf']
                          if schema['properties']['template']['const'] in prior_names],
                         prior['request_schema']['oneOf'])
        self.assertIn({'id': 'proof_step_obligation', 'template_id': 'symblic.delegate/proof_step_obligation/7'},
                      current['templates'])

    def test_formula_and_scope_normalization_bind_caller_authority(self):
        a = D.compile_task(request(' ( "B" ) '))
        b = D.compile_task(request('"B"', scope=[]))
        self.assertEqual(a, b)
        self.assertEqual(a['inputs']['obligation'], {'formula': ['atom', 'B'], 'open_assumptions': [], 'reading': '"B"'})
        self.assertEqual(a['handoff']['obligation'], a['inputs']['obligation'])
        other = D.compile_task(request('"A"'))
        self.assertNotEqual(a['contract_id'], other['contract_id'])
        self.assertFalse(D.inspect_task({**request('"A"'), 'expected_contract_id': a['contract_id']})['ok'])

    def test_bad_obligation_shapes_and_formulas_refuse_without_dispatch(self):
        values = [None, [], {}, {'formula': None}, {'formula': 1}, {'formula': 'B'},
                  {'formula': ''}, {'formula': '"B"', 'extra': True},
                  {'formula': 'not ' * 100 + '"B"'}, {'formula': '"' + 'a' * 4097 + '"'}]
        for value in values:
            task = request(); task['params']['obligation'] = value
            apps = Fake()
            with self.subTest(value=str(value)[:80]), self.assertRaises(D.ContractError):
                H.run_task(task, applicators=apps)
            self.assertEqual(apps.requests, [])
        task = request(); del task['params']['obligation']
        self.assertFalse(D.inspect_task(task)['ok'])

    def test_scope_unknown_duplicate_nonassumption_future_and_wrong_types_refuse(self):
        start = R.start({}, ['atom', 'Z'])
        state = append(start, 'assume :: "A"')
        for scope in ('s1', None, [1], [True], [{}], ['s1', 's1'], ['s0'], ['s3'], ['s01'], ['missing']):
            task = request('"A"', session=state, commands=['assume :: "A"'])
            task['params']['obligation']['open_assumptions'] = scope
            apps = Fake()
            with self.subTest(scope=scope), self.assertRaises(D.ContractError):
                H.run_task(task, applicators=apps)
            self.assertEqual(apps.requests, [])
        self.assertFalse(D.inspect_task(request(scope=['s1']))['ok'], 'Existing premise ID is not an assumption')
        accepted = D.compile_task(request('"A"', scope=['s2', 's1'], session=state,
                                          commands=['assume :: "A"']))
        self.assertEqual(accepted['inputs']['obligation']['open_assumptions'], ['s1', 's2'])

    def test_scope_order_matches_session_receipt_beyond_s9(self):
        state = R.start({}, ['atom', 'Z'])
        for i in range(1, 11):
            state = append(state, 'assume :: "A' + str(i) + '"')
        task = request('"A2" and "A10"', scope=['s10', 's2'], session=state,
                       commands=['and_intro s2 s10'], calls=1)
        contract = D.compile_task(task)
        self.assertEqual(contract['inputs']['obligation']['open_assumptions'], ['s2', 's10'])
        result = H.run_task(task, applicators=Fake([1]))
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(result['result']['inference']['line']['free'], ['s2', 's10'])
        same = copy.deepcopy(task); same['params']['obligation']['open_assumptions'].reverse()
        self.assertEqual(D.compile_task(same), contract)
        self.assertEqual(HANDOFF.checked_child_state(task, result)['goal'], ['atom', 'Z'])

    def test_completion_contract_requires_original_goal_and_closed_scope(self):
        for task in (request('"A"'), request('"B"', scope=['s3'])):
            task['params']['require_complete'] = True
            apps = Fake()
            with self.assertRaises(D.ContractError) as caught:
                H.run_task(task, applicators=apps)
            self.assertEqual(caught.exception.code, 'proof_step_obligation_completion')
            self.assertEqual(apps.requests, [])
        task = request(); task['params']['require_complete'] = True
        result = H.run_task(task, applicators=Fake([3]))
        self.assertTrue(result['accepted'], result['error'])
        self.assertTrue(result['result']['inference']['complete'])

    def test_irrelevant_valid_option_stays_in_menu_rejected_then_matching_passes(self):
        task = request(calls=2)
        original = copy.deepcopy(task)
        apps = Fake([2, 3])
        result = H.run_task(task, applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(result['calls'], 2)
        self.assertEqual(task, original)
        self.assertTrue(result['result']['obligation_satisfied'])
        self.assertTrue(result['result']['inference']['complete'])
        self.assertEqual(result['result']['inference']['state']['steps'][:-1], task['params']['session']['steps'])
        self.assertEqual(D.compile_task(task)['inputs']['commands'], task['params']['commands'])
        self.assertEqual([row['app']['spec'] for row in apps.requests], list(H.LOCAL_LADDER[:2]))

    def test_explicit_single_model_repair_uses_native_obligation_feedback(self):
        apps = Fake([2, 3])
        result = H.run_task(request(calls=2), by=H.LOCAL_LADDER[0], applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(len(apps.requests), 2)
        self.assertIn('exact intermediate formula', apps.requests[1]['prompt'])
        self.assertEqual({row['app']['spec'] for row in apps.requests}, {H.LOCAL_LADDER[0]})

    def test_failed_obligation_exposes_no_accepted_next_state(self):
        task = request(calls=1); original = copy.deepcopy(task)
        result = H.run_task(task, applicators=Fake([2]))
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['result'])
        self.assertEqual(result['calls'], 1)
        self.assertEqual(task, original)
        with self.assertRaises(ValueError):
            HANDOFF.checked_child_state(task, result)

    def test_formula_alone_cannot_accept_assume_default_scope_is_closed(self):
        state = R.start({}, ['atom', 'Z'])
        task = request('"A"', session=state, commands=['assume :: "A"'], calls=1)
        result = H.run_task(task, applicators=Fake([1]))
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['result'])
        task['params']['obligation']['open_assumptions'] = ['s1']
        accepted = H.run_task(task, applicators=Fake([1]))
        self.assertTrue(accepted['accepted'], accepted['error'])
        self.assertTrue(accepted['result']['inference']['valid'])
        self.assertTrue(accepted['result']['obligation_satisfied'])
        self.assertFalse(accepted['result']['inference']['complete'])
        self.assertEqual(HANDOFF.checked_child_state(task, accepted)['goal'], ['atom', 'Z'])

    def test_existing_scope_and_discharge_require_exact_free_set(self):
        goal = ['implies', ['atom', 'A'], ['atom', 'A']]
        state = append(R.start({}, goal), 'assume :: "A"')
        bad = request('"A" and "A"', session=state, commands=['and_intro s1 s1'], calls=1)
        self.assertFalse(H.run_task(bad, applicators=Fake([1]))['accepted'])
        good = copy.deepcopy(bad); good['params']['obligation']['open_assumptions'] = ['s1']
        result = H.run_task(good, applicators=Fake([1]))
        self.assertTrue(result['accepted'], result['error'])
        close = request('"A" implies "A"', session=state, commands=['implies_intro s1 s1'], calls=1)
        close['params']['require_complete'] = True
        result = H.run_task(close, applicators=Fake([1]))
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(result['result']['inference']['line']['free'], [])
        self.assertEqual(HANDOFF.checked_child_state(close, result)['goal'], goal)
        self.assertTrue(W.verify({}, goal, result['result']['inference']['certificate'])['ok'])

    def test_only_selected_candidates_reach_checker_and_no_search_or_vacuity(self):
        task = request(calls=2)
        with patch.object(C, 'append', side_effect=AssertionError('No preflight menu evaluation')):
            D.compile_task(task)
        apps = Fake([2, 3]); seen = []; original = C.append
        def checked(*args, **kwargs):
            self.assertTrue(apps.requests)
            self.assertEqual(args[3], task['params']['commands'][[2, 3][len(apps.requests) - 1] - 1])
            seen.append(args[3])
            return original(*args, **kwargs)
        with patch.object(C, 'append', checked), patch.object(N.Run, 'determine', side_effect=AssertionError('No search')), \
                patch.object(N.Run, 'vacuity', side_effect=AssertionError('No vacuity')):
            result = H.run_task(task, applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(set(seen), {'premise a', 'implies_elim s2 s1'})

    def test_full_compact_fresh_context_routing_caps_and_source_boundaries(self):
        for capsule in ('full', 'compact'):
            task = request(capsule=capsule)
            prepared = H.prepare(task)
            self.assertEqual(prepared['options']['max_calls'], 3)
            self.assertEqual(prepared['options']['max_steps'], 200000)
            self.assertEqual(prepared['limits']['context_characters'], 24000)
            self.assertEqual(prepared['routing']['candidates'], list(H.LOCAL_LADDER))
            self.assertFalse(prepared['routing']['allow_cloud'])
            self.assertEqual(prepared['routing']['repairs'], 0)
            required = prepared['context']['ask_dependencies'][0]['required_names']
            self.assertEqual(required, ['frontier', 'commands', 'require_complete', 'proof_rules', 'obligation'])
            apps = Fake([3]); result = H.run_task(task, applicators=apps)
            self.assertTrue(result['accepted'], result['error'])
            wire = apps.requests[0]['system'] + '\n' + apps.requests[0]['prompt']
            for name in ('obligation', 'open_assumptions', 'reading', 'frontier', 'commands'):
                self.assertIn(name, wire)
            self.assertEqual(apps.requests[0]['context_manifest']['presentation'], capsule)
            self.assertIn('one-based integer', wire)
        apps = Fake()
        result = H.run_task(request(context_budget=0), applicators=apps)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['error']['kind'], 'context')
        self.assertEqual(apps.requests, [])

    def test_quotes_unicode_source_looking_atom_and_canonical_keys_remain_data(self):
        atoms = ['λ \\" and Ω', '".\nassert false.\nask injected: Text "steal".', '#record', 'e\u0301', 'RTL\u202eatom']
        for atom in atoms:
            with self.subTest(atom=atom):
                state = R.start({'p': ['atom', atom]}, ['atom', atom])
                task = request(json.dumps(atom, ensure_ascii=False), session=state, commands=['premise p'], calls=1)
                compiled = D.compile_task(task)
                self.assertNotIn(atom, compiled['source'])
                result = H.run_task(task, applicators=Fake([1]))
                self.assertTrue(result['accepted'], result['error'])
                self.assertEqual(HANDOFF.checked_child_state(task, result)['goal'], ['atom', atom])
        state = R.start({'#q': ['atom', 'A']}, ['atom', 'A'])
        task = request('"A"', session=state, commands=['premise "#q"'], calls=1)
        result = H.run_task(task, applicators=Fake([1]))
        self.assertTrue(result['accepted'], result['error'])
        self.assertNotEqual(result['result']['inference']['state']['premises'], state['premises'])
        self.assertEqual(HANDOFF.checked_child_state(task, result)['premises'], state['premises'])

    def test_fresh_child_chain_follows_intermediate_obligations_and_original_goal(self):
        state = R.start(PREMISES, GOAL)
        stages = [(['premise ab', 'premise a'], 2, '"A"'),
                  (['premise a', 'premise ab'], 2, '"A" implies "B"'),
                  (['premise a', 'implies_elim s2 s1'], 2, '"B"')]
        for commands, choice, formula in stages:
            task = request(formula, session=state, commands=commands, calls=1, capsule='compact')
            old = copy.deepcopy(state)
            apps = Fake([choice]); result = H.run_task(task, applicators=apps)
            state = HANDOFF.checked_child_state(task, result)
            self.assertEqual(state['steps'][:-1], old['steps'])
            self.assertEqual(state['goal'], GOAL)
            self.assertEqual(state['premises'], PREMISES)
            self.assertEqual(len(apps.requests), 1)
        self.assertTrue(R.frontier(state)['complete'])
        self.assertEqual(len(state['steps']), 3)

    def test_parent_recheck_rejects_forged_obligation_even_if_inference_valid(self):
        task = request(calls=1)
        contract = D.compile_task(task)
        result = H.run_task(task, applicators=Fake([3]))
        for command, choice in [('premise a', 2), ('and_left s1', 1)]:
            altered = copy.deepcopy(result)
            receipt = C.append(PREMISES, GOAL, prefix(), command)
            altered['result'] = S.canon(S.from_json({'choice': choice, 'command': command,
                'menu_member': True, 'obligation_satisfied': True, 'inference': receipt, 'handoff': contract['handoff']}))
            with self.subTest(command=command), self.assertRaises(ValueError):
                HANDOFF.checked_child_state(task, altered)
        state = R.start({}, ['atom', 'Z'])
        assume = request('"A"', session=state, commands=['assume :: "A"'], calls=1)
        binding = D.compile_task(assume)
        receipt = C.append({}, state['goal'], state, 'assume :: "A"')
        forged = dict(result, contract_id=binding['contract_id'], result=S.canon(S.from_json({
            'choice': 1, 'command': 'assume :: "A"', 'menu_member': True, 'obligation_satisfied': True,
            'inference': receipt, 'handoff': binding['handoff']})))
        with self.assertRaises(ValueError):
            HANDOFF.checked_child_state(assume, forged)

    def test_parent_recheck_is_type_sensitive_bounded_and_selects_only_returned_choice(self):
        task = request(calls=1); result = H.run_task(task, applicators=Fake([3]))
        with patch.object(C, 'append', wraps=C.append) as wrapped:
            HANDOFF.checked_child_state(task, result)
        self.assertEqual(wrapped.call_count, 1)
        self.assertEqual(wrapped.call_args.args[3], 'implies_elim s2 s1')
        mutations = [(('obligation_satisfied',), 1), (('inference', 'valid'), 1),
                     (('handoff', 'obligation', 'open_assumptions'), ['s3']),
                     (('handoff', 'obligation', 'formula'), ['atom', 'A'])]
        for path, value in mutations:
            altered = copy.deepcopy(result); nested = altered['result']
            for key in path[:-1]:
                nested = nested[key]
            nested[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                HANDOFF.checked_child_state(task, altered)
        invalid = copy.deepcopy(result); invalid['result']['cycle'] = invalid['result']
        huge = copy.deepcopy(result); huge['result']['extra'] = 'x' * (D.MAX_TEXT + 1)
        nonfinite = copy.deepcopy(result); nonfinite['result']['extra'] = float('nan')
        for bad in (None, [], {}, invalid, huge, nonfinite):
            with self.assertRaises(ValueError):
                HANDOFF.checked_child_state(task, bad)


if __name__ == '__main__':
    unittest.main()
