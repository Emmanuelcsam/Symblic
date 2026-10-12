# symblic/constructor: answering an ask without a model, durably

**What this package explores.** Some `ask` statements have contracts a solver can satisfy directly: the anchored
`ensure` lines are linear arithmetic over the answer (see `symblic/linear`). This package is the bridge that lets
an ordinary Symblic run use that solver *safely*: every attempt is announced in a journal before anything is
dispatched, every candidate is re-checked by the run's own contract before it is adopted, a crash can never cause
a silent second attempt, and the whole configuration (mode, limits, solver runtime, the hashes of the code that
did the work) is pinned in the run folder so a resume or replay cannot change it.

**Status: prototype.** 199 unit tests cover the bridge, the journal (including real child processes killed at
chosen points), the records, the lockfile integration and the read-only inspector, all with a fake solver worker.
The real Z3 worker is optional and was only exercised on the development machine.

## The modules

| Module | What it does |
| --- | --- |
| `core.py` | `Bridge`: created by `symblic.kernel.run.Run` when the run option `constructor` is `linear` or `linear_diagnose`. Builds each attempt's request, calls `symblic.linear.constructor.assess_ask`, re-checks and selects candidates, journals everything. |
| `journal.py` | `constructor-events.jsonl`: an append-only, hash-chained stream of `open`, `intent`, `outcome`, `reconcile` and `repair` rows with strict reading; `Journal.begin` / `Journal.complete`; `reconcile` and `repair_torn_tail` for the operator. |
| `records.py` | `constructor-config.json` (mode, limits, runtime record, implementation hashes) and the checks that bind a journal to a run and a `solver_proposal` claim to an accepted outcome. |
| `inspect.py` | `tools/symblic constructor inspect FOLDER`: a read-only classification of a run folder and what may safely be done next, by whom. |

## Modes

| `constructor` option | What happens at a linear ask |
| --- | --- |
| `off` (default) | Nothing; the run never imports this package. |
| `linear_diagnose` | The solver is asked and its proposal is journaled, but the model still answers. |
| `linear` | An accepted, re-checked solver value becomes the answer (origin `solver_proposal`); otherwise the run falls back to the model. |

Both enabled modes need a run folder (`--dir`); the command line sets `determine=false` and `solve=off` for them
(the kernel's own finite search and the constructor do not overlap). Limits: `--constructor-attempts`,
`--constructor-milliseconds`, `--constructor-attempt-ms`, `--constructor-resource-limit` (see
`tools/symblic run --help`).

## Recovery in one paragraph

An attempt whose intent was journaled but whose outcome was not is *uncertain*: the worker may have run. The
run refuses to continue until the operator decides (`journal.reconcile`, which records a decision, not proof),
or a new run is started in a new folder. `inspect.py` reports this and every other state with an explicit list
of next steps, and its reports never authorize a retry.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/constructor -t .
```

Run from the repository root (a few minutes; some tests start child Python processes). No model, no network
and no real solver are used. The original host's run API with constructor options is tested in
`tests/integration/test_symblic_constructor_api.py` and `test_symblic_constructor_controls.py`, which skip
without the host.

Further reading: `docs/reference/CONSTRUCTORS.md`, `docs/reference/CONSTRUCTOR-CLI.md`,
`docs/reference/CONSTRUCTOR-LOCKS.md`, `docs/reference/CONSTRUCTOR-PROVISIONING.md`.
