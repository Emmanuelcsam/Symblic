# Use Symblic from another agent

Agent integration card, 5 October 2026. Use the local executable and its
catalog to inspect the installed capabilities. Examples use admitted local
models; no cloud fallback is implicit in these commands.

1. Discover templates: `tools/symblic delegate catalog --agent-json`.
2. Put caller instructions, data, output schema and acceptance checks in a JSON
   task. Do not interpolate untrusted data into Symblic source.
3. Validate without a model: `tools/symblic delegate check task.json --agent-json`.
4. Run: `tools/symblic delegate run task.json --dir /tmp/new-task-record --agent-json`.
5. Consume `result` only when `accepted` is true. Retain `contract_id`,
   `routing_id`, exact canonical encoding, assurance, accounting and the private
   run record. A failed or exhausted attempt has no accepted result.

When the task template is already known, request just its discovery contract:
`tools/symblic delegate catalog --template proof_step_obligation --agent-json`.
This returns that template's schema, required schema definitions, assurance,
validation notes, JSON bounds and defaults. It does not execute a task. Names
are exact and case-sensitive; blank, unknown or repeated selectors refuse.
The full catalog command above is unchanged.

For one precisely defined proof step, use the [numbered task card](PROOF-TASK-CARD.md):
`tools/symblic delegate catalog --template proof_step_card --agent-json`.
The child sees the exact target first, then every numbered caller option and
its required checked context. The parent retains the full session and rechecks
the returned inference. Start with the [task JSON](../../examples/proof-step-card.task.json)
and [three-child handoff](../../examples/proof_step_card_handoff.py). The example uses
fake providers; use the normal admitted `delegate run` path for a real child.
The card changes presentation while preserving existing `/6`, `/7` and `/8`
contracts. The published [card pilot](PROOF-TASK-CARD.md) did not establish a
model-quality improvement; its smaller inputs did not produce completed goals.

With no `--by`, delegated model tasks use the declared local ladder: installed
1B, Granite 2B, then Qwen 4B tags. Each checked failure advances with zero shared
repairs, inside the task's total call ceiling. An explicit `--by` string uses
that applicator and its template retries; repeated `--by` flags request an
ordered route. A larger model does not strengthen the acceptance checks. Read
[local routing](LOCAL-ROUTING.md) for accounting and explicit cloud authority.

Read `determinism_summary` when present for the native execution classification,
then read the template's declared `assurance` for what acceptance actually checks.
The summary is not a replacement for source truth or task-specific validation.

For native source authoring, use `tools/symblic grammar catalog --agent-json` and
`tools/symblic grammar check program.sym --agent-json`. The
[authoring contract](AUTHORING-GRAMMAR.md) exports scoped EBNF and checks existing
syntax/reference rules only. Its optional caller-authored command menu can
retain an invalid inference; the ordinary proof checker still decides validity.

For authored linear constraints, the optional native
[constructor handoff](CONSTRUCTOR-CLI.md#parent-to-child-native-handoff) adds
checked value construction and portable replay. It requires a separately
provisioned host runtime. Constructor policy belongs to native
`run` or the operator API; these delegated JSON schemas remain unchanged.

## Copyable parent-to-child handoff

Run these commands from the checkout. The checked-in
[task](../../examples/agent-handoff.task.json) asks a child to select a delivery line
from two caller-supplied source lines. Inspection makes no model call; `run`
uses the admitted local route.

```sh
tools/symblic delegate check examples/agent-handoff.task.json --agent-json > handoff-contract.json
python3 - <<'PY'
import json
from pathlib import Path
request = json.loads(Path('examples/agent-handoff.task.json').read_text())
contract = json.loads(Path('handoff-contract.json').read_text())
assert contract['ok'], contract.get('errors')
request['expected_contract_id'] = contract['contract_id']
Path('handoff-task.json').write_text(json.dumps(request))
PY
record="$(mktemp -d /tmp/symblic-handoff.XXXXXX)"
tools/symblic delegate run handoff-task.json --dir "$record" --agent-json > handoff-result.json
```

The parent consumes machine output, not prose extracted from a log:

```python
import json
from pathlib import Path
contract = json.loads(Path('handoff-contract.json').read_text())
receipt = json.loads(Path('handoff-result.json').read_text())
assert receipt['accepted'], receipt.get('error')
assert receipt['contract_id'] == contract['contract_id']
assert receipt['routing']['allow_cloud'] is False
span = receipt['result']
assert span['source_id'] == 'order-7' and span['revision'] == 1
# Forward the whole span, including its source hash, offsets and exact quote.
# Keep receipt['routing_id'], output_encoding, assurance and private run records.
```

The checked result is an exact source association. A child can select the wrong
line and still return a valid span. Selection relevance and source truth remain
unassessed; the parent needs a separate check if its task requires those facts.
`expected_contract_id` pins the template contract, not a routing choice. The
separate `routing_id` binds the prepared route and execution pins. Hosts that
need to inspect that route before dispatch can call
`symblic.delegate.run.prepare(request, by=...)` without a provider call.

The template library includes typed transformation, checked proof construction,
one-step proof handoffs, enum classification, exact source-line selection, and exact rational arithmetic.
[AGENT-DELEGATION](AGENT-DELEGATION.md) specifies
their request fields and assurance scopes. The arithmetic template makes zero
model calls. The transformation template checks declared structure and predicates;
the proof template checks a constructed derivation under caller premises.

For a compound source-extraction project, use the executable
[expense handoff](EXPENSE-HANDOFF.md). Its parent-owned source, item catalog,
field contracts and policy stay separate from model proposals. The example shows
prepare/run/check commands, one-item fresh requests, exact rational totals and
offline artifact rechecking. It uses ordinary Symblic statements and existing
validators; category, day and catalog completeness remain explicit caller premises.

For a small model, first try a bounded choice task. `enum_classification` accepts
`params: {instruction, data, categories}` where categories maps 1–32 ASCII keys
to descriptions. `witnessed_line` accepts `params: {instruction, text, source_id}`
and optional `revision`; the model chooses one of at most 64 nonempty source
lines, and the host returns its exact checked span. These templates enforce
membership and source fidelity respectively; they do not establish classification
accuracy or selection relevance. Each uses a fresh context and a constrained
response schema. Measure correctness separately on operator-held examples.

To request one model-constructed inference per fresh context, use the proof
step handoff template [`proof_step`](PROOF-STEP-DELEGATION.md) when the parent owns a checked session
and an exact command menu. Each child selects one bounded ordinal; the native checker validates only
the selected inference. The parent rechecks the returned receipt before adopting its next state.
Set `require_complete=true` when this step must close the goal. A valid partial step alone does not
establish completion or useful progress. The [three-child example](../../examples/proof_step_handoff.py)
shows explicit state transfer, contract IDs and exact receipt checking with fake providers.

For an exact intermediate milestone, use
[`proof_step_obligation`](PROOF-OBLIGATION-DELEGATION.md) with the same session/menu
and `obligation: {formula: '"B"', open_assumptions: []}`. The selected line must
match both the parsed formula and exact free-assumption set. The empty default
prevents accepting a mere assumption as a closed derivation. The original goal
stays fixed; inspect `inference.complete` separately from `obligation_satisfied`.
Use its [parent recheck helper](../../examples/proof_step_obligation_handoff.py) before
adopting a child's state.

For a long checked prefix and a fixed next-step menu, use
[`proof_step_focus`](PROOF-FOCUS-DELEGATION.md) with those same obligation fields.
Each fresh child sees the exact menu references and complete free-assumption
sets. The full prefix remains in the checker and returned receipt. Discover
only this contract with
`tools/symblic delegate catalog --template proof_step_focus --agent-json`.
Use its [parent helper](../../examples/proof_step_focus_handoff.py) to recheck the full
result before handing the next step to another agent. The projection is specific
to the caller's menu; it does not construct that menu or choose a correct option.

For a child that constructs its own sequence of inferences, use the proof
template with `params.certificate_format="incremental"` and optional
`params.step_limit` (1–32 accepted steps, default 16). Its outer `calls` budget is
1–64, default 32, and includes rejected attempts and repairs. `terms` and `steps`
remain one-certificate formats with 1–6 calls, default 3 in delegation. The outer
`max_steps` is a separate kernel-work budget. An incomplete proof returns no
accepted result; failure to find a derivation does not prove the goal false.

Optionally add `params.inference_format="command"` for one explicit text command
per inference, such as `premise p` or `implies_elim s2 s1`. It translates to the
same checked candidate; JSON remains the default. See
[PROOF-COMMANDS](PROOF-COMMANDS.md) for exact syntax and a runnable task.

```json
{"template":"proof","calls":8,"params":{"premises":"a: \"A\"\nrule: \"A\" implies \"B\"","goal":"\"B\"","certificate_format":"incremental","step_limit":4}}
```

After inspection, include its exact `contract_id` as `expected_contract_id` in
the task to refuse a changed compilation. `context.ask_dependencies` includes
all potential branch asks; actual calls can be fewer when the proof finishes.

For code projects, use [task cards](TASK-CARDS.md). A parent hands a child a unit
contract and complete dependency slice. The host stores accepted artifacts and
checkpoints; each request starts fresh. Import/export preserves exact accepted
bytes, and dependency-aware reuse avoids regenerating unaffected branches.
Use [differential probes](DIFFERENTIAL-SPECS.md) to compare complete JavaScript
candidates against the same exposed checks and new inputs. The comparison returns
questions with no chosen expected answer; the operator supplies that answer before
adopting a new example. Textual equality, checked behavior and universal equivalence
are separate claims.

For arbitrary native programs, `tools/symblic check program.sym --agent-json` emits
structured errors, source locations, warnings and the plan. `preview --agent-json`
shows the next request without calling a model. `run --agent-json` and `delegate`
keep progress messages on stderr so stdout remains one JSON document.

For a native `run`, `--strict-model-pins` requires the runtime's validated model
identity policy. The operator API accepts `options: {"model_pins":"strict"}` when
`meta.features.strict_model_pins` is true. These entry points refuse an explicit
strict request if the loaded runtime lacks that capability; omitting it retains
observational reporting. The Write screen exposes the same opt-in under Run model
identity policy and retains the selection across reloads, source edits and loaded
programs until explicitly cleared. A saved
strict task stays blocked on an unsupported server until you explicitly clear it.
This checks retained host observations of model manifests, not loaded-weight
attestation. Replay retains its saved policy. Strict refuses an answer when its
identity is missing, changed or cannot be freshly checked; any dispatched call
still counts against the budget. Invalid policies refuse before run-directory
writes or provider construction. The native producer and entry points are
installed in the 5 October reform; inspect the capability before use on another host.
Version-2 [execution receipts](EXECUTION-PINS.md) additionally bind registered
loaded Python code to reviewed source. They are separate from model identity;
version-1 execution receipts need review and rebuilding.

Use `from` to name required values, `context=none` to exclude unrelated history,
and `ensure ... else retry` for a bounded repair window. Put real external actions
after acceptance through the existing authorized effect/delegation path. Native
effect ledgers preserve uncertain outcomes; retrying an unknown external effect
does not make it atomic or undone.

Exact rational results use Symblic's versioned canonical encoding, for example
`{"#q":"1/2"}`. A display string or ordinary floating-point JSON conversion is
not the exact result contract. Keep the declared encoding version with the value.

The operator API uses `/api/automation/symblic/`: `GET delegate/catalog`,
`POST delegate/compile` with the task, `POST delegate/run` with
`{"task": task, "by": "ollama:granite3.3:2b"}`, then
`GET delegate/result?id=RUN_ID`. Omit `by` for the default local ladder, or pass
an explicit list of distinct applicators for that exact route.
Read the latter's exact canonical `result` only when `accepted=true`; unfinished
runs return null and damaged/incompatible completed records return a visible
error. The endpoint checks the recorded contract, routing declaration and canonical output row; it
does not parse a display string or return the original private task request.

Use a new empty CLI record directory. `SIGINT` or `SIGTERM` requests native
cancellation and cleanup of that command's owned calls; a stopped/failed run
returns nonzero with no accepted output. A nonempty directory is refused,
not resumed. API resume verifies the delegation declaration before dispatch.
Native `replay` verifies a saved delegation declaration before applying its
no-model policy. It returns a native report, not this delegation receipt. CLI
callers retain the original JSON receipt alongside the replay report. For
API-managed runs, the declaration-verifying result endpoint returns the compact
accepted handoff.

Discover the catalog in the parent agent before building a batch. Keep discovery
output and full run records with that parent; send each child only its task and
complete selected dependencies. Validate and pin each compiled task after its
inputs or options change. Repeating the whole catalog or past conversation in
every model request adds cost without adding task evidence.

For reusable groups of agents, the [graph composition interface](GRAPH-COMPOSITION.md)
adds `tools/symblic graph catalog|example|compose`. Define typed public ports once
and instantiate the same checked fragment repeatedly. Expansion returns a flat
draft for the existing host's Check → Run workflow, with no implicit dispatch.
Keep the reusable source and authoring manifest with the parent; saved runs
retain their frozen flat graph. Each leaf keeps its checks, permissions and call limits.

Measure complete accepted-task cost: authoring, input/schema/tool tokens,
generated tokens, repairs, checker time and failures. Templates reduce repeated
syntax authoring; they do not prescribe a universal token savings percentage.

To try smaller prompt annotations, add `"capsule": "compact"` alongside
`template` and `params`. Check the task again and use its new contract ID.
[Compact capsules](COMPACT-CAPSULES.md) retain complete host provenance and the
same required values and checks. The default is `full`; compare total accepted-task
cost and correctness before choosing a presentation for repeated work.
