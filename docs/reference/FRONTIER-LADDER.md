# Frontier ladder: one frozen small model, one budget, six compiler rungs

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

This is a prepared experiment. It has not been run. Preparing it made no model call, froze no benchmark and started no cluster job. It fixes a small local model (by default `qwen2.5:0.5b`), its digest, one physical node and one caller budget. Then it changes only the compiler: the six MICA modes. The result shows which task families reach an independent hidden pass at which rung.

| File | Role |
|---|---|
| `tools/scripts/symblic_frontier_ladder.py` | Planner. `plan` prints every operator command and writes a private plan JSON. `materialize` writes the planned inputs. `aggregate` reads the bench reports. It never freezes, runs, calls a model or contacts the dashboard. |
| `benchmarks/frontier/*.fixture.json` | Six evaluator-owned fixtures, F1 to F6, in the exact `symblic.mica.bench` fixture shape. |
| `benchmarks/frontier/ladder.json` | Manifest: family order, titles, counts, the shared budget and each file's SHA-256 pin. |
| `tests/integration/test_symblic_frontier_ladder.py` | Freeze-only fixture checks, plan shape, aggregation over synthetic bench files, argument refusals. |

## Hypothesis

**Capability can come from organization, not only from weights.** Hold the weights, node and caller budget fixed. Change only how the work is organized: one whole program, a generated decomposition, decomposition after a verified failure, empirical routing or bounded search over alternative plans. If some of these rungs reach hidden passes on families that the whole-program rung misses, organization changed what the same model could build.

What would count against it: passes only at `direct`, passes nowhere, or passes that differ between rungs no more than the noise pairs described below.

What it cannot show: general capability, statistical significance from one repetition, held-out generalization, or which mechanism inside a mode caused a pass. A mode bundles several factors.

Current evidence does not yet support the hypothesis. The matched `qwen3:4b-instruct` development pilot (1,800 s and 24 calls per assignment) has no hidden pass. Its retained report holds 7 receipts for 12 assignments. The two whole-program arms of the arithmetic task (`direct` and `decompose_on_failure`) each produced an artifact in 2 calls and about 470 s that failed 1 of 51 hidden cases. The four decomposed arithmetic arms exhausted their budgets. One strict-JSON arm was blocked and paused the driver, and five remain pending. This ladder tests the claim on a smaller model with an easier first family.

## Controls

| Control | How it is held | Limit |
|---|---|---|
| Frozen model | One inventory row `{engine, model, node, digest, ready, available, ...}` sits in every arm's frozen controls. The MICA CLI refuses a run whose inventory or construction implementation differs from the freeze (`benchmark_controls`). | A digest is a provider manifest observation, not an attestation of loaded weights. No operator route supplies one; see Step 1. |
| Equal budgets | All fixtures carry one normalized budget. The bench refuses unequal budgets inside a freeze (`unequal_caller_budgets`), and control overrides cannot change it. The planner applies the same budget to every family. | Equal caller budgets do not equalize prompt length, inference speed or information. |
| Hidden oracle | Hidden cases stay in the evaluator. They never enter the request, prompts, repair feedback or the runner. They are graded by `symblic.js.check` only after `done`. | Finite tests establish TESTED, not PROVEN. |
| Seeded order | Inside a family block, the bench's balanced Latin-square order decides which rung runs at which position. The planner picks one seed per family so that no rung holds the same dispatch position in two families (a Latin rectangle with one repetition). | Counterbalancing spreads warm-up, cache and heat drift over the rungs. It does not remove them. |
| One node | One inventory row: every call goes to that node through the admitted fleet-runner lane, under the per-node model lock. Sessions run one at a time. | Results describe one machine. |
| One compiler build | The freeze pins the construction implementation identity. The aggregator compares the frozen implementation digest across families. | The live checkout changes often: MICA.md, `symblic/mica/bench.py` and `symblic/mica/contracts.py` changed on disk at 21:19 (host local time) while this plan was being written. Freeze all families back to back. |

## The ladder: a rung is a mode

The bench freezes all six modes for every fixture. One freeze per family therefore contains every rung, and the "compiler ladder" is the set of six arms inside each family block. Reading another rung means reading another arm of the same frozen experiment, under the same budget, model and order design.

| Rung | Mode | First plan | Empirical routing | Alternative plans |
|---|---|---|---|---|
| 1 | `direct` | whole program | no | no |
| 2 | `static` | generated decomposition | no | no |
| 3 | `decompose_on_failure` | whole program | no | after a verified failure |
| 4 | `capability` | generated decomposition | yes | no |
| 5 | `search` | generated decomposition | no | yes |
| 6 | `mica` | generated decomposition | yes | yes |

The rungs are the operator's chosen order, not a nested hierarchy: rung 3 starts from a whole program and rung 2 has no alternatives. With one inventory row, empirical routing has nothing to choose between. Rung 4 should therefore behave like rung 2 and rung 6 like rung 5. Those two pairs are built-in noise estimates, not routing measurements.

## Task families

| Key | Exports | Structure | Requirements | Public tests | Hidden cases (invalid input) | Request size |
|---|---|---|---|---|---|---|
| F1 | `gcd`, `lcm`, `isPrime` | Three pure integer functions; exact `lcm` up to 2^53-1, bounded `isPrime` | 4 | 4 | 56 (16) | 1,996 chars |
| F2 | `slugify`, `padLeft`, `wordCount` | String rules with NFD, code points and `\p{L}`/`\p{M}`/`\p{Nd}` | 4 | 7 | 56 (11) | 2,718 chars |
| F3 | `groupBy`, `histogram`, `sortBy` | Own-key results for `__proto__`, `constructor` and `toString`; stable sort in both directions | 6 | 7 | 52 (15) | 3,504 chars |
| F4 | `tokenize` | Scanner with three token classes, longest match, positions and character errors | 3 | 4 | 46 (18) | 2,719 chars |
| F5 | `tokenize`, `parse`, `evaluate` | F4's tokenizer, recursive descent with precedence and right-associative `^`, tree output, evaluation errors | 8 | 8 | 59 (26) | 5,196 chars |
| F6 (optional) | `vend` | Sequential state machine: credit state, four event kinds, one output per event | 5 | 3 | 48 (13) | 3,014 chars |

The default ladder is F1 to F5; F6 is available with `--families F1..F6`. The difficulty order is an authoring judgment about structure, not a measurement.

Every fixture uses the request shape of `symblic.mica.fixtures`: explicit requirements with `TESTED` acceptance, exact export signatures, public tests that cover every requirement, and one script output `result.js`. The split is `dev`. The budget is 300 s wall and 8 calls per assignment. Every other field is at the current default: 4 candidates, depth 4, 64 units, 3 workers, 2 retries and 32,768 context characters. Hidden calls never repeat a public call. They cover ordinary values, boundaries (zero, the 2^53-1 limit, empty input, ties, astral characters) and invalid input (wrong types, out-of-range values, malformed text) through the same `e instanceof Error` convention as the strict JSON fixture.

Authoring-time validation (2026-10-10, about 21:41):

- An independent Python oracle computed every expected value.
- Hand-written reference implementations passed every public and hidden case through the actual grader, `symblic.js.check.test`, on node 22.17.0 with adapter 12. Public and hidden results: F1 4/4 and 56/56; F2 7/7 and 56/56; F3 7/7 and 52/52; F4 4/4 and 46/46; F5 8/8 and 59/59; F6 3/3 and 48/48. Every family is therefore solvable as written, and the oracle values match JavaScript semantics.
- Plausible naive implementations that pass every public test still fail hidden cases: F1 9, F2 12, F3 13, F4 4, F5 12, F6 12. A public pass is not a hidden pass.
- The generator and both implementations stayed outside the repository, so no reference solution sits beside the fixtures. The manifest pins each file. The planner refuses a fixture that no longer matches its pin.

These are development fixtures written and inspected here, not a held-out benchmark. Each `*.fixture.json` file contains its hidden cases. Only its `request` field may enter a construction context.

## Budget, time and heat

The planning estimate is **assignments x (wall budget + 120 s grading allowance)**. The 120 s figure is the matched pilot's explicit grading bound, used here as an allowance. The CLI's default grader has no explicit deadline. Its worst case is 15 s plus 7 s per hidden case (428 s for F5). That worst case happens only when cases time out, and a timeout makes the grade unknown rather than failed. Estimates are planning figures, not bounds.

| Budget | Repetitions | Per family session | Five families | Within about an hour per session? |
|---|---|---|---|---|
| 300 s, 8 calls | 1 | 6 x 420 s = 2,520 s (42 min) | 12,600 s (3.5 h) in five sessions | yes |
| 300 s, 8 calls | 2 | 5,040 s (84 min) | 25,200 s (7 h) | no |
| 1,800 s, 24 calls (pilot budget) | 1 | 6 x 1,920 s = 11,520 s (3.2 h) | 57,600 s (16 h) | no |

Start with the 300 s, 8-call rung and one repetition. That is one family per session within about an hour of continuous worker node load. Rest the node between sessions until the Step 1 routes show it idle, and never chain sessions past about an hour without the operator's agreement. A session over the hour bound needs the operator's explicit approval first; the planner marks every such session `over_hour_bound` and adds a `session_exceeds_hour_bound` confound. Power stays normal: no the temporary high-power mode and no power setting changes.

An empty table at 300 s is a budget result, not a capability verdict. On a CPU-only node, 300 s may allow only a few calls of a 0.5B model.

## Operator commands, in order

The planner prints these commands with exact paths, IDs and seeds. Its output is authoritative; the lines below are its output for this example. `node-d` is an example only. In the cached catalogue receipt of 2026-10-10 23:29 UTC, `qwen2.5:0.5b` was listed as ready on node-a, node-b, node-d and node-f. Choose a node that is idle and that no other experiment is using.

**0. Plan** (writes `experiments-plan/frontier-plan.json`, mode 0600 in a 0700 directory; refuses to replace a different plan unless you pass `--replace`):

```bash
python3 tools/scripts/symblic_frontier_ladder.py plan \
  --model qwen2.5:0.5b --node node-d \
  --root ~/.local/state/symblic-frontier-20261010/experiments \
  --budget-seconds 300 --max-calls 8 --repetitions 1 --families F1..F5
```

Add `--digest HEX` once you have a pin; `--json` prints the plan JSON instead of text. With the default base seed 20261010, the family seeds are F1 20261010, F2 20261011, F3 20261019, F4 20261025 and F5 20262007.

**1. Read-only checks, before freezing and before every session.** Read these yourself; the planner prints them and never calls them:

```bash
curl -s 'http://127.0.0.1:8080/api/automation/symblic/mica/inventory'   # a qwen2.5:0.5b row on the node, ready and available
curl -s 'http://127.0.0.1:8080/api/runner/fleet'                        # cached node facts: ollama_models, ollama_sizes, caps_age
curl -s 'http://127.0.0.1:8080/api/runner/runs?status=active'           # no run on the node
curl -s 'http://127.0.0.1:8080/api/cluster/status?force=1'              # node online and fresh
curl -s 'http://127.0.0.1:8080/api/cluster/capacity'                    # not overcommitted, no operator reservation
curl -s 'http://127.0.0.1:8080/api/cluster/nodepower/state'             # phase ready; no fence, drain or transition
curl -s 'http://127.0.0.1:8080/api/cluster/power/state'             # enabled false, phase off
```

**Digest pin.** No operator route returns a model digest. `GET /api/automation/symblic/mica/inventory` sets `digest` to null by construction (`discover_inventory`), and `/api/runner/fleet` lists names and sizes only. the fleet runner observes the Ollama manifest digest on each call by reading `/api/tags` before and after (`result.meta.model_identity`). MICA retains it as `observed_digest` in `mica-provider-evidence.jsonl`. Take the pin from such a retained observation for this exact model and node, and record its file and row hashes as the matched pilot did in `historical-digest-provenance.json`. Pass it as `--digest`; a `sha256:` prefix is stripped. Without a pin, the row carries `digest: null`. That is an explicit cold start: drift inside one run is still refused, but the families are not pinned to one set of weights. The plan then lists `digest_unpinned` as a confound.

**2. Materialize the inputs.** This writes `inventory.json` (and re-budgeted fixture copies if the budget differs from 300 s and 8 calls), creates `pins/` and `runs/`, and creates the experiment root's parent. The bench refuses to create a root whose parent is missing. Existing files with different content are refused, never overwritten.

```bash
python3 tools/scripts/symblic_frontier_ladder.py materialize \
  --plan ~/.local/state/symblic-frontier-20261010/experiments-plan/frontier-plan.json
```

**3. Freeze every family, back to back, before any run.** One freeze per family holds all six rungs. `noclobber` keeps a retained pin from being overwritten by a repeated command:

```bash
(set -o noclobber; tools/symblic mica benchmark --root ~/.local/state/symblic-frontier-20261010/experiments --id frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1 --fixture benchmarks/frontier/F1-integer-arithmetic.fixture.json --inventory ~/.local/state/symblic-frontier-20261010/experiments-plan/inventory.json --repetitions 1 --seed 20261010 --split dev > ~/.local/state/symblic-frontier-20261010/experiments-plan/pins/frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1.freeze.json)
```

The planner prints the same command for F2 to F5 with their own IDs, fixtures and seeds. Each pin file is the CLI's JSON output (`status: frozen`, `freeze_sha256`, the empty report), retained outside the experiment store.

**4. Run one family per session, serially, on the one node.** Recheck Step 1, launch one session and wait for it to finish, then rest the node before the next. The bench's own `--run` dispatches the frozen assignments one at a time in frozen order. Re-running the same command resumes pending assignments and never replays an unknown one. Unlike the matched pilot driver, the bench CLI does not halt after an unknown or blocked assignment. If a session reports any, stop and investigate before the next session. The command launches that CLI entry point in its own `a systemd slice for work` scope, as the matched pilot did:

```bash
FREEZE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["freeze_sha256"])' ~/.local/state/symblic-frontier-20261010/experiments-plan/pins/frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1.freeze.json) && STAMP=$(date -u +%Y%m%dT%H%M%SZ) && systemd-run --user --scope "--unit=symblic-frontier-f1-$STAMP" --slice=a systemd slice for work --property=CPUQuota=150% --property=MemoryMax=2G --property=TasksMax=256 --property=RuntimeMaxSec=3780 --working-directory=the host checkout env DASHBOARD_DIR=the host checkout nice -n 10 the host checkout/.venv/bin/python -I -B -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); import symblic.mica.cli as cli; sys.exit(cli.main(sys.argv[1:]))' the host checkout benchmark --root ~/.local/state/symblic-frontier-20261010/experiments --id frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1 --inventory ~/.local/state/symblic-frontier-20261010/experiments-plan/inventory.json --freeze "$FREEZE" --run > "~/.local/state/symblic-frontier-20261010/experiments-plan/runs/frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1.run-$STAMP.json" 2> "~/.local/state/symblic-frontier-20261010/experiments-plan/runs/frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1.run-$STAMP.err"
```

The documented form, `tools/symblic mica benchmark ... --freeze "$FREEZE" --run`, takes the same CLI path. The planner also prints that form, but `tools/symblic` runs inside `symblic.kernel.process_limits` limits: 120 CPU-seconds and a 2 GiB address space. A long session may use up that CPU allowance in the controller process; this was not measured. The process would then be killed mid-assignment, and that assignment would stay unknown and never be replayed. The scope's `RuntimeMaxSec` is 1.5 times the session estimate. It exists to stop a runaway session: a scope stopped by it also leaves its current assignment unknown.

**5. Status, at any time (read-only):**

```bash
FREEZE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["freeze_sha256"])' ~/.local/state/symblic-frontier-20261010/experiments-plan/pins/frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1.freeze.json) && tools/symblic mica report --root ~/.local/state/symblic-frontier-20261010/experiments --id frontier-f1-qwen2.5-0.5b-node-d-300s-8c-r1-s20261010-v1 --freeze "$FREEZE"
```

**6. Aggregate (read-only).** This uses `symblic.mica.bench.MicaBenchmark(...).report()` for every family with a retained pin. Add `--json` for the full structure, and `--pin ID=SHA` if a pin was retained elsewhere:

```bash
python3 tools/scripts/symblic_frontier_ladder.py aggregate \
  --plan ~/.local/state/symblic-frontier-20261010/experiments-plan/frontier-plan.json
```

## How to read the table

- **A cell is one family at one rung.** `Pass k/n` counts assignments that finished `done`, passed every hidden case and stayed within the call budget. That is the bench's own `success`.
- **n is every planned assignment.** Pending, unknown, damaged, blocked, stopped, not yet frozen and unreadable experiments all stay in it as non-passes. `Outcomes` shows which, with grade statuses and over-budget counts. A family without a retained pin appears as `not_frozen`. A pin file that holds a failed freeze appears as `pin_unreadable`.
- **With one repetition, a cell is a single observation.** A pass means the family was solved at that rung in this run, not that the rung solves it reliably.
- **The frontier is read two ways.** By rung: the families with a pass. By family: the first rung with a pass. If organization matters, passes should move up the ladder: F1 low, F2 and F3 needing decomposition, F4 and F5 needing search. Passes only at `direct`, or nowhere, give no support at this budget.
- **Compare inside a family.** Rung 1 against 2 isolates generated decomposition. Rung 1 against 3 shows decomposition after a verified failure. Rung 2 against 5 shows alternative plans. Rungs 2 against 4 and 5 against 6 are the noise pairs.
- **Calls and wall seconds** are observed totals over runs that have receipts. `(obs/n)` shows coverage: an unknown run's costs are unobserved, not zero. Wall seconds are the runner's end-to-end construction seconds, not grading time.
- **Experiments and confounds lines** report each family's state and freeze pin, the bench's confound counts (`runtime_controls_unobserved`, `budget_exceeded`, declared control differences), `frozen_controls_differ_from_plan` and `construction_implementation_differs_across_families`. The frozen-controls check reads each frozen plan with the same loader the CLI uses. It compares split, repetitions, seed, request digest, budget, inventory and arm controls against the plan.
- **Never re-run an unknown assignment.** The bench never replays one; investigate it instead.

## Confounds and limits

- **CPU-only inference.** A wall budget measures inference speed as well as competence. Heat and competing load change that speed within a session.
- **Prompt size against a 0.5B context.** Requests range from 1,996 to 5,196 characters before declared JSON schemas and decomposition capsules. MICA bounds provider context at 16,384 tokens and output at 4,096 tokens. A failure on a larger family can be a context failure, not a reasoning failure.
- **Cache state.** Model loads, page cache and Ollama state carry over between assignments. The seeded order spreads them over the rungs but does not remove them.
- **Dependent repetitions.** Repetitions reuse the same fixture, model and node. Rates are descriptive.
- **Sampling.** The native adapter does not apply the experiment seed to provider sampling; the seed fixes assignment order only.
- **Unpinned digest.** Without `--digest`, the families are not pinned to one set of weights.
- **Implementation drift.** A source change after a freeze makes the run refuse. A change between freezes makes families incomparable; the aggregator reports it.
- **Single routes.** Rungs 4 and 6 have nothing to route between; see the noise pairs above.
- **Grading time.** The CLI path grades without an explicit deadline. A case timeout yields an unknown grade.
- **Fixture provenance.** The fixtures were authored and inspected here. They show development behavior, not held-out generalization. The difficulty order is designed, not measured.

## Mismatches found while preparing

- MICA.md's benchmark example passes `--split dev` with the seeded demo fixtures. `symblic.mica.fixtures` labels those fixtures `heldout`, and a freeze that way fails with `ProtocolError: Requested split has no cases`. This was verified with a freeze-only check on 2026-10-10. The CLI default split is also `dev`. The frontier fixtures are labelled `dev`, and every planned freeze passes `--split dev`.
- MICA.md documents `tools/symblic mica benchmark ... --run` but not the wrapper's limits: RLIMIT_CPU 120 s soft and 122 s hard, plus 2 GiB of address space, from `symblic.kernel.process_limits.CPU_SECONDS['cli']`. This plan launches the same CLI entry point in a scope instead.
- MICA.md treats a missing catalogue digest as a cold start. The current operator inventory route never supplies a digest, so every catalogue-derived row starts cold unless a retained provider observation supplies the pin.
- The 120 s grading bound exists only in the matched pilot driver; the bench CLI's default grading has no deadline.
- The bench creates the experiment root but not its parent; a missing parent fails as `private_directory`. `materialize` creates the parent.

## Verification of this preparation

`TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 nice -n 10 python3 -B -m unittest tests.integration.test_symblic_frontier_ladder -v` runs the checks. They cover:

- Manifest pins.
- Fixture schema and bounds.
- A six-rung freeze for each fixture, and one freeze holding all six fixtures. A one-second budget difference is refused.
- Planned orders that match the frozen bench orders.
- The plan JSON shape. Every printed freeze and run command is parsed by the MICA CLI's own parser, and the printed F1 freeze is executed through `symblic.mica.cli.main` (freeze only, with an injected implementation identity).
- Rebudgeted copies and the over-hour flag.
- Aggregation over bench intent and outcome files written with the bench's own store helpers. Those files cover passed, failed, exhausted, budget-exceeded, unknown and pending assignments, families that are not frozen, wrong pins and failed-freeze pins.
- Argument refusals, refusal of `--run`, `--execute`, `--launch` and `--dispatch`, and an inert module level.

The tests use stub evaluator and implementation identities. They call no model, run no assignment and execute no JavaScript. Every bench store is a temporary directory.
