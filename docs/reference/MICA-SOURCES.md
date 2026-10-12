# MICA source-to-method adoption matrix

All 22 requested repositories were cloned through admitted cluster work and inspected at the commits below. This is a mapping of independently implemented method subsets, proposed extensions and deliberate non-adoptions. No upstream implementation was copied and no cloned runtime was installed. A clone is research evidence, not an integration claim. Named tests establish bounded implementation behavior only when run against the stated coherent source snapshot; empirical model comparisons remain pending.

Coverage: repository README/relevant official documentation, observed licenses and the listed algorithm files; primary paper method sections/abstracts where linked. This does not mean every repository file, every appendix or all cited literature was read. Exact inspected-file/license hashes are retained in [MICA-SOURCES.json](MICA-SOURCES.json). See [MICA.md](MICA.md) for implemented scope, invocation and outstanding acceptance work.

## ezelikman/parsel

Source: [ezelikman/parsel](https://github.com/ezelikman/parsel/tree/bc1687cab9e8a79249f0d3e3cb4f5826dba39a95) · commit `bc1687cab9e8a79249f0d3e3cb4f5826dba39a95`. Observed licensing: No local license file found. No local license grant found; source not copied.

**Adoption status:** `implemented_method_subset`. Hierarchical function contracts, explicit dependencies and retained checked components across bounded alternatives.

**Implementation:** `symblic/mica/contracts.py:validate_plan`, `symblic/mica/search.py:proposal_to_plan`, `symblic/mica/search.py:MicaRun._build`.

**Tests:** `tests/mica/test_symblic_mica_contracts.py:test_rejects_dependency_and_parent_cycles`, `tests/mica/test_symblic_mica_execution.py:test_bad_planner_graph_uses_next_bounded_alternative`.

**Not adopted / limits:** No automatic SCC discovery or Parsel candidate-combination solver. Source-language mutual recursion must be one explicitly declared compound unit; task cycles are rejected.

**Inspected source:** `graph.py:84:strongly_connected_components`, `parsel.py:417:attempt_implementations`, `parsel.py:490:implement_scc`.

**Primary papers:** [author paper](https://arxiv.org/html/2212.10561v3).

## IPRC-DIP/ANPL

Source: [IPRC-DIP/ANPL](https://github.com/IPRC-DIP/ANPL/tree/bfc28987f11aee5290ad51ecac8248664d653640) · commit `bfc28987f11aee5290ad51ecac8248664d653640`. Observed licensing: No local license file found. No local license grant found; source not copied.

**Adoption status:** `implemented_method_subset`. Natural-language implementation units lower into fixed native asks with explicit dependency artifacts and checked invalidation.

**Implementation:** `symblic/mica/native.py:unit_source`, `symblic/mica/search.py:MicaRun._scoped_facts`, `symblic/mica/search.py:MicaRun._prepare_unit`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_dependency_capsule_contains_declared_closure_only`, `tests/mica/test_symblic_mica_review_regressions.py:test_equal_dependency_code_with_changed_contract_has_distinct_artifact_identity`.

**Not adopted / limits:** No upstream interactive runtime, Python execution, broad-source provider prompt or copied source.

**Inspected source:** `anpl/anpl.py:107:find_dependencies`, `anpl/anpl.py:123:fill_fun`, `anpl/synthesizer.py:67:fun_synthesis`.

**Primary papers:** [author paper](https://arxiv.org/abs/2305.18498).

## ZhangHanDong/agent-spec

Source: [ZhangHanDong/agent-spec](https://github.com/ZhangHanDong/agent-spec/tree/2483398da89bd392186849bb865aae969667ac0a) · commit `2483398da89bd392186849bb865aae969667ac0a`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `implemented_method_subset`. Requirement IDs, coverage, assumptions, validated graph and explicit proposal provenance connect root authority to evidence.

**Implementation:** `symblic/mica/contracts.py:normalize_request`, `symblic/mica/contracts.py:validate_plan`, `symblic/mica/project.py:MicaProject`.

**Tests:** `tests/mica/test_symblic_mica_contracts.py:test_sealed_plan_revalidates_every_derived_field`, `tests/mica/test_symblic_mica_project.py:test_model_cannot_change_original_objective_or_output_authority`.

**Not adopted / limits:** No adoption of its Rust runtime or claim that generated requirements fully capture human intent.

**Inspected source:** `src/spec_knowledge/requirement_graph.rs`, `src/spec_knowledge/requirement_plan.rs`, `src/spec_knowledge/test_obligations.rs`, `src/spec_knowledge/traceability.rs`, `docs/intent-compiler/architecture.md`.

## archiki/ADaPT

Source: [archiki/ADaPT](https://github.com/archiki/ADaPT/tree/ecdc4ab0030b4be9be122622d8ea78f8c59c44c4) · commit `ecdc4ab0030b4be9be122622d8ea78f8c59c44c4`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `implemented_method_subset`. decompose_on_failure begins with a whole-program attempt, then permits bounded decompositions driven by host-verified failures.

**Implementation:** `symblic/mica/search.py:direct_plan`, `symblic/mica/search.py:MicaRun.execute`, `symblic/mica/bench.py:MODE_FACTORS`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_bad_planner_graph_uses_next_bounded_alternative`, `tests/mica/test_symblic_mica_execution.py:test_call_budget_counts_every_failed_repair_and_never_oversubscribes`.

**Not adopted / limits:** No TextCraft environment/tool actions, heuristic model success authority, or claim of replicated paper performance. A dedicated actual-model comparison remains pending.

**Inspected source:** `run_textcraft.py:394:plan_and_run`, `run_textcraft.py:106:parse_expression`.

**Primary papers:** [author paper](https://arxiv.org/html/2311.05772v2).

## FoundationAgents/ReCode

Source: [FoundationAgents/ReCode](https://github.com/FoundationAgents/ReCode/tree/6e7223f71281d914762e78d7bbcf6446d362ecbc) · commit `6e7223f71281d914762e78d7bbcf6446d362ecbc`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `implemented_method_subset`. Explicit unresolved units expand into scoped children with retained failure/dependency context.

**Implementation:** `symblic/mica/refinement.py:refine_prompt`, `symblic/mica/refinement.py:apply_refinement`, `symblic/mica/search.py:MicaRun._propose`, `symblic/mica/native.py:unit_source`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_dependency_capsule_contains_declared_closure_only`, `tests/mica/test_symblic_mica_project.py:test_no_ambient_hidden_tests_or_files_enter_specification_context`.

**Not adopted / limits:** No training, shared executor or general on-demand recursive CodeNode interpreter; a failed contract can be replaced by a validated helper DAG while preserving the original wrapper and unaffected contracts.

**Inspected source:** `agents/recode/agent.py:120:_handle_stub`, `agents/recode/agent.py:143:_expand`, `agents/recode/utils.py:33:CodeNode`.

**Primary papers:** [author paper](https://arxiv.org/html/2510.23564v1).

## github/spec-kit

Source: [github/spec-kit](https://github.com/github/spec-kit/tree/0443760542e7e5269724744a2ac55c4bd386d095) · commit `0443760542e7e5269724744a2ac55c4bd386d095`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `methodology_and_documentation`. Separate objective, explicit requirement proposal, plan, execution and retained evidence; machine-readable interfaces expose each stage.

**Implementation:** `symblic/mica/project.py:root_prompt`, `symblic/mica/contracts.py:normalize_request`, `docs/reference/MICA.md`.

**Tests:** `tests/mica/test_symblic_mica_project.py:test_objective_build_preserves_authority_provenance_and_exact_calls`, `tests/mica/test_symblic_mica_cli.py:test_initial_plan_cannot_replace_objective_or_bypass_requirement_validation`.

**Not adopted / limits:** No global template/skill installation or replacement of repository instructions. Scaffolding is not runtime proof.

**Inspected source:** `templates/spec-template.md`, `templates/plan-template.md`, `templates/tasks-template.md`, `spec-driven.md`.

## FoundationAgents/AFlow

Source: [FoundationAgents/AFlow](https://github.com/FoundationAgents/AFlow/tree/3f457218fc716093fe53f6df8a5d5e6379d66346) · commit `3f457218fc716093fe53f6df8a5d5e6379d66346`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `implemented_method_subset`. Retain checked work while revising bounded alternative workflows using verified failures.

**Implementation:** `symblic/mica/search.py:MicaRun.execute`, `symblic/mica/search.py:MicaRun._build`, `symblic/mica/library.py:ComponentLibrary`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_bad_planner_graph_uses_next_bounded_alternative`, `tests/mica/test_symblic_mica_library.py:test_compatible_cross_run_reuse_makes_no_provider_calls`.

**Not adopted / limits:** No general workflow-operator optimizer, MCTS, indefinite rewrite loops or learned optimizer. Plans are accepted through actual checks, not model self-scores.

**Inspected source:** `scripts/optimizer.py:120:_optimize_graph`, `scripts/optimizer_utils/data_utils.py`, `scripts/optimizer_utils/experience_utils.py:91:update_experience`, `scripts/evaluator.py`.

**Primary papers:** [author paper](https://arxiv.org/html/2410.10762v3).

## SqueezeAILab/LLMCompiler

Source: [SqueezeAILab/LLMCompiler](https://github.com/SqueezeAILab/LLMCompiler/tree/a00c9d35507507da70e8c637eee64efc8c1857ae) · commit `a00c9d35507507da70e8c637eee64efc8c1857ae`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `implemented_method_subset`. Validated dependency-ready layer scheduling, bounded parallelism and serialized same-node model admission.

**Implementation:** `symblic/mica/contracts.py:validate_plan`, `symblic/mica/search.py:MicaRun._build`, `symblic/mica/search.py:MicaRun._native`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_multiworker_single_node_serializes_provider_dispatch`, `tests/mica/test_symblic_mica_execution.py:test_later_parallel_unknown_prevents_earlier_pending_dispatch_on_resume`.

**Not adopted / limits:** No streaming planner execution; the whole graph is admitted before dispatch. Existing durable native journals replace its example scheduler recovery.

**Inspected source:** `src/llm_compiler/task_fetching_unit.py:82:TaskFetchingUnit`, `src/llm_compiler/output_parser.py:97:_get_dependencies_from_graph`, `src/llm_compiler/planner.py:86:StreamingGraphParser`.

**Primary papers:** [author paper](https://arxiv.org/abs/2312.04511).

## alexzhang13/rlm

Source: [alexzhang13/rlm](https://github.com/alexzhang13/rlm/tree/d04208afbad29ca675ab13478c40ee8bebc84bfe) · commit `d04208afbad29ca675ab13478c40ee8bebc84bfe`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `implemented_method_subset`. Externally retained scoped state, bounded subordinate model calls and cumulative accounting instead of an ever-growing shared prompt.

**Implementation:** `symblic/mica/native.py:unit_source`, `symblic/mica/search.py:MicaRun._native`, `symblic/mica/project.py:MicaProject`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_unrelated_local_evaluator_file_never_enters_provider_context`, `tests/mica/test_symblic_mica_project.py:test_root_generation_consumes_original_call_allowance`.

**Not adopted / limits:** No same-process arbitrary REPL or unlimited long-context recursion. Call allowances are reserved before dispatch, not checked only after a loop.

**Inspected source:** `rlm/core/rlm.py:226:_spawn_completion_context`, `rlm/core/rlm.py:512:_check_iteration_limits`, `rlm/core/rlm.py:706:_subcall`, `rlm/core/lm_handler.py`.

**Primary papers:** [author paper](https://arxiv.org/abs/2512.24601).

## princeton-nlp/tree-of-thought-llm

Source: [princeton-nlp/tree-of-thought-llm](https://github.com/princeton-nlp/tree-of-thought-llm/tree/8050e67d0e3a0fddc424d7fa5801538722a4c4cc) · commit `8050e67d0e3a0fddc424d7fa5801538722a4c4cc`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `implemented_method_subset`. Retain alternative branches and let host checks decide whether search may proceed.

**Implementation:** `symblic/mica/search.py:MicaRun.execute`, `symblic/mica/search.py:failure_class`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_bad_planner_graph_uses_next_bounded_alternative`, `tests/mica/test_symblic_mica_execution.py:test_root_acceptance_rejects_candidate_that_passes_its_own_examples`.

**Not adopted / limits:** Current search is a bounded sequential alternative sequence, not BFS/DFS/beam traversal of arbitrary thought trees; model-valued thought scores are not correctness evidence.

**Inspected source:** `src/tot/methods/bfs.py:49:solve`, `src/tot/tasks/game24.py`.

**Primary papers:** [author paper](https://arxiv.org/abs/2305.10601).

## Z3Prover/z3

Source: [Z3Prover/z3](https://github.com/Z3Prover/z3/tree/2d08bfcad30cabb7b2819dd2f4c47b7bbf4c377f) · commit `2d08bfcad30cabb7b2819dd2f4c47b7bbf4c377f`. Observed licensing: MIT (LICENSE.txt). 

**Adoption status:** `existing_native_capability_not_new_dependency`. Use the existing native verifier/constructor boundary; MICA adds exact finite predicate implication and a finite coefficient family with explicit unknown/unsupported outcomes.

**Implementation:** `symblic/mica/contracts.py:validate_plan`, `symblic/mica/deterministic.py:compile_contract`, `symblic/mica/native.py:execute_kernel`, `symblic/constructor/core.py`.

**Tests:** `tests/mica/test_symblic_mica_contracts.py:test_false_refinement_refuses_even_tested_requirement`, `tests/mica/test_symblic_mica_deterministic.py:test_underconstrained_family_does_not_choose_a_favorite_or_call_a_model`.

**Not adopted / limits:** The cloned Z3 build was not installed. MICA affine determination uses existing finite native enumeration, not a new SMT backend. Existing optional linear solver support is not general JS verification.

**Inspected source:** `src/api/python/z3/z3.py`, `examples/python/example.py`, `LICENSE.txt`.

**Primary papers:** [author paper](https://microsoft.github.io/z3guide/).

## pschanely/crosshair

Source: [pschanely/crosshair](https://github.com/pschanely/crosshair/tree/35e504cc5b09846242e9ac67d10219b67d587a65) · commit `35e504cc5b09846242e9ac67d10219b67d587a65`. Observed licensing: MIT-default; bundled Apache/PSF notices (LICENSE). 

**Adoption status:** `not_adopted_runtime`. Research informed counterexample/unknown distinctions; existing finite checks remain independently implemented.

**Implementation:** `symblic/mica/contracts.py`, `symblic/mica/bench.py`.

**Tests:** `tests/mica/test_symblic_mica_contracts.py:test_refinement_exact_exhaustion_and_counterexample`, `tests/mica/test_symblic_mica_bench.py`.

**Not adopted / limits:** No Python symbolic-execution runtime or Python-to-JavaScript semantic translation is integrated. A supported-language checker adapter would require a separate explicit contract and sandbox.

**Inspected source:** `crosshair/core.py`, `crosshair/statespace.py`, `crosshair/diff_behavior.py`, `doc/source/limitations.rst`.

**Primary papers:** [author paper](https://crosshair.readthedocs.io/en/latest/limitations.html).

## HypothesisWorks/hypothesis

Source: [HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis/tree/1484f6dd4c0a220f68e2698afed29e2a16a3f654) · commit `1484f6dd4c0a220f68e2698afed29e2a16a3f654`. Observed licensing: MPL-2.0 (LICENSE.txt). MPL-2.0 with documented exceptions; no code copied.

**Adoption status:** `implemented_method_subset`. Seeded valid/invalid structured input generation with an independent reference oracle, frozen outside construction context.

**Implementation:** `symblic/mica/fixtures.py:arithmetic_collections`, `symblic/mica/fixtures.py:strict_json`, `symblic/mica/bench.py:MicaBenchmark`.

**Tests:** `tests/mica/test_symblic_mica_bench.py`.

**Not adopted / limits:** Hypothesis itself and its shrinker are not installed or used. These fixed development generators are not a general automatically derived property suite.

**Inspected source:** `hypothesis/src/hypothesis/core.py`, `hypothesis/src/hypothesis/internal/conjecture/engine.py`, `hypothesis/src/hypothesis/internal/conjecture/shrinker.py`.

**Primary papers:** [author paper](https://hypothesis.readthedocs.io/en/latest/).

## dafny-lang/dafny

Source: [dafny-lang/dafny](https://github.com/dafny-lang/dafny/tree/5f717bf447b19d38cad1b69b1bf9a9f102feccfb) · commit `5f717bf447b19d38cad1b69b1bf9a9f102feccfb`. Observed licensing: notices/inspect (NOTICES.txt); MIT (LICENSE.txt). 

**Adoption status:** `not_adopted_runtime`. Research informed explicit pre/postconditions and the distinction between encoded obligations and emitted-program proof.

**Implementation:** `symblic/mica/contracts.py:validate_plan`, `symblic/mica/search.py:MicaRun._build`.

**Tests:** `tests/mica/test_symblic_mica_contracts.py:test_proven_never_comes_from_coverage_or_failed_refinement`.

**Not adopted / limits:** No Dafny compiler, translation or verifier is integrated. Arbitrary JavaScript PROVEN requirements block rather than receive a false proof label.

**Inspected source:** `docs/DafnyRef/Specifications.md`, `Source/DafnyCore/Verifier`, `LICENSE.txt`, `NOTICES.txt`.

**Primary papers:** [author paper](https://dafny-lang.github.io/dafny/DafnyRef/DafnyRef).

## microsoft/codet

Source: [microsoft/codet](https://github.com/microsoft/codet/tree/35f54d60b152cc31d134b788e702878ad613d9f7) · commit `35f54d60b152cc31d134b788e702878ad613d9f7`. Observed licensing: MIT (CodeT/LICENSE). 

**Adoption status:** `implemented_method_subset`. Candidate generation and executable checking are separate; independent hidden acceptance is withheld from candidate selection/repair.

**Implementation:** `symblic/mica/search.py:MicaRun._unit_checks`, `symblic/mica/search.py:MicaRun._build`, `symblic/mica/bench.py:MicaBenchmark`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_root_acceptance_rejects_candidate_that_passes_its_own_examples`, `tests/mica/test_symblic_mica_bench.py`.

**Not adopted / limits:** No dual-agreement clustering or generated-test consensus score. Agreement among models/tests is not independent correctness evidence.

**Inspected source:** `CodeT/src/agreement.py:122:DualAgreement`, `CodeT/src/execution.py`, `CodeT/LICENSE`.

**Primary papers:** [author paper](https://arxiv.org/abs/2207.10397).

## huangd1999/AgentCoder

Source: [huangd1999/AgentCoder](https://github.com/huangd1999/AgentCoder/tree/d8538d63675c2b805855e6deb7ddc39fefb5723d) · commit `d8538d63675c2b805855e6deb7ddc39fefb5723d`. Observed licensing: No local license file found. No local license grant found; source not copied. README claims MIT; no local LICENSE found.

**Adoption status:** `implemented_method_subset`. A public test proposal precedes construction; the code checker, not a model evaluator, controls adoption and bounded feedback.

**Implementation:** `symblic/mica/project.py:root_prompt`, `symblic/mica/native.py:unit_source`, `symblic/mica/bench.py:MicaBenchmark`.

**Tests:** `tests/mica/test_symblic_mica_project.py:test_objective_build_preserves_authority_provenance_and_exact_calls`, `tests/mica/test_symblic_mica_execution.py:test_native_repair_receives_public_counterexample_then_passes`.

**Not adopted / limits:** No copied agent scripts, paid API dependency or independent-model test-designer guarantee. Root and unit tests can still be proposed by the same model; provenance remains explicit.

**Inspected source:** `src/programmer_humaneval.py`, `src/test_designer_humaneval.py`, `src/test_executor_humaneval.py`.

**Primary papers:** [author paper](https://arxiv.org/abs/2312.13010).

## ggml-org/llama.cpp

Source: [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/tree/23b0202a189c44a54625aadcb37a946dd1d6278d) · commit `23b0202a189c44a54625aadcb37a946dd1d6278d`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `not_adopted_new_runtime_or_grammar`. Official grammar limitations informed fail-closed host validation of JSON and source envelopes.

**Implementation:** `symblic/mica/native.py:planner_source`, `symblic/mica/contracts.py:normalize_request`.

**Tests:** `tests/mica/test_symblic_mica_execution.py:test_bad_planner_graph_uses_next_bounded_alternative`.

**Not adopted / limits:** No cloned runtime build or GBNF/schema injection is integrated in MICA. The existing Ollama backend may use its own inference implementation; that does not demonstrate grammar-constrained MICA decoding.

**Inspected source:** `grammars/README.md`, `common/json-schema-to-grammar.cpp`, `tests/test-json-schema-to-grammar.cpp`, `tests/test-gbnf-validator.cpp`.

**Primary papers:** [author paper](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md).

## dottxt-ai/outlines

Source: [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines/tree/c52af8472c6fe8a607a733ec11b709476af77a96) · commit `c52af8472c6fe8a607a733ec11b709476af77a96`. Observed licensing: Apache-2.0 (LICENSE). 

**Adoption status:** `not_adopted_runtime`. Structured output is validated against finite host contracts, with explicit rejection/repair.

**Implementation:** `symblic/mica/contracts.py`, `symblic/mica/project.py:_proposal`.

**Tests:** `tests/mica/test_symblic_mica_project.py:test_invalid_root_is_repaired_with_public_validation_failure`.

**Not adopted / limits:** No Outlines sampler/model runtime or regex/grammar decoder is integrated. Schema conformance and semantic correctness remain separate.

**Inspected source:** `src/outlines/types`, `src/outlines/models`, `docs/examples/structured_generation_workflow.md`.

**Primary papers:** [author paper](https://dottxt-ai.github.io/outlines/).

## google-deepmind/funsearch

Source: [google-deepmind/funsearch](https://github.com/google-deepmind/funsearch/tree/cc53f274237d7ab05c19df939edbc1f9616a7c19) · commit `cc53f274237d7ab05c19df939edbc1f9616a7c19`. Observed licensing: Apache-2.0 (LICENSE). Implementation Apache-2.0; paper/supporting materials have separate CC-BY terms.

**Adoption status:** `implemented_method_subset`. Keep bounded executable candidates and require an actual evaluator before adoption/reuse.

**Implementation:** `symblic/mica/library.py:ComponentLibrary`, `symblic/mica/search.py:MicaRun._prepare_unit`, `symblic/mica/search.py:MicaRun._build`.

**Tests:** `tests/mica/test_symblic_mica_library.py:test_eight_variants_bound_growth_without_evicting_existing_bytes`, `tests/mica/test_symblic_mica_library.py:test_invalid_cached_code_blocks_without_route_and_is_never_adopted`.

**Not adopted / limits:** No evolutionary islands, novelty scoring or deployment infrastructure is imported. Reference code omits important model/sandbox infrastructure; its installation would not constitute a working integration.

**Inspected source:** `implementation/programs_database.py:75:ProgramsDatabase`, `implementation/evaluator.py:115:Evaluator`, `implementation/sampler.py:40:Sampler`.

**Primary papers:** [author paper](https://www.nature.com/articles/s41586-023-06924-6).

## lm-sys/routellm

Source: [lm-sys/routellm](https://github.com/lm-sys/routellm/tree/0b64fdafe049e596a3f5657c219329f24af24198) · commit `0b64fdafe049e596a3f5657c219329f24af24198`. Observed licensing: Apache-2.0 (LICENSE). 

**Adoption status:** `independently_implemented_routing_method`. Empirical exact-identity/task-class routing with uncertainty and a shared observed/estimated cost dimension; frozen weights.

**Implementation:** `symblic/mica/routing.py:rank_models`, `symblic/mica/routing.py:summarize`, `symblic/mica/search.py:MicaRun._observe`.

**Tests:** `tests/mica/test_symblic_mica_routing.py:test_digest_node_and_class_drift_do_not_borrow_success`, `tests/mica/test_symblic_mica_routing.py:test_wilson_reduces_small_sample_overconfidence`, `tests/mica/test_symblic_mica_routing.py:test_expected_total_cost_can_favor_a_faster_less_reliable_model`.

**Not adopted / limits:** No pretrained RouteLLM router, paid embeddings or threshold-calibration dataset is imported. Current observations need genuine task-family coverage before capability claims.

**Inspected source:** `routellm/controller.py`, `routellm/calibrate_threshold.py:50`, `routellm/routers/routers.py`.

**Primary papers:** [author paper](https://arxiv.org/abs/2406.18665).

## EnvCommons/NL2RepoBench

Source: [EnvCommons/NL2RepoBench](https://github.com/EnvCommons/NL2RepoBench/tree/61d26cc0abd084ece8f5d805dcbd3f806a291f15) · commit `61d26cc0abd084ece8f5d805dcbd3f806a291f15`. Observed licensing: No local license file found. No local license grant found; source not copied. README refers to upstream Apache terms, not a local license grant.

**Adoption status:** `evaluation_methodology_subset`. Frozen public tasks, isolated hidden whole-program grading, all-assignment denominators and retained run artifacts.

**Implementation:** `symblic/mica/bench.py:MicaBenchmark`, `symblic/mica/fixtures.py`, `symblic/mica/cli.py:dispatch`.

**Tests:** `tests/mica/test_symblic_mica_bench.py`, `tests/mica/test_symblic_mica_cli.py`.

**Not adopted / limits:** Current fixtures grade pure JS programs, not full repository tasks. Reference-workspace overlay and last-command-only grading were explicitly not adopted; no dataset or harness import.

**Inspected source:** `nl2repobench.py:46:TaskSpec`, `nl2repobench.py:200:submit`, `prepare_data.py`, `tests.py`.

**Primary papers:** [author paper](https://github.com/multimodal-art-projection/NL2RepoBench).

## SWE-bench/SWE-bench

Source: [SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench/tree/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e) · commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`. Observed licensing: MIT (LICENSE). 

**Adoption status:** `evaluation_methodology_subset`. Separate task specification, isolated evaluation, exact artifact identity, reproducible assignments and failure-inclusive reports.

**Implementation:** `symblic/mica/bench.py:MicaBenchmark`, `symblic/mica/cli.py:dispatch`.

**Tests:** `tests/mica/test_symblic_mica_bench.py`.

**Not adopted / limits:** No SWE-bench dataset or container harness is installed, and no SWE-bench score is claimed. Repository repair/integration remains a future artifact lane.

**Inspected source:** `swebench/harness/run_evaluation.py`, `swebench/harness/grading.py`, `swebench/harness/reporting.py`.

**Primary papers:** [author paper](https://arxiv.org/abs/2310.06770), [author paper](https://www.swebench.com/SWE-bench/).

