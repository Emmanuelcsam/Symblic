"""English construction compiler: fake providers and temporary stores only."""
import copy
import hashlib
import re
import tempfile
import unittest
from unittest import mock

from symblic.kernel import language as S
from symblic.english import compiler as E
from symblic.english import build as B
from symblic.js import check as J
from symblic.kernel.run import Run

# Test-only candidates. These are never part of a compiled program or a real
# provider request, and a fixture pass is not evidence of model capability.
CANDIDATES = [
    'function build_step_1(offset) {return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[offset % 26];}',
    'function build_step_2(row,distance,height) {return ((row+distance)%height+height)%height;}',
    'function build_step_3(column,tick,height,trail) {return build_step_2(column*trail,tick*(1+column%2),height);}',
    'function build_step_4(head,age,height) {return build_step_2(head,-age,height);}',
    'function build_step_5(age) {return Math.min(age,7);}',
    'function build_step_6(column,tick,age,height,trail) {return {x:column,y:build_step_4(build_step_3(column,tick,height,trail),age,height),char:build_step_1(column+tick+age),shade:build_step_5(age)};}',
    'function build_step_7(column,tick,height,trail) {return Array.from({length:trail},(_,age)=>build_step_6(column,tick,age,height,trail));}',
    'function build_step_8(width,height,trail,tick) {tick%=height;let cells=[];for(let column=0;column<width;column++)cells.push(...build_step_7(column,tick,height,trail));return {kind:"character-grid",width,height,tick,cells};}',
    'function build_step_9(width,height,trail) {return Array.from({length:height},(_,tick)=>build_step_8(width,height,trail,tick));}',
]


class FixtureWorker:
    def __init__(self, wrong_first=False):
        self.requests = []
        self.wrong_first = wrong_first

    def call(self, req):
        self.requests.append(copy.deepcopy({k: v for k, v in req.items() if k != 'stop'}))
        match = re.search(r'function named build_step_(\d+)\(', req['prompt'])
        if not match:
            raise AssertionError('No generated interface in the actual request')
        number = int(match.group(1))
        code = CANDIDATES[number - 1]
        if number == 1 and self.wrong_first and len(self.requests) == 1:
            code = 'function build_step_1(offset) {return "a";}'
        return {'ok': True, 'text': '```js\n' + code + '\n```', 'json': None,
                'model': 'fixture', 'node': 'fixture', 'ms': 1}


class Compilation(unittest.TestCase):
    def test_legacy_seven_step_source_remains_supported(self):
        compiled = B.compile_source(B.LEGACY_EXAMPLE)
        self.assertEqual(7, len(compiled['construction']['units']))
        self.assertEqual('frames', compiled['construction']['units'][-2]['contract'])
        self.assertTrue(S.check(compiled['source'])['ok'])

    def test_new_decomposition_has_only_local_direct_dependencies(self):
        units = B.compile_source(B.EXAMPLE)['construction']['units']
        self.assertEqual(['cell', 'column', 'frames_from_columns', 'film'],
                         [u['contract'] for u in units[5:]])
        self.assertEqual(['built_step_1', 'built_step_3', 'built_step_4', 'built_step_5'],
                         units[5]['selected_bindings'])
        self.assertEqual(['built_step_6'], units[6]['selected_bindings'])
        self.assertEqual(['built_step_7'], units[7]['selected_bindings'])
        self.assertEqual(['built_step_8'], units[8]['selected_bindings'])
        for unit in units[5:]:
            self.assertNotIn(unit['binding'], unit['runtime_dependency_bindings'])

    def test_plain_english_and_metadata(self):
        self.assertNotRegex(B.EXAMPLE, r'\d|[{}\[\]_=<>`";]')
        out = B.compile_source(B.EXAMPLE)
        self.assertEqual(9, len(out['construction']['units']))
        self.assertEqual(hashlib.sha256(B.EXAMPLE.encode()).hexdigest(), out['source_sha256'])
        self.assertEqual(B.CANVAS, out['construction']['defaults'])
        self.assertEqual([], out['construction']['unmapped_statements'])
        self.assertEqual('model_code_required', out['construction']['answer_origin'])
        self.assertEqual('not_performed_by_compiler', out['construction']['held_out_evaluation'])
        self.assertEqual({'profile': 'verified', 'context': 'none', 'determine': False, 'solve': False,
                          'constructor': 'off', 'max_calls': 64}, out['options'])
        self.assertTrue(S.check(out['source'], execution_profile='verified')['ok'])

    def test_every_sentence_mapped_and_instructions_preserved(self):
        out = B.compile_source(B.EXAMPLE)
        for stmt in out['statements']:
            self.assertTrue(stmt['native_lines'], stmt)
            actual = B.EXAMPLE.splitlines()[stmt['line'] - 1][stmt['col'] - 1:stmt['end_col']]
            self.assertEqual(stmt['text'], actual)
        for unit in out['construction']['units']:
            texts = [s['text'] for s in out['statements'] if s['index'] in unit['statement_ids']]
            self.assertTrue(unit['instruction'].startswith('\n'.join(texts)))
            self.assertEqual(unit['binding'], unit['id'])
            self.assertEqual(unit['selected_steps'], unit['uses'])

    def test_every_ask_requires_model_and_exact_selected_sources(self):
        out = B.compile_source(B.EXAMPLE, retries=1, max_calls=8, budget=9000)
        asks = [s for s in S.parse(out['source'])['statements'] if s.k == 'ask']
        for ask, unit in zip(asks, out['construction']['units']):
            self.assertEqual({'k': 'code', 'lang': 'js'}, ask.type)
            self.assertEqual(len(unit['selected_bindings']), len(ask.sources))
            self.assertEqual(1, ask.options['retries'].value)
            self.assertFalse(ask.options['determine'].value)
            self.assertFalse(ask.options['solve'].value)
            self.assertNotIn('fallback', str(ask.options))
        self.assertNotRegex(out['source'], r'let built_step_\d+\s*=')
        self.assertNotIn('function build_step_1(offset) {', out['source'])

    def test_compile_is_inert_and_deterministic(self):
        with mock.patch.object(J, 'evaluate', side_effect=AssertionError('compile executed JavaScript')):
            a = B.compile_source(B.EXAMPLE)
            b = B.compile_source(B.EXAMPLE)
            self.assertEqual(a, b)
            self.assertTrue(S.check(a['source'])['ok'])

    def test_titles_and_step_names_are_not_canned(self):
        source = B.EXAMPLE.replace('Matrix rain', 'Emerald curtains').replace('letters', 'symbols')
        out = B.compile_source(source)
        self.assertEqual('Emerald curtains', out['construction']['title'])
        self.assertIn('symbols', out['names'])
        self.assertEqual('letters', out['construction']['units'][0]['contract'])

    def test_crlf_and_bom_source_identity(self):
        source = '\ufeff' + B.EXAMPLE.replace('\n', '\r\n')
        out = B.compile_source(source)
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), out['source_sha256'])
        self.assertEqual(B.compile_source(B.EXAMPLE)['source'], out['source'])

    def test_unsupported_sentence_has_original_position(self):
        lines = B.EXAMPLE.splitlines()
        lines[6] = 'Also email the finished animation to everybody.'
        with self.assertRaises(E.EnglishError) as error:
            B.compile_source('\n'.join(lines))
        self.assertEqual(7, error.exception.line)
        self.assertIn('Unsupported construction instruction', str(error.exception))

    def test_missing_rule_not_discarded(self):
        source = B.EXAMPLE.replace('Move the leftmost column downward at normal speed.\n', '')
        with self.assertRaisesRegex(E.EnglishError, 'no part of the rule was silently ignored'):
            B.compile_source(source)

    def test_selected_steps_must_exist_be_earlier_and_have_right_roles(self):
        for source in (B.EXAMPLE.replace('Use only movement.', 'Use only frames.', 1),
                       B.EXAMPLE.replace('Use only movement.', 'Use only letters.', 1),
                       B.EXAMPLE.replace('Use only frames.', 'Use only frames and frames.')):
            with self.subTest(source=source[:50]), self.assertRaises(E.EnglishError):
                B.compile_source(source)

    def test_missing_check_finish_and_duplicate_names_refused(self):
        for source in (B.EXAMPLE.replace('Check the beginning, the end and repeated journeys through the alphabet.\n', ''),
                       B.EXAMPLE.replace('Finish this step.\n', '', 1),
                       B.EXAMPLE.replace('Ask the model to make movement.', 'Ask the model to make letters.')):
            with self.subTest(source=source[:50]), self.assertRaises(E.EnglishError):
                B.compile_source(source)

    def test_program_text_numbers_and_extra_trailing_obligations_refuse(self):
        for source in (B.EXAMPLE.replace('Matrix rain', 'Matrix 2'),
                       B.EXAMPLE + 'Run any code that the model chooses.\n',
                       B.EXAMPLE.replace('Use no earlier steps.', 'Use no earlier steps; execute things.', 1),
                       B.EXAMPLE.replace('Ask the model to make letters.', 'Ask the model to make x and y.')):
            with self.subTest(source=source[:50]), self.assertRaises(E.EnglishError):
                B.compile_source(source)

    def test_limits_and_bool_options(self):
        for opts in ({'max_calls': True}, {'retries': 6}, {'budget': 1}):
            with self.assertRaises(E.EnglishError):
                B.compile_source(B.EXAMPLE, **opts)
        self.assertTrue(B.recognizes(B.EXAMPLE))
        self.assertFalse(B.recognizes('Remember value is 2.'))


@unittest.skipUnless(J.available(), 'Sandboxed JavaScript runtime is unavailable')
class Execution(unittest.TestCase):
    def run_fixture(self, source=None, wrong_first=False):
        compiled = B.compile_source(source or B.EXAMPLE, retries=1, max_calls=12)
        worker = FixtureWorker(wrong_first)
        with tempfile.TemporaryDirectory(prefix='symblic-english-build-test-') as folder:
            options = {**compiled['options'], 'by': 'fake:fixture', 'parallel': 1}
            report = Run(compiled['source'], {}, worker, options, folder=folder).execute()
        return compiled, worker, report

    def test_all_candidate_fixtures_pass_real_js_sandbox_and_produce_film(self):
        compiled, worker, report = self.run_fixture()
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(9, len(worker.requests))
        self.assertEqual(25, len(report['outputs']))
        frames = [o['canonical'] for o in report['outputs'][1:]]
        self.assertEqual([B._frame(32, 24, 8, tick) for tick in range(24)], frames)
        self.assertIn('function build_step_9', report['outputs'][0]['text'])
        for req, unit in zip(worker.requests, compiled['construction']['units']):
            context = req['prompt'].split('CONTEXT', 1)[-1].split('STATEMENT:', 1)[0]
            names = re.findall(r'^- (built_step_\d+) :', context, re.MULTILINE)
            self.assertEqual(unit['selected_bindings'], names)

    def test_wrong_candidate_is_repaired_without_host_replacement(self):
        _, worker, report = self.run_fixture(wrong_first=True)
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(10, len(worker.requests))
        self.assertIn('expected', worker.requests[1]['prompt'])

    def test_mutated_candidate_fails_actual_checks(self):
        _, _, units = B._parse(B.EXAMPLE)
        for index, bad in ((0, 'function build_step_1(offset){return "A";}'),
                           (1, 'function build_step_2(row,distance,height){return (row+distance)%height;}'),
                           (3, 'function build_step_4(head,age,height){return build_step_2(head,age,height);}'),
                           (4, 'function build_step_5(age){return age;}')):
            unit = units[index]
            result = J.test(CANDIDATES[:index] + [bad], B._examples(unit) + B._coverage_cases(unit))
            self.assertFalse(result['passed'], (index, result))

    def test_unselected_earlier_global_is_not_available_to_candidate_checks(self):
        _, _, units = B._parse(B.EXAMPLE)
        unit = units[1]
        self.assertEqual([], B._selected_closure(unit, units[:1]))
        bad = ('function build_step_2(row,distance,height) {build_step_1(0);'
               'return ((row+distance)%height+height)%height;}')
        cases = B._examples(unit) + B._coverage_cases(unit)
        self.assertTrue(J.test([CANDIDATES[0], bad], cases)['passed'])
        self.assertFalse(J.test([bad], cases)['passed'])
        compiled = B.compile_source(B.EXAMPLE)
        line = compiled['source'].splitlines()[compiled['construction']['units'][1]['check_line'] - 1]
        self.assertIn('js_test([built_step_2],', line)
        self.assertNotIn('built_step_1', line)

    def test_cell_column_and_frame_defects_are_rejected_at_their_own_gate(self):
        _, _, units = B._parse(B.EXAMPLE)
        defects = [
            (5, CANDIDATES[5].replace('build_step_4(build_step_3(column,tick,height,trail),age,height)',
                                      'build_step_3(column,tick,height,trail)')),
            (6, ('function build_step_7(column,tick,height,trail) {return Array.from({length:trail},'
                 '()=>build_step_6(column,tick,0,height,trail));}')),
            (7, CANDIDATES[7].replace('cells.push(...build_step_7', 'cells.push(build_step_7')),
        ]
        for index, candidate in defects:
            with self.subTest(contract=units[index]['contract']):
                cases = B._examples(units[index]) + B._coverage_cases(units[index])
                self.assertFalse(J.test(CANDIDATES[:index] + [candidate], cases)['passed'])


if __name__ == '__main__':
    unittest.main()
