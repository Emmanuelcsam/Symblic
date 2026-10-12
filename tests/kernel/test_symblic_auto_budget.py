"""Adversarial automatic-call budget/replay tests. Fake providers, temp stores only.

Two separate Store/Run instances contend through the on-disk reservation lock;
no live worker, model, network, shell or application data is touched.
"""
import copy
import hashlib
import json
import tempfile
import threading
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from symblic.kernel import language as S
from symblic.kernel import lockfile as K
from symblic.kernel.run import Run, Store

SOURCE = 'ask x: Int "n".'
SOURCE_ID = hashlib.sha256(SOURCE.encode()).hexdigest()


def options(**changes):
    route = {'candidates': ['fake:a'], 'max_calls': 8, 'repairs': 1}
    route.update(changes)
    return {'by': 'auto', 'auto_route': route, 'parallel': 1}


class Provider:
    def __init__(self, replies=None):
        self.replies = copy.deepcopy(replies or [7])
        self.requests = []
        self.lock = threading.Lock()

    def call(self, req):
        with self.lock:
            self.requests.append(dict(req))
            answer = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, dict) and 'ok' in answer:
            return answer
        return {'ok': True, 'json': {'answer': answer}, 'model': req['app']['model'], 'node': 'fake-node'}


def direct(run, *, repair=False):
    return run._call({'engine': 'fake', 'model': 'a'}, 'system', 'prompt',
                     {'type': 'object'}, 1000 if repair else 0, 0, 0, 'low', 'none',
                     S.Node('ask', 1, 1, name='x'), repair=repair)


class BudgetAtomicity(unittest.TestCase):
    def test_two_stores_cap_one_dispatches_fake_provider_once(self):
        provider = Provider()
        barrier = threading.Barrier(2)
        with tempfile.TemporaryDirectory() as folder:
            runs = [Run(SOURCE, applicators=provider, options=options(max_calls=1), folder=folder) for _ in range(2)]
            self.assertIsNot(runs[0].store.lock, runs[1].store.lock)

            def contend(run):
                barrier.wait(timeout=5)
                try:
                    return direct(run)
                except S.SymblicError as exc:
                    return exc.as_dict()

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(contend, runs))
            ledger = json.loads(Path(folder, 'model-budget.json').read_text())
        self.assertEqual(1, len(provider.requests))
        self.assertEqual(1, sum(r.get('ok') is True for r in outcomes))
        self.assertEqual(1, sum(r.get('kind') == 'budget' for r in outcomes))
        self.assertEqual({'calls': 1, 'repairs': 0}, ledger['sources'][SOURCE_ID])

    def test_interruption_after_reservation_remains_charged(self):
        interrupted, resumed = Provider([KeyboardInterrupt('fake interruption')]), Provider()
        with tempfile.TemporaryDirectory() as folder:
            first = Run(SOURCE, applicators=interrupted, options=options(max_calls=1), folder=folder)
            with self.assertRaises(KeyboardInterrupt):
                direct(first)
            self.assertFalse(Path(folder, 'calls.jsonl').exists())
            second = Run(SOURCE, applicators=resumed, options=options(max_calls=1), folder=folder)
            with self.assertRaises(S.SymblicError) as caught:
                direct(second)
            usage = json.loads(Path(folder, 'model-budget.json').read_text())['sources'][SOURCE_ID]
        self.assertEqual('budget', caught.exception.kind)
        self.assertEqual(1, usage['calls'])
        self.assertEqual([], resumed.requests)

    def test_repair_cap_is_persistent_across_distinct_stores(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Store(folder).reserve_model_call(SOURCE_ID, 10, 1, repair=True)
            refused = Store(folder).reserve_model_call(SOURCE_ID, 10, 1, repair=True)
            primary = Store(folder).reserve_model_call(SOURCE_ID, 10, 1, repair=False)
        self.assertEqual({'calls': 1, 'repairs': 1}, first)
        self.assertEqual({'refused_repair': True, 'calls': 1, 'repairs': 1}, refused)
        self.assertEqual({'calls': 2, 'repairs': 1}, primary)

    def test_journal_cap_is_per_exact_source(self):
        other = hashlib.sha256((SOURCE + '\nshow x.').encode()).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            Store(folder).reserve_model_call(SOURCE_ID, 1, 0)
            second = Store(folder).reserve_model_call(other, 1, 0)
            with self.assertRaises(S.SymblicError):
                Store(folder).reserve_model_call(SOURCE_ID, 1, 0)
        self.assertEqual({'calls': 1, 'repairs': 0}, second)

    def test_malformed_counter_types_and_negatives_refuse(self):
        for calls, repairs in [(True, 0), (1.0, 0), (-1, 0), (0, True), (0, -1), (0, '0')]:
            with self.subTest(calls=calls, repairs=repairs), tempfile.TemporaryDirectory() as folder:
                Path(folder, 'model-budget.json').write_text(json.dumps({'version': 1, 'sources': {
                    SOURCE_ID: {'calls': calls, 'repairs': repairs}}}))
                with self.assertRaises(S.SymblicError):
                    Store(folder).reserve_model_call(SOURCE_ID, 10, 10)

    def test_boolean_version_is_not_integer_version_one(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'model-budget.json').write_text(json.dumps({'version': True, 'sources': {}}))
            with self.assertRaises(S.SymblicError):
                Store(folder).reserve_model_call(SOURCE_ID, 10, 10)

    def test_repairs_cannot_exceed_total_charged_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'model-budget.json').write_text(json.dumps({'version': 1, 'sources': {
                SOURCE_ID: {'calls': 0, 'repairs': 9}}}))
            with self.assertRaises(S.SymblicError):
                Store(folder).reserve_model_call(SOURCE_ID, 10, 10)

    def test_unreadable_legacy_json_line_refuses_before_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'calls.jsonl').write_text('{"key":"torn"\n')
            provider = Provider()
            report = Run(SOURCE, applicators=provider, options=options(), folder=folder).execute()
        self.assertEqual('failed', report['status'])
        self.assertEqual('budget', report['error']['kind'])
        self.assertIsNone(report['model_budget']['used'])
        self.assertIsNone(report['model_budget']['repairs_used'])
        self.assertEqual([], provider.requests)

    def test_nonobject_and_invalid_utf8_legacy_logs_refuse_dispatch(self):
        for raw in (b'[]\n', b'null\n', b'1\n', b'\xff\n'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                Path(folder, 'calls.jsonl').write_bytes(raw)
                provider = Provider()
                report = Run(SOURCE, applicators=provider, options=options(), folder=folder).execute()
                self.assertEqual('failed', report['status'])
                self.assertEqual('budget', report['error']['kind'])
                self.assertEqual([], provider.requests)

    def test_cached_resume_preserves_real_repair_usage(self):
        first = Provider(['wrong type', 7])
        with tempfile.TemporaryDirectory() as folder:
            initial = Run(SOURCE, applicators=first, options=options(), folder=folder).execute()
            second = Provider()
            resumed = Run(SOURCE, applicators=second, options=options(), folder=folder).execute()
        self.assertEqual('done', initial['status'])
        self.assertEqual({'scope': 'run_source', 'used': 2, 'repairs_used': 1, 'limit': 8}, resumed['model_budget'])
        self.assertEqual(0, resumed['calls'])
        self.assertEqual(2, resumed['cached'])
        self.assertEqual([], second.requests)

    def test_legacy_cached_resume_reports_repair_usage_without_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Run(SOURCE, applicators=Provider(['wrong type', 7]), options=options(), folder=folder).execute()
            self.assertEqual(1, first['model_budget']['repairs_used'])
            Path(folder, 'model-budget.json').unlink()  # An old folder had only calls.jsonl.
            provider = Provider()
            resumed = Run(SOURCE, applicators=provider, options=options(), folder=folder).execute()
        self.assertEqual('done', resumed['status'])
        self.assertEqual(2, resumed['model_budget']['used'])
        self.assertEqual(1, resumed['model_budget']['repairs_used'])
        self.assertEqual([], provider.requests)

    def test_unknown_budget_is_not_reported_as_zero_on_cached_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            Run(SOURCE, applicators=Provider(), options=options(), folder=folder).execute()
            Path(folder, 'model-budget.json').write_text('{')
            provider = Provider()
            resumed = Run(SOURCE, applicators=provider, options=options(), folder=folder).execute()
        self.assertEqual('done', resumed['status'])
        self.assertIsNone(resumed['model_budget']['used'])
        self.assertIsNone(resumed['model_budget']['repairs_used'])
        self.assertEqual([], provider.requests)


class ReplySequences(unittest.TestCase):
    def test_repeated_key_failure_success_and_cache_within_one_invocation_replays(self):
        class Replies:
            def __init__(self):
                self.keys, self.requests = Counter(), []

            def call(self, req):
                self.requests.append(req)
                self.keys[req['key']] += 1
                if req['app']['model'] == 'a' and self.keys[req['key']] == 1:
                    return {'ok': False, 'fatal': True, 'error': 'one transient failure per key'}
                return {'ok': True, 'json': {'answer': 7}, 'model': req['app']['model'], 'node': 'fake'}

        source = 'for i in [1,2,3,4,5] do\n ask x: Int "n".\nend.\nshow x.'
        opts = options(candidates=['fake:a', 'fake:b'], max_calls=20, repairs=0)
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'program.sym').write_text(source)
            Path(folder, 'meta.json').write_text(json.dumps({'options': opts, 'inputs': {}}))
            provider = Replies()
            first = Run(source, applicators=provider, options=opts, folder=folder).execute()
            self.assertEqual('done', first['status'], first)
            locked = K.make_lock(folder)
            sequences = [[r['ok'] for r in c['replies']] for c in locked['calls']]
            self.assertTrue(any(seq[:2] == [False, True] and len(seq) > 2 for seq in sequences), sequences)
            replayed = K.replay(locked)
        self.assertTrue(replayed['ok'], replayed)
        self.assertEqual(0, replayed['calls'])
        self.assertEqual([], replayed['refused'])
        self.assertTrue(replayed['evidence_match'])
        self.assertEqual(first['fingerprint'], replayed['fingerprint'])


if __name__ == '__main__':
    unittest.main()
