"""Proof-term checking for intuitionistic propositional logic: the trusted core of the proof adapters.

A proof term is a small tree such as ['implies_elim', ['premise', 'rule'], ['premise', 'human']]. verify()
checks that a term proves a goal from named premises, rule by rule; parse_formula() and render_formula() read
and write the controlled formula syntax ("A" and "B", "A" implies "B", not "A", ...). A model may construct
the term; only this checker decides whether it is valid.

No proof search, I/O, models, registry mutation or non-standard-library dependencies. See
docs/reference/PROOF-TERMS.md for the wire format and the trust boundary.

Depends on: the standard library only. Used by: every other proof module and the proof builtins.
"""

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
import hashlib
import json

VERSION = 1
LOGIC = 'intuitionistic-propositional-logic'
MAX_DEPTH = 64
MAX_NODES = 20000
MAX_BYTES = 262144
MAX_WORK = 200000
MAX_TEXT = 4096


class ProofError(ValueError):
    """A finite diagnostic code; never includes caller-controlled text."""


def _fail(code):
    raise ProofError(code)


def _scan(value, tick=None, *, _stats=None):
    """Bound all expanded occurrences with O(depth) iterator frontier state."""
    def children(item):
        if type(item) is dict:
            # Preserve the old LIFO traversal order without enqueuing siblings.
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
    if _stats is not None:
        _stats['max_frontier'] = 1
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
            tick()
        nodes += 1
        size += 2
        if nodes > MAX_NODES:
            _fail('node_limit')
        if depth > MAX_DEPTH:
            _fail('depth_limit')
        kind = type(item)
        if kind in (list, dict):
            if id(item) in active:
                _fail('cycle')
            if len(item) > MAX_NODES:
                _fail('node_limit')
            active.add(id(item))
            stack.append((children(item), depth + 1, id(item)))
            if _stats is not None:
                _stats['max_frontier'] = max(_stats['max_frontier'], len(stack))
        elif kind is str:
            if len(item) > MAX_TEXT:
                _fail('text_limit')
            try:
                size += len(json.dumps(item, ensure_ascii=False).encode('utf-8'))
            except UnicodeError:
                _fail('unicode')
        elif kind is int and -1 <= item <= 1:
            size += 1
        else:
            _fail('input_type')
        if size > MAX_BYTES:
            _fail('byte_limit')
    return nodes


def _formula(value):
    if type(value) is not list or not value or type(value[0]) is not str:
        _fail('formula_shape')
    op = value[0]
    if op == 'atom' and len(value) == 2 and type(value[1]) is str:
        return
    if op == 'false' and len(value) == 1:
        return
    if op in ('implies', 'and', 'or') and len(value) == 3:
        _formula(value[1])
        _formula(value[2])
        return
    _fail('formula_shape')


def _name(value):
    if type(value) is not str or not value:
        _fail('name')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def verify(premises, goal, certificate, *, tick=None):
    """Return a detached receipt, with ok=False and a stable error on rejection.

    Only the caller supplies premises and goal. A certificate has exactly
    version/proof. Checks counts inference nodes, not a semantic confidence score.
    """
    receipt = dict(ok=False, version=VERSION, logic=LOGIC, conclusion=None,
                   used_premises=[], open_assumptions=[], checks=0, hashes={},
                   conditional_on_premises=True, consistency='not_checked')
    try:
        work = _scan([premises, goal, certificate], tick)
        if type(premises) is not dict:
            _fail('premises_shape')
        for name, formula in premises.items():
            _name(name)
            _formula(formula)
        _formula(goal)
        if type(certificate) is not dict or set(certificate) != {'version', 'proof'}:
            _fail('certificate_shape')
        if type(certificate['version']) is not int or certificate['version'] != VERSION:
            _fail('version')
        used = set()

        def infer(term, scope):
            nonlocal work
            if type(term) is not list or not term or type(term[0]) is not str:
                _fail('term_shape')
            op = term[0]
            arities = {'premise': 2, 'hypothesis': 2, 'implies_intro': 4,
                       'implies_elim': 3, 'and_intro': 3, 'and_left': 2,
                       'and_right': 2, 'or_left': 3, 'or_right': 3,
                       'or_elim': 6, 'false_elim': 3}
            if op not in arities or len(term) != arities[op]:
                _fail('term_shape')
            receipt['checks'] += 1

            def bind(name, formula):
                _name(name)
                if name in premises or name in scope:
                    _fail('shadowing')
                return dict(scope, **{name: formula})

            if op in ('premise', 'hypothesis'):
                _name(term[1])
                source = premises if op == 'premise' else scope
                if term[1] not in source:
                    _fail('unknown_' + op)
                result = source[term[1]]
                if op == 'premise':
                    used.add(term[1])
            elif op == 'implies_intro':
                _formula(term[2])
                result = ['implies', term[2], infer(term[3], bind(term[1], term[2]))]
            elif op in ('implies_elim', 'and_intro'):
                left, right = infer(term[1], scope), infer(term[2], scope)
                if op == 'and_intro':
                    result = ['and', left, right]
                else:
                    if left[0] != 'implies' or left[1] != right:
                        _fail('implies_elim_mismatch')
                    result = left[2]
            elif op in ('and_left', 'and_right'):
                pair = infer(term[1], scope)
                if pair[0] != 'and':
                    _fail('and_expected')
                result = pair[1 if op == 'and_left' else 2]
            elif op in ('or_left', 'or_right'):
                value = infer(term[1], scope)
                _formula(term[2])
                result = ['or', value, term[2]] if op == 'or_left' else ['or', term[2], value]
            elif op == 'or_elim':
                value = infer(term[1], scope)
                if value[0] != 'or':
                    _fail('or_expected')
                _name(term[2])
                _name(term[4])
                if term[2] == term[4]:
                    _fail('shadowing')
                left = infer(term[3], bind(term[2], value[1]))
                right = infer(term[5], bind(term[4], value[2]))
                if left != right:
                    _fail('or_elim_mismatch')
                result = left
            else:  # false_elim
                if infer(term[1], scope) != ['false']:
                    _fail('false_expected')
                _formula(term[2])
                result = term[2]
            # Inferred formulas can be much larger/deeper than their proof terms.
            # Charge their expanded size, preventing shared subtrees hiding growth.
            work += _scan(result, tick)
            if work > MAX_WORK:
                _fail('work_limit')
            return result

        conclusion = infer(certificate['proof'], {})
        if conclusion != goal:
            _fail('goal_mismatch')
        receipt.update(ok=True, conclusion=json.loads(_json(conclusion)),
                       used_premises=sorted(used),
                       hashes={'premises': _hash(premises), 'goal': _hash(goal),
                               'certificate': _hash(certificate),
                               'judgment': _hash([VERSION, LOGIC, premises, goal, certificate])})
    except ProofError as exc:
        receipt['error'] = str(exc)
    except RecursionError:
        receipt['error'] = 'depth_limit'
    return receipt


def parse_formula(text):
    """Parse JSON-quoted atoms, false, not, and, or, implies and parentheses.

    Highest precedence: not, and, or, implies (right associative). Other binary
    operators associate left. Invalid text raises ProofError, never RecursionError.
    """
    try:
        if type(text) is not str:
            _fail('text_type')
        if len(text) > MAX_BYTES:
            _fail('byte_limit')
        try:
            if len(text.encode('utf-8')) > MAX_BYTES:
                _fail('byte_limit')
        except UnicodeError:
            _fail('unicode')
        tokens = []
        decoder = json.JSONDecoder()
        pos = 0
        while pos < len(text):
            char = text[pos]
            if char.isspace():
                pos += 1
                continue
            if char == '"':
                try:
                    atom, end = decoder.raw_decode(text, pos)
                except ValueError:
                    _fail('syntax')
                tokens.append(['atom', atom])
                pos = end
            elif char in '()':
                tokens.append(char)
                pos += 1
            else:
                end = pos
                while end < len(text) and text[end].isalpha():
                    end += 1
                word = text[pos:end]
                if word not in ('not', 'and', 'or', 'implies', 'false'):
                    _fail('syntax')
                tokens.append(word)
                pos = end
            if len(tokens) > MAX_NODES:
                _fail('node_limit')
        index = 0
        precedence = {'implies': 1, 'or': 2, 'and': 3}

        def expression(minimum=1, depth=0):
            nonlocal index
            if depth > MAX_DEPTH:
                _fail('depth_limit')
            if index == len(tokens):
                _fail('syntax')
            token = tokens[index]
            index += 1
            if type(token) is list:
                left = token
            elif token == 'false':
                left = ['false']
            elif token == 'not':
                left = ['implies', expression(4, depth + 1), ['false']]
            elif token == '(':
                left = expression(1, depth + 1)
                if index == len(tokens) or tokens[index] != ')':
                    _fail('syntax')
                index += 1
            else:
                _fail('syntax')
            while index < len(tokens) and type(tokens[index]) is str:
                op = tokens[index]
                rank = precedence.get(op, 0)
                if rank < minimum:
                    break
                index += 1
                right = expression(rank if op == 'implies' else rank + 1, depth + 1)
                left = [op, left, right]
            return left

        result = expression()
        if index != len(tokens):
            _fail('syntax')
        _scan(result)
        _formula(result)
        return result
    except RecursionError:
        raise ProofError('depth_limit') from None


def render_formula(formula):
    """Render unambiguous human-readable text; parse(render(f)) == f."""
    try:
        _scan(formula)
        _formula(formula)

        def render(value):
            if value[0] == 'atom':
                return json.dumps(value[1], ensure_ascii=False)
            if value[0] == 'false':
                return 'false'
            return '(' + render(value[1]) + ' ' + value[0] + ' ' + render(value[2]) + ')'

        text = render(formula)
        if len(text.encode('utf-8')) > MAX_BYTES:
            _fail('byte_limit')
        return text
    except RecursionError:
        raise ProofError('depth_limit') from None
