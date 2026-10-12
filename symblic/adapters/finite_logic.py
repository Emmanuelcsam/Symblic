"""Finite-domain logic: expand quantified statements over small named domains into propositional proof tasks.

With a finite domain written out by the caller (for example people = {ann, bob}), "every person is mortal"
becomes the conjunction of its instances, and a proof can then be checked by symblic.adapters.proof and
symblic.adapters.proof_steps. expand() performs that expansion, verify() checks a certificate against the
expanded task, parse_formula() reads the controlled syntax. There is no truth or model search: domains,
premises and goal are the caller's, and a receipt means "valid for exactly these finite domains".

See docs/reference/FINITE-LOGIC.md for the grammar, resource bounds, namespace encoding and the conditional
meaning of receipts.

Depends on: symblic.adapters.proof. Used by: the finite_parse, finite_expand, finite_check and
finite_steps_check builtins (through symblic.adapters.proof_adapter) and the human-logic compiler
(symblic.adapters.logic).
"""

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
import hashlib
import json
import re
import unicodedata

from symblic.adapters import proof as proof

VERSION = 1
LOGIC = 'finite-domain-intuitionistic-propositional-expansion'
MAX_DEPTH = 48
MAX_INPUT_NODES = 12000
MAX_INPUT_BYTES = 262144
MAX_TEXT = 1024
MAX_IDENTIFIER = 64
MAX_DOMAIN = 128
MAX_MEMBERS = 1024
MAX_OUTPUT_NODES = 8000
MAX_OUTPUT_BYTES = 100000
MAX_WORK = 50000
_WORD = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
_IDENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]*\Z')
_RESERVED = frozenset(('forall', 'exists', 'in', 'and', 'or', 'implies', 'not', 'false'))


class FiniteLogicError(ValueError):
    """Stable diagnostic without source excerpts."""


def _fail(code):
    raise FiniteLogicError(code)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _text(value):
    if type(value) is not str:
        _fail('text_type')
    if len(value) > MAX_TEXT:
        _fail('text_limit')
    if unicodedata.normalize('NFC', value) != value:
        _fail('unicode')
    if any(unicodedata.category(c) in ('Cs', 'Cf') or
           (unicodedata.category(c) == 'Cc' and c not in '\n\r\t') for c in value):
        _fail('unicode')


def _ident(value):
    if (type(value) is not str or len(value) > MAX_IDENTIFIER or
            not _IDENT.fullmatch(value) or value in _RESERVED):
        _fail('identifier')


def _scan(value, tick=None):
    # Walk one child at a time.  The previous eager ``stack.extend`` copied a
    # wide sibling frontier before charging those nodes, so a bounded input
    # could consume memory proportional to width times depth.  Iterators keep
    # the pending frontier O(depth) while retaining the old deterministic LIFO
    # order and per-occurrence charging for shared subtrees.
    def children(item):
        if type(item) is dict:
            for key, child in reversed(item.items()):
                if type(key) is not str:
                    _fail('input_type')
                yield key
                yield child
        else:
            yield from reversed(item)

    stack = [(iter((value,)), 0, None)]
    active = set()
    nodes = size = 0
    while stack:
        iterator, depth, container = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            if container is not None:
                active.remove(container)
            continue
        if tick is not None:
            tick(1)
        nodes += 1
        size += 2
        if nodes > MAX_INPUT_NODES:
            _fail('input_nodes')
        if depth > MAX_DEPTH:
            _fail('depth_limit')
        typ = type(item)
        if typ in (dict, list):
            if id(item) in active:
                _fail('cycle')
            if len(item) > MAX_INPUT_NODES:
                _fail('input_nodes')
            active.add(id(item))
            stack.append((children(item), depth + 1, id(item)))
        elif typ is str:
            # Proof atoms may be longer than source text after namespace encoding.
            if len(item) > proof.MAX_TEXT:
                _fail('text_limit')
            try:
                size += len(_json(item).encode('utf-8'))
            except UnicodeError:
                _fail('unicode')
        elif typ is int and item in (0, 1):
            size += 1
        else:
            _fail('input_type')
        if size > MAX_INPUT_BYTES:
            _fail('input_bytes')
    return nodes


def _join(op, values):
    """Balanced, deterministic left-to-right split; no associative ambiguity."""
    def part(start, end):
        if end - start == 1:
            return values[start]
        middle = (start + end) // 2
        return [op, part(start, middle), part(middle, end)]
    return part(0, len(values))


def _prepare(domains, premises, goal, tick=None):
    if type(domains) is not dict or type(premises) is not dict:
        _fail('schema')
    total = 0
    members = {}
    widths = {}
    for name, values in domains.items():
        _ident(name)
        if type(values) is not list:
            _fail('domain_schema')
        if len(values) > MAX_DOMAIN:
            _fail('domain_limit')
        total += len(values)
        if total > MAX_MEMBERS:
            _fail('domain_limit')
        for value in values:
            _text(value)
        if len(set(values)) != len(values):
            _fail('duplicate_member')
        members[name] = set(values)
        widths[name] = max((len(_json(v).encode('utf-8')) for v in values), default=2)
    signatures = {}

    def domain(name):
        _ident(name)
        if name not in domains:
            _fail('undeclared_domain')

    def inspect(f, scope):
        if tick is not None:
            tick(1)
        # Returns conservative expanded (nodes, bytes, work) before allocation.
        if type(f) is not list or not f or type(f[0]) is not str:
            _fail('formula_schema')
        op = f[0]
        if op == 'false' and len(f) == 1:
            return (2, 9, 1)
        if op == 'atom' and len(f) == 2:
            _text(f[1])
            atom = _json(['proposition', f[1]])
            if len(atom) > proof.MAX_TEXT:
                _fail('ground_atom_limit')
            return (3, len(_json(['atom', atom]).encode('utf-8')), 1)
        if op == 'pred' and len(f) == 3 and type(f[2]) is list:
            _ident(f[1])
            signature = []
            width = 32 + len(f[1])
            for term in f[2]:
                if type(term) is not list or len(term) != 3:
                    _fail('term_schema')
                if term[0] == 'var':
                    _ident(term[1])
                    domain(term[2])
                    if term[1] not in scope:
                        _fail('free_variable')
                    if scope[term[1]] != term[2]:
                        _fail('variable_domain')
                    sort = term[2]
                    val_width = widths[sort]
                elif term[0] == 'const':
                    domain(term[1])
                    _text(term[2])
                    sort = term[1]
                    if term[2] not in members[sort]:
                        _fail('out_of_domain')
                    val_width = len(_json(term[2]).encode('utf-8'))
                else:
                    _fail('term_schema')
                signature.append(sort)
                width += len(sort) + val_width + 8
            if f[1] in signatures and signatures[f[1]] != signature:
                _fail('predicate_signature')
            signatures[f[1]] = signature
            # Upper bound on the JSON-string namespace encoding, including escaping.
            if width > proof.MAX_TEXT:
                _fail('ground_atom_limit')
            return (3, width * 6 + 16, 1 + len(f[2]))
        if op in ('and', 'or', 'implies') and len(f) == 3:
            a, b = inspect(f[1], scope), inspect(f[2], scope)
            return (2 + a[0] + b[0], 16 + a[1] + b[1], 1 + a[2] + b[2])
        if op in ('forall', 'exists') and len(f) == 4:
            _ident(f[1])
            domain(f[2])
            if f[1] in scope:
                _fail('shadowing')
            body = inspect(f[3], dict(scope, **{f[1]: f[2]}))
            n = len(domains[f[2]])
            if not n:
                return (6, 40, 1) if op == 'forall' else (2, 9, 1)
            return (n * body[0] + 2 * (n - 1),
                    n * body[1] + 16 * (n - 1), 1 + n * body[2] + n)
        _fail('formula_schema')

    costs = []
    for name, f in premises.items():
        _ident(name)
        costs.append(inspect(f, {}))
    costs.append(inspect(goal, {}))
    totals = tuple(sum(c[i] for c in costs) for i in range(3))
    if totals[0] > MAX_OUTPUT_NODES:
        _fail('expansion_nodes')
    if totals[1] > MAX_OUTPUT_BYTES:
        _fail('expansion_bytes')
    if totals[2] > MAX_WORK:
        _fail('expansion_work')

    if tick is not None:
        tick(totals[2])  # Charge bounded expansion before allocating it.

    def lower(f, env):
        op = f[0]
        if op == 'false':
            return ['false']
        if op == 'atom':
            return ['atom', _json(['proposition', f[1]])]
        if op == 'pred':
            args = [[t[2], env[t[1]]] if t[0] == 'var' else [t[1], t[2]] for t in f[2]]
            return ['atom', _json(['predicate', f[1], args])]
        if op in ('forall', 'exists'):
            values = [lower(f[3], dict(env, **{f[1]: v})) for v in domains[f[2]]]
            if not values:
                return ['implies', ['false'], ['false']] if op == 'forall' else ['false']
            return _join('and' if op == 'forall' else 'or', values)
        return [op, lower(f[1], env), lower(f[2], env)]

    expanded = {'premises': {name: lower(f, {}) for name, f in premises.items()},
                'goal': lower(goal, {})}
    # Locally check generated depth/text against the downstream envelope.
    # No dependency on the proof checker's private normalization/validation.
    for f in [*expanded['premises'].values(), expanded['goal']]:
        stack = [(f, 2)]  # formula inside premises inside verify's input envelope
        while stack:
            item, depth = stack.pop()
            if depth + 1 > proof.MAX_DEPTH:
                _fail('proof_formula_limit')
            if item[0] == 'atom':
                if len(item[1]) > proof.MAX_TEXT:
                    _fail('ground_atom_limit')
            elif item[0] != 'false':
                stack.extend(((item[1], depth + 1), (item[2], depth + 1)))
    return expanded, totals


def expand(domains, premises, goal, *, tick=None):
    """Return detached expanded premises/goal and source/expanded identities.

    Raises FiniteLogicError on invalid source or bounded-expansion refusal.
    Domain list order is authoritative and determines conjunction tree order.
    """
    try:
        _scan([domains, premises, goal], tick)
        expanded, costs = _prepare(domains, premises, goal, tick)
        hashes = {'domains': _hash(domains), 'premises': _hash(premises), 'goal': _hash(goal),
                  'source': _hash([VERSION, LOGIC, domains, premises, goal]),
                  'expanded_premises': _hash(expanded['premises']),
                  'expanded_goal': _hash(expanded['goal'])}
        return dict(expanded, version=VERSION, logic=LOGIC, hashes=hashes,
                    domain_sizes={k: len(v) for k, v in domains.items()},
                    expansion_bounds=dict(zip(('nodes', 'bytes', 'work'), costs)))
    except RecursionError:
        raise FiniteLogicError('depth_limit') from None


def verify(domains, premises, goal, certificate, *, tick=None):
    """Check an ordinary proof certificate against caller-authorized expansion."""
    result = dict(ok=False, version=VERSION, logic=LOGIC, hashes={}, proof_receipt=None,
                  conditional_on_premises=True, conditional_on_domains=True,
                  consistency='not_checked')
    try:
        _scan([domains, premises, goal, certificate], tick)
        expansion = expand(domains, premises, goal, tick=tick)
        checked = proof.verify(expansion['premises'], expansion['goal'], certificate,
                               tick=(lambda: tick(1)) if tick is not None else None)
        result.update(ok=checked['ok'], hashes=expansion['hashes'],
                      domain_sizes=expansion['domain_sizes'], proof_receipt=checked,
                      expansion_bounds=expansion['expansion_bounds'])
        if checked['ok']:
            result['hashes']['judgment'] = _hash([VERSION, LOGIC, expansion['hashes']['source'],
                                                 checked['hashes']['judgment']])
        else:
            result['error'] = 'proof_rejected'
    except FiniteLogicError as exc:
        result['error'] = str(exc)
    except RecursionError:
        result['error'] = 'depth_limit'
    return result


def parse_formula(text):
    """Controlled syntax with typed terms: P(x:People, People[\"Ada\"])."""
    try:
        if type(text) is not str:
            _fail('text_type')
        if len(text) > MAX_INPUT_BYTES:
            _fail('input_bytes')
        try:
            if len(text.encode('utf-8')) > MAX_INPUT_BYTES:
                _fail('input_bytes')
        except UnicodeError:
            _fail('unicode')
        tokens = []
        pos = 0
        decoder = json.JSONDecoder()
        while pos < len(text):
            c = text[pos]
            if c in ' \n\r\t':
                pos += 1
                continue
            if c == '"':
                try:
                    val, pos = decoder.raw_decode(text, pos)
                except ValueError:
                    _fail('syntax')
                _text(val)
                tokens.append(('string', val))
            elif c in '():,[]':
                tokens.append((c, c))
                pos += 1
            else:
                match = _WORD.match(text, pos)
                if not match:
                    _fail('syntax')
                val = match.group()
                tokens.append(('word', val))
                pos += len(val)
            if len(tokens) > MAX_INPUT_NODES:
                _fail('input_nodes')
        index = 0

        def take(kind=None, value=None):
            nonlocal index
            if index == len(tokens):
                _fail('syntax')
            token = tokens[index]
            if (kind is not None and token[0] != kind) or (value is not None and token[1] != value):
                _fail('syntax')
            index += 1
            return token[1]

        def peek(value):
            return index < len(tokens) and tokens[index][1] == value and tokens[index][0] != 'string'

        def name():
            val = take('word')
            _ident(val)
            return val

        def term():
            first = name()
            if peek(':'):
                take(':')
                return ['var', first, name()]
            take('[')
            val = take('string')
            take(']')
            return ['const', first, val]

        def expression(minimum=1, depth=0):
            if depth > MAX_DEPTH:
                _fail('depth_limit')
            if index == len(tokens):
                _fail('syntax')
            if tokens[index][0] == 'string':
                left = ['atom', take('string')]
            elif peek('forall') or peek('exists'):
                op = take('word')
                var = name()
                take('word', 'in')
                sort = name()
                take(':')
                left = [op, var, sort, expression(1, depth + 1)]
            elif peek('not'):
                take('word')
                left = ['implies', expression(4, depth + 1), ['false']]
            elif peek('false'):
                take('word')
                left = ['false']
            elif peek('('):
                take('(')
                left = expression(1, depth + 1)
                take(')')
            else:
                symbol = name()
                take('(')
                args = []
                if not peek(')'):
                    args.append(term())
                    while peek(','):
                        take(',')
                        args.append(term())
                take(')')
                left = ['pred', symbol, args]
            while index < len(tokens) and tokens[index][0] == 'word':
                op = tokens[index][1]
                rank = {'implies': 1, 'or': 2, 'and': 3}.get(op, 0)
                if rank < minimum:
                    break
                take('word')
                left = [op, left, expression(rank if op == 'implies' else rank + 1, depth + 1)]
            return left

        formula = expression()
        if index != len(tokens):
            _fail('syntax')
        _scan(formula)
        return formula
    except RecursionError:
        raise FiniteLogicError('depth_limit') from None
