"""The autogen coordinator (symblic/autogen/coordinator.py) driven through the documented
FakeTaskRunner: submission, candidates and promotion, feedback regeneration, decomposition,
handoff, claims the disk refutes, remote staging, conflicts, cancellation and crash recovery.

Every store is temporary; the task runner, the check runner and the clock are fakes
(tests/autogen/harness.py). The longer journeys of the original host's agent runner live in
tests/integration/test_symblicos_autogen_hub_lane*.py.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from symblic.autogen import coordinator as AG
from symblic.autogen import policy as POLICY
from symblic.autogen.coordinator import AutogenError
from symblic.autogen.runner import KernelOnlyRunner, TaskError, deterministic_task_id
from tests.autogen.harness import REMOTE, CoordinatorHarness, Crash


class Admission(CoordinatorHarness):
    def test_the_record_is_durable_before_any_launch_and_a_duplicate_returns_it(self):
        lines = [self.statement('app.py')]
        result = self.auto.submit(self.body(lines))
        run_id = result['run']['id']
        self.assertFalse(result['duplicate'])
        self.assertRegex(run_id, r'^autogen-[a-f0-9]{24}$')
        on_disk = json.loads((self.root / 'state' / 'autogen' / (run_id + '.json')).read_text())
        self.assertEqual(('queued', []), (on_disk['status'], on_disk['nodes'][0]['attempts']))
        self.assertEqual({'agents_started': 0, 'agents_max': 24, 'deadline': self.clock() + 6 * 3600}, on_disk['budget'])
        self.assertEqual(['submitted'], self.names(run_id))
        self.assertEqual([], self.tasks.submitted)
        again = self.auto.submit(self.body(lines))
        self.assertEqual((True, run_id), (again['duplicate'], again['run']['id']))
        with self.assertRaises(AutogenError) as caught:
            self.auto.submit(self.body(lines, regenerate=1))
        self.assertEqual(409, caught.exception.status)

    def test_refusals_happen_before_any_record(self):
        plain = Path(self.tmp.name) / 'plain'
        plain.mkdir()
        good = self.statement('app.py')
        cases = [
            ({**self.body([good]), 'cwd': str(plain)}, 'git workspace'),
            ({**self.body([good]), 'cwd': 'relative/folder'}, 'Select the project workspace'),
            (self.body([good], bogus=1), 'Unknown autogen field bogus.'),
            ({**self.body([good]), 'engine': 'gemini'}, 'Choose an engine the task runner offers.'),
            (self.body(['Make it.']), 'Statements refused: line 1: shorter than 20 characters'),
            (self.body([good], final=['curl https://example.org']), 'final contains a command the autogen runner refuses'),
            ({**self.body([good]), 'client_request_id': 'bad id!'}, 'stable client_request_id'),
            ({**self.body([good]), 'engine': 'local', 'model': 'qwen3:4b-instruct'}, 'local attempts take a spec sheet'),
        ]
        for body, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(AutogenError) as caught:
                    self.auto.submit(body)
                self.assertIn(message, str(caught.exception))
        folder = self.root / 'state' / 'autogen'
        self.assertEqual([], list(folder.glob('*.json')) if folder.exists() else [])

    def test_without_a_task_runner_only_spec_sheets_run(self):
        manager = AG.AutogenManager(str(self.root), background=False, check_host=lambda: None)
        self.assertIsInstance(manager.task_runner, KernelOnlyRunner)
        with self.assertRaises(AutogenError) as caught:
            manager.submit(self.body([self.statement('app.py')]))
        self.assertIn('Choose an engine the task runner offers.', str(caught.exception))


class Candidates(CoordinatorHarness):
    def test_the_first_passing_candidate_is_promoted_and_its_rival_cancelled(self):
        lines = [self.statement('app.py'), self.statement('lib.py')]
        run_id = self.submit(lines, candidates=2)
        self.assertTrue(self.auto.advance(run_id))
        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(['run-1:n0-a0', 'run-1:n0-a1'], [a0['request_id'], a1['request_id']])
        for attempt, body in zip((a0, a1), self.tasks.submitted):
            self.assertEqual(deterministic_task_id(attempt['request_id']), attempt['task_id'])
            self.assertEqual(self.loc(lines[0] + '\n\n' + self.suffix(run_id)), body['instruction'])
            self.assertNotIn(self.cwd, body['instruction'])
            self.assertTrue(body['context_note'].startswith(POLICY.CHECKOUT_LOCK))
            self.assertEqual(('agent', True, True, True), (body['mode'], body['worktree'], body['auto'], body['auto_next']))
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(a1)                                  # the second candidate finishes first
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual(('accepted', 'n0-a1'), (node['status'], node['winner']))
        won, lost = node['attempts'][1], node['attempts'][0]
        self.assertEqual(['exists', 'syntax'], [c['kind'] for c in won['verdict']['checks']])
        self.assertEqual(['app.py'], won['verdict']['changed'])
        self.assertEqual(('failed', 'CANCELLED', 'another candidate was accepted first'),
                         (lost['status'], lost['failure'], lost['error']))
        self.assertEqual([(a0['task_id'], 'cancel')], self.tasks.controls)
        self.assertEqual([won['agent_id']], [agent for agent, _ in self.tasks.promoted])
        self.assertEqual({'message': 'applied', 'files': ['app.py']}, won['applied'])
        self.assertIn('promoted', self.names(run_id))
        self.assertTrue(self.auto.advance(run_id))       # the next statement launches
        self.assertEqual(['run-1:n1-a0', 'run-1:n1-a1'], [a['request_id'] for a in self.attempts(run_id, 'n1')])


class Regeneration(CoordinatorHarness):
    def test_feedback_carries_public_check_output_only_then_the_node_fails(self):
        statement = self.statement('app.py')
        run_id = self.submit([statement], candidates=1, regenerate=1, hidden=['test -s hidden-oracle'],
                             strategies=['fresh', 'feedback'])
        self.results['app.py'] = {'rc': 1, 'out': 'SyntaxError: x'}
        self.results['test -s hidden-oracle'] = {'rc': 1, 'out': 'HIDDEN-ORACLE-OUTPUT'}
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.write('app.py', 'def main(:\n')
        self.finish(first)
        self.assertTrue(self.auto.advance(run_id))       # observe the failure and regenerate in one pass
        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(('failed', 'SYNTAX'), (a0['status'], a0['failure']))
        self.assertEqual(('regen', 'feedback'), (a1['kind'], a1['strategy']))
        note = self.tasks.submitted[1]['context_note']
        self.assertIn('- syntax app.py: SyntaxError: x', note)
        self.assertNotIn('HIDDEN-ORACLE-OUTPUT', note)
        self.assertNotIn('test -s hidden-oracle', [r['argv'] for r in self.runs])   # hidden checks run once, at the end
        self.write('app.py', 'def main(:\n    pass\n')
        self.finish(a1)
        self.assertFalse(self.auto.advance(run_id))      # candidates + regenerate spent at depth 0
        run = self.auto.get(run_id)
        self.assertEqual('failed', run['status'])
        self.assertIn('no eligible strategy remains: SYNTAX, SYNTAX', run['error'])
        self.assertEqual(2, len(self.tasks.submitted))


class Claims(CoordinatorHarness):
    def test_a_claim_the_disk_refutes_is_a_claim_mismatch_never_a_pass(self):
        run_id = self.submit([self.statement('app.py')], regenerate=0)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.finish(attempt, 'Done: I created 1 file and all 4 tests passed.')   # and wrote nothing
        self.assertFalse(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'CLAIM_MISMATCH'), (seen['status'], seen['failure']))
        self.assertIn('claim', [c['kind'] for c in seen['verdict']['checks']])
        self.assertEqual([], self.tasks.promoted)


class Decomposition(CoordinatorHarness):
    def parent(self):
        return f'Create the files alpha.py and beta.py in the folder {self.cwd} with one function each.'

    def test_split_children_run_before_the_next_statement_and_the_parent_is_judged_last(self):
        tail = self.statement('gamma.py')
        run_id = self.submit([self.parent(), tail], candidates=1, regenerate=0, depth=1)
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.finish(first)                               # wrote nothing: NO_OUTPUT
        self.assertTrue(self.auto.advance(run_id))
        a0, planner = self.attempts(run_id, 'n0')
        self.assertEqual(('failed', 'NO_OUTPUT'), (a0['status'], a0['failure']))
        self.assertEqual(('planner', 'split'), (planner['kind'], planner['strategy']))
        children = [f'Create the file alpha.py in the folder {self.cwd} with a function named alpha.',
                    f'Create the file beta.py in the folder {self.cwd} with a function named beta.']
        self.write(POLICY.SPLIT_FILE, '\n'.join(children) + '\n')
        self.finish(planner)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual(('split', ['n0.0', 'n0.1']), (node['status'], node['children']))
        self.assertEqual([], self.tasks.promoted)        # a split is not promoted
        for child_id, name in (('n0.0', 'alpha.py'), ('n0.1', 'beta.py')):
            self.assertTrue(self.auto.advance(run_id))   # the child launches before statement n1
            self.assertEqual([], self.attempts(run_id, 'n1'))
            attempt = self.attempts(run_id, child_id)[0]
            self.write(name, 'def f():\n    return 1\n')
            self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
            self.assertEqual('accepted', self.node(run_id, child_id)['status'])
        self.assertTrue(self.auto.advance(run_id))       # the parent passes its own checks; n1 launches
        self.assertEqual(('accepted', 'children'), (self.node(run_id, 'n0')['status'], self.node(run_id, 'n0')['winner']))
        last = self.attempts(run_id, 'n1')[0]
        self.write('gamma.py', 'gamma = 1\n')
        self.finish(last)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])

    def test_a_split_that_drops_a_file_is_refused(self):
        run_id = self.submit([self.parent()], candidates=1, regenerate=0, depth=1)
        self.auto.advance(run_id)
        self.finish(self.attempts(run_id, 'n0')[0])
        self.auto.advance(run_id)
        planner = self.attempts(run_id, 'n0')[1]
        self.write(POLICY.SPLIT_FILE, f'Create the file alpha.py in the folder {self.cwd} with a function named alpha.\n'
                                      f'Create the file notes.md in the folder {self.cwd} describing the alpha function.\n')
        self.finish(planner)
        self.assertFalse(self.auto.advance(run_id))
        planner = self.attempts(run_id, 'n0')[1]
        self.assertIn('the split drops files the statement names: beta.py', planner['error'])
        self.assertTrue(self.node(run_id, 'n0')['split_refused'])
        self.assertEqual('failed', self.auto.get(run_id)['status'])


class Handoff(CoordinatorHarness):
    def test_a_checkpointed_worker_is_continued_by_a_successor_in_its_own_workspace(self):
        statement = self.statement('big.py', 'with ten numbered functions')
        run_id = self.submit([statement], generations=2)
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.write('big.py', 'def f1():\n')
        self.checkpoint(['f1 to f3'], ['f4 to f10'], ['big.py'])
        self.finish(first)
        self.assertTrue(self.auto.advance(run_id))
        seen, successor = self.attempts(run_id, 'n0')
        self.assertEqual('handoff', seen['status'])
        self.assertEqual(('handoff', 1, seen['id']), (successor['kind'], successor['generation'], successor['from']))
        body = self.tasks.submitted[1]
        self.assertEqual((seen['workspace'], False), (body['cwd'], body['worktree']))
        self.assertIn('Done: f1 to f3', body['instruction'])
        self.assertIn('Left: f4 to f10', body['instruction'])

    def test_a_checkpoint_naming_absent_files_is_no_handoff(self):
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        run_id = self.submit([self.statement('big.py', 'with ten numbered functions')], generations=3)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.write('big.py', 'def f1():\n')
        self.checkpoint(['f1'], ['f2'], ['big.py', 'missing.py'])
        self.finish(attempt)
        self.auto.advance(run_id)
        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(('failed', 'SYNTAX'), (a0['status'], a0['failure']))
        self.assertEqual(('regen', 'feedback'), (a1['kind'], a1['strategy']))


class Remote(CoordinatorHarness):
    """An attempt on another node is verified here, in a staging checkout of the fetched ref."""

    def setUp(self):
        super().setUp()
        self.produced, self.diff, self.git_calls = {}, '', []
        self.auto = self.make_auto(git=self.git)

    def git(self, argv, cwd, timeout=120):
        self.git_calls.append(argv[3:])
        if argv[3:5] == ['worktree', 'add']:
            staging = argv[-2]
            os.makedirs(staging)
            for name, text in self.produced.items():
                Path(staging, name).write_text(text)
            return {'rc': 0, 'out': ''}
        if argv[3:5] == ['worktree', 'remove']:
            import shutil
            shutil.rmtree(argv[-1], ignore_errors=True)
            return {'rc': 0, 'out': ''}
        if argv[3] == 'diff':
            return {'rc': 0, 'out': self.diff}
        return {'rc': 0, 'out': ''}

    def start(self, **policy):
        body = {**self.body([self.statement('app.py')], 'remote-1', **policy), 'node': REMOTE}
        run_id = self.auto.submit(body)['run']['id']
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.task(attempt)['steps'][0]['agent_id']
        self.tasks.remote_refs[agent] = {'ref': 'refs/fetched/x', 'main_root': self.cwd, 'base_sha': 'b' * 40}
        return run_id, attempt, agent

    def test_a_remote_change_is_staged_outside_the_project_and_passes(self):
        run_id, attempt, agent = self.start()
        self.produced, self.diff = {'app.py': 'def main():\n    return 1\n'}, 'app.py\0'
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])
        self.assertEqual([agent], self.tasks.fetched)
        staging = self.auto._staging_path(run_id, 'n0-a0')
        self.assertIn(['worktree', 'add', '--detach', '-f', str(staging), 'refs/fetched/x'], self.git_calls)
        self.assertFalse(staging.exists())
        self.assertFalse((self.project / 'app.py').exists())   # the fake runner's promote applies nothing itself

    def test_a_remote_attempt_that_changed_nothing_is_no_output(self):
        run_id, attempt, _ = self.start(regenerate=0)
        self.produced, self.diff = {'app.py': 'def main():\n    return 1\n'}, ''
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'NO_OUTPUT'), (seen['status'], seen['failure']))
        self.assertTrue(seen['verdict']['staging'])


class Promotion(CoordinatorHarness):
    def test_a_promotion_conflict_retries_once_on_the_same_placement_then_fails(self):
        run_id = self.submit([self.statement('app.py')], regenerate=2)
        self.auto.advance(run_id)
        for round_ in range(2):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.write('app.py', f'def main():\n    return {round_}\n')
            self.tasks.promote_error = TaskError('Nothing was applied: 1 file(s) clash with your checkout: app.py')
            self.finish(attempt)
            keep = self.auto.advance(run_id)
            seen = self.attempts(run_id, 'n0')[round_]
            self.assertEqual(('failed', 'CONFLICT'), (seen['status'], seen['failure']))
            if round_ == 0:
                self.assertTrue(keep)
                self.assertTrue(self.auto.advance(run_id))   # the next pass launches the retry
                retry = self.attempts(run_id, 'n0')[1]
                self.assertEqual(('regen', 'conflict_retry'), (retry['kind'], retry['strategy']))
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('failed', run['status'])
        self.assertIn('promotion conflicts with the project folder persist', run['error'])

    def test_a_crash_inside_promotion_is_inspected_not_regenerated(self):
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(attempt)
        with patch.object(self.tasks, 'promote', side_effect=Crash()):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        restarted = self.make_auto()
        self.assertFalse(restarted.advance(run_id))
        run = restarted.get(run_id)
        self.assertEqual('unknown', run['status'])
        self.assertIn('was interrupted after its intent was recorded', run['error'])
        self.assertEqual(1, len(self.tasks.submitted))   # nothing was relaunched


class Cancel(CoordinatorHarness):
    def test_cancel_stops_running_attempts_and_ends_the_run(self):
        run_id = self.submit([self.statement('app.py')], candidates=2)
        self.auto.advance(run_id)
        attempts = self.attempts(run_id, 'n0')
        self.assertTrue(self.auto.control(run_id, 'cancel')['run']['cancel_requested'])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('cancelled', run['status'])
        self.assertEqual([('failed', 'CANCELLED')] * 2, [(a['status'], a['failure']) for a in run['nodes'][0]['attempts']])
        self.assertEqual({(a['task_id'], 'cancel') for a in attempts}, set(self.tasks.controls))
        self.assertEqual('cancelled', self.auto.control(run_id, 'resume')['run']['status'])

    def test_a_refused_cancel_keeps_the_attempt_in_its_slot(self):
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        self.auto.control(run_id, 'cancel')
        self.tasks.control_error = TaskError('the runner is busy')
        self.assertTrue(self.auto.advance(run_id))       # retried on the next pass
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('running', 'the runner is busy'), (attempt['status'], attempt['cancel_failed']))
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('cancelled', self.auto.get(run_id)['status'])


class Recovery(CoordinatorHarness):
    def test_an_unknown_task_makes_the_run_unknown_and_nothing_is_relaunched(self):
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.tasks.fail(attempt['task_id'], 'the launch outcome was not confirmed', status='unknown')
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('unknown', run['status'])
        self.assertIn('Inspect it with your task runner', run['error'])
        self.assertEqual(1, len(self.tasks.submitted))

    def test_a_crash_between_submit_and_record_adopts_the_same_task(self):
        run_id = self.submit([self.statement('app.py')])
        real = self.tasks.submit

        def submitted_then_died(body):
            real(body)
            raise Crash()
        with patch.object(self.tasks, 'submit', side_effect=submitted_then_died):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('queued', ''), (attempt['status'], attempt['task_id']))
        restarted = self.make_auto()
        self.assertTrue(restarted.advance(run_id))
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('running', True), (attempt['status'], attempt['duplicate']))
        self.assertEqual(deterministic_task_id('run-1:n0-a0'), attempt['task_id'])
        self.assertEqual(1, len(self.tasks.submitted))   # the runner's reservation was adopted
        self.assertIn('launch_recovered', self.names(run_id))

    def test_a_transient_read_error_leaves_the_attempt_running(self):
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.tasks.get_errors[attempt['task_id']] = TaskError('receipt is being written', 409)
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual('running', self.attempts(run_id, 'n0')[0]['status'])
        self.tasks.get_errors[attempt['task_id']] = TaskError('Task not found.', 404)
        self.auto.advance(run_id)
        self.assertEqual(('failed', 'UNKNOWN'), (self.attempts(run_id, 'n0')[0]['status'],
                                                  self.attempts(run_id, 'n0')[0]['failure']))


class Budget(CoordinatorHarness):
    def test_a_passed_deadline_cancels_the_running_attempt(self):
        run_id = self.submit([self.statement('app.py')], wall_seconds=300)
        self.auto.advance(run_id)
        self.clock.advance(301)
        self.assertTrue(self.auto.advance(run_id))
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'TIMEOUT'), (attempt['status'], attempt['failure']))
        self.assertEqual('run deadline passed', attempt['error'])
        self.assertFalse(self.auto.advance(run_id))
        self.assertIn('budget or deadline exhausted', self.auto.get(run_id)['error'])


class Final(CoordinatorHarness):
    def test_final_and_hidden_commands_gate_the_run_once_every_statement_is_accepted(self):
        run_id = self.submit([self.statement('app.py')], final=['python3 -c "import app"'], hidden=['test -s app.py'])
        self.results['test -s app.py'] = {'rc': 1, 'out': 'SECRET-ORACLE'}
        self.auto.advance(run_id)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(self.attempts(run_id, 'n0')[0])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('failed', run['status'])
        self.assertIn('hidden acceptance check 1 of 1 failed (HIDDEN_FAILURE)', run['error'])
        self.assertNotIn('SECRET-ORACLE', json.dumps(run))
        self.assertTrue(run['final']['checks'][0]['passed'])


class Processes(unittest.TestCase):
    def test_a_check_timeout_kills_its_process_group(self):
        # item 9: a background child of a timed-out check survived it
        with tempfile.TemporaryDirectory() as folder:
            out = AG._run('sleep 30 & echo $! > pid; wait', folder, timeout=1, shell=True)
            self.assertEqual(124, out['rc'])
            pid = int(Path(folder, 'pid').read_text())
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                    with open(f'/proc/{pid}/stat') as stat:
                        state = stat.read().split()[2]
                except (ProcessLookupError, FileNotFoundError, PermissionError, IndexError):
                    break                                # gone, or reaped between the check and the read
                if state == 'Z':
                    break
                time.sleep(0.02)
            else:
                self.fail('the background child outlived the check')

    def test_checks_stop_at_the_run_deadline(self):
        calls = []
        auto = AG.AutogenManager(tempfile.gettempdir(), background=False, check_host=lambda: None,
                              check_runner=lambda *a, **k: calls.append(a) or {'rc': 0, 'out': ''}, clock=lambda: 1000.0)
        plan = {'checks': [{'kind': 'command', 'command': 'make test', 'public': True}]}
        checks = auto._run_checks(plan, tempfile.gettempdir(), deadline=999.0)
        self.assertEqual([], calls)
        self.assertEqual((False, 'the run deadline passed; this check was not run'), (checks[0]['passed'], checks[0]['output']))


if __name__ == '__main__':
    unittest.main()
