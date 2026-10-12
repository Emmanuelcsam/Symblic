"""Actual durable jobs with temporary SQLite and fake applicators only."""
import copy
import json
import signal
import tempfile
import unittest

from symblic.forge import core as C
from symblic.forge import models as M
from symblic.forge.store import Store, StoreError


def proposal(text='Specify an exact update interval.'):
    return {'questions': [], 'statements': [{'text': text}], 'assumptions': [], 'entities': []}


class FakeApplicators:
    def __init__(self, replies, callback=None):
        self.replies = list(replies)
        self.calls = []
        self.callback = callback

    def call(self, request):
        self.calls.append(request)
        if self.callback:
            self.callback(len(self.calls))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return copy.deepcopy(reply)


class ForgeModelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-model-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.p = self.store.create('Make a bounded Snake design', 'Fixture', '', 'create_request')
        self.p = self.store.mutate(self.p['id'], 0, 'settings.set', {'roles': {
            'IDEATOR': {'app': 'ollama:fixture@node-a', 'allow_cloud': False, 'fallback': []},
            'CRITIC': {'app': 'ollama:fixture@node-a', 'allow_cloud': False, 'fallback': []}}}, 'setting_request')

    def request(self, **kwargs):
        return M.build_request(self.p, 'IDEATOR', **kwargs)

    def job(self, request):
        return self.store.reserve_job(self.p['id'], self.p['revision'], request, 'reserve_request')[0]

    def run_job(self, request, fake):
        return M.run_job(self.job(request)['id'], store=self.store, applicators=fake, check_host=False)

    def test_typed_schema_guides_exact_entity_shape(self):
        schema = self.request()['schema']
        self.assertFalse(schema['additionalProperties'])
        statement = schema['properties']['statements']['items']
        self.assertNotIn('status', statement['properties'])
        self.assertIn('objective_ids', statement['properties'])
        variants = schema['properties']['entities']['items']['oneOf']
        unit = next(v for v in variants if v['properties']['kind']['const'] == 'units')
        self.assertIn('component_id', unit['properties']['entity']['properties'])
        self.assertEqual(unit['properties']['entity']['properties']['dependencies']['type'], 'array')
        alternatives = schema['properties']['questions']['items']['properties']['suggestions']['items']['oneOf']
        self.assertEqual(alternatives[0]['type'], 'string')
        self.assertIn('tradeoffs', alternatives[1]['properties'])

    def test_mode_and_exact_values_are_in_context_without_private_snapshot(self):
        self.p = self.store.mutate(self.p['id'], self.p['revision'], 'mode.set', {'mode': 'PRECISION'}, 'mode_request')
        request = self.request(instruction='Keep 800 px and exact/path.py')
        self.assertEqual(request['context']['mode'], 'PRECISION')
        self.assertIn('800 px', request['prompt'])
        self.assertNotIn('validation_project', json.loads(request['prompt']))
        self.assertEqual(request['validation_project']['revision'], self.p['revision'])

    def test_critic_does_not_receive_original_idea_rejected_drafts_or_history(self):
        p = self.p
        for action, payload, rid in [('statement.propose', {'text': 'SECRET discarded draft'}, 'propose_request')]:
            p = self.store.mutate(p['id'], p['revision'], action, payload, rid)
        identifier = C.active_branch(p)['statements'][-1]['id']
        p = self.store.mutate(p['id'], p['revision'], 'statement.edit', {'id': identifier, 'text': 'Current exact accepted requirement'}, 'edit_request')
        p = self.store.mutate(p['id'], p['revision'], 'statement.accept', {'id': identifier}, 'accept_request')
        request = M.build_request(p, 'CRITIC')
        self.assertNotIn('SECRET', request['prompt'])
        self.assertNotIn('Make a bounded Snake design', request['prompt'])
        self.assertIn('Current exact accepted requirement', request['prompt'])

    def test_native_json_reply_and_legacy_text_are_supported(self):
        for reply in [{'ok': True, 'json': proposal()}, {'ok': True, 'data': proposal()},
                      {'ok': True, 'text': '```json\n' + json.dumps(proposal()) + '\n```'}]:
            self.assertEqual(M.parse_reply(reply), proposal())

    def test_duplicate_fields_nonfinite_wrong_shape_and_hidden_fields_refuse(self):
        cases = [ {'ok': True, 'text': '{"questions":[],"questions":[],"statements":[],"assumptions":[],"entities":[]}'},
            {'ok': True, 'json': {**proposal(), 'statements': [{'text': 'x', 'fact': float('nan')}]}},
            {'ok': True, 'json': {**proposal(), 'accepted': True}},
            {'ok': True, 'json': {**proposal(), 'statements': [{'text': 'x', 'reasoning': 'hidden'}]}}]
        for reply in cases:
            with self.subTest(reply=reply), self.assertRaises(StoreError):
                M.parse_reply(reply)

    def test_role_requires_explicit_model_and_cloud_permission_for_fallback_too(self):
        blank = C.new_project('Idea')
        with self.assertRaises(StoreError):
            M.build_request(blank, 'IDEATOR')
        p = C.transition(self.p, 'settings.set', {'roles': {'IDEATOR': {'app': 'ollama:fixture@node-a', 'allow_cloud': False, 'fallback': ['claude']}}})
        with self.assertRaises(StoreError):
            M.build_request(p, 'IDEATOR')
        with self.assertRaises(StoreError):
            self.request(apps=[{}])

    def test_success_is_proposal_only_and_durable_dispatch_precedes_fake_call(self):
        request = self.request()
        def during_call(_):
            job = self.store.jobs(self.p['id'])[0]
            self.assertEqual(job['status'], 'running')
            self.assertEqual(job['dispatch']['app'], 'ollama:fixture@node-a')
        fake = FakeApplicators([{'ok': True, 'json': proposal(), 'model_identity': {'status': 'fixture'}}], during_call)
        result = self.run_job(request, fake)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.store.get(self.p['id']), self.p)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]['tools'], 'none')
        self.assertNotIn('validation_project', fake.calls[0])
        self.assertEqual(result['outcomes'][0]['artifact']['model'], 'ollama:fixture@node-a')
        with self.assertRaises(StoreError):
            M.run_job(result['id'], store=self.store, applicators=fake, check_host=False)
        self.assertEqual(len(fake.calls), 1)

    def test_explicit_fallback_records_failed_and_chosen_models(self):
        self.p = self.store.mutate(self.p['id'], self.p['revision'], 'settings.set', {'roles': {
            'IDEATOR': {'app': 'ollama:fixture@node-a', 'allow_cloud': False, 'fallback': ['ollama:backup@node-b']}}}, 'fallback_request')
        request = self.request()
        fake = FakeApplicators([{'ok': False, 'error': 'fixture unavailable'}, {'ok': True, 'json': proposal()}])
        result = self.run_job(request, fake)
        self.assertEqual([r['app']['spec'] for r in fake.calls], ['ollama:fixture@node-a', 'ollama:backup@node-b'])
        self.assertEqual([a['status'] for a in result['attempts']], ['failed', 'completed'])
        outcome = result['outcomes'][0]
        self.assertTrue(outcome['fallback'])
        self.assertEqual(outcome['requested_model'], 'ollama:fixture@node-a')
        self.assertEqual(outcome['artifact']['model'], 'ollama:backup@node-b')
        self.assertTrue(request['policy']['automatic_fallback'])

    def test_no_implicit_fallback_after_failure(self):
        fake = FakeApplicators([{'ok': False, 'error': 'fixture unavailable'}])
        result = self.run_job(self.request(), fake)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(fake.calls), 1)

    def test_failed_job_names_the_underlying_attempt_cause_at_job_level(self):
        fake = FakeApplicators([StoreError('unavailable: ollama: invalid JSON schema in format')])
        result = self.run_job(self.request(), fake)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['attempts'][0]['status'], 'failed')
        self.assertIn('invalid JSON schema', result['attempts'][0]['error'])
        self.assertIn('Cause: unavailable: ollama: invalid JSON schema in format', result['error'])
        self.assertIn('Inspect the retained attempts', result['error'])

    def test_multiple_explicit_models_do_not_vote_a_requirement_into_state(self):
        request = self.request(apps=['ollama:first@node-c', 'ollama:second@node-b'])
        fake = FakeApplicators([{'ok': True, 'json': proposal()}, {'ok': True, 'json': proposal()}])
        result = self.run_job(request, fake)
        self.assertEqual(len(result['outcomes']), 2)
        self.assertEqual(C.analyze(self.store.get(self.p['id']))['counts']['accepted'], 0)

    def test_stale_valid_result_uses_frozen_original_for_validation_and_never_applies(self):
        def during_call(_):
            self.store.mutate(self.p['id'], self.p['revision'], 'project.rename', {'title': 'Concurrent edit'}, 'concurrent_request')
        result = self.run_job(self.request(), FakeApplicators([{'ok': True, 'json': proposal()}], during_call))
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['outcomes'][0]['artifact']['revision'], self.p['revision'])
        self.assertEqual(self.store.get(self.p['id'])['title'], 'Concurrent edit')

    def test_stale_invalid_result_is_still_refused_against_frozen_schema(self):
        def during_call(_):
            self.store.mutate(self.p['id'], self.p['revision'], 'project.rename', {'title': 'Concurrent edit'}, 'concurrent_request')
        bad = {**proposal(), 'statements': [{'text': 'Pretend accepted', 'status': 'accepted'}]}
        result = self.run_job(self.request(), FakeApplicators([{'ok': True, 'json': bad}], during_call))
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['outcomes'])

    def test_signal_handlers_restored_after_isolated_worker(self):
        before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        self.run_job(self.request(), FakeApplicators([{'ok': True, 'json': proposal()}]))
        self.assertEqual({sig: signal.getsignal(sig) for sig in before}, before)

    def test_cancellation_during_call_is_not_overwritten(self):
        def during_call(_):
            job = self.store.jobs(self.p['id'])[0]
            self.store.update_job(job['id'], {'status': 'cancelled'})
        result = self.run_job(self.request(), FakeApplicators([{'ok': True, 'json': proposal()}], during_call))
        self.assertEqual(result['status'], 'cancelled')

    def test_source_identity_validation_refuses_unsupplied_fabricated_reference(self):
        bad = {**proposal(), 'statements': [{'text': 'A proposal', 'source_ids': ['invented_id']}]}
        result = self.run_job(self.request(), FakeApplicators([{'ok': True, 'json': bad}]))
        self.assertEqual(result['status'], 'failed')
        self.assertIn('source', result['attempts'][0]['error'].lower())

    def test_known_but_unsent_proposal_identifier_is_not_usable_context(self):
        self.p = self.store.mutate(self.p['id'], self.p['revision'], 'statement.propose', {'text': 'A private unaccepted alternative'}, 'unsent_request')
        identifier = C.active_branch(self.p)['statements'][-1]['id']
        request = self.request()
        self.assertNotIn(identifier, request['allowed_source_ids'])
        bad = {**proposal(), 'statements': [{'text': 'Reference a hidden draft', 'source_ids': [identifier]}]}
        result = self.run_job(request, FakeApplicators([{'ok': True, 'json': bad}]))
        self.assertEqual(result['status'], 'failed')
        self.assertIn('explicit context', result['attempts'][0]['error'])

    def test_refinement_intents_are_explicit_and_replacement_is_only_proposed(self):
        self.p = self.store.mutate(self.p['id'], self.p['revision'], 'statement.propose', {'text': 'Preserve 800 px.'}, 'intent_propose_request')
        original = C.active_branch(self.p)['statements'][-1]['id']
        self.p = self.store.mutate(self.p['id'], self.p['revision'], 'statement.accept', {'id': original}, 'intent_accept_request')
        for intent in ('improve', 'simplify', 'normalize'):
            request = self.request(refinement_intent=intent)
            self.assertEqual(request['context']['refinement_intent'], intent)
            self.assertIn('structural_findings', request['context'])
        result = self.run_job(self.request(refinement_intent='normalize'), FakeApplicators([{'ok': True, 'json': {
            **proposal(), 'statements': [{'text': 'The viewport width is 800 px.', 'replaces_id': original, 'source_ids': [original]}]}}]))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(C.active_branch(self.store.get(self.p['id']))['statements'][0]['text'], 'Preserve 800 px.')

    def test_compiler_repair_context_and_proposal_preserve_original_source(self):
        source = 'program Custom.\nlet item = .\nshow item.\n'
        result = {'ok': False, 'generated': False, 'source': source, 'fingerprint': C.fingerprint(self.p),
            'source_revision': self.p['revision'], 'diagnostics': {'diagnostics': [{'severity': 'error', 'line': 2, 'message': 'Missing expression'}]}}
        self.p = self.store.mutate(self.p['id'], self.p['revision'], 'validation.record', {'result': result}, 'compiler_receipt_request', trusted=True)
        request = self.request(refinement_intent='compiler_repair')
        repair = {'source_sha256': request['context']['compiler_repair']['source_sha256'], 'start': source.index(' .') + 1,
                  'end': source.index(' .') + 1, 'replacement': '2', 'diagnostic_index': 0, 'statement_ids': []}
        artifact = {**proposal(), 'statements': [], 'entities': [{'kind': 'evidence', 'entity': {
            'text': 'Insert the missing expression at the compiler error.', 'evidence_type': 'compiler_repair', 'repair': repair}}]}
        completed = self.run_job(request, FakeApplicators([{'ok': True, 'json': artifact}]))
        self.assertEqual(completed['status'], 'completed')
        p = C.transition(self.p, 'model.artifact', completed['outcomes'][0]['artifact'])
        row = C.active_branch(p)['entities']['evidence'][-1]
        self.assertEqual(row['status'], 'proposed')
        candidate = C.repair_candidate(p, row['id'])
        self.assertIn('let item = 2.', candidate['source'])
        self.assertEqual(C.active_branch(p)['validation']['source'], source)
        self.assertFalse(candidate['validated'])

    def test_compiler_repair_requires_real_current_error_and_refuses_changed_source(self):
        with self.assertRaisesRegex(StoreError, 'actual source error'):
            self.request(refinement_intent='compiler_repair')
        source = 'bad source'
        result = {'ok': False, 'source': source, 'fingerprint': C.fingerprint(self.p), 'source_revision': self.p['revision'],
            'diagnostics': {'diagnostics': [{'severity': 'error', 'line': 1, 'message': 'Invalid source'}]}}
        self.p = self.store.mutate(self.p['id'], self.p['revision'], 'validation.record', {'result': result}, 'repair_receipt_request', trusted=True)
        repair = {'source_sha256': '0' * 64, 'start': 0, 'end': 1, 'replacement': 'p', 'diagnostic_index': 0, 'statement_ids': []}
        with self.assertRaisesRegex(C.ForgeError, 'source has changed'):
            C.transition(self.p, 'entity.propose', {'kind': 'evidence', 'entity': {'text': 'Stale repair', 'evidence_type': 'compiler_repair', 'repair': repair}})


if __name__ == '__main__':
    unittest.main()
