"""Mixed project teams use only fake hub dispatch and temporary receipts."""
import copy
import json
import tempfile
import unittest

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host.symblicos_tasks import TaskError, TaskManager
    from tests.integration.test_symblicos_tasks import FakeHub
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None


class Hub(FakeHub):
    ENGINES = FakeHub.ENGINES + ('codex', 'agy', 'copilot')

    def start(self, options, group=''):
        reply = super().start(options, group)
        reply['agent']['cwd'] = '/test/' + options['node']
        return reply


def team():
    return {'version': 1, 'members': [
        {'id': 'architect', 'engine': 'claude', 'model': '', 'node': 'node-a', 'role': 'architect'},
        {'id': 'builder', 'engine': 'ollama', 'model': 'qwen3:4b-instruct', 'node': 'node-f', 'role': 'builder'},
        {'id': 'reviewer', 'engine': 'codex', 'model': '', 'node': 'node-a', 'role': 'reviewer'},
        {'id': 'tester', 'engine': 'copilot', 'model': '', 'node': 'node-local', 'role': 'tester'},
        {'id': 'editor', 'engine': 'agy', 'model': '', 'node': 'node-local', 'role': 'editor'},
    ]}


class ProjectTeams(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root, self.hub = temporary.name, Hub()
        self.manager = self.make_manager()

    def make_manager(self):
        return TaskManager(self.root, hub=self.hub, check_host=lambda: None, background=False,
            completion=lambda *_: {'available': False, 'done': False})

    def body(self, **extra):
        return {'client_request_id': 'mixed-five', 'instruction': 'Build and check the owner game.',
                'mode': 'team', 'team': team(), 'cwd': '/test/source', 'auto': True,
                'worktree': True, 'context_note': 'Only the named game.', **extra}

    def finish(self, task_id):
        self.manager.advance(task_id)
        self.assertEqual(self.manager.get(task_id)['status'], 'awaiting_review')
        self.manager.control(task_id, 'next')

    def test_five_distinct_agents_each_exact_selection_and_per_device_workspace(self):
        task = self.manager.submit(self.body())['task']
        self.assertEqual(task['team_policy']['planned_sessions'], 5)
        for index in range(5):
            self.manager.advance(task['id'])
            options, group = self.hub.calls[index]
            member = task['team']['members'][index]
            self.assertEqual(options['node'], member['node'])
            self.assertEqual(options['engine'], {'ollama': 'local'}.get(member['engine'], member['engine']))
            self.assertEqual(options['model'], member['model'])
            self.assertIn('"id":"' + member['id'] + '"', options['prompt'])
            self.assertIn('Build and check the owner game.', options['prompt'])
            if index == 1:
                self.assertNotIn('workspaceFrom', options, 'different nodes must not receive another device checkout')
            if index == 2:
                self.assertEqual(options['workspaceFrom'], '1', 'reuse the last matching device, not immediately previous seat')
            if index == 4:
                self.assertEqual(options['cwd'], '/test/node-local')
                self.assertFalse(options['worktree'])
            self.finish(task['id'])
        self.manager.advance(task['id'])
        self.assertEqual(self.manager.get(task['id'])['status'], 'completed')
        self.assertEqual(self.hub.stops, ['1', '2', '3', '4', '5'])
        self.assertEqual(len({call[1] for call in self.hub.calls}), 5)

    def test_fresh_lines_expand_exact_member_order_without_prior_prompt(self):
        result = self.manager.submit(self.body(instruction='FIRST unique\n\nSECOND unique', fresh_lines=True))['task']
        self.assertEqual(len(result['steps']), 10)
        self.assertEqual(result['team_policy']['planned_sessions'], 10)
        self.assertEqual([step['instruction_index'] for step in result['steps']], [0]*5+[1]*5)
        for step in result['steps']:
            prompt = self.manager._prompt(result, step)
            self.assertNotIn('SECOND unique' if step['instruction_index'] == 0 else 'FIRST unique', prompt)

    def test_duplicate_binds_exact_profiles_no_extra_dispatch(self):
        body = self.body()
        task = self.manager.submit(body)['task']
        self.manager.advance(task['id'])
        again = self.make_manager().submit(body)
        self.assertTrue(again['duplicate'])
        self.assertEqual(len(self.hub.calls), 1)
        altered = copy.deepcopy(body)
        altered['team']['members'][0]['instruction'] = 'New characteristic.'
        with self.assertRaisesRegex(TaskError, 'different'):
            self.make_manager().submit(altered)

    def test_receipt_profile_tampering_is_fenced(self):
        task = self.manager.submit(self.body())['task']
        path = self.manager._path(task['id'])
        row = json.loads(path.read_text())
        row['steps'][0]['member']['node'] = 'node-i'
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(TaskError, 'identity changed'):
            self.manager.advance(task['id'])
        self.assertEqual(self.hub.calls, [])

    def test_ambiguous_launch_never_replays_and_recovery_keeps_member(self):
        original = self.hub.start
        def lost(options, group=''):
            original(options, group)
            raise OSError('response lost')
        self.hub.start = lost
        task = self.manager.submit(self.body())['task']
        self.manager.advance(task['id'])
        self.assertEqual(self.manager.get(task['id'])['status'], 'unknown')
        self.make_manager().advance(task['id'])
        self.assertEqual(len(self.hub.calls), 1)
        self.hub.start = original
        recovered = self.make_manager().control(task['id'], 'resume')['task']
        self.assertEqual(recovered['steps'][0]['member']['id'], 'architect')
        self.assertEqual(recovered['steps'][0]['agent_id'], '1')
        self.assertEqual(len(self.hub.calls), 1)

    def test_cancel_stops_owned_agent_and_never_starts_other_seats(self):
        task = self.manager.submit(self.body())['task']
        self.manager.advance(task['id'])
        self.manager.control(task['id'], 'cancel')
        self.manager.advance(task['id'])
        self.assertEqual(self.manager.get(task['id'])['status'], 'cancelled')
        self.assertEqual(self.hub.stops, ['1'])
        self.assertEqual(len(self.hub.calls), 1)

    def test_unsupported_project_options_or_aggregate_seats_refuse_before_launch(self):
        for change in ({'engine': 'triad'}, {'settings': {'temperature': .5}}, {'engine': 'unknown'}, {'weight': 2}):
            body = self.body()
            body['team']['members'][0].update(change)
            with self.subTest(change=change), self.assertRaises(TaskError):
                self.manager.submit(body)
        with self.assertRaisesRegex(TaskError, 'requires mode'):
            self.manager.submit(self.body(mode='agent', engine='claude', node='node-local'))
        self.assertEqual(self.hub.calls, [])
