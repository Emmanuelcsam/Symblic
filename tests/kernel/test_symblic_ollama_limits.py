"""Explicit local-model budgets (the run option `ollama_limits`) through the runtime and the shipped Ollama
applicator. A fake Ollama server on 127.0.0.1 stands in for the model; nothing else is contacted."""
import json
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from symblic.kernel import language as S
from symblic.providers import applicators as A
from symblic.kernel import run as R
from tests.providers.test_symblic_apply import FakeOllama, req

LIMITS = {'num_predict': 2048, 'num_ctx': 8192, 'timeout_seconds': 300,
          'total_timeout_seconds': 900}
APP = {'engine': 'ollama', 'model': 'tiny', 'node': 'local'}
STMT = S.Node('ask', 1, 1, name='result')


class Limits(unittest.TestCase):
    def test_closed_integer_policy(self):
        self.assertEqual(R.validate_ollama_limits(None), {})
        self.assertEqual(R.validate_ollama_limits(LIMITS), LIMITS)
        for bad in (True, [], {'extra': 1}, {'num_predict': True}, {'num_predict': '20'},
                    {'num_predict': 0}, {'num_ctx': 511}, {'timeout_seconds': 29},
                    {'total_timeout_seconds': 14401}, {'num_predict': 3.5}):
            with self.subTest(bad=bad), self.assertRaises(S.SymblicError):
                R.validate_ollama_limits(bad)

    def test_invalid_native_policy_has_no_store_or_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = pathlib.Path(temporary) / 'run'
            run = R.Run('', options={'ollama_limits': {'num_predict': True}}, folder=str(folder))
            self.assertEqual(run.execute()['status'], 'failed')
            self.assertFalse(folder.exists())

    def test_key_retains_default_and_separates_every_explicit_limit(self):
        args = (APP, 's', 'p', None, 0, 0, 7)
        old = R.call_key(*args)
        self.assertEqual(old, R.call_key(*args, ollama_limits={}))
        keys = {old, R.call_key(*args, ollama_limits=LIMITS)}
        for key in LIMITS:
            changed = {**LIMITS, key: LIMITS[key] + 1}
            keys.add(R.call_key(*args, ollama_limits=changed))
        self.assertEqual(len(keys), 6)

    def test_adapter_forwards_limits_without_other_options(self):
        with FakeOllama() as server:
            out = server.apps().call(req('ollama:tiny@local', ollama_limits=LIMITS))
        self.assertTrue(out['ok'], out)
        options = server.bodies[0]['options']
        self.assertEqual(options['num_predict'], 2048)
        self.assertLessEqual(options['num_ctx'], 8192)
        self.assertEqual(set(options), {'temperature', 'seed', 'num_ctx', 'num_predict'})

    def test_cancelled_request_never_dispatches(self):
        request = req('ollama:tiny@local', ollama_limits=LIMITS)
        request['stop'].set()
        with FakeOllama() as server:
            out = server.apps().call(request)
        self.assertFalse(out['ok'])
        self.assertEqual(server.bodies, [])

    def test_expired_total_budget_never_dispatches(self):
        with FakeOllama() as server:
            out = server.apps().call(req('ollama:tiny@local', ollama_limits=LIMITS, deadline=1))
        self.assertTrue(out['fatal'])
        self.assertEqual(server.bodies, [])

    def test_expiring_total_budget_ends_only_its_own_call(self):
        with FakeOllama(delay=5) as server:
            started = time.monotonic()
            out = server.apps().call(req('ollama:tiny@local', ollama_limits=LIMITS, deadline=time.time() + 2))
        self.assertLess(time.monotonic() - started, 4.5)
        self.assertTrue(out['fatal'])
        self.assertIn('timed out', out['error'])
        self.assertEqual(len(server.bodies), 1)

    def _call(self, run, sample=0):
        return run._call(APP, 's', 'p', None, sample, 0, 7, 'low', 'none', STMT)

    def test_durable_deadline_survives_resume_and_allows_cached_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            app = mock.Mock()
            app.call.return_value = {'ok': True, 'json': {'answer': 1}}
            with mock.patch.object(R.time, 'time', return_value=1000), mock.patch.object(R.time, 'monotonic', return_value=50):
                run = R.Run('show 1.', applicators=app, options={'ollama_limits': LIMITS}, folder=folder)
                self._call(run)
            row = json.loads((pathlib.Path(folder) / 'ollama-budget.json').read_text())
            self.assertEqual(row['started'], 1000)
            self.assertEqual(app.call.call_args.args[0]['deadline'], 1900)
            with mock.patch.object(R.time, 'time', return_value=2000):
                resumed = R.Run('show 1.', applicators=app, options={'ollama_limits': LIMITS}, folder=folder)
                self.assertTrue(self._call(resumed)['cached'])
                with self.assertRaisesRegex(S.SymblicError, 'total Ollama time budget'):
                    self._call(resumed, sample=1)
            self.assertEqual(app.call.call_count, 1)

    def test_changed_or_removed_policy_and_corrupt_ledger_fail_before_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            run = R.Run('show 1.', options={'ollama_limits': LIMITS}, folder=folder)
            run._reserve_ollama_time()
            for options in ({}, {'ollama_limits': {**LIMITS, 'num_predict': 2049}}):
                resumed = R.Run('show 1.', options=options, folder=folder)
                self.assertEqual(resumed.execute()['status'], 'failed')
                self.assertIn('limits/source changed', resumed.error['message'])
            (pathlib.Path(folder) / 'ollama-budget.json').write_text('{')
            resumed = R.Run('show 1.', options={'ollama_limits': LIMITS}, folder=folder)
            self.assertEqual(resumed.execute()['status'], 'failed')

    def test_backward_wall_clock_refuses_and_monotonic_clock_bounds_calls(self):
        run = R.Run('', options={'ollama_limits': LIMITS})
        with mock.patch.object(R.time, 'time', return_value=1000), mock.patch.object(R.time, 'monotonic', return_value=50):
            self.assertEqual(run._reserve_ollama_time(), 1900)
        with mock.patch.object(R.time, 'time', return_value=999), self.assertRaisesRegex(S.SymblicError, 'backwards'):
            run._reserve_ollama_time()
        with mock.patch.object(R.time, 'time', return_value=1001), mock.patch.object(R.time, 'monotonic', return_value=1000):
            with self.assertRaisesRegex(S.SymblicError, 'total Ollama time budget'):
                run._reserve_ollama_time()

    def test_minimum_budget_does_not_round_itself_to_zero(self):
        run = R.Run('', options={'ollama_limits': {'total_timeout_seconds': 30}})
        self.assertGreater(run._reserve_ollama_time(), R.time.time())
