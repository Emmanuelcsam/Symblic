# Light local models through Symblic: beta record (2026-10-11)

> **Working log of 2026-10-11, frozen at publication.** It was written while the trials ran, so "run pending" and
> "is running" describe that moment; later rows and sections record what happened. Paths under `~/.local/state/`
> and `fleet_runner_data/`, the `kirby-kit/` folder and its `grade.py` were the original host's private stores and
> tools and are not included: the published kit is [../../kits/kirby/](../../kits/kirby/README.md), graded by
> `kits/kirby/build/grade.sh`. Clock times are the host's local time.

Operator's rule for this record: every trial below runs a LOCAL Ollama model on a worker node through the kernel's admitted
path (`ollama:MODEL@NODE`); no cloud or CLI agent takes part. A pass is a code verdict (js_test examples, the
harness), never a model's claim. Failures are development input: each one names the fix it produced.

## Ladder on the 4-unit mini sheet (Tetris `SHAPES, COLORS`, `cellsOf`, `emptyBoard`, `fits`)

| model @ node | sheet variant | units accepted | calls | what happened | fix it produced |
|---|---|---|---|---|---|
| qwen3:4b-instruct @ node-a | plain | 4 / 4 | 4 | every unit first try (236 s for `emptyBoard`) | none needed |
| qwen2.5-coder:3b @ node-f | plain | 1 / 4 | 4 | `cellsOf` returns the rotation-1 cells for rot 0; every retry byte-identical at temperature 0 | varied regeneration (below); rerun pending |
| gemma3:1b @ node-i | plain | 0 / 4 | 3 | `SHAPES, COLORS` correct, then the model kept generating: the constants again, a renamed copy, `function f()() {` until the token limit; unparseable | junk-tail cut in the normalizer (below) |
| gemma3:1b @ node-i | `Answers normalized: yes` + signatures | 0 / 4 | 3 | same (the normalizer could not parse the tail) | same |
| gemma3:1b @ node-i | same, after the junk cut | 1 / 4 | 5 | `SHAPES, COLORS` accepted (first 1B unit); `cellsOf` returns `[]`: a 1B cannot compose "turn rot times" from the contract (the atomic study's finding) | exact-code unit variant (level D); run pending |
| gemma3:1b @ node-i | `cellsOf` given as exact code | 3 / 4 | 7 | `cellsOf` reproduced exactly, `emptyBoard` written from its contract; `fits` (a loop over `cellsOf` with bounds) wrong four times, identical at temperature 0.6 | `fits` as exact code too |
| gemma3:1b @ node-i | `cellsOf` and `fits` exact | 4 / 4 | 4 | every unit first try; `pieces.html` assembled (1,960 chars) | none: the 1B frontier on this sheet is two units from contracts plus two reproduced |
| qwen2.5:0.5b @ node-a | `cellsOf` and `fits` exact | 0 / 4 | 4 | the table unit came back as `function SHAPES() { return {...} }` without the `n` field, four times | every unit exact for the 0.5B rung (run pending) |
| qwen2.5-coder:3b @ node-f | plain, varied retries live | 1 / 4 | 5 | the same `cellsOf` answer four times even with temperature 0.6 requested | numbered-steps contract for `cellsOf` (run pending) |
| qwen2.5-coder:3b @ node-f | `cellsOf` as numbered steps | 3 / 4 | 7 | `cellsOf` fixed by wording alone; `fits` passes 4 of 9 examples (right and bottom bounds missed) | `fits` as numbered steps (run pending) |
| qwen2.5-coder:3b @ node-f | `cellsOf` and `fits` as numbered steps | 3 / 4 | 7 | `fits` passes 8 of 9: for the O piece at column -1 it returns the cells array instead of `false`, four identical times | the reply shows why: it pasted `cellsOf`'s shown code into `fits` (with its early `return cells` for O) instead of calling it, the documented small-model habit; `Used units shown as: signatures` for the 3B rung (run pending) |
| qwen2.5-coder:3b @ node-f | numbered steps + `Used units shown as: signatures` | 4 / 4 | 4 | every unit written from its contract first try; `pieces.html` assembled (1,690 chars) | none: the 3B rung needs steps and signatures, not exact code |
| granite3.3:2b @ node-f | numbered steps + signatures, normalization off | 1 / 4 | 5 | `cellsOf` redeclared `const SHAPES` (a copy of a name it was only shown) | same sheet with `Answers normalized: yes` |
| granite3.3:2b @ node-f | steps + signatures + normalized | 2 / 4 | 7 | the copied `SHAPES` is cut and `cellsOf` passes; `emptyBoard` builds 22 references to one row (`Array(22).fill(Array(10).fill(''))`) | a negative sentence in the contract naming that form |
| granite3.3:2b @ node-f | steps + signatures + normalized + a negative constraint on `emptyBoard` ("never `Array(22).fill(Array(10).fill(''))` or any form that reuses one row object", "a loop that pushes a fresh array for every row") | **4 / 4**, page assembled | 5 | one repair | the 2B rung assembles the page once the contract names the wrong form it likes |
| qwen2.5:0.5b @ node-a | every unit exact | 0 / 4 | 4 | reproduced the code, then junk functions and a second `function SHAPES` until the token limit, no closing fence; the normalizer kept the junk's `SHAPES` | junk starts at a late redeclaration of a unit name; unterminated fences accepted |
| qwen2.5:0.5b @ node-a | every unit exact, after those fixes | 4 / 4 | 4 | every unit first try; `pieces.html` assembled (1,856 chars) in 126 s | none: the 0.5B floor on this sheet is faithful reproduction |
| llama3.2:1b @ node-a | every unit exact | 4 / 4 | 5 | one repair, then the page assembled (1,739 chars) | none |

Reading (final for this sheet): 4B from plain contracts; 3B from contracts once the composition unit is numbered steps and used units are shown as signatures; 1B from two contracts plus two exact units; 0.5B and the other 1B from exact units only. On this sheet the lightest model's capability is the kernel's work plus the sheet's: with the junk cut it
writes the table-like and loop-like units from their contracts and reproduces the composition-heavy ones exactly
(which also proves the pipeline tolerates its output). A 3B writes three of four from contracts and fails the
rotation math; a 4B writes all four. The Kirby sheet therefore needs an exact-unit variant for the 1B rung and
contract units sized for 3B-4B.

Verified in the launcher's own records (`fleet_runner_data/runs/r_*/run.json`, node-f and node-i, 02:22-02:25): the varied
repairs ran with temperature 0.6 and seeds 2007 and 5007, and both small models still returned the same code. So the
sampling lever is real but weak at this size; the wording and the examples are the levers that move a 1B or 3B.

## Beta matrix, batch 1 (`symblic/bench/local_beta.py`, 02:01 to 02:40 host local time, node-b and node-d, not on the host)

| lane | qwen3:4b-instruct @ node-d | gemma3:1b @ node-b |
|---|---|---|
| spec sheet: markdown, 13 units | 1/1 (13 units, 28 calls, 1777 s, whole page 500/500 random documents) | 0/1 (stops at unit 1 `escapeHtml`: `a &amp;amp b`) |
| native .sym typed asks (3 fixtures) | 3/3 | 1/3 (word problem 3 instead of 44; counts six a's in "banana", every attempt) |
| local web research (a DOI's title) | 1/1 (read the DOI page, quoted the exact title) | 0/1 (searched for the journal, answered a blog title) |
| English statement `change` (smoke) | not run | 0/1 (answered 50 three times) |
| delegate template `classify-complaint` (smoke) | not run | 1/1 |

Peak worker node temperature 73 °C. Ledger: `~/.local/state/symblic-local-beta-20261011/ledger.jsonl`. Batch 2 (the exact
and fine 37-unit sheets on 1B, 0.5B, 3B and 2B models, after the kernel fixes) is running.

## Autogen through the kernel lane, first run on a local model (02:35 onward, coder:3b on node-i)

`tools/symblic-task start --sheet` on the plain mini sheet, `--until-done --novelty-limit 2`: candidate a0 accepted one
unit and failed `cellsOf`; feedback regeneration a1 kept that unit (`--keep`) and failed the same unit; the plain
regeneration a2 the same; the stall rule then launched the split planner a3, which asked the 3B for two or three
smaller units with examples; the 3B answered with the examples themselves or the unit restated, never the required
sections, so the code validation refused it (`heads >= 2 and heads <= 3 and arrows >= heads * 2`); the policy then
re-planned on untried placements (a4 refused: no such model there; a5 ran) and the node ends `stuck`. Reading: every
mechanism fired as designed on a real local model, the verdicts were code's, and the honest limit surfaced: a 3B cannot
plan sub-units from free text. Next improvement for the lane: ask the planner for a typed JSON answer (a list of
`{name, contract, examples}`) that small models follow better, with the same code validation.

**How that run ended (03:52, still under the pre-restart code).** Ten attempts: three candidates/regenerations stopped at `cellsOf` (NO_OUTPUT), then the split planner rotated through node-i, node-arm (model absent: INFRASTRUCTURE), node-a, node-b, node-f (one unit section instead of 2-3) and node-h (model absent), and the statement ended `stuck`: "no eligible strategy remains … the split was refused". Two defects seen here are what the kernel-lane changes fix: the planner asked for free text and the 3B restated the unit or gave one section (now a typed JSON answer whose schema Ollama enforces), and placement rotated onto nodes without the model (now narrowed to worker nodes whose inventory lists it; an absent model counts as no try). A fresh run under the new code follows the host restart.

**Second run under the new code (`autogen-a5b0052a053503ef72253770`, 03:59 onward, coder:3b, primary node-f, the same plain-contract mini sheet).** Attempts a0 (fresh), a1 (regeneration with feedback) and a2 (another node, node-a) each accepted `SHAPES` and stopped at `cellsOf` (NO_OUTPUT). The stall then went to the typed JSON split planner (a3, node-a), whose answer was **accepted by code at 04:59**: it split `cellsOf(type, rot)` into `getPieceCells(type, rot)` and `handleO(type, rot)`, kept `cellsOf` with its own examples as the integration check, and the refined child sheet (`n0.0`, five units: the two sub-units, `cellsOf`, `emptyBoard`, `fits`) was compiled and started as attempt `n0.0-a0`. That is the first self-split a 3B model has produced that the kernel accepted (the previous run's free-text planner failed on every node). Whether the child's sub-units let the 3B pass `cellsOf` is the next measurement.

**How it went (05:00-07:22):** it did not. The child (5 units) accepted `SHAPES` and stalled on its own first sub-unit (`getPieceCells`, 6 calls per attempt, three attempts), was split again (8 units), again (13 units), and a fourth level was starting when I cancelled the run at 07:22 (17 attempts; the policy's `until_done` depth limit is 12). Every level accepted exactly the one unit its parent already had. Measurement: the typed split planner works mechanically on a 3B model (every split was accepted by code), but recursive decomposition does not lift a 3B over a unit it cannot write; the numbered-steps wording did (the 3B pair built the same `cellsOf` first try in the Kirby ladder's mini sheet). Change made from it: a split child now carries its parent's best evidence and is never split again unless it beats it (`unproductive_split`; tests, RECURSION.md, CONTRACTS.md), so a stuck leaf ends at depth 1 instead of 12.

**Third run, under the rule (`autogen-389ab28d8ad3aab86052bf5a`, 07:28-10:14):** the same path (three attempts stopped at `cellsOf`, a typed split accepted), but this child beat its parent (2 units: it wrote its own `getShapeCells`), so one more split was allowed; the grandchild stayed at 2 units through four attempts and the run ended `stuck` with the reason "this split made no progress over its parent (units 2 vs 2, checks 0 vs 0), so it is not split again". Depth 2 instead of the earlier run's 4 and the policy's 12, with every level that did add a unit still allowed. The rule holds live.

## Kernel changes made from these failures (all under tests)

1. **Varied regeneration** (`symblic/kernel/run.py`): when a retry's rejected answer is byte-identical to the previous one,
   the next ask runs at temperature 3/5 with a new seed (ensure-retry level, `_vary`; the in-sample repair loop too);
   requests carry plain numbers (an exact Fraction crashed the launcher's JSON). Test
   `tests/kernel/test_symblic_repair_variation.py`.
2. **Junk-tail cut** (`symblic.js.normalize.cut_trailing_junk`): with `Answers normalized: yes`, the lines from the first
   real syntax error onward are dropped while unit-name redeclarations are hidden behind placeholders, so the valid
   prefix becomes the answer and the existing duplicate rule still keeps the `function` form. Tests in
   `tests/js/test_symblic_js_normalize.py`.
3. Autogen: the `local` engine is admitted only for runs that ask for it, never placed or rotated onto the host, and
   gets a minimal prompt (`LOCAL_RULE`, `LOCAL_LOCK`) because the CLI agent guard admits 7168 tokens including tool
   schemas. Measured: a 1B model under the CLI agent echoes a tool schema and stops; the agent lane is not a path for tiny
   models. The kernel lane (spec sheets) is.

## What is being built on this evidence

- A Kirby-level spec sheet with a reference implementation and a strict harness, built by the 4B class first, then
  3B/2B, then 1B with exact units (`kits/kirby/sheets/kirby.sheet.md`, `kirby-kit/`).
- Autogen kernel attempts for `engine: local`: a statement is a spec sheet; attempts are kernel builds with
  incremental `--keep`; regeneration, stall-driven splits and stuck/resume operate at unit level.
- A beta matrix runner (`symblic/bench/local_beta.py`) that records every trial of every lane with every light model.

## Beta matrix, batch 2 (02:47-03:23, node-b and node-d only; `python3 symblic/bench/local_beta.py report --batch batch2-20261011`)

Settings: samples 1, retries 3, rounds 1, 2048 tokens and 900 s per call, one hour per build. Pass = the whole page passes the 500-document check.

| sheet | model @ worker node | result | units | calls | time |
|---|---|---|---|---|---|
| markdown exact (37 units) | gemma3:1b @ node-b | **pass**, 500/500 documents, all units first try | 37 / 37 | 37 | 508 s |
| markdown exact | qwen2.5:0.5b @ node-d | fail at unit 1 (`escapeHtml` escapes, then appends `.replace` calls that undo it; 4 byte-identical replies, 2 of 3 retries re-sampled) | 0 / 37 | 4 | 31 s |
| markdown fine | granite3.3:2b @ node-d | fail at `isOlBlock` (regex `^[0-9]+\.\.` needs two dots) | 22 / 37 | 26 | 881 s |
| markdown fine | qwen2.5-coder:3b @ node-b | no verdict: the kernel's JavaScript check of `codeBodyLines` ran past its limit while the host was overloaded (below) | 28 / 37 | 29 | 1641 s |
| markdown fine (rerun `batch2b-20261011`, 03:44-04:13, samples 2, retries 3, rounds 2, with the re-observation) | qwen2.5-coder:3b @ node-d | **pass**: 500/500 documents, plain 8/8; one unit needed a retry (`codeBodyLines`, re-sampled), 6 byte-identical repeated replies | 37 / 37 | 75 | 1744 s |

The runner now records the hashes of the script and kernel files per row, per-unit retry/re-sample/identical counts, the failed unit's first failing example and reply head, counts an inconclusive kernel check as no verdict, and `rejudge ID` re-reads a saved run.

## RESULT 05:50: the 3B rung built the Kirby level (harness 68/68)

Run `kirby-3b-r1` (`~/.local/state/symblic-kirby-20261011/runs/kirby-3b-r1`): `kirby-3b.sheet.md` (numbered steps, one "never" sentence per unit, `Used units shown as: signatures`, `Answers normalized: yes`), applicators `ollama:qwen2.5-coder:3b@node-b` and `ollama:granite3.3:2b@node-d` (samples 2, retries 3, rounds 2; 4096 tokens / 900 s per call), kernel on the host with the timeout re-observation.

| measure | value |
|---|---|
| units accepted | 39 of 39, one round, no `--keep` |
| model calls | 92 (47 granite3.3:2b, 45 qwen2.5-coder:3b) |
| units settled within the first pair of samples | 35 of 39 |
| units that needed more | `walk` (3 calls), `step` (3), `startGame` (3), `drawHud` (13: both models dropped the trailing `ctx.textAlign = 'left'` until a repair kept it; the sheet now makes that reset its own final step) |
| wall time | 4 990 s (83 min), 04:26 to 05:49 |
| page | 15 480 characters, `kits/kirby/results/kirby-3b-r1.html` |
| strict harness (`kirby-kit/harness.mjs`, 68 required checks, 20 369 page states against the reference) | **required 68/68**, graded by `grade.py` and again by hand from the saved copy |

The grading step of that round ran by hand: I edited `build.sh` while the round's bash was blocked in the build, bash resumed at a shifted byte offset and died with "unexpected EOF" after the run had finished. Lesson in the scripts' comments: never edit a running shell script; the running 4B lane's scripts were restored byte-for-byte, and new lanes use `build2.sh`/`loop2.sh`.

The 4B rung (`kirby-4b-r4`, qwen3:4b-instruct @ node-a + gemma3:4b @ node-i, plain contracts) was at 33 of 39 at the same time, slowed by sharing node-a with the autogen run and by gemma3:4b's habits that the sheet edits of 04:11-05:39 address (bare bodies, IIFEs, ignored tables, local accumulators, extra fields). The 1B rung (`kirby-1b.sheet.md`, gemma3:1b @ node-b + qwen2.5:0.5b @ node-d) started at 05:52.

## RESULT 06:12: the 4B rung built the Kirby level too (harness 68/68)

Run `kirby-4b-r4` (`kirby.sheet.md`, plain contracts; `ollama:qwen3:4b-instruct@node-a` + `ollama:gemma3:4b@node-i`; samples 2, retries 3, rounds 2; 4096 tokens / 900 s per call): kept the 7 units of round 1 and wrote the other 32 in one round of 127 min (103 calls: 68 gemma3:4b, 35 qwen3:4b-instruct; 13 units needed more than one pair of samples, among them `newGame`, `tick`, `touchTiles`, `snapshot`, `startGame`). Page 16 765 characters, `kits/kirby/results/kirby-4b-r4.html`, **required 68/68** by `grade.py` and again by hand. The round shared node-a with the autogen run's planner and child for most of its length. The sheet edits made during the round (newGame, Shared, swallow, touchTiles, tick, snapshot, drawHud and the four ported drawing/start contracts) apply to later builds, not to this one.

## RESULT 06:28: the 1B rung built the Kirby level, mostly by the 0.5B model (harness 68/68)

Run `kirby-1bg-r1` (`kirby-1b.sheet.md`: every unit "Write exactly this code:" plus the reference code; the level map `Given: yes`; `ollama:gemma3:1b@node-b` + `ollama:qwen2.5:0.5b@node-d`; samples 2, retries 3, rounds 2; 2048 tokens / 600 s per call):

| measure | value |
|---|---|
| units | 39 of 39 (38 asked, the level map given by the sheet and only tested) |
| model calls | 81 (41 qwen2.5:0.5b, 40 gemma3:1b) |
| accepted answers by author (matched against each call's reply) | **35 by qwen2.5:0.5b, 3 by gemma3:1b** |
| units that needed more than one pair of samples | `moveY` (3 calls), `swallow` (4), `drawTile` (3), `drawHud` (3) |
| wall time | 1 522 s (25 min), 06:02 to 06:28 |
| page | 14 963 characters, `kits/kirby/results/kirby-1b-r1.html`; one line differs from the reference page (`input`: `g.keys[action] = pressed` instead of `g.keys.inhale = pressed`, equivalent on the examples and the harness) |
| strict harness | **required 68/68**, by `grade.py` and again by hand |

So the whole ladder passes the same 68 checks: plain contracts for 4B models, numbered steps for 3B/2B, exact code for 1B/0.5B, with the level data given. A 0.5B model alone (`kirby-05b`, qwen2.5:0.5b @ node-d) is the next measurement, started 06:29; the second 1B pair (llama3.2:1b @ node-a + gemma3:1b @ node-i, `kirby-1bl`) was at 14 of 39 at 06:28. The first 1B attempt without the given level stopped at unit 1: gemma3:1b dropped characters from one 64-character row and qwen2.5:0.5b wrapped the constant in a function, four times each.

## RESULT 06:48: the floor. qwen2.5:0.5b alone built the Kirby level (harness 68/68)

Run `kirby-05b-r1`: `kirby-1b.sheet.md` (exact code per unit, the level map given), the single applicator `ollama:qwen2.5:0.5b@node-d` (both samples from the same model; samples 2, retries 3, rounds 2; 2048 tokens / 600 s per call), started 06:29.

| measure | value |
|---|---|
| units | 39 of 39 (38 written by the 0.5B, the level map given) |
| model calls | 84; every unit but one settled within its first pair of samples |
| the hard unit | `swallow(g), spit(g)`: 10 calls; the model rewrote the given guard `if (k.full === null) return false;` as `if (k.full === 'B') {` and only a late re-sampled retry copied it right. From the next build on, an exact-code unit's retry reason also lists the lines that differ from the given code (`diff_lines`, below) |
| wall time | 1 171 s (19.5 min) |
| page | 14 958 characters, `kits/kirby/results/kirby-05b-r1.html` |
| strict harness | **required 68/68**, by `grade.py` and again by hand |

**Repeat with the line-diff retry reason (`kirby-05b2-r1`, 06:49-07:08, same sheet, model and settings, the compiler now emitting `diff_lines` for exact units):** 39 of 39, 78 calls, 1 089 s (18 min), harness 68/68 (`results/kirby-05b2-r1.html`); `swallow` took 4 calls instead of 10 and no other unit needed more than its first pair. One run per arm, so this is a measurement of one repeat, not a proof; the diff text is in the compiled retry reason by construction, and neither run file stores prompt text.

**Second 1B pair (`kirby-1bl-r1`, llama3.2:1b @ node-a + gemma3:1b @ node-i, same exact-code sheet, 06:14-07:19):** 39 of 39, 96 calls (52 llama, 44 gemma), 3 958 s (66 min), harness 68/68 (`results/kirby-1bl-r1.html`). Accepted answers: 30 by gemma3:1b, 8 by llama3.2:1b; 15 units needed more than their first pair of samples (`moveY` 6, `drawHud` 5, thirteen others 3). Of the four light models measured on the exact-code sheet, llama3.2:1b copies least faithfully, qwen2.5:0.5b and gemma3:1b most.

**Control: the 1B pair on the numbered-steps sheet (`kirby-1bs`, gemma3:1b @ node-b + qwen2.5:0.5b @ node-d, 07:08-07:45):** stalled at 4 of 39 in three rounds (27, 16 and 15 calls on the three-function `solidRow` unit). The models invent names the steps never mention (`c0`, `c1`, an extra `c` parameter) and loop over the wrong axis. So the step wording that carries 3B/2B models does not carry 1B models: at 1B and below the sheet has to give the code, and the kernel's job is to check the copy (and, since 06:40, to show the differing lines).

**4B pair on the numbered-steps sheet (`kirby-4bs-r1`, qwen3:4b-instruct @ node-a + gemma3:4b @ node-i, 07:20-09:39, level given):** 39 of 39, 96 calls for 38 written units (56 gemma, 40 qwen3), harness 68/68 (`results/kirby-4bs-r1.html`). Against the same pair's plain-contract run (103 calls for 32 units, 13 units beyond their first pair): 2.5 calls per unit instead of 3.2, 9 units beyond their first pair instead of 13, and `swallow`, `touchTiles`, `tick`, `snapshot`, `drawHud` all passed within their first pair. Wall time (139 min) is not comparable: node-a was shared with the autogen run's attempts for most of it. So the step wording helps the 4B pair too, moderately; it is the 3B/2B rung that it makes possible.

That is the lightest model on the cluster producing the same 68-check-clean page as the 4B pair, with the sheet carrying the exactness and the kernel carrying the verification. The ladder in one line: 4B + plain contracts (127 min for 32 units), 3B/2B + numbered steps (83 min), 1B pair + exact code (25 min), 0.5B alone + exact code (19.5 min).

## Kirby ladder: the sheet variants (04:30)

Three sheets with byte-identical examples, headings, `Uses:` lines, test setups and Assemble, built and verified with the kit (`node fill-sheet.mjs check`: 39 units, 229 examples, 0 differing; dry run through the real kernel 39/39; assembled page byte-identical to the reference; harness 68/68):

Since 07:11 the level map is `Given: yes` in all three sheets (data is the designer's input, not a model task); the runs recorded above wrote it themselves where their rung could (4B and 3B/2B did, first try).

| sheet | wording | rung |
|---|---|---|
| `kirby.sheet.md` | plain contracts, `Used units shown as: signatures`, `Answers normalized: yes`; since 04:11 `newGame` shows its whole function and Shared forbids placeholder lines (`const LEVEL = /* provided */;`) | 4B (qwen3:4b-instruct @ node-a + gemma3:4b @ node-i, loop `kirby-4b`) |
| `kirby-3b.sheet.md` | every contract as 3-8 numbered steps naming the reference's loops, conditions and returns, plus one "never" sentence per unit for the likely slip | 3B/2B (qwen2.5-coder:3b @ node-b + granite3.3:2b @ node-d, loop `kirby-3b`, started 04:30) |
| `kirby-1b.sheet.md` | "Write exactly this code:" with the reference unit in a fence; since 06:02 the level map is `Given: yes` (supplied by the sheet, tested, no model asked: gemma3:1b dropped characters from one 64-character row and qwen2.5:0.5b wrapped the constant in a function, four times each) | 1B (gemma3:1b @ node-b + qwen2.5:0.5b @ node-d, loop `kirby-1bg`, started 06:02; the first attempt `kirby-1b-r1` was stopped at unit 1) |

## Host-load incident on the host (02:57-03:45) and the fix

The host (6 CPUs) ran at load 27-58 with I/O pressure 75-83 %: nightly indexing jobs of the host's other applications, a sync job's git hashing, the ARM node rsync, and the host's own Ollama serving llama3.1:8b (6.9 GB, runner ~370 % CPU) for other workers on node-d through the inference relay on port 11436. None of it was a beta or Kirby call (every model call ran on the named worker nodes), but every 3 s JavaScript case on the host timed out: Kirby round 1 ended "inconclusive" after 7 accepted units, round 2 failed the same way with 0 units, and round 3 (which kept from round 2, so from nothing) restarted from scratch and was stopped.

Changes:
- `symblic.js.check`: a timed-out case is observed again, up to 2 more times, each after a bounded wait (90 s, never past the deadline) for the host to be calm (1-minute load ≤ 1.5 per CPU, I/O pressure ≤ 40 %). Only `timeout` observations are re-run; a verdict, a memory or an unavailable observation never is. Re-run rows carry `reobserved`; the `js_test` report carries `reobserved: n`; the inconclusive reason says how many re-observations were made. Tests `tests/js/test_symblic_js_reobserve.py` (fakes only). Contract: `docs/reference/JS.md`.
- The Kirby loop keeps the best run so far (`--from RUN --start N`), never a worse later round, and each round waits (at most 30 min) for a calm host before judging code.

## Added for publication: how much of each page the sheets dictated (measured 10:05)

This measurement was made at the end of the same session, against the 359 non-trivial code lines of the Kirby
reference implementation (now in `kits/kirby/reference/`), and recorded in the session's own notes, which are
not part of this repository. Each reference line was classified once per sheet: given verbatim in the sheet, its main
expression quoted inside a numbered step, or left for the model to write from prose.

| sheet | lines given verbatim | main expression quoted inside a step | the model writes from prose |
|---|---|---|---|
| `kirby-1b.sheet.md` (exact code) | 359 (100%) | 0 | 0 |
| `kirby-3b.sheet.md` (numbered steps) | 208 (57%) | 132 (36%) | 19 (5%) |
| `kirby.sheet.md` (plain contracts) | 141 (39%) | 142 (39%) | 76 (21%) |

Reading, as recorded then: the 1B and 0.5B pages are transcription tests (the sheet contains all of the code; the
kernel checks the copy); the 3B result is mostly assembly of dictated expressions into correct control flow; the 4B
plain-contract run is the only one in which the model wrote a meaningful share (21% of lines from prose, another 39%
from quoted expressions), and even that sheet is far more specific than a human specification would be. The
classification was made by the agent that ran the ladder; this repository has no script that reproduces this exact
three-way split. `kits/tetris/build/verbatim.py` measures a related quantity (how much of a page appears word for
word in its sheet: 38% of `kirby-4b-r4.html`'s non-trivial script lines, `kits/kirby/results/README.md`).
