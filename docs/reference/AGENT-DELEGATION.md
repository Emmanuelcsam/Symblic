# Reusable delegation contracts

An agent can choose a template, provide JSON parameters, inspect the generated
contract, and hand that contract to the existing Symblic runner. This removes
repeated program authoring for supported tasks. It does not guarantee that a
model will find an acceptable answer or that using the template will save tokens.

The implementation included in the installed 5 October reform uses `symblic/delegate/contracts.py` for compilation and
`symblic/delegate/run.py` for pinned native execution. Compiler and wrapper
checks exercise fake providers, exact arithmetic, rejection/repair, budgets and
canonical parent results. `tools/symblic delegate` exposes catalog/check/compile/run;
the operator API exposes catalog, compile, start and exact result transport under
`delegate/`. The runner records canonical output rows for that result
transport. See [AGENT-CARD](AGENT-CARD.md) for commands. This document does not
establish measured improvement on real models. Installation is recorded in the
[5 October release evidence](evidence/2026-10-05-reform-install.json).

For authored linear constraints, the optional native
[constructor handoff](CONSTRUCTOR-CLI.md#parent-to-child-native-handoff) adds
checked value construction and portable replay. It requires a separately
provisioned host runtime. Constructor policy belongs to native
`run` or the operator API; these delegated JSON schemas remain unchanged.
An agent that lost context reads a constructor run folder with the read-only
[recovery inspection](CONSTRUCTOR-CLI.md#recovery-inspection-after-lost-context);
it grants no retry authority.

## Contract interface

`catalog()` returns the request JSON Schema, available template IDs, bounds, and
additional semantic validation rules. `compile_task(request)` either returns a
complete contract or raises `ContractError`, with `code`, `path`, and `message`.
`inspect_task(request)` provides the same result as JSON with an `ok` flag; a
refusal includes `errors` and no partial executable program.

For focused discovery, use `catalog("proof_step_obligation")`,
`tools/symblic delegate catalog --template proof_step_obligation --agent-json`, or
the existing operator-only API
`GET /api/automation/symblic/delegate/catalog?template=proof_step_obligation`.
The optional selector returns one unchanged request-schema branch, only the local
schema definitions that branch references, relevant validation/assurance notes,
JSON bounds and execution defaults. The incremental proof call-default override
remains explicit. `selected_template` identifies the scope of this response.
Compilation remains authoritative for semantic and resource checks that a JSON
Schema cannot express.

The no-argument catalog is unchanged, including all template IDs and schemas.
Selection is exact and case-sensitive: no trimming, coercion, aliases or fallback
to the full catalog. Python `None` is an invalid selector; omit the argument to
request all templates. The CLI accepts exactly one `--template`, only with
`catalog`. The API accepts one `template` query field, refuses blank, duplicate,
unknown or malformed selectors and other query fields, and caps the raw query at
1,024 characters. Normal URL percent encoding is decoded once using strict UTF-8.
Discovery creates no run or provider call. A smaller serialized discovery
response is not a measured reduction in provider tokens, cost or model errors.

A request has exactly `template` and `params`, plus these optional fields:

| Field | Range and default | Meaning |
| --- | --- | --- |
| `calls` | 1–6, default 3; incremental proof: 1–64, default 32; arithmetic accepts only 0 | Charged native applicator-dispatch cap; includes failed attempts and repairs |
| `context_budget` | 0–131072, default 24000 | Native prompt/context character budget; not a token count |
| `capsule` | `full` (default) or `compact` | Choose prompt annotation presentation; complete host provenance and acceptance checks are retained |
| `max_steps` | 1000–1000000, default 200000 | Native kernel evaluation budget |
| `expected_contract_id` | 64 lowercase hexadecimal characters | Refuse if compilation differs from this previously inspected contract |

Every caller string and value is a named input. Arbitrary source fragments are
not accepted as parameters. The compiler creates a verified-profile program with
`context=none`, explicit `from` dependencies, strict native coercion, bounded
retry attempts, one parallel worker, and disabled effects. A provider selection
belongs to the host runner; it cannot be hidden inside the JSON task.

The result includes `source`, `inputs`, `options`, `output_binding`,
`output_encoding`, `output_schema`, `assurance`, `check`, and a full SHA-256
`contract_id`. That ID binds the compiled source, exact JSON inputs, limits,
per-template version, and declared assurance. The five original templates retain
version 5, `proof_step` uses 6, `proof_step_obligation` uses 7, and
`proof_step_focus` uses 8; the catalog
revision is separate. `source_sha256` and `inputs_sha256`
also expose the two component identities. Returned objects are detached copies.

Set `"capsule": "compact"` on the task envelope to omit three exact digest fields
from displayed host provenance annotations. The choice is bound into the contract,
generated source, execution options and route declaration; compiled-source export
retains it. Required values, status, origin and complete provenance records remain.
The default `full` form is unchanged. See [COMPACT-CAPSULES](COMPACT-CAPSULES.md)
for accounting boundaries and the separate offline token measurements.
These hashes bind content; they do not authenticate the caller, establish truth,
or replace the host's execution-implementation pins.

`context.input_names` lists task inputs. `context.ask_dependencies` lists required
binding names for every potential ask, recursively including conditional branches;
`ask_dependencies_scope` is `all_static_branches`. This is not a dispatch count:
an incremental proof stops at its first completed branch. A one-shot finite proof
uses the derived `expanded` value; an incremental proof uses its numbered frontier
and generic `proof_rules`. The compiler does not describe each raw premise or
domain as a separate prompt row. The native context manifest records
the packet that was actually sent and must refuse when required data will not
fit. No parent conversation history is implicitly copied. A caller can still
explicitly supply large or sensitive data, and input text can still influence a
model's behavior.

There is no new runner, model service, store, scheduler, or cache. Hosts retain
the existing native result registry, execution pins, receipts, cancellation,
and recovery path. They must run the returned source with the returned inputs
and options. The base `contract_id` binds compiled template semantics. The
wrapper's separate `routing_id` binds that contract to its canonical routing
plan and complete execution options, including runtime pins. Preserve both IDs.
`expected_contract_id` checks only the base contract. Provider timeouts and wall-clock admission
are host policies; this helper does not claim an enforced wall-time limit.

## Preparing and accounting for a route

`prepare(request, by=None)` in `symblic.delegate.run` returns the full compiled
contract with pinned execution options, `routing` and `routing_id`, without
calling a provider. The template-only CLI `check` and API `delegate/compile`
do not prepare a route. Omitted `by` selects the installed local 1B → Granite 2B
→ Qwen 4B ladder for model tasks; arithmetic has no model route. A string selects
one applicator with template retries. An API/Python list of 1–12 distinct
strings selects exactly that ordered route, even for a singleton list; the CLI
uses repeated `--by` flags for a multi-applicator list. Cloud engines require an
explicit caller choice. See [LOCAL-ROUTING](LOCAL-ROUTING.md).

The call ceiling counts native applicator dispatches. Confirmed pre-dispatch
refusals are refunded; returned failures and uncertain dispatches are charged.
A missing-model failure marked fatal is currently charged. Cached replies do
not dispatch again. An explicit single council remains supported, but its nested
provider-call ceiling is not established by this wrapper.

The route receipt distinguishes the declared policy, completed-rung summaries,
selected applicators, durable budget ledger and current-invocation calls. Rung
sample counts can include cached replies, and an interrupted rung may have no
summary. The compact API result explicitly omits the detailed native trace.
Use underlying private call records for raw provider usage; unavailable token
or cost fields remain unknown. Applicator labels do not authenticate a model
family or prove independence.

## Typed transformation

```json
{
  "template": "typed_transform",
  "calls": 2,
  "params": {
    "instruction": "Return the two amounts as integers.",
    "data": "first 1, second 2",
    "output_schema": {
      "type": "array",
      "items": {"type": "integer"},
      "minItems": 2,
      "maxItems": 2
    },
    "checks": [{"op": "sum_equals", "path": [], "expected": 3}]
  }
}
```

The model constructs `answer`; native type checking and the encoded sum check
accept or reject it. A wrong sum triggers a bounded retry. The check does not
establish that the answer faithfully extracted the two amounts: `[0, 3]` also
passes these declared constraints. Stronger requirements need stronger checks
or a source-witness contract. A checked sum of model-proposed inputs establishes
the sum conditional on those inputs, not their empirical correctness.

The executable [expense handoff](EXPENSE-HANDOFF.md) composes existing source-item,
field and complete-catalog contracts in a native project. It demonstrates the
stronger extraction checks and exact arithmetic without adding a domain solver
or hiding category and date assumptions in a validator.

The supported output schema is deliberately explicit:

- `integer`, optionally with both `minimum` and `maximum`;
- `string` or `boolean`;
- `array` with `items` and both `minItems` and `maxItems` (at most 128);
- `object` with 1–16 ASCII-identifier properties, every property required
  exactly once, and `additionalProperties: false`.

Schemas can nest at most eight levels. Unsupported JSON Schema keywords refuse
rather than silently weakening the contract. Bounds must be ordered. Integer
schema bounds have magnitude at most `10^100`.

There can be at most sixteen checks. A `path` selects the whole answer (`[]`) or
declared nested object fields (`["invoice", "amounts"]`). `equals` compares that
value to an exact, type-matching `expected` value. `sum_equals` requires an integer
array and an integer expected sum. Array indexing and arbitrary expression
snippets are outside this template's check language; the underlying Symblic
language remains available for more extensive programs.

The requested model JSON schema is distinguished from the accepted native
value. Native strict coercion rejects undeclared field deletion, fuzzy field
matching, and scalar-to-text conversions. It still accepts exact numeric strings
as numeric wire values and records canonicalization. A result of `["1", "2"]`
can therefore become native integer values `[1, 2]`; raw reply identity is not
claimed. Host receipts retain that distinction.

With no checks, acceptance establishes only the declared type. An internal
anchoring equality enables the native bounded-retry path and adds no semantic
assurance. The compiled `assurance` explicitly lists arbitrary instruction
fidelity, source entailment, factual truth, and enumeration completeness as
unassessed. This template is not an implicit factual extraction verifier.

## Micro choices and exact source witnesses

For `enum_classification`, provide `{instruction, data, categories}`. `categories`
maps 1–32 ASCII identifier keys to nonempty descriptions. The model receives those
descriptions and returns one key under an enum response schema. Acceptance checks
membership only. Category completeness, classification correctness and factual
truth remain unassessed.

For `witnessed_line`, provide `{instruction, text, source_id}` and optionally a
positive integer `revision` (default 1). The source must have 1–64 nonempty lines.
The compiler prepares choices with line numbers and exact quotations. The model
returns a bounded integer; the host materializes the chosen source span and checks
its source identity, revision, code-point offsets and exact quotation. It preserves
Unicode normalization, whitespace and line terminators from the caller's source.
No output quotation is generated by the model. Relevance, source truth, semantic
entailment and completeness are separate properties.

```json
{"template":"witnessed_line","calls":2,"params":{"instruction":"Select the delivery date line.","source_id":"order-7","text":"Order: 7\nDelivery: Monday\n"}}
```

Both templates use the ordinary 1–6 total call cap and fresh context. Small output
domains reduce construction work, but a valid choice can still be the wrong
choice. Evaluation must score task correctness as well as schema compliance.

Ordinary model asks now bound optional runtime enumeration and empty-answer probes to 50,000 admitted
kernel steps or one quarter of the remaining run budget, whichever is smaller, when `solve` is plainly
off. Returned answers still require their normal checks. Use `determine=false` for a deliberate
construction-only handoff, or explicit `solve=true`/`solve=auto` for the existing full finite-solving
path. Inspect `report.evidence.determinations` for partial-scan counts; an unfinished scan cannot
establish uniqueness or contradiction. See [the determination contract](SPEC.md#5-checks-and-retries).

## Checked proof construction

For parent-controlled statement handoffs, [`proof_step`](PROOF-STEP-DELEGATION.md) accepts
`params: {session, commands, require_complete?}`. It preserves the caller's exact ordered commands and
uses a bounded integer response, with `determine=false` to prevent runtime speculation before a model
proposal. Every returned selection is checked against the original session; a closing certificate is
rechecked. The [parent example](../../examples/proof_step_handoff.py) verifies the exact contract and typed
receipt before passing the next state to another fresh child. A valid partial inference is not a proof
of completion or relevance. This ordinal interface has no measured model-quality result yet.

[`proof_step_obligation`](PROOF-OBLIGATION-DELEGATION.md) adds a caller-defined
intermediate milestone: `params: {session, commands, obligation: {formula,
open_assumptions?}, require_complete?}`. Acceptance requires the exact parsed
formula and free-assumption set; the latter defaults to empty. The original goal
and prefix stay fixed. It checks only selected commands and provides a separate
`obligation_satisfied` flag, plus a [parent recheck helper](../../examples/proof_step_obligation_handoff.py).
Existing `proof_step/6` contracts remain unchanged; the new template has identity
`symblic.delegate/proof_step_obligation/7` and no measured model-quality result yet.

[`proof_step_focus`](PROOF-FOCUS-DELEGATION.md) uses the same request fields and
exact obligation checks, but projects the model's frontier to all exact menu
references, their complete free-assumption sets, and the required assumption
definitions. It preserves every menu option and validates the full original
prefix before dispatch. The original session remains authoritative for checking
the selected inference and the parent's adoption of the full returned state.
Projection version, view and manifest hashes are part of the handoff. Use
`symblic.delegate/proof_step_focus/8` when the caller owns a fixed menu and wants
smaller fresh contexts. Existing `/5`, `/6`, and `/7` compiled contracts remain
exact. This changes compiler source pins and route identities; existing saved
execution pins cannot silently claim the new compiler.

```json
{
  "template": "proof",
  "calls": 2,
  "params": {
    "premises": "human: \"Socrates is human\"\nrule: \"Socrates is human\" implies \"Socrates is mortal\"",
    "goal": "\"Socrates is mortal\"",
    "certificate_format": "steps"
  }
}
```

This reuses `symblic.adapters.logic.compile_task`, its controlled human syntax, its
generic proof instructions, and the existing certificate checkers. The model
constructs a certificate. It cannot replace the caller's authoritative premises
or goal. `certificate_format` accepts `terms`, `steps` or `incremental` (default:
`terms`); the optional `domains`
field uses the existing finite-domain logic frontend. The inspected
`formalization` exposes the actual parsed scope.

The result binding is `verification`. Acceptance means that the certificate
derives the exact goal under the declared premises and, when present, finite
domains. It does not check premise truth or consistency, prove that prose was
formalized as its author intended, or guarantee that a derivation will be found.
See [Proof terms](PROOF-TERMS.md) and [Finite logic](FINITE-LOGIC.md).

For one inference per fresh task card, change the proof parameters to:

```json
{
  "template": "proof",
  "calls": 32,
  "params": {
    "premises": "a: \"A\"\nrule: \"A\" implies \"B\"",
    "goal": "\"B\"",
    "certificate_format": "incremental",
    "step_limit": 16
  }
}
```

`params.step_limit` is optional, defaults to 16, and must be an integer from 1 to
32. It is accepted only for `incremental` and counts accepted proof inferences;
it is separate from the outer `max_steps` kernel-work budget. Each model answer
contains exactly `{rule, args, formula}`. The host assigns line IDs, rechecks the
prefix, and supplies explicit premises, goal, accepted lines, free assumptions
and remaining proof steps to the next call. Rejected candidates do not enter
that frontier. With an explicit single applicator, each inference permits up to
two repairs within the total call cap. With the default or an explicit list route,
the wrapper opts into shared zero repairs: a checked failure advances to the
next rung. Each inference starts at the first rung and shares the same total
ceiling with every other inference. Repair feedback names the failed rule
requirement when a repair is permitted. There is no hidden
parent conversation or precomputed target proof.

The first closed derivation stops further calls. The full certificate then passes
`proof_steps_check`, or `finite_steps_check` against the original finite domains,
before the `verification` output is bound. A step/call/context limit or repeated
rejection yields no accepted task output; it does not establish the goal's
negation. [Incremental proofs](INCREMENTAL-PROOFS.md) defines the helper's trust
boundary. Fake-constructor tests exercise this path; they establish no real-model
success rate or efficiency improvement.

## Exact arithmetic convenience

```json
{
  "template": "exact_arithmetic",
  "params": {
    "operation": "add",
    "left": {"numerator": 1, "denominator": 3},
    "right": {"numerator": 1, "denominator": 6}
  }
}
```

`add`, `subtract`, `multiply`, and `divide` use the existing rational kernel and
make no model call. Numerators and denominators are caller-provided integers of
magnitude at most `10^100`; denominators must be positive. Division by zero
refuses during compilation. The output binding is `answer`.

This is a convenient reusable kernel program, not a claim that arithmetic alone
fulfills Symblic's model-backed programming goal. A result is exact for the
supplied operands. Source association, operand truth, units, and currency
compatibility require separate contracts.

## Machine output and handoff

Read the declared output binding only after the native run's status is `done`.
Failed, stopped, or incomplete runs do not have an accepted task output, even if
an intermediate binding happens to exist. Keep the native run ID and receipts
alongside the delegation contract ID and routing ID.

Serialize the kernel value with `symblic.canon`. The `output_encoding` names the
current native canonical format version dynamically. For the arithmetic example,
the exact output is `{"#q":"1/2"}`. An integer is a JSON integer. This encoding
also distinguishes native sets and escaped record keys where relevant. Do not
reparse the human display string or substitute a rounded decimal report value.

The operator-only API prefix is `/api/automation/symblic/`:

| Request | Result |
| --- | --- |
| `GET delegate/catalog` | Detached template schemas and bounds |
| `POST delegate/compile` with the task object | Checked contract or visible refusal; no model call |
| `POST delegate/run` with `{"task": task, "by": "ollama:granite3.3:2b"}` | Native run ID, contract ID, routing ID and plan; the host pins source, inputs and runtime |
| `GET delegate/result?id=RUN_ID` | Recorded status, `accepted`, exact canonical `result`, encoding, contract/routing IDs, call accounting, error and evidence |

Only a completed, consistent delegation record returns `accepted=true`. The
endpoint checks the recorded contract/source/inputs/options and routing declaration, pinned kernel ID,
declared output binding, canonical format, output location and hashes. A damaged
or incompatible record produces a visible error rather than a reconstructed
display value. Old workers without a canonical output row require a compatible
rerun. Unfinished, stopped or failed runs return `accepted=false` and `result=null`.
The original request is retained in the private run metadata and omitted from
the compact API result. These checks provide local record consistency, not
authentication against an actor able to rewrite all records.

The CLI `run` command sends progress to stderr and emits one final JSON document
on stdout. A nonempty `--dir` refuses before dispatch; do not use a second run as
an implicit resume. `SIGINT`/`SIGTERM` set the native stop event, and the wrapper
cancels its owned applicator calls in cleanup, including exception paths, then
restores prior signal handlers. A failed or stopped result exits nonzero and
contains no accepted value. API resume and the native recorded worker verify the
delegation declaration before dispatch. The generic CLI `replay` verifies any
saved delegation declaration before applying its no-model overrides or opening
the native runner. It returns a native report, not a reconstructed delegation
receipt. CLI callers retain the original JSON receipt alongside the replay
report. For API-managed runs, the declaration-verifying result endpoint returns
the compact accepted handoff. An uncertain external action must not be
blindly redispatched.

```python
import symblic as S
import symblic.delegate.contracts as D

request = {
    "template": "exact_arithmetic",
    "params": {
        "operation": "add",
        "left": {"numerator": 1, "denominator": 3},
        "right": {"numerator": 1, "denominator": 6},
    },
}
contract = D.compile_task(request)
assert contract["check"]["ok"]
assert contract["options"]["max_calls"] == 0
assert contract["output_encoding"] == f"symblic.canon/{S.CANON_VERSION}"
assert D.compile_task({**request, "expected_contract_id": contract["contract_id"]})["contract_id"] == contract["contract_id"]
# The host now hands source, inputs, and options to its existing native run path.
```

Request JSON is bounded to 512 KiB, depth 24, and 20000 visited values; individual
strings are limited to 131072 characters. Cycles, custom Python objects,
nonfinite numbers, invalid Unicode encodings, unknown fields, and mismatched
contract IDs refuse before dispatch. Repeated aliased objects are charged each
time rather than bypassing bounds through shared references.

The focused tests cover source-injection attempts, exact contract identity,
detached records, schema and constraint refusals, wrong answers followed by a
valid repair, exhaustion, required-context overflow before a provider call,
strict-profile normalization boundaries, exact arithmetic without a provider,
and conditional propositional/finite proof construction. They establish these
tested operational behaviors, not formal soundness of the entire runtime,
universal model reliability, or a token-economics result. Evaluate economics
with matched tasks and include authoring, schema, retry, validation, and cache
costs before claiming a saving.

## Target-first numbered proof cards

The additive `proof_step_card/9` template takes the same caller session, command
menu, exact intermediate formula and free-assumption set as `proof_step_focus/8`.
It puts those values in one target-first card with numbered unchanged options
and generic guidance for all eleven inference rules. Full-session validation,
selected-inference checks and parent adoption remain authoritative. No choice
is evaluated or ranked by the presentation compiler. Read
[the contract and handoff example](PROOF-TASK-CARD.md). Earlier compiled template
contracts are unchanged; source-pinned execution and route identities reflect
the updated compiler. The new card has component evidence; the older `/7`
[feasibility pilot](evidence/2026-10-05-obligation-pilot.json) does not measure it.
