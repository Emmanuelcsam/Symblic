"""Constructor cleanup diagnostics survive both journal and native error boundaries.

Temporary files and injected I/O failures only; no model, worker, solver or host store.
"""
import errno
import os
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest import mock

from symblic.constructor import core as C
from symblic.constructor import journal as J

# A memory-backed temporary folder makes the many fsyncs fast; any temporary folder works.
SHM = '/dev/shm' if os.path.isdir('/dev/shm') else None


def pins():
    return {'source_sha256': 'a' * 64, 'input_sha256': 'b' * 64, 'kernel_id': 'test-kernel',
            'kind': 'smt_linear', 'mode': 'linear', 'selection_policy': 'canonical_min_v1',
            'implementation_sha256': 'c' * 64, 'worker_sha256': 'd' * 64,
            'configuration_sha256': 'e' * 64, 'allowance': {'attempts': 4, 'milliseconds': 10000}}


def request():
    return {'occurrence': 'ask:1', 'item': None, 'contract_sha256': '1' * 64,
            'constants_sha256': '2' * 64, 'dependencies_sha256': '3' * 64,
            'limits': {'milliseconds': 1000, 'resource_limit': 10000,
                       'address_space_bytes': 268435456}}


class CleanupNotes(unittest.TestCase):
    def failed_write(self, boundary, rollback):
        temp = tempfile.TemporaryDirectory(dir=SHM)
        self.addCleanup(temp.cleanup)
        journal = J.Journal(temp.name, pins())
        original = OSError(errno.ENOSPC, 'synthetic write failure')
        original.add_note('original write diagnostic')
        real_write = os.write

        def write(fd, data):
            real_write(fd, data[:12])
            raise original

        operation = journal.begin if boundary == 'journal' else C._typed_errors(journal.begin)
        error_type = J.JournalError if boundary == 'journal' else C.S.SymblicError
        with mock.patch.object(J.os, 'write', side_effect=write), \
                mock.patch.object(J.os, rollback, side_effect=OSError(errno.EIO, 'synthetic rollback failure')):
            with self.assertRaises(error_type) as caught:
                operation(request())

        self.assertTrue(journal._poisoned)
        with self.assertRaises(J.JournalError) as refused:
            journal.begin(request())
        self.assertEqual(refused.exception.code, 'durability')
        fresh_reader = J.Journal(temp.name, pins())
        if rollback == 'ftruncate':
            self.assertEqual(Path(journal.path).stat().st_size, 12)
            with self.assertRaises(J.JournalError) as damaged:
                fresh_reader.lookup(request())
            self.assertEqual(damaged.exception.code, 'torn_tail')
        else:
            self.assertEqual(Path(journal.path).read_bytes(), b'')
            self.assertEqual(fresh_reader.lookup(request())['kind'], 'fresh')
        return caught.exception, original

    def test_journal_wrapper_retains_original_and_rollback_notes(self):
        for rollback in ('ftruncate', 'fsync'):
            with self.subTest(rollback=rollback):
                failure, original = self.failed_write('journal', rollback)
                self.assertEqual(failure.code, 'durability')
                self.assertIn('synthetic write failure', str(failure))
                notes = getattr(failure, '__notes__', [])
                self.assertEqual(notes, original.__notes__)
                self.assertIsNot(notes, original.__notes__)
                self.assertIn('original write diagnostic', notes)
                self.assertTrue(any('synthetic rollback failure' in note and 'torn tail may remain' in note
                                    for note in notes))
                rendered = ''.join(traceback.format_exception(failure))
                self.assertIn('original write diagnostic', rendered)
                self.assertIn('torn tail may remain', rendered)

    def test_native_serialized_error_shows_rollback_warning(self):
        for rollback in ('ftruncate', 'fsync'):
            with self.subTest(rollback=rollback):
                failure, original = self.failed_write('native', rollback)
                public = failure.as_dict()
                self.assertEqual(public['code'], 'SYM_UNCERTAIN')
                self.assertIn('synthetic write failure', public['message'])
                self.assertIn('original write diagnostic', public['message'])
                self.assertIn('synthetic rollback failure', public['message'])
                self.assertIn('torn tail may remain', public['message'])
                self.assertIsInstance(failure.__cause__, J.JournalError)
                self.assertEqual(failure.__cause__.__notes__, original.__notes__)

    def test_unannotated_native_error_keeps_message_and_kind(self):
        for code, kind in (('durability', 'uncertain'), ('budget', 'budget'), ('drift', 'version')):
            with self.subTest(code=code):
                original = J.JournalError(code, 'original refusal')

                @C._typed_errors
                def refuse():
                    raise original

                with self.assertRaises(C.S.SymblicError) as caught:
                    refuse()
                self.assertEqual(caught.exception.as_dict(), {'message': 'Constructor: original refusal',
                                 'line': 0, 'col': 0, 'kind': kind, 'code': 'SYM_' + kind.upper()})
                self.assertIs(caught.exception.__cause__, original)
