"""Graph page→API→durable Run integration, fake Apps/launcher and private temp stores."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integration.host import symblic_engine as E
from integration.host import symblic_graph_api as A
from symblic.graph import planner as G


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class Handler:
    def __init__(self, ident='', owner=True):
        self.ident, self.owner = ident, owner
    def identity(self):
        class Identity:
            is_owner = self.owner
        return Identity()
    def get_query_param(self, _key):
        return self.ident
    def send_json(self, value, status=200):
        self.value, self.status = value, status


class Apps:
    def __init__(self):
        self.calls = []
    def call(self, request):
        self.calls.append(request)
        return {'ok': True, 'json': {'answer': 6}, 'node': request['app']['node'],
                'model': request['app']['model'], 'ms': 0}


class GraphAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.apps = Apps()
        self.launches = []
        def launch(ident, folder, generation):
            self.launches.append(ident)
            A.run_job(folder, applicators=self.apps, generation=generation)
            return {'ok': True}
        self.mock_launch = patch.dict(A.launcher, {'launch': launch, 'active': lambda _: False, 'stop': lambda _: True})
        self.mock_launch.start()
        self.addCleanup(self.mock_launch.stop)
        self.body = {k:v for k,v in A.example().items() if k in ('graph','policy')}
    def api(self, method, route, body=None, ident='', owner=True):
        h = Handler(ident, owner)
        self.assertTrue(E.handle(h, method, route, body or {}))
        return h
    def test_check_owner_gate_and_no_store_or_calls(self):
        with patch.object(A, '_root', side_effect=AssertionError('check touched a store')):
            self.assertEqual(self.api('POST', 'graph/check', self.body).status, 200)
            self.assertEqual(self.api('POST', 'graph/run', self.body, owner=False).status, 403)
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])
    def test_exact_review_pins_reject_before_creation(self):
        check = self.api('POST', 'graph/check', self.body).value
        body = {**self.body, 'expected_graph_hash': check['graph_hash'], 'expected_policy_hash': check['policy_hash']}
        body['graph']['nodes'][0]['checks'] = ['answer = 7']
        denied = self.api('POST', 'graph/run', body)
        self.assertEqual(denied.status, 409)
        self.assertEqual(self.launches, [])
        self.assertFalse(list(Path(self.temp.name).rglob('frozen.json')))
    def test_two_nodes_execute_and_terminal_resume_is_zero_dispatch(self):
        check = self.api('POST', 'graph/check', self.body).value
        answer = self.api('POST', 'graph/run', {**self.body, 'expected_graph_hash': check['graph_hash'],
                                               'expected_policy_hash': check['policy_hash']})
        self.assertEqual(answer.status, 200, answer.value)
        ident = answer.value['id']
        view = self.api('GET', 'graph/run', ident=ident).value
        self.assertEqual(view['state']['status'], 'succeeded', view)
        double = next(n for n in view['state']['nodes'] if n['node'] == 'Double')
        self.assertEqual(double['result']['value'], 12)
        self.assertEqual(double['result']['evidence'][0]['source_truth'], 'contingent')
        self.assertFalse(view['can_resume'])
        self.assertEqual(self.api('GET', 'graph/runs').value['runs'][0]['id'], ident)
        self.assertTrue(self.api('POST', 'graph/resume', {'id': ident}).value['terminal'])
        self.assertEqual(self.launches, [ident])
        self.assertEqual(self.apps.calls, [])
        for path in Path(self.temp.name).rglob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o077, 0)
    def test_registered_model_call_composes_with_next_node_and_keeps_receipt(self):
        self.body['graph']['nodes'][0]['source'] = 'use profile=verified.\nask answer: Int "Return six." with retries=0.'
        ident = A.start(self.body)['id']
        self.assertEqual(len(self.apps.calls), 1)
        view = A.view(ident)
        self.assertEqual(view['state']['status'], 'succeeded', view)
        self.assertEqual(self.apps.calls[0]['app']['engine'], 'ollama')
        self.assertEqual(self.apps.calls[0]['app']['node'], 'node-a')
        outcome = next(n for n in view['state']['nodes'] if n['node'] == 'Measure')['result']
        self.assertEqual(outcome['independence'], 'not_established')
        self.assertEqual(outcome['provenance'][0]['issued_calls'], 1)
        A.run_job(A._folder(ident), applicators=self.apps)
        self.assertEqual(len(self.apps.calls), 1)
    def test_launch_failure_visible_and_resume_reuses_frozen_job(self):
        with patch.dict(A.launcher, {'launch': lambda *_: {'ok': False, 'error': 'fixture refused placement'}}):
            with self.assertRaises(A.ApiError):
                A.start(self.body)
        row = A.list_runs()[0]
        self.assertEqual(row['status'], 'failed')
        self.assertIn('placement', row['error'])
        self.assertTrue(A.view(row['id'])['can_resume'])
        A.resume(row['id'])
        self.assertEqual(A.view(row['id'])['state']['status'], 'succeeded')
    def test_nonexistent_and_tampered_files_are_visible(self):
        self.assertEqual(self.api('GET', 'graph/run', ident='../private').status, 404)
        ident = A.start(self.body)['id']
        path = A._folder(ident) / 'runtime' / 'graph-events.jsonl'
        with path.open('ab') as handle:
            handle.write(b'{')
        view = A.view(ident)
        self.assertEqual(view['state']['status'], 'unavailable')
        self.assertIn('partial', view['error'])
        self.assertFalse(view['can_resume'])
    def test_unsupported_routes_effects_and_schema_refuse_before_launch(self):
        bad = []
        b = copy.deepcopy(self.body); b['graph']['nodes'][0]['effect_risk'] = 'write'; bad.append(b)
        b = copy.deepcopy(self.body); b['policy']['routes'][0]['local'] = False; bad.append(b)
        b = copy.deepcopy(self.body); b['graph']['nodes'][0]['output_schema']['pattern'] = '.'; bad.append(b)
        for body in bad:
            with self.subTest(body=body), self.assertRaises((A.ApiError, G.GraphError)):
                A.start(body)
        self.assertEqual(self.launches, [])


if __name__ == '__main__':
    unittest.main()
