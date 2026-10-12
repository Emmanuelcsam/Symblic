"""Tightening fidelity/adoption boundaries; invented fixtures and fake readers only."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.authoring import tighten as T


ORIGINAL = 'ask value: Number "Return the exact total in dollars." with effort=low\n'
CANDIDATE = 'ask value: Number "Return the total in dollars, rounded to a whole number." with effort=low\n'
REQUIREMENTS = [{'id': 'exact-total', 'text': 'Preserve the exact total without rounding.'}]


def obligations():
    return [
        {'id': 'fractional-total', 'kind': 'positive', 'split': 'heldout',
         'requirement_ids': ['exact-total'], 'fixture': {'total': '19.60'}, 'expected': '19.60'},
        {'id': 'reject-rounded', 'kind': 'negative', 'split': 'heldout',
         'requirement_ids': ['exact-total'], 'fixture': {'total': '19.60', 'forbidden': '20'}, 'expected': False},
    ]


def finite_rounding_checker(original, candidate, obligation):
    # Deliberately narrow fixture executor, not a claimed English interpreter.
    if candidate not in (ORIGINAL, CANDIDATE):
        return {'status': 'unknown', 'reason': 'This fixture interpreter does not support the candidate'}
    result = '20' if candidate == CANDIDATE else obligation['fixture']['total']
    observed = result if obligation['kind'] == 'positive' else result == obligation['fixture']['forbidden']
    return {'status': 'pass' if observed == obligation['expected'] else 'fail',
            'reason': 'Compared exact fixture result', 'evidence': {'observed': observed}}


def pass_checker(original, candidate, obligation):
    return {'status': 'pass', 'reason': 'The declared finite fixture passed'}


class FidelityAudit(unittest.TestCase):
    def test_rounding_away_difference_fails_even_with_explicit_adoption(self):
        result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=REQUIREMENTS,
                                   obligations=obligations(), fidelity_checker=finite_rounding_checker,
                                   checker_id='finite-rounding-fixture-v1')
        self.assertEqual(result['program'], ORIGINAL)
        self.assertEqual(result['candidate_program'], CANDIDATE)
        self.assertEqual(result['fidelity']['status'], 'fail')
        self.assertEqual([r['status'] for r in result['fidelity']['checks']], ['fail', 'fail'])
        adopted = T.adopt(result, T.adoption_token(result, 'authenticated-owner'))
        self.assertEqual(adopted['program'], ORIGINAL)
        self.assertEqual(adopted['adoption']['reason'], 'failed_fidelity_obligation')

    def test_finite_success_neither_adopts_nor_proves_meaning(self):
        result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=REQUIREMENTS,
                                   obligations=obligations(), fidelity_checker=pass_checker, checker_id='fake-finite-v1')
        self.assertEqual(result['fidelity']['status'], 'pass')
        self.assertEqual(result['program'], ORIGINAL)
        self.assertEqual(result['adoption']['status'], 'not_requested')
        self.assertEqual(result['fidelity']['meaning_preserved'], 'not_established')

    def test_faithful_clarification_can_be_explicitly_adopted(self):
        source = 'term total means "gross amount before discounts".\nask v: Number "What is the total?"\n'
        candidate = source.replace('What is the total?', 'What is the gross amount before discounts?')
        requirements = [{'id': 'gross', 'text': 'Use the defined gross total.'}]
        checks = [{'id': 'defined-term', 'kind': 'positive', 'split': 'heldout', 'requirement_ids': ['gross'],
                   'fixture': {'total': 120, 'net': 100}, 'expected': 120}]

        def checker(before, after, obligation):
            valid = ('gross amount before discounts' in after and 'term total means' in before)
            return {'status': 'pass' if valid else 'unknown', 'reason': 'Exact existing definition retained'}

        result = T.audit_candidate(source, candidate, requirements=requirements, obligations=checks,
                                   fidelity_checker=checker, checker_id='gross-fixture-v1')
        adopted = T.adopt(result, T.adoption_token(result, 'owner'))
        self.assertEqual(adopted['program'], candidate)
        self.assertTrue(adopted['accepted_changed'])
        self.assertEqual(adopted['adoption']['basis'], 'explicit_host_decision')
        self.assertEqual(result['program'], source)  # the earlier proposal is immutable

    def test_absent_checker_boolean_self_certification_and_errors_stay_unknown(self):
        for checker, identity in ((None, ''), (lambda *args: True, 'bad-return'),
                                  (lambda *args: {'status': 'proven', 'reason': 'I say so'}, 'bad-status')):
            result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=REQUIREMENTS,
                                       obligations=obligations(), fidelity_checker=checker, checker_id=identity)
            self.assertEqual(result['fidelity']['status'], 'unknown')
            self.assertEqual(result['program'], ORIGINAL)

        def broken(*args):
            raise RuntimeError('Synthetic checker failure')

        result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=REQUIREMENTS,
                                   obligations=obligations(), fidelity_checker=broken, checker_id='broken-v1')
        self.assertEqual(result['fidelity']['status'], 'unknown')

    def test_every_requirement_is_visible_even_if_unmapped(self):
        reqs = REQUIREMENTS + [{'id': 'currency', 'text': 'Keep dollars, not another currency.'}]
        result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=reqs, obligations=obligations(),
                                   fidelity_checker=pass_checker, checker_id='finite-v1')
        rows = {r['id']: r for r in result['fidelity']['requirements']}
        self.assertEqual(set(rows), {'exact-total', 'currency'})
        self.assertEqual(rows['currency']['mapping'], 'unmapped')
        self.assertEqual(rows['currency']['status'], 'unmapped')
        self.assertEqual(result['fidelity']['status'], 'unknown')

    def test_meaning_changes_disabled_even_when_finite_checks_pass(self):
        result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=REQUIREMENTS,
                                   obligations=obligations(), fidelity_checker=pass_checker,
                                   checker_id='finite-v1', allow_meaning_changes=False)
        adopted = T.adopt(result, T.adoption_token(result, 'owner'))
        self.assertEqual(adopted['program'], ORIGINAL)
        self.assertEqual(adopted['adoption']['reason'], 'meaning_changes_disabled')

    def test_stale_source_candidate_or_audit_decision_cannot_adopt(self):
        result = T.audit_candidate(ORIGINAL, CANDIDATE)
        for key in ('original_sha256', 'candidate_sha256', 'audit_sha256'):
            decision = T.adoption_token(result, 'owner')
            decision[key] = '0' * 64
            adopted = T.adopt(result, decision)
            self.assertEqual(adopted['program'], ORIGINAL)
            self.assertEqual(adopted['adoption']['reason'], 'stale_or_mismatched_decision')

    def test_candidate_or_requirement_mutation_invalidates_receipt(self):
        result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=REQUIREMENTS)
        decision = T.adoption_token(result, 'owner')
        for what in ('candidate', 'requirement'):
            changed = copy.deepcopy(result)
            if what == 'candidate':
                changed['candidate_program'] = ORIGINAL
            else:
                changed['fidelity']['requirements'].clear()
            with self.assertRaises(T.FidelityError):
                T.adopt(changed, decision)

    def test_predeclared_ast_policy_only_adopts_exact_syntax_equivalence(self):
        candidate = '\n' + ORIGINAL
        policy = {'id': 'formatting-only-v1', 'kind': 'ast_equivalent',
                  'original_sha256': T.source_hash(ORIGINAL)}
        result = T.audit_candidate(ORIGINAL, candidate, equivalent_policy=policy, allow_meaning_changes=False)
        self.assertEqual(result['program'], candidate)
        self.assertEqual(result['adoption']['basis'], 'predeclared_ast_equivalence')
        semantic = T.audit_candidate(ORIGINAL, CANDIDATE, equivalent_policy=policy)
        self.assertEqual(semantic['program'], ORIGINAL)
        self.assertEqual(semantic['adoption']['reason'], 'equivalence_not_established')

    def test_requirement_mapping_and_checker_mutation_are_isolated(self):
        reqs, fixtures = copy.deepcopy(REQUIREMENTS), obligations()

        def mutator(before, after, fixture):
            fixture['requirement_ids'].clear()
            fixture['expected'] = 'wrong'
            return {'status': 'pass', 'reason': 'Fixture checker attempted to mutate its input'}

        result = T.audit_candidate(ORIGINAL, CANDIDATE, requirements=reqs, obligations=fixtures,
                                   requirement_map={'value': ['exact-total']}, fidelity_checker=mutator,
                                   checker_id='mutation-fixture-v1')
        self.assertEqual(fixtures, obligations())
        self.assertEqual(result['fidelity']['requirements'][0]['mapping'], 'mapped')
        reqs.clear()
        self.assertEqual(result['fidelity']['requirements'][0]['id'], 'exact-total')

    def test_unknown_requirement_and_nonheldout_checks_fail_before_exploration(self):
        invalid = obligations()
        invalid[0]['requirement_ids'] = ['missing']
        with patch.object(T, 'probe', side_effect=AssertionError('No model work expected')):
            with self.assertRaises(T.FidelityError):
                T.tighten(ORIGINAL, None, [], None, requirements=REQUIREMENTS, obligations=invalid)
        invalid = obligations()
        invalid[0]['split'] = 'train'
        with self.assertRaises(T.FidelityError):
            T.audit_candidate(ORIGINAL, CANDIDATE, requirements=REQUIREMENTS, obligations=invalid)


class Readers:
    def __init__(self, instruction, assumptions=()):
        self.instruction, self.assumptions = instruction, list(assumptions)
        self.prompts = []

    def call(self, request):
        prompt = request['prompt']
        self.prompts.append(prompt)
        if 'Rewrite the statement' in prompt:
            return {'ok': True, 'json': {'answer': {'instruction': self.instruction,
                                                   'assumptions': self.assumptions or ['caller should review']}}}
        refined = self.instruction in prompt
        value = 42 if refined or request['app']['spec'] == 'claude:haiku' else 26
        readings = {'readings': []} if 'readings' in request['schema']['properties'] else {}
        return {'ok': True, 'json': {'answer': value, **readings}}


class Exploration(unittest.TestCase):
    SOURCE = 'ask value: Number "How long is a marathon?" with effort=low\n'
    PANEL = ['claude:haiku', 'codex']

    def test_unit_convention_change_is_only_a_candidate_despite_convergence(self):
        readers = Readers('How long is a marathon, in kilometres?', ['Use kilometres'])
        result = T.tighten(self.SOURCE, None, self.PANEL, readers)
        self.assertEqual([r['asks'][0]['diagnosis'] for r in result['history']], ['ambiguous', 'converged'])
        self.assertEqual(result['program'], self.SOURCE)
        self.assertTrue(result['changed'])
        self.assertFalse(result['accepted_changed'])
        self.assertIn('kilometres', result['candidate_program'])
        change = result['rewrites'][0]
        self.assertIn('unit_or_convention', change['risks'])
        self.assertEqual(change['original_sha256'], T.source_hash(self.SOURCE))
        self.assertEqual(change['candidate_sha256'], result['candidate_sha256'])
        self.assertEqual(change['assumption_records'][0]['status'], 'proposed')

    def test_heldout_fixtures_are_checked_once_after_all_model_work_and_not_exposed(self):
        readers = Readers('How long is a marathon, in kilometres?')
        reqs = [{'id': 'length', 'text': 'Measure the specified marathon'}]
        fixtures = [{'id': 'SECRET_HELDOUT_19', 'kind': 'positive', 'split': 'heldout',
                     'requirement_ids': ['length'], 'fixture': {'private_fixture': 'SECRET_HELDOUT_19'},
                     'expected': 'SECRET_HELDOUT_ANSWER'}]
        calls_seen = []

        def checker(before, after, obligation):
            calls_seen.append(len(readers.prompts))
            return {'status': 'pass', 'reason': 'Exact heldout fixture'}

        result = T.tighten(self.SOURCE, None, self.PANEL, readers, requirements=reqs,
                           obligations=fixtures, requirement_map={'value': ['length']},
                           fidelity_checker=checker, checker_id='heldout-fixture-v1')
        self.assertEqual(calls_seen, [len(readers.prompts)])
        self.assertNotIn('SECRET_HELDOUT', '\n'.join(readers.prompts))
        self.assertEqual(result['rewrites'][0]['requirement_ids'], ['length'])
        self.assertEqual(result['fidelity']['status'], 'pass')
        self.assertEqual(result['program'], self.SOURCE)

    def test_answer_leak_never_enters_candidate_or_proves_fidelity(self):
        readers = Readers('How long is a marathon? Its distance is 42.')
        result = T.tighten(self.SOURCE, None, self.PANEL, readers)
        self.assertFalse(result['changed'])
        self.assertEqual(result['candidate_program'], self.SOURCE)
        self.assertEqual(result['rewrites'][0]['status'], 'rejected_answer_leak')
        self.assertIsNotNone(result['rewrites'][0]['candidate_sha256'])

    def test_option_removal_is_reported_even_when_leak_heuristic_misses(self):
        source = 'ask value: one of {red, blue, green} "Select red, blue or green as appropriate." with effort=low\n'
        diagnostics = {'line': 1, 'name': 'value', 'diagnosis': 'ambiguous', 'agreement_all': .5,
                       'agreement_valid': .5, 'coverage': 1, 'distinct': 2, 'suggestions': [],
                       'readings': [], 'flagged': []}
        probe = {'agreement_all': .5, 'coverage': 1, 'asks': [diagnostics]}
        fix = {'ok': True, 'instruction': 'Select red or blue as appropriate.',
               'assumptions': ['Ignore green'], 'leaks_answer': False}
        with patch.object(T, 'probe', return_value=probe), patch.object(T, 'clarify', return_value=fix):
            result = T.tighten(source, None, [], None, rounds=1)
        self.assertIn('removed_option_mention', result['rewrites'][0]['risks'])
        self.assertEqual(result['program'], source)
        self.assertEqual(result['fidelity']['status'], 'unknown')

    def test_rounding_hint_does_not_automatically_make_a_rewrite_safe(self):
        readers = Readers('How long is a marathon, rounded to zero decimal places?')
        result = T.tighten(self.SOURCE, None, self.PANEL, readers)
        self.assertIn('rounding_or_precision', result['rewrites'][0]['risks'])
        self.assertEqual(result['program'], self.SOURCE)

    def test_paper_original_is_retained_and_decision_pins_paper_bytes(self):
        paper = '# Length\n\n```symblic\n' + self.SOURCE + '```\n'
        readers = Readers('How long is a marathon, in kilometres?')
        result = T.tighten_paper(paper, self.PANEL, readers)
        self.assertEqual(result['paper'], paper)
        self.assertIn('kilometres', result['candidate_paper'])
        decision = T.paper_adoption_token(result, 'owner')
        adopted = T.adopt_paper(result, decision)
        self.assertEqual(adopted['paper'], result['candidate_paper'])
        decision['candidate_paper_sha256'] = '0' * 64
        rejected = T.adopt_paper(result, decision)
        self.assertEqual(rejected['paper'], paper)
        changed = copy.deepcopy(result)
        changed['candidate_paper'] += '\nUnreviewed prose.\n'
        with self.assertRaises(T.FidelityError):
            T.adopt_paper(changed, T.paper_adoption_token(result, 'owner'))

    def test_job_retains_fidelity_metadata_without_importing_json_named_checker(self):
        metadata = {'id': 'synthetic-job', 'panel': self.PANEL, 'clarifier': 'claude:sonnet',
                    'requirements': [{'id': 'length', 'text': 'Measure the specified marathon'}],
                    'requirement_map': {'value': ['length']},
                    'fidelity_obligations': [{'id': 'check-length', 'kind': 'positive', 'split': 'heldout',
                        'requirement_ids': ['length'], 'fixture': {}, 'expected': 42}],
                    'checker_module': 'this_untrusted_module_must_never_be_imported'}
        with tempfile.TemporaryDirectory(prefix='symblic-tighten-fidelity-test-') as folder:
            path = Path(folder)
            (path / 'program.sym').write_text(self.SOURCE)
            (path / 'meta.json').write_text(json.dumps(metadata))
            result = T.run_job(folder, Readers('How long is a marathon, in kilometres?'))
            self.assertEqual(result['status'], 'done')
            self.assertEqual(result['program'], self.SOURCE)
            self.assertEqual(result['fidelity']['status'], 'unknown')
            self.assertEqual(result['fidelity']['requirements'][0]['mapping'], 'mapped')
            persisted = json.loads((path / 'result.json').read_text())
            self.assertEqual(persisted['candidate_sha256'], result['candidate_sha256'])
            self.assertEqual(persisted['adoption']['status'], 'not_requested')


if __name__ == '__main__':
    unittest.main()
