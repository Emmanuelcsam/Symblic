# English statements (`symblic.english.compiler`, version `symblic-english/1`)

A bounded, near-English way to write a Symblic workflow as a list of atomic instructions. The compiler
turns each statement into ordinary native Symblic source. The program then runs on the existing native
`Run`, with its capsules, budgets, routing, retries and replay unchanged. It is a fixed grammar, not
English understanding: anything outside the grammar is refused with a line and column.

## Use it

Open `/automation-studio/symblic.html` (or its preserved `#english` link). A new visit opens
**English statements** with one instruction field. Choose **Checked statements** for the bounded
compiler documented here, or **Agent task** for file and tool work. Switching workflows preserves
the exact text; it does not translate or submit it. Run/status stays before the advanced panels.
The compact English/Native/Runs navigation and searchable **All Symblic tools** menu retain all
19 original views and deep links. Native execution settings are also collapsible.

Expand **Agents · N members** in that same editor to configure 1–24 agents. Each seat has an
explicit engine, exact model or visible provider-default option, device, effort, role,
characteristics and instructions. Add, duplicate, remove or move seats; increasing the count
explicitly copies the last seat. There is no three-member preset limit. Saved choices remain
exact when the catalogue changes. Ollama requires an exact model. Unsupported adapters, device
placements or settings refuse before dispatch rather than silently choosing another agent.

With **Use configured team** enabled, Check statements, See next task and Run statements send
that team with the original English document. It overrides the single statement worker without
rewriting the editor. Each Ask uses fresh profiled typed requests for its selected candidates with
the declared inputs; native checks and voting still govern the result. An existing checked-winner
search rule can stop later candidates once its requirement is met. An explicit per-Ask provider
selection cannot be silently replaced by the configured team. Roles and model agreement are not
proof that a free-form objective is true. Optional temperature and seed settings apply only to
supported Ollama typed requests; vote weight is explicit. The typed-adapter catalogue, including
its supported device placements, is distinct from general interactive-agent availability.

**Statement worker and limits** retains the original single-worker route when the configured-team
switch is off, including older saved drafts. **Examples and statement guide** and **Your instruction
circuit** retain examples, grammar help, source diagnostics and the source-linked circuit.
The grid plays saved checked frames without another model call. **Open full run** exposes the
existing trace, stop, resume and lock controls. Original English, source map, compiler identity
and the frozen team digest remain with the native run.

In **Agent task**, configured members run sequentially in their chosen order, each with a fresh
session. **New team for each line** repeats the team for each nonblank line. A confirmed stop
precedes the next session; files on the same selected device persist in its workspace. Different
devices keep separate checkouts, with no implicit file transfer or previous-member chat.
General project seats use individual engines and do not accept temperature/seed overrides that
their native coding CLIs cannot honor. Turn off **Use configured team** to access the complete
single-agent workflow and existing three-agent-pipeline, council and squad controls; those aggregate engines
retain their native semantics rather than masquerading as typed team seats. The shared durable
composer uses the exact same instruction field and retains uncertain submission identities for
reconnect. See [Symblic Terminal](TERMINAL.md) for working folders, completion and recovery.

Running English programs publish a bounded snapshot after each output. The page
follows new frames as they arrive and retains playback when the run ends. A retry
removes any rolled-back output from the snapshot. At most 128 recent outputs and
1 MiB of output data appear in a running snapshot; the page identifies omissions,
and the final report retains the full result.

The relative CLI commands below run from `the host checkout` on
The host.

```sh
tools/symblic english check examples/english/falling-number.english.txt
tools/symblic english preview examples/english/falling-number.english.txt --json
tools/symblic english run examples/english/falling-number.english.txt --dir /tmp/my-symblic-run --max-calls 12
tools/symblic english resume /tmp/my-symblic-run --json
tools/symblic lock /tmp/my-symblic-run
```

Choose a new empty directory for each run. Native `run --dir` refuses to overwrite
an English run; native `replay` validates its original instructions. Portable locks
retain the English as `authoring`, and replay returns it as `recorded_authoring`.
Resume uses the saved compiled program and its execution pins; it does not silently
recompile with a newer compiler. New compilation refuses a stale loaded compiler
until the dashboard restarts.

The existing operator-only API provides `GET english/examples` and
`POST english/check`, `english/preview`, `english/run` under
`/api/automation/symblic/`. POST fields are `source`, optional `by`, `title`,
`retries`, `max_calls`, `budget` and `team`. A team has `version: 1` and 1–24 `members`, each with
`id`, `engine`, `model`, `node`, `effort`, `role`, `characteristics`, `instruction`, `settings` and optional `weight`. Defaults are Qwen 4B on admitted worker nodes,
two corrections, 64 model calls and 12000 context characters. A zero call budget
allows checking and preview but refuses model dispatch.

```text
Remember width is 20.
Remember 'row 0' is 6.
Ask for 'row 1' as a whole number: "Subtract 1 from the numeric CONTEXT value named row_0. Return the difference.".
Using only 'row 0'.
Accept only if 'row 1' equals 'row 0' minus 1.
Accept only if 'row 1' is at least 0.
Display 7 at column 5 and row 'row 1' on a grid width columns by 7 rows.
```

## Statements

Every statement ends with a period. It may continue across lines. Keywords are case-insensitive.

| English | Native | Notes |
|---|---|---|
| `Remember <name> is <literal>.` | `let id = literal.` | defines a name once |
| `Ask for <name> as <shape>: "<instruction>".` | `ask id: Type "instruction" [from …] with context=none, determine=false, solve=false, retries=R, budget=B.` | one model ask; the instruction is kept verbatim |
| `Using only <name>, <name> and <name>.` | the ask's `from` list | belongs to the Ask for directly above; at most one per ask, before its Accept lines |
| `Accept only if <answer> <comparison> <operand>.` | `ensure … else retry because "<the English statement>".` | belongs to the Ask for directly above; checks that ask's own answer |
| `Show <name>.` | `show id.` | ordinary output |
| `Display <value> at column <x> and row <y> on a grid <width> columns by <height> rows.` | `show {kind: "grid", value, x, y, width, height}.` | a plain record; the renderer is the host's |

**Shapes:** `a whole number` → `Int`; `a whole number from A to B` → `Int in A..B`; `a number` →
`Number`; `a number from A to B` → `Number in A..B`; `text` → `Text`; `yes or no` → `Bool`;
`one of "a", "b" or "c"` → `one of {"a", "b", "c"}` (2–32 labels made of letters, digits, spaces,
`'`, `-` and `_`).

**Comparisons:** `equals` (`=`), `does not equal` (`!=`), `is at least` (`>=`), `is at most`
(`<=`), `is more than` (`>`), `is less than` (`<`). Ordering comparisons need numbers. Text and labels
compare only for equality. Yes/no compares only with yes/no.

**Operands:** a name, a literal, or one arithmetic step: `<term> plus|minus|times|divided by <term>`
over numbers. Chains (`a plus b plus c`) are refused, so English and native precedence can never
disagree. Remember an intermediate value or ask for it instead. Division by a literal zero is refused.

**Literals:** whole numbers `7`, `-3`; decimals `0.5`; fractions `3/4`. All are exact, and there are no
exponents, separators or leading/trailing dots. Text is `"…"` with the escapes `\"`, `\\`, `\n` and
`\t`; a raw line break inside the quotes is also kept. Booleans are `yes`/`no` (or `true`/`false`).
Because a number needs digits after its decimal point, the statement-ending period is never ambiguous:
`Remember r is 5.` is the whole number 5.

**Names:** one word (`width`, `row_1`), or several words in single quotes (`'row 0'`, `'internal note'`).
Names compare case- and space-insensitively. Each maps deterministically to a readable native id
(`'row 0'` → `row_0`). A native builtin, constant or keyword gets `_value` (`sum` → `sum_value`,
`e` → `e_value`). A leading digit gets `n_`. Accents are dropped (`'Café'` → `cafe`). The following
are refused:

- a second definition of a name;
- two names that map to the same native id (`'next y'` and `'next-y'`);
- a use before the definition ("defined later, at line N");
- an undefined name;
- an ask that selects its own answer;
- a name selected twice;
- a bare name that is a literal or operator word (`yes no true false plus minus times divided by and or`).

Quote such a name to use it.
The worker's context uses the mapped native name. In instruction quotes, name
that input explicitly (for example, `row_0`), so a small model can distinguish
the variable's value from a number appearing in its label. Check **See next task**
to inspect the exact inputs and instruction together.

**Comments:** a `#` at the start of a statement (also right after a period) runs to the end of the line.

## The direct-step contract

- **Profile:** the program starts with `use profile=verified.`
- **Ask options:** every ask carries `context=none, determine=false, solve=false` in its own `with`
  clause. A per-statement option takes precedence over `use` defaults and host options natively. A
  host `solve=true` or `context=all` therefore cannot turn a compiled ask into a kernel-solved or
  wider-context ask. Tests prove this with a uniquely determined finite ask: it still makes one model
  call.
- **Host options:** `compile_source` returns
  `options = {profile: verified, context: none, determine: false, solve: false, constructor: off, max_calls}`.
  There is no option for the constructor, a solver, paths, hosts or models.
- **Caller options:** `retries` (0–5, the native maximum), `max_calls` (0–10000) and `budget`
  (capsule characters, 1000–100000). Each must be an exact `int`; `bool` and floats are refused.
- **Verbatim text:** after generating, the compiler parses the program with the native parser. It refuses
  unless every ask's instruction comes back as exactly the author's text, braces and quotes included.
  The native interpolation `{…}` is escaped, so `{secret}` in an instruction or literal is literal text,
  never a read.

## Determinism

A compiled program is a pure function of the English text and the three integer options. The result
carries `source_sha256` (the original text) and `version` so a host can pin both. Runtime determinism
is exactly the native runner's: a recorded run replays through `symblic.kernel.lockfile.replay` with zero model
calls and the same fingerprint, and `symblic.kernel.execution_pins` pins refuse a changed source. Nothing stronger is
claimed. A fresh run of a model ask can return a different accepted answer.

## API

The Python compiler API:

- `compile_source(text, *, retries=2, max_calls=64, budget=12000)` raises `EnglishError` (`.line`
  `.col` `.code` `.message`, positions in the original text).
- `check_source(...)` never raises for an author error. It maps native `check` errors and warnings back
  to English positions (`ENG_NATIVE`, `ENG_NATIVE_WARNING`) and keeps the native row verbatim.
- `EXAMPLES` and `examples()` give the examples.

## How the metaphor maps to the runtime

| Idea | What exists natively | Limit |
|---|---|---|
| An atomic instruction | one `Ask for` = one native `ask` statement (one capsule, one typed answer) | the model may still do more work internally; only the answer is checked |
| A fresh mind per step | each ask builds a new capsule from scratch (`context=none`), with a distinct request key; nothing from earlier calls is carried unless selected | the same applicator or model process may serve several asks; the runtime gives no process or weight isolation |
| Selected context | `Using only` → `from`: exactly those values (with provenance) appear under CONTEXT; tests check that no other binding name or value appears in the prompt or the context manifest | the instruction text itself is visible, so do not put unselected values in it |
| Typed outputs | the shape becomes a native type and JSON schema; verified strict coercion refuses `true` for a number, `2.5` for a whole number and labels outside the set | native verified coercion still accepts declared numeric wire strings (`"3"` for a whole number) |
| Semantic constraints | `Accept only if` → anchored `ensure … else retry`. Retry feedback quotes the author's sentence and the native check, never an unselected value | a weak or wrong check accepts a wrong answer; checks prove conformance to what is written |
| Bounded effort | `retries` per ask (≤5), `max_calls` per run, `budget` per capsule; exhausting retries fails the run at the mapped English line | — |
| Evidence and replay | the native run folder, trace, lock and replay; `source_map` links every native line to its English statement | the compiler does not store anything; the host saves the English text, compiler version and source map with the run |
| A picture | `Display` → a plain grid record; positions a model produced are guarded by a native `assert` (0 ≤ x < width, 0 ≤ y < height, 1 ≤ size ≤ 100, at most 2500 cells) | drawing is the host renderer's job; no HTML/SVG is generated |

**Missing mechanisms in the scalar statements above (stated, not faked):**

- **Arbitrary English.** There is no model translator; unknown phrasing is refused.
- **Compound conditions and longer arithmetic.** There is no `and`/`or` inside one Accept line (write
  several Accept lines) and no multi-step arithmetic.
- **Advanced native expressions.** This compiler offers no escape hatch for writing native Symblic
  inside English.
- **Static guarantees beyond the literals.** Bounds on model-produced positions are enforced at run
  time by `assert`, not proven statically.
- **A fresh model process per ask.** Isolation of model processes is a property of the applicator, not
  of this compiler.
- **Lists, records, loops and branches.** These are not supported; write native Symblic for them.

## Examples

`examples/english/`:

- **`falling-number`:** six fresh model asks. Each computes the next row from the previous row only;
  the checks are equality and bounds; each verified frame is displayed.
- **`categorize`:** a remembered message is classified into one of three labels. The ask sees the message
  and not the remembered internal note.

Each example has a `.compiled.sym` with the generated native program; a test keeps them in sync.


## Construct an animation from English

A document beginning `Build a character animation called Matrix rain.` selects the
bounded construction lane in `symblic/english/build.py`. Its author source uses
ordinary English sentences without digits, code, signatures or data records.
The [complete example](../../examples/english/matrix-rain.english.txt) names small tasks
for letters, movement, leading positions, trailing positions, shades, individual
characters, columns, frames and the complete animation. Each assembly task uses
the accepted pieces from smaller tasks. Titles and step names may change; the supported rule and
check sentences have explicit meanings. Unknown or incomplete sentences refuse
with their original source location. This is a supported construction vocabulary,
not an unrestricted English translator.

Each step becomes a real `Code js` ask through the selected applicator. The host
supplies generated interfaces and finite checks, but no candidate implementation
or fallback answer. Only the selected earlier code enters the model capsule.
Returned code runs in the existing JavaScript sandbox, first with its declared
runtime dependency closure and then with the preceding assembled program. One
retry gate checks both results. This checks finite behavior in both scopes; it
does not prove that every execution calls each selected helper, or that arbitrary
replacement code preserves earlier behavior outside those checks.

Construction version two adds the individual-character and column tasks. The
earlier seven-task document remains supported and retains its native lowering.
The finer example separates making one character, collecting a column and
collecting columns into a frame. This responds to an actual Qwen run that accepted
the first five primitives but exhausted its frame corrections. A failed run has
no accepted animation; its failure record remains intact.

The standard character canvas is an explicit preset: thirty-two columns,
twenty-four rows, trails of eight characters, top-left origin, green characters
on black, and twenty-four frames per loop. Normal movement is one row per frame;
double movement is two. The palette has eight shades, from bright to dark.
Compiled construction metadata retains these values, every original statement,
selected inputs, interfaces and check coverage. The circuit distinguishes model
memory from code used during candidate checks. Its gates remain marked not run.

The accepted model code produces character-grid data. The existing player draws
those recorded cells and supplies playback timing and controls. It does not invent
rain positions or letters. English runs save the exact author document, accepted
implementation and frames. The English compiler identity includes the construction
helper for this lane; older scalar documents retain their existing compilation
and source identity. Actual model results require their own run receipts.

The recorded Matrix rain run (recorded on the original host; not public)
completed all nine tasks with Qwen in ten calls, including one rejected trail
answer that Qwen corrected. Its exact generated program passed forty-four frozen
held-out cases and a separate preset recheck. Desktop and phone playback matched
the saved frame data. The [evidence receipt](evidence/2026-10-06-english-matrix.json)
retains the earlier failed run and the limits of these checks.
