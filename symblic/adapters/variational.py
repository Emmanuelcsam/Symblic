"""Exact quadratic minimization: the minimum of H(x) = (1/2) x^T A x - b^T x for a symmetric positive-definite A.

    quadratic_minimize(A, b)              # exact rational x with A x = b, with a receipt
    quadratic_verify(A, b, receipt)       # check a receipt again (for example one a model or another run made)

The matrix and vector are supplied explicitly as rationals; the solution is exact (no floating point) and
comes with a receipt that the checker can verify again. This is the finite core of variational problems
(least squares, small finite-element systems) without PDE assembly, a model or a service.

Import is inert: no I/O and no registration as a side effect. The kernel exposes quadratic_minimize and
quadratic_verify as builtins through lazy wrappers in symblic/kernel/language.py, which also imports this
module at load (harmless, because the import is inert). register(kernel) still attaches the same functions to
one Kernel's function table, for hosts that build their own kernels. Receipts are mathematical witnesses for
the supplied finite problem, not signed attestations, physical validation or evidence about natural-language
meaning.

Depends on: symblic.kernel.language. Used by: the quadratic_* builtins, symblic.adapters.projection,
quantities and transport.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction
from math import gcd

from symblic.kernel import language as S

VERSION = 1
SCHEMA = 'symblic.quadratic-minimum.v1'
METHOD = 'exact-rational-ldlt'
SCOPE = 'explicit-finite-rational-quadratic'
MAX_DIMENSION = 32
MAX_BITS = 4096
MAX_WORK = 200_000
_CHECKS = ('symmetric', 'positive_pivots', 'factorization', 'stationary', 'unique_minimum')
_FIELDS = frozenset(('schema', 'method', 'scope', 'A', 'b', 'L', 'D', 'x', 'residual',
                     'min_energy', 'checks'))


class VariationalError(S.SymblicError):
    """Invalid finite problem, invalid witness, or exhausted deterministic limit."""


def _limit(value, ceiling, name):
    if type(value) is not int or not 1 <= value <= ceiling:
        raise VariationalError(f'{name} must be an integer in 1..{ceiling}', kind='budget')
    return value


class _Work:
    """Count scalar validation/arithmetic, preflight every integer product/sum.

    Work units are deterministic operation counts, not wall-clock or bit-complexity
    estimates. Bounds also cover unreduced intermediates, so a representable final
    answer may be refused when an intermediate would exceed the selected limit.
    """

    def __init__(self, dimension, bits, work, budget=None, node=None):
        self.dimension = _limit(dimension, MAX_DIMENSION, 'max_dimension')
        self.bits = _limit(bits, MAX_BITS, 'max_bits')
        self.maximum = _limit(work, MAX_WORK, 'max_work')
        if budget is not None and not isinstance(budget, S.Budget):
            raise VariationalError('budget must be a Symblic Budget', kind='type')
        self.budget, self.node, self.used = budget, node, 0
        self.cap = (1 << self.bits) - 1

    def tick(self):
        if self.used >= self.maximum:
            raise VariationalError('quadratic arithmetic work budget exhausted', kind='budget')
        self.used += 1
        if self.budget is not None:
            self.budget.tick(1, self.node)

    def scalar(self, value):
        self.tick()
        # Reject bool, floats (even integral/finite), Decimal, strings and custom
        # numeric subclasses; there is no implicit approximation or coercion.
        if type(value) not in (int, Fraction):
            raise VariationalError('quadratic entries must be exact integers or Fractions', kind='type')
        numerator = value if type(value) is int else value.numerator
        denominator = 1 if type(value) is int else value.denominator
        if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
            raise VariationalError('quadratic Fractions must be canonical rationals', kind='type')
        if numerator.bit_length() > self.bits or denominator.bit_length() > self.bits:
            raise VariationalError('quadratic rational bit budget exceeded', kind='budget')
        if gcd(numerator, denominator) != 1:
            raise VariationalError('quadratic Fractions must be canonical rationals', kind='type')
        return Fraction(value)

    def _product(self, a, b):
        # Check before multiplication, without constructing an oversized integer.
        if b and abs(a) > self.cap // abs(b):
            raise VariationalError('quadratic intermediate bit budget exceeded', kind='budget')
        return a * b

    def _sum(self, a, b):
        if (a > 0 and b > 0 or a < 0 and b < 0) and abs(a) > self.cap - abs(b):
            raise VariationalError('quadratic intermediate bit budget exceeded', kind='budget')
        return a + b

    def add(self, a, b):
        self.tick()
        common = gcd(a.denominator, b.denominator)
        ad, bd = a.denominator // common, b.denominator // common
        numerator = self._sum(self._product(a.numerator, bd), self._product(b.numerator, ad))
        if not numerator:
            return Fraction(0)
        denominator = self._product(ad, b.denominator)
        return Fraction(numerator, denominator)

    def sub(self, a, b):
        return self.add(a, -b)

    def mul(self, a, b):
        self.tick()
        # Cross-cancel before preflight; large but cancelling fractions stay useful.
        left, right = gcd(abs(a.numerator), b.denominator), gcd(abs(b.numerator), a.denominator)
        numerator = self._product(a.numerator // left, b.numerator // right)
        denominator = self._product(a.denominator // right, b.denominator // left)
        return Fraction(numerator, denominator)

    def div(self, a, b):
        if not b:
            raise VariationalError('quadratic division by zero', kind='domain')
        return self.mul(a, Fraction(b.denominator, b.numerator))


def _sequence(value, size, label):
    if type(value) not in (list, tuple) or len(value) != size:
        raise VariationalError(f'{label} must have exactly {size} entries', kind='type')


def _vector(value, size, work, label):
    _sequence(value, size, label)
    return tuple(work.scalar(v) for v in value)


def _matrix(value, size, work, label):
    _sequence(value, size, label)
    return tuple(_vector(row, size, work, label + ' row') for row in value)


def _problem(A, b, work):
    if type(A) not in (list, tuple) or not 1 <= len(A) <= work.dimension:
        raise VariationalError(f'A must be square with dimension 1..{work.dimension}', kind='type')
    size = len(A)
    matrix, vector = _matrix(A, size, work, 'A'), _vector(b, size, work, 'b')
    if any(matrix[i][j] != matrix[j][i] for i in range(size) for j in range(i)):
        raise VariationalError('A must be exactly symmetric', kind='domain')
    return matrix, vector


def _ldlt(A, work):
    size = len(A)
    lower = [[Fraction(int(i == j)) for j in range(size)] for i in range(size)]
    diagonal = []
    for j in range(size):
        pivot = A[j][j]
        for k in range(j):
            pivot = work.sub(pivot, work.mul(work.mul(lower[j][k], lower[j][k]), diagonal[k]))
        if pivot <= 0:
            raise VariationalError(f'A is not positive definite: pivot {j + 1} is not positive', kind='domain')
        diagonal.append(pivot)
        for i in range(j + 1, size):
            entry = A[i][j]
            for k in range(j):
                entry = work.sub(entry, work.mul(work.mul(lower[i][k], lower[j][k]), diagonal[k]))
            lower[i][j] = work.div(entry, pivot)
    return tuple(tuple(row) for row in lower), tuple(diagonal)


def _solve(lower, diagonal, b, work):
    size = len(b)
    forward = []
    for i in range(size):
        value = b[i]
        for j in range(i):
            value = work.sub(value, work.mul(lower[i][j], forward[j]))
        forward.append(value)
    scaled = [work.div(forward[i], diagonal[i]) for i in range(size)]
    solution = [Fraction(0)] * size
    for i in range(size - 1, -1, -1):
        value = scaled[i]
        for j in range(i + 1, size):
            value = work.sub(value, work.mul(lower[j][i], solution[j]))
        solution[i] = value
    return tuple(solution)


def _energy(A, b, x, work):
    product = []
    for row in A:
        value = Fraction(0)
        for a, v in zip(row, x):
            value = work.add(value, work.mul(a, v))
        product.append(value)
    quadratic, linear = Fraction(0), Fraction(0)
    for v, ax, rhs in zip(x, product, b):
        quadratic = work.add(quadratic, work.mul(v, ax))
        linear = work.add(linear, work.mul(rhs, v))
    energy = work.sub(work.mul(Fraction(1, 2), quadratic), linear)
    residual = tuple(work.sub(ax, rhs) for ax, rhs in zip(product, b))
    return energy, residual


def _native(value):
    if type(value) is Fraction:
        return S.norm_num(value)
    if type(value) in (list, tuple):
        return tuple(_native(v) for v in value)
    return value


def _verify(A, b, receipt, work):
    """Check the supplied witness directly, without factorization or solving."""
    if type(receipt) is not dict or len(receipt) != len(_FIELDS) or set(receipt) != _FIELDS:
        raise VariationalError('quadratic receipt fields do not match its schema', kind='verification')
    for name, expected in (('schema', SCHEMA), ('method', METHOD), ('scope', SCOPE)):
        if type(receipt[name]) is not str or receipt[name] != expected:
            raise VariationalError('quadratic receipt metadata does not match', kind='verification')
    claimed = receipt['checks']
    if (type(claimed) is not dict or len(claimed) != len(_CHECKS) or set(claimed) != set(_CHECKS)
            or any(v is not True for v in claimed.values())):
        raise VariationalError('quadratic receipt check labels do not match', kind='verification')
    size = len(A)
    if _matrix(receipt['A'], size, work, 'receipt A') != A or _vector(receipt['b'], size, work, 'receipt b') != b:
        raise VariationalError('quadratic receipt describes different inputs', kind='verification')
    lower = _matrix(receipt['L'], size, work, 'L')
    diagonal = _vector(receipt['D'], size, work, 'D')
    solution = _vector(receipt['x'], size, work, 'x')
    residual = _vector(receipt['residual'], size, work, 'residual')
    minimum = work.scalar(receipt['min_energy'])
    if any(diagonal[i] <= 0 or lower[i][i] != 1 or any(lower[i][j] for j in range(i + 1, size))
           for i in range(size)):
        raise VariationalError('quadratic receipt lacks positive unit-triangular LDLT', kind='verification')
    for i in range(size):
        for j in range(i + 1):
            value = Fraction(0)
            for k in range(j + 1):
                value = work.add(value, work.mul(work.mul(lower[i][k], diagonal[k]), lower[j][k]))
            if value != A[i][j]:
                raise VariationalError('quadratic LDLT witness does not reconstruct A', kind='verification')
    energy, actual_residual = _energy(A, b, solution, work)
    if any(actual_residual) or residual != actual_residual or minimum != energy:
        raise VariationalError('quadratic stationary point, residual or energy does not match', kind='verification')
    return True


def minimize_quadratic(A, b, *, max_dimension=MAX_DIMENSION, max_bits=MAX_BITS,
                       max_work=MAX_WORK, budget=None, node=None):
    """Exact unique minimum for the supplied finite rational symmetric PD problem.

    Raises VariationalError for unsupported inputs/limits; no partial or approximate
    minimum is returned. An attached kernel Budget is charged throughout.
    """
    work = _Work(max_dimension, max_bits, max_work, budget, node)
    matrix, vector = _problem(A, b, work)
    lower, diagonal = _ldlt(matrix, work)
    solution = _solve(lower, diagonal, vector, work)
    minimum, residual = _energy(matrix, vector, solution, work)
    receipt = {'schema': SCHEMA, 'method': METHOD, 'scope': SCOPE,
               'A': _native(matrix), 'b': _native(vector), 'L': _native(lower), 'D': _native(diagonal),
               'x': _native(solution), 'residual': _native(residual), 'min_energy': _native(minimum),
               'checks': dict.fromkeys(_CHECKS, True)}
    # A defect in the solve must not promote an unchecked result to a witness.
    _verify(matrix, vector, receipt, work)
    return receipt


def verify_quadratic(A, b, receipt, *, max_dimension=MAX_DIMENSION, max_bits=MAX_BITS,
                     max_work=MAX_WORK, budget=None, node=None):
    """Independently validate a witness; False means invalid OR locally unverified.

    Malformed inputs, nonpositive witnesses and local limits fail closed. Exhaustion
    of an attached kernel's global Budget propagates as a SymblicError.
    This verifies mathematics, not author identity, code provenance or a signature.
    """
    try:
        work = _Work(max_dimension, max_bits, max_work, budget, node)
        matrix, vector = _problem(A, b, work)
        return _verify(matrix, vector, receipt, work)
    except VariationalError:
        return False


def _minimize(kernel, node, A, b, **limits):
    return minimize_quadratic(A, b, budget=kernel.budget, node=node, **limits)


def _verify_builtin(kernel, node, A, b, receipt, **limits):
    return verify_quadratic(A, b, receipt, budget=kernel.budget, node=node, **limits)


FUNCTIONS = {'quadratic_minimize': _minimize, 'quadratic_verify': _verify_builtin}


def register(kernel):
    """Attach to one Kernel.functions mapping, idempotently and without replacing names."""
    if not isinstance(kernel, S.Kernel):
        raise VariationalError('register requires a Symblic Kernel', kind='type')
    for name, function in FUNCTIONS.items():
        if ((name in S.BUILTINS and S.BUILTINS[name] is not function
             and getattr(S.BUILTINS[name], '_symblic_variational', None) != name)
                or (name in kernel.functions and kernel.functions[name] is not function)):
            raise VariationalError(f'kernel function {name} already exists', kind='name')
    kernel.functions.update(FUNCTIONS)
    return kernel
