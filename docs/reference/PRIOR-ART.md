# Symblic: prior-art survey and research scope

Original survey: 2026-10-02. Research qualification updates: 2026-10-03 and 2026-10-04.

**Source status:** the original catalogue, feature matrix and individual performance claims are retained
as historical research notes. They were **not independently reverified in the version-2.1 pass** and
must not be cited as established current product capabilities or benchmark results. Provider restrictions,
software features and preprint status may change. Section 1.1 identifies the primary comparators
separately reopened for this update; that check does not validate the rest of the catalogue or prove novelty.

The 2026-10-04 pass reopened the primary resampling paper (v3), MAKER and Vote/Filter-Vote papers
for the scope corrections below. Their task-specific results motivate experiments; they are not
universal laws for Symblic, and this pass does not revalidate every other survey entry.

Original survey method (historical account, not a new verification claim). Sources were reported as opened by the author and four research sub-agents, with WebSearch and WebFetch. Most are arXiv abstract or HTML pages, official documentation, GitHub READMEs, ACL Anthology, proceedings pages and publisher pages. Where a number mattered, it was re-checked against the paper's full text or raw page text. Anything that was seen only in a search snippet, or could not be confirmed on an opened page, is marked UNVERIFIED. Many 2026 items are arXiv preprints that have not been peer reviewed; they are labelled as preprints. Reference keys in square brackets, e.g. [MAKER], point to the reference list at the end.

---

## 1. Relationship to existing work

Taken one at a time, Symblic's components are prior art:

- **An LLM that interprets a program one step at a time.** CoRE [CoRE], RunAgent [RunAgent], Cognitive BASIC [CogBASIC] and Chain of Code's LMulator [ChainOfCode].
- **Per-block or per-call context control.** PDL's `contribute` field [PDL], MTP/byLLM's fresh per-call prompts [MTP], Agentics' stateless typed transductions [Agentics2], Chain-of-Agents [CoA], Atom of Thoughts [AoT], MAKER's minimal-context microagents [MAKER], and the "Ralph" and Anthropic harness practice of fresh sessions over on-disk state [Ralph][AnthHarness].
- **Typed, grammar-constrained outputs.** LMQL, Outlines, XGrammar, Guidance and provider structured outputs [LMQL][Outlines][XGrammar][Guidance][OAI-SO][Claude-SO].
- **Per-call effort controls.** Anthropic `effort` and OpenAI `reasoning.effort` [Claude-effort][OAI-reasoning].
- **Voting and mixture-of-agents as inference strategies.** Self-consistency [SC], MoA [MoA], PPDL [PPDL], DSPy `majority` [DSPy] and Mellea [Mellea].
- **A deterministic solver that decides while the LLM only translates.** PAL, Faithful CoT (including Datalog), Logic-LM, LINC, SatLM, Chain of Code, Vieira on Scallop (Datalog with foundation models as foreign predicates), SPL's SOLVE/ASSERT vs GENERATE, and λ-RLM [PAL][FaithfulCoT][LogicLM][LINC][SatLM][Vieira][SPL-DP][LambdaRLM].
- **Validate-and-repair loops.** DSPy Assertions/Refine, Instructor, TypeChat, Mellea and MTP [DSPyAssert][Instructor][TypeChat][Mellea][MTP].
- **Canonicalization standards and meaning-level grouping.** RFC 8785 JCS [JCS] and semantic entropy [SemEntropy][SemUncertainty].
- **Cross-model consensus as a selector.** ReConcile, LLMs-as-a-Jury and Karpathy's llm-council [ReConcile][LLMJury][llm-council].

Symblic combines the following engineering choices. This is a description of its design, not evidence that the combination is a first invention:

1. Each model-dependent statement can use an interchangeable LLM applicator; supported formal expressions run in the kernel.
2. Each statement carries author-declared context visibility (none, named prior results, all), effort and weight.
3. The context is rebuilt from canonical formal state between statements.
4. Supported formal expressions run in the kernel. Explicit asks can still request model-built
   formulas, programs or proofs; separate checkers evaluate those artifacts. Not every decidable
   problem has an implemented solver, and proof checking need not perform proof search.
5. Every result is canonicalized and fingerprinted.
6. Cross-applicator agreement is reported per statement, as a first-class output of the language.

This survey does not establish novelty of that combination. LMQL, PDL/PPDL, MTP/byLLM, PAL, LINC, controlled languages and other systems below overlap substantially. A publication claim needs an explicit comparison, reproducible artifacts and a result beyond recombining those components. Failure to find an identical system is a search limitation, not a novelty proof.

**Defensible claims:**

- For statements evaluated by the kernel (exact rational arithmetic, Datalog fixpoints, deterministic renderers), the intended result is fixed by the supported formal semantics, equal inputs and the same kernel/module versions, conditional on successful execution within limits. Conformance tests cover specific cases and platforms.
- For judgment statements whose outputs are restricted to finite or canonical domains (enums, booleans, integers, rationals, sets of declared atoms), Symblic can measure and report cross-applicator agreement. This is an empirical rate, not a guarantee.

**Overclaims to avoid:**

- **"4+4 is always 8 whatever the agent."** Direct kernel evaluation establishes this arithmetic
  result; a fresh model asked to construct an answer still needs checking.
- **"The same flower from any agent."** A deterministic renderer over a fully determined specification is one route [ABOP]. Models may also construct formal artifacts whose identity, uniqueness or declared equivalence is independently checked. No route guarantees that every fresh model will find an accepted artifact; translating the intended task remains fallible. Lean autoformalization shows a 3-29 point gap between "compiles" and "is faithful" [BeyondCompilation].
- **Identical open-ended text.** This cannot be guaranteed:
  - Temperature 0 alone is not a reproducibility guarantee; serving configuration and the tested
    conditions matter [TML-nondet][Atil].
  - The original survey reported non-default-temperature restrictions for the Claude models it considered [Claude-thinking].
  - Four LLMs given an identical prompt and schema built knowledge graphs whose edges overlapped with a Jaccard similarity of only 0.06-0.11 [XieKG].
- **"Councils of small models approach large-model reasoning."** Specific decomposed or verifier-assisted
  tasks motivate that hypothesis [MAKER][Liu1B][LLMonkeys]. The cited knowledge-heavy and debate results
  include failures [Avengers][Gemma3][DebateOrVote][TalkCheap][SLM-MUX]; they neither establish general
  parity nor rule out every useful small-model composition.

---

## 1.1 Primary comparators revisited for version 2.1

| Prior system | Established overlap | What Symblic must measure separately |
|---|---|---|
| [LMQL, PLDI 2023](https://arxiv.org/abs/2212.06094) | Prompt programming with control flow and constraints | Whether per-statement provenance, contracts and comparison add value beyond constrained generation |
| [PAL, ICML 2023](https://proceedings.mlr.press/v202/gao23f.html) | A model translates a problem into a program executed by an interpreter | Translation fidelity and equal-budget performance against an ordinary model-plus-interpreter baseline |
| [LINC, EMNLP 2023](https://arxiv.org/abs/2310.15164) | Language-to-logic translation followed by a theorem prover | Extraction errors and the coverage/false-acceptance tradeoff of Symblic's own formalization |
| [Attempto Controlled English interpretation rules](https://attempto.ifi.uzh.ch/site/docs/ace/6.5/ace_interpretationrules.html) | Controlled syntax and explicit scope/reference rules assign an executable reading | Whether authors choose the intended reading and can repair mismatches |
| [PDL](https://arxiv.org/abs/2410.19135) | Declarative prompt programs, structured results and context control | A concrete feature and benchmark comparison, not a claim that declarative orchestration is new |

The multi-frame design rationale ([EVIDENCE.md](EVIDENCE.md)) proposes: seek observation routes that can
expose each other's shared faults while addressing the same claim. It motivates provenance records and experiments, not an automatic confidence gain
from heterogeneous agents. Statistical independence requires stronger assumptions than different model
names or declared modes; [Stegenga and Menon](https://doi.org/10.1086/692141) make explicit the conditions
under which independence and confirmation support a diversity argument. [EVIDENCE.md](EVIDENCE.md)
describes the implemented declarations and what remains unestablished.

For the perspective gap, [Clark and Brennan's grounding account](https://www.cs.cmu.edu/~illah/CLASSDOCS/Clark91.pdf)
sets a task-relative criterion for mutual understanding and repair. A controlled parse can remove a
syntactic choice without proving equivalence to an author's mental state. A useful experiment therefore
measures reference recovery, omitted or invented properties, alternative readings and correction cost,
separately from runtime conformance and agreement.

A defensible research contribution could be an openly reproducible semantic/conformance suite and a
controlled evaluation of checked routing plus observation provenance. It is currently a research target,
not an established breakthrough. The historical catalogue and performance numbers below are retained
for traceability; this update rechecked the primary comparators above, not every legacy benchmark claim.

## 2. Comparison table

Historical feature matrix, not an implementation audit of every current release. Legend: Y = reported yes; P = partial (see the note); N = absent from the reviewed material or not found, not proved absent. "Cross-model identity measured" means the system or paper reports whether different models produce the same output for the same input.

| System | Year | Typed outputs | Per-step context control | Multi-model consensus | Deterministic kernel / solver | Cross-model identity measured | Link |
|---|---|---|---|---|---|---|---|
| LMQL | 2022-23 | P (typed vars, regex, token masks) | P (nested-query instructions scoped away) | N | N | N | https://arxiv.org/abs/2212.06094 |
| Guidance / llguidance | 2023- | Y (regex, CFG, JSON Schema) | N | N | N | N | https://github.com/guidance-ai/guidance |
| Outlines | 2023 | Y (FSM/CFG decoding) | N/A (single call) | N | N | N | https://arxiv.org/abs/2307.09702 |
| XGrammar | 2024 | Y (CFG engine, up to 100x faster) | N/A | N | N | N | https://arxiv.org/abs/2411.15100 |
| DSPy (+ Assertions, BestOfN/Refine) | 2023-25 | Y (typed signatures) | P (module prompt built from its signature) | P (`dspy.majority`, one model) | P (ProgramOfThought runs code) | N | https://arxiv.org/abs/2310.03714 |
| SGLang | 2023-24 | Y (regex/JSON) | P (fork/join of prompt state) | N | N | N | https://arxiv.org/abs/2312.07104 |
| PDL (IBM) | 2024-25 | Y (`spec` = JSON Schema subset) | Y/P (`contribute` per block; context accumulates by default) | N | P (code blocks) | N | https://arxiv.org/abs/2410.19135 |
| PPDL (probabilistic PDL) | 2026 | Y | as PDL | P (majority vote, IS, SMC; one model per flow in examples) | N | N | https://arxiv.org/abs/2608.05234 |
| POML (Microsoft) | 2025 | N | N | N | N | N | https://arxiv.org/abs/2508.13948 |
| SudoLang | 2023 | P (prompt-level) | N (one conversation) | N | N | N | https://github.com/paralleldrive/sudolang-llm-support |
| APPL | 2024-25 | P | P (function-scoped) | N | N | N | https://arxiv.org/abs/2406.13161 |
| BAML | 2023- | Y (typed functions + schema-aligned parsing) | N | N (provider fallback only) | N | N | https://github.com/BoundaryML/baml |
| TypeChat / Instructor | 2023- | Y (types + repair) | N | N | N (validator) | N | https://github.com/microsoft/TypeChat |
| MTP / byLLM (Jac) | 2024-25 | Y (type-checked, re-prompt on mismatch) | Y (prompt rebuilt from program state per call) | N | P (host language) | N | https://arxiv.org/abs/2405.08965 |
| CoRE / AIOS Compiler | 2024 | N | P (interpreter-chosen summary + retrieval per step) | N | N | N | https://arxiv.org/abs/2405.06907 |
| RunAgent | 2026 | P (XML) | P (accepted steps + summary, filtered) | N | P (code execution) | N | https://arxiv.org/abs/2605.00798 |
| Cognitive BASIC | 2025 | N | N | N | N | P (3 models compared, not identity) | https://arxiv.org/abs/2511.16837 |
| Mellea (IBM) | 2025- | Y (`@generative` typed functions) | N (not found) | P (majority voting, one model) | N | N | https://github.com/generative-computing/mellea |
| Agentics 2.0 (IBM) | 2026 | Y (Pydantic transductions) | Y (stateless calls, "locality of evidence") | N | N | N | https://arxiv.org/abs/2603.04241 |
| SPL, declarative context (Gong) | 2026 | N (not stated) | Y (token BUDGET/LIMIT per query) | N | N | N | https://arxiv.org/abs/2602.21257 |
| SPL, deterministic-probabilistic (Gong) | 2026 | N (not stated) | N (not stated) | N | Y (SOLVE/ASSERT via SymPy/SageMath) | N | https://arxiv.org/abs/2607.07727 |
| Workflow as Knowledge (derive vs infer) | 2026 | N | Y (infer under "declared context") | N | Y (derive) | N | https://arxiv.org/abs/2607.08740 |
| Vieira on Scallop | 2024 | Y (relations) | Y (FMs are stateless foreign functions) | N | Y (Datalog) | N | https://arxiv.org/abs/2412.14515 |
| λ-RLM | 2026 | Y (typed λ runtime) | Y (bounded leaf calls) | N | Y (pre-verified combinators) | N | https://arxiv.org/abs/2603.20105 |
| Recursive Language Models | 2025 | N | Y (context as REPL variable, sub-calls) | N | P (REPL) | N | https://arxiv.org/abs/2512.24601 |
| Chain of Code | 2023-24 | N | N | N | Y (interpreter first, LM fallback) | N | https://arxiv.org/abs/2312.04474 |
| PAL / PoT | 2022 | N | N | P (PAL majority@40, one model) | Y (Python) | N | https://arxiv.org/abs/2211.10435 |
| Faithful CoT | 2023 | N | N | N | Y (Python, Datalog, PDDL) | N | https://arxiv.org/abs/2301.13379 |
| Logic-LM / LINC / SatLM | 2023 | N | N | P (LINC K=10 vote, one model) | Y (Prover9, SAT/SMT and other symbolic solvers) | N | https://arxiv.org/abs/2305.12295 |
| MAKER | 2025 | P (format red-flagging) | Y (strategy + current state + previous move only) | P (per-step vote, one model) | N | N (model comparison of error rates only) | https://arxiv.org/abs/2511.09030 |
| Chain-of-Agents | 2024 | N | Y (chunked workers + communication unit) | N | N | N | https://arxiv.org/abs/2406.02818 |
| Atom of Thoughts | 2025 | N | Y (Markov: self-contained atomic question per state) | N | N | N | https://arxiv.org/abs/2502.12018 |
| Mixture-of-Agents / Self-MoA | 2024-25 | N | N | Y (layered aggregation) | N | N | https://arxiv.org/abs/2406.04692 |
| ReConcile | 2023-24 | N | N | Y (confidence-weighted, ChatGPT/Bard/Claude2) | N | P (response similarity reported) | https://arxiv.org/abs/2309.13007 |
| LLMs as a Jury | 2026 | N | N | Y (cross-model agreement as selector) | N | Y (agreement structure, not text identity) | https://arxiv.org/abs/2607.10139 |
| llm-council (Karpathy) | 2025 | N | N | Y (peer review + chairman) | N | N | https://github.com/karpathy/llm-council |
| CNL-P | 2025 | Y (BNF + Pydantic types + linter) | N | N | P (static linter) | N | https://arxiv.org/abs/2508.06942 |
| ACE + APE | 1996- | Y (DRS/FOL) | N/A (no LLM) | N/A | Y (deterministic parser) | N/A | http://attempto.ifi.uzh.ch/site/description/ |
| Logical English | 2021- | Y (Prolog) | N/A (no LLM) | N/A | Y (Prolog) | N/A | https://doi.org/10.1007/s10506-021-09295-3 |
| ell | 2024- | P | N | N | N | N (hashes prompt code, not outputs) | https://github.com/MadcowD/ell |
| LangGraph | 2024- | P (typed state) | P (nodes read explicit state) | N | N | N | https://github.com/langchain-ai/langgraph |
| **Symblic 2.1** | 2026 | Y (schema and runtime checks; decoding is adapter-dependent) | Y (none / named / all, per statement, rebuilt from formal state) | Y (heterogeneous vote, MoA rounds) | Y (rationals, Datalog, SVG renderer) | Y (per statement, canonical SHA-256) | — |

---

## 3. Area 1: LM programming and prompt languages

**LMQL** (Beurer-Kellner, Fischer, Vechev; PLDI 2023) [LMQL]
- Mixes prompt text with Python control flow and `where` constraints (stopping phrases, INT, set membership, length, regex). Constraints are evaluated eagerly per token and compiled into token masks.
- Reports 26-85% cost savings.
- Nested queries drop their local instructions from the trace and keep only the return value. This is a limited form of context scoping.

**Guidance / llguidance** [Guidance][llguidance]
- Constrain output with regex, `select`, context-free grammars and JSON Schema.
- llguidance computes a token mask in about 50 µs of CPU per token for a 128k-token vocabulary. It is integrated into llama.cpp, vLLM, SGLang and OpenAI structured outputs.
- Context accumulates in one stream.

**DSPy** (Khattab et al.; ICLR 2024) [DSPy] and **DSPy Assertions** (Singhvi et al., arXiv 2312.13382) [DSPyAssert]
- DSPy compiles declarative, typed "signatures" and modules into optimized prompts.
- Gains over few-shot prompting: more than 25% with GPT-3.5 and more than 65% with llama2-13b.
- Includes `dspy.majority` voting and ProgramOfThought.
- LM Assertions report up to 164% more constraint passes. Since DSPy 2.6 they are replaced by BestOfN and Refine.
- This is the closest library analogue to Symblic's ensure-and-repair. It does not measure agreement across models.

**SGLang** (Zheng et al.; NeurIPS 2024) [SGLang]
- A frontend language (gen, select, fork/join, regex-constrained generation) on a fast runtime with RadixAttention and compressed finite-state machines. Up to 6.4x throughput.
- `fork` copies prompt state. Authors cannot declare what each step sees.

**Outlines** (Willard and Louf, 2023) [Outlines] and **XGrammar** (Dong et al., MLSys 2025) [XGrammar]
- Outlines recasts constrained generation as transitions of a finite-state machine over an indexed vocabulary.
- XGrammar splits tokens into context-independent and context-dependent sets. It reports up to 100x speedup and near-zero end-to-end overhead.

**PDL** (Vaziri, Mandel, Spiess, Hirzel; IBM, arXiv 2410.19135, 2024) [PDL]
- A YAML-based prompt language with an implicit background context.
- Quote: "The contribute: keyword can specify a (possibly empty) subset of the two destinations 'result' or 'context'. By default, every block contributes to both".
- `spec:` types are "a subset of JSON Schema", and `parser:` supports json, yaml, regex and jsonl.
- The follow-up paper (arXiv 2507.06396) reports up to 4x improvement from tuning a compliance agent's prompting pattern.
- **PPDL** (Mandel, Baudart, Vaziri, Hirzel; arXiv 2608.05234, August 2026) [PPDL] adds majority voting, importance sampling and sequential Monte Carlo to flows without changing the flow logic:
  - GSM8K with granite4-small: 83.8% to 93.7% using importance sampling.
  - MiniF2F-Rocq: SMC@40 proved 95 of 244 theorems, vs 72.7 for sequential scaling.
  - All experiments used temperature 0.8. The paper makes no determinism or cross-model claims.
- PDL plus PPDL is the closest language-level match to Symblic's per-statement context and effort controls. It lacks context rebuilt from formal state, a decidable-statement kernel and cross-model identity.

**POML** (Microsoft Research, arXiv 2508.13948, 2025) [POML]
- Component markup with CSS-like styling to reduce format sensitivity. It is a presentation layer with no execution semantics.

**SudoLang** (Elliott, 2023) [SudoLang]
- A pseudocode language for LLMs. Interfaces are typed and constraints are "continuously respected by the AI".
- The LLM itself is the interpreter, inside one conversation.

**APPL** (Dong et al.; ACL 2025) [APPL]
- Prompts embedded in Python functions, with an async runtime and trace replay "without extra costs".

**BAML** [BAML]
- Typed LLM functions with schema-aligned parsing that repairs malformed JSON, plus retry and fallback across providers.
- Its blog reports function-calling accuracy on the BFCL benchmark: claude-3-haiku 91.7% with BAML's parser vs 57.3% with native function calling.

**TypeChat** [TypeChat] and **Instructor** [Instructor]
- Types drive the prompt. Validation failures are fed back for repair; Instructor's docs say "Failed validations are automatically retried with the error message."

**Meaning-Typed Programming / byLLM (Jac)** (Dantanarayana et al.; OOPSLA 2025) [MTP]
- The `by` operator hands a typed function to an LLM.
- The prompt is built from names, types and schemas plus runtime values, with no conversation history. On a type mismatch it re-prompts with the wrong output and the expected type.
- User study: 3.2x faster, with 45% fewer lines of code.
- This is the closest match to Symblic's rebuild-context-per-call plus typed repair. It is an operator inside a general-purpose language, not a statement language with consensus.

**CoRE / "AIOS Compiler: LLM as Interpreter for Natural Language Programming and Flow Programming of AI Agents"** (Xu, Li, Mei, Zhang; arXiv 2405.06907, 2024) [CoRE]
- Programs are named steps written as `name ::: type ::: instruction ::: connection`, with types Process, Decision and Terminal. The LLM interprets one step at a time.
- Each step's prompt holds the task description, a "Current Progress" summary, optional retrieved observations and the current instruction.
- On OpenAGI with GPT-4: 0.5744 vs 0.5391 for few-shot prompting.
- Outputs are untyped. Branch conditions are decided by the LLM. There is no voting, kernel or determinism claim.

**RunAgent** (Srivastava et al.; arXiv 2605.00798, May 2026) [RunAgent]
- Interprets natural-language plans step by step with IF/GOTO/FORALL, plus constraint derivation and checking at each step.
- Context is all accepted step instruction-output pairs plus a running summary.
- Uses a single model (GPT-4o). Natural-Plan calendar scheduling: 81.1% vs 68.9% for PlanGEN.

**Cognitive BASIC** (Kramer; arXiv 2511.16837, November 2025) [CogBASIC]
- BASIC-style numbered lines interpreted inside the model, producing explicit stepwise traces. Three LLMs were compared; output identity was not measured.

**Mellea** (IBM Research) [Mellea]
- `@generative` typed functions, natural-language requirements with validate-and-repair, and sampling strategies including rejection sampling and majority voting.
- Supports Ollama, OpenAI, HuggingFace, WatsonX, LiteLLM and Bedrock backends.

**Agentics 2.0** (Gliozzo, Lee, Defosse; IBM, arXiv 2603.04241, March 2026) [Agentics2]
- Each LLM call is a typed "transducible function" that "enforces schema validity and the locality of evidence". Calls "execute as stateless asynchronous calls".

**Structured Prompt Language (SPL)** (Wen G. Gong; arXiv 2602.21257, February 2026; arXiv 2607.07727, July 2026) [SPL-CM][SPL-DP]
- The first paper is SQL-like, with explicit `WITH BUDGET/LIMIT` token management and EXPLAIN. The same script runs on OpenRouter or a local Ollama instance.
- The second adds GENERATE/EVALUATE for LLM steps and SOLVE/ASSERT for deterministic computation (SymPy, SageMath), sharing variable bindings.
- This is the closest published design to Symblic's kernel/judgment split. No cross-model identity metric appears in the abstracts.

**"Workflow as Knowledge"** (Quinto, Rozzi, Zanitti; arXiv 2607.08740, July 2026) [WaK]
- Separates `derive`, "deterministic computation over available state", from `infer`, "mediated LLM judgment under declared context". Formal semantics are left as future work.

**Pel** (Mohammadi; arXiv 2505.13453, 2025) [Pel]
- A Lisp-like orchestration language with a grammar small enough for constrained generation, and natural-language conditions evaluated by LLMs.

**Other frameworks**
- **Semantic Kernel:** its Stepwise and Handlebars planners "have been deprecated and removed"; planning is now automatic function calling over chat history [SK].
- **LangGraph:** a stateful graph with typed state and checkpoints [LangGraph].
- **AI Chains / PromptChainer:** explicit step-to-step chaining in a GUI (Wu, Terry, Cai; CHI 2022) [AIChains][PromptChainer].
- **"Large Language Model Programs":** an algorithm decides what each LLM call sees; +6.4% over CoT (Schlag et al. 2023) [LLMPrograms].
- **Promptware Engineering:** LLMs as "probabilistic and non-deterministic" runtimes (Chen et al.; ACM TOSEM) [Promptware].
- **"Prompts Are Programs Too!":** 20 developer interviews; even experienced prompt programmers "struggle to develop reliable mental models" (Liang et al.; FSE 2025) [PromptsArePrograms].
- **ell:** hashes the lexical closure of the prompt program to version it. This is the only hashing found in this area, and it fingerprints code, not outputs [ell].

---

## 4. Area 2: Controlled natural languages

**Kuhn, "A Survey and Classification of Controlled Natural Languages"** (Computational Linguistics 40(1):121-170, 2014) [Kuhn2014]
- Surveys "exactly 100" English-based CNLs. They form "a single scattered cloud" between full English (P1 E5 N5 S1) and propositional logic (P5 E1 N1 S5).
- PENS dimensions:
  - **Precision:** P1 imprecise, up to P4 deterministically interpretable and P5 fixed semantics.
  - **Expressiveness:** E1 inexpressive, up to E3 first-order and E5 maximal.
  - **Naturalness:** N1 unnatural, up to N5 natural texts. Only N3 and above count as CNLs.
  - **Simplicity:** S1 very complex, up to S5 a one-page description.
- Symblic's supported formal fragment aims at P4-P5 precision. This classification does not extend to the meaning of arbitrary prose in model instructions; typed output alone does not fix that meaning.

**Attempto Controlled English (ACE)** (Fuchs, Kaljurand, Kuhn et al., University of Zurich) [ACE][APE]
- "a rich subset of standard English designed to serve as knowledge representation language", "unambiguously translated into discourse representation structures".
- Kuhn classifies it as P4 E3 N4 S3.
- The APE parser (SWI-Prolog) outputs DRS, FOL, OWL/SWRL and TPTP.
- ACE shows that a formal surface language can map deterministically to logic with no model involved.

**Logical English** (Kowalski and Datoo; Artificial Intelligence and Law, 2021) [LogicalEnglish]
- "syntactic sugar for logic programs". Typed variables are signalled by common nouns, sentences come from declared templates, and pronouns are disallowed to avoid ambiguity. It translates to Prolog or ASP.
- An application to UK Highway Code rules compiled to Prolog appears in [LE-AV].

**CNLs combined with LLMs**
- **CNL-P** (Xing et al.; arXiv 2508.06942, 2025) [CNL-P]:
  - A BNF grammar for prompts (PERSONA, CONSTRAINTS, typed VARIABLES, COMMAND, IF), Pydantic type checking and a linter.
  - The linter scored 100% accuracy vs 76.6% for GPT-4o.
  - Performance was comparable to natural-language prompts across 5 models.
- **CNL as a bridge to knowledge graphs** (Bhandiwad et al.; Knowledge-Based Systems, 2026) [CNL-KG]: LLMs parse into a CNL "more accurately and data-efficiently" than directly into SPARQL, and the CNL then converts deterministically.
- **Traffic-rule formalization** (Zin et al.; arXiv 2609.20334, 2026) [S4L]: rules correctly formalized were 75% via S4L, 60% via direct NL-to-Prolog and 55% via Logical English. In this study, Logical English as an intermediate step did not help.

---

## 5. Area 3: Neurosymbolic reasoning — the LLM translates, a solver decides

**PAL** (Gao et al., 2022) [PAL]
- The LLM writes Python and the interpreter computes the answer.
- GSM8K: 72.0% vs 65.6% for chain-of-thought (Codex). With majority voting at k=40: 80.4%.
- Standard deviation across 3 prompt orderings: 0.16 for PAL vs 1.10 for CoT. This is early evidence that moving computation into an interpreter stabilizes outputs.

**Program of Thoughts** (Chen et al.; TMLR 2023) [PoT]
- About 12% average gain over CoT across 5 math word-problem datasets and 3 financial QA datasets.

**Faithful CoT** (Lyu et al.; IJCNLP-AACL 2023) [FaithfulCoT]
- The LM translates to a symbolic chain, which "is executed by a deterministic solver": Python, Datalog, PDDL or a relational engine.
- Beats CoT on 9 of 10 benchmarks; relative gain of 21.4% on relational inference.

**Logic-LM** (Pan et al.; Findings of EMNLP 2023) [LogicLM]
- A symbolic solver plus self-refinement driven by solver error messages.
- +39.2% over standard prompting and +18.4% over CoT on average.
- Self-refinement raised GPT-4's executable rate on FOLIO from 79.9% to 85.8%.
- It lost to CoT on PrOntoQA (83.20 vs 98.79). Solvers do not always help.

**LINC** (Olausson et al.; EMNLP 2023, Outstanding Paper) [LINC]
- The LLM translates to first-order logic, Prover9 decides, and K=10 majority votes are taken over prover outputs.
- StarCoder+ (15.5B) with LINC beat GPT-3.5 and GPT-4 with CoT on ProofWriter by an absolute 38% and 10%.
- FOL syntax-error rates: 38% (StarCoder+), 24% (GPT-3.5), 13% (GPT-4).
- Quote: "all errors have been localized to the semantic parsing procedure."

**SatLM** (Ye et al.; NeurIPS 2023) [SatLM]
- The LLM writes a declarative specification and a SAT/SMT solver answers.
- GSM-Sys: 69.4 vs 43.4 for PAL and 46.5 for CoT.
- Unsatisfiable or ambiguous specifications are detected, which allows abstention. Selective accuracy on GSM-Sys: 77.1% vs 45.2%.
- Its correctness guarantee holds only "with respect to the parsed specification".

**SymbCoT** (Xu et al.; ACL 2024) [SymbCoT]
- A symbolic format, but executed "entirely ... by LLMs without relying on any external reasoners". GPT-4 on FOLIO: 83.33 vs 70.58 for CoT.
- It has no deterministic engine, so it offers no identity guarantee.

**Chain of Code** (Li et al.; ICML 2024 oral) [ChainOfCode]
- "If the line is executable by a code interpreter, it is executed ... If it is not ... a language model ... generates the next program state."
- BIG-Bench Hard: 84% vs 72% for CoT. On algorithmic tasks 95% vs 71%; on NLP tasks 74% vs 74%.
- This is the closest published analogue of Symblic's kernel-first applicator.

**LLM-Modulo** (Kambhampati et al.; ICML 2024) [LLMModulo] and **planning evaluation** (Valmeekam et al.; NeurIPS 2023) [Valmeekam]
- "auto-regressive LLMs cannot, by themselves, do planning or self-verification".
- LLMs should be coupled with "external model-based verifiers". GPT-4 alone averaged about 12% planning success across domains.

**Other solver-coupled work**
- **LLM + Answer Set Programming** (Yang, Ishay, Lee; Findings of ACL 2023) [LLM-ASP]: the LLM as a semantic parser into ASP knowledge modules; state of the art on bAbI, StepGame, CLUTRR and gSCAN.
- **Prolog generation** (Yang, Chen, Tam; NAACL 2024) [PrologGen]: generating Prolog for GSM8K beats CoT across three LLMs, because calculation is delegated to the interpreter.
- **Proof of Thought** (Ganguly et al., 2024) [ProofOfThought]: a JSON-based typed DSL compiled to FOL and checked by Z3.

**Critiques and limits of translate-then-solve**
- **CLOVER** (Ryu et al.; ICLR 2025) [CLOVER]: LLMs "have difficulties capturing complex logical semantics ... during translation". It compares candidate formalizations by SAT-checked semantic equivalence.
- **Logic-LM++** (Kirtania et al., 2024) [LogicLM++]: averages 18.5% over standard prompting and 5% over Logic-LM.
- **"When Do Symbolic Solvers Enhance Reasoning in LLMs?"** (He and Wang; arXiv 2512.03272) [WhenSolvers]: solvers help for problems with "limited implicit reasoning but ... ample search space" (constraint satisfaction with backtracking). On shallow deduction GPT-4o alone is better.
- **"Beyond Compilation"** (Zhang et al.; arXiv 2606.31002, 2026) [BeyondCompilation]: across 8 systems and 400 graduate-level statements, the gap between "compiles in Lean" and "faithful" was 3.0-29.0 points. The full agent compiled 89.5% but was faithful on only 60.5%.
- **Symbolic-equivalence ranking** (Li et al.; NeurIPS 2024) [AutoformEquiv]: ranks k candidate formalizations by ATP-checked equivalence, a usable mechanism for "same statement across models".

**Autoformalization and olympiad systems**
- **Wu et al. 2022** [Autoformalization]: 25.3% of competition problems were translated perfectly into Isabelle/HOL.
- **DeepSeek-Prover-V2** [DSProverV2]: 88.9% on miniF2F-test.
- **AlphaGeometry** (Trinh et al.; Nature 2024) [AlphaGeometry]: 25 of 30 olympiad geometry problems. A language model proposes constructions and a symbolic engine proves them.
- **AlphaGeometry2** [AlphaGeometry2]: 84% of IMO geometry problems from 2000-2024.
- **AlphaProof** (Nature 2025) [AlphaProof]: 28/42 at IMO 2024 together with AlphaGeometry 2, but "The problems were manually translated into formal mathematical language".
- **Gemini Deep Think** [DeepThink]: 35/42 at IMO 2025 end to end in natural language. Strong, but with no machine-checked or cross-model guarantee.

---

## 6. Area 4: Decomposition with fresh or limited context

**Classic decomposition**
- **Least-to-Most** (Zhou et al.; ICLR 2023) [L2M]: each subproblem is solved using "the answers to previously solved subproblems". SCAN ≥99% with 14 exemplars vs 16% for CoT. This is the named-prior-results mode.
- **Decomposed Prompting** (Khot et al.; ICLR 2023) [DecomP]: sub-task handlers that can be prompts, symbolic modules or retrievers.
- **Successive Prompting** (Dua et al., 2022) [Successive]: one simple question at a time; about 5% absolute F1 gain on few-shot DROP.
- **Self-Ask** [SelfAsk]: the "compositionality gap" does not shrink with scale; explicit sub-questions narrow it.

**Bounded per-step context**
- **Chain-of-Agents** (Zhang et al., Google; NeurIPS 2024) [CoA]: worker agents each read one chunk and pass a "communication unit" forward to a manager. Up to 10% better than RAG, full-context and multi-agent baselines. The Google blog states an 8k-token input limit per model.
- **Atom of Thoughts** (Teng et al.; NeurIPS 2025) [AoT]: Markov reasoning in which each state is contracted into a self-contained atomic question and history is dropped.
  - gpt-4o-mini reaches 80.6% F1 on HotpotQA, above o3-mini by 3.4 points.
  - On MATH and GSM8K the gains are modest: 83.6 vs 83.0 and 95.0 vs 93.5.
- **Recursive Language Models** (Zhang, Kraska, Khattab; arXiv 2512.24601) [RLM]:
  - The root model sees only the query. The long context sits as a REPL variable and is inspected programmatically, with sub-calls.
  - Handles inputs up to 100x beyond the context window. Median gains on GPT-5: 26% vs compaction and 130% vs CodeAct.
  - **λ-RLM** (Roy et al.; arXiv 2603.20105, 2026) [LambdaRLM] replaces the free-form REPL with "a compact library of pre-verified combinators", using neural inference only on bounded leaves. It beats standard RLM in 29 of 36 model-task comparisons, by up to +21.9 points.
- **MemGPT/Letta** [MemGPT]: OS-style virtual context in which the model pages memory itself. Symblic gives this control to the author instead.

**Search over thoughts**
- **Skeleton-of-Thought** [SoT]: independent points expanded in parallel.
- **Tree of Thoughts** (Yao et al.; NeurIPS 2023) [ToT]: Game of 24 rises from 4% (CoT) to 74%.
- **Graph of Thoughts** [GoT]: sorting quality 62% better than ToT at more than 31% lower cost.
- **Buffer of Thoughts** [BoT]: reusable thought templates.

**Evidence that long or accumulated context degrades performance**
- **Lost in the Middle** (Liu et al.; TACL) [LostMiddle]: relevant information in the middle of the context is used worst.
- **Chroma "Context Rot"** (Hong, Troynikov, Huber, July 2025) [ContextRot]: on 18 models, performance falls as input length grows, even on simple tasks.
- **NoLiMa** (ICML 2025) [NoLiMa]: at 32K tokens, 11 of 13 models fall below 50% of their short-context baseline. GPT-4o drops from 99.3% to 69.7%.
- **"LLMs Get Lost in Multi-Turn Conversation"** (Laban et al., 2025) [Laban]:
  - 15 LLMs and more than 200,000 simulated conversations. Average drop of 39% from single-turn to multi-turn.
  - Concatenating all information into one single-turn prompt recovers 95.1% of fully specified performance.
  - Unreliability stays around 30% even at temperature 0.
  - This is the strongest empirical support for "wipe and rebuild context from consolidated state".

**Vendor and industry practice**
- **Anthropic, "Effective context engineering for AI agents"** (September 2025) [AnthCtxEng]: compaction, structured notes and sub-agents returning condensed summaries.
- **Anthropic, "Effective harnesses for long-running agents"** (Young et al., 26 November 2025) [AnthHarness]:
  - "each new session begins with no memory of what came before". State lives in `claude-progress.txt`, a JSON feature list and git.
  - JSON was chosen because the model "is less likely to inappropriately change or overwrite JSON files compared to Markdown files".
- **Anthropic context editing and memory tool** [AnthCtxMgmt]: +29% on an internal agentic-search eval for editing alone and 84% fewer tokens in a 100-turn eval.
- **Claude Code sub-agents** "run in [their] own context window" [CC-subagents].
- **The "Ralph" loop** (Huntley, 14 July 2025) [Ralph]: `while :; do cat PROMPT.md | claude-code ; done`, one task per iteration, with state on disk.

**Counter-evidence: isolation can lose decisions**
- **Cognition, "Don't Build Multi-Agents"** (Yan, June 2025) [Cognition]: "Share context, and share full agent traces"; "Actions carry implicit decisions". Isolated sub-agents produced mismatched parts in their example.

**Learned state carry-over**
- **The Markovian Thinker / Delethink** (Aghajohari et al.; arXiv 2510.06557) [Delethink]: resets context at fixed-size chunks with a short learned carryover. A 1.5B model reasons in 8K chunks up to 24K tokens, matching LongCoT-RL.
- **InftyThink** [InftyThink], **PENCIL** [PENCIL], **MEM1** [MEM1] and **Context-Folding** [ContextFolding] show that compact rewritten state can match or beat full history, usually when the summarization is trained.
- **IterResearch** (arXiv 2511.07327) [IterResearch] reconstructs a Markovian workspace each round: 3.5% to 42.5% when extending to 2048 interactions.

**Repeated context-free passes can drift**
- **Markovian Generation Chains** (Geng et al.; arXiv 2603.11228, 2026) [MarkovChains]: when text is repeatedly processed "without including any prior memory", outputs "either converge to a small recurrent set or continue to produce novel sentences", depending on temperature and input. Symblic can retain canonical prior state instead of repeatedly replacing it with prose; that design
  does not itself prove that a model-driven chain cannot drift.

---

## 7. Area 5: Small models collectively vs. large models

See section 11 for the synthesis. Key works:

**Sampling and voting**
- **Self-consistency** (Wang et al.; ICLR 2023) [SC]: 40 sampled paths and a majority vote.
  - GSM8K +17.9 points for PaLM-540B (56.5 to 74.4).
  - Gains shrink for small models: UL2-20B +3.2, LaMDA-137B +10.6.
- **Universal Self-Consistency** [USC]: the model selects the most consistent free-form answer. The number of samples is limited by the context window.
- **"More Agents Is All You Need"** (Li et al.; TMLR) [MoreAgents]:
  - GSM8K: Llama2-13B rises from 0.35 to 0.59 with a 15-sample ensemble, matching a single Llama2-70B (0.54). The 70B with the same ensemble reaches 0.74.
  - Gains fall off at extreme difficulty.
- **Vote/Filter-Vote scaling** (Chen et al., 2024) [MoreCalls]: the studied aggregation schemes can
  improve and then degrade as calls increase, depending on query difficulty and answer distributions.
  A binary-majority threshold is not a universal rule for every multiclass voting procedure.
- **Large Language Monkeys** (Brown et al., 2024) [LLMonkeys]:
  - Coverage grows roughly log-linearly with sample count. SWE-bench Lite: 15.9% with 1 sample to 56% with 250.
  - On MATH, Llama-3-8B coverage goes from 82.9% (100 samples) to 98.44% (10,000), but majority voting only from 40.50% to 41.41%. Selection methods "saturate before reaching 100 samples".
- **Inference Scaling Laws** (Wu et al., 2024) [InfScaling]: Llemma-7B with tree search matches Llemma-34B at lower FLOPs, but the 34B has the higher ceiling. Voting "converges" to a limit that "only depends on the distribution modeled by the language model".

**Test-time compute and verifiers**
- **Snell et al., 2024** [Snell]:
  - Compute-optimal allocation is about 4x more efficient than best-of-N.
  - "on problems where a smaller base model attains somewhat non-trivial success rates, test-time compute can be used to outperform a 14x larger model".
  - On the hardest questions there is "very little" benefit; more pretraining compute is better there.
- **"Can 1B LLM Surpass 405B LLM?"** (Liu et al., 2025) [Liu1B]:
  - MATH-500: Llama-3.2-1B scores 72.2 vs Llama-3.1-405B 71.4; Qwen2.5-0.5B scores 76.4 vs GPT-4o 74.6.
  - AIME24: the 1B scores 10.0 vs 23.3.
  - Requires process reward models (7B-72B). "PRMs are hard to generalize across policy models and tasks."
- **rStar-Math** (Guan et al., 2025) [rStarMath]: Qwen2.5-Math-7B rises from 58.8 to 90.0 on MATH, using MCTS, a 7B process preference model and 4 rounds of self-evolution training.
- **Let's Verify Step by Step** [LetsVerify]: best-of-1860 with a PRM scores 78.2% vs 69.6% for majority voting.
- **ProcessBench** [ProcessBench]: existing PRMs "fail to generalize" beyond GSM8K and MATH.
- **The Limits of Inference Scaling Through Resampling** (Stroebl, Kapoor, Narayanan, v3) [fLaws]:
  false-positive acceptance limits the studied resampling procedures. HumanEval/MBPP results motivate
  stronger-verifier comparisons; the revised paper reports optimal attempts often below 10 under its
  utility assumptions, not a universal K≤5 rule. [Primary paper, v3](https://arxiv.org/abs/2411.17501v3)
- **Inverse Scaling in Test-Time Compute** [InverseTTC]: longer reasoning can lower accuracy.
- **DeepSeek-R1 distillation** [R1]:
  - Distill-Qwen-7B: AIME24 55.5 pass@1 and 83.3 cons@64, but GPQA-Diamond only 49.1 vs 65.0 for Claude-3.5-Sonnet.
  - DeepSeek-R1-0528-Qwen3-8B: AIME24 86.0 [R1-8B].
- **s1** [s1]: budget forcing works, but "eventually flattens out" and is capped by the context window.

**Mixture-of-Agents and architecture search**
- **Mixture-of-Agents** (Wang et al., 2024) [MoA]:
  - Open-source-only MoA reaches 65.1% length-controlled win rate on AlpacaEval 2.0 vs 57.5% for GPT-4o.
  - The six proposers are 70B-141B class models and the aggregator is Qwen1.5-110B. MoA-Lite scores 59.3%.
  - LLM-judged chat benchmark; no small-model evidence.
- **Self-MoA / "Rethinking MoA"** (Li et al., 2025) [SelfMoA]:
  - Repeated sampling of the single best model scores 65.7 vs 59.1 for mixed MoA (+6.6), and +3.8 on average across MMLU, CRUX and MATH.
  - "Quality matters more than diversity." Mixing helps only when members are similar in quality, by 0.17-0.35.
- **MoA under deception** [MoADeception]: one deceptive agent drops a Llama-3.1-70B MoA from 49.2 to 37.9.
- **Archon** (Saad-Falcon et al.; ICML 2025) [Archon]: +15.1% average over o1, GPT-4o and Claude 3.5 Sonnet. It is "most effective when utilizing LLMs with 70B+ parameters"; with 7B models, "7B models work well for ranking but are less effective for critique and fusion".

**Debate**
- **Multi-agent debate** (Du et al., 2023) [Du-debate]: gpt-3.5, 3 agents, 2 rounds, GSM8K 77.0 to 85.0. Test sets are small.
- **"Should we be going MAD?"** [MAD-Smit]: with GPT-3.5, debate did not reliably beat self-consistency (MMLU best was self-consistency, 0.78) and was sensitive to hyperparameters.
- **"Debate or Vote"** (Choi et al.; NeurIPS 2025) [DebateOrVote]:
  - "Majority Voting alone accounts for most of the performance gains."
  - Qwen2.5-7B on Arithmetic: single 0.814, vote 0.990, debate after 2 rounds 0.760, after 3 rounds 0.670.
  - The paper's martingale result holds under its formal assumptions; it is not an unconditional law of real multi-agent discussion.
- **"Talk Isn't Always Cheap"** [TalkCheap]: 3x Mistral-7B on CommonsenseQA drops from 44.4 to 39.4.
- **ReConcile** [ReConcile]: diverse frontier models gain up to 11.4%, but still lose to GPT-4 on GSM8K (85.3 vs 90.7).
- **"Rethinking the bounds of LLM reasoning"** [RethinkBounds]: a single agent with a strong prompt about equals the best discussion.
- **MAST** [MAST]: 14 failure modes in multi-agent systems, from more than 1,600 traces.
- **Conformity (BenchForm)** [BenchForm] and **memetic drift** [MemeticDrift]: group consensus can be a "lottery" driven by sampling noise.

**Small-model ensembles and routers**
- **SLM-MUX** (Wang et al., 2025) [SLM-MUX]:
  - With small models, debate, MoA and multi-agent verification "fail to outperform the best single model ... drops of up to 5.5%".
  - MATH: MoA 51.4 vs best single 56.8. 59.5% of failures were groupthink.
  - Selecting the most self-consistent model's answer works better.
- **The Avengers** [Avengers]: 10 models of about 7B, with routing calibrated on labeled data plus 10-sample self-consistency.
  - Averages 70.54 vs GPT-4.1 69.20, winning on AIME (61.67 vs 45.00).
  - Loses on knowledge-heavy tasks: GPQA 55.76 vs 62.05, MedQA 73.89 vs 88.77.
- **"Can Small Agents Collaborate to Beat a Single LLM?"** (2026) [SmallAgents]: a Qwen3-8B orchestrator with 1.7-8B sub-agents vs Qwen3-32B with tools.
  - AIME 55.0 vs 45.0, but GPQA 58.6 vs 60.1.
  - Sub-agent size barely mattered. Orchestrator thinking added +18.4 on AIME.
- **"Rethinking Scale"** (2026) [RethinkScale]: 27 models under 10B on finance tasks. Multi-agent quality score 0.36 vs 4.85 for a single agent with tools; completion rate 72.01% vs 99.67% for the base model.
- **SLMJury** (2026) [SLMJury]: with 16 judges of 0.6-14B, the best 3-judge jury was +0.06 over the best single judge, because "top judges share most mistakes".
- **Correlated errors** (Kim et al.; ICML 2025) [CorrErrors]: across 349 and 71 model sets, models agree about 60% of the time when both are wrong. More accurate models have more correlated errors.
- **"Great Models Think Alike"** [GreatModels]: mistakes become more similar as capability rises.
- **Routers and cascades:**
  - FrugalGPT [FrugalGPT] matches GPT-4 with up to 98% cost reduction.
  - RouteLLM [RouteLLM] routes between a strong and a weak model.
  - LLM-Blender [LLMBlender] ranks and fuses 11 open models.
  - Wisdom of the Silicon Crowd [SiliconCrowd]: 12 LLMs reach a Brier score of 0.20 vs 0.19 for 925 humans, not a significant difference.
- **MAKER** [MAKER]: see section 9 for the reported task and its decomposition/error assumptions.

---

## 8. Area 6: Determinism, constrained decoding, cross-model agreement

**Inference nondeterminism**
- **Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference"** (He et al., 10 September 2025) [TML-nondet]:
  - The main cause is lack of batch invariance: server load changes batch size, which changes reduction order.
  - Qwen3-235B-A22B at temperature 0, 1000 completions: 80 unique, first diverging at token 103. With batch-invariant kernels all 1000 are identical.
  - Cost on Qwen3-8B: 26 s by default, 55 s deterministic unoptimized, 42 s with an improved attention kernel.
- **Atil et al.** (arXiv 2408.04667) [Atil]:
  - 5 "deterministic" LLMs, 8 tasks, 10 runs. Accuracy varies by up to 15%, with a best-to-worst gap of up to 70%.
  - "None of the LLMs consistently delivers repeatable accuracy across all tasks, much less identical output strings."
  - Proposes TARr@N (agreement on raw output) and TARa@N (agreement on parsed answers).
- **Yuan et al.** (arXiv 2506.09501) [FP32]: under bf16 greedy decoding, up to 9% accuracy variation and up to 9,000-token length differences for DeepSeek-R1-Distill-Qwen-7B across GPU count, type and batch size.
- **Fixes for specific configuration changes:**
  - TBIK [TBIK]: invariance to tensor-parallel size.
  - LLM-42 [LLM42]: determinism through scheduling.
  - Cooper et al. 2026 [CrossGPU]: identical linear-layer outputs across NVIDIA Ampere, Ada and Hopper via fixed reduction order, 1.17-3.1x faster than prior fixes.
- **"Beyond Reproducibility"** [TokenProbs]: nondeterminism mainly perturbs tokens with probability between 0.1 and 0.9.
- **"How is ChatGPT's behavior changing over time?"** [Drift]: GPT-4 prime identification accuracy fell from 84% (March 2023) to 51% (June 2023). Model IDs drift.
- **Model Equality Testing** [ModelEquality]: 11 of 31 commercial Llama endpoints served distributions that differed from the reference weights.

**Provider and engine controls**
- **Anthropic** [Claude-glossary][Claude-thinking]:
  - "Even with temperature set to 0, the results will not be fully deterministic".
  - On Opus 4.7 and later, Sonnet 5 and later, Fable and Mythos, "non-default temperature, top_p, or top_k values return a 400 error".
- **OpenAI** [OAI-adv][OAI-latest]:
  - `seed` gives "(mostly) deterministic outputs", and `system_fingerprint` tracks backend changes.
  - For GPT-6-family models with reasoning effort other than `none`, `temperature`, `top_p` and `top_logprobs` should be removed.
- **Local engines** [vLLM-repro][vLLM-BI][SGLang-det][llamacpp-server][Ollama-SO]:
  - vLLM: reproducibility is not guaranteed by default; `VLLM_BATCH_INVARIANT=1` is beta.
  - SGLang has `--enable-deterministic-inference`.
  - llama.cpp: `cache_prompt` "can cause nondeterministic results", and `seed` defaults to -1 (random).
  - Ollama exposes `seed`, plus `format` for JSON Schema.

**Grammar-constrained decoding and structured outputs**
- **JSONSchemaBench** (Geng et al., 2025) [JSONSchemaBench]: 10K real-world schemas. Coverage on GitHub-Hard: Guidance 41%, llama.cpp 39%, XGrammar 28%, Outlines 3%. Constrained decoding improved accuracy by up to 4%.
- **OpenAI Structured Outputs** [OAI-SO]: strict mode adheres to the schema and emits keys "in the same order as the ordering of keys in the schema". It "can still contain mistakes". The launch claim of 100% vs under 40% for gpt-4-0613 is UNVERIFIED (search snippet only).
- **Claude structured outputs** [Claude-SO]:
  - Not supported: recursive schemas, numeric constraints, string-length constraints.
  - Enum and const capitalization is not guaranteed.
  - "A property that asks for the model's thinking or step-by-step reasoning may lead to a `reasoning_extraction` refusal."
- **Gemini** [Gemini-SO]: "always validate values".
- **llama.cpp GBNF** [GBNF]: converts JSON Schema to GBNF, but does not support `uniqueItems`, `not`, if/then/else and similar keywords.

**Format restrictions and reasoning**
- **"Let Me Speak Freely?"** (Tam et al., 2024) [SpeakFreely]:
  - Format restrictions can sharply cut reasoning. GSM8K with Claude-3-Haiku: 86.5 free text vs 23.4 with format-restricting JSON instructions. GPT-3.5-turbo: 76.6 vs 49.3.
  - In JSON mode GPT-3.5 put "answer" before "reason" in 100% of Last-Letter responses.
  - The two-step NL-to-Format method is "nearly identical" to free text. Classification tasks can improve under JSON mode.
- **Rebuttal, "Say What You Mean"** (dottxt) [SayWhatYouMean]: with fair prompts, structured generation matched or beat unstructured on Llama-3-8B (GSM8K 0.78 vs 0.77).
- **CRANE** (ICML 2025) [CRANE]: proves very restrictive grammars reduce reasoning. Allowing reasoning inside the grammar gains up to 10 points.
- **Grammar-Aligned Decoding** (NeurIPS 2024) [GAD]: token masking distorts the model's distribution.

**Measured cross-model and repeat agreement**
- **Xie, Fang, Hu** (Frontiers in Immunology, August 2026) [XieKG]:
  - 4 LLMs (DeepSeek, GLM, Kimi, Qwen), identical prompt and schema, 9,978 abstracts. Pairwise edge Jaccard 0.06-0.11.
  - "two-thirds to three-quarters of each model's graph were unique to that model".
  - Naive majority consensus did worse than the best single model. Only unanimous 4-model agreement beat it (precision 0.423 at about 4% coverage).
- **Lee** (arXiv 2604.19598, 2026) [LeeRx]: at temperature 0, 20 repeats per scenario, GPT-4.1 produced 100% unique outputs and Gemini 2.5 Flash 27.5% unique.
- **Sarkar** (arXiv 2609.30074, 2026) [Sarkar]: 8 open models (8B-675B), identical calls with caching off. Node-set Jaccard 0.39-0.96; 72% of prompt-model combinations never reached a perfect match.
- **Khatchadourian and Franco** (arXiv 2511.07585, 2025) [FinDrift]:
  - At T=0, Granite-3-8B and Qwen2.5-7B were 100% consistent; GPT-OSS-120B 12.5%.
  - SQL tasks were stable even at T=0.2; RAG tasks drifted 25-75%.
- **PromptPort** (arXiv 2601.06151, 2026) [PromptPort]: deterministic canonicalization recovers 6-8 F1 of cross-model gaps, and a verifier adds 14-16.
- **Murin** (arXiv 2606.05970, 2026) [Murin]: most cross-model disagreement on three-way clinical flags sat on "absent vs not mentioned". Collapsing to binary removed most of it. This also removes information: explicit absence and missing documentation are different states. Preserve that distinction whenever the task requires it, and report uncertainty or definition failures instead of improving agreement by changing the task.
- **Agreement as a correctness signal**
  - **"LLMs as a Jury"** (Liu, arXiv 2607.10139, 2026) [LLMJury]:
    - Cross-model consensus "selects correct answers better than self-consistency" across seven benchmarks.
    - On competition math it closes the gap to an oracle selector, through error decorrelation.
    - Its stated ceiling is a "shared-error floor", non-trivial on science.
  - **Ding** (arXiv 2607.08065, 2026) [Ding]:
    - Agreement is a weak positive predictor of correctness (rho 0.20-0.59).
    - For the most consistent frontier model, agreement was at least 0.8 on 77% of GPQA entries, and 48% of those were wrong.

**Canonicalization and meaning-level equivalence**
- **RFC 8785 JCS** [JCS]: sorted keys, ECMAScript number serialization, no whitespace, for "reliably repeatable" hashing.
- **Semantic entropy** (Farquhar et al., Nature 2024) [SemEntropy]: clusters answers by bidirectional entailment, with AUROC 0.790 for detecting confabulations.
- **SemanticVote** (arXiv 2605.08680, 2026) [SemanticVote]: clustering code candidates by execution fingerprints beat textual majority voting by 19-52 percentage points.

---

## 9. Area 8: Searching for the exact combination

Searches run on 2026-10-02 included:
- "deterministic prompt language"
- "cross-model reproducibility DSL"
- "statement-level context control LLM language"
- "stateless prompting per step"
- "LLM as interpreter natural-language program"
- "model-agnostic LLM program identical output"
- "Markovian agent current state only"
- "derive vs infer"
- "deterministic-probabilistic composition"
- "cross-model consensus"
- "canonicalization voting"
- the name "Symblic" (no collision found)

No system was found that combines the six properties in section 1. The nearest matches are:

- **MAKER** (Meyerson et al., 2025) [MAKER] is relevant prior art for long chains of small model tasks.
  It reports 1,048,575 correct Towers-of-Hanoi moves with gpt-4.1-mini, given a task decomposition and
  strategy, local state, repeated voting and response-format/length filters. Those filters detect selected
  failure signs; they are not semantic proofs of each move. The scaling analysis depends on its sampling
  and error assumptions; automatic decomposition and generalization remain separate questions. This is
  a reported task result, not a theorem that every tiny-step program succeeds.
  [Primary paper](https://arxiv.org/abs/2511.09030)
- **CoRE, PDL/PPDL, MTP/byLLM, RunAgent:** section 3.
- **SPL (deterministic-probabilistic) and Workflow as Knowledge:** the same kernel/judgment split as Symblic (section 3).
- **Vieira on Scallop** (Li et al., AAAI 2024; arXiv 2412.14515) [Vieira]: a Datalog kernel with recursion, aggregation and negation; foundation models are "stateless functions with relational inputs and outputs"; 12 model plugins; 9 tasks.
- **λ-RLM:** section 6.
- **Compile-once systems:**
  - ANVIL [ANVIL]: one model call writes a LaTeX formulation and a deterministic compiler emits solver code. 92.9% compiled with no model fallback; accuracy 98.9% easy and 91.1% hard on NLP4LP; "Almost all of these errors trace back to the formulation".
  - PlanCompiler [PlanCompiler]: 278/300 tasks vs 202/300 for GPT-4.1 and 187/300 for Claude Sonnet baselines.
  - Compiled AI [CompiledAI]: "workflows execute deterministically without further model invocation".
- **Heterogeneous councils:**
  - Karpathy's llm-council [llm-council]: first opinions, anonymized peer ranking, then a chairman model; "99% vibe coded as a fun Saturday hack".
  - An inspectable LLM Council [InspectableCouncil]: an analyst turns 3 candidates into structured state and a writer composes from it; 70.98 on DRACO.
- **Consensus serving:** Aegean [Aegean] adds a formal consensus protocol and quorum detection for reasoning agents, with 1.2-20x lower latency at answer quality within 2.5%.

**Cross-model identity as a design target.** The reviewed sources do not establish whether Symblic is first to combine these features. Per-statement comparison is an engineering feature whose utility must be measured against existing systems, not a novelty conclusion. The measurements that exist (section 8) show it is not achieved for open-ended or extraction outputs. They also show that agreement, even when achieved, is not the same as correctness [CorrErrors][Ding].

---

## 10. Area 7: Formal specification to an identical generative artifact

**L-systems**
- Lindenmayer introduced them in 1968 (J. Theoretical Biology 18:280-299 and 300-315) [Lindenmayer1968].
- *The Algorithmic Beauty of Plants* (Prusinkiewicz and Lindenmayer, Springer 1990; free edition at algorithmicbotany.org) [ABOP] states:
  - An L-system "is deterministic (noted DOL-system) if and only if for each a ∈ V there is exactly one χ ∈ V* such that a → χ".
  - "All plants generated by the same deterministic L-system are identical" (Sec. 1.7, p. 28).
  - For stochastic L-systems, "If the same L-system was used again (with different seed values for the random number generator), a variation of this image would be obtained" (p. 30).
  - The turtle-interpretation parameters (step d, angle δ, derivation depth n) are part of the specification. Fig. 1.26 is a flowering plant from a 7-production D0L system with n=5 and δ=18°.
- This is the classic precedent for "the same flower from a formal description".
- **Vogel's sunflower model** [Vogel1979][MathWorld-Vogel] is a smaller example: r_n = c√n, θ_n = n·α, with α the golden angle π(3-√5). It determines a seed-head pattern exactly.

**Procedural generation from language**
- **Infinigen** (CVPR 2023) [Infinigen]: entirely procedural assets from "randomized mathematical rules". Seed behaviour was not verified.
- **3D-GPT** [3DGPT]: LLM agents extract procedural parameters for Infinigen and Blender.
- **FloraForge** (arXiv 2512.11925) [FloraForge]: an LLM refines a procedural plant generator driven by human-readable YAML "Plant Descriptor" files.
- **Scenic** (PLDI 2019) [Scenic]: deliberately specifies distributions over scenes, the opposite design choice.

**LLM to CAD**
- **CAD-Recode** (Rukhovich et al.; ICCV 2025) [CADRecode]: point cloud to CadQuery Python with a 1.5B model. Mean Chamfer distance falls about tenfold (3.43 to 0.30 on DeepCAD).
- **Text2CAD** (NeurIPS 2024) [Text2CAD].
- **CADCodeVerify** [CADCodeVerify]: VLM render-and-check feedback gives 7.30% lower point-cloud distance with GPT-4.
- **Query2CAD** [Query2CAD]: 53.6% first-attempt success, +23.1% with refinement.
- **LLM4CAD** [LLM4CAD], **CAD-Coder** (NeurIPS 2025) [CADCoder], **CADmium** (TMLR 2026) [CADmium], **BlenderLLM** [BlenderLLM].
- **AIDL** [AIDL]: a solver-aided CAD DSL in which a geometric constraint solver does the spatial reasoning; it beats OpenSCAD in few-shot use. This is direct support for "the model writes constraints, the solver computes geometry".

**LLM to SVG and graphics programs**
- **Generators:** StarVector (CVPR 2025) [StarVector], LLM4SVG (CVPR 2025) [LLM4SVG], Chat2SVG (CVPR 2025, which reintroduces stochasticity through diffusion refinement) [Chat2SVG], OmniSVG (NeurIPS 2025) [OmniSVG].
- **VGBench** (EMNLP 2024) [VGBench]: LLMs do worse on low-level SVG than on higher-level formats such as TikZ and Graphviz.
- **SVGenius** [SVGenius]: "systematic performance degradation with increasing complexity".
- **SGP-Bench** (ICLR 2025 spotlight) [SGPBench]: best SVG understanding is 67.4% (Claude 3.5 Sonnet). GPT-4o scores 13.0% vs 10% chance on SGP-MNIST. Models cannot reliably "see" what code renders.
- **AutomaTikZ** (ICLR 2024) [AutomaTikZ].
- **Willison's "pelican riding a bicycle"** comparison (October 2024) [Pelicans]: the same prompt sent to 16 models gave widely different SVGs. This is informal. No peer-reviewed measurement of cross-model identity for the same formal SVG or CAD specification was found, which looks like an open gap.

**Code as the intermediate representation for vision**
- VISPROG (CVPR 2023) [VISPROG] and ViperGPT (ICCV 2023) [ViperGPT].
- LLM-grounded Diffusion [LMD] and VPGen [VPGen]: the layout step is deterministic, the pixels are not.

---

## 11. What the evidence says about small-model councils

1. **Matching frontier models happens mainly on verifiable math, and only with help.**
   - Small models beat older frontier models on MATH-500 when they have a strong process reward model, often as large as or larger than the policy, or training and distillation. Llama-3.2-3B scores 78.2 vs Llama-3.1-405B 71.4 [Liu1B]; rStar-Math 7B scores 90.0 vs o1-preview 85.5 [rStarMath].
   - On harder problems they lose: Llama-3.2-1B scores 10.0 vs 23.3 on AIME24 [Liu1B]. Snell finds "very little" test-time benefit on the hardest questions [Snell].
2. **Include a strong single-model baseline with matched sampling budget.** DeepSeek-R1-0528-Qwen3-8B scores 86.0 on AIME24 [R1-8B]. Any council has to beat one such model sampled several times.
3. **Without a verifier, voting saturates at the model's own most common answer.**
   - Llama-3-8B on MATH: coverage reaches 98.44% at 10,000 samples, yet majority voting moves only from 40.50% to 41.41% [LLMonkeys].
   - Voting converges to a limit set by the model's own distribution [InfScaling].
   - Self-consistency gains shrink for smaller models: +3.2 for UL2-20B vs +17.9 for PaLM-540B [SC].
4. **More votes can lower accuracy.** Vote/Filter-Vote experiments demonstrate non-monotone aggregate
   performance [MoreCalls]. In a binary independent-vote model p>0.5 has a specific role; multiple wrong
   answer classes and correlated samples require their own analysis, not a borrowed universal threshold.
5. **Errors are correlated, so the effective number of independent voters is smaller than the member count.**
   - Models agree about 60% of the time when both are wrong [CorrErrors], and similarity grows with capability [GreatModels].
   - A small-model jury gained +0.06 [SLMJury]. SLM-MUX peaked at 2 models on GPQA [SLM-MUX].
   - Cross-model juries help where errors decorrelate (math), but hit a "shared-error floor" in science [LLMJury].
6. **The cited 7–8B debate settings include losses against voting or direct baselines.**
   - Qwen2.5-7B on Arithmetic: vote 0.990 vs debate 0.670 [DebateOrVote].
   - 3x Mistral-7B on CommonsenseQA: 44.4 to 39.4 [TalkCheap].
   - Discussion methods fall up to 5.5% below the best single model, with 59.5% of failures from groupthink [SLM-MUX].
7. **MoA's headline results do not carry over to small models.**
   - The 65.1 vs 57.5 AlpacaEval result used 70B-141B proposers on an LLM-judged chat benchmark [MoA].
   - Resampling one strong model beats mixing in weaker ones: 65.7 vs 59.1 [SelfMoA].
   - Archon's critique and fusion steps are weak at 7B [Archon]. One unreliable member can drag MoA down: 49.2 to 37.9 [MoADeception].
8. **Several cited successful small-model systems emphasize selection.**
   - SLM-MUX picks the most self-consistent model [SLM-MUX].
   - Avengers routes using labeled calibration data and votes over 10 samples, averaging 70.54 vs GPT-4.1 69.20 [Avengers].
   - MAKER votes on micro-steps [MAKER].
9. **Repeated voting does not supply absent external evidence.**
   - The cited synthetic knowledge-capacity experiments reported about 2 bits per parameter under
     their setup; this is not a universal capacity law [Physics33].
   - Gemma 3 4B scores 4.0 on SimpleQA vs Gemini 2.0 Pro 44.3 [Gemma3].
   - Avengers loses on MedQA (73.89 vs 88.77) and GPQA (55.76 vs 62.05) [Avengers]. R1-Distill-7B scores 49.1 on GPQA vs 65.0 for Claude-3.5-Sonnet [R1].
10. **False acceptance changes the value of resampling.** The v3 resampling paper studies limits under
    imperfect acceptance and utility assumptions [fLaws]. It does not choose a universal attempt budget
    for a different verifier or task. Evaluate false positives and stronger-model baselines directly.
    The cited process-verifier/self-correction failures also concern their tested settings
    [ProcessBench][SelfCorrect][SmallVerifiers].
11. **Long decomposed runs have a concrete precedent.** MAKER's reported task supports further
    experiments [MAKER]; its given decomposition and error-correction assumptions do not establish
    general tiny-step reliability. Format/length checks are weaker than correctness checks. The cited
    Atom of Thoughts results concern different tasks and conditions [AoT].
12. **Multi-agent overhead is real.** With small models, multi-agent setups used 6.2x the tokens and completed 72.01% of runs vs 99.67% for the base model [RethinkScale]. The orchestrator's capacity mattered more than sub-agent size [SmallAgents].

**Research implications for Symblic's second goal:**
Short typed constructions with useful independent checks are promising evaluation targets. Preserve
open-ended and knowledge-heavy capabilities, while measuring their different assurance limits. Compare
single-model resampling, selection, discussion, deterministic tools and proof/source-witness construction
at matched information and cost. The cited successes/failures do not predetermine which strategy will
win on a new task or guarantee parity with a stronger model.

---

## 12. Design lessons for Symblic

1. **Separate construction from checking and supported computation.** Existing results motivate an
   exact-tool path; they do not require banning model-built solutions or moving every algorithm into
   bespoke kernel code. The new proof path lets a model construct while a generic checker validates:
   - PAL: 72.0 vs 65.6 on GSM8K, and about 7x lower standard deviation across prompt orderings (0.16 vs 1.10) [PAL].
   - SatLM: 69.4 vs 43.4 on GSM-Sys [SatLM].
   - Chain of Code: 95% vs 71% on algorithmic tasks [ChainOfCode].
   - ANVIL: all compiled cases took the deterministic path [ANVIL].
   - Route search-heavy, low-implicit-knowledge statements to the kernel, since solvers can hurt on shallow deduction [WhenSolvers][LogicLM].
2. **Translation/formalization were major failure points in the cited systems. Invest in grammar,
   diagnostics and independent intent-fidelity checks without presuming they are every task's dominant risk.**
   - LINC: "all errors have been localized to the semantic parsing procedure" [LINC].
   - Solver error feedback raised executable rates by 5.9-17.6 points in Logic-LM [LogicLM].
   - Arity and type errors recur, so reject them before execution [LINC][ImprovingSymbolic].
3. **Passing the checker does not mean capturing the intent.** Lean "compiles" overstates "faithful" by 3-29 points [BeyondCompilation]. State claims as "identical given the formal statements", and audit faithfulness separately.
4. **Temperature 0 does not establish determinism; provider parameter restrictions must be checked for the specific model.** 80 of 1000 completions were unique at T=0 [TML-nondet]; accuracy varied by up to 15% [Atil]; the historical survey reported HTTP 400 for non-default temperature on the Claude models it considered [Claude-thinking]. Record-and-replay is one reproducibility contract. Its identity must cover the complete request and pinned runtime: context serialization, definitions, model/provider settings, validator and adapter semantics, source modules and budgets. The earlier five-field sketch was not a sufficient cache-key specification; use the current [execution contract](EXECUTION-PINS.md).
5. **Pin and test the actual serving configuration before a bitwise repeatability claim.** The cited
   implementations identify relevant batching, build, hardware and runtime settings; these are historical
   implementation-specific observations, not a necessary-and-sufficient universal checklist
   [TML-nondet][vLLM-BI][SGLang-det][TBIK][llamacpp-server].
6. **Cross-model identity is an agreement rate. Report it, and separate format agreement from content agreement.**
   - Report raw, canonical and chance-adjusted agreement, in the style of Atil's TARr/TARa and CAPA [Atil][GreatModels].
   - Canonicalization alone recovers 6-8 F1 of cross-model gaps [PromptPort].
   - Specify and version canonicalization before hashing. RFC 8785 JCS [JCS] is prior art for JSON; Symblic uses its own tagged rational/set format and exact-text identity, and does not claim RFC 8785 compliance.
   - Treat provider quirks as versioned compatibility behavior [Claude-SO]. Record transformations;
     strict coercion refuses fuzzy matching rather than silently changing a candidate's spelling.
7. **Agreement is not correctness.** About 60% of shared wrong answers coincide across models [CorrErrors]. 48% of high-agreement frontier answers on GPQA were wrong [Ding]. Majority consensus among 4 LLMs did worse than the best single model on knowledge-graph extraction [XieKG]. Report encoded-predicate conformance separately from agreement and independently established target correctness. A passing ensure clause is only as adequate as its predicate and premises.
8. **Design output schemas to preserve the task's distinctions with explicit definitions.** Closed enums and exact values can simplify comparison; lower entropy is not an objective if it erases required information. The clinical example above illustrates that risk [Murin]. Structured SQL output stayed stable where RAG output drifted 25-75% in one study [FinDrift]; transfer to Symblic needs measurement.
9. **Compare construction and formatting strategies for each model/task.**
   - Format restriction cut Claude-3-Haiku's GSM8K from 86.5 to 23.4 [SpeakFreely].
   - Two-step NL-to-Format and grammars allowing reasoning improve the cited settings [SpeakFreely][CRANE]; they are not universal fixes. Count all stages in the budget.
   - Provider-supported reasoning or a separate candidate-construction step may help. The historical Claude refusal observation is version-specific [Claude-SO]; do not require a private-reasoning field or assume that any fixed sequence is best.
10. **Schema enforcement has a provider/engine-specific scope.** The historical coverage survey and
    provider restrictions are versioned observations [JSONSchemaBench][Claude-SO]. Refusal, truncation
    and unsupported schema features remain possible. Independently validate type/range/shape and the
    declared predicates; syntactic conformance does not establish semantic correctness.
11. **Compare explicit consolidated state with the context the task actually needs.**
    - Single-turn consolidated prompts recover 95.1% of performance vs a 39% multi-turn drop [Laban].
    - Long contexts degrade even when the needed fact is present [ContextRot][NoLiMa][LostMiddle].
    - Isolation loses implicit decisions unless they are written into state [Cognition][AnthHarness].
    - Keep the "all prior results" mode for statements that need history. Least-to-Most-style named prior results is the well-supported default [L2M].
    - [Task cards](TASK-CARDS.md) make declared dependencies and source identity inspectable. Full declared dependency closure is not proof of semantic sufficiency; test omissions, source-linked compression and fresh-reader transfer against a full-context baseline.
12. **Compare selection, resampling and mixed-model discussion at equal budgets.** The following results motivate baselines, not a universal rule that one strategy wins:
    - Majority voting accounts for most multi-agent gains [DebateOrVote], and debate among 7B models lowers accuracy [TalkCheap].
    - Self-MoA beats mixed MoA by 6.6 [SelfMoA].
    - Cross-model voting is worth it mainly where errors decorrelate, as in math [LLMJury]. For heterogeneous councils, weight members by measured per-statement accuracy.
13. **Measure the stopping policy.** The cited studies motivate bounded sampling and early stopping
    [LLMonkeys][MoreCalls][fLaws][MAKER][Aegean]. Choose budgets on development outcomes with explicit
    false-acceptance cost, then evaluate frozen choices on held-out tasks; no K≤5 optimum transfers
    automatically to Symblic.
14. **Use per-step red flags as cheap verifiers.** MAKER discarded overlong or malformed outputs before voting [MAKER]. Symblic's schema validation, length caps and kernel ensure clauses play the same role, and they can remove particular malformed or predicate-violating answers. Whether remaining errors decorrelate must be measured.
15. **For "the same flower", declare the required identity or equivalence.** A deterministic grammar yields identical plants; a stochastic one varies with the seed [ABOP]. Parameter extraction plus a renderer is useful, as AIDL illustrates [AIDL], but checked model-generated code or formal geometry are also legitimate construction paths. Pin execution/rendering versions, fonts and seeds; distinguish exact bytes, canonical geometry, finite test agreement and proved equivalence. The cited geometry/SVG weaknesses [SGPBench][VGBench][SVGenius] motivate baselines, not a permanent ban on model construction.

---

## 13. Defensible claims vs. overclaims (summary)

| Claim | Status |
|---|---|
| Kernel-evaluated statements have specified executable meaning | Scoped to equal inputs, semantic versions and successful bounded execution; conformance requires measured cases |
| Canonical values support comparison and compatible complete locks support replay | Versioned custom canonical form and SHA-256; integrity is not authentication, and missing/incompatible records fail |
| Cross-applicator agreement is measured and reported per statement | Implemented measurement feature; novelty not established |
| Judgment statements with finite canonical outputs reach high cross-model agreement | Empirical; must be measured per statement and model set |
| Any model produces identical output for any well-specified statement | Overclaim: not true even for one model at T=0 on shared serving [TML-nondet][Atil]; open-ended outputs diverge across models [XieKG][LeeRx] |
| Agreement across models shows the answer is correct | Overclaim [CorrErrors][Ding] |
| A formal essay yields the same flower from any agent | Identity requires a fully determined formal target and compatible execution, or an adequate uniqueness/equivalence check; fresh construction success and intent fidelity remain separate [ABOP][BeyondCompilation] |
| Councils of small local models approach large-model reasoning | Task- and budget-specific findings in prior work; no general Symblic parity or superiority result |

---

## 14. References

Historical reference list. The original survey reported opening these URLs unless marked UNVERIFIED; the version-2.1 update independently reopened only its stated primary comparators.

### LM programming and prompt languages
- [LMQL] Beurer-Kellner, Fischer, Vechev. Prompting Is Programming: A Query Language for LLMs. PLDI 2023. https://arxiv.org/abs/2212.06094
- [Guidance] guidance-ai/guidance. https://github.com/guidance-ai/guidance
- [llguidance] guidance-ai/llguidance. https://github.com/guidance-ai/llguidance
- [DSPy] Khattab et al. DSPy. ICLR 2024. https://arxiv.org/abs/2310.03714
- [DSPyAssert] Singhvi et al. DSPy Assertions. https://arxiv.org/abs/2312.13382
- [SGLang] Zheng et al. SGLang. NeurIPS 2024. https://arxiv.org/abs/2312.07104
- [Outlines] Willard, Louf. Efficient Guided Generation for LLMs. 2023. https://arxiv.org/abs/2307.09702
- [XGrammar] Dong et al. XGrammar. MLSys 2025. https://arxiv.org/abs/2411.15100
- [PDL] Vaziri, Mandel, Spiess, Hirzel. PDL: A Declarative Prompt Programming Language. 2024. https://arxiv.org/abs/2410.19135 ; follow-up https://arxiv.org/abs/2507.06396 ; https://github.com/IBM/prompt-declaration-language
- [PPDL] Mandel, Baudart, Vaziri, Hirzel. PPDL: LLM-Based Flows as Probabilistic Programs. 2026. https://arxiv.org/abs/2608.05234
- [POML] Zhang et al. POML. 2025. https://arxiv.org/abs/2508.13948
- [SudoLang] Elliott. SudoLang. https://github.com/paralleldrive/sudolang-llm-support
- [APPL] Dong et al. APPL. ACL 2025. https://arxiv.org/abs/2406.13161
- [BAML] BoundaryML. https://github.com/BoundaryML/baml ; https://boundaryml.com/blog/schema-aligned-parsing
- [TypeChat] Microsoft TypeChat. https://github.com/microsoft/TypeChat
- [Instructor] 567-labs/instructor. https://github.com/567-labs/instructor
- [MTP] Dantanarayana et al. MTP: Meaning-Typed Programming (byLLM/Jac). OOPSLA 2025. https://arxiv.org/abs/2405.08965
- [CoRE] Xu, Li, Mei, Zhang. AIOS Compiler: LLM as Interpreter for Natural Language Programming and Flow Programming of AI Agents. 2024. https://arxiv.org/abs/2405.06907 ; https://github.com/agiresearch/CoRE
- [RunAgent] Srivastava et al. RunAgent. 2026. https://arxiv.org/abs/2605.00798
- [CogBASIC] Kramer. Cognitive BASIC. 2025. https://arxiv.org/abs/2511.16837
- [Mellea] IBM Research. Mellea. https://github.com/generative-computing/mellea
- [Agentics2] Gliozzo, Lee, Defosse. Agentics 2.0: Logical Transduction Algebra for Agentic Data Workflows. 2026. https://arxiv.org/abs/2603.04241
- [SPL-CM] Gong. Structured Prompt Language: Declarative Context Management for LLMs. 2026. https://arxiv.org/abs/2602.21257
- [SPL-DP] Gong. SPL: Orchestrating Workflows with Declarative Deterministic-Probabilistic Composition. 2026. https://arxiv.org/abs/2607.07727
- [WaK] Quinto, Rozzi, Zanitti. Workflow as Knowledge: Semantic Persistence for LLM-Mediated Workflows. 2026. https://arxiv.org/abs/2607.08740
- [Pel] Mohammadi. Pel, A Programming Language for Orchestrating AI Agents. 2025. https://arxiv.org/abs/2505.13453
- [SK] Microsoft Semantic Kernel planning docs. https://learn.microsoft.com/en-us/semantic-kernel/concepts/planning
- [LangGraph] https://github.com/langchain-ai/langgraph
- [AIChains] Wu, Terry, Cai. AI Chains. CHI 2022. https://arxiv.org/abs/2110.01691
- [PromptChainer] Wu et al. PromptChainer. CHI 2022 LBW. https://arxiv.org/abs/2203.06566
- [LLMPrograms] Schlag et al. Large Language Model Programs. 2023. https://arxiv.org/abs/2305.05364
- [Promptware] Chen et al. Promptware Engineering. https://arxiv.org/abs/2503.02400
- [PromptsArePrograms] Liang et al. Prompts Are Programs Too! FSE 2025. https://arxiv.org/abs/2409.12447
- [ell] https://github.com/MadcowD/ell
- [Cognify] Cognify Module Ensemble docs. https://cognify-ai.readthedocs.io/en/latest/fundamentals/cog_basics/ensemble.html
- [AFlow] Zhang et al. AFlow. https://arxiv.org/abs/2410.10762
- [BlendSQL] Glenn, Samuel, Liu. Play by the Type Rules. 2025. https://arxiv.org/abs/2509.20208

### Controlled natural languages
- [Kuhn2014] Kuhn. A Survey and Classification of Controlled Natural Languages. Computational Linguistics 40(1), 2014. https://aclanthology.org/J14-1005 ; https://arxiv.org/abs/1507.01701
- [ACE] Attempto Controlled English. http://attempto.ifi.uzh.ch/site/description/
- [APE] https://github.com/Attempto/APE
- [LogicalEnglish] Kowalski, Datoo. Logical English meets legal English. AI and Law, 2021. https://doi.org/10.1007/s10506-021-09295-3
- [LE-AV] Sartor, Wyner, Contissa. 2025. https://arxiv.org/abs/2502.09216
- [CNL-P] Xing et al. CNL-P. 2025. https://arxiv.org/abs/2508.06942
- [CNL-KG] Bhandiwad et al. Knowledge-Based Systems, 2026 (Amazon Science page opened).
- [S4L] Zin et al. 2026. https://arxiv.org/abs/2609.20334

### Neurosymbolic reasoning and formal proof
- [PAL] Gao et al. PAL. 2022. https://arxiv.org/abs/2211.10435
- [PoT] Chen et al. Program of Thoughts. TMLR 2023. https://arxiv.org/abs/2211.12588
- [FaithfulCoT] Lyu et al. Faithful Chain-of-Thought. 2023. https://arxiv.org/abs/2301.13379
- [LogicLM] Pan et al. Logic-LM. Findings of EMNLP 2023. https://arxiv.org/abs/2305.12295
- [LogicLM++] Kirtania et al. 2024. https://arxiv.org/abs/2407.02514
- [LINC] Olausson et al. LINC. EMNLP 2023. https://arxiv.org/abs/2310.15164
- [SatLM] Ye et al. SatLM. NeurIPS 2023. https://arxiv.org/abs/2305.09656
- [SymbCoT] Xu et al. SymbCoT. ACL 2024. https://arxiv.org/abs/2405.18357
- [ChainOfCode] Li et al. Chain of Code. ICML 2024. https://arxiv.org/abs/2312.04474
- [LLMModulo] Kambhampati et al. LLMs Can't Plan, But Can Help Planning in LLM-Modulo Frameworks. ICML 2024. https://arxiv.org/abs/2402.01817
- [Valmeekam] Valmeekam et al. On the Planning Abilities of LLMs. NeurIPS 2023. https://arxiv.org/abs/2305.15771
- [LLM-ASP] Yang, Ishay, Lee. Coupling LLMs with Logic Programming. Findings of ACL 2023. https://arxiv.org/abs/2307.07696
- [PrologGen] Yang, Chen, Tam. Arithmetic Reasoning with LLM: Prolog Generation & Permutation. NAACL 2024. https://arxiv.org/abs/2405.17893
- [ProofOfThought] Ganguly et al. 2024. https://arxiv.org/abs/2409.17270
- [CLOVER] Ryu et al. Divide and Translate. ICLR 2025. https://arxiv.org/abs/2410.08047
- [WhenSolvers] He, Wang. When Do Symbolic Solvers Enhance Reasoning in LLMs? 2025. https://arxiv.org/abs/2512.03272
- [ImprovingSymbolic] Thatikonda et al. 2026. https://arxiv.org/abs/2601.09446
- [BeyondCompilation] Zhang et al. Beyond Compilation. 2026. https://arxiv.org/abs/2606.31002
- [AutoformEquiv] Li et al. Autoformalize by Symbolic Equivalence and Semantic Consistency. NeurIPS 2024. https://arxiv.org/abs/2410.20936
- [Autoformalization] Wu et al. Autoformalization with LLMs. 2022. https://arxiv.org/abs/2205.12615
- [DSProverV2] DeepSeek-Prover-V2. 2025. https://arxiv.org/abs/2504.21801
- [AlphaGeometry] Trinh et al. Nature 2024. https://deepmind.google/discover/blog/alphageometry-an-olympiad-level-ai-system-for-geometry/
- [AlphaGeometry2] Chervonyi et al. 2025. https://arxiv.org/abs/2502.03544
- [AlphaProof] Hubert et al. Nature 2025. https://research.google/pubs/olympiad-level-formal-mathematical-reasoning-with-reinforcement-learning/ ; https://deepmind.google/blog/ai-solves-imo-problems-at-silver-medal-level/
- [DeepThink] Google DeepMind, IMO 2025 gold. https://deepmind.google/discover/blog/advanced-version-of-gemini-with-deep-think-officially-achieves-gold-medal-standard-at-the-international-mathematical-olympiad
- [Vieira] Li et al. Relational Programming with Foundation Models. AAAI 2024. https://arxiv.org/abs/2412.14515
- [ANVIL] Patil et al. Where the LLM Ends and Reliable Decisions Begin. 2026. https://arxiv.org/abs/2609.19545
- [PlanCompiler] Harikumar. PlanCompiler. 2026. https://arxiv.org/abs/2604.13092
- [CompiledAI] Trooskens et al. Compiled AI. 2026. https://arxiv.org/abs/2604.05150

### Decomposition and context
- [L2M] Zhou et al. Least-to-Most Prompting. ICLR 2023. https://arxiv.org/abs/2205.10625
- [DecomP] Khot et al. Decomposed Prompting. ICLR 2023. https://arxiv.org/abs/2210.02406
- [Successive] Dua et al. Successive Prompting. 2022. https://arxiv.org/abs/2212.04092
- [SelfAsk] Press et al. 2022. https://arxiv.org/abs/2210.03350
- [CoA] Zhang et al. Chain of Agents. NeurIPS 2024. https://arxiv.org/abs/2406.02818 ; https://research.google/blog/chain-of-agents-large-language-models-collaborating-on-long-context-tasks/
- [AoT] Teng et al. Atom of Thoughts. 2025. https://arxiv.org/abs/2502.12018
- [RLM] Zhang, Kraska, Khattab. Recursive Language Models. https://arxiv.org/abs/2512.24601 ; https://alexzhang13.github.io/blog/2025/rlm/
- [LambdaRLM] Roy et al. The Y-Combinator for LLMs. 2026. https://arxiv.org/abs/2603.20105
- [MemGPT] Packer et al. MemGPT. https://arxiv.org/abs/2310.08560
- [SoT] Ning et al. Skeleton-of-Thought. ICLR 2024. https://arxiv.org/abs/2307.15337
- [ToT] Yao et al. Tree of Thoughts. NeurIPS 2023. https://arxiv.org/abs/2305.10601
- [GoT] Besta et al. Graph of Thoughts. AAAI 2024. https://arxiv.org/abs/2308.09687
- [BoT] Yang et al. Buffer of Thoughts. NeurIPS 2024. https://arxiv.org/abs/2406.04271
- [LostMiddle] Liu et al. Lost in the Middle. TACL. https://arxiv.org/abs/2307.03172
- [ContextRot] Hong, Troynikov, Huber. Context Rot. Chroma, 2025. https://www.trychroma.com/research/context-rot
- [NoLiMa] Modarressi et al. NoLiMa. ICML 2025. https://arxiv.org/abs/2502.05167
- [Laban] Laban et al. LLMs Get Lost in Multi-Turn Conversation. 2025. https://arxiv.org/abs/2505.06120
- [AnthCtxEng] Anthropic. Effective context engineering for AI agents. 2025. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- [AnthHarness] Anthropic (Young et al.). Effective harnesses for long-running agents. 2025-11-26. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- [AnthCtxMgmt] Anthropic. Context management. 2025. https://claude.com/blog/context-management
- [AnthMultiAgent] Anthropic. How we built our multi-agent research system. 2025. https://www.anthropic.com/engineering/multi-agent-research-system
- [CC-subagents] Claude Code sub-agents docs. https://code.claude.com/docs/en/sub-agents
- [Ralph] Huntley. Ralph Wiggum as a "software engineer". 2025-07-14. https://ghuntley.com/ralph/
- [Cognition] Yan. Don't Build Multi-Agents. 2025. https://cognition.com/blog/dont-build-multi-agents
- [Delethink] Aghajohari et al. The Markovian Thinker. 2025. https://arxiv.org/abs/2510.06557
- [InftyThink] Yan et al. InftyThink. https://arxiv.org/abs/2503.06692
- [PENCIL] Yang et al. PENCIL. ICML 2025. https://arxiv.org/abs/2503.14337
- [MEM1] Zhou et al. MEM1. 2025. https://arxiv.org/abs/2506.15841
- [ContextFolding] Sun et al. Context-Folding. 2025. https://arxiv.org/abs/2510.11967
- [IterResearch] Chen et al. IterResearch. 2025. https://arxiv.org/abs/2511.07327
- [MarkovChains] Geng et al. Markovian Generation Chains in LLMs. 2026. https://arxiv.org/abs/2603.11228

### Small models, ensembles, test-time compute
- [SC] Wang et al. Self-Consistency. ICLR 2023. https://arxiv.org/abs/2203.11171
- [USC] Chen et al. Universal Self-Consistency. 2023. https://arxiv.org/abs/2311.17311
- [MoreAgents] Li et al. More Agents Is All You Need. TMLR. https://arxiv.org/abs/2402.05120
- [MoreCalls] Chen et al. Are More LLM Calls All You Need? 2024. https://arxiv.org/abs/2403.02419
- [LLMonkeys] Brown et al. Large Language Monkeys. 2024. https://arxiv.org/abs/2407.21787
- [InfScaling] Wu et al. Inference Scaling Laws. 2024. https://arxiv.org/abs/2408.00724
- [Snell] Snell et al. Scaling LLM Test-Time Compute Optimally. 2024. https://arxiv.org/abs/2408.03314
- [Liu1B] Liu et al. Can 1B LLM Surpass 405B LLM? 2025. https://arxiv.org/abs/2502.06703
- [rStarMath] Guan et al. rStar-Math. 2025. https://arxiv.org/abs/2501.04519
- [LetsVerify] Lightman et al. Let's Verify Step by Step. https://arxiv.org/abs/2305.20050
- [ProcessBench] Zheng et al. ProcessBench. ACL 2025. https://arxiv.org/abs/2412.06559
- [fLaws] Stroebl, Kapoor, Narayanan. The Limits of Inference Scaling Through Resampling. v3, 2026-03-26 (earlier versions titled Inference Scaling fLaws). https://arxiv.org/abs/2411.17501v3
- [InverseTTC] Gema et al. Inverse Scaling in Test-Time Compute. https://arxiv.org/abs/2507.14417
- [s1] Muennighoff et al. s1. 2025. https://arxiv.org/abs/2501.19393
- [R1] DeepSeek-AI. DeepSeek-R1. https://arxiv.org/abs/2501.12948
- [R1-8B] DeepSeek-R1-0528-Qwen3-8B model card. https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B
- [MoA] Wang et al. Mixture-of-Agents. 2024. https://arxiv.org/abs/2406.04692
- [SelfMoA] Li et al. Rethinking Mixture-of-Agents. 2025. https://arxiv.org/abs/2502.00674
- [MoADeception] Wolf, Yoon, Bogunovic. 2025. https://arxiv.org/abs/2503.05856
- [Archon] Saad-Falcon et al. Archon. ICML 2025. https://arxiv.org/abs/2409.15254
- [Du-debate] Du et al. Multiagent Debate. 2023. https://arxiv.org/abs/2305.14325
- [MAD-Smit] Smit et al. Should we be going MAD? https://arxiv.org/abs/2311.17371
- [DebateOrVote] Choi, Zhu, Li. Debate or Vote. NeurIPS 2025. https://arxiv.org/abs/2508.17536
- [TalkCheap] Wynn, Satija, Hadfield. Talk Isn't Always Cheap. 2025. https://arxiv.org/abs/2509.05396
- [ReConcile] Chen, Saha, Bansal. ReConcile. ACL 2024. https://arxiv.org/abs/2309.13007
- [RethinkBounds] Wang et al. Rethinking the Bounds of LLM Reasoning. 2024. https://arxiv.org/abs/2402.18272
- [MAST] Cemri et al. Why Do Multi-Agent LLM Systems Fail? 2025. https://arxiv.org/abs/2503.13657
- [BenchForm] Weng, Chen, Wang. ICLR 2025. https://arxiv.org/abs/2501.13381
- [MemeticDrift] Tanaka. When Is Collective Intelligence a Lottery? 2026. https://arxiv.org/abs/2603.24676
- [SLM-MUX] Wang et al. SLM-MUX. 2025. https://arxiv.org/abs/2510.05077
- [Avengers] Zhang et al. The Avengers. 2025. https://arxiv.org/abs/2505.19797
- [SmallAgents] Żywot et al. Can Small Agents Collaborate to Beat a Single LLM? 2026. https://arxiv.org/abs/2601.11327
- [RethinkScale] Wang, Brorsson. Rethinking Scale. 2026. https://arxiv.org/abs/2604.19299
- [SLMJury] Laddha, Pradhan, Srivastava. SLMJury. 2026. https://arxiv.org/abs/2606.07810
- [CorrErrors] Kim, Garg, Peng, Garg. Correlated Errors in LLMs. ICML 2025. https://arxiv.org/abs/2506.07962
- [GreatModels] Goel et al. Great Models Think Alike. 2025. https://arxiv.org/abs/2502.04313
- [FrugalGPT] Chen, Zaharia, Zou. FrugalGPT. https://arxiv.org/abs/2305.05176
- [RouteLLM] Ong et al. RouteLLM. https://arxiv.org/abs/2406.18665
- [LLMBlender] Jiang, Ren, Lin. LLM-Blender. ACL 2023. https://arxiv.org/abs/2306.02561
- [SiliconCrowd] Schoenegger et al. Wisdom of the Silicon Crowd. 2024. https://arxiv.org/abs/2402.19379
- [SelfCorrect] Huang et al. LLMs Cannot Self-Correct Reasoning Yet. ICLR 2024. https://arxiv.org/abs/2310.01798
- [SmallVerifiers] Zhang et al. Small LMs Need Strong Verifiers to Self-Correct. 2024. https://arxiv.org/abs/2404.17140
- [Physics33] Allen-Zhu, Li. Physics of LMs 3.3. https://arxiv.org/abs/2404.05405
- [Gemma3] Gemma Team. Gemma 3 Technical Report. https://arxiv.org/abs/2503.19786
- [MAKER] Meyerson et al. Solving a Million-Step LLM Task with Zero Errors. 2025. https://arxiv.org/abs/2511.09030
- [LLMJury] Liu. LLMs as a Jury. 2026. https://arxiv.org/abs/2607.10139
- [Ding] Ding. When LLMs Agree, Are They Right? 2026. https://arxiv.org/abs/2607.08065
- [Aegean] Ruan et al. Reaching Agreement Among Reasoning LLM Agents. 2025. https://arxiv.org/abs/2512.20184
- [llm-council] Karpathy. llm-council. https://github.com/karpathy/llm-council
- [InspectableCouncil] Wu et al. An Inspectable LLM Council. 2026. https://arxiv.org/abs/2604.02923

### Determinism, structured outputs, agreement
- [TML-nondet] He et al. Defeating Nondeterminism in LLM Inference. Thinking Machines Lab, 2025-09-10. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
- [Atil] Atil et al. Non-Determinism of "Deterministic" LLM Settings. https://arxiv.org/abs/2408.04667
- [FP32] Yuan et al. Understanding and Mitigating Numerical Sources of Nondeterminism in LLM Inference. https://arxiv.org/abs/2506.09501
- [TBIK] Zhang et al. Tree-Based Invariant Kernels. 2025. https://arxiv.org/abs/2511.17826
- [LLM42] Gond et al. LLM-42. 2026. https://arxiv.org/abs/2601.17768
- [CrossGPU] Cooper et al. Accelerating the Mitigation of LLM Inference Nondeterminism Across GPU Architectures. 2026. https://arxiv.org/abs/2609.25624
- [TokenProbs] Fu et al. Beyond Reproducibility. 2026. https://arxiv.org/abs/2601.06118
- [Drift] Chen, Zaharia, Zou. How is ChatGPT's behavior changing over time? https://arxiv.org/abs/2307.09009
- [ModelEquality] Gao, Liang, Guestrin. Model Equality Testing. ICLR 2025. https://arxiv.org/abs/2410.20247
- [ChatGPT-codegen] Ouyang et al. Non-determinism of ChatGPT in code generation. https://arxiv.org/abs/2308.02828
- [Claude-glossary] Anthropic glossary. https://platform.claude.com/docs/en/docs/about-claude/glossary
- [Claude-thinking] Anthropic thinking docs. https://platform.claude.com/docs/en/build-with-claude/thinking
- [Claude-effort] Anthropic effort docs. https://platform.claude.com/docs/en/build-with-claude/effort
- [Claude-SO] Anthropic structured outputs. https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- [OAI-adv] OpenAI advanced usage (seed, system_fingerprint). https://developers.openai.com/api/docs/guides/advanced-usage
- [OAI-latest] OpenAI latest-model guide. https://developers.openai.com/api/docs/guides/latest-model
- [OAI-reasoning] OpenAI reasoning guide. https://developers.openai.com/api/docs/guides/reasoning
- [OAI-SO] OpenAI Structured Outputs. https://developers.openai.com/api/docs/guides/structured-outputs
- [Gemini-SO] Gemini structured output. https://ai.google.dev/gemini-api/docs/structured-output
- [vLLM-repro] https://docs.vllm.ai/en/latest/usage/reproducibility.html
- [vLLM-BI] https://docs.vllm.ai/en/latest/features/batch_invariance.html
- [SGLang-det] https://docs.sglang.io/advanced_features/deterministic_inference.html
- [llamacpp-server] https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md
- [GBNF] https://raw.githubusercontent.com/ggml-org/llama.cpp/master/grammars/README.md
- [Ollama-SO] Ollama structured outputs, 2024-12-06. https://ollama.com/blog/structured-outputs
- [JSONSchemaBench] Geng et al. 2025. https://arxiv.org/abs/2501.10868
- [SpeakFreely] Tam et al. Let Me Speak Freely? 2024. https://arxiv.org/abs/2408.02442
- [SayWhatYouMean] Kurt (dottxt). Say What You Mean. https://blog.dottxt.ai/say-what-you-mean.html
- [CRANE] Banerjee et al. CRANE. ICML 2025. https://arxiv.org/abs/2502.09061
- [GAD] Park et al. Grammar-Aligned Decoding. NeurIPS 2024. https://arxiv.org/abs/2405.21047
- [XieKG] Xie, Fang, Hu. LLMs build inconsistent knowledge graphs from one immune-checkpoint corpus. Frontiers in Immunology, 2026. https://pmc.ncbi.nlm.nih.gov/articles/PMC13529944/
- [LeeRx] Lee. Cross-Model Consistency of AI-Generated Exercise Prescriptions. 2026. https://arxiv.org/abs/2604.19598
- [Sarkar] Sarkar. How Reproducible Are Evaluation Conclusions? 2026. https://arxiv.org/abs/2609.30074
- [FinDrift] Khatchadourian, Franco. LLM Output Drift. 2025. https://arxiv.org/abs/2511.07585
- [SameOutcomes] Cui, Alexander. Same Prompt, Different Outcomes. 2026. https://arxiv.org/abs/2602.14349
- [PromptPort] Kotte. PromptPort. 2026. https://arxiv.org/abs/2601.06151
- [Murin] Murin. 2026. https://arxiv.org/abs/2606.05970
- [JCS] Rundgren, Jordan, Erdtman. RFC 8785 JSON Canonicalization Scheme. 2020. https://www.rfc-editor.org/rfc/rfc8785
- [SemEntropy] Farquhar, Kossen, Kuhn, Gal. Detecting hallucinations in LLMs using semantic entropy. Nature 630, 2024. https://pmc.ncbi.nlm.nih.gov/articles/PMC11186750/
- [SemUncertainty] Kuhn, Gal, Farquhar. Semantic Uncertainty. ICLR 2023. https://arxiv.org/abs/2302.09664
- [SemanticVote] Jiang, Yi, Zhu. Semantic Voting. 2026. https://arxiv.org/abs/2605.08680
- [StructuredSC] Xu, Huang, Zhang. Structured Self-Consistency. 2026. https://arxiv.org/abs/2602.00611

### Formal specification to artifact
- [Lindenmayer1968] Lindenmayer. Mathematical models for cellular interactions in development I and II. J. Theor. Biol. 18, 1968. https://doi.org/10.1016/0022-5193(68)90079-9 ; https://doi.org/10.1016/0022-5193(68)90080-5
- [ABOP] Prusinkiewicz, Lindenmayer. The Algorithmic Beauty of Plants. Springer, 1990. https://algorithmicbotany.org/papers/abop/abop-ch1.pdf
- [Vogel1979] Vogel. A better way to construct the sunflower head. Math. Biosci. 44:179-189, 1979. https://doi.org/10.1016/0025-5564(79)90080-4 (DOI from search result; definition verified via [MathWorld-Vogel])
- [MathWorld-Vogel] https://mathworld.wolfram.com/VogelSpiral.html
- [Infinigen] Raistrick et al. CVPR 2023. https://arxiv.org/abs/2306.09310
- [3DGPT] Sun et al. 3D-GPT. https://arxiv.org/abs/2310.12945
- [FloraForge] Hadadi et al. 2025. https://arxiv.org/abs/2512.11925
- [Scenic] Fremont et al. Scenic. PLDI 2019. https://arxiv.org/abs/1809.09310
- [CADRecode] Rukhovich et al. CAD-Recode. https://arxiv.org/abs/2412.14042
- [Text2CAD] Khan et al. Text2CAD. NeurIPS 2024. https://arxiv.org/abs/2409.17106
- [CADCodeVerify] Alrashedy et al. https://arxiv.org/abs/2410.05340
- [Query2CAD] Badagabettu et al. https://arxiv.org/abs/2406.00144
- [LLM4CAD] Li, Sun, Sha. ASME IDETC 2024. https://par.nsf.gov/biblio/10661832
- [CADCoder] Guan et al. CAD-Coder. NeurIPS 2025. https://arxiv.org/abs/2505.19713
- [CADmium] Govindarajan et al. TMLR 2026. https://arxiv.org/abs/2507.09792
- [BlenderLLM] Du et al. https://arxiv.org/abs/2412.14203
- [AIDL] Jones et al. AIDL. 2025. https://arxiv.org/abs/2502.09819
- [StarVector] Rodriguez et al. CVPR 2025. https://arxiv.org/abs/2312.11556
- [LLM4SVG] Xing et al. CVPR 2025. https://arxiv.org/abs/2412.11102
- [Chat2SVG] Wu, Su, Liao. CVPR 2025. https://arxiv.org/abs/2411.16602
- [OmniSVG] Yang et al. NeurIPS 2025. https://arxiv.org/abs/2504.06263
- [VGBench] Zou et al. EMNLP 2024. https://arxiv.org/abs/2407.10972
- [SVGenius] Chen et al. 2025. https://arxiv.org/abs/2506.03139
- [SGPBench] Qiu et al. Can LLMs Understand Symbolic Graphics Programs? ICLR 2025. https://arxiv.org/abs/2408.08313
- [AutomaTikZ] Belouadi, Lauscher, Eger. ICLR 2024. https://arxiv.org/abs/2310.00367
- [Pelicans] Willison. Pelicans on a bicycle. 2024-10-25. https://simonwillison.net/2024/Oct/25/pelicans-on-a-bicycle/
- [VISPROG] Gupta, Kembhavi. Visual Programming. CVPR 2023. https://arxiv.org/abs/2211.11559
- [ViperGPT] Surís, Menon, Vondrick. ICCV 2023. https://arxiv.org/abs/2303.08128
- [LMD] Lian et al. LLM-grounded Diffusion. TMLR 2024. https://arxiv.org/abs/2305.13655
- [VPGen] Cho, Zala, Bansal. NeurIPS 2023. https://arxiv.org/abs/2305.15328

### Not verified in this survey
- OpenAI Structured Outputs launch figures (100% vs <40% for gpt-4-0613): search snippet only; the launch blog returned HTTP 403.
- MAST failure-rate percentages; Archon call budget; the PRM used for each row in Liu et al. Table 3; rStar-Math trajectory budget behind the headline numbers: not confirmed on opened pages.
- Venues for some preprints (Successive Prompting, Atil et al., JSONSchemaBench, AIDL, Context-Folding) were not confirmed.
- Infinigen fixed-seed reproducibility: not stated in the README opened.
- Impromptu feature list: search snippet only.
