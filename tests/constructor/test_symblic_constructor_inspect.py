"""Read-only constructor inspection: fake worker/model/runtime and temporary folders only."""
from contextlib import redirect_stdout
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from symblic.constructor import inspect as I
from symblic.constructor import journal as J
from symblic.constructor import records as R
from tests.constructor.test_symblic_constructor_cli import ConstructorCLI
from tests.constructor.test_symblic_constructor_crash_recovery import CHILD

ROOT = Path(__file__).resolve().parents[2]
KERNEL = {'id': 'feedfacecafe0001', 'lang': 'test'}
CURRENT_LINEAR = json.dumps({'inputs': {}, 'options': {'max_calls': 2, 'constructor': 'linear', 'determine': False,
                                                        'solve': False}})


def tree(folder):
    """Every name, byte and mtime under `folder` (no symlink is followed), plus the folder's own mtime."""
    out = {'.': os.lstat(folder).st_mtime_ns}
    for path in sorted(Path(folder).rglob('*')):
        info = os.lstat(path)
        out[str(path.relative_to(folder))] = (info.st_mode, info.st_size, info.st_mtime_ns,
                                              path.read_bytes() if path.is_file() and not path.is_symlink() else None)
    return out


class Inspect(unittest.TestCase):
    def setUp(self):
        self.cli = ConstructorCLI('setUp')
        self.cli.setUp()
        self.addCleanup(self.cli.doCleanups)
        self.folder = self.cli.folder

    # ---- helpers -------------------------------------------------------------------------------------------
    def inspect(self, folder=None, **kwargs):
        """Inspect and prove the folder is byte-, name- and mtime-identical afterwards, and repeatable."""
        folder = str(folder or self.folder)
        before = tree(folder) if os.path.isdir(folder) and not os.path.islink(folder) else None
        kwargs.setdefault('current_kernel', KERNEL)
        first = I.inspect(folder, **kwargs)
        second = I.inspect(folder, **kwargs)
        if before is not None:
            self.assertEqual(tree(folder), before)
        self.assertEqual(I.dumps(first), I.dumps(second))
        self.assertIs(first['authorizes_retry'], False)
        self.assertIn(first['classification'], I.CLASSIFICATIONS)
        return first

    def seed(self, *extra):
        code, out, err, _opts, calls, _apps = self.cli.cli(self.cli.args(*extra))
        self.assertEqual(code, 0, out + err)
        return json.loads(out), calls

    def killed_child(self):
        child = subprocess.run([sys.executable, '-B', '-c', CHILD, str(ROOT), str(self.folder), 'dispatch'],
                               cwd=ROOT, capture_output=True, text=True, timeout=25)
        self.assertEqual(child.returncode, 137, child.stderr)
        (self.folder / 'meta.json').write_text(CURRENT_LINEAR)

    def erase(self, *names):
        for name in names:
            (self.folder / name).unlink(missing_ok=True)

    def legacy_state(self, status='running', **fields):
        self.folder.mkdir(exist_ok=True)
        (self.folder / 'meta.json').write_text(CURRENT_LINEAR)
        (self.folder / 'state.json').write_text(json.dumps({'program': 'p', 'status': status, **fields}))

    # ---- no attempt versus unknowable history ------------------------------------------------------------------
    def test_empty_folder_is_no_history_not_proof(self):
        self.folder.mkdir()
        report = self.inspect()
        self.assertEqual(report['classification'], 'no_constructor_history')
        self.assertIn('meta_absent', report['reasons'])
        self.assertIn('not proof', report['next_steps'][0]['note'])
        self.assertIsNone(report['native_gate'])

    def test_ordinary_off_run_has_no_constructor_history(self):
        self.seed()
        report = self.inspect()
        self.assertEqual(report['classification'], 'no_constructor_history')
        self.assertEqual(report['mode']['selected'], 'off')
        self.assertEqual(report['native_gate'], {'mode': 'off', 'verdict': 'no_records'})

    def test_settled_current_run_reports_hashes_allowance_and_bindings(self):
        result, calls = self.seed('--constructor', 'linear')
        self.assertEqual((result['status'], calls), ('done', 1))
        report = self.inspect(current_kernel=None)              # the real kernel_id() of this process
        self.assertEqual(report['classification'], 'attempts_settled')
        self.assertEqual(report['reasons'], [])
        self.assertEqual(report['kernel']['compatibility'], 'same')
        self.assertEqual(report['mode'], {'selected': 'linear', 'selected_limits': report['records']['config']['limits'],
                                          'config': 'linear', 'journal': 'linear', 'consistent': True})
        journal = report['journal']
        self.assertEqual((journal['charged'], journal['remaining']),
                         ({'attempts': 1, 'milliseconds': 5000}, {'attempts': 15, 'milliseconds': 75000}))
        self.assertEqual(journal['phases'], {'accepted': 1})
        self.assertEqual(journal['bindings'], {'source': True, 'inputs': True})
        raw = (self.folder / J.FILE).read_bytes()
        self.assertEqual(report['records']['journal']['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(journal['last_row_sha256'], json.loads(raw.splitlines()[-1])['sha256'])
        config = R.read_config(str(self.folder))
        self.assertEqual(journal['pins']['configuration_sha256'], R.config_hash(config))
        self.assertEqual(report['native_gate'], {'mode': 'linear', 'verdict': 'records_present'})
        self.assertEqual([step['action'] for step in report['next_steps']], ['resume_exact_command', 'replay'])
        text = I.dumps(report)
        self.assertNotIn('Compute one more', text)               # no source text
        self.assertNotIn('"answer"', text)

    def test_kernel_change_is_reported_and_steers_to_recording_deployment(self):
        self.seed('--constructor', 'linear')
        report = self.inspect()                                   # a different current kernel
        self.assertEqual(report['kernel']['compatibility'], 'changed')
        self.assertIn('kernel_changed', report['reasons'])
        self.assertEqual(report['next_steps'][0]['action'], 'same_deployment')
        (self.folder / 'kernel.json').write_text('{"version": 1, "id": "a", "id": "b"}')
        report = self.inspect()
        self.assertEqual(report['kernel']['compatibility'], 'unreadable')
        self.assertIn('kernel_record_unreadable', report['reasons'])

    def test_journal_pins_alone_still_identify_the_recording_kernel(self):
        self.seed('--constructor', 'linear')
        self.erase('kernel.json', 'state.json', 'trace.jsonl')
        report = self.inspect()
        self.assertEqual(report['kernel']['recorded'][0]['source'], 'journal_pins')
        self.assertEqual(report['kernel']['compatibility'], 'changed')
        pinned = report['journal']['pins']['kernel_id']
        self.assertEqual(self.inspect(current_kernel={'id': pinned, 'lang': 'x'})['kernel']['compatibility'], 'same')

    def test_crash_after_intent_is_uncertain_and_never_authorizes_retry(self):
        self.killed_child()
        report = self.inspect()
        self.assertEqual(report['classification'], 'attempt_uncertain')
        [attempt] = report['journal']['attempts']
        self.assertEqual((attempt['phase'], attempt['disposition'], attempt['owner_appears_live']),
                         ('open', None, False))
        self.assertEqual(report['journal']['charged'], {'attempts': 1, 'milliseconds': 5000})
        self.assertEqual(report['next_steps'][0], {'authority': 'none', 'action': 'do_not_retry',
                                                    'note': I.NEXT_STEPS['attempt_uncertain'][0][2]})
        self.assertEqual(report['native_gate']['verdict'], 'records_present')
        with patch.object(J, 'owner_live', return_value=True):
            self.assertIn('owner_appears_live', I.inspect(str(self.folder), current_kernel=KERNEL)['reasons'])

    def test_deleted_records_after_crash_are_unknowable_not_no_attempt(self):
        self.killed_child()
        self.erase(J.FILE, R.CONFIG_FILE, J.LOCK_FILE, 'trace.jsonl')
        report = self.inspect()
        self.assertEqual(report['classification'], 'history_unknowable')
        self.assertIn('history_activity_valid', report['reasons'])
        self.assertEqual(report['native_gate']['verdict'], 'refused')
        self.erase('state.json')                 # deletion of every artifact: indistinguishable, and said so
        report = self.inspect()
        self.assertEqual(report['classification'], 'no_constructor_history')
        self.assertTrue(any('not proof' in step['note'] for step in report['next_steps']))

    def test_each_leftover_alone_is_unknowable(self):
        self.folder.mkdir()
        (self.folder / 'meta.json').write_text(CURRENT_LINEAR)
        for name in (J.LOCK_FILE,) + I.SLOTS:
            with self.subTest(name=name):
                (self.folder / name).write_bytes(b'')
                report = self.inspect()
                self.assertIn(report['classification'], ('history_unknowable', 'repair_unfinished'))
                self.assertNotEqual(report['native_gate']['verdict'], 'no_records')
                (self.folder / name).unlink()

    def test_records_incomplete_when_only_one_primary_remains(self):
        self.seed('--constructor', 'linear')
        self.erase(J.FILE)
        self.assertEqual(self.inspect()['classification'], 'records_incomplete')

    def test_a_held_journal_lock_is_neither_waited_on_nor_taken(self):
        self.seed('--constructor', 'linear')
        fd = os.open(self.folder / J.LOCK_FILE, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)            # a live writer's transaction
        started = time.monotonic()
        report = self.inspect()
        self.assertLess(time.monotonic() - started, J.LOCK_WAIT_SECONDS)
        self.assertEqual(report['classification'], 'attempts_settled')

    # ---- the bridge marker: only the exact supported integer asserts checkpointing -------------------------------
    def test_snapshot_marker_values(self):
        cases = [('absent', None, 'history_unknowable', 'history_marker_absent'),
                 ('current', 2, 'no_constructor_history', None),
                 ('malformed', True, 'history_unknowable', 'history_marker_malformed'),
                 ('malformed', False, 'history_unknowable', 'history_marker_malformed'),
                 ('malformed', 2.0, 'history_unknowable', 'history_marker_malformed'),
                 ('malformed', '2', 'history_unknowable', 'history_marker_malformed'),
                 ('malformed', None, 'history_unknowable', 'history_marker_malformed'),
                 ('malformed', [2], 'history_unknowable', 'history_marker_malformed'),
                 ('unsupported', 1, 'history_unknowable', 'history_marker_unsupported'),
                 ('unsupported', 3, 'history_unknowable', 'history_marker_unsupported')]
        for marker, value, classification, reason in cases:
            with self.subTest(value=value, marker=marker):
                if marker == 'absent':
                    self.legacy_state()
                else:
                    self.legacy_state(constructor_bridge=value)
                report = self.inspect()
                self.assertEqual(report['history']['marker'], marker)
                self.assertEqual(report['classification'], classification)
                if reason:
                    self.assertIn(reason, report['reasons'])
        self.legacy_state(status='done', constructor_bridge=True)    # a finished snapshot is not ambiguous
        self.assertEqual(self.inspect()['classification'], 'no_constructor_history')
        self.legacy_state(constructor_bridge=2, constructor_activity={'version': 2})
        report = self.inspect()                                  # damaged activity still means possible work
        self.assertEqual((report['classification'], report['history']['activity']),
                         ('history_unknowable', 'malformed'))

    def test_legacy_snapshot_under_off_mode_keeps_ordinary_tolerance(self):
        self.legacy_state()
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': {'max_calls': 2}}))
        self.assertEqual(self.inspect()['classification'], 'no_constructor_history')
        (self.folder / 'meta.json').unlink()                      # mode unknown: cannot rule out an enabled run
        report = self.inspect()
        self.assertEqual(report['classification'], 'history_unknowable')
        self.assertIn('history_mode_unknown', report['reasons'])

    # ---- torn tails, interrupted repairs and all eight slots -----------------------------------------------------
    def torn(self):
        self.seed('--constructor', 'linear')
        tail = b'{"v":3,"seq":4,"partial'
        with open(self.folder / J.FILE, 'ab') as stream:
            stream.write(tail)
        return tail

    def test_torn_tail_reports_exact_hash_and_prefix(self):
        tail = self.torn()
        report = self.inspect()
        self.assertEqual(report['classification'], 'journal_torn')
        self.assertEqual(report['journal']['torn']['torn_sha256'], hashlib.sha256(tail).hexdigest())
        self.assertEqual(report['journal']['torn']['torn_bytes'], len(tail))
        self.assertTrue(report['journal']['complete_rows_only'])
        self.assertEqual(report['journal']['charged'], {'attempts': 1, 'milliseconds': 5000})
        self.assertEqual(report['next_steps'][0]['action'], 'repair_torn_tail')

    def test_interrupted_repair_after_cut_is_repair_unfinished(self):
        tail = self.torn()
        with patch.object(J._Stream, '_append', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                J.repair_torn_tail(str(self.folder), hashlib.sha256(tail).hexdigest())
        report = self.inspect()
        self.assertEqual(report['classification'], 'repair_unfinished')
        slot = report['records']['quarantine'][0]
        self.assertEqual((slot['kind'], slot['recorded'], slot['sha256']),
                         ('regular', False, hashlib.sha256(tail).hexdigest()))
        self.assertIsNone(report['journal']['problem'])
        J.repair_torn_tail(str(self.folder), hashlib.sha256(tail).hexdigest())   # the owner finishes it
        report = self.inspect()
        self.assertEqual(report['classification'], 'attempts_settled')
        self.assertEqual((report['journal']['repairs'], report['journal']['quarantined']), (1, [I.SLOTS[0]]))
        (self.folder / I.SLOTS[0]).unlink()
        report = self.inspect()
        self.assertEqual(report['classification'], 'records_damaged')
        self.assertIn('quarantine_recorded_missing', report['reasons'])

    def test_every_slot_individually_and_all_eight(self):
        self.seed('--constructor', 'linear')
        for slot, name in enumerate(I.SLOTS):
            with self.subTest(slot=slot):
                (self.folder / name).write_bytes(b'kept')
                report = self.inspect()
                self.assertEqual(report['classification'], 'repair_unfinished')
                self.assertEqual([s['slot'] for s in report['records']['quarantine'] if s['kind'] != 'absent'],
                                 [slot])
                (self.folder / name).write_bytes(b'')
                self.assertIn('quarantine_empty_reservation', self.inspect()['reasons'])
                (self.folder / name).unlink()
        for name in I.SLOTS:
            (self.folder / name).write_bytes(b'')
        self.assertIn('quarantine_full', self.inspect()['reasons'])

    def test_unsafe_slots_and_lock_are_never_followed_or_opened(self):
        self.seed('--constructor', 'linear')
        target = self.folder.parent / 'outside'
        target.write_bytes(b'secret')
        for name in I.SLOTS:
            with self.subTest(name=name, kind='symlink'):
                (self.folder / name).symlink_to(target)
                report = self.inspect()
                self.assertEqual(report['classification'], 'records_damaged')
                self.assertNotIn(hashlib.sha256(b'secret').hexdigest(), I.dumps(report))
                (self.folder / name).unlink()
            with self.subTest(name=name, kind='fifo'):
                os.mkfifo(self.folder / name)
                self.assertEqual(self.inspect()['classification'], 'records_damaged')   # would block if opened
                (self.folder / name).unlink()
        os.unlink(self.folder / J.LOCK_FILE)
        os.mkfifo(self.folder / J.LOCK_FILE)
        self.assertIn('lock_unsafe', self.inspect()['reasons'])

    # ---- damaged, oversized and adversarial records ------------------------------------------------------------
    def test_damaged_primary_records(self):
        self.seed('--constructor', 'linear')
        journal = (self.folder / J.FILE).read_bytes()
        config = (self.folder / R.CONFIG_FILE).read_text()
        cases = {
            'config_invalid': (R.CONFIG_FILE, config[:-1] + ',"mode":"linear"}'),           # duplicate key
            'journal_noncanonical': (J.FILE, journal.replace(b'{"', b'{ "', 1)),
            'journal_chain': (J.FILE, journal.replace(b'"seq":2', b'"seq":2', 1).replace(b'"at_ms":', b'"at_ms":1', 1)),
            'journal_empty': (J.FILE, b''),
            'journal_malformed': (J.FILE, b'\xff\n'),
        }
        for reason, (name, data) in cases.items():
            with self.subTest(reason=reason):
                (self.folder / name).write_bytes(data.encode() if isinstance(data, str) else data)
                report = self.inspect()
                self.assertEqual(report['classification'], 'records_damaged')
                self.assertTrue(any(code.startswith(reason.split('_')[0] + '_') for code in report['reasons']),
                                report['reasons'])
                (self.folder / J.FILE).write_bytes(journal)
                (self.folder / R.CONFIG_FILE).write_text(config)
        self.assertEqual(self.inspect()['classification'], 'attempts_settled')

    def test_unsafe_journal_cannot_be_classified_as_ready_to_resume(self):
        self.seed('--constructor', 'linear')
        journal = self.folder / J.FILE
        journal.unlink()
        target = self.folder.parent / 'outside-journal'
        target.write_bytes(b'unrelated bytes must not be read')
        for kind in ('symlink', 'fifo'):
            with self.subTest(kind=kind):
                journal.symlink_to(target) if kind == 'symlink' else os.mkfifo(journal)
                try:
                    report = self.inspect()
                    self.assertEqual(report['classification'], 'records_damaged')
                    self.assertIn('journal_unsafe', report['reasons'])
                    self.assertNotIn(hashlib.sha256(target.read_bytes()).hexdigest(), I.dumps(report))
                    self.assertNotIn('resume_exact_command', [step['action'] for step in report['next_steps']])
                finally:
                    journal.unlink()

    def test_source_or_input_drift_is_contradictory(self):
        self.seed('--constructor', 'linear')
        (self.folder / 'program.sym').write_text('given base: Int = 11.\n')
        report = self.inspect()
        self.assertEqual((report['classification'], report['journal']['bindings']['source']),
                         ('records_damaged', False))
        self.assertIn('source_differs', report['reasons'])

    def test_oversized_files_are_refused_by_size_without_reading(self):
        self.seed('--constructor', 'linear')
        reads = []
        real = R._regular_bytes
        def spy(path, limit):
            reads.append(os.path.basename(path))
            return real(path, limit)
        for name, limit, reason in [(J.FILE, J.MAX_JOURNAL_BYTES, 'journal_oversized'),
                                    ('meta.json', I.HISTORY_BYTES, 'meta_oversized'),
                                    ('state.json', I.HISTORY_BYTES, 'state_unreadable'),
                                    (R.CONFIG_FILE, R.MAX_CONFIG_BYTES, 'config_oversized')]:
            with self.subTest(name=name):
                saved = (self.folder / name).read_bytes()
                with open(self.folder / name, 'r+b') as stream:
                    stream.truncate(limit + 1)                   # sparse
                reads.clear()
                with patch.object(R, '_regular_bytes', side_effect=spy):
                    report = I.inspect(str(self.folder), current_kernel=KERNEL)
                self.assertIn(reason, report['reasons'])
                self.assertNotIn(name, reads)
                if name == J.FILE:
                    self.assertEqual(report['classification'], 'records_damaged')
                    self.assertNotIn('resume_exact_command', [step['action'] for step in report['next_steps']])
                (self.folder / name).write_bytes(saved)

    def test_adversarial_history_json(self):
        bad = {'duplicate': b'{"status":"running","status":"done"}',
               'nonfinite': b'{"status":"running","x":NaN}',
               'deep': b'[' * 200 + b']' * 200,
               'not_object': b'[1]',
               'binary': b'\xff\xfe\x00'}
        for label, data in bad.items():
            with self.subTest(label=label):
                self.legacy_state()
                (self.folder / 'state.json').write_bytes(data)
                report = self.inspect()
                self.assertEqual(report['classification'], 'history_unknowable')
                self.assertIn('history_unreadable', report['reasons'])
        self.legacy_state(status='done', constructor_bridge=2)
        rows = b'{"kind":"x"}\n' * (I.TRACE_ROWS + 5)
        (self.folder / 'trace.jsonl').write_bytes(rows)
        report = self.inspect()
        self.assertEqual(report['history']['trace_rows'], I.TRACE_ROWS)
        self.assertIn('trace_unreadable', report['reasons'])
        (self.folder / 'meta.json').write_bytes(b'{"options":{"constructor":"linear"},"options":{}}')
        self.assertIn('meta_invalid', self.inspect()['reasons'])

    def test_recorded_identities_are_bounded_texts(self):
        self.legacy_state(status='done', constructor_bridge=2, kernel={'id': 'k' * 100000, 'lang': '2.5'})
        (self.folder / 'trace.jsonl').write_text(json.dumps({'kind': 'x', 'kernel': {'id': 'bad id\n'}}) + '\n')
        report = self.inspect()
        self.assertIn('kernel_identity_malformed', report['reasons'])
        self.assertLess(len(I.dumps(report)), 20000)
        self.assertEqual(report['kernel']['recorded'], [])

    def test_unexpected_failure_is_one_json_object(self):
        self.folder.mkdir()
        out = io.StringIO()
        with patch.object(I, '_history', side_effect=RuntimeError('boom')), redirect_stdout(out):
            code = I.main(['inspect', str(self.folder), '--agent-json'])
        report = json.loads(out.getvalue())
        self.assertEqual((code, report['classification'], report['reasons'], report['authorizes_retry']),
                         (1, 'inspection_failed', ['internal_RuntimeError'], False))

    def test_folder_itself_must_be_a_plain_directory(self):
        real = self.folder.parent / 'real'
        real.mkdir()
        self.folder.symlink_to(real)
        self.assertEqual(self.inspect()['classification'], 'folder_unsafe')
        self.assertEqual(I.inspect(str(self.folder.parent / 'nowhere'))['classification'], 'folder_absent')

    # ---- snapshot races ---------------------------------------------------------------------------------------
    def test_a_concurrent_writer_is_reported_not_proved(self):
        self.seed('--constructor', 'linear')
        real = R._regular_bytes
        def racing(path, limit):
            if path.endswith('trace.jsonl'):
                with open(os.path.join(os.path.dirname(path), 'trace.jsonl'), 'ab') as stream:
                    stream.write(b'{"kind":"x"}\n')
            return real(path, limit)
        with patch.object(R, '_regular_bytes', side_effect=racing):
            report = I.inspect(str(self.folder), current_kernel=KERNEL)
        self.assertEqual(report['classification'], 'snapshot_inconsistent')
        self.assertFalse(report['snapshot']['consistent'])
        self.assertIn('trace.jsonl', report['snapshot']['changed'])
        def vanishing(path, limit):
            return None if path.endswith('state.json') else real(path, limit)
        with patch.object(R, '_regular_bytes', side_effect=vanishing):
            self.assertEqual(I.inspect(str(self.folder), current_kernel=KERNEL)['classification'],
                             'snapshot_inconsistent')


class InspectProcess(unittest.TestCase):
    """The command-line entry point (tools/symblic constructor inspect), as another agent would call it."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)

    def symblic(self, *args):
        env = {**os.environ, 'SYMBLIC_ROOT': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
        return subprocess.run(['bash', str(ROOT / 'tools/symblic'), *args], capture_output=True, text=True,
                              env=env, timeout=120)

    def test_exact_agent_json_and_exit_codes(self):
        folder = self.base / 'run'
        folder.mkdir()
        (folder / 'meta.json').write_text(CURRENT_LINEAR)
        (folder / 'state.json').write_text('{"status":"running","constructor_bridge":true}')
        before = tree(str(folder))
        done = self.symblic('constructor', 'inspect', str(folder), '--agent-json')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.count('\n'), 1)
        report = json.loads(done.stdout)
        self.assertEqual(done.stdout, I.dumps(report) + '\n')
        self.assertEqual(report['classification'], 'history_unknowable')
        self.assertEqual(report['folder'], str(folder))
        self.assertEqual(tree(str(folder)), before)
        again = self.symblic('constructor', 'inspect', str(folder), '--agent-json')
        self.assertEqual(again.stdout, done.stdout)
        absent = self.symblic('constructor', 'inspect', str(self.base / 'none'), '--agent-json')
        self.assertEqual((absent.returncode, json.loads(absent.stdout)['classification']), (1, 'folder_absent'))
        usage = self.symblic('constructor', 'inspect', str(folder), '--repair')
        self.assertEqual((usage.returncode, usage.stdout), (2, ''))
        human = self.symblic('constructor', 'inspect', str(folder))
        self.assertTrue(human.stdout.startswith('history_unknowable: '), human.stdout)

    def test_no_solver_import_inventory_or_child_process(self):
        folder = self.base / 'run'
        folder.mkdir()
        probe = r'''
import json, subprocess, sys
sys.path.insert(0, sys.argv[1])
spawned = []
real = subprocess.Popen.__init__
def spy(self, args, *a, **k):
    spawned.append(list(args) if isinstance(args, (list, tuple)) else [args])
    return real(self, args, *a, **k)
subprocess.Popen.__init__ = spy
from symblic.constructor import inspect as I
report = I.inspect(sys.argv[2])
loaded = sorted(m for m in sys.modules if m == 'z3' or m.startswith('z3.') or m in (
    'symblic.constructor.core', 'symblic.linear.constructor', 'symblic.linear.worker', 'symblic.linear.resources',
    'symblic_linear_provision'))
print(json.dumps({'loaded': loaded, 'spawned': spawned, 'classification': report['classification']}))
'''
        done = subprocess.run([sys.executable, '-B', '-c', probe, str(ROOT), str(folder)], capture_output=True,
                              text=True, timeout=60, cwd=str(self.base))
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result['loaded'], [])
        # kernel_id() itself asks the JS adapter for `node --version`; nothing else may start.
        self.assertTrue(all(len(argv) == 2 and argv[1] == '--version' and os.path.basename(argv[0]) == 'node'
                            for argv in result['spawned']), result['spawned'])
        self.assertEqual(result['classification'], 'no_constructor_history')


if __name__ == '__main__':
    unittest.main()
