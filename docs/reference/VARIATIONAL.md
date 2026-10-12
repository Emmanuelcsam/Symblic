# Exact finite quadratic minimization

`symblic/adapters/variational.py` solves the explicitly supplied problem

\[
H(x)=\tfrac12 x^T A x-b^T x,\qquad x\in\mathbb R^n,
\]

when every input coefficient is rational and `A` is symmetric positive definite.
It returns an exact rational minimizer and an independently checkable finite
algebraic witness. It makes no model calls. It does not assemble a PDE, infer
boundary conditions, choose units, or certify a physical component or a natural
language interpretation.

The established mathematical result is described in Boyd and Vandenberghe,
*Convex Optimization*, **Example 4.5**, §4.2.3, printed pp. 140–141: the stationary
equation for a convex quadratic is linear, and positive definiteness gives a
unique minimizer. The book's §4.5 instead covers geometric programming.
[Primary textbook](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf#page=154).

## Interface and current integration

Symblic 2.2 loads this fixed first-party module and exposes the two bounded builtins.
Canonical form remains version 3; `kernel_id()` additionally pins the variational
adapter's version. Old kernel identities must not be treated as the same semantics.
The module itself performs no registration, service work or I/O on import.

```python
from fractions import Fraction
import symblic.adapters.variational as V

A = [[4, 1], [1, 3]]
b = [1, 2]
receipt = V.minimize_quadratic(A, b)
assert receipt["x"] == (Fraction(1, 11), Fraction(7, 11))
assert receipt["min_energy"] == Fraction(-15, 22)
assert V.verify_quadratic(A, b, receipt)
```

The following program runs with the Symblic 2.2 builtins and uses the kernel's
shared step budget:

```symblic
let A = [[4, 1], [1, 3]].
let b = [1, 2].
let result = quadratic_minimize(A, b).
assert quadratic_verify(A, b, result).
assert result.x = [1/11, 7/11].
assert result.min_energy = -15/22.
show result.x.
```

Hosts using the adapter through the extension seam may also call
`V.register(run.kernel)` before `run.execute()`. It adds `quadratic_minimize` and
`quadratic_verify` to that kernel's `functions` mapping, is idempotent, accepts the
equivalent 2.2 builtin wrappers, and refuses to replace another function. It does
not alter the global registry. The wrappers and explicit registration share the
same implementation and resource accounting.

`minimize_quadratic(A,b)` and `quadratic_minimize(A,b)` return the same native
record. Lists are tuples; numbers are integers or `fractions.Fraction`, matching
Symblic's exact values. Python floats, Decimal values, strings, booleans and custom
numeric subclasses are rejected. Write a decimal as a Symblic numeric literal or
construct an explicit `Fraction` in Python; a binary floating-point approximation
is not silently reinterpreted as the intended rational. Corrupted or noncanonical
`Fraction` internals are also refused.

The verifier takes the expected inputs **separately**:
`verify_quadratic(A,b,receipt)` / `quadratic_verify(A,b,receipt)`. A self-consistent
receipt for a different matrix or right-hand side does not verify against the
original problem. Verification returns `False` for malformed, mismatched or locally
over-budget data. This means *unverified*, not a proof that the mathematical problem
has no solution. Exhausting an attached kernel's global budget raises its normal
error. Minimization raises `VariationalError` rather than returning a partial answer.

The receipt's fields are `schema`, `method`, `scope`, `A`, `b`, `L`, `D`, `x`,
`residual`, `min_energy`, and `checks`. Extra or missing fields are refused by this
version's verifier. Its method/version labels identify the witness format, not
authenticated software provenance. A third party may construct a valid witness.
Plain display/API renderings of fractions may be approximate text; they are not a
lossless receipt transport. Verify native exact values. This module does not add
an importable JSON certificate format or signatures.

## What the witness establishes

The solver performs exact, unpivoted `LDLᵀ` factorization. For a symmetric positive
definite input, all its diagonal pivots are positive. Forward substitution, diagonal
division and backward substitution solve `Ax=b`.

The separate verifier never calls the factorization or solve routines. It checks:

1. Exact matrix symmetry, dimensions, input identity and coefficient bounds.
2. A unit lower-triangular `L`, strictly positive diagonal vector `D`, and exact
   reconstruction `A = L diag(D) Lᵀ`.
3. The supplied `x` has exactly zero residual `Ax-b`.
4. The reported minimum energy equals direct evaluation of the supplied quadratic.

The Boolean labels in `checks` cannot substitute for those calculations. Given
the checked identities, any real displacement `v` satisfies

\[
H(x+v)-H(x)=\tfrac12v^TAv
 =\tfrac12\sum_i D_i\big((L^Tv)_i\big)^2.
\]

This is positive for every nonzero `v`, since a unit triangular matrix is invertible
and every `D_i>0`. Hence the checked stationary point is the unique global minimum
of this **encoded finite problem**. This is an exact algebraic witness checked by
the implementation, not a proof of the implementation in a proof assistant.

Singular and indefinite matrices are refused, even when `Ax=b` has a solution.
For example, `A=[[-1]], b=[0]` has a stationary point at zero that is a maximum.
`A=[[1,-1],[-1,1]], b=[0,0]` has an entire constant nullspace and no unique minimum.
The adapter does not silently choose a gauge, regularize a matrix, symmetrize it,
or invent constraints to make a problem fit the supported class.

## Deterministic resource limits

Defaults and hard upper bounds are:

| Keyword | Limit | Meaning |
| --- | ---: | --- |
| `max_dimension` | 32 | Dense square dimension, at least one |
| `max_bits` | 4096 | Numerator, denominator and arithmetic intermediate bit size |
| `max_work` | 200000 | Scalar validations and rational arithmetic operations |

Callers may lower these integer limits, including from a Symblic function call.
They cannot increase the hard bounds. Each counted operation also charges an
attached kernel budget. Multiplication cross-cancels first; integer products and
sums are checked **before** constructing an oversized intermediate. A small final
answer can therefore still be refused if an intermediate would exceed its bound.

Dense factorization, substitution and witness reconstruction have cubic arithmetic
growth overall and quadratic storage. Rational bit growth matters as well: these
operation limits are not a wall-clock guarantee or a substitute for host admission
controls. The adapter is intended for small explicit contracts, not large simulation
meshes. No numerical convergence tolerance or floating-point condition estimate is
being reported.

## What the energy analogy does not prove

The local two-page vorticity note motivates the finite quadratic formulation. Its
weak-form cancellation depends on the stated boundary terms vanishing. Turning its
continuum energy argument into a well-posed PDE result additionally needs an
appropriate domain/function space, coefficient positivity and coercivity. A
nonempty boundary subset alone does not establish those hypotheses. In a continuum
Sobolev formulation, fixing one boundary point is not automatically a valid coercive
Dirichlet condition. Pure Neumann problems require source compatibility and treatment
of the constant nullspace. This adapter verifies only the supplied discrete matrix;
it does not establish those continuum or discretization facts.

The sign of the source term and the construction of `b` must follow the actual weak
form and discretization. They are not inferred from a variable named “vorticity.”
Physical use also requires units, material/constitutive assumptions where relevant,
loads, supports, discretization convergence and a suitable validation criterion.

Lower entropy or lower disagreement between model answers is not this theorem's
positive quadratic energy. All readers can agree on a false extraction. Deleting a
requirement can reduce disagreement while damaging fidelity. Even a decreasing
scalar objective can have the wrong optimum for the user's intention. No general
semantic-truth, gradient-convergence or conjugate-gradient guarantee follows from
the analogy. The finite exact algebra above is established prior mathematics; the
contribution here is its bounded integration and checkable witness contract, not a
claim to a new energy principle.

## Focused verification

`tests/adapters/test_symblic_variational.py` covers known scalar and coupled solutions,
seeded SPD matrices built independently as `L diag(D) Lᵀ`, exact energy comparisons,
singular/indefinite/nonsymmetric counterexamples, malformed and tampered witnesses,
type and budget refusals, verifier independence, and explicit kernel attachment with
zero model calls. A performance profile must identify its dimension, coefficient
construction, operation count, runtime and hardware; it cannot be quoted as model
accuracy or as performance on arbitrary matrices.

One bounded observation on 2026-10-03 used CPython 3.12.3 on a 6-core desktop CPU
(x86_64), adapter version 1. Each matrix came from the independent test generator
`spd_problem(n, 20261003+n)` with a known rational solution. The largest input
numerator/denominator used at most 17 bits in these four cases. Solver times include
its receipt audit; verifier times are a separate check. These are individual
current-load observations, not latency guarantees or PDE benchmarks.

| Dimension | Solve + audit (s) | Verify (s) | Solve work units | Verify work units |
| ---: | ---: | ---: | ---: | ---: |
| 4 | 0.00252 | 0.00140 | 301 | 183 |
| 8 | 0.0109 | 0.00553 | 1333 | 763 |
| 16 | 0.0583 | 0.0275 | 7141 | 3891 |
| 32 | 0.350 | 0.173 | 44485 | 23395 |

Every row matched its independently constructed solution and passed witness
verification. No model was called. Matrices with more difficult rational bit growth
may reach the arithmetic bound earlier, even at the same dimension.
