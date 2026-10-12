"""Model-first construction: no speculative contract evaluation; checked answers still required.

All providers are fakes and all durable state is temporary.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from symblic.kernel import run as R  # noqa: E402


class Models:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': next(self.answers)}, 'ms': 1}


SOURCE = ('ask n: Int in 1..3 "Select the valid value." with effort=low, retries=1{options}\n'
          'ensure n = 2 else retry.\nshow n.\n')


def execute(source, answers=(2,), folder=None, **options):
    models = Models(answers)
    run = R.Run(source, None, models, {'by': 'fake:a', **options}, folder=folder)
    return run, run.execute(), models


class DeterminationControl(unittest.TestCase):
    def disabled(self, report):
        self.assertTrue(report['determinacy']['asks'])
        for row in report['determinacy']['asks']:
            self.assertEqual((row['status'], row['reason']), ('unassessed', 'author_disabled'))
            self.assertFalse(set(row) & {'domain', 'passing', 'passing_count', 'method', 'exhaustive'})

    def test_disabled_skips_both_runtime_probes_and_still_calls_model(self):
        source = SOURCE.format(options=', determine=false, solve=false')
        with (mock.patch.object(R.Run, 'determine', side_effect=AssertionError('enumeration')),
              mock.patch.object(R.Run, 'vacuity', side_effect=AssertionError('empty probe'))):
            run, report, models = execute(source)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 1)
        self.disabled(report)
        self.assertEqual(report['determinacy']['asks'][0]['answered_by'], 'model')
        self.assertFalse(any(row['kind'] in ('determination', 'vacuity') for row in run.trace))

    def test_text_empty_probe_is_also_skipped(self):
        source = ('ask t: Text "A short name." with effort=low, determine=false\n'
                  'ensure len(t) < 50 else retry.\n')
        with mock.patch.object(R.Run, '_candidate', side_effect=AssertionError('speculation')):
            _run, report, models = execute(source, ('Nile',))
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 1)
        self.assertFalse(any(row.get('code') == 'SYM_VACUOUS' for row in report['warnings']))
        self.disabled(report)

    def test_default_and_explicit_true_preserve_enumeration_and_kernel_solving(self):
        for setting in ('', ', determine=true'):
            for solve, calls in (('', 1), (', solve=true', 0), (', solve=auto', 0)):
                with self.subTest(setting=setting, solve=solve):
                    _run, report, models = execute(SOURCE.format(options=setting + solve))
                    self.assertEqual(report['status'], 'done', report.get('error'))
                    self.assertEqual(len(models.requests), calls)
                    self.assertEqual(report['determinacy']['asks'][0]['status'], 'determined')

    def test_disabled_does_not_accept_a_bad_candidate(self):
        for route in ('vote', 'escalate', 'search'):
            with self.subTest(route=route):
                source = SOURCE.format(options=', determine=false, route=' + route)
                _run, report, models = execute(source, (1, 2), max_calls=2)
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(len(models.requests), 2)
                self.disabled(report)
                self.assertTrue(any(row['name'] == 'n' and row['value'] == 2 for row in report['bindings']))

    def test_candidate_checks_start_only_after_a_real_reply_and_check_selected_values(self):
        for route in ('escalate', 'search'):
            with self.subTest(route=route):
                source = SOURCE.format(options=', determine=false, route=' + route)
                models = Models((2,))
                run = R.Run(source, None, models, {'by': 'fake:a', 'max_calls': 1})
                original = run._candidate
                checked = []

                def candidate(statement, env, value, *args, models=models, checked=checked,
                              original=original, **kwargs):
                    self.assertEqual(len(models.requests), 1)
                    checked.append(value)
                    return original(statement, env, value, *args, **kwargs)

                with mock.patch.object(run, '_candidate', side_effect=candidate):
                    report = run.execute()
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertTrue(checked)
                self.assertEqual(set(checked), {2})

    def test_contradiction_is_not_invented_when_analysis_disabled(self):
        source = SOURCE.format(options=', determine=false').replace('n = 2', 'n = 4')
        _run, report, models = execute(source, (1, 2), max_calls=2)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(models.requests), 2)
        self.assertNotEqual(report['error']['kind'], 'contradictory')
        self.disabled(report)

    def test_invalid_option_refuses_without_a_call(self):
        for value in ('"false"', '0', '1', 'none', '[]', '{:}'):
            with self.subTest(value=value):
                _run, report, models = execute(SOURCE.format(options=', determine=' + value))
                self.assertEqual(report['status'], 'failed')
                self.assertIn('determine must be true or false', report['error']['message'])
                self.assertEqual(models.requests, [])
        for value in (None, 0, 1, 'false', [], {}):
            with self.subTest(host=value):
                _run, report, models = execute(SOURCE.format(options=''), determine=value)
                self.assertEqual(report['status'], 'failed')
                self.assertIn('determine must be true or false', report['error']['message'])
                self.assertEqual(models.requests, [])

    def test_conflicting_kernel_solve_refuses_without_checks_or_calls(self):
        for suffix in (', solve=true', ', solve=auto', ', by=kernel'):
            with self.subTest(suffix=suffix), mock.patch.object(
                    R.Run, 'determine', side_effect=AssertionError('enumeration')):
                _run, report, models = execute(SOURCE.format(options=', determine=false' + suffix))
                self.assertEqual(report['status'], 'failed')
                self.assertIn('determine=false', report['error']['message'])
                self.assertEqual(models.requests, [])
                self.disabled(report)

    def test_use_host_and_statement_precedence(self):
        for source, host, status in (
            (SOURCE.format(options=''), False, 'unassessed'),
            ('use determine=false.\n' + SOURCE.format(options=''), True, 'unassessed'),
            ('use determine=true.\n' + SOURCE.format(options=''), False, 'determined'),
            ('use determine=false.\n' + SOURCE.format(options=', determine=true'), False, 'determined'),
            ('let enabled = false.\n' + SOURCE.format(options=', determine=enabled'), True, 'unassessed'),
        ):
            with self.subTest(source=source, host=host):
                _run, report, _models = execute(source, determine=host)
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(report['determinacy']['asks'][0]['status'], status)

    def test_for_each_resolves_option_per_item(self):
        source = ('ask n: Int "Give a number." for each enabled in [false, true] '
                  'with effort=low, determine=enabled\n')
        _run, report, models = execute(source, (2, 2), parallel=1)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 2)
        self.assertEqual([(row['index'], row['reason']) for row in report['determinacy']['asks']],
                         [(1, 'author_disabled'), (2, 'no_finite_domain')])

    def test_fresh_resume_keeps_answer_cache_and_disabled_receipt(self):
        source = SOURCE.format(options=', determine=false')
        with tempfile.TemporaryDirectory() as folder:
            _run, report, models = execute(source, folder=folder)
            self.assertEqual(report['status'], 'done', report.get('error'))
            self.assertEqual(len(models.requests), 1)
            _run, second, models = execute(source, (), folder=folder)
            self.assertEqual(second['status'], 'done', second.get('error'))
            self.assertEqual(models.requests, [])
            self.disabled(second)


if __name__ == '__main__':
    unittest.main()
