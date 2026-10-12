# Tetris kit: a complete falling-block game, written unit by unit by small local models

> **A tribute, not an official product.** Tetris is a registered trademark of The Tetris Company. This kit is an
> unofficial tribute used as a programming test; it is not affiliated with, endorsed by or sponsored by The Tetris
> Company or anyone else. It contains no artwork, music or code from any Tetris product: the rules below were
> written for this kit from the widely known guideline behaviour (seven pieces, a shuffled bag, rotation with wall
> kicks, hold, lock delay), and the page draws coloured squares on a canvas.

This is the first Symblic kit, and the first page Symblic built with small local models only (2026-10-04). It has
the same parts as the Kirby kit (`../kirby/`), in a rougher, earlier form:

1. **A specification sheet** (`sheets/tetris.sheet.md`): `tetris.html` described as 25 units of JavaScript with 120
   examples. Symblic compiles it into a program that asks a model for one unit at a time in a fresh context, tests
   each answer against the unit's examples in a sandbox, retries with the failing examples as feedback, and
   assembles the page from passing units only. See `symblic/spec/README.md` for spec sheets in general.
2. **A deterministic reference** (`reference/`): an oracle written from the rules as one class
   (`reference.mjs`), the same rules written as the sheet's units (`ref-units.mjs` for the game logic, `ref-page.js`
   for drawing and the page), and a check that the two agree (`check-ref-units.mjs`). The sheet's examples were
   computed from `ref-units.mjs` with an early prototype tool that is not included; `build/dryrun.py` checks every
   example against the reference in the real kernel.
3. **A strict harness** (`harness/harness.mjs`): loads a page in headless Chromium and replays scripted and random
   play against the oracle after every action: 39 required checks and 2 advisory ones. `harness/golden.html` is a
   page written directly from the rules (not from the sheet), used to check the harness itself.
4. **A build loop** (`../build_loop.py` and `build/`): the commands below compile the sheet, run it against an
   Ollama server, rebuild keeping every unit that passed, and grade the page. `build/dryrun.py` runs the whole
   build with the reference standing in for the model, so the loop can be checked with no model.
   `build/verbatim.py` measures how much of a page appears word for word in its sheet.
5. **Results** (`results/`): the two pages local models built on 2026-10-04, both 39/39 (see `results/README.md`).

## What the page must do

One self-contained HTML file (inline style and script, no external resource): a 10 x 22 board (the top 2 rows
hidden) and a side panel on two canvases; the seven pieces I, O, T, S, Z, J, L with fixed colours; a shuffled
7-piece bag from a seeded PRNG (mulberry32, given as code) so a game is a pure function of its seed and inputs;
rotation both ways with the standard wall-kick tables; hold (once per piece); a queue of upcoming pieces; gravity
by level (`level = 1 + floor(lines / 10)`, interval `max(1, round((0.8 - (level - 1) * 0.007)^(level - 1) * 1000))`
ms); a 500 ms lock delay that a move or rotation while resting restarts at most 15 times; scoring of 100, 300, 500
and 800 times the level for 1-4 lines, 1 per soft-drop row and 2 per hard-drop row; pause; game over when a new
piece does not fit; the keyboard (arrows, Space, Z/X/Up, C/Shift, P, R; keys with Ctrl, Alt or Meta are left to the
browser); and a test API, `window.tetris` with `reset(seed)`, `input(action)`, `tick(ms)` and `state()`, that the
harness drives. The sheet states every rule exactly, as numbered steps and expressions; read it for the details.

The harness checks the page's file (size, no external URL), the test API and its state's exact shape and types, the
bag and spawns on four seeds, moves, rotations and wall kicks, hold, soft-drop scoring, line clears and scoring over
two long played games, line clears inside ticks, three random input games, pause, gravity at levels 1 and 2, the
lock delay and its 15 restarts, one long tick against many 1 ms ticks, game over and the frozen state after it, the
keyboard, a drawn canvas, restart, no page errors and no network request. The two advisory checks want the score
and "GAME OVER" as page text, which a canvas-only page does not have.

## Layout

| path | what it is |
|---|---|
| `sheets/tetris.sheet.md` | the spec sheet: 25 units, 120 examples |
| `reference/reference.mjs` | the oracle: the rules as one `Game` class (pure logic, no page) |
| `reference/ref-units.mjs` | the reference written as the sheet's logic units, in sheet order. Models never see it |
| `reference/ref-page.js` | the reference drawing and page units (`drawCell` ... `startGame`), as plain script |
| `reference/check-ref-units.mjs` | `ref-units.mjs` against the oracle on 300 seeded random games |
| `harness/harness.mjs` | the strict harness (headless Chromium through Playwright) |
| `harness/golden.html` | a page written straight from the rules; it must pass the harness |
| `build/dryrun.py` | the compiled build in the real kernel with the reference as a stand-in answer (no model) |
| `build/grade.sh` | saves a build's `tetris.html` from its run folder and grades it with the harness |
| `build/verbatim.py` | how much of a page's script appears word for word in its sheet |
| `../build_loop.py` | one round of a real build: compile the sheet, run it against Ollama, keep what passed (shared with the Kirby kit) |
| `results/` | the two model-built pages and their record |

## Requirements

- Python 3.12 and Node.js 22, and Linux 6.7 or newer for the kernel's JavaScript sandbox (see `../kirby/README.md`).
- For the harness: Playwright and its Chromium (`npm install playwright` in a folder on Node's module path, then
  `npx playwright install chromium`), or `PLAYWRIGHT_MODULE=/path/to/node_modules/playwright/index.mjs`.
- For a real build: an [Ollama](https://ollama.com) server and the models you name.

Commands below run from the repository root.

## Checks that need no model

Measured on 2026-10-11 in this repository (Node.js 22.17.0, Playwright 1.63 with its Chromium, a heavily loaded
6-core machine):

| command | result |
|---|---|
| `node kits/tetris/reference/check-ref-units.mjs` | `ref-units agrees with the oracle: 300 seeds, 120000 steps` |
| `python3 -m symblic.spec.sheets check kits/tetris/sheets/tetris.sheet.md` | `ok` |
| `python3 -m symblic.spec.sheets compile kits/tetris/sheets/tetris.sheet.md --by ollama:qwen3:4b-instruct` | a program `Build tetris.html` that the kernel's static check accepts (56 exact statements, 25 open: the model asks) |
| `python3 kits/tetris/build/dryrun.py --dir /tmp/tetris-dry /tmp/tetris-dry.html` | `status done`, 25 of 25 units asked and accepted: every example of the sheet holds for the reference |
| `kits/tetris/build/grade.sh /tmp/tetris-dry` | `39/39 required checks passed; 0/2 advisory` |
| `node kits/tetris/harness/harness.mjs kits/tetris/results/PAGE.html` | `39/39 required checks passed; 0/2 advisory` for both result pages |
| `node kits/tetris/harness/harness.mjs kits/tetris/harness/golden.html` | `39/39 required checks passed; 1/2 advisory`. One of two runs on the loaded machine failed `real-time gravity before any reset()`, the one check that depends on wall-clock time (it waits 3 s for the piece to fall); the other run passed it |

## Building it against an Ollama server

The steps are the Kirby kit's (`../kirby/README.md`, "Building it against an Ollama server"), with this sheet:

```
ollama pull qwen3:4b-instruct; ollama pull phi4-mini; ollama pull gemma3:4b
python3 -m symblic.spec.sheets check kits/tetris/sheets/tetris.sheet.md                   # no model
python3 kits/build_loop.py kits/tetris/sheets/tetris.sheet.md --dir /tmp/tetris-build/run1 \
  --by ollama:qwen3:4b-instruct --by ollama:phi4-mini --by ollama:gemma3:4b \
  --samples 5 --retries 3 --rounds 3 --num-predict 4096 --call-timeout 900
python3 -m symblic.spec.sheets diagnose kits/tetris/sheets/tetris.sheet.md --run /tmp/tetris-build/run1
python3 kits/build_loop.py kits/tetris/sheets/tetris.sheet.md --dir /tmp/tetris-build/run2 \
  --by ... --keep /tmp/tetris-build/run1                       # the next round keeps what passed
kits/tetris/build/grade.sh /tmp/tetris-build/run1
```

`SYMBLIC_OLLAMA_HOSTS` names the Ollama servers (default `127.0.0.1:11434`); `symblic/providers/applicators.py`
documents it. Nothing in this repository was run against a model while it was being prepared for publication.

## What made 4B models succeed, and what a pass means

The sheet went through about a dozen rewordings on 2026-10-03/04 before local 4B models could build it. What made
the difference: numbered steps with exact expressions; lookup tables for mappings (the key table above); units of
2-40 lines (drawing was split into four units); units that are declarations only, with the page making the call;
and prompts that never say "define" and that name the units an answer must not copy. The kernel gained checks
along the way: a name declared twice fails at once ("defines f again"), and error lines are quoted back to the
model.

A unit that passes gives every value its examples list, after the units before it; that is all acceptance shows. The
harness is the independent test of the whole page: it compares every state with the oracle over many games. The
oracle, the reference, the sheet and the harness were written by AI coding agents from one prose description, so a
misreading shared by all of them would not be caught. Not covered: how the page looks, real key timing, and touch
input (there is none).

Since the 2026-10-04 builds the sheet changed in one place: the unit `refill(g)` lost its line `Uses: g.rng,
g.queue` (those are fields of the game state, not units). Every example is unchanged.

## How this kit was made

The rules, the oracle, the harness, the golden page, the sheet and the reference units were written by AI coding
agents (Claude, by Anthropic) working in a terminal for the project's author on 2026-10-03 and 2026-10-04. The two
pages in `results/` were written unit by unit by the local models named in `results/README.md`; no person wrote game
code by hand. The kit was moved into this repository on 2026-10-11 and every check above was run again here.
