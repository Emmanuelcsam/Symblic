"""Trusted checker deadlines: context isolation and actual native execution.

Only tiny fixed programs, fake providers and temporary stores; no live service.
"""
import concurrent.futures
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from symblic.js import check as JS
from symblic.js import contract as JSC
from symblic.mica import search as M
from symblic.mica import native as N
from tests.mica.test_symblic_mica_execution import FakeApps, request, ROUTE


class VerificationDeadlineTest(unittest.TestCase):
    def test_nested_scopes_use_minimum_and_restore_after_exception(self):
        self.assertIsNone(JS._effective_deadline())
        with JS.verification_deadline_scope(100):
            self.assertEqual(JS._effective_deadline(200), 100)
            self.assertEqual(JS._effective_deadline(50), 50)
            with JS.verification_deadline_scope(None):
                self.assertEqual(JS._effective_deadline(), 100)
            with JS.verification_deadline_scope(300):
                self.assertEqual(JS._effective_deadline(), 100)
            with self.assertRaisesRegex(RuntimeError, 'fixture'):
                with JS.verification_deadline_scope(25):
                    self.assertEqual(JS._effective_deadline(), 25)
                    raise RuntimeError('fixture')
            self.assertEqual(JS._effective_deadline(), 100)
        self.assertIsNone(JS._effective_deadline())

    def test_invalid_deadlines_refused_without_changing_scope(self):
        for value in [True, False, 'later', object(), float('nan'), float('inf'), -float('inf'), 10**1000]:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(JS.JsError):
                    with JS.verification_deadline_scope(value):
                        self.fail('Invalid deadline entered a scope')
                self.assertIsNone(JS._effective_deadline())

    def test_scope_does_not_leak_between_worker_threads_or_reused_threads(self):
        ready = threading.Event()
        release = threading.Event()
        def worker():
            with JS.verification_deadline_scope(50):
                ready.set(); self.assertTrue(release.wait(2))
                return JS._effective_deadline()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with JS.verification_deadline_scope(100):
                task=pool.submit(worker); self.assertTrue(ready.wait(2))
                self.assertEqual(JS._effective_deadline(),100)
                release.set(); self.assertEqual(task.result(),50)
                self.assertIsNone(pool.submit(JS._effective_deadline).result())
        self.assertIsNone(JS._effective_deadline())

    def test_host_helpers_and_run_builtin_respect_stricter_context(self):
        deadline=time.monotonic()+10
        with JS.verification_deadline_scope(deadline):
            with mock.patch.object(JS,'evaluate',wraps=JS.evaluate) as evaluate:
                self.assertTrue(JS.test('function f(){return 1;}', [('f()','1')],deadline=deadline+100)['passed'])
                self.assertEqual(evaluate.call_args.kwargs['deadline'],deadline)
            with mock.patch.object(JSC,'_parse',wraps=JSC._parse) as parse:
                self.assertTrue(JSC.check('function f(){return 1;}',{'version':1,'exports':{'f':'function'}},deadline=deadline+100)['passed'])
                self.assertEqual(parse.call_args.kwargs['deadline'],deadline)
            with mock.patch.object(JS,'evaluate',wraps=JS.evaluate) as evaluate:
                self.assertEqual(JS._js_run(None,None,'function f(){return 1;}','f()'),1)
                self.assertEqual(evaluate.call_args.kwargs['deadline'],deadline)

    def test_expired_scope_stops_host_checker_before_child_launch(self):
        with JS.verification_deadline_scope(time.monotonic()-1):
            with mock.patch.object(JS.subprocess,'Popen',side_effect=AssertionError('deadline launched subprocess')):
                with self.assertRaises(JS.JsError):
                    JS.test('function f(){return 1;}', [('f()','1')])
                result=JSC.check('function f(){return 1;}',{'version':1,'exports':{'f':'function'}})
                self.assertFalse(result['passed'])
                self.assertEqual(result['status'],'budget')

    def test_native_candidate_threads_and_sequential_checks_inherit_original_deadline(self):
        normalized=M.C.normalize_request(request())
        contract=M.direct_plan(normalized)['contracts'][0]
        source=N.unit_source(contract,[],ROUTE,retries=0,context_chars=24000)
        apps=FakeApps()
        stop=M.DeadlineStop(threading.Event(),int(time.time()*1000)+30000)
        with tempfile.TemporaryDirectory(prefix='mica-native-deadline-') as temp:
            with mock.patch.object(JS,'evaluate',wraps=JS.evaluate) as evaluate, mock.patch.object(JSC,'_parse',wraps=JSC._parse) as parse:
                result=N.execute(source,Path(temp)/'run',apps,ROUTE,limit=1,output_binding='candidate',stop=stop)
                self.assertEqual(result['status'],'done',result)
                self.assertEqual(result['calls'],1)
                # Route-search candidate checks run in a worker, then adopted-source checks run sequentially.
                self.assertGreaterEqual(evaluate.call_count,2)
                self.assertGreaterEqual(parse.call_count,2)
                for call in list(evaluate.call_args_list)+list(parse.call_args_list):
                    self.assertIsNotNone(call.kwargs.get('deadline'),call)
                    self.assertLessEqual(call.kwargs['deadline'],stop.monotonic_deadline)
        self.assertIsNone(JS._effective_deadline())


if __name__=='__main__':unittest.main()
