"""Contract boundaries, with synthetic replies and temporary replay stores only.

Confirmed defects belong in docs/reference/reinforcements/contract-audit.md,
not in expected-failure tests that could hide a future regression.
"""

import itertools
import json
import os
import tempfile
import unittest

from symblic.kernel import language as S
from symblic.kernel import run as SR


class FakeApplicators:
    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': self.answer(request)}, 'ms': 0}


class ReinforcementContracts(unittest.TestCase):
    def execute(self, source, answer, folder=None, **options):
        apps = FakeApplicators(answer)
        run = SR.Run(source, applicators=apps, folder=folder,
                     options={'by': 'fake:a', 'parallel': 1, **options})
        return run.execute(), apps

    def binding(self, report, name='x'):
        return next(b for b in report['bindings'] if b['name'] == name)

    def assertDone(self, report):
        self.assertEqual(report['status'], 'done', report.get('error'))

    def test_type_valid_wrong_unanimity_needs_a_truth_check(self):
        source = ('group g = ["fake:a", "fake:b", "fake:c"].\n'
                  'ask x: Int in 0..10 "What is 4 + 4?" by g '
                  'with effort=low, strict, agree=1\n')
        unchecked, apps = self.execute(source, lambda _: 7)
        self.assertDone(unchecked)
        self.assertEqual(len(apps.requests), 3)
        self.assertEqual(self.binding(unchecked)['value'], 7)
        self.assertEqual(self.binding(unchecked)['meta']['agreement'], 1)
        checked, _ = self.execute(source + 'assert x = 4 + 4.\n', lambda _: 7)
        self.assertEqual(checked['status'], 'failed')
        self.assertEqual(checked['error']['kind'], 'check')
        self.assertEqual(checked['error']['line'], 3)
        # A fingerprint is output identity, not a certificate of successful checks.
        self.assertEqual(checked['fingerprint'], unchecked['fingerprint'])

    def test_tie_threshold_is_inclusive_and_strict_uses_that_threshold(self):
        source = ('group g = ["fake:a", "fake:b"].\n'
                  'ask x: Int "Choose." by g with effort=low, strict')
        answer = lambda req: 9 if req['app']['model'] == 'a' else 8
        # 2026-10-02 (semantics review K6): a tie at the top is contested, so `strict` stops on it; without
        # strict the tie is still decided the same way every time (applicator order) and reported
        tied, _ = self.execute(source + '\n', answer)
        self.assertEqual(tied['status'], 'failed')
        self.assertIn('a tie between the top answers', tied['error']['message'])
        accepted, _ = self.execute(source.replace(', strict', '') + '\n', answer)
        self.assertDone(accepted)
        binding = self.binding(accepted)
        self.assertEqual(binding['value'], 9)
        self.assertEqual(binding['meta']['agreement'], 0.5)
        self.assertEqual(binding['meta']['distinct'], 2)
        self.assertTrue(binding['meta']['contested'])
        rejected, _ = self.execute(source + ', agree=0.5001\n', answer)
        self.assertEqual(rejected['status'], 'failed')
        self.assertEqual(rejected['error']['kind'], 'check')
        self.assertIn('did not agree', rejected['error']['message'])

    def test_tie_breaking_ignores_arrival_order_including_final_canonical_tie(self):
        def sample(value, order):
            return {'value': value, 'hash': S.fingerprint(value), 'app': str(value),
                    'order': order, 'weight': 1}
        for rows, winner in (([sample(9, 0), sample(8, 1), sample(7, 2)], 9),
                             ([sample('z', 0), sample('a', 0)], 'a')):
            for permutation in itertools.permutations(rows):
                with self.subTest(permutation=permutation):
                    result = S.consensus(permutation, threshold=0.6)
                    self.assertEqual(result['value'], winner)
                    self.assertTrue(result['contested'])
                    self.assertEqual(result['distinct'], len(rows))

    def test_nfc_text_votes_merge_but_compatibility_characters_stay_distinct(self):
        answers = ['e\u0301\r\nnext  ', 'é\nnext']
        report, _ = self.execute('ask x: Text "Text." with effort=low, votes=2\n',
                                 lambda req: answers[req['sample']])
        self.assertDone(report)
        binding = self.binding(report)
        self.assertEqual(binding['value'], 'é\nnext')
        self.assertEqual(binding['meta']['distinct'], 1)
        self.assertEqual(binding['meta']['agreement'], 1)
        self.assertNotEqual(S.fingerprint('①'), S.fingerprint('1'))
        self.assertNotEqual(S.fingerprint('a b'), S.fingerprint('ab'))

    def test_coercion_agreement_does_not_imply_raw_reply_identity(self):
        answers = [{'LABEL': 'RED!', 'ignored': 1}, {'label': 'red', 'ignored': 2}]
        report, _ = self.execute(
            'ask x: Record {label: one of {red, blue}} "Label." '
            'with effort=low, votes=2, vote=whole\n',
            lambda req: answers[req['sample']])
        self.assertDone(report)
        self.assertNotEqual(answers[0], answers[1])
        self.assertEqual(self.binding(report)['value'], {'label': 'red'})
        self.assertEqual(self.binding(report)['meta']['agreement'], 1)

    def test_ambiguous_enum_normalization_is_rejected_even_for_exact_spelling(self):
        ty = {'k': 'enum', 'options': ['a-b', 'a_b']}
        for raw in ('a-b', 'a_b', 'A B'):
            with self.subTest(raw=raw):
                with self.assertRaises(S.SymblicError) as caught:
                    S.coerce(raw, ty)
                self.assertEqual(caught.exception.kind, 'type')

    def test_bool_cannot_vote_as_an_integer(self):
        report, apps = self.execute('ask x: Int "Count." with effort=low, retries=0\n',
                                    lambda _: True)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('must be a number', report['error']['message'])
        self.assertEqual(len(apps.requests), 1)

    def test_key_equivalence_is_only_the_equivalence_the_author_requested(self):
        answers = ['x + 1', '1']
        report, _ = self.execute(
            'ask x: Text "A formula." with effort=low, votes=2, key=eval(it, x=0)\n',
            lambda req: answers[req['sample']])
        self.assertDone(report)
        self.assertEqual(self.binding(report)['meta']['distinct'], 1)
        checked, apps = self.execute('show eval("x + 1", x=2).\nshow eval("1", x=2).\n',
                                     lambda _: self.fail('kernel evaluation called an applicator'))
        self.assertDone(checked)
        self.assertEqual(apps.requests, [])
        self.assertEqual([output['value'] for output in checked['outputs']], [3, 1])

    def test_key_failures_abstain_without_repair_and_agreement_excludes_them(self):
        answers = ['4 + 4', '1 / 0', 'missing_name']
        report, apps = self.execute(
            'ask x: Text "Formula for eight." with effort=low, votes=3, retries=2, '
            'key=eval(it), strict, agree=1\n', lambda req: answers[req['sample']])
        self.assertDone(report)
        meta = self.binding(report)['meta']
        self.assertEqual(len(apps.requests), 3)
        self.assertEqual(meta['agreement'], 1)
        self.assertEqual([s['ok'] for s in meta['samples']], [True, False, False])
        self.assertTrue(all('red flag: key failed' in s['error'] for s in meta['samples'][1:]))

    def test_invalid_samples_have_bounded_independent_repair_budgets(self):
        for retries, attempts in ((0, 1), (1, 2), (2, 3), (99, 6)):
            with self.subTest(retries=retries):
                report, apps = self.execute(
                    f'ask x: Int "Count." with effort=low, votes=2, retries={retries}\n',
                    lambda _: 'invalid')
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['asks'], 1)
                self.assertEqual(report['calls'], 2 * attempts)
                self.assertEqual(len(apps.requests), 2 * attempts)
                self.assertEqual(len({req['key'] for req in apps.requests}), 2 * attempts)
                repairs = [req for req in apps.requests if req['sample'] >= 1000]
                self.assertTrue(all('YOUR PREVIOUS REPLY WAS NOT VALID' in req['prompt']
                                    for req in repairs))

    def test_ensure_repair_recomputes_dependencies_without_reasking_unrelated_ask(self):
        source = ('ask fixed: Int "Unrelated." with effort=low, retries=1\n'
                  'ask x: Int "Eight." with effort=low, retries=1\n'
                  'let doubled = x * 2.\nensure doubled = 16 else retry.\nshow doubled.\n')
        answers = iter([99, 7, 8])
        report, apps = self.execute(source, lambda _: next(answers))
        self.assertDone(report)
        self.assertEqual(len(apps.requests), 3)
        self.assertEqual(self.binding(report, 'fixed')['value'], 99)
        self.assertEqual(self.binding(report)['value'], 8)
        self.assertEqual(self.binding(report, 'doubled')['value'], 16)
        self.assertEqual(report['outputs'][0]['value'], 16)
        self.assertIn('doubled = 16', apps.requests[-1]['prompt'])
        self.assertIn('REJECTED BY THE KERNEL', apps.requests[-1]['prompt'])

    def test_zero_ensure_retries_fails_without_a_second_call(self):
        report, apps = self.execute('ask x: Int "Eight." with effort=low, retries=0\n'
                                    'ensure x = 8 else retry.\n', lambda _: 7)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'check')
        self.assertEqual(len(apps.requests), 1)

    def test_replay_reuses_evidence_while_a_fresh_store_can_disagree(self):
        source = 'ask x: Int "Eight." with effort=low\nshow x.\n'
        with tempfile.TemporaryDirectory() as root:
            replay_dir, fresh_dir = (os.path.join(root, part) for part in ('replay', 'fresh'))
            first, _ = self.execute(source, lambda _: 8, folder=replay_dir)
            replay, replay_apps = self.execute(source, lambda _: 9, folder=replay_dir)
            fresh, fresh_apps = self.execute(source, lambda _: 9, folder=fresh_dir)
            for report in (first, replay, fresh):
                self.assertDone(report)
            self.assertEqual(replay_apps.requests, [])
            self.assertEqual((replay['calls'], replay['cached']), (0, 1))
            self.assertTrue(self.binding(replay)['meta']['samples'][0]['cached'])
            self.assertEqual(first['fingerprint'], replay['fingerprint'])
            self.assertEqual((fresh['calls'], fresh['cached']), (1, 0))
            self.assertEqual(len(fresh_apps.requests), 1)
            self.assertNotEqual(first['fingerprint'], fresh['fingerprint'])
            with open(os.path.join(replay_dir, 'calls.jsonl'), encoding='utf-8') as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['reply']['json']['answer'], 8)


if __name__ == '__main__':
    unittest.main()
