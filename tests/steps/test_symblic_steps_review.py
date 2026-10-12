"""Review regressions: native execution with fake providers and private stores."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import execution_pins as X
from symblic.steps import construction as C
from symblic.steps import recovery as API
from symblic.authoring import workcards as W
from symblic.kernel.run import Run
from tests.delegate.test_symblic_delegate import Fake


def request(choices=None, checks=None):
    return {'title': 'Checked arithmetic', 'steps': [{
        'name': 'twice', 'instruction': 'Double the integer x.',
        'parameters': [{'name': 'x', 'type': 'Int'}], 'returns': 'Int', 'uses': [],
        'choices': choices or ['x + 3', 'x + 1', 'x * 2'],
        'checks': checks or ['twice(3) = 6', 'twice(0) = 0']}],
        'final_checks': ['twice(4) = 8'], 'program': 'show twice(5).'}


class RetryBudget(unittest.TestCase):
    def execute(self, task, answers, retries=1):
        compiled = C.compile_sequence(task, 'fake:worker', retries=retries)
        fake = Fake(answers)
        report = Run(compiled['source'], compiled['inputs'], fake, compiled['options']).execute()
        return compiled, fake, report

    def test_partial_pass_then_new_failure_restarts_all_checks_with_one_budget(self):
        compiled, fake, report = self.execute(request(), ['x + 3', 'x + 1', 'x * 2'])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'check')
        self.assertNotIn('max_asks', report['error']['message'])
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.answers, ['x * 2'])
        self.assertEqual(report['outputs'], [])
        self.assertEqual(len([s for s in S.parse(compiled['source'])['statements'] if s.k == 'ensure']), 1)
        for check in request()['steps'][0]['checks']:
            self.assertIn(check, fake.requests[1]['prompt'])

    def test_alternating_failures_cannot_spend_the_next_steps_quota(self):
        task = request()
        task['steps'].append({'name': 'plusone', 'instruction': 'Add one to x.',
            'parameters': [{'name': 'x', 'type': 'Int'}], 'returns': 'Int', 'uses': [],
            'choices': ['x + 1'], 'checks': ['plusone(4) = 5']})
        _, fake, report = self.execute(task, ['x + 3', 'x + 1', 'x * 2', 'x + 1'])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'check')
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.answers, ['x * 2', 'x + 1'])
        self.assertTrue(all('brick_choice_0' in r['prompt'] for r in fake.requests))

    def test_repaired_first_step_leaves_a_full_retry_for_second_step(self):
        task = request()
        task['steps'].append({'name': 'plusone', 'instruction': 'Add one to x.',
            'parameters': [{'name': 'x', 'type': 'Int'}], 'returns': 'Int', 'uses': [],
            'choices': ['x - 1', 'x + 1'], 'checks': ['plusone(4) = 5']})
        task['final_checks'].append('plusone(0) = 1')
        _, fake, report = self.execute(task, ['x + 3', 'x * 2', 'x - 1', 'x + 1'])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(fake.requests), 4)
        self.assertEqual(report['outputs'][0]['value'], {'twice': 3, 'plusone': 2})

    def test_native_domain_and_type_errors_retry_without_removing_choices(self):
        for bad in ['[x][5]', 'x / 0', '"two"']:
            with self.subTest(expression=bad):
                task = request([bad, 'x * 2'])
                compiled, fake, report = self.execute(task, [bad, 'x * 2'])
                self.assertEqual(compiled['task']['steps'][0]['choices'], [bad, 'x * 2'])
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(len(fake.requests), 2)
                self.assertEqual(report['outputs'][0]['value'], {'twice': 2})

    def test_builtin_allowlist_is_native_and_excludes_denied_calls(self):
        self.assertLessEqual(C.BUILTINS, set(S.BUILTINS))
        self.assertFalse(C.BUILTINS & set(S.EVAL_DENIED))

    def test_exact_expression_answers_preserve_order_and_ordinal_output(self):
        task = request(['x * 2', 'x + x'])
        compiled, fake, report = self.execute(task, ['x + x'])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['outputs'][0]['value'], {'twice': 2})
        self.assertEqual(compiled['task']['steps'][0]['choices'], ['x * 2', 'x + x'])
        ask = next(n for n in S.parse(compiled['source'])['statements'] if n.k == 'ask')
        self.assertIn('one of', S.type_label(ask.type))
        self.assertIn('Return the exact expression', fake.requests[0]['prompt'])
        for invalid in [2, 'x*2']:
            with self.subTest(answer=invalid):
                _, fake, report = self.execute(task, [invalid], retries=0)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(len(fake.requests), 1)
                self.assertEqual(report['outputs'], [])

    def test_artifact_runtime_type_check_is_not_reported_as_preparation(self):
        task = request(['x * 2'])
        task['program'] = 'show twice("text").'
        artifact = C.assemble(task, {'twice': 1})
        self.assertEqual(artifact['execution'], 'not_run')
        fake = Fake()
        report = Run(artifact['source'], artifact['inputs'], fake, artifact['options']).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'type')
        self.assertEqual(fake.requests, [])

    def test_singleton_text_fallback_checks_membership_before_adoption(self):
        task = request(['x * 2'])
        compiled, fake, report = self.execute(task, ['unlisted', 'x * 2'])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(report['outputs'][0]['value'], {'twice': 1})
        self.assertIn('Text up to 4096 words', compiled['source'])
        self.assertEqual(compiled['task']['steps'][0]['choices'], ['x * 2'])
        _, fake, refused = self.execute(task, ['unlisted'], retries=0)
        self.assertEqual(refused['status'], 'failed')
        self.assertEqual(refused['error']['kind'], 'check')
        self.assertEqual(refused['outputs'], [])

    def test_native_normalization_collisions_preserve_exact_choices_and_order(self):
        task = request(['x * 2', 'x  * 2'])
        compiled, fake, report = self.execute(task, ['x*2', 'x  * 2'])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(report['outputs'][0]['value'], {'twice': 2})
        self.assertEqual(compiled['task']['steps'][0]['choices'], ['x * 2', 'x  * 2'])
        self.assertIn('Text up to 4096 words', compiled['source'])

    def test_enum_schema_keeps_record_and_interpolation_expression_bytes(self):
        cases = [
            (['{value: x}', '{value: x + 1}'], 'Record {value: Int}',
             ['twice(3).value = 3', 'twice(0).value = 0'], 'twice(4).value = 4'),
            (['"{x}"', '"constant"'], 'Text',
             ['twice(3) = "3"', 'twice(0) = "0"'], 'twice(4) = "4"'),
        ]
        for choices, returns, checks, final in cases:
            with self.subTest(choices=choices):
                task = request(choices, checks)
                task['steps'][0]['returns'] = returns
                task['final_checks'] = [final]
                compiled, fake, report = self.execute(task, [choices[0]])
                ask = next(n for n in S.parse(compiled['source'])['statements'] if n.k == 'ask')
                self.assertEqual(ask.type['options'], choices)
                self.assertEqual(fake.requests[0]['schema']['properties']['answer']['enum'], choices)
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(report['outputs'][0]['value'], {'twice': 1})
                artifact = C.assemble(task, {'twice': 1})
                no_models = Fake()
                result = Run(artifact['source'], artifact['inputs'], no_models, artifact['options']).execute()
                self.assertEqual(result['status'], 'done', result.get('error'))
                self.assertEqual(no_models.requests, [])


class StepsCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.request_path = self.root / 'request.json'
        self.request_path.write_text(json.dumps(request(['x + 1', 'x * 2'])))

    def cli(self, *arguments):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = W.main(list(arguments))
        return code, json.loads(stream.getvalue())

    def test_steps_fill_refuses_before_reading_files(self):
        with patch.object(W.A, '_load_json', side_effect=AssertionError('must not read')):
            code, result = self.cli('fill', '--kind', 'steps')
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'refused')
        self.assertIn('fill supports slots only', result['error'])

    def test_step_flags_do_not_silently_apply_to_other_commands(self):
        for args in [('compile', '--kind', 'slots'), ('result', '--kind', 'steps')]:
            with self.subTest(args=args), patch.object(W.A, '_load_json', side_effect=AssertionError('must not read')):
                code, result = self.cli(*args, '--retries', '1')
            self.assertEqual(code, 1)
            self.assertIn('apply only to steps', result['error'])

    def test_compile_and_prepare_return_pinned_handoff_with_exact_flags(self):
        for command in ['compile', 'prepare']:
            with self.subTest(command=command), patch.object(Run, 'execute', side_effect=AssertionError('compile must not run')):
                code, result = self.cli(command, '--kind', 'steps', '--request', str(self.request_path),
                    '--by', 'fake:worker', '--retries', '1', '--context-budget', '10000')
            self.assertEqual(code, 0)
            self.assertEqual(result['inputs']['_steps_settings'],
                             {'by': 'fake:worker', 'retries': 1, 'context_budget': 10000})
            self.assertEqual(result['options']['max_calls'], 2)
            self.assertEqual(X.validate(result['options']['execution_pins'], result['source'],
                                        result['inputs'])['source_sha256'], result['source_sha256'])

    def test_run_cli_preserves_flags_and_persists_recoverable_artifact(self):
        fake = Fake(['x + 1', 'x * 2'])
        original = W.run_card
        folder = self.root / 'run'
        def local_run(*args, **kwargs):
            return original(*args, applicators=fake, **kwargs)
        with patch.object(W, 'run_card', side_effect=local_run):
            code, result = self.cli('run', '--kind', 'steps', '--request', str(self.request_path),
                '--by', 'fake:worker', '--dir', str(folder), '--retries', '1', '--context-budget', '10000')
        self.assertEqual(code, 0, result)
        self.assertEqual(len(fake.requests), 2)
        meta = json.loads((folder / 'meta.json').read_text())
        record = json.loads((folder / 'card.json').read_text())
        self.assertEqual(record['steps_compiler_version'], C.VERSION)
        self.assertEqual(record['steps_compiler_sha256'], hashlib.sha256(Path(C.__file__).read_bytes()).hexdigest())
        self.assertEqual(meta['inputs']['_steps_settings']['retries'], 1)
        self.assertEqual(meta['inputs']['_steps_settings']['context_budget'], 10000)
        self.assertEqual(meta['options']['max_calls'], 2)
        self.assertTrue(API.from_folder(folder)['accepted'])
        self.assertTrue((folder / 'assembled.sym').is_file())

    def test_recovery_failure_persists_refusal_without_artifact_or_redispatch(self):
        folder = self.root / 'refused'
        fake = Fake(['x * 2'])
        with patch.object(API, 'from_folder', side_effect=API.StepsResultError('runtime pin changed')):
            result = W.run_card(request(['x + 1', 'x * 2']), kind='steps', folder=folder,
                                by='fake:worker', applicators=fake)
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(result['report']['status'], 'done')
        self.assertEqual(result['error'], 'runtime pin changed')
        self.assertEqual(json.loads((folder / 'workcard-result.json').read_text()), result)
        self.assertFalse((folder / 'assembled.sym').exists())
        self.assertNotIn('artifact', result)
        with self.assertRaisesRegex(W.CardError, 'already exists'):
            W.run_card(request(['x + 1', 'x * 2']), kind='steps', folder=folder,
                       by='fake:worker', applicators=fake)
        self.assertEqual(len(fake.requests), 1)


if __name__ == '__main__':
    unittest.main()
