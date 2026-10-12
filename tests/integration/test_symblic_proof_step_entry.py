"""Actual owner-gated CLI/API journeys; temporary stores and fake providers only."""
import ast
import contextlib
import copy
import io
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
    from tests.integration.test_symblic_engine import Base, Handler
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
from tests.delegate.test_symblic_delegate_proof_step import COMMANDS, GOAL, PREMISES, prefix, request

ROOT = Path(__file__).resolve().parents[2]
# Match the existing terminal-route security fixtures: run the exact owner gate,
# without importing server.py's live singletons or workers.
TREE = ast.parse((ROOT / 'server.py').read_text())
DASHBOARD = next(node for node in TREE.body if getattr(node, 'name', '') == 'DashboardHandler')
OWNER_GATE = next(node for node in DASHBOARD.body if getattr(node, 'name', '') == 'require_owner')
OWNER_NS = {'_security_audit': lambda *_args: None}
exec(compile(ast.Module(body=[OWNER_GATE], type_ignores=[]), 'server.py', 'exec'), OWNER_NS)


class RoutedHandler(Handler):
    require_owner = OWNER_NS['require_owner']

    def __init__(self, route, query=None, identity=None):
        super().__init__(query)
        self.path = '/api/automation/symblic/' + route
        self.ident = identity if identity is not None else SG.Identity(SG.LOCAL)
        # stands in for the authenticated-user header the host's access proxy added to every request
        self.headers = {'X-Authenticated-User-Email': 'owner@example.test'}

    def identity(self):
        return self.ident

    def send_error(self, status, message):
        self.send_json({'error': message}, status)


class OwnedFake:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []
        self.cancelled = 0

    def call(self, task):
        self.requests.append(task)
        if not self.answers:
            raise AssertionError('Unexpected fake child dispatch')
        return {'ok': True, 'json': {'answer': self.answers.pop(0)}, 'model': 'fake', 'node': 'isolated'}

    def cancel_all(self):
        self.cancelled += 1


def cli(arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = H.main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class ProofStepCLI(unittest.TestCase):
    def test_catalog_check_and_compile_discover_identical_contract_without_provider(self):
        body = request(capsule='compact')
        expected = D.compile_task(body)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
            with patch.object(symblic_apply, 'Applicators', side_effect=AssertionError('Read-only CLI built a provider')):
                code, text, _ = cli(['catalog', '--agent-json'])
                self.assertEqual(code, 0)
                catalog = json.loads(text)
                self.assertIn({'id': 'proof_step', 'template_id': 'symblic.delegate/proof_step/6'}, catalog['templates'])
                for action in ('check', 'compile'):
                    code, text, _ = cli([action, str(path), '--agent-json'])
                    self.assertEqual(code, 0, text)
                    self.assertEqual(json.loads(text), {'ok': True, **expected})
                code, text, _ = cli(['compile', str(path)])
                self.assertEqual((code, text), (0, expected['source']))

    def test_run_returns_exact_canonical_parent_value_and_cleans_owned_fake(self):
        body = request(calls=1, capsule='compact')
        body['params']['require_complete'] = True
        expected = D.compile_task(body)
        body['expected_contract_id'] = expected['contract_id']
        apps = OwnedFake([3])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
            folder = Path(directory, 'record')
            with patch.object(symblic_apply, 'Applicators', return_value=apps):
                code, text, _ = cli(['run', str(path), '--dir', str(folder), '--agent-json'])
            self.assertEqual(code, 0, text)
            result = json.loads(text)
            self.assertTrue(result['accepted'])
            self.assertEqual(result['result']['inference'], S.canon(S.from_json(C.append(PREMISES, GOAL, prefix(), COMMANDS[2]))))
            self.assertEqual(result['result']['handoff'], expected['handoff'])
            self.assertEqual(result['contract_id'], expected['contract_id'])
            self.assertEqual(result['calls'], 1)
            self.assertEqual(result['result']['command'], COMMANDS[2])
            meta = json.loads((folder / 'meta.json').read_text())
            self.assertIs(meta['options']['side_effects'], False)
            self.assertIn('execution_pins', meta['options'])
        self.assertEqual(apps.cancelled, 1)
        self.assertEqual(apps.requests[0]['app']['spec'], H.LOCAL_LADDER[0])
        self.assertEqual(apps.requests[0]['context_manifest']['presentation'], 'compact')

    def test_invalid_logic_and_malformed_cli_requests_expose_no_accepted_result(self):
        for body, answer in ((request(calls=1), 1),):
            apps = OwnedFake([answer])
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
                with patch.object(symblic_apply, 'Applicators', return_value=apps):
                    code, text, _ = cli(['run', str(path), '--agent-json'])
            result = json.loads(text)
            self.assertEqual(code, 1)
            self.assertFalse(result['accepted'])
            self.assertIsNone(result['result'])
            self.assertEqual(apps.cancelled, 1)
        bad = request(); bad['params']['commands'] = ['premise a\nact notes.write(text="bad").']
        injected = request(); injected['options'] = {'side_effects': True}
        for body in ({}, [], bad, injected):
            apps = OwnedFake([])
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
                with patch.object(symblic_apply, 'Applicators', return_value=apps):
                    code, text, _ = cli(['run', str(path), '--agent-json'])
            self.assertEqual(code, 1, text)
            self.assertFalse(json.loads(text)['ok'])
            self.assertEqual(apps.requests, [])
            self.assertEqual(apps.cancelled, 1)


class ProofStepAPI(Base):
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

    def test_owner_discovery_compile_and_preview_preserve_exact_ordinal_capsule_without_dispatch(self):
        body = request(capsule='compact')
        original = copy.deepcopy(body)
        catalog = self.routed('GET', 'delegate/catalog')
        self.assertEqual(catalog.status, 200)
        self.assertIn({'id': 'proof_step', 'template_id': 'symblic.delegate/proof_step/6'}, catalog.sent['templates'])
        compiled = self.routed('POST', 'delegate/compile', body)
        self.assertEqual(compiled.status, 200)
        self.assertEqual(compiled.sent, {'ok': True, **D.compile_task(body)})
        with patch.object(C, 'append', side_effect=AssertionError('Preview checked a candidate')):
            preview = self.routed('POST', 'preview', {'source': compiled.sent['source'], 'inputs': compiled.sent['inputs']})
        self.assertEqual(preview.status, 200, preview.sent)
        self.assertEqual(preview.sent['status'], 'paused', preview.sent)
        self.assertEqual(preview.sent['next']['name'], 'choice')
        self.assertEqual(preview.sent['next']['schema']['properties']['answer'],
                         {'type': 'integer', 'minimum': 1, 'maximum': 3})
        self.assertEqual(preview.sent['next']['context_manifest']['presentation'], 'compact')
        for command in COMMANDS:
            self.assertIn(command, preview.sent['next']['prompt'])
        self.assertEqual(body, original)
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])

    def test_run_and_result_return_exact_checked_value_with_original_request_bound(self):
        body = request(calls=1)
        body['params']['require_complete'] = True
        contract = D.compile_task(body)
        body['expected_contract_id'] = contract['contract_id']
        started = self.routed('POST', 'delegate/run', {'task': body})
        self.assertEqual(started.status, 200, started.sent)
        ident = started.sent['id']
        result = self.routed('GET', 'delegate/result', query={'id': ident})
        self.assertEqual(result.status, 200, result.sent)
        expected = {'choice': 3, 'command': COMMANDS[2], 'menu_member': True,
                    'inference': C.append(PREMISES, GOAL, prefix(), COMMANDS[2]), 'handoff': contract['handoff']}
        self.assertEqual(result.sent['result'], S.canon(S.from_json(expected)))
        self.assertTrue(result.sent['accepted'])
        self.assertEqual(result.sent['contract_id'], contract['contract_id'])
        self.assertNotIn('request', result.sent)
        self.assertEqual(result.sent['calls'], 1)
        self.assertEqual(self.apps.calls[0]['app']['spec'], H.LOCAL_LADDER[0])
        folder = Path(E.run_dir(ident))
        self.assertTrue(folder.is_relative_to(Path(self.tmp)))
        meta = json.loads((folder / 'meta.json').read_text())
        self.assertEqual(meta['delegation']['request'], body)
        self.assertIs(meta['options']['side_effects'], False)
        self.assertEqual(meta['options']['parallel'], 1)

    def test_nonowners_cannot_discover_compile_preview_run_or_read_with_forged_owner_header(self):
        identities = [SG.Identity(SG.ANONYMOUS), SG.Identity(SG.VERIFIED, 'guest@example.test'),
                      SG.Identity(SG.ANONYMOUS, 'owner@example.test')]
        routes = [('GET', 'delegate/catalog', None), ('POST', 'delegate/compile', request()),
                  ('POST', 'preview', {}), ('POST', 'delegate/run', {'task': request()}),
                  ('GET', 'delegate/result', None)]
        with patch.object(E, 'handle', side_effect=AssertionError('Unauthorized request reached Symblic')):
            for identity in identities:
                for method, route, body in routes:
                    with self.subTest(identity=identity.level, route=route):
                        response = self.routed(method, route, body, identity=identity)
                        self.assertEqual(response.status, 403)
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])
        self.assertEqual(list(Path(self.tmp).rglob('*')), [])

    def test_malformed_compile_run_requests_and_effect_override_refuse_before_launch(self):
        bad = request(); bad['params']['commands'] = ['and_left s99']
        broken = request(); broken['params']['session']['goal'] = ['atom', 'Changed']
        option = request(); option['side_effects'] = True
        for body in ({}, [], bad, broken, option):
            compiled = self.routed('POST', 'delegate/compile', body)
            self.assertEqual(compiled.status, 200)
            self.assertFalse(compiled.sent['ok'])
            started = self.routed('POST', 'delegate/run', {'task': body})
            self.assertEqual(started.status, 400, started.sent)
        for body in ({'task': request(), 'options': {'side_effects': True}},
                     {'task': request(), 'source': 'act notes.write(text="bad").'},
                     {'task': request(), 'by': ['fake:a', 'fake:a']}):
            self.assertEqual(self.routed('POST', 'delegate/run', body).status, 400)
        self.assertEqual(self.launches, [])
        self.assertEqual(self.apps.calls, [])

    def test_invalid_inference_exposes_no_accepted_result_and_partial_success_is_not_completion(self):
        for answer, accepted, complete in ((1, False, None), (2, True, False)):
            self.apps.answer = lambda _app, _prompt, answer=answer: {'answer': answer}
            started = self.routed('POST', 'delegate/run', {'task': request(calls=1)})
            self.assertEqual(started.status, 200, started.sent)
            result = self.routed('GET', 'delegate/result', query={'id': started.sent['id']})
            self.assertEqual(result.status, 200, result.sent)
            self.assertIs(result.sent['accepted'], accepted)
            if accepted:
                self.assertIs(result.sent['result']['inference']['complete'], complete)
                self.assertEqual(result.sent['assurance']['goal_closure'], 'not_required; inspect inference.complete')
            else:
                self.assertIsNone(result.sent['result'])

    def test_no_effect_policy_and_exact_menu_drift_refuse_result_and_resume_without_relaunch(self):
        started = self.routed('POST', 'delegate/run', {'task': request(calls=1)})
        self.assertEqual(started.status, 200, started.sent)
        ident = started.sent['id']; path = Path(E.run_dir(ident), 'meta.json')
        original = path.read_text(); before_launches = len(self.launches); before_calls = len(self.apps.calls)
        for field in ('side_effects', 'commands'):
            meta = json.loads(original)
            if field == 'side_effects':
                meta['options']['side_effects'] = True
            else:
                meta['inputs']['commands'].reverse()
            path.write_text(json.dumps(meta))
            read = self.routed('GET', 'delegate/result', query={'id': ident})
            resumed = self.routed('POST', 'resume', {'id': ident})
            self.assertEqual(read.status, 400, read.sent)
            self.assertEqual(resumed.status, 400, resumed.sent)
        self.assertEqual(len(self.launches), before_launches)
        self.assertEqual(len(self.apps.calls), before_calls)


if __name__ == '__main__':
    unittest.main()
