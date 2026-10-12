"""Graph repair regressions of the original host's graph job runner.

These cases drive integration/host/symblic_graph_api.py (start, view, resume and stop of graph jobs, launch
generations, worker leases, signal handling) with the fake store in fake_host_apps.py standing in for the host's
run store, so they run without the host. The executor-level regressions of the same review are in
tests/graph/test_symblic_graph_repair.py. Fake applicators, launchers and signal handlers; temporary stores.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_graph_api as A
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

from symblic.graph import planner as G
from symblic.graph import run as R
from tests.graph.test_symblic_graph_repair import STOPPED, Isolated, answering
from tests.graph.test_symblic_graph_run import Crash, FakeApps, Host, graph, node


from tests.integration import fake_host_apps  # noqa: E402

# The host's store, faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()

# Upper bound for a worker thread to reach the fake provider, finish, or be released. An event that is already
# set returns at once, so a generous bound costs nothing when the machine is idle; 10 s was too short on a
# machine with a load average of 15 to 18.
WAIT = 120


class ApiHarness(Isolated):
    def setUp(self):
        super().setUp()
        env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': str(self.root / 'data')})
        env.start()
        self.addCleanup(env.stop)
        self.pending = []
        self.active = False
        hooks = patch.dict(A.launcher, {'launch': self.defer, 'active': lambda _: self.active, 'stop': lambda _: True})
        hooks.start()
        self.addCleanup(hooks.stop)
        body = A.example()
        self.body = {key: body[key] for key in ('graph', 'policy')}
        measure = self.body['graph']['nodes'][0]
        measure.update(source='use profile=verified.\nask answer: Int "Return six." with retries=0.',
                       call_limit=2, max_calls=2)
        self.body['graph']['max_calls'] = 3

    def defer(self, ident, folder, generation):
        self.pending.append((ident, Path(folder), generation))
        return {'ok': True}

    def started(self):
        ident = A.start(self.body)['id']
        _, folder, generation = self.pending[-1]
        return ident, folder, generation


class SignalsAndOwnerStops(ApiHarness):
    """graph-3: only the owner's persisted Stop cancels; a bare signal interrupts resumably."""

    def test_signal_without_owner_marker_leaves_a_resumable_run(self):
        ident, folder, generation = self.started()
        event = threading.Event()
        apps = answering(6, first=lambda request: event.set() or dict(STOPPED))
        self.assertEqual(A.run_job(folder, applicators=apps, stop_event=event, generation=generation)['status'], 'stopped')
        runtime = folder / 'runtime'
        self.assertNotIn('cancel', self.kinds(runtime))
        view = A.view(ident)
        self.assertEqual(view['state']['status'], 'stopped')
        self.assertTrue(view['can_resume'])
        self.assertNotIn('terminal', A.resume(ident))
        _, _, current = self.pending[-1]
        self.assertNotEqual(current, generation)
        state = A.run_job(folder, applicators=apps, generation=current)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(A.view(ident)['state']['status'], 'succeeded')
        self.assertEqual(A.read_job(folder)['reserved_calls'], 3)

    def test_owner_stop_during_call_is_a_durable_cancel(self):
        ident, folder, generation = self.started()
        event = threading.Event()

        def owner_stop(request):
            A.stop(ident)  # persists the marker; the unit stop then signals the worker
            event.set()
            return dict(STOPPED)
        apps = answering(6, first=owner_stop)
        self.assertEqual(A.run_job(folder, applicators=apps, stop_event=event, generation=generation)['status'], 'canceled')
        self.assertEqual(self.kinds(folder / 'runtime'), ['started', 'cancel'])
        view = A.view(ident)
        self.assertEqual(view['state']['status'], 'canceled')
        self.assertFalse(view['can_resume'])
        self.assertTrue(A.resume(ident)['terminal'])
        self.assertEqual(len(apps.calls), 1)

    def test_worker_main_signal_handler_interrupts_instead_of_canceling(self):
        ident, folder, generation = self.started()
        handlers = {}

        class Applicators:
            made = []

            def __init__(self, **_options):
                self.calls, self.canceled = [], 0
                Applicators.made.append(self)

            def call(self, request):
                self.calls.append(request)
                if len(self.calls) == 1:
                    handlers[signal.SIGTERM](signal.SIGTERM, None)  # e.g. host shutdown
                    return dict(STOPPED)
                return {'ok': True, 'json': {'answer': 6}, 'model': request['app']['model'],
                        'node': request['app']['node'], 'ms': 0}

            def cancel_all(self):
                self.canceled += 1
                return 1

        argv = ['symblic_graph_api.py', 'job', '--id', ident, '--folder', str(folder), '--generation', generation]
        with patch('symblic.providers.applicators.Applicators', Applicators), patch.object(sys, 'argv', argv), \
                patch.object(A.signal, 'signal', side_effect=lambda number, handler: handlers.update({number: handler})):
            A.main()
        self.assertEqual(set(handlers), {signal.SIGTERM, signal.SIGINT})
        self.assertEqual(Applicators.made[0].canceled, 1)
        self.assertNotIn('cancel', self.kinds(folder / 'runtime'))
        self.assertFalse((folder / ('.cancel-' + generation)).exists())
        view = A.view(ident)
        self.assertEqual((view['state']['status'], view['can_resume']), ('stopped', True))

    def test_non_final_job_stop_interrupts_policy_style_runs(self):
        # begin_job defaults to non-final stops (the policy lane): an owner Stop of the
        # experiment must not permanently cancel the assignment graph it interrupts.
        folder = self.root / 'job'
        folder.mkdir(mode=0o700)
        A._save(folder, 'job.json', {'status': 'starting', 'generation': 'a' * 24, 'updated': 0})
        stop, generation = A.begin_job(folder, 'a' * 24, threading.Event())
        frozen = graph(node('A'))

        def owner_stop(request):
            (folder / ('.cancel-' + generation)).write_text('{}')
            return dict(STOPPED)
        apps = answering(2, first=owner_stop)
        with self.assertRaises(R.Interrupted):
            R.GraphRun(frozen, folder / 'runtime', apps, stop=stop).execute()
        self.assertEqual(self.kinds(folder / 'runtime'), ['started'])
        stop.release()
        A._save(folder, 'job.json', {'status': 'starting', 'generation': 'b' * 24, 'updated': 0})
        resumed, _ = A.begin_job(folder, 'b' * 24, threading.Event())
        try:
            state = R.GraphRun(frozen, folder / 'runtime', apps, stop=resumed).execute()
        finally:
            resumed.release()
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 2)


class GenerationFence(ApiHarness):
    """graph-2 and the dispatch gap: generation ownership is a lease held while the worker lives."""

    def blocking(self):
        entered, release = threading.Event(), threading.Event()

        def first(request):
            entered.set()
            if not release.wait(WAIT):
                raise AssertionError('test did not release the fake provider')
            return {'ok': True, 'json': {'answer': 6}, 'model': request['app']['model'],
                    'node': request['app']['node'], 'ms': 0}
        return answering(6, first=first), entered, release

    def worker(self, folder, apps, generation):
        outcome = {}
        thread = threading.Thread(target=lambda: outcome.update(
            result=A.run_job(folder, applicators=apps, generation=generation)))
        thread.start()
        return thread, outcome

    def test_live_worker_cannot_be_superseded_even_when_liveness_misreports(self):
        ident, folder, old = self.started()
        apps, entered, release = self.blocking()
        thread, outcome = self.worker(folder, apps, old)
        self.assertTrue(entered.wait(WAIT))
        self.assertTrue(A.worker_alive(folder))
        self.assertTrue(A.launch_job(ident, folder, A.launcher)['already_active'])  # the probe said inactive
        view = A.view(ident)
        self.assertEqual((view['active'], view['can_resume']), (True, False))
        self.assertEqual(A.read_job(folder)['generation'], old)
        release.set()
        thread.join(WAIT)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome['result']['status'], 'succeeded')
        self.assertFalse(A.worker_alive(folder))
        self.assertEqual(len(apps.calls), 1)

    def test_resume_in_the_admission_to_dispatch_gap_is_refused_for_calls_and_effects(self):
        ident, folder, old = self.started()
        seen = []

        def first(request):  # runs after the intent was admitted under the fence
            seen.extend([A.launch_job(ident, folder, A.launcher), A.read_job(folder)['generation']])
            return {'ok': True, 'json': {'answer': 6}, 'model': request['app']['model'],
                    'node': request['app']['node'], 'ms': 0}
        state = A.run_job(folder, applicators=answering(6, first=first), generation=old)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual((seen[0].get('already_active'), seen[1]), (True, old))
        job = self.root / 'effect-job'
        job.mkdir(mode=0o700)
        A._save(job, 'job.json', {'status': 'starting', 'generation': 'c' * 24, 'updated': 0})
        stop, _ = A.begin_job(job, 'c' * 24, threading.Event(), final=True)
        observed = []

        class GapHost(Host):
            def perform(self, effect, signal_stop):  # FX intent written and admitted under the fence
                observed.append(A.launch_job('0123456789ab', job, {**A.launcher, 'active': lambda _: False}))
                return super().perform(effect, signal_stop)
        host = GapHost()
        try:
            state = R.GraphRun(graph(node('A', source='act answer: Int = fixture.write().', effect_risk='write')),
                               job / 'runtime', FakeApps(), stop=stop, effects=host).execute()
        finally:
            stop.release()
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertTrue(observed[0]['already_active'])
        self.assertEqual(A.read_job(job)['generation'], 'c' * 24)
        self.assertEqual(len(host.calls), 1)

    def test_forced_generation_swap_ends_the_old_worker_and_keeps_its_receipts(self):
        # Defense in depth against a generation written without launch_job: the
        # admitted call completes and keeps its receipt; nothing after it is sent or committed.
        ident, folder, old = self.started()
        new = 'f' * 24

        def first(request):
            A._save(folder, 'job.json', {**A.read_job(folder), 'generation': new, 'status': 'starting'})
            return {'ok': True, 'json': {'answer': 6}, 'model': request['app']['model'],
                    'node': request['app']['node'], 'ms': 0}
        apps = answering(6, first=first)
        self.assertEqual(A.run_job(folder, applicators=apps, generation=old)['status'], 'superseded')
        runtime = folder / 'runtime'
        self.assertEqual(self.kinds(runtime), ['started'])
        self.assertEqual(self.journal(runtime, 'Iter000_Measure_Attempt01'), ['intent', 'outcome'])
        self.assertFalse((runtime / 'attempts' / 'Iter000_Measure_Attempt01' / 'graph-result.json').exists())
        self.assertFalse(A.worker_alive(folder))
        state = A.run_job(folder, applicators=apps, generation=new)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 1)  # replayed from the old worker's receipt

    def test_stale_cancel_after_a_forced_swap_is_never_appended(self):
        ident, folder, old = self.started()
        new = 'e' * 24

        def first(request):
            (folder / ('.cancel-' + old)).write_text('{}')  # the owner's Stop of the old generation
            A._save(folder, 'job.json', {**A.read_job(folder), 'generation': new, 'status': 'starting'})
            return {'ok': True, 'json': {'answer': 6}, 'model': request['app']['model'],
                    'node': request['app']['node'], 'ms': 0}
        apps = answering(6, first=first)
        self.assertEqual(A.run_job(folder, applicators=apps, generation=old)['status'], 'superseded')
        self.assertNotIn('cancel', self.kinds(folder / 'runtime'))
        state = A.run_job(folder, applicators=apps, generation=new)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 1)

    def test_owner_stop_of_a_live_worker_waits_for_it_and_resume_stays_terminal(self):
        ident, folder, old = self.started()
        apps, entered, release = self.blocking()
        thread, outcome = self.worker(folder, apps, old)
        self.assertTrue(entered.wait(WAIT))

        def stop_unit(_ident):  # systemd stops the unit: the worker sees its marker and ends
            release.set()
            thread.join(WAIT)
            return True
        with patch.dict(A.launcher, {'stop': stop_unit}):
            self.assertTrue(A.stop(ident)['ok'])
        self.assertEqual(outcome['result']['status'], 'canceled')
        self.assertEqual(self.kinds(folder / 'runtime')[-1], 'cancel')
        self.assertTrue(A.resume(ident)['terminal'])

    def test_stop_reported_done_only_after_the_worker_released_its_lease(self):
        ident, folder, old = self.started()
        apps, entered, release = self.blocking()
        thread, outcome = self.worker(folder, apps, old)
        self.assertTrue(entered.wait(WAIT))
        with patch.dict(A.launcher, {'stop': lambda _: True}), patch.object(A, 'STOP_CONFIRM_WAIT', 0.2):
            with self.assertRaises(A.ApiError) as refused:
                A.stop(ident)  # the unit stop claimed success but the worker still runs
        self.assertEqual(refused.exception.status, 503)
        self.assertEqual(A.read_job(folder)['status'], 'stopping')
        release.set()
        thread.join(WAIT)
        self.assertEqual(outcome['result']['status'], 'canceled')

    def test_unknown_liveness_counts_as_active(self):
        for failure in (subprocess.TimeoutExpired('systemctl', 10), OSError('fork failed')):
            with patch.object(A.subprocess, 'run', side_effect=failure):
                self.assertTrue(A._active('0123456789ab'))
        for output, active in (('active\n', True), ('deactivating\n', True), ('inactive\n', False),
                               ('failed\n', False), ('', True)):
            reply = subprocess.CompletedProcess([], 3, output, '')
            with patch.object(A.subprocess, 'run', return_value=reply):
                self.assertEqual(A._active('0123456789ab'), active, output)
        ident, folder, generation = self.started()
        A._save(folder, 'job.json', {**A.read_job(folder), 'status': 'running', 'updated': 0})
        with patch.dict(A.launcher, {'active': A._active}), \
                patch.object(A.subprocess, 'run', side_effect=subprocess.TimeoutExpired('systemctl', 10)):
            self.assertTrue(A.launch_job(ident, folder, A.launcher)['already_active'])
            self.assertFalse(A.view(ident)['can_resume'])
        self.assertEqual(A.read_job(folder)['generation'], generation)


class StaleStop(ApiHarness):
    """An old Stop's signal to the stable unit name can never reach a newer generation."""

    def test_resume_waits_until_the_stop_signal_has_settled(self):
        ident, folder, old = self.started()
        probes, attempts, signalled = [], [], []

        def active(_ident):  # the unit looks active when Stop checks, and is gone right after
            probes.append(1)
            return len(probes) == 1

        def stop_unit(_ident):  # the signal is in flight: a concurrent Resume arrives now
            try:
                attempts.append(A.resume(ident))
            except A.ApiError as error:
                attempts.append(error.status)
            signalled.append(A.read_job(folder)['generation'])
            return True
        with patch.dict(A.launcher, {'active': active, 'stop': stop_unit}):
            self.assertTrue(A.stop(ident)['ok'])
        self.assertEqual(attempts, [409])
        self.assertEqual(signalled, [old])  # the signal reached only the generation it stopped
        self.assertFalse(A.stop_settling(folder))
        A.resume(ident)
        _, _, current = self.pending[-1]
        self.assertNotEqual(current, old)
        state = A.run_job(folder, applicators=answering(6), generation=current)
        self.assertEqual(state['status'], 'succeeded', state)


class WorkerLease(ApiHarness):
    """The worker lifetime lock is held while a worker may dispatch and released on every exit."""

    def test_lease_is_held_while_running_and_released_on_every_exit_path(self):
        for name in ('succeeded', 'interrupted', 'failed', 'killed'):
            with self.subTest(name=name):
                ident, folder, generation = self.started()
                held, event = [], threading.Event()

                def first(request, name=name, folder=folder, held=held, event=event):
                    held.append(A.worker_alive(folder))
                    if name == 'interrupted':
                        event.set()
                        return dict(STOPPED)
                    if name == 'killed':
                        raise Crash()
                    return {'ok': True, 'json': {'answer': 6}, 'model': request['app']['model'],
                            'node': request['app']['node'], 'ms': 0}

                def reports(runner, action, folder=folder, held=held):
                    held.append(A.worker_alive(folder))
                    raise RuntimeError('fixture failure inside the worker')
                apps = answering(6, first=first)
                if name == 'failed':
                    with patch.object(R.GraphRun, '_producer_reports', reports), self.assertRaises(RuntimeError):
                        A.run_job(folder, applicators=apps, stop_event=event, generation=generation)
                elif name == 'killed':
                    with self.assertRaises(Crash):
                        A.run_job(folder, applicators=apps, stop_event=event, generation=generation)
                else:
                    A.run_job(folder, applicators=apps, stop_event=event, generation=generation)
                self.assertEqual(held, [True])
                self.assertFalse(A.worker_alive(folder))
                self.assertNotIn((str(folder), generation), A._HELD)

    def test_begin_job_refuses_while_another_worker_holds_the_lease(self):
        ident, folder, generation = self.started()
        other = A._acquire(folder / A.WORKER_LOCK, 0)
        try:
            with patch.object(A, 'WORKER_LOCK_WAIT', 0.1):
                result = A.run_job(folder, applicators=answering(6), generation=generation)
            self.assertEqual(result['status'], 'not_started')
            self.assertEqual(A.read_job(folder)['status'], 'starting')
        finally:
            A._release(other)
        self.assertEqual(A.run_job(folder, applicators=answering(6), generation=generation)['status'], 'succeeded')


class HostDurableWrites(Isolated):
    """graph-4 through the host job runner: a killed attempt-pins write never blocks an API resume."""

    def kill_during(self, name):
        real = R._write_file

        def write(folder, target, raw):
            if target == name:
                (Path(folder) / f'.{target}.4242.0123456789abcdef.tmp').write_bytes(raw[:7])
                raise Crash()
            return real(folder, target, raw)
        return patch.object(R, '_write_file', side_effect=write)

    def test_api_resume_after_a_killed_attempt_pins_write(self):
        env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': str(self.root / 'data')})
        env.start()
        self.addCleanup(env.stop)
        pending = []
        hooks = patch.dict(A.launcher, {'launch': lambda ident, folder, generation: pending.append(
            (Path(folder), generation)) or {'ok': True}, 'active': lambda _: False, 'stop': lambda _: True})
        hooks.start()
        self.addCleanup(hooks.stop)
        body = A.example()
        ident = A.start({key: body[key] for key in ('graph', 'policy')})['id']
        folder, generation = pending[-1]
        with self.kill_during('attempt-pins.json'), self.assertRaises(Crash):
            A.run_job(folder, applicators=FakeApps(), generation=generation)
        self.assertTrue(A.view(ident)['can_resume'])
        A.resume(ident)
        _, current = pending[-1]
        self.assertEqual(A.run_job(folder, applicators=FakeApps(), generation=current)['status'], 'succeeded')


class HostNoRepeatedCompilation(Isolated):
    """surface-3 through the host job runner: list and poll views reuse verification."""

    def count(self, owner, name):
        calls, real = [], getattr(owner, name)

        def counted(*args, **kwargs):
            calls.append(name)
            return real(*args, **kwargs)
        patcher = patch.object(owner, name, side_effect=counted)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_execution_compiles_and_builds_linearly_and_views_reuse_verification(self):
        env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': str(self.root / 'data')})
        env.start()
        self.addCleanup(env.stop)
        pending = []
        hooks = patch.dict(A.launcher, {'launch': lambda ident, folder, generation: pending.append(
            (Path(folder), generation)) or {'ok': True}, 'active': lambda _: False, 'stop': lambda _: True})
        hooks.start()
        self.addCleanup(hooks.stop)
        body = A.example()
        ident = A.start({key: body[key] for key in ('graph', 'policy')})['id']
        folder, generation = pending[-1]
        refreezes, compiles, builds = self.count(G, '_freeze'), self.count(G, '_compile'), self.count(R.X, 'build')
        self.assertEqual(A.run_job(folder, applicators=FakeApps(), generation=generation)['status'], 'succeeded')
        self.assertEqual((len(refreezes), len(compiles)), (0, 2))
        self.assertLessEqual(len(builds), 4)  # admission and attempt pins per node
        for _ in range(3):
            view = A.view(ident)
            self.assertEqual(view['state']['status'], 'succeeded')
        self.assertEqual((len(refreezes), len(compiles)), (0, 2))
        self.assertLessEqual(len(builds), 4)  # audits reuse pin digests under the same runtime
        self.assertNotIn('states', view['state'])
        self.assertTrue(all('history' not in row for row in view['state']['nodes']))
        self.assertEqual(len(view['events']), 4)
        real_read = R._read

        def read(path, **kwargs):
            if Path(path).name == 'graph-events.jsonl':
                raise AssertionError('list views must not read ledgers')
            return real_read(path, **kwargs)
        with patch.object(R, '_read', side_effect=read):
            rows = A.list_runs()
        self.assertEqual((rows[0]['id'], rows[0]['status'], rows[0]['reserved_calls']), (ident, 'succeeded', 2))


if __name__ == '__main__':
    unittest.main()
