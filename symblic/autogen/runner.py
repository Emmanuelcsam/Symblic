"""The task-runner boundary of autogen: how the coordinator gets coding agents to work.

What it is for
    The autogen coordinator (symblic/autogen/coordinator.py) runs every attempt at a statement
    as a *task*: one fresh coding-agent session that receives one instruction and works in its
    own git checkout. The coordinator never starts an agent itself. It talks to a TaskRunner,
    an object with the small interface defined here, so any agent launcher can sit behind it.
    Spec-sheet runs on the kernel lane (symblic/autogen/kernel_lane.py) need no agents at all;
    for them the runner only names the machines ("nodes") that serve local models.

What is in this module
    TaskError               the one error type a runner raises (status 404 means "no such task").
    deterministic_task_id   the task id a runner must derive from a client_request_id.
    execution_fence         an optional fence: refuse to execute anywhere but the machine named
                            by the SYMBLIC_EXECUTION_HOST environment variable.
    workspace_inventory, inventory_changes, claimed_work, disk_evidence
                            pure evidence helpers: what a local agent changed on disk, and what it
                            claimed in its final text. A claim is never evidence; it is only
                            cross-checked against the disk.
    TaskRunner              the protocol (the methods and the task record the coordinator reads).
    missing_members         which protocol members an object lacks (for tests and sanity checks).
    KernelOnlyRunner        a runner that launches no agent tasks: enough for kernel-lane runs.
    FakeTaskRunner          an in-memory runner for tests and for reading the contract by example.

Where a real agent runner comes from
    This repository ships no production agent launcher. The only one that existed drove the
    original host's agent hub (terminal panes, remote nodes, a human review gate); it is kept for
    reference in integration/host/symblicos_tasks.py (TaskManager and its HubTaskRunner adapter)
    and does not run outside that host. To use autogen with CLI coding agents, implement
    TaskRunner over your own launcher; FakeTaskRunner shows every field the coordinator reads.

Depends on
    The Python standard library only. Nothing here starts a process or opens a socket.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import time
from typing import Any, Protocol, Sequence, runtime_checkable


class TaskError(ValueError):
    """A runner's refusal or failure. `status` follows HTTP: 404 no such task, 409 conflicting
    request, 501 not supported by this runner, 503 fenced or unavailable, 400 anything else."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def deterministic_task_id(request_id: str) -> str:
    """The task id for a client_request_id. Every runner must use it: after a crash between a
    submit and its record, the coordinator cancels or adopts the task by this id alone."""
    return 'task-' + hashlib.sha256(str(request_id).encode()).hexdigest()[:32]


# ------------------------------------------------------------------------------ execution fence

FENCE_ENV = 'SYMBLIC_EXECUTION_HOST'


def execution_fence() -> None:
    """Refuse to execute on any machine but the one SYMBLIC_EXECUTION_HOST names.

    Unset (the default), there is no fence. A deployment that copies its state folder to a standby
    machine sets it on both, so the copy can be read but never launches work twice."""
    wanted = (os.environ.get(FENCE_ENV) or '').strip().split('.')[0].lower()
    if wanted and socket.gethostname().split('.')[0].lower() != wanted:
        raise TaskError(f'Execution is fenced to {FENCE_ENV}={wanted}; this copy is read-only.', 503)


# ------------------------------------------------------------------------------ disk evidence (pure)

INVENTORY_FILES = 200                    # files one inventory walk records (bounded on purpose)
INVENTORY_HASH_BYTES = 4 * 1024 * 1024   # larger files are listed without a hash
EVIDENCE_TAIL = 4000                     # characters of an agent's final text kept as evidence
CLAIMED_TESTS = re.compile(r'(?:(\d+)\s+)?tests?\s+(?:are\s+|were\s+)?(?:passed|passing|ok)\b', re.I)
CLAIMED_FILES = re.compile(r'(?:edited|changed|modified|updated|created|wrote)\s+(\d+)\s+files?\b', re.I)


def workspace_inventory(root, *, max_files=INVENTORY_FILES, max_hash_bytes=INVENTORY_HASH_BYTES) -> dict:
    """A bounded walk of a local workspace: relative paths, sizes and sha256 of regular files
    (never following links, skipping .git). `truncated` is true when the walk stopped early."""
    if not isinstance(root, str) or not root.strip():
        return {'available': False, 'reason': 'No workspace path was recorded for this step.'}
    path = Path(root)
    try:
        if not path.is_dir():
            return {'available': False, 'reason': f'The recorded workspace is not a local folder: {root}'}
    except OSError:
        return {'available': False, 'reason': 'The recorded workspace could not be read from this machine.'}
    files, total, truncated = [], 0, False
    for directory, names, leaves in os.walk(path, followlinks=False):
        names[:] = sorted(name for name in names if name != '.git')
        for leaf in sorted(leaves):
            entry = Path(directory) / leaf
            try:
                info = entry.lstat()
                if not stat.S_ISREG(info.st_mode):
                    continue
            except OSError:
                continue
            digest = None
            if info.st_size <= max_hash_bytes:
                try:
                    hashed = hashlib.sha256()
                    handle = os.open(entry, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                    try:
                        while True:
                            chunk = os.read(handle, 65536)
                            if not chunk:
                                break
                            hashed.update(chunk)
                    finally:
                        os.close(handle)
                    digest = hashed.hexdigest()
                except OSError:
                    digest = None
            total += info.st_size
            files.append({'path': str(entry.relative_to(path)), 'size': info.st_size, 'sha256': digest})
            if len(files) >= max_files:
                truncated = True
                break
        if truncated:
            break
    return {'available': True, 'root': root, 'file_count': len(files),
            'total_bytes': total, 'truncated': truncated, 'files': files}


def inventory_changes(before, after) -> dict | None:
    """Added, removed and modified paths between two inventories; None when either is missing."""
    if not (before or {}).get('available') or not (after or {}).get('available'):
        return None
    old = {row['path']: row for row in before['files']}
    new = {row['path']: row for row in after['files']}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(path for path in set(old) & set(new) if old[path].get('sha256') != new[path].get('sha256'))
    return {'added': added, 'removed': removed, 'modified': modified,
            'files_changed': len(added) + len(removed) + len(modified)}


def claimed_work(text) -> dict:
    """What an agent's final text claims ("created 2 files", "all 4 tests passed"). A claim is a
    claim: it is recorded so it can be compared with the disk, never trusted on its own."""
    tests = CLAIMED_TESTS.search(text or '')
    files = CLAIMED_FILES.search(text or '')
    if not tests and not files:
        return {'claimed': False}
    return {'claimed': True,
            'tests': int(tests.group(1)) if tests and tests.group(1) else None,
            'files': int(files.group(1)) if files else None}


def disk_evidence(baseline, workspace, final_text='', *, clock=time.time) -> dict:
    """The evidence record of one ended agent turn, in the shape the coordinator reads:
    `changes` (what the disk says changed since `baseline`, or None when unverifiable), the
    agent's `claims`, and a `warning` when it claimed work while no file changed."""
    inventory = (workspace_inventory(workspace) if workspace else
                 {'available': False, 'reason': 'The workspace is on another machine; it cannot be inventoried here.'})
    changes = inventory_changes(baseline, inventory)
    tail = str(final_text or '')[-EVIDENCE_TAIL:]
    claims = claimed_work(tail)
    warning = ''
    if claims['claimed'] and changes is not None and changes['files_changed'] == 0:
        warning = ('The agent reported completed work, but no workspace file changed since launch; '
                   'inspect its terminal and the workspace before accepting this result.')
    return {'kind': 'disk_cross_check', 'captured': clock(), 'tail': tail, 'inventory': inventory,
            'changes': changes, 'claims': claims, 'warning': warning}


# ------------------------------------------------------------------------------ the protocol

@runtime_checkable
class TaskRunner(Protocol):
    """What the autogen coordinator needs from an agent launcher.

    Catalogue
        engines       the engine names this runner can launch (for example 'claude', 'codex',
                      'local'). The coordinator rotates among them for the other_engine strategy.
        local_node    the machine the coordinator itself runs on. A local model is never placed
                      there (a deployment rule: the coordinating machine only coordinates).
                      '' disables that rule.
        nodes()       [{'id': str, 'online': bool}, ...]: the machines attempts may run on.

    Tasks
        submit(body)  start one task. `body` holds client_request_id, instruction, mode='agent',
                      engine, node, cwd (an absolute project folder), worktree (True: work in an
                      own git checkout of cwd), auto, auto_next, headless, context_note and,
                      optionally, model and effort. Returns {'task': TASK, 'duplicate': bool}. The
                      task id MUST be deterministic_task_id(client_request_id); the same request id
                      with the same body returns the same task with duplicate=True, a different
                      body raises TaskError(status=409). A refusal raises TaskError (a message
                      containing "refus" is recorded as a REFUSAL, anything else as INFRASTRUCTURE).
        get(task_id)  the TASK record, or TaskError(status=404) when there is none. Any other
                      TaskError is treated as transient (the coordinator asks again later).
        control(task_id, action)
                      'cancel' stops the task (cancelling a completed task changes nothing and
                      returns it as completed); 'next' accepts a step that waits in a review gate.
                      Returns {'task': TASK}; a refusal raises TaskError and is retried later.
        advance(task_id)
                      drive one observation pass of a task now (used when a step waits in a review
                      gate while its agent still runs). May do nothing.
        reattach(task)
                      re-attach whatever watches a task after a restart. May do nothing.

    TASK record (a dict; the coordinator reads only these fields)
        id, status ('queued'|'active'|'awaiting_review'|'completed'|'failed'|'cancelled'|'unknown'),
        error (text), workspace (absolute folder), instruction, and steps: a list whose FIRST step is
        the attempt, with status (as above), running (bool: the agent process still runs), error,
        agent_id, agent ({'id', 'node', 'cwd', optional 'git': {'cwd', 'worktree', 'base_sha'}}),
        workspace, completion ({'done': bool, 'available': bool}) and evidence (None until the turn
        ended, then the disk_evidence() record: 'changes', 'inventory', 'claims', 'warning').
        'unknown' means the launch or stop could not be confirmed: the coordinator never relaunches
        over it and asks the operator to inspect.

    Results on other machines
        is_remote(agent)
                      True when the agent works on another machine (its files are not on this one).
        fetch_remote(agent_id)
                      commit the agent's work on its machine and fetch the branch here. Returns
                      {'ref': a git ref in main_root, 'main_root': the project repository,
                      'base_sha': the commit the agent started from}. The coordinator verifies the
                      ref in a detached staging checkout outside the project.

    Promotion
        promote(agent_id, message)
                      bring an accepted agent's work into the project folder: commit it in the
                      agent's checkout, then apply it to the project's working tree (3-way, no
                      commit there). Returns {'files': [...], 'message': text} or raises; a message
                      containing "clash" or "conflict" is recorded as CONFLICT (the project changed
                      meanwhile), anything else as INFRASTRUCTURE.
    """

    engines: Sequence[str]
    local_node: str

    def nodes(self) -> list[dict]: ...

    def submit(self, body: dict) -> dict: ...

    def get(self, task_id: str) -> dict: ...

    def control(self, task_id: str, action: str) -> dict: ...

    def advance(self, task_id: str) -> Any: ...

    def reattach(self, task: dict) -> None: ...

    def is_remote(self, agent: dict) -> bool: ...

    def fetch_remote(self, agent_id: str) -> dict: ...

    def promote(self, agent_id: str, message: str = '') -> dict: ...


RUNNER_MEMBERS = ('engines', 'local_node', 'nodes', 'submit', 'get', 'control', 'advance', 'reattach',
                  'is_remote', 'fetch_remote', 'promote')


def missing_members(runner) -> list[str]:
    """The TaskRunner members `runner` lacks (an empty list for a complete runner)."""
    return [name for name in RUNNER_MEMBERS if not hasattr(runner, name)]


# ------------------------------------------------------------------------------ a runner without agents

class KernelOnlyRunner:
    """A TaskRunner that launches no agent tasks.

    Spec-sheet runs on the kernel lane (engine 'local') build their file with local models through
    the Symblic kernel and never need an agent; they only need to know which nodes serve local
    models. Every task method refuses with status 501, so a statement meant for a CLI agent is
    refused at submit instead of waiting forever.

        runner = KernelOnlyRunner(nodes=['node-a', 'node-b'])
        manager = AutogenManager(root, task_runner=runner)
    """

    engines = ('local',)

    def __init__(self, nodes: Sequence[str] = (), local_node: str = ''):
        self.local_node = str(local_node or '')
        self._nodes = [str(node) for node in nodes]

    def nodes(self) -> list[dict]:
        return [{'id': node, 'online': True} for node in self._nodes]

    def submit(self, body):
        raise TaskError('This runner launches no agent tasks: only spec sheets on the kernel lane (engine local) '
                        'run without an agent runner.', 501)

    def get(self, task_id):
        raise TaskError('Task not found.', 404)

    def control(self, task_id, action):
        raise TaskError('Task not found.', 404)

    def advance(self, task_id):
        return None

    def reattach(self, task):
        return None

    def is_remote(self, agent):
        return False

    def fetch_remote(self, agent_id):
        raise TaskError('This runner has no agents on other machines.', 501)

    def promote(self, agent_id, message=''):
        raise TaskError('This runner has no agent checkouts to promote.', 501)


# ------------------------------------------------------------------------------ the documented fake

class FakeTaskRunner:
    """An in-memory TaskRunner for tests, and the contract written out as working code.

    Nothing is launched. submit() records the body and creates a task whose one step is already
    "active" with an agent; the test then plays the agent: it writes files into the task's
    workspace and calls finish() (the turn ended and the task completed), gate() (the turn ended
    in a review gate) or fail(). Evidence is real: the workspace is inventoried at submit and again
    at the end, so the coordinator's "did this attempt change the files it names" check sees the
    disk. Unlike a real runner, the fake's agents work directly in the folder they are given (no
    own checkout), so a test writes an agent's files into that folder.

    Knobs a test may set: engines, local_node, set_nodes(...), submit_error / control_error /
    promote_error (raised once and cleared), get_errors[task_id] (raised by get), remote_refs
    [agent_id] (what fetch_remote returns), promote_result (what promote returns), on_advance
    (called by advance). Records a test may read: submitted (bodies), controls, advanced,
    reattached, fetched, promoted.
    """

    def __init__(self, *, engines: Sequence[str] = ('claude', 'codex', 'agy', 'local'),
                 nodes: Sequence[str] = ('host', 'node-a'), local_node: str = 'host', clock=time.time):
        self.engines = tuple(engines)
        self.local_node = local_node
        self.clock = clock
        self._nodes = [{'id': node, 'online': True} for node in nodes]
        self.tasks: dict[str, dict] = {}
        self.submitted: list[dict] = []
        self.controls: list[tuple[str, str]] = []
        self.advanced: list[str] = []
        self.reattached: list[str] = []
        self.fetched: list[str] = []
        self.promoted: list[tuple[str, str]] = []
        self.submit_error = None
        self.control_error = None
        self.promote_error = None
        self.promote_result = None
        self.get_errors: dict[str, Exception] = {}
        self.remote_refs: dict[str, dict] = {}
        self.on_advance = None

    # -- catalogue
    def set_nodes(self, *nodes, offline=()):
        self._nodes = [{'id': node, 'online': node not in offline} for node in nodes]

    def nodes(self) -> list[dict]:
        return [dict(node) for node in self._nodes]

    # -- tasks
    def submit(self, body: dict) -> dict:
        if not isinstance(body, dict):
            raise TaskError('Submit a JSON object.')
        request_id = body.get('client_request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', request_id):
            raise TaskError('A stable client_request_id is required.')
        for key in ('instruction', 'engine', 'node', 'cwd'):
            if not isinstance(body.get(key), str) or not body[key]:
                raise TaskError(f'{key} is required.')
        task_id = deterministic_task_id(request_id)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if task_id in self.tasks:
            if self.tasks[task_id]['request_digest'] != digest:
                raise TaskError('This request id already belongs to a different body.', 409)
            return {'task': copy.deepcopy(self.tasks[task_id]), 'duplicate': True}
        if self.submit_error is not None:
            error, self.submit_error = self.submit_error, None
            raise error
        self.submitted.append(copy.deepcopy(body))
        agent = {'id': f'agent-{len(self.submitted)}', 'engine': body['engine'], 'node': body['node'],
                 'cwd': body['cwd']}
        remote = self.is_remote(agent)
        step = {'index': 0, 'status': 'active', 'running': True, 'error': '', 'agent_id': agent['id'],
                'agent': agent, 'workspace': body['cwd'], 'evidence': None,
                'completion': {'available': True, 'done': False},
                'baseline': None if remote else workspace_inventory(body['cwd']), 'started': self.clock()}
        options = {key: body[key] for key in ('engine', 'model', 'effort', 'node', 'cwd', 'worktree', 'auto',
                                              'auto_next', 'headless') if key in body}
        self.tasks[task_id] = {'id': task_id, 'client_request_id': request_id, 'request_digest': digest,
                               'instruction': body['instruction'], 'mode': body.get('mode', 'agent'),
                               'context_note': body.get('context_note', ''), 'options': options,
                               'status': 'active', 'error': '', 'workspace': body['cwd'],
                               'cancel_requested': False, 'steps': [step]}
        return {'task': copy.deepcopy(self.tasks[task_id]), 'duplicate': False}

    def get(self, task_id: str) -> dict:
        if task_id in self.get_errors:
            raise self.get_errors[task_id]
        if task_id not in self.tasks:
            raise TaskError('Task not found.', 404)
        return copy.deepcopy(self.tasks[task_id])

    def control(self, task_id: str, action: str) -> dict:
        self.controls.append((task_id, action))
        if self.control_error is not None:
            error, self.control_error = self.control_error, None
            raise error
        if task_id not in self.tasks:
            raise TaskError('Task not found.', 404)
        task = self.tasks[task_id]
        step = task['steps'][0]
        if action == 'cancel':
            task['cancel_requested'] = True
            if task['status'] != 'completed':
                task['status'] = step['status'] = 'cancelled'
                step['running'] = False
        elif action == 'next':
            if step['status'] != 'awaiting_review':
                raise TaskError('Next requires a step that waits in the review gate.', 409)
            step.update(status='completed', running=False)
            task['status'] = 'completed'
        else:
            raise TaskError('Choose cancel or next.')
        return {'task': copy.deepcopy(task)}

    def advance(self, task_id: str):
        self.advanced.append(task_id)
        if self.on_advance is not None:
            self.on_advance(task_id)

    def reattach(self, task: dict) -> None:
        self.reattached.append(task.get('id'))

    # -- the test plays the agent
    def task_for(self, request_id: str) -> dict:
        return self.tasks[deterministic_task_id(request_id)]

    def _end_turn(self, task_id, final_text):
        task = self.tasks[task_id]
        step = task['steps'][0]
        workspace = None if self.is_remote(step['agent']) else step['workspace']
        step['evidence'] = disk_evidence(step.get('baseline'), workspace, final_text, clock=self.clock)
        return task, step

    def finish(self, task_id: str, final_text: str = '') -> dict:
        """The agent's turn ended and the task completed, with disk evidence."""
        task, step = self._end_turn(task_id, final_text)
        step.update(status='completed', running=False, completion={'available': True, 'done': True, 'kind': 'native_turn'})
        task['status'] = 'completed'
        return copy.deepcopy(task)

    def gate(self, task_id: str, final_text: str = '', *, running: bool = False) -> dict:
        """The step waits in a review gate. running=False: the turn ended (evidence is captured);
        running=True: the agent still works and there is no evidence yet."""
        task = self.tasks[task_id]
        step = task['steps'][0]
        if running:
            step.update(status='awaiting_review', running=True, evidence=None,
                        completion={'available': False, 'done': False})
        else:
            task, step = self._end_turn(task_id, final_text)
            step.update(status='awaiting_review', running=False, completion={'available': True, 'done': False})
        task['status'] = 'awaiting_review'
        return copy.deepcopy(task)

    def fail(self, task_id: str, error: str = 'the launch failed', status: str = 'failed') -> dict:
        """The task ended without a turn: 'failed', 'cancelled' or 'unknown'."""
        task = self.tasks[task_id]
        task['steps'][0].update(status=status, running=False, error=error)
        task.update(status=status, error=error)
        return copy.deepcopy(task)

    # -- other machines and promotion
    def is_remote(self, agent: dict) -> bool:
        return (agent or {}).get('node') not in ('', None, self.local_node)

    def fetch_remote(self, agent_id: str) -> dict:
        self.fetched.append(agent_id)
        if agent_id not in self.remote_refs:
            raise TaskError('no fetched branch for this agent')
        return dict(self.remote_refs[agent_id])

    def promote(self, agent_id: str, message: str = '') -> dict:
        self.promoted.append((agent_id, message))
        if self.promote_error is not None:
            error, self.promote_error = self.promote_error, None
            raise error
        if self.promote_result is not None:
            return copy.deepcopy(self.promote_result)
        files = []
        for task in self.tasks.values():
            step = task['steps'][0]
            if step.get('agent_id') == agent_id:
                changes = (step.get('evidence') or {}).get('changes') or {}
                files = sorted(set(changes.get('added') or []) | set(changes.get('modified') or []))
        return {'message': 'applied', 'files': files}
