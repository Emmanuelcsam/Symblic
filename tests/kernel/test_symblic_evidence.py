"""Evidence and escalation regressions: fake readers, no files or external calls."""

import copy
import unittest

from symblic.kernel import language as S
from symblic.kernel import embed as EMB
from symblic.kernel import certificates as C
from symblic.kernel.run import Run


class Readers:
    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def call(self, req):
        self.requests.append(req)
        result = self.answers[req['app']['model']]
        if isinstance(result, list):
            result = result.pop(0)
        return {'ok': True, 'json': {'answer': result}, 'model': req['app']['model'], 'node': 'fake-node'}


class Evidence(unittest.TestCase):
    def test_requested_model_and_node_do_not_invent_observed_provenance(self):
        class MissingMetadata:
            def call(self, _request):
                return {'ok': True, 'json': {'answer': 2}}
        rep = Run('ask x:Int "count" by {app:"fake:requested@node-a", mode:"count", sources:["s"]}.',
                  applicators=MissingMetadata()).execute()
        self.assertEqual(rep['status'], 'done', rep)
        ev = rep['bindings'][0]['meta']['evidence']
        observed = ev['observations'][0]
        self.assertEqual((observed['model'], observed['node']), ('', ''))
        self.assertEqual(observed['requested_node'], 'node-a')
        self.assertEqual(ev['missing_provenance'], [0])

    def test_kernel_ambiguity_keeps_witnesses_without_model_calls(self):
        readers = Readers({'a': 2})
        rep = Run('ask x:Int in 1..3 "pick" by kernel with solve=true\nensure x>1 else retry.',
                  applicators=readers).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['code'], 'SYM_UNDERDETERMINED')
        self.assertEqual(rep['evidence']['determinations'][0]['witnesses'], [2, 3])
        self.assertFalse(rep['bindings'])
        self.assertEqual(readers.requests, [])

    def test_modes_do_not_erase_shared_source_or_claim_independence(self):
        source = '''group panel = [
          {app: "fake:a", mode: "text-extraction", sources: ["paper:1"], assumptions: ["basis:total"]},
          {app: "fake:b", mode: "counterexample", sources: ["paper:1"], assumptions: ["basis:total"]}].
        ask x: Int "Read the count" by panel.
        assert x = 2.
        '''
        run = Run(source, applicators=Readers({'a': 2, 'b': 2}))
        rep = run.execute()
        self.assertEqual(rep['status'], 'done', rep)
        ev = rep['bindings'][0]['meta']['evidence']
        self.assertEqual(ev['declared_modes'], ['counterexample', 'text-extraction'])
        self.assertEqual(ev['independence'], 'not_established')
        self.assertEqual(ev['assurance'], 'typed_answer')
        shared = {(x['kind'], x['id']) for x in ev['shared_dependencies']}
        self.assertIn(('source', 'paper:1'), shared)
        self.assertIn(('assumption', 'basis:total'), shared)
        self.assertTrue(any(x['kind'] == 'capsule' for x in ev['shared_dependencies']))
        self.assertEqual(len(rep['evidence']['checks']), 1)
        check = rep['evidence']['checks'][0]
        self.assertTrue(check['passed'])
        self.assertEqual(check['scope'], 'encoded_predicate')
        self.assertEqual(check['bindings'][0]['hash'], S.fingerprint(2))
        self.assertEqual(len(check['predicate_sha256']), 64)

    def test_invalid_mode_metadata_refused_before_call(self):
        readers = Readers({'a': 1})
        rep = Run('ask x: Int "x" by {app:"fake:a", mode:true}.', applicators=readers).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(readers.requests, [])

    def test_peer_exposure_and_missing_provenance_are_visible(self):
        rep = Run('ask x: Int "x" by ["fake:a", "fake:b"] with effort=ultra.',
                  applicators=Readers({'a': 2, 'b': 2})).execute()
        self.assertEqual(rep['status'], 'done', rep)
        ev = rep['bindings'][0]['meta']['evidence']
        self.assertTrue(ev['missing_provenance'])
        self.assertTrue(any(o['peer_exposed'] for o in ev['observations']))
        self.assertTrue(any(not o['peer_exposed'] for o in ev['observations']))
        self.assertTrue(all(len(o['request_sha256']) == 64 for o in ev['observations']))

    def test_retry_rolls_back_passed_check_receipts(self):
        source = '''ask x: Int "x" by "fake:a" with retries=1.
        ensure x > 0 else retry.
        ensure x = 2 else retry.
        '''
        rep = Run(source, applicators=Readers({'a': [1, 2]})).execute()
        self.assertEqual(rep['status'], 'done', rep)
        receipts = rep['evidence']['checks']
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(r['passed'] for r in receipts))
        self.assertTrue(all(r['bindings'][0]['hash'] == S.fingerprint(2) for r in receipts))

    def test_statement_events_are_copied_and_failure_is_visible(self):
        rows = []
        def event(row):
            rows.append(copy.deepcopy(row))
            row['status'] = 'forged'
        run = Run('let x=2.\nassert x=2.\nshow x.', options={'on_event': event})
        rep = run.execute()
        self.assertEqual(rep['status'], 'done')
        self.assertEqual([r['sequence'] for r in rows], [1, 2, 3])
        self.assertTrue(all(r['status'] == 'ok' for r in run.trace))
        def fail(_row):
            raise ValueError('private callback details')
        rep = Run('let x=2.\nlet y=3.', options={'on_event': fail}).execute()
        self.assertEqual(rep['error']['kind'], 'event')
        self.assertNotIn('private callback details', rep['error']['message'])
        self.assertEqual(len(rep['bindings']), 1)


class Escalation(unittest.TestCase):
    SOURCE = '''ask item_count: Int "Count the supplied items" by ["fake:small", "fake:strong"]
        with route=escalate, retries=1.
        let doubled: Int = item_count * 2.
        ensure doubled = 8 else retry.
        show doubled.
        '''

    def test_small_success_never_calls_larger_model(self):
        apps = Readers({'small': 4, 'strong': 4})
        rep = Run(self.SOURCE, applicators=apps).execute()
        self.assertEqual(rep['status'], 'done', rep)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(rep['bindings'][0]['meta']['selected'], 'fake:small')

    def test_invalid_answer_retries_then_escalates_without_leaking_bindings(self):
        apps = Readers({'small': 3, 'strong': 4})
        rep = Run(self.SOURCE, applicators=apps).execute()
        self.assertEqual(rep['status'], 'done', rep)
        self.assertEqual([r['app']['model'] for r in apps.requests], ['small', 'small', 'strong'])
        self.assertEqual([b['name'] for b in rep['bindings']], ['item_count', 'doubled'])
        self.assertEqual(rep['outputs'][0]['text'], '8')
        meta = rep['bindings'][0]['meta']
        self.assertEqual(meta['selected'], 'fake:strong')
        self.assertEqual([a['ok'] for a in meta['route_attempts']], [False, True])
        self.assertEqual([o['constraint_passed'] for o in meta['evidence']['observations']], [False, False, True])

    def test_all_fail_is_visible_and_no_value_is_bound(self):
        rep = Run(self.SOURCE, applicators=Readers({'small': 3, 'strong': 5})).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['kind'], 'check')
        self.assertEqual(rep['bindings'], [])

    def test_missing_contract_refuses_before_any_call(self):
        apps = Readers({'small': 4})
        rep = Run('ask x: Int "x" by "fake:small" with route=escalate.', applicators=apps).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('requires an anchored ensure', rep['error']['message'])
        self.assertEqual(apps.requests, [])

    def test_speculation_never_calls_a_routine(self):
        apps = Readers({'small': 4})
        source = '''routine read_count() -> Int do.
          ask z: Int "z" by "fake:small".
          return z.
        end.
        ask x: Int in 1..4 "x" by "fake:small" with route=escalate.
        ensure x = read_count() else retry.
        '''
        rep = Run(source, applicators=apps).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(apps.requests, [])

    def test_call_budget_bounds_all_repair_and_escalation_attempts(self):
        apps = Readers({'small': 3, 'strong': 4})
        rep = Run(self.SOURCE, applicators=apps, options={'max_calls': 2}).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['kind'], 'budget')
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(rep['calls'], 2)

    def test_derived_values_keep_parent_evidence(self):
        rep = Run(self.SOURCE, applicators=Readers({'small': 4, 'strong': 4})).execute()
        derived = rep['bindings'][1]['meta']['evidence']
        self.assertEqual(derived['assurance'], 'derived_from_inputs')
        self.assertEqual(derived['parents'][0]['name'], 'item_count')
        self.assertEqual(len(derived['parents'][0]['evidence_sha256']), 64)


class Determination(unittest.TestCase):
    def test_multiple_checks_include_later_derived_bindings(self):
        source = '''ask x: Int in 1..5 "x" by "kernel" with solve=true.
        ensure x > 1 else retry.
        let doubled = x * 2.
        ensure doubled = 6 else retry.
        '''
        rep = Run(source).execute()
        self.assertEqual(rep['status'], 'done', rep)
        meta = rep['bindings'][0]['meta']
        self.assertEqual(meta['determination']['accepted'], 1)
        self.assertTrue(meta['determination']['exhaustive'])
        self.assertEqual(meta['evidence']['assurance'], 'unique_in_declared_domain')

    def test_underdetermined_returns_distinct_witnesses(self):
        source = '''ask x: Int in 1..5 "x" by "fake:a".
        ensure x > 2 else retry.
        '''
        rep = Run(source, applicators=Readers({'a': 3})).execute()
        det = rep['bindings'][0]['meta']['determination']
        self.assertEqual(det['verdict'], 'underdetermined')
        self.assertEqual(det['witnesses'], [3, 4])

    def test_budget_exhaustion_cannot_be_reported_as_uniqueness(self):
        source = '''ask x: Int in 1..100 "x" by "kernel" with solve=true.
        ensure x > 0 else retry.
        '''
        rep = Run(source, options={'max_steps': 12}).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('budget', rep['error']['message'])


class Embedding(unittest.TestCase):
    def test_wrong_version_refuses_before_applicator_or_event(self):
        events = []
        readers = Readers({'a': 1})
        rep = EMB.run('ask x:Int "x" by "fake:a".', kernel_id='obsolete', applicators=readers,
                      on_event=events.append)
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['code'], 'SYM_VERSION')
        self.assertEqual(events, [])
        self.assertEqual(readers.requests, [])

    def test_effect_extension_cannot_execute_in_preview_or_replay(self):
        fired = []
        ext = S.Extension('audit_effect', lambda p, line, col, prog: S.Node('audit_effect', line, col),
                          lambda run, stmt, env: fired.append(True), klass='effect')
        S.register_extension(ext)
        self.addCleanup(S.EXTENSIONS.pop, 'audit_effect', None)
        for mode in ('preview', 'replay'):
            rep = Run('audit_effect.', options={mode: True, 'side_effects': True}).execute()
            self.assertEqual(rep['status'], 'failed', rep)
            self.assertEqual(rep['error']['code'], 'SYM_EFFECT')
        self.assertEqual(fired, [])

    def test_certificate_dispatch_filters_failed_cohort_and_requires_live_checks(self):
        source = '''ask x: Int "x" with retries=0.
        ensure x=4 else retry.
        '''
        report = {'source_sha256': C.source_hash(source), 'kernel': S.kernel_id(), 'module_hashes': {},
                  'cohorts': [{'by': 'fake:small', 'passed': 0, 'failed': 1, 'error': None},
                              {'by': 'fake:strong', 'passed': 1, 'failed': 0, 'error': None}],
                  'tests': [{'title': 'sample', 'passed': 1, 'of': 2, 'cohorts': [
                      {'by': 'fake:small', 'status': 'failed', 'calls': 1},
                      {'by': 'fake:strong', 'status': 'passed', 'calls': 1}]}]}
        cert = C.make_certificate(source, report, module_hashes={})
        apps = Readers({'small': 4, 'strong': 4})
        rep = Run(source, applicators=apps, options={'certificate': cert}).execute()
        self.assertEqual(rep['status'], 'done', rep)
        self.assertEqual([r['app']['model'] for r in apps.requests], ['strong'])
        rep = Run(source, applicators=Readers({'strong': 3}), options={'certificate': cert}).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['bindings'], [])
        apps = Readers({'strong': 4})
        rep = Run(source + '\n', applicators=apps, options={'certificate': cert}).execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertEqual(rep['error']['kind'], 'certificate')
        self.assertEqual(apps.requests, [])
        self.assertEqual(rep['bindings'], [])

    def test_regex_work_is_bounded_before_backtracking(self):
        for pattern in ('(a|aa)+$', 'a*a*a*a*a*$', 'a?a?a?a?a?$'):
            rep = Run('show matches("aaaaaaaaaaaaaaa!", "' + pattern + '").').execute()
            self.assertEqual(rep['status'], 'failed')
            self.assertIn('bounded pattern profile', rep['error']['message'])
        rep = Run('show matches("a" * 1000, "a+$").').execute()
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('budget', rep['error']['message'])


if __name__ == '__main__':
    unittest.main()
