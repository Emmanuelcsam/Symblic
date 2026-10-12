"""HOST-ONLY engine, fake hub: the original host's task engine (integration/host/symblicos_tasks.py)
and its HTTP routes (integration/host/symblicos_engine.py), driven against a fake agent hub.

These modules cannot run without the original host's agent hub; the tests run anyway because the hub
is injected. They pin the engine's rules: durable reservation before any launch, request identity,
review gates, parallel lines, stall advisories, disk cross-checks of agent claims, refusal detection,
no replay of an uncertain launch, cancellation, and re-attachment after a restart. Temporary stores
and fake agents only. Run: DASH_TEST=1 python3 -m unittest discover -s tests/integration -t .
"""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from integration.host.symblicos_tasks import STALL_HINT_SECONDS, HubTaskRunner, TaskError, TaskManager, catalog
from symblic.autogen.runner import missing_members


class FakeHub:
    ENGINES = ('claude', 'triad', 'local', 'gpt', 'gemini', 'council', 'squad')
    LOCAL_NODE = 'node-local'
    MODEL_RX = re.compile(r'^[\w.:/-]{1,80}$')
    _SHELLS = ('bash', 'sh')

    def __init__(self):
        self.calls = []
        self.stops = []
        self.agents = []
        self.error = None
        self.turn = 'agent'       # what the agent pane runs now: 'agent', a shell, or 'gone'
        self.screen_text = ''

    def start(self, options, group=''):
        self.calls.append((options, group))
        if self.error:
            raise self.error
        agent = {'id': str(len(self.calls)), 'group': group, 'engine': options['engine'],
                 'cwd': options.get('cwd') or '/test/workspace', 'node': options.get('node', 'node-local')}
        self.agents.append(agent)
        return {'agent': agent, 'url': '/terminal?session=' + agent['id']}

    def stop(self, agent_id):
        self.stops.append(agent_id)
        return {'ok': True}

    def _load(self):
        return {'agents': self.agents}

    def is_remote(self, agent):
        return (agent or {}).get('node', self.LOCAL_NODE) != self.LOCAL_NODE

    def _current(self, agent_id, agent=None):
        if self.turn == 'gone':
            return 'gone'
        return self.turn

    def _remote_state(self, agent_id, agent, lines=1):
        if self.turn == 'gone':
            return False, '', 'gone'
        return self.turn != 'agent', self.screen_text, self.turn

    def screen(self, agent_id):
        return {'id': agent_id, 'screen': self.screen_text, 'alive': self.turn != 'gone'}

    def history_text(self, agent_id):
        return {'id': agent_id, 'screen': self.screen_text}

    def node_of(self, agent):
        return agent.get('node', 'node-local')

    @staticmethod
    def _home():
        return '/test'

    @staticmethod
    def engines_payload(cached=False):
        assert cached
        return {'specs': {'future-engine': {'title': 'Future engine'}}, 'models': {}, 'machines': {}}

    @staticmethod
    def fleet_nodes(refresh=False):
        return [{'id': 'new-node', 'label': 'Actual node', 'online': True}]


class Tasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.hub = FakeHub()
        self.evidence = {'available': False, 'done': False}
        self.manager = self.make_manager()

    def make_manager(self):
        return TaskManager(self.tmp.name, hub=self.hub, background=False,
                           completion=lambda *_: self.evidence, check_host=lambda: None)

    def start(self, **extra):
        body = {'instruction': 'Create a snake game.', 'engine': 'claude', 'client_request_id': 'stable-1',
                'node': 'node-local', 'cwd': '/test/workspace'}
        body.update(extra)
        return self.manager.submit(body)['task']['id']

    def test_reservation_is_durable_before_any_dispatch(self):
        task_id = self.start()
        self.assertEqual([], self.hub.calls)
        self.assertEqual('queued', self.make_manager().get(task_id)['status'])
        self.manager.advance(task_id)
        self.assertEqual('active', self.manager.get(task_id)['status'])

    def test_duplicate_after_restart_does_not_dispatch(self):
        task_id = self.start()
        self.manager.advance(task_id)
        fresh = self.make_manager()
        result = fresh.submit({'instruction': 'Create a snake game.', 'engine': 'claude', 'client_request_id': 'stable-1',
                                'node': 'node-local', 'cwd': '/test/workspace'})
        self.assertTrue(result['duplicate'])
        self.assertEqual(task_id, result['task']['id'])
        self.assertEqual(1, len(self.hub.calls))

    def test_request_id_binds_all_options(self):
        self.start()
        with self.assertRaisesRegex(TaskError, 'different'):
            self.start(model='different')

    def test_unknown_field_is_refused_before_reservation(self):
        # A nested envelope (options under their own key) must fail fast, not pass
        # silently and surface later as a missing machine or workspace.
        with self.assertRaisesRegex(TaskError, 'Unknown task field'):
            self.manager.submit({'instruction': 'Create a snake game.', 'client_request_id': 'x-1',
                                 'options': {'engine': 'claude', 'node': 'node-local'}})
        with self.assertRaisesRegex(TaskError, 'Unknown task fields options, typo'):
            self.manager.submit({'instruction': 'Create a snake game.', 'client_request_id': 'x-2',
                                 'options': {'engine': 'claude'}, "typo": 'node-local'})
        self.assertEqual([], self.manager.listing())

    def test_concurrent_same_request_has_one_reservation(self):
        out = []
        threads = [threading.Thread(target=lambda: out.append(self.start())) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len(set(out)))
        self.assertEqual(1, len(self.manager.listing()))

    def test_lines_get_new_agents_and_only_current_line(self):
        task_id = self.start(mode='lines', instruction='Create first.txt\n\nCreate second.txt', context_note='Use UTF-8.', worktree=True)
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('awaiting_review', row['status'])
        self.assertNotIn('second.txt', self.hub.calls[0][0]['prompt'])
        self.manager.control(task_id, 'next')
        self.manager.advance(task_id)
        options = self.hub.calls[1][0]
        self.assertNotIn('first.txt', options['prompt'])
        self.assertIn('Use UTF-8.', options['prompt'])
        self.assertFalse(options['worktree'])
        self.assertEqual('/test/workspace', options['cwd'])
        self.assertNotEqual(self.hub.calls[0][1], self.hub.calls[1][1])

    def test_review_gate_holds_the_workspace_until_the_operator_finishes_it(self):
        # The next line of a lines task chains the previous agent's workspace; a
        # step waiting for review still holds that live session. Launching early
        # made the hub refuse ('Finish and stop the previous agent') and burn the
        # step as failed while the previous agent was still working.
        task_id = self.start(mode='lines', instruction='Create first.txt\n\nCreate second.txt')
        self.manager.advance(task_id)                     # launch line 1
        self.manager.advance(task_id)                     # line 1 awaits review
        self.assertEqual('awaiting_review', self.manager.get(task_id)['status'])
        self.manager.advance(task_id)                     # must NOT launch line 2 yet
        self.assertEqual(1, len(self.hub.calls))
        self.manager.control(task_id, 'next')             # the operator's gate releases it
        self.manager.advance(task_id)
        self.assertEqual(2, len(self.hub.calls))
        self.assertEqual('active', self.manager.get(task_id)['status'])
        self.manager.advance(task_id)                    # line 2 reaches its own gate
        self.assertEqual('awaiting_review', self.manager.get(task_id)['status'])

    def test_failed_step_does_not_brick_the_review_gate_for_later_steps(self):
        # A lines task that lost one step to a launch refusal still has later
        # healthy steps; Next must complete the step holding the gate.
        task_id = self.start(mode='lines', instruction='One\nTwo\nThree')
        row = self.manager.get(task_id)
        row['steps'][0].update(status='completed')
        row['steps'][1].update(status='failed', error='refused')
        row['steps'][2].update(status='awaiting_review', agent_id='9',
                                agent={'id': '9', 'engine': 'claude', 'cwd': '/test/workspace'})
        self.manager._write(row)
        result = self.manager.control(task_id, 'next')
        self.assertEqual('completed', result['task']['steps'][2]['status'])
        self.assertEqual('failed', result['task']['steps'][1]['status'])
        self.assertIn('9', self.hub.stops)

    def test_parallel_lines_run_up_to_cap_and_complete_all(self):
        task_id = self.start(mode='lines', parallel=3,
                             instruction='One\nTwo\nThree\nFour\nFive')
        self.manager.advance(task_id)
        self.assertEqual(3, len(self.hub.calls))          # three sessions at once, two queued
        self.evidence = {'available': True, 'done': True, 'kind': 'native_turn'}
        self.manager.advance(task_id)                     # observes the three active lines
        row = self.manager.get(task_id)
        self.assertEqual(3, sum(1 for s in row['steps'] if s['status'] == 'completed'))
        self.manager.advance(task_id)                     # two spare slots launch lines 4 and 5
        self.assertEqual(5, len(self.hub.calls))
        self.manager.advance(task_id)                     # both finish
        self.manager.advance(task_id)                      # nothing left: the task completes
        row = self.manager.get(task_id)
        self.assertEqual('completed', row['status'])
        self.assertEqual(5, sum(1 for s in row['steps'] if s['status'] == 'completed'))
        self.assertEqual(5, len(self.hub.stops))           # every session was closed behind itself

    def test_last_line_completing_completes_the_task_in_the_same_pass(self):
        """The background worker stops the moment a pass reports nothing left to drive, so the
        completion of the final line must be recorded by that same pass (2026-10-10: seven
        lines tasks sat `queued` for hours with every step completed)."""
        task_id = self.start(mode='lines', instruction='Only line')
        self.manager.advance(task_id)                     # launch
        self.evidence = {'available': True, 'done': True, 'kind': 'native_turn'}
        keep = self.manager.advance(task_id)              # the one line finishes
        self.assertFalse(keep)
        row = json.loads(self.manager._path(task_id).read_text())
        self.assertEqual('completed', row['status'])      # on disk, not only through get()
        self.assertEqual(['completed'], [s['status'] for s in row['steps']])

    def test_a_gated_line_with_a_live_agent_and_no_evidence_needs_resume_after_a_restart(self):
        """The operator's review gate with the agent still running (no native completion adapter):
        the coordinator was probing it when the process died, so it reads as stranded (2026-10-11)."""
        task_id = self.start(mode='lines', instruction='Only line')
        self.manager.advance(task_id)                     # launch
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        row['steps'][0].update(status='awaiting_review', running=True, evidence=None,
                               completion={'available': False, 'done': False, 'reason': 'no adapter'})
        row['status'] = 'awaiting_review'
        path.write_text(json.dumps(row))
        seen = self.manager.get(task_id)
        self.assertEqual('awaiting_review', seen['status'])
        self.assertTrue(seen['resume_required'])
        self.assertTrue(self.manager._gated_live(seen))
        row['steps'][0]['evidence'] = {'kind': 'native_turn'}   # with evidence the operator decides; nothing to probe
        path.write_text(json.dumps(row))
        self.assertFalse(self.manager.get(task_id)['resume_required'])

    def test_queued_record_with_every_step_completed_heals_on_read(self):
        """A record left `queued` by an older coordinator is finalized on read: no agent is
        touched and nothing is replayed; the state is derived from the steps alone."""
        task_id = self.start(mode='lines', instruction='One\nTwo')
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        for step in row['steps']:
            step['status'] = 'completed'
        row['status'] = 'queued'
        path.write_text(json.dumps(row))
        seen = self.manager.get(task_id)
        self.assertEqual('completed', seen['status'])
        self.assertFalse(seen['resume_required'])
        self.assertEqual('completed', json.loads(path.read_text())['status'])
        self.assertEqual([], self.hub.calls)
        self.assertEqual([], self.hub.stops)
        listed = self.manager.listing()
        self.assertEqual(['completed'], [t['status'] for t in listed])

    def test_parallel_completion_of_one_line_does_not_touch_its_neighbours(self):
        task_id = self.start(mode='lines', parallel=2, instruction='One\nTwo')
        self.manager.advance(task_id)
        self.assertEqual(2, len(self.hub.calls))
        # One line reports native completion; the other is still working.
        calls = {'n': 0}

        def completion(hub, agent):
            calls['n'] += 1
            return {'available': True, 'done': True, 'kind': 'native_turn'} if calls['n'] == 1 \
                else {'available': True, 'done': False, 'reason': 'still working'}
        self.manager.completion = completion
        keep = self.manager.advance(task_id)
        row = self.manager.get(task_id)
        statuses = [s['status'] for s in row['steps']]
        self.assertEqual(1, statuses.count('completed'))
        self.assertEqual(1, statuses.count('active'))
        self.assertTrue(keep)                              # the task keeps polling the live line

    def test_parallel_is_refused_outside_lines_mode_and_bounds(self):
        for bad in (0, 9, -1, 'three', True, 2.5):
            with self.subTest(parallel=bad):
                with self.assertRaisesRegex(TaskError, 'integer from 1 to 8'):
                    self.start(mode='lines', parallel=bad)
        with self.assertRaisesRegex(TaskError, 'lines-mode option'):
            self.start(mode='agent', parallel=2)
        with self.assertRaisesRegex(TaskError, 'lines-mode option'):
            self.start(mode='qwen', fresh_lines=True, parallel=2)

    def test_parallel_receipt_tampering_stays_clamped(self):
        task_id = self.start(mode='lines', parallel=2, instruction='One\nTwo')
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        row['options']['parallel'] = 99
        path.write_text(json.dumps(row))
        self.assertEqual(8, self.manager._parallel_cap(self.manager.get(task_id)))

    def test_stalled_active_step_gets_advisory_and_stays_active(self):
        # The wedge case is a lane WITH a native completion adapter (agy/claude/codex):
        # the agent runs, the adapter never reports done, and the step sits 'active'.
        self.evidence = {'available': True, 'done': False, 'reason': 'Waiting for native completion evidence.'}
        task_id = self.start()
        self.manager.advance(task_id)      # launch
        # A launch that died before its first turn produces no evidence for a long time.
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        row['steps'][0]['started'] -= STALL_HINT_SECONDS + 10
        path.write_text(json.dumps(row))
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('active', row['status'])
        self.assertTrue(row['steps'][0]['stalled'])
        self.assertIn('fifteen minutes', row['stalled_hint'])
        self.assertEqual('', row['error'])
        self.assertEqual([], self.hub.stops)

    def test_fresh_active_step_gets_no_stall_advisory(self):
        task_id = self.start()
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertNotIn('stalled', row['steps'][0])
        self.assertNotIn('stalled_hint', row)

    def test_stall_advisory_is_idempotent_across_repeated_observes(self):
        self.evidence = {'available': True, 'done': False, 'reason': 'Waiting for native completion evidence.'}
        task_id = self.start()
        self.manager.advance(task_id)
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        row['steps'][0]['started'] -= STALL_HINT_SECONDS + 10
        path.write_text(json.dumps(row))
        self.manager.advance(task_id)
        first = self.manager.get(task_id)
        self.manager.advance(task_id)
        second = self.manager.get(task_id)
        self.assertTrue(second['steps'][0]['stalled'])
        self.assertEqual(first['revision'], second['revision'])  # unchanged outcome stops rewriting

    def test_stall_advisory_clears_when_evidence_lands(self):
        self.evidence = {'available': True, 'done': False, 'reason': 'Waiting for native completion evidence.'}
        work = self.root / 'anim'
        work.mkdir()
        task_id = self.start(cwd=str(work))
        self.manager.advance(task_id)
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        row['steps'][0]['started'] -= STALL_HINT_SECONDS + 10
        path.write_text(json.dumps(row))
        self.manager.advance(task_id)
        self.assertTrue(self.manager.get(task_id)['steps'][0]['stalled'])
        self.hub.turn = 'bash'
        self.hub.screen_text = 'Created animation.py and its 4 tests. All tests passed.'
        (work / 'animation.py').write_text('print("ball")\n')
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertNotIn('stalled', row['steps'][0])
        self.assertNotIn('stalled_hint', row)

    def test_discrete_step_never_gets_the_stall_advisory(self):
        self.evidence = {'available': True, 'done': False, 'reason': 'Waiting for native completion evidence.'}
        task_id = self.start()
        self.manager.advance(task_id)
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        row['steps'][0]['started'] -= STALL_HINT_SECONDS + 10
        row['steps'][0]['agent']['discrete'] = True
        path.write_text(json.dumps(row))
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertNotIn('stalled', row['steps'][0])
        self.assertNotIn('stalled_hint', row)

    def test_idle_is_never_completion(self):
        task_id = self.start()
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.assertEqual('awaiting_review', self.manager.get(task_id)['status'])
        self.assertEqual(1, len(self.hub.calls))

    def test_ended_manual_turn_records_evidence_and_closes_by_review(self):
        work = self.root / 'anim'
        work.mkdir()
        task_id = self.start(cwd=str(work))
        self.manager.advance(task_id)      # launch
        self.manager.advance(task_id)      # the agent is still working; the manual lane is already reviewable
        self.assertIsNone(self.manager.get(task_id)['steps'][0].get('evidence'))
        self.hub.turn = 'bash'
        self.hub.screen_text = 'Created animation.py and its 4 tests. All tests passed.'
        (work / 'animation.py').write_text('print("ball")\n')
        self.assertFalse(self.manager.advance(task_id))
        row = self.manager.get(task_id)
        self.assertEqual('awaiting_review', row['status'])
        evidence = row['steps'][0]['evidence']
        self.assertIn('All tests passed', evidence['tail'])
        self.assertEqual(['animation.py'], [entry['path'] for entry in evidence['inventory']['files']])
        self.assertEqual(hashlib.sha256(b'print("ball")\n').hexdigest(),
                         evidence['inventory']['files'][0]['sha256'])
        self.assertEqual(1, evidence['changes']['files_changed'])
        self.assertTrue(evidence['claims']['claimed'])
        self.assertEqual('', evidence['warning'])
        # Finish works from the recorded evidence; the explicit review gate is unchanged.
        result = self.manager.control(task_id, 'next')
        self.assertEqual('completed', result['task']['steps'][0]['status'])
        self.assertEqual(['1'], self.hub.stops)

    def test_claimed_work_with_unchanged_disk_keeps_visible_warning(self):
        work = self.root / 'empty-work'
        work.mkdir()
        task_id = self.start(cwd=str(work))
        self.manager.advance(task_id)
        self.hub.turn = 'bash'
        self.hub.screen_text = '4 tests passed, edited 2 files.'
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('awaiting_review', row['status'])
        evidence = row['steps'][0]['evidence']
        self.assertEqual(0, evidence['changes']['files_changed'])
        self.assertEqual(4, evidence['claims']['tests'])
        self.assertEqual(2, evidence['claims']['files'])
        self.assertIn('no workspace file changed', evidence['warning'])

    def test_ended_turn_without_native_evidence_becomes_reviewable_with_evidence(self):
        work = self.root / 'native-lane'
        work.mkdir()
        task_id = self.start(cwd=str(work), engine='claude')
        self.manager.advance(task_id)                       # launch
        self.evidence = {'available': True, 'done': False, 'reason': 'Waiting for native completion evidence.'}
        self.manager.advance(task_id)                      # native lane, turn still running
        self.assertEqual('active', self.manager.get(task_id)['status'])
        self.hub.turn = 'bash'
        self.hub.screen_text = 'Done. Edited 1 file.'
        (work / 'game.py').write_text('print(1)\n')
        self.assertFalse(self.manager.advance(task_id))     # the adapter never fired, but the turn ended
        row = self.manager.get(task_id)
        self.assertEqual('awaiting_review', row['status'])
        evidence = row['steps'][0]['evidence']
        self.assertEqual(1, evidence['changes']['files_changed'])
        self.assertEqual('Done. Edited 1 file.', evidence['tail'])

    def test_self_refused_remote_agent_fails_instead_of_idling(self):
        work = self.root / 'refused'
        work.mkdir()
        task_id = self.start(cwd=str(work), engine='local', node='node-test')
        self.manager.advance(task_id)      # launch
        self.manager.advance(task_id)      # manual lane: awaiting_review while it runs
        self.assertEqual('awaiting_review', self.manager.get(task_id)['status'])
        self.hub.turn = 'bash'
        self.hub.screen_text = 'complete messages and tool schemas exceed the admitted input budget'
        self.assertFalse(self.manager.advance(task_id))
        row = self.manager.get(task_id)
        self.assertEqual('failed', row['status'])
        self.assertEqual('failed', row['steps'][0]['status'])
        self.assertIn('refused its own launch', row['steps'][0]['error'])
        self.assertIn('input budget', row['steps'][0]['error'])
        self.assertEqual(['1'], self.hub.stops)

    def test_refusal_wording_with_changed_files_is_not_a_failed_refusal(self):
        work = self.root / 'worked'
        work.mkdir()
        task_id = self.start(cwd=str(work))
        self.manager.advance(task_id)
        self.hub.turn = 'bash'
        self.hub.screen_text = 'Refused to run the extra linter; edited 2 files and all tests passed.'
        (work / 'game.py').write_text('print(1)\n')
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('awaiting_review', row['status'])
        self.assertEqual(1, row['steps'][0]['evidence']['changes']['files_changed'])
        self.assertEqual('', row['steps'][0]['evidence']['warning'])

    def test_inventory_walk_is_bounded_and_skips_git(self):
        from symblic.autogen.runner import workspace_inventory
        work = self.root / 'big'
        (work / '.git').mkdir(parents=True)
        (work / '.git' / 'packed').write_text('x')
        for index in range(3):
            (work / f'f{index}.txt').write_text(str(index))
        inventory = workspace_inventory(str(work), max_files=2)
        self.assertTrue(inventory['available'])
        self.assertTrue(inventory['truncated'])
        self.assertEqual(2, inventory['file_count'])
        self.assertNotIn('.git/packed', [entry['path'] for entry in inventory['files']])

    def test_polling_during_finish_keeps_live_action_owned_and_refuses_second_finish(self):
        task_id = self.start(mode='lines', instruction='First\nSecond')
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        entered, release = threading.Event(), threading.Event()
        result, errors = [], []
        original_stop = self.hub.stop

        def blocked_stop(agent_id):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test stop release timed out')
            return original_stop(agent_id)

        def finish():
            try:
                result.append(self.manager.control(task_id, 'next'))
            except Exception as error:
                errors.append(error)

        self.hub.stop = blocked_stop
        thread = threading.Thread(target=finish)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            # A second manager represents a reconnect or another HTTP process.
            observer = self.make_manager()
            for _ in range(3):
                row = observer.get(task_id)
                self.assertEqual('finishing', row['status'])
                self.assertFalse(row['resume_required'])
            with self.assertRaisesRegex(TaskError, 'still handling'):
                observer.control(task_id, 'next')
            self.assertEqual(1, len(self.hub.calls))
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        self.assertEqual('queued', result[0]['task']['status'])
        self.assertEqual(['1'], self.hub.stops)
        self.manager.advance(task_id)
        self.assertEqual(2, len(self.hub.calls))
        self.assertEqual('active', self.manager.get(task_id)['status'])

    def test_interrupted_finish_is_unknown_once_its_worker_lease_is_gone(self):
        task_id = self.start()
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        row['status'] = row['steps'][0]['status'] = 'finishing'
        self.manager._write(row)
        recovered = self.make_manager().get(task_id)
        self.assertEqual('unknown', recovered['status'])
        self.assertTrue(recovered['resume_required'])
        self.assertEqual([], self.hub.stops)
        self.assertEqual(1, len(self.hub.calls))

    def test_native_evidence_auto_advances_without_claiming_verified_objective(self):
        task_id = self.start(mode='lines', instruction='First\nSecond')
        self.manager.advance(task_id)
        self.evidence = {'available': True, 'done': True, 'kind': 'native_turn'}
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('completed', row['status'])
        self.assertIn('review', row['completion'])
        self.assertEqual(2, len(self.hub.calls))

    def test_launch_exception_after_persisted_spawn_stays_unknown(self):
        # The hub persists its agent row before spawning; a lost response after that
        # point leaves an owned group agent, so the outcome stays unknown and only
        # a unique owned group identity can recover it.
        original = self.hub.start
        def lost(options, group=''):
            original(options, group)
            raise RuntimeError('response lost after spawn')
        self.hub.start = lost
        task_id = self.start()
        self.manager.advance(task_id)
        self.assertEqual('unknown', self.manager.get(task_id)['status'])
        adopted = self.manager.control(task_id, 'resume')['task']
        self.assertEqual('active', adopted['status'])
        self.assertEqual('1', adopted['steps'][0]['agent_id'])
        self.assertEqual(1, len(self.hub.calls))

    def test_launch_refusal_without_any_spawn_is_failed(self):
        self.hub.error = RuntimeError('complete messages and tool schemas exceed the admitted input budget')
        task_id = self.start()
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('failed', row['status'])
        self.assertEqual('failed', row['steps'][0]['status'])
        self.assertIn('input budget', row['steps'][0]['error'])
        self.assertEqual([], self.hub.stops)

    def test_explicit_admission_refusal_is_failed(self):
        class Refused(Exception):
            refused = True
        self.hub.error = Refused('No capacity')
        task_id = self.start()
        self.manager.advance(task_id)
        self.assertEqual('failed', self.manager.get(task_id)['status'])

    def test_lost_launch_response_can_adopt_exact_owned_group(self):
        task_id = self.start()
        row = self.manager.get(task_id)
        row['status'] = row['steps'][0]['status'] = 'dispatching'
        self.manager._write(row)
        self.hub.agents.append({'id': 'recovered', 'engine': 'claude', 'group': row['steps'][0]['group']})
        adopted = self.manager.control(task_id, 'resume')['task']
        self.assertEqual('recovered', adopted['steps'][0]['agent_id'])
        self.assertEqual([], self.hub.calls)

    def test_nonunique_recovery_refuses(self):
        task_id = self.start()
        row = self.manager.get(task_id)
        row['status'] = row['steps'][0]['status'] = 'dispatching'
        self.manager._write(row)
        self.hub.agents.extend([{'id': str(i), 'group': row['steps'][0]['group']} for i in (1, 2)])
        with self.assertRaises(TaskError):
            self.manager.control(task_id, 'resume')

    def test_cancel_before_launch_does_not_start_agent(self):
        task_id = self.start()
        self.manager.control(task_id, 'cancel')
        self.manager.advance(task_id)
        self.assertEqual('cancelled', self.manager.get(task_id)['status'])
        self.assertEqual([], self.hub.calls)

    def test_cancel_stops_only_owned_agent_and_skips_later_lines(self):
        task_id = self.start(mode='lines', instruction='First\nSecond')
        self.manager.advance(task_id)
        self.manager.control(task_id, 'cancel')
        self.manager.advance(task_id)
        self.assertEqual(['1'], self.hub.stops)
        self.assertEqual('cancelled', self.manager.get(task_id)['status'])
        self.assertEqual(1, len(self.hub.calls))

    def test_cancel_during_launch_records_request_before_response(self):
        original = self.hub.start
        def launching(*args, **kwargs):
            self.manager.control(task_id, 'cancel')
            return original(*args, **kwargs)
        self.hub.start = launching
        task_id = self.start()
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.assertEqual(['1'], self.hub.stops)

    def test_qwen_seats_use_existing_triad_launch(self):
        task_id = self.start(mode='qwen', node='node-local', model='qwen3:4b')
        self.manager.advance(task_id)
        options = self.hub.calls[0][0]
        self.assertEqual('triad', options['engine'])
        self.assertEqual('ollama', options['roles']['mastermind'])
        self.assertEqual('ollama', options['roles']['implementer'])
        self.assertEqual('ollama', options['roles']['ai_review'])
        self.assertEqual('qwen3:4b', options['roles']['review_model'])

    def test_qwen_refuses_unselected_machine_or_nonqwen_model(self):
        for options in ({'model': 'qwen3:4b', 'node': ''}, {'node': 'node-local', 'model': 'llama3:8b'}):
            with self.assertRaises(TaskError):
                self.start(mode='qwen', **options)

    def test_council_spec_and_roles_preserved(self):
        spec = {'stages': [{'kind': 'propose'}]}
        task_id = self.start(engine='council', council=spec)
        self.manager.advance(task_id)
        self.assertEqual(spec, self.hub.calls[0][0]['council'])

    def test_remote_lines_reuse_previous_owned_workspace_after_stop(self):
        task_id = self.start(mode='lines', instruction='First\nSecond', node='node-test', cwd='/test/source')
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.manager.control(task_id, 'next')
        self.assertEqual(['1'], self.hub.stops)
        self.manager.advance(task_id)
        options = self.hub.calls[1][0]
        self.assertEqual('1', options['workspaceFrom'])
        self.assertEqual('/test/source', options['cwd'])

    def test_next_stop_failure_prevents_next_launch(self):
        task_id = self.start(mode='lines', instruction='First\nSecond')
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.hub.stop = lambda *_: (_ for _ in ()).throw(RuntimeError('stop unavailable'))
        result = self.manager.control(task_id, 'next')
        self.assertEqual('unknown', result['task']['status'])
        self.manager.advance(task_id)
        self.assertEqual(1, len(self.hub.calls))

    def test_local_triad_worktree_uses_native_workspace_for_next_line(self):
        self.hub._git_info = lambda *_: {'worktree': '/test/native-triad-worktree'}
        task_id = self.start(engine='triad', mode='lines', worktree=True, instruction='First\nSecond')
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.manager.control(task_id, 'next')
        self.manager.advance(task_id)
        self.assertEqual('/test/native-triad-worktree', self.hub.calls[1][0]['cwd'])
        self.assertFalse(self.hub.calls[1][0]['worktree'])

    def test_host_fence_precedes_reservation(self):
        self.manager.check_host = lambda: (_ for _ in ()).throw(TaskError('fenced', 503))
        with self.assertRaisesRegex(TaskError, 'fenced'):
            self.start()
        self.assertFalse(self.manager.root.exists())

    def test_corrupt_receipt_refuses_reexecution(self):
        task_id = self.start()
        self.manager._path(task_id).write_text('{bad')
        with self.assertRaisesRegex(TaskError, 'unreadable'):
            self.start()

    def test_path_traversal_and_empty_input_refused(self):
        for invalid in ('../bad', 'task-a', None):
            with self.assertRaises(TaskError):
                self.manager.get(invalid)
        with self.assertRaises(TaskError):
            self.start(instruction=' ')

    def test_machine_and_option_types_are_checked_before_receipt(self):
        for options in ({'node': ''}, {'model': 3}, {'roles': []}, {'auto': 'false'}):
            with self.assertRaises(TaskError):
                self.start(**options)
        self.assertEqual([], self.manager.listing())

    def test_missing_or_empty_cwd_is_refused_before_receipt(self):
        for extra in ({'cwd': ''}, {'cwd': '   '}):
            with self.assertRaisesRegex(TaskError, 'workspace'):
                self.start(**extra)
        body = {'instruction': 'Create a snake game.', 'engine': 'claude', 'client_request_id': 'no-cwd',
                'node': 'node-local'}
        with self.assertRaisesRegex(TaskError, 'workspace/create'):
            self.manager.submit(body)
        self.assertEqual([], self.manager.listing())
        self.assertEqual([], self.hub.calls)

    def test_combined_instruction_context_budget_is_checked_before_launch(self):
        with self.assertRaisesRegex(TaskError, 'prompt limit'):
            self.start(instruction='a' * 59000, context_note='b' * 2000)
        self.assertEqual([], self.hub.calls)

    def test_catalog_is_live_registry_not_frozen_engine_copy(self):
        result = catalog(self.hub)
        self.assertIn('future-engine', result['specs'])
        self.assertEqual('new-node', result['nodes'][0]['id'])

    def test_catalog_refresh_is_explicit_background_request(self):
        with patch.object(self.hub, 'fleet_nodes', wraps=self.hub.fleet_nodes) as nodes:
            self.assertFalse(catalog(self.hub)['refreshing'])
            nodes.assert_called_once_with(refresh=False)
            self.assertTrue(catalog(self.hub, refresh=True)['refreshing'])
            nodes.assert_called_with(refresh=True)


class API(unittest.TestCase):
    def test_the_operator_gate_precedes_engine_initialization(self):
        from integration.host import symblicos_engine as symblicos_engine
        class Handler:
            def require_owner(self, *_):
                return False
        with patch.object(symblicos_engine, 'get_engine', side_effect=AssertionError('must not initialize')):
            self.assertTrue(symblicos_engine.handle(Handler(), 'GET', '/api/symblicos/tasks', {}))

    def test_http_contract_start_get_and_control_use_same_ledger(self):
        from integration.host import symblicos_engine as symblicos_engine
        with tempfile.TemporaryDirectory() as root:
            from symblic.os.terminal_server import SymblicOSTerminalEngine
            engine = SymblicOSTerminalEngine(root)
            hub = FakeHub()
            manager = TaskManager(root, hub=hub, background=False,
                                  check_host=lambda: None, completion=lambda *_: {'available': False, 'done': False})
            class Handler:
                result = None
                code = None
                query = {}
                def require_owner(self, *_):
                    return True
                def send_json(self, value, status=200):
                    self.result, self.code = value, status
                def get_query_param(self, name):
                    return self.query.get(name)
            handler = Handler()
            with patch.object(symblicos_engine, 'get_engine', return_value=engine), \
                    patch.object(symblicos_engine, 'TaskManager', return_value=manager), \
                    patch.object(symblicos_engine, 'host_check'):
                symblicos_engine.handle(handler, 'POST', '/api/symblicos/tasks/start',
                                       {'instruction': 'Build game', 'client_request_id': 'api', 'engine': 'claude',
                                        'node': 'node-local', 'cwd': '/test/workspace'})
                task_id = handler.result['task']['id']
                self.assertEqual(200, handler.code)
                manager.advance(task_id)
                manager.advance(task_id)
                handler.query = {'id': task_id}
                symblicos_engine.handle(handler, 'GET', '/api/symblicos/tasks/get?id=' + task_id, {})
                self.assertEqual('awaiting_review', handler.result['task']['status'])
                symblicos_engine.handle(handler, 'POST', '/api/symblicos/tasks/control', {'id': task_id, 'action': 'cancel'})
                manager.advance(task_id)
                self.assertEqual('cancelled', manager.get(task_id)['status'])


class RemoteObservation(unittest.TestCase):
    """A gated line (no completion adapter) whose agent still runs keeps being observed, so a
    node line that later ends its turn or refuses its launch is seen; a coordinator lost to a
    restart is re-attached on the next listing (2026-10-10)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.hub = FakeHub()
        self.evidence = {'available': False, 'done': False}
        self.manager = TaskManager(self.tmp.name, hub=self.hub, background=False,
                                   completion=lambda *_: self.evidence, check_host=lambda: None)

    def start(self, **extra):
        body = {'instruction': 'Create a snake game.', 'engine': 'claude', 'client_request_id': 'stable-1',
                'node': 'node-local', 'cwd': '/test/workspace'}
        body.update(extra)
        return self.manager.submit(body)['task']['id']

    def test_a_gated_line_with_a_live_agent_is_still_driven_and_its_turn_end_is_seen(self):
        task_id = self.start(mode='lines', instruction='One\nTwo', node='node-test', cwd='/test/source')
        self.hub.turn = 'agent'
        self.manager.advance(task_id)                     # launch line 1 on the node
        keep = self.manager.advance(task_id)              # no adapter: gated, but the agent runs
        row = self.manager.get(task_id)
        self.assertEqual('awaiting_review', row['steps'][0]['status'])
        self.assertTrue(row['steps'][0].get('running'))
        self.assertTrue(keep, 'the coordinator keeps watching a running gated line')
        self.assertTrue(self.manager._driving(row))
        self.assertTrue(self.manager._busy(row), 'line 2 is still queued, so the fast cadence holds')
        self.assertEqual(1, len(self.hub.calls), 'line 2 is not launched into a busy workspace')
        self.hub.turn = 'bash'                            # the agent process handed the pane back
        self.hub.screen_text = 'complete messages and tool schemas exceed the admitted input budget'
        keep = self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('failed', row['steps'][0]['status'], 'the refusal was seen after the gate')
        self.assertIn('refused its own launch', row['steps'][0]['error'])
        self.assertFalse(keep)
        self.assertNotIn('running', row['steps'][0])

    def test_a_gated_line_whose_turn_ends_cleanly_keeps_evidence_and_stops_polling(self):
        task_id = self.start(mode='lines', instruction='One', node='node-test', cwd='/test/source')
        self.hub.turn = 'agent'
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertTrue(self.manager._driving(row))
        self.assertFalse(self.manager._busy(row), 'one gated line with a live agent polls at the slow cadence')
        self.hub.turn = 'bash'
        self.hub.screen_text = 'Wrote the file. Done.'
        keep = self.manager.advance(task_id)
        row = self.manager.get(task_id)
        self.assertEqual('awaiting_review', row['steps'][0]['status'])
        self.assertEqual('disk_cross_check', row['steps'][0]['evidence']['kind'])
        self.assertFalse(keep)
        self.assertFalse(self.manager._driving(row))

    def test_a_task_with_a_failed_line_and_nothing_left_to_drive_is_failed_not_queued(self):
        task_id = self.start(mode='lines', instruction='One\nTwo\nThree')
        path = self.manager._path(task_id)
        row = json.loads(path.read_text())
        for step, st in zip(row['steps'], ('completed', 'failed', 'completed')):
            step['status'] = st
        row['status'] = 'queued'
        path.write_text(json.dumps(row))
        seen = self.manager.get(task_id)
        self.assertEqual('failed', seen['status'])
        self.assertIn('Line 1 failed', seen['error'])
        self.assertFalse(seen['resume_required'])

    def test_auto_next_accepts_an_ended_turn_with_evidence_and_launches_the_next_line(self):
        task_id = self.start(mode='lines', instruction='One\nTwo', node='node-test', cwd='/test/source', auto_next=True, headless=True)
        self.hub.turn = 'agent'
        self.manager.advance(task_id)                     # launch line 1
        self.manager.advance(task_id)                     # gated, running
        self.hub.turn = 'bash'
        self.hub.screen_text = 'Created the file. Done.'
        keep = self.manager.advance(task_id)              # the turn ended: accepted (the worker keeps going)
        row = self.manager.get(task_id)
        self.assertEqual('completed', row['steps'][0]['status'])
        self.assertEqual('auto_next', row['steps'][0]['completion']['kind'])
        self.assertEqual(['1'], self.hub.stops)
        self.assertTrue(keep)
        self.manager.advance(task_id)                     # the next pass launches line 2
        row = self.manager.get(task_id)
        self.assertEqual(2, len(self.hub.calls), 'line 2 was launched')
        self.assertTrue(self.hub.calls[1][0].get('headless'), 'the launch carries the headless flag')
        self.assertEqual('active', row['steps'][1]['status'])

    def test_auto_next_never_accepts_a_refusal_or_a_claim_the_disk_contradicts(self):
        task_id = self.start(mode='lines', instruction='One\nTwo', node='node-test', cwd='/test/source', auto_next=True)
        self.hub.turn = 'agent'
        self.manager.advance(task_id)
        self.manager.advance(task_id)
        self.hub.turn = 'bash'
        self.hub.screen_text = 'complete messages and tool schemas exceed the admitted input budget'
        self.manager.advance(task_id)
        self.assertEqual('failed', self.manager.get(task_id)['steps'][0]['status'])
        self.assertEqual(1, len(self.hub.calls))
        with self.assertRaises(TaskError):
            self.start(mode='qwen', instruction='x', auto_next=True, client_request_id='q-1')

    def test_next_makes_a_watching_coordinator_yield_its_lease(self):
        task_id = self.start(mode='lines', instruction='One\nTwo', node='node-test', cwd='/test/source')
        self.hub.turn = 'agent'
        self.manager.advance(task_id)
        self.manager.advance(task_id)                     # gated, running: the worker would keep the lease
        import threading
        released = threading.Event()

        def watching_worker():
            with self.manager._lock(task_id, worker=True):
                # the worker's sleep: it leaves as soon as Next asks for the lease
                self.manager._sleep_unless_yield(task_id, 30)
            released.set()
        thread = threading.Thread(target=watching_worker, daemon=True)
        thread.start()
        time.sleep(0.3)
        result = self.manager.control(task_id, 'next')    # waits for the yield instead of a 409
        self.assertTrue(released.wait(5))
        row = result['task']
        self.assertEqual('completed', row['steps'][0]['status'])
        self.assertNotIn('yield_requested', row)
        self.assertEqual(['1'], self.hub.stops)

    def test_listing_reattaches_a_stranded_coordinator_without_replaying(self):
        scheduled = []
        manager = TaskManager(self.tmp.name, hub=self.hub, background=True,
                              completion=lambda *_: self.evidence, check_host=lambda: None)
        manager._schedule = lambda task_id: scheduled.append(task_id)
        body = {'instruction': 'Only line', 'engine': 'claude', 'client_request_id': 'stranded-1',
                'node': 'node-local', 'cwd': '/test/workspace', 'mode': 'lines'}
        task_id = manager.submit(body)['task']['id']
        self.assertEqual([task_id], scheduled)             # the normal start
        rows = manager.listing()
        self.assertTrue(rows[0]['resume_required'])
        self.assertEqual([task_id, task_id], scheduled, 'the listing re-attached the coordinator')
        self.assertEqual('listing', json.loads(manager._path(task_id).read_text())['resumed']['by'])
        self.assertEqual([], self.hub.calls, 'nothing was launched by the listing itself')
        done = json.loads(manager._path(task_id).read_text())
        done['status'] = 'completed'
        manager._path(task_id).write_text(json.dumps(done))
        manager.listing()
        self.assertEqual(2, len(scheduled), 'a terminal task is never re-attached')


class Adapter(unittest.TestCase):
    def test_hub_task_runner_is_a_complete_task_runner_over_the_engine(self):
        with tempfile.TemporaryDirectory() as root:
            hub = FakeHub()
            runner = HubTaskRunner(TaskManager(root, hub=hub, background=False, check_host=lambda: None,
                                               completion=lambda *_: {'available': False, 'done': False}))
            self.assertEqual([], missing_members(runner))
            self.assertEqual((('claude', 'local'), 'node-local'), (runner.engines, runner.local_node))
            task = runner.submit({'client_request_id': 'adapter-1', 'instruction': 'Build it.', 'engine': 'claude',
                                  'node': 'node-local', 'cwd': '/test/workspace'})['task']
            self.assertEqual(task['id'], runner.get(task['id'])['id'])
            self.assertEqual('cancelling', runner.control(task['id'], 'cancel')['task']['status'])


if __name__ == '__main__':
    unittest.main()
