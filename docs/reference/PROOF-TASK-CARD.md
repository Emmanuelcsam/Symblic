# One exact proof obligation as a numbered task card

`proof_step_card/9` is an additive authoring template. It presents the
same caller obligation and full-session checks as
[`proof_step_focus/8`](PROOF-FOCUS-DELEGATION.md) in one required context value.
It has fake-provider component evidence, not a measured model-quality result.
The earlier `/6`, `/7` and `/8` templates remain available with unchanged
compiled contracts.

Start with [the request](../../examples/proof-step-card.task.json). These existing
source-only commands inspect the contract without dispatching a model:

```sh
python3 symblic/delegate/run.py catalog --template proof_step_card --agent-json
python3 symblic/delegate/run.py check examples/proof-step-card.task.json --agent-json
```

The [three-child handoff example](../../examples/proof_step_card_handoff.py) runs with
fake applicators only:

```sh
python3 examples/proof_step_card_handoff.py
```

For a real authorized child, pass the caller's admitted applicators and a new
private record directory to the existing `symblic.delegate.run.run_task`.
Keep the original request in the parent, set `expected_contract_id` after
reviewing `compile_task`, and adopt output only through
`checked_child_state(original_request, child_result)`. The helper recompiles the
parent request and rechecks the selected inference against the full original
session. Its type-sensitive canonical comparison rejects altered receipts,
wrong contracts and Boolean-for-integer substitutions. A hash binds these
values; it does not authenticate a remote agent.

## Caller input and visible card

Use the same `params` as `/8`: original `session`, exact ordered `commands`,
`obligation` with a controlled `formula` and optional exact `open_assumptions`,
and optional `require_complete`. The default assumption set is empty. The
caller cannot upload a replacement card or an expected choice.

The compiler creates an ordered list of sections so the native renderer's
record-key sorting cannot move the target behind the context:

1. **TARGET:** exact controlled formula, exact open-assumption IDs and whether
   the inference must close the original goal.
2. **OPTIONS:** every original command, in its original position, with an
   explicit one-based number. No option receives a correctness label or score.
3. **CHECKED LINES and NAMED PREMISES:** precisely the `/8` projection, including
   all named menu references, complete free-ID sets and required assumption
   definitions. Unreferenced derivation history stays in the full checker input.
4. **ORIGINAL SESSION:** original goal, next host line ID, completion flag and
   remaining step count.
5. **READING RULES and RULE GUIDE:** generic guidance for all eleven rules,
   including exact formula matching, implication argument order and disjunction
   branch scope. This guide is fixed, independent of which choices would pass.
6. **CONTEXT SCOPE and RESPONSE:** visible omission counts, conditional scope
   and the native ordinal answer format.

The model still constructs the decision. A valid inference with a different
formula does not satisfy the obligation. An `assume` command introduces its
new free-assumption ID and therefore cannot satisfy an empty-scope obligation.
The command table may include invalid inferences; only the selected command is
checked for inference validity after the model returns its number.

All command and proposition text remains JSON-quoted caller data. This prevents
source interpolation and preserves exact text/control characters; it is not a
prompt-injection immunity claim. The original full session, command table,
obligation, rules and projection remain in the compiled inputs. The input card
and handoff bind its version and exact hash. The full projection manifest
retains the identities and hashes omitted from the shorter visible scope note.

## Runtime behavior and limits

The source uses a verified profile, strict coercion, `context=none` and
`from task_card`. Both `determine=false` and `solve=false` remain explicit. The
existing native runner performs full-prefix validation, selected-inference
checking, exact formula/scope checks and bounded retries. It independently
checks a completed certificate. No new provider, scheduler, solver, inference
search or menu filter is introduced.

The schema remains a native integer answer inside the required JSON response
object. The inherited verified wire normalization also accepts an exact numeric
string such as `"3"` as ordinal 3 and records that normalization; Boolean `true`
is not ordinal 1. Inspect `determinism_summary` and the declared assurance separately.
Acceptance proves the encoded inference and caller obligation under the given
premises; it does not establish premise truth, consistency, model independence
or arbitrary prose fidelity. Original-goal completion is separate unless
`require_complete` is true.

Defaults remain three calls, 24,000 context characters and 200,000 kernel steps;
1–6 calls and 1–32 exact command entries remain the bounded interface. The
512 KiB/depth-24/20,000-value delegation bounds and native proof bounds apply.
Every card section is required. Full or compact capsule presentation is an
explicit caller option; full remains default. The verified native budget
counts the system, complete prompt and exact JSON schema, including repairs.
Overflow refuses before dispatch rather than silently dropping a reference.
The card adds a presentation value and may itself exceed a compiler or context
limit; callers can continue using the unchanged earlier templates.

Runtime records retain the existing source, inputs, exact provider requests,
all attempts, budgets and canonical result. Reusing a nonempty standalone
child directory refuses; use the existing explicit replay workflow instead of
silently issuing another call. Parent adoption always rechecks the full state,
even though the model sees only the focused card.

## Why try this presentation

A preceding developmental pilot delivered six schema-conformant ordinal
replies; its other three dispatches timed out. The delivered replies selected
a valid but wrong-target premise or repeated an invalid implication argument
order. The prompts already contained the target and relevant correction. Those
observations do not establish why the choices occurred, or that this card will
improve them. The target-first ordering, explicit numbering and static rule
guide are hypotheses for a future separately frozen experiment.

The component checks preserve 53 complete prior contracts, exercise
all eleven rules, compare actual preview and fake dispatch surfaces, and attack
scope, menu, source/receipt tampering, Unicode text, budgets and durable
handoff behavior. Character counts describe the finite captured requests;
they are not token, speed, cost or accuracy claims.
