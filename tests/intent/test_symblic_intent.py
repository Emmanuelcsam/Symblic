"""Pure intent invariants; no providers, stores, network or external effects."""
import copy
import hashlib
import math
import unittest

from symblic.intent import records as I


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def event(state, kind, payload, actor='owner', event_id=None):
    return I.apply_event(state, {'id': event_id or 'event-' + str(state['revision'] + 1),
                                'kind': kind, 'actor': actor, 'payload': payload}, state['revision'])


def reference(state, text, source_id='request'):
    source = next(s for s in state['sources'] if s['id'] == source_id)
    start = source['text'].index(text)
    return {'source_id': source_id, 'start': start, 'end': start + len(text),
            'quote': text, 'source_sha256': source['sha256']}


def proposal(state, **fields):
    return event(state, 'proposal', {'goal': 'Produce the requested artifact.', **fields}, actor='model')


def artifact(state):
    source = 'let value = 1 + 1.\nreturn value.\n'
    return {'content_revision': state['content_revision'], 'intent_content_sha256': I.content_digest(state),
            'source': source, 'source_sha256': sha(source), 'inputs': {}, 'input_sha256': I.digest({}),
            'kernel_id': 'kernel-fixture', 'module_hashes': {}, 'catalogue_sha256': sha('catalogue'),
            'policy_sha256': I.digest(state['policy']), 'effective_policy': copy.deepcopy(state['policy']),
            'source_hashes': {s['id']: s['sha256'] for s in state['sources']},
            'checks': [{'kind': 'static', 'ok': True, 'scope': 'encoded syntax'},
                       {'kind': 'effect_static', 'ok': True, 'scope': 'declared capabilities'}]}


def pins(compiled):
    return {key: copy.deepcopy(compiled[key]) for key in
            ('kernel_id', 'module_hashes', 'catalogue_sha256', 'policy_sha256', 'source_hashes')}


def question(ident='q1', blocking=True):
    return {'id': ident, 'question': 'Which output artifact?', 'why': 'Changes tools and units.',
            'field': 'output.kind', 'blocking': blocking,
            'options': [{'id': 'image', 'label': 'Image', 'consequence': 'A rendered image.'},
                        {'id': 'model', 'label': '3D model', 'consequence': 'A dimensioned mesh.'}]}


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.initial = I.new_intent('intent-fixture', 'Make a blue flower. Keep the background white.',
                                    policy={'allow_cloud': True, 'max_calls': 6}, now='fixture')

    def test_initial_is_private_json_and_no_claim_of_readiness(self):
        self.assertEqual('draft', self.initial['phase'])
        self.assertEqual('personal', self.initial['sources'][0]['sensitivity'])
        self.assertTrue(I.validate(self.initial)['ok'])
        self.assertIn(self.initial['request']['text'], I.readback(self.initial)['prompt'])

    def test_confidential_policy_cannot_accidentally_allow_cloud(self):
        state = I.new_intent('private', 'Sensitive request', policy={'confidential': True, 'allow_cloud': True})
        self.assertFalse(state['policy']['allow_cloud'])
        self.assertEqual('confidential', state['sources'][0]['sensitivity'])
        with self.assertRaises(I.IntentError):
            event(state, 'proposal', {'goal': 'Task', 'policy': {'allow_cloud': True}}, actor='model')

    def test_original_and_sources_are_detached_from_caller(self):
        sources = [{'id': 's1', 'text': 'Reference', 'kind': 'document'}]
        policy = {'allow_cloud': False}
        state = I.new_intent('one', 'Task', sources, policy)
        sources[0]['text'] = 'Changed'
        policy['allow_cloud'] = True
        self.assertEqual('Reference', state['sources'][1]['text'])
        self.assertFalse(state['policy']['allow_cloud'])

    def test_exact_codepoint_quote_supports_astral_and_combining_text(self):
        state = I.new_intent('unicode', '🌻 blue e\u0301 petal')
        ref = reference(state, 'blue e\u0301')
        state = proposal(state, requirements=[{'id': 'r1', 'text': 'Blue petal',
                         'origin': 'model_extracted', 'source_refs': [ref]}])
        self.assertEqual(2, state['requirements'][0]['source_refs'][0]['start'])
        self.assertEqual('model_extracted', state['requirements'][0]['origin'])
        self.assertTrue(I.validate(state)['ok'])

    def test_wrong_quote_source_hash_and_utf16_offset_refuse(self):
        state = I.new_intent('unicode', '🌻 blue')
        for mutation in ({'start': 3}, {'quote': 'BLUE'}, {'source_sha256': sha('different')}):
            ref = reference(state, 'blue')
            ref.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(I.IntentError):
                proposal(state, requirements=[{'id': 'r', 'text': 'Blue', 'source_refs': [ref]}])

    def test_no_source_hash_normalization_or_unbound_reference(self):
        with self.assertRaises(I.IntentError):
            I.new_intent('one', 'Task', [{'id': 's', 'text': 'e\u0301', 'sha256': sha('é')}])
        ref = reference(self.initial, 'blue')
        ref['source_id'] = 'missing'
        with self.assertRaises(I.IntentError):
            proposal(self.initial, requirements=[{'id': 'r', 'text': 'Blue', 'source_refs': [ref]}])

    def test_nonfinite_nonjson_bool_revisions_and_oversize_refuse(self):
        for value in (math.nan, math.inf, object(), {1: 'non-string'}):
            with self.subTest(value=type(value).__name__), self.assertRaises(I.IntentError):
                I.digest(value)
        with self.assertRaises(I.IntentError):
            I.new_intent('one', 'x' * 40001)
        with self.assertRaises(I.IntentError):
            I.apply_event(self.initial, {'id': 'p', 'kind': 'proposal', 'actor': 'model',
                                        'payload': {'goal': 'Task'}}, False)
        self.assertNotEqual(I.digest(True), I.digest(1))

    def test_model_cannot_create_owner_facts_or_adopt_assumptions(self):
        cases = ({'requirements': [{'id': 'r', 'text': 'A fact', 'origin': 'owner_explicit'}]},
                 {'assumptions': [{'id': 'a', 'text': 'An assumption', 'status': 'adopted'}]})
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(I.IntentError):
                proposal(self.initial, **fields)

    def test_owner_adopts_assumption_without_converting_it_to_fact(self):
        state = proposal(self.initial, assumptions=[{'id': 'a1', 'text': 'Front view', 'consequence': 'Camera angle'}])
        self.assertIn('INTENT_ASSUMPTIONS', str(I.validate(state)))
        state = event(state, 'assumption', {'assumption_id': 'a1', 'status': 'adopted'})
        self.assertEqual('model_proposed', state['assumptions'][0]['origin'])
        self.assertEqual('adopted', state['assumptions'][0]['status'])
        self.assertIn('Assumptions are not observed facts', I.readback(state)['prompt'])

    def test_model_cannot_answer_its_own_question(self):
        q = question()
        q.update(status='answered', answer={'text': 'Image'})
        with self.assertRaises(I.IntentError):
            proposal(self.initial, questions=[q])
        state = proposal(self.initial, questions=[question()])
        with self.assertRaises(I.IntentError):
            event(state, 'answer', {'question_id': 'q1', 'option_id': 'image'}, actor='model')

    def test_at_most_three_pending_questions_no_hidden_fourth(self):
        state = proposal(self.initial, questions=[question('q' + str(i)) for i in range(3)])
        self.assertEqual(3, I.clarification_view(state)['remaining'])
        with self.assertRaises(I.IntentError):
            proposal(state, questions=[question('fourth')])

    def test_questions_need_consequence_and_distinct_options(self):
        for change in ({'why': ''}, {'options': [question()['options'][0]]},
                       {'options': [question()['options'][0], question()['options'][0]]}):
            q = question()
            q.update(change)
            with self.subTest(change=change), self.assertRaises(I.IntentError):
                proposal(self.initial, questions=[q])

    def test_answer_applies_only_to_named_question_and_retains_its_source(self):
        state = proposal(self.initial, questions=[question('q1'), question('q2')])
        state = event(state, 'answer', {'question_id': 'q1', 'option_id': 'image'})
        self.assertEqual('clarifying', state['phase'])
        self.assertEqual(['q2'], I.validate(state)['readiness']['blocking_question_ids'])
        self.assertEqual('Image', state['questions'][0]['answer']['text'])
        self.assertEqual('owner_answer', state['sources'][-1]['kind'])
        self.assertIn('OWNER ANSWER TO q1 (Which output artifact?): Image', I.readback(state)['prompt'])

    def test_missing_and_duplicate_answers_refuse(self):
        state = proposal(self.initial, questions=[question()])
        with self.assertRaises(I.IntentError):
            event(state, 'answer', {'question_id': 'q1'})
        state = event(state, 'answer', {'question_id': 'q1', 'text': 'Image'})
        with self.assertRaises(I.IntentError):
            event(state, 'answer', {'question_id': 'q1', 'text': 'Different'})

    def test_rewrite_preserves_original_answers_requirements_and_assumptions(self):
        state = proposal(self.initial, requirements=[{'id': 'r', 'text': 'White background'}],
                         assumptions=[{'id': 'a', 'text': 'Front view'}], questions=[question()])
        state = event(state, 'answer', {'question_id': 'q1', 'option_id': 'image'})
        original = copy.deepcopy(state)
        state = event(state, 'rewrite', {'text': 'Use six petals.'})
        self.assertEqual('draft', state['phase'])
        for field in ('request', 'requirements', 'assumptions', 'questions'):
            self.assertEqual(original[field], state[field])
        prompt = I.readback(state)['prompt']
        for text in (self.initial['request']['text'], 'Use six petals.', 'White background', 'Front view', 'Image'):
            self.assertIn(text, prompt)

    def test_proposals_cannot_silently_drop_or_change_retained_requirements(self):
        state = proposal(self.initial, requirements=[{'id': 'r', 'text': 'White background'}])
        next_state = proposal(state, requirements=[])
        self.assertEqual(state['requirements'], next_state['requirements'])
        with self.assertRaises(I.IntentError):
            proposal(state, requirements=[{'id': 'r', 'text': 'Black background'}])

    def test_retained_owner_items_can_be_echoed_but_not_fabricated(self):
        state = event(self.initial, 'proposal', {'goal': 'Flower', 'requirements': [{'id': 'r', 'text': 'White'}]})
        self.assertEqual('owner_explicit', state['requirements'][0]['origin'])
        state = proposal(state, requirements=state['requirements'])
        self.assertEqual('owner_explicit', state['requirements'][0]['origin'])

    def test_owner_can_retire_mistaken_extraction_and_model_cannot(self):
        state = proposal(self.initial, requirements=[{'id': 'bad', 'text': 'Black background'}])
        payload = {'requirement_id': 'bad', 'status': 'retired', 'reason': 'I said white, not black.'}
        with self.assertRaises(I.IntentError):
            event(state, 'requirement', payload, actor='model')
        state = event(state, 'requirement', payload)
        row = state['requirements'][0]
        self.assertEqual('retired', row['status'])
        self.assertEqual('Black background', row['text'])
        self.assertEqual(payload['reason'], row['retired_reason'])
        self.assertEqual('owner_requirement', state['sources'][-1]['kind'])
        self.assertIn('Keep the background white.', I.readback(state)['prompt'])

    def test_event_retry_is_noop_before_revision_check_but_changed_payload_refuses(self):
        raw = {'id': 'retry', 'kind': 'proposal', 'actor': 'model', 'payload': {'goal': 'Flower'}}
        state = I.apply_event(self.initial, raw, 0)
        state = event(state, 'rewrite', {'text': 'Six petals'})
        self.assertEqual(state, I.apply_event(state, raw, 0))
        raw['payload']['goal'] = 'Different'
        with self.assertRaises(I.IntentError):
            I.apply_event(state, raw, 0)

    def test_concurrent_stale_tab_refuses_without_mutating_state(self):
        state = proposal(self.initial)
        before = copy.deepcopy(state)
        with self.assertRaises(I.IntentError):
            I.apply_event(state, {'id': 'stale', 'kind': 'rewrite', 'actor': 'owner',
                                 'payload': {'text': 'Change'}}, 0)
        self.assertEqual(before, state)

    def test_artifact_checks_pin_content_without_revision_oscillation(self):
        state = proposal(self.initial)
        compiled = artifact(state)
        before_digest = I.content_digest(state)
        state = event(state, 'checked', {'artifact': compiled}, actor='system')
        self.assertEqual('checked', state['phase'])
        self.assertEqual(1, state['content_revision'])
        self.assertEqual(2, state['revision'])
        self.assertEqual(before_digest, I.content_digest(state))
        self.assertTrue(I.validate(state, pins(compiled))['ok'])

    def test_unanswered_blocking_question_cannot_compile_or_handoff(self):
        state = proposal(self.initial, questions=[question()])
        compiled = artifact(state)
        with self.assertRaises(I.IntentError):
            event(state, 'checked', {'artifact': compiled}, actor='system')
        with self.assertRaises(I.IntentError):
            I.prepare_handoff(state, compiled, pins(compiled))

    def test_every_handoff_pin_is_checked(self):
        state = proposal(self.initial)
        compiled = artifact(state)
        for field in ('kernel_id', 'module_hashes', 'catalogue_sha256', 'policy_sha256', 'source_hashes'):
            current = pins(compiled)
            current[field] = {'different': sha('x')} if type(current[field]) is dict else sha('different')
            with self.subTest(field=field), self.assertRaises(I.IntentError):
                I.prepare_handoff(state, compiled, current)

    def test_effective_policy_may_only_lower_creation_limits(self):
        state = I.new_intent('bounded', 'Task', policy={'allow_cloud': True, 'confidential': False,
                                                      'max_calls': 6, 'repairs': 2})
        state = proposal(state)
        compiled = artifact(state)
        compiled['effective_policy'].update(allow_cloud=False, max_calls=2, repairs=0)
        compiled['policy_sha256'] = I.digest(compiled['effective_policy'])
        envelope = I.prepare_handoff(state, compiled, pins(compiled))
        self.assertFalse(envelope['effective_policy']['allow_cloud'])
        self.assertEqual(6, state['policy']['max_calls'])
        for key, value in (('max_calls', 7), ('repairs', 3), ('confidential', True)):
            changed = artifact(state)
            changed['effective_policy'][key] = value
            changed['policy_sha256'] = I.digest(changed['effective_policy'])
            with self.subTest(key=key), self.assertRaises(I.IntentError):
                I.prepare_handoff(state, changed, pins(changed))

    def test_effective_policy_cannot_enable_cloud_or_use_numeric_flags(self):
        state = proposal(I.new_intent('bounded', 'Task', policy={'allow_cloud': False, 'max_calls': 6, 'repairs': 2}))
        for key, value in (('allow_cloud', True), ('allow_cloud', 0), ('max_calls', True)):
            compiled = artifact(state)
            compiled['effective_policy'][key] = value
            compiled['policy_sha256'] = I.digest(compiled['effective_policy'])
            with self.subTest(key=key), self.assertRaises(I.IntentError):
                I.prepare_handoff(state, compiled, pins(compiled))

    def test_missing_pins_failed_checks_and_empty_test_cohort_refuse(self):
        state = proposal(self.initial)
        for update in ({'checks': []}, {'module_hashes': None}, {'checks': [{'kind': 'finite_example', 'ok': True, 'scope': 'sample'}]},
                       {'checks': [{'kind': 'static', 'ok': False, 'scope': 'syntax'},
                                   {'kind': 'effect_static', 'ok': True, 'scope': 'tools'}]}):
            compiled = artifact(state)
            compiled.update(update)
            with self.subTest(update=update), self.assertRaises(I.IntentError):
                I.prepare_handoff(state, compiled, pins(compiled))

    def test_source_input_and_content_tampering_refuse(self):
        state = proposal(self.initial)
        for field, changed in (('source', 'return 9.'), ('inputs', {'x': 9}), ('content_revision', True),
                               ('intent_content_sha256', sha('wrong'))):
            compiled = artifact(state)
            compiled[field] = changed
            with self.subTest(field=field), self.assertRaises(I.IntentError):
                I.prepare_handoff(state, compiled, pins(compiled))

    def test_owner_edit_invalidates_compiled_artifact(self):
        state = proposal(self.initial)
        compiled = artifact(state)
        state = event(state, 'checked', {'artifact': compiled}, actor='system')
        state = event(state, 'rewrite', {'text': 'Six petals'})
        self.assertIsNone(state['checks'])
        state = proposal(state)
        with self.assertRaises(I.IntentError):
            I.prepare_handoff(state, compiled, pins(compiled))

    def test_handoff_is_a_detached_handle_not_task_completion(self):
        state = proposal(self.initial)
        compiled = artifact(state)
        envelope = I.prepare_handoff(state, compiled, pins(compiled))
        state = event(state, 'checked', {'artifact': compiled}, actor='system')
        state = event(state, 'handed_off', {'envelope_sha256': envelope['key'],
                      'native': {'kind': 'host_run', 'id': 'abc123'}}, actor='system')
        self.assertEqual('handed_off', state['phase'])
        self.assertEqual('not_established', envelope['assurance']['semantic_truth'])
        self.assertNotIn('success', state['handoff'])
        envelope['inputs']['changed'] = True
        self.assertEqual({}, state['checks']['inputs'])

    def test_rechecking_cannot_erase_existing_handoff_or_reassign_native_run(self):
        state = proposal(self.initial)
        compiled = artifact(state)
        envelope = I.prepare_handoff(state, compiled, pins(compiled))
        state = event(state, 'checked', {'artifact': compiled}, actor='system')
        state = event(state, 'handed_off', {'envelope_sha256': envelope['key'],
                      'native': {'kind': 'host_run', 'id': 'abc123'}}, actor='system')
        state = event(state, 'checked', {'artifact': compiled}, actor='system')
        self.assertEqual('abc123', state['handoff']['native']['id'])
        with self.assertRaises(I.IntentError):
            event(state, 'handed_off', {'envelope_sha256': envelope['key'],
                  'native': {'kind': 'host_run', 'id': 'different'}}, actor='system')

    def test_unknown_schema_tampered_history_and_derived_view_are_invalid(self):
        for field, value in (('schema', 2), ('schema', True), ('revision', 3), ('phase', 'checked'),
                              ('revised_prompt', 'Dropped original')):
            state = copy.deepcopy(self.initial)
            state[field] = value
            self.assertFalse(I.validate(state)['ok'], field)
        self.assertFalse(I.validate({})['ok'])

    def test_record_preservation_is_not_truth_even_for_unanimous_false_reading(self):
        state = I.new_intent('invoice', 'I ordered 3 laptops at $800 each.')
        state = proposal(state, requirements=[{'id': 'quantity', 'text': 'Use one laptop at one dollar.',
                          'origin': 'model_extracted', 'source_refs': [reference(state, '3 laptops at $800 each')]}])
        next_state = proposal(state)
        assessed = I.assess_continuation(state, next_state)
        self.assertTrue(assessed['compatible'])
        self.assertEqual('not_established', assessed['semantic_correctness'])
        self.assertEqual('not_established', assessed['unique_intended_reading'])
        self.assertIn('entropy is not a proof', assessed['reason'])
        self.assertIn('3 laptops at $800 each', I.readback(next_state)['prompt'])

    def test_continuation_detects_requirement_loss_in_another_valid_record(self):
        previous = proposal(self.initial, requirements=[{'id': 'r', 'text': 'White background'}])
        other = proposal(self.initial)
        assessed = I.assess_continuation(previous, other)
        self.assertFalse(assessed['compatible'])
        self.assertEqual(['r'], assessed['changed_requirement_ids'])


if __name__ == '__main__':
    unittest.main()
