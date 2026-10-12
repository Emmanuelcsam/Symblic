"""Execution-profile contracts; injected fakes, no providers or stores."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import embed as embed  # noqa: E402
from symblic.kernel import profiles as P  # noqa: E402
from symblic.kernel.run import Run  # noqa: E402


class Apps:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def call(self, request):
        self.calls.append(request)
        return {'ok': True, 'json': {'answer': self.answers[(len(self.calls) - 1) % len(self.answers)]}}


def execute(source, answers=(1,), **options):
    apps = Apps(answers)
    result = Run(source, applicators=apps, options={'by': 'fake:a', 'retries': 0,
                 'parallel': 1, **options}, folder=None).execute()
    return result, apps


class Profiles(unittest.TestCase):
    def test_typo_and_implicit_prose_make_zero_calls(self):
        for prefix in ('use profile=explicit.\n', 'use profile=verified.\n'):
            for instruction in ('asertt false.', 'Please decide the answer.'):
                result, apps = execute(prefix + instruction)
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(apps.calls, [])
                self.assertFalse(S.check(prefix + instruction)['ok'])

    def test_legacy_prose_remains_runnable_and_disclosed(self):
        result, apps = execute('Please decide the answer.', ('yes',), votes=1)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(len(apps.calls), 1)
        self.assertTrue(any(w.get('code') == 'SYM_IMPLICIT_ASK' for w in result['warnings']))

    def test_host_can_strengthen_but_not_weaken_source(self):
        for source, profile in [('asertt false.', 'explicit'),
                                ('use profile=verified.\nasertt false.', 'legacy')]:
            result = embed.run(source, options={'profile': profile})
            self.assertEqual(result['calls'], 0)
            self.assertEqual(result['status'], 'failed')

    def test_profiles_cannot_change_inside_a_run(self):
        for source in ('use profile=verified.\nuse profile=legacy.',
                       'if true then\nuse profile=verified.\nend', 'use profile=nonsense.'):
            self.assertFalse(S.check(source)['ok'], source)

    def test_boolean_query_is_still_a_query_and_obligation_fails(self):
        result, _ = execute('use profile=verified.\n1 = 2.')
        self.assertEqual(result['status'], 'done')
        self.assertTrue(any(w.get('code') == 'SYM_BOOLEAN_QUERY' for w in result['warnings']))
        result, _ = execute('use profile=verified.\nassert 1 = 2.')
        self.assertEqual(result['status'], 'failed')

    def test_transitive_function_effects_and_default_argument_refused(self):
        head = ('use profile=verified.\nroutine r() -> Int do\n'
                'ask x: Int "Give a number." with effort=low\nreturn x.\nend\n')
        for tail in ('function g() = r().\nfunction f() = g().\nshow f().',
                     'function f(x = r()) = x.\nshow f().'):
            result, apps = execute(head + tail)
            self.assertEqual(result['status'], 'failed', result)
            self.assertEqual(len(apps.calls), 0)
            self.assertEqual(result['error']['kind'], 'effect')

    def test_pure_recursion_and_legacy_effect_capability_preserved(self):
        source = 'function f(x) = if x <= 0 then 0 else f(x-1) + 1.\nshow f(3).'
        result, apps = execute('use profile=verified.\n' + source)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(apps.calls, [])
        source = ('routine r() -> Int do\nask x: Int "Give a number." with effort=low\nreturn x.\nend\n'
                  'function f() = r().\nshow f().')
        result, apps = execute(source)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(len(apps.calls), 1)

    def test_external_adapters_are_not_reported_as_pure_functions(self):
        from unittest.mock import patch
        from symblic.js import check as JS
        source = 'function js_value() = js_run("function a() {{return 1;}}", "a()").\nshow js_value().'
        with patch.object(JS, 'evaluate', side_effect=AssertionError('must not execute while checking')):
            checked = S.check('use profile=verified.\n' + source)
            self.assertFalse(checked['ok'])
            self.assertIn('external_adapter', str(checked['errors']))
            legacy = S.check(source)
            self.assertTrue(legacy['ok'])
            self.assertIn('external_adapter', str(legacy['warnings']))

    def test_verified_contested_answer_cannot_feed_next_step(self):
        source = ('use profile=verified.\nask n: Int "A number." with effort=low, votes=2, '
                  'by=["fake:a", "fake:b"], strict=false\nask m: Int "Next." from n with effort=low')
        result, apps = execute(source, (1, 2))
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(len(apps.calls), 2)


class Transformations(unittest.TestCase):
    TY = {'k': 'record', 'fields': [('answer', {'k': 'int'})]}

    def test_extra_caveat_cannot_silently_disappear(self):
        source = 'use profile=verified.\nask r: Record {answer: Int} "Read." with effort=low'
        result, apps = execute(source, ({'answer': 3, 'warning': 'unknown'},))
        self.assertEqual(result['status'], 'failed', result)
        self.assertIn('drop_extra_field', str(result['error']))
        self.assertEqual(len(apps.calls), 1)

    def test_legacy_dropped_fields_have_receipts(self):
        receipt = {}
        self.assertEqual(P.coerce({'answer': 3, 'warning': 'unknown'}, self.TY, receipt=receipt), {'answer': 3})
        self.assertEqual(receipt['dropped_paths'], ['answer.warning'])
        self.assertFalse(receipt['changes'][0]['declared'])
        self.assertEqual(len(receipt['raw_sha256']), 64)

    def test_nested_extra_and_fuzzy_keys_refused(self):
        ty = {'k': 'list', 'of': self.TY}
        for raw in ([{'answer': 3, 'warning': 'unknown'}], [{' Answer ': 3}]):
            with self.assertRaises(S.SymblicError):
                P.coerce(raw, ty, policy='strict')

    def test_scalars_require_declared_representation(self):
        for raw, ty in [(1, {'k': 'bool'}), ('YES', {'k': 'bool'}),
                        (' yes ', {'k': 'enum', 'options': ['yes', 'no']}),
                        ('The number is 3', {'k': 'int'}), (False, {'k': 'text'})]:
            with self.assertRaises(S.SymblicError):
                P.coerce(raw, ty, policy='strict')

    def test_explicit_rounding_and_set_equivalence_preserved(self):
        receipt = {}
        self.assertEqual(P.coerce('3.14159', {'k': 'number', 'places': 2}, policy='strict', receipt=receipt),
                         S.Fraction(157, 50))
        self.assertTrue(receipt['changes'])
        self.assertTrue(receipt['changes'][0]['declared'])
        self.assertEqual(len(P.coerce([1, 1], {'k': 'set', 'of': {'k': 'int'}}, policy='strict')), 1)

    def test_receipt_is_attached_to_observation(self):
        result, _ = execute('ask x: Record {answer: Int} "Read." with effort=low',
                            ({'answer': 3, 'warning': 'unknown'},))
        self.assertEqual(result['status'], 'done', result.get('error'))
        obs = result['bindings'][0]['meta']['evidence']['observations'][0]
        self.assertEqual(obs['transformation']['dropped_paths'], ['answer.warning'])


if __name__ == '__main__':
    unittest.main()
