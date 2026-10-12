"""Symblic's abstraction layer: functions, routines, modules (with a standard library) and tests.

Symblic evaluates formal statements in a kernel and dispatches typed interpretation steps to model
applicators. This module adds reusable declarations and tests to the language; a type or a passing test does
not prove that an implementation satisfies every intended natural-language requirement:

    function area(side: Number) -> Number = side ^ 2.               # pure: the kernel decides it

    routine colour_of(thing: Text) -> one of {red, green, blue} do  # a typed model function with a contract
        ask c: one of {red, green, blue} "What colour is {thing}?" with effort=high
        ensure c != blue else retry.
        return c.
    end.

    import units.                                                    # symblic/lang/library/units.sym, unqualified
    import stats as st.                                              # st.variance(...) (qualified)
    import c_to_f, f_to_c from units.                                # just these names
    import "My saved program" as mine.                               # a saved program (only with a host's store)

    test "a unit square has area 1" do
        assert area(1) = 1.
    end.

The standard library is the folder library/ next to this file: constants, dates, graphs, kinship, lab,
order, records, stats, text and units (`python3 -m symblic.lang.abstraction lib` lists them).

Semantics (docs/reference/LANGUAGE-3.md):
- A function is one kernel expression. Its parameters and result are type-checked, it may recurse (at most
  MAX_CALL_DEPTH calls deep). In verified mode it cannot call routines or external adapters, including
  through other functions. Legacy mode retains the historical function-to-routine bridge.
- A routine is a block of statements run in a fresh scope per call. Its asks go through the normal
  capsule, consensus, replay and ensure/retry path. `return EXPR.` ends it. Options after `with` are the
  defaults for the asks inside it. Within one run a routine is a function: the same arguments (and the same
  defaults) return the recorded value without asking again.
- A module is a Symblic program that only declares (function, routine, define, term, let, fact, rule,
  import, test, assert). It cannot see the importing program; its source and SHA-256 are recorded in the
  run folder (modules.json), so a resumed or replayed run uses exactly the module it started with.
- Verified-profile modules isolate Datalog relations under a source/module-key namespace. Public callers
  use ordinary helpers such as `function edges() = query edge(X, Y).` Qualified helper calls work as usual.
  Within another isolated module, `import "Edges" as e` explicitly binds `e.edge` for query/rule bodies;
  `import edge from "Edges"` binds that relation read-only and re-exports it. Imported predicates cannot
  also be defined locally. Raw caller/global predicates are never inferred as module inputs. Libraries
  intentionally consuming global facts (kinship/graphs) remain usable through legacy mode, or the explicit
  host option `module_logic={"lib:kinship": "shared"}`. Mode and imported relation identities are replay-pinned.
- Tests are skipped in a normal run; run_tests() (or `python3 -m symblic.lang.abstraction test FILE`) runs each
  one in its own scope after the program's declarations, with whatever applicators are given (fakes in tests).
- certify runs a module's tests once per cohort of applicators and can seal the outcome as a certificate
  (symblic.kernel.certificates); crystallise compiles a routine's agreed answers over a finite domain into a
  plain kernel function. Both call models: they need configured applicators (symblic.providers.applicators).

    python3 -m symblic.lang.abstraction test FILE|MODULE [--by APP] | certify MODULE --cohort A --cohort B
                                         | crystallise FILE --routine NAME --domain JSON --by APP | lib | doc NAME

The statements are registered as core extensions (symblic.kernel.language.register_extension) when
symblic.kernel.language is imported; the core interpreter is not edited here. Nothing runs on import except
that registration.

Depends on: symblic.kernel.language, symblic.kernel.evidence, symblic.kernel.run (to run tests and jobs),
symblic.providers.applicators (only for model-backed commands).
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import os
import re
import sys
import threading
import time

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import evidence as E  # noqa: E402

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library')   # the standard library (*.sym)
MAX_CALL_DEPTH = 32           # nested function/routine calls (recursion included)
MAX_MODULES = 40              # modules loaded by one run (nested imports included)
MAX_PARAMS = 16
MODULE_LOGIC_VERSION = 1       # namespaced predicates and recorded logic-policy compatibility
MODULE_NAME_RX = re.compile(r'^[a-z][a-z0-9_]{0,40}$')
SAVED_NAME_RX = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$')
MODULE_KINDS = ('program', 'note', 'section', 'define', 'term', 'let', 'fact', 'rule', 'function', 'routine',
                'import', 'test', 'assert', 'expect', 'ensure')
DECLARATIONS = ('program', 'note', 'section', 'use', 'define', 'term', 'fact', 'rule', 'group', 'function',
                'routine', 'import', 'let', 'given')


class _Return(Exception):
    """`return` inside a routine: unwinds the routine's block (and any if/for inside it) with the value."""

    def __init__(self, value):
        super().__init__('return')
        self.value = value


# ---------------------------------------------------------------------------
# Per-run state (attached to the Run lazily; the core Run knows nothing about it)
# ---------------------------------------------------------------------------

class LangState:
    def __init__(self, run):
        self.run = run
        self.main = threading.current_thread()
        self.local = threading.local()          # call depth per thread
        self.lock = threading.Lock()
        self.memo: dict = {}                    # (routine uid, args fingerprint, defaults) -> value
        self.callables: dict = {}               # registered name -> Callable
        self.scopes: dict = {}                  # registered name -> the Env it was registered in
        self.modules: dict = {}                 # module key -> Module
        self.loading: list = []                 # module keys being loaded (cycle detection)
        self.recorded = _read_recorded(run)     # module key -> {'source', 'sha256', ...} from the run folder
        self.tests: list = []                   # test results (TestRun)
        self.calls = 0
        self.declarations = 0                 # stable per-run lexical declaration identity, never id(env)
        self.taint = 'exact'                    # worst determinism class reached by routine calls

    @property
    def depth(self) -> int:
        return getattr(self.local, 'depth', 0)

    @depth.setter
    def depth(self, v: int) -> None:
        self.local.depth = v


def state(run) -> LangState:
    st = run.__dict__.get('_lang')
    if st is None:
        st = run.__dict__['_lang'] = LangState(run)
    return st


def snapshot_state(run) -> dict:
    """Transactional extension state at an ask anchor. Recorded module sources remain replay inputs."""
    st = state(run)
    with st.lock:
        return {'memo': dict(st.memo), 'callables': dict(st.callables), 'scopes': dict(st.scopes),
                'modules': dict(st.modules), 'loading': list(st.loading), 'tests': list(st.tests),
                'calls': st.calls, 'declarations': st.declarations, 'taint': st.taint,
                'functions': dict(run.kernel.functions), 'klass': getattr(run.kernel, 'klass', 'exact')}


def restore_state(run, snapshot: dict) -> None:
    """Forget definitions and memo results caused by a rejected answer, including their registrations.

    Module source records are retained, like model-call replay records: a retry must reuse the same
    source even if the external library has changed. Loaded module objects themselves are rolled back.
    """
    st = state(run)
    with st.lock:
        for name in ('memo', 'callables', 'scopes', 'modules'):
            current = getattr(st, name)
            current.clear()
            current.update(snapshot[name])
        for name in ('loading', 'tests'):
            getattr(st, name)[:] = snapshot[name]
        for name in ('calls', 'declarations', 'taint'):
            setattr(st, name, snapshot[name])
        run.kernel.functions.clear()
        run.kernel.functions.update(snapshot['functions'])
        run.kernel.klass = snapshot['klass']


def _read_recorded(run) -> dict:
    folder = getattr(getattr(run, 'store', None), 'dir', None)
    if not folder:
        return {}
    try:
        with open(os.path.join(folder, 'modules.json'), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _params(p: S.Parser) -> list:
    """(name[: Type][= default], ...) -> [{'name', 'type', 'default'}]."""
    p.expect_op('(')
    out = []
    while not p.op(')'):
        name = p.expect_name('a parameter name').value
        if any(x['name'] == name for x in out):
            raise p.err(f'the parameter {name} is listed twice')
        ty = default = None
        if p.op(':'):
            p.take()
            ty = p.type_expr()
        if p.op('='):
            p.take()
            default = p.expr()
        elif any(x['default'] is not None for x in out):
            raise p.err(f'{name} needs a default: it follows a parameter that has one')
        out.append({'name': name, 'type': ty, 'default': default})
        if len(out) > MAX_PARAMS:
            raise p.err(f'more than {MAX_PARAMS} parameters')
        if not p.op(','):
            break
        p.take()
    p.expect_op(')')
    return out


def _callable_name(p: S.Parser, what: str) -> str:
    t = p.expect_name(f'a {what} name')
    if t.value in S.BUILTINS:
        raise S.SymblicError(f'{t.value} is a builtin function; pick another name', t.line, t.col, 'name')
    return t.value


def parse_function(p: S.Parser, line: int, col: int, prog: dict) -> S.Node:
    name = _callable_name(p, 'function')
    params = _params(p)
    ret = None
    if p.op('->'):
        p.take()
        ret = p.type_expr()
    if not p.op('='):
        raise p.err("expected '=' and the function's expression: function f(x) = x * 2.")
    p.take()
    body = p.expr()
    p.finish()
    return S.Node('function', line, col, name=name, params=[x['name'] for x in params], specs=params, ret=ret,
                  value=body)


def parse_routine(p: S.Parser, line: int, col: int, prog: dict) -> S.Node:
    name = _callable_name(p, 'routine')
    params = _params(p)
    ret = None
    if p.op('->'):
        p.take()
        ret = p.type_expr()
    options = {}
    if p.word('with'):
        p.take()
        while not p.done() and not p.word('do'):
            key_tok = p.expect_name('an option name')
            key = key_tok.value.lower()
            if key not in S.USE_OPTIONS or key in ('max_asks', 'side_effects'):
                raise S.SymblicError(f'a routine cannot set {key!r}', key_tok.line, key_tok.col, 'syntax')
            p.expect_op('=', ':')
            options[key] = p.expr()
            if p.op(','):
                p.take()
    if p.word('do'):
        p.take()
    p.finish()
    return S.Node('routine', line, col, name=name, params=[x['name'] for x in params], specs=params, ret=ret,
                  options=options)


def parse_import(p: S.Parser, line: int, col: int, prog: dict) -> S.Node:
    names = None
    saved = False
    if p.at('str'):
        module = p.take().value.strip()
        saved = True
        if not SAVED_NAME_RX.match(module):
            raise S.SymblicError('a saved program name is letters, numbers and spaces', line, col, 'syntax')
    else:
        first = [p.expect_name('a module name').value]
        while p.op(','):
            p.take()
            first.append(p.expect_name('a name').value)
        if p.word('from'):
            p.take()
            names = first
            if p.at('str'):
                module = p.take().value.strip()
                saved = True
            else:
                module = p.expect_name('a module name').value
        elif len(first) == 1:
            module = first[0]
        else:
            raise p.err("expected 'from MODULE' after the names")
    alias = None
    if p.word('as'):
        p.take()
        alias = p.expect_name('a name for the module').value
        if names is not None:
            raise S.SymblicError('import NAMES from MODULE takes no alias', line, col, 'syntax')
    p.finish()
    if not saved and not MODULE_NAME_RX.match(module):
        raise S.SymblicError(f'{module!r} is not a library module name (lower case, digits, _)', line, col, 'syntax')
    return S.Node('import', line, col, module=module, saved=saved, alias=alias, names=names)


def parse_test(p: S.Parser, line: int, col: int, prog: dict) -> S.Node:
    if p.at('str'):
        title = p.take().value.strip()
    else:
        title = p.expect_name('a test name in quotes').value
    if p.word('do'):
        p.take()
    p.finish()
    if not title:
        raise S.SymblicError('a test needs a name: test "what it shows" do ... end.', line, col, 'syntax')
    return S.Node('test', line, col, title=title[:200])


# ---------------------------------------------------------------------------
# Callables: functions and routines
# ---------------------------------------------------------------------------

class Callable:
    """A function or routine, defined in `env` (its lexical scope). `uid` is unique per definition."""

    def __init__(self, kind: str, node: S.Node, env: S.Env, qualname: str, declaration: int = 0):
        self.kind, self.node, self.env, self.qualname = kind, node, env, qualname
        self.uid = f'{qualname}@{node.line}#{declaration}'
        self.body = None                         # routine: the body with returns rewritten

    def signature(self) -> str:
        ps = []
        for spec in self.node.specs:
            t = f': {S.type_label(spec["type"])}' if spec['type'] else ''
            d = f' = {_src_text(spec["default"])}' if spec['default'] is not None else ''
            ps.append(f'{spec["name"]}{t}{d}')
        ret = f' -> {S.type_label(self.node.ret)}' if self.node.ret else ''
        return f'{self.kind} {self.qualname}({", ".join(ps)}){ret}'


def _bind_args(run, fn: Callable, args, kwargs, node: S.Node) -> list:
    specs = fn.node.specs
    if len(args) > len(specs):
        raise S.SymblicError(f'{fn.qualname} takes {len(specs)} argument(s), got {len(args)}', node.line, node.col,
                             'type')
    values = {}
    for spec, v in zip(specs, args):      # noqa: B905  (len(args) <= len(specs) was checked above)
        values[spec['name']] = v
    for key, v in kwargs.items():
        if not any(s['name'] == key for s in specs):
            raise S.SymblicError(f'{fn.qualname} has no parameter {key}', node.line, node.col, 'name')
        if key in values:
            raise S.SymblicError(f'{fn.qualname}: {key} is given twice', node.line, node.col, 'type')
        values[key] = v
    out = []
    for spec in specs:
        name = spec['name']
        if name not in values:
            if spec['default'] is None:
                raise S.SymblicError(f'{fn.qualname} needs {name}', node.line, node.col, 'type')
            values[name] = run.kernel.eval(spec['default'], fn.env)
        v = values[name]
        ty = None
        if spec['type'] is not None:
            ty = S.resolve_type(spec['type'], run.types, node.line)
            try:
                v = S.check_value(v, ty, name)
            except S.SymblicError as e:
                raise S.SymblicError(f'{fn.qualname}: {e.message}', node.line, node.col, 'type') from None
        out.append((name, v, ty))
    return out


def _check_result(run, fn: Callable, value, node: S.Node):
    if fn.node.ret is None:
        return value
    ty = S.resolve_type(fn.node.ret, run.types, fn.node.line)
    try:
        return S.check_value(value, ty, f'the result of {fn.qualname}')
    except S.SymblicError as e:
        raise S.SymblicError(e.message, node.line, node.col, 'type') from None


def _enter(st: LangState, fn: Callable, node: S.Node) -> None:
    if st.depth >= MAX_CALL_DEPTH:
        raise S.SymblicError(f'calls nest deeper than {MAX_CALL_DEPTH} (unbounded recursion in {fn.qualname}?)',
                             node.line, node.col)
    st.depth += 1


def _invoke(run, fn: Callable, node: S.Node, args, kwargs):
    st = state(run)
    if fn.kind == 'routine' and getattr(st.local, 'pure_depth', 0):
        raise S.SymblicError(f'pure function cannot invoke routine {fn.qualname}', node.line, node.col, 'effect')
    if fn.kind == 'function':
        pure = getattr(run, 'execution_profile', 'legacy') == 'verified'
        st.local.pure_depth = getattr(st.local, 'pure_depth', 0) + int(pure)
        entered = False
        try:
            # Kernel._call refuses external code adapters (S.SPECULATION_DENIED) inside a verified
            # function's defaults and body, through helpers and module aliases alike.
            with S.pure_scope(pure):
                bound = _bind_args(run, fn, args, kwargs, node)
                _enter(st, fn, node)
                entered = True
                child = S.Env(fn.env)
                for name, v, ty in bound:
                    # Argument reads already belong to the calling statement.
                    child.vars[name] = S.Binding(name, v, ty, stmt=f'L{fn.node.line}', line=fn.node.line,
                                                meta={'_epistemic_element': True})
                try:
                    value = run.kernel.eval(fn.node.value, child)
                except RecursionError:
                    raise S.SymblicError(f'{fn.qualname} recursed too deeply', node.line, node.col) from None
        finally:
            st.depth -= int(entered)
            st.local.pure_depth -= int(pure)
        return _check_result(run, fn, value, node)
    return _call_routine(run, st, fn, node, args, kwargs)


def _call_routine(run, st: LangState, fn: Callable, node: S.Node, args, kwargs):
    if threading.current_thread() is not st.main:
        raise S.SymblicError(f'{fn.qualname} is a routine: call it in its own statement (let x = '
                             f'{fn.node.name}(...).), not inside an ask', node.line, node.col)
    bound = _bind_args(run, fn, args, kwargs, node)
    defaults = json.dumps({k: S.to_plain(v) if not isinstance(v, str) else v for k, v in sorted(run.defaults.items())},
                          sort_keys=True, default=str)
    key = (fn.uid, S.canon_json(tuple(v for _n, v, _t in bound)), defaults)
    with st.lock:
        recorded = st.memo.get(key)
    if recorded is not None:
        value, klass, dependencies = recorded
        run._trace(S.Node('call', node.line, node.col), 'ok',
                   note=f'{fn.qualname}({_args_text(bound)}) = {S.show(value, 160)} (same call, recorded) '
                        f'[{klass}]', dependencies=dependencies)
        _taint(run, st, klass)
        return value
    _enter(st, fn, node)
    saved_defaults = dict(run.defaults)
    outer_klass = getattr(run.kernel, 'klass', 'exact')    # statements inside the body reset it
    first_row = len(run.trace)
    try:
        for k, v in fn.node.options.items():
            run.defaults[k] = run._opt_value(k, v, fn.env)
        child = S.Env(fn.env)
        # Explicit parameter context is derived from the original caller reads;
        # a literal argument introduces no external premise of its own.
        basis = tuple(run._read_bindings()) if hasattr(run, '_read_bindings') else ()
        for name, v, ty in bound:
            child.vars[name] = S.Binding(name, v, ty, weight=3, stmt=f'L{fn.node.line}', line=fn.node.line,
                                        meta={'_epistemic_element': True, '_epistemic_basis': basis,
                                              '_epistemic_derivation': 'routine argument'})
        try:
            run.exec_block(fn.body, child)
        except _Return as r:
            value = r.value
        else:
            raise S.SymblicError(f'routine {fn.qualname} ended without return', node.line, node.col)
    finally:
        run.defaults.clear()
        run.defaults.update(saved_defaults)
        st.depth -= 1
    value = _check_result(run, fn, value, node)
    klass = 'exact'
    for row in run.trace[first_row:]:
        if row.get('class'):
            klass = S_worse(klass, row['class'])
    dependencies = _ask_dependencies(run.trace[first_row:])
    for dependency in dependencies:
        klass = S_worse(klass, dependency.get('class', 'open'))
    with st.lock:
        st.memo[key] = (value, klass, dependencies)
        st.calls += 1
    run.kernel.klass = outer_klass
    _taint(run, st, klass)
    run._trace(S.Node('call', node.line, node.col), 'ok',
               note=f'{fn.qualname}({_args_text(bound)}) = {S.show(value, 160)} [{klass}]',
               dependencies=dependencies)
    return value


def _ask_dependencies(rows) -> list:
    """References to original ask events, deduplicated across derived/memoized calls.

    These are dependencies, not new observations: cached computation cannot improve agreement or
    create another independent view of the phenomenon.
    """
    found = {}
    for row in rows:
        if row.get('kind') == 'ask' and row.get('ask') is not None:
            sequence = row['sequence']
            agreement = row['ask'].get('agreement')
            found[sequence] = {'sequence': sequence, 'agreement': agreement,
                               'kind': 'ask_reference', 'line': row.get('line'),
                               'class': row.get('class', 'open'),
                               **({'contested': True} if row['ask'].get('contested') else {})}
        for dep in row.get('dependencies') or []:
            found.setdefault(dep['sequence'], dict(dep))
    return [found[sequence] for sequence in sorted(found)]


def _taint(run, st: LangState, klass: str) -> None:
    """The statement being evaluated now depends on a model: its binding's class is at least `klass`."""
    st.taint = S_worse(st.taint, klass)
    run.kernel.klass = S_worse(getattr(run.kernel, 'klass', 'exact'), klass)


def _args_text(bound) -> str:
    return ', '.join(S.show(v, 60) for _n, v, _t in bound)


def S_worse(a: str, b: str) -> str:
    order = ['exact', 'closed', 'structured', 'open', 'observed', 'effect']
    return a if order.index(a if a in order else 'open') >= order.index(b if b in order else 'open') else b


def _rewrite_returns(stmts: list) -> list:
    """The routine body with every `return` (in if/for blocks too) turned into a routine return. Other
    routines' bodies are left alone: a nested routine definition has its own returns."""
    for s in stmts:
        if s.k == 'return':
            s.k = 'routine-return'
        elif s.k == 'if':
            for _c, body in s.branches:
                _rewrite_returns(body)
            if s.else_body:
                _rewrite_returns(s.else_body)
        elif s.k == 'for':
            _rewrite_returns(s.body)
    return stmts


def _register(run, name: str, fn: Callable, node: S.Node, scope: S.Env | None = None) -> None:
    """Make `name` callable. `scope` is where the name is visible from (the definition's or the importing
    statement's scope); a name still in scope cannot be defined again, a sibling scope's can."""
    st = state(run)
    scope = scope if scope is not None else fn.env
    if name in S.BUILTINS:
        raise S.SymblicError(f'{name} is a builtin function; pick another name', node.line, node.col, 'name')
    old = st.callables.get(name)
    if old is not None and old is not fn and _encloses(st.scopes.get(name, old.env), scope):
        where = f'line {old.node.line}' if old.qualname == name else f'imported as {old.qualname}'
        raise S.SymblicError(f'{name} is already defined ({where}); names are defined once', node.line,
                             node.col, 'name')
    st.callables[name] = fn
    st.scopes[name] = scope

    def call(kernel, cnode, *args, **kwargs):
        return _invoke(run, fn, cnode, args, kwargs)
    run.kernel.functions[name] = call


def _encloses(outer: S.Env, inner: S.Env) -> bool:
    """True when `outer` is `inner` or one of its parents: a definition there is still in scope, so the
    same name cannot be defined again. Sibling scopes (two tests, two calls of one routine) may reuse it."""
    e = inner
    while e is not None:
        if e is outer:
            return True
        e = e.parent
    return False


def define(run, node: S.Node, env: S.Env, qualname: str | None = None) -> Callable:
    st = state(run)
    with st.lock:
        st.declarations += 1
        declaration = st.declarations
    fn = Callable(node.k, node, env, qualname or node.name, declaration)
    if node.k == 'routine':
        fn.body = _rewrite_returns(node.body)
    return fn


def exec_function(run, node, env):
    fn = define(run, node, env)
    _register(run, node.name, fn, node)
    run._trace(node, 'ok', note=fn.signature())


def exec_routine(run, node, env):
    fn = define(run, node, env)
    _register(run, node.name, fn, node)
    run._trace(node, 'ok', note=fn.signature())


def exec_return(run, node, env):
    value = run.kernel.eval(node.value, env)
    run._trace(node, 'ok', note=f'return {S.show(value, 160)}')
    raise _Return(value)


def exec_test(run, node, env):
    run._trace(node, 'skipped', note=f'test "{node.title}" (run the tests to check it)')


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

class Module:
    def __init__(self, key: str, modid: str, source: str, origin: str, logic_mode='shared'):
        self.key, self.modid, self.source, self.origin = key, modid, source, origin
        self.sha256 = hashlib.sha256(source.encode('utf-8')).hexdigest()
        self.logic_mode = logic_mode
        identity = json.dumps([MODULE_LOGIC_VERSION, key, self.sha256], separators=(',', ':'))
        self.logic_namespace = ('__symmod_' + hashlib.sha256(identity.encode()).hexdigest()) if logic_mode == 'isolated' else ''
        if self.logic_namespace:
            # Saved titles can normalize to the same _modid ("A B" and "A-B").
            # Isolated helper/type names must share the immutable module identity.
            self.modid = modid + self.logic_namespace
        self.predicates: dict = {}     # lexical predicate name -> canonical relation
        self.logic_imports: dict = {}  # explicitly imported predicate references, read-only
        self.env = S.Env()
        self.callables: dict = {}      # local name -> canonical name
        self.types: dict = {}          # local name -> canonical name
        self.constants: dict = {}      # local name -> Binding (exported unless it starts with _)
        self.terms: list = []
        self.tests: list = []
        self.notes: list = []
        self.title = modid

    def exports(self) -> dict:
        pub = lambda n: not n.startswith('_')   # noqa: E731
        return {'callables': {n: c for n, c in self.callables.items() if pub(n)},
                'types': {n: c for n, c in self.types.items() if pub(n)},
                'constants': {n: b for n, b in self.constants.items() if pub(n)},
                'predicates': {n: c for n, c in self.predicates.items() if pub(n) and '.' not in n}}

    def logic_identity(self):
        return {'version': MODULE_LOGIC_VERSION, 'mode': self.logic_mode,
                'namespace': self.logic_namespace, 'imports': dict(sorted(self.logic_imports.items()))}


def _logic_mode(run, key, node):
    policy = run.opts.get('module_logic', {})
    if (not isinstance(policy, dict) or any(not isinstance(k, str) or not k.startswith(('lib:', 'saved:'))
            or v not in ('shared', 'isolated') for k, v in policy.items())):
        raise S.SymblicError('module_logic must map exact lib:NAME or saved:NAME keys to shared/isolated',
                             node.line, node.col, 'type')
    return policy.get(key, 'isolated' if getattr(run, 'execution_profile', 'legacy') == 'verified' else 'shared')


def _logic_nodes(value):
    """Walk executed declarations/bodies; a skipped test cannot declare a live input relation."""
    if isinstance(value, S.Node):
        if value.k == 'test':
            return
        yield value
        for child in vars(value).values():
            yield from _logic_nodes(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from _logic_nodes(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from _logic_nodes(child)


def _logic_symbols(stmts):
    owned, reads, arities = set(), set(), {}
    for node in _logic_nodes(stmts):
        pairs = node.atoms if node.k == 'fact' else [(node.pred, node.args)] if node.k in ('rule', 'query', 'lit_pos', 'lit_neg') else []
        for name, args in pairs:
            arities.setdefault(name, set()).add(len(args))
            (owned if node.k in ('fact', 'rule') else reads).add(name)
    return owned, reads, arities


def saved_source(name: str):
    """A saved program's source by exact name, or None. Saved programs live in the host's program store
    (integration/host/symblic_engine.py); without that host there are none. Replaced in tests."""
    try:
        from integration.host import symblic_engine as E
        for item in E.load_programs():
            if item.get('name') == name:
                return item.get('source')
    except Exception:  # noqa: BLE001  (no engine store: no saved programs)
        return None
    return None


def library_source(name: str):
    if not MODULE_NAME_RX.match(name):
        return None
    path = os.path.join(LIB_DIR, name + '.sym')
    try:
        with open(path, encoding='utf-8') as f:
            return f.read(S.MAX_SOURCE + 1)
    except OSError:
        return None


def _resolve(run, module: str, saved: bool, node: S.Node):
    key = ('saved:' if saved else 'lib:') + module
    if 'execution_pins' in run.opts:
        pins = getattr(run, '_execution_pins', None)
        row = pins.get('libraries', {}).get(module) if isinstance(pins, dict) else None
        if saved or not isinstance(row, dict):
            raise S.SymblicError('execution pins refuse saved or uncaptured module imports',
                                 node.line, node.col, 'version')
        return key, row['source'], 'execution snapshot symblic/lang/library/' + module + '.sym'
    st = state(run)
    rec = st.recorded.get(key)
    if isinstance(rec, dict) and isinstance(rec.get('source'), str):
        return key, rec['source'], rec.get('origin') or key
    source = saved_source(module) if saved else library_source(module)
    if source is None:
        where = 'saved programs' if saved else f'the library (symblic/lang/library/{module}.sym)'
        raise S.SymblicError(f'no module {module!r} in {where}', node.line, node.col, 'name')
    if len(source) > S.MAX_SOURCE:
        raise S.SymblicError(f'module {module} is too long', node.line, node.col)
    return key, source, (f'saved program "{module}"' if saved else f'symblic/lang/library/{module}.sym')


def _modid(module: str, saved: bool) -> str:
    return re.sub(r'\W+', '_', module).strip('_').lower() if saved else module


def load_module(run, module: str, saved: bool, node: S.Node) -> Module:
    st = state(run)
    key, source, origin = _resolve(run, module, saved, node)
    mode = _logic_mode(run, key, node)
    if key in st.modules:
        if st.modules[key].logic_mode != mode:
            raise S.SymblicError('module logic policy changed after loading ' + key, node.line, node.col, 'version')
        return st.modules[key]
    if key in st.loading:
        raise S.SymblicError(f'modules import each other in a cycle: {" -> ".join(st.loading + [key])}', node.line,
                             node.col, 'name')
    if len(st.modules) + len(st.loading) >= MAX_MODULES:
        raise S.SymblicError(f'more than {MAX_MODULES} modules', node.line, node.col)
    st.loading.append(key)
    try:
        mod = Module(key, _modid(module, saved), source, origin, mode)
        recorded = st.recorded.get(key)
        # A validated execution snapshot is authoritative over unrelated stale
        # folder records. For matching source bytes, semantic-mode pins still apply.
        if (isinstance(getattr(run, '_execution_pins', None), dict) and isinstance(recorded, dict)
                and recorded.get('sha256') != mod.sha256):
            recorded = None
        if isinstance(recorded, dict):
            if recorded.get('sha256') != mod.sha256:
                raise S.SymblicError('recorded module source hash changed: ' + key, node.line, node.col, 'version')
            previous = recorded.get('logic')
            # Historical records had only shared predicates. They may replay in
            # legacy shared mode, never silently acquire isolated semantics.
            if previous is None and mode != 'shared':
                raise S.SymblicError('historical shared module cannot replay as isolated: ' + key,
                                     node.line, node.col, 'version')
            if previous is not None and (not isinstance(previous, dict) or any(
                    previous.get(k) != mod.logic_identity()[k] for k in ('version', 'mode', 'namespace'))):
                raise S.SymblicError('recorded module logic identity changed: ' + key, node.line, node.col, 'version')
        try:
            prog = S.parse(source, execution_profile=getattr(run, 'execution_profile', 'legacy'))
        except S.SymblicError as e:
            raise S.SymblicError(f'module {module}, line {e.line}: {e.message}', node.line, node.col, e.kind) from None
        mod.title = prog.get('name') or mod.modid
        pure = getattr(run, 'execution_profile', 'legacy') == 'verified'
        old_loading = getattr(run.kernel, 'module_loading', False)
        st.local.pure_depth = getattr(st.local, 'pure_depth', 0) + int(pure)
        run.kernel.module_loading = old_loading or pure
        try:
            _declare_module(run, mod, prog['statements'], node)
        finally:
            st.local.pure_depth -= int(pure)
            run.kernel.module_loading = old_loading
        if isinstance(recorded, dict) and recorded.get('logic') is not None and recorded['logic'] != mod.logic_identity():
            raise S.SymblicError('recorded module predicate imports changed: ' + key, node.line, node.col, 'version')
    finally:
        st.loading.remove(key)
    st.modules[key] = mod
    _record(run, mod)
    return mod


def _record(run, mod: Module) -> None:
    st = state(run)
    identity = mod.logic_identity()
    if st.recorded.get(mod.key, {}).get('sha256') == mod.sha256 and st.recorded.get(mod.key, {}).get('logic') == identity:
        return
    st.recorded[mod.key] = {'origin': mod.origin, 'sha256': mod.sha256, 'source': mod.source, 'title': mod.title,
                          'logic': identity}
    run.store.save('modules.json', st.recorded)


def _rewrite(obj, calls: dict, types: dict, predicates=None) -> None:
    """Rename calls, types and every syntactic predicate occurrence in place."""
    predicates = predicates or {}
    if isinstance(obj, (list, tuple)):
        for x in obj:
            _rewrite(x, calls, types, predicates)
    elif isinstance(obj, dict):
        if obj.get('k') == 'named' and obj.get('name') in types:
            obj['name'] = types[obj['name']]
        for v in obj.values():
            _rewrite(v, calls, types, predicates)
    elif isinstance(obj, S.Node):
        if obj.k == 'call' and obj.fn in calls:
            obj.fn = calls[obj.fn]
        if obj.k in ('rule', 'query', 'lit_pos', 'lit_neg'):
            obj.pred = predicates.get(obj.pred, obj.pred)
        elif obj.k == 'fact':
            obj.atoms = [(predicates.get(pred, pred), args) for pred, args in obj.atoms]
        for key, v in obj.__dict__.items():
            if key not in ('k', 'line', 'col'):
                _rewrite(v, calls, types, predicates)


def _module_lineage(run, mod, binding, statement, parents, origin):
    """Host-recorded source premises/derivations, never evidence of source truth."""
    logic = mod.logic_identity()
    bounded_logic = {key: logic[key] for key in ('version', 'mode', 'namespace')}
    bounded_logic.update(imports_sha256=E.digest(logic['imports']), imports_count=len(logic['imports']))
    module = {'key': mod.key, 'source_sha256': mod.sha256, 'logic': bounded_logic,
              'line': statement.line, 'kind': statement.k}
    binding.meta['_epistemic_module'] = module
    if statement.k in ('fact', 'rule'):
        binding.meta['_epistemic_predicates'] = tuple(sorted(
            {p for p, _args in statement.atoms} if statement.k == 'fact' else {statement.pred}))
    binding.meta['evidence'] = {'module': module, 'mechanism': 'module_declaration',
                                'empirical_truth': 'not_established'}
    run._claim_for_binding(binding, parents=parents, origin=origin,
                           derivation=E.syntax(statement) if origin == 'derived' else None)
    return binding


def _declare_module(run, mod: Module, stmts: list, at: S.Node) -> None:
    where = lambda s: f'module {mod.modid}, line {s.line}'   # noqa: E731
    # 1. what the module defines and imports, so its own references can be renamed before anything runs
    calls, types, imported_predicates = {}, {}, {}
    owned, reads, arities = _logic_symbols(stmts)
    for s in stmts:
        if s.k not in MODULE_KINDS:
            raise S.SymblicError(f'{where(s)}: a module only declares (function, routine, define, term, let, fact, '
                                 f'rule, import, test, assert), not {s.k}', at.line, at.col, 'syntax')
        if s.k in ('function', 'routine'):
            if s.name in calls:
                raise S.SymblicError(f'{where(s)}: {s.name} is defined twice', at.line, at.col, 'name')
            calls[s.name] = f'{mod.modid}.{s.name}'
        elif s.k == 'define':
            types[s.name] = f'{mod.modid}.{s.name}'
        elif s.k == 'import':
            sub = load_module(run, s.module, s.saved, at)
            ex = sub.exports()
            if mod.logic_mode == 'isolated':
                if s.names is not None:
                    available = set().union(*(set(ex[k]) for k in ('callables', 'types', 'constants', 'predicates')))
                    if any(name not in available for name in s.names):
                        raise S.SymblicError(f'{where(s)}: imported module has no requested declaration',
                                             at.line, at.col, 'name')
                for name, canonical in ex['predicates'].items():
                    if s.names is not None and name not in s.names:
                        continue
                    local = f'{s.alias}.{name}' if s.alias else name
                    if local in owned or (local in imported_predicates and imported_predicates[local] != canonical):
                        raise S.SymblicError(f'{where(s)}: predicate {local} has multiple owners; imported predicates '
                                             'are read-only, use an import alias and a distinct local relation',
                                             at.line, at.col, 'name')
                    imported_predicates[local] = canonical
                    mod.logic_imports[local] = {'module': sub.key, 'predicate': canonical}
            if s.alias:
                for n, c in ex['callables'].items():
                    calls[f'{s.alias}.{n}'] = c
                for n, c in ex['types'].items():
                    types[f'{s.alias}.{n}'] = c
            else:
                wanted = s.names
                for n, c in ex['callables'].items():
                    if wanted is None or n in wanted:
                        calls[n] = c
                for n, c in ex['types'].items():
                    if wanted is None or n in wanted:
                        types[n] = c
    if mod.logic_mode == 'isolated':
        unresolved = sorted(reads - owned - imported_predicates.keys())
        if unresolved:
            raise S.SymblicError(f'module {mod.title}: undeclared external predicates {", ".join(unresolved)}; '
                                 'import their defining module/relations explicitly, expose a relation helper, or '
                                 f'choose module_logic["{mod.key}"]="shared" for intentional global composition',
                                 at.line, at.col, 'name')
        bad_arity = sorted(name for name, sizes in arities.items() if len(sizes) > 1)
        if bad_arity:
            raise S.SymblicError('isolated predicates require one arity: ' + ', '.join(bad_arity),
                                 at.line, at.col, 'type')
        mod.predicates = {name: f'{mod.logic_namespace}__{name}' for name in owned}
        mod.predicates.update(imported_predicates)
    else:
        mod.predicates = {name: name for name in owned}
    _rewrite(stmts, calls, types, mod.predicates)
    mod.callables = {n: c for n, c in calls.items() if '.' not in n and c.startswith(mod.modid + '.')}
    mod.types = {n: c for n, c in types.items() if c.startswith(mod.modid + '.')}
    # 2. declare, in order
    st = state(run)
    for s in stmts:
        k = s.k
        if k in ('program', 'section'):
            continue
        if k == 'note':
            mod.notes.append((s.line, s.text))
        elif k == 'define':
            run.types[types[s.name]] = s.type
            S.resolve_type(s.type, run.types, s.line)
        elif k == 'term':
            _merge_term(run, s.term, s.definition, f'module {mod.modid}', at)
            mod.terms.append((s.term, s.definition))
        elif k == 'fact':
            with S.capture_binding_reads(run, run._read_bindings(), scope=True) as reads:
                for pred, args in s.atoms:
                    run.kernel.kb.add_fact(pred, tuple(run.kernel._logic_arg(a, mod.env) for a in args))
            premise = _module_lineage(run, mod, S.Binding('knowledge', E.syntax(s), line=s.line),
                                      s, list(reads.values()), 'owner_premise')
            run._epistemic_knowledge.append(premise)
            run._trace(S.Node('module-knowledge', s.line, s.col), 'ok', binding=premise, note=mod.key)
        elif k == 'rule':
            with S.capture_binding_reads(run, run._read_bindings(), scope=True) as reads:
                run.kernel.kb.add_rule(s, mod.env)
            premise = _module_lineage(run, mod, S.Binding('knowledge', E.syntax(s), line=s.line),
                                      s, list(reads.values()), 'owner_premise')
            run._epistemic_knowledge.append(premise)
            run._trace(S.Node('module-knowledge', s.line, s.col), 'ok', binding=premise, note=mod.key)
        elif k in ('function', 'routine'):
            canon = calls[s.name]
            fn = define(run, s, mod.env, canon)
            fn.module = mod
            if canon not in st.callables:
                _register(run, canon, fn, s)
        elif k == 'import':
            sub = load_module(run, s.module, s.saved, at)
            ex = sub.exports()
            if s.alias:
                mod.env.vars[s.alias] = S.Binding(s.alias, {n: b.value for n, b in ex['constants'].items()},
                                                  stmt=f'L{s.line}', line=s.line)
                _module_lineage(run, mod, mod.env.vars[s.alias], s, list(ex['constants'].values()), 'derived')
            else:
                for n, b in ex['constants'].items():
                    if s.names is None or n in s.names:
                        if n in mod.env.vars:
                            raise S.SymblicError(f'{where(s)}: {n} is already bound', at.line, at.col, 'name')
                        mod.env.vars[n] = b
        elif k == 'let':
            if s.name in mod.env.vars:
                raise S.SymblicError(f'{where(s)}: {s.name} is bound twice', at.line, at.col, 'name')
            try:
                with S.capture_binding_reads(run, run._read_bindings(), scope=True) as reads:
                    value = run.kernel.eval(s.value, mod.env)
                ty = S.resolve_type(s.type, run.types, s.line) if s.type is not None else None
                if ty is not None:
                    value = S.check_value(value, ty, s.name)
            except S.SymblicError as e:
                raise S.SymblicError(f'{where(s)}: {e.message}', at.line, at.col, e.kind) from None
            b = S.Binding(s.name, value, ty, stmt=f'{mod.modid}:L{s.line}', line=s.line)
            _module_lineage(run, mod, b, s, list(reads.values()), 'derived')
            mod.env.vars[s.name] = b
            mod.constants[s.name] = b
        elif k in ('assert', 'expect', 'ensure'):
            try:
                ok = S._truth(run.kernel.eval(s.cond, mod.env), s.cond)
            except S.SymblicError as e:
                raise S.SymblicError(f'{where(s)}: {e.message}', at.line, at.col, 'check') from None
            if not ok:
                raise S.SymblicError(f'{where(s)}: the module\'s own check failed', at.line, at.col, 'check')
        elif k == 'test':
            mod.tests.append(s)


def _merge_term(run, term: str, definition: str, origin: str, node: S.Node) -> None:
    key = term.lower()
    old = run.terms.get(key)
    if old is not None and old[1].strip() != definition.strip():
        raise S.SymblicError(f'the term "{term}" means different things here and in {origin}', node.line, node.col,
                             'name')
    run.terms[key] = (term, definition)


def exec_import(run, node, env):
    mod = load_module(run, node.module, node.saved, node)
    st = state(run)
    ex = mod.exports()
    for term, definition in mod.terms:
        _merge_term(run, term, definition, f'module {mod.modid}', node)
    if node.alias:
        for n, canon in ex['callables'].items():
            _register(run, f'{node.alias}.{n}', st.callables[canon], node, env)
        for n, canon in ex['types'].items():
            _alias_type(run, f'{node.alias}.{n}', canon, node)
        rec = {n: b.value for n, b in ex['constants'].items()}
        run._bind(env, node.alias, rec, None, node, 'exact', 1,
                  meta={'_epistemic_parents': list(ex['constants'].values())})
        what = f'as {node.alias}'
    else:
        wanted = node.names
        if wanted is not None:
            known = set(ex['callables']) | set(ex['types']) | set(ex['constants'])
            missing = [n for n in wanted if n not in known]
            if missing:
                relations = [n for n in missing if n in ex['predicates']]
                if relations:
                    raise S.SymblicError('predicate imports are read-only bindings inside modules; expose '
                                         + ', '.join(relations) + ' through a module query helper function for '
                                         'a top-level caller', node.line, node.col, 'name')
                raise S.SymblicError(f'module {mod.modid} has no {", ".join(missing)} (it exports: '
                                     f'{", ".join(sorted(known)) or "nothing"})', node.line, node.col, 'name')
        for n, canon in ex['callables'].items():
            if wanted is None or n in wanted:
                _register(run, n, st.callables[canon], node, env)
        for n, canon in ex['types'].items():
            if wanted is None or n in wanted:
                _alias_type(run, n, canon, node)
        for n, b in ex['constants'].items():
            if wanted is None or n in wanted:
                run._bind(env, n, b.value, b.type, node, 'exact', 1, meta={'_epistemic_parents': [b]})
        what = 'all' if wanted is None else ', '.join(wanted)
    run._trace(node, 'ok', note=f'{mod.origin} {mod.sha256[:12]} ({what}): {len(ex["callables"])} callable(s), '
                                f'{len(ex["types"])} type(s), {len(ex["constants"])} constant(s), '
                                f'{len(mod.terms)} term(s); logic={mod.logic_mode}')


def _alias_type(run, name: str, canon: str, node: S.Node) -> None:
    if name in run.types and run.types[name] != {'k': 'named', 'name': canon}:
        raise S.SymblicError(f'type {name} is already defined', node.line, node.col, 'type')
    run.types[name] = {'k': 'named', 'name': canon}


def import_binds(node: S.Node) -> list:
    """The names an import binds (constants), for check() and the plan. Library modules are read to know
    their constants; anything unreadable binds only what the statement names."""
    if node.alias:
        return [node.alias]
    source = None if node.saved else library_source(node.module)
    consts = []
    if source is not None:
        try:
            prog = S.parse(source)
            consts = [s.name for s in prog['statements'] if s.k == 'let' and not s.name.startswith('_')]
        except S.SymblicError:
            consts = []
    if node.names is not None:
        return [n for n in node.names if n in consts] if source is not None else list(node.names)
    return consts


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _label_callable(n) -> str:
    ps = ', '.join(n.params)
    ret = f' -> {S.type_label(n.ret)}' if n.ret is not None else ''
    if n.k == 'routine':
        worst = 'exact'
        for s in _walk(n.body):
            if s.k == 'ask':
                ty = s.type or {'k': 'text'}
                worst = S_worse(worst, S.determinism_class(ty) if ty.get('k') != 'named' else 'structured')
        return f'{n.k} {n.name}({ps}){ret} [{worst}]'
    return f'{n.k} {n.name}({ps}){ret}'


def _defaults_read(n):
    return [s['default'] for s in n.specs if s['default'] is not None] or None


def _function_reads(n):
    """What a function reads for check(): its defaults, and its body with the parameters bound (wrapped in
    empty comprehensions, which bind their variable), so a misspelt name is reported before any run."""
    body = n.value
    for p in reversed(n.params):
        body = S.Node('comp', n.line, n.col, body=body, var=p, src=S.Node('list', n.line, n.col, items=[]), cond=None)
    return [_defaults_read(n), body]


def register() -> None:
    exts = [
        S.Extension('function', parse_function, exec_function, reads=_function_reads, label=_label_callable),
        S.Extension('routine', parse_routine, exec_routine, reads=_defaults_read, label=_label_callable,
                    block=True),
        S.Extension('import', parse_import, exec_import, binds=import_binds,
                    label=lambda n: 'import ' + (', '.join(n.names) + ' from ' if n.names else '') +
                    (f'"{n.module}"' if n.saved else n.module) + (f' as {n.alias}' if n.alias else '')),
        S.Extension('test', parse_test, exec_test, label=lambda n: f'test "{n.title}"', block=True),
        S.Extension('routine-return', lambda p, line, col, prog: None, exec_return, reads=lambda n: n.value,
                    label=lambda n: 'return'),
    ]
    # A statement only when it has the statement's shape, so v1 prose ("Import the data.", "Test it.")
    # stays prose. import and test are written in lower case; a capitalised first word is a sentence.
    looks = {
        'function': re.compile(r'^function\s+[^\W\d]\w*\s*\(', re.I | re.U),
        'routine': re.compile(r'^routine\s+[^\W\d]\w*\s*\(', re.I | re.U),
        'import': re.compile(r'^import\s+("|[a-z][a-z0-9_]*\s*(,|\bas\b|\bfrom\b|\.?\s*(#.*)?$))'),
        'test': re.compile(r'^test\s+("|\')'),
    }
    for ext in exts:
        if ext.keyword in looks:
            ext.looks = looks[ext.keyword].match       # used by the core once it filters prose lines
        if S.EXTENSIONS.get(ext.keyword) is None or getattr(S.EXTENSIONS[ext.keyword], '_lang', False):
            ext._lang = True
            S.register_extension(ext)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _test_run_class():
    from symblic.kernel import run as SR

    class TestRun(SR.Run):
        """Runs a program's declarations, then each `test` body in its own scope. Top-level asks, outputs and
        checks are skipped (they are the program, not its tests); a `let` that cannot be computed without
        them is skipped too."""

        def exec_statement(self, s, env):
            if env is self.kernel.env and s.k not in DECLARATIONS and s.k != 'test':
                self._trace(s, 'skipped', note='not run by the tests')
                return
            if env is self.kernel.env and s.k == 'given' and s.name not in self.inputs and s.default is None:
                self._trace(s, 'skipped', note='input not given to the tests')
                return
            if env is self.kernel.env and s.k == 'let':
                try:
                    return super().exec_statement(s, env)
                except (S.SymblicError, SR.RunFailed) as e:
                    error = e.err if isinstance(e, SR.RunFailed) else e
                    if error.kind in ('resource', 'unavailable', 'budget'):
                        raise
                    self._trace(s, 'skipped', note=f'not computable in the tests: {getattr(e, "message", e)}')
                    return
            if s.k == 'test' and env is self.kernel.env:
                return self._one_test(s, env)
            return super().exec_statement(s, env)

        def _one_test(self, s, env):
            st = state(self)
            only = self.opts.get('only')
            if only and s.title not in only:
                return
            t0 = time.time()
            asks0, calls0 = self.asks, self.calls
            row = {'title': s.title, 'line': s.line}
            try:
                self.exec_block(s.body, S.Env(env))
                row['status'] = 'passed'
            except SR.RunFailed as e:
                row.update(status='inconclusive' if e.err.kind in ('resource', 'unavailable', 'budget') else 'failed',
                           error=e.err.as_dict())
            except S.SymblicError as e:
                row.update(status='inconclusive' if e.kind in ('resource', 'unavailable', 'budget') else 'failed',
                           error=e.as_dict())
            except _Return:
                row.update(status='failed', error={'message': 'return outside a routine', 'line': s.line})
            row.update(seconds=round(time.time() - t0, 3), asks=self.asks - asks0, calls=self.calls - calls0)
            st.tests.append(row)
            self._trace(s, 'ok' if row['status'] == 'passed' else row['status'],
                        note=f'test "{s.title}" {row["status"]}' + (f': {row["error"]["message"]}'
                                                                     if row.get('error') else ''))
            if row['status'] == 'inconclusive':
                error = row['error']
                raise S.SymblicError(error['message'], error.get('line', 0), error.get('col', 0), error['kind'])

    return TestRun


def run_tests(source: str, applicators=None, inputs=None, by: str | None = None, only=None, folder=None,
              log=None) -> dict:
    """{'ok', 'passed', 'failed', 'tests': [...], 'error'}. Applicators are whatever the caller gives
    (fake ones in unit tests, real ones for a certification run)."""
    TestRun = _test_run_class()
    opts = {'by': by or 'fake:test', 'parallel': 1}
    if only:
        opts['only'] = list(only)
    run = TestRun(source, inputs or {}, applicators, opts, folder=folder, log=log)
    rep = run.execute()
    st = state(run)
    tests = st.tests
    passed = sum(1 for t in tests if t['status'] == 'passed')
    return {'ok': rep['status'] == 'done' and passed == len(tests), 'passed': passed,
            'failed': sum(1 for t in tests if t['status'] == 'failed'),
            'inconclusive': sum(1 for t in tests if t['status'] == 'inconclusive'),
            'tests': tests, 'error': rep.get('error'), 'status': rep['status'], 'asks': rep['asks'],
            'calls': rep['calls'], 'cached': rep['cached'],
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'kernel': rep['kernel'],
            'module_hashes': {key: module.sha256 for key, module in sorted(st.modules.items())}}


def certify(source: str, cohorts: list, applicators_for, only=None) -> dict:
    """Run a module's (or program's) tests once per cohort of agents, each from an empty record, and report
    each test's pass rate across cohorts. A routine whose certification tests pass for every cohort is
    one any of those agents can be trusted to apply; a test that passes for some cohorts and not others
    marks a routine whose contract is not yet tight. applicators_for(by) -> applicators for that cohort.
    Passing is measured by the tests' own assertions, never by agreement."""
    if len(cohorts) < 1:
        raise S.SymblicError('certify needs at least one cohort')
    per = []
    for by in cohorts:
        label = by if isinstance(by, str) else ', '.join(by)
        res = run_tests(source, applicators_for(by), by=by, only=only)
        per.append({'by': label, 'result': res})
    titles = []
    for p in per:
        for t in p['result']['tests']:
            if t['title'] not in titles:
                titles.append(t['title'])
    tests = []
    for title in titles:
        rows = []
        for p in per:
            t = next((x for x in p['result']['tests'] if x['title'] == title), None)
            rows.append({'by': p['by'], 'status': t['status'] if t else 'missing',
                         'error': (t or {}).get('error', {}).get('message') if t and t.get('error') else None,
                         'calls': (t or {}).get('calls', 0)})
        passed = sum(1 for r in rows if r['status'] == 'passed')
        tests.append({'title': title, 'passed': passed, 'of': len(rows), 'cohorts': rows})
    certified = [t['title'] for t in tests if t['passed'] == t['of']]
    module_maps = [p['result']['module_hashes'] for p in per]
    matching_modules = all(m == module_maps[0] for m in module_maps)
    complete = all(p['result']['status'] == 'done' and p['result']['ok'] for p in per)
    result = {'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'kernel': S.kernel_id(),
              'cohorts': [{'by': p['by'], 'passed': p['result']['passed'], 'failed': p['result']['failed'],
                          'inconclusive': p['result']['inconclusive'],
                          'status': p['result']['status'], 'error': p['result'].get('error'),
                          'source_sha256': p['result']['source_sha256'], 'kernel': p['result']['kernel'],
                          'module_hashes': p['result']['module_hashes']} for p in per],
              'tests': tests, 'certified': certified,
              'all': complete and matching_modules and len(certified) == len(tests) and bool(tests)}
    if matching_modules:
        result['module_hashes'] = module_maps[0]
    else:
        result['provenance_divergence'] = 'cohorts loaded different module source hashes'
    return result


# ---------------------------------------------------------------------------
# Crystallisation: a routine's verified answers compiled into a kernel function
# ---------------------------------------------------------------------------

_BARE_KEY = re.compile(r'^[^\W\d]\w*$', re.U)


def literal(v) -> str:
    """A kernel value as Symblic source that evaluates back to the same canonical value."""
    from fractions import Fraction
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v) if v >= 0 else f'({v})'
    if isinstance(v, Fraction):
        text = f'{abs(v.numerator)}/{v.denominator}'
        return f'(-{text})' if v < 0 else f'({text})'
    if isinstance(v, S.Svg):
        raise S.SymblicError('a drawing cannot be crystallised (keep the program that draws it)')
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t') \
            .replace('{', '{{').replace('}', '}}') + '"'
    if isinstance(v, tuple):
        return '[' + ', '.join(literal(x) for x in v) + ']'
    if isinstance(v, frozenset):
        items = sorted(v, key=lambda x: S.canon_json(x))
        return '{' + ', '.join(literal(x) for x in items) + '}' if items else 'set([])'
    if isinstance(v, dict):
        if not v:
            return '{:}'
        parts = []
        for k in sorted(v):
            key = k if _BARE_KEY.match(k) and k.lower() not in S.WORD_OPS else literal(k)
            parts.append(f'{key}: {literal(v[k])}')
        return '{' + ', '.join(parts) + '}'
    raise S.SymblicError(f'cannot write {S.type_name(v)} as a literal')


def _check_literal(v) -> str:
    text = literal(v)
    k = S.Kernel()
    p = S.Parser(S.tokenize(text), 1)
    back = k.eval(p.expr())
    if S.fingerprint(back) != S.fingerprint(v):
        raise S.SymblicError(f'the literal {text[:80]} does not read back as the same value')
    return text


def crystallise(source: str, routine: str, domain: list, applicators=None, by: str | None = None,
                min_agreement: float = 1.0, inputs=None, folder=None, log=None, workers: int = 1) -> dict:
    """Ask a routine once per input in `domain` (each input a value, or a list of arguments when the
    routine takes several) and compile the answers every one of whose asks agreed at least `min_agreement`
    into a module: a table plus a kernel function with the routine's name and signature. Importing that
    module answers those inputs exactly and with no model; anything else fails loudly instead of guessing.
    `workers` runs that many inputs at a time (each worker loads its own copy of the program; with a
    folder each keeps its record in folder/w<N>). The table keeps the domain's order whatever finishes first.
    {'module': text, 'kept': [...], 'left_out': [...], 'routine', 'signature', 'applicators', 'families',
    'kernel'}."""
    from symblic.kernel import run as SR
    from concurrent.futures import ThreadPoolExecutor
    TestRun = _test_run_class()
    workers = max(1, min(8, int(workers or 1), len(domain) or 1))

    def load(i: int):
        sub = folder if not folder or workers == 1 else os.path.join(folder, f'w{i}')
        if sub:
            os.makedirs(sub, mode=0o700, exist_ok=True)
        run = TestRun(source, inputs or {}, applicators, {'by': by or 'fake:none', 'parallel': 4, 'only': ['\x00']},
                      folder=sub, log=log)
        rep = run.execute()
        if rep['status'] != 'done':
            raise S.SymblicError(f'the program did not load: {(rep.get("error") or {}).get("message")}')
        fn = state(run).callables.get(routine)
        if fn is None or fn.kind != 'routine':
            raise S.SymblicError(f'{routine} is not a routine of this program')
        return run, fn

    run, fn = load(0)
    n_params = len(fn.node.specs)
    node = S.Node('call', 0, 0)
    results: list = [None] * len(domain)
    runs = [run]

    def one(r, raw):
        args = tuple(S.from_json(x) for x in raw) if n_params > 1 else (S.from_json(raw),)
        first = len(r.trace)
        try:
            value = r.kernel.functions[routine](r.kernel, node, *args)
        except (S.SymblicError, SR.RunFailed) as e:
            err = getattr(e, 'err', e)
            return 'left', {'input': raw, 'reason': getattr(err, 'message', str(err))}
        dependencies = _ask_dependencies(r.trace[first:])
        agreements = [d['agreement'] for d in dependencies]
        if any(not isinstance(a, (int, float)) or isinstance(a, bool) for a in agreements):
            return 'left', {'input': raw, 'reason': 'an ask dependency has no recorded agreement',
                            'dependencies': dependencies}
        low = min(agreements) if agreements else 1.0
        if any(d.get('contested') for d in dependencies):
            # e.g. a families shortfall or an order probe that was not stable: never an exact table entry
            return 'left', {'input': raw, 'value': S.show(value, 200), 'agreement': low,
                            'reason': 'an ask behind this answer was contested', 'dependencies': dependencies}
        if low < min_agreement:
            return 'left', {'input': raw, 'value': S.show(value, 200), 'agreement': low,
                            'reason': f'agreement {low:.0%} is below {min_agreement:.0%}',
                            'dependencies': dependencies}
        try:
            text = _check_literal(value)
            key = _check_literal(args[0] if n_params == 1 else args)
        except S.SymblicError as e:
            return 'left', {'input': raw, 'reason': e.message}
        return 'kept', {'input': raw, 'key': key, 'value': text, 'agreement': low, 'asks': len(agreements),
                        'dependencies': dependencies}

    def worker(w: int):
        # routines run on the thread that loaded their program: in parallel, every worker loads its own
        r = run if workers == 1 else load(w)[0]
        if workers > 1:
            runs.append(r)
        for i in range(w, len(domain), workers):
            results[i] = one(r, domain[i])
    if workers == 1:
        worker(0)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(worker, range(workers)))
    kept = [row for kind, row in results if kind == 'kept']
    left = [row for kind, row in results if kind == 'left']
    sig = fn.signature()
    params = [sp['name'] for sp in fn.node.specs]
    typed = ', '.join(f'{sp["name"]}: {S.type_label(sp["type"])}' if sp['type'] else sp['name'] for sp in fn.node.specs)
    ret = f' -> {S.type_label(fn.node.ret)}' if fn.node.ret is not None else ''
    match = params[0] if n_params == 1 else '[' + ', '.join(params) + ']'
    table = f'{routine}_table'
    sha = hashlib.sha256(source.encode('utf-8')).hexdigest()
    apps = sorted({a for r in runs for row in r.trace for a in ((row.get('ask') or {}).get('apps') or [])})
    # the families the votes computed (from the models the replies reported), not those of the requested labels
    voted = {f for r in runs for row in r.trace if row.get('kind') == 'ask'
             for f in ((row.get('ask') or {}).get('families') or [])}
    named = sorted(voted - {getattr(S, 'UNATTRIBUTED', 'unattributed')})
    families = named or sorted(voted) or (S.families_of(apps) if hasattr(S, 'families_of') else (
        sorted({S.family_of(a) for a in apps}) if hasattr(S, 'family_of') else []))
    kid = S.kernel_id() if hasattr(S, 'kernel_id') else {'lang': S.VERSION}
    rows = ',\n  '.join(f'[{r["key"]}, {r["value"]}]' for r in kept)
    module = (f'program {routine} crystal.\n'
              f'note Crystallised from routine {routine} ({sig}) of a program with SHA-256 {sha[:16]}…,\n'
              f'note answered by {", ".join(apps) or by or "?"} (model families: {", ".join(families) or "?"}) on '
              f'{time.strftime("%Y-%m-%d")}. {len(kept)} of {len(domain)} inputs kept: every ask behind each kept '
              f'answer agreed at least {min_agreement:.0%}.\n'
              f'note Kernel regime: {_kernel_text(kid)}.\n'
              f'note Inputs outside the table fail instead of guessing: call the routine itself for those.\n'
              f'let {table} = [\n  {rows}\n].\n' if kept else
              f'program {routine} crystal.\nnote Nothing was kept.\nlet {table} = [[0, 0]].\n')
    call_args = ', '.join(f'row[1][{i + 1}]' for i in range(n_params)) if n_params > 1 else 'row[1]'
    lookup = f'first([row[2] for row in {table} if row[1] = {match}])'
    if 'fail' in S.BUILTINS:          # a clear refusal outside the table (core builtin fail(message))
        lookup = (f'if any row in {table}: row[1] = {match} then {lookup} else fail("{routine} has no crystallised '
                  f'answer for this input (the crystal covers {len(kept)}); call the routine itself")')
    module += (f'function {routine}({typed}){ret} = {lookup}.\n'
               f'test "the table answers its own inputs" do\n'
               f'  assert all row in {table}: {routine}({call_args}) = row[2].\n'
               f'end.\n')
    check = S.check(module)
    if not check['ok']:
        raise S.SymblicError(f'the crystal does not check: {check["errors"][0]["message"]}')
    return {'module': module, 'kept': kept, 'left_out': left, 'routine': routine, 'signature': sig,
            'source_sha256': sha, 'applicators': apps, 'families': families, 'kernel': kid}


def _kernel_text(kid: dict) -> str:
    keys = ('lang', 'canon', 'geometry', 'unicode', 'max_digits', 'id')
    return ', '.join(f'{k} {kid[k]}' for k in keys if kid.get(k) is not None)


# ---------------------------------------------------------------------------
# The library: what each module offers (for a front end, the command line and the docs)
# ---------------------------------------------------------------------------

def library() -> list:
    out = []
    try:
        names = sorted(f[:-4] for f in os.listdir(LIB_DIR) if f.endswith('.sym') and MODULE_NAME_RX.match(f[:-4]))
    except OSError:
        return out
    for name in names:
        out.append(describe_module(name))
    return out


def describe_module(name: str, source: str | None = None) -> dict:
    """A module's documentation from its source alone (no run): title, notes, signatures, types, constants,
    terms and tests. Each callable's doc is the run of `note` lines right above it."""
    source = source if source is not None else library_source(name)
    if source is None:
        raise S.SymblicError(f'no module {name!r}')
    prog = S.parse(source)
    sha = hashlib.sha256(source.encode('utf-8')).hexdigest()
    items, intro = [], []
    notes = []                                   # (line, text) of the notes not yet attached
    seen_decl = False

    def doc_for(line: int) -> str:
        """The notes on the lines right above `line` (a contiguous run); earlier runs are the intro."""
        run, want = [], line - 1
        for ln, text in reversed(notes):
            if ln != want:
                break
            run.insert(0, text)
            want -= 1
        rest = [t for ln, t in notes if ln <= want]
        if not seen_decl:
            intro.extend(rest)
        notes.clear()
        return ' '.join(run)

    for s in prog['statements']:
        if s.k == 'note':
            notes.append((s.line, s.text))
            continue
        if s.k not in ('function', 'routine', 'define', 'let', 'term', 'rule'):
            continue
        if s.k == 'rule' and any(i['kind'] == 'relation' and i['name'] == s.pred for i in items):
            notes.clear()
            continue
        doc = doc_for(s.line)
        seen_decl = True
        if s.k == 'rule':
            args = ', '.join(a.name if a.k == 'name' else '…' for a in s.args)
            items.append({'kind': 'relation', 'name': s.pred, 'signature': f'relation {s.pred}({args})', 'doc': doc,
                          'line': s.line})
            continue
        if s.k in ('function', 'routine'):
            fn = Callable(s.k, s, S.Env(), s.name)
            items.append({'kind': s.k, 'name': s.name, 'signature': fn.signature(), 'doc': doc, 'line': s.line,
                          'asks': sum(1 for x in _walk(s.body) if x.k == 'ask') if s.k == 'routine' else 0})
        elif s.k == 'define':
            items.append({'kind': 'type', 'name': s.name, 'signature': f'{s.name} = {S.type_label(s.type)}',
                          'doc': doc, 'line': s.line})
        elif s.k == 'let':
            items.append({'kind': 'constant', 'name': s.name, 'signature': f'{s.name} = {_src_text(s.value)}',
                          'doc': doc, 'line': s.line})
        else:
            items.append({'kind': 'term', 'name': s.term, 'signature': f'{s.term} means "{s.definition}"', 'doc': doc,
                          'line': s.line})
    if not seen_decl:
        intro.extend(t for _ln, t in notes)
    tests = [s.title for s in prog['statements'] if s.k == 'test']
    return {'name': name, 'title': prog['name'], 'intro': ' '.join(intro), 'sha256': sha, 'items':
            [i for i in items if not i['name'].startswith('_')], 'tests': tests}


def _walk(stmts):
    for s in stmts or ():
        yield s
        if s.k == 'if':
            for _c, body in s.branches:
                yield from _walk(body)
            yield from _walk(s.else_body)
        elif hasattr(s, 'body') and isinstance(s.body, list):
            yield from _walk(s.body)


def _src_text(node) -> str:
    fn = getattr(__import__('importlib').import_module('symblic.kernel.run'), '_expr_text', None)
    try:
        return fn(node) if fn else '…'
    except Exception:  # noqa: BLE001
        return '…'


# `python3 -m symblic.lang.abstraction` runs this file as __main__: the language's own import of the canonical
# module (symblic.kernel.language imports it) registers the statements once, and the command line below
# hands over to that module, so there is never a second copy of these extensions.
if __name__ != '__main__':
    register()


# ---------------------------------------------------------------------------
# Background jobs: a job folder (job.json in, result.json out) run in its own process. A front end starts them
# with `python3 -m symblic.lang.abstraction job --dir FOLDER` (the host's API did: integration/host/symblic_lang_api.py)
# ---------------------------------------------------------------------------

def run_job(folder: str, applicators_for=None) -> int:
    """Run the certify or crystallise job described by folder/job.json; write folder/result.json (0600).
    applicators_for(by) gives the applicators (tests pass fakes; by default symblic.providers.applicators)."""
    folder = os.path.abspath(folder)
    with open(os.path.join(folder, 'job.json'), encoding='utf-8') as f:
        job = json.load(f)
    logf = open(os.path.join(folder, 'log.txt'), 'a', encoding='utf-8')

    def log(text):
        logf.write(f'{time.strftime("%H:%M:%S")} {text}\n')
        logf.flush()
    if applicators_for is None:
        from symblic.providers import applicators as SA

        def applicators_for(by):
            return SA.Applicators(owner_label=f'operator (Symblic {job["kind"]} job {os.path.basename(folder)})')
    out = {'kind': job['kind'], 'started': time.time()}
    try:
        source = job.get('source') or library_source(job.get('module') or '')
        if not source:
            raise S.SymblicError('no program to work on')
        if job['kind'] == 'certify':
            log(f'certify with {", ".join(job["cohorts"])}')
            out['result'] = certify(source, job['cohorts'], applicators_for)
        elif job['kind'] == 'crystallise':
            log(f'crystallise {job["routine"]} over {len(job["domain"])} inputs by {job["by"]}')
            res = crystallise(source, job['routine'], job['domain'], applicators_for(job['by']), by=job['by'],
                              min_agreement=float(job.get('min_agreement', 1.0)), log=log,
                              workers=int(job.get('workers') or 1))
            out['result'] = res
        else:
            raise S.SymblicError(f'unknown job kind {job["kind"]!r}')
        out['status'] = 'done'
    except Exception as e:  # noqa: BLE001  (a job ends visibly, whatever went wrong)
        out.update(status='failed', error=getattr(e, 'message', None) or f'{type(e).__name__}: {e}')
        log(f'failed: {out["error"]}')
    out['finished'] = time.time()
    tmp = os.path.join(folder, '.result.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, default=str)
    os.chmod(tmp, 0o600)
    os.replace(tmp, os.path.join(folder, 'result.json'))
    log(out['status'])
    logf.close()
    return 0 if out['status'] == 'done' else 1


# ---------------------------------------------------------------------------
# Command line: python3 -m symblic.lang.abstraction test FILE|MODULE [--by APP]
#               | certify MODULE --cohort A --cohort B [--certificate-out FILE]
#               | crystallise FILE --routine NAME --domain JSON --by APP [--out M.sym] | lib | doc NAME
# ---------------------------------------------------------------------------

def _cancel_on_sigterm() -> None:
    try:
        from symblic.providers import applicators as symblic_apply
        if hasattr(symblic_apply, 'install_sigterm'):
            symblic_apply.install_sigterm()
    except Exception:  # noqa: BLE001  (no applicators here: nothing to cancel)
        pass


def _write_certificate(path: str, value: dict) -> None:
    """Write a private certificate atomically; the target is never briefly readable by other users."""
    import tempfile
    target = os.path.abspath(path)
    fd, temporary = tempfile.mkstemp(prefix='.symblic-certificate-', dir=os.path.dirname(target))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog='python3 -m symblic.lang.abstraction', description='Symblic modules and tests.')
    p.add_argument('cmd', choices=['test', 'certify', 'crystallise', 'lib', 'doc', 'job'])
    p.add_argument('path', nargs='?')
    p.add_argument('--by', default=None, help='applicator for asks inside tests (default: none: kernel tests only)')
    p.add_argument('--cohort', action='append', default=[], help='certify: an applicator per cohort (repeat)')
    p.add_argument('--certificate-out', default='', help='certify: write a private source/kernel-pinned certificate')
    p.add_argument('--routine', default='', help='crystallise: the routine to compile')
    p.add_argument('--domain', default='', help='crystallise: a JSON list of inputs (a list of arguments each '
                                                'when the routine takes several)')
    p.add_argument('--min-agreement', type=float, default=1.0, help='crystallise: keep answers at least this agreed')
    p.add_argument('--out', default='', help='crystallise: write the module here')
    p.add_argument('--workers', type=int, default=1, help='crystallise: inputs asked at a time (at most 8)')
    p.add_argument('--dir', default='', help='job: the job folder (job.json in, result.json out)')
    p.add_argument('--json', action='store_true')
    a = p.parse_args(argv)
    if a.certificate_out and a.cmd != 'certify':
        p.error('--certificate-out is available only with certify')
    if a.cmd in ('job', 'certify', 'crystallise') or (a.cmd == 'test' and a.by):
        _cancel_on_sigterm()                 # a stopped job must not leave a model call running
    if a.cmd == 'job':
        return run_job(a.dir)
    if a.cmd == 'lib':
        lib = library()
        if a.json:
            print(json.dumps(lib, indent=1))
            return 0
        for m in lib:
            print(f'{m["name"]:<10} {m["title"]} · {len(m["items"])} names · {len(m["tests"])} tests')
        return 0
    if a.cmd == 'doc':
        d = describe_module(a.path)
        if a.json:
            print(json.dumps(d, indent=1))
            return 0
        print(f'{d["name"]}: {d["title"]}\n{d["intro"]}\n')
        for it in d['items']:
            print(f'  {it["signature"]}' + (f'\n      {it["doc"]}' if it['doc'] else ''))
        return 0
    if a.path and os.path.isfile(a.path):
        with open(a.path, encoding='utf-8') as f:
            source = f.read()
    else:
        source = library_source(a.path or '')
    if source is None:
        print(f'no file or library module {a.path!r}', file=sys.stderr)
        return 2
    if a.cmd == 'crystallise':
        if not (a.routine and a.domain and a.by):
            print('crystallise needs --routine, --domain JSON and --by', file=sys.stderr)
            return 2
        from symblic.providers import applicators as SA
        apps = SA.Applicators(owner_label='operator (symblic.lang.abstraction crystallise)')
        res = crystallise(source, a.routine, json.loads(a.domain), apps,
                          by=a.by, min_agreement=a.min_agreement, log=lambda t: print(t, file=sys.stderr, flush=True),
                          workers=a.workers)
        if a.out:
            with open(a.out, 'w', encoding='utf-8') as f:
                f.write(res['module'])
        print(json.dumps(res, indent=1, default=str) if a.json else res['module'])
        for x in res['left_out']:
            print(f'left out {json.dumps(x["input"])}: {x["reason"]}', file=sys.stderr)
        return 0
    if a.cmd == 'certify':
        if not a.cohort:
            print('certify needs at least one --cohort', file=sys.stderr)
            return 2
        from symblic.providers import applicators as SA
        cert = certify(source, a.cohort,
                       lambda by: SA.Applicators(owner_label='operator (symblic.lang.abstraction certify)'))
        if a.json:
            print(json.dumps(cert, indent=1, default=str))
        else:
            for t in cert['tests']:
                marks = ' '.join(f'{c["by"]}={c["status"]}' for c in t['cohorts'])
                print(f'{t["passed"]}/{t["of"]}  {t["title"]}  ({marks})')
            print('certified for every cohort' if cert['all'] else
                  f'{len(cert["certified"])}/{len(cert["tests"])} tests pass for every cohort')
        if a.certificate_out:
            from symblic.kernel import certificates as C
            try:
                sealed = C.make_certificate(source, cert, module_hashes=cert.get('module_hashes'))
                _write_certificate(a.certificate_out, sealed)
            except (C.CertificateError, OSError, ValueError) as exc:
                print(f'could not write certificate: {exc}', file=sys.stderr)
                return 2
        return 0 if cert['all'] else 1
    apps = None
    if a.by:
        from symblic.providers import applicators as SA
        apps = SA.Applicators(owner_label='operator (symblic.lang.abstraction test)')
    res = run_tests(source, apps, by=a.by, log=lambda t: None)
    if a.json:
        print(json.dumps(res, indent=1, default=str))
    else:
        for t in res['tests']:
            err = t.get('error') or {}
            print(f'{"PASS" if t["status"] == "passed" else "INCONCLUSIVE" if t["status"] == "inconclusive" else "FAIL"} line {t["line"]:>4}  {t["title"]}'
                  + (f'  — line {err.get("line")}: {err.get("message")}' if err else ''))
        if res.get('error'):
            print(f'error: {res["error"]}')
        print(f'{res["passed"]} passed, {res["failed"]} failed, {res["inconclusive"]} inconclusive')
    return 0 if res['ok'] else 1


if __name__ == '__main__':
    from symblic.lang import abstraction as _canonical
    sys.exit(_canonical.main())
