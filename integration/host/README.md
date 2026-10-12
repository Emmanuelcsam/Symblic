# integration/host: code that only ran inside the original host

Symblic was built inside one private home-server system, called "the host" in this repository: a web
server on a single machine (the operator's dashboard) with an agent hub, a node launcher for a small
cluster of worker machines, provider admission, a task engine and other applications. The modules in this
folder are how Symblic plugged into that system: its HTTP routes, its background-job launchers and a few
maintenance scripts.

They are kept because they show how the pieces were wired, and because some of their rules (idempotent
launches, no replay of an uncertain dispatch, owner gates, bounded reads) are worth reading. But **none of
them runs on its own**: each one needs a host object, service or module that is not part of this
repository. Every file says why in the first lines of its docstring (`HOST-ONLY: ...`). Their tests live in
`tests/integration/` and either run against fakes or skip with a reason (see "Tests" below).

Some package modules import from this folder, on the code path of a host feature (all lazily, inside the
function that needs it, except `symblic/mica/forge.py`, which imports `symblic_forge_bridge.py` at module level;
that import works without a host):

| Package module | Imports | For |
|---|---|---|
| `symblic/lang/abstraction.py` | `symblic_engine` | `import "Saved program" as x`: programs saved in the host's store |
| `symblic/providers/agent_teams.py` | `symblic_web` | team members that use the `chatgpt` or `gemini` browser applicators |
| `symblic/authoring/workcards.py` | `symblic_steps_api` | the `steps/result` route of its HTTP adapter (a run looked up in the host's store) |
| `symblic/mica/forge.py`, `symblic/mica/forge_cli.py` | `symblic_forge_bridge` | frozen Forge handoffs |

## What a host would have to provide

To run these modules again you would need to supply, under the names they import:

| Piece | Used by | What it must do |
|---|---|---|
| A loopback HTTP server and its request handler object | every `*_api.py`, `symblic_engine.py`, `symblic_forge.py`, `symblicos_engine.py` | Call `handle_get(handler)` / `handle_post(handler, data)` / `handle(handler, method, route, data)`. The handler offers `send_json(value, status)`, `get_query_param(name)`, `identity()` (an object with `is_owner` and `email`), `require_owner(label)`, and for downloads `send_response`, `send_header`, `end_headers`, `wfile`. |
| An identity gate | all routes | Only the owner reaches them; the host's automation route table (`automation_engine`) checked ownership before it handed a `symblic/...` route to `symblic_engine.handle_*`. `person.require(handler, 'owner', label)` was an extra per-person check. |
| A private store module, `host_apps` | `symblic_engine.py`, `symblic_lang_api.py`, `symblic_web.py`, `symblic_intent_api.py` | `save_json(path, value)` and `load_json(path, default)` (atomic JSON files), `store_lock(path)` (an inter-process lock), `data_dir(name, env_var)` (the host's data folder) and `DASHBOARD_DIR`. |
| A job launcher | `symblic_engine.py` (`_launch_unit`) and every module that starts a job | `systemd-run --user` transient units with memory and CPU limits; `systemctl --user` to observe and stop them. Jobs are started as `python -m <module> ...` from the repository root. |
| An agent runner and fleet records | `symblicos_tasks.py`, `symblic_mica_api.py`, `symblic_web.py`, `symblic_forge.py` | `host_agent_hub` (run a command on a node, the hub's data folder), `host_fleet` and `host_agents` (cached node facts, draining state, active model runs), `worker_health.host_ok(name)` (is this the configured fleet host). |
| A program runner and scheduler | `symblic_supervisor.py`, `symblic_intent_api.py` | `host_runner`, `host_planner`, `host_runner_capabilities`, `host_runner_jobs` (start and observe pinned native runs), `host_sched`, `host_triggers`, `host_tools`, `host_store` (timers, event triggers and the tool registry). |
| Browser agents | `symblic_web.py` | `host_browser_hub` (registered browser nodes and their hold), `host_council_run.member_env`, and a browser-automation runtime installed on the nodes. |

The `host_*` names are placeholders chosen for this repository: the original modules had other names, and
none of them is published here.

## Module by module

### The Symblic web API (`/api/automation/symblic/...`)

| File | What it did in the original host | Works without the host? |
|---|---|---|
| `symblic_engine.py` | The hub of the Symblic routes: check, preview, run, compare, stop, resume and delete programs; saved programs; examples; the evidence view; tighten jobs. Each run is a folder in the host's data directory, executed by `python -m symblic.kernel.run --dir FOLDER` in its own systemd user unit, so it survives a web-server restart and resumes by replaying `calls.jsonl`. It also dispatches every sub-route below. | Importing it does. Its preview and request checks now live in `symblic/kernel/preview.py` (re-exported here), which is what `tools/symblic preview` uses. Everything that saves or reads a run needs `host_apps` and the launcher. |
| `symblic_lang_api.py` | Routes for the abstraction layer: the standard library, module docs, in-language tests, `.symd` papers (check, compile, run, reproduce, view), lockfiles and their replay, and certify/crystallise jobs (`python -m symblic.lang.abstraction job`). | No. The same features run locally: `tools/symblic test|certify|lib|doc|paper|lock`. |
| `symblic_english_api.py` | The `english/` routes: examples, check, preview, run, and retry of a saved run. | No: runs go through the engine's store and launcher. Its pure half is `symblic/english/authoring.py`, which `tools/symblic english` uses. Its compiler-identity pins still name the original flat module files, exactly as the host computed them. |
| `symblic_steps_api.py` | The `steps/` routes: prepare a step construction and read a finished one back by run id. | No: the run-id lookup needs the host's run store. Its pure half (`from_folder`, `prepare`) is `symblic/steps/recovery.py`. |
| `symblic_memory_api.py` | The `memory/` routes and a CLI for claim notebooks (`notebooks`, `view`, `create`, `change`, `context`), importing claims from finished runs. | No: notebooks live under the engine's data root. The notebook logic is `symblic/memory/notebooks.py`; `tools/symblic memory` reaches this module and reports the missing host. |
| `symblic_experiments_api.py` | `experiments/catalog`, `experiments/run`, `experiments/verify`: a thin HTTP wrapper. | The logic is `symblic/experiments/registry.py`: `tools/symblic experiments ...`. |
| `symblic_inquiry_api.py` | `inquiry/example`, `inquiry/plan`: a thin HTTP wrapper. | The logic is `symblic/inquiry/selection.py`: `tools/symblic inquiry ...`. |
| `symblic_academy_sources.py` | `academy/source`: returned, read only and to the owner only, the text of one document listed in the catalog of the Academy learning page. | No: the route needs the host's handler and owner check. The page and its catalog are now in this repository (`web/academy/`, catalog `web/academy/symblic-academy-content.js`, kept current by `tools/scripts/symblic_refresh_catalog.py`), and the page reads the documents as static files. `read_source` serves only catalog rows under `docs/`, `examples/`, `benchmarks/` and `kits/`; tests: `tests/integration/test_symblic_academy_sources.py`. |
| `symblic_example_artifacts.py` | `examples/artifacts`: checked downloads of example files, pinned by a manifest (`artifacts.json`) in the host's docs folder. | No: it reads the host's path layout (`docs/symblic/examples/`). The manifest is shipped as `examples/artifacts.json`, its hashes matching this repository's files; the examples are in `examples/`. |

### Background jobs: graphs, policies, MICA and the Forge

| File | What it did in the original host | Works without the host? |
|---|---|---|
| `symblic_graph_api.py` | Routes and the job worker for agent graphs (`symblic/graph/`): check, start, view, stop and resume a graph job; each job ran as `python -m integration.host.symblic_graph_api job ...` in a systemd unit, with per-job locks so a stop and a resume cannot race. | No. The planner and runner are `symblic/graph/`; `tools/symblic graph ...` composes graphs locally. |
| `symblic_policy_api.py` | `policy/` routes: frozen graph-policy experiments (training selection, held-out comparison) run as graph jobs. | No. The policy learning is `symblic/policy/`. |
| `symblic_mica_api.py` | `mica/` routes and job launcher: check, start, follow and stop MICA constructions; the model inventory came from the host's cached fleet records (`host_fleet`, `host_agents`). | No. `tools/symblic mica ...` (`symblic/mica/cli.py`) runs constructions locally with your own applicators. |
| `symblic_forge.py` | `/api/symblic-forge/` routes: Forge projects, coaching, model proposals as jobs (`python -m symblic.forge.models --job ...`), exports; it also declared a read-only tool for the host's agents (`HOST_TOOLS`). | No. The Forge itself is `symblic/forge/` and is pure. |
| `symblic_forge_bridge.py` | `forge/handoff`, `forge/request`, `forge/run`: turned a frozen Forge handoff into a native Symblic run, once, by explicit owner action, with a durable request ledger. | No: it starts runs through the engine's store and launcher. |

### Workflows and the interpreter

| File | What it did in the original host | Works without the host? |
|---|---|---|
| `symblic_supervisor.py` | Durable multi-step workflows over pinned native runs: each step ran through the host's program runner, each timer or event trigger lived in the host's scheduler. | The workflow format and `simulate` are pure, but every real step needs `host_runner` and the scheduler. See `docs/reference/SUPERVISOR.md`. |
| `symblic_supervisor_api.py` | The `supervisor/` routes (list, view, create, start, tick, state, pause, schedule, bind, reconcile, simulate) and a loopback CLI for them. | No. |
| `symblic_intent_api.py` | The intent interpreter: a person writes a request, model jobs propose a read-back (goal, requirements, assumptions, questions, examples) and compile it into a Symblic program, which the host's runner then executes. | No. The pure records and store are `symblic/intent/`. |

### Applicators that needed the host

| File | What it did in the original host | Works without the host? |
|---|---|---|
| `symblic_web.py` | The `chatgpt` and `gemini` applicators: one tool-free typed prompt typed into a signed-in web chat by the host's browser-automation runtime on a node, answered as one JSON receipt; a dispatch whose reply was lost is observed, never re-sent. | No. The applicators in `symblic/providers/` cover local Ollama models and agent command lines instead. |

### The OS prototype and autogen (`symblicos_*.py`)

| File | What it is | Why it is host-only |
|---|---|---|
| `symblicos_tasks.py` | The host's durable task engine (`TaskManager`: one agent session per line, review gates, disk cross-checks of agent claims, no replay of uncertain launches) and `HubTaskRunner`, its adapter to the `TaskRunner` protocol of `symblic/autogen/runner.py`. | Every launch, observation and stop goes through the host's agent hub (terminal sessions on the host and on remote nodes). It is the only real `TaskRunner` that autogen ran with. |
| `symblicos_engine.py` | The host web server's `/api/symblicos/` routes: tasks, workspaces, autogen, and the OS terminal engine. `tools/symblic-task` is the command-line client of these routes. | It is called by the host's web server with its request handler and needs the host's hub object (`HUB`). |
| `symblicos_model_engine.py` | The OS prototype's model registry, READY health check, capacity plan and model calls. | Its inventory came from the hub and its calls went through the host's admitted provider path. |
| `symblicos_integrations.py` | Adapters for programs the host ran beside Symblic, and a declared runtime registry. | Those programs are not part of this repository; most adapters are stubs that return `simulated`. |
| `symblicos_physical_installer.py` | A read-only disk inspection of a node before a physical install, plus a gate that never installs. | It reaches the node through the host's cluster module (pass `cluster=` to use it elsewhere). |
| `symblicos_terminal_reference.py` | An audit of the host dashboard's terminal page against a pinned hash. | That page is not part of this repository. |

Nothing in `symblic/autogen/` or `symblic/os/` imports from this folder.

### Pages

| File | What it is | Why it is host-only |
|---|---|---|
| `tetris_player_shell.html` | The host page that framed the model-built Tetris page, scaled it to the screen and added touch buttons (moved from `kits/tetris/demo/index.html`). | It needs the host's shared page library (`/studio.js`, `/studio.css`). Open `kits/tetris/results/tetris-90ffd27f92ab.html` directly to play. |

### Scripts (`scripts/`)

| File | What it did in the original host | Why it is host-only |
|---|---|---|
| `scripts/index_symblic_to_reader.py` | Split the Symblic documents into passages and registered them in the host's reading app, pinning the master book in the operator's reading profile. | It needs the reading app's modules and store (`host_reader`, `host_reader_store`, `host_apps`). The original also indexed private agent notes; those sources were removed from this copy. |
| `scripts/install_symblic_node.py` | Installed a staged bundle on a worker node: one reviewed wheel of a third-party terminal agent, the context tools and small command wrappers in `~/.local/bin`. | The bundle layout and the job runner that copied it to a node belong to the host. The terminal agent's package name is replaced by the placeholder `agentcli`. |
| `scripts/check_symblic_node_runtime.py` | An offline contract probe of that installed terminal agent: its flags and tool protocol against a loopback fixture, with no account or real model call. | It probes the host's node wrapper and the same placeholder `agentcli` package. |

## Tests

The tests of this folder are in `tests/integration/`. Run them with

    DASH_TEST=1 python3 -m unittest discover -s tests/integration -t .

Three kinds of module live there:

- **Run without the host, against fakes.** Most route tests need only the host's store, so
  `tests/integration/fake_host_apps.py` stands in for it (atomic JSON files, a lock and a data folder under a
  temporary directory) and, where needed, for empty fleet-record modules. The engine, language, graph, policy,
  MICA, Forge, steps, delegate, tighten, logic, memory and determination route tests run this way, as do the
  OS task engine and the autogen coordinator over a fake hub, the task command line's pure functions, the
  frontier-ladder planner and the contract pilot.
- **Skipped with a reason when the host is absent.** A module that needs a host module the fakes do not
  provide starts with

      try:  # host-only: these modules belong to the private host system Symblic was built in
          import automation_engine as AE
          ...
      except ImportError as missing:
          raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, ...')

  so it is reported as skipped with the missing module named; an import error inside this repository is
  still raised as a failure. Tests that need the host's application router call `fake_host_apps.router(self)`,
  which skips just that test.
- **Skipped because a host file is missing**: the browser runtime of `symblic_web.py`, the host checkout's own
  registration files, and the English routes, whose host copy pins the original flat file layout.

`tests/integration/README.md` lists every file with its state.
