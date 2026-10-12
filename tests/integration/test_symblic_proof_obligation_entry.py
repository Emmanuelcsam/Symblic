"""Owner-gated obligation/7 CLI/API journeys, fake providers and temporary stores."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import automation_engine as AE
    import host_apps
    import security_gate as SG
    from integration.host import symblic_engine as E
    from tests.integration.test_symblic_engine import Base
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.kernel import language as S
from symblic.providers import applicators as symblic_apply
from symblic.delegate import contracts as D
from symblic.delegate import run as H
from symblic.adapters import proof_command as C
from symblic.adapters import proof_session as R
from symblic.kernel import run as N
from tests.delegate.test_symblic_delegate_proof_obligation import HANDOFF, request
from tests.delegate.test_symblic_delegate_proof_step import COMMANDS, GOAL, PREMISES, prefix
from tests.integration.test_symblic_proof_step_entry import OwnedFake, RoutedHandler, cli


def wrong_scope_task():
    return request('"A"', session=R.start({}, ['atom', 'Z']),
                   commands=['assume :: "A"'], calls=1)


class ProofObligationCLI(unittest.TestCase):
    def test_catalog_full_compact_check_compile_preserve_exact_obligation_without_provider(self):
        with patch.object(symblic_apply, 'Applicators', side_effect=AssertionError('Read-only CLI built a provider')):
            code, text, _ = cli(['catalog', '--agent-json'])
            self.assertEqual(code, 0)
            catalog = json.loads(text)
            self.assertIn({'id': 'proof_step_obligation', 'template_id': 'symblic.delegate/proof_step_obligation/7'},
                          catalog['templates'])
            for capsule in ('full', 'compact'):
                body = request(capsule=capsule)
                expected = D.compile_task(body)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
                    for action in ('check', 'compile'):
                        code, text, _ = cli([action, str(path), '--agent-json'])
                        self.assertEqual(code, 0, text)
                        self.assertEqual(json.loads(text), {'ok': True, **expected})
                    code, text, _ = cli(['compile', str(path)])
                    self.assertEqual((code, text), (0, expected['source']))

    def test_run_acceptance_rejection_and_malformed_scope_use_no_live_provider(self):
        for body, answer, accepted in ((request(calls=1, capsule='compact'), 3, True),
                                       (request(calls=1), 2, False), (wrong_scope_task(), 1, False)):
            apps = OwnedFake([answer])
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
                folder = Path(directory, 'run')
                with patch.object(symblic_apply, 'Applicators', return_value=apps):
                    code, text, _ = cli(['run', str(path), '--dir', str(folder), '--agent-json'])
                value = json.loads(text)
                self.assertEqual(code, 0 if accepted else 1, text)
                self.assertIs(value['accepted'], accepted)
                self.assertEqual(value['calls'], 1)
                self.assertEqual(apps.cancelled, 1)
                if accepted:
                    self.assertTrue(value['result']['obligation_satisfied'])
                    self.assertEqual(value['result']['inference'], S.canon(S.from_json(
                        C.append(PREMISES, GOAL, prefix(), COMMANDS[2]))))
                    self.assertTrue(R.frontier(HANDOFF.checked_child_state(body, value))['complete'])
                else:
                    self.assertIsNone(value['result'])
        malformed = request(scope=['s999'])
        apps = OwnedFake([])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'task.json'); path.write_text(json.dumps(malformed))
            folder = Path(directory, 'uncreated')
            with patch.object(symblic_apply, 'Applicators', return_value=apps):
                code, text, _ = cli(['run', str(path), '--dir', str(folder), '--agent-json'])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(text)['ok'])
            self.assertFalse(folder.exists())
        self.assertEqual(apps.requests, [])
        self.assertEqual(apps.cancelled, 1)


class ProofObligationAPI(Base):
    def setUp(self):
        super().setUp()
        for target in (patch.dict(host_apps._modules, {'automation_engine': AE}),
                       patch.object(AE, '_ensure_started', side_effect=AssertionError('No scheduler in API test')),
                       patch.object(SG, 'OWNER_EMAILS', {'owner@example.test'})):
            target.start(); self.addCleanup(target.stop)
        self.apps.answer = lambda _app, _prompt: {'answer': 3}

    def routed(self, method, route, data=None, query=None, identity=None):
        handler = RoutedHandler(route, query, identity)
        handled = host_apps.handle_get(handler) if method == 'GET' else host_apps.handle_post(handler, data)
        self.assertTrue(handled)
        return handler

    def test_owner_catalog_full_compact_compile_and_preview_retain_obligation_without_selection(self):
        catalog = self.routed('GET', 'delegate/catalog')
        self.assertEqual(catalog.status, 200)
        self.assertIn({'id': 'proof_step_obligation', 'template_id': 'symblic.delegate/proof_step_obligation/7'},
                      catalog.sent['templates'])
        for capsule in ('full', 'compact'):
            body = request(capsule=capsule); original = copy.deepcopy(body)
            compiled = self.routed('POST', 'delegate/compile', body)
            self.assertEqual(compiled.status, 200)
            self.assertEqual(compiled.sent, {'ok': True, **D.compile_task(body)})
            self.assertEqual(compiled.sent['inputs']['obligation'],
                             {'formula': ['atom', 'B'], 'open_assumptions': [], 'reading': '"B"'})
            with patch.object(C, 'append', side_effect=AssertionError('Preview checked a candidate')), \
                    patch.object(N.Run, 'determine', side_effect=AssertionError('Preview searched')), \
                    patch.object(N.Run, 'vacuity', side_effect=AssertionError('Preview probed vacuity')):
                preview = self.routed('POST', 'preview', {'source': compiled.sent['source'],
                                                         'inputs': compiled.sent['inputs']})
            self.assertEqual(preview.status, 200, preview.sent)
            self.assertEqual(preview.sent['status'], 'paused')
            next_step = preview.sent['next']
            self.assertEqual(next_step['name'], 'choice')
            self.assertEqual(next_step['context_manifest']['presentation'], capsule)
            self.assertEqual(next_step['schema']['properties']['answer'], {'type': 'integer', 'minimum': 1, 'maximum': 3})
            for value in (*COMMANDS, 'obligation', 'open_assumptions', 'reading', 'one-based integer'):
                self.assertIn(value, next_step['prompt'])
            row = next(line for line in next_step['prompt'].splitlines() if line.startswith('- obligation : Any = '))
            self.assertEqual(json.loads(row.partition(' = ')[2]), compiled.sent['inputs']['obligation'])
            self.assertEqual(body, original)
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])
        self.assertEqual(list(Path(self.tmp).rglob('*')), [])

    def test_accepted_canonical_api_result_retains_goal_obligation_and_original_request(self):
        body = request(calls=1); body['params']['require_complete'] = True
        contract = D.compile_task(body); body['expected_contract_id'] = contract['contract_id']
        started = self.routed('POST', 'delegate/run', {'task': body})
        self.assertEqual(started.status, 200, started.sent)
        result = self.routed('GET', 'delegate/result', query={'id': started.sent['id']})
        self.assertEqual(result.status, 200, result.sent)
        expected = {'choice': 3, 'command': COMMANDS[2], 'menu_member': True, 'obligation_satisfied': True,
                    'inference': C.append(PREMISES, GOAL, prefix(), COMMANDS[2]), 'handoff': contract['handoff']}
        self.assertEqual(result.sent['result'], S.canon(S.from_json(expected)))
        self.assertTrue(result.sent['accepted'])
        self.assertEqual(result.sent['contract_id'], contract['contract_id'])
        state = HANDOFF.checked_child_state(body, result.sent)
        self.assertEqual(state['goal'], GOAL)
        self.assertTrue(R.frontier(state)['complete'])
        self.assertEqual(result.sent['calls'], 1)
        self.assertEqual(self.apps.calls[0]['app']['spec'], H.LOCAL_LADDER[0])
        folder = Path(E.run_dir(started.sent['id']))
        self.assertTrue(folder.is_relative_to(Path(self.tmp)))
        meta = json.loads((folder / 'meta.json').read_text())
        self.assertEqual(meta['delegation']['request'], body)
        self.assertEqual(meta['inputs']['obligation'], contract['inputs']['obligation'])
        self.assertEqual(meta['inputs']['handoff_binding'], contract['handoff'])

    def test_off_target_and_wrong_scope_reject_while_explicit_partial_scope_is_distinct(self):
        open_task = wrong_scope_task(); open_task['params']['obligation']['open_assumptions'] = ['s1']
        for body, answer, accepted in ((request(calls=1), 2, False), (wrong_scope_task(), 1, False),
                                       (open_task, 1, True)):
            self.apps.answer = lambda _app, _prompt, answer=answer: {'answer': answer}
            started = self.routed('POST', 'delegate/run', {'task': body})
            self.assertEqual(started.status, 200, started.sent)
            result = self.routed('GET', 'delegate/result', query={'id': started.sent['id']})
            self.assertEqual(result.status, 200, result.sent)
            self.assertIs(result.sent['accepted'], accepted)
            if accepted:
                self.assertTrue(result.sent['result']['obligation_satisfied'])
                self.assertFalse(result.sent['result']['inference']['complete'])
                self.assertEqual(result.sent['result']['inference']['line']['free'], ['s1'])
                self.assertEqual(HANDOFF.checked_child_state(body, result.sent)['goal'], ['atom', 'Z'])
            else:
                self.assertIsNone(result.sent['result'])
                with self.assertRaises(ValueError):
                    HANDOFF.checked_child_state(body, result.sent)

    def test_nonowners_cannot_reach_obligation_paths_with_forged_owner_header(self):
        identities = [SG.Identity(SG.ANONYMOUS), SG.Identity(SG.VERIFIED, 'guest@example.test'),
                      SG.Identity(SG.ANONYMOUS, 'owner@example.test')]
        routes = [('GET', 'delegate/catalog', None), ('POST', 'delegate/compile', request()),
                  ('POST', 'preview', {}), ('POST', 'delegate/run', {'task': request()}),
                  ('GET', 'delegate/result', None)]
        with patch.object(E, 'handle', side_effect=AssertionError('Nonowner reached engine')):
            for identity in identities:
                for method, route, body in routes:
                    with self.subTest(identity=identity.level, route=route):
                        response = self.routed(method, route, body, identity=identity)
                        self.assertEqual(response.status, 403)
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])
        self.assertEqual(list(Path(self.tmp).rglob('*')), [])

    def test_malformed_scope_refuses_before_any_store_or_launch(self):
        for scope in (None, 's3', ['s1'], ['s99'], ['s3', 's3'], [True], [{}]):
            body = request(); body['params']['obligation']['open_assumptions'] = scope
            for route, envelope in (('delegate/compile', body), ('delegate/run', {'task': body})):
                result = self.routed('POST', route, envelope)
                if route.endswith('compile'):
                    self.assertEqual(result.status, 200)
                    self.assertFalse(result.sent['ok'])
                else:
                    self.assertEqual(result.status, 400)
                self.assertNotIn('accepted', result.sent)
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])
        self.assertEqual(list(Path(self.tmp).rglob('*')), [])

    def test_tampered_handoff_or_obligation_refuses_read_resume_and_parent_adoption(self):
        body = request(calls=1)
        started = self.routed('POST', 'delegate/run', {'task': body})
        self.assertEqual(started.status, 200, started.sent)
        ident = started.sent['id']; folder = Path(E.run_dir(ident))
        meta_path = folder / 'meta.json'; original = meta_path.read_text()
        before = len(self.launches), len(self.apps.calls)
        for field in ('obligation', 'handoff_binding'):
            meta = json.loads(original)
            target = meta['inputs'][field]
            if field == 'handoff_binding':
                target = target['obligation']
            target['open_assumptions'] = ['s3']
            meta_path.write_text(json.dumps(meta))
            for result in (self.routed('GET', 'delegate/result', query={'id': ident}),
                           self.routed('POST', 'resume', {'id': ident})):
                self.assertEqual(result.status, 400, result.sent)
                self.assertNotIn('accepted', result.sent)
        meta_path.write_text(original)
        result = self.routed('GET', 'delegate/result', query={'id': ident})
        self.assertTrue(result.sent['accepted'])
        altered = copy.deepcopy(result.sent)
        altered['result']['handoff']['obligation']['formula'] = ['atom', 'A']
        with self.assertRaises(ValueError):
            HANDOFF.checked_child_state(body, altered)
        state_path = folder / 'state.json'; state = json.loads(state_path.read_text())
        state['outputs'][0]['canonical']['handoff']['obligation']['open_assumptions'] = ['s3']
        state_path.write_text(json.dumps(state))
        result = self.routed('GET', 'delegate/result', query={'id': ident})
        self.assertEqual(result.status, 400, result.sent)
        self.assertNotIn('accepted', result.sent)
        self.assertEqual((len(self.launches), len(self.apps.calls)), before)


if __name__ == '__main__':
    unittest.main()
