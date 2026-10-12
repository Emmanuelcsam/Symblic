"""Projected proof context through real CLI/API routing, with fake providers."""
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
from symblic.providers import applicators as symblic_apply
from symblic.delegate import contracts as D
from symblic.adapters import proof_command as C
from tests.delegate.test_symblic_delegate_proof_focus import PARENT, prefix, task
from tests.integration.test_symblic_proof_step_entry import RoutedHandler, cli


HIDDEN = 'UNREFERENCED_PREMISE_46801'


def request(capsule='full'):
    a, b = ['atom', 'A'], ['atom', 'B']
    state = prefix({'a': a, 'ab': ['implies', a, b], 'noise': ['atom', HIDDEN]},
                   ['premise noise', 'premise a', 'premise ab'], goal=b)
    body = task(state, ['and_left s2', 'premise a', 'implies_elim s3 s2'], '"B"', capsule=capsule)
    body['params']['require_complete'] = True
    return body


class ProofFocusCLI(unittest.TestCase):
    def test_focused_discovery_and_full_compact_compilation_need_no_provider(self):
        with patch.object(symblic_apply, 'Applicators', side_effect=AssertionError('Read-only CLI made provider')):
            code, text, _ = cli(['catalog', '--template', 'proof_step_focus', '--agent-json'])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text), D.catalog('proof_step_focus'))
            for capsule in ('full', 'compact'):
                body = request(capsule)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory, 'task.json'); path.write_text(json.dumps(body))
                    code, text, _ = cli(['check', str(path), '--agent-json'])
                self.assertEqual(code, 0, text)
                compiled = json.loads(text)
                self.assertEqual(compiled, {'ok': True, **D.compile_task(body)})
                self.assertEqual([row['id'] for row in compiled['inputs']['focused_frontier']['lines']], ['s2', 's3'])


class ProofFocusAPI(Base):
    def setUp(self):
        super().setUp()
        for target in (patch.dict(host_apps._modules, {'automation_engine': AE}),
                       patch.object(AE, '_ensure_started', side_effect=AssertionError('No scheduler')),
                       patch.object(SG, 'OWNER_EMAILS', {'owner@example.test'})):
            target.start(); self.addCleanup(target.stop)
        self.apps.answer = lambda _app, _prompt: {'answer': 3}

    def routed(self, method, route, data=None, query=None):
        handler = RoutedHandler(route, query)
        handled = host_apps.handle_get(handler) if method == 'GET' else host_apps.handle_post(handler, data)
        self.assertTrue(handled)
        return handler

    def test_preview_omits_unreferenced_history_but_run_and_parent_retain_full_checked_state(self):
        for capsule in ('full', 'compact'):
            body = request(capsule)
            compiled = self.routed('POST', 'delegate/compile', body)
            self.assertEqual(compiled.status, 200)
            self.assertTrue(compiled.sent['ok'])
            with patch.object(C, 'append', side_effect=AssertionError('Preview evaluated a menu option')):
                preview = self.routed('POST', 'preview', {'source': compiled.sent['source'],
                                                         'inputs': compiled.sent['inputs']})
            self.assertEqual(preview.status, 200, preview.sent)
            self.assertEqual(preview.sent['status'], 'paused')
            surface = preview.sent['next']
            self.assertNotIn(HIDDEN, surface['prompt'])
            self.assertIn('implies_elim s3 s2', surface['prompt'])
            self.assertIn('omitted_lines', surface['prompt'])
            self.assertEqual(surface['schema']['properties']['answer'], {'type': 'integer', 'minimum': 1, 'maximum': 3})
            body['expected_contract_id'] = compiled.sent['contract_id']
            started = self.routed('POST', 'delegate/run', {'task': body})
            self.assertEqual(started.status, 200, started.sent)
            result = self.routed('GET', 'delegate/result', query={'id': started.sent['id']})
            self.assertEqual(result.status, 200, result.sent)
            self.assertTrue(result.sent['accepted'], result.sent)
            self.assertEqual(result.sent['calls'], 1)
            state = PARENT.checked_child_state(body, result.sent)
            self.assertEqual(state['steps'][:-1], body['params']['session']['steps'])
            self.assertEqual(len(state['steps']), 4)
            self.assertEqual(state['premises']['noise'], ['atom', HIDDEN])
            self.assertEqual(result.sent['result']['handoff']['projection'], compiled.sent['handoff']['projection'])
            self.assertNotIn(HIDDEN, self.apps.calls[-1]['prompt'])
        self.assertEqual(len(self.apps.calls), 2)

    def test_caller_cannot_override_projection_or_run_with_forged_full_prefix(self):
        body = request(); body['params']['focused_frontier'] = {}
        forged = request(); forged['params']['session']['steps'][0]['args'] = ['missing']
        for candidate in (body, forged):
            for route, envelope in (('delegate/compile', candidate), ('delegate/run', {'task': candidate})):
                response = self.routed('POST', route, envelope)
                self.assertFalse(response.sent.get('ok', False), response.sent)
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])
        self.assertEqual(list(Path(self.tmp).rglob('*')), [])

    def test_persisted_projection_drift_refuses_result_resume_and_child_tampering(self):
        body = request()
        started = self.routed('POST', 'delegate/run', {'task': body})
        ident = started.sent['id']
        result = self.routed('GET', 'delegate/result', query={'id': ident})
        self.assertTrue(result.sent['accepted'], result.sent)
        changed = copy.deepcopy(result.sent)
        changed['result']['handoff']['projection']['view_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            PARENT.checked_child_state(body, changed)
        path = Path(E.run_dir(ident), 'meta.json')
        meta = json.loads(path.read_text())
        meta['inputs']['focused_frontier']['lines'] = []
        path.write_text(json.dumps(meta))
        before = len(self.launches), len(self.apps.calls)
        for method, route, data, query in (('GET', 'delegate/result', None, {'id': ident}),
                                          ('POST', 'resume', {'id': ident}, None)):
            response = self.routed(method, route, data, query)
            self.assertEqual(response.status, 400, response.sent)
        self.assertEqual((len(self.launches), len(self.apps.calls)), before)


if __name__ == '__main__':
    unittest.main()
