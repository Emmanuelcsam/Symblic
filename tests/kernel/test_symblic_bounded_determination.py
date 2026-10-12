"""Optional analysis must leave a budget for checked model construction. Fakes only."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import run as R  # noqa: E402


SUM = 'x + x + x + x + x + x + x + x'
INTEGER = ('ask x: Int in 0..19999 "Return the specified integer." with effort=low{options}\n'
           'ensure ' + SUM + ' = {total} else retry.\nshow x.')
RECORD = ('ask r: Record {{a: Int in 0..140, b: Int in 0..140}} "Return the pair." with effort=low\n'
          'ensure r.a + r.a + r.a + r.b + r.b + r.b = 6 and r.a = 1 else retry.\nshow r.')


class Models:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': next(self.answers)}, 'model': 'fake', 'ms': 1}


def execute(source, answers, **opts):
    models = Models(answers)
    run = R.Run(source, {}, models, {'by': 'fake:a', 'max_calls': 2, 'side_effects': False, **opts})
    return run, run.execute(), models


class Construction(unittest.TestCase):
    def test_published_integer_and_record_failures_now_reach_checked_models(self):
        for source, answer in ((INTEGER.format(options='', total=8), 1), (RECORD.format(), {'a': 1, 'b': 1})):
            with self.subTest(source=source):
                run, report, models = execute(source, [answer])
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(len(models.requests), 1)
                self.assertGreater(run.kernel.budget.left, 140000)
                receipt = report['determinacy']['asks'][0]
                self.assertEqual((receipt['status'], receipt['reason'], receipt['answered_by']),
                                 ('unassessed', 'budget', 'model'))
                detail = report['evidence']['determinations'][0]
                self.assertEqual((detail['verdict'], detail['reason'], detail['accepted']),
                                 ('unassessed', 'budget', 1))
                self.assertFalse(detail['exhaustive'])
                self.assertLess(detail['evaluated'], detail['domain'])
                self.assertNotIn('unique', detail)
                self.assertNotIn('unique_hash', detail)
                self.assertGreater(detail['assessment_budget']['charged'], 49000)
                self.assertLessEqual(detail['assessment_budget']['charged'], 50000)

    def test_partial_zero_is_not_contradiction_and_partial_two_are_witnesses(self):
        cases = [(INTEGER.format(options='', total=19000 * 8), 19000, 'unassessed', 0),
                 ('ask x: Int in 0..19999 "Pick zero or one." with effort=low\n'
                  'ensure x < 2 and ' + SUM + ' >= 0 else retry.\nshow x.', 1, 'underdetermined', 2)]
        for source, answer, status, count in cases:
            with self.subTest(status=status):
                _run, report, models = execute(source, [answer])
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(len(models.requests), 1)
                det = report['evidence']['determinations'][0]
                self.assertEqual((det['verdict'], det['accepted']), (status, count))
                self.assertFalse(det['exhaustive'])
                self.assertEqual(report['determinacy']['asks'][0]['status'], status)
                self.assertFalse(any('no possible answer' in w['message'] for w in report['warnings']))

    def test_interrupted_last_domain_value_does_not_complete_the_scan(self):
        source = INTEGER.format(options='', total=8).replace('0..19999', '0..1')
        _run, report, models = execute(source, [1], max_steps=120)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 1)
        det = report['evidence']['determinations'][0]
        self.assertEqual((det['domain'], det['evaluated'], det['accepted']), (2, 1, 0))
        self.assertFalse(det['exhaustive'])
        self.assertEqual(det['verdict'], 'unassessed')

    def test_small_exhaustive_uniqueness_contradiction_and_explicit_solving_survive(self):
        source = 'ask x: Int in 0..3 "Pick one." with effort=low{option}\nensure x = {target} else retry.'
        for option, target, expected, calls in (('', 1, 'done', 1), (', solve=true', 1, 'done', 0),
                                               (', solve=auto', 1, 'done', 0),
                                               (', by=kernel', 1, 'done', 0), ('', 9, 'failed', 0)):
            with self.subTest(option=option, target=target):
                _run, report, models = execute(source.format(option=option, target=target), [1])
                self.assertEqual(report['status'], expected, report.get('error'))
                self.assertEqual(len(models.requests), calls)
                self.assertEqual(report['determinacy']['asks'][0]['status'],
                                 'contradictory' if target == 9 else 'determined')

    def test_explicit_full_modes_and_dynamic_solve_keep_full_budget_behavior(self):
        for option in (', solve=true', ', solve=auto', ', by=kernel', ', solve=(1 = 0)'):
            with self.subTest(option=option):
                run, report, models = execute(INTEGER.format(options=option, total=8), [1])
                self.assertEqual(report['status'], 'failed')
                self.assertIn('kernel step budget ran out', report['error']['message'])
                self.assertLess(run.kernel.budget.left, 0)
                self.assertEqual(models.requests, [])

    def test_literal_bound_and_default_false_modes_use_the_optional_pool(self):
        for prefix, option, host in (('', ', solve=false', {}), ('let mode = false.\n', ', solve=mode', {}),
                                    ('use solve=false.\n', '', {}), ('', '', {'solve': False})):
            with self.subTest(prefix=prefix, option=option):
                _run, report, _models = execute(prefix + INTEGER.format(options=option, total=8), [1], **host)
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(report['determinacy']['asks'][0]['reason'], 'budget')

    def test_bad_answer_still_retries_and_call_cap_still_refuses(self):
        for route in ('vote', 'escalate', 'search'):
            with self.subTest(route=route):
                source = INTEGER.format(options=', retries=1, route=' + route, total=8)
                _run, report, models = execute(source, [0, 1])
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(len(models.requests), 2)
                self.assertEqual(next(b['value'] for b in report['bindings'] if b['name'] == 'x'), 1)
                _run, report, models = execute(source, [0], max_calls=1)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(len(models.requests), 1)

    def test_vacuity_oversized_charge_stops_and_the_real_answer_still_checks(self):
        source = ('ask t: Text "Return a nonempty word." with effort=low\n'
                  'ensure len(t) > 0 or len(1..60000) = 60000 else retry.')
        run, report, models = execute(source, ['word'])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 1)
        self.assertGreater(run.kernel.budget.left, 199000)
        self.assertFalse(any(w.get('code') == 'SYM_VACUOUS' for w in report['warnings']))
        rows = [row for row in run.trace if row['kind'] == 'optional-assessment']
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['exhausted'])

    def test_nested_eval_shares_optional_allowance_without_swallowing_its_signal(self):
        source = ('ask x: Int in 0..19999 "Return one." with effort=low\n'
                  'ensure eval("x + x + x + x + x + x + x + x = 8", x=x) else retry.')
        run, report, models = execute(source, [1])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 1)
        self.assertGreater(run.kernel.budget.left, 140000)
        self.assertEqual(report['determinacy']['asks'][0]['reason'], 'budget')

    def test_stop_during_scan_propagates_without_dispatch_or_false_contradiction(self):
        models = Models([1])
        run = R.Run(INTEGER.format(options='', total=8), {}, models, {'by': 'fake:a'})
        candidate = run._candidate

        def stop_at_three(s, env, value, *args, **kwargs):
            if value == 3:
                run.stop.set()
            return candidate(s, env, value, *args, **kwargs)

        with mock.patch.object(run, '_candidate', side_effect=stop_at_three):
            report = run.execute()
        self.assertEqual(report['status'], 'stopped')
        self.assertEqual(models.requests, [])
        self.assertFalse(any(row['status'] == 'contradictory' for row in report['determinacy']['asks']))

    def test_exhausted_enumeration_does_not_run_a_second_vacuity_probe(self):
        with mock.patch.object(R.Run, 'vacuity', side_effect=AssertionError('pool must stay exhausted')):
            _run, report, models = execute(INTEGER.format(options='', total=8), [1])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 1)

    def test_candidate_arithmetic_errors_remain_rejections_and_do_not_fake_exhaustion(self):
        source = ('ask x: Int in 0..3 "Pick two." with effort=low\n'
                  'ensure 1 / (x - 1) = 1 else retry.')
        _run, report, models = execute(source, [2])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 1)
        det = report['evidence']['determinations'][0]
        self.assertEqual((det['exhaustive'], det['evaluated'], det['accepted']), (True, 4, 1))
        self.assertFalse(det['assessment_budget']['exhausted'])

    def test_retry_spends_a_new_smaller_allowance_and_never_refunds_previous_work(self):
        source = INTEGER.format(options=', retries=1', total=8)
        run, report, models = execute(source, [0, 1])
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 2)
        details = report['evidence']['determinations']
        self.assertEqual(len(details), 2)
        first, second = [d['assessment_budget'] for d in details]
        self.assertLess(second['limit'], first['limit'])
        self.assertLess(run.kernel.budget.left, 120000)
        self.assertGreaterEqual(S.MAX_STEPS - run.kernel.budget.left, first['charged'] + second['charged'])


class Accounting(unittest.TestCase):
    def test_every_admitted_charge_debits_parent_once_and_large_refusal_is_latched(self):
        parent = S.Budget(100)
        quota = R._AssessmentBudget(parent, lambda: None)
        quota.tick(3)
        self.assertEqual((parent.left, quota.left), (97, 22))
        with self.assertRaises(R._AssessmentExhausted):
            quota.tick(100000)
        self.assertEqual((parent.left, quota.left), (97, 22))
        with self.assertRaises(R._AssessmentExhausted):
            quota.tick(1)
        self.assertEqual((parent.left, quota.left), (97, 22))
        self.assertEqual(quota.record(), {'limit': 25, 'charged': 3, 'exhausted': True,
                                          'unit': 'admitted_kernel_steps'})

    def test_zero_pool_is_truthy_and_does_not_create_a_fresh_kernel_budget(self):
        quota = R._AssessmentBudget(S.Budget(3), lambda: None)
        kernel = S.Kernel(budget=quota)
        self.assertIs(kernel.budget, quota)
        with self.assertRaises(R._AssessmentExhausted):
            kernel.eval(S.Parser(S.tokenize('1'), 1).expr())

    def test_real_parent_exhaustion_and_stop_take_precedence_over_optional_fallback(self):
        parent = S.Budget(100)
        quota = R._AssessmentBudget(parent, lambda: None)
        parent.left = -1
        with self.assertRaises(S.SymblicError):
            quota.tick(100000)
        self.assertFalse(quota.exhausted)
        parent.left = 0
        with self.assertRaises(S.SymblicError):
            quota.tick(1)
        self.assertEqual(quota.left, quota.limit)

        def stopped():
            raise R.Stopped()

        quota.check_stop = stopped
        with self.assertRaises(R.Stopped):
            quota.tick(1)


if __name__ == '__main__':
    unittest.main()
