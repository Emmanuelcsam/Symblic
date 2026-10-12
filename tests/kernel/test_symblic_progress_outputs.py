"""Opt-in progress frames use temporary records and fake provider callbacks only."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import run as R


class Provider:
    def __init__(self, callback):
        self.callback = callback
        self.calls = 0

    def call(self, request):
        self.calls += 1
        return {'ok': True, 'json': {'answer': self.callback(self.calls, request)}, 'ms': 1}


class ProgressOutputs(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def state(self):
        return json.loads((self.folder / 'state.json').read_text())

    def run_program(self, source, callback, **options):
        apps = Provider(callback)
        run = R.Run(source, applicators=apps, options={
            'by': 'fake:progress', 'determine': False, 'solve': False,
            'progress_outputs': True, **options}, folder=str(self.folder))
        report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        return run, report, apps

    def test_first_and_second_show_are_persisted_before_the_next_provider_dispatch(self):
        source = ('let initial = 2.\nshow initial.\n'
                  'ask frame_one: Int "First frame." from initial with retries=0.\n'
                  'ensure frame_one = initial + 1 else retry.\nshow frame_one.\n'
                  'ask frame_two: Int "Second frame." from frame_one with retries=0.\n'
                  'ensure frame_two = frame_one + 1 else retry.\nshow frame_two.\n')
        observed = []
        def provider(number, _request):
            state = self.state()
            observed.append(state)
            self.assertEqual(state['status'], 'running')
            self.assertEqual([row['value'] for row in state['outputs']], [2] if number == 1 else [2, 3])
            self.assertEqual(state['outputs_progress']['total'], number)
            self.assertEqual(state['outputs_progress']['omitted'], 0)
            self.assertIs(state['outputs_progress']['partial'], True)
            return number + 2
        _run, report, apps = self.run_program(source, provider)
        self.assertEqual(apps.calls, 2)
        self.assertEqual(len(observed), 2)
        self.assertEqual([row['value'] for row in report['outputs']], [2, 3, 4])
        self.assertEqual(self.state()['outputs'], report['outputs'])
        self.assertNotIn('outputs_progress', self.state())
        self.assertNotIn('outputs_progress', report)

    def test_retry_removes_rejected_output_before_its_next_provider_call(self):
        source = ('show 7.\nask candidate: Int "Choose." with retries=1.\n'
                  'show candidate.\nensure candidate = 2 else retry.\n'
                  'ask later: Int "Later." with retries=0.\nshow later.\n')
        saved = []
        original = R.Store.save
        def save(store, name, data, **kwargs):
            if name == 'state.json':
                saved.append(copy.deepcopy(data))
            return original(store, name, data, **kwargs)
        def provider(number, _request):
            values = [row['value'] for row in self.state()['outputs']]
            self.assertEqual(values, [7] if number in (1, 2) else [7, 2])
            return {1: 1, 2: 2, 3: 9}[number]
        with patch.object(R.Store, 'save', save):
            _run, report, apps = self.run_program(source, provider)
        self.assertEqual(apps.calls, 3)
        states = [[row['value'] for row in state.get('outputs', [])] for state in saved]
        rejected = states.index([7, 1])
        self.assertEqual(states[rejected + 1], [7])
        self.assertEqual([row['value'] for row in report['outputs']], [7, 2, 9])

    def test_default_and_non_boolean_truthy_options_keep_existing_progress_shape(self):
        source = 'show 3.\nask value: Int "Continue." with retries=0.\nshow value.\n'
        for option in (None, False, 1, 'true'):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as temporary:
                self.folder = Path(temporary)
                def provider(_number, _request):
                    self.assertNotIn('outputs', self.state())
                    self.assertNotIn('outputs_progress', self.state())
                    return 4
                _run, report, _apps = self.run_program(source, provider, progress_outputs=option)
                self.assertEqual([row['value'] for row in report['outputs']], [3, 4])

    def test_snapshot_count_bound_keeps_recent_suffix_and_final_report_keeps_all(self):
        run = R.Run('', options={'progress_outputs': True}, folder=str(self.folder))
        run.outputs = [{'line': i, 'hash': str(i), 'value': i} for i in range(140)]
        run.status = 'running'
        run._save_state()
        state = self.state()
        self.assertEqual([row['value'] for row in state['outputs']], list(range(12, 140)))
        self.assertEqual(state['outputs_progress']['included'], 128)
        self.assertEqual(state['outputs_progress']['omitted'], 12)
        self.assertEqual(state['outputs_progress']['start_index'], 12)
        run.status = 'done'
        report = run.report()
        run._save_state(report)
        self.assertEqual(len(self.state()['outputs']), 140)
        self.assertNotIn('outputs_progress', self.state())

    def test_byte_bound_counts_unicode_and_does_not_substitute_an_older_frame(self):
        run = R.Run('', options={'progress_outputs': True}, folder=str(self.folder))
        older = {'line': 1, 'hash': 'older', 'value': 'older'}
        large = {'line': 2, 'hash': 'large', 'value': '界' * 400_000}
        latest = {'line': 3, 'hash': 'latest', 'value': ['界'] * 1000}
        run.outputs = [older, large, latest]
        run._save_state()
        state = self.state()
        self.assertEqual(state['outputs'], [latest])
        self.assertEqual(state['outputs_progress']['omitted'], 2)
        self.assertLessEqual(len(json.dumps({'outputs': state['outputs']}, ensure_ascii=False, indent=1).encode()), 1_048_576)
        run.outputs.append({'line': 4, 'hash': 'newest', 'value': 'x' * 1_048_576})
        run._save_state()
        self.assertEqual(self.state()['outputs'], [])
        self.assertEqual(self.state()['outputs_progress']['omitted'], 4)
        report = run.report()
        run._save_state(report)
        self.assertEqual(len(self.state()['outputs']), 4)

    def test_rollback_orders_after_an_inflight_periodic_snapshot(self):
        run = R.Run('', options={'progress_outputs': True}, folder=str(self.folder))
        snap = run._snapshot(run.kernel.env)
        run.outputs.append({'line': 1, 'hash': 'rejected', 'value': 1})
        entered, release = threading.Event(), threading.Event()
        original, errors = run.store.save, []
        def save(name, data, **kwargs):
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise AssertionError('Snapshot gate timed out')
            return original(name, data, **kwargs)
        def invoke(function):
            try:
                function()
            except BaseException as error:  # noqa: BLE001 -- thread failures must reach the test assertion
                errors.append(error)
        with patch.object(run.store, 'save', side_effect=save):
            writer = threading.Thread(target=invoke, args=(run._save_state,))
            writer.start()
            self.assertTrue(entered.wait(5))
            restore = threading.Thread(target=invoke, args=(lambda: run._restore(snap, run.kernel.env),))
            restore.start()
            release.set()
            writer.join(5)
            restore.join(5)
            self.assertFalse(writer.is_alive())
            self.assertFalse(restore.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.state()['outputs'], [])
        run._save_state()
        self.assertEqual(self.state()['outputs_progress']['total'], 0)

    def test_constructor_checkpoint_retains_activity_and_progress_with_fake_worker(self):
        from symblic.constructor import core as C
        from tests.constructor.test_symblic_constructor_run import (
            OPTIONS,
            SOURCE,
            Apps,
            fake_runtime,
            helper,
        )

        with patch.object(C, '_runtime', return_value=fake_runtime()), \
                patch.object(C.L, 'assess_ask', side_effect=helper()):
            run = R.Run('show 5.\n' + SOURCE, applicators=Apps(), options={
                **OPTIONS, 'progress_outputs': True}, folder=str(self.folder))
            report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)
        state = self.state()
        self.assertEqual(state['constructor_bridge'], 2)
        self.assertTrue(state['constructor_activity']['attempt_possible'])
        self.assertEqual([row['value'] for row in state['outputs']], [5, 22])

    def test_output_publication_does_not_change_native_kernel_identity(self):
        identity = copy.deepcopy(S.kernel_id())
        source = 'show 3.\nask value: Int "Continue." with retries=0.\nshow value.\n'
        for enabled in (False, True):
            with self.subTest(progress_outputs=enabled), tempfile.TemporaryDirectory() as temporary:
                self.folder = Path(temporary)
                _run, report, apps = self.run_program(source, lambda *_: 4, progress_outputs=enabled)
                self.assertEqual(apps.calls, 1)
                self.assertEqual([row['value'] for row in report['outputs']], [3, 4])
                self.assertEqual(report['kernel'], identity)
                self.assertEqual(S.kernel_id(), identity)


if __name__ == '__main__':
    unittest.main()
