"""Agent wrapper uses pinned native execution and exact accepted values, no live calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.delegate import contracts as D
from symblic.delegate import run as H
from tests.delegate.test_symblic_delegate import ARITHMETIC, TRANSFORM, Fake


class NativeDelegation(unittest.TestCase):
    def test_native_summary_reaches_the_parent_without_reinterpretation(self):
        original = H.Run.execute
        summary = {'version': 1, 'determined': 1, 'unassessed': 2, 'cloud_accepted': 0}

        def execute(run):
            return {**original(run), 'determinism_summary': summary}

        with patch.object(H.Run, 'execute', execute):
            result = H.run_task(ARITHMETIC, applicators=Fake())
        self.assertEqual(result['determinism_summary'], summary)

    def test_exact_parent_result_and_saved_record(self):
        apps = Fake()
        with tempfile.TemporaryDirectory() as folder:
            result = H.run_task(ARITHMETIC, applicators=apps, folder=folder)
            self.assertTrue(result['accepted'], result['error'])
            self.assertEqual(result['result'], {'#q': '1/2'})
            self.assertEqual(apps.requests, [])
            meta = json.loads(Path(folder, 'meta.json').read_text())
            self.assertEqual(meta['delegation']['contract_id'], result['contract_id'])
            self.assertIn('execution_pins', meta['options'])
            self.assertRaises(D.ContractError, H.run_task, ARITHMETIC, applicators=apps, folder=folder)

    def test_rejected_candidate_never_reaches_parent_and_retry_remains_native(self):
        apps = Fake([[4, 5], [1, 2]])
        accepted = H.run_task(TRANSFORM, applicators=apps, by='fake:child')
        self.assertTrue(accepted['accepted'], accepted['error'])
        self.assertEqual(accepted['result'], [1, 2])
        self.assertEqual(accepted['calls'], 2)
        failed = H.run_task({**TRANSFORM, 'calls': 1}, applicators=Fake([[4, 5]]), by='fake:child')
        self.assertFalse(failed['accepted'])
        self.assertIsNone(failed['result'])

