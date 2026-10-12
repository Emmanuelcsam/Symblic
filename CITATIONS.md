# Citations

The software Symblic runs on, the agents that wrote it, the papers and repositories whose methods it adapts, and the
research its design notes cite. Most of these sources were found and summarized by AI agents while Symblic was
built ([docs/MADE-WITH-AI.md](docs/MADE-WITH-AI.md)); "Used for" says what Symblic took, as recorded in the design
document named in each section.

**How the links were checked.** On 2026-10-11 every link below was opened by a script: arXiv entries through the
arXiv API, DOIs through Crossref, GitHub repositories (and pinned commits) through the GitHub API, other pages by
fetching them. For papers, the title or authors returned were compared with the citation, and the title shown here
is the one the source returned. A few pages block automated access; they were checked another way, as noted.
Links that could not be confirmed are not used below; they are listed in [the last section](#links-that-could-not-be-verified).
A working link and a matching title say that the source exists, not that the design documents describe it correctly.

## 1. Software Symblic runs on or ships

- **Python 3.12**: [python.org](https://www.python.org/). The interpreter and all tools. The language kernel uses only the standard library.
- **Acorn 8.8.1 (MIT license)**: [github.com/acornjs/acorn](https://github.com/acornjs/acorn). Bundled as `symblic/js/acorn.js` to parse model-written JavaScript before it runs; license in `symblic/js/acorn-LICENSE.txt` (tag `8.8.1` confirmed in the repository).
- **Node.js 22**: [nodejs.org](https://nodejs.org/). Runs model-written JavaScript against a program's examples (`symblic/js`).
- **Linux Landlock**: [docs.kernel.org](https://docs.kernel.org/userspace-api/landlock.html). Filesystem, network and scope rules of the sandbox for untrusted programs (`symblic/sandbox/landlock.py`).
- **Linux seccomp**: [docs.kernel.org](https://docs.kernel.org/userspace-api/seccomp_filter.html). Filters that close the ways around Landlock's network rules and block Unix sockets in the same sandbox.
- **Ollama**: [github.com/ollama/ollama](https://github.com/ollama/ollama), [ollama.com](https://ollama.com/blog/structured-outputs). The local model server behind the `ollama:` applicator; an answer's JSON Schema is sent as Ollama's `format` (structured outputs).
- **llama.cpp**: [github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp). The inference engine under Ollama; its grammar documentation informed the fail-closed checks on JSON answers (MICA sources below).
- **Z3 (`z3-solver` 4.15.4.0), optional**: [github.com/Z3Prover/z3](https://github.com/Z3Prover/z3). Constructs answers for asks whose checks are linear arithmetic (`symblic/linear`), in a separate pinned worker.
- **PyTorch, Transformers, PEFT, safetensors and tokenizers, optional**: [github.com/pytorch/pytorch](https://github.com/pytorch/pytorch), [github.com/huggingface/transformers](https://github.com/huggingface/transformers), [github.com/huggingface/peft](https://github.com/huggingface/peft), [github.com/safetensors/safetensors](https://github.com/safetensors/safetensors), [github.com/huggingface/tokenizers](https://github.com/huggingface/tokenizers). The LoRA fine-tuning worker in `symblic/distill` (versions pinned there).
- **markdown-it-py 3.0.0, optional**: [github.com/executablebooks/markdown-it-py](https://github.com/executablebooks/markdown-it-py). Parses the documents for the documentation audit (`tools/scripts/symblic_docs_audit.py`).
- **grep-ast, optional**: [github.com/Aider-AI/grep-ast](https://github.com/Aider-AI/grep-ast). Source context for agent task packs (`symblic/kernel/context_packs.py`).

## 2. Models used in the measurements

Small open models, run locally through Ollama ([docs/HONEST-ASSESSMENT.md](docs/HONEST-ASSESSMENT.md)). Links go to
the Ollama library pages, which link the model cards and licenses.

- Qwen3 4B Instruct (`qwen3:4b-instruct`): [ollama.com](https://ollama.com/library/qwen3)
- Qwen2.5-Coder 3B (`qwen2.5-coder:3b`): [ollama.com](https://ollama.com/library/qwen2.5-coder)
- Qwen2.5 0.5B (`qwen2.5:0.5b`): [ollama.com](https://ollama.com/library/qwen2.5)
- Gemma 3 1B and 4B (`gemma3:1b`, `gemma3:4b`): [ollama.com](https://ollama.com/library/gemma3)
- Llama 3.2 1B (`llama3.2:1b`): [ollama.com](https://ollama.com/library/llama3.2)
- Granite 3.3 2B (`granite3.3:2b`): [ollama.com](https://ollama.com/library/granite3.3)
- Phi-4-mini (`phi4-mini`): [ollama.com](https://ollama.com/library/phi4-mini)

Earlier measurements also used hosted models (Claude Haiku, Sonnet and Opus; OpenAI Codex; Gemini through
Antigravity) as applicators; see [docs/reference/RESULTS.md](docs/reference/RESULTS.md).

## 3. The AI agents that wrote Symblic

- **Claude Code (Anthropic)**: [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code). Role: the main coding agent; Claude was also used in the browser and in cloud tasks for reviews ([product page](https://www.anthropic.com/claude)).
- **OpenAI Codex CLI**: [github.com/openai/codex](https://github.com/openai/codex). Role: a second coding agent: MICA releases, audits, a matched pilot.
- **Gemini CLI (Google)**: [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli). Role: Gemini models from the command line.
- **Google Antigravity**: [antigravity.google](https://antigravity.google/). Role: the `agy` agent that generated the essays and the first versions of the proposal documents.
- **Mistral Vibe CLI**: [github.com/mistralai/mistral-vibe](https://github.com/mistralai/mistral-vibe). Role: coordinated one beta trial.
- **ChatGPT (OpenAI)**. Role: design reviews, used through its web interface (chatgpt.com, which blocks automated checks).

Their roles are described in [docs/MADE-WITH-AI.md](docs/MADE-WITH-AI.md).

## 4. Methods Symblic adapts

### 4.1 Recursive decomposition in autogen

The person directing the work named these eight papers and asked for them to become mechanisms, not prose. The
mapping is from [docs/reference/RECURSION.md](docs/reference/RECURSION.md) §2, which also states the limits of each
implementation. No mechanism has been measured against the paper's own results.

- **Parsel: Algorithmic Reasoning with Language Models by Composing Decompositions** (Zelikman et al., 2022). [arXiv:2212.10561](https://arxiv.org/abs/2212.10561). Used for: Hierarchical split of a statement into children with explicit per-line interfaces (`split_prompt`, `parse_split`), together with ANPL.
- **ANPL: Towards Natural Programming with Interactive Decomposition** (Huang et al., 2023). [arXiv:2305.18498](https://arxiv.org/abs/2305.18498). Used for: Same mechanism as Parsel: natural-language units with explicit interfaces, decomposed when a unit is too big.
- **CodePlan: Repository-level Coding using LLMs and Planning** (Bairi et al., 2023). [arXiv:2309.12499](https://arxiv.org/abs/2309.12499). Used for: Dependency-aware ordering: the children of a split run in the planner's order before later statements, and a parent is judged after its children.
- **CodeT: Code Generation with Generated Tests** (Chen et al., 2022). [arXiv:2207.10397](https://arxiv.org/abs/2207.10397). Used for: Generated tests select candidates: an independent designer writes `AUTOGEN-TESTS.sh` first, admitted only if it fails on an empty folder.
- **AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation** (Huang et al., 2023). [arXiv:2312.13010](https://arxiv.org/abs/2312.13010). Used for: Same mechanism as CodeT: a test designer separate from the code writer; code, not a model, decides adoption.
- **AFlow: Automating Agentic Workflow Generation** (Zhang et al., 2024). [arXiv:2410.10762](https://arxiv.org/abs/2410.10762). Used for: Strategy rotation chosen by evidence: the last failure class orders the next strategy, and a repeated search state is refused.
- **Agent Contracts: A Formal Framework for Resource-Bounded Autonomous AI Systems** (Ye and Tan, 2026). [arXiv:2601.08815](https://arxiv.org/abs/2601.08815). Used for: Checks per statement and per subtree, budgets per run (`plan_checks`, `normalize`).
- **Recursive Models for Long-Horizon Reasoning** (Yang et al., 2026). [arXiv:2603.02112](https://arxiv.org/abs/2603.02112). Used for: Fresh contexts with external checkpoints: a worker near its context limit hands off through `HANDOFF.md` and a validated checkpoint.

The last entry is the paper the request named ("Recursive Models for Long-Horizon Reasoning"). The related
**Recursive Language Models** paper (Zhang, Kraska and Khattab, [arXiv:2512.24601](https://arxiv.org/abs/2512.24601))
is the source of the externally retained state adapted in MICA (next section) and is compared in the prior-art survey.

### 4.2 Repositories studied for MICA

MICA ([docs/reference/MICA.md](docs/reference/MICA.md)) assembles small checked JavaScript programs. Its design was
mapped against these repositories at the pinned commits in
[docs/reference/MICA-SOURCES.md](docs/reference/MICA-SOURCES.md). No source code was copied from any of them and
none is a runtime dependency; "Used for" is the method adopted, quoted from that record.

- **ezelikman/parsel** at `bc1687cab9e8`: [github.com/ezelikman/parsel](https://github.com/ezelikman/parsel/tree/bc1687cab9e8a79249f0d3e3cb4f5826dba39a95); paper or documentation: [arXiv:2212.10561](https://arxiv.org/html/2212.10561v3). Status: implemented method subset. Used for: Hierarchical function contracts, explicit dependencies and retained checked components across bounded alternatives.
- **IPRC-DIP/ANPL** at `bfc28987f11a`: [github.com/IPRC-DIP/ANPL](https://github.com/IPRC-DIP/ANPL/tree/bfc28987f11aee5290ad51ecac8248664d653640); paper or documentation: [arXiv:2305.18498](https://arxiv.org/abs/2305.18498). Status: implemented method subset. Used for: Natural-language implementation units lower into fixed native asks with explicit dependency artifacts and checked invalidation.
- **ZhangHanDong/agent-spec** at `2483398da89b`: [github.com/ZhangHanDong/agent-spec](https://github.com/ZhangHanDong/agent-spec/tree/2483398da89bd392186849bb865aae969667ac0a). Status: implemented method subset. Used for: Requirement IDs, coverage, assumptions, validated graph and explicit proposal provenance connect root authority to evidence.
- **archiki/ADaPT** at `ecdc4ab0030b`: [github.com/archiki/ADaPT](https://github.com/archiki/ADaPT/tree/ecdc4ab0030b4be9be122622d8ea78f8c59c44c4); paper or documentation: [arXiv:2311.05772](https://arxiv.org/html/2311.05772v2). Status: implemented method subset. Used for: decompose_on_failure begins with a whole-program attempt, then permits bounded decompositions driven by host-verified failures.
- **FoundationAgents/ReCode** at `6e7223f71281`: [github.com/FoundationAgents/ReCode](https://github.com/FoundationAgents/ReCode/tree/6e7223f71281d914762e78d7bbcf6446d362ecbc); paper or documentation: [arXiv:2510.23564](https://arxiv.org/html/2510.23564v1). Status: implemented method subset. Used for: Explicit unresolved units expand into scoped children with retained failure/dependency context.
- **github/spec-kit** at `0443760542e7`: [github.com/github/spec-kit](https://github.com/github/spec-kit/tree/0443760542e7e5269724744a2ac55c4bd386d095). Status: methodology and documentation. Used for: Separate objective, explicit requirement proposal, plan, execution and retained evidence; machine-readable interfaces expose each stage.
- **FoundationAgents/AFlow** at `3f457218fc71`: [github.com/FoundationAgents/AFlow](https://github.com/FoundationAgents/AFlow/tree/3f457218fc716093fe53f6df8a5d5e6379d66346); paper or documentation: [arXiv:2410.10762](https://arxiv.org/html/2410.10762v3). Status: implemented method subset. Used for: Retain checked work while revising bounded alternative workflows using verified failures.
- **SqueezeAILab/LLMCompiler** at `a00c9d355075`: [github.com/SqueezeAILab/LLMCompiler](https://github.com/SqueezeAILab/LLMCompiler/tree/a00c9d35507507da70e8c637eee64efc8c1857ae); paper or documentation: [arXiv:2312.04511](https://arxiv.org/abs/2312.04511). Status: implemented method subset. Used for: Validated dependency-ready layer scheduling, bounded parallelism and serialized same-node model admission.
- **alexzhang13/rlm** at `d04208afbad2`: [github.com/alexzhang13/rlm](https://github.com/alexzhang13/rlm/tree/d04208afbad29ca675ab13478c40ee8bebc84bfe); paper or documentation: [arXiv:2512.24601](https://arxiv.org/abs/2512.24601). Status: implemented method subset. Used for: Externally retained scoped state, bounded subordinate model calls and cumulative accounting instead of an ever-growing shared prompt.
- **princeton-nlp/tree-of-thought-llm** at `8050e67d0e3a`: [github.com/princeton-nlp/tree-of-thought-llm](https://github.com/princeton-nlp/tree-of-thought-llm/tree/8050e67d0e3a0fddc424d7fa5801538722a4c4cc); paper or documentation: [arXiv:2305.10601](https://arxiv.org/abs/2305.10601). Status: implemented method subset. Used for: Retain alternative branches and let host checks decide whether search may proceed.
- **Z3Prover/z3** at `2d08bfcad30c`: [github.com/Z3Prover/z3](https://github.com/Z3Prover/z3/tree/2d08bfcad30cabb7b2819dd2f4c47b7bbf4c377f); paper or documentation: [microsoft.github.io](https://microsoft.github.io/z3guide/). Status: existing native capability not new dependency. Used for: Use the existing native verifier/constructor boundary; MICA adds exact finite predicate implication and a finite coefficient family with explicit unknown/unsupported outcomes.
- **pschanely/crosshair** at `35e504cc5b09`: [github.com/pschanely/crosshair](https://github.com/pschanely/crosshair/tree/35e504cc5b09846242e9ac67d10219b67d587a65); paper or documentation: [crosshair.readthedocs.io](https://crosshair.readthedocs.io/en/latest/limitations.html). Status: not adopted runtime. Used for: Research informed counterexample/unknown distinctions; existing finite checks remain independently implemented.
- **HypothesisWorks/hypothesis** at `1484f6dd4c0a`: [github.com/HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis/tree/1484f6dd4c0a220f68e2698afed29e2a16a3f654); paper or documentation: [hypothesis.readthedocs.io](https://hypothesis.readthedocs.io/en/latest/). Status: implemented method subset. Used for: Seeded valid/invalid structured input generation with an independent reference oracle, frozen outside construction context.
- **dafny-lang/dafny** at `5f717bf447b1`: [github.com/dafny-lang/dafny](https://github.com/dafny-lang/dafny/tree/5f717bf447b19d38cad1b69b1bf9a9f102feccfb); paper or documentation: [dafny-lang.github.io](https://dafny-lang.github.io/dafny/DafnyRef/DafnyRef). Status: not adopted runtime. Used for: Research informed explicit pre/postconditions and the distinction between encoded obligations and emitted-program proof.
- **microsoft/codet** at `35f54d60b152`: [github.com/microsoft/codet](https://github.com/microsoft/codet/tree/35f54d60b152cc31d134b788e702878ad613d9f7); paper or documentation: [arXiv:2207.10397](https://arxiv.org/abs/2207.10397). Status: implemented method subset. Used for: Candidate generation and executable checking are separate; independent hidden acceptance is withheld from candidate selection/repair.
- **huangd1999/AgentCoder** at `d8538d63675c`: [github.com/huangd1999/AgentCoder](https://github.com/huangd1999/AgentCoder/tree/d8538d63675c2b805855e6deb7ddc39fefb5723d); paper or documentation: [arXiv:2312.13010](https://arxiv.org/abs/2312.13010). Status: implemented method subset. Used for: A public test proposal precedes construction; the code checker, not a model evaluator, controls adoption and bounded feedback.
- **ggml-org/llama.cpp** at `23b0202a189c`: [github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/tree/23b0202a189c44a54625aadcb37a946dd1d6278d); paper or documentation: [github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md). Status: not adopted new runtime or grammar. Used for: Official grammar limitations informed fail-closed host validation of JSON and source envelopes.
- **dottxt-ai/outlines** at `c52af8472c6f`: [github.com/dottxt-ai/outlines](https://github.com/dottxt-ai/outlines/tree/c52af8472c6fe8a607a733ec11b709476af77a96); paper or documentation: [dottxt-ai.github.io](https://dottxt-ai.github.io/outlines/). Status: not adopted runtime. Used for: Structured output is validated against finite host contracts, with explicit rejection/repair.
- **google-deepmind/funsearch** at `cc53f274237d`: [github.com/google-deepmind/funsearch](https://github.com/google-deepmind/funsearch/tree/cc53f274237d7ab05c19df939edbc1f9616a7c19); paper or documentation: [nature.com](https://www.nature.com/articles/s41586-023-06924-6). Status: implemented method subset. Used for: Keep bounded executable candidates and require an actual evaluator before adoption/reuse.
- **lm-sys/routellm** at `0b64fdafe049`: [github.com/lm-sys/routellm](https://github.com/lm-sys/routellm/tree/0b64fdafe049e596a3f5657c219329f24af24198); paper or documentation: [arXiv:2406.18665](https://arxiv.org/abs/2406.18665). Status: independently implemented routing method. Used for: Empirical exact-identity/task-class routing with uncertainty and a shared observed/estimated cost dimension; frozen weights.
- **EnvCommons/NL2RepoBench** at `61d26cc0abd0`: [github.com/EnvCommons/NL2RepoBench](https://github.com/EnvCommons/NL2RepoBench/tree/61d26cc0abd084ece8f5d805dcbd3f806a291f15); paper or documentation: [github.com/multimodal-art-projection/NL2RepoBench](https://github.com/multimodal-art-projection/NL2RepoBench). Status: evaluation methodology subset. Used for: Frozen public tasks, isolated hidden whole-program grading, all-assignment denominators and retained run artifacts.
- **SWE-bench/SWE-bench** at `02e7a74ffd0b`: [github.com/SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench/tree/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e); paper or documentation: [arXiv:2310.06770](https://arxiv.org/abs/2310.06770), [swebench.com](https://www.swebench.com/SWE-bench/). Status: evaluation methodology subset. Used for: Separate task specification, isolated evaluation, exact artifact identity, reproducible assignments and failure-inclusive reports.

### 4.3 Research transferred into the fresh-context work cycle

From [docs/reference/RESEARCH-TRANSFER.md](docs/reference/RESEARCH-TRANSFER.md): "engineering transfers from the
cited studies, not claims that their measured gains already apply to Symblic."

- **Least-to-Most Prompting Enables Complex Reasoning in Large Language Models**. [arXiv:2205.10625](https://arxiv.org/abs/2205.10625). Used for: Preserve necessary answers explicitly when clearing chat history.
- **Decomposed Prompting: A Modular Approach for Solving Complex Tasks**. [arXiv:2210.02406](https://arxiv.org/abs/2210.02406). Used for: Compare typed constructors and generic checkers with this close baseline.
- **Lost in the Middle**. [aclanthology.org](https://aclanthology.org/2024.tacl-1.9/). Used for: Test dependency position and distractors, not only total context length.
- **LLMs Get Lost In Multi-Turn Conversation**. [arXiv:2505.06120](https://arxiv.org/abs/2505.06120). Used for: Rebuild consolidated authoritative state; measure against an equal-information history condition.
- **Atom of Thoughts for Markov LLM Test-Time Scaling**. [arXiv:2502.12018](https://arxiv.org/abs/2502.12018). Used for: Compare state reconstruction and error propagation, including its additional cost.
- **The Markovian Thinker: Architecture-Agnostic Linear Scaling of Reasoning**. [arXiv:2510.06557](https://arxiv.org/abs/2510.06557). Used for: Small local models are a relevant target; learned carryover is a distinct training experiment.
- **The $\mathbf{Y}$-Combinator for LLMs: Solving Long-Context Rot with $λ$-Calculus**. [arXiv:2603.20105](https://arxiv.org/abs/2603.20105). Used for: Add explicit composition, cost and termination contracts; compare with lambda-RLM.
- **Solving a Million-Step LLM Task with Zero Errors**. [arXiv:2511.09030](https://arxiv.org/abs/2511.09030). Used for: Evaluate long-run accepted-step error and shared failures on held-out task families.
- **Proof-Carrying Code**. [homes.cs.washington.edu](https://homes.cs.washington.edu/~mernst/teaching/6.893/readings/necula-popl97.pdf). Used for: Keep difficult construction/search outside the reusable checker.
- **Language Agents as Optimizable Graphs**. [arXiv:2402.16823](https://arxiv.org/abs/2402.16823). Used for: Optimize candidate nodes/edges under fixed author contracts, then freeze before held-out comparison.
- **TextGrad: Automatic "Differentiation" via Text**. [arXiv:2406.07496](https://arxiv.org/abs/2406.07496). Used for: Optimize candidate nodes/edges under fixed author contracts, then freeze before held-out comparison.
- **Reducing everyday memory and planning problems by means of a paging system: a randomised control crossover study**. [pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/11254770/). Used for: Human-memory research behind the durable work-card scheduler and kept rejected attempts (a hypothesis, not evidence)
- **When implicit learning fails: amnesia and the problem of error elimination**. [pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/8818154/). Used for: Human-memory research behind the durable work-card scheduler and kept rejected attempts (a hypothesis, not evidence)
- **Strategic use of reminders: Influence of both domain-general and task-specific metacognitive confidence, independent of objective memory ability**. [pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/25666463/). Used for: Human-memory research behind the durable work-card scheduler and kept rejected attempts (a hypothesis, not evidence)

### 4.4 The research adoption ledger

[docs/reference/RESEARCH-ADOPTION.md](docs/reference/RESEARCH-ADOPTION.md) turns ideas from the AI-written proposal
documents into concrete constructions or experiments, each with its limit. These are the sources it cites, with the
row that cites them.

- **Clark and Brennan**. [cs.cmu.edu](https://www.cs.cmu.edu/~illah/CLASSDOCS/Clark91.pdf). Used for: Common ground, Davidsonian triangulation, perspective-taking.
- **ACE guidance**. [attempto.ifi.uzh.ch](https://attempto.ifi.uzh.ch/site/docs/ace_troubleshooting.html). Used for: Common ground, Davidsonian triangulation, perspective-taking.
- **Eyal, Steffel and Epley**. [nicholasepley.com](https://nicholasepley.com/publications). Used for: Human observations, feelings, needs and requests.
- **Aumann**. [haverford.edu](https://www.haverford.edu/sites/default/files/Aumann1976.pdf). Used for: Aumann knowledge partitions and theory of mind.
- **Crawford and Sobel**. [econweb.ucsd.edu](https://econweb.ucsd.edu/~vcrawfor/CrawfordSobel82EMT.pdf). Used for: Cheap talk, incentive compatibility and non-degeneracy.
- **Mathematical Foundations for a Compositional Distributional Model of Meaning**. [arXiv:1003.4394](https://arxiv.org/abs/1003.4394). Used for: Pragmatics, modality, anaphora and compositional semantics.
- **Lean's kernel and trusted-code account**. [lean-lang.org](https://lean-lang.org/doc/reference/latest/Elaboration-and-Compilation/). Used for: Curry–Howard and proof-carrying results.
- **SMT-LIB**. [smt-lib.org](https://smt-lib.org/language.shtml). Used for: SMT, induction and decidability.
- **Quipper: A Scalable Quantum Programming Language**. [arXiv:1304.3390](https://arxiv.org/abs/1304.3390). Used for: Linear capabilities and no-cloning.
- **Garcia-Molina and Salem's original sagas paper**. [cs.cornell.edu](https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf). Used for: Sagas and external-effect recovery.
- **Fischer, Lynch and Paterson**. [groups.csail.mit.edu](https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf). Used for: GPU determinism and FLP.
- **HoTT book, §§2.3, 2.10**. [homotopytypetheory.org](https://homotopytypetheory.org/book/). Used for: HoTT, equivalence and automatic schema transport.
- **Toward a Spectral Theory of Cellular Sheaves**. [arXiv:1808.01513](https://arxiv.org/abs/1808.01513). Used for: Topoi, sheaves and perspectival consistency.
- **Cellular Sheaves of Lattices and the Tarski Laplacian**. [arXiv:2007.04099](https://arxiv.org/abs/2007.04099). Used for: Topoi, sheaves and perspectival consistency.
- **Wang and colleagues**. [jbusemey.pages.iu.edu](https://jbusemey.pages.iu.edu/quantum/PNAS2014.pdf). Used for: Quantum probability, density matrices and question order.
- **lambeq: An Efficient High-Level Python Library for Quantum NLP**. [arXiv:2110.04236](https://arxiv.org/abs/2110.04236). Used for: DisCoCat, tensor semantics and quantum NLP.
- **The ZX-calculus is complete for stabilizer quantum mechanics**. [arXiv:1307.7025](https://arxiv.org/abs/1307.7025). Used for: ZX-calculus and exact algebraic amplitudes.
- **The ZX-Calculus is Canonical in the Heisenberg Picture for Stabilizer Quantum Mechanics**. [arXiv:2301.05717](https://arxiv.org/abs/2301.05717). Used for: ZX-calculus and exact algebraic amplitudes.
- **Ising formulations of many NP problems**. [arXiv:1302.5843](https://arxiv.org/abs/1302.5843). Used for: Ising/QUBO, annealing, QAOA/VQE and ground states.
- **Adiabatic quantum optimization fails for random instances of NP-complete problems**. [arXiv:0908.2782](https://arxiv.org/abs/0908.2782). Used for: Quantum speedups.
- **Does Adiabatic Quantum Optimization Truly Fail for NP-complete problems?**. [arXiv:1010.0669](https://arxiv.org/abs/1010.0669). Used for: Quantum speedups.
- **Boyd and Vandenberghe**. [stanford.edu](https://www.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf). Used for: Variational principles and least-action ideas.
- **Turing complete Navier-Stokes steady states via cosymplectic geometry**. [arXiv:2507.07696](https://arxiv.org/abs/2507.07696). Used for: Navier–Stokes, Sobolev/BKM bounds and fluid computation.
- **Hairer, Lubich and Wanner**. [unige.ch](https://www.unige.ch/~hairer/preprints/gniverlet.html). Used for: Symplectic geometry and Noether invariants.
- **The information bottleneck method**. [arXiv:physics/0004057](https://arxiv.org/abs/physics/0004057). Used for: Wilsonian coarse-graining and context compression.
- **Natural Gradient Works Efficiently in Learning**. [doi:10.1162/089976698300017746](https://doi.org/10.1162/089976698300017746). Used for: Fisher geometry and natural gradients.
- **Gromov-Wasserstein Alignment of Word Embedding Spaces**. [arXiv:1809.00013](https://arxiv.org/abs/1809.00013). Used for: Wasserstein transport and barycenters.
- **Hodge Theory for Combinatorial Geometries**. [arXiv:1511.02888](https://arxiv.org/abs/1511.02888). Used for: Hodge theory and matroids.
- **The sphere packing problem in dimension 8**. [arXiv:1603.04246](https://arxiv.org/abs/1603.04246). Used for: E8/Leech packing and error-correcting representations.
- **The Large N Limit of Superconformal Field Theories and Supergravity**. [arXiv:hep-th/9711200](https://arxiv.org/abs/hep-th/9711200). Used for: AdS/CFT, holography and Ryu–Takayanagi.
- **Holographic Derivation of Entanglement Entropy from AdS/CFT**. [arXiv:hep-th/0603001](https://arxiv.org/abs/hep-th/0603001). Used for: AdS/CFT, holography and Ryu–Takayanagi.
- **Simple statistical gradient-following algorithms for connectionist reinforcement learning**. [doi:10.1007/BF00992696](https://doi.org/10.1007/BF00992696). Used for: RLVR/GRPO, distillation and curriculum.
- **PPDL**. [proceedings.mlr.press](https://proceedings.mlr.press/v306/mandel26a.html). Used for: Sequential Monte Carlo and probabilistic execution.
- **PAL**. [proceedings.mlr.press](https://proceedings.mlr.press/v202/gao23f.html). Used for: Novelty and universal epistemic architecture.
- **LINC: A Neurosymbolic Approach for Logical Reasoning by Combining Language Models with First-Order Logic Provers**. [arXiv:2310.15164](https://arxiv.org/abs/2310.15164). Used for: Novelty and universal epistemic architecture.
- **SPL: Orchestrating Workflows with Declarative Deterministic-Probabilistic Composition**. [arXiv:2607.07727](https://arxiv.org/abs/2607.07727). Used for: Novelty and universal epistemic architecture.
- **byLLM**. [jac-lang.org](https://www.jac-lang.org/reference/plugins/byllm/). Used for: Novelty and universal epistemic architecture.

## 5. Research behind the design rules

Evidence for the 23 engineering rules on getting different models to agree, from [docs/reference/RESEARCH-AGREEMENT.md](docs/reference/RESEARCH-AGREEMENT.md) §10 (grouped as there).


**Prompt sensitivity and order bias**

- [Sclar] Sclar, Choi, Tsvetkov, Suhr. Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design. ICLR 2024. [arXiv:2310.11324](https://arxiv.org/abs/2310.11324)
- [Voronov] Voronov, Wolf, Ryabinin. Mind Your Format. ACL Findings 2024. Verified title: "Mind Your Format: Towards Consistent Evaluation of In-Context Learning Improvements". [arXiv:2401.06766](https://arxiv.org/abs/2401.06766)
- [Mizrahi] Mizrahi et al. State of What Art? A Call for Multi-Prompt LLM Evaluation. TACL. [arXiv:2401.00595](https://arxiv.org/abs/2401.00595)
- [Errica] Errica et al. What Did I Do Wrong? Quantifying LLMs' Sensitivity and Consistency to Prompt Engineering. NAACL 2025. [arXiv:2406.12334](https://arxiv.org/abs/2406.12334)
- [PromptBench] Zhu et al. PromptRobust (PromptBench). Verified title: "PromptRobust: Towards Evaluating the Robustness of Large Language Models on Adversarial Prompts". [arXiv:2306.04528](https://arxiv.org/abs/2306.04528)
- [ParaRel] Elazar et al. Measuring and Improving Consistency in Pretrained Language Models. TACL 2021. [arXiv:2102.01017](https://arxiv.org/abs/2102.01017)
- [GVCons] Li, Shrivastava, Li, Hashimoto, Liang. Benchmarking and Improving Generator-Validator Consistency of LMs. [arXiv:2310.01846](https://arxiv.org/abs/2310.01846)
- [Moore] Moore, Deshpande, Yang. Are LLMs Consistent over Value-laden Questions? EMNLP Findings 2024. Verified title: "Are Large Language Models Consistent over Value-laden Questions?". [arXiv:2407.02996](https://arxiv.org/abs/2407.02996)
- [Raj] Raj, Rosati, Majumdar. Measuring Reliability of LLMs through Semantic Consistency. NeurIPS 2022 ML Safety Workshop. Verified title: "Measuring Reliability of Large Language Models through Semantic Consistency". [arXiv:2211.05853](https://arxiv.org/abs/2211.05853)
- [Pezeshkpour] Pezeshkpour & Hruschka. LLMs Sensitivity to the Order of Options in Multiple-Choice Questions. Verified title: "Large Language Models Sensitivity to The Order of Options in Multiple-Choice Questions". [arXiv:2308.11483](https://arxiv.org/abs/2308.11483)
- [PriDe] Zheng, Zhou, Meng, Zhou, Huang. Large Language Models Are Not Robust Multiple Choice Selectors. ICLR 2024. [arXiv:2309.03882](https://arxiv.org/abs/2309.03882), [arXiv:2309.03882](https://arxiv.org/html/2309.03882)
- [MTBench] Zheng et al. Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023 D&B. [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)
- [WangFair] Wang et al. Large Language Models are not Fair Evaluators. [arXiv:2305.17926](https://arxiv.org/abs/2305.17926)
- [Calibrate] Zhao, Wallace, Feng, Klein, Singh. Calibrate Before Use. ICML 2021. Verified title: "Calibrate Before Use: Improving Few-Shot Performance of Language Models". [arXiv:2102.09690](https://arxiv.org/abs/2102.09690)
- [FantOrder] Lu et al. Fantastically Ordered Prompts. ACL 2022. Verified title: "Fantastically Ordered Prompts and Where to Find Them: Overcoming Few-Shot Prompt Order Sensitivity". [arXiv:2104.08786](https://arxiv.org/abs/2104.08786)
- [FeiLabel] Fei, Hou, Chen, Bosselut. Mitigating Label Biases for In-context Learning. ACL 2023. [arXiv:2305.19148](https://arxiv.org/abs/2305.19148)
- [ReifLabel] Reif & Schwartz. Beyond Performance: Quantifying and Mitigating Label Bias in LLMs. NAACL 2024. [arXiv:2405.02743](https://arxiv.org/abs/2405.02743)
- [BatchCal] Zhou et al. Batch Calibration. ICLR 2024. Verified title: "Batch Calibration: Rethinking Calibration for In-Context Learning and Prompt Engineering". [arXiv:2309.17249](https://arxiv.org/abs/2309.17249)

**Ambiguity and clarification**

- [AmbiEnt] Liu et al. We're Afraid Language Models Aren't Modeling Ambiguity. EMNLP 2023. [arXiv:2304.14399](https://arxiv.org/abs/2304.14399)
- [AmbigQA] Min, Michael, Hajishirzi, Zettlemoyer. AmbigQA. EMNLP 2020. Verified title: "AmbigQA: Answering Ambiguous Open-domain Questions". [arXiv:2004.10645](https://arxiv.org/abs/2004.10645)
- [CLAMBER] Zhang et al. CLAMBER. ACL 2024. Verified title: "CLAMBER: A Benchmark of Identifying and Clarifying Ambiguous Information Needs in Large Language Models". [arXiv:2405.12063](https://arxiv.org/abs/2405.12063)
- [Tamkin] Tamkin, Handa, Shrestha, Goodman. Task Ambiguity in Humans and Language Models. [arXiv:2212.10711](https://arxiv.org/abs/2212.10711)
- [Underspec] Yang, Shi, Ma, Liu, Kästner, Wu. What Prompts Don't Say. ACL Findings 2026. Verified title: "What Prompts Don't Say: Understanding and Managing Underspecification in LLM Prompts". [arXiv:2505.13360](https://arxiv.org/abs/2505.13360)
- [Qulac] Aliannejadi, Zamani, Crestani, Croft. Asking Clarifying Questions in Open-Domain Information-Seeking Conversations. SIGIR 2019. [arXiv:1907.06554](https://arxiv.org/abs/1907.06554)
- [CLAM] Kuhn, Gal, Farquhar. CLAM: Selective Clarification for Ambiguous Questions. [arXiv:2212.07769](https://arxiv.org/abs/2212.07769)
- [IntentSim] Zhang & Choi. Clarify When Necessary. Verified title: "Clarify When Necessary: Resolving Ambiguity Through Interaction with LMs". [arXiv:2311.09469](https://arxiv.org/abs/2311.09469)
- [CLARINET] Chi, Lin, Lin, Klein. CLARINET. Verified title: "CLARINET: Augmenting Language Models to Ask Clarification Questions for Retrieval". [arXiv:2405.15784](https://arxiv.org/abs/2405.15784)
- [APA] Kim et al. Aligning Language Models to Explicitly Handle Ambiguity. [arXiv:2404.11972](https://arxiv.org/abs/2404.11972)
- [SemUnc] Kuhn, Gal, Farquhar. Semantic Uncertainty. ICLR 2023. Verified title: "Semantic Uncertainty: Linguistic Invariances for Uncertainty Estimation in Natural Language Generation". [arXiv:2302.09664](https://arxiv.org/abs/2302.09664)
- [SemEntropy] Farquhar, Kossen, Kuhn, Gal. Detecting hallucinations in LLMs using semantic entropy. Nature 2024. [nature.com](https://www.nature.com/articles/s41586-024-07421-0), [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11186750/)
- [Cole] Cole et al. Selectively Answering Ambiguous Questions. EMNLP 2023. [arXiv:2305.14613](https://arxiv.org/abs/2305.14613)
- [StressSpec] Zhang, Sleight, Peng, Schulman, Durmus. Stress-Testing Model Specs Reveals Character Differences among Language Models. 2025. [arXiv:2510.07686](https://arxiv.org/abs/2510.07686)
- [ExpertsRise] He, Zhou, Vanacore, Kizilcec, Huang. Experts Rise Where LLMs Disagree. 2026. [arXiv:2609.26926](https://arxiv.org/abs/2609.26926)
- [CrossModelPPL] Gorbett & Jana. Cross-Model Disagreement as a Label-Free Correctness Signal. 2026. [arXiv:2603.25450](https://arxiv.org/abs/2603.25450)
- [ClarifyGPT] Mu et al. ClarifyGPT. (method:. Verified title: "ClarifyGPT: Empowering LLM-based Code Generation with Intention Clarification". [arXiv:2310.10996](https://arxiv.org/abs/2310.10996), [arXiv:2310.10996](https://ar5iv.labs.arxiv.org/html/2310.10996)
- [SpecFix] Jia, Morris, Ye, Sarro, Mechtaev. Automated Repair of Ambiguous Problem Descriptions for LLM-Based Code Generation. ASE 2025. [arXiv:2505.07270](https://arxiv.org/abs/2505.07270)
- [HumanEvalComm] Wu & Fard. HumanEvalComm. Verified title: "HumanEvalComm: Benchmarking the Communication Competence of Code Generation for LLMs and LLM Agent". [arXiv:2406.00215](https://arxiv.org/abs/2406.00215)

**Annotation, agreement techniques**

- [Gilardi] Gilardi, Alizadeh, Kubli. ChatGPT Outperforms Crowd-Workers for Text-Annotation Tasks. PNAS 120(30), 2023. [V, full text]. [arXiv:2303.15056](https://arxiv.org/abs/2303.15056)
- [Tornberg23] Törnberg. ChatGPT-4 Outperforms Experts and Crowd Workers in Annotating Political Twitter Messages. [arXiv:2304.06588](https://arxiv.org/abs/2304.06588)
- [Tornberg24] Törnberg. Best Practices for Text Annotation with LLMs. Sociologica 18(2), 2024. [sociologica.unibo.it](https://sociologica.unibo.it/article/view/19461)
- [Reiss] Reiss. Testing the Reliability of ChatGPT for Text Annotation and Classification. [arXiv:2304.11085](https://arxiv.org/abs/2304.11085)
- [PSS] Barrie, Palaiologou, Törnberg. Prompt Stability Scoring for Text Annotation with LLMs. [arXiv:2407.02039](https://arxiv.org/abs/2407.02039)
- [Roulette] Haldar & Hockenmaier. Rating Roulette: Self-Inconsistency in LLM-As-A-Judge Frameworks. EMNLP Findings 2025. [V, full text]. [aclanthology.org](https://aclanthology.org/2025.findings-emnlp.1361.pdf)
- [Codebook] Halterman & Keith. Codebook LLMs. Political Analysis 2025. Verified title: "Codebook LLMs: Evaluating LLMs as Measurement Tools for Political Science Concepts". [arXiv:2407.10747](https://arxiv.org/abs/2407.10747)
- [LabelDefs] Mohammadi et al. Do LLMs Adhere to Label Definitions? EMNLP 2025. [arXiv:2509.02452](https://arxiv.org/abs/2509.02452)
- [Constitution] Berlin & Swanda. Improving Labeling Consistency with Detailed Constitutional Definitions and AI-Driven Evaluation. 2026. [arXiv:2605.24247](https://arxiv.org/abs/2605.24247)
- [CheckEval] Lee et al. CheckEval. EMNLP 2025. Verified title: "CheckEval: A reliable LLM-as-a-Judge framework for evaluating text generation using checklists". [arXiv:2403.18771](https://arxiv.org/abs/2403.18771)
- [TICK] Cook et al. TICKing All the Boxes. Verified title: "TICKing All the Boxes: Generated Checklists Improve LLM Evaluation and Generation". [arXiv:2410.03608](https://arxiv.org/abs/2410.03608)
- [FollowBench] Jiang et al. FollowBench. ACL 2024. Verified title: "FollowBench: A Multi-level Fine-grained Constraints Following Benchmark for Large Language Models". [arXiv:2310.20410](https://arxiv.org/abs/2310.20410)
- [IFEval] Zhou et al. Instruction-Following Evaluation for LLMs. [arXiv:2311.07911](https://arxiv.org/abs/2311.07911)
- [MinDemos] Min et al. Rethinking the Role of Demonstrations. EMNLP 2022. [arXiv:2202.12837](https://arxiv.org/abs/2202.12837)
- [ToCoT] Sprague et al. To CoT or not to CoT? ICLR 2025. Verified title: "To CoT or not to CoT? Chain-of-thought helps mainly on math and symbolic reasoning". [arXiv:2409.12183](https://arxiv.org/abs/2409.12183)
- [Temp] Renze & Guven. The Effect of Sampling Temperature on Problem Solving in LLMs. EMNLP Findings 2024. [arXiv:2402.05201](https://arxiv.org/abs/2402.05201)
- [USC] Chen et al. Universal Self-Consistency for LLM Generation. [arXiv:2311.17311](https://arxiv.org/abs/2311.17311)
- [eLLM] Kamen & Kamen. Majority Rules: LLM Ensemble is a Winning Approach for Content Categorization. [arXiv:2511.15714](https://arxiv.org/abs/2511.15714)
- [Ding] Ding. When LLMs Agree, Are They Right? 2026. [arXiv:2607.08065](https://arxiv.org/abs/2607.08065)

**Populations, conventions, debate**

- [Ashery] Ashery, Aiello, Baronchelli. Emergent social conventions and collective bias in LLM populations. Science Advances 11(20), 2025. [science.org](https://www.science.org/doi/10.1126/sciadv.adu9368), [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC12077490/)
- [Topology] Mehdizadeh & Hilbert. Exploring the Topology and Memory of Consensus. 2026. [arXiv:2606.04197](https://arxiv.org/abs/2606.04197)
- [ICCA] Hua & Artzi. Talk Less, Interact Better. COLM 2024. Verified title: "Talk Less, Interact Better: Evaluating In-context Conversational Adaptation in Multimodal LLMs". [arXiv:2408.01417](https://arxiv.org/abs/2408.01417)
- [JonesConv] Jones, Lombardi, Mahowald, Bergen. LLMs and people both learn to form conventions — just not with each other. 2026. [arXiv:2602.08208](https://arxiv.org/abs/2602.08208)
- [NoPacts] Wang, Mishra, Özyürek, Rubio-Fernández, Ghaleb. Aligned but Not Partner-Specific. 2026. [arXiv:2606.08081](https://arxiv.org/abs/2606.08081)
- [DeGrootLLM] Yazici, Kayaalp, Taga, Sayed. Opinion Consensus Formation Among Networked LLMs. ICASSP 2026. [arXiv:2601.21540](https://arxiv.org/abs/2601.21540)
- [Chuang] Chuang et al. Simulating Opinion Dynamics with Networks of LLM-based Agents. [arXiv:2311.09618](https://arxiv.org/abs/2311.09618)
- [DebateVote] Choi, Zhu, Li. Debate or Vote. NeurIPS 2025. Verified title: "Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?". [arXiv:2508.17536](https://arxiv.org/abs/2508.17536)
- [Estornell] Estornell & Liu. Multi-LLM Debate: Framework, Principals, and Interventions. NeurIPS 2024. [proceedings.nips.cc](https://proceedings.nips.cc/paper_files/paper/2024/file/32e07a110c6c6acf1afbf2bf82b614ad-Paper-Conference.pdf)
- [BenchForm] Weng, Chen, Wang. Do as We Do, Not as You Think: the Conformity of LLMs. ICLR 2025. [arXiv:2501.13381](https://arxiv.org/abs/2501.13381)

**Spec to artifact**

- [CADPrompt] Alrashedy et al. Generating CAD Code with Vision-Language Models for 3D Designs. [arXiv:2410.05340](https://arxiv.org/abs/2410.05340)
- [Text2CAD] Khan et al. Text2CAD. NeurIPS 2024. Verified title: "Text2CAD: Generating Sequential CAD Models from Beginner-to-Expert Level Text Prompts". [arXiv:2409.17106](https://arxiv.org/abs/2409.17106)
- [T2CBench] Wang et al. Text2CAD-Bench. 2026. (details:. Verified title: "Text2CAD-Bench: A Benchmark for LLM-based Text-to-Parametric CAD Generation". [arXiv:2605.18430](https://arxiv.org/abs/2605.18430), [arXiv:2605.18430](https://arxiv.org/html/2605.18430v1)
- [T2CQ] Xie & Ju. Text-to-CadQuery. 2025. Verified title: "Text-to-CadQuery: A New Paradigm for CAD Generation with Scalable Large Model Capabilities". [arXiv:2505.06507](https://arxiv.org/abs/2505.06507)
- [Query2CAD] Badagabettu, Yarlagadda, Barati Farimani. Query2CAD. Verified title: "Query2CAD: Generating CAD models using natural language queries". [arXiv:2406.00144](https://arxiv.org/abs/2406.00144)
- [CADConsensus] Haag, Kacan, Fuchs, Lohse. Test-Time Scaling for CAD Generation via Verifier-Free Consensus Selection. 2026. [arXiv:2608.09706](https://arxiv.org/abs/2608.09706)
- [BRepMatch] Jones, Noeckel, Kodnongbua, Baran, Schulz. B-rep Matching for Collaborating Across CAD Systems. ACM TOG 42(4), 2023. [arXiv:2306.03169](https://arxiv.org/abs/2306.03169)
- [Makatura] Makatura et al. How Can LLMs Help Humans in Design and Manufacturing?. Verified title: "How Can Large Language Models Help Humans in Design and Manufacturing?". [arXiv:2307.14377](https://arxiv.org/abs/2307.14377)
- [Ouyang] Ouyang, Zhang, Harman, Wang. An Empirical Study of the Non-determinism of ChatGPT in Code Generation. ACM TOSEM 2025. [arXiv:2308.02828](https://arxiv.org/abs/2308.02828)
- [MBRexec] Shi et al. Natural Language to Code Translation with Execution. EMNLP 2022. [arXiv:2204.11454](https://arxiv.org/abs/2204.11454)
- [CodeT] Chen et al. CodeT: Code Generation with Generated Tests. [arXiv:2207.10397](https://arxiv.org/abs/2207.10397)
- [FuncCluster] Ravuri & Amarasinghe. Eliminating Hallucination-Induced Errors in LLM Code Generation with Functional Clustering. 2025. [arXiv:2506.11021](https://arxiv.org/abs/2506.11021)
- [CodeEnsemble] Mahmud, Duan, Pasareanu, Yang. Enhancing LLM Code Generation with Ensembles. 2025. [arXiv:2503.15838](https://arxiv.org/abs/2503.15838)
- [PartialOrder] Zi, Menon, Guha. More Than a Score: Probing the Impact of Prompt Specificity on LLM Code Generation. [arXiv:2508.03678](https://arxiv.org/abs/2508.03678)

**Agreement statistics and correlated errors**

- [Kripp2011] Krippendorff. Computing Krippendorff's Alpha-Reliability (2011). [asc.upenn.edu](https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff%27s%20Alpha-Reliability.pdf)
- [KrippBoot] Krippendorff. Bootstrapping Distributions for Krippendorff's Alpha (rev. 2016). [asc.upenn.edu](https://asc.upenn.edu/sites/default/files/2021-03/Algorithm%20for%20Bootstrapping%20a%20Distribution%20of%20Alpha.pdf)
- [HayesKripp] Hayes & Krippendorff. Answering the Call for a Standard Reliability Measure for Coding Data. Communication Methods and Measures 1(1):77–89, 2007. [asc.upenn.edu](https://www.asc.upenn.edu/sites/default/files/2021-03/Answering%20the%20Call%20for%20a%20Standard%20Reliability%20Measure%20for%20Coding%20Data.pdf)
- [Gwet] Gwet. Computing inter-rater reliability and its variance in the presence of high agreement. Br. J. Math. Stat. Psychol. 61(1):29–48, 2008. Verified title: "Computing inter‐rater reliability and its variance in the presence of high agreement". [doi:10.1348/000711006X126600](https://doi.org/10.1348/000711006X126600)
- [ErrCons] Geirhos, Meding, Wichmann. Beyond Accuracy: Error Consistency. NeurIPS 2020. Verified title: "Beyond accuracy: quantifying trial-by-trial behaviour of CNNs and humans by measuring error consistency". [arXiv:2006.16736](https://arxiv.org/abs/2006.16736)
- [CAPA] Goel et al. Great Models Think Alike and this Undermines AI Oversight. ICML 2025 (PMLR 267). [arXiv:2502.04313](https://arxiv.org/abs/2502.04313), [proceedings.mlr.press](https://proceedings.mlr.press/v267/goel25b.html)
- [CorrErr] Kim, Garg, Peng, Garg. Correlated Errors in Large Language Models. ICML 2025. [arXiv:2506.07962](https://arxiv.org/abs/2506.07962)

Background for the 25 language design rules (can a description fix its object for any reader?), from [docs/reference/RESEARCH-LANGUAGE.md](docs/reference/RESEARCH-LANGUAGE.md) §9.


**Logic and philosophy of language**

- [Dawar] Dawar, A. *Model Theory on Finite Structures* (lecture notes, Univ. of Wales Swansea). [cl.cam.ac.uk](https://www.cl.cam.ac.uk/~ad260/talks/fmt-swansea1.pdf)
- [SEP-FOMT] Hodges, W. & Scanlon, T. "First-order Model Theory", SEP, rev. 2024-01-25. [plato.stanford.edu](https://plato.stanford.edu/entries/modeltheory-fo/)
- [SEP-HOL] "Second-order and Higher-order Logic", SEP, rev. 2024-08-31. [plato.stanford.edu](https://plato.stanford.edu/entries/logic-higher-order/)
- [SEP-Skolem] Bays, T. "Skolem's Paradox", SEP, rev. 2025-02-05. [plato.stanford.edu](https://plato.stanford.edu/entries/paradox-skolem/)
- [Putnam] Putnam, H. "Models and Reality", J. Symbolic Logic 45(3):464–482, 1980. [jstor.org](https://www.jstor.org/stable/2273415)
- [Tarski-ax] "Tarski's axioms", Wikipedia; Tarski & Givant, "Tarski's System of Geometry", Bull. Symbolic Logic 5(2), 1999. [en.wikipedia.org](https://en.wikipedia.org/wiki/Tarski%27s_axioms)
- [SEP-Witt] "Ludwig Wittgenstein", SEP, rev. 2026-09-17. [plato.stanford.edu](https://plato.stanford.edu/entries/wittgenstein/)
- [IEP-Kripke] "Kripke's Wittgenstein", Internet Encyclopedia of Philosophy.; Kripke, *Wittgenstein on Rules and Private Language*, Harvard UP 1982. [iep.utm.edu](https://iep.utm.edu/kripkes-wittgenstein/)
- [SEP-Quine] Hylton, P. "Willard Van Orman Quine", SEP, rev. 2023-07-06. [plato.stanford.edu](https://plato.stanford.edu/entries/quine/)
- [SEP-Goodman] Cohnitz, D. & Rossberg, M. "Nelson Goodman", SEP, rev. 2024-02-08. [plato.stanford.edu](https://plato.stanford.edu/entries/goodman/)
- [SEP-Davidson] Malpas, J. "Donald Davidson", SEP, rev. 2023-04-28. [plato.stanford.edu](https://plato.stanford.edu/entries/davidson/)
- [SEP-Conv] "Convention", SEP, rev. 2024-02-22. [plato.stanford.edu](https://plato.stanford.edu/entries/convention/)
- [Harnad] Harnad, S. "The Symbol Grounding Problem", Physica D 42:335–346, 1990. [arXiv:cs/9906002](https://arxiv.org/abs/cs/9906002)
- [BenderKoller] Bender, E. & Koller, A. "Climbing towards NLU", ACL 2020, pp. 5185–5198. [aclanthology.org](https://aclanthology.org/2020.acl-main.463/)
- [PiantadosiHill] Piantadosi, S. & Hill, F. "Meaning without reference in large language models", 2022. [arXiv:2208.02957](https://arxiv.org/abs/2208.02957)
- [SEP-Montague] Janssen, T. & Zimmermann, T. E. "Montague Semantics", SEP, rev. 2025-02-05. [plato.stanford.edu](https://plato.stanford.edu/entries/montague-semantics/)
- [SEP-DRT] "Discourse Representation Theory", SEP. [plato.stanford.edu](https://plato.stanford.edu/entries/discourse-representation-theory/)
- [SEP-Desc] "Descriptions", SEP, rev. 2022-09-21. [plato.stanford.edu](https://plato.stanford.edu/entries/descriptions/)
- [Wadler] Wadler, P. "Propositions as Types", CACM 58(12):75–84, 2015. [doi:10.1145/2699407](https://doi.org/10.1145/2699407)
- [Euclid] Euclid, *Elements* XI Def. 25 (Joyce ed.). [mathcs.clarku.edu](https://mathcs.clarku.edu/~djoyce/elements/bookXI/defXI25.html)

**Human communication and instructions**

- [KW64] Krauss, R. & Weinheimer, S. Psychonomic Science 1:113–114, 1964. Verified title: "Changes in reference phrases as a function of frequency of usage in social interaction: a preliminary study". [doi:10.3758/BF03342817](https://doi.org/10.3758/BF03342817)
- [KW66] Krauss, R. & Weinheimer, S. JPSP 4:343–346, 1966. Verified title: "Concurrent feedback, confirmation, and the encoding of referents in verbal communication.". [doi:10.1037/h0023705](https://doi.org/10.1037/h0023705)
- [CWG] Clark, H. & Wilkes-Gibbs, D. "Referring as a collaborative process", Cognition 22:1–39, 1986. [web.stanford.edu](https://web.stanford.edu/~clark/1980s/Clark.Wilkes-Gibbs.86.pdf)
- [BC96] Brennan, S. & Clark, H. "Conceptual pacts and lexical choice in conversation", JEP:LMC 22:1482–1493, 1996. [doi:10.1037/0278-7393.22.6.1482](https://doi.org/10.1037/0278-7393.22.6.1482)
- [Brennan96] Brennan, S. "Lexical entrainment in spontaneous dialog", ISSD-96, pp. 41–44. [cs.columbia.edu](https://www.cs.columbia.edu/~julia/papers/brennan96.pdf)
- [Furnas] Furnas, G. et al. "The vocabulary problem in human-system communication", CACM 30(11):964–971, 1987. [doi:10.1145/32206.32212](https://doi.org/10.1145/32206.32212)
- [Hawkins19] Hawkins, R., Frank, M. & Goodman, N. "Characterizing the dynamics of learning in repeated reference games". [arXiv:1912.07199](https://arxiv.org/abs/1912.07199)
- [GA87] Garrod, S. & Anderson, A. Cognition 27:181–218, 1987. Verified title: "Saying what you mean in dialogue: A study in conceptual and semantic co-ordination". [doi:10.1016/0010-0277(87)90018-7](https://doi.org/10.1016/0010-0277(87)90018-7)
- [PG04] Pickering, M. & Garrod, S. BBS 27:169–190, 2004. Verified title: "Toward a mechanistic psychology of dialogue". [doi:10.1017/S0140525X04000056](https://doi.org/10.1017/S0140525X04000056)
- [CB91] Clark, H. & Brennan, S. "Grounding in communication", 1991. Verified title: "Grounding in communication.". [doi:10.1037/10096-006](https://doi.org/10.1037/10096-006)
- [ClarkKrych] Clark, H. & Krych, M. "Speaking while monitoring addressees for understanding", JML 50:62–81, 2004. [doi:10.1016/j.jml.2003.08.004](https://doi.org/10.1016/j.jml.2003.08.004)
- [MapTask] HCRC Map Task design.; Anderson et al., Language and Speech 34(4), 1991. [groups.inf.ed.ac.uk](https://groups.inf.ed.ac.uk/maptask/maptask-description.html)
- [MinecraftACL] Narayan-Chen, A., Jayannavar, P. & Hockenmaier, J. ACL 2019, pp. 5405–5415. [aclanthology.org](https://aclanthology.org/P19-1537/)
- [Kranti] Kranti, C., Hakimov, S. & Schlangen, D. 2024. Verified title: "Retrieval-Augmented Code Generation for Situated Action Generation: A Case Study on Minecraft". [arXiv:2406.17553](https://arxiv.org/abs/2406.17553)
- [MadgePoesio] Madge, C. & Poesio, M. "Large Language Models as Minecraft Agents", 2024. [arXiv:2402.08392](https://arxiv.org/abs/2402.08392)
- [IGLU] Kiseleva, J. et al. 2022. Verified title: "Interactive Grounded Language Understanding in a Collaborative Environment: IGLU 2021". [arXiv:2205.02388](https://arxiv.org/abs/2205.02388)
- [Keysar00] Keysar, B. et al. Psychological Science 11:32–38, 2000. Verified title: "Taking Perspective in Conversation: The Role of Mutual Knowledge in Comprehension". [doi:10.1111/1467-9280.00211](https://doi.org/10.1111/1467-9280.00211)
- [Keysar03] Keysar, B., Lin, S. & Barr, D. Cognition 89:25–41, 2003. Verified title: "Limits on theory of mind use in adults". [doi:10.1016/S0010-0277(03)00064-7](https://doi.org/10.1016/S0010-0277(03)00064-7)
- [Schober] Schober, M. "Spatial perspective-taking in conversation", Cognition 47:1–24, 1993. [doi:10.1016/0010-0277(93)90060-9](https://doi.org/10.1016/0010-0277(93)90060-9)
- [Camerer] Camerer, C., Loewenstein, G. & Weber, M. JPE 97:1232–1254, 1989. Verified title: "The Curse of Knowledge in Economic Settings: An Experimental Analysis". [doi:10.1086/261651](https://doi.org/10.1086/261651)
- [Levinson] Levinson, S. *Space in Language and Cognition*, CUP 2003. [doi:10.1017/CBO9780511613609](https://doi.org/10.1017/CBO9780511613609)
- [Grice] Grice, H. P. "Logic and Conversation", 1975.; [SEP-Impl] "Implicature", SEP, rev. 2024-01-10. [doi:10.1163/9789004368811_003](https://doi.org/10.1163/9789004368811_003), [plato.stanford.edu](https://plato.stanford.edu/entries/implicature/)
- [Berry] Berry, D., Kamsties, E. & Krieger, M. *From Contract Drafting to Software Specification: Linguistic Sources of Ambiguity*, 2003. [cs.uwaterloo.ca](https://cs.uwaterloo.ca/~dberry/handbook/ambiguityHandbook.pdf)
- [Agrawala] Agrawala, M. et al. SIGGRAPH 2003. [graphics.stanford.edu](https://graphics.stanford.edu/papers/assembly_instructions/)
- [Heiser] Heiser, J. et al. AVI 2004, pp. 311–319. Verified title: "Identification and validation of cognitive design principles for automated generation of assembly instructions". [doi:10.1145/989863.989917](https://doi.org/10.1145/989863.989917)
- [NovickMorse] Novick, L. & Morse, D. Memory & Cognition 28:1242–1256, 2000. Verified title: "Folding a fish, making a mushroom: The role of diagrams in executing assembly procedures". [doi:10.3758/BF03211824](https://doi.org/10.3758/BF03211824)
- [LeFevreDixon] LeFevre, J. & Dixon, P. Cognition and Instruction 3:1–30, 1986. Verified title: "Do Written Instructions Need Examples?". [doi:10.1207/s1532690xci0301_1](https://doi.org/10.1207/s1532690xci0301_1)
- [Dixon] Dixon, P. JVLVB 21:70–84, 1982. Verified title: "Plans and written directions for complex tasks". [doi:10.1016/S0022-5371(82)90456-X](https://doi.org/10.1016/S0022-5371(82)90456-X)
- [EiriksdottirCatrambone] Eiriksdottir, E. & Catrambone, R. Human Factors 53:749–770, 2011. Verified title: "Procedural Instructions, Principles, and Examples". [doi:10.1177/0018720811419154](https://doi.org/10.1177/0018720811419154)
- [Shaikh] Shaikh, O. et al. "Grounding Gaps in Language Model Generations", NAACL 2024. [arXiv:2311.09144](https://arxiv.org/abs/2311.09144)
- [HuaArtzi] Hua, Y. & Artzi, Y. "Talk Less, Interact Better", COLM 2024. Verified title: "Talk Less, Interact Better: Evaluating In-context Conversational Adaptation in Multimodal LLMs". [arXiv:2408.01417](https://arxiv.org/abs/2408.01417)
- [Hawkins20] Hawkins, R. et al. "Continual adaptation for efficient machine communication", CoNLL 2020. [arXiv:1911.09896](https://arxiv.org/abs/1911.09896)
- [AmbiEnt] Liu, A. et al. "We're Afraid Language Models Aren't Modeling Ambiguity", EMNLP 2023. [arXiv:2304.14399](https://arxiv.org/abs/2304.14399)
- [Sclar] Sclar, M. et al. ICLR 2024. Verified title: "Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design or: How I learned to start worrying about prompt formatting". [arXiv:2310.11324](https://arxiv.org/abs/2310.11324)
- [ClarifyGPT] Mu, F. et al. 2023 (preprint). Verified title: "ClarifyGPT: Empowering LLM-based Code Generation with Intention Clarification". [arXiv:2310.10996](https://arxiv.org/abs/2310.10996)

**Controlled languages and engineering practice**

- [STE-site] ASD-STE100. [asd-ste100.org](https://www.asd-ste100.org/about.html), [asd-ste100.org](https://asd-ste100.org/about_STE.html)
- [tcworld] "ASD-STE100 Issue 9". [tcworld.info](https://www.tcworld.info/e-magazine/column/asd-ste100-issue-9-setting-a-standard-for-technical-documentation)
- [STE-wiki] "Simplified Technical English", Wikipedia. [en.wikipedia.org](https://en.wikipedia.org/wiki/Simplified_Technical_English)
- [Shubert] Shubert, S. et al. JTWC 25:347–369, 1995. Verified title: "The Comprehensibility of Simplified English in Procedures". [doi:10.2190/WG69-D74B-4DLL-2WBK](https://doi.org/10.2190/WG69-D74B-4DLL-2WBK)
- [Chervak] Chervak, S., Drury, C. & Ouellette, J. HFES 40:303–307, 1996. Verified title: "Simplified English for Aircraft Workcards". [doi:10.1177/154193129604000502](https://doi.org/10.1177/154193129604000502)
- [ASW2007] "Simplified Technical English", AeroSafety World, Aug 2007. [flightsafety.org](https://flightsafety.org/wp-content/uploads/2016/11/asw_aug07_p16-21.pdf)
- [ACE] Attempto Controlled English.; [ACE-IR]. [attempto.ifi.uzh.ch](http://attempto.ifi.uzh.ch/site/description/), [attempto.ifi.uzh.ch](http://attempto.ifi.uzh.ch/site/docs/ace_interpretationrules.html)
- [Kuhn] Kuhn, T. Computational Linguistics 40(1):121–170, 2014. Verified title: "A Survey and Classification of Controlled Natural Languages". [arXiv:1507.01701](https://arxiv.org/abs/1507.01701)
- [LogicalEnglish] Kowalski, R. & Datoo, A. AI and Law 30:163–197, 2021. Verified title: "Logical English meets legal English for swaps and derivatives". [doi:10.1007/s10506-021-09295-3](https://doi.org/10.1007/s10506-021-09295-3)
- [GF] Ranta, A. JFP 14(2):145–189, 2004. Verified title: "Grammatical Framework". [doi:10.1017/S0956796803004738](https://doi.org/10.1017/S0956796803004738)
- [EARS] Mavin, A. EARS.; Mavin et al., IEEE RE'09. [alistairmavin.com](https://alistairmavin.com/ears/)
- [RFC2119] [RFC8174]. [rfc-editor.org](https://www.rfc-editor.org/rfc/rfc2119), [rfc-editor.org](https://www.rfc-editor.org/rfc/rfc8174)
- [NASA-C] NASA SE Handbook, Appendix C. [nasa.gov](https://www.nasa.gov/seh/appendix-c-how-to-write-a-good-requirement)
- [INCOSE] INCOSE Guide to Writing Requirements v4. [jamasoftware.com](https://www.jamasoftware.com/requirements-management-guide/writing-requirements/incose-requirements-writing-guide/)
- [DeganiWiener] Degani, A. & Wiener, E.; Human Factors 35:345–359, 1993. Verified title: "Cockpit Checklists: Concepts, Design, and Use". [ntrs.nasa.gov](https://ntrs.nasa.gov/citations/19920000775), [doi:10.1177/001872089303500209](https://doi.org/10.1177/001872089303500209)
- [OPORD] "Operations order", Wikipedia; Army article on mission command (Perna, 2019). Verified title: "Mission command requires sharp commander's intent (Perna, 2019)". [en.wikipedia.org](https://en.wikipedia.org/wiki/Operations_order), [army.mil](https://www.army.mil/article/215297/mission_command_requires_sharp_commanders_intent)
- [Errington] Errington, T. et al. "Challenges for assessing replicability in preclinical cancer biology", eLife 2021.; [ErringtonMain]. [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC8651289/), [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC8651293/)
- [Vasilevsky] Vasilevsky, N. et al. PeerJ 1:e148, 2013. Verified title: "On the reproducibility of science: unique identification of research resources in the biomedical literature". [doi:10.7717/peerj.148](https://doi.org/10.7717/peerj.148)
- [Teytelman] Teytelman, L. et al. PLoS Biology 2016. Verified title: "Protocols.io: Virtual Communities for Protocol Development and Discussion". [doi:10.1371/journal.pbio.1002538](https://doi.org/10.1371/journal.pbio.1002538)
- [TLA] Lamport, L. TLA+. [lamport.azurewebsites.net](https://lamport.azurewebsites.net/tla/tla.html)
- [AWS] Newcombe, C. et al. CACM 58(4):66–73, 2015.; PDF. Verified title: "How Amazon web services uses formal methods". [doi:10.1145/2699417](https://doi.org/10.1145/2699417), [lamport.azurewebsites.net](https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf)
- [Alloy] . [alloytools.org](https://alloytools.org/about.html)
- [Adzic] Adzic, G. *Specification by Example*, Manning 2011. [manning.com](https://www.manning.com/books/specification-by-example)
- [Gherkin] . [cucumber.io](https://cucumber.io/docs/gherkin/reference/)
- [Requicha] Requicha, A. ACM Computing Surveys 12(4):437–464, 1980. Verified title: "Representations for Rigid Solids: Theory, Methods, and Systems". [doi:10.1145/356827.356833](https://doi.org/10.1145/356827.356833)
- [OpenSCAD] . [en.wikibooks.org](https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Primitive_Solids)
- [CadQuery] `Workplane.box`, cadquery/cq.py. [github.com/CadQuery/cadquery](https://github.com/CadQuery/cadquery/blob/master/cadquery/cq.py)

**Description length and reference**

- [Kolmogorov] "Kolmogorov complexity", Wikipedia , citing Kolmogorov 1965 and Li & Vitányi 2008. [en.wikipedia.org](https://en.wikipedia.org/wiki/Kolmogorov_complexity)
- [Rissanen] Rissanen, J. Automatica 14:465–471, 1978. Verified title: "Modeling by shortest data description". [doi:10.1016/0005-1098(78)90005-5](https://doi.org/10.1016/0005-1098(78)90005-5)
- [DaleReiter] Dale, R. & Reiter, E. Cognitive Science 19(2), 1995. Verified title: "Computational Interpretations of the Gricean Maxims in the Generation of Referring Expressions". [arXiv:cmp-lg/9504020](https://arxiv.org/abs/cmp-lg/9504020)
- [Pechmann] Pechmann, T. Linguistics 27:89–110, 1989. Verified title: "Incremental speech production and referential overspecification". [doi:10.1515/ling.1989.27.1.89](https://doi.org/10.1515/ling.1989.27.1.89)
- [Engelhardt] Engelhardt, P., Bailey, K. & Ferreira, F. JML 54:554–573, 2006. Verified title: "Do speakers and listeners observe the Gricean Maxim of Quantity?". [doi:10.1016/j.jml.2005.12.009](https://doi.org/10.1016/j.jml.2005.12.009)
- [Koolen] Koolen, R. et al. J. Pragmatics 43:3231–3250, 2011. Verified title: "Factors causing overspecification in definite descriptions". [doi:10.1016/j.pragma.2011.06.008](https://doi.org/10.1016/j.pragma.2011.06.008)
- [Degen] Degen, J. et al. Psychological Review 127:591–621, 2020. Verified title: "When redundancy is useful: A Bayesian approach to “overinformative” referring expressions.". [doi:10.1037/rev0000186](https://doi.org/10.1037/rev0000186), [arXiv:1903.08237](https://arxiv.org/abs/1903.08237)
- [RubioFernandez] Rubio-Fernández, P. Frontiers in Psychology 7:153, 2016. Verified title: "How Redundant Are Redundant Color Adjectives? An Efficiency-Based Analysis of Color Overspecification". [doi:10.3389/fpsyg.2016.00153](https://doi.org/10.3389/fpsyg.2016.00153)
- [FrankGoodman] Frank, M. & Goodman, N. Science 336:998, 2012. Verified title: "Predicting Pragmatic Reasoning in Language Games". [doi:10.1126/science.1218633](https://doi.org/10.1126/science.1218633)
- [ShepardMetzler] Shepard, R. & Metzler, J. Science 171:701–703, 1971. Verified title: "Mental Rotation of Three-Dimensional Objects". [doi:10.1126/science.171.3972.701](https://doi.org/10.1126/science.171.3972.701)
- [Hinton] Hinton, G. Cognitive Science 3:231–250, 1979. [cs.toronto.edu](https://www.cs.toronto.edu/~fritz/absps/cube.pdf)

## 6. Prior art compared

Related systems and results that Symblic was compared with, from the survey in [docs/reference/PRIOR-ART.md](docs/reference/PRIOR-ART.md) §14. The survey says which of its claims were re-checked; a listing here says only that the source exists and matches the citation.


**LM programming and prompt languages**

- [LMQL] Beurer-Kellner, Fischer, Vechev. Prompting Is Programming: A Query Language for LLMs. PLDI 2023. [arXiv:2212.06094](https://arxiv.org/abs/2212.06094)
- [Guidance] guidance-ai/guidance. [github.com/guidance-ai/guidance](https://github.com/guidance-ai/guidance)
- [llguidance] guidance-ai/llguidance. [github.com/guidance-ai/llguidance](https://github.com/guidance-ai/llguidance)
- [DSPy] Khattab et al. DSPy. ICLR 2024. Verified title: "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines". [arXiv:2310.03714](https://arxiv.org/abs/2310.03714)
- [DSPyAssert] Singhvi et al. DSPy Assertions. Verified title: "DSPy Assertions: Computational Constraints for Self-Refining Language Model Pipelines". [arXiv:2312.13382](https://arxiv.org/abs/2312.13382)
- [SGLang] Zheng et al. SGLang. NeurIPS 2024. Verified title: "SGLang: Efficient Execution of Structured Language Model Programs". [arXiv:2312.07104](https://arxiv.org/abs/2312.07104)
- [Outlines] Willard, Louf. Efficient Guided Generation for LLMs. 2023. [arXiv:2307.09702](https://arxiv.org/abs/2307.09702)
- [XGrammar] Dong et al. XGrammar. MLSys 2025. Verified title: "XGrammar: Flexible and Efficient Structured Generation Engine for Large Language Models". [arXiv:2411.15100](https://arxiv.org/abs/2411.15100)
- [PDL] Vaziri, Mandel, Spiess, Hirzel. PDL: A Declarative Prompt Programming Language. 2024. [arXiv:2410.19135](https://arxiv.org/abs/2410.19135), [arXiv:2507.06396](https://arxiv.org/abs/2507.06396), [github.com/IBM/prompt-declaration-language](https://github.com/IBM/prompt-declaration-language)
- [PPDL] Mandel, Baudart, Vaziri, Hirzel. PPDL: LLM-Based Flows as Probabilistic Programs. 2026. [arXiv:2608.05234](https://arxiv.org/abs/2608.05234)
- [POML] Zhang et al. POML. 2025. Verified title: "Prompt Orchestration Markup Language". [arXiv:2508.13948](https://arxiv.org/abs/2508.13948)
- [SudoLang] Elliott. SudoLang. [github.com/paralleldrive/sudolang-llm-support](https://github.com/paralleldrive/sudolang-llm-support)
- [APPL] Dong et al. APPL. ACL 2025. Verified title: "APPL: A Prompt Programming Language for Harmonious Integration of Programs and Large Language Model Prompts". [arXiv:2406.13161](https://arxiv.org/abs/2406.13161)
- [BAML] BoundaryML. [github.com/BoundaryML/baml](https://github.com/BoundaryML/baml), [boundaryml.com](https://boundaryml.com/blog/schema-aligned-parsing)
- [TypeChat] Microsoft TypeChat. [github.com/microsoft/TypeChat](https://github.com/microsoft/TypeChat)
- [Instructor] 567-labs/instructor. [github.com/567-labs/instructor](https://github.com/567-labs/instructor)
- [MTP] Dantanarayana et al. MTP: Meaning-Typed Programming (byLLM/Jac). OOPSLA 2025. Verified title: "MTP: A Meaning-Typed Language Abstraction for AI-Integrated Programming". [arXiv:2405.08965](https://arxiv.org/abs/2405.08965)
- [CoRE] Xu, Li, Mei, Zhang. AIOS Compiler: LLM as Interpreter for Natural Language Programming and Flow Programming of AI Agents. 2024. [arXiv:2405.06907](https://arxiv.org/abs/2405.06907), [github.com/agiresearch/CoRE](https://github.com/agiresearch/CoRE)
- [RunAgent] Srivastava et al. RunAgent. 2026. Verified title: "RunAgent: Interpreting Natural-Language Plans with Constraint-Guided Execution". [arXiv:2605.00798](https://arxiv.org/abs/2605.00798)
- [CogBASIC] Kramer. Cognitive BASIC. 2025. Verified title: "Cognitive BASIC: An In-Model Interpreted Reasoning Language for LLMs". [arXiv:2511.16837](https://arxiv.org/abs/2511.16837)
- [Mellea] IBM Research. Mellea. [github.com/generative-computing/mellea](https://github.com/generative-computing/mellea)
- [Agentics2] Gliozzo, Lee, Defosse. Agentics 2.0: Logical Transduction Algebra for Agentic Data Workflows. 2026. [arXiv:2603.04241](https://arxiv.org/abs/2603.04241)
- [SPL-CM] Gong. Structured Prompt Language: Declarative Context Management for LLMs. 2026. [arXiv:2602.21257](https://arxiv.org/abs/2602.21257)
- [SPL-DP] Gong. SPL: Orchestrating Workflows with Declarative Deterministic-Probabilistic Composition. 2026. [arXiv:2607.07727](https://arxiv.org/abs/2607.07727)
- [WaK] Quinto, Rozzi, Zanitti. Workflow as Knowledge: Semantic Persistence for LLM-Mediated Workflows. 2026. [arXiv:2607.08740](https://arxiv.org/abs/2607.08740)
- [Pel] Mohammadi. Pel, A Programming Language for Orchestrating AI Agents. 2025. [arXiv:2505.13453](https://arxiv.org/abs/2505.13453)
- [SK] Microsoft Semantic Kernel planning docs. [learn.microsoft.com](https://learn.microsoft.com/en-us/semantic-kernel/concepts/planning)
- [LangGraph] . [github.com/langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)
- [AIChains] Wu, Terry, Cai. AI Chains. CHI 2022. Verified title: "AI Chains: Transparent and Controllable Human-AI Interaction by Chaining Large Language Model Prompts". [arXiv:2110.01691](https://arxiv.org/abs/2110.01691)
- [PromptChainer] Wu et al. PromptChainer. CHI 2022 LBW. Verified title: "PromptChainer: Chaining Large Language Model Prompts through Visual Programming". [arXiv:2203.06566](https://arxiv.org/abs/2203.06566)
- [LLMPrograms] Schlag et al. Large Language Model Programs. 2023. [arXiv:2305.05364](https://arxiv.org/abs/2305.05364)
- [Promptware] Chen et al. Promptware Engineering. Verified title: "Promptware Engineering: Software Engineering for Prompt-Enabled Systems". [arXiv:2503.02400](https://arxiv.org/abs/2503.02400)
- [PromptsArePrograms] Liang et al. Prompts Are Programs Too! FSE 2025. Verified title: "Prompts Are Programs Too! Understanding How Developers Build Software Containing Prompts". [arXiv:2409.12447](https://arxiv.org/abs/2409.12447)
- [ell] . [github.com/MadcowD/ell](https://github.com/MadcowD/ell)
- [Cognify] Cognify Module Ensemble docs. [cognify-ai.readthedocs.io](https://cognify-ai.readthedocs.io/en/latest/fundamentals/cog_basics/ensemble.html)
- [AFlow] Zhang et al. AFlow. Verified title: "AFlow: Automating Agentic Workflow Generation". [arXiv:2410.10762](https://arxiv.org/abs/2410.10762)
- [BlendSQL] Glenn, Samuel, Liu. Play by the Type Rules. 2025. Verified title: "Play by the Type Rules: Inferring Constraints for LLM Functions in Declarative Programs". [arXiv:2509.20208](https://arxiv.org/abs/2509.20208)

**Controlled natural languages**

- [Kuhn2014] Kuhn. A Survey and Classification of Controlled Natural Languages. Computational Linguistics 40(1), 2014. [aclanthology.org](https://aclanthology.org/J14-1005), [arXiv:1507.01701](https://arxiv.org/abs/1507.01701)
- [ACE] Attempto Controlled English. [attempto.ifi.uzh.ch](http://attempto.ifi.uzh.ch/site/description/)
- [APE] . [github.com/Attempto/APE](https://github.com/Attempto/APE)
- [LogicalEnglish] Kowalski, Datoo. Logical English meets legal English. AI and Law, 2021. [doi:10.1007/s10506-021-09295-3](https://doi.org/10.1007/s10506-021-09295-3)
- [LE-AV] Sartor, Wyner, Contissa. 2025. Verified title: "Mind the Gaps: Logical English, Prolog, and Multi-agent Systems for Autonomous Vehicles". [arXiv:2502.09216](https://arxiv.org/abs/2502.09216)
- [CNL-P] Xing et al. CNL-P. 2025. Verified title: "When Prompt Engineering Meets Software Engineering: CNL-P as Natural and Robust "APIs'' for Human-AI Interaction". [arXiv:2508.06942](https://arxiv.org/abs/2508.06942)
- [S4L] Zin et al. 2026. Verified title: "Structured Four-Stage Legal Translation: From Natural-Language Traffic Rules to PROLOG". [arXiv:2609.20334](https://arxiv.org/abs/2609.20334)

**Neurosymbolic reasoning and formal proof**

- [PAL] Gao et al. PAL. 2022. Verified title: "PAL: Program-aided Language Models". [arXiv:2211.10435](https://arxiv.org/abs/2211.10435)
- [PoT] Chen et al. Program of Thoughts. TMLR 2023. Verified title: "Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks". [arXiv:2211.12588](https://arxiv.org/abs/2211.12588)
- [FaithfulCoT] Lyu et al. Faithful Chain-of-Thought. 2023. Verified title: "Faithful Chain-of-Thought Reasoning". [arXiv:2301.13379](https://arxiv.org/abs/2301.13379)
- [LogicLM] Pan et al. Logic-LM. Findings of EMNLP 2023. Verified title: "Logic-LM: Empowering Large Language Models with Symbolic Solvers for Faithful Logical Reasoning". [arXiv:2305.12295](https://arxiv.org/abs/2305.12295)
- [LogicLM++] Kirtania et al. 2024. Verified title: "LOGIC-LM++: Multi-Step Refinement for Symbolic Formulations". [arXiv:2407.02514](https://arxiv.org/abs/2407.02514)
- [LINC] Olausson et al. LINC. EMNLP 2023. Verified title: "LINC: A Neurosymbolic Approach for Logical Reasoning by Combining Language Models with First-Order Logic Provers". [arXiv:2310.15164](https://arxiv.org/abs/2310.15164)
- [SatLM] Ye et al. SatLM. NeurIPS 2023. Verified title: "SatLM: Satisfiability-Aided Language Models Using Declarative Prompting". [arXiv:2305.09656](https://arxiv.org/abs/2305.09656)
- [SymbCoT] Xu et al. SymbCoT. ACL 2024. Verified title: "Faithful Logical Reasoning via Symbolic Chain-of-Thought". [arXiv:2405.18357](https://arxiv.org/abs/2405.18357)
- [ChainOfCode] Li et al. Chain of Code. ICML 2024. Verified title: "Chain of Code: Reasoning with a Language Model-Augmented Code Emulator". [arXiv:2312.04474](https://arxiv.org/abs/2312.04474)
- [LLMModulo] Kambhampati et al. LLMs Can't Plan, But Can Help Planning in LLM-Modulo Frameworks. ICML 2024. [arXiv:2402.01817](https://arxiv.org/abs/2402.01817)
- [Valmeekam] Valmeekam et al. On the Planning Abilities of LLMs. NeurIPS 2023. [arXiv:2305.15771](https://arxiv.org/abs/2305.15771)
- [LLM-ASP] Yang, Ishay, Lee. Coupling LLMs with Logic Programming. Findings of ACL 2023. Verified title: "Coupling Large Language Models with Logic Programming for Robust and General Reasoning from Text". [arXiv:2307.07696](https://arxiv.org/abs/2307.07696)
- [PrologGen] Yang, Chen, Tam. Arithmetic Reasoning with LLM: Prolog Generation & Permutation. NAACL 2024. [arXiv:2405.17893](https://arxiv.org/abs/2405.17893)
- [ProofOfThought] Ganguly et al. 2024. Verified title: "Proof of Thought : Neurosymbolic Program Synthesis allows Robust and Interpretable Reasoning". [arXiv:2409.17270](https://arxiv.org/abs/2409.17270)
- [CLOVER] Ryu et al. Divide and Translate. ICLR 2025. Verified title: "Divide and Translate: Compositional First-Order Logic Translation and Verification for Complex Logical Reasoning". [arXiv:2410.08047](https://arxiv.org/abs/2410.08047)
- [WhenSolvers] He, Wang. When Do Symbolic Solvers Enhance Reasoning in LLMs? 2025. [arXiv:2512.03272](https://arxiv.org/abs/2512.03272)
- [ImprovingSymbolic] Thatikonda et al. 2026. Verified title: "Improving Symbolic Translation of Language Models for Logical Reasoning". [arXiv:2601.09446](https://arxiv.org/abs/2601.09446)
- [BeyondCompilation] Zhang et al. Beyond Compilation. 2026. Verified title: "Beyond Compilation: Evaluating Faithful Natural-Language-to-Lean Statement Formalization". [arXiv:2606.31002](https://arxiv.org/abs/2606.31002)
- [AutoformEquiv] Li et al. Autoformalize by Symbolic Equivalence and Semantic Consistency. NeurIPS 2024. Verified title: "Autoformalize Mathematical Statements by Symbolic Equivalence and Semantic Consistency". [arXiv:2410.20936](https://arxiv.org/abs/2410.20936)
- [Autoformalization] Wu et al. Autoformalization with LLMs. 2022. Verified title: "Autoformalization with Large Language Models". [arXiv:2205.12615](https://arxiv.org/abs/2205.12615)
- [DSProverV2] DeepSeek-Prover-V2. 2025. Verified title: "DeepSeek-Prover-V2: Advancing Formal Mathematical Reasoning via Reinforcement Learning for Subgoal Decomposition". [arXiv:2504.21801](https://arxiv.org/abs/2504.21801)
- [AlphaGeometry] Trinh et al. Nature 2024. [deepmind.google](https://deepmind.google/discover/blog/alphageometry-an-olympiad-level-ai-system-for-geometry/)
- [AlphaGeometry2] Chervonyi et al. 2025. Verified title: "Gold-medalist Performance in Solving Olympiad Geometry with AlphaGeometry2". [arXiv:2502.03544](https://arxiv.org/abs/2502.03544)
- [AlphaProof] Hubert et al. Nature 2025. [research.google](https://research.google/pubs/olympiad-level-formal-mathematical-reasoning-with-reinforcement-learning/), [deepmind.google](https://deepmind.google/blog/ai-solves-imo-problems-at-silver-medal-level/)
- [DeepThink] Google DeepMind, IMO 2025 gold. [deepmind.google](https://deepmind.google/discover/blog/advanced-version-of-gemini-with-deep-think-officially-achieves-gold-medal-standard-at-the-international-mathematical-olympiad)
- [Vieira] Li et al. Relational Programming with Foundation Models. AAAI 2024. [arXiv:2412.14515](https://arxiv.org/abs/2412.14515)
- [ANVIL] Patil et al. Where the LLM Ends and Reliable Decisions Begin. 2026. [arXiv:2609.19545](https://arxiv.org/abs/2609.19545)
- [PlanCompiler] Harikumar. PlanCompiler. 2026. Verified title: "PlanCompiler: A Deterministic Compilation Architecture for Structured Multi-Step LLM Pipelines". [arXiv:2604.13092](https://arxiv.org/abs/2604.13092)
- [CompiledAI] Trooskens et al. Compiled AI. 2026. Verified title: "Compiled AI: Deterministic Code Generation for LLM-Based Workflow Automation". [arXiv:2604.05150](https://arxiv.org/abs/2604.05150)

**Decomposition and context**

- [L2M] Zhou et al. Least-to-Most Prompting. ICLR 2023. Verified title: "Least-to-Most Prompting Enables Complex Reasoning in Large Language Models". [arXiv:2205.10625](https://arxiv.org/abs/2205.10625)
- [DecomP] Khot et al. Decomposed Prompting. ICLR 2023. Verified title: "Decomposed Prompting: A Modular Approach for Solving Complex Tasks". [arXiv:2210.02406](https://arxiv.org/abs/2210.02406)
- [Successive] Dua et al. Successive Prompting. 2022. Verified title: "Successive Prompting for Decomposing Complex Questions". [arXiv:2212.04092](https://arxiv.org/abs/2212.04092)
- [SelfAsk] Press et al. 2022. Verified title: "Measuring and Narrowing the Compositionality Gap in Language Models". [arXiv:2210.03350](https://arxiv.org/abs/2210.03350)
- [CoA] Zhang et al. Chain of Agents. NeurIPS 2024. Verified title: "Chain of Agents: Large Language Models Collaborating on Long-Context Tasks". [arXiv:2406.02818](https://arxiv.org/abs/2406.02818), [research.google](https://research.google/blog/chain-of-agents-large-language-models-collaborating-on-long-context-tasks/)
- [AoT] Teng et al. Atom of Thoughts. 2025. Verified title: "Atom of Thoughts for Markov LLM Test-Time Scaling". [arXiv:2502.12018](https://arxiv.org/abs/2502.12018)
- [RLM] Zhang, Kraska, Khattab. Recursive Language Models. [arXiv:2512.24601](https://arxiv.org/abs/2512.24601), [alexzhang13.github.io](https://alexzhang13.github.io/blog/2025/rlm/)
- [LambdaRLM] Roy et al. The Y-Combinator for LLMs. 2026. Verified title: "The $\mathbf{Y}$-Combinator for LLMs: Solving Long-Context Rot with $λ$-Calculus". [arXiv:2603.20105](https://arxiv.org/abs/2603.20105)
- [MemGPT] Packer et al. MemGPT. Verified title: "MemGPT: Towards LLMs as Operating Systems". [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)
- [SoT] Ning et al. Skeleton-of-Thought. ICLR 2024. Verified title: "Skeleton-of-Thought: Prompting LLMs for Efficient Parallel Generation". [arXiv:2307.15337](https://arxiv.org/abs/2307.15337)
- [ToT] Yao et al. Tree of Thoughts. NeurIPS 2023. Verified title: "Tree of Thoughts: Deliberate Problem Solving with Large Language Models". [arXiv:2305.10601](https://arxiv.org/abs/2305.10601)
- [GoT] Besta et al. Graph of Thoughts. AAAI 2024. Verified title: "Graph of Thoughts: Solving Elaborate Problems with Large Language Models". [arXiv:2308.09687](https://arxiv.org/abs/2308.09687)
- [BoT] Yang et al. Buffer of Thoughts. NeurIPS 2024. Verified title: "Buffer of Thoughts: Thought-Augmented Reasoning with Large Language Models". [arXiv:2406.04271](https://arxiv.org/abs/2406.04271)
- [LostMiddle] Liu et al. Lost in the Middle. TACL. Verified title: "Lost in the Middle: How Language Models Use Long Contexts". [arXiv:2307.03172](https://arxiv.org/abs/2307.03172)
- [ContextRot] Hong, Troynikov, Huber. Context Rot. Chroma, 2025. [trychroma.com](https://www.trychroma.com/research/context-rot)
- [NoLiMa] Modarressi et al. NoLiMa. ICML 2025. Verified title: "NoLiMa: Long-Context Evaluation Beyond Literal Matching". [arXiv:2502.05167](https://arxiv.org/abs/2502.05167)
- [Laban] Laban et al. LLMs Get Lost in Multi-Turn Conversation. 2025. [arXiv:2505.06120](https://arxiv.org/abs/2505.06120)
- [AnthCtxEng] Anthropic. Effective context engineering for AI agents. 2025. [anthropic.com](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [AnthHarness] Anthropic (Young et al.). Effective harnesses for long-running agents. 2025-11-26. [anthropic.com](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [AnthCtxMgmt] Anthropic. Context management. 2025. [claude.com](https://claude.com/blog/context-management)
- [AnthMultiAgent] Anthropic. How we built our multi-agent research system. 2025. [anthropic.com](https://www.anthropic.com/engineering/multi-agent-research-system)
- [CC-subagents] Claude Code sub-agents docs. [code.claude.com](https://code.claude.com/docs/en/sub-agents)
- [Ralph] Huntley. Ralph Wiggum as a "software engineer". 2025-07-14. [ghuntley.com](https://ghuntley.com/ralph/)
- [Cognition] Yan. Don't Build Multi-Agents. 2025. [cognition.com](https://cognition.com/blog/dont-build-multi-agents)
- [Delethink] Aghajohari et al. The Markovian Thinker. 2025. Verified title: "The Markovian Thinker: Architecture-Agnostic Linear Scaling of Reasoning". [arXiv:2510.06557](https://arxiv.org/abs/2510.06557)
- [InftyThink] Yan et al. InftyThink. Verified title: "InftyThink: Breaking the Length Limits of Long-Context Reasoning in Large Language Models". [arXiv:2503.06692](https://arxiv.org/abs/2503.06692)
- [PENCIL] Yang et al. PENCIL. ICML 2025. Verified title: "PENCIL: Long Thoughts with Short Memory". [arXiv:2503.14337](https://arxiv.org/abs/2503.14337)
- [MEM1] Zhou et al. MEM1. 2025. Verified title: "MEM1: Learning to Synergize Memory and Reasoning for Efficient Long-Horizon Agents". [arXiv:2506.15841](https://arxiv.org/abs/2506.15841)
- [ContextFolding] Sun et al. Context-Folding. 2025. Verified title: "Scaling Long-Horizon LLM Agent via Context-Folding". [arXiv:2510.11967](https://arxiv.org/abs/2510.11967)
- [IterResearch] Chen et al. IterResearch. 2025. Verified title: "IterResearch: Rethinking Long-Horizon Agents with Interaction Scaling". [arXiv:2511.07327](https://arxiv.org/abs/2511.07327)
- [MarkovChains] Geng et al. Markovian Generation Chains in LLMs. 2026. [arXiv:2603.11228](https://arxiv.org/abs/2603.11228)

**Small models, ensembles, test-time compute**

- [SC] Wang et al. Self-Consistency. ICLR 2023. Verified title: "Self-Consistency Improves Chain of Thought Reasoning in Language Models". [arXiv:2203.11171](https://arxiv.org/abs/2203.11171)
- [USC] Chen et al. Universal Self-Consistency. 2023. Verified title: "Universal Self-Consistency for Large Language Model Generation". [arXiv:2311.17311](https://arxiv.org/abs/2311.17311)
- [MoreAgents] Li et al. More Agents Is All You Need. TMLR. [arXiv:2402.05120](https://arxiv.org/abs/2402.05120)
- [MoreCalls] Chen et al. Are More LLM Calls All You Need? 2024. [arXiv:2403.02419](https://arxiv.org/abs/2403.02419)
- [LLMonkeys] Brown et al. Large Language Monkeys. 2024. Verified title: "Large Language Monkeys: Scaling Inference Compute with Repeated Sampling". [arXiv:2407.21787](https://arxiv.org/abs/2407.21787)
- [InfScaling] Wu et al. Inference Scaling Laws. 2024. Verified title: "Inference Scaling Laws: An Empirical Analysis of Compute-Optimal Inference for Problem-Solving with Language Models". [arXiv:2408.00724](https://arxiv.org/abs/2408.00724)
- [Snell] Snell et al. Scaling LLM Test-Time Compute Optimally. 2024. [arXiv:2408.03314](https://arxiv.org/abs/2408.03314)
- [Liu1B] Liu et al. Can 1B LLM Surpass 405B LLM? 2025. Verified title: "Can 1B LLM Surpass 405B LLM? Rethinking Compute-Optimal Test-Time Scaling". [arXiv:2502.06703](https://arxiv.org/abs/2502.06703)
- [rStarMath] Guan et al. rStar-Math. 2025. Verified title: "rStar-Math: Small LLMs Can Master Math Reasoning with Self-Evolved Deep Thinking". [arXiv:2501.04519](https://arxiv.org/abs/2501.04519)
- [LetsVerify] Lightman et al. Let's Verify Step by Step. [arXiv:2305.20050](https://arxiv.org/abs/2305.20050)
- [ProcessBench] Zheng et al. ProcessBench. ACL 2025. Verified title: "ProcessBench: Identifying Process Errors in Mathematical Reasoning". [arXiv:2412.06559](https://arxiv.org/abs/2412.06559)
- [fLaws] Stroebl, Kapoor, Narayanan. The Limits of Inference Scaling Through Resampling. v3, 2026-03-26 (earlier versions titled Inference Scaling fLaws). [arXiv:2411.17501](https://arxiv.org/abs/2411.17501v3)
- [InverseTTC] Gema et al. Inverse Scaling in Test-Time Compute. [arXiv:2507.14417](https://arxiv.org/abs/2507.14417)
- [s1] Muennighoff et al. s1. 2025. Verified title: "s1: Simple test-time scaling". [arXiv:2501.19393](https://arxiv.org/abs/2501.19393)
- [R1] DeepSeek-AI. DeepSeek-R1. Verified title: "DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning". [arXiv:2501.12948](https://arxiv.org/abs/2501.12948)
- [R1-8B] DeepSeek-R1-0528-Qwen3-8B model card. [huggingface.co](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B)
- [MoA] Wang et al. Mixture-of-Agents. 2024. Verified title: "Mixture-of-Agents Enhances Large Language Model Capabilities". [arXiv:2406.04692](https://arxiv.org/abs/2406.04692)
- [SelfMoA] Li et al. Rethinking Mixture-of-Agents. 2025. Verified title: "Rethinking Mixture-of-Agents: Is Mixing Different Large Language Models Beneficial?". [arXiv:2502.00674](https://arxiv.org/abs/2502.00674)
- [MoADeception] Wolf, Yoon, Bogunovic. 2025. Verified title: "This Is Your Doge, If It Please You: Exploring Deception and Robustness in Mixture of LLMs". [arXiv:2503.05856](https://arxiv.org/abs/2503.05856)
- [Archon] Saad-Falcon et al. Archon. ICML 2025. Verified title: "Archon: An Architecture Search Framework for Inference-Time Techniques". [arXiv:2409.15254](https://arxiv.org/abs/2409.15254)
- [Du-debate] Du et al. Multiagent Debate. 2023. Verified title: "Improving Factuality and Reasoning in Language Models through Multiagent Debate". [arXiv:2305.14325](https://arxiv.org/abs/2305.14325)
- [MAD-Smit] Smit et al. Should we be going MAD?. Verified title: "Should we be going MAD? A Look at Multi-Agent Debate Strategies for LLMs". [arXiv:2311.17371](https://arxiv.org/abs/2311.17371)
- [DebateOrVote] Choi, Zhu, Li. Debate or Vote. NeurIPS 2025. Verified title: "Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?". [arXiv:2508.17536](https://arxiv.org/abs/2508.17536)
- [TalkCheap] Wynn, Satija, Hadfield. Talk Isn't Always Cheap. 2025. Verified title: "Talk Isn't Always Cheap: Understanding Failure Modes in Multi-Agent Debate". [arXiv:2509.05396](https://arxiv.org/abs/2509.05396)
- [ReConcile] Chen, Saha, Bansal. ReConcile. ACL 2024. Verified title: "ReConcile: Round-Table Conference Improves Reasoning via Consensus among Diverse LLMs". [arXiv:2309.13007](https://arxiv.org/abs/2309.13007)
- [RethinkBounds] Wang et al. Rethinking the Bounds of LLM Reasoning. 2024. [arXiv:2402.18272](https://arxiv.org/abs/2402.18272)
- [MAST] Cemri et al. Why Do Multi-Agent LLM Systems Fail? 2025. [arXiv:2503.13657](https://arxiv.org/abs/2503.13657)
- [BenchForm] Weng, Chen, Wang. ICLR 2025. Verified title: "Do as We Do, Not as You Think: the Conformity of Large Language Models". [arXiv:2501.13381](https://arxiv.org/abs/2501.13381)
- [MemeticDrift] Tanaka. When Is Collective Intelligence a Lottery? 2026. [arXiv:2603.24676](https://arxiv.org/abs/2603.24676)
- [SLM-MUX] Wang et al. SLM-MUX. 2025. Verified title: "Slm-mux: Orchestrating small language models for reasoning". [arXiv:2510.05077](https://arxiv.org/abs/2510.05077)
- [Avengers] Zhang et al. The Avengers. 2025. Verified title: "The Avengers: A Simple Recipe for Uniting Smaller Language Models to Challenge Proprietary Giants". [arXiv:2505.19797](https://arxiv.org/abs/2505.19797)
- [SmallAgents] Żywot et al. Can Small Agents Collaborate to Beat a Single LLM? 2026. [arXiv:2601.11327](https://arxiv.org/abs/2601.11327)
- [RethinkScale] Wang, Brorsson. Rethinking Scale. 2026. Verified title: "Rethinking Scale: Deployment Trade-offs of Small Language Models under Agent Paradigms". [arXiv:2604.19299](https://arxiv.org/abs/2604.19299)
- [SLMJury] Laddha, Pradhan, Srivastava. SLMJury. 2026. Verified title: "SLMJury: Can Small Language Models Judge as Well as Large Ones?". [arXiv:2606.07810](https://arxiv.org/abs/2606.07810)
- [CorrErrors] Kim, Garg, Peng, Garg. Correlated Errors in LLMs. ICML 2025. Verified title: "Correlated Errors in Large Language Models". [arXiv:2506.07962](https://arxiv.org/abs/2506.07962)
- [GreatModels] Goel et al. Great Models Think Alike. 2025. Verified title: "Great Models Think Alike and this Undermines AI Oversight". [arXiv:2502.04313](https://arxiv.org/abs/2502.04313)
- [FrugalGPT] Chen, Zaharia, Zou. FrugalGPT. Verified title: "FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance". [arXiv:2305.05176](https://arxiv.org/abs/2305.05176)
- [RouteLLM] Ong et al. RouteLLM. Verified title: "RouteLLM: Learning to Route LLMs with Preference Data". [arXiv:2406.18665](https://arxiv.org/abs/2406.18665)
- [LLMBlender] Jiang, Ren, Lin. LLM-Blender. ACL 2023. Verified title: "LLM-Blender: Ensembling Large Language Models with Pairwise Ranking and Generative Fusion". [arXiv:2306.02561](https://arxiv.org/abs/2306.02561)
- [SiliconCrowd] Schoenegger et al. Wisdom of the Silicon Crowd. 2024. Verified title: "Wisdom of the Silicon Crowd: LLM Ensemble Prediction Capabilities Rival Human Crowd Accuracy". [arXiv:2402.19379](https://arxiv.org/abs/2402.19379)
- [SelfCorrect] Huang et al. LLMs Cannot Self-Correct Reasoning Yet. ICLR 2024. Verified title: "Large Language Models Cannot Self-Correct Reasoning Yet". [arXiv:2310.01798](https://arxiv.org/abs/2310.01798)
- [SmallVerifiers] Zhang et al. Small LMs Need Strong Verifiers to Self-Correct. 2024. Verified title: "Small Language Models Need Strong Verifiers to Self-Correct Reasoning". [arXiv:2404.17140](https://arxiv.org/abs/2404.17140)
- [Physics33] Allen-Zhu, Li. Physics of LMs 3.3. Verified title: "Physics of Language Models: Part 3.3, Knowledge Capacity Scaling Laws". [arXiv:2404.05405](https://arxiv.org/abs/2404.05405)
- [Gemma3] Gemma Team. Gemma 3 Technical Report. [arXiv:2503.19786](https://arxiv.org/abs/2503.19786)
- [MAKER] Meyerson et al. Solving a Million-Step LLM Task with Zero Errors. 2025. [arXiv:2511.09030](https://arxiv.org/abs/2511.09030)
- [LLMJury] Liu. LLMs as a Jury. 2026. Verified title: "LLMs as a Jury: Cross-Model Consensus Can Outperform Process Reward Models for LLM Reasoning". [arXiv:2607.10139](https://arxiv.org/abs/2607.10139)
- [Ding] Ding. When LLMs Agree, Are They Right? 2026. [arXiv:2607.08065](https://arxiv.org/abs/2607.08065)
- [Aegean] Ruan et al. Reaching Agreement Among Reasoning LLM Agents. 2025. [arXiv:2512.20184](https://arxiv.org/abs/2512.20184)
- [llm-council] Karpathy. llm-council. [github.com/karpathy/llm-council](https://github.com/karpathy/llm-council)
- [InspectableCouncil] Wu et al. An Inspectable LLM Council. 2026. Verified title: "An Inspectable LLM Council for Multi-Model Research Answer Aggregation". [arXiv:2604.02923](https://arxiv.org/abs/2604.02923)

**Determinism, structured outputs, agreement**

- [TML-nondet] He et al. Defeating Nondeterminism in LLM Inference. Thinking Machines Lab, 2025-09-10. [thinkingmachines.ai](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)
- [Atil] Atil et al. Non-Determinism of "Deterministic" LLM Settings. [arXiv:2408.04667](https://arxiv.org/abs/2408.04667)
- [FP32] Yuan et al. Understanding and Mitigating Numerical Sources of Nondeterminism in LLM Inference. [arXiv:2506.09501](https://arxiv.org/abs/2506.09501)
- [TBIK] Zhang et al. Tree-Based Invariant Kernels. 2025. Verified title: "Deterministic Inference across Tensor Parallel Sizes That Eliminates Training-Inference Mismatch". [arXiv:2511.17826](https://arxiv.org/abs/2511.17826)
- [LLM42] Gond et al. LLM-42. 2026. Verified title: "LLM-42: Enabling Determinism in LLM Inference with Verified Speculation". [arXiv:2601.17768](https://arxiv.org/abs/2601.17768)
- [CrossGPU] Cooper et al. Accelerating the Mitigation of LLM Inference Nondeterminism Across GPU Architectures. 2026. [arXiv:2609.25624](https://arxiv.org/abs/2609.25624)
- [TokenProbs] Fu et al. Beyond Reproducibility. 2026. Verified title: "Beyond Reproducibility: Token Probabilities Expose Large Language Model Nondeterminism". [arXiv:2601.06118](https://arxiv.org/abs/2601.06118)
- [Drift] Chen, Zaharia, Zou. How is ChatGPT's behavior changing over time?. [arXiv:2307.09009](https://arxiv.org/abs/2307.09009)
- [ModelEquality] Gao, Liang, Guestrin. Model Equality Testing. ICLR 2025. Verified title: "Model Equality Testing: Which Model Is This API Serving?". [arXiv:2410.20247](https://arxiv.org/abs/2410.20247)
- [ChatGPT-codegen] Ouyang et al. Non-determinism of ChatGPT in code generation. Verified title: "An Empirical Study of the Non-determinism of ChatGPT in Code Generation". [arXiv:2308.02828](https://arxiv.org/abs/2308.02828)
- [Claude-glossary] Anthropic glossary. [platform.claude.com](https://platform.claude.com/docs/en/docs/about-claude/glossary)
- [Claude-thinking] Anthropic thinking docs. [platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/thinking)
- [Claude-effort] Anthropic effort docs. [platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Claude-SO] Anthropic structured outputs. [platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [OAI-adv] OpenAI advanced usage (seed, system_fingerprint). [developers.openai.com](https://developers.openai.com/api/docs/guides/advanced-usage)
- [OAI-latest] OpenAI latest-model guide. [developers.openai.com](https://developers.openai.com/api/docs/guides/latest-model)
- [OAI-reasoning] OpenAI reasoning guide. [developers.openai.com](https://developers.openai.com/api/docs/guides/reasoning)
- [OAI-SO] OpenAI Structured Outputs. [developers.openai.com](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Gemini-SO] Gemini structured output. [ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output)
- [vLLM-repro] . [docs.vllm.ai](https://docs.vllm.ai/en/latest/usage/reproducibility.html)
- [vLLM-BI] . [docs.vllm.ai](https://docs.vllm.ai/en/latest/features/batch_invariance.html)
- [SGLang-det] . [docs.sglang.io](https://docs.sglang.io/advanced_features/deterministic_inference.html)
- [llamacpp-server] . [raw.githubusercontent.com](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md)
- [GBNF] . [raw.githubusercontent.com](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/grammars/README.md)
- [Ollama-SO] Ollama structured outputs, 2024-12-06. [ollama.com](https://ollama.com/blog/structured-outputs)
- [JSONSchemaBench] Geng et al. 2025. Verified title: "JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models". [arXiv:2501.10868](https://arxiv.org/abs/2501.10868)
- [SpeakFreely] Tam et al. Let Me Speak Freely? 2024. Verified title: "Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models". [arXiv:2408.02442](https://arxiv.org/abs/2408.02442)
- [SayWhatYouMean] Kurt (dottxt). Say What You Mean. [blog.dottxt.ai](https://blog.dottxt.ai/say-what-you-mean.html)
- [CRANE] Banerjee et al. CRANE. ICML 2025. Verified title: "CRANE: Reasoning with constrained LLM generation". [arXiv:2502.09061](https://arxiv.org/abs/2502.09061)
- [GAD] Park et al. Grammar-Aligned Decoding. NeurIPS 2024. [arXiv:2405.21047](https://arxiv.org/abs/2405.21047)
- [XieKG] Xie, Fang, Hu. LLMs build inconsistent knowledge graphs from one immune-checkpoint corpus. Frontiers in Immunology, 2026. [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC13529944/)
- [LeeRx] Lee. Cross-Model Consistency of AI-Generated Exercise Prescriptions. 2026. [arXiv:2604.19598](https://arxiv.org/abs/2604.19598)
- [Sarkar] Sarkar. How Reproducible Are Evaluation Conclusions? 2026. [arXiv:2609.30074](https://arxiv.org/abs/2609.30074)
- [FinDrift] Khatchadourian, Franco. LLM Output Drift. 2025. Verified title: "LLM Output Drift: Cross-Provider Validation & Mitigation for Financial Workflows". [arXiv:2511.07585](https://arxiv.org/abs/2511.07585)
- [SameOutcomes] Cui, Alexander. Same Prompt, Different Outcomes. 2026. [arXiv:2602.14349](https://arxiv.org/abs/2602.14349)
- [PromptPort] Kotte. PromptPort. 2026. Verified title: "PromptPort: A Reliability Layer for Cross-Model Structured Extraction". [arXiv:2601.06151](https://arxiv.org/abs/2601.06151)
- [Murin] Murin. 2026. Verified title: "Measuring the sensitivity of LLM-based structured extraction to prompt, model, and schema choices in clinical discharge summaries". [arXiv:2606.05970](https://arxiv.org/abs/2606.05970)
- [JCS] Rundgren, Jordan, Erdtman. RFC 8785 JSON Canonicalization Scheme. 2020. [rfc-editor.org](https://www.rfc-editor.org/rfc/rfc8785)
- [SemEntropy] Farquhar, Kossen, Kuhn, Gal. Detecting hallucinations in LLMs using semantic entropy. Nature 630, 2024. [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11186750/)
- [SemUncertainty] Kuhn, Gal, Farquhar. Semantic Uncertainty. ICLR 2023. Verified title: "Semantic Uncertainty: Linguistic Invariances for Uncertainty Estimation in Natural Language Generation". [arXiv:2302.09664](https://arxiv.org/abs/2302.09664)
- [SemanticVote] Jiang, Yi, Zhu. Semantic Voting. 2026. Verified title: "Semantic Voting: Execution-Grounded Consensus for LLM Code Generation". [arXiv:2605.08680](https://arxiv.org/abs/2605.08680)
- [StructuredSC] Xu, Huang, Zhang. Structured Self-Consistency. 2026. Verified title: "Structured Self-Consistency:A Multi-Task Evaluation of LLMs on VirtualHome". [arXiv:2602.00611](https://arxiv.org/abs/2602.00611)

**Formal specification to artifact**

- [Lindenmayer1968] Lindenmayer. Mathematical models for cellular interactions in development I and II. J. Theor. Biol. 18, 1968. [doi:10.1016/0022-5193(68)90079-9](https://doi.org/10.1016/0022-5193(68)90079-9), [doi:10.1016/0022-5193(68)90080-5](https://doi.org/10.1016/0022-5193(68)90080-5)
- [ABOP] Prusinkiewicz, Lindenmayer. The Algorithmic Beauty of Plants. Springer, 1990. [algorithmicbotany.org](https://algorithmicbotany.org/papers/abop/abop-ch1.pdf)
- [Vogel1979] Vogel. A better way to construct the sunflower head. Math. Biosci. 44:179-189, 1979. (DOI from search result; definition verified via [MathWorld-Vogel]). [doi:10.1016/0025-5564(79)90080-4](https://doi.org/10.1016/0025-5564(79)90080-4)
- [MathWorld-Vogel] . [mathworld.wolfram.com](https://mathworld.wolfram.com/VogelSpiral.html)
- [Infinigen] Raistrick et al. CVPR 2023. Verified title: "Infinite Photorealistic Worlds using Procedural Generation". [arXiv:2306.09310](https://arxiv.org/abs/2306.09310)
- [3DGPT] Sun et al. 3D-GPT. Verified title: "3D-GPT: Procedural 3D Modeling with Large Language Models". [arXiv:2310.12945](https://arxiv.org/abs/2310.12945)
- [FloraForge] Hadadi et al. 2025. Verified title: "FloraForge: LLM-Assisted Procedural Generation of Editable and Analysis-Ready 3D Plant Geometric Models For Agricultural Applications". [arXiv:2512.11925](https://arxiv.org/abs/2512.11925)
- [Scenic] Fremont et al. Scenic. PLDI 2019. Verified title: "Scenic: A Language for Scenario Specification and Scene Generation". [arXiv:1809.09310](https://arxiv.org/abs/1809.09310)
- [CADRecode] Rukhovich et al. CAD-Recode. Verified title: "CAD-Recode: Reverse Engineering CAD Code from Point Clouds". [arXiv:2412.14042](https://arxiv.org/abs/2412.14042)
- [Text2CAD] Khan et al. Text2CAD. NeurIPS 2024. Verified title: "Text2CAD: Generating Sequential CAD Models from Beginner-to-Expert Level Text Prompts". [arXiv:2409.17106](https://arxiv.org/abs/2409.17106)
- [CADCodeVerify] Alrashedy et al. Verified title: "Generating CAD Code with Vision-Language Models for 3D Designs". [arXiv:2410.05340](https://arxiv.org/abs/2410.05340)
- [Query2CAD] Badagabettu et al. Verified title: "Query2CAD: Generating CAD models using natural language queries". [arXiv:2406.00144](https://arxiv.org/abs/2406.00144)
- [LLM4CAD] Li, Sun, Sha. ASME IDETC 2024. [par.nsf.gov](https://par.nsf.gov/biblio/10661832)
- [CADCoder] Guan et al. CAD-Coder. NeurIPS 2025. Verified title: "CAD-Coder: Text-to-CAD Generation with Chain-of-Thought and Geometric Reward". [arXiv:2505.19713](https://arxiv.org/abs/2505.19713)
- [CADmium] Govindarajan et al. TMLR 2026. Verified title: "CADmium: Fine-Tuning Code Language Models for Text-Driven Sequential CAD Design". [arXiv:2507.09792](https://arxiv.org/abs/2507.09792)
- [BlenderLLM] Du et al. Verified title: "BlenderLLM: Training Large Language Models for Computer-Aided Design with Self-improvement". [arXiv:2412.14203](https://arxiv.org/abs/2412.14203)
- [AIDL] Jones et al. AIDL. 2025. Verified title: "A Solver-Aided Hierarchical Language for LLM-Driven CAD Design". [arXiv:2502.09819](https://arxiv.org/abs/2502.09819)
- [StarVector] Rodriguez et al. CVPR 2025. Verified title: "StarVector: Generating Scalable Vector Graphics Code from Images and Text". [arXiv:2312.11556](https://arxiv.org/abs/2312.11556)
- [LLM4SVG] Xing et al. CVPR 2025. Verified title: "Empowering LLMs to Understand and Generate Complex Vector Graphics". [arXiv:2412.11102](https://arxiv.org/abs/2412.11102)
- [Chat2SVG] Wu, Su, Liao. CVPR 2025. Verified title: "Chat2SVG: Vector Graphics Generation with Large Language Models and Image Diffusion Models". [arXiv:2411.16602](https://arxiv.org/abs/2411.16602)
- [OmniSVG] Yang et al. NeurIPS 2025. Verified title: "OmniSVG: A Unified Scalable Vector Graphics Generation Model". [arXiv:2504.06263](https://arxiv.org/abs/2504.06263)
- [VGBench] Zou et al. EMNLP 2024. Verified title: "VGBench: Evaluating Large Language Models on Vector Graphics Understanding and Generation". [arXiv:2407.10972](https://arxiv.org/abs/2407.10972)
- [SVGenius] Chen et al. 2025. Verified title: "SVGenius: Benchmarking LLMs in SVG Understanding, Editing and Generation". [arXiv:2506.03139](https://arxiv.org/abs/2506.03139)
- [SGPBench] Qiu et al. Can LLMs Understand Symbolic Graphics Programs? ICLR 2025. Verified title: "Can Large Language Models Understand Symbolic Graphics Programs?". [arXiv:2408.08313](https://arxiv.org/abs/2408.08313)
- [AutomaTikZ] Belouadi, Lauscher, Eger. ICLR 2024. Verified title: "AutomaTikZ: Text-Guided Synthesis of Scientific Vector Graphics with TikZ". [arXiv:2310.00367](https://arxiv.org/abs/2310.00367)
- [Pelicans] Willison. Pelicans on a bicycle. 2024-10-25. [simonwillison.net](https://simonwillison.net/2024/Oct/25/pelicans-on-a-bicycle/)
- [VISPROG] Gupta, Kembhavi. Visual Programming. CVPR 2023. Verified title: "Visual Programming: Compositional visual reasoning without training". [arXiv:2211.11559](https://arxiv.org/abs/2211.11559)
- [ViperGPT] Surís, Menon, Vondrick. ICCV 2023. Verified title: "ViperGPT: Visual Inference via Python Execution for Reasoning". [arXiv:2303.08128](https://arxiv.org/abs/2303.08128)
- [LMD] Lian et al. LLM-grounded Diffusion. TMLR 2024. Verified title: "LLM-grounded Diffusion: Enhancing Prompt Understanding of Text-to-Image Diffusion Models with Large Language Models". [arXiv:2305.13655](https://arxiv.org/abs/2305.13655)
- [VPGen] Cho, Zala, Bansal. NeurIPS 2023. Verified title: "Visual Programming for Text-to-Image Generation and Evaluation". [arXiv:2305.15328](https://arxiv.org/abs/2305.15328)

## 7. Other works cited in the design records

- **Aider-AI/grep-ast**. [github.com/Aider-AI/grep-ast](https://github.com/Aider-AI/grep-ast/tree/9a2c49b00852d012dc97850a3c0b3248f15bd043). Cited in [docs/reference/2026-10-06-full-symblic.md](docs/reference/2026-10-06-full-symblic.md).
- **OpenAI compatibility - Ollama**. [docs.ollama.com](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size). Cited in [docs/reference/2026-10-06-full-symblic.md](docs/reference/2026-10-06-full-symblic.md).
- **frabjous/logicpenguin**. [github.com/frabjous/logicpenguin](https://github.com/frabjous/logicpenguin/blob/da325893b81f6be1fd20443a9218b556a2e19790/public/js/checkers/derivation-check.js). Cited in [docs/reference/EDITOR.md](docs/reference/EDITOR.md).
- **magmide/magmide**. [github.com/magmide/magmide](https://github.com/magmide/magmide/blob/79eadf59f4790bd8dbb51d2f41c437c60bcd0873/README.md). Cited in [docs/reference/EDITOR.md](docs/reference/EDITOR.md).
- **sylvainhalle/textidote**. [github.com/sylvainhalle/textidote](https://github.com/sylvainhalle/textidote/blob/241beb356ff37dd4495bdaa0d58721888282cd16/Source/Core/src/ca/uqac/lif/textidote/as/AnnotatedString.java). Cited in [docs/reference/EDITOR.md](docs/reference/EDITOR.md).
- **ACE 6.5 Interpretation Rules**. [attempto.ifi.uzh.ch](https://attempto.ifi.uzh.ch/site/docs/ace/6.5/ace_interpretationrules.html). Cited in [docs/reference/EVIDENCE.md](docs/reference/EVIDENCE.md).
- **Robustness and Independent Evidence**. [doi:10.1086/692141](https://doi.org/10.1086/692141). Cited in [docs/reference/EVIDENCE.md](docs/reference/EVIDENCE.md).
- **Convex Optimization – Boyd and Vandenberghe**. [web.stanford.edu](https://web.stanford.edu/~boyd/cvxbook/). Cited in [docs/reference/EXPERIMENTS.md](docs/reference/EXPERIMENTS.md).
- **Course 18.086: Mathematical Methods for Engineers II**. [math.mit.edu](https://math.mit.edu/classes/18.086/2007/). Cited in [docs/reference/EXPERIMENTS.md](docs/reference/EXPERIMENTS.md).
- **Quantum Mechanics helps in searching for a needle in a haystack**. [arXiv:quant-ph/9706033](https://arxiv.org/abs/quant-ph/9706033). Cited in [docs/reference/EXPERIMENTS.md](docs/reference/EXPERIMENTS.md).
- **Clarify When Necessary: Resolving Ambiguity Through Interaction with LMs**. [aclanthology.org](https://aclanthology.org/2025.findings-naacl.306/). Cited in [docs/reference/INTERPRETER.md](docs/reference/INTERPRETER.md).
- **Interactive Semantic Parsing for If-Then Recipes via Hierarchical Reinforcement Learning**. [arXiv:1808.06740](https://arxiv.org/abs/1808.06740). Cited in [docs/reference/INTERPRETER.md](docs/reference/INTERPRETER.md).
- **codecrafters-io/build-your-own-x**. [github.com/codecrafters-io/build-your-own-x](https://github.com/codecrafters-io/build-your-own-x?tab=readme-ov-file#build-your-own-programming-language). Cited in [docs/reference/NOTES-2026-10-02.md](docs/reference/NOTES-2026-10-02.md).
- **Convex Optimization (Boyd and Vandenberghe), book PDF**. [web.stanford.edu](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf). Cited in [docs/reference/PROJECTION.md](docs/reference/PROJECTION.md).
- **Sagas (Garcia-Molina and Salem, 1987), Princeton technical report**. [cs.princeton.edu](https://www.cs.princeton.edu/research/techreps/598). Cited in [docs/reference/PROTOCOL-EXPERIMENTS.md](docs/reference/PROTOCOL-EXPERIMENTS.md).
- **NIST Guide to the SI, Appendix B.8: Factors for Units Listed Alphabetically | NIST**. [nist.gov](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8). Cited in [docs/reference/QUANTITIES.md](docs/reference/QUANTITIES.md).
- **SI Units – Temperature | NIST**. [nist.gov](https://www.nist.gov/pml/owm/si-units-temperature). Cited in [docs/reference/QUANTITIES.md](docs/reference/QUANTITIES.md).
- **SI base units - BIPM**. [bipm.org](https://www.bipm.org/en/measurement-units/si-base-units). Cited in [docs/reference/QUANTITIES.md](docs/reference/QUANTITIES.md).
- **OpenAI announcement of 8 September 2026 (the page blocks automated fetching; the announcement is reported by Quanta Magazine and others)**. [openai.com](https://openai.com/index/navier-stokes-solution/). Cited in [docs/reference/RESEARCH-ADOPTION.md](docs/reference/RESEARCH-ADOPTION.md).
- **Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?**. [arXiv:2508.17536](https://arxiv.org/html/2508.17536v1). Cited in [docs/reference/RESEARCH-AGREEMENT.md](docs/reference/RESEARCH-AGREEMENT.md).
- **Improving Labeling Consistency with Detailed Constitutional Definitions and AI-Driven Evaluation**. [arXiv:2605.24247](https://arxiv.org/html/2605.24247v1#S4.T2). Cited in [docs/reference/RESEARCH-AGREEMENT.md](docs/reference/RESEARCH-AGREEMENT.md).
- **Geometric numerical integration, lecture notes (Hairer), PDF**. [unige.ch](https://www.unige.ch/~hairer/poly_geoint/intro.pdf). Cited in [docs/reference/RESEARCH-GEOMETRY.md](docs/reference/RESEARCH-GEOMETRY.md).
- **Poisson equation — DOLFINx Python 0.12.0.dev0**. [docs.fenicsproject.org](https://docs.fenicsproject.org/dolfinx/main/python/demos/demo_poisson.html). Cited in [docs/reference/RESEARCH-TRANSFER.md](docs/reference/RESEARCH-TRANSFER.md).
- **openai/tiktoken**. [github.com/openai/tiktoken](https://github.com/openai/tiktoken/blob/main/tiktoken_ext/openai_public.py). Cited in [docs/reference/RESEARCH-TRANSFER.md](docs/reference/RESEARCH-TRANSFER.md).
- **A.I. May Have Solved a Longstanding Math Problem With a Million-Dollar Prize. It Ignited a Controversy Over Who Gets Credit**. [smithsonianmag.com](https://www.smithsonianmag.com/smart-news/ai-may-have-solved-a-longstanding-math-problem-with-a-million-dollar-prize-it-ignited-a-controversy-over-who-gets-credit-180989472/). Cited in [docs/reference/REVIEW-2.3.md](docs/reference/REVIEW-2.3.md).
- **Computational Optimal Transport (Peyré and Cuturi), book PDF**. [optimaltransport.github.io](https://optimaltransport.github.io/pdf/ComputationalOT.pdf). Cited in [docs/reference/TRANSPORT.md](docs/reference/TRANSPORT.md).
- **Convex Optimization (Boyd and Vandenberghe), book PDF**. [web.stanford.edu](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf#page=154). Cited in [docs/reference/VARIATIONAL.md](docs/reference/VARIATIONAL.md).
- **HTML Standard**. [html.spec.whatwg.org](https://html.spec.whatwg.org/multipage/webappapis.html#rendering-opportunity). Cited in [docs/reference/evidence/2026-10-06-english-dot.json](docs/reference/evidence/2026-10-06-english-dot.json).
- **Performance Criteria 1.2 TB1400 260708 - VESA Certified DisplayHDR™**. [displayhdr.org](https://displayhdr.org/performance-criteria/). Cited in [docs/reference/evidence/2026-10-06-english-dot.json](docs/reference/evidence/2026-10-06-english-dot.json).
- **UAX #15: Unicode Normalization Forms**. [unicode.org](https://www.unicode.org/reports/tr15/). Cited in [docs/reference/reinforcements/contract-audit.md](docs/reference/reinforcements/contract-audit.md).
- **PAL: Program-aided Language Models**. [arXiv:2211.10435](https://arxiv.org/abs/2211.10435v2). Cited in [docs/reference/reinforcements/cube-protocol.md](docs/reference/reinforcements/cube-protocol.md).
- **3. Data model — Python 3.11.17 documentation**. [docs.python.org](https://docs.python.org/3.11/reference/datamodel.html#object.__hash__). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **Aggregating Sets of Judgments: An Impossibility Result**. [doi:10.1017/S0266267102001098](https://doi.org/10.1017/S0266267102001098). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **Built-in Types — Python 3.11.17 documentation**. [docs.python.org](https://docs.python.org/3.11/library/stdtypes.html#integer-string-conversion-length-limitation). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **Character Encoding Stability**. [unicode.org](https://www.unicode.org/policies/stability_policy.html). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **Extensible Markup Language (XML) 1.0 (Fifth Edition)**. [w3.org](https://www.w3.org/TR/xml/#sec-notation). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **I2E: Exceptions**. [eiffel.org](https://www.eiffel.org/doc/eiffel/I2E-_Exceptions). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **Regular Expression Matching Can Be Simple And Fast**. [swtch.com](https://swtch.com/~rsc/regexp/regexp1.html). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **unicodedata — Unicode Database — Python 3.11.17 documentation**. [docs.python.org](https://docs.python.org/3.11/library/unicodedata.html). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).
- **unicodedata — Unicode Database — Python 3.12.15 documentation**. [docs.python.org](https://docs.python.org/3.12/library/unicodedata.html). Cited in [docs/reference/reinforcements/semantics-review.md](docs/reference/reinforcements/semantics-review.md).

References that appear only in the speculative documents ([docs/MADE-WITH-AI.md](docs/MADE-WITH-AI.md) lists them) are
not repeated here: they did not shape what Symblic is. Their links were checked in the same pass; the ones that
failed are in the next section.

## Links that could not be verified

These links appear in the documents but could not be confirmed on 2026-10-11 (the reason is given). They are not
used as sources above.

- <https://content.iospress.com/articles/occupational-ergonomics/oer00053>: the publisher blocks automated access (HTTP 403); the citing document marks it as seen only in a search snippet (cited in RESEARCH-LANGUAGE.md).
- <https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/using_selinux/getting-started-with-selinux_using-selinux>: the site blocks automated access (HTTP 403); cited only in an AI dialogue report (cited in SYMBLIC-COMPLETE-MASTER-RECORD.md, SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md).
- <https://www.phon.ucl.ac.uk/publications/WPL/02papers/wilson_sperber.pdf>: the server refused connections from the checking machine; the citing document marks it "not opened" (cited in RESEARCH-LANGUAGE.md).
- <https://agreestat.com/papers/bjmsp2008_interrater.pdf>: HTTP 404; the same paper is cited above through its DOI (Gwet 2008, [doi:10.1348/000711006X126600](https://doi.org/10.1348/000711006X126600)).
