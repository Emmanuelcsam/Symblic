# tools: the command lines and maintenance scripts

Every command here runs from a checkout of this repository with Python 3.12 (Node.js 22 for the JavaScript
checks some commands start). They find the repository from their own location, so they work from any folder and
through a symlink (for example `ln -s "$PWD/tools/symblic" ~/.local/bin/symblic`). Nothing needs installing for
`check`, `preview` and `replay`; running programs that ask models needs an applicator (below).

## The command lines

| Command | What it does | Needs |
|---|---|---|
| `tools/symblic` | The main entry point: `check`, `preview`, `run`, `replay` for `.sym` programs and `.symd` papers, plus `english`, `delegate`, `graph`, `spec`, `mica`, `inquiry`, `test`, `certify`, `lib`, `doc`, `paper`, `lock`, `grammar`, `constructor`, `experiments`. `tools/symblic --help` lists them all. | The `symblic` package only. `run` (and other commands that ask models) needs an applicator: `--by ollama:MODEL` with a reachable Ollama server (`SYMBLIC_OLLAMA_HOSTS`), or `--by command:NAME` with an agent command line configured (see `symblic/providers/README.md`). `memory` needs the original host. |
| `tools/symblic-task` | Client of a host's task engine: start one fresh coding agent per statement line, wait, review, resume; the autogen runs (candidates, regeneration, splits) ride on the same API. | **The original host** (`/api/symblicos/`, served by `integration/host/symblicos_engine.py`) for everything except `lint`, which checks statement files locally with `symblic/autogen/policy.py`. `SYMBLIC_TASK_URL` sets the host address (default `http://127.0.0.1:8080`, loopback only). |
| `tools/symblic-context` | A bounded, read-only pack of a few named source files for one agent task: hashes, top-level symbols, excerpts around a query (`symblic/kernel/context_packs.py`). | Nothing. With the optional tools installed (`python3 tools/scripts/install_symblic_tools.py`), excerpts come from grep-ast. |
| `tools/symblic-workcard` | Bounded workcards: typed holes, teams and steps compiled into checked programs (`symblic/authoring/workcards.py`). | The `symblic` package; filling a card asks models. |
| `tools/symblic-distill` | The distillation pipeline: records to datasets, frozen splits, training and evaluation plans, comparison (`symblic/distill/cli.py`). It never trains or downloads anything; `launch` prints the worker command. | The `symblic` package. |

How `tools/symblic` runs: the bash wrapper picks an interpreter (`SYMBLIC_PYTHON`, else `.venv/bin/python` in
the repository, else `python3`) and runs the Python program at the bottom of the file inside
`symblic/kernel/process_limits.py`, which first sets an address-space ceiling (2 GiB) and a CPU-time limit
(120 s) for the whole command. `tools/symblic-workcard` runs under the same limits.

### Try it

    tools/symblic check examples/01-four-plus-four.sym       # the plan and determinism profile; no model
    tools/symblic preview examples/01-four-plus-four.sym     # the exact request the one `ask` would send
    tools/symblic run examples/10-kernel-identity.sym --dir /tmp/ki    # a kernel-only program: no model
    tools/symblic replay /tmp/ki                             # rerun it from its record; no model
    tools/symblic lanes                                      # which way to hand work to models

## Scripts (`tools/scripts/`)

| Script | What it does | Runs here? |
|---|---|---|
| `symblic_conformance.py` | Copies a reviewed whitelist of runtime files into a temporary folder and checks that a fixed corpus gives byte-identical observables under three hash seeds and three decimal contexts, plus the soundness tests. Writes a receipt. | Yes (about a minute). Tests: `tests/tools/test_symblic_conformance_snapshot.py`. |
| `symblic_docs_audit.py` | Inventories every fenced block in the documentation; checks only declared, pinned Symblic cases in a bounded child. | Yes, with markdown-it-py 3.0.0 installed. Tests: `tests/tools/test_symblic_docs_audit.py`. |
| `symblic_import_markers.py` | Adds or checks the import-identity marker at the top of every module the execution pins register. | Yes. Tests: `tests/kernel/`. |
| `symblic_linear_provision.py` | Inventories an already installed Z3 solver environment for the linear constructor and pins its files; never installs. | Yes, with a solver environment to inspect. Tests: `tests/linear/`. |
| `symblic_reinforcement_stats.py` | Descriptive statistics over a benchmark manifest; no runner imports. | Yes. Tests: `tests/tools/`. |
| `symblic_frontier_ladder.py` | Plans the "frontier ladder" benchmark (one local model, six compiler rungs): prints the commands and writes a plan; materializes fixtures; aggregates reports. Never runs a benchmark or calls a model. | Planning, materializing and aggregating: yes. The printed session commands were written for the original host (its loopback readiness routes, its worker nodes). Tests: `tests/integration/test_symblic_frontier_ladder.py`. |
| `symblic_contract_pilot.py` | A preregistered diagnostic of semantic contracts and bounded escalation: prepare a frozen plan, then execute it. | Preparation: yes. Execution calls models through your applicators. Its recorded results are in `docs/reference/evidence/2026-10-03-contract-pilot-*.json`. Tests: `tests/integration/test_symblic_contract_pilot.py` (fake applicators). |
| `symblic_lang_bench.py` | The abstraction-layer experiments: certify the `text` library's tests per cohort of agents, and reproduce a paper per cohort. | It calls real models. Its thermal gate read the original host's cluster status route and never holds without one. |
| `symblic_refresh_catalog.py` | Refreshes the source list of the Academy page's catalog, `web/academy/symblic-academy-content.js`: a row for every `.md`, `.sym`, `.symd` and `.json` file under `docs/`, `examples/`, `benchmarks/` and `kits/`, with titles, headings and SHA-256 hashes read from the files. The authored curriculum, statuses and lesson links are kept, and the six rows that point at other repository files are refreshed (such rows are never added); `--check` only reports. When a document is moved or deleted, its row is dropped if the script wrote it and nobody has changed it; any other row whose file is gone stops the script, which names it: rename or remove that row by hand first, with the lesson links to it. | Yes. Run it after adding, moving, deleting or editing a document. Tests: `tests/tools/test_symblic_refresh_catalog.py` (temporary fixtures, plus read-only checks of the shipped catalog). |
| `install_symblic_tools.py` | Installs the optional source-navigation tools (grep-ast and pinned tree-sitter packages) into their own virtual environment for `tools/symblic-context`. | Yes; needs `git`, `uv` and network access. |
| `build_symblic_guides.cjs` | Rebuilds the static guides in `web/studio/symblic-guides/` from `docs/reference/` and `examples/`. | Yes, with marked 15.0.12 (`npm install marked@15.0.12`, or `SYMBLIC_MARKED=/path/to/marked.min.js`). |

Three scripts that only made sense inside the original host moved to `integration/host/scripts/`: indexing the
documents into the host's reading app, installing a node bundle on a worker machine, and probing the terminal
agent installed there.

## Tests

`tests/tools/` covers the scripts above; `tests/integration/test_symblic_task_cli*.py` cover the pure parts of
`tools/symblic-task` (statements, lint, request bodies, rendering) with the HTTP layer stubbed;
`tests/spec/`, `tests/authoring/` and `tests/tools/test_symblic_cli_agent.py` run `tools/symblic` as a
subprocess. For example:

    DASH_TEST=1 python3 -m unittest discover -s tests/tools -t .
    DASH_TEST=1 python3 -m unittest tests.integration.test_symblic_task_cli tests.integration.test_symblic_task_cli_autogen
