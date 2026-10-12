# Supplied geometry experiments, version 1

Private staged candidate. The module does not call providers, run native Symblic programs, persist results, read user files or modify execution pins. The required import marker records its own source identity; the host supplies the existing first-party identity module. Root owns API/CLI/UI integration and deployment.

`catalog()` returns deep-copied entries with `id`, `title`, `summary`, `example`, `sources` and `limits`. `run(id, data)` returns JSON-safe `arithmetic`, `results`, `checks`, `limits`, `sources` and `work`. Unknown IDs and malformed/oversized inputs raise `ValueError` containing a fixed short code, with no echoed input. Checks report the particular finite computation, not empirical truth.

## Hamiltonian integrators

`hamiltonian_integrators` accepts exactly `K`, `inverse_mass`, `q0`, `p0`, `step`, `steps`, `units`. Dimension is 1–4. `K` is symmetric positive definite, certified by exact elimination pivots; inverse masses are positive. The only admitted unit convention is `"dimensionless"`. The supplied separable Hamiltonian is

`H(q,p) = (qᵀKq + pᵀMp)/2`, where `M=diag(inverse_mass)`.

Both methods start from the same state and use the same 1–32 fixed steps, `0 < h <= 4`. Explicit Euler uses the old momentum for the position update. Symplectic Euler first computes `p'=p−hKq`, then `q'=q+hMp'`. These are the Euler schemes presented in [Hairer's geometric-integration lectures](https://www.unige.ch/~hairer/poly_geoint/intro.pdf). This adapter supports the quadratic subset specified here.

The result contains every state, original energy, energy error, maximum absolute energy error, and the two exact update matrices. Independent matrix calculations check `AᵀJA=J` for the displayed symplectic form. They separately check whether each matrix preserves the *original* energy quadratic; this is generally false. The adapter's explicit modified quadratic has block matrix

`S_h = [[K, −hKM/2], [−hMK/2, M]]`.

It checks `A_symᵀS_h A_sym=S_h` and constancy of that quadratic on the actual trajectory. Positive definiteness of `S_h` is reported separately. Large-step examples can retain the modified invariant while original energy explodes: symplecticity alone is not a universal stability or physical-fit claim. No conservation law is inferred from prose or an LLM state.

## Fisher gradient

`fisher_gradient` accepts exactly `probabilities`, `train`, `heldout`, `step`, `steps`, `regularization`. There are 2–6 categories, with strictly positive probabilities summing exactly to one. Two categories provide the Bernoulli case. Both count arrays have the same size and a positive total; each count is an integer 0–1,000,000.

The independent probability coordinates are `theta=(p_0,...,p_(k−2))`, with `p_(k−1)=1−sum(theta)`. Training frequencies `t_i` determine the negative log-likelihood gradient `g_i=−t_i/p_i+t_last/p_last`. Taking the expectation of the categorical score outer product gives `F_ij=delta_ij/p_i+1/p_last`. Exact positive pivots report rank `k−1`; boundary or redundant-coordinate charts are not supported. [Amari's natural-gradient paper](https://doi.org/10.1162/089976698300017746) supplies the information-geometric method; these explicit categorical formulas are implemented and checked here.

Ordinary descent uses `g`. Natural descent solves `(F+lambda I)d=g` and checks the exact solve residual. `lambda=0` is the natural direction; positive `lambda` is explicitly labeled damping, never silently described as the undamped Fisher metric. The same initial state, step (`0 < h <= 1`) and 1–16 attempted updates apply to both methods. A proposal leaving the open simplex is recorded and rejected, consumes that attempt and retains the previous state. There is no clipping, line search, early selection or hidden stopping rule.

Only training data affects updates. Both fixed final distributions are evaluated on the caller-declared frozen held-out counts, reporting exact Brier score and squared frequency error, plus approximate mean negative log-likelihood in nats. Logs use a fixed Decimal context, precision 50 and round-half-even. Held-out values select neither updates nor hyperparameters nor a winner. The module cannot establish the independence of caller-supplied train/held-out sets, superiority on other data, global convergence or an LLM's hidden Fisher geometry.

## Arithmetic, bounds and verification

Inputs are exact integers (excluding Booleans, magnitude at most 2^53−1) or ASCII integer/rational strings of at most 81 characters and 128 reduced numerator/denominator bits. Floats, decimal/exponent strings, arbitrary code and paths are rejected. All rational update/linear-algebra operations are charged against 50,000 operations and a 512-bit normalized numerator/denominator limit; exceeding a bound refuses the experiment. Fraction operations normalize before the size check; pairwise multiplication/addition may transiently allocate integers up to 1,025 bits from admitted 512-bit operands. Matrix dimensions and trajectory lengths are validated before iterative work. At most 36 logarithms are evaluated for the bounded final score tables. Decimal values are labeled approximate strings; exact fractions serialize as rational strings.

Twelve isolated tests cover independent scalar/coupled trajectories, analytic Euler energy growth, indefinite modified-invariant counterexample, analytic Bernoulli and categorical Fisher directions, damping, held-out isolation, rejected-boundary accounting, malformed domains, hard work/bit refusals, deterministic JSON output and the source-identity marker. No model, production store or daemon is used.
