"""Exact finite operators: orthogonal projectors, commutators and the probabilities of ordered questions.

A small algebra over the rationals for the projector model of question order (Busemeyer and Wang). Matrices
are real, square and rational, of dimension 1..MAX_DIMENSION, given as lists of rows; a state is a rational
vector of the same dimension.

    is_projector(P)          Bool: P is symmetric and P*P = P (an orthogonal projector with rational entries).
    commutator(A, B)         the matrix A*B - B*A, a list of rows in index order.
    commutes(A, B)           Bool: A*B - B*A is the zero matrix.
    ordered_probability(state, answers)
                             |M_k ... M_1 state|^2 / |state|^2, exactly. `answers` is a list of 1..MAX_ANSWERS
                             records {projector: P, yes: Bool} taken in order; M_i is P_i for yes and I - P_i
                             for no. The state is a non-zero vector and need not be normalised. Every
                             projector must pass is_projector.

Numbers are int or canonical Fraction, never float and never bool. Results are kernel values: tuples, numbers
normalised by S.norm_num, bools. A call is charged to the kernel step budget in full, from the shapes alone,
before any entry is read; numerators and denominators of the inputs and of every unreduced intermediate are
bounded by MAX_BITS bits, checked before they are built. Refusals raise OperatorError: kind 'type' for shapes,
sizes, record fields and kinds of number; 'check' for a zero state or an answer whose matrix is not an
orthogonal projector; 'budget' for the bit and work limits; 'runtime' only if the module's own work count ever
exceeded its charge (a defect, not reachable by an input). Exhausting the shared kernel budget raises the
kernel's own error.

This computes what the projector model PREDICTS for the matrices a program supplies. When the projectors
commute no probability depends on the order of the questions; when they do not it can, and the model then
also predicts the QQ equality (Wang and Busemeyer 2013): the probability that the two answers differ is the
same in both orders. None of it shows that a person or a language model follows the model, and a language
model's hidden state is not a quantum state. Unequal conditional probabilities P(B|A) != P(A|B) are ordinary
probability, not an order effect.

Import is inert: nothing is registered, read, written or called. symblic.kernel.language.ADAPTERS names the four
builtins.

Depends on: symblic.kernel.language. See docs/reference/OPERATORS.md.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction
from math import gcd

from symblic.kernel import language as S

VERSION = 1
MAX_DIMENSION = 8        # rows and columns of every matrix; entries of the state
MAX_ANSWERS = 8          # questions in one ordered_probability call
MAX_BITS = 4096          # numerator and denominator of every input and of every unreduced intermediate
MAX_WORK = 10_000        # work units one call may be charged; the largest call the size limits admit costs 6249
_ANSWER_FIELDS = frozenset(('projector', 'yes'))


class OperatorError(S.SymblicError):
    """An input outside the finite operator domain, or an exhausted deterministic limit."""


# -- the charge: computed from the shapes and taken before any entry is read ------------------------------

def _projector_cost(n):
    """n*n entries read, then the n(n+1)/2 entries of P*P on and above the diagonal, 2n operations each."""
    return n * n + n * n * (n + 1)


def _commutator_cost(n):
    """2n*n entries read, then 4n operations for each of the n*n entries of A*B - B*A."""
    return 2 * n * n + 4 * n ** 3


def _probability_cost(n, k):
    """The state's n entries; per answer its projector check and one application (2n*n, and n more for a no,
    charged for every answer); then the two squared norms (2n each) and the quotient."""
    return n + k * (_projector_cost(n) + 2 * n * n + n) + 4 * n + 1


class _Work:
    """Exact rational arithmetic that spends a precomputed charge and refuses oversized integers.

    Units are deterministic counts of scalar validations and rational operations (comparisons are not
    counted), not wall-clock or bit-complexity measures. The kernel budget is charged the whole amount once,
    before the work, and the call can then never do more units than it was charged.
    """

    def __init__(self, cost, budget=None, node=None):
        if cost > MAX_WORK:
            raise OperatorError(f'the call needs {cost} work units; the limit is {MAX_WORK}', kind='budget')
        if budget is not None:
            if not isinstance(budget, S.Budget):
                raise OperatorError('budget must be a Symblic Budget', kind='type')
            budget.tick(cost, node)
        self.charged, self.used = cost, 0
        self.cap = (1 << MAX_BITS) - 1

    def tick(self):
        if self.used >= self.charged:
            # Reachable only through a wrong cost formula: refuse rather than do uncharged work.
            raise OperatorError('operator work exceeded its precomputed charge', kind='runtime')
        self.used += 1

    def scalar(self, value, label):
        self.tick()
        # bool, float (even integral or infinite), Decimal, text and numeric subclasses are refused: a binary
        # approximation is never reinterpreted as the rational the author meant.
        if type(value) not in (int, Fraction):
            raise OperatorError(f'{label} must be an exact integer or fraction, not {_what(value)}', kind='type')
        numerator = value if type(value) is int else value.numerator
        denominator = 1 if type(value) is int else value.denominator
        if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
            raise OperatorError(f'{label} must be a canonical fraction', kind='type')
        if numerator.bit_length() > MAX_BITS or denominator.bit_length() > MAX_BITS:
            raise OperatorError(f'{label} has more than {MAX_BITS} bits', kind='budget')
        if gcd(numerator, denominator) != 1:
            raise OperatorError(f'{label} must be a canonical fraction', kind='type')
        return Fraction(numerator, denominator)

    def _product(self, a, b):
        # Checked before multiplying, so no integer above the cap is ever built.
        if b and abs(a) > self.cap // abs(b):
            raise OperatorError(f'an intermediate number would exceed {MAX_BITS} bits', kind='budget')
        return a * b

    def _sum(self, a, b):
        if (a > 0 and b > 0 or a < 0 and b < 0) and abs(a) > self.cap - abs(b):
            raise OperatorError(f'an intermediate number would exceed {MAX_BITS} bits', kind='budget')
        return a + b

    def add(self, a, b):
        self.tick()
        common = gcd(a.denominator, b.denominator)
        ad, bd = a.denominator // common, b.denominator // common
        numerator = self._sum(self._product(a.numerator, bd), self._product(b.numerator, ad))
        if not numerator:
            return Fraction(0)
        return Fraction(numerator, self._product(ad, b.denominator))

    def sub(self, a, b):
        return self.add(a, -b)

    def mul(self, a, b):
        self.tick()
        # Cross-cancel first, so large but cancelling fractions stay inside the bound.
        left, right = gcd(a.numerator, b.denominator), gcd(b.numerator, a.denominator)
        return Fraction(self._product(a.numerator // left, b.numerator // right),
                        self._product(a.denominator // right, b.denominator // left))

    def dot(self, xs, ys):
        total = Fraction(0)
        for x, y in zip(xs, ys):
            total = self.add(total, self.mul(x, y))
        return total


# -- shapes: read before the charge, so a call is refused by size before it costs anything -----------------

def _what(value):
    """The kernel's name for a refused value; the Python type for anything the kernel does not make."""
    if type(value) in (bool, int, Fraction, str, tuple, list, dict, S.ValueSet):
        return S.type_name(value)
    return type(value).__name__


def _size(value, label, most):
    if type(value) not in (list, tuple) or not 1 <= len(value) <= most:
        raise OperatorError(f'{label} must be a list of 1..{most} entries', kind='type')
    return len(value)


def _square(value, label):
    """The dimension of a square matrix given as a list of rows."""
    if type(value) not in (list, tuple) or not 1 <= len(value) <= MAX_DIMENSION:
        raise OperatorError(f'{label} must be a square matrix of dimension 1..{MAX_DIMENSION} (a list of rows)',
                            kind='type')
    n = len(value)
    if any(type(row) not in (list, tuple) or len(row) != n for row in value):
        raise OperatorError(f'{label} must be square: {n} rows of {n} entries each', kind='type')
    return n


def _entries(value, label, work):
    return tuple(tuple(work.scalar(x, f'{label} row {i} column {j}') for j, x in enumerate(row, 1))
                 for i, row in enumerate(value, 1))


# -- the mathematics ----------------------------------------------------------------------------------------

def _projector_defect(P, work):
    """None for an orthogonal projector, else the first property P lacks; symmetry is checked first."""
    n = len(P)
    if any(P[i][j] != P[j][i] for i in range(n) for j in range(i)):
        return 'is not symmetric'
    # For a symmetric P, entry (i, j) of P*P is the dot product of rows i and j, and P*P is symmetric too:
    # the entries on and above the diagonal decide P*P = P.
    for i in range(n):
        for j in range(i, n):
            if work.dot(P[i], P[j]) != P[i][j]:
                return 'does not satisfy P*P = P'
    return None


def _commutator_entry(A, B, i, j, work):
    total = Fraction(0)
    for m in range(len(A)):
        total = work.add(total, work.mul(A[i][m], B[m][j]))
        total = work.sub(total, work.mul(B[i][m], A[m][j]))
    return total


def _pair(A, B, budget, node):
    n = _square(A, 'A')
    if _square(B, 'B') != n:
        raise OperatorError(f'A is {n} x {n} and B is {len(B)} x {len(B)}: they must have the same dimension',
                            kind='type')
    work = _Work(_commutator_cost(n), budget, node)
    return _entries(A, 'A', work), _entries(B, 'B', work), work


def is_projector(P, *, budget=None, node=None):
    """True when the square rational matrix P is symmetric and P*P = P; False otherwise."""
    n = _square(P, 'P')
    work = _Work(_projector_cost(n), budget, node)
    return _projector_defect(_entries(P, 'P', work), work) is None


def commutator(A, B, *, budget=None, node=None):
    """A*B - B*A for square rational matrices of one dimension, as a tuple of rows in index order."""
    A, B, work = _pair(A, B, budget, node)
    n = len(A)
    return tuple(tuple(S.norm_num(_commutator_entry(A, B, i, j, work)) for j in range(n)) for i in range(n))


def commutes(A, B, *, budget=None, node=None):
    """True when A*B = B*A; it stops at the first non-zero entry of the commutator."""
    A, B, work = _pair(A, B, budget, node)
    n = len(A)
    return all(not _commutator_entry(A, B, i, j, work) for i in range(n) for j in range(n))


def ordered_probability(state, answers, *, budget=None, node=None):
    """The exact probability of a sequence of yes/no answers under the projector model (see the module)."""
    n = _size(state, 'state', MAX_DIMENSION)
    k = _size(answers, 'answers', MAX_ANSWERS)
    asked = []
    for index, answer in enumerate(answers, 1):
        if not isinstance(answer, dict) or len(answer) != len(_ANSWER_FIELDS) or set(answer) != _ANSWER_FIELDS:
            raise OperatorError(f'answer {index} must be a record with exactly the fields projector and yes',
                                kind='type')
        if type(answer['yes']) is not bool:
            raise OperatorError(f'answer {index}: yes must be true or false, not {_what(answer["yes"])}',
                                kind='type')
        if _square(answer['projector'], f'answer {index} projector') != n:
            raise OperatorError(f'answer {index}: the projector must be {n} x {n}, the dimension of the state',
                                kind='type')
        asked.append((answer['projector'], answer['yes']))
    work = _Work(_probability_cost(n, k), budget, node)
    start = tuple(work.scalar(x, f'state entry {i}') for i, x in enumerate(state, 1))
    if not any(start):
        raise OperatorError('the state must not be the zero vector', kind='check')
    steps = []
    for index, (matrix, yes) in enumerate(asked, 1):
        P = _entries(matrix, f'answer {index} projector', work)
        defect = _projector_defect(P, work)
        if defect:
            raise OperatorError(f'answer {index}: the matrix {defect}, so it is not an orthogonal projector',
                                kind='check')
        steps.append((P, yes))
    vector = start
    for P, yes in steps:
        image = tuple(work.dot(row, vector) for row in P)          # P is symmetric: row i of P times the vector
        vector = image if yes else tuple(work.sub(v, p) for v, p in zip(vector, image))
    after, before = work.dot(vector, vector), work.dot(start, start)
    # before > 0 because the state is not zero; dividing is multiplying by the reciprocal.
    return S.norm_num(work.mul(after, Fraction(before.denominator, before.numerator)))


# -- builtins: fixed positional arguments, no named options -------------------------------------------------

def _arguments(name, args, kwargs, names):
    if kwargs or len(args) != len(names):
        raise OperatorError(f'{name} takes {len(names)} argument{"s" if len(names) > 1 else ""} '
                            f'({", ".join(names)}) and no named options', kind='type')
    return args


def _is_projector(kernel, node, *args, **kwargs):
    P, = _arguments('is_projector', args, kwargs, ('P',))
    return is_projector(P, budget=kernel.budget, node=node)


def _commutator(kernel, node, *args, **kwargs):
    A, B = _arguments('commutator', args, kwargs, ('A', 'B'))
    return commutator(A, B, budget=kernel.budget, node=node)


def _commutes(kernel, node, *args, **kwargs):
    A, B = _arguments('commutes', args, kwargs, ('A', 'B'))
    return commutes(A, B, budget=kernel.budget, node=node)


def _ordered_probability(kernel, node, *args, **kwargs):
    state, answers = _arguments('ordered_probability', args, kwargs, ('state', 'answers'))
    return ordered_probability(state, answers, budget=kernel.budget, node=node)


FUNCTIONS = {'is_projector': _is_projector, 'commutator': _commutator, 'commutes': _commutes,
             'ordered_probability': _ordered_probability}
