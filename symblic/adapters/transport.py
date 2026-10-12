"""Earth mover's distance between two finite one-dimensional distributions, computed exactly.

    wasserstein1([{at: 0, mass: 1}, {at: 2, mass: 1}], [{at: 1, mass: 2}])    # a Symblic builtin: 1

The first Wasserstein distance (the minimal "work" needed to move one pile of mass onto the other along the
number line), computed with exact rationals after normalizing each distribution. Each distribution is a list
of {at, mass} records; positions must already share one unit. Useful for comparing two answer distributions
or two histograms a program built.

Only the supplied rational coordinates and masses are interpreted. There are no embeddings, model calls,
semantic similarity or truth guarantees. Import is inert; register(kernel) explicitly adds the one kernel
function, and the language exposes it through a lazy wrapper.

Depends on: symblic.kernel.language, symblic.adapters.variational. Used by: the wasserstein1 builtin.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction
from functools import cmp_to_key

from symblic.kernel import language as S
from symblic.adapters import variational as V

VERSION = 1
ARITHMETIC_VERSION = V.VERSION
MAX_ATOMS = 128                       # Per input, including zero/duplicate atoms.
MAX_BITS = V.MAX_BITS
MAX_WORK = V.MAX_WORK


class TransportError(S.SymblicError):
    """Unsupported finite distribution or exhausted deterministic limit."""


def _compare(a, b, work):
    # Fraction's native ordering can construct unchecked cross-products. Use the
    # bounded arithmetic also for sorting, charging every comparison as work.
    difference = work.sub(a, b)
    return (difference.numerator > 0) - (difference.numerator < 0)


def _distribution(value, max_atoms, work):
    if type(value) not in (list, tuple) or not 1 <= len(value) <= max_atoms:
        raise TransportError(f'distribution must contain 1..{max_atoms} at/mass records', kind='type')
    atoms = []
    for item in value:
        if (type(item) is not dict or len(item) != 2
                or any(type(key) is not str for key in item) or set(item) != {'at', 'mass'}):
            raise TransportError('each atom must have exactly at and mass fields', kind='type')
        at, mass = work.scalar(item['at']), work.scalar(item['mass'])
        if mass.numerator < 0:
            raise TransportError('transport masses must be nonnegative', kind='domain')
        if mass:
            atoms.append((at, mass))
    if not atoms:
        raise TransportError('transport total mass must be positive', kind='domain')

    def compare_atoms(a, b):
        return _compare(a[0], b[0], work) or _compare(a[1], b[1], work)

    # Order by mass as well at duplicate coordinates so summation order does not
    # depend on their input order. Never hash/coerce coordinates to floats.
    atoms.sort(key=cmp_to_key(compare_atoms))
    merged, total = [], Fraction(0)
    for at, mass in atoms:
        total = work.add(total, mass)
        if merged and at == merged[-1][0]:
            merged[-1] = (at, work.add(merged[-1][1], mass))
        else:
            merged.append((at, mass))
    return tuple((at, work.div(mass, total)) for at, mass in merged)


def wasserstein1(left, right, *, max_atoms=MAX_ATOMS, max_bits=MAX_BITS,
                 max_work=MAX_WORK, budget=None, node=None):
    """Return exact W1 after independently normalizing each finite distribution.

    Each input is a list/tuple of dictionaries with exactly 'at' and 'mass';
    values must be native int or canonical Fraction (never bool/float). Masses
    are nonnegative with positive total. Duplicate positions merge; zero masses
    are ignored only after validating their coordinates. Coordinates must already
    use the same numeric scale/unit, which this function cannot infer or check.

    Limits cover input atoms, every rational and preflighted intermediate, plus
    deterministic scalar/arithmetic/comparison work; no partial value is returned
    on exhaustion. An attached kernel Budget is also charged throughout.
    """
    if type(max_atoms) is not int or not 1 <= max_atoms <= MAX_ATOMS:
        raise TransportError(f'max_atoms must be an integer in 1..{MAX_ATOMS}', kind='budget')
    try:
        # Reuse the existing preflight arithmetic without invoking its matrix
        # solver. The dimension argument is a fixed unused constructor bound.
        work = V._Work(1, max_bits, max_work, budget, node)
        lhs = _distribution(left, max_atoms, work)
        rhs = _distribution(right, max_atoms, work)
        events = [(at, mass) for at, mass in lhs] + [(at, -mass) for at, mass in rhs]
        events.sort(key=cmp_to_key(lambda a, b: _compare(a[0], b[0], work)))
        distance, gap = Fraction(0), Fraction(0)
        previous = events[0][0]
        for at, signed_mass in events:
            if at != previous:
                width = work.sub(at, previous)
                distance = work.add(distance, work.mul(abs(gap), width))
            gap = work.add(gap, signed_mass)
            previous = at
        if gap:
            raise TransportError('normalized transport masses do not balance', kind='verification')
        return S.norm_num(distance)
    except V.VariationalError as exc:
        raise TransportError(exc.message.replace('quadratic', 'transport'),
                             exc.line, exc.col, exc.kind) from None


def _wasserstein1(kernel, node, left, right, **limits):
    return wasserstein1(left, right, budget=kernel.budget, node=node, **limits)


FUNCTIONS = {'wasserstein1': _wasserstein1}


def register(kernel):
    """Attach to Kernel.functions idempotently, without replacing other names.

    A first-party core wrapper may carry _symblic_transport='wasserstein1'.
    Merely importing this module never registers anything globally.
    """
    if not isinstance(kernel, S.Kernel):
        raise TransportError('register requires a Symblic Kernel', kind='type')
    for name, function in FUNCTIONS.items():
        if ((name in S.BUILTINS and S.BUILTINS[name] is not function
             and getattr(S.BUILTINS[name], '_symblic_transport', None) != name)
                or (name in kernel.functions and kernel.functions[name] is not function)):
            raise TransportError(f'kernel function {name} already exists', kind='name')
    kernel.functions.update(FUNCTIONS)
    return kernel
