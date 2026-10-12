"""Agent graphs, part 2: the durable executor. Run a frozen graph node by node through the ordinary Run.

What it is for
    GraphRun(frozen, folder, applicators, stop, effects=None).execute() runs a graph frozen by
    symblic.graph.planner, one attempt at a time, in a private folder. Every node attempt is an ordinary
    symblic.kernel.run.Run of the node's compiled program with execution pins and the 'verified' profile, using
    exactly the applicator its frozen route names (refused otherwise: no fallback route, no nested council,
    no tool use, local-only routes stay local). Inputs flow between nodes as evidence envelopes and claim
    lineage (symblic.kernel.epistemic), never as trusted text.

    Durability rules, all tested with crash points:
    - The folder holds graph-pins.json (graph, policy, kernel identity, source hashes, capability catalogue),
      graph-events.jsonl (the planner ledger) and attempts/ (one native run folder per attempt, plus
      graph-calls.jsonl, an intent-before-dispatch journal of model calls).
    - A model call is journaled as an intent before it is sent. An intent without a recorded outcome is
      'unknown' after a crash and is never sent again automatically; known outcomes are replayed.
    - Effects (observe/act) run only through a host object you pass (idempotent by ID, with a capability
      catalogue); an unfinished effect is never performed twice.
    - A stop either cancels durably (when the stop object says the cancel was requested) or interrupts, in
      which case nothing stop-caused is recorded and execute() can resume the open attempt.
    - A process that loaded different graph code than the bytes on disk refuses to continue (see GRAPH_FILES).

What it is not
    It is not a distributed scheduler: one process runs one graph sequentially under an flock. There is no
    exactly-once guarantee for external calls; an unfinished call is reported as unknown instead.

Depends on: symblic.kernel (language, run, effects, epistemic, execution_pins), symblic.graph.planner, and
symblic.js.check (asset identity). You inject the applicators (symblic.providers or a fake) and, optionally,
an effects host. Used by: symblic.policy.graph and the original host's job runner
(integration/host/symblic_graph_api.py). Status: prototype; tested with fake applicators and fake hosts only.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import sys
import threading
from collections import OrderedDict, defaultdict
from contextlib import contextmanager, nullcontext
from pathlib import Path

from symblic.kernel import language as S
from symblic.kernel import effects as FX
from symblic.kernel import epistemic as EP
from symblic.kernel import execution_pins as X
from symblic.graph import planner as G
from symblic.kernel.run import Run, Store

_SOURCE_SHA256, _SOURCE_LOADED = G._import_identity(__file__, sys._getframe(0).f_code)

VERSION = 1
MAX_FILE_BYTES = X.MAX_BYTES
# The graph modules whose bytes every graph's pins record, as registry paths relative to X.BASE (the folder
# that holds the symblic package). Graph code is absent from the kernel's execution registry
# (symblic.kernel.execution_pins). Each graph module records the bytes it was loaded from at its own import
# boundary, and whether the executing code is their compilation. Pins bind those identities: disk must still
# equal every loaded copy before any pin or cached check is used. (In the original host the host's graph
# adapter, now integration/host/symblic_graph_api.py, was pinned too; it is not part of this package.)
GRAPH_FILES = ('symblic/graph/planner.py', 'symblic/graph/run.py')
_GRAPH_HASHES = {'symblic/graph/planner.py': G._SOURCE_SHA256, 'symblic/graph/run.py': _SOURCE_SHA256}
_GRAPH_LOADED = {'symblic/graph/planner.py': G._SOURCE_LOADED, 'symblic/graph/run.py': _SOURCE_LOADED}
# The event ledger must stay readable by _read. An attempt starts only while its
# completion (one planner row at most) and one closing row still fit.
LEDGER_FILE_BYTES = MAX_FILE_BYTES
ROW_RESERVE = G.MAX_BYTES + 1
CLOSING_RESERVE = 1024
# Room kept in an attempt's call journal for the receipt of an issued call.
JOURNAL_RESERVE = 4096
# The root (without attempts/) and each attempt folder are bounded and walked
# separately, so opening one attempt never rescans the others.
ROOT_TREE_LIMIT = 1024
ATTEMPT_TREE_LIMIT = 1024
ATTEMPT_DIR_LIMIT = G.MAX_CALLS + 64
# Uncommitted atomic-write temps: .NAME.PID.tmp (native Store) or .NAME.PID.HEX.tmp.
_TEMP = re.compile(r'\..+\.\d+(?:\.[0-9a-f]+)?\.tmp\Z')


class Unsupported(G.GraphError):
    """A declared capability cannot safely be supplied by this adapter."""


class Uncertain(G.GraphError):
    """A dispatch may have happened; recovery cannot repeat it automatically."""


class Interrupted(RuntimeError):
    """Stopped without an owner cancellation. Nothing stop-caused was recorded;
    executing again resumes the open attempt, replaying its known outcomes."""


class Superseded(RuntimeError):
    """A newer launch generation owns this job; this worker dispatches and commits nothing more."""


def _json(value):
    try:
        return X._json(value)
    except (S.SymblicError, RecursionError, UnicodeError) as exc:
        raise G.GraphError('invalid bounded adapter JSON') from exc


def _hash(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _seal(body):
    return {**body, 'sha256': _hash(body)}


def _unseal(value):
    if type(value) is not dict or value.get('sha256') != _hash({k: v for k, v in value.items() if k != 'sha256'}):
        raise G.GraphError('corrupt adapter receipt')
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise G.GraphError('duplicate JSON field')
        result[key] = value
    return result


def _decode(raw):
    try:
        def invalid(_):
            raise G.GraphError('nonfinite JSON')
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)
        _json(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise G.GraphError('corrupt adapter JSON') from exc


def _read(path, *, lines=False, missing=False):
    path = Path(path)
    if path.is_symlink():
        raise G.GraphError('symlinked graph file refused')
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        if missing:
            return [] if lines else None
        raise G.GraphError('required graph file missing: ' + path.name) from None
    if len(raw) > MAX_FILE_BYTES:
        raise G.GraphError('graph file limit: ' + path.name)
    if not lines:
        return _decode(raw)
    if raw and not raw.endswith(b'\n'):
        raise G.GraphError('partial ledger row: ' + path.name)
    chunks = raw.splitlines()
    if len(chunks) > G.MAX_EVENTS or any(not line.strip() for line in chunks):
        raise G.GraphError('invalid/oversized ledger: ' + path.name)
    return [_decode(line) for line in chunks]


def _sync_directory(folder):
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(descriptor, raw):
    view = memoryview(raw)
    while view:
        view = view[os.write(descriptor, view):]


def _write_file(folder, name, raw):
    """Crash-atomic durable replace: write and fsync a private temp, rename, fsync the folder."""
    folder = Path(folder)
    if (folder / name).is_symlink():
        raise G.GraphError('symlinked graph file refused')
    temp = folder / f'.{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp'
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temp, folder / name)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    _sync_directory(folder)


def _write_json(folder, name, value):
    _write_file(folder, name, _json(value))


def _save(store, name, value):
    _write_json(store.dir, name, value)


def _append(store, name, row):
    """Append one canonical row, then fsync the file and its folder."""
    raw = _json(row) + b'\n'
    path = Path(store.dir) / name
    if path.is_symlink():
        raise G.GraphError('symlinked ledger refused')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _sync_directory(store.dir)


def _line_bytes(row):
    return len(_json(row)) + 1


def _uncommitted(path):
    """A temp a killed writer left before its rename: never committed, never work."""
    return not path.is_symlink() and path.is_file() and _TEMP.fullmatch(path.name) is not None


def _discard_uncommitted(folder):
    # Callers hold the graph flock, the only lock under which these folders are written.
    for path in Path(folder).iterdir():
        if _uncommitted(path):
            path.unlink()


def _mkdir_private(path):
    """Create missing directories 0700 whatever the umask, syncing each new entry."""
    path = Path(path)
    missing = []
    while not path.is_dir():
        if path.is_symlink() or path.exists():
            raise G.GraphError('private graph folder is not a directory')
        missing.append(path)
        path = path.parent
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            if directory.is_symlink() or not directory.is_dir():
                raise G.GraphError('private graph folder is not a directory') from None
            continue
        os.chmod(directory, 0o700)
        _sync_directory(directory.parent)


def _safe_tree(folder, limit=ATTEMPT_TREE_LIMIT, *, skip=()):
    """Refuse redirected or oversized files before the tolerant native Store opens them."""
    folder = Path(folder)
    count = 0
    for root, dirs, files in os.walk(folder, followlinks=False):
        here = Path(root)
        if len(here.relative_to(folder).parts) > 24:
            raise G.GraphError('graph directory depth limit')
        for name in dirs + files:
            count += 1
            path = here / name
            if count > limit:
                raise G.GraphError('graph directory entry limit')
            if path.is_symlink():
                raise G.GraphError('symlinked graph path refused')
            if path.is_file() and path.stat().st_size > MAX_FILE_BYTES:
                raise G.GraphError('graph file byte limit')
        if here == folder:
            dirs[:] = [name for name in dirs if name not in skip]


def _safe_listing(folder, limit):
    """Bounded shallow check of attempts/; each attempt is walked when it is opened."""
    count = 0
    with os.scandir(folder) as entries:
        for entry in entries:
            count += 1
            if count > limit:
                raise G.GraphError('graph attempt directory limit')
            if entry.is_symlink():
                raise G.GraphError('symlinked graph path refused')
            if entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_size > MAX_FILE_BYTES:
                raise G.GraphError('graph file byte limit')


class _LRU:
    """Bounded process cache of verified deterministic results under exact identity keys."""

    def __init__(self, limit):
        self.limit, self.items, self.lock = limit, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            value = self.items.get(key)
            if value is not None:
                self.items.move_to_end(key)
            return value

    def put(self, key, value):
        with self.lock:
            self.items[key] = value
            self.items.move_to_end(key)
            while len(self.items) > self.limit:
                self.items.popitem(last=False)


# Execution pin digests and static-check passes, keyed by the runtime identity
# (all registered module/library bytes, kernel identity, runtime assets) plus the
# exact source, inputs and capabilities. Only digests and flags are retained.
_PINS = _LRU(8192)
_CHECKS = _LRU(1024)


def _loaded_graph_modules():
    """name -> [(sha256, attested)] for every loaded copy of a pinned graph module,
    including a worker's __main__; a copy without an import identity is unattested."""
    found = defaultdict(list)
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if type(path) is not str or not path.endswith(GRAPH_FILES):
            continue
        try:
            resolved = Path(path).resolve()
        except OSError:
            continue
        if not resolved.is_relative_to(X.BASE):
            continue
        name = resolved.relative_to(X.BASE).as_posix()
        if name in GRAPH_FILES:
            found[name].append((getattr(module, '_SOURCE_SHA256', None),
                                getattr(module, '_SOURCE_LOADED', False)))
    return found


def _asset_identity():
    """Exact bytes of runtime assets outside the Python registry: the JS runner and
    its sandbox, which execution pins may record. Absence is recorded, never bypassed.
    A host startup-asset registry can extend this identity."""
    from symblic.js import check as JS
    identity = {}
    for label in ('RUNNER', 'SANDBOX'):
        path = getattr(JS, label, None)
        try:
            with open(path, 'rb') as stream:
                raw = stream.read(MAX_FILE_BYTES + 1)
            identity[label] = hashlib.sha256(raw).hexdigest()
        except (OSError, TypeError):
            identity[label] = None
    return identity


def _audit(value):
    """Preserve finite report floats as tagged decimal text in exact envelopes."""
    # Bound before recursion; values come from native JSON receipts/reports.
    _json(value)
    def convert(v):
        if type(v) is float:
            if not math.isfinite(v):
                raise G.GraphError('nonfinite audit number')
            return {'finite_float_repr': repr(v)}
        if type(v) is dict:
            return {k: convert(item) for k, item in v.items()}
        if type(v) is list:
            return [convert(item) for item in v]
        return v
    return G.snapshot(convert(value))


def _output(value, depth=0, budget=None):
    """Exact JSON transport; never use the kernel's rounded display as a value."""
    budget = [50000] if budget is None else budget
    budget[0] -= 1
    if depth > 24 or budget[0] < 0:
        raise Unsupported('output data complexity limit')
    if type(value) in (str, bool, int) or value is None:
        return value
    if S.is_num(value):
        value = S.norm_num(value)
        if type(value) is int:
            return value
        raise Unsupported('nonintegral kernel output needs an explicit exact JSON contract')
    if isinstance(value, str):  # Code/text subtypes are transported as text.
        return str(value)
    if isinstance(value, (tuple, list, frozenset)):
        if len(value) > 10000:
            raise Unsupported('output collection limit')
        items = sorted(value, key=S.canon_json) if isinstance(value, frozenset) else value
        return [_output(item, depth + 1, budget) for item in items]
    if type(value) is dict and len(value) <= 10000 and all(type(key) is str for key in value):
        return {key: _output(item, depth + 1, budget) for key, item in value.items()}
    raise Unsupported('output binding is not exact JSON data')


def _schema(schema):
    """Refuse keywords the existing FX checker would otherwise silently ignore."""
    G.snapshot(schema)
    keywords = {'type', 'enum', 'const', 'properties', 'required', 'additionalProperties', 'items',
                'minItems', 'maxItems', 'minimum', 'maximum', 'minLength', 'maxLength',
                'title', 'description', '$schema'}
    types = {'integer', 'number', 'boolean', 'string', 'array', 'object', 'null'}

    def visit(s, depth=0):
        if depth > 24 or type(s) is not dict or s.keys() - keywords:
            raise Unsupported('output schema uses unsupported keywords/structure')
        if 'type' in s:
            declared = s['type'] if type(s['type']) is list else [s['type']]
            if not 1 <= len(declared) <= 7 or any(type(t) is not str or t not in types for t in declared):
                raise Unsupported('output schema type is invalid')
        for key in ('minItems', 'maxItems', 'minLength', 'maxLength'):
            if key in s:
                G.integer(s[key], 0, G.MAX_BYTES)
        for key in ('minimum', 'maximum'):
            if key in s and type(s[key]) is not int:
                raise Unsupported('schema numeric bounds must be exact JSON integers')
        if 'enum' in s and (type(s['enum']) is not list or not 1 <= len(s['enum']) <= 128):
            raise Unsupported('schema enum limit')
        if 'additionalProperties' in s and type(s['additionalProperties']) is not bool:
            raise Unsupported('schema additionalProperties must be boolean')
        if 'required' in s and (type(s['required']) is not list or len(s['required']) > 128
                               or any(type(k) is not str for k in s['required'])):
            raise Unsupported('schema required fields must be bounded text')
        if 'properties' in s:
            if type(s['properties']) is not dict or len(s['properties']) > 128:
                raise Unsupported('schema properties limit')
            for child in s['properties'].values():
                visit(child, depth + 1)
        if 'items' in s:
            visit(s['items'], depth + 1)
    visit(schema)


def _labels(value):
    """Conservative cross-node flow restriction; never erase provenance labels."""
    _json(value)
    private = False
    untrusted = False

    def visit(v):
        nonlocal private, untrusted
        if type(v) is dict:
            private |= type(v.get('sensitivity')) is str and v['sensitivity'] not in ('', 'public', 'none')
            untrusted |= v.get('untrusted') is True
            for child in v.values():
                visit(child)
        elif type(v) is list:
            for child in v:
                visit(child)
    visit(value)
    return private, untrusted


def _route(node, policy):
    route = G.choose_route(node, policy)
    if route['provider'] in ('council', 'kernel'):
        raise Unsupported('nested council/kernel dispatch cannot enforce a single graph route')
    if route['node'] in ('auto', ''):
        # 'auto' and an empty node let an applicator pick a machine; a graph route must name one.
        raise Unsupported('graph route requires an exact physical node')
    try:
        app = S.parse_applicator(route['provider'] + ':' + route['model'] + '@' + route['node'])
    except S.SymblicError as exc:
        raise Unsupported('route is not a registered Symblic applicator') from exc
    if any(app[field] != route[other] for field, other in
           (('engine', 'provider'), ('model', 'model'), ('node', 'node'))):
        raise Unsupported('route labels do not encode one exact applicator')
    actual_local = app['engine'] in S.LOCAL_APPLICATOR_ENGINES
    if actual_local != route['local'] or (node['allowed']['local_only'] and not actual_local):
        raise Unsupported('declared locality conflicts with actual applicator engine class')
    return route, S.app_label(app)


class _NodeRun(Run):
    """Carry host-recorded graph lineage through given bindings, without gold/data expansion."""

    def __init__(self, *args, graph_inputs, graph_reports, **kwargs):
        self.graph_inputs, self.graph_reports = graph_inputs, graph_reports
        super().__init__(*args, **kwargs)

    def _attach_epistemic(self, binding, statement, env):
        item = self.graph_inputs.get(binding.name) if statement.k == 'given' else None
        # Literal/seed envelopes are caller premises. Their content or supplied
        # evidence cannot forge a host-produced node attestation.
        if not item or 'origin' not in item:
            return super()._attach_epistemic(binding, statement, env)
        if item.get('status') != 'succeeded':
            return self._claim_for_binding(binding, origin='source_report', status='contested')
        records = [row for row in item['result']['evidence'] if row.get('scope') == 'symblic_run']
        if len(records) != 1 or not records[0].get('binding_epistemic'):
            # Older incomplete lineage remains explicitly unknown. It is never
            # promoted to an owner premise merely by traversing an edge.
            return self._claim_for_binding(binding, origin='source_report', status='unknown')
        record = records[0]
        epistemic = self.graph_reports[binding.name]['epistemic']
        claims = {row['id']: row for row in epistemic['claims']}
        views = {row['id']: row for row in epistemic['assessments']}
        selected = record['binding_epistemic']
        root = selected['claim']
        pending, seen = [EP.reference(root)], set()
        while pending:
            ref = pending.pop()
            if ref['id'] in seen:
                continue
            seen.add(ref['id'])
            claim, view = claims.get(ref['id']), views.get(ref['id'])
            if (claim is None or view is None or EP.reference(claim) != ref
                    or any(view.get(key) != value for key, value in ref.items())
                    or view.get('empirical_truth') != 'not_established'):
                raise G.GraphError('node epistemic lineage is incomplete or inconsistent')
            EP.validate_claim(claim)
            if claim['id'] in self._epistemic_claims and self._epistemic_claims[claim['id']] != claim:
                raise G.GraphError('conflicting cross-node claim identity')
            self._epistemic_claims[claim['id']] = claim
            self._epistemic_views[claim['id']] = view
            pending.extend(claim['dependencies'])
            # Runtime bounded summaries retain independent conservative roots.
            pending.extend(row['ref'] for row in view['conditional_on'])
        if root != claims[root['id']] or selected['assessment'] != views[root['id']]:
            raise G.GraphError('node output epistemic reference differs from its report')
        parent = S.Binding(root['content']['name'], None, meta={'epistemic': selected})
        self._claim_for_binding(binding, parents=[parent], origin='derived',
                                derivation={'operation': 'graph_value_transport', 'origin': item['origin'],
                                            'value_id': item['result']['value_id']})


class _Calls:
    """Intent-before-dispatch plus receipt-backed recovery around injected Apps.call.

    A call the stop interrupted gets an 'interrupted' receipt: it closes and
    charges the intent but is never replayed, so the resumed attempt asks again
    instead of repeating a stop-caused failure as the answer.
    """
    def __init__(self, store, apps, route, local_only, limit, context, source_sha256, stop, fence=None):
        self.store, self.apps, self.route = store, apps, route
        self.local_only, self.limit, self.context, self.stop = local_only, limit, context, stop
        self.fence = fence if fence is not None else nullcontext
        self.lock = threading.Lock()
        self.failure = None
        self.runner = None
        self.uncertain = False
        self.halted = False
        self.cursor = defaultdict(int)
        self.intents, self.replies, self.interrupted = {}, defaultdict(list), defaultdict(list)
        path = Path(store.path('graph-calls.jsonl'))
        self.rows = _read(path, lines=True, missing=True)
        self.journal_rows, self.journal_bytes = len(self.rows), path.stat().st_size if self.rows else 0
        for row in self.rows:
            _unseal(row)
            if type(row.get('version')) is not int or row['version'] != VERSION or row.get('context') != context:
                raise G.GraphError('call receipt context changed')
            index = row.get('index')
            G.integer(index, 1, limit)
            if row.get('kind') == 'intent':
                G.keys(row, ('version', 'context', 'kind', 'index', 'key', 'request_hash', 'sha256'))
                if index != len(self.intents) + 1 or index in self.intents:
                    raise G.GraphError('call intent order corrupted')
                if type(row['key']) is not str or type(row['request_hash']) is not str:
                    raise G.GraphError('invalid call identity')
                self.intents[index] = {'intent': row}
            elif row.get('kind') in ('outcome', 'interrupted'):
                G.keys(row, ('version', 'context', 'kind', 'index', 'key', 'request_hash', 'reply', 'sha256'))
                prior = self.intents.get(index)
                if (prior is None or 'reply' in prior or 'interrupted' in prior
                        or any(row[k] != prior['intent'][k] for k in ('key', 'request_hash'))):
                    raise G.GraphError('call outcome has no matching intent')
                self._validate_reply(row['reply'])
                if row['kind'] == 'outcome':
                    prior['reply'] = row['reply']
                    self.replies[row['key']].append(prior)
                else:
                    if row['reply']['ok']:
                        raise G.GraphError('an interrupted call receipt cannot carry an answer')
                    prior['interrupted'] = row['reply']
                    self.interrupted[row['key']].append(row['reply'])
            else:
                raise G.GraphError('invalid call ledger phase')
        self.uncertain = any('reply' not in item and 'interrupted' not in item for item in self.intents.values())
        # Store silently ignores corrupt JSONL. Verify its cache independently,
        # against the durable graph call receipts, BEFORE constructing Run.
        for native in _read(store.path('calls.jsonl'), lines=True, missing=True):
            if type(native) is not dict or type(native.get('key')) is not str or type(native.get('reply')) is not dict:
                raise G.GraphError('invalid native call cache')
            if native.get('source_sha256') != source_sha256 or type(native.get('ok')) is not bool:
                raise G.GraphError('native call source/status pin changed')
            if not native.get('ok') and native['reply'].get('refused') is True:
                continue  # native pre-dispatch refusal has no graph call intent
            if not native.get('ok') and any(item['intent']['key'] == native['key'] and 'reply' not in item
                                          and 'interrupted' not in item for item in self.intents.values()):
                continue  # native error represents the standing unknown intent
            matches = [item['reply'] for item in self.replies.get(native['key'], [])]
            if not native.get('ok'):
                matches += self.interrupted.get(native['key'], [])
            if not any(_hash(reply) == _hash(native['reply']) for reply in matches):
                raise G.GraphError('native call cache lacks a durable graph outcome')
        for name in ('trace.jsonl', 'call-events.jsonl', 'delegate-effects.jsonl'):
            if any(type(row) is not dict for row in _read(store.path(name), lines=True, missing=True)):
                raise G.GraphError('native event ledger row is not an object')
        _read(store.path('state.json'), missing=True)
        if _read(store.path('delegate-effects.jsonl'), lines=True, missing=True):
            raise Unsupported('delegation is outside the graph call contract')

    def _validate_app(self, request):
        app = request.get('app')
        if type(app) is not dict or any(app.get(key) != self.route[field] for key, field in
                                      (('engine', 'provider'), ('model', 'model'), ('node', 'node'))):
            raise Unsupported('source routing override violates the frozen graph route')
        actual_local = app['engine'] in S.LOCAL_APPLICATOR_ENGINES
        acquired_private = bool(self.runner and (self.runner._protected_acquired or any(
            _labels((b.meta or {}).get('evidence'))[0] for b in self.runner.kernel.env.all().values())))
        if acquired_private and not actual_local:
            raise Unsupported('protected acquisition cannot leave the local graph model lane')
        if app['engine'] in ('council', 'kernel') or actual_local != self.route['local'] or (self.local_only and not actual_local):
            raise Unsupported('nonlocal/nested model route refused before dispatch')
        if request.get('tools') != 'none':
            raise Unsupported('model tool execution requires the existing effects host, not Apps tools')

    def _validate_reply(self, reply):
        if type(reply) is not dict or type(reply.get('ok')) is not bool:
            raise G.GraphError('applicator gave an invalid reply')
        if reply.get('refused') is True and reply['ok']:
            raise G.GraphError('successful reply cannot also be a dispatch refusal')
        for name in ('model', 'node'):
            if name in reply and reply[name] != self.route[name]:
                raise Unsupported('applicator reported a different ' + name)
        if reply['ok'] and any(reply.get(name) != self.route[name] for name in ('model', 'node')):
            raise Unsupported('successful reply lacks exact observed model/node attribution')
        if 'engine' in reply and reply['engine'] != self.route['provider']:
            raise Unsupported('applicator reported a different provider')
        _json(reply)

    def call(self, request):
        # Run's sampling may use its thread pool even in a sequential graph.
        # Serialize the wrapper's reserve/call/outcome lane as well.
        with self.lock:
            try:
                self._validate_app(request)
            except G.GraphError as exc:
                self.failure = str(exc)
                return {'ok': False, 'fatal': True, 'refused': True, 'error': self.failure}
            if self.uncertain:
                self.failure = 'unfinished call intent; automatic redispatch refused'
                return {'ok': False, 'fatal': True, 'error': self.failure}
            clean = {k: v for k, v in request.items() if k != 'stop'}
            request_hash = _hash(clean)
            key = request.get('key')
            if type(key) is not str:
                raise G.GraphError('Run request lacks a stable call key')
            prior = self.replies.get(key, [])
            cursor = self.cursor[key]
            if cursor < len(prior):
                hit = prior[cursor]
                if hit['intent']['request_hash'] != request_hash:
                    raise G.GraphError('cached request differs under the same call key')
                self.cursor[key] += 1
                return json.loads(_json(hit['reply']))
            if self.stop.is_set():
                self.halted = True
                return {'ok': False, 'fatal': True, 'refused': True, 'error': 'graph stopped before dispatch'}
            if len(self.intents) >= self.limit:
                self.failure = 'attempt call budget exhausted across restarts'
                return {'ok': False, 'fatal': True, 'refused': True, 'error': self.failure}
            index = len(self.intents) + 1
            body = {'version': VERSION, 'context': self.context, 'index': index, 'key': key,
                    'request_hash': request_hash}
            intent = _seal({**body, 'kind': 'intent'})
            size = _line_bytes(intent)
            if (self.journal_rows + 2 > G.MAX_EVENTS
                    or self.journal_bytes + size + JOURNAL_RESERVE > MAX_FILE_BYTES):
                self.failure = 'attempt call journal is full; dispatch refused'
                return {'ok': False, 'fatal': True, 'refused': True, 'error': self.failure}
            try:
                # Admission: the durable intent, written while the launch generation
                # is current and the stop is clear. The fence's owner keeps that
                # generation current until this worker ends (JobStop's lifetime lock),
                # so the admitted call is never sent by a superseded generation. A
                # stop arriving after admission reaches the provider, which polls
                # the same stop; its reply then closes the intent as 'interrupted'.
                with self.fence():
                    if self.stop.is_set():
                        self.halted = True
                        return {'ok': False, 'fatal': True, 'refused': True, 'error': 'graph stopped before dispatch'}
                    _append(self.store, 'graph-calls.jsonl', intent)
            except Superseded:
                self.halted = True
                return {'ok': False, 'fatal': True, 'refused': True, 'error': 'superseded before dispatch'}
            self.journal_rows, self.journal_bytes = self.journal_rows + 1, self.journal_bytes + size
            self.intents[index] = {'intent': intent}
            self.uncertain = True
            try:
                reply = self.apps.call(request)
                self._validate_reply(reply)
            except Exception as exc:  # issued call: loss/invalid attribution cannot be known safe
                self.failure = 'issued model call has no reliable outcome: ' + type(exc).__name__ + ': ' + str(exc)[:400]
                return {'ok': False, 'fatal': True, 'error': self.failure}
            # Match exactly the fields the native call cache retains. Engine is
            # independently checked above; attribution remains in model/node.
            clean_reply = {k: v for k, v in reply.items() if k in
                           ('ok', 'json', 'text', 'error', 'fatal', 'refused', 'ms', 'node', 'model', 'meta')}
            if not (clean_reply.get('refused') is True and not clean_reply['ok']):
                clean_reply.pop('refused', None)
            clean_reply.setdefault('ms', 0)
            # Receipts below close an intent this generation already issued; they are
            # recorded even if a newer generation now owns the job (it replays them).
            # A stop-caused failure is 'interrupted': charged, never replayed.
            kind = 'interrupted' if not clean_reply['ok'] and self.stop.is_set() else 'outcome'
            receipt = _seal({**body, 'kind': kind, 'reply': clean_reply})
            if self.journal_bytes + _line_bytes(receipt) > MAX_FILE_BYTES:
                clean_reply = {k: clean_reply[k] for k in ('node', 'model', 'ms') if k in clean_reply}
                clean_reply.update(ok=False, fatal=True, error='model reply exceeds the graph call journal limit')
                self.failure = clean_reply['error']
                receipt = _seal({**body, 'kind': kind, 'reply': clean_reply})
            self._journal(receipt)
            if kind == 'interrupted':
                self.intents[index]['interrupted'] = clean_reply
                self.interrupted[key].append(clean_reply)
                self.uncertain = False
                self.halted = True
                return dict(clean_reply)
            self.intents[index]['reply'] = clean_reply
            self.replies[key].append(self.intents[index])
            self.cursor[key] += 1
            self.uncertain = False
            return dict(clean_reply)

    def _journal(self, row):
        size = _line_bytes(row)
        _append(self.store, 'graph-calls.jsonl', row)
        self.journal_rows, self.journal_bytes = self.journal_rows + 1, self.journal_bytes + size

    def delegate(self, *args, **kwargs):
        self.failure = 'graph delegation refused; use a declared contracted node'
        raise Unsupported(self.failure)


class _Host:
    """Forward only through the supplied existing host, preserving FX ownership."""
    idempotent_by_id = True

    def __init__(self, host, catalogue, stop, labels, fence=None):
        self.host, self.cat, self.stop = host, catalogue, stop
        self.private, self.untrusted = labels
        self.fence = fence if fence is not None else nullcontext
        self.halted = False

    def catalogue(self):
        return json.loads(_json(self.cat))

    def perform(self, effect, stop):
        # A denial is recorded by FX as 'failed' (it did not happen), so a resumed
        # attempt may still perform the effect; it never becomes the node result.
        if self.stop.is_set():
            self.halted = True
            return {'status': 'denied', 'error': 'graph stopped before capability dispatch'}
        spec = self.cat.get(effect['capability'], {})
        if (self.private and spec.get('egress')) or (self.untrusted and effect['kind'] == 'act'):
            return {'status': 'denied', 'error': 'cross-node provenance forbids this effect data flow'}
        if _hash(X._catalogue(self.host.catalogue())) != _hash(self.cat):
            return {'status': 'denied', 'error': 'host catalogue changed before capability dispatch'}
        refusal = self._admit()
        return refusal if refusal is not None else self.host.perform(effect, stop)

    def _admit(self):
        """Admit this perform: FX has already written its durable intent row; here
        the generation must still be current and the stop clear, checked together
        under the fence. The fence's owner keeps the generation current until this
        worker ends, so an admitted effect is never performed by a superseded one."""
        try:
            with self.fence():
                if self.stop.is_set():
                    self.halted = True
                    return {'status': 'denied', 'error': 'graph stopped before capability dispatch'}
        except Superseded:
            self.halted = True
            return {'status': 'denied', 'error': 'superseded before capability dispatch'}
        return None


class GraphRun:
    """Sequential durable scheduler using existing Run + injected registered Apps.

    ``execute()`` is idempotent for completed graphs and holds a per-graph flock
    across dispatch. ``checkpoint(stage, action)`` is an optional trusted observer
    for crash testing (exceptions are intentionally not swallowed).

    ``stop`` is the job cancellation signal. A stop exposing ``cancel_requested()``
    is a durable cancel only when that returns true (the owner's Stop); any other
    stop interrupts: nothing stop-caused is recorded and execute() raises
    Interrupted, leaving the open attempt resumable. A plain event remains a
    durable cancel. A stop exposing ``fence()`` (a context manager raising
    Superseded) guards every dispatch admission and every ledger/result/pins
    commit. Its owner must keep the admitted generation current until this
    worker ends; the original host's job runner (JobStop in
    integration/host/symblic_graph_api.py) does so with a worker lifetime lock,
    so no generation change can fall between an admission and its dispatch.
    """
    def __init__(self, frozen, folder, applicators, stop=None, *, effects=None,
                 reviewed_hashes=None, checkpoint=None):
        self.frozen = G.snapshot(frozen)
        G.Replay(self.frozen)
        self.folder = Path(os.path.abspath(os.fspath(folder)))
        if self.folder.is_symlink():
            raise G.GraphError('graph folder must not be a symlink')
        self.apps, self.stop, self.effects = applicators, stop if stop is not None else threading.Event(), effects
        if not callable(getattr(applicators, 'call', None)):
            raise Unsupported('inject registered Applicators.call explicitly')
        self.reviewed = G.snapshot(reviewed_hashes) if reviewed_hashes is not None else None
        self.checkpoint = checkpoint
        self.nodes = {n['id']: n for n in self.frozen['graph']['nodes']}
        _mkdir_private(self.folder)
        self.store = None
        self.replay = None
        self.rows = []
        self.ledger_bytes = 0

    @contextmanager
    def _locked(self):
        path = self.folder / '.graph.lock'
        if path.is_symlink():
            raise G.GraphError('symlinked graph lock refused')
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            _safe_tree(self.folder, ROOT_TREE_LIMIT, skip=('attempts',))
            if (self.folder / 'attempts').is_dir():
                _safe_listing(self.folder / 'attempts', ATTEMPT_DIR_LIMIT)
            self.store = Store(str(self.folder))
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _fence_factory(self):
        fence = getattr(self.stop, 'fence', None)
        return fence if callable(fence) else nullcontext

    def _fenced(self):
        return self._fence_factory()()

    def _observe(self, stage, action):
        if self.checkpoint is not None:
            self.checkpoint(stage, G.snapshot(action))

    def _metadata(self):
        files = {}
        loaded = _loaded_graph_modules()
        for name in sorted(X.PYTHON_FILES | X.LIBRARY_FILES.keys() | set(GRAPH_FILES)):
            if name in X.PYTHON_FILES - X.REQUIRED_FILES and not (X.BASE / name).exists():
                continue
            raw = X._read(name)
            files[name] = hashlib.sha256(raw).hexdigest()
            if name in _GRAPH_HASHES and (files[name] != _GRAPH_HASHES[name] or _GRAPH_LOADED[name] is not True):
                raise G.GraphError('graph module changed after process import; use a fresh worker')
            if any(sha != files[name] or attested is not True for sha, attested in loaded.get(name, ())):
                raise G.GraphError('a loaded graph module differs from its pinned source; use a fresh worker')
            if name in GRAPH_FILES and not X._bytecode_matches(name, raw):
                raise G.GraphError('graph cached bytecode differs from pinned source')
        if self.reviewed is not None and files != self.reviewed:
            raise G.GraphError('reviewed graph/runtime module hashes differ')
        cat = {}
        if any(n['effect_risk'] != 'none' for n in self.nodes.values()):
            if (self.effects is None or getattr(self.effects, 'idempotent_by_id', False) is not True
                    or not callable(getattr(self.effects, 'catalogue', None))
                    or not callable(getattr(self.effects, 'perform', None)) or not FX.SYNC):
                raise Unsupported('effectful graph requires existing durable idempotent-by-id host + catalogue/pins')
            cat = X._catalogue(self.effects.catalogue())
        return _seal({'version': VERSION, 'frozen': self.frozen, 'kernel': S.kernel_id(),
                      'files': files, 'capabilities': cat, 'scheduler': 'sequential_v1'})

    def _prepare(self, *, clean=False):
        metadata = self._metadata()
        prior = _read(self.folder / 'graph-pins.json', missing=True)
        if prior is None:
            # A temp left by a killed first pins write is not work: it was never renamed.
            if any(p.name not in ('.graph.lock', 'artifacts') and not _uncommitted(p) for p in self.folder.iterdir()):
                raise G.GraphError('graph folder contains work without durable graph pins')
        else:
            _unseal(prior)
            if _hash(prior) != _hash(metadata):
                raise G.GraphError('frozen graph/policy/runtime/capability pins changed')
        module_hashes = {k: v for k, v in metadata['files'].items()
                         if k in X.PYTHON_FILES or k in X.LIBRARY_FILES}
        libraries = {name: {'source': X._read(path).decode('utf-8'), 'sha256': metadata['files'][path]}
                     for path, name in X.LIBRARY_FILES.items()}
        self.metadata, self.module_hashes, self.libraries = metadata, module_hashes, libraries
        # Cached pins/check results are valid only for these exact runtime bytes.
        self.runtime_id = _hash({'files': metadata['files'], 'kernel': metadata['kernel'],
                                 'assets': _asset_identity()})
        # Refuse unsupported capability anywhere before any node can dispatch.
        for n in self.nodes.values():
            _route(n, self.frozen['policy'])
            _schema(n['output_schema'])
            if 'output_binding' not in n:
                raise Unsupported('durable node requires an explicit output_binding')
            if n['effect_risk'] != 'none' and n['retries']:
                raise Unsupported('effectful graph retries require cross-attempt effect identity recovery')
            bridge = G.compile_node(n, {k: None for k in n['inputs']}, libraries=libraries,
                                    allow_effects=n['effect_risk'] != 'none')
            self._pins(bridge)
            self._check(bridge['source'], metadata['capabilities'])
        if prior is None:
            with self._fenced():
                if clean:
                    _discard_uncommitted(self.folder)
                _save(self.store, 'graph-pins.json', metadata)
        events = self.folder / 'graph-events.jsonl'
        self.rows = _read(events, lines=True, missing=True)
        self.ledger_bytes = events.stat().st_size if self.rows else 0
        self.replay = G.Replay(self.frozen)
        for row in self.rows:
            self.replay.apply(row)
        state = self.replay.state()
        # Audit all historical attempts, even for completed/canceled graphs.
        states = {(s['iteration'], s['node']): s for s in state['states']}
        completions = {}
        for row in self.rows:
            if row['kind'] in ('succeeded', 'failed', 'unknown'):
                completions.setdefault((row['iteration'], row['node'], row['attempt']), row)
        audited = set()
        for row in self.rows:
            if row['kind'] != 'started':
                continue
            identity = (row['iteration'], row['node'], row['attempt'])
            if identity in audited:
                continue
            audited.add(identity)
            st = states[row['iteration'], row['node']]
            n = self.nodes[row['node']]
            action = {k: row[k] for k in ('node', 'iteration', 'attempt', 'route')}
            action.update(inputs=st['inputs'], call_limit=n['call_limit'], effect_risk=n['effect_risk'])
            if G.digest(action['inputs']) != row['inputs_hash']:
                raise G.GraphError('historical attempt inputs differ')
            attempt = self._attempt(action, existing=True)
            stored = attempt[-1]
            completion = completions.get(identity)
            if completion is not None:
                if stored is None:
                    if completion['kind'] != 'unknown' or not (attempt[-3].uncertain or attempt[-2]):
                        raise G.GraphError('completed attempt lacks a durable result')
                else:
                    expected = {k: completion[k] for k in ('kind', 'result', 'error', 'retryable', 'effect_known')
                                if k in completion}
                    if _hash(stored['result']) != _hash(expected):
                        raise G.GraphError('graph completion differs from durable attempt result')
        return state

    def _pins(self, bridge):
        """(digest, pins): execution pins for a compiled bridge. A cached digest
        under the same runtime identity returns pins None; build them if needed."""
        key = _hash(['execution-pins', self.runtime_id, bridge['source'], bridge['inputs'],
                     self.module_hashes, self.metadata['capabilities']])
        expected = _PINS.get(key)
        if expected is not None:
            return expected, None
        pins = X.build(bridge['source'], bridge['inputs'], self.module_hashes,
                       capabilities=self.metadata['capabilities'])
        expected = _hash(pins)
        _PINS.put(key, expected)
        return expected, pins

    def _check(self, source, catalogue):
        key = _hash(['static-check', self.runtime_id, source, catalogue])
        if _CHECKS.get(key):
            return
        # Same thread-local capability scope as FX.check, with the current
        # kernel's explicit execution_profile argument. Source cannot weaken it.
        prior = getattr(FX._LOCAL, 'cat', FX._UNSET)
        FX._LOCAL.cat = catalogue
        try:
            checked = S.check(source, execution_profile='verified')
        finally:
            if prior is FX._UNSET:
                del FX._LOCAL.cat
            else:
                FX._LOCAL.cat = prior
        if not checked['ok']:
            raise G.GraphError('node static check refused: ' + checked['errors'][0]['message'])
        _CHECKS.put(key, True)

    def _event(self, kind, **fields):
        self._commit(self.replay.event(kind, id=f'GraphEvent{self.replay.next_seq}', **fields))

    def _commit(self, row):
        # Validate against the incremental replay, append under the generation
        # fence, then fold: one row costs one validation, not a full re-derive.
        self.replay.apply(row, commit=False)
        size = _line_bytes(row)
        with self._fenced():
            _append(self.store, 'graph-events.jsonl', row)
        self.replay.apply(row)
        self.rows.append(row)
        self.ledger_bytes += size

    def _fits(self, started):
        """Room for this start, its completion and one closing row (cancel/capacity)."""
        return (self.replay.count + 3 <= G.MAX_EVENTS
                and self.ledger_bytes + _line_bytes(started) + ROW_RESERVE + CLOSING_RESERVE <= LEDGER_FILE_BYTES)

    def _recordable(self, result, fields):
        """A completion must remain one bounded planner row; refuse oversized results honestly."""
        if result['kind'] != 'succeeded':
            return result
        probe = {'version': G.VERSION, 'id': f'GraphEvent{G.MAX_EVENTS}', 'seq': G.MAX_EVENTS,
                 'graph_hash': self.frozen['graph_hash'], 'policy_hash': self.frozen['policy_hash'],
                 'kind': 'succeeded', **fields, 'result': result['result']}
        try:
            G.snapshot(probe)
        except G.GraphError:
            return {'kind': 'failed', 'error': 'node result exceeds the graph ledger row limit',
                    'retryable': False, 'effect_known': True}
        return result

    def _halt(self):
        """Stop handling: never records a stop-caused node outcome."""
        if getattr(self.stop, 'superseded', False):
            raise Superseded('a newer launch generation owns this graph job')
        requested = getattr(self.stop, 'cancel_requested', None)
        if requested is None or requested():
            self._event('cancel')
            return self.replay.state()
        raise Interrupted('graph stopped without an owner cancellation; resume continues the open attempt')

    def _attempt(self, action, existing=False):
        n = self.nodes[action['node']]
        inputs = {k: (item['result']['value'] if n['join'] == 'require_all' else item)
                  for k, item in action['inputs'].items()}
        bridge = G.compile_node(n, inputs, libraries=self.libraries, allow_effects=n['effect_risk'] != 'none')
        expected, pins = self._pins(bridge)
        folder = self.folder / 'attempts' / f'Iter{action["iteration"]:03d}_{action["node"]}_Attempt{action["attempt"]:02d}'
        if folder.is_symlink():
            raise G.GraphError('symlinked graph path refused')
        if not folder.is_dir():
            if existing:
                raise G.GraphError('recorded attempt folder missing')
            with self._fenced():
                _mkdir_private(folder / 'artifacts')
        _safe_tree(folder, ATTEMPT_TREE_LIMIT)
        prior = _read(folder / 'attempt-pins.json', missing=True)
        if prior is not None:
            # Equal to the sealed contract this runtime would write; the pins are
            # compared by digest, so an audit needs no second full build.
            _unseal(prior)
            G.keys(prior, ('version', 'graph_pins', 'action', 'bridge', 'execution_pins', 'sha256'))
            if (type(prior['version']) is not int or prior['version'] != VERSION
                    or prior['graph_pins'] != self.metadata['sha256'] or _hash(prior['action']) != _hash(action)
                    or _hash(prior['bridge']) != _hash(bridge) or _hash(prior['execution_pins']) != expected):
                raise G.GraphError('attempt source/input/runtime/routing pins changed')
            contract, pins = prior, prior['execution_pins']
        else:
            if existing:
                raise G.GraphError('recorded attempt pins missing')
            if any(p.name != 'artifacts' and not _uncommitted(p) for p in folder.iterdir()):
                raise G.GraphError('attempt work exists without pins')
            if pins is None:
                pins = X.build(bridge['source'], bridge['inputs'], self.module_hashes,
                               capabilities=self.metadata['capabilities'])
            contract = _seal({'version': VERSION, 'graph_pins': self.metadata['sha256'], 'action': action,
                              'bridge': bridge, 'execution_pins': pins})
            with self._fenced():
                _discard_uncommitted(folder)
                _write_json(folder, 'attempt-pins.json', contract)
        if not existing:
            _discard_uncommitted(folder)  # crash leftovers of earlier result/state writes
        store = Store(str(folder))
        # Validate native files before Store's tolerant reader can hide damage.
        # Attempt source is read from sealed metadata, not an editable program file.
        context = contract['sha256']
        input_private, _ = _labels(action['inputs'])
        # Child/loop acquisitions must not lose protection when their bindings
        # leave scope. Conservatively fence any node using a private capability.
        capability_private = any(spec.get('sensitivity') not in ('', 'public', 'none')
                                 for spec in pins['capabilities'].values())
        calls = _Calls(store, self.apps, action['route'],
                       n['allowed']['local_only'] or input_private or capability_private,
                       action['call_limit'], context, bridge['source_sha256'], self.stop, self._fence_factory())
        effect_rows = _read(folder / FX.LEDGER, lines=True, missing=True)
        latest = {}
        for row in effect_rows:
            if (type(row) is not dict or type(row.get('id')) is not str
                    or row.get('phase') not in ('intent', 'done', 'failed', 'unknown')):
                raise G.GraphError('corrupt effects ledger')
            if FX.recovery_block(row, row):
                raise G.GraphError('effect contract/identity receipt corrupted')
            if row['phase'] == 'done' and not FX.intact(row):
                raise G.GraphError('effect outcome identity corrupted')
            if row.get('source_sha256') != bridge['source_sha256']:
                raise G.GraphError('effect source pin changed')
            latest[row['id']] = row
        unknown_effect = any(row['phase'] in ('intent', 'unknown') for row in latest.values())
        if effect_rows and n['effect_risk'] == 'none':
            raise G.GraphError('undeclared effects ledger')
        outcome = _read(folder / 'graph-result.json', missing=True)
        if outcome is not None:
            _unseal(outcome)
            G.keys(outcome, ('version', 'context', 'result', 'issued_calls', 'run_report', 'sha256'))
            if type(outcome['version']) is not int or outcome['version'] != VERSION:
                raise G.GraphError('durable result version changed')
            if outcome.get('context') != context:
                raise G.GraphError('result belongs to a different attempt')
            if type(outcome['issued_calls']) is not int or outcome['issued_calls'] != len(calls.intents):
                raise G.GraphError('durable result call accounting differs')
            result = outcome['result']
            if type(result) is not dict or result.get('kind') not in ('succeeded', 'failed', 'unknown'):
                raise G.GraphError('invalid durable result')
            if result['kind'] == 'succeeded':
                G.keys(result, ('kind', 'result'))
                G.validate_envelope(result['result'])
                native = [row for row in result['result']['evidence'] if row.get('scope') == 'symblic_run']
                if len(native) != 1 or native[0].get('run_report_sha256') != _hash(outcome['run_report']):
                    raise G.GraphError('native report differs from graph evidence reference')
            else:
                G.keys(result, ('kind', 'error', 'retryable', 'effect_known'))
                if (type(result['error']) is not str or type(result['retryable']) is not bool
                        or type(result['effect_known']) is not bool):
                    raise G.GraphError('invalid durable failure receipt')
            if (calls.uncertain or unknown_effect) and outcome['result'].get('kind') != 'unknown':
                raise G.GraphError('durable result conflicts with unfinished external intent')
        return n, bridge, pins, store, calls, unknown_effect, outcome

    def _producer_reports(self, action):
        """Resolve only host-derived graph event identities, never content-supplied paths."""
        reports = {}
        for name, item in action['inputs'].items():
            if 'origin' not in item or item.get('status') != 'succeeded':
                continue
            origin = item['origin']
            G.keys(origin, ('node', 'iteration', 'attempt'))
            G.identifier(origin['node'])
            if origin['node'] not in self.nodes:
                raise G.GraphError('missing producer node')
            G.integer(origin['iteration'], 0, self.frozen['graph']['iterations'] - 1)
            G.integer(origin['attempt'], 1, 9)
            folder = self.folder / 'attempts' / (
                f'Iter{origin["iteration"]:03d}_{origin["node"]}_Attempt{origin["attempt"]:02d}')
            saved = _unseal(_read(folder / 'graph-result.json'))
            native = [row for row in item['result']['evidence'] if row.get('scope') == 'symblic_run']
            if (saved['result'].get('kind') != 'succeeded' or saved['result']['result'] != item['result']
                    or len(native) != 1 or native[0].get('report_reference') != origin
                    or native[0].get('run_report_sha256') != _hash(saved['run_report'])):
                raise G.GraphError('producer report/envelope reference differs')
            reports[name] = saved['run_report']
        return reports

    def _result(self, runner, n, bridge, action, calls, *, report=None):
        report = runner.report() if report is None else report
        fx = getattr(runner, '_effects', None)
        unknown_effect = bool(fx and any(r.get('phase') in ('intent', 'unknown') for r in fx.ledger.all()))
        if calls.uncertain or unknown_effect or (report.get('error') or {}).get('kind') == 'uncertain':
            return {'kind': 'unknown', 'error': calls.failure or 'external effect outcome uncertain',
                    'retryable': False, 'effect_known': False}
        if report['status'] != 'done' or calls.failure:
            message = calls.failure or (report.get('error') or {}).get('message') or report['status']
            return {'kind': 'failed', 'error': message[:1000],
                    'retryable': not bool(calls.failure) and n['effect_risk'] == 'none', 'effect_known': True}
        bound = runner.kernel.env.lookup(n['output_binding'])
        if bound is None:
            return {'kind': 'failed', 'error': 'declared output binding is absent', 'retryable': False, 'effect_known': True}
        try:
            value = G.snapshot(_output(bound.value))
            errors = FX.schema_errors(value, n['output_schema'])
            if errors:
                raise G.GraphError('output schema: ' + '; '.join(errors[:4]))
            contracts = dict(zip(bridge['contract_lines'], bridge['contract_predicates']))
            receipts = [r for r in runner.checks if contracts.get(r['line']) == r['predicate_sha256']
                        and any(b['name'] == bound.name and b['hash'] == bound.hash for b in r['bindings'])]
            if len(receipts) != len(n.get('checks', [])) or any(not r['passed'] for r in receipts):
                raise G.GraphError('declared node checks lack accepted receipts')
            unresolved = any(item['status'] != 'succeeded' or item['result']['outcome'] != 'supported'
                             for item in action['inputs'].values())
            contested = bool((bound.meta or {}).get('contested')) or unresolved or any(
                (row.get('ask') or {}).get('contested') for row in runner.trace)
            outcome = 'contested' if contested else 'supported' if receipts else 'unknown'
            scope = {'scope': 'node_contract', 'assurance': 'supported_under_encoded_contract' if receipts else 'typed_output_only',
                     'source_truth': 'contingent', 'binding': bound.name, 'binding_hash': bound.hash,
                     'predicate_receipts': _audit(receipts), 'schema': n['output_schema'],
                     'graph_hash': self.frozen['graph_hash'], 'policy_hash': self.frozen['policy_hash'],
                     'execution_pins': runner._execution_pins['sha256']}
            # Full native reports stay in their original attempt folder. Graph
            # edges carry exact references, not recursively nested ancestor data.
            epistemic = report['epistemic']
            evidence = [scope, {'scope': 'symblic_run', 'run_report_sha256': _hash(report),
                                'report_reference': {key: action[key] for key in ('node', 'iteration', 'attempt')},
                                'evidence': {'sha256': _hash(report['evidence']), 'scope': 'native_run_report.evidence'},
                                'binding_evidence': {'sha256': _hash((bound.meta or {}).get('evidence')),
                                                     'scope': 'native_run_report.bindings'},
                                'epistemic': {'version': EP.VERSION, 'empirical_truth': 'not_established',
                                    'claims_sha256': _hash(epistemic['claims']), 'claim_count': len(epistemic['claims']),
                                    'assessments_sha256': _hash(epistemic['assessments']),
                                    'lineage_complete': bound.meta['epistemic']['assessment']['lineage_complete']},
                                'binding_epistemic': _audit((bound.meta or {}).get('epistemic')),
                                'execution_profile': report['execution_profile'],
                                'observed_bindings': _audit([
                                    {'binding': b.name, 'hash': b.hash, 'evidence_sha256': _hash(b.meta['evidence'])}
                                    for b in runner.kernel.env.all().values() if (b.meta or {}).get('evidence')])}]
            inputs = {}
            for name, item in action['inputs'].items():
                reference = {'status': item['status'], 'input_sha256': _hash(item)}
                if 'origin' in item:
                    reference['origin'] = item['origin']
                if 'error' in item:
                    reference['error_sha256'] = _hash(item['error'])
                if 'result' in item:
                    reference.update(value_id=item['result']['value_id'], outcome=item['result']['outcome'],
                                     envelope_sha256=_hash(item['result']), evidence_sha256=_hash(item['result']['evidence']))
                inputs[name] = reference
            private, untrusted = _labels([action['inputs'], report])
            result = G.envelope(value, outcome, evidence=evidence, assumptions=n.get('assumptions', []),
                                provenance=[{'inputs': inputs, 'kernel': bridge['kernel'],
                                             'sensitivity': 'confidential' if private else 'public', 'untrusted': untrusted,
                                             'source_sha256': bridge['source_sha256'],
                                             'declared_source_sha256': bridge['declared_source_sha256'],
                                             'issued_calls': len(calls.intents)}])
            return {'kind': 'succeeded', 'result': result}
        except (G.GraphError, S.SymblicError) as exc:
            return {'kind': 'failed', 'error': str(exc)[:1000], 'retryable': False, 'effect_known': True}

    def execute(self):
        with self._locked():
            self._prepare(clean=True)
            replay = self.replay
            while True:
                if replay.status() in ('succeeded', 'unresolved', 'canceled'):
                    return replay.state()
                if self.stop.is_set():
                    return self._halt()
                action = replay.running()
                recovery = action is not None
                started = None
                if not recovery:
                    action = replay.next_action()
                    if action is None:
                        raise G.GraphError('graph has no schedulable or recoverable action')
                    started = replay.event('started', id=f'GraphEvent{replay.next_seq}',
                                           **{k: action[k] for k in ('node', 'iteration', 'attempt')},
                                           route=action['route'], inputs_hash=G.digest(action['inputs']))
                    if not self._fits(started):
                        # Close durably before any new work: a dispatched attempt
                        # must always be able to record its completion.
                        self._event('capacity')
                        return replay.state()
                n, bridge, pins, store, calls, unknown_effect, stored = self._attempt(action)
                fields = {k: action[k] for k in ('node', 'iteration', 'attempt')}
                if started is not None:
                    self._commit(started)
                    self._observe('started', action)
                if stored is not None:
                    result = stored['result']
                elif calls.uncertain or unknown_effect:
                    result = {'kind': 'unknown', 'error': 'unfinished external intent; automatic redispatch refused',
                              'retryable': False, 'effect_known': False}
                else:
                    route, app_label = _route(n, self.frozen['policy'])
                    options = {**bridge['options'], 'by': app_label, 'parallel': 1, 'stop': self.stop,
                               'execution_pins': pins, 'max_asks': action['call_limit'], 'max_steps': S.MAX_STEPS}
                    host = None
                    if n['effect_risk'] != 'none':
                        host = _Host(self.effects, self.metadata['capabilities'], self.stop,
                                     _labels(action['inputs']), self._fence_factory())
                        options.update(effects=host, effects_wait=0, max_effects=G.MAX_CALLS)
                    runner = _NodeRun(bridge['source'], bridge['inputs'], calls, options, folder=store.dir,
                                      graph_inputs=action['inputs'], graph_reports=self._producer_reports(action))
                    calls.runner = runner
                    runner.execute()
                    report = runner.report()
                    if self.stop.is_set() or calls.halted or (host is not None and host.halted):
                        # A stop-caused outcome is never saved as the node's result.
                        # Owner cancellation closes the graph; any other stop leaves
                        # this attempt open, so resume replays its known calls.
                        self._observe('interrupted', action)
                        return self._halt()
                    result = self._recordable(self._result(runner, n, bridge, action, calls, report=report), fields)
                    # The adapter's result snapshot is synced BEFORE the graph completion row.
                    saved = _seal({'version': VERSION, 'context': calls.context, 'result': result,
                                   'issued_calls': len(calls.intents), 'run_report': report})
                    with self._fenced():
                        _save(store, 'graph-result.json', saved)
                    self._observe('result_saved', action)
                if self.stop.is_set():
                    return self._halt()
                self._event(result['kind'], **fields, **{k: v for k, v in result.items() if k != 'kind'})
                self._observe('completed', action)
