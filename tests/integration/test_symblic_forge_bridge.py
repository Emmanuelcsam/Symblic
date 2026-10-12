"""Frozen Forge lineage reaches real native preparation, with fake launch/providers.

HOST-ONLY: these cases drive integration/host/symblic_forge_bridge.py through the original host's tool registry
(host_tools), its test base class for tools (tests/tool_case.py of the host checkout) and, in two cases, its
personal agent and site modules; none of them is part of this repository, so the module is skipped without them.
"""
import copy
import hashlib
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

try:  # host-only: these modules belong to the private host system Symblic was built in
    import host_tools as bt
    from tests.tool_case import ToolCase
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from integration.host import symblic_engine as E
from integration.host import symblic_forge as Forge
from integration.host import symblic_forge_bridge as B
from symblic.forge.store import Store, StoreError, digest


class FrozenBridge(ToolCase):
    MODULES = ('symblic_forge',)
    ENV = {'SYMBLIC_FORGE_DATA': '{tmp}/forge', 'AUTOMATION_DATA_DIR': '{tmp}/automation'}

    def setUp(self):
        super().setUp()
        self.db = Store()
        project = Forge.dispatch('POST', 'demo', {'request_id': 'fixture-demo'}, db=self.db)['project']
        self.frozen = Forge.dispatch('POST', 'handoff', {'id': project['id'], 'revision': project['revision'],
                                                      'request_id': 'fixture-handoff'}, db=self.db)
        self.project = self.frozen['project']
        self.handoff = self.frozen['handoff']
        self.native = next(a for a in self.frozen['artifacts'] if a['format'] == 'symblic')
        self.body = {'project': project['id'], 'handoff': self.handoff['id'], 'artifact': self.native['id'],
                     'artifact_sha256': self.native['sha256'], 'source_revision': self.handoff['source_revision'],
                     'by': 'ollama:fixture-small-model@node-i', 'max_calls': 8, 'request_id': 'fixture-native-run',
                     'ollama_limits': {'num_predict': 2048, 'num_ctx': 8192, 'timeout_seconds': 300,
                                       'total_timeout_seconds': 900}}
        self.launched = []

        def launch(run_id, folder, resume):
            source = Path(folder, 'program.sym').read_text()
            meta = json.loads(Path(folder, 'meta.json').read_text())
            B.validate_saved(source, meta)
            self.launched.append((run_id, folder, resume))
            return {'ok': True}

        for patch in (mock.patch.dict(E.launcher, launch=launch, active=lambda *args, **kwargs: False),
                      mock.patch('symblic.autogen.runner.execution_fence', return_value=None),
                      mock.patch('symblic.providers.applicators.Applicators.call', side_effect=AssertionError('No model in tests'))):
            patch.start()
            self.addCleanup(patch.stop)

    def test_read_capability_is_bounded_private_untrusted_and_never_launches(self):
        self.assertDeclarationsClean()
        names = self.declarations()
        self.assertEqual(set(names), {'forge.handoff'})
        tool = bt.get('forge.handoff')
        self.assertEqual((tool['caller'], tool['effect'], tool['untrusted'], tool['mcp']),
                         ('owner', 'read', True, False))
        import personal_agent
        with self.assertRaises(ValueError):
            personal_agent.issue_token('owner', ['forge.handoff'])
        result = self.ok('forge.handoff', {'project': self.project['id'], 'handoff': self.handoff['id'],
                                          'artifact': self.native['id'], 'offset': 0, 'limit': 30}, caller_account='owner')
        value = result['json']
        self.assertEqual(value['content']['text'], self.native['text'][:30])
        self.assertEqual(value['content']['next_offset'], 30)
        self.assertFalse(value['execution_started'])
        self.assertEqual(len(value['artifacts']), 5)
        self.assertEqual(self.launched, [])

    def test_exact_frozen_native_source_and_origin_persist_before_launch(self):
        with mock.patch.object(B, 'sync_native', wraps=B.sync_native) as sync:
            receipt = B.run(self.body)
        self.assertEqual(receipt['state'], 'started', receipt)
        self.assertEqual(len(self.launched), 1)
        self.assertEqual(sync.call_count, 1)
        folder = Path(E.run_dir(receipt['run_id']))
        self.assertEqual((folder / 'program.sym').read_text(), self.native['text'])
        meta = json.loads((folder / 'meta.json').read_text())
        self.assertEqual(meta['forge_handoff']['artifact_sha256'], self.native['sha256'])
        self.assertEqual(meta['forge_handoff']['options_sha256'], digest(meta['options']))
        self.assertEqual(meta['options']['by'], self.body['by'])
        self.assertEqual(meta['options']['max_calls'], 8)
        self.assertEqual(meta['options']['ollama_limits'], self.body['ollama_limits'])
        self.assertEqual(meta['options']['execution_pins']['source_sha256'], self.native['sha256'])
        self.assertIn('Prose verification', receipt['assurance'])
        self.assertFalse(self.db.get(self.project['id'])['handoffs'][0]['execution_started'])

    def test_same_request_recovers_original_and_changed_payload_refuses(self):
        first = B.run(self.body)
        self.assertEqual(B.run(dict(self.body)), first)
        self.assertEqual(B.receipt(self.body['request_id']), first)
        with self.assertRaises(StoreError):
            B.run({**self.body, 'max_calls': 9})
        self.assertEqual(len(self.launched), 1)

    def test_lost_launch_response_keeps_handle_and_never_dispatches_twice(self):
        original = E.launcher['launch']

        def lost(*args):
            original(*args)
            raise TimeoutError('reply lost after native acceptance')

        with mock.patch.dict(E.launcher, launch=lost):
            first = B.run(self.body)
            self.assertEqual(first['state'], 'unknown', first)
            self.assertIsNone(first['execution_started'])
            self.assertIn('run_id', first)
            second = B.run(self.body)
        self.assertEqual(second, first)
        self.assertEqual(len(self.launched), 1)

    def test_missing_native_handle_after_reserved_intent_stays_unknown(self):
        self.db.api_begin(self.body['request_id'], {'operation': 'automation/symblic/forge/run', 'body': self.body})
        out = B.run(self.body)
        self.assertEqual(out['state'], 'unknown')
        self.assertNotIn('run_id', out)
        self.assertEqual(self.launched, [])

    def test_stale_accepted_spec_refuses_new_run_but_existing_receipt_survives(self):
        first = B.run(self.body)
        p = self.db.get(self.project['id'])
        p = self.db.mutate(p['id'], p['revision'], 'statement.propose',
                           {'text': 'An additional accepted requirement', 'dimension': 'BEHAVIOR'}, 'changed-spec-proposal')
        row = p['branches'][p['active_branch']]['statements'][-1]
        self.db.mutate(p['id'], p['revision'], 'statement.accept', {'id': row['id']}, 'changed-spec-accept')
        self.assertEqual(B.run(self.body), first)
        with self.assertRaisesRegex(StoreError, 'changed'):
            B.run({**self.body, 'request_id': 'different-native-run'})
        self.assertFalse(B.inspect({'project': p['id'], 'handoff': self.handoff['id']})['applicable'])
        self.assertEqual(len(self.launched), 1)

    def test_wrong_bytes_revision_artifact_and_proprietary_model_refuse_before_intent(self):
        for changes in ({'artifact_sha256': '0' * 64}, {'source_revision': True},
                        {'source_revision': 999}, {'artifact': 'artifact-not-mine'},
                        {'by': 'claude:opus'}, {'max_calls': True}, {'max_calls': 0}, {'max_calls': 201}):
            with self.subTest(changes=changes), self.assertRaises((StoreError, ValueError)):
                B.run({**self.body, **changes})
        self.assertEqual(B.receipt(self.body['request_id'])['state'], 'missing')
        self.assertEqual(self.launched, [])

    def test_tampered_retained_artifact_refuses_inspection_and_new_run(self):
        broken = copy.deepcopy(self.native)
        broken['text'] += 'changed'
        with self.db.connection(True) as db:
            db.execute('UPDATE artifacts SET document=? WHERE id=?', (json.dumps(broken), broken['id']))
        for action in (lambda: B.inspect({'project': self.project['id'], 'handoff': self.handoff['id']}),
                       lambda: B.run(self.body)):
            with self.assertRaisesRegex(StoreError, 'hash'):
                action()
        self.assertEqual(self.launched, [])

    def test_invalid_local_limits_refuse_before_reserving_intent(self):
        for limits in (None, {}, {'num_predict': 1},
                       {**self.body['ollama_limits'], 'num_predict': True},
                       {**self.body['ollama_limits'], 'timeout_seconds': 29},
                       {**self.body['ollama_limits'], 'num_ctx': 131073},
                       {**self.body['ollama_limits'], 'extra': 1}):
            with self.subTest(limits=limits), self.assertRaises(StoreError):
                B.run({**self.body, 'ollama_limits': limits})
        self.assertEqual(B.receipt(self.body['request_id'])['state'], 'missing')
        self.assertEqual(self.launched, [])

    def test_mismatched_frozen_lineage_refuses_even_if_artifact_hash_is_internally_valid(self):
        broken = copy.deepcopy(self.native)
        broken['text'] += '\n'
        broken['sha256'] = hashlib.sha256(broken['text'].encode()).hexdigest()
        with self.db.connection(True) as db:
            db.execute('UPDATE artifacts SET document=? WHERE id=?', (json.dumps(broken), broken['id']))
        with self.assertRaisesRegex(StoreError, 'lineage'):
            B.run(self.body)

    def test_resume_refuses_changed_native_source_and_execution_policy(self):
        out = B.run(self.body)
        folder = Path(E.run_dir(out['run_id']))
        original = (folder / 'program.sym').read_text()
        (folder / 'program.sym').write_text(original + '\n')
        with self.assertRaisesRegex(E.SymblicApiError, 'Forge resume refused'):
            E.resume_run(out['run_id'])
        (folder / 'program.sym').write_text(original)
        meta = json.loads((folder / 'meta.json').read_text())
        meta['options']['max_calls'] += 1
        (folder / 'meta.json').write_text(json.dumps(meta))
        with self.assertRaisesRegex(E.SymblicApiError, 'policy'):
            E.resume_run(out['run_id'])
        self.assertEqual(len(self.launched), 1)

    def test_co_tampered_model_and_policy_do_not_override_original_request(self):
        out = B.run(self.body)
        folder = Path(E.run_dir(out['run_id']))
        meta = json.loads((folder / 'meta.json').read_text())
        meta['by'] = meta['forge_handoff']['by'] = meta['options']['by'] = 'chatgpt:synthetic-model'
        meta['options']['max_calls'] = 99
        meta['forge_handoff']['options_sha256'] = digest(meta['options'])
        (folder / 'meta.json').write_text(json.dumps(meta))
        (folder / 'forge-origin.json').write_text(json.dumps(meta['forge_handoff']))
        with self.assertRaisesRegex(E.SymblicApiError, 'original durable request'):
            E.resume_run(out['run_id'])
        self.assertEqual(len(self.launched), 1)

    def test_removed_lineage_cannot_bypass_resume_validation(self):
        out = B.run(self.body)
        folder = Path(E.run_dir(out['run_id']))
        meta = json.loads((folder / 'meta.json').read_text())
        del meta['forge_handoff']
        (folder / 'meta.json').write_text(json.dumps(meta))
        with self.assertRaisesRegex(E.SymblicApiError, 'Missing Forge run lineage'):
            E.resume_run(out['run_id'])
        self.assertEqual(len(self.launched), 1)

    def test_copied_or_relabelled_native_run_cannot_resume_as_another_identity(self):
        out = B.run(self.body)
        original = Path(E.run_dir(out['run_id']))
        copied_id = 'fedcba987654'
        copied = Path(E.runs_dir(), copied_id)
        shutil.copytree(original, copied)
        with self.assertRaisesRegex(E.SymblicApiError, 'run identity'):
            E.resume_run(copied_id)
        meta = json.loads((copied / 'meta.json').read_text())
        meta['id'] = copied_id
        with self.assertRaisesRegex(StoreError, 'run identity'):
            B.validate_saved(self.native['text'], meta)
        self.assertEqual(len(self.launched), 1)

    def test_http_owner_gate_refuses_before_inspection_or_launch(self):
        handler = mock.Mock()
        handler.identity.side_effect = RuntimeError('unauthenticated')
        handler.require_person.return_value = False
        with mock.patch.object(B, 'inspect', side_effect=AssertionError('read crossed gate')), \
                mock.patch.object(B, 'run', side_effect=AssertionError('run crossed gate')):
            self.assertTrue(B.handle(handler, 'GET', 'forge/handoff', {}))
            self.assertTrue(B.handle(handler, 'POST', 'forge/run', self.body))
        self.assertEqual(self.launched, [])

    def test_full_workstation_discovers_and_reads_the_tool_but_gateway_cannot_hold_it(self):
        import personal_agent as pa
        import host_sched as sched
        from tests.test_workstation_mcp_recovery import bridge
        from urllib.parse import parse_qsl
        mod = bridge()

        def site(method, path, body=None, timeout=60):
            path, _, query = path.partition('?')
            route = path.removeprefix('/api/personal-agent/')
            if route == 'capabilities':
                return {'items': pa.capabilities(probe={})}
            result = pa.dispatch('owner', method, route, body or {}, dict(parse_qsl(query)))
            if route == 'action/propose' and not result.get('replayed'):
                mid = result['mission_id']
                step = self.store.select('steps', 'mission=?', (mid,))[0]
                self.store.update('steps', step['id'], status='dispatched')
                sched.exec_tool(self.store.get('missions', mid), self.store.get('steps', step['id']))
            return result

        with mock.patch.object(mod, 'STATE', str(Path(self.tmp, 'workstation'))), \
                mock.patch.object(mod, '_site', site), mock.patch.object(mod, 'WAIT_S', 0), \
                mock.patch.object(mod, '_mode', return_value={'full': True, 'auto_approve': False}):
            listed = mod.call('site_capabilities', {'tool': 'forge.handoff'})
            self.assertEqual(listed['total'], 1)
            self.assertTrue(listed['items'][0]['untrusted'])
            out = mod.call('site_call', {'tool': 'forge.handoff', 'args': {
                'project': self.project['id'], 'handoff': self.handoff['id']}, 'request_id': 'workstation-forge-read'})
        self.assertIn('steps', out, out)
        self.assertEqual(out['steps'][0]['result']['json']['fingerprint'], self.handoff['fingerprint'])
        with self.assertRaises(ValueError):
            pa.issue_token('owner', ['forge.handoff'])
        self.assertEqual(self.launched, [])

    def test_runner_read_uses_real_tool_durable_ledger_and_untrusted_flow(self):
        import host_site as H
        from symblic.kernel import effects as FX
        from symblic.kernel.run import Run
        calls = []

        def http(method, path, body=None, timeout=60):
            calls.append(path)
            if path == '/api/personal-agent/capabilities':
                return 200, {'items': [bt.descriptor(bt.get('forge.handoff'))]}
            if path == '/api/fleet/tools/try':
                return 200, bt.call(body['name'], body['args'], {})
            raise AssertionError('An inspection attempted a write: ' + path)

        host = H.SiteHost('abc123def456', http=http)
        source = 'observe plan = forge.handoff(project=' + json.dumps(self.project['id']) + ', handoff=' + json.dumps(self.handoff['id']) + ').\nshow plan.data.fingerprint.'
        rows = host.catalogue()
        self.assertTrue(rows[0]['untrusted'])
        self.assertTrue(FX.check(source, rows)['ok'])
        action = {'name': 'agents.start', 'effect': 'compute', 'policy': 'auto', 'instructs': True,
                  'params': {'type': 'object', 'properties': {'prompt': {'type': 'string'}}}}
        unsafe = FX.check(source + '\nact run = agents.start(prompt=plan.text).', rows + [action])
        self.assertFalse(unsafe['ok'])
        self.assertTrue(any('untrusted' in error['message'] for error in unsafe['errors']))
        folder = str(Path(self.tmp, 'runner-read'))
        options = {'effects': host, 'side_effects': False}
        first = Run(source, folder=folder, options=options).execute()
        self.assertEqual(first['status'], 'done', first.get('error'))
        again = Run(source, folder=folder, options=options).execute()
        self.assertEqual(again['status'], 'done', again.get('error'))
        self.assertEqual(calls.count('/api/fleet/tools/try'), 1)
        rows = [json.loads(line) for line in Path(folder, FX.LEDGER).read_text().splitlines()]
        self.assertEqual([row['phase'] for row in rows], ['intent', 'done'])
        self.assertEqual(self.launched, [])
