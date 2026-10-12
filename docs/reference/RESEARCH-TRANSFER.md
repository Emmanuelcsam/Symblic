# Research transfer: fresh-context construction and the cognitive fabric

Research and implementation map, 4 October 2026; deployment status reconciled 5 October.
Task-card compilation, agent delegation and incremental one-inference proof sessions are included
in the installed Reform 3/2.5 runtime; see the [5 October release evidence](evidence/2026-10-05-reform-install.json). The flat
certificate checker and incremental session remain distinct interfaces. Tests with injected providers check
the machinery, while a real local-model evaluation measures construction ability.

The architectural direction is **proof-carrying cognitive programs**: an author specifies a task, its inputs
and acceptance obligations; a human or model constructs an artifact; reusable checks decide whether it can
enter persistent state. **Symblic Cognitive Fabric** is a proposed name for their composition into typed agent
graphs. It does not claim a new neural architecture or established novelty. The model remains a constructor
of code, proofs, plans, encodings and numerical witnesses. Direct kernel computation and empirical judgments
remain available alongside checked construction.

## Executable research adapters

The [Experiments interface](EXPERIMENTS.md) makes the mathematical transfers callable through the page, operator API and CLI. It includes exact source compression and sidecar transport, fitted ordered-probability models, Hamiltonian/Fisher geometry, native graph adaptation, particle inference, circuit/POVM/tensor calculations, finite combinatorial structures, field refinement, full-metric reconciliation and transport witnesses. Inputs and implementation identities are retained in reproducible receipts, while independent reference tests assess the algorithms.

The worker-with-amnesia construction cycle below also has a complete real-model field result: [20 fresh calls, zero repairs, checked residual and witness](VORTICITY-CONSTRUCTION.md). Earlier failures are retained. Fixed experiment calculations and model-constructed artifacts are separately visible; neither measurement is silently substituted for the other.

## The work-card execution cycle

The operator's worker-with-amnesia analogy becomes an explicit protocol:

1. Identify the next eligible statement and its exact source revision.
2. Reconstruct its work card from committed state: task, definitions, required inputs, dependency code or
   interfaces, assumptions, output format, checks and remaining budget.
3. Start a fresh model call. No implicit conversation history is required.
4. Check the proposed artifact against the caller-owned obligations. A rejected proposal is repair evidence,
   never committed progress.
5. Commit the accepted artifact and its precise evidence, then make dependent statements eligible.
6. Resume after interruption from the same recorded state and identities. Unknown external outcomes require
   resolution before redispatch.

Memory reset removes conversational accumulation; the card supplies the information the next step needs.
Task size is therefore measured by required dependency content and the constructor's observed competence,
not by the number of lines alone. A short instruction can hide a large problem. A long explicit instruction
can be necessary. The compiler should expose that distinction rather than universally banning either form.

## What the implementation now connects

| Mechanism | Exact implementation surface | Current assurance and remaining work |
|---|---|---|
| Declared dependency graph | `symblic.spec.contracts.plan` resolves `Uses`, exports, stable IDs, topological order and layers | Installed pure planner. Missing names, cycles and duplicate exports refuse. It does not discover all JavaScript dependencies. |
| Complete context card | `context_card` carries the full transitive artifact closure; `symblic.spec.build.compile_cards` emits the full declared contract/code closure as a required native value | Installed compiler runs under the verified profile. Required context overflow refuses rather than silently dropping code. Budgets are characters, not model tokens. |
| Branch-local reuse | `reuse_decisions`, `record_artifact`, `compile_cards` | Contract, dependency artifact and runtime changes invalidate affected reuse. Unrelated accepted branches survive. Kept code still runs through current local examples. |
| Whole-build checking | Unit checks, joined-unit checks and final `.js` template checks in `compile_cards` and `checkpoint` | Exposed examples check executed behavior. An HTML template still needs a browser-level independent test; finite examples do not establish arbitrary semantic equivalence. |
| Portable build memory | `checkpoint`, `artifact_manifest`, `verify_manifest` | Exact code/output bytes, source/runtime pins and scoped records. The helper validates association and integrity; the native compiler rechecks imported code locally. A self-issued hash is not authority. |
| Agent-callable operations | `symblic.delegate.contracts.compile_task`; `symblic.delegate.run.prepare` / `run_task` | Installed `typed_transform`, `proof` and `exact_arithmetic` templates compile to existing native execution. Caller-held checks, execution pins, canonical accepted output and call limits remain. Arithmetic needs no provider call. |
| Formal human/model construction | `symblic.adapters.logic`, `symblic.adapters.finite_logic`, `symblic.adapters.proof`, `symblic.adapters.proof_steps`, `symblic.adapters.proof_adapter` | Existing controlled formulas, finite-domain lowering and nested/flat intuitionistic proof checking. The author/model supplies the derivation; the checker supplies no missing inference. |
| Conditional knowledge and graphs | `symblic.kernel.epistemic`, `symblic.graph.planner`, `symblic.graph.run`, `symblic_policy_*` | RC2 carries conditional origins/receipts, contested votes and dependency checks, plus graph execution, recovery and frozen candidate comparison. Supplied revisions/withdrawals/disagreements are additionally supported by the pure evaluator; learned topology and calibrated confidence remain separate evidence questions. |
| Persistent evidence memory | `symblic.memory.notebooks`, `integration.host.symblic_memory_api`, `symblic-memory.js` | Installed notebook for imported run snapshots, operator revisions/withdrawals/disagreements, retained history and selected-context export. 28 helper and four API tests plus desktop-light/phone-dark browser journeys passed with isolated stores/HTTP. Content revisions clear prior checks and do not mutate completed runs; hash-only values and unassessed acquisition independence remain explicit. Installation is recorded in the 5 October release; these remain component-test results. |

Focused component tests include `test_symblic_spec_contracts.py`, `test_symblic_spec_build.py`,
`test_symblic_task_card_api.py`, `test_symblic_delegate.py`, `test_symblic_delegate_run.py` and
`test_symblic_cli_agent.py`. The release evidence records revision-specific pass counts and scoped live verification.
Current tests target stale dependencies, forged/imported records, missing context, overflow before dispatch,
independent branch reuse, template interference and exact output reconstruction. They do not measure model
accuracy. [SPEC-SHEETS](SPEC-SHEETS.md), [PROOF-STEPS](PROOF-STEPS.md) and [REFORM-3](REFORM-3.md) describe the
existing neighboring contracts.

There are three separate determinism targets. Pure evaluation fixes a result under pinned semantics.
Replay reproduces recorded accepted replies without new generation. Fresh construction can produce different
valid artifacts. To require identical observable output, declare exact bytes, canonical values or an explicit
equivalence relation, and justify why the acceptance contract selects one such result. Requiring a known
output hash checks identity; it does not make a model find that output.

## Research that informs the mechanism

These are engineering transfers from the cited studies, not claims that their measured gains already apply
to Symblic. The evaluation below tests the transfer.

| Primary source | Result or method relevant here | Symblic consequence |
|---|---|---|
| [Least-to-Most Prompting](https://arxiv.org/abs/2205.10625), Zhou et al., ICLR 2023 | Solve subproblems in sequence and supply prior answers to later problems | Preserve necessary answers explicitly when clearing chat history. |
| [Decomposed Prompting](https://arxiv.org/abs/2210.02406), Khot et al., ICLR 2023 | Modular handlers may use prompts, symbolic functions or retrieval | Compare typed constructors and generic checkers with this close baseline. |
| [Lost in the Middle](https://aclanthology.org/2024.tacl-1.9/), Liu et al., TACL 2024 | Relevant information's position affects retrieval and question answering | Test dependency position and distractors, not only total context length. |
| [LLMs Get Lost in Multi-Turn Conversation](https://arxiv.org/abs/2505.06120), Laban et al., 2025 | Progressive instruction delivery can degrade generation across the studied tasks | Rebuild consolidated authoritative state; measure against an equal-information history condition. |
| [Atom of Thoughts](https://arxiv.org/abs/2502.12018), Teng et al., NeurIPS 2025 | Self-contained atomic reasoning states | Compare state reconstruction and error propagation, including its additional cost. |
| [The Markovian Thinker](https://arxiv.org/abs/2510.06557), Aghajohari et al., 2025 | Trained carryover enables fixed-size reasoning chunks in a 1.5B model | Small local models are a relevant target; learned carryover is a distinct training experiment. |
| [The Y-Combinator for LLMs](https://arxiv.org/abs/2603.20105), Roy et al., 2026 | Typed combinators and bounded neural leaves | Add explicit composition, cost and termination contracts; compare with lambda-RLM. |
| [MAKER](https://arxiv.org/abs/2511.09030), Meyerson et al., 2025 | Extreme decomposition and error correction on a particular long task | Evaluate long-run accepted-step error and shared failures on held-out task families. |
| [Proof-Carrying Code](https://homes.cs.washington.edu/~mernst/teaching/6.893/readings/necula-popl97.pdf), Necula, 1997 | An untrusted producer supplies evidence a consumer checks | Keep difficult construction/search outside the reusable checker. |
| [GPTSwarm](https://arxiv.org/abs/2402.16823) and [TextGrad](https://arxiv.org/abs/2406.07496), 2024 | Agent graphs and textual feedback over compound systems | Optimize candidate nodes/edges under fixed author contracts, then freeze before held-out comparison. |

Human memory research supplies another source of concrete design ideas. A 143-person randomized crossover
study of external paging prompts supports reminders for the prospective-memory tasks it studied. Symblic's
translation is a durable scheduler that presents the next exact work card; it is not evidence that LLM context
reset is equivalent to human amnesia. [Wilson et al., 2001](https://pubmed.ncbi.nlm.nih.gov/11254770/)

Errorless-learning experiments motivate keeping accepted state distinct from bounded, explicitly rejected
repair attempts. Reminder research that separates confidence from performance motivates choosing task size
and routing from measured outcomes rather than self-confidence. These transfers are hypotheses to evaluate.
[Baddeley and Wilson, 1994](https://pubmed.ncbi.nlm.nih.gov/8818154/),
[Gilbert, 2015](https://pubmed.ncbi.nlm.nih.gov/25666463/)

## A numerical construction task from the vorticity energy method

A supplied two-page derivation (not in this repository) gives
`div(y grad(phi)) = Omega` with positive `y`, declared boundary conditions and an energy functional whose
stationary point solves the weak equation. The useful transfer is an explicit discrete energy problem with
model-constructed operator and witness. The checker need not acquire a new PDE solver. The standard weak-form
and Dirichlet-boundary formulation is also documented in the primary
[DOLFINx Poisson example](https://docs.fenicsproject.org/dolfinx/main/python/demos/demo_poisson.html).

For an oriented graph incidence matrix `D`, positive diagonal weights `W`, source load `f`, and declared
boundary substitution `u = T x + g`, the finite contract is:

```text
L = transpose(D) W D
A = transpose(T) L T
b = -transpose(T) (L g + f)
H(x) = (1/2) transpose(x) A x - transpose(b) x + constant
```

Use a synthetic dimensionless five-vertex chain, unit weights, zero endpoints and interior load `[0,-2,0]`.
The model supplies six independent scalar coefficients, each from selected
incidence columns and edge weights. Code assembles the symmetric operator, whose
expected fixture is:

```text
A = [[2,-1,0],[-1,2,-1],[0,-1,2]],  b = [0,2,0]
```

It then supplies the nontrivial exact LDL entries and solution. The expected witness has diagonal
`[2,3/2,4/3]`, lower entries `[-1/2,-2/3]`, interior solution `[1,2,1]` and reduced minimum energy `-2`.
An independent test keeps those expected values hidden from the construction request. The author-held
incidence/weights/load determine the checks; the model cannot replace them with easier inputs.

The initial private prototype made nine fresh fake-provider construction calls and used the existing
`quadratic_verify` checker, with solve/factorization entrypoints disabled. A real Qwen 4B trial of its
three-row construction stopped at the first exact row check after two rejected candidates. That negative
record is retained. The scalar version used twelve tasks at medium effort: six coefficients,
five factor entries, and one solution vector. An independent matrix check against the original incidence
and weights follows assembly. The admitted scalar Qwen 4B run `8219c94f2275` passed the six coefficients,
full matrix check, and first three factor entries, then stopped at `lower32`: both candidates had the wrong
positive sign. It used eleven calls and produced no final solution or witness.

Explicit signed-numerator wording passed the one-ask synthetic diagnostic `f00de8fbac95`, with a portable
lock and zero-model replay. Full run `0731a75ff11c` then passed all eleven coefficient/factor tasks but
rejected both final vectors, `[1,1,1]` and `[1,0,1]`, under the original residual condition. Its thirteen
calls were fresh, and no final potential, energy or witness was produced. All three whole-program failures
remain retained; the diagnostic success has its narrower scope.

The revised example now uses twenty tasks at medium effort: the unchanged eleven coefficient/factor
tasks followed by nine scalar substitution tasks. Forward tasks satisfy `y1=b1`, `y2+l21*y1=b2`, and
`y3+l32*y2=b3`; diagonal tasks satisfy `di*zi=yi`; backward tasks satisfy `x3=z3`,
`x2+l32*x3=z2`, and `x1+l21*x2=z1`. Each worker receives only the named scalars its identity needs.
The host extracts scalar inputs, converts signed rational records and assembles accepted answers;
it does not supply substitution answers. Each identity is checked before a dependent task, then the
original full residual and quadratic witness are checked. Backward `Int` types deliberately cover this
integer-solution fixture. The thirty-call host budget bounds correction attempts.

Isolated tests derive all answers from selected request data, reject wrong forward/diagonal/backward
proposals, detect incorrect assembly, and reject old backward values after changing to an integer-solution
load. They forbid built-in solving and factorization. The separate nine-ask diagnostic
`09d7ff1df692` completed substitution from synthetic `A,b,L,D` in ten fresh calls, retaining one rejected
proposal. The complete twenty-task construction then succeeded in admitted Qwen 3 4B run `ae4e46820f83`:
twenty fresh calls, no repairs or reused prefix, potential `[0,1,2,1,0]`, residual `[0,0,0]`, and exact energy
`-2`. Its factorization, positive-pivot, stationarity, symmetry and unique-minimum checks passed. The
portable lock replay used zero model calls and matched fingerprint `4f8ee53abdc44057`; all three earlier
whole-program failures remain retained. This is one positive finite-fixture result, not a general accuracy
estimate. See the [construction result](VORTICITY-CONSTRUCTION.md) and
[pinned receipt](evidence/2026-10-05-vorticity-construction.json). Later evaluations should vary topology,
weights, boundary values and source signs while retaining the construction/checking protocol.

For uniqueness, every connected component needs a fixed value or an explicitly valid gauge treatment. Pure
Neumann components need compatible loads; silently adding regularization changes the problem. Physical PDE
claims additionally need units, discretization error and mesh-refinement evidence. An exact certificate of
the finite system is not a bound on continuum error. [VARIATIONAL](VARIATIONAL.md) records the existing exact
quadratic verifier's scope.

## Evidence acquisition and broader mathematics

The multi-frame design rationale ([EVIDENCE.md](EVIDENCE.md)) motivates attention to distinct acquisition methods and
their assumptions. The concrete extension is a **claim × method × failure-mode
matrix** built on existing evidence identities: record what each acquisition method checked, which seeded
faults it caught, shared assumptions, unresolved conflicts and revision invalidation. Choose the next method
by additional measured failure coverage per cost, while preserving unknown coverage. Model family names
alone do not establish independence, and a formal consequence does not establish its empirical premises.

The installed [Inquiry planner](INQUIRY.md), available in the Inquiry tab, operator API and CLI, makes this
matrix executable by comparing measured finite fixture coverage and declared costs while preserving shared
dependencies and unknowns.

Preserve the broader research agenda by giving each proposal a computable target:

| Research direction | Executable next experiment | Acceptance target |
|---|---|---|
| Quantum question-order models | Fit supplied projector and classical contextual models to the same blinded ordered-answer data | Held-out predictive fit, parameter cost and order effects reported separately; no Boolean truth inferred from a fit |
| Ising/QUBO and heuristic search | A model constructs an encoding; an optional bounded search proposes witnesses beyond the exhaustive baseline | Recheck original constraints and objective; report a bound/gap only when a valid certificate supports it |
| Symplectic and information geometry | Supply an explicit Hamiltonian or finite probability model, then compare integrators or update directions | Preserved quantities/error/cost against a declared baseline; no metaphorical conservation law over prompts |
| Schema equivalence | A model constructs forward/backward maps with unit and field contracts | Round trips over the declared finite domain plus the exact predicates transported |
| Source compression | Extractive or proposed summaries retain exact source links, entities, quantities, negation, scope and exceptions | Required-information retention and final task accuracy against full source and simple retrieval |
| Typed agent composition | Reusable subgraphs and explicit map/reduce/fold or feedback interfaces | Shape/evidence/cost contracts, bounded cycles, deterministic reduction and interrupted-run recovery |

[RESEARCH-ADOPTION](RESEARCH-ADOPTION.md) retains primary references and the wider proposal register. Rejecting
an unsupported guarantee does not justify removing an optional mechanism that can be isolated, checked and
measured. A floating-point or heuristic constructor can be useful without weakening an exact checker.

## Token and evaluation discipline

Encoding costs depend on tokenizer and surrounding text. In pinned `tiktoken 0.9.0` fixtures, isolated `≤`
costs two tokens in `cl100k_base` and one in `o200k_base`; `<=` costs one in both. Complete condition strings
can nevertheless tie. Numeric tokens are grouped by tokenizer rules, not by whether a number is common or
mathematically simple. Retain human-friendly symbols and measure optional transport aliases per actual local
model tokenizer. [Official tiktoken encoding definitions](https://github.com/openai/tiktoken/blob/main/tiktoken_ext/openai_public.py)

Opaque repeated hashes are a better compression candidate than deleting required context: move them to a
host-pinned sidecar and expose short references while keeping origin, scope, assumptions and needed source
values visible. This is a measured private fixture proposal, not yet a runtime feature. Adoption requires
forged-reference, cross-card, source-drift and restart checks plus local-model quality measurements. A hash
cannot replace information the constructor must actually read.

The next evaluation freezes at least two small local model families and compares equal-information,
equal-budget conditions: whole-task prompting, granular tasks with growing history, fresh dependency cards,
and fresh cards plus checking/repair. Optional graph diversity is a separate factor. Freeze task families,
models, checkers and hidden tests before generation; preserve every planned cell and distinguish malformed,
wrong, refused, timed-out, interrupted and accepted outcomes. Record calls, prompt/output tokens, model-seconds,
wall time, repair exposure, copied reference code and human specification/debugging effort.

Release acceptance should show restart-equivalent cards, precise dependency invalidation, rejection of forged
authority, no accepted failed witness, independent whole-artifact behavior and a complete local-only outcome
denominator. A larger fallback model remains an available feature, but its success belongs to an assisted
condition. Those results determine which decomposition and routing advances deserve adoption.
