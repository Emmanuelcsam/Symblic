"""Reusable delegation through the existing runner, with fake providers only."""

import copy
import hashlib
import json
import unittest
from fractions import Fraction
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.kernel.run import Run

TRANSFORM = {'template': 'typed_transform', 'calls': 2, 'params': {
    'instruction': 'Return the two amounts as integers.', 'data': 'first 1, second 2',
    'output_schema': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 2, 'maxItems': 2},
    'checks': [{'op': 'sum_equals', 'path': [], 'expected': 3}]}}
ARITHMETIC = {'template': 'exact_arithmetic', 'params': {
    'operation': 'add', 'left': {'numerator': 1, 'denominator': 3},
    'right': {'numerator': 1, 'denominator': 6}}}
PROOF = {'template': 'proof', 'calls': 2, 'params': {
    'premises': 'p: "A"\nrule: "A" implies "B"', 'goal': '"B"'}}


class Fake:
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        if not self.answers:
            raise AssertionError('Unexpected model call')
        return {'ok': True, 'json': {'answer': self.answers.pop(0)}, 'model': 'fake', 'node': 'isolated'}


def execute(task, answers=()):
    apps = Fake(answers)
    run = Run(task['source'], task['inputs'], apps, {**task['options'], 'by': 'fake:child'}, folder=None)
    return run, run.execute(), apps


class Delegation(unittest.TestCase):
    def refusal(self, request, code=None):
        result = D.inspect_task(request)
        self.assertFalse(result['ok'], result)
        self.assertNotIn('source', result)
        self.assertNotIn('inputs', result)
        self.assertIsInstance(result['errors'][0]['message'], str)
        if code:
            self.assertEqual(result['errors'][0]['code'], code)
        return result

    def test_catalog_detached_schemas_have_exact_top_level_and_no_dispatch(self):
        with patch('symblic.kernel.run.Run', side_effect=AssertionError('inspection executed')):
            catalog = D.catalog()
            self.assertEqual({row['id'] for row in catalog['templates']},
                             {'typed_transform', 'proof', 'exact_arithmetic', 'enum_classification', 'witnessed_line',
                              'proof_step', 'proof_step_obligation', 'proof_step_focus', 'proof_step_card'})
            for schema in catalog['request_schema']['oneOf']:
                self.assertFalse(schema['additionalProperties'])
            self.assertTrue(D.inspect_task(ARITHMETIC)['ok'])
        catalog['templates'].clear()
        self.assertEqual(len(D.catalog()['templates']), 9)

    def test_parameter_text_cannot_inject_program_or_change_checks(self):
        request = copy.deepcopy(TRANSFORM)
        evil = '".\nact stolen = shell("bad").\nshow task_data.\n#'
        request['params']['instruction'] = evil
        request['params']['data'] = {'text': evil, 'parent_history': 'opaque caller-selected data'}
        result = D.compile_task(request)
        self.assertNotIn(evil, result['source'])
        self.assertEqual(result['inputs']['task_instruction'], evil)
        self.assertIn('ensure sum(answer) == check_value_0', result['source'])
        self.assertIn('use context=none, coercion=strict.', result['source'])
        self.assertEqual(result['context']['input_names'], sorted(result['inputs']))
        self.assertEqual(set(result['context']['ask_dependencies'][0]['required_names']), set(result['inputs']))
        self.assertEqual(result['options']['side_effects'], False)

    def test_contract_id_binds_full_inputs_schema_checks_limits_and_source(self):
        original = D.compile_task(TRANSFORM)
        self.assertEqual(len(original['contract_id']), 64)
        self.assertEqual(original['source_sha256'], hashlib.sha256(original['source'].encode()).hexdigest())
        self.assertEqual(D.compile_task(json.loads(json.dumps(TRANSFORM)))['contract_id'], original['contract_id'])
        for changed in ({**TRANSFORM, 'calls': 1}, {**TRANSFORM, 'context_budget': 24001},
                        {**TRANSFORM, 'max_steps': 200001}):
            self.assertNotEqual(D.compile_task(changed)['contract_id'], original['contract_id'])
        for key, value in [('data', 'different'), ('instruction', 'Different instruction'),
                           ('checks', [{'op': 'sum_equals', 'path': [], 'expected': 4}])]:
            changed = copy.deepcopy(TRANSFORM); changed['params'][key] = value
            self.assertNotEqual(D.compile_task(changed)['contract_id'], original['contract_id'])
        pinned = {**TRANSFORM, 'expected_contract_id': original['contract_id']}
        self.assertEqual(D.compile_task(pinned)['contract_id'], original['contract_id'])
        for bad in ('0'*64, None, True, 'sha256:' + original['contract_id']):
            self.refusal({**TRANSFORM, 'expected_contract_id': bad}, 'contract_mismatch')

    def test_compiled_and_input_objects_are_detached(self):
        request = copy.deepcopy(TRANSFORM)
        first = D.compile_task(request)
        first['inputs']['requirements'].clear()
        first['options']['max_calls'] = 99
        self.assertEqual(request, TRANSFORM)
        again = D.compile_task(TRANSFORM)
        self.assertTrue(again['inputs']['requirements'])
        self.assertEqual(again['options']['max_calls'], 2)

    def test_transform_rejects_wrong_sum_then_accepts_with_native_retry(self):
        task = D.compile_task(TRANSFORM)
        run, report, apps = execute(task, [[3, 5], [1, 2]])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(S.canon(run.kernel.env.lookup('answer').value), [1, 2])
        self.assertTrue(run.checks)
        self.assertIn('source entailment', task['assurance']['unassessed'])
        self.assertEqual(task['assurance']['origin'], 'model_proposal')

    def test_exhausted_wrong_sum_never_becomes_accepted_output(self):
        task = D.compile_task({**TRANSFORM, 'calls': 1})
        _, report, apps = execute(task, [[3, 5]])
        self.assertEqual(report['status'], 'failed', report)
        self.assertEqual(len(apps.requests), 1)

    def test_exact_numeric_wire_strings_follow_recorded_native_normalization(self):
        task = D.compile_task(TRANSFORM)
        run, report, apps = execute(task, [['1', '2']])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(S.canon(run.kernel.env.lookup('answer').value), [1, 2])
        self.assertIn('numeric_strings', task['assurance'])

    def test_strict_profile_rejects_undeclared_extra_fields(self):
        request = {'template': 'typed_transform', 'calls': 2, 'params': {'instruction': 'Copy', 'data': {'x': 4},
            'output_schema': {'type': 'object', 'properties': {'x': {'type': 'integer'}},
                              'required': ['x'], 'additionalProperties': False}}}
        task = D.compile_task(request)
        run, report, apps = execute(task, [{'x': 4, 'extra': 'unrequested'}, {'x': 4}])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(S.canon(run.kernel.env.lookup('answer').value), {'x': 4})

    def test_required_context_overflow_refuses_before_model_call(self):
        task = D.compile_task({**TRANSFORM, 'context_budget': 0})
        _, report, apps = execute(task)
        self.assertEqual(report['status'], 'failed', report)
        self.assertEqual(len(apps.requests), 0)
        self.assertIn('context', str(report['error']).lower())

    def test_schema_only_transform_is_not_claimed_as_instruction_verification(self):
        request = copy.deepcopy(TRANSFORM); request['params']['checks'] = []
        task = D.compile_task(request)
        self.assertTrue(task['assurance']['schema_only'])
        self.assertEqual(task['assurance']['checked'], ['output_schema'])
        self.assertIn('arbitrary instruction fidelity', task['assurance']['unassessed'])

    def test_nested_records_and_array_bounds_survive_native_type_roundtrip(self):
        schema = {'type': 'object', 'properties': {'items': {'type': 'array', 'minItems': 1, 'maxItems': 3,
            'items': {'type': 'array', 'minItems': 0, 'maxItems': 2, 'items': {'type': 'integer', 'minimum': 0, 'maximum': 9}}},
            'label': {'type': 'string'}}, 'required': ['label', 'items'], 'additionalProperties': False}
        request = {'template': 'typed_transform', 'params': {'instruction': 'Copy', 'data': {}, 'output_schema': schema,
            'checks': [{'op': 'equals', 'path': ['label'], 'expected': 'café'}]}}
        task = D.compile_task(request)
        parsed = S.parse(task['source'], execution_profile='verified')
        ask = next(row for row in parsed['statements'] if row.k == 'ask')
        self.assertEqual(S.json_schema(ask.type), task['output_schema'])
        run, report, _ = execute(task, [{'items': [[1, 2]], 'label': 'café'}])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(S.canon(run.kernel.env.lookup('answer').value), {'items': [[1, 2]], 'label': 'café'})

    def test_invalid_schema_injection_unknown_keywords_and_weakening_refuse(self):
        for schema in ({'type': 'integer.\nshow hidden'}, {'type': 'string', 'pattern': 'secret'},
                       {'type': 'integer', 'minimum': 1},
                       {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 2, 'maxItems': 1},
                       {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 0, 'maxItems': 129},
                       {'type': 'object', 'properties': {'x. act': {'type': 'string'}},
                        'required': ['x. act'], 'additionalProperties': False},
                       {'type': 'object', 'properties': {'x': {'type': 'string'}},
                        'required': [], 'additionalProperties': True}):
            request = copy.deepcopy(TRANSFORM); request['params']['output_schema'] = schema
            with self.subTest(schema=schema):
                self.refusal(request)

    def test_bad_check_paths_types_expressions_and_extra_expected_fields_refuse(self):
        for check in ({'op': 'eval', 'path': [], 'expected': 'act bad'},
                      {'op': 'sum_equals', 'path': ['missing'], 'expected': 3},
                      {'op': 'sum_equals', 'path': [], 'expected': True},
                      {'op': 'equals', 'path': [], 'expected': ['1', '2']},
                      {'op': 'equals', 'path': ['x) or true'], 'expected': 3}):
            request = copy.deepcopy(TRANSFORM); request['params']['checks'] = [check]
            self.refusal(request, 'check')
        request = {'template': 'typed_transform', 'params': {'instruction': 'Copy', 'data': {},
            'output_schema': {'type': 'object', 'properties': {'x': {'type': 'integer'}},
                              'required': ['x'], 'additionalProperties': False},
            'checks': [{'op': 'equals', 'path': [], 'expected': {'x': 1, 'unmentioned': 2}}]}}
        self.refusal(request, 'check')

    def test_exact_arithmetic_runs_without_provider_and_retains_fraction(self):
        task = D.compile_task(ARITHMETIC)
        run, report, apps = execute(task)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 0)
        self.assertEqual(task['options']['max_calls'], 0)
        value = run.kernel.env.lookup('answer').value
        self.assertEqual(value, Fraction(1, 2))
        self.assertEqual(S.canon(value), {'#q': '1/2'})
        self.assertEqual(task['output_encoding'], 'symblic.canon/' + str(S.CANON_VERSION))
        self.assertIn('operand truth', task['assurance']['unassessed'])

    def test_arithmetic_all_operations_negative_and_large_operands(self):
        for operation, expected in [('subtract', Fraction(1, 6)), ('multiply', Fraction(1, 18)), ('divide', 2)]:
            request = copy.deepcopy(ARITHMETIC); request['params']['operation'] = operation
            run, report, _ = execute(D.compile_task(request))
            self.assertEqual(report['status'], 'done', report.get('error'))
            self.assertEqual(run.kernel.env.lookup('answer').value, expected)
        request = copy.deepcopy(ARITHMETIC)
        request['params']['left'] = {'numerator': -10**90, 'denominator': 7}
        run, report, _ = execute(D.compile_task(request))
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(run.kernel.env.lookup('answer').value, Fraction(-10**90, 7) + Fraction(1, 6))

    def test_arithmetic_bad_operands_and_operation_are_compile_errors(self):
        for operand in ({'numerator': 1, 'denominator': 0}, {'numerator': True, 'denominator': 1},
                        {'numerator': 1.0, 'denominator': 1}, {'numerator': 10**101, 'denominator': 1}):
            request = copy.deepcopy(ARITHMETIC); request['params']['left'] = operand
            self.refusal(request)
        request = copy.deepcopy(ARITHMETIC); request['params']['operation'] = '+ show hidden'
        self.refusal(request, 'operation')
        request = copy.deepcopy(ARITHMETIC); request['params'].update(operation='divide', right={'numerator': 0, 'denominator': 1})
        self.refusal(request, 'division_by_zero')
        self.refusal({**ARITHMETIC, 'calls': 1}, 'range')

    def test_proof_uses_caller_goal_and_rejects_unrelated_derivation(self):
        task = D.compile_task(PROOF)
        invalid = {'version': 1, 'proof': ['premise', 'p']}
        valid = {'version': 1, 'proof': ['implies_elim', ['premise', 'rule'], ['premise', 'p']]}
        run, report, apps = execute(task, [invalid, valid])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 2)
        result = run.kernel.env.lookup(task['output_binding']).value
        self.assertTrue(result['valid'])
        self.assertEqual(S.canon(result['conclusion']), ['atom', 'B'])
        self.assertTrue(task['assurance']['conditional'])
        self.assertEqual(task['inputs']['premises']['p'], ['atom', 'A'])
        self.assertEqual(task['inputs']['goal'], ['atom', 'B'])

    def test_finite_flat_proof_reuses_existing_compiler_and_its_rules(self):
        task = D.compile_task({'template': 'proof', 'params': {'domains': {'People': ['Ada']},
            'premises': 'p: forall x in People: Kind(x:People)', 'goal': 'Kind(People["Ada"])', 'certificate_format': 'steps'}})
        certificate = {'version': 1, 'steps': [{'id': 's', 'rule': 'premise', 'args': ['p'], 'formula': None}], 'result': 's'}
        run, report, apps = execute(task, [certificate])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 1)
        self.assertTrue(run.kernel.env.lookup('verification').value['conditional_on_domains'])
        self.assertIn('finite_steps_check', task['source'])
        self.assertIn('from expanded, proof_rules', task['source'])

    def test_request_bounds_unknowns_cycles_alias_expansion_and_invalid_json(self):
        for update in ({'calls': 0}, {'calls': 7}, {'calls': True}, {'context_budget': -1},
                       {'context_budget': 131073}, {'max_steps': 0}, {'max_steps': 1000001},
                       {'unadvertised': True}, {'template': 'missing'}):
            self.refusal({**TRANSFORM, **update})
        self.refusal(None, 'shape')
        for value in (float('nan'), float('inf'), object(), '\ud800', 1 << 4000):
            request = copy.deepcopy(TRANSFORM); request['params']['data'] = value
            self.refusal(request)
        request = copy.deepcopy(TRANSFORM); request['params']['data'] = request
        self.refusal(request, 'cycle')
        request = copy.deepcopy(TRANSFORM); request['params']['data'] = ['x' * 4096] * 200
        self.refusal(request, 'bounds')
        request = copy.deepcopy(TRANSFORM); request['params']['data'] = 'x' * (D.MAX_TEXT + 1)
        self.refusal(request, 'bounds')


if __name__ == '__main__':
    unittest.main()
