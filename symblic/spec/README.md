# symblic/spec: spec sheets

A **spec sheet** describes one output file (a game page, a small library) as a list of small units of code. Each
unit has a contract in prose and examples (`call ==> expected JSON`). Symblic compiles the sheet into a program in
which a model writes each unit in a fresh context, the kernel tests every answer against that unit's examples in a
JavaScript sandbox, a failing answer is retried with the failing examples as feedback, and the file is assembled only
from units that passed. No model writes the program, and nothing a model returns is used until its unit's examples
hold.

This is the part of Symblic that small local models have actually built complete programs with: a Tetris game
(qwen3:4b-instruct, phi4-mini and gemma3:4b, 2026-10-04) and a platformer level (models from 4B down to a 0.5B model
alone, 2026-10-11). Both kits, with their sheets, references, harnesses and result pages, are in `../../kits/`.

## The modules

| module | what it does | runs a model? |
|---|---|---|
| `sheets.py` | the sheet format (`parse`, `problems`) and the build compiler the kits use (`compile_sheet`), plus `diagnose` (why replies failed) and `accepted_units` (reuse what a build accepted). CLI: `python3 -m symblic.spec.sheets check|compile|diagnose` | no (it writes a program; the kernel runs it) |
| `build.py` | the newer task-card compiler: every model request carries the unit's exact contract and its complete dependency closure within a measured budget; accepted units are rechecked and sealed into portable records. CLI: `python3 -m symblic.spec.build check|compile|run|checkpoint|manifest|verify` (also `tools/symblic spec ...`) | only `run` |
| `contracts.py` | pure unit contracts: stable identities, dependency order, reuse decisions, records and manifests for `build.py` | no |
| `compare.py` | differential questions: run several candidate implementations on new probe calls and report where they disagree, without choosing an answer | no |

How they fit: `sheets.parse` reads a sheet. `sheets.compile_sheet` turns it into a program directly (the kits' path).
`contracts.plan` turns the parsed sheet into unit contracts, which `build.compile_cards` uses for the task-card path
and `compare.compare` uses to check candidates. Both compilers produce ordinary Symblic programs that the kernel's
runner (`symblic/kernel/run.py`) executes with the applicators of `symblic/providers/`. `kits/build_loop.py` does one
round of a real build (compile, run against an Ollama server, keep what passed) in one command.

**Which compiler?** Use `sheets.py` for sheets written for the smallest models: only it supports `Answers normalized:
yes` (the kernel repairs mechanical slips in a model's answer before testing it) and `Given: yes` (a unit whose code the
sheet supplies), and only it has `diagnose`; its `--keep` reuses the leading units an earlier build accepted. Use
`build.py` when you need portable, verifiable records of accepted units, an exact output hash, or reuse of accepted
units across edits by dependency rather than by position.
The recorded game builds all used `sheets.py`; `build.py` is tested with fake models only.

## The sheet format, in brief

```
# tetris.html                         the output file
(intro)
## Shared                             what every unit sees
Used units shown as: signatures       optional; prompts name the units a unit may call instead of pasting their code
Answers normalized: yes               optional; the kernel repairs a small model's mechanical slips before testing
## Unit `cellsOf(type, rot)`          one unit: the names it defines, then its contract
Uses: `SHAPES`                        names of earlier units it may call
Given: yes                            optional; the unit's fenced ```js block is its code (tested, never asked)
Test setup:                           optional, indented helpers for the examples
Examples:
    cellsOf('T', 1) ==> [[1,2],[0,1],[1,1],[2,1]]
## Assemble `tetris.html`
    (the page, with /*UNITS*/ where the code goes)
```

The smallest complete sheet is `../../examples/agent-handoff.sheet.md`; the largest are in `../../kits/`. Writing
for small models (what worked, measured on the kits): numbered steps with exact expressions, lookup tables for
mappings, units of 2-40 lines, the functions a unit calls described in its own text, and for 1B models the exact code
(`Write exactly this code:`), which the compiler checks with a line-by-line difference as the retry reason.

## What a passing build establishes

Every unit gives every value its examples list, after the units before it. That is all. A unit can pass its examples
and still be wrong on inputs no example covers, which is why each kit has an independent harness for the whole file,
and why `compare.py` exists: two passing candidates that disagree on a new input reveal a question the sheet has not
answered.

## Requirements

Python 3.12; for the JavaScript checks Node.js 22 and Linux 6.7 or newer (Landlock), see `symblic/js/check.py`.
Without the sandbox every check is "unavailable" and no unit can pass.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/spec -t .
```

All tests use fake models and temporary folders. `test_cli_dispatches_source_only_spec_check` runs `tools/symblic`.
The host-only HTTP route test is `tests/integration/test_symblic_spec_compare_api.py` (skipped without that host).
