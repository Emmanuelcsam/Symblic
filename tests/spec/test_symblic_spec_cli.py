"""Agent-friendly spec run preserves compiler policy; fake models, local JS sandbox."""
import contextlib
import io
import json
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.js import check as JS
from symblic.spec import build as B

ROOT = Path(__file__).resolve().parents[2]          # the repository root
SHEET = (ROOT / 'examples/agent-handoff.sheet.md').read_text()
CODE = {'double': 'function double(x) { return x * 2; }',
        'ready': 'function ready() { return "ready"; }',
        'next': 'function next(x) { return double(x) + 1; }'}


class Fake:
    def __init__(self, fail=False, stop=False):
        self.requests, self.cancelled, self.fail, self.stop = [], 0, fail, stop

    def call(self, request):
        self.requests.append(request)
        if self.stop:
            os.kill(os.getpid(), signal.SIGTERM)
            # Provider work can run on a search thread; Python delivers the
            # signal handler on the main thread at its next interpreter turn.
            self.assert_stopped = request['stop'].wait(2)
            return {'ok': False, 'fatal': True, 'error': 'stopped'}
        for name, code in CODE.items():
            if 'ask unit_' + name + ' ' in request['prompt']:
                answer = 'function ' + name + '() { return 0; }' if self.fail else code
                return {'ok': True, 'text': '```js\n' + answer + '\n```'}
        raise AssertionError('Unexpected request')

    def cancel_all(self):
        self.cancelled += 1


class CommandFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sheet = self.root / 'handoff.sheet.md'
        self.sheet.write_text(SHEET)

    def command(self, *args, apps=None):
        output, progress = io.StringIO(), io.StringIO()
        apps = apps or Fake()
        with patch('symblic.providers.applicators.Applicators', return_value=apps) as factory, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
            code = B.main(list(args))
        return code, json.loads(output.getvalue()), progress.getvalue(), factory


class Commands(CommandFixture, unittest.TestCase):
    def test_check_and_compile_remain_source_only(self):
        code, checked, _, factory = self.command('check', str(self.sheet), '--agent-json')
        self.assertEqual(code, 0)
        self.assertTrue(checked['ok'])
        factory.assert_not_called()
        code, compiled, _, factory = self.command('compile', str(self.sheet), '--by', 'fake:child', '--agent-json')
        self.assertEqual(code, 0)
        self.assertIn('source', compiled)
        factory.assert_not_called()

    def test_missing_applicator_or_nonempty_record_refuses_before_provider(self):
        code, error, _, factory = self.command('run', str(self.sheet), '--agent-json')
        self.assertEqual(code, 1)
        self.assertFalse(error['ok'])
        factory.assert_not_called()
        occupied = self.root / 'occupied'; occupied.mkdir(); (occupied / 'keep').write_text('original')
        code, error, _, factory = self.command('run', str(self.sheet), '--by', 'fake:child',
                                                '--dir', str(occupied), '--agent-json')
        self.assertEqual(code, 1)
        factory.assert_not_called()
        self.assertEqual((occupied / 'keep').read_text(), 'original')

    def test_invalid_expected_hash_refuses_before_provider(self):
        code, error, _, factory = self.command('run', str(self.sheet), '--by', 'fake:child',
                                                '--output-sha256', 'not-a-hash', '--agent-json')
        self.assertEqual(code, 1)
        self.assertFalse(error['ok'])
        factory.assert_not_called()

    def test_cli_dispatches_source_only_spec_check(self):
        # tools/symblic is the repository's command-line entry point; `spec` dispatches to symblic.spec.build
        process = subprocess.run([str(ROOT / 'tools/symblic'), 'spec', 'check', str(self.sheet), '--agent-json'],
                                 capture_output=True, text=True, timeout=30, check=False, env=dict(os.environ))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(json.loads(process.stdout)['ok'])

    def test_native_summary_is_passed_through_only_when_present(self):
        compiled = B.compile_cards(SHEET, ['fake:child'])
        summary = {'execution': 'test-summary', 'truncated': False}
        with patch('symblic.kernel.run.Run') as runner, patch('symblic.providers.applicators.Applicators'):
            runner.return_value.execute.return_value = {'status': 'failed', 'calls': 0, 'error': None,
                                                        'determinism_summary': summary}
            self.assertEqual(B._run_cards(compiled)['determinism_summary'], summary)
            del runner.return_value.execute.return_value['determinism_summary']
            self.assertNotIn('determinism_summary', B._run_cards(compiled))


@unittest.skipUnless(JS.available(), 'local required JavaScript sandbox unavailable')
class NativeJourney(CommandFixture, unittest.TestCase):
    def test_complete_envelope_exact_output_manifest_and_fresh_dependencies(self):
        folder = self.root / 'record'; apps = Fake()
        plan = B.C.plan(B.SP.parse(SHEET))
        policies = {unit['id']: {'version': 1, 'exports': {name: 'function' for name in unit['exports']}}
                    for unit in plan['units']}
        policy_path = self.root / 'declarations.json'; policy_path.write_text(json.dumps(policies))
        code, result, progress, _ = self.command('run', str(self.sheet), '--by', 'fake:child', '--dir', str(folder),
                                                '--samples', '1', '--retries', '1', '--rounds', '1',
                                                '--declaration-contracts', str(policy_path),
                                                '--presentation', 'full', '--agent-json', apps=apps)
        self.assertEqual(code, 0, result.get('error'))
        self.assertTrue(result['accepted'])
        self.assertEqual(len(apps.requests), 3)
        self.assertEqual(apps.cancelled, 1)
        self.assertTrue(progress)
        compiled = json.loads((folder / 'compiler.json').read_text())
        meta = json.loads((folder / 'meta.json').read_text())
        for key, value in compiled['options'].items():
            self.assertEqual(meta['options'][key], value)
            self.assertEqual(result['options'][key], value)
        self.assertEqual(result['options']['max_calls'], 6)
        self.assertIn('execution_pins', meta['options'])
        self.assertEqual(result['settings']['presentation'], 'full')
        self.assertEqual(result['settings']['declaration_contracts'], policies)
        self.assertEqual((folder / 'program.sym').read_text(), compiled['source'])
        self.assertEqual(json.loads((folder / 'spec-result.json').read_text()), result)
        last = next(req for req in apps.requests if 'ask unit_next ' in req['prompt'])
        self.assertIn(CODE['double'], last['prompt'])
        self.assertNotIn(CODE['ready'], last['prompt'])
        code, manifest, _, factory = self.command('manifest', str(folder), '--agent-json')
        self.assertEqual(code, 0, manifest)
        factory.assert_not_called()
        self.assertEqual(manifest['output']['text'], result['output']['text'])
        self.assertEqual(manifest['output']['sha256'], result['output']['sha256'])
        path = self.root / 'manifest.json'; path.write_text(json.dumps(manifest))
        code, checked, _, factory = self.command('verify', str(path), '--output-sha256', result['output']['sha256'], '--agent-json')
        self.assertEqual(code, 0, checked)
        factory.assert_not_called()
        code, reused, _, _ = self.command('run', str(self.sheet), '--by', 'fake:child',
                                         '--manifest', str(path), '--presentation', 'full',
                                         '--declaration-contracts', str(policy_path),
                                         '--agent-json', apps=Fake(fail=True))
        self.assertEqual(code, 0, reused.get('error'))
        self.assertEqual(reused['kept'], 3)
        self.assertEqual(reused['calls'], 0)
        self.assertEqual(reused['output'], result['output'])

    def test_rejected_construction_returns_no_output_and_respects_compiled_budget(self):
        apps = Fake(fail=True)
        code, result, _, _ = self.command('run', str(self.sheet), '--by', 'fake:child',
                                          '--samples', '1', '--retries', '1', '--rounds', '1', '--agent-json', apps=apps)
        self.assertEqual(code, 1)
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['output'])
        self.assertEqual(result['calls'], 2)
        self.assertLessEqual(result['calls'], result['options']['max_calls'])
        self.assertEqual(apps.cancelled, 1)

    def test_stop_is_cooperative_and_restores_handlers(self):
        prior = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        apps = Fake(stop=True)
        code, result, _, _ = self.command('run', str(self.sheet), '--by', 'fake:child', '--agent-json', apps=apps)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'stopped')
        self.assertIsNone(result['output'])
        self.assertTrue(apps.assert_stopped)
        self.assertEqual(apps.cancelled, 1)
        self.assertEqual({sig: signal.getsignal(sig) for sig in prior}, prior)

    def test_output_hash_requirement_is_separate_from_exposed_checks(self):
        code, result, _, _ = self.command('run', str(self.sheet), '--by', 'fake:child', '--samples', '1',
                                          '--retries', '1', '--rounds', '1', '--output-sha256', '0' * 64, '--agent-json')
        self.assertEqual(code, 1)
        self.assertEqual(result['native_status'], 'done')
        self.assertFalse(result['accepted'])
        self.assertEqual(result['error']['kind'], 'output_hash')
        self.assertIsNone(result['output'])


if __name__ == '__main__':
    unittest.main()
