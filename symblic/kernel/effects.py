"""`observe` and `act`: Symblic statements that read and change the world, at most once and on the record.

An `ask` puts a typed question to a model. These two statements reach the world itself, through capabilities
a host declares (a calendar, a mailbox, a search engine, a light switch, an agent runner):

    observe busy: List of Record {start: Text, end: Text} = calendar.free_busy(days=2).
    ask slot: Int in 1..3 "Which of the three free hours suits a one-hour meeting best?" from busy
    act booked = calendar.add(title="Review", start=options[slot]) with key="review-{today}".
    observe after = calendar.created(start=today, end=today).
    ensure any e in after: e.title = "Review" else fail.

This repository ships no capabilities: a program that embeds Symblic passes a host object as the run option
`effects`, with catalogue() (its capabilities) and perform(effect, stop). The tests use a fake host.

`observe` only reads; `act` changes something. Both are contracts the interpreter enforces, in the way an ask
is a contract:

- **Typed.** The capability comes from the host's catalogue (name, JSON Schema of its arguments, effect
  class, approval policy). Unknown capabilities and wrong arguments are errors before anything runs; the
  result is read against the statement's type like a model's answer.
- **At most once, automatically.** Every observe/act has an identity: SHA-256 of [capability, canonical
  arguments, key]. An intent row is written (and synced) to the ledger before the host is called and an
  outcome row after. A resumed run, a retry and a replay take the outcome from the ledger and never call
  again; runs that share a ledger claim an identity atomically and wait for the claimant's outcome, so they
  see one result. An `act` whose outcome is unknown (the process died between the two rows) stops the run
  until the operator says whether it happened (resolve()). Only a read or an action its capability declares
  idempotent is started again after an interrupted attempt. This is not exactly-once: the world can act and
  the record be lost, and then a person decides.
- **Never by accident.** Nothing fires in a preview or a replay; an `act` needs the host to allow side
  effects; an `act` between an ask and the check that may re-ask it is refused (a retry would act on a
  rejected answer); neither statement is allowed inside a function, routine or test.
- **Flow-checked.** Text that comes from outside the operator's control (a web page, a stranger's mail) is
  labelled `untrusted` and the label follows every value computed from it. Such a value cannot become an
  argument of an `act`: outside text never writes an action. Passed through a closed type (Bool, a choice, a
  small Int range) it becomes `steered`: it chose among alternatives the program itself wrote. A steered act
  is allowed and reported, and the host is told, so a consequential one waits for the operator. Personal data
  cannot be an argument of a capability that sends its arguments out.
- **Evidence, not opinion.** A value the interpreter acquired through a capability is recorded as that:
  which capability, which arguments, when, with which result hash. It is a different way of knowing than a
  model's recall, and the record says so; agreement between models is never counted as that.

The module is pure apart from the ledger file it appends to. It never calls a capability itself: the host
object (`options['effects']`) does, behind `perform(effect, stop)`. ("owner" in field names such as
needs_owner means the operator: the person who runs the program and answers for its actions.)

Depends on: symblic.kernel.language; symblic.lang.abstraction (library modules) and symblic.kernel.run (the
interpreter that calls in). Registered as statement kinds when symblic.kernel.language is imported.
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import contextlib
import fcntl
import hashlib
import json
import os
import re
import socket
import threading
import time
import uuid

from symblic.kernel import language as S

VERSION = 2
KINDS = ('observe', 'act')
OBSERVED = 'observed'              # determinism class of an observation: fixed inside a run by the ledger
EFFECT = 'effect'
DEFAULT_MAX_EFFECTS = 200
LEDGER = 'effects.jsonl'
CATALOGUE_FILE = 'effects-catalogue.json'    # the capabilities a run used, frozen beside its ledger
STATEMENT_OPTIONS = ('key', 'scope', 'timeout', 'mode', 'sources', 'allow_untrusted', 'weight')
READ = 'read'
EFFECT_CLASSES = ('read', 'compute', 'write-local', 'write-external', 'device', 'destructive', 'money')
UNTRUSTED, STEERED, PERSONAL = 'untrusted', 'steered', 'personal'
CONSEQUENTIAL = ('write-external', 'device', 'destructive', 'money')   # effect classes a steered act must not auto-run


def weighty(spec: dict) -> bool:
    """May this capability do something a person would want to be asked about: a consequential effect class, or
    arguments that instruct an agent or a program (which can then do anything its own tools allow)."""
    return (spec or {}).get('effect') in CONSEQUENTIAL or bool((spec or {}).get('instructs'))


# What a capability promises a program: what calling it means, which arguments it takes, and the flags the
# flow rules read. A run is pinned to it (effects-catalogue.json), and so is every attempt at an action (the
# `spec_sha256` of its ledger rows): an interrupted attempt is never continued under another contract.
CONTRACT_KEYS = ('effect', 'policy', 'params', 'idempotent', 'untrusted', 'sensitivity', 'egress', 'instructs')


def contract_sha(spec: dict) -> str:
    return hashlib.sha256(json.dumps({k: (spec or {}).get(k) for k in CONTRACT_KEYS}, sort_keys=True,
                                     ensure_ascii=False, separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


def needs_owner(kind: str, influence: str, spec: dict) -> bool:
    """Outside text chose this action (steered) or wrote part of it (untrusted, through allow_untrusted), and
    the action is weighty: a host must not approve it on its own."""
    return kind == 'act' and influence in (STEERED, UNTRUSTED) and weighty(spec)
MAX_CHECKED_VALUES = 50_000        # values one argument check may visit; more is refused, never skipped
MAX_ARGUMENT_DEPTH = 32
MAX_ARGUMENT_BYTES = 1_000_000
CLAIM_WAIT_S = 120.0               # how long to wait for another live run that is performing the same action
SYNC = True                        # fsync every ledger row before the call it announces; tests may turn it off
_CAP_RX = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$')
# `observe x = family.name(` / `act family.name(`: anything else that starts with the word stays prose
_LOOKS = re.compile(r'^(observe|act)\s+(?:[^\W\d]\w*\s*(?::[^=]*)?=\s*)?[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\s*\(',
                    re.I | re.S)


# ---------------------------------------------------------------------------
# Capability catalogue
# ---------------------------------------------------------------------------

def normalize_spec(name: str, raw: dict) -> dict:
    """One capability as this module reads it. Unknown or missing fields take the cautious value."""
    raw = raw or {}
    effect = str(raw.get('effect') or 'write-external')
    if effect not in EFFECT_CLASSES:
        effect = 'write-external'
    params = raw.get('params')
    if not isinstance(params, dict):
        params = {'type': 'object'}
    idem = raw.get('idempotent')
    return {'name': name, 'effect': effect, 'policy': str(raw.get('policy') or 'confirm'),
            'params': params, 'returns': raw.get('returns') if isinstance(raw.get('returns'), dict) else None,
            'idempotent': bool(idem) if idem is not None else effect == READ,
            'untrusted': bool(raw.get('untrusted')), 'sensitivity': str(raw.get('sensitivity') or ''),
            'egress': bool(raw.get('egress')),
            # its arguments are instructions an agent or a program will follow (start an agent, run a program)
            'instructs': bool(raw.get('instructs')),
            'timeout': raw.get('timeout'), 'summary': str(raw.get('summary') or '')[:300],
            'family': str(raw.get('family') or name.split('.')[0])}


def normalize_catalogue(rows) -> dict:
    """{name: spec} from a list of descriptor rows (a host capability catalogue) or a {name: row} dict."""
    if rows is None:
        return {}
    items = rows.items() if isinstance(rows, dict) else ((r.get('name'), r) for r in rows if isinstance(r, dict))
    out = {}
    for name, raw in items:
        if isinstance(name, str) and _CAP_RX.match(name):
            out[name] = normalize_spec(name, raw)
    return out


def catalogue_digest(cat: dict) -> str:
    """What typing was checked against: part of a run's regime, like the kernel id."""
    rows = [[n, s['effect'], s['policy'], s['params'], s['idempotent'], s['untrusted'], s['sensitivity'],
             s.get('egress', False)] for n, s in sorted((cat or {}).items())]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


_CATALOGUE: dict | None = None      # the process's catalogue for static checks; a run's host supplies its own
_LOCAL = threading.local()          # check(source, cat) checks against `cat` on this thread only
_UNSET = object()


def set_catalogue(rows) -> None:
    global _CATALOGUE
    _CATALOGUE = normalize_catalogue(rows) if rows is not None else None


def catalogue() -> dict | None:
    """The catalogue static checks use now: the one given to check() on this thread, else the process's."""
    over = getattr(_LOCAL, 'cat', _UNSET)
    return _CATALOGUE if over is _UNSET else over


# ---------------------------------------------------------------------------
# JSON Schema, the subset capability declarations use
# ---------------------------------------------------------------------------

_JSON_TYPES = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'null': type(None)}


def _is_type(value, name: str) -> bool:
    if name == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if name == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    t = _JSON_TYPES.get(name)
    return t is not None and isinstance(value, t) and not (name != 'boolean' and isinstance(value, bool))


def json_equal(a, b) -> bool:
    """JSON equality: true is not 1, numbers compare by value, arrays and objects member by member."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(v, b[k]) for k, v in a.items())
    return type(a) is type(b) and a == b


class _Budget:
    def __init__(self, left: int):
        self.left = left
        self.spent = False


def schema_errors(value, schema, path: str = '', _budget=None, _depth: int = 0) -> list:
    """Why `value` does not fit `schema` ([] when it fits). Keywords: type, enum, const, properties, required,
    additionalProperties, items, minItems, maxItems, minimum, maximum, minLength, maxLength, pattern. Every
    element is checked; a value too large or too deep to check within the limit is refused, never skipped."""
    budget = _budget or _Budget(MAX_CHECKED_VALUES)
    if budget.spent:
        return []
    budget.left -= 1
    if budget.left < 0 or _depth > MAX_ARGUMENT_DEPTH:
        budget.spent = True
        return [f'the arguments are too large or too deeply nested to check (limits: {MAX_CHECKED_VALUES} values, '
                f'depth {MAX_ARGUMENT_DEPTH})']
    if not isinstance(schema, dict):
        schema = {}                          # nothing declared here: still walk it, so the limit holds
    where = path or 'the arguments'
    out = []
    ty = schema.get('type')
    if ty is not None:
        names = ty if isinstance(ty, list) else [ty]
        if not any(_is_type(value, n) for n in names):
            return [f'{where} must be {" or ".join(str(n) for n in names)}']
    if isinstance(schema.get('enum'), list) and not any(json_equal(value, x) for x in schema['enum']):
        out.append(f'{where} must be one of {", ".join(json.dumps(x) for x in schema["enum"][:12])}')
    if 'const' in schema and not json_equal(value, schema['const']):
        out.append(f'{where} must be {json.dumps(schema["const"])}')
    if isinstance(value, str):
        if isinstance(schema.get('minLength'), int) and len(value) < schema['minLength']:
            out.append(f'{where} is shorter than {schema["minLength"]} characters')
        if isinstance(schema.get('maxLength'), int) and len(value) > schema['maxLength']:
            out.append(f'{where} is longer than {schema["maxLength"]} characters')
        pat = schema.get('pattern')
        if isinstance(pat, str):
            try:
                if not re.search(pat, value):
                    out.append(f'{where} does not match {pat}')
            except re.error:
                out.append(f'{where}: the capability declares an unreadable pattern')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(schema.get('minimum'), (int, float)) and value < schema['minimum']:
            out.append(f'{where} is below {schema["minimum"]}')
        if isinstance(schema.get('maximum'), (int, float)) and value > schema['maximum']:
            out.append(f'{where} is above {schema["maximum"]}')
    if isinstance(value, list):
        if isinstance(schema.get('minItems'), int) and len(value) < schema['minItems']:
            out.append(f'{where} has fewer than {schema["minItems"]} items')
        if isinstance(schema.get('maxItems'), int) and len(value) > schema['maxItems']:
            out.append(f'{where} has more than {schema["maxItems"]} items')
        items = schema.get('items')
        for i, x in enumerate(value):
            if len(out) >= 20 or budget.spent:
                break
            out += schema_errors(x, items, f'{path}[{i + 1}]' if path else f'item {i + 1}', budget, _depth + 1)
    if isinstance(value, dict):
        props = schema.get('properties') if isinstance(schema.get('properties'), dict) else {}
        for name in schema.get('required') or []:
            if name not in value:
                out.append(f'{(path + ".") if path else ""}{name} is required')
        if schema.get('additionalProperties') is False:
            for name in value:
                if name not in props:
                    known = ', '.join(sorted(props)) or 'none'
                    out.append(f'{(path + ".") if path else ""}{name} is not an argument (arguments: {known})')
        for name, x in value.items():
            if len(out) >= 20 or budget.spent:
                break
            out += schema_errors(x, props.get(name), f'{path}.{name}' if path else name, budget, _depth + 1)
    if budget.spent and _depth == 0:
        return [f'the arguments are too large or too deeply nested to check (limits: {MAX_CHECKED_VALUES} values, '
                f'depth {MAX_ARGUMENT_DEPTH})']
    return out


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse(kind: str):
    def parse(p: S.Parser, line: int, col: int, prog: dict) -> S.Node:
        name, ty = None, None
        bound = p.at('name') and (p.op('=', k=1) or p.op(':', k=1))
        if bound:
            name = p.expect_name('a name for the result').value
            if p.op(':'):
                p.take()
                ty = p.type_expr()
            p.expect_op('=')
        elif kind == 'observe':
            raise p.err('observe needs a name for what it reads: observe NAME = capability(...)')
        first = p.expect_name('a capability (family.name)')
        parts = [first.value]
        while p.at('attr'):
            p.take()
            seg = p.take()
            if seg.kind != 'name':
                raise S.SymblicError('expected a capability name after "."', seg.line, seg.col, 'syntax')
            parts.append(seg.value)
        capability = '.'.join(parts)
        if not _CAP_RX.match(capability):
            raise S.SymblicError(f'{capability!r} is not a capability name (family.name, lower case)', first.line,
                                 first.col, 'syntax')
        if not p.op('('):
            raise p.err(f'expected the arguments of {capability} in brackets')
        positional, args = p.call_args()
        if positional:
            raise S.SymblicError(f'the arguments of {capability} are named: {capability}(name=value, ...)',
                                 first.line, first.col, 'syntax')
        options = S.p_options(p) if p.word('with') else {}
        p.finish()
        for key in options:
            if key not in STATEMENT_OPTIONS:
                raise S.SymblicError(f'unknown {kind} option {key!r} (options: {", ".join(STATEMENT_OPTIONS)})',
                                     line, col, 'syntax')
        if kind == 'observe' and 'allow_untrusted' in options:
            raise S.SymblicError('allow_untrusted is an option of act', line, col, 'syntax')
        scope = options.get('scope')
        if isinstance(scope, S.Node) and scope.k == 'name' and scope.name.lower() in ('run', 'program'):
            options['scope'] = S.Node('str', scope.line, scope.col, parts=[scope.name.lower()])   # scope=program
        return S.Node(kind, line, col, name=name, type=ty, capability=capability, args=args, options=options,
                      cap_line=first.line, cap_col=first.col)
    return parse


def _reads(node: S.Node):
    return [list(node.args.values()), list(node.options.values())]


def _binds(node: S.Node) -> list:
    return [node.name] if node.name else []


def _label(node: S.Node) -> str:
    head = f'{node.k} {node.name} = ' if node.name else f'{node.k} '
    return f'{head}{node.capability}({", ".join(node.args)})'


# ---------------------------------------------------------------------------
# Static checks: typing against the catalogue, placement, information flow
# ---------------------------------------------------------------------------

def _diag(node, message: str, kind: str = 'check', severity: str = 'error') -> dict:
    row = {'line': node.line, 'col': node.col, 'kind': kind, 'code': 'SYM_' + kind.upper(), 'message': message}
    if severity == 'warning':
        row['severity'] = 'warning'
    return row


def _literal(node):
    """(True, json value) when an argument is a literal the checker can read without running anything."""
    if not isinstance(node, S.Node):
        return False, None
    if node.k in ('lit', 'num'):
        return True, to_argument(node.get('value'))
    if node.k == 'str':
        parts = node.get('parts') or []
        if all(isinstance(x, str) for x in parts):       # no {interpolation}
            return True, ''.join(parts)
        return False, None
    if node.k == 'list':
        items = [_literal(x) for x in (node.get('items') or [])]
        if all(ok for ok, _v in items):
            return True, [v for _ok, v in items]
        return False, None
    if node.k == 'record':
        fields = [(str(k), _literal(v)) for k, v in (node.get('fields') or [])]
        if all(ok for _k, (ok, _v) in fields):
            return True, {k: v for k, (_ok, v) in fields}
    return False, None


def check_node(node: S.Node, scope=frozenset(), cat: dict | None = None) -> list:
    """Diagnostics for one observe/act statement from its text alone: the capability exists, the statement
    kind fits its effect class, argument names are the declared ones and literal arguments fit the schema."""
    cat = catalogue() if cat is None else cat
    if cat is None:
        return [_diag(node, f'{node.capability} is unchecked: no capability catalogue is loaded', 'effect', 'warning')]
    spec = cat.get(node.capability)
    if spec is None:
        near = sorted(n for n in cat if n.split('.')[0] == node.capability.split('.')[0])[:8]
        hint = f' ({node.capability.split(".")[0]} has: {", ".join(near)})' if near else ''
        return [_diag(node, f'there is no capability {node.capability}{hint}', 'name')]
    out = []
    if node.k == 'observe' and spec['effect'] != READ:
        out.append(_diag(node, f'{node.capability} is not a read (its effect is {spec["effect"]}): use act'))
    if node.k == 'act' and spec['effect'] == READ:
        out.append(_diag(node, f'{node.capability} only reads: observe says so and needs no side effects', 'effect',
                         'warning'))
    if spec['policy'] == 'never':
        out.append(_diag(node, f'{node.capability} is never available to a program (policy never)'))
    params = spec['params']
    props = params.get('properties') if isinstance(params.get('properties'), dict) else {}
    literal = {}
    for name, value in node.args.items():
        if params.get('additionalProperties') is False and name not in props:
            known = ', '.join(sorted(props)) or 'none'
            out.append(_diag(node, f'{node.capability} has no argument {name} (arguments: {known})', 'type'))
            continue
        ok, v = _literal(value)
        if ok:
            literal[name] = v
            for msg in schema_errors(v, props.get(name), name):
                out.append(_diag(node, f'{node.capability}: {msg}', 'type'))
    for name in params.get('required') or []:
        if name not in node.args:
            out.append(_diag(node, f'{node.capability} needs the argument {name}', 'type'))
    return out


def _closed(ty, types: dict, line: int) -> bool:
    if ty is None:
        return False
    try:
        return S.determinism_class(S.resolve_type(ty, types, line)) == 'closed'
    except S.SymblicError:
        return False


def _names(node) -> set:
    try:
        return set(S.free_names(node))
    except Exception:  # noqa: BLE001  (an expression kind without names)
        return set()


def _has_query(node) -> bool:
    try:
        return any(getattr(n, 'k', '') == 'query' for n in S.walk(node))
    except Exception:  # noqa: BLE001
        return False


def _context(ctx):
    """An ask's (or a `use`/routine default's) context option as flow sees it: (wide, listed). `wide`: the capsule
    may carry any earlier result (all, last N, relevant, facts, or anything computed); `listed`: the list node of
    context=[a, b], whose names are read. No option, or none/clear/fresh: neither."""
    if not isinstance(ctx, S.Node):
        return False, None
    if ctx.k == 'list':
        # an item that is not a bare name is evaluated and its TEXT names a binding: any binding, so wide
        return not all(getattr(item, 'k', '') == 'name' for item in ctx.items), ctx
    word = str(ctx.get('name') if ctx.k == 'name' else ctx.get('value', '')).lower().split(' ')[0]
    return word not in ('none', 'clear', 'fresh'), None


def _params_bound(node, params):
    """node inside empty comprehensions that bind `params` (as symblic.lang.abstraction does for function bodies), so the
    names a callable's body reads leave out its own parameters and nothing else."""
    for p in reversed(list(params)):
        node = S.Node('comp', 0, 0, body=node, var=p, src=S.Node('list', 0, 0, items=[]), cond=None)
    return node


def _callable_reads(s):
    """What one function or routine definition reads when it runs: its defaults (they run in the defining scope,
    so they keep every name) and its body with its own parameters bound. For a routine, every body statement's
    reads, its asks' options and context lists, and the bare names of its facts. Also returns the flags flow
    needs: (nodes, {'wide', 'default_asks', 'facts', 'delegates', 'own_context'}); `default_asks`: an ask that
    takes the program's `use` default (none does inside a routine with its own `with context=`)."""
    params = list(getattr(s, 'params', None) or [])
    defaults = [spec['default'] for spec in getattr(s, 'specs', None) or [] if spec.get('default') is not None]
    flags = {'wide': False, 'default_asks': False, 'facts': False, 'delegates': False, 'own_context': False}
    if s.k == 'function':
        return [defaults, _params_bound(s.value, params)], flags
    body = []
    own = (getattr(s, 'options', None) or {}).get('context')
    # a routine's own `with context=` is the default of every ask inside it, and of its callees', while it runs
    flags['own_context'] = own is not None
    wide, listed = _context(own)
    flags['wide'] |= wide
    if listed is not None:
        body.append(listed)
    for t, _inside in _each(getattr(s, 'body', None) or []):
        body.append(S._reads_of(t))
        if t.k == 'ask':
            body.append([v for key, v in t.options.items() if key != 'context'])
            if t.options.get('context') is None and own is None:
                flags['default_asks'] = True
        if t.k in ('ask', 'use'):
            wide, listed = _context(t.options.get('context'))
            flags['wide'] |= wide
            if listed is not None:
                body.append(listed)
        elif t.k == 'fact':
            flags['facts'] = True
            body.append([a for _p, args in t.atoms for a in args if getattr(a, 'k', '') == 'name'])
        elif t.k == 'rule':                              # joins the shared knowledge base like a fact
            flags['facts'] = True
            body.append([t.args, t.body])
        elif t.k == 'delegate':
            flags['delegates'] = True
    return [defaults, _params_bound(body, params)], flags


def _callables(stmts) -> dict:
    """Every function and routine a program defines, at any depth, by name: one name defined in several places
    (sibling scopes, the passes of a loop) is the union of its definitions. Each row: `reads`, the value names
    its definitions read when called; `calls`, every name they call that is not a builtin (call names are
    strings, apart from value names; a builtin is always the builtin), local, imported or unknown alike;
    `query`; and the flags of `_callable_reads`. Imported
    callables are added by flow() from `_module_summary`: they read none of the program's values, but they share
    its callable registry, knowledge base and defaults."""
    defs = [s for s, _inside in _each(stmts) if s.k in ('function', 'routine') and getattr(s, 'name', None)]
    table: dict = {}
    for s in defs:
        nodes, flags = _callable_reads(s)
        row = table.setdefault(s.name, {'reads': set(), 'calls': set(), 'query': False, 'wide': False,
                                        'default_asks': False, 'facts': False, 'delegates': False,
                                        'own_context': True})
        row['reads'] |= _names(nodes)
        # every edge but a builtin's: flow resolves an imported or unknown callee where it reads the graph
        row['calls'] |= {n.fn for n in S.walk(nodes) if getattr(n, 'k', '') == 'call' and n.fn not in S.BUILTINS}
        row['query'] = row['query'] or _has_query(nodes)
        for key in _FLAGS[1:]:
            row[key] = row[key] or flags[key]
        row['own_context'] = row['own_context'] and flags['own_context']    # every definition must set one
    return table


_FLAGS = ('query', 'wide', 'default_asks', 'facts', 'delegates')


def _module_summary(name: str, saved: bool, depth: int = 0, seen: frozenset = frozenset()):
    """A library module as its callers see it: its exported callable names, what any of its callables may do
    (the flags, merged over the module and the modules it imports) and `foreign`, the names it calls that it
    neither defines nor imports: those resolve in the shared callable registry, where the importing program's own
    callables live. A module runs in its own value scope, so it reads none of the program's values; it does share
    the knowledge base and the run's defaults. None when the source cannot be summarised (a saved program, an
    unreadable module, an import cycle or chain too deep): the caller treats its callables as unknown."""
    if saved or depth > 8 or name in seen:
        return None
    try:
        from symblic.lang import abstraction as symblic_lang
        source = symblic_lang.library_source(name)
        stmts = S.parse(source)['statements'] if source is not None else None
    except Exception:  # noqa: BLE001  (no layer, unreadable or unparsable: unknown)
        return None
    if stmts is None:
        return None
    table = _callables(stmts)
    flags = {key: any(row[key] for row in table.values()) for key in _FLAGS}
    known, foreign, aliases = set(table), set(), set()
    for s, _inside in _each(stmts):
        if s.k != 'import':
            continue
        sub = _module_summary(s.module, s.saved, depth + 1, seen | {name})
        if sub is None:
            return None
        for key in _FLAGS:
            flags[key] = flags[key] or sub['flags'][key]
        foreign |= sub['foreign']
        if s.alias:
            aliases.add(s.alias)
        else:
            known |= set(sub['exports']) if s.names is None else set(s.names)
    for n in S.walk(stmts):
        if getattr(n, 'k', '') == 'call' and n.fn not in S.BUILTINS and n.fn not in known \
                and n.fn.split('.', 1)[0] not in aliases:
            foreign.add(n.fn)
    return {'exports': sorted(n for n in table if not n.startswith('_')), 'flags': flags, 'foreign': foreign}


def _imported(s) -> tuple:
    """(the callable names an import statement registers, the module's summary or None)."""
    summary = _module_summary(s.module, s.saved)
    if summary is None:
        return [], None
    exports = summary['exports'] if s.alias or s.names is None else [n for n in summary['exports'] if n in s.names]
    return [f'{s.alias}.{n}' if s.alias else n for n in exports], summary


def flow(prog: dict, cat: dict | None = None) -> dict:
    """Information-flow labels by name, statically.

    `untrusted`: text someone outside controls (a capability declared untrusted). The label follows everything
    computed from the value, including the answer of an ask that was shown it. An untrusted value may not be an
    argument of an act: outside text must never write an action.
    `steered`: what `untrusted` becomes when it passes through a closed type (Bool, a choice, a small Int range),
    and what a condition or a loop over such data puts on the statements inside it. Outside text then only
    chose among alternatives the program itself wrote. A steered act is allowed, and reported, so that a host
    can demand the owner's approval before a consequential one.
    `personal`: private data. It may not be an argument of a capability that sends data out (egress).

    Returns {'labels', 'origins', 'effects' (per observe/act: influence none|steered|untrusted), 'violations',
    'warnings'}."""
    cat = (catalogue() if cat is None else cat) or {}
    labels: dict = {}                       # name -> frozenset of labels
    origins: dict = {}                      # name -> where its untrusted/steered label came from
    # use_wide/use_lists: the `use context=` defaults seen so far (once wide, it stays possible: a later `use` may
    # sit in a branch that does not run)
    state = {'kb': frozenset(), 'kb_origin': '', 'use_wide': False, 'use_lists': [], 'rule_names': set()}
    types: dict = {}
    violations, warnings, effects = [], [], []
    integrity = {UNTRUSTED, STEERED}
    statements = prog.get('statements') or []
    # Callables: a call reads what its callee's body reads WHEN CALLED (a callable keeps its defining scope, which
    # later statements fill), plus what that scope held when it was defined (`declared`: a function defined in a
    # loop keeps that pass's values even after the name is bound again outside). Both, always: neither alone.
    callables = _callables(statements)
    defined = frozenset(callables)
    unknown = {'reads': set(), 'calls': set(defined), **{key: True for key in _FLAGS}}
    for s, _inside in _each(statements):
        if s.k == 'import':
            names, summary = _imported(s)
            for name in names:
                row = callables.setdefault(name, {'reads': set(), 'calls': set(), **{key: False for key in _FLAGS}})
                row['calls'] |= {f for f in summary['foreign'] if f in defined} | \
                    ({'?'} if summary['foreign'] - defined else set())
                for key in _FLAGS:
                    row[key] = row[key] or summary['flags'][key]
    declared: dict = {}                     # callable name -> (labels, origin) at its definitions, joined

    def callee_rows(node):
        """The callables a node can reach through calls, transitively, as (name, row) pairs. A name nobody
        defined or imported, or a call out of a module that could not be read, is `unknown`: it may query the
        knowledge base, ask with any context, assert facts, delegate or call any program callable back."""
        found, todo, steps = {}, [], 0
        for n in S.walk(node):
            if getattr(n, 'k', '') == 'call' and n.fn not in S.BUILTINS:
                todo.append(n.fn)
        while todo:
            steps += 1
            if steps > 20_000:                         # bounded: past this, everything is unknown
                found['?'] = unknown
                break
            f = todo.pop()
            if f in found:
                continue
            found[f] = row = callables.get(f, unknown)
            todo.extend(row['calls'])
        return sorted(found.items())

    def default_asks(node):
        """True when a callee asks with the program's `use` default: one reached through no routine that sets its
        own `with context=` (that routine's option is the default for everything it runs)."""
        todo = [n.fn for n in S.walk(node) if getattr(n, 'k', '') == 'call' and n.fn not in S.BUILTINS]
        seen = set()
        while todo:
            f = todo.pop()
            if f in seen:
                continue
            seen.add(f)
            row = callables.get(f, unknown)
            if row.get('own_context'):
                continue
            if row['default_asks']:
                return True
            todo.extend(row['calls'])
        return False

    def of(node, ctrl):
        ls, why = set(ctrl[0]), ctrl[1]
        rows = callee_rows(node)
        exposed = bool(rows) and default_asks(node)
        names = set(_names(node))
        for _f, row in rows:
            names |= row['reads']
        if exposed:
            names |= _names(state['use_lists'])
        for n in sorted(names):
            got = labels.get(n, frozenset())
            ls |= got
            if got & integrity and not why:
                why = origins.get(n, n)
        for f, _row in rows:
            got, origin = declared.get(f, (frozenset(), ''))
            ls |= got
            if got & integrity and not why:
                why = origin
        if _has_query(node) or any(row['query'] for _f, row in rows):
            ls |= state['kb']
            if state['kb'] & integrity and not why:
                why = state['kb_origin']
            for n in sorted(state['rule_names']):        # what the rules read, as it is when this query derives
                got = labels.get(n, frozenset())
                ls |= got
                if got & integrity and not why:
                    why = origins.get(n, n)
        if any(row['wide'] for _f, row in rows) or (exposed and state['use_wide']):
            # a callee asks with a wide context: its capsule may carry any earlier result, captured ones included
            for n, got in labels.items():
                ls |= got
                if got & integrity and not why:
                    why = origins.get(n, n)
            for got, origin in declared.values():
                ls |= got
                if got & integrity and not why:
                    why = origin
            ls |= state['kb']
        return frozenset(ls), why

    def call_effects(s, ctrl):
        """What a call does besides returning a value: the facts a callee asserts join the shared knowledge base,
        and a delegate inside a callee hands its task to an agent, which must not be built from outside text."""
        if s.k in ('function', 'routine', 'test', 'import'):
            return                                     # declarations: their calls run where they are called
        reads = [S._reads_of(s), list(s.options.values()) if s.k == 'ask' else []]
        for n in S.walk(reads):
            if getattr(n, 'k', '') != 'call' or n.fn in S.BUILTINS:
                continue
            rows = callee_rows(n)
            if not any(row['facts'] or row['delegates'] for _f, row in rows):
                continue
            ls, why = of(n, ctrl)
            if any(row['facts'] for _f, row in rows):
                state['kb'] = state['kb'] | ls
                if ls & integrity and not state['kb_origin']:
                    state['kb_origin'] = why
            if UNTRUSTED in ls and any(row['delegates'] for _f, row in rows):
                violations.append(_diag(s, f'{n.fn} can delegate a task to an agent, and this call can build it from '
                                           f'untrusted text ({why}): an agent with tools would follow it. Pass the '
                                           'text through a closed type first', 'flow'))

    def control(pair):
        """What a condition or a loop source puts on the statements it governs: a choice, never content."""
        return (frozenset({STEERED}), pair[1]) if pair[0] & integrity else (frozenset(), '')

    def bind(name, pair, ty, line):
        ls, why = set(pair[0]), pair[1]
        if UNTRUSTED in ls and _closed(ty, types, line):
            ls.discard(UNTRUSTED)
            ls.add(STEERED)
        labels[name] = frozenset(ls)
        if ls & integrity:
            origins[name] = why or name

    def visit(stmts, ctrl, inner=None):
        # `inner`: the names that can differ from one pass of the enclosing loop to the next (None outside a loop)
        for s in stmts:
            k = s.k
            if inner is not None and getattr(s, 'name', None) and k != 'define':
                inner.add(s.name)
            call_effects(s, ctrl)
            if k == 'define':
                types[s.name] = s.type
            elif k == 'given':
                # an input given by the run is the owner's; without one the default is evaluated here
                bind(s.name, of(s.default, ctrl) if s.default is not None else (frozenset(), ''), s.type, s.line)
            elif k == 'rule':
                # a rule reads the bindings it names when a query derives from it: every later query reads them
                state['rule_names'] |= _names([s.args, s.body])
            elif k == 'let':
                bind(s.name, of(s.value, ctrl), s.type, s.line)
            elif k == 'use':
                wide, listed = _context(s.options.get('context'))
                state['use_wide'] = state['use_wide'] or wide
                if listed is not None:
                    state['use_lists'].append(listed)
            elif k in ('function', 'routine'):
                # what this definition's scope holds now for the names its body reads, and the branch or loop that
                # chose to define it; callees, queries and contexts are read where it is called
                ls, why = set(ctrl[0]), ctrl[1]
                for n in sorted(_names(_callable_reads(s)[0])):
                    got = labels.get(n, frozenset())
                    ls |= got
                    if got & integrity and not why:
                        why = origins.get(n, n)
                old = declared.get(s.name, (frozenset(), ''))
                declared[s.name] = (old[0] | frozenset(ls), old[1] or why)
            elif k == 'ask':
                # the capsule shows the prompt's values, its `from` sources, every option it evaluates (examples=
                # among them) and its context: its own option, else the program's `use` default
                ctx = s.options.get('context')
                reads = [S._reads_of(s), [v for key, v in s.options.items() if key != 'context']]
                if ctx is None:
                    wide = state['use_wide']
                    reads.append(state['use_lists'])
                else:
                    wide, listed = _context(ctx)     # all, last N, relevant, facts or computed: wide
                    if listed is not None:
                        reads.append(listed)         # context=[a, b]: exactly those results
                pair = of(reads, ctrl)
                if wide:                             # the capsule may carry any earlier result
                    ls, why = set(pair[0]), pair[1]
                    for n, got in labels.items():
                        ls |= got
                        if got & integrity and not why:
                            why = origins.get(n, n)
                    ls |= state['kb']
                    pair = (frozenset(ls), why or state['kb_origin'])
                if PERSONAL in pair[0]:
                    by = s.options.get('by')
                    who = S._opt_text(by) if by is not None and hasattr(S, '_opt_text') else ''
                    warnings.append(_diag(s, f'{s.name}: the applicator{" " + who if who else ""} is shown personal '
                                             'data; keep it on a local model unless cloud use is intended',
                                          'effect', 'warning'))
                bind(s.name, pair, s.type, s.line)
            elif k == 'fact':
                # a bare name in a fact is the bound value when one exists (else an atom): count it as read
                named = [a for _pred, args in s.atoms for a in args if getattr(a, 'k', '') == 'name']
                pair = of([S._reads_of(s), named], ctrl)
                state['kb'] = state['kb'] | pair[0]
                if pair[0] & integrity and not state['kb_origin']:
                    state['kb_origin'] = pair[1]
            elif k == 'delegate':
                pair = of([s.task, s.target], ctrl)
                if UNTRUSTED in pair[0]:
                    violations.append(_diag(s, 'the delegated task is built from untrusted text '
                                               f'({pair[1]}): an agent with tools would follow it. Pass it through '
                                               'a closed type first', 'flow'))
                if s.name:
                    bind(s.name, pair, None, s.line)
            elif k in KINDS:
                spec = cat.get(s.capability) or {}
                allow = set()
                opt = s.options.get('allow_untrusted')
                if opt is not None:
                    ok, v = _literal(opt)
                    if ok and isinstance(v, str):
                        allow = {v}
                    elif ok and isinstance(v, list) and all(isinstance(x, str) for x in v):
                        allow = set(v)
                    else:
                        violations.append(_diag(s, 'allow_untrusted must name arguments literally, e.g. '
                                                   'allow_untrusted=["text"]', 'flow'))
                key_node = s.options.get('key')
                if k == 'act' and inner is not None and key_node is not None and not (_names(key_node) & inner):
                    warnings.append(_diag(s, f'act {s.capability}: the key is the same on every pass of the loop, so '
                                             'the action happens once for the whole loop. Put the loop\'s variable '
                                             'in the key to act once per pass', 'effect', 'warning'))
                total, why_all = set(ctrl[0]), ctrl[1]
                raw_args = []
                for name, value in s.args.items():
                    ls, why = of(value, (frozenset(), ''))
                    total |= ls
                    why_all = why_all or why
                    if UNTRUSTED in ls:
                        raw_args.append(name)
                        if k == 'act' and spec.get('instructs'):
                            violations.append(_diag(
                                s, f'act {s.capability}: the argument {name} is built from untrusted text ({why}), '
                                   f'and {s.capability} follows its arguments as instructions. Outside text never '
                                   'instructs an agent or a program: pass it through a closed type (a choice, Bool, '
                                   'a small Int range) and write the instruction yourself', 'flow'))
                        elif k == 'act' and name not in allow:
                            violations.append(_diag(
                                s, f'act {s.capability}: the argument {name} is built from untrusted text ({why}). '
                                   'Pass it through a closed type (a choice, Bool, a small Int range)', 'flow'))
                    if PERSONAL in ls and spec.get('egress'):
                        violations.append(_diag(s, f'{s.k} {s.capability}: the argument {name} carries personal data '
                                                   f'and {s.capability} sends its arguments out. Send only what the '
                                                   'program wrote or a closed value', 'flow'))
                influence = UNTRUSTED if raw_args else (STEERED if STEERED in total else 'none')
                effects.append({'line': s.line, 'col': s.col, 'kind': k, 'capability': s.capability,
                                'influence': influence, 'origin': why_all if influence != 'none' else '',
                                'untrusted_arguments': sorted(raw_args),
                                'consequential': weighty(spec)})
                out_labels = set(total) - {STEERED, UNTRUSTED}       # the result is the world's, not the caller's
                if total & integrity:
                    out_labels.add(STEERED)          # which result came back was chosen by outside text
                if raw_args:
                    # ...unless outside text was itself an argument: a tool may hand its arguments back (a search
                    # that quotes its query), so the result counts as outside text too
                    out_labels.add(UNTRUSTED)
                if spec.get('untrusted'):
                    out_labels.add(UNTRUSTED)
                    why_all = f'{s.capability}, line {s.line}'
                if spec.get('sensitivity') and spec['sensitivity'] not in ('public', 'none'):
                    out_labels.add(PERSONAL)
                if s.name:
                    bind(s.name, (frozenset(out_labels), why_all), s.type, s.line)
            elif k == 'if':
                # Exactly one path runs: every branch starts from the labels before the `if` (a sibling branch's
                # bindings are not there), reaching a branch is decided by its condition and every condition
                # above it, and afterwards a name carries what it carries on ANY path (the path where no branch
                # runs included: it keeps the label it had before).
                before = (dict(labels), dict(origins))
                paths = []
                above = (frozenset(), '')
                bodies = list(s.branches) + [(None, s.else_body or [])]
                for cond, body in bodies:
                    labels.clear()
                    labels.update(before[0])
                    origins.clear()
                    origins.update(before[1])
                    c = above
                    if cond is not None:
                        here = control(of(cond, ctrl))
                        c = (above[0] | here[0], above[1] or here[1])
                    visit(body, (ctrl[0] | c[0], ctrl[1] or c[1]), inner)
                    paths.append((dict(labels), dict(origins)))
                    if cond is not None:
                        above = c
                labels.clear()
                origins.clear()
                for path_labels, path_origins in paths:
                    for n, got in path_labels.items():
                        labels[n] = labels.get(n, frozenset()) | got
                    for n, origin in path_origins.items():
                        origins.setdefault(n, origin)
            elif k == 'for':
                src = of(s.src, ctrl)
                outer = (s.var in labels, labels.get(s.var), origins.get(s.var))
                labels[s.var] = src[0]
                if src[0] & integrity:
                    origins[s.var] = src[1]
                c = control(src)
                visit(s.body, (ctrl[0] | c[0], ctrl[1] or c[1]), (inner or set()) | {s.var})
                # each pass had its own scope: after `end` the name is the outside binding again, if there is one
                if outer[0]:
                    labels[s.var] = outer[1]
                else:
                    labels.pop(s.var, None)
                if outer[2] is not None:
                    origins[s.var] = outer[2]
                else:
                    origins.pop(s.var, None)
            elif k in S.EXTENSIONS:
                ext = S.EXTENSIONS[k]
                pair = of(ext.reads(s), ctrl)
                for name in ext.binds(s):
                    bind(name, pair, None, s.line)
                if k == 'import':                    # which module was imported can be a choice too
                    for name in _imported(s)[0]:
                        old = declared.get(name, (frozenset(), ''))
                        declared[name] = (old[0] | pair[0], old[1] or pair[1])
                # bodies of function/routine/test are declarations: observe/act are refused there (check_program)

    visit(prog.get('statements') or [], (frozenset(), ''))
    return {'labels': {n: sorted(v) for n, v in labels.items() if v}, 'origins': origins, 'effects': effects,
            'violations': violations, 'warnings': warnings}


def _each(stmts, inside=''):
    """(statement, enclosing declaration keyword or '') for every statement, bodies included."""
    for s in stmts:
        yield s, inside
        if s.k == 'if':
            for _c, body in s.branches:
                yield from _each(body, inside)
            if s.else_body:
                yield from _each(s.else_body, inside)
        elif s.k == 'for':
            yield from _each(s.body, inside)
        elif s.k in S.EXTENSIONS and S.EXTENSIONS[s.k].block:
            yield from _each(getattr(s, 'body', None) or [], s.k)


def check_program(prog: dict, cat: dict | None = None) -> list:
    """Whole-program diagnostics: placement (no observe/act inside a function, routine or test) and information
    flow. Typing of each statement is check_node's part; retry windows are the core's (symblic.kernel.language.retry_effects)."""
    cat = catalogue() if cat is None else cat
    stmts = prog.get('statements') or []
    out = []
    for s, inside in _each(stmts):
        if s.k in KINDS and inside:
            out.append(_diag(s, f'{s.k} cannot be used inside a {inside}: its result is remembered per '
                                'argument and may run during checks. Use it in the program body'))
    f = flow(prog, cat)
    return out + f['violations'] + f['warnings']


def _program_hook(kind: str):
    """The core calls check_program once per extension keyword a program uses. `act` reports; `observe` reports
    only for a program without an act, so nothing is said twice."""
    def hook(prog: dict) -> list:
        if kind == 'observe' and any(s.k == 'act' for s, _inside in _each(prog.get('statements') or [])):
            return []
        return check_program(prog)
    return hook


def plan(prog: dict, cat: dict | None = None) -> list:
    """The observe/act statements of a program, in order, with what the catalogue says about each."""
    cat = (catalogue() if cat is None else cat) or {}
    how = {(e['line'], e['col']): e for e in flow(prog, cat)['effects']}
    rows = []
    for s, _inside in _each(prog.get('statements') or []):
        if s.k in KINDS:
            spec = cat.get(s.capability) or {}
            inf = how.get((s.line, s.col)) or {}
            rows.append({'line': s.line, 'kind': s.k, 'capability': s.capability, 'name': s.name,
                         'arguments': sorted(s.args), 'effect': spec.get('effect'), 'policy': spec.get('policy'),
                         'known': s.capability in cat, 'summary': spec.get('summary', ''),
                         'influence': inf.get('influence', 'none'), 'origin': inf.get('origin', ''),
                         'needs_owner': needs_owner(s.k, inf.get('influence', 'none'), spec)})
    return rows


def check(source: str, cat=_UNSET) -> dict:
    """symblic.kernel.language.check with capabilities typed against `cat` (the process's catalogue when not given; None means
    none), plus `effects` (the observe/act statements), `flow` (labels by name) and `catalogue` (its digest)."""
    if cat is not _UNSET:
        cat = normalize_catalogue(cat) if isinstance(cat, list) else cat
        prior = getattr(_LOCAL, 'cat', _UNSET)
        _LOCAL.cat = cat
    try:
        res = S.check(source)
        active = catalogue()
        res['effects'], res['flow'] = [], {}
        res['catalogue'] = catalogue_digest(active) if active is not None else None
        try:
            prog = S.parse(source)
        except S.SymblicError:
            return res
        res['effects'] = plan(prog, active)
        res['flow'] = flow(prog, active)['labels']
        return res
    finally:
        if cat is not _UNSET:
            if prior is _UNSET:
                del _LOCAL.cat
            else:
                _LOCAL.cat = prior


# ---------------------------------------------------------------------------
# Identity and the ledger
# ---------------------------------------------------------------------------

def to_argument(value):
    """A Symblic value as the JSON a capability receives (integers stay integers, other numbers are floats,
    sets are sorted lists)."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if S.is_num(value):
        v = S.norm_num(value)
        return v if isinstance(v, int) else float(v)
    if isinstance(value, (list, tuple)):
        return [to_argument(x) for x in value]
    if isinstance(value, frozenset):
        return [to_argument(x) for x in sorted(value, key=lambda x: S.canon_json(x))]
    if isinstance(value, dict):
        return {str(k): to_argument(v) for k, v in sorted(value.items())}
    return S.show(value)


def effect_id(capability: str, args: dict, key: str = '', kind: str = 'observe') -> str:
    """The identity of one observation or action: what is asked of the world, not where in the program.

    An action with a key IS its key: `act ... with key="digest-2026-10-03"` names one action, and a second call
    under that name is the same action whatever its arguments say by then (a count that moved, a rewritten
    text). Everything else is identified by the capability and its arguments, plus the key when one is given."""
    if kind == 'act' and key:
        parts = [VERSION, capability, None, key]
    else:
        parts = [VERSION, capability, args, key or '']
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                                     default=str).encode('utf-8')).hexdigest()


class Ledger:
    """Append-only record of intents and outcomes, one JSON row per line. `path` None keeps it in memory.

    Several runs (threads or processes) may share one file. Whoever is to perform an action first CLAIMS it:
    under an exclusive lock on `<path>.lock` the file is read again and the intent row is written only if
    nobody holds the action. So two runs that reach the same action at the same moment cannot both perform it.
    A row is fully written and synced before the call it announces is made. An unreadable row means nothing
    new is performed from this ledger until someone repairs it; an unfinished last row is cut off (no call
    follows an unfinished intent, and an unfinished outcome leaves its intent standing, which keeps the action
    uncertain)."""

    def __init__(self, path: str | None):
        self.path = path
        self.lock = threading.RLock()
        self.rows: dict = {}                # id -> the latest row for that id
        self.failed: dict = {}              # id -> how many times it ended `failed` (nothing happened)
        self.count = 0
        self.offset = 0                     # bytes of the file already read
        self.damaged = ''
        self.owner = {'host': socket.gethostname(), 'pid': os.getpid(), 'token': uuid.uuid4().hex}
        if path:
            with self._exclusive():
                self._refresh()

    @contextlib.contextmanager
    def _exclusive(self):
        with self.lock:
            if not self.path:
                yield
                return
            fd = os.open(self.path + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)

    def _refresh(self) -> None:
        """Read what others appended. Call with the exclusive lock held: no writer is then mid-row."""
        try:
            with open(self.path, 'rb') as f:
                f.seek(self.offset)
                data = f.read()
        except FileNotFoundError:
            return
        pos = 0
        while True:
            nl = data.find(b'\n', pos)
            if nl < 0:
                break
            raw, at = data[pos:nl], self.offset + pos
            pos = nl + 1
            if not raw.strip():
                continue
            try:
                row = json.loads(raw.decode('utf-8'))
                good = isinstance(row, dict) and isinstance(row.get('id'), str) and isinstance(row.get('phase'), str)
            except (ValueError, UnicodeDecodeError):
                good = False
            if not good:
                self.damaged = self.damaged or f'the row at byte {at} cannot be read'
                continue
            self.rows[row['id']] = row
            self.count += 1
            if row.get('phase') == 'failed':
                self.failed[row['id']] = self.failed.get(row['id'], 0) + 1
        self.offset += pos
        if data[pos:]:                       # an unfinished last row: cut it off
            with open(self.path, 'r+b') as f:
                f.truncate(self.offset)
                f.flush()
                if SYNC:
                    os.fsync(f.fileno())

    def _write(self, row: dict) -> dict:
        row = {'at': round(time.time(), 3), **row, 'v': VERSION}     # a copied row keeps when it was acquired
        data = (json.dumps(row, ensure_ascii=False, default=str) + '\n').encode('utf-8')
        if self.path:
            new = not os.path.exists(self.path)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                view = memoryview(data)
                while view:                  # a short write is finished, not left as half a row
                    view = view[os.write(fd, view):]
                if SYNC:
                    os.fsync(fd)
            finally:
                os.close(fd)
            if new and SYNC:
                with contextlib.suppress(OSError):
                    dfd = os.open(os.path.dirname(self.path) or '.', os.O_RDONLY)
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
            self.offset += len(data)
        self.rows[row['id']] = row
        self.count += 1
        if row.get('phase') == 'failed':
            self.failed[row['id']] = self.failed.get(row['id'], 0) + 1
        return row

    def get(self, eid: str):
        """The latest row this ledger object has read for the id (refresh() first to see other writers)."""
        with self.lock:
            return self.rows.get(eid)

    def refresh(self) -> None:
        if self.path:
            with self._exclusive():
                self._refresh()

    def append(self, row: dict) -> dict:
        with self._exclusive():
            if self.path:
                self._refresh()
            return self._write(row)

    def claim(self, eid: str, intent: dict, repeatable: bool, takeover: bool = False):
        """(state, row). 'done': an outcome exists, use it. 'claimed': the intent row is written and this caller
        performs the action. 'busy': someone else's intent or an unknown outcome stands. 'drift': an earlier
        attempt may be under way and the capability's contract is no longer the one it began under (nothing is
        written). 'damaged': the file cannot be trusted, nothing new is performed. One atomic step for every
        run that shares the file.

        While another running claimant holds the intent, everyone else is 'busy', a read included: they wait
        and take its outcome, so all of them see one result. `repeatable` (a read, an idempotent action) only
        allows starting again after an interrupted or unknown attempt, or with `takeover` once waiting ran out."""
        with self._exclusive():
            if self.path:
                self._refresh()
            cur = self.rows.get(eid)
            if cur is not None and cur.get('phase') == 'done':
                return 'done', cur
            if self.damaged:
                return 'damaged', cur
            live = cur is not None and cur.get('phase') == 'intent' and _alive_elsewhere(cur, self.owner)
            if cur is None or cur.get('phase') == 'failed' or (repeatable and (takeover or not live)):
                attempt = int((cur or {}).get('attempt') or 0) + 1
                if cur is not None and cur.get('phase') != 'failed':
                    # An earlier attempt at this action may be under way: this claim continues THAT request,
                    # which is one record: its arguments, the contract they were checked under, where they
                    # came from and how they must be approved. An action is continued only when that record
                    # is complete, intact and still describes the capability as it is now. Otherwise nothing
                    # is written: the standing row keeps saying "unknown", and the owner settles it.
                    if intent.get('kind') == 'act' and recovery_block(cur, intent):
                        return 'drift', cur
                    intent = continued(cur, intent)
                return 'claimed', self._write({**intent, 'phase': 'intent', 'attempt': attempt, 'owner': self.owner})
            return 'busy', cur

    def all(self) -> list:
        with self.lock:
            return list(self.rows.values())

    def failures(self, eid: str) -> int:
        """How many attempts at this id ended `failed`: each of those is over, so the next one is a new request."""
        with self.lock:
            return int(self.failed.get(eid, 0))


_RANK = {'none': 0, STEERED: 1, UNTRUSTED: 2}
_CARRIED = ('influence', 'influence_origin', 'needs_owner', 'effect', 'policy', 'spec', 'spec_sha256',
            'args_source_sha256', 'continues')
_PINS = ('args', 'args_sha256', 'spec', 'spec_sha256', 'influence', 'needs_owner')


def recovery_block(cur: dict, intent: dict) -> str:
    """Why an interrupted or unknown attempt at an action may NOT be continued by itself; '' when it may.

    The arguments that would be sent are the earlier attempt's. They were checked, and their approval decided,
    against the capability as it was then; the caller's own check covered other arguments. So the record must
    carry all of it (a row an older writer left without its contract or labels cannot be vouched for by the
    program that happens to come next), must match its hashes, and the capability must be unchanged."""
    spec = cur.get('spec')
    if any(cur.get(k) is None for k in _PINS) or not isinstance(spec, dict) or any(k not in spec for k in CONTRACT_KEYS):
        return 'it was recorded without its full contract and approval labels'
    try:
        whole = (cur['args_sha256'] == _sha(cur['args']) and cur['spec_sha256'] == contract_sha(spec)
                 and cur.get('id') == effect_id(str(cur.get('capability')), cur['args'], cur.get('key') or '',
                                                str(cur.get('kind') or 'act')))
    except (TypeError, ValueError):
        whole = False
    if not whole:
        return 'its record does not match the hashes written with it'
    if cur['spec_sha256'] != intent.get('spec_sha256'):
        return 'the capability is no longer what it was when that attempt began'
    return ''


def continued(cur: dict, intent: dict) -> dict:
    """The intent of a claim that continues an attempt which may be under way (an interrupted or unknown one).
    It is THAT request: its arguments, the contract they were checked under, the source that wrote them, and
    everything that decided how it must be approved (for an action, claim() has already made sure the record
    is complete and the capability unchanged: recovery_block). What the continuing statement would have
    asked for is not what is performed, so its own labels cannot lower the first ones: across a takeover the
    requirements only ever rise. A row written without labels (an older writer) is read as the strictest."""
    labelled = 'influence' in cur and 'needs_owner' in cur
    was = str(cur.get('influence') or 'none') if labelled else UNTRUSTED
    now = str(intent.get('influence') or 'none')
    keep = _RANK.get(was, 2) >= _RANK.get(now, 2)
    out = dict(intent)
    for k in ('args', 'args_sha256', 'spec', 'spec_sha256', 'effect', 'policy'):
        if cur.get(k) is not None:          # the original request, whole (a bare read row has little to carry)
            out[k] = cur[k]
    out['args_source_sha256'] = cur.get('args_source_sha256') or cur.get('source_sha256')
    out['influence'] = was if keep else now
    if keep:
        out['influence_origin'] = str(cur.get('influence_origin') or '') if labelled else \
            'an earlier attempt recorded without labels'
    out['needs_owner'] = bool(intent.get('needs_owner')) or (bool(cur.get('needs_owner')) if labelled else True)
    out['continues'] = int(cur.get('attempt') or 0)      # the attempt this one takes over
    return out


def intact(row: dict) -> bool:
    """Does a recorded outcome still match the hashes written with it (identity, arguments, result)?"""
    try:
        return (row.get('id') == effect_id(str(row.get('capability')), row.get('args'), row.get('key') or '',
                                           str(row.get('kind') or 'observe'))
                and row.get('args_sha256') == _sha(row.get('args'))
                and row.get('result_sha256') == _sha(row.get('result')))
    except (TypeError, ValueError):
        return False


def _alive_elsewhere(row: dict, mine: dict) -> bool:
    """Is the claimant of this intent a different, still running claimant on this machine?"""
    owner = row.get('owner') if isinstance(row.get('owner'), dict) else {}
    if not owner or owner.get('token') == mine.get('token') or owner.get('host') != mine.get('host'):
        return False
    try:
        os.kill(int(owner.get('pid')), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def resolve(path: str, eid: str, happened: bool, result=None, by: str = 'owner') -> dict:
    """The owner's word on an action whose outcome was never recorded: it happened (with what result, if
    known) or it did not. Appended like any other row; the next run continues from it."""
    led = Ledger(path)
    if led.damaged:
        raise ValueError(f'the ledger is damaged ({led.damaged}); repair it first')
    row = led.get(eid)
    if row is None:
        raise ValueError('no such effect in this ledger')
    if row.get('phase') == 'done':
        raise ValueError('that effect already has an outcome')
    base = {k: row.get(k) for k in ('id', 'kind', 'capability', 'args', 'args_sha256', 'key', 'line', 'scope',
                                    'attempt', 'source_sha256', 'spec', 'effect', 'policy')}
    base.update({k: row[k] for k in _CARRIED if k in row})
    if happened:
        return led.append({**base, 'phase': 'done', 'ok': True, 'result': result, 'result_sha256': _sha(result),
                           'resolved_by': by})
    return led.append({**base, 'phase': 'failed', 'ok': False, 'error': 'resolved: it did not happen',
                       'resolved_by': by})


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class _State:
    """What this module keeps for one Run: its ledger(s), the catalogue in force and a counter."""

    def __init__(self, run):
        folder = getattr(run.store, 'dir', None)
        self.replay = bool(run.opts.get('replay'))
        self.ledger = Ledger(os.path.join(folder, LEDGER) if folder else None)
        # a replay reads this run's own files and nothing else: no host, and the program's ledger is never opened
        self.host = None if self.replay else run.opts.get('effects')
        shared = run.opts.get('effects_ledger')
        self.program_ledger = Ledger(shared) if isinstance(shared, str) and shared and not self.replay else None
        self.problem = ''                   # why nothing may be performed in this run
        cat = None
        if self.host is not None and hasattr(self.host, 'catalogue'):
            cat = normalize_catalogue(self.host.catalogue())
        frozen = _load_frozen(folder)
        if frozen == {}:
            self.problem = f'{CATALOGUE_FILE} in the run folder cannot be read'
            frozen = None
        if cat is not None and folder:
            self.digest = catalogue_digest(cat)
            used = _used(run.source)
            if frozen is not None:
                # a run is pinned to the capabilities it names as they were when it began; the rest of the
                # catalogue may grow. A changed capability means a different program: start a new run.
                was = normalize_catalogue(frozen.get('capabilities') or {})
                for name in sorted(used & set(was)):
                    now = cat.get(name)
                    if now is None or any(now[k] != was[name][k] for k in CONTRACT_KEYS):
                        self.problem = (f'the capability {name} changed since this run began; a run is pinned to '
                                        'the capabilities it started with: start a new run')
                        break
                cat_frozen = {**{n: cat[n] for n in used if n in cat}, **{n: was[n] for n in was if n in used}}
            else:
                cat_frozen = {n: cat[n] for n in used if n in cat}
            if not self.problem and not _freeze(folder, cat_frozen,
                                                self.digest if frozen is None else frozen.get('digest')):
                self.problem = f'{CATALOGUE_FILE} cannot be written in the run folder: nothing is performed unpinned'
        elif cat is None and frozen is not None:
            cat, self.digest = normalize_catalogue(frozen.get('capabilities') or {}), frozen.get('digest')
        else:
            self.digest = catalogue_digest(cat) if cat is not None else None
        self.cat = cat if cat is not None else (catalogue() or {})
        self.typed = cat is not None or catalogue() is not None
        try:
            self.influence = {(e['line'], e['col']): e for e in flow(S.parse(run.source), self.cat)['effects']}
        except S.SymblicError:
            self.influence = {}
        # the limit is the run's, not the process's: what earlier passes over this folder recorded counts
        # (a `failed` one does not: it is claimed, and counted, again)
        self.fired = sum(1 for r in self.ledger.all() if r.get('phase') != 'failed')
        self.max = int(run.opts.get('max_effects') or DEFAULT_MAX_EFFECTS)
        self.wait = float(run.opts.get('effects_wait') if run.opts.get('effects_wait') is not None else CLAIM_WAIT_S)
        self.rows: list = []                # one summary per executed statement, for the host's report
        self.lock = threading.Lock()


def _used(source: str) -> set:
    try:
        return {s.capability for s, _inside in _each(S.parse(source).get('statements') or []) if s.k in KINDS}
    except S.SymblicError:
        return set()


def _load_frozen(folder):
    """The frozen catalogue of a run folder: a dict, None when there is none, {} when the file is damaged."""
    if not folder:
        return None
    path = os.path.join(folder, CATALOGUE_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get('capabilities'), dict) or data.get('version') != VERSION:
        return {}
    return data


def _freeze(folder: str, used_specs: dict, digest) -> bool:
    """effects-catalogue.json: {version, digest (of the host's whole catalogue when the run began), capabilities:
    {name: spec}} for the capabilities this program names. A replay without a host types and labels from it."""
    data = {'version': VERSION, 'digest': digest, 'capabilities': {n: used_specs[n] for n in sorted(used_specs)}}
    path = os.path.join(folder, CATALOGUE_FILE)
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.flush()
            if SYNC:
                os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        return False


def state(run) -> _State:
    st = getattr(run, '_effects', None)
    if st is None:
        st = _State(run)
        run._effects = st
        run.effects = st.rows
    return st


def _in_retry_window(run, node) -> bool:
    from symblic.kernel import run as SR
    for plan_ in list(getattr(run, '_checks', {}).values()):
        if any(t is node for t in SR._flat(plan_.get('between') or [])):
            return True
    return False


def _option(run, node, env, key, default=None):
    opt = node.options.get(key)
    if opt is None:
        return default
    return run.kernel.eval(opt, env)


def _fail(node, message: str, kind: str = 'effect'):
    return S.SymblicError(message, node.line, node.col, kind)


def _execute(kind: str):
    def execute(run, node, env) -> None:
        st = state(run)
        cap = node.capability
        t0 = time.time()
        if run.opts.get('preview'):
            raise _fail(node, f'a preview stops here: {kind} {cap} would reach the world')
        replay = st.replay
        if st.problem:
            raise _fail(node, st.problem, 'uncertain' if 'cannot be' in st.problem else 'effect')
        spec = st.cat.get(cap)
        if spec is None:
            if st.typed:
                raise _fail(node, f'there is no capability {cap}', 'name')
            spec = normalize_spec(cap, {'effect': READ if kind == 'observe' else 'write-external',
                                        'policy': 'auto' if kind == 'observe' else 'confirm'})
        if kind == 'observe' and spec['effect'] != READ:
            raise _fail(node, f'{cap} is not a read (its effect is {spec["effect"]}): use act')
        if kind == 'act':
            if not replay and not run.opts.get('side_effects'):
                raise _fail(node, f'act {cap} changes something: run the program with side effects allowed')
            if _in_retry_window(run, node):
                raise _fail(node, f'the act at line {node.line} lies between an ask and the ensure that may re-ask '
                                  'it: a retry would act on a rejected answer. Move it after the ensure', 'check')
        values = {name: run.kernel.eval(expr, env) for name, expr in node.args.items()}
        args = {name: to_argument(v) for name, v in values.items()}
        problems = schema_errors(args, spec['params'])
        if not problems and len(json.dumps(args, ensure_ascii=False)) > MAX_ARGUMENT_BYTES:
            problems = [f'the arguments are larger than {MAX_ARGUMENT_BYTES} bytes']
        if problems:
            raise _fail(node, f'{cap}: ' + '; '.join(problems[:4]), 'type')
        key = _option(run, node, env, 'key', '')
        key = S.show(key) if key not in ('', None) else ''
        scope = str(_option(run, node, env, 'scope', 'run')).lower()
        if scope not in ('run', 'program'):
            raise _fail(node, 'scope must be run or program', 'type')
        if scope == 'program' and not key:
            raise _fail(node, 'scope=program needs a key: it names the action across runs', 'type')
        ledger = st.ledger
        if scope == 'program' and not replay:        # a replay reads only the copy this run kept
            if st.program_ledger is None:
                raise _fail(node, 'scope=program needs a host that keeps a ledger for the program')
            ledger = st.program_ledger
        eid = effect_id(cap, args, key, kind)
        frozen = {**{k: spec[k] for k in CONTRACT_KEYS}, 'family': spec['family']}       # the whole contract
        base = {'id': eid, 'kind': kind, 'capability': cap, 'args': args, 'args_sha256': _sha(args), 'key': key,
                'line': node.line, 'scope': scope, 'source_sha256': getattr(run, 'source_sha256', None),
                'spec': frozen, 'spec_sha256': contract_sha(spec)}
        # a host that is idempotent by effect id (it hands the id to the service as its request id) can be
        # asked again after an interrupted or unknown attempt: the service continues the same action
        repeatable = (kind == 'observe' or bool(spec['idempotent'])
                      or bool(getattr(st.host, 'idempotent_by_id', False)))
        inf = st.influence.get((node.line, node.col)) or {}
        # outside text chose this action among the program's alternatives: a host must not approve a
        # consequential one on its own
        steer = {'influence': inf.get('influence', 'none'), 'influence_origin': inf.get('origin', ''),
                 'needs_owner': needs_owner(kind, inf.get('influence', 'none'), spec)}
        replayed = False
        if replay:
            outcome = ledger.get(eid)
            if outcome is None or outcome.get('phase') != 'done':
                raise _fail(node, f'a replay has no recorded outcome for {kind} {cap}: nothing is called in a replay')
            if outcome.get('source_sha256') not in (None, base['source_sha256']):
                # a resume may continue an edited program (an act must never fire twice because a line moved);
                # a replay claims to reproduce one program text, so it only reads what that text recorded
                raise _fail(node, f'the recorded outcome of {kind} {cap} belongs to a different program text: a '
                                  'replay is pinned to the source that recorded it')
            replayed = True
        else:
            waited = 0.0
            while True:
                how, row = ledger.claim(eid, {**base, 'effect': spec['effect'], 'policy': spec['policy'], **steer},
                                        repeatable, takeover=waited >= st.wait)
                if how in ('done', 'claimed'):
                    break
                if how == 'damaged':
                    raise _fail(node, f'the effects ledger is damaged ({ledger.damaged}): nothing is performed '
                                      'from it until it is repaired', 'uncertain')
                if how == 'drift':
                    if ledger is not st.ledger and (st.ledger.get(eid) or {}).get('phase') != row.get('phase'):
                        st.ledger.append({**row, 'copied_from': 'program'})  # visible, and resolvable, from this run
                    why = recovery_block(row, {**base, **steer}) or 'it cannot be continued safely'
                    raise _fail(node, f'an earlier attempt at {cap} (effect {eid[:12]}) may have happened, and '
                                      f'{why}. Nothing is sent and nothing is tried afresh: say whether it '
                                      'happened, then run this again', 'uncertain')
                if row.get('phase') == 'intent' and _alive_elsewhere(row, ledger.owner) and waited < st.wait:
                    run.check_stop()                 # another run is performing exactly this: wait for its word
                    time.sleep(0.2)
                    waited += 0.2
                    continue
                if ledger is not st.ledger and row is not None and (st.ledger.get(eid) or {}).get('phase') != \
                        row.get('phase'):
                    st.ledger.append({**row, 'copied_from': 'program'})      # visible, and resolvable, from this run
                raise _fail(node, f'the outcome of an earlier {cap} with these arguments is unknown (effect '
                                  f'{eid[:12]}). Say whether it happened before running this again', 'uncertain')
            if how == 'done':
                outcome, replayed = row, True
            else:
                attempt = row['attempt']
                # What is performed is what the claim wrote: for a continued attempt that is the first one's
                # arguments together with its labels and its pinned capability (continued()), never this
                # statement's own. Every later row repeats them, so a further recovery reads them again.
                steer = {'influence': row.get('influence', steer['influence']),
                         'influence_origin': row.get('influence_origin', steer['influence_origin']),
                         'needs_owner': bool(row.get('needs_owner', steer['needs_owner']))}
                base = {**base, 'args': row['args'], 'args_sha256': row['args_sha256'],
                        'effect': row.get('effect', spec['effect']), 'policy': row.get('policy', spec['policy']),
                        **({'spec': row['spec'], 'spec_sha256': row.get('spec_sha256') or base['spec_sha256']}
                           if isinstance(row.get('spec'), dict) else {}),
                        **({'args_source_sha256': row['args_source_sha256']} if row.get('args_source_sha256') else {}),
                        **({'continues': row['continues']} if 'continues' in row else {}),
                        **steer}
                # This run did not perform it. If the claim continued an earlier attempt, that attempt may still
                # have happened: the record must go back to unknown, never to "nothing happened".
                unperformed = 'unknown' if 'continues' in row else 'failed'
                if 'continues' in row:
                    # the arguments that will be sent are the earlier attempt's, whether or not they equal the
                    # ones checked above: they are checked against the schema here, before anything is sent
                    stale = schema_errors(base['args'], spec['params'])
                    if not stale and len(json.dumps(base['args'], ensure_ascii=False)) > MAX_ARGUMENT_BYTES:
                        stale = [f'the arguments are larger than {MAX_ARGUMENT_BYTES} bytes']
                    if stale:
                        ledger.append({**base, 'phase': unperformed, 'ok': False, 'attempt': attempt,
                                       'error': 'not performed: the earlier attempt\'s arguments do not fit the '
                                                'capability: ' + '; '.join(stale[:3])})
                        raise _fail(node, f'{cap}: the arguments of the earlier attempt this would continue do not '
                                          f'fit the capability ({"; ".join(stale[:3])}). Nothing is sent: say '
                                          f'whether that attempt (effect {eid[:12]}) happened', 'uncertain')
                if st.host is None or not hasattr(st.host, 'perform'):
                    ledger.append({**base, 'phase': unperformed, 'ok': False, 'attempt': attempt,
                                   'error': 'no capability host is connected'})
                    raise _fail(node, f'no capability host is connected: {kind} {cap} cannot run here',
                                'uncertain' if unperformed == 'unknown' else 'effect')
                with st.lock:
                    over = st.fired >= st.max
                    st.fired += 0 if over else 1
                if over:
                    ledger.append({**base, 'phase': unperformed, 'ok': False, 'attempt': attempt,
                                   'error': 'not performed: the run reached its limit'})
                    raise _fail(node, f'the program reached its limit of {st.max} observations and actions', 'budget')
                timeout = _option(run, node, env, 'timeout')
                effect = {**base, 'idempotent': spec['idempotent'], 'attempt': attempt,
                          'failures': ledger.failures(eid),
                          'timeout': to_argument(timeout) if S.is_num(timeout) else spec['timeout']}
                try:
                    out = st.host.perform(effect, run.stop)
                except Exception as e:  # noqa: BLE001  (a host that breaks mid-call may or may not have acted)
                    out = {'status': 'unknown' if kind == 'act' else 'failed', 'error': f'{type(e).__name__}: {e}'}
                if not isinstance(out, dict):
                    out = {'status': 'unknown' if kind == 'act' else 'failed', 'error': 'the host gave no outcome'}
                status = out.get('status')
                if status == 'done':
                    outcome = ledger.append({**base, 'phase': 'done', 'ok': True, 'result': out.get('result'),
                                             'result_sha256': _sha(out.get('result')), 'receipt': out.get('receipt'),
                                             'attempt': attempt, 'ms': int((time.time() - t0) * 1000)})
                else:
                    phase = 'failed' if status in ('failed', 'denied') else 'unknown'
                    error = str(out.get('error') or status or 'no outcome')[:600]
                    ended = ledger.append({**base, 'phase': phase, 'ok': False, 'error': error,
                                           'receipt': out.get('receipt'), 'attempt': attempt})
                    if ledger is not st.ledger:      # the run's own record shows what the program's ledger holds
                        st.ledger.append({**ended, 'copied_from': 'program'})
                    st.rows.append({'id': eid, 'kind': kind, 'capability': cap, 'line': node.line, 'status': phase})
                    if phase == 'unknown':
                        run.check_stop()             # a stop during the call is a stop, not a failure
                        raise _fail(node, f'{kind} {cap}: the outcome is unknown ({error}). It may have happened; '
                                          f'effect {eid[:12]} needs the owner\'s word before a rerun', 'uncertain')
                    raise _fail(node, f'{kind} {cap} failed: {error}')
            if ledger is not st.ledger:              # the run keeps its own copy: a replay never leaves its folder
                mine = st.ledger.get(eid)
                if mine is None or mine.get('phase') != 'done':
                    st.ledger.append({**outcome, 'copied_from': 'program'})
            run.check_stop()
        if replayed and not intact(outcome):
            raise _fail(node, f'the recorded outcome of {kind} {cap} (effect {eid[:12]}) does not match the hashes '
                              'written with it: the ledger was altered. Nothing is served from an altered row',
                        'uncertain')
        result = outcome.get('result')
        if isinstance(outcome.get('spec'), dict):    # label the value as it was labelled when it was acquired
            spec = {**spec, **outcome['spec']}
        st.rows.append({'id': eid, 'kind': kind, 'capability': cap, 'line': node.line, 'status': 'done',
                        'replayed': replayed})
        said = f'{cap} {eid[:12]}' + (' (from the ledger)' if replayed else '')
        if replayed and outcome.get('args_sha256') != base['args_sha256']:
            said += '; done earlier under this key with other arguments, and not done again'
        if not node.name:
            run._trace(node, 'ok', note=said)
            return
        ty = S.resolve_type(node.type, run.types, node.line) if node.type is not None else None
        try:
            value = S.coerce(result, ty, node.name) if ty is not None else S.from_json(result)
        except S.SymblicError as e:
            raise _fail(node, f'{cap} returned something the type does not accept: {e.message}', 'type') from None
        declared_mode = _option(run, node, env, 'mode')
        declared_sources = _option(run, node, env, 'sources')
        sources = [S.show(x) for x in declared_sources] if isinstance(declared_sources, (tuple, list, frozenset)) \
            else [cap]
        evidence = {'version': VERSION, 'mechanism': 'observation' if kind == 'observe' else 'effect',
                    'capability': cap, 'effect_id': eid, 'args_sha256': outcome.get('args_sha256'),
                    'result_sha256': outcome.get('result_sha256'), 'acquired_at': outcome.get('at'),
                    'trusted_acquisition': True, 'replayed': replayed,
                    'declaration': {'mode': S.show(declared_mode) if declared_mode not in (None, '') else
                                    f'capability:{spec["family"]}',
                                    'sources': sorted(set(sources)),
                                    'origin': 'author_declared' if declared_mode not in (None, '') else 'catalogue'},
                    'untrusted': spec['untrusted'], 'sensitivity': spec['sensitivity'],
                    'independence': 'not_established'}
        weight = run._weight(node.options['weight'], env) if 'weight' in node.options else 1
        b = run._bind(env, node.name, value, ty, node, OBSERVED if kind == 'observe' else EFFECT, weight,
                      meta={'evidence': evidence, 'capability': cap, 'effect_id': eid, 'replayed': replayed})
        run._trace(node, 'ok', binding=b, note=said, ms=int((time.time() - t0) * 1000))
    return execute


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register() -> None:
    """Add `observe` and `act` to the language. Safe to call again."""
    for kind, klass in (('observe', OBSERVED), ('act', EFFECT)):
        if kind in S.EXTENSIONS and getattr(S.EXTENSIONS[kind], 'origin', '') == __name__:
            continue
        ext = S.Extension(kind, _parse(kind), _execute(kind), reads=_reads, binds=_binds, label=_label, klass=klass)
        ext.looks = _LOOKS.match
        ext.origin = __name__
        ext.self_gating = True              # this module decides when a statement may reach the world
        ext.check = lambda node, scope: check_node(node, scope)
        ext.check_program = _program_hook(kind)
        S.register_extension(ext)


register()
