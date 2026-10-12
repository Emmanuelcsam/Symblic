"""Independent native fallback adversaries. Temp folders and fake providers only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from symblic.kernel import language as S
from symblic.kernel import run as R
from symblic.kernel import lockfile as K

OPTIONS = {'by': 'fake:review', 'profile': 'verified', 'determine': False, 'solve': False,
           'constructor': 'off', 'effort': 'low', 'context': 'none', 'strict': True,
           'parallel': 1, 'max_calls': 3, 'max_asks': 3, 'budget': 12000, 'side_effects': False}
BODY = 'if n = "right" then 3 * x else x'
SOURCE = ('ask n: one of {"bad", "partial", "right"} "Choose n." with retries=1, fallback_choices=["partial", "right"]\n'
          'function twice(x: Int) -> Int = ' + BODY + '.\n'
          'ensure n = n and twice(2) = 6 else retry.\n'
          'let answer = twice(3).\nshow answer.\n')


class Apps:
    def __init__(self, value='bad'):
        self.value = value
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': self.value}, 'model': 'review-model',
                'node': 'review-node', 'ms': 1}


class Review(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'run'

    def run_source(self, source=SOURCE, *, options=None, cls=R.Run, apps=None, folder=None):
        apps = apps or Apps()
        options = {**OPTIONS, **(options or {})}
        run = cls(source, {}, apps, options, folder=str(folder) if folder else None)
        return run, run.execute(), apps

    def save(self, source=SOURCE, *, options=None):
        self.folder.mkdir()
        (self.folder / 'program.sym').write_text(source)
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': {**OPTIONS, **(options or {})}}))
        return self.run_source(source, options=options, folder=self.folder)

    def test_host_binding_does_not_inherit_model_proposal_or_agreement(self):
        run, report, apps = self.run_source()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(report['outputs'][0]['value'], 9)
        binding = run.kernel.env.lookup('n')
        self.assertEqual(binding.value, 'right')
        self.assertNotEqual(binding.meta['epistemic']['claim']['origin'], 'model_proposal')
        self.assertEqual(report['agreement_n'], 0)
        self.assertIsNone(report['agreement'])
        self.assertEqual(report['determinism_summary']['answered_by_model'], 0)
        self.assertEqual(report['determinism_summary']['answered_by_finite_fallback'], 1)
        self.assertEqual(report['determinacy']['asks'][0]['answered_by'], 'finite_fallback')
        self.assertTrue(all(c['origin'] != 'model_proposal' for c in report['epistemic']['claims']))
        self.assertTrue(all(c['passed'] for c in report['evidence']['checks']))
        self.assertTrue(any(t.get('answered_by') == 'model' for t in run.trace))

    def test_no_opt_in_preserves_failure(self):
        _, report, apps = self.run_source(SOURCE.replace(', fallback_choices=["partial", "right"]', ''))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(report['outputs'], [])

    def test_lock_replay_and_resume_never_reach_a_provider(self):
        _, report, apps = self.save()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.requests), 2)
        lock = K.make_lock(str(self.folder))
        replay = K.replay(lock)
        self.assertTrue(replay['ok'], replay)
        self.assertTrue(replay['evidence_match'])
        self.assertEqual(replay['calls'], 0)
        self.assertEqual(replay['report']['determinism_summary']['answered_by_finite_fallback'], 1)
        _, resumed, apps = self.run_source(folder=self.folder)
        self.assertEqual(resumed['status'], 'done', resumed.get('error'))
        self.assertEqual(apps.requests, [])
        self.assertEqual(resumed['fingerprint'], report['fingerprint'])

    def test_resource_unavailable_budget_effect_and_internal_abort_without_next_candidate(self):
        for error in [S.SymblicError('review refusal', kind=k) for k in
                      ('resource', 'unavailable', 'budget', 'effect')] + [RuntimeError('review fault'), MemoryError()]:
            with self.subTest(error=type(error).__name__, kind=getattr(error, 'kind', None)):
                seen = []

                class Refuse(R.Run):
                    def _checked(self, statement, env):
                        value = env.lookup('n').value
                        seen.append(value)
                        if value == 'partial':
                            raise error
                        return super()._checked(statement, env)

                _, report, apps = self.run_source(cls=Refuse)
                self.assertEqual(report['status'], 'failed', report)
                self.assertEqual(report['outputs'], [])
                self.assertNotIn('right', seen)
                self.assertEqual(len(apps.requests), 2)

    def test_stop_between_candidate_bind_and_check_refuses_without_next_candidate(self):
        seen = []

        class Stop(R.Run):
            def _bind(self, env, name, value, ty, statement, klass, weight, meta=None):
                result = super()._bind(env, name, value, ty, statement, klass, weight, meta)
                if name == 'n':
                    seen.append(value)
                    if value == 'partial':
                        self.stop.set()
                return result

        _, report, apps = self.run_source(cls=Stop)
        self.assertEqual(report['status'], 'stopped')
        self.assertEqual(report['outputs'], [])
        self.assertNotIn('right', seen)
        self.assertEqual(len(apps.requests), 2)

    def test_interrupted_fallback_resumes_from_recorded_calls_only(self):
        class Interrupted(R.Run):
            def _checked(self, statement, env):
                if env.lookup('n').value == 'partial':
                    raise R.Stopped()
                return super()._checked(statement, env)

        self.folder.mkdir()
        (self.folder / 'program.sym').write_text(SOURCE)
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': OPTIONS}))
        _, stopped, apps = self.run_source(cls=Interrupted, folder=self.folder)
        self.assertEqual(stopped['status'], 'stopped')
        self.assertEqual(stopped['outputs'], [])
        self.assertEqual(len(apps.requests), 2)
        _, resumed, apps = self.run_source(folder=self.folder)
        self.assertEqual(resumed['status'], 'done', resumed.get('error'))
        self.assertEqual(resumed['outputs'][0]['value'], 9)
        self.assertEqual(apps.requests, [])
        self.assertEqual(resumed['determinism_summary']['answered_by_finite_fallback'], 1)

    def test_recursive_candidate_function_is_refused_before_dispatch(self):
        source = SOURCE.replace(BODY, 'if n = "right" then 3 * x else twice(x)')
        _, report, apps = self.run_source(source)
        self.assertEqual(report['status'], 'failed', report)
        self.assertEqual(apps.requests, [])

    def test_context_overflow_does_not_become_a_host_answer(self):
        _, report, apps = self.run_source(options={'budget': 100})
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'context')
        self.assertEqual(apps.requests, [])
        self.assertEqual(report['outputs'], [])

    def test_authored_menu_limits_types_duplicates_and_dynamic_values_refuse_pre_dispatch(self):
        for choice in ['[]', '["right", "right"]', '[true, "right"]', '[0, "right"]', '["unlisted", "right"]',
                       '[' + ', '.join(json.dumps(str(i)) for i in range(1, 18)) + ']', '["partial", secret]']:
            with self.subTest(choice=choice):
                source = 'given secret: Text = "right".\n' + SOURCE.replace('["partial", "right"]', choice)
                _, report, apps = self.run_source(source)
                self.assertEqual(report['status'], 'failed', report)
                self.assertEqual(apps.requests, [])

    def test_text_answer_constraints_apply_before_provider_dispatch(self):
        for menu in ['["too many words", "right"]', '["", "right"]', '["  right  "]']:
            with self.subTest(menu=menu):
                source = ('ask n: Text up to 1 words "Choose n." with retries=0, fallback_choices='
                          + menu + '.\nensure n != "bad" else retry.\nshow n.')
                _, report, apps = self.run_source(source)
                self.assertEqual(report['status'], 'failed', report.get('error'))
                self.assertEqual(apps.requests, [])

    def test_real_range_digit_exponent_and_work_limits_are_inconclusive(self):
        for expression, limit in [('sum(1..100001)', 100000), ('10 ^ 100001', 100000),
                                  ('10 ^ 100000.5', 100000),
                                  ('10 ^ 4001', 100000), ('len([1] * 100001)', 100000),
                                  ('round(1, 4000)', 100000), ('sum(1..5000)', 1000)]:
            with self.subTest(expression=expression):
                source = SOURCE.replace(BODY, 'if n = "partial" then (' + expression + ') else (' + BODY + ')')
                _, report, apps = self.run_source(source, options={'max_steps': limit})
                self.assertEqual(report['status'], 'failed', report.get('error'))
                self.assertIn(report['error']['kind'], ('resource', 'budget'))
                self.assertEqual(report['outputs'], [])
                self.assertEqual(len(apps.requests), 2)
                self.assertTrue(all(b['name'] != 'n' for b in report['bindings']))

    def test_preflight_work_limit_is_inconclusive_before_any_call(self):
        _, report, apps = self.run_source(options={'max_steps': 1})
        self.assertEqual(report['status'], 'failed')
        self.assertIn(report['error']['kind'], ('resource', 'budget'))
        self.assertEqual(apps.requests, [])

    def test_unresolved_dynamic_and_process_calls_in_function_checks_refuse_pre_dispatch(self):
        for body in ['missing(x)', 'eval("n * x")', 'js_run("", "")', 'js_test("", [])',
                     '"{js_run(x, x)}"']:
            with self.subTest(body=body):
                source = SOURCE.replace(BODY, body)
                _, report, apps = self.run_source(source)
                self.assertEqual(report['status'], 'failed', report)
                self.assertEqual(apps.requests, [])

    def test_callable_defaults_and_transitive_helpers_refuse_pre_dispatch(self):
        for prelude in ['function hidden(x = eval("3")) = x.\n',
                        'function helper(x) = eval("3").\nfunction hidden(x = 3) = helper(x).\n',
                        'routine helper() do\n ask answer: Int "unexpected".\n return answer.\nend.\n'
                        'function hidden(x = 3) = helper().\n']:
            with self.subTest(prelude=prelude):
                source = prelude + SOURCE.replace(BODY, 'hidden() * x')
                _, report, apps = self.run_source(source)
                self.assertEqual(report['status'], 'failed', report)
                self.assertEqual(apps.requests, [])

    def test_two_checks_and_effectful_retry_window_refuse_pre_dispatch(self):
        for source in [SOURCE.replace('let answer', 'ensure n != "bad" else retry.\nlet answer'),
                       SOURCE.replace('function twice', 'show n.\nfunction twice'),
                       SOURCE.replace('function twice', 'ask other: Int "unexpected".\nfunction twice')]:
            with self.subTest(source=source):
                _, report, apps = self.run_source(source)
                self.assertEqual(report['status'], 'failed', report)
                self.assertEqual(apps.requests, [])

    def test_domain_failure_candidate_can_be_rejected_without_inconclusive_claim(self):
        source = SOURCE.replace(BODY, 'if n = "partial" then 1 / 0 else (' + BODY + ')')
        _, report, apps = self.run_source(source)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['outputs'][0]['value'], 9)
        self.assertEqual(len(apps.requests), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
