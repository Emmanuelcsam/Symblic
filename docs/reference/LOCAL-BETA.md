# Local beta: Symblic lanes with light local models

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

`symblic/bench/local_beta.py` runs Symblic trials with light Ollama models on the worker nodes and writes one ledger
row per trial. It never calls a model itself. Each trial runs a lane's own CLI with the model pinned to one worker node
(`ollama:MODEL@NODE`), and the fleet runner admits it there. Tests: `tests/bench/test_symblic_local_beta.py` (fakes only).

```sh
python3 symblic/bench/local_beta.py fixtures                 # registry: lane, file, expected check
python3 symblic/bench/local_beta.py plan --batch first       # the trials a batch would run (no model)
python3 symblic/bench/local_beta.py batch --batch first [--pair gemma3:1b@node-b ...] [--batch-id ID]
python3 symblic/bench/local_beta.py batch --batch second   # exact then fine 37-unit sheets, samples 1 retries 3 rounds 1
python3 symblic/bench/local_beta.py trial --lane native --fixture minutes-split --pair qwen3:4b-instruct@node-d
python3 symblic/bench/local_beta.py report [--batch ID] [--json]
python3 symblic/bench/local_beta.py rejudge ID     # a run that did not finish, judged again from its saved output
```

`rejudge` appends a new row with `supersedes: ID`, and the report counts that one. The original row stays in the
ledger. It only covers spec, native and English runs that did not finish, because a finished run would need its
expected checks or the harness again. An inconclusive kernel check counts as `error`: the kernel itself reports
"No candidate verdict", for example when its JavaScript sandbox runs past its wall clock on a loaded the host.

Ledger: `~/.local/state/symblic-local-beta-20261011/ledger.jsonl`. Run folders are kept under `runs/<trial id>/`,
with the exact command (`*.cmd`), stdout/stderr and the lane's run record. Set `--state DIR` or
`SYMBLIC_LOCAL_BETA_STATE` to use another location. Each row has lane, fixture, model, node, attempt, started/ended,
`seconds` (the lane's wall time after the gate; `waited_seconds` is the gate), `calls` (rows of the run's
`calls.jsonl`; for research, tool steps + 1), outcome, reason, evidence, `call_nodes`/`placement_ok` and the
worker node's temperature before and during the trial. `model_seconds` sums each call's latency including time spent
queueing for the worker node's single model slot, so parallel votes or candidates can exceed the wall time.
`ollama_seconds` is Ollama's own reported duration (load, prompt and generation). `code_sha256` holds the sha256 of
this script, `symblic/js/normalize.py`/`.js`, `symblic/kernel/run.py`, `symblic/kernel/language.py`, `symblic/spec/sheets.py`, `symblic/js/check.py` and
`symblic/providers/applicators.py` at trial start, so a before/after is attributable. `code_changed_during_trial` lists any of them
that changed before the trial ended. Spec rows also keep `settings` (samples, retries, rounds) and per unit the calls,
retries (sample index 1000 and up), re-sampled retries (another temperature or seed than the candidate's first
attempt) and byte-identical repeated replies. They also keep the unit a failed build stopped at, with its last
attempt's first failing example and the first 200 characters of the model's last reply.

## Rules the script enforces

- **Models.** Only the light models are accepted: qwen3:4b-instruct, phi4-mini, gemma3:4b, ministral-3:3b,
  qwen2.5-coder:3b, granite3.3:2b, deepseek-r1:1.5b, gemma3:1b, llama3.2:1b and qwen2.5:0.5b. Pairs name a bare
  Ollama model. An applicator kind such as `claude:` is refused.
- **Nodes.** node-b and node-d by default. node-a, node-f and node-i need `--allow-reserved` (they host the Kirby
  build tonight). The host, node-h, node-arm and node-standby are always refused. The spec lane also refuses to run a
  compiled program that names any applicator other than the pinned one.
- **One model per worker node.** A batch runs each worker node's trials one after another and the worker nodes in parallel. Before
  each trial the script reads `/api/cluster/status?force=1` and `/api/runner/runs?status=active`. It waits
  (default 600 s while hot, 900 s while busy) and then skips when the worker node is above 80 °C or another model run
  holds it. It also skips when the worker node is offline or its temperature cannot be read. In a batch, a model that
  `bin/local-research --list` does not show on that worker node is skipped too.
- **No silent retries.** Every run is a row with its own attempt number and folder. A trial in progress has
  `intent.json` and no row yet. `report` lists it as running while its batch process lives, and as interrupted
  (no verdict) once that process has ended.
- **Time.** Lanes 1 and 2 pass `--ollama-limits {"num_predict":2048,"timeout_seconds":900,"total_timeout_seconds":T}`.
  T is 3600 s for the 13-unit sheet and 900 s for a native fixture; the last field is the run's own wall budget.
  Every lane also has an outer cap. Past it the process group gets SIGTERM, then SIGKILL, and the fleet runner runs this trial
  started on that worker node are cancelled. The row is a timeout.

## Lanes and what counts as a pass

| # | lane | command (pinned) | pass |
|---|---|---|---|
| 1 | spec | `symblic/spec/sheets.py compile SHEET --by ollama:M@NODE --samples 2 --retries 3 --rounds 2`, then `tools/symblic run build.sym --dir RUN --json --ollama-limits ...` | every unit passes its `js_test`, and the Atomic harness passes 500/500 random documents and 8/8 plain documents against the reference |
| 2 | native | `tools/symblic run F.sym --by ollama:M@NODE --dir RUN --json --ollama-limits ...` | run `done` (every ensure/assert held) and each expected output is an exact match |
| 3 | english | `tools/symblic english run F.txt --dir RUN --by ollama:M@NODE --max-calls N --json` | run `done` and the expected outputs match |
| 4 | delegate | `tools/symblic delegate run T.json --dir RUN --by ollama:M@NODE --agent-json` | `accepted` and the result equals the expected value |
| 5 | ladder | `tools/scripts/symblic_frontier_ladder.py` plan → materialize → freeze → session → aggregate | per rung: the bench's own success (done, every hidden case, within budget) |
| 6 | research | `bin/local-research --model M --node NODE --tools 4 --json "Q"` | the ANSWER contains the expected string, ignoring case and spacing |

Outcomes: `pass`, `fail` (with the first failing check as the reason), `refused` (the lane or the model declined),
`timeout`, `error` and `skipped`. An `error` means the trial reached no verdict about the model, for example a call
placed off the pinned worker node or an unreadable result. A `skipped` trial never started. The scoreboard counts every
trial that started; skipped trials are listed apart. A pass with zero model calls is flagged, because the kernel
decided it alone.

Lane 5 is a separate, long trial. F1 at 900 s per rung is estimated at about 1.7 h, over the one-hour worker node bound,
so `trial --lane ladder --fixture ladder-F1` refuses before freezing anything unless `--approve-over-hour` records
the operator's approval. Batches never include it.

## Fixtures

The Atomic study sheets (`~/.local/state/symblic-atomic-20261010/sheets/`): markdown 13 units, fine 37, exact 37.
Native: `examples/01-four-plus-four.sym` and `examples/05-word-problem.sym`. The ensure in 05 only checks for a
whole number of at least 0, so the expected 44 is checked here. `examples/44-small-model-math.sym` replays
model-written code with no model call: a kernel-only control. Two new tiny fixtures are in
`benchmarks/local-beta/`: `count-and-prime.sym` (the kernel computes the letter count and primality) and
`minutes-split.sym` (two chained asks). English: `falling-number`, `categorize` (the expected label is checked here,
because an Accept line would quote the answer back on retry) and `benchmarks/local-beta/change.english.txt`.
Delegate: `examples/agent-handoff.task.json` and `benchmarks/local-beta/complaint.task.json`. Research: two DOI
titles read from Crossref on 2026-10-11.

A pass shows that one trial met these checks once on that worker node. It does not show reliability (use repeats: each
is a row), correctness beyond the examples and harness, or anything about other prompts.
