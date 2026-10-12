"""Public handoff fixture and record replay boundary; no provider/network calls."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from symblic.delegate import contracts as D
from symblic.delegate import run as DR
from symblic.kernel import grounding as G

ROOT = Path(__file__).resolve().parents[2]
TASK = json.loads((Path(__file__).resolve().parent / 'fixtures' / 'agent-handoff.task.json').read_text())
ARITHMETIC = {'template': 'exact_arithmetic', 'params': {
    'operation': 'add', 'left': {'numerator': 1, 'denominator': 3},
    'right': {'numerator': 1, 'denominator': 6}}}


class Fake:
    def __init__(self, choice=2):
        self.choice, self.requests = choice, []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': self.choice}}


class Handoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'record'

    def replay(self):
        return subprocess.run([str(ROOT / 'tools/symblic'), 'replay', str(self.folder), '--agent-json'],
                              capture_output=True, text=True, timeout=30, check=False,
                              env={**os.environ, 'DASHBOARD_DIR': str(ROOT)})

    def test_public_witness_handoff_preserves_exact_span_and_route_identity(self):
        contract = D.inspect_task(TASK)
        self.assertTrue(contract['ok'])
        pinned = {**TASK, 'expected_contract_id': contract['contract_id']}
        apps = Fake()
        receipt = DR.run_task(pinned, applicators=apps, folder=str(self.folder))
        self.assertTrue(receipt['accepted'], receipt.get('error'))
        self.assertEqual(receipt['contract_id'], contract['contract_id'])
        self.assertFalse(receipt['routing']['allow_cloud'])
        self.assertEqual(len(apps.requests), 1)
        source = G.source_record('order-7', TASK['params']['text'], 1)
        self.assertEqual(receipt['result'], G.source_span(source, 9, 26))
        self.assertEqual(receipt['routing_id'], DR.prepare(pinned)['routing_id'])
        # Membership/source association is not a relevance checker.
        wrong = DR.run_task(pinned, applicators=Fake(choice=1))
        self.assertTrue(wrong['accepted'])
        self.assertEqual(wrong['result']['quote'], 'Order: 7\n')

    def test_valid_delegated_kernel_replay_and_ordinary_replay_remain_native(self):
        apps = Fake()
        original = DR.run_task(ARITHMETIC, applicators=apps, folder=str(self.folder))
        self.assertTrue(original['accepted'])
        self.assertEqual(original['result'], {'#q': '1/2'})
        self.assertEqual(apps.requests, [])
        replay = self.replay()
        self.assertEqual(replay.returncode, 0, replay.stderr + replay.stdout)
        native = json.loads(replay.stdout)
        self.assertEqual(native['status'], 'done')
        self.assertEqual(native['calls'], 0)
        meta_path = self.folder / 'meta.json'
        meta = json.loads(meta_path.read_text())
        del meta['delegation']
        meta_path.write_text(json.dumps(meta))
        ordinary = self.replay()
        self.assertEqual(ordinary.returncode, 0, ordinary.stderr + ordinary.stdout)
        self.assertEqual(json.loads(ordinary.stdout)['status'], 'done')

    def test_route_drift_refuses_before_replay_can_touch_prior_state(self):
        original = DR.run_task(TASK, applicators=Fake(), folder=str(self.folder))
        self.assertTrue(original['accepted'])
        state_before = (self.folder / 'state.json').read_bytes()
        calls_before = (self.folder / 'calls.jsonl').read_bytes()
        meta_path = self.folder / 'meta.json'
        meta = json.loads(meta_path.read_text())
        meta['options']['auto_route']['repairs'] = 1
        meta_path.write_text(json.dumps(meta))
        refused = self.replay()
        self.assertEqual(refused.returncode, 1, refused.stderr)
        error = json.loads(refused.stdout)
        self.assertFalse(error['accepted'])
        self.assertEqual(error['error']['kind'], 'routing')
        self.assertEqual((self.folder / 'state.json').read_bytes(), state_before)
        self.assertEqual((self.folder / 'calls.jsonl').read_bytes(), calls_before)


if __name__ == '__main__':
    unittest.main()
