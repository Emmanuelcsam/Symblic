"""Autogen coordinator: the durable process that runs, checks and promotes agent attempts.

What it does
    One autogen run owns a tree of statement nodes (one per line of the task, plus the children
    of every split). For each node the coordinator asks the pure policy (symblic/autogen/policy.py)
    what to do next, launches attempts, verifies every finished attempt with code only (files
    exist and changed, syntax, the operator's commands, an optional generated test), promotes the
    first accepted attempt into the project folder, and records everything in a durable run record.
    Nothing here trusts an agent's words: a worker that says "done" with no file change, a split
    that drops a file, or a checkpoint that names files absent from disk is refused by code.

Two kinds of attempt
    Agent tasks   every attempt is one task of a TaskRunner (symblic/autogen/runner.py): a fresh
                  coding-agent session in its own git checkout, submitted with a deterministic
                  request id so a crash or restart can never launch the same attempt twice. The
                  attempt instruction is "localized" so it names that checkout ("the current
                  working folder"), never the project folder. Promotion goes through the runner
                  (commit in the agent's checkout, 3-way apply into the project), behind a durable
                  promotion intent.
    Kernel builds a `local` run's statement is one spec sheet, and every attempt is a build of it
                  on the kernel lane (symblic/autogen/kernel_lane.py, docs/reference/LOCAL-AUTOGEN.md):
                  a process with its own durable intent, run folder and pid file instead of a task.
                  The same decisions, verdicts and promotion apply.

Durable record
    <root>/state/autogen/<run id>.json (run ids look like autogen-<24 hex digits>) plus an
    append-only <run id>.events.jsonl whose seq is its line number. Every change is a
    read-modify-write under the run lock (_mutate); external actions (submit, cancel, close,
    promotion, checks) run outside the lock between a locked intent and a locked record, so a crash
    at any point leaves a state the next pass can finish or report.

What runs it
    A host process creates AutogenManager(root, task_runner=...) and calls submit(body); with
    background=True a daemon thread per run drives advance() until the run ends. Tests use
    background=False and call advance() by hand with fakes for the runner, the checks and the
    clock (tests/autogen/). Without a task_runner the manager uses KernelOnlyRunner(): only spec
    sheets on the kernel lane can run then.

Depends on
    The Python standard library, git, symblic.autogen.{policy,kernel_lane,runner,durable}, and, for
    model-written test scripts, the Landlock launcher symblic/sandbox/landlock.py (Linux only).

Status
    Experimental. The agent-task lane was exercised only with the original host's agent runner
    (integration/host/symblicos_tasks.py), which does not run elsewhere; here it is tested with
    fakes. See symblic/autogen/README.md for what was measured.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from symblic.autogen import policy as POLICY
from symblic.autogen import kernel_lane as KERNEL
from symblic.autogen.durable import atomic_json
from symblic.autogen.runner import KernelOnlyRunner, TaskError, deterministic_task_id, execution_fence

RUN_ID = re.compile(r'^autogen-[a-f0-9]{24}$')
TERMINAL = {'completed', 'failed', 'cancelled', 'unknown', 'stuck'}   # stuck: resumable after a change
OPEN = ('queued', 'running')            # attempt statuses that hold a slot
CHECK_TIMEOUT = 120
STAGING_PREFIX = '.autogen-staging-'    # the old in-project staging name; walks still skip it
MAX_OUTPUT = 4000
GIT_OUTPUT = 1 << 20
LOCATE_LIMIT = 20000                    # entries a basename fallback search may visit
REQUEST_ID_MAX = 160                    # the longest client_request_id a TaskRunner must accept
HEARTBEAT_STALE = 300                   # a worker that has not beaten for this long is gone
RESUME_WINDOW = 2 * 3600                # a coordinator is re-attached only to recently updated runs
WORKER_ACQUIRE_TRIES = 10
LOCAL_ENGINE = 'local'                   # a small Ollama model on a node. Admitted only when the run asks for it, so
                                         # a strategy rotation never moves a CLI-agent run onto a small local model.
                                         # Its attempts are spec-sheet builds on the kernel lane, not agent tasks
                                         # (a run recorded earlier with ordinary statements on 'local' keeps its
                                         # agent-task attempts).


def admitted_engines(engines, base_engine):
    """The engines a run may use and rotate among: the runner's engines, without 'local' unless the run
    itself is a local run (a CLI-agent run never moves onto a small local model)."""
    return [e for e in dict.fromkeys(engines or ()) if isinstance(e, str) and (e != LOCAL_ENGINE or base_engine == LOCAL_ENGINE)]


SANDBOX_PATH = '/usr/local/bin:/usr/bin:/bin'
SANDBOX_LAUNCHER = str(Path(__file__).resolve().parents[1] / 'sandbox' / 'landlock.py')
SANDBOX_REFUSED = 125                    # the launcher's exit code when Landlock is unavailable (--require)
_SCOPE = {}                              # one systemd user-scope probe per process
SCOPE_SLICE = os.environ.get('SYMBLIC_SCOPE_SLICE') or 'symblic.slice'   # systemd user slice for designed checks


def _node_bin():
    """The node runtime's bin folder (nvm installs live under $HOME, which the sandbox hides)."""
    node = shutil.which('node')
    if node:
        return os.path.dirname(os.path.realpath(node))
    versions = Path(os.path.expanduser('~')) / '.nvm' / 'versions' / 'node'
    try:
        newest = sorted(versions.iterdir(), key=lambda p: p.name)[-1]
        return str(newest / 'bin')
    except (OSError, IndexError):
        return ''


def sandbox_prefix(folder, home, extra_files=()):
    """How a MODEL-WRITTEN test script is run: through the repository's Landlock launcher
    (symblic/sandbox/landlock.py, kernel-enforced, unprivileged): the system read-only, `folder` and the
    throwaway `home` the only writable places, the rest of $HOME absent, no TCP connect or bind
    (--net-connect 1 allows only port 1, plus the launcher's seccomp filters), no abstract unix
    sockets, no signals outside the sandbox, and an environment built from scratch (`env -i`).
    --require makes a missing Landlock a visible refusal (exit 125), never an unsandboxed run.
    Returns (kind, argv prefix ending in '--', absolute shell path)."""
    node_bin = _node_bin()
    path = SANDBOX_PATH + (':' + node_bin if node_bin else '')
    shell = shutil.which('bash') or '/usr/bin/bash'
    python = shutil.which('python3') or '/usr/bin/python3'
    argv = ['env', '-i', 'PATH=' + path, 'HOME=' + home, 'LANG=C.UTF-8', 'TMPDIR=' + home,
            python, SANDBOX_LAUNCHER, '--cwd', folder, '--rw', folder, '--rw', home, '--require', '--no-unix', '--net-connect', '1']
    if node_bin:
        argv += ['--ro', os.path.dirname(os.path.dirname(node_bin))]
    for extra in extra_files:
        argv += ['--ro', extra]
    return 'landlock', argv + ['--'], shell


# One error type for the coordinator and its policy: submit() raises the policy's validation
# errors too, and a caller catching symblic.autogen.coordinator.AutogenError must see both.
AutogenError = POLICY.AutogenError
KernelError = KERNEL.KernelError


def _env():
    return {'PATH': os.environ.get('PATH', os.defpath), 'HOME': os.environ.get('HOME', '/tmp'),
            'LANG': 'C.UTF-8', 'TMPDIR': os.environ.get('TMPDIR', '/tmp')}


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _run(argv, cwd, timeout=CHECK_TIMEOUT, shell=False, limit=MAX_OUTPUT):
    """Bounded subprocess for code checks: low priority, no inherited secrets, its own session so
    a timeout (or a check that leaves a background child) kills the whole process group."""
    try:
        proc = subprocess.Popen(argv if not shell else ['bash', '-c', argv], cwd=cwd, env=_env(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace',
                                start_new_session=True, preexec_fn=lambda: os.nice(10))
    except (OSError, ValueError) as exc:
        return {'rc': 127, 'out': f'{type(exc).__name__}: {exc}'}
    try:
        out, _ = proc.communicate(timeout=timeout)
        return {'rc': proc.returncode, 'out': (out or '')[-limit:]}
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return {'rc': 124, 'out': f'check timed out after {timeout}s'}
    finally:
        _kill_group(proc)               # nothing a check started outlives it


def _git(argv, cwd, timeout=CHECK_TIMEOUT):
    """git plumbing for change sets and staging: the full output (bounded at 1 MB), not a tail."""
    return _run(argv, cwd, timeout=timeout, limit=GIT_OUTPUT)


def _listing(folder, limit=400):
    """Relative paths of regular files under a workspace, bounded; prunes .git and staging trees
    during the walk. Checks no longer depend on it (they look files up directly)."""
    out = []
    if not folder or not os.path.isdir(folder):
        return out
    for top, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d != '.git' and not d.startswith(STAGING_PREFIX))
        for name in sorted(files):
            path = os.path.join(top, name)
            if os.path.isfile(path) and not os.path.islink(path):
                out.append(os.path.relpath(path, folder))
                if len(out) >= limit:
                    return out
    return out


def _safe_rel(name):
    return bool(name) and not name.startswith('/') and '..' not in name.split('/') and '\0' not in name


def _is_file(folder, name):
    path = os.path.join(folder, name)
    return os.path.isfile(path) and not os.path.islink(path)


def _locate(folder, name, limit=LOCATE_LIMIT):
    """The named file's path relative to `folder`: the exact relative path first, then a bounded
    search for the same trailing path anywhere below (pruning .git and staging trees)."""
    if not folder or not _safe_rel(name) or not os.path.isdir(folder):
        return None
    if _is_file(folder, name):
        return name
    tail, seen = '/' + name, 0
    for top, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d != '.git' and not d.startswith(STAGING_PREFIX))
        for leaf in sorted(files):
            seen += 1
            if seen > limit:
                return None
            rel = os.path.relpath(os.path.join(top, leaf), folder)
            if ('/' + rel).endswith(tail) and _is_file(folder, rel):
                return rel
    return None


def _find(row, node_id, attempt_id=None):
    node = next((n for n in row['nodes'] if n['id'] == node_id), None)
    if node is None or attempt_id is None:
        return node, None
    return node, next((a for a in node['attempts'] if a['id'] == attempt_id), None)


def _public_report(checks):
    return '; '.join(f'{c["kind"]} {c.get("file") or c.get("command") or ""}: {str(c.get("output") or "")[:120]}'
                     for c in checks if not c.get('passed') and c.get('public'))


class AutogenManager:
    """The durable coordinator of autogen runs.

    root          the state folder; run records live in <root>/state/autogen/.
    task_runner   a TaskRunner (symblic/autogen/runner.py) that launches agent attempts and names the
                  nodes; default KernelOnlyRunner() (no agents: spec sheets on the kernel lane only).
    background    True: submit() and resume start a daemon thread per run that drives advance().
                  False (tests, embedding): the caller calls advance(run_id) itself.
    check_host    called before every action; default execution_fence (see runner.py).
    check_runner  runs one code check: check_runner(argv_or_command, cwd, timeout=..., shell=False)
                  -> {'rc': int, 'out': str}; default _run (a bounded subprocess at low priority).
    listing, clock, git, kernel
                  injectable for tests: a folder listing, the time source, a git runner, and the
                  kernel-lane module (symblic/autogen/kernel_lane.py).
    """

    POLL_SECONDS = 10

    def __init__(self, root, *, task_runner=None, background=True, check_host=execution_fence,
                 check_runner=_run, listing=_listing, clock=time.time, git=None, kernel=None):
        self.root = Path(root)
        self.kernel = kernel or KERNEL      # the kernel lane of `local` runs; tests inject a fake
        self.dir = self.root / 'state' / 'autogen'
        self.task_runner = task_runner if task_runner is not None else KernelOnlyRunner()
        self.background = background
        self.check_host = check_host
        self.check_runner = check_runner
        self.git = git or _git
        self.list_files = listing  # kept for callers; checks look named files up directly
        self.clock = clock
        self._seq = {}

    # ------------------------------------------------------------------ records
    def _path(self, run_id):
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise AutogenError('Unknown autogen run id.', 404)
        return self.dir / (run_id + '.json')

    @contextmanager
    def _lock(self, run_id, worker=False, blocking=True):
        self._path(run_id)
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.dir / (run_id + ('.worker.lock' if worker else '.lock'))
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            yield True
        finally:
            os.close(fd)

    def _read(self, run_id):
        path = self._path(run_id)
        try:
            with open(path, encoding='utf-8') as handle:
                return json.load(handle)
        except FileNotFoundError:
            raise AutogenError('Unknown autogen run id.', 404) from None
        except ValueError:
            raise AutogenError('The autogen record is unreadable; nothing was changed.', 409) from None

    def _write(self, row):
        row['updated'] = self.clock()
        atomic_json(self._path(row['id']), row)

    @contextmanager
    def _mutate(self, run_id):
        """Read-modify-write under the run lock: re-read, yield, write only when something
        changed. A concurrent control() (cancel, resume) can never be overwritten by a pass."""
        with self._lock(run_id):
            row = self._read(run_id)
            before = json.dumps(row, sort_keys=True)
            yield row
            if json.dumps(row, sort_keys=True) != before:
                self._write(row)

    def _events_path(self, run_id):
        return self.dir / (run_id + '.events.jsonl')

    def _log_lines(self, path):
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return 0, 0, True
        cached = self._seq.get(str(path))
        if cached and cached[0] == size:
            return cached[1], size, cached[2]
        data = path.read_bytes()
        complete = not data or data.endswith(b'\n')
        count = data.count(b'\n') + (0 if complete else 1)
        return count, size, complete

    def _event(self, row, name, **fields):
        """Append one event. Called under the run lock; seq is the event's line number in the log,
        so it stays unique and gap-free even when a crash lost the record write that followed."""
        path = self._events_path(row['id'])
        count, _, complete = self._log_lines(path)
        event = {'at': self.clock(), 'seq': count + 1, 'event': name, **fields}
        row['seq'] = event['seq']
        text = ('' if complete else '\n') + json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n'
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        self._seq[str(path)] = (path.stat().st_size, count + 1, True)
        return event

    # ------------------------------------------------------------------ submit
    def submit(self, body):
        """Start (or find again) one run. `body`: client_request_id (stable; the same id and body return
        the same run with duplicate=True), instruction (one statement per line, or one spec sheet),
        engine, node, cwd (an existing git project folder), optional model, effort, context_note,
        headless, sheet and autogen (the policy fields of policy.normalize). Everything is validated
        before any record is written; the record is durable before any attempt starts.
        Returns {'run': record, 'duplicate': bool}."""
        self.check_host()
        if not isinstance(body, dict):
            raise AutogenError('Submit a JSON object.')
        allowed = {'client_request_id', 'instruction', 'engine', 'model', 'effort', 'node', 'cwd', 'context_note',
                   'autogen', 'headless', 'sheet'}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise AutogenError('Unknown autogen field' + ('s ' if len(unknown) > 1 else ' ') + ', '.join(unknown) + '.')
        request_id = body.get('client_request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', request_id):
            raise AutogenError('A stable client_request_id is required (letters, digits, dot, colon, underscore or hyphen).')
        instruction = body.get('instruction') if isinstance(body.get('instruction'), str) else ''
        sheet = body.get('sheet', False)
        if not isinstance(sheet, bool):
            raise AutogenError('sheet must be true or false.')
        if sheet and (body.get('engine') or 'agy') != LOCAL_ENGINE:
            raise AutogenError('A spec sheet runs on the local kernel lane: engine local, an Ollama model and a node.')
        # The kernel lane (docs/reference/LOCAL-AUTOGEN.md): a local run's statement is ONE spec sheet, kept
        # verbatim; small models write its units one fresh context at a time, checked by js_test.
        sheet = body.get('engine') == LOCAL_ENGINE and (sheet or self.kernel.is_sheet(instruction))
        if body.get('engine') == LOCAL_ENGINE and not sheet:
            raise AutogenError('local attempts take a spec sheet; see docs/reference/SPEC-SHEETS.md (tools/symblic-task start '
                               '--sheet SHEET.md --engine local --model MODEL --node NODE --autogen).')
        lines = [instruction] if sheet else POLICY.statements(instruction)
        if not lines or len(lines) > POLICY.MAX_LINES:
            raise AutogenError(f'Give 1 to {POLICY.MAX_LINES} statements, one per line.')
        cwd = body.get('cwd')
        if not isinstance(cwd, str) or not cwd.startswith('/') or not os.path.isdir(cwd):
            raise AutogenError('Select the project workspace explicitly (an existing absolute folder; create one with '
                               'tools/symblic-task workspace NAME).')
        if not os.path.isdir(os.path.join(cwd, '.git')):
            raise AutogenError('Autogen candidates need a git workspace so results can be verified and promoted; run git init '
                               'there, or create one with tools/symblic-task workspace NAME.')
        node = body.get('node')
        if not isinstance(node, str) or not node.strip():
            raise AutogenError('Select the execution machine explicitly.')
        engine = body.get('engine') or 'agy'
        runner = self.task_runner
        engines = admitted_engines(getattr(runner, 'engines', ()), engine)
        if engine not in engines:
            raise AutogenError('Choose an engine the task runner offers.')
        if engine == LOCAL_ENGINE and not str(body.get('model') or '').strip():
            raise AutogenError('The local engine needs a model (an installed Ollama model name).')
        nodes = self._online_nodes()
        if engine == LOCAL_ENGINE:
            # the deployment rule: a model runs on a node, the coordinating machine only coordinates; a strategy
            # rotation (other_node) must never move a local model onto it
            host = self._local_node()
            if host and node == host:
                raise AutogenError(f'A local model runs on a node, not on the coordinating machine ({host}): '
                                   'choose another node.')
            nodes = [n for n in nodes if n != host]
            try:
                self.kernel.applicator(body.get('model'), node, host)
            except ValueError as exc:
                raise AutogenError(f'The local engine runs an installed Ollama model on a node: {exc}.') from None
            # the coordinator narrows the rotation (other_node, re-plans) to the nodes that hold the model
            # (_check_catalogue) without delaying this request, and never vetoes the operator's own node with a
            # cached inventory: the launch itself is the fresh check
            nodes = self._model_catalogue(nodes, None, local_node=host)
        # a sheet run stays on the kernel lane: other_engine never moves it onto a CLI agent
        policy = POLICY.normalize(body.get('autogen', {}), engines=[LOCAL_ENGINE] if sheet else engines, nodes=nodes)
        if sheet:
            if policy['perpetual']:
                raise AutogenError('A spec sheet builds one file; a perpetual lane does not apply to it.')
            found = self.kernel.sheet_problems(instruction)
            if found:
                raise AutogenError('Spec sheet refused: ' + '; '.join(str(f) for f in found[:8]))
        else:
            findings = POLICY.lint(lines, cwd)
            errors = [f for f in findings if f[0] == 'error']
            if errors:
                raise AutogenError('Statements refused: ' + '; '.join(f'line {n}: {m}' for _, n, m in errors))
        note = body.get('context_note', '')
        if not isinstance(note, str) or len(note) > 12000:
            raise AutogenError('Context note must be text under 12000 characters.')
        base = {'engine': engine, 'model': body.get('model') or '', 'effort': body.get('effort') or '', 'node': node,
                'cwd': cwd, 'context_note': note, 'headless': bool(body.get('headless', True))}
        for key in ('model', 'effort'):
            if not isinstance(base[key], str):
                raise AutogenError(f'{key} must be text.')
        if sheet:
            base['sheet'] = True          # only on sheet runs: older request digests stay what they were
        payload = {'lines': lines, 'base': base, 'policy': {k: v for k, v in policy.items() if k not in ('engines', 'nodes')}}
        request_digest = POLICY.digest(payload)
        run_id = 'autogen-' + hashlib.sha256(request_id.encode()).hexdigest()[:24]
        with self._lock(run_id):
            if self._path(run_id).exists():
                row = self._read(run_id)
                if row['request_digest'] != request_digest:
                    raise AutogenError('This request id already belongs to different statements or a different policy.', 409)
                duplicate = True
            else:
                duplicate = False
                now = self.clock()
                row = {'id': run_id, 'client_request_id': request_id, 'request_digest': request_digest, 'version': POLICY.VERSION,
                       'created': now, 'status': 'queued', 'error': '', 'cancel_requested': False, 'seq': 0,
                       'base': base, 'policy': policy, 'lines': lines,
                       'budget': {'agents_started': 0, 'agents_max': policy['agents_max'],   # 0 = unlimited (until_done)
                                  'deadline': (now + policy['wall_seconds']) if policy['wall_seconds'] else None},
                       'nodes': [self._node(i, line, 0, None, policy, sheet=sheet) for i, line in enumerate(lines)],
                       'order': [f'n{i}' for i in range(len(lines))], 'cursor': 0, 'final': None}
                self._event(row, 'submitted', lines=len(lines), policy_sha256=policy['sha256'])
                self._write(row)
        # A retried submit (the first answer was lost, or its worker never started) re-attaches
        # the coordinator; the worker lease makes a second one exit at once.
        if not duplicate or row['status'] not in TERMINAL:
            self._schedule(run_id)
        return {'run': row, 'duplicate': duplicate}

    @staticmethod
    def _node(index, statement, depth, parent, policy, sheet=False):
        # a spec sheet's prose names no files; its examples are its tests, so no designer runs for it
        files = [] if sheet else POLICY.statement_files(statement)['files']
        node = {'id': f'n{index}' if parent is None else f'{parent}.{index}', 'index': index, 'parent': parent,
                'depth': depth, 'statement': statement, 'status': 'pending', 'attempts': [], 'children': [],
                'generation': 0, 'handoffs': 0, 'perpetual': policy['perpetual'], 'winner': '',
                'last_fingerprint': '', 'fingerprints': [], 'split_refused': False, 'planners': 0,
                'needs_design': bool(policy.get('designer')) and bool(files) and not policy['perpetual'],
                'designed': '', 'progress': {}, 'stale': 0, 'progress_recent': False, 'handoff_progress': True,
                'items_total': 0, 'stale_generations': 0,
                'engine': None, 'node': None, 'decisions': []}
        if sheet:
            node['sheet'] = True
        return node

    # ------------------------------------------------------------------ worker
    def _schedule(self, run_id):
        if self.background:
            self._beat(run_id)            # alive from the moment a worker is scheduled
            threading.Thread(target=self._worker, args=(run_id,), name='symblic-autogen-' + run_id[-8:], daemon=True).start()

    def _alive_path(self, run_id):
        return self.dir / (run_id + '.alive')

    def _beat(self, run_id):
        try:
            path = self._alive_path(run_id)
            with open(path, 'w', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as handle:
                handle.write(str(os.getpid()))          # the coordinator thread lives in this process only
            os.utime(path, None)
        except OSError:
            pass

    def _alive(self, run_id):
        """Liveness from the heartbeat file, never from the worker lease: probing the lease made a
        freshly scheduled worker lose its non-blocking acquire to a status read and exit. A heartbeat
        written by another process (the host process before a restart) is dead at once, not after
        HEARTBEAT_STALE: that lag left re-attachment up to five minutes late (2026-10-11)."""
        try:
            path = self._alive_path(run_id)
            fresh = time.time() - path.stat().st_mtime < HEARTBEAT_STALE
            if not fresh:
                return False
            with open(path, encoding='utf-8') as handle:
                pid = handle.read(32).strip()
            return not pid or pid == str(os.getpid())
        except (OSError, ValueError):
            return False

    def _worker(self, run_id):
        for attempt in range(WORKER_ACQUIRE_TRIES):
            with self._lock(run_id, worker=True, blocking=False) as owned:
                if owned:
                    self._drive(run_id)
                    try:
                        self._alive_path(run_id).unlink()
                    except OSError:
                        pass
                    return
            if attempt + 1 < WORKER_ACQUIRE_TRIES:
                time.sleep(0.2)

    def _drive(self, run_id):
        while True:
            self._beat(run_id)
            try:
                keep_going = self.advance(run_id)
            except Exception as exc:
                try:
                    self._interrupted(run_id, exc)
                except Exception:
                    pass
                return
            if not keep_going:
                return
            try:
                seconds = self._sleep_seconds(self._read(run_id))
            except AutogenError:
                return
            for _ in range(max(1, int(seconds))):
                time.sleep(1)
                self._beat(run_id)
                try:
                    if self._read(run_id).get('cancel_requested'):
                        break
                except AutogenError:
                    return

    def _sleep_seconds(self, row):
        """Poll cadence; a perpetual lane waiting for its interval sleeps until min(until, deadline)."""
        node = self._node_now(row)
        if node is not None and not any(a.get('status') in OPEN for a in node['attempts']):
            last = (node.get('decisions') or [{}])[-1]
            if last.get('action') == 'wait' and last.get('until'):
                deadline = row['budget'].get('deadline')
                until = last['until'] if deadline is None else min(last['until'], deadline)
                return max(1.0, until - self.clock())
        return self.POLL_SECONDS

    def _interrupted(self, run_id, exc):
        """The pass raised: stop the run's live children so nothing runs unsupervised, then mark
        the run unknown for the operator. Intents never reserved stay (Resume re-submits them)."""
        row = self._read(run_id)
        for node in row['nodes']:
            for attempt in node['attempts']:
                if attempt['status'] in OPEN or attempt['status'] == 'unknown':
                    try:
                        self._cancel_attempt(run_id, node['id'], attempt['id'], 'interrupted')
                    except Exception:
                        pass
        with self._mutate(run_id) as row:
            row.update(status='unknown', error=f'Coordinator interrupted: {type(exc).__name__}: {str(exc)[:300]}. Inspect the attempts before resuming.')

    # ------------------------------------------------------------------ reads
    def get(self, run_id, include_tasks=False):
        """The run record plus `summary` (policy.summary) and `resume_required` (no live coordinator);
        with include_tasks, the runner's task record of every attempt under `tasks`. Reading a run that
        a restart left without a coordinator re-attaches one (background mode only)."""
        row = self._read(run_id)
        row['resume_required'] = row['status'] in ('queued', 'active') and not self._alive(run_id)
        self._resume_stranded(row)
        row['summary'] = POLICY.summary(row)
        if include_tasks:
            tasks = {}
            for node in row['nodes']:
                for attempt in node['attempts']:
                    if attempt.get('task_id'):
                        try:
                            tasks[attempt['task_id']] = self.task_runner.get(attempt['task_id'])
                        except TaskError as exc:
                            tasks[attempt['task_id']] = {'error': str(exc)}
            row['tasks'] = tasks
        return row

    def listing(self):
        """The 100 most recently changed runs, newest first (each as get() returns it)."""
        if not self.dir.exists():
            return []
        paths = sorted(self.dir.glob('autogen-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        return [self.get(path.stem) for path in paths if RUN_ID.fullmatch(path.stem)]

    def _resume_stranded(self, row):
        """Re-attach a coordinator to a run a process restart left without one: only queued or active
        runs, never one whose cancel is pending, only within RESUME_WINDOW of its last update. Nothing is
        replayed: the next pass observes what the attempts did meanwhile."""
        if not self.background or not row.get('resume_required'):
            return
        if row.get('status') not in ('queued', 'active') or row.get('cancel_requested'):
            return
        try:
            if self.clock() - float(row.get('updated') or row.get('created') or 0) > RESUME_WINDOW:
                return
        except (TypeError, ValueError):
            return
        try:
            self.check_host()
        except Exception:
            return
        with self._mutate(row['id']) as current:
            if current['status'] not in ('queued', 'active') or current.get('cancel_requested'):
                return
            current['resumed'] = {'at': self.clock(), 'by': 'listing', 'reason': 'coordinator absent after a restart'}
        self._beat(row['id'])           # one re-attachment per stale period, not one per status read
        self._schedule(row['id'])

    def control(self, run_id, action, extend=None):
        """cancel | resume. `extend` = {'agents_max': N, 'wall_seconds': S} raises a spent explicit cap on
        resume (0 = unlimited, until_done only); a stuck run whose cap is spent refuses a plain resume."""
        self.check_host()
        if action not in ('cancel', 'resume'):
            raise AutogenError('Choose cancel or resume.')
        if extend is not None and not isinstance(extend, dict):
            raise AutogenError('extend must be an object with agents_max and/or wall_seconds.')
        with self._mutate(run_id) as row:
            if action == 'resume' and row['status'] == 'stuck':
                self._extend_budget(row, extend or {})
            if action == 'cancel':
                # an 'unknown' run still has children to stop: cancel works on it too
                if row['status'] not in ('completed', 'failed', 'cancelled') and not row['cancel_requested']:
                    row['cancel_requested'] = True
                    self._event(row, 'cancel_requested')
            elif row['status'] in ('queued', 'active', 'unknown', 'stuck'):
                if row['status'] == 'stuck':
                    # Resume = another full rotation: every stuck node is reopened with its stall counter
                    # and its tried-fingerprint set cleared (archived on the node), and the engine/node
                    # catalogue is re-read so a machine or agent added since the run started is tried.
                    for node in row['nodes']:
                        if node['status'] == 'stuck':
                            archive = (node.get('fingerprints_archive') or []) + (node.get('fingerprints') or [])
                            node.update(status='pending', stale=0, error='', progress_recent=False, handoff_progress=True,
                                        rotations=node.get('rotations', 0) + 1, fingerprints=[], last_fingerprint='',
                                        fingerprints_archive=archive[-512:], rotation_start=len(node['attempts']))
                            # a handoff chain that stalled gets its successor again in the new rotation
                            for attempt in node['attempts']:
                                if attempt.get('status') == 'handoff':
                                    attempt['progress'] = {**(attempt.get('progress') or {}), 'new': True, 'reopened': True}
                    self._refresh_catalogue(row)
                    row.pop('catalogue_checked', None)       # the next pass reads the model inventory again
                row.update(status='queued' if row['status'] in ('unknown', 'stuck') else row['status'], error='')
                row['resumed'] = {'at': self.clock(), 'by': 'operator'}
                for node in row['nodes']:
                    for attempt in node['attempts']:
                        if attempt['status'] == 'unknown':
                            attempt['status'] = 'running'          # re-observe its task
                        promotion = attempt.get('promotion') or {}
                        if promotion.get('state') == 'intent':
                            # the operator inspected the interrupted apply; re-applying is content-idempotent
                            attempt['promotion'] = {**promotion, 'state': 'resumed'}
                self._event(row, 'resumed')
        self._schedule(run_id)
        return {'run': self.get(run_id)}

    def _extend_budget(self, row, extend):
        """Under the run lock. A spent explicit cap (agents_max or the deadline) is the operator's own
        limit: a resume must raise it (or lift it, 0 with until_done), otherwise the run would be
        stuck again on the next pass."""
        budget, policy, now = row['budget'], row['policy'], self.clock()
        until = bool(policy.get('until_done'))
        changed = {}
        for key in ('agents_max', 'wall_seconds'):
            if key not in extend:
                continue
            value = extend[key]
            if isinstance(value, bool) or not isinstance(value, int):
                raise AutogenError(f'extend.{key} must be a whole number.')
            low, high = POLICY.LIMITS[key]
            if value == 0 and not until:
                raise AutogenError(f'extend.{key} 0 (unlimited) needs until_done true.')
            if value and not low <= value <= high:
                raise AutogenError(f'extend.{key} must be from {low} to {high}, or 0 with until_done.')
            changed[key] = value
        if 'agents_max' in changed:
            budget['agents_max'] = changed['agents_max']
            policy['agents_max'] = changed['agents_max']
        if 'wall_seconds' in changed:
            budget['deadline'] = (now + changed['wall_seconds']) if changed['wall_seconds'] else None
            policy['wall_seconds'] = changed['wall_seconds']
        spent_agents = bool(budget['agents_max']) and budget['agents_started'] >= budget['agents_max']
        spent_clock = budget.get('deadline') is not None and now >= budget['deadline']
        if spent_agents or spent_clock:
            # the refusal leaves the record and the log untouched (the mutation is discarded)
            what = 'agents_max' if spent_agents else 'wall_seconds'
            raise AutogenError(f'The {what} cap you gave this run is spent; resume with extend {{"{what}": N}} '
                               '(0 lifts it under until_done) or start a new run with a higher cap.', 409)
        if changed:
            self._event(row, 'budget_extended', **changed)

    def _local_node(self):
        """The machine the coordinator runs on, as the runner names it ('' when it names none)."""
        return str(getattr(self.task_runner, 'local_node', '') or '')

    def _online_nodes(self):
        """The ids of the runner's online nodes; [] when the runner cannot say."""
        try:
            return [n['id'] for n in self.task_runner.nodes() if n.get('online') and isinstance(n.get('id'), str)]
        except Exception:
            return []

    @staticmethod
    def _model_catalogue(nodes, inventory, absent=(), local_node=''):
        """A local run's rotation nodes: the given nodes except the coordinating machine and every node an
        attempt found without the model, narrowed to the nodes whose inventory lists the model when an
        inventory could be read."""
        keep = [n for n in nodes if n and n != local_node and n not in absent]
        return [n for n in keep if n in inventory['have']] if inventory is not None else keep

    def _check_catalogue(self, run_id):
        """Once per run (and after each resume), outside the lock: a local sheet run's rotation is narrowed to the
        nodes whose inventory lists the model (kernel_lane.model_nodes; reading it may ask every node, so it never
        happens inside a request). An unreadable inventory keeps every online node; a node an attempt found
        without the model stays out either way."""
        row = self._read(run_id)
        if not (row.get('base') or {}).get('sheet') or row.get('catalogue_checked'):
            return
        local = self._local_node()
        inventory = self.kernel.model_nodes(row['base'].get('model') or '', local)
        with self._mutate(run_id) as row:
            if row.get('catalogue_checked'):
                return
            before = list(row['policy'].get('nodes') or [])
            row['policy']['nodes'] = self._model_catalogue(before, inventory, row.get('model_absent') or (), local)
            row['catalogue_checked'] = {'at': self.clock(), 'inventory': inventory is not None}
            if row['policy']['nodes'] != before:
                self._event(row, 'catalogue_refreshed', engines=row['policy'].get('engines'), nodes=row['policy']['nodes'],
                            reason='model inventory')

    def _refresh_catalogue(self, row, inventory=None):
        """The policy's engine and node lists come from the task runner at submit time; a resume
        re-reads them (the request digest never covers them). A runner that cannot answer keeps the
        lists the run already has."""
        base_engine = (row.get('base') or {}).get('engine')
        sheet = bool((row.get('base') or {}).get('sheet'))
        engines = [e for e in admitted_engines(getattr(self.task_runner, 'engines', ()), base_engine)
                   if not sheet or e == LOCAL_ENGINE]
        nodes = self._online_nodes()
        if base_engine == LOCAL_ENGINE:
            local = self._local_node()
            nodes = [n for n in nodes if n != local]
            if sheet:
                nodes = self._model_catalogue(nodes, inventory, row.get('model_absent') or (), local)
        before = (list(row['policy'].get('engines') or []), list(row['policy'].get('nodes') or []))
        if engines:
            row['policy']['engines'] = engines
        if nodes:
            row['policy']['nodes'] = list(dict.fromkeys(nodes))
        after = (row['policy'].get('engines'), row['policy'].get('nodes'))
        if after != before:
            self._event(row, 'catalogue_refreshed', engines=after[0], nodes=after[1])

    # ------------------------------------------------------------------ one pass
    def advance(self, run_id):
        """One admitted pass over the tree: observe attempts, decide, act. Returns True while
        the coordinator still has something to drive."""
        self.check_host()
        now = self.clock()
        with self._mutate(run_id) as row:
            cancelling = bool(row['cancel_requested']) and row['status'] in ('queued', 'active', 'unknown', 'stuck')
            if row['status'] in TERMINAL and not cancelling:
                if not self._loose_ends(row):
                    return False
            elif not cancelling:
                row['status'] = 'active'
        if row['status'] in TERMINAL and not cancelling:
            # a run that ended with a refused close or cancel keeps retrying it (no agent left alive)
            self._sweep(run_id)
            return bool(self._loose_ends(self._read(run_id)))
        if cancelling:
            return self._cancel_run(run_id)
        self._check_catalogue(run_id)
        if not self._sweep(run_id):
            return False
        node_id = self._settle(run_id)
        if node_id is None:
            return self._finish(run_id)
        row = self._read(run_id)
        node, _ = _find(row, node_id)
        if node['status'] == 'failed':
            # a split parent whose children all passed but whose own checks failed in the promoted
            # workspace: the run ends here with the parent's report (no further launches)
            with self._mutate(run_id) as row:
                if row['status'] == 'active':
                    row.update(status='failed', error=f'Statement {node["id"]} failed: {node.get("error") or "parent checks failed"}')
            return False
        for attempt in node['attempts']:
            if attempt['status'] in OPEN:
                self._observe(run_id, node_id, attempt['id'], now)
        for attempt in _find(self._read(run_id), node_id)[0]['attempts']:
            if attempt['status'] == 'promoting' and (attempt.get('promotion') or {}).get('state') != 'intent':
                self._promote_generation(run_id, node_id, attempt['id'])
        row = self._read(run_id)
        node, _ = _find(row, node_id)
        unknown = [a for a in node['attempts'] if a['status'] == 'unknown']
        if unknown:
            first = unknown[0]
            with self._mutate(run_id) as row:
                if row['status'] == 'active' and not row['cancel_requested']:
                    row.update(status='unknown', error=(
                        f'Attempt {first["id"]} (task {first.get("task_id") or "not recorded"}) is in an unknown state: '
                        f'{first.get("error") or "its launch outcome was not confirmed"}. Inspect it with your task runner and '
                        'recover the task before resuming this run; nothing was relaunched.'))
                    self._event(row, 'run_unknown', node=node_id, attempt=first['id'])
            return False
        decision = None
        with self._mutate(run_id) as row:
            if row['status'] != 'active' or row['cancel_requested']:
                return row['status'] in ('queued', 'active')       # the next pass honours the cancel
            node, _ = _find(row, node_id)
            node['stale'] = POLICY.stale_count(node)
            node['handoff_stale'] = POLICY.handoff_stale(node)
            node['progress_recent'] = POLICY.recent_progress(node)
            decision = POLICY.decide(node, row['policy'], row['budget'], now)
            if node.get('sheet') and decision.get('strategy') == 'conflict_retry':
                # A rebuilt file never contains the operator's concurrent edit, and the retry's checkout would hold
                # it as its base, so a retry would overwrite it: the node ends and the operator resolves it.
                where = next((((a.get('kernel') or {}).get('checkout') or {}).get('worktree') for a in reversed(node['attempts'])
                              if a.get('failure') == 'CONFLICT'), '') or 'its checkout'
                decision = {'action': 'stuck' if row['policy'].get('until_done') else 'fail',
                            'reason': ('the project file changed while the build ran (CONFLICT); the built file was not '
                                       f'applied and stays in {where}: resolve it, then resume')}
            record = {'at': now, **{k: v for k, v in decision.items() if k != 'overrides'}}
            last = node['decisions'][-1] if node['decisions'] else None
            quiet = (decision['action'] == 'wait' and not decision.get('timeout') and last is not None
                     and all(last.get(k) == record.get(k) for k in ('action', 'reason', 'until')))
            if not quiet:
                # a pure wait that repeats the last decision neither grows the log nor the record
                node['decisions'].append(record)
                node['decisions'] = node['decisions'][-40:]
                self._event(row, 'decision', node=node['id'], action=decision['action'], reason=decision['reason'])
            if decision['action'] in ('regenerate', 'perpetual_next') and decision.get('fingerprint'):
                node['last_fingerprint'] = decision['fingerprint']
                node['fingerprints'] = (node.get('fingerprints') or [])[-127:] + [decision['fingerprint']]
        action = decision['action']
        before = len(node['attempts'])            # a refusal recorded on the node is progress of a kind; an empty wave is not
        if action == 'wait':
            for attempt_id in decision.get('timeout', []):
                self._cancel_attempt(run_id, node_id, attempt_id, 'timeout',
                                     message='run deadline passed' if (row['budget'].get('deadline') is not None and now >= row['budget']['deadline'])
                                     else 'attempt exceeded the policy attempt_seconds allowance')
            return True
        if action == 'accept':
            self._accept(run_id, node_id, decision.get('attempt'))
            if self._settle(run_id) is None:
                return self._finish(run_id)
            return self._read(run_id)['status'] in ('queued', 'active')
        if action == 'launch':
            return self._launched(run_id, node_id, before, self._launch_wave(
                run_id, node_id, [{'kind': 'candidate', 'strategy': 'fresh'}] * decision['count']))
        if action == 'regenerate':
            return self._launched(run_id, node_id, before, self._launch_wave(
                run_id, node_id, [{'kind': 'regen', 'strategy': decision['strategy'], 'overrides': decision.get('overrides') or {}}]))
        if action == 'design':
            return self._launched(run_id, node_id, before, self._launch_wave(run_id, node_id, [{'kind': 'designer', 'strategy': 'design'}]))
        if action == 'decompose':
            spec = {'kind': 'planner', 'strategy': 'split', 'overrides': decision.get('overrides') or {}}
            if decision.get('remaining'):
                spec.update(strategy='split_remaining', from_attempt=decision.get('from'))
            elif decision.get('replan'):
                spec['strategy'] = 'replan'
            return self._launched(run_id, node_id, before, self._launch_wave(run_id, node_id, [spec]))
        if action == 'stuck':
            with self._mutate(run_id) as row:
                node, _ = _find(row, node_id)
                node['status'] = 'stuck'
                node['error'] = decision['reason']
                row.update(status='stuck', error=f'Statement {node["id"]} is stuck: {decision["reason"]}')
                self._event(row, 'node_stuck', node=node['id'], reason=decision['reason'][:300])
            return False
        if action == 'handoff':
            return self._launched(run_id, node_id, before, self._launch_wave(
                run_id, node_id, [{'kind': 'handoff', 'strategy': 'handoff', 'generation': decision['generation'],
                                   'from_attempt': decision['from']}]))
        if action == 'perpetual_next':
            return self._launched(run_id, node_id, before, self._launch_wave(
                run_id, node_id, [{'kind': 'perpetual', 'strategy': 'perpetual', 'generation': decision['generation'],
                                   'overrides': decision.get('overrides') or {}}]))
        if action == 'fail':
            with self._mutate(run_id) as row:
                node, _ = _find(row, node_id)
                node['status'] = 'failed'
                node['error'] = decision['reason']
                row.update(status='failed', error=f'Statement {node["id"]} failed: {decision["reason"]}')
                self._event(row, 'node_failed', node=node['id'], reason=decision['reason'])
            return False
        return False

    def _launched(self, run_id, node_id, before, launched):
        """A wave the budget refused (nothing recorded on the node) would make every later pass
        repeat the same decision forever: the node ends there instead, stuck (until_done) or failed.
        A refusal recorded as a failed attempt (a remote handoff, a runner's refusal) is new evidence the
        next decision reads, so it is not terminal here."""
        if launched:
            return True
        with self._mutate(run_id) as row:
            if row['status'] != 'active' or row.get('cancel_requested'):
                return row['status'] in ('queued', 'active')
            node, _ = _find(row, node_id)
            if len(node['attempts']) > before or any(a['status'] in OPEN or a.get('body') for a in node['attempts']):
                return True
            until = bool(row['policy'].get('until_done'))
            node['status'] = 'stuck' if until else 'failed'
            node['error'] = 'the launch was refused (budget spent or the run is being cancelled); nothing could be started'
            row.update(status=node['status'], error=f'Statement {node_id} is {node["status"]}: {node["error"]}')
            self._event(row, 'node_stuck' if until else 'node_failed', node=node_id, reason=node['error'])
        return False

    @staticmethod
    def _current(row):
        """Pure: ('node', node) for the first node in execution order that is not accepted
        (children of a split node come before the nodes after it), ('parent', node) for a split
        node whose children are all accepted and whose own verdict is still due, or (None, None)."""
        by_id = {n['id']: n for n in row['nodes']}

        def walk(node_id):
            node = by_id[node_id]
            if node['status'] == 'split':
                for child in node['children']:
                    found = walk(child)
                    if found is not None:
                        return found
                return ('parent', node) if all(by_id[c]['status'] == 'accepted' for c in node['children']) else None
            if node['status'] == 'accepted':
                return None
            return ('node', node)
        for node_id in row['order']:
            found = walk(node_id)
            if found is not None:
                return found
        return None, None

    def _node_now(self, row):
        kind, node = self._current(row)
        return node if kind == 'node' else None

    def _settle(self, run_id):
        """Persisted parent verdicts, then the current node's id (None when every node is accepted).
        A split parent is accepted only when its own checks pass in the promoted project folder."""
        for _ in range(64 * 8):
            row = self._read(run_id)
            kind, node = self._current(row)
            if kind is None:
                return None
            if kind == 'node':
                return node['id']
            verdict = self._parent_verdict(row, node)
            with self._mutate(run_id) as row:
                parent, _ = _find(row, node['id'])
                if parent['status'] != 'split':
                    continue
                parent['parent_verdict'] = verdict
                if verdict['passed']:
                    parent['status'] = 'accepted'
                    parent['winner'] = 'children'
                    self._event(row, 'node_accepted', node=parent['id'], winner='children', checks=len(verdict['checks']))
                elif row['policy'].get('until_done'):
                    # every child passed, the assembled result does not: the parent is worked on as a
                    # whole again (its checkout now holds the children's files) with the failed checks
                    # as evidence; nothing ends by a count
                    now = self.clock()
                    n = sum(1 for a in parent['attempts'] if a.get('kind') == 'integration') + 1
                    parent['attempts'].append({'id': f"{parent['id']}-i{n}", 'kind': 'integration', 'strategy': 'integration',
                                               'engine': parent.get('engine'), 'node': parent.get('node'), 'model': '',
                                               'generation': 0, 'request_id': '', 'task_id': '', 'status': 'failed',
                                               'failure': 'CHECK_FAILURE', 'started': now, 'finished': now, 'verdict': verdict,
                                               'error': 'children accepted, parent checks failed: ' + verdict['report'][:400]})
                    for attempt in parent['attempts']:
                        if attempt.get('kind') == 'planner' and attempt.get('status') == 'accepted':
                            attempt['status'] = 'split_done'
                    parent['status'] = 'pending'
                    parent['winner'] = ''
                    parent['integrations'] = n
                    self._event(row, 'parent_reopened', node=parent['id'], reason=verdict['report'][:300])
                else:
                    # every child passed its own checks, but the assembled result does not satisfy
                    # the parent statement: the parent fails and the run ends with its report
                    parent['status'] = 'failed'
                    parent['error'] = 'children accepted, parent checks failed: ' + verdict['report'][:400]
                    self._event(row, 'node_failed', node=parent['id'], reason=parent['error'][:300])
        return None

    @staticmethod
    def _loose_ends(row):
        return [a['id'] for n in row['nodes'] for a in n['attempts']
                if a.get('cancel_pending') or (a.get('close') and not a.get('closed'))]

    def _sweep(self, run_id):
        """Retry what an earlier pass could not finish: cancels the task engine refused, gated
        closes, and stop on a promotion whose outcome is unknown. False when the run stops."""
        row = self._read(run_id)
        doubt = []
        for node in row['nodes']:
            for attempt in node['attempts']:
                if attempt.get('cancel_pending'):
                    self._cancel_attempt(run_id, node['id'], attempt['id'], attempt.get('cancel_reason') or 'operator',
                                         message=attempt.get('cancel_message') or '')
                if attempt.get('close') and not attempt.get('closed'):
                    self._close(run_id, node['id'], attempt['id'], retry=True)
                if (attempt.get('promotion') or {}).get('state') == 'intent':
                    doubt.append(attempt['id'])
        if doubt:
            with self._mutate(run_id) as row:
                if row['status'] == 'active':
                    row.update(status='unknown', error=(
                        f'The promotion of attempt {doubt[0]} was interrupted after its intent was recorded; the project '
                        'folder may hold part of it. Inspect the folder (git status) and the attempt\'s checkout, then '
                        'resume to re-apply it (re-applying is content-idempotent).'))
                    self._event(row, 'promotion_in_doubt', attempt=doubt[0])
            return False
        return True

    # ------------------------------------------------------------------ launches
    def _request_id(self, row, attempt_id):
        request_id = f'{row["client_request_id"]}:{attempt_id}'
        if len(request_id) > REQUEST_ID_MAX:
            request_id = f'{row["id"]}:{attempt_id}'      # fixed-length hash form
        return request_id

    def _launch(self, row, node, *, kind, strategy, overrides=None, generation=0, from_attempt=None):
        """One attempt (kept for callers): a wave of one."""
        spec = {'kind': kind, 'strategy': strategy, 'overrides': overrides or {}, 'generation': generation,
                'from_attempt': from_attempt}
        launched = self._launch_wave(row['id'], node['id'], [spec])
        return launched[0] if launched else None

    def _launch_wave(self, run_id, node_id, specs):
        """Every intent of the wave is written in ONE record write before the first submit (a crash
        mid-wave never shrinks a first wave), then each is submitted outside the lock and recorded
        by attempt id. A cancel that lands before a submit stops that submit."""
        intents = []
        with self._mutate(run_id) as row:
            node, _ = _find(row, node_id)
            if row.get('cancel_requested') or row['status'] not in ('queued', 'active'):
                self._event(row, 'launch_refused', node=node_id, reason='the run is being cancelled')
                return []
            for spec in specs:
                budget = row['budget']
                if budget['agents_max'] and budget['agents_started'] >= budget['agents_max']:
                    self._event(row, 'launch_refused', node=node_id, reason='agents_max reached')
                    break
                attempt = self._intent(row, node, **spec)
                if attempt is not None and (attempt.get('body') or (attempt.get('kernel') or {}).get('pending')):
                    intents.append(attempt['id'])
        launched = []
        for attempt_id in intents:
            if self._read(run_id).get('cancel_requested'):
                self._cancel_attempt(run_id, node_id, attempt_id, 'operator')
                continue
            self._dispatch(run_id, node_id, attempt_id, 'launched')
            launched.append(_find(self._read(run_id), node_id, attempt_id)[1])
        return launched

    def _intent(self, row, node, *, kind, strategy, overrides=None, generation=0, from_attempt=None):
        """Append one durable launch intent (called under the run lock). The exact task body rides
        on the intent until the task id is recorded, so a crash between the two re-submits the same
        request id (the task engine returns the reserved task) instead of losing it."""
        policy, base = row['policy'], row['base']
        overrides = overrides or {}
        attempt_id = f'{node["id"]}-a{len(node["attempts"])}'
        request_id = self._request_id(row, attempt_id)
        engine = overrides.get('engine') or node.get('engine') or base['engine']
        target = overrides.get('node') or node.get('node') or base['node']
        model = overrides.get('model') or base['model']
        cwd, worktree, checkout_agent = base['cwd'], True, ''
        attempt = {'id': attempt_id, 'kind': kind, 'strategy': strategy, 'engine': engine, 'node': target, 'model': model,
                   'generation': generation, 'request_id': request_id, 'task_id': '', 'status': 'queued',
                   'started': self.clock(), 'finished': None, 'failure': None, 'verdict': None, 'from': from_attempt}
        if overrides:
            attempt['overrides'] = dict(overrides)
        if node.get('sheet'):
            return self._kernel_intent(row, node, attempt, engine, target, model)
        if kind == 'handoff':
            previous = next((a for a in node['attempts'] if a['id'] == from_attempt), None) or {}
            refusal = ''
            if previous.get('remote'):
                refusal = ('remote handoff unsupported: a successor cannot be started in the remote node\'s checkout '
                           'that holds its predecessor\'s partial work')
            elif not previous.get('workspace') or not os.path.isdir(previous['workspace']):
                refusal = 'the predecessor\'s checkout is not available on this host'
            if refusal:
                # recorded, never launched into a fresh checkout that lacks the partial files
                attempt.update(engine=previous.get('engine') or engine, node=previous.get('node') or target,
                               status='failed', failure='REFUSAL', finished=self.clock(), error=refusal)
                node['attempts'].append(attempt)
                self._event(row, 'launch_refused', node=node['id'], attempt=attempt_id, reason=refusal)
                return attempt
            # the successor continues in the predecessor's own checkout, where the partial files are
            engine, target = previous.get('engine') or engine, previous.get('node') or target
            cwd, worktree = previous['workspace'], False
            checkout_agent = previous.get('checkout_agent') or previous.get('agent_id') or ''
            attempt.update(engine=engine, node=target, checkout_agent=checkout_agent)
        prompt = POLICY.localize(self._attempt_instruction(row, node, kind, generation, from_attempt), base['cwd'])
        note = base['context_note']
        if kind == 'regen' and strategy == 'feedback':
            failed = [a for a in node['attempts'] if a.get('status') == 'failed' and a.get('verdict') and a.get('kind') != 'planner']
            if failed:
                feedback = POLICY.feedback_note(node['statement'], failed[-1]['verdict'], policy)
                if feedback:
                    note = feedback + ('\n\n' + note if note else '')
        if engine == LOCAL_ENGINE and kind in ('candidate', 'regen'):
            note = (POLICY.LOCAL_LOCK + ('\n\n' + note[:600] if note else ''))[:1200]
        elif POLICY.CHECKOUT_LOCK not in note:
            note = POLICY.CHECKOUT_LOCK + ('\n\n' + note if note else '')
        # mode 'agent': the whole prompt (statement plus the autogen rules) is ONE instruction; lines
        # mode would split the rules into further statements.
        body = {'client_request_id': request_id, 'instruction': prompt, 'mode': 'agent', 'engine': engine,
                'node': target, 'cwd': cwd, 'worktree': worktree, 'auto': True, 'auto_next': True,
                'headless': bool(base.get('headless', True)), 'context_note': note[:12000]}
        if model:
            body['model'] = model
        if base.get('effort'):
            body['effort'] = base['effort']
        attempt['body'] = body
        node['attempts'].append(attempt)
        row['budget']['agents_started'] += 1
        node['engine'], node['node'] = engine, target
        if kind == 'handoff':
            node['handoffs'] = node.get('handoffs', 0) + 1
        if kind == 'planner':
            node['planners'] = node.get('planners', 0) + 1
        self._event(row, 'launch_intent', node=node['id'], attempt=attempt_id, request_id=request_id, kind=kind,
                    strategy=strategy, engine=engine, target=target)
        return attempt

    def _dispatch(self, run_id, node_id, attempt_id, event):
        """Submit a recorded intent outside the lock, then record the task id by attempt id."""
        _, attempt = _find(self._read(run_id), node_id, attempt_id)
        if attempt is not None and attempt.get('kernel'):
            return self._dispatch_kernel(run_id, node_id, attempt_id, event)
        if attempt is None or attempt.get('task_id') or not attempt.get('body'):
            return
        error = None
        try:
            result = self.task_runner.submit(attempt['body'])
        except TaskError as exc:
            result, error = None, exc
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if attempt is None or attempt.get('task_id') or 'body' not in attempt:
                return
            attempt.pop('body', None)
            if error is None:
                attempt['task_id'] = result['task']['id']
                attempt['status'] = 'running'
                attempt['duplicate'] = bool(result.get('duplicate'))
                self._event(row, event, node=node_id, attempt=attempt_id, task=attempt['task_id'],
                            duplicate=attempt['duplicate'])
            else:
                attempt.update(status='failed', failure='REFUSAL' if 'refus' in str(error).lower() else 'INFRASTRUCTURE',
                               finished=self.clock(), error=str(error)[:500])
                self._event(row, 'launch_failed', node=node_id, attempt=attempt_id, error=str(error)[:300])

    def _attempt_instruction(self, row, node, kind, generation, from_attempt):
        """The attempt's instruction BEFORE localization (statements name the project folder)."""
        policy, base = row['policy'], row['base']
        can_split = not node.get('perpetual') and node.get('depth', 0) < self._max_depth(policy)
        suffix = POLICY.worker_suffix(policy, node['index'], can_split=can_split)
        if base.get('engine') == LOCAL_ENGINE and kind in ('candidate', 'regen'):
            # a small local model driven as an agent (the harness that was tried admitted 7168 tokens of input,
            # tool schemas included): the statement and one rule, nothing a 4B model would copy or a 1B model
            # would drown in
            return node['statement'] + '\n\n' + POLICY.LOCAL_RULE
        if kind == 'designer':
            return POLICY.designer_prompt(node['statement'], base['cwd'], policy)
        if kind == 'planner':
            if from_attempt:
                previous = next((a for a in node['attempts'] if a['id'] == from_attempt), None)
                return POLICY.split_remaining_prompt(node['statement'], (previous or {}).get('checkpoint') or {},
                                                     base['cwd'], policy, node['depth'])
            return POLICY.split_prompt(node['statement'], base['cwd'], policy, node['depth'])
        if kind == 'handoff':
            previous = next((a for a in node['attempts'] if a['id'] == from_attempt), None)
            checkpoint = (previous or {}).get('checkpoint') or {}
            return POLICY.handoff_prompt(node['statement'], checkpoint, generation) + '\n\n' + suffix
        if kind == 'perpetual':
            # the cursor of the last promoted generation: a failed generation's checkpoint never counts
            previous = next((a for a in reversed(node['attempts'])
                             if a.get('status') == 'generation_done' and a.get('checkpoint')), None)
            checkpoint = (previous or {}).get('checkpoint') or {}
            index = {'total': node.get('items_total', 0), 'recent': node.get('recent_items') or []} if node.get('items_total') else None
            return POLICY.perpetual_prompt(node['statement'], checkpoint, generation, policy['interval_seconds'], index) + '\n\n' + suffix
        return node['statement'] + '\n\n' + suffix

    # ------------------------------------------------------------------ observation
    def _observe(self, run_id, node_id, attempt_id, now):
        row = self._read(run_id)
        node, attempt = _find(row, node_id, attempt_id)
        if attempt is None or attempt['status'] not in OPEN:
            return
        if attempt.get('kernel'):
            return self._observe_kernel(run_id, node_id, attempt_id, now)
        if not attempt.get('task_id'):
            if attempt.get('body'):
                # A durable intent whose submit result was never recorded (the coordinator died in
                # between): the same request id adopts the reserved task or reserves it once.
                self._dispatch(run_id, node_id, attempt_id, 'launch_recovered')
            return
        try:
            task = self.task_runner.get(attempt['task_id'])
        except TaskError as exc:
            if getattr(exc, 'status', 400) == 404:
                with self._mutate(run_id) as row:
                    _, current = _find(row, node_id, attempt_id)
                    if current is not None and current['status'] in OPEN:
                        current.update(status='failed', failure='UNKNOWN', finished=now,
                                       error='the task receipt is missing: ' + str(exc)[:200])
                        self._event(row, 'attempt_failed', node=node_id, attempt=attempt_id, failure='UNKNOWN')
            return                       # a fenced or unreadable receipt (409, OSError) is transient
        self._reattach_task(task)
        status = task.get('status')
        step = (task.get('steps') or [{}])[0]
        if self._gated_live(step):
            # A review gate with a live remote agent and no evidence yet: the runner's own watcher may
            # be gone after a restart, and nothing else re-attaches a gated task (observed 2026-10-11:
            # two remote agents had finished while their tasks sat at awaiting_review for an hour).
            # This coordinator drives one observation pass itself, so the verdict never depends on
            # another thread.
            try:
                self.task_runner.advance(attempt['task_id'])
                task = self.task_runner.get(attempt['task_id'])
            except TaskError:
                return
            except Exception as exc:
                with self._mutate(run_id) as row:
                    self._event(row, 'child_observe_failed', node=node_id, attempt=attempt_id, error=str(exc)[:200])
                return
            status = task.get('status')
            step = (task.get('steps') or [{}])[0]
        if status == 'unknown' or step.get('status') == 'unknown':
            # the runner's no-replay contract: an uncertain launch or stop is the operator's to recover,
            # never a failure to regenerate from
            with self._mutate(run_id) as row:
                _, current = _find(row, node_id, attempt_id)
                if current is not None and current['status'] in OPEN:
                    current.update(status='unknown', error=str(task.get('error') or step.get('error') or 'task state unknown')[:500])
                    self._event(row, 'attempt_unknown', node=node_id, attempt=attempt_id, task=attempt['task_id'])
            return
        # A review gate counts as an ended turn only with positive evidence: a recorded
        # evidence capture or a done completion. A gate entered because the probe failed is waited on.
        gated = (step.get('status') == 'awaiting_review' and not step.get('running')
                 and (step.get('evidence') is not None or bool((step.get('completion') or {}).get('done'))))
        # The step is the unit of evidence: a one-line task whose step completed is done even
        # while its own coordinator has not yet recorded the task-level completion.
        completed = status == 'completed' or step.get('status') == 'completed'
        if not (completed or gated or status in ('failed', 'cancelled')):
            return
        effective = 'completed' if (completed or gated) else status
        workspace = self._workspace(task, step)
        remote = self._is_remote(step)
        verdict, checkpoint = None, None
        if effective == 'completed':
            verdict, checkpoint = self._verdict(row, node, attempt, task, step, workspace, remote)
        # a perpetual generation always writes its checkpoint: it is the lane's cursor, not a handoff
        failure = POLICY.classify(dict(task, status=effective), verdict,
                                  handoff=None if node.get('perpetual') else checkpoint,
                                  timeout_requested=bool(attempt.get('timeout_requested')))
        # Self-split (Parsel/ANPL, worker side): a worker that judged the statement too big wrote a
        # valid split instead of partial work. Its checks fail by construction; the split is the
        # result, exactly as a planner's, provided the tree may still grow at this depth.
        self_split = bool(failure is not None and (verdict or {}).get('self_split') and (verdict or {}).get('lines')
                          and attempt['kind'] in ('candidate', 'regen', 'handoff') and not node.get('perpetual')
                          and node.get('depth', 0) < self._max_depth(row['policy']))
        if self_split:
            failure = None
        close = ('next' if failure is None else 'cancel') if gated and not completed else ''
        named = POLICY.statement_files(node['statement'])['files']
        metrics = POLICY.progress_metrics(verdict, checkpoint, named=named)
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if attempt is None or attempt['status'] not in OPEN:
                return
            for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed'):
                attempt.pop(key, None)            # the task ended: a pending cancel has nothing to stop
            attempt['workspace'] = workspace
            attempt['agent_id'] = step.get('agent_id') or ''
            attempt['remote'] = remote
            if not attempt.get('checkout_agent'):
                attempt['checkout_agent'] = attempt['agent_id']
            attempt['finished'] = now
            lines = None
            if verdict is not None and 'lines' in verdict:
                lines = verdict.pop('lines')
                if failure is None and attempt['kind'] == 'planner':
                    attempt['split'] = lines
            attempt['verdict'] = verdict
            if close:
                # the verdict and failure are durable BEFORE the gated task is closed
                attempt['close'], attempt['closed'] = close, False
            if self_split:
                # the attempt becomes the node's planner: _accept splits it, nothing is promoted
                attempt.update(kind='planner', strategy='self_split', self_split=True, split=lines)
                node['planners'] = node.get('planners', 0) + 1
                self._event(row, 'attempt_self_split', node=node_id, attempt=attempt_id, lines=len(lines))
            if attempt['kind'] == 'planner' and failure is not None:
                node['split_refused'] = True
            if attempt['kind'] == 'designer':
                # the test designer never competes: its script becomes a check on every later candidate
                if failure is None:
                    attempt['status'] = 'design_done'
                    node['designed'] = (verdict or {}).get('design') or ''
                    node['needs_design'] = False
                    self._event(row, 'design_done', node=node_id, attempt=attempt_id, chars=len(node['designed']))
                else:
                    attempt.update(status='failed', failure=failure,
                                   error=str(task.get('error') or (verdict or {}).get('report') or '')[:500])
                    node['needs_design'] = False      # best effort: candidates run without a designed test
                    self._event(row, 'design_failed', node=node_id, attempt=attempt_id, failure=failure)
                verdict = None                        # a designer's verdict is not candidate progress
            elif failure is None and node.get('perpetual'):
                # a passing generation is promoted now (each runs in its own checkout); it is a
                # finished generation, never the node's winner
                attempt['status'] = 'promoting'
                if checkpoint and checkpoint.get('valid'):
                    attempt['pending_checkpoint'] = checkpoint
            elif failure is None:
                attempt['status'] = 'accepted'
                self._event(row, 'attempt_accepted', node=node_id, attempt=attempt_id, checks=len(verdict['checks']))
            elif failure == 'CONTEXT_EXHAUSTED' and not node.get('perpetual'):
                attempt['status'] = 'handoff'
                attempt['checkpoint'] = checkpoint
                node['generation'] = attempt.get('generation', node.get('generation', 0))
                self._event(row, 'attempt_handoff', node=node_id, attempt=attempt_id)
            else:
                attempt['status'] = 'failed'
                attempt['failure'] = failure
                # public check output only: hidden and fetch internals never reach the record's error
                attempt['error'] = str(task.get('error') or (verdict or {}).get('report') or '')[:500]
                self._event(row, 'attempt_failed', node=node_id, attempt=attempt_id, failure=failure)
                self._designed_outcome(row, node, attempt, verdict)
            if attempt['kind'] in ('candidate', 'regen', 'handoff'):
                self._progress(node, attempt, metrics, failure)
        if close:
            self._close(run_id, node_id, attempt_id)

    def _designed_outcome(self, row, node, attempt, verdict):
        """The designer's script is evidence, not law: when two candidates in a row pass every
        other check and fail only the designed test, the script is retired (kept on the record)."""
        if not node.get('designed') or attempt['kind'] not in ('candidate', 'regen', 'handoff') or not verdict:
            return
        failed = {c.get('kind') for c in verdict.get('checks') or [] if not c.get('passed')}
        if failed == {'designed'}:
            node['designed_only'] = node.get('designed_only', 0) + 1
            if node['designed_only'] >= 2:
                node['designed_retired'] = node['designed']
                node['designed'] = ''
                self._event(row, 'design_retired', node=node['id'], attempt=attempt['id'],
                            reason='two candidates in a row failed only the designed test')
        else:
            node['designed_only'] = 0

    @staticmethod
    def _max_depth(policy):
        return POLICY.HARD_DEPTH if policy.get('until_done') else policy['depth']

    @staticmethod
    def _sandbox(folder, home, extra_files=()):
        return sandbox_prefix(folder, home, extra_files)

    def _progress(self, node, attempt, metrics, failure):
        """Progress bookkeeping: an attempt counts as progress only when it beat the node's best on
        a code-verified axis (a new named file, more checks passing). The node's stall counters are
        derived from the attempts afterwards (POLICY.stale_count / handoff_stale / recent_progress);
        `handoff_progress` is kept on the record for readers, no rule reads it."""
        best = node.get('progress') or {}
        progress = POLICY.is_progress(best, metrics)
        attempt['progress'] = {**metrics, 'new': progress}
        if attempt['status'] == 'handoff':
            node['handoff_progress'] = progress
        if progress:
            node['progress'] = POLICY.merge_progress(best, metrics)
            node['stale'] = 0
            node['progress_recent'] = True
        else:
            # any attempt without progress ends the feedback/fresh repeat exemption (a failing machine
            # or a refused launch must not be retried plainly forever)
            node['progress_recent'] = False
        # the counters shown to the operator are derived from the attempts (a timeout or a launch
        # failure never passes through here, yet counts)
        node['stale'] = POLICY.stale_count(node)
        node['handoff_stale'] = POLICY.handoff_stale(node)

    def _index_items(self, row, node, attempt, checkpoint):
        """Perpetual dedup index: the items a PROMOTED generation lists (sources, findings) are keyed
        by DOI, URL or text and appended once to AUTOGEN-INDEX.jsonl in the project folder; a
        generation that adds no new key counts toward saturation. Rows this very attempt wrote
        earlier (a crash between the append and the record write) count as its own new items.
        Bad lines or bytes are skipped; the file must be a regular file (never a symlink); one
        locked write per generation. Called under the run lock."""
        items = (checkpoint or {}).get('items') if (checkpoint or {}).get('valid') else None
        path = os.path.join(row['base']['cwd'], POLICY.INDEX_FILE)
        known, own = set(), set()
        try:
            if os.path.lexists(path) and not os.path.isfile(path) or os.path.islink(path):
                raise OSError('the index is not a regular file')
            with open(path, encoding='utf-8', errors='replace') as handle:
                for line in handle:
                    try:
                        rowx = json.loads(line)
                        key = rowx.get('key')
                    except (ValueError, AttributeError, TypeError):
                        continue
                    if not isinstance(key, str):
                        continue
                    if rowx.get('run') == row['id'] and rowx.get('attempt') == attempt['id']:
                        own.add(key)
                    else:
                        known.add(key)
        except OSError as exc:
            if os.path.lexists(path):
                self._event(row, 'index_unreadable', node=node['id'], attempt=attempt['id'], error=str(exc)[:200])
                known = None
        new = []
        for item in items or []:
            if not isinstance(item, str):
                continue
            key = POLICY.items_key(item)
            if known is None or key in known or key in {k for k, _ in new}:
                continue
            new.append((key, item))
        to_write = [(k, i) for k, i in new if k not in own]
        if to_write:
            payload = ''.join(json.dumps({'key': key, 'item': item[:400], 'run': row['id'], 'attempt': attempt['id'],
                                          'generation': attempt.get('generation', 0), 'at': self.clock()}) + '\n'
                              for key, item in to_write)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    os.write(fd, payload.encode('utf-8'))
                finally:
                    os.close(fd)
            except OSError as exc:
                self._event(row, 'index_write_failed', node=node['id'], attempt=attempt['id'], error=str(exc)[:200])
                new = [(k, i) for k, i in new if k in own]
        attempt['items_new'] = len(new)
        attempt['items_listed'] = len(items or [])
        node['items_total'] = node.get('items_total', 0) + len(new)
        node['recent_items'] = ((node.get('recent_items') or []) + [k for k, _ in new])[-30:]
        node['stale_generations'] = 0 if new else node.get('stale_generations', 0) + 1
        if items is not None:
            self._event(row, 'items_indexed', node=node['id'], attempt=attempt['id'], new=len(new), listed=len(items),
                        total=node['items_total'])

    @staticmethod
    def _gated_live(step):
        return (step.get('status') == 'awaiting_review' and bool(step.get('running')) and step.get('evidence') is None
                and not bool((step.get('completion') or {}).get('done')))

    def _reattach_task(self, task):
        """A child task stranded by a restart is re-attached through the runner's own path."""
        resume = getattr(self.task_runner, 'reattach', None)
        if resume is None:
            return
        try:
            resume(task)
        except Exception:
            pass

    def _close(self, run_id, node_id, attempt_id, retry=False):
        """Close a gated child task (next on a pass, cancel on a failure); a refusal (the task's
        own coordinator holds its lease) is retried on later passes while the gate stands."""
        _, attempt = _find(self._read(run_id), node_id, attempt_id)
        if attempt is None or not attempt.get('close') or attempt.get('closed'):
            return
        error = ''
        if retry:
            try:
                task = self.task_runner.get(attempt['task_id'])
                step = (task.get('steps') or [{}])[0]
                if step.get('status') != 'awaiting_review':
                    error = None         # the gate is gone (finished or cancelled elsewhere)
            except TaskError as exc:
                if getattr(exc, 'status', 400) == 404:
                    error = None
        if error == '':
            try:
                self.task_runner.control(attempt['task_id'], attempt['close'])
                error = None
            except TaskError as exc:
                error = str(exc)[:200]
        with self._mutate(run_id) as row:
            _, attempt = _find(row, node_id, attempt_id)
            if attempt is None:
                return
            if error is None:
                attempt['closed'] = True
                attempt.pop('close_error', None)
            elif attempt.get('close_error') != error:
                attempt['close_error'] = error
                self._event(row, 'close_failed', attempt=attempt_id, error=error)

    @staticmethod
    def _workspace(task, step):
        agent = step.get('agent') or {}
        git = agent.get('git') or {}
        return git.get('cwd') or step.get('workspace') or agent.get('cwd') or task.get('workspace') or ''

    # ------------------------------------------------------------------ cancellation
    def _cancel_attempt(self, run_id, node_id, attempt_id, reason, message=''):
        """Cancel one attempt's task: a locked intent, the control call outside the lock, then the
        record. An intent with a body and no task id is cancelled through its deterministic task
        id. A refused control keeps the attempt in its slot (cancel_failed) and is retried each
        pass, so no regeneration runs beside a live agent. True when the attempt is settled."""
        _, current = _find(self._read(run_id), node_id, attempt_id)
        if current is not None and current.get('kernel'):
            return self._cancel_kernel(run_id, node_id, attempt_id, reason, message)
        with self._mutate(run_id) as row:
            _, attempt = _find(row, node_id, attempt_id)
            if attempt is None:
                return True
            if attempt['status'] not in OPEN and attempt['status'] != 'unknown':
                # its task ended on its own meanwhile: nothing is left to stop
                for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed'):
                    attempt.pop(key, None)
                return True
            if reason != 'interrupted':
                attempt['cancel_pending'] = True
                attempt['cancel_reason'] = reason
                if message:
                    attempt['cancel_message'] = message
                if reason == 'timeout':
                    attempt['timeout_requested'] = True   # survives a crash: re-observation reads TIMEOUT
            task_id = attempt.get('task_id') or (deterministic_task_id(attempt['request_id']) if attempt.get('body') else '')
            derived = not attempt.get('task_id')
        error, finished = None, False
        if task_id:
            try:
                result = self.task_runner.control(task_id, 'cancel')
                # a cancel that lands after the task completed changes nothing: observe its result
                finished = not derived and ((result or {}).get('task') or {}).get('status') == 'completed'
            except TaskError as exc:
                if derived and getattr(exc, 'status', 400) == 404:
                    if reason == 'interrupted':
                        return True       # never reserved: the intent stays for Resume to submit
                else:
                    error = str(exc)[:300]
        with self._mutate(run_id) as row:
            _, attempt = _find(row, node_id, attempt_id)
            if attempt is None or (attempt['status'] not in OPEN and attempt['status'] != 'unknown'):
                return True
            if error:
                if attempt.get('cancel_failed') != error:
                    attempt['cancel_failed'] = error
                    self._event(row, 'cancel_failed', node=node_id, attempt=attempt_id, error=error)
                if reason == 'interrupted':
                    attempt.update(cancel_pending=True, cancel_reason='operator')
                return False
            if finished and reason == 'timeout':     # the next observation judges its files
                for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed'):
                    attempt.pop(key, None)
                return True
            for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed', 'body'):
                attempt.pop(key, None)
            text = message or {'timeout': 'attempt exceeded the policy attempt_seconds allowance',
                               'superseded': 'another candidate was accepted first',
                               'interrupted': 'the coordinator was interrupted; the attempt was stopped so it does not run unsupervised',
                               }.get(reason, 'the run was cancelled')
            attempt.update(status='failed', failure='TIMEOUT' if reason == 'timeout' else 'CANCELLED',
                           finished=self.clock(), error=text)
            if reason == 'timeout':
                self._event(row, 'attempt_timeout', node=node_id, attempt=attempt_id)
        return True

    def _cancel_run(self, run_id):
        row = self._read(run_id)
        settled = True
        for node in row['nodes']:
            for attempt in node['attempts']:
                if attempt['status'] in OPEN or attempt['status'] == 'unknown' or attempt.get('cancel_pending'):
                    settled = self._cancel_attempt(run_id, node['id'], attempt['id'], 'operator') and settled
        if not settled:
            return True                   # a refused cancel is retried next pass
        with self._mutate(run_id) as row:
            if row['status'] in ('queued', 'active', 'unknown', 'stuck'):
                row.update(status='cancelled')
                self._event(row, 'cancelled')
        return False

    # ------------------------------------------------------------------ verdicts
    def _verdict(self, row, node, attempt, task, step, workspace, remote):
        """Code decides. Remote attempts are verified at home after commit -> fetch, in a detached
        staging checkout of the fetched ref; local own-checkout attempts in place. Returns
        (verdict, checkpoint) where the checkpoint is read while the files are reachable."""
        policy = row['policy']
        # The operator's public commands are keyed by top-level statement index; a split child keeps
        # its own index among its siblings, which must not pick up another statement's commands.
        index = node['index'] if node['parent'] is None else node['id']
        planner = attempt['kind'] == 'planner'
        designer = attempt['kind'] == 'designer'
        plan = {'checks': [], 'files': [], 'read_only': True} if (planner or designer) else self._checks_plan(node, index, policy)
        evidence = step.get('evidence') or {}
        evidence = evidence if isinstance(evidence, dict) else {}
        staging, verify_in, changes = None, workspace, None
        try:
            if remote:
                staging, verify_in, changes, error = self._stage_remote(row, attempt, step)
                if error:
                    return ({'passed': False, 'checks': [{'kind': 'fetch', 'passed': False, 'public': True, 'output': error[:1500]}],
                             'files_changed': None, 'report': error[:300]}, None)
            if planner:
                return self._planner_verdict(row, node, verify_in, attempt=attempt, remote=remote), None
            if designer:
                return self._designer_verdict(row, node, verify_in, attempt=attempt, remote=remote), None
            if not remote:
                changes = self._local_changes(step, evidence, workspace)
            checks = self._run_checks(plan, verify_in, row['budget']['deadline'])
            if node.get('designed') and verify_in:
                checks.append(self._designed_check(node['designed'], verify_in, row['budget']['deadline']))
            files_changed = len(changes) if changes is not None else None
            if policy.get('require_change') and not plan['read_only'] and changes is not None:
                # a reopened parent (its children's files are already in the project) must change
                # something, not every named file again
                for spec in plan['checks'] if not node.get('integrations') else []:
                    if spec.get('changed') and not self._changed(spec['file'], changes):
                        checks.append({'kind': 'change', 'file': spec['file'], 'passed': False, 'public': True,
                                       'output': f'{spec["file"]} was not added or modified by this attempt'})
                if files_changed == 0 and not any(c['kind'] == 'change' for c in checks):
                    checks.append({'kind': 'change', 'passed': False, 'public': True,
                                   'output': 'no workspace file changed since launch; the statement writes files'})
            if evidence.get('warning'):
                checks.append({'kind': 'claim', 'passed': False, 'public': True, 'output': evidence['warning'][:300]})
            verdict = {'passed': all(c['passed'] for c in checks), 'checks': checks, 'files_changed': files_changed,
                       'report': _public_report(checks), 'staging': bool(staging)}
            if changes is not None:
                verdict['changed'] = sorted(changes)[:64]
            if (not verdict['passed'] and policy.get('self_split', True) and verify_in and not node.get('perpetual')
                    and attempt['kind'] in ('candidate', 'regen', 'handoff') and not attempt.get('kernel')):
                # a worker may answer "too big" with a split file instead of partial work
                split = self._planner_verdict(row, node, verify_in, quiet=True, attempt=attempt, remote=remote)
                if split.get('lines'):
                    verdict.update(self_split=True, lines=split['lines'])
                elif split.get('present'):
                    verdict['checks'].append({'kind': 'split', 'passed': False, 'public': True, 'output': split['report'][:300]})
                    verdict['report'] = _public_report(verdict['checks'])
            return verdict, (self._checkpoint(attempt, verify_in, remote) if verify_in and not attempt.get('kernel') else None)
        finally:
            if staging:
                self._drop_staging(row, attempt, staging)

    @staticmethod
    def _changed(name, changes):
        if name in changes:
            return True
        tail = '/' + name.split('/')[-1]
        matches = [c for c in changes if c == name.split('/')[-1] or c.endswith(tail)]
        return '/' not in name and len(matches) == 1      # a basename counts only when unique

    def _local_changes(self, step, evidence, workspace):
        """Paths this attempt added, modified or removed (relative to its workspace), from the task
        evidence's launch inventory; from the checkout's git state when that inventory was truncated
        (its 200-file cap) or absent. None when unverifiable. Autogen control files never count."""
        git = ((step.get('agent') or {}).get('git') or {})
        inventory = evidence.get('inventory') or {}
        changes = evidence.get('changes')
        if isinstance(changes, dict) and not inventory.get('truncated'):
            paths = set(changes.get('added') or []) | set(changes.get('modified') or []) | set(changes.get('removed') or [])
            return {p for p in paths if p not in POLICY.CONTROL_FILES}
        if git.get('worktree') and git.get('base_sha') and workspace:
            return self._git_changes(git['worktree'], workspace, git['base_sha'])
        return None

    def _git_changes(self, top, workspace, base_sha, ref=None):
        """Changed paths between base_sha and the checkout (working tree, untracked included) or a
        fetched ref, relative to `workspace` (a folder inside the repository at `top`)."""
        if ref:
            listings = [['git', '-C', top, 'diff', '--name-only', '--no-renames', '-z', base_sha, ref]]
        else:
            listings = [['git', '-C', top, 'diff', '--name-only', '--no-renames', '-z', base_sha],
                        ['git', '-C', top, 'ls-files', '--others', '--exclude-standard', '-z']]
        paths = set()
        for argv in listings:
            out = self.git(argv, top)
            if out['rc'] != 0:
                return None
            paths |= {p for p in out['out'].split('\0') if p}
        prefix = os.path.relpath(workspace, top) if workspace else '.'
        if prefix.startswith('..'):
            return None
        if prefix != '.':
            paths = {p[len(prefix) + 1:] for p in paths if p.startswith(prefix + '/')}
        return {p for p in paths if p not in POLICY.CONTROL_FILES}

    def _run_checks(self, plan, verify_in, deadline=None):
        """Evaluate one statement's planned checks in a folder. Named files are looked up directly
        (exact relative path, then a bounded search), never through a capped listing. Checks stop
        at the run deadline; each subprocess gets at most the time that remains."""
        checks = []
        for spec in plan['checks']:
            result = dict(spec)
            result.pop('changed', None)
            remaining = (deadline - self.clock()) if deadline is not None else CHECK_TIMEOUT
            timeout = max(1, min(CHECK_TIMEOUT, int(remaining)))
            if spec['kind'] == 'exists':
                ok = bool(verify_in) and _locate(verify_in, spec['file']) is not None
                result.update(passed=ok, output='' if ok else f'{spec["file"]} was not created')
            elif spec['kind'] == 'absent':
                ok = bool(verify_in) and _safe_rel(spec['file']) and not os.path.lexists(os.path.join(verify_in, spec['file']))
                result.update(passed=ok, output='' if ok else f'{spec["file"]} still exists')
            elif remaining <= 0:
                result.update(passed=False, output='the run deadline passed; this check was not run')
            elif spec['kind'] == 'syntax':
                target = _locate(verify_in, spec['file']) if verify_in else None
                if target is None:
                    result.update(passed=False, output=f'{spec["file"]} missing')
                else:
                    argv = [a if a != spec['file'] else target for a in spec['argv']]
                    out = self.check_runner(argv, verify_in, timeout=timeout)
                    result.update(passed=out['rc'] == 0, output=out['out'][-1500:])
            else:
                out = self.check_runner(spec['command'], verify_in, timeout=timeout, shell=True)
                result.update(passed=out['rc'] == 0, output=out['out'][-1500:])
            checks.append(result)
        return checks

    def _parent_verdict(self, row, node):
        """A split statement is accepted only when ITS OWN checks pass in the promoted project
        workspace after every child was accepted: children covering the parent's files is a
        plan-time guarantee, not evidence that the assembled result satisfies the parent."""
        index = node['index'] if node['parent'] is None else node['id']
        plan = self._checks_plan(node, index, row['policy'])
        checks = self._run_checks(plan, row['base']['cwd'], row['budget']['deadline'])
        passed = all(c['passed'] for c in checks)
        return {'passed': passed, 'checks': checks, 'files_changed': None, 'report': _public_report(checks),
                'scope': 'parent_after_children'}

    def _planner_verdict(self, row, node, verify_in, quiet=False, attempt=None, remote=False):
        """quiet: a candidate's workspace is probed for a self-split; a missing file is no finding.
        A split of the REMAINING work (attempt['from'] = the last handoff) may leave out files that
        handoff's checkpoint lists: they exist in its checkout and are promoted before the children run."""
        present = ()
        if attempt is not None and attempt.get('from'):
            previous = next((a for a in node['attempts'] if a['id'] == attempt['from']), None) or {}
            present = tuple(((previous.get('checkpoint') or {}).get('files') or []))
        path = os.path.join(verify_in, POLICY.SPLIT_FILE) if verify_in else ''
        try:
            with open(path, encoding='utf-8', errors='replace') as handle:
                text = handle.read(20000)
        except OSError:
            if quiet:
                return {'passed': False, 'present': False, 'checks': [], 'files_changed': None, 'report': ''}
            return {'passed': False, 'checks': [{'kind': 'exists', 'file': POLICY.SPLIT_FILE, 'passed': False, 'public': True,
                                                 'output': 'the planner wrote no split file'}], 'files_changed': None,
                    'report': 'no split file'}
        if not remote and attempt is not None and self._predates(path, attempt):
            # carried over from the project or an earlier attempt (a checkout copies untracked files
            # with their old timestamps): not this worker's answer
            if quiet:
                return {'passed': False, 'present': False, 'checks': [], 'files_changed': None, 'report': ''}
            return {'passed': False, 'present': True, 'checks': [{'kind': 'split', 'passed': False, 'public': True,
                                                                  'output': POLICY.SPLIT_FILE + ' predates this attempt'}],
                    'files_changed': None, 'report': POLICY.SPLIT_FILE + ' predates this attempt'}
        if quiet and node.get('depth', 0) >= self._max_depth(row['policy']):
            return {'passed': False, 'present': True, 'checks': [], 'files_changed': None,
                    'report': f'{POLICY.SPLIT_FILE} was written at the maximum depth; the statement cannot be split further'}
        # the planner was told "the current working folder"; stored children name the project folder
        text = POLICY.delocalize(text, row['base']['cwd'])
        lines, errors = POLICY.parse_split(text, node['statement'], row['base']['cwd'], row['policy'], present=present)
        if errors:
            return {'passed': False, 'present': True, 'checks': [{'kind': 'split', 'passed': False, 'public': True,
                                                                  'output': '; '.join(errors)[:1500]}],
                    'files_changed': None, 'report': POLICY.SPLIT_FILE + ' refused: ' + '; '.join(errors)[:300]}
        return {'passed': True, 'present': True, 'checks': [{'kind': 'split', 'passed': True, 'public': True, 'output': f'{len(lines)} lines'}],
                'files_changed': None, 'report': '', 'lines': lines}

    @staticmethod
    def _predates(path, attempt):
        try:
            return os.path.getmtime(path) < float(attempt.get('started') or 0) - 5
        except (OSError, TypeError, ValueError):
            return False

    def _designer_verdict(self, row, node, verify_in, attempt=None, remote=False):
        """CodeT/AgentCoder: the designed script counts only when it is admissible bash (policy),
        parses (bash -n) and DISCRIMINATES: run in an empty folder it must exit non-zero. Its text is
        kept on the node (bounded) so every later candidate is checked against it."""
        path = os.path.join(verify_in, POLICY.DESIGN_FILE) if verify_in else ''
        try:
            with open(path, encoding='utf-8', errors='replace') as handle:
                text = handle.read(POLICY.DESIGN_MAX_CHARS + 1)
        except OSError:
            return {'passed': False, 'checks': [{'kind': 'exists', 'file': POLICY.DESIGN_FILE, 'passed': False, 'public': True,
                                                 'output': 'the designer wrote no test script'}], 'files_changed': None,
                    'report': 'no test script'}
        if not remote and attempt is not None and self._predates(path, attempt):
            why = POLICY.DESIGN_FILE + ' predates this attempt'
            return {'passed': False, 'checks': [{'kind': 'design', 'passed': False, 'public': True, 'output': why}],
                    'files_changed': None, 'report': why}
        ok, why = POLICY.design_valid(text)
        if not ok:
            return {'passed': False, 'checks': [{'kind': 'design', 'passed': False, 'public': True, 'output': why}],
                    'files_changed': None, 'report': why[:300]}
        deadline = row['budget']['deadline']
        empty = tempfile.mkdtemp(prefix='autogen-design-')             # truly empty: the script lives elsewhere
        home = tempfile.mkdtemp(prefix='autogen-design-home-')
        handle = tempfile.NamedTemporaryFile('w', prefix='.autogen-design-', suffix='.sh', delete=False, encoding='utf-8')
        try:
            handle.write(text)
            handle.close()
            script = handle.name
            parse = self.check_runner(['bash', '-n', script], empty, timeout=30)
            if parse['rc'] != 0:
                why = 'the test script does not parse: ' + parse['out'][-300:]
                return {'passed': False, 'checks': [{'kind': 'design', 'passed': False, 'public': True, 'output': why}],
                        'files_changed': None, 'report': why[:300]}
            remaining = (deadline - self.clock()) if deadline is not None else CHECK_TIMEOUT
            sandbox, prefix, shell = self._sandbox(empty, home, (script,))
            probe = self.check_runner(prefix + [shell, script], empty, timeout=max(1, min(CHECK_TIMEOUT, int(remaining))))
        finally:
            shutil.rmtree(empty, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)
            try:
                os.unlink(handle.name)
            except OSError:
                pass
        if probe['rc'] == SANDBOX_REFUSED and sandbox != 'none':
            why = 'the sandbox refused to run the test script: ' + probe['out'][-300:]
            return {'passed': False, 'checks': [{'kind': 'design', 'passed': False, 'public': True, 'output': why, 'sandbox': sandbox}],
                    'files_changed': None, 'report': why[:300]}
        if probe['rc'] == 0:
            why = 'the test script passes on an empty folder, so it tests nothing'
            return {'passed': False, 'checks': [{'kind': 'design', 'passed': False, 'public': True, 'output': why, 'sandbox': sandbox}],
                    'files_changed': None, 'report': why}
        if not POLICY.design_probe_ok(probe['rc'], probe['out']):
            why = f'the test script did not run to a verdict on an empty folder (exit {probe["rc"]}): ' + probe['out'][-300:]
            return {'passed': False, 'checks': [{'kind': 'design', 'passed': False, 'public': True, 'output': why, 'sandbox': sandbox}],
                    'files_changed': None, 'report': why[:300]}
        return {'passed': True, 'checks': [{'kind': 'design', 'passed': True, 'public': True, 'sandbox': sandbox,
                                            'output': f'discriminating: exit {probe["rc"]} on an empty folder'}],
                'files_changed': None, 'report': '', 'design': text}

    def _designed_check(self, script_text, verify_in, deadline=None):
        """Run the node's designed test against a throwaway copy of the candidate's files, with the
        script written into that copy as AUTOGEN-TESTS.sh (so `$0`-relative paths work); the
        candidate's own checkout, which promotion commits, is never touched."""
        remaining = (deadline - self.clock()) if deadline is not None else CHECK_TIMEOUT
        timeout = max(1, min(CHECK_TIMEOUT, int(remaining)))
        result = {'kind': 'designed', 'file': POLICY.DESIGN_FILE, 'public': True}
        if remaining <= 0:
            return dict(result, passed=False, output='the run deadline passed; the designed test was not run')
        home = tempfile.mkdtemp(prefix='autogen-designed-home-')
        scratch = tempfile.mkdtemp(prefix='autogen-designed-work-')
        unit = 'autogen-designed-' + os.path.basename(scratch)[-12:].replace('_', '-')
        try:
            work = os.path.join(scratch, 'w')
            copied = self._copy_workspace(verify_in, work)
            if copied is not True:
                return dict(result, passed=False, output='the designed test was not run: ' + str(copied))
            script = os.path.join(work, POLICY.DESIGN_FILE)        # the script sits beside the files it tests
            with open(script, 'w', encoding='utf-8') as handle:
                handle.write(script_text)
            sandbox, prefix, shell = self._sandbox(work, home, ())
            scope = self._scope(unit)
            out = self.check_runner(scope + prefix + [shell, script], work, timeout=timeout)
        finally:
            self._stop_scope(unit)
            shutil.rmtree(scratch, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)
        if out['rc'] == SANDBOX_REFUSED and sandbox != 'none':
            return dict(result, passed=False, output='the sandbox refused to run the designed test: ' + out['out'][-300:], sandbox=sandbox)
        return dict(result, passed=out['rc'] == 0, output=out['out'][-1500:], sandbox=sandbox + ('+scope' if scope else ''))

    COPY_LIMIT = 20000                      # entries a candidate workspace may hold to be copied for a designed test

    def _copy_workspace(self, source, target):
        """A throwaway copy of the candidate's files (never .git): the designed script can rewrite
        the copy without touching what promotion would commit. True, or the reason it was refused."""
        count = 0
        for _root, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if d != '.git']
            count += len(dirs) + len(files)
            if count > self.COPY_LIMIT:
                return f'the workspace holds more than {self.COPY_LIMIT} entries'
        try:
            shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns('.git'))
        except (OSError, shutil.Error) as exc:
            return f'copy failed: {str(exc)[:200]}'
        return True

    @staticmethod
    def _scope(unit):
        """A transient systemd user scope under SCOPE_SLICE bounds the check's tasks and memory
        and lets a leftover background process be stopped with the unit. Empty when unavailable or
        when SYMBLIC_SCOPE=0; the user bus is probed once per process, so a check never fails for
        want of a bus and reads as a failing script."""
        if os.environ.get('SYMBLIC_SCOPE', '1') == '0':
            return []
        if not shutil.which('systemd-run') or not os.environ.get('XDG_RUNTIME_DIR'):
            return []
        if 'ok' not in _SCOPE:
            try:
                _SCOPE['ok'] = subprocess.run(['systemd-run', '--user', '--scope', '--quiet', '--slice', SCOPE_SLICE,
                                               '--', '/bin/true'], capture_output=True, timeout=20).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _SCOPE['ok'] = False
        if not _SCOPE['ok']:
            return []
        # the check runner (_run) scrubs the environment, so systemd-run gets the bus variables
        # explicitly; the sandbox prefix after it (`env -i`) still scrubs the script's own environment
        bus = ['env'] + [f'{k}={os.environ[k]}' for k in ('XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS') if os.environ.get(k)]
        return bus + ['systemd-run', '--user', '--scope', '--quiet', '--unit', unit, '--slice', SCOPE_SLICE,
                      '-p', 'TasksMax=64', '-p', 'MemoryMax=1G', '--']

    @staticmethod
    def _stop_scope(unit):
        if not shutil.which('systemctl') or not os.environ.get('XDG_RUNTIME_DIR'):
            return
        try:
            subprocess.run(['systemctl', '--user', 'stop', unit + '.scope'], capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass

    def _checkpoint(self, attempt, folder, remote=False):
        path = os.path.join(folder, POLICY.CHECKPOINT_FILE)
        try:
            with open(path, encoding='utf-8') as handle:
                raw = handle.read(20000)
        except OSError:
            return None
        if not remote:                    # a staging checkout's mtimes are its own, not the worker's
            try:
                if os.path.getmtime(path) < float(attempt.get('started') or 0) - 5:
                    return {'valid': False, 'reason': 'checkpoint predates this attempt'}
            except OSError:
                return None
        try:
            claimed = json.loads(raw).get('files')
        except (ValueError, AttributeError):
            claimed = None
        present = [f for f in claimed if isinstance(f, str) and _safe_rel(f) and _is_file(folder, f)] if isinstance(claimed, list) else []
        return POLICY.checkpoint_valid(raw, present)

    # ------------------------------------------------------------------ remote staging
    def _is_remote(self, step):
        agent = step.get('agent') or {}
        try:
            return bool(self.task_runner.is_remote(agent))
        except Exception:
            return False

    def _staging_path(self, run_id, attempt_id):
        return self.dir / 'staging' / run_id / attempt_id.replace('.', '-')

    def _stage_remote(self, row, attempt, step):
        """commit on the node -> fetch home (the runner's fetch_remote) -> detached staging checkout of the
        fetched ref, under the autogen state folder (never inside the project). Returns (staging, verify_in,
        changes, error); changes come from `git diff base_sha ref`, so a no-op remote attempt is caught."""
        agent_id = step.get('agent_id')
        if not agent_id:
            return None, None, None, 'remote attempt has no agent identity'
        try:
            fetched = self.task_runner.fetch_remote(agent_id) or {}
        except Exception as exc:
            return None, None, None, f'commit/fetch from the node failed: {str(exc)[:200]}'
        ref = fetched.get('ref')
        main = fetched.get('main_root') or row['base']['cwd']
        if not ref or not main:
            return None, None, None, 'remote attempt has no fetched branch'
        staging = str(self._staging_path(row['id'], attempt['id']))
        self._clear_staging(main, staging)
        os.makedirs(os.path.dirname(staging), exist_ok=True)
        out = self.git(['git', '-C', main, 'worktree', 'add', '--detach', '-f', staging, ref], main)
        if out['rc'] != 0:
            return None, None, None, 'staging checkout failed: ' + out['out'][-300:]
        prefix = os.path.relpath(row['base']['cwd'], main)
        verify_in = staging if prefix in ('.', '') or prefix.startswith('..') else os.path.join(staging, prefix)
        changes = None
        if fetched.get('base_sha'):
            changes = self._git_changes(main, row['base']['cwd'] if not prefix.startswith('..') else main,
                                        fetched['base_sha'], ref=ref)
        return staging, verify_in, changes, None

    def _clear_staging(self, main, staging):
        """A leftover from a crashed verdict would make `worktree add` fail on every re-observation."""
        if os.path.lexists(staging):
            self.git(['git', '-C', main, 'worktree', 'remove', '--force', staging], main)
            shutil.rmtree(staging, ignore_errors=True)
        self.git(['git', '-C', main, 'worktree', 'prune'], main)

    def _drop_staging(self, row, attempt, staging):
        main = row['base']['cwd']
        out = self.git(['git', '-C', main, 'worktree', 'remove', '--force', staging], main)
        if out['rc'] != 0 or os.path.lexists(staging):
            shutil.rmtree(staging, ignore_errors=True)
            self.git(['git', '-C', main, 'worktree', 'prune'], main)
            with self._mutate(row['id']) as current:
                self._event(current, 'staging_drop_failed', attempt=attempt['id'], error=out['out'][-200:])

    # ------------------------------------------------------------------ kernel lane (local runs)
    def _checks_plan(self, node, index, policy):
        """The code checks of a statement: a spec sheet writes exactly its Assemble file (its prose is never
        read for file names); any other statement is planned by the policy."""
        if node.get('sheet'):
            return self.kernel.plan_checks(self.kernel.plan(node['statement'])['file'], index, policy)
        return POLICY.plan_checks(node['statement'], index, policy)

    @staticmethod
    def _best_run(node):
        """The node's build that accepted the most units (the latest on a tie): the source of `--keep`
        for the next build and of the stalled unit for a split. None before any unit was accepted."""
        best, most = None, 0
        for attempt in node.get('attempts') or []:
            kernel = attempt.get('kernel') or {}
            if kernel.get('mode') == 'build' and len(kernel.get('accepted') or []) >= max(1, most):
                best, most = kernel, len(kernel.get('accepted') or [])
        return best

    def _checkout_name(self, run_id, attempt_id):
        return f'autogen-{run_id[8:20]}-{attempt_id}'

    def _kernel_intent(self, row, node, attempt, engine, target, model):
        """Under the run lock: the durable intent of a kernel attempt (no task body). A candidate or a
        regeneration is a build of the node's sheet, keeping what its best earlier build (or, for a split
        child, its parent's) accepted; a planner is the split ask for the unit that build stopped at.
        Nothing starts here: `_dispatch_kernel` makes the checkout, compiles and starts the process."""
        kind, attempt_id = attempt['kind'], attempt['id']
        if node.get('status') != 'pending':
            return None                       # ended by an earlier intent of the same wave
        absent = row.get('model_absent') or []
        if target in absent:
            # a decision made from a placement that has since proved to lack the model: the next node that may
            # hold it takes the attempt (the operator's node first); with none left the statement ends here
            options = [n for n in [row['base']['node']] + list(row['policy'].get('nodes') or []) if n not in absent]
            if not options:
                until = bool(row['policy'].get('until_done'))
                node['status'] = 'stuck' if until else 'failed'
                node['error'] = f'{model} is not installed on any node this run may use (missing on {", ".join(absent)})'
                row.update(status=node['status'], error=f'Statement {node["id"]} is {node["status"]}: {node["error"]}')
                self._event(row, 'node_stuck' if until else 'node_failed', node=node['id'], reason=node['error'][:300])
                return None
            target = options[0]
            attempt['node'] = target
            if attempt.get('overrides', {}).get('node'):
                attempt['overrides'] = {**attempt['overrides'], 'node': target}
        spec = self.kernel.plan(node['statement'])
        mode = 'split' if kind == 'planner' else 'build'
        kernel = {'mode': mode, 'run_dir': str(self.dir / 'kernel' / row['id'] / attempt_id), 'applicators': [],
                  'seed': self.kernel.seed(row['id'], attempt_id), 'limits': dict(self.kernel.LIMITS),
                  'file': spec['file'], 'units_total': len(spec['units']), 'pid': None, 'program_sha256': ''}
        refusal = ''
        try:
            if kind not in ('candidate', 'regen', 'planner'):
                raise KernelError(f'a {kind} attempt does not apply to a spec sheet')
            if engine != LOCAL_ENGINE:
                raise KernelError('a spec sheet runs only on the local kernel lane (engine local)')
            kernel['applicators'] = [self.kernel.applicator(model, target, self._local_node())]
        except ValueError as exc:
            refusal = str(exc)
        best = self._best_run(node) or {}
        if mode == 'build':
            kernel.update(keep_from=best.get('run_dir') or node.get('keep_from') or '', label=spec['file'],
                          **self.kernel.SEARCH)
        elif not refusal:
            unit = self.kernel.stalled_unit(node['statement'], best.get('accepted') or [])
            if unit is None:
                node['split_impossible'] = True
                refusal = ('every unit of the sheet passed its examples, so no unit is left to split; the failing checks '
                           'are the operator\'s own: give the sheet examples that catch what they catch')
            else:
                kernel.update(unit=unit['name'], heading=unit['heading'], from_run=best.get('run_dir') or '',
                              children=max(2, min(3, row['policy']['children'])), label=self.kernel.SPLIT_LABEL,
                              **self.kernel.SPLIT_SEARCH)
        attempt['kernel'] = kernel
        if refusal:
            # recorded, never started: the next decision reads it (a planner refusal ends the splitting)
            attempt.update(status='failed', failure='REFUSAL', finished=self.clock(), error=refusal[:500])
            node['attempts'].append(attempt)
            if kind == 'planner':
                node['split_refused'] = True
            self._event(row, 'launch_refused', node=node['id'], attempt=attempt_id, reason=refusal[:300])
            return attempt
        kernel['pending'] = True
        node['attempts'].append(attempt)
        row['budget']['agents_started'] += 1
        node['engine'], node['node'] = engine, target
        if kind == 'planner':
            node['planners'] = node.get('planners', 0) + 1
        self._event(row, 'launch_intent', node=node['id'], attempt=attempt_id, request_id=attempt['request_id'], kind=kind,
                    strategy=attempt['strategy'], engine=engine, target=target, kernel=mode)
        return attempt

    def _kernel_program(self, node, kernel):
        """The attempt's program, deterministic for its record: the sheet compiled with --keep and the
        attempt's seed, or the split ask (with the stopped build's error as evidence)."""
        if kernel.get('mode') == 'split':
            error = ''
            if kernel.get('from_run'):
                error = str((self.kernel.status(kernel['from_run']).get('error') or {}).get('message') or '')
            return self.kernel.split_program(node['statement'], kernel['unit'], kernel['applicators'],
                                             seed=kernel.get('seed'), error=error, children=kernel.get('children', 3))
        search = {key: kernel.get(key) or value for key, value in self.kernel.SEARCH.items()}
        return self.kernel.compile(node['statement'], kernel['applicators'], keep_folder=kernel.get('keep_from') or None,
                                   seed=kernel.get('seed'), **search)

    def _dispatch_kernel(self, run_id, node_id, attempt_id, event):
        """Start a recorded kernel intent outside the lock: own checkout (builds), program, then the process.
        The checkout and the program hash are recorded before the process starts, the pid after it. A crash
        anywhere in between re-dispatches the same attempt: the checkout is adopted by its name, the same
        program is compiled again, and `run` adopts the pid the process wrote itself, so one attempt never
        starts two builds."""
        row = self._read(run_id)
        node, attempt = _find(row, node_id, attempt_id)
        if attempt is None or attempt['status'] not in OPEN:
            return
        kernel = attempt.get('kernel') or {}
        if kernel.get('pid') or not kernel.get('pending') or row.get('cancel_requested'):
            return                        # a cancel settles the intent through _cancel_kernel
        program, checkout, base, error = None, kernel.get('checkout'), kernel.get('base_sha256'), None
        try:
            program = self._kernel_program(node, kernel)
            if kernel.get('mode') == 'build' and not checkout:
                checkout = self.kernel.checkout(row['base']['cwd'], self._checkout_name(run_id, attempt_id))
                base = self.kernel.file_sha256(checkout['cwd'], kernel['file'])
        except Exception as exc:  # noqa: BLE001 - every refusal is recorded on the attempt
            error = exc
        digest = hashlib.sha256(program.encode('utf-8')).hexdigest() if program else ''
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if attempt is None or attempt['status'] not in OPEN or attempt['kernel'].get('pid') or row.get('cancel_requested'):
                return
            current = attempt['kernel']
            if checkout and not current.get('checkout'):
                current['checkout'], current['base_sha256'] = checkout, base
                attempt['workspace'] = checkout.get('cwd') or ''
            if error is None and current.get('program_sha256') and current['program_sha256'] != digest:
                error = AutogenError('the build program differs from the one recorded for this attempt')
            if error is not None:
                current['pending'] = False
                attempt.update(status='failed', failure='REFUSAL' if 'refus' in str(error).lower() else 'INFRASTRUCTURE',
                               finished=self.clock(), error=str(error)[:500])
                self._event(row, 'launch_failed', node=node_id, attempt=attempt_id, error=str(error)[:300])
                return
            current['program_sha256'] = digest
            run_dir, apps, limits = current['run_dir'], list(current['applicators']), dict(current.get('limits') or {})
        try:
            pid = self.kernel.run(program, run_dir, apps, limits)
        except Exception as exc:  # noqa: BLE001
            pid, error = None, exc
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if attempt is None or attempt['status'] not in OPEN or attempt['kernel'].get('pid'):
                return
            current = attempt['kernel']
            if error is not None or not pid:
                current['pending'] = False
                text = str(error or 'the build process did not start')
                attempt.update(status='failed', failure='REFUSAL' if 'refus' in text.lower() else 'INFRASTRUCTURE',
                               finished=self.clock(), error=text[:500])
                self._event(row, 'launch_failed', node=node_id, attempt=attempt_id, error=text[:300])
                return
            current.update(pid=pid, pending=False, spawned=self.clock())
            attempt['status'] = 'running'
            self._event(row, event, node=node_id, attempt=attempt_id, pid=pid, kernel=current['mode'])

    def _kernel_outcome(self, st):
        """(task-like status, error text) of an ended build: a model that answered and never passed a unit's
        examples is the statement's failure (completed, judged by its checks); anything else is the
        placement's (failed: INFRASTRUCTURE, or REFUSAL when it says so)."""
        error = st.get('error') or {}
        message = str(error.get('message') or '')
        if not st['done']:
            return 'failed', 'the kernel build ended without a final state'
        if st['status'] == 'done':
            return 'completed', ''
        if st['status'] == 'stopped':
            return 'cancelled', 'the kernel build was stopped'
        if error.get('kind') == 'check':
            return 'completed', message
        return 'failed', f'kernel {error.get("kind") or st["status"]}: {message}'

    def _observe_kernel(self, run_id, node_id, attempt_id, now):
        """One kernel attempt: start its recorded intent, or read its run folder. A running build only
        updates its accepted units; an ended one is judged by code: a build by the node's checks run in its
        own checkout once the assembled file is written there, a split by `split_sheet`."""
        row = self._read(run_id)
        node, attempt = _find(row, node_id, attempt_id)
        kernel = attempt['kernel']
        if not kernel.get('pid'):
            if kernel.get('pending'):
                self._dispatch(run_id, node_id, attempt_id, 'launch_recovered')
            return
        st = self.kernel.status(kernel['run_dir'], label=kernel.get('label'))
        if not st['done'] and self.kernel.alive(kernel['pid'], kernel['run_dir']):
            if kernel.get('mode') == 'build' and st['accepted'] != (kernel.get('accepted') or []):
                with self._mutate(run_id) as row:            # live units for the operator; no event
                    _, current = _find(row, node_id, attempt_id)
                    if current is not None and current['status'] in OPEN:
                        current['kernel'].update(accepted=st['accepted'], units_accepted=len(st['accepted']),
                                                 calls=st['calls'])
            return
        outcome, why = self._kernel_outcome(st)
        if not st['done']:
            tail = self.kernel.log_tail(kernel['run_dir'])
            why += (': ' + ' '.join(tail.split())[-300:]) if tail else ''
        mode, file = kernel.get('mode'), kernel.get('file') or ''
        lacking = self.kernel.absent_node(str((st.get('error') or {}).get('message') or '')) if outcome == 'failed' else ''
        lacking = lacking if lacking and lacking == attempt.get('node') else ''   # the node lacked the model
        stalled = self.kernel.stalled_unit(node['statement'], st['accepted']) if mode == 'build' else None
        verdict = None
        if mode == 'build' and outcome == 'completed':
            units = {'kind': 'units', 'passed': st['status'] == 'done', 'public': True,
                     'output': f'{len(st["accepted"])}/{kernel.get("units_total")} units accepted'
                               + (f'; the build stopped at {stalled["heading"]}: {why[:900]}' if stalled else '')}
            if st['status'] == 'done' and st['page'] is not None:
                checkout = kernel.get('checkout') or {}
                try:
                    written = self.kernel.install(checkout.get('cwd') or '', file, st['page'])
                    changed = written['sha256'] != kernel.get('base_sha256')
                    absent = kernel.get('base_sha256') is None
                    step = {'evidence': {'changes': {'added': [file] if changed and absent else [],
                                                     'modified': [file] if changed and not absent else [], 'removed': []},
                                         'inventory': {}}}
                    verdict, _ = self._verdict(row, node, attempt, {}, step, checkout.get('cwd') or '', False)
                    verdict['checks'].append(units)
                    verdict.update(passed=all(c['passed'] for c in verdict['checks']), report=_public_report(verdict['checks']))
                except (OSError, ValueError) as exc:
                    outcome, why, verdict = 'failed', f'the built file could not be checked in its checkout: {exc}', None
            else:
                checks = [{'kind': 'exists', 'file': file, 'passed': False, 'public': True,
                           'output': f'{file} was not assembled: a unit never passed its examples'}, units]
                verdict = {'passed': False, 'checks': checks, 'files_changed': 0, 'report': _public_report(checks)}
        elif mode == 'split' and outcome == 'completed':
            reply = st['outputs'].get(kernel.get('label') or self.kernel.SPLIT_LABEL)
            refined, errors = (None, [why or 'no answer passed the split format']) if st['status'] != 'done' or not reply \
                else self.kernel.split_sheet(node['statement'], kernel['unit'], reply, children=kernel.get('children', 3))
            if refined:
                verdict = {'passed': True, 'files_changed': None, 'report': '', 'lines': [refined],
                           'checks': [{'kind': 'split', 'passed': True, 'public': True,
                                       'output': f'{kernel.get("heading")} split; the refined sheet compiles'}]}
            else:
                text = '; '.join(errors)
                verdict = {'passed': False, 'files_changed': None, 'report': 'split refused: ' + text[:300],
                           'checks': [{'kind': 'split', 'passed': False, 'public': True, 'output': text[:1500]}]}
        if mode == 'build' and verdict is not None:
            verdict['units_accepted'] = len(st['accepted'])
        failure = POLICY.classify({'status': outcome, 'error': why}, verdict,
                                  timeout_requested=bool(attempt.get('timeout_requested')))
        metrics = POLICY.progress_metrics(verdict, None, named=[file], units=len(st['accepted'])) if mode == 'build' else None
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if attempt is None or attempt['status'] not in OPEN:
                return
            for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed'):
                attempt.pop(key, None)            # the build ended: a pending cancel has nothing to stop
            attempt['finished'] = now
            current = attempt['kernel']
            current.update(status=st['status'], accepted=st['accepted'], units_accepted=len(st['accepted']),
                           calls=st['calls'], error=why[:500])
            if mode == 'build':
                current['stalled'] = stalled['name'] if stalled else ''
            lines = verdict.pop('lines', None) if verdict else None
            attempt['verdict'] = verdict
            if failure is None:
                if attempt['kind'] == 'planner':
                    attempt['split'] = lines
                attempt['status'] = 'accepted'
                self._event(row, 'attempt_accepted', node=node_id, attempt=attempt_id, checks=len(verdict['checks']))
            else:
                attempt.update(status='failed', failure=failure, error=(why or (verdict or {}).get('report') or '')[:500])
                if lacking:
                    self._model_absent(row, node, attempt, lacking)
                elif attempt['kind'] == 'planner':
                    node['split_refused'] = True
                self._event(row, 'attempt_failed', node=node_id, attempt=attempt_id, failure=failure)
            if attempt['kind'] in ('candidate', 'regen') and metrics is not None and not lacking:
                self._progress(node, attempt, metrics, failure)

    def _model_absent(self, row, node, attempt, where):
        """Under the run lock: the attempt's node proved to lack the model. The attempt is a placement that never
        ran (`placement_absent`: the policy counts it neither as a try nor as a planner), the node leaves this
        run's rotation, and a statement placed there moves back to the operator's node (or the first that may hold
        the model)."""
        attempt['placement_absent'] = True
        row['model_absent'] = sorted(set(row.get('model_absent') or []) | {where})
        row['policy']['nodes'] = [n for n in row['policy'].get('nodes') or [] if n != where]
        if node.get('node') == where:
            options = [n for n in [row['base']['node']] + row['policy']['nodes'] if n not in row['model_absent']]
            node['node'] = options[0] if options else row['base']['node']
        self._event(row, 'model_absent', node=node['id'], attempt=attempt['id'], where=where,
                    model=row['base'].get('model') or '')

    def _cancel_kernel(self, run_id, node_id, attempt_id, reason, message=''):
        """`_cancel_attempt` for a kernel attempt: a locked intent, the process group stopped outside the
        lock (SIGTERM releases its admitted model calls; SIGKILL after a grace; a pid file the record never
        saw is honoured), then the record. A timed-out build keeps the units it accepted as progress: the
        next build keeps them. A stop that fails keeps the attempt in its slot and is retried each pass."""
        with self._mutate(run_id) as row:
            _, attempt = _find(row, node_id, attempt_id)
            if attempt is None:
                return True
            if attempt['status'] not in OPEN and attempt['status'] != 'unknown':
                for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed'):
                    attempt.pop(key, None)
                return True
            if reason != 'interrupted':
                attempt['cancel_pending'] = True
                attempt['cancel_reason'] = reason
                if message:
                    attempt['cancel_message'] = message
                if reason == 'timeout':
                    attempt['timeout_requested'] = True
            kernel = dict(attempt['kernel'])
        stopped = self.kernel.stop(kernel.get('pid'), kernel['run_dir'])
        st = self.kernel.status(kernel['run_dir'], label=kernel.get('label')) if stopped else None
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if attempt is None or (attempt['status'] not in OPEN and attempt['status'] != 'unknown'):
                return True
            if not stopped:
                error = 'the kernel build did not stop'
                if attempt.get('cancel_failed') != error:
                    attempt['cancel_failed'] = error
                    self._event(row, 'cancel_failed', node=node_id, attempt=attempt_id, error=error)
                if reason == 'interrupted':
                    attempt.update(cancel_pending=True, cancel_reason='operator')
                return False
            if reason == 'interrupted' and not attempt['kernel'].get('pid'):
                return True                       # never started: the intent stays for Resume
            if reason == 'timeout' and st['done']:
                for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed'):
                    attempt.pop(key, None)        # it ended on its own first: the next observation judges it
                return True
            for key in ('cancel_pending', 'cancel_reason', 'cancel_message', 'cancel_failed'):
                attempt.pop(key, None)
            current = attempt['kernel']
            current.update(pending=False, status=st['status'], accepted=st['accepted'],
                           units_accepted=len(st['accepted']), calls=st['calls'])
            text = message or {'timeout': 'attempt exceeded the policy attempt_seconds allowance',
                               'superseded': 'another candidate was accepted first',
                               'interrupted': 'the coordinator was interrupted; the build was stopped so it does not run unsupervised',
                               }.get(reason, 'the run was cancelled')
            attempt.update(status='failed', failure='TIMEOUT' if reason == 'timeout' else 'CANCELLED',
                           finished=self.clock(), error=text)
            if reason == 'timeout':
                if attempt['kind'] in ('candidate', 'regen') and current.get('mode') == 'build':
                    self._progress(node, attempt, POLICY.progress_metrics(None, None, named=[current.get('file') or ''],
                                                                          units=len(st['accepted'])), 'TIMEOUT')
                self._event(row, 'attempt_timeout', node=node_id, attempt=attempt_id)
        return True

    def _promote_kernel(self, run_id, attempt_id, checkout):
        """Bring an accepted build home (the intent is already recorded by `_promote`): commit -> apply on
        the attempt's checkout (kernel_lane.promote: git_checkouts.commit_all + apply_to_project, the per-file
        3-way apply into the project's working copy). Returns (error, conflict, applied)."""
        if not checkout.get('worktree'):
            return 'the accepted kernel attempt has no checkout', False, None
        try:
            applied = self.kernel.promote(checkout, f'autogen: kernel build {attempt_id} of {run_id}')
        except Exception as exc:  # noqa: BLE001 - a refusal is recorded; a clash is CONFLICT
            return f'apply refused: {str(exc)[:300]}', bool(re.search(r'clash|conflict', str(exc), re.I)), None
        if isinstance(applied, dict) and applied.get('conflicts'):
            return 'apply conflicts: ' + ', '.join(str(c) for c in applied['conflicts'][:5]), True, applied
        return '', False, applied

    # ------------------------------------------------------------------ acceptance and promotion
    def _accept(self, run_id, node_id, attempt_id):
        row = self._read(run_id)
        node, attempt = _find(row, node_id, attempt_id) if attempt_id else (_find(row, node_id)[0], None)
        if node.get('perpetual') and attempt is None:
            with self._mutate(run_id) as row:
                node, _ = _find(row, node_id)
                if node['status'] == 'pending':
                    node['status'] = 'accepted'
                    node['winner'] = 'generations'
                    self._event(row, 'node_accepted', node=node_id, winner='generations')
            return
        if attempt is None:
            return
        if attempt['kind'] == 'planner':
            with self._mutate(run_id) as row:
                node, _ = _find(row, node_id)
                for other in node['attempts']:
                    if other['id'] != attempt_id and other['status'] == 'accepted':
                        other.update(status='superseded', error='the statement was split before this attempt was promoted')
            for other in _find(self._read(run_id), node_id)[0]['attempts']:
                if other['id'] != attempt_id and other['status'] in OPEN:
                    self._cancel_attempt(run_id, node_id, other['id'], 'superseded')
            if attempt.get('from') and not self._promote_partial(run_id, node_id, attempt['from']):
                return
            self._split(run_id, node_id, attempt_id)
            return

        def won(row, node, attempt):
            node['status'] = 'accepted'
            node['winner'] = attempt['id']
            self._event(row, 'node_accepted', node=node['id'], winner=attempt['id'])
            for other in node['attempts']:
                if other is not attempt and other['status'] == 'accepted':
                    # a second passing candidate is not left 'accepted' beside the winner
                    other.update(status='superseded', error='another accepted candidate was promoted first')
        if not self._promote(run_id, node_id, attempt_id, won):
            return
        for other in _find(self._read(run_id), node_id)[0]['attempts']:
            if other['status'] in OPEN:
                self._cancel_attempt(run_id, node_id, other['id'], 'superseded')

    def _promote_partial(self, run_id, node_id, attempt_id):
        """A split of the remaining work: the children start from the files the handoff chain
        produced, so the last handoff's checkout is applied to the project folder first (its
        checks failed, which is why the work was split; the parent verdict still runs after the
        children). A refused apply ends the node: the children would otherwise redo done work."""
        _, previous = _find(self._read(run_id), node_id, attempt_id)
        if previous is None or previous.get('partial_promoted'):
            return previous is not None

        def done(row, node, attempt):
            attempt['partial_promoted'] = True
            self._event(row, 'partial_promoted', node=node_id, attempt=attempt_id)
        if (previous.get('checkout_agent') or previous.get('agent_id')) and self._promote(run_id, node_id, attempt_id, done):
            return True
        with self._mutate(run_id) as row:
            node, previous = _find(row, node_id, attempt_id)
            until = bool(row['policy'].get('until_done'))
            node['status'] = 'stuck' if until else 'failed'
            why = str(previous.get('error') or '') if (previous.get('checkout_agent') or previous.get('agent_id')) \
                else 'the handoff attempt has no agent identity'
            node['error'] = f'the partial work of {attempt_id} could not be brought into the project folder: ' + why[:300]
            row.update(status=node['status'], error=f'Statement {node_id} is {node["status"]}: {node["error"]}')
            self._event(row, 'node_stuck' if until else 'node_failed', node=node_id, reason=node['error'][:300])
        return False

    def _promote_generation(self, run_id, node_id, attempt_id):
        def done(row, node, attempt):
            attempt['status'] = 'generation_done'
            checkpoint = attempt.pop('pending_checkpoint', None)
            if checkpoint:
                attempt['checkpoint'] = checkpoint       # only a promoted generation sets the cursor
            node['generation'] = attempt.get('generation', node.get('generation', 0))
            # a promoted generation is progress: the lane's tried-strategy memory starts over
            if node.get('fingerprints'):
                node['fingerprints_archive'] = ((node.get('fingerprints_archive') or []) + node['fingerprints'])[-512:]
            node['fingerprints'], node['last_fingerprint'] = [], ''
            self._index_items(row, node, attempt, checkpoint)   # only promoted items enter the index
            self._event(row, 'generation_done', node=node_id, attempt=attempt_id, generation=node['generation'])
        self._promote(run_id, node_id, attempt_id, done)

    def _promote(self, run_id, node_id, attempt_id, on_success):
        """Bring the winner home through the runner's promote (commit -> 3-way apply against the base
        the candidate started from). A durable intent precedes the apply: a crash in between makes
        the run unknown (inspect) instead of a regeneration on top of half-applied files. A
        conflict with concurrent edits is CONFLICT (the base moved), not an engine failure."""
        with self._mutate(run_id) as row:
            _, attempt = _find(row, node_id, attempt_id)
            attempt['promotion'] = {'state': 'intent', 'at': self.clock()}
            agent_id = attempt.get('checkout_agent') or attempt.get('agent_id')
            checkout = dict((attempt.get('kernel') or {}).get('checkout') or {}) if attempt.get('kernel') else None
        error, conflict, applied = '', False, None
        if checkout is not None:
            error, conflict, applied = self._promote_kernel(run_id, attempt_id, checkout)
        elif not agent_id:
            error = 'the accepted attempt has no agent identity'
        else:
            try:
                applied = self.task_runner.promote(agent_id, f'autogen: attempt {attempt_id} of {run_id}')
            except Exception as exc:
                error = f'apply refused: {str(exc)[:300]}'
                # a 3-way apply refuses on a clash ("Nothing was applied: N file(s) clash with your
                # checkout", "The merge had conflicts"): the base moved, not an engine failure
                conflict = bool(re.search(r'clash|conflict', str(exc), re.I))
            if not error and isinstance(applied, dict) and applied.get('conflicts'):
                error = 'apply conflicts: ' + ', '.join(str(c) for c in applied['conflicts'][:5])
                conflict = True
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if error:
                attempt.update(status='failed', failure='CONFLICT' if conflict else 'INFRASTRUCTURE', error=error[:500],
                               promotion={'state': 'failed', 'at': self.clock(), 'error': error[:300]})
                self._event(row, 'promotion_failed', node=node_id, attempt=attempt_id, error=error[:300])
                return False
            attempt['applied'] = applied if isinstance(applied, dict) else {'message': str(applied)}
            attempt['promotion'] = {'state': 'done', 'at': self.clock()}
            self._event(row, 'promoted', node=node_id, attempt=attempt_id,
                        files=len((applied or {}).get('files') or []) if isinstance(applied, dict) else None)
            on_success(row, node, attempt)
        return True

    def _split(self, run_id, node_id, attempt_id):
        with self._mutate(run_id) as row:
            node, attempt = _find(row, node_id, attempt_id)
            if node['status'] != 'pending':
                return
            policy = row['policy']
            children = []
            # a parent split for the second time (reopened after its assembled result failed) keeps
            # its earlier children as history; the new ones never reuse their ids
            offset = sum(1 for n in row['nodes'] if n.get('parent') == node['id'])
            for i, line in enumerate(attempt.get('split') or []):
                child = self._node(offset + i, line, node['depth'] + 1, node['id'], policy, sheet=bool(node.get('sheet')))
                child['engine'], child['node'] = node.get('engine'), node.get('node')
                # the parent's best evidence at the split: a child that never beats it is not split again
                child['parent_progress'] = dict(node.get('progress') or {})
                if node.get('sheet'):
                    # the refined sheet keeps the units the parent's best build accepted (all before the split unit)
                    child['keep_from'] = (attempt.get('kernel') or {}).get('from_run') or ''
                row['nodes'].append(child)
                children.append(child['id'])
            node['children'] = children
            node['status'] = 'split'
            node['winner'] = attempt_id
            self._event(row, 'node_split', node=node_id, children=children)

    def _finish(self, run_id):
        """Every statement is accepted: run the operator's final commands and hidden checks against
        the project folder. Hidden checks are a run-level gate; their output never enters the record."""
        row = self._read(run_id)
        if any(a['status'] in OPEN or a.get('cancel_pending') for n in row['nodes'] for a in n['attempts']):
            return True                   # a superseded rival is still being stopped
        policy, cwd = row['policy'], row['base']['cwd']
        checks = []
        for command in policy.get('final', []):
            out = self.check_runner(command, cwd, shell=True)
            checks.append({'kind': 'final', 'command': command, 'passed': out['rc'] == 0, 'output': out['out'][-1500:]})
        hidden = []
        for i, command in enumerate(policy.get('hidden', [])):
            out = self.check_runner(command, cwd, shell=True)
            hidden.append({'kind': 'hidden', 'index': i, 'passed': out['rc'] == 0, 'rc': out['rc'], 'public': False})
        with self._mutate(run_id) as row:
            if row['status'] != 'active' or row['cancel_requested']:
                return row['status'] in ('queued', 'active')
            row['final'] = {'checks': checks, 'passed': all(c['passed'] for c in checks)}
            if policy.get('hidden'):
                row['final']['hidden'] = hidden
            hidden_ok = all(c['passed'] for c in hidden)
            if row['final']['passed'] and hidden_ok:
                row.update(status='completed')
                self._event(row, 'completed', final_checks=len(checks))
            elif not row['final']['passed']:
                row['final']['passed'] = False
                row.update(status='failed', error='Every statement was accepted, but a final check failed: ' +
                           '; '.join(c['command'] for c in checks if not c['passed'])[:300])
                self._event(row, 'final_failed')
            else:
                row['final']['passed'] = False
                failed = [str(c['index'] + 1) for c in hidden if not c['passed']]
                row.update(status='failed', error='Every statement was accepted, but hidden acceptance check '
                           + ', '.join(failed) + f' of {len(hidden)} failed (HIDDEN_FAILURE).')
                self._event(row, 'final_failed', failure='HIDDEN_FAILURE')
        return False
