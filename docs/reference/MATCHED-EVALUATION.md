# Matched evaluation protocol

`--suite matched` runs a frozen comparison between a direct model request and a
single production `Run(profile="verified")` typed capsule. This page describes
protocol version 2. Both arms receive byte-identical task text (question, format
rule, any contract feedback and exact serialized context), the same canonical output
type, model schedule/settings, output schema, dispatch budget, repair policy and
gold-free validator. The prompt framing around that text is the declared treatment.
This measures one typed decision; it does not measure arbitrary programs or establish
reliable project completion. This page reports no model results.

The older identity/arithmetic/logic/shape/flower suites retain their historical
scorers and records. Their report now labels the heuristic grading and observed-cell
denominators. A last-number match, a normalized prose match or a successful model
call is not newly reinterpreted as exact correctness.

## Freeze, run, resume and report

A synthetic manifest is at
[`symblic/bench/data/matched-example-v1.json`](../../symblic/bench/data/matched-example-v1.json) (manifest
format 1, which protocol 2 still accepts). Its `fake:*` labels are placeholders for
injected test Applicators. Set explicit real applicator IDs before intentionally
running a provider experiment.

```sh
python3 -m symblic.bench.bench --suite matched --out /tmp/matched-example \
  --matched-manifest symblic/bench/data/matched-example-v1.json --dry-run
python3 -m symblic.bench.bench --suite matched --out /tmp/matched-example --report-only
```

Neither command constructs Applicators or calls a provider. For an actual experiment,
freeze a manifest with the intended model IDs, then run the same frozen assignment:

```sh
python3 -m symblic.bench.bench --suite matched --out /path/to/experiment --resume
```

The runner uses the existing `symblic.providers.applicators.Applicators` admission path, serially,
in the frozen counterbalanced order (see Arm order). It does not start a provider on
import. It does not retry historical suite rows. Composite council/automatic
applicators are refused because their nested calls are outside this runner's receipt
boundary. Provider-internal work and retries remain unobserved and are not claimed as
measured calls. Resume executes only assignments that never started; an interrupted
assignment stays uncertain. A new experiment directory is required for a changed
manifest, implementation or protocol version. `--report-only` can still inspect an
earlier implementation's or protocol's records and reports the difference (see
Versions and version 1 reports).

Python integration is explicit:

```python
from symblic.bench.matched import MatchedBench
bench = MatchedBench(output_directory, manifest, apps=injected_applicators)
summary = bench.run()
```

For API integration, validate/freeze the manifest before creating a worker or
Applicators. Run this object inside the existing admitted benchmark job. For reads,
use `symblic.bench.matched.load_summary(folder)`: it validates the frozen plan and
cell journals without mkdir, writes, dispatch or worker launch, returning
`{ok, summary, markdown}` (or `ok: false` with an error for an unreadable plan). One
unreadable cell is reported as a damaged cell, never as an unreadable experiment.
Use the returned frozen plan ID and assignment counts; do not derive a denominator
from successful result rows. The read bridge does not call a model; `bench.report()`
additionally writes report artifacts and is intended for the benchmark worker/CLI.
Existing web benchmark controls should expose this as a separate protocol, with
explicit models and a visible held-out split, rather than append its counts to
historical suite accuracy. No new API or web control is installed by this module itself.

## Exact task exposure

For each dispatch the runner builds one task text, used unchanged by both arms:

```text
<question>
<output-format rule>
CONTRACT FEEDBACK: <fixed rejection sentence>     (only on a contract_only repair)
TASK CONTEXT JSON:                                 (only when the case has context)
<context as json.dumps(ensure_ascii=False, sort_keys=True)>
```

- **Direct arm:** a fixed system sentence and the prompt
  `<task text>` + `\nOUTPUT TYPE: <canonical type label>`.
- **Typed arm:** the verified program `given task: Any.` /
  `ask answer: <type> "{task}".`, with the task text passed as the runtime input
  `task`. The task never becomes program source, so non-ASCII text, decomposed
  accents, `\r`, other control characters, quotes, backslashes, `{...}`, `\{...\}` and
  `#` reach the model exactly as in the direct arm. The input is `Any` because a
  `Text` input is normalized (NFC, line endings, surrounding whitespace). The capsule
  quotes the task text as its statement's instruction and adds its own system
  prompt, program header and answer-format lines. That framing is the treatment.
- **Not shown to either arm:** case ID, family, rubric, gold and other splits' data.

Before writing a dispatch intent, the runner checks that the request carries the
exact task text (the whole direct prompt, or the capsule statement quoting it). If
not, the cell fails in the harness before any dispatch. Every dispatch records
`information_sha256`, the SHA-256 of that task text's UTF-8 bytes. The summary
compares each pair's first-dispatch hashes (`paired[].information`: matched,
mismatched, unrecorded). It also reports `observed_protocol.information_mismatched_pairs`.
Contract feedback appears only after a contract rejection, so later dispatches can
differ by design. These hashes are host records, not provider attestations. Both
requests carry the same JSON output schema, temperature, seed (plus the repeat
index), effort and `tools: none`.

## Declaration and boundaries

The manifest has these required fields:

- `version: 1` (manifest format), `cases`, `arms`, `model`, `schedule`, `feedback`,
  `split`, `repetitions`.
- Cases have unique `id`, `family`, `split` (`train`, `dev`, `heldout`), public `input`
  and evaluator-only `rubric`. Input contains `question`, `type`, and optional JSON
  `context`. The runner does not pass case IDs, families, rubrics or other split's
  data to a model.
- `type` is validated where it is used: freeze parses the typed arm's actual program
  under the verified profile. Freeze refuses a type that ends, comments out or extends
  the ask (an extra statement, `from`/`by`/`with`, other instruction text), an unknown
  named type, or one outside exact JSON scalar/list/record types. It also checks that
  the runtime input would carry the task text unchanged, with and without feedback.
  Both arms show the canonical type label, so `((Int))` is shown as `Int`.
- Each arm declares `id` and `treatment` (`direct` or `typed`). All five control axes
  are derived once and fingerprinted identically across arms: model, information,
  budget, feedback and validator. The information axis also declares the task
  delivery and type labelling. Request hashes record the actual distinct prompts.
- `model` declares unique `primary`, `fallback`, and `stronger_fallback` lists plus
  `settings` (`temperature`, integer `seed`, `effort` low/medium). Stronger is an
  author's declared cohort, not a measured model ranking. A schedule lists every
  permitted `{model, role}` dispatch and starts with a primary. Both arms stop at
  the first contract-valid answer or explicit abstention. A wrong but well-formed
  answer does **not** trigger gold-guided repair or fallback.
- `feedback` is `none` or `contract_only`. The latter exposes the same fixed format/type
  rejection sentence, never gold or correctness. Refusal/transport failure creates
  no fabricated semantic feedback. The dispatch cap includes refusals and errors.
- Optional `max_prompt_characters` is enforced before dispatch for both treatments.
  No time, token or dollar ceiling is claimed. Model tokens and dollars are included
  only when the provider returns valid values in `usage.input_tokens`,
  `usage.output_tokens`, `usage.usd`; missing/invalid fields remain unmeasured.
- Optional `order_seed`, an integer in 0..2^31-1 (default 0), fixes the arm order
  reproducibly (see Arm order).
- Optional `spec_labor` measurements contain unique `id`, `arm_id`, nonnegative
  `minutes`, `method` (`timed` or `self_reported`) and `scope`. They are counted once,
  not multiplied by tasks or repetitions. Absence means unmeasured.

Output is one complete JSON envelope `{"answer": value}` with optional string
`reasoning`, or exactly `{"abstain": true}`. Raw text takes precedence over a parsed
provider object so duplicate keys, surrounding prose and malformed JSON cannot be
hidden by a permissive parser. Every envelope violation is recorded with encoding
`invalid_envelope` and grades `malformed` under every rubric mode. Violations include
text that is not one strict JSON object, extra or missing fields, non-text `reasoning`,
nonfinite numbers, invalid Unicode and a reply over the 2 MB size limit. The receipt
keeps at most 4,000 characters of such a reply; a longer reply's length and SHA-256 are
noted in its error. A well-formed envelope whose value breaks the declared type keeps
that value for exact grading: `"8"` for `Int` is incorrect under `typed_json`, and a
non-text value under `exact_text` is malformed.

Both arms use the same exact scalar/list/record shape validation; numeric strings,
dropped fields, boolean/integer substitution, value-changing rounding and other
transformations are rejected. Unsupported types such as Code/Set are diagnosed
before the experiment. Symblic still supports those types; this exact JSON
evaluation endpoint does not pretend to grade them. If the verified runtime and the
shared validator disagree about an answer, that is a harness failure, not a model
outcome.

`typed_json` rubrics compare complete values with type-sensitive equality: `1`,
`1.0`, `true` and `"1"` differ. `exact_text` requires Text and matches the whole
string, with only an explicitly declared `outer_whitespace` normalization if used.
There is no prose entailment judge, entity guessing, last-number extraction, or
substring scoring. Gold must satisfy the same output contract before freezing.

## Arm order

The protocol 2 plan interleaves arms within each case and repeat. Each case/repeat
block uses one row of a balanced Latin square (Williams design). `order_seed` decides,
reproducibly, which arm takes which row slot and which row comes first; each later
block takes the next row. The plan records
`order: {design: balanced_latin_square, seed, unit: case_repeat}` and every
assignment's `position`. The runner dispatches assignments in plan order. Over each
full cycle of rows (k blocks for an even number k of arms, 2k for an odd number),
every arm takes every position equally often. With an even number of arms, each arm
also immediately follows each other arm exactly once within a cycle's blocks. With two
arms, the first arm alternates between blocks. When the blocks are not a whole number
of cycles, two arms' counts for one position differ by at most 1 (even number of arms)
or 2 (odd). The summary's `order.positions` gives each arm's count per position.

Each dispatch intent and attempt records `dispatched_at_ms`, the host's wall-clock time
in Unix milliseconds. Counterbalancing spreads warm-up, cache, thermal and drift
effects across arms; it does not remove them, and latency remains a host
measurement around `Applicators.call`.

## Cells, outcomes and unresolved pairs

Every planned assignment is one cell and stays in the denominator. A cell ends in
exactly one status:

- `pending`: never started (no start record); resume runs it.
- `complete`: an answer or explicit abstention was selected.
- `failed`: the schedule ended without a contract-valid answer or abstention.
- `harness_failed`: the harness ended the cell (for example the prompt ceiling,
  the verified runtime failing before dispatch, a missing exact task text, a
  runtime/validator disagreement). `failure.json` records why. Dispatches already
  made still count.
- `uncertain`: started but without a final receipt. Its intents without results are
  `unknown` attempts. It is never re-run automatically.
- `damaged`: its start record, journal or receipt is torn, malformed, mismatched or
  misfiled.
- `cancelled`: a receipt recorded as cancelled (this runner does not write one).

Each cell also gets a `resolution`. It is `resolved` when the outcome is
model-attributable: `complete`, or `failed` after at least one dispatch where every
dispatch returned a model reply. Otherwise it names the reason:

- `pending`, `uncertain`, `damaged` or `cancelled`;
- `harness`: failed with no dispatch, `harness_failed`, or failed with a `failure.json`;
- `infrastructure`: failed with at least one refused, errored, unknown or cancelled
  dispatch, so part of the declared schedule never reached a model.

`summary.cells` and each arm's `cells` keep exact accounting:

- assigned = pending + attempted;
- attempted = damaged + attempted with a recorded dispatch + attempted without one;
- assigned = sum of `by_status` = `resolved` + the unresolved reasons.

A summary whose counts do not balance is refused. The Markdown report prints this
accounting and a separate harness-failed column.

Per-arm rates still divide by all assigned cells: an unresolved cell is not correct
there, and it is shown separately. In the paired table (`paired[]`), only pairs whose
members are both resolved enter `both_correct`, `left_only_correct`,
`right_only_correct` and `neither_correct`. A pending, unfinished, damaged, harness or
infrastructure cell is never counted as a wrong paired answer.
`assigned_pairs = resolved_pairs + unresolved_pairs`. `unresolved` splits pairs by
which side is open, `unresolved_reasons` counts each side's reasons, and family rows
carry the same resolved and unresolved pair counts. No independent-sample confidence
interval is implied.

## Held-out integrity and durable evidence

Family IDs and exact input hashes cannot cross train/dev/held-out splits. Optional
`exposures` declare case/family/input references and purposes (train, tune, prompt,
repair, score). Held-out answers/feedback are evaluator-only; only that assigned
case's input may enter its prompt. Freeze fails on declared leakage. These checks
cannot detect paraphrased leakage, dishonest family labels, prior manual exposure,
or model pretraining. Keep those limits in any empirical claim.

`matched-plan.json` freezes assignments, their order, gold, controls, source hashes
and semantic kernel identity before a call. It is private evaluation material.
Per-assignment `started.json` is exclusively created before execution. Each provider
call writes and flushes a dispatch intent and a response receipt to `events.jsonl`.
Final `receipt.json` must name its own cell's assignment and preserve exactly those
attempts. A misfiled, partial, mismatched or corrupt receipt damages only its own cell
(`receipt_integrity.issues`); other cells are still scored. If a receipt cannot be
built, `failure.json` records why, the cell stays without a receipt, and the run
continues. The files are host records and checksums, not signed attestations of
provider behavior.

## Known and unknown cost

Costs are counted per dispatch attempt, whatever the cell's resolution: unresolved,
harness-failed and infrastructure cells keep their recorded attempts and known costs.
For each cost field (`latency_ms`, `input_tokens`, `output_tokens`, `usd`) the
summary gives `known_total`, `observed_attempts` and `unobserved_attempts`; a missing
value is unknown, never zero. An intent without a response is an `unknown` attempt: it
may have been dispatched, so its billable cost is unknown. A damaged cell's journal and
receipt are not trusted, so its dispatches are left out of the attempt and cost totals;
its cost is unknown, not zero. `cost_unresolved_assignments` counts pending, uncertain
and damaged cells. Cached provider responses are not fresh agreement observations and
their historical token/USD usage is not charged again. Fresh calls count dispatch
attempts, including refusals, not billable provider calls.

`matched-summary.json` and `matched-report.md` separate correctness, delivered false
acceptance, validator acceptance, abstention, refusal/error/malformed outcomes, every
cell status and resolution, fresh/cached attempts, strong-model fallback, initial
correctness, measured agreement, paired family outcomes, arm order and known/unknown
cost coverage. Agreement never supplies a correctness label. No performance claim
follows from the synthetic tests or example.

## Versions and version 1 reports

- Arm declarations remain version 1.
- Plans, receipts and summaries are version 2.
- The frozen experiment (`matched-plan.json`) is runner version 2.
- The manifest format stays 1; `order_seed` is optional.
- A summary reports `version`, `plan_version`, `runner.version` (the experiment's
  protocol) and `runner.reader_version`.
- Rows from different protocol versions are not one measurement.

Version 1 experiments still verify (their plan identities are unchanged) and still
load with `--report-only` or `load_summary`. They never run or resume under the
current implementation; freeze a new experiment directory instead. A version 1
report:

- shows `runner.version: 1` and `plan_version: 1`;
- labels the arm order `fixed_case_arm_repeat`, with latency, cost and time-dependent
  provider state confounded with arm;
- adds a limit: version 1 interpolated the task into escaped program source, so
  non-ASCII text, control characters, braces or an annotated type could differ in, or
  fail before dispatch from, the typed arm;
- keeps its receipts' recorded grading (an envelope violation recorded as text is not
  regraded);
- uses the same resolution rules, so a version 1 failure with no dispatch or with a
  `failure.json` is an unresolved harness cell, not a model failure.

## Paired obligation feasibility, 5 October 2026

[Audited aggregate and source bindings](evidence/2026-10-05-obligation-pilot.json): retain all four assigned projects and sixteen slots, including eleven unreached stages and three generation timeouts. Nine calls delivered six strict replies and no completed milestone. The obligation gate prevented three observed valid-but-off-target adoptions; it did not establish a completion benefit. Grade raw replies separately from native adoption, and compare identical requests only on actual shared prefixes. Read the captured merged provider options: the master defaults were not the effective generation ceilings. Missing usage remains unknown. A different card or focused-context treatment needs a new preregistration; these results remain frozen.


## Focus versus task-card feasibility, 5 October 2026

The [audited `/8` versus `/9` pilot](evidence/2026-10-05-proof-card-pilot.json) froze the current runtime, identical exact obligations and effective provider options before eight real calls on the 1B and 2B local models. All eight replies used the strict ordinal wire; neither arm adopted a step. The four assigned projects retain all sixteen slots, including twelve unreached. Two card selections matched the requested formula but had the wrong free-assumption scope, and the gate rejected them.

Reported input tokens were 10,037 for focus and 5,152 for card (four calls each); each arm reported 28 output tokens. Input and output counters are complete for these calls; schema breakdown and authoring cost are unknown. The two initial shared-prefix pairs differed only in prompt; repair feedback can differ. This is a small descriptive feasibility result, with no completed-project cost, general quality gain or cross-model equality established. Independent fresh observations confirmed all eight remote units inactive, no assigned loaded models and the controller absent; all eight nodes restored the owned power lease.
