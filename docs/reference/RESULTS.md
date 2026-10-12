# Symblic — measured results and their scope

This ledger records measured results and the stored evidence for each, newest first. It covers results through
version 2.4 (corrected on 2026-10-04). Version 2.5, live since 2026-10-04 (`VERSION` in `symblic/kernel/language.py`; the reform is
described in [REFORM-3.md](REFORM-3.md)), has no section here yet; later results belong in new sections. A result
covers only the source snapshot, models, inputs and sample it names; later code changes are not covered by it.
Kernel determinism means the kernel's own computation and the replay of recorded runs, not what a model answers.
Where no stored artifact was found for a reported figure, the text says
**reported, artifact not found**. Paths under `automation_data/`, `host_executor_data/` and `~/.local/state/` are
private operator stores, cited so that a figure can be re-checked.

## Version 2.4: spec-sheet builds by local models (2026-10-04)

The Tetris file built from a spec sheet by local models (qwen3:4b-instruct, phi4-mini and gemma3:4b), its
from-scratch validation through the Build API, and what a passing build does and does not establish are recorded in
[SPEC-SHEETS.md, "The Tetris record"](SPEC-SHEETS.md#the-tetris-record-2026-10-04) and the section after it. They
are not restated here.

Version 2.3 (2026-10-03) built 12 reviewed proposals in reduced form. [REVIEW-2.3.md](REVIEW-2.3.md) records each
proposal's outcome and reason. It is a review, not a measurement, and this file records no 2.3 result.

## Version 2.2 / canonical 3: finite witnesses and intent interpretation

This increment adds an exact, bounded quadratic solver/verifier and an operator-facing intent interpreter.
`quadratic_minimize(A, b)` minimises H(x) = ½xᵀAx − bᵀx for an explicitly supplied rational, symmetric,
positive-definite matrix A of size at most 32. It factors A exactly as LDLᵀ, refuses any non-positive pivot, and
returns the factors, the solution, a zero residual and the minimum energy as a receipt. `quadratic_verify` re-checks
a receipt without re-solving (`MAX_DIMENSION`, `_ldlt`, `_verify`, `minimize_quadratic` and `verify_quadratic` in
`symblic/adapters/variational.py`). Since version 2.2 both are kernel builtins (lazy wrappers in `BUILTINS` in `symblic/kernel/language.py`),
so any program can call them, including runs through `symblic.kernel.run` and the live API (the review driver and the
2026-10-03 run below). `solve=true` does not use them, and they assemble no PDE. Only the final discrete step of the
two-page vorticity note discussed in [VARIATIONAL.md](VARIATIONAL.md#what-the-energy-analogy-does-not-prove)
motivated this solver: minimising the quadratic is the same as solving Ax = b. The mathematical result used is the
standard one for a positive-definite quadratic (Boyd and Vandenberghe, *Convex Optimization*, Cambridge University
Press, 2004, §4.2.3, Example 4.5: for P ≻ 0 the unique minimiser is x* = −P⁻¹q; here q = −b). It is not a new
uniqueness theorem for natural language. See [the adapter's domain and limits](VARIATIONAL.md) and
[the interpretation/recovery contract](INTERPRETER.md).

Independent checks of the finite solver ran against the accepted module (sha256 `500c08d0…`), whose code was still
live on 2026-10-04 (the 2.5 release changed only its docstring, so the file's sha256 is now `32202185…`):
- A review driver (`~/.local/state/executor-integration-20261003/variational-fleet-review.py`, receipt
  `variational-fleet-review.json` beside it) compared the solver with a separate Gauss–Jordan elimination on 72
  seeded positive-definite problems of dimensions 1–6, and checked 360 energy-difference identities. It rejected 31
  modified receipts and 14 invalid or over-limit inputs, and solved and verified a diagonal 32-dimensional problem
  exactly. It also ran a program that calls both builtins through the runner without a model, locked and replayed
  it, and checked that the replay is refused once the adapter's version changes.
- A separate reviewer's probe solved 30 constructed positive-definite problems (dimensions 1–6, seed 47) and refused
  90 tampered receipts (`variational-independent-probe-final.json` in the same folder). Only summary receipts are
  stored: this one, and `variational-independent-probe.json` for an earlier draft of the module (`05151e3a…`). The
  probe's script was not found.
- The accepted scale profile (`~/.local/state/symblic-variational-20261003/scale-profile-v1-accepted.json`) solved
  dense constructed problems of dimension 4, 8, 16 and 32 and matched their known solutions. Dimension 32 took
  0.35 s to solve (including the solver's own check) and 0.17 s to verify on a 6-core desktop CPU. That is one
  observation under the load of the moment, not a performance guarantee.

The verifier shares the solver's exact arithmetic and energy code, so it is only partly independent of it. These are
bounded software checks, not an exhaustive proof of implementation correctness or a PDE validation campaign.

Executed counterexamples from the review of the AGY study documents used fake replies and no model calls
(`~/.local/state/executor-integration-20261003/agy-review/syntax-and-semantic-probes.json`, summarised in
`critical-assessment.txt` beside it). They showed three things:
- a short, unrelated summary ("A short but factually unrelated response.") satisfies a word-count check;
- a fabricated order extraction (quantity 1, unit price 1, total 1 for "I ordered 3 laptops at $800 each")
  satisfies a quantity × unit price = total check;
- a proposed invoice constraint that adds a $25 setup fee already listed among the items rejects the faithful
  extraction: it computes $250 against the stated $225.

A falling error count or lower reader disagreement therefore does not establish that intent was preserved. The
interpreter retains operator turns and requirements, keeps proposed assumptions in a separate list that only the operator
can adopt or reject, and records whether each statement came from the operator or from a model: a model can neither
create an operator statement nor retire a requirement. It also labels the scope of each check (the statement-origin and
operator-turn checks, `readback` and `assess_continuation` in `symblic/intent/records.py`).
Model-proposed examples are not reported as executed evidence.

Recovery tests use isolated stores and fake providers, including the real native host-executor handoff with a fake unit
launcher (`tests/integration/test_symblic_intent_api.py`). They cover concurrent submission, lost replies, retained call
reservations, local-only policy, source/input/version drift and changed capability contracts. Examples are
`test_concurrent_duplicate_handoff_only_one_dispatch`,
`test_lost_native_reply_recovers_existing_clock_pinned_run_without_dispatch`,
`test_confidential_call_gate_drops_cloud_before_reservation` and
`test_changed_catalogue_blocks_handoff_before_native_launch`. They do not measure general model accuracy.

Live the host executor plans on 2026-10-03 showed the 1B/2B local models taking minutes to return programs that failed the
checker: about 2–3 minutes per planning attempt for llama3.2:1b and 7–8 minutes for granite3.3:2b, whose two answers
stayed at the stage "does not parse, or none of its statements is right" (`host_executor_data/plans/3b470de39bd2/` and
`76ae0f43fda2/`, `log.txt` and `plan.json`). Under the earlier check, a llama3.2:1b plan consisting only of the bare
expression `cluster.nodes().count()` was marked ready, and so was a second such program (recorded in the
`prose_lines` docstring in `host_executor_plan.py`). A passing simple typed task is not a planner qualification. The
planner now holds a machine-written program to the language's statement forms, so implicit prose questions and bare
expressions are rejected (`prose_lines`). It also records each planner's outcomes: a failed plan counts two points
if its best answer was no program, did not parse or had no right statement, and one point for a near miss. At four
points since its last pass, a planner is skipped until seven days after its last failure, unless it is the only one
left (`SKIP_POINTS`, `SKIP_FOR_S`, `usable_planners` and `record_plans`). No general small-model reasoning gain is
claimed from these changes. Held-out intent fidelity, false acceptance, refusal, latency and total-call-cost
comparisons remain necessary for publication claims.

On 2026-10-03 the live 2.2 API solved the documented two-variable quadratic (A = [[4, 1], [1, 3]], b = [1, 2]) and
returned `x = [1/11, 7/11]` and minimum energy `-15/22`. It then locked and replayed the run with the same
fingerprint, `7a3023f1b53be32b`, and zero model calls (run `79c19a8c40a7`; receipt
`~/.local/state/executor-integration-20261003/live-quadratic.json`). The isolated Symblic regression suite
passed 628 tests after the interpreter deployment fixes (`symblic-2.2-final-regression.log` in the same folder).

A separate local-only flower-diagram interpretation (intent `cffd9c2f7111`) took about 238 seconds and two model
calls. gemma3:4b failed in transport (an empty reply from Ollama), and qwen3:4b-instruct returned a typed answer. It
returned a goal but no requested clarification question. This is an observed task failure despite structural
acceptance, not an accuracy improvement. The explicit **Ask for specifics** mode now rejects proposals without a
pending blocking question within the same call budget. Fake-provider counterexamples verify that gate
(`intent-clarification-contract-closure.json` in the same folder;
`test_requested_specifics_cannot_silently_accept_a_goal_only_reply` and
`test_specifics_requires_unanswered_blocking_question_in_merged_state`). They do not establish that the model asks
the right question.

The next live attempt exposed a schema mismatch: `List of Any` generated string items for constrained decoding,
while the interpretation contract required objects. Both local candidates returned string questions and were
rejected (same intent, about 285 seconds). The interpreter now supplies explicit nested record schemas and retains
previous items by code, asking the model only for additions. Failed requested refinement also blocks a new
translation/handoff until a successful analysis or operator revision resolves it; it cannot silently reuse an older
checked interpretation (`test_actual_provider_schema_contains_nested_objects_not_any_string_fallback`,
`test_failed_requested_refinement_blocks_old_translation_until_successful_readback`). The subsequent local-only trial
on that schema (intent `60570818573f`) encountered a transport failure on `gemma3:4b`; `qwen3:4b-instruct` had not
finished when the five-minute verification window ended. Cancellation left no admitted run active and retained both
charged calls. This trial is unfinished, not a successful clarification or a measured model-quality gain. No
confidence or success rate is inferred from these three development trials.

## Version 2.1 / canonical 3: 2026-10-03

The following receipts concern fixed source snapshots. Ongoing changes after those snapshots are not
silently covered by the same measurements. Local fake-based regressions check implementation behavior;
they do not measure live-model accuracy. Semantics and assurance limits: [SPEC.md](SPEC.md) and
[EVIDENCE.md](EVIDENCE.md).

### Fixed-corpus conformance

[Portable conformance receipt](evidence/2026-10-03-conformance-v3.json): three hosts (x86-64 Python
3.12.3 and 3.11.2; aarch64 Python 3.13.5), each with three hash seeds and three ambient Decimal profiles.
All **27 profiles** produced the same observable corpus SHA-256,
`b7496ea6bc19a211aa3a4d610b21f1849a94b660ee5f9c21fae7406e105216b9`.
The 30 soundness regressions also passed on each host. The corpus covers typed sets/facts, exact string
identity, rational/approximate arithmetic, a logic program and SVG outputs. It used no model calls.

The receipt includes the driver and identity-program source, file-hash manifest, per-profile outputs,
limits and admitted job identifiers. The kernel identity includes the Python and Unicode versions, which differ
across the three runtimes (Unicode 15.0.0, 14.0.0 and 15.1.0), so the three kernel IDs differ. The result is
equality of the tested observable bytes, **not** a claim that different kernel IDs are interchangeable. It is not a
proof of universal semantic equivalence or a test of every extension, effect, provider or possible input. Later
runner changes, including null-answer handling and failed-ask determination reporting, are outside this historical
snapshot.

To capture a new local snapshot without model calls, run
`python3 tools/scripts/symblic_conformance.py --output /tmp/symblic-conformance.json` (choose a new output
path for each run). The runner freezes a whitelisted source copy before its nine seed/context profiles
and soundness checks; the receipt identifies exactly those source bytes. A local rerun is not another
cross-node measurement.

### Six-case communication diagnostic: llama3.2:1b

[Preregistered plan, calls and scored receipt](evidence/2026-10-03-contract-pilot-llama1b.json),
2026-10-03 12:48–12:52 UTC. Six synthetic task instances were assigned to each of three arms, with the
same two-call ceiling per cell (36 maximum). All 18 cells reached a terminal state; 30 calls were used.
The templates were exposed and instances frozen before calls. They are not a novel-domain holdout.

| arm | first-attempt correct / assigned | final correct / assigned | wrong accepted / assigned | run status `failed` | calls |
|---|---|---|---|---|---|
| natural prompt | 0/6 | 0/6 | 1/6 | 5/6 | 12 |
| typed answer | 0/6 | 0/6 | 6/6 | 0/6 | 6 |
| checked escalation | 0/6 | 6/6 | 0/6 | 0/6 | 12 |

Every checked success required the conditional Haiku fallback: **the 1B model was not made correct on
these tasks**. The checked arm combines an executable reference predicate and a stronger fallback, so
this is evidence that this package rejected the observed wrong candidates and recovered these six
cases. It does not isolate verifier benefit from model benefit or demonstrate small-model reasoning gain.
The typed arm illustrates that schema validity can coexist with wrong accepted answers.

The receipt retains each requested/observed model, actual node, call identifier, timing, outcomes and
source hashes. Hosted/local model aliases are not pinned weight revisions. Equal call ceilings do not
mean equal calls consumed, equal prompts or equal cost. The initial diagnostic pinned source hashes;
a complete source-byte archive was added for the subsequent follow-up, not retroactively asserted for
this run. Six paired cases support no statistical superiority, independence or general accuracy claim.

### Same-case follow-up: qwen3:4b

[Plan, calls and scored receipt](evidence/2026-10-03-contract-pilot-qwen4b.json), 2026-10-03
12:56:54–13:07:19 UTC. This follow-up used the same six instances, seed and prompts as the 1B
diagnostic. It is a comparative follow-up, not a new holdout. All 18 cells finished with status `done`,
with 20 calls total (18 qwen3:4b-instruct and 2 Haiku); no call outcome remained unknown.

| arm | first-attempt correct / assigned | final correct / assigned | wrong accepted / assigned | calls |
|---|---|---|---|---|
| natural prompt | 4/6 | 4/6 | 2/6 | 6 |
| typed answer | 4/6 | 4/6 | 2/6 | 6 |
| checked escalation | 4/6 | 6/6 | 0/6 | 8 |

The two checked-arm failures were rejected and recovered by Haiku. Schema alone showed no gain on
these instances. The narrower supported finding is that the tested reference-contract-plus-fallback
path recovered these two errors without accepting them. This does not show that Qwen's own reasoning
improved or establish general superiority, independence, calibration or small/frontier model parity.
The same intervention and sample-size limits as the 1B diagnostic apply. Exact imported source bytes
were archived before calls and their nine file hashes verified against the plan; the public receipt
records those hashes, actual placements and call outcomes.

## Historical experiments: 2026-10-02, version 2.0

The tables, counts and fingerprints in sections 1–8 below are historical results under the earlier
implementation. They are retained without treating them as a rerun of version 2.1/canonical 3. Clock times in
sections 1–8 are the original host's local time.

**Historical status: the benchmark was paused by the operator at about 20:50 because the worker nodes were running hot.**
512 result lines (511 distinct cells) are saved in `automation_data/symblic/bench/nodes-20261002/results.jsonl`
(private), and the run resumes from there. The total of 644 planned cells given at the time
([NOTES-2026-10-02.md](NOTES-2026-10-02.md)) is **reported, artifact not found**: the run log's last plan line
(18:10) lists 606 cells. The identity, flower and logic suites are complete (224, 42 and 90 cells). The arithmetic
suite is complete only for Claude Sonnet and Codex (24 of 24 items); Claude Haiku answered 20, the qwen3:4b councils
18–20, and each single-small-model baseline 3–4, so no claim below compares a council with one small model.
Method and code: `symblic/bench/bench.py`. The ground truth for every item is fixed in code before the run (constants for
the identity questions, computed for the generated items). The figures below follow the stored report (`report.md`
beside the results, written by `symblic/bench/bench.py`). It leaves out 8 council cells from an older arithmetic item
numbering, and its medians are upper medians.

Scoring differed by form. Typed and Symblic answers were compared exactly with the ground truth; prose and direct
answers were scored by text heuristics in `symblic/bench/bench.py`. `_prose_correct` looks for a yes/no or true/false
prefix, or the expected answer as a whole word (for a list, the expected items in the expected order; for a record,
each expected value anywhere); `_num_from_text` takes the last number after `ANSWER:`, else the last number in the
reply; `_names_from_text` takes the capitalised words of the last `ANSWER:` line, else of the reply's last line.
For direct answers the results keep only the extracted value, not the reply. A right answer in an unexpected form
can be scored wrong (§2 has three such prose answers), and some extracted values are not answers at all: two of
qwen3:4b's direct logic answers were read as `but` and `therefore`. The prose-versus-typed and direct-versus-Symblic
comparisons in §2, §3 and §5 therefore include scoring differences, and the arms were also not matched for budget or
feedback. `report()` in the current `symblic/bench/bench.py` prints the same limit; the stored report predates it. Prior
work: [PRIOR-ART.md](PRIOR-ART.md).

## 1. Historical kernel conformance cases

The kernel (exact rationals, Decimal trigonometry with no platform maths library, Datalog, drawings rounded
half-even to 0.01) was run on 8 machines: the host (Ubuntu 24.04, Python 3.12.3), six worker nodes (Debian 12 with Python
3.11.2, Debian 13 with Python 3.13.5) and the ARM node (aarch64, Python 3.13.5). Both programs gave one run fingerprint
everywhere (`02-flower-formal.sym` → `c2351a32c05cc58d`, `10-kernel-identity.sym` → `fff6d4efbecb4a3a`), and each of
the four drawings had the same hash everywhere. Both kinds of value are 16-hex-digit SHA-256 prefixes
([`kernel-identity.json`](kernel-identity.json)). These are observed identities for the tested programs, runtimes and
implementation snapshot. Formal computation removes model sampling from those steps; it does not prove every program
or platform.

A first live check on a small program with one closed and one integer ask is reported to have given the run
fingerprint `ed944e6a299b9b61` from llama3.2:1b (node-a), qwen3:4b (node-b), Claude Haiku and Codex alike. This is
**reported, artifact not found**: only a handoff note (`~/.local/state/dashboard-reinforcements/c6d9-owner-handoff.md`)
and a session transcript record the fingerprint, and the run records were not found.

## 2. Do different agents give the same answer? (16 questions, 7 applicators)

Each question was asked twice of every applicator: as a plain prompt (answer text compared after
lower-casing and removing punctuation) and as a Symblic typed ask (canonical fingerprint compared).
Applicators: Claude Haiku, Claude Sonnet, Codex, Antigravity (agy), qwen3:4b and llama3.2:1b on the
worker nodes, and Claude Opus in this session answering the same capsules by hand.

| | plain prompt | Symblic typed ask |
|---|---|---|
| questions where every applicator agreed | 4 / 16 | 6 / 16 |
| pairwise identical answers | 62% (207/336) | 78% (259/330) |
| … 95% CI resampling whole questions | 47–76% | 69–87% |
| Krippendorff's α (nominal), same resampling | 0.60 (0.44–0.74) | 0.77 (0.65–0.85) |
| … without llama3.2:1b (subset chosen after seeing the data) | 71% (170/240), unanimous 8 / 16 | 94% (221/235), unanimous 13 / 16 |
| correct (prose by text heuristic, typed exactly) | 88% (99/112) | 88% (98/112; 98/111 answered) |
| valid (parsed against the type) | 112 / 112 | 111 / 112 (one request got no answer: the provider refused the generated schema) |

The missing typed answer is Codex on one question. Codex's output-schema check refused the generated JSON schema
(`uniqueItems` is not permitted), so no answer came back; it was not an invalid answer.

The prose score marked three right answers wrong. Sonnet, Codex and agy listed the vowels of "education" in the order
they occur (`e u a i o`); the question asks for a set, but the scorer expects the order of its key (`a e i o u`).
Counting those three, prose was 102/112 correct.

**Paired, the same 16 questions resampled together (2 000 seeded draws):** typed − prose = **+17 points of
pairwise identity (95% CI +4 to +30)** and **+0.17 α (+0.04 to +0.31)**. Correction (phase 2): the first
version of this table gave Wilson intervals over the 336 answer pairs; those pairs come from 16 questions, so
they are not independent and the intervals were too narrow. The bootstrap above resamples questions. The
"without llama3.2:1b" row was chosen after seeing the data and is descriptive only.

In this 16-question sample, the typed form had higher cross-agent identity than the prose form, without higher
correctness: 98/112 typed against 99/112 prose as scored, or 102/112 counting the three prose answers above.
llama3.2:1b is the largest single source of disagreement in both forms: it is in 59 of the 129 disagreeing prose
pairs and 57 of the 71 disagreeing typed pairs. It is often wrong (6/16 correct as a typed ask), and a wrong answer
in a canonical form is still a different fingerprint. Agreement is not correctness.

## 3. Multi-hop logic: translate, then let the kernel reason (15 generated family trees)

The model only extracts `parent(...)` facts from the shuffled story (a typed list); Datalog rules answer
descendants / ancestors / cousins. "Direct" asks the model to reason the answer itself.

| applicator | direct | Symblic + Datalog | median seconds (direct → Symblic) |
|---|---|---|---|
| Claude Haiku | 15/15 | 15/15 | 13 → 9 |
| qwen3:4b (worker node CPU) | 9/15 (60%) | **12/15 (80%)** | 296 → 96 |
| llama3.2:1b | 0/15 | 3/15 (20%) | 26 → 60 |

In the Symblic arm the multi-hop inference is done by the kernel's Datalog rules, and the model only lists parent
facts. qwen3:4b went from 9/15 to 12/15, and its median time fell from 296 s to 96 s (about 3×). Two of its six
direct failures were read as `but` and `therefore`, not as names, so the direct score may understate it (see the
scoring note above). A shorter answer (a list of facts instead of a chain of reasoning) may explain the time
difference. Answer lengths were not recorded, and in the same arm llama3.2:1b was slower: it went from 0/15 to 3/15,
and from 26 s to 60 s. With correct rules, every remaining error in the Symblic arm is an extraction error. The prior
work summarised in [PRIOR-ART.md](PRIOR-ART.md) (LINC, Logic-LM) also places the errors of translate-then-solve
systems in the translation step. This is one run of 15 generated items, without confidence intervals.

## 4. "The same flower from an essay" (6 essays)

Each applicator turned a prose description into a closed `FlowerSpec` (petals, shape, layers, colour,
centre, leaves, stem); the kernel drew it.

- Claude Haiku, Claude Sonnet, Codex, agy and Claude Opus (this session): **6/6 exactly right, and the
  same drawing bytes for every essay**.
- qwen3:4b: 5/6. llama3.2:1b: 0/6.
- Per essay, 5–6 of 7 applicators produced the identical drawing.

Given equal parameter records, the tested renderer produced equal drawing bytes. Whether the records
match the description or the author's intended flower is a separate question. The five named cloud
applicators matched the supplied references on these six descriptions; this is not perfect mental transfer.

## 5. Arithmetic word problems and small-model councils (24 generated problems, GSM-Symbolic style)

| condition | correct | median seconds |
|---|---|---|
| Claude Haiku / Claude Sonnet / Codex, direct | 20/20, 24/24, 24/24 | 6 / 4 / 12 |
| council of 5× qwen3:4b, typed answer, 5 votes | **18/18** | 121 |
| same council, `effort=ultra` (votes, then one round seeing each other's answers) | 19/19 | 596 |
| same council, formula + kernel (`key=eval(it)`), 5 votes | 18/20 (90%) | 180 |
| single qwen3:4b / llama3.2:1b (direct, typed, formula) | 3–4 items each: not enough to compare | 74–152 |

Read carefully:
- The completed five-model council cells were 18/18 correct; large-model counts have different
  denominators. These incomplete arms do not establish paired parity. The ultra arm had roughly five
  times the median latency of ordinary voting; different completed subsets prevent a clean gain estimate.
- In these runs the formula-plus-kernel council (18/20) did not score higher than voting on the typed number
  (18/18). The completed item sets differ; on the 3 items that every condition finished, both councils were 3/3.
- These problems are templated arithmetic that the large models solve perfectly, so they cannot show a
  council exceeding a large model, and the paused single-model baselines are too small to show the
  council's gain over one small model. Resume the run to settle that.

## 6. What this does and does not show

- **Mechanism:** the kernel computes formal results without model sampling. These receipts demonstrate selected
  cross-machine cases. Replay requires complete, compatible records and now enforces explicit pins
  ([EXECUTION-PINS.md](EXECUTION-PINS.md)). This determinism concerns the kernel's own computation and replay; it
  says nothing about what a model answers.
- **Measured, on these samples only:**
  - on 16 questions and 7 applicators, the typed form had 17 points higher pairwise identity than the prose form
    (95% CI +4 to +30, questions resampled together), and α of 0.77 against 0.60, without higher correctness (§2);
  - without llama3.2:1b (a subset chosen after seeing the data), unanimity was 8 of 16 questions for prose and 13 of
    16 for typed asks;
  - on 15 generated family trees, extraction + Datalog gave qwen3:4b 12/15 against 9/15 direct, at a median of 96 s
    against 296 s;
  - five cloud applicators turned each of six prose flower descriptions into the reference record, and drew
    identical bytes.
- **Not shown:** general identical open-ended outputs; agreement as correctness; universal small-model
  or council parity with larger models; complete transfer of an author's intended meaning.
- **Limits:**
  - one run, small samples (confidence intervals only for the identity table) and generated items;
  - prose and direct answers scored by text heuristics, typed answers exactly (the scoring note under the
    historical status);
  - CPU-only worker node models. Ollama was then capped at CPUQuota 200% and 3 GB by a drop-in (the worker node-hosts bullet of
    `docs/agents/CONTRACTS.md`). At the operator's direction the caps were lifted late on 2026-10-03, at about
    23:54: no CPU quota and a higher memory cap; one node that runs other services kept them.
    CONTRACTS.md's "worker node Ollama is uncapped" bullet records this without a date; the time is from
    `~/.local/state/symblic-local-tetris-20261003/CHECKPOINT.md`;
  - the operator's subscription models only;
  - no result from the host's model service (it runs only on the host, which was kept free of model load).

## 7. Phase 2: making agents converge (2026-10-02, night)

The operator asked for Symblic to become as predictable as possible: research how people and machines come to
read a description the same way, test the cube hypothesis ("there is a way to describe a cube so that anyone
builds it"), and get a technical paper that fresh groups of agents reproduce. Research:
[RESEARCH-LANGUAGE.md](RESEARCH-LANGUAGE.md) (logic, philosophy of language, communication, controlled languages) and
[RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md) (LLM agreement, ambiguity, measurement). Language changes:
[SPEC.md](SPEC.md) §4, §5, §7, §12; reliability fixes from an independent semantics audit
(`reinforcements/semantics-review.md`): transactional retries, per-item prompts, kernel results independent of
hash seed and integer-digit limits, static-check repairs. Later audits found additional soundness defects; the
kernel's adversarial regressions are in `tests/kernel/test_symblic_soundness.py`, whose 30 tests passed on every host in the
version-2.1 conformance run above.

### 7.1 The cube hypothesis, measured (4 solids, 4 description styles, up to 9 applicators, 2 repetitions)

Each applicator built a solid (exact vertices and faces) from a description: **minimal** ("Construct a cube."),
**everyday** (size, centre, orientation in plain words), **technical** (numbered steps with frame, coordinates
and a numbering convention) and **checked** (the technical text plus kernel end-state checks, re-asked with the
failing check). The first three styles were planned for 4 solids × 9 applicators × 2 repetitions (216 cells), and the
checked style for 4 solids × 5 applicators × 2 repetitions (40 cells). The three-style run was paused before it
reached the fourth solid (a square pyramid), so its rows cover the cube, tetrahedron and octahedron. Every answer is
judged by the exact geometry checker (v2: a closed, convex, consistently oriented solid; congruence by exact
isometry search), re-judged from the stored answers (`report.md` in `automation_data/symblic/bench/shapes-20261002/`
and `shapes-checked-20261002/`).

| style | answers | valid solid | congruent to the reference | same placement | identical record |
|---|---|---|---|---|---|
| minimal | 48 | 62% | 38% | 38% | 0% |
| everyday | 40 | 65% | 60% | 60% | 0% |
| technical | 37 | 62% | 57% | 57% | 54% |
| **checked** | 37 | 95% | 89% | 89% | **86%** |

In the checked style the kernel accepted 32 of 37 answers (86%), all of them the reference record. Three of the five
rejected qwen3:4b answers were valid solids; one octahedron had the reference placement and failed only the numbering
check. A sixth qwen3:4b cell, also rejected, was recorded at 23:13, after the stored report, and is not in these
percentages.

By applicator (same placement):
- **Claude Haiku, Claude Sonnet and Codex:** 4/6 minimal → 6/6 everyday → 5/5–6/6 technical → **8/8 checked**.
- **Antigravity (agy):** 4/6 minimal → 4/4 everyday → 4/4 technical → **8/8 checked**.
- **qwen3:4b:** 0/6 minimal, 2/5 everyday, 0/4 technical; checked 1/5 at the reference placement and **0/5
  accepted** (0/6 with the late cell).
- **Other small models:** granite3.3:2b matched the reference placement 2/6 times in the minimal style and 0/8 in the
  others; gemma3:4b (0/12) and llama3.2:1b (0/15) never did; phi4-mini answered 2 cells and matched neither.

What this shows:
- **For the four cloud applicators, each added specification raised agreement on the reference.** A minimal
  description fixes the shape only up to size and placement: 38% of minimal answers were congruent to the reference
  and 0% were identical records. Same placement (which normalises numbering and face order) equals congruence there,
  so the remaining difference is how writers number vertices and order faces. Plain-language size and position
  brought the cloud applicators to the reference placement (6/6; agy 4/4). A numbering convention made 20 of 37
  technical answers (54%) byte-identical.
- **Encoded checks constrain admitted records.** Each object's checks are written to admit exactly one canonical
  record (`SHAPE_CHECKS`, `SHAPE_ORDER_CHECK` and the comment above them in `symblic/bench/bench.py`). The vertex
  conditions fix the point set (the pyramid's by an explicit set), a
  valid convex solid's faces are its hull facets, and `solid = canonical_shape(solid)` fixes numbering and order.
  `tests/adapters/test_symblic_geometry.py::CheckedStyle` checks three things: the reference is accepted; six listed
  perturbations (seven for the cube) are refused; and a Python transcription of the cube's, tetrahedron's and
  octahedron's vertex conditions admits exactly the required points on the grid {−2, …, 2}³. As designed, all 32
  accepted answers, from four applicators and three model families, were the reference record, and repeated cells
  were 18/18 self-consistent.
- **Acceptance identity and coverage must be reported separately.** A reader that cannot satisfy the checks is
  rejected, not accepted with a different cube. qwen3:4b was 0/5 in the report (0/6 with the late cell). A minimal
  description can converge through shared defaults, but cannot establish a uniquely intended object without
  additional constraints: the hypothesis holds only for descriptions that determine their object up to a stated
  equivalence (RESEARCH-LANGUAGE §2).
- The three-style run was paused with 138 of its 216 planned cells recorded (142 result lines, including re-runs),
  to give capacity to the tightening runs. 52 of the 78 missing cells belong to the five small models, and the
  fourth solid was not reached.

### 7.2 Tightening: turning measured disagreement into a clearer statement

`symblic.authoring.tighten` asks every statement of a program of a probe panel (fresh context, temperature 0). Each reader
also lists the readings it sees. A statement is rewritten by a clarifier with explicit assumptions, without the
answer, when it is diagnosed ambiguous, divergent or a capability split (`analyse` and `TIGHTEN` in
`symblic/authoring/tighten.py`). Roughly, that is when the valid answers differ, or when two readers (one, if fewer than three
readers were reached) list another reading of an agreed answer. A statement with fewer than 60% valid answers is
diagnosed `format` and is not rewritten. The panel then answers again. The fair test is a **held-out panel that
shares no model** with the probes or the clarifier.

- **Pilot, finding 1** (probes Haiku, Codex, agy and qwen3:4b; held-out Opus, gemma3:4b, granite3.3:2b, phi4-mini
  and llama3.2:1b): the probes answered "How many days are in a year?" (365) and "What is the boiling point of
  water?" (100) unanimously. The held-out panel did not fully agree. On the year, llama3.2:1b answered 360. On the
  boiling point, every returned answer was 100; the agreement of 0.8 came from phi4-mini returning no answer, which
  the score counts as disagreement. "How long is a marathon?" gave 42.195 vs 26.2, which is km vs miles, a reading
  and not an error. Agreement among capable readers can hide ambiguity that shared conventions cover, so probes now
  list readings, and an agreed statement whose readers list another reading is clarified too (the rule above).
- **v2, finding 2:** after the rewrite "the official World Athletics distance, in kilometres, three decimals",
  held-out agreement on the marathon went **0.4 → 1.0**. All five held-out readers answered 42.195, including
  llama3.2:1b.
- **v2, finding 3:** the clarifier "fixed" the year by naming "the calendar year 2026". That needs leap-year
  knowledge, and held-out agreement fell **0.8 → 0.6** (granite and llama answered 366). A rewrite must name the
  convention ("a common, non-leap year"), never substitute a specific instance that needs more knowledge. This rule
  is now in the clarifier's instruction in `symblic/authoring/tighten.py`. The failure resembles what the
  communication literature calls the curse of knowledge: better-informed agents cannot ignore what they know
  (Camerer, Loewenstein and Weber, *Journal of Political Economy* 97(5):1232–1254, 1989; more in
  [RESEARCH-LANGUAGE.md](RESEARCH-LANGUAGE.md) §3.3). That is an analogy for one observed rewrite, not a measured
  effect.
- **v3 (24 statements: 18 with known competing conventions, 6 controls).** Probes: Haiku, Codex, agy,
  qwen3:4b, llama3.2:1b. Clarifier: Sonnet. Held-out: Opus, granite3.3:2b, phi4-mini. No model is in both
  panels.
  - **Coverage.** 12 of the 18 statements had all three held-out readers answer both before and after. On the other
    6, a small held-out model gave no answer in at least one phase, and in five of them Opus answered alone in at
    least one phase. The causes given at the time were worker node capacity and Ollama restarts; the stored rows record only
    which readers are missing. These 6 do not enter the paired agreement estimate; they still count against
    operational coverage.
  - **Where the held-out readers split along a real reading, tightening fixed it.** 3 of 4 went 0.67 → 1.0:
    - "how long is a marathon" (km vs miles);
    - "how many zeros in a billion" (short vs long scale);
    - "what are the primary colours" (RYB vs RGB).
    The fourth, teaspoons per tablespoon, stayed split: granite answered 2 before and after, a knowledge error,
    not a reading.
  - **Where they already agreed, two rewrites did harm.** 6 of 8 unanimous statements stayed unanimous. 2 broke:
    - Freezing point: the rewrite added "not on the Kelvin or Fahrenheit scale", and granite3.3:2b answered
      −17.77, about 0 °F expressed in Celsius.
    - Tomato: after a rewrite that named culinary vs botanical use, granite answered "vegetable".
    In both, the rewrite named the excluded reading and a small reader then gave it. Priming is a plausible
    explanation; it was not tested. The clarifier is now told to say what to use, never what to avoid (same
    instruction; not yet re-measured).
  - **Controls.** The diagnosis used in this run called 5 of 6 controls "ambiguous", because one reader listed a
    nuance, and 3 were rewritten. One broke: "feet in a mile" became 1760, yards, for granite. The diagnosis now
    needs two readers (one, if fewer than three were reached) to flag an agreed answer, or a deviation explained by
    a listed reading (tested with fakes, not yet re-measured).
  - Five rewrites of closed-answer statements were refused because they listed the options, the modal answer among
    them: three of the 18 test statements and two controls. That was an over-strict leak rule, fixed since (the
    closed-answer exception in `clarify`).
  - Net on the 12 fully covered statements: mean held-out agreement 0.889 → 0.917, unanimous 8 → 9.
  - The lesson is narrower than "tightening always helps": it fixed genuine reading splits, and a rewrite must
    state conventions positively and leave clear statements alone. Both rules are now in the code; a v4 run
    would measure them.

### 7.3 Papers that fresh groups of agents execute (`.symd`, built with peer session c2)

A paper is Markdown whose ```` ```symblic ```` blocks are the program. Definitions become terms, section prose
becomes the asks' context, and `reproduce` runs the paper with several groups of agents, each starting from
nothing, then traces any divergence back to a paper line.

- **Scaling a recipe:** reproduces. Haiku, Codex and agy each gave the same run fingerprint, `6f9f0545592d6906`,
  and the exact shopping list (540 mL, 45 mL, 7.5 mL, 300 g). In a second run, **qwen3:4b on the worker nodes' CPUs
  reproduced the same fingerprint in two separate recorded runs**, beside Haiku and Codex (agy was in an outage:
  coverage 4/5). On this one paper, the completed local-model runs matched the cloud runs. This does not isolate
  the contribution of definitions from arithmetic or establish general model-capability parity.
- **A furnace schedule**, three versions, each run by Haiku, Codex and Sonnet:
  - **Draft** with undefined "slowly", "room temperature" and "a couple of hours": 3 different readings, 1/3 correct.
  - **Definitions added:** reproduces in one run, all correct. In an earlier run Haiku filled in a field the
    paper's prose said to leave at 0, so only the result reproduced there.
  - **Contract version:** the reading is a routine that returns only what the computation needs. In its one recorded
    reproduction, all three cohorts gave the same fingerprint (`05907ee2df654a99`) and the correct total. That is an
    observation, not a universal guarantee about future extraction.
  - The design rule drawn from this: **never take from a reader what the kernel can compute**. A degree of freedom
    that the kernel computes is not left to the reader, so it cannot vary between readers.
- **Certification** (c2): the `text` library's routines (yes_or_no, choose_one, grounded items_in,
  count_in/number_in, summary_of with a word limit) passed every test for Haiku, Codex and agy, on replies recorded
  earlier and replayed from the call cache (0 new calls). In two separate qwen3:4b runs everything passed except
  `summary_of`: after their retries, both runs' last summaries had 14 words (earlier attempts had 13 or 14) against a
  12-word limit, and the kernel refused them. So `summary_of` is certified for the cloud cohorts and not for
  qwen3:4b. A routine counts as certified only for the cohorts that pass every test.
- **Crystallisation** (c2): the routine `is_metal(element)` was asked of a Haiku + Codex panel (two model
  families, effort high) for hydrogen through calcium. 20/20 answers were unanimous, and the frozen table
  matches the standard classification (Li, Be, Na, Mg, Al, K, Ca). Importing it answers with zero model calls;
  `is_metal("iron")` fails rather than guessing. Boron and silicon, expected to be contested, were not. Unanimity
  of two families is not correctness: the table is right because it matches the reference.
  Also new: the `dates` library (exact Gregorian arithmetic). Its test checks 20 dates (4 edge cases and 16 seeded
  random ones) against Python's `datetime` for day number, weekday, day of year and the inverse
  (`test_dates_match_pythons_calendar` in `tests/lang/test_symblic_lang.py`). The earlier figure of 44 checked dates is
  **reported, artifact not found**; the test file was last changed on 2026-10-03, after this result.
  A program can compute questions like "how many days are in year Y" (`days_in_year`) with it, without a model.
- **Agreement is not evidence of specification** (c2's slurry papers). "Prepare 200 g of a 40% alumina slurry
  … with 1% dispersant" reproduced across Haiku, Codex and Sonnet (one fingerprint): all three dosed the
  dispersant on the whole slurry (2 g). (The powder is named "alumina" here for publication; see
  [papers/README.md](papers/README.md).) c2's hand-written definitions dose it on the dry powder (0.8 g), which c2
  gives as the usual convention in ceramics practice; no source for that convention is stored with this result. A
  shared default reading is invisible to a reproduction test. **Readings expose it:** asked for alternative
  readings, Codex and Sonnet each listed the dry-basis reading (0.8 g) although every answer was 2 g, so
  tightening diagnosed the statement as ambiguous despite unanimous answers. The clarifier (Opus), then told to
  prefer "the most widely used convention", pinned the whole-slurry basis: the statement became unambiguous
  and the readers converged, but on the general convention, not the field's. Choosing between readings is
  the author's decision; tightening makes it explicit, not right. The clarifier now prefers the convention of the
  statement's field and names its choice. **Rerun:** the readings again included the dry basis, and the clarifier
  pinned "the usual ceramics convention: the dispersant dose is a percentage of the dry alumina" (named in its
  assumptions). The three readers that answered (Haiku, Codex and Sonnet; agy was in an outage) converged on
  80 / 0.8 / 119.2 g, the masses of c2's hand-written definitions. Automatic tightening reached the specification
  that c2's definitions encode, with the choice visible in its assumptions; the author still confirms it.
- **Furnace paper, tightened by machine and judged by readers who never saw the tightening.**
  - Probes: Haiku, Codex, agy, qwen3:4b. Clarifier: Sonnet. Held-out cohorts: Opus, gemma3:4b, granite3.3:2b,
    phi4-mini, each from nothing.
  - **Before:** the held-out cohorts read the steps 4 different ways. Only Opus produced the correct run.
  - **Tightening:** probe agreement went 0.33 → 0.67 → 1.0 over two rewrites. The final instruction restates
    the definitions and the paper's rule that ramps and cools carry minutes 0.
  - **After:** Opus, granite3.3:2b (IBM) and phi4-mini (Microsoft) produced the **identical run, fingerprint
    `93a84f87d61c14f4`**, which is also the correct hand-defined paper's. gemma3:4b did not finish: Ollama on node-d
    and node-f returned empty replies and then refused connections. That is an outage, not a reading. Ollama then ran
    under a 3 GB memory cap, and a crash while loading the model is a plausible cause, but the stored log records
    only the failed requests. Coverage 3/4.
  - Two held-out small models matched the Opus result on this paper. Coverage was 3/4, and the
    experiment does not establish general parity, independence or a population-level gain.
  - (The first experiment run did not write the final rewrite into the paper, because chained rewrites were
    mishandled. That is now fixed and tested; the after-test was run on the paper built from the final rewrite.)
- **Constructing a cube** (`papers/constructing-a-cube.symd`, the cube hypothesis as a paper; cohorts Haiku,
  Sonnet, Codex, Opus, qwen3:4b, each from nothing):
  - **First run, under-informed readers.** By a compiler choice since changed, each ask saw only the
    introduction and its own section, not "The object", where the paper states the edge length and centre.
    Every capable cohort first built the library-default cube with a corner at the origin. The paper's kernel
    checks rejected it and re-asked with the reason ("every edge 2 units long", then "every coordinate is 1 or
    -1"). All four then reached the **identical record, run fingerprint `bf548ea196d3ca27`**, the same as a
    perfect reader's, after exactly 2 re-asks each. qwen3:4b never produced a closed solid in 4 attempts
    (coverage 4/5). The end-state checks plus feedback carried readers who were missing facts to the one
    admitted object.
  - **Second run, fully informed readers** (each ask sees every earlier section, as a human reader would):
    Haiku, Sonnet, Codex and Opus each built the **identical record on the first attempt, with zero kernel
    re-asks: the same run fingerprint `bf548ea196d3ca27`**. qwen3:4b again produced no closed solid in 4
    attempts (coverage 4/5; with a cohort unfinished the strict verdict is "results reproduce").
  - So, for this cube: a description that states its frame, size, position and numbering convention made four
    fresh capable readers from three model families write the same object byte for byte. The paper's checks are the
    benchmark's checked-cube checks, which admit only that record (§7.1), so any answer they accept is that object,
    as far as the checker itself is correct. That is the cube hypothesis in its defensible form (RESEARCH-LANGUAGE
    §1): the object is fixed up to the stated equivalence, by a description that a fixed interpreter checks, and
    agreement on the reading is measured, not assumed.

Erratum (c2): paper records written between about 22:45 and 23:15 (`lang-20261002-paper-cloud`, `-furnace`,
`-furnace2`) carry a wrong paper `sha256` for papers with definitions (a shadowed variable hashed the definitions
list). Fingerprints and verdicts are unaffected; fixed with a regression test.

### 7.4 The determinism ladder (what can be claimed, rung by rung)

| rung | how a statement is decided | what holds, and on what evidence |
|---|---|---|
| kernel | exact arithmetic, logic, Datalog, geometry, drawings, standard-library facts (`dates`, `constants`) | specified to give the same result for equal formal inputs and semantic versions; observed equal for the tested programs on 8 machines (§1) and in 27 runtime profiles (version 2.1 receipt) |
| crystal | a routine's answers over a finite domain that a panel agreed on (unanimously by default), frozen into a kernel table | answered from the frozen table with zero model calls; outside the table it fails rather than guesses; the table is only as correct as the panel's answers, so it must be checked against a reference (`crystallise` does not do this; §7.3 compares the `is_metal` table with the standard classification) |
| contract | a routine returns only what the kernel needs; the rest is computed | choices the kernel computes are not left to the reader; results agree whenever readers extract the same facts |
| checked ask | the ask's checks admit exactly one canonical value (finite domains of up to 20 000 values: decided by enumeration, `Run.determine` in `symblic/kernel/run.py`) | when exactly one value is admitted, every accepted answer is that value; coverage (who reaches acceptance) is measured |
| defined and tightened ask | closed type, option definitions, terms, rewrites validated on held-out readers | agreement rate measured per panel; rewrites can help or harm |
| prose | a natural-language instruction | agreement measured; no guarantee |

Agreement does not establish correctness. `ensure`/`assert` establish conformance to encoded predicates,
which may be incomplete or wrong. An outage reduces operational coverage; it is not a disagreeing answer.

## 8. Historical resumption recipe

This records the earlier command, not a current launch instruction. Any new run must recheck fleet
capacity, reservations and admission/power fences, and use a versioned output directory.

```
systemd-run --user --collect --unit=symblic-bench-nodes --slice=a systemd slice for work --nice=10 \
  --property=IOSchedulingClass=idle --property=CPUQuota=50% --property=MemoryMax=1G \
  --working-directory=$HOME/host-checkout -- .venv/bin/python symblic/bench/bench.py \
  --out automation_data/symblic/bench/nodes-20261002 --workers 6 --arith-per 3 --ultra \
  --identity-apps "claude:haiku,claude:sonnet,codex,agy,ollama:llama3.2:1b,ollama:qwen3:4b-instruct" \
  --small "ollama:qwen3:4b-instruct,ollama:llama3.2:1b" --big "claude:haiku,claude:sonnet,codex" \
  --council "ollama:qwen3:4b-instruct@node-a,ollama:qwen3:4b-instruct@node-b,ollama:qwen3:4b-instruct@node-d,ollama:qwen3:4b-instruct@node-f,ollama:qwen3:4b-instruct@node-i"
```

The historical estimate was about 130 cells remaining (mostly single small-model arithmetic, ~1 h of worker node CPU). It
follows from the 644-cell total above, which is not in the stored log, so recount the remaining cells before
resuming. That timing assumed the worker nodes' former Ollama CPU cap. Run it in a cool period and without a long the temporary high-power mode
lease. The page's Evidence screen and `symblic/bench/bench.py --out … --report-only` show the report.
