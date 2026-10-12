"""Launch-generation, stale receipt and malformed-request adversaries; no real workers/providers."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integration.host import symblic_engine as Engine
from integration.host import symblic_graph_api as Graph
from symblic.graph import run as Runtime
from symblic.js import check as JS
from integration.host import symblic_policy_api as Policy
from tests.integration.test_symblic_policy_api import Handler


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class NoCalls:
    def call(self, _request):
        raise AssertionError('a stopped or read-only path dispatched a model')


class ApiAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': self.temp.name})
        env.start(); self.addCleanup(env.stop)
        node = patch.object(JS, 'node_version', return_value='test-no-node')
        node.start(); self.addCleanup(node.stop)
        self.pending = []
        self.hooks = []
        for api in (Graph, Policy):
            hooks = patch.dict(api.launcher, {'launch': self.defer, 'active': lambda _: False, 'stop': lambda _: True})
            hooks.start(); self.addCleanup(hooks.stop)
    def defer(self, ident, folder, generation):
        self.pending.append((ident, folder, generation))
        return {'ok': True}
    def body(self, api):
        body = api.example()
        return body if api is Policy else {key:body[key] for key in ('graph', 'policy')}
    def api(self, method, route, body=None, ident=''):
        h = Handler(ident)
        self.assertTrue(Engine.handle(h, method, route, {} if body is None else body))
        return h
    def test_pending_resume_and_duplicate_worker_are_idempotent(self):
        for api in (Graph, Policy):
            with self.subTest(api=api.__name__):
                ident = api.start(self.body(api))['id']
                count = len(self.pending)
                self.assertTrue(api.resume(ident)['already_starting'])
                self.assertTrue(api.resume(ident)['already_starting'])
                self.assertEqual(len(self.pending), count)
                _, folder, generation = self.pending[-1]
                # A pending worker can be canceled before any engine construction.
                api.stop(ident)
                self.assertEqual(api.run_job(folder, applicators=NoCalls(), generation=generation)['status'], 'not_started')
                self.assertEqual(api.run_job(folder, applicators=NoCalls(), generation=generation)['status'], 'not_started')
    def test_superseded_generation_cannot_start_or_overwrite_new_job(self):
        for api in (Graph, Policy):
            with self.subTest(api=api.__name__):
                ident = api.start(self.body(api))['id']
                _, folder, old = self.pending[-1]
                api.stop(ident)
                api.resume(ident)
                _, _, current = self.pending[-1]
                self.assertNotEqual(old, current)
                self.assertEqual(api.run_job(folder, applicators=NoCalls(), generation=old)['status'], 'not_started')
                before = Runtime._read(Path(folder)/'job.json')
                Graph.finish_job(folder, old, 'succeeded')
                self.assertEqual(Runtime._read(Path(folder)/'job.json'), before)
    def test_stop_failure_retains_cancellation_and_late_worker_refusal(self):
        for api in (Graph, Policy):
            with self.subTest(api=api.__name__):
                ident = api.start(self.body(api))['id']
                _, folder, generation = self.pending[-1]
                with patch.dict(api.launcher, {'active': lambda _:True, 'stop':lambda _:False}):
                    with self.assertRaises(Graph.ApiError):api.stop(ident)
                self.assertTrue(Runtime._read(Path(folder)/'job.json')['cancel_requested'])
                self.assertEqual(api.run_job(folder, applicators=NoCalls(), generation=generation)['status'], 'not_started')
    def test_policy_preflight_refuses_unsupported_concrete_route(self):
        body = Policy.example()
        body['candidates'][0]['routes'][0].update(provider='council', local=False)
        for stage in ('training', 'heldout'):
            for row in body[stage]:
                for node in row['input']['graph']['nodes']:
                    node['allowed'].update(providers=['council'], local_only=False)
        self.assertEqual(self.api('POST', 'policy/check', body).status, 400)
        self.assertEqual(self.pending, [])
    def test_malformed_control_payloads_are_client_errors(self):
        for prefix in ('graph', 'policy'):
            for control in ('stop', 'resume'):
                for body in ([], 'unexpected', 0):
                    with self.subTest(prefix=prefix, control=control, body=body):
                        self.assertEqual(self.api('POST', prefix+'/'+control, body).status, 400)
    def test_malformed_policy_metadata_is_visible_failure(self):
        ident = Policy.start(self.body(Policy))['id']
        path = Policy._folder(ident)/'meta.json'
        Graph._save(path.parent, path.name, {'id':ident})
        response = self.api('GET', 'policy/run', ident=ident)
        self.assertIn(response.status, (400,409))
        self.assertEqual(len(self.pending), 1)
    def test_malformed_job_records_fail_visibly_without_control_mutation(self):
        for api, prefix in ((Graph, 'graph'), (Policy, 'policy')):
            ident = api.start(self.body(api))['id']
            path = api._folder(ident)/'job.json'
            original = json.loads(path.read_text())
            malformed = ([1], {**original, 'updated': 'bad'}, {**original, 'generation': '../other'},
                         {**original, 'status': 'invented'}, {**original, 'cancel_requested': 'yes'},
                         {**original, 'status': 'stopping', 'cancel_requested': False})
            launches = len(self.pending)
            for value in malformed:
                with self.subTest(api=api.__name__, value=value):
                    Graph._save(path.parent, path.name, value)
                    before = path.read_bytes()
                    self.assertEqual(self.api('GET', prefix+'/run', ident=ident).status, 409)
                    listed = self.api('GET', prefix+'/runs')
                    self.assertEqual(listed.status, 200)
                    row = next(row for row in listed.value['runs'] if row['id'] == ident)
                    self.assertEqual(row['status'], 'unavailable')
                    for action in ('resume', 'stop'):
                        self.assertEqual(self.api('POST', prefix+'/'+action, {'id': ident}).status, 409)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(len(self.pending), launches)
            Graph._save(path.parent, path.name, original)
    def test_graph_metadata_is_bound_to_folder_and_frozen_hashes(self):
        ident = Graph.start(self.body(Graph))['id']
        path = Graph._folder(ident)/'meta.json'
        original = json.loads(path.read_text())
        for value in ([], {**original, 'id': 'f'*12}, {**original, 'graph_hash': '0'*64},
                      {**original, 'policy_hash': '0'*64}):
            with self.subTest(value=value):
                Graph._save(path.parent, path.name, value)
                self.assertEqual(self.api('GET', 'graph/run', ident=ident).status, 409)
                self.assertEqual(self.api('POST', 'graph/resume', {'id': ident}).status, 409)
                listed = self.api('GET', 'graph/runs')
                self.assertEqual(listed.status, 200)
                self.assertEqual([row['id'] for row in listed.value['runs']], [ident])
                self.assertEqual(listed.value['runs'][0]['status'], 'unavailable')
                self.assertEqual(len(self.pending), 1)
        Graph._save(path.parent, path.name, original)
    def test_inactive_interrupted_stop_can_resume_without_reviving_old_generation(self):
        for api in (Graph, Policy):
            with self.subTest(api=api.__name__):
                ident = api.start(self.body(api))['id']
                _, folder, old = self.pending[-1]
                with patch.dict(api.launcher, {'active': lambda _: True, 'stop': lambda _: False}):
                    with self.assertRaises(Graph.ApiError):
                        api.stop(ident)
                marker = Path(folder)/('.cancel-'+old)
                cancellation = marker.read_bytes()
                self.assertEqual(Graph.read_job(folder)['status'], 'stopping')
                self.assertTrue(api.view(ident)['can_resume'])
                api.resume(ident)
                _, _, current = self.pending[-1]
                self.assertNotEqual(current, old)
                self.assertEqual(marker.read_bytes(), cancellation)
                before = Graph.read_job(folder)
                self.assertEqual(api.run_job(folder, applicators=NoCalls(), generation=old)['status'], 'not_started')
                self.assertEqual(Graph.read_job(folder), before)
    def test_policy_host_identity_drift_refuses_selection_before_any_dispatch(self):
        ident = Policy.start(self.body(Policy))['id']
        changed = copy.deepcopy(Policy.runtime_identity())
        changed['kernel'] = 'changed-runtime'
        with patch.object(Policy, 'runtime_identity', return_value=changed):
            selected = self.api('GET', 'policy/selected', ident=ident)
            self.assertIn(selected.status, (400, 409))
            self.assertIn('host', selected.value['error'].lower())
            self.assertEqual(Policy.view(ident)['status'], 'unavailable')
            self.assertIn(self.api('POST', 'policy/resume', {'id': ident}).status, (400, 409))
        self.assertEqual(len(self.pending), 1)
    def test_completed_graph_drift_cannot_keep_current_success_assurance(self):
        ident = Graph.start(self.body(Graph))['id']
        _, folder, generation = self.pending[-1]
        self.assertEqual(Graph.run_job(folder, applicators=NoCalls(), generation=generation)['status'], 'succeeded')
        pin = Path(folder)/'runtime'/'graph-pins.json'
        original = pin.read_bytes()
        value = json.loads(original); value['files']['symblic.py'] = '0'*64
        Graph._save(pin.parent, pin.name, Runtime._seal({key:v for key,v in value.items() if key!='sha256'}))
        view = Graph.view(ident)
        self.assertEqual(view['state']['status'], 'unavailable', view.get('error'))
        self.assertFalse(view['can_resume'])
        pin.write_bytes(original)
        self.assertEqual(Graph.view(ident)['state']['status'], 'succeeded')


if __name__ == '__main__':
    unittest.main()
