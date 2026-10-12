"""The task-runner boundary (symblic/autogen/runner.py): the protocol, the evidence helpers, the
execution fence, KernelOnlyRunner and the documented FakeTaskRunner. Temporary folders only.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from symblic.autogen import runner as R
from symblic.autogen.runner import FakeTaskRunner, KernelOnlyRunner, TaskError, TaskRunner


class Protocol(unittest.TestCase):
    def test_the_fake_and_the_kernel_only_runner_are_complete_task_runners(self):
        for runner in (FakeTaskRunner(), KernelOnlyRunner(nodes=['node-a'])):
            with self.subTest(runner=type(runner).__name__):
                self.assertEqual([], R.missing_members(runner))
                self.assertIsInstance(runner, TaskRunner)
        self.assertEqual(['submit', 'get'], [m for m in R.missing_members(object()) if m in ('submit', 'get')])

    def test_task_ids_are_derived_from_the_request_id(self):
        expected = 'task-' + hashlib.sha256(b'run-1:n0-a0').hexdigest()[:32]
        self.assertEqual(expected, R.deterministic_task_id('run-1:n0-a0'))
        runner = FakeTaskRunner()
        task = runner.submit({'client_request_id': 'run-1:n0-a0', 'instruction': 'x', 'engine': 'claude',
                              'node': 'host', 'cwd': tempfile.gettempdir()})['task']
        self.assertEqual(expected, task['id'])

    def test_the_execution_fence(self):
        here = socket.gethostname().split('.')[0]
        for value, fenced in (('', False), (here, False), (here.upper() + '.example.org', False),
                              ('another-machine', True)):
            with self.subTest(value=value), patch.dict(os.environ, {R.FENCE_ENV: value}):
                if fenced:
                    with self.assertRaises(TaskError) as caught:
                        R.execution_fence()
                    self.assertEqual(503, caught.exception.status)
                else:
                    R.execution_fence()


class Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_the_inventory_walk_is_bounded_and_skips_git(self):
        work = self.root / 'big'
        (work / '.git').mkdir(parents=True)
        (work / '.git' / 'packed').write_text('x')
        for index in range(3):
            (work / f'f{index}.txt').write_text(str(index))
        inventory = R.workspace_inventory(str(work), max_files=2)
        self.assertEqual((True, True, 2), (inventory['available'], inventory['truncated'], inventory['file_count']))
        self.assertNotIn('.git/packed', [entry['path'] for entry in inventory['files']])
        self.assertFalse(R.workspace_inventory(str(self.root / 'missing'))['available'])
        self.assertFalse(R.workspace_inventory('')['available'])

    def test_changes_between_two_inventories(self):
        work = self.root / 'w'
        work.mkdir()
        (work / 'same.txt').write_text('a')
        (work / 'edit.txt').write_text('a')
        (work / 'gone.txt').write_text('a')
        before = R.workspace_inventory(str(work))
        (work / 'edit.txt').write_text('b')
        (work / 'gone.txt').unlink()
        (work / 'new.txt').write_text('c')
        changes = R.inventory_changes(before, R.workspace_inventory(str(work)))
        self.assertEqual({'added': ['new.txt'], 'removed': ['gone.txt'], 'modified': ['edit.txt'], 'files_changed': 3},
                         changes)
        self.assertIsNone(R.inventory_changes(None, before))

    def test_a_claim_is_cross_checked_with_the_disk(self):
        self.assertEqual({'claimed': True, 'tests': 4, 'files': 2}, R.claimed_work('I created 2 files and 4 tests passed.'))
        self.assertEqual({'claimed': False}, R.claimed_work('Nothing to report.'))
        work = self.root / 'w'
        work.mkdir()
        baseline = R.workspace_inventory(str(work))
        idle = R.disk_evidence(baseline, str(work), 'Created 1 file; all tests passed.', clock=lambda: 5.0)
        self.assertIn('no workspace file changed', idle['warning'])
        self.assertEqual((5.0, 0), (idle['captured'], idle['changes']['files_changed']))
        (work / 'app.py').write_text('x = 1\n')
        busy = R.disk_evidence(baseline, str(work), 'Created 1 file; all tests passed.')
        self.assertEqual(('', ['app.py']), (busy['warning'], busy['changes']['added']))
        remote = R.disk_evidence(None, None, 'Created 1 file.')
        self.assertEqual((None, ''), (remote['changes'], remote['warning']))   # unverifiable is not a refutation


class Runners(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = self.tmp.name

    def body(self, request='r-1', **extra):
        return {'client_request_id': request, 'instruction': 'Create the file a.py.', 'engine': 'claude', 'node': 'host',
                'cwd': self.work, 'worktree': True, **extra}

    def test_the_fake_records_duplicates_refusals_and_disk_evidence(self):
        runner = FakeTaskRunner()
        first = runner.submit(self.body())
        self.assertEqual((False, 'active'), (first['duplicate'], first['task']['status']))
        self.assertTrue(runner.submit(self.body())['duplicate'])
        with self.assertRaises(TaskError) as caught:
            runner.submit(self.body(instruction='something else'))
        self.assertEqual(409, caught.exception.status)
        runner.submit_error = TaskError('admission refused: the node is busy')
        with self.assertRaises(TaskError):
            runner.submit(self.body('r-2'))
        self.assertEqual(1, len(runner.submitted))           # a refusal reserves nothing
        Path(self.work, 'a.py').write_text('x = 1\n')
        task = runner.finish(first['task']['id'])
        self.assertEqual(('completed', ['a.py']), (task['status'], task['steps'][0]['evidence']['changes']['added']))
        self.assertEqual({'message': 'applied', 'files': ['a.py']}, runner.promote(task['steps'][0]['agent_id']))
        self.assertEqual('completed', runner.control(task['id'], 'cancel')['task']['status'])   # nothing to stop
        with self.assertRaises(TaskError) as caught:
            runner.get('task-' + '0' * 32)
        self.assertEqual(404, caught.exception.status)

    def test_the_fake_review_gate_and_remote_agents(self):
        runner = FakeTaskRunner(nodes=('host', 'node-a'))
        task = runner.submit(self.body(node='node-a'))['task']
        agent = task['steps'][0]['agent']
        self.assertTrue(runner.is_remote(agent))
        self.assertIsNone(task['steps'][0]['baseline'])      # a remote workspace is never inventoried here
        gated = runner.gate(task['id'], running=True)
        self.assertEqual(('awaiting_review', True, None), (gated['steps'][0]['status'], gated['steps'][0]['running'],
                                                            gated['steps'][0]['evidence']))
        with self.assertRaises(TaskError):
            runner.fetch_remote(agent['id'])
        runner.remote_refs[agent['id']] = {'ref': 'refs/x', 'main_root': self.work, 'base_sha': 'b' * 40}
        self.assertEqual('refs/x', runner.fetch_remote(agent['id'])['ref'])
        runner.gate(task['id'])
        self.assertEqual('completed', runner.control(task['id'], 'next')['task']['status'])

    def test_the_kernel_only_runner_names_nodes_and_launches_nothing(self):
        runner = KernelOnlyRunner(nodes=['node-a', 'node-b'], local_node='host')
        self.assertEqual((('local',), 'host'), (runner.engines, runner.local_node))
        self.assertEqual([{'id': 'node-a', 'online': True}, {'id': 'node-b', 'online': True}], runner.nodes())
        for call in (lambda: runner.submit(self.body()), lambda: runner.promote('a'), lambda: runner.fetch_remote('a')):
            with self.assertRaises(TaskError) as caught:
                call()
            self.assertEqual(501, caught.exception.status)
        with self.assertRaises(TaskError) as caught:
            runner.get('task-x')
        self.assertEqual(404, caught.exception.status)


if __name__ == '__main__':
    unittest.main()
