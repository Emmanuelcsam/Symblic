"""Proof-step ordinal response instructions remain consistent in real capsules."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.adapters import proof_command as C
from tests.delegate.test_symblic_delegate_proof_step import COMMANDS, Fake, request


class ProofStepOrdinalWire(unittest.TestCase):
    def test_overlay_is_detached_and_changes_only_native_wire_description(self):
        body = request()
        native = C.rules()
        shared = copy.deepcopy(native)
        with patch.object(C, 'rules', return_value=shared):
            task = D.compile_task(body)
        actual = task['inputs']['proof_rules']
        self.assertEqual(set(actual), set(native))
        self.assertEqual({key: value for key, value in actual.items() if key != 'wire'},
                         {key: value for key, value in native.items() if key != 'wire'})
        self.assertEqual(shared, native, 'Compiler must not mutate supplier-owned rules')
        self.assertEqual(C.rules(), native)
        self.assertIn('one-based integer index', actual['wire'])
        self.assertIn('describe menu entries only', actual['wire'])
        actual['commands'].clear()
        self.assertEqual(shared, native)
        self.assertEqual(C.rules(), native)

    def test_compiled_source_session_menu_and_check_contract_are_unchanged(self):
        body = request()
        original = D._proof_step_request
        def original_wire(params):
            state, menu, required, binding, _rules = original(params)
            return state, menu, required, binding, C.rules()
        with patch.object(D, '_proof_step_request', original_wire):
            before = D.compile_task(body)
        after = D.compile_task(body)
        self.assertNotEqual(before['contract_id'], after['contract_id'])
        self.assertNotEqual(before['inputs_sha256'], after['inputs_sha256'])
        restored = copy.deepcopy(after)
        restored['inputs']['proof_rules']['wire'] = before['inputs']['proof_rules']['wire']
        for name in ('contract_id', 'inputs_sha256'):
            restored[name] = before[name]
        self.assertEqual(restored, before)
        self.assertEqual(after['inputs']['commands'], COMMANDS)

    def test_full_and_compact_rendered_requests_require_integer_not_command_answer(self):
        native = C.rules()
        for presentation in ('full', 'compact'):
            with self.subTest(presentation=presentation):
                body = request(calls=1, capsule=presentation)
                task = D.compile_task(body)
                apps = Fake([3])
                result = H.run_task(body, applicators=apps)
                self.assertTrue(result['accepted'], result['error'])
                self.assertEqual(result['result']['choice'], 3)
                self.assertEqual(result['result']['command'], COMMANDS[2])
                self.assertTrue(result['result']['inference']['complete'])
                self.assertEqual(len(apps.requests), 1)
                actual = apps.requests[0]
                self.assertEqual(actual['schema']['properties']['answer'],
                                 {'type': 'integer', 'minimum': 1, 'maximum': 3})
                self.assertEqual(actual['context_manifest']['presentation'], presentation)
                rendered = actual['system'] + '\n' + actual['prompt'] + '\n' + json.dumps(actual['schema'])
                self.assertIn(task['inputs']['proof_rules']['wire'], actual['prompt'])
                self.assertIn('Return its one-based choice number as the answer value.', actual['prompt'])
                self.assertNotIn(native['wire'], rendered)
                self.assertNotIn('The answer value is one text command', rendered)
                for command in COMMANDS:
                    self.assertIn(command, actual['prompt'])
                self.assertEqual(C.rules(), native)

    def test_every_previous_template_contract_remains_exact(self):
        path = Path(__file__).resolve().parents[1] / 'fixtures/symblic_delegate_v5_parity.json'
        fixtures = json.loads(path.read_text())['fixtures']
        self.assertEqual(len(fixtures), 16)
        for fixture in fixtures:
            with self.subTest(fixture=fixture['id']):
                self.assertEqual(D.compile_task(fixture['request']), fixture['compiled'])


if __name__ == '__main__':
    unittest.main()
