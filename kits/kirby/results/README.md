# Kirby results: seven pages written by small local models

Each page here is a complete, self-contained `kirby.html` (open it in a browser; arrows or A/D walk, Space jumps and
floats, X inhales, S swallows, C spits, R restarts). Each one was built on 2026-10-11 by a Symblic program compiled
from one of the sheets in `../sheets/`: every unit was asked of the models named below in a fresh context, tested by
the kernel against that unit's examples, and the page was assembled only from units that passed. Nobody edited a
page afterwards.

All seven were graded again on 2026-10-11 with this repository's harness
(`node kits/kirby/harness/harness.mjs PAGE`): **every page passes `required 68/68`.**

| page | sheet | models (each in Ollama on its own CPU-only machine) | units asked | model calls | wall time |
|---|---|---|---|---|---|
| `kirby-4b-r4.html` | `kirby.sheet.md` (4B wording, before the level became a given unit) | qwen3:4b-instruct, gemma3:4b | 32; the first 7 units were kept from an earlier round of the same build that accepted them and then stopped (21 calls) | 103 (+21 in the earlier round) | 127 min |
| `kirby-4bs-r1.html` | `kirby-3b.sheet.md` (numbered steps), level given | qwen3:4b-instruct, gemma3:4b | 38 | 96 | 139 min |
| `kirby-3b-r1.html` | `kirby-3b.sheet.md` (numbered steps, before the level became a given unit) | qwen2.5-coder:3b, granite3.3:2b | 39 | 92 | 83 min |
| `kirby-1b-r1.html` | `kirby-1b.sheet.md` (exact code), level given | gemma3:1b, qwen2.5:0.5b | 38 | 81 | 25 min |
| `kirby-1bl-r1.html` | `kirby-1b.sheet.md` (exact code), level given | llama3.2:1b, gemma3:1b | 38 | 96 | 66 min |
| `kirby-05b-r1.html` | `kirby-1b.sheet.md` (exact code), level given | qwen2.5:0.5b alone | 38 | 84 | 20 min |
| `kirby-05b2-r1.html` | `kirby-1b.sheet.md` (exact code, with the line-difference retry reason), level given | qwen2.5:0.5b alone | 38 | 78 | 18 min |

Settings of every build: `--samples 2 --retries 3 --rounds 2` (route=search, fresh context per unit). Local calls
were capped at 4096 output tokens and 900 s each for the first and third rows, and at 2048 tokens and 600 s for the
others. Wall time includes waiting for busy machines.

## Read this before drawing conclusions

- **The sheets were still being edited that day.** The rows marked "before the level became a given unit" were
  built before `Given: yes` existed (the models typed the level map themselves). The sheets in `../sheets/` are the
  final versions of that day; their examples are the ones every page was built against, and the harness grades
  behaviour, not wording. A page built from today's sheets will differ in detail: models sample.
- **The lighter the model, the more the sheet dictates.** The 1B and 0.5B pages come from the exact-code sheet: the
  model's job there is to reproduce given code inside a fenced block, which those models did not manage reliably
  without the kernel's answer normalizer, the given level and the line-difference retries. What these rows show is
  that the pipeline (sheet, checks, retries, assembly) carries a very small model to a correct page, not that a
  0.5B model can design a game. `kits/tetris/build/verbatim.py` measures how much of a page appears word for word
  in its sheet: 38% of `kirby-4b-r4.html`'s non-trivial script lines.
- **Failures happened too.** The first two rounds of the 4B build stopped early, after accepting 7 units and before
  any call, because JavaScript checks timed out on a heavily loaded machine (the kernel now observes a timed-out
  check again after waiting for the load to drop); a third round was stopped after accepting 4 units, and the fourth
  kept the first round's 7 units (`--keep`) and finished. Three builds of gemma3:1b with qwen2.5:0.5b on the
  numbered-steps sheet (`kirby-3b.sheet.md`) failed at the same unit (`solidRow`) after 27, 16 and 16 calls; the 1B
  models needed the exact-code sheet.
- **One author.** The sheet, its examples, the reference, the oracle and the harness were written by the same AI
  coding agent; a misreading of the contract shared by all of them would not be caught (see `../README.md`).
