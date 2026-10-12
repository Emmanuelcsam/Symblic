"""The intent session store (symblic.intent.store): atomic records, integrity and the model-call budget.

Temporary folders only; no model, network or worker.
"""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from symblic.intent import records as I
from symblic.intent import store as Store


class IntentStore(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'sessions'
        self.state = I.new_intent('0123456789ab', 'Count the petals of a five-petal flower.')

    def job(self, row, job_id='job-1', kind='analyse'):
        row['jobs'].append({'id': job_id, 'status': 'running', 'kind': kind,
                            'content_revision': row['state']['content_revision']})
        folder = self.root / row['state']['id']
        with Store.locked(folder):
            Store.save(folder, row)
        return folder

    def test_make_load_and_idempotent_create_key(self):
        row = Store.make(self.root, self.state, limit=3, create_key='create-1', repairs=1)
        folder = self.root / '0123456789ab'
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder / 'record.json').stat().st_mode), 0o600)
        with Store.locked(folder):
            loaded = Store.load(folder)
        self.assertEqual({k: v for k, v in loaded.items() if k != 'integrity'}, row)
        self.assertEqual(loaded['integrity'], Store.sha(row))
        self.assertEqual(Store.make(self.root, self.state, limit=3, create_key='create-1'), loaded)
        with self.assertRaises(Store.StoreError):
            Store.make(self.root, self.state, limit=3, create_key='other')

    def test_damaged_or_tampered_record_is_an_error_not_an_empty_session(self):
        Store.make(self.root, self.state, limit=3)
        folder = self.root / '0123456789ab'
        record = json.loads((folder / 'record.json').read_text())
        record['budget']['used'] = 0
        record['state']['goal'] = 'Changed outside the store.'
        (folder / 'record.json').write_text(json.dumps(record))
        with self.assertRaises(Store.StoreError):
            Store.load(folder)
        (folder / 'record.json').write_text('{broken')
        with self.assertRaises(Store.StoreError):
            Store.load(folder)

    def test_reserve_spends_the_budget_and_repairs_draw_on_their_own_allowance(self):
        row = Store.make(self.root, self.state, limit=3, repairs=1)
        folder = self.job(row)
        self.assertEqual(Store.reserve(folder, 'job-1', 'fake:small', 3, 1), 1)
        self.assertEqual(Store.reserve(folder, 'job-1', 'fake:small', 3, 1), 2)   # a repeat on the same revision
        with self.assertRaises(Store.StoreError):
            Store.reserve(folder, 'job-1', 'fake:small', 3, 1)                     # repair allowance exhausted
        with Store.locked(folder):
            saved = Store.load(folder)
        self.assertEqual(saved['budget']['used'], 2)
        self.assertEqual([r['repair'] for r in saved['budget']['reservations']], [False, True])
        with self.assertRaises(Store.StoreError):
            Store.reserve(folder, 'missing-job', 'fake:small', 3, 1)

    def test_identifier_and_finite_json_bounds(self):
        for bad in ('../escape', 'ABCDEF123456', '0123', None):
            with self.assertRaises(Store.StoreError):
                Store.identifier(bad)
        with self.assertRaises(Store.StoreError):
            Store.encode({'value': float('nan')})


if __name__ == '__main__':
    unittest.main()
