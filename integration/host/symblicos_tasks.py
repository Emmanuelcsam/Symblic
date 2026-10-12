"""HOST-ONLY: the original host's durable task engine, kept as the reference TaskRunner.

Why this file is in integration/host/
    Every launch, observation and stop here goes through the original host's agent hub: a
    service that ran coding-agent CLIs in terminal sessions on the host and on remote nodes,
    showed them on a web page, and let a person close a step through a review gate. That hub is
    not part of this repository and no replacement exists, so this module cannot run anywhere
    else. It is kept because it is the only real implementation of the TaskRunner contract
    (symblic/autogen/runner.py) that autogen was used with, and its rules (durable receipts,
    no replay of an uncertain launch, disk cross-checks of agent claims) are worth reading.
    Its tests (tests/integration/test_symblicos_tasks.py) run against a fake hub.

What it does
    One line of an instruction launches one new agent session. A finished native turn is
    evidence that the agent answered, not that an arbitrary English objective was met.
    Uncertain launches are retained and never replayed, including after a restart. An ended
    turn records bounded terminal and workspace evidence; the agent's own claims are
    cross-checked against the disk, never trusted.

The hub interface it expects (an object passed as `hub=`; nothing is imported)
    ENGINES, LOCAL_NODE, MODEL_RX, MAX_PROMPT (optional), _SHELLS,
    start(options, group), stop(agent_id), screen(agent_id), history_text(agent_id),
    is_remote(agent), node_of(agent), _current(agent_id, agent), _remote_state(agent_id, agent, lines),
    _load() -> {'agents': [...]}, _git_info(agent), _home(), engines_payload(cached), fleet_nodes(refresh),
    and optionally answer_trust_for(agent_id), triad_discrete_status(agent), native_turn(agent),
    work_action(action, agent_id), _find(agent_id) (the last two for HubTaskRunner).

HubTaskRunner (at the end) adapts TaskManager plus such a hub to the TaskRunner protocol, so
AutogenManager(root, task_runner=HubTaskRunner(manager)) behaves as it did on the original host.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re
import threading
import time

from symblic.autogen.durable import atomic_json  # noqa: F401  (re-exported for older callers)
from symblic.autogen.runner import (CLAIMED_FILES, CLAIMED_TESTS, EVIDENCE_TAIL, INVENTORY_FILES,  # noqa: F401
                                    INVENTORY_HASH_BYTES, TaskError, claimed_work, execution_fence,
                                    inventory_changes, workspace_inventory)

ID = re.compile(r'^task-[a-f0-9]{32}$')
TERMINAL = {'completed', 'cancelled', 'failed', 'unknown'}
OPTIONS = ('engine', 'model', 'effort', 'node', 'cwd', 'worktree', 'auto', 'roles',
           'council', 'squad', 'context', 'attachments', 'deepResearch', 'workingDefaults', 'discrete',
           'parallel', 'headless', 'auto_next')
PARALLEL_MAX = 8                     # concurrent line sessions a lines-mode task may run
STALL_HINT_SECONDS = 900             # active-without-evidence advisory threshold
STALL_HINT = ('This step has been active without completion evidence for over fifteen '
              'minutes. Inspect the linked agent terminal: a launch that died before its '
              'first turn looks the same as slow progress.')
REFUSAL_TEXT = re.compile(r'exceeds?\s+(?:the\s+|its\s+)?(?:admitted\s+)?input\s+budget'
                          r'|refus(?:e|es|ed|ing)\s+(?:to\s+)?(?:start|launch|admit|run)\b'
                          r'|admission\s+refus(?:e|es|ed)\b', re.I)


def catalog(hub=None, *, refresh=False):
    """The engines, models and nodes the hub offers, plus the task modes; cached unless refresh.
    The hub must be given: without the host's hub there is no catalogue (TaskError 503)."""
    if hub is None:
        raise TaskError('No agent hub was given: this catalogue needs the host\'s hub object.', 503)
    result = hub.engines_payload(cached=True)
    result['nodes'] = [{**node, 'name': node.get('label', node['id']),
                        'status': 'online' if node.get('online') else 'offline'}
                       for node in hub.fleet_nodes(refresh=refresh)]
    from symblic.providers import agent_teams as teams
    result['team_capabilities'] = teams.capability_catalog(result)
    result['nodes'] = result['team_capabilities']['nodes']
    result.update(home=hub._home(), modes=['agent', 'lines', 'qwen', 'team'], refreshing=bool(refresh),
                  refresh_note='Refresh requests queue background probes; this response is cached. A later cached response is not a completion acknowledgement.',
                  browser_models='retained catalogue; refresh models in the hub',
                  parallel_max=PARALLEL_MAX,
                  parallel_policy='lines mode only: 1 to %d line sessions run concurrently, each a fresh agent in the same workspace; capacity is bounded by agent admission' % PARALLEL_MAX,
                  context_policy='New agent session per instruction; only the instruction, explicit context and repository instructions are sent. Workspace files remain available.')
    return result


def native_completion(hub, agent):
    """Fresh native evidence only. A quiet terminal is never a completion event."""
    engine = agent.get('engine')
    if engine == 'triad' and agent.get('discrete'):
        try:
            receipt = hub.triad_discrete_status(agent)
        except Exception:
            return {'available': True, 'done': False, 'reason': 'Discrete stage receipt is temporarily unavailable.'}
        status = receipt.get('status')
        if not status and time.time() - float(agent.get('created') or time.time()) > 15:
            try:
                if hub.is_remote(agent):
                    _, _, current = hub._remote_state(agent['id'], agent, 1)
                else:
                    current = hub._current(agent['id'], agent)
                if current == 'gone' or current in hub._SHELLS:
                    return {'available': True, 'done': False, 'failed': True,
                            'reason': 'The discrete controller exited without a valid result receipt. Inspect its retained terminal output.'}
            except Exception:
                pass  # Unknown transport is not evidence of exit.
        return {'available': True, 'done': status == 'completed', 'failed': status == 'failed',
                'unknown': status == 'unknown', 'receipt': receipt,
                'reason': receipt.get('error') or ('Waiting for a durable discrete result.' if not status else
                          'Discrete workflow: ' + status + '. A review acceptance is not an independent correctness proof.')}
    if hub.is_remote(agent) or engine not in ('claude', 'codex', 'agy'):
        return {'available': False, 'done': False,
                'reason': 'Inspect this agent result and choose Next / Finish; no native completion adapter for this placement.'}
    # On the original host this was the terminal multiplexer's idle detector for the agent's session; a hub
    # passes it in as native_turn(agent) -> {'ready': bool, 'fingerprint': str} (absent: no evidence).
    observe = getattr(hub, 'native_turn', None)
    if observe is None:
        return {'available': True, 'done': False, 'reason': 'Native completion evidence is unavailable.'}
    try:
        seen = observe(agent) or {}
        if seen.get('ready'):
            return {'available': True, 'done': True, 'kind': 'native_turn', 'fingerprint': seen.get('fingerprint'),
                    'reason': 'Native agent turn finished; objective correctness has not been independently checked.'}
        return {'available': True, 'done': False, 'reason': 'Waiting for native completion evidence.'}
    except (OSError, ValueError, RuntimeError):
        return {'available': True, 'done': False, 'reason': 'Native completion evidence is unavailable.'}


def refusal_reason(evidence):
    """A refusal marker in the ended terminal, with no work on disk: the launch refused itself."""
    tail = str((evidence or {}).get('tail') or '')
    match = REFUSAL_TEXT.search(tail)
    if not match:
        return ''
    changes = (evidence or {}).get('changes')
    if changes is not None and changes.get('files_changed'):
        return ''  # the agent changed files; the wording alone does not prove a refusal
    line = next((part.strip() for part in tail.splitlines() if REFUSAL_TEXT.search(part)), match.group(0))
    return 'The agent refused its own launch: ' + line[:240]


class TaskManager:
    """Durable line-by-line agent tasks over the host's agent hub (see the module docstring)."""

    def __init__(self, root, *, hub=None, completion=None, background=True, check_host=execution_fence):
        self.root = Path(root) / 'state' / 'tasks'
        self.hub = hub
        self.completion = completion or native_completion
        self.background = background
        self.check_host = check_host

    def _hub(self):
        if self.hub is None:
            raise TaskError('No agent hub was given: TaskManager(root, hub=...) needs the host\'s hub object.', 503)
        return self.hub

    def _path(self, task_id):
        if not isinstance(task_id, str) or not ID.fullmatch(task_id):
            raise TaskError('Invalid task id.')
        return self.root / (task_id + '.json')

    @contextmanager
    def _lock(self, task_id, worker=False, blocking=True):
        self._path(task_id)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / (task_id + ('.worker.lock' if worker else '.lock'))
        with path.open('a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _read(self, task_id):
        try:
            row = json.loads(self._path(task_id).read_text())
        except FileNotFoundError:
            raise TaskError('Task not found.', 404) from None
        except (ValueError, OSError):
            raise TaskError('Task receipt is unreadable; execution is fenced.', 409) from None
        if (not isinstance(row, dict) or row.get('id') != task_id or
                not isinstance(row.get('options'), dict) or not isinstance(row.get('steps'), list) or
                not row['steps'] or not isinstance(row.get('request_digest'), str) or
                not isinstance(row.get('context_note'), str) or
                any(not isinstance(step, dict) or step.get('index') != index or
                    not isinstance(step.get('instruction'), str) or
                    step.get('group') != f'symblic-{task_id}-{index}' or
                    step.get('status') not in {'queued', 'dispatching', 'active', 'awaiting_review', 'finishing',
                                               'completed', 'cancelled', 'failed', 'unknown'}
                    for index, step in enumerate(row['steps']))):
            raise TaskError('Task receipt is invalid; execution is fenced.', 409)
        if row.get('mode') == 'team':
            from symblic.providers import agent_teams as teams
            try:
                selected = teams.normalize(row.get('team'), lane='project')
                inputs = [line for line in row['instruction'].splitlines() if line.strip()] if row.get('fresh_lines') else [row['instruction']]
                expected = [(line_no, line, member) for line_no, line in enumerate(inputs) for member in selected['members']]
                payload = {key: row[key] for key in ('instruction', 'mode', 'options', 'context_note', 'team', 'team_sha256', 'team_policy')}
                if row.get('fresh_lines'):
                    payload['fresh_lines'] = True
                valid = (selected == row['team'] and teams.digest(selected) == row['team_sha256']
                    and hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest() == row['request_digest']
                    and len(expected) == len(row['steps'])
                    and all(step.get('instruction_index') == line_no and step['instruction'] == line and step.get('member') == member
                            for step, (line_no, line, member) in zip(row['steps'], expected)))
            except (ValueError, KeyError, TypeError):
                valid = False
            if not valid:
                raise TaskError('Configured team receipt identity changed; execution is fenced.', 409)
        return row

    def _write(self, row):
        row['updated'] = time.time()
        row['revision'] = int(row.get('revision', 0)) + 1
        atomic_json(self._path(row['id']), row)

    def submit(self, body):
        self.check_host()
        if not isinstance(body, dict):
            raise TaskError('Submit a JSON object.')
        # A mistyped envelope (an options object nested where the flat fields belong, a
        # renamed key) used to pass silently and fail later on a missing field; refuse it
        # here, naming what the caller sent, before any identity is reserved.
        unknown = sorted(set(body) - (set(OPTIONS) | {'client_request_id', 'request_id', 'instruction',
                                                      'mode', 'fresh_lines', 'team', 'context_note'}))
        if unknown:
            raise TaskError('Unknown task field' + ('s' if len(unknown) > 1 else '') + ' '
                            + ', '.join(unknown) + '. Options (' + ', '.join(OPTIONS)
                            + ') are top-level fields, never nested under "options".')
        request_id = body.get('client_request_id') or body.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', request_id):
            raise TaskError('A stable client_request_id is required (letters, digits, dot, colon, underscore or hyphen).')
        instruction = body.get('instruction')
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 60000 or '\0' in instruction:
            raise TaskError('Enter an instruction between 1 and 60000 characters.')
        mode = body.get('mode', 'agent')
        if mode not in ('agent', 'lines', 'qwen', 'team'):
            raise TaskError('Choose agent, lines, qwen or team mode.')
        fresh_lines = body.get('fresh_lines', False)
        if not isinstance(fresh_lines, bool) or (fresh_lines and mode not in ('qwen', 'team')):
            raise TaskError('New team for each line is a boolean option for Qwen or configured team mode.')
        options = {key: body[key] for key in OPTIONS if key in body}
        selected_team = None
        if mode == 'team':
            from symblic.providers import agent_teams as teams
            try:
                selected_team = teams.normalize(body.get('team'), lane='project')
            except teams.TeamError as exc:
                raise TaskError(str(exc)) from None
            if any(key in options for key in ('roles', 'council', 'squad', 'discrete')):
                raise TaskError('Configured project teams contain individual coding agents. Use the dedicated pipeline, council or squad controls for nested orchestrators.')
            first = selected_team['members'][0]
            options.update(engine={'ollama': 'local', 'chatgpt': 'gpt'}.get(first['engine'], first['engine']),
                           node=first['node'], model=first['model'], effort=first['effort'])
        elif 'team' in body:
            raise TaskError('A configured project team requires mode: team; no team was silently ignored.')
        options.setdefault('auto', True)
        options.setdefault('worktree', False)
        for key in ('engine', 'model', 'effort', 'node', 'cwd'):
            if key in options and not isinstance(options[key], str):
                raise TaskError(f'{key} must be text.')
        if not options.get('node', '').strip():
            raise TaskError('Select the execution machine explicitly.')
        if not options.get('cwd', '').strip():
            raise TaskError('Select the execution workspace explicitly; create one first (workspace/create). '
                            'An empty folder choice would silently run in the home folder.')
        for key in ('roles', 'council', 'squad'):
            if key in options and not isinstance(options[key], dict):
                raise TaskError(f'{key} must be an object.')
        for key in ('auto', 'worktree', 'workingDefaults', 'deepResearch', 'discrete', 'headless', 'auto_next'):
            if key in options and not isinstance(options[key], bool):
                raise TaskError(f'{key} must be true or false.')
        if options.get('auto_next') and mode not in ('lines', 'agent'):
            raise TaskError('auto_next advances fresh lines on evidence; Qwen and team flows keep their own review gates.')
        if 'parallel' in options:
            # Independent lines are the only shape that can run side by side: team lanes
            # chain workspaces and every other mode is one instruction or one sequence.
            if (isinstance(options['parallel'], bool) or not isinstance(options['parallel'], int)
                    or not 1 <= options['parallel'] <= PARALLEL_MAX):
                raise TaskError(f'parallel is an integer from 1 to {PARALLEL_MAX}: how many line sessions '
                                'run at the same time.')
            if options['parallel'] > 1 and (mode != 'lines' or fresh_lines):
                raise TaskError('Parallel lines are a lines-mode option; sequential flows keep one session at a time.')
        note = body.get('context_note', '')
        if not isinstance(note, str) or len(note) > 12000:
            raise TaskError('Context note must be text under 12000 characters.')
        hub = self._hub()
        if mode == 'qwen':
            roles = options.get('roles') or {}
            if not isinstance(roles, dict):
                raise TaskError('Qwen roles must be an object.')
            selected = {}
            for role, key in (('mastermind', 'mastermind_model'), ('implementer', 'implementer_model'), ('ai_review', 'review_model')):
                model = roles.get(key) or options.get('model') or ''
                if not isinstance(model, str) or 'qwen' not in model.lower() or not hub.MODEL_RX.fullmatch(model):
                    raise TaskError('Choose an installed Qwen model for each of the three seats.')
                selected.update({role: 'ollama', key: model})
            options.update(engine='triad', roles=selected, model='', discrete=True)
            if not options.get('node'):
                raise TaskError('Select the machine explicitly for the three Qwen seats.')
        if options.get('discrete') and not options.get('auto'):
            raise TaskError('Three Qwen discrete execution requires Auto. Choose the ordinary three-agent pipeline for interactive tool approvals.')
        if options.get('engine') not in hub.ENGINES:
            raise TaskError('Choose an agent from the current Agents catalogue.')
        if selected_team and any({'ollama': 'local', 'chatgpt': 'gpt'}.get(member['engine'], member['engine']) not in hub.ENGINES
                                 for member in selected_team['members']):
            raise TaskError('A selected team engine is absent from the current Agents catalogue.')
        lines = [line for line in instruction.splitlines() if line.strip()] if mode == 'lines' or fresh_lines else [instruction]
        if len(lines) > 64:
            raise TaskError('Use at most 64 nonblank instruction lines per task.')
        step_inputs = ([{'instruction': line, 'instruction_index': line_no, 'member': member}
                        for line_no, line in enumerate(lines) for member in selected_team['members']]
                       if selected_team else [{'instruction': line} for line in lines])
        if any(len(self._prompt({'context_note': note}, item)) > getattr(hub, 'MAX_PROMPT', 60000) for item in step_inputs):
            raise TaskError('The instruction plus explicit context exceeds the agent prompt limit.')
        if options.get('discrete') and any(len(self._prompt({'context_note': note}, {'instruction': line})) > 20000 for line in lines):
            raise TaskError('Each discrete team instruction, including shared context, must fit 20000 characters; split larger work into fresh lines.')
        payload = {'instruction': instruction, 'mode': mode, 'options': options, 'context_note': note}
        if fresh_lines:
            payload['fresh_lines'] = True
        if selected_team:
            payload.update(team=selected_team, team_sha256=teams.digest(selected_team),
                team_policy={'version': 1, 'strategy': 'sequential_members', 'fresh_context': True,
                    'workspace': 'per_device', 'cross_device_file_transfer': False,
                    'peer_chat': False, 'planned_sessions': len(step_inputs),
                    'acceptance': 'native_turn_or_explicit_owner_finish_not_objective_proof'})
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        task_id = 'task-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
        with self._lock(task_id):
            if self._path(task_id).exists():
                row = self._read(task_id)
                if row['request_digest'] != digest:
                    raise TaskError('This request id already belongs to different instructions or options.', 409)
                return {'task': row, 'duplicate': True}
            row = {'id': task_id, 'client_request_id': request_id, 'request_digest': digest,
                   **payload, 'created': time.time(), 'status': 'queued', 'error': '', 'cancel_requested': False,
                   'steps': [{'index': i, **item, 'status': 'queued',
                              'group': f'symblic-{task_id}-{i}', 'agent_id': '', 'url': ''}
                             for i, item in enumerate(step_inputs)]}
            self._write(row)  # durable identity BEFORE thread creation or agent launch
        self._schedule(task_id)
        return {'task': row, 'duplicate': False}

    def _schedule(self, task_id):
        if self.background:
            threading.Thread(target=self._worker, args=(task_id,), name='symblic-task-' + task_id[-8:], daemon=True).start()

    def _worker(self, task_id):
        with self._lock(task_id, worker=True) as owned:
            if not owned:
                return
            while True:
                try:
                    keep_going = self.advance(task_id)
                except Exception as exc:
                    with self._lock(task_id):
                        row = self._read(task_id)
                        row.update(status='unknown', error=f'Coordinator interrupted: {type(exc).__name__}. Inspect the linked agent before continuing.')
                        self._write(row)
                    return
                if not keep_going:
                    return
                try:
                    busy = self._busy(self._read(task_id))
                except TaskError:
                    return
                if self._sleep_unless_yield(task_id, 3 if busy else self.GATED_POLL_SECONDS):
                    return

    def _sleep_unless_yield(self, task_id, seconds):
        """Sleep in one-second slices; True when the operator asked for the worker lease (Next on a
        gated line whose agent still runs): the lease must be free for the finish action."""
        for _ in range(max(1, int(seconds))):
            try:
                if self._read(task_id).get('yield_requested'):
                    return True
            except TaskError:
                return True
            time.sleep(1)
        return False

    def advance(self, task_id):
        """One admitted pass. Tests inject the hub and drive this synchronously.

        Lines mode with options.parallel > 1 runs up to that many line sessions at
        once: every pass launches queued lines while capacity remains and observes
        every active line. Every other mode keeps the one-action-per-pass behaviour
        it has always had (cap 1), because their lanes chain context or workspaces.
        """
        self.check_host()
        with self._lock(task_id):
            row = self._read(task_id)
            if row['status'] in TERMINAL:
                return False
            if row['cancel_requested']:
                step = next((s for s in row['steps'] if s['status'] != 'completed'), None)
                plan = [('cancel', step['index'])] if step is not None else []
            else:
                cap = self._parallel_cap(row)
                # A step under the operator's review gate still holds its live agent
                # session and its workspace: the next line of a lines task chains
                # that same workspace, and launching into it while the previous
                # agent still runs is refused by the hub (a remote start) or
                # races it (a local one). Only a completed step releases its slot.
                in_flight = sum(1 for s in row['steps']
                                if s['status'] in ('dispatching', 'active', 'awaiting_review'))
                plan = [('launch', s['index']) for s in row['steps']
                        if s['status'] == 'queued'][:max(0, cap - in_flight)]
                plan += [('observe', s['index']) for s in row['steps']
                         if s['status'] in ('active', 'awaiting_review')]
                if not plan:
                    # Nothing to launch or observe: either every line finished, or the
                    # remaining steps wait on the operator (review, recovery). Both stop
                    # the coordinator; control re-schedules it when the operator answers.
                    if self._finalize_if_done(row):
                        self._write(row)
                    return False
        for action, index in plan:
            self._advance_one(task_id, action, index)
        with self._lock(task_id):
            row = self._read(task_id)
            if row['status'] in TERMINAL:
                return False
            if self._finalize_if_done(row):
                # The last line finished during THIS pass. The background worker stops as
                # soon as a pass reports nothing left to drive, so the completion must be
                # recorded here: a task whose every step was complete stayed `queued` for
                # hours (observed 2026-10-10, seven lines tasks) when it was left to the
                # next pass that never came.
                self._write(row)
                return False
            return self._driving(row)

    @staticmethod
    def _driving(row):
        """True while a pass can still change something: a line to launch or observe, or a
        gated line whose agent is still running (its turn end and refusal are worth seeing)."""
        return any(s['status'] in ('queued', 'dispatching', 'active')
                   or (s['status'] == 'awaiting_review' and s.get('running'))
                   for s in row['steps'])

    @staticmethod
    def _busy(row):
        """A line is being launched or driven (poll fast); gated-but-running lines poll slowly."""
        return any(s['status'] in ('queued', 'dispatching', 'active') for s in row['steps'])

    @staticmethod
    def _finalize_if_done(row):
        """Pure: a task whose steps are all completed is completed; one with nothing left to drive
        and a failed line is failed, naming the lines. True when the row changed."""
        if row['status'] in TERMINAL or not row['steps']:
            return False
        statuses = [s['status'] for s in row['steps']]
        if all(st == 'completed' for st in statuses):
            row.update(status='completed',
                       completion='Agent turns finished; review files and tests for objective acceptance.')
            return True
        if 'failed' in statuses and not any(st in ('queued', 'dispatching', 'active', 'awaiting_review', 'finishing')
                                            for st in statuses):
            # Mixed outcomes used to leave the task `queued` forever with "resume required"
            # (two tasks of 2026-10-09: lines 1 and 3 completed, line 2 failed).
            failed = [str(s['index']) for s in row['steps'] if s['status'] == 'failed']
            row.update(status='failed', error='Line' + ('s ' if len(failed) > 1 else ' ') + ', '.join(failed)
                       + ' failed; the other lines finished. Nothing is left to launch.')
            return True
        return False

    @staticmethod
    def _parallel_cap(row):
        """Concurrent line sessions admitted for this task; 1 for every sequential flow."""
        if row.get('mode') != 'lines' or row.get('fresh_lines') or row.get('team'):
            return 1
        try:
            value = int(row['options'].get('parallel') or 1)
        except (TypeError, ValueError):
            return 1
        return max(1, min(PARALLEL_MAX, value))

    def _advance_one(self, task_id, action, index):
        """Launch, observe or cancel one step. The caller owns the pass loop and the
        decision to keep polling; every branch here is the admitted transition it
        has always been, re-read from the receipt so a concurrent operator action
        (Next, cancel) can never be replayed against stale state."""
        hub = self._hub()
        with self._lock(task_id):
            row = self._read(task_id)
            if index >= len(row['steps']):
                return True
            step = row['steps'][index]
            if action == 'launch' and step['status'] == 'queued':
                step['status'] = row['status'] = 'dispatching'
                self._write(row)
            elif action == 'cancel':
                pass
            elif action != 'observe' or step['status'] not in ('active', 'awaiting_review'):
                return True
        if action == 'cancel':
            return self._cancel_owned(task_id, step)
        if action == 'launch':
            options = dict(row['options'])
            if row.get('team'):
                member = step['member']
                options.update(engine={'ollama': 'local', 'chatgpt': 'gpt'}.get(member['engine'], member['engine']),
                               node=member['node'], model=member['model'], effort=member['effort'])
                prior = next((item for item in reversed(row['steps'][:index])
                              if item.get('member', {}).get('node') == member['node']
                              and item['status'] == 'completed'), None)
                if prior and options['node'] != hub.LOCAL_NODE:
                    options['workspaceFrom'] = prior['agent_id']
                elif prior:
                    workspace = prior.get('workspace') or prior.get('agent', {}).get('cwd')
                    if not workspace:
                        raise TaskError('The preceding member workspace is unknown; no new agent was launched.', 409)
                    options.update(cwd=workspace, worktree=False)
            elif index:
                if options.get('node', hub.LOCAL_NODE) != hub.LOCAL_NODE:
                    options['workspaceFrom'] = row['steps'][index - 1]['agent_id']
                elif row.get('workspace'):
                    options.update(cwd=row['workspace'], worktree=False)
            options['prompt'] = self._prompt(row, step)
            # Name the hub agent after the instruction, not the fixed wrapper: every Symblic
            # agent used to be "execute-instruction-N", unreadable on cards and in history.
            options['name'] = step['instruction'][:120]
            try:
                result = hub.start(options, group=step['group'])
                agent = result.get('agent') or {}
                if not agent.get('id'):
                    raise RuntimeError('Agent launch returned no identity')
            except Exception as exc:
                with self._lock(task_id):
                    row = self._read(task_id)
                    # Only a proven refusal shows failure: the hub marks its refusals, and an
                    # exception with no persisted group agent proves nothing was started.
                    started = self._group_agents(hub, step['group'])
                    status = ('failed' if getattr(exc, 'refused', False) is True or started == []
                              else 'unknown')
                    row.update(status=status, error=str(exc))
                    row['steps'][index].update(status=status, error=str(exc))
                    self._write(row)
                return False
            with self._lock(task_id):
                row = self._read(task_id)
                row['steps'][index].update(status='active', agent_id=agent['id'], agent=agent,
                                           url=result.get('url', ''), started=time.time(),
                                           workspace=agent.get('cwd') or options.get('cwd'),
                                           baseline=self._baseline(hub, agent))
                row.update(status='active', workspace=agent.get('cwd') or options.get('cwd'))
                self._write(row)
            return True
        if step.get('status') == 'active' and row.get('options', {}).get('auto') and step.get('agent_id'):
            # A fresh workspace can ask the folder-trust question before its first turn; the
            # hub's auto-trust watcher (a page in the host) is not polling for a headless task agent.
            trust = getattr(hub, 'answer_trust_for', None)
            if trust:
                try:
                    trust(step['agent_id'])
                except Exception:
                    pass
        outcome = self.completion(hub, step['agent'])
        workspace = None
        if outcome.get('done') and self._needs_native_workspace(row, step, hub):
            try:
                git = hub._git_info(step['agent']) or {}
                workspace = git.get('cwd') or git.get('worktree')
            except Exception:
                workspace = None
            if not workspace:
                outcome = {'available': True, 'done': False, 'unknown': True,
                           'reason': 'The three-agent pipeline finished, but its native workspace identity could not be verified. The next instruction was not launched.'}
        evidence, refusal, turn = None, '', None
        if outcome.get('done'):
            # Capture the final terminal text while the pane still holds it, before Stop.
            evidence = self._step_evidence(hub, step)
        elif not (outcome.get('failed') or outcome.get('unknown')):
            turn = self._turn_ended(hub, step)
            if turn:
                evidence = self._step_evidence(hub, step)
                refusal = refusal_reason(evidence)
        if outcome.get('done') or refusal or outcome.get('failed'):
            try:
                hub.stop(step['agent_id'])
            except Exception:
                with self._lock(task_id):
                    row = self._read(task_id)
                    row['steps'][index]['status'] = 'unknown'
                    row.update(status='unknown', error='Native turn finished, but the prior agent could not be stopped. The next instruction was not launched.')
                    self._write(row)
                return False
        with self._lock(task_id):
            row = self._read(task_id)
            current = row['steps'][index]
            if current['status'] not in ('active', 'awaiting_review'):
                return True
            # A plain agent lane with no completion evidence for a long time is not
            # failed (long turns and background work are legal), but the record must
            # say so: a launch that died before its first turn (observed: an engine
            # eligibility 503, a killed unbounded background search) otherwise looks
            # identical to progress. Discrete triad steps are exempt; their long
            # build/review rounds are normal. Purely advisory: no status change, no
            # agent interaction, cleared as soon as evidence or a terminal state lands.
            stalled_now = (bool(current.get('started'))
                          and not (current.get('agent') or {}).get('discrete')
                          and time.time() - float(current['started']) > STALL_HINT_SECONDS
                          and not outcome.get('done') and not outcome.get('failed')
                          and not outcome.get('unknown') and evidence is None and not refusal)
            if (not outcome.get('done') and not outcome.get('failed') and not outcome.get('unknown')
                    and current.get('completion') == outcome and evidence is None
                    and bool(current.get('stalled')) == stalled_now):
                return True if turn is False else bool(outcome.get('available'))
            current['completion'] = outcome
            if evidence is not None:
                current['evidence'] = evidence
            if stalled_now:
                current['stalled'] = True
                row['stalled_hint'] = STALL_HINT
            else:
                current.pop('stalled', None)
                row.pop('stalled_hint', None)
            # A gated step whose agent demonstrably still runs keeps being observed (at the
            # slow cadence): before, the coordinator stopped at the first gate, so a remote line
            # that later finished or refused its launch was never seen (2026-10-10).
            if turn is False:
                current['running'] = True
            elif turn is not None or evidence is not None or outcome.get('done'):
                current.pop('running', None)
            if outcome.get('failed') or outcome.get('unknown'):
                current['status'] = row['status'] = 'unknown' if outcome.get('unknown') else 'failed'
                row['error'] = outcome.get('reason') or 'The discrete workflow did not produce an accepted result.'
                self._write(row)
                return False
            if refusal:
                current.update(status='failed', error=refusal)
                row.update(status='failed', error=refusal)
                self._write(row)
                return False
            if outcome.get('done'):
                if workspace:
                    row['workspace'] = workspace
                current.update(status='completed', finished=time.time())
                row['status'] = 'queued'
            elif evidence is not None and self._auto_next_ok(row, current, evidence, refusal):
                # auto_next: the turn ended (the process exited) with evidence, no refusal and
                # no claim the disk contradicts, so the line is accepted the way the operator's
                # Next would accept it, and the next line launches without anyone at the page
                # (unattended remote lines, 2026-10-10). Objective correctness is still the
                # statements' own verify line's job.
                current.update(status='completed', finished=time.time(),
                               completion={'kind': 'auto_next', 'done': True,
                                           'reason': 'The turn ended with durable evidence; auto_next accepted it. '
                                                     'Objective correctness has not been independently checked.'})
                row['status'] = 'queued'
                self._write(row)
                stop_error = ''
                try:
                    hub.stop(step['agent_id'])
                except Exception as exc:
                    stop_error = str(exc)
                if stop_error:
                    with self._lock(task_id):
                        row = self._read(task_id)
                        row['steps'][index].update(status='unknown', error=stop_error)
                        row.update(status='unknown', error='auto_next could not confirm the prior agent stopped; the next line was not launched.')
                        self._write(row)
                    return False
                return True
            elif evidence is not None or not outcome.get('available'):
                # The operator's review gate: the turn ended with durable evidence, or this
                # placement has no native completion adapter (a TUI agent's process never
                # ends its turn from here, so the operator decides when the step is done).
                # Nothing is auto-applied.
                current['status'] = row['status'] = 'awaiting_review'
            self._write(row)
            if outcome.get('done'):
                return True
            if evidence is not None:
                return False
            if turn is False:
                return True
            return bool(outcome.get('available'))

    @staticmethod
    def _auto_next_ok(row, step, evidence, refusal):
        """Pure: an ended turn may be accepted unattended only when the task asked for it, the agent
        did not refuse its launch, and no success claim contradicts the disk."""
        if not row.get('options', {}).get('auto_next') or refusal:
            return False
        if step.get('status') not in ('active', 'awaiting_review'):
            return False
        return not (evidence or {}).get('warning')

    @staticmethod
    def _needs_native_workspace(row, step, hub):
        return (step['index'] == 0 and row['options'].get('engine') == 'triad'
                and row['options'].get('worktree') and row['options'].get('node') == hub.LOCAL_NODE)

    @staticmethod
    def _placement(hub, agent):
        """True/False for remote/local placement; None when the hub cannot say."""
        try:
            return bool(hub.is_remote(agent))
        except Exception:
            return None

    @staticmethod
    def _turn_ended(hub, step):
        """True when the agent process itself exited, False while it runs, None when unknown."""
        agent = step.get('agent') or {}
        if not step.get('agent_id') or not agent:
            return None
        try:
            if hub.is_remote(agent):
                alive, _, current = hub._remote_state(step['agent_id'], agent, 1)
                if current == 'gone':
                    return True
                if alive and current and current != 'agent':
                    return True
                return None if not alive and not current else False
            current = hub._current(step['agent_id'], agent)
            if current == 'agent':
                return False
            if current == 'gone' or current in getattr(hub, '_SHELLS', ()):
                return True
        except Exception:
            return None
        return None

    @staticmethod
    def _screen_tail(hub, step):
        """Bounded final terminal text; a missing transcript is not evidence of failure."""
        if not step.get('agent_id'):
            return ''
        try:
            observed = hub.screen(step['agent_id'])
            if not observed.get('alive') and not observed.get('screen'):
                observed = {**hub.history_text(step['agent_id']), 'alive': False}
            return str(observed.get('screen') or '')[-EVIDENCE_TAIL:]
        except Exception:
            try:
                return str((hub.history_text(step['agent_id']) or {}).get('screen') or '')[-EVIDENCE_TAIL:]
            except Exception:
                return ''

    def _baseline(self, hub, agent):
        """Bounded workspace snapshot at launch; completion cross-checks diff against it."""
        if self._placement(hub, agent) is False:
            return workspace_inventory(agent.get('cwd'))
        return {'available': False, 'reason': 'The workspace is not on this host; no launch snapshot was taken.'}

    def _step_evidence(self, hub, step):
        """Durable completion evidence: final tail, bounded inventory, claim-vs-disk."""
        agent = step.get('agent') or {}
        placement = self._placement(hub, agent)
        tail = self._screen_tail(hub, step)
        if placement is False:
            inventory = workspace_inventory(step.get('workspace') or agent.get('cwd'))
        else:
            inventory = {'available': False,
                         'reason': 'The workspace is on another machine or its placement is unknown; '
                                   'its files cannot be inventoried from this host.'}
        changes = inventory_changes(step.get('baseline'), inventory)
        claims = claimed_work(tail)
        warning = ''
        if claims['claimed'] and changes is not None and changes['files_changed'] == 0:
            warning = ('The agent reported completed work, but no workspace file changed since launch; '
                       'inspect its terminal and the workspace before accepting this result.')
        return {'kind': 'disk_cross_check', 'captured': time.time(), 'tail': tail,
                'inventory': inventory, 'changes': changes, 'claims': claims, 'warning': warning}

    @staticmethod
    def _group_agents(hub, group):
        """Persisted hub agents for one step group; an unreadable store proves nothing."""
        try:
            return [a for a in (hub._load() or {}).get('agents', []) if a.get('group') == group]
        except Exception:
            return None


    @staticmethod
    def _prompt(row, step):
        note = row['context_note']
        prompt = ('Execute this instruction in the selected workspace. This is a fresh Symblic task; '
                'no earlier conversation is supplied. Follow repository instructions. Stay inside the '
                'folder the instruction names and edit only the files it names; start no background '
                'searches. Report files changed, checks run and remaining problems. Do not claim '
                'completion from a plan alone. '
                'For source navigation, optionally check command -v symblic-context, then use '
                'symblic-context pack --root PROJECT --file relative.py --query literal. '
                'Select relevant files explicitly; do not index histories or the whole filesystem. '
                'If a skill named use-symblic is available to you, it explains this task shape.\n\n'
                + step['instruction'] + ('\n\nExplicit context:\n' + note if note else ''))
        if step.get('member'):
            from symblic.providers import agent_teams as teams
            prompt = teams.member_system(step['member'], prompt, lane='project')
            prompt += ('\nThis is one sequential project-team member. Workspace files are shared only with earlier '
                       'members on this same device. Other devices have separate checkouts; no implicit file transfer or '
                       'prior member chat is supplied. Inspect actual files and checks instead of assuming another member completed work.')
        return prompt

    def _cancel_owned(self, task_id, step):
        error = ''
        if step.get('agent_id'):
            try:
                self._hub().stop(step['agent_id'])
            except Exception as exc:
                error = str(exc)
        elif step['status'] in ('dispatching', 'unknown'):
            error = 'Launch outcome is unknown; inspect Agents before acknowledging cancellation.'
        with self._lock(task_id):
            row = self._read(task_id)
            row.update(status='unknown' if error else 'cancelled', error=error,
                       cancellation_scope='Task coordinator and its owned agent terminal; external provider work may continue.')
            for item in row['steps']:
                if item['status'] != 'completed':
                    item['status'] = 'unknown' if error and item['index'] == step['index'] else 'cancelled'
            self._write(row)
        return False

    def get(self, task_id, include_screen=False):
        row = self._read(task_id)
        with self._lock(task_id, worker=True, blocking=False) as idle:
            if idle and row['status'] == 'queued' and self._finalize_if_done(row):
                # Self-heal a record left `queued` by an earlier coordinator that stopped
                # right after its last step completed: no agent is touched, nothing is
                # replayed; the terminal state is derived from the steps alone.
                with self._lock(task_id):
                    row = self._read(task_id)
                    if self._finalize_if_done(row):
                        self._write(row)
            row['resume_required'] = idle and (row['status'] in ('active', 'queued', 'dispatching') or self._gated_live(row))
            if idle and row['status'] in ('dispatching', 'finishing'):
                with self._lock(task_id):
                    row = self._read(task_id)
                    for step in row['steps']:
                        if step['status'] in ('dispatching', 'finishing'):
                            step['status'] = 'unknown'
                    row.update(status='unknown', resume_required=True,
                               error='The coordinator stopped during an external action. Recover the existing agent; the instruction will not be replayed.')
                    self._write(row)
        if include_screen:
            step = next((s for s in reversed(row['steps']) if s.get('agent_id')), None)
            if step:
                try:
                    observed = self._hub().screen(step['agent_id'])
                    if not observed.get('alive') and not observed.get('screen'):
                        observed = {**self._hub().history_text(step['agent_id']), 'alive': False}
                    row.update(screen=str(observed.get('screen') or '')[-16000:],
                               agent_alive=observed.get('alive'))
                except Exception:
                    row['screen_error'] = 'The agent terminal could not be read. Its task receipt is retained.'
        return row

    def listing(self):
        if not self.root.exists():
            return []
        paths = sorted(self.root.glob('task-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        rows = [self.get(path.stem) for path in paths if ID.fullmatch(path.stem)]
        for row in rows:
            self._resume_stranded(row)
        return rows

    RESUME_WINDOW = 2 * 3600           # a coordinator is re-attached only to work updated recently
    GATED_POLL_SECONDS = 20            # a gated line with a live agent: one remote probe per 20 s
    YIELD_WAIT_SECONDS = 8             # how long Next waits for a watching coordinator to yield its lease

    def _resume_stranded(self, row):
        """Re-attach a coordinator to a task the process restart left without one.

        Resume semantics only: existing agents are observed, queued lines that never had an
        agent are launched; a `dispatching`/`finishing` step (an action in flight when the
        process died) was already fenced to `unknown` by get(). Nothing is replayed. Before
        this, every restart of the host process stranded running tasks until the operator
        pressed Resume (observed 2026-10-10).
        """
        if not self.background or not row.get('resume_required'):
            return
        if (row.get('status') not in ('queued', 'active') and not self._gated_live(row)) or row.get('cancel_requested'):
            return
        try:
            # The last recorded change, not the creation time: a task abandoned yesterday with a
            # failed line is the operator's to resume, never the listing's.
            if time.time() - float(row.get('updated') or row.get('created') or 0) > self.RESUME_WINDOW:
                return
        except (TypeError, ValueError):
            return
        try:
            self.check_host()
        except TaskError:
            return
        with self._lock(row['id']):
            current = self._read(row['id'])
            if current['status'] not in ('queued', 'active') and not self._gated_live(current):
                return
            current['resumed'] = {'at': time.time(), 'by': 'listing', 'reason': 'coordinator absent after a restart'}
            self._write(current)
        self._schedule(row['id'])

    @staticmethod
    def _gated_live(row):
        """A line under the operator's review gate whose agent still runs and has produced no
        evidence: its coordinator was still probing the remote turn (GATED_POLL_SECONDS) when the
        process died, so it is re-attached like an active line (2026-10-11)."""
        return any(s.get('status') == 'awaiting_review' and s.get('running') and s.get('evidence') is None
                   and not (s.get('completion') or {}).get('done') and s.get('agent_id') for s in row.get('steps') or [])

    def control(self, task_id, action):
        self.check_host()
        if action not in ('cancel', 'next', 'resume'):
            raise TaskError('Choose cancel, next or resume.')
        if action == 'next':
            # Finish is an external action, just like worker dispatch. Hold the
            # same process-safe ownership lease until Stop and its receipt are
            # complete, so polling cannot mistake a live action for a crash.
            # A coordinator that only watches a gated line with a live agent holds
            # the lease too (2026-10-10): ask it to yield and wait a bounded time.
            deadline = time.time() + self.YIELD_WAIT_SECONDS
            asked = False
            while True:
                with self._lock(task_id, worker=True, blocking=False) as owned:
                    if owned:
                        if asked:
                            with self._lock(task_id):
                                row = self._read(task_id)
                                row.pop('yield_requested', None)
                                self._write(row)
                        return self._control(task_id, action)
                if not asked:
                    with self._lock(task_id):
                        row = self._read(task_id)
                        if not any(s['status'] == 'awaiting_review' for s in row['steps']):
                            raise TaskError('The coordinator is still handling this task. Refresh before finishing the step.', 409)
                        row['yield_requested'] = True
                        self._write(row)
                    asked = True
                if time.time() > deadline:
                    raise TaskError('The coordinator is still handling this task. Refresh before finishing the step.', 409)
                time.sleep(0.5)
        return self._control(task_id, action)

    def _control(self, task_id, action):
        with self._lock(task_id):
            row = self._read(task_id)
            if action == 'cancel':
                if row['status'] in ('completed', 'cancelled'):
                    return {'task': row}
                row['cancel_requested'] = True
                # Leave dispatching intact until the original launch returns with its identity.
                if row['status'] != 'dispatching':
                    row['status'] = 'cancelling'
                self._write(row)
            elif action == 'next':
                # The first step actually holding the review gate. A permanently
                # failed step must not brick the gate for the healthy steps
                # behind it (a remote lines task burns a step when the hub
                # refuses to launch into a busy workspace).
                step = next((s for s in row['steps'] if s['status'] == 'awaiting_review'), None)
                if not step:
                    raise TaskError('Next requires an inspected result awaiting review; unfinished or unknown launches cannot advance.', 409)
                # The local three-agent pipeline creates its own checkout after hub.start returns;
                # the launch row initially names the source repository. Resolve
                # the native worktree before handing files to another fresh agent.
                if self._needs_native_workspace(row, step, self._hub()):
                    git = self._hub()._git_info(step['agent']) or {}
                    workspace = git.get('cwd') or git.get('worktree')
                    if not workspace:
                        raise TaskError('The three-agent pipeline has not published its workspace identity. Inspect its terminal before finishing this step.', 409)
                    row['workspace'] = workspace
                step['status'] = row['status'] = 'finishing'
                self._write(row)
            elif row['status'] in ('unknown', 'dispatching'):
                # A unique persisted group may identify a launch whose response was lost.
                step = next((s for s in row['steps'] if s['status'] in ('dispatching', 'unknown')), None)
                matches = [a for a in self._hub()._load()['agents'] if step and a.get('group') == step['group']]
                if len(matches) != 1:
                    raise TaskError('Launch outcome is unknown. No unique owned agent can be recovered; it will not be replayed.', 409)
                agent = matches[0]
                step.update(status='active', agent=agent, agent_id=agent['id'], workspace=agent.get('cwd'),
                            url=f'/terminal.html?session={agent["id"]}&node={self._hub().node_of(agent)}')
                row.update(status='active', error='',
                           workspace=agent.get('cwd') or row.get('workspace') or row['options'].get('cwd'))
                self._write(row)
        if action == 'next':
            # Acknowledgement also closes the prior task's execution surface. Files
            # remain, while a fresh session receives the next instruction only.
            evidence = self._step_evidence(self._hub(), step)  # the pane still holds the final text
            try:
                self._hub().stop(step['agent_id'])
            except Exception as exc:
                with self._lock(task_id):
                    row = self._read(task_id)
                    row['steps'][step['index']].update(status='unknown', error=str(exc))
                    row.update(status='unknown', error='Could not confirm the prior agent stopped; the next line was not launched.')
                    self._write(row)
                return {'task': row}
            with self._lock(task_id):
                row = self._read(task_id)
                row['steps'][step['index']].update(status='completed', finished=time.time(),
                                                  completion={'kind': 'owner_acknowledged', 'done': True},
                                                  evidence=evidence)
                row['steps'][step['index']].pop('running', None)
                row['status'] = 'queued'
                self._write(row)
        self._schedule(task_id)
        return {'task': self.get(task_id)}


class HubTaskRunner:
    """The TaskRunner protocol (symblic/autogen/runner.py) over a TaskManager and its hub.

    engines     the hub's engines that autogen attempts may use: the CLI coding agents and the
                local-model engine (the hub's orchestrators and browser engines are left out).
    local_node  the hub's own machine; nodes() is the hub's node list.
    promote     commit in the agent's checkout, then the hub's 3-way apply into the project.
    fetch_remote
                commit on the agent's node and fetch its branch; the hub keeps fetched branches
                under refs/agents-nodes/<node>/<branch> in the project repository.
    """

    AUTOGEN_ENGINES = ('agy', 'claude', 'codex', 'mistral', 'copilot', 'local')

    def __init__(self, tasks: TaskManager, hub=None):
        self.tasks = tasks
        self.hub = hub if hub is not None else tasks.hub

    @property
    def engines(self):
        return tuple(e for e in getattr(self.hub, 'ENGINES', ()) if e in self.AUTOGEN_ENGINES)

    @property
    def local_node(self):
        return str(getattr(self.hub, 'LOCAL_NODE', '') or '')

    def nodes(self):
        return list(self.hub.fleet_nodes(refresh=False))

    def submit(self, body):
        return self.tasks.submit(body)

    def get(self, task_id):
        return self.tasks.get(task_id)

    def control(self, task_id, action):
        return self.tasks.control(task_id, action)

    def advance(self, task_id):
        return self.tasks.advance(task_id)

    def reattach(self, task):
        return self.tasks._resume_stranded(task)

    def is_remote(self, agent):
        return bool(self.hub.is_remote(agent))

    def fetch_remote(self, agent_id):
        self.hub.work_action('commit', agent_id)
        agent = self.hub._find(agent_id) or {}
        git = agent.get('git') or {}
        remote = git.get('remote') or {}
        branch = remote.get('sourceBranch') or git.get('branch')
        if not branch:
            return {}
        return {'ref': f"refs/agents-nodes/{remote.get('node')}/{branch}", 'main_root': git.get('main_root') or '',
                'base_sha': git.get('base_sha') or ''}

    def promote(self, agent_id, message=''):
        self.hub.work_action('commit', agent_id)
        return self.hub.work_action('apply', agent_id)
