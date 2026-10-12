"""symblic.authoring.tighten (the convergence compiler) with fake applicators only: diagnosis, outages, readings, the
clarifier's rewrite and its leak guard."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # the repository root

from symblic.kernel import language as S  # noqa: E402
from symblic.authoring import tighten as T  # noqa: E402

SRC = 'ask d: Number "How long is a marathon?" with effort=low\nshow d.\n'
PANEL = ['claude:haiku', 'codex', 'agy', 'ollama:llama3.2:1b']


class Readers:
    """Capable readers answer in km; llama in miles; agy is in an outage; the clarifier pins the unit."""

    def __init__(self, rewrite='How long is a marathon race, in kilometres?', reads=True):
        self.rewrite, self.reads, self.prompts = rewrite, reads, []

    def call(self, req):
        app, p = req['app']['spec'], req['prompt']
        self.prompts.append((app, p))
        if app == 'agy':
            return {'ok': False, 'error': 'quota: agy is paused until 23:57 (outage)'}
        if 'Rewrite the statement' in p:
            return {'ok': True, 'json': {'answer': {'instruction': self.rewrite, 'assumptions': ['in kilometres']}}}
        extra = {'readings': []} if 'readings' in req['schema']['properties'] else {}
        if 'kilometres' in p:
            return {'ok': True, 'json': {'answer': 42.195, **extra}}
        if self.reads and app == 'claude:haiku' and extra:
            extra = {'readings': ['in kilometres: 42.195', 'in miles: 26.2']}
        return {'ok': True, 'json': {'answer': 26.2 if 'llama' in app else 42.195, **extra}}


class Diagnosis(unittest.TestCase):
    def test_a_listed_reading_makes_an_agreed_ask_ambiguous(self):
        pr = T.probe(SRC, None, ['claude:haiku', 'codex'], Readers(), readings=True)
        a = pr['asks'][0]
        self.assertEqual(a['agreement_all'], 1.0)
        self.assertEqual(a['diagnosis'], 'ambiguous')
        self.assertIn('in miles: 26.2', a['readings'])

    def test_an_outage_is_missing_not_disagreement(self):
        pr = T.probe(SRC, None, ['claude:haiku', 'codex', 'agy'], Readers(reads=False))
        a = pr['asks'][0]
        self.assertEqual(a['missing'], ['agy'])
        self.assertEqual(a['agreement_all'], 1.0)
        self.assertEqual(a['diagnosis'], 'converged')
        pr = T.probe(SRC, None, ['agy'], Readers())
        self.assertEqual(pr['asks'][0]['diagnosis'], 'unreached')

    def test_one_reader_with_a_nuance_does_not_make_an_agreed_ask_ambiguous(self):
        # three agreeing readers, only Haiku lists readings: below the two-reader quorum
        pr = T.probe(SRC, None, ['claude:haiku', 'codex', 'claude:sonnet'], Readers(), readings=True)
        self.assertEqual(pr['asks'][0]['diagnosis'], 'converged')

    def test_a_deviation_another_reader_listed_is_ambiguity(self):
        pr = T.probe(SRC, None, ['claude:haiku', 'codex', 'ollama:llama3.2:1b'], Readers(), readings=True)
        self.assertEqual(pr['asks'][0]['diagnosis'], 'ambiguous')     # llama's 26.2 is Haiku's "in miles: 26.2"

    def test_weak_only_deviation_is_capability(self):
        pr = T.probe(SRC, None, ['claude:haiku', 'codex', 'ollama:llama3.2:1b'], Readers(reads=False))
        self.assertEqual(pr['asks'][0]['diagnosis'], 'capability')


class Tightening(unittest.TestCase):
    def test_rewrite_never_edits_a_nearby_literal_instead_of_the_ask(self):
        source = 'ask x: Text "say \\"hello\\"".\nshow \'say "hello"\'.\n'
        # Escaped source spelling is not an exact replaceable literal; the
        # following show has the old text but is a different statement.
        self.assertIsNone(T.rewrite(source, 1, 'say "hello"', 'changed'))

    def test_rewrite_changes_only_target_instruction_and_keeps_braces_literal(self):
        source = 'ask x: one of {"old", "other"} "old".\nshow "old".\n'
        changed = T.rewrite(source, 1, 'old', 'Choose {old} or {other}')
        self.assertIsNotNone(changed)
        node, text = T.ask_instruction(changed, 1)
        self.assertEqual(text, 'Choose {old} or {other}')
        self.assertEqual(node.type, S.parse(source)['statements'][0].type)
        self.assertTrue(changed.endswith('show "old".\n'))

    def test_probe_clarify_probe_converges_and_proposes_a_candidate(self):
        res = T.tighten(SRC, None, PANEL, Readers(), clarifier='claude:sonnet')
        self.assertTrue(res['changed'])
        self.assertEqual(res['program'], SRC)
        self.assertFalse(res['accepted_changed'])
        self.assertIn('in kilometres', res['candidate_program'])
        self.assertTrue(S.check(res['candidate_program'])['ok'])
        self.assertEqual([h['asks'][0]['diagnosis'] for h in res['history']], ['ambiguous', 'converged'])

    def test_the_clarifier_is_told_the_readings_and_the_knowledge_rule(self):
        readers = Readers()
        T.tighten(SRC, None, PANEL, readers, clarifier='claude:sonnet')
        clar = [p for app, p in readers.prompts if 'Rewrite the statement' in p]
        self.assertEqual(len(clar), 1)
        self.assertIn('in miles: 26.2', clar[0])
        self.assertIn('no more knowledge than the original', clar[0])

    def test_a_rewrite_that_names_the_answer_is_refused(self):
        res = T.tighten(SRC, None, PANEL, Readers(rewrite='How long is a marathon (42.195 km)?'),
                        clarifier='claude:sonnet')
        self.assertFalse(res['changed'])
        self.assertTrue(res['rewrites'][0]['leaks_answer'])

    def test_listing_the_options_of_a_closed_answer_is_not_a_leak(self):
        src = 'ask day: one of {monday, sunday} "What is the first day of the week?" with effort=low\n'

        class Readers:
            def call(self, req):
                app, p = req['app']['spec'], req['prompt']
                if 'Rewrite the statement' in p:
                    return {'ok': True, 'json': {'answer': {
                        'instruction': 'Under ISO 8601, which day starts the week: monday or sunday?',
                        'assumptions': ['ISO 8601']}}}
                extra = {'readings': []} if 'readings' in req['schema']['properties'] else {}
                if 'ISO 8601' not in p and app == 'claude:haiku':
                    extra = {'readings': ['ISO: monday', 'US: sunday']}
                return {'ok': True, 'json': {'answer': 'sunday' if (app == 'codex' and 'ISO' not in p) else 'monday',
                                             **extra}}
        res = T.tighten(src, None, ['claude:haiku', 'codex', 'claude:sonnet'], Readers(), clarifier='claude:opus')
        self.assertFalse(res['rewrites'][0]['leaks_answer'])
        self.assertTrue(res['changed'])

    def test_interpolated_instructions_are_left_for_a_person(self):
        src = 'given race: Text = "marathon".\nask d: Number "How long is a {race}?" with effort=low\n'
        res = T.tighten(src, None, PANEL, Readers(), clarifier='claude:sonnet')
        self.assertFalse(res['changed'])
        self.assertEqual(res['rewrites'], [])


class Papers(unittest.TestCase):
    def test_chained_rewrites_land_in_the_paper_as_the_final_instruction(self):
        paper = ('# T\n\n```symblic\nask d: Number "How long is a marathon?" with effort=low\nshow d.\n```\n')
        texts = ['How long is a marathon race?', 'How long is a marathon race, in kilometres?']

        class Readers:
            n = 0

            def call(self, req):
                p = req['prompt']
                if 'Rewrite the statement' in p:
                    Readers.n += 1
                    return {'ok': True, 'json': {'answer': {'instruction': texts[Readers.n - 1], 'assumptions': ['x']}}}
                extra = {'readings': []} if 'readings' in req['schema']['properties'] else {}
                v = 42.195 if 'kilometres' in p or req['app']['spec'] != 'ollama:llama3.2:1b' else 26.2
                return {'ok': True, 'json': {'answer': v, **extra}}
        res = T.tighten_paper(paper, ['claude:haiku', 'codex', 'ollama:llama3.2:1b'], Readers(), clarifier='claude:sonnet')
        self.assertTrue(res['changed'])
        self.assertIn('in kilometres', res['candidate_paper'])
        self.assertEqual(res['paper'], paper)
        self.assertNotIn('"How long is a marathon?"', res['candidate_paper'])
        self.assertEqual(res['applied'][0]['rewrites'], 2)

    def test_a_paper_is_tightened_in_its_own_code_block(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository root
        with open(os.path.join(root, 'docs', 'reference', 'papers', 'furnace-schedule.symd'), encoding='utf-8') as fh:
            paper = fh.read()
        new = 'List the heating steps of the protocol in order. For a ramp or a cool step, minutes is 0.'

        class Readers:
            def call(self, req):
                app, p = req['app']['spec'], req['prompt']
                if 'Rewrite the statement' in p:
                    assert 'minutes is 0' in p           # the section's rule reached the clarifier
                    return {'ok': True, 'json': {'answer': {'instruction': new, 'assumptions': ['ramp minutes 0']}}}
                extra = {'readings': []} if 'readings' in req['schema']['properties'] else {}
                ramp = 0 if ('For a ramp or a cool step' in p or app == 'codex') else 115
                steps = [{'kind': 'ramp', 'start_c': 25, 'end_c': 600, 'rate_c_per_min': 5, 'minutes': ramp},
                         {'kind': 'hold', 'start_c': 600, 'end_c': 600, 'rate_c_per_min': 0, 'minutes': 120},
                         {'kind': 'cool', 'start_c': 600, 'end_c': 100, 'rate_c_per_min': 3, 'minutes': 0}]
                return {'ok': True, 'json': {'answer': steps, **extra}}
        res = T.tighten_paper(paper, ['claude:haiku', 'codex'], Readers(), clarifier='claude:sonnet')
        self.assertIn('lint', res)
        self.assertTrue(res['changed'])
        self.assertEqual(res['applied'][0]['paper_line'], 31)
        self.assertEqual(res['applied'][0]['instruction'], new)
        self.assertIn(new, res['candidate_paper'])
        from symblic.authoring import paper as P
        self.assertTrue(P.check_paper(res['candidate_paper'])['ok'])


if __name__ == '__main__':
    unittest.main()
