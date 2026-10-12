# symblic.experiments — bounded research experiments with reproducible receipts

**Status: research experiments. No result is claimed.** Every module here computes an explicit, caller-supplied
finite model (a 2x2 density matrix, a small graph, a short event ledger, ...) with exact arithmetic and reports
checks, comparisons and limits. None of them calls a language model, and none of them is evidence about physical
systems, people or model behaviour. They were written by AI coding agents as explorations of ideas around
Symblic; treat them as worked examples, not findings.

What *is* engineered and tested here is the machinery around the calculations: the registry refuses stale code,
inputs are strictly bounded JSON, and every result comes back as a receipt that can be recomputed.

## What is in this package

| Module | What it does |
|---|---|
| `registry.py` | The entry point. Lists the experiments (`catalog`), runs one (`run`) and recomputes a saved receipt (`verify`). Also the command line. |
| `quantum.py` | Question-order projector models, density matrices and POVMs, exact circuit-rewrite checks, tensor composition. Also the shared input helpers the other modules import. |
| `context.py` | Source-linked context compression under a byte budget; pinned short ids for repeated SHA-256 values. |
| `geometry.py` | Symplectic versus explicit Euler integration; Fisher versus ordinary gradient updates. |
| `graph.py` | Grows a small integer arithmetic graph on training cases, freezes it, then evaluates held-out cases (runs native Symblic graphs). |
| `sampling.py` | Seeded particle filter against the exact posterior; Ising energy search against exhaustive search; noisy codebook decoding. |
| `structure.py` | Finite matroids, boundary graph cuts by max-flow and by exhaustion, graph smoothing. |
| `resources.py` | Ideal Grover search probabilities versus classical sampling with the same query budget. |
| `numerics.py` | Mesh-refinement of a manufactured heat field, SPD-metric reconciliation, transport-plan certificates (runs native Symblic programs). |
| `transport.py` | Cellular-sheaf consistency; finite schema and predicate transport. |
| `protocols.py` | Replays message and resource ledgers; plans saga-style compensation as inert data. |

Each adapter module exposes `catalog()` (id, title, summary, example input, sources, limits) and
`run(experiment_id, data)`. The registry is the only intended caller.

## How the pieces fit

```
python3 -m symblic.experiments.registry run ID input.json
    └─ registry.run(ID, data)
         ├─ strict bounded JSON copy of the input (no floats: write exact numbers as "2/3")
         ├─ _identity(adapter): SHA-256 pins of the adapter, its DEPENDENCIES and the registry itself,
         │    each checked against its import marker (symblic.mica.source_identity)
         ├─ adapter.run(ID, copy)      pure calculation
         ├─ refuse if the adapter mutated its input or any pinned source changed meanwhile
         └─ receipt = {input, output, implementation_sha256, ...} + sha256 over all of it
```

A receipt proves: this exact input, run by these exact source files, gave this output. `verify` recomputes it.
It is not a signature and not an independent empirical validation; a source change invalidates old receipts.

## Run it

```sh
python3 -m symblic.experiments.registry list
python3 -m symblic.experiments.registry example circuit_rewrite > input.json
python3 -m symblic.experiments.registry run circuit_rewrite input.json > receipt.json
python3 -m symblic.experiments.registry verify receipt.json
```

Exit code 0 on success, 1 when `verify` finds a mismatch, 2 when the input or the code is refused.

## Tests

```sh
cd <repository root>
DASH_TEST=1 python3 -m unittest discover -s tests/experiments -t .
```

The identity tests copy the registry and one adapter into a temporary directory and edit the copy, so the live
sources are never touched.

## Only in the original host

In the system these experiments came from, a web page and an owner-only HTTP API called this registry. That
glue is kept in `integration/host/symblic_experiments_api.py` and does not run in this repository. Everything in
this package runs with the repository alone.

Further reading: `docs/reference/EXPERIMENTS.md` (the full mechanism catalogue).

## Sources the experiments cite

Each experiment's catalogue entry carries these links (`sources`); they are background for the calculation, not
claims that the experiment reproduces the cited work.

| Experiment | Source |
|---|---|
| `question_order_fit` | Wang, Solloway, Shiffrin and Busemeyer, "Context effects produced by question orders reveal quantum nature of human judgments", PNAS 2014 — <https://jbusemey.pages.iu.edu/quantum/PNAS2014.pdf> |
| `density_measurements` | Watrous, *The Theory of Quantum Information* — <https://cs.uwaterloo.ca/~watrous/TQI/TQI.pdf> |
| `circuit_rewrite` | <https://arxiv.org/abs/1307.7025> |
| `tensor_semantics` | Coecke, Sadrzadeh and Clark, "Mathematical Foundations for a Compositional Distributional Model of Meaning" — <https://arxiv.org/abs/1003.4394> |
| `hamiltonian_integrators` | Hairer, geometric numerical integration lecture notes — <https://www.unige.ch/~hairer/poly_geoint/intro.pdf> |
| `fisher_gradient` | Amari, "Natural Gradient Works Efficiently in Learning", Neural Computation 1998 — <https://doi.org/10.1162/089976698300017746> |
| `particle_filter` | Doucet and Johansen, "A Tutorial on Particle Filtering and Smoothing" — <https://www.stats.ox.ac.uk/~doucet/doucet_johansen_tutorialPF.pdf> |
| `ising_search` | Lucas, "Ising formulations of many NP problems" — <https://arxiv.org/abs/1302.5843> |
| `noisy_codebook` | <https://arxiv.org/abs/1603.04246> |
| `finite-matroid` | Edmonds, "Matroids and the greedy algorithm" (1971) — <https://doi.org/10.1007/BF01584082>; Adiprasito, Huh and Katz, "Hodge Theory for Combinatorial Geometries" (motivation only) — <https://arxiv.org/abs/1511.02888> |
| `boundary-graph-cut` | Bao et al., "The Holographic Entropy Cone" (2015) — <https://arxiv.org/abs/1505.07839>; Ryu and Takayanagi, "Holographic Derivation of Entanglement Entropy from AdS/CFT" (motivation only) — <https://arxiv.org/abs/hep-th/0603001> |
| `graph-smoothing` | Shuman et al., "The Emerging Field of Signal Processing on Graphs" — <https://arxiv.org/abs/1211.0053> |
| `grover-query-comparison` | Grover, "Quantum mechanics helps in searching for a needle in a haystack" (1997) — <https://arxiv.org/abs/quant-ph/9706033> |
| `field-refinement` | MIT 18.086, Mathematical Methods for Engineers II (2007) — <https://math.mit.edu/classes/18.086/2007/> |
| `spd-reconciliation`, `transport-certificate` | Boyd and Vandenberghe, *Convex Optimization* — <https://web.stanford.edu/~boyd/cvxbook/> |
| `cellular-sheaf` | Hansen and Ghrist, "Toward a Spectral Theory of Cellular Sheaves" — <https://arxiv.org/abs/1808.01513> |
| `finite-schema-transport` | Spivak, "Functorial Data Migration" — <https://arxiv.org/abs/1009.1166> |
| `saga-compensation-plan` | Garcia-Molina and Salem, "Sagas" (1987) — <https://www.cs.princeton.edu/research/techreps/598> |

The context and protocol experiments cite Symblic's own design documents (`docs/reference/SOURCE-WITNESSES.md`,
`RESEARCH-TRANSFER.md`, `EFFECTS.md`, `AGENT-GRAPHS.md`); the graph experiment cites the modules it runs.
