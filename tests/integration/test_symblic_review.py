"""Owned council lifecycle regressions: fake hub, fake clock, no real workers."""

import json
import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import host_council_run as ACR
    import host_agent_hub as AH
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

from symblic.providers import applicators as SA


class CouncilCleanup(unittest.TestCase):
    def setUp(self):
        self.app = SA.Applicators()
        self.calls = []
        self.view = {'summary': {'status': 'running'}, 'final': ''}
        self.hub_patch = patch.object(self.app, '_hub', side_effect=self.fake_hub)
        self.hub_patch.start()
        self.addCleanup(self.hub_patch.stop)

    def fake_hub(self, method, route, body=None, timeout=60):
        self.calls.append((method, route, body))
        if route == 'council/templates':
            return 200, {'templates': [{'id': 'panel', 'spec': {'fake': 'spec'}}]}
        if route == 'start':
            return 200, {'agent': {'id': 'owned-fake-council'}}
        if route == 'stop':
            return 200, {'ok': True}
        if route == 'council?id=owned-fake-council':
            return 200, self.view
        raise AssertionError('unexpected fake hub route: ' + route)

    def request(self, cancelled=False):
        if cancelled:
            stop = threading.Event()
            stop.set()
        else:
            stop = Mock()
            stop.wait.return_value = False
        return {'app': {'engine': 'council', 'model': 'panel'}, 'system': 'fixture system',
                'prompt': 'fixture prompt', 'stop': stop}

    def stopped_ids(self):
        return [body['id'] for method, route, body in self.calls if method == 'POST' and route == 'stop']

    def run_with_deadline(self, request):
        # First poll occurs immediately; the next loop observes expiry. No real sleep.
        with patch.object(SA.time, 'time', side_effect=[0, 0, SA.COUNCIL_TIMEOUT + 1]):
            return self.app._council(request)

    def test_terminal_failure_uses_actual_hub_summary_and_retires_owned_council(self):
        self.view = {'summary': {'status': 'failed', 'error': 'not enough valid votes'}, 'final': ''}
        result = self.run_with_deadline(self.request())
        self.assertFalse(result['ok'])
        self.assertIn('failed', result['error'])
        self.assertIn('not enough valid votes', result['error'])
        self.assertEqual(self.stopped_ids(), ['owned-fake-council'])

    def test_timeout_retires_only_the_council_it_started(self):
        result = self.run_with_deadline(self.request())
        self.assertFalse(result['ok'])
        self.assertIn('did not finish', result['error'])
        self.assertEqual(self.stopped_ids(), ['owned-fake-council'])

    def test_cancellation_retires_owned_council_without_polling_its_answers(self):
        result = self.run_with_deadline(self.request(cancelled=True))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'stopped')
        self.assertEqual(self.stopped_ids(), ['owned-fake-council'])
        self.assertFalse(any(route.startswith('council?id=') for _, route, _ in self.calls))

    def test_success_collects_final_answer_before_retiring_owned_council(self):
        self.view = {'summary': {'status': 'done'}, 'final': '{"answer": 8}'}
        result = self.run_with_deadline(self.request())
        self.assertTrue(result['ok'])
        self.assertEqual(result['json'], {'answer': 8})
        self.assertEqual(result['meta']['council'], 'owned-fake-council')
        self.assertEqual(self.stopped_ids(), ['owned-fake-council'])


class DetachedFleetCleanup(unittest.TestCase):
    def backend(self):
        runner = SimpleNamespace(id='owned-fake-council', stopping=threading.Event(),
                                 hub='http://fake.invalid', mark=Mock(), say=Mock())
        return runner, ACR.Backends(runner)

    def test_resumed_fleet_turn_is_tracked_and_cancelled_on_stop(self):
        runner, backend = self.backend()
        runner.stopping.set()
        with patch.object(backend, '_hub', return_value=(200, {'ok': True})) as hub:
            result = backend.fleet({'id': '0.0.0.r1', 'node': 'node-a', 'no': 1},
                                   run_id='owned-resumed-run')
            backend.cancel_all()
        self.assertEqual(result['error'], 'stopped')
        cancelled = [call.args[2]['run'] for call in hub.call_args_list
                     if call.args[:2] == ('POST', 'council/fleet/cancel')]
        self.assertEqual(set(cancelled), {'owned-resumed-run'})

    def test_stop_during_pending_launch_cancels_the_returned_owned_run(self):
        runner, backend = self.backend()
        launched = threading.Event()
        release_response = threading.Event()
        cancelled = []
        results = []
        errors = []

        def hub(method, route, body=None, timeout=60):
            if route == 'council/fleet':
                # The hub has launched a detached run, but its response is still in flight.
                launched.set()
                if not release_response.wait(2):
                    raise AssertionError('fake response not released')
                return 200, {'run': 'owned-late-run', 'node': 'node-a'}
            if route == 'council/fleet/cancel':
                cancelled.append(body['run'])
                return 200, {'ok': True}
            raise AssertionError('unexpected fake route: ' + route)

        def work():
            try:
                results.append(backend.fleet({'id': '0.0.0.r1', 'node': 'node-a', 'no': 1}))
            except Exception as exc:
                errors.append(exc)

        with patch.object(backend, '_hub', side_effect=hub):
            worker = threading.Thread(target=work, name='fake-pending-council-launch')
            worker.start()
            try:
                self.assertTrue(launched.wait(1), 'fake launch never reached the response barrier')
                runner.stopping.set()
                backend.cancel_all()
            finally:
                release_response.set()
                worker.join(3)
        self.assertFalse(worker.is_alive(), 'fake launch thread did not finish')
        self.assertEqual(errors, [])
        self.assertEqual(results[0]['error'], 'stopped')
        self.assertEqual(set(cancelled), {'owned-late-run'})


class DurableHubStop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='owned-council-stop-')
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'AGENTS_DATA_DIR': self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.cid = 'aaaaaaaa'
        self.folder = AH.council_dir(self.cid)
        os.makedirs(os.path.join(self.folder, 'turns'))
        self.spec = {'stages': [{'members': [{'engine': 'ollama', 'model': 'fake:1b', 'node': 'node-a'}]}]}
        self.save('spec.json', self.spec)
        self.save('state.json', {'status': 'running', 'turns': {}})
        self.save('meta.json', {'id': self.cid})
        self.save('fleet.json', {'owned_a': '0.0.0.r1', 'owned_b': '0.0.1.r1'})
        with open(os.path.join(self.folder, 'turns', '0.0.0.r1.prompt.md'), 'w') as f:
            f.write('fixture prompt')
        self.ba = SimpleNamespace(poll=Mock(return_value={'status': 'running'}),
                                  cancel=Mock(return_value=True),
                                  launch=Mock(return_value={'id': 'unexpected-new-run', 'status': 'running'}))
        self.row = {'id': self.cid, 'engine': 'council', 'node': 'node-local'}
        self.patchers = [patch.object(AH, '_find', return_value=self.row),
                         patch.object(AH, '_keep_history'), patch.object(AH, '_tmux',
                             return_value=SimpleNamespace(returncode=0, stdout='', stderr='')),
                         patch.object(AH, '_session', return_value='isolated-fake-session'),
                         patch.object(AH, '_import', side_effect=lambda name: {
                             'host_agents': self.ba, 'host_fleet': SimpleNamespace()}.get(name))]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)

    def save(self, name, value):
        with open(os.path.join(self.folder, name), 'w') as f:
            json.dump(value, f)

    def test_stop_cancels_durable_owned_receipts_without_a_live_runner(self):
        foreign = AH.council_dir('bbbbbbbb')
        os.makedirs(foreign)
        with open(os.path.join(foreign, 'fleet.json'), 'w') as f:
            json.dump({'unrelated_run': '0.0.0.r1'}, f)
        self.assertEqual(AH.stop(self.cid), {'ok': True})
        cancelled = {call.args[0]['id'] for call in self.ba.cancel.call_args_list}
        self.assertEqual(cancelled, {'owned_a', 'owned_b'})

    def test_tmux_stop_failure_still_sweeps_detached_owned_fleet_runs(self):
        with patch.object(AH, '_tmux', side_effect=TimeoutError('fake tmux did not answer')):
            try:
                AH.stop(self.cid)
            except TimeoutError:
                pass
        cancelled = {call.args[0]['id'] for call in self.ba.cancel.call_args_list}
        self.assertEqual(cancelled, {'owned_a', 'owned_b'})

    def test_stop_closes_admission_before_another_owned_fleet_turn_can_launch(self):
        AH.stop(self.cid)
        with self.assertRaises(AH.AgentError):
            AH.council_fleet_start({'id': self.cid, 'turn': '0.0.0.r1'})
        self.ba.launch.assert_not_called()


class RunnerCrashCleanup(unittest.TestCase):
    def test_recovery_failure_still_cancels_resumed_owned_backends(self):
        runner = object.__new__(ACR.Runner)
        runner.stopping = threading.Event()
        runner.header = Mock()
        runner.recover = Mock(side_effect=RuntimeError('fake recovery save failure'))
        runner.backends = Mock()
        with patch.object(ACR.signal, 'signal'):
            try:
                runner.run()
            except RuntimeError:
                pass
        runner.backends.cancel_all.assert_called()

    def test_unexpected_controller_failure_still_cancels_owned_backends(self):
        # No files, subprocesses, providers or worker threads are started by this runner.
        runner = object.__new__(ACR.Runner)
        runner.stopping = threading.Event()
        runner.header = Mock()
        runner.recover = Mock()
        runner.save = Mock()
        runner.say = Mock()
        runner.lock = threading.RLock()
        runner.spec = {}
        runner.state = {'status': 'running', 'stage': 0, 'round': 1}
        runner.task = 'fixture'
        runner.context = ''
        runner.folder = '/fake/checkout'
        runner.backends = Mock()
        with patch.object(ACR.signal, 'signal'), patch.object(ACR.ac, 'advance',
                                                          side_effect=RuntimeError('fake controller failure')):
            try:
                runner.run()
            except RuntimeError:
                pass
        runner.backends.cancel_all.assert_called()


if __name__ == '__main__':
    unittest.main()
