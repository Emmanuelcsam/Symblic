# Local autogen: light models on the kernel lane

Light local models (0.5B to 4B, in Ollama on the worker nodes) cannot drive a CLI agent. the CLI agent's tool schemas alone
exceed its 7168-token input guard, and a 1B model answers by echoing the schema. What works for them is the
kernel lane that built Tetris with 4B models ([SPEC-SHEETS.md](SPEC-SHEETS.md)): a spec sheet is compiled into
one fresh-context `Code js` ask per unit, every answer is checked by the sandboxed `js_test` against the sheet's
examples, and the file is assembled from passing units only.

An autogen run with `engine local` therefore takes one spec sheet as its one statement, and every attempt is a
kernel build, not a hub task. Every autogen mechanism still applies: candidates, regeneration, stall-driven
decomposition, stuck and resume, timeouts, cancel and promotion ([AUTOGEN.md](AUTOGEN.md),
[RECURSION.md](RECURSION.md)). Code decides every verdict.

**Status, 2026-10-11 03:06 (host local time).** Implemented in `symblic/autogen/kernel_lane.py`, `symblic/autogen/coordinator.py`,
`symblic/autogen/policy.py` and `tools/symblic-task`, with focused tests that use a fake kernel and temporary stores.
One build of a sheet whose units were all kept (no ask, so no model call) ran through the real path: its own
scope under `a systemd slice for work`, the pid file, `tools/symblic run`, `js_test` and the assembled page.

The first version went live with the restart at 02:35. Its first run (`autogen-4b11d1ff5024991b97c899e4`, a
4-unit Tetris-pieces sheet, `qwen2.5-coder:3b@node-i`) recorded, as read at 02:49:
- the first build accepted 1 of 4 units, and two regenerations (feedback, fresh, both keeping it) stopped at
  `cellsOf`;
- the Text split never passed its shape check: the 3B answered inside the kernel's `{"reasoning", "answer"}`
  envelope with the stalled unit or its examples restated, never `## Unit` sections;
- a re-plan was placed on `node-arm`, an ARM node without the model (`INFRASTRUCTURE`).

The typed planner and the placement rules below answer those two failures. They are not live until the next
restart, and no model has run them.

## What runs where

| Part | Where | What |
|---|---|---|
| Coordinator | the dashboard process on the host (`AutogenManager`) | decisions, the run record, verdicts, promotion |
| Build | the host: `tools/symblic run RUN_DIR.sym --dir RUN_DIR --ollama-limits JSON --json` | orchestrates only, at nice 10, in its own process group, in the user scope `autogen-kernel-<run hex>-<attempt>.scope` under `a systemd slice for work` (`MemoryMax=1G`, `CPUQuota=50%`, `TasksMax=128`) when the user bus allows; the environment is `PATH`, `HOME` and `LANG` only |
| Model calls | the worker node named by `--node`, as `ollama:<model>@<node>` through the fleet runner | never the host, never a hosted Ollama model (`...-cloud`, `...:cloud`), never a CLI agent |
| Unit checks | the host, `js_test` in its Landlock sandbox ([JS.md](JS.md)) | each answer against the unit's examples |
| Checkout | `agent_hub.make_worktree`: `<project>.agents/autogen-<12 hex>-<attempt>-<stamp>` | the assembled file is written there and checked there |
| Promotion | `agent_hub.commit_all` + `apply_work` | the hub's per-file 3-way apply into the project's working copy |

The run folder of each attempt is `<symblic/os root>/state/autogen/kernel/<run id>/<attempt id>/`, with
`<attempt id>.sym` (the program), `.pid` and `.log` beside it. The folders are kept: they are the evidence, and
the source of `--keep` for later builds.

## Starting a run

```sh
tools/symblic-task workspace tetris
tools/symblic-task start --sheet kits/tetris/sheets/tetris.sheet.md --root ~/symblicos/projects/tetris \
    --model qwen3:4b-instruct --node node-i --autogen --until-done --strategies feedback,fresh --attempt-seconds 14400
tools/symblic-task autogen wait RUN_ID
tools/symblic-task autogen get RUN_ID        # units N/M per build; a running build's folder and log
```

- `--sheet FILE` replaces `--lines` and `--instruction`; the file is sent verbatim as `instruction` with
  `sheet: true`. It implies `--autogen` and `--engine local`, and needs `--model` (an Ollama model installed on
  the node) and `--node` (a worker node).
- `--check 0:COMMAND` runs the operator's command on the assembled file, in the attempt's checkout; `--final` and
  `--hidden` run in the project folder at the end, as for any run.
- `--parallel`, `--worktree`, `--auto-next`, `--no-auto`, `--mode`, `--perpetual` and `--designer` are refused
  for a sheet.
- `--strategies feedback,fresh` keeps the run on the worker node it names. With `other_node` in the rotation (the
  default), a regeneration may move to another online worker node, which must have the model installed.
- The CLI checks the sheet with `symblic.spec.sheets.problems` before sending it; the server checks it again.

The route is `POST /api/symblicos/autogen/start` with `"sheet": true, "engine": "local"`. The server:

- refuses `sheet: true` with another engine, and an ordinary statement on `local` ("local attempts take a spec
  sheet; see docs/reference/SPEC-SHEETS.md"); a `local` instruction that is a sheet is taken as one without the flag;
- replaces the line lint with `symblic.spec.sheets.problems`, and refuses a sheet over 200 000 characters or whose
  Assemble file is not a relative path with an extension inside the workspace;
- refuses a perpetual lane, a hosted or malformed model name, and the host as the node;
- keeps the sheet on the kernel lane: the policy's engines are `["local"]`, so `other_engine` never applies, and
  a resume re-reads only the worker nodes;
- records `base.sheet` and `node.sheet`; a sheet node never gets a test designer (its examples are its tests).

## One attempt

1. **Intent**, under the run lock: `attempt.kernel = {mode: "build", run_dir, applicators, seed, limits, file,
   units_total, keep_from, samples, retries, rounds, pending: true}` and the budget count. There is no task body.
2. **Dispatch**, outside the lock: the program is compiled (`symblic.spec.sheets.compile_sheet` with `--keep` and the
   attempt's seed), the checkout is made, and the checkout, the hash of the file it already holds and the
   program's hash are recorded before the process starts; its pid after. The process writes its own pid file
   before it execs.
   - A crash before the process started re-dispatches the same intent once (`launch_recovered`): the checkout is
     adopted by its name, the same program is compiled again.
   - A crash after it started: the pid file is adopted, so one run folder never holds two builds.
   - A dashboard restart leaves the build running in its scope; the coordinator re-attaches and recognises the
     process by its command line, which names the run folder.
3. **Observation**, every pass: `state.json` and `trace.jsonl` are read. While the build runs, only its accepted
   units are updated. A unit counts as accepted when its ask row is `ok` (the search route writes it only after a
   candidate passed), or when a kept unit's `assert` passed.
4. **Verdict**, when the build ended:
   - It finished: the assembled page is written into the checkout and checked there like any statement of one
     file: it exists and changed, its syntax by extension, the operator's commands. A `units` row (`3/3 units
     accepted`) is added.
   - It stopped at a unit because no answer passed its examples (kernel error kind `check`): the file fails
     `exists` (`NO_OUTPUT`), and the `units` row names the unit and the kernel's report.
   - Any other end (a model or node unavailable, no final state, a kernel refusal) is `INFRASTRUCTURE` (or
     `REFUSAL`), with the log's tail.
5. **Progress** adds one axis: more units accepted than the node's best is progress (`progress.units`).
6. **Promotion**: a durable intent, then the hub's `commit_all` and `apply_work` on the attempt's checkout.

## Regeneration, timeouts and stops

- Every build after the first keeps the units the node's best earlier build accepted (the most units, the latest
  on a tie): they become fixed text, are tested again by the kernel, and are never asked again. The first build
  of a split child keeps its parent's best build. `feedback` and `fresh` both keep; within a build, the failing
  examples reach the model through the compiler's own `ensure ... else retry because test_X.report`.
- Each attempt has its own seed in the program's `use` line, so a regeneration samples new answers rather than
  repeating the same seeded replies.
- `attempt_seconds` stops a build: SIGTERM to its process group (the CLI releases its admitted model calls), then
  SIGKILL after 20 s. The attempt is `TIMEOUT`, and the units it accepted count as progress, so a long sheet is
  built across several attempts, each keeping the last one's units.
- Cancel and a superseded candidate stop the build the same way. A build that does not stop keeps its slot
  (`cancel_failed`) and is stopped again on the next pass.
- A promotion `CONFLICT` (the project file changed while the build ran) ends the node, `stuck` with `until_done`
  and `failed` otherwise. There is no conflict retry for a sheet: a rebuilt page never contains the operator's edit,
  and the retry's checkout would hold that edit as its base, so the apply would overwrite it. The built file
  stays in the attempt's checkout.

## Decomposition

The policy's own decisions trigger it: the stall rule (`novelty_limit` builds without a new unit) with
`until_done`, or `--decompose D` in bounded mode.

- **The planner is a typed kernel ask.** A small program asks the model to split the stalled unit (the first unit
  the best build did not accept) with the answer type
  `List of Record {name: Text, args: Text, contract: Text, examples: List of Record {call: Text, expect: Text}
  length 2..6} length 2..3` (`autogen_kernel.planner_type`). The kernel compiles it to a JSON schema, and the
  local route sends that schema as Ollama's `format`, so decoding is grammar-constrained: the answer is a list of
  2 or 3 unit objects, after the envelope's `reasoning`. `expect` is text holding the JSON value, because `Any`
  compiles to the empty schema, which older llama.cpp grammar converters read as "any object".
- **The kernel checks it before any code does**, with `route=search, samples=2, retries=2` and a `because` that
  reaches the model: every `name` is an identifier (`matches`), is new (`not contains(taken, name)`, where `taken`
  includes the format's example `smallName`), names are distinct, and every example's `call` contains `name(`.
  An answer that restates the stalled unit or its examples fails here and is retried. The prompt holds the shared
  section, the unit's contract, examples and test setup, and the stopped build's error.
- **Code validates the answer** (`autogen_kernel.split_sheet`). Each object becomes a `## Unit `name(args)``
  section that inherits the stalled unit's `Uses:`; `expect` is read as JSON, and text that is not JSON is the
  string it spells (`ready` and `'ready'` both become `"ready"`). The typed answer is read from the output's
  canonical form, so its values are exact. Refused: fewer than 2 or more than 3 units, a name that is not an
  identifier or that the sheet already defines, `smallName`, a unit with fewer than two examples or with an
  example that does not call it, a refined sheet with `symblic.spec.sheets.problems`, and an example call that does not
  run as JavaScript. The last check evaluates every call in the sandboxed js adapter against stubs of every name
  in the sheet: a syntax error or an undefined name refuses the split, a wrong value cannot (no implementation
  exists yet). A Text answer from a planner compiled before the typed ask is still read as `## Unit` sections.
- **The result is one refined sheet**: the sub-units, then the stalled unit itself, its `Uses:` extended with the
  sub-units and one line asking it to call them. Its examples stay as the integration check. Every other byte of
  the sheet is unchanged. It becomes the node's one child (`n0.0`), whose first build keeps the parent's best
  build; the parent is accepted after the child, when its own checks pass in the project folder.
- A refused split sets `split_refused`; with `until_done` the node re-plans on another worker node that holds the model,
  else ends.
- **Nothing to split.** When every unit was accepted and only the operator's checks fail, a split cannot help: the
  planner is refused without starting a build (`split_impossible`), and the node regenerates until nothing novel
  is left, then ends `stuck`. Give the sheet examples that catch what the operator's check catches.
- A kernel build never writes `AUTOGEN-SPLIT.txt`, so worker self-splits do not apply to it.

## Where attempts run

- **The rotation is the worker nodes that hold the model.** A sheet run's `policy.nodes` (what `other_node` and re-plans
  choose from) starts as the online worker nodes (never the host, never the ARM node `node-arm`). On its first pass, and
  again after each resume, the coordinator narrows it to the worker nodes whose inventory lists the model and where it
  fits the node's Ollama memory limit: `symblic.providers.applicators.Applicators.inventory()`, the data `pick_node` places on
  (`local_research.inventory`, every node's `/api/tags`, cached 10 minutes). That read can ask every node over
  SSH, so it runs in the coordinator thread, outside the run lock, never in a request. An unreadable inventory
  keeps every online worker node.
- **The operator's own node is never vetoed by the cached inventory.** The first build goes where the operator said;
  the launch is the fresh check (the 2026-10-06 admission rule: a cached picker inventory is not launch
  evidence).
- **A node found without the model is not a try.** When a build or planner fails because the model is not
  installed on its node (the kernel reports the fleet runner's "M is not installed on NODE"), the attempt is marked
  `placement_absent`. The node joins `model_absent`, leaves `policy.nodes`, and a statement placed there moves
  back to the operator's node, or else the first node that may hold the model. The policy then counts the attempt
  as neither work nor a planner: it consumes no regeneration, no strategy quota and no re-plan placement, adds
  no stall and no progress, and a planner placed there does not set `split_refused`, so the same split runs
  again where the model is.
- A decision made before the absence was seen never launches there: the intent moves to the first node that may
  hold the model. With none left, the statement ends (`stuck` with `until_done`, `failed` otherwise): "M is not
  installed on any node this run may use".

## Record

| Field | Meaning |
|---|---|
| `base.sheet`, `node.sheet` | a sheet run and its sheet nodes (only on such runs, so older request digests are unchanged) |
| `node.keep_from` | a split child: the parent's best build folder |
| `node.split_impossible` | every unit passed; the node is never decomposed |
| `model_absent` (run) | nodes an attempt found without the model; never placed on again |
| `catalogue_checked` (run) | when the rotation was last narrowed by the model inventory, and whether it was readable |
| `attempt.placement_absent` | the attempt's node lacked the model: it never ran and is not counted |
| `attempt.kernel` | `mode` (`build` or `split`), `run_dir`, `applicators`, `seed`, `limits`, `file`, `units_total`, `keep_from` (builds), `unit`, `heading`, `from_run`, `children` (splits), `checkout`, `base_sha256`, `program_sha256`, `pid`, `pending`, `spawned`, `accepted`, `units_accepted`, `calls`, `status`, `stalled`, `error` |

Events are the existing ones (`launch_intent` and `launched` carry `kernel` and `pid`;
`catalogue_refreshed` says `reason: model inventory` when the inventory narrowed the rotation), plus
`model_absent` (`where`, `model`). A kernel attempt has no `task_id`; the panel shows it without a terminal link.

## Limits

- Per attempt and unit: `samples 2, retries 2, rounds 1`; per local call: `num_predict 4096`,
  `timeout_seconds 900`. These are constants in `autogen_kernel` (`SEARCH`, `LIMITS`), not policy fields.
- Each build makes one checkout and branch in `<project>.agents/`, as CLI attempts do; nothing prunes them.
- A build killed with SIGKILL may leave an admitted call on its worker node until the fleet runner releases it.
- The `/symblic/#autogen` panel has no sheet field: start sheet runs with the CLI or the route.
- A passing build establishes what [SPEC-SHEETS.md](SPEC-SHEETS.md) says it establishes: every unit gives every
  example's value. The operator's checks are what test the whole file.
- Runs recorded before 2026-10-11 with ordinary statements on `local` keep their CLI-agent task attempts.

## Tests

`tests/autogen/test_kernel_lane.py`: submission (a sheet is one statement checked by `symblic.spec.sheets`,
refusals), the kernel intent and dispatch (no task, own checkout, seeded program; a crash before or after the
process started never starts a second build), verdicts with the operator's check and promotion, regeneration with
`--keep` from the earlier build, progress in accepted units, timeout and cancel stopping the process group, a
stop that fails, decomposition into a refined child sheet from a typed answer, a restated answer refused by code,
a sheet with nothing to split, a conflict that never overwrites the operator's edit, the typed planner's schema and
its in-kernel check (evaluated by the kernel on fixed answers, no model), typed answers with exact values, the
rotation narrowed by the model inventory, builds and planners on a node without the model (not counted, moved,
stuck when no node is left, resumed with the inventory), the run-folder parser, compiled and split programs
(statically checked by Symblic), split validation, the sandboxed example check (when node is available), the real
process mechanics against a stand-in for `tools/symblic`, the hub's checkout and apply on a temporary git
repository, and the CLI. No test starts a real build or calls a model; `autogen_kernel.run` refuses the real
`tools/symblic` under `DASH_TEST=1`.
