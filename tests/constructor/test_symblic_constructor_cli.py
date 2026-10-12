"""The constructor flags of the command line (tools/symblic run --constructor ...): durable runs with fakes.

The tests execute the Python program embedded in tools/symblic in this process, with a fake applicator and a
fake solver worker; no real worker, solver or provider runs.
"""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from symblic.providers import applicators as A
from symblic.constructor import core as C
from symblic.constructor import journal as J
from symblic.kernel import run as SR
from tests.constructor.test_symblic_constructor_run import SOURCE, Apps, helper, fake_runtime

ROOT = Path(__file__).resolve().parents[2]


class ConstructorCLI(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name); self.source = self.base / 'input.sym'; self.source.write_text(SOURCE)
        self.folder = self.base / 'run'

    def cli(self, args, *, native=None, no_worker=False, no_runtime=False):
        path = ROOT / 'tools/symblic'
        embedded = path.read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        out, err = io.StringIO(), io.StringIO(); apps = Apps(); observed = []; original_run = SR.Run
        def run(*argv, **kwargs):
            observed.append(copy.deepcopy(argv[3] if len(argv) > 3 else kwargs.get('options')))
            return original_run(*argv, **kwargs) if native is None else native(*argv, **kwargs)
        runtime = patch.object(C, '_runtime', side_effect=AssertionError('runtime read')) if no_runtime else \
            patch.object(C, '_runtime', return_value=fake_runtime())
        fake = (lambda *_a, **_k: self.fail('worker redispatched')) if no_worker else helper()
        with patch.object(sys, 'argv', ['symblic', *args]), patch.object(sys, 'path', list(sys.path)), \
                patch.dict(os.environ, {'SYMBLIC_ROOT': str(ROOT)}), \
                patch.object(A, 'Applicators', return_value=apps), patch.object(SR, 'Run', side_effect=run), \
                runtime, patch.object(C.L, 'assess_ask', side_effect=fake) as worker, \
                redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as ended:
            exec(compile(embedded, str(path), 'exec'), {'__name__': '__main__'})
        return ended.exception.code, out.getvalue(), err.getvalue(), observed, worker.call_count, apps

    def args(self, *extra):
        return ['run', str(self.source), '--dir', str(self.folder), '--by', 'fake:a', '--agent-json', *extra]

    @staticmethod
    def captured(*_args, **_kwargs):
        class Run:
            def execute(self): return {'status': 'done', 'outputs': [], 'calls': 0}
        return Run()

    def snapshot(self):
        return {str(p.relative_to(self.folder)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.folder.rglob('*') if p.is_file() and not p.is_symlink()}

    def seed(self):
        result = self.cli(self.args('--constructor', 'linear'))
        self.assertEqual(result[0], 0, result[1:3]); self.assertEqual(result[4], 1)
        return json.loads(result[1])

    def test_default_and_explicit_off_keep_the_plain_options_without_policy_import(self):
        # Without constructor flags (or with --constructor off) the run gets exactly the options it got before the
        # constructor existed. (The original suite also compared against a frozen copy of that older command line.)
        args = ['run', str(self.source), '--agent-json', '--by', 'fake:a', '--max-calls', '7']
        with patch.object(SR, 'validate_constructor_options', side_effect=AssertionError('off policy touched')):
            default = self.cli(args, native=self.captured)
            off = self.cli([*args, '--constructor', 'off'], native=self.captured)
        self.assertEqual(default[:2], off[:2])
        self.assertEqual(default[3], off[3])
        self.assertEqual(default[3], [{'max_calls': 7, 'by': 'fake:a'}])
        self.assertEqual(default[4], 0); self.assertEqual(off[4], 0)

    def test_invalid_mode_limits_combinations_refuse_before_files_or_runner(self):
        cases = [('--constructor', 'unknown'), ('--constructor', ' linear'),
                 ('--constructor-attempts', '1'), ('--constructor', 'off', '--constructor-attempts', '1')]
        for flag, values in (('--constructor-attempts', ['0', '65', 'true', '1.0', '-1', '9' * 1000]),
                             ('--constructor-milliseconds', ['1', '320001']),
                             ('--constructor-attempt-ms', ['5001']),
                             ('--constructor-resource-limit', ['1000001'])):
            cases.extend(('--constructor', 'linear', flag, value) for value in values)
        for extra in cases:
            result = self.cli(['run', '/no/source/file', '--dir', str(self.folder), '--agent-json', *extra],
                              native=lambda *_a, **_k: self.fail('Run'))
            with self.subTest(extra=extra):
                self.assertEqual(result[0], 1); self.assertFalse(json.loads(result[1])['accepted'])
                self.assertFalse(self.folder.exists()); self.assertEqual(result[4], 0)
        result = self.cli(['run', '/no/source/file', '--constructor', 'linear', '--agent-json'])
        self.assertEqual(result[0], 1); self.assertIn('--dir', json.loads(result[1])['error']['message'])
        for command in ('check', 'preview', 'replay'):
            result = self.cli([command, '/no/path', '--constructor', 'linear', '--agent-json'])
            self.assertEqual(result[0], 1); self.assertIn('run only', json.loads(result[1])['error']['message'])

    def test_missing_capability_and_client_executable_path_refuse_early(self):
        with patch.object(SR, 'validate_constructor_options', None):
            result = self.cli(self.args('--constructor', 'linear'), native=lambda *_a, **_k: self.fail('Run'))
        self.assertEqual(result[0], 1); self.assertIn('runtime update', result[1]); self.assertFalse(self.folder.exists())
        result = self.cli(self.args('--constructor', 'linear', '--constructor-python', '/bin/false'))
        self.assertEqual(result[0], 2); self.assertIn('unrecognized arguments', result[2]); self.assertFalse(self.folder.exists())

    def test_enabled_limits_reach_native_run_and_exact_saved_configuration(self):
        # Generous time limits: a loaded machine must not turn this into a deadline refusal.
        result = self.cli(self.args('--constructor', 'linear', '--constructor-attempts', '2',
            '--constructor-milliseconds', '6000', '--constructor-attempt-ms', '3000',
            '--constructor-resource-limit', '101'))
        self.assertEqual(result[0], 0, result[1:3]); report = json.loads(result[1])
        self.assertEqual(result[4], 1); self.assertEqual(result[5].requests, []); self.assertEqual(report['calls'], 0)
        options = result[3][0]
        self.assertIs(options['determine'], False); self.assertIs(options['solve'], False)
        self.assertEqual(options['constructor_limits'], {'attempts': 2, 'milliseconds': 6000,
                                                         'attempt_ms': 3000, 'resource_limit': 101})
        self.assertEqual(json.loads((self.folder / 'meta.json').read_text())['options'], options)
        self.assertEqual(C.R.read_config(self.folder)['limits'], options['constructor_limits'])
        self.assertEqual(report['determinism_summary']['answered_by_constructor'], 1)
        self.assertIn('solver_proposal', [c['origin'] for c in report['epistemic']['claims']])

    def test_diagnostic_mode_still_calls_native_model_and_does_not_mint_solver_origin(self):
        result = self.cli(self.args('--constructor', 'linear_diagnose'))
        self.assertEqual(result[0], 0, result[1:3]); report = json.loads(result[1])
        self.assertEqual(result[4], 1); self.assertEqual(len(result[5].requests), 1)
        self.assertEqual(J.summary(str(self.folder))['dispositions'], {'diagnosed': 1})
        self.assertNotIn('solver_proposal', [c['origin'] for c in report['epistemic']['claims']])
        visible = [{k: req.get(k) for k in ('system', 'prompt', 'schema')} for req in result[5].requests]
        self.assertNotIn('native_validation', json.dumps(visible))

    def test_same_constructor_rerun_preserves_metadata_and_replays_without_worker(self):
        first = self.seed(); files = ['program.sym', 'meta.json', C.R.CONFIG_FILE, J.FILE]
        before = {n: ((self.folder / n).read_bytes(), (self.folder / n).stat().st_mtime_ns) for n in files}
        result = self.cli(self.args('--constructor', 'linear'), no_worker=True)
        self.assertEqual(result[0], 0, result[1:3]); self.assertEqual(result[4], 0)
        self.assertEqual(json.loads(result[1])['fingerprint'], first['fingerprint'])
        self.assertEqual(before, {n: ((self.folder / n).read_bytes(), (self.folder / n).stat().st_mtime_ns) for n in files})

    def test_existing_constructor_folder_off_missing_mode_and_source_input_option_drift_preserve_files(self):
        self.seed()
        for extra in ((), ('--constructor', 'off'), ('--constructor', 'linear', '--constructor-attempts', '2'),
                      ('--constructor', 'linear', '--input', 'base=12')):
            before = self.snapshot()
            result = self.cli(self.args(*extra), native=lambda *_a, **_k: self.fail('Run'))
            self.assertEqual(result[0], 1); self.assertEqual(before, self.snapshot()); self.assertEqual(result[4], 0)
        self.source.write_text(SOURCE + '\nshow 9.')
        before = self.snapshot(); result = self.cli(self.args('--constructor', 'linear'))
        self.assertEqual(result[0], 1); self.assertEqual(before, self.snapshot())

    def test_damaged_duplicate_symlink_and_kernel_metadata_refuse_without_overwrite(self):
        self.seed(); names = ('meta.json', 'program.sym', SR.KERNEL_RECORD)
        originals = {n: (self.folder / n).read_bytes() for n in names}
        for name, raw in [('meta.json', b'{'), ('meta.json', b'{"inputs":{},"inputs":{},"options":{}}'),
                          ('meta.json', b'[' * 2000 + b']' * 2000), ('program.sym', b'changed'),
                          (SR.KERNEL_RECORD, b'{"version":1,"id":"changed","lang":"2.5"}')]:
            (self.folder / name).write_bytes(raw); before = self.snapshot()
            result = self.cli(self.args('--constructor', 'linear'), native=lambda *_a, **_k: self.fail('Run'))
            self.assertEqual(result[0], 1); self.assertEqual(before, self.snapshot())
            (self.folder / name).write_bytes(originals[name])
        metadata = self.folder / 'meta.json'; metadata.unlink(); metadata.symlink_to(self.source)
        before = self.snapshot(); source_before = self.source.read_bytes()
        result = self.cli(self.args('--constructor', 'linear'), native=lambda *_a, **_k: self.fail('Run'))
        self.assertEqual(result[0], 1); self.assertEqual(before, self.snapshot()); self.assertTrue(metadata.is_symlink())
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_config_without_journal_and_oversized_metadata_still_refuse_without_write(self):
        self.seed(); journal = self.folder / J.FILE; journal.unlink()
        for extra in ((), ('--constructor', 'off')):
            before = self.snapshot(); result = self.cli(self.args(*extra), native=lambda *_a, **_k: self.fail('Run'))
            self.assertEqual(result[0], 1); self.assertEqual(before, self.snapshot())
        metadata = self.folder / 'meta.json'
        with metadata.open('wb') as stream: stream.truncate(16 * 1024 * 1024 + 1)
        original = metadata.stat()
        result = self.cli(self.args('--constructor', 'linear'), native=lambda *_a, **_k: self.fail('Run'))
        self.assertEqual(result[0], 1); self.assertIn('presence differs', result[1])
        self.assertEqual((metadata.stat().st_size, metadata.stat().st_mtime_ns), (original.st_size, original.st_mtime_ns))

    def test_replay_retains_policy_and_never_reads_runtime_or_dispatches_worker(self):
        first = self.seed()
        result = self.cli(['replay', str(self.folder), '--agent-json'], no_worker=True, no_runtime=True)
        self.assertEqual(result[0], 0, result[1:3]); self.assertEqual(result[4], 0)
        self.assertEqual(json.loads(result[1])['fingerprint'], first['fingerprint'])

    def test_help_exposes_modes_units_and_determination_constraint(self):
        result = self.cli(['run', '--help'])   # `tools/symblic --help` alone prints the command overview
        self.assertEqual(result[0], 0); self.assertIn('linear_diagnose', result[1])
        self.assertIn('determine=false', result[1]); self.assertIn('solve=off', result[1])
        self.assertIn('--constructor-attempt-ms', result[1]); self.assertEqual(result[4], 0)


if __name__ == '__main__': unittest.main()
