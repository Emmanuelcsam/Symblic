# tests/integration: tests of the host glue and of code that crosses package lines

The modules here test `integration/host/` (the original host's HTTP routes and job launchers, see
`integration/host/README.md`), the command lines in `tools/` and a few cross-package journeys. They use fakes
only: temporary stores, fake launchers and fake applicators. No model, agent, network or host service is used.

    DASH_TEST=1 python3 -m unittest discover -s tests/integration -t .

How a host-only module is handled:

- `fake_host_apps.py` stands in for the host's store module (`host_apps`: atomic JSON files, a lock, a data
  folder) and, when asked, for empty fleet-record modules. Route tests that need nothing else use it through
  `fake_host_apps.install(self)` or `setUpModule, tearDownModule = fake_host_apps.module_fixture()`, so they run
  here; when the real host is importable, it is used instead.
- A module that needs any other host module imports it inside `try: ... except ImportError` and raises
  `unittest.SkipTest('host-only test: needs ...')` naming the missing module. An import error of a module of
  this repository is re-raised: it is a bug, not a missing host.
- A test that needs the host's application router calls `fake_host_apps.router(self)`, which skips only that test.

The autogen coordinator journeys (`test_symblicos_autogen_hub_lane*.py`) write and fsync many small files and take
several minutes on a busy disk.

## Every module

State as of the last full pass (45 modules run, 18 skipped, 0 failing):

| Module | What it covers | State without the host |
|---|---|---|
| `test_symblic_academy_sources.py` | The Academy source route (integration/host/symblic_academy_sources.py): exact catalog rows only, document roots, no symlinks, size limit, owner and GET checks through the engine's dispatch; then every row of the shipped catalog (web/academy/symblic-academy-content.js) under the document roots read byte for byte. | runs: 7 tests |
| `test_symblic_agent_teams_english.py` | Team profiles through the English front end (symblic/english/authoring.py, the pure half of the host's English API). | runs: 9 tests |
| `test_symblic_catalog_focus.py` | Strict optional catalog selection through pure, CLI and owner API entry points. | skipped: needs 'automation_engine', which is not part of this repository |
| `test_symblic_constructor_api.py` | Host-only: the original host's run API with constructor options (start policy, resume refusals, routing). | skipped: needs 'automation_engine', which is not part of this repository |
| `test_symblic_constructor_controls.py` | The original host's write-page constructor controls (the meta feature marker and page payloads). | runs: 7 tests |
| `test_symblic_constructor_memory_import.py` | Importing a constructor run's claims into a notebook through the original host's notebook API. | runs: 1 test |
| `test_symblic_contract_pilot.py` | The preregistered contract pilot (tools/scripts/symblic_contract_pilot.py): isolated stores and injected fake applicators only, so it runs without ... | runs: 11 tests |
| `test_symblic_delegate_routes.py` | Delegation routes of the original host: its `delegate/...` HTTP API (catalog, compile, run, result, resume) and the declaration it stores with a run. | runs: 12 tests |
| `test_symblic_determination_entry.py` | Public determination control: fake launcher/provider and temporary run folders only. | runs: 8 tests |
| `test_symblic_discrete_tasks.py` | Discrete Qwen receipts drive task state; providers and sessions are fake. | runs: 15 tests |
| `test_symblic_editor_api.py` | Owner-module editor route: source diagnostics never launch a run. | runs: 5 tests |
| `test_symblic_engine.py` | integration/host/symblic_engine.py (the host's /api/automation/symblic/ routes): runs, preview, compare, programs, evidence and the HTTP dispatch ... | runs: 19 tests |
| `test_symblic_english_entry.py` | English host integration with an isolated compiler fixture, fake providers and temporary stores. | skipped: needs 'automation_engine', which is not part of this repository |
| `test_symblic_english_routes.py` | Host-only English routes: the original host dashboard's `english/...` HTTP API and its retry of saved runs. | skipped: needs 'host_apps', which is not part of this repository |
| `test_symblic_example_artifacts.py` | Checked example publication: isolated fixtures, no models, stores or server. | runs: 15 tests (skipped=1) |
| `test_symblic_example_tools.py` | Model-produced artifacts remain pinned data across shared agent readers. | skipped: needs 'host_tools', which is not part of this repository |
| `test_symblic_experiments_api.py` | Owner routing and finite experiment HTTP boundaries (integration/host/symblic_experiments_api.py); no real stores/providers. Runs without the ... | runs: 4 tests (skipped=1) |
| `test_symblic_forge_api.py` | Isolated persistence/API integration; no real providers, workers or fleet probes. | runs: 26 tests |
| `test_symblic_forge_bridge.py` | Frozen Forge lineage reaches real native preparation, with fake launch/providers. | skipped: needs 'host_tools', which is not part of this repository |
| `test_symblic_forge_examples.py` | Synthetic authoring/export corpus; no model, project execution or live stores. | runs: 2 tests |
| `test_symblic_forge_integration.py` | Static owner/private registration and real online SQLite backup, fully isolated. | skipped: reads the original host checkout (its server, store, navigation and backup modules), which is not part of this repository; set SYMBLIC_HOST_CHECKOUT to run it |
| `test_symblic_forge_team_coach.py` | Mixed proposal teams and atomic instruction coaching with isolated stores only. | runs: 18 tests |
| `test_symblic_frontier_ladder.py` | Frontier ladder planner (tools/scripts/symblic_frontier_ladder.py): fixtures, plan, aggregation and refusals. | runs: 20 tests |
| `test_symblic_graph_api.py` | Graph page→API→durable Run integration, fake Apps/launcher and private temp stores. | runs: 7 tests |
| `test_symblic_graph_api_audit.py` | Launch-generation, stale receipt and malformed-request adversaries; no real workers/providers. | runs: 11 tests |
| `test_symblic_graph_compose_host.py` | Composition routes of the original host: `graph/compose` and `graph/composition-example` HTTP API. | runs: 4 tests |
| `test_symblic_graph_repair_host.py` | Graph repair regressions of the original host's graph job runner. | runs: 16 tests |
| `test_symblic_inquiry_api.py` | Pure inquiry HTTP contract (integration/host/symblic_inquiry_api.py) and owner-routed engine integration, without stores. Runs without the host, ... | runs: 5 tests (skipped=1) |
| `test_symblic_intent_api.py` | Host-only: the original host's intent interpreter (journeys and recovery), with fake providers and temp stores. | skipped: needs 'host_runner', which is not part of this repository |
| `test_symblic_intent_page.py` | The intent interpreter web page (web/studio/symblic-intent.js): fake DOM and API, plus static rules. | runs: 4 tests |
| `test_symblic_intent_selection.py` | Host-only: an explicit model selection in the intent interpreter reaches the host's real planning boundaries. | skipped: needs 'host_runner', which is not part of this repository |
| `test_symblic_lang_api.py` | integration/host/symblic_lang_api.py (library, tests, papers, locks under the host's /api/automation/symblic/) with a temporary data dir, a fake ... | runs: 11 tests |
| `test_symblic_logic_api.py` | The human-logic compiler through the host's owner-only Symblic API (integration/host/symblic_engine.py). | runs: 4 tests |
| `test_symblic_memory_api.py` | Notebook API journeys use isolated host run records; never a model or live store. | runs: 4 tests |
| `test_symblic_mica_api.py` | Private MICA API journeys; fake launchers/providers, real durable job fences. | runs: 22 tests |
| `test_symblic_mica_forge_api.py` | Forge source through the original host's MICA HTTP API job lifecycle (integration/host), isolated host adapters. | runs: 28 tests |
| `test_symblic_mica_forge_api_native.py` | The original host's owner API -> real Forge/core/module checker; fake provider only. | runs: 2 tests |
| `test_symblic_mica_historical_artifacts_api.py` | Historical MICA artifact reads through the original host's owner-only HTTP API (integration/host). | runs: 4 tests |
| `test_symblic_model_recheck_api.py` | Explicit identity inspection is bounded; ordinary polling stays historical. | runs: 2 tests |
| `test_symblic_policy_api.py` | Owner API through actual graph-policy execution; private temp stores, fake Apps/launchers. | runs: 17 tests |
| `test_symblic_policy_lease.py` | Policy integration with graph990 worker leases, using private fake journals. | runs: 3 tests |
| `test_symblic_policy_repair.py` | Private-store regressions for concurrent admission and interrupted native jobs. | runs: 14 tests |
| `test_symblic_project_teams.py` | Mixed project teams use only fake hub dispatch and temporary receipts. | runs: 7 tests |
| `test_symblic_proof_card_entry.py` | Target-first card via existing owner API and CLI, with isolated stores and fake models. | skipped: needs 'automation_engine', which is not part of this repository |
| `test_symblic_proof_focus_entry.py` | Projected proof context through real CLI/API routing, with fake providers. | skipped: needs 'automation_engine', which is not part of this repository |
| `test_symblic_proof_obligation_entry.py` | Owner-gated obligation/7 CLI/API journeys, fake providers and temporary stores. | skipped: needs 'automation_engine', which is not part of this repository |
| `test_symblic_proof_step_entry.py` | Actual owner-gated CLI/API journeys; temporary stores and fake providers only. | skipped: needs 'automation_engine', which is not part of this repository |
| `test_symblic_resume_api.py` | Old-kernel resumes refuse before relaunch; the host's orchestrator keeps lowered authority. | skipped: needs 'host_orchestrator', which is not part of this repository |
| `test_symblic_review.py` | Owned council lifecycle regressions: fake hub, fake clock, no real workers. | skipped: needs 'host_council_run', which is not part of this repository |
| `test_symblic_spec_compare_api.py` | Differential owner API uses only supplied candidates and the local sandbox. | runs: 2 tests |
| `test_symblic_steps_api.py` | Exact saved-run recovery; isolated stores and fake native applicators only. | runs: 18 tests |
| `test_symblic_strict_identity_entry.py` | Explicit strict policy reaches native execution or refuses before dispatch. | runs: 5 tests |
| `test_symblic_supervisor.py` | Native handoff and durable workflow tests; all stores, launches and clocks isolated. | skipped: needs 'host_runner', which is not part of this repository |
| `test_symblic_task_card_api.py` | Owner API dispatch with isolated stores, fake launcher/models, local JS sandbox. | runs: 3 tests |
| `test_symblic_task_cli.py` | Pure functions of the tools/symblic-task command line: statements, lint and next_action. No host is needed. | runs: 7 tests |
| `test_symblic_task_cli_autogen.py` | The autogen lane of the tools/symblic-task command line: request bodies, rendering, wait, lint delegation. | runs: 49 tests |
| `test_symblic_tighten_api.py` | Owner adoption binds saved audited bytes; no launch or model in tests. | runs: 4 tests |
| `test_symblic_web.py` | Admitted typed browser requests with fake transports and temporary ledgers only. | skipped: needs the host's browser-automation runtime (integrations/chatgpt-browser/), which is not part of this repository |
| `test_symblic_web_catalog.py` | Read-only installed protocol metadata; no browser/provider or remote calls. | skipped: needs 'host_agents', which is not part of this repository |
| `test_symblicos_autogen_hub_lane.py` | The autogen coordinator over the original host's task engine (HOST-ONLY engine, fake hub). | runs: 63 tests |
| `test_symblicos_autogen_hub_lane_v2.py` | Autogen v2 over the original host's task engine (HOST-ONLY engine, fake hub): until_done (no clock or count caps), stall-driven subdivision, ... | runs: 32 tests |
| `test_symblicos_model_engine.py` | HOST-ONLY module, fakes only: the OS prototype's model engine (integration/host/symblicos_model_engine.py). | runs: 5 tests |
| `test_symblicos_tasks.py` | HOST-ONLY engine, fake hub: the original host's task engine (integration/host/symblicos_tasks.py) and its HTTP routes ... | runs: 62 tests |
