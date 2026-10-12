"""Missing records refuse before Store/CLI writes; fake workers/providers only."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.constructor import core as C
from symblic.constructor import journal as J
from symblic.kernel import run as R
from tests.constructor.test_symblic_constructor_run import SOURCE, OPTIONS, Apps, helper, fake_runtime
from tests.constructor.test_symblic_constructor_cli import ConstructorCLI


def snapshot(folder):
    return {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in folder.rglob('*') if p.is_file() and not p.is_symlink()}


class MissingRecords(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'run'

    def run_it(self, *, mode='linear', source=SOURCE, fake=None, runtime='fake', options=None):
        apps = Apps()
        policy = {**OPTIONS, 'constructor': mode, **(options or {})}
        assessment = patch.object(C.L, 'assess_ask', wraps=C.L.assess_ask) if runtime is None else \
            patch.object(C.L, 'assess_ask', side_effect=fake or helper())
        with patch.object(C, '_runtime', return_value=fake_runtime() if runtime == 'fake' else None), \
             patch.object(C.L.subprocess, 'Popen', side_effect=AssertionError('unexpected real worker')), assessment as worker:
            run = R.Run(source, {}, apps, policy, folder=str(self.folder))
            report = run.execute()
        return report, worker.call_count, apps

    def refuse_unchanged(self, *, mode='linear', kind='uncertain'):
        before = snapshot(self.folder)
        with patch.object(C, 'Bridge', side_effect=AssertionError('Bridge reached')), \
             patch.object(R.Store, '__init__', autospec=True, wraps=R.Store.__init__) as store:
            # A real folderless Store is needed to construct the failed report.
            store.side_effect = lambda obj, folder=None: original_store(obj, folder)
            report = R.Run(SOURCE, {}, Apps(), {**OPTIONS, 'constructor': mode}, folder=str(self.folder)).execute()
        self.assertEqual(report['status'], 'failed', report)
        self.assertEqual(report['error']['kind'], kind)
        self.assertIsNone(store.call_args.args[1])
        self.assertEqual(snapshot(self.folder), before)
        return report

    def test_primary_presence_mismatches_refuse_enabled_and_off_before_store(self):
        report, _, _ = self.run_it()
        self.assertEqual(report['status'], 'done')
        for name in (J.FILE, 'constructor-config.json'):
            path = self.folder / name; original = path.read_bytes(); path.unlink()
            self.refuse_unchanged()
            self.refuse_unchanged(mode='off', kind='version')
            path.write_bytes(original)
        self.refuse_unchanged(mode='off', kind='version')

    def test_config_only_before_intent_is_conservative_recovery_not_fresh_admission(self):
        self.folder.mkdir(); (self.folder / 'constructor-config.json').write_text('{}')
        self.refuse_unchanged()

    def test_unfinished_enabled_snapshot_requires_exact_supported_integer_marker(self):
        self.folder.mkdir()
        for mode in ('linear', 'linear_diagnose'):
            for marker in (True, False, 2.0, '2', None, [2], {}, 1, 3):
                with self.subTest(mode=mode, marker=marker):
                    (self.folder / 'state.json').write_text(json.dumps({
                        'status': 'running', 'constructor_bridge': marker, 'calls': 0, 'asks': 0}))
                    self.refuse_unchanged(mode=mode)

    def test_exact_marker_retains_zero_activity_resume(self):
        self.folder.mkdir()
        (self.folder / 'state.json').write_text(json.dumps({
            'status': 'running', 'constructor_bridge': 2, 'calls': 0, 'asks': 0}))
        self.assertFalse(R.constructor_records_gate(str(self.folder), mode='linear'))
        report, worker_calls, apps = self.run_it()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(worker_calls, 1)
        self.assertEqual(apps.requests, [])

    def test_marker_validation_preserves_completed_no_activity_and_ordinary_off_history(self):
        self.folder.mkdir()
        for marker in (True, False, 2.0, '2', None, [2], {}, 1, 2, 3):
            for status, mode in (('done', 'linear'), ('done', 'linear_diagnose'), ('running', 'off')):
                with self.subTest(marker=marker, status=status, mode=mode):
                    (self.folder / 'state.json').write_text(json.dumps({
                        'status': status, 'constructor_bridge': marker, 'calls': 0, 'asks': 0}))
                    before = snapshot(self.folder)
                    self.assertFalse(R.constructor_records_gate(str(self.folder), mode=mode))
                    self.assertEqual(snapshot(self.folder), before)

    def test_both_missing_accepted_diagnostic_unavailable_charged_outcomes_refuse(self):
        for mode, rt in [('linear', 'fake'), ('linear_diagnose', 'fake'), ('linear', None)]:
            with self.subTest(mode=mode, runtime=rt):
                self.folder = self.root / ('run-' + mode + str(rt))
                report, _, _ = self.run_it(mode=mode, runtime=rt)
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(J.summary(self.folder)['attempts'], 1)
                for name in (J.FILE, 'constructor-config.json'):
                    (self.folder / name).unlink()
                self.refuse_unchanged(mode=mode)
                self.refuse_unchanged(mode='off', kind='version')
                # A newer incomplete state cannot erase the completed attempt's append-only trace.
                (self.folder / 'state.json').write_text('{"status":"running"}')
                self.refuse_unchanged(mode=mode)
                self.refuse_unchanged(mode='off', kind='version')

    def test_both_missing_stopped_and_unknown_have_conservative_interruption_guard(self):
        stopped_flag = threading.Event()
        def stopped(*_a, **kw):
            kw['lifecycle'].update(dispatched=True, reaped=True)
            stopped_flag.set()
            kw['check_stop']()
        def unknown(*_a, **kw):
            kw['lifecycle'].update(dispatched=True, reaped=True)
            raise RuntimeError('fixture')
        for label, fake in [('stopped', stopped), ('unknown', unknown)]:
            self.folder = self.root / label
            report, _, _ = self.run_it(fake=fake, options={'stop': stopped_flag} if label == 'stopped' else {})
            self.assertIn(report['status'], ('failed', 'stopped'))
            for name in (J.FILE, 'constructor-config.json'):
                (self.folder / name).unlink()
            self.refuse_unchanged()
            self.refuse_unchanged(mode='off', kind='version')

    def test_old_completed_trace_preserves_evidence_if_current_state_overwritten(self):
        report, _, _ = self.run_it()
        self.assertEqual(report['status'], 'done')
        for name in (J.FILE, 'constructor-config.json'):
            (self.folder / name).unlink()
        (self.folder / 'state.json').write_text('{"status":"running"}')
        self.refuse_unchanged()
        self.refuse_unchanged(mode='off', kind='version')

    def test_completed_noask_and_unsupported_route_zero_attempts_resume(self):
        for label, source, options in [('pure', 'let x = 7.\nshow x.', {}),
                                      ('route', SOURCE, {'route': 'search'})]:
            self.folder = self.root / label
            first, calls, _ = self.run_it(source=source, options=options)
            self.assertEqual(first['status'], 'done', first.get('error'))
            self.assertEqual(calls, 0)
            self.assertFalse((self.folder / J.FILE).exists())
            self.assertFalse((self.folder / 'constructor-config.json').exists())
            second, calls, _ = self.run_it(source=source, options=options)
            self.assertEqual(second['status'], 'done', second.get('error'))
            self.assertEqual(calls, 0)

    def test_bounded_strict_required_history_and_old_off_tolerance(self):
        self.folder.mkdir()
        malformed = [b'{"broken":', b'{"status":"done","status":"done"}', b'{"n":NaN}',
                     b'{"n":1e9999}', b'[]', b'{"x":' + b'[' * 129 + b'0' + b']' * 129 + b'}']
        for raw in malformed:
            (self.folder / 'state.json').write_bytes(raw)
            with self.subTest(raw=raw[:40]):
                self.refuse_unchanged()
                self.assertFalse(R.constructor_records_gate(str(self.folder), mode='off'))
        (self.folder / 'state.json').unlink()
        with (self.folder / 'trace.jsonl').open('wb') as f:
            f.truncate(R._CONSTRUCTOR_HISTORY_BYTES + 1)
        self.refuse_unchanged()
        (self.folder / 'trace.jsonl').unlink()
        os.mkfifo(self.folder / 'state.json')
        with self.assertRaises(S.SymblicError):
            R.constructor_records_gate(str(self.folder), mode='linear')
        (self.folder / 'state.json').unlink()
        target = self.root / 'unrelated'; target.write_text('{"status":"done"}')
        (self.folder / 'state.json').symlink_to(target)
        with self.assertRaises(S.SymblicError):
            R.constructor_records_gate(str(self.folder), mode='linear')
        self.assertEqual(target.read_text(), '{"status":"done"}')

    def test_user_text_and_record_values_are_not_constructor_evidence(self):
        self.folder.mkdir()
        ordinary = {'status': 'done', 'bindings': [{'name': 'constructor', 'value': {
            'origin': 'solver_proposal', 'constructor': {'attempt': 9}}, 'meta': {}}],
            'outputs': [{'text': 'answered_by_constructor constructor-events.jsonl'}]}
        (self.folder / 'state.json').write_text(json.dumps(ordinary))
        (self.folder / 'trace.jsonl').write_text(json.dumps({'kind': 'show', 'value': ordinary}) + '\n')
        self.assertFalse(R.constructor_records_gate(str(self.folder), mode='linear'))


original_store = R.Store.__init__


class MissingCLI(ConstructorCLI):
    # Run only these new methods, not inherited producer tests when loading this module.
    def test_cli_damaged_marker_refuses_before_metadata_or_dispatch(self):
        self.folder.mkdir()
        for marker in (True, False, 2.0, '2', None, [2], {}, 1, 3):
            with self.subTest(marker=marker):
                (self.folder / 'state.json').write_text(json.dumps({
                    'status': 'running', 'constructor_bridge': marker, 'calls': 0, 'asks': 0}))
                before = self.snapshot()
                result = self.cli(self.args('--constructor', 'linear'), no_worker=True, no_runtime=True)
                self.assertEqual(result[0], 1, result[1:3])
                self.assertEqual(json.loads(result[1])['error']['kind'], 'uncertain')
                self.assertEqual(result[3], [])
                self.assertEqual(result[4], 0)
                self.assertEqual(self.snapshot(), before)

    def test_cli_exact_command_refuses_deleted_primary_and_preserves_metadata(self):
        self.seed()
        (self.folder / J.FILE).unlink()
        before = self.snapshot()
        result = self.cli(self.args('--constructor', 'linear'), no_worker=True, no_runtime=True)
        self.assertEqual(result[0], 1, result[1:3])
        self.assertEqual(result[3], [])
        self.assertEqual(result[4], 0)
        self.assertEqual(self.snapshot(), before)

    def test_cli_both_missing_refuses_before_changed_source_metadata_write(self):
        self.seed()
        for name in (J.FILE, 'constructor-config.json'):
            (self.folder / name).unlink()
        self.source.write_text('let completely_different = 9.\nshow completely_different.')
        before = self.snapshot()
        result = self.cli(self.args('--constructor', 'linear'), no_worker=True, no_runtime=True)
        self.assertEqual(result[0], 1, result[1:3])
        self.assertEqual(result[3], [])
        self.assertEqual(result[4], 0)
        self.assertEqual(self.snapshot(), before)


def load_tests(loader, _tests, _pattern):
    suite = loader.loadTestsFromTestCase(MissingRecords)
    for name in MissingCLI.__dict__:
        if name.startswith('test_'):
            suite.addTest(MissingCLI(name))
    return suite
