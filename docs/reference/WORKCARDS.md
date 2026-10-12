# Typed workcards and reviewer roles

Workcards narrow a model's task and make its acceptance rules explicit. They use the existing native parser, checker, interpreter and admitted model paths. They do not add a second language or model service.

## Build one checked step at a time

The Workcards page now also prepares a sequence of small function-building tasks. Each worker sees one English instruction, a finite menu of expressions and only its declared accepted dependencies. Native checks must pass before the next step can use that function. The finished pure program can run on fresh inputs with zero model calls. See [Writing precise steps](STEPS.md) for the page flow, parcel example, terminal commands and limits.

## Builder, critic and reviewer

A team request declares an answer type, executable predicates, one builder and one to three named reviewers. The builder proposes an answer. The kernel evaluates the predicates. Each reviewer sees that answer, the predicate result, the explicit inputs and preceding reviews; reviewers can veto it. Acceptance requires the predicates and every reviewer to agree. If rejected, the next builder round sees the previous candidate and its reviews. The first accepted round ends execution. The maximum is four rounds; calls are bounded by `rounds × (1 + reviewers)` and share the native run budget.

The [team example](../../examples/workcard-team.json) requests the positive square root of nine. Its generated program accepts `3`; a unanimous vote for `4` still fails the square check. Identical models in different roles are not independent evidence. A reviewer can incorrectly reject a valid answer, so adding reviewers can also reduce completion and increase cost.

```sh
tools/symblic-workcard compile --kind team --request examples/workcard-team.json
tools/symblic-workcard run --kind team --request examples/workcard-team.json --dir /private/new-team-run
```

Replace the example's model/node choices with installed, admitted applicators. Each role has one exact route; nested councils and weighted fan-out are excluded so calls remain countable. Compile makes no model calls and returns ordinary verified Symblic `source`, `inputs` and `options`, suitable for the existing native runner. Instructions are data, not interpolated source. Every supplied check must read `answer`, may also read explicit input names, and uses only allowed pure expression nodes and native builtins. Predicates cannot read builder or reviewer bindings. Write total predicates for the declared answer type: a runtime error inside a predicate stops the run and remains visible, rather than being converted into a vote. An accepted result establishes the encoded predicates and reviewer decisions, not the adequacy of those predicates to reality.

## A planner fills one visible hole at a time

A slot request contains a program template with visible `[[name]]` holes. Each hole declares `expression`, `identifier` or `type`, an instruction and exact caller-authored choices. The actual Symblic parser checks each choice and the template shape. It never evaluates choices to rank them or quietly remove wrong answers. The model gets one typed bounded one-based index question per hole, matching native list indices. Expression choices are inserted inside parentheses; replacement traverses only the original template. The `[[name]]` delimiter is reserved for holes; write nested lists with spaces, such as `[ [x] ]`. Its choice is validated by the native interpreter before another hole is asked. The complete filled program then passes the native parser and static checker.

```sh
tools/symblic-workcard catalog
tools/symblic-workcard prepare --request examples/workcard-slots.json
tools/symblic-workcard run --request examples/workcard-slots.json --by ollama:llama3.2:1b@node-a --dir /private/new-slot-run
```

The [slot example](../../examples/workcard-slots.json) retains both `x+x` and `x*x`. Both are legal expressions. Choosing `x+x` produces a syntactically prepared program but fails its assertion at `x=3`. `prepared` therefore means ready for separate execution, not correct. The result exposes that distinction and the final source. `fill --request REQUEST --answers ANSWERS` also accepts explicit exact selected strings without calling a model.

The small catalog's `let`, `assert`, `if` and `for` templates are checked against the current native parser and bind its authoring contract. This is a finite authoring interface with caller-defined menus, not a general-purpose unconstrained code planner or a proof that a small model can solve every task. No provider-specific constrained decoding is claimed.

## Records and limits

`run` requires a new empty private folder. It writes the immutable request, compiler hash, source, inputs, execution pins, native call/trace records and final result. An existing folder refuses before any model call; an interrupted invocation is never silently repeated. Inspect retained records and use the native explicit replay tools for known recorded outcomes. Starting a distinct folder is a fresh invocation and a fresh budget.

Maximums: 32 slots, 32 choices per slot, 32 acceptance predicates, four builder rounds, three reviewers and 32 KiB template text. Context budgets are character limits, enforced by native ask options; they are not token counts. Slot budgets account for the template and choice card up to 131,072 characters; larger requests refuse with a split-task message. Effects and constructor execution are disabled. The CLI uses the native child-process boundary when installed, so it does not impose limits on the dashboard process or remote provider workers.

The isolated tests exercise actual native dispatch with fake providers, critic veto, mistaken consensus, multi-review context, early stopping, failure budgets, parser injection refusal, visible wrong choices and the durable existing-folder fence. These tests establish implementation behavior; they do not measure a real model's accuracy gain.

## Page and pure authoring API

Open the **Workcards** tab, select the builder and critic, write the type and predicates, then **Prepare checked team**. Inspect the generated program and **Open in Write** to run it. Preparation never calls a model. The native run API pins the exact source, inputs and current execution runtime when starting, just as for a handwritten program. A draft compile is not an execution pin.

`workcards/catalog` (GET), `workcards/compile`, `workcards/prepare` and `workcards/fill` (POST under `/api/automation/symblic/`) expose pure authoring. Slot fill returns selected text and prepared source with `execution: not_run`; run the source separately to check its behavior.

An actual local example completed with a Llama3.2 1B builder on node-a and the same model as critic on node-b: two model calls returned `3`, then native predicates checked its square and sign. Inspect that recorded run (recorded on the original host; not public). This establishes that execution path for one task, not a general accuracy benefit from debate.
