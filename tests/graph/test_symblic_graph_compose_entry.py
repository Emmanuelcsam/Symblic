"""The composition command line (python3 -m symblic.graph.compose): read-only, exact, no model calls.

The original host also exposed composition through its HTTP routes; those cases are in
tests/integration/test_symblic_graph_compose_host.py.
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from symblic.graph import planner as G
from symblic.graph import compose as C
from symblic.js import check as JS


class ComposeCommandLine(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.enter(patch.object(JS, 'node_version', return_value='entry-no-node'))
        self.enter(patch('subprocess.Popen', side_effect=AssertionError('no external process')))
        self.body = C.example()

    def enter(self, context):
        result = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return result

    def cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = C.main(list(args))
        return code, json.loads(output.getvalue())

    def test_actual_cli_catalog_example_compose_and_flat_contract(self):
        self.assertEqual(self.cli('catalog', '--agent-json')[1]['scope'], 'authoring_only')
        self.assertEqual(self.cli('example')[1], self.body)
        request = self.folder / 'request.json'
        request.write_text(json.dumps(self.body))
        code, receipt = self.cli('compose', str(request), '--agent-json')
        self.assertEqual(code, 0)
        self.assertTrue(receipt['ok'])
        self.assertEqual(self.cli('compose', str(request), '--flat'), (0, receipt['draft']))
        self.assertEqual({p.name for p in self.folder.iterdir()}, {'request.json'})
        native = C.expand_composition(self.body['composition'], self.body['policy'])
        self.assertEqual(receipt['draft'], {k: native['frozen'][k] for k in ('graph', 'policy')})
        self.assertEqual(receipt['manifest'], native['manifest'])

    def test_cli_refuses_duplicate_nonfinite_oversized_and_malformed_inputs(self):
        request = self.folder / 'request.json'
        for raw in ('{"composition":{},"composition":{},"policy":{}}',
                    '{"composition":NaN,"policy":{}}', '{broken', ' ' * (G.MAX_BYTES + 1)):
            request.write_text(raw)
            code, result = self.cli('compose', str(request), '--agent-json')
            self.assertEqual(code, 1)
            self.assertFalse(result['ok'])
            self.assertEqual(result['error']['kind'], 'graph_composition')
        self.assertEqual({p.name for p in self.folder.iterdir()}, {'request.json'})

    def test_pure_authoring_retains_effect_nodes(self):
        body = json.loads(json.dumps(self.body))
        definition = next(iter(body['composition']['definitions'].values()))
        definition['nodes'][0]['effect_risk'] = 'write'
        for instance in body['composition']['instances']:
            instance['sha256'] = C.definition_digest(body['composition']['definitions'][instance['definition']])
        generic = C.compose(body)
        self.assertTrue(any(row['effect_risk'] == 'write' for row in generic['draft']['graph']['nodes']))


if __name__ == '__main__':
    unittest.main()
