"""Mixed proposal teams and atomic instruction coaching with isolated stores only."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from integration.host import symblic_forge as API
from symblic.forge import coach as Coach
from symblic.forge import core as C
from symblic.forge import models as M
from symblic.forge.store import Store, StoreError
from tests.forge.test_symblic_forge_models import FakeApplicators, proposal


def team(count=5):
    return {'version': 1, 'members': [{'id': 'member' + str(i), 'engine': 'ollama', 'model': 'fixture',
            'node': 'node-f', 'role': 'Perspective ' + str(i), 'characteristics': 'Exact trait "' + str(i) + '"',
            'instruction': 'Preserve 800 px and snake/src/state.js', 'settings': {'temperature': i / 10, 'seed': i}}
            for i in range(count)]}


class ForgeTeamCoachTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-team-coach-')
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.p = self.store.create('Create a bounded Snake game', '', '', 'create_request')
        self.number = 0

    def call(self, route, **data):
        self.number += 1
        data.setdefault('request_id', 'request_' + str(self.number))
        return API.dispatch('POST', route, data, db=self.store)

    def run_team(self, spec=None, replies=None, callback=None, **kwargs):
        request = M.build_request(self.p, 'IDEATOR', team=spec or team(), **kwargs)
        job = self.store.reserve_job(self.p['id'], self.p['revision'], request, 'reserve_request')[0]
        fake = FakeApplicators(replies or [{'ok': True, 'json': proposal()} for _ in request['team']['members']], callback)
        return M.run_job(job['id'], store=self.store, applicators=fake, check_host=False), fake

    def test_five_same_model_members_receive_distinct_exact_profiles_and_options(self):
        result, fake = self.run_team()
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(len(fake.calls), 5)
        self.assertEqual(len({r['context_sha256'] for r in result['outcomes']}), 5)
        for i, call in enumerate(fake.calls):
            self.assertEqual(call['tools'], 'none')
            self.assertEqual(call['seed'], i)
            self.assertEqual(call['temperature'], i / 10)
            self.assertEqual(call['app']['member']['role'], 'Perspective ' + str(i))
            self.assertEqual(json.loads(call['prompt'])['member_id'], 'member' + str(i))
            self.assertNotIn('peer_proposals', json.loads(call['prompt']))
            self.assertIn('snake/src/state.js', call['system'])
        self.assertEqual(self.store.get(self.p['id']), self.p)

    def test_mixed_providers_need_explicit_permission_and_preserve_effort(self):
        spec = team(2)
        spec['members'][1].update(engine='codex', model='gpt-5.4', node='node-b', effort='high', settings={})
        with self.assertRaisesRegex(StoreError, 'Explicitly allow'):
            M.build_request(self.p, 'IDEATOR', team=spec)
        result, fake = self.run_team(spec, allow_cloud=True)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(fake.calls[1]['app']['engine'], 'codex')
        self.assertEqual(fake.calls[1]['app']['node'], 'node-b')
        self.assertEqual(fake.calls[1]['effort'], 'high')
        self.assertNotIn('temperature', fake.calls[1])
        self.assertNotIn('seed', fake.calls[1])
        self.assertFalse(result['outcomes'][1]['fallback'])

    def test_team_never_inherits_role_fallback_or_reuses_peer_output(self):
        self.p = self.store.mutate(self.p['id'], 0, 'settings.set', {'roles': {'IDEATOR': {
            'app': 'ollama:old@node-a', 'allow_cloud': False, 'fallback': ['ollama:backup@node-b']}}}, 'settings_request')
        result, fake = self.run_team(team(2), [{'ok': False, 'error': 'offline'}, {'ok': True, 'json': proposal()}])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(result['outcomes'][0]['member_id'], 'member1')
        self.assertEqual(result['member_errors'][0]['member_id'], 'member0')
        self.assertNotIn('backup', json.dumps(result['attempts']))

    def test_failed_team_job_names_the_first_member_cause_at_job_level(self):
        result, _ = self.run_team(team(2), [StoreError('unavailable: ollama: invalid JSON schema in format'),
                                           StoreError('unavailable: fixture node offline')])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], result['member_errors'][0]['error'])
        self.assertIn('invalid JSON schema', result['error'])

    def test_partial_team_job_names_its_first_member_cause_at_job_level(self):
        result, _ = self.run_team(team(2), [StoreError('unavailable: ollama: invalid JSON schema in format'),
                                           {'ok': True, 'json': proposal()}])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['error'], result['member_errors'][0]['error'])
        self.assertIn('invalid JSON schema', result['error'])

    def test_critique_is_separate_bounded_frozen_proposal_context(self):
        replies = [{'ok': True, 'json': proposal('First perspective')}, {'ok': True, 'json': proposal('Second perspective')},
                   {'ok': True, 'json': proposal('Critique A')}, {'ok': True, 'json': proposal('Critique B')}]
        result, fake = self.run_team(team(2), replies, strategy='critique')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([r['phase'] for r in result['outcomes']], ['proposal', 'proposal', 'critique', 'critique'])
        a, b = (json.loads(call['prompt'])['peer_proposals'] for call in fake.calls[2:])
        self.assertEqual(a, b)
        self.assertNotIn('Critique A', json.dumps(b))
        self.assertEqual(len(a), 2)
        self.assertEqual(C.analyze(self.p)['counts']['accepted'], 0)

    def test_oversized_peer_context_is_refused_without_truncation_or_dispatch(self):
        replies = [{'ok': True, 'json': proposal('A' * 19000)}, {'ok': True, 'json': proposal('B' * 19000)},
                   {'ok': True, 'json': proposal('C' * 19000)}]
        result, fake = self.run_team(team(3), replies, strategy='critique')
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(len(result['outcomes']), 3)
        self.assertTrue(all('not truncated' in error['error'] for error in result['member_errors']))

    def test_successful_partial_results_can_be_adopted_together_once_as_proposals(self):
        result, _ = self.run_team(team(3), [{'ok': True, 'json': proposal('One')}, {'ok': False, 'error': 'offline'},
                                           {'ok': True, 'json': proposal('Three')}])
        adopted = self.call('model/adopt', id=self.p['id'], revision=0, job_id=result['id'], indices=[0, 1], request_id='adopt_request')
        rows = C.active_branch(adopted['project'])['statements']
        self.assertEqual([r['text'] for r in rows], ['One', 'Three'])
        self.assertTrue(all(r['status'] == 'proposed' for r in rows))
        self.assertEqual(adopted['project']['revision'], 1)
        self.assertEqual([r['provenance']['identity']['member']['id'] for r in rows], ['member0', 'member2'])
        again = self.call('model/adopt', id=self.p['id'], revision=0, job_id=result['id'], indices=[0, 1], request_id='adopt_request')
        self.assertTrue(again['duplicate'])
        self.assertEqual(C.import_manifest(C.export_manifest(adopted['project']))['branches'], adopted['project']['branches'])

    def test_duplicate_selection_and_browser_fabricated_artifacts_are_refused(self):
        result, _ = self.run_team(team(1))
        with self.assertRaises(StoreError):
            self.call('model/adopt', id=self.p['id'], revision=0, job_id=result['id'], indices=[0, 0])
        with self.assertRaises(StoreError):
            self.call('action', id=self.p['id'], revision=0, action='model.artifacts', payload={'artifacts': []})
        self.assertEqual(self.store.get(self.p['id']), self.p)

    def test_stale_team_cannot_be_adopted(self):
        def changed(i):
            if i == 1:
                self.store.mutate(self.p['id'], 0, 'project.rename', {'title': 'Changed'}, 'change_request')
        result, _ = self.run_team(team(2), callback=changed)
        self.assertEqual(result['status'], 'stale')
        with self.assertRaises(StoreError):
            self.call('model/adopt', id=self.p['id'], revision=1, job_id=result['id'], indices=[0, 1])

    def test_wrong_node_receipt_fails_and_preserves_requested_identity(self):
        result, _ = self.run_team(team(1), [{'ok': True, 'json': proposal(), 'node': 'node-a'}])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('different node', result['member_errors'][0]['error'])
        self.assertEqual(result['attempts'][0]['member']['node'], 'node-f')

    def test_worker_cancellation_between_members_is_not_overwritten(self):
        def cancelled(_):
            job = self.store.jobs(self.p['id'])[0]
            self.store.update_job(job['id'], {'status': 'cancelled'})
        result, fake = self.run_team(team(2), callback=cancelled)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(len(fake.calls), 1)

    def test_model_endpoint_retains_selected_team_and_explicit_coaching_context(self):
        with patch('symblic.autogen.runner.execution_fence'), patch.dict(API.launcher, launch=lambda _: {'ok': True}):
            answer = self.call('model/start', id=self.p['id'], revision=0, role='SPECIFIER', team=team(),
                               strategy='critique', refinement_intent='specify', lens='boundaries')
        request = answer['job']['request']
        self.assertEqual(len(request['team']['members']), 5)
        self.assertEqual(request['strategy'], 'critique')
        self.assertEqual(request['context']['ideation_lens']['id'], 'boundaries')
        self.assertIn('unknowns', request['context']['atomic_instruction_contract'])
        self.assertFalse(request['policy']['automatic_acceptance'])

    def complete_fields(self):
        return {'text': 'write exactly "800 px" to the declared output record.', 'input': 'value="800 px"',
                'output': 'the record named snake/src/state.js', 'check': 'the output equals the exact input string',
                'context': ['Only the provided value; no filesystem execution'], 'source_ids': [], 'lens': 'verification'}

    def test_coach_empty_preview_is_incomplete_and_cannot_be_proposed(self):
        before = copy.deepcopy(self.p)
        p = Coach.preview(self.p, {'text': 'Make it nice and then make it fast'})
        self.assertFalse(p['complete'])
        self.assertEqual(p['missing'], ['input', 'output', 'check', 'context'])
        self.assertIn('[Specify the input]', p['after'])
        self.assertTrue(p['granularity'])
        with self.assertRaises(C.ForgeError):
            C.transition(self.p, 'coach.propose', {'text': 'Make it nice'})
        self.assertEqual(self.p, before)

    def test_coach_exact_values_and_operator_edit_persist_only_after_proposal(self):
        fields = self.complete_fields()
        preview = self.call('coach/preview', id=self.p['id'], revision=0, **fields)['preview']
        self.assertTrue(preview['complete'])
        self.assertEqual(self.store.get(self.p['id']), self.p)
        self.assertEqual(len(preview['after'].splitlines()), 5)
        self.assertIn('"800 px"', preview['after'])
        edited = preview['after'] + '\nOperator clarification: preserve spaces.'
        result = self.call('coach/propose', id=self.p['id'], revision=0, **fields, edited_text=edited)
        statement = C.active_branch(result['project'])['statements'][0]
        self.assertEqual(statement['text'], edited)
        self.assertEqual(statement['status'], 'proposed')
        self.assertEqual(statement['provenance']['kind'], 'SYSTEM_DERIVED')
        self.assertFalse(result['analysis']['readiness']['ready'])

    def test_coach_sources_must_be_accepted_and_inputs_are_bounded(self):
        self.p = C.transition(self.p, 'statement.propose', {'text': 'An unaccepted detail'})
        source = C.active_branch(self.p)['statements'][0]['id']
        for fields in ({**self.complete_fields(), 'source_ids': [source]}, {'text': 'x', 'context': ['x'] * 31},
                       {'text': 'x', 'lens': 'invented'}, {'text': 'x', 'authority': 'accepted'}):
            with self.subTest(fields=fields), self.assertRaises(C.ForgeError):
                Coach.preview(self.p, fields)
        p = C.transition(self.p, 'statement.accept', {'id': source})
        self.assertEqual(Coach.preview(p, {**self.complete_fields(), 'source_ids': [source]})['source_ids'], [source])

    def test_coach_refuses_hidden_conversation_as_an_explicit_context_contract(self):
        for text in ('all prior context', 'the whole conversation', 'Use all previous context'):
            for changed in ({'context': [text]}, {'input': text}):
                fields = {**self.complete_fields(), **changed}
                preview = Coach.preview(self.p, fields)
                self.assertFalse(preview['complete'])
                self.assertIn('bounded_context', preview['missing'])
                with self.assertRaises(C.ForgeError):
                    C.transition(self.p, 'coach.propose', fields)

    def test_coach_overview_has_practical_tradeoffs_edges_and_labelled_examples_without_acceptance(self):
        overview = API.dispatch('GET', 'coach', query={'id': self.p['id']}, db=self.store)['coach']
        self.assertGreaterEqual(len(overview['lenses']), 6)
        self.assertTrue(all(row['alternatives'] and row['edge_cases'] for row in overview['lenses']))
        self.assertTrue(all(choice['tradeoffs'] for row in overview['lenses'] for choice in row['alternatives']))
        self.assertTrue(all(example['illustrative'] for example in overview['examples']))
        self.assertFalse(overview['readiness']['ready'])
        self.assertEqual(self.store.get(self.p['id']), self.p)


if __name__ == '__main__':
    unittest.main()
