"""Discrete Qwen receipts drive task state; providers and sessions are fake."""
import tempfile
import time
import unittest

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host.symblicos_tasks import TaskError, TaskManager
    from tests.integration.test_symblicos_tasks import FakeHub
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None


class DiscreteHub(FakeHub):
    def __init__(self):
        super().__init__()
        self.receipt = {}

    def start(self, options, group=''):
        result = super().start(options, group)
        result['agent']['discrete'] = options.get('discrete', False)
        return result

    def triad_discrete_status(self, agent):
        return self.receipt


class DiscreteTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hub = DiscreteHub()
        self.manager = TaskManager(self.tmp.name, hub=self.hub, background=False, check_host=lambda: None)

    def start(self, **extra):
        body = {'client_request_id': 'discrete-1', 'instruction': 'Create a function and test it.',
                'mode': 'qwen', 'engine': 'triad', 'model': 'qwen3:4b-instruct', 'node': 'node-f',
                'cwd': '/test/workspace'}
        body.update(extra)
        task = self.manager.submit(body)['task']['id']
        self.manager.advance(task)
        return task

    def test_qwen_preset_enforces_discrete_roles(self):
        self.start(discrete=False)
        sent = self.hub.calls[0][0]
        self.assertTrue(sent['discrete'])
        for key in ('mastermind', 'implementer', 'ai_review'):
            self.assertEqual(sent['roles'][key], 'ollama')

    def test_working_receipt_never_becomes_manual_finish_or_success(self):
        task = self.start()
        for status in ('planning', 'building', 'reviewing'):
            self.hub.receipt = {'version': 1, 'status': status, 'round': 1, 'error': ''}
            self.assertTrue(self.manager.advance(task))
            self.assertEqual(self.manager.get(task)['status'], 'active')
        self.assertEqual(self.hub.stops, [])

    def test_unchanged_stage_does_not_rewrite_durable_receipt(self):
        task = self.start()
        self.hub.receipt = {'version': 1, 'status': 'building', 'round': 1, 'error': ''}
        self.manager.advance(task)
        revision = self.manager.get(task)['revision']
        self.manager.advance(task)
        self.assertEqual(self.manager.get(task)['revision'], revision)

    def test_exact_completed_receipt_finishes_and_stops_once(self):
        task = self.start()
        self.hub.receipt = {'version': 1, 'status': 'completed', 'round': 1, 'error': ''}
        self.manager.advance(task)
        self.manager.advance(task)
        self.assertEqual(self.manager.get(task)['status'], 'completed')
        self.assertEqual(self.hub.stops, ['1'])
        self.assertEqual(len(self.hub.calls), 1)

    def test_failed_review_stops_and_does_not_start_the_next_line(self):
        task = self.start(mode='lines', discrete=True, instruction='Build\nContinue')
        self.hub.receipt = {'version': 1, 'status': 'failed', 'round': 3, 'error': 'Review changes remain.'}
        self.assertFalse(self.manager.advance(task))
        self.assertEqual(self.manager.get(task)['status'], 'failed')
        self.assertEqual(self.hub.stops, ['1'])
        self.manager.advance(task)
        self.assertEqual(len(self.hub.calls), 1)

    def test_unknown_receipt_preserves_execution_reservation(self):
        task = self.start()
        self.hub.receipt = {'version': 1, 'status': 'unknown', 'round': 1, 'error': 'Interrupted build.'}
        self.assertFalse(self.manager.advance(task))
        self.assertEqual(self.manager.get(task)['status'], 'unknown')
        self.assertEqual(self.hub.stops, [])

    def test_missing_or_unreachable_receipt_never_finishes(self):
        task = self.start()
        self.assertTrue(self.manager.advance(task))
        self.hub.triad_discrete_status = lambda _: (_ for _ in ()).throw(OSError('unreachable'))
        self.assertTrue(self.manager.advance(task))
        self.assertEqual(self.manager.get(task)['status'], 'active')
        self.assertEqual(self.hub.stops, [])

    def test_discrete_option_must_be_boolean(self):
        with self.assertRaises(TaskError):
            self.start(discrete='yes')

    def test_interactive_approval_refuses_before_launch(self):
        with self.assertRaisesRegex(TaskError, 'requires Auto'):
            self.start(auto=False)
        self.assertEqual(self.hub.calls, [])

    def test_local_worktree_completion_preserves_mapped_subdirectory(self):
        self.hub._git_info = lambda *_: {'worktree': '/test/native-tree', 'cwd': '/test/native-tree/src'}
        task = self.start(node='node-local', worktree=True, fresh_lines=True, instruction='Build\nTest')
        self.hub.receipt = {'version': 1, 'status': 'completed', 'round': 1, 'error': ''}
        self.manager.advance(task)
        self.manager.advance(task)
        self.assertEqual(self.hub.calls[1][0]['cwd'], '/test/native-tree/src')
        self.assertFalse(self.hub.calls[1][0]['worktree'])
        self.assertEqual(self.hub.stops, ['1'])

    def test_local_worktree_missing_identity_blocks_next_instruction(self):
        self.hub._git_info = lambda *_: {}
        task = self.start(node='node-local', worktree=True, fresh_lines=True, instruction='Build\nTest')
        self.hub.receipt = {'version': 1, 'status': 'completed', 'round': 1, 'error': ''}
        self.assertFalse(self.manager.advance(task))
        self.assertEqual(self.manager.get(task)['status'], 'unknown')
        self.assertEqual(self.hub.stops, [])
        self.assertEqual(len(self.hub.calls), 1)

    def test_oversized_discrete_prompt_refuses_before_launch(self):
        with self.assertRaisesRegex(TaskError, '20000'):
            self.start(instruction='x' * 20000)
        self.assertEqual(self.hub.calls, [])

    def test_confirmed_controller_exit_without_receipt_is_failure(self):
        from integration.host.symblicos_tasks import native_completion
        self.hub.is_remote = lambda _: True
        self.hub._remote_state = lambda *_: (True, '', 'bash')
        self.hub._SHELLS = {'bash'}
        agent = {'id': '1', 'engine': 'triad', 'discrete': True, 'created': time.time() - 30}
        self.assertTrue(native_completion(self.hub, agent)['failed'])
        self.hub._remote_state = lambda *_: (False, '', '')
        self.assertFalse(native_completion(self.hub, agent).get('failed'))

    def test_qwen_lines_keep_fresh_team_and_reuse_exact_workspace(self):
        task = self.start(fresh_lines=True, instruction='Build the rules\nTest the rules')
        self.assertIn('Build the rules', self.hub.calls[0][0]['prompt'])
        self.assertNotIn('Test the rules', self.hub.calls[0][0]['prompt'])
        self.hub.receipt = {'version': 1, 'status': 'completed', 'round': 1, 'error': ''}
        self.manager.advance(task)
        self.manager.advance(task)
        self.assertEqual(self.hub.stops, ['1'])
        second = self.hub.calls[1][0]
        self.assertTrue(second['discrete'])
        self.assertEqual(second['workspaceFrom'], '1')
        self.assertIn('Test the rules', second['prompt'])
        self.assertNotIn('Build the rules', second['prompt'])

    def test_lost_launch_adoption_retains_remote_workspace_handoff(self):
        task = self.manager.submit({'client_request_id': 'lost-launch', 'instruction': 'Build\nTest',
                                   'mode': 'qwen', 'model': 'qwen3:4b-instruct', 'node': 'node-f',
                                   'cwd': '/test/workspace', 'fresh_lines': True})['task']['id']
        row = self.manager.get(task)
        row['status'] = row['steps'][0]['status'] = 'dispatching'
        self.manager._write(row)
        self.hub.agents.append({'id': 'adopted', 'engine': 'triad', 'discrete': True,
                                'group': row['steps'][0]['group'], 'node': 'node-f', 'cwd': '/remote/work'})
        self.manager.control(task, 'resume')
        self.hub.receipt = {'version': 1, 'status': 'completed', 'round': 1, 'error': ''}
        self.manager.advance(task)
        self.manager.advance(task)
        self.assertEqual(self.hub.calls[0][0]['workspaceFrom'], 'adopted')
        self.assertEqual(self.hub.stops, ['adopted'])
