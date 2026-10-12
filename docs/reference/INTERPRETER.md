# From an idea to a checked program

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

Open **Symblic → Interpreter** at `/automation-studio/symblic.html#interpreter`.
The existing Write editor, library, runs and comparisons remain available.

1. Describe the result you want. Select **Confidential / local only** when the
   request must stay off cloud models. Otherwise the interpreter inherits
   the host executor's current routing policy, including its local-first default.
   **Interpreter model** lists the cached model catalogue, including local models.
   Choose an exact model and machine, or leave **Use routing policy** selected.
2. Analyse the request. Review the proposed goal, requirements and assumptions.
   **Ask for specifics** is selected initially. It requires a pending question
   from a model analysis; clear it when you only want a read-back. Recognized
   deterministic recipes need neither a model nor a clarification question.
   A question should distinguish outcomes that matter: an image versus an editable
   3D object, centimetres versus inches, a one-time action versus a schedule.
   At most three questions are pending at once. You can answer freely.
3. Correct a mistaken requirement with a reason, decide on proposed assumptions,
   or add a clarified request. The original request and earlier answers stay in
   the record. Corrections invalidate the old translation.
4. Translate to Symblic. Read the program, recorded inputs, diagnostics and the
   scope of each check. Copy the complete rewritten prompt when you want to use
   it elsewhere without starting anything.
5. **Run in the host executor** starts the checked program through the existing executor.
   Its link shows the actual execution outcome. The host executor retains the operator's
   full/guarded setting; interpretation does not silently change that setting.

For example, “make the flower I imagine” does not specify whether the output
should be a picture, a drawing or a physical design. Choosing an output kind is
more useful than asking for twelve decorative preferences at once. A physical
design then needs relevant dimensions, units, loads and materials. An image can
leave aesthetic judgments explicit and subjective. Neither workflow can recover
an unexpressed mental image with a universal guarantee.

## What is recorded and checked

`symblic/intent/records.py` preserves the original text and append-only operator turns.
Requirements, assumptions and examples record their origin. A model cannot
declare its proposal to be an operator statement or silently remove an earlier
requirement to make agreement easier. The operator can retire an incorrect
requirement; its text and the correction remain visible.

Optional source references contain an exact quote, source SHA-256 and Unicode
code-point offsets. Quote matching checks provenance, not whether the quote
entails a proposed interpretation. Model suggestions remain suggestions even when
they cite a matching span. An adopted assumption is still an assumption.

The translator reuses the host executor's declared capability catalogue, deterministic
recipes and planner. It checks the actual generated program with the Symblic and
effects checkers. Generated code must use explicit typed `ask` statements: a
misplaced option line cannot quietly become another prose question. Automatic
clock inputs are captured during translation and displayed as recorded inputs.

A translation pins the intent content revision, source text, inputs, source
snapshots, kernel identity, first-party modules, library, catalogue and effective
policy. A changed pin requires a fresh translation. Model-free recipes remain
model-free. Compilation performs no capability calls or exploratory tool reads.
The Interpreter compares these pins when displaying a saved translation. A stale
or unavailable comparison disables starting a new run and explains how to
retranslate; existing native run links and the original read-back remain usable.
This display reads metadata only. Handoff independently rechecks compatibility,
so a matching display is not permission to bypass a later deployment change.
Execution checks the pinned deployment again before its first statement, uses
captured standard-library sources, and rejects incompatible capability contracts.
It also detects stale accepted Python bytecode for the pinned files. See the
[execution-pin scope and limits](EXECUTION-PINS.md); this is local compatibility
checking, not attestation of arbitrary extensions or external tool implementations.

The display separates these claims:

| Receipt | What it establishes |
| --- | --- |
| Exact source quote | Those characters occur in the retained source |
| Typed model proposal | The answer satisfies the recorded structural checks |
| Static/effect check | The encoded program passes the named language and capability rules |
| Finite example | Only the explicitly executed example, when such a receipt exists |
| the host executor run handle | The native run was started or recovered; inspect its outcome |

No receipt is labelled “intent proven.” Proposed examples in a read-back are not
reported as executed tests. Arithmetic consistency alone cannot prove a faithful
invoice extraction; a word-count bound cannot prove a faithful summary.
The evidence details also distinguish operator-adopted assumptions, exact source
quotes, current-reply mechanism, feedback exposure and question-presence checks.
They do not turn a provider label or a model-generated question into a measure of
independent observation or semantic accuracy.

## Routing, budget and recovery

An explicit **Interpreter model** is saved with the interpretation. Analysis,
clarifications and compilation use that exact applicator, including its model,
machine and effort. It becomes the default for the compiled the host executor run too.
If unavailable or no longer allowed, it fails visibly; it never falls back to a
model from the global route. Model-free recipes still make no model call.
Generated programs that override this choice with another applicator are refused;
clear the choice and translate again when the program needs its own routing.
This control does not rewrite user-authored programs in the Write editor.

Changing the selection is an operator revision. It preserves original text and
answers, invalidates the previous translation, and does not refund spent calls.
Clearing it restores routing policy. The catalogue is metadata: selecting a model
does not load it. A cloud selection cannot override confidential/local-only or
current host-executor policy. Explicitly choosing a local model on `@host` uses
that machine through the existing admitted provider; automatic routes retain
their existing placement policy.

All analysis, compilation, failed calls and fallback attempts share one durable
model-call budget. An additional dispatch for the same content revision and phase
also consumes the shared **retry/fallback allowance**. This is deliberately broader
than just corrections prompted by an error. A new operator clarification permits a
new primary attempt but does not reset either session total. Execution has its own
The host executor budget, shown separately.

The interpreter validates a candidate's whole proposal before accepting it, then
may try another permitted candidate within the remaining allowances. Later
candidates receive the check failure; this feedback exposure is recorded and is
not called independent observation. Compilation prefers the model that produced
the accepted interpretation when it is still allowed and available.
When **Ask for specifics** is selected, a goal-only reply is rejected within that
same budget and translation waits for the clarification. This check establishes
that a question is present, not that it asks the most useful distinction or
captures every ambiguity. It never invents an operator answer to make the request
appear complete.
The model receives nested record schemas for questions, options, requirements
and source references, including through local constrained decoding. Existing
items and operator decisions are retained by code; a model proposes only additions.
A failed requested refinement keeps the old read-back visible but blocks a new
translation or handoff. Retry it, or choose readback-only analysis and obtain a
successful result; changing the checkbox alone does not clear that failure.
The retained read-back may contain up to 100,000 characters for compilation; an
oversized record is refused before a model call, never silently shortened. The
ordinary host-executor request endpoint retains its separate 6,000-character limit.

Confidential input retains its local-only restriction through planning and native
execution. A current settings change can lower a session's permissions or limits,
but cannot raise its creation policy. Model calls use the existing admitted
applicators and worker node placement. The interface never directly loads a local model
on the web host.

Records are private under `automation_data/symblic/intents/`. Atomic replacement,
file and directory fsync, process locks, optimistic revisions and stable request
identities cover reconnects and concurrent tabs. An uncertain model call remains
charged. A damaged record is not replaced by an empty history or a free budget.

A run handoff writes its intent before calling the host executor. If the reply is lost,
the interpreter can recover the uniquely matching existing native run using the
handoff marker and exact source/input/policy checks. It never starts another run
just because an outcome is missing. Unmatched or ambiguous outcomes remain
uncertain for reconciliation; this is not an exactly-once external-effect claim.

## Research basis and present limits

This interface applies established controlled-language and interactive parsing
ideas. ACE's documentation explains why an accepted sentence can still need a
read-back and reformulation. [ACE interpretation guidance](https://attempto.ifi.uzh.ch/site/docs/ace_troubleshooting.html).
Clarification has task-dependent utility rather than a universal benefit.
[Zhang and Choi, 2025](https://aclanthology.org/2025.findings-naacl.306/).
Interactive semantic parsing for structured recipes also predates this system.
[Yao et al., 2019](https://arxiv.org/abs/1808.06740).

The multi-frame design rationale ([EVIDENCE.md](EVIDENCE.md)) motivates complementary checks: operator answers,
source comparison, formal validation and counterexamples access different parts
of a task. Different provider or role names alone do not establish independence.

The energy-method discussion led to the separate
[exact finite quadratic adapter](VARIATIONAL.md). Its positive-definite witness
proves a property of a supplied finite quadratic. Decreasing model disagreement
does not have that guarantee: readers can unanimously give the same wrong answer.
The interpreter instead checks mechanical preservation of source snapshots and
requirements and keeps the remaining semantic judgment visible.

The current tests use fake models, isolated stores and native execution adapters
with fake launchers. They establish implementation and recovery behavior, not a
measured improvement in general language understanding or small-model accuracy.
Publication-level claims require held-out intended outcomes, matched total
budgets, coverage/refusal, erroneous acceptance, question counts, latency and
cost, including failures in the denominator.

The saved Interpreter view now distinguishes the static predicate map from
observed execution checks (not included in this repository). Retained native checks are
joined only to the exact linked source, inputs, intent revision and execution
pins. Missing, stale, provisional or ambiguous evidence remains unassessed;
passing a predicate does not establish intended meaning or operator acceptance.

## Developer entry points

- Pure contract: `symblic/intent/records.py`.
- Private durable store: `symblic/intent/store.py`.
- API and bounded worker: `integration/host/symblic_intent_api.py`, under the existing
  `/api/automation/symblic/intent/` operator prefix with the host's operator identity check.
- GET: `list`, `view?id=...`. POST: `create`, `revise`, `analyse`, `compile`,
  `handoff`, `reconcile`, `stop`.
- Mutations carry `id` and `revision`. Analysis/compilation carry a stable
  `request_id` for that operation; a deliberate retry uses a new identity.
  Analysis also accepts `require_question` (strict boolean; absent means false
  for API compatibility). It is part of the operation identity.
  `validation.readiness.analysis_required` reports the durable refinement hold.
  `artifact_compatibility` is null without a translation; otherwise its status is
  `current`, `stale` or `unknown`. `differences` names changed intent, kernel,
  modules, catalogue, policy or sources. Metadata failures preserve the record
  and return `unknown`; they never trigger a model or capability call.
  A handoff for the current content prevents another compilation before a model
  call is reserved. Open or reconcile that run; revise the request or create a
  new interpretation to translate another program. An earlier revision's run
  link stays readable without blocking the revised translation.
  Pinning and execution use the same explicit Python/library registry; an
  unrelated `.sym` file is not silently added to an execution receipt.
  Creation accepts optional `by` (one exact typed-answer applicator; empty means
  routing policy). An operator `revise` event with `kind: applicator` and payload
  `{by: spec}` changes only this policy field. The server validates it without a
  provider probe; content/policy hashes bind jobs and checked artifacts. Handoff
  recovery additionally requires the same native default `options.by`. Legacy
  records without this optional field retain their original policy/hash shape.
  The server assigns event actors. A client cannot submit a system check receipt.
- UI: `web/studio/symblic-intent.js` and `symblic-intent.css`.
- Isolated checks: `tests/intent/test_symblic_intent.py`, `test_symblic_intent_api.py`,
  `test_symblic_intent_page.py` and the corresponding JavaScript journey fixture.

Python changes are restart-gated; a source-file change alone is not a live
deployment receipt.


### Run recovery identity

The installed Symblic runner writes a private `kernel.json` identity record before an
unpinned run's first statement. Pins or legacy trace/report identities identify other
folders. An incompatible or unknown identity with prior work refuses on Resume before
model calls or effects; the API leaves the recorded status intact. The host executor retains
any reduction in model authority even when it refuses. The record is an integrity
check within the private run folder, not authentication. This guard is included in the installed 5 October reform; see the
[5 October release evidence](evidence/2026-10-05-reform-install.json). Old records are preserved rather than migrated by rerun.
