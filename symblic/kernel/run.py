#!/usr/bin/env python3
"""The Symblic interpreter: runs a program statement by statement and records everything it did.

    python3 -m symblic.kernel.run --dir FOLDER [--resume]     # FOLDER holds program.sym and meta.json
    Run(source, inputs, applicators, options, folder=None).execute()   # from Python

The interpreter walks the program. Formal statements go to the kernel (symblic.kernel.language.Kernel). An `ask`
becomes one or more CALLS: the statement's capsule (symblic.kernel.language.capsule: only the context its
policy allows, packed by weight) goes to each applicator chosen for it, every reply is read against the
statement's type (a reply that does not fit gets a repair attempt with the kernel's complaint), the valid
answers are put to consensus on their canonical fingerprints, and the winner is bound. At effort=ultra the
applicators then see the anonymised candidates and answer again (a mixture-of-agents round) before the final
vote. An `ensure ... else retry` that fails re-runs the statements from the ask it checks, with the failure as
feedback.

Everything a run does is recorded in its folder (when it has one): trace.jsonl (a row per statement),
calls.jsonl (every model call, keyed by a hash of exactly what was sent, so a resumed or replayed run re-uses
answers instead of asking again), state.json (bindings, outputs, fingerprint, status), kernel.json (the
semantic kernel the folder's work belongs to: work another kernel recorded is never continued, see
kernel_gate) and artifacts/ (drawings). Nothing runs on import; tests drive Run with fake applicators.

Every report also carries determinism receipts (report keys determinacy, code_behavior, model_identity,
escalation, determinism_summary): which asks the kernel determined, how the passing Code candidates behaved on
their declared tests, which observed manifest digests the calls reported (calls.jsonl keeps each reply's
model_identity and usage; the option `model_pins: "strict"` accepts an answer only with an observed,
freshly validated digest equal to the folder's pin), and which escalation rung answered. They describe the run
and never change what it asks, accepts or binds, except under strict pins.

Depends on: symblic.kernel.language (the kernel), symblic.kernel.diagnose, symblic.kernel.evidence,
symblic.kernel.epistemic; symblic.lang.abstraction, symblic.kernel.effects, symblic.constructor.* and
symblic.delegate.* when a program uses their statements; symblic.providers.applicators only in run_folder()
when no applicators are passed in.
Used by: every front end (the command-line tools in tools/, the English and spec-sheet compilers, the
benchmarks) and by the tests.
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import argparse
from contextlib import contextmanager, nullcontext
import copy
import fcntl
import hashlib
import json
import math
from fractions import Fraction
import os
import re
import stat
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import diagnose as D  # noqa: E402
from symblic.kernel import evidence as E  # noqa: E402
from symblic.kernel import epistemic as EP  # noqa: E402

DEFAULT_BUDGET = 12_000
DEFAULT_MAX_ASKS = 400
DEFAULT_MAX_CALLS = 2_000
DEFAULT_PARALLEL = 4
MOA_CANDIDATES = 6
KERNEL_RECORD = 'kernel.json'       # which semantic kernel a run folder's work belongs to (kernel_gate)
KERNEL_RECORD_VERSION = 1
SYNC = True                         # kernel.json is fsynced (file and folder); tests may turn it off (see _durable)
EFFECT_LEDGERS = (('effects.jsonl', 'id'), ('delegate-effects.jsonl', 'key'))   # (file, the field naming an action)


FINITE_FALLBACK_VERSION = 1
FINITE_FALLBACK_MAX_CHOICES = 16
# A small transparent expression fragment, shared in behavior with the steps
# compiler. No eval, query, external adapter, observation or effect executor.
_FINITE_NODES = frozenset({'num', 'lit', 'str', 'name', 'list', 'set', 'record', 'range',
                         'un', 'bin', 'cmp', 'cond', 'quant', 'comp', 'attr', 'index', 'call'})
_FINITE_BUILTINS = frozenset({'abs', 'ceil', 'floor', 'round', 'min', 'max', 'sum', 'product',
    'len', 'length', 'count', 'first', 'last', 'list', 'set', 'keys', 'zip', 'sort',
    'reverse', 'unique', 'contains', 'starts_with', 'ends_with', 'lower', 'upper',
    'trim', 'split', 'join', 'replace', 'text', 'number', 'words'})


def finite_fallback_choices(ask):
    """Decode only a source-authored literal menu; no expression execution."""
    node = ask.options.get('fallback_choices')
    if (not isinstance(node, S.Node) or node.k != 'list'
            or not 1 <= len(node.items) <= FINITE_FALLBACK_MAX_CHOICES
            or any(n.k != 'str' or any(type(part) is not str for part in n.parts) for n in node.items)):
        raise S.SymblicError('Finite fallback: fallback_choices must be a literal list of 1 to 16 exact strings',
                             ask.line, ask.col, 'type')
    values = tuple(''.join(n.parts) for n in node.items)
    if len(set(values)) != len(values) or any(len(v.encode('utf-8')) > 4096 for v in values):
        raise S.SymblicError('Finite fallback: choices must be distinct exact strings of at most 4096 UTF-8 bytes',
                             ask.line, ask.col, 'type')
    return values


def finite_fallback_receipt(ask, ensure, selected_index, *, source_sha256, kernel_id):
    """Pure identity used by the native writer and read-only recovery. A receipt
    describes deterministic selection, not authenticity or predicate adequacy.
    """
    values = finite_fallback_choices(ask)
    if type(selected_index) is not int or not 1 <= selected_index <= len(values):
        raise S.SymblicError('Finite fallback: selected index is outside its source menu', kind='type')
    return {'version': FINITE_FALLBACK_VERSION, 'method': 'authored_choices',
            'selection': 'first_passing_in_declared_order', 'trigger': 'ensure_retries_exhausted',
            'choices_sha256': E.digest([S.canon(v) for v in values]),
            'predicate_sha256': E.digest(E.syntax(ensure.cond)),
            'selected_index': selected_index, 'evaluated_count': selected_index,
            'selected_value_hash': S.fingerprint(values[selected_index - 1]),
            'source_sha256': source_sha256, 'kernel_id': kernel_id,
            'model_calls': 0, 'uniqueness': 'not_established'}


def validate_constructor_options(options):
    """Exact host policy, without importing or reading an optional constructor."""
    mode = options.get('constructor', 'off')
    if type(mode) is not str or mode not in ('off', 'linear_diagnose', 'linear'):
        raise S.SymblicError('constructor must be off, linear_diagnose or linear', kind='type')
    if any(type(key) is str and key.startswith('constructor_') and key != 'constructor_limits' for key in options):
        raise S.SymblicError('unknown constructor host option; runtime paths are not client options', kind='type')
    limits = options.get('constructor_limits', {'attempts': 16, 'milliseconds': 80000,
                                              'attempt_ms': 5000, 'resource_limit': 100000})
    bounds = {'attempts': 64, 'milliseconds': 320000, 'attempt_ms': 5000, 'resource_limit': 1000000}
    if type(limits) is not dict or set(limits) != set(bounds) or any(
            type(limits[k]) is not int or not 1 <= limits[k] <= bound for k, bound in bounds.items()) \
            or limits['milliseconds'] < limits['attempt_ms']:
        raise S.SymblicError('constructor_limits must contain bounded exact attempt/time/work counts', kind='type')
    if mode != 'off' and (options.get('determine') is not False or _solve_mode(options.get('solve')) != 'off'):
        raise S.SymblicError('enabled construction requires host determine=false and solve off', kind='type')
    return {'mode': mode, 'limits': dict(limits)}


_CONSTRUCTOR_HISTORY_BYTES = 16 * 1024 * 1024
_CONSTRUCTOR_TRACE_ROW_BYTES = 4 * 1024 * 1024


def _constructor_history_bytes(path):
    """Read one bounded regular history file without following a symlink or blocking on a FIFO."""
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(before.st_mode) or before.st_size > _CONSTRUCTOR_HISTORY_BYTES:
        raise ValueError('constructor recovery history is not a bounded regular file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    primary = None
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('constructor recovery history changed while opening')
        chunks, count = [], 0
        while count <= _CONSTRUCTOR_HISTORY_BYTES:
            part = os.read(fd, min(65536, _CONSTRUCTOR_HISTORY_BYTES + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
        if count > _CONSTRUCTOR_HISTORY_BYTES:
            raise ValueError('constructor recovery history exceeds its byte bound')
        return b''.join(chunks)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            os.close(fd)
        except BaseException as exc:
            if primary is None:
                raise
            try:
                primary.add_note('Closing recovery history also failed: ' + type(exc).__name__)
            except BaseException:
                pass


def _constructor_history_json(raw):
    # Bound depth and container allocation before json.loads. Strings remain byte-bounded by the reader.
    quoted = escaped = False
    depth = punctuation = 0
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1; punctuation += 1
        elif byte in (93, 125):
            depth -= 1
        elif byte in (44, 58):
            punctuation += 1
        if depth > 128 or punctuation > 262144:
            raise ValueError('constructor recovery history exceeds structural bounds')

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('duplicate recovery history JSON key')
            out[key] = value
        return out

    def invalid(_value):
        raise ValueError('nonfinite recovery history JSON number')

    def real(value):
        result = float(value)
        return invalid(value) if abs(result) == float('inf') else result

    row = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid, parse_float=real)
    if type(row) is not dict:
        raise ValueError('constructor recovery history row must be an object')
    return row


def _constructor_history_evidence(row, *, state=False):
    """Recognize host-owned structural fields, never source text or an arbitrary user value."""
    def receipt(value):
        if type(value) is dict and 'attempt' in value:
            if type(value['attempt']) is not int or value['attempt'] < 1:
                raise ValueError('malformed constructor attempt breadcrumb')
            return True
        return False

    def claim(value):
        return type(value) is dict and value.get('origin') == 'solver_proposal'

    def item(value):
        if type(value) is not dict:
            return False
        if value.get('answered_by') == 'constructor' or receipt(value.get('constructor')):
            return True
        ep = value.get('epistemic')
        if type(ep) is dict and claim(ep.get('claim')):
            return True
        return False

    if item(row) or item(row.get('ask')):
        return 'work'
    if not state:
        return None
    # This host field is synced before the first possible intent and retained
    # in every later snapshot. Even damaged content establishes ambiguity.
    if 'constructor_activity' in row:
        return 'ambiguous'
    ep = row.get('epistemic')
    if type(ep) is dict and type(ep.get('claims')) is list and any(claim(c) for c in ep['claims']):
        return 'work'
    determinacy = row.get('determinacy')
    if type(determinacy) is dict and type(determinacy.get('asks')) is list \
            and any(item(ask) for ask in determinacy['asks']):
        return 'work'
    for binding in row.get('bindings', []) if type(row.get('bindings')) is list else []:
        if type(binding) is dict and item(binding.get('meta')):
            return 'work'
    summary = row.get('determinism_summary')
    if type(summary) is dict and 'answered_by_constructor' in summary:
        count = summary['answered_by_constructor']
        if type(count) is not int or count < 0:
            raise ValueError('malformed constructor count breadcrumb')
        if count:
            return 'work'
        if row.get('status') != 'done':
            return 'ambiguous'  # Zero answers does not establish that an interrupted enabled run spent nothing.
    return None


def constructor_records_gate(folder, *, mode='off'):
    """Before Store/CLI writes: missing records are recovery work, never permission to redispatch.

    Returns whether both primary records exist. This detects retained evidence,
    not deletion of every artifact or a malicious host. Ordinary off-mode history
    retains its former tolerance of malformed unrelated state/trace records.
    """
    if not folder:
        return False
    present = [os.path.lexists(os.path.join(folder, name)) for name in
               ('constructor-config.json', 'constructor-events.jsonl')]
    if any(present):
        if mode == 'off':
            raise S.SymblicError('recorded constructor work cannot be resumed with construction disabled', kind='version')
        if not all(present):
            raise S.SymblicError('constructor configuration/journal presence differs; explicit recovery is required',
                                 kind='uncertain')
        return True
    leftovers = ['.constructor-events.lock'] + [f'constructor-events.torn-{slot}.bin' for slot in range(8)]
    if any(os.path.lexists(os.path.join(folder, name)) for name in leftovers):
        raise S.SymblicError('constructor journal byproducts remain without its records; explicit recovery is required',
                             kind='version' if mode == 'off' else 'uncertain')
    constructor_history_gate(folder, mode=mode)
    return False


def constructor_history_gate(folder, *, mode='off'):
    """Read retained host history before resume or lock export; never writes or follows user values.

    File-pair and journal-byproduct policy belongs to the caller. Export may
    ignore an unused configuration, but cannot discard evidence of an attempt.
    """
    problems = []
    for name in ('state.json', 'trace.jsonl'):
        try:
            raw = _constructor_history_bytes(os.path.join(folder, name))
            if raw is None or (not raw and name == 'trace.jsonl'):
                continue
            if name == 'state.json':
                lines = [raw]
            else:
                lines = raw.split(b'\n', 32768)
                if lines and lines[-1] == b'':
                    lines.pop()
                if len(lines) > 32768:
                    raise ValueError('constructor trace exceeds its row bound')
            for line in lines:
                try:
                    if name == 'trace.jsonl' and len(line) > _CONSTRUCTOR_TRACE_ROW_BYTES:
                        raise ValueError('constructor trace row exceeds its byte bound')
                    history = _constructor_history_json(line)
                    evidence = _constructor_history_evidence(history, state=name == 'state.json')
                    # Old running snapshots predate the durable activity marker.
                    # Without primary records, an enabled resume cannot prove that
                    # such an invocation stopped before reserving constructor work.
                    # Keep the existing ordinary off-mode tolerance.
                    # Only the exact supported integer asserts the checkpointing writer.
                    marker = history.get('constructor_bridge')
                    if name == 'state.json' and mode != 'off' and (type(marker) is not int or marker != 2) \
                            and history.get('status') != 'done':
                        evidence = 'ambiguous'
                except (ValueError, TypeError, RecursionError) as exc:
                    problems.append(type(exc).__name__)
                    continue
                if evidence in ('work', 'ambiguous'):
                    raise S.SymblicError('constructor records are missing but retained history requires explicit recovery',
                                         kind='version' if mode == 'off' else 'uncertain')
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            problems.append(type(exc).__name__)
    if problems and mode != 'off':
        raise S.SymblicError('constructor recovery history is unreadable or exceeds its bound; explicit recovery is required',
                             kind='uncertain')
    return False


class Stopped(Exception):
    pass


class RunFailed(Exception):
    def __init__(self, err: S.SymblicError):
        super().__init__(str(err))
        self.err = err


class _AssessmentExhausted(RuntimeError):
    """An optional scan stopped; distinct from an invalid answer or a real kernel-budget failure."""


class _AssessmentBudget(S.Budget):
    """Ask-local allowance charged against the real budget, with no refunds or global budget swaps.

    This bounds admitted kernel charges, not CPU time or allocations preceding an aggregate tick.
    A rejected charge latches exhaustion so another probe cannot repeat that unadmitted operation.
    Keep the object truthy even at zero: Kernel uses `budget or Budget()`.
    """
    def __init__(self, parent, check_stop):
        super().__init__(min(50_000, max(0, parent.left // 4)))
        self.limit = self.left
        self.parent = parent
        self.check_stop = check_stop
        self.exhausted = False

    def tick(self, n=1, node=None):
        self.check_stop()
        if self.parent.left < 0:
            self.parent.tick(0, node)  # A real exhausted budget must never become optional fallback.
        if self.exhausted or n > self.left:
            self.exhausted = True
            raise _AssessmentExhausted()
        self.parent.tick(n, node)
        self.left -= n

    def record(self):
        return {'limit': self.limit, 'charged': self.limit - self.left, 'exhausted': self.exhausted,
                'unit': 'admitted_kernel_steps'}


# ---------------------------------------------------------------------------
# Persistence (optional: a Run without a folder keeps everything in memory)
# ---------------------------------------------------------------------------

class Store:
    def __init__(self, folder: str | None):
        self.dir = folder
        self.lock = threading.Lock()
        self.save_lock = threading.Lock()   # snapshots (state.json, modules.json) are replaced by one thread at a time
        self.calls: dict = {}
        self.replay_calls: dict = {}
        self.attempt_count = 0
        self.repair_count = 0
        self.effect_rows: dict = {}
        self.trace_offset = 0
        self.legacy_effects = False
        self.trace_rows = 0
        self.trace_kernels: dict = {}       # (kernel id, lang) -> trace rows; (None, None) for a row naming none
        self.identity_rows: list = []       # (applicator, raw model_identity, cut) of earlier calls, in file order
        if folder:
            os.makedirs(os.path.join(folder, 'artifacts'), mode=0o700, exist_ok=True)
            for row in _read_jsonl(os.path.join(folder, 'calls.jsonl')):
                if _refused_row(row):
                    continue                    # refused before any model saw it: given back when it happened
                if 'model_identity_raw' in row:
                    self.identity_rows.append((row.get('app'), row['model_identity_raw'],
                                               row.get('model_identity_raw_truncated') is True))
                self.attempt_count += 1
                self.repair_count += bool(row.get('repair')) or (type(row.get('sample')) is int
                                                                and row['sample'] >= 1000)
                if row.get('key') and row.get('ok'):
                    self.calls[row['key']] = row
                if row.get('key') and isinstance(row.get('replies'), list):
                    self.replay_calls[row['key']] = list(row['replies'])
            trace = _read_jsonl(os.path.join(folder, 'trace.jsonl'))
            self.trace_offset = max([r['sequence'] for r in trace if type(r.get('sequence')) is int] or [0])
            self.legacy_effects = any(r.get('kind') == 'delegate' and r.get('status') == 'ok' for r in trace)
            work = _work_rows(trace)
            self.trace_rows, self.trace_kernels = len(work), _trace_kernels(work)

    def path(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def append(self, name: str, row: dict, durable=False) -> None:
        if not self.dir:
            return
        line = json.dumps(row, ensure_ascii=False, default=str)
        with self.lock:
            fd = os.open(self.path(name), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
                if durable:
                    f.flush()
                    os.fsync(f.fileno())

    @contextmanager
    def delegation_ledger(self):
        """One read/intent/outcome transaction, including across resumed processes."""
        if not self.dir:
            yield self.effect_rows
            return
        fd = os.open(self.path('.delegate-effects.lock'), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            rows = {}
            path = self.path('delegate-effects.jsonl')
            if os.path.exists(path):
                try:
                    with open(path, encoding='utf-8') as stream:
                        for line in stream:
                            row = json.loads(line)
                            if not isinstance(row, dict) or not row.get('key') or row.get('phase') not in ('intent', 'done', 'failed'):
                                raise ValueError('invalid ledger row')
                            rows[row['key']] = row
                except (OSError, ValueError) as exc:
                    raise S.SymblicError('delegate ledger is unreadable; reconcile before continuing',
                                         kind='uncertain') from exc
            self.effect_rows = rows
            yield rows
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def save(self, name: str, data, *, durable=False) -> None:
        """Replace `name` atomically. `ask ... for each` items save state from worker threads (every fifth trace row):
        one writer at a time, each with its own temporary file, so no save renames another's file away."""
        if not self.dir:
            return
        text = json.dumps(data, ensure_ascii=False, indent=1, default=str)
        tmp = self.path(f'.{name}.{os.getpid()}.{threading.get_ident()}.tmp')
        with self.save_lock:
            if durable:
                # Constructor activity must survive a process crash before an
                # intent, and every subsequent replacement must retain it.
                # Reuse the journal's reviewed cleanup/short-write behavior.
                from symblic.constructor import journal as journal
                primary = None
                def discard():
                    try:
                        os.unlink(tmp)
                    except FileNotFoundError:
                        pass
                try:
                    fd = journal._open_regular(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                    with journal._closing(fd):
                        journal._write_all(fd, text.encode('utf-8'))
                        os.fchmod(fd, 0o600)
                        os.fsync(fd)
                    os.replace(tmp, self.path(name))
                    journal._sync_folder(self.dir)
                except BaseException as exc:
                    primary = exc
                    raise
                finally:
                    journal._cleanup(discard, primary)
                return
            try:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(text)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path(name))
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def team_attempt(self, key, member, *, outcome=None):
        """Durable intent before a profiled call; unresolved calls never replay.

        The ordinary answer cache is checked first. A success can be reused only
        from its exact fsynced call record, never inferred from this small ledger.
        """
        if not self.dir:
            return
        with self.lock:
            fd = os.open(self.path('.team-calls.lock'), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                path = self.path('team-calls.json')
                try:
                    with open(path, encoding='utf-8') as stream:
                        ledger = json.load(stream)
                except FileNotFoundError:
                    if os.path.exists(self.path('team-calls.established.json')):
                        raise S.SymblicError('Team call records are missing after establishment; no call was replayed.', kind='uncertain') from None
                    ledger = {'version': 1, 'calls': {}}
                except (OSError, ValueError):
                    raise S.SymblicError('Team call records are unreadable; no call was replayed.', kind='uncertain') from None
                if (type(ledger) is not dict or ledger.get('version') != 1 or type(ledger.get('calls')) is not dict
                        or any(type(v) is not dict or v.get('phase') not in ('intent', 'done') for v in ledger['calls'].values())):
                    raise S.SymblicError('Team call records are invalid; no call was replayed.', kind='uncertain')
                prior = ledger['calls'].get(key)
                if outcome is None:
                    if prior:
                        raise S.SymblicError('This team call was already dispatched without a reusable accepted reply. Inspect the retained run; it will not be replayed.', kind='uncertain')
                    ledger['calls'][key] = {'phase': 'intent', 'member': member, 'at': time.time()}
                else:
                    if not prior or prior.get('phase') != 'intent' or prior.get('member') != member:
                        raise S.SymblicError('Team call intent identity changed; no outcome was adopted.', kind='uncertain')
                    prior.update(phase='done', ok=bool(outcome.get('ok')), error=str(outcome.get('error') or '')[:500])
                self.save('team-calls.established.json', {'version': 1}, durable=True)
                self.save('team-calls.json', ledger, durable=True)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def reserve_model_call(self, source, limit, repair_limit, repair=False):
        """Charge before dispatch, across resumes/processes. A crashed attempt
        still counts. This journal governs automatic routes, not replay reads.
        Old folders without it are conservatively charged for all call rows.
        """
        if not self.dir:
            return None
        with self.lock:
            fd = os.open(self.path('.model-budget.lock'), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                path = self.path('model-budget.json')
                try:
                    with open(path, encoding='utf-8') as stream:
                        ledger = json.load(stream)
                except FileNotFoundError:
                    try:
                        with open(self.path('calls.jsonl'), encoding='utf-8') as stream:
                            prior = [json.loads(line) for line in stream if line.strip()]
                        if any(not isinstance(r, dict) or not r.get('key')
                               or type(r.get('sample', 0)) is not int for r in prior):
                            raise ValueError('invalid prior call record')
                        prior = [r for r in prior if not _refused_row(r)]
                    except FileNotFoundError:
                        prior = []
                    except (OSError, ValueError) as exc:
                        raise S.SymblicError('prior model-call history is unreadable; cannot recover budget',
                                             kind='budget') from exc
                    ledger = {'version': 1, 'sources': {source: {
                        'calls': len(prior),
                        'repairs': sum(bool(r.get('repair')) or int(r.get('sample') or 0) >= 1000
                                       for r in prior)}}}
                except (OSError, ValueError) as exc:
                    raise S.SymblicError('model-call budget journal is unreadable', kind='budget') from exc
                if (not isinstance(ledger, dict) or type(ledger.get('version')) is not int or ledger['version'] != 1
                        or not isinstance(ledger.get('sources'), dict)
                        or any(not isinstance(k, str) or not isinstance(v, dict)
                               or any(type(v.get(n)) is not int or v[n] < 0 for n in ('calls', 'repairs'))
                               or v['repairs'] > v['calls']
                               for k, v in ledger['sources'].items())):
                    raise S.SymblicError('model-call budget journal is invalid', kind='budget')
                used = ledger['sources'].setdefault(source, {'calls': 0, 'repairs': 0})
                if used['calls'] >= limit:
                    raise S.SymblicError(f'the program exhausted its model-call budget ({limit}) across resumes',
                                         kind='budget')
                if repair and used['repairs'] >= repair_limit:
                    return {'refused_repair': True, **used}
                used['calls'] += 1
                used['repairs'] += int(repair)
                tmp = self.path(f'.model-budget.{os.getpid()}.{threading.get_ident()}.tmp')
                try:
                    out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(out, 'w', encoding='utf-8') as stream:
                        json.dump(ledger, stream, sort_keys=True)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(tmp, path)
                    directory = os.open(self.dir, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                except OSError as exc:
                    raise S.SymblicError('cannot reserve the model-call budget before dispatch', kind='budget') from exc
                return dict(used)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def release_model_call(self, source, repair=False):
        """Give back one reserve_model_call: launch() refused that call before any model saw the prompt.
        A missing, unreadable or unwritable journal keeps the charge (the conservative side)."""
        if not self.dir:
            return None
        with self.lock:
            fd = os.open(self.path('.model-budget.lock'), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                path = self.path('model-budget.json')
                try:
                    with open(path, encoding='utf-8') as stream:
                        ledger = json.load(stream)
                    used = ledger['sources'][source]
                    if type(used.get('calls')) is not int or type(used.get('repairs')) is not int \
                            or used['calls'] < 1:
                        return None
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    return None
                used['calls'] -= 1
                if repair and used['repairs'] > 0:
                    used['repairs'] -= 1
                used['repairs'] = min(used['repairs'], used['calls'])
                tmp = self.path(f'.model-budget.{os.getpid()}.{threading.get_ident()}.tmp')
                try:
                    out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(out, 'w', encoding='utf-8') as stream:
                        json.dump(ledger, stream, sort_keys=True)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(tmp, path)
                except OSError:
                    return None
                return dict(used)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def write_artifact(self, name: str, text: str) -> str:
        if not self.dir:
            return ''
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', name)[:80] or 'drawing.svg'
        if not safe.endswith('.svg'):
            safe += '.svg'
        p = os.path.join(self.dir, 'artifacts', safe)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
        return safe

    def log(self, text: str) -> None:
        if not self.dir:
            return
        with self.lock:
            fd = os.open(self.path('log.txt'), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as f:
                f.write(f'{time.strftime("%H:%M:%S")} {text}\n')


def _refused_row(row) -> bool:
    """A call row the launcher refused before any model saw the prompt (Run._call gave its budget back)."""
    return isinstance(row, dict) and not row.get('ok') and isinstance(row.get('reply'), dict) \
        and row['reply'].get('refused') is True


def _read_jsonl(path: str) -> list:
    out = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict):
                            out.append(row)
                    except ValueError:
                        pass
    except (OSError, UnicodeError):
        pass
    return out


# ---------------------------------------------------------------------------
# Which kernel a run folder's work belongs to
# ---------------------------------------------------------------------------

def _kernel_pair(kernel) -> tuple:
    """(id, lang) of a recorded kernel_id() dict; None for what it does not name."""
    if not isinstance(kernel, dict):
        return None, None
    kid, lang = kernel.get('id'), kernel.get('lang')
    return (kid if isinstance(kid, str) and kid else None), (lang if isinstance(lang, str) and lang else None)


def _trace_kernels(rows) -> dict:
    out: dict = {}
    for row in rows:
        pair = _kernel_pair(row.get('kernel'))
        out[pair] = out.get(pair, 0) + 1
    return out


# Trace rows that only report on the run (lane C determinism receipts), never work a resume could repeat: kernel_gate
# weighs work and statements without them, exactly as before they were written.
RECEIPT_ROW_KINDS = frozenset({'determinacy', 'model-drift', 'model-identity'})


def _work_rows(rows) -> list:
    return [row for row in rows if row.get('kind') not in RECEIPT_ROW_KINDS]


def _read_kernel_record(folder: str) -> tuple:
    """(kernel.json, problem): (None, '') when there is none. A record this code cannot read, damaged or in a newer
    format, is a problem: another kernel may have written it."""
    try:
        with open(os.path.join(folder, KERNEL_RECORD), encoding='utf-8') as stream:
            data = json.load(stream)
    except FileNotFoundError:
        return None, ''
    except (OSError, ValueError):
        return None, 'unreadable'
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != KERNEL_RECORD_VERSION \
            or None in _kernel_pair(data):
        return None, 'unreadable'
    return data, ''


def _ledger_entries(path: str, field: str) -> int:
    """Distinct actions in an effect ledger. One that holds anything unreadable counts at least once: something
    may have been done."""
    try:
        with open(path, 'rb') as stream:
            raw = stream.read()
    except OSError:
        return 0
    seen, unreadable = set(), False
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            unreadable = True
            continue
        if isinstance(row, dict) and isinstance(row.get(field), str):
            seen.add(row[field])
        else:
            unreadable = True
    return len(seen) or int(unreadable)


def kernel_gate(folder: str, *, store: Store | None = None, pins=None, replay: bool = False) -> dict:
    """May the program in `folder` run under this process's semantic kernel? Only reads.

    A resumed run reuses the folder's answered calls, keyed by the exact prompt, and its effect ledgers, keyed by
    the arguments. Both depend on the kernel (its system prompt, capsule layout and value texts), so continuing
    work another kernel recorded would ask those calls again and could repeat effects with different arguments
    under new ids. Such work is refused, and so is work whose kernel cannot be told. A folder where nothing ran
    yet may run.

    The identity comes from kernel.json (written before a run's first statement), from every trace row (each has
    carried kernel_id() since 2.1), from the last report in state.json when there is neither, and from the run's
    execution pins. A lock replay's identity is its lock's, checked by symblic.kernel.lockfile before the folder is made.
    Work is answered calls, trace rows, and effect ledger rows beside a state.json: every run since 2.0 writes
    state.json before its first statement, so a ledger without one was seeded or resolved by tools, and each of
    its actions is governed by the effects module's own receipts (contract, source pin, labels).
    Returns {decision: fresh|same|refused, reason: changed|unknown|None, current, recorded, answered_calls,
    effects, statements, write (kernel.json should be written), basis, message}.
    """
    if store is not None:
        answered, rows, kernels = len(store.calls), store.trace_rows, store.trace_kernels
    else:
        answered = len({r['key'] for r in _read_jsonl(os.path.join(folder, 'calls.jsonl'))
                        if isinstance(r.get('key'), str) and r['key'] and r.get('ok') and not _refused_row(r)})
        trace = _work_rows(_read_jsonl(os.path.join(folder, 'trace.jsonl')))
        rows, kernels = len(trace), _trace_kernels(trace)
    effects = sum(_ledger_entries(os.path.join(folder, name), field) for name, field in EFFECT_LEDGERS)
    acted = bool(effects) and os.path.exists(os.path.join(folder, 'state.json'))
    kid, lang = _kernel_pair(S.kernel_id())
    pin = pins.get('kernel_id') if isinstance(pins, dict) else None
    pin = pin if isinstance(pin, str) and pin else None
    record, problem = _read_kernel_record(folder)
    gate = {'decision': 'same', 'reason': None, 'current': {'id': kid, 'lang': lang}, 'recorded': [],
            'answered_calls': answered, 'effects': effects, 'statements': rows, 'write': False, 'basis': None,
            'message': ''}
    own = not replay and pin is None            # else the caller's pins or the lock hold the identity
    constructor_work = 0
    if os.path.lexists(os.path.join(folder, 'constructor-events.jsonl')):
        from symblic.constructor import journal as symblic_constructor_journal
        constructor_work = symblic_constructor_journal.work_count(folder)
        gate['constructor_attempts'] = constructor_work
    if not (answered or rows or acted or constructor_work):
        stale = bool(problem) or record is None or _kernel_pair(record) != (kid, lang)
        gate.update(decision='fresh', write=own and stale, basis='first_execution')
        return gate
    recorded = gate['recorded']
    if problem:
        recorded.append({'source': KERNEL_RECORD, 'id': None, 'lang': None, 'problem': problem})
    elif record is not None:
        recorded.append({'source': KERNEL_RECORD, 'id': record['id'], 'lang': record['lang']})
    for (row_id, row_lang), n in sorted(kernels.items(), key=lambda item: (item[0][0] or '', item[0][1] or '')):
        recorded.append({'source': 'trace.jsonl', 'id': row_id, 'lang': row_lang, 'rows': n})
    if not recorded:
        # Neither kernel.json nor a trace (a fresh restart dropped it): the report of the run's last end.
        state = _load(os.path.join(folder, 'state.json'), {})
        state_id, state_lang = _kernel_pair(state.get('kernel') if isinstance(state, dict) else None)
        if state_id is not None:
            recorded.append({'source': 'state.json', 'id': state_id, 'lang': state_lang})
    if pin is not None:
        recorded.append({'source': 'execution_pins', 'id': pin, 'lang': None})
    changed = [r for r in recorded if r['id'] != kid or r['lang'] not in (None, lang)]
    if changed:
        gate.update(decision='refused', reason='changed')
    elif not recorded and not replay:
        gate.update(decision='refused', reason='unknown')
    else:
        gate['basis'] = '+'.join(dict.fromkeys(r['source'] for r in recorded)) or 'replay'
        gate['write'] = own and record is None
    if gate['decision'] == 'refused':
        gate['message'] = _kernel_refusal(gate, changed, folder)
    return gate


def _count(n: int, noun: str) -> str:
    return f'{n} {noun}' + ('' if n == 1 else 's')


def _recorded_label(row: dict) -> str:
    if row.get('problem'):
        return f'a kernel this deployment cannot identify ({KERNEL_RECORD} is damaged or newer)'
    if row['id'] is None:
        return 'an earlier kernel that did not record its identity'
    return f'Symblic {row["lang"]} (kernel {row["id"]})' if row['lang'] else f'kernel {row["id"]} ({row["source"]})'


def _kernel_refusal(gate: dict, changed: list, folder: str) -> str:
    """The refusal, in words an owner or an agent can act on."""
    now = gate['current']
    here = f'Symblic {now["lang"]} (kernel {now["id"]})'
    calls, effects = gate['answered_calls'], gate['effects']
    if changed:
        head = (f"Resume refused: this run's work was recorded by "
                f'{"; ".join(dict.fromkeys(_recorded_label(r) for r in changed))}, and this deployment runs {here}.')
    else:
        meta = _load(os.path.join(folder, 'meta.json'), {})
        created = meta.get('version') if isinstance(meta, dict) and isinstance(meta.get('version'), str) else ''
        held = ' and '.join(text for text in (calls and _count(calls, 'answered model call'),
                                              effects and _count(effects, 'recorded effect')) if text)
        head = (f'Resume refused: this run holds {held} but no record of the kernel that made them'
                + (f' (it was created under Symblic {created})' if created else '') + f'; this deployment runs {here}.')
    risks = [f'ask up to {_count(calls, "answered model call")} again'] if calls else []
    if effects:
        risks.append(f'repeat {_count(effects, "recorded effect")} with different arguments')
    if not risks:
        risks.append(f'recompute its {_count(gate["statements"], "recorded statement")} under other semantics')
    # A new run does everything again: an agent that follows this option literally must know that it acts again.
    again = 'it asks everything again' + (' and performs its effects again' if effects else '')
    return (head + ' Prompts and effect arguments depend on the kernel, so continuing here could '
            + ' and '.join(risks) + ". Nothing was asked or performed; the run's status and records are "
            f'unchanged. Safe options: start a new run of this program here ({again}, as a new run), '
            'or continue this one on the deployment that recorded it (resume it there, or replay its lock once it '
            'has finished).')


def _durable() -> bool:
    """Whether kernel.json is fsynced. Its durability exists for the effect ledger's (a lost record beside fsynced
    ledger rows would leave the folder's work unidentified), so a test that turns the ledger's off
    (symblic.kernel.effects.SYNC, when that module is loaded) turns this one off too, as does SYNC here."""
    effects = sys.modules.get('symblic.kernel.effects')
    return SYNC and getattr(effects, 'SYNC', True) is not False


def _write_kernel_record(folder: str, basis: str) -> None:
    """kernel.json, durably (_durable): before a run's first statement, or (adopted from an older folder's evidence)
    before a fresh restart drops the trace that held it."""
    kernel = S.kernel_id()
    data = {'version': KERNEL_RECORD_VERSION, 'id': kernel['id'], 'lang': kernel.get('lang'), 'kernel': kernel,
            'basis': basis, 'recorded': round(time.time(), 3)}
    path = os.path.join(folder, KERNEL_RECORD)
    tmp = os.path.join(folder, f'.{KERNEL_RECORD}.{os.getpid()}.{threading.get_ident()}.tmp')
    durable = _durable()
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, sort_keys=True)
            if durable:
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(tmp, path)
        if durable:
            directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise S.SymblicError('the run folder cannot record which kernel runs it; nothing was run',
                             kind='version') from exc


def start_fresh(folder: str, *, pins=None, replay: bool = False) -> dict:
    """Ready `folder` for a fresh (not resumed) start: drop its trace and keep its answers and effect ledgers. The
    trace is also an older folder's record of its kernel, so it is weighed first: it stays on a refusal (which
    Run.execute then reports), and the identity it proves goes to kernel.json before it is dropped."""
    gate = kernel_gate(folder, pins=pins, replay=replay)
    keep = gate['decision'] == 'refused'
    if gate['decision'] == 'same' and gate['write']:
        try:
            _write_kernel_record(folder, gate['basis'])
        except S.SymblicError:
            keep = True                     # Run.execute meets the same failure and reports it
    if not keep:
        try:
            os.unlink(os.path.join(folder, 'trace.jsonl'))
        except OSError:
            pass
    return gate


CALL_KEY_VERSION = 2       # v2 adds the engine's effort and tools: a 'high' or web call never replays a 'low' one


def _plain_number(v):
    """An exact Symblic number as JSON-safe int or float (integers stay int)."""
    if isinstance(v, bool) or not S.is_num(v):
        return v
    f = Fraction(v)
    return int(f) if f.denominator == 1 else float(f)


def _has_measured_agreement(ask):
    if ask.get('route') in ('escalate', 'search'):
        return False
    if ask.get('items'):
        return all(_has_measured_agreement(item) for item in ask['items'])
    last_round = ask.get('rounds') or 1
    return sum(bool(s.get('ok')) for s in ask.get('samples', [])
               if (s.get('round') or 1) == last_round) >= 2


class _EitherStop:
    """Set when the run stops OR a search no longer needs a candidate: the applicators poll is_set() and wait(), so a
    candidate's in-flight model run is cancelled within a poll instead of finishing for nothing."""

    def __init__(self, *events):
        self.events = [e for e in events if e is not None]

    def is_set(self) -> bool:
        return any(e.is_set() for e in self.events)

    def wait(self, timeout=None) -> bool:
        end = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            left = None if end is None else end - time.monotonic()
            if left is not None and left <= 0:
                return False
            time.sleep(0.5 if left is None else min(0.5, left))
        return True


CODE_FEEDBACK_CHARS = 16_000      # a rejected Code answer shown back whole (the model repairs its own code)
SEARCH_MAX_SAMPLES = 25
SEARCH_MAX_ROUNDS = 20


def call_key(app: dict, system: str, prompt: str, schema, sample: int, temperature, seed, effort: str = '',
             tools: str = 'none', context_identity: str | None = None, ollama_limits=None) -> str:
    parts = [CALL_KEY_VERSION, S.app_label(app), system, prompt, schema, sample, _plain_number(temperature),
             _plain_number(seed), effort or '', tools or 'none']
    if context_identity is not None:
        parts.append({'capsule_context_sha256': context_identity})
    if ollama_limits:
        parts.append({'ollama_limits': ollama_limits})
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Determinism receipts (core repair lane C, D1-D5). The report keys are the contract in
# core-repair/D-REPORT-SCHEMA.md, version 1: every block is additive, and a reader treats a missing key as "not
# reported". They describe the run; none of them changes what it asks, accepts or binds (except model_pins=strict,
# a host opt-in that accepts an answer only with an observed, freshly validated manifest digest equal to the folder's
# pin). Digests are what the node's Ollama listed around the call: observations, never an attestation of loaded weights.
# ---------------------------------------------------------------------------

RECEIPTS_VERSION = 1
# The host's model_pins policies. 'observe' (the default): identities are checked, recorded and reported, and nothing
# is refused for them. 'strict': an answer is accepted only when its identity is observed, freshly validated, with a
# non-null digest equal to the folder's pin for that applicator (or the first such pin); every other answer is refused
# before it is accepted or cached, on the first call too.
MODEL_PIN_POLICIES = ('observe', 'strict')
# The model identity contract this runner implements: calls.jsonl model_identity_raw/usage/identity_check_at_call,
# fresh checks, folder pins, drift, the validated model_pins policy with strict enforcement, the report's policy and
# recheck_model_identities. A front end offers strict pins only when this is exactly the int 1; the capability
# string is derived from it, never set on its own.
MODEL_IDENTITY_VERSION = 1
MODEL_PINS_CAPABILITY = f'symblic.model_pins.strict.v{MODEL_IDENTITY_VERSION}'
LIST_MAX = {'asks': 500, 'passing': 20, 'checks': 20, 'groups': 20, 'members': 50, 'applicators': 50,
            'digests': 20, 'drift': 50, 'by_rung': 50}
IDENTITY_RAW_CHARS = 8_192           # a model_identity record's JSON text kept in calls.jsonl (the helper's is ~1 KB)
USAGE_CHARS = 4_096
IDENTITY_CHECKER = 'symblic.providers.ollama_call.check'
IDENTITY_STATUSES = ('observed', 'drift', 'unavailable', 'invalid', 'unverifiable')
_PINNED_DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
_DOMAIN_KINDS = {'bool': 'bool', 'enum': 'enum', 'int': 'int_range', 'record': 'record', 'set': 'set', 'list': 'list'}


def _solve_mode(value) -> str:
    """How an ask's `solve` option reads: off, on or auto. Its behaviour is the option's truth, as since 2.3 (a
    determined ask is answered by the kernel, anything else goes to the models); `solve=auto` names that mode and
    any other true value reads `on`."""
    if isinstance(value, str) and value.strip().lower() == 'auto':
        return 'auto'
    return 'on' if value else 'off'


def _canonical_text(value) -> str:
    """A finite-domain value in the kernel's own text (show), text quoted as JSON so "3" and 3 stay apart."""
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else S.show(value)


def _brief(value, limit: int = 60) -> str:
    """A bounded description of a host value for an error message (never fails)."""
    try:
        text = repr(value[:limit + 1] if isinstance(value, (str, bytes)) else value)
    except Exception:  # noqa: BLE001  (a value whose repr fails is described by its type)
        return f'a {type(value).__name__}'
    return text if len(text) <= limit else text[:limit - 1] + '…'


def validate_ollama_limits(value) -> dict:
    """Explicit per-run Ollama ceilings. Omission preserves historical defaults."""
    if value is None:
        return {}
    bounds = {'num_predict': (1, 32768), 'num_ctx': (512, 131072),
              'timeout_seconds': (30, 3600), 'total_timeout_seconds': (30, 14400)}
    if type(value) is not dict or any(key not in bounds for key in value):
        raise S.SymblicError('ollama_limits must contain only num_predict, num_ctx, timeout_seconds and '
                             'total_timeout_seconds', kind='invalid')
    for key, number in value.items():
        lo, hi = bounds[key]
        if type(number) is not int or not lo <= number <= hi:
            raise S.SymblicError(f'ollama_limits.{key} must be an integer in {lo}..{hi}', kind='invalid')
    return dict(value)


def _ollama_budget_read(folder, limits, source_sha256):
    if not folder:
        return None
    path = os.path.join(folder, 'ollama-budget.json')
    if not os.path.lexists(path):
        return None
    try:
        if os.path.islink(path):
            raise ValueError('linked ledger')
        with open(path, encoding='utf-8') as stream:
            row = json.loads(stream.read(4097))
        if (type(row) is not dict or type(row.get('version')) is not int or row.get('version') != 1 or row.get('limits') != limits
                or row.get('source_sha256') != source_sha256):
            raise ValueError('changed policy or source')
        validate_ollama_limits(row['limits'])
        for key in ('started', 'last_seen'):
            if type(row.get(key)) not in (int, float) or not math.isfinite(row[key]) or row[key] <= 0:
                raise ValueError('invalid clock')
        if row['last_seen'] < row['started']:
            raise ValueError('invalid clock order')
        return row
    except (OSError, ValueError, TypeError) as exc:
        raise S.SymblicError('Ollama budget is unreadable or its limits/source changed; start a new run',
                             kind='budget') from exc


def validate_model_pins(value) -> str:
    """The host's model_pins policy, validated (pure): None (the option omitted) is 'observe'; exactly 'observe' or
    exactly 'strict' is itself; anything else (another or misspelled text, a case variant, the empty text, a bool, a
    number, a container, a str subclass) raises SymblicError(kind='invalid') naming the allowed values. An invalid
    policy is never read as the default: Run.execute refuses it before any model call, effect or write."""
    if value is None:
        return 'observe'
    if type(value) is str and value in MODEL_PIN_POLICIES:
        return value
    raise S.SymblicError(f'model_pins must be {" or ".join(repr(p) for p in MODEL_PIN_POLICIES)} (or omitted, which '
                         f'means {MODEL_PIN_POLICIES[0]!r}), not {_brief(value)} ({type(value).__name__}); nothing was '
                         'run', kind='invalid')


def _identity_checker():
    """(check, VERSION) of the provider helper symblic.providers.ollama_call, imported when needed; (None, None) without it.
    A helper that is absent, half-deployed or broken (it raises at import or on reading its attributes) is no checker:
    identities are then unverifiable, and nothing here raises because of it. It is never part of the kernel identity:
    it reads observations, not the language."""
    try:
        boc = __import__('importlib').import_module('symblic.providers.ollama_call')
        check, version = getattr(boc, 'check', None), getattr(boc, 'VERSION', None)
    except Exception:  # noqa: BLE001  (any failure of the provider's module means: no checker here)
        return None, None
    if not callable(check):
        return None, None
    return check, (version if type(version) is int else None)


def _label_app(label):
    """The applicator a calls.jsonl row's `app` label names, or None when it names none."""
    if not isinstance(label, str) or not label:
        return None
    try:
        return S.parse_applicator(label)
    except (S.SymblicError, TypeError, ValueError):
        return None


def _names_applicator(record: dict, app) -> bool:
    """Whether a validated observed record is evidence about this applicator: its engine as the provider, its model
    as requested (or with Ollama's own ':latest' added to an untagged name) and, when the label names a node, that
    node (or none). A record for another model or node never pins or drifts this applicator's label."""
    if not isinstance(app, dict) or record.get('provider') != app.get('engine'):
        return False
    model = app.get('model') or ''
    if model:
        names = [model] if ':' in model.rsplit('/', 1)[-1] else [model, model + ':latest']
        if record.get('model') not in names:
            return False
    node = app.get('node') or ''
    return not node or record.get('node') in (None, node)


def _bounded_json(value, limit: int) -> tuple:
    """(stored, truncated): `value` as its JSON round trip when its text fits `limit` characters, else the first
    `limit` characters of that text (a string, so a cut record can never validate)."""
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return f'<not JSON: {type(value).__name__}>'[:limit], False
    if len(text) > limit:
        return text[:limit], True
    return json.loads(text), False


def _identity_status(raw, truncated: bool, check, app=None) -> tuple:
    """(status, digest, why) of one stored model_identity record for the applicator `app`, checked now: observed
    (validated, with its sha256 manifest digest, and naming this applicator), drift or unavailable (validated, no
    digest), invalid (cut, not a record, rejected by the checker, or naming another model or node) or unverifiable
    (no checker here). Only `observed` carries a digest, and only it can pin. `why` says, for every other status,
    what was not shown (strict pins quote it)."""
    if truncated:
        return 'invalid', None, 'the model identity record was cut at its size bound'
    if not isinstance(raw, dict):
        return 'invalid', None, 'the reply carries no model identity record that can be read'
    if check is None:
        return 'unverifiable', None, 'no identity checker (symblic.providers.ollama_call) is available to validate the record'
    try:
        record = check(raw)
        status = record.get('status') if isinstance(record, dict) else None
        digest = record.get('digest') if status == 'observed' else None
        reason = record.get('reason') if status == 'unavailable' else None
        names = True if app is None or status != 'observed' else _names_applicator(record, app)
    except Exception:  # noqa: BLE001  (a checker that fails, or a result that cannot be read, validates nothing)
        status = None
    if status not in ('observed', 'drift', 'unavailable'):
        return 'invalid', None, 'the model identity record does not validate'
    if status == 'drift':
        return 'drift', None, 'the model listing changed during the call, so no manifest digest was observed'
    if status == 'unavailable':
        return 'unavailable', None, 'no manifest digest was observed for this call' + (
            f' ({reason[:80]})' if isinstance(reason, str) and reason else '')
    if not (isinstance(digest, str) and _PINNED_DIGEST.fullmatch(digest)):
        return 'invalid', None, 'the model identity record does not validate'
    if not names:
        return 'invalid', None, 'the model identity record names another model or node than this applicator'
    return 'observed', digest, None


def _identity_block(events: list, pins: dict, *, basis: str, strict: bool, checker_version, checker_available: bool,
                    extra=None) -> dict:
    """report.model_identity (and the recheck's): per applicator its pin, digest counts and status counts; the
    drift events in order. `events`: {'app', 'status', 'digest', 'drift'} rows, `drift` the event or None."""
    apps: dict = {}
    for event in events:
        app = apps.setdefault(event['app'], {'digests': {}, 'statuses': dict.fromkeys(IDENTITY_STATUSES, 0)})
        app['statuses'][event['status']] += 1
        if event['digest'] is not None:
            app['digests'][event['digest']] = app['digests'].get(event['digest'], 0) + 1
    labels = sorted(apps)
    out = {}
    for label in labels[:LIST_MAX['applicators']]:
        digests = sorted(apps[label]['digests'].items(), key=lambda item: (-item[1], item[0]))
        out[label] = {'pinned': pins.get(label), 'digests': dict(digests[:LIST_MAX['digests']]),
                      'digests_truncated': len(digests) > LIST_MAX['digests'], 'statuses': apps[label]['statuses']}
    drift = [event['drift'] for event in events if event.get('drift') is not None]
    return {'version': RECEIPTS_VERSION, 'basis': basis, 'computed_at': round(time.time(), 3), 'strict': strict,
            'checker': {'available': checker_available, 'version': checker_version},
            'applicators': out, 'applicators_truncated': len(labels) > LIST_MAX['applicators'],
            'drift': drift[:LIST_MAX['drift']], 'drift_truncated': len(drift) > LIST_MAX['drift'], **(extra or {})}


def recheck_model_identities(folder: str, *, max_rows: int = 2000, max_bytes: int = 4_000_000, checker=None) -> dict:
    """Re-validate the model_identity records a run folder's calls.jsonl kept, with a fresh checker, and summarise
    them like report.model_identity (basis `fresh_recheck`). Only reads, within the bounds: no Run, model, network
    or write. `checker` is injectable (tests); by default it is symblic.providers.ollama_call.check, imported now, or none
    (every record then `unverifiable`). Pins and drift follow the rows' file order, as the runner does: the first
    observed validated digest of an applicator pins, a later different one is drift. Recorded evidence of what the
    node's Ollama listed, never an attestation of the weights that are installed now.

    The block says how complete the audit was, and never reports a clean audit it did not complete:
    - calls_file: 'absent' (the run folder holds no calls.jsonl: a complete audit of no calls), 'present' (read), or
      'unreadable' (the file, or the folder itself, could not be read);
    - rows_scanned: the lines examined; invalid_rows: torn or malformed lines (not a JSON object, or identity
      evidence without an applicator label), counted and skipped; rows_truncated: max_rows or max_bytes cut the scan
      (a line cut by max_bytes is not read);
    - missing_identity_rows: model attempts the folder recorded without any model_identity record (a row from before
      the identity contract, an applicator without it, a failed dispatch, a strict refusal of an unlabelled answer);
      every calls.jsonl row is an attempt except a launcher refusal before any model saw the prompt (_refused_row),
      which is not counted. Such a row is given no status and pins nothing: its identity is unknown, not checked;
    - incomplete_reasons, in this order: 'unreadable', 'invalid_rows', 'max_rows', 'max_bytes', 'no_checker'
      (records no checker here could examine), 'missing_identity' (missing_identity_rows > 0); audit_complete is true
      only when it is empty, so a ledger whose attempts carry no identity never reads like one with no attempts.
      There is no `policy`: a folder's rows can come from executions under several policies (`strict` says whether
      any row was recorded under strict pins)."""
    if type(max_rows) is not int or max_rows < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError('max_rows and max_bytes must be positive integers')
    if checker is None:
        check, version = _identity_checker()
    else:
        check, version = checker, getattr(checker, 'VERSION', None)
        version = version if type(version) is int else None
    found, calls_file, data = set(), 'present', b''
    try:
        with open(os.path.join(folder, 'calls.jsonl'), 'rb') as stream:
            data = stream.read(max_bytes + 1)
    except FileNotFoundError:
        calls_file = 'absent' if os.path.isdir(folder) else 'unreadable'
    except OSError:
        calls_file = 'unreadable'
    if calls_file == 'unreadable':
        found.add('unreadable')
    if len(data) > max_bytes:
        data = data[:max_bytes]
        data = data[:data.rfind(b'\n') + 1]          # a cut line is not read
        found.add('max_bytes')
    raw_rows, scanned, invalid = [], 0, 0
    for line in data.splitlines():
        if not line.strip():
            continue
        if scanned >= max_rows:
            found.add('max_rows')
            break
        scanned += 1
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):        # torn, not JSON, not UTF-8, or nested past any record
            row = None
        if not isinstance(row, dict):
            invalid += 1
            continue
        raw_rows.append(row)
    pins, events, strict, missing = {}, [], False, 0
    for row in raw_rows:
        if _refused_row(row):
            continue                                # refused before any model saw the prompt: not an attempt
        if 'model_identity_raw' not in row:
            missing += 1                            # an attempt with no identity evidence: counted, never a status
            continue
        label = row.get('app')
        app = _label_app(label)
        if app is None:
            invalid += 1                            # identity evidence that names no applicator
            continue
        status, digest, _why = _identity_status(row['model_identity_raw'],
                                                row.get('model_identity_raw_truncated') is True, check, app)
        at_call = row.get('identity_check_at_call') if isinstance(row.get('identity_check_at_call'), dict) else {}
        strict = strict or at_call.get('strict') is True
        drift = None
        if digest is not None:
            pinned = pins.setdefault(label, digest)
            if pinned != digest:
                drift = {'line': row.get('line') if type(row.get('line')) is int else 0, 'applicator': label,
                         'pinned': pinned, 'observed': digest, 'cached': False,
                         'action': 'refused' if at_call.get('refused') is True else 'recorded'}
        events.append({'app': label, 'status': status, 'digest': digest, 'drift': drift})
    if invalid:
        found.add('invalid_rows')
    if any(event['status'] == 'unverifiable' for event in events):
        found.add('no_checker')
    if missing:
        found.add('missing_identity')
    reasons = [r for r in ('unreadable', 'invalid_rows', 'max_rows', 'max_bytes', 'no_checker', 'missing_identity')
               if r in found]
    return _identity_block(events, pins, basis='fresh_recheck', strict=strict, checker_version=version,
                           checker_available=check is not None,
                           extra={'calls_file': calls_file, 'rows_scanned': scanned, 'invalid_rows': invalid,
                                  'missing_identity_rows': missing,
                                  'rows_truncated': 'max_rows' in found or 'max_bytes' in found,
                                  'audit_complete': not reasons, 'incomplete_reasons': reasons})


def _behaviour_projection(name, out):
    """What one external code adapter's result says about the candidate's behaviour on the declared test, and nothing
    derived from its source text (a declarations check returns the source's hash, declaration positions and parser
    provenance; a js_test failure report quotes the candidate's lines). None when this runner cannot project the
    result: an adapter it does not know, or a js_test with failing cases, whose result does not say which cases
    failed or what the candidate returned for them."""
    try:
        if name == 'js_run':
            return {'value': out}                                   # the value the declared call returned
        if name == 'js_test':
            passed, total, failed = out['passed'], out['total'], out['failed']
            if passed is True and type(total) is int and type(failed) is int and failed == 0:
                return {'passed': True, 'total': total, 'failed': 0}  # every case returned its expected JSON value
            return None
        if name == 'js_declarations_check':
            passed, status = out['passed'], out['status']
            surface = sorted((row['name'], row['kind']) for row in out['declarations'])
            if type(passed) is bool and isinstance(status, str) and all(
                    isinstance(n, str) and isinstance(k, str) for n, k in surface):
                return {'passed': passed, 'status': status, 'declarations': [[n, k] for n, k in surface]}
            return None
    except (KeyError, TypeError, AttributeError, IndexError):
        return None
    return None


def _adapter_observation(name, args, kwargs, out) -> dict:
    """One external code adapter call made while checking a Code candidate, without the candidate's source: the
    declared test (the arguments after the source) and the behaviour it observed (_behaviour_projection), as
    digests. `behavior` is None when the result cannot be projected (the ask is then not grouped)."""
    def digest(value):
        try:
            return E.digest(S.canon(value))
        except (S.SymblicError, TypeError, ValueError, RecursionError):
            return None
    cases = 1
    if name == 'js_test' and len(args) > 1 and isinstance(args[1], (tuple, list)):
        cases = len(args[1])
    behaviour = _behaviour_projection(name, out)
    return {'fn': name, 'test': digest([tuple(args[1:]), {k: kwargs[k] for k in sorted(kwargs)}]),
            'behavior': None if behaviour is None else digest(behaviour), 'cases': cases}


def _adapter_recorder(seen: list):
    def record(name, args, kwargs, out):
        try:
            seen.append(_adapter_observation(name, args, kwargs, out))
        except Exception:  # noqa: BLE001  (an observer never changes the check it watches)
            pass
    return record


def _code_behavior(s, checked: dict, occurrence=None) -> dict:
    """report.code_behavior's entry for one checked Code search round (D3): its passing candidates grouped by the
    behaviour their declared tests observed (_behaviour_projection: never the source text or anything derived from
    it). `checked`: candidate index -> (passed, observations of its last check). This certifies the declared tests
    only: candidates that agree here may still differ on any other input. When a passing candidate's results cannot
    be projected (unmeasured_adapters), nothing is grouped and two or more passing candidates are `unmeasured`:
    agreement is neither claimed nor denied. `single` means one passing candidate, so agreement was not measured;
    a search stops checking once its winner is decided, so a replay can check fewer candidates."""
    passing = [(i, seen) for i, (ok, seen) in sorted(checked.items()) if ok]
    unmeasured = sorted({o['fn'] for _i, seen in passing for o in seen if o['behavior'] is None})
    vectors: dict = {}
    for i, seen in passing if not unmeasured else ():
        vectors.setdefault(E.digest([[o['fn'], o['test'], o['behavior']] for o in seen]), []).append(i)
    basis = passing[0][1] if passing else (checked[min(checked)][1] if checked else [])
    groups = [{'vector_sha256': vector, 'members': members[:LIST_MAX['members']],
               'members_truncated': len(members) > LIST_MAX['members']}
              for vector, members in sorted(vectors.items(), key=lambda item: item[1][0])]
    n = len(passing)
    return {'line': s.line, 'name': s.name, **({'occurrence': occurrence} if occurrence is not None else {}),
            'scope': 'declared_tests_only',
            'tests': {'count': sum(o['cases'] for o in basis), 'sha256': E.digest([[o['fn'], o['test']] for o in basis])},
            'candidates': len(checked), 'passing': n,
            'groups': groups[:LIST_MAX['groups']], 'groups_truncated': len(groups) > LIST_MAX['groups'],
            'status': 'none' if n == 0 else 'single' if n == 1 else 'unmeasured' if unmeasured else
                      'agreed_on_declared' if len(groups) == 1 else 'differs_on_declared',
            **({'unmeasured_adapters': unmeasured} if unmeasured else {}),
            'covered_by': None}


# ---------------------------------------------------------------------------
# The interpreter
# ---------------------------------------------------------------------------

class Run:
    """One execution of a program. `applicators` has .call(req) -> reply dict (see symblic.providers.applicators) and
    optionally .delegate(target, task, options). `options`: by (default applicator(s)), max_asks, parallel,
    side_effects, effort, stop (a threading.Event)."""

    def __init__(self, source: str, inputs: dict | None = None, applicators=None, options: dict | None = None,
                 folder: str | None = None, log=None):
        self.source = source
        self.source_sha256 = hashlib.sha256(source.encode('utf-8')).hexdigest()
        self.execution_id = uuid.uuid4().hex
        self.checks: list = []
        self.inputs = dict(inputs or {})
        self.apps = applicators
        self.opts = dict(options or {})
        self._constructor_activity = False
        # The host's model_pins policy is validated BEFORE the Store exists: Store(folder) creates the folder and its
        # artifacts/, and an invalid policy must refuse this invocation without any write (no folder, no directory,
        # no changed mtime). Such a Run gets a folder-less Store; execute() then refuses before anything else.
        try:
            self.model_pins, self._policy_error = validate_model_pins(self.opts.get('model_pins')), None
            self.ollama_limits = validate_ollama_limits(self.opts.get('ollama_limits'))
            self._ollama_budget = _ollama_budget_read(folder, self.ollama_limits, self.source_sha256)
            self._ollama_deadline = None
            self.constructor_policy = validate_constructor_options(self.opts)
            if self.constructor_policy['mode'] != 'off' and not folder:
                raise S.SymblicError('enabled construction requires a durable run folder', kind='type')
            self._constructor_activity = constructor_records_gate(folder, mode=self.constructor_policy['mode'])
        except S.SymblicError as exc:
            self.model_pins, self._policy_error = None, exc
            self.ollama_limits, self._ollama_budget, self._ollama_deadline = {}, None, None
            self.constructor_policy = {'mode': 'off', 'limits': {}}
        self._constructor = None
        self.store = Store(folder if self._policy_error is None else None)
        self.say = log or (lambda text: None)
        self.stop = self.opts.get('stop') or threading.Event()
        self.kernel = S.Kernel(S.Env(), S.KB(), S.Budget(int(self.opts.get('max_steps') or S.MAX_STEPS)))
        self.types: dict = {}
        self.terms: dict = {}               # term (lower case) -> (term, definition): the program's vocabulary
        self.groups: dict = {}
        self.defaults: dict = {}
        self.outputs: list = []
        self.trace: list = []
        self.warnings: list = []
        self.notes: list = []
        self.asks = 0
        self.calls = 0
        self.calls_total = 0
        self.repairs_total = 0
        self.cached = 0
        # Acquisition labels survive child environments, routines and lifted
        # loop bindings. Automatic routing stays local for the rest of a run
        # after protected data is acquired; this is a conservative restriction,
        # not a claim that every later value depends on that acquisition.
        self._protected_acquired = False
        self.order = 0
        self.max_asks = int(self.opts.get('max_asks') or DEFAULT_MAX_ASKS)
        self.max_calls = int(self.opts.get('max_calls', DEFAULT_MAX_CALLS))
        auto_policy = self.opts.get('auto_route')
        if isinstance(auto_policy, dict) and self.store.dir and not self.opts.get('replay'):
            try:
                with open(self.store.path('model-budget.json'), encoding='utf-8') as stream:
                    ledger = json.load(stream)
                usage = ledger['sources'].get(self.source_sha256, {'calls': 0, 'repairs': 0})
                if type(ledger.get('version')) is not int or ledger['version'] != 1 or any(
                        type(usage.get(k)) is not int or usage[k] < 0 for k in ('calls', 'repairs')) \
                        or usage['repairs'] > usage['calls']:
                    raise ValueError('invalid budget')
                self.calls_total, self.repairs_total = usage['calls'], usage['repairs']
            except FileNotFoundError:
                self.calls_total = self.store.attempt_count
                self.repairs_total = self.store.repair_count
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                # A new dispatch will fail closed in reserve_model_call. Cached
                # reads are still useful, but an unreadable usage is not zero.
                self.calls_total = self.repairs_total = None
        if isinstance(auto_policy, dict) and isinstance(auto_policy.get('max_calls'), int) \
                and not isinstance(auto_policy['max_calls'], bool):
            self.max_calls = min(self.max_calls, max(0, auto_policy['max_calls']))
        # Not reduced by the repairs a resume finds in the ledger: a resumed run walks its recorded corrections
        # again through repair_gate, answered from the record at no charge; a NEW correction past the limit is
        # refused by reserve_model_call (refused_repair) and ends that candidate.
        self.auto_repairs_left = max(0, int(auto_policy.get('repairs', 0))) if isinstance(auto_policy, dict) else 0
        self.parallel = max(1, min(16, int(self.opts.get('parallel') or DEFAULT_PARALLEL)))
        self.feedback: dict = {}            # id(ask node) -> text for its next attempt
        self._vary: dict = {}               # id(ask node) -> identical rejected answers seen (sampling varied)
        self.feedback_checks: dict = {}    # id(ask node) -> the answer-only check line its feedback exposes
        self._finite_enabled = False
        self._finite_plans: dict = {}
        self._finite_rows: list = []
        self._finite_active = None
        self._checks: dict = {}             # id(ask node) -> {'between': [...], 'ensures': [...]}
        self.diagnoses: list = []           # checks that ran out of retries, with the pattern of what they rejected
        self.program = 'Untitled'
        self.execution_profile = 'legacy'
        self.total = 0
        self.no = 0
        self.status = 'new'
        self.error = None
        self.kernel_check = None            # kernel_gate's refusal, when this folder's work is another kernel's
        self.started = time.time()
        self.lock = threading.Lock()
        self._retry_effect_fences = 0
        self._epistemic_claims = {}
        self._epistemic_views = {}
        # D16: digests of immutable values only (binding names and type labels as str; receipt predicates by the
        # values that determine them), computed once per run. Never keyed by a parsed node: symblic.lang.abstraction rewrites
        # nested routine returns in place after first use (Lang._rewrite_returns), so a statement's syntax is
        # recomputed every time. Never run state, so an ensure-retry rollback cannot make an entry stale.
        self._digest_memo = {}
        self._epistemic_knowledge = []
        self._epistemic_rootsets = {}       # claim id -> frozenset of its roots' claim ids (exact; views are bounded)
        self._epistemic_rootrows = {}       # root claim id -> its conditional_on row
        self._epistemic_bounded = {}        # id(root set) -> (root set, listed rows, roots_omitted)
        self._memo_bases = {}               # id(a routine memo entry's dependency list) -> (list, read basis)
        self._epistemic_lock = threading.RLock()
        self._kernel_memo = None            # kernel_id() of this execution, once (see _kernel_identity)
        self.kernel.knowledge_read = self._knowledge_read
        self.kernel.knowledge_predicate_read = self._knowledge_read
        # Determinism receipts (lane C). One record per executed ask, rolled back with the run on an ensure-retry
        # (like warnings and checks; the trace keeps every attempt). _receipts_lock guards the records, carried
        # charges, occurrence counts, cloud totals and queued rows; _identity_lock the folder's pins, the identity
        # events and the call rows' order; _trace_lock a trace row's sequence number and its append (memory and file
        # in the same order, also from `for each` worker threads). None of them is taken while holding another,
        # self.lock or Store.lock (_identity_lock and _trace_lock are held around a Store.append, a leaf).
        self._ask_records: list = []
        self._ask_carry: dict = {}          # (id(ask), index) -> cloud dispatches a rolled-back execution charged
        self._ask_occurrences: dict = {}    # id(ask) -> its executions in this run (never rolled back)
        self._cloud_totals = {'charged': 0, 'refused': 0, 'rolled_back': 0}   # escalations, rollbacks included
        self._queued_rows: list = []        # trace rows from worker threads, written by ask() in the run's thread
        self._receipts_lock = threading.Lock()
        self._identity_lock = threading.Lock()
        self._trace_lock = threading.Lock()
        self._identity_pins = None          # applicator label -> pinned digest; read from the folder when needed
        self._identity_events: list = []
        # self.model_pins / self._policy_error were set before the Store (top of __init__): an invalid policy leaves
        # model_pins None, and _strict_pins fails closed on it.

    # -- entry -----------------------------------------------------------------------------
    def execute(self) -> dict:
        if self._policy_error is not None:
            # The host's policy is not one this runner enforces: refused before any model call, effect or write, as
            # the kernel gate's refusal below. The Store is folder-less (see __init__), so the folder is not even
            # created; an existing one keeps its status, records, directories and mtimes. Only this invocation fails.
            self.status, self.error = 'failed', self._policy_error.as_dict()
            return self.report()
        gate = None
        if self.store.dir:
            # Every resume path (run_folder and any embedding program) comes through here with the folder it continues.
            gate = kernel_gate(self.store.dir, store=self.store, pins=self.opts.get('execution_pins'),
                               replay=bool(self.opts.get('replay')))
            if gate['decision'] == 'refused':
                # Before any model call, effect or write: the folder keeps its status and records, so a stopped or
                # lost run stays resumable where its kernel is deployed. Only this invocation fails.
                self.status = 'failed'
                self.error = S.SymblicError(gate['message'], kind='version').as_dict()
                self.kernel_check = {k: gate[k] for k in ('decision', 'reason', 'current', 'recorded',
                                                          'answered_calls', 'effects', 'statements')}
                return self.report()
        self.status = 'running'
        try:
            if 'execution_pins' in self.opts:
                from symblic.kernel import execution_pins as execution
                execution.prepare(self)
            prog = S.parse(self.source, execution_profile=self.opts.get('profile'))
            self.execution_profile = prog['execution_profile']
            self._finite_preflight(prog['statements'])
            if self.constructor_policy['mode'] != 'off':
                from symblic.constructor.core import Bridge
                self._constructor = Bridge(self, self.constructor_policy)
            self.program = prog['name']
            self.warnings.extend(prog['warnings'])
            self.total = sum(1 for _ in _flat(prog['statements']))
            if gate is not None and gate['write']:
                _write_kernel_record(self.store.dir, gate['basis'])
            self._save_state()
            self.exec_block(prog['statements'], self.kernel.env)
            self.status = 'done'
        except RunFailed as e:
            self.status, self.error = 'failed', e.err.as_dict()
        except S.SymblicError as e:
            if self._finite_enabled and isinstance(e, S.KernelLimitError):
                e = S.SymblicError(e.message, e.line, e.col, e.limit)
            self.status, self.error = 'failed', e.as_dict()
        except Stopped:
            self.status = 'stopped'
        except MemoryError:
            self.status, self.error = 'failed', {'message': 'Check inconclusive: interpreter memory allocation failed; '
                                                'no candidate verdict.', 'line': 0, 'col': 0, 'kind': 'resource'}
        except Exception as e:  # noqa: BLE001  (a bug must end the run visibly, not hang it)
            self.status, self.error = 'failed', {'message': f'internal error: {type(e).__name__}: {e}',
                                                 'line': 0, 'col': 0, 'kind': 'internal'}
        if self._finite_active is not None:
            # No provisional host candidate survives an interrupted/inconclusive
            # check. Recorded calls and trial trace rows remain audit evidence.
            active = self._finite_active
            active['row']['status'] = 'inconclusive'
            active['row']['error_kind'] = (self.error or {}).get('kind', self.status)
            self._restore(active['snapshot'], active['env'])
            self._finite_active = None
        report = self.report()
        self._save_state(report)
        return report

    def check_stop(self):
        if self.stop.is_set():
            raise Stopped()

    def _kernel_identity(self) -> dict:
        """kernel_id() of this execution, computed once: it costs about 80 µs, and every binding's evidence, every
        trace row and every derivation receipt names it (language-2). A fresh copy each time, as kernel_id() gives."""
        kernel = self._kernel_memo
        if kernel is None:
            kernel = self._kernel_memo = S.kernel_id()
        return dict(kernel)

    def _finite_preflight(self, statements):
        """Validate every explicit menu/window before the first provider call.

        Menus are source literals, never evaluated model/input expressions. The
        first edition supports top-level sequential Text/enum asks and a single
        anchored conjunction. Actual trials use normal native execution only.
        """
        if 'fallback_choices' in self.opts:
            raise S.SymblicError('fallback_choices is an explicit per-ask source option, not a host default',
                                 kind='type')
        enabled = [n for n in _flat(statements) if n.k == 'ask' and 'fallback_choices' in n.options]
        self._finite_enabled = bool(enabled)
        if not enabled:
            return
        def refuse(message, node):
            raise S.SymblicError('Finite fallback: ' + message, node.line, node.col, 'type')
        if self.execution_profile != 'verified' or self.constructor_policy['mode'] != 'off':
            refuse('requires the verified profile and constructor=off', enabled[0])
        if any(n not in statements or n.each is not None for n in enabled):
            refuse('requires a top-level sequential ask', enabled[0])
        anchors = self._anchors(statements)
        types, functions, defaults = {}, {}, dict(self.opts)
        def static_option(value, key, ask):
            if not isinstance(value, S.Node):
                return value
            if value.k == 'lit':
                return value.value
            if value.k == 'str' and all(type(p) is str for p in value.parts):
                return ''.join(value.parts)
            # A bare route word can be rebound by the language. Requiring its
            # quoted literal avoids deciding a dynamic policy before execution.
            refuse(key + ' must be a literal for a finite fallback ask', ask)
        def pure(expr, available, visiting=(), checked=None):
            checked = set() if checked is None else checked
            for node in S.walk(expr):
                self.kernel.budget.tick(node=node)
                if node.k not in _FINITE_NODES:
                    refuse('unsupported expression in retry window: ' + node.k, node)
                if node.k != 'call' or node.fn in _FINITE_BUILTINS:
                    continue
                fn = available.get(node.fn)
                if fn is None or node.fn in visiting:
                    refuse('unknown, recursive or unsupported callable: ' + node.fn, node)
                if node.fn not in checked:
                    pure([fn.value, [spec.get('default') for spec in fn.specs]],
                         available, (*visiting, node.fn), checked)
                    checked.add(node.fn)
        for index, ask in enumerate(statements):
            if ask.k == 'use':
                defaults.update(ask.options)
            if ask.k == 'define':
                types[ask.name] = ask.type
            if ask.k == 'function':
                functions[ask.name] = ask
            if ask not in enabled:
                continue
            effective = {key: static_option(ask.options.get(key, defaults.get(key)), key, ask)
                         for key in ('route', 'determine', 'solve')}
            if (effective['route'] not in (None, 'vote') or effective['determine'] is not False
                    or effective['solve'] not in (None, False)):
                refuse('requires route="vote", determine=false and solve=false', ask)
            values = finite_fallback_choices(ask)
            ty = S.resolve_type(ask.type, types, ask.line)
            if ty['k'] not in ('text', 'enum'):
                refuse('this edition supports Text and one-of answer types', ask)
            # read_answer is the actual ask boundary: check_value alone does
            # not enforce Text nonempty/word bounds. Strict decoding must keep
            # the exact source string, with no normalization or substitution.
            for value in values:
                checked, _why = S.read_answer({'answer': value}, ty, coercion='strict')
                if type(checked) is not str or checked != value:
                    refuse('choice does not retain its exact native answer type', ask)
            ends = [ei for ei, ai in anchors.items() if ai == index]
            if len(ends) != 1:
                refuse('requires exactly one anchored ensure ... else retry', ask)
            end = ends[0]
            between = statements[index + 1:end]
            if any(n.k not in ('function', 'let') for n in between):
                refuse('retry window permits only pure function and let declarations', ask)
            available = {**functions, **{n.name: n for n in between if n.k == 'function'}}
            for row in between:
                if row.k == 'function':
                    pure([row.value, [spec.get('default') for spec in row.specs]], available, (row.name,))
                else:
                    pure(row.value, available)
            ensure = statements[end]
            pure([ensure.cond, ensure.because], available)
            self._finite_plans[id(ask)] = {'choices': tuple(values), 'type': ty, 'ensure': ensure,
                'choices_sha256': E.digest([S.canon(v) for v in values]),
                'predicate_sha256': E.digest(E.syntax(ensure.cond))}

    def _finite_trial(self, ask, env, snapshot, row):
        """Restore, bind a source-authored value, then let exec_block run the
        original declarations/check. No speculative evaluator or provider here.
        """
        plan = self._finite_plans[id(ask)]
        index = row['evaluated_count']
        self._finite_active = {'ask': ask, 'snapshot': snapshot, 'env': env, 'row': row}
        self._restore(snapshot, env)
        if index >= len(plan['choices']):
            row['status'] = 'exhausted'
            self._finite_active = None
            return False
        self.check_stop()
        self.kernel.budget.tick()
        row['evaluated_count'] = index + 1
        row['status'] = 'testing'
        metadata = finite_fallback_receipt(ask, plan['ensure'], index + 1,
            source_sha256=self.source_sha256, kernel_id=self._kernel_identity()['id'])
        value, _why = S.read_answer({'answer': plan['choices'][index]}, plan['type'], coercion='strict')
        meta = {'answered_by_finite_fallback': True, 'finite_fallback': metadata,
                'votes': 0, 'apps': [], 'rounds': 0, 'agreement': None,
                'contested': False, 'calls': 0, 'samples': []}
        binding = self._bind(env, ask.name, value, plan['type'], ask, 'exact', 1, meta=meta)
        rec = {'_key': (id(ask), None), 'line': ask.line, 'name': ask.name,
               'occurrence': self._ask_occurrences.get(id(ask), 0), 'status': 'unassessed',
               'reason': 'finite_fallback_not_uniqueness', 'answered_by': None,
               'solve_mode': 'off', '_finite_fallback': metadata}
        self._ask_records.append(rec)
        self._finite_active = {'ask': ask, 'snapshot': snapshot, 'env': env, 'row': row,
                               'record': rec, 'binding': binding}
        self._trace(ask, 'candidate', binding=binding, ask=meta,
                    note='host finite fallback candidate; original checks still required',
                    extra={'answered_by': 'finite_fallback'})
        return True

    # -- blocks ----------------------------------------------------------------------------
    def exec_block(self, stmts: list, env: S.Env) -> None:
        anchors = self._anchors(stmts)
        for ei, ai in anchors.items():          # the checks each ask must pass, for determination analysis
            plan = self._checks.setdefault(id(stmts[ai]), {'between': [], 'ensures': []})
            # The complete span is needed when later checks use later derived bindings.
            plan['between'] = stmts[ai + 1:ei]
            if not any(e is stmts[ei] for e in plan['ensures']):
                plan['ensures'].append(stmts[ei])
            for t in _flat(stmts[ai + 1:ei]):
                if t.k == 'delegate' or (t.k in S.EXTENSIONS and S.EXTENSIONS[t.k].klass == 'effect'):
                    raise S.SymblicError(f'the effect ({t.k}) at line {t.line} lies between the ask at line '
                                         f'{stmts[ai].line} and the ensure at line {stmts[ei].line} that may re-ask '
                                         'it: a retry would repeat it; move it after the ensure', t.line, t.col, 'check')
        starts = set(anchors.values())
        snaps: dict = {}                        # anchor index -> the run's state just before that ask
        attempts: dict = {}
        turned_down: dict = {}                  # ensure index -> [(fingerprint, shown)] it rejected in THIS pass of the
                                                # block (a loop body or an outer retry starts a new count)
        rejected_here: dict = {}                # id(ask node) -> the answers shown as rejected in its next request,
                                                # this pass only: another item's or pass's answers are not this one's

        def start_over_after(a):
            # the statements after ask a run again from scratch (a re-ask of a, or a whole-record fallback for
            # it): every later ask's count and rejected answers start over; the run's call budget does not
            for j, aj in anchors.items():
                if aj > a:
                    attempts.pop(j, None)
                    turned_down.pop(j, None)
                    rejected_here.pop(id(stmts[aj]), None)
        i = 0
        while i < len(stmts):
            self.check_stop()
            s = stmts[i]
            if i in starts:
                snaps[i] = self._snapshot(env)
            if s.k == 'ensure' and s.on_fail == 'retry':
                with S.capture_binding_reads(self) as check_reads:
                    ok, msg, raised = self._checked(s, env)
                receipt = self._record_check(s, env, ok)
                if ok:
                    active = self._finite_active
                    if active is not None and self._finite_plans[id(active['ask'])]['ensure'] is s:
                        active['row'].update(status='accepted',
                                             selected_index=active['row']['evaluated_count'],
                                             check_id=receipt['id'],
                                             selected_value_hash=active['binding'].hash,
                                             receipt_sha256=E.digest(active['binding'].meta['finite_fallback']))
                        active['record']['answered_by'] = 'finite_fallback'
                        self._finite_active = None
                    ai = anchors.get(i)
                    acceptance = None
                    if ai is not None:
                        acceptance = self._refine_module_acceptance(stmts[ai], env, check_reads.values(), receipt)
                    self._trace(s, 'ok', note='ensured', check=receipt, acceptance=acceptance)
                    i += 1
                    continue
                a = anchors.get(i)
                ask = stmts[a] if a is not None else None
                limit = self._retries(ask, env) if ask is not None else 0
                n = attempts.get(i, 0)
                bound = env.lookup(ask.name) if ask is not None else None
                fallback = (bound.meta or {}).get('_whole_value') if bound is not None else None
                if fallback is not None and not (bound.meta or {}).get('fallback_used'):
                    # a field-voted record nobody gave broke a whole-record check: try the record most agents
                    # did give (kernel arbitration, no model call) before re-asking anyone
                    self.say(f'  ensure failed at line {s.line} on an assembled record; trying the whole-record '
                             f'consensus for {ask.name}')
                    meta = {**(bound.meta or {}), 'fallback_used': True, 'vote': 'whole (fallback)',
                            'synthesized_rejected': S.show(bound.value, 200)}
                    meta.pop('_whole_value', None)
                    # transactional: nothing the rejected record caused survives (the ask's own receipt does: its
                    # models answered, and the substituted record is theirs)
                    self._restore(snaps[a], env, keep_receipts_of=ask)
                    self._bind(env, ask.name, fallback, bound.type, ask, bound.klass, bound.weight, meta=meta)
                    self._trace(s, 'retry', note='assembled record rejected; whole-record consensus substituted')
                    start_over_after(a)
                    i = a + 1
                    continue
                previous = env.lookup(ask.name) if ask is not None else None
                if ask is not None and n < limit:
                    attempts[i] = n + 1
                    rejected = rejected_here.setdefault(id(ask), [])
                    if previous is not None:
                        rejected.append(S.show(previous.value, 200))
                        turned_down.setdefault(i, []).append((previous.hash, S.show(previous.value, 200)))
                        down = turned_down[i]
                        if len(down) >= 2 and down[-1][0] == down[-2][0]:
                            # the model answered the retry with the very same answer (a small model at
                            # temperature 0, 2026-10-11): repeating the request is no regeneration; the next ask
                            # samples differently (temperature at least 0.6, a new seed), recorded on the ask
                            self._vary[id(ask)] = self._vary.get(id(ask), 0) + 1
                            self._trace(s, 'retry', note=f'identical rejected answer ({self._vary[id(ask)]}): sampling varied')
                    # what the kernel computed from the answer alone (never a part that reads another name),
                    # read before the restore below unbinds it; a `because` message is the author's own text
                    derived = D.derived_names(ask.name, stmts[a + 1:i], env)
                    detail = _bounded_explanation(s.cond, env, self.kernel.kb, derived)
                    alone = D.answer_only(s.cond, derived)
                    if alone:
                        # the whole check reads the answer alone, so its failed-check text (kernel error
                        # included) is model-readable on retry: the run's exposure record names the line
                        self.feedback_checks[id(ask)] = {'line': s.line, 'model_readable': True}
                    told = msg
                    if raised and not alone:
                        # the kernel's own error text can quote a value; one that may come from outside the
                        # answer is not handed to the model (the trace and the run's error keep it)
                        told = 'the check could not be evaluated for this answer'
                    # the attempt number and every rejected answer make each retry a new request: a retry whose
                    # prompt repeated the last one was answered from the replay cache (2026-10-02 audit)
                    self.feedback[id(ask)] = (f'Attempt {n + 2}. These answers were rejected: '
                                              + '; '.join(rejected[-5:]) +
                                              f'. Each failed the check `{_src(s)}`' + (f' ({told})' if told else '') +
                                              '. Give an answer that passes it.'
                                              + (f' In the last answer: {detail}.' if detail else ''))
                    self.say(f'  ensure failed at line {s.line}; re-asking {ask.name} (attempt {n + 2})')
                    # transactional retry: bindings, facts, rules, outputs, types, terms, groups and defaults go
                    # back to their state before the ask, so no effect of a rejected answer survives
                    self._restore(snaps[a], env)
                    self._trace(s, 'retry', note=msg)
                    start_over_after(a)
                    i = a
                    continue
                finite = self._finite_plans.get(id(ask)) if ask is not None else None
                if finite is not None:
                    active = self._finite_active
                    if active is None:
                        row = {'line': ask.line, 'name': ask.name, 'version': FINITE_FALLBACK_VERSION,
                               'choices_sha256': finite['choices_sha256'],
                               'predicate_sha256': finite['predicate_sha256'],
                               'selection': 'first_passing_in_declared_order',
                               'evaluated_count': 0, 'model_calls': 0, 'status': 'testing'}
                        self._finite_rows.append(row)
                        self._rejected_by_check(ask, snaps[a])
                    else:
                        row = active['row']
                    self._trace(s, 'rejected', note=msg, check=receipt,
                                extra={'finite_fallback': {'phase': 'candidate_rejected' if active else
                                                          'model_retries_exhausted',
                                                          'evaluated_count': row['evaluated_count']}})
                    if self._finite_trial(ask, env, snaps[a], row):
                        start_over_after(a)
                        i = a + 1
                        continue
                    self._trace(s, 'failed', note='all authored finite choices failed their checks', check=receipt)
                    raise RunFailed(S.SymblicError('all authored finite choices failed: ' + _src(s),
                                                  s.line, s.col, 'check'))
                message = f'ensure failed: {_src(s)}' + (f' — {msg}' if msg else '')
                note = msg
                found = None
                if ask is not None and previous is not None:
                    # the answers this check rejected, the last one included
                    seen = turned_down.get(i, [])
                    hashes = [h for h, _text in seen] + [previous.hash]
                    shown = [text for _h, text in seen] + [S.show(previous.value, 200)]
                    found = D.exhaustion(hashes)
                if found:
                    text = D.exhaustion_text(found)
                    message += f'; {text}' if text else ''
                    note = (f'{msg}; ' if msg else '') + f'rejected answers: {found["pattern"]}'
                    self._diagnose(s.line, ask.name, _src(s), found, shown)
                if ask is not None and a in snaps:
                    self._rejected_by_check(ask, snaps[a])
                self._trace(s, 'failed', note=note, check=receipt)
                raise RunFailed(S.SymblicError(message, s.line, s.col, 'check'))
            fenced = any(ai <= i < ei for ei, ai in anchors.items())
            self._retry_effect_fences += int(fenced)
            try:
                self.exec_statement(s, env)
            finally:
                self._retry_effect_fences -= int(fenced)
            i += 1

    def _anchors(self, stmts: list) -> dict:
        """For each `ensure ... else retry` (by index): the nearest earlier ask in this block that it reads,
        directly, through the names bound between them, or through the knowledge base (a fact statement
        derived from the answer feeds a query/holds in the check, also through rules)."""
        deps = self._rule_deps(stmts)
        out = {}
        for i, s in enumerate(stmts):
            if s.k != 'ensure' or s.on_fail != 'retry':
                continue
            need = set(S.free_names(s.cond)) | {'#fact:' + p for p in _closure(_queried(s.cond), deps)}
            for j in range(i - 1, -1, -1):
                t = stmts[j]
                binds = set(_binds(t))
                if binds & need:
                    if t.k == 'ask':
                        out[i] = j
                        break
                    need |= set(S.free_names(S._reads_of(t))) | _fact_names(t)
                    need |= {'#fact:' + p for p in _closure(_queried_in(t), deps)}
        return out

    def _rule_deps(self, stmts: list) -> dict:
        """pred -> the predicates its rules read (rules already in the KB and rules in this block)."""
        deps: dict = {}
        for pred, _args, body, *_ in self.kernel.kb.rules:
            deps.setdefault(pred, set()).update(_lit_preds(body))
        for t in _flat(stmts):
            if t.k == 'rule':
                deps.setdefault(t.pred, set()).update(_lit_preds(t.body))
        return deps

    def _snapshot(self, env: S.Env) -> dict:
        """Everything a statement between an ask and its ensure can change (extensions' own state excepted)."""
        flags = {}
        e = env
        while e is not None:
            for name, b in e.vars.items():
                flags[(id(e), name)] = (b, b.hidden, b.weight)
            e = e.parent
        kb = self.kernel.kb
        from symblic.lang import abstraction as symblic_lang
        return {'vars': dict(env.vars), 'flags': flags, 'facts': {p: set(ts) for p, ts in kb.facts.items()},
                'rules': list(kb.rules), 'outputs': len(self.outputs), 'warnings': len(self.warnings),
                'notes': len(self.notes), 'diagnoses': len(self.diagnoses), 'types': dict(self.types),
                'terms': dict(self.terms),
                'groups': dict(self.groups), 'defaults': dict(self.defaults), 'checks': len(self.checks),
                'epistemic_claims': dict(self._epistemic_claims),
                'epistemic_views': dict(self._epistemic_views),
                'epistemic_knowledge': list(self._epistemic_knowledge),
                'epistemic_index': [dict(self._epistemic_rootsets), dict(self._epistemic_rootrows),
                                    dict(self._epistemic_bounded), dict(self._memo_bases)],
                'epistemic_reads': [(frame, dict(frame)) for frame in S.binding_read_frames(self)],
                'language': symblic_lang.snapshot_state(self),
                'ask_records': len(self._ask_records)}

    def _rejected_by_check(self, ask, snap: dict) -> None:
        """The ensure anchored to `ask` rejected what it bound, with no retry left: the answer was delivered but never
        accepted, so this execution's receipts (every item of a `for each`) say nothing was answered (D2)."""
        with self._receipts_lock:
            for rec in self._ask_records[snap['ask_records']:]:
                if rec['_key'][0] == id(ask) and rec['answered_by'] is not None:
                    rec['answered_by'] = None
                    rec['rejected_by_check'] = True

    def _restore(self, snap: dict, env: S.Env, keep_receipts_of=None) -> None:
        from symblic.lang import abstraction as symblic_lang
        with self._receipts_lock:
            undone = self._ask_records[snap['ask_records']:]
            del self._ask_records[snap['ask_records']:]
            for rec in undone:
                if keep_receipts_of is not None and rec['_key'][0] == id(keep_receipts_of):
                    self._ask_records.append(rec)
                    continue
                if rec.get('_escalation'):
                    self._cloud_totals['rolled_back'] += 1      # its charges stay in the run's totals
                # a rolled-back execution's cloud calls were charged: its re-run carries them
                charged = (rec.get('_escalation') or {}).get('cloud_dispatches_charged') or 0
                if charged:
                    self._ask_carry[rec['_key']] = self._ask_carry.get(rec['_key'], 0) + charged
        env.vars.clear()
        env.vars.update(snap['vars'])
        for (_eid, _name), (b, hidden, weight) in snap['flags'].items():
            b.hidden, b.weight = hidden, weight
        kb = self.kernel.kb
        kb.facts = {p: set(ts) for p, ts in snap['facts'].items()}
        kb.rules = list(snap['rules'])
        kb._derived = None
        with self.lock if self.opts.get('progress_outputs') is True else nullcontext():
            del self.outputs[snap['outputs']:]
        del self.warnings[snap['warnings']:]
        del self.notes[snap['notes']:]
        del self.diagnoses[snap['diagnoses']:]
        del self.checks[snap['checks']:]
        self._epistemic_claims = dict(snap['epistemic_claims'])
        self._epistemic_views = dict(snap['epistemic_views'])
        self._epistemic_knowledge = list(snap['epistemic_knowledge'])
        rootsets, rootrows, bounded, memo_bases = snap['epistemic_index']
        self._epistemic_rootsets, self._epistemic_rootrows = dict(rootsets), dict(rootrows)
        self._epistemic_bounded, self._memo_bases = dict(bounded), dict(memo_bases)
        for frame, saved in snap['epistemic_reads']:
            frame.clear()
            frame.update(saved)
        for attr in ('types', 'terms', 'groups', 'defaults'):
            cur = getattr(self, attr)
            cur.clear()
            cur.update(snap[attr])
        symblic_lang.restore_state(self, snap['language'])
        if self.opts.get('progress_outputs') is True:
            # The next provider call must never leave a rejected frame on disk.
            self._save_state()

    def _retries(self, ask, env) -> int:
        v = self._opt(ask, 'retries', env)
        return max(0, min(5, int(v))) if S.is_num(v) else 2

    def _check(self, s, env):
        ok, msg, _raised = self._checked(s, env)
        return ok, msg

    def _checked(self, s, env):
        """(ok, message, raised): `raised` when the condition could not be evaluated and the message is the
        kernel's own error text (which can quote a value) rather than the author's `because`."""
        try:
            ok = S._truth(self.kernel.eval(s.cond, env), s.cond)
        except S.SymblicError as e:
            if self._finite_enabled and isinstance(e, S.KernelLimitError):
                raise S.SymblicError(e.message, e.line, e.col, e.limit) from e
            if e.kind in ('effect', 'resource', 'unavailable', 'budget') or (
                    self._finite_plans and any(p['ensure'] is s for p in self._finite_plans.values())
                    and e.kind not in ('type', 'runtime', 'check', 'name', 'syntax')):
                raise           # no candidate verdict: retries cannot repair unavailable checks or exhausted resources
            return False, e.message, True
        msg = ''
        if not ok and s.because is not None:
            try:
                msg = S.show(self.kernel.eval(s.because, env))
            except S.SymblicError as exc:
                if exc.kind in ('resource', 'unavailable', 'budget'):
                    raise
                msg = ''
        return ok, msg, False

    def _diagnose(self, line, name, check, found, answers) -> None:
        """A check ran out of retries: keep the pattern of the answers it rejected (restored like warnings)."""
        with self.lock:
            self.diagnoses.append({'line': line, 'name': name, 'check': check, 'attempts': found['attempts'],
                                   'distinct': found['distinct'], 'pattern': found['pattern'],
                                   'answers': list(answers)[-6:]})

    def _record_check(self, s, env, passed):
        receipt = E.check_receipt(s, env, source=self.source_sha256, passed=passed, text=_src(s))
        preds = _closure(_queried(s.cond), self._rule_deps([]))
        if preds:
            receipt['facts'] = []
            for pred in sorted(preds):
                rows = self.kernel.kb.facts.get(pred, set())
                values = sorted([S.canon(tuple(S._unkey(v) for v in row)) for row in rows], key=E.digest)
                rules = [[p, E.syntax(args), E.syntax(body)] for p, args, body, *_ in self.kernel.kb.rules if p == pred]
                receipt['facts'].append({'pred': pred, 'count': len(values), 'sha256': E.digest(values),
                                         'rules_sha256': E.digest(rules)})
            receipt['id'] = E.digest({k: v for k, v in receipt.items() if k != 'id'})
        self.checks.append(receipt)
        return receipt

    def _refine_module_acceptance(self, ask, env, reads, receipt):
        """An executed check can select a proposal under imported module premises.

        Keep that immutable proposal, its value/status and every original root.
        Only an accepted check whose actual reads depend on a new module
        fact/rule adds a derivation from the old proposal and those premises. Bindings already
        derived from this proposal in the same scope receive the same acceptance
        condition. This neither executes imports early nor certifies their truth.
        """
        original = env.lookup(ask.name)
        if original is None or not original.meta.get('epistemic'):
            return
        old_claim = original.meta['epistemic']['claim']
        roots = self._root_ids(old_claim['id'])
        read_roots = set()
        for binding in reads:
            claim = binding.meta.get('epistemic', {}).get('claim')
            if claim is not None:
                read_roots.update(self._root_ids(claim['id']))
        # A check can read a previously computed Boolean or a memoized result.
        # Its original root set, including bounded grouping, is authoritative;
        # querying the current KB again would change that snapshot's meaning.
        new_roots = read_roots - roots
        premises = [b for b in self._epistemic_knowledge
                    if b.meta.get('_epistemic_module', {}).get('kind') in ('fact', 'rule')
                    and b.meta['epistemic']['claim']['id'] in new_roots]
        if not premises:
            return
        # Build a reverse dependency index once for this acceptance, rather
        # than repeatedly walking long paths for every in-scope binding.
        children = {}
        for ident, claim in self._epistemic_claims.items():
            for dep in claim['dependencies']:
                children.setdefault(dep['id'], []).append(ident)
        affected, todo = {old_claim['id']}, [old_claim['id']]
        while todo:
            for child in children.get(todo.pop(), ()):
                if child not in affected:
                    affected.add(child)
                    todo.append(child)

        def refine(binding, parents):
            revised = copy.copy(binding)
            revised.meta = dict(binding.meta)
            revised.meta.pop('epistemic', None)
            self._claim_for_binding(revised, parents=[binding, *parents], origin='derived',
                status='contested' if binding.meta.get('contested') else 'unknown',
                derivation={'operation': 'accepted_under_module_premises', 'check': receipt['id']})
            return revised

        accepted = refine(original, premises)
        replacements = {ask.name: accepted}
        for name, binding in env.vars.items():
            claim = binding.meta.get('epistemic', {}).get('claim', {})
            if name != ask.name and claim.get('id') in affected:
                replacements[name] = refine(binding, [accepted])
        env.vars.update(replacements)
        # Preserve the receipt's hash/contents. This separate trace relation
        # links its immutable ID to the new immutable acceptance claims.
        return {'check_id': receipt['id'],
                'bindings': {name: self._epistemic_ref(b.meta['epistemic']['claim'])
                             for name, b in sorted(replacements.items())},
                'scope': 'same_scope_values_selected_by_a_passed_check',
                'premise_scope': 'conservative_actual_check_read_ancestry'}

    # -- statements ------------------------------------------------------------------------
    def exec_statement(self, s, env: S.Env) -> None:
        with S.capture_binding_reads(self):
            return self._exec_statement(s, env)

    def _exec_statement(self, s, env: S.Env) -> None:
        k = s.k
        self.no += 1
        t0 = time.time()
        if k == 'program':
            self.program = s.name
            return
        if k in ('note', 'section'):
            self.notes.append({'line': s.line, 'kind': k, 'text': s.get('text') or s.get('title') or ''})
            return
        if k == 'use':
            for key, v in s.options.items():
                value = self._opt_value(key, v, env)
                self.defaults[key] = S.capsule_presentation(value, s.line, s.col) if key == 'capsule' else value
            self._trace(s, 'ok', note=', '.join(f'{k2}={_short(v2)}' for k2, v2 in self.defaults.items()))
            return
        if k == 'given':
            self._given(s, env)
            return
        if k == 'let':
            first_row = len(self.trace)
            self.kernel.klass = 'exact'          # a routine call in the expression raises it (symblic.lang.abstraction)
            value = self.kernel.eval(s.value, env)
            if s.type is not None:
                value = S.check_value(value, S.resolve_type(s.type, self.types, s.line), s.name)
            weight = self._weight(s.weight, env)
            from symblic.lang import abstraction as symblic_lang
            deps = symblic_lang._ask_dependencies(self.trace[first_row:])
            b = self._bind(env, s.name, value, s.type and S.resolve_type(s.type, self.types, s.line), s,
                           getattr(self.kernel, 'klass', 'exact'), weight, meta={'dependencies': deps} if deps else None)
            self._trace(s, 'ok', binding=b, ms=_ms(t0))
            return
        if k == 'term':
            key = s.term.lower()
            if key in self.terms:
                raise S.SymblicError(f'the term "{s.term}" is defined twice', s.line, s.col, 'name')
            self.terms[key] = (s.term, s.definition)
            self._trace(s, 'ok', note=s.term)
            return
        if k == 'define':
            if s.name in self.types:
                raise S.SymblicError(f'type {s.name} is defined twice', s.line, s.col, 'type')
            self.types[s.name] = s.type
            S.resolve_type(s.type, self.types, s.line)
            return
        if k == 'group':
            members = self.kernel.eval(s.members, env)
            if not isinstance(members, (tuple, frozenset)):
                members = (members,)
            apps = [E.parse_applicator(m) for m in members]
            if not apps:
                raise S.SymblicError('a group needs at least one applicator', s.line, s.col)
            self.groups[s.name] = apps
            self._bind(env, s.name, tuple(S.app_label(a) for a in apps), None, s, 'exact', 0)
            self._trace(s, 'ok', note=', '.join(S.app_label(a) for a in apps))
            return
        if k == 'fact':
            added = 0
            for pred, args in s.atoms:
                added += self.kernel.kb.add_fact(pred, tuple(self.kernel._logic_arg(a, env) for a in args))
            self._trace(s, 'ok', note=f'{added} fact(s); {self.kernel.kb.fact_count()} known')
            return
        if k == 'rule':
            self.kernel.kb.add_rule(s, env)
            self._trace(s, 'ok')
            return
        if k == 'ask':
            self.ask(s, env)
            return
        if k in ('ensure', 'assert', 'expect'):
            ok, msg = self._check(s, env)
            receipt = self._record_check(s, env, ok)
            if ok:
                self._trace(s, 'ok', check=receipt)
                return
            if k == 'ensure' and s.on_fail == 'warn':
                self.warnings.append({'line': s.line, 'message': f'ensure failed: {_src(s)}' + (f' — {msg}' if msg else '')})
                self._trace(s, 'warn', note=msg, check=receipt)
                return
            detail = _bounded_explanation(s.cond, env, self.kernel.kb) if k in ('assert', 'expect') else ''
            suffix = f' In this check: {detail}.' if detail else ''
            self._trace(s, 'failed', note=msg + suffix, check=receipt)
            raise RunFailed(S.SymblicError(f'{k} failed: {_src(s)}' + (f' — {msg}' if msg else '') + suffix,
                                           s.line, s.col, 'check'))
        if k == 'if':
            for cond, body in s.branches:
                if S._truth(self.kernel.eval(cond, env), cond):
                    self._trace(s, 'ok', note=f'took the branch at line {cond.line}')
                    self.exec_block(body, env)
                    return
            if s.else_body is not None:
                self._trace(s, 'ok', note='took else')
                self.exec_block(s.else_body, env)
            return
        if k == 'for':
            self._for(s, env)
            return
        if k in ('show', 'return', 'draw'):
            self._output(s, env)
            return
        if k == 'forget':
            for name in s.names:
                b = env.lookup(name)
                if b is None:
                    raise S.SymblicError(f'cannot forget {name}: it is not bound', s.line, s.col, 'name')
                b.hidden = True
            self._trace(s, 'ok', note=', '.join(s.names))
            return
        if k == 'pin':
            w = self._weight(s.weight, env) if s.weight is not None else 5
            for name in s.names:
                b = env.lookup(name)
                if b is None:
                    raise S.SymblicError(f'cannot pin {name}: it is not bound', s.line, s.col, 'name')
                b.weight, b.hidden = w, False
            self._trace(s, 'ok', note=f'weight {w}: ' + ', '.join(s.names))
            return
        if k == 'delegate':
            self._delegate(s, env)
            return
        if k in S.EXTENSIONS:
            ext = S.EXTENSIONS[k]
            if ext.klass == 'effect' and self._retry_effect_fences:
                raise S.SymblicError('effect inside a retry window is refused', s.line, s.col, 'effect')
            if ext.klass == 'effect' and not getattr(ext, 'self_gating', False) and (
                    self.opts.get('replay') or self.opts.get('preview') or not self.opts.get('side_effects')):
                raise S.SymblicError('effect statements are disabled in preview/replay and require '
                                     'side_effects for execution', s.line, s.col, 'effect')
            ext.execute(self, s, env)
            return
        raise S.SymblicError(f'cannot run a {k} statement', s.line, s.col)

    def _given(self, s, env):
        ty = S.resolve_type(s.type, self.types, s.line) if s.type else None
        if s.name in self.inputs:
            raw = self.inputs[s.name]
            value = S.coerce(raw, ty, s.name) if ty else S.from_json(raw)
            note = 'input'
        elif s.default is not None:
            value = self.kernel.eval(s.default, env)
            if ty:
                value = S.check_value(value, ty, s.name)
            note = 'default'
        else:
            raise S.SymblicError(f'the input {s.name} is required (pass it when you run the program)', s.line, s.col,
                                 'name')
        b = self._bind(env, s.name, value, ty, s, 'exact', 3)
        self._trace(s, 'ok', binding=b, note=note)

    def _for(self, s, env):
        items = self.kernel._iterable(self.kernel.eval(s.src, env), s)
        if len(items) > 10_000:
            raise S.SymblicError('a loop over more than 10000 items', s.line, s.col)
        # What the source read is every iteration's control dependency: this statement's frame keeps it, and an
        # iteration's own reads stay in that iteration's scope (language-2: no iteration inherits another's).
        head = tuple(self._read_bindings())
        # In a routine, a loop whose body can `return` (review of lane A): whether an iteration returned, and so
        # what the routine returns from inside the loop or does after it, is decided by what every iteration so far
        # read. Those reads are kept, once each, and reach the enclosing frames when the loop is left, however it
        # is left; no iteration sees another's.
        decided: dict | None = {} if _returns_from(s.body) else None
        lifted: dict = {}
        klass: dict = {}
        types: dict = {}
        evidence: dict = {}
        members: dict = {}
        for idx, item in enumerate(items, 1):
            self.check_stop()
            self.kernel.budget.tick(1, s)
            child = S.Env(env)
            # An element of the source: reading it is no further read, and a claim for it, when a context row
            # needs one, is derived from the source's reads (as `ask ... for each` does for its item)
            child.vars[s.var] = S.Binding(s.var, item, stmt=f'L{s.line}', line=s.line, weight=2,
                                          meta={'_epistemic_element': True, '_epistemic_basis': head})
            frame: dict = {}
            try:
                with S.capture_binding_reads(self, scope=True) as frame:
                    self.exec_block(s.body, child)
            except BaseException:
                # A non-local exit (a routine's `return`, an error a test block catches) carries this iteration's
                # reads out, with those of the iterations before it that went on
                for b in (decided or {}).values():
                    S.record_binding_read(b)
                for b in frame.values():
                    S.record_binding_read(b)
                raise
            if decided is not None:
                decided.update(frame)
            for name, b in child.vars.items():
                if name == s.var:
                    continue
                lifted.setdefault(name, []).append(b.value)
                members.setdefault(name, []).append(b)
                klass[name] = _worse(klass.get(name, 'exact'), b.klass)
                types[name] = b.type
                evidence.setdefault(name, []).append({'hash': b.hash,
                    'evidence_sha256': E.digest(b.meta['evidence']) if b.meta and b.meta.get('evidence') else None})
        for b in (decided or {}).values():
            # the loop ran to its end because no iteration returned: what follows it depends on what decided that
            S.record_binding_read(b)
        for name, values in lifted.items():
            if env.has_local(name):
                raise S.SymblicError(f'{name} is already bound outside the loop', s.line, s.col, 'name')
            if len(values) != len(items):
                # lifting only the iterations that bound it would misalign the lists (2026-10-02 audit R5h)
                raise S.SymblicError(f'{name} is bound in {len(values)} of {len(items)} iterations: bind it in '
                                     'every iteration (add an else) so the lists line up', s.line, s.col, 'name')
            ty = {'k': 'list', 'of': types[name]} if types.get(name) else None
            # Each iteration's binding is a parent of the list (epistemic-1): its model, contested and other roots
            # and its admissibility carry over, as they would through any derivation.
            b = self._bind(env, name, tuple(values), ty, s, klass[name], 1,
                           meta={'evidence': {'version': E.VERSION, 'mechanism': 'aggregation',
                                             'assurance': 'derived_from_inputs', 'items': evidence[name],
                                             'independence': 'not_established'},
                                 '_epistemic_parents': members[name]})
            self._trace(s, 'ok', binding=b, note=f'{len(values)} iteration(s)')
        if not lifted:
            self._trace(s, 'ok', note=f'{len(items)} iteration(s)')

    def _output(self, s, env):
        self.kernel.klass = 'exact'
        value = self.kernel.eval(s.value, env)
        label = S.show(self.kernel.eval(s.label, env)) if s.label is not None else ''
        row = {'kind': s.k, 'line': s.line, 'label': label, 'value': S.to_plain(value), 'text': S.show(value, 4000),
               'hash': S.fingerprint(value), 'type': S.type_name(value),
               'canonical': S.canon(value), 'canonical_version': S.CANON_VERSION,
               'binding': s.value.name if s.value.k == 'name' else None}
        if getattr(self.kernel, 'klass', 'exact') != 'exact':
            row['class'] = self.kernel.klass
        if s.k == 'draw':
            if not isinstance(value, S.Svg):
                raise S.SymblicError('draw needs a drawing (flower(...), rose(...), polygon(...))', s.line, s.col,
                                     'type')
            row['file'] = self.store.write_artifact(label or f'drawing-{s.line}.svg', str(value))
            row['svg'] = str(value)
            row.pop('value')
        with self.lock if self.opts.get('progress_outputs') is True else nullcontext():
            self.outputs.append(row)
        self._trace(s, 'ok', note=f'{s.k} {row["hash"]}')
        if self.opts.get('progress_outputs') is True:
            self._save_state()

    def _delegate(self, s, env):
        if self._retry_effect_fences:
            raise S.SymblicError('delegate inside a retry window is refused', s.line, s.col, 'effect')
        if self.opts.get('preview') or (not self.opts.get('replay') and not self.opts.get('side_effects')):
            raise S.SymblicError('delegate starts an agent: run the program with side effects allowed', s.line, s.col)
        task = S.show(self.kernel.eval(s.task, env))
        target = S.show(self.kernel.eval(s.target, env))
        options = {key: self._opt_value(key, v, env) for key, v in s.options.items()}
        key = E.digest([self.source_sha256, s.line, s.name, target, task, E.syntax(options)])
        with self.store.delegation_ledger() as ledger:
            previous = ledger.get(key)
            if previous is not None and previous['phase'] != 'failed':
                if previous['phase'] != 'done':
                    raise S.SymblicError('delegate outcome is uncertain; reconcile the original action before retrying',
                                         s.line, s.col, 'uncertain')
                res = previous['result']
            else:
                if self.opts.get('replay') or self.store.legacy_effects:
                    raise S.SymblicError('delegate has no completed ledger receipt; replay/resume cannot launch it',
                                         s.line, s.col, 'uncertain')
                if self.apps is None or not hasattr(self.apps, 'delegate'):
                    raise S.SymblicError('no agent runner is available to delegate to (the applicators have no '
                                         'delegate method)', s.line, s.col)
                intent = {'key': key, 'phase': 'intent', 'source_sha256': self.source_sha256, 'line': s.line}
                self.store.append('delegate-effects.jsonl', intent, durable=True)
                ledger[key] = intent
                try:
                    res = self.apps.delegate(target, task, options)
                except Exception as exc:  # noqa: BLE001
                    raise S.SymblicError('delegate outcome is uncertain: ' + type(exc).__name__,
                                         s.line, s.col, 'uncertain') from None
                if isinstance(res, dict) and res.get('refused') is True and not res.get('id'):
                    refused = {**intent, 'phase': 'failed', 'refused': True,
                               'error': str(res.get('error') or 'admission refused')[:600]}
                    self.store.append('delegate-effects.jsonl', refused, durable=True)
                    ledger[key] = refused
                    raise S.SymblicError('delegate was refused before dispatch: ' + refused['error'],
                                         s.line, s.col, 'unavailable')
                if not isinstance(res, dict) or res.get('error') or not res.get('id') or res.get('refused') is True:
                    raise S.SymblicError('delegate did not confirm an outcome; reconcile before retrying',
                                         s.line, s.col, 'uncertain')
                outcome = {**intent, 'phase': 'done', 'result': res}
                self.store.append('delegate-effects.jsonl', outcome, durable=True)
                ledger[key] = outcome
        value = {k: S.from_json(v) for k, v in res.items() if k in ('id', 'engine', 'name', 'status', 'link')}
        b = self._bind(env, s.name, value, None, s, 'effect', 1) if s.name else None
        self._trace(s, 'ok', binding=b, note=f'{target}: {value.get("id", "")}')

    # -- asks ------------------------------------------------------------------------------
    def ask(self, s, env: S.Env) -> None:
        try:
            self._ask_statement(s, env)
        finally:
            self._write_queued_rows()     # what worker threads observed (model identity), from the run's thread

    def _ask_statement(self, s, env: S.Env) -> None:
        # the n-th execution of this ask statement in this run (a loop, a routine, a retry): with `index` for the items
        # of a `for each`, it tells repeated executions of one line apart in the receipts and the trace
        with self._receipts_lock:
            occurrence = self._ask_occurrences[id(s)] = self._ask_occurrences.get(id(s), 0) + 1
        ty = S.resolve_type(s.type, self.types, s.line)
        if s.each is None:
            res = self._ask_one(s, env, ty, None, occurrence=occurrence)
            amb = res['meta'].get('ambiguity')
            if amb and amb['flagged']:
                self.warnings.append({'line': s.line, 'message': f'{s.name}: {amb["flagged"]} of {amb["of"]} readers '
                                      'found more than one reading: ' + '; '.join(amb['readings'][:4])})
            b = self._bind(env, s.name, res['value'], ty, s, S.determinism_class(ty), res['weight'], meta=res['meta'])
            self._trace(s, 'ok' if not res['meta'].get('contested') else 'contested', binding=b, ask=res['meta'],
                        extra=self._answer_fields([res['_record']]))
            return
        var, src = s.each
        feedback = self.feedback.pop(id(s), '')          # once, for every item (not whichever thread pops first)
        items = self.kernel._iterable(self.kernel.eval(src, env), s)
        if len(items) > 1000:
            raise S.SymblicError('ask ... for each over more than 1000 items', s.line, s.col)

        source_reads = tuple(self._read_bindings())
        records: dict = {}                                 # item index -> its receipt, kept in item order below

        def one(idx_item):
            idx, item = idx_item
            with S.capture_binding_reads(self, source_reads) as frame:
                child = S.Env(env)
                bound = child.vars[var] = S.Binding(var, item, weight=3, stmt=f'L{s.line}', line=s.line)
                self._claim_for_binding(bound, parents=source_reads,
                                        origin='derived', derivation='selected iteration item')
                result = self._ask_one(s, child, ty, idx, feedback=feedback, records=records, occurrence=occurrence)
                # the item's own claim is derived from source_reads, which this statement's frame holds already
                return result, [b for b in frame.values() if b is not bound]

        workers = min(self.parallel, max(1, len(items)))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                outcomes = list(pool.map(one, enumerate(items, 1)))
        finally:
            for idx in sorted(records):
                with self._receipts_lock:
                    self._ask_records.append(records[idx])
                self._determinacy_row(records[idx])
        # A worker's frame lives in its own thread: what it read (facts shown in its context, a key= or other option
        # input) is merged into this statement's frame here, in this thread, once every worker is done (epistemic-5)
        for _result, reads in outcomes:
            for b in reads:
                S.record_binding_read(b)
        results = [result for result, _reads in outcomes]
        values = tuple(r['value'] for r in results)
        # an automatic route measures no agreement (None): the items' aggregate is then unmeasured too, not a crash
        agreements = [r['meta']['agreement'] for r in results]
        meta = {'each': len(items), 'agreement': None if None in agreements else min(agreements or [1.0]),
                'contested': any(r['meta'].get('contested') for r in results),
                'items': [r['meta'] for r in results]}
        b = self._bind(env, s.name, values, {'k': 'list', 'of': ty}, s, S.determinism_class(ty),
                       results[0]['weight'] if results else 1, meta=meta)
        self._trace(s, 'ok' if not meta['contested'] else 'contested', binding=b, ask=meta,
                    extra=self._answer_fields([r['_record'] for r in results], each=True))

    def _ask_one(self, s, env: S.Env, ty: dict, index, feedback=None, records=None, occurrence=1) -> dict:
        """One executed ask (an item of `for each` included), with its determinism receipt: the record exists from
        here on, so an ask that fails still reports that nothing was answered (answered_by None), in the report and,
        with its determinacy row, in the trace."""
        self.check_stop()
        presentation = self._opt(s, 'capsule', env) if (
            'capsule' in s.options or 'capsule' in self.defaults or 'capsule' in self.opts) else 'full'
        presentation = S.capsule_presentation(presentation, s.line, s.col)
        with self.lock:
            self.asks += 1
            if self.asks > self.max_asks:
                raise S.SymblicError(f'the program asked more than {self.max_asks} questions (max_asks)', s.line,
                                     s.col)
        rec = {'_key': (id(s), index), 'line': s.line, 'name': s.name, 'occurrence': occurrence,
               **({'index': index} if index is not None else {}),
               'status': 'unassessed', 'reason': 'not_attempted', 'answered_by': None,
               'solve_mode': self._solve_peek(s, env)}
        with self._receipts_lock:
            carried = self._ask_carry.pop(rec['_key'], 0)
            if records is None:
                self._ask_records.append(rec)
        if records is not None:
            records[index] = rec                    # for-each items: ask() adds them in item order
        if carried:
            rec['_carried_cloud'] = carried
        try:
            res = self._ask_body(s, env, ty, index, feedback, rec, presentation)
        except BaseException:
            if index is None and not rec.get('_row'):
                # failed before its assessment (an option, an applicator, a stop): the trace says so too; for-each
                # items get theirs from ask(), in item order
                try:
                    self._determinacy_row(rec)
                except Exception:  # noqa: BLE001  (the ask's own failure is what the run reports)
                    pass
            raise
        rec['answered_by'] = ('constructor' if res['meta'].get('answered_by_constructor') else
                              'kernel' if res['meta'].get('solved_by_kernel') else 'model')
        return {**res, '_record': rec}

    def _solve_peek(self, s, env):
        """The ask's solve mode before it is evaluated (an ask can fail first): from a literal, a bare word, a `use`
        default or the host option, read without evaluating anything or recording a read. None for an expression,
        which the ask evaluates where it always did."""
        node = s.options.get('solve')
        if node is None:
            return _solve_mode(self.defaults['solve'] if 'solve' in self.defaults else self.opts.get('solve'))
        if not isinstance(node, S.Node) or node.k == 'lit':
            return _solve_mode(node.value if isinstance(node, S.Node) else node)
        if node.k == 'name':
            e = env
            while e is not None:
                if node.name in e.vars:
                    return _solve_mode(e.vars[node.name].value)
                e = e.parent
            return _solve_mode(node.name)
        return None

    def _ask_body(self, s, env: S.Env, ty: dict, index, feedback, rec, presentation='full') -> dict:
        # Construction can explicitly bypass speculative candidate evaluation. Resolve once per item:
        # options may read the current environment, including a for-each item's binding.
        determination = self._determination_enabled(s, env)
        if self._constructor is not None and determination:
            rec['_constructor'] = {'version': 1, 'kind': 'smt_linear', 'disposition': 'not_attempted',
                                   'reason': 'native_determination_enabled', 'dispatched': False,
                                   'replayed': False}
        if not determination:
            rec.update(status='unassessed', reason='author_disabled')
            solve = self._opt(s, 'solve', env)
            if solve:
                raise S.SymblicError('determine=false cannot be combined with solve; use solve=false',
                                     s.line, s.col, 'type')
        effort = str(self._opt(s, 'effort', env) or 'medium')
        if effort not in S.EFFORTS:
            raise S.SymblicError(f'effort must be one of {", ".join(S.EFFORTS)}', s.line, s.col)
        apps = self._apps(s, env)
        if not determination and all(a['engine'] == 'kernel' for a in apps):
            raise S.SymblicError('determine=false requires a model applicator; by=kernel needs determination',
                                 s.line, s.col, 'type')
        votes_opt = self._opt(s, 'votes', env)
        votes = int(votes_opt) if S.is_num(votes_opt) else S.VOTES_FOR_EFFORT[effort]
        votes = max(1, min(25, max(votes, len(apps))))
        if self.opts.get('override_by'):
            votes = len(apps)                       # one answer per probe applicator
        weight = self._weight(self._opt(s, 'weight', env), env)
        agree = self._opt(s, 'agree', env)
        threshold = float(agree) if S.is_num(agree) else 0.5
        strict = self.execution_profile == 'verified' or bool(self._opt(s, 'strict', env))
        retries = self._retries(s, env)
        budget = self._opt(s, 'budget', env)
        if budget is None:
            budget = DEFAULT_BUDGET
        if self.execution_profile == 'verified':
            if (type(budget) not in (int, Fraction) or budget != int(budget)
                    or not 0 <= budget <= 16 * 1024 * 1024):
                raise S.SymblicError('verified context budget must be an exact integer in 0..16777216',
                                     s.line, s.col, 'context')
        elif not S.is_num(budget) or budget != int(budget):
            self.warnings.append({'line': s.line, 'code': 'legacy_budget_coercion',
                                  'message': 'legacy context budget was defaulted or truncated; '
                                             'verified execution requires an exact integer'})
        budget = int(budget) if S.is_num(budget) else DEFAULT_BUDGET
        temperature = self.opts['override_temperature'] if 'override_temperature' in self.opts \
            else self._opt(s, 'temperature', env)
        seed = self._opt(s, 'seed', env)
        seed = int(seed) if S.is_num(seed) else 7
        vary = self._vary.get(id(s), 0)
        if vary:
            # an exact number: the sample planner keeps a program's own temperature only when it is one
            temperature = max(Fraction(temperature) if S.is_num(temperature) else Fraction(0), Fraction(3, 5))
            seed = seed + 1000 * vary
        tools = str(self._opt(s, 'tools', env) or 'none')
        automatic = self._automatic(s, env)
        route = 'escalate' if self.opts.get('certificate') is not None else str(self._opt(s, 'route', env) or 'vote').lower()
        if route not in ('vote', 'escalate', 'search'):
            raise S.SymblicError('route must be vote, escalate or search', s.line, s.col, 'type')

        text = ''.join(p if isinstance(p, str) else S.show(self.kernel.eval(p, env)) for p in s.parts)
        known, facts = self.context(s, env, text)
        # per-ask capsule inputs, passed down explicitly: `ask ... for each` runs items in threads, and shared
        # instance state gave one item another item's definitions (2026-10-02 semantics audit, R3)
        extras = {'definitions': self.definitions_for(text), 'examples': self.examples_for(s, ty, env),
                  'presentation': presentation}
        amb = 'report' if self.opts.get('override_ambiguous') else self._opt(s, 'ambiguous', env)
        amb = str(amb).lower() if amb not in (None, False) else ''
        if amb in ('true', 'yes', 'report'):
            amb = 'report'
        if amb not in ('', 'report', 'fail'):
            raise S.SymblicError('ambiguous must be true (report readings) or fail (stop when a reader finds two '
                                 'readings)', s.line, s.col)
        extras['readings'] = bool(amb)
        extras['coercion'] = self._opt(s, 'coercion', env) or (
            'strict' if self.execution_profile == 'verified' else 'legacy')
        if extras['coercion'] not in ('legacy', 'strict'):
            raise S.SymblicError('coercion must be legacy or strict', s.line, s.col, 'type')
        stmt_text = S.statement_source(s.name + (f'[{index}]' if index else ''), ty, text)
        if feedback is None:
            feedback = self.feedback.pop(id(s), '')
        extras['feedback_exposed'] = bool(feedback)
        exposed_check = self.feedback_checks.get(id(s)) if feedback else None
        if exposed_check is not None:
            # the answer-only accept line whose failed-check text this attempt's feedback shows the model
            extras['feedback_check'] = dict(exposed_check)
        extras['statement_sha256'] = E.digest([stmt_text, E.syntax(known), E.syntax(facts),
                                               extras['definitions'], extras['examples']])
        contract = self._contract(s)
        extras['oracle_sha256'] = E.digest([E.syntax(e.cond) for e in contract['ensures']]) if contract else ''

        assessment_budget = (_AssessmentBudget(self.kernel.budget, self.check_stop)
                             if determination and rec['solve_mode'] == 'off'
                             and any(a['engine'] != 'kernel' for a in apps) else None)
        left = self.kernel.budget.left
        try:
            det = self.determine(s, env, ty, budget=assessment_budget) if determination else None
        except S.KernelLimitError as exc:
            rec.update(status='unassessed', reason=(
                'budget' if self.kernel.budget.left < 0 else exc.limit))
            if index is None:
                self._determinacy_row(rec)
            raise
        except S.SymblicError as exc:
            if self.kernel.budget.left < 0 or exc.kind in ('resource', 'unavailable', 'budget'):
                rec.update(status='unassessed', reason=(
                    'budget' if self.kernel.budget.left < 0 else exc.kind))
                if index is None:
                    self._determinacy_row(rec)
            raise
        if determination:
            self._assess(rec, s, ty, det, left - self.kernel.budget.left)
        if det:
            self._trace(S.Node('determination', s.line, s.col), 'ok',
                        note=det['report']['verdict'], ask={'determination': det['report']})
        if index is None:
            self._determinacy_row(rec)              # for-each items: ask() writes theirs in item order
        if det and det['report']['exhaustive'] and det['accepted'] == 0:
            raise S.SymblicError(f'{s.name}: no value in the declared domain satisfies its encoded predicates',
                                 s.line, s.col, 'contradictory')
        if determination:
            solve = self._opt(s, 'solve', env)
        rec['solve_mode'] = _solve_mode(solve)
        if (det and det['report']['exhaustive'] and det['accepted'] == 1
                and (solve or all(a['engine'] == 'kernel' for a in apps))):
            value = det['unique']
            meta = {'effort': effort, 'votes': 0, 'apps': ['kernel'], 'rounds': 0, 'agreement': 1.0, 'distinct': 1,
                    'contested': False, 'calls': 0, 'samples': [], 'vote': 'kernel', 'determination': det['report'],
                    'solved_by_kernel': True, 'context': [k[0] for k in known], 'facts': len(facts)}
            meta['evidence'] = E.evidence([], source=self.source_sha256, line=s.line, name=s.name, ty=ty,
                                           determination=det['report'], value=value)
            return {'value': value, 'weight': weight, 'meta': meta}
        if all(a['engine'] == 'kernel' for a in apps):
            if det and det['accepted'] > 1:
                raise S.SymblicError(f'{s.name}: the written constraints permit several answers; witnesses '
                                     + S.show(S.from_json(det['report']['witnesses']))
                                     + '. Refine the contract to select one.', s.line, s.col, 'underdetermined')
            raise S.SymblicError('an ask needs a model applicator (by=...); the kernel only decides formal '
                                 'statements', s.line, s.col)
        if self._requested_by(s, env) == 'auto':
            # Keep the restriction even after a child environment is gone.
            protected = self._protected_acquired or any((b.meta.get('evidence') or {}).get('sensitivity') in
                            ('lab-confidential', 'confidential', 'mixed') for b in env.all().values())
            local_only = protected or (self.opts.get('auto_route') or {}).get('allow_cloud') is False
            if local_only:
                listed = len(apps)
                apps = [app for app in apps if app['engine'] in S.LOCAL_APPLICATOR_ENGINES]
                rec['_policy_cloud_refused'] = listed - len(apps)       # cloud rungs refused before any dispatch
                self._trace(S.Node('route-filter', s.line, s.col), 'ok', note=
                            'local only: protected acquisition in this run' if protected else
                            'local only: routing policy disallows cloud')
                if not apps:
                    raise S.SymblicError('automatic routing has no local candidate allowed for this data and policy',
                                         s.line, s.col, 'unavailable')
        def warned():
            return any(w.get('line') == s.line and w.get('code') == 'SYM_VACUOUS' for w in self.warnings)
        finding = (self.vacuity(s, env, ty, budget=assessment_budget) if determination and not warned()
                   and not (assessment_budget is not None and assessment_budget.exhausted) else None)
        if assessment_budget is not None and assessment_budget.exhausted:
            self._trace(S.Node('optional-assessment', s.line, s.col), 'unassessed',
                        note='optional assessment stopped at its allowance; returned answers still require checks',
                        extra={'name': s.name, 'reason': 'budget', **assessment_budget.record()})
        if finding:
            # the checks cannot tell an empty answer from a real one: say so once per statement
            row = {'line': s.line, 'code': 'SYM_VACUOUS', 'message': D.vacuous_message(s.name, finding['value'])}
            with self.lock:
                fresh = not warned()
                if fresh:
                    self.warnings.append(row)
            if fresh:
                self._trace(S.Node('vacuity', s.line, s.col), 'warn', note=row['message'])
        if self._constructor is not None and (route != 'vote' or automatic or s.each is not None):
            rec['_constructor'] = {'version': 1, 'kind': 'smt_linear', 'disposition': 'not_attempted',
                                   'reason': 'unsupported_each' if s.each is not None else 'unsupported_route',
                                   'dispatched': False, 'replayed': False}
        if route == 'search':
            return self._search(s, env, ty, apps, effort, known, facts, stmt_text, feedback, retries, budget,
                                temperature, seed, tools, extras, weight, det, rec=rec)
        if route == 'escalate' or automatic:
            return self._escalate(s, env, ty, apps, effort, known, facts, stmt_text, feedback, retries, budget,
                                  temperature, seed, tools, extras, weight, det, automatic=automatic, rec=rec)
        plan = [apps[i % len(apps)] for i in range(votes)]
        key_node = s.options.get('key')          # votes are grouped by key(it), a kernel expression
        ahead = self._opt(s, 'ahead', env)
        ahead = int(ahead) if S.is_num(ahead) and int(ahead) > 0 else 0
        vote = str(self._opt(s, 'vote', env) or 'auto').lower()
        if vote not in ('auto', 'whole', 'fields', 'median'):
            raise S.SymblicError('vote must be whole, fields, median or auto', s.line, s.col)
        permute = self._opt(s, 'permute', env)
        within = self._opt(s, 'within', env)
        if vote == 'median':
            if ty['k'] not in ('int', 'number'):
                raise S.SymblicError('vote=median needs a numeric answer', s.line, s.col, 'type')
            if key_node is not None:
                raise S.SymblicError('vote=median cannot be combined with key', s.line, s.col, 'type')
            if permute is not None:
                raise S.SymblicError('vote=median cannot be combined with permute', s.line, s.col, 'type')
        if within is not None:
            if vote != 'median':
                raise S.SymblicError('within needs vote=median', s.line, s.col, 'type')
            if isinstance(within, str):
                try:
                    within = S._coerce_num(within, 'within')
                except S.SymblicError:
                    pass
            if not S.is_num(within) or within < 0:
                raise S.SymblicError('within must be a number >= 0', s.line, s.col, 'type')
        rotations = 0
        if permute is not None:
            # the permutation probe: the same vote with the options listed in K rotated orders
            if not S.is_num(permute) or S.norm_num(permute) != int(permute) or not 2 <= int(permute) <= 6:
                raise S.SymblicError('permute must be an integer from 2 to 6', s.line, s.col, 'type')
            if not D.has_options(ty):
                raise S.SymblicError('permute needs an answer with a "one of"', s.line, s.col, 'type')
            if ahead:
                raise S.SymblicError('permute cannot be combined with ahead', s.line, s.col, 'type')
            if effort == 'ultra':
                # ultra's second round is asked in the written order and decides the value: no rotation chose it
                raise S.SymblicError('permute cannot be combined with effort=ultra', s.line, s.col, 'type')
            rotations = int(permute)
        if self._constructor is not None and not determination and not solve and s.each is None:
            built = self._constructor.attempt(s, ty, env, rec['occurrence'], rec)
            if built is not None:
                from symblic.constructor.core import decode
                value = decode(built['canonical'], ty)
                rec['_constructor'] = built['receipt']
                meta = {'effort': effort, 'votes': 0, 'apps': [], 'rounds': 0, 'agreement': None,
                        'distinct': None, 'contested': False, 'calls': 0, 'samples': [],
                        'answered_by_constructor': True, 'constructor': built['receipt'],
                        '_constructor_content': built['content'], '_constructor_validation': built['validation'],
                        'context': [], 'facts': 0}
                meta['evidence'] = E.evidence([], source=self.source_sha256, line=s.line,
                                             name=s.name, ty=ty, value=value)
                return {'value': value, 'weight': weight, 'meta': meta}
        rounds = []
        per_rotation = []
        if rotations:
            # same plan, seeds and temperatures for every rotation (offset 0): only the listed order differs
            samples = []
            orders = set()
            for r in range(rotations):
                rty = D.rotated(ty, r)
                order = json.dumps(S.json_schema(rty), sort_keys=True, default=str)
                if order in orders:
                    continue                    # fewer distinct orders than K: an order is asked once
                orders.add(order)
                rtext = S.statement_source(s.name + (f'[{index}]' if index else ''), rty, text)
                got = self._keyed(self._round(plan, s, rty, effort, known, facts, rtext, feedback, None, retries,
                                              budget, temperature, seed, tools, 1, extras=extras), key_node, env)
                for x in got:
                    x['rotation'] = r
                per_rotation.append(got)
                samples += got
        elif ahead:
            # MAKER's first-to-ahead-by-k: sample a batch at a time, stop once one answer leads by k
            samples, i = [], 0
            while i < len(plan):
                batch = plan[i:i + len(apps)]
                samples += self._keyed(self._round(batch, s, ty, effort, known, facts, stmt_text, feedback, None,
                                                   retries, budget, temperature, seed, tools, 1, offset=i,
                                                   extras=extras),
                                       key_node, env)
                i += len(batch)
                tally = S.consensus([x for x in samples if x.get('ok')], threshold)['tally']
                lead = tally[0]['count'] if tally else 0
                second = tally[1]['count'] if len(tally) > 1 else 0
                if lead - second >= ahead:
                    break
        else:
            samples = self._keyed(self._round(plan, s, ty, effort, known, facts, stmt_text, feedback, None, retries,
                                              budget, temperature, seed, tools, 1, extras=extras), key_node, env)
        for order, x in enumerate(samples):
            x['order'] = order
        rounds.append(samples)
        by_fields = ty['k'] == 'record' and key_node is None and (
            vote == 'fields' or (vote == 'auto' and sum(1 for x in samples if x.get('ok')) >= 3))

        def decide(xs):
            ok = [x for x in xs if x.get('ok')]
            if vote == 'median':
                return S.consensus_median(ok, threshold, within)
            return S.consensus_fields(ok, ty, threshold) if by_fields else S.consensus(ok, threshold)
        permutation = None
        if rotations:
            winners = [decide(xs) for xs in per_rotation]
            # a rotation with no valid answer, or with a contested vote, establishes nothing about the order
            missing = [r for r, w in enumerate(winners) if w['hash'] is None]
            weak = [r for r, w in enumerate(winners) if w['hash'] is not None and w.get('contested')]
            differ = len({w['hash'] for w in winners if w['hash'] is not None}) > 1
            permutation = {'rotations': len(per_rotation), 'stable': not (missing or weak or differ),
                           'complete': not missing, 'without_answer': missing, 'contested': weak,
                           'winners': [S.show(w['value'], 80) if w['hash'] is not None else None for w in winners]}
        result = decide(samples)
        if effort == 'ultra' and len(plan) > 1 and result['hash'] is not None:
            cands = []
            for row in result['tally'][:MOA_CANDIDATES]:
                why = next((x.get('why', '') for x in samples if x.get('hash') == row['hash'] and x.get('why')), '')
                cands.append((row['value'], _clip(why, 300)))
            samples2 = self._keyed(self._round(plan, s, ty, effort, known, facts, stmt_text, '', cands, retries,
                                               budget, temperature, seed, tools, 2, extras=extras), key_node, env)
            rounds.append(samples2)
            r2 = decide(samples2)
            if r2['hash'] is not None:
                result = r2
        if result['hash'] is None:
            errs = '; '.join(sorted({x.get('error', '') for x in rounds[-1] if x.get('error')}))[:600]
            raise RunFailed(S.SymblicError(f'no applicator gave a valid answer for {s.name}' +
                                           (f' ({errs})' if errs else ''), s.line, s.col, 'runtime'))
        if permutation is not None and not permutation['stable']:
            if differ:
                unstable = f'{s.name}: the answer changed with the order of the options'
            elif missing:
                unstable = (f'{s.name}: no valid answer with the options in order '
                            + ', '.join(str(r + 1) for r in missing) + f' of {len(per_rotation)}')
            else:
                unstable = (f'{s.name}: the vote was contested with the options in order '
                            + ', '.join(str(r + 1) for r in weak) + f' of {len(per_rotation)}')
            result = {**result, 'contested': True, 'unstable_order': True}
            if strict:
                raise RunFailed(S.SymblicError(unstable, s.line, s.col, 'check'))
            with self.lock:
                self.warnings.append({'line': s.line, 'message': unstable})
        fam_need = self._opt(s, 'families', env)
        if S.is_num(fam_need) and int(fam_need) > 1 and len(result.get('families') or []) < int(fam_need):
            # errors within one model family are correlated: agreement counts only across families (R11)
            result = {**result, 'contested': True,
                      'families_short': f'{len(result.get("families") or [])} of {int(fam_need)} families'}
        if result['contested'] and strict:
            why = ('a tie between the top answers' if result.get('tied') else
                   f'the winning answer has {result["families_short"]}' if result.get('families_short') else
                   f'agreement {result["agreement"]:.0%} < {threshold:.0%}')
            raise RunFailed(S.SymblicError(f'{s.name}: the applicators did not agree ({why})', s.line, s.col, 'check'))
        flagged = [x for x in rounds[0] if x.get('ok') and x.get('readings')]
        ambiguity = None
        if amb:
            seen = []
            for x in flagged:
                for r in x['readings']:
                    if r not in seen:
                        seen.append(r)
            ambiguity = {'flagged': len(flagged), 'of': sum(1 for x in rounds[0] if x.get('ok')),
                         'by': [x['app'] for x in flagged], 'readings': seen[:12]}
            if amb == 'fail' and flagged:
                raise RunFailed(S.SymblicError(
                    f'{s.name}: {len(flagged)} reader(s) found more than one reading: ' + '; '.join(seen[:6]),
                    s.line, s.col, 'ambiguous'))
        synthesized = by_fields and not any(x.get('ok') and x.get('hash') == result['hash'] for x in rounds[-1])
        meta = {'effort': effort, 'votes': votes, 'apps': [S.app_label(a) for a in apps], 'rounds': len(rounds),
                'synthesized': synthesized,
                **({'determination': det['report']} if det else {}),
                'ahead': ahead or None,
                'agreement': result['agreement'], 'distinct': result['distinct'], 'contested': result['contested'],
                'vote': 'median' if vote == 'median' else 'fields' if by_fields else 'whole',
                **({'agreement_whole': result.get('agreement_whole'), 'fields': result.get('fields')}
                   if by_fields else {}),
                **({'within': result.get('within'), 'spread': result.get('spread')} if vote == 'median' else {}),
                **({'permutation': permutation} if permutation is not None else {}),
                **({'unstable_order': True} if result.get('unstable_order') else {}),
                'entropy': result.get('entropy', 0.0), 'entropy_bits': result.get('entropy_bits', 0.0),
                'families': result.get('families', []), 'tally': result['tally'],
                **({'ambiguity': ambiguity} if ambiguity is not None else {}),
                'calls': sum(len(r) for r in rounds),
                'key': S.show(key_node.name) if key_node is not None and key_node.k == 'name' else
                ('kernel expression' if key_node is not None else None),
                'samples': [{'app': x['app'], 'round': x['round'], 'ok': x.get('ok', False), 'hash': x.get('hash'),
                             'keyed': x.get('keyed'),
                             'value': S.show(x['value'], 160) if x.get('ok') else None, 'error': x.get('error', ''),
                             'ms': x.get('ms', 0), 'node': x.get('node', ''), 'attempts': x.get('attempts', 1),
                             'cached': x.get('cached', False),
                             **({'rotation': x['rotation']} if 'rotation' in x else {}),
                             **({'readings': x['readings']} if x.get('readings') else {})} for r in rounds for x in r],
                'context': [k[0] for k in known], 'facts': len(facts)}
        meta['evidence'] = E.evidence([x['observation'] for r in rounds for x in r if x.get('observation')],
                                      source=self.source_sha256, line=s.line, name=s.name, ty=ty,
                                      determination=det['report'] if det else None, value=result['value'])
        if index:
            meta['index'] = index
        if synthesized:
            whole = S.consensus([x for x in rounds[-1] if x.get('ok')], threshold)
            meta['_whole_value'] = whole['value']      # used only if a whole-record ensure rejects the assembly
        return {'value': result['value'], 'weight': weight, 'meta': meta}

    def _keyed(self, samples: list, key_node, env) -> list:
        """With `key=EXPR`, each valid answer is grouped by the fingerprint of EXPR evaluated with `it` bound
        to it (e.g. key=eval(it): two formulas with the same value agree). An answer the kernel cannot key
        is discarded before the vote — a red flag decided by code, not by a model."""
        if key_node is None:
            return samples
        for x in samples:
            if not x.get('ok'):
                continue
            child = S.Env(env)
            child.vars['it'] = S.Binding('it', x['value'], meta={'_epistemic_internal_trial': True})
            try:
                k = self.kernel.eval(key_node, child)
            except S.SymblicError as e:
                x.update({'ok': False, 'error': f'red flag: key failed ({e.message})', 'value': x['value']})
                continue
            x['hash'] = S.fingerprint(k)
            x['keyed'] = S.show(k, 120)
        return samples

    def _round(self, plan, s, ty, effort, known, facts, stmt_text, feedback, candidates, retries, budget,
               temperature, seed, tools, round_no, offset: int = 0, extras=None) -> list:
        extras = extras or {}
        caps = {}
        for native in sorted({a['engine'] in S.NATIVE_REASONING for a in plan}):
            caps[native] = S.capsule(self.program, min(self.no, self.total) or 1, self.total or 1, stmt_text, ty,
                                     effort, known, facts, candidates=candidates, feedback=feedback, budget=budget,
                                     native=native, definitions=extras.get('definitions'),
                                     examples=extras.get('examples'), readings=bool(extras.get('readings')),
                                     profile=self.execution_profile, presentation=extras.get('presentation', 'full'))
            self._context_warnings(s, caps[native])

        def run_sample(i_app):
            i, app = i_app
            i += offset
            # a program's temperature is an exact number (7/10); applicators and the replay key take a plain float,
            # and 0.7 from a program keys the same as the default 0.7 (2026-10-02 helper report)
            temp = _plain_number(temperature) if S.is_num(temperature) else (0 if i == 0 else 0.7)
            cap = caps[app['engine'] in S.NATIVE_REASONING]
            return self._sample(app, cap, ty, s, i, temp, seed + i, retries, effort, tools, round_no,
                                 provenance=extras)

        workers = min(self.parallel, len(plan))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            out = list(pool.map(run_sample, enumerate(plan)))
        for order, x in enumerate(out):
            x['order'] = order + offset
        return out

    def _context_warnings(self, s, cap) -> None:
        """Surface the capsule's context warnings (SYM_CONTEXT_OMITTED) once per statement line."""
        for row in cap.get('warnings') or ():
            with self.lock:
                if not any(w.get('line') == s.line and w.get('code') == row.get('code') for w in self.warnings):
                    self.warnings.append({'line': s.line, **row})

    def _sample(self, app, cap, ty, s, i, temperature, seed, retries, effort, tools, round_no,
                validate=None, provenance=None, repair_gate=None, cancel=None, on_attempt=None, tally=None) -> dict:
        if app.get('member'):
            from symblic.providers import agent_teams as teams
            member = teams.normalize_member(app['member'])
            # Copy the capsule: concurrent members must never share mutable profile state.
            system = teams.member_system(member, cap['system'])
            manifest = {**(cap.get('context_manifest') or {}),
                        'member': member, 'member_sha256': teams.digest(member)}
            if type(manifest.get('fixed_size')) is int:
                manifest['fixed_size'] += len(system) - len(cap['system'])
            cap = {**cap, 'system': system, 'context_manifest': manifest}
            temperature = member['settings'].get('temperature', temperature)
            seed = member['settings'].get('seed', seed)
        prompt = cap['prompt']
        attempts = 0
        last_error = ''
        observations = []
        provenance = provenance or {}
        code = ty.get('k') == 'code'
        prev_hash = None                  # the last rejected answer's fingerprint (identical repeats vary the sampling)
        varied = 0
        while attempts <= retries:
            self.check_stop()
            if cancel is not None and cancel.is_set():
                last_error = last_error or 'cancelled: a lower candidate was accepted'
                break
            if attempts and repair_gate is not None and not repair_gate():
                break
            attempts += 1
            manifest = dict(cap.get('context_manifest') or {})
            schema_text = json.dumps(cap['schema'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            actual_size = len(cap['system']) + len(prompt) + len(schema_text)
            if self.execution_profile == 'verified' and actual_size > manifest.get('budget', DEFAULT_BUDGET):
                raise S.SymblicError('required context, fixed prompt and repair text exceed the verified '
                                     'context budget; no further model call was made', s.line, s.col, 'context')
            manifest.update({'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
                             'system_sha256': hashlib.sha256(cap['system'].encode('utf-8')).hexdigest(),
                             'request_characters': actual_size,
                             'repair_suffix_characters': len(prompt) - len(cap['prompt'])})
            if self.execution_profile == 'verified':
                manifest['used'] = actual_size
            reply = self._call(app, cap['system'], prompt, cap['schema'], i + (round_no - 1) * 100 + (attempts - 1) * 1000,
                               temperature, seed, effort, tools, s,
                               context_manifest=manifest,
                               **({'repair': True} if attempts > 1 and repair_gate is not None else {}),
                               **({'stop': _EitherStop(self.stop, cancel)} if cancel is not None else {}),
                               **({'tally': tally} if tally is not None else {}))
            if cancel is not None and cancel.is_set():
                # a search accepted another candidate meanwhile: its in-flight call was cancelled; nothing to check
                last_error = 'cancelled: another candidate was accepted'
                break
            if not reply.get('ok'):
                last_error = reply.get('error') or 'no answer'
                # refused by the launcher: asking this engine again gets the same refusal, and no model was asked
                if reply.get('refused') is True:
                    attempts -= 1
                    break
                if on_attempt is not None:
                    on_attempt(attempts, False)
                if reply.get('fatal'):
                    break
                continue
            try:
                # a Code answer is the reply's own text (a JSON-looking object inside code is not an answer object)
                transformation = {}
                value, why = S.read_answer(reply.get('text') if 'json_schema' in ty else
                                           reply.get('text') or reply.get('json') or '' if ty.get('k') == 'code' else
                                           reply.get('json') if reply.get('json') is not None else reply.get('text', ''),
                                           ty, coercion=provenance.get('coercion', 'legacy'), receipt=transformation)
            except S.SymblicError as e:
                if e.kind in ('resource', 'unavailable', 'budget', 'version'):
                    raise  # incomplete validation is not model-quality evidence or a repair opportunity
                last_error = e.message
                if on_attempt is not None:
                    on_attempt(attempts, False)
                prompt = cap['prompt'] + (f'\nYOUR PREVIOUS REPLY WAS NOT VALID: {e.message}. ' +
                                          ('Reply again with one raw JSON document matching the schema, without a fence or wrapper.\n' if 'json_schema' in ty else
                                           'Reply again with the whole code in one fenced block.\n' if code else
                                           'Reply again with only the JSON object.\n'))
                continue
            readings = S.read_readings(reply.get('json') if reply.get('json') is not None else reply.get('text', ''))
            obs = E.observation(app, reply, value, request=reply.get('_request_sha256', ''),
                                capsule=E.digest([cap['system'], prompt, cap['schema']]), round_no=round_no,
                                statement=provenance.get('statement_sha256', ''), attempt=attempts,
                                feedback_exposed=attempts > 1 or provenance.get('feedback_exposed', False),
                                oracle=provenance.get('oracle_sha256', '') if
                                (validate is not None and attempts > 1) or provenance.get('feedback_exposed') else '',
                                readings=readings)
            obs['transformation'] = transformation
            obs['context_manifest'] = manifest
            this_hash = S.fingerprint(value)
            if prev_hash is not None and this_hash == prev_hash:
                # A small model at temperature 0 often answers a repair with the very same code (the 2026-10-11
                # gemma3:1b runs: three identical replies). Repeating the identical request is no regeneration:
                # the next attempt samples differently (temperature at least 0.6, a new seed), and the record
                # says so. The call key carries both values, so replay stays exact.
                varied += 1
                temperature = max(Fraction(temperature) if S.is_num(temperature) else Fraction(0), Fraction(3, 5))
                seed = seed + 1000 * attempts
                obs['identical_repeat'] = True
            obs['sampling'] = {'temperature': _plain_number(temperature) if S.is_num(temperature) else temperature,
                               'seed': seed, 'varied': varied}
            prev_hash = this_hash
            if provenance.get('feedback_check'):
                # an answer-only accept line is model-readable on this attempt: named, like feedback_exposed,
                # as recorded exposure, not as a claim that the expected answer is unknowable
                obs['feedback_check'] = dict(provenance['feedback_check'])
            observations.append(obs)
            if validate is not None:
                valid, message = validate(value, readings)
                obs['constraint_passed'] = valid
                if not valid:
                    last_error = message
                    if on_attempt is not None:
                        on_attempt(attempts, False)
                    if 'json_schema' in ty:
                        prompt = cap['prompt'] + (f'\nCHECK REJECTED ATTEMPT {attempts}: {message}. '
                                                  'Return a corrected raw JSON document matching the same schema.\n')
                    elif code:
                        fence = ty.get('lang') or ''
                        again = ('\nYour last two replies were identical. Change the code where the check failed; '
                                 'do not repeat it.\n' if obs.get('identical_repeat') else '')
                        prompt = cap['prompt'] + (f'\nCHECK REJECTED ATTEMPT {attempts}. Your code was:\n```{fence}\n'
                                                  f'{value[:CODE_FEEDBACK_CHARS]}\n```\nIt failed the check: {message}\n'
                                                  f'Write the corrected, complete code in one fenced block.\n' + again)
                    else:
                        prompt = cap['prompt'] + (f'\nCHECK REJECTED ATTEMPT {attempts}: {S.show(value, 200)}. '
                                                  f'{message}. Return a corrected JSON answer.\n')
                    continue
            if on_attempt is not None:
                on_attempt(attempts, True)
            return {'ok': True, 'value': value, 'hash': S.fingerprint(value), 'why': why, 'app': S.app_label(app),
                    'lineage': S.lineage_label(S.app_label(app), reply.get('model'))[0],
                    'readings': readings,
                    'observation': obs, 'observations': observations,
                    'weight': app.get('weight', 1.0), 'weight_exact': app.get('weight_exact'),
                    'ms': reply.get('ms', 0), 'node': reply.get('node', ''),
                    'attempts': attempts, 'round': round_no, 'cached': reply.get('cached', False)}
        return {'ok': False, 'error': last_error[:400], 'app': S.app_label(app), 'attempts': attempts,
                'round': round_no, 'observations': observations}

    def _reserve_ollama_time(self):
        """Persist the first-dispatch deadline before launch; called under the run lock.

        Wall time survives a resume; monotonic time also limits this process if
        the clock moves backwards. A backward clock between dispatches refuses.
        Cached replies never spend or restart this budget.
        """
        now = time.time()
        row = self._ollama_budget or {'version': 1, 'source_sha256': self.source_sha256,
                                     'limits': self.ollama_limits, 'started': now, 'last_seen': now}
        if now < row['last_seen']:
            raise S.SymblicError('clock moved backwards during the Ollama budget; start a new run', kind='budget')
        total = self.ollama_limits.get('total_timeout_seconds')
        remaining = None
        if total is not None:
            remaining = row['started'] + total - now
            if self._ollama_deadline is None:
                self._ollama_deadline = time.monotonic() + max(0, remaining)
            remaining = min(remaining, self._ollama_deadline - time.monotonic())
            if math.ceil(remaining) < 30:
                raise S.SymblicError('the total Ollama time budget has no remaining 30-second request slot',
                                     kind='budget')
        row = {**row, 'last_seen': now}
        self.store.save('ollama-budget.json', row, durable=True)
        self._ollama_budget = row
        return now + remaining if remaining is not None else None

    def _call(self, app, system, prompt, schema, sample, temperature, seed, effort, tools, s, repair=False,
              stop=None, context_manifest=None, tally=None) -> dict:
        engine_effort = app['member']['effort'] if app.get('member') else app.get('effort') or _engine_effort(effort)
        context_identity = None
        if (context_manifest or {}).get('presentation') == 'compact':
            context_identity = context_manifest.get('context_identity_sha256')
            if type(context_identity) is not str or not re.fullmatch(r'[0-9a-f]{64}', context_identity):
                raise S.SymblicError('compact capsule is missing its exact context identity; no model was called',
                                     s.line, s.col, 'context')
        limits = self.ollama_limits if app['engine'] == 'ollama' else {}
        key = call_key(app, system, prompt, schema, sample, temperature, seed, engine_effort, tools,
                       context_identity=context_identity, ollama_limits=limits)
        def recorded(reply):
            clean = {k: v for k, v in reply.items() if k in
                     ('ok', 'json', 'text', 'error', 'fatal', 'refused', 'ms', 'node', 'model', 'meta')}
            self.store.append('call-events.jsonl', {'execution_id': self.execution_id, 'key': key,
                              'app': S.app_label(app), 'line': s.line, 'stmt': s.name,
                              'sample': sample, 'reply': clean, 'context_manifest': context_manifest})
            return {**reply, '_request_sha256': key}
        if self.opts.get('replay') and key in self.store.replay_calls:
            with self.lock:
                sequence = self.store.replay_calls[key]
                reply = sequence.pop(0) if sequence else None
                if reply is not None:
                    self.cached += 1
            if reply is not None:
                if tally is not None:
                    tally['cached'] += 1
                return recorded({**reply, 'cached': True})
            # A consumed sequence never falls back to its last successful reply.
            hit = None
        else:
            hit = self.store.calls.get(key)
        if hit is not None:
            # A recorded answer is an active decision too: its identity is checked again now (D4), never trusted
            # from the label it was stored with. Refused, it is not asked again either: the sample fails.
            with self._identity_lock:
                if 'model_identity_raw' in hit:
                    _label, refusal, rows = self._identity_decision(app, s, hit['model_identity_raw'],
                                                                    hit.get('model_identity_raw_truncated') is True,
                                                                    cached=True)
                else:
                    refusal, rows = self._unlabelled_refusal(app, s, cached=True)
            self._queue_rows(rows)
            if refusal is not None:
                return recorded({'ok': False, 'fatal': True, 'error': refusal, 'cached': True})
            with self.lock:
                self.cached += 1
            if tally is not None:
                tally['cached'] += 1
            return recorded({**hit.get('reply', {}), 'cached': True})
        if self.apps is None:
            return {'ok': False, 'error': 'no applicators are connected', 'fatal': True}
        with self.lock:
            if self.calls >= self.max_calls:
                raise S.SymblicError(f'the program exhausted its model-call budget ({self.max_calls})',
                                     s.line, s.col, 'budget')
            deadline = self._reserve_ollama_time() if limits else None
            if isinstance(self.opts.get('auto_route'), dict) and not self.opts.get('replay'):
                try:
                    usage = self.store.reserve_model_call(self.source_sha256, self.max_calls,
                                                          self.opts['auto_route'].get('repairs', 0), repair)
                except S.SymblicError as exc:
                    if 'unreadable' in exc.message or 'invalid' in exc.message:
                        self.calls_total = self.repairs_total = None
                    raise
                if usage is not None:
                    self.calls_total, self.repairs_total = usage['calls'], usage['repairs']
                    if usage.get('refused_repair'):
                        return recorded({'ok': False, 'fatal': True,
                                         'error': 'automatic correction budget exhausted across resumes'})
            self.calls += 1
            self.calls_total = max(self.calls_total or 0, self.calls)
        req = {'app': app, 'system': system, 'prompt': prompt, 'schema': schema, 'sample': sample,
               # a plain number on the wire: a varied retry carries an exact Fraction, which the launcher's JSON
               # cannot serialize (gemma3:1b run, 2026-10-11)
               'temperature': _plain_number(temperature) if S.is_num(temperature) else temperature,
               'seed': int(seed) if S.is_num(seed) else seed, 'effort': engine_effort,
               'tools': tools, 'key': key, 'stop': stop if stop is not None else self.stop,
               'context_manifest': context_manifest}
        if limits:
            req['ollama_limits'] = dict(limits)
            if deadline is not None:
                req['deadline'] = deadline
        if app.get('member'):
            self.store.team_attempt(key, app['member'])
        t0 = time.time()
        try:
            reply = self.apps.call(req) or {}
        except MemoryError:
            raise  # an interpreter resource failure is not a provider abstention or a repair opportunity
        except S.SymblicError as e:
            if e.kind in ('resource', 'unavailable', 'budget'):
                raise
            reply = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
        except Exception as e:  # noqa: BLE001  (one applicator failing is an abstention, not a crash)
            reply = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
        reply.setdefault('ms', _ms(t0))
        refused = reply.get('refused') is True and not reply.get('ok')
        if refused:
            # the applicators said no before any model saw the prompt (a model that is not installed, a launcher's
            # admission refusal): the call goes back to the budget, so refusals cannot use up a route before it
            # reaches an engine that answers (a refused, oversized local model was once charged as one of 6 calls)
            with self.lock:
                self.calls = max(0, self.calls - 1)
                if repair:
                    self.auto_repairs_left += 1
                if isinstance(self.opts.get('auto_route'), dict) and not self.opts.get('replay'):
                    usage = self.store.release_model_call(self.source_sha256, repair)
                    if usage is not None:
                        self.calls_total, self.repairs_total = usage['calls'], usage['repairs']
                else:
                    self.calls_total = self.calls
        else:
            reply.pop('refused', None)
        if tally is not None:
            tally['refused' if refused else 'dispatched'] += 1
        row = {'key': key, 'ok': bool(reply.get('ok')), 'app': S.app_label(app), 'line': s.line, 'stmt': s.name,
               'source_sha256': self.source_sha256, 'repair': repair,
               'sample': sample, 'ms': reply.get('ms'), 'at': round(time.time(), 3),
               'reply': {k: v for k, v in reply.items() if k in ('ok', 'json', 'text', 'error', 'fatal', 'refused', 'ms',
                                                                  'node', 'model', 'meta')}}
        if limits:
            row['ollama_limits'] = dict(limits)
        # D4: the provider's evidence, kept as received (bounded) beside the answer; the label is history only
        if 'model_identity' in reply:
            row['model_identity_raw'], cut = _bounded_json(reply['model_identity'], IDENTITY_RAW_CHARS)
            if cut:
                row['model_identity_raw_truncated'] = True
        if 'usage' in reply:
            row['usage'], cut = _bounded_json(reply['usage'], USAGE_CHARS)
            if cut:
                row['usage_truncated'] = True
        rows = []
        with self._identity_lock:          # pins follow the order of calls.jsonl, so the decision and the row go together
            refusal = None
            if 'model_identity_raw' in row:
                label, refusal, rows = self._identity_decision(app, s, row['model_identity_raw'],
                                                               row.get('model_identity_raw_truncated') is True,
                                                               cached=False, counted=not refused,
                                                               answered=row['ok'])
                row['identity_check_at_call'] = label
            elif row['ok']:
                refusal, rows = self._unlabelled_refusal(app, s, cached=False)
            if refusal is not None and row['ok']:
                # model_pins=strict: refused before it is accepted or cached; the model's answer is not kept
                reply = {**{k: v for k, v in reply.items() if k in ('ms', 'node', 'model', 'meta')},
                         'ok': False, 'fatal': True, 'error': refusal}
                row['ok'], row['reply'] = False, dict(reply)
            if row['ok']:
                self.store.calls[key] = row
            self.store.append('calls.jsonl', row, durable=bool(app.get('member')))
        if app.get('member'):
            self.store.team_attempt(key, app['member'], outcome=reply)
        self._queue_rows(rows)
        self.say(f'    {S.app_label(app)} {"ok" if row["ok"] else "failed: " + str(reply.get("error", ""))[:120]} '
                 f'({reply.get("ms", 0)} ms)')
        return recorded(reply)

    # -- model identity (D4): observed manifest digests, checked now, pinned per applicator per folder ---------------
    def _strict_pins(self) -> bool:
        """The validated host policy is model_pins=strict: an answer is accepted only with an observed, freshly
        validated manifest digest equal to the folder's pin (or pinning it). An invalid policy never reads as observe
        (execute() refuses it; any other path fails closed). Not in a lock replay, whose answers come from the lock
        and are not new model observations."""
        return self.model_pins != 'observe' and not self.opts.get('replay')

    def _pins(self) -> dict:
        """applicator label -> the first observed, validated digest in this folder's calls.jsonl (checked now, in
        file order), then this execution's own calls. Call with self._identity_lock held."""
        if self._identity_pins is None:
            pins: dict = {}
            check, _version = _identity_checker()
            for label, raw, cut in self.store.identity_rows:
                app = _label_app(label)
                if app is None:
                    continue
                _status, digest, _why = _identity_status(raw, cut, check, app)
                if digest is not None:
                    pins.setdefault(label, digest)
            self._identity_pins = pins
        return self._identity_pins

    def _identity_decision(self, app, s, raw, cut, *, cached, counted=True, answered=True) -> tuple:
        """(label for identity_check_at_call, strict refusal text or None, trace rows to queue) for one call's
        model_identity record, validated freshly by symblic.providers.ollama_call.check. Only an observed validated digest that
        names this applicator pins; a later different one for the same applicator is drift (recorded, or refused under
        strict pins). Under strict pins every other identity is refused too, on the first call as on any other:
        unavailable, the helper's drift, invalid, unverifiable. Call with self._identity_lock held."""
        check, version = _identity_checker()
        status, digest, unproven = _identity_status(raw, cut, check, app)
        label = S.app_label(app)
        strict = self._strict_pins()
        pins = self._pins()
        pinned = pins.get(label)
        drift = None
        holds_pin = False
        if digest is not None and counted:
            if pinned is None:
                pins[label] = digest
                holds_pin = True
            elif pinned == digest:
                holds_pin = True
            else:
                drift = {'line': s.line, 'applicator': label, 'pinned': pinned, 'observed': digest, 'cached': cached,
                         'action': 'recorded'}
        elif digest is not None:
            holds_pin = pinned == digest
        refusal = None
        if strict and answered and counted:
            # accepted ONLY with an observed, freshly validated digest naming this applicator, equal to its pin (or
            # the first pin); everything else is refused before the answer is accepted or cached
            if drift is not None:
                refusal = (f'{label}: answer refused under model_pins=strict: the observed manifest digest {digest} '
                           f'differs from the pinned {pinned}')
            elif status != 'observed':
                refusal = f'{label}: answer refused under model_pins=strict ({status} identity): {unproven}'
        rows = []
        if counted:
            if drift is not None:
                drift['action'] = 'refused' if refusal is not None else 'recorded'
                rows.append(('model-drift', s, drift['action'],
                             f'{label} listed {digest} where this folder pinned {pinned}'
                             + (' (cached answer)' if cached else '') + f': {drift["action"]}',
                             {'name': s.name, **drift}))
            elif refusal is not None:
                rows.append(('model-identity', s, 'refused', refusal,
                             {'name': s.name, 'applicator': label, 'identity': status, 'cached': cached}))
            self._identity_events.append({'app': label, 'status': status, 'digest': digest, 'drift': drift,
                                          'cached': cached})
        return ({'checker': IDENTITY_CHECKER, 'checker_version': version,
                 'validated': status in ('observed', 'drift', 'unavailable'), 'pinned': holds_pin, 'strict': strict,
                 'refused': refusal is not None}, refusal, rows)

    def _unlabelled_refusal(self, app, s, *, cached) -> tuple:
        """(refusal or None, trace rows). Under strict pins, an answer that carries no model_identity record at all
        (an older folder's row, an applicator without the ABI) cannot be shown to match, and is refused."""
        if not self._strict_pins():
            return None, []
        label = S.app_label(app)
        refusal = f'{label}: answer refused under model_pins=strict: it carries no model identity record'
        return refusal, [('model-identity', s, 'refused', refusal,
                          {'name': s.name, 'applicator': label, 'identity': None, 'cached': cached})]

    def _queue_rows(self, rows) -> None:
        if rows:
            with self._receipts_lock:
                self._queued_rows.extend(rows)

    def _write_queued_rows(self) -> None:
        """Trace rows observed in worker threads, written from the run's thread in the order they were observed
        (unique sequence numbers; _trace is not called from those threads for them)."""
        with self._receipts_lock:
            rows, self._queued_rows = self._queued_rows, []
        for kind, s, status, note, extra in rows:
            self._trace(S.Node(kind, s.line, s.col), status, note=note, extra=extra)

    # -- context: what an applicator may see ------------------------------------------------
    def context(self, s, env: S.Env, text: str):
        """(known rows, facts) for one ask under its context policy, highest weight first."""
        policy = self._opt(s, 'context', env)
        names = list(s.sources)
        visible = [b for b in env.all().values() if not b.hidden and b.name not in self.groups]
        chosen: list = []
        facts: list = []
        mode = 'none'
        if isinstance(policy, tuple):
            names += [str(x) for x in policy]
        elif isinstance(policy, str):
            mode = policy.strip().lower()
        if mode in ('all', 'inherit', 'continue', 'append'):
            chosen = [b for b in visible if b.weight > 0]
        elif mode.startswith('last'):
            n = int(mode.split()[1]) if len(mode.split()) > 1 else 3
            chosen = sorted([b for b in visible if b.weight > 0], key=lambda b: b.order)[-n:]
        elif mode == 'relevant':
            chosen = _relevant(visible, text, 6)
        elif mode == 'facts':
            facts = self.kernel.kb.all_facts(derived=True) if self.kernel.kb._derived else self.kernel.kb.all_facts()
        elif mode not in ('none', 'clear', 'fresh', ''):
            raise S.SymblicError(f'unknown context {mode!r} (none, all, last N, relevant, facts, or [names])', s.line,
                                 s.col)
        if mode in ('all', 'inherit', 'continue', 'append') and self.kernel.kb.fact_count():
            facts = self.kernel.kb.all_facts()
        if facts:
            self._knowledge_read()
            knowledge_roots = set()
            for premise in self._epistemic_knowledge:
                knowledge_roots |= self._root_ids(self._claim_for_binding(premise)['claim']['id'])
            roots = self._root_rows(knowledge_roots)
            provenance = {'dependency_scope': 'conservative_all_declared_knowledge',
                          'empirical_truth': 'not_established', 'conditional_root_count': len(roots),
                          'conditional_roots_sha256': E.digest(roots),
                          'root_origins': sorted({root['origin'] for root in roots})}
            facts = [{'text': fact, 'provenance': provenance} for fact in facts]
        for name in names:
            b = env.lookup(name)
            if b is None:
                raise S.SymblicError(f'{name} is not bound (from/context names must be bound first)', s.line, s.col,
                                     'name')
            if b not in chosen:
                chosen.append(b)
        chosen.sort(key=lambda b: (-b.weight, b.order))
        rows = []
        for binding in chosen:
            evidence = self._claim_for_binding(binding, parents=[b for b in self._read_bindings() if b is not binding])
            claim, view = evidence['claim'], evidence['assessment']
            # every root, also those a long lineage's bounded view does not list (epistemic-3)
            roots = self._root_rows(self._root_ids(claim['id']))
            info = {'required': binding.name in names, 'claim': self._epistemic_ref(claim),
                    'value_sha256': claim['content']['value_sha256'],
                    'prompt': {'origin': claim['origin'], 'status': view['status'],
                               'support': view['support'], 'empirical_truth': 'not_established',
                               'claim_sha256': claim['sha256'], 'value_sha256': claim['content']['value_sha256'],
                               'conditional_root_count': len(roots), 'conditional_roots_sha256': E.digest(roots),
                               'root_origins': sorted({root['origin'] for root in roots}),
                               'lineage_complete': view.get('lineage_complete', True)}}
            rows.append((binding.name, S.type_label(binding.type) if binding.type else S.type_name(binding.value),
                         _known_text(binding.value), binding.weight, info))
        return rows, facts

    def _contract(self, s):
        plan = self._checks.get(id(s))
        if not plan or s.each is not None or not plan['ensures']:
            return None
        # Speculation must never invoke a routine, extension, effect or another model.
        # User functions may transitively call routines, so this first contract
        # evaluator deliberately accepts only the kernel's builtins.
        if any(t.k not in ('let', 'ensure') for t in plan['between']):
            return None
        nodes = [t.value for t in plan['between'] if t.k == 'let']
        nodes += [e.cond for e in plan['ensures']]
        def pure(obj):
            if isinstance(obj, S.Node):
                if obj.k == 'call' and obj.fn not in S.BUILTINS:
                    return False
                return all(pure(v) for v in vars(obj).values())
            if isinstance(obj, dict):
                return all(pure(v) for v in obj.values())
            if isinstance(obj, (tuple, list)):
                return all(pure(v) for v in obj)
            return True
        return plan if all(pure(n) for n in nodes) else None

    def _speculable(self, plan) -> bool:
        """Whether a contract may be evaluated speculatively (empty-answer probes, enumeration): not when it runs an
        outside process (S.SPECULATION_DENIED). Validating a real candidate still runs it."""
        def free(obj):
            if isinstance(obj, S.Node):
                if obj.k == 'call' and obj.fn in S.SPECULATION_DENIED:
                    return False
                return all(free(v) for v in vars(obj).values())
            if isinstance(obj, dict):
                return all(free(v) for v in obj.values())
            if isinstance(obj, (tuple, list)):
                return all(free(v) for v in obj)
            return True
        return free([t.value for t in plan['between'] if t.k == 'let'] + [e.cond for e in plan['ensures']])

    def _candidate(self, s, env, value, plan, explain=False, budget=None):
        """Check a hypothetical answer without mutating the run or calling an extension. With `explain`, a
        failing predicate's message says what the kernel computed from the answer alone (D.explain)."""
        child = S.Env(env)
        child.vars[s.name] = S.Binding(s.name, value, meta={'_epistemic_internal_trial': True})
        kb = S.KB()
        kb.facts = {p: set(ts) for p, ts in self.kernel.kb.facts.items()}
        kb.rules = list(self.kernel.kb.rules)
        kernel = S.Kernel(child, kb, budget if budget is not None else self.kernel.budget)
        kernel.knowledge_read = self._knowledge_read
        kernel.knowledge_predicate_read = self._knowledge_read
        checks = {id(e) for e in plan['ensures']}
        steps = list(plan['between'])
        steps.extend(e for e in plan['ensures'] if not any(e is t for t in steps))
        prior = []
        for t in steps:
            self.check_stop()
            if t.k == 'let':
                if child.has_local(t.name):
                    return False, f'duplicate binding {t.name}'
                val = kernel.eval(t.value, child)
                if t.type is not None:
                    val = S.check_value(val, S.resolve_type(t.type, self.types, t.line), t.name)
                child.vars[t.name] = S.Binding(t.name, val, meta={'_epistemic_internal_trial': True})
                prior.append(t)
            elif id(t) in checks and not S._truth(kernel.eval(t.cond, child), t.cond):
                why = ''
                if explain and t.because is not None:
                    # the author's own message, used as written (SPEC §5), as the ensure-retry path does
                    try:
                        why = S.show(kernel.eval(t.because, child))
                    except S.SymblicError:
                        why = ''
                detail = _bounded_explanation(t.cond, child, kb,
                    D.derived_names(s.name, prior, env)) if explain else ''
                if why:
                    return False, (f'failed encoded predicate: {_src(t)}\n{why}'
                                   + (f'\nIn the last answer: {detail}.' if detail else ''))
                return False, f'failed encoded predicate: {_src(t)}' + (f' ({detail})' if detail else '')
        return True, ''

    def vacuity(self, s, env, ty, budget=None) -> dict | None:
        """Whether the checks anchored to this ask accept its empty answer (D.trivial): {'value', 'checks'} or
        None. Speculative like `determine`: kernel only, nothing in the run changes."""
        plan = self._contract(s)
        if plan is None or not self._speculable(plan):
            return None
        found = D.trivial(ty)
        if found is None or not found[0]:
            return None
        try:
            ok, _message = self._candidate(s, env, found[1], plan, budget=budget)
        except _AssessmentExhausted:
            return None
        except S.SymblicError:
            if self.kernel.budget.left < 0:
                raise
            return None
        if not ok:
            return None
        return {'value': D.shown_empty(found[1]), 'checks': [_expr_text(e.cond) for e in plan['ensures']]}

    def _escalate(self, s, env, ty, apps, effort, known, facts, stmt_text, feedback, retries, budget,
                  temperature, seed, tools, extras, weight, det, automatic=False, rec=None):
        plan = self._contract(s)
        if plan is None and not automatic:
            raise S.SymblicError('route=escalate requires an anchored ensure ... else retry with only '
                                 'kernel expressions and let bindings; no routines or effects', s.line,
                                 s.col, 'check')
        ignored = [key for key in ('votes', 'ahead', 'key', 'vote', 'agree', 'strict', 'permute', 'within')
                   if self._opt(s, key, env) is not None]
        if ignored or effort == 'ultra':
            raise S.SymblicError('route=escalate does not use voting options: '
                                 + ', '.join(ignored + (['effort=ultra'] if effort == 'ultra' else [])),
                                 s.line, s.col, 'check')
        fam_need = self._opt(s, 'families', env)
        if fam_need is not None and not S.is_num(fam_need):
            raise S.SymblicError('families must be a number', s.line, s.col, 'type')
        if S.is_num(fam_need) and fam_need > 1:
            raise S.SymblicError('route=escalate selects one checked answer; ahead, key and families>1 '
                                 'are voting options', s.line, s.col, 'check')
        # Opt-in routing policy shares correction allowance without weakening the
        # anchored-contract requirement or changing explicit single-model calls.
        shared_repairs = automatic or (self._requested_by(s, env) == 'auto'
            and isinstance(self.opts.get('auto_route'), dict)
            and self.opts['auto_route'].get('declared_repairs') == 'shared')
        attempts, observations = [], []
        shown: dict = {}                    # answer hash -> the answer, for a diagnosis when every attempt fails
        position = {'i': 0}

        def repair_gate():
            with self.lock:
                # An automatic route keeps its last correction for its LAST candidate, its escalation (as the
                # planner keeps its final correction): an earlier, cheaper candidate may
                # use the others. 2026-10-03: a 1B model took both corrections of a Tetris ask and the one
                # engine able to write it was left a single attempt.
                if shared_repairs and position['i'] < len(apps) - 1 and self.auto_repairs_left <= 1:
                    return False
                if self.auto_repairs_left <= 0:
                    return False
                self.auto_repairs_left -= 1
                return True
        def validate(value, readings):
            if str(self._opt(s, 'ambiguous', env)).lower() == 'fail' and readings:
                self.warnings.append({'line': s.line, 'message': 'multiple interpretations: ' + '; '.join(readings)})
                self._trace(s, 'ambiguous', note='; '.join(readings))
                raise RunFailed(S.SymblicError(f'{s.name}: reader reported multiple interpretations: '
                                               + '; '.join(readings), s.line, s.col, 'ambiguous'))
            shown.setdefault(S.fingerprint(value), S.show(value, 200))
            try:
                return self._candidate(s, env, value, plan, explain=True) if plan is not None else (True, '')
            except S.SymblicError as exc:
                if self.kernel.budget.left < 0 or exc.kind in ('effect', 'resource', 'unavailable', 'budget'):
                    raise       # an exhausted budget or the program's own effect violation is not the answer's fault
                # the kernel's error text can quote a value: it goes to the model only when every check and
                # let of the contract reads the answer alone
                answer_only = _answer_only_contract(s.name, plan)
                return False, exc.message if answer_only else 'a check could not be evaluated for this answer'
        # D5 provenance (observed, never steering): which rung answered, its locality, and the cloud calls this ask
        # charged or had refused before dispatch. Cloud rungs the routing policy removed count as refused. The run's
        # totals are kept apart from the ladders: an ensure-retry rolls a ladder back, never a charge or a refusal.
        ladder = {'accepted': False, 'rungs': len(apps),
                  'cloud_dispatches_charged': (rec or {}).get('_carried_cloud', 0),
                  'cloud_refused_pre_dispatch': (rec or {}).get('_policy_cloud_refused', 0)}
        if rec is not None:
            rec['_escalation'] = ladder
        if ladder['cloud_refused_pre_dispatch']:
            with self._receipts_lock:
                self._cloud_totals['refused'] += ladder['cloud_refused_pre_dispatch']
        for i, app in enumerate(apps):
            self.check_stop()
            position['i'] = i
            cap = S.capsule(self.program, min(self.no, self.total) or 1, self.total or 1, stmt_text, ty,
                            effort, known, facts, feedback=feedback, budget=budget,
                            native=app['engine'] in S.NATIVE_REASONING, definitions=extras['definitions'],
                            examples=extras['examples'], readings=extras['readings'], profile=self.execution_profile,
                            presentation=extras.get('presentation', 'full'))
            self._context_warnings(s, cap)
            temp = _plain_number(temperature) if S.is_num(temperature) else 0
            tally = {'dispatched': 0, 'refused': 0, 'cached': 0}
            local = app['engine'] in S.LOCAL_APPLICATOR_ENGINES
            try:
                result = self._sample(app, cap, ty, s, i, temp, seed + i, retries, effort, tools, 1,
                                       validate=validate, provenance=extras,
                                       repair_gate=repair_gate if shared_repairs else None, tally=tally)
            finally:
                if not local:
                    refused = int(tally['refused'] > 0 and tally['dispatched'] == 0)
                    ladder['cloud_dispatches_charged'] += tally['dispatched']
                    ladder['cloud_refused_pre_dispatch'] += refused
                    if tally['dispatched'] or refused:
                        with self._receipts_lock:
                            self._cloud_totals['charged'] += tally['dispatched']
                            self._cloud_totals['refused'] += refused
            observations.extend(result.get('observations', []))
            attempt = {k: result[k] for k in ('app', 'ok', 'attempts', 'error', 'hash', 'ms', 'cached')
                       if k in result}
            attempts.append(attempt)
            self._trace(S.Node('route-attempt', s.line, s.col), 'accepted' if result['ok'] else 'rejected',
                         note=S.app_label(app), ask={'route': 'escalate', 'attempt': attempt,
                                                     'observations': result.get('observations', [])})
            if not result['ok']:
                continue
            ladder.update(accepted=True, rung=i, applicator=S.app_label(app), locality='local' if local else 'cloud',
                          cached=bool(result.get('cached')))
            meta = {'route': 'automatic' if automatic else 'escalate',
                    'validation_scope': 'encoded_predicates' if plan is not None else 'declared_type_only',
                    'effort': effort, 'votes': 1, 'apps': [S.app_label(a) for a in apps],
                    'selected': S.app_label(app), 'route_attempts': attempts, 'rounds': 1, 'agreement': 1.0,
                    'agreement_scope': 'single_selected_answer', 'distinct': 1, 'contested': False,
                    'vote': 'checked', 'calls': sum(a['attempts'] for a in attempts), 'samples': [],
                    'context': [k[0] for k in known], 'facts': len(facts),
                    'evidence': E.evidence(observations, source=self.source_sha256, line=s.line, name=s.name,
                                            ty=ty, determination=det['report'] if det else None,
                                            value=result['value'])}
            if automatic:
                meta['agreement'] = None
                meta['routing'] = {'requested': 'auto',
                                   'validation_scope': meta['validation_scope'],
                                   'semantic_correctness': 'not_established',
                                   'policy_sha256': E.digest(self.opts.get('auto_route') or {})}
            if det:
                meta['determination'] = det['report']
            flagged = [o for o in observations if o.get('readings')]
            if extras['readings']:
                meta['ambiguity'] = {'flagged': len(flagged), 'of': len(observations),
                                      'by': [o['app'] for o in flagged],
                                      'readings': list(dict.fromkeys(r for o in flagged for r in o['readings']))[:12]}
            return {'value': result['value'], 'weight': weight, 'meta': meta}
        kind = 'check' if observations else 'unavailable'
        message = (f'{s.name}: no escalation candidate supplied an accepted answer: '
                   + '; '.join(f'{a["app"]}: {a.get("error", "rejected")}' for a in attempts))
        hashes = [o.get('answer_hash') for o in observations if o.get('constraint_passed') is False]
        found = D.exhaustion(hashes)
        if found:
            text = D.exhaustion_text(found)
            message += f'; {text}' if text else ''
            checks = '; '.join(_src(e) for e in plan['ensures']) if plan is not None else ''
            self._diagnose(s.line, s.name, checks, found, [shown.get(h, '') for h in hashes])
            self._trace(s, 'failed', note=f'rejected answers: {found["pattern"]}')
        raise RunFailed(S.SymblicError(message, s.line, s.col, kind))

    def _search(self, s, env, ty, apps, effort, known, facts, stmt_text, feedback, retries, budget,
                temperature, seed, tools, extras, weight, det, rec=None):
        """route=search: checked candidates in parallel, for a contract the kernel decides (a test suite, exact
        predicates). A round asks `samples` candidates at once, the applicators in turn, each with its own seed:
        the first of the first round at the program's temperature (0 unless set), the others at 0.7 unless a
        temperature is set. Each candidate is repaired against its own failures up to `retries` times. The answer is
        the pass with the FEWEST attempts, ties to the LOWEST index, never the first to arrive, so the same replies
        always select the same answer; it is taken as soon as no other candidate can still do better, and the others'
        in-flight calls are cancelled. A round in which none passes starts a fresh round (new seeds, no carried
        feedback), up to `rounds`; then the run fails at the ask, like escalation."""
        plan = self._contract(s)
        if plan is None:
            raise S.SymblicError('route=search requires an anchored ensure ... else retry (the checks decide) with only '
                                 'kernel expressions and let bindings between them', s.line, s.col, 'check')
        ignored = [key for key in ('votes', 'ahead', 'key', 'vote', 'agree', 'strict', 'permute', 'within',
                                   'families') if self._opt(s, key, env) is not None]
        if ignored or effort == 'ultra':
            raise S.SymblicError('route=search does not use voting options: '
                                 + ', '.join(ignored + (['effort=ultra'] if effort == 'ultra' else [])),
                                 s.line, s.col, 'check')
        def count(key, default, hi):
            raw = self._opt(s, key, env)
            if raw is None:
                return default
            if not S.is_num(raw) or int(raw) != raw or not 1 <= int(raw) <= hi:
                raise S.SymblicError(f'{key} must be a whole number from 1 to {hi}', s.line, s.col, 'type')
            return int(raw)
        samples = count('samples', len(apps), SEARCH_MAX_SAMPLES)
        rounds = count('rounds', 1, SEARCH_MAX_ROUNDS)
        fixed_temp = _plain_number(temperature) if S.is_num(temperature) else None
        attempts, observations, shown = [], [], {}
        budget_lock = threading.Lock()
        # D3: what each Code candidate's declared tests returned when it was checked, by (round, candidate). Read from
        # the checks that run anyway (S.observe_external_adapters): no extra execution, no change to selection.
        code = ty.get('k') == 'code' and rec is not None
        behaviour: dict = {}
        behaviour_lock = threading.Lock()

        def validate(value, readings, slot=None):
            # candidates are checked in threads: each check spends its own copy of the remaining steps, and what it
            # spent comes off the run's budget under a lock (no lost update, no lock on the kernel's hot path)
            shown.setdefault(S.fingerprint(value), S.show(value, 200))
            with budget_lock:
                local = S.Budget(max(0, self.kernel.budget.left))
            start = local.left
            seen = [] if code and slot is not None else None
            try:
                with S.observe_external_adapters(_adapter_recorder(seen)) if seen is not None else nullcontext():
                    verdict = self._candidate(s, env, value, plan, explain=True, budget=local)
                if seen is not None:
                    with behaviour_lock:
                        behaviour[slot] = (bool(verdict[0]), seen)
                return verdict
            except S.SymblicError as exc:
                if local.left < 0 or exc.kind in ('effect', 'resource', 'unavailable', 'budget'):
                    raise       # an exhausted budget or the program's own effect violation is not the answer's fault
                if seen is not None:
                    with behaviour_lock:
                        behaviour[slot] = (False, seen)
                answer_only = _answer_only_contract(s.name, plan)
                return False, exc.message if answer_only else 'a check could not be evaluated for this answer'
            finally:
                with budget_lock:
                    self.kernel.budget.left -= start - local.left

        for r in range(rounds):
            self.check_stop()
            cancel = threading.Event()
            results = [None] * samples

            def one(i, r=r, cancel=cancel, on_attempt=None):
                app = apps[i % len(apps)]
                temp = fixed_temp if fixed_temp is not None else (0 if (r == 0 and i == 0) else 0.7)
                cap = S.capsule(self.program, min(self.no, self.total) or 1, self.total or 1, stmt_text, ty, effort,
                                known, facts, feedback=feedback if r == 0 else '', budget=budget,
                                native=app['engine'] in S.NATIVE_REASONING, definitions=extras['definitions'],
                                examples=extras['examples'], readings=extras['readings'], profile=self.execution_profile,
                                presentation=extras.get('presentation', 'full'))
                self._context_warnings(s, cap)
                return self._sample(app, cap, ty, s, i, temp, seed + i + 1000 * r, retries, effort, tools, r + 1,
                                    validate=lambda value, readings, slot=(r, i): validate(value, readings, slot),
                                    provenance=extras, cancel=cancel, on_attempt=on_attempt)

            accepted = None
            failed = [0] * samples                  # attempts that failed, per candidate (they run in order)
            passed_at = [None] * samples            # the attempt that passed
            done = [False] * samples
            changed = threading.Condition()

            def decided():
                """(attempts, index) of the winner once no other candidate can still do better, else None. The
                winner is the pass with the FEWEST attempts, ties to the lowest index: the same replies always select
                the same answer, and a first-try pass need not wait for another candidate's repairs."""
                passing = [(passed_at[j], j) for j in range(samples) if passed_at[j] is not None]
                if not passing:
                    return None
                best = min(passing)
                for j in range(samples):
                    if j == best[1] or done[j] or (passed_at[j] is not None and (passed_at[j], j) > best):
                        continue
                    need = best[0] if j < best[1] else best[0] - 1      # attempts j must have failed to lose
                    if failed[j] < need:
                        return None
                return best

            def observer(i):
                def seen(attempt, ok):
                    with changed:
                        if ok:
                            passed_at[i] = attempt
                        else:
                            failed[i] = max(failed[i], attempt)
                        changed.notify_all()
                return seen

            def one_wrapped(i):
                try:
                    return one(i, on_attempt=observer(i))
                finally:
                    with changed:
                        done[i] = True
                        changed.notify_all()

            with ThreadPoolExecutor(max_workers=max(1, min(self.parallel, samples))) as pool:
                futures = {pool.submit(one_wrapped, i): i for i in range(samples)}
                try:
                    with changed:
                        while True:
                            best = decided()
                            if best is not None or all(done):
                                break
                            changed.wait(timeout=5)
                    if best is not None:
                        accepted = best[1]
                        cancel.set()
                    for fut in futures:                   # every thread ends (the cancelled ones before a new call)
                        results[futures[fut]] = fut.result()
                except BaseException:
                    cancel.set()
                    raise
            if accepted is None:
                ok = [(r.get('attempts', 0), i) for i, r in enumerate(results) if r and r.get('ok')]
                accepted = min(ok)[1] if ok else None
            for i, result in enumerate(results):
                if result is None:
                    continue
                observations.extend(result.get('observations', []))
                attempt = {k: result[k] for k in ('app', 'ok', 'attempts', 'error', 'hash', 'ms', 'cached')
                           if k in result}
                attempt.update(candidate=i, round=r + 1)
                attempts.append(attempt)
                self._trace(S.Node('route-attempt', s.line, s.col), 'accepted' if i == accepted else 'rejected',
                            note=S.app_label(apps[i % len(apps)]), ask={'route': 'search', 'attempt': attempt})
            if code:
                with behaviour_lock:
                    rec['_code'] = _code_behavior(s, {i: got for (rr, i), got in behaviour.items() if rr == r},
                                                  occurrence=rec.get('occurrence'))
            if accepted is None:
                continue
            result = results[accepted]
            meta = {'route': 'search', 'validation_scope': 'encoded_predicates', 'effort': effort, 'votes': 1,
                    'apps': [S.app_label(a) for a in apps], 'selected': result['app'], 'route_attempts': attempts,
                    'samples_per_round': samples, 'rounds': r + 1, 'agreement': None,
                    'agreement_scope': 'single_selected_answer', 'distinct': 1, 'contested': False, 'vote': 'checked',
                    'calls': sum(a.get('attempts', 0) for a in attempts), 'samples': [],
                    'context': [k[0] for k in known], 'facts': len(facts),
                    'evidence': E.evidence(observations, source=self.source_sha256, line=s.line, name=s.name,
                                            ty=ty, determination=det['report'] if det else None,
                                            value=result['value'])}
            if det:
                meta['determination'] = det['report']
            return {'value': result['value'], 'weight': weight, 'meta': meta}
        kind = 'check' if observations else 'unavailable'
        message = (f'{s.name}: no search candidate passed its checks in {rounds} round(s) of {samples}: '
                   + '; '.join(f'{a["app"]}: {str(a.get("error", "rejected"))[:160]}' for a in attempts[-samples:]))
        hashes = [o.get('answer_hash') for o in observations if o.get('constraint_passed') is False]
        found = D.exhaustion(hashes)
        if found:
            text = D.exhaustion_text(found)
            message += f'; {text}' if text else ''
            self._diagnose(s.line, s.name, '; '.join(_src(e) for e in plan['ensures']), found,
                           [shown.get(h, '') for h in hashes])
            self._trace(s, 'failed', note=f'rejected answers: {found["pattern"]}')
        raise RunFailed(S.SymblicError(message, s.line, s.col, kind))

    def determine(self, s, env, ty, budget=None) -> dict | None:
        """Conditional uniqueness by enumeration. For a finite answer type whose checks (the ensure statements
        anchored to this ask, with only kernel `let`s between) can be evaluated here, try every possible
        answer: exactly one accepted means any accepted answer is that value whoever gives it (the result is
        applicator-independent by construction); none means the checks contradict each other; several means
        the statement is underdetermined and agreement can only be measured. An optional allowance can stop
        enumeration: zero or one checked witnesses then establish neither contradiction nor uniqueness.
        None when it does not apply."""
        plan = self._contract(s)
        if plan is None or not self._speculable(plan):
            return None
        values = S.domain(ty)
        if values is None:
            return None
        accepted = []
        evaluated = 0
        for v in values:
            try:
                ok, _message = self._candidate(s, env, v, plan, budget=budget)
            except _AssessmentExhausted:
                break
            except S.KernelLimitError:
                # An unexecuted candidate predicate is not false. In particular,
                # skipping representation refusals could invent uniqueness or
                # contradiction despite an incomplete domain assessment.
                raise
            except S.SymblicError as exc:
                if self.kernel.budget.left < 0 or exc.kind in ('resource', 'unavailable', 'budget'):
                    raise
                ok = False
            evaluated += 1
            if ok:
                accepted.append(v)
                if len(accepted) > 50:
                    break
        n = len(accepted)
        exhaustive = evaluated == len(values)
        verdict = ('determined' if exhaustive and n == 1 else 'contradictory' if exhaustive and n == 0
                   else 'underdetermined' if n >= 2 else 'unassessed')
        report = {'domain': len(values), 'accepted': n if n <= 50 else '>50', 'verdict': verdict,
                  'exhaustive': exhaustive, 'evaluated': evaluated,
                  'scope': 'declared_domain_and_encoded_predicates',
                  'checks': [_expr_text(e.cond) for e in plan['ensures']]}
        if budget is not None:
            report['assessment_budget'] = budget.record()
            if budget.exhausted:
                report['reason'] = 'budget'
        if exhaustive and n == 1:
            report['unique'] = S.show(accepted[0], 200)
            report['unique_hash'] = S.fingerprint(accepted[0])
        if exhaustive and n == 0:
            self.warnings.append({'line': s.line, 'message': f'{s.name}: no possible answer passes its checks'})
        if n > 1:
            report['witnesses'] = [S.to_plain(v) for v in accepted[:2]]
        # _accepted/_checks feed the determinacy receipt; partial details survive in evidence.determinations.
        return {'accepted': n, 'unique': accepted[0] if exhaustive and n == 1 else None, 'report': report,
                '_accepted': accepted, '_checks': [e.line for e in plan['ensures']]}

    # -- determinacy receipts (D1, D2) ------------------------------------------------------------------------------
    def _assess(self, rec, s, ty, det, steps) -> None:
        """The ask's determinacy from what `determine` found (it adds no evaluation and no model call). Uniqueness
        and contradiction need the whole domain; two passing values show underdetermination either way."""
        if det is None:
            rec.update(status='unassessed', reason=self._unassessed_reason(s, ty))
            return
        accepted = det.get('_accepted') or []
        exhaustive = bool(det['report']['exhaustive'])
        n = len(accepted)
        status = ('determined' if exhaustive and n == 1 else 'contradictory' if exhaustive and n == 0 else
                  'underdetermined' if n >= 2 else None)
        if status is None:
            rec.update(status='unassessed', reason=det['report'].get('reason', 'not_attempted'))
            return
        checks = det.get('_checks') or []
        rec.pop('reason', None)
        rec.update(status=status, domain={'kind': _DOMAIN_KINDS.get(ty['k'], ty['k']), 'size': det['report']['domain']},
                   exhaustive=exhaustive, method='enumeration',
                   passing=[_canonical_text(v) for v in accepted[:LIST_MAX['passing']]],
                   passing_count=n if exhaustive else None,
                   passing_truncated=n > LIST_MAX['passing'] or not exhaustive,
                   checks=checks[:LIST_MAX['checks']], checks_truncated=len(checks) > LIST_MAX['checks'],
                   cost={'steps': max(0, int(steps))})

    def _unassessed_reason(self, s, ty) -> str:
        """Why `determine` did not enumerate this ask, read from the type and the anchored checks only."""
        size = S.domain_size(ty)
        if size is None:
            return 'no_finite_domain'
        if size > S.DOMAIN_CAP:
            return 'over_limit'
        plan = self._checks.get(id(s))
        if not plan or not plan['ensures']:
            return 'no_anchored_checks'
        if s.each is not None:
            return 'not_attempted'                  # the evaluator does not enumerate `for each` asks
        return 'unsupported_check'                  # functions, routines, extensions or code adapters in the checks

    def _determinacy_row(self, rec) -> None:
        """The trace's determinacy row for one assessment (D1), written from the run's thread."""
        rec['_row'] = True
        self._trace(S.Node('determinacy', rec['line'], 0), rec['status'],
                    note=rec.get('reason') or (f'{rec["passing_count"]} of {rec["domain"]["size"]} pass'
                                               if rec.get('passing_count') is not None else
                                               f'{len(rec.get("passing") or [])}+ pass (stopped early)'),
                    extra={'name': rec['name'], 'occurrence': rec['occurrence'],
                           **({'index': rec['index']} if 'index' in rec else {}),
                           'method': rec.get('method'), 'exhaustive': rec.get('exhaustive'),
                           'passing_count': rec.get('passing_count'), 'reason': rec.get('reason')})

    def _answer_fields(self, records, each=False) -> dict:
        """The ask trace row's who-answered fields (D2) and, for an escalated answer, its rung receipt (D5)."""
        answered = {r['answered_by'] for r in records}
        modes = [r['solve_mode'] for r in records]
        out = {'answered_by': 'kernel' if answered == {'kernel'} else 'model' if 'model' in answered else None,
               'solve_mode': modes[0] if modes else 'off',
               **({'occurrence': records[0]['occurrence']} if records else {})}
        if 'constructor' in answered:
            out['answered_by'] = 'constructor' if answered == {'constructor'} else 'mixed'
        if any(r.get('_constructor') for r in records):
            out['constructor'] = ([r.get('_constructor') for r in records] if each
                                  else records[0].get('_constructor'))
        receipts = [self._escalation_receipt(r) for r in records]
        if any(receipts):
            out['escalation'] = receipts if each else receipts[0]
        return out

    @staticmethod
    def _escalation_receipt(rec):
        esc = rec.get('_escalation')
        if not esc or not esc.get('accepted'):
            return None
        return {k: esc[k] for k in ('rung', 'rungs', 'applicator', 'locality', 'cached', 'cloud_dispatches_charged',
                                    'cloud_refused_pre_dispatch')}

    def definitions_for(self, text: str) -> list:
        """The program's terms that occur in this statement (word match, case-insensitive, plural -s/-es),
        in the order they were defined: deterministic common ground for the applicator."""
        low = text.lower()
        out = []
        for key, (term, meaning) in self.terms.items():
            if re.search(rf'\b{re.escape(key)}(s|es)?\b', low):
                out.append((term, meaning))
        return out

    def examples_for(self, s, ty, env) -> list:
        """examples=[[question, answer], ...] or [{q: ..., a: ...}]: each answer is checked against the ask's
        type (a wrong example is an error, not a hint) and shown in canonical JSON."""
        node = s.options.get('examples')
        if node is None:
            return []
        raw = self.kernel.eval(node, env)
        if not isinstance(raw, tuple):
            raise S.SymblicError('examples must be a list of [question, answer] pairs', s.line, s.col, 'type')
        out = []
        for i, ex in enumerate(raw[:8], 1):
            if isinstance(ex, dict):
                q, a = ex.get('q', ex.get('question')), ex.get('a', ex.get('answer'))
            elif isinstance(ex, tuple) and len(ex) == 2:
                q, a = ex
            else:
                raise S.SymblicError(f'example {i} must be [question, answer]', s.line, s.col, 'type')
            try:
                val = S.coerce(S.to_plain(a) if not isinstance(a, (tuple, dict, frozenset)) else _jsonish(a), ty)
            except S.SymblicError as e:
                raise S.SymblicError(f'example {i}: {e.message}', s.line, s.col, 'type') from None
            out.append((S.show(q, 300), json.dumps(_jsonish(val), ensure_ascii=False)))
        return out

    # -- options -----------------------------------------------------------------------------
    def _determination_enabled(self, s, env) -> bool:
        """Runtime speculative assessment is opt-out; an explicit value must be an actual Boolean."""
        if not ('determine' in s.options or 'determine' in self.defaults or 'determine' in self.opts):
            return True
        value = self._opt(s, 'determine', env)
        if type(value) is not bool:
            raise S.SymblicError('determine must be true or false', s.line, s.col, 'type')
        return value

    def _opt(self, s, key, env):
        if s is not None and key in s.options:
            return self._opt_value(key, s.options[key], env)
        if key in self.defaults:
            return self.defaults[key]
        return self.opts.get(key)

    def _opt_value(self, key, node, env):
        """Option values are expressions, except that bare words name things (effort=high, by=panel,
        context=[a, b] names bindings rather than reading their values)."""
        if not isinstance(node, S.Node):
            return node
        if node.k == 'lit':
            return node.value
        if key == 'context' and node.k == 'list':
            return tuple(x.name if x.k == 'name' else S.show(self.kernel.eval(x, env)) for x in node.items)
        if node.k == 'name':
            if key == 'by' and node.name in self.groups:
                return node.name
            b = env.lookup(node.name)
            if b is not None and key not in ('effort', 'context', 'think', 'tools', 'capsule'):
                return b.value
            return node.name
        return self.kernel.eval(node, env)

    def _requested_by(self, s, env):
        by = self._opt(s, 'by', env)
        return by if by is not None else self.defaults.get('applicator') or self.opts.get('by')

    def _automatic(self, s, env) -> bool:
        # Explicit voting keeps its existing semantics on the primary model. A
        # routing list is a sequential fallback order, never an implied council.
        return (self.opts.get('certificate') is None and not self.opts.get('override_by')
                and self._requested_by(s, env) == 'auto'
                and self._opt(s, 'route', env) is None
                and not any(self._opt(s, k, env) is not None for k in
                            ('votes', 'ahead', 'key', 'vote', 'agree', 'strict', 'families', 'permute', 'within'))
                and str(self._opt(s, 'effort', env) or 'medium') != 'ultra')

    def _apps(self, s, env) -> list:
        if self.opts.get('certificate') is not None:
            from symblic.kernel import certificates as C
            from symblic.lang import abstraction as L
            modules = {key: mod.sha256 for key, mod in L.state(self).modules.items()}
            table = C.route_table(self.opts['certificate'], self.source, module_hashes=modules)
            if table['status'] != 'qualified':
                raise S.SymblicError('certificate routing refused: ' + table['escalation']['reason'],
                                     s.line, s.col, 'certificate')
            # A tested council is not evidence that its individual members passed.
            # Only single-applicator cohort labels are dispatchable in this lane.
            try:
                return [E.parse_applicator(label) for label in table['candidates']]
            except S.SymblicError:
                raise S.SymblicError('certificate routing requires single-applicator cohorts; '
                                     'a tested group cannot certify each member separately', s.line,
                                     s.col, 'certificate') from None
        if self.opts.get('override_by'):            # probe mode (symblic.authoring.tighten): the same panel for every ask
            return [E.parse_applicator(x) for x in self.opts['override_by']]
        by = self._opt(s, 'by', env)
        if by is None:
            by = self.defaults.get('applicator') or self.opts.get('by')
        if by is None and (self.defaults.get('provider') or self.defaults.get('model')):
            prov = str(self.defaults.get('provider') or 'ollama').lower()
            by = prov + (':' + str(self.defaults['model']) if self.defaults.get('model') else '')
        if by is None:
            raise S.SymblicError('no applicator: add `use by="..."` or `with by="..."`, or pick one when you run it',
                                 s.line, s.col)
        if by == 'auto':
            policy = self.opts.get('auto_route')
            candidates = policy.get('candidates') if isinstance(policy, dict) else None
            if not isinstance(candidates, (list, tuple)) or not 1 <= len(candidates) <= 12:
                raise S.SymblicError('auto needs a resolved auto_route with one to twelve concrete candidates',
                                     s.line, s.col, 'unavailable')
            apps = [E.parse_applicator(spec) for spec in candidates]
            if any(app['engine'] == 'kernel' for app in apps):
                raise S.SymblicError('an automatic model route cannot contain the kernel', s.line, s.col, 'type')
            if any(app['engine'] == 'council' for app in apps):
                raise S.SymblicError('councils need their explicit orchestration tool and member budget; '
                                     'they cannot hide nested calls in an automatic single-model route',
                                     s.line, s.col, 'budget')
            if not self._automatic(s, env) and self._opt(s, 'route', env) != 'escalate':
                return apps[:1]
            return apps
        if isinstance(by, str) and by in self.groups:
            return self.groups[by]
        if isinstance(by, (tuple, list, frozenset)):
            out = []
            for x in by:
                if isinstance(x, str) and x in self.groups:
                    out.extend(self.groups[x])
                else:
                    out.append(E.parse_applicator(x))
            return out
        try:
            return [E.parse_applicator(by)]
        except S.SymblicError as e:
            e.line, e.col = s.line, s.col
            raise

    def _weight(self, v, env) -> float:
        if isinstance(v, S.Node):
            v = self._opt_value('weight', v, env)
        if v is None:
            return 1
        if not S.is_num(v):
            raise S.SymblicError('weight must be a number from 0 to 10')
        f = float(v)
        if not 0 <= f <= 10:
            raise S.SymblicError('weight must be from 0 to 10')
        return int(f) if f == int(f) else f

    # -- bindings, trace, report -------------------------------------------------------------
    def _read_bindings(self):
        rows = {}
        for frame in S.binding_read_frames(self):
            rows.update(frame)
        return list(rows.values())

    def _knowledge_read(self, predicate=None):
        # Main-program knowledge keeps its existing conservative scope. Module
        # premises are selected by the canonical predicate and all rule inputs,
        # including negative literals. This is statement/predicate scope, not a
        # minimal successful proof tree. Full fact context deliberately reads all.
        needed = _closure({predicate}, self._rule_deps([])) if predicate is not None else None
        for binding in self._epistemic_knowledge:
            if needed is not None and binding.meta.get('_epistemic_module'):
                if not needed.intersection(binding.meta.get('_epistemic_predicates', ())):
                    continue
            S.record_binding_read(binding)

    def _callable_reads(self, statement):
        """Conservative closure reads also cover pure memo hits with no model event."""
        return self._callable_reads_of(S._reads_of(statement))[0]

    def _callable_reads_of(self, nodes):
        """(bindings, queries, unknown): the bindings that the user functions and routines `nodes` call,
        transitively, read from their scopes, in their bodies and in the parameter defaults and (a routine's) options
        their scope evaluates at a call; whether any of them queries the knowledge base; and whether a call names
        nothing callable yet (no builtin, no registered function or routine: a module imported later registers it).
        Imported callables are reached by any name they are registered under (a module alias too)."""
        from symblic.lang import abstraction as symblic_lang
        state = symblic_lang.state(self)
        found, visited, queries, unknown = {}, set(), [], []

        def read(env, names):
            for name in names:
                binding = env.lookup(name)
                if binding is not None:
                    found[id(binding)] = binding

        def walk(obj):
            if isinstance(obj, S.Node):
                fn = state.callables.get(obj.fn) if obj.k == 'call' else None
                if obj.k == 'call' and fn is None and obj.fn not in S.BUILTINS \
                        and obj.fn not in self.kernel.functions:
                    unknown.append(obj.fn)
                if fn is not None and id(fn) not in visited:
                    visited.add(id(fn))
                    target = fn.node.value if fn.kind == 'function' else fn.body
                    read(fn.env, S.free_names(target) - set(fn.node.params))
                    # defaults and options are evaluated in the defining scope, where a parameter is not bound
                    scoped = [spec['default'] for spec in fn.node.specs if spec.get('default') is not None]
                    scoped += list((getattr(fn.node, 'options', None) or {}).values())
                    read(fn.env, S.free_names(scoped))
                    if _queried([target, scoped]):
                        queries.append(fn)
                    walk(target)
                    walk(scoped)
                for value in vars(obj).values():
                    walk(value)
            elif isinstance(obj, dict):
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, (list, tuple)):
                for value in obj:
                    walk(value)
        walk(nodes)
        return list(found.values()), bool(queries), bool(unknown)

    def _contract_reads(self, statement):
        """What decides which answer of an ask is accepted (epistemic-2): every ensure anchored to it and every
        statement between the ask and that ensure, nested blocks included, whatever they call; `ask ... for each`
        too. The speculation gate _contract() refuses anything but builtins, which is right for speculation and
        wrong for lineage. [] for any other statement.

        A routine defined between is not registered when the ask binds: its body is among the statements, its
        defaults are its statement's reads, and its options, evaluated in its scope when the check calls it, are
        added here (they are not statements). A module imported between registers its callables only when the
        import runs; _imported_between says so."""
        plan = self._checks.get(id(statement)) if statement.k == 'ask' else None
        if not plan or not plan['ensures']:
            return []
        between = list(_flat(plan['between']))
        reads = [_statement_reads(t) for t in between]
        reads += [list((getattr(t, 'options', None) or {}).values()) for t in between if t.k == 'routine']
        return [reads, [e.cond for e in plan['ensures']]]

    def _imported_between(self, statement) -> bool:
        """Whether a module is imported between an ask and an ensure anchored to it."""
        plan = self._checks.get(id(statement)) if statement.k == 'ask' else None
        return bool(plan and plan['ensures'] and any(t.k == 'import' for t in _flat(plan['between'])))

    # -- epistemic lineage -------------------------------------------------------------------
    # A claim depends on at most EP.MAX_REFS references and a view lists at most EP.MAX_REFS roots. Neither bound
    # may drop a parent, relabel a root or manufacture admissibility (epistemic-3): a larger parent set goes through
    # grouping claims, and the exact root set of every assessed claim is kept beside the views
    # (_epistemic_rootsets: claim id -> frozenset of root claim ids; _epistemic_rootrows: id -> root row), so a
    # bounded view counts by origin and status what it does not list.

    def _epistemic_ref(self, claim):
        """A claim's pinned reference. A claim this run registered (made by EP.make_claim, or validated when a graph
        edge imported it) is not validated again: re-validating every parent of every binding made loops quadratic
        (language-2)."""
        ident = claim.get('id') if isinstance(claim, dict) else None
        if ident is not None and self._epistemic_claims.get(ident) is claim:
            return {'id': ident, 'revision': claim['revision'], 'sha256': claim['sha256']}
        return EP.reference(claim)

    @staticmethod
    def _root_union(parts):
        """The union of root-ID sets, reusing the largest when it holds the others (the usual case)."""
        if not parts:
            return frozenset()
        parts = sorted(parts, key=len, reverse=True)
        base, extra = parts[0], set()
        for part in parts[1:]:
            if not part <= base:
                extra |= part
        return base | extra if extra else base

    def _root_ids(self, ident):
        """Every root of an assessed claim as a frozenset of claim IDs. Claims this run made are indexed when they
        are assessed; an imported one (a graph edge) is indexed once from its dependencies, without recursion. A
        missing claim has no known roots (its dependants report missing_dependency)."""
        with self._epistemic_lock:
            sets = self._epistemic_rootsets
            found = sets.get(ident)
            if found is not None:
                return found
            stack, visiting = [ident], set()
            while stack:
                top = stack[-1]
                if top in sets:
                    stack.pop()
                    continue
                claim, view = self._epistemic_claims.get(top), self._epistemic_views.get(top)
                if claim is None or view is None:
                    sets[top] = frozenset()
                    stack.pop()
                    continue
                visiting.add(top)
                waiting = [d['id'] for d in claim['dependencies'] if d['id'] not in sets]
                if waiting:
                    for dep in waiting:
                        if dep in visiting:         # a cycle cannot be content-addressed; refuse it, never loop
                            sets[dep] = frozenset()
                    stack.extend(dep for dep in waiting if dep not in sets)
                    continue
                stack.pop()
                ids = self._root_union([sets[d['id']] for d in claim['dependencies']])
                if claim['origin'] != 'derived':
                    ref = {key: claim[key] for key in ('id', 'revision', 'sha256')}
                    self._epistemic_rootrows.setdefault(top, {'ref': ref, 'origin': claim['origin'],
                                                              'status': view['status']})
                    ids = ids | {top}
                sets[top] = ids
            return sets[ident]

    def _root_rows(self, ids):
        with self._epistemic_lock:
            rows = self._epistemic_rootrows
            return [rows[key] for key in sorted(ids)]

    def _bounded_roots(self, ids):
        """(conditional_on, roots_omitted) for a root set. Up to MAX_REFS roots are listed: first the lowest ID of
        every (origin, status) and every contested or refuted root, then the rest by ID. The others are counted
        by origin and status, with the digest of the complete list; nothing is relabelled."""
        if len(ids) <= EP.MAX_REFS:
            return self._root_rows(ids), None
        cached = self._epistemic_bounded.get(id(ids))
        if cached is not None and cached[0] is ids:
            return cached[1], cached[2]
        rows = self._epistemic_rootrows
        ordered = sorted(ids)
        keep, kinds = set(), set()
        for key in ordered:
            kind = (rows[key]['origin'], rows[key]['status'])
            if kind not in kinds:
                kinds.add(kind)
                keep.add(key)
        for key in ordered:
            if len(keep) >= EP.MAX_REFS:
                break
            if rows[key]['status'] in ('contested', 'refuted'):
                keep.add(key)
        for key in ordered:
            if len(keep) >= EP.MAX_REFS:
                break
            keep.add(key)
        counts: dict = {}
        for key in ordered:
            if key not in keep:
                kind = (rows[key]['origin'], rows[key]['status'])
                counts[kind] = counts.get(kind, 0) + 1
        listed = [rows[key] for key in sorted(keep)]
        omitted = {'count': len(ordered) - len(keep), 'total': len(ordered),
                   'by_origin_status': [{'origin': o, 'status': st, 'count': n}
                                        for (o, st), n in sorted(counts.items())],
                   'roots_sha256': E.digest([rows[key]['ref'] for key in ordered])}
        self._epistemic_bounded[id(ids)] = (ids, listed, omitted)
        return listed, omitted

    def _epistemic_assess(self, ref, claim, refs, origin, status):
        """Incremental evaluation of one new host claim by the same conditional rules as EP.evaluate, its
        dependencies assessed already: no whole-registry O(n^2) pass or MAX_CLAIMS failure in long programs."""
        issues, complete, parts = [], True, []
        for parent in refs:
            view = self._epistemic_views.get(parent['id'])
            if view is None or any(view.get(k) != parent[k] for k in parent):
                issues.append({'code': 'missing_dependency', 'ref': parent})
                complete = False
                continue
            complete = complete and view.get('lineage_complete', True)
            if not view['admissible']:
                issues.append({'code': 'unavailable_dependency', 'ref': parent})
            parts.append(self._root_ids(parent['id']))
        if status in ('contested', 'refuted'):
            issues.append({'code': status, 'id': ref['id']})
        ids = self._root_union(parts)
        if origin == 'derived':
            if not any(c['scope'] == 'encoded_derivation' for c in claim['checks']):
                issues.append({'code': 'no_checked_derivation', 'id': ref['id']})
            status = status if status in ('contested', 'refuted') else 'unknown' if issues else 'conditional'
            support = 'unavailable' if issues else 'checked_derivation'
        else:
            self._epistemic_rootrows[ref['id']] = {'ref': ref, 'origin': origin, 'status': status}
            ids = ids | {ref['id']}
            support = 'unavailable' if issues else 'premise'
        self._epistemic_rootsets[ref['id']] = ids
        listed, omitted = self._bounded_roots(ids)
        view = {**ref, 'status': status, 'admissible': not issues, 'support': support,
                'empirical_truth': 'not_established', 'conditional_on': listed,
                'passed_receipt_ids': [c['id'] for c in claim['checks']],
                'derivation_receipt_ids': [c['id'] for c in claim['checks'] if c['scope'] == 'encoded_derivation'],
                'issues': issues, 'disagreements': [], 'lineage_complete': complete and omitted is None}
        if omitted is not None:
            view['roots_omitted'] = omitted
        return view

    def _epistemic_summary(self, refs):
        """One grouping claim over at most MAX_REFS references: derived by the host from exactly those, with an
        encoded_derivation receipt for them, and assessed like any derivation, so it is admissible only when every
        reference is and keeps every root (epistemic-3). The same references give the same claim."""
        content = {'kind': 'bounded_lineage_summary', 'grouping': 'hierarchical', 'count': len(refs),
                   'references_sha256': E.digest(refs), 'empirical_truth': 'not_established'}
        ident = 'summary:' + E.digest(content)[:48]
        known = self._epistemic_claims.get(ident)
        if known is not None and ident in self._epistemic_views:
            return self._epistemic_ref(known)
        kernel = self._kernel_identity()['id']
        predicate = {'kernel': kernel, 'operation': 'lineage_grouping'}
        check = EP.receipt(subject=content, predicate=predicate,
                           predicate_sha256=self._predicate_digest(predicate, ('grouping-predicate', kernel)),
                           scope='encoded_derivation', passed=True, inputs=refs)
        claim = EP.make_claim(ident, content, origin='derived', dependencies=refs, checks=[check])
        ref = {'id': ident, 'revision': claim['revision'], 'sha256': claim['sha256']}
        self._epistemic_claims[ident] = claim
        self._epistemic_views[ident] = self._epistemic_assess(ref, claim, refs, 'derived', 'unknown')
        return ref

    def _epistemic_group(self, refs):
        """References for a claim's dependencies: unchanged up to MAX_REFS, else grouped level by level."""
        while len(refs) > EP.MAX_REFS:
            groups = [self._epistemic_summary(refs[i:i + EP.MAX_REFS]) for i in range(0, len(refs), EP.MAX_REFS)]
            refs = sorted(groups, key=lambda row: row['id'])
        return refs

    def _text_digest(self, text):
        """E.digest of a str, once per run (D16): the digest of an immutable str never changes."""
        if type(text) is not str:
            return E.digest(text)
        found = self._digest_memo.get(text)
        if found is None:
            found = self._digest_memo[text] = E.digest(text)
        return found

    def _predicate_digest(self, predicate, key):
        """EP.digest of a receipt predicate, once per run per key (D16); the key determines the predicate."""
        found = self._digest_memo.get(key)
        if found is None:
            found = self._digest_memo[key] = EP.digest(predicate)
        return found

    def _claim_for_binding(self, binding, *, parents=(), origin=None, status='unknown', derivation=None):
        """Host-only immutable metadata. Values are represented by a full canonical hash."""
        with self._epistemic_lock:
            previous = (binding.meta or {}).get('epistemic')
            if previous and previous['claim']['id'] in self._epistemic_claims:
                return previous
            basis = (binding.meta or {}).get('_epistemic_basis')
            if basis is not None:
                # an element binding (a loop variable): derived from what its statement read, whichever statement
                # needs its claim
                parents, origin = basis, 'derived'
                derivation = binding.meta.get('_epistemic_derivation') or 'selected iteration item'
            references = {}
            for parent in parents:
                if parent is binding:
                    continue
                ref = self._epistemic_ref(self._claim_for_binding(parent)['claim'])
                references[ref['id']] = ref
            refs = self._epistemic_group([references[key] for key in sorted(references)])
            if origin is None:
                origin = 'derived' if refs else 'assumption'
                derivation = derivation or ('runtime scoped value' if refs else None)
            label = S.type_label(binding.type) if binding.type else S.type_name(binding.value)
            content = {'name': binding.name[:256], 'name_sha256': self._text_digest(binding.name),
                       'type': label[:1024], 'type_sha256': self._text_digest(label),
                       'value_sha256': E.digest(S.canon(binding.value)),
                       'source_sha256': self.source_sha256, 'line': binding.line,
                       'representation': 'canonical_value_hash_only'}
            if binding.meta.get('_epistemic_module') is not None:
                content['module'] = binding.meta['_epistemic_module']
            if origin == 'solver_proposal':
                content['constructor'] = binding.meta['_constructor_content']
            checks = []
            if binding.type is not None:
                type_sha256 = self._text_digest(label)
                predicate = {'type_sha256': type_sha256}
                checks.append(EP.receipt(subject=content, predicate=predicate,
                    predicate_sha256=self._predicate_digest(predicate, ('type-predicate', type_sha256)),
                    scope='encoded_schema', passed=True, inputs=refs))
            if origin == 'derived' and derivation is not None:
                kernel, operation = self._kernel_identity()['id'], self._text_digest(derivation)
                predicate = {'kernel': kernel, 'operation_sha256': operation}
                checks.append(EP.receipt(subject=content, predicate=predicate,
                    predicate_sha256=self._predicate_digest(predicate, ('derivation-predicate', kernel, operation)),
                    scope='encoded_derivation', passed=True, inputs=refs))
            if origin == 'solver_proposal':
                validated = binding.meta['_constructor_validation']
                for predicate_hash in validated['predicate_sha256s']:
                    predicate = {'kernel': validated['kernel_id'], 'source_sha256': self.source_sha256,
                                 'contract_sha256': validated['contract_sha256'],
                                 'predicate_sha256': predicate_hash}
                    checks.append(EP.receipt(subject=content, predicate=predicate,
                                            scope='encoded_predicate', passed=True, inputs=refs))
            identity = E.digest([content, origin, status, refs, checks])
            ident = 'binding:' + identity[:48]
            claim = self._epistemic_claims.get(ident)
            if claim is not None and ident in self._epistemic_views:
                # The identity digests everything the claim holds, so this is the same claim (a statement that a
                # loop repeats with the same value and lineage): one claim, one assessment, no second validation.
                view = self._epistemic_views[ident]
            else:
                claim = EP.make_claim(ident, content, origin=origin, dependencies=refs, checks=checks, status=status)
                # make_claim has validated it: its reference needs no second validation
                ref = {'id': claim['id'], 'revision': claim['revision'], 'sha256': claim['sha256']}
                self._epistemic_claims[ref['id']] = claim
                view = self._epistemic_assess(ref, claim, refs, origin, status)
                self._epistemic_views[ref['id']] = view
            result = {'claim': claim, 'assessment': view, 'dependency_scope': 'conservative_runtime_reads'}
            binding.meta['epistemic'] = result
            return result

    def _attach_epistemic(self, binding, statement, env):
        parents = {}

        def add(candidates):
            # an element binding (a loop variable) holds part of a value whose reads are parents already
            for b in candidates:
                if b is not binding and not (b.meta or {}).get('_epistemic_element'):
                    parents[id(b)] = b
        add(binding.meta.pop('_epistemic_parents', ()))     # a lifted loop list: each iteration's binding
        add(self._read_bindings())
        add(self._callable_reads(statement))
        reads = S._reads_of(statement)
        contract = self._contract_reads(statement)
        if contract:
            # The checks anchored to an ask decide which of its answers is accepted, so what they read is a parent,
            # through user functions and routines too (epistemic-2). Their trial values are never parents.
            reads = [reads, contract]
            callee_reads, callee_queries, unknown = self._callable_reads_of(contract)
            add(callee_reads)
            # a check, or a function or routine it calls (root review), that queries the knowledge base reads the
            # declared knowledge when it runs, after this binding: the same conservative scope as a direct query.
            # So does a callable a module imported between will register (review of lane A): its body cannot be
            # read yet, and besides its arguments the declared knowledge is all of this program it can read.
            if callee_queries or _queried(reads) or (unknown and self._imported_between(statement)):
                # Module predicates are lazy and namespace-specific. Their
                # actual query event supplies premises; an accepted check then
                # refines the immutable proposal. Static look-ahead must not
                # attach unrelated modules or unevaluated query branches.
                add(b for b in self._epistemic_knowledge if not b.meta.get('_epistemic_module'))
        for name in S.free_names(reads):
            parent = env.lookup(name)
            if parent is not None:
                add((parent,))
        # Original model events survive routine memoization; they remain roots,
        # not additional votes. Only active claims may supply a dependency.
        # A row is found by its sequence (row i of this execution is offset + i + 1), not by a scan of the whole
        # trace for every binding (language-2).
        dependencies = binding.meta.get('dependencies') or ()
        by_sequence = None
        for dependency in dependencies:
            sequence = dependency.get('sequence') if isinstance(dependency, dict) else None
            index = sequence - self.store.trace_offset - 1 if type(sequence) is int else -1
            if 0 <= index < len(self.trace) and self.trace[index].get('sequence') == sequence:
                row = self.trace[index]
            else:
                if by_sequence is None:
                    by_sequence = {r.get('sequence'): r for r in self.trace}
                row = by_sequence.get(sequence)
            if row is not None and row.get('epistemic'):
                claim = row['epistemic']['claim']
                if claim['id'] in self._epistemic_claims:
                    proxy = S.Binding(claim['content']['name'], None, meta={'epistemic': row['epistemic']})
                    parents[id(proxy)] = proxy
        # Optional context rows actually sent by a model call also count.
        def observations(value):
            if isinstance(value, dict):
                manifest = value.get('context_manifest')
                if manifest:
                    for item in manifest.get('included', []):
                        ident = (item.get('claim') or {}).get('id')
                        claim = self._epistemic_claims.get(ident)
                        if claim is not None:
                            proxy = S.Binding(claim['content'].get('name', ident), None,
                                meta={'epistemic': {'claim': claim, 'assessment': self._epistemic_views[ident]}})
                            parents[id(proxy)] = proxy
                for key in ('evidence', 'observations', 'items'):
                    if key in value:
                        observations(value[key])
            elif isinstance(value, list):
                for child in value:
                    observations(child)
        observations(binding.meta)
        if statement.k == 'given':
            origin = 'owner_premise'
        elif statement.k == 'ask' and binding.meta.get('answered_by_finite_fallback'):
            origin = 'derived'
        elif statement.k == 'ask' and binding.meta.get('answered_by_constructor'):
            origin = 'solver_proposal'
        elif statement.k == 'ask' and not binding.meta.get('solved_by_kernel'):
            origin = 'model_proposal'
        elif statement.k == 'observe':
            origin = 'observation'
        elif binding.klass == 'effect':
            origin = 'source_report'
        else:
            origin = 'derived'
        self._claim_for_binding(binding, parents=list(parents.values()), origin=origin,
            status='contested' if binding.meta.get('contested') else 'unknown',
            derivation=({'operation': 'authored_finite_choice', **binding.meta['finite_fallback']}
                        if binding.meta.get('answered_by_finite_fallback') else
                        E.syntax(statement) if origin == 'derived' else None))

    def _memo_basis(self, dependencies):
        """Snapshot lineage for routine memo hits (root review, gap 4). symblic.lang.abstraction traces every routine call
        with the dependency list it keeps in the memo entry, and a memo hit with that very list. The first time
        a list is seen, the call has just run inside the kernel's call frame (S.capture_call_reads): what it read
        becomes the entry's basis. Seen again, the call is a memo hit and that basis is read again, so the cached
        value carries the lineage of the computation that produced it (snapshot semantics: not the knowledge or
        values current at the hit, and nothing is re-executed)."""
        frame = S.call_frame()
        if frame is None:
            return
        with self._epistemic_lock:
            known = self._memo_bases.get(id(dependencies))
            if known is None or known[0] is not dependencies:
                self._memo_bases[id(dependencies)] = (dependencies, tuple(frame.values()))
                return
        for binding in known[1]:
            S.record_binding_read(binding)

    def _bind(self, env, name, value, ty, s, klass, weight, meta=None) -> S.Binding:
        if env.has_local(name):
            prev = env.vars[name]
            raise S.SymblicError(f'{name} is already bound (line {prev.line}); Symblic names are immutable', s.line,
                                 s.col, 'name')
        if name in S.BUILTINS:
            raise S.SymblicError(f'{name} is a builtin function name', s.line, s.col, 'name')
        with self.lock:
            self.order += 1
            order = self.order
        meta = dict(meta or {})
        evidence = meta.get('evidence')
        if isinstance(evidence, dict) and evidence.get('sensitivity') in \
                ('lab-confidential', 'confidential', 'mixed'):
            with self.lock:
                self._protected_acquired = True
        if 'evidence' not in meta:
            parents = []
            for parent_name in sorted(S.free_names(S._reads_of(s))):
                parent = env.lookup(parent_name)
                if parent is not None:
                    pe = (parent.meta or {}).get('evidence')
                    parents.append({'name': parent_name, 'hash': parent.hash,
                                    'evidence_sha256': E.digest(pe) if pe else None})
            mechanism = ('input' if s.k == 'given' else 'effect' if klass == 'effect' else
                         'kernel_computation' if klass == 'exact' else 'model_derived')
            meta['evidence'] = {'version': E.VERSION, 'source_sha256': self.source_sha256,
                                'statement_line': s.line, 'name': name, 'parents': parents,
                                'mechanism': mechanism,
                                'assurance': 'derived_from_inputs' if parents or klass == 'exact' else 'unattested',
                                'independence': 'not_established',
                                'kernel': self._kernel_identity()}
            if meta.get('answered_by_finite_fallback'):
                meta['evidence'].update(mechanism='authored_finite_choice', finite_fallback=meta['finite_fallback'])
            if meta.get('dependencies'):
                meta['evidence']['observation_dependencies'] = meta['dependencies']
        b = S.Binding(name, value, ty, weight, stmt=f'L{s.line}', line=s.line, klass=klass, order=order, meta=meta)
        env.vars[name] = b
        # Rebinding a fallback value must never reuse another value's claim.
        b.meta.pop('epistemic', None)
        self._attach_epistemic(b, s, env)
        return b

    def _trace(self, s, status, binding=None, note='', ask=None, ms=0, check=None, dependencies=None,
               acceptance=None, extra=None) -> None:
        # the sequence is given under _trace_lock, with the append to memory and to trace.jsonl: rows written from
        # `for each` worker threads stay unique, gap-free and in the same order in both
        row = {'line': s.line, 'kind': s.k, 'status': status, 'at': round(time.time() - self.started, 3),
               'sequence': None, 'kernel': self._kernel_identity()}
        if binding is not None:
            row.update({'name': binding.name, 'hash': binding.hash, 'class': binding.klass,
                        'value': S.show(binding.value, 400), 'evidence': (binding.meta or {}).get('evidence'),
                        'epistemic': (binding.meta or {}).get('epistemic')})
        if s.k == 'call' and dependencies is not None:
            self._memo_basis(dependencies)
        if extra:
            row.update(extra)               # determinism receipts (lane C): determinacy, answered_by, escalation, drift
        if s.k in ('fact', 'rule'):
            premise = S.Binding('knowledge', E.syntax(s), line=s.line)
            self._claim_for_binding(premise, parents=self._read_bindings(), origin='owner_premise')
            self._epistemic_knowledge.append(premise)
            row['epistemic'] = premise.meta['epistemic']
        if note:
            row['note'] = note
        if ask is not None:
            row['ask'] = ask
        if check is not None:
            row['check'] = check
        if acceptance is not None:
            row['acceptance_lineage'] = acceptance
        if dependencies is not None:
            row['dependencies'] = dependencies
        if ms:
            row['ms'] = ms
        with self._trace_lock:
            row['sequence'] = self.store.trace_offset + len(self.trace) + 1
            self.trace.append(row)
            self.store.append('trace.jsonl', row)
            rows = len(self.trace)
        on_event = self.opts.get('on_event')
        if on_event is not None:
            # An embedder receives a copy and cannot mutate execution state through it.
            try:
                on_event(json.loads(json.dumps(row, default=str)))
            except Exception as exc:  # noqa: BLE001
                raise S.SymblicError(f'statement event callback failed: {type(exc).__name__}',
                                     s.line, s.col, 'event') from None
        if s.k == 'ask' and binding is not None:
            agree = (ask or {}).get('agreement')
            voted = _has_measured_agreement(ask or {})
            self.say(f'line {s.line}: {binding.name} = {S.show(binding.value, 120)}'
                     + (f'  [agreement {agree:.0%}]' if voted and isinstance(agree, float) else ''))
        if rows % 5 == 0:
            self._save_state()

    def bindings(self) -> list:
        return [b.as_dict() for b in sorted(self.kernel.env.vars.values(), key=lambda b: b.order)
                if b.name not in self.groups]

    def fingerprint(self) -> str:
        """The run's identity: every top-level binding's fingerprint and every output's, in order."""
        parts = [f'{b.name}={b.hash}' for b in sorted(self.kernel.env.vars.values(), key=lambda b: b.order)
                 if b.name not in self.groups]
        parts += [f'out{o["line"]}={o["hash"]}' for o in self.outputs]
        return hashlib.sha256('\n'.join(parts).encode()).hexdigest()[:16]

    def report(self) -> dict:
        classes: dict = {}
        agreements = []
        for row in self.trace:
            if row.get('class'):
                classes[row['class']] = classes.get(row['class'], 0) + 1
            ask = row.get('ask') or {}
            a = ask.get('agreement')
            if isinstance(a, float) and _has_measured_agreement(ask):
                agreements.append(a)
        return {'program': self.program, 'status': self.status, 'error': self.error, 'fingerprint': self.fingerprint(),
                'execution_profile': self.execution_profile,
                'outputs': self.outputs, 'bindings': self.bindings(), 'warnings': self.warnings, 'notes': self.notes,
                'diagnoses': self.diagnoses,
                **({'finite_fallbacks': copy.deepcopy(self._finite_rows)} if self._finite_plans else {}),
                'asks': self.asks, 'calls': self.calls, 'cached': self.cached, 'classes': classes,
                'execution_id': self.execution_id,
                'model_budget': {'scope': 'run_source' if isinstance(self.opts.get('auto_route'), dict) else 'invocation',
                                 'used': self.calls_total, 'repairs_used': self.repairs_total, 'limit': self.max_calls},
                'agreement': round(sum(agreements) / len(agreements), 4) if agreements else None,
                'agreement_n': len(agreements),
                'facts': self.kernel.kb.fact_count(), 'seconds': round(time.time() - self.started, 2),
                'version': S.VERSION, 'kernel': S.kernel_id(),
                'epistemic': {'version': EP.VERSION, 'empirical_truth': 'not_established',
                              'claims': list(self._epistemic_claims.values()),
                              'assessments': list(self._epistemic_views.values())},
                'evidence': E.report(self.source_sha256, self.checks,
                                     [{'line': row['line'], **row['ask']['determination']}
                                      for row in self.trace if row.get('kind') == 'determination']),
                **self._receipts(),
                **({'constructor_activity': {'version': 1, 'attempt_possible': True}}
                   if self._constructor_activity else {}),
                **({'kernel_check': self.kernel_check} if self.kernel_check is not None else {})}

    def _receipts(self) -> dict:
        """The determinism blocks of the report (D-REPORT-SCHEMA v1): determinacy, code_behavior, model_identity,
        escalation and the one-line determinism_summary agents read first. Computed from what the run recorded;
        nothing is re-read or re-evaluated."""
        with self._receipts_lock:
            records = [dict(rec) for rec in self._ask_records]
            totals = dict(self._cloud_totals)
        with self._identity_lock:
            events = list(self._identity_events)
            pins = dict(self._identity_pins or {})
        statuses = ('determined', 'underdetermined', 'contradictory', 'unassessed')
        asks = []
        for rec in records:
            entry = {'line': rec['line'], 'name': rec['name'], 'occurrence': rec['occurrence'],
                     **({'index': rec['index']} if 'index' in rec else {}), 'status': rec['status']}
            if rec['status'] == 'unassessed':
                entry['reason'] = rec['reason']
            else:
                entry.update({k: rec[k] for k in ('domain', 'exhaustive', 'method', 'passing', 'passing_count',
                                                  'passing_truncated', 'checks', 'checks_truncated', 'cost')})
            entry.update(answered_by=rec['answered_by'], solve_mode=rec['solve_mode'])
            if rec.get('_finite_fallback'):
                entry['finite_fallback'] = rec['_finite_fallback']
            if rec.get('_constructor'):
                entry['constructor'] = rec['_constructor']
            if rec.get('rejected_by_check'):
                entry['rejected_by_check'] = True       # delivered, then rejected by its anchored check: not answered
            asks.append(entry)
        summary = {status: sum(1 for rec in records if rec['status'] == status) for status in statuses}
        determinacy = {'version': RECEIPTS_VERSION, 'summary': summary, 'asks': asks[:LIST_MAX['asks']],
                       'asks_truncated': len(asks) > LIST_MAX['asks']}
        behaviours = [rec['_code'] for rec in records if rec.get('_code')]
        code_behavior = {'version': RECEIPTS_VERSION, 'asks': behaviours[:LIST_MAX['asks']],
                         'asks_truncated': len(behaviours) > LIST_MAX['asks']}
        check, version = _identity_checker()
        # policy: the validated host model_pins; strict: whether strict enforcement applied to this execution's calls
        # (not in a lock replay). Both null only when an invalid policy refused the invocation before anything ran.
        identity = _identity_block(events, pins, basis='recorded_at_report',
                                   strict=None if self.model_pins is None else self._strict_pins(),
                                   checker_version=version, checker_available=check is not None,
                                   extra={'policy': self.model_pins})
        ladders = [rec['_escalation'] for rec in records if rec.get('_escalation')]
        accepted = [ladder for ladder in ladders if ladder['accepted']]
        rungs: dict = {}
        for ladder in accepted:
            key = (ladder['rung'], ladder['applicator'], ladder['locality'])
            rungs[key] = rungs.get(key, 0) + 1
        by_rung = [{'rung': rung, 'applicator': app, 'locality': locality, 'accepted': n}
                   for (rung, app, locality), n in sorted(rungs.items())]
        # asks, outcomes and rungs: the escalated executions that stand (an ensure-retry rolls a rejected one back:
        # rolled_back counts those); the cloud totals: every escalation of the run, rolled back or not (a charge is
        # never given back by a rollback)
        escalation = {'version': RECEIPTS_VERSION, 'asks': len(ladders),
                      'local_only_success': sum(1 for ladder in accepted if ladder['locality'] == 'local'
                                                and ladder['cloud_dispatches_charged'] == 0),
                      'cloud_accepted': sum(1 for ladder in accepted if ladder['locality'] == 'cloud'),
                      'failed': len(ladders) - len(accepted),
                      'cloud_dispatches_charged': totals['charged'],
                      'cloud_refused_pre_dispatch': totals['refused'],
                      'rolled_back': totals['rolled_back'],
                      'by_rung': by_rung[:LIST_MAX['by_rung']], 'by_rung_truncated': len(by_rung) > LIST_MAX['by_rung']}
        answered = [rec['answered_by'] for rec in records]
        summary_line = {'version': RECEIPTS_VERSION, **summary,
                        'answered_by_kernel': answered.count('kernel'), 'answered_by_model': answered.count('model'),
                        'unanswered': answered.count(None),
                        'local_only_success': escalation['local_only_success'],
                        'cloud_accepted': escalation['cloud_accepted'],
                        'cloud_dispatches_charged': escalation['cloud_dispatches_charged'],
                        'drift_events': sum(1 for event in events if event['drift'] is not None),
                        'identity_unverifiable': sum(1 for event in events if event['status'] == 'unverifiable'),
                        'behavior_scope': 'declared_tests_only'}
        if self._finite_plans:
            summary_line['answered_by_finite_fallback'] = answered.count('finite_fallback')
        if self.constructor_policy['mode'] != 'off':
            summary_line['answered_by_constructor'] = answered.count('constructor')
        return {'determinacy': determinacy, 'code_behavior': code_behavior, 'model_identity': identity,
                'escalation': escalation, 'determinism_summary': summary_line}

    def _constructor_checkpoint(self) -> None:
        """Retain possible activity before an intent, including when the process dies in dispatch."""
        self._constructor_activity = True
        self._save_state()

    def _save_state(self, report=None) -> None:
        if not self.store.dir:
            return
        progress_outputs = self.opts.get('progress_outputs') is True
        # Capture and write under one ordering lock. A periodic worker snapshot
        # captured before a rollback cannot overwrite that rollback's snapshot.
        with self.lock if progress_outputs else nullcontext():
            data = report or {'program': self.program, 'status': self.status, 'asks': self.asks, 'calls': self.calls,
                              'progress': [self.no, self.total], 'seconds': round(time.time() - self.started, 2)}
            if report is None and progress_outputs:
                maximum, byte_limit = 128, 1_048_576
                kept, used = [], 2
                encoder = json.JSONEncoder(ensure_ascii=False, indent=1, default=str)
                for row in reversed(self.outputs[-maximum:]):
                    size = 0
                    try:
                        # A separately wrapped row conservatively includes its
                        # actual nested indentation and the list separators.
                        for part in encoder.iterencode({'outputs': [row]}):
                            remaining = byte_limit - used - size
                            if len(part) > remaining:
                                size = byte_limit + 1
                                break
                            size += len(part.encode('utf-8'))
                            if size > byte_limit - used:
                                break
                    except (TypeError, ValueError, UnicodeError, RecursionError):
                        size = byte_limit + 1
                    if size > byte_limit - used:
                        break  # Keep a contiguous suffix; never display an older substitute.
                    kept.append(row)
                    used += size
                kept.reverse()
                total = len(self.outputs)
                data['outputs'] = kept
                data['outputs_progress'] = {'version': 1, 'partial': True, 'total': total,
                    'included': len(kept), 'omitted': total - len(kept), 'start_index': total - len(kept),
                    'max_outputs': maximum, 'max_bytes': byte_limit, 'rollback_possible': True}
            data['progress'] = [min(self.no, self.total), self.total]
            data['updated'] = time.time()
            if self.constructor_policy['mode'] != 'off':
                data['constructor_bridge'] = 2  # this writer checkpoints possible work before every intent
            if self._constructor_activity:
                data['constructor_activity'] = {'version': 1, 'attempt_possible': True}
                self.store.save('state.json', data, durable=True)
            else:
                self.store.save('state.json', data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat(stmts):
    for s in stmts:
        yield s
        if s.k == 'if':
            for _c, body in s.branches:
                yield from _flat(body)
            if s.else_body:
                yield from _flat(s.else_body)
        elif s.k == 'for' or (s.k in S.EXTENSIONS and S.EXTENSIONS[s.k].block):
            yield from _flat(s.body)


def _returns_from(stmts) -> bool:
    """Whether a block can leave the routine it is in: a routine `return` in it or in its if/for blocks (the blocks
    symblic.lang.abstraction rewrites; a routine defined inside returns from itself)."""
    for s in stmts or ():
        if s.k == 'routine-return':
            return True
        if s.k == 'if':
            if any(_returns_from(body) for _c, body in s.branches) or _returns_from(s.else_body):
                return True
        elif s.k == 'for' and _returns_from(s.body):
            return True
    return False


def _lit_preds(body) -> set:
    return {lit.pred for lit in body or () if getattr(lit, 'k', '') in ('lit_pos', 'lit_neg')}


def _queried(node) -> set:
    """Predicates an expression queries (query / holds)."""
    out = set()

    def visit(n):
        if isinstance(n, (list, tuple)):
            for x in n:
                visit(x)
        elif isinstance(n, dict):
            for x in n.values():
                visit(x)
        elif isinstance(n, S.Node):
            if n.k == 'query':
                out.add(n.pred)
            for x in n.__dict__.values() if hasattr(n, '__dict__') else ():
                visit(x)
    visit(node)
    return out


def _queried_in(s) -> set:
    try:
        return _queried(S._reads_of(s))
    except Exception:  # noqa: BLE001  (a statement kind without reads)
        return set()


def _statement_reads(s):
    try:
        return S._reads_of(s)
    except Exception:  # noqa: BLE001  (a statement kind without reads)
        return None


def _closure(preds: set, deps: dict) -> set:
    out, todo = set(), list(preds)
    while todo:
        p = todo.pop()
        if p in out:
            continue
        out.add(p)
        todo.extend(deps.get(p, ()))
    return out


def _fact_names(s) -> set:
    """Bare names in a fact statement's arguments: atoms, or bound names the kernel substitutes."""
    if s.k == 'fact':
        return {a.name for _p, args in s.atoms for a in args if getattr(a, 'k', '') == 'name'}
    if s.k == 'for':
        out = set()
        for t in s.body:
            out |= _fact_names(t)
        return out
    return set()


def _binds(s) -> list:
    if s.k == 'fact':
        return ['#fact:' + pred for pred, _args in s.atoms]
    if s.k in ('let', 'given', 'ask', 'group'):
        return [s.name]
    if s.k in S.EXTENSIONS:
        return list(S.EXTENSIONS[s.k].binds(s))
    if s.k == 'delegate' and s.name:
        return [s.name]
    if s.k == 'if':
        out = []
        for _c, body in s.branches:
            for t in body:
                out += _binds(t)
        for t in s.else_body or ():
            out += _binds(t)
        return out
    if s.k == 'for':
        out = []
        for t in s.body:
            out += [n for n in _binds(t) if n != s.var]
        return out
    return []


# Optional failure diagnostics have their own small resource envelope. D.explain already limits its final
# text, but S.show builds a value before clipping it; bound the expression and expanded input values first.
_DIAGNOSTIC_ITEMS = 512
_DIAGNOSTIC_CHARS = 8192
_DIAGNOSTIC_BITS = 32768
_DIAGNOSTIC_DEPTH = 24
_DIAGNOSTIC_STEPS = 2000
_DIAGNOSTIC_CALLS = frozenset({
    'len', 'length', 'sum', 'product', 'mean', 'average', 'median', 'min', 'max',
    'abs', 'round', 'floor', 'ceil', 'count', 'first', 'last', 'keys', 'text', 'number',
    'contains', 'starts_with', 'ends_with', 'hash',
})
_DIAGNOSTIC_NUMERIC_CALLS = frozenset({
    'len', 'length', 'sum', 'product', 'mean', 'average', 'median', 'abs', 'round',
    'floor', 'ceil', 'count', 'number',
})


def _diagnostic_size(values):
    """Inspect only exact kernel containers/scalars, without formatting or expanding a wide container.

    Repeated references count repeatedly: a compact DAG must not expand into a huge S.show string. Cycles,
    unknown host objects and deeply nested values are refused without calling their str/repr methods.
    """
    left, chars, bits = _DIAGNOSTIC_ITEMS, _DIAGNOSTIC_CHARS, _DIAGNOSTIC_BITS
    stack = [(values, 0)]
    while stack:
        value, depth = stack.pop()
        left -= 1
        if left < 0 or depth > _DIAGNOSTIC_DEPTH:
            return False
        ty = type(value)
        if value is None or ty is bool:
            continue
        if ty is int:
            bits -= value.bit_length()
        elif ty is Fraction:
            bits -= value.numerator.bit_length() + value.denominator.bit_length()
        elif ty in (str, S.Svg):
            chars -= len(value)
        elif ty in (tuple, list, frozenset, S.ValueSet):
            if len(value) > left - len(stack):
                return False
            stack.extend((x, depth + 1) for x in value)
        elif ty is dict:
            if len(value) * 2 > left - len(stack) or any(type(key) is not str for key in value):
                return False
            stack.extend((x, depth + 1) for pair in value.items() for x in pair)
        else:
            return False
        if chars < 0 or bits < 0:
            return False
    return True


def _diagnostic_numeric(node, env, local):
    """A conservative shape guard for overloaded +/*, not an evaluator or a type checker.

    Numeric leaves cannot concatenate/repeat containers. Absent bindings are safe to refuse in the isolated
    diagnostic environment; quantifier locals have unknown types here, so do not assume they are numbers.
    """
    if node.k == 'num':
        return True
    if node.k == 'name':
        if node.name in local:
            return False
        binding = env.lookup(node.name)
        return binding is None or type(binding.value) in (int, Fraction)
    if node.k == 'un':
        return node.op in ('+', '-') and _diagnostic_numeric(node.a, env, local)
    if node.k == 'bin':
        return (node.op in ('+', '-', '*', '/', '//', 'mod', '^')
                and _diagnostic_numeric(node.a, env, local) and _diagnostic_numeric(node.b, env, local))
    return node.k == 'call' and node.fn in _DIAGNOSTIC_NUMERIC_CALLS


def _answer_only_contract(ask_name, plan):
    """Error text is model-visible only if every read is authorized at that point in the contract.

    A later let must not retroactively make an inherited input answer-derived at an earlier check. Keep
    the existing conservative whole-contract rule, but grow its authority only after each safe let.
    """
    derived = {ask_name}
    checks = {id(e) for e in plan['ensures']}
    steps = list(plan['between'])
    steps.extend(e for e in plan['ensures'] if not any(e is t for t in steps))
    for stmt in steps:
        if stmt.k == 'let':
            if not D.answer_only(stmt.value, derived):
                return False
            derived.add(stmt.name)
        elif id(stmt) in checks and not D.answer_only(stmt.cond, derived):
            return False
    return True


def _bounded_explanation(cond, env, kb, derived=None):
    """Reuse D.explain inside a bounded, read-isolated envelope; optional refusal never changes a check.

    derived=None is author-facing (visible condition inputs may be shown). Model feedback always supplies
    D.derived_names; only those bindings enter the diagnostic environment. The original constant-shadowing
    and D.explain/answer-only rules still apply. No query, helper, adapter, dynamic eval, interpolation or
    unbounded text/container constructor is evaluated for diagnostics.
    """
    try:
        with S.capture_binding_reads(None, scope=True):
            # Bound traversal before recursive D.names/pure and _expr_text. Container widths are checked
            # before extending the work list; source text and exact integers share the same bounded scan.
            nodes, flat, stack = [], [], [(cond, 0)]
            visited = 0
            while stack:
                value, depth = stack.pop()
                visited += 1
                if visited > _DIAGNOSTIC_ITEMS or depth > _DIAGNOSTIC_DEPTH:
                    return ''
                if isinstance(value, S.Node):
                    nodes.append(value)
                    value = vars(value)
                if type(value) is dict:
                    if len(value) * 2 > _DIAGNOSTIC_ITEMS - visited - len(stack):
                        return ''
                    # Keyword/record names are source text too; charge keys before diagnostic formatting.
                    stack.extend((x, depth + 1) for pair in value.items() for x in pair)
                elif type(value) in (tuple, list):
                    if len(value) > _DIAGNOSTIC_ITEMS - visited - len(stack):
                        return ''
                    stack.extend((x, depth + 1) for x in value)
                else:
                    flat.append(value)
            if not _diagnostic_size(flat) or any(env.lookup(c) is not None for c in S.CONSTANTS):
                return ''
            allowed = D.names(cond)
            if derived is not None:
                allowed.intersection_update(derived)
            isolated = S.Env()
            for name in allowed:
                binding = env.lookup(name)
                if binding is not None:
                    isolated.vars[name] = binding
            # Count each syntactic read, not just each distinct binding (S.show expands shared values).
            values = [isolated.vars[n.name].value for n in nodes if n.k == 'name' and n.name in isolated.vars]
            if not _diagnostic_size(values):
                return ''
            local = {n.var for n in nodes if n.k == 'quant'}
            for node in nodes:
                if node.k not in ('num', 'lit', 'str', 'name', 'attr', 'index', 'list', 'set', 'record',
                                   'un', 'bin', 'cmp', 'quant', 'call'):
                    return ''
                if node.k == 'str' and not all(type(part) is str for part in node.parts):
                    return ''
                if node.k == 'bin':
                    if node.op not in ('+', '-', '*', '/', '//', 'mod', '^', 'and', 'or', '->', '<->', 'xor'):
                        return ''
                    if node.op in ('+', '*') and not _diagnostic_numeric(node, isolated, local):
                        return ''
                if node.k == 'call':
                    if node.fn not in _DIAGNOSTIC_CALLS:
                        return ''
                    # text of a constructed/nested container can amplify escaping at each level. Direct
                    # bounded values and numeric expressions cannot; other forms simply get no detail.
                    if node.fn == 'text':
                        for arg in [*node.args, *node.kwargs.values()]:
                            ref = arg
                            while ref.k in ('attr', 'index'):
                                ref = ref.obj
                            if ref.k not in ('name', 'num', 'lit') and not _diagnostic_numeric(arg, isolated, local):
                                return ''
            return D.explain(cond, isolated, kb, allowed, steps=_DIAGNOSTIC_STEPS)
    except Stopped:
        raise
    except Exception:  # noqa: BLE001  (a diagnostic-only refusal preserves the original failure)
        return ''


def _src(s) -> str:
    return _expr_text(s.cond)


def _expr_text(n) -> str:
    """A compact readable rendering of an expression (for messages)."""
    if not isinstance(n, S.Node):
        return str(n)
    k = n.k
    if k == 'num':
        return S.num_text(n.value)
    if k == 'lit':
        return S.show(n.value)
    if k == 'str':
        return json.dumps(''.join(p if isinstance(p, str) else '{' + _expr_text(p) + '}' for p in n.parts))
    if k == 'name':
        return n.name
    if k == 'bin':
        return f'{_expr_text(n.a)} {n.op} {_expr_text(n.b)}'
    if k == 'un':
        return f'{n.op} {_expr_text(n.a)}' if n.op == 'not' else f'{n.op}{_expr_text(n.a)}'
    if k == 'cmp':
        out = _expr_text(n.parts[0])
        for op, p in zip(n.ops, n.parts[1:]):
            out += f' {op} {_expr_text(p)}'
        return out
    if k == 'call':
        args = [_expr_text(a) for a in n.args] + [f'{key}={_expr_text(v)}' for key, v in n.kwargs.items()]
        return f'{n.fn}({", ".join(args)})'
    if k == 'attr':
        return f'{_expr_text(n.obj)}.{n.name}'
    if k == 'index':
        return f'{_expr_text(n.obj)}[{_expr_text(n.idx)}]'
    if k == 'list':
        return '[' + ', '.join(_expr_text(x) for x in n.items) + ']'
    if k == 'set':
        return '{' + ', '.join(_expr_text(x) for x in n.items) + '}'
    if k == 'quant':
        return f'{n.q} {n.var} in {_expr_text(n.src)}: {_expr_text(n.body)}'
    if k == 'query':
        return f'query {n.pred}({", ".join(_expr_text(a) for a in n.args)})'
    return k


def _jsonish(v):
    """A kernel value as plain JSON (numbers exact where possible) for examples and answers."""
    if isinstance(v, bool) or v is None or isinstance(v, int):
        return v
    if S.is_num(v):
        return float(v) if v.denominator & (v.denominator - 1) == 0 or 10 ** 12 % v.denominator == 0 else S.num_text(v)
    if isinstance(v, (tuple, list)):
        return [_jsonish(x) for x in v]
    if isinstance(v, frozenset):
        return sorted((_jsonish(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(v, dict):
        return {k: _jsonish(x) for k, x in sorted(v.items())}
    return str(v)


def _known_text(v) -> str:
    """Exact selected value, distinct from the intentionally abbreviated UI display.

    A full canonical hash cannot substitute for missing digits or SVG source.
    Control characters and record keys are escaped as JSON text; no ancestor
    values are fetched here. Capsule packing charges the complete representation.
    """
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else f'{v.numerator}/{v.denominator}'
    if isinstance(v, str):
        return json.dumps(str(v), ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return '[' + ', '.join(_known_text(item) for item in v) + ']'
    if isinstance(v, frozenset):
        return '{' + ', '.join(_known_text(item) for item in sorted(v, key=S.canon_json)) + '}'
    if isinstance(v, dict):
        return ('{' + ', '.join(json.dumps(key, ensure_ascii=False) + ': ' + _known_text(item)
                               for key, item in sorted(v.items())) + '}') if v else '{:}'
    if v is None:
        return 'null'
    raise S.SymblicError('unsupported value in selected context', kind='context')


def _relevant(bindings, text: str, k: int) -> list:
    """Deterministic lexical retrieval: bindings whose name and value share the most words with the
    statement (ties: earlier binding first)."""
    want = set(re.findall(r'[a-z0-9]{3,}', text.lower()))
    scored = []
    for b in bindings:
        if b.weight <= 0:
            continue
        words = set(re.findall(r'[a-z0-9]{3,}', (b.name + ' ' + S.show(b.value, 2000)).lower()))
        score = len(want & words) + (2 if b.name.lower() in want else 0)
        if score:
            scored.append((-score, b.order, b))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [b for _s, _o, b in scored[:k]]


def _worse(a: str, b: str) -> str:
    order = ['exact', 'closed', 'structured', 'open', 'observed', 'effect']
    return a if order.index(a if a in order else 'open') >= order.index(b if b in order else 'open') else b


def _engine_effort(effort: str) -> str:
    return {'low': 'low', 'medium': 'medium', 'high': 'high', 'max': 'max', 'ultra': 'max'}.get(effort, '')


def _clip(text: str, n: int) -> str:
    text = ' '.join(str(text or '').split())
    return text if len(text) <= n else text[:n - 1] + '…'


def _short(v) -> str:
    return S.show(v, 60) if not isinstance(v, str) else v[:60]


def _ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)


# ---------------------------------------------------------------------------
# The runner process
# ---------------------------------------------------------------------------

def run_folder(folder: str, resume: bool = False, applicators=None) -> dict:
    """Run the program saved in folder (program.sym, meta.json): `python3 -m symblic.kernel.run --dir FOLDER`."""
    folder = os.path.abspath(folder)
    meta = _load(os.path.join(folder, 'meta.json'), {})
    try:
        with open(os.path.join(folder, 'program.sym'), encoding='utf-8') as f:
            source = f.read()
    except OSError as e:
        raise SystemExit(f'no program in {folder}: {e}')
    saved = dict(meta.get('options') or {})        # read exactly as the run below reads its options
    if meta.get('authoring') is not None or os.path.lexists(os.path.join(folder, 'instructions.english')):
        try:
            from symblic.english.authoring import validate_saved
            validate_saved(folder, source, meta)
        except (ImportError, S.SymblicError) as error:
            return {'status': 'failed', 'calls': 0, 'error': {'kind': 'version', 'line': 0, 'col': 0,
                    'message': str(error)}}
    try:
        validate_model_pins(saved.get('model_pins'))
        constructor_policy = validate_constructor_options(saved)
        constructor_records_gate(folder, mode=constructor_policy['mode'])
    except S.SymblicError:
        # An invalid saved model_pins policy refuses before ANY write or construction: no delegation refusal record,
        # no provider (Applicators), no signal handler, no fresh start, no log.txt line. The refusal report comes from
        # a Run that holds no folder (see Run.__init__); only stdout (the runner's log) carries the reason.
        report = Run(source, meta.get('inputs') or {}, None, saved, folder=folder).execute()
        try:
            sys.stdout.write(f'{time.strftime("%H:%M:%S")} {(report.get("error") or {}).get("message", "refused")}\n')
        except (OSError, ValueError):
            pass
        return report
    if meta.get('delegation') is not None:
        from symblic.delegate import run as delegation
        try:
            delegation.verify_declaration(meta['delegation'], source, meta.get('inputs'), meta.get('options'))
        except (ValueError, S.SymblicError, TypeError, KeyError) as exc:
            report = {'status': 'failed', 'calls': 0, 'error': {'kind': 'version', 'line': 0, 'col': 0,
                      'message': 'Delegation contract refused before dispatch: ' + str(exc)}}
            store = Store(folder)
            store.save('delegation-refusal.json', report)
            if not os.path.exists(os.path.join(folder, 'state.json')):
                store.save('state.json', report)
            return report
    if applicators is None:
        from symblic.providers import applicators as symblic_apply
        applicators = symblic_apply.Applicators(owner_label=meta.get('by_label') or 'operator',
                                                run_id=os.path.basename(folder))
    stop = threading.Event()

    def on_signal(*_a):
        stop.set()

    # SIGTERM and SIGINT ask the run to stop at its next safe point. The previous handlers come back when
    # run_folder returns, so an in-process caller (a test runner, a host process) keeps its own Ctrl-C.
    import signal
    previous = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            previous[signum] = signal.signal(signum, on_signal)
        except (ValueError, OSError):   # not the main thread: no handler, the caller keeps its own
            pass
    try:
        opts = dict(meta.get('options') or {})
        # a launched run is polled through symblic/run?id=: each output reaches state.json (the bounded snapshot)
        # when it is produced, not only in the completion report, unless the saved options say otherwise
        opts.setdefault('progress_outputs', True)
        opts['stop'] = stop
        if not resume:                      # the saved policy was validated above, before anything was constructed
            start_fresh(folder, pins=opts.get('execution_pins'), replay=bool(opts.get('replay')))
        out = sys.stdout

        def log(text):
            line = f'{time.strftime("%H:%M:%S")} {text}'
            try:
                out.write(line + '\n')
                out.flush()
            except OSError:
                pass
            run.store.log(text)

        run = Run(source, meta.get('inputs') or {}, applicators, opts, folder=folder, log=log)
        log(f'Symblic {S.VERSION}: {meta.get("title") or "program"} ({"resumed" if resume else "started"})')
        report = run.execute()
        if report.get('kernel_check'):
            log(report['error']['message'])     # a front end shows this log; state.json keeps the run's own status
        else:
            log(f'{report["status"]}: fingerprint {report["fingerprint"]}, {report["asks"]} asks, {report["calls"]} '
                f'calls ({report["cached"]} reused)' + (f' — {report["error"]["message"]}' if report.get('error') else ''))
        return report
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler if handler is not None else signal.SIG_DFL)


def _load(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Run a Symblic program folder.')
    ap.add_argument('--dir', required=True)
    ap.add_argument('--resume', action='store_true')
    a = ap.parse_args(argv)
    report = run_folder(a.dir, a.resume)
    return 0 if report['status'] == 'done' else 1


if __name__ == '__main__':
    # `python3 -m symblic.kernel.run` executes this file as __main__; run the canonical module instead, so every
    # other module that imports symblic.kernel.run sees the same classes (Run, Stopped, Store).
    from symblic.kernel import run as _canonical
    sys.exit(_canonical.main())
