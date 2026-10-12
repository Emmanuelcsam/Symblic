"""Observed lineage and missing attribution: pure receipts, no providers."""
import unittest

from symblic.kernel import language as S
from symblic.kernel import evidence as E


class LineageEvidence(unittest.TestCase):
    def observation(self, requested, observed='', **extra):
        return E.observation(S.parse_applicator(requested), {'model': observed, 'node': 'fixture'}, 2,
                             request='r', capsule='c', round_no=1, statement='s', **extra)

    def evidence(self, *rows):
        return E.evidence(rows, source='source', line=1, name='x', ty={'k': 'int'}, value=2)

    def test_observed_model_overrides_requested_wrapper_without_erasing_it(self):
        row = self.observation('copilot:gpt-5', 'claude-sonnet-4.5')
        self.assertEqual('copilot:gpt-5', row['app'])
        self.assertEqual('claude-sonnet-4.5', row['model'])
        self.assertEqual('anthropic', row['family'])
        self.assertEqual(['anthropic'], row['lineages'])
        self.assertEqual('observed_model', row['lineage_basis'])

    def test_missing_observed_model_keeps_inference_distinct(self):
        row = self.observation('claude:claude-sonnet-4.5')
        self.assertEqual('', row['model'])
        self.assertEqual('requested_app', row['lineage_basis'])
        self.assertEqual([0], self.evidence(row)['missing_provenance'])

    def test_unknown_observed_model_does_not_borrow_wrapper_maker(self):
        # a front-end of several makers that reports a model nobody can place: the requested model's maker is
        # not borrowed (Fable, carrying root's patch: the wrapper here is copilot, see the next test for why)
        row = self.observation('copilot:claude-sonnet-4.5', 'unrecognized-deployment')
        self.assertEqual([], row['lineages'])
        self.assertEqual('unattributed', row['family'])
        self.assertEqual('observed_model', row['lineage_basis'])

    def test_an_echoed_alias_does_not_erase_a_single_maker_engine(self):
        # symblic_apply reports `row.get('model') or app.get('model')`: for claude:haiku that is the alias
        # 'haiku', which names no lineage by itself. The requested label still does.
        for requested, observed, family in [('claude:haiku', 'haiku', 'anthropic'), ('codex', 'gpt-6-astra', 'openai'),
                                            ('gemini:pro', 'pro', 'google'), ('gemini', 'gemini', 'google'),
                                            ('claude', 'us.anthropic.some-deployment', 'anthropic')]:
            with self.subTest(requested=requested, observed=observed):
                row = self.observation(requested, observed)
                self.assertEqual(family, row['family'])
                self.assertEqual(observed, row['model'])
        self.assertEqual('requested_app', self.observation('claude:haiku', 'haiku')['lineage_basis'])
        self.assertEqual('observed_model', self.observation('codex', 'gpt-6-astra')['lineage_basis'])

    def test_unattributed_is_never_a_shared_family_in_new_or_old_rows(self):
        rows = [self.observation('copilot:unknown-a'), self.observation('ollama:unknown-b')]
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                if legacy:
                    rows = [{k: v for k, v in r.items() if k != 'lineages'} for r in rows]
                ev = self.evidence(*rows)
                self.assertFalse(any(x['kind'] == 'family' for x in ev['shared_dependencies']))
                self.assertEqual('not_established', ev['independence'])

    def test_distill_base_and_teacher_both_survive_shared_dependency_report(self):
        distill = self.observation('ollama:deepseek-r1:7b', 'deepseek-r1:7b')
        base = self.observation('ollama:qwen2.5:7b', 'qwen2.5:7b')
        teacher = self.observation('ollama:deepseek-r1:671b', 'deepseek-r1:671b')
        ev = self.evidence(distill, base, teacher)
        shared = {x['id']: x['observations'] for x in ev['shared_dependencies'] if x['kind'] == 'family'}
        self.assertEqual({'alibaba': [0, 1], 'deepseek': [0, 2]}, shared)
        self.assertEqual(['alibaba', 'deepseek'], distill['lineages'])
        self.assertEqual('not_established', ev['independence'])

    def test_one_observation_does_not_share_a_dependency_with_itself(self):
        row = self.observation('ollama:qwen2.5:7b', 'qwen2.5:7b')
        row['lineages'] *= 2
        ev = self.evidence(row)
        self.assertFalse(any(x['kind'] == 'family' for x in ev['shared_dependencies']))


if __name__ == '__main__':
    unittest.main()
