"""Shared test fixtures for the autogen coordinator (not a test module itself).

CoordinatorHarness gives every test a fresh temporary state root, a temporary project folder
(with a .git directory, which is all the coordinator checks for), the documented
FakeTaskRunner from symblic/autogen/runner.py as the agent launcher, a scripted check runner
(no real syntax checks or commands run unless a test says so) and an injected clock. A test
plays each agent: it writes files into the project folder and calls finish() for the attempt.
No model, agent, network or real node is ever involved.
"""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from symblic.autogen import coordinator as AG
from symblic.autogen import policy as POLICY
from symblic.autogen.coordinator import AutogenManager
from symblic.autogen.runner import FakeTaskRunner

HOST = 'orchestrator'           # the machine the coordinator runs on, in every fixture
REMOTE = 'node09'               # a second node


class Clock:
    """An injected time source that only moves when a test moves it."""

    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Crash(BaseException):
    """Simulates the process dying at an exact point (not an Exception, so nothing catches it)."""


class CoordinatorHarness(unittest.TestCase):
    ENGINES = ('claude', 'agy', 'codex', 'local')
    NODES = (HOST, REMOTE)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autogen-test-')
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / 'state-root'
        self.root.mkdir()
        self.project = base / 'project'
        (self.project / '.git').mkdir(parents=True)
        self.cwd = str(self.project)
        self.clock = Clock(time.time())
        self.results = {}           # syntax target file or shell command -> {'rc', 'out'}
        self.runs = []              # every check the coordinator ran
        self.on_run = None
        self.tasks = self.make_runner()
        self.auto = self.make_auto()

    # -- injected collaborators
    def make_runner(self):
        return FakeTaskRunner(engines=self.ENGINES, nodes=self.NODES, local_node=HOST, clock=self.clock)

    def check_runner(self, argv, cwd, timeout=120, shell=False):
        self.runs.append({'argv': argv, 'cwd': cwd, 'shell': shell, 'timeout': timeout})
        if self.on_run:
            self.on_run(argv)
        return dict(self.results.get(argv if shell else argv[-1], {'rc': 0, 'out': ''}))

    def listing(self, folder, limit=400):
        return AG._listing(folder, limit)

    def make_auto(self, task_runner=None, **extra):
        return AutogenManager(str(self.root), task_runner=task_runner or self.tasks, background=False,
                              check_host=lambda: None, check_runner=self.check_runner, listing=self.listing,
                              clock=self.clock, **extra)

    # -- statements and runs
    def statement(self, name, extra='with a function named main'):
        return f'Create the file {name} in the folder {self.cwd} {extra}.'

    def body(self, lines, request='run-1', **policy):
        return {'client_request_id': request, 'instruction': '\n'.join(lines), 'engine': 'claude',
                'node': HOST, 'cwd': self.cwd, 'autogen': policy}

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

    # -- playing the agent
    def write(self, rel, text, at=None):
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        stamp = self.clock() if at is None else at
        os.utime(path, (stamp, stamp))

    def checkpoint(self, done, left, files):
        self.write(POLICY.CHECKPOINT_FILE, json.dumps({'version': 1, 'done': done, 'left': left, 'files': files}))

    def task(self, attempt):
        """The fake runner's task record of an attempt."""
        return self.tasks.tasks[attempt['task_id']]

    def finish(self, attempt, text=''):
        """The attempt's agent ends its turn; its task completes with disk evidence."""
        return self.tasks.finish(attempt['task_id'], text)

    def loc(self, text):
        """An attempt instruction as the worker receives it: localized to its own checkout."""
        return POLICY.localize(text, self.cwd)

    def suffix(self, run_id, index=0):
        run = self.auto.get(run_id)
        node = next((n for n in run['nodes'] if n['parent'] is None and n['index'] == index), run['nodes'][0])
        limit = POLICY.HARD_DEPTH if run['policy'].get('until_done') else run['policy']['depth']
        can_split = not node.get('perpetual') and node.get('depth', 0) < limit
        return POLICY.worker_suffix(run['policy'], index, self.cwd, can_split=can_split)
