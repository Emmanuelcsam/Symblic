"""Long supported graphs retain pinned lineage without recursively copying values."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.graph import planner as G
from symblic.graph import run as R
from symblic.js import check as JS
from tests.graph.test_symblic_graph_run import FakeApps, Host, graph, node


class GraphBounds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / 'graph'
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)

    def test_twenty_node_chain_preserves_root_identity_with_bounded_envelopes(self):
        nodes = []
        for index in range(20):
            reference = {'node': 'N' + str(index - 1)} if index else {'literal': G.envelope(0, 'supported')}
            nodes.append(node('N' + str(index), {'x': reference}, 'given x: Int.\nlet answer = x + 1.',
                              checks=['answer = x + 1'], call_limit=1, max_calls=1))
        apps = FakeApps()
        state = R.GraphRun(graph(*nodes, max_calls=20), self.folder, apps).execute()
        self.assertEqual(state['status'], 'succeeded')
        self.assertEqual(next(row['result']['value'] for row in state['states'] if row['node'] == 'N19'), 20)
        self.assertFalse(apps.calls)
        roots = set()
        sizes = []
        for row in state['states']:
            report = row['result']['evidence'][1]
            roots.add(tuple(item['ref']['sha256'] for item in report['binding_epistemic']['assessment']['conditional_on']))
            self.assertTrue(report['binding_epistemic']['assessment']['lineage_complete'])
            sizes.append(len(R._json(row['result'])))
        self.assertEqual(len(roots), 1)
        self.assertLess(max(sizes), 20000)
        self.assertLess(len(R._json(state)), G.MAX_BYTES)
        self.assertEqual(R.GraphRun(graph(*nodes, max_calls=20), self.folder, apps).execute(), state)
        self.assertFalse(apps.calls)

    def test_thirty_two_feedback_iterations_keep_full_native_claim_closure(self):
        n = node('A', {'previous': {'node': 'A', 'delay': 1, 'seed': G.envelope(0, 'supported')}},
                 'given previous: Int.\nlet answer = previous + 1.', checks=['answer = previous + 1'],
                 call_limit=1, max_calls=32)
        apps = FakeApps()
        state = R.GraphRun(graph(n, iterations=32, max_calls=32), self.folder, apps).execute()
        self.assertEqual(state['status'], 'succeeded')
        self.assertEqual([row['result']['value'] for row in state['states']], list(range(1, 33)))
        final = R._read(self.folder / 'attempts' / 'Iter031_A_Attempt01' / 'graph-result.json')
        claims = final['run_report']['epistemic']['claims']
        self.assertGreaterEqual(len(claims), 64)
        self.assertEqual(final['result']['result']['evidence'][1]['run_report_sha256'], R._hash(final['run_report']))
        self.assertFalse(apps.calls)
        self.assertLess(len(R._json(state)), G.MAX_BYTES)

    def test_private_taint_survives_intermediate_computation_before_cloud_route(self):
        host = Host()
        host.cat['fixture.read']['sensitivity'] = 'confidential'
        a = node('A', source='observe answer: Int = fixture.read().', effect_risk='read')
        b = node('B', {'x': {'node': 'A'}}, 'given x: Int.\nlet answer = x + 1.')
        c = node('C', {'x': {'node': 'B'}})
        c['allowed']['local_only'] = False
        c['allowed']['routes'] = ['Cloud']
        apps = FakeApps()
        state = R.GraphRun(graph(a, b, c), self.folder, apps, effects=host).execute()
        self.assertEqual(next(row['status'] for row in state['states'] if row['node'] == 'C'), 'failed')
        self.assertFalse(apps.calls)
        self.assertEqual(len(host.calls), 1)
        middle = next(row for row in state['states'] if row['node'] == 'B')
        self.assertEqual(middle['result']['provenance'][0]['sensitivity'], 'confidential')


if __name__ == '__main__':
    unittest.main()
