"""Host-only: the original host's intent interpreter (journeys and recovery), with fake providers and temp stores.

These cases drive integration/host/symblic_intent_api.py and the host runner modules it imports (host_runner,
host_runner_capabilities, host_runner_jobs), which are not part of this repository, so they are skipped when
those modules are absent. The pure intent records, coverage, store and requirement execution are tested in
tests/intent.
"""
import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import host_runner as C
    import host_runner_capabilities as CH
    import host_runner_jobs as CR
    from integration.host import symblic_intent_api as A
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

from symblic.kernel import language as S
from symblic.intent import store as Store

REAL_MODEL_ROUTE = A.model_route


class Reader:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def call(self, req):
        self.calls.append(req)
        if not self.answers:
            return {'ok': False, 'fatal': True, 'error': 'no fixture reply'}
        return {'ok': True, 'json': {'answer': self.answers.pop(0)}, 'model': 'fixture', 'node': 'fake-node'}


def proposal(questions=None):
    return {'goal': 'Compute the clarified exact result.', 'requirements': [], 'assumptions': [],
            'questions': questions or [], 'examples': []}


QUESTION = {'id': 'q-output', 'field': 'output', 'question': 'Which output do you need?',
            'why': 'An image and a dimensional object require different artifacts.', 'blocking': True,
            'options': [{'id': 'image', 'label': 'Image', 'consequence': 'Produce a picture.'},
                        {'id': 'model', 'label': '3D model', 'consequence': 'Produce editable geometry.'}], 'source_refs': []}
SOURCE = 'let result = 2 + 3.\nshow result.\n'


class Journey(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.env = {'settings': {'direct': False, 'mode': 'full'},
                    'policy': {'max_calls': 6, 'repairs': 1, 'allow_cloud': True},
                    'rows': [{'name': 'fixture.read', 'effect': 'read', 'policy': 'auto',
                              'summary': 'A fake read tool; never executed.', 'params': {'type': 'object', 'properties': {}}}]}
        for obj, key, value in (
            (A, 'root', lambda: self.path), (A, 'environment', lambda: copy.deepcopy(self.env)),
            (A, 'model_route', lambda state, env: {**A.effective_policy(state, env), 'candidates': ['fake:fixture']}),
            (A, 'launcher', {'launch': lambda *_args: {'ok': True}, 'active': lambda *_args: False}),
            (CR, '_workflow', lambda *_args: None),
            (C, 'root', lambda: str(self.path / 'native')),
            (A, '_execution_run_folder', lambda ident: self.path / 'native' / 'runs' / ident),
            (C, 'check', lambda source: A.checked_program(source, {}, [])),
        ):
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.external = patch('socket.socket', side_effect=AssertionError('No network in interpreter tests'))
        self.external.start()
        self.addCleanup(self.external.stop)

    def new(self, **kwargs):
        return A.create({'request': 'Give the exact result of two plus three.', 'request_id': 'create-fixture', **kwargs})

    def job(self, v, kind, reader):
        j = A.start_job({'id': v['state']['id'], 'revision': v['state']['revision']}, kind)
        result = A.work(v['state']['id'], j['job']['id'], reader)
        v = A.view(v['state']['id'])
        self.assertTrue(result['ok'], (result, v['job']))
        return v

    def compiled(self):
        v = self.job(self.new(), 'analyse', Reader(proposal()))
        return self.job(v, 'compile', Reader({'program': SOURCE, 'summary': 'Computes five.'}))

    def test_actual_handoff_transition_joins_retained_native_checks(self):
        import hashlib
        from symblic.kernel import run as SR
        p = proposal()
        p['requirements'] = [{'id':'r-result','text':'Return five.','kind':'hard','origin':'model_extracted','source_refs':[]}]
        v = self.job(self.new(), 'analyse', Reader(p))
        v = A.revise({'id':v['state']['id'],'revision':v['state']['revision'],'event':{
            'id':'owner-predicate','kind':'predicate','payload':{'requirement_id':'r-result','predicate':'result = 5'}}})
        source = SOURCE + 'assert result = 5.\n'
        v = self.job(v, 'compile', Reader({'program':source,'summary':'Synthetic exact check.'}))
        native_folder = self.path/'native'/'runs'/'abcd1234abcd'
        def start(body, **_kwargs):
            native_folder.mkdir(parents=True)
            run = SR.Run(body['source'], body['inputs'], Reader(),
                         {**body['options'],'max_calls':0,'parallel':1}, folder=None)
            report = run.execute()
            self.assertEqual(report['status'],'done',report.get('error'))
            (native_folder/'program.sym').write_text(body['source'])
            (native_folder/'meta.json').write_text(json.dumps({'prompt':body['prompt'],'inputs':body['inputs'],
                'inputs_source_sha256':hashlib.sha256(body['source'].encode()).hexdigest(),'options':body['options']}))
            (native_folder/'state.json').write_text(json.dumps(report))
            (native_folder/'trace.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in run.trace))
            return {'id':'abcd1234abcd'}
        with patch.object(C,'start_run',side_effect=start) as launch:
            v = A.handoff({'id':v['state']['id'],'revision':v['state']['revision']})
        launch.assert_called_once()
        self.assertEqual(v['state']['phase'],'handed_off')
        self.assertIn('assurance',v['handoff']['envelope'])
        self.assertIn('request_sha256',v['handoff']['envelope'])
        self.assertEqual(v['execution_coverage']['status'],'joined',v['execution_coverage'])
        self.assertEqual(v['execution_coverage']['requirements'][0]['passed_checks'],1)
        self.assertEqual(v['execution_coverage']['requirements'][0]['status'],'observed_pass')
        self.assertEqual(v['artifact']['coverage']['execution'],'not_executed')
        self.execution_coverage_fixture = {'view':v,'native_folder':native_folder}

    def test_compatibility_without_translation_does_not_read_deployment(self):
        with patch.object(A, 'current_pins', side_effect=AssertionError('no artifact needs no comparison')):
            self.assertIsNone(self.new()['artifact_compatibility'])

    def test_pin_registry_ignores_unregistered_library_files(self):
        from symblic.kernel import execution_pins as X
        v = self.new()
        with patch.object(Path, 'glob', side_effect=AssertionError('pins must use the execution registry')):
            pins = A.current_pins(v['state'], self.env)
        self.assertEqual(X.PYTHON_FILES | X.LIBRARY_FILES.keys(), pins['module_hashes'].keys())

    def test_handed_off_request_refuses_new_compile_before_launch_or_budget(self):
        v = self.compiled()
        with patch.object(C, 'start_run', return_value={'id': 'abcd1234abcd'}):
            v = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        before = Store.load(A.folder(v['state']['id']))
        pins = {**A.current_pins(v['state'], self.env), 'kernel_id': 'f' * 64}
        with (patch.object(A, 'current_pins', return_value=pins),
              patch.dict(A.launcher, {'launch': lambda *_: self.fail('handed-off compile launched')}),
              self.assertRaisesRegex(A.IntentApiError, 'already has a handoff to the host runner')):
            A.start_job({'id': v['state']['id'], 'revision': v['state']['revision'],
                         'request_id': 'post-upgrade-compile'}, 'compile')
        self.assertEqual(before, Store.load(A.folder(v['state']['id'])))
        changed = A.revise({'id': v['state']['id'], 'revision': v['state']['revision'],
                            'event': {'id': 'new-content', 'kind': 'rewrite',
                                      'payload': {'text': 'Use three plus four instead.'}}})
        changed = self.job(changed, 'analyse', Reader(proposal()))
        changed = self.job(changed, 'compile', Reader({'program': SOURCE, 'summary': 'New fixture.'}))
        self.assertEqual('checked', changed['state']['phase'])
        self.assertEqual('abcd1234abcd', changed['handoff']['run_id'])

    def test_uncertain_handoff_also_refuses_compile(self):
        v = self.compiled()
        with patch.object(C, 'start_run', side_effect=TimeoutError('fixture')):
            v = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        with self.assertRaisesRegex(A.IntentApiError, 'uncertain outcome'):
            A.start_job({'id': v['state']['id'], 'revision': v['state']['revision']}, 'compile')

    def test_legacy_queued_compile_after_handoff_spends_no_call(self):
        v = self.compiled()
        with patch.object(C, 'start_run', return_value={'id': 'abcd1234abcd'}):
            v = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        path = A.folder(v['state']['id'])
        with Store.locked(path):
            row = Store.load(path)
            row['jobs'].append({'id': 'aaaaaaaabbbb', 'kind': 'compile', 'status': 'queued',
                                'revision': row['state']['revision'],
                                'content_revision': row['state']['content_revision']})
            Store.save(path, row)
        reader = Reader({'program': SOURCE, 'summary': 'Should never be read.'})
        result = A.work(v['state']['id'], 'aaaaaaaabbbb', reader)
        self.assertFalse(result['ok'])
        self.assertIn('already has a handoff to the host runner', result['error'])
        self.assertEqual([], reader.calls)
        self.assertEqual(v['budget']['used'], A.view(v['state']['id'])['budget']['used'])

    def test_view_reports_current_pins_without_changing_the_record_or_spending_calls(self):
        v = self.compiled()
        path = self.path / v['state']['id'] / 'record.json'
        before = path.read_bytes()
        with patch.object(C, 'start_run', side_effect=AssertionError('view must never dispatch')):
            latest = A.view(v['state']['id'])
        self.assertEqual('current', latest['artifact_compatibility']['status'])
        self.assertEqual([], latest['artifact_compatibility']['differences'])
        self.assertEqual(v['budget'], latest['budget'])
        self.assertEqual(before, path.read_bytes())

    def test_view_reports_each_changed_dependency_and_retains_the_translation(self):
        v = self.compiled()
        pins = A.current_pins(v['state'], self.env)
        for field, label in (('kernel_id', 'kernel'), ('module_hashes', 'modules'),
                             ('catalogue_sha256', 'catalogue'), ('policy_sha256', 'policy'),
                             ('source_hashes', 'sources')):
            with self.subTest(field=field):
                changed = {**pins, field: {} if isinstance(pins[field], dict) and pins[field] else 'changed'}
                with patch.object(A, 'current_pins', return_value=changed):
                    latest = A.view(v['state']['id'])
                self.assertEqual('stale', latest['artifact_compatibility']['status'])
                self.assertEqual([label], latest['artifact_compatibility']['differences'])
                self.assertEqual(v['artifact'], latest['artifact'])
                self.assertEqual(v['budget'], latest['budget'])
        modified = {**v['artifact'], 'intent_content_sha256': '0' * 64}
        self.assertEqual(['intent'], A.artifact_compatibility(v['state'], modified)['differences'])

    def test_metadata_failure_is_unknown_without_exposing_error_or_losing_history(self):
        v = self.compiled()
        with patch.object(A, 'environment', side_effect=OSError('private-detail-fixture')):
            latest = A.view(v['state']['id'])
        self.assertEqual('unknown', latest['artifact_compatibility']['status'])
        self.assertNotIn('private-detail-fixture', json.dumps(latest))
        self.assertEqual(v['artifact'], latest['artifact'])
        self.assertEqual(v['readback'], latest['readback'])
        with patch.object(A, 'current_pins', return_value={}):
            self.assertEqual('unknown', A.view(v['state']['id'])['artifact_compatibility']['status'])
        self.assertEqual('unknown', A.artifact_compatibility(v['state'], {})['status'])

    def test_stale_deployment_retains_existing_native_handle_and_never_restarts_it(self):
        v = self.compiled()
        body = {'id': v['state']['id'], 'revision': v['state']['revision']}
        with patch.object(C, 'start_run', return_value={'id': 'abcd1234abcd'}) as launch:
            started = A.handoff(body)
            pins = {**A.current_pins(started['state'], self.env), 'kernel_id': 'new-kernel'}
            with patch.object(A, 'current_pins', return_value=pins):
                latest = A.view(v['state']['id'])
                recovered = A.handoff(body)
            with patch.object(A, 'environment', side_effect=OSError('private metadata unavailable')):
                outage = A.handoff(body)
        self.assertEqual('stale', latest['artifact_compatibility']['status'])
        self.assertEqual('abcd1234abcd', latest['handoff']['run_id'])
        self.assertEqual(latest['handoff'], recovered['handoff'])
        self.assertEqual(latest['handoff'], outage['handoff'])
        self.assertEqual('unknown', outage['artifact_compatibility']['status'])
        self.assertEqual(1, launch.call_count)

    def test_matching_deployment_does_not_validate_an_internally_inconsistent_artifact(self):
        v = self.compiled()
        for mutation in ({'source': 'show 999.'}, {'inputs': {'extra': 1}}, {'content_revision': True}):
            with self.subTest(mutation=mutation):
                result = A.artifact_compatibility(v['state'], {**v['artifact'], **mutation})
                self.assertEqual('unknown', result['status'])

    def test_analysis_source_is_explicit_typed_one_question(self):
        check = S.check(A.ANALYSE_SOURCE)
        self.assertTrue(check['ok'], check)
        self.assertEqual(1, check['asks'])

    def test_actual_provider_schema_contains_nested_objects_not_any_string_fallback(self):
        reader = Reader(proposal([QUESTION]))
        self.job(self.new(), 'analyse', reader)
        fields = reader.calls[0]['schema']['properties']['answer']['properties']
        for name in ('requirements', 'assumptions', 'questions', 'examples'):
            self.assertEqual('object', fields[name]['items']['type'], name)
            self.assertEqual('object', fields[name]['items']['properties']['source_refs']['items']['type'])
        question = fields['questions']['items']['properties']
        self.assertEqual('boolean', question['blocking']['type'])
        self.assertEqual('object', question['options']['items']['type'])

    def test_create_retry_returns_same_session_but_nonce_cannot_change_request(self):
        a, b = self.new(), self.new()
        self.assertEqual(a['state']['id'], b['state']['id'])
        with self.assertRaises(Store.StoreError):
            self.new(request='Changed request')

    def test_clarification_answer_compile_and_exact_native_handoff_once(self):
        v = self.job(self.new(request='Make the flower I imagine.'), 'analyse', Reader(proposal([QUESTION])))
        self.assertEqual('clarifying', v['state']['phase'])
        with self.assertRaises(A.IntentApiError):
            A.start_job({'id': v['state']['id'], 'revision': v['state']['revision']}, 'compile')
        body = {'id': v['state']['id'], 'revision': v['state']['revision'],
                'event': {'id': 'answer-1', 'kind': 'answer', 'payload': {'question_id': 'q-output', 'option_id': 'image'}}}
        v = A.revise(body)
        self.assertIn('image', v['readback']['prompt'].lower())
        v = self.job(v, 'compile', Reader({'program': SOURCE, 'summary': 'Fixture only.'}))
        body = {'id': v['state']['id'], 'revision': v['state']['revision']}
        with patch.object(C, 'start_run', return_value={'id': 'abcd1234abcd'}) as start:
            first = A.handoff(body)
            second = A.handoff(body)
        self.assertEqual(1, start.call_count)
        self.assertEqual(SOURCE, start.call_args.args[0]['source'])
        self.assertEqual(first['handoff']['run_id'], second['handoff']['run_id'])
        self.assertEqual(2, first['budget']['used'])
        self.assertEqual('started', first['handoff']['status'])
        self.assertEqual('handed_off', first['state']['phase'])

    def test_mutation_retains_original_and_invalidates_artifact(self):
        v = self.compiled()
        original = v['state']['request']
        v = A.revise({'id': v['state']['id'], 'revision': v['state']['revision'],
                      'event': {'id': 'change-1', 'kind': 'rewrite', 'payload': {'text': 'Use three plus four instead.'}}})
        self.assertEqual(original, v['state']['request'])
        self.assertIsNone(v['artifact'])
        self.assertIn('three plus four', v['readback']['prompt'])
        with self.assertRaises(A.IntentApiError):
            A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})

    def test_worker_duplicate_and_job_double_click_do_not_dispatch_twice(self):
        v = self.new()
        body = {'id': v['state']['id'], 'revision': 0}
        j1, j2 = A.start_job(body, 'analyse'), A.start_job(body, 'analyse')
        self.assertEqual(j1['job']['id'], j2['job']['id'])
        reader = Reader(proposal())
        self.assertTrue(A.work(body['id'], j1['job']['id'], reader)['ok'])
        self.assertFalse(A.work(body['id'], j1['job']['id'], reader)['ok'])
        self.assertEqual(1, len(reader.calls))

    def test_invalid_model_source_quote_fails_without_owner_promotion(self):
        v = self.new()
        bad = proposal()
        bad['requirements'] = [{'id': 'r1', 'text': 'Invented', 'origin': 'owner_explicit'}]
        job = A.start_job({'id': v['state']['id'], 'revision': 0}, 'analyse')
        result = A.work(v['state']['id'], job['job']['id'], Reader(bad))
        self.assertFalse(result['ok'])
        latest = A.view(v['state']['id'])
        self.assertEqual('draft', latest['state']['phase'])
        self.assertEqual(1, latest['budget']['used'])

    def test_outer_json_acceptance_does_not_stop_proposal_validation_fallback(self):
        v = self.new()
        bad = proposal()
        bad['requirements'] = [{'id': 'r1', 'text': 'Invented owner statement', 'origin': 'owner_explicit'}]
        reader = Reader(bad, proposal())
        route = {**v['state']['policy'], 'candidates': ['fake:first', 'fake:second']}
        with patch.object(A, 'model_route', return_value=route):
            v = self.job(v, 'analyse', reader)
        self.assertEqual('fake:second', v['job']['evidence']['requested_app'])
        self.assertTrue(v['job']['evidence']['feedback_exposed'])
        self.assertEqual('not_established', v['job']['evidence']['independence'])
        self.assertEqual(2, v['budget']['used'])
        self.assertEqual(1, v['budget']['repairs_used'])

    def test_recognized_kernel_recipe_analyse_and_compile_without_models(self):
        self.env['settings']['direct'] = True
        self.env['policy']['max_calls'] = 0
        direct = {'ok': True, 'program': SOURCE, 'values': {}, 'workflow': {'recipe': 'fixture'}, 'calls': 0}
        with patch.object(CR, '_workflow', return_value=direct), \
                patch.object(A, 'model_route', side_effect=AssertionError('no model route for a kernel recipe')):
            v = self.job(self.new(), 'analyse', Reader())
            v = self.job(v, 'compile', Reader())
        self.assertEqual('checked', v['state']['phase'])
        self.assertEqual(0, v['budget']['used'])

    def test_requested_specifics_cannot_silently_accept_a_goal_only_reply(self):
        v = self.new(request='A flower diagram for a child; ask a useful clarification.')
        reader = Reader(proposal(), proposal([QUESTION]))
        route = {**v['state']['policy'], 'candidates': ['fake:first', 'fake:second']}
        j = A.start_job({'id': v['state']['id'], 'revision': 0, 'require_question': True}, 'analyse')
        with patch.object(A, 'model_route', return_value=route):
            result = A.work(v['state']['id'], j['job']['id'], reader)
        self.assertTrue(result['ok'], result)
        v = A.view(v['state']['id'])
        self.assertEqual('clarifying', v['state']['phase'])
        self.assertIn('requires a pending clarification', v['job']['evidence']['attempts'][0]['error'])
        self.assertEqual('presence_only', v['job']['evidence']['question_check'])
        self.assertEqual(2, v['budget']['used'])
        self.assertEqual(1, v['budget']['repairs_used'])

    def test_specifics_failure_retains_request_and_charge_without_inventing_a_question(self):
        v = self.new()
        j = A.start_job({'id': v['state']['id'], 'revision': 0, 'require_question': True}, 'analyse')
        result = A.work(v['state']['id'], j['job']['id'], Reader(proposal()))
        self.assertFalse(result['ok'])
        current = A.view(v['state']['id'])
        self.assertEqual(v['state'], current['state'])
        self.assertEqual(1, current['budget']['used'])
        self.assertEqual('failed', current['job']['status'])

    def test_specifics_requires_unanswered_blocking_question_in_merged_state(self):
        v = self.job(self.new(), 'analyse', Reader(proposal([QUESTION])))
        j = A.start_job({'id': v['state']['id'], 'revision': v['state']['revision'],
                         'require_question': True}, 'analyse')
        self.assertTrue(A.work(v['state']['id'], j['job']['id'], Reader(proposal()))['ok'])
        v = A.view(v['state']['id'])
        v = A.revise({'id': v['state']['id'], 'revision': v['state']['revision'],
                      'event': {'id': 'answer-mode', 'kind': 'answer',
                                'payload': {'question_id': 'q-output', 'option_id': 'image'}}})
        nonblocking = {**QUESTION, 'id': 'q-optional', 'blocking': False}
        j = A.start_job({'id': v['state']['id'], 'revision': v['state']['revision'],
                         'require_question': True}, 'analyse')
        result = A.work(v['state']['id'], j['job']['id'], Reader(proposal([nonblocking])))
        self.assertFalse(result['ok'])
        self.assertIn('blocking=true', result['error'])
        self.assertEqual(v['state'], A.view(v['state']['id'])['state'])

    def test_question_mode_is_typed_and_part_of_the_operation_identity(self):
        v = self.new()
        body = {'id': v['state']['id'], 'revision': 0, 'request_id': 'specifics'}
        for malformed in (None, 1, 'true', []):
            with self.assertRaises(A.IntentApiError):
                A.start_job({**body, 'require_question': malformed}, 'analyse')
        j = A.start_job({**body, 'require_question': True}, 'analyse')
        same = A.start_job({**body, 'require_question': True}, 'analyse')
        self.assertEqual(j['job']['id'], same['requested_job']['id'])
        with self.assertRaises(A.IntentApiError):
            A.start_job({**body, 'require_question': False}, 'analyse')

    def test_failed_requested_refinement_blocks_old_translation_until_successful_readback(self):
        self.env['policy']['repairs'] = 5
        v = self.compiled()
        ident = v['state']['id']
        old_artifact = v['artifact']
        body = {'id': ident, 'revision': v['state']['revision']}
        j = A.start_job({**body, 'require_question': True}, 'analyse')
        self.assertFalse(A.work(ident, j['job']['id'], Reader(proposal()))['ok'])
        current = A.view(ident)
        self.assertEqual(old_artifact, current['artifact'])
        self.assertTrue(current['validation']['readiness']['analysis_required'])
        with self.assertRaises(A.IntentApiError):
            A.start_job({**body, 'request_id': 'blocked-compile'}, 'compile')
        with patch.object(C, 'start_run', side_effect=AssertionError('No native dispatch')), \
                self.assertRaises(A.IntentApiError):
            A.handoff(body)
        # A later failed readback-only attempt is not an escape hatch.
        j = A.start_job({**body, 'request_id': 'failed-readback'}, 'analyse')
        self.assertFalse(A.work(ident, j['job']['id'], Reader())['ok'])
        self.assertTrue(A.view(ident)['validation']['readiness']['analysis_required'])
        j = A.start_job({**body, 'request_id': 'successful-readback'}, 'analyse')
        self.assertTrue(A.work(ident, j['job']['id'], Reader(proposal()))['ok'])
        self.assertFalse(A.view(ident)['validation']['readiness']['analysis_required'])

    def test_specifics_mode_does_not_add_questions_or_calls_to_exact_recipe(self):
        self.env['settings']['direct'] = True
        self.env['policy']['max_calls'] = 0
        v = self.new()
        j = A.start_job({'id': v['state']['id'], 'revision': 0, 'require_question': True}, 'analyse')
        direct = {'ok': True, 'program': SOURCE, 'values': {}, 'workflow': {'recipe': 'fixture'}, 'calls': 0}
        with patch.object(CR, '_workflow', return_value=direct), \
                patch.object(A, 'model_route', side_effect=AssertionError('no model route')):
            result = A.work(v['state']['id'], j['job']['id'], Reader())
        self.assertTrue(result['ok'], result)
        current = A.view(v['state']['id'])
        self.assertEqual([], current['state']['questions'])
        self.assertEqual(0, current['budget']['used'])

    def test_shared_budget_does_not_reset_for_compile_or_failed_reply(self):
        self.env['policy']['max_calls'] = 1
        v = self.job(self.new(), 'analyse', Reader(proposal()))
        job = A.start_job({'id': v['state']['id'], 'revision': v['state']['revision']}, 'compile')
        reader = Reader({'program': SOURCE, 'summary': 'Five.'})
        result = A.work(v['state']['id'], job['job']['id'], reader)
        self.assertFalse(result['ok'])
        self.assertEqual([], reader.calls)
        self.assertEqual(1, A.view(v['state']['id'])['budget']['used'])

    def test_stop_reaches_provider_and_prevents_next_candidate_without_refunding(self):
        v = self.new()
        stop_event = threading.Event()
        calls = []
        class Cancellable:
            def call(self, request):
                calls.append(request)
                self_stop = request.get('stop')
                self_stop.set()
                return {'ok': False, 'fatal': True, 'error': 'stopped'}
        route = {**v['state']['policy'], 'candidates': ['fake:first', 'fake:second']}
        j = A.start_job({'id': v['state']['id'], 'revision': 0}, 'analyse')
        with patch.object(A, 'model_route', return_value=route):
            result = A.work(v['state']['id'], j['job']['id'], Cancellable(), stop_event)
        self.assertFalse(result['ok'])
        self.assertEqual(1, len(calls))
        self.assertIs(stop_event, calls[0]['stop'])
        self.assertEqual(1, A.view(v['state']['id'])['budget']['used'])

    def test_worker_main_installs_shared_stop_handler_before_work(self):
        with patch.object(CR, '_stop_on_signal') as install, patch.object(A, 'work', return_value={'ok': True}) as work:
            self.assertEqual(0, A.main(['--session', '123456789abc', '--job', 'abcdef123456']))
        self.assertIs(install.call_args.args[0], work.call_args.kwargs['stop_event'])
        self.assertIs(A.worker_environment, work.call_args.kwargs['environment_fn'])

    def test_standalone_worker_uses_site_declarations_not_partial_import_registry(self):
        with patch.object(C, 'settings', return_value=copy.deepcopy(C.DEFAULT_SETTINGS)), \
                patch.object(C, 'catalogue_rows', side_effect=AssertionError('partial standalone registry')), \
                patch.object(CH, 'site_http', return_value=(200, {'items': self.env['rows']})) as http:
            actual = A.worker_environment()
        self.assertEqual('fixture.read', actual['rows'][0]['name'])
        self.assertEqual(('GET', '/api/personal-agent/capabilities'), http.call_args.args[:2])

    def test_confidential_call_gate_drops_cloud_before_reservation(self):
        v = self.new(confidential=True)
        self.assertFalse(v['state']['policy']['allow_cloud'])
        reader = Reader(proposal())
        wrapper = A.BudgetApplicators(reader, self.path, 'not-used', {'allow_cloud': False, 'max_calls': 6})
        answer = wrapper.call({'app': {'engine': 'claude'}})
        self.assertFalse(answer['ok'])
        self.assertEqual([], reader.calls)

    def test_confidential_intent_resolves_candidates_under_its_lowered_policy(self):
        v = self.new(confidential=True)
        with patch.object(C, 'warm_route', return_value={'candidates': ['fake:fixture'], 'max_calls': 6}) as warm:
            route = REAL_MODEL_ROUTE(v['state'], self.env)
        self.assertEqual({'max_calls': 6, 'repairs': 1, 'allow_cloud': False}, warm.call_args.args[2])
        self.assertFalse(route['allow_cloud'])

    def test_native_runner_receives_only_supported_lower_policy_fields(self):
        v = self.job(self.new(confidential=True), 'analyse', Reader(proposal()))
        v = self.job(v, 'compile', Reader({'program': SOURCE, 'summary': 'Five.'}))
        native_root = self.path / 'native'
        native_root.mkdir()
        with patch.object(C, 'root', return_value=str(native_root)), \
                patch.object(C, 'settings', return_value=copy.deepcopy(C.DEFAULT_SETTINGS)), \
                patch.dict(C.launcher, {'launch': lambda *_args: {'ok': True}}):
            result = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        self.assertEqual('started', result['handoff']['status'], result['handoff'])
        meta = json.loads((native_root / 'runs' / result['handoff']['run_id'] / 'meta.json').read_text())
        self.assertEqual({'max_calls': 6, 'repairs': 1, 'allow_cloud': False}, meta['options']['model_policy'])
        self.assertTrue(result['state']['policy']['confidential'])

    def test_explicit_new_attempt_retains_failed_call_and_shared_retry_budget(self):
        v = self.new()
        bad = proposal()
        bad['requirements'] = [{'id': 'r1', 'text': 'Invented owner statement', 'origin': 'owner_explicit'}]
        for i in range(2):
            j = A.start_job({'id': v['state']['id'], 'revision': 0, 'request_id': f'attempt-{i}'}, 'analyse')
            self.assertFalse(A.work(v['state']['id'], j['job']['id'], Reader(bad))['ok'])
        reader = Reader(proposal())
        j = A.start_job({'id': v['state']['id'], 'revision': 0, 'request_id': 'attempt-2'}, 'analyse')
        self.assertFalse(A.work(v['state']['id'], j['job']['id'], reader)['ok'])
        self.assertEqual([], reader.calls)
        latest = A.view(v['state']['id'])
        self.assertEqual(2, latest['budget']['used'])
        self.assertEqual(1, latest['budget']['repairs_used'])

    def test_changed_catalogue_blocks_handoff_before_native_launch(self):
        v = self.compiled()
        self.env['rows'] = [{'name': 'changed.tool', 'effect': 'read', 'policy': 'auto', 'params': {}}]
        with patch.object(C, 'start_run') as launch, self.assertRaises(ValueError):
            A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        launch.assert_not_called()

    def test_launch_exception_stays_uncertain_and_is_never_retried(self):
        v = self.compiled()
        body = {'id': v['state']['id'], 'revision': v['state']['revision']}
        with patch.object(C, 'start_run', side_effect=TimeoutError('fixture timeout')) as launch:
            result = A.handoff(body)
            again = A.handoff(body)
        self.assertEqual(1, launch.call_count)
        self.assertEqual('uncertain', result['handoff']['status'])
        self.assertEqual('uncertain', again['handoff']['status'])

    def test_lost_native_reply_recovers_existing_clock_pinned_run_without_dispatch(self):
        source = 'given today: Text.\nshow today.\n'
        v = self.job(self.new(), 'analyse', Reader(proposal()))
        v = self.job(v, 'compile', Reader({'program': source, 'summary': 'Show the recorded day.'}))
        original_start = C.start_run
        handles = []
        def lost_reply(*args, **kwargs):
            handles.append(original_start(*args, **kwargs)['id'])
            raise TimeoutError('reply lost after native persistence')
        with patch.object(C, 'settings', return_value=copy.deepcopy(C.DEFAULT_SETTINGS)), \
                patch.dict(C.launcher, {'launch': lambda *_args: {'ok': True}}), \
                patch.object(C, 'start_run', side_effect=lost_reply) as start:
            pending = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
            recovered = A.reconcile({'id': v['state']['id']})
        self.assertEqual('uncertain', pending['handoff']['status'])
        self.assertEqual(1, start.call_count)
        self.assertEqual(handles[0], recovered['handoff']['run_id'])
        self.assertTrue(recovered['handoff']['recovered'])
        self.assertEqual(v['artifact']['inputs'], recovered['handoff']['envelope']['inputs'])
        self.assertIn('today', recovered['artifact']['inputs'])

    def test_malformed_native_metadata_is_skipped_during_reconciliation(self):
        v = self.compiled()
        with patch.object(C, 'start_run', side_effect=TimeoutError('fixture')):
            A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        p = self.path / 'native' / 'runs' / 'badc0ffee1234'
        p.mkdir(parents=True)
        (p / 'program.sym').write_text(SOURCE)
        for meta in ([], {'options': []}, {'options': {'model_policy': []}}):
            with self.subTest(meta=meta):
                (p / 'meta.json').write_text(json.dumps(meta))
                self.assertEqual('uncertain', A.reconcile({'id': v['state']['id']})['handoff']['status'])

    def test_prior_job_nonce_recovers_its_own_handle_after_later_job(self):
        v = self.new()
        body = {'id': v['state']['id'], 'revision': 0, 'request_id': 'first-analysis'}
        initial = A.start_job(body, 'analyse')
        self.assertTrue(A.work(v['state']['id'], initial['job']['id'], Reader(proposal()))['ok'])
        later = self.job(A.view(v['state']['id']), 'compile', Reader({'program': SOURCE, 'summary': 'Five.'}))
        repeated = A.start_job(body, 'analyse')
        self.assertEqual(initial['job']['id'], repeated['requested_job']['id'])
        self.assertEqual(later['job']['id'], repeated['job']['id'])

    def test_long_readback_is_retained_in_compiler_model_input(self):
        request = 'Keep this detail. ' * 450 + 'Final detail must remain.'
        v = self.job(self.new(request=request), 'analyse', Reader(proposal()))
        reader = Reader({'program': SOURCE, 'summary': 'Fixture only.'})
        v = self.job(v, 'compile', reader)
        self.assertIn(request, reader.calls[0]['prompt'])
        self.assertEqual(request, v['state']['request']['text'])

    def test_client_cannot_submit_system_receipt_and_owner_gate_precedes_io(self):
        v = self.new()
        with self.assertRaises(A.IntentApiError):
            A.revise({'id': v['state']['id'], 'revision': 0,
                      'event': {'id': 'forged', 'kind': 'checked', 'actor': 'system', 'payload': {}}})
        class Denied:
            def require_owner(self, _label):
                return False
        with patch.object(A, 'create', side_effect=AssertionError('owner gate did not run first')):
            self.assertTrue(A.handle(Denied(), 'POST', 'intent/create', {}))

    def test_disk_sync_failure_prevents_dispatch(self):
        v = self.new()
        with patch.object(Store.os, 'fsync', side_effect=OSError('fixture disk failure')), \
                patch.dict(A.launcher, {'launch': lambda *_args: self.fail('launch before durable intent')}), \
                self.assertRaises(OSError):
            A.start_job({'id': v['state']['id'], 'revision': 0}, 'analyse')

    def test_damaged_budget_fails_closed_instead_of_reset(self):
        v = self.new()
        p = self.path / v['state']['id'] / 'record.json'
        row = json.loads(p.read_text())
        row['budget']['used'] = 0
        row['budget']['reservations'] = [{'job': 'fake'}]
        p.write_text(json.dumps(row))
        with self.assertRaises(Store.StoreError):
            A.view(v['state']['id'])

    def test_concurrent_duplicate_handoff_only_one_dispatch(self):
        v = self.compiled()
        body = {'id': v['state']['id'], 'revision': v['state']['revision']}
        entered, finish = threading.Event(), threading.Event()
        def start(*_args, **_kwargs):
            entered.set()
            finish.wait(3)
            return {'id': 'abcd1234abcd'}
        with patch.object(C, 'start_run', side_effect=start) as launch:
            t = threading.Thread(target=lambda: A.handoff(body))
            t.start()
            self.assertTrue(entered.wait(3))
            pending = A.handoff(body)
            finish.set()
            t.join(3)
        self.assertEqual('intent', pending['handoff']['status'])
        self.assertEqual(1, launch.call_count)

    def test_multiline_typo_is_not_silently_another_model_question(self):
        source = 'ask diagnosis: Text "What is this?"\neffort=ultra, agree=0.7\nshow diagnosis.'
        self.assertTrue(S.check(source)['ok'])
        check = A.checked_program(source, {}, [])
        self.assertFalse(check['ok'])
        self.assertIn('SYM_IMPLICIT_ASK', [e.get('code') for e in check['errors']])


    def test_compiler_and_handoff_receive_sources_and_negative_examples(self):
        v = self.new(sources=[{'id': 'invoice', 'text': 'Specific source exception: exclude refunds.'}])
        p = proposal()
        p['requirements'] = [{'id': 'r-total', 'text': 'Return total only.', 'kind': 'hard', 'origin': 'model_extracted', 'source_refs': []}]
        p['examples'] = [{'id': 'negative-refund', 'kind': 'negative', 'description': 'Never include refunded items.', 'source_refs': []}]
        v = self.job(v, 'analyse', Reader(p))
        reader = Reader({'program': SOURCE, 'summary': 'Fixture'})
        v = self.job(v, 'compile', reader)
        prompt = reader.calls[0]['prompt']
        self.assertIn('Specific source exception: exclude refunds.', prompt)
        self.assertIn('Never include refunded items.', prompt)
        self.assertEqual(['r-total'], v['artifact']['coverage']['unmapped_hard_ids'])
        with patch.object(C, 'start_run', return_value={'id': 'abcd1234abcd'}) as native:
            result = A.handoff({'id': v['state']['id'], 'revision': v['state']['revision']})
        self.assertIn('Specific source exception: exclude refunds.', native.call_args.args[0]['prompt'])
        self.assertIn('Never include refunded items.', native.call_args.args[0]['prompt'])
        self.assertEqual(['r-total'], result['handoff']['envelope']['coverage']['unmapped_hard_ids'])

    def test_huge_required_source_refuses_compile_before_call_and_is_retained(self):
        v = self.new(sources=[{'id': 'huge', 'text': 'Required detail. ' * 200}])
        v = self.job(v, 'analyse', Reader(proposal()))
        before = v['budget']['used']
        reader = Reader({'program': SOURCE, 'summary': 'Must not be used'})
        job = A.start_job({'id': v['state']['id'], 'revision': v['state']['revision']}, 'compile')
        with patch.object(A, 'COMPILE_REQUEST_LIMIT', 2000):
            result = A.work(v['state']['id'], job['job']['id'], reader)
        self.assertFalse(result['ok'])
        self.assertEqual([], reader.calls)
        view = A.view(v['state']['id'])
        self.assertEqual(before, view['budget']['used'])
        self.assertEqual('Required detail. ' * 200, view['state']['sources'][1]['text'])
        self.assertIn('no requirement, source or example was removed', result['error'])

    def test_owner_predicate_editor_is_operative_and_model_cannot_assign_actor(self):
        p = proposal()
        p['requirements'] = [{'id': 'r-result', 'text': 'Return five.', 'kind': 'hard', 'origin': 'model_extracted', 'source_refs': []}]
        v = self.job(self.new(), 'analyse', Reader(p))
        body = {'id': v['state']['id'], 'revision': v['state']['revision'], 'event': {
            'id': 'owner-check', 'kind': 'predicate', 'actor': 'model',
            'payload': {'requirement_id': 'r-result', 'predicate': 'result = 5'}}}
        v = A.revise(body)
        self.assertEqual('owner_predicate', v['state']['sources'][-1]['kind'])
        reader = Reader({'program': SOURCE + 'assert result = 5.\n', 'summary': 'Fixture'})
        v = self.job(v, 'compile', reader)
        self.assertEqual(['r-result'], v['artifact']['coverage']['predicate_present_ids'])
        self.assertEqual('not_executed', v['artifact']['coverage']['execution'])

    def test_owner_predicate_editor_rejects_statement_injection_without_changing_state(self):
        v = self.job(self.new(), 'analyse', Reader(proposal()))
        for predicate in ('true. show 1.', 'true else retry', '', '(' * 100 + 'true' + ')' * 100):
            with self.subTest(predicate=predicate), self.assertRaises(A.IntentApiError):
                A.revise({'id': v['state']['id'], 'revision': v['state']['revision'], 'event': {
                    'id': 'bad-predicate', 'kind': 'predicate',
                    'payload': {'requirement_id': 'missing', 'predicate': predicate}}})
        self.assertEqual(v['state'], A.view(v['state']['id'])['state'])

    def test_source_identity_is_retained_and_confidential_source_constrains_policy(self):
        source = {'id': 'private-note', 'text': 'Private source fixture.', 'sensitivity': 'lab-confidential'}
        v = self.new(sources=[source])
        self.assertFalse(v['state']['policy']['allow_cloud'])
        self.assertTrue(v['state']['policy']['confidential'])
        self.assertEqual(source['text'], v['state']['sources'][1]['text'])
        with self.assertRaises(Store.StoreError):
            self.new(sources=[{**source, 'text': 'Different source with same request token.'}])

    def test_source_supplement_cannot_be_skipped_by_a_direct_recipe(self):
        self.env['settings']['direct'] = True
        v = self.new(sources=[{'id': 'source', 'text': 'A required qualification.'}])
        with patch.object(CR, '_workflow', side_effect=AssertionError('recipe would omit supplemental source')):
            v = self.job(v, 'analyse', Reader(proposal()))
        self.assertEqual('specified', v['state']['phase'])

class HostRunFolderLookup(unittest.TestCase):
    """Moved from tests/intent: the host's configured run-folder lookup never creates a missing store."""

    def test_configured_path_lookup_never_creates_missing_store(self):
        from tests.intent.test_symblic_requirement_execution import fixture
        with tempfile.TemporaryDirectory() as temporary:
            absent = Path(temporary) / 'absent'
            data = fixture()
            with patch.dict(os.environ, {'HOST_RUNNER_DATA_DIR': str(absent)}):
                self.assertEqual(A._execution_run_folder('abcdef123456'), absent / 'runs' / 'abcdef123456')
                row = {'state': data[0], 'artifact': data[1], 'handoffs': [data[2]]}
                self.assertEqual(A.execution_coverage(row)['status'], 'unknown')
            self.assertFalse(absent.exists())


if __name__ == '__main__':
    unittest.main()
