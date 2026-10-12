# Build one checked step at a time

Symblic keeps the objective and the accepted work. The model receives one small construction task, the exact functions it may use, and a finite set of possible expressions. Local checks decide whether its choice fits. A rejected choice can be corrected within a fixed budget; an exhausted budget stops construction visibly unless the explicit finite completion option is enabled. Later steps never consume a rejected piece.

For example, one English instruction is **“Subtract used from start to return the remaining item count.”** Its function is `remaining_items(start: Int, used: Int) -> Int`. The visible menu can contain `start + used`, `used - start`, `start - used` and `start * start`. Checks such as `remaining_items(9, 4) = 5` and `remaining_items(4, 4) = 0` reject plausible mistakes. The worker returns the exact expression it chooses. Symblic checks that expression; it does not secretly choose the passing answer for the model. The completed record also retains its original 1-based choice index for assembly.

The English instruction describes the job. The signature, dependencies, choices and executable predicates make its fit conditions concrete. English alone cannot guarantee correctness. A weak model can still choose incorrectly, and inadequate checks can still admit a wrong program.

Native enum answers carry the exact expressions. A single expression, or choices that native enum normalization would consider alike, use a bounded text answer with an exact membership check before the authored checks. All original expressions stay in order; an unlisted answer cannot adopt the fallback function body.

## Use the page

1. Open Symblic → **Workcards** → **Build one step at a time**.
2. Choose **Load parcel program example**. Review the English steps; expand **Edit instructions, choices and checks** to edit the full contract.
3. Select an installed worker model and its node. For bounded completion after a rejected proposal, enable **Let the engine try the finite menu after rejected model attempts** and set corrections to **0**: one model proposal per step, then explicit finite checking if needed. **Prepare checked steps** validates and pins the construction without calling a model.
4. Choose **Open construction in Write**, then run. The ordinary Runs page records every attempt and check.
5. Copy the completed construction's run ID. Return to Workcards, enter it under **Get a completed program**, and choose **Get checked program**.
6. Open the assembled program in Write or download its `.sym` file. Supply its declared inputs before running it. This execution has a zero-model-call budget.

Recovery works after a page reload. It reads the saved run, checks its exact source, inputs, runtime pins, choices and passing native receipts, then assembles the file. A browser cannot claim that a selection passed. Changed or incomplete records refuse recovery. This is coherence checking of local records, not cryptographic authentication against somebody who can rewrite the entire private run store.

## When the model repeats a mistake

Finite completion is an explicit option, off by default. After a model answer fails the checks and exhausts its correction budget, the engine tries the caller-authored expressions in their declared order under the same native checks. It records every trial, adopts the first passing expression and marks that step as engine-selected. It does not claim that the model supplied the replacement or that the passing choice is unique.

All local checks run again for a replacement. A final combined check can still fail after local choices pass; this mode stops and does not backtrack through earlier accepted steps. The parcel example includes a tax case that distinguishes rounding the final fraction from rounding before multiplication. Candidate type or domain errors can reject a choice. An unavailable provider, malformed reply that never binds an answer, exhausted resources, an unavailable checker or a stop still ends the run visibly. If no candidate passes, or the final combined checks fail, there is no completed artifact. This bounds a finite construction problem; it does not establish the adequacy of the menus or tests to every possible objective.

The [measured Llama 1B results](STEPS-EVIDENCE.md) include a [completed program](../../examples/steps-parcel-built.sym) and a saved zero-model-call dashboard run.

## A program with thirteen connected pieces

The [parcel request](../../examples/steps-parcel.json) constructs area, volume, dimensional weight, chargeable weight, rounded billing units, base price, an oversize decision, its fee, subtotal, a bounded promotion, net price, rounded tax and final price. Each instruction builds a reusable function. Earlier accepted functions are available only when a step lists them in `uses`. The worker sees each declared dependency's signature, English instruction and selected expression. To expose a deeper dependency too, list that earlier function explicitly.

The caller supplies the final native program body, which loops over parcel records and produces all intermediate values and a total. Each model proposal selects one of the thirteen function expressions; optional finite completion can select a replacement after failed checks. The caller supplies the surrounding loop, menus and tests. The [sample inputs](../../examples/steps-parcel-inputs.json) contain three parcels, including oversize and promotion-cap cases. In Write, paste the value of `parcels` into that declared input. Replace it with new records to run the same functions again without a model.

The sample arithmetic uses integer dimensions, weights and price units. Use consistent units and positive divisors, increments and tax denominators. It is a programming example, not a carrier's tariff or a production billing policy.

## Write a precise construction line

Each step declares:

- `instruction`: one operation, named inputs, exact direction and any boundary rule. Prefer “round upward to a whole billing unit” to “calculate a fair charge.”
- `parameters` and `returns`: closed native types.
- `uses`: only earlier functions needed for this step. No entire transcript or unrelated future work is sent.
- `choices`: distinct, exact native expressions. Every supplied choice remains visible, including wrong ones.
- `checks`: executable predicates that call this function. Include unequal inputs, zero or boundary cases, and cases that distinguish the plausible mistakes.

`final_checks` test the combined functions. The optional `program` is the pure native body that uses them. Keep an independent set of cases outside the model context to evaluate the completed artifact. Passing the construction checks establishes those checks, not the completeness of the objective.

Write explicit input domains and boundary behavior. Native checks can reject an erroneous selected expression and retry within the call budget; exhaustion stops construction visibly. Split an instruction further when it needs several independent decisions. Symblic bounds the work and catches encoded failures; it cannot make every model incapable of error.

Each step has one correction budget shared by all its local checks, evaluated in authored order. Every replacement choice starts those checks again from the first one. Ordinary expression errors, including division by zero, indexing errors or a wrong return type, reject that choice and can be corrected. Resource exhaustion or an unavailable checker does not establish that the choice is wrong.

## Terminal use

```sh
tools/symblic-workcard compile --kind steps \
  --request examples/steps-parcel.json \
  --by ollama:llama3.2:1b@node-f

tools/symblic-workcard run --kind steps \
  --request examples/steps-parcel.json \
  --by ollama:llama3.2:1b@node-f \
  --retries 0 --context-budget 12000 --finite-fallback \
  --dir /private/new-parcel-construction

tools/symblic-workcard result --dir /private/new-parcel-construction
```

Use an available admitted node and a new private folder. A successful run writes `assembled.sym`; `result` reconstructs the artifact from the existing records without a model call. Reusing a nonempty run folder refuses rather than silently repeating work.

`--retries`, `--context-budget` and `--finite-fallback` also apply to steps `prepare` and `compile`. The `fill` command is for slots; step construction selects its expressions during `run`.

The operator-only API provides `POST /api/automation/symblic/workcards/steps/compile` with `request`, `by`, optional `retries`, `context_budget` and boolean `finite_fallback`; preparation returns the pinned native source, inputs and options. `POST /api/automation/symblic/workcards/steps/result` accepts only a saved native run `id`. The ordinary native run endpoint owns execution.

## Bounds and evidence

This first construction interface supports 1–64 steps, up to 16 choices, 12 parameters and dependencies, and 32 local checks per step. Each step allows 0–5 corrections. Model calls are bounded by `steps × (corrections + 1)`. Optional finite completion evaluates at most the authored menu size (up to 16 candidates) per failed step and adds no model calls. Native context budgets count characters, including request overhead; they are not token or RAM measurements. Oversized contexts refuse before dispatch. Effects, arbitrary code, external named types, dynamic evaluation and model calls inside choices are excluded.

The assembled file contains the selected functions, the authored assertions and the caller's program body. It has no model asks. Preparation checks grammar, scope and supported operations; it is not a complete static type check of expressions. For example, a final program that calls an integer function with text can prepare successfully and fail its type check when executed. The caller's program body is not executed during construction. Assembly is preparation; running the file on independent inputs supplies additional behavioral evidence. Model failures, unreachable steps, retries, context sizes and costs must remain visible when comparing this approach with a larger single prompt.

Recovery uses the current compiler and pinned runtime. A compiler or runtime upgrade can refuse recovery of an old construction. Keep the downloaded `.sym` file and its original private run records when upgrading.
