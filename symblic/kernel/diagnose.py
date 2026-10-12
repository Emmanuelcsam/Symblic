"""What the kernel can say about a failed check without asking a model.

Pure helpers for the interpreter (symblic.kernel.run) and for symblic.kernel.language.check: which parts of a
failed check depend on the answer alone (and what they computed), whether a statement's checks accept an
empty answer (a "vacuous" check that any answer passes), what a run of rejected answers looks like, and the
option rotations of a `one of` type for the permutation probe. These feed the repair text a model sees after
a rejected answer, and the warnings `check` prints.

Nothing here reads a store, calls a model or runs on import. A value is shown only when every name it reads
is the answer or a binding computed from the answer alone by the kernel: a given, an input or another
statement's result never reaches the text these helpers return.

Depends on: symblic.kernel.language. Used by: symblic.kernel.language (check) and symblic.kernel.run.
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction
import math

from symblic.kernel import language as S

SHOW = 80                    # characters of one shown value
EXPLAIN_LIMIT = 400          # characters of one explanation
STATIC_STEPS = 50_000        # kernel steps for the whole of static_warnings


# ---------------------------------------------------------------------------
# Which expressions reach only the kernel, and which names come from the answer alone
# ---------------------------------------------------------------------------

def pure(node) -> bool:
    """True when an expression reaches only the kernel: no query, and every call is a builtin."""
    if isinstance(node, S.Node):
        if node.k == 'query':
            return False
        if node.k == 'call' and (node.fn not in S.BUILTINS or node.fn in S.SPECULATION_DENIED):
            return False
        return all(pure(v) for v in vars(node).values())
    if isinstance(node, dict):
        return all(pure(v) for v in node.values())
    if isinstance(node, (tuple, list)):
        return all(pure(v) for v in node)
    return True


def names(node) -> set:
    """Every name an expression reads, except the variables its own quantifiers and comprehensions bind.
    Nothing else is left out: a name spelled like a logic variable (`Limit`, `_s`) or like a builtin (`count`,
    `last`) can be bound to an input or a loop item, so the no-leak rule must see it. A query's arguments are not
    walked (pure() already rejects queries); that is the one difference from S.free_names."""
    out = set()

    def visit(n, bound):
        if isinstance(n, (list, tuple)):
            for x in n:
                visit(x, bound)
        elif isinstance(n, dict):
            for x in n.values():
                visit(x, bound)
        elif isinstance(n, S.Node):
            if n.k == 'name':
                if n.name not in bound:
                    out.add(n.name)
            elif n.k in ('quant', 'comp'):
                visit(n.src, bound)
                inner = bound | {n.var}
                visit(n.body, inner)
                if n.k == 'comp' and getattr(n, 'cond', None) is not None:
                    visit(n.cond, inner)
            elif n.k == 'query':
                return
            else:
                for x in vars(n).values():
                    visit(x, bound)
    visit(node, frozenset())
    return out


def derived_names(ask_name, between, env=None) -> set:
    """The ask's name and each `let` in `between` (in order) whose value is a pure function of names already
    derived (or of the kernel's constants): the bindings whose values follow from the answer alone. With `env`,
    a constant name the program has bound (`given pi: Text`) is that binding, not the constant, so it does not
    count; without `env` no constant counts."""
    constants = set(S.CONSTANTS) if env is not None and not any(
        env.lookup(c) is not None for c in S.CONSTANTS) else set()
    out = {ask_name}
    for t in between or ():
        if getattr(t, 'k', '') != 'let' or not pure(t.value):
            continue
        if all(n in out or n in constants for n in names(t.value)):
            out.add(t.name)
    return out


def _literal(node) -> bool:
    return isinstance(node, S.Node) and (node.k in ('num', 'lit') or (
        node.k == 'str' and all(isinstance(p, str) for p in node.parts)))


def answer_only(node, derived) -> bool:
    """True when an expression reaches only the kernel and reads no name outside `derived` (the names whose
    values follow from the answer alone): anything it computes, and any error it raises, is then a function of
    the answer."""
    return isinstance(node, S.Node) and pure(node) and names(node) <= set(derived)


def _showable(node, derived) -> bool:
    if not isinstance(node, S.Node) or not pure(node):
        return False
    read = names(node)
    return bool(read) and read <= derived


# ---------------------------------------------------------------------------
# explain: the answer-only parts of a failed check
# ---------------------------------------------------------------------------

def explain(cond, env, kb, derived, steps=20_000) -> str:
    """What the kernel computed for the parts of a failed check that depend on the answer alone, as
    `<expression> = <value>` pieces joined by `; ` (at most 400 characters), or '' when nothing can be shown.
    A part that reads any other name is never evaluated, shown or named. Evaluation uses its own kernel and
    budget and never binds into `env`."""
    try:
        if any(env.lookup(c) is not None for c in S.CONSTANTS):
            # a program that binds `pi` or `e` makes a let reading it depend on that binding, which
            # derived_names cannot see: show nothing rather than risk an outside value
            return ''
        kernel = S.Kernel(S.Env(env), kb, S.Budget(steps))
        pieces = _explain(cond, kernel, kernel.env, set(derived))
    except Exception:  # noqa: BLE001  (a diagnosis never breaks the run)
        return ''
    text = '; '.join(dict.fromkeys(p for p in pieces if p))
    if len(text) > EXPLAIN_LIMIT:
        cut = text.rfind('; ', 0, EXPLAIN_LIMIT + 1)
        text = text[:cut] if cut > 0 else text[:EXPLAIN_LIMIT - 1] + '…'
    return text


def _text(node) -> str:
    from symblic.kernel import run as symblic_run
    return symblic_run._expr_text(node)


def _value(kernel, node, env):
    """(True, value) or (False, None) when the kernel refuses (budget included)."""
    try:
        return True, kernel.eval(node, env)
    except S.SymblicError:
        return False, None


def _shown(kernel, node, env, derived) -> list:
    if _literal(node) or not _showable(node, derived):
        return []
    ok, v = _value(kernel, node, env)
    return [f'{_text(node)} = {S.show(v, SHOW)}'] if ok else []


def _conjuncts(node) -> list:
    if isinstance(node, S.Node) and node.k == 'bin' and node.op == 'and':
        return _conjuncts(node.a) + _conjuncts(node.b)
    return [node]


def _explain(node, kernel, env, derived) -> list:
    if not isinstance(node, S.Node):
        return []
    k = node.k
    if k == 'cmp':
        out = []
        for part in node.parts:
            out += _shown(kernel, part, env, derived)
        return out
    if k == 'bin' and node.op == 'and':
        for part in _conjuncts(node):
            if not _showable(part, derived):
                continue
            ok, v = _value(kernel, part, env)
            if ok and v is False:
                return _explain(part, kernel, env, derived)
        return []
    if k == 'bin' and node.op == 'or':
        out = []
        for side in (node.a, node.b):
            if _showable(side, derived):
                out += _explain(side, kernel, env, derived)
        return out
    if k == 'bin' and node.op == '->':
        return _explain(node.b, kernel, env, derived)
    if k == 'quant':
        return _quant(node, kernel, env, derived)
    if k == 'call':
        out = []
        for arg in list(node.args) + list(node.kwargs.values()):
            out += _shown(kernel, arg, env, derived)
        return out
    return []


def _quant(node, kernel, env, derived) -> list:
    inner = derived | {node.var}
    if not _showable(node.src, derived) or not _showable(node.body, inner):
        return []
    ok, src = _value(kernel, node.src, env)
    if not ok:
        return []
    try:
        items = kernel._iterable(src, node)
    except S.SymblicError:
        return []
    n = len(items)
    for i, item in enumerate(items, 1):
        child = S.Env(env)
        child.vars[node.var] = S.Binding(node.var, item)
        ok, v = _value(kernel, node.body, child)
        if not ok or not isinstance(v, bool):
            return []
        if node.q == 'any':
            if v:
                return []
            continue
        if (node.q == 'all' and not v) or (node.q == 'none' and v):
            item_text = S.show(item, SHOW)
            head = f'{"fails" if node.q == "all" else "holds"} for {node.var} = {item_text} (item {i} of {n})'
            # the body explained with the variable bound, when that adds more than the item itself
            more = [p for p in _explain(node.body, kernel, child, inner) if p != f'{node.var} = {item_text}']
            return [head + (': ' + '; '.join(dict.fromkeys(more)) if more else '')]
    if node.q == 'any':
        return [f'no item of {_text(node.src)} passes ({n} items)']
    return []


# ---------------------------------------------------------------------------
# trivial: the empty answer of a type
# ---------------------------------------------------------------------------

TRIVIAL_CAP = 10_000         # values an empty-answer witness may hold; a larger one is not built (no finding)


def _witness_size(ty) -> int | None:
    """How many values the empty answer of a type holds, computed from the type alone (nothing is built), or
    None when there is no empty answer. Nested minimum lengths multiply."""
    k = ty.get('k') if isinstance(ty, dict) else None
    if k in ('text', 'code', 'int', 'number', 'bool', 'enum'):
        return 1
    if k in ('list', 'set'):
        n = ty.get('min') or 0
        if not n:
            return 1
        if k == 'set' or not isinstance(n, int):
            return None
        inner = _witness_size(ty.get('of'))
        return None if inner is None else n * inner
    if k == 'record':
        total = 1
        for _name, fty in ty.get('fields') or ():
            inner = _witness_size(fty)
            if inner is None:
                return None
            total += inner
            if total > TRIVIAL_CAP:
                return total
        return total
    return None


def trivial(ty):
    """(open, value): the EMPTY value of a resolved type and whether it has an open part (free text, a list
    or set that may be empty, an unbounded number), or None when the type has none (a set that must have
    items, any, svg) or when it would hold more than TRIVIAL_CAP values (`List of Text length 1000000000`: the
    witness is never built). Values are ones `S.check_value` accepts for the type."""
    size = _witness_size(ty)
    if size is None or size > TRIVIAL_CAP:
        return None
    found = _trivial(ty)
    if found is None:
        return None
    try:
        return found[0], S.check_value(found[1], ty)
    except S.SymblicError:
        return None


def _trivial(ty):
    k = ty.get('k') if isinstance(ty, dict) else None
    if k in ('text', 'code'):
        return True, ''
    if k in ('list', 'set'):
        n = ty.get('min') or 0
        if not n:
            return True, (() if k == 'list' else S.ValueSet())
        if k == 'set':
            return None
        inner = _trivial(ty['of'])
        if inner is None:
            return None
        return inner[0], tuple(inner[1] for _ in range(n))
    if k in ('int', 'number'):
        if 'lo' not in ty:
            return True, 0
        lo, hi = Fraction(str(ty['lo'])), Fraction(str(ty['hi']))
        if lo <= 0 <= hi:
            return False, 0
        if k == 'int':
            v = math.ceil(lo)
            return (False, v) if v <= hi else None
        return False, S.norm_num(lo)
    if k == 'bool':
        return False, False
    if k == 'enum':
        return False, ty['options'][0]
    if k == 'record':
        value, opened = {}, False
        for name, fty in ty['fields']:
            inner = _trivial(fty)
            if inner is None:
                return None
            opened = opened or inner[0]
            value[name] = inner[1]
        return opened, value
    return None


# ---------------------------------------------------------------------------
# static_warnings: lints for symblic.kernel.language.check
# ---------------------------------------------------------------------------

def static_warnings(statements, types) -> list:
    """Warnings for `symblic.kernel.language.check`: an ask whose anchored `ensure ... else retry` checks all accept its empty
    answer (SYM_VACUOUS), and two keyed `act` statements of one capability that share a literal key on one
    path (SYM_SAME_KEY). Never raises."""
    out = []
    try:
        budget = S.Budget(STATIC_STEPS)
        rules = _rule_deps(statements)
        for block in _blocks(statements):
            out += _vacuous(block, types or {}, rules, budget)
    except Exception:  # noqa: BLE001  (a lint never breaks check)
        pass
    try:
        out += _same_keys(statements)
    except Exception:  # noqa: BLE001
        pass
    return out


def _blocks(stmts):
    """Every statement list of a program: the top level, if branches, for bodies, extension blocks."""
    yield stmts
    for s in stmts:
        if s.k == 'if':
            for _c, body in s.branches:
                yield from _blocks(body)
            if s.else_body:
                yield from _blocks(s.else_body)
        elif s.k == 'for' or (s.k in S.EXTENSIONS and S.EXTENSIONS[s.k].block):
            yield from _blocks(s.body)


def _rule_deps(statements) -> dict:
    from symblic.kernel import run as R
    deps: dict = {}
    for t in R._flat(statements):
        if t.k == 'rule':
            deps.setdefault(t.pred, set()).update(R._lit_preds(t.body))
    return deps


def _anchors(stmts, deps) -> dict:
    """Run._anchors without a run: ensure index -> the index of the ask it checks."""
    from symblic.kernel import run as R
    out = {}
    for i, s in enumerate(stmts):
        if s.k != 'ensure' or s.on_fail != 'retry':
            continue
        need = set(S.free_names(s.cond)) | {'#fact:' + p for p in R._closure(R._queried(s.cond), deps)}
        for j in range(i - 1, -1, -1):
            t = stmts[j]
            if set(R._binds(t)) & need:
                if t.k == 'ask':
                    out[i] = j
                    break
                need |= set(S.free_names(S._reads_of(t))) | R._fact_names(t)
                need |= {'#fact:' + p for p in R._closure(R._queried_in(t), deps)}
    return out


def shown_empty(value) -> str:
    """An empty answer as a message shows it: empty text is written "" (S.show gives nothing for it)."""
    return '""' if value == '' and isinstance(value, str) else S.show(value, SHOW)


def vacuous_message(name, shown) -> str:
    """The SYM_VACUOUS text; `shown` is the empty answer as `shown_empty(value)` gives it."""
    return f'{name}: its checks accept the empty answer {shown}; add a check that an empty answer fails'


def _vacuous(stmts, types, deps, budget) -> list:
    by_ask: dict = {}
    for ei, ai in sorted(_anchors(stmts, deps).items()):
        by_ask.setdefault(ai, []).append(ei)
    out = []
    for ai, ensures in sorted(by_ask.items()):
        ask = stmts[ai]
        if getattr(ask, 'each', None) is not None:
            continue
        between = stmts[ai + 1:max(ensures)]
        if any(t.k not in ('let', 'ensure') for t in between):
            continue
        lets = [t for t in between if t.k == 'let']
        if not all(pure(t.value) for t in lets) or not all(pure(stmts[e].cond) for e in ensures):
            continue
        try:
            found = trivial(S.resolve_type(ask.type, types, ask.line))
            if found is None or not found[0]:
                continue
            value = found[1]
            env = S.Env()
            env.vars[ask.name] = S.Binding(ask.name, value)
            kernel = S.Kernel(env, S.KB(), budget)
            checks = {id(stmts[e]) for e in ensures}
            passed = True
            for t in between + [stmts[max(ensures)]]:
                if t.k == 'let':
                    if env.has_local(t.name):
                        passed = False
                        break
                    v = kernel.eval(t.value, env)
                    if t.type is not None:
                        v = S.check_value(v, S.resolve_type(t.type, types, t.line), t.name)
                    env.vars[t.name] = S.Binding(t.name, v)
                elif id(t) in checks and not S._truth(kernel.eval(t.cond, env), t.cond):
                    passed = False
                    break
        except Exception:  # noqa: BLE001  (an unbound outside name, the budget: no finding for this ask)
            continue
        if passed:
            out.append({'line': ask.line, 'code': 'SYM_VACUOUS',
                        'message': vacuous_message(ask.name, shown_empty(value))})
    return out


def _act_key(s):
    capability, options = getattr(s, 'capability', None), getattr(s, 'options', None)
    if not isinstance(capability, str) or not isinstance(options, dict):
        return None
    key = options.get('key')
    if not isinstance(key, S.Node) or key.k != 'str' or not all(isinstance(p, str) for p in key.parts):
        return None
    return capability, ''.join(key.parts)


def _same_keys(statements) -> list:
    acts = []                                   # (statement, (capability, key), path of (if id, branch))

    def walk(stmts, path):
        for s in stmts:
            if s.k == 'act':
                found = _act_key(s)
                if found is not None:
                    acts.append((s, found, path))
            if s.k == 'if':
                for n, (_c, body) in enumerate(s.branches):
                    walk(body, path + ((id(s), n),))
                if s.else_body:
                    walk(s.else_body, path + ((id(s), len(s.branches)),))
            elif s.k == 'for' or (s.k in S.EXTENSIONS and S.EXTENSIONS[s.k].block):
                walk(s.body, path)
    walk(statements, ())

    def exclusive(p, q):
        branch = dict(p)
        return any(i in branch and branch[i] != n for i, n in q)

    out = []
    for j, (later, found, path) in enumerate(acts):
        first = next((s for s, f, p in acts[:j] if f == found and not exclusive(p, path)), None)
        if first is not None:
            out.append({'line': later.line, 'code': 'SYM_SAME_KEY', 'message':
                        f'act {found[0]}: the key "{found[1]}" is also used at line {first.line}; an action with a '
                        "key happens once, so this statement would get that one's outcome"})
    return out


# ---------------------------------------------------------------------------
# Retry exhaustion
# ---------------------------------------------------------------------------

def exhaustion(hashes):
    """The pattern of the answers a check rejected (their fingerprints, in order), or None for fewer than 2."""
    hashes = list(hashes or ())
    if len(hashes) < 2:
        return None
    n, d = len(hashes), len(set(hashes))
    return {'attempts': n, 'distinct': d, 'pattern': 'same' if d == 1 else ('different' if d == n else 'mixed')}


def exhaustion_text(d) -> str:
    pattern = (d or {}).get('pattern')
    if pattern == 'same':
        return 'every attempt gave the same answer, so the check, the answer type or the input may be what is wrong'
    if pattern == 'different':
        return 'every attempt gave a different answer, so the statement may be read in more than one way'
    return ''


# ---------------------------------------------------------------------------
# Option rotations (the permutation probe)
# ---------------------------------------------------------------------------

def rotated(ty, r) -> dict:
    """A copy of a resolved type with the options of every `one of` in it rotated left by r (mod their
    number); definitions stay with their options."""
    if not isinstance(ty, dict):
        return ty
    k = ty.get('k')
    if k == 'enum':
        opts = list(ty['options'])
        shift = r % len(opts) if opts else 0
        return {**ty, 'options': opts[shift:] + opts[:shift]}
    if k in ('list', 'set'):
        return {**ty, 'of': rotated(ty['of'], r)}
    if k == 'record':
        return {**ty, 'fields': [[name, rotated(fty, r)] for name, fty in ty['fields']]}
    return dict(ty)


def has_options(ty) -> bool:
    """Whether a `one of` with at least two options occurs in a resolved type."""
    if not isinstance(ty, dict):
        return False
    k = ty.get('k')
    if k == 'enum':
        return len(ty.get('options') or ()) >= 2
    if k in ('list', 'set'):
        return has_options(ty.get('of'))
    if k == 'record':
        return any(has_options(fty) for _name, fty in ty.get('fields') or ())
    return False
