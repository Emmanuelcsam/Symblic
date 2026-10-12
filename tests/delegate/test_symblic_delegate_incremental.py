"""Incremental proof delegation through catalog, contract and pinned native child."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.kernel.run import Run

TASK = {'template': 'proof', 'params': {
    'premises': 'a: "A"\nrule: "A" implies "B"', 'goal': '"B"',
    'certificate_format': 'incremental', 'step_limit': 3}}
ANSWERS = [{'rule': 'premise', 'args': ['rule'], 'formula': None},
           {'rule': 'premise', 'args': ['a'], 'formula': None},
           {'rule': 'implies_elim', 'args': ['s1', 's2'], 'formula': None}]


class Apps:
    def __init__(self, answers):
        self.answers = copy.deepcopy(answers)
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        if not self.answers:
            raise AssertionError('unexpected provider call')
        return {'ok': True, 'json': {'answer': self.answers.pop(0)}, 'model': 'fake', 'node': 'isolated'}


class IncrementalDelegation(unittest.TestCase):
    def test_defaults_nested_dependencies_and_output_contract(self):
        task = D.compile_task(TASK)
        self.assertEqual(task['options']['max_calls'], 32)
        self.assertEqual(task['options']['max_steps'], 200000)
        self.assertEqual(task['output_binding'], 'verification')
        self.assertEqual(task['formalization']['step_limit'], 3)
        self.assertEqual(task['context']['ask_dependencies_scope'], 'all_static_branches')
        self.assertEqual(task['context']['ask_dependencies'], [
            {'binding': f'candidate{index}', 'required_names': [f'frontier{index}', 'proof_rules']}
            for index in range(1, 4)])
        self.assertIn('use context=none, coercion=strict.', task['source'])
        self.assertFalse(task['options']['side_effects'])

    def test_catalog_schema_matches_lane_specific_budgets_and_step_limits(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional JSON Schema validator is unavailable')
        catalog = json.loads(json.dumps(D.catalog()))
        Draft202012Validator.check_schema(catalog['request_schema'])
        validator = Draft202012Validator(catalog['request_schema'])
        for calls in (1, 32, 64):
            request = {**TASK, 'calls': calls}
            self.assertTrue(validator.is_valid(request), list(validator.iter_errors(request)))
            self.assertEqual(D.compile_task(request)['limits']['max_calls'], calls)
        for change in ({'calls': 65}, {'calls': True},
                       {'params': {**TASK['params'], 'step_limit': 33}},
                       {'params': {**TASK['params'], 'step_limit': False}},
                       {'params': {**TASK['params'], 'certificate_format': 'steps'}},
                       {'params': {**TASK['params'], 'certificate_format': 'terms'}}):
            request = {**TASK, **change}
            self.assertFalse(validator.is_valid(request), request)
            self.assertFalse(D.inspect_task(request)['ok'])
        for lane in ('terms', 'steps'):
            params = {name: value for name, value in TASK['params'].items() if name != 'step_limit'}
            params['certificate_format'] = lane
            legacy = {'template': 'proof', 'params': params}
            self.assertTrue(validator.is_valid(legacy))
            self.assertEqual(D.compile_task(legacy)['limits']['max_calls'], 3)
            self.assertFalse(validator.is_valid({**legacy, 'calls': 7}))
            self.assertFalse(D.inspect_task({**legacy, 'calls': 7})['ok'])

    def test_step_limit_without_incremental_and_unknown_params_refuse(self):
        for params in ({**TASK['params'], 'certificate_format': 'terms'},
                       {key: val for key, val in TASK['params'].items() if key != 'certificate_format'},
                       {**TASK['params'], 'max_steps': 3}, {**TASK['params'], 'calls': 32}):
            result = D.inspect_task({**TASK, 'params': params})
            self.assertFalse(result['ok'])
            self.assertNotIn('source', result)

    def test_roundtrip_contract_id_pins_bounds_and_expected_id(self):
        task = D.compile_task(json.loads(json.dumps(TASK)))
        pinned = {**TASK, 'expected_contract_id': task['contract_id']}
        self.assertEqual(D.compile_task(pinned)['contract_id'], task['contract_id'])
        for change in ({'calls': 31}, {'context_budget': 24001}, {'max_steps': 200001},
                       {'params': {**TASK['params'], 'step_limit': 4}},
                       {'params': {**TASK['params'], 'goal': '"A"'}}):
            request = {**TASK, **change}
            self.assertNotEqual(D.compile_task(request)['contract_id'], task['contract_id'])
            result = D.inspect_task({**request, 'expected_contract_id': task['contract_id']})
            self.assertFalse(result['ok'])
            self.assertEqual(result['errors'][0]['code'], 'contract_mismatch')

    def test_context_budget_applies_to_every_nested_step_and_no_silent_truncation(self):
        task = D.compile_task({**TASK, 'context_budget': 0})
        self.assertEqual(task['source'].count('budget=0'), 3)
        self.assertNotIn('budget=24000', task['source'])
        apps = Apps([])
        report = Run(task['source'], task['inputs'], apps, {**task['options'], 'by': 'fake:child'}).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(apps.requests, [])
        self.assertEqual(report['error']['kind'], 'context')

    def test_native_parent_child_receipt_three_steps_and_specific_repair(self):
        wrong = {'rule': 'implies_elim', 'args': ['s2', 's1'], 'formula': None}
        apps = Apps(ANSWERS[:2] + [wrong, ANSWERS[2]])
        contract = D.compile_task(TASK)
        request = {**TASK, 'expected_contract_id': contract['contract_id']}
        with tempfile.TemporaryDirectory() as folder:
            result = H.run_task(request, applicators=apps, by='fake:child', folder=folder)
            self.assertTrue(result['accepted'], result.get('error'))
            self.assertEqual(result['contract_id'], contract['contract_id'])
            self.assertEqual(result['calls'], 4)
            self.assertTrue(result['result']['valid'])
            self.assertEqual(result['result']['conclusion'], ['atom', 'B'])
            meta = json.loads(Path(folder, 'meta.json').read_text())
            self.assertEqual(meta['delegation']['output_binding'], 'verification')
            self.assertIn('symblic/adapters/proof_session.py', meta['options']['execution_pins']['python_hashes'])
            self.assertEqual(meta['delegation']['contract_id'], contract['contract_id'])
        self.assertIn('implies_elim_mismatch', apps.requests[3]['prompt'])
        self.assertIn('"next_id": "s3"', apps.requests[3]['prompt'])

    def test_native_parent_receives_no_accepted_output_when_two_calls_are_insufficient(self):
        apps = Apps(ANSWERS[:2])
        result = H.run_task({**TASK, 'calls': 2}, applicators=apps, by='fake:child')
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['result'])
        self.assertEqual((result['calls'], len(apps.requests)), (2, 2))
        self.assertIn('budget', result['error']['message'])


if __name__ == '__main__':
    unittest.main()
