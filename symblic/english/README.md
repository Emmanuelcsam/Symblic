# symblic/english: plain-English statements

Write a model-backed program as short English sentences instead of Symblic syntax, and keep every model answer
checked by code:

```
Remember digit is 7.
Remember 'row 0' is 6.
Ask for 'row 1' as a whole number: "Subtract 1 from the numeric CONTEXT value named row_0. Return the difference.".
Using only 'row 0'.
Accept only if 'row 1' equals 'row 0' minus 1.
Display digit at column 5 and row 'row 1' on a grid 20 columns by 7 rows.
```

Each `Ask for` becomes one model request in a fresh context that sees only the values its `Using only` line names;
each `Accept only if` becomes a kernel check, and a failing answer is retried with the reason. There is no model
translator: the compiler is a fixed grammar, the English text is data, and the result is an ordinary Symblic program
run by the kernel. The grammar and its limits are in `docs/reference/ENGLISH-STATEMENTS.md`.

## The modules

| module | what it does |
|---|---|
| `compiler.py` | the statement grammar: `compile_source`, `check_source` (never raises for an author error), a source map from program lines back to English lines, and two built-in examples |
| `build.py` | a second grammar, "Build a character animation called ...": each English step becomes one model-written JavaScript function, checked against cases derived from the step's obligations, and the accepted functions produce the frames (example: Matrix rain) |
| `pixels.py` | a third grammar, labelled documents ("STATEMENT ZERO ONE: ..."): a raster animation described in numbered statements becomes a spec sheet of small JavaScript units built with task cards (`symblic/spec/build.py`) (example: a white dot crossing the screen, 34 statements) |
| `pixel_checks.py` | checks for `pixels.py` that run every candidate inside the exact browser pixel interpreter of the web studio, pinned by SHA-256 |
| `authoring.py` | `prepare`: compile a document and attach an authoring record (the exact document, the hashes of the compiler files used, the program's hash, the source map); `validate_saved` checks a saved run against its record |
| `cli.py` | the `english` command: `check`, `compile`, `preview`, `run`, `resume`, `examples` (`python3 -m symblic.english.cli ...` or `tools/symblic english ...`) |

`compiler.compile_source` recognizes the other two grammars by their first words and hands them to `build.py` or
`pixels.py`; `authoring.prepare` wraps all three; `cli.py` runs the result on the kernel's runner.

## Try it

```
python3 -m symblic.english.cli check examples/english/falling-number.english.txt      # no model
python3 -m symblic.english.cli compile examples/english/categorize.english.txt        # no model
python3 -m symblic.english.cli run examples/english/falling-number.english.txt \
  --dir /tmp/falling --by ollama:qwen3:4b-instruct                                    # asks the model
```

A run folder keeps the document (`instructions.english`), the program, every call and the results; `resume` continues
it, and `python3 -m symblic.kernel.lockfile lock FOLDER` then `... replay FOLDER/run.lock.json` replays it with no
model.

## Status

The statement grammar (`compiler.py`) is the most used and tested part. The construction and pixel grammars each have
one worked example and are tested with fake models only; they are experimental. `preview` needs the kernel's bounded
preview process (`symblic/kernel/process_limits.py`); where that is unavailable it says so. Statements a check cannot
establish (that a physical monitor showed a frame, that a timer fired) are recorded as obligations, not as passed.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/english -t .
```

Fake models and temporary folders only. The JavaScript tests need Node.js 22 and Linux Landlock and are skipped
without them; a few JavaScript checks have a 3-second budget per case and can time out on a heavily loaded machine.
The host-only HTTP route tests are `tests/integration/test_symblic_english_routes.py` and
`tests/integration/test_symblic_english_entry.py` (skipped without that host).
