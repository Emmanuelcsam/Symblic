"""Executed counterexamples from Fable's review, with isolated fake readers.

These test observable contracts, including failed runs, rather than model quality.
No test dispatches a real agent, contacts a provider, or shares a persistent store.
"""

import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel.run import Run


class Readers:
    def __init__(self, answers=None, models=None, uncertain=False):
        self.answers = copy.deepcopy(answers or {})
        self.models = models or {}
        self.requests = []
        self.dispatched = []
        self.uncertain = uncertain
        self.mutex = threading.Lock()

    def call(self, request):
        with self.mutex:
            # Requests include live cancellation callbacks; retain the request
            # without trying to copy their runner and synchronization objects.
            self.requests.append(dict(request))
            key = request['app'].get('model') or request['app']['engine']
            answer = self.answers[key]
            if isinstance(answer, list):
                answer = answer.pop(0) if len(answer) > 1 else answer[0]
            if isinstance(answer, dict) and 'fail' in answer:
                return {'ok': False, 'fatal': True, 'error': answer['fail']}
            body = answer if isinstance(answer, dict) else {'answer': answer}
            return {'ok': True, 'json': copy.deepcopy(body),
                    'model': self.models.get(key, key), 'node': 'fake-node'}

    def delegate(self, target, task, options):
        self.dispatched.append((target, task, copy.deepcopy(options)))
        if self.uncertain:
            raise RuntimeError('dispatch happened but its outcome was lost')
        return {'id': f'fake-agent-{len(self.dispatched)}', 'engine': target, 'status': 'started'}


class Delegates(Readers):
    def __init__(self, replies):
        super().__init__()
        self.replies = list(replies)

    def delegate(self, target, task, options):
        self.dispatched.append((target, task, dict(options)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return dict(reply)


def execute(source, apps=None, folder=None, **options):
    events = []
    run = Run(source, applicators=apps or Readers(), folder=folder,
              options={'on_event': events.append, **options})
    return run.execute(), events


def binding(report, name='x'):
    return next(row for row in report['bindings'] if row['name'] == name)


class Ambiguity(unittest.TestCase):
    SOURCE = '''ask x: Int in 1..9 "How many are there?" by ["fake:a", "fake:b"]
        with route=escalate, ambiguous=fail
        ensure x > 0 else retry.'''
    READINGS: ClassVar[list[str]] = ['count the red ones: 3', 'count all of them: 7']

    def test_fail_cannot_coach_reader_to_withdraw_ambiguity(self):
        apps = Readers({'a': [{'answer': 3, 'readings': self.READINGS}, 3], 'b': 7})
        report, _ = execute(self.SOURCE, apps)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error']['kind'], 'ambiguous')
        self.assertEqual(len(apps.requests), 1)
        self.assertFalse(report['bindings'])

    def test_fail_cannot_escalate_past_reader_with_ambiguity(self):
        apps = Readers({'a': {'answer': 3, 'readings': self.READINGS}, 'b': 7})
        report, _ = execute(self.SOURCE, apps)
        self.assertEqual(report['error']['kind'], 'ambiguous')
        self.assertEqual(len(apps.requests), 1)

    def test_report_retains_readings_of_rejected_candidate(self):
        source = self.SOURCE.replace('ambiguous=fail', 'ambiguous=true, retries=0')
        source = source.replace('x > 0', 'x = 7')
        apps = Readers({'a': {'answer': 3, 'readings': self.READINGS}, 'b': 7})
        report, _ = execute(source, apps)
        self.assertEqual(report['status'], 'done', report)
        ambiguity = binding(report)['meta']['ambiguity']
        self.assertEqual(set(ambiguity['readings']), set(self.READINGS))
        self.assertTrue(report['warnings'])
        observations = binding(report)['meta']['evidence']['observations']
        self.assertEqual(observations[0]['readings'], self.READINGS)
        self.assertFalse(observations[0]['constraint_passed'])


class Provenance(unittest.TestCase):
    def test_loop_lift_retains_evidence_for_each_model_answer(self):
        report, events = execute('for v in [1,2] do\nask a: Int "n {v}" by "fake:a"\nend.',
                                 Readers({'a': [3, 5]}))
        self.assertEqual(report['status'], 'done', report)
        row = binding(report, 'a')
        evidence = row['meta']['evidence']
        self.assertEqual(row['class'], 'structured')
        self.assertNotEqual(evidence['mechanism'], 'kernel_computation')
        self.assertEqual([item['hash'] for item in evidence['items']],
                         [S.fingerprint(3), S.fingerprint(5)])
        asks = [row for row in events if row['kind'] == 'ask']
        self.assertEqual(len(asks), 2)
        self.assertTrue(all(len(item['evidence_sha256']) == 64 for item in evidence['items']))
        self.assertNotEqual(evidence['items'][0]['evidence_sha256'], evidence['items'][1]['evidence_sha256'])

    def test_routine_model_result_is_not_kernel_computation(self):
        source = '''routine guess(q: Text) -> Int do
            ask g: Int "{q}" by "fake:a"
            return g.
            end.
            let z = guess("how many").'''
        report, _ = execute(source, Readers({'a': 5}))
        self.assertEqual(report['status'], 'done', report)
        evidence = binding(report, 'z')['meta']['evidence']
        self.assertEqual(evidence['mechanism'], 'model_derived')
        self.assertEqual(evidence['assurance'], 'unattested')

    def test_delegate_result_is_effect_evidence(self):
        report, _ = execute('delegate job = "work" to "triad".', side_effects=True)
        self.assertEqual(report['status'], 'done', report)
        row = binding(report, 'job')
        self.assertEqual(row['class'], 'effect')
        self.assertEqual(row['meta']['evidence']['mechanism'], 'effect')
        self.assertEqual(row['meta']['evidence']['assurance'], 'unattested')

    def test_rejected_values_never_gain_unique_solution_assurance(self):
        source = 'ask x: Int in 1..5 "pick" by "fake:a"\nensure x=3 else retry.'
        report, events = execute(source, Readers({'a': 4}))
        self.assertEqual(report['status'], 'failed')
        asks = [row for row in events if row['kind'] == 'ask' and 'value' in row]
        self.assertTrue(asks)
        for row in asks:
            self.assertEqual(row['value'], '4')
            self.assertEqual(row['ask']['evidence']['assurance'], 'typed_answer')

    def test_only_actual_unique_solution_gains_assurance_after_retry(self):
        source = 'ask x: Int in 1..5 "pick" by "fake:a"\nensure x=3 else retry.'
        report, events = execute(source, Readers({'a': [4, 3]}))
        self.assertEqual(report['status'], 'done', report)
        rows = [(row['value'], row['ask']['evidence']['assurance']) for row in events
                if row['kind'] == 'ask' and 'value' in row]
        self.assertEqual(rows, [('4', 'typed_answer'), ('3', 'unique_in_declared_domain')])

    def test_native_and_schema_reader_share_statement_dependency(self):
        report, _ = execute('ask x:Int "count" by ["claude:haiku", "ollama:q"].',
                             Readers({'haiku': 2, 'q': 2}))
        self.assertEqual(report['status'], 'done', report)
        evidence = binding(report)['meta']['evidence']
        self.assertTrue(any(row['kind'] == 'statement' for row in evidence['shared_dependencies']))
        self.assertEqual(evidence['independence'], 'not_established')

    def test_different_requested_labels_share_actual_model(self):
        report, _ = execute('ask x:Int "count" by ["fake", "fake:m1"].',
                             Readers({'fake': 2, 'm1': 2}, models={'fake': 'm1', 'm1': 'm1'}))
        self.assertEqual(report['status'], 'done', report)
        deps = binding(report)['meta']['evidence']['shared_dependencies']
        self.assertIn(('model_observed', 'm1'), {(row['kind'], row['id']) for row in deps})

    def test_related_models_share_family_dependency(self):
        report, _ = execute('ask x:Int "count" by ["claude:haiku", "claude:sonnet"].',
                             Readers({'haiku': 2, 'sonnet': 2}))
        self.assertEqual(report['status'], 'done', report)
        deps = binding(report)['meta']['evidence']['shared_dependencies']
        self.assertIn(('family', S.family_of('claude:haiku')),
                      {(row['kind'], row['id']) for row in deps})

    def test_repair_exposure_and_actual_prompt_hashes_are_recorded(self):
        source = '''ask x:Int in 1..9 "pick" by "fake:a" with route=escalate
            ensure x=3 else retry.'''
        report, _ = execute(source, Readers({'a': [4, 5, 3]}))
        self.assertEqual(report['status'], 'done', report)
        evidence = binding(report)['meta']['evidence']
        observations = evidence['observations']
        self.assertEqual([row['attempt'] for row in observations], [1, 2, 3])
        self.assertEqual([row['feedback_exposed'] for row in observations], [False, True, True])
        self.assertEqual([row['oracle_exposed'] for row in observations], [False, True, True])
        self.assertEqual([row['constraint_passed'] for row in observations], [False, False, True])
        self.assertEqual(len({row['request_sha256'] for row in observations}), 3)
        self.assertEqual(len({row['capsule_sha256'] for row in observations}), 3)
        self.assertTrue(any(row['kind'] == 'oracle' and row['observations'] == [1, 2]
                            for row in evidence['shared_dependencies']))


class Agreement(unittest.TestCase):
    def test_one_valid_answer_and_an_unavailable_reader_is_not_measured_agreement(self):
        report, _ = execute('ask x:Int "n" by ["fake:a","fake:b"].',
                            Readers({'a': 3, 'b': {'fail': 'unavailable'}}))
        self.assertEqual(report['status'], 'done', report)
        self.assertIsNone(report['agreement'])
        self.assertEqual(report['agreement_n'], 0)

    def test_null_is_a_valid_any_answer_not_an_abstention(self):
        for effort in ('low', 'ultra'):
            report, _ = execute(f'ask x:Any "an absent value" by ["fake:a", "fake:b"] with effort={effort}.',
                                 Readers({'a': {'answer': None}, 'b': {'answer': None}}))
            self.assertEqual(report['status'], 'done', report)
            self.assertIsNone(binding(report)['value'])
            self.assertEqual(report['agreement'], 1.0)

    def test_single_readers_and_kernel_solutions_are_not_agreement_samples(self):
        sources = [
            'ask x:Int "pick" by "fake:a".',
            'ask x:Int in 1..5 "pick" by "fake:a" with route=escalate\nensure x>0 else retry.',
            'ask x:Int in 1..5 "pick" by "kernel" with solve=true\nensure x=3 else retry.',
        ]
        for source in sources:
            with self.subTest(source=source):
                report, _ = execute(source, Readers({'a': 3}))
                self.assertEqual(report['status'], 'done', report)
                self.assertIsNone(report['agreement'])
                self.assertEqual(report['agreement_n'], 0)

    def test_pair_agreement_remains_measured(self):
        report, _ = execute('ask x:Int "pick" by ["fake:a","fake:b"].', Readers({'a': 3, 'b': 3}))
        self.assertEqual(report['status'], 'done', report)
        self.assertEqual(report['agreement'], 1.0)
        self.assertEqual(report['agreement_n'], 1)

    def test_unit_text_cannot_manufacture_numeric_unanimity(self):
        report, _ = execute('ask d:Number "Distance?" by ["fake:a","fake:b"].',
                             Readers({'a': '26.2 miles', 'b': '26.2 km'}))
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['bindings'])


class Effects(unittest.TestCase):
    SOURCE = '''ask x:Int in 1..9 "pick" by "fake:a"
        delegate job = "build part {x}" to "triad".
        show job.id.'''

    def test_effect_extension_is_refused_in_retry_window_before_dispatch(self):
        fired = []
        def parse(parser, line, col, _program):
            name = parser.expect_name().value
            parser.finish()
            return S.Node('adversarial_effect', line, col, name=name)
        def effect(_run, node, env):
            fired.append(env.lookup(node.name).value)
        old = S.EXTENSIONS.get('adversarial_effect')
        S.register_extension(S.Extension('adversarial_effect', parse, effect, klass='effect'))
        def restore():
            if old is None:
                S.EXTENSIONS.pop('adversarial_effect', None)
            else:
                S.EXTENSIONS['adversarial_effect'] = old
        self.addCleanup(restore)
        source = '''ask x:Int in 1..9 "pick" by "fake:a"
            adversarial_effect x.
            ensure x=3 else retry.'''
        self.assertFalse(S.check(source)['ok'])
        apps = Readers({'a': [4, 5, 3]})
        report, _ = execute(source, apps, side_effects=True)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(fired)
        self.assertFalse(apps.requests)

    def test_resume_reuses_completed_delegate_without_second_side_effect(self):
        apps = Readers({'a': 3})
        with tempfile.TemporaryDirectory(prefix='symblic-adversarial-') as folder:
            first, _ = execute(self.SOURCE, apps, folder, side_effects=True)
            second, _ = execute(self.SOURCE, apps, folder, side_effects=True)
        self.assertEqual(first['status'], 'done', first)
        self.assertEqual(second['status'], 'done', second)
        self.assertEqual(len(apps.dispatched), 1)
        self.assertEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(first['outputs'], second['outputs'])

    def test_uncertain_dispatch_is_not_repeated_on_resume(self):
        apps = Readers({'a': 3}, uncertain=True)
        with tempfile.TemporaryDirectory(prefix='symblic-adversarial-') as folder:
            first, _ = execute(self.SOURCE, apps, folder, side_effects=True)
            second, _ = execute(self.SOURCE, apps, folder, side_effects=True)
        self.assertEqual(first['status'], 'failed')
        self.assertEqual(second['status'], 'failed')
        self.assertEqual(second['error']['kind'], 'uncertain')
        self.assertEqual(len(apps.dispatched), 1)

    def test_callback_failure_after_effect_does_not_lose_durable_outcome(self):
        apps = Readers()
        source = 'delegate job = "work" to "triad".'
        def event(_row):
            raise RuntimeError('event sink disconnected')
        with tempfile.TemporaryDirectory(prefix='symblic-adversarial-') as folder:
            first = Run(source, applicators=apps, folder=folder,
                        options={'side_effects': True, 'on_event': event}).execute()
            second, _ = execute(source, apps, folder, side_effects=True)
        self.assertEqual(first['status'], 'failed')
        self.assertEqual(first['error']['kind'], 'event')
        self.assertEqual(second['status'], 'done', second)
        self.assertEqual(len(apps.dispatched), 1)

    def test_corrupt_delegate_history_fails_closed_without_dispatch(self):
        apps = Readers()
        source = 'delegate job = "work" to "triad".'
        with tempfile.TemporaryDirectory(prefix='symblic-adversarial-') as folder:
            first, _ = execute(source, apps, folder, side_effects=True)
            with (Path(folder) / 'delegate-effects.jsonl').open('a') as stream:
                stream.write('{torn outcome')
            second, _ = execute(source, apps, folder, side_effects=True)
        self.assertEqual(first['status'], 'done', first)
        self.assertEqual(second['status'], 'failed')
        self.assertEqual(second['error']['kind'], 'uncertain')
        self.assertEqual(len(apps.dispatched), 1)

    def test_real_observation_can_reformulate_and_reuse_a_read_inside_retry(self):
        from symblic.kernel import effects as F
        class Host:
            def __init__(self):
                self.calls = []
            def catalogue(self):
                return {'fake.read': {'effect': 'read', 'params': {'type': 'object',
                    'properties': {'n': {'type': 'integer'}}, 'required': ['n']}}}
            def perform(self, effect, stop):
                self.calls.append(effect)
                return {'status': 'done', 'result': list(range(effect['args']['n']))}
        source = '''ask n:Int in 1..9 "How many items?" by "fake:a"
            observe items = fake.read(n=n).
            ensure len(items)>=3 else retry.
            show items.'''
        for answers, expected_reads in (([1, 2, 3], [1, 2, 3]), ([1, 1, 3], [1, 3])):
            with self.subTest(answers=answers), tempfile.TemporaryDirectory() as folder, \
                    patch.object(F, '_CATALOGUE', None):
                host = Host()
                apps = Readers({'a': answers})
                first, _ = execute(source, apps, folder, effects=host)
                second, _ = execute(source, apps, folder, effects=host)
                ledger = [json.loads(row) for row in (Path(folder) / F.LEDGER).read_text().splitlines()]
                self.assertEqual(first['status'], 'done', first)
                self.assertEqual(second['status'], 'done', second)
                self.assertEqual(binding(first, 'items')['class'], 'observed')
                self.assertEqual(binding(first, 'items')['value'], [0, 1, 2])
                self.assertEqual([row['args']['n'] for row in host.calls], expected_reads)
                self.assertEqual(len(apps.requests), 3)
                self.assertEqual(sum(row['phase'] == 'done' for row in ledger), len(expected_reads))
                self.assertEqual(first['fingerprint'], second['fingerprint'])

    def test_real_act_still_cannot_dispatch_inside_retry_window(self):
        from symblic.kernel import effects as F
        class Host:
            def __init__(self):
                self.calls = []
            def catalogue(self):
                return {'fake.write': {'effect': 'write-local', 'policy': 'auto'}}
            def perform(self, effect, stop):
                self.calls.append(effect)
                return {'status': 'done', 'result': True}
        source = '''ask n:Int in 1..9 "How many?" by "fake:a"
            act fake.write(n=n).
            ensure n=3 else retry.'''
        host, apps = Host(), Readers({'a': [1, 3]})
        with patch.object(F, '_CATALOGUE', None):
            report, _ = execute(source, apps, effects=host, side_effects=True)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(host.calls)
        self.assertFalse(apps.requests)

    def test_explicit_predispatch_refusal_can_resume_then_lock_completed_outcome(self):
        from symblic.kernel import lockfile as K
        source = 'delegate job = "work" to "triad".\nshow job.id.'
        apps = Delegates([{'refused': True, 'error': 'capacity full'},
                          {'id': 'fake-agent', 'engine': 'triad', 'status': 'started'}])
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'program.sym').write_text(source)
            first, _ = execute(source, apps, folder, side_effects=True)
            self.assertEqual(first['status'], 'failed')
            self.assertEqual(first['error']['kind'], 'unavailable')
            rows = [json.loads(row) for row in (Path(folder) / 'delegate-effects.jsonl').read_text().splitlines()]
            self.assertEqual([row['phase'] for row in rows], ['intent', 'failed'])
            with self.assertRaises(K.LockError):
                K.make_lock(folder)
            # Replay has no authority to retry even a known refusal.
            replay, _ = execute(source, apps, folder, replay=True)
            self.assertEqual(replay['status'], 'failed')
            self.assertEqual(replay['error']['kind'], 'uncertain')
            self.assertEqual(len(apps.dispatched), 1)
            second, _ = execute(source, apps, folder, side_effects=True)
            third, _ = execute(source, apps, folder, side_effects=True)
            rows = [json.loads(row) for row in (Path(folder) / 'delegate-effects.jsonl').read_text().splitlines()]
            self.assertEqual(second['status'], 'done', second)
            self.assertEqual(third['status'], 'done', third)
            self.assertEqual([row['phase'] for row in rows], ['intent', 'failed', 'intent', 'done'])
            locked = K.replay(K.make_lock(folder))
        self.assertEqual(len(apps.dispatched), 2)
        self.assertEqual(second['fingerprint'], third['fingerprint'])
        self.assertTrue(locked['ok'], locked)

    def test_unconfirmed_or_contradictory_dispatch_cannot_retry_on_resume(self):
        source = 'delegate job = "work" to "triad".'
        replies = [{'error': 'request failed'}, {}, {'status': 'started'},
                   {'refused': 'true', 'error': 'unverified refusal'},
                   {'refused': True, 'id': 'possible-agent'},
                   {'refused': True, 'id': 'possible-agent', 'error': 'conflicting receipt'},
                   RuntimeError('after dispatch'), TimeoutError('lost response')]
        for reply in replies:
            with self.subTest(reply=repr(reply)), tempfile.TemporaryDirectory() as folder:
                apps = Delegates([reply, {'id': 'must-not-dispatch'}])
                first, _ = execute(source, apps, folder, side_effects=True)
                second, _ = execute(source, apps, folder, side_effects=True)
                rows = [json.loads(row) for row in (Path(folder) / 'delegate-effects.jsonl').read_text().splitlines()]
                self.assertEqual(first['status'], 'failed')
                self.assertEqual(first['error']['kind'], 'uncertain')
                self.assertEqual(second['status'], 'failed')
                self.assertEqual(second['error']['kind'], 'uncertain')
                self.assertEqual(len(apps.dispatched), 1)
                self.assertEqual([row['phase'] for row in rows], ['intent'])


class ReceiptsAndFailures(unittest.TestCase):
    def test_receipt_identifies_actual_queried_facts(self):
        receipts = []
        for facts in ('p(1)', 'p(1), p(2), p(99)'):
            report, _ = execute(f'fact {facts}.\nassert count(query(p(X)))>0.')
            self.assertEqual(report['status'], 'done', report)
            receipts.append(report['evidence']['checks'][0])
        fact_rows = [next(row for row in receipt['facts'] if row['pred'] == 'p') for receipt in receipts]
        self.assertEqual([row['count'] for row in fact_rows], [1, 3])
        self.assertNotEqual(fact_rows[0]['sha256'], fact_rows[1]['sha256'])

    def test_receipt_covers_facts_read_through_rules(self):
        report, _ = execute('fact base(1).\nrule p(X) if base(X).\nassert count(query(p(X)))>0.')
        self.assertEqual(report['status'], 'done', report)
        facts = report['evidence']['checks'][0]['facts']
        self.assertTrue(any(row['pred'] == 'base' and row['count'] == 1 for row in facts), facts)

    def test_outage_is_not_reported_as_predicate_rejection(self):
        source = '''ask x:Int in 1..9 "pick" by ["fake:a","fake:b"] with route=escalate
            ensure x=3 else retry.'''
        for answers, expected in [({'a': {'fail': 'unavailable: offline'},
                                   'b': {'fail': 'unavailable: offline'}}, 'unavailable'),
                                  ({'a': 4, 'b': {'fail': 'unavailable: offline'}}, 'check')]:
            with self.subTest(expected=expected):
                report, _ = execute(source, Readers(answers))
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['error']['kind'], expected)

    def test_escalation_rejects_incompatible_voting_options_before_calls(self):
        for option in ('votes=5', 'effort=ultra', 'strict=true', 'agree=0.9', 'vote=fields'):
            with self.subTest(option=option):
                source = f'''ask x:Int in 1..9 "pick" by "fake:a" with route=escalate, {option}
                    ensure x>0 else retry.'''
                apps = Readers({'a': 3})
                report, _ = execute(source, apps)
                self.assertEqual(report['status'], 'failed')
                self.assertFalse(apps.requests)

    def test_exhaustive_contradiction_spends_no_model_calls(self):
        for option in ('', ' with route=escalate'):
            with self.subTest(option=option):
                source = f'ask x:Int in 1..5 "pick" by "fake:a"{option}\nensure x>9 else retry.'
                apps = Readers({'a': 3})
                report, _ = execute(source, apps)
                self.assertEqual(report['status'], 'failed')
                self.assertFalse(apps.requests)

    def test_persisted_event_sequences_are_monotonic_across_resume(self):
        with tempfile.TemporaryDirectory(prefix='symblic-adversarial-') as folder:
            first, events1 = execute('let x=1.\nshow x.', folder=folder)
            second, events2 = execute('let x=1.\nshow x.', folder=folder)
            rows = [json.loads(line) for line in (Path(folder) / 'trace.jsonl').read_text().splitlines()]
        self.assertEqual(first['status'], 'done', first)
        self.assertEqual(second['status'], 'done', second)
        sequences = [row['sequence'] for row in rows]
        self.assertEqual(sequences, sorted(set(sequences)))
        self.assertGreater(events2[0]['sequence'], events1[-1]['sequence'])


if __name__ == '__main__':
    unittest.main()
