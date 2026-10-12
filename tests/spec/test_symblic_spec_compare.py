"""Differential probes use fake protocols or the local sandbox, never providers."""

import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.js import check as JS
from symblic.spec import sheets as SP
from symblic.spec import compare as D
from symblic.spec import contracts as C

SHEET = '''# output.js
## Unit `f(x)`
Return x+1 for integer inputs.
Examples:
    f(1) ==> 2
## Assemble `output.js`
    /*UNITS*/
'''
GOOD = 'function f(x){return x+1;}'
WRONG = 'function f(x){return x === -7 ? 900 : x+1;}'
CANDIDATES = [{'label': 'caller-A', 'source': GOOD}, {'label': 'caller-B', 'source': WRONG}]


def value(text):
    return {'ok': True, 'value': text}


class Protocol(unittest.TestCase):
    def invoke(self, results, probes=None, candidates=None, **options):
        with patch.object(JS, 'evaluate', side_effect=results) as evaluate:
            result = D.compare(SHEET, CANDIDATES if candidates is None else candidates,
                               ['f(-7)'] if probes is None else probes, **options)
        return result, evaluate

    def assertCode(self, code, function):
        with self.assertRaises(D.CompareError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.as_dict()['code'], code)

    def test_valid_divergence_proposes_question_without_choosing_majority(self):
        result, call = self.invoke([[value('2')], [value('2')], [value('-6')], [value('900')]])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['probes'][0]['status'], 'divergent')
        self.assertEqual(result['proposed_examples'][0]['expected_json'], None)
        self.assertTrue(result['proposed_examples'][0]['requires_owner_resolution'])
        self.assertEqual(result['assurance']['expected_answers'], 'not_chosen')
        self.assertEqual(result['work']['requested_evaluations'], 4)
        self.assertEqual(len({row.kwargs['deadline'] for row in call.call_args_list}), 1)
        self.assertTrue(all(row.kwargs['max_output_bytes'] == D.MAX_BATCH_OUTPUT_BYTES for row in call.call_args_list))

    def test_exposed_mismatch_excludes_candidate_from_differential_vote(self):
        result, call = self.invoke([[value('0')], [value('2')], [value('900')]])
        self.assertEqual(call.call_count, 3)
        self.assertEqual(result['candidates'][0]['exposed_checks'], 'failed')
        self.assertEqual(result['candidates'][0]['probes'][0]['status'], 'not_evaluated')
        self.assertEqual(result['probes'][0]['status'], 'unresolved')
        self.assertEqual(result['proposed_examples'], [])

    def test_probe_errors_are_unresolved_not_alternative_answers(self):
        result, _ = self.invoke([[value('2')], [value('2')], [value('-6')],
                                 [{'ok': False, 'kind': 'error', 'error': 'ReferenceError'}]])
        row = result['probes'][0]
        self.assertEqual(row['status'], 'unresolved')
        self.assertEqual(len(row['alternatives']), 1)
        self.assertEqual(row['unresolved'][0]['label'], 'caller-B')
        self.assertEqual(result['proposed_examples'], [])

    def test_json_semantics_ignore_object_order_and_numeric_spelling(self):
        result, _ = self.invoke([[value('2')], [value('2')],
                                 [value('{"x":1,"y":[0]}')], [value('{"y":[-0.0],"x":1.00}')]])
        self.assertEqual(result['probes'][0]['status'], 'agreement')
        self.assertEqual(len(result['probes'][0]['alternatives']), 1)
        first, second = (row['probes'][0] for row in result['candidates'])
        self.assertEqual(first['value_sha256'], second['value_sha256'])
        self.assertNotEqual(first['json_text_sha256'], second['json_text_sha256'])
        self.assertFalse(result['exact_source_agreement']['all_equal'])
        self.assertEqual(result['assurance']['universal_equivalence'], 'not_established')

    def test_boolean_and_number_are_not_grouped_together(self):
        result, _ = self.invoke([[value('2')], [value('2')], [value('true')], [value('1')]])
        self.assertEqual(result['probes'][0]['status'], 'divergent')
        self.assertNotEqual(*[row['value_sha256'] for row in result['probes'][0]['alternatives']])

    def test_duplicate_or_nonfinite_json_is_not_valid_divergence(self):
        for text in ('{"x":1,"x":2}', 'NaN', 'Infinity', 'not JSON', '[' * 40 + '0' + ']' * 40):
            with self.subTest(text=text):
                result, _ = self.invoke([[value('2')], [value('2')], [value('-6')], [value(text)]])
                self.assertEqual(result['probes'][0]['status'], 'unresolved')
                self.assertEqual(result['proposed_examples'], [])
                self.assertEqual(result['candidates'][1]['probes'][0]['kind'], 'invalid_json')

    def test_output_caps_keep_budget_outcome_and_no_large_retained_answer(self):
        with patch.object(D, 'MAX_VALUE_BYTES', 10):
            result, _ = self.invoke([[value('2')], [value('2')], [value('-6')], [value('"' + 'x' * 20 + '"')]])
        row = result['candidates'][1]['probes'][0]
        self.assertEqual(row['status'], 'budget')
        self.assertEqual(row['kind'], 'output_limit')
        self.assertNotIn('value_json', row)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['proposed_examples'], [])

    def test_stream_overflow_is_budget_and_does_not_restart_with_larger_limits(self):
        result, call = self.invoke([[value('2')], [value('2')],
                                    JS.JsError('output too large', kind='budget'), [value('900')]])
        self.assertEqual(call.call_count, 4)
        self.assertEqual(result['candidates'][0]['probes'][0]['status'], 'budget')
        self.assertEqual(result['proposed_examples'], [])

    def test_runtime_unavailability_and_os_errors_preserve_unknown_denominator(self):
        with patch.object(D, 'runtime_identity', side_effect=JS.JsError('missing', kind='unavailable')), \
                patch.object(JS, 'evaluate', side_effect=AssertionError('unavailable runtime dispatched')):
            result = D.compare(SHEET, CANDIDATES, ['f(-7)'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['candidates']), 2)
        self.assertTrue(all(row['exposed_checks'] == 'unresolved' for row in result['candidates']))
        result, call = self.invoke(OSError('synthetic launch failure'))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result['proposed_examples'], [])

    def test_malformed_sandbox_protocol_is_unknown(self):
        for bad in ({}, [], [True], [{'ok': 'yes', 'value': '2'}], [{'ok': True, 'value': 2}]):
            with self.subTest(bad=bad):
                result, _ = self.invoke([bad, [value('2')], [value('900')]])
                self.assertFalse(result['candidates'][0]['eligible_for_comparison'])
                self.assertEqual(result['proposed_examples'], [])

    def test_source_drift_retains_observations_but_disables_questions(self):
        runtime = D.runtime_identity()
        with patch.object(D, 'runtime_identity', return_value=runtime), patch.object(D, '_source_hashes', return_value={}):
            result, _ = self.invoke([[value('2')], [value('2')], [value('-6')], [value('900')]])
        self.assertTrue(result['runtime_drift'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['probes'][0]['status'], 'unresolved')
        self.assertEqual(result['proposed_examples'], [])

    def test_exact_source_identity_preserves_script_boundaries(self):
        one = [{'label': 'a', 'source': GOOD}, {'label': 'b', 'source': [GOOD]}]
        result, _ = self.invoke([[value('2')], [value('2')], [value('0')], [value('0')]], candidates=one)
        self.assertTrue(result['exact_source_agreement']['all_equal'])
        split = [{'label': 'a', 'source': GOOD + '\n;'}, {'label': 'b', 'source': [GOOD, ';']}]
        result, _ = self.invoke([[value('2')], [value('2')], [value('0')], [value('0')]], candidates=split)
        self.assertFalse(result['exact_source_agreement']['all_equal'])

    def test_every_exposed_unit_is_checked_even_after_known_mismatch(self):
        sheet = SHEET.replace('## Assemble', '## Unit `g(x)`\nReturn x.\nExamples:\n    g(2) ==> 2\n## Assemble')
        with patch.object(JS, 'evaluate', side_effect=[[value('0')], [value('2')], [value('2')], [value('2')], [value('2')]]) as call:
            result = D.compare(sheet, CANDIDATES, ['f(-7)'])
        self.assertEqual(call.call_count, 5)
        self.assertEqual([len(row['checks']) for row in result['candidates']], [2, 2])
        self.assertEqual([row.args[1][0] for row in call.call_args_list[:4]], ['f(1)', 'f(1)', 'g(2)', 'g(2)'])

    def test_expected_json_is_data_never_inserted_into_executable_calls(self):
        expected = json.dumps('(()=>{throw new Error("injected")})()')
        sheet = SHEET.replace('==> 2', '==> ' + expected)
        with patch.object(JS, 'evaluate', side_effect=[[value(expected)], [value(expected)]]) as call:
            result = D.compare(sheet, [CANDIDATES[0]], ['f(0)'])
        self.assertTrue(result['candidates'][0]['eligible_for_comparison'])
        self.assertEqual([row.args[1] for row in call.call_args_list], [['f(1)'], ['f(0)']])
        self.assertTrue(all('injected' not in piece for row in call.call_args_list for piece in row.args[0]))

    def test_empty_unknown_large_and_ambiguous_inputs_refuse_before_runtime(self):
        invalid = [([], ['f(0)']), (CANDIDATES, []), (CANDIDATES * 5, ['f(0)']),
                   ([{'label': 'x', 'source': GOOD}, {'label': 'x', 'source': GOOD}], ['f(0)']),
                   ([{'label': 'x', 'source': [None]}], ['f(0)']),
                   ([{'label': 'x', 'source': 'x' * (JS.MAX_SOURCE + 1)}], ['f(0)']),
                   (CANDIDATES, ['f(0)'] * 65),
                   (CANDIDATES, [{'id': 'p', 'expression': 'f(0)', 'expected': '1'}]),
                   (CANDIDATES, [{'id': 'p', 'expression': 'f(0)', 'unit_id': 'missing'}]),
                   (CANDIDATES, [{'id': 'p', 'expression': 'f(0)'}] * 2)]
        with patch.object(D, 'runtime_identity', side_effect=AssertionError('invalid request reached runtime')):
            for candidates, probes in invalid:
                with self.subTest(candidates=len(candidates), probes=len(probes)):
                    self.assertCode('input', lambda candidates=candidates, probes=probes: D.compare(SHEET, candidates, probes))
            self.assertCode('spec', lambda: D.compare(SHEET.replace('output.js', 'output.html'), CANDIDATES, ['f(0)']))
            self.assertCode('budget', lambda: D.compare(SHEET, CANDIDATES, ['f(0)'], deadline_seconds=True))
            with patch.object(D, 'MAX_EVALUATIONS', 3):
                self.assertCode('work_limit', lambda: D.compare(SHEET, CANDIDATES, ['f(0)']))

    def test_cli_json_is_review_only_and_preserves_request_file(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / 'request.json'
            raw = json.dumps({'sheet': SHEET, 'candidates': CANDIDATES, 'probes': ['f(-7)']})
            request.write_text(raw)
            output = io.StringIO()
            with patch.object(JS, 'evaluate', side_effect=[[value('2')], [value('2')], [value('-6')], [value('900')]]), \
                    contextlib.redirect_stdout(output):
                code = D.main([str(request), '--agent-json'])
            self.assertEqual(code, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['proposed_examples'][0]['expected_json'], None)
            self.assertEqual(request.read_text(), raw)


@unittest.skipUnless(JS.available(), 'local sandboxed node is unavailable')
class RealSandbox(unittest.TestCase):
    def test_candidate_cannot_spoof_results_by_replacing_or_shadowing_serializer(self):
        sources = ['function f(x){return 0;} JSON.stringify=function(){return "2";};',
                   'function f(x){JSON.stringify=function(){return "2";};return 0;}',
                   'const JSON={stringify(){return "2";}}; function f(x){return 0;}']
        for source in sources:
            with self.subTest(source=source):
                result = D.compare(SHEET, [{'label': 'spoof', 'source': source}, CANDIDATES[0]], ['f(-7)'])
                self.assertFalse(result['candidates'][0]['eligible_for_comparison'])
                self.assertEqual(result['proposed_examples'], [])

    def test_counterexample_allows_owner_to_see_underspecified_sample(self):
        result = D.compare(SHEET, CANDIDATES, ['f(1)', 'f(-7)'])
        self.assertTrue(all(row['eligible_for_comparison'] for row in result['candidates']))
        self.assertEqual([row['status'] for row in result['probes']], ['agreement', 'divergent'])
        self.assertEqual([row['value_json'] for row in result['probes'][1]['alternatives']], ['-6', '900'])
        self.assertEqual(result['proposed_examples'][0]['expected_json'], None)

    def test_probe_setup_is_explicit_and_used_identically(self):
        sheet = SHEET.replace('Return x+1 for integer inputs.', 'Return x+base.\nTest setup:\n    const base=1;')
        unit_id = C.plan(SP.parse(sheet))['units'][0]['id']
        candidates = [{'label': label, 'source': 'function f(x){return x+base;}'} for label in ('a', 'b')]
        result = D.compare(sheet, candidates, ['f(-7)', {'id': 'with-setup', 'expression': 'f(-7)', 'unit_id': unit_id}])
        self.assertEqual(result['probes'][0]['status'], 'unresolved')
        self.assertEqual(result['probes'][1]['status'], 'agreement')

    def test_syntax_error_timeout_and_large_output_remain_unresolved(self):
        broken = [{'label': 'syntax', 'source': 'function f( {'}, CANDIDATES[0]]
        result = D.compare(SHEET, broken, ['f(-7)'])
        self.assertFalse(result['candidates'][0]['eligible_for_comparison'])
        self.assertEqual(result['candidates'][0]['checks'][0]['kind'], 'syntax')
        large = [{'label': label, 'source': 'function f(x){return x===1?2:"x".repeat(600000);}'} for label in ('a', 'b')]
        result = D.compare(SHEET, large, ['f(-7)'])
        self.assertEqual(result['proposed_examples'], [])
        self.assertTrue(all(row['probes'][0]['status'] == 'budget' for row in result['candidates']))
        looping = [{'label': 'loop', 'source': 'function f(x){if(x===1)return 2;while(true){}}'}, CANDIDATES[0]]
        start = time.monotonic()
        result = D.compare(SHEET, looping, ['f(-7)'], deadline_seconds=0.4)
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(result['proposed_examples'], [])
        self.assertEqual(result['status'], 'partial')


if __name__ == '__main__':
    unittest.main()
