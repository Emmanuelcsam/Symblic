# symblic.mica — checked construction of small JavaScript programs

**MICA** (Minimum-Intelligence Contract Assembly) tries to get *small local models* to build correct programs by
never trusting them with much at once. A model proposes a decomposition of the task into small function
contracts; code validates that graph; each unit is written by one model call (or built with no model at all) and
checked against its examples; the units are assembled and the original acceptance tests run; failures lead to
bounded repair or another decomposition. Everything is journaled so that a run can be resumed or audited, and an
unknown model call is never silently repeated.

## Status — read this first

* **Measured machinery:** the construction search (`search.py`), its contracts, journals, routing, checks,
  module bundles, check packs and the six-mode benchmark are implemented and tested with fake model applicators
  and the real sandboxed JavaScript checker (`tests/mica`).
* **Not established:** that MICA works with real small models. In the original system, four objective-only
  attempts with local models (two tasks, each tried twice) ended without an artifact: the first two produced no
  valid plan; of the second two, one admitted a six-function plan and checked two of its units before its
  1,800-second budget ran out. Their hidden tests were therefore never evaluated. No performance gain from
  decomposition, optimal search, or general correctness has been shown. `docs/reference/MICA.md` records these
  runs and the remaining acceptance work.
* The six experimental modes (`direct`, `static`, `decompose_on_failure`, `capability`, `search`, `mica`) exist so
  that the factors can be compared; that comparison has not been run.

Like the rest of Symblic, this code was written by AI coding agents.

## What is in this package

| File | Role |
|---|---|
| `cli.py` | Command line: `python3 -m symblic.mica.cli --help`. Every command prints one JSON document. |
| `search.py` | `MicaRun`: the bounded construction search for an explicit request (the core). |
| `project.py` | `MicaProject`: from a plain objective to a checked request (model-proposed requirements), then `MicaRun`. |
| `proposal.py` | Strict, versioned decoding of a model's root proposal. |
| `contracts.py` | Request and contract shapes, plan (DAG) validation, hashes, finite refinement checks. |
| `native.py` | Lowers a unit contract to a native Symblic program and runs it with the durable call journal. |
| `routing.py` | Inventory normalization and model ranking from past outcomes (Wilson lower bounds). |
| `strategy.py` | Bounded AND/OR frontier of alternative graphs and worker assignments. |
| `refinement.py` | Replaces one failed unit by a checked sub-graph of helpers. |
| `deterministic.py` | Zero-model-call construction of an explicit integer-affine function family. |
| `library.py` | Private component library: reuse of units that passed, always rechecked. |
| `promote.py` | Publishes a finished run's units into the library after its frozen check pack passes. |
| `bundle.py`, `bundle_runner.js` | ES-module bundles and their sandboxed checks in Node.js; deterministic ZIP export. |
| `costs.py` | Wall-clock and thread-CPU spans of the host's own work. |
| `calibration.py` | Freezes routing evidence from finished runs for later runs. |
| `checkpack.py`, `checkpack_cli.py`, `checkpack_link.py`, `domains.py` | Frozen, requirement-linked finite test data (public and evaluator-only rows). |
| `bench.py`, `fixtures.py` | The frozen six-mode benchmark and its seeded demo fixtures. |
| `forge.py`, `forge_cli.py` | Runs an accepted Forge handoff (symblic/forge) through `MicaRun`. |
| `source_identity.py` | Pins of the exact source files a result depends on, checked against the loaded code. |

## How the pieces fit

```
objective + budget ──► project.MicaProject ──► model proposes requirements and tests (proposal.py)
                                                        │
explicit request ──────────────────────────────────────►│
                                                        ▼
                        search.MicaRun: plan (model) ─► contracts.validate_plan ─► strategy (alternatives)
                                                        │
                    for each ready unit: library reuse │ deterministic constructor │ native ask (native.py)
                                                        ▼
                          unit checks (symblic.js) ─► assembly ─► original acceptance tests
                                                        │            (bundle.py for ES modules)
                                     failure ─► refinement / another alternative, within the budget
                                                        ▼
                                  artifact + evidence (mica-result.json, journals, costs)
```

Models are reached through `symblic.providers.applicators` as `ollama:MODEL@NODE`, where NODE is a host label in
`SYMBLIC_OLLAMA_HOSTS`. MICA only asks the models listed in an explicit inventory file.

## Run it

```sh
export SYMBLIC_OLLAMA_HOSTS="local=127.0.0.1:11434"      # name your Ollama host(s)
python3 -m symblic.mica.cli inventory > inventory.json   # reads /api/tags only; no model call
python3 -m symblic.mica.cli capabilities --inventory inventory.json
python3 -m symblic.mica.cli validate request.json
python3 -m symblic.mica.cli plan request.json --inventory inventory.json --dir runs/one --mode mica
python3 -m symblic.mica.cli execute request.json --inventory inventory.json --dir runs/one --mode mica
python3 -m symblic.mica.cli status --dir runs/one
python3 -m symblic.mica.cli artifacts --dir runs/one --include-text
```

A request is JSON with `objective`, `requirements` (`id`, `text`, `acceptance`), `exports` (`name`, `signature`),
`tests` (`call`, `expected`, `requirement_ids`), `allowed_outputs` and an optional `budget`; see
`contracts.normalize_request` and `docs/reference/MICA.md`. `SYMBLIC_MICA_EXCLUDED_NODES` lists nodes that must
never run construction calls.

## Tests

```sh
cd <repository root>
DASH_TEST=1 python3 -m unittest discover -s tests/mica -t .
```

No test calls a model. The tests run the real JavaScript checker, so they need Node.js 22 and the Linux sandbox
helpers the checker uses; expect 10 to 20 minutes for the whole package. Two tests are marked as expected
failures: they also fail on the original code this package was copied from (see the comments in
`tests/mica/test_symblic_mica_strategies.py`). Tests of the original host's HTTP API for MICA live in
`tests/integration/` and are skipped when that API cannot be imported.

## Only in the original host

The owner-only HTTP API and browser panel that drove MICA jobs (`integration/host/symblic_mica_api.py`) belonged
to the original home-server system. Its inventory came from that system's cluster status; here the `inventory`
command reads the configured Ollama hosts instead. Construction calls were placed on the cluster's compute
machines through its admission service; here they go straight to the configured Ollama hosts.

## Prior work

MICA reimplements method subsets from the projects below; no upstream code was copied and none of their runtimes
is a dependency. The exact inspected commits, files, licenses and what was and was not adopted are recorded in
`docs/reference/MICA-SOURCES.md` (machine-readable: `docs/reference/MICA-SOURCES.json`).

| Project | Paper or documentation | Used for |
|---|---|---|
| [ezelikman/parsel](https://github.com/ezelikman/parsel) | [Parsel (arXiv 2212.10561)](https://arxiv.org/abs/2212.10561) | hierarchical function contracts with explicit dependencies |
| [IPRC-DIP/ANPL](https://github.com/IPRC-DIP/ANPL) | [ANPL (arXiv 2305.18498)](https://arxiv.org/abs/2305.18498) | natural-language units lowered to fixed asks with dependency artifacts |
| [ZhangHanDong/agent-spec](https://github.com/ZhangHanDong/agent-spec) | — | requirement IDs, coverage and proposal provenance |
| [archiki/ADaPT](https://github.com/archiki/ADaPT) | [ADaPT (arXiv 2311.05772)](https://arxiv.org/abs/2311.05772) | the `decompose_on_failure` mode |
| [FoundationAgents/ReCode](https://github.com/FoundationAgents/ReCode) | [ReCode (arXiv 2510.23564)](https://arxiv.org/abs/2510.23564) | scoped expansion of unresolved units (refinement.py) |
| [github/spec-kit](https://github.com/github/spec-kit) | — | objective / requirements / plan / execution separation |
| [FoundationAgents/AFlow](https://github.com/FoundationAgents/AFlow) | [AFlow (arXiv 2410.10762)](https://arxiv.org/abs/2410.10762) | keeping checked work while revising alternative workflows |
| [SqueezeAILab/LLMCompiler](https://github.com/SqueezeAILab/LLMCompiler) | [LLMCompiler (arXiv 2312.04511)](https://arxiv.org/abs/2312.04511) | dependency-ready layer scheduling with bounded parallelism |
| [alexzhang13/rlm](https://github.com/alexzhang13/rlm) | [RLM (arXiv 2512.24601)](https://arxiv.org/abs/2512.24601) | externally retained scoped state and bounded sub-calls |
| [princeton-nlp/tree-of-thought-llm](https://github.com/princeton-nlp/tree-of-thought-llm) | [Tree of Thoughts (arXiv 2305.10601)](https://arxiv.org/abs/2305.10601) | retained alternative branches decided by host checks |
| [Z3Prover/z3](https://github.com/Z3Prover/z3) | [Z3 guide](https://microsoft.github.io/z3guide/) | informed the finite predicate implication checks (not a dependency) |
| [pschanely/crosshair](https://github.com/pschanely/crosshair) | [CrossHair limitations](https://crosshair.readthedocs.io/en/latest/limitations.html) | counterexample versus unknown distinctions (not adopted as a runtime) |
| [HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis) | [Hypothesis docs](https://hypothesis.readthedocs.io/en/latest/) | seeded structured inputs with an independent oracle (fixtures.py) |
| [dafny-lang/dafny](https://github.com/dafny-lang/dafny) | [Dafny reference](https://dafny-lang.github.io/dafny/DafnyRef/DafnyRef) | explicit pre/postconditions versus emitted-program claims (not adopted as a runtime) |
| [microsoft/codet](https://github.com/microsoft/codet) | [CodeT (arXiv 2207.10397)](https://arxiv.org/abs/2207.10397) | separating candidate generation from executable checking |
| [huangd1999/AgentCoder](https://github.com/huangd1999/AgentCoder) | [AgentCoder (arXiv 2312.13010)](https://arxiv.org/abs/2312.13010) | public tests proposed before construction; the checker decides |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | [grammars README](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md) | limits of grammar-constrained output (fail-closed JSON validation) |
| [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) | [Outlines docs](https://dottxt-ai.github.io/outlines/) | structured output validated against host contracts |
| [google-deepmind/funsearch](https://github.com/google-deepmind/funsearch) | [FunSearch (Nature, 2023)](https://www.nature.com/articles/s41586-023-06924-6) | executable candidates adopted only after an evaluator runs them |
| [lm-sys/routellm](https://github.com/lm-sys/routellm) | [RouteLLM (arXiv 2406.18665)](https://arxiv.org/abs/2406.18665) | empirical routing with uncertainty and a shared cost dimension |
| [EnvCommons/NL2RepoBench](https://github.com/EnvCommons/NL2RepoBench) | [NL2RepoBench](https://github.com/multimodal-art-projection/NL2RepoBench) | frozen public tasks with isolated hidden grading (bench.py) |
| [SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench) | [SWE-bench (arXiv 2310.06770)](https://arxiv.org/abs/2310.06770) | separate task specification and isolated evaluation |

Statistics used for ranking: the Wilson score interval (E. B. Wilson, "Probable inference, the law of succession,
and statistical inference", *Journal of the American Statistical Association* 22, 1927).
