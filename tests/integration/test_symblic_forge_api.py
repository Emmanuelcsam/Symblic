"""Isolated persistence/API integration; no real providers, workers or fleet probes."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from integration.host import symblic_forge as API
from symblic.forge import core as C
from symblic.forge.store import Store, StoreError


def rid():
    return 'request-' + uuid.uuid4().hex


class ForgeAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Store(Path(self.tmp.name) / 'private')
        self.launch = patch.dict(API.launcher, launch=lambda _: {'ok': True}, active=lambda _: False, stop=lambda _: True)
        self.launch.start(); self.addCleanup(self.launch.stop)
        self.host = patch('symblic.autogen.runner.execution_fence', return_value=None)
        self.host.start(); self.addCleanup(self.host.stop)
        self.providers = patch('symblic.providers.applicators.Applicators.call', side_effect=AssertionError('No real model in API tests'))
        self.providers.start(); self.addCleanup(self.providers.stop)

    def call(self, route, **data):
        data.setdefault('request_id', rid())
        return API.dispatch('POST', route, data, db=self.db)

    def new(self, idea='I want a simple Snake game'):
        return self.call('project/create', idea=idea)['project']

    def action(self, p, action, **payload):
        return self.call('action', id=p['id'], revision=p['revision'], action=action, payload=payload)['project']

    def test_create_reload_preserves_exact_idea_and_schema(self):
        p = self.new('  Snake idea\nwith exact spacing  ')
        self.assertEqual(C.validate_project(p), p)
        self.assertEqual(self.db.get(p['id']), p)
        self.assertEqual(p['original_idea'], '  Snake idea\nwith exact spacing  ')
        self.assertEqual(C.analyze(p)['counts']['accepted'], 0)
        self.assertEqual(len(self.db.listing()), 1)
        self.assertEqual((self.db.root / 'forge.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_identical_request_replays_without_duplicate_project(self):
        request_id = rid()
        first = self.call('project/create', idea='x', request_id=request_id)
        replay = self.call('project/create', idea='x', request_id=request_id)
        self.assertEqual(first['project'], replay['project'])
        self.assertTrue(replay['duplicate'])
        self.assertEqual(len(self.db.listing()), 1)
        with self.assertRaises(StoreError):
            self.call('project/create', idea='changed', request_id=request_id)

    def test_cas_refuses_stale_and_bool_revisions_without_mutation(self):
        p = self.new(); q = self.action(p, 'project.rename', title='New title')
        for revision in (0, True, '1', -1):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.call('action', id=p['id'], revision=revision, action='project.rename', payload={'title': 'bad'})
        self.assertEqual(self.db.get(p['id']), q)

    def test_concurrent_same_revision_has_one_winner(self):
        p = self.new()
        def rename(i):
            try:
                return self.action(p, 'project.rename', title='Concurrent ' + str(i))
            except StoreError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(rename, range(2)))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertEqual(results.count(409), 1)
        self.assertEqual(len(self.db.history(p['id'])), 2)

    def test_undo_redo_are_new_events_and_survive_new_store(self):
        p = self.new(); initial = copy.deepcopy(p)
        p = self.action(p, 'project.rename', title='New title')
        p = self.action(p, 'undo')
        self.assertEqual(p['title'], initial['title']); self.assertEqual(p['revision'], 2)
        self.db = Store(self.db.root)
        p = self.action(p, 'redo')
        self.assertEqual(p['title'], 'New title'); self.assertEqual(p['revision'], 3)
        self.assertEqual([r['action'] for r in self.db.history(p['id'])], ['redo', 'undo', 'project.rename', 'project.create'])

    def test_rejected_transaction_retains_previous_state_and_failure_receipt(self):
        p = self.new(); request_id = rid()
        with self.assertRaises(ValueError):
            self.call('action', id=p['id'], revision=0, action='statement.accept', payload={'id': 'missing'}, request_id=request_id)
        receipt = self.db.request(request_id)
        self.assertEqual(receipt['state'], 'failed')
        self.assertEqual(self.db.get(p['id']), p)
        self.assertEqual(len(self.db.history(p['id'])), 1)

    def test_post_commit_lost_response_can_be_recovered_without_repeat(self):
        p = self.new(); request_id = rid()
        body = {'id': p['id'], 'revision': 0, 'action': 'project.rename', 'payload': {'title': 'Once'}, 'request_id': request_id}
        with patch.object(self.db, 'api_finish', side_effect=RuntimeError('lost reply')):
            with self.assertRaises(RuntimeError):
                API.dispatch('POST', 'action', body, db=self.db)
        self.assertEqual(self.db.request(request_id)['state'], 'confirmed')
        replay = API.dispatch('POST', 'action', body, db=self.db)
        self.assertTrue(replay['duplicate']); self.assertEqual(replay['project']['revision'], 1)
        self.assertEqual(len(self.db.history(p['id'])), 2)

    def test_precommit_unknown_is_never_automatically_repeated(self):
        request_id = rid(); data = {'idea': 'Never repeated', 'request_id': request_id}
        self.db.api_begin(request_id, {'route': 'project/create', 'data': data})
        with self.assertRaises(StoreError):
            API.dispatch('POST', 'project/create', data, db=self.db)
        self.assertEqual(self.db.listing(), [])
        self.assertEqual(self.db.request(request_id)['state'], 'pending')

    def test_trusted_receipts_cannot_be_submitted_by_browser(self):
        p = self.new()
        for action in ('model.artifact', 'validation.record', 'handoff.record', 'export.record'):
            with self.subTest(action=action), self.assertRaises(StoreError):
                self.call('action', id=p['id'], revision=0, action=action, payload={})
        self.assertEqual(self.db.get(p['id']), p)

    def test_demo_is_explicit_separate_and_all_exports_are_retained(self):
        blank = self.new(); p = self.call('demo')['project']
        self.assertNotEqual(blank['id'], p['id'])
        self.assertEqual(C.analyze(blank)['counts']['accepted'], 0)
        self.assertTrue(C.analyze(p)['readiness']['ready'])
        for kind in ('manifest', 'brief', 'prompt', 'construction', 'tasks', 'sheet', 'symblic'):
            with self.subTest(kind=kind):
                result = self.call('export', id=p['id'], revision=p['revision'], format=kind)
                p, artifact = result['project'], result['artifact']
                self.assertEqual(artifact, self.db.artifact(artifact['id']))
                self.assertEqual(hashlib.sha256(artifact['text'].encode()).hexdigest(), artifact['sha256'])
                if kind == 'symblic':
                    self.assertTrue(artifact['validation']['ok'], artifact['validation'])
        self.assertEqual(len(p['exports']), 7)

    def test_handoff_freezes_current_bytes_without_executing_and_survives_undo(self):
        p = self.call('demo')['project']
        result = self.call('handoff', id=p['id'], revision=p['revision'])
        self.assertFalse(result['handoff']['execution_started'])
        self.assertEqual(len(result['artifacts']), 5)
        p = self.action(result['project'], 'undo')
        self.assertEqual(len(p['handoffs']), 1)
        self.assertEqual(p['handoffs'][0]['fingerprint'], C.fingerprint(p))
        self.assertEqual(self.db.jobs(p['id']), [])

    def test_blank_handoff_refused_and_imported_readiness_not_authoritative(self):
        p = self.new()
        with self.assertRaises(StoreError):
            self.call('handoff', id=p['id'], revision=p['revision'])
        manifest = C.export_manifest(C.snake_demo(project_id='import-fixture-project'))
        result = self.call('project/import', manifest=manifest)
        self.assertFalse(result['analysis']['readiness']['compiler_current'])

    def test_evidence_is_atomic_private_inert_and_requires_acceptance(self):
        p = self.new(); content = b'Observation: 20 mm with +/- 1 mm tolerance.\n'
        result = self.call('evidence/file', id=p['id'], revision=0, filename='measurement.txt', content_b64=base64.b64encode(content).decode())
        row = C.active_branch(result['project'])['entities']['evidence'][0]
        self.assertEqual(row['status'], 'proposed')
        self.assertEqual(row['sha256'], hashlib.sha256(content).hexdigest())
        artifact = self.db.artifact(row['file_artifact_id'])
        self.assertEqual(base64.b64decode(artifact['text']), content)
        for filename, data in (('../secret.txt', b'x'), ('x.svg', b'<svg/>'), ('x.png', b'not a PNG'), ('x.txt', b'\xff'), ('x.json', b'{bad}'), ('x.txt', b'<html>active</html>')):
            with self.subTest(filename=filename, data=data), self.assertRaises(ValueError):
                self.call('evidence/file', id=p['id'], revision=1, filename=filename, content_b64=base64.b64encode(data).decode())
        self.assertEqual(len(C.active_branch(self.db.get(p['id']))['entities']['evidence']), 1)

    def test_artifact_mismatch_rolls_back_document_and_receipt(self):
        p = self.new(); artifact = {'id': 'artifact-badbytes', 'source_revision': 0, 'text': 'bytes', 'sha256': '0'*64}
        request_id = rid()
        with self.assertRaises(StoreError):
            self.db.mutate(p['id'], 0, 'project.rename', {'title': 'Never saved'}, request_id, trusted=True, artifacts=[artifact])
        self.assertEqual(self.db.get(p['id']), p)
        self.assertFalse(self.db.request(request_id)['found'])

    def model(self, p, **kwargs):
        return self.call('model/start', id=p['id'], revision=p['revision'], role='QUESTIONER', apps=['ollama:qwen3:4b-instruct@node-f'], **kwargs)['job']

    def test_model_launch_is_once_and_failure_is_unknown(self):
        p = self.new(); request_id = rid(); calls = []
        with patch.dict(API.launcher, launch=lambda job: calls.append(job) or {'ok': False, 'error': 'Lost ack'}):
            job = self.model(p, request_id=request_id)
            replay = self.model(p, request_id=request_id)
        self.assertEqual(job['status'], 'unknown'); self.assertEqual(job['id'], replay['id'])
        self.assertEqual(len(calls), 1)

    def test_launch_ack_failure_cannot_overwrite_claimed_worker(self):
        p = self.new()
        def launch(job_id):
            self.db.update_job(job_id, {'status': 'running'})
            return {'ok': False, 'error': 'ack delayed'}
        with patch.dict(API.launcher, launch=launch):
            job = self.model(p)
        self.assertEqual(job['status'], 'running')

    def test_model_adoption_requires_same_project_branch_revision_and_only_proposes(self):
        p = self.new(); other = self.new('Separate')
        job = self.model(p)
        artifact = {'role': 'QUESTIONER', 'model': 'ollama:qwen3:4b-instruct@node-f', 'revision': 0,
                    'statements': [{'text': 'A proposed bounded behavior.', 'dimension': 'BEHAVIOR'}]}
        self.db.update_job(job['id'], {'status': 'completed', 'outcomes': [{'model': artifact['model'], 'artifact': artifact}]})
        with self.assertRaises(StoreError):
            self.call('model/adopt', id=other['id'], revision=0, job_id=job['id'])
        adopted = self.call('model/adopt', id=p['id'], revision=0, job_id=job['id'])['project']
        self.assertEqual(C.active_branch(adopted)['statements'][-1]['status'], 'proposed')
        with self.assertRaises(StoreError):
            self.call('model/adopt', id=p['id'], revision=adopted['revision'], job_id=job['id'])

    def test_foreign_job_stop_refused_and_lost_worker_never_relaunched(self):
        p = self.new(); other = self.new('other'); job = self.model(p)
        with self.assertRaises(StoreError):
            self.call('model/stop', id=other['id'], job_id=job['id'])
        recovered = self.call('model/recover', id=p['id'], job_id=job['id'])['job']
        self.assertEqual(recovered['status'], 'unknown')
        stopped = self.call('model/stop', id=p['id'], job_id=job['id'])['job']
        self.assertEqual(stopped['status'], 'cancelled')

    def test_terminal_worker_wins_recovery_and_stop_probe_races(self):
        for route, hook in [('model/recover', 'active'), ('model/stop', 'stop')]:
            with self.subTest(route=route):
                p = self.new(); job = self.model(p)
                def probe(_):
                    self.db.update_job(job['id'], {'status': 'completed', 'outcomes': []})
                    return hook == 'stop'
                with patch.dict(API.launcher, {hook: probe}):
                    result = self.call(route, id=p['id'], job_id=job['id'])
                self.assertEqual(result['job']['status'], 'completed')

    def test_corrupted_artifact_is_refused_on_read(self):
        p = self.new()
        result = self.call('export', id=p['id'], revision=0, format='manifest')
        artifact = result['artifact']
        artifact['text'] += ' corrupt bytes'
        with self.db.connection(True) as db:
            db.execute('UPDATE artifacts SET document=? WHERE id=?', (json.dumps(artifact), artifact['id']))
        with self.assertRaisesRegex(StoreError, 'recorded hash'):
            self.db.artifact(artifact['id'])

    def test_pending_requests_are_bounded_and_identity_immutable(self):
        p = self.new(); jobs = [self.model(p) for _ in range(3)]
        with self.assertRaises(StoreError):
            self.model(p)
        with self.assertRaises(StoreError):
            self.db.update_job(jobs[0]['id'], {'project_id': 'another-project'})

    def test_owner_gate_precedes_all_routes(self):
        class Handler:
            def require_owner(self, reason):
                return False
            def send_json(self, value, status=200):
                raise AssertionError('No private data before owner gate')
        with patch.object(API, 'dispatch', side_effect=AssertionError('No dispatch')):
            self.assertTrue(API.handle(Handler(), 'GET', '/api/symblic-forge/projects', {}))

    def test_sqlite_symlink_is_refused(self):
        self.db.root.mkdir()
        target = Path(self.tmp.name) / 'do-not-touch'
        target.write_text('preserve')
        (self.db.root / 'forge.sqlite3').symlink_to(target)
        with self.assertRaises(StoreError):
            self.db.listing()
        self.assertEqual(target.read_text(), 'preserve')

    def test_native_catalog_maps_terminal_aliases_and_retains_node_models(self):
        catalogue = {'models': {'local': [{'id': 'qwen', 'title': 'Qwen'}], 'gpt': [{'id': 'chat-model', 'title': 'Chat'}]},
                     'nodes': [{'id': 'node-f', 'models': [{'name': 'qwen-remote'}], 'ready': {'ollama': True}}]}
        with patch('integration.host.symblicos_tasks.catalog', return_value=catalogue):
            result = API.environment()
        self.assertEqual({m['id'] for m in result['models']['ollama']}, {'qwen', 'qwen-remote'})
        self.assertEqual(result['models']['chatgpt'][0]['id'], 'chat-model')
        self.assertEqual(result['native_placements'][0]['app'], 'ollama:qwen-remote@node-f')

    def test_inventory_capture_is_incomplete_proposed_and_never_launches(self):
        p = self.new()
        observed = {'models': {'ollama': [{'id': 'qwen'}]}, 'nodes': [{'id': 'node-f', 'models': [{'name': 'qwen'}]}]}
        with patch.object(API, 'environment', return_value=observed):
            result = self.call('inventory/attach', id=p['id'], revision=0)
        row = C.active_branch(result['project'])['entities']['evidence'][0]
        self.assertEqual(row['status'], 'proposed')
        self.assertFalse(row['inventory']['complete'])
        self.assertEqual(row['inventory']['nodes'][0]['models'], ['qwen'])
        self.assertEqual(self.db.jobs(p['id']), [])

    def test_compiler_repair_preview_checks_exact_source_and_remains_proposed(self):
        p = self.new(); source = 'not valid Symblic grammar'
        p = self.call('validate', id=p['id'], revision=0, source=source)['project']
        validation = C.active_branch(p)['validation']
        errors = validation['diagnostics']['diagnostics']
        index = next(i for i, row in enumerate(errors) if row['severity'] == 'error')
        p = self.action(p, 'entity.propose', kind='evidence', entity={'text': 'Explicit diagnostic repair',
            'evidence_type': 'compiler_repair', 'repair': {'source_sha256': validation['source_sha256'],
            'start': 0, 'end': len(source), 'replacement': 'program Fixed.\nlet fixture_value = 1.\nshow fixture_value.\n',
            'diagnostic_index': index, 'statement_ids': []}})
        row = C.active_branch(p)['entities']['evidence'][0]
        preview = self.call('repair/preview', id=p['id'], revision=p['revision'], evidence_id=row['id'])
        self.assertFalse(preview['repair']['validated'])
        self.assertEqual(self.db.get(p['id']), p)
        self.assertEqual(row['status'], 'proposed')
        checked = self.call('validate', id=p['id'], revision=p['revision'], source=preview['repair']['source'])
        self.assertTrue(checked['validation']['ok'])
        self.assertFalse(checked['analysis']['readiness']['compiler_current'])


if __name__ == '__main__':
    unittest.main()
