# Map: where every part of Symblic went

Symblic was developed inside a private host system (a personal web dashboard with a small cluster of worker
machines), as loose files at the top of that system's repository: `symblic.py`, `symblic_run.py`,
`symblic_js.py` and about 180 more, plus folders such as `docs/symblic/`, `symblicos/` and `tests/`. For
publication the files that mention Symblic were copied out and arranged into the package layout this repository
has now. This page is the translation table, for anyone who meets an old name in a document, a test, a commit
message or an old run record.

- Older documents in [reference/](reference/README.md) were rewritten to use the new paths wherever a path could be
  resolved automatically. Line numbers they quote (`language.py:4880`) refer to the files as they were before the
  move and may be off by a few lines.
- A few old file names belonged to the host's other applications; they are shown by their role instead of their
  name.
- Some files were renamed or merged again after the first move; those rows say so. Their package README describes
  the current files.

## Folders

| Old location | New location | Notes |
|---|---|---|
| `symblic*.py` (top level) | [`symblic/`](../symblic/) subpackages | one subpackage per area: `kernel`, `adapters`, `js`, `spec`, `english`, ... (table below) |
| `symblicos/` | [`symblic/os/`](../symblic/os/), [`symblic/autogen/`](../symblic/autogen/), [`integration/host/`](../integration/host/) | the prototype OS layer, the autogen coordinator, and the parts that needed the host's web server |
| `symblic_*_api.py`, `symblic_engine.py`, `symblic_web.py` | [`integration/host/`](../integration/host/) | HTTP routes of the original host; kept for reference, not runnable here |
| `symblic_lib/` | [`symblic/lang/library/`](../symblic/lang/library/) | the standard library modules (`text.sym`, `units.sym`, ...) |
| `symblic_js_*.js`, `symblic_js_contract_LICENSE.txt` | [`symblic/js/`](../symblic/js/) | the JavaScript runner and the vendored Acorn parser with its license |
| `bin/symblic`, `bin/symblic-*` | [`tools/`](../tools/) | the command-line entry points |
| `scripts/*symblic*` | [`tools/scripts/`](../tools/scripts/) (one moved to `symblic/bench/`) | benchmark, audit and install scripts |
| `automation-studio/` (the Symblic page and its assets) | [`web/studio/`](../web/studio/) | the browser page; it talked to the host's HTTP API |
| `symblic-hub/` | [`web/hub/`](../web/hub/) | the hub page, its records and demos |
| `symblic-learn.html`, `symblic-learn.js`, `symblic-learn.css`, `symblic-academy-content.js` (top level) | [`web/academy/`](../web/academy/README.md) | the Academy learning page (served at `/symblic-learn`) and its catalog; the page is `index.html` now, and the catalog's links are repository paths |
| `tetris/` | [`kits/tetris/`](../kits/tetris/) | the Tetris kit |
| `docs/symblic/*.md`, `*.json`, `*.svg` | [`docs/reference/`](reference/README.md) | same file names |
| `docs/symblic/examples/` | [`examples/`](../examples/) and [`kits/`](../kits/) | programs, task files and records; the Kirby kit went to `kits/kirby/` |
| `docs/symblic/benchmarks/` | [`benchmarks/`](../benchmarks/) | the frontier-ladder fixtures |
| `docs/symblic/papers/`, `grammar/`, `evidence/`, `reinforcements/` | `docs/reference/papers/`, `grammar/`, `evidence/`, `reinforcements/` | unchanged inside |
| `docs/symblic/life/` | (separate repository) | the never-run LIFE kit, kept in its own repository because it describes the original host in detail |
| AI essays (an agent's own working folder on the host) | [`docs/essays/`](essays/README.md) | one machine-generated inventory of the host's files was removed |
| `tests/test_*.py` | `tests/<package>/test_*.py` | sorted by the package they test; host-only tests in `tests/integration/` (table at the end) |

## Python modules and other top-level code

Import names changed with the files: `import symblic_js` is now `from symblic.js import check`, and
`symblic_run.Run` is `symblic.kernel.run.Run`.

| Old file | Old module | New file | New module | Note |
|---|---|---|---|---|
| `symblic_academy_sources.py` | `symblic_academy_sources` | `integration/host/symblic_academy_sources.py` | `integration.host.symblic_academy_sources` |  |
| `symblic_engine.py` | `symblic_engine` | `integration/host/symblic_engine.py` | `integration.host.symblic_engine` |  |
| `symblic_english_api.py` | `symblic_english_api` | `integration/host/symblic_english_api.py` | `integration.host.symblic_english_api` |  |
| `symblic_example_artifacts.py` | `symblic_example_artifacts` | `integration/host/symblic_example_artifacts.py` | `integration.host.symblic_example_artifacts` |  |
| `symblic_experiments_api.py` | `symblic_experiments_api` | `integration/host/symblic_experiments_api.py` | `integration.host.symblic_experiments_api` |  |
| `symblic_forge.py` | `symblic_forge` | `integration/host/symblic_forge.py` | `integration.host.symblic_forge` |  |
| `symblic_forge_bridge.py` | `symblic_forge_bridge` | `integration/host/symblic_forge_bridge.py` | `integration.host.symblic_forge_bridge` |  |
| `symblic_graph_api.py` | `symblic_graph_api` | `integration/host/symblic_graph_api.py` | `integration.host.symblic_graph_api` |  |
| `symblic_inquiry_api.py` | `symblic_inquiry_api` | `integration/host/symblic_inquiry_api.py` | `integration.host.symblic_inquiry_api` |  |
| `symblic_intent_api.py` | `symblic_intent_api` | `integration/host/symblic_intent_api.py` | `integration.host.symblic_intent_api` |  |
| `symblic_lang_api.py` | `symblic_lang_api` | `integration/host/symblic_lang_api.py` | `integration.host.symblic_lang_api` |  |
| `symblic_memory_api.py` | `symblic_memory_api` | `integration/host/symblic_memory_api.py` | `integration.host.symblic_memory_api` |  |
| `symblic_mica_api.py` | `symblic_mica_api` | `integration/host/symblic_mica_api.py` | `integration.host.symblic_mica_api` |  |
| `symblic_policy_api.py` | `symblic_policy_api` | `integration/host/symblic_policy_api.py` | `integration.host.symblic_policy_api` |  |
| `symblic_steps_api.py` | `symblic_steps_api` | `integration/host/symblic_steps_api.py` | `integration.host.symblic_steps_api` |  |
| `symblic_supervisor.py` | `symblic_supervisor` | `integration/host/symblic_supervisor.py` | `integration.host.symblic_supervisor` |  |
| `symblic_supervisor_api.py` | `symblic_supervisor_api` | `integration/host/symblic_supervisor_api.py` | `integration.host.symblic_supervisor_api` |  |
| `symblic_web.py` | `symblic_web` | `integration/host/symblic_web.py` | `integration.host.symblic_web` |  |
| `symblicos_engine.py` | `symblicos_engine` | `integration/host/symblicos_engine.py` | `integration.host.symblicos_engine` |  |
| `symblic_discrete.py` | `symblic_discrete` | `symblic/adapters/discrete.py` | `symblic.adapters.discrete` |  |
| `symblic_finite_logic.py` | `symblic_finite_logic` | `symblic/adapters/finite_logic.py` | `symblic.adapters.finite_logic` |  |
| `symblic_geometry.py` | `symblic_geometry` | `symblic/adapters/geometry.py` | `symblic.adapters.geometry` |  |
| `symblic_knowledge.py` | `symblic_knowledge` | `symblic/adapters/knowledge.py` | `symblic.adapters.knowledge` |  |
| `symblic_logic.py` | `symblic_logic` | `symblic/adapters/logic.py` | `symblic.adapters.logic` |  |
| `symblic_operators.py` | `symblic_operators` | `symblic/adapters/operators.py` | `symblic.adapters.operators` |  |
| `symblic_projection.py` | `symblic_projection` | `symblic/adapters/projection.py` | `symblic.adapters.projection` |  |
| `symblic_proof.py` | `symblic_proof` | `symblic/adapters/proof.py` | `symblic.adapters.proof` |  |
| `symblic_proof_adapter.py` | `symblic_proof_adapter` | `symblic/adapters/proof_adapter.py` | `symblic.adapters.proof_adapter` |  |
| `symblic_proof_command.py` | `symblic_proof_command` | `symblic/adapters/proof_command.py` | `symblic.adapters.proof_command` |  |
| `symblic_proof_session.py` | `symblic_proof_session` | `symblic/adapters/proof_session.py` | `symblic.adapters.proof_session` |  |
| `symblic_proof_steps.py` | `symblic_proof_steps` | `symblic/adapters/proof_steps.py` | `symblic.adapters.proof_steps` |  |
| `symblic_quantities.py` | `symblic_quantities` | `symblic/adapters/quantities.py` | `symblic.adapters.quantities` |  |
| `symblic_render.py` | `symblic_render` | `symblic/adapters/render.py` | `symblic.adapters.render` |  |
| `symblic_transport.py` | `symblic_transport` | `symblic/adapters/transport.py` | `symblic.adapters.transport` |  |
| `symblic_variational.py` | `symblic_variational` | `symblic/adapters/variational.py` | `symblic.adapters.variational` |  |
| `symblic_editor_diagnostics.py` | `symblic_editor_diagnostics` | `symblic/authoring/editor_diagnostics.py` | `symblic.authoring.editor_diagnostics` |  |
| `symblic_authoring.py` | `symblic_authoring` | `symblic/authoring/helpers.py` | `symblic.authoring.helpers` |  |
| `symblic_paper.py` | `symblic_paper` | `symblic/authoring/paper.py` | `symblic.authoring.paper` |  |
| `symblic_tighten.py` | `symblic_tighten` | `symblic/authoring/tighten.py` | `symblic.authoring.tighten` |  |
| `symblic_workcards.py` | `symblic_workcards` | `symblic/authoring/workcards.py` | `symblic.authoring.workcards` |  |
| `symblicos/autogen.py` | `symblicos.autogen` | `symblic/autogen/coordinator.py` | `symblic.autogen.coordinator` |  |
| `symblicos/autogen_kernel.py` | `symblicos.autogen_kernel` | `symblic/autogen/kernel_lane.py` | `symblic.autogen.kernel_lane` |  |
| `symblic_autogen.py` | `symblic_autogen` | `symblic/autogen/policy.py` | `symblic.autogen.policy` |  |
| `symblicos/tasks.py` | `symblicos.tasks` | `symblic/autogen/tasks.py` | `symblic.autogen.tasks` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `symblicos/workspaces.py` | `symblicos.workspaces` | `symblic/autogen/workspaces.py` | `symblic.autogen.workspaces` |  |
| `symblic_bench_ambiguity.py` | `symblic_bench_ambiguity` | `symblic/bench/ambiguity.py` | `symblic.bench.ambiguity` |  |
| `symblic_bench.py` | `symblic_bench` | `symblic/bench/bench.py` | `symblic.bench.bench` |  |
| `symblic_eval_protocol.py` | `symblic_eval_protocol` | `symblic/bench/eval_protocol.py` | `symblic.bench.eval_protocol` |  |
| `symblic_bench_matched.py` | `symblic_bench_matched` | `symblic/bench/matched.py` | `symblic.bench.matched` |  |
| `symblic_constructor.py` | `symblic_constructor` | `symblic/constructor/core.py` | `symblic.constructor.core` |  |
| `symblic_constructor_inspect.py` | `symblic_constructor_inspect` | `symblic/constructor/inspect.py` | `symblic.constructor.inspect` |  |
| `symblic_constructor_journal.py` | `symblic_constructor_journal` | `symblic/constructor/journal.py` | `symblic.constructor.journal` |  |
| `symblic_constructor_records.py` | `symblic_constructor_records` | `symblic/constructor/records.py` | `symblic.constructor.records` |  |
| `symblic_delegate.py` | `symblic_delegate` | `symblic/delegate/contracts.py` | `symblic.delegate.contracts` |  |
| `symblic_delegate_run.py` | `symblic_delegate_run` | `symblic/delegate/run.py` | `symblic.delegate.run` |  |
| `symblic_distill_checkers.py` | `symblic_distill_checkers` | `symblic/distill/checkers.py` | `symblic.distill.checkers` |  |
| `symblic_distill_contracts.py` | `symblic_distill_contracts` | `symblic/distill/contracts.py` | `symblic.distill.contracts` |  |
| `symblic_distill.py` | `symblic_distill` | `symblic/distill/datasets.py` | `symblic.distill.datasets` |  |
| `symblic_distill_export.py` | `symblic_distill_export` | `symblic/distill/export.py` | `symblic.distill.export` |  |
| `symblic_distill_worker.py` | `symblic_distill_worker` | `symblic/distill/worker.py` | `symblic.distill.worker` |  |
| `symblic_english_build.py` | `symblic_english_build` | `symblic/english/build.py` | `symblic.english.build` |  |
| `symblic_english_cli.py` | `symblic_english_cli` | `symblic/english/cli.py` | `symblic.english.cli` |  |
| `symblic_english.py` | `symblic_english` | `symblic/english/compiler.py` | `symblic.english.compiler` |  |
| `symblic_english_pixel_checks.py` | `symblic_english_pixel_checks` | `symblic/english/pixel_checks.py` | `symblic.english.pixel_checks` |  |
| `symblic_english_pixels.py` | `symblic_english_pixels` | `symblic/english/pixels.py` | `symblic.english.pixels` |  |
| `symblic_experiments_context.py` | `symblic_experiments_context` | `symblic/experiments/context.py` | `symblic.experiments.context` |  |
| `symblic_experiments_geometry.py` | `symblic_experiments_geometry` | `symblic/experiments/geometry.py` | `symblic.experiments.geometry` |  |
| `symblic_experiments_graph.py` | `symblic_experiments_graph` | `symblic/experiments/graph.py` | `symblic.experiments.graph` |  |
| `symblic_experiments_numerics.py` | `symblic_experiments_numerics` | `symblic/experiments/numerics.py` | `symblic.experiments.numerics` |  |
| `symblic_experiments_protocols.py` | `symblic_experiments_protocols` | `symblic/experiments/protocols.py` | `symblic.experiments.protocols` |  |
| `symblic_experiments_quantum.py` | `symblic_experiments_quantum` | `symblic/experiments/quantum.py` | `symblic.experiments.quantum` |  |
| `symblic_experiments.py` | `symblic_experiments` | `symblic/experiments/registry.py` | `symblic.experiments.registry` |  |
| `symblic_experiments_resources.py` | `symblic_experiments_resources` | `symblic/experiments/resources.py` | `symblic.experiments.resources` |  |
| `symblic_experiments_sampling.py` | `symblic_experiments_sampling` | `symblic/experiments/sampling.py` | `symblic.experiments.sampling` |  |
| `symblic_experiments_structure.py` | `symblic_experiments_structure` | `symblic/experiments/structure.py` | `symblic.experiments.structure` |  |
| `symblic_experiments_transport.py` | `symblic_experiments_transport` | `symblic/experiments/transport.py` | `symblic.experiments.transport` |  |
| `symblic_forge_catalog.py` | `symblic_forge_catalog` | `symblic/forge/catalog.py` | `symblic.forge.catalog` |  |
| `symblic_forge_coach.py` | `symblic_forge_coach` | `symblic/forge/coach.py` | `symblic.forge.coach` |  |
| `symblic_forge_core.py` | `symblic_forge_core` | `symblic/forge/core.py` | `symblic.forge.core` |  |
| `symblic_forge_exports.py` | `symblic_forge_exports` | `symblic/forge/exports.py` | `symblic.forge.exports` |  |
| `symblic_forge_models.py` | `symblic_forge_models` | `symblic/forge/models.py` | `symblic.forge.models` |  |
| `symblic_forge_store.py` | `symblic_forge_store` | `symblic/forge/store.py` | `symblic.forge.store` |  |
| `symblic_forge_watch.py` | `symblic_forge_watch` | `symblic/forge/watch.py` | `symblic.forge.watch` |  |
| `symblic_graph_compose.py` | `symblic_graph_compose` | `symblic/graph/compose.py` | `symblic.graph.compose` |  |
| `symblic_graph.py` | `symblic_graph` | `symblic/graph/planner.py` | `symblic.graph.planner` |  |
| `symblic_graph_run.py` | `symblic_graph_run` | `symblic/graph/run.py` | `symblic.graph.run` |  |
| `symblic_inquiry.py` | `symblic_inquiry` | `symblic/inquiry/selection.py` | `symblic.inquiry.selection` |  |
| `symblic_intent.py` | `symblic_intent` | `symblic/intent/records.py` | `symblic.intent.records` |  |
| `symblic_requirement_execution.py` | `symblic_requirement_execution` | `symblic/intent/requirement_execution.py` | `symblic.intent.requirement_execution` |  |
| `symblic_intent_store.py` | `symblic_intent_store` | `symblic/intent/store.py` | `symblic.intent.store` |  |
| `symblic_js_contract_LICENSE.txt` |  | `symblic/js/acorn-LICENSE.txt` |  |  |
| `symblic_js_contract_acorn.js` |  | `symblic/js/acorn.js` |  |  |
| `symblic_js.py` | `symblic_js` | `symblic/js/check.py` | `symblic.js.check` |  |
| `symblic_js_contract.py` | `symblic_js_contract` | `symblic/js/contract.py` | `symblic.js.contract` |  |
| `symblic_js_normalize.py` | `symblic_js_normalize` | `symblic/js/normalize.py` | `symblic.js.normalize` |  |
| `symblic_js_runner.js` |  | `symblic/js/runner.js` |  |  |
| `symblic_certificates.py` | `symblic_certificates` | `symblic/kernel/certificates.py` | `symblic.kernel.certificates` |  |
| `symblic_context.py` | `symblic_context` | `symblic/kernel/context_packs.py` | `symblic.kernel.context_packs` |  |
| `symblic_diagnose.py` | `symblic_diagnose` | `symblic/kernel/diagnose.py` | `symblic.kernel.diagnose` |  |
| `symblic_effects.py` | `symblic_effects` | `symblic/kernel/effects.py` | `symblic.kernel.effects` |  |
| `symblic_embed.py` | `symblic_embed` | `symblic/kernel/embed.py` | `symblic.kernel.embed` |  |
| `symblic_epistemic.py` | `symblic_epistemic` | `symblic/kernel/epistemic.py` | `symblic.kernel.epistemic` |  |
| `symblic_evidence.py` | `symblic_evidence` | `symblic/kernel/evidence.py` | `symblic.kernel.evidence` |  |
| `symblic_execution.py` | `symblic_execution` | `symblic/kernel/execution_pins.py` | `symblic.kernel.execution_pins` |  |
| `symblic_grounding.py` | `symblic_grounding` | `symblic/kernel/grounding.py` | `symblic.kernel.grounding` |  |
| `symblic_identity.py` | `symblic_identity` | `symblic/kernel/identity.py` | `symblic.kernel.identity` |  |
| `symblic_json_schema.py` | `symblic_json_schema` | `symblic/kernel/json_schema.py` | `symblic.kernel.json_schema` |  |
| `symblic.py` | `symblic` | `symblic/kernel/language.py` | `symblic.kernel.language` |  |
| `symblic_lock.py` | `symblic_lock` | `symblic/kernel/lockfile.py` | `symblic.kernel.lockfile` |  |
| `symblic_process.py` | `symblic_process` | `symblic/kernel/process_limits.py` | `symblic.kernel.process_limits` |  |
| `symblic_profiles.py` | `symblic_profiles` | `symblic/kernel/profiles.py` | `symblic.kernel.profiles` |  |
| `symblic_run.py` | `symblic_run` | `symblic/kernel/run.py` | `symblic.kernel.run` |  |
| `symblic_lang.py` | `symblic_lang` | `symblic/lang/abstraction.py` | `symblic.lang.abstraction` |  |
| `symblic_linear.py` | `symblic_linear` | `symblic/linear/constructor.py` | `symblic.linear.constructor` |  |
| `symblic_linear_resources.py` | `symblic_linear_resources` | `symblic/linear/resources.py` | `symblic.linear.resources` |  |
| `symblic_linear_worker.py` | `symblic_linear_worker` | `symblic/linear/worker.py` | `symblic.linear.worker` |  |
| `symblic_memory.py` | `symblic_memory` | `symblic/memory/notebooks.py` | `symblic.memory.notebooks` |  |
| `symblic_mica_bench.py` | `symblic_mica_bench` | `symblic/mica/bench.py` | `symblic.mica.bench` |  |
| `symblic_mica_bundle.py` | `symblic_mica_bundle` | `symblic/mica/bundle.py` | `symblic.mica.bundle` |  |
| `symblic_mica_calibration.py` | `symblic_mica_calibration` | `symblic/mica/calibration.py` | `symblic.mica.calibration` |  |
| `symblic_mica_checkpack.py` | `symblic_mica_checkpack` | `symblic/mica/checkpack.py` | `symblic.mica.checkpack` |  |
| `symblic_mica_checkpack_cli.py` | `symblic_mica_checkpack_cli` | `symblic/mica/checkpack_cli.py` | `symblic.mica.checkpack_cli` |  |
| `symblic_mica_checkpack_link.py` | `symblic_mica_checkpack_link` | `symblic/mica/checkpack_link.py` | `symblic.mica.checkpack_link` |  |
| `symblic_mica_cli.py` | `symblic_mica_cli` | `symblic/mica/cli.py` | `symblic.mica.cli` |  |
| `symblic_mica_contracts.py` | `symblic_mica_contracts` | `symblic/mica/contracts.py` | `symblic.mica.contracts` |  |
| `symblic_mica_costs.py` | `symblic_mica_costs` | `symblic/mica/costs.py` | `symblic.mica.costs` |  |
| `symblic_mica_deterministic.py` | `symblic_mica_deterministic` | `symblic/mica/deterministic.py` | `symblic.mica.deterministic` |  |
| `symblic_mica_domains.py` | `symblic_mica_domains` | `symblic/mica/domains.py` | `symblic.mica.domains` |  |
| `symblic_mica_fixtures.py` | `symblic_mica_fixtures` | `symblic/mica/fixtures.py` | `symblic.mica.fixtures` |  |
| `symblic_mica_forge.py` | `symblic_mica_forge` | `symblic/mica/forge.py` | `symblic.mica.forge` |  |
| `symblic_mica_forge_cli.py` | `symblic_mica_forge_cli` | `symblic/mica/forge_cli.py` | `symblic.mica.forge_cli` |  |
| `symblic_mica_library.py` | `symblic_mica_library` | `symblic/mica/library.py` | `symblic.mica.library` |  |
| `symblic_mica_native.py` | `symblic_mica_native` | `symblic/mica/native.py` | `symblic.mica.native` |  |
| `symblic_mica_project.py` | `symblic_mica_project` | `symblic/mica/project.py` | `symblic.mica.project` |  |
| `symblic_mica_promote.py` | `symblic_mica_promote` | `symblic/mica/promote.py` | `symblic.mica.promote` |  |
| `symblic_mica_proposal.py` | `symblic_mica_proposal` | `symblic/mica/proposal.py` | `symblic.mica.proposal` |  |
| `symblic_mica_refinement.py` | `symblic_mica_refinement` | `symblic/mica/refinement.py` | `symblic.mica.refinement` |  |
| `symblic_mica_routing.py` | `symblic_mica_routing` | `symblic/mica/routing.py` | `symblic.mica.routing` |  |
| `symblic_mica.py` | `symblic_mica` | `symblic/mica/search.py` | `symblic.mica.search` |  |
| `symblic_mica_strategy.py` | `symblic_mica_strategy` | `symblic/mica/strategy.py` | `symblic.mica.strategy` |  |
| `symblicos/acceptance.py` | `symblicos.acceptance` | `symblic/os/acceptance.py` | `symblic.os.acceptance` |  |
| `symblicos/compiler_bridge.py` | `symblicos.compiler_bridge` | `symblic/os/compiler_bridge.py` | `symblic.os.compiler_bridge` |  |
| `symblicos/demonstrations.py` | `symblicos.demonstrations` | `symblic/os/demonstrations.py` | `symblic.os.demonstrations` |  |
| `symblicos/file_effects.py` | `symblicos.file_effects` | `symblic/os/file_effects.py` | `symblic.os.file_effects` |  |
| `symblicos/fs_boundary.py` | `symblicos.fs_boundary` | `symblic/os/fs_boundary.py` | `symblic.os.fs_boundary` |  |
| `symblicos/image_builder.py` | `symblicos.image_builder` | `symblic/os/image_builder.py` | `symblic.os.image_builder` |  |
| `symblicos/intake.py` | `symblicos.intake` | `symblic/os/intake.py` | `symblic.os.intake` |  |
| `symblicos/integrations.py` | `symblicos.integrations` | `symblic/os/integrations.py` | `symblic.os.integrations` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `symblicos/model_engine.py` | `symblicos.model_engine` | `symblic/os/model_engine.py` | `symblic.os.model_engine` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `symblicos/paths.py` | `symblicos.paths` | `symblic/os/paths.py` | `symblic.os.paths` |  |
| `symblicos/physical_installer.py` | `symblicos.physical_installer` | `symblic/os/physical_installer.py` | `symblic.os.physical_installer` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `symblicos/process_effects.py` | `symblicos.process_effects` | `symblic/os/process_effects.py` | `symblic.os.process_effects` |  |
| `symblicos/protocol.py` | `symblicos.protocol` | `symblic/os/protocol.py` | `symblic.os.protocol` |  |
| `symblicos/receipts.py` | `symblicos.receipts` | `symblic/os/receipts.py` | `symblic.os.receipts` |  |
| `symblicos/release_manifest.py` | `symblicos.release_manifest` | `symblic/os/release_manifest.py` | `symblic.os.release_manifest` |  |
| `symblicos/roadmap.py` | `symblicos.roadmap` | `symblic/os/roadmap.py` | `symblic.os.roadmap` |  |
| `symblicos/security_boundary.py` | `symblicos.security_boundary` | `symblic/os/security_boundary.py` | `symblic.os.security_boundary` |  |
| `symblicos/service_defs.py` | `symblicos.service_defs` | `symblic/os/service_defs.py` | `symblic.os.service_defs` |  |
| `symblicos/terminal_reference.py` | `symblicos.terminal_reference` | `symblic/os/terminal_reference.py` | `symblic.os.terminal_reference` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `symblicos/terminal_server.py` | `symblicos.terminal_server` | `symblic/os/terminal_server.py` | `symblic.os.terminal_server` |  |
| `symblicos/virtual_boot.py` | `symblicos.virtual_boot` | `symblic/os/virtual_boot.py` | `symblic.os.virtual_boot` |  |
| `symblic_policy_graph.py` | `symblic_policy_graph` | `symblic/policy/graph.py` | `symblic.policy.graph` |  |
| `symblic_policy_learning.py` | `symblic_policy_learning` | `symblic/policy/learning.py` | `symblic.policy.learning` |  |
| `symblic_policy_store.py` | `symblic_policy_store` | `symblic/policy/store.py` | `symblic.policy.store` |  |
| `symblic_portable.py` | `symblic_portable` | `symblic/portable/export.py` | `symblic.portable.export` |  |
| `symblic_portable_runner.py` | `symblic_portable_runner` | `symblic/portable/runner.py` | `symblic.portable.runner` |  |
| `symblic_agent_teams.py` | `symblic_agent_teams` | `symblic/providers/agent_teams.py` | `symblic.providers.agent_teams` |  |
| `symblic_apply.py` | `symblic_apply` | `symblic/providers/applicators.py` | `symblic.providers.applicators` |  |
| (the host's Ollama call helper) |  | `symblic/providers/ollama_call.py` | `symblic.providers.ollama_call` |  |
| (the host's Landlock launcher) |  | `symblic/sandbox/landlock.py` | `symblic.sandbox.landlock` |  |
| `symblic_spec_build.py` | `symblic_spec_build` | `symblic/spec/build.py` | `symblic.spec.build` |  |
| `symblic_spec_compare.py` | `symblic_spec_compare` | `symblic/spec/compare.py` | `symblic.spec.compare` |  |
| `symblic_spec_contracts.py` | `symblic_spec_contracts` | `symblic/spec/contracts.py` | `symblic.spec.contracts` |  |
| `symblic_spec.py` | `symblic_spec` | `symblic/spec/sheets.py` | `symblic.spec.sheets` |  |
| `symblic_steps.py` | `symblic_steps` | `symblic/steps/construction.py` | `symblic.steps.construction` |  |

## Command-line tools and scripts

| Old path | New path | Note |
|---|---|---|
| `scripts/check_symblic_node_runtime.py` | `integration/host/scripts/check_symblic_node_runtime.py` | moved again after the first move |
| `scripts/install_symblic_node.py` | `integration/host/scripts/install_symblic_node.py` | moved again after the first move |
| `scripts/symblic_local_beta.py` | `symblic/bench/local_beta.py` |  |
| `scripts/build_symblic_guides.cjs` | `tools/scripts/build_symblic_guides.cjs` |  |
| (the host's script that indexed the documents into its reading app) | `integration/host/scripts/index_symblic_to_reader.py` | moved and renamed after the first move |
| `scripts/install_symblic_tools.py` | `tools/scripts/install_symblic_tools.py` |  |
| `scripts/symblic_conformance.py` | `tools/scripts/symblic_conformance.py` |  |
| `scripts/symblic_contract_pilot.py` | `tools/scripts/symblic_contract_pilot.py` |  |
| `scripts/symblic_docs_audit.py` | `tools/scripts/symblic_docs_audit.py` |  |
| `scripts/symblic_frontier_ladder.py` | `tools/scripts/symblic_frontier_ladder.py` |  |
| `scripts/symblic_import_markers.py` | `tools/scripts/symblic_import_markers.py` |  |
| `scripts/symblic_lang_bench.py` | `tools/scripts/symblic_lang_bench.py` |  |
| `scripts/symblic_linear_provision.py` | `tools/scripts/symblic_linear_provision.py` |  |
| `scripts/symblic_refresh_catalog.py` | `tools/scripts/symblic_refresh_catalog.py` |  |
| `scripts/symblic_reinforcement_stats.py` | `tools/scripts/symblic_reinforcement_stats.py` |  |
| `bin/symblic` | `tools/symblic` |  |
| `bin/symblic-context` | `tools/symblic-context` |  |
| `bin/symblic-distill` | `tools/symblic-distill` |  |
| `bin/symblic-task` | `tools/symblic-task` |  |
| `bin/symblic-workcard` | `tools/symblic-workcard` |  |

## Browser pages

<details><summary>90 files</summary>

| Old path | New path | Note |
|---|---|---|
| `tetris/index.html` | `kits/tetris/demo/index.html` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `symblic-hub/atomic/atomic.js` | `web/hub/atomic/atomic.js` |  |
| `symblic-hub/atomic/results.json` | `web/hub/atomic/results.json` |  |
| `symblic-hub/autogen.js` | `web/hub/autogen.js` |  |
| `symblic-hub/beta.html` | `web/hub/beta.html` |  |
| `symblic-hub/demos/graphview/README.md` | `web/hub/demos/graphview/README.md` |  |
| `symblic-hub/demos/graphview/index.html` | `web/hub/demos/graphview/index.html` |  |
| `symblic-hub/demos/graphview/prompt-draft.english.txt` | `web/hub/demos/graphview/prompt-draft.english.txt` |  |
| `symblic-hub/demos/graphview/prompt-executed.english.txt` | `web/hub/demos/graphview/prompt-executed.english.txt` |  |
| `symblic-hub/demos/kirby/prompt-executed.english.txt` | `web/hub/demos/kirby/prompt-executed.english.txt` |  |
| `symblic-hub/demos/pcb/index.html` | `web/hub/demos/pcb/index.html` |  |
| `symblic-hub/index.html` | `web/hub/index.html` |  |
| `symblic-hub/mica.js` | `web/hub/mica.js` |  |
| `symblic-hub/records/README.md` | `web/hub/records/README.md` |  |
| `symblic-hub/records/SYMBLIC-CRITICAL-ANALYSIS.md` | `web/hub/records/SYMBLIC-CRITICAL-ANALYSIS.md` |  |
| `symblic-hub/records/beta-graphview-draft-v1.english.txt` | `web/hub/records/beta-graphview-draft-v1.english.txt` |  |
| `symblic-hub/records/beta-graphview-executed-v2.english.txt` | `web/hub/records/beta-graphview-executed-v2.english.txt` |  |
| `symblic-hub/records/beta-kirby-executed-v2.english.txt` | `web/hub/records/beta-kirby-executed-v2.english.txt` |  |
| `symblic-hub/records/beta-review-2026-10-08.md` | `web/hub/records/beta-review-2026-10-08.md` |  |
| `symblic-hub/records/beta-trial-2026-10-08.md` | `web/hub/records/beta-trial-2026-10-08.md` |  |
| `symblic-hub/records/beta-trial-run-log.md` | `web/hub/records/beta-trial-run-log.md` |  |
| `symblic-hub/records/index.html` | `web/hub/records/index.html` |  |
| `symblic-hub/records/other-beta-trials/beta-hw4.english.txt` | `web/hub/records/other-beta-trials/beta-hw4.english.txt` |  |
| `symblic-hub/records/other-beta-trials/beta-mist-lang.english.txt` | `web/hub/records/other-beta-trials/beta-mist-lang.english.txt` |  |
| `symblic-hub/records/other-beta-trials/beta-pcb.english.txt` | `web/hub/records/other-beta-trials/beta-pcb.english.txt` |  |
| `symblic-hub/records/other-beta-trials/beta-sem.english.txt` | `web/hub/records/other-beta-trials/beta-sem.english.txt` |  |
| `symblic-hub/records/other-beta-trials/cc-task-local-tools.md` | `web/hub/records/other-beta-trials/cc-task-local-tools.md` |  |
| `symblic-hub/records/other-beta-trials/cc-task-stall-advisory.md` | `web/hub/records/other-beta-trials/cc-task-stall-advisory.md` |  |
| `symblic-hub/records/task-graphview-run2.json` | `web/hub/records/task-graphview-run2.json` |  |
| `symblic-hub/records/task-kirby-run2.json` | `web/hub/records/task-kirby-run2.json` |  |
| `symblic-hub/records/verification/checkkirby.js` | `web/hub/records/verification/checkkirby.js` |  |
| `symblic-hub/records/verification/nav-add-graphview.json` | `web/hub/records/verification/nav-add-graphview.json` |  |
| `symblic-hub/records/verification/nav-add-kirby.json` | `web/hub/records/verification/nav-add-kirby.json` |  |
| `symblic-hub/records/verification/nav-add-pcb.json` | `web/hub/records/verification/nav-add-pcb.json` |  |
| `symblic-hub/subnav.js` | `web/hub/subnav.js` |  |
| `automation-studio/index.html` | `web/studio/index.html` |  |
| `automation-studio/js/constants.js` | `web/studio/js/constants.js` |  |
| `automation-studio/js/graph.js` | `web/studio/js/graph.js` |  |
| `automation-studio/js/symblic.js` | `web/studio/js/symblic.js` |  |
| `automation-studio/js/symblic/compiler.js` | `web/studio/js/symblic/compiler.js` |  |
| `automation-studio/js/symblic/constants.js` | `web/studio/js/symblic/constants.js` |  |
| `automation-studio/js/symblic/parser.js` | `web/studio/js/symblic/parser.js` |  |
| `automation-studio/js/symblic/settings.js` | `web/studio/js/symblic/settings.js` |  |
| `automation-studio/js/ui.js` | `web/studio/js/ui.js` |  |
| `automation-studio/styles.css` | `web/studio/styles.css` |  |
| `automation-studio/symblic-determinism.js` | `web/studio/symblic-determinism.js` |  |
| `automation-studio/symblic-editor-diagnostics.js` | `web/studio/symblic-editor-diagnostics.js` |  |
| `automation-studio/symblic-english-circuit.js` | `web/studio/symblic-english-circuit.js` |  |
| `automation-studio/symblic-english.css` | `web/studio/symblic-english.css` |  |
| `automation-studio/symblic-english.js` | `web/studio/symblic-english.js` |  |
| `automation-studio/symblic-experiments.js` | `web/studio/symblic-experiments.js` |  |
| `automation-studio/symblic-frames.js` | `web/studio/symblic-frames.js` |  |
| `automation-studio/symblic-graphs.js` | `web/studio/symblic-graphs.js` |  |
| `automation-studio/symblic-guides/claude-cloud.html` | `web/studio/symblic-guides/claude-cloud.html` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `automation-studio/symblic-guides/cmatrix.html` | `web/studio/symblic-guides/cmatrix.html` |  |
| `automation-studio/symblic-guides/distillation.html` | `web/studio/symblic-guides/distillation.html` |  |
| `automation-studio/symblic-guides/editor.html` | `web/studio/symblic-guides/editor.html` |  |
| `automation-studio/symblic-guides/index.html` | `web/studio/symblic-guides/index.html` |  |
| `automation-studio/symblic-guides/portable.html` | `web/studio/symblic-guides/portable.html` |  |
| `automation-studio/symblic-guides/slots-example.html` | `web/studio/symblic-guides/slots-example.html` |  |
| `automation-studio/symblic-guides/steps-evidence.html` | `web/studio/symblic-guides/steps-evidence.html` |  |
| `automation-studio/symblic-guides/steps-parcel-built.html` | `web/studio/symblic-guides/steps-parcel-built.html` |  |
| `automation-studio/symblic-guides/steps-parcel-inputs.html` | `web/studio/symblic-guides/steps-parcel-inputs.html` |  |
| `automation-studio/symblic-guides/steps-parcel.html` | `web/studio/symblic-guides/steps-parcel.html` |  |
| `automation-studio/symblic-guides/steps.html` | `web/studio/symblic-guides/steps.html` |  |
| `automation-studio/symblic-guides/supervisor.html` | `web/studio/symblic-guides/supervisor.html` |  |
| `automation-studio/symblic-guides/team-example.html` | `web/studio/symblic-guides/team-example.html` |  |
| `automation-studio/symblic-guides/vorticity.html` | `web/studio/symblic-guides/vorticity.html` |  |
| `automation-studio/symblic-guides/workcards.html` | `web/studio/symblic-guides/workcards.html` |  |
| `automation-studio/symblic-help-content.json` | `web/studio/symblic-help-content.json` |  |
| `automation-studio/symblic-help.css` | `web/studio/symblic-help.css` |  |
| `automation-studio/symblic-help.js` | `web/studio/symblic-help.js` |  |
| `automation-studio/symblic-inquiry.js` | `web/studio/symblic-inquiry.js` |  |
| `automation-studio/symblic-intent.js` | `web/studio/symblic-intent.js` |  |
| `automation-studio/symblic-logic.js` | `web/studio/symblic-logic.js` |  |
| `automation-studio/symblic-memory.js` | `web/studio/symblic-memory.js` |  |
| `automation-studio/symblic-page.js` | `web/studio/symblic-page.js` |  |
| `automation-studio/symblic-picker.css` | `web/studio/symblic-picker.css` |  |
| `automation-studio/symblic-picker.js` | `web/studio/symblic-picker.js` |  |
| `automation-studio/symblic-pixel-program.js` | `web/studio/symblic-pixel-program.js` |  |
| `automation-studio/symblic-pixel-vm.js` | `web/studio/symblic-pixel-vm.js` |  |
| `automation-studio/symblic-policies.js` | `web/studio/symblic-policies.js` |  |
| `automation-studio/symblic-supervisor.js` | `web/studio/symblic-supervisor.js` |  |
| `automation-studio/symblic-workcards.js` | `web/studio/symblic-workcards.js` |  |
| `automation-studio/symblic.css` | `web/studio/symblic.css` |  |
| `automation-studio/symblic.html` | `web/studio/symblic.html` |  |
| `symblic-learn.html` | `web/academy/index.html` | loads its files by relative paths, with `web/hub/standalone-shell.js` when the host's page library is absent |
| `symblic-learn.js` | `web/academy/symblic-learn.js` | the research reader loads catalog documents as static files; check and preview need the host |
| `symblic-learn.css` | `web/academy/symblic-learn.css` |  |
| `symblic-academy-content.js` | `web/academy/symblic-academy-content.js` | source and reference links rewritten to repository paths; entries for documents not in this repository removed |

</details>

## Other files

| Old path | New path | Note |
|---|---|---|
| `symblic_lib/text.sym` | `symblic/lang/library/text.sym` | moved again after the first move |

## Tests

Run a package's tests with `DASH_TEST=1 python3 -m unittest discover -s tests/<package> -t .` from the repository
root. Tests of host-only code are in `tests/integration/` and skip themselves where the host is missing.

<details><summary>351 test files</summary>

| Old path | New path | Note |
|---|---|---|
| `tests/test_symblic_discrete.py` | `tests/adapters/test_symblic_discrete.py` |  |
| `tests/test_symblic_finite_logic.py` | `tests/adapters/test_symblic_finite_logic.py` |  |
| `tests/test_symblic_geometry.py` | `tests/adapters/test_symblic_geometry.py` |  |
| `tests/test_symblic_knowledge.py` | `tests/adapters/test_symblic_knowledge.py` |  |
| `tests/test_symblic_logic.py` | `tests/adapters/test_symblic_logic.py` |  |
| `tests/test_symblic_logic_incremental.py` | `tests/adapters/test_symblic_logic_incremental.py` |  |
| `tests/test_symblic_logic_namespaces.py` | `tests/adapters/test_symblic_logic_namespaces.py` |  |
| `tests/test_symblic_operators.py` | `tests/adapters/test_symblic_operators.py` |  |
| `tests/test_symblic_projection.py` | `tests/adapters/test_symblic_projection.py` |  |
| `tests/test_symblic_proof.py` | `tests/adapters/test_symblic_proof.py` |  |
| `tests/test_symblic_proof_command.py` | `tests/adapters/test_symblic_proof_command.py` |  |
| `tests/test_symblic_proof_run.py` | `tests/adapters/test_symblic_proof_run.py` |  |
| `tests/test_symblic_proof_scan_bounds.py` | `tests/adapters/test_symblic_proof_scan_bounds.py` |  |
| `tests/test_symblic_proof_session.py` | `tests/adapters/test_symblic_proof_session.py` |  |
| `tests/test_symblic_proof_step_handoff_integrity.py` | `tests/adapters/test_symblic_proof_step_handoff_integrity.py` |  |
| `tests/test_symblic_proof_step_wire.py` | `tests/adapters/test_symblic_proof_step_wire.py` |  |
| `tests/test_symblic_proof_steps.py` | `tests/adapters/test_symblic_proof_steps.py` |  |
| `tests/test_symblic_proof_steps_run.py` | `tests/adapters/test_symblic_proof_steps_run.py` |  |
| `tests/test_symblic_quantities.py` | `tests/adapters/test_symblic_quantities.py` |  |
| `tests/test_symblic_transport.py` | `tests/adapters/test_symblic_transport.py` |  |
| `tests/test_symblic_variational.py` | `tests/adapters/test_symblic_variational.py` |  |
| `tests/test_symblic_authoring.py` | `tests/authoring/test_symblic_authoring.py` |  |
| `tests/test_symblic_editor_diagnostics.py` | `tests/authoring/test_symblic_editor_diagnostics.py` |  |
| `tests/test_symblic_paper.py` | `tests/authoring/test_symblic_paper.py` |  |
| `tests/test_symblic_tighten.py` | `tests/authoring/test_symblic_tighten.py` |  |
| `tests/test_symblic_tighten_fidelity.py` | `tests/authoring/test_symblic_tighten_fidelity.py` |  |
| `tests/test_symblic_workcards.py` | `tests/authoring/test_symblic_workcards.py` |  |
| `tests/test_symblic_autogen.py` | `tests/autogen/test_symblic_autogen.py` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/test_symblicos_autogen.py` | `tests/autogen/test_symblicos_autogen.py` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/test_symblicos_autogen_kernel.py` | `tests/autogen/test_symblicos_autogen_kernel.py` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/test_symblicos_autogen_v2.py` | `tests/autogen/test_symblicos_autogen_v2.py` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/test_symblic_bench_ambiguity.py` | `tests/bench/test_symblic_bench_ambiguity.py` |  |
| `tests/test_symblic_bench_ambiguity_cli.py` | `tests/bench/test_symblic_bench_ambiguity_cli.py` |  |
| `tests/test_symblic_bench_matched.py` | `tests/bench/test_symblic_bench_matched.py` |  |
| `tests/test_symblic_eval_protocol.py` | `tests/bench/test_symblic_eval_protocol.py` |  |
| `tests/test_symblic_local_beta.py` | `tests/bench/test_symblic_local_beta.py` |  |
| `tests/browser/academy-depth.mjs` | `tests/browser/symblic-academy.mjs` | the page is `/web/academy/index.html` now, and its reader loads documents as files instead of calling the host's source API |
| `tests/browser/symblic-atomic.mjs` | `tests/browser/symblic-atomic.mjs` |  |
| `tests/browser/symblic-autogen.mjs` | `tests/browser/symblic-autogen.mjs` |  |
| `tests/browser/symblic-beta.mjs` | `tests/browser/symblic-beta.mjs` |  |
| `tests/browser/symblic-composition.mjs` | `tests/browser/symblic-composition.mjs` |  |
| `tests/browser/symblic-constructor-controls.mjs` | `tests/browser/symblic-constructor-controls.mjs` |  |
| `tests/browser/symblic-determinism.mjs` | `tests/browser/symblic-determinism.mjs` |  |
| `tests/browser/symblic-differential.mjs` | `tests/browser/symblic-differential.mjs` |  |
| `tests/browser/symblic-editor-diagnostics.mjs` | `tests/browser/symblic-editor-diagnostics.mjs` |  |
| `tests/browser/symblic-editor-integration.mjs` | `tests/browser/symblic-editor-integration.mjs` |  |
| `tests/browser/symblic-english-atomic-construction-circuit.mjs` | `tests/browser/symblic-english-atomic-construction-circuit.mjs` |  |
| `tests/browser/symblic-english-circuit.mjs` | `tests/browser/symblic-english-circuit.mjs` |  |
| `tests/browser/symblic-english-construction-circuit.mjs` | `tests/browser/symblic-english-construction-circuit.mjs` |  |
| `tests/browser/symblic-english-pixel-circuit.mjs` | `tests/browser/symblic-english-pixel-circuit.mjs` |  |
| `tests/browser/symblic-english-rain.mjs` | `tests/browser/symblic-english-rain.mjs` |  |
| `tests/browser/symblic-english.mjs` | `tests/browser/symblic-english.mjs` |  |
| `tests/browser/symblic-example-downloads.mjs` | `tests/browser/symblic-example-downloads.mjs` |  |
| `tests/browser/symblic-focused.mjs` | `tests/browser/symblic-focused.mjs` |  |
| `tests/browser/symblic-forge-native.mjs` | `tests/browser/symblic-forge-native.mjs` |  |
| `tests/browser/symblic-forge.mjs` | `tests/browser/symblic-forge.mjs` |  |
| `tests/browser/symblic-graph-number-scan.test.mjs` | `tests/browser/symblic-graph-number-scan.test.mjs` |  |
| `tests/browser/symblic-graphs.mjs` | `tests/browser/symblic-graphs.mjs` |  |
| `tests/browser/symblic-help.mjs` | `tests/browser/symblic-help.mjs` |  |
| `tests/browser/symblic-hub.mjs` | `tests/browser/symblic-hub.mjs` |  |
| `tests/browser/symblic-incremental.mjs` | `tests/browser/symblic-incremental.mjs` |  |
| `tests/browser/symblic-intent-selection.mjs` | `tests/browser/symblic-intent-selection.mjs` |  |
| `tests/browser/symblic-memory.mjs` | `tests/browser/symblic-memory.mjs` |  |
| `tests/browser/symblic-mica.mjs` | `tests/browser/symblic-mica.mjs` |  |
| `tests/browser/symblic-model-picker.mjs` | `tests/browser/symblic-model-picker.mjs` |  |
| `tests/browser/symblic-picker.mjs` | `tests/browser/symblic-picker.mjs` |  |
| `tests/browser/symblic-pixel-program.mjs` | `tests/browser/symblic-pixel-program.mjs` |  |
| `tests/browser/symblic-pixel-vm.mjs` | `tests/browser/symblic-pixel-vm.mjs` |  |
| `tests/browser/symblic-policies.mjs` | `tests/browser/symblic-policies.mjs` |  |
| `tests/browser/symblic-policy-history.mjs` | `tests/browser/symblic-policy-history.mjs` |  |
| `tests/browser/symblic-reform.mjs` | `tests/browser/symblic-reform.mjs` |  |
| `tests/browser/symblic-steps.mjs` | `tests/browser/symblic-steps.mjs` |  |
| `tests/browser/symblic-supervisor.mjs` | `tests/browser/symblic-supervisor.mjs` |  |
| `tests/browser/symblic-task-cards.mjs` | `tests/browser/symblic-task-cards.mjs` |  |
| `tests/browser/symblic-team-numeric.mjs` | `tests/browser/symblic-team-numeric.mjs` |  |
| `tests/browser/symblic-terminal.mjs` | `tests/browser/symblic-terminal.mjs` |  |
| `tests/fixtures/symblic_lock_v2_d6baf27e.py` | `tests/constructor/fixtures/symblic_lock_v2_d6baf27e.py` | moved again after the first move |
| `tests/test_symblic_constructor_cleanup_notes.py` | `tests/constructor/test_symblic_constructor_cleanup_notes.py` |  |
| `tests/test_symblic_constructor_cli.py` | `tests/constructor/test_symblic_constructor_cli.py` |  |
| `tests/test_symblic_constructor_crash_recovery.py` | `tests/constructor/test_symblic_constructor_crash_recovery.py` |  |
| `tests/test_symblic_constructor_export_recovery.py` | `tests/constructor/test_symblic_constructor_export_recovery.py` |  |
| `tests/test_symblic_constructor_inspect.py` | `tests/constructor/test_symblic_constructor_inspect.py` |  |
| `tests/test_symblic_constructor_journal.py` | `tests/constructor/test_symblic_constructor_journal.py` |  |
| `tests/test_symblic_constructor_journal_v3.py` | `tests/constructor/test_symblic_constructor_journal_v3.py` |  |
| `tests/test_symblic_constructor_lock.py` | `tests/constructor/test_symblic_constructor_lock.py` |  |
| `tests/test_symblic_constructor_missing_records.py` | `tests/constructor/test_symblic_constructor_missing_records.py` |  |
| `tests/test_symblic_constructor_records.py` | `tests/constructor/test_symblic_constructor_records.py` |  |
| `tests/test_symblic_constructor_run.py` | `tests/constructor/test_symblic_constructor_run.py` |  |
| `tests/test_symblic_delegate.py` | `tests/delegate/test_symblic_delegate.py` |  |
| `tests/test_symblic_delegate_capsule.py` | `tests/delegate/test_symblic_delegate_capsule.py` |  |
| `tests/test_symblic_delegate_incremental.py` | `tests/delegate/test_symblic_delegate_incremental.py` |  |
| `tests/test_symblic_delegate_lifecycle.py` | `tests/delegate/test_symblic_delegate_lifecycle.py` |  |
| `tests/test_symblic_delegate_proof_card.py` | `tests/delegate/test_symblic_delegate_proof_card.py` |  |
| `tests/test_symblic_delegate_proof_focus.py` | `tests/delegate/test_symblic_delegate_proof_focus.py` |  |
| `tests/test_symblic_delegate_proof_obligation.py` | `tests/delegate/test_symblic_delegate_proof_obligation.py` |  |
| `tests/test_symblic_delegate_proof_step.py` | `tests/delegate/test_symblic_delegate_proof_step.py` |  |
| `tests/test_symblic_delegate_result.py` | `tests/delegate/test_symblic_delegate_result.py` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/test_symblic_delegate_routing.py` | `tests/delegate/test_symblic_delegate_routing.py` |  |
| `tests/test_symblic_delegate_run.py` | `tests/delegate/test_symblic_delegate_run.py` |  |
| `tests/test_symblic_distill.py` | `tests/distill/test_symblic_distill.py` |  |
| `tests/test_symblic_distill_checkers.py` | `tests/distill/test_symblic_distill_checkers.py` |  |
| `tests/test_symblic_distill_export.py` | `tests/distill/test_symblic_distill_export.py` |  |
| `tests/test_symblic_english.py` | `tests/english/test_symblic_english.py` |  |
| `tests/test_symblic_english_build.py` | `tests/english/test_symblic_english_build.py` |  |
| `tests/test_symblic_english_build_entry.py` | `tests/english/test_symblic_english_build_entry.py` |  |
| `tests/test_symblic_english_construction_recovery.py` | `tests/english/test_symblic_english_construction_recovery.py` |  |
| `tests/test_symblic_english_pixel_checks.py` | `tests/english/test_symblic_english_pixel_checks.py` |  |
| `tests/test_symblic_english_pixel_recovery.py` | `tests/english/test_symblic_english_pixel_recovery.py` |  |
| `tests/test_symblic_english_pixels.py` | `tests/english/test_symblic_english_pixels.py` |  |
| `tests/test_symblic_english_pixels_entry.py` | `tests/english/test_symblic_english_pixels_entry.py` |  |
| `tests/test_symblic_english_runtime.py` | `tests/english/test_symblic_english_runtime.py` |  |
| `tests/test_symblic_expense_handoff.py` | `tests/examples/test_symblic_expense_handoff.py` | moved again after the first move |
| `tests/test_symblic_experiments_context.py` | `tests/experiments/test_symblic_experiments_context.py` |  |
| `tests/test_symblic_experiments_geometry.py` | `tests/experiments/test_symblic_experiments_geometry.py` |  |
| `tests/test_symblic_experiments_graph.py` | `tests/experiments/test_symblic_experiments_graph.py` |  |
| `tests/test_symblic_experiments_identity.py` | `tests/experiments/test_symblic_experiments_identity.py` |  |
| `tests/test_symblic_experiments_numerics.py` | `tests/experiments/test_symblic_experiments_numerics.py` |  |
| `tests/test_symblic_experiments_protocols.py` | `tests/experiments/test_symblic_experiments_protocols.py` |  |
| `tests/test_symblic_experiments_quantum.py` | `tests/experiments/test_symblic_experiments_quantum.py` |  |
| `tests/test_symblic_experiments_resources.py` | `tests/experiments/test_symblic_experiments_resources.py` |  |
| `tests/test_symblic_experiments_sampling.py` | `tests/experiments/test_symblic_experiments_sampling.py` |  |
| `tests/test_symblic_experiments_structure.py` | `tests/experiments/test_symblic_experiments_structure.py` |  |
| `tests/test_symblic_experiments_transport.py` | `tests/experiments/test_symblic_experiments_transport.py` |  |
| `tests/fixtures/symblic-editor-checks.json` | `tests/fixtures/symblic-editor-checks.json` |  |
| `tests/fixtures/symblic-english-atomic-construction.json` | `tests/fixtures/symblic-english-atomic-construction.json` |  |
| `tests/fixtures/symblic-english-construction.json` | `tests/fixtures/symblic-english-construction.json` |  |
| `tests/fixtures/symblic-english-pixel-recovery.json` | `tests/fixtures/symblic-english-pixel-recovery.json` |  |
| `tests/fixtures/symblic-english-pixel-vm-v1.json` | `tests/fixtures/symblic-english-pixel-vm-v1.json` |  |
| `tests/fixtures/symblic-english-pixel-vm.json` | `tests/fixtures/symblic-english-pixel-vm.json` |  |
| `tests/fixtures/symblic-english-pixels.json` | `tests/fixtures/symblic-english-pixels.json` |  |
| `tests/fixtures/symblic_capsule_full_v4.json` | `tests/fixtures/symblic_capsule_full_v4.json` |  |
| `tests/fixtures/symblic_catalog_v7_parity.json` | `tests/fixtures/symblic_catalog_v7_parity.json` |  |
| `tests/fixtures/symblic_catalog_v8_parity.json` | `tests/fixtures/symblic_catalog_v8_parity.json` |  |
| `tests/fixtures/symblic_cli_before_constructor.sh` | `tests/fixtures/symblic_cli_before_constructor.sh` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/fixtures/symblic_delegate_v5_parity.json` | `tests/fixtures/symblic_delegate_v5_parity.json` |  |
| `tests/fixtures/symblic_delegate_v6_parity.json` | `tests/fixtures/symblic_delegate_v6_parity.json` |  |
| `tests/fixtures/symblic_delegate_v7_parity.json` | `tests/fixtures/symblic_delegate_v7_parity.json` |  |
| `tests/fixtures/symblic_delegate_v8_parity.json` | `tests/fixtures/symblic_delegate_v8_parity.json` |  |
| `tests/test_symblic_forge_coach_construction.py` | `tests/forge/test_symblic_forge_coach_construction.py` |  |
| `tests/test_symblic_forge_core.py` | `tests/forge/test_symblic_forge_core.py` |  |
| `tests/test_symblic_forge_exports.py` | `tests/forge/test_symblic_forge_exports.py` |  |
| `tests/test_symblic_forge_models.py` | `tests/forge/test_symblic_forge_models.py` |  |
| `tests/test_symblic_graph.py` | `tests/graph/test_symblic_graph.py` |  |
| `tests/test_symblic_graph_bounds.py` | `tests/graph/test_symblic_graph_bounds.py` |  |
| `tests/test_symblic_graph_compose.py` | `tests/graph/test_symblic_graph_compose.py` |  |
| `tests/test_symblic_graph_compose_entry.py` | `tests/graph/test_symblic_graph_compose_entry.py` |  |
| `tests/test_symblic_graph_epistemic.py` | `tests/graph/test_symblic_graph_epistemic.py` |  |
| `tests/test_symblic_graph_repair.py` | `tests/graph/test_symblic_graph_repair.py` |  |
| `tests/test_symblic_graph_run.py` | `tests/graph/test_symblic_graph_run.py` |  |
| `tests/test_symblic_graph_scaling.py` | `tests/graph/test_symblic_graph_scaling.py` |  |
| `tests/test_symblic_inquiry.py` | `tests/inquiry/test_symblic_inquiry.py` |  |
| `tests/test_symblic_catalog_focus.py` | `tests/integration/test_symblic_catalog_focus.py` | moved again after the first move |
| `tests/test_symblic_constructor_api.py` | `tests/integration/test_symblic_constructor_api.py` | moved again after the first move |
| `tests/test_symblic_constructor_controls.py` | `tests/integration/test_symblic_constructor_controls.py` | moved again after the first move |
| `tests/test_symblic_contract_pilot.py` | `tests/integration/test_symblic_contract_pilot.py` | moved again after the first move |
| `tests/test_symblic_determination_entry.py` | `tests/integration/test_symblic_determination_entry.py` | moved again after the first move |
| `tests/test_symblic_discrete_tasks.py` | `tests/integration/test_symblic_discrete_tasks.py` | moved again after the first move |
| `tests/test_symblic_editor_api.py` | `tests/integration/test_symblic_editor_api.py` | moved again after the first move |
| `tests/test_symblic_engine.py` | `tests/integration/test_symblic_engine.py` |  |
| `tests/test_symblic_english_entry.py` | `tests/integration/test_symblic_english_entry.py` | moved again after the first move |
| `tests/test_symblic_example_artifacts.py` | `tests/integration/test_symblic_example_artifacts.py` |  |
| `tests/test_symblic_example_tools.py` | `tests/integration/test_symblic_example_tools.py` | moved again after the first move |
| `tests/test_symblic_experiments_api.py` | `tests/integration/test_symblic_experiments_api.py` |  |
| `tests/test_symblic_forge_api.py` | `tests/integration/test_symblic_forge_api.py` |  |
| `tests/test_symblic_forge_bridge.py` | `tests/integration/test_symblic_forge_bridge.py` |  |
| `tests/test_symblic_forge_examples.py` | `tests/integration/test_symblic_forge_examples.py` |  |
| `tests/test_symblic_forge_integration.py` | `tests/integration/test_symblic_forge_integration.py` |  |
| `tests/test_symblic_forge_team_coach.py` | `tests/integration/test_symblic_forge_team_coach.py` |  |
| `tests/test_symblic_frontier_ladder.py` | `tests/integration/test_symblic_frontier_ladder.py` | moved again after the first move |
| `tests/test_symblic_graph_api.py` | `tests/integration/test_symblic_graph_api.py` |  |
| `tests/test_symblic_graph_api_audit.py` | `tests/integration/test_symblic_graph_api_audit.py` |  |
| `tests/test_symblic_inquiry_api.py` | `tests/integration/test_symblic_inquiry_api.py` |  |
| `tests/test_symblic_intent_api.py` | `tests/integration/test_symblic_intent_api.py` |  |
| `tests/test_symblic_intent_page.py` | `tests/integration/test_symblic_intent_page.py` | moved again after the first move |
| `tests/test_symblic_intent_selection.py` | `tests/integration/test_symblic_intent_selection.py` | moved again after the first move |
| `tests/test_symblic_lang_api.py` | `tests/integration/test_symblic_lang_api.py` |  |
| `tests/test_symblic_memory_api.py` | `tests/integration/test_symblic_memory_api.py` |  |
| `tests/test_symblic_mica_api.py` | `tests/integration/test_symblic_mica_api.py` |  |
| `tests/test_symblic_mica_forge_api.py` | `tests/integration/test_symblic_mica_forge_api.py` | moved again after the first move |
| `tests/test_symblic_mica_forge_api_native.py` | `tests/integration/test_symblic_mica_forge_api_native.py` | moved again after the first move |
| `tests/test_symblic_model_recheck_api.py` | `tests/integration/test_symblic_model_recheck_api.py` | moved again after the first move |
| `tests/test_symblic_policy_api.py` | `tests/integration/test_symblic_policy_api.py` |  |
| `tests/test_symblic_policy_lease.py` | `tests/integration/test_symblic_policy_lease.py` | moved again after the first move |
| `tests/test_symblic_policy_repair.py` | `tests/integration/test_symblic_policy_repair.py` | moved again after the first move |
| `tests/test_symblic_project_teams.py` | `tests/integration/test_symblic_project_teams.py` | moved again after the first move |
| `tests/test_symblic_proof_card_entry.py` | `tests/integration/test_symblic_proof_card_entry.py` | moved again after the first move |
| `tests/test_symblic_proof_focus_entry.py` | `tests/integration/test_symblic_proof_focus_entry.py` | moved again after the first move |
| `tests/test_symblic_proof_obligation_entry.py` | `tests/integration/test_symblic_proof_obligation_entry.py` | moved again after the first move |
| `tests/test_symblic_proof_step_entry.py` | `tests/integration/test_symblic_proof_step_entry.py` | moved again after the first move |
| `tests/test_symblic_resume_api.py` | `tests/integration/test_symblic_resume_api.py` | moved again after the first move |
| `tests/test_symblic_review.py` | `tests/integration/test_symblic_review.py` | moved again after the first move |
| `tests/test_symblic_spec_compare_api.py` | `tests/integration/test_symblic_spec_compare_api.py` | moved again after the first move |
| `tests/test_symblic_steps_api.py` | `tests/integration/test_symblic_steps_api.py` |  |
| `tests/test_symblic_strict_identity_entry.py` | `tests/integration/test_symblic_strict_identity_entry.py` | moved again after the first move |
| `tests/test_symblic_supervisor.py` | `tests/integration/test_symblic_supervisor.py` |  |
| `tests/test_symblic_task_card_api.py` | `tests/integration/test_symblic_task_card_api.py` | moved again after the first move |
| `tests/test_symblic_task_cli.py` | `tests/integration/test_symblic_task_cli.py` | moved again after the first move |
| `tests/test_symblic_task_cli_autogen.py` | `tests/integration/test_symblic_task_cli_autogen.py` | moved again after the first move |
| `tests/test_symblic_tighten_api.py` | `tests/integration/test_symblic_tighten_api.py` | moved again after the first move |
| `tests/test_symblic_web.py` | `tests/integration/test_symblic_web.py` |  |
| `tests/test_symblic_web_catalog.py` | `tests/integration/test_symblic_web_catalog.py` |  |
| `tests/test_symblicos_tasks.py` | `tests/integration/test_symblicos_tasks.py` | moved again after the first move |
| `tests/test_symblic_intent.py` | `tests/intent/test_symblic_intent.py` |  |
| `tests/test_symblic_intent_coverage.py` | `tests/intent/test_symblic_intent_coverage.py` |  |
| `tests/test_symblic_requirement_execution.py` | `tests/intent/test_symblic_requirement_execution.py` |  |
| `tests/js/symblic-editor-diagnostics.cjs` | `tests/js/symblic-editor-diagnostics.cjs` |  |
| `tests/test_symblic_js_assets.py` | `tests/js/test_symblic_js_assets.py` |  |
| `tests/test_symblic_js_availability.py` | `tests/js/test_symblic_js_availability.py` |  |
| `tests/test_symblic_js_binding_writes.py` | `tests/js/test_symblic_js_binding_writes.py` |  |
| `tests/test_symblic_js_contract.py` | `tests/js/test_symblic_js_contract.py` |  |
| `tests/test_symblic_js_normalize.py` | `tests/js/test_symblic_js_normalize.py` |  |
| `tests/test_symblic_js_output.py` | `tests/js/test_symblic_js_output.py` |  |
| `tests/test_symblic_js_reobserve.py` | `tests/js/test_symblic_js_reobserve.py` |  |
| `tests/test_symblic_js_review_findings.py` | `tests/js/test_symblic_js_review_findings.py` |  |
| `tests/fixtures/symblic_epistemic_baseline_e5aa249c.py` | `tests/kernel/fixtures/symblic_epistemic_baseline_e5aa249c.py` | moved again after the first move |
| `tests/fixtures/symblic_epistemic_bytebound_ec009877.py` | `tests/kernel/fixtures/symblic_epistemic_bytebound_ec009877.py` | moved again after the first move |
| `tests/fixtures/symblic_epistemic_prebytebound_c3710aed.py` | `tests/kernel/fixtures/symblic_epistemic_prebytebound_c3710aed.py` | moved again after the first move |
| `tests/test_symblic.py` | `tests/kernel/test_symblic.py` |  |
| `tests/test_symblic_adversarial.py` | `tests/kernel/test_symblic_adversarial.py` |  |
| `tests/test_symblic_any_schema.py` | `tests/kernel/test_symblic_any_schema.py` |  |
| `tests/test_symblic_auto_budget.py` | `tests/kernel/test_symblic_auto_budget.py` |  |
| `tests/test_symblic_auto_route.py` | `tests/kernel/test_symblic_auto_route.py` |  |
| `tests/test_symblic_bookkeeping_d16.py` | `tests/kernel/test_symblic_bookkeeping_d16.py` |  |
| `tests/test_symblic_bookkeeping_d16_v4.py` | `tests/kernel/test_symblic_bookkeeping_d16_v4.py` |  |
| `tests/test_symblic_bounded_determination.py` | `tests/kernel/test_symblic_bounded_determination.py` |  |
| `tests/test_symblic_capsule_presentation.py` | `tests/kernel/test_symblic_capsule_presentation.py` |  |
| `tests/test_symblic_certificates.py` | `tests/kernel/test_symblic_certificates.py` |  |
| `tests/test_symblic_code.py` | `tests/kernel/test_symblic_code.py` |  |
| `tests/test_symblic_consensus_fields_regression.py` | `tests/kernel/test_symblic_consensus_fields_regression.py` |  |
| `tests/test_symblic_context.py` | `tests/kernel/test_symblic_context.py` |  |
| `tests/test_symblic_core_repair_determinism.py` | `tests/kernel/test_symblic_core_repair_determinism.py` |  |
| `tests/test_symblic_core_repair_grounding.py` | `tests/kernel/test_symblic_core_repair_grounding.py` |  |
| `tests/test_symblic_core_repair_kernel.py` | `tests/kernel/test_symblic_core_repair_kernel.py` |  |
| `tests/test_symblic_core_repair_run.py` | `tests/kernel/test_symblic_core_repair_run.py` |  |
| `tests/test_symblic_count_literals.py` | `tests/kernel/test_symblic_count_literals.py` |  |
| `tests/test_symblic_determination_control.py` | `tests/kernel/test_symblic_determination_control.py` |  |
| `tests/test_symblic_diagnose.py` | `tests/kernel/test_symblic_diagnose.py` |  |
| `tests/test_symblic_diagnostic_feedback.py` | `tests/kernel/test_symblic_diagnostic_feedback.py` |  |
| `tests/test_symblic_effects.py` | `tests/kernel/test_symblic_effects.py` |  |
| `tests/test_symblic_effects_closures.py` | `tests/kernel/test_symblic_effects_closures.py` |  |
| `tests/test_symblic_empty_record_literal.py` | `tests/kernel/test_symblic_empty_record_literal.py` |  |
| `tests/test_symblic_epistemic.py` | `tests/kernel/test_symblic_epistemic.py` |  |
| `tests/test_symblic_epistemic_bytebound.py` | `tests/kernel/test_symblic_epistemic_bytebound.py` |  |
| `tests/test_symblic_epistemic_claim_path.py` | `tests/kernel/test_symblic_epistemic_claim_path.py` |  |
| `tests/test_symblic_epistemic_run.py` | `tests/kernel/test_symblic_epistemic_run.py` |  |
| `tests/test_symblic_evidence.py` | `tests/kernel/test_symblic_evidence.py` |  |
| `tests/test_symblic_evidence_lineage.py` | `tests/kernel/test_symblic_evidence_lineage.py` |  |
| `tests/test_symblic_execution.py` | `tests/kernel/test_symblic_execution.py` |  |
| `tests/test_symblic_finite_fallback.py` | `tests/kernel/test_symblic_finite_fallback.py` |  |
| `tests/test_symblic_finite_fallback_review.py` | `tests/kernel/test_symblic_finite_fallback_review.py` |  |
| `tests/test_symblic_finite_resource_regression.py` | `tests/kernel/test_symblic_finite_resource_regression.py` |  |
| `tests/test_symblic_grounding.py` | `tests/kernel/test_symblic_grounding.py` |  |
| `tests/test_symblic_identity.py` | `tests/kernel/test_symblic_identity.py` |  |
| `tests/test_symblic_json_schema.py` | `tests/kernel/test_symblic_json_schema.py` |  |
| `tests/test_symblic_json_schema_context.py` | `tests/kernel/test_symblic_json_schema_context.py` |  |
| `tests/test_symblic_json_schema_native.py` | `tests/kernel/test_symblic_json_schema_native.py` |  |
| `tests/test_symblic_json_schema_provider.py` | `tests/kernel/test_symblic_json_schema_provider.py` |  |
| `tests/test_symblic_kernel23.py` | `tests/kernel/test_symblic_kernel23.py` |  |
| `tests/test_symblic_lane_b_followup.py` | `tests/kernel/test_symblic_lane_b_followup.py` |  |
| `tests/test_symblic_lib23.py` | `tests/kernel/test_symblic_lib23.py` |  |
| `tests/test_symblic_lib23b.py` | `tests/kernel/test_symblic_lib23b.py` |  |
| `tests/test_symblic_literal_roundtrip.py` | `tests/kernel/test_symblic_literal_roundtrip.py` |  |
| `tests/test_symblic_lock.py` | `tests/kernel/test_symblic_lock.py` |  |
| `tests/test_symblic_micro.py` | `tests/kernel/test_symblic_micro.py` |  |
| `tests/test_symblic_module_provenance.py` | `tests/kernel/test_symblic_module_provenance.py` |  |
| `tests/test_symblic_ollama_limits.py` | `tests/kernel/test_symblic_ollama_limits.py` |  |
| `tests/test_symblic_parameter_lineage.py` | `tests/kernel/test_symblic_parameter_lineage.py` |  |
| `tests/test_symblic_parser_bounds.py` | `tests/kernel/test_symblic_parser_bounds.py` |  |
| `tests/test_symblic_picker_native.py` | `tests/kernel/test_symblic_picker_native.py` |  |
| `tests/test_symblic_profiles.py` | `tests/kernel/test_symblic_profiles.py` |  |
| `tests/test_symblic_progress_outputs.py` | `tests/kernel/test_symblic_progress_outputs.py` |  |
| `tests/test_symblic_provider_identity_pin.py` | `tests/kernel/test_symblic_provider_identity_pin.py` |  |
| `tests/test_symblic_reinforcement_contracts.py` | `tests/kernel/test_symblic_reinforcement_contracts.py` |  |
| `tests/test_symblic_repair_variation.py` | `tests/kernel/test_symblic_repair_variation.py` |  |
| `tests/test_symblic_resources.py` | `tests/kernel/test_symblic_resources.py` |  |
| `tests/test_symblic_run23.py` | `tests/kernel/test_symblic_run23.py` |  |
| `tests/test_symblic_solver_provenance.py` | `tests/kernel/test_symblic_solver_provenance.py` |  |
| `tests/test_symblic_soundness.py` | `tests/kernel/test_symblic_soundness.py` |  |
| `tests/test_symblic_verification_deadline.py` | `tests/kernel/test_symblic_verification_deadline.py` |  |
| `tests/test_symblic_vorticity_construction.py` | `tests/kernel/test_symblic_vorticity_construction.py` |  |
| `tests/test_symblic_witness_quantity_run.py` | `tests/kernel/test_symblic_witness_quantity_run.py` |  |
| `tests/test_symblic_lang.py` | `tests/lang/test_symblic_lang.py` |  |
| `tests/test_symblic_linear_provision.py` | `tests/linear/test_symblic_linear_provision.py` |  |
| `tests/test_symblic_memory.py` | `tests/memory/test_symblic_memory.py` |  |
| `tests/test_symblic_mica_bench.py` | `tests/mica/test_symblic_mica_bench.py` |  |
| `tests/test_symblic_mica_bundle.py` | `tests/mica/test_symblic_mica_bundle.py` |  |
| `tests/test_symblic_mica_calibration.py` | `tests/mica/test_symblic_mica_calibration.py` |  |
| `tests/test_symblic_mica_check_consistency.py` | `tests/mica/test_symblic_mica_check_consistency.py` |  |
| `tests/test_symblic_mica_check_consistency_native.py` | `tests/mica/test_symblic_mica_check_consistency_native.py` |  |
| `tests/test_symblic_mica_checkpack.py` | `tests/mica/test_symblic_mica_checkpack.py` |  |
| `tests/test_symblic_mica_checkpack_decimal.py` | `tests/mica/test_symblic_mica_checkpack_decimal.py` |  |
| `tests/test_symblic_mica_checkpack_link.py` | `tests/mica/test_symblic_mica_checkpack_link.py` |  |
| `tests/test_symblic_mica_checkpack_link_native.py` | `tests/mica/test_symblic_mica_checkpack_link_native.py` |  |
| `tests/test_symblic_mica_checkpack_native.py` | `tests/mica/test_symblic_mica_checkpack_native.py` |  |
| `tests/test_symblic_mica_cli.py` | `tests/mica/test_symblic_mica_cli.py` |  |
| `tests/test_symblic_mica_cli_split.py` | `tests/mica/test_symblic_mica_cli_split.py` |  |
| `tests/test_symblic_mica_contracts.py` | `tests/mica/test_symblic_mica_contracts.py` |  |
| `tests/test_symblic_mica_cost_review.py` | `tests/mica/test_symblic_mica_cost_review.py` |  |
| `tests/test_symblic_mica_costs.py` | `tests/mica/test_symblic_mica_costs.py` |  |
| `tests/test_symblic_mica_deterministic.py` | `tests/mica/test_symblic_mica_deterministic.py` |  |
| `tests/test_symblic_mica_domains.py` | `tests/mica/test_symblic_mica_domains.py` |  |
| `tests/test_symblic_mica_domains_native.py` | `tests/mica/test_symblic_mica_domains_native.py` |  |
| `tests/test_symblic_mica_execution.py` | `tests/mica/test_symblic_mica_execution.py` |  |
| `tests/test_symblic_mica_extensions.py` | `tests/mica/test_symblic_mica_extensions.py` |  |
| `tests/test_symblic_mica_forge.py` | `tests/mica/test_symblic_mica_forge.py` |  |
| `tests/test_symblic_mica_forge_cli.py` | `tests/mica/test_symblic_mica_forge_cli.py` |  |
| `tests/test_symblic_mica_forge_cli_delegation.py` | `tests/mica/test_symblic_mica_forge_cli_delegation.py` |  |
| `tests/test_symblic_mica_forge_native.py` | `tests/mica/test_symblic_mica_forge_native.py` |  |
| `tests/test_symblic_mica_historical_artifacts.py` | `tests/mica/test_symblic_mica_historical_artifacts.py` |  |
| `tests/test_symblic_mica_library.py` | `tests/mica/test_symblic_mica_library.py` |  |
| `tests/test_symblic_mica_module_integration_review.py` | `tests/mica/test_symblic_mica_module_integration_review.py` |  |
| `tests/test_symblic_mica_project.py` | `tests/mica/test_symblic_mica_project.py` |  |
| `tests/test_symblic_mica_promote.py` | `tests/mica/test_symblic_mica_promote.py` |  |
| `tests/test_symblic_mica_proposal.py` | `tests/mica/test_symblic_mica_proposal.py` |  |
| `tests/test_symblic_mica_proposal_journey.py` | `tests/mica/test_symblic_mica_proposal_journey.py` |  |
| `tests/test_symblic_mica_provider_failure.py` | `tests/mica/test_symblic_mica_provider_failure.py` |  |
| `tests/test_symblic_mica_refinement.py` | `tests/mica/test_symblic_mica_refinement.py` |  |
| `tests/test_symblic_mica_review_regressions.py` | `tests/mica/test_symblic_mica_review_regressions.py` |  |
| `tests/test_symblic_mica_routing.py` | `tests/mica/test_symblic_mica_routing.py` |  |
| `tests/test_symblic_mica_strategies.py` | `tests/mica/test_symblic_mica_strategies.py` |  |
| `tests/test_symblic_mica_strategy.py` | `tests/mica/test_symblic_mica_strategy.py` |  |
| `tests/test_automation_symblic_nodes.py` | `tests/misc/test_automation_symblic_nodes.py` |  |
| `tests/test_symblicos_acceptance.py` | `tests/os/test_symblicos_acceptance.py` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/test_symblicos_image_builder.py` | `tests/os/test_symblicos_image_builder.py` | not at this path any more (renamed or merged by a later reorganization; see the package README) |
| `tests/test_symblic_policy_graph.py` | `tests/policy/test_symblic_policy_graph.py` |  |
| `tests/test_symblic_policy_learning.py` | `tests/policy/test_symblic_policy_learning.py` |  |
| `tests/test_symblic_policy_learning_audit.py` | `tests/policy/test_symblic_policy_learning_audit.py` |  |
| `tests/test_symblic_policy_store.py` | `tests/policy/test_symblic_policy_store.py` |  |
| `tests/test_symblic_portable.py` | `tests/portable/test_symblic_portable.py` |  |
| `tests/test_symblic_agent_teams.py` | `tests/providers/test_symblic_agent_teams.py` |  |
| `tests/test_symblic_apply.py` | `tests/providers/test_symblic_apply.py` |  |
| `tests/test_symblic_spec_build.py` | `tests/spec/test_symblic_spec_build.py` |  |
| `tests/test_symblic_spec_cli.py` | `tests/spec/test_symblic_spec_cli.py` |  |
| `tests/test_symblic_spec_cli_requirements.py` | `tests/spec/test_symblic_spec_cli_requirements.py` |  |
| `tests/test_symblic_spec_compare.py` | `tests/spec/test_symblic_spec_compare.py` |  |
| `tests/test_symblic_spec_contracts.py` | `tests/spec/test_symblic_spec_contracts.py` |  |
| `tests/test_symblic_spec_given.py` | `tests/spec/test_symblic_spec_given.py` |  |
| `tests/test_symblic_spec_presentation.py` | `tests/spec/test_symblic_spec_presentation.py` |  |
| `tests/test_symblic_spec_uses_shown.py` | `tests/spec/test_symblic_spec_uses_shown.py` |  |
| `tests/test_symblic_steps.py` | `tests/steps/test_symblic_steps.py` |  |
| `tests/test_symblic_steps_parcel.py` | `tests/steps/test_symblic_steps_parcel.py` |  |
| `tests/test_symblic_steps_review.py` | `tests/steps/test_symblic_steps_review.py` |  |
| `tests/symblic_frames_check.js` | `tests/symblic_frames_check.js` |  |
| `tests/symblic_intent_page_check.js` | `tests/symblic_intent_page_check.js` |  |
| `tests/test_symblic_agent_handoff_cli.py` | `tests/tools/test_symblic_agent_handoff_cli.py` | moved again after the first move |
| `tests/test_symblic_cli_agent.py` | `tests/tools/test_symblic_cli_agent.py` | moved again after the first move |
| `tests/test_symblic_conformance_snapshot.py` | `tests/tools/test_symblic_conformance_snapshot.py` | moved again after the first move |
| `tests/test_symblic_docs_audit.py` | `tests/tools/test_symblic_docs_audit.py` | moved again after the first move |
| `tests/test_symblic_refresh_catalog.py` | `tests/tools/test_symblic_refresh_catalog.py` | moved again after the first move |
| `tests/test_symblic_reinforcement_stats.py` | `tests/tools/test_symblic_reinforcement_stats.py` | moved again after the first move |
| `tests/test_academy_depth.py` | `tests/web/test_symblic_academy.py`, `tests/integration/test_symblic_academy_sources.py` | the Symblic half only: the catalog checks, and the checks of the source route; the cases for another course of the host were left out |

</details>
