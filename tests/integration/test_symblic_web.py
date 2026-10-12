"""Admitted typed browser requests with fake transports and temporary ledgers only.

HOST-ONLY: integration/host/symblic_web.py pins the source of the host's browser-automation runtime
(integrations/chatgpt-browser/chatgpt.js and typed-requests.cjs next to the module), which is not part of this
repository, so the module is skipped when those files are absent.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from symblic.providers import applicators as symblic_apply
from integration.host import symblic_web as W

_RUNTIME = Path(W.__file__).parent / 'integrations' / 'chatgpt-browser'
if not ((_RUNTIME / 'chatgpt.js').is_file() and (_RUNTIME / 'typed-requests.cjs').is_file()):
    raise unittest.SkipTest("host-only test: needs the host's browser-automation runtime "
                            '(integrations/chatgpt-browser/), which is not part of this repository')


def request(**changes):
    body = {'app': {'engine': 'gemini', 'model': 'thinking', 'node': 'node-f'}, 'system': 'Propose only. Exact 800 px.',
            'prompt': 'Keep "snake/src/state.js" and emoji 🐍 unchanged.', 'schema': {'type': 'object'}, 'sample': 0}
    body.update(changes)
    return body


class BrowserFixture:
    def __init__(self, states=('completed',)):
        self.calls = []; self.states = list(states); self.body = None

    def __call__(self, node, operation, body):
        self.calls.append((node, operation, body))
        if operation == 'start':
            self.body = dict(body)
        row = {k: self.body[k] for k in ('id', 'site', 'model')}
        row.update(sha256=W.digest(self.body), status=self.states.pop(0), source_sha256=W.source_hash(), accepted=True)
        if row['status'] == 'completed':
            row.update(response='{"answer":"exact"}', modelSelection={'requested': self.body['model'], 'status': 'visible_mode'})
        return {'ok': True, 'protocol': 1, 'source_sha256': W.source_hash(), 'request': row}


class TypedBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='typed-browser-')
        self.addCleanup(self.tmp.cleanup)
        self.events = []

    def call(self, req=None, send=None, admission=None):
        return W.call(req or request(), run_id='fixture-run', root=self.tmp.name,
                      send=send or BrowserFixture(), admission=admission or (lambda node: self.events.append(('hold', node))),
                      check_host=False, poll_seconds=0)

    def test_exact_request_schema_node_and_tool_free_reply_are_retained(self):
        fake = BrowserFixture(); reply = self.call(send=fake)
        self.assertTrue(reply['ok'], reply)
        self.assertEqual(reply['node'], 'node-f')
        self.assertEqual(reply['json'], {'answer': 'exact'})
        self.assertEqual(self.events, [('hold', 'node-f')])
        sent = fake.calls[0][2]
        self.assertIn(request()['prompt'], sent['fullPrompt'])
        self.assertIn(request()['system'], sent['fullPrompt'])
        self.assertIn('"type":"object"', sent['fullPrompt'])
        self.assertEqual(set(sent), {'id', 'site', 'model', 'fullPrompt'})
        self.assertNotIn('uploadPath', sent)
        self.assertEqual(reply['meta']['protocol_source_sha256'], W.source_hash())
        row = json.loads(next(Path(self.tmp.name).glob('*.json')).read_text())
        self.assertEqual(row['reply'], reply)

    def test_dispatch_intent_precedes_transport_and_same_request_never_replays(self):
        fixture = BrowserFixture()
        def send(node, operation, body):
            row = json.loads((Path(self.tmp.name) / (body['id'] + '.json')).read_text())
            self.assertEqual(row['status'], 'dispatching')
            self.assertEqual(self.events, [('hold', node)])
            return fixture(node, operation, body)
        first = self.call(send=send)
        second = self.call(send=lambda *_: self.fail('No second dispatch'), admission=lambda _: self.fail('No second admission'))
        self.assertEqual(first, second)
        self.assertEqual(len(fixture.calls), 1)

    def test_lost_start_ack_is_unknown_and_reconnect_only_observes_same_id(self):
        fixture = BrowserFixture(('completed',))
        def lost(node, operation, body):
            fixture.body = body
            raise TimeoutError('lost start acknowledgement')
        first = self.call(send=lost)
        self.assertFalse(first['ok']); self.assertTrue(first['meta']['hold_retained'])
        result = self.call(send=fixture, admission=lambda _: self.fail('No repeat admission'))
        self.assertTrue(result['ok'])
        self.assertEqual([row[1] for row in fixture.calls], ['status'])

    def test_cancel_targets_only_the_exact_retained_request(self):
        stop = threading.Event()
        fixture = BrowserFixture(('running', 'cancelled'))
        def send(*args):
            result = fixture(*args); stop.set(); return result
        result = self.call(request(stop=stop), send=send)
        self.assertFalse(result['ok'])
        self.assertEqual([row[1] for row in fixture.calls], ['start', 'cancel'])
        reference = fixture.calls[1][2]
        self.assertEqual(reference['id'], fixture.body['id'])
        self.assertEqual(reference['sha256'], W.digest(fixture.body))
        self.assertNotIn('/stop', str(fixture.calls))

    def test_fence_refuses_before_transport_and_retains_explicit_non_admission(self):
        def blocked(node):
            self.assertEqual(len(list(Path(self.tmp.name).glob('*.json'))), 1)
            raise ValueError('Node is fenced')
        result = self.call(admission=blocked, send=lambda *_: self.fail('No transport behind fence'))
        self.assertFalse(result['ok']); self.assertIs(result['accepted'], False)

    def test_status_and_cancel_auth_errors_do_not_erase_prior_admission(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as folder:
                fixture = BrowserFixture(('running',)); stop = threading.Event()
                def send(node, operation, body):
                    if operation == 'start':
                        result = fixture(node, operation, body)
                        if cancel: stop.set()
                        return result
                    return {'ok': False, 'accepted': False, 'error': 'Missing daemon token'}
                result = W.call(request(stop=stop), run_id='fixture', root=folder, send=send,
                                admission=lambda _: None, check_host=False, poll_seconds=0)
                self.assertFalse(result['ok']); self.assertIsNone(result['accepted'])
                row = json.loads(next(Path(folder).glob('*.json')).read_text())
                self.assertEqual(row['status'], 'unknown')

    def test_protocol_source_and_exact_identity_mismatch_refuse(self):
        for change in ('source', 'site', 'model', 'hash'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                fixture = BrowserFixture()
                def send(*args):
                    out = fixture(*args)
                    if change == 'source': out['source_sha256'] = '0' * 64
                    elif change == 'hash': out['request']['sha256'] = '0' * 64
                    else: out['request'][change] = 'wrong'
                    return out
                result = W.call(request(), run_id='fixture', root=folder, send=send, admission=lambda _: None, check_host=False)
                self.assertFalse(result['ok']); self.assertEqual(result['meta']['status'], 'unknown')

    def test_no_install_no_signin_old_protocol_are_visible_without_fallback(self):
        result = self.call(send=lambda *_: {'ok': False, 'accepted': False, 'error': 'Update the idle runtime; no prompt was sent'})
        self.assertIs(result['accepted'], False)
        self.assertIn('Update', result['error'])
        self.assertEqual(len(self.events), 1)

    def test_adapter_passes_stop_and_exact_app_to_new_lane(self):
        apps = symblic_apply.Applicators(run_id='fixture', thermal=False)
        req = request(stop=threading.Event())
        with patch('symblic_web.call', return_value={'ok': True, 'json': {'a': 1}}) as call:
            out = apps._web(req)
        self.assertTrue(out['ok'])
        call.assert_called_once_with({**req, 'effort': ''}, run_id='fixture')

    def test_native_run_host_effort_reaches_real_tool_free_adapter_without_becoming_provider_effort(self):
        from symblic.kernel import run as R
        fixture = BrowserFixture(('completed',) * 5)
        def send(*args):
            out = fixture(*args); out['request']['response'] = '{"answer":8}'; return out
        actual_call = W.call
        def isolated(req, *, run_id):
            return actual_call(req, run_id=run_id, root=Path(self.tmp.name) / 'web', send=send,
                               admission=lambda _: None, check_host=False, poll_seconds=0)
        with patch('symblic_web.call', side_effect=isolated):
            run = R.Run('ask x: Int "Return eight." with effort=medium, votes=1\nshow x.\n',
                        applicators=symblic_apply.Applicators(run_id='native-fixture', thermal=False),
                        options={'by': 'gemini:thinking@node-f', 'parallel': 1, 'max_calls': 5, 'side_effects': False},
                        folder=str(Path(self.tmp.name) / 'native'))
            result = run.execute()
        self.assertEqual(result['status'], 'done', result)
        self.assertTrue(fixture.calls)
        self.assertTrue(all(row[0] == 'node-f' for row in fixture.calls))

    def test_historical_receipt_and_cached_reply_do_not_claim_current_protocol(self):
        fixture = BrowserFixture()
        result = self.call(send=fixture)
        self.assertTrue(result['ok'])
        with patch('symblic_web.source_hash', return_value='0' * 64):
            historical = self.call(send=lambda *_: self.fail('Historical cache is not replayed'))
        self.assertFalse(historical['ok']); self.assertIn('historical evidence', historical['error'])
        with tempfile.TemporaryDirectory() as folder:
            def old_receipt(*args):
                out = BrowserFixture()(*args); out['request']['source_sha256'] = '0' * 64; return out
            bad = W.call(request(), run_id='fixture', root=folder, send=old_receipt, admission=lambda _: None, check_host=False)
            self.assertFalse(bad['ok'])

    def test_native_run_initial_refusal_refunds_model_budget(self):
        from symblic.kernel import run as R
        actual_call = W.call
        calls = []
        def send(node, operation, body):
            calls.append(operation)
            return {'ok': False, 'accepted': False, 'error': 'Installed runtime protocol is too old'}
        def isolated(req, *, run_id):
            return actual_call(req, run_id=run_id, root=Path(self.tmp.name) / 'web', send=send,
                               admission=lambda _: None, check_host=False, poll_seconds=0)
        with patch('symblic_web.call', side_effect=isolated):
            run = R.Run('ask x: Int "Return eight." with effort=medium, votes=1\nshow x.\n',
                        applicators=symblic_apply.Applicators(run_id='refusal-fixture', thermal=False),
                        options={'by': 'gemini:thinking@node-f', 'parallel': 1, 'max_calls': 1, 'side_effects': False},
                        folder=str(Path(self.tmp.name) / 'native-refusal'))
            result = run.execute()
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 0, result)
        self.assertEqual(calls, ['start'])

    def test_unsupported_effort_context_size_and_fields_refuse_before_transport(self):
        for req in (request(effort='high'), request(prompt='🐍' * 51000), request(app={'engine': 'gemini', 'model': 'x', 'node': 'auto'})):
            with self.subTest(req=str(req)[:100]), self.assertRaises(ValueError):
                self.call(req, send=lambda *_: self.fail('No transport'))

    def test_remote_transport_is_fixed_code_with_stdin_and_installed_protocol_guard(self):
        body = {'id': 'a' * 32, 'site': 'chatgpt', 'model': '', 'fullPrompt': '$(touch /tmp/NEVER) `whoami`'}
        with patch.dict(os.environ, DASH_TEST='0'), patch('host_agent_hub._on_node', return_value=subprocess.CompletedProcess([], 0, '{"ok":false,"accepted":false}', '')) as run:
            W.transport('node-f', 'start', body)
        args, kwargs = run.call_args
        self.assertEqual(args[0], 'node-f')
        self.assertNotIn(body['fullPrompt'], args[1])
        self.assertIn('TYPED_VERSION', args[1]); self.assertIn('TYPED_SOURCE_SHA256', args[1])
        self.assertIn('integrations/chatgpt-browser/chatgpt.js', args[1])
        self.assertEqual(json.loads(kwargs['stdin'])['request'], body)

    def test_real_transport_disabled_under_test_guard(self):
        with patch.dict(os.environ, DASH_TEST='1'), self.assertRaises(RuntimeError):
            W.transport('node-f', 'start', {})

    def test_browser_admission_reuses_existing_hold_and_install_epoch(self):
        with patch('host_browser_hub.web_node', return_value='node-f'), patch('host_browser_hub._hold') as held:
            W.admit('node-f')
        held.assert_called_once_with('node-f', 'browser')


if __name__ == '__main__':
    unittest.main()
