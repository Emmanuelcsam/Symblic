# Honest assessment: what Symblic has shown, and what it has not

Every number on this page comes from a record in this repository; the source is named next to it. The records
were written by the AI agents that ran the experiments (see [MADE-WITH-AI.md](MADE-WITH-AI.md)), on one private set
of machines: a small Linux host and a few CPU-only laptops running [Ollama](https://ollama.com), between 2 and 11
October 2026. Almost every result is a single run on a small sample. None of it is a benchmark, and none of it was
reproduced by anyone else.

## The short version

- **The exact parts are exact.** Programs whose steps are all formal gave the same fingerprints and the same drawing
  bytes on 8 machines with three Python versions and two CPU architectures. This is about the interpreter, not about
  what a model answers.
- **Small local models can be carried to a complete, tested result.** Seven builds of a 39-unit game level by 0.5B to
  4B models all passed the same strict 68-check harness, with no human edits to the pages.
- **The smaller the model, the more the specification has to contain.** The share of the reference code left for the
  model to write from prose was 21% for the 4B sheet, 5% for the 3B sheet and 0% for the 1B sheet. The 1B and 0.5B
  results are tests of faithful copying, not of ability.
- **Splitting did not rescue a model that could not write a unit; rewording did.** A 3B model that failed one unit
  stalled on the first piece at each of three split levels (a fourth was starting when the run was cancelled); in a
  later run one child wrote one sub-piece but never the unit. One unit, one 3B model, three runs. The same unit
  written as numbered steps passed on the first try.
- **Whole programs from small models did not pass hidden tests.** In the attempts that ended with a program (a 4B
  model on the easiest family of a difficulty ladder, and a longer pilot), no program passed the independent hidden
  tests.

## 1. The ladder of small local models (2026-10-11)

Source for this section unless another is named:
[reference/LOCAL-BETA-REPORT-2026-10-11.md](reference/LOCAL-BETA-REPORT-2026-10-11.md). A pass is always a code
verdict (the unit's examples run in a sandbox, then a harness), never a model's own claim. Models ran in Ollama on
CPU-only laptops; each call was capped (2,048 or 4,096 output tokens, 600 or 900 seconds).

### 1.1 A four-unit sheet: which wording each model size needs

The sheet asks for four units of a falling-block game: the piece table, `cellsOf` (the cells of a rotated piece),
`emptyBoard` and `fits`. Each row is the final wording that worked for that model; earlier attempts are in the
source.

| Model | Wording that worked | Units accepted |
|---|---|---|
| qwen3:4b-instruct | plain contracts | 4 of 4, each on the first try |
| qwen2.5-coder:3b | `cellsOf` and `fits` as numbered steps, used units shown as signatures | 4 of 4 (1 of 4 with plain contracts; identical wrong answers even at temperature 0.6) |
| granite3.3:2b | numbered steps, signatures, normalized answers, and one "never" sentence naming the wrong form it kept writing | 4 of 4 (1 and then 2 of 4 before) |
| gemma3:1b | `cellsOf` and `fits` given as exact code to copy | 4 of 4 (0 of 4 with plain contracts) |
| llama3.2:1b | every unit given as exact code | 4 of 4 |
| qwen2.5:0.5b | every unit given as exact code, after two fixes to the answer normalizer | 4 of 4 (0 of 4 before the fixes) |

The record's own reading: "4B from plain contracts; 3B from contracts once the composition unit is numbered steps and
used units are shown as signatures; 1B from two contracts plus two exact units; 0.5B and the other 1B from exact units
only." Sampling was a weak lever: retries at temperature 0.6 with new seeds returned the same code; wording and
examples were the levers that moved a 1B or 3B model.

### 1.2 A complete game level: 39 units, 229 examples, 68 required checks

Sources: [../kits/kirby/results/README.md](../kits/kirby/results/README.md) (the pages, re-graded in this repository)
and the beta report. The sheets come in three wordings: plain contracts (for 4B models), numbered steps (3B/2B) and
exact code (1B/0.5B). Every completed build passed `required 68/68`.

| Page | Models | Sheet | Units asked | Model calls | Wall time |
|---|---|---|---|---|---|
| `kirby-4b-r4` | qwen3:4b-instruct + gemma3:4b | plain contracts | 32 (7 kept from an earlier round) | 103 (+21 earlier) | 127 min |
| `kirby-4bs-r1` | qwen3:4b-instruct + gemma3:4b | numbered steps | 38 | 96 | 139 min |
| `kirby-3b-r1` | qwen2.5-coder:3b + granite3.3:2b | numbered steps | 39 | 92 | 83 min |
| `kirby-1b-r1` | gemma3:1b + qwen2.5:0.5b | exact code | 38 | 81 | 25 min |
| `kirby-1bl-r1` | llama3.2:1b + gemma3:1b | exact code | 38 | 96 | 66 min |
| `kirby-05b-r1` | qwen2.5:0.5b alone | exact code | 38 | 84 | 20 min |
| `kirby-05b2-r1` | qwen2.5:0.5b alone | exact code, with the differing lines shown on retry | 38 | 78 | 18 min |

What did not work, from the same records:

- The 1B pair on the numbered-steps sheet stalled at 4 of 39 units in three rounds (27, 16 and 15 calls in the beta
  report; the kit's record gives 16 for the third). The models invented names the steps never mention and looped over
  the wrong axis.
- The first 1B attempt, before the level map was supplied as data, stopped at unit 1: gemma3:1b dropped characters
  from a 64-character row and qwen2.5:0.5b wrapped the constant in a function, four times each.
- Two rounds of the 4B build ended early because JavaScript checks timed out on an overloaded host; the interpreter
  now observes a timed-out check again after waiting for the load to drop.
- In the 1B pair's build, 35 of the 38 accepted answers came from qwen2.5:0.5b and 3 from gemma3:1b.

### 1.3 How much the sheets dictated

Measured at the end of the same session against the 359 non-trivial lines of the reference implementation (table
added to the beta report for publication; the classification was done by the agent that ran the ladder, and no
script in this repository reproduces it):

| Sheet | Lines given verbatim | Main expression quoted inside a step | Left to the model (written from prose) |
|---|---|---|---|
| exact code (1B, 0.5B) | 359 (100%) | 0 | 0 |
| numbered steps (3B, 2B) | 208 (57%) | 132 (36%) | 19 (5%) |
| plain contracts (4B) | 141 (39%) | 142 (39%) | 76 (21%) |

### 1.4 What the 1B and 0.5B results show, and what they do not

They show that the pipeline (a sheet, a fresh context per unit, code checks, retries that show the lines that
differ, answer normalization, assembly from passing units only) can carry a 0.5B model to a page that passes all 68
harness checks (38 units answered by the model, the level map given by the sheet), unattended, in about 20 minutes on
a laptop CPU. The harness does not cover a real browser, real keys or how the drawing looks
([../kits/kirby/README.md](../kits/kirby/README.md)).

They do not show that a 0.5B or 1B model can write that code. The sheet contained all of it; the models copied it
and the interpreter checked the copy. "A 0.5B model built a game level" is true of the page and misleading about the
model. The session's first summary framed these results as capability; that framing was withdrawn the same morning,
and these records call them copy tests, which is what they are. The 3B result is mostly assembly of dictated
expressions into correct control flow, more than transcription and less than design. The 4B plain-contract run is the only one in which the model
wrote a meaningful share of the code.

### 1.5 Automatic splitting (autogen) on a 3B model

Three runs gave qwen2.5-coder:3b the four-unit sheet with plain contracts, through the automatic regenerate-and-split
coordinator ([../symblic/autogen/](../symblic/autogen/README.md),
[reference/RECURSION.md](reference/RECURSION.md)):

- When the planner had to answer in free text, the 3B model restated the unit or its examples instead of a split,
  and code refused every plan.
- With a typed JSON answer, the split was accepted by code, but each child stalled on its own first piece, so the
  later pieces were never tried; the run was split again to 8 and 13 units and cancelled after 17 attempts, as a
  fourth level was starting. Every level accepted only the one unit its parent already had.
- A rule was added: a split child is not split again unless it beats its parent. In the third run the first child did
  write one sub-piece (`getShapeCells`: 2 units against its parent's 1) but never `cellsOf`; its own split made no
  further progress, and the run stopped at depth 2 with "this split made no progress over its parent".

Measured result, for one unit, one 3B model and three runs: recursive decomposition did not lift the model over a
unit it could not write; rewording that unit as numbered steps did, on the first try, in the ladder above.

### 1.6 Other lanes, one trial each

The same day's beta matrix (`symblic/bench/local_beta.py`; source: the beta report's two "Beta matrix" sections) ran
single trials of other lanes. A Markdown page passes when its output matches the reference on 500 random documents.

| Lane | Model | Result |
|---|---|---|
| Spec sheet, Markdown renderer, 13 units | qwen3:4b-instruct | pass: 13 units, 28 calls, 500/500 documents |
| Spec sheet, Markdown renderer, 13 units | gemma3:1b | fail: stopped at unit 1 (`escapeHtml`) |
| Native typed asks (3 fixtures) | qwen3:4b-instruct | 3/3 |
| Native typed asks (3 fixtures) | gemma3:1b | 1/3 (a word problem answered 3 instead of 44; counted six a's in "banana" on every attempt) |
| Local web research (the title of a DOI) | qwen3:4b-instruct | 1/1: read the DOI page and quoted the exact title |
| Local web research (the title of a DOI) | gemma3:1b | 0/1: answered with a blog title |
| English statement (smoke test) | gemma3:1b | 0/1 (answered 50 three times) |
| Delegate template `classify-complaint` (smoke test) | gemma3:1b | 1/1 |
| Spec sheet, Markdown renderer, 37 units given as exact code | gemma3:1b | pass: 37/37 units, all on the first try, 500/500 documents |
| Spec sheet, Markdown renderer, 37 units given as exact code | qwen2.5:0.5b | fail at unit 1 (`escapeHtml` escapes, then undoes it; four identical replies) |
| Spec sheet, Markdown renderer, 37 units in finer wording | granite3.3:2b | fail at `isOlBlock`, with 22 of 37 units accepted |
| Spec sheet, Markdown renderer, 37 units in finer wording | qwen2.5-coder:3b | first run: no verdict (a JavaScript check timed out on an overloaded host) at 28 of 37; second run (2 samples, 2 rounds): pass, 37/37, 75 calls, 500/500 documents |

Each row is one trial, so a pass shows the path can work and a failure shows where that model stopped; neither is a
rate.

## 2. Earlier measurements (2026-10-02 to 2026-10-10)

| What | Result | Source |
|---|---|---|
| Interpreter identity | Two all-formal programs gave one run fingerprint each on 8 machines (x86 and ARM; Python 3.11, 3.12, 3.13), and the same drawing hashes | [reference/RESULTS.md](reference/RESULTS.md) §1, [reference/kernel-identity.json](reference/kernel-identity.json) |
| Typed asks and agreement (16 questions, 7 model applicators) | Pairwise identical answers 78% typed against 62% prose: +17 points (95% CI +4 to +30), with correctness unchanged (88% in both forms). Agreement is not correctness | RESULTS.md §2 |
| Translate, then let the interpreter reason (15 generated family trees) | qwen3:4b: 9/15 answering directly, 12/15 when it only listed facts and Datalog rules did the reasoning; llama3.2:1b: 0/15 and 3/15 | RESULTS.md §3 |
| The same drawing from a prose description (6 descriptions) | Five cloud models: 6/6, identical bytes; qwen3:4b: 5/6; llama3.2:1b: 0/6 | RESULTS.md §4 |
| Councils of five qwen3:4b on 24 generated arithmetic problems | 18/18 completed items correct, but the comparison arms did not finish; no gain over one model or parity with large models is shown | RESULTS.md §5 |
| Falling-block game from a 25-unit sheet (qwen3:4b-instruct, phi4-mini, gemma3:4b) | Passed 39/39 required harness checks after 14 incremental builds, 421 model calls and 21 model-hours; a from-scratch rebuild took 141 calls and 8.7 model-hours; about 30% of the page's lines appear word for word in the sheet | [reference/SPEC-SHEETS.md](reference/SPEC-SHEETS.md), "The Tetris record" |
| Difficulty ladder, easiest family, 300 s and 8 calls per rung | qwen2.5:0.5b: all six strategies ran out of calls or time; qwen3:4b-instruct: two programs passed their own public checks and failed the hidden tests, four strategies ran out of time planning | [reference/REPORT-2026-10-10.md](reference/REPORT-2026-10-10.md) §6 |
| Longer matched pilot (qwen3:4b-instruct, 1,800 s and 24 calls per assignment) | 7 of 12 assignments ran; the two finished programs failed the hidden grade (best 50 of 51 cases); no whole-program hidden pass | REPORT-2026-10-10.md §2 |
| Fine-tuning pilot (qwen2.5 0.5B, four LoRA steps on CPU) | 0/3 to 1/3 agreement on a frozen three-item comparison; shows the pipeline runs, not that training helps | [reference/DISTILLATION.md](reference/DISTILLATION.md), [../symblic/distill/](../symblic/distill/README.md) |
| AI-written proposal documents (9 documents) | Independent readers found 63 proposals and 120 factual errors; 12 proposals were built in reduced form and 32 were rejected | [reference/REVIEW-2.3.md](reference/REVIEW-2.3.md) |

## 3. Limits that apply to everything above

- **One run, small samples.** Most rows are one run of a few to a few dozen items. Only the agreement study reports
  confidence intervals.
- **One author for everything.** The sheets, their examples, the reference implementations, the harnesses and the
  reports were written by AI agents, mostly by the same agent in the same session. A misreading shared by a sheet and
  its harness would not be caught.
- **One private setup.** The worker machines, their scheduler, the agent runner and the web pages that started many of
  these runs belonged to the original host and are not in this repository. The spec-sheet builds should be repeatable from
  [../kits/](../kits/README.md) with your own Ollama server, but this repository's Ollama path and build loop have
  only been run against fakes (nothing here was run against a model while it was prepared for publication); most
  other rows cannot be repeated as they were run.
- **Software tests are not model results.** The thousands of unit tests in [../tests/](../tests/README.md) check the code with
  fake models. They say nothing about how often a real model succeeds.
- **Sampling.** Models sample. A rebuild from the same sheet gives a different page that may or may not pass.

## 4. Questions that remain open

- How much logic each model size contributes when a sheet quotes no expressions at all (a contracts-only sheet run
  across the ladder). Not started.
- Whether small models do real work in a porting task, where the examples carry over and the model translates.
  Not measured.
- Whether the results hold for other people's specifications, written and checked by someone other than the agent
  that wrote the harness.

If you run any of these, please add the record next to the others, failures included.
