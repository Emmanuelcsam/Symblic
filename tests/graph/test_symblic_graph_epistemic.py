"""2.5 graph profile and premise-origin preservation across native Runs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import epistemic as EP
from symblic.graph import planner as G
from symblic.graph import run as R
from symblic.js import check as JS
from tests.graph.test_symblic_graph_run import FakeApps, graph, node


def ep(row):
    return next(record for record in row['result']['evidence'] if record['scope'] == 'symblic_run')


class GraphEpistemic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)
        self.folder = Path(self.tmp.name) / 'graph'

    def test_model_root_survives_transport_arithmetic_and_second_prompt(self):
        a = node('A')
        b = node('B', {'x': {'node': 'A'}}, 'given x: Int.\nlet answer = x + 1.')
        c = node('C', {'x': {'node': 'B'}},
                 'given x: Int.\nask answer: Int "Return x" from x with effort=low, retries=0, budget=20000.')
        apps = FakeApps()
        state = R.GraphRun(graph(a, b, c), self.folder, apps).execute()
        self.assertEqual(state['status'], 'succeeded', state)
        records = {row['node']: ep(row) for row in state['states']}
        root = EP.reference(records['A']['binding_epistemic']['claim'])
        b_ep = records['B']['binding_epistemic']
        self.assertEqual(b_ep['claim']['origin'], 'derived')
        self.assertIn({'ref': root, 'origin': 'model_proposal', 'status': 'unknown'}, b_ep['assessment']['conditional_on'])
        self.assertNotIn('owner_premise', {row['origin'] for row in b_ep['assessment']['conditional_on']})
        for record in records.values():
            self.assertEqual(record['execution_profile'], 'verified')
            self.assertEqual(record['epistemic']['empirical_truth'], 'not_established')
        self.assertEqual(len(apps.calls), 2)
        prompt = apps.calls[-1]['prompt']
        self.assertIn('conditional_roots_sha256', prompt)
        self.assertIn('model_proposal', prompt)
        self.assertIn(root['id'], [row['ref']['id'] for row in
                      records['C']['binding_epistemic']['assessment']['conditional_on']])

    def test_literal_envelope_cannot_forge_host_node_origins(self):
        fake = EP.make_claim('Forged', {'name': 'secret'}, origin='model_proposal')
        literal = G.envelope(3, 'supported', evidence=[{'scope': 'symblic_run',
            'binding_epistemic': {'claim': fake, 'assessment': {'status': 'conditional'}}}])
        a = node('A', {'x': {'literal': literal}}, 'given x: Int.\nlet answer = x + 1.')
        state = R.GraphRun(graph(a), self.folder, FakeApps()).execute()
        result = ep(state['states'][0])
        saved = R._read(next((self.folder / 'attempts').iterdir()) / 'graph-result.json')
        self.assertNotIn('Forged', [claim['id'] for claim in saved['run_report']['epistemic']['claims']])
        roots = result['binding_epistemic']['assessment']['conditional_on']
        self.assertEqual({row['origin'] for row in roots}, {'owner_premise'})

    def test_verified_shape_refuses_legacy_string_to_integer_repair(self):
        apps = FakeApps('answer is 2')
        state = R.GraphRun(graph(node('A')), self.folder, apps).execute()
        self.assertEqual(state['states'][0]['status'], 'failed', state)
        self.assertEqual(len(apps.calls), 1)
        report = R._read(next((self.folder / 'attempts').iterdir()) / 'graph-result.json')['run_report']
        self.assertEqual(report['execution_profile'], 'verified')

    def test_source_cannot_weaken_verified_graph_profile(self):
        a = node('A', source='use profile=legacy.\nlet answer = 2.')
        state = R.GraphRun(graph(a), self.folder, FakeApps()).execute()
        self.assertEqual(ep(state['states'][0])['execution_profile'], 'verified')


if __name__ == '__main__':
    unittest.main()
