# Kirby kit: a complete platformer level, written unit by unit by small local models

> **A tribute, not an official product.** Kirby, waddle-dees and bronto-burts are characters owned by Nintendo and
> HAL Laboratory. This kit is an unofficial fan tribute used as a programming test; it is not affiliated with,
> endorsed by or sponsored by Nintendo, HAL Laboratory or anyone else. It contains no artwork, sound, level data or
> code from any game: the page draws circles, rectangles and text on a canvas, and the level below was written for
> this kit.

This folder is a complete *kit* for one Symblic build (see `symblic/spec/README.md` for spec sheets in general):

1. **A specification sheet** (`sheets/`): the file `kirby.html` described as 39 small units of JavaScript, each with
   a contract in prose and examples (`call ==> expected JSON`). Symblic compiles the sheet into a program that asks a
   model for one unit at a time in a fresh context, tests each answer against the unit's examples in a sandbox, retries
   with the failing examples as feedback, and assembles the page from passing units only. The same 39 units come in
   three wordings, for 4B, 2-3B and 1B models.
2. **A deterministic reference** (`reference/`): the same 39 units written out (`ref-units.mjs`), a tool that computes
   every example of the sheets from it (so no expected value is typed by hand), an independent oracle written from
   the feature contract below, and a check that the two agree.
3. **A strict harness** (`harness/`): grades an assembled page in Node.js alone (no browser) by replaying scripted and
   random play against the reference: 68 required checks. Two mutation tests check the checkers: 60 broken pages
   the harness must reject, and 90 plausible small-model slips the sheet's examples must reject.
4. **A build loop** (`../build_loop.py` and `build/`): the commands below compile the sheet, run it against an
   Ollama server, diagnose a unit that stalls, rebuild keeping every unit that passed, and grade the page.
   `build/dryrun.py` runs the whole build in the real kernel with the reference standing in for the model, so the
   loop can be checked with no model.
5. **Results** (`results/`): seven pages that local models built on 2026-10-11. All seven pass 68/68; see
   `results/README.md` for who built each one, at what cost.

## Layout

| path | what it is |
|---|---|
| `sheets/kirby.sheet.md` | the spec sheet for 4B models: 39 units, 229 examples, `Used units shown as: signatures`, `Answers normalized: yes`, the level map as a `Given: yes` unit |
| `sheets/kirby-3b.sheet.md` | the same units reworded for 2-3B models: every contract is 3-8 numbered steps naming the exact loop, condition and return, plus one "never" sentence for the slip small models make there |
| `sheets/kirby-1b.sheet.md` | the same units for 1B and 0.5B models: every contract is `Write exactly this code:` and the unit's reference code |
| `reference/ref-units.mjs` | the reference: the 45 names of the 39 units as plain ES2020 declarations, in sheet order. Models never see it |
| `reference/fill-sheet.mjs` | `fill SHEET` computes every `call ==> ?` example with the reference; `check SHEET` recomputes all of them. Each example runs as the kernel runs it: a fresh `vm` context, the unit's test setup and the units up to that one, each as its own script |
| `reference/check-ref.mjs` | checks the reference against the contract: an independent oracle (one class, written from this README), the contract's numbers, the level's rules, and every example of the sheet |
| `reference/assemble-ref.mjs` | assembles `kirby.html` from the reference exactly as a build assembles accepted units |
| `harness/harness.mjs` | the strict harness for an assembled page (68 required checks; Node.js only) |
| `harness/mutants.mjs` | the harness's own test: 60 pages, each with one rule broken, must all be rejected |
| `harness/sheet-mutants.mjs` | the sheet's own test: 90 plausible slips (a wrong constant, a swapped order, an off-by-one), each applied to one unit, must each fail that unit's examples, so the kernel rejects them during the build instead of the harness after it |
| `build/dryrun.py` | runs the compiled build in the real kernel with the reference as a stand-in answer (no model); `--sheet` picks a variant, `--dir` keeps the run folder for `grade.sh` |
| `build/grade.sh` | saves a build's `kirby.html` from its run folder and grades it with the harness |
| `../build_loop.py` | one round of a real build: compile the sheet, run it against Ollama, keep what passed (shared with the Tetris kit) |
| `results/` | the seven model-built pages and their record |

## Requirements

- Python 3.12 and Node.js 22 (`node` on `PATH`, or `SYMBLIC_NODE=/path/to/node` for the kernel's JavaScript checks).
- Linux 6.7 or newer: the kernel runs model-written JavaScript in a sandbox that uses Landlock network rules
  (`symblic/js/check.py`). Without it every JavaScript check is "unavailable" and no unit can pass.
- For a real build: an [Ollama](https://ollama.com) server and the models you name (`ollama pull qwen3:4b-instruct`).

Commands below run from the repository root.

## Checks that need no model

Measured on 2026-10-11 in this repository (Node.js 22.17.0, Python 3.12, a 6-core machine that was heavily loaded
by other work at the time, so the wall times are pessimistic):

| command | result |
|---|---|
| `node kits/kirby/reference/check-ref.mjs` | `check-ref 15/15`: the oracle and the reference agree on 180 000 random actions (300 seeds) and on 20 932 actions of the harness's travelling player (20 seeds, all 20 reach the door); 4 min wall, 72 s CPU |
| `node kits/kirby/reference/fill-sheet.mjs check kits/kirby/sheets/kirby.sheet.md` (and `kirby-3b`, `kirby-1b`) | `39 units, 229 examples, 0 differing from the reference, 0 unfilled` for each of the three sheets |
| `node kits/kirby/reference/assemble-ref.mjs /tmp/kirby-ref.html` then `node kits/kirby/harness/harness.mjs /tmp/kirby-ref.html` | `required 68/68` (about 20 000 page states compared with the reference) |
| `node kits/kirby/harness/sheet-mutants.mjs` | `sheet mutants caught by their unit's examples: 90/90` |
| `python3 -m symblic.spec.sheets check kits/kirby/sheets/kirby.sheet.md` (and `kirby-3b`, `kirby-1b`) | `ok` for each |
| `python3 -m symblic.spec.sheets compile kits/kirby/sheets/kirby.sheet.md --by ollama:qwen3:4b-instruct` | a program `Build kirby.html` that the kernel's static check accepts: 85 exact statements and 38 open ones (the model asks; the 39th unit, the level, is given by the sheet) |
| `python3 kits/kirby/build/dryrun.py --dir /tmp/kirby-dry /tmp/kirby-dry.html` (and `--sheet` for each variant) | `status done`, 38 of 39 units asked and accepted plus the given level; for each of the three sheets the page is byte-identical to `assemble-ref.mjs`'s |
| `kits/kirby/build/grade.sh /tmp/kirby-dry` | `required 68/68` on the dry run's page |
| `DASH_TEST=1 python3 -m unittest discover -s tests/kits -t .` | 4 tests OK: a round of `kits/build_loop.py` with a fake model writes its records, a `--keep` round asks no model, and `fill-sheet.mjs check` holds for this kit's 4B sheet |
| `node kits/kirby/reference/assemble-ref.mjs /tmp/kirby-ref.html` then `node kits/kirby/harness/mutants.mjs /tmp/kirby-ref.html /tmp/kirby-mutants` | `mutants rejected 60/60`: every page with one rule broken fails the harness (21 min wall, two harness processes at a time) |

## Building it against an Ollama server

A build asks real models. Nothing in this repository was run against a model while it was being prepared for
publication; the commands are the ones the result pages were built with, translated to this repository's tools.

1. **Start Ollama and pull the models.** Any machine you can reach over HTTP works. One model per machine is
   faster: the candidates of a round are asked at the same time.

   ```
   ollama pull qwen3:4b-instruct
   ollama pull gemma3:4b
   export SYMBLIC_OLLAMA_HOSTS=127.0.0.1:11434          # the default; list more servers with commas
   ```

   With several servers, name them (`SYMBLIC_OLLAMA_HOSTS="127.0.0.1:11434,gpu=192.0.2.10:11434"`) and pin a model
   to one with `--by ollama:gemma3:4b@gpu`. `symblic/providers/applicators.py` documents every option.

2. **Check the sheet and look at the program** (deterministic; no model is called). Pick the sheet that fits your
   models:

   ```
   python3 -m symblic.spec.sheets check kits/kirby/sheets/kirby.sheet.md
   python3 -m symblic.spec.sheets compile kits/kirby/sheets/kirby.sheet.md \
     --by ollama:qwen3:4b-instruct --by ollama:gemma3:4b --samples 2 --retries 3 --rounds 2 | less
   ```

   The program asks for each unit with `route=search`: a round asks `--samples` candidates at once (the models
   take turns, so with two models and `--samples 2` each answers once), each candidate is repaired up to
   `--retries` times with its own failing examples, and a round in which none passes starts a fresh one, up to
   `--rounds`. The accepted answer is the passing candidate with the fewest attempts (ties go to the earlier
   candidate), never simply the first to arrive, so the same replies always select the same answer.

3. **Run a round** with `kits/build_loop.py`: it compiles the sheet, writes the program into a new run folder and
   runs it, with ceilings on every local call so a model that loops cannot hold a machine for long:

   ```
   python3 kits/build_loop.py kits/kirby/sheets/kirby.sheet.md --dir /tmp/kirby-build/run1 \
     --by ollama:qwen3:4b-instruct --by ollama:gemma3:4b --samples 2 --retries 3 --rounds 2 \
     --num-predict 2048 --call-timeout 600
   ```

   The run folder keeps the program, every model call and every accepted unit. A stopped run continues with
   `python3 kits/build_loop.py --resume /tmp/kirby-build/run1` (recorded calls are not asked again).

4. **When a unit stalls, diagnose the sheet, not the models**, then start the next round keeping what passed:

   ```
   python3 -m symblic.spec.sheets diagnose kits/kirby/sheets/kirby.sheet.md --run /tmp/kirby-build/run1
   python3 kits/build_loop.py kits/kirby/sheets/kirby.sheet.md --dir /tmp/kirby-build/run2 \
     --by ollama:qwen3:4b-instruct --by ollama:gemma3:4b --keep /tmp/kirby-build/run1 [--redo NAME]
   ```

   `diagnose` tests every model reply again and groups the failures by the first example each reply fails: many
   replies from different models failing one example the same way usually point at the sheet's wording. `--keep`
   turns the leading units that run accepted into fixed text (still tested, never asked again). Keep from the best
   run so far, not simply the last one: a round that accepted nothing would otherwise restart from scratch.

   After rewording a unit, mark changed or new examples `==> ?` and run `fill-sheet.mjs fill`, `check-ref.mjs`,
   `sheet-mutants.mjs` and `build/dryrun.py` again before the next round.

5. **Grade the page:**

   ```
   kits/kirby/build/grade.sh /tmp/kirby-build/run1
   ```

   It writes `run1/kirby.html` and `run1/kirby.grade.json`; a correct build prints `required 68/68`.

**What it costs** (measured on 2026-10-11, models running in Ollama on CPU-only machines, one model per machine):
78 to 124 model calls per page (counting an earlier round whose accepted units a build kept) and 18 minutes to 2.3
hours of wall time per build. The lighter the model, the more
of the code the sheet has to dictate: the 0.5B builds used the exact-code sheet. `results/README.md` has every run.

## The feature contract: what the level must do

The sheets state every rule below as unit steps; this is the same contract in one place, with the numbers the harness and `reference/check-ref.mjs` test.

### The level

12 rows x 64 columns of 32 x 32 px tiles (384 x 2048 px), row 0 at the top. The view is 640 x 384 px (20 columns).

```
................................................................
................................................................
.............................................*..................
..........................................B.....................
.........................***....................................
........................=====...................................
................................................................
...............**..................W............................
..............====...............######.....B...................
....***..#..W.....W........^^....######.............W...**...D..
####################....#######################..###############
####################....#######################..###############
```

| letter | meaning |
|---|---|
| `.` | air |
| `#` | ground: solid from every side |
| `=` | one-way platform: holds Kirby only when he comes down onto it from above; he jumps up through it and walks through it |
| `^` | spike: touching it hurts |
| `*` | star: +100 when touched, then air (counted once) |
| `D` | door: touching it completes the level |
| `W`, `B` | where a waddle-dee or a bronto-burt starts; the tile itself is air |

Outside the grid: the left and right edges are walls (`#`), the top is a ceiling (`#`), below the bottom is open (a
pit). The level holds 11 stars, 4 waddle-dees, 2 bronto-burts, a one-tile wall (column 9), two pits (columns 20-23,
four tiles, too wide for a plain jump; columns 47-48), two spikes (columns 27-28), a low platform (row 8, reachable
by a jump), a high platform (row 5, reachable only by floating), a 6 x 2 plateau (columns 33-38) and the door
(row 9, column 61).

### Units, time and determinism

- Positions are pixels, x to the right and y down. One step is one frame; speeds are pixels per step.
- `tick(g, ms)` adds `ms * 60` to an accumulator and runs one step per 1000: exactly 60 steps per second, the
  remainder kept for the next call (16 ms: no step yet; 1 ms more: the first step; 1000 ms: 60 steps).
- Every constant is a multiple of 1/16, so positions and speeds stay exact binary fractions and any order of the same
  additions gives the same bits. The one transcendental value, the bronto-burt's sine, is one fixed expression.
- The seeded PRNG is mulberry32, given as code. It is used only when a game starts: for each enemy, top row first and
  left to right, `dir = rng() < 0.5 ? -1 : 1`, then `t = Math.floor(rng() * 64)`.
- So the whole game is a pure function of the seed, the inputs and the tick sizes.

### Kirby (a 24 x 24 box)

| rule | numbers |
|---|---|
| start | x 40, y 296 (standing on the ground in column 1), facing right, 6 HP, ability `none` |
| walk | +0.125 px/step per step toward the held direction, at most 2 px/step (16 steps to full speed); no key, both keys, or inhaling: friction 0.25 px/step per step to 0 (8 steps) |
| fall | gravity +0.25 px/step per step, at most 6 px/step; also on the ground (he lands again each step) |
| jump | on the ground: vy -6, rises 69 px, 48 steps in the air |
| float | the jump key in the air (not full, float time left): inflate and flap, vy -2 (about 31 px of lift); every press while floating flaps again; floating gravity +0.0625, at most 1 px/step; 360 floating steps (6 s) per time in the air, then he deflates and cannot inflate again until he lands (landing resets the count) |
| exhale | the inhale key while floating: stop floating, fall with normal gravity |
| inhale | hold the inhale key (not floating, not full); every live enemy with 0 < dx <= 64 px ahead (dx between left edges, in the facing direction) and less than 32 px above or below is pulled 2 px per step; when dx <= 24 it is inside: `full` is its kind, +200; one enemy at a time; Kirby cannot walk while inhaling |
| swallow | full: ability from the enemy, waddle-dee `none`, bronto-burt `wing`; `wing` jumps start at vy -8.5: 140.25 px, 2.03 times the plain jump |
| spit | full: a 16 x 16 star at (x + 24 or x - 16, y + 4), flying 6 px/step the way he faces; it defeats the first live enemy it touches (+200) and vanishes; it vanishes when its middle is in a `#` tile (the level edges are walls) |
| full | a full Kirby cannot float or inhale; he walks and jumps normally |
| damage | touching an enemy (the enemy is defeated, no score) or a spike: -1 HP, knockback vx = -2 x facing, vy = -3, floating stops, then 90 steps (1.5 s) without damage, blinking |
| end | 0 HP is game over; falling below the level (y > 384) sets HP 0, game over; HP never goes below 0; touching the door completes the level; both freeze the game (steps and inputs change nothing) |
| camera | `cam = clamp(floor(x + 12 - 320), 0, 1408)`: his middle in the middle of the view, never past either edge |

### Enemies (24 x 24 boxes)

- Waddle-dee: walks 0.5 px/step and turns around, without moving that step, when the tile at its front edge is `#`
  (a wall or the level's edge) or the tile under its front edge is neither `#` nor `=` (a ledge). In this level they
  patrol x 320-616 (two of them), 1056-1224 (on the plateau) and 1568-2024.
- Bronto-burt: flies through tiles; x changes by `dir` each step and `dir` flips whenever its phase `t` reaches a
  multiple of 128; `y = baseY + round(24 * sin(t / 16))`.

### One step, in order

1. Nothing when the game is over or complete.
2. `frame` +1; the invulnerability count -1.
3. `inhaling` = inhale held, not floating, not full.
4. Walk, then fall (the float count first), then move sideways (stopped by `#`), then up or down (landing on `#`, or on
   `=` from above; landing ends floating and resets the float count; the ceiling stops his head).
5. Below the level: HP 0, game over, stop.
6. Enemies move; then, while inhaling, the pull.
7. The spit star moves (and may hit); then enemy bumps; then the tiles he touches (stars, spikes, door).
8. The camera follows.

### Input, keys and the page

- `input(g, action, pressed)`: `left`, `right` and `inhale` are held keys; `jump`, `swallow`, `spit` act once, when
  pressed. Nothing is accepted after the end.
- Keys: arrows or A/D walk; Space, W, Z or Up jump (and float); X inhales (hold); S or Down swallows; C spits; R starts
  a new game. Game keys call `preventDefault` (the page never scrolls); a repeating keydown does nothing; keys with
  Ctrl, Alt or Meta are left to the browser.
- `window.kirby` is the test API: `reset(seed)` (a new game; animation frames stop moving it), `input(action,
  pressed)`, `tick(ms)`, `state()`. Until the first reset the game runs in real time from `requestAnimationFrame`,
  each frame counting at most 100 ms.
- `state()` is a new object: `frame, score, cam, stars` (left), `over, won`, `kirby` (13 fields), `enemies`
  (`kind, x, y, dir, t, alive`), `shot` (`x, y, dir` or null).
- Drawing uses canvas primitives only, on a 640 x 384 canvas: a sky, the visible tiles (brown ground with a grass top,
  plank platforms, grey spike triangles, gold star diamonds, a brown door), the enemies (a waddle-dee is an orange ball
  with feet and a pale face; a bronto-burt a pink ball with white wings), the spit star, Kirby (a pink `#ff9ebd`
  ball of radius 12, 15 when floating, 14 when full, red `#d81e3a` feet, two eyes, a mouth that opens wide while
  inhaling, blinking while invulnerable) and the HUD (6 HP squares, `SCORE`, `ABILITY`, `GAME OVER` or
  `LEVEL COMPLETE`). No artwork from any game is used: everything is circles, rectangles and text.

## Three wordings for three model sizes

All three sheets have the same 39 units in the same order, and their title, intro, both directives, `## Shared`,
every `## Unit` heading, `Uses:` line, test setup, `Examples:` block and `## Assemble` section are byte-identical
(`fill-sheet.mjs check` recomputes the same 229 examples in each). Only the contracts differ:

- `kirby.sheet.md` (4B models such as qwen3:4b-instruct, gemma3:4b): units of 3-25 lines, every rule as numbered
  steps with the exact expressions, lookup tables for mappings, and the functions a unit calls described in its own
  text. With `Used units shown as: signatures` a prompt names the units a unit may call instead of pasting their
  code (small models copy pasted code instead of calling it).
- `kirby-3b.sheet.md` (2-3B models such as qwen2.5-coder:3b, granite3.3:2b): every contract is 3-8 numbered steps
  that name the reference's exact loop, condition and return, plus one "never" sentence for the slip small models
  make there (a `row` array shared between rows, a helper's body copied instead of called, an off-by-one at an edge,
  the input changed, the wrong return type). No contract exceeds 94 words, counting an inline code span as one word.
- `kirby-1b.sheet.md` (gemma3:1b, llama3.2:1b, qwen2.5:0.5b): every contract is `Write exactly this code:` and the
  unit's code from `ref-units.mjs`, byte for byte. A unit whose contract says that is compiled with a retry reason
  that shows the model the lines where its answer departs from the given code (the kernel builtin `diff_lines`).

In all three, the level map (`LEVEL`, 12 strings of 64 characters) is a `Given: yes` unit: the sheet supplies its
code, the kernel tests it like any other unit, and no model is asked to retype it (1B models dropped characters
from a row). `Answers normalized: yes` makes the kernel take the fenced block that declares the unit, restore a
dropped `function` keyword and cut a model's copies of earlier units before testing (`symblic/js/normalize.py`).

Units most likely to cost a 4B model repairs, and what the 4B sheet does about each:

| unit | why it is hard | in the sheet |
|---|---|---|
| `LEVEL` | 12 strings of 64 characters copied exactly; a dot miscounted shifts a column | given by the sheet (`Given: yes`); one example is the whole level as JSON |
| `moveY(g)` | a compound landing condition, five assignments, two branches | the condition is given verbatim; 10 examples cover landing, the one-way rule from above and below, the ceiling and a pit |
| `step(g)` | ten calls in a fixed order, two early returns | numbered steps; two examples pin the order (enemies before the pull; the star before bumps before tiles) |
| `startGame()` | closures, four methods, two listeners, a frame loop (25 lines) | numbered steps with the code; the method syntax that fails is named; key handling was moved to `handleKey` |
| `drawTile(ctx, ch, x, y)` | five branches of canvas calls (14 lines) | a table with each branch's code, one line per branch; exact call lists as examples |
| `input`, `handleKey` | order of checks (end, exhale, press versus release, repeat, restart) | numbered steps; examples for each order |
| `parseLevel`, `touchTiles`, `snapshot` | nested loops, the PRNG call order, exact field lists | steps, field lists and the order stated |

Finer decompositions (about 85 units of 1-6 lines for 2-3B models, about 110 for 1B) were planned and are not
written; the three 39-unit wordings above were enough for every result in `results/`. A finer ladder would keep this
sheet's behaviour exactly, so the same reference (extended with the new helper names), the same harness and the same
68 checks would grade it.

## What a passing build establishes, and what it does not

- A unit that passes gives every value its examples list, after the units before it. That is all a unit's
  acceptance shows. In an earlier study with a different, 37-unit sheet, a llama3.2:1b build passed all 37 units
  and still scored 243 of 500 on that sheet's whole-file harness. `sheet-mutants.mjs` measures how much this sheet's
  examples pin: 90 of 90 planted slips fail their unit. Its first run found four `step` slips the examples let
  through (the enemies moved after the pull, the pit test after the enemies, the axis order at a block's corner, the
  invulnerability count at the end of the step); the `step` examples now pin all four. Slips outside that list can
  still pass a unit and are left to the harness.
- The harness compares the whole page with the reference over scripted and random play (about 20 000 states) and
  asserts the contract's numbers on the page's own states. The reference agrees with an independent oracle on about
  200 000 actions and with the contract's numbers. The oracle, the reference, the sheet and the harness were written
  by the same author (an AI coding agent, see below), so a misreading of the contract shared by all four would not
  be caught; the contract above is the place to review.
- Not covered: a real browser (the harness's canvas is a recording fake, so pixels, fonts, layout and scaling are
  not seen), real keyboard focus and key timing, the feel of real-time play at the display's frame rate, touch
  controls (there are none), and how the drawing looks.
- The white-box checks call the units' own names (`newGame`, `pull`, `drawKirby` ...); a page built from these
  sheets has them all, a page written another way would not.

## How this kit was made

Everything in this folder except the pages in `results/` was written by an AI coding agent (Claude, by Anthropic)
working in a terminal for the project's author, on 2026-10-11: the feature contract, the three sheets, the
reference, the oracle, the harness and its mutation tests. The pages in `results/` were written unit by
unit by the local models named in `results/README.md`; the kernel assembled them from the units that passed. No
person wrote the game code by hand. The kit was moved into this repository on 2026-10-11 and every check in the
table above was run again here.
