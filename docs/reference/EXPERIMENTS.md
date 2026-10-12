# Executable research mechanisms

Open Symblic → Experiments (a page of the original host), choose a mechanism, and run the supplied example. The advanced input editor accepts explicit JSON data; integers and rational strings such as `"2/3"` preserve exact arithmetic. Each result includes checks, comparisons, assumptions and limits. Download its receipt, or recompute it against the installed implementation.

These are callable, bounded computational mechanisms. They do not require a model call. Native graph adaptation executes the existing typed Symblic graph engine; numerical reconciliation and field experiments reuse the native exact quadratic machinery. The full model-constructed field example remains a separate [20-call execution](VORTICITY-CONSTRUCTION.md).

## Interfaces and reproducibility

The fixed registry is `symblic/experiments/registry.py`; adapters expose `catalog()` and `run(id, input)`. They perform no provider dispatch, network access, personal-store access or external capability execution. Optional imports degrade to a visible unavailable-adapter notice. The existing operator-only Symblic gate protects these routes:

| Method | Existing API child | Body |
|---|---|---|
| GET | `/api/automation/symblic/experiments/catalog` | None |
| POST | `/api/automation/symblic/experiments/run` | `experiment`, `input_json` |
| POST | `/api/automation/symblic/experiments/verify` | `receipt_json` |

Use the local CLI to inspect a schema/example, run a JSON file or standard input, and verify a saved receipt:

```sh
tools/symblic experiments list
tools/symblic experiments example circuit_rewrite > /tmp/symblic-circuit.json
tools/symblic experiments run circuit_rewrite /tmp/symblic-circuit.json > /tmp/symblic-receipt.json
tools/symblic experiments verify /tmp/symblic-receipt.json
```

A receipt pins the original input, its SHA-256, adapter version, exact loaded implementation sources, and complete output. Native dependencies include the current kernel sources when used. Imported code is checked against its loaded identity before and after execution, not only against a newly read file. Mutation of the caller's input is prevented; mutation by an adapter or a source change during execution refuses the receipt. Verification validates the supplied content hash and recomputes the exact typed JSON result. Booleans cannot stand in for numbers.

This is reproducibility relative to local pinned code and supplied inputs, not a signature or independent empirical validation. Source changes invalidate old receipts; preserve the original implementation to reproduce an older version. External actions and native model runs use their existing durable ledgers and portable locks, not this stateless receipt format.

The envelope caps JSON at 1 MiB, 65536 nodes, depth 24, individual strings at 65536 characters, and integers at JavaScript's exact range. Float literals, duplicate keys, cycles and unsupported types refuse. Adapters impose smaller dimensions, iteration counts, rational-bit and operation limits. Decimal log scores are labeled approximate; no tokenizer-derived token savings or physical runtime is invented.

## Mechanism catalog

| Mechanism | Executed operation and comparison |
|---|---|
| `extractive-compression` | Required source spans survive an exact byte budget or the operation refuses; optional selection and hierarchical merging compare against full source and keyword retrieval. |
| `pinned-hash-sidecar` | Exact encode/decode with caller-pinned card identity, revision and content hash; model-payload, sidecar and complete transport bytes reported separately. |
| `question_order_fit` | Select finite projector candidates on training Brier score; compare held-out likelihood, Brier and calibration against a classical contextual count model. |
| `density_measurements` | Validate real 2×2 density and POVM positivity/completeness, compute Born probabilities, and compare basis dephasing. |
| `circuit_rewrite` | Check two 1–2 qubit circuits as channels on every matrix unit, including global-phase equivalence; supports H, X, Z, CNOT and SWAP. |
| `tensor_semantics` | Contract supplied noun vectors and relation tensor, test subject/object reversal and scalar negation, compare a one-hot baseline against supplied gold. |
| `integer-graph-adaptation` | Generate bounded arithmetic graph mutations, execute native typed graphs on training examples, freeze selection before held-out execution; retain all candidates and actual work. |
| `particle_filter` | Seeded bootstrap particles, exact weights and multinomial resampling; compare ESS and posterior error against the exact finite Markov filter. |
| `ising_search` | Fixed-budget seeded spin descent and restarts checked against exhaustive finite energy minimization. |
| `noisy_codebook` | Compare supplied equal-rate codebooks under identical finite perturbations; report nearest-code ties, distortion and work. |
| `finite-matroid` | Validate the full finite independence family, rank and exchange axioms; compare weighted greedy basis selection with exhaustive optimum. |
| `boundary-graph-cut` | Compare exact max-flow/min-cut witnesses with exhaustive bulk assignments for supplied boundary sets and capacities. |
| `graph-smoothing` | Execute a stable bounded Laplacian averaging sequence, retain originals, independently check matrix/edge updates, conservation, energy and distortion. |
| `hamiltonian_integrators` | Evolve the same separable quadratic with explicit and symplectic Euler; check exact symplectic and modified-energy identities and record ordinary energy error. |
| `fisher_gradient` | Compute exact categorical Fisher metrics and matched natural/ordinary gradient updates from training data, then score a frozen held-out split. |
| `grover-query-comparison` | Calculate exact ideal Grover amplitudes and oracle-query counts; compare equal query budgets with classical sampling without replacement. |
| `field-refinement` | Solve a manufactured 1D steady heat field on several meshes with SI units, zero Dirichlet boundaries, independent stencil residuals and error against the known solution. |
| `spd-reconciliation` | Project observations onto affine constraints using a full SPD metric; check KKT feasibility/stationarity and compare a diagonal-metric baseline under the same objective. |
| `transport-certificate` | Verify finite mass balance, nonnegative transport plan, dual inequalities and optimality gap. Only a feasible dual is labeled a certified lower bound. |
| `cellular-sheaf` | Compute a supplied section's coboundary and independently check each edge's restriction compatibility. |
| `finite-schema-transport` | Check finite bidirectional mappings, predicate pullback, existential/universal fibers, round trips and a typed commuting square. |
| `revision-acknowledgements` | Replay exact-revision receive/acknowledgement events with idempotence and visible stale or missing recipients. |
| `one-use-resources` | Fold branch ownership, transfer and consumption intents; unresolved outcomes remain fenced and old outcomes cannot settle a later attempt. |
| `saga-compensation-plan` | Build eligible compensations in reverse dependency order, preserve original action links, and retain crash/uncertainty states. |

Detailed contracts: [source context](CONTEXT-EXPERIMENTS.md) , [Hamiltonian and Fisher geometry](RESEARCH-GEOMETRY.md), and [finite sheaf/schema transport](FINITE-TRANSPORT-EXPERIMENTS.md). The [protocol contract](PROTOCOL-EXPERIMENTS.md) describes replay of supplied event streams; it does not send messages, reserve resources or execute compensations. Each catalog entry and result carries its own sources and limits.

[Documentation inventory](DOCUMENTATION-CONFORMANCE.md) accounts for code fences and runs explicitly declared inert cases. The [portable finite export](PORTABLE-FINITE.md) produces a local reproducible source bundle and checks its fixed conformance corpus outside the checkout; no artifact is published.

## Numerical interpretation

The field fixture solves `-k u'' = f` with `u(0)=u(L)=0` and manufactured `u=A(x/L)^2(1-x/L)^2`. Inputs are metres, W/(m K), and kelvin relative to the boundary temperature; forcing and residual have W/m³ units. Central finite differences give a nonzero discretization error even when the algebraic residual is exactly zero. The experiment reports both and compares meshes; the known quartic error provides an independent reference. The discretization follows the [author's finite-difference Poisson course material](https://math.mit.edu/classes/18.086/2007/).

Full-metric reconciliation minimizes `(y-x)^T M (y-x)/2` subject to `Cy=d`. Positive-definite `M` and independent constraint rows make the KKT witness sufficient for the unique supplied finite optimum. Original observations remain unchanged in the receipt. [Boyd and Vandenberghe's convex optimization text](https://web.stanford.edu/~boyd/cvxbook/) provides the equality-constrained quadratic and duality basis.

The quantum-resource experiment simulates ideal uniform-state [Grover search](https://arxiv.org/abs/quant-ph/9706033) using two rational amplitudes scaled by `1/sqrt(N)`. It includes one final verification query and displays overshooting, rather than assuming more iterations always help. Oracle construction, loading, physical gates, noise, ancillas and elapsed runtime remain unspecified; no quantum hardware is invoked.

## Meaning and evidence

The supplied models and their mathematical mappings are explicit. Fitting an ordered-count model does not establish a quantum model of a person. A graph cut does not establish physical holography. Source-linked compression preserves declared spans, but cannot certify that every necessary nuance was declared. Numeric smoothing does not establish prompt-injection resistance. Those are empirical or semantic questions that require additional evidence.

Regression tests use independent known solutions, exhaustive small references, changed held-out data, invalid witnesses, provenance drift, type substitutions and bounded failure cases. They run with isolated stores and refusing model/effect paths. Receipt replay checks repeatability; these independent tests check adapter behavior. Prior unsuccessful model construction attempts remain in the separate field execution record.
