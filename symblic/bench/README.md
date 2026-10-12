# symblic.bench — measuring Symblic against ground truth

**Status: measured machinery.** This package contains the runners and scoring rules used to measure Symblic:
they generate or load items, ask real applicators, grade answers with code, and keep every failure in the
denominator. The machinery itself is tested with fake applicators (`tests/bench`). This README makes no claim
about how well any model or Symblic itself performs; results from the original system are reported, with their
limits, in `docs/reference/RESULTS.md`, `docs/reference/MATCHED-EVALUATION.md`,
`docs/reference/AMBIGUITY-BENCH.md` and `docs/reference/LOCAL-BETA-REPORT-2026-10-11.md`.

Like the rest of Symblic, this code was written by AI coding agents.

## What is in this package

| File | What it is |
|---|---|
| `bench.py` | The benchmark runner and its command line. Suites: identity, arith, logic, flower, shape, tighten; it also dispatches the ambiguity and matched suites. |
| `ambiguity.py` | Ambiguity benchmark: does a model ask for the one missing preference instead of guessing? Frozen assignment, one first attempt per cell, journaled calls. |
| `matched.py` | Matched evaluation: the same tasks asked directly and through a typed Symblic capsule, under frozen, counterbalanced controls with durable dispatch receipts. |
| `eval_protocol.py` | Pure scoring core shared by `matched.py` and MICA's benchmark: arms, plans, receipts, summaries. |
| `local_beta.py` | Local beta: runs the repository's own CLI lanes with small local models pinned to configured nodes, one ledger row per trial. |
| `code_pins.py` | SHA-256 digests of the source files a result depends on (repository-relative paths). |
| `data/ambiguity-v1.json` | The synthetic ambiguity dataset: 42 cases in 14 families (documented in `data/ambiguity-v1.md`). |
| `data/matched-example-v1.json` | An example matched-evaluation manifest using `fake:` applicators. |
| `data/local_beta/config.example.json` | Example local-beta configuration: models, nodes, fixtures, batches, optional monitoring commands. |
| `data/local_beta/fixtures/` | The small Symblic programs, English statements and delegate tasks the local beta runs. |

## How the pieces fit

```
python3 -m symblic.bench.bench --suite identity,arith,...   ─► Bench ─► Applicators ─► results.jsonl ─► report.md
python3 -m symblic.bench.bench --suite ambiguity ...        ─► ambiguity.make_plan ─► run ─► summarize
python3 -m symblic.bench.bench --suite matched ...          ─► matched.freeze ─► MatchedBench.run ─► summary
                                                                       └─ eval_protocol (plans, records, scoring)
python3 -m symblic.bench.local_beta batch --batch first     ─► one process per lane command ─► ledger.jsonl
```

Every model call goes through `symblic.providers.applicators.Applicators` (see `symblic/providers/README.md`):

* `ollama:MODEL` or `ollama:MODEL@NODE` — an Ollama server; NODE is a label from `SYMBLIC_OLLAMA_HOSTS`.
* `command:NAME` — a command-line agent you configured as `SYMBLIC_COMMAND_NAME` (for example a CLI coding agent).
* `fake:LABEL` — scripted answers for dry runs and tests.

## What is measured machinery and what is a research claim

* **Measured machinery** (tested, makes no claim by itself): the benchmark runner's cell bookkeeping and resume,
  the item generators (seeded, deterministic), the graders, the ambiguity and matched protocols and their
  receipts, the local beta's trial lifecycle, ledger and judges.
* **Research claims** live in the documents listed at the top, each with its denominators and limits. Notable
  limits stated by the code itself: prose answers in the legacy suites are graded heuristically; answers in one
  cell share questions and applicators, so they are not independent draws; the ambiguity labels are synthetic
  and author-stipulated; the matched evaluation measures one typed decision per case, not multistep work.

## Run it

```sh
# a quick smoke run of two suites with local Ollama models (pull the models first)
python3 -m symblic.bench.bench --out /tmp/symblic-bench --suite identity,arith --quick

# freeze the ambiguity assignment without any model call, then run it
python3 -m symblic.bench.bench --suite ambiguity --out /tmp/amb --ambiguity-apps ollama:qwen3:4b-instruct --dry-run
python3 -m symblic.bench.bench --suite ambiguity --out /tmp/amb --ambiguity-apps ollama:qwen3:4b-instruct --resume

# freeze the example matched experiment and print its report (every cell still pending; no model is asked)
python3 -m symblic.bench.bench --suite matched --out /tmp/matched --matched-manifest symblic/bench/data/matched-example-v1.json --dry-run

# the local beta: copy the example configuration, name your Ollama nodes and models, then plan and run
cp symblic/bench/data/local_beta/config.example.json my-beta.json
python3 -m symblic.bench.local_beta --config my-beta.json plan --batch first
python3 -m symblic.bench.local_beta --config my-beta.json batch --batch first
python3 -m symblic.bench.local_beta --config my-beta.json report
```

## Tests

```sh
cd <repository root>
DASH_TEST=1 python3 -m unittest discover -s tests/bench -t .
```

No test calls a model, opens the network or starts a lane: applicators and the local beta's environment are fakes.

## Differences from the original host

The original runners lived inside a private home-server system. These parts were removed or turned into
configuration so the package runs with this repository alone:

* `bench.py` paused new cells while a compute node ran hot (it read the host's cluster status). That hold is gone;
  the default applicator lists are now small local Ollama models instead of the original mix of hosted CLI agents
  and named machines, and the council conditions run only when you pass `--council`.
* `local_beta.py` placed trials on named machines and refused the machines that served other duties. The model
  list, the node list (with reserved and excluded nodes), the fixtures, the batches and the optional temperature,
  active-run, cancel, inventory and research commands are now read from a configuration file. Without monitoring
  commands there is no heat or busy gate; the inventory comes from the configured Ollama hosts.
* The research lane depended on a private local search tool; it runs only when you configure
  `commands.research`, and is skipped (with that reason) otherwise. The spec lane needs spec-sheet fixtures with a
  whole-file harness; none are configured in the example, because the original study's sheets were not published.
