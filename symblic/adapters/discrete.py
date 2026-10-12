"""Exact ground states of a small Ising model, by exhaustive enumeration (the ising_minimize and ising_energy builtins).

Contract (adapter version 1). No floating point, sampling, annealing, heuristic, model, service or
I/O. Import is inert: the host registers FUNCTIONS as kernel builtins.

Energy of a state s in {-1, +1}^n, each unordered pair of spins counted once:

    E(s) = - sum_i h[i]*s[i] - sum_{i<j} J[i][j]*s[i]*s[j]

ising_minimize(h, J) evaluates every one of the 2^n states and returns the record
    {energy:     the exact minimum (an integer or a fraction),
     degeneracy: how many states attain it,
     states:     ground states, each a list of -1/+1 by spin, in lexicographic order with -1 < +1;
                 at most MAX_STATES = 16 of them: the first 16 in that order,
     truncated:  true when degeneracy > MAX_STATES (states then lists only the first 16),
     spins:      n,
     method:     "exhaustive"}.
ising_energy(h, J, s) returns the exact energy of one state s: a list of n values, each -1 or 1.

Domain, checked before any work (positions in messages count from 1, as Symblic indexes):
- h is a list of n exact numbers (int or Fraction) with 1 <= n <= MAX_SPINS = 16; J is a list of n
  rows of n exact numbers, exactly symmetric with a zero diagonal. Kernel lists arrive as tuples;
  Python lists are accepted too. Both builtins accept exactly the same (h, J).
- Kind 'type': a float, bool, Decimal, text, set, record or noncanonical Fraction; a wrong shape or
  length; n = 0. Kind 'budget': n > MAX_SPINS; a numerator or denominator above MAX_BITS bits; a
  common denominator of h and J above MAX_BITS bits; a coefficient above MAX_BITS bits once
  multiplied by that common denominator. Kind 'check': J not exactly symmetric; a non-zero diagonal
  entry; a spin that is not -1 or 1. Kind 'runtime': the internal audit below failed (a defect).

Method: every coefficient is multiplied by the common denominator of h and J, giving integers of at
most MAX_BITS bits (the walk's sums are larger but bounded: at most 136 times a scaled coefficient at 16
spins, 4104 bits; a refused input can build one temporary product of at most 2 * MAX_BITS bits before the
check). A Gray-code walk visits all 2^n states, flipping one spin per step and updating
the energy and every local field with O(n) integer additions. Every reported state, and the walk's
final state, is then evaluated again term by term with exact fractions and must agree (else
'runtime'). ising_energy uses only the term-by-term evaluation.

Budget (kernel steps, each charged before the work it pays for): ising_minimize charges n + n*n
before reading the coefficients and 2^n before the walk; ising_energy charges 2n + n*n before
reading its inputs and n + n(n-1)/2 before evaluating.

What a result does not establish: the minimum is exact for the supplied numbers only. Ground states
are in general not unique (with h = 0 their count is even: flipping every spin keeps the energy),
which is why the count is reported. The cost doubles with every spin, so 16 is a hard limit and this
is not a method for large problems. That h and J encode some real problem is the author's claim,
not checked here.

Depends on: symblic.kernel.language. Used by: the ising_* builtins (symblic.kernel.language.ADAPTERS imports this
module on first use). See docs/reference/DISCRETE.md.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from bisect import insort
from fractions import Fraction
from math import gcd

from symblic.kernel import language as S

VERSION = 1
METHOD = 'exhaustive'
MAX_SPINS = 16
MAX_STATES = 16
MAX_BITS = 4096   # every numerator and denominator, the common denominator, every scaled coefficient
FIELDS = ('energy', 'degeneracy', 'states', 'truncated', 'spins', 'method')


class DiscreteError(S.SymblicError):
    """An input outside the stated domain, an exceeded limit, or a failed internal audit."""


def _budget(budget):
    if budget is not None and not isinstance(budget, S.Budget):
        raise DiscreteError('budget must be a Symblic Budget', kind='type')
    return budget


def _charge(budget, steps, node):
    if budget is not None:
        budget.tick(steps, node)


def _is_list(value):
    # Kernel lists are tuples; Python callers may pass lists. A set has no order, so it is not a list.
    return type(value) in (list, tuple)


def _shape(h, J):
    """The number of spins, from lengths alone: no entry is read, so this costs O(n)."""
    if not _is_list(h):
        raise DiscreteError(f'h must be a list of numbers, one per spin, not {S.type_name(h)}', kind='type')
    n = len(h)
    if n == 0:
        raise DiscreteError('h must have at least one entry (one per spin)', kind='type')
    if n > MAX_SPINS:
        raise DiscreteError(f'at most {MAX_SPINS} spins (h has {n} entries): the work doubles with every spin',
                            kind='budget')
    if not _is_list(J) or len(J) != n or any(not _is_list(row) or len(row) != n for row in J):
        raise DiscreteError(f'J must be a {n} x {n} matrix: a list of {n} rows of {n} numbers', kind='type')
    return n


def _exact(value, label):
    """One exact rational as a Fraction. Bools, floats, Decimals, subclasses and corrupted or
    noncanonical Fraction internals are refused; nothing is coerced or approximated."""
    if type(value) not in (int, Fraction):
        raise DiscreteError(f'{label} must be an exact number (an integer or a fraction), not {S.type_name(value)}',
                            kind='type')
    numerator = value if type(value) is int else value.numerator
    denominator = 1 if type(value) is int else value.denominator
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise DiscreteError(f'{label} must be a canonical fraction', kind='type')
    # Sizes before gcd, so an oversized number costs nothing to refuse.
    if numerator.bit_length() > MAX_BITS or denominator.bit_length() > MAX_BITS:
        raise DiscreteError(f'{label} has more than {MAX_BITS} bits', kind='budget')
    if gcd(numerator, denominator) != 1:
        raise DiscreteError(f'{label} must be a canonical fraction', kind='type')
    return Fraction(numerator, denominator)


def _scaled(value, common, label):
    scaled = value.numerator * (common // value.denominator)
    if scaled.bit_length() > MAX_BITS:
        raise DiscreteError(f'{label} times the common denominator of h and J has more than {MAX_BITS} bits',
                            kind='budget')
    return scaled


def _entries(h, J, n):
    """Read and check every coefficient, then clear denominators.

    Returns (fields, couplings, common, scaled_fields, scaled_couplings): the Fractions of h and J,
    their common denominator, and the integers h*common and J*common (J as a full n x n tuple).
    """
    fields = tuple(_exact(v, f'h[{i + 1}]') for i, v in enumerate(h))
    couplings = tuple(tuple(_exact(v, f'J[{i + 1}][{j + 1}]') for j, v in enumerate(row))
                      for i, row in enumerate(J))
    for i in range(n):
        if couplings[i][i]:
            raise DiscreteError(f'J must have a zero diagonal: J[{i + 1}][{i + 1}] is not 0', kind='check')
        for j in range(i + 1, n):
            if couplings[i][j] != couplings[j][i]:
                raise DiscreteError(f'J must be symmetric: J[{i + 1}][{j + 1}] and J[{j + 1}][{i + 1}] differ',
                                    kind='check')
    common = 1
    for value in fields + tuple(couplings[i][j] for i in range(n) for j in range(i + 1, n)):
        # Both factors have at most MAX_BITS bits, so no product here exceeds 2 * MAX_BITS bits.
        common = common // gcd(common, value.denominator) * value.denominator
        if common.bit_length() > MAX_BITS:
            raise DiscreteError(f'the common denominator of h and J has more than {MAX_BITS} bits', kind='budget')
    scaled_fields = tuple(_scaled(v, common, f'h[{i + 1}]') for i, v in enumerate(fields))
    upper = {(i, j): _scaled(couplings[i][j], common, f'J[{i + 1}][{j + 1}]')
             for i in range(n) for j in range(i + 1, n)}
    scaled_couplings = tuple(tuple(0 if i == j else upper[min(i, j), max(i, j)] for j in range(n))
                             for i in range(n))
    return fields, couplings, common, scaled_fields, scaled_couplings


def _spin(value, label):
    if type(value) not in (int, Fraction):
        raise DiscreteError(f'{label} must be -1 or 1, not {S.type_name(value)}', kind='type')
    if _exact(value, label) not in (-1, 1):
        raise DiscreteError(f'{label} must be -1 or 1', kind='check')
    return int(value)


def _direct_energy(fields, couplings, state):
    """E(s) term by term with exact fractions; independent of the scaled integers and of the walk."""
    n = len(state)
    total = Fraction(0)
    for i in range(n):
        total -= fields[i] * state[i]
        for j in range(i + 1, n):
            total -= couplings[i][j] * (state[i] * state[j])
    return total


def _decode(code, n):
    """Bit n-1-i of a code is set when spin i is +1, so numeric order is lexicographic order."""
    return tuple(1 if (code >> (n - 1 - i)) & 1 else -1 for i in range(n))


def _walk(n, scaled_fields, scaled_couplings):
    """All 2^n states in Gray-code order, on integers (the energy here is E times the common denominator).

    Starts at all spins -1 (code 0); step t flips the spin of code bit k, the lowest set bit of t.
    With local fields f_i = h_i + sum_{j != i} J_ij s_j, flipping spin i from s changes E by 2*s*f_i
    and every f_j by -2*s*J_ij; the walk keeps F_i = 2*f_i so a step is additions only.
    Returns (minimum, how many states attain it, the smallest MAX_STATES codes attaining it in
    ascending order, the final code, the final energy).
    """
    spins = [-1] * n
    energy = sum(scaled_fields) - sum(scaled_couplings[i][j] for i in range(n) for j in range(i + 1, n))
    local = [2 * (scaled_fields[i] - sum(scaled_couplings[i][j] for j in range(n) if j != i)) for i in range(n)]
    neighbours = tuple(tuple((j, 4 * scaled_couplings[i][j]) for j in range(n) if j != i and scaled_couplings[i][j])
                       for i in range(n))
    best, count, codes, code = energy, 1, [0], 0
    for step in range(1, 1 << n):
        bit = (step & -step).bit_length() - 1
        i = n - 1 - bit
        code ^= 1 << bit
        if spins[i] < 0:
            energy -= local[i]
            spins[i] = 1
            for j, weight in neighbours[i]:
                local[j] += weight
        else:
            energy += local[i]
            spins[i] = -1
            for j, weight in neighbours[i]:
                local[j] -= weight
        if energy < best:
            best, count, codes = energy, 1, [code]
        elif energy == best:
            count += 1
            if len(codes) < MAX_STATES or code < codes[-1]:
                insort(codes, code)
                del codes[MAX_STATES:]
    return best, count, codes, code, energy


def minimize_ising(h, J, *, budget=None, node=None):
    """The exact minimum of E over all 2^n states, its degeneracy and the first ground states.

    Raises DiscreteError for inputs outside the domain or limits; never returns a partial or
    approximate answer. An attached kernel Budget is charged before each part of the work.
    """
    budget = _budget(budget)
    n = _shape(h, J)
    _charge(budget, n + n * n, node)
    fields, couplings, common, scaled_fields, scaled_couplings = _entries(h, J, n)
    _charge(budget, 1 << n, node)
    best, count, codes, final_code, final_energy = _walk(n, scaled_fields, scaled_couplings)
    energy = Fraction(best, common)
    states = tuple(_decode(code, n) for code in codes)
    # A defect in the incremental update must not reach a result: every reported state and the walk's
    # final state are evaluated again term by term.
    if (_direct_energy(fields, couplings, _decode(final_code, n)) != Fraction(final_energy, common)
            or any(_direct_energy(fields, couplings, state) != energy for state in states)):
        raise DiscreteError('internal audit failed: the walk and the direct evaluation disagree', kind='runtime')
    return {'energy': S.norm_num(energy), 'degeneracy': count, 'states': states,
            'truncated': count > len(states), 'spins': n, 'method': METHOD}


def state_energy(h, J, s, *, budget=None, node=None):
    """The exact energy of one state s (n values, each -1 or 1), for (h, J) validated as above."""
    budget = _budget(budget)
    n = _shape(h, J)
    if not _is_list(s) or len(s) != n:
        raise DiscreteError(f's must be a list of {n} spins, each -1 or 1', kind='type')
    _charge(budget, 2 * n + n * n, node)
    fields, couplings, *_ = _entries(h, J, n)
    state = tuple(_spin(v, f's[{i + 1}]') for i, v in enumerate(s))
    _charge(budget, n + n * (n - 1) // 2, node)
    return S.norm_num(_direct_energy(fields, couplings, state))


def _kernel_budget(kernel, name):
    budget = getattr(kernel, 'budget', None)
    if not isinstance(budget, S.Budget):
        raise DiscreteError(f'{name} needs a Symblic kernel with a step budget', kind='type')
    return budget


def _ising_minimize(kernel, node, h, J):
    return minimize_ising(h, J, budget=_kernel_budget(kernel, 'ising_minimize'), node=node)


def _ising_energy(kernel, node, h, J, s):
    return state_energy(h, J, s, budget=_kernel_budget(kernel, 'ising_energy'), node=node)


FUNCTIONS = {'ising_minimize': _ising_minimize, 'ising_energy': _ising_energy}
