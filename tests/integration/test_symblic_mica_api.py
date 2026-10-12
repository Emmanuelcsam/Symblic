"""Private MICA API journeys; fake launchers/providers, real durable job fences."""
import copy
import base64
import io
import hashlib
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from integration.host import symblic_mica_api as A
from symblic.mica import contracts as C
from tests.mica.test_symblic_mica_cli import script_manifest, calibration, bundle_result, RUNTIME

INVENTORY = [{'engine': 'ollama', 'model': 'fixture-small', 'node': 'node-f',
              'ready': True, 'available': True}]


def request():
    return C.normalize_request({'objective': 'Return input plus one.',
        'requirements': [{'id': 'increment', 'text': 'Return input plus one.', 'acceptance': 'TESTED'}],
        'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
        'tests': [{'requirement_ids': ['increment'], 'call': 'inc(1)', 'expected': '2'}],
        'allowed_outputs': ['result.js'], 'budget': {'max_calls': 4, 'max_candidates': 2}})


def result(status='done'):
    row = {'status': status, 'calls': 1, 'costs': {'wall_seconds': 0.125, 'usd': None},
           'attempts': [], 'evidence': [], 'assurance': 'TESTED'}
    if status == 'done':
        source = 'function inc(x){return x+1}'
        row['output'] = {'file': 'result.js', 'text': source,
                         'sha256': hashlib.sha256(source.encode()).hexdigest(), 'utf8_bytes': len(source.encode())}
        row.update(manifest=script_manifest(source), checks={'passed': True})
    return row


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture(fleet=True)


class Handler:
    def __init__(self, owner=True, **query):
        self.owner, self.query, self.response = owner, query, None

    def identity(self):
        return SimpleNamespace(is_owner=self.owner)

    def get_query_param(self, key):
        return self.query.get(key)

    def send_json(self, body, status=200):
        self.response = (status, body)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mica-api-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.calls, self.launches = [], []
        self.next_status = 'done'
        for patcher in (patch.dict('os.environ', {'AUTOMATION_DATA_DIR': str(self.path/'store')}),
                        patch.object(A, '_host_ok', return_value=True),
                        patch.object(A, '_implementation', return_value={'isolated_fixture': 1, 'construction': RUNTIME}),
                        patch.object(A, 'launcher', {'launch': self.launch, 'active': lambda _: False,
                                                     'stop': lambda _: True})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def body(self, **updates):
        return {'request': request(), 'inventory': copy.deepcopy(INVENTORY), 'mode': 'mica', **updates}

    def factory(self, req, folder, apps, inventory, stop=None, *, library=None):
        outer = self
        class Run:
            def plan(self, mode):
                outer.calls.append(('plan', req, str(folder), inventory, mode, library))
                return result('planned')

            def execute(self, mode):
                outer.calls.append(('execute', req, str(folder), inventory, mode, library))
                return result(outer.next_status)
        return Run()

    def launch(self, ident, folder, generation):
        self.launches.append((ident, folder, generation))
        A.run_job(folder, applicators=object(), generation=generation, runtime_factory=self.factory,
                  project_factory=self.project_factory)
        return {'ok': True}

    def project_factory(self, objective, folder, apps, inventory, budget, outputs, stop=None, *, library=None):
        return self.factory({'objective': objective, 'budget': budget, 'allowed_outputs': outputs},
                            folder, apps, inventory, stop=stop, library=library)

    def invoke(self, route, *, method='GET', body=None, owner=True, **query):
        handler = Handler(owner, **query)
        handled = A.handle(handler, method, route, body)
        self.assertTrue(handled)
        return handler.response

    def test_owner_gate_precedes_all_store_or_discovery_access(self):
        for route, method in [('mica/run', 'POST'), ('mica/check', 'POST'), ('mica/inventory', 'GET')]:
            self.assertEqual(self.invoke(route, method=method, body=self.body(), owner=False)[0], 403)
        self.assertFalse((self.path/'store').exists())
        self.assertFalse(self.calls)

    def test_check_pure_freeze_pin_and_unknown_fields(self):
        checked = A.check(self.body())
        self.assertEqual(checked['eligible_snapshot'], 1)
        self.assertFalse((self.path/'store').exists())
        bad = self.body(expected_sha256='0'*64)
        self.assertEqual(self.invoke('mica/run', method='POST', body=bad)[0], 409)
        self.assertEqual(self.invoke('mica/check', method='POST', body=self.body(folder='/tmp'))[0], 400)
        self.assertFalse(self.calls)

    def test_idempotency_has_one_worker_and_conflicting_body_is_refused(self):
        body = self.body(idempotency_key='fixture-request-1')
        first = A.start(body)
        second = A.start(body)
        self.assertEqual(first['id'], second['id'])
        self.assertTrue(second['existing'])
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(A.view(first['id'])['status'], 'done')
        self.assertEqual(self.invoke('mica/run', method='POST', body={**body, 'mode': 'static'})[0], 409)
        self.assertEqual(self.invoke('mica/plan', method='POST', body=body)[0], 409)

    def test_plan_execute_and_reconnect_keep_original_budget_and_folder(self):
        ident = A.start(self.body(), action='plan')['id']
        planned = A.view(ident)
        self.assertEqual(planned['status'], 'planned')
        self.assertTrue(planned['can_execute'])
        self.assertFalse(planned['can_resume'])
        self.assertTrue(A.resume(ident)['planned'])
        self.assertEqual(len(self.calls), 1)
        A.resume(ident, execute=True)
        done = A.view(ident)
        self.assertEqual(done['status'], 'done')
        self.assertTrue(A.resume(ident)['terminal'])
        self.assertEqual([row[0] for row in self.calls], ['plan', 'execute'])
        self.assertEqual(self.calls[0][1:5], self.calls[1][1:5])
        self.assertEqual(self.calls[1][1]['budget'], request()['budget'])
        self.assertEqual(len(A.list_runs()), 1)

    def test_listing_preserves_exhausted_result_separate_from_control_status(self):
        self.next_status = 'exhausted'
        ident = A.start(self.body())['id']
        self.assertEqual(A.view(ident)['status'], 'exhausted')
        with patch.object(A, 'view', side_effect=AssertionError('list must remain observational')), \
             patch.object(A, 'discover_inventory', side_effect=AssertionError('no worker probe')):
            row = next(r for r in A.list_runs() if r['id'] == ident)
        self.assertEqual(row['status'], 'exhausted')
        self.assertEqual(row['control_status'], 'failed')
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(len(self.calls), 1)

    def test_listing_refuses_outcome_from_another_generation(self):
        ident = A.start(self.body())['id']
        folder, _, _ = A._open(ident)
        generation = A.J.read_job(folder)['generation']
        name = 'outcome-' + generation + '.json'
        receipt = A._read(folder, name)
        receipt['generation'] = 'wrong-generation'
        A.G._write_json(folder, name, A.G._seal({k:v for k,v in receipt.items() if k != 'sha256'}))
        row = next(r for r in A.list_runs() if r['id'] == ident)
        self.assertEqual(row['status'], 'unavailable')
        self.assertEqual(len(self.launches), 1)

    def test_unknown_outcome_is_retained_and_never_relaunched(self):
        self.next_status = 'unknown'
        ident = A.start(self.body())['id']
        self.assertEqual(A.view(ident)['status'], 'unknown')
        self.assertTrue(A.resume(ident, execute=True)['terminal'])
        self.assertFalse(A.view(ident)['can_resume'])
        self.assertEqual(len(self.calls), 1)

    def test_missing_decisions_require_a_new_objective_not_resume(self):
        self.next_status = 'missing_decisions'
        ident = A.start({'objective': 'Resolve an ambiguous task.', 'budget': request()['budget'],
                         'inventory': INVENTORY})['id']
        self.assertEqual(A.view(ident)['status'], 'missing_decisions')
        self.assertFalse(A.view(ident)['can_resume'])
        self.assertTrue(A.resume(ident, execute=True)['terminal'])
        self.assertEqual(len(self.calls), 1)

    def test_stopped_requires_explicit_resume_with_same_frozen_request(self):
        self.next_status = 'stopped'
        ident = A.start(self.body())['id']
        self.assertTrue(A.view(ident)['can_resume'])
        self.assertEqual(len(self.calls), 1)
        self.next_status = 'done'
        A.resume(ident)
        self.assertEqual(A.view(ident)['status'], 'done')
        self.assertEqual(self.calls[0][1:5], self.calls[1][1:5])
        self.assertEqual(len(list(A._folder(ident).glob('outcome-*.json'))), 2)

    def test_delayed_canceled_generation_cannot_dispatch(self):
        deferred = []
        def reserve(ident, folder, generation):
            deferred.append((ident, folder, generation))
            return {'ok': True}
        with patch.dict(A.launcher, {'launch': reserve}):
            ident = A.start(self.body())['id']
        A.stop(ident)
        _, folder, generation = deferred[0]
        value = A.run_job(folder, applicators=object(), generation=generation, runtime_factory=self.factory)
        self.assertEqual(value['status'], 'not_started')
        self.assertFalse(self.calls)
        A.resume(ident)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(A.view(ident)['status'], 'done')

    def test_worker_lifetime_blocks_new_generation_despite_inactive_unit_probe(self):
        deferred = []
        def reserve(ident, folder, generation):
            deferred.append((ident, folder, generation))
            return {'ok': True}
        with patch.dict(A.launcher, {'launch': reserve}):
            ident = A.start(self.body())['id']
        _, folder, generation = deferred[0]
        guard, _ = A.J.begin_job(Path(folder), generation, threading.Event(), final=False)
        try:
            self.assertTrue(A.view(ident)['active'])
            self.assertTrue(A.resume(ident)['already_active'])
            self.assertEqual(A.J.read_job(Path(folder))['generation'], generation)
        finally:
            A.J.finish_job(Path(folder), generation, 'stopped')
            guard.release()

    def test_stop_fences_running_generation_then_explicit_resume_uses_same_runtime(self):
        entered = threading.Event()
        worker = []
        failures = []
        def factory(req, folder, apps, inventory, stop=None, *, library=None):
            class Run:
                def execute(self, mode):
                    entered.set()
                    if not stop.wait(3):
                        raise AssertionError('Owner cancellation did not reach the worker.')
                    return result('stopped')
            return Run()
        def launch(ident, folder, generation):
            def work():
                try:
                    A.run_job(folder, applicators=object(), generation=generation, runtime_factory=factory)
                except BaseException as error:  # noqa: BLE001 - assert worker-thread failures in the owning test
                    failures.append(error)
            thread = threading.Thread(target=work)
            worker.append(thread)
            thread.start()
            self.assertTrue(entered.wait(3))
            return {'ok': True}
        def stop_worker(_):
            worker[0].join(3)
            return not worker[0].is_alive()
        with patch.dict(A.launcher, {'launch': launch, 'stop': stop_worker}):
            ident = A.start(self.body())['id']
            old = A.view(ident)['job']['generation']
            self.assertTrue(A.stop(ident)['ok'])
        self.assertFalse(failures)
        self.assertEqual(A.view(ident)['status'], 'stopped')
        self.assertTrue(A.view(ident)['can_resume'])
        A.resume(ident)
        current = A.view(ident)
        self.assertEqual(current['status'], 'done')
        self.assertNotEqual(old, current['job']['generation'])
        self.assertEqual(self.calls[0][1], request())
        self.assertEqual(self.calls[0][2], str(A._folder(ident)/'runtime'))

    def test_launch_failure_is_visible_and_resume_reserves_new_generation(self):
        with patch.dict(A.launcher, {'launch': lambda *_: {'ok': False, 'error': 'isolated launch failed'}}):
            status, error = self.invoke('mica/run', method='POST', body=self.body(idempotency_key='launch-fail'))
        self.assertEqual(status, 503)
        self.assertIn('launch failed', error['error'])
        ident = hashlib.sha256(b'launch-fail').hexdigest()[:12]
        first = A.view(ident)
        self.assertEqual(first['status'], 'failed')
        A.resume(ident)
        self.assertNotEqual(first['job']['generation'], A.view(ident)['job']['generation'])
        self.assertEqual(A.view(ident)['status'], 'done')

    def test_implementation_change_prevents_resume(self):
        self.next_status = 'stopped'
        ident = A.start(self.body())['id']
        with patch.object(A, '_implementation', return_value={'different': 1}):
            self.assertEqual(self.invoke('mica/resume', method='POST', body={'id': ident})[0], 409)
        self.assertEqual(len(self.calls), 1)

    def test_artifacts_verify_bytes_without_opening_output_paths(self):
        ident = A.start(self.body())['id']
        summary = A.artifacts(ident)['artifacts'][0]
        self.assertNotIn('text', summary)
        self.assertEqual(A.artifacts(ident, include_text=True)['artifacts'][0]['text'], result()['output']['text'])
        folder, _, frozen = A._open(ident)
        generation = A.J.read_job(folder)['generation']
        outcome = A._read(folder, 'outcome-' + generation + '.json')
        outcome['result']['output']['text'] += ' altered'
        A.G._write_json(folder, 'outcome-' + generation + '.json', A.G._seal(outcome))
        self.assertEqual(self.invoke('mica/artifacts', id=ident)[0], 409)
        self.assertEqual(frozen['spec']['task']['request']['allowed_outputs'], ['result.js'])

    def test_tamper_and_symlink_paths_are_refused(self):
        ident = A.start(self.body())['id']
        path = A._folder(ident)/'frozen.json'
        raw = json.loads(path.read_text())
        raw['spec']['mode'] = 'direct'
        path.write_text(json.dumps(raw))
        self.assertEqual(self.invoke('mica/run', id=ident)[0], 400)
        self.assertEqual(self.invoke('mica/run', id='../escape')[0], 404)
        target = self.path/'outside'
        target.mkdir(mode=0o700)
        (A._root()/('a'*12)).symlink_to(target, target_is_directory=True)
        self.assertEqual(self.invoke('mica/run', id='a'*12)[0], 400)

    def test_host_fence_and_no_ready_inventory_precede_launch(self):
        with patch.object(A, '_host_ok', return_value=False):
            self.assertEqual(self.invoke('mica/run', method='POST', body=self.body())[0], 409)
            self.assertEqual(A.run_job(self.path/'missing', applicators=object())['status'], 'not_started')
        self.assertEqual(self.invoke('mica/run', method='POST', body=self.body(inventory=[]))[0], 409)
        self.assertFalse(self.calls)

    def test_objective_project_path_and_internal_component_library(self):
        body = {'objective': 'Return input plus one.', 'budget': request()['budget'],
                'allowed_outputs': ['result.js'], 'inventory': INVENTORY, 'reuse_components': True}
        ident = A.start(body, action='plan')['id']
        self.assertEqual(A.view(ident)['status'], 'planned')
        self.assertEqual(self.calls[0][1]['objective'], body['objective'])
        self.assertEqual(self.calls[0][-1], A._root()/'_components')
        self.assertEqual(self.invoke('mica/check', method='POST', body={**body, 'library': '/tmp'})[0], 400)

    def test_inventory_is_cached_only_and_unavailable_facts_are_explicit(self):
        node = {'id': 'node-f', 'role': 'worker', 'online': True, 'stale': False,
                'power': 'performance', 'guest_busy': False, 'agents': {'online': True,
                'ollama': {'installed': True, 'models': ['fixture-small', 'fixture-embed']}}}
        with patch('host_fleet.nodes', return_value=[node]) as cached, \
                patch('host_fleet._draining', return_value=False), \
                patch('host_agents.active_runs', return_value=[]), \
                patch('host_agents.capabilities', side_effect=AssertionError('unexpected probe')):
            data = A.discover_inventory()
        cached.assert_called_once_with(refresh=False)
        self.assertEqual(len(data['inventory']), 1)
        self.assertTrue(data['inventory'][0]['available'])
        self.assertIsNone(data['inventory'][0]['digest'])
        self.assertIsNone(data['inventory'][0]['context_chars'])
        with patch('host_fleet.nodes', return_value=[{**node, 'stale': True}]), \
                patch('host_fleet._draining', side_effect=AssertionError('stale must not be eligible')):
            stale = A.discover_inventory()
        self.assertFalse(stale['inventory'][0]['ready'])
        self.assertTrue(stale['diagnostics'])


    def test_calibration_is_an_exact_sealed_object_not_a_server_scan_and_is_frozen(self):
        from symblic.mica import search as M
        seed = calibration(); captured = []
        factory = self.factory
        def calibrated(req, folder, apps, inventory, stop=None, *, library=None, calibration=None):
            captured.append(calibration)
            return factory(req, folder, apps, inventory, stop=stop, library=library)
        with patch.object(M, 'implementation_identity', return_value=RUNTIME), \
                patch.object(self, 'factory', side_effect=calibrated):
            checked = A.check(self.body(calibration=seed))
            self.assertEqual(checked['spec']['calibration'], seed)
            self.assertEqual(checked['sha256'], A.G._hash(checked['spec']))
            self.next_status = 'stopped'
            ident = A.start(self.body(calibration=seed))['id']
            self.next_status = 'done'; A.resume(ident)
        self.assertEqual(captured, [seed, seed])
        self.assertEqual(A.view(ident)['spec']['calibration'], seed)
        with patch.object(M, 'implementation_identity', return_value=RUNTIME):
            self.assertEqual(self.invoke('mica/check', method='POST', body=self.body(calibration='/private/run'))[0], 400)
        with patch.object(M, 'implementation_identity', return_value={'different': True}):
            self.assertEqual(self.invoke('mica/check', method='POST', body=self.body(calibration=seed))[0], 400)
        self.assertEqual(self.invoke('mica/check', method='POST', body=self.body(calibration_file='/private/run'))[0], 400)

    def test_objective_module_format_survives_plan_execute_and_cannot_override_explicit_request(self):
        seen = []
        factory = self.project_factory
        def project(objective, folder, apps, inventory, budget, outputs, stop=None, *, library=None, artifact_format=None):
            seen.append((artifact_format, outputs))
            return factory(objective, folder, apps, inventory, budget, outputs, stop=stop, library=library)
        body = {'objective': 'Build a module library.', 'budget': request()['budget'],
                'inventory': INVENTORY, 'artifact_format': 'javascript_modules'}
        with patch.object(self, 'project_factory', side_effect=project):
            ident = A.start(body, action='plan')['id']; A.resume(ident, execute=True)
        self.assertEqual(seen, [('javascript_modules', ['index.mjs'])] * 2)
        self.assertEqual(A.view(ident)['spec']['task']['artifact_format'], 'javascript_modules')
        self.assertEqual(self.invoke('mica/check', method='POST', body=self.body(artifact_format='javascript_modules'))[0], 400)
        self.assertEqual(self.invoke('mica/check', method='POST', body={**body, 'artifact_format': 'javascript_script',
                                  'allowed_outputs': ['a.js', 'b.js']})[0], 400)
        caps = self.invoke('mica/capabilities')[1]
        self.assertEqual(caps['artifact_formats'], list(A.FORMATS))
        self.assertIn('calibration', caps)

    def test_module_bundle_download_covers_actual_files_and_archive_is_explicit(self):
        from symblic.mica import search as M
        from symblic.mica import bundle as B
        with patch.object(B, 'asset_snapshot', return_value={'fixture': b'exact trusted asset'}), \
                patch.object(M, 'implementation_identity', return_value=RUNTIME):
            bundle = bundle_result()
            class Run:
                def execute(self, mode): return copy.deepcopy(bundle)
            with patch.object(self, 'factory', return_value=Run()):
                ident = A.start(self.body(request=bundle['bundle']['request']))['id']
            code, summary = self.invoke('mica/artifacts', id=ident)
            self.assertEqual(code, 200, summary)
            self.assertEqual(len(summary['artifacts']), 2)
            self.assertNotIn('archive', summary)
            code, downloaded = self.invoke('mica/artifacts', id=ident, text='1', archive='1')
            self.assertEqual(code, 200, downloaded)
            raw = base64.b64decode(downloaded['archive']['base64'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), downloaded['archive']['sha256'])
            with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
                self.assertEqual(set(zipped.namelist()), {r['file'] for r in downloaded['artifacts']})
            self.assertFalse((A._folder(ident)/'package').exists())
            folder, _, _ = A._open(ident); generation = A.J.read_job(folder)['generation']
            outcome = A._read(folder, 'outcome-' + generation + '.json')
            outcome['result']['module_checks']['module_checks'].pop()
            A.G._write_json(folder, 'outcome-' + generation + '.json', A.G._seal(outcome))
            self.assertEqual(self.invoke('mica/artifacts', id=ident, archive='1')[0], 409)


if __name__ == '__main__':
    unittest.main()
