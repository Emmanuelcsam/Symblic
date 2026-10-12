"""The proof builtins: Symblic functions that check proofs a model constructed, within the kernel's step budget.

This module connects the language to the proof checkers. Each builtin charges the kernel's step budget and
calls one checker; none of them searches for a proof:

    proof_parse, proof_render, proof_check, proof_valid           proof terms (symblic.adapters.proof)
    proof_steps_check, proof_steps_valid                          flat natural deduction (proof_steps)
    proof_session_start, proof_session_append, proof_session_frontier   one inference at a time (proof_session)
    proof_session_command, proof_command_frontier                 the same, as text commands (proof_command)
    finite_parse, finite_expand, finite_check, finite_steps_check  finite-domain logic (finite_logic)

Depends on: symblic.kernel.language and the modules above. Used by: symblic.kernel.language.ADAPTERS, which
names these builtins and imports this module on first use.
"""

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction

from symblic.kernel import language as S
from symblic.adapters import proof as P

VERSION = 4


def _wire(value, kernel, node, depth=0, *, allow_none=False):
    kernel.budget.tick(1, node)
    if depth > P.MAX_DEPTH:
        raise S.SymblicError('proof value exceeds the nesting limit', kind='budget')
    if type(value) in (tuple, list):
        if len(value) > P.MAX_NODES:
            raise S.SymblicError('proof list exceeds the node limit', kind='budget')
        return [_wire(item, kernel, node, depth + 1, allow_none=allow_none) for item in value]
    if type(value) is dict:
        if len(value) > P.MAX_NODES:
            raise S.SymblicError('proof record exceeds the node limit', kind='budget')
        return {key: _wire(item, kernel, node, depth + 1, allow_none=allow_none) for key, item in value.items()}
    if value is None and allow_none:
        return None
    if type(value) is Fraction and value.denominator == 1:
        return value.numerator
    if type(value) in (str, int):
        return value
    raise S.SymblicError('proof values require exact lists, records, text and integer version', kind='type')


def proof_check(kernel, node, premises, goal, certificate):
    rows, target, term = _wire([premises, goal, certificate], kernel, node)
    result = P.verify(rows, target, term, tick=lambda: kernel.budget.tick(1, node))
    # Public result uses valid as the language predicate, preserving ok for the
    # standalone verifier's callers. Both attest only to the declared sequent.
    return S.from_json({**result, 'valid': result['ok'], 'scope': 'derivation_from_declared_premises'})


def proof_valid(kernel, node, premises, goal, certificate):
    return proof_check(kernel, node, premises, goal, certificate)['valid']


def proof_steps_check(kernel, node, premises, goal, certificate):
    from symblic.adapters import proof_steps as W
    rows, target, steps = _wire([premises, goal, certificate], kernel, node, allow_none=True)
    result = W.verify(rows, target, steps, tick=lambda: kernel.budget.tick(1, node))
    return S.from_json({**result, 'valid': result['ok'], 'scope': 'derivation_from_declared_premises'})


def proof_steps_valid(kernel, node, premises, goal, certificate):
    return proof_steps_check(kernel, node, premises, goal, certificate)['valid']


def _exact(value, kernel, node, depth=0):
    """Session wire: like _wire, but anything outside the proof wire format is passed on
    unconverted, so the pure session refuses it with a finite code instead of a run error."""
    kernel.budget.tick(1, node)
    kind = type(value)
    if kind in (tuple, list):
        if depth > P.MAX_DEPTH or len(value) > P.MAX_NODES:
            return list(value)
        return [_exact(item, kernel, node, depth + 1) for item in value]
    if kind is dict:
        if depth > P.MAX_DEPTH or len(value) > P.MAX_NODES:
            return dict(value)
        return {key: _exact(item, kernel, node, depth + 1) for key, item in value.items()}
    if kind is Fraction and value.denominator == 1:
        return value.numerator
    return value


def proof_session_start(kernel, node, premises, goal):
    from symblic.adapters import proof_session as R
    values = [_exact(value, kernel, node) for value in (premises, goal)]
    try:
        return S.from_json(R.start(*values, tick=lambda: kernel.budget.tick(1, node)))
    except P.ProofError as error:
        raise S.SymblicError(f'proof session: {error}', kind='check') from None


def proof_session_append(kernel, node, premises, goal, state, candidate):
    # A refused candidate or state is a finite valid=false result; only the host budget raises.
    from symblic.adapters import proof_session as R
    values = [_exact(value, kernel, node) for value in (premises, goal, state, candidate)]
    return S.from_json(R.append(*values, tick=lambda: kernel.budget.tick(1, node)))


def proof_session_frontier(kernel, node, state):
    from symblic.adapters import proof_session as R
    value = _exact(state, kernel, node)
    try:
        return S.from_json(R.frontier(value, tick=lambda: kernel.budget.tick(1, node)))
    except P.ProofError as error:
        raise S.SymblicError(f'proof session: {error}', kind='check') from None


def proof_session_command(kernel, node, premises, goal, state, command):
    from symblic.adapters import proof_command as C
    values = [_exact(value, kernel, node) for value in (premises, goal, state, command)]
    return S.from_json(C.append(*values, tick=lambda: kernel.budget.tick(1, node)))


def proof_command_frontier(kernel, node, state):
    from symblic.adapters import proof_command as C
    try:
        return S.from_json(C.frontier(_exact(state, kernel, node), tick=lambda: kernel.budget.tick(1, node)))
    except P.ProofError as error:
        raise S.SymblicError(f'proof command frontier: {error}', kind='check') from None


def proof_parse(kernel, node, text):
    if not isinstance(text, str):
        raise S.SymblicError('proof_parse needs controlled formal text', kind='type')
    kernel.budget.tick(1 + len(text), node)
    try:
        return S.from_json(P.parse_formula(text))
    except P.ProofError as error:
        raise S.SymblicError(f'proof formula: {error}', kind='syntax') from None


def proof_render(kernel, node, formula):
    value = _wire(formula, kernel, node)
    try:
        result = P.render_formula(value)
    except P.ProofError as error:
        raise S.SymblicError(f'proof formula: {error}', kind='type') from None
    kernel.budget.tick(1 + len(result), node)
    return result


def finite_parse(kernel, node, text):
    from symblic.adapters import finite_logic as F
    if not isinstance(text, str):
        raise S.SymblicError('finite_parse needs controlled formal text', kind='type')
    kernel.budget.tick(1 + len(text), node)
    try:
        return S.from_json(F.parse_formula(text))
    except F.FiniteLogicError as error:
        raise S.SymblicError(f'finite formula: {error}', kind='syntax') from None


def finite_expand(kernel, node, domains, premises, goal):
    from symblic.adapters import finite_logic as F
    values = _wire([domains, premises, goal], kernel, node)
    try:
        return S.from_json(F.expand(*values, tick=lambda n: kernel.budget.tick(n, node)))
    except F.FiniteLogicError as error:
        raise S.SymblicError(f'finite expansion: {error}', kind='check') from None


def finite_check(kernel, node, domains, premises, goal, certificate):
    from symblic.adapters import finite_logic as F
    values = _wire([domains, premises, goal, certificate], kernel, node)
    result = F.verify(*values, tick=lambda n: kernel.budget.tick(n, node))
    return S.from_json({**result, 'valid': result['ok'], 'scope': 'derivation_from_declared_finite_domains_and_premises'})


def finite_steps_check(kernel, node, domains, premises, goal, certificate):
    from symblic.adapters import finite_logic as F
    from symblic.adapters import proof_steps as W
    domains, rows, target, steps = _wire([domains, premises, goal, certificate], kernel, node, allow_none=True)
    result = {'ok': False, 'version': F.VERSION, 'logic': F.LOGIC, 'certificate_format': 'steps',
              'hashes': {}, 'proof_receipt': None, 'conditional_on_premises': True,
              'conditional_on_domains': True, 'consistency': 'not_checked'}
    try:
        expansion = F.expand(domains, rows, target, tick=lambda n: kernel.budget.tick(n, node))
        checked = W.verify(expansion['premises'], expansion['goal'], steps,
                           tick=lambda: kernel.budget.tick(1, node))
        result.update(ok=checked['ok'], hashes=expansion['hashes'], domain_sizes=expansion['domain_sizes'],
                      proof_receipt=checked, expansion_bounds=expansion['expansion_bounds'])
        if checked['ok']:
            result['hashes']['judgment'] = F._hash([F.VERSION, F.LOGIC, 'steps', expansion['hashes']['source'],
                                                  checked['hashes']['judgment']])
        else:
            result['error'] = 'proof_rejected'
    except F.FiniteLogicError as error:
        result['error'] = str(error)
    return S.from_json({**result, 'valid': result['ok'], 'scope': 'derivation_from_declared_finite_domains_and_premises'})


FUNCTIONS = {function.__name__: function for function in
             (proof_check, proof_valid, proof_steps_check, proof_steps_valid, proof_parse, proof_render,
              finite_parse, finite_expand, finite_check, finite_steps_check,
              proof_session_start, proof_session_append, proof_session_frontier,
              proof_session_command, proof_command_frontier)}
