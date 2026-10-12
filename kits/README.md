# Kits: complete spec-sheet builds, with everything needed to trust the result

A **kit** is everything one Symblic build needs besides the models:

| part | what it does |
|---|---|
| `sheets/` | the specification sheet: the output file described as small units, each with a contract and examples (see `symblic/spec/README.md`) |
| `reference/` | a deterministic reference written as the same units, the tools that compute the sheet's examples from it, and an independent oracle it is checked against |
| `harness/` | a strict harness that grades an assembled page against the reference over scripted and random play, and tests of the harness itself |
| `build/` | a no-model dry run of the whole build (the reference stands in for the model), and the script that saves and grades a build's page |
| `results/` | pages that small local models built, with the record of who built each one and at what cost |

The build loop itself, shared by both kits, is `build_loop.py`: it compiles a sheet, runs it against an
[Ollama](https://ollama.com) server and keeps what passed for the next round. Each kit's `README.md` says exactly how
to run every check and every round.

| kit | output | units | built by (all pages pass their harness) |
|---|---|---|---|
| `tetris/` | `tetris.html`, a falling-block game | 25 | qwen3:4b-instruct with phi4-mini and gemma3:4b, 2026-10-04 (2 pages) |
| `kirby/` | `kirby.html`, one platformer level | 39 | seven builds on 2026-10-11, from qwen3:4b-instruct with gemma3:4b down to qwen2.5:0.5b alone (7 pages) |

Both games are unofficial tributes used as programming tests; they are not affiliated with or endorsed by the owners
of the Tetris or Kirby trademarks, and they contain no artwork, sound or code from those games. Everything in the
kits except the result pages was written by AI coding agents; the result pages were written unit by unit by the small
local models named in each kit's `results/README.md`.
