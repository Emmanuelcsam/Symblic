"""Automatic routing contracts, with fake readers and temporary replay stores.

Type-only acceptance says nothing about semantic correctness. An encoded pure
predicate adds exactly its written checks; no test here measures model quality.
"""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path

from symblic.kernel import language as S
from symblic.kernel import effects as FX
from symblic.lang import abstraction as L
from symblic.kernel import lockfile as K
from symblic.kernel.run import Run


class Readers:
    def __init__(self, answers):
        self.answers = copy.deepcopy(answers)
        self.requests = []
        self.lock = threading.Lock()

    def call(self, req):
        with self.lock:
            self.requests.append(dict(req))
            name = req['app']['model'] or req['app']['engine']
            answer = self.answers[name]
            if isinstance(answer, list):
                answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, dict) and 'ok' in answer:
            return answer
        body = answer if isinstance(answer, dict) else {'answer': answer}
        return {'ok': True, 'json': body, 'model': 'actual-' + name, 'node': 'actual-node', 'ms': 1}


def policy(**kwargs):
    return dict({'candidates': ['fake:a', 'fake:b'], 'max_calls': 8, 'repairs': 0}, **kwargs)


def run(source, readers, route=None, folder=None, **opts):
    return Run(source, applicators=readers, folder=folder,
               options={'by': 'auto', 'auto_route': policy() if route is None else route,
                        'parallel': 1, **opts}).execute()


def binding(report, name='x'):
    return next(b for b in report['bindings'] if b['name'] == name)


class AutomaticChecks(unittest.TestCase):
    def test_local_only_accepts_explicit_local_candidate_without_cloud(self):
        apps = Readers({'small': True, 'a': False})
        report = run('ask x: Bool "Return true".', apps,
                     route=policy(candidates=['ollama:small', 'claude:a'], allow_cloud=False))
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['ollama'], [q['app']['engine'] for q in apps.requests])
        self.assertIsNone(binding(report)['meta']['agreement'])

    def test_type_failure_falls_through_with_no_semantic_claim(self):
        apps = Readers({'a': 'not an integer', 'b': 7})
        report = run('ask x: Int "Give a number".', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['a', 'b'], [q['app']['model'] for q in apps.requests])
        meta = binding(report)['meta']
        self.assertEqual('fake:b', meta['selected'])
        self.assertEqual('declared_type_only', meta['validation_scope'])
        self.assertEqual('not_established', meta['routing']['semantic_correctness'])
        self.assertIsNone(meta['agreement'])

    def test_syntax_invalid_reply_falls_through(self):
        apps = Readers({'a': {'ok': True, 'text': 'not JSON at all'}, 'b': 3})
        report = run('ask x: Int "n".', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(2, len(apps.requests))

    def test_accepted_typed_wrong_meaning_does_not_claim_correctness(self):
        apps = Readers({'a': 9, 'b': 2})
        report = run('ask x: Int "What is 1 plus 1?".', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(S.fingerprint(9), binding(report)['hash'])
        self.assertEqual(1, len(apps.requests))
        self.assertEqual('typed_answer', binding(report)['meta']['evidence']['assurance'])

    def test_pure_encoded_predicate_filters_before_selecting(self):
        apps = Readers({'a': 2, 'b': 7})
        report = run('ask x: Int "n"\nensure x = 7 else retry.', apps)
        self.assertEqual('done', report['status'], report)
        meta = binding(report)['meta']
        self.assertEqual('encoded_predicates', meta['validation_scope'])
        self.assertEqual('fake:b', meta['selected'])
        obs = meta['evidence']['observations']
        self.assertEqual([False, True], [o['constraint_passed'] for o in obs])
        self.assertEqual(['actual-a', 'actual-b'], [o['model'] for o in obs])

    def test_kernel_impossible_contract_makes_no_model_call(self):
        apps = Readers({'a': 1, 'b': 2})
        report = run('ask x: Int in 1..2 "n"\nensure x = 3 else retry.', apps)
        self.assertEqual('failed', report['status'])
        self.assertEqual('contradictory', report['error']['kind'])
        self.assertEqual([], apps.requests)

    def test_ambiguity_fail_never_repairs_or_escalates(self):
        apps = Readers({'a': {'answer': 3, 'readings': ['three red', 'seven all']}, 'b': 7})
        report = run('ask x: Int "n" with ambiguous=fail.', apps, route=policy(repairs=2))
        self.assertEqual('failed', report['status'])
        self.assertEqual('ambiguous', report['error']['kind'])
        self.assertEqual(1, len(apps.requests))

    def test_ambiguity_report_preserves_rejected_readings(self):
        apps = Readers({'a': {'answer': 3, 'readings': ['red', 'all']}, 'b': 7})
        report = run('ask x: Int "n" with ambiguous=report\nensure x = 7 else retry.', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['red', 'all'], binding(report)['meta']['ambiguity']['readings'])

    def test_explicit_by_takes_precedence_over_default_auto(self):
        apps = Readers({'a': 3, 'b': 7})
        report = run('ask x: Int "n" by "fake:b".', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['b'], [q['app']['model'] for q in apps.requests])
        self.assertNotIn('routing', binding(report)['meta'])

    def test_explicit_program_default_takes_precedence(self):
        apps = Readers({'a': 3, 'b': 7})
        report = run('use by="fake:b".\nask x: Int "n".', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['b'], [q['app']['model'] for q in apps.requests])

    def test_explicit_votes_sample_primary_only(self):
        apps = Readers({'a': 3, 'b': 7})
        report = run('ask x: Int "n" with votes=3.', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['a', 'a', 'a'], [q['app']['model'] for q in apps.requests])
        self.assertNotIn('routing', binding(report)['meta'])

    def test_voting_primary_failure_does_not_silently_escalate(self):
        apps = Readers({'a': 'wrong type', 'b': 7})
        report = run('ask x: Int "n" with votes=2, retries=0.', apps)
        self.assertEqual('failed', report['status'])
        self.assertEqual(['a', 'a'], [q['app']['model'] for q in apps.requests])

    def test_unavailable_candidate_falls_through(self):
        apps = Readers({'a': {'ok': False, 'fatal': True, 'error': 'offline'}, 'b': 7})
        report = run('ask x: Int "n".', apps)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['a', 'b'], [q['app']['model'] for q in apps.requests])


class AutomaticBudgets(unittest.TestCase):
    def test_model_call_budget_counts_invalid_replies(self):
        apps = Readers({'a': 'wrong type', 'b': 7})
        report = run('ask x: Int "n".', apps, route=policy(max_calls=1))
        self.assertEqual('failed', report['status'])
        self.assertEqual('budget', report['error']['kind'])
        self.assertEqual(1, len(apps.requests))

    def test_caller_budget_cannot_be_raised_by_route(self):
        apps = Readers({'a': 'wrong type', 'b': 7})
        report = run('ask x: Int "n".', apps, route=policy(max_calls=8), max_calls=1)
        self.assertEqual('budget', report['error']['kind'])
        self.assertEqual(1, len(apps.requests))

    def test_call_budget_shared_across_distinct_statements(self):
        apps = Readers({'a': 3, 'b': 7})
        report = run('ask x: Int "first".\nask y: Int "second".', apps, route=policy(max_calls=1))
        self.assertEqual('failed', report['status'])
        self.assertEqual('budget', report['error']['kind'])
        self.assertEqual(1, len(apps.requests))

    def test_one_repair_total_not_one_per_candidate(self):
        # the route's only correction is kept for its last candidate (2026-10-03), and it is the only one
        apps = Readers({'a': ['wrong', 'wrong again'], 'b': ['wrong too', 'still wrong', 7]})
        report = run('ask x: Int "n" with retries=9.', apps, route=policy(repairs=1))
        self.assertEqual('failed', report['status'])
        self.assertEqual(['a', 'b', 'b'], [q['app']['model'] for q in apps.requests])

    def test_the_last_correction_is_kept_for_the_last_candidate(self):
        # a Tetris ask, 2026-10-03: a 1B model took both corrections and the engine able to answer had one try
        apps = Readers({'a': ['wrong', 'wrong again'], 'b': ['wrong too'], 'c': ['close', 7]})
        report = run('ask x: Int "n" with retries=9.', apps,
                     route=policy(candidates=['fake:a', 'fake:b', 'fake:c'], repairs=2))
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['a', 'a', 'b', 'c', 'c'], [q['app']['model'] for q in apps.requests])
        self.assertEqual('fake:c', binding(report)['meta']['selected'])

    def test_a_launcher_refusal_costs_no_call_and_no_repair_and_is_not_asked_again(self):
        # 2026-10-03: a refused oversized worker-node model was charged as one of a Tetris run's 6 calls
        refused = {'ok': False, 'refused': True, 'error': 'ollama@node-d: unavailable: too big for its MemoryMax'}
        apps = Readers({'big': refused, 'big2': refused, 'a': ['wrong', 7]})
        with tempfile.TemporaryDirectory() as folder:
            report = run('ask x: Int "n" with retries=9.', apps, folder=folder,
                         route=policy(candidates=['fake:big', 'fake:big2', 'fake:a'], max_calls=2, repairs=1))
            ledger = json.loads((Path(folder) / 'model-budget.json').read_text())
            rows = [json.loads(line) for line in (Path(folder) / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['big', 'big2', 'a', 'a'], [q['app']['model'] for q in apps.requests])
        self.assertEqual((report['calls'], report['model_budget']['used'], report['model_budget']['repairs_used']),
                         (2, 2, 1))
        self.assertEqual([{'calls': 2, 'repairs': 1}], list(ledger['sources'].values()))
        self.assertEqual([True, True, None, None], [r['reply'].get('refused') for r in rows])

    def test_a_refused_correction_gives_its_repair_back(self):
        refused = {'ok': False, 'refused': True, 'error': 'ollama@node-a: node fenced: powering off'}
        apps = Readers({'a': ['wrong', refused], 'b': ['wrong too', 'b wrong again'], 'c': ['c wrong', 7]})
        with tempfile.TemporaryDirectory() as folder:
            report = run('ask x: Int "n" with retries=9.', apps, folder=folder,
                         route=policy(candidates=['fake:a', 'fake:b', 'fake:c'], repairs=2, max_calls=5))
        self.assertEqual('done', report['status'], report)
        # a's correction was refused, so that repair went back: b may still correct once (the last correction
        # stays kept for c), and the refused call did not take one of the 5 calls
        self.assertEqual(['a', 'a', 'b', 'b', 'c', 'c'], [q['app']['model'] for q in apps.requests])
        self.assertEqual(('fake:c', 7), (binding(report)['meta']['selected'], binding(report)['value']))
        self.assertEqual((report['calls'], report['model_budget']['repairs_used']), (5, 2))

    def test_a_rebuilt_budget_never_recharges_refusals(self):
        refused = {'ok': False, 'refused': True, 'error': 'ollama@node-d: unavailable: too big for its MemoryMax'}
        with tempfile.TemporaryDirectory() as folder:
            first = run('ask x: Int "n" with retries=9.', Readers({'big': refused, 'a': ['wrong', 'wrong again']}),
                        folder=folder, route=policy(candidates=['fake:big', 'fake:a'], max_calls=3, repairs=1))
            self.assertEqual('failed', first['status'], first)
            ledger = json.loads((Path(folder) / 'model-budget.json').read_text())
            self.assertEqual([{'calls': 2, 'repairs': 1}], list(ledger['sources'].values()))
            # the journal is lost: rebuilt from calls.jsonl, the refused row is not charged again
            (Path(folder) / 'model-budget.json').unlink()
            apps = Readers({'big': refused, 'a': ['still wrong', 7]})
            second = run('ask x: Int "n" with retries=9.', apps, folder=folder,
                         route=policy(candidates=['fake:big', 'fake:a'], max_calls=3, repairs=1))
            # a's recorded answers (first try and correction) are replayed at no charge: nothing more is asked
            self.assertEqual(['big'], [q['app']['model'] for q in apps.requests])
            self.assertEqual('failed', second['status'], second)
            ledger = json.loads((Path(folder) / 'model-budget.json').read_text())
            self.assertEqual([{'calls': 2, 'repairs': 1}], list(ledger['sources'].values()))

    def test_a_started_run_that_fails_is_still_charged(self):
        failed = {'ok': False, 'error': 'agy@node-a: unavailable: agy: malformed function call'}
        apps = Readers({'a': failed, 'b': 7})
        report = run('ask x: Int "n".', apps, route=policy(max_calls=1))
        self.assertEqual('failed', report['status'], report)
        self.assertEqual(['a'], [q['app']['model'] for q in apps.requests])

    def test_repairs_shared_across_statements(self):
        # the first statement spends the route's one correction on its last candidate: the second has none
        apps = Readers({'a': ['wrong', 'second wrong'], 'b': ['wrong too', 7, 'b wrong']})
        report = run('ask x: Int "first".\nask y: Int "second".', apps, route=policy(repairs=1))
        self.assertEqual('failed', report['status'], report)
        self.assertEqual(['a', 'b', 'b', 'a', 'b'], [q['app']['model'] for q in apps.requests])
        self.assertEqual(('fake:b', 7), (binding(report, 'x')['meta']['selected'], binding(report, 'x')['value']))

    def test_repair_receipt_records_feedback_exposure(self):
        apps = Readers({'a': [1, 7], 'b': 7})
        report = run('ask x: Int "n"\nensure x = 7 else retry.', apps, route=policy(candidates=['fake:a'], repairs=1))
        self.assertEqual('done', report['status'], report)
        obs = binding(report)['meta']['evidence']['observations']
        self.assertEqual([False, True], [o['feedback_exposed'] for o in obs])
        self.assertEqual([False, True], [o['oracle_exposed'] for o in obs])


class AutomaticAdmissionAndReplay(unittest.TestCase):
    def test_empty_auto_route_refused_without_dispatch(self):
        apps = Readers({'a': 3})
        report = run('ask x: Int "n".', apps, route=policy(candidates=[]))
        self.assertEqual('failed', report['status'])
        self.assertEqual([], apps.requests)

    def test_kernel_cannot_be_hidden_inside_model_route(self):
        apps = Readers({'kernel': 3})
        report = run('ask x: Int "n".', apps, route=policy(candidates=['kernel']))
        self.assertEqual('failed', report['status'])
        self.assertEqual([], apps.requests)

    def test_council_cannot_hide_nested_calls_behind_one_budget_charge(self):
        apps = Readers({'panel': 3})
        report = run('ask x: Int "n".', apps, route=policy(candidates=['council:panel']))
        self.assertEqual('failed', report['status'])
        self.assertEqual([], apps.requests)

    def test_original_app_identity_is_saved_not_auto_placeholder(self):
        apps = Readers({'a': 'wrong', 'b': 7})
        with tempfile.TemporaryDirectory() as folder:
            report = run('ask x: Int "n".', apps, folder=folder)
            self.assertEqual('done', report['status'], report)
            rows = [json.loads(line) for line in (Path(folder) / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual(['fake:a', 'fake:b'], [r['app'] for r in rows])
        self.assertEqual('actual-b', binding(report)['meta']['evidence']['observations'][0]['model'])

    def test_lock_replays_route_without_provider_and_preserves_evidence(self):
        apps = Readers({'a': 2, 'b': 7})
        source = 'ask x: Int "n"\nensure x = 7 else retry.'
        options = {'by': 'auto', 'auto_route': policy(), 'parallel': 1}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'program.sym').write_text(source)
            (Path(folder) / 'meta.json').write_text(json.dumps({'options': options, 'inputs': {}}))
            report = Run(source, applicators=apps, folder=folder, options=options).execute()
            self.assertEqual('done', report['status'], report)
            locked = K.make_lock(folder)
            replay = K.replay(locked)
        self.assertTrue(replay['ok'], replay)
        self.assertEqual([], replay['refused'])
        self.assertEqual(0, replay['calls'])
        self.assertEqual(report['fingerprint'], replay['fingerprint'])
        self.assertEqual(options['auto_route'], locked['options']['auto_route'])

    def test_lock_replays_unavailable_attempt_before_selected_provider(self):
        apps = Readers({'a': {'ok': False, 'fatal': True, 'error': 'provider offline'}, 'b': 7})
        source = 'ask x: Int "n".'
        options = {'by': 'auto', 'auto_route': policy(max_calls=2), 'parallel': 1}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'program.sym').write_text(source)
            (Path(folder) / 'meta.json').write_text(json.dumps({'options': options, 'inputs': {}}))
            report = Run(source, applicators=apps, folder=folder, options=options).execute()
            self.assertEqual('done', report['status'], report)
            replay = K.replay(K.make_lock(folder))
        self.assertTrue(replay['ok'], replay)
        self.assertEqual([], replay['refused'])
        self.assertEqual(0, replay['calls'])
        self.assertEqual(report['fingerprint'], replay['fingerprint'])

    def test_same_folder_resume_cannot_reset_total_provider_budget(self):
        source = 'ask x: Int "n".'
        first = Readers({'a': 'wrong type', 'b': {'ok': False, 'fatal': True, 'error': 'offline'}})
        resumed = Readers({'a': 99, 'b': 7})
        with tempfile.TemporaryDirectory() as folder:
            report = run(source, first, route=policy(max_calls=2), folder=folder)
            self.assertEqual('failed', report['status'])
            report = run(source, resumed, route=policy(max_calls=2), folder=folder)
        self.assertEqual('failed', report['status'])
        self.assertEqual('budget', report['error']['kind'])
        self.assertEqual(2, len(first.requests) + len(resumed.requests))

    def test_cached_rejected_predicate_remains_rejected_on_resume(self):
        source = 'ask x: Int "n"\nensure x = 7 else retry.'
        first = Readers({'a': 2, 'b': 7})
        resumed = Readers({'a': 7, 'b': 999})
        with tempfile.TemporaryDirectory() as folder:
            report = run(source, first, folder=folder)
            again = run(source, resumed, folder=folder)
        self.assertEqual('done', again['status'], again)
        self.assertEqual([], resumed.requests)
        self.assertEqual(report['fingerprint'], again['fingerprint'])
        self.assertEqual(binding(report)['meta']['evidence'], binding(again)['meta']['evidence'])
        self.assertEqual([False, True], [o['constraint_passed'] for o in binding(again)['meta']['evidence']['observations']])

    def test_concrete_provider_change_does_not_reuse_old_provider_key(self):
        source = 'ask x: Int "n".'
        first = Readers({'a': 2})
        second = Readers({'b': 7})
        with tempfile.TemporaryDirectory() as folder:
            before = run(source, first, route=policy(candidates=['fake:a']), folder=folder)
            after = run(source, second, route=policy(candidates=['fake:b']), folder=folder)
        self.assertEqual('done', after['status'], after)
        self.assertEqual(1, len(second.requests))
        self.assertNotEqual(first.requests[0]['key'], second.requests[0]['key'])
        self.assertNotEqual(before['fingerprint'], after['fingerprint'])
        self.assertEqual('actual-b', binding(after)['meta']['evidence']['observations'][0]['model'])

    def test_observed_model_identity_is_frozen_with_cached_response(self):
        source = 'ask x: Int "n".'
        first = Readers({'a': {'ok': True, 'json': {'answer': 2}, 'model': 'weights-v1', 'node': 'node1'}})
        second = Readers({'a': {'ok': True, 'json': {'answer': 7}, 'model': 'weights-v2', 'node': 'node2'}})
        with tempfile.TemporaryDirectory() as folder:
            report = run(source, first, route=policy(candidates=['fake:a']), folder=folder)
            replayed = run(source, second, route=policy(candidates=['fake:a']), folder=folder)
        self.assertEqual([], second.requests)
        self.assertEqual(report['fingerprint'], replayed['fingerprint'])
        obs = binding(replayed)['meta']['evidence']['observations'][0]
        self.assertEqual(('weights-v1', 'node1'), (obs['model'], obs['node']))

    def test_cached_invalid_format_replays_same_fallback_sequence(self):
        source = 'ask x: Int "n".'
        apps = Readers({'a': {'ok': True, 'text': 'broken JSON'}, 'b': 7})
        options = {'by': 'auto', 'auto_route': policy(), 'parallel': 1}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'program.sym').write_text(source)
            (Path(folder) / 'meta.json').write_text(json.dumps({'options': options, 'inputs': {}}))
            report = Run(source, applicators=apps, folder=folder, options=options).execute()
            replay = K.replay(K.make_lock(folder))
        self.assertTrue(replay['ok'], replay)
        self.assertEqual('fake:b', binding(replay['report'])['meta']['selected'])
        self.assertEqual(report['fingerprint'], replay['fingerprint'])
        self.assertEqual(0, replay['calls'])

    def test_malformed_persisted_auto_budget_refuses_before_provider(self):
        for contents in ('{', '{}', '[]', '{"calls":true}', '{"calls":-1}'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as folder:
                (Path(folder) / 'model-budget.json').write_text(contents)
                apps = Readers({'a': 3, 'b': 7})
                report = run('ask x: Int "n".', apps, folder=folder)
                self.assertEqual('failed', report['status'], report)
                self.assertEqual([], apps.requests)

    def test_legacy_attempt_log_cannot_reset_budget_when_new_ledger_absent(self):
        source = 'ask x: Int "n".'
        first = Readers({'a': 'wrong type', 'b': {'ok': False, 'fatal': True, 'error': 'offline'}})
        second = Readers({'a': 99, 'b': 7})
        with tempfile.TemporaryDirectory() as folder:
            report = run(source, first, route=policy(max_calls=2), folder=folder)
            self.assertEqual('failed', report['status'])
            (Path(folder) / 'model-budget.json').unlink(missing_ok=True)
            report = run(source, second, route=policy(max_calls=2), folder=folder)
        self.assertEqual('failed', report['status'], report)
        self.assertEqual([], second.requests)

    def test_lock_uses_latest_success_after_same_key_was_previously_unavailable(self):
        source = 'ask x: Int "n".'
        options = {'by': 'auto', 'auto_route': policy(candidates=['fake:a'], max_calls=4), 'parallel': 1}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'program.sym').write_text(source)
            (Path(folder) / 'meta.json').write_text(json.dumps({'options': options, 'inputs': {}}))
            first = Readers({'a': {'ok': False, 'fatal': True, 'error': 'offline'}})
            old = Run(source, applicators=first, folder=folder, options=options).execute()
            self.assertEqual('failed', old['status'])
            second = Readers({'a': 7})
            done = Run(source, applicators=second, folder=folder, options=options).execute()
            self.assertEqual('done', done['status'], done)
            self.assertEqual(first.requests[0]['key'], second.requests[0]['key'])
            replay = K.replay(K.make_lock(folder))
        self.assertTrue(replay['ok'], replay)
        self.assertEqual(0, replay['calls'])

    def test_lock_preserves_nonfatal_retry_failure_and_feedback_sequence(self):
        source = 'ask x: Int "n".'
        options = {'by': 'auto', 'auto_route': policy(candidates=['fake:a'], repairs=1), 'parallel': 1}
        apps = Readers({'a': [{'ok': False, 'fatal': False, 'error': 'temporary failure'}, 7]})
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'program.sym').write_text(source)
            (Path(folder) / 'meta.json').write_text(json.dumps({'options': options, 'inputs': {}}))
            done = Run(source, applicators=apps, folder=folder, options=options).execute()
            self.assertEqual('done', done['status'], done)
            replay = K.replay(K.make_lock(folder))
        self.assertTrue(replay['ok'], replay)
        self.assertEqual([], replay['refused'])
        self.assertEqual(binding(done)['meta']['evidence'], binding(replay['report'])['meta']['evidence'])


class ProtectedHost:
    def __init__(self, sensitivity):
        self.sensitivity = sensitivity

    def catalogue(self):
        return [{'name': 'lab.read', 'effect': 'read', 'policy': 'auto', 'sensitivity': self.sensitivity,
                 'params': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]

    def perform(self, effect, stop):
        return {'status': 'done', 'result': 'PRIVATE TEST FIXTURE'}


class AutomaticConfidentiality(unittest.TestCase):
    def setUp(self):
        L.register()
        FX.set_catalogue(None)
        self.addCleanup(FX.set_catalogue, None)
        old_sync = FX.SYNC
        FX.SYNC = False  # These tests check routing, not filesystem durability.
        self.addCleanup(setattr, FX, 'SYNC', old_sync)

    def protected_run(self, source, sensitivity='lab-confidential', **kwargs):
        apps = Readers({'a': 3, 'b': 7})
        with tempfile.TemporaryDirectory() as folder:
            report = run(source, apps, route=policy(candidates=['claude:a', 'ollama:b@node-a']),
                         effects=ProtectedHost(sensitivity), folder=folder, **kwargs)
        return report, apps

    def test_top_level_protected_acquisition_filters_cloud(self):
        for sensitivity in ('lab-confidential', 'confidential', 'mixed'):
            with self.subTest(sensitivity=sensitivity):
                report, apps = self.protected_run('observe secret = lab.read().\nask x: Int "Count {secret}".', sensitivity)
                self.assertEqual('done', report['status'], report)
                self.assertEqual(['ollama'], [q['app']['engine'] for q in apps.requests])

    def test_routine_return_keeps_protected_acquisition_local(self):
        source = '''routine private() -> Text do
          observe inner = lab.read().
          return inner.
        end.
        let secret = private().
        ask x: Int "Count {secret}".'''
        report, apps = self.protected_run(source)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['ollama'], [q['app']['engine'] for q in apps.requests])

    def test_loop_lift_keeps_protected_acquisition_local(self):
        source = '''for i in [1] do
          observe secret = lab.read().
        end.
        ask x: Int "Count {secret}".'''
        report, apps = self.protected_run(source)
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['ollama'], [q['app']['engine'] for q in apps.requests])

    def test_protected_primary_vote_refuses_cloud_without_silent_swap(self):
        report, apps = self.protected_run('observe secret = lab.read().\nask x: Int "Count {secret}" with votes=1.')
        self.assertEqual('failed', report['status'])
        self.assertEqual([], apps.requests)

    def test_cloud_disabled_refuses_cloud_primary_even_for_explicit_votes(self):
        apps = Readers({'a': 3})
        report = run('ask x: Int "n" with votes=1.', apps,
                     route=policy(candidates=['claude:a'], allow_cloud=False))
        self.assertEqual('failed', report['status'])
        self.assertEqual([], apps.requests)

    def test_public_observation_keeps_owner_cloud_fallback_available(self):
        report, apps = self.protected_run('observe data = lab.read().\nask x: Int "Count {data}".', 'public')
        self.assertEqual('done', report['status'], report)
        self.assertEqual(['claude'], [q['app']['engine'] for q in apps.requests])


if __name__ == '__main__':
    unittest.main()
