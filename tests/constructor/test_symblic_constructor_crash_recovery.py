"""Crash/recovery counterexamples use fake workers and disposable run folders only."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.constructor import core as C
from symblic.constructor import journal as J
from symblic.kernel import run as R
from tests.constructor.test_symblic_constructor_run import SOURCE, OPTIONS, Apps, fake_runtime, helper
from tests.constructor.test_symblic_constructor_missing_records import snapshot

TREE = Path(__file__).resolve().parents[2]   # the repository root
CHILD = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
import tests
from unittest.mock import patch
from symblic.constructor import core as C
from symblic.kernel import run as R
from tests.constructor.test_symblic_constructor_run import SOURCE, OPTIONS, Apps, fake_runtime, helper
def crash(*args, **kwargs):
    kwargs.get('lifecycle', {}).update(dispatched=True)
    os._exit(137)
with patch.object(C, '_runtime', return_value=fake_runtime()):
    if sys.argv[3] == 'resume':
        with patch.object(C.Bridge, 'attempt', side_effect=crash):
            R.Run(SOURCE, {}, Apps(), dict(OPTIONS), folder=sys.argv[2]).execute()
    else:
        with patch.object(C.L, 'assess_ask', side_effect=crash):
            R.Run(SOURCE, {}, Apps(), dict(OPTIONS), folder=sys.argv[2]).execute()
raise AssertionError('crash point not reached')
'''


class CrashRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'run'

    def killed_child(self, phase='dispatch'):
        child = subprocess.run([sys.executable, '-B', '-c', CHILD, str(TREE), str(self.folder), phase],
                               cwd=TREE, capture_output=True, text=True, timeout=25)
        self.assertEqual(child.returncode, 137, child.stderr)

    def erase_primary(self, *, lock=True, trace=True):
        names = [J.FILE, 'constructor-config.json']
        if lock:
            names.append('.constructor-events.lock')
        if trace:
            names.append('trace.jsonl')
        for name in names:
            (self.folder / name).unlink(missing_ok=True)

    def refuse_unchanged(self):
        before = snapshot(self.folder)
        for mode, kind in [('linear', 'uncertain'), ('off', 'version')]:
            with self.subTest(mode=mode), \
                    patch.object(C, 'Bridge', side_effect=AssertionError('constructor reached')), \
                    patch.object(C.L, 'assess_ask', side_effect=AssertionError('worker reached')):
                with self.assertRaises(S.SymblicError) as caught:
                    R.constructor_records_gate(str(self.folder), mode=mode)
                self.assertEqual(caught.exception.kind, kind)
                run = R.Run(SOURCE, {}, Apps(), {**OPTIONS, 'constructor': mode}, folder=str(self.folder))
                report = run.execute()
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['error']['kind'], kind)
                self.assertIsNone(run.store.dir)
            self.assertEqual(snapshot(self.folder), before)

    def test_hard_crash_and_deleted_primary_lock_trace_still_refuses(self):
        self.killed_child()
        self.assertEqual(J.summary(self.folder)['attempts'], 1)
        state = json.loads((self.folder / 'state.json').read_text())
        self.assertEqual(state['status'], 'running')
        self.assertEqual(state['constructor_activity'], {'version': 1, 'attempt_possible': True})
        self.erase_primary()
        self.refuse_unchanged()

    def test_surviving_legacy_lock_and_each_quarantine_slot_refuse_without_reading(self):
        self.folder.mkdir()
        for name in ['.constructor-events.lock'] + [f'constructor-events.torn-{i}.bin' for i in range(8)]:
            with self.subTest(name=name):
                # A dangling link establishes a leftover without following its target.
                (self.folder / name).symlink_to(self.root / 'absent')
                self.refuse_unchanged()
                (self.folder / name).unlink()

    def test_existing_activity_is_retained_before_resumed_ask(self):
        with patch.object(C, '_runtime', return_value=fake_runtime()), \
                patch.object(C.L, 'assess_ask', side_effect=helper()):
            run = R.Run(SOURCE, {}, Apps(), dict(OPTIONS), folder=str(self.folder))
            self.assertEqual(run.execute()['status'], 'done')
        # A resumed invocation writes a running snapshot before visiting the ask.
        self.killed_child('resume')
        self.erase_primary()
        self.refuse_unchanged()

    def test_activity_file_and_directory_are_synced_before_intent(self):
        synced = []
        real_sync, real_begin = os.fsync, J.Journal.begin
        def sync(fd):
            info = os.fstat(fd)
            synced.append(('directory' if stat.S_ISDIR(info.st_mode) else 'file',
                           os.readlink(f'/proc/self/fd/{fd}')))
            return real_sync(fd)
        def begin(journal, *args, **kwargs):
            state = json.loads((self.folder / 'state.json').read_text())
            self.assertTrue(state['constructor_activity']['attempt_possible'])
            self.assertTrue(any(kind == 'file' and '/.state.json.' in path for kind, path in synced))
            self.assertTrue(any(kind == 'directory' and path == str(self.folder) for kind, path in synced))
            return real_begin(journal, *args, **kwargs)
        with patch.object(C, '_runtime', return_value=fake_runtime()), \
                patch.object(C.L, 'assess_ask', side_effect=helper()), \
                patch.object(os, 'fsync', side_effect=sync), patch.object(J.Journal, 'begin', begin):
            run = R.Run(SOURCE, {}, Apps(), dict(OPTIONS), folder=str(self.folder))
            report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertTrue(report['constructor_activity']['attempt_possible'])
        self.assertTrue(json.loads((self.folder / 'state.json').read_text())['constructor_activity']['attempt_possible'])

    def test_checkpoint_failure_prevents_intent_and_worker(self):
        real_save = R.Store.save
        failure = R.Stopped('state directory sync stopped')
        def save(store, name, data, **kwargs):
            if kwargs.get('durable'):
                with patch.object(J, '_sync_folder', side_effect=failure):
                    return real_save(store, name, data, **kwargs)
            return real_save(store, name, data, **kwargs)
        with patch.object(C, '_runtime', return_value=fake_runtime()), \
                patch.object(C.L, 'assess_ask', side_effect=AssertionError('worker reached')) as worker, \
                patch.object(J.Journal, 'begin', side_effect=AssertionError('intent reached')) as begin, \
                patch.object(R.Store, 'save', save):
            with self.assertRaises(R.Stopped) as caught:
                R.Run(SOURCE, {}, Apps(), dict(OPTIONS), folder=str(self.folder)).execute()
        self.assertIs(caught.exception, failure)
        worker.assert_not_called(); begin.assert_not_called()

    def test_durable_state_cleanup_preserves_original_exception(self):
        store = R.Store(str(self.folder)); original = R.Stopped('first failure')
        with patch.object(J, '_write_all', side_effect=original), \
                patch.object(os, 'unlink', side_effect=KeyboardInterrupt('cleanup')):
            with self.assertRaises(R.Stopped) as caught:
                store.save('state.json', {'constructor_activity': {}}, durable=True)
        self.assertIs(caught.exception, original)
        self.assertTrue(any('KeyboardInterrupt' in note for note in getattr(original, '__notes__', [])))

    def test_legacy_running_snapshot_without_constructor_records_refuses_enabled_resume(self):
        self.folder.mkdir()
        for status in ('running', 'stopping'):
            with self.subTest(status=status):
                # The pre-bridge-2 host snapshot carries no semantic identity or
                # constructor marker; the absent records cannot establish no work.
                (self.folder / 'state.json').write_text(json.dumps({
                    'program': 'ConstructorRun', 'status': status, 'asks': 1,
                    'calls': 0, 'progress': [2, 4], 'seconds': 0.01, 'updated': 1}))
                before = snapshot(self.folder)
                with self.assertRaises(S.SymblicError) as caught:
                    R.constructor_records_gate(str(self.folder), mode='linear')
                self.assertEqual(caught.exception.kind, 'uncertain')
                # Ordinary off-mode runs retain their former missing-history policy.
                self.assertFalse(R.constructor_records_gate(str(self.folder), mode='off'))
                self.assertEqual(snapshot(self.folder), before)

    def test_current_bridge_no_attempt_snapshot_keeps_enabled_resume_available(self):
        self.folder.mkdir()
        (self.folder / 'state.json').write_text(json.dumps({
            'status': 'running', 'constructor_bridge': 2, 'asks': 0, 'calls': 0}))
        self.assertFalse(R.constructor_records_gate(str(self.folder), mode='linear'))

    def test_run_folder_refuses_before_start_fresh_can_drop_trace(self):
        self.folder.mkdir()
        (self.folder / 'program.sym').write_text(SOURCE)
        (self.folder / 'meta.json').write_text(json.dumps({'options': OPTIONS, 'inputs': {}}))
        (self.folder / 'trace.jsonl').write_text(json.dumps({'kind': 'ask', 'ask': {
            'constructor': {'attempt': 2}}}) + '\n')
        before = snapshot(self.folder)
        with patch.object(R, 'start_fresh', side_effect=AssertionError('trace reset reached')):
            report = R.run_folder(str(self.folder), applicators=Apps())
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'uncertain')
        self.assertEqual(snapshot(self.folder), before)

    def test_pure_and_ordinary_runs_do_not_gain_activity(self):
        for mode in ['off', 'linear']:
            folder = self.root / mode
            with patch.object(C, '_runtime', return_value=None):
                report = R.Run('show 3.', options={**OPTIONS, 'constructor': mode}, folder=str(folder)).execute()
            self.assertEqual(report['status'], 'done')
            self.assertNotIn('constructor_activity', report)
            self.assertNotIn('constructor_activity', json.loads((folder / 'state.json').read_text()))
            self.assertFalse(R.constructor_records_gate(str(folder), mode=mode))


if __name__ == '__main__':
    unittest.main()
