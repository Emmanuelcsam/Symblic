# Examples

Small, complete inputs for each part of Symblic, from programs that need no model at all to records of what small
local models built. Every command below runs from the repository root. Commands marked **no model** can be run on any
machine with Python 3.12 (and Node.js 22 plus Linux 6.7 or newer where JavaScript is checked); the others ask a
model through an applicator such as `ollama:qwen3:4b-instruct` (see `symblic/providers/applicators.py`).

`tools/symblic` is the command-line entry point (`tools/symblic --help`); `python3 -m symblic.<package>.<module>`
reaches each package's own command directly.

## Native programs (`*.sym`)

| file | what it shows | run |
|---|---|---|
| `02-flower-formal.sym` | a flower drawn entirely from formal statements; every applicator draws the same bytes | **no model**: `tools/symblic run examples/02-flower-formal.sym --max-calls 0` |
| `03-flower-from-essay.sym` | the same kind of flower described in prose: a model turns the essay into a closed specification and the kernel draws it, so identical drawings mean the models read the essay the same way | asks a model |
| `04-family-logic.sym` | a model lists the parent-child facts of a short story; the kernel's Datalog rules do the multi-hop reasoning (ancestors, cousins) | asks a model |
| `06-small-model-council.sym` | a logic puzzle split into three small asks for a panel of small Ollama models with `effort=ultra` (one round in which each sees the others' anonymised answers); its `@node-a` ... placements name the original host's worker nodes, so change them to your servers | asks models |
| `07-local-model-decisions.sym` | two closed, low-effort decisions about one message (a category and a yes/no) from a small local model | asks a model |
| `08-v1-prose.sym` | the prose form of Symblic version 1 (`Program:`, `Use Model:`, one sentence per ask), which the legacy profile still reads | asks a model |
| `09-council-and-triad.sym` | a council decision and a plan, then `delegate` to a coding agent; it needs an embedding host that provides councils and delegation, which this repository does not | asks models; starts an agent |
| `10-kernel-identity.sym` | everything decided by the kernel (exact rationals, decimal trigonometry, Datalog rules, drawings); the fingerprints it shows must be the same on every machine | **no model**: `tools/symblic run examples/10-kernel-identity.sym --max-calls 0` |
| `11-checked-routing.sym` | an ask the kernel can answer by itself because its finite domain admits one value (`solve=true`), and checked escalation when it may not | **no model**: `tools/symblic run examples/11-checked-routing.sym --by kernel --max-calls 0 --json` |
| `12-finite-ambiguity.sym` | an intentional failure: two values satisfy the check, so the report must not claim a unique answer | **no model**: `tools/symblic run examples/12-finite-ambiguity.sym --by kernel --max-calls 0 --json` |
| `14-question-order.sym` | a measurement of question-order effects on the models it runs with (it says nothing about people) | asks models; see the notes in the file |
| `constructor.sym` | the smallest program for the linear constructor: one `Int` ask whose check is linear, so a solver can answer it instead of a model ([../docs/reference/CONSTRUCTOR-CLI.md](../docs/reference/CONSTRUCTOR-CLI.md)) | **no model** with `--constructor linear --max-calls 0` and a provisioned solver runtime ([CONSTRUCTOR-PROVISIONING.md](../docs/reference/CONSTRUCTOR-PROVISIONING.md)); otherwise asks a model |
| `quadratic-witness.sym` | an exact finite quadratic minimization and its independent check ([../docs/reference/VARIATIONAL.md](../docs/reference/VARIATIONAL.md)) | **no model**: `tools/symblic run examples/quadratic-witness.sym --max-calls 0 --dir NEW_FOLDER` |
| `cmatrix.sym` | "matrix rain": the kernel computes every character, position and shade; a player supplies the clock | **no model**: `tools/symblic run examples/cmatrix.sym --max-calls 0` |
| `vorticity-construction.sym` | a discrete energy-method construction on a 5-vertex graph, one small model-built part per ask, every part checked (a synthetic example, not a fluid simulation) | asks models |
| `stand-in-answer.py` | not a program: a stand-in for a model that answers an `Int` ask with 3 (or the number you give it), for trying `run` and `replay` without a model; see step 3 of the root README | **no model**: `SYMBLIC_COMMAND_STAND_IN="python3 $PWD/examples/stand-in-answer.py" tools/symblic run root.sym --by command:stand-in --dir NEW_FOLDER` |
| `41-small-model-cup.sym` ... `46-small-model-gantry.sym` | checked playback of the code small models wrote on 2026-10-07 (the `small-model-*` folders below): the exact accepted functions and all their checks | **no model**: `tools/symblic run examples/44-small-model-math.sym --max-calls 0 --dir NEW_FOLDER` |

## Crystals (`crystals/`)

A *crystal* is a routine's answers over a finite list of inputs, frozen into a kernel table after a panel of models
agreed on them; afterwards the table answers with no model call and refuses inputs it does not cover. `elements.sym`
is the routine (is a chemical element a metal?) and `is_metal.crystal.sym` the crystal made from it on 2026-10-02
(20 of 20 inputs kept); see [crystals/README.md](crystals/README.md).

- **no model**: `tools/symblic test examples/crystals/is_metal.crystal.sym`

## Plain-English statements (`english/`)

Documents for `symblic/english` (one fresh, checked model request per `Ask for` statement):
`falling-number.english.txt` and `categorize.english.txt` with the programs they compile to (`*.compiled.sym`, kept
byte for byte by the tests), `matrix-rain.english.txt` and `matrix-rain-seven-step.english.txt` (the construction
grammar), `moving-dot.english.txt` (the labelled pixel grammar) and `twin-helix.english.txt` (a larger statement
program: a counter-rotating double helix around a ringed planet, every visible cell an exact integer projection and
every `Ask for` one small claim).

- **no model**: `python3 -m symblic.english.cli check examples/english/falling-number.english.txt`
- **no model**: `python3 -m symblic.english.cli compile examples/english/categorize.english.txt`
- asks a model: `python3 -m symblic.english.cli run examples/english/falling-number.english.txt --dir NEW_FOLDER --by ollama:qwen3:4b-instruct`

## Handing a bounded task to a small agent (`symblic/delegate`)

| file | what it is |
|---|---|
| `agent-handoff.task.json` | a `witnessed_line` task: select one line of a given text and prove where it came from |
| `incremental-command.task.json` | a `proof` task: build a short derivation one checked command at a time |
| `proof-step.task.json`, `proof-step-card.task.json`, `proof-step-focus.task.json`, `proof-step-obligation.task.json` | the four proof-step templates, one request each |
| `proof_step_handoff.py`, `proof_step_card_handoff.py`, `proof_step_focus_handoff.py`, `proof_step_obligation_handoff.py` | parent programs that hand proof steps to fresh child agents and recheck every returned step; they use fake children, so they make no model call |
| `expense_handoff.py`, `expense-handoff.sym`, `expense-handoff.json` | a complete hand-off with pinned inputs, a local model and an exact replay (`docs/reference/EXPENSE-HANDOFF.md`) |

- **no model**: `python3 -m symblic.delegate.run check examples/agent-handoff.task.json --agent-json`
- **no model**: `python3 examples/proof_step_handoff.py` (prints `{"complete": true, "fake_only": true, "steps": 3}`)
- **no model**: `python3 examples/expense_handoff.py prepare examples/expense-handoff.json --by ollama:qwen3:4b-instruct --dir NEW_FOLDER`
  (then `run` asks the model and `check` replays the record; see the file's docstring)

## Spec sheets, step constructions, workcards and graphs

| file | for | run |
|---|---|---|
| `agent-handoff.sheet.md` | the smallest spec sheet (3 units: `double`, `ready`, `next`); the kits in `../kits/` are the large ones | **no model**: `python3 -m symblic.spec.sheets check examples/agent-handoff.sheet.md` or `python3 -m symblic.spec.build check examples/agent-handoff.sheet.md` |
| `steps-parcel.json`, `steps-parcel-inputs.json`, `steps-parcel-built.sym` | a 13-function parcel-pricing program built as a step construction: a model picks each function's expression from the author's list, the kernel's checks decide; `steps-parcel-built.sym` is the assembled result | **no model**: `python3 -m symblic.authoring.workcards compile --kind steps --request examples/steps-parcel.json --by ollama:qwen3:4b-instruct` |
| `workcard-slots.json`, `workcard-team.json` | a fill-the-hole workcard and a builder-with-reviewer workcard | **no model**: `python3 -m symblic.authoring.workcards prepare --kind slots --request examples/workcard-slots.json` |
| `reusable-graph.json` | a reusable group of agents composed twice; its expansion runs with zero model calls | `python3 -m symblic.graph.compose example` |

## Records of small-model builds (`small-model-*-20261007/`)

Four bundles from 2026-10-07, each with its own `README.md`: what qwen3:4b-instruct wrote through Symblic (a 3D-printable
cup mesh and a chart; exact rational mathematics; a pricing page; a gantry geometry mock-up), the exact accepted
code, the outputs, independent validators and an `evidence.json` record of every call, failure and hash. Each has a
**no model** check: `python3 examples/small-model-math-20261007/verify.py`. These are finite synthetic tests, not a
benchmark; each README says what its checks do and do not establish. The bundles' READMEs were edited for publication
(names of the original private host removed); `evidence.json` records that edit, and every other file is unchanged.
`artifacts.json` lists the files of the four bundles with their sizes and SHA-256 hashes; the original host served
checked downloads from it (`integration/host/symblic_example_artifacts.py`). Its entries for the edited READMEs and
`evidence.json` files were updated to the published bytes on 2026-10-12.

## Larger kits

`../kits/kirby/` and `../kits/tetris/` hold the two complete game kits (a spec sheet, a deterministic reference, a
strict harness, a build loop and the pages small local models built).
