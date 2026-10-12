# A focused context for one caller-owned proof obligation

`symblic.delegate/proof_step_focus/8` is an opt-in template. It uses the same
exact intermediate obligation and native inference checks as
[`proof_step_obligation/7`](PROOF-OBLIGATION-DELEGATION.md), while showing the model
only the checked judgments referenced by its exact command menu and their free
assumption definitions. The full original session remains the checker's input.
Component checks use fake providers; this interface has no measured model-quality
result yet. Its deployment status is recorded in [the reform record](REFORM-3.md).

Start with [the runnable request](../../examples/proof-step-focus.task.json). Source-only
inspection and a fake three-child handoff use existing entry points:

```sh
python3 symblic/delegate/run.py check examples/proof-step-focus.task.json --agent-json
python3 examples/proof_step_focus_handoff.py
```

The first command compiles without dispatch. The second uses fake applicators
only. For an authorized real child, the host can pass its existing admitted
applicators to `symblic.delegate.run.run_task`. This template adds no provider,
scheduler, persistent store or solver.

## Caller contract and visible state

Use the same fields as `/7`, with `template: "proof_step_focus"`: an original
`session`, exact ordered `commands`, an `obligation` containing a controlled
`formula` and optional `open_assumptions`, and optional `require_complete`.
`open_assumptions` defaults to the exact empty set. The caller cannot supply or
override the projected frontier. Compilation refuses unknown fields.

Every menu command first passes the existing bounded syntax and reference
parser. Compilation does not check whether any menu inference succeeds, rank
options, remove invalid inferences, or construct a proof path. The model still
chooses a one-based integer from the unchanged ordered menu.

The compiler creates one required `frontier` context value containing:

- The original goal, next line ID, completion flag and remaining step count.
- Every line named by any command, with its exact formula, rule and complete
  free-assumption ID set, in session order.
- Each referenced line's free assumption definitions and the existing
  assumption definitions named by the obligation. The known next ID can appear
  in the obligation; no future assumption line is fabricated.
- Every named premise used by a `premise` command, with its exact formula.
- An explicit projection version, original session/menu hashes, omitted row
  counts and scope statement.

The exact commands, generic proof rules, obligation AST and reading, requested
assumption IDs and completion requirement are also required context. The
projection applies to a fixed menu; it does not claim to provide enough context
for unrestricted proof construction. A menu that references most of a prefix,
or judgments with many free assumptions, can require most of the full frontier.

| Command rule | Required visible judgments, in addition to global fields |
| --- | --- |
| `premise` | The exact named premise formula |
| `assume` | Formula in the command and the next line ID |
| `implies_intro` | Assumption and body lines, including the body's full free set |
| `implies_elim`, `and_intro` | Both argument lines and their full free sets |
| `and_left`, `and_right` | The argument judgment and its full free set |
| `or_left`, `or_right` | Argument judgment, free set and command-supplied formula |
| `or_elim` | Disjunction, both branch assumptions and both branch results, with every free set retained |
| `false_elim` | Argument judgment, its full free set and the target formula in the command |

These rules check formulas and dependency sets of already checked judgments;
they do not require each argument's derivation history in the model's view.
Discharge still depends on the full free sets, including cross-branch
dependencies. No transitive derivation-ancestor walk is substituted for those
sets. Projection version 1 refuses an unreviewed rule or changed argument arity.

## Full checks and parent adoption

The generated source validates the full original prefix before dispatch. It
then binds the compiler's projection as `frontier` and uses explicit `from`
dependencies with `context=none`. Raw session history is not selected for the
model request. Both `determine=false` and `solve=false` remain set.

After selection, the unchanged native command checker receives the **full**
original session. Acceptance still requires a valid inference, exact obligation
formula, exact free-assumption IDs, and original goal closure when requested.
A completed certificate is independently checked. The returned inference
receipt includes its full checked state; projection does not reduce host-side
checking, durable output, or parent verification work.

The contract pins the full session, unchanged menu, projection data and version,
manifest and hashes. `projection_manifest` records included and omitted row IDs,
content hashes and reasons. The returned `handoff` binds both view and manifest
hashes. These bind the supplied contract; they do not authenticate a caller,
establish premise truth, or attest model weights.

Use [the parent helper](../../examples/proof_step_focus_handoff.py) with the parent's
original request. It recompiles that request, checks the selected command under
the full original session, checks formula/scope/completion and compares the
entire canonical receipt with type-sensitive bounded JSON. It never adopts the
child's supplied state without rechecking. Bind `expected_contract_id` when
handing a reviewed request to a child.

## Bounds and evidence

Existing delegation limits remain: 512 KiB JSON, depth 24 and 20,000 visited
values; 1–32 exact command entries; 1–6 calls, with default 3; default 24,000
context characters and 200,000 kernel steps. Native proof/session limits still
apply. Required context that cannot fit refuses before dispatch. Missing
projection dependencies refuse instead of producing a partial silent view.
Full capsules remain default and compact capsules are opt-in.

In a synthetic 200-line valid prefix with two referenced lines, the default
24,000-character budget refused `/7` before dispatch in both capsule modes:
the required surfaces were 26,474 and 25,276 characters. Under that same default,
`/8` sent 7,706 and 6,508 characters respectively, accepted one fake selection,
and retained all 201 lines in its full checked output. Here the verified native
budget includes system text, the entire prompt and exact compact sorted JSON
schema in Unicode characters. This demonstrates a finite context-budget case,
not a performance comparison. Separate equal high-budget fixtures keep both
templates admitted when comparing their request sizes.

`projection_costs` counts exact compact-JSON characters and UTF-8 bytes of the
full and projected frontier values. It is not a tokenizer result, a measurement
of the complete provider request, or evidence of lower latency or higher
accuracy. Separate private fixtures measure actual native preview and fake
dispatch surfaces, including system, prompt and schema. They use synthetic
prefixes and make no real model calls. Effectiveness needs a separately frozen,
matched experiment.

The five `/5` templates, `proof_step/6` and `proof_step_obligation/7` remain
available. Frozen fixtures check their existing compiled contracts and request
schemas byte-for-byte as serialized JSON values. Updating this compiler still
changes execution source pins and wrapper routing identity, even when an older
template's base contract ID is unchanged.
