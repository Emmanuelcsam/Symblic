"""Least-change reconciliation: the smallest exact adjustment of numbers so that they satisfy linear constraints.

    reconcile(x, C, d, weights=None)    # a Symblic builtin

Typical use: a model reads figures from a document (a table whose rows must add up to its total) and they
disagree slightly; reconcile returns the closest values (in the weighted least-squares sense) that satisfy the
constraints exactly. For positive diagonal weights W and independent rows of C it finds the unique y
minimizing sum_i W[i]*(y[i]-x[i])**2 subject to C*y=d, in exact rational arithmetic. Both feasibility and the
KKT stationarity conditions are checked before returning.

The returned vector is a repair of the supplied values, never a measurement or a claim of semantic truth.
Import is inert; FUNCTIONS exposes only the reconcile(kernel, node, x, C, d, weights=None) hook. See
docs/reference/PROJECTION.md.

Depends on: symblic.kernel.language. Used by: the reconcile builtin (symblic.kernel.language.ADAPTERS).
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction

from symblic.kernel import language as S
from symblic.adapters import variational as V

VERSION = 1
MAX_DIMENSION = 32
MAX_BITS = 4096
MAX_WORK = 200_000
METHOD = 'exact-affine-projection'


class ProjectionError(S.SymblicError):
    """Invalid affine problem, failed check, or exhausted deterministic limit."""


def _length(value, size, label):
    if type(value) not in (list, tuple) or len(value) != size:
        raise ProjectionError(f'{label} must contain exactly {size} entries', kind='type')


def _problem(x, C, d, weights, work):
    if type(x) not in (list, tuple) or not 1 <= len(x) <= work.dimension:
        raise ProjectionError(f'x must contain 1..{work.dimension} entries', kind='type')
    n = len(x)
    if type(C) not in (list, tuple) or not 1 <= len(C) <= n:
        raise ProjectionError('C must contain 1..len(x) constraint rows', kind='type')
    for row in C:
        _length(row, n, 'C row')
    _length(d, len(C), 'd')
    if weights is None:
        weights = (1,) * n
    _length(weights, n, 'weights')
    # Validate all shapes before traversing scalar values or assembling matrices.
    x = tuple(work.scalar(v) for v in x)
    C = tuple(tuple(work.scalar(v) for v in row) for row in C)
    d = tuple(work.scalar(v) for v in d)
    weights = tuple(work.scalar(v) for v in weights)
    if any(weight.numerator <= 0 for weight in weights):
        raise ProjectionError('weights must be strictly positive', kind='check')
    return x, C, d, weights


def _dot(a, b, work):
    total = Fraction(0)
    for left, right in zip(a, b):
        total = work.add(total, work.mul(left, right))
    return total


def _solve(matrix, rhs, work):
    """Exact Gaussian elimination, first nonzero pivot row in original order."""
    size = len(rhs)
    rows = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for column in range(size):
        pivot = None
        for row in range(column, size):
            work.tick()
            if rows[row][column]:
                pivot = row
                break
        if pivot is None:
            raise ProjectionError('C must have independent rows', kind='check')
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for row in range(column + 1, size):
            work.tick()
            if not rows[row][column]:
                continue
            ratio = work.div(rows[row][column], rows[column][column])
            for j in range(column + 1, size + 1):
                rows[row][j] = work.sub(rows[row][j], work.mul(ratio, rows[column][j]))
            rows[row][column] = Fraction(0)
    solution = [Fraction(0)] * size
    for row in range(size - 1, -1, -1):
        value = rows[row][-1]
        for j in range(row + 1, size):
            value = work.sub(value, work.mul(rows[row][j], solution[j]))
        solution[row] = work.div(value, rows[row][row])
    return tuple(solution)


def _checked_moved(x, C, d, weights, value, multipliers, work):
    """Check feasibility and stationarity without rerunning elimination.

    Positive weights make the objective strictly convex. These exact identities
    suffice for the unique constrained minimizer; no numeric tolerance is used.
    """
    for row, target in zip(C, d):
        if _dot(row, value, work) != target:
            raise ProjectionError('projection failed exact feasibility check', kind='check')
    moved = Fraction(0)
    for i, (before, after, weight) in enumerate(zip(x, value, weights)):
        change = work.sub(after, before)
        dual = _dot(tuple(row[i] for row in C), multipliers, work)
        if work.add(work.mul(weight, change), dual):
            raise ProjectionError('projection failed exact stationarity check', kind='check')
        moved = work.add(moved, work.mul(weight, work.mul(change, change)))
    return moved


def reconcile(x, C, d, weights=None, *, max_dimension=MAX_DIMENSION, max_bits=MAX_BITS,
              max_work=MAX_WORK, budget=None, node=None):
    """Return the five-field exact affine repair record for the supplied problem.

    Native int/Fraction only, 1<=len(C)<=len(x)<=32, independent C rows, positive
    weights. The residual describes the ORIGINAL x; satisfied means it already
    met C*x=d. Local bit/work limits may refuse even a representable final answer.
    A shared kernel Budget is charged throughout. No partial answer is returned.
    """
    try:
        # Runtime-only access tolerates V importing S while S discovers adapters.
        # V._Work supplies checked sums/products and scalar validation, not a solve.
        work = V._Work(max_dimension, max_bits, max_work, budget, node)
        x, C, d, weights = _problem(x, C, d, weights, work)
        residual = tuple(work.sub(_dot(row, x, work), target) for row, target in zip(C, d))
        inverse_weights = tuple(work.div(Fraction(1), weight) for weight in weights)
        scaled = tuple(tuple(work.mul(v, inv) for v, inv in zip(row, inverse_weights)) for row in C)
        gram = tuple(tuple(_dot(left, right, work) for right in C) for left in scaled)
        multipliers = _solve(gram, residual, work)
        value = tuple(work.sub(before, work.mul(inverse_weights[i],
                      _dot(tuple(row[i] for row in C), multipliers, work))) for i, before in enumerate(x))
        moved = _checked_moved(x, C, d, weights, value, multipliers, work)
        return {'value': tuple(S.norm_num(v) for v in value), 'moved': S.norm_num(moved),
                'residual': tuple(S.norm_num(v) for v in residual), 'satisfied': not any(residual),
                'method': METHOD}
    except V.VariationalError as exc:
        raise ProjectionError(exc.message.replace('quadratic', 'projection'),
                              exc.line, exc.col, 'check' if exc.kind == 'domain' else exc.kind) from None


def _reconcile(kernel, node, x, C, d, weights=None):
    return reconcile(x, C, d, weights, budget=kernel.budget, node=node)


FUNCTIONS = {'reconcile': _reconcile}
