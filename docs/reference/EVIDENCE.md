# Symblic evidence and assurance

Implementation scope: 2026-10-03, language 2.1, canonical form 3, evidence schema 1.
This document describes implemented records and their limits. It does not report a new live-model
accuracy result. The language rules are in [SPEC.md](SPEC.md); dated measurements are in
[RESULTS.md](RESULTS.md).

## What a result establishes

| Record or outcome | What it establishes | What it does not establish |
|---|---|---|
| Typed answer | The accepted value passes the implemented type/coercion rules | Faithful interpretation, factual truth or units absent from the type |
| Passing `ensure`/`assert` | Conformance to the encoded predicate on the recorded state | That the predicate captures the intended requirement or uses true premises |
| Exhaustive finite determination | Exactly one canonical value in the declared domain passes the supported predicates | Uniqueness outside that domain or a match to an unformalized intention |
| Agreement | Recorded answers coincide under a stated comparison rule | Independent evidence or correctness |
| Kernel computation | A value computed under the recorded formal semantics | Empirical truth of its inputs; exact real arithmetic for transcendental approximations |
| Capability observation | A host-acquired result with capability, arguments and outcome provenance | A flawless instrument, true source contents, or independent acquisition |
| Crystallised table | Repeatable lookup of the recorded entries without a model | Generalization or truth of the table's entries |
| Certificate | Test outcomes tied to source, module and semantic kernel hashes | A signature, trustworthy issuer, general model competence or hosted-model freshness |
| Lock replay | Reproduction from compatible pinned records without fresh model calls | A fresh independent observation of the world |

Language can make reference, units, alternatives and acceptance conditions explicit. It cannot recover
an author's unexpressed mental image. For a flower, for example, specify petal count, color space,
geometry and the required equivalence: same parameter record, same rendered bytes, or some independently
defined perceptual criterion. These are different targets. Symblic's renderer implements the first two;
it does not prove perceptual or experiential identity.

## Observation declarations and recorded dependencies

An applicator record can declare an observation mode and source/assumption identifiers:

```symblic
group readers = [
  {app: "claude:haiku", mode: "text-reading", sources: ["description-v1"], assumptions: ["SI-units"]},
  {app: "codex", mode: "coordinate-reading", sources: ["coordinates-v1"], assumptions: ["SI-units"]}
].
```

`mode` is a nonempty label of at most 160 characters. `sources` and `assumptions` are lists of up to
32 nonempty identifiers, each at most 200 characters, deduplicated and sorted. They have
`origin: author_declared`. They do not cause a different sensor, representation or source to be delivered;
the program and acquisition path must actually supply those inputs. Merely labeling two copies of the
same prompt differently does not create two observation modes.

For typed model observations the applicator label records the request, and `requested_node` is separate
from `model` and `node`, which contain only identifiers actually supplied by the reply. Missing actual
identifiers stay empty and are flagged as incomplete provenance; requested values never fill them. The
runtime also records answer/request/capsule/statement hashes, family labels, attempt and round, alternative readings,
and whether repair feedback, a kernel oracle or peer answers were exposed. Model identifiers supplied
by an adapter are not an attestation of the provider's weights. Invalid or unavailable responses remain
call failures rather than becoming typed observations.

Per-answer evidence identifies the claim by source hash, statement location, name, type and kernel. It
lists shared recorded dependencies such as prompt capsule, statement, model, oracle, declared sources
and assumptions, and flags missing declarations. `independence` remains `not_established`. Different
providers, model families, machines, random seeds and mode labels receive no automatic confidence bonus.

Derived bindings carry parent hashes and evidence references. A memo hit refers back to the original
observations; it is not a new vote or a new measurement. In particular, repeated nested routine calls
must not turn a low-agreement answer into unanimous evidence. Audit history survives a rejected attempt,
while its mutable program state and memo entries are rolled back.

## Predicate receipts and finite determination

The evidence sidecar records checks with a predicate hash, source location, pass/fail outcome, referenced
binding hashes, kernel identity and scope `encoded_predicate`. The sidecar must be interpreted with the
pinned source, modules and execution state; it is not a standalone formal proof certificate. A predicate
that queries facts or invokes a routine can depend on more than its directly named bindings.

The finite evaluator currently handles supported domains of at most 20 000 candidates and anchored
retry checks with only builtin kernel calls and intervening `let`/`ensure` statements. User routines,
extensions and parallel `for each` asks are outside this speculative evaluator. Reports expose the
number evaluated and whether the search was exhaustive. Multiple witnesses establish ambiguity inside
the domain; only a completed search can establish a unique solution or no solution. Contradictory
supported contracts fail before any model is called. `solve=true` can return the unique solution directly.
`report.evidence.determinations` and determination trace events preserve every evaluated attempt,
including failure witnesses. A kernel-only ambiguous domain fails with `SYM_UNDERDETERMINED` and
the witnesses; it does not manufacture a unique answer.

The assurance label `unique_in_declared_domain` requires exhaustive uniqueness and a match between the
selected value and that unique value. Otherwise the evidence reports `typed_answer`. Neither label is
a calibrated probability or an assurance about all possible interpretations of the prose.

## Checked escalation and budgets

```symblic
ask n: Int in 1..4 "Return an integer whose double is 6." with route=escalate
ensure n * 2 = 6 else retry.
return n.
```

Given an ordered applicator list, escalation tries each applicator with a supported contract and stops
at its first passing candidate. A rejected answer may receive bounded repair feedback before moving
on. The route therefore exposes verifier information; its accepted accuracy must be reported separately
from first-attempt accuracy. It refuses a missing/unsupported contract instead of accepting an unchecked
candidate. Voting options and the peer-exposure `ultra` mode do not apply to escalation.

The selected-answer metadata retains a compatibility `agreement` value of 1 with scope
`single_selected_answer`. This is not consensus. Run-level agreement requires at least two valid
answers in the final voting round and is null when no such asks exist. Failed attempts are not votes. Use route-attempt records for acceptance, rejection, latency and calls.

The default model-call cap is 2 000 (`max_calls` / CLI `--max-calls`), shared across voting, repairs and
escalation; the ask cap is a separate 400. Kernel candidate checking consumes the same kernel step
budget as the run. Exhaustion is a visible failure, never permission to bypass a predicate. Platform
admission, worker limits and capability policy still apply independently.

## Test certificates and locks

`symblic.lang.abstraction.certify` records each cohort's tests, status, call counts, source SHA-256, semantic kernel
and hashes of the module sources actually imported by that test run. It emits an aggregate module map
only when cohort maps agree. Missing provenance is not filled by assuming today's modules were used.
The CLI can write a private artifact with `certify ... --certificate-out PATH`.

`symblic.kernel.certificates.make_certificate` binds that report to its source and module/kernel pins. A routed
cohort must pass the complete nonempty suite, finish successfully and actually exercise model calls;
a pure kernel-only suite cannot qualify an unexercised model. Duplicate or inconsistent test/cohort
records fail qualification. The runtime uses only eligible single-applicator cohorts; passing as a
council does not certify its individual members. `tools/symblic run ... --certificate FILE` validates
the pins and forces checked escalation. Route order is declared order, not a measured cost ranking.

A certificate's SHA-256 is an integrity checksum. Someone able to rewrite the artifact can also recompute
it; there is no issuer signature or independent authentication. The scope is `observed_tests_only`,
model identity is limited to requested cohort labels, and hosted-model freshness is `not_established`.
Passing a finite suite provides evidence for those tests under those conditions, not a guarantee for
new inputs, newer provider models or arbitrary agents.

Locks additionally preserve the answers, source/modules, evidence and supported effect ledgers needed
for replay. Strict replay refuses incompatible semantic pins and missing answers; it cannot silently
ask a model to repair the record. Legacy unpinned records may be inspected but do not acquire current
replay guarantees by being opened. A lock checksum has the same authentication limitation as a certificate.

## Observations, actions and extension boundaries

The first-party `observe` and `act` extensions dispatch only capabilities declared by the embedding host.
They validate arguments and result types, attach acquisition provenance and keep intent/outcome ledger
records. Preview acquires nothing. Replay reads recorded outcomes and refuses missing outcomes. For a
non-idempotent action with an uncertain outcome, resumption must resolve that uncertainty before another
dispatch. This is recovery discipline, not a general exactly-once guarantee for external services.

Static extension hooks are `check(node, scope)` and `check_program(program)`; both must be pure. Static
retry analysis rejects effect statements and follows known local routine calls. Ledger-backed `observe`
statements can reuse a read with unchanged arguments or acquire a new result for changed arguments;
the earlier acquisition remains in the audit record. Runtime gates remain necessary for imported or
otherwise unknown call paths. `self_gating=True` is reserved for
trusted ledger-backed extensions implementing their own preview/replay protection. Python extensions
and the host are trusted components; a source-level type check is not a sandbox for arbitrary Python.

`Run.execute()` reports `done`, `failed` or `stopped`. Error kinds and `SYM_<KIND>` codes distinguish
failure causes; they are not all model errors. The embedding `on_event` callback receives detached,
sequence-numbered trace rows after they are recorded, and callback failure stops later execution with
a visible `event` error. Consumers should retain failed attempts and check final status before treating
an output as a completed result.

## Applying the multi-frame design rationale without overstating it

One design rationale for these records is to check a claim through observation routes that do not share a
failure mode (for example a recorded observation, a tool result and a model's recall). Symblic applies it by
recording acquisition modes, common sources, assumptions and derived dependencies, and by distinguishing an
external observation from model recall. This is a design rationale, not an empirical demonstration that this
implementation improves accuracy.

The philosophical lesson is conditional: seek complementary ways of checking the *same claim* and test
their shared failure modes. It does not follow that model mixture always helps, that differently named
modes are independent, or that repeated samples can never help. Formal diversity arguments require
assumptions such as evidential relevance and conditional independence that mere method labels do not
establish. See [Stegenga and Menon, *Robustness and Independent Evidence*](https://doi.org/10.1086/692141).

Language research also supports explicit reference and repair, with grounding sufficient for the task,
rather than perfect mental transfer: [Clark and Brennan, *Grounding in Communication*](https://www.cs.cmu.edu/~illah/CLASSDOCS/Clark91.pdf).
[ACE's interpretation rules](https://attempto.ifi.uzh.ch/site/docs/ace/6.5/ace_interpretationrules.html)
illustrate how a controlled language fixes scope and attachment by convention. Such rules make a reading
executable; a reader or author must still confirm that it is the intended reading.

## Evaluation requirements

Compare equal-budget conditions: one model, repeated samples, mixed models with the same representation,
and genuinely different acquisition/representation methods. Preserve blind first rounds separately from
feedback and peer-exposed rounds. Validate references independently of the generation/checking pipeline.
Report wrong accepted answers per assigned task, correct completions per assigned task, first-attempt
accuracy, repairs, abstentions/failures, calls, latency and shared wrong answers. Include unavailable tasks
in operational coverage; identify the paired complete-case subset separately. A held-out task and model
panel is needed before claiming transfer to smaller models. Current pilot and conformance receipts belong
in [RESULTS.md](RESULTS.md) when available, without retrofitting them onto historical results.
