"""D14/D15: optional bounded author diagnostics and answer-only retry feedback; fake providers only."""

from fractions import Fraction
import json
import tempfile
import threading
import unittest
from unittest import mock

from symblic.kernel import language as S
from symblic.kernel import diagnose as D
from symblic.lang import abstraction as L
from symblic.kernel import run as SR
from tests.kernel.test_symblic_run23 import FakeApps, run_with, sequence

SECRET = 'private-diagnostic-value-739501'


def expression(source):
    parser = S.Parser(S.tokenize(source), 1)
    node = parser.expr()
    assert parser.done()
    return node


def environment(**values):
    env = S.Env()
    for name, value in values.items():
        # Assign after construction to test hostile host values without canon/formatting them first.
        binding = S.Binding(name, 0)
        binding.value = value
        env.vars[name] = binding
    return env


class AuthorDiagnostics(unittest.TestCase):
    def test_assert_expect_keep_prefix_position_and_author_message(self):
        for kind in ('assert', 'expect'):
            with self.subTest(kind=kind):
                source = f'let n = 3.\nlet half = n / 2.\n{kind} half > 5 because "too small".\n'
                run, report, apps = run_with(source, sequence(0))
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['error']['kind'], 'check')
                self.assertEqual(report['error']['line'], 3)
                self.assertEqual(report['error']['message'],
                                 f'{kind} failed: half > 5 — too small In this check: half = 1.5.')
                self.assertIn('half = 1.5', run.trace[-1]['note'])
                self.assertEqual((report['calls'], report['asks'], len(apps.reqs)), (0, 0, 0))

    def test_test_bodies_reuse_assert_expect_diagnostics(self):
        source = ('test "one" do\n let x = 3.\n assert x = 4.\nend.\n'
                  'test "two" do\n let x = 7.\n expect x = 8 because "specific".\nend.\n')
        report = L.run_tests(source)
        self.assertEqual((report['passed'], report['failed'], report['calls'], report['asks']), (0, 2, 0, 0))
        self.assertIn('In this check: x = 3.', report['tests'][0]['error']['message'])
        self.assertIn('— specific In this check: x = 7.', report['tests'][1]['error']['message'])
        self.assertEqual([t['error']['line'] for t in report['tests']], [3, 7])

    def test_quantifier_and_stored_code_report(self):
        source = 'let cells = [{col: 1}, {col: 12}].\nassert all c in cells: c.col < 10.\n'
        _, report, _ = run_with(source, sequence(0))
        self.assertIn('fails for c = {col: 12} (item 2 of 2): c.col = 12', report['error']['message'])
        _, report, _ = run_with('let checked = {passed: false, failed: 1, report: "case 1 failed"}.\n'
                                'expect checked.failed = 0.', sequence(0))
        self.assertIn('checked.failed = 1', report['error']['message'])

    def test_diagnostic_work_never_repeats_helper_query_or_external_adapter(self):
        cases = [('assert js_test("irrelevant", []).passed = true.', 'js_test')]
        for source, name in cases:
            calls = []
            def fake(*args, **kwargs):
                calls.append(1)
                return {'passed': False}
            with mock.patch.dict(S.BUILTINS, {name: fake}):
                _, report, apps = run_with(source, sequence(0))
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(calls, [1])
            self.assertEqual(apps.reqs, [])
            self.assertNotIn('In this check', report['error']['message'])
        run = SR.Run('assert helper(3) = 9.', None, FakeApps(sequence(0)), {'by': 'fake:a'})
        calls = []
        def helper(*args):
            calls.append(1)
            return 4
        run.kernel.functions['helper'] = helper
        report = run.execute()
        self.assertEqual((report['status'], calls), ('failed', [1]))
        query = S.KB.query
        calls = []
        def tracked(kb, *args, **kwargs):
            calls.append(1)
            return query(kb, *args, **kwargs)
        with mock.patch.object(S.KB, 'query', tracked):
            _, report, _ = run_with('fact p(1).\nassert holds p(2).', sequence(0))
        self.assertEqual((report['status'], calls), ('failed', [1]))

    def test_optional_detail_refusal_and_runtime_budget_do_not_change_check(self):
        source = 'let x = 3.\nassert x > 5 because "too small".'
        run, report, _ = run_with(source, sequence(0))
        with mock.patch.object(SR, '_bounded_explanation', return_value=''):
            old, prior, _ = run_with(source, sequence(0))
        self.assertEqual(run.kernel.budget.left, old.kernel.budget.left)
        self.assertEqual(run.trace[-1]['check'], old.trace[-1]['check'])
        self.assertEqual((report['status'], report['error']['line'], report['error']['kind']),
                         (prior['status'], prior['error']['line'], prior['error']['kind']))
        with mock.patch.object(D, 'explain', side_effect=ValueError('optional refusal')):
            _, refused, _ = run_with(source, sequence(0))
        self.assertEqual(refused['error'], prior['error'])

    def test_ensure_warn_and_plain_failure_are_unchanged(self):
        for suffix in ('else warn', 'else fail'):
            source = f'let x = 3.\nensure x > 5 {suffix} because "too small".'
            with mock.patch.object(SR, '_bounded_explanation', side_effect=AssertionError('must not diagnose')):
                _, report, _ = run_with(source, sequence(0))
            self.assertEqual(report['status'], 'done' if suffix == 'else warn' else 'failed')


class RetryDiagnostics(unittest.TestCase):
    def test_because_and_safe_detail_on_all_routes_without_extra_calls(self):
        for route in ('vote', 'escalate', 'search'):
            with self.subTest(route=route):
                source = (f'ask n: Int "Pick." with context=none, effort=low, route={route}, retries=1\n'
                          'let half = n / 2.\nensure half > 5 else retry because "too small\\nkeep this".')
                run, report, apps = run_with(source, sequence(3, 12), parallel=1)
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual((len(apps.reqs), report['calls']), (2, 2))
                self.assertIn('too small\nkeep this', apps.reqs[1]['prompt'])
                self.assertIn('In the last answer: half = 1.5.', apps.reqs[1]['prompt'])
                with mock.patch.object(SR, '_bounded_explanation', return_value=''):
                    old, _, old_apps = run_with(source, sequence(3, 12), parallel=1)
                self.assertEqual(run.kernel.budget.left, old.kernel.budget.left)
                self.assertEqual(len(old_apps.reqs), 2)

    def test_inputs_aliases_other_results_and_helper_closures_stay_private(self):
        for route in ('vote', 'escalate', 'search'):
            for check in ('n = secret', 'n = alias', 'n = other', 'n = hidden(n)', 'n = hidden2(n)'):
                with self.subTest(route=route, check=check):
                    source = (f'given secret: Text = "{SECRET}".\nlet alias = secret.\n'
                              'function hidden(x) = alias.\nfunction hidden2(x) = hidden(x).\n'
                              'ask other: Text "Other" with context=none, effort=low\n'
                              f'ask n: Text "Pick" with context=none, effort=low, route={route}, retries=1\n'
                              f'ensure {check} else retry because "try again".')
                    _, report, apps = run_with(source, sequence(SECRET, 'candidate'), parallel=1)
                    self.assertEqual(report['status'], 'failed', report)
                    if 'hidden' in check and route != 'vote':
                        self.assertEqual(len(apps.reqs), 1)  # existing pure-candidate admission refuses helpers
                    else:
                        self.assertEqual(len(apps.reqs), 3)
                    for req in apps.reqs:
                        self.assertNotIn(SECRET, req['prompt'])
                        self.assertNotIn(SECRET, req['system'])

    def test_observations_and_routine_arguments_do_not_reach_feedback(self):
        from tests.kernel.test_symblic_effects import Host
        for route in ('vote', 'escalate', 'search'):
            with self.subTest(route=route):
                source = ('observe secret: Text = calendar.free_busy(days=2).\n'
                          f'ask n: Text "Pick" with context=none, effort=low, route={route}, retries=1\n'
                          'ensure n = secret else retry because "try again".')
                host = Host({'calendar.free_busy': SECRET})
                _, report, apps = run_with(source, sequence('candidate'), effects=host, parallel=1)
                self.assertEqual((report['status'], len(host.calls), len(apps.reqs)), ('failed', 1, 2))
                for req in apps.reqs:
                    self.assertNotIn(SECRET, req['prompt'])
                source = ('routine secret_pick(secret: Text) -> Text do\n'
                          f'ask n: Text "Pick" with context=none, effort=low, route={route}, retries=1\n'
                          'ensure n = secret else retry because "try again".\nreturn n.\nend.\n'
                          f'let out = secret_pick("{SECRET}").')
                _, report, apps = run_with(source, sequence('candidate'), parallel=1)
                self.assertEqual((report['status'], len(apps.reqs)), ('failed', 2))
                for req in apps.reqs:
                    self.assertNotIn(SECRET, req['prompt'])

    def test_secret_error_text_and_shadowed_constant_are_redacted(self):
        for route in ('vote', 'escalate', 'search'):
            with self.subTest(route=route):
                source = (f'given secret: Text = "{SECRET}".\n'
                          f'ask n: Int "Pick" with context=none, effort=low, route={route}, retries=1\n'
                          'ensure n + number(secret) > 5 else retry because "try again".')
                _, report, apps = run_with(source, sequence(1), parallel=1)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(len(apps.reqs), 2)
                for req in apps.reqs:
                    self.assertNotIn(SECRET, req['prompt'])
                self.assertIn('could not be evaluated', apps.reqs[1]['prompt'])
        source = (f'given pi: Text = "{SECRET}".\nask n: Int "Pick" with context=none,effort=low,retries=1\n'
                  'ensure n > 10 else retry because "try again".')
        _, _, apps = run_with(source, sequence(1))
        self.assertNotIn('In the last answer', apps.reqs[1]['prompt'])

    def test_future_shadow_never_authorizes_an_earlier_check_or_error(self):
        for route in ('escalate', 'search'):
            for condition in ('n = limit', 'n + number(limit) > 0'):
                with self.subTest(route=route, condition=condition):
                    source = (f'given limit: Text = "{SECRET}".\nfor item in [1] do\n'
                              f'ask n: Int "Pick" with context=none, effort=low, route={route}, retries=1\n'
                              f'ensure {condition} else retry because "try again".\n'
                              'let limit = n + 1.\nensure limit > n else retry.\nend.')
                    _, report, apps = run_with(source, sequence(1), parallel=1)
                    self.assertEqual(report['status'], 'failed')
                    self.assertEqual(len(apps.reqs), 2)
                    self.assertNotIn(SECRET, apps.reqs[1]['prompt'])

    def test_retry_prompt_manifest_and_verified_limit_include_new_detail(self):
        source = ('ask n: Int "Pick" with context=none, effort=low, route=escalate, retries=1\n'
                  'ensure n > 5 else retry because "too small".')
        _, report, apps = run_with(source, sequence(1, 8), profile='verified', budget=10000, parallel=1)
        self.assertEqual(report['status'], 'done', report.get('error'))
        sizes = []
        for req in apps.reqs:
            actual = len(req['system']) + len(req['prompt']) + len(json.dumps(
                req['schema'], ensure_ascii=False, sort_keys=True, separators=(',', ':')))
            self.assertEqual(req['context_manifest']['used'], actual)
            sizes.append(actual)
        self.assertGreater(sizes[1], sizes[0])
        _, report, apps = run_with(source, sequence(1, 8), profile='verified', budget=sizes[1] - 1, parallel=1)
        self.assertEqual((report['status'], len(apps.reqs)), ('failed', 1))
        self.assertEqual(report['error']['kind'], 'context')

    def test_persisted_replay_reuses_exact_augmented_prompts(self):
        source = ('ask n: Int "Pick" with context=none, effort=low, retries=1\n'
                  'ensure n > 5 else retry because "too small".')
        with tempfile.TemporaryDirectory() as folder:
            _, report, apps = run_with(source, sequence(1, 8), folder=folder)
            self.assertEqual(report['status'], 'done', report.get('error'))
            _, replay, again = run_with(source, sequence(999), folder=folder)
            self.assertEqual((replay['status'], replay['cached'], len(again.reqs)), ('done', 2, 0))
            self.assertEqual(replay['fingerprint'], report['fingerprint'])
            self.assertIn('In the last answer: n = 1.', apps.reqs[1]['prompt'])


class DiagnosticEnvelope(unittest.TestCase):
    def assert_skipped_before_explain(self, source, value):
        with mock.patch.object(D, 'explain', side_effect=AssertionError('must not enter formatter')) as explain:
            result = SR._bounded_explanation(expression(source), environment(n=value), S.KB(), {'n'})
        self.assertEqual(result, '')
        explain.assert_not_called()

    def test_large_deep_shared_cyclic_and_host_values_are_not_formatted(self):
        deep = 1
        for _ in range(40):
            deep = (deep,)
        shared = 'x'
        for _ in range(20):
            shared = (shared, shared)
        cyclic = []; cyclic.append(cyclic)
        class Host:
            def __str__(self):
                raise AssertionError('host object must not be formatted')
        for value in ('x' * 100000, tuple(range(100000)), {'x': 'x' * 100000}, 1 << 50000,
                      Fraction(1, 1 << 50000), deep, shared, cyclic, Host()):
            with self.subTest(kind=type(value).__name__):
                self.assert_skipped_before_explain('n = 0', value)

    def test_growth_and_dynamic_helpers_are_skipped_before_explain(self):
        for source in ('text(v=[n]) = "x"', 'text({x: [n]}.x) = "x"',
                       'text([{x: [n]}][1].x) = "x"', 'eval(n) = 0', 'replace(n, "", n) = "x"',
                       'n * 10000 = "x"', 'n + n = "x"', 'helper(n) = 0', 'js_test(n, []).passed'):
            with self.subTest(source=source):
                self.assert_skipped_before_explain(source, 'candidate')

    def test_keyword_name_text_is_charged_before_diagnostic_entry(self):
        huge = 'q' * (SR._DIAGNOSTIC_CHARS + 1)
        self.assert_skipped_before_explain('len(n, ' + huge + '=1) > 0', 'candidate')

    def test_wide_ast_is_refused_before_formatting(self):
        self.assert_skipped_before_explain('n = [' + ','.join('1' for _ in range(10000)) + ']', 3)

    def test_diagnostics_are_read_isolated_and_only_copy_allowed_values(self):
        env = environment(n=3, secret=SECRET, observed=SECRET, other=SECRET)
        owner = object()
        with S.capture_binding_reads(owner) as reads:
            text = SR._bounded_explanation(expression('n = secret'), env, S.KB(), {'n'})
        self.assertEqual(text, 'n = 3')
        self.assertEqual(reads, {})
        with mock.patch.object(D, 'explain', wraps=D.explain) as explain:
            SR._bounded_explanation(expression('n = observed or n = other'), env, S.KB(), {'n'})
        self.assertEqual(set(explain.call_args.args[1].vars), {'n'})

    def test_final_output_step_cap_and_cancellation(self):
        node = expression('n = "other"')
        detail = SR._bounded_explanation(node, environment(n='x' * 1000), S.KB(), {'n'})
        self.assertTrue(detail)
        self.assertLessEqual(len(detail), D.EXPLAIN_LIMIT)
        with mock.patch.object(D, 'explain', return_value='') as explain:
            SR._bounded_explanation(node, environment(n='candidate'), S.KB(), {'n'})
        self.assertEqual(explain.call_args.kwargs['steps'], SR._DIAGNOSTIC_STEPS)
        with mock.patch.object(D, 'explain', side_effect=SR.Stopped):
            with self.assertRaises(SR.Stopped):
                SR._bounded_explanation(node, environment(n='candidate'), S.KB(), {'n'})
        stop = threading.Event(); stop.set()
        _, report, apps = run_with('assert 1 = 2.', sequence(0), stop=stop)
        self.assertEqual((report['status'], len(apps.reqs)), ('stopped', 0))


if __name__ == '__main__':
    unittest.main()
