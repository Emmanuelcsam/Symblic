# Symblic as an autonomous capability compiler

Design document and research plan, 2026-10-10. It turns the operator's "Beyond LLMs" conversation with ChatGPT into Symblic's architecture: what already exists, what is a named gap, and how the conversation's thought experiment becomes a runnable measurement. Nothing in this document is a new receipt. Statuses below cite existing receipts from [MICA.md](MICA.md), [MICA-SOURCES.md](MICA-SOURCES.md), the autogen modules and the atomic study results; where none exists the row says so.

The conversation's statements are treated as **proposals**, not findings. Several are plausible, a few are already partly implemented, and none has been demonstrated end to end by Symblic on a real local model with an independent hidden evaluation. The operator asked for the thought experiment to be attempted rather than declared impossible; section 5 is that attempt, written as a protocol.

Status words used throughout:

| Word | Meaning |
|---|---|
| implemented | Code exists in the repository |
| tested | Focused isolated tests pass (private stores, fake provider boundaries) |
| live | Installed on the dashboard and exercised through the operator API or CLI |
| gap | Not built; named here so it is not mistaken for a capability |

## 1. Position

**Name.** The project stays Symblic. The technical description is the one the conversation preferred: an *autonomous capability compiler*. The purpose statement the conversation proposed is adopted as a target, not as a description of current results: "Symblic is an autonomous capability compiler that transforms declarative objectives into optimized, contract-governed computational graphs executable by heterogeneous AI models and deterministic algorithms." Today "optimized" is not established (MICA's frontier is a bounded neighbourhood, not a global optimum) and "autonomous" is established only for the steps listed as live below.

**The compiled object is the construction graph.** The conversation calls it a cognitive execution graph (CEG). In Symblic it already has a concrete form:

- Nodes are contracts `U = (S, I, O, D, V, E, B)`: required behaviour, input artifacts, output artifacts, dependencies, verification obligations, permitted effects, budget (`symblic/mica/contracts.py`, the field list in MICA.md "Execution path"). Each node is implemented by exactly one of: a scoped native model ask, a declared finite deterministic constructor, a rechecked library component, or (in autogen) one fresh agent task.
- Edges are declared dependency artifacts. `validate_plan` requires `uses` and `dependency_contract_ids` to agree exactly and every input artifact to come from a declared dependency output.
- Acceptance is code only: interface, unit, integration and original root checks in MICA; file existence, syntax, the operator's public commands and a disk change cross-check in autogen.
- Revision is recorded: MICA's frontier keeps scored AND/OR graph alternatives and frozen decisions (`symblic/mica/strategy.py`); autogen keeps a statement tree whose nodes split under failure (`symblic/autogen/coordinator.py`).

**The conversation's formula maps onto existing inputs.** `P = Compile(S, M, T, B)`: S is the normalized request (`normalize_request`) or autogen's statement lines plus checks; M is the explicit inventory (exact model, physical node, observed digest); T is the native JavaScript checker, the affine constructor, finite refinement and frozen checkpacks; B is the normalized request budget (`max_calls`, `max_candidates`, `max_depth`, `max_units`, `max_workers`, `retries`, `context_chars`, `wall_seconds`) or the autogen policy (`agents_max`, `wall_seconds`, ...). `y = Execute(P, x)` is `MicaRun` producing an assembled script or module bundle, or an autogen run promoting accepted files into a git workspace.

### Concept map

| Conversation concept | Module or command today | Status | Honest receipt |
|---|---|---|---|
| A model call as a primitive unit | Typed native ask (`symblic/mica/native.py`); one fresh agent per statement (`integration/host/symblicos_tasks.py`, `tools/symblic-task`) | live | MICA CLI/API/panel installed 2026-10-10; MICA.md: "actual successful local-model demonstrations ... remain pending" |
| Signals are structured data, contracts, artifact references | Contract IR, `proposal_version: 3`, declared JSON output shape (`symblic/mica/contracts.py`, `symblic/mica/proposal.py`, `symblic/kernel/json_schema.py`) | live | Rollout receipts in MICA.md; shape validation "does not establish semantic correctness or an improvement in model success" |
| Memory outside the models | Durable native journals, run store, private component library (`symblic/mica/library.py`) | tested | `test_compatible_cross_run_reuse_makes_no_provider_calls`; library is disabled in benchmarks |
| Control flow | Ready-layer DAG scheduling, at most three worker threads, one model per physical node (`symblic/mica/search.py`) | tested | 304 isolated checks on node-i (`mica-check-20261010-182035`); counts are software verification, not model success |
| Error correction | Bounded repair, scoped refinement (`symblic/mica/refinement.py`); autogen regeneration with public feedback (`symblic/autogen/policy.py`) | tested | `test_native_repair_receives_public_counterexample_then_passes` (fake provider) |
| Adaptation without weight changes | Wilson-bounded exact-identity routing, frozen calibration (`symblic/mica/routing.py`, `symblic/mica/calibration.py`) | tested | MICA.md: "routing heuristics, not calibrated population accuracy or training" |
| Architecture changes during execution | `decompose_on_failure`, `search`, `mica` modes; AND/OR frontier (`symblic/mica/strategy.py`); autogen `decompose` | tested | Frontier "neither exhaustive nor globally optimal"; never measured on real models |
| Program the objective, not the arrangement | Objective-to-request synthesis and planning (`symblic/mica/project.py`) | live | First objective-only attempts (6 and 5 calls) produced no valid plan; second pair exhausted 1,800 s budgets; no artifact, hidden tests unevaluated |
| Deterministic computation where it fits | `affine_integer_v1` (`symblic/mica/deterministic.py`), native finite constructor | tested | Planner-to-constructor journey: one planning call, zero implementation calls (fake provider). Planner use on real models unmeasured |
| Retrieve verified functions instead of regenerating | `ComponentLibrary.candidates` + recheck before reuse | tested | Exact contract/dependency/runtime identity only (section 4) |
| Deterministic verifier over stochastic candidates | Unit/root checks, evaluator-only hidden fixtures, checkpacks (`symblic/mica/checkpack.py`) | live | Checkpack freeze/public/fixture/validate journey passed on the installed CLI |
| Budget B | Normalized request budget; autogen `agents_max` and wall deadline | live | Budgets are backend controls, "not measured aggregate GPU/energy costs" |
| Cost model J(D) | Scoped host cost spans (`symblic/mica/costs.py`) | implemented | Coverage partial: remote CPU, GPU, memory, energy unmeasured |
| Model independence (swap the workers, keep the contract) | Inventory, eligibility, digest pinning; autogen `other_engine`/`stronger_model` | tested | Cold digests never borrow evidence (`test_digest_node_and_class_drift_do_not_borrow_success`) |
| Many agents per line, auto-spawn, auto-decompose, context handoff, perpetual lanes | `symblic/autogen/policy.py` (pure policy), `symblic/autogen/coordinator.py` (coordinator), `/api/symblicos/autogen/*` | implemented; routes installed | Routes went live with the 2026-10-10 fourth-release restart while lane edits continued; no recorded end-to-end autogen run receipt yet |
| Stage IV: new verified tools become primitives | Library holds TESTED components; no promotion into the planner catalogue | gap | Section 2 |
| Compile intelligence into algorithms | Only the affine family | gap beyond affine | Section 3 |
| Compose whole Symblic computations; prove the parent contract | Exact-identity reuse; finite predicate refinement | gap | Section 4 |
| Capability frontier F(m, B, T) | Six-mode benchmark (`symblic/mica/bench.py`) | implemented, unmeasured | No whole-program hidden pass yet (section 5) |

## 2. The four stages

The conversation proposes four stages. Each maps onto mechanisms that exist, with a different amount missing.

| Stage (conversation) | Symblic mechanism | Status | What is missing |
|---|---|---|---|
| I. Model network: models exchange results | Fresh task per line (`integration/host/symblicos_tasks.py`); MICA `direct` (whole program) and `static` (one generated decomposition) | live | Nothing structural; the gap is evidence of real-model success |
| II. Adaptive network: execution feedback changes the architecture | MICA `decompose_on_failure`, `search`, `mica`; autogen regeneration (`fresh`, `feedback`, `other_node`, `other_engine`, `stronger_model`), split into 2..`children` lines up to `depth`, checkpointed handoff | tested | Real-model measurement; autogen has no parent re-check after a split (section 4) |
| III. Autonomous compiler: the system chooses decomposition, models, tools, verification | MICA objective planning, clause frontier, AND/OR graph/worker frontier, empirical routing | live (planning), tested (frontier) | A plan has never been carried to an accepted artifact by a real model under hidden evaluation |
| IV. Recursively extensible system: verified outputs become new primitives | Component library; checkpack finite domains; affine constructor | gap | A promotion rule (below) |

**Stage I and II are the same engine at two settings.** A MICA request in `direct` mode is a one-node graph; `decompose_on_failure` adds a node split after a verified failure (ADaPT's method subset, MICA-SOURCES.md). Autogen is the same idea one level up: each statement is a node, each attempt an ordinary durable task with a deterministic request id, and the pure `decide()` function returns one of `launch`, `regenerate`, `decompose`, `handoff`, `perpetual_next`, `accept`, `fail`, `wait` from the durable record alone. A repeated identical (statement, depth, strategy, failure) fingerprint is refused as a cycle, so the adaptive loop cannot spend budget on an equivalent attempt.

**Recursive decomposition without caps.** [RECURSION.md](RECURSION.md) is the contract for autogen's `until_done` mode, added later on 2026-10-10. In this mode a statement that stops making measured progress is split, and a failed split is re-planned on another engine and machine. Workers may also split themselves, and a node with nothing novel left ends `stuck` (resumable) instead of failed. `decide()` now also returns `design`, `stuck` and `stop`. The current code re-checks a split parent in the project folder after its children (`_settle`, `_parent_verdict`), runs hidden commands once in `_finish`, and classifies hidden failures as `HIDDEN_FAILURE`. The autogen defect in section 4 and the three autogen rows in section 7 therefore describe the earlier code. None of this has been measured on real models.

**Stage III is where Symblic is weakest in evidence and strongest in structure.** The objective-to-graph path exists and is live, but every recorded real-model run so far has stopped before an accepted artifact (section 5).

### Proposed promotion rule (Stage IV): designed, not built

Rule: *a unit whose declared finite input domain passes exhaustively against an independent oracle becomes a deterministic tool, and the planner prefers it over a model call for any later contract with the same identity.*

A search of `symblic/mica/library.py` and `symblic/mica/checkpack.py` found no promotion code: library records carry only `assurance: "TESTED"` and are reused only under an exact `identity(contract_sha256, dependency_hashes, runtime)` key. The rule below is therefore a design.

Files that would own it:

| File | Responsibility |
|---|---|
| `symblic/mica/checkpack.py` | A `complete_domain` declaration: every parameter's finite value list, total cardinality at most 65,536, oracle origin (caller table, reference implementation, or asserted law) |
| `symblic_mica_promotion.py` (new, pure) | Admission decision: exhaustive result, domain guard present, identities pinned; returns `PROMOTED` or a refusal reason |
| `symblic/mica/library.py` | New record kind with `assurance: "EXHAUSTIVE_FINITE"`, the checkpack SHA, domain digest and oracle origin; `TESTED` records unchanged |
| `symblic/mica/strategy.py`, `symblic/mica/routing.py` | Rank a promoted zero-call component before every model route for a matching contract; never across a different contract hash |
| `symblic/mica/native.py` | Advertise promoted tools to the planner by exact signature and domain, as it already advertises the affine fragment |
| `tests/mica/test_symblic_mica_promote.py` (new at the time) | Refusals for: missing guard, partial domain, oracle derived from the candidate, identity drift, a domain value that fails |

Admission evidence required, all of it:

1. A frozen checkpack whose `complete_domain` enumerates the contract's entire declared input domain, with its SHA retained outside the run store.
2. An oracle that does not come from the candidate or from the model that wrote it (model-proposed rows are already excluded from acceptance).
3. Execution of the candidate on every domain element through the existing sandboxed checker, all passing, with the count equal to the declared cardinality.
4. A generated input guard that throws outside the domain, as `affine_integer_v1` does ("Outside declared affine integer domain").
5. Pinned contract, dependency, runtime and checker identities; any drift revokes the preference and falls back to ordinary routing.
6. Recheck on every reuse (current library behaviour, kept).

What the rule buys and what it does not: inside the declared domain, exhaustive agreement with an oracle is complete verification relative to that oracle. Outside the domain the tool refuses rather than guesses. It does not make a finite sample into a general law.

## 3. Algorithm compilation ("intelligence into algorithms")

**The conversation's proposal.** After many verified examples of an operation performed by a local model, discover the general rule, synthesize an algorithm, verify it against the specification, register it as a tool, and route future executions to it with no inference. The conversation itself notes the limit: a finite set of examples does not prove a general rule, and the idea is plausible mainly where specifications are strong or equivalence can be checked.

**What finite checks can establish.** Three distinct situations, which must never be reported as one:

| Situation | What a pass establishes | Symblic instance |
|---|---|---|
| Exhaustive over a declared finite domain, independent oracle | Correct on every input in the domain, relative to the oracle | `validate_refinement` for declared predicates (`symblic/mica/contracts.py`); the proposed promotion rule for code |
| Unique member of a declared hypothesis family consistent with the examples | Identification *conditional on the family, its bounds and the examples* | `affine_integer_v1` |
| Passing sampled tests on an unbounded domain | Evidence, not proof | Every ordinary unit and root check; hidden fixtures |

The second row is the honest form of "discover the general rule": the rule is general only within a family the caller declared in advance. If the family is wrong, uniqueness is meaningless; if several members fit, the result is underconstrained and nothing is chosen.

**The existing instance.** `symblic/mica/deterministic.py` compiles a contract that declares `construction.kind = "affine_integer_v1"`: one function, one to four bounded integer parameters, explicit coefficient and intercept ranges, one to 32 direct integer examples, at most 4,096 coefficient tuples. Native finite determination must find a unique tuple before JavaScript is emitted; the emitted function rejects inputs outside its integer domain; `model_calls` is 0; the host still runs interface, example, integration and root acceptance. The module's own scope string is the claim boundary: "Unique bounded affine coefficients conditional on declared finite examples; JS/root checks remain required." The planner advertises the fragment and can propose it; a tested journey spends one planning call and zero implementation calls, with a fake provider. Whether a real local planner chooses the fragment when it applies is unmeasured.

**A bounded plan.** Each step lands with a fixture where it fires and a fixture where it must refuse.

1. **Harvest (read-only).** Extract (contract hash, input, output) rows from accepted unit checks in retained runs. No new executor, no model call. This is the raw material the conversation's "many verified examples" refers to.
2. **More declared families,** each lowered to the existing native finite constructor exactly as the affine family is: finite lookup over an enumerated domain (at most 65,536 cases); boolean predicates over at most 12 variables within `validate_refinement`'s 10,000-case bound; integer polynomials of degree at most 2; piecewise-affine with at most two breakpoints. Uniqueness required; underconstrained and refuted results stay visible.
3. **Promotion** per section 2, only for exhaustively checked finite domains.
4. **Measurement.** On the frozen fixture families, report the fraction of unit contracts a family identifies, model calls avoided, and hidden whole-program acceptance with and without the families at equal budget. A family that does not change hidden acceptance or calls on any fixture is not kept.
5. **Stop rule.** No family is admitted without a refusal test; no promoted tool is used across a contract hash change.

This plan does not attempt general program synthesis, SMT verification of JavaScript, or learned rule discovery. Z3, CrossHair and Dafny were inspected and not adopted as runtimes (MICA-SOURCES.md).

## 4. Composition of Symblic computations

The conversation proposes networks of Symblic computations: one complete construction graph becomes a component whose single contract hides thousands of internal calls, and a parent verifies the combined behaviour. It names the hard part correctly: local correctness of each component does not establish the parent contract.

**What composes today, inside one run.** Contracts declare dependencies; `validate_plan` requires `uses` and `dependency_contract_ids` to agree exactly and every `input_artifacts` path to be an output of a declared dependency. Complete dependency artifact identity includes the dependency's contract, so identical source under a changed requirement is a different dependency. After units pass, MICA assembles deterministically and reruns integration checks and the *original* public root checks; a unit that passes its own examples can still be rejected at the root (`test_root_acceptance_rejects_candidate_that_passes_its_own_examples`). A contract may also carry `finite_refinement` obligations: `validate_refinement` exhaustively checks a declared premise-implies-conclusion over finite variable domains (1..12 variables, at most 10,000 cases) and a refuted obligation refuses the plan. That check links predicates to predicates; it does not link the predicates to the emitted JavaScript.

**What composes today, across runs.** `MicaRun` publishes each accepted unit with `ComponentLibrary.publish(contract_sha256, dependency_hashes, runtime, code)`; a later run looks up `candidates(key)` under the exact identity and reruns current interface, unit and root checks before reuse (at most eight variants per identity). So a later request reuses an earlier result only when its own planner happens to produce a byte-identical contract with identical dependency hashes. A request cannot name an earlier run's artifact as an input. The only cross-artifact pin today is the Forge adapter, which verifies five original artifact hashes of one accepted Forge handoff before execution; it consumes a specification, not a MICA result.

**What composes in autogen.** A split node is marked accepted when all its children are accepted (`AutogenManager._current`, `symblic/autogen/coordinator.py` lines 385-408). The parent's own checks are not rerun at that point: `_verdict` keys the operator's public commands by top-level index and a child uses its own id (line 585), and hidden commands run only on the last *top-level* statement (line 623). A split therefore bypasses the parent statement's public commands, and splitting the last statement bypasses the hidden commands entirely. This is exactly the local-correctness gap the conversation warns about, and it is a defect, reported with a fix below.

**What parent-contract verification would need.**

1. **Autogen, immediate.** When every child of a split is accepted, run the parent's `plan_checks` (existence, syntax, its public commands) and, for the last top-level statement, the hidden commands, in the project workspace before marking the parent accepted; on failure mark the parent failed with a `split_verification` reason.
2. **MICA imports.** A request-level `imports` field naming `{artifact_sha256, contract_sha256, exports, origin}`; admission rereads the retained bytes against the digest, reruns the imported component's original checks under the current runtime, and treats the import as a dependency artifact for `validate_plan`. Operator: `symblic/mica/contracts.py` (field and validation), `symblic/mica/search.py` (resolution), with tests for digest drift and contract drift.
3. **Assume-guarantee obligations.** The consumer states what it assumes of the import as predicates; the import's contract states what it guarantees; a `finite_refinement` checks guarantee implies assumption on a finite domain. This uses `validate_refinement` unchanged.
4. **Code-to-predicate link.** To establish `{P} C1 {R}` and `{R} C2 {Q}` (the sequential-composition rule in astra-prompt Part VI) for emitted code, execute each unit across a finite domain of P-satisfying inputs and check R on its outputs, then check the chain. This is the same exhaustive mechanism as the promotion rule; on unbounded domains the result stays TESTED, never PROVEN, as MICA already enforces for `PROVEN` requirements.

## 5. The thought experiment as a runnable protocol

**The question (conversation).** Fix one frozen 0.5B model, no other model, no training. Allow storage, conventional algorithms, verification and reorganization within a budget. What is the hardest problem the system solves autonomously? Then change only the compiler. If a newer compiler solves a class the older one did not, at the same model, weights, hardware and budget, the gain came from the computational organization. Repeating this across task families would relate individual model capability to the structures that amplify it.

**Formal target (astra-prompt Part III).** `S(m, D, B, T) = P(program accepted)` measured with independent whole-program tests; the frontier `F(m, B, T)` is the best S over the admissible decomposition strategies. Symblic can only estimate F over the strategies its compiler versions implement. That estimate per compiler version is the measured quantity.

### Fixed factors

| Factor | Setting |
|---|---|
| Model | `qwen2.5:0.5b`, listed by the fleet catalogue on node-a/b/d/f/i (the atomic study ran it on node-b and node-f). A second, separate arm uses `qwen3:4b-instruct`, the current pilot model. Arms are never mixed in one comparison |
| Weights | Observed digest pinned per node; affirmative digest drift is refused by existing inventory checks |
| Hardware | Fixed node assignment per arm, recorded; one Ollama run per node (the fleet runner admission) |
| Budget | One normalized request budget for every fixture (the benchmark requires identical budgets) |
| Library and calibration | Disabled for the ladder (current benchmark default); Stage IV is a separate arm with the library enabled and its contents frozen before the run |
| Hidden checks | Evaluator-only, frozen before the first call, never in construction context, never driving repair |

### The compiler ladder

| Rung | Compiler setting | Adds over the previous rung |
|---|---|---|
| R0 | MICA `direct` | Whole program, one model |
| R1 | MICA `static` | One generated decomposition |
| R2 | MICA `decompose_on_failure` | Decomposition after a verified failure |
| R3 | MICA `capability` | Empirical routing (with one model this ranks nodes only; report it as such) |
| R4 | MICA `search` | Alternative graphs within budget |
| R5 | MICA `mica` | Routing and alternatives together |
| R6 | Autogen over the same statements | Several candidates per statement, regeneration with public feedback, statement decomposition |

R6 uses autogen's `local` engine (the CLI agent over Ollama) with `model` set to the frozen model, `strategies: ["fresh", "feedback"]` only (`other_engine` and `stronger_model` change the model; `other_node` changes hardware), fixed `candidates`, `regenerate`, `depth`, `agents_max`, and `wall_seconds` equal to the MICA wall budget. The evaluator's hidden commands must **not** be placed in autogen's `hidden` policy: autogen uses them as an acceptance gate, so candidates would be selected on the evaluator's tests. Run them after the run completes. R6 also adds the CLI agent agent loop around the model, a confound reported with every R6 number. Autogen does not count model calls inside an agent; R6 is compared to R0-R5 on wall time and agent count only, labelled as such.

### Task families of increasing difficulty

| Family | Source | Hidden evaluator | Status |
|---|---|---|---|
| F0 affine integer functions | Contracts in the `affine_integer_v1` domain | Exhaustive over the declared domain | Constructible today; a control: a compiler that uses T should spend zero implementation calls |
| F1 arithmetic and collections | `symblic/mica/fixtures.py` | 51 hidden checks | Exists |
| F2 strict JSON parser | `symblic/mica/fixtures.py` | 77 hidden checks, Python standard-library oracle | Exists |
| F3 markdown renderer | Atomic study sheet (`web/hub/atomic/`) | 500 random documents against the reference | Needs conversion into a MICA fixture: gap |
| F4 regex engine | Atomic study sheet | 400 random cases against `RegExp` | Needs conversion: gap |

Each family needs held-out instances (`--split heldout`) the compiler authors never inspected. Tuning a compiler on the dev split and reporting on it measures the authors, not the compiler.

### Commands

From MICA.md, unchanged. Freeze first and keep the returned `freeze_sha256` outside the experiment store; authorize and place the compute through the existing fleet workflow (one Ollama run per worker node, at most about an hour of continuous load per worker node).

```bash
tools/symblic mica checkpack freeze request.json --declaration declaration.json
tools/symblic mica checkpack linked-fixture pack.json --freeze ORIGINAL_PACK_SHA

tools/symblic mica benchmark --root /private/experiments --id ladder-05b-dev \
  --fixture /private/arithmetic_collections.fixture.json \
  --fixture /private/strict_json.fixture.json --inventory inventory.json \
  --repetitions 2 --seed 7183 --split dev
tools/symblic mica benchmark --root /private/experiments --id ladder-05b-dev \
  --inventory inventory.json --freeze RETAINED_SHA256 --run
tools/symblic mica report --root /private/experiments --id ladder-05b-dev --freeze RETAINED_SHA256
```

The inventory file must be a discovered snapshot containing only the frozen model. R6 goes through `POST /api/symblicos/autogen/start` with a stable `client_request_id` per assignment, `engine: "local"`, the model, the node, a fresh git workspace per assignment, and the policy above; results are read with `GET /api/symblicos/autogen/get?id=RUN_ID&tasks=1`.

### Measurement

The primary outcome is independent hidden whole-program acceptance after `done`, per (model, rung, family, compiler implementation identity), as k of n with the full planned denominator: pending, blocked, stopped, failed, exhausted, unknown and evaluator-unknown assignments stay in n. Secondary: dispatched calls, reservations, wall seconds, unknown outcomes. A claim that "capability came from the organization" requires: the same model digest and nodes, the same budget, the same frozen fixtures, a later compiler identity accepting a held-out family the earlier identity did not, repeated. Repeated fixtures are dependent observations; intervals are descriptive.

### Confounds the operator must report

- Sampling: the native callback does not enforce the experiment seed as deterministic provider sampling.
- Information: equal budgets do not mean equal information; modes differ in prompts, decomposition text and feedback.
- Hardware and cache: node CPU, thermal mode, Ollama load state and warm caches differ between assignments.
- Transient infrastructure: an Ollama timeout becomes `VERIFICATION_UNKNOWN` and blocks the assignment; unknowns are not replayed.
- Harness: R6 adds the CLI agent; atomic-study results use the Symblic kernel path, not MICA.
- Human decomposition: atomic-study sheets were decomposed by people, so they measure Stage I with a human compiler.
- Author tuning: any fix made after reading dev results must be evaluated on held-out instances.
- Selection: autogen hidden gating (if misused), caller-selected calibration runs, and caller-chosen fixtures.
- Partial cost coverage: remote CPU, GPU, memory and energy are unmeasured.

### Placement and stopping

- Every assignment runs on a worker node through the existing admitted fleet path; the host only orchestrates.
- One build per worker node at a time (the fleet runner admits one Ollama run per node across processes); cap provider output so a looping small model cannot hold a node for many minutes.
- Bound continuous load per worker node to about an hour and ask the operator before longer sessions; split the ladder into resumable batches using the benchmark's frozen assignment order.
- A blocked or unknown assignment halts the driver by design. Investigate, then resume the same frozen benchmark; never re-freeze to drop an inconvenient assignment.

### Where the evidence stands

The frozen MICA development pilot (`modules-dev-pinned191238-v1`, `qwen3:4b-instruct` on node-d and node-f, 12 planned assignments) paused after 7: arithmetic ran six times (two reached `done` and both failed hidden grading, four exhausted), strict JSON's first assignment blocked on a transient Ollama timeout, five remain pending. The best result is 50 of 51 hidden arithmetic checks (an object-key `__proto__` case), which is not an acceptance. Earlier objective-only runs produced no artifact. **No hidden-test pass has been recorded for any MICA mode, so there is no capability curve; any curve is future work.**

A separate path gives the only positive weak-model receipts, and its limits matter here. In the atomic study (human-authored sheets, Symblic kernel), `gemma3:1b` completed the 37-unit exact markdown sheet and passed 500 of 500 random documents, twice on different worker nodes (node-i, node-d); `qwen2.5:0.5b` accepted 34 of 37 exact units in both of its runs and failed, accepted 3 of 37 at the fine level and 0 of 13 at the coarse unit level, and accepted 14 of 34 exact regex units (`web/hub/atomic/results.json`). That shows granularity matters for a fixed small model. It does not show that a compiler can find that granularity on its own, which is the thought experiment's actual question.

## 6. Known versus claimed

Known (receipts exist):

- MICA's contract graph, validation, scheduling, repair, frontier, routing, library reuse, checkpacks, affine constructor and six-mode benchmark are implemented and pass isolated tests with fake providers; the CLI, API and panel are installed.
- Hidden evaluator checks are kept out of construction by design and by test.
- Exhaustive finite refinement checks declared predicates; the affine fragment identifies coefficients uniquely within its declared bounds with zero implementation calls.
- Autogen's policy and coordinator exist; its routes were installed on 2026-10-10.
- In the atomic study, human decomposition let a 1B model complete a program that passed 500 of 500 random documents.

Not known (proposals or open questions):

- That MICA has ever produced a hidden-accepted program from a real local model. It has not yet.
- That any compiler rung improves hidden acceptance over another at equal budget.
- That a 0.5B model can complete any F1-F4 program through any compiler rung.
- That decomposition, search or routing is optimal, or that a capability-versus-granularity law exists.
- That Symblic is a new abstraction level, a "cognitive compiler" in the conversation's sense, or a "verified compound intelligence system". These are the conversation's names for a target.
- That composing verified components verifies the parent: today only exact-identity reuse and the original root checks stand between components and the parent, and autogen splits skip the parent's checks.
- That finite examples yield general algorithms: only exhaustive finite domains and declared hypothesis families give anything stronger than tests.

Next action, in order: fix the autogen split re-check; finish and rerun the paused pilot to a complete denominator; run R0-R5 on F0-F2 with `qwen2.5:0.5b`; then R6; then convert F3 and F4. Section 3's families and section 2's promotion rule follow only once one hidden-accepted program exists to promote from.

## 7. Defects found in the core modules while writing this document

| Location | Defect | Proposed fix |
|---|---|---|
| `symblic/autogen/coordinator.py` `_current`, lines 397-399 | A split node becomes accepted when all children are accepted, with no rerun of the parent statement's checks; `_verdict` (line 585) keys public commands by top-level index, so children never run the parent's commands | Before marking the parent accepted, run its `plan_checks` and public commands in the project workspace; fail the parent with a `split_verification` reason on any failure |
| `symblic/autogen/coordinator.py` `_verdict`, line 623 | Hidden commands run only when the last *top-level* statement is verified; if that statement is split, its children have a parent and the hidden commands never run, yet the run can complete | Run hidden commands in the same post-split parent check (or once in `_finish` against the project workspace) |
| `symblic/autogen/policy.py` `classify`, lines 268-277 | A failing hidden check is not mapped to any class and falls through to `UNKNOWN`, so the evaluator-only signal still drives a regeneration indistinguishable from an infrastructure unknown | Add an explicit `HIDDEN_FAILURE` class that regenerates without feedback text and is counted separately in summaries |
| `symblic/autogen/policy.py` `next_strategy`, line 316 | `or name in ('fresh',)` makes `fresh` always eligible; with the default order, after a check, syntax, claim or no-output failure (once `feedback` has been used) or after an `UNKNOWN` failure, `fresh` is chosen ahead of `other_node` and `other_engine`, which are then never reached; the next identical `fresh` fingerprint is refused as a cycle and the node goes straight to decompose or fail (infrastructure, refusal and timeout failures do reach the other strategies) | Apply the same per-strategy quota to `fresh`, or move `fresh` after the other eligible strategies once it has been used |
