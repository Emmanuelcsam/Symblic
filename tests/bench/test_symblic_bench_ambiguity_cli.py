"""Ambiguity CLI journeys with synthetic dev cases, private temp stores and no providers.

These tests exercise the early CLI branch and its persisted assignment. They do
not read the published held-out dataset or launch models, tools or remote work.
"""

import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from symblic.providers import applicators as Apply
from symblic.bench import bench as B
from symblic.bench import ambiguity as A


def fixture_data():
    fields = [{'name': 'color', 'description': 'The fixture label to use.',
               'type': 'text', 'choices': ['red', 'blue', 'green']}]

    def case(name, family, value, ambiguous):
        return {'id': name, 'family': family, 'domain': 'fixture', 'split': 'dev',
                'public_group': family,
                'request': 'Choose my preferred label.' if ambiguous else 'Use the green label.',
                'context': 'This is a synthetic offline fixture.', 'fields': fields,
                'gold': {'values': {'color': value},
                         'clarify_fields': ['color'] if ambiguous else [],
                         'owner_answers': {'color': value} if ambiguous else {}}}

    return {'version': 1, 'cases': [case('alpha-red', 'alpha', 'red', True),
                                    case('alpha-blue', 'alpha', 'blue', True),
                                    case('beta-green', 'beta', 'green', False)]}


class AmbiguityCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='symblic-ambiguity-cli-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'results'
        self.data = self.root / 'synthetic-dev.json'
        self.data.write_text(json.dumps(fixture_data()), encoding='utf-8')
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        self.legacy = self.guards.enter_context(
            patch.object(B, 'Bench', side_effect=AssertionError('Legacy Bench is forbidden')))
        self.factory = self.guards.enter_context(
            patch.object(Apply, 'Applicators', side_effect=AssertionError('Provider factory is forbidden')))
        self.signal = self.guards.enter_context(
            patch.object(Apply, 'install_sigterm', side_effect=AssertionError('Live signal hooks are forbidden')))
        self.guards.enter_context(
            patch('socket.create_connection', side_effect=AssertionError('Network is forbidden')))

    def args(self, *extra):
        return ['--suite', 'ambiguity', '--out', str(self.out),
                '--ambiguity-data', str(self.data),
                '--ambiguity-apps', 'ollama:fixture-a,ollama:fixture-b', *extra]

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = B.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def rejected(self, args, message):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            B.main(args)
        self.assertEqual(caught.exception.code, 2)
        self.assertIn(message, stderr.getvalue())
        self.factory.assert_not_called()
        self.legacy.assert_not_called()

    def read(self, name):
        return json.loads((self.out / name).read_text(encoding='utf-8'))

    def test_dry_run_freezes_every_assignment_without_constructing_a_provider(self):
        result, output, _ = self.invoke(self.args('--dry-run'))
        self.assertEqual(result, 0)
        self.assertIn('no dispatch', output)
        plan = self.read('ambiguity-manifest.json')
        summary = self.read('ambiguity-summary.json')
        self.assertEqual(len(plan['cells']), 24)
        self.assertEqual(plan['maximum_calls'], 30)
        self.assertEqual(summary['planned_cells'], 24)
        self.assertEqual(sum(g['pending'] for g in summary['groups']), 24)
        self.assertEqual(sum(g['call_attempts'] for g in summary['groups']), 0)
        self.assertEqual({g['assigned'] for g in summary['groups']}, {3})
        self.assertEqual(plan['config']['tools'], 'none')
        self.assertFalse((self.out / 'ambiguity-cells').exists())
        self.factory.assert_not_called()
        self.signal.assert_not_called()
        self.legacy.assert_not_called()

    def test_quick_keeps_a_whole_family_and_all_requested_conditions_and_apps(self):
        self.invoke(self.args('--dry-run', '--quick'))
        plan = self.read('ambiguity-manifest.json')
        self.assertEqual(plan['config']['case_ids'], ['alpha-red', 'alpha-blue'])
        self.assertEqual(len(plan['cells']), 16)
        self.assertEqual(plan['maximum_calls'], 20)
        self.assertEqual({c['family'] for c in plan['cells']}, {'alpha'})
        for case in plan['config']['case_ids']:
            actual = {(c['by'], c['condition']) for c in plan['cells'] if c['case'] == case}
            expected = {(by, condition) for by in plan['config']['apps'] for condition in A.CONDITIONS}
            self.assertEqual(actual, expected)

    def test_repeated_dry_run_preserves_the_exact_manifest(self):
        self.invoke(self.args('--dry-run'))
        path = self.out / 'ambiguity-manifest.json'
        before = path.read_bytes(), path.stat().st_mtime_ns
        self.invoke(self.args('--dry-run'))
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_report_only_is_cold_and_needs_neither_dataset_nor_applicators(self):
        self.invoke(self.args('--dry-run'))
        self.data.unlink()
        with patch.object(A, 'load_dataset', side_effect=AssertionError('Report must use its manifest')), \
                patch.object(A, 'make_plan', side_effect=AssertionError('Report must not rebuild its plan')):
            result, output, _ = self.invoke(['--suite', 'ambiguity', '--out', str(self.out), '--report-only'])
        self.assertEqual(result, 0)
        self.assertIn('Assigned cells: 24', output)
        self.assertEqual(self.read('ambiguity-summary.json')['planned_cells'], 24)
        self.factory.assert_not_called()
        self.signal.assert_not_called()

    def test_resume_rejects_changed_models_or_conditions_before_provider_creation(self):
        self.invoke(self.args('--dry-run'))
        for changed in (('--ambiguity-apps', 'ollama:fixture-other'),
                        ('--ambiguity-conditions', 'typed')):
            with self.subTest(changed=changed):
                self.rejected(self.args('--resume', *changed), 'different data, code, models or conditions')

    def test_resume_rejects_changed_dataset_bytes_before_provider_creation(self):
        self.invoke(self.args('--dry-run'))
        self.data.write_text(json.dumps(fixture_data(), indent=2), encoding='utf-8')
        self.rejected(self.args('--resume'), 'different data, code, models or conditions')

    def test_an_existing_assignment_requires_explicit_resume_before_provider_creation(self):
        self.invoke(self.args('--dry-run'))
        self.rejected(self.args(), 'use --resume')

    def test_mixed_suites_retries_and_unrelated_dry_runs_are_refused_offline(self):
        cases = [(self.args('--suite', 'ambiguity,identity', '--dry-run'), 'only suite'),
                 (self.args('--suite', 'identity', '--dry-run'), 'only for --suite ambiguity'),
                 (self.args('--dry-run', '--retry', 'offline'), 'keeps first attempts')]
        for args, message in cases:
            with self.subTest(args=args):
                self.rejected(args, message)
        self.assertFalse(self.out.exists())

    def test_explicit_apps_and_avoided_node_are_validated_before_any_factory(self):
        cases = [(self.args('--dry-run', '--ambiguity-apps', ''), 'distinct explicit applicators'),
                 (self.args('--dry-run', '--avoid', 'node-x', '--ambiguity-apps', 'ollama:fixture@node-x'),
                  'avoided node')]
        for args, message in cases:
            with self.subTest(args=args):
                self.rejected(args, message)
        self.assertFalse(self.out.exists())

    def test_failed_and_interrupted_cells_keep_the_denominator_and_are_never_redispatched(self):
        base = self.args('--ambiguity-apps', 'ollama:fixture-a', '--ambiguity-conditions', 'direct')
        self.invoke([*base, '--dry-run'])
        plan = self.read('ambiguity-manifest.json')
        for cell, status in zip(plan['cells'], ('failed', 'started', 'failed')):
            row = {'cell': cell['id'], 'case': cell['case'], 'condition': cell['condition'],
                   'by': cell['by'], 'status': status, 'correct': False,
                   'calls': [{'status': 'intent' if status == 'started' else 'error'}],
                   'error': 'synthetic node offline'}
            A._save(self.out / 'ambiguity-cells' / (cell['id'] + '.json'), row)

        class NoDispatch:
            def call(self, request):
                raise AssertionError('An existing failure/intent must never be redispatched')

        with patch.object(Apply, 'Applicators', return_value=NoDispatch()), \
                patch.object(Apply, 'install_sigterm'):
            self.assertEqual(self.invoke([*base, '--resume'])[0], 0)
        self.assertEqual(self.invoke(['--suite', 'ambiguity', '--out', str(self.out), '--report-only'])[0], 0)
        group, = self.read('ambiguity-summary.json')['groups']
        self.assertEqual({k: group[k] for k in ('assigned', 'failed', 'uncertain', 'pending', 'call_attempts')},
                         {'assigned': 3, 'failed': 2, 'uncertain': 1, 'pending': 0, 'call_attempts': 3})
        self.assertEqual(group['success'], 0)


if __name__ == '__main__':
    unittest.main()
