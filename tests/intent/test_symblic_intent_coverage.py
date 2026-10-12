"""Requirement coverage (symblic.intent.coverage) is source-pinned syntax presence, never invented execution."""
import copy
import json
import unittest
from unittest.mock import patch

from symblic.intent import records as I
from symblic.intent import coverage as COV
from tests.intent.test_symblic_intent import artifact, event, pins, proposal


class CoverageTests(unittest.TestCase):
    def state(self):
        state = I.new_intent('coverage', 'Extract the invoice total; include the exception.',
                            sources=[{'id': 'invoice', 'text': '🌻 Count: 3; Total: USD 120; except refunds.'}])
        return proposal(state, requirements=[
            {'id': 'total', 'text': 'Use the invoice total.', 'predicate': 'total = 120'},
            {'id': 'exception', 'text': 'Preserve refund exceptions.'}],
            assumptions=[{'id': 'currency', 'text': 'Currency is USD.'}],
            examples=[{'id': 'refund', 'kind': 'negative', 'description': 'Reject omitted refund exception.',
                       'input': {'refund': True}, 'expected': {'reject': True}}])

    def test_complete_compiler_record_preserves_sources_predicates_and_negative_examples(self):
        state = self.state()
        old_prompt = state['revised_prompt']
        text = I.compiler_prompt(state)
        record = json.loads(text.split('\n', 2)[2])
        for key in ('request', 'sources', 'turns', 'goal', 'requirements', 'assumptions', 'questions', 'examples'):
            self.assertEqual(state[key], record[key], key)
        self.assertIn('not held-out tests', text)
        self.assertEqual(old_prompt, state['revised_prompt'])

    def test_wrong_field_is_unmapped_even_if_same_number_and_source_quote(self):
        result = COV.requirement_coverage(self.state(), 'let count = 120.\nassert count = 120.', {})
        self.assertEqual(['total', 'exception'], result['unmapped_hard_ids'])
        self.assertEqual('unassessed', result['intent_fidelity'])

    def test_unreachable_matching_predicate_is_present_never_executed(self):
        state = event(self.state(), 'predicate', {'requirement_id': 'total', 'predicate': 'total = 120'})
        with patch.object(COV.S.Kernel, 'eval', side_effect=AssertionError('coverage must not execute')):
            result = COV.requirement_coverage(state, 'let total = 3.\nif false then\n assert total = 120.\nend.', {})
        row = result['requirements'][0]
        self.assertEqual('predicate_present', row['status'])
        self.assertEqual(3, row['locations'][0]['line'])
        self.assertEqual('not_executed', row['execution'])
        self.assertEqual(['exception'], result['unmapped_hard_ids'])

    def test_whitespace_does_not_change_ast_match_or_claim_logical_equivalence(self):
        state = event(self.state(), 'predicate', {'requirement_id': 'total', 'predicate': 'total = 120'})
        result = COV.requirement_coverage(state, 'let total = 120.\nassert total=120.', {})
        self.assertEqual(['total'], result['predicate_present_ids'])
        changed = COV.requirement_coverage(state, 'let total = 120.\nassert 120=total.', {})
        self.assertEqual([], changed['predicate_present_ids'])

    def test_model_predicate_cannot_discharge_owner_requirement_coverage(self):
        state = self.state()
        state['requirements'][0]['predicate'] = 'true'
        result = COV.requirement_coverage(state, 'assert true.', {})
        self.assertEqual('model_proposed', result['requirements'][0]['predicate_origin'])
        self.assertEqual('proposed_predicate_present', result['requirements'][0]['status'])
        self.assertEqual(['total'], result['proposed_predicate_present_ids'])
        self.assertEqual(['total', 'exception'], result['unmapped_hard_ids'])
        self.assertEqual([], result['predicate_present_ids'])

    def test_examples_are_exposed_proposals_and_assumptions_are_not_facts(self):
        result = COV.requirement_coverage(self.state(), 'show 0.', {})
        self.assertEqual('negative', result['examples'][0]['kind'])
        self.assertIs(False, result['examples'][0]['held_out'])
        self.assertEqual('not_executed', result['examples'][0]['execution'])
        self.assertEqual('not_established', result['assumptions'][0]['truth'])

    def checked(self):
        state = self.state()
        compiled = artifact(state)
        compiled['coverage'] = COV.requirement_coverage(state, compiled['source'], compiled['inputs'])
        return state, compiled

    def test_handoff_preserves_missing_hard_requirements_and_no_execution_claim(self):
        state, compiled = self.checked()
        envelope = I.prepare_handoff(state, compiled, pins(compiled))
        self.assertEqual(['total', 'exception'], envelope['coverage']['unmapped_hard_ids'])
        self.assertEqual('not_executed', envelope['assurance']['execution'])
        self.assertEqual('unassessed', envelope['assurance']['intent_fidelity'])

    def test_forged_pass_missing_row_wrong_input_and_boolean_version_refuse(self):
        state, compiled = self.checked()
        for mutate in (lambda c: c['requirements'][0].update(status='executed_pass'),
                       lambda c: c['requirements'].pop(),
                       lambda c: c.update(input_sha256=I.digest({'x': 1})),
                       lambda c: c.update(version=True)):
            bad = copy.deepcopy(compiled)
            mutate(bad['coverage'])
            with self.subTest(coverage=bad['coverage']), self.assertRaises(I.IntentError):
                I.prepare_handoff(state, bad, pins(bad))

    def test_changed_source_and_requirement_make_old_coverage_stale(self):
        state, compiled = self.checked()
        bad = copy.deepcopy(compiled)
        bad['source'] += '\nshow 9.'
        bad['source_sha256'] = I._raw_hash(bad['source'])
        with self.assertRaises(I.IntentError):
            I.prepare_handoff(state, bad, pins(bad))
        changed = event(state, 'assumption', {'assumption_id': 'currency', 'status': 'rejected'})
        with self.assertRaises(I.IntentError):
            I.prepare_handoff(changed, compiled, pins(compiled))

    def test_duplicate_locations_and_unknown_requirement_refuse(self):
        state = self.state()
        location = {'kind': 'assert', 'line': 1, 'col': 1, 'predicate_sha256': I._raw_hash('total = 120')}
        for mappings in ({'unknown': []}, {'total': [location, location]}):
            with self.assertRaises(I.IntentError):
                I.coverage_manifest(state, 'assert total = 120.', {}, mappings)

    def test_owner_predicate_keeps_history_and_invalidates_checked_artifact(self):
        state, compiled = self.checked()
        state = event(state, 'checked', {'artifact': compiled}, actor='system')
        changed = event(state, 'predicate', {'requirement_id': 'total', 'predicate': 'total = 240'})
        self.assertIsNone(changed['checks'])
        self.assertEqual('total = 120', state['requirements'][0]['predicate'])
        self.assertEqual('total = 240', changed['sources'][-1]['text'])
        self.assertEqual('owner_predicate', changed['sources'][-1]['kind'])
        with self.assertRaises(I.IntentError):
            event(state, 'predicate', {'requirement_id': 'total', 'predicate': 'true'}, actor='model')

    def test_no_recorded_requirements_does_not_establish_vacuous_intent_fidelity(self):
        state = proposal(I.new_intent('empty', 'Do the whole task.'))
        result = COV.requirement_coverage(state, 'show 0.', {})
        self.assertEqual([], result['requirements'])
        self.assertEqual('unassessed', result['intent_fidelity'])


if __name__ == '__main__':
    unittest.main()
