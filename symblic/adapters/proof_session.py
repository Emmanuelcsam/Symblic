"""Incremental proofs: build a natural-deduction proof one checked inference at a time, each in a fresh context.

A session never searches for a proof, completes a formula or invents a premise. The caller holds the premises
and goal; a model proposes exactly one {rule, args, formula} candidate at a time and the host names it s1, s2,
... start() opens a session, append() checks and adds one inference, frontier() says what is proven so far and
what may be referenced next. Every call rechecks the whole stored prefix with
symblic.adapters.proof_steps.check_prefix, the same inference as symblic.adapters.proof_steps.verify, which
alone decides completion. This is how a small model can finish a proof too long for its context.

No I/O, models, stores or registry mutation; inert on import. See docs/reference/INCREMENTAL-PROOFS.md for the
state, frontier and result contracts.

Depends on: symblic.adapters.proof, symblic.adapters.proof_steps. Used by: symblic.adapters.proof_command,
symblic.adapters.proof_adapter and the delegation templates.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json

from symblic.adapters import proof as P
from symblic.adapters import proof_steps as W

VERSION = 1
FORMAT = 'symblic-proof-session'
LOGIC = W.LOGIC
SCOPE = 'derivation_from_declared_premises'
_STATE = frozenset({'version', 'format', 'certificate_version', 'premises', 'goal', 'steps', 'hashes'})
_CANDIDATE = frozenset({'rule', 'args', 'formula'})
CANDIDATE_TYPE = ('Record {rule: one of {' + ', '.join(W.ARITIES) + '}, args: List of Text length 0..5, '
                  'formula: Any}')
_LIMIT = 'The candidate or the proof it would extend exceeds a checker limit.'
HINTS = {
    'candidate_shape': 'Answer with exactly one object holding rule, args and formula.',
    'rule': 'Use one of the listed rule names.',
    'rule_arity': ('Give exactly as many text args as the rule takes: '
                   + ', '.join(f'{rule} {count}' for rule, count in W.ARITIES.items()) + '.'),
    'unexpected_formula': 'Use formula null except for assume, or_left, or_right and false_elim.',
    'formula_shape': 'A formula is ["atom", text], ["false"] or [op, left, right] with op and, or or implies.',
    'unknown_premise': 'A premise arg must be one of the listed premise names.',
    'unknown_or_forward_reference': 'Args must be ids of earlier lines.',
    'and_expected': 'and_left and and_right need a line whose formula is an and.',
    'implies_elim_mismatch': 'implies_elim needs an implication line, then a line whose formula is exactly its left side.',
    'assumption_reference': 'The discharged args of implies_intro and or_elim must be assume lines.',
    'or_expected': 'The first or_elim arg must be a line whose formula is an or.',
    'branch_assumption_collision': 'or_elim needs two different assume lines.',
    'branch_assumption_mismatch': 'Each or_elim assume line must state exactly the matching side of the or.',
    'or_elim_mismatch': 'Both or_elim branch lines must have the same formula.',
    'branch_scope': ("A branch line cannot depend on the other branch's assume line, "
                     'and the or line cannot depend on either.'),
    'false_expected': 'false_elim needs a line whose formula is ["false"].',
    'input_type': 'Use only JSON text, lists, objects and null.',
    'unicode': 'Text must be valid Unicode.',
    'session_complete': 'The proof is already complete; ask for no further inference.',
    'step_limit': 'The proof has reached its step limit.',
    **{code: _LIMIT for code in ('node_limit', 'depth_limit', 'byte_limit', 'text_limit', 'work_limit',
                                 'output_limit', 'cycle')},
}
STATE_HINT = 'The session state does not match these premises and goal; the host must restore or restart it.'
RULES = {
    'task': 'Propose exactly one next inference. The host checks it, names it next_id and adds it to lines.',
    'candidate': {'rule': 'one rule name below', 'args': 'list of text names the rule requires',
                  'formula': 'null except for assume, or_left, or_right and false_elim'},
    'rules': [
        {'rule': 'premise', 'args': ['premise name'], 'formula': None, 'gives': 'that premise'},
        {'rule': 'assume', 'args': [], 'formula': 'A', 'gives': 'A, depending on this new line'},
        {'rule': 'implies_intro', 'args': ['assume line of A', 'line of B'], 'formula': None,
         'gives': 'A implies B, no longer depending on that assume line'},
        {'rule': 'implies_elim', 'args': ['line of A implies B', 'line of exactly A'], 'formula': None, 'gives': 'B'},
        {'rule': 'and_intro', 'args': ['line of A', 'line of B'], 'formula': None, 'gives': 'A and B'},
        {'rule': 'and_left', 'args': ['line of A and B'], 'formula': None, 'gives': 'A'},
        {'rule': 'and_right', 'args': ['line of A and B'], 'formula': None, 'gives': 'B'},
        {'rule': 'or_left', 'args': ['line of A'], 'formula': 'B', 'gives': 'A or B'},
        {'rule': 'or_right', 'args': ['line of B'], 'formula': 'A', 'gives': 'A or B'},
        {'rule': 'or_elim', 'args': ['line of A or B', 'assume line of A', 'line of C', 'assume line of B',
                                   'line of C'],
         'formula': None, 'gives': 'C, no longer depending on either branch assume line'},
        {'rule': 'false_elim', 'args': ['line of false'], 'formula': 'C', 'gives': 'C'},
    ],
    'formulas': [['atom', 'exact proposition text'], ['false'],
                 ['implies', 'A', 'B'], ['and', 'A', 'B'], ['or', 'A', 'B']],
    'semantics': ('Args name earlier line ids; premise args name premises. A line depends on the assume lines '
                  "in its free list. An or_elim branch line cannot depend on the other branch's assume line. "
                  'The proof is complete when a line with an empty free list has exactly the goal formula. '
                  'Not A is A implies false. Never restate the premises, goal or lines. Atoms are opaque; '
                  'premise truth and consistency are not checked.'),
    'unrelated_example': {
        'frontier': {'goal': ['atom', 'An unrelated sample flag'],
                     'premises': {'sample': ['atom', 'An unrelated sample flag']},
                     'lines': [], 'next_id': 's1', 'complete': False, 'steps_left': W.MAX_STEPS},
        'candidate': {'rule': 'premise', 'args': ['sample'], 'formula': None}},
}


def step_id(index):
    """The host-generated ID of the zero-based line index: s1, s2, ..."""
    return 's' + str(index + 1)


def rules():
    """Detached generic task-card rules; they contain no task's proof."""
    return json.loads(json.dumps(RULES))


def candidate_schema():
    """Detached uniform JSON Schema for one candidate; append remains authoritative."""
    return {'type': 'object', 'additionalProperties': False, 'required': ['rule', 'args', 'formula'],
            'properties': {'rule': {'type': 'string', 'enum': list(W.ARITIES)},
                           'args': {'type': 'array', 'maxItems': 5,
                                    'items': {'type': 'string', 'maxLength': W.MAX_TEXT}},
                           'formula': {}}}


def _copy(value):
    # Only called on scanned plain JSON: bounded, acyclic and valid Unicode.
    return json.loads(json.dumps(value, ensure_ascii=False))


def _state(premises, goal, steps):
    """A canonical detached session ledger; only raw steps are stored, never inferences."""
    premises = {name: premises[name] for name in sorted(premises)}
    rows = [{'id': step['id'], 'rule': step['rule'], 'args': step['args'], 'formula': step['formula']}
            for step in steps]
    return _copy({'version': VERSION, 'format': FORMAT, 'certificate_version': W.VERSION,
                  'premises': premises, 'goal': goal, 'steps': rows,
                  'hashes': {'premises': P._hash(premises), 'goal': P._hash(goal)}})


def _load(state, charge):
    """Check an imported envelope, host IDs and sequent hashes; inferences are rechecked separately."""
    if type(state) is not dict or set(state) != _STATE:
        P._fail('state_shape')
    if (type(state['version']) is not int or state['version'] != VERSION
            or type(state['format']) is not str or state['format'] != FORMAT
            or type(state['certificate_version']) is not int or state['certificate_version'] != W.VERSION):
        P._fail('state_version')
    steps, hashes = state['steps'], state['hashes']
    if type(steps) is not list or type(hashes) is not dict or set(hashes) != {'premises', 'goal'}:
        P._fail('state_shape')
    if len(steps) > W.MAX_STEPS:
        P._fail('step_limit')
    for index, step in enumerate(steps):
        if type(step) is not dict or type(step.get('id')) is not str or step['id'] != step_id(index):
            P._fail('state_step_id')
    if type(hashes['premises']) is not str or type(hashes['goal']) is not str:
        P._fail('state_hash')
    W._scan([state['premises'], state['goal']], charge)
    if P._hash(state['premises']) != hashes['premises'] or P._hash(state['goal']) != hashes['goal']:
        P._fail('state_hash')


def _closes(line, goal):
    return not line['free'] and line['formula'] == goal


def _complete(lines, goal):
    """A session ends at its first closed goal line; a ledger continued past it is refused."""
    if any(_closes(line, goal) for line in lines[:-1]):
        P._fail('state_after_complete')
    return bool(lines) and _closes(lines[-1], goal)


def _view(line, order):
    return {'id': line['id'], 'rule': line['rule'], 'formula': line['formula'],
            'free': sorted(line['free'], key=order.__getitem__)}


def _frontier(premises, goal, lines, complete):
    order = {line['id']: index for index, line in enumerate(lines)}
    count = len(lines)
    return {'goal': goal, 'premises': {name: premises[name] for name in sorted(premises)},
            'lines': [_view(line, order) for line in lines],
            'next_id': None if complete or count >= W.MAX_STEPS else step_id(count),
            'complete': complete, 'steps_left': max(W.MAX_STEPS - count, 0)}


def start(premises, goal, *, tick=None):
    """Return an empty session state bound to the caller's sequent.

    Invalid premises or goal raise symblic.adapters.proof.ProofError with a finite code; host budget
    exceptions from tick escape.
    """
    checked = W.check_prefix(premises, goal, [], tick=tick)
    if not checked['ok']:
        P._fail(checked['error'])
    return _state(premises, goal, [])


def _seal(premises, goal, ledger, tick):
    """The flat certificate of a ledger whose last line closes the goal, and verify's receipt."""
    certificate = {'version': W.VERSION, 'steps': ledger['steps'], 'result': ledger['steps'][-1]['id']}
    return certificate, W.verify(premises, goal, certificate, tick=tick)


def frontier(state, *, tick=None):
    """The next inference's task card: rechecked lines, free assumptions, premises and goal.

    The whole stored prefix is rechecked against the state's hash-bound sequent; a complete
    state must also pass verify. An invalid or forged state raises symblic.adapters.proof.ProofError
    with a finite code; host budget exceptions from tick escape.
    """
    try:
        _load(state, W._charger(tick))
    except RecursionError:
        P._fail('depth_limit')
    premises, goal = state['premises'], state['goal']
    checked = W.check_prefix(premises, goal, state['steps'], tick=tick)
    if not checked['ok']:
        P._fail(checked['error'])
    complete = _complete(checked['lines'], goal)
    if complete:
        _, receipt = _seal(premises, goal, state, tick)
        if not receipt['ok']:
            P._fail(receipt['error'])
    return _copy(_frontier(premises, goal, checked['lines'], complete))


def append(premises, goal, state, candidate, *, tick=None):
    """Check one candidate as the next host-numbered line of state under the caller's sequent.

    Always returns a detached result; only host budget exceptions from tick escape. A refused
    candidate returns the unchanged prior state; a refused state returns state None. Completion
    requires a new closed line equal to goal and an accepting symblic.adapters.proof_steps.verify receipt.
    """
    result = {'valid': False, 'complete': False, 'rejected': None, 'error': None, 'hint': None,
              'rejected_step': None, 'step': None, 'line': None, 'state': None, 'frontier': None,
              'next_id': None, 'certificate': None, 'receipt': None, 'checks': 0, 'hashes': {},
              'version': VERSION, 'format': FORMAT, 'logic': LOGIC, 'scope': SCOPE,
              'conditional_on_premises': True, 'consistency': 'not_checked'}
    charge = W._charger(tick)

    def refuse(scope, code, index=None):
        result.update(rejected=scope, error=code, rejected_step=index,
                      hint=STATE_HINT if scope == 'state' else HINTS.get(code))
        return _copy(result)

    def describe(ledger, lines, sealed=None):
        # Fields after the candidate's own describe the state this call returns.
        complete = sealed is not None
        result.update(state=ledger, complete=complete, hashes=ledger['hashes'],
                      frontier=_frontier(premises, goal, lines, complete),
                      certificate=sealed[0] if complete else None, receipt=sealed[1] if complete else None)
        result['next_id'] = result['frontier']['next_id']

    try:
        _load(state, charge)
        W._scan([premises, goal], charge)
        if P._hash(premises) != state['hashes']['premises'] or P._hash(goal) != state['hashes']['goal']:
            P._fail('sequent_mismatch')
    except P.ProofError as exc:
        return refuse('state', str(exc))
    except RecursionError:
        return refuse('state', 'depth_limit')
    steps = state['steps']
    count = len(steps)
    problem = None
    try:
        W._scan(candidate, charge)
        if type(candidate) is not dict or set(candidate) != _CANDIDATE:
            P._fail('candidate_shape')
    except P.ProofError as exc:
        problem = str(exc)
    except RecursionError:
        problem = 'depth_limit'
    lines = proposal = line = None
    if problem is None and count < W.MAX_STEPS:
        # One pass rechecks the stored prefix and the candidate as the next host-numbered line.
        proposal = {'id': step_id(count), 'rule': candidate['rule'], 'args': candidate['args'],
                    'formula': candidate['formula']}
        checked = W.check_prefix(premises, goal, steps + [proposal], tick=tick)
        result['checks'] += checked['checks']
        if checked['ok']:
            lines, line = checked['lines'][:count], checked['lines'][count]
        elif checked.get('rejected_step') is not None and checked['rejected_step'] < count:
            return refuse('state', checked['error'], checked['rejected_step'])
        else:
            problem = checked['error']
    if lines is None:
        # The candidate was refused: recheck the stored prefix alone before returning it.
        checked = W.check_prefix(premises, goal, steps, tick=tick)
        result['checks'] += checked['checks']
        if not checked['ok']:
            return refuse('state', checked['error'], checked.get('rejected_step'))
        lines = checked['lines']
    try:
        complete = _complete(lines, goal)
    except P.ProofError as exc:
        return refuse('state', str(exc))
    prior = _state(premises, goal, steps)
    if complete:
        sealed = _seal(premises, goal, prior, tick)
        if not sealed[1]['ok']:
            return refuse('state', sealed[1]['error'])
        describe(prior, lines, sealed)
        return refuse('session', 'session_complete')
    if count >= W.MAX_STEPS:
        describe(prior, lines)
        return refuse('session', 'step_limit')
    if problem is not None:
        describe(prior, lines)
        return refuse('candidate', problem, count)
    after, ledger, sealed = lines + [line], _state(premises, goal, steps + [proposal]), None
    if _closes(line, goal):
        sealed = _seal(premises, goal, ledger, tick)
        if not sealed[1]['ok']:
            # verify alone decides completion; keep the prior ledger if it refuses at a bound.
            describe(prior, lines)
            return refuse('candidate', sealed[1]['error'], count)
    describe(ledger, after, sealed)
    order = {row['id']: index for index, row in enumerate(after)}
    result.update(valid=True, step=ledger['steps'][-1], line=_view(line, order))
    return _copy(result)
