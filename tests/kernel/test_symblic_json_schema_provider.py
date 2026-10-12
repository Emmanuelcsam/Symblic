"""Launcher capability refusals: real native journal, fake provider, no models."""
import copy
from pathlib import Path
import tempfile
import unittest

from symblic.mica import search as M
from symblic.mica import native as N
from tests.kernel.test_symblic_json_schema_native import RawApps, obj
from tests.mica.test_symblic_mica_execution import request, inventory, ROUTE

SCHEMA = {'anyOf': [obj({'x': {'type': 'integer'}}), obj({'message': {'type': 'string'}})]}


def refusal(*, flagged=True):
    return {'ok': False, 'refused': flagged, 'node': ROUTE['node'],
            'error': 'ollama@node-a: unsupported JSON schema keyword anyOf'}


class ProviderRefusals(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='json-provider-refusal-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'attempt'

    def run_source(self, apps, *, schema=SCHEMA):
        source = N.planner_source('Return the document.', ROUTE, schema=schema).replace('retries=0', 'retries=2')
        result = N.execute(source, self.root, apps, ROUTE, limit=3, output_binding='proposal')
        return source, result

    def test_explicit_capability_refusal_never_removes_schema_or_replays(self):
        apps = RawApps(lambda req, number: refusal())
        source, result = self.run_source(apps)
        self.assertEqual((result['status'], result['failure'], result['calls']), ('blocked', 'VERIFICATION_UNKNOWN', 1))
        self.assertEqual(result['native_report']['calls'], 0)  # Refused launch; intent remains retained.
        self.assertIsNone(result['output'])
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(apps.requests[0]['schema'], SCHEMA)
        self.assertIs(result['provider_evidence'][0]['observed']['refused'], True)
        self.assertIs(result['provider_evidence'][0]['observed']['ok'], False)
        before = (self.root / 'graph-calls.jsonl').read_bytes()
        self.assertEqual(N.execute(source, self.root, apps, ROUTE, limit=3, output_binding='proposal'), result)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual((self.root / 'graph-calls.jsonl').read_bytes(), before)

    def test_partial_model_attempt_then_refusal_keeps_exact_cost_denominators(self):
        apps = RawApps(lambda req, number: '{"x":false}' if number == 1 else refusal())
        _, result = self.run_source(apps)
        self.assertEqual((result['status'], result['failure'], result['calls']), ('blocked', 'VERIFICATION_UNKNOWN', 2))
        self.assertEqual(result['native_report']['calls'], 1)
        self.assertEqual(len(apps.requests), 2)
        self.assertTrue(all(row['schema'] == SCHEMA for row in apps.requests))
        observed = [row['observed'] for row in result['provider_evidence']]
        self.assertEqual(sum(row.get('refused') is True and row.get('ok') is False for row in observed), 1)
        self.assertEqual(sum(row.get('ok') is True for row in observed), 1)

    def test_error_text_without_refused_flag_is_not_capability_evidence(self):
        apps = RawApps(lambda req, number: {**refusal(flagged=False), 'fatal': True})
        _, result = self.run_source(apps)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(M.failure_class(result), 'MODEL_OUTPUT_ERROR')
        self.assertEqual((result['calls'], result['native_report']['calls']), (1, 1))
        self.assertIs(result['provider_evidence'][0]['observed']['refused'], False)

    def test_plain_code_keeps_plain_reply_contract_and_visible_provider_refusal(self):
        apps = RawApps(lambda req, number: refusal())
        _, result = self.run_source(apps, schema=None)
        self.assertEqual((result['status'], result['failure']), ('blocked', 'VERIFICATION_UNKNOWN'))
        self.assertIsNone(apps.requests[0]['schema'])
        self.assertEqual(result['native_report']['status'], 'failed')
        self.assertEqual(len(apps.requests), 1)

    def test_mica_refusal_is_ungraded_and_stops_alternative_dispatch(self):
        apps = RawApps(lambda req, number: refusal())
        run = M.MicaRun(request(max_calls=5, max_candidates=3), self.root, apps, inventory())
        result = run.execute(mode='mica')
        self.assertEqual((result['status'], result['failure'], result['calls']), ('blocked', 'VERIFICATION_UNKNOWN', 1))
        self.assertEqual(run.observations, [])
        self.assertEqual(len(apps.requests), 1)
        self.assertIsNotNone(apps.requests[0]['schema'])
        replay = M.MicaRun(request(max_calls=5, max_candidates=3), self.root, apps, inventory()).execute(mode='mica')
        self.assertEqual(replay, result)
        self.assertEqual(len(apps.requests), 1)


if __name__ == '__main__':
    unittest.main()
