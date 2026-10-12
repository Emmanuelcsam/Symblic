"""Portable exports retain crash/recovery evidence; fake providers and disposable stores only."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.constructor import core as C
from symblic.constructor import journal as J
from symblic.kernel import lockfile as K
from symblic.kernel import run as R
from tests.constructor.test_symblic_constructor_missing_records import snapshot

SOURCE = 'ask x: Int "Return seven."\nensure x = 7 else retry.\nshow x.'
OPTIONS = {'constructor': 'linear', 'determine': False, 'profile': 'verified',
           'by': 'fake:seven', 'effort': 'low', 'max_calls': 1}


class Apps:
    def call(self, _request):
        return {'ok': True, 'json': {'answer': 7}, 'model': 'fake', 'node': 'isolated'}


class ExportRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'run'
        self.folder.mkdir()
        (self.folder / 'program.sym').write_text(SOURCE)
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': OPTIONS}))
        with patch.object(C, '_runtime', return_value=None):
            self.report = R.Run(SOURCE, {}, Apps(), OPTIONS, folder=str(self.folder)).execute()
        self.assertEqual(self.report['status'], 'done')
        self.assertEqual(K.make_lock(str(self.folder))['symblic_lock'], 3)

    def refuses_without_mutation(self):
        before = snapshot(self.folder)
        with patch.object(C, '_runtime', side_effect=AssertionError('export loaded runtime')):
            with self.assertRaises(K.LockError):
                K.make_lock(str(self.folder))
        self.assertEqual(snapshot(self.folder), before)

    def test_truncate_without_repair_audit_cannot_export(self):
        with (self.folder / J.FILE).open('ab') as stream:
            stream.write(b'{')
        append = J._Stream._append

        def die_before_audit(stream, state, events):
            if events[0][0] == 'repair':
                raise SystemExit(137)
            return append(stream, state, events)

        with patch.object(J._Stream, '_append', die_before_audit):
            with self.assertRaises(SystemExit):
                J.repair_torn_tail(str(self.folder), hashlib.sha256(b'{').hexdigest())
        self.assertEqual(J._validate((self.folder / J.FILE).read_bytes()).repairs, 0)
        self.assertEqual((self.folder / J._quarantine_name(0)).read_bytes(), b'{')
        self.refuses_without_mutation()

    def test_every_fixed_slot_refuses_including_dangling_links(self):
        for slot in range(8):
            with self.subTest(slot=slot):
                path = self.folder / J._quarantine_name(slot)
                path.symlink_to(self.folder / 'absent')
                self.refuses_without_mutation()
                path.unlink()

    def test_missing_records_cannot_downgrade_fallback_to_ordinary_lock(self):
        for name in (J.FILE, 'constructor-config.json'):
            (self.folder / name).unlink()
        self.refuses_without_mutation()  # the retained lock is enough
        (self.folder / '.constructor-events.lock').unlink()
        (self.folder / 'trace.jsonl').unlink()
        self.refuses_without_mutation()  # the durable state marker is enough

    def test_unused_config_exception_does_not_erase_retained_history(self):
        (self.folder / J.FILE).unlink()
        (self.folder / '.constructor-events.lock').unlink()
        self.refuses_without_mutation()

    def test_legacy_fallback_trace_without_activity_field_also_refuses(self):
        for name in (J.FILE, 'constructor-config.json', '.constructor-events.lock'):
            (self.folder / name).unlink()
        # Simulate the older running snapshot that had no constructor-specific fields.
        (self.folder / 'state.json').write_text(json.dumps({
            'status': 'done', 'version': self.report['version'], 'kernel': self.report['kernel']}))
        self.refuses_without_mutation()


if __name__ == '__main__':
    unittest.main()
