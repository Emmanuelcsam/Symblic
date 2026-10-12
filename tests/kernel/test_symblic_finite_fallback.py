"""Finite native fallback: temporary stores/fake providers; no real dispatch."""
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from symblic.kernel import language as S
from symblic.kernel import evidence as E
from symblic.kernel import run as R

PREFIX = 'use profile=verified, determine=false, solve=false, effort=low, retries=1.\n'
SOURCE = (PREFIX + 'ask choice: Text "Select" by "fake:unit" with fallback_choices=["bad", "good"].\n'
          'function double(n: Int) -> Int = if choice = "good" then n*2 else n.\n'
          'ensure choice = choice and double(2)=4 and double(3)=6 else retry.\n'
          'show double(4).\n')

class Apps:
    def __init__(self, answer='bad'):
        self.answer, self.calls = answer, []
    def call(self, req):
        self.calls.append(req)
        return {'ok': True, 'json': {'answer': self.answer}}

class FiniteFallback(unittest.TestCase):
    def execute(self, source=SOURCE, **opts):
        app = Apps()
        run = R.Run(source, {}, app, {'by': 'fake:unit', 'max_calls': 20, **opts})
        return run, run.execute(), app

    def test_source_order_first_pass_not_uniqueness(self):
        source = (PREFIX + 'ask x: Text "Pick" with fallback_choices=["second", "first"].\n'
                  'ensure x in ["first", "second"] else retry.\nshow x.\n')
        run, report, apps = self.execute(source)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(run.kernel.env.lookup('x').value, 'second')
        self.assertEqual(report['finite_fallbacks'][0]['evaluated_count'], 1)
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(run.kernel.env.lookup('x').meta['finite_fallback']['uniqueness'], 'not_established')
        self.assertEqual(report['determinacy']['asks'][0]['status'], 'unassessed')

    def test_pure_receipt_matches_binding_and_report(self):
        run, report, apps = self.execute()
        rows = S.parse(SOURCE)['statements']
        ask, ensure = rows[1], rows[3]
        expected = R.finite_fallback_receipt(ask, ensure, 2,
            source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(), kernel_id=S.kernel_id()['id'])
        binding = run.kernel.env.lookup('choice')
        self.assertEqual(binding.meta['finite_fallback'], expected)
        row = report['finite_fallbacks'][0]
        self.assertEqual(row['receipt_sha256'], E.digest(expected))
        self.assertEqual(row['selected_value_hash'], binding.hash)
        self.assertEqual(row['check_id'], report['evidence']['checks'][0]['id'])
        self.assertEqual(report['outputs'][0]['value'], 8)
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(report['calls'], 2)
        for index in (True, False, 0, 3, 1.0):
            with self.assertRaises(S.SymblicError):
                R.finite_fallback_receipt(ask, ensure, index, source_sha256='x', kernel_id='x')

    def test_all_fail_removes_trial_bindings_and_functions(self):
        source = SOURCE.replace('then n*2', 'then n')
        run, report, apps = self.execute(source)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'check')
        self.assertEqual(report['finite_fallbacks'][0]['status'], 'exhausted')
        self.assertEqual(report['finite_fallbacks'][0]['evaluated_count'], 2)
        self.assertIsNone(run.kernel.env.lookup('choice'))
        self.assertNotIn('double', run.kernel.functions)
        self.assertEqual(report['evidence']['checks'], [])
        self.assertEqual(report['outputs'], [])
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(sum(t['status']=='rejected' for t in run.trace), 3)

    def test_domain_error_and_wrong_return_type_are_not_adopted(self):
        for bad in ('n/0', '[n][4]', '"not an Int"'):
            with self.subTest(bad=bad):
                source = SOURCE.replace('then n*2 else n.', 'then n*2 else '+bad+'.')
                run, report, apps = self.execute(source)
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(run.kernel.env.lookup('choice').value, 'good')
                self.assertEqual(len(apps.calls), 2)

    def test_all_menus_preflight_before_earlier_model_call(self):
        source = (PREFIX + 'ask earlier: Text "Earlier".\n'
                  'ask later: one of {"valid", "other"} "Later" with fallback_choices=["invalid"].\n'
                  'ensure later="valid" else retry.\n')
        _, report, apps = self.execute(source)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'type')
        self.assertEqual(apps.calls, [])

    def test_transitive_recursive_closure_rejected_before_calls(self):
        source = (PREFIX + 'function recurse(n: Int)->Int = recurse(n).\n'
                  'ask x: Text "x" with fallback_choices=["ok"].\n'
                  'function nested(n: Int)->Int = recurse(n).\n'
                  'ensure x=x and nested(2)=4 else retry.\n')
        _, report, apps = self.execute(source)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('recursive', report['error']['message'])
        self.assertEqual(apps.calls, [])

    def test_literal_braces_and_exact_normalization_collisions_preserved(self):
        source = (PREFIX + 'ask x: Text "Pick" with fallback_choices=["\\{x\\}", "X"].\n'
                  'ensure x="\\{x\\}" else retry.\nshow x.\n')
        run, report, _ = self.execute(source)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(run.kernel.env.lookup('x').value, '{x}')
        self.assertEqual(report['finite_fallbacks'][0]['selected_index'], 1)

    def test_two_steps_have_independent_model_and_finite_counters(self):
        source = SOURCE.replace('show double(4).', '') + (
            'ask second: Text "Second" from choice with fallback_choices=["bad", "yes"].\n'
            'function triple(n: Int)->Int = if second="yes" then double(n)+n else n.\n'
            'ensure second=second and triple(3)=9 else retry.\nshow triple(4).\n')
        run, report, apps = self.execute(source)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(apps.calls), 4)
        self.assertEqual([r['evaluated_count'] for r in report['finite_fallbacks']], [2, 2])
        self.assertEqual(report['determinism_summary']['answered_by_finite_fallback'], 2)
        self.assertEqual(report['outputs'][0]['value'], 12)
        self.assertTrue(all(r['passed'] for r in report['evidence']['checks']))
        self.assertEqual(len(report['evidence']['checks']), 2)
        self.assertEqual(run.kernel.env.lookup('choice').value, 'good')

    def test_prior_accepted_model_dependency_survives_host_selection(self):
        source = (PREFIX + 'ask accepted: Text "Base".\n' + SOURCE[len(PREFIX):].replace(
            'by "fake:unit" with', 'from accepted by "fake:unit" with'))
        run, report, _ = self.execute(source)
        self.assertEqual(report['status'], 'done', report.get('error'))
        roots = run.kernel.env.lookup('choice').meta['epistemic']['assessment']['conditional_on']
        self.assertEqual([r['origin'] for r in roots], ['model_proposal'])
        self.assertEqual(report['determinism_summary']['answered_by_model'], 1)
        self.assertEqual(report['determinism_summary']['answered_by_finite_fallback'], 1)

    def test_malformed_model_reply_does_not_masquerade_as_predicate_exhaustion(self):
        source = SOURCE.replace('ask choice: Text', 'ask choice: one of {"bad", "good"}')
        apps = Apps('not listed')
        run = R.Run(source, {}, apps)
        report = run.execute()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['finite_fallbacks'], [])
        self.assertIsNone(run.kernel.env.lookup('choice'))
        self.assertEqual(len(apps.calls), 2)

if __name__ == '__main__':
    unittest.main()
