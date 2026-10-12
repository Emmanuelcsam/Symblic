"""symblic.js.check re-observation: a timed-out case is observed again once the machine is calm (fakes only, no Node).

2026-10-11: a development machine at load 38 (6 CPUs) turned every 3 s JavaScript case of a game-level build into a
timeout, and the build failed "inconclusive" twice without a single model repair. A timeout is still never a
verdict; it is just observed again, up to REOBSERVE times, each after a bounded wait for the load to drop.
"""
import unittest
from unittest import mock

from symblic.js import check as J


def _ok(value='1'):
    return {'ok': True, 'value': value}


def _timeout():
    return {'ok': False, 'kind': 'timeout', 'error': 'Script execution timed out after 3000ms', 'line': None}


class Reobserve(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self.evaluations = []
        patches = [mock.patch.object(J, 'CALM_WAIT_S', 0.0), mock.patch.object(J, 'host_load', lambda: 0.1),
                   mock.patch.object(J, 'host_io', lambda: 0.0)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _evaluate(self, answers):
        """A fake evaluate: one list of rows per call, in order; records which calls were asked."""
        answers = list(answers)

        def evaluate(source, calls, **kw):
            self.evaluations.append(list(calls))
            rows = answers.pop(0)
            self.assertEqual(len(rows), len(calls))
            return rows
        return evaluate

    def test_a_timed_out_case_is_observed_again_and_only_that_case(self):
        fake = self._evaluate([[_ok('1'), _timeout(), _ok('3')], [_ok('2')]])
        with mock.patch.object(J, 'evaluate', fake):
            failed, results = J.failures('src', [('a()', '1'), ('b()', '2'), ('c()', '3')])
        self.assertEqual(failed, [])
        self.assertEqual(self.evaluations, [['a()', 'b()', 'c()'], ['b()']])
        self.assertEqual(results[1], {'ok': True, 'value': '2', 'reobserved': 1})
        self.assertNotIn('reobserved', results[0])

    def test_test_reports_how_many_cases_were_reobserved(self):
        fake = self._evaluate([[_timeout(), _timeout()], [_ok('1'), _timeout()], [_ok('2')]])
        with mock.patch.object(J, 'evaluate', fake), mock.patch.object(J, '_effective_deadline', lambda d: None):
            report = J.test('src', [('a()', '1'), ('b()', '2')])
        self.assertTrue(report['passed'])
        self.assertEqual(report['reobserved'], 2)
        self.assertEqual(self.evaluations, [['a()', 'b()'], ['a()', 'b()'], ['b()']])

    def test_a_case_that_keeps_timing_out_stays_inconclusive_after_the_last_round(self):
        fake = self._evaluate([[_timeout()], [_timeout()], [_timeout()], [_ok('1')]])
        with mock.patch.object(J, 'evaluate', fake):
            with self.assertRaises(J.JsError) as caught:
                J.failures('src', [('a()', '1')])
        self.assertEqual(self.evaluations, [['a()']] * (1 + J.REOBSERVE))
        self.assertIn('inconclusive', str(caught.exception))
        self.assertIn(f'after {J.REOBSERVE} re-observation(s) on a loaded host', str(caught.exception))
        self.assertEqual(caught.exception.kind, 'resource')

    def test_a_passing_or_failing_verdict_is_never_re_run(self):
        fake = self._evaluate([[_ok('1'), {'ok': False, 'kind': 'error', 'error': 'boom', 'line': 1}]])
        with mock.patch.object(J, 'evaluate', fake):
            failed, results = J.failures('src', [('a()', '1'), ('b()', '2')])
        self.assertEqual(len(failed), 1)
        self.assertEqual(self.evaluations, [['a()', 'b()']])

    def test_memory_and_unavailable_observations_are_not_re_run(self):
        rows = [{'ok': False, 'kind': 'resource', 'error': 'memory allocation failed', 'line': None}]
        fake = self._evaluate([rows])
        with mock.patch.object(J, 'evaluate', fake):
            with self.assertRaises(J.JsError):
                J.failures('src', [('a()', '1')])
        self.assertEqual(self.evaluations, [['a()']])

    def test_a_report_without_re_observation_is_unchanged(self):
        fake = self._evaluate([[_ok('1')]])
        with mock.patch.object(J, 'evaluate', fake), mock.patch.object(J, '_effective_deadline', lambda d: None):
            report = J.test('src', [('a()', '1')])
        self.assertEqual(report, {'passed': True, 'total': 1, 'failed': 0, 'report': 'All 1 examples passed.'})


class Calm(unittest.TestCase):
    def test_waits_until_the_load_drops_and_reports_calm(self):
        loads = iter([4.0, 3.0, 1.0])
        clock = iter([0.0, 0.0, 2.0, 2.0, 4.0, 4.0, 6.0, 6.0])
        sleeps = []
        calm = J._calm(None, wait_s=30, sleep=sleeps.append, load=lambda: next(loads), io=lambda: 0.0,
                       clock=lambda: next(clock))
        self.assertTrue(calm)
        self.assertEqual(sleeps, [2.0, 2.0])

    def test_waits_for_io_pressure_too(self):
        pressures = iter([82.5, 60.0, 12.0])
        clock = iter([0.0, 0.0, 2.0, 4.0])
        sleeps = []
        calm = J._calm(None, wait_s=30, sleep=sleeps.append, load=lambda: 0.5, io=lambda: next(pressures),
                       clock=lambda: next(clock))
        self.assertTrue(calm)
        self.assertEqual(sleeps, [2.0, 2.0])

    def test_one_unreadable_reading_defers_to_the_other(self):
        sleeps = []
        self.assertTrue(J._calm(None, wait_s=30, sleep=sleeps.append, load=lambda: None, io=lambda: 5.0))
        self.assertFalse(J._calm(None, wait_s=0, sleep=sleeps.append, load=lambda: None, io=lambda: 95.0))
        self.assertEqual(sleeps, [])

    def test_the_real_io_reader_gives_a_percentage_or_none(self):
        value = J.host_io()
        self.assertTrue(value is None or (isinstance(value, float) and 0.0 <= value <= 100.0))

    def test_gives_up_at_the_wait_bound_and_at_the_deadline(self):
        ticks = iter([0.0, 0.0, 2.0, 4.0, 6.0])          # one reading for the bound, then one per round
        sleeps = []
        calm = J._calm(None, wait_s=5, sleep=sleeps.append, load=lambda: 9.0, io=lambda: 0.0, clock=lambda: next(ticks))
        self.assertFalse(calm)
        self.assertEqual(sleeps, [2.0, 2.0, 1.0])
        ticks = iter([10.0, 10.0, 12.0])
        sleeps = []
        calm = J._calm(11.0, wait_s=60, sleep=sleeps.append, load=lambda: 9.0, io=lambda: 0.0, clock=lambda: next(ticks))
        self.assertFalse(calm)
        self.assertEqual(sleeps, [1.0])

    def test_unreadable_readings_never_wait(self):
        sleeps = []
        self.assertFalse(J._calm(None, wait_s=30, sleep=sleeps.append, load=lambda: None, io=lambda: None))
        self.assertEqual(sleeps, [])

    def test_the_real_reader_gives_a_per_cpu_number_or_none(self):
        value = J.host_load()
        self.assertTrue(value is None or (isinstance(value, float) and value >= 0.0))


if __name__ == '__main__':
    unittest.main()
