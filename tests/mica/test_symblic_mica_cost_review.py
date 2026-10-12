"""Independent cost-meter review; only fake providers and isolated stores.

Tests express the required behavior, including known findings in the initial
review snapshot. No live store, shell session or real model is invoked.
"""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from symblic.mica import costs as T


def events():
    return [
        {'kind': 'cost_started', 'cost_id': 'a' * 32, 'category': 'verification',
         'label': 'fixture', 'version': T.VERSION},
        {'kind': 'cost_finished', 'cost_id': 'a' * 32, 'outcome': 'returned',
         'elapsed_ns': 10, 'host_thread_cpu_ns': 5, 'exclusive_ns': 10,
         'exclusive_host_thread_cpu_ns': 5},
    ]


class MeterReview(unittest.TestCase):
    def setUp(self):
        self.old_stack = getattr(T._LOCAL, 'stack', None)
        T._LOCAL.stack = []
        self.rows = []

    def tearDown(self):
        T._LOCAL.stack = self.old_stack if self.old_stack is not None else []

    def emit(self, kind, **fields):
        self.rows.append({'kind': kind, **fields})

    def test_failed_start_cpu_clock_does_not_leak_nesting(self):
        def unavailable():
            raise RuntimeError('clock unavailable')
        with self.assertRaisesRegex(RuntimeError, 'clock unavailable'):
            with T.measure(self.emit, 'verification', 'start', clock=lambda: 1, cpu=unavailable):
                self.fail('operation must not run after timer setup fails')
        self.assertEqual(T._LOCAL.stack, [])
        self.assertEqual(T.summarize(self.rows)['interrupted'], 1)

    def test_failed_finish_clock_does_not_leak_nesting(self):
        values = iter([1])
        with self.assertRaisesRegex(RuntimeError, 'StopIteration'):
            with T.measure(self.emit, 'verification', 'finish', clock=lambda: next(values), cpu=lambda: 0):
                pass
        self.assertEqual(T._LOCAL.stack, [])
        self.assertEqual(T.summarize(self.rows)['interrupted'], 1)

    def test_summary_rejects_impossible_exclusive_cost(self):
        summary = T.summarize(events())
        summary['groups'][0]['counters']['exclusive_ns']['known_sum'] = 11
        summary['groups'][0]['counters']['exclusive_ns']['completed_span_total'] = 11
        with self.assertRaises(ValueError):
            T.combine([summary])

    def test_summary_rejects_missing_top_level_started_count(self):
        summary = T.summarize(events())
        summary['started'] = 0
        with self.assertRaises(ValueError):
            T.combine([summary])

    def test_summary_rejects_individually_invalid_counts_that_cancel(self):
        first = T.summarize(events())
        second = copy.deepcopy(first)
        first['groups'][0]['started'] = 0
        second['groups'][0]['started'] = 2
        with self.assertRaises(ValueError):
            T.combine([first, second])

    def test_interleaved_threads_are_not_assumed_to_be_nested(self):
        rows = events()
        second = copy.deepcopy(rows)
        for row in second:
            row['cost_id'] = 'b' * 32
        result = T.summarize([rows[0], second[0], rows[1], second[1]])
        self.assertEqual(result['completed'], 2)
        self.assertEqual(result['groups'][0]['counters']['exclusive_ns']['known_sum'], 20)
        self.assertIn('overlap', result['wall_semantics'])

    def test_failed_body_is_costed_without_fabricating_verdict(self):
        with self.assertRaisesRegex(LookupError, 'candidate unavailable'):
            with T.measure(self.emit, 'verification', 'failure'):
                raise LookupError('candidate unavailable')
        summary = T.summarize(self.rows)
        self.assertEqual((summary['completed'], summary['interrupted']), (1, 0))
        self.assertEqual(summary['groups'][0]['raised'], 1)


class NativeContextReview(unittest.TestCase):
    def test_complete_scope_is_nested_exception_safe_and_thread_local(self):
        from symblic.kernel import language as S
        from symblic.js import check as JS
        from symblic.js import contract as JSC
        observed = []
        record = {'passed': False, 'status': 'budget', 'report': 'limited'}
        def check():
            try:
                return JSC._js_declarations_check(S.Kernel(), None, '', {'version': 1, 'exports': {}})['status']
            except JS.JsError as error:
                return error.kind
        with mock.patch.object(JSC, 'check', return_value=record):
            with JSC.require_complete_scope():
                self.assertEqual(check(), 'resource')
                thread = threading.Thread(target=lambda: observed.append(check()))
                thread.start(); thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
                with self.assertRaisesRegex(RuntimeError, 'nested'):
                    with JSC.require_complete_scope():
                        raise RuntimeError('nested')
                self.assertEqual(check(), 'resource')
            self.assertEqual(check(), 'budget')
        self.assertEqual(observed, ['budget'])


class RecoveryReview(unittest.TestCase):
    def test_meter_writer_failure_cannot_be_a_model_contract_failure(self):
        from symblic.mica import search as M
        from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request, proposal
        class InterruptedMeterRun(M.MicaRun):
            def _event(self, kind, **fields):
                if kind == 'cost_started' and fields.get('label') == 'proposal_admission':
                    self.inject_failure_id = fields['cost_id']
                if kind == 'cost_finished' and fields['cost_id'] == getattr(self, 'inject_failure_id', None):
                    raise ValueError('cost journal writer unavailable')
                return super()._event(kind, **fields)
        with tempfile.TemporaryDirectory(prefix='cost-review-') as tmp:
            apps = FakeApps(lambda req, number: json.dumps(proposal()))
            run = InterruptedMeterRun(request(max_candidates=1), Path(tmp) / 'run', apps, inventory())
            try:
                result = run.execute(mode='static')
            except RuntimeError:
                pass  # A distinct visible host instrumentation fault is acceptable.
            else:
                self.assertEqual(result['routing_observations']['unique_observations'], 0, result)
                self.assertNotEqual(result.get('failure'), 'INVALID_CONTRACT', result)
                self.assertIn(result['status'], ('blocked', 'unknown'))
            self.assertEqual(len(apps.requests), 1)
            self.assertFalse(any(row['kind'] == 'observation' for row in run._events()))

    def test_root_resource_refusal_stops_without_retrying_another_root(self):
        from symblic.mica import project as P
        from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request
        with tempfile.TemporaryDirectory(prefix='cost-review-') as tmp:
            apps = FakeApps()
            project = P.MicaProject('Implement public integer increment.', Path(tmp) / 'p', apps, inventory(),
                                    budget=request(max_candidates=3)['budget'], allowed_outputs=['result.js'])
            report = {'status': 'failed', 'error': {'kind': 'resource', 'message': 'native resource unavailable'}}
            with mock.patch.object(P.N._BoundedRun, 'execute', return_value=report) as native:
                result = project.execute(mode='direct')
            self.assertEqual(result['status'], 'blocked', result)
            self.assertEqual(result['failure'], 'VERIFICATION_UNKNOWN')
            self.assertEqual(native.call_count, 1)
            self.assertEqual(apps.requests, [])

    def test_internal_native_fault_is_ungraded_after_one_fake_call(self):
        from symblic.mica import search as M
        from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request
        apps = FakeApps()
        original = M.N.Run._candidate
        def candidate(runner, *args, **kwargs):
            if apps.requests:
                raise RuntimeError('host predicate instrumentation unavailable')
            return original(runner, *args, **kwargs)
        with tempfile.TemporaryDirectory(prefix='cost-review-') as tmp:
            with mock.patch.object(M.N.Run, '_candidate', candidate):
                result = M.MicaRun(request(max_candidates=2), Path(tmp) / 'run', apps, inventory()).execute(mode='direct')
            self.assertEqual(result['status'], 'blocked', result)
            self.assertEqual(result['failure'], 'INTERNAL_ERROR')
            self.assertEqual(result['routing_observations']['unique_observations'], 0)
            self.assertEqual(result['calls'], 1)
            self.assertEqual(len(apps.requests), 1)

    def test_project_unknown_recovery_keeps_interrupted_native_cost(self):
        from symblic.mica import project as P
        from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request
        with tempfile.TemporaryDirectory(prefix='cost-review-') as tmp:
            folder = Path(tmp) / 'project'
            attempt = folder / 'root-attempts' / 'root-000'
            P.G._mkdir_private(attempt)
            (attempt / 'mica-native-pins.json').write_text('{}')
            row = P.G._seal({'sequence': 0, 'previous': None, **events()[0]})
            (attempt / 'mica-host-costs.jsonl').write_text(json.dumps(row) + '\n')
            apps = FakeApps()
            project = P.MicaProject('Implement public integer increment.', folder, apps, inventory(),
                                    budget=request()['budget'], allowed_outputs=['result.js'])
            with mock.patch.object(P.N, 'inspect_attempt', return_value={'status': 'unknown', 'calls': 1}):
                result = project.execute(mode='direct')
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['calls'], 1)
            self.assertEqual(result['host_costs']['interrupted'], 1)
            self.assertIsNone(result['host_costs']['groups'][0]['counters']['elapsed_ns']['completed_span_total'])
            self.assertEqual(apps.requests, [])

    def test_new_completed_result_cannot_drop_cost_field_on_replay(self):
        from symblic.mica import search as M
        from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request
        with tempfile.TemporaryDirectory(prefix='cost-review-') as tmp:
            folder = Path(tmp) / 'run'
            apps = FakeApps()
            result = M.MicaRun(request(), folder, apps, inventory()).execute(mode='direct')
            self.assertEqual(result['status'], 'done', result)
            result.pop('sha256', None)
            result.pop('host_costs')
            (folder / 'mica-result.json').write_text(json.dumps(M.D._seal(result)))
            with self.assertRaisesRegex(ValueError, '[Cc]ost'):
                M.MicaRun(request(), folder, apps, inventory()).execute(mode='direct')
            self.assertEqual(len(apps.requests), 1)


if __name__ == '__main__':
    unittest.main()
