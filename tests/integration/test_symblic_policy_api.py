"""Owner API through actual graph-policy execution; private temp stores, fake Apps/launchers."""
import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from integration.host import symblic_engine as Engine

from integration.host import symblic_graph_api as GraphAPI
from symblic.graph import run as GraphRun
from symblic.js import check as JS
from integration.host import symblic_policy_api as API
from symblic.policy import learning as Policy
from symblic.policy import store as Store


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class Handler:
    def __init__(self, ident='', owner=True, query=None):
        self.ident, self.owner, self.query = ident, owner, query or {}
    def identity(self):
        return type('Identity', (), {'is_owner': self.owner})()
    def get_query_param(self, key):
        if key in self.query:
            return self.query[key]
        return self.ident
    def send_json(self, value, status=200):
        self.value, self.status = value, status


class Apps:
    def __init__(self):
        self.calls = []
    def call(self, request):
        self.calls.append(request)
        answer = 0
        if request['app']['model'] == 'large':
            answer = 9 if 'Read nine' in request['prompt'] else 6
        return {'ok': True, 'json': {'answer': answer}, 'model': request['app']['model'],
                'node': request['app']['node'], 'ms': 0}


def fixture():
    body = API.example()
    policies = []
    for model in ('small', 'large'):
        candidate = copy.deepcopy(body['candidates'][0])
        candidate['routes'][0]['model'] = model
        policies.append(candidate)
    body['candidates'] = policies
    for stage, wording in [('training', 'Read six'), ('heldout', 'Read nine')]:
        graph = body[stage][0]['input']['graph']
        for node in graph['nodes']:
            node['allowed']['models'] = ['small', 'large']
        graph['nodes'][0]['source'] = ('use profile=verified.\nask answer: Int "' + wording +
                                      '." with effort=low, retries=0, budget=20000.')
        graph['nodes'][0]['checks'] = ['answer >= 0']
    return body


class PolicyAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': self.temp.name})
        env.start(); self.addCleanup(env.stop)
        node = patch.object(JS, 'node_version', return_value='test-no-node')
        node.start(); self.addCleanup(node.stop)
        self.apps, self.launches = Apps(), []
        def launch(ident, folder, generation):
            self.launches.append(ident)
            API.run_job(folder, applicators=self.apps, generation=generation)
            return {'ok': True}
        launcher = patch.dict(API.launcher, {'launch': launch, 'active': lambda _: False, 'stop': lambda _: True})
        launcher.start(); self.addCleanup(launcher.stop)
        self.body = fixture()
    def api(self, method, route, body=None, ident='', owner=True, query=None):
        handler = Handler(ident, owner, query)
        self.assertTrue(Engine.handle(handler, method, route, {} if body is None else body))
        return handler
    def test_owner_gate_every_route_without_store_or_dispatch(self):
        with patch.object(API, '_root', side_effect=AssertionError('unauthorized store')):
            for method, route in [('GET', 'policy/example'), ('GET', 'policy/runs'), ('GET', 'policy/run'),
                                  ('GET', 'policy/selected'), ('POST', 'policy/check'), ('POST', 'policy/run'),
                                  ('POST', 'policy/resume'), ('POST', 'policy/stop')]:
                self.assertEqual(self.api(method, route, self.body, owner=False).status, 403)
        self.assertEqual(self.launches, []); self.assertEqual(self.apps.calls, [])
    def test_check_and_example_are_pure(self):
        result = self.api('POST', 'policy/check', self.body)
        self.assertEqual(result.status, 200, result.value)
        self.assertEqual(result.value['max_provider_calls'], 8)
        self.assertEqual(self.api('GET', 'policy/example').status, 200)
        self.assertFalse(list(Path(self.temp.name).rglob('*.json')))
        self.assertEqual(self.apps.calls, []); self.assertEqual(self.launches, [])
    def test_review_hash_and_split_overlap_refuse_before_creation(self):
        reviewed = API.check(self.body)['plan_hash']
        changed = copy.deepcopy(self.body)
        changed['training'][0]['input']['graph']['nodes'][0]['source'] += '\nnote Changed input.'
        changed['expected_plan_hash'] = reviewed
        self.assertEqual(self.api('POST', 'policy/run', changed).status, 409)
        overlap = copy.deepcopy(self.body); overlap['heldout'][0]['family'] = overlap['training'][0]['family']
        self.assertEqual(self.api('POST', 'policy/run', overlap).status, 400)
        self.assertEqual(self.launches, [])
        self.assertFalse(list(Path(self.temp.name).rglob('frozen.json')))
    def test_full_graph_selection_heldout_accounting_and_terminal_resume(self):
        checked = API.check(self.body)
        response = self.api('POST', 'policy/run', {**self.body, 'expected_plan_hash': checked['plan_hash']})
        self.assertEqual(response.status, 200, response.value)
        ident = response.value['id']
        result = self.api('GET', 'policy/run', ident=ident)
        self.assertEqual(result.status, 200, result.value)
        self.assertEqual(result.value['status'], 'done')
        self.assertEqual(result.value['state']['stage'], 'evaluated')
        selected = API.selected(ident)
        self.assertEqual(selected['policy_hash'], Policy.digest(self.body['candidates'][1]))
        self.assertTrue(result.value['state']['evaluation']['improvement'])
        self.assertEqual(len(self.apps.calls), 4)
        requests = [json.loads(path.read_text()) for path in API._folder(ident).glob('assignment-*/intent.json')]
        self.assertEqual(len(requests), 4)
        self.assertTrue(all('expected' not in request for request in requests))
        self.assertTrue(all('heldout' not in json.dumps(request['input']) for request in requests if request['stage'] == 'training'))
        for path in API._folder(ident).glob('assignment-*/result.json'):
            result = json.loads(path.read_text())
            self.assertEqual(sum(a['calls'] for a in result['record']['attempts']), 1)
            self.assertEqual(sum(a['cost_units'] for a in result['record']['attempts']), 1)
        self.assertTrue(API.resume(ident)['terminal'])
        API.run_job(API._folder(ident), applicators=self.apps)
        self.assertEqual(len(self.apps.calls), 4)
        self.assertEqual(self.launches, [ident])
        self.assertEqual(API.selected(ident), selected)
        for path in Path(self.temp.name).rglob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o077, 0, str(path))
    def test_selection_is_training_only_and_not_a_heldout_data_channel(self):
        ident = API.start(self.body)['id']
        original = Store._read
        def read(path):
            if Path(path).name.startswith('heldout-'):
                raise AssertionError('selector read heldout fixture')
            return original(path)
        with patch.object(Store, '_read', side_effect=read):
            selected = API.selected(ident)
        raw = json.dumps(selected)
        self.assertNotIn('Read nine', raw)
        self.assertNotIn('expected', raw)
        # A completed selection cannot retain current assurance after its host changes.
        changed = copy.deepcopy(API.runtime_identity())
        changed['kernel'] = 'changed-runtime'
        calls = len(self.apps.calls)
        with patch.object(API, 'runtime_identity', return_value=changed):
            response = self.api('GET', 'policy/selected', ident=ident)
            self.assertIn(response.status, (400, 409))
            self.assertEqual(API.view(ident)['status'], 'unavailable')
        self.assertEqual(len(self.apps.calls), calls)
        self.assertEqual(API.selected(ident), selected)
    def test_frozen_source_change_invalidates_selected_receipt(self):
        ident = API.start(self.body)['id']
        path = API._folder(ident) / 'training-cases.json'
        original = path.read_bytes()
        body = json.loads(original)
        body[0]['input']['graph']['nodes'][0]['source'] += '\nnote Drift.'
        path.write_text(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False))
        self.assertEqual(self.api('GET', 'policy/selected', ident=ident).status, 400)
        self.assertEqual(API.view(ident)['status'], 'unavailable')
        path.write_bytes(original)
        self.assertEqual(API.selected(ident)['policy_hash'], Policy.digest(self.body['candidates'][1]))
        # Policy records alone are insufficient when the underlying graph receipt drifts.
        request_path = next(path for path in API._folder(ident).glob('assignment-*/intent.json')
                            if json.loads(path.read_text())['stage'] == 'training')
        request = json.loads(request_path.read_text())
        native = API._folder(ident) / 'graph-runtime' / request['assignment_id'] / 'runtime' / 'graph-pins.json'
        pinned = native.read_bytes()
        value = json.loads(pinned); value['files']['symblic.py'] = '0' * 64
        GraphAPI._save(native.parent, native.name, GraphRun._seal({k:v for k,v in value.items() if k != 'sha256'}))
        self.assertIn(self.api('GET', 'policy/selected', ident=ident).status, (400,409))
        self.assertEqual(API.view(ident)['status'], 'unavailable')
        native.write_bytes(pinned)
        self.assertEqual(API.selected(ident)['policy_hash'], Policy.digest(self.body['candidates'][1]))
        meta = API._folder(ident) / 'meta.json'
        row = json.loads(meta.read_text()); row['freeze_sha256'] = '0' * 64; meta.write_text(json.dumps(row))
        self.assertEqual(self.api('GET', 'policy/selected', ident=ident).status, 400)
        self.assertEqual(len(self.apps.calls), 4)
    def test_launch_failure_visible_and_resume_preserves_freeze(self):
        with patch.dict(API.launcher, {'launch': lambda *_: {'ok': False, 'error': 'fixture capacity refusal'}}):
            response = self.api('POST', 'policy/run', self.body)
        self.assertEqual(response.status, 503)
        row = API.list_runs()[0]
        frozen = API._folder(row['id']) / 'frozen.json'; before = frozen.read_bytes()
        self.assertEqual(row['status'], 'failed')
        API.resume(row['id'])
        self.assertEqual(frozen.read_bytes(), before)
        self.assertEqual(API.view(row['id'])['status'], 'done')
    def test_paths_and_symlinks_refuse_without_dispatch(self):
        self.assertEqual(self.api('GET', 'policy/run', ident='../private').status, 404)
        target = Path(self.temp.name) / 'unrelated'; target.mkdir()
        link = API._root() / 'abcdef123456'; link.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.api('GET', 'policy/run', ident=link.name).status, 404)
        self.assertEqual(self.launches, [])

    def test_pre_compilation_admission_limits_and_candidate_uniqueness(self):
        dup_body = copy.deepcopy(self.body)
        dup_body['candidates'] = [self.body['candidates'][0], self.body['candidates'][0]]
        with patch('symblic.policy.graph.validate_case', side_effect=AssertionError('compilation called')):
            resp = self.api('POST', 'policy/run', dup_body)
            self.assertEqual(resp.status, 400)
            self.assertIn('Candidate policies must be unique', resp.value['error'])

        big_body = copy.deepcopy(self.body)
        candidates = []
        for i in range(20):
            c = copy.deepcopy(self.body['candidates'][0])
            c['routes'][0]['rule'] = f'answer == {i}'
            candidates.append(c)
        big_body['candidates'] = candidates
        big_body['training'] = [self.body['training'][0]] * 60
        with patch('symblic.policy.graph.validate_case', side_effect=AssertionError('compilation called')):
            resp = self.api('POST', 'policy/run', big_body)
            self.assertEqual(resp.status, 400)
            self.assertIn('The training cases and candidate count exceed MAX_ASSIGNMENTS', resp.value['error'])

    def test_heldout_reuse_flagged_and_requires_acknowledgement(self):
        res1 = self.api('POST', 'policy/run', self.body)
        self.assertEqual(res1.status, 200)
        ident1 = res1.value['id']

        checked = API.check(self.body)
        self.assertIn(ident1, checked['prior_heldout_uses'])

        res2 = self.api('POST', 'policy/run', self.body)
        self.assertEqual(res2.status, 400)
        self.assertIn('Held-out evaluation set reuses cases from 1 prior experiment', res2.value['error'])

        res3 = self.api('POST', 'policy/run', {**self.body, 'acknowledge_heldout_reuse': True})
        self.assertEqual(res3.status, 200)
        ident3 = res3.value['id']
        view3 = API.view(ident3, audit=False)
        self.assertIn(ident1, view3['meta']['prior_heldout_uses'])

    def test_acknowledge_heldout_reuse_must_be_boolean(self):
        for invalid in ('true', 1, 0, [True], {'ack': True}):
            res = self.api('POST', 'policy/run', {**self.body, 'acknowledge_heldout_reuse': invalid})
            self.assertEqual(res.status, 400)
            self.assertIn('acknowledge_heldout_reuse must be a boolean', res.value['error'])

    def test_heldout_registry_crash_reconciles_frozen_folders_durably(self):
        res1 = self.api('POST', 'policy/run', self.body)
        self.assertEqual(res1.status, 200)
        ident1 = res1.value['id']

        # Simulate crash before registry write by deleting .heldout_registry.json
        reg_path = API._root() / '.heldout_registry.json'
        if reg_path.is_file():
            reg_path.unlink()

        # check() scans frozen folders under root, reconciles ident1, and rewrites .heldout_registry.json
        checked = API.check(self.body)
        self.assertIn(ident1, checked['prior_heldout_uses'])
        self.assertTrue(reg_path.is_file())
        reconciled_data = json.loads(reg_path.read_text())
        self.assertTrue(any(e.get('experiment') == ident1 for e in reconciled_data))

    def test_heldout_registry_corruption_fails_visibly(self):
        reg_path = API._root() / '.heldout_registry.json'
        reg_path.write_text('not-valid-json{{{')
        resp = self.api('POST', 'policy/run', self.body)
        self.assertEqual(resp.status, 500)
        self.assertIn('Heldout registry is corrupt', resp.value['error'])

    def test_cheap_polling_and_tampered_result_fails_audit_without_cache(self):
        res = self.api('POST', 'policy/run', self.body)
        self.assertEqual(res.status, 200)
        ident = res.value['id']

        with patch('integration.host.symblic_policy_api.audit_runtime', side_effect=AssertionError('audited during cheap poll')):
            resp_cheap = self.api('GET', 'policy/run', ident=ident, query={'id': ident, 'audit': '0'})
            self.assertEqual(resp_cheap.status, 200)
            self.assertEqual(resp_cheap.value['state']['assurance'], 'recorded')

        with patch('integration.host.symblic_policy_api.audit_runtime', wraps=API.audit_runtime) as spy_audit:
            resp_full = self.api('GET', 'policy/run', ident=ident, query={'id': ident})
            self.assertEqual(resp_full.status, 200)
            self.assertEqual(resp_full.value['state']['assurance'], 'verified')
            self.assertTrue(spy_audit.called)

        # Even after warm audit, differing graph evidence cannot bypass audit because cache was removed
        with patch('symblic.policy.graph.GraphPolicyRunner.resolve') as mock_resolve:
            mock_resolve.return_value = {'status': 'done', 'output': 9999, 'attempts': [], 'checks': [], 'complete': True, 'effects': 'none'}
            exp, _ = API._open(ident)
            with self.assertRaises(GraphAPI.ApiError) as cm:
                API.audit_runtime(exp)
            self.assertIn('Native graph evidence differs', str(cm.exception))

            v_audit = API.view(ident, audit=True)
            self.assertEqual(v_audit['status'], 'unavailable')
            self.assertIn('Native graph evidence differs', v_audit['error'])

    def test_implementation_drift_preserves_runs_list_and_recorded_view(self):
        res = self.api('POST', 'policy/run', self.body)
        self.assertEqual(res.status, 200)
        ident = res.value['id']

        orig_imp = Store._implementation()
        drifted = dict(orig_imp, **{'symblic/policy/learning.py': '0' * 64})
        with patch.object(Store, '_implementation', return_value=drifted):
            runs = API.list_runs()
            run_row = next(r for r in runs if r['id'] == ident)
            self.assertEqual(run_row['status'], 'done')

            v_cheap = API.view(ident, audit=False)
            self.assertEqual(v_cheap['status'], 'done')
            self.assertFalse(v_cheap['state']['implementation_intact'])
            self.assertIn('implementation changed', v_cheap['state']['assurance'])

            v_audit = API.view(ident, audit=True)
            self.assertEqual(v_audit['status'], 'unavailable')
            self.assertIn('implementation_pin', v_audit['error'])

            self.assertEqual(self.api('GET', 'policy/selected', ident=ident).status, 400)

    def test_stop_during_job_preserves_inflight_and_resumes_cleanly(self):
        stopped = threading.Event()
        class StoppingApps:
            def __init__(self):
                self.calls = []
            def call(self, request):
                self.calls.append(request)
                if len(self.calls) == 2:
                    stopped.set()
                return {'ok': True, 'json': {'answer': 6}, 'model': request['app']['model'],
                        'node': request['app']['node'], 'ms': 0}

        stopping_apps = StoppingApps()
        with patch.dict(API.launcher, {'launch': lambda *_: {'ok': True}}):
            res = self.api('POST', 'policy/run', self.body)
        ident = res.value['id']
        folder = API._folder(ident)

        job_result = API.run_job(folder, applicators=stopping_apps, stop_event=stopped)
        self.assertEqual(job_result['stage'], 'training')

        v = API.view(ident, audit=False)
        self.assertEqual(v['status'], 'stopped')
        self.assertTrue(v['can_resume'])
        self.assertFalse((folder / 'selection.json').exists())
        self.assertFalse((folder / 'evaluation.json').exists())

        res_resume = API.resume(ident)
        self.assertTrue(res_resume.get('ok'))
        v2 = API.view(ident, audit=True)
        self.assertEqual(v2['status'], 'done')
        self.assertEqual(v2['state']['stage'], 'evaluated')
        self.assertIsNotNone(v2['state']['selected'])

    def test_unrecoverable_crash_with_uncertain_call_blocks_resume(self):
        class DisconnectingApps:
            def call(self, request):
                raise RuntimeError('network dropped during model dispatch')

        with patch.dict(API.launcher, {'launch': lambda *_: {'ok': True}}):
            res = self.api('POST', 'policy/run', self.body)
        ident = res.value['id']
        folder = API._folder(ident)

        with self.assertRaises(Store.PolicyStoreError):
            API.run_job(folder, applicators=DisconnectingApps())

        v = API.view(ident)
        self.assertFalse(v['can_resume'])
        self.assertIn('unfinished external intent', v['error'])

        resp = self.api('POST', 'policy/resume', {'id': ident})
        self.assertEqual(resp.status, 409)
        self.assertIn('unfinished external intent', resp.value['error'])


if __name__ == '__main__':
    unittest.main()
