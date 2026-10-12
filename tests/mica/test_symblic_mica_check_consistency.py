"""Pure admission regressions for original/public versus proposed unit checks."""
import copy
import unittest
from unittest import mock

from symblic.mica import contracts as C
from symblic.js import check as JS
from tests.mica.test_symblic_mica_contracts import request, unit


def shape(root_call='inc(2)', root_expected='3', unit_call=None, unit_expected=None):
    req = request()
    req['tests'][0].update(call=root_call, expected=root_expected)
    row = unit()
    row['unit']['examples'] = [[unit_call or root_call, root_expected if unit_expected is None else unit_expected]]
    return req, {'id': 'consistency', 'contracts': [row]}


class ConsistencyTest(unittest.TestCase):
    def conflict(self, req, plan, index=0):
        original = copy.deepcopy((req, plan))
        with mock.patch.object(JS, 'test', side_effect=AssertionError('admission cannot execute JavaScript')), \
             mock.patch('subprocess.run', side_effect=AssertionError('admission cannot spawn')):
            with self.assertRaises(C.ContractError) as caught:
                C.validate_plan(req, plan)
        self.assertEqual(caught.exception.code, 'unit_example_conflict')
        self.assertIn('original root test ' + str(index), str(caught.exception))
        self.assertEqual((req, plan), original)
        return str(caught.exception)

    def test_original_sum_and_clamp_pilot_contradictions_are_rejected(self):
        for name, signature, call, expected, proposed in [
            ('sum', 'sum(values)', 'sum([1,2,3])', '6', '{"result":6}'),
            ('clamp', 'clamp(x,lo,hi)', 'clamp(12,0,10)', '10', '{"result":"10"}')]:
            with self.subTest(name=name):
                req, plan = shape(call, expected, call.replace(',', ', '), proposed)
                req['exports'] = [{'name': name, 'signature': signature}]
                plan['contracts'][0]['unit'].update(names=[name], heading=signature)
                text = self.conflict(req, plan)
                self.assertIn('Original expected JSON: ' + expected, text)
                self.assertIn('proposed expected JSON: ' + proposed, text)

    def test_literal_trivia_and_string_escapes_match_without_evaluation(self):
        req, plan = shape('inc(["a",true,null,{"x":1}])', '1',
                          '  inc ( [ "\\u0061", true , null , { "x" : 1 } ] )\n', '2')
        self.conflict(req, plan)
        req, plan = shape('inc(2)', '3', 'inc(2)', '4')
        self.conflict(req, plan)

    def test_expected_comparison_reuses_json_number_and_object_semantics(self):
        for original, proposed in [('1', '1.00'), ('0', '-0'),
                                   ('{"a":[1,true],"b":null}', '{"b":null,"a":[1.0,true]}')]:
            req, plan = shape(root_expected=original, unit_expected=proposed)
            sealed = C.validate_plan(req, plan)
            self.assertEqual(sealed['root_tests'], req['tests'])
            self.assertEqual(sealed['contracts'][0]['unit']['examples'], plan['contracts'][0]['unit']['examples'])
            self.assertEqual(C.validate_plan(req, sealed), sealed)
        self.conflict(*shape(root_expected='true', unit_expected='1'))
        self.conflict(*shape(root_expected='"1"', unit_expected='1'))

    def test_argument_types_negative_zero_numbers_and_object_order_do_not_merge(self):
        pairs = [('inc(true)', 'inc(1)'), ('inc("1")', 'inc(1)'), ('inc(-0)', 'inc(0)'),
                 ('inc(9007199254740992)', 'inc(9007199254740993)'),
                 ('inc(1)', 'inc(1.0)'), ('inc(1e0)', 'inc(1)'),
                 ('inc({"a":1,"b":2})', 'inc({"b":2,"a":1})')]
        for root_call, example_call in pairs:
            with self.subTest(root=root_call, example=example_call):
                req, plan = shape(root_call, '1', example_call, '2')
                self.assertEqual(C.validate_plan(req, plan)['root_tests'], req['tests'])
        # Identical unsafe lexemes still denote the same literal; no rounding occurs.
        self.conflict(*shape('inc(9007199254740993)', '1', unit_expected='2'))

    def test_setup_dependencies_helpers_and_signature_mismatch_remain_unassessed(self):
        req, plan = shape(unit_expected='4')
        plan['contracts'][0]['unit']['setup'] = 'const fixture = 2;'
        C.validate_plan(req, plan)
        req, plan = shape(unit_expected='4')
        plan['contracts'][0]['unit']['heading'] = 'inc(value)'
        C.validate_plan(req, plan)
        req, plan = shape(unit_expected='4')
        plan['contracts'][0]['dependency_contract_ids'] = ['helper']
        plan['contracts'][0]['unit']['uses'] = ['helper']
        helper = unit('helper', 'helper')
        helper['unit']['examples'] = [['helper(2)', '4']]
        plan['contracts'].append(helper)
        C.validate_plan(req, plan)
        req, plan = shape()
        helper = unit('helper', 'helper')
        helper['unit']['examples'] = [['inc(2)', '4']]
        plan['contracts'].append(helper)
        C.validate_plan(req, plan)

    def test_arbitrary_js_and_unsupported_literal_forms_are_not_normalized(self):
        for call in ['inc(1+1)', 'inc(helper())', 'inc(...[2])', 'inc(/* note */2)',
                     'inc({"__proto__":null})', 'inc({"x":1,"x":2})',
                     'inc(2);', '(inc)(2)', 'inc(' + '[' * 18 + '2' + ']' * 18 + ')']:
            with self.subTest(call=call):
                req, plan = shape(call, '1', unit_expected='2')
                C.validate_plan(req, plan)

    def test_conflicting_original_tests_identify_original_index_without_rewriting_authority(self):
        req, plan = shape()
        req['tests'].append({**req['tests'][0], 'expected': '4'})
        text = self.conflict(req, plan, index=1)
        self.assertIn('Original expected JSON: 4', text)
        self.assertIn('proposed expected JSON: 3', text)

    def test_compound_exact_signatures_and_root_tests_are_preserved(self):
        req, plan = shape(unit_expected='4')
        req['exports'].append({'name': 'double', 'signature': 'double(x)'})
        plan['contracts'][0]['unit'].update(names=['inc', 'double'], heading='inc(x), double(x)')
        self.conflict(req, plan)
        plan['contracts'][0]['unit']['examples'][0][1] = '3'
        sealed = C.validate_plan(req, plan)
        self.assertEqual(sealed['root_tests'], req['tests'])


if __name__ == '__main__':
    unittest.main()
