# Spec sheets: building a file from small checked units

A spec sheet describes one output file strictly enough that small models can write it piece by piece.
`symblic/spec/sheets.py` compiles it into an ordinary Symblic program, deterministically: no model writes the program.
The program asks for each unit in its own fresh context, tests each answer with the kernel's sandboxed JavaScript
(`js_test`, [JS.md](JS.md)), and assembles the file from the passing units only.

This is the point of Symblic applied to code. Every step resets the model's context to exactly what that step
needs, and every step is checked by the kernel before the next one starts. A model only has to get one small,
fully specified unit right at a time.

```
python3 symblic/spec/sheets.py check SHEET.md
python3 symblic/spec/sheets.py compile SHEET.md --by ollama:qwen3:4b-instruct --by ollama:phi4-mini \
    --by ollama:gemma3:4b --samples 5 --retries 3 --rounds 3 > build.sym
```

## The format

```markdown
# tetris.html
One self-contained HTML5 file that implements exactly this Tetris.

## Shared
Conventions every unit follows, and the data model they share (the game state's fields).

## Unit `cellsOf(type, rot)`
Uses: `SHAPES`

Return a new array of the piece's [row, col] cells after `rot` clockwise turns: ...

Test setup:

    function blank() { return Array.from({ length: 22 }, () => Array(10).fill('')); }

Examples:

    cellsOf('T', 1) ==> [[1,2],[0,1],[1,1],[2,1]]

## Assemble `tetris.html`

    <!DOCTYPE html> ... <script>
    /*UNITS*/
    </script> ...
```

- The first heading names the file. The text before `## Shared` says what the file is.
- **`## Shared`** is shown to every unit. Put the conventions and the shared data model there.
- **`## Unit `names``**: the heading lists what the unit defines (`levelOf(lines), gravityMs(level)` defines two
  functions). Then:
  - the contract in prose;
  - `Uses:` the names other units define that this one may call; their tested code is pasted into the prompt,
    unless the sheet says `Used units shown as: signatures` (a line before the first unit): then the prompt only
    names them. Use that for 0.5B-1B workers, which copy pasted code instead of calling it (2026-10-10);
  - an optional indented `Test setup:`, with helpers the examples use;
  - indented `Examples:` lines `call ==> expected JSON`.

  Every unit needs examples. A unit may use only units above it.
- **`## Assemble `file``**: the file as an indented block, with `/*UNITS*/` where the code goes. Units are placed
  in sheet order.

## What the compiled program does

For each unit, in sheet order:

1. **`ask unit_X: Code js "..."`** with `context=none`. The instruction holds:
   - the shared section;
   - the unit's contract;
   - the code of the units it uses, already written and tested, shown verbatim so a model never guesses what they
     hold;
   - its examples and test setup;
   - "define these names and nothing else".

   The answer is the last fenced code block of the reply. No JSON is involved.
2. **`let test_X = js_test([setup, every earlier unit, unit_X], [examples])`**. Every earlier unit is included, not
   only the dependencies, because the file holds them all. The pieces run as separate scripts. A top-level name
   declared twice fails at the unit that repeats it: a `const` as "already declared", a function as "it defines f
   again". The last unit's test is a whole-file check.
3. **`ensure test_X.passed else retry because test_X.report`**. A failing answer comes back to its model with the
   failing examples (expected and actual values) and its own code.

`use ... route=search, samples=K, retries=R, rounds=N` is the program's default for every unit:
- K candidates work at once, taking the applicators in turn, each with its own seed. The first runs at temperature
  0 and the others at 0.7.
- Each candidate is repaired against its own failures up to R times.
- The selected answer is the pass with the fewest attempts, with ties going to the lowest index, never the first to
  arrive, so the same replies always select the same code. It is taken as soon as nothing can beat it.
- A round in which none passes is followed by a fresh one, up to N rounds. Then the run stops at that unit.

The file is `replace(page, "/*UNITS*/", join([units...], "\n\n"))`. Only code that passed its checks reaches it.

## Incremental rebuilds: keep what already passed

```
python3 symblic/spec/sheets.py compile SHEET.md --by ... --keep automation_data/symblic/runs/RUN_ID [--redo NAME] > next.sym
```

On the Symblic page this is the Build screen's "Keep the units an earlier build accepted" menu, which lists earlier
spec builds (`POST spec/run` with `keep: RUN_ID`). `--keep` reads the code that earlier build accepted
(`accepted_units`). The longest run of leading units found
there becomes fixed text in the new program: `let unit_X = "...code..."`, the same `js_test`, then `assert`. No
model is asked for those units again. A kept unit that no longer passes the sheet's examples stops the build at
that unit. Later units see the kept code exactly as before. `--redo NAME` stops keeping at that unit, for when its
wording changed. The program's first notes name the run the kept code came from.

Without `--keep`, restarting after editing a later unit depends on the call cache: unchanged prompts replay their
recorded replies. That is fragile. A change in the feedback text a repair was given (for example a better error
report) makes that repair a new call, which can select a different candidate for an early unit. Every later prompt
then changes with it. Keeping removes that dependence.

## When a unit stalls: diagnose the sheet, not the models

```
python3 symblic/spec/sheets.py diagnose SHEET.md --run automation_data/symblic/runs/RUN_ID [--unit NAME] [--all] [--json]
```

This reads one build's run folder (`program.sym`, `calls.jsonl`, `trace.jsonl`) and calls no model. It tests every
model reply to each unit again, the way the build did: after the code that run accepted for the earlier units,
which it finds by the answer fingerprints in the trace. The failures are grouped by the first example each reply
fails, with what the replies returned and which models wrote them. By default it counts only the run's own calls;
`--all` adds the calls merged into the folder from earlier programs as a cache, which may have answered other
wordings.

When many replies from different models fail one example the same way, the wording is usually the cause. In the
Tetris build, 9 of 13 replies for `afterMove` returned `[0,3]` instead of `[0,2]`: they tested `wasResting` where
the sheet meant the state after the move. The other 4 copied `SHAPES` into their answer again ("already
declared"). What fixed it was wording, not a bigger model:
- numbered steps;
- naming the call each step makes ("step 1 must call `resting(g)`");
- "`was` is only passed on; never test it here";
- the shape of the code ("exactly two `if` statements").

## Writing for small models

These rules come from the local Tetris build, which used only 4B models (qwen3:4b-instruct, phi4-mini,
gemma3:4b) on CPU-only worker nodes:
- **Steps for anything stateful.** Prose such as "first note `was = resting(g)`, then ..." was read as
  `if (was && ...)`. A numbered list of steps, each naming the exact call or assignment, was followed.
- **Exact literals for exact shapes.** Write object literals, field lists and formulas (`x = c * 30`,
  `fillRect(x + 1, y + 1, 28, 28)`) in the text. A model told only to "start a new game" drops or renames fields.
- **Show what a unit must not do.** "Append all 7, never remove letters" stopped models from truncating the queue
  to the 3 letters the examples showed.
- **Standard algorithms verbatim.** The PRNG is given as code, because the output must match bit for bit.
- **Keep units small.** Every unit's prompt holds only the shared section, its contract, the code it uses and its
  examples, so a 4B model's context holds the whole task. A 60-line `draw` failed on syntax slips and each attempt
  took 10-15 minutes on a CPU. Split into `drawCell` (2 lines), `drawBoard`, `drawSide` and a 2-line `draw`,
  each step was small enough to get right.
- **Units are declarations only.** The page's Assemble section makes the one top-level call (`startGame();`), and
  the unit's examples call it themselves. A unit told both to declare `startGame` and to call it obeyed the
  compiler's "declarations, nothing else" and left the call out, so every reply failed.
- **Tables for mappings.** `keyAction` as one long sentence took 15 replies to get 2 passes: replies dropped
  `Shift`, mapped `z` to `cw`, or returned the key itself. Rewritten as a lookup table.
- **Words the models act on.** Do not write "define" in an instruction: phi4-mini answered
  `define("drawBoard", function ...)` after reading "no define()". The compiler's prompt says "declarations named
  X". Name what must not be copied: "your answer must not contain SHAPES, cellsOf again". Models pasted the
  dependency code they were shown, and a pasted `function` silently replaced the tested one until the kernel
  started checking for it.

## The Tetris record (2026-10-04)

`examples/tetris.sheet.md` (25 units, 120 examples) was built into `tetris.html` by local models only:
qwen3:4b-instruct, phi4-mini and gemma3:4b in Ollama on CPU-only worker nodes. The page passes the strict harness, 39 of
39 required checks; the 2 advisory checks want the score and "GAME OVER" as page text, not canvas text.
- **Cost:** 14 incremental builds (each kept what the last one accepted), 421 model calls and 21 model-hours.
- **Writers:** qwen3:4b-instruct, as candidate 0, wrote every accepted unit. The other two models passed 14 of
  the 25 units too and lost the tie.
- **Copied text:** 30% of the page script's non-trivial lines appear word for word in the sheet, mostly in the
  drawing steps, `startGame` and the PRNG. The sheet gives the PRNG as code.
- **Sheet changes:** what changed along the way is listed under "Writing for small models".
- **Kernel changes:** "it defines f again", quoted error lines, the 1-hour local call limit, and incremental
  `--keep`.
- **From-scratch validation** (run `3566050e304f`, 08:30-10:24): the final sheet was built once through the Build
  API (`spec/run`, three local models, samples 5, nothing kept, no cache).
  - It passes 39/39 required.
  - All 25 units were accepted on their first attempt, and in 12 of them a second model passed too.
  - Cost: 141 calls and 8.7 model-hours.
  - The page differs from the first build: the models sample, and a different but equally passing page is
    expected. Both pages have about 30% of their lines verbatim from the sheet.

## What a passing build establishes, and what it does not

Every unit gives every value its examples list, after the code of the units it uses. That is all.
- A unit can pass its examples and still be wrong on inputs no example covers.
- An independent test of the whole file is still needed. For Tetris that is the harness in
  `~/.local/state/executor-integration-20261003/tetris-kit/`, which compares every state with an exact
  reference over many games.
- When the sheet's examples come from a reference implementation (as the Tetris sheet's do,
  `~/.local/state/symblic-local-tetris-20261003/ref-units.mjs`), check that reference against the specification
  first. That reference agrees with the Tetris oracle on 300 games and 120 000 steps.


## Small local models (2026-10-10, the Atomic study)

- Cap a run's local calls: `tools/symblic run … --ollama-limits '{"num_predict": 2048, "timeout_seconds": 900}'`
  (the hub's `spec/run` defaults to 4096 tokens and 15 minutes per call for `ollama:` applicators). The worker nodes'
  default reply room is 16384 tokens: a 1B model in a repetition loop otherwise holds a node for up to an hour.
- Size the atoms and the prompt to the worker. gemma3:1b failed 13 units of 2-40 lines (0/13) and mangled a
  one-line expression given verbatim under a 2 kB shared section; with a 350-character shared section it passed
  one-expression units. Put `Used units shown as: signatures` before the first unit for 0.5B-1B workers.
- Pin one build per worker node (`ollama:MODEL@NODE`): the fleet runner admits one model run per node across processes, so two
  unpinned builds starve each other and a killed build's calls can hold a node until its runs are released.
- `Given: yes` (a line in a unit's contract, 2026-10-11): the unit is data the sheet supplies, not work for a model.
  Its fenced ```js block becomes the unit's text, tested against the unit's examples exactly like a kept unit
  (`assert`, so a given unit that fails its examples stops the build), and no model is asked for it. Why: the Kirby
  level map is 12 rows of 64 characters; gemma3:1b dropped characters from one row and qwen2.5:0.5b wrapped the
  constant in a function, four times each, on the exact-code sheet. A level is the designer's input, not something
  to be re-typed by the lightest worker. Later units see a given unit as any other (signatures or code).
- Exact-code units (2026-10-11): a unit whose contract says "Write exactly this code:" and holds a fenced ```js
  block (the 1B/0.5B rung) is compiled with `let exact_X = <the block>` and a retry reason of
  `join([test.report, "Your answer must be exactly the code given in the task.", diff_lines(unit_X, exact_X)], "\n")`:
  after the failing examples, the model sees the lines where its answer departs from the given code
  (`diff_lines`, a kernel builtin: difflib over whitespace-stripped lines, the first 6 changes, "your line 2: … |
  must be: …"). Why: on `swallow(g), spit(g)` qwen2.5:0.5b rewrote `if (k.full === null) return false;` as
  `if (k.full === 'B') {` four times when its only feedback was the failing example. A given unit never gets it.
- `Answers normalized: yes` (a line before the first unit, 2026-10-10): every unit is asked as
  `Code js unit NAMES reusing EARLIER-NAMES`, and the kernel normalizes the answer by code before it is tested or
  assembled: the fenced block that declares the unit is the one taken (not the last block), a unit written as
  `name(args) {` gets its `function` back, and the worker's own top-level copies of names earlier units already
  passed are cut out (parsed with the pinned Acorn in `symblic_js_normalize.js`, never executed), and a unit declared
  twice (`const f = ...` next to `function f`) keeps its `function` form; a bare `name = function ...` becomes a
  `const` for the unit's own name and is cut for a reused name (the sandbox's protected bindings swallow such a
  reassignment silently, the assembled page would run it: llama3.2:1b passed 37/37 units and scored 243/500 that
  way before this repair). These were the
  three ways 0.5B-1B workers failed the exact-code sheet: a volunteered `escapeHtml` next to the unit (gemma3:1b,
  qwen2.5:0.5b), backticks inside a regex literal breaking the fence (llama3.2:1b). The normalized text is the
  binding: what passed is what ships. A plain `Code js` answer is untouched.
