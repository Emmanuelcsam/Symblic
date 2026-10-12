# Underlines and your instruction circuit

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

The **Write** and **English** editors check your source as you type. Errors have red wavy underlines; warnings have amber underlines. The problem list gives the message and location in words, so you can use it without relying on color.

## Find and fix a problem

1. Pause briefly after typing to let the source check finish.
2. Click or tap a problem below the editor to select its location. With the editor focused, **F8** selects the next problem and **Shift+F8** selects the previous one. On a desktop, hovering over an underline shows its explanation.
3. Edit the source. Earlier underlines clear immediately while the new check is pending.

For example, this native program has a syntax error at the closing parenthesis:

```symblic
let total = 1 + ).
```

Changing the expression to `1 + 2` fixes that syntax error. Passing a source check still does not establish that the program calculates what you intended.

The same controls work for a `.symd` paper in **Write**. Diagnostics refer to the original paper, including mapped Symblic code blocks. In **English**, they refer to your original instructions rather than the generated native program.

When the checker identifies a token, that token is underlined. Some checks identify only a line or an insertion point; the problem list says so. Diagnostics without a reliable source location remain in the list. A generated native diagnostic may map only to an English statement's line. The editor does not invent a more precise position.

## Read the English circuit

Open **English** and enter:

```text
Remember base is 7.
Ask for result as a whole number: "Add one to base. Return the sum.".
Using only base.
Accept only if result equals base plus 1.
Show result.
```

After the source check succeeds, **Your instruction circuit** shows these components:

| Component | What it means |
|---|---|
| Input | `Remember` supplies a named value. |
| Worker | `Ask for` declares one model task and its answer type. |
| Selected inputs | `Using only` names the values included in that worker's context. |
| Check gate | `Accept only if` declares the predicate that must pass before execution advances. |
| Output | `Show` or `Display` presents a value. |

The `result` worker reads `base`; its check gate reads `result` and `base`; the output reads `result`. Each named connection links to the source line that supplies that value. Clicking a component's line button selects its original instruction.

Connections come from the compiled program's parsed reads and bindings. A word appearing inside the quoted instruction does not automatically create a connection. **Using only** is the explicit wiring for model context.

This view covers the straight-line English grammar. It preserves the authored statements and can show generated grid checks, but it does not display runtime values or turn the source into a new execution format. Its check gates say **not run** because this view describes declarations. Running the program produces a separate run record; the circuit itself does not change into a run receipt.

## What checking establishes

Source checking uses Symblic's existing parsers, available static checks and authoring warnings. It can detect syntax errors, some name/type/option mistakes and unsafe retry structure. The existing bounded pure lint may examine predicates. It makes no model calls and starts no program, external action or subprocess.

Some faults appear only when values are supplied and the program executes. Passing examples or predicates also depends on whether those checks capture your objective. Spelling, polished English and model agreement do not establish that relationship.

Parsing can stop at the first syntax error. Long diagnostic lists are bounded, with the visible limit reported. An unavailable check is shown as unavailable rather than a passing document. Source edits invalidate the prior diagnostics and circuit. If inline ranges are unavailable on an older server, the existing Write diagnostics remain the fallback.

Use **Preview** to inspect the deterministic prefix and next model request, then **Run** when ready. For building functions from tiny checked steps, see [Build one step at a time](STEPS.md).

## Accept lines and retry feedback

A retry is honest about what it shows the model, and that honesty has a consequence for accept lines.
Retry feedback carries only what the kernel computed from the answer alone: a value from an input,
an observation or another result never reaches it. The failed check's own text is always part of the
feedback, and when the whole check reads the answer alone the kernel's error for that answer is
included too.

So an accept line is a specification the model can read, not a secret. `Accept only if wrong equals 5`
compares the answer with a value written in the line itself: on a retry the model sees that text and
can answer it directly. A passing check establishes conformance, not independent computation. When the
checker sees an accept line whose whole check reads the answer alone, it marks the line with a warning
(ENG_ACCEPT_READABLE) saying what a retry exposes, and a run's evidence names the same line as
model-readable on each retried attempt.

## Design references

- **Logic Penguin** supplies a useful example of feedback attached to individual proof lines, with unavailable references and damaged dependencies distinguished. Symblic uses its own checkers and calculus. [Inspected checker, commit da32589](https://github.com/frabjous/logicpenguin/blob/da325893b81f6be1fd20443a9218b556a2e19790/public/js/checkers/derivation-check.js).
- **TeXtidote** demonstrates how transformed text can retain ranges pointing back to the original source. It is a document and grammar linter; the Symblic underlines come from Symblic's language checkers. [Inspected source mapping, commit 241beb3](https://github.com/sylvainhalle/textidote/blob/241beb356ff37dd4495bdaa0d58721888282cd16/Source/Core/src/ca/uqac/lif/textidote/as/AnnotatedString.java).
- **Magmide** proposes separating the logic used to constrain a program from the host that executes it. Its repository explicitly describes itself as dormant and early; it is a design reference here, not a verification backend. [Inspected project description, commit 79eadf5](https://github.com/magmide/magmide/blob/79eadf59f4790bd8dbb51d2f41c437c60bcd0873/README.md).

These references informed the design. No code was copied from these repositories, and no upstream dependency or service was installed for this feature.
