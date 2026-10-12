"""Regression probes for original cancellation and bounded interrupted-repair retention.

All files are temporary. No models, solver workers, host stores or network.
Set SYMBLIC_JOURNAL_REVIEW_SOURCE only to run these same probes against a prior source.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

# A memory-backed temporary folder makes the many fsyncs fast; any temporary folder works.
SHM = '/dev/shm' if os.path.isdir('/dev/shm') else None

SOURCE = Path(os.environ.get('SYMBLIC_JOURNAL_REVIEW_SOURCE',
                             str(Path(__file__).resolve().parents[2] / 'symblic/constructor/journal.py')))
spec = importlib.util.spec_from_file_location('_journal_v3_review', SOURCE)
J = importlib.util.module_from_spec(spec)
spec.loader.exec_module(J)


def pins():
    return {'source_sha256': 'a'*64, 'input_sha256': 'b'*64, 'kernel_id': 'test-kernel', 'kind': 'smt_linear',
            'mode': 'linear', 'selection_policy': 'canonical_min_v1', 'implementation_sha256': 'c'*64,
            'worker_sha256': 'd'*64, 'configuration_sha256': 'e'*64,
            'allowance': {'attempts': 4, 'milliseconds': 10000}}


def request():
    return {'occurrence': 'ask:1', 'item': None, 'contract_sha256': '1'*64, 'constants_sha256': '2'*64,
            'dependencies_sha256': '3'*64,
            'limits': {'milliseconds': 1000, 'resource_limit': 10000, 'address_space_bytes': 268435456}}


class Stop(BaseException):
    pass


class ReviewV3(unittest.TestCase):
    def test_all_write_cleanup_boundaries_keep_original_stop_and_poison(self):
        for target in ('journal', 'folder_sync', 'folder_lock'):
            for kind in (OSError, KeyboardInterrupt, SystemExit):
                with self.subTest(target=target, secondary=kind.__name__), \
                        tempfile.TemporaryDirectory(dir=SHM) as folder:
                    journal = J.Journal(folder, pins())
                    original, secondary = Stop('original'), kind('cleanup')
                    close_real, sync_real = J.os.close, J.os.fsync
                    expected = {'journal': journal.path, 'folder_sync': folder,
                                'folder_lock': str(Path(folder)/J.LOCK_FILE)}[target]

                    def close(fd):
                        path = os.readlink(f'/proc/self/fd/{fd}')
                        close_real(fd)
                        if path == expected:
                            raise secondary

                    def sync(fd):
                        if os.readlink(f'/proc/self/fd/{fd}') == folder:
                            raise original
                        return sync_real(fd)

                    primary_patch = (mock.patch.object(J.os, 'fsync', side_effect=sync) if target == 'folder_sync'
                                     else mock.patch.object(J.os, 'write', side_effect=original))
                    caught = None
                    with mock.patch.object(J.os, 'close', side_effect=close), primary_patch:
                        try:
                            journal.begin(request())
                        except BaseException as exc:
                            caught = exc
                    self.assertIs(caught, original)
                    self.assertTrue(journal._poisoned)
                    with self.assertRaises(J.JournalError) as refused:
                        journal.begin(request())
                    self.assertEqual(refused.exception.code, 'durability')

    def test_first_cleanup_failure_propagates_and_never_returns_an_attempt(self):
        for target in ('journal', 'folder_sync', 'folder_lock'):
            for kind in (OSError, KeyboardInterrupt, SystemExit):
                with self.subTest(target=target, kind=kind.__name__), \
                        tempfile.TemporaryDirectory(dir=SHM) as folder:
                    journal = J.Journal(folder, pins())
                    later = kind('first close failure')
                    close_real = J.os.close
                    expected = {'journal': journal.path, 'folder_sync': folder,
                                'folder_lock': str(Path(folder)/J.LOCK_FILE)}[target]

                    def close(fd):
                        path = os.readlink(f'/proc/self/fd/{fd}')
                        close_real(fd)
                        if path == expected:
                            raise later
                    caught = None
                    with mock.patch.object(J.os, 'close', side_effect=close):
                        try:
                            journal.begin(request())
                        except BaseException as exc:
                            caught = exc
                    self.assertIsNotNone(caught)
                    if kind is OSError:
                        self.assertIsInstance(caught, J.JournalError)
                        self.assertEqual(caught.code, 'durability')
                    else:
                        self.assertIs(caught, later)
                    self.assertTrue(journal._poisoned)
                    self.assertTrue(J.summary(folder)['uncertain'])

    def test_read_and_open_cleanup_keep_original_control_flow(self):
        for point in ('read', 'open_validation'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir=SHM) as folder:
                path = Path(folder)/J.FILE
                path.write_bytes(b'')
                original = Stop('read stop')
                close_real, stat_real = J.os.close, J.os.fstat
                stat_calls = []

                def close(fd):
                    close_real(fd)
                    raise SystemExit('close interruption')

                def fstat(fd):
                    stat_calls.append(fd)
                    if point == 'open_validation':
                        raise original
                    return stat_real(fd)
                with mock.patch.object(J.os, 'close', side_effect=close), \
                        mock.patch.object(J.os, 'fstat', side_effect=fstat), \
                        mock.patch.object(J.os, 'read', side_effect=original):
                    try:
                        J._read_bytes(str(path))
                        caught = None
                    except BaseException as exc:
                        caught = exc
                self.assertIs(caught, original)

    def test_ninth_interrupted_post_cut_repair_refuses_at_exact_retention_bound(self):
        with tempfile.TemporaryDirectory(dir=SHM) as folder:
            path = Path(folder)/J.FILE
            for i in range(J.MAX_REPAIRS):
                torn = ('{"partial":'+str(i)).encode().ljust(J.MAX_ROW_BYTES, b'x')
                path.write_bytes(torn)
                with mock.patch.object(J._Stream, '_append', side_effect=Stop('before audit')):
                    with self.assertRaises(Stop):
                        J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
            self.assertEqual(J._validate(path.read_bytes()).repairs, 0)
            files = list(Path(folder).glob('constructor-events.torn-*.bin'))
            self.assertEqual(len(files), J.MAX_REPAIRS)
            self.assertEqual(sum(p.stat().st_size for p in files), J.MAX_REPAIRS*J.MAX_ROW_BYTES)
            torn = b'{"ninth":0'
            path.write_bytes(torn)
            before = {p.name: p.read_bytes() for p in Path(folder).iterdir()}
            with self.assertRaises(J.JournalError) as caught:
                J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
            self.assertEqual(caught.exception.code, 'repair_limit')
            self.assertEqual(before, {p.name: p.read_bytes() for p in Path(folder).iterdir()})

    def test_empty_and_partial_reservations_consume_bounded_capacity_before_cut(self):
        for partial in (False, True):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory(dir=SHM) as folder:
                path = Path(folder)/J.FILE
                torn = b'{"torn":1'
                path.write_bytes(torn)
                real_write = J.os.write

                def write(fd, data):
                    if partial:
                        real_write(fd, bytes(data[:2]))
                    raise Stop('quarantine interrupted')
                for _ in range(J.MAX_REPAIRS):
                    with mock.patch.object(J.os, 'write', side_effect=write):
                        with self.assertRaises(Stop):
                            J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
                    self.assertEqual(path.read_bytes(), torn)
                files = list(Path(folder).glob('constructor-events.torn-*.bin'))
                self.assertEqual(len(files), J.MAX_REPAIRS)
                self.assertEqual(sorted(p.stat().st_size for p in files), [2 if partial else 0]*J.MAX_REPAIRS)
                self.assertFalse(list(Path(folder).glob('*.tmp')))
                with self.assertRaises(J.JournalError) as caught:
                    J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
                self.assertEqual(caught.exception.code, 'repair_limit')

    def test_slot_reservation_is_synced_before_first_retained_byte(self):
        with tempfile.TemporaryDirectory(dir=SHM) as folder:
            path = Path(folder)/J.FILE
            torn = b'{"torn":2'
            path.write_bytes(torn)
            events = []
            sync_real, write_real = J.os.fsync, J.os.write

            def sync(fd):
                name = os.readlink(f'/proc/self/fd/{fd}')
                events.append(('sync', Path(name).name, os.fstat(fd).st_size))
                return sync_real(fd)

            def write(fd, data):
                events.append(('write', Path(os.readlink(f'/proc/self/fd/{fd}')).name, len(data)))
                return write_real(fd, data)
            with mock.patch.object(J.os, 'fsync', side_effect=sync), mock.patch.object(J.os, 'write', side_effect=write):
                row = J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
            self.assertEqual(events[0], ('sync', row['quarantine'], 0))
            self.assertEqual(events[1][:2], ('sync', Path(folder).name))
            self.assertEqual(events[2], ('write', row['quarantine'], len(torn)))
            self.assertEqual((Path(folder)/row['quarantine']).read_bytes(), torn)

    def test_quarantine_close_never_replaces_write_stop(self):
        with tempfile.TemporaryDirectory(dir=SHM) as folder:
            path = Path(folder)/J.FILE
            torn = b'{"torn":3'
            path.write_bytes(torn)
            primary = Stop('quarantine write')
            close_real = J.os.close

            def close(fd):
                name = os.readlink(f'/proc/self/fd/{fd}')
                close_real(fd)
                if 'constructor-events.torn-' in name:
                    raise KeyboardInterrupt('quarantine close')
            with mock.patch.object(J.os, 'write', side_effect=primary), mock.patch.object(J.os, 'close', side_effect=close):
                try:
                    J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
                    caught = None
                except BaseException as exc:
                    caught = exc
            self.assertIs(caught, primary)
            self.assertEqual(path.read_bytes(), torn)

    def test_same_confirmed_tail_reuses_durable_slot_before_or_after_cut(self):
        for phase in ('before_cut', 'before_audit'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory(dir=SHM) as folder:
                path = Path(folder)/J.FILE
                torn = b'{"torn":4'
                path.write_bytes(torn)
                failure = (mock.patch.object(J.os, 'ftruncate', side_effect=Stop('before cut')) if phase == 'before_cut'
                           else mock.patch.object(J._Stream, '_append', side_effect=Stop('before audit')))
                with failure:
                    with self.assertRaises(Stop):
                        J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
                row = J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
                self.assertEqual(row['quarantine'], 'constructor-events.torn-0.bin')
                self.assertEqual(len(list(Path(folder).glob('constructor-events.torn-*.bin'))), 1)
                self.assertEqual(J._validate(path.read_bytes()).repairs, 1)

    def test_zero_write_is_a_bounded_durability_failure(self):
        with tempfile.TemporaryDirectory(dir=SHM) as folder:
            journal = J.Journal(folder, pins())
            calls = []
            def write(fd, data):
                calls.append(1)
                if len(calls) > 1:
                    raise Stop('old implementation repeated zero write')
                return 0
            caught = None
            with mock.patch.object(J.os, 'write', side_effect=write):
                try:
                    journal.begin(request())
                except BaseException as exc:
                    caught = exc
            self.assertIsInstance(caught, J.JournalError)
            self.assertEqual(caught.code, 'durability')
            self.assertEqual(len(calls), 1)

    def test_reader_refuses_reused_slot_even_with_resealed_hashes(self):
        with tempfile.TemporaryDirectory(dir=SHM) as folder:
            path = Path(folder)/J.FILE
            torn = b'{"torn":5'
            path.write_bytes(torn)
            row = J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
            forged = dict(row, seq=row['seq']+1, prev=row['sha256'])
            del forged['sha256']
            forged['sha256'] = J._sha('row', forged)
            raw = path.read_bytes()+J.canonical(forged).encode('ascii')+b'\n'
            with self.assertRaises(J.JournalError) as caught:
                J._validate(raw)
            self.assertEqual(caught.exception.code, 'state')

    def test_reserved_unsafe_slot_refuses_without_cut_or_following_link(self):
        for special in ('symlink', 'fifo'):
            with self.subTest(special=special), tempfile.TemporaryDirectory(dir=SHM) as folder:
                path = Path(folder)/J.FILE
                torn = b'{"torn":6'
                path.write_bytes(torn)
                slot = Path(folder)/'constructor-events.torn-0.bin'
                if special == 'symlink':
                    slot.symlink_to(path)
                else:
                    os.mkfifo(slot)
                with self.assertRaises(J.JournalError) as caught:
                    J.repair_torn_tail(folder, hashlib.sha256(torn).hexdigest())
                self.assertEqual(caught.exception.code, 'state')
                self.assertEqual(path.read_bytes(), torn)


if __name__ == '__main__':
    unittest.main(verbosity=2)
