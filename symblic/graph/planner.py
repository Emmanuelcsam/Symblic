"""Agent graphs, part 1: the pure planner. Validate and freeze a graph of contracted nodes, replay its ledger.

What it is for
    An agent graph is a small explicit workflow. Each node is a Symblic program with a statement contract, an
    output schema, a declared output binding and optional checks on that binding. Edges carry one node's result
    envelope into another node's `given` input (optionally delayed by one iteration, starting from a seed).
    A routing policy lists the applicators (provider, model, node, local or not) a node may use. This module
    never runs anything; it decides what may run next:

    freeze_graph(spec, policy)   validate sizes and fields, compile every pure node against the kernel
                                 (compile_node), refuse undelayed cycles, choose each route by the policy's
                                 fixed order with restrictions that only narrow (choose_route), check that the
                                 worst case fits the event ledger, and pin graph and policy by SHA-256
    Replay / derive(frozen, ledger)   fold an append-only ledger of 'started', 'succeeded', 'failed', 'unknown',
                                 'cancel' and 'capacity' rows, refusing any row that does not match the pins;
                                 reserve each attempt's whole call allowance at its start; block, exhaust or
                                 retry nodes; return the deterministic ready batch
    envelope / validate_envelope a value with its outcome ('supported', 'contested' or 'unknown'), evidence,
                                 assumptions and provenance; independence is always 'not_established'
    evaluate_policy              descriptive per-route counts over labelled observations; it learns nothing

Depends on: the standard library; symblic.kernel (language, evidence, execution_pins) when compiling nodes.
Used by: symblic.graph.run (the durable executor), symblic.graph.compose and symblic.policy.graph.
Status: prototype with unit tests (tests/graph). Design notes: docs/reference/AGENT-GRAPHS.md.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path


def _import_identity(path, executing):
    """(sha256, attested) of a module's source at its own import boundary.

    `executing` is the module code object being run. It equals the compilation of
    the hashed bytes only when this process loaded exactly those bytes, whatever
    the bytecode cache or a later disk change says.
    """
    raw = Path(path).read_bytes()
    compiled = compile(raw, str(path), 'exec', dont_inherit=True, optimize=sys.flags.optimize)
    return hashlib.sha256(raw).hexdigest(), executing == compiled


_SOURCE_SHA256, _SOURCE_LOADED = _import_identity(__file__, sys._getframe(0).f_code)

VERSION = 1
MAX_NODES = 128
MAX_ITERATIONS = 32
MAX_EVENTS = 10000
MAX_CALLS = 10000
MAX_BYTES = 1_000_000
# A ledger is replayed one bounded row at a time. The whole ledger is bounded by
# MAX_EVENTS rows and by these canonical bytes, the durable adapter's file cap.
MAX_LEDGER_BYTES = 8_000_000
ID = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
TERMINAL = {'succeeded', 'failed', 'unknown', 'blocked', 'exhausted'}
CAPACITY_ERROR = 'graph ledger capacity reached before dispatch'
# Frozen-graph verification recompiles every node, so a verified identity is
# remembered (bounded) per planner source, kernel identity and frozen content.
VERIFIED_LIMIT = 256
_VERIFIED = OrderedDict()
_VERIFIED_LOCK = threading.Lock()
COMPILED_LIMIT = 512
_COMPILED = OrderedDict()
_COMPILED_LOCK = threading.Lock()


class GraphError(ValueError):
    """Invalid contract or ledger: fail closed, never discard a row."""


def snapshot(value):
    """Validate before serialization; reject cycles, floats, deep/large objects."""
    return json.loads(_encode(value))


def _encode(value):
    """Canonical UTF-8 JSON of a validated bounded value (the snapshot form)."""
    count = 0
    size = 0
    active = set()

    def visit(v, depth):
        nonlocal count, size
        count += 1
        if depth > 24 or count > 50000:
            raise GraphError('JSON depth/item limit')
        if type(v) is str:
            size += len(v.encode('utf-8'))
        elif type(v) is int:
            if v.bit_length() > 4096:
                raise GraphError('integer limit')
        elif v is None or type(v) is bool:
            pass
        elif type(v) in (dict, list):
            if id(v) in active or len(v) > 10000:
                raise GraphError('cyclic/oversized collection')
            active.add(id(v))
            if type(v) is dict:
                for k, item in v.items():
                    if type(k) is not str:
                        raise GraphError('JSON keys must be text')
                    visit(k, depth + 1)
                    visit(item, depth + 1)
            else:
                for item in v:
                    visit(item, depth + 1)
            active.remove(id(v))
        else:
            raise GraphError('only exact JSON values supported')
        if size > MAX_BYTES:
            raise GraphError('JSON byte limit')
    visit(value, 0)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise GraphError('JSON byte limit')
    return raw


def _detach(value):
    """Copy an already validated value in snapshot form, without re-applying size limits."""
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


def digest(value):
    # Canonical JSON of a snapshot is its own canonical form: one serialization suffices.
    return hashlib.sha256(_encode(value)).hexdigest()


def identifier(value):
    if type(value) is not str or not ID.fullmatch(value):
        raise GraphError('invalid identifier')
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise GraphError('integer outside declared limits')
    return value


def keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise GraphError('missing or unsupported contract fields')


def names(value):
    if type(value) is not list or not value or len(value) > 128:
        raise GraphError('nonempty bounded choices required')
    for name in value:
        identifier(name)
    if len(set(value)) != len(value):
        raise GraphError('duplicate choices')


def envelope(value, outcome='unknown', *, evidence=None, assumptions=None, provenance=None):
    """Labels and receipts describe evidence; supported is not a truth guarantee."""
    result = {'version': VERSION, 'value': snapshot(value), 'value_id': digest(value),
              'outcome': outcome, 'evidence': [] if evidence is None else evidence,
              'assumptions': [] if assumptions is None else assumptions,
              'provenance': [] if provenance is None else provenance, 'independence': 'not_established'}
    return validate_envelope(result)


def validate_envelope(value):
    v = snapshot(value)
    keys(v, ('version', 'value', 'value_id', 'outcome', 'evidence', 'assumptions', 'provenance', 'independence'))
    if (type(v['version']) is not int or v['version'] != VERSION or v['value_id'] != digest(v['value'])
            or v['outcome'] not in ('supported', 'contested', 'unknown')
            or v['independence'] != 'not_established'):
        raise GraphError('invalid evidence envelope')
    for field in ('evidence', 'assumptions', 'provenance'):
        if type(v[field]) is not list or len(v[field]) > 128:
            raise GraphError('bounded evidence lists required')
    return v


def validate_policy(policy):
    p = snapshot(policy)
    keys(p, ('version', 'routes', 'order'))
    if type(p['version']) is not int or p['version'] != VERSION:
        raise GraphError('unsupported policy version')
    if type(p['routes']) is not list or not 1 <= len(p['routes']) <= 128:
        raise GraphError('route limit')
    routes = {}
    for r in p['routes']:
        keys(r, ('id', 'provider', 'model', 'node', 'local'))
        identifier(r['id'])
        for field in ('provider', 'model', 'node'):
            if type(r[field]) is not str or not r[field] or len(r[field]) > 160:
                raise GraphError('invalid route label')
        if type(r['local']) is not bool or r['id'] in routes:
            raise GraphError('invalid/duplicate route')
        routes[r['id']] = r
    names(p['order'])
    if set(p['order']) != set(routes):
        raise GraphError('order must name every route exactly once')
    return p


def choose_route(node, policy):
    """Frozen fixed-order policy; restrictions intersect, never get relaxed."""
    p = validate_policy(policy)
    node = snapshot(node)
    if type(node) is not dict or 'allowed' not in node:
        raise GraphError('node restrictions required')
    allowed = node['allowed']
    keys(allowed, ('routes', 'providers', 'models', 'nodes', 'local_only'))
    names(allowed['routes'])
    if type(allowed['local_only']) is not bool:
        raise GraphError('local_only must be boolean')
    for field in ('providers', 'models', 'nodes'):
        values = allowed[field]
        if (type(values) is not list or not 1 <= len(values) <= 128
                or any(type(v) is not str or not v or len(v) > 160 for v in values)):
            raise GraphError('explicit bounded route restrictions required')
    routes = {r['id']: r for r in p['routes']}
    if set(allowed['routes']) - routes.keys():
        raise GraphError('undeclared permitted route')
    for rid in p['order']:
        r = routes[rid]
        if (rid in allowed['routes'] and r['provider'] in allowed['providers']
                and r['model'] in allowed['models'] and r['node'] in allowed['nodes']
                and (not allowed['local_only'] or r['local'])):
            return snapshot(r)
    raise GraphError('no permitted route; refusing fallback')


def evaluate_policy(policy, observations):
    """Descriptive training-only exact statistics; no learned policy is supported."""
    p = validate_policy(policy)
    obs = snapshot(observations)
    if type(obs) is not list or len(obs) > 4096:
        raise GraphError('observation limit')
    stats = {r['id']: {'count': 0, 'successes': 0, 'cost': 0} for r in p['routes']}
    held_out = 0
    for row in obs:
        keys(row, ('split', 'route', 'success', 'cost'))
        if (row['split'] not in ('training', 'held_out') or type(row['route']) is not str
                or row['route'] not in stats or type(row['success']) is not bool):
            raise GraphError('invalid labeled observation')
        integer(row['cost'], 0, 10**12)
        if row['split'] == 'held_out':
            held_out += 1
            continue
        s = stats[row['route']]
        s['count'] += 1
        s['successes'] += int(row['success'])
        s['cost'] += row['cost']
    for s in stats.values():
        s['success_rate'] = str(Fraction(s['successes'], s['count'])) if s['count'] else None
        s['mean_cost'] = str(Fraction(s['cost'], s['count'])) if s['count'] else None
    return {'policy_hash': digest(p), 'training': stats, 'held_out_excluded': held_out,
            'learner_supported': False, 'performance_improvement_established': False}


def compile_node(spec, inputs, *, libraries=None, allow_effects=False):
    """Compile supplied formal source and declared predicates for existing Run.

    Values remain separate frozen JSON. Library sources, when supplied, must be
    execution-pinned by the durable adapter. No saved imports or process adapters.
    Effect statements require an explicitly pinned existing effects host.
    """
    from symblic.kernel import language as S
    s, values = snapshot(spec), snapshot(inputs)
    if type(s) is not dict or not {'source', 'call_limit', 'effect_risk', 'output_schema'} <= s.keys():
        raise GraphError('missing node compiler metadata')
    source = s['source']
    if type(source) is not str or not source.strip() or len(source.encode('utf-8')) > 32768:
        raise GraphError('explicit bounded Symblic source required')
    if type(values) is not dict or len(values) > 128:
        raise GraphError('bounded named inputs required')
    for name in values:
        identifier(name)
    if s['effect_risk'] != 'none' and not allow_effects:
        raise GraphError('effectful programs require a separate pinned host adapter')
    supplied = snapshot(libraries) if libraries is not None else None
    # Compilation depends on the node, pinned libraries and the kernel, never on
    # input values: a verified template is reused and only the values are bound.
    extensions = [[name, id(ext)] for name, ext in sorted(S.EXTENSIONS.items())]
    key = hashlib.sha256(json.dumps([VERSION, _SOURCE_SHA256, S.kernel_id()['id'], extensions, s, supplied,
                                     bool(allow_effects)], sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()
    with _COMPILED_LOCK:
        template = _COMPILED.get(key)
        if template is not None:
            _COMPILED.move_to_end(key)
    if template is not None:
        declared, raw = template
        if set(declared) != set(values):
            raise GraphError('inputs must exactly match top-level given declarations')
        result = json.loads(raw)
        result['inputs'], result['inputs_hash'] = values, digest(values)
        return result
    result, declared = _compile(s, values, supplied, allow_effects)
    raw = json.dumps({**result, 'inputs': None, 'inputs_hash': None}, ensure_ascii=False)
    with _COMPILED_LOCK:
        _COMPILED[key] = (declared, raw)
        _COMPILED.move_to_end(key)
        while len(_COMPILED) > COMPILED_LIMIT:
            _COMPILED.popitem(last=False)
    return result


def _compile(s, values, supplied, allow_effects):
    from symblic.kernel import language as S
    from symblic.kernel import evidence as E
    from symblic.kernel import execution_pins as X
    source = s['source']
    if supplied is not None and (type(supplied) is not dict or not supplied.keys() <= X.LIBRARIES):
        raise GraphError('only registered pinned libraries supported')
    used = set()
    scanned = set()
    pure_extensions = {'function', 'routine', 'routine-return', 'import', 'test'}

    def inspect_source(text, is_library=False):
        if type(text) is not str or len(text.encode('utf-8')) > 32768:
            raise GraphError('library/source byte limit')
        if any(kind == 'prose' and not re.match(r'^(program|section|note)\b', line, re.I)
               for line, _, kind in S.split_statements(text)):
            raise GraphError('implicit prose programs are unsupported')
        try:
            program = S.parse(text)
            nodes = list(S.walk(program['statements']))
        except (S.SymblicError, RecursionError) as exc:
            raise GraphError('invalid or excessive Symblic program') from exc
        if len(nodes) > 10000 or program['warnings']:
            raise GraphError('program complexity/warning refusal')
        for n in nodes:
            if getattr(n, 'prose', False) or n.k in ('delegate', 'workflow'):
                raise GraphError('implicit asks/delegation need unsupported adapter capability')
            if n.k in S.EXTENSIONS and n.k not in pure_extensions | {'observe', 'act'}:
                raise GraphError('unregistered graph extension capability')
            if n.k in ('observe', 'act'):
                if not allow_effects or s['effect_risk'] == 'none' or is_library:
                    raise GraphError('undeclared or imported effect capability')
                if s['effect_risk'] == 'read' and n.k == 'act':
                    raise GraphError('write exceeds declared effect risk')
            if n.k == 'call' and n.fn in ('js_test', 'js_run'):
                raise GraphError('process adapters require an unsupported graph adapter')
            if n.k == 'import':
                if n.saved or n.module not in X.LIBRARIES:
                    raise GraphError('saved/uncaptured library import refused')
                used.add(n.module)
                if supplied is not None and n.module not in scanned:
                    row = supplied.get(n.module)
                    text = row.get('source') if type(row) is dict else row
                    if type(text) is not str:
                        raise GraphError('missing pinned library source')
                    scanned.add(n.module)
                    inspect_source(text, True)
        return program

    program = inspect_source(source)
    declared = [stmt.name for stmt in program['statements'] if stmt.k == 'given']
    if len(set(declared)) != len(declared) or set(declared) != set(values):
        raise GraphError('inputs must exactly match top-level given declarations')
    # Nested given declarations could replace the graph's frozen input contract.
    if sum(n.k == 'given' for n in S.walk(program['statements'])) != len(declared):
        raise GraphError('nested given declarations unsupported')
    checks = s.get('checks', [])
    if type(checks) is not list or len(checks) > 32:
        raise GraphError('bounded declared checks required')
    binding = s.get('output_binding')
    if binding is not None:
        identifier(binding)
    additions = []
    for predicate in checks:
        if type(predicate) is not str or not predicate or len(predicate) > 4096:
            raise GraphError('invalid node predicate')
        assertion = 'assert (' + predicate + ').'
        checked = inspect_source(assertion)
        if (len(checked['statements']) != 1 or checked['statements'][0].k != 'assert'
                or binding is None or binding not in S.free_names(checked['statements'][0].cond)):
            raise GraphError('each node predicate must check the declared output binding')
        additions.append(assertion)
    assumptions = s.get('assumptions', [])
    if type(assumptions) is not list or len(assumptions) > 128:
        raise GraphError('bounded node assumptions required')
    compiled = source + ('\n' + '\n'.join(additions) if additions else '')
    if len(compiled.encode('utf-8')) > 32768:
        raise GraphError('compiled program byte limit')
    integer(s['call_limit'], 1, MAX_CALLS)
    contract_nodes = [n for n in S.parse(compiled)['statements']
                      if n.line > source.count('\n') + 1 and n.k == 'assert']
    return {'version': VERSION, 'source': compiled,
            'declared_source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'source_sha256': hashlib.sha256(compiled.encode()).hexdigest(),
            'inputs': values, 'inputs_hash': digest(values), 'kernel': S.kernel_id(),
            'options': {'profile': 'verified', 'max_calls': s['call_limit'],
                        'side_effects': s['effect_risk'] != 'none'},
            'requires_restrictive_applicators': True, 'required_libraries': sorted(used),
            'output_binding': binding, 'contract_lines': [n.line for n in contract_nodes],
            'contract_predicates': [E.digest(E.syntax(n.cond)) for n in contract_nodes],
            'output_schema': snapshot(s['output_schema'])}, declared


def worst_case_attempts(graph):
    """Most attempts any ledger of a frozen graph can start under its reservations.

    A node-iteration starts at most retries+1 attempts; each start reserves the
    node's whole call_limit from its node and graph budgets, so the cheapest
    attempts are counted first.
    """
    budget, total = graph['max_calls'], 0
    for cost, count in sorted((n['call_limit'], min(graph['iterations'] * (n['retries'] + 1),
                                                     n['max_calls'] // n['call_limit']))
                              for n in graph['nodes']):
        take = min(count, budget // cost)
        total += take
        budget -= take * cost
    return total


def freeze_graph(spec, policy):
    """Validate and pin topology/policy; updates create a different future run.

    Admission refuses a graph whose worst case cannot fit the event ledger: every
    attempt it could start needs a start and a completion row, plus one closing
    row. Output bytes depend on data; the runtime instead stops before dispatch
    when a completion could no longer be recorded (a durable 'capacity' row).
    """
    frozen = _freeze(spec, policy)
    events = 2 * worst_case_attempts(frozen['graph']) + 1
    if events > MAX_EVENTS:
        raise GraphError(f'graph worst case needs {events} ledger events (limit {MAX_EVENTS}); '
                         'lower retries, iterations or call caps')
    _remember(frozen)
    return frozen


def _freeze(spec, policy):
    """Validate a graph and policy into their pinned frozen form, without admission caps."""
    g, p = snapshot(spec), validate_policy(policy)
    keys(g, ('id', 'nodes', 'iterations', 'max_calls'))
    identifier(g['id'])
    integer(g['iterations'], 1, MAX_ITERATIONS)
    integer(g['max_calls'], 1, MAX_CALLS)
    if type(g['nodes']) is not list or not 1 <= len(g['nodes']) <= MAX_NODES:
        raise GraphError('node limit')
    nodes = {}
    for n in g['nodes']:
        keys(n, ('id', 'inputs', 'source', 'contract', 'output_schema', 'allowed', 'join',
                 'effect_risk', 'retries', 'call_limit', 'max_calls', 'max_iterations'),
             ('output_binding', 'checks', 'assumptions'))
        identifier(n['id'])
        if n['id'] in nodes:
            raise GraphError('duplicate node')
        nodes[n['id']] = n
        if n['join'] not in ('require_all', 'collect_unresolved') or n['effect_risk'] not in ('none', 'read', 'write'):
            raise GraphError('unsupported join/effect risk')
        if type(n['contract']) is not str or not n['contract'] or len(n['contract']) > 8192:
            raise GraphError('explicit statement contract required')
        if type(n['output_schema']) is not dict:
            raise GraphError('output schema metadata required')
        integer(n['retries'], 0, 8)
        integer(n['call_limit'], 1, MAX_CALLS)
        integer(n['max_calls'], 1, MAX_CALLS)
        integer(n['max_iterations'], g['iterations'], MAX_ITERATIONS)
        if type(n['inputs']) is not dict or len(n['inputs']) > 128:
            raise GraphError('input limit')
        choose_route(n, p)
        compile_values = {}
        for name, ref in n['inputs'].items():
            identifier(name)
            if type(ref) is not dict:
                raise GraphError('input ref must be an object')
            if 'node' in ref:
                keys(ref, ('node',), ('delay', 'seed'))
                identifier(ref['node'])
                integer(ref.get('delay', 0), 0, 1)
                if ref.get('delay', 0) == 1:
                    if 'seed' not in ref:
                        raise GraphError('delayed dependency requires initial envelope')
                    validate_envelope(ref['seed'])
                elif 'seed' in ref:
                    raise GraphError('seed only permitted on delayed edge')
                compile_values[name] = None
            else:
                keys(ref, ('literal',))
                compile_values[name] = validate_envelope(ref['literal'])['value']
        if n['effect_risk'] == 'none':
            compile_node(n, compile_values)
        else:
            # We schedule explicit effect risk, but cannot compile/execute it.
            if type(n['source']) is not str or not n['source'] or len(n['source']) > 32768:
                raise GraphError('bounded effect program required')
    pending = set(nodes)
    while pending:
        ready = sorted(nid for nid in pending if all(
            ref['node'] in nodes and ref['node'] not in pending
            for ref in nodes[nid]['inputs'].values() if 'node' in ref and not ref.get('delay')))
        if not ready:
            raise GraphError('missing dependency or undelayed cycle')
        pending.difference_update(ready)
    for n in nodes.values():
        if any(ref['node'] not in nodes for ref in n['inputs'].values() if 'node' in ref):
            raise GraphError('missing delayed dependency')
    g['nodes'].sort(key=lambda n: n['id'])
    return {'version': VERSION, 'graph': g, 'policy': p, 'graph_hash': digest(g), 'policy_hash': digest(p)}


def _verification_key(f):
    from symblic.kernel import language as S
    raw = json.dumps([VERSION, _SOURCE_SHA256, S.kernel_id()['id'], f], sort_keys=True,
                     ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _remember(frozen):
    key = _verification_key(frozen)
    with _VERIFIED_LOCK:
        _VERIFIED[key] = True
        _VERIFIED.move_to_end(key)
        while len(_VERIFIED) > VERIFIED_LIMIT:
            _VERIFIED.popitem(last=False)


def _verified(frozen):
    """Detached frozen graph whose pins match its content (re-frozen once per identity)."""
    f = snapshot(frozen)
    keys(f, ('version', 'graph', 'policy', 'graph_hash', 'policy_hash'))
    if type(f['version']) is not int or f['version'] != VERSION:
        raise GraphError('corrupt/unpinned graph')
    key = _verification_key(f)
    with _VERIFIED_LOCK:
        if key in _VERIFIED:
            _VERIFIED.move_to_end(key)
            return f
    # Graphs admitted under earlier caps stay derivable: check pins, not admission.
    if _freeze(f['graph'], f['policy']) != f:
        raise GraphError('corrupt/unpinned graph')
    _remember(f)
    return f


class Replay:
    """Exact incremental derive(): validate and fold ordered ledger rows one at a time.

    derive() is Replay(frozen), apply() for every row, then state(). Planning
    (blocked/exhausted propagation and the ready batch) runs before each start and
    closing row and before reporting. Reservation totals change only at starts and
    terminal states are final, so this reaches the same fixed point as a scan
    before every row. apply(row, commit=False) validates without folding the row;
    its only effect is that same planner normalization.
    """

    def __init__(self, frozen):
        f = _verified(frozen)
        g, policy = f['graph'], f['policy']
        self.frozen, self.graph = f, g
        self.nodes = {n['id']: n for n in g['nodes']}
        self._order = {nid: index for index, nid in enumerate(self.nodes)}
        self.routes = {nid: choose_route(n, policy) for nid, n in self.nodes.items()}
        self._route_ids = {nid: digest(route) for nid, route in self.routes.items()}
        self.states = {(i, nid): {'status': 'pending', 'attempt': 0, 'history': []}
                       for i in range(g['iterations']) for nid in self.nodes}
        self._open = [len(self.nodes)] * g['iterations']
        self._first = 0
        self._supported = 0
        self._running = set()
        self._changes = 0
        self.calls = 0
        self.node_calls = {nid: 0 for nid in self.nodes}
        self.seen = {}
        self.count = 0
        self.bytes = 0
        self.closed = None
        self._items, self._inputs, self._digests = {}, {}, {}
        # Literal and seed inputs are frozen: build their input items once.
        self._fixed = {}
        for nid, n in self.nodes.items():
            for name, ref in n['inputs'].items():
                if 'literal' in ref:
                    self._fixed[nid, name] = snapshot({'status': 'succeeded', 'result': ref['literal']})
                elif ref.get('delay'):
                    self._fixed[nid, name] = snapshot({'status': 'succeeded', 'result': ref['seed']})

    @property
    def next_seq(self):
        return len(self.seen) + 1

    def _item(self, j, nid):
        # Terminal states are final, so a producer's input item is built once.
        item = self._items.get((j, nid))
        if item is None:
            parent = self.states[j, nid]
            item = {k: parent[k] for k in ('status', 'result', 'error') if k in parent}
            item['origin'] = {'node': nid, 'iteration': j, 'attempt': parent['attempt']}
            item = self._items[j, nid] = snapshot(item)
        return item

    def _inputs_for(self, key):
        """(inputs, unresolved) once every dependency is terminal; None while waiting."""
        entry = self._inputs.get(key)
        if entry is not None:
            return entry
        i, nid = key
        inputs, bad = {}, False
        for name, ref in self.nodes[nid]['inputs'].items():
            if 'literal' in ref or (ref.get('delay') and i == 0):
                item = self._fixed[nid, name]
            else:
                j = i - ref.get('delay', 0)
                if self.states[j, ref['node']]['status'] not in TERMINAL:
                    return None
                item = self._item(j, ref['node'])
            inputs[name] = item
            if item['status'] != 'succeeded' or item['result']['outcome'] != 'supported':
                bad = True
        entry = self._inputs[key] = (inputs, bad)
        return entry

    def _inputs_digest(self, key):
        value = self._digests.get(key)
        if value is None:
            value = self._digests[key] = digest(self._inputs[key][0])
        return value

    def _close(self, key, **fields):
        self.states[key].update(fields)
        self._open[key[0]] -= 1
        self._changes += 1

    def _plan(self):
        g = self.graph
        ready, batch, i = [], 0, self._first
        # Previous iterations finish before later iterations; prevents seeded
        # independent nodes consuming the whole budget ahead of feedback nodes.
        while i < g['iterations']:
            for nid, n in self.nodes.items():
                if self.states[i, nid]['status'] != 'pending':
                    continue
                entry = self._inputs_for((i, nid))
                if entry is None:
                    continue
                inputs, bad = entry
                if bad and n['join'] == 'require_all':
                    self._close((i, nid), status='blocked', inputs=inputs, error='unresolved dependency')
                    continue
                if (self.calls + n['call_limit'] > g['max_calls']
                        or self.node_calls[nid] + n['call_limit'] > n['max_calls']):
                    self._close((i, nid), status='exhausted', error='call reservation budget exhausted')
                    continue
                if self.calls + batch + n['call_limit'] > g['max_calls']:
                    continue  # defer to the next batch; do not mark exhausted early
                batch += n['call_limit']
                ready.append((i, nid))
            if self._open[i]:
                break
            i += 1
        self._first = i
        return ready

    def _stabilized(self):
        # Iterate blocked propagation to a fixed point with a bounded scan.
        for _ in range(MAX_NODES * self.graph['iterations'] + 1):
            before = self._changes
            ready = self._plan()
            if self._changes == before:
                return ready
        raise GraphError('planner failed to converge')

    def _action(self, key):
        i, nid = key
        n = self.nodes[nid]
        return {'node': nid, 'iteration': i, 'attempt': self.states[key]['attempt'] + 1,
                'inputs': _detach(self._inputs[key][0]), 'route': _detach(self.routes[nid]),
                'call_limit': n['call_limit'], 'effect_risk': n['effect_risk']}

    def _status(self):
        if self.closed == 'cancel':
            return 'canceled'
        if any(self._open):
            return 'running'
        return 'succeeded' if self._supported == len(self.states) else 'unresolved'

    def status(self):
        if not self.closed:
            self._stabilized()
        return self._status()

    def ready(self):
        """Detached ready batch (empty once the ledger is closed)."""
        return [] if self.closed else [self._action(key) for key in self._stabilized()]

    def next_action(self):
        ready = [] if self.closed else self._stabilized()
        return self._action(ready[0]) if ready else None

    def running(self):
        """Detached recovery action of the first started attempt without a completion."""
        if not self._running:
            return None
        key = min(self._running, key=lambda k: (k[0], self._order[k[1]]))
        st, n = self.states[key], self.nodes[key[1]]
        return {'node': key[1], 'iteration': key[0], 'attempt': st['attempt'], 'inputs': _detach(st['inputs']),
                'route': _detach(st['route']), 'call_limit': n['call_limit'], 'effect_risk': n['effect_risk']}

    def event(self, kind, **fields):
        """Construct a pinned row for the next sequence; caller supplies a stable unique id."""
        fields = snapshot(fields)
        if fields.keys() & {'version', 'seq', 'graph_hash', 'policy_hash', 'kind'}:
            raise GraphError('event fields cannot override pins')
        return {'version': VERSION, 'seq': self.next_seq, 'graph_hash': self.frozen['graph_hash'],
                'policy_hash': self.frozen['policy_hash'], 'kind': kind, **fields}

    def apply(self, row, *, commit=True):
        """Validate one ordered row against the current state; fold it when commit is true."""
        raw = _encode(row)
        row = json.loads(raw)
        if self.count >= MAX_EVENTS or self.bytes + len(raw) > MAX_LEDGER_BYTES:
            raise GraphError('ledger limit')
        keys(row, ('version', 'id', 'seq', 'graph_hash', 'policy_hash', 'kind'),
             ('node', 'iteration', 'attempt', 'route', 'inputs_hash', 'result', 'error', 'retryable', 'effect_known'))
        identifier(row['id'])
        if row['id'] in self.seen:
            if digest(self.seen[row['id']]) != digest(row):
                raise GraphError('conflicting duplicate event')
            if commit:
                self.count += 1
                self.bytes += len(raw)
            return
        f = self.frozen
        if (type(row['version']) is not int or row['version'] != VERSION or type(row['seq']) is not int
                or row['seq'] != len(self.seen) + 1 or row['graph_hash'] != f['graph_hash']
                or row['policy_hash'] != f['policy_hash']):
            raise GraphError('out-of-order/version/pin mismatch')
        if self.closed == 'cancel':
            raise GraphError('event after cancellation')
        if self.closed:
            raise GraphError('event after capacity closure')
        kind = row['kind']
        ready = self._stabilized() if kind in ('started', 'cancel', 'capacity') else None
        if kind in ('cancel', 'capacity'):
            keys(row, ('version', 'id', 'seq', 'graph_hash', 'policy_hash', 'kind'))
            if kind == 'capacity':
                # The runtime closes only between attempts, with work still pending.
                pending = [key for key, st in self.states.items() if st['status'] == 'pending']
                if self._running or not pending:
                    raise GraphError('capacity closure needs pending work and no running attempt')
                if commit:
                    for key in pending:
                        self._close(key, status='exhausted', error=CAPACITY_ERROR)
            if commit:
                self.closed = kind
        else:
            nid = identifier(row.get('node'))
            if nid not in self.nodes:
                raise GraphError('unknown event node')
            i = integer(row.get('iteration'), 0, self.graph['iterations'] - 1)
            attempt = integer(row.get('attempt'), 1, 9)
            key = (i, nid)
            st, n = self.states[key], self.nodes[nid]
            if kind == 'started':
                keys(row, ('version', 'id', 'seq', 'graph_hash', 'policy_hash', 'kind',
                           'node', 'iteration', 'attempt', 'route', 'inputs_hash'))
                if (key not in ready or attempt != st['attempt'] + 1 or digest(row['route']) != self._route_ids[nid]
                        or row['inputs_hash'] != self._inputs_digest(key)):
                    raise GraphError('start is not a pinned ready action')
                if commit:
                    st.pop('error', None)
                    st.update(status='running', attempt=attempt, inputs=self._inputs[key][0], route=self.routes[nid])
                    self._running.add(key)
                    self.calls += n['call_limit']
                    self.node_calls[nid] += n['call_limit']
            elif kind in ('succeeded', 'failed', 'unknown'):
                if st['status'] != 'running' or st['attempt'] != attempt:
                    raise GraphError('completion without matching start')
                required = ('version', 'id', 'seq', 'graph_hash', 'policy_hash', 'kind', 'node', 'iteration', 'attempt')
                if kind == 'succeeded':
                    keys(row, required + ('result',))
                    update = {'status': 'succeeded', 'result': validate_envelope(row['result'])}
                else:
                    keys(row, required + ('error', 'retryable', 'effect_known'))
                    if type(row['error']) is not str or type(row['retryable']) is not bool or type(row['effect_known']) is not bool:
                        raise GraphError('invalid failure receipt')
                    if kind == 'unknown' or not row['effect_known']:
                        update = {'status': 'unknown', 'error': row['error']}
                    elif row['retryable'] and attempt <= n['retries']:
                        update = {'status': 'pending', 'error': row['error']}
                    else:
                        update = {'status': 'failed', 'error': row['error']}
                if commit:
                    st.update(update)
                    self._running.discard(key)
                    if update['status'] != 'pending':
                        self._open[i] -= 1
                    if update['status'] == 'succeeded' and update['result']['outcome'] == 'supported':
                        self._supported += 1
            else:
                raise GraphError('unknown event kind')
            if commit:
                st['history'].append(row)
        if commit:
            self.seen[row['id']] = row
            self.count += 1
            self.bytes += len(raw)

    def state(self):
        ready = [] if self.closed else self._stabilized()
        return {'version': VERSION, 'graph_hash': self.frozen['graph_hash'], 'policy_hash': self.frozen['policy_hash'],
                'status': self._status(), 'reserved_calls': self.calls, 'node_calls': dict(self.node_calls),
                'ready': [self._action(key) for key in ready],
                'states': [{'node': nid, 'iteration': i, **_detach(st)} for (i, nid), st in self.states.items()],
                'next_seq': len(self.seen) + 1}


def _replayed(frozen, ledger):
    replay = Replay(frozen)
    if type(ledger) is not list or len(ledger) > MAX_EVENTS:
        raise GraphError('ledger limit')
    for row in ledger:
        replay.apply(row)
    return replay


def event(frozen, ledger, kind, **fields):
    """Construct a pinned row; caller supplies stable unique event id."""
    return _replayed(frozen, ledger).event(kind, **fields)


def derive(frozen, ledger):
    """Replay ordered ledger and return deterministic ready batch/state.

    Started attempts are recovery work, never ready actions. Call caps reserve the
    entire per-attempt allowance before dispatch (no refund after crashes). Each
    row is a bounded snapshot; the ledger is bounded by rows and canonical bytes.
    """
    return _replayed(frozen, ledger).state()
