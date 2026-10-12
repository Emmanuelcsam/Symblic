"""Existing native MICA/benchmark journeys; fake providers and isolated stores.

Run only in a coherent source snapshot on a machine that can run the JavaScript sandbox.
The check-pack is frozen before any provider dispatch. No real model is called.
"""
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.mica import search as M
from symblic.mica import bench as B
from symblic.mica import checkpack as K
from symblic.mica import cli as CLI
from tests.mica.test_symblic_mica_checkpack import request, declaration, SENTINEL
from tests.mica.test_symblic_mica_execution import FakeApps, inventory


class CheckPackNativeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mica-checkpack-native-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inv = inventory(('node-e',))
        self.checker = B.js_evaluator_identity()
        self.pack = K.freeze(request(), declaration(), self.checker)

    def test_actual_parent_cli_freeze_public_fixture_validate_is_inert(self):
        for name, value in [('request', request()), ('declaration', declaration())]:
            (self.root/(name+'.json')).write_text(json.dumps(value))
        def command(args):
            stream = io.StringIO()
            code = CLI.main(['checkpack', *args], out=stream)
            result = json.loads(stream.getvalue())
            self.assertEqual(code, 0, result)
            return result
        with mock.patch.object(M.MicaRun, 'execute', side_effect=AssertionError('no construction from data CLI')), \
             mock.patch.object(CLI, '_applications', side_effect=AssertionError('no providers from data CLI')):
            pack = command(['freeze', str(self.root/'request.json'), '--declaration', str(self.root/'declaration.json')])
            (self.root/'pack.json').write_text(json.dumps(pack))
            suffix = [str(self.root/'pack.json'), '--freeze', pack['sha256']]
            public = command(['public', *suffix])
            fixture = command(['fixture', *suffix])
            receipt = command(['validate', *suffix])
        self.assertEqual(public['tests'][:1], request()['tests'])
        self.assertNotIn(SENTINEL, json.dumps(public))
        self.assertIn(SENTINEL, json.dumps(fixture['hidden_tests']))
        self.assertTrue(receipt['valid'])
        self.assertEqual(receipt['sha256'], pack['sha256'])

    def test_proto_roundtrip_native_acceptance_exact_replay_and_no_hidden_context(self):
        apps = FakeApps(lambda req, n: 'function encode(value){return value;} function decode(value){return value;}')
        public = K.public_request(self.pack, expected_sha256=self.pack['sha256'])
        first = M.MicaRun(public, self.root/'build', apps, self.inv).execute(mode='direct')
        self.assertEqual(first['status'], 'done', first)
        self.assertEqual(first['calls'], 1)
        M.verify_result_artifacts(first, public, M.implementation_identity())
        repeated = M.MicaRun(public, self.root/'build', apps, self.inv).execute(mode='direct')
        self.assertEqual(first, repeated)
        self.assertEqual(len(apps.requests), 1)
        self.assertNotIn(SENTINEL, json.dumps(apps.requests))
        self.assertNotIn('model-proposed-only-sentinel', json.dumps(apps.requests))

    def test_generated_public_check_rejects_candidate_passing_only_original_example(self):
        apps = FakeApps(lambda req, n: 'function encode(value){return value;} function decode(value){return value===7?7:0;}')
        result = M.MicaRun(K.public_request(self.pack), self.root/'bad', apps, self.inv).execute(mode='direct')
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertNotIn(SENTINEL, json.dumps(apps.requests))

    def test_hidden_sentinel_only_reaches_existing_evaluator_and_never_repair(self):
        apps = FakeApps(lambda req, n: 'function encode(value){return value;} function decode(value){return typeof value==="string" && value.startsWith("hidden") ? 0 : value;}')
        fixture = K.fixture(self.pack, expected_sha256=self.pack['sha256'])
        model = {'primary': ['fixture-small'], 'fallback': [], 'stronger_fallback': [], 'settings': {'temperature': 0}}
        bench = B.MicaBenchmark.freeze(self.root/'bench', 'checkpack', [fixture], model=model,
                                      budget=fixture['request']['budget'], evaluator_identity=self.checker)
        assignment = next(row for row in bench.assignments() if row['arm_id'] == 'direct')
        received = []
        def runner(**kwargs):
            received.append(kwargs)
            return M.MicaRun(kwargs['request'], self.root/'hidden-build', apps, self.inv).execute(mode=kwargs['mode'])
        result = bench.run_assignment(assignment['id'], runner)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['grade']['status'], 'failed', result)
        self.assertFalse(result['grade']['passed'])
        self.assertNotIn(SENTINEL, json.dumps(received))
        self.assertNotIn(SENTINEL, json.dumps(apps.requests))
        replay = bench.run_assignment(assignment['id'], runner)
        self.assertEqual(replay, result)
        self.assertEqual(len(received), 1)
        self.assertEqual(len(apps.requests), 1)


if __name__ == '__main__':
    unittest.main()
