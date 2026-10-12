"""The autogen coordinator over the original host's task engine (HOST-ONLY engine, fake hub).

These are the coordinator's long journeys as they ran on the original host: every attempt is a task of
integration/host/symblicos_tasks.py (TaskManager), adapted to the TaskRunner protocol by HubTaskRunner,
and every agent is played by a fake hub whose agents work in a temporary project folder, so the task
engine's disk cross-check sees real files. Each journey drives AutogenManager.advance(run_id) and
TaskManager.advance(task_id) by hand. No model, agent, node or live hub is touched. The standalone
version of the core journeys, over the documented FakeTaskRunner, is tests/autogen/test_coordinator.py.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/integration -t .
"""
import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.autogen import policy as POLICY
from symblic.autogen import coordinator as AG
from symblic.autogen.coordinator import AutogenError, AutogenManager
from integration.host.symblicos_tasks import HubTaskRunner, TaskManager


class FakeHub:
    ENGINES = ('claude', 'agy', 'codex', 'triad')
    LOCAL_NODE = 'orchestrator'
    MODEL_RX = re.compile(r'^[\w.:/-]{1,80}$')
    _SHELLS = ('bash', 'sh')

    def __init__(self, workspace):
        self.workspace = workspace
        self.calls = []
        self.stops = []
        self.agents = []
        self.actions = []
        self.error = None
        self.turn = 'agent'       # what the agent pane runs now: 'agent', a shell, another process or 'gone'
        self.screen_text = ''
        self.apply_result = None

    def start(self, options, group=''):
        self.calls.append((options, group))
        if self.error:
            raise self.error
        agent = {'id': str(len(self.calls)), 'group': group, 'engine': options['engine'],
                 'cwd': options.get('cwd') or self.workspace, 'node': options.get('node', 'orchestrator')}
        self.agents.append(agent)
        return {'agent': agent, 'url': '/terminal?session=' + agent['id']}

    def stop(self, agent_id):
        self.stops.append(agent_id)
        return {'ok': True}

    def work_action(self, action, agent_id, title='', upto=''):
        self.actions.append((action, agent_id))
        if action == 'apply' and self.apply_result is not None:
            return self.apply_result
        return {'message': 'ok', 'files': ['app.py']}

    def _find(self, agent_id, parked=False):
        return next((a for a in self.agents if a['id'] == agent_id), None)

    def _load(self):
        return {'agents': self.agents}

    def is_remote(self, agent):
        return (agent or {}).get('node', self.LOCAL_NODE) != self.LOCAL_NODE

    def _current(self, agent_id, agent=None):
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
        return agent.get('node', 'orchestrator')

    @staticmethod
    def _home():
        return '/test'

    @staticmethod
    def fleet_nodes(refresh=False):
        return [{'id': 'orchestrator', 'label': 'orchestrator', 'online': True},
                {'id': 'node09', 'label': 'node09', 'online': True}]


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / 'symblicos'
        self.root.mkdir()
        self.project = base / 'project'
        (self.project / '.git').mkdir(parents=True)
        self.cwd = str(self.project)
        self.hub = FakeHub(self.cwd)
        self.evidence = {}        # agent id -> completion evidence the fake adapter reports
        self.results = {}         # syntax target file or shell command -> {'rc', 'out'}
        self.runs = []
        self.on_run = None
        self.clock = Clock(time.time())
        self.tasks = self.make_tasks()
        self.auto = self.make_auto()

    # -- injected collaborators
    def completion(self, hub, agent):
        return self.evidence.get(agent['id'], {'available': True, 'done': False, 'reason': 'still working'})

    def runner(self, argv, cwd, timeout=120, shell=False):
        self.runs.append({'argv': argv, 'cwd': cwd, 'shell': shell, 'timeout': timeout})
        if self.on_run:
            self.on_run(argv)
        return dict(self.results.get(argv if shell else argv[-1], {'rc': 0, 'out': ''}))

    def listing(self, folder, limit=400):
        return AG._listing(folder, limit)

    def make_tasks(self):
        return TaskManager(str(self.root), hub=self.hub, background=False, completion=self.completion,
                           check_host=lambda: None)

    def make_auto(self, tasks=None, **extra):
        return AutogenManager(str(self.root), task_runner=HubTaskRunner(tasks or self.tasks, self.hub), background=False,
                              check_host=lambda: None, check_runner=self.runner, listing=self.listing, clock=self.clock,
                              **extra)

    # -- helpers
    def statement(self, name, extra='with a function named main'):
        return f'Create the file {name} in the folder {self.cwd} {extra}.'

    def body(self, lines, request='run-1', **policy):
        return {'client_request_id': request, 'instruction': '\n'.join(lines), 'engine': 'claude',
                'node': 'orchestrator', 'cwd': self.cwd, 'autogen': policy}

    def submit(self, lines, request='run-1', **policy):
        return self.auto.submit(self.body(lines, request, **policy))['run']['id']

    def node(self, run_id, node_id):
        return next(n for n in self.auto.get(run_id)['nodes'] if n['id'] == node_id)

    def attempts(self, run_id, node_id):
        return self.node(run_id, node_id)['attempts']

    def events(self, run_id):
        path = self.root / 'state' / 'autogen' / (run_id + '.events.jsonl')
        return [json.loads(line) for line in path.read_text().splitlines()]

    def names(self, run_id):
        return [e['event'] for e in self.events(run_id)]

    def write(self, rel, text, at=None):
        path = self.project / rel
        path.write_text(text)
        stamp = self.clock() if at is None else at
        os.utime(path, (stamp, stamp))

    def checkpoint(self, done, left, files):
        self.write(POLICY.CHECKPOINT_FILE, json.dumps({'version': 1, 'done': done, 'left': left, 'files': files}))

    def launch(self, attempt):
        """The task engine launches the attempt's agent; returns its agent id."""
        self.tasks.advance(attempt['task_id'])
        step = self.tasks.get(attempt['task_id'])['steps'][0]
        self.assertEqual('active', step['status'])
        return step['agent_id']

    def finish(self, attempt):
        """The agent's native turn ends; the task engine records evidence and completes it."""
        agent_id = self.tasks.get(attempt['task_id'])['steps'][0]['agent_id']
        self.evidence[agent_id] = {'available': True, 'done': True, 'kind': 'native_turn'}
        self.tasks.advance(attempt['task_id'])
        self.assertEqual('completed', self.tasks.get(attempt['task_id'])['status'])
        return agent_id

    def suffix(self, run_id, index=0):
        run = self.auto.get(run_id)
        node = next((n for n in run['nodes'] if n['parent'] is None and n['index'] == index), run['nodes'][0])
        limit = POLICY.HARD_DEPTH if run['policy'].get('until_done') else run['policy']['depth']
        can_split = not node.get('perpetual') and node.get('depth', 0) < limit
        return POLICY.worker_suffix(run['policy'], index, self.cwd, can_split=can_split)

    def loc(self, text):
        """An attempt instruction as the worker receives it: localized to its own checkout (D6)."""
        return POLICY.localize(text, self.cwd)


class Admission(Harness):
    def test_record_is_durable_before_any_launch_and_duplicates_return_it(self):
        lines = [self.statement('app.py')]
        result = self.auto.submit(self.body(lines))
        run_id = result['run']['id']
        self.assertFalse(result['duplicate'])
        self.assertRegex(run_id, r'^autogen-[a-f0-9]{24}$')
        on_disk = json.loads((self.root / 'state' / 'autogen' / (run_id + '.json')).read_text())
        self.assertEqual('queued', on_disk['status'])
        self.assertEqual([], on_disk['nodes'][0]['attempts'])
        self.assertEqual({'agents_started': 0, 'agents_max': 24, 'deadline': self.clock() + 6 * 3600},
                         on_disk['budget'])
        self.assertEqual(['submitted'], self.names(run_id))
        self.assertEqual([], self.hub.calls)
        self.assertEqual([], self.tasks.listing())

        again = self.auto.submit(self.body(lines))
        self.assertTrue(again['duplicate'])
        self.assertEqual(run_id, again['run']['id'])

        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual(1, len(self.tasks.listing()))
        events_before = len(self.events(run_id))
        restarted = self.make_auto(self.make_tasks())
        again = restarted.submit(self.body(lines))
        self.assertTrue(again['duplicate'])
        self.assertEqual(run_id, again['run']['id'])
        self.assertEqual(1, len(self.tasks.listing()))      # no new task
        self.assertEqual([], self.hub.calls)                 # and no agent
        self.assertEqual(events_before, len(self.events(run_id)))

        with self.assertRaises(AutogenError) as caught:
            self.auto.submit(self.body(lines, regenerate=1))
        self.assertEqual(409, caught.exception.status)
        self.assertIn('different statements or a different policy', str(caught.exception))

    def test_refusals_happen_before_any_record(self):
        plain = Path(self.tmp.name) / 'plain'
        plain.mkdir()
        good = self.statement('app.py')
        cases = [
            ({**self.body([good]), 'cwd': str(plain)}, 'git workspace'),
            ({**self.body([good]), 'cwd': 'relative/folder'}, 'Select the project workspace'),
            ({**self.body([good]), 'options': {'engine': 'claude'}}, 'Unknown autogen field options.'),
            (self.body([good], bogus=1), 'Unknown autogen field bogus.'),
            ({**self.body([good]), 'engine': 'gemini'}, 'Choose an engine the task runner offers.'),
            (self.body(['Make it.']), 'Statements refused: line 1: shorter than 20 characters'),
            (self.body([good], final=['curl https://example.org']), 'final contains a command the autogen runner refuses'),
            (self.body([good], candidates=5), 'candidates must be from 1 to 4'),
            ({**self.body([good]), 'client_request_id': 'bad id!'}, 'stable client_request_id'),
        ]
        for body, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(AutogenError) as caught:
                    self.auto.submit(body)
                self.assertIn(message, str(caught.exception))
                self.assertEqual(400, getattr(caught.exception, 'status', 400))
        autogen_dir = self.root / 'state' / 'autogen'
        self.assertEqual([], list(autogen_dir.glob('*.json')) if autogen_dir.exists() else [])
        self.assertEqual([], self.tasks.listing())


class Candidates(Harness):
    def test_first_passing_candidate_is_promoted_and_its_rival_cancelled(self):
        lines = [self.statement('app.py'), self.statement('lib.py')]
        run_id = self.submit(lines, candidates=2)
        self.assertTrue(self.auto.advance(run_id))
        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(['n0-a0', 'n0-a1'], [a0['id'], a1['id']])
        self.assertEqual(['run-1:n0-a0', 'run-1:n0-a1'], [a0['request_id'], a1['request_id']])
        for attempt in (a0, a1):
            task = self.tasks.get(attempt['task_id'])
            self.assertEqual(attempt['request_id'], task['client_request_id'])
            self.assertEqual('agent', task['mode'])
            self.assertEqual(self.loc(lines[0] + '\n\n' + self.suffix(run_id)), task['instruction'])
            self.assertNotIn(self.cwd, task['instruction'])
            self.assertTrue(task['context_note'].startswith(POLICY.CHECKOUT_LOCK))
            self.assertEqual({'engine': 'claude', 'node': 'orchestrator', 'cwd': self.cwd, 'worktree': True,
                              'auto': True, 'auto_next': True, 'headless': True}, task['options'])
            self.assertEqual(('candidate', 'fresh', 'running'), (attempt['kind'], attempt['strategy'], attempt['status']))
            self.assertNotIn('body', attempt)
        self.assertEqual(2, self.auto.get(run_id)['budget']['agents_started'])

        agent0 = self.launch(a0)
        agent1 = self.launch(a1)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(a1)                                  # the second candidate finishes first
        self.assertTrue(self.auto.advance(run_id))

        node = self.node(run_id, 'n0')
        self.assertEqual(('accepted', 'n0-a1'), (node['status'], node['winner']))
        won, lost = node['attempts'][1], node['attempts'][0]
        self.assertEqual('accepted', won['status'])
        self.assertTrue(won['verdict']['passed'])
        self.assertEqual(['exists', 'syntax'], [c['kind'] for c in won['verdict']['checks']])
        self.assertEqual(1, won['verdict']['files_changed'])
        self.assertEqual(agent1, won['agent_id'])
        self.assertEqual(('failed', 'CANCELLED', 'another candidate was accepted first'),
                         (lost['status'], lost['failure'], lost['error']))
        self.assertEqual([('commit', agent1), ('apply', agent1)], self.hub.actions)
        self.assertEqual({'message': 'ok', 'files': ['app.py']}, won['applied'])
        syntax = [r for r in self.runs if not r['shell']]
        self.assertEqual(1, len(syntax))
        self.assertEqual('app.py', syntax[0]['argv'][-1])
        self.assertEqual(self.cwd, syntax[0]['cwd'])

        rival = self.tasks.get(a0['task_id'])
        self.assertTrue(rival['cancel_requested'])
        self.tasks.advance(a0['task_id'])                # the task engine closes the rival's agent
        self.assertEqual('cancelled', self.tasks.get(a0['task_id'])['status'])
        self.assertIn(agent0, self.hub.stops)

        # every intent of a wave is durable before the first submit (crash safety, 7a)
        self.assertEqual(['submitted', 'decision', 'launch_intent', 'launch_intent', 'launched', 'launched',
                          'attempt_accepted', 'decision', 'promoted', 'node_accepted'], self.names(run_id))
        accept = self.events(run_id)[7]
        self.assertEqual(('n0', 'accept'), (accept['node'], accept['action']))
        self.assertEqual(list(range(1, 11)), [e['seq'] for e in self.events(run_id)])

        self.assertTrue(self.auto.advance(run_id))       # the next statement launches
        self.assertEqual(['run-1:n1-a0', 'run-1:n1-a1'], [a['request_id'] for a in self.attempts(run_id, 'n1')])
        task = self.tasks.get(self.attempts(run_id, 'n1')[0]['task_id'])
        self.assertEqual(self.loc(lines[1] + '\n\n' + self.suffix(run_id, 1)), task['instruction'])
        self.assertEqual(['decision', 'launch_intent', 'launch_intent', 'launched', 'launched'], self.names(run_id)[10:])


class Regeneration(Harness):
    def test_feedback_carries_public_output_only_then_rotates_then_fails(self):
        statement = self.statement('app.py')
        run_id = self.submit([statement], candidates=1, regenerate=2, hidden=['test -s hidden-oracle'],
                             strategies=['fresh', 'feedback'])
        self.results['app.py'] = {'rc': 1, 'out': 'SyntaxError: x'}
        self.results['test -s hidden-oracle'] = {'rc': 1, 'out': 'HIDDEN-ORACLE-OUTPUT'}

        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.launch(first)
        self.write('app.py', 'def main(:\n')
        self.finish(first)
        self.assertTrue(self.auto.advance(run_id))       # observe the failure and regenerate in one pass

        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(('failed', 'SYNTAX'), (a0['status'], a0['failure']))
        # hidden checks run once, as a run-level gate in _finish, never in an attempt's verdict (D4)
        self.assertEqual([('exists', True), ('syntax', False)],
                         [(c['kind'], c['passed']) for c in a0['verdict']['checks']])
        self.assertEqual([True, True], [c['public'] for c in a0['verdict']['checks']])
        self.assertNotIn('test -s hidden-oracle', [r['argv'] for r in self.runs])
        self.assertEqual(('regen', 'feedback', 'run-1:n0-a1'), (a1['kind'], a1['strategy'], a1['request_id']))
        child = self.tasks.get(a1['task_id'])
        self.assertIn('- syntax app.py: SyntaxError: x', child['context_note'])
        for text in (child['context_note'], child['instruction']):
            self.assertNotIn('HIDDEN-ORACLE-OUTPUT', text)
            self.assertNotIn('hidden-oracle', text)
        self.assertEqual(self.loc(statement + '\n\n' + self.suffix(run_id)), child['instruction'])
        self.assertTrue(child['context_note'].startswith(POLICY.CHECKOUT_LOCK + '\n\nA previous attempt'))
        node = self.node(run_id, 'n0')
        self.assertEqual(POLICY.fingerprint(node, 'feedback', 'SYNTAX'), node['last_fingerprint'])
        self.assertEqual('regeneration after SYNTAX', node['decisions'][-1]['reason'])

        self.launch(a1)
        self.write('app.py', 'def main(:\n    pass\n')
        self.finish(a1)
        self.assertTrue(self.auto.advance(run_id))       # the identical failure rotates the strategy
        a2 = self.attempts(run_id, 'n0')[2]
        self.assertEqual(('failed', 'SYNTAX'), (self.attempts(run_id, 'n0')[1]['status'], self.attempts(run_id, 'n0')[1]['failure']))
        self.assertEqual(('regen', 'fresh'), (a2['kind'], a2['strategy']))
        self.assertEqual(POLICY.CHECKOUT_LOCK, self.tasks.get(a2['task_id'])['context_note'])
        node = self.node(run_id, 'n0')
        self.assertEqual(POLICY.fingerprint(node, 'fresh', 'SYNTAX'), node['last_fingerprint'])

        self.launch(a2)
        self.write('app.py', 'def main(:\n    return 3\n')
        self.finish(a2)
        self.assertFalse(self.auto.advance(run_id))      # candidates + regenerate spent at depth 0
        run = self.auto.get(run_id)
        reason = 'no eligible strategy remains: SYNTAX, SYNTAX, SYNTAX'
        self.assertEqual(('failed', 'Statement n0 failed: ' + reason), (run['status'], run['error']))
        self.assertEqual(('failed', reason), (run['nodes'][0]['status'], run['nodes'][0]['error']))
        self.assertEqual(3, run['budget']['agents_started'])
        self.assertEqual(3, len(self.hub.calls))
        self.assertEqual(['SYNTAX', 'SYNTAX', 'SYNTAX'], run['summary']['nodes'][0]['failed'])
        self.assertEqual(['attempt_failed', 'decision', 'node_failed'], self.names(run_id)[-3:])
        self.assertFalse(self.auto.advance(run_id))      # terminal: nothing more is launched
        self.assertEqual(3, len(self.hub.calls))


class Decomposition(Harness):
    def parent(self):
        return f'Create the files alpha.py and beta.py in the folder {self.cwd} with one function each.'

    def fail_first_wave(self, run_id):
        first = self.attempts(run_id, 'n0')[0]
        self.launch(first)
        self.finish(first)                               # wrote nothing: NO_OUTPUT
        self.assertTrue(self.auto.advance(run_id))
        a0, planner = self.attempts(run_id, 'n0')
        self.assertEqual(('failed', 'NO_OUTPUT'), (a0['status'], a0['failure']))
        return planner

    def test_split_children_run_before_the_next_statement_and_the_parent_reads_accepted(self):
        tail = self.statement('gamma.py')
        run_id = self.submit([self.parent(), tail], candidates=1, regenerate=0, depth=1,
                             checks={'1': ['grep -q gamma gamma.py']})
        self.auto.advance(run_id)
        planner = self.fail_first_wave(run_id)
        self.assertEqual(('planner', 'split', 'run-1:n0-a1'), (planner['kind'], planner['strategy'], planner['request_id']))
        policy = self.auto.get(run_id)['policy']
        self.assertEqual(self.loc(POLICY.split_prompt(self.parent(), self.cwd, policy, 0)),
                         self.tasks.get(planner['task_id'])['instruction'])
        self.assertNotIn(self.cwd, self.tasks.get(planner['task_id'])['instruction'])

        self.launch(planner)
        children = [f'Create the file alpha.py in the folder {self.cwd} with a function named alpha.',
                    f'Create the file beta.py in the folder {self.cwd} with a function named beta.']
        self.write(POLICY.SPLIT_FILE, '\n'.join(children) + '\n')
        self.finish(planner)
        self.assertTrue(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual(('split', ['n0.0', 'n0.1'], 'n0-a1'), (node['status'], node['children'], node['winner']))
        self.assertEqual(children, self.attempts(run_id, 'n0')[1]['split'])
        self.assertEqual([], self.hub.actions)           # a split is not promoted
        run = self.auto.get(run_id)
        self.assertEqual(['n0', 'n1'], run['order'])
        self.assertEqual([('n0.0', 1, 'n0', children[0]), ('n0.1', 1, 'n0', children[1])],
                         [(n['id'], n['depth'], n['parent'], n['statement']) for n in run['nodes'][2:]])
        self.assertEqual(['attempt_accepted', 'decision', 'node_split'], self.names(run_id)[-3:])

        for child_id, name in (('n0.0', 'alpha.py'), ('n0.1', 'beta.py')):
            self.assertTrue(self.auto.advance(run_id))   # the child launches before statement n1
            attempt = self.attempts(run_id, child_id)[0]
            self.assertEqual(f'run-1:{child_id}-a0', attempt['request_id'])
            self.assertEqual([], self.attempts(run_id, 'n1'))
            self.launch(attempt)
            self.write(name, 'def f():\n    return 1\n')
            agent = self.finish(attempt)
            self.assertTrue(self.auto.advance(run_id))
            child = self.node(run_id, child_id)
            self.assertEqual(('accepted', child_id + '-a0'), (child['status'], child['winner']))
            self.assertEqual(('apply', agent), self.hub.actions[-1])
            # a child's sibling index never selects the operator's commands for a top-level statement
            self.assertEqual(['exists', 'syntax'], [c['kind'] for c in child['attempts'][0]['verdict']['checks']])
        self.assertNotIn('grep -q gamma gamma.py', [r['argv'] for r in self.runs])

        self.assertTrue(self.auto.advance(run_id))       # the parent reads accepted; n1 launches
        node = self.node(run_id, 'n0')
        self.assertEqual(('accepted', 'children'), (node['status'], node['winner']))
        last = self.attempts(run_id, 'n1')[0]
        self.assertEqual('run-1:n1-a0', last['request_id'])
        self.launch(last)
        self.write('gamma.py', 'gamma = 1\n')
        self.finish(last)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(['exists', 'syntax', 'command'],
                         [c['kind'] for c in run['nodes'][1]['attempts'][0]['verdict']['checks']])
        self.assertEqual(['accepted'] * 4, [n['status'] for n in run['nodes']])
        self.assertEqual(5, run['budget']['agents_started'])

    def test_a_split_that_drops_a_file_fails_the_planner_and_the_node(self):
        run_id = self.submit([self.parent()], candidates=1, regenerate=0, depth=1)
        self.auto.advance(run_id)
        planner = self.fail_first_wave(run_id)
        self.launch(planner)
        self.write(POLICY.SPLIT_FILE,
                   f'Create the file alpha.py in the folder {self.cwd} with a function named alpha.\n'
                   f'Create the file notes.md in the folder {self.cwd} describing the alpha function.\n')
        self.finish(planner)
        self.assertFalse(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        planner = node['attempts'][1]
        self.assertEqual(('failed', 'UNKNOWN'), (planner['status'], planner['failure']))
        self.assertIn('the split drops files the statement names: beta.py', planner['error'])
        self.assertEqual([('split', False)], [(c['kind'], c['passed']) for c in planner['verdict']['checks']])
        self.assertEqual(('failed', []), (node['status'], node['children']))
        run = self.auto.get(run_id)
        self.assertTrue(node['split_refused'])           # D8: no second planner, ever
        self.assertEqual(('failed', 'Statement n0 failed: no eligible strategy remains: NO_OUTPUT; the split was refused'),
                         (run['status'], run['error']))
        self.assertEqual(2, len(self.hub.calls))         # no second planner
        self.assertEqual(['attempt_failed', 'decision', 'node_failed'], self.names(run_id)[-3:])


class Handoff(Harness):
    def test_checkpointed_worker_hands_off_until_the_generation_cap(self):
        statement = self.statement('big.py', 'with ten numbered functions')
        run_id = self.submit([statement], generations=3)
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        self.auto.advance(run_id)
        for generation in range(4):
            attempt = self.attempts(run_id, 'n0')[-1]
            self.assertEqual(generation, attempt['generation'])
            self.launch(attempt)
            self.write('big.py', 'def f1():\n' * (generation + 1))
            self.checkpoint([f'f1 to f{generation + 3}'], [f'f{generation + 4} to f10'], ['big.py'])
            self.finish(attempt)
            keep = self.auto.advance(run_id)
            seen = self.attempts(run_id, 'n0')[generation]
            self.assertEqual(('handoff', None), (seen['status'], seen['failure']))
            self.assertEqual({'valid': True, 'done': [f'f1 to f{generation + 3}'],
                              'left': [f'f{generation + 4} to f10'], 'files': ['big.py']}, seen['checkpoint'])
            self.assertEqual(generation, self.node(run_id, 'n0')['generation'])
            if generation < 3:
                self.assertTrue(keep)
                successor = self.attempts(run_id, 'n0')[-1]
                self.assertEqual(('handoff', 'handoff', generation + 1, seen['id']),
                                 (successor['kind'], successor['strategy'], successor['generation'], successor['from']))
                instruction = self.tasks.get(successor['task_id'])['instruction']
                self.assertEqual(self.loc(POLICY.handoff_prompt(statement, seen['checkpoint'], generation + 1)
                                          + '\n\n' + self.suffix(run_id)), instruction)
                options = self.tasks.get(successor['task_id'])['options']
                self.assertEqual((seen['workspace'], False), (options['cwd'], options['worktree']))
                self.assertEqual(self.node(run_id, 'n0')['handoffs'], generation + 1)
                self.assertIn(f'Done: f1 to f{generation + 3}', instruction)
                self.assertIn(f'Left: f{generation + 4} to f10', instruction)
                self.assertEqual(['attempt_handoff', 'decision', 'launch_intent', 'launched'], self.names(run_id)[-4:])
            else:
                self.assertFalse(keep)
        run = self.auto.get(run_id)
        self.assertEqual(('failed', 'Statement n0 failed: handoff generations exhausted'), (run['status'], run['error']))
        self.assertEqual(4, run['budget']['agents_started'])
        self.assertEqual(['attempt_handoff', 'decision', 'node_failed'], self.names(run_id)[-3:])

    def test_a_checkpoint_naming_absent_files_or_predating_the_attempt_is_no_handoff(self):
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        for request, write_checkpoint in (
                ('absent', lambda: self.checkpoint(['f1'], ['f2'], ['big.py', 'missing.py'])),
                ('stale', lambda: self.write(POLICY.CHECKPOINT_FILE, json.dumps(
                    {'version': 1, 'done': ['f1'], 'left': ['f2'], 'files': ['big.py']}), at=self.clock() - 60))):
            with self.subTest(request=request):
                run_id = self.submit([self.statement('big.py', 'with ten numbered functions')], request, generations=3)
                self.auto.advance(run_id)
                attempt = self.attempts(run_id, 'n0')[0]
                self.launch(attempt)
                self.write('big.py', 'def f1():\n' + request)
                write_checkpoint()
                self.finish(attempt)
                self.auto.advance(run_id)
                a0, a1 = self.attempts(run_id, 'n0')
                self.assertEqual(('failed', 'SYNTAX'), (a0['status'], a0['failure']))
                self.assertNotIn('checkpoint', a0)
                self.assertEqual(('regen', 'feedback'), (a1['kind'], a1['strategy']))


class Perpetual(Harness):
    def test_generations_wait_for_the_interval_and_stop_at_the_cap(self):
        statement = f'Index the notes in the folder {self.cwd} and write the summary to index.md for each batch.'
        run_id = self.submit([statement], perpetual=True, generations=2, interval_seconds=60)
        self.assertTrue(self.auto.advance(run_id))
        first = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('perpetual', 'perpetual', 1), (first['kind'], first['strategy'], first['generation']))
        self.assertEqual(self.loc(POLICY.perpetual_prompt(statement, {}, 1, 60) + '\n\n' + self.suffix(run_id)),
                         self.tasks.get(first['task_id'])['instruction'])
        self.launch(first)
        self.write('index.md', '# batch 1\n')
        self.checkpoint(['batch 1'], ['batch 2'], ['index.md'])
        agent = self.finish(first)
        self.assertTrue(self.auto.advance(run_id))
        first = self.attempts(run_id, 'n0')[0]
        self.assertEqual('generation_done', first['status'])
        self.assertEqual(1, self.node(run_id, 'n0')['generation'])
        self.assertEqual('pending', self.node(run_id, 'n0')['status'])
        self.assertEqual([('commit', agent), ('apply', agent)], self.hub.actions)   # each generation is promoted
        self.assertEqual('perpetual interval not elapsed', self.node(run_id, 'n0')['decisions'][-1]['reason'])
        self.assertEqual(1, len(self.hub.calls))

        self.clock.advance(59)
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual(1, len(self.attempts(run_id, 'n0')))
        self.clock.advance(1)
        self.assertTrue(self.auto.advance(run_id))
        second = self.attempts(run_id, 'n0')[1]
        self.assertEqual(('perpetual', 2, 'run-1:n0-a1'), (second['kind'], second['generation'], second['request_id']))
        instruction = self.tasks.get(second['task_id'])['instruction']
        self.assertIn('Perpetual generation 2', instruction)
        self.assertIn('Earlier done: batch 1.', instruction)
        self.assertIn('Cursor: batch 2.', instruction)

        self.launch(second)
        self.write('index.md', '# batch 1\n# batch 2\n')
        self.finish(second)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(('accepted', 'generations', 2), (run['nodes'][0]['status'], run['nodes'][0]['winner'],
                                                          run['nodes'][0]['generation']))
        self.assertEqual(['generation_done', 'generation_done'], [a['status'] for a in run['nodes'][0]['attempts']])
        self.assertEqual(['promoted', 'generation_done', 'decision', 'node_accepted', 'completed'], self.names(run_id)[-5:])


class Timeouts(Harness):
    def test_attempt_seconds_cancels_the_child_task_and_regenerates_elsewhere(self):
        run_id = self.submit([self.statement('app.py')], attempt_seconds=120)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.clock.advance(120)
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual('running', self.attempts(run_id, 'n0')[0]['status'])
        self.clock.advance(1)
        self.assertTrue(self.auto.advance(run_id))
        timed_out = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'TIMEOUT'), (timed_out['status'], timed_out['failure']))
        self.assertEqual('attempt exceeded the policy attempt_seconds allowance', timed_out['error'])
        self.assertEqual(['decision', 'attempt_timeout'], self.names(run_id)[-2:])
        self.assertEqual('wait', self.events(run_id)[-2]['action'])
        self.assertTrue(self.tasks.get(attempt['task_id'])['cancel_requested'])
        self.tasks.advance(attempt['task_id'])
        self.assertEqual('cancelled', self.tasks.get(attempt['task_id'])['status'])
        self.assertIn(agent, self.hub.stops)

        self.assertTrue(self.auto.advance(run_id))       # infrastructure-class failure: another machine
        regen = self.attempts(run_id, 'n0')[1]
        self.assertEqual(('regen', 'other_node', 'node09'), (regen['kind'], regen['strategy'], regen['node']))
        self.assertEqual('node09', self.tasks.get(regen['task_id'])['options']['node'])


class Cancel(Harness):
    def test_cancel_closes_running_children_and_the_run(self):
        run_id = self.submit([self.statement('app.py')], candidates=2)
        self.auto.advance(run_id)
        attempts = self.attempts(run_id, 'n0')
        agents = [self.launch(a) for a in attempts]
        run = self.auto.control(run_id, 'cancel')['run']
        self.assertTrue(run['cancel_requested'])
        self.assertEqual('active', run['status'])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('cancelled', run['status'])
        self.assertEqual([('failed', 'CANCELLED')] * 2, [(a['status'], a['failure']) for a in run['nodes'][0]['attempts']])
        self.assertEqual(['cancel_requested', 'cancelled'], self.names(run_id)[-2:])
        for attempt, agent in zip(attempts, agents):
            self.assertTrue(self.tasks.get(attempt['task_id'])['cancel_requested'])
            self.tasks.advance(attempt['task_id'])
            self.assertEqual('cancelled', self.tasks.get(attempt['task_id'])['status'])
            self.assertIn(agent, self.hub.stops)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('cancelled', self.auto.control(run_id, 'resume')['run']['status'])
        self.assertNotIn('resumed', self.names(run_id))
        self.assertEqual(2, len(self.hub.calls))

    def test_cancel_during_a_pass_survives_the_pass(self):
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.write('app.py', 'def main(:\n')
        self.finish(attempt)
        self.results['app.py'] = {'rc': 1, 'out': 'SyntaxError: x'}
        self.on_run = lambda argv: self.auto.control(run_id, 'cancel')   # the operator presses Cancel mid-check
        self.auto.advance(run_id)
        self.on_run = None
        self.assertTrue(self.auto.get(run_id)['cancel_requested'])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('cancelled', run['status'])
        # the pass that saw the cancel launched no regeneration (it used to, and cancel it a pass later)
        self.assertEqual(['n0-a0'], [a['id'] for a in run['nodes'][0]['attempts']])
        self.assertEqual(1, len(self.hub.calls))

    def test_resume_after_an_interrupted_coordinator_relaunches_only_the_recorded_intent(self):
        run_id = self.submit([self.statement('app.py')])
        with patch.object(self.tasks, 'submit', side_effect=RuntimeError('store went away')):
            self.auto._worker(run_id)                    # the background loop records the interruption
        run = self.auto.get(run_id)
        self.assertEqual('unknown', run['status'])
        self.assertEqual('Coordinator interrupted: RuntimeError: store went away. Inspect the attempts before resuming.',
                         run['error'])
        self.assertEqual(('queued', ''), (run['nodes'][0]['attempts'][0]['status'], run['nodes'][0]['attempts'][0]['task_id']))
        self.assertFalse(self.auto.advance(run_id))      # unknown is terminal until the operator resumes

        resumed = self.auto.control(run_id, 'resume')['run']
        self.assertEqual(('queued', ''), (resumed['status'], resumed['error']))
        self.assertEqual('operator', resumed['resumed']['by'])
        self.assertEqual('resumed', self.names(run_id)[-1])
        self.assertTrue(self.auto.advance(run_id))
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('running', 'run-1:n0-a0'), (attempt['status'], attempt['request_id']))
        self.assertNotIn('body', attempt)
        self.assertEqual(1, len(self.tasks.listing()))
        self.assertEqual(1, self.auto.get(run_id)['budget']['agents_started'])
        self.assertIn('launch_recovered', self.names(run_id))


class Recovery(Harness):
    def test_a_restarted_coordinator_launches_nothing_new_and_keeps_observing(self):
        run_id = self.submit([self.statement('app.py')], candidates=2)
        self.auto.advance(run_id)
        for attempt in self.attempts(run_id, 'n0'):
            self.launch(attempt)
        tasks = self.make_tasks()
        auto = self.make_auto(tasks)
        self.assertTrue(auto.advance(run_id))
        self.assertTrue(auto.advance(run_id))
        self.assertEqual(2, len(self.hub.calls))
        self.assertEqual(2, len(tasks.listing()))
        self.assertEqual(2, auto.get(run_id)['budget']['agents_started'])
        # the second identical wait neither appends an event nor rewrites the record (item 10)
        self.assertEqual(['launched', 'decision'], self.names(run_id)[-2:])
        self.assertEqual('wait', self.events(run_id)[-1]['action'])

        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(self.attempts(run_id, 'n0')[0])
        self.assertFalse(auto.advance(run_id))
        self.assertEqual('completed', auto.get(run_id)['status'])

    def test_a_crash_between_reservation_and_record_adopts_the_reserved_task(self):
        run_id = self.submit([self.statement('app.py')])
        real = self.tasks.submit

        def reserve_then_die(body):
            real(body)
            raise RuntimeError('coordinator died after the reservation')
        with patch.object(self.tasks, 'submit', side_effect=reserve_then_die):
            with self.assertRaises(RuntimeError):
                self.auto.advance(run_id)
        reserved = self.tasks.listing()
        self.assertEqual(1, len(reserved))
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('queued', ''), (attempt['status'], attempt['task_id']))

        auto = self.make_auto(self.make_tasks())
        self.assertTrue(auto.advance(run_id))
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('running', reserved[0]['id'], True), (attempt['status'], attempt['task_id'], attempt['duplicate']))
        self.assertEqual(1, len(self.tasks.listing()))
        self.assertEqual(1, auto.get(run_id)['budget']['agents_started'])
        recovered = [e for e in self.events(run_id) if e['event'] == 'launch_recovered']
        self.assertEqual([('n0-a0', reserved[0]['id'], True)], [(e['attempt'], e['task'], e['duplicate']) for e in recovered])
        self.launch(attempt)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(attempt)
        self.assertFalse(auto.advance(run_id))
        self.assertEqual('completed', auto.get(run_id)['status'])


class Budget(Harness):
    def test_agents_max_refuses_further_launches_and_fails_the_run(self):
        run_id = self.submit([self.statement('app.py'), self.statement('lib.py')], candidates=2, regenerate=0, agents_max=2)
        self.auto.advance(run_id)
        a0, a1 = self.attempts(run_id, 'n0')
        self.launch(a0)
        self.launch(a1)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(a0)
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual('accepted', self.node(run_id, 'n0')['status'])

        row = self.auto._read(run_id)
        self.assertIsNone(self.auto._launch(row, row['nodes'][1], kind='candidate', strategy='fresh'))
        refused = self.events(run_id)[-1]
        self.assertEqual(('launch_refused', 'n1', 'agents_max reached'), (refused['event'], refused['node'], refused['reason']))

        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(('failed', 'Statement n1 failed: budget or deadline exhausted before the first attempt'),
                         (run['status'], run['error']))
        self.assertEqual([], run['nodes'][1]['attempts'])
        self.assertEqual(2, len(self.hub.calls))
        self.assertEqual(2, len(self.tasks.listing()))

    def test_a_passed_deadline_fails_the_next_statement(self):
        run_id = self.submit([self.statement('app.py'), self.statement('lib.py')], wall_seconds=300)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(attempt)
        self.assertTrue(self.auto.advance(run_id))
        self.clock.advance(300)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(('failed', 'Statement n1 failed: budget or deadline exhausted before the first attempt'),
                         (run['status'], run['error']))
        self.assertEqual(1, len(self.hub.calls))

    def test_a_passed_deadline_bounds_a_running_attempt(self):
        run_id = self.submit([self.statement('app.py')], wall_seconds=300, attempt_seconds=3600)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.clock.advance(299)
        self.assertTrue(self.auto.advance(run_id))
        self.assertEqual('running', self.attempts(run_id, 'n0')[0]['status'])
        self.clock.advance(1)
        self.assertTrue(self.auto.advance(run_id))       # the wall deadline cancels it, not attempt_seconds
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'TIMEOUT'), (seen['status'], seen['failure']))
        self.assertTrue(self.tasks.get(attempt['task_id'])['cancel_requested'])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(('failed', 'Statement n0 failed: budget or deadline exhausted'), (run['status'], run['error']))
        self.assertEqual(1, len(self.hub.calls))


class Final(Harness):
    COMMAND = 'python3 -m unittest discover -s tests'

    def run_to_final(self, rc, out):
        self.results[self.COMMAND] = {'rc': rc, 'out': out}
        run_id = self.submit([self.statement('app.py')], final=[self.COMMAND])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        final = [r for r in self.runs if r['argv'] == self.COMMAND]
        self.assertEqual([(self.cwd, True)], [(r['cwd'], r['shell']) for r in final])
        return self.auto.get(run_id)

    def test_a_passing_final_completes_the_run(self):
        run = self.run_to_final(0, 'OK')
        self.assertEqual('completed', run['status'])
        self.assertEqual({'checks': [{'kind': 'final', 'command': self.COMMAND, 'passed': True, 'output': 'OK'}],
                          'passed': True}, run['final'])
        self.assertEqual(['promoted', 'node_accepted', 'completed'], self.names(run['id'])[-3:])

    def test_a_failing_final_fails_the_run_naming_the_command(self):
        run = self.run_to_final(1, 'FAILED (failures=1)')
        self.assertEqual(('failed', 'Every statement was accepted, but a final check failed: ' + self.COMMAND),
                         (run['status'], run['error']))
        self.assertFalse(run['final']['passed'])
        self.assertEqual('accepted', run['nodes'][0]['status'])
        self.assertEqual('final_failed', self.names(run['id'])[-1])


class Gated(Harness):
    def test_a_gate_without_positive_evidence_waits_until_the_turn_really_ends(self):
        # D14: the gate below was entered because the foreground was unrecognised and no adapter
        # exists, not because the turn ended; it used to be verified and closed mid-turn.
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.hub.turn = 'python3'                        # no native adapter and an unrecognised foreground
        self.evidence[agent] = {'available': False, 'done': False, 'reason': 'no native completion adapter'}
        self.write('app.py', 'def main():\n    return 1\n')
        self.tasks.advance(attempt['task_id'])
        step = self.tasks.get(attempt['task_id'])['steps'][0]
        self.assertEqual('awaiting_review', step['status'])
        self.assertNotIn('running', step)
        self.assertNotIn('evidence', step)
        self.assertTrue(self.auto.advance(run_id))       # no positive evidence: keep waiting
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('running', None), (seen['status'], seen['verdict']))
        self.assertNotIn('close', seen)
        self.assertEqual([], self.hub.actions)
        self.assertEqual('awaiting_review', self.tasks.get(attempt['task_id'])['steps'][0]['status'])

        self.hub.turn = 'bash'                           # the agent process exits: evidence is captured
        self.tasks.advance(attempt['task_id'])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual('accepted', run['nodes'][0]['attempts'][0]['status'])
        step = self.tasks.get(attempt['task_id'])['steps'][0]
        self.assertEqual(('completed', 'auto_next'), (step['status'], step['completion']['kind']))
        self.assertIn(agent, self.hub.stops)
        self.assertEqual([('commit', agent), ('apply', agent)], self.hub.actions)

    def test_a_gated_child_whose_claim_the_disk_refutes_is_cancelled(self):
        run_id = self.submit([self.statement('app.py')], regenerate=0)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.hub.turn = 'bash'                           # the agent exited back to its shell
        self.hub.screen_text = 'Done: created 1 file and all 4 tests passed.'
        self.tasks.advance(attempt['task_id'])
        step = self.tasks.get(attempt['task_id'])['steps'][0]
        self.assertEqual('awaiting_review', step['status'])
        self.assertTrue(step['evidence']['warning'])
        self.assertFalse(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'CLAIM_MISMATCH'), (seen['status'], seen['failure']))
        self.assertEqual(['exists', 'syntax', 'change', 'claim'], [c['kind'] for c in seen['verdict']['checks']])
        self.assertTrue(self.tasks.get(attempt['task_id'])['cancel_requested'])
        self.tasks.advance(attempt['task_id'])
        self.assertEqual('cancelled', self.tasks.get(attempt['task_id'])['status'])
        self.assertIn(agent, self.hub.stops)
        self.assertEqual([], self.hub.actions)
        self.assertEqual('failed', self.auto.get(run_id)['status'])


class API(Harness):
    class Handler:
        def __init__(self, owner=True):
            self.owner, self.result, self.code, self.query = owner, None, None, {}

        def require_owner(self, *_):
            return self.owner

        def send_json(self, value, status=200):
            self.result, self.code = value, status

        def get_query_param(self, name):
            return self.query.get(name)

    def test_the_operator_gate_precedes_engine_initialization(self):
        from integration.host import symblicos_engine as symblicos_engine
        for method, path in (('GET', '/api/symblicos/autogen'), ('GET', '/api/symblicos/autogen/catalog'),
                             ('POST', '/api/symblicos/autogen/start'), ('POST', '/api/symblicos/autogen/control')):
            with self.subTest(path=path), \
                    patch.object(symblicos_engine, 'get_engine', side_effect=AssertionError('must not initialize')):
                handler = self.Handler(owner=False)
                self.assertTrue(symblicos_engine.handle(handler, method, path, {}))
                self.assertIsNone(handler.result)

    def test_http_contract_start_list_get_catalog_and_control(self):
        from integration.host import symblicos_engine as symblicos_engine
        from symblic.os.terminal_server import SymblicOSTerminalEngine
        engine = SymblicOSTerminalEngine(str(self.root))
        tasks = TaskManager(engine.paths['root'], hub=self.hub, background=False, completion=self.completion,
                            check_host=lambda: None)
        built = []

        def factory(root, *, task_runner=None):
            built.append((root, task_runner))
            return AutogenManager(root, task_runner=task_runner, background=False, check_host=lambda: None,
                                  check_runner=self.runner, listing=self.listing, clock=self.clock)
        handler = self.Handler()

        def call(method, route, data=None, **query):
            handler.query = query
            self.assertTrue(symblicos_engine.handle(handler, method, '/api/symblicos/' + route, data or {}))
            return handler.code, handler.result
        with patch.object(symblicos_engine, 'get_engine', return_value=engine), \
                patch.object(symblicos_engine, 'TaskManager', return_value=tasks), \
                patch.object(symblicos_engine, 'host_check'), \
                patch('symblic.autogen.coordinator.AutogenManager', side_effect=factory):
            code, result = call('GET', 'autogen/catalog')
            self.assertEqual(200, code)
            self.assertEqual({'version', 'limits', 'defaults', 'strategies', 'all_strategies', 'failure_classes', 'handoff_file',
                              'checkpoint_file'}, set(result))
            self.assertEqual(list(POLICY.WIRED_STRATEGIES), result['strategies'])
            self.assertEqual(list(POLICY.STRATEGIES), result['all_strategies'])
            self.assertEqual(POLICY.CHECKPOINT_FILE, result['checkpoint_file'])
            self.assertEqual(json.loads(json.dumps(POLICY.LIMITS)), json.loads(json.dumps(result['limits'])))

            body = self.body([self.statement('app.py')], 'api-1', candidates=2)
            code, result = call('POST', 'autogen/start', body)
            self.assertEqual(200, code)
            self.assertFalse(result['duplicate'])
            run_id = result['run']['id']
            self.assertEqual([], self.hub.calls)
            code, result = call('POST', 'autogen/start', body)
            self.assertEqual((200, True, run_id), (code, result['duplicate'], result['run']['id']))
            code, result = call('POST', 'autogen/start', self.body([self.statement('app.py')], 'api-1'))
            self.assertEqual(409, code)
            self.assertIn('different', result['error'])
            code, result = call('POST', 'autogen/start', {**body, 'client_request_id': 'api-2', 'engine': 'gemini'})
            self.assertEqual((400, {'error': 'Choose an engine the task runner offers.'}), (code, result))

            factory(engine.paths['root'], task_runner=HubTaskRunner(tasks)).advance(run_id)
            code, result = call('GET', 'autogen')
            self.assertEqual(200, code)
            self.assertEqual([run_id], [r['id'] for r in result['runs']])
            code, result = call('GET', 'autogen/get', id=run_id, tasks='1')
            self.assertEqual(200, code)
            ids = [a['task_id'] for a in result['run']['nodes'][0]['attempts']]
            self.assertEqual(sorted(ids), sorted(result['run']['tasks']))
            self.assertEqual('active', result['run']['status'])
            self.assertEqual('active', result['run']['summary']['status'])
            code, result = call('GET', 'autogen/get', id=run_id)
            self.assertNotIn('tasks', result['run'])
            code, result = call('GET', 'autogen/get', id='autogen-' + '0' * 24)
            self.assertEqual((404, {'error': 'Unknown autogen run id.'}), (code, result))
            code, result = call('GET', 'autogen/get', id='../../etc')
            self.assertEqual(404, code)

            code, result = call('POST', 'autogen/control', {'id': run_id, 'action': 'pause'})
            self.assertEqual((400, {'error': 'Choose cancel or resume.'}), (code, result))
            code, result = call('POST', 'autogen/control', {'id': run_id, 'action': 'cancel'})
            self.assertEqual(200, code)
            self.assertTrue(result['run']['cancel_requested'])
            factory(engine.paths['root'], task_runner=HubTaskRunner(tasks)).advance(run_id)
            code, result = call('GET', 'autogen/get', id=run_id)
            self.assertEqual('cancelled', result['run']['status'])
        self.assertTrue(built)
        self.assertTrue(all(root == engine.paths['root'] and runner.tasks is tasks for root, runner in built))
        self.assertTrue(str(self.root) in str(engine.paths['root']))




class ParentVerdict(Decomposition):
    """A split statement is accepted only when its own checks pass in the promoted workspace."""

    def split_and_accept_children(self, run_id):
        self.auto.advance(run_id)                        # first wave launches
        planner = self.fail_first_wave(run_id)
        self.launch(planner)
        self.write(POLICY.SPLIT_FILE,
                   f'Create the file alpha.py in the folder {self.cwd} with a function named alpha.\n'
                   f'Create the file beta.py in the folder {self.cwd} with a function named beta.\n')
        self.finish(planner)
        self.assertTrue(self.auto.advance(run_id))
        for child_id, name in (('n0.0', 'alpha.py'), ('n0.1', 'beta.py')):
            self.assertTrue(self.auto.advance(run_id))
            attempt = self.attempts(run_id, child_id)[0]
            self.launch(attempt)
            self.write(name, 'def f():\n    return 1\n')
            self.finish(attempt)
            self.auto.advance(run_id)                    # the last child's pass may also settle the parent
            self.assertEqual('accepted', self.node(run_id, child_id)['status'])

    def test_parent_checks_run_in_the_project_workspace_after_the_children(self):
        run_id = self.submit([self.parent()], candidates=1, regenerate=0, depth=1,
                             checks={'0': ['grep -q alpha alpha.py']})
        self.split_and_accept_children(run_id)
        self.assertFalse(self.auto.advance(run_id))      # the parent's own checks pass: run completes
        node = self.node(run_id, 'n0')
        self.assertEqual(('accepted', 'children'), (node['status'], node['winner']))
        self.assertEqual([('exists', 'alpha.py'), ('syntax', 'alpha.py'), ('exists', 'beta.py'), ('syntax', 'beta.py'),
                          ('command', 'grep -q alpha alpha.py')],
                         [(c['kind'], c.get('file') or c.get('command')) for c in node['parent_verdict']['checks']])
        self.assertTrue(node['parent_verdict']['passed'])
        parent_runs = [r for r in self.runs if r['argv'] == 'grep -q alpha alpha.py']
        # once by the first-wave attempt (its own verdict), once by the parent verdict in the project folder
        self.assertEqual([self.cwd, self.cwd], [r['cwd'] for r in parent_runs])
        self.assertEqual('completed', self.auto.get(run_id)['status'])
        self.assertIn('node_accepted', self.names(run_id))

    def test_children_passing_cannot_accept_a_parent_whose_own_check_fails(self):
        run_id = self.submit([self.parent()], candidates=1, regenerate=0, depth=1,
                             checks={'0': ['grep -q gamma alpha.py']})
        self.results['grep -q gamma alpha.py'] = {'rc': 1, 'out': ''}
        self.split_and_accept_children(run_id)
        self.assertFalse(self.auto.advance(run_id))
        node = self.node(run_id, 'n0')
        self.assertEqual('failed', node['status'])
        self.assertFalse(node['parent_verdict']['passed'])
        self.assertIn('parent checks failed', node['error'])
        run = self.auto.get(run_id)
        self.assertEqual('failed', run['status'])
        self.assertIn('n0', run['error'])
        self.assertEqual(['accepted', 'accepted'], [self.node(run_id, c)['status'] for c in ('n0.0', 'n0.1')])
        self.assertEqual(4, run['budget']['agents_started'])     # nothing launched after the parent verdict


# ------------------------------------------------------------------------------ review findings (2026-10-10)

class Crash(BaseException):
    """A process death at an exact point: nothing in the coordinator catches BaseException."""


class CheckoutHub(FakeHub):
    """The host hub's own-checkout contract: a worktree start runs the agent in a checkout beside the
    project (<repo>.agents/<name>-<stamp> on the original host) and reports it in agent['git']."""

    def __init__(self, workspace, checkouts, filler=0):
        super().__init__(workspace)
        self.checkouts = checkouts
        self.filler = filler

    def start(self, options, group=''):
        result = super().start(options, group)
        agent = result['agent']
        if options.get('worktree'):
            wt = os.path.join(self.checkouts, 'wt-' + agent['id'])
            os.makedirs(wt)
            for i in range(self.filler):
                Path(wt, f'a{i:04d}.txt').write_text('x')
            agent['cwd'] = wt
            agent['git'] = {'worktree': wt, 'cwd': wt, 'branch': 'agents/a-' + agent['id'], 'base_sha': 'b' * 40,
                            'main_root': self.workspace}
        return result


class OwnCheckout(Harness):
    def setUp(self):
        super().setUp()
        self.checkouts = Path(self.tmp.name) / 'project.agents'
        self.checkouts.mkdir()
        self.hub = CheckoutHub(self.cwd, str(self.checkouts))
        self.tasks = self.make_tasks()
        self.auto = self.make_auto()

    def checkout(self, attempt):
        return self.tasks.get(attempt['task_id'])['steps'][0]['agent']['cwd']

    def test_attempts_are_told_their_checkout_and_verified_there(self):
        # D6: the prompt named the project folder while the verdict read the checkout
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        task = self.tasks.get(attempt['task_id'])
        self.assertNotIn(self.cwd, task['instruction'])
        self.assertIn('Create the file app.py in ' + POLICY.WORKING_FOLDER, task['instruction'])
        self.assertTrue(task['context_note'].startswith(POLICY.CHECKOUT_LOCK))
        self.assertEqual((self.cwd, True), (task['options']['cwd'], task['options']['worktree']))
        agent = self.launch(attempt)
        wt = self.checkout(attempt)
        self.assertNotEqual(self.cwd, wt)
        Path(wt, 'app.py').write_text('def main():\n    return 1\n')
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(wt, run['nodes'][0]['attempts'][0]['workspace'])
        self.assertEqual([wt], [r['cwd'] for r in self.runs if not r['shell']])
        self.assertFalse((self.project / 'app.py').exists())       # only the hub's apply touches the project
        self.assertEqual([('commit', agent), ('apply', agent)], self.hub.actions)

    def test_a_handoff_successor_continues_in_its_predecessors_checkout(self):
        # item 5: a successor in a fresh checkout found none of the partial files
        statement = self.statement('big.py', 'with ten numbered functions')
        run_id = self.submit([statement], generations=2)
        self.results['big.py'] = {'rc': 1, 'out': 'SyntaxError: unexpected EOF'}
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        agent0 = self.launch(first)
        wt = self.checkout(first)
        Path(wt, 'big.py').write_text('def f1():\n')
        Path(wt, POLICY.CHECKPOINT_FILE).write_text(json.dumps({'version': 1, 'done': ['f1'], 'left': ['f2 to f10'], 'files': ['big.py']}))
        self.finish(first)
        self.assertTrue(self.auto.advance(run_id))
        seen, successor = self.attempts(run_id, 'n0')
        self.assertEqual('handoff', seen['status'])
        options = self.tasks.get(successor['task_id'])['options']
        self.assertEqual((wt, False), (options['cwd'], options['worktree']))
        self.assertEqual(agent0, successor['checkout_agent'])
        self.launch(successor)
        self.assertEqual(wt, self.checkout(successor))
        Path(wt, 'big.py').write_text('def f1():\n    return 1\n')
        self.results['big.py'] = {'rc': 0, 'out': ''}
        self.finish(successor)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])
        # the checkout belongs to the first agent: promotion goes through it
        self.assertEqual([('commit', agent0), ('apply', agent0)], self.hub.actions)

    def test_a_truncated_inventory_falls_back_to_the_checkouts_git_state(self):
        # item 2: the task engine's 200-file inventory misses a late file; git does not
        self.hub.filler = 210
        changed = {'out': 'zz.py\0'}

        def git(argv, cwd, timeout=120):
            self.runs.append({'argv': argv, 'cwd': cwd, 'shell': False, 'timeout': timeout, 'git': True})
            if argv[3] == 'diff':
                return {'rc': 0, 'out': changed['out']}
            return {'rc': 0, 'out': ''}
        auto = self.make_auto(git=git)
        for request, out, expected in (('git-yes', 'zz.py\0', 'accepted'), ('git-no', 'a0001.txt\0', 'failed')):
            with self.subTest(request=request):
                changed['out'] = out
                run_id = auto.submit(self.body([self.statement('zz.py')], request, regenerate=0))['run']['id']
                auto.advance(run_id)
                attempt = [a for n in auto.get(run_id)['nodes'] for a in n['attempts']][0]
                self.launch(attempt)
                Path(self.checkout(attempt), 'zz.py').write_text('x = 1\n')
                self.finish(attempt)
                self.assertTrue(self.tasks.get(attempt['task_id'])['steps'][0]['evidence']['inventory']['truncated'])
                auto.advance(run_id)
                seen = auto.get(run_id)['nodes'][0]['attempts'][0]
                self.assertEqual(expected, seen['status'])
                if expected == 'failed':
                    self.assertEqual('NO_OUTPUT', seen['failure'])
                    self.assertIn(('change', 'zz.py'), [(c['kind'], c.get('file')) for c in seen['verdict']['checks']])


class PerpetualFindings(Harness):
    def test_perpetual_lane_runs_every_generation(self):
        # review test 1 (D1): a passing generation used to end the lane as the node's winner
        statement = f'Monitor the folder {self.cwd} and record new findings in the file log.md for each batch.'
        run_id = self.submit([statement], perpetual=True, generations=3, interval_seconds=60, require_change=False)
        for generation in range(1, 4):
            self.assertTrue(self.auto.advance(run_id))
            attempt = self.attempts(run_id, 'n0')[-1]
            self.assertEqual(('perpetual', generation), (attempt['kind'], attempt['generation']))
            if generation == 3:
                self.assertIn('Earlier done: batch 1; batch 2.', self.tasks.get(attempt['task_id'])['instruction'])
            self.launch(attempt)
            self.write('log.md', f'# batch {generation}\n')
            self.checkpoint([f'batch {i}' for i in range(1, generation + 1)], [f'batch {generation + 1}'], ['log.md'])
            self.finish(attempt)
            keep = self.auto.advance(run_id)
            self.assertEqual(generation < 3, keep)
            self.clock.advance(61)
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual(['generation_done'] * 3, [a['status'] for a in run['nodes'][0]['attempts']])
        self.assertEqual(('accepted', 'generations', 3), (run['nodes'][0]['status'], run['nodes'][0]['winner'],
                                                          run['nodes'][0]['generation']))
        self.assertEqual(3, run['budget']['agents_started'])
        self.assertEqual(6, len(self.hub.actions))                 # commit + apply per generation

    def test_a_failed_generation_never_moves_the_cursor_and_waits_stay_quiet(self):
        # item 6: the cursor came from the last attempt, even a failed one; every wait poll logged
        command = 'grep -q batch index.md'
        statement = f'Index the notes in the folder {self.cwd} and write the summary to index.md for each batch.'
        run_id = self.submit([statement], perpetual=True, generations=3, interval_seconds=60, regenerate=2,
                             checks={'0': [command]})
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.launch(first)
        self.write('index.md', '# batch 1\n')
        self.checkpoint(['batch 1'], ['batch 2'], ['index.md'])
        self.finish(first)
        self.assertTrue(self.auto.advance(run_id))
        record = self.root / 'state' / 'autogen' / (run_id + '.json')
        events, written = len(self.events(run_id)), record.read_text()
        for _ in range(3):
            self.clock.advance(5)
            self.assertTrue(self.auto.advance(run_id))
        self.assertEqual(events, len(self.events(run_id)))         # no event per poll
        self.assertEqual(written, record.read_text())              # and no record rewrite
        seconds = self.auto._sleep_seconds(self.auto._read(run_id))
        self.assertTrue(44 <= seconds <= 46, seconds)               # the worker sleeps until the interval ends

        self.clock.advance(45)
        self.assertTrue(self.auto.advance(run_id))
        second = self.attempts(run_id, 'n0')[1]
        self.launch(second)
        self.checkpoint(['batch 1', 'batch 2', 'batch 3'], ['batch 4'], ['index.md'])
        self.results[command] = {'rc': 1, 'out': ''}
        self.finish(second)
        self.assertTrue(self.auto.advance(run_id))
        failed = self.attempts(run_id, 'n0')[1]
        self.assertEqual(('failed', 'CHECK_FAILURE'), (failed['status'], failed['failure']))
        self.assertNotIn('checkpoint', failed)
        self.clock.advance(61)
        self.assertTrue(self.auto.advance(run_id))
        third = self.attempts(run_id, 'n0')[2]
        instruction = self.tasks.get(third['task_id'])['instruction']
        self.assertEqual(2, third['generation'])
        self.assertIn('Earlier done: batch 1.', instruction)
        self.assertIn('Cursor: batch 2.', instruction)


class LaunchSafety(Harness):
    def test_cancel_during_a_submit_survives_and_stops_the_rest_of_the_wave(self):
        # review test 3 (D3, crash-safety 7b): the pass's write used to erase the cancel
        run_id = self.submit([self.statement('app.py')], candidates=2)
        real = self.tasks.submit

        def cancel_then_submit(body):
            if not self.auto._read(run_id).get('cancel_requested'):
                self.auto.control(run_id, 'cancel')
            return real(body)
        with patch.object(self.tasks, 'submit', side_effect=cancel_then_submit):
            self.assertTrue(self.auto.advance(run_id))
        run = self.auto._read(run_id)
        self.assertTrue(run['cancel_requested'])
        a0, a1 = run['nodes'][0]['attempts']
        self.assertEqual('running', a0['status'])
        self.assertEqual(('failed', 'CANCELLED', ''), (a1['status'], a1['failure'], a1['task_id']))
        self.assertEqual(1, len(self.tasks.listing()))           # the second intent was never submitted
        seqs = [e['seq'] for e in self.events(run_id)]
        self.assertEqual(list(range(1, len(seqs) + 1)), seqs)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('cancelled', self.auto.get(run_id)['status'])
        self.assertTrue(self.tasks.get(a0['task_id'])['cancel_requested'])

    def test_every_first_wave_intent_is_durable_before_the_first_submit(self):
        # crash-safety 7a: a crash after the first of three submits shrank the wave to one
        run_id = self.submit([self.statement('app.py')], candidates=3)
        with patch.object(self.tasks, 'submit', side_effect=Crash()):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        attempts = self.attempts(run_id, 'n0')
        self.assertEqual([('queued', '')] * 3, [(a['status'], a['task_id']) for a in attempts])
        self.assertEqual(3, self.auto.get(run_id)['budget']['agents_started'])
        auto = self.make_auto(self.make_tasks())
        self.assertTrue(auto.advance(run_id))
        self.assertEqual(['running'] * 3, [a['status'] for a in self.attempts(run_id, 'n0')])
        self.assertEqual(3, len(self.tasks.listing()))
        self.assertEqual(3, self.names(run_id).count('launch_recovered'))

    def test_a_long_request_id_still_launches(self):
        # crash-safety: '<160 chars>:n0-a0' exceeded the task engine's limit on every launch
        run_id = self.auto.submit(self.body([self.statement('app.py')], 'r' * 160))['run']['id']
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual('running', attempt['status'])
        self.assertEqual(run_id + ':n0-a0', attempt['request_id'])
        self.assertLessEqual(len(attempt['request_id']), 160)

    def test_event_seq_stays_gap_free_across_a_crash_between_event_and_record(self):
        # D16 / item 10: the log reused seq numbers after such a crash
        run_id = self.submit([self.statement('app.py')])
        with self.auto._lock(run_id):
            self.auto._event(self.auto._read(run_id), 'decision', node='n0', action='launch')   # record never written
        self.assertEqual(0 + 1, self.auto._read(run_id)['seq'])
        self.assertTrue(self.make_auto().advance(run_id))
        seqs = [e['seq'] for e in self.events(run_id)]
        self.assertEqual(list(range(1, len(seqs) + 1)), seqs)
        self.assertEqual(seqs[-1], self.auto._read(run_id)['seq'])


class CancelSafety(Harness):
    def test_cancel_works_on_an_unknown_run_and_an_interrupted_pass_stops_children(self):
        # crash-safety 7c: cancel returned early on 'unknown'; the exception path left children running
        run_id = self.submit([self.statement('app.py')], candidates=2)
        self.auto.advance(run_id)
        attempts = self.attempts(run_id, 'n0')
        for attempt in attempts:
            self.launch(attempt)
        with patch.object(self.auto, '_sweep', side_effect=RuntimeError('boom')):
            self.auto._worker(run_id)
        run = self.auto.get(run_id)
        self.assertEqual('unknown', run['status'])
        self.assertEqual([('failed', 'CANCELLED')] * 2, [(a['status'], a['failure']) for a in run['nodes'][0]['attempts']])
        for attempt in attempts:
            self.assertTrue(self.tasks.get(attempt['task_id'])['cancel_requested'])

        other = self.submit([self.statement('lib.py')], 'run-2')
        self.auto.advance(other)
        live = self.attempts(other, 'n0')[0]
        with self.auto._mutate(other) as row:
            row.update(status='unknown', error='simulated')
        self.assertTrue(self.auto.control(other, 'cancel')['run']['cancel_requested'])
        self.assertFalse(self.auto.advance(other))
        self.assertEqual('cancelled', self.auto.get(other)['status'])
        self.assertTrue(self.tasks.get(live['task_id'])['cancel_requested'])

    def test_an_intent_without_a_task_id_is_cancelled_through_its_deterministic_task(self):
        # crash-safety 7d: the reserved task escaped cancellation and launched later
        run_id = self.submit([self.statement('app.py')])
        real = self.tasks.submit

        def reserve_then_die(body):
            real(body)
            raise Crash()
        with patch.object(self.tasks, 'submit', side_effect=reserve_then_die):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        reserved = self.tasks.listing()[0]
        self.auto.control(run_id, 'cancel')
        self.assertFalse(self.make_auto().advance(run_id))
        attempt = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'CANCELLED'), (attempt['status'], attempt['failure']))
        self.assertNotIn('body', attempt)
        self.assertTrue(self.tasks.get(reserved['id'])['cancel_requested'])
        self.tasks.advance(reserved['id'])
        self.assertEqual('cancelled', self.tasks.get(reserved['id'])['status'])
        self.assertEqual([], self.hub.calls)

    def test_a_refused_cancel_keeps_the_attempt_in_its_slot(self):
        # crash-safety 7e: a swallowed TaskError recorded TIMEOUT and regenerated beside a live agent
        run_id = self.submit([self.statement('app.py')], attempt_seconds=120)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.clock.advance(121)
        from symblic.autogen.runner import TaskError
        with patch.object(self.tasks, 'control', side_effect=TaskError('Task receipt is invalid; execution is fenced.', 409)):
            self.assertTrue(self.auto.advance(run_id))
            self.assertTrue(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')
        self.assertEqual(1, len(seen))
        self.assertEqual('running', seen[0]['status'])
        self.assertTrue(seen[0]['timeout_requested'])
        self.assertIn('fenced', seen[0]['cancel_failed'])
        self.assertEqual(1, self.names(run_id).count('cancel_failed'))
        self.assertEqual(1, len(self.hub.calls))
        self.assertTrue(self.auto.advance(run_id))                 # control works again: settle, then regenerate
        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(('failed', 'TIMEOUT'), (a0['status'], a0['failure']))
        self.assertNotIn('cancel_failed', a0)
        self.assertEqual('other_node', a1['strategy'])

    def test_a_refused_cancel_whose_task_then_finishes_leaves_no_loose_end(self):
        from symblic.autogen.runner import TaskError
        run_id = self.submit([self.statement('app.py')], attempt_seconds=120)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.clock.advance(121)
        with patch.object(self.tasks, 'control', side_effect=TaskError('fenced', 409)):
            self.assertTrue(self.auto.advance(run_id))
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(attempt)                                   # the agent finished after all
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertNotIn('cancel_pending', run['nodes'][0]['attempts'][0])

    def test_a_crash_mid_timeout_still_reads_timeout(self):
        # D17: the cancelled task was re-observed as CANCELLED after such a crash
        run_id = self.submit([self.statement('app.py')], attempt_seconds=120)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.clock.advance(121)
        real = self.tasks.control

        def cancel_then_die(task_id, action):
            real(task_id, action)
            raise Crash()
        with patch.object(self.tasks, 'control', side_effect=cancel_then_die):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        self.assertEqual('running', self.attempts(run_id, 'n0')[0]['status'])
        self.tasks.advance(attempt['task_id'])
        self.assertEqual('cancelled', self.tasks.get(attempt['task_id'])['status'])
        self.assertTrue(self.make_auto().advance(run_id))
        self.assertEqual(('failed', 'TIMEOUT'), (self.attempts(run_id, 'n0')[0]['status'], self.attempts(run_id, 'n0')[0]['failure']))


class ObservationSafety(Harness):
    def test_an_unknown_child_task_makes_the_run_unknown_without_a_regeneration(self):
        # item 1 / crash-safety: an unknown task was classified UNKNOWN and regenerated (a replay)
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.write('app.py', 'def main():\n    return 1\n')

        def stop_fails(agent_id):
            raise RuntimeError('tmux did not answer')
        self.hub.stop = stop_fails
        self.evidence[agent] = {'available': True, 'done': True, 'kind': 'native_turn'}
        self.tasks.advance(attempt['task_id'])
        self.assertEqual('unknown', self.tasks.get(attempt['task_id'])['status'])
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('unknown', run['status'])
        self.assertIn('Inspect it with your task runner', run['error'])
        self.assertEqual('unknown', run['nodes'][0]['attempts'][0]['status'])
        self.assertEqual([], self.hub.actions)                     # never promoted
        self.assertEqual(1, len(self.hub.calls))                   # never regenerated
        self.assertEqual(['attempt_unknown', 'run_unknown'], self.names(run_id)[-2:])
        self.auto.control(run_id, 'resume')
        self.assertFalse(self.auto.advance(run_id))                # still unknown: it stays the operator's
        self.assertEqual(1, len(self.hub.calls))

    def test_a_failed_task_with_a_vacuous_plan_is_never_accepted(self):
        # item 1 / unknown-7: no named files and no checks meant all([]) == True
        statement = f'Research the notes in the folder {self.cwd} and summarize the open questions for the operator.'
        run_id = self.submit([statement], regenerate=0)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]

        class Refused(Exception):
            refused = True
        self.hub.error = Refused('The agent refused its own launch: no')
        self.tasks.advance(attempt['task_id'])
        self.assertEqual('failed', self.tasks.get(attempt['task_id'])['status'])
        self.assertFalse(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'REFUSAL'), (seen['status'], seen['failure']))
        self.assertEqual([], self.hub.actions)

    def test_transient_task_read_errors_leave_the_attempt_running(self):
        # crash-safety: any TaskError failed the attempt while its agent kept running
        from symblic.autogen.runner import TaskError
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        with patch.object(self.tasks, 'get', side_effect=TaskError('Task receipt is unreadable; execution is fenced.', 409)):
            self.assertTrue(self.auto.advance(run_id))
        self.assertEqual('running', self.attempts(run_id, 'n0')[0]['status'])
        with patch.object(self.tasks, 'get', side_effect=TaskError('Task not found.', 404)):
            self.auto.advance(run_id)
        self.assertEqual(('failed', 'UNKNOWN'), (self.attempts(run_id, 'n0')[0]['status'], self.attempts(run_id, 'n0')[0]['failure']))

    def test_running_child_tasks_are_reattached_through_the_task_engine(self):
        # crash-safety: child coordinators stranded by a restart were never resumed
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        with patch.object(self.tasks, '_resume_stranded') as resume:
            self.assertTrue(self.auto.advance(run_id))
        self.assertEqual([attempt['task_id']], [c.args[0]['id'] for c in resume.call_args_list])

    def test_a_noop_edit_is_refused(self):
        # item 2: an Extend statement on an existing file passed when only HANDOFF.md changed
        self.write('app.py', 'def main():\n    return 1\n')
        statement = f'Extend the file app.py in the folder {self.cwd} with a function stop, keeping every existing part.'
        run_id = self.submit([statement], regenerate=0)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.write(POLICY.HANDOFF_FILE, 'Done\n')
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'NO_OUTPUT'), (seen['status'], seen['failure']))
        self.assertEqual([('exists', True), ('syntax', True), ('change', False)],
                         [(c['kind'], c['passed']) for c in seen['verdict']['checks']])
        self.assertEqual(0, seen['verdict']['files_changed'])     # control files never count

    def test_delete_statement_passes_when_the_file_is_gone(self):
        # item 3
        self.write('old.js', 'x\n')
        run_id = self.submit([f'Delete the file old.js in the folder {self.cwd} because nothing imports it any more.'])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        (self.project / 'old.js').unlink()
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('completed', run['status'])
        self.assertEqual([('absent', True)], [(c['kind'], c['passed']) for c in run['nodes'][0]['attempts'][0]['verdict']['checks']])

    def test_exists_check_is_not_bounded_by_the_listing_cap(self):
        # review test 12 (D12)
        for i in range(450):
            (self.project / f'a{i:04d}.txt').write_text('x')
        run_id = self.submit([self.statement('zzz_verify.txt', 'recording PASS')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.write('zzz_verify.txt', 'PASS\n')
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])
        self.assertNotIn('zzz_verify.txt', AG._listing(self.cwd))

    def test_syntax_check_finds_a_file_in_a_subfolder(self):
        # D12/D13: a pathed statement file is looked up by its exact relative path
        (self.project / 'src').mkdir()
        run_id = self.submit([self.statement('src/app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.write('src/app.py', 'def main():\n    return 1\n')
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])
        self.assertEqual(['src/app.py'], [r['argv'][-1] for r in self.runs if not r['shell']])

    def test_checkpoint_with_nothing_left_is_not_a_handoff(self):
        # review test 9 (D9)
        run_id = self.submit([self.statement('hello.py')], generations=3, syntax=False)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.checkpoint(['wrote hello.py'], [], [])
        self.finish(attempt)
        self.assertTrue(self.auto.advance(run_id))
        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(('failed', 'NO_OUTPUT'), (a0['status'], a0['failure']))
        self.assertEqual(('regen', 'feedback'), (a1['kind'], a1['strategy']))

    def test_feedback_ignores_planner_verdicts(self):
        # review test 11 (D11)
        run_id = self.submit([self.statement('hello.py')], regenerate=2, syntax=False)
        self.auto.advance(run_id)
        a0 = self.attempts(run_id, 'n0')[0]
        self.launch(a0)
        self.finish(a0)
        self.auto.advance(run_id)                               # a0 fails NO_OUTPUT, a1 launches with feedback
        with self.auto._mutate(run_id) as row:
            row['nodes'][0]['attempts'].append({
                'id': 'n0-a9', 'kind': 'planner', 'strategy': 'split', 'status': 'failed', 'failure': 'UNKNOWN',
                'verdict': {'passed': False, 'checks': [{'kind': 'split', 'passed': False, 'public': True,
                                                         'output': 'the split has 1 lines; it needs 2 to 4'}]}})
        row = self.auto._read(run_id)
        launched = self.auto._launch(row, row['nodes'][0], kind='regen', strategy='feedback')
        note = self.tasks.get(launched['task_id'])['context_note']
        self.assertIn('- exists hello.py: hello.py was not created', note)
        self.assertNotIn('split', note)

    def test_two_accepted_candidates_leave_one_winner(self):
        # Section 3: the second passing candidate stayed 'accepted' forever
        run_id = self.submit([self.statement('app.py')], candidates=2)
        self.auto.advance(run_id)
        a0, a1 = self.attempts(run_id, 'n0')
        self.launch(a0)
        self.launch(a1)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(a0)
        self.finish(a1)
        self.assertFalse(self.auto.advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual(['accepted', 'superseded'], [a['status'] for a in run['nodes'][0]['attempts']])
        self.assertEqual(1, run['summary']['nodes'][0]['accepted'])


class GateAndPromotion(Harness):
    def test_a_refused_gated_close_is_retried_and_the_failure_is_durable_first(self):
        # D23 / crash-safety 7f
        from symblic.autogen.runner import TaskError
        run_id = self.submit([self.statement('app.py')], regenerate=1)
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        self.launch(attempt)
        self.hub.turn = 'bash'
        self.hub.screen_text = 'Done: created 1 file and all 4 tests passed.'
        self.tasks.advance(attempt['task_id'])
        with patch.object(self.tasks, 'control', side_effect=TaskError('The coordinator is still handling this task.', 409)):
            self.assertTrue(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'CLAIM_MISMATCH', 'cancel', False), (seen['status'], seen['failure'], seen['close'], seen['closed']))
        self.assertIn('close_failed', self.names(run_id))
        self.assertFalse(self.tasks.get(attempt['task_id'])['cancel_requested'])
        self.auto.advance(run_id)                               # the next pass retries the close
        self.assertTrue(self.attempts(run_id, 'n0')[0]['closed'])
        self.assertTrue(self.tasks.get(attempt['task_id'])['cancel_requested'])

    def test_a_crash_inside_promotion_is_inspected_not_regenerated(self):
        # crash-safety 7g: a half-applied promotion was silently regenerated on top
        run_id = self.submit([self.statement('app.py')])
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.write('app.py', 'def main():\n    return 1\n')
        self.finish(attempt)
        real = self.hub.work_action

        def crash_on_apply(action, agent_id, *args, **kwargs):
            if action == 'apply':
                raise Crash()
            return real(action, agent_id, *args, **kwargs)
        with patch.object(self.hub, 'work_action', side_effect=crash_on_apply):
            with self.assertRaises(Crash):
                self.auto.advance(run_id)
        self.assertEqual('intent', self.attempts(run_id, 'n0')[0]['promotion']['state'])
        self.assertFalse(self.make_auto().advance(run_id))
        run = self.auto.get(run_id)
        self.assertEqual('unknown', run['status'])
        self.assertIn('promotion of attempt n0-a0 was interrupted', run['error'])
        self.assertEqual(1, len(self.hub.calls))
        self.auto.control(run_id, 'resume')
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])
        self.assertEqual(('apply', agent), self.hub.actions[-1])

    def test_a_promotion_conflict_retries_once_on_the_same_placement(self):
        # D15: a conflict rotated to another engine and node until the regenerate budget was gone
        self.hub.apply_result = {'conflicts': ['app.py']}
        run_id = self.submit([self.statement('app.py')], regenerate=3)
        self.auto.advance(run_id)
        for index in range(2):
            attempt = self.attempts(run_id, 'n0')[index]
            self.launch(attempt)
            self.write('app.py', f'def main():\n    return {index}\n')
            self.finish(attempt)
            self.auto.advance(run_id)
            seen = self.attempts(run_id, 'n0')[index]
            self.assertEqual(('failed', 'CONFLICT'), (seen['status'], seen['failure']))
            self.auto.advance(run_id)
        a0, a1 = self.attempts(run_id, 'n0')
        self.assertEqual(('conflict_retry', 'claude', 'orchestrator'), (a1['strategy'], a1['engine'], a1['node']))
        run = self.auto.get(run_id)
        self.assertEqual('failed', run['status'])
        self.assertIn('promotion conflicts with the project folder persist: apply conflicts: app.py', run['error'])
        self.assertEqual(2, len(self.hub.calls))


class HiddenGate(Harness):
    PARENT = 'Create the files alpha.py and beta.py in the folder {cwd} with one function each.'

    def split_run(self, hidden):
        run_id = self.submit([self.PARENT.format(cwd=self.cwd)], candidates=1, regenerate=0, depth=1, hidden=[hidden])
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.launch(first)
        self.finish(first)
        self.auto.advance(run_id)
        planner = self.attempts(run_id, 'n0')[1]
        self.launch(planner)
        # the planner speaks of its working folder; stored children name the project folder again
        self.write(POLICY.SPLIT_FILE, 'Create the file alpha.py in the current working folder with a function named alpha.\n'
                                      'Create the file beta.py in the current working folder with a function named beta.\n')
        self.finish(planner)
        self.auto.advance(run_id)
        self.assertEqual(f'Create the file alpha.py in the folder {self.cwd} with a function named alpha.',
                         self.node(run_id, 'n0.0')['statement'])
        for child_id, name in (('n0.0', 'alpha.py'), ('n0.1', 'beta.py')):
            self.auto.advance(run_id)
            attempt = self.attempts(run_id, child_id)[0]
            self.assertNotIn(self.cwd, self.tasks.get(attempt['task_id'])['instruction'])
            self.launch(attempt)
            self.write(name, 'def f():\n    return 1\n')
            self.finish(attempt)
            self.auto.advance(run_id)
        self.auto.advance(run_id)
        return self.auto.get(run_id)

    def test_hidden_checks_gate_the_run_after_a_split(self):
        # review test 4 (D4): the hidden command never ran against accepted work after a split
        command = 'python3 -c "import alpha, beta"'
        run = self.split_run(command)
        self.assertEqual('completed', run['status'])
        hidden = [r for r in self.runs if r['argv'] == command]
        self.assertEqual([(self.cwd, True)], [(r['cwd'], r['shell']) for r in hidden])
        self.assertEqual([{'kind': 'hidden', 'index': 0, 'passed': True, 'rc': 0, 'public': False}], run['final']['hidden'])
        self.assertEqual(1, [e.get('node') for e in self.events(run['id']) if e['event'] == 'node_accepted'].count('n0'))

    def test_a_failing_hidden_check_fails_the_run_and_its_output_stays_out(self):
        command = 'python3 -c "import alpha, beta"'
        self.results[command] = {'rc': 1, 'out': 'SECRET-ORACLE-OUTPUT'}
        run = self.split_run(command)
        self.assertEqual('failed', run['status'])
        self.assertIn('HIDDEN_FAILURE', run['error'])
        record = (self.root / 'state' / 'autogen' / (run['id'] + '.json')).read_text()
        log = (self.root / 'state' / 'autogen' / (run['id'] + '.events.jsonl')).read_text()
        self.assertNotIn('SECRET-ORACLE-OUTPUT', record + log)
        self.assertEqual('', AG._public_report([{'kind': 'hidden', 'passed': False, 'public': False, 'output': 'SECRET'}]))


class Reattach(Harness):
    def test_restart_reattaches_without_probing_the_worker_lease(self):
        # D22 and crash-safety: get()/listing() never re-attached; probing the lease raced the worker
        lines = [self.statement('app.py')]
        run_id = self.submit(lines)
        auto = self.make_auto()
        auto.background = True
        scheduled = []
        auto._schedule = scheduled.append
        self.assertTrue(auto.submit(self.body(lines))['duplicate'])
        self.assertEqual([run_id], scheduled)                   # a retried submit re-attaches
        with patch.object(auto, '_lock', wraps=auto._lock) as lock:
            row = auto.get(run_id)
            self.assertFalse(any(c.kwargs.get('worker') for c in lock.call_args_list))
        self.assertTrue(row['resume_required'])
        self.assertEqual([run_id, run_id], scheduled)
        self.assertEqual('listing', auto._read(run_id)['resumed']['by'])
        auto.listing()
        self.assertEqual(2, len(scheduled))                     # the heartbeat now says a worker is starting
        os.unlink(auto._alive_path(run_id))
        self.clock.advance(AG.RESUME_WINDOW + 1)
        auto.listing()
        self.assertEqual(2, len(scheduled))                     # outside the window: the operator's to resume
        self.clock.advance(-AG.RESUME_WINDOW - 1)
        auto.control(run_id, 'cancel')
        scheduled.clear()
        os.unlink(auto._alive_path(run_id)) if auto._alive_path(run_id).exists() else None
        auto.listing()
        self.assertEqual([], scheduled)                         # a pending cancel is not re-attached by a read


class RemoteHarness(Harness):
    """A node attempt: verified at home in a staging checkout of the fetched ref."""

    def setUp(self):
        super().setUp()
        self.produced = {}               # files the node's checkout holds when it is fetched
        self.diff = ''
        self.drop_rc = 0
        self.git_calls = []
        self.auto = self.make_auto(git=self.git)

    def git(self, argv, cwd, timeout=120):
        self.git_calls.append(argv[3:])
        if argv[3:5] == ['worktree', 'add']:
            staging = argv[-2]
            if os.path.exists(staging):
                return {'rc': 128, 'out': f"fatal: '{staging}' already exists"}
            os.makedirs(staging)
            for name, text in self.produced.items():
                Path(staging, name).parent.mkdir(parents=True, exist_ok=True)
                Path(staging, name).write_text(text)
            return {'rc': 0, 'out': ''}
        if argv[3:5] == ['worktree', 'remove']:
            if self.drop_rc == 0:
                import shutil
                shutil.rmtree(argv[-1], ignore_errors=True)
            return {'rc': self.drop_rc, 'out': '' if self.drop_rc == 0 else 'error: cannot remove'}
        if argv[3] == 'diff':
            return {'rc': 0, 'out': self.diff}
        return {'rc': 0, 'out': ''}

    def remote_body(self, request='remote-1', **policy):
        return {**self.body([self.statement('app.py')], request, **policy), 'node': 'node09'}

    def give_git(self, agent_id):
        agent = next(a for a in self.hub.agents if a['id'] == agent_id)
        agent['git'] = {'branch': 'agents/x', 'base_sha': 'b' * 40, 'main_root': self.cwd,
                        'remote': {'node': 'node09', 'sourceBranch': 'agents/x'}}


class Remote(RemoteHarness):
    def test_a_remote_attempt_is_staged_outside_the_project_and_a_noop_is_refused(self):
        # item 2 (remote change set from git diff) and item 8 (staging location, leftovers)
        run_id = self.auto.submit(self.remote_body(regenerate=0))['run']['id']
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.give_git(agent)
        staging = self.auto._staging_path(run_id, 'n0-a0')
        staging.mkdir(parents=True)                             # a leftover from a crashed verdict
        self.produced = {'app.py': 'def main():\n    return 1\n'}
        self.diff = ''                                          # the node changed nothing
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        seen = self.attempts(run_id, 'n0')[0]
        self.assertEqual(('failed', 'NO_OUTPUT'), (seen['status'], seen['failure']))
        self.assertTrue(seen['verdict']['staging'])
        adds = [c for c in self.git_calls if c[:2] == ['worktree', 'add']]
        self.assertEqual(str(staging), adds[0][-2])
        self.assertTrue(str(staging).startswith(str(self.root / 'state' / 'autogen' / 'staging')))
        self.assertLess(self.git_calls.index(['worktree', 'remove', '--force', str(staging)]), self.git_calls.index(adds[0]))
        self.assertFalse(staging.exists())
        self.assertFalse(any(name.startswith(AG.STAGING_PREFIX) for name in os.listdir(self.cwd)))

    def test_a_remote_change_passes_and_a_failed_drop_is_recorded(self):
        run_id = self.auto.submit(self.remote_body('remote-2'))['run']['id']
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.give_git(agent)
        self.produced = {'app.py': 'def main():\n    return 1\n'}
        self.diff = 'app.py\0'
        self.drop_rc = 1
        self.finish(attempt)
        self.assertFalse(self.auto.advance(run_id))
        self.assertEqual('completed', self.auto.get(run_id)['status'])
        self.assertIn('staging_drop_failed', self.names(run_id))
        self.assertEqual(['app.py'], [r['argv'][-1] for r in self.runs if not r['shell']])

    def test_a_remote_checkpoint_is_read_from_staging_and_its_handoff_is_refused_not_relaunched_fresh(self):
        # D7 (checkpoint read while the staging checkout exists) and item 5 (no workspaceFrom option)
        run_id = self.auto.submit(self.remote_body('remote-3', generations=2, regenerate=1))['run']['id']
        self.auto.advance(run_id)
        attempt = self.attempts(run_id, 'n0')[0]
        agent = self.launch(attempt)
        self.give_git(agent)
        self.produced = {'app.py': 'def main(:\n', POLICY.CHECKPOINT_FILE: json.dumps(
            {'version': 1, 'done': ['started'], 'left': ['finish main'], 'files': ['app.py']})}
        self.diff = 'app.py\0'
        self.results['app.py'] = {'rc': 1, 'out': 'SyntaxError'}
        self.finish(attempt)
        self.assertTrue(self.auto.advance(run_id))
        a0, refused = self.attempts(run_id, 'n0')[:2]
        self.assertEqual('handoff', a0['status'])
        self.assertEqual(['finish main'], a0['checkpoint']['left'])
        self.assertEqual(('handoff', 'failed', 'REFUSAL'), (refused['kind'], refused['status'], refused['failure']))
        self.assertIn('remote handoff unsupported', refused['error'])
        self.assertEqual(1, len(self.hub.calls))
        self.assertTrue(self.auto.advance(run_id))              # then an ordinary regeneration
        self.assertEqual('regen', self.attempts(run_id, 'n0')[2]['kind'])

    def test_a_remote_planner_drops_its_staging(self):
        # item 8: the planner branch returned before the finally and leaked its staging checkout
        body = {**self.body([f'Create the files alpha.py and beta.py in the folder {self.cwd} with one function each.'],
                            'remote-4', candidates=1, regenerate=0, depth=1), 'node': 'node09'}
        run_id = self.auto.submit(body)['run']['id']
        self.auto.advance(run_id)
        first = self.attempts(run_id, 'n0')[0]
        self.give_git(self.launch(first))
        self.finish(first)
        self.auto.advance(run_id)
        planner = self.attempts(run_id, 'n0')[1]
        self.give_git(self.launch(planner))
        self.produced = {POLICY.SPLIT_FILE: 'Create the file alpha.py in the current working folder with a function alpha.\n'
                                            'Create the file beta.py in the current working folder with a function beta.\n'}
        self.finish(planner)
        self.auto.advance(run_id)
        self.assertEqual('split', self.node(run_id, 'n0')['status'])
        staging = self.auto._staging_path(run_id, 'n0-a1')
        self.assertIn(['worktree', 'remove', '--force', str(staging)], self.git_calls)
        self.assertFalse(staging.exists())


if __name__ == '__main__':
    unittest.main()
