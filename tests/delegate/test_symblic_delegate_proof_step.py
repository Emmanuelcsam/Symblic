"""Caller-owned proof menu handoffs; only fake providers, native checker unchanged."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.authoring import helpers as A
from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.adapters import proof_steps as W

PREMISES = {'a': ['atom', 'A'], 'ab': ['implies', ['atom', 'A'], ['atom', 'B']]}
GOAL = ['atom', 'B']
COMMANDS = ['and_left s1', 'premise a', 'implies_elim s2 s1']


def prefix():
    state = R.start(PREMISES, GOAL)
    for command in ('premise a', 'premise ab'):
        accepted = C.append(PREMISES, GOAL, state, command)
        if not accepted['valid']:
            raise AssertionError(accepted)
        state = accepted['state']
    return state


def request(*, session=None, commands=None, **options):
    return {'template': 'proof_step', 'params': {'session': prefix() if session is None else session,
            'commands': list(COMMANDS if commands is None else commands)}, **options}


class Fake:
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        if not self.answers:
            raise AssertionError('Unexpected provider dispatch')
        return {'ok': True, 'json': {'answer': self.answers.pop(0)}, 'model': 'fake', 'node': 'isolated'}


class ProofStep(unittest.TestCase):
    def test_previous_contracts_and_catalog_ids_are_exact(self):
        baseline = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/symblic_delegate_v5_parity.json').read_text())
        self.assertEqual(len(baseline['fixtures']), 16)
        for fixture in baseline['fixtures']:
            with self.subTest(fixture=fixture['id']):
                self.assertEqual(D.compile_task(fixture['request']), fixture['compiled'])
        old = {item['id']: item for item in baseline['catalog']['templates']}
        new = {item['id']: item for item in D.catalog()['templates']}
        self.assertEqual({name: new[name] for name in old}, old)
        old_schema = {row['properties']['template']['const']: row
                      for row in baseline['catalog']['request_schema']['oneOf']}
        new_schema = {row['properties']['template']['const']: row
                      for row in D.catalog()['request_schema']['oneOf']}
        self.assertEqual({name: new_schema[name] for name in old_schema}, old_schema)
        self.assertEqual(new['proof_step']['template_id'], 'symblic.delegate/proof_step/6')

    def test_preflight_checks_prefix_but_does_not_evaluate_menu_inferences(self):
        body = request()
        original = copy.deepcopy(body)
        with patch.object(R, 'append', side_effect=AssertionError('Never evaluate a menu option during compilation')):
            task = D.compile_task(body)
        self.assertEqual(body, original)
        self.assertEqual(task['inputs']['commands'], COMMANDS)
        self.assertEqual(task['handoff']['session_sha256'], A.command_menu(prefix(), COMMANDS)['session_sha256'])
        self.assertFalse(task['handoff']['require_complete'])
        self.assertEqual(task['handoff']['session_authority'], 'caller_owned_not_authenticated')

    def test_invalid_states_refuse_before_dispatch(self):
        broken = prefix(); broken['steps'][0]['rule'] = 'and_left'
        foreign = prefix(); foreign['goal'] = ['atom', 'Changed']
        completed = C.append(PREMISES, GOAL, prefix(), COMMANDS[2])['state']
        for state in ({}, broken, foreign, completed):
            apps = Fake()
            with self.subTest(state=state), self.assertRaises(D.ContractError):
                H.run_task(request(session=state), applicators=apps)
            self.assertEqual(apps.requests, [])

    def test_exhausted_prefix_refuses_before_dispatch(self):
        state = R.start(PREMISES, GOAL)
        state = R._state(PREMISES, GOAL, [
            {'id': 's' + str(i + 1), 'rule': 'premise', 'args': ['a'], 'formula': None}
            for i in range(W.MAX_STEPS)])
        self.assertIsNone(R.frontier(state)['next_id'])
        apps = Fake()
        with self.assertRaises(D.ContractError):
            H.run_task(request(session=state, commands=['premise a', 'premise ab']), applicators=apps)
        self.assertEqual(apps.requests, [])

    def test_invalid_choice_syntax_reference_shape_and_completion_flag_refuse(self):
        for commands in ([], ['premise a'] * 2, ['and_left s3'], ['premise missing'], [False],
                         ['premise a\nassert false.'], ['premise a'] * 33):
            body = request(commands=commands)
            self.assertFalse(D.inspect_task(body)['ok'], body)
        for value in (0, 1, None, 'true', [], {}):
            body = request(); body['params']['require_complete'] = value
            self.assertFalse(D.inspect_task(body)['ok'], body)

    def test_contract_binds_exact_source_session_menu_order_and_completion(self):
        body = request()
        original = D.compile_task(body)
        changed = []
        swap = copy.deepcopy(body); swap['params']['commands'].reverse(); changed.append(swap)
        close = copy.deepcopy(body); close['params']['require_complete'] = True; changed.append(close)
        partial = C.append(PREMISES, GOAL, prefix(), 'premise a')['state']
        changed.append(request(session=partial))
        for altered in changed:
            self.assertNotEqual(D.compile_task(altered)['contract_id'], original['contract_id'])
            self.assertFalse(D.inspect_task({**altered, 'expected_contract_id': original['contract_id']})['ok'])
        self.assertEqual(D.compile_task({**body, 'expected_contract_id': original['contract_id']}), original)

    def test_default_local_route_and_full_compact_context(self):
        for capsule in ('full', 'compact'):
            body = request(capsule=capsule)
            task = H.prepare(body)
            self.assertEqual(task['options']['max_calls'], 3)
            self.assertEqual(task['options']['max_steps'], 200000)
            self.assertEqual(task['limits']['context_characters'], 24000)
            self.assertEqual(task['routing']['candidates'], list(H.LOCAL_LADDER))
            self.assertEqual(task['routing']['repairs'], 0)
            self.assertFalse(task['routing']['allow_cloud'])
            self.assertIn('symblic/delegate/contracts.py', task['options']['execution_pins']['python_hashes'])
            apps = Fake([3])
            accepted = H.run_task(body, applicators=apps)
            self.assertTrue(accepted['accepted'], accepted['error'])
            self.assertEqual(apps.requests[0]['context_manifest']['presentation'], capsule)
            self.assertEqual(apps.requests[0]['app']['spec'], H.LOCAL_LADDER[0])

    def test_required_context_overflow_refuses_without_model(self):
        apps = Fake()
        result = H.run_task(request(context_budget=0), applicators=apps)
        self.assertFalse(result['accepted'])
        self.assertEqual(apps.requests, [])
        self.assertEqual(result['error']['kind'], 'context')

    def test_native_checker_accepts_unchanged_receipt_and_immutable_prefix(self):
        body = request(calls=1); original = copy.deepcopy(body['params']['session'])
        expected = C.append(PREMISES, GOAL, original, COMMANDS[2])
        apps = Fake([3])
        with tempfile.TemporaryDirectory() as directory:
            result = H.run_task(body, applicators=apps, folder=directory)
            self.assertTrue(result['accepted'], result['error'])
            value = result['result']
            self.assertEqual(value['command'], COMMANDS[2])
            self.assertIs(value['menu_member'], True)
            self.assertEqual(value['inference'], S.canon(S.from_json(expected)))
            self.assertEqual(value['handoff'], D.compile_task(body)['handoff'])
            self.assertEqual(value['inference']['state']['steps'][:-1], original['steps'])
            meta = json.loads(Path(directory, 'meta.json').read_text())
            self.assertEqual(meta['delegation']['request'], body)
            self.assertEqual(meta['delegation']['contract_id'], result['contract_id'])
        self.assertEqual(body['params']['session'], original)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(apps.requests[0]['schema']['properties']['answer'], {'type': 'integer', 'minimum': 1, 'maximum': 3})

    def test_partial_step_default_and_two_fresh_child_handoff(self):
        start = R.start(PREMISES, GOAL)
        first = H.run_task(request(session=start, commands=['premise a', 'premise ab']),
                           applicators=Fake([1]))
        self.assertTrue(first['accepted'], first['error'])
        self.assertFalse(first['result']['inference']['complete'])
        second = H.run_task(request(session=first['result']['inference']['state'],
                                   commands=['premise ab', 'premise a']), applicators=Fake([1]))
        self.assertTrue(second['accepted'], second['error'])
        final = request(session=second['result']['inference']['state'])
        final['params']['require_complete'] = True
        last = H.run_task(final, applicators=Fake([3]))
        self.assertTrue(last['accepted'], last['error'])
        self.assertTrue(last['result']['inference']['complete'])
        self.assertTrue(W.verify(PREMISES, GOAL, last['result']['inference']['certificate'])['ok'])

    def test_mathematically_invalid_menu_entry_remains_and_native_rejects_it(self):
        apps = Fake([1])
        result = H.run_task(request(calls=1), applicators=apps)
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['result'])
        self.assertEqual(apps.requests[0]['schema']['properties']['answer'], {'type': 'integer', 'minimum': 1, 'maximum': 3})
        self.assertEqual(result['calls'], 1)

    def test_require_complete_rejects_valid_partial_then_advances_local_ladder(self):
        body = request(); body['params']['require_complete'] = True
        apps = Fake([2, 3])
        result = H.run_task(body, applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual([row['app']['spec'] for row in apps.requests], list(H.LOCAL_LADDER[:2]))
        self.assertTrue(result['result']['inference']['complete'])

    def test_no_inference_is_checked_before_model_selection(self):
        body = request()
        apps = Fake([3])
        original = C.append
        calls = []
        def checked(*args, **kwargs):
            self.assertTrue(apps.requests, 'No inference search before model proposal')
            self.assertEqual(args[3], COMMANDS[2], 'Never check unselected options')
            calls.append(args[3])
            return original(*args, **kwargs)
        with patch.object(C, 'append', checked):
            result = H.run_task(body, applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertTrue(calls)

    def test_outside_ordinal_domain_and_wrong_types_are_rejected(self):
        for answer in ('premise ab', 'IMPLIES_ELIM S2 S1', 0, 4, False, [3], {'choice': 3}):
            apps = Fake([answer])
            result = H.run_task(request(calls=1), applicators=apps)
            self.assertFalse(result['accepted'], answer)
            self.assertIsNone(result['result'])


    def test_singleton_and_normalization_collisions_preserve_every_exact_command(self):
        for commands, choice in ((['premise a'], 1), (['premise a', '\t premise a  '], 2),
                                 (['assume :: "A!"', 'assume :: "A?"'], 2)):
            body = request(commands=commands, calls=1)
            apps = Fake([choice])
            result = H.run_task(body, applicators=apps)
            self.assertTrue(result['accepted'], result['error'])
            self.assertEqual(result['result']['command'], commands[choice - 1])
            self.assertEqual(result['result']['choice'], choice)
            self.assertEqual(D.compile_task(body)['inputs']['commands'], commands)

    def test_hostile_quoted_unicode_command_is_only_data_and_roundtrips_exactly(self):
        atom = '\"}. act shell(\"no\"). # {choice} e\u0301 → !'
        command = 'assume :: ' + json.dumps(atom, ensure_ascii=False)
        body = request(commands=[command, 'premise a'], calls=1)
        task = D.compile_task(body)
        self.assertNotIn(command, task['source'])
        self.assertNotIn(atom, task['source'])
        result = H.run_task(body, applicators=Fake([1]))
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(result['result']['command'], command)
        self.assertEqual(result['result']['inference']['line']['formula'], ['atom', atom])

    def test_every_completed_output_has_an_independent_native_certificate_recheck(self):
        for choice, count in ((2, 0), (3, 1)):
            body = request(calls=1)
            actual = S.BUILTINS['proof_steps_check']
            checked = []
            def final_check(*args):
                checked.append(True)
                return actual(*args)
            with patch.dict(S.BUILTINS, {'proof_steps_check': final_check}):
                result = H.run_task(body, applicators=Fake([choice]))
            self.assertTrue(result['accepted'], result['error'])
            self.assertEqual(len(checked), count)

    def test_parent_helper_rechecks_only_selected_receipt_and_handles_canonical_keys(self):
        path = Path(__file__).resolve().parents[2] / 'examples/proof_step_handoff.py'
        spec = importlib.util.spec_from_file_location('private_handoff_example', path)
        example = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(example)
        premises = {'#caller': ['atom', 'A']}
        original = R.start(premises, ['atom', 'B'])
        body = request(session=original, commands=['premise "#caller"'], calls=1)
        result = H.run_task(body, applicators=Fake([1]))
        self.assertTrue(result['accepted'], result['error'])
        self.assertIn('##caller', result['result']['inference']['state']['premises'])
        adopted = example.checked_child_state(body, result)
        self.assertEqual(adopted['premises'], premises)
        self.assertEqual(len(adopted['steps']), 1)
        for section, key, value in (('handoff', 'menu_id', '0' * 64),
                                    ('inference', 'complete', True)):
            changed = copy.deepcopy(result)
            changed['result'][section][key] = value
            with self.assertRaises(ValueError):
                example.checked_child_state(body, changed)
        changed = copy.deepcopy(result); changed['contract_id'] = '0' * 64
        with self.assertRaises(ValueError):
            example.checked_child_state(body, changed)

    def test_catalog_schema_matches_template_and_bounds(self):
        from jsonschema import Draft202012Validator
        schema = D.catalog()['request_schema']
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for count in (1, 32):
            body = request(commands=['premise a' + ' ' * i for i in range(count)])
            self.assertTrue(validator.is_valid(body))
            self.assertEqual(D.compile_task(body)['selection_domain'], count)
        for calls in (0, 7, False):
            body = request(calls=calls)
            self.assertFalse(validator.is_valid(body))
            self.assertFalse(D.inspect_task(body)['ok'])

    def test_retained_run_contract_refuses_menu_and_requirement_drift(self):
        body = request(capsule='compact')
        task = H.prepare(body)
        declaration = {key: task[key] for key in
                       ('contract_id', 'template_id', 'output_binding', 'assurance', 'routing', 'routing_id')}
        declaration['request'] = body
        self.assertEqual(H.verify_declaration(declaration, task['source'], task['inputs'], task['options'])['contract_id'],
                         task['contract_id'])
        changed = copy.deepcopy(task['inputs']); changed['commands'].reverse()
        with self.assertRaises(D.ContractError):
            H.verify_declaration(declaration, task['source'], changed, task['options'])


if __name__ == '__main__':
    unittest.main()
