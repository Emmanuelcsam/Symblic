# symblic/policy: choosing a routing policy without fooling yourself

**What this package explores.** Which model should answer which part of a task? A tempting answer is to try a
few routings, keep the one that "worked best" and move on. This package makes that choice auditable: the
candidate policies, the cases, the budget and the objective are frozen *before* any outcome is collected; the
selector only ever sees training records; held-out cases must not share any declared identity with training;
and the chosen policy is compared with a baseline on held-out cases it was never tuned on. It is finite
candidate selection, not machine learning: the answer is always one of the policies you listed.

**Status: prototype.** The selector, the experiment store and the graph runner are tested with temporary
stores and fake model providers (56 tests). No real-model routing improvement is claimed: this repository
contains no such measurement.

## The modules

| Module | What it does |
| --- | --- |
| `learning.py` | The pure selector: `select()` on training records only, `validate_split()` for the train/held-out separation, `evaluate_heldout()` to compare the frozen choice with the baseline. Also a small command line (`hash`, `select`, `evaluate`). |
| `store.py` | `PolicyExperiment`: a private, crash-safe directory that freezes plans and evaluator-owned fixtures, runs every (candidate, case) assignment through a runner you inject with a durable intent first, scores outputs by exact equality, then seals training and held-out results. |
| `graph.py` | `GraphPolicyRunner`: the runner for routing policies over agent graphs. Runs one assignment as a durable graph (`symblic/graph`) under the candidate policy and reports output, attempts and check receipts; recovers interrupted assignments without ever repeating an unconfirmed model call. |

## The protocol in one picture

```
freeze: training plan + held-out plan + fixtures ──► frozen.json (hashes of plans, fixtures, code)
training: every candidate × every training case ──► runner (graph.py) ──► exact-output score + call counts
seal_training: select()   ── training records only ──► selection.json (immutable)
held-out: chosen policy and baseline × held-out cases ──► runner ──► scores
seal_heldout: evaluate_heldout() ──► 'observed_improvement' or 'not_established'
```

Every result carries `measurement_status: host_declared_not_verified`, and `confidence` and `causality` are
always `not_established`: the module checks the bookkeeping, not the truth of what the runner reported.

## Outside this package

`integration/host/symblic_policy_api.py` is the original host's HTTP routes and job worker for experiments
(private store location, owner checks, launching workers as background jobs). It needs the host and is kept
for reference; its tests are in `tests/integration/` and skip without the host.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/policy -t .
```

Run from the repository root. Temporary folders and fake applicators only; no model, network or worker.

Further reading: `docs/reference/POLICY-LEARNING.md`, `docs/reference/POLICY-EXPERIMENTS.md`.
