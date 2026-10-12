# Benchmarks

Benchmark fixtures that are data, kept apart from the code that runs them. (Datasets that belong to one module live
beside it: the ambiguity and matched-evaluation data are in `symblic/bench/data/`.)

## `frontier/`: the frontier ladder (prepared, never run)

**Question.** Can organization add capability that the weights alone lack? Hold one small local model, one machine
and one budget fixed, and change only how the work is organized: the six construction modes of `symblic/mica`
(`direct` whole program, `static` decomposition, `decompose_on_failure`, `capability` routing, `search` over
alternative plans, and `mica`, routing plus search). If some modes reach hidden passes on task families that the
whole-program mode misses, organization changed what the same model could build.

**Status, honestly.** The ladder was prepared on 2026-10-10 and has **not been run**: no result exists. A related
pilot with qwen3:4b-instruct (1 800 s and 24 calls per assignment) had no hidden pass, so current evidence does not
support the hypothesis yet. One repetition could not establish statistical significance or general capability in any
case.

**Files.**

| file | what it is |
|---|---|
| `ladder.json` | the manifest: family order, titles, test counts, the shared budget (300 s wall and 8 calls per assignment; 4 candidates, depth 4, 64 units, 3 workers, 2 retries, 32 768 context characters) and the SHA-256 pin of every fixture |
| `F1-integer-arithmetic.fixture.json` | `gcd`, `lcm`, `isPrime` over safe integers: 4 public tests, 56 hidden cases |
| `F2-string-utilities.fixture.json` | `slugify`, `padLeft`, `wordCount` with exact Unicode rules: 7 public, 56 hidden |
| `F3-collection-algebra.fixture.json` | `groupBy`, `histogram`, `sortBy` with own-key results and a stable sort: 7 public, 52 hidden |
| `F4-expression-tokenizer.fixture.json` | `tokenize`: three token classes, longest match, positions, errors: 4 public, 46 hidden |
| `F5-expression-evaluator.fixture.json` | `tokenize`, `parse`, `evaluate` with precedence and right-associative `^`: 8 public, 59 hidden |
| `F6-vending-machine.fixture.json` | `vend`, a sequential state machine (optional family): 3 public, 48 hidden |

Each fixture holds a `request` (the requirements, exact export signatures and public tests: the only part a builder
may see) and `hidden_tests` (graded by the evaluator after a build finishes). **Never put a whole fixture file into a
model's context**; only its `request` field may enter a construction. Because these files are public now, they are
development fixtures, not a held-out benchmark.

**How they were checked when written (2026-10-10).** An independent Python oracle computed every expected value.
Hand-written reference implementations (kept outside the repository, so no solution sits beside the fixtures) passed
every public and hidden case through the real grader (`symblic.js.check`, Node.js 22.17.0). Plausible naive
implementations that pass every public test still fail hidden cases (F1 9, F2 12, F3 13, F4 4, F5 12, F6 12): a public
pass is not a hidden pass.

**Check the pins** (no model):

```
python3 -c "import hashlib, json, pathlib; d = pathlib.Path('benchmarks/frontier'); m = json.loads((d / 'ladder.json').read_text()); print(all(hashlib.sha256((d / f['file']).read_bytes()).hexdigest() == f['sha256'] for f in m['families']))"
```

**Run it.** The planner `tools/scripts/symblic_frontier_ladder.py` (`plan`, `materialize`, `aggregate`) prints every
command; the MICA bench (`symblic/mica/bench.py`, `tools/symblic mica benchmark`) freezes and runs the six modes per
family. The design, controls and limits are in `docs/reference/FRONTIER-LADDER.md`. Budget about 42 minutes of model
time per family at 300 s per assignment (six assignments plus grading), and expect an empty table on a slow machine:
at 300 s a CPU-only machine may allow only a few calls of a 0.5B model, which is a budget result, not a verdict.
