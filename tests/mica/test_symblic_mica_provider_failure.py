"""Provider uncertainty must retain failure evidence, not invent weight drift."""
import json
from pathlib import Path
import tempfile
import unittest

from symblic.providers import ollama_call as B
from symblic.mica import search as M
from symblic.mica import native as N
from symblic.kernel.run import Store
from tests.mica.test_symblic_mica_execution import FakeApps, ROUTE


class ProviderFailure(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-provider-failure-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.route = {**ROUTE, 'digest': 'a' * 64}

    def reply(self, identity=None, ok=False):
        result = {'ok': ok, 'error': 'transient: ollama request failed (curl exit 28): the generate request ran out of time',
                  'model': self.route['model'], 'node': self.route['node'], 'ms': 300000}
        if identity is not None:
            result['model_identity'] = identity
        return result

    def observed(self, digest='a'):
        side = {'at_ms': 1, 'name': self.route['model'], 'digest': 'sha256:' + digest * 64, 'error': None}
        return B.identity({'version': 1, 'model': self.route['model'], 'nonce': '1' * 32,
                           'before': side, 'after': {**side, 'at_ms': 2}, 'response_model': self.route['model']},
                          self.route['model'], self.route['node'], '2' * 64, '1' * 32)

    def call(self, reply, folder='evidence'):
        apps = FakeApps(lambda req, n: reply)
        evidence = N._ProviderEvidence(Store(str(self.root / folder)), apps, self.route)
        result = evidence.call({'key': 'fixture-key', 'app': self.route, 'prompt': 'fixture'})
        self.assertEqual(evidence.records()[0]['observed']['model_identity'], reply['model_identity'])
        return result

    def test_native_failed_delivery_with_unknown_node_preserves_timeout_and_replays(self):
        reply = self.reply(B.unavailable('ollama', self.route['model'], 'call_failed'))
        apps = FakeApps(lambda req, n: reply)
        source = N.planner_source('Return one JSON fixture.', self.route)
        first = N.execute(source, self.root / 'native', apps, self.route, limit=1, output_binding='proposal')
        self.assertEqual(M.failure_class(first), 'MODEL_TIMEOUT', first)
        self.assertNotIn('identity conflicts', json.dumps(first['error']))
        self.assertEqual(first['provider_evidence'][0]['observed']['model_identity'], reply['model_identity'])
        self.assertEqual(N.execute(source, self.root / 'native', apps, self.route, limit=1,
                                  output_binding='proposal'), first)
        self.assertEqual(len(apps.requests), 1)

    def test_success_still_requires_observed_pin(self):
        result = self.call(self.reply(B.unavailable('ollama', self.route['model'], 'call_failed'), ok=True))
        self.assertFalse(result['ok'])
        self.assertTrue(result['fatal'])

    def test_failed_delivery_with_affirmative_wrong_node_is_conflict(self):
        result = self.call(self.reply(B.unavailable('ollama', self.route['model'], 'call_failed', 'other-node')))
        self.assertTrue(result['fatal'])

    def test_failed_delivery_with_malformed_identity_is_conflict(self):
        result = self.call(self.reply({'status': 'unavailable'}))
        self.assertTrue(result['fatal'])

    def test_failed_delivery_with_observed_wrong_digest_is_conflict(self):
        result = self.call(self.reply(self.observed('b')))
        self.assertTrue(result['fatal'])

    def test_failed_delivery_with_exact_observation_retains_failure(self):
        reply = self.reply(self.observed())
        self.assertEqual(self.call(reply), reply)


if __name__ == '__main__':
    unittest.main()
