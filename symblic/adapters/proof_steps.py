"""Flat natural-deduction certificates: a proof written as numbered lines, each citing earlier lines.

Where symblic.adapters.proof checks nested proof terms, this module checks the line-by-line form models find
easier to write: each line names a rule, the lines it uses and the formula it concludes. verify() checks a
whole certificate, check_prefix() checks a partial one (used by proof sessions), certificate_schema() gives
the JSON Schema a model is asked to fill.

A model or author constructs every inference; this checker performs no proof search. Premises and goal come
only from the caller. Free assumption identities are tracked per line, so shared nodes cannot leak discharged
hypotheses into a closed result. See docs/reference/PROOF-STEPS.md.

Depends on: symblic.adapters.proof. Used by: symblic.adapters.proof_session, proof_adapter, finite_logic and
the delegation templates.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import re

from symblic.adapters import proof as P

VERSION = 1
FORMAT = 'flat-natural-deduction-dag'
LOGIC = P.LOGIC
MAX_STEPS = 512
MAX_PREMISES = 256
MAX_DEPTH = P.MAX_DEPTH
MAX_NODES = P.MAX_NODES
MAX_BYTES = P.MAX_BYTES
MAX_TEXT = P.MAX_TEXT
MAX_WORK = P.MAX_WORK
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
ARITIES = {'premise': 1, 'assume': 0, 'implies_intro': 2, 'implies_elim': 2,
           'and_intro': 2, 'and_left': 1, 'and_right': 1, 'or_left': 1,
           'or_right': 1, 'or_elim': 5, 'false_elim': 1}
FORMULA_RULES = frozenset({'assume', 'or_left', 'or_right', 'false_elim'})


def _scan(value, charge, *, _stats=None):
    """Bound all expanded occurrences with O(depth) iterator frontier state."""
    def children(item):
        if type(item) is dict:
            # Preserve the old LIFO traversal order without enqueuing siblings.
            for key, child in reversed(item.items()):
                if type(key) is not str:
                    P._fail('input_type')
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
        charge(1)
        nodes += 1
        size += 2
        if nodes > MAX_NODES:
            P._fail('node_limit')
        if depth > MAX_DEPTH:
            P._fail('depth_limit')
        kind = type(item)
        if kind in (list, dict):
            if id(item) in active:
                P._fail('cycle')
            if len(item) > MAX_NODES:
                P._fail('node_limit')
            active.add(id(item))
            stack.append((children(item), depth + 1, id(item)))
            if _stats is not None:
                _stats['max_frontier'] = max(_stats['max_frontier'], len(stack))
        elif kind is str:
            if len(item) > MAX_TEXT:
                P._fail('text_limit')
            try:
                size += len(json.dumps(item, ensure_ascii=False).encode('utf-8'))
            except UnicodeError:
                P._fail('unicode')
        elif item is None:
            size += 4
        elif kind is int and -1 <= item <= 1:
            size += 1
        else:
            P._fail('input_type')
        if size > MAX_BYTES:
            P._fail('byte_limit')
    return nodes


def certificate_schema():
    """Detached uniform JSON Schema for generation; verify remains authoritative."""
    return {'type': 'object', 'additionalProperties': False,
            'required': ['version', 'steps', 'result'], 'properties': {
                'version': {'type': 'integer', 'const': VERSION},
                'steps': {'type': 'array', 'minItems': 1, 'maxItems': MAX_STEPS,
                    'items': {'type': 'object', 'additionalProperties': False,
                        'required': ['id', 'rule', 'args', 'formula'], 'properties': {
                            'id': {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_]{0,63}$'},
                            'rule': {'type': 'string', 'enum': list(ARITIES)},
                            'args': {'type': 'array', 'maxItems': 5,
                                     'items': {'type': 'string', 'maxLength': MAX_TEXT}},
                            'formula': {}}}},
                'result': {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_]{0,63}$'}}}


def _charger(tick):
    """One aggregate work allowance per check; host budget exceptions from tick escape."""
    work = 0

    def charge(amount):
        nonlocal work
        if work + amount > MAX_WORK:
            P._fail('work_limit')
        work += amount
        if tick is not None:
            for _ in range(amount):
                tick()
    return charge


def _sequent(premises, goal):
    """The caller-held contract: named premise formulas and a goal formula."""
    if type(premises) is not dict:
        P._fail('premises_shape')
    if len(premises) > MAX_PREMISES:
        P._fail('premise_limit')
    for name, formula in premises.items():
        P._name(name)
        P._formula(formula)
    P._formula(goal)


def _infer(premises, steps, charge, receipt):
    """Infer each supplied line in order, sharing one checker between verify and check_prefix.

    Each line records its inferred formula, free assumption IDs and used premises.
    receipt counts checked lines and names the zero-based line being rejected.
    """
    lines = {}
    for index, step in enumerate(steps):
        receipt['rejected_step'] = index
        if type(step) is not dict or set(step) != {'id', 'rule', 'args', 'formula'}:
            P._fail('step_shape')
        ident, rule, args, declared = (step[key] for key in ('id', 'rule', 'args', 'formula'))
        if type(ident) is not str or not _ID.fullmatch(ident):
            P._fail('step_id')
        if ident in lines:
            P._fail('duplicate_step')
        if type(rule) is not str or rule not in ARITIES:
            P._fail('rule')
        if type(args) is not list or len(args) != ARITIES[rule] or any(type(arg) is not str for arg in args):
            P._fail('rule_arity')
        if rule in FORMULA_RULES:
            P._formula(declared)
        elif declared is not None:
            P._fail('unexpected_formula')
        receipt['checks'] += 1
        if rule == 'premise':
            if args[0] not in premises:
                P._fail('unknown_premise')
            result, free, used = premises[args[0]], frozenset(), frozenset(args)
        elif rule == 'assume':
            result, free, used = declared, frozenset({ident}), frozenset()
        else:
            if any(arg not in lines for arg in args):
                P._fail('unknown_or_forward_reference')
            refs = [lines[arg] for arg in args]
            charge(1 + sum(len(row['free']) + len(row['used']) for row in refs))
            used = frozenset().union(*(row['used'] for row in refs))
            free = frozenset().union(*(row['free'] for row in refs))
            first = refs[0]['formula']
            if rule == 'and_intro':
                result = ['and', first, refs[1]['formula']]
            elif rule in ('and_left', 'and_right'):
                if first[0] != 'and':
                    P._fail('and_expected')
                result = first[1 if rule == 'and_left' else 2]
            elif rule == 'implies_elim':
                if first[0] != 'implies' or first[1] != refs[1]['formula']:
                    P._fail('implies_elim_mismatch')
                result = first[2]
            elif rule == 'implies_intro':
                if refs[0]['rule'] != 'assume':
                    P._fail('assumption_reference')
                result = ['implies', first, refs[1]['formula']]
                free = refs[1]['free'] - {args[0]}
                used = refs[1]['used']
            elif rule in ('or_left', 'or_right'):
                result = ['or', first, declared] if rule == 'or_left' else ['or', declared, first]
            elif rule == 'or_elim':
                if first[0] != 'or':
                    P._fail('or_expected')
                if refs[1]['rule'] != 'assume' or refs[3]['rule'] != 'assume':
                    P._fail('assumption_reference')
                if args[1] == args[3]:
                    P._fail('branch_assumption_collision')
                if refs[1]['formula'] != first[1] or refs[3]['formula'] != first[2]:
                    P._fail('branch_assumption_mismatch')
                if refs[2]['formula'] != refs[4]['formula']:
                    P._fail('or_elim_mismatch')
                if (args[1] in refs[0]['free'] or args[3] in refs[0]['free']
                        or args[1] in refs[4]['free'] or args[3] in refs[2]['free']):
                    P._fail('branch_scope')
                result = refs[2]['formula']
                free = refs[0]['free'] | (refs[2]['free'] - {args[1]}) | (refs[4]['free'] - {args[3]})
                used = refs[0]['used'] | refs[2]['used'] | refs[4]['used']
            else:  # false_elim
                if first != ['false']:
                    P._fail('false_expected')
                result = declared
        # A tiny DAG can infer exponentially large formulas. Charge expanded
        # occurrences, depth and bytes before preserving each inferred line.
        _scan(result, charge)
        lines[ident] = {'rule': rule, 'formula': result, 'free': free, 'used': used}
    receipt.pop('rejected_step', None)
    return lines


def check_prefix(premises, goal, steps, *, tick=None, max_bytes=None):
    """Check an ordered list of zero or more lines with verify's preflight and inference.

    No result is selected: free assumptions and the goal are reported, never required.
    A success receipt lists every line's id, rule, inferred formula and sorted free
    assumption IDs as detached JSON. A line table whose compact JSON exceeds max_bytes
    (default MAX_BYTES) is refused as output_limit. Host budget exceptions from tick escape.
    """
    limit = MAX_BYTES if max_bytes is None else max_bytes
    receipt = {'ok': False, 'version': VERSION, 'format': FORMAT, 'logic': LOGIC, 'lines': [],
               'checks': 0, 'conditional_on_premises': True, 'consistency': 'not_checked'}
    charge = _charger(tick)
    try:
        _scan([premises, goal, steps], charge)
        _sequent(premises, goal)
        if type(steps) is not list or len(steps) > MAX_STEPS:
            P._fail('step_limit')
        lines, size = [], 1
        for ident, row in _infer(premises, steps, charge, receipt).items():
            # Each formula was bounded when inferred; stop expanding shared DAG
            # structure as soon as the detached table would exceed the limit.
            text = P._json({'id': ident, 'rule': row['rule'], 'formula': row['formula'],
                            'free': sorted(row['free'])})
            size += len(text.encode('utf-8')) + 1
            if size > limit:
                P._fail('output_limit')
            lines.append(json.loads(text))
        receipt.update(ok=True, lines=lines)
    except P.ProofError as exc:
        receipt['error'] = str(exc)
    except RecursionError:
        receipt['error'] = 'depth_limit'
    return receipt


def verify(premises, goal, certificate, *, tick=None):
    """Infer each supplied line and require a closed root matching the caller's goal.

    tick is a no-argument host budget callback, as in symblic.adapters.proof.verify. It is
    called during bounded preflight and inference. Host budget exceptions escape;
    certificate errors return a detached ok=False receipt with a finite error code.
    """
    receipt = {'ok': False, 'version': VERSION, 'format': FORMAT, 'logic': LOGIC,
               'conclusion': None, 'used_premises': [], 'open_assumptions': [],
               'checks': 0, 'hashes': {}, 'conditional_on_premises': True,
               'consistency': 'not_checked'}
    charge = _charger(tick)
    try:
        _scan([premises, goal, certificate], charge)
        _sequent(premises, goal)
        if type(certificate) is not dict or set(certificate) != {'version', 'steps', 'result'}:
            P._fail('certificate_shape')
        if type(certificate['version']) is not int or certificate['version'] != VERSION:
            P._fail('version')
        steps = certificate['steps']
        if type(steps) is not list or not 1 <= len(steps) <= MAX_STEPS:
            P._fail('step_limit')
        root = certificate['result']
        if type(root) is not str or not _ID.fullmatch(root):
            P._fail('step_id')
        lines = _infer(premises, steps, charge, receipt)
        if root not in lines:
            P._fail('unknown_result')
        result = lines[root]
        receipt['open_assumptions'] = sorted(result['free'])
        if result['free']:
            P._fail('open_assumptions')
        if result['formula'] != goal:
            P._fail('goal_mismatch')
        receipt.update(ok=True, conclusion=json.loads(P._json(result['formula'])),
                       used_premises=sorted(result['used']),
                       hashes={'premises': P._hash(premises), 'goal': P._hash(goal),
                               'certificate': P._hash(certificate),
                               'judgment': P._hash([VERSION, FORMAT, LOGIC, premises, goal, certificate])})
    except P.ProofError as exc:
        receipt['error'] = str(exc)
    except RecursionError:
        receipt['error'] = 'depth_limit'
    return receipt
