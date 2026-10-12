"""Host-only: an explicit model selection in the intent interpreter reaches the host's real planning boundaries.

Moved from tests/intent. It drives integration/host/symblic_intent_api.py together with the host runner and
planner modules (host_runner, host_planner), which are not part of this repository, so it is skipped when they
are absent. Fake providers only.
"""
import copy
import json
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import host_runner as C
    import host_planner as CP
    from integration.host import symblic_intent_api as A
    from tests.integration import test_symblic_intent_api as Fixtures
    from tests.integration.test_symblic_intent_api import Reader, proposal, QUESTION, REAL_MODEL_ROUTE, SOURCE
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

from symblic.kernel import language as S
from symblic.intent import records as I
from symblic.intent import store as Store
from tests.intent.test_symblic_intent import artifact, event

LOCAL = 'ollama:deepseek-r1:1.5b@node-a+high'
OTHER = 'ollama:qwen3:4b@node-b'


class Selection(unittest.TestCase):
    new, job = Fixtures.Journey.new, Fixtures.Journey.job

    def setUp(self):
        Fixtures.Journey.setUp(self)
        change = patch.object(A, 'model_route', REAL_MODEL_ROUTE)
        change.start()
        self.addCleanup(change.stop)
        route = patch.object(C, 'warm_route', side_effect=AssertionError('explicit selection must not route globally'))
        route.start()
        self.addCleanup(route.stop)

    def change(self, v, by, token='select-model'):
        return A.revise({'id': v['state']['id'], 'revision': v['state']['revision'],
                         'event': {'id': token, 'kind': 'applicator', 'payload': {'by': by}}})

    def test_exact_selection_analysis_answer_compile_and_native_default(self):
        v = self.new(by=LOCAL, confidential=True)
        reader = Reader(proposal([QUESTION]))
        v = self.job(v, 'analyse', reader)
        self.assertEqual(reader.calls[0]['app']['spec'], LOCAL)
        self.assertEqual(reader.calls[0]['effort'], 'high')
        v = A.revise({'id': v['state']['id'], 'revision': v['state']['revision'], 'event': {
            'id': 'answer-output', 'kind': 'answer', 'payload': {'question_id': QUESTION['id'], 'text': 'Image'}}})
        reader = Reader(proposal())
        v = self.job(v, 'analyse', reader)
        self.assertEqual(reader.calls[0]['app']['spec'], LOCAL)
        source = 'ask result: Int = "Return five".\nshow result.\n'
        reader = Reader({'program': source, 'summary': 'Fixture question.'})
        with patch.object(CP, 'load_track', side_effect=AssertionError('explicit model cannot be suppressed by automatic planner history')):
            v = self.job(v, 'compile', reader)
        self.assertEqual(reader.calls[0]['app']['spec'], LOCAL)
        self.assertEqual(v['state']['policy']['by'], LOCAL)
        self.assertEqual(v['artifact']['effective_policy']['by'], LOCAL)
        self.assertEqual(v['budget']['used'], 3)
        native_reader = Reader(5)
        def start(body, **_kwargs):
            from symblic.kernel.run import Run
            self.assertEqual(body['options']['by'], LOCAL)
            self.assertFalse(body['options']['model_policy']['allow_cloud'])
            rep = Run(body['source'], body['inputs'], native_reader,
                      {**body['options'], 'parallel': 1}).execute()
            self.assertEqual(rep['status'], 'done', rep.get('error'))
            return {'id': 'abcd1234abcd'}
        with patch.object(C, 'start_run', side_effect=start) as launch:
            v = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
            again = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        self.assertEqual(native_reader.calls[0]['app']['spec'], LOCAL)
        self.assertEqual(v['handoff']['key'], again['handoff']['key'])
        launch.assert_called_once()

    def test_selection_revision_invalidates_artifact_and_keeps_spent_budget(self):
        v = self.job(self.new(by=LOCAL), 'analyse', Reader(proposal()))
        v = self.job(v, 'compile', Reader({'program': SOURCE, 'summary': 'Five.'}))
        old = copy.deepcopy(v)
        v = self.change(v, OTHER)
        self.assertIsNone(v['artifact'])
        self.assertIsNone(v['state']['checks'])
        self.assertEqual(v['state']['content_revision'], old['state']['content_revision'] + 1)
        self.assertEqual(v['budget']['used'], old['budget']['used'])
        self.assertNotEqual(I.content_digest(v['state']), I.content_digest(old['state']))
        self.assertNotEqual(A.current_pins(v['state'], self.env)['policy_sha256'], old['artifact']['policy_sha256'])
        with self.assertRaisesRegex(A.IntentApiError, 'stale'):
            A.start_job({'id': v['state']['id'], 'revision': old['state']['revision'], 'request_id': 'stale-selected'}, 'compile')
        with self.assertRaises(I.IntentError):
            self.change(old, LOCAL, 'another-event')
        # Exact revisioned event retry is idempotent even if the response was lost.
        again = self.change(old, OTHER)
        self.assertEqual(v['state'], again['state'])
        reader = Reader({'program': SOURCE, 'summary': 'Five.'})
        v = self.job(v, 'compile', reader)
        self.assertEqual(reader.calls[0]['app']['spec'], OTHER)
        self.assertEqual(v['budget']['used'], old['budget']['used'] + 1)

    def test_selected_failure_no_fallback_and_reserved_call_stays_spent(self):
        v = self.new(by=LOCAL)
        j = A.start_job({'id': v['state']['id'], 'revision': 0}, 'analyse')
        reader = Reader()
        result = A.work(v['state']['id'], j['job']['id'], reader)
        self.assertFalse(result['ok'])
        self.assertEqual([r['app']['spec'] for r in reader.calls], [LOCAL])
        self.assertEqual(A.view(v['state']['id'])['budget']['used'], 1)
        self.assertFalse(A.work(v['state']['id'], j['job']['id'], reader)['ok'])
        self.assertEqual(len(reader.calls), 1)

    def test_confidential_or_lowered_policy_refuses_before_dispatch(self):
        for payload in ({'confidential': True}, {'sources': [{'id': 'secret', 'text': 'Private source', 'kind': 'document', 'sensitivity': 'confidential'}]}):
            with self.subTest(payload=payload), self.assertRaisesRegex(A.IntentApiError, 'cloud'):
                self.new(by='claude:sonnet', **payload)
        v = self.new(by='claude:sonnet')
        self.env['policy']['allow_cloud'] = False
        j = A.start_job({'id': v['state']['id'], 'revision': 0}, 'analyse')
        reader = Reader(proposal())
        result = A.work(v['state']['id'], j['job']['id'], reader)
        self.assertFalse(result['ok'])
        self.assertIn('cloud', result['error'])
        self.assertEqual(reader.calls, [])
        self.assertEqual(A.view(v['state']['id'])['budget']['used'], 0)

    def test_budget_wrapper_rejects_wrong_spec_before_reservation(self):
        v = self.new(by=LOCAL)
        j = A.start_job({'id': v['state']['id'], 'revision': 0}, 'analyse')
        reader = Reader(proposal())
        apps = A.BudgetApplicators(reader, A.folder(v['state']['id']), j['job']['id'], v['state']['policy'])
        result = apps.call({'app': S.parse_applicator(OTHER)})
        self.assertFalse(result['ok'])
        self.assertEqual(reader.calls, [])
        self.assertEqual(A.view(v['state']['id'])['budget']['used'], 0)

    def test_invalid_selection_and_creation_identity(self):
        for by in (None, False, [], 'auto', 'council:debate', 'claude:sonnet,ollama:qwen', ' ollama:qwen', 'unknown:model'):
            with self.subTest(by=by), self.assertRaises(A.IntentApiError):
                self.new(by=by)
        self.new(by=LOCAL)
        with self.assertRaises(Store.StoreError):
            self.new(by=OTHER)

    def test_clear_selection_restores_existing_route_and_legacy_policy_shape(self):
        v = self.new(by=LOCAL)
        v = self.change(v, '')
        route = {'candidates': [OTHER], 'max_calls': 6, 'repairs': 1, 'allow_cloud': True}
        with patch.object(C, 'warm_route', return_value=route) as fallback:
            reader = Reader(proposal())
            self.job(v, 'analyse', reader)
        fallback.assert_called_once()
        self.assertEqual(reader.calls[0]['app']['spec'], OTHER)
        old = copy.deepcopy(v['state']); old['policy'].pop('by')
        self.assertNotIn('by', A.effective_policy(old, self.env))

    def test_generated_model_override_refuses_translation_not_silent_switch(self):
        v = self.job(self.new(by=LOCAL), 'analyse', Reader(proposal()))
        source = 'ask result: Int = "Return five" with by="' + OTHER + '".\nshow result.\n'
        reader = Reader({'program': source, 'summary': 'Wrong engine.'})
        j = A.start_job({'id': v['state']['id'], 'revision': v['state']['revision']}, 'compile')
        result = A.work(v['state']['id'], j['job']['id'], reader)
        self.assertFalse(result['ok'])
        v = A.view(v['state']['id'])
        self.assertEqual(v['artifact']['check']['errors'][0]['code'], 'INTENT_APPLICATOR')
        self.assertEqual([r['app']['spec'] for r in reader.calls], [LOCAL])
        self.assertEqual(v['budget']['used'], 2)
        self.assertIsNone(v['state']['checks'])
        self.assertTrue(A.checked_program(source, {}, [], by='')['ok'])
        self.assertTrue(A.checked_program(source.replace(OTHER, LOCAL), {}, [], by=LOCAL)['ok'])

    def test_recovery_requires_exact_selected_native_default(self):
        v = self.job(self.new(by=LOCAL), 'analyse', Reader(proposal()))
        v = self.job(v, 'compile', Reader({'program': SOURCE, 'summary': 'Five.'}))
        with patch.object(C, 'start_run', side_effect=TimeoutError('lost reply')):
            v = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        entry = Store.load(A.folder(v['state']['id']))['handoffs'][-1]
        native = self.path / 'native' / 'runs' / 'abcdef123456'; native.mkdir(parents=True)
        (native / 'program.sym').write_text(v['artifact']['source'])
        meta = {'prompt': '[Symblic intent ' + entry['key'] + ']\nfixture', 'inputs': v['artifact']['inputs'],
                'options': {'execution_pins': entry['execution_pins'], 'model_policy': self.env['policy'], 'by': OTHER}}
        with patch.object(C, 'run_dir', return_value=str(native)), patch.object(C, 'start_run', side_effect=AssertionError('recovery cannot relaunch')):
            (native / 'meta.json').write_text(json.dumps(meta))
            with self.assertRaisesRegex(A.IntentApiError, 'does not uniquely match'):
                A.reconcile({'id': v['state']['id'], 'run_id': native.name})
            meta['options']['by'] = LOCAL
            (native / 'meta.json').write_text(json.dumps(meta))
            recovered = A.reconcile({'id': v['state']['id'], 'run_id': native.name})
        self.assertTrue(recovered['handoff']['recovered'])


class PureSelection(unittest.TestCase):
    def test_owner_choice_changes_content_but_model_cannot_choose(self):
        s = I.new_intent('fixture', 'Compute five', policy={'by': LOCAL, 'allow_cloud': False})
        s = event(s, 'proposal', {'goal': 'Compute five'}, actor='model')
        checked = artifact(s)
        s = event(s, 'checked', {'artifact': checked}, actor='system')
        with self.assertRaises(I.IntentError):
            event(s, 'applicator', {'by': OTHER}, actor='model')
        changed = event(s, 'applicator', {'by': OTHER})
        self.assertIsNone(changed['checks'])
        self.assertNotEqual(I.content_digest(s), I.content_digest(changed))
        self.assertEqual(changed['policy']['by'], OTHER)
        self.assertEqual(changed['request'], s['request'])
        with self.assertRaises(I.IntentError):
            event(s, 'applicator', {'by': LOCAL, 'allow_cloud': True})


if __name__ == '__main__':
    unittest.main()
