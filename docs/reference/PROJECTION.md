# Exact adjustment to affine constraints

`reconcile(x, C, d, weights=None)` returns the unique vector `y` that satisfies
`C y = d` and minimizes `sum(weights[i] * (y[i] - x[i])^2)`.
Omitted weights are all one. This is an orthogonal projection onto the supplied
affine subspace, using the weighted inner product when weights are supplied.
It is a classical finite weighted least-squares adjustment, not a new method.

The result is a **changed vector**. Report it as a repair, keep the original
values, and choose an acceptable bound on `moved` for the application. Feasibility
does not establish that a model answer or measurement was correct. The adapter
cannot determine whether the constraints, units or weights represent reality.

Historical linear data-reconciliation reference: R. Kuehn and H. Davidson (1961),
“Computer control II: mathematics of control,” *Chemical Engineering Progress*
57(6). The underlying strictly convex quadratic framework is also described in
Boyd and Vandenberghe, *Convex Optimization*, Example 4.5 and the treatment of
equality-constrained minimization.
[Primary textbook](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf).

## Inputs and result

`x` contains `n` native exact numbers, `C` has `m` rows of length `n`, and `d`
contains `m` targets. Require `1 <= m <= n <= 32`, independent rows of `C`, and
strictly positive weights of length `n`. Python integers and canonical Fractions
are accepted; floats, booleans, numeric strings, nonfinite values and numeric
subclasses refuse. Symblic decimal literals are already exact rational numbers.
Kernel tuples and Python lists are accepted; inputs are never mutated.

The five-field result is:

| Field | Meaning |
| --- | --- |
| `value` | Repaired vector, in the original coordinate order |
| `moved` | Exact weighted sum of squared adjustments |
| `residual` | `C x - d`, the **original** violation, in constraint-row order |
| `satisfied` | Whether the **original** `x` already satisfied every constraint |
| `method` | `"exact-affine-projection"` |

Consequently, `satisfied=false` is expected when a repair was necessary. Every
returned `value` has passed the exact feasibility check. A large `moved` is still
a valid mathematical projection; only the caller can decide whether to accept it.
No uncertainties, probabilities, model confidence or inverse variances are inferred
from the supplied weights. Weights also determine the units of the objective;
compare `moved` only under the same coordinate and weight conventions.

```symblic
let original = [40, 35, 30].
let repair = reconcile(original, [[1, 1, 1]], [100]).
assert repair.value = [115/3, 100/3, 85/3].
assert repair.moved = 25/3.
assert repair.residual = [5].
assert not repair.satisfied.
assert repair.moved <= 9.
show repair.value.
show repair.moved.
```

With the adapter registered as a core builtin, this kernel-only program reports
the repaired values `115/3`, `100/3`, `85/3` and adjustment cost `25/3`; it makes no
model call. Display formatting may show approximate decimal text, while the
assertions use the exact fractions. The example's cost bound of nine is an
explicit program choice, not a universal acceptance threshold.

## Computation and checks

Let `W` be the positive diagonal weight matrix. The implementation assembles
`G = C W^-1 C^T` and solves `G lambda = C x - d`, then computes
`y = x - W^-1 C^T lambda`. Gaussian elimination chooses the first nonzero pivot
row in increasing row order. Dependent constraint rows are refused, including
redundant but consistent rows; no rank repair or tolerance is applied.

Before returning, separate calculations check both `C y = d` and
`W(y-x) + C^T lambda = 0`, then evaluate the adjustment cost from `x` and `y`.
They do not rerun elimination. Positive weights make the objective strictly
convex. For every feasible nonzero displacement `v`, stationarity cancels the
cross term and the cost increases by `sum(weights[i] * v[i]^2) > 0`.
Thus these checked identities establish the unique minimum for the encoded
finite problem. This is not a proof of the implementation in a proof assistant;
the five-field result is not a signed or externally self-verifying certificate.

## Bounds and integration

The pure Python `reconcile` API additionally accepts lower `max_dimension`,
`max_bits` and `max_work` limits, with hard ceilings 32, 4096 and 200000.
Limits are positive native integers. Numerators, denominators and unreduced
arithmetic intermediates have a bit bound; products and sums are checked before
construction. The operation may refuse a small final answer when an intermediate
is too large. Work counts scalar validation, exact arithmetic and pivot-search
steps; it is not a wall-clock estimate. No partial answer is returned.

The module reuses `symblic.adapters.variational._Work` for bounded arithmetic, not its
quadratic solver. It accesses that helper only when called, so discovering this
module during a partial variational import does not read incomplete attributes.
An optional shared `Symblic.Budget` is charged throughout and exhaustion propagates.
The kernel callback in `FUNCTIONS['reconcile']` has signature
`(kernel, node, x, C, d, weights=None)` and always uses `kernel.budget`.
The module is inert on import; the core coordinator supplies the builtin wrapper
and version pin. There is no direct provider, host, filesystem or network access.

Focused verification covers hand-checked examples, 48 seeded rational problems
against an independent full KKT solve, finite feasible displacements, constraint
reordering/scaling, canonical forms, invalid domains, arithmetic bounds and shared
budget exhaustion. The reference solve does not construct the implementation's
smaller matrix `G`. These finite tests provide implementation evidence within
their scope; they do not establish semantic truth or physical validity.
