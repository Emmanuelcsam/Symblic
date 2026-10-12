# Symblic: Architectural Compendium

> **Speculative AI writing, revised.** Drafted by an AI model through Google's Antigravity agent and corrected by a
> later AI coding agent against the code; not reviewed by a human expert. See [../MADE-WITH-AI.md](../MADE-WITH-AI.md).

**Drafted by:** Antigravity (AGY), October 3, 2026. **Corrected:** October 4, 2026, against the live code.

**Historical baseline:** Symblic 2.4, canonical form 3, kernel `0b2cca3828a1965a`.
**Reform update:** 4 October 2026; deployment labels reconciled 5 October against the [5 October release evidence](evidence/2026-10-05-reform-install.json). Dated measurements below retain their original versions.

**Home Repository:** `the host checkout`

**Version note:** this text was checked against Symblic 2.4 (kernel `0b2cca3828a1965a`). It was installed with
Symblic 2.5 (kernel `83fa056574158e28`; [REFORM-3.md](REFORM-3.md)), which keeps `legacy` as the default
profile and adds `explicit` and `verified` profiles and a checker for supplied proof terms. Re-run under 2.5 on
2026-10-04, the code blocks, the Rosetta rows and the invoice variants behave as described here. Notes that
name 2.5 give the other changes found so far; the rest has not been re-checked against 2.5.

**Construction update (4 October 2026; installed in the 5 October reform):** `symblic/spec/contracts.py` and
`symblic/spec/build.py` add dependency-complete task cards for declared spec-sheet dependencies, branch-local
reuse, local rechecks and portable artifact manifests. `symblic/delegate/contracts.py` / `symblic/delegate/run.py`
expose bounded agent-callable construction templates through the existing runner. Flat proof certificates
are available through the proof checker and native bridge. The separate one-inference-at-a-time
session is also installed; [REFORM-3](REFORM-3.md) distinguishes its implementation evidence from
the historical measurements in this document. [RESEARCH-TRANSFER.md](RESEARCH-TRANSFER.md) maps them to research and explicit acceptance targets.

> **Status of this document.** [SPEC.md](SPEC.md) is the specification of what is built; this compendium
> summarises it and collects proposals made around it. Sections 1–8, 10 and 19 describe built behaviour, and
> §17, §18 and §21 explain the language and its visual identity. §9, §11–16, §20 and §22–29 are mostly
> proposals. [REVIEW-2.3.md](REVIEW-2.3.md) records what happened to each proposal in the nine documents it
> reviewed (built in a reduced form, already present, deferred, or rejected, with the reason), and those
> proposals below carry that outcome. REVIEW-2.3 did not review this compendium: the proposals it gives no
> outcome for (§9, §14, §15 items 1–3, §16) are marked built or not built from the code. The October 3 draft
> described several proposals as built and attached guarantees from physics and mathematics that do not hold.
> Those statements are corrected in place, not only disclaimed. No construction described here prevents
> hallucination or prompt injection, or makes model answers deterministic ([REVIEW-2.3.md](REVIEW-2.3.md),
> "Outcome").

---

## Table of Contents
1. [The Core Architecture & Separation of Concerns](#1-the-core-architecture--separation-of-concerns)
2. [Formal Symbolic Logic Foundation & Its Scope](#2-formal-symbolic-logic-foundation--its-scope)
3. [Controlled Natural Language & Bounded Contexts](#3-controlled-natural-language--bounded-contexts)
4. [File Types, Compilation & Runtime Pipeline](#4-file-types-compilation--runtime-pipeline)
5. [Language Reference & Syntax](#5-language-reference--syntax)
6. [Architectural Comparison: Symblic vs. Python & Other Languages](#6-architectural-comparison-symblic-vs-python--other-languages)
7. [Empirical Cluster Receipts: Local Model Capabilities & Limits](#7-empirical-cluster-receipts-local-model-capabilities--limits)
8. [Backend Architecture: Python Runtime & Native Kernel Tradeoffs](#8-backend-architecture-python-runtime--native-kernel-tradeoffs)
9. [Large Contexts & Codebases: Relational Fact Extraction (Proposal)](#9-large-contexts--codebases-relational-fact-extraction-proposal)
10. [Finite Quadratic Minimization & Symblic 2.2 Integration](#10-finite-quadratic-minimization--symblic-22-integration)
11. [High-Performance Computing (HPC) Execution & Distributed Scaling (Proposals)](#11-high-performance-computing-hpc-execution--distributed-scaling-proposals)
12. [HPC Training & Reinforcement Learning with Verifiable Rewards (RLVR) (Proposals)](#12-hpc-training--reinforcement-learning-with-verifiable-rewards-rlvr-proposals)
13. [Multi-frame checking: background](#13-multi-frame-checking-background)
14. [The Shippable Product Roadmap (Proposals)](#14-the-shippable-product-roadmap-proposals)
15. [Strategic Roadmap for Future Verification Extensions](#15-strategic-roadmap-for-future-verification-extensions)
16. [Possible Applications & Assurance Boundaries](#16-possible-applications--assurance-boundaries)
17. [How to Explain Symblic (Conceptual & Developer Summary)](#17-how-to-explain-symblic-conceptual--developer-summary)
18. [Focused Minimalist Visual Identity](#18-focused-minimalist-visual-identity)
19. [CLI Command Reference](#19-cli-command-reference)
20. [Symblic and Human Intersubjectivity: Background and Proposals](#20-symblic-and-human-intersubjectivity-background-and-proposals)
21. [Expanded Minimalist Formal Logic Icon Suite](#21-expanded-minimalist-formal-logic-icon-suite)
22. [Intersubjective & Epistemic Proposals for the Core: Outcomes](#22-intersubjective--epistemic-proposals-for-the-core-outcomes)
23. [Theoretical and Systems Critique of Symblic, Checked Against the Code](#23-theoretical-and-systems-critique-of-symblic-checked-against-the-code)
24. [Adversarial Critique: Proof Theory, Information Flow and Effects, Checked Against the Code](#24-adversarial-critique-proof-theory-information-flow-and-effects-checked-against-the-code)
25. [Quantum Mathematics and Symblic (Q-Symblic): Proposals and What Was Built](#25-quantum-mathematics-and-symblic-q-symblic-proposals-and-what-was-built)
26. [Quantum Mechanics and Computational Determinism: What Is Deterministic in Symblic](#26-quantum-mechanics-and-computational-determinism-what-is-deterministic-in-symblic)
27. [Mathematical Physics: The September 2026 Navier-Stokes Announcement and Physics Proposals](#27-mathematical-physics-the-september-2026-navier-stokes-announcement-and-physics-proposals)
28. [Analogies from Higher Physics and Mathematics: Proposals and Outcomes](#28-analogies-from-higher-physics-and-mathematics-proposals-and-outcomes)
29. [The "Universal Epistemic Operating System" Proposal: Status](#29-the-universal-epistemic-operating-system-proposal-status)
30. [References](#references)

---

## 1. The Core Architecture & Separation of Concerns

Traditional software engineering and artificial intelligence face distinct structural trade-offs:

1. **Deterministic computation** gives the same result under its declared inputs, semantics and execution
   conditions. Python, C++ and Rust can also express randomness, concurrency and external effects; a program
   in any of them can contain a wrong formula or fabricated constant. Binary floating-point arithmetic
   rounds: `0.1 + 0.2` is `0.30000000000000004`. Rust and C++ check
   declared types when compiling; Python's type annotations are not enforced at run time. Ordinary procedural
   code cannot read unstructured prose or judge subjective nuance without heuristic glue.
2. **Generative AI (large language models)** is good at interpreting natural language. It also produces fluent
   wrong answers ("hallucinations"), does worse as inputs and conversations grow long (context rot, §3), makes
   arithmetic slips, and loses track over several reasoning hops. Its outputs can differ between runs even at
   temperature 0 on shared serving infrastructure ([PRIOR-ART.md](PRIOR-ART.md) [TML-nondet], [Atil]).

**Symblic is a neuro-symbolic domain-specific language (DSL)** that keeps these two parts separate:

Models can interpret inputs **and construct code, proofs, encodings and numerical witnesses**. General
checkers validate those artifacts against caller-owned contracts before commitment. Direct exact computation
remains available when it is the efficient route. A new application should supply its task and obligations;
it should not require adding its entire solution algorithm to the trusted kernel.

- **The deterministic kernel** (`symblic/kernel/language.py`, pure Python, no I/O): exact rational arithmetic (`1/3 * 3 = 1`;
  `0.1 + 0.2 = 0.3`), Boolean logic with English or Unicode operators, quantifiers over finite collections,
  sets, lists, records, Datalog facts and rules, exact 3D polyhedra (`symblic.adapters.geometry`), deterministic SVG
  drawings, and bounded exact adapters: the quadratic minimizer of §10 (since 2.2) and, since 2.3, the
  Wasserstein-1 distance, exhaustive Ising ground states (at most 16 spins), Aumann's partition model (at most
  64 states), least-change reconciliation with linear constraints, and rational projectors ([SPEC.md](SPEC.md)
  §7). Transcendental functions (`sin`, `exp`, `sqrt` of a non-square) are deterministic 30-place Decimal
  approximations, not exact reals. No kernel builtin calls a model. The 2.4 JavaScript adapter (`js_test`,
  `js_run`) runs code in a fresh sandboxed V8 context, also without a model ([JS.md](JS.md)).
- **The applicators** (among them the Claude, Codex, AGY and Copilot CLIs; Ollama models on the worker nodes; ChatGPT
  and Gemini through the browser daemon; [SPEC.md](SPEC.md) §6 lists all engines): an `ask` statement sends one
  typed question. The answer type compiles to JSON Schema, and the capsule asks for a JSON reply whose answer
  has that type. The Claude, Codex and AGY CLIs also receive the schema through their schema flags, and Ollama
  as its `format`; Copilot and the browser engines (ChatGPT, Gemini) receive no schema, and their JSON is read
  from the reply text. The kernel checks every reply against the type ([SPEC.md](SPEC.md) §3, §4, §6). A 2.4
  `Code` answer sends no schema; the kernel takes the reply's last fenced code block. A reply that fits its type
  can still be wrong.
- **Transactional retries:** when an `ensure ... else retry` check fails, the run's state is restored to the
  snapshot taken when the anchor ask started (bindings, facts, rules, outputs and the rest), and the ask runs
  again with feedback that names the rejected value and the failed condition. Without a `because`, the
  feedback also carries the kernel's values for the parts of the check that depend on the answer alone.
  Retries are capped (`retries`, default 2, at most 5). An `act` between an ask and a check that may re-ask it
  is refused, so a retry never has to undo an external action ([SPEC.md](SPEC.md) §5).

---

## 2. Formal Symbolic Logic Foundation & Its Scope

Symblic's kernel uses standard formal logic, finite model theory and programming-language practice. What each
part gives, and what it does not, is stated below.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FORMAL SYMBOLIC LOGIC IN SYMBLIC                │
└────────────────────────────────────────────────────────────────────────┘
                                    │
  ┌─────────────────┬───────────────┴───────────────┬──────────────────┐
  ▼                 ▼                               ▼                  ▼
1. Finite         2. Horn Logic (Datalog)        3. Quantifiers       4. Types
   structures:       Stratified fixpoints;          over finite          Schemas as
   canonical         closed-world negation          collections:         specifications
   values                                           ∀, ∃, ∧, ∨, ¬, →, ↔  (Analogy to C-H)
```

### The Formal Logic Pillars & Their Strict Boundaries:

1. **Finite Structures & Canonical Values:**
   - *What the mathematics says:* every finite structure over a finite vocabulary is described up to
     isomorphism by one first-order sentence. The sentence names n distinct elements, says there are no
     others, and lists exactly which tuples each relation holds on. This is an elementary fact of finite model
     theory. (The draft attributed it to a "Dawar finite categoricity theorem", a name that could not be
     traced to a source; the fact is elementary and needs no attribution.)
   - *What Symblic implements:* a canonical serialization of values (`symblic.canon`, canonical form 3). Sets
     are sorted, record keys are sorted, non-integer rationals are written `p/q`, and a fingerprint is the
     first 16 hex digits of SHA-256 over the canonical JSON. Equal values therefore give equal bytes under the
     same kernel identity. A conformance receipt found the same output bytes on 3 hosts × 9 hash-seed and
     Decimal profiles for a fixed corpus ([RESULTS.md](RESULTS.md), "Fixed-corpus conformance"). This is a
     property of the serializer, tested on that corpus. It does not follow from the logical fact above. Exact
     polyhedra have their own canonical form (`symblic.adapters.geometry`).
   - *What it does NOT establish:* that a model extracted the right structure from a text.
2. **Restricting Types to `Bool` or Enums:**
   - Restricting an output to `Bool` or `one of {A, B}` restricts the answer to 2 or $N$ values. A reply
     outside the set is refused; enum matching ignores case, spacing and punctuation ([SPEC.md](SPEC.md) §3).
   - *Crucial boundary:* This does **not** guarantee correct semantic interpretation. Two valid boolean values
     exist (`true` and `false`). An LLM can confidently output `true` when the ground truth is `false`.
     Restricting to finite types bounds the answer set, but does not solve perceptual error.
3. **Datalog & Horn Clause Logic:**
   Symblic embeds Datalog: ground facts, range-restricted Horn rules, and stratified closed-world negation. A
   program whose rules depend on themselves through `not` is refused at run time. The kernel computes the
   standard model by naive bottom-up iteration of the immediate-consequence operator, one stratum after
   another ($T_P \uparrow \omega$ per stratum; van Emden & Kowalski 1976; Apt, Blair & Walker 1988 for
   stratified negation). For pure Datalog and a fixed program, the number of derived facts and rounds is
   polynomial in the number of facts (Vardi 1982). Two limits matter in practice:
   - **Rules may compute values** (`N = A + 1` binds `N`), which takes a program outside pure Datalog. Such a
     program can derive facts without end; the kernel stops it at 10 000 rounds per stratum, 200 000 facts or
     the 200 000-step budget, whichever comes first.
   - **Evaluation is naive:** every rule is re-run over all facts in each round, scanning whole relations
     without an index, and every scanned fact costs a budget step. Measured on the host (a 6-core desktop CPU, under load): the transitive closure of a 25-edge chain
     (325 derived pairs) took 0.57 s; a 30-edge chain (465 pairs) ran out of the default step budget; with the
     budget raised to 5 000 000 steps (a `Run` option; `tools/symblic` has no flag for it) a 50-edge chain (1 275
     pairs) took 8.2 s.

   Negation is closed-world: `not p(...)` means "absent from the derived relation", not "false in the world"
   ([SPEC.md](SPEC.md) §7).
4. **Quantifiers and Connectives:**
   `all x in xs: p`, `any x in xs: p`, `none x in xs: p`, and the symbols
   $\forall, \exists, \neg, \land, \lor, \to, \leftrightarrow, \in, \notin, \subseteq, \cup, \cap, \setminus$.
   Quantifiers range over finite collections the program holds and are evaluated by iterating over them. This
   is evaluation over finite data, not first-order theorem proving over unbounded domains. `⊂` is accepted,
   but it means the same as `⊆` (non-strict): `{1, 2} ⊂ {1, 2}` is `true`.
5. **Types as Specifications (Curry-Howard Analogy):**
   In Symblic, declared types act as contracts: an applicator's output is admitted only if it parses as that
   type and passes the checks anchored to it. This is a design analogy to Curry-Howard type checking; Symblic
   2.4 is an interpreted execution runtime, not a constructive dependent proof assistant with proof terms
   (such as Lean 4 or Coq). Symblic 2.5 adds `proof_check` and related builtins. They check proof terms that
   a person or a model supplies, in intuitionistic propositional natural deduction, with quantifiers only over
   explicitly listed finite domains (`finite_check`). They check a derivation and do not search for one, and
   admitting a typed answer is still not a proof that it is right ([PROOF-TERMS.md](PROOF-TERMS.md),
   [FINITE-LOGIC.md](FINITE-LOGIC.md)).
6. **The Symbol Grounding Boundary:**
   In formal semantics, a model is defined as $\mathcal{M} = \langle \mathcal{D}, \mathcal{I} \rangle$, where
   $\mathcal{D}$ is the domain and $\mathcal{I}$ is the interpretation function. Symblic couples a model
   applicator that maps text to typed values (loosely, $\mathcal{I}: \text{Text} \to \text{Symbols}$) with a
   kernel that evaluates expressions and derives Datalog facts. The 2.5 proof lane also checks supplied
   derivations in a named intuitionistic fragment: there, $\Gamma \vdash \phi$ names a formal judgment
   conditional on caller-held premises. A typed extraction alone is not such a derivation. This architecture structures and records the interface between model
   interpretation and exact computation; it does not solve the Symbol Grounding Problem (Harnad 1990).

---

## 3. Controlled Natural Language & Bounded Contexts

### The Controlled Natural Language (CNL) Architecture
- **Direction of Fit:** Natural language is used for semantic queries (`"What is the customer's sentiment?"`).
  Strict types are enforced for return values (`one of {delighted, neutral, furious}`). Symblic's statements
  use English keywords but follow a fixed formal grammar; free natural language appears in an ask's quoted
  instruction and in prose lines, which become asks ([SPEC.md](SPEC.md) §1).
- **Context Capsules:** Long inputs and long multi-turn conversations degrade model performance (Chroma's
  "Context Rot", 2025; NoLiMa, ICML 2025; Laban et al. 2025; [PRIOR-ART.md](PRIOR-ART.md) [ContextRot],
  [NoLiMa], [Laban]). Symblic carries no chat history between asks: each `ask` is a fresh call whose capsule
  is rebuilt from the program's formal state. What the capsule holds is the author's choice: `context=none`
  (the default: only the names given with `from`), `last N`, `relevant` (the 6 known items with the most word
  overlap), `facts`, `all`, or an explicit list. Known items are packed by weight into a character budget
  (default 12 000), and the capsule says how many were left out ([SPEC.md](SPEC.md) §4). In 2.5, names given
  with `from` or in an explicit list must fit whole, or the ask fails before any call. This avoids accumulated
  history. It does not protect a long `from` source from the same degradation, and passing too little context
  starves the model (§23).
- *Interpretation Boundary:* Clark & Brennan (1991) describe communication as a joint process of establishing
  enough mutual understanding for the task ("grounding"). Controlled languages such as Attempto Controlled
  English fix one reading through explicit interpretation rules. A controlled parse removes a syntactic
  ambiguity; it does not show that the reading is the one the author intended. That takes testing and feedback
  ([PRIOR-ART.md](PRIOR-ART.md), [EVIDENCE.md](EVIDENCE.md)).

### The 4-Step Translation Method
1. **Inputs (`given` / `observe`):** values given to the program (text, numbers, records), and observations
   read through capabilities the host declares (a calendar, a sensor), with their provenance recorded.
2. **AI Interpretation (`ask`):** a typed answer. Closed types (`Bool`, `one of {...}`, small `Int` ranges,
   records of those) bound the set of answers; open types (`Text`, `Number`, lists, `Code`) do not.
3. **Guardrails (`ensure ... else retry`):** Programmatic invariants that reject structurally invalid or
   contradictory outputs.
4. **Exact Computation (`let` / `function` / Datalog):** Mechanically evaluated operations executed entirely in
   the Kernel with zero model calls.

### The Rosetta Stone

| Plain English Intent | Conventional Prompt Pattern | Symblic Implementation |
|---|---|---|
| *"Assume the invoice is $120"* | "Input: $120" | `given invoice: Number = 120.` |
| *"Calculate a 15% tip"* | "What is a 15% tip on $120?" | `let tip = invoice * 15 / 100.` *(exact: 18)* |
| *"Is this review positive or negative?"* | "Answer positive or negative" | `ask s: one of {positive, negative} "Classify" from review` *(`text` is a builtin name and cannot name an input)* |
| *"Extract customer name and phone"* | "Return JSON with name and phone" | `define Lead as Record {name: Text, phone: Text}.`<br>`ask lead: Lead "Extract" from raw` |
| *"Ensure name appears in the source"* | "Please double check your answer" | `ensure contains(raw, lead.name) else retry.`<br>*(stricter: `quotes(raw, lead.name)` needs whole words and the same case)* |
| *"Find everyone managed by Alice"* | "List all downstream reports" | `rule reports(X, Y) if direct(X, Y).`<br>`rule reports(X, Z) if direct(X, Y) and reports(Y, Z).`<br>`let team = query reports(alice, Who).` |

---

## 4. File Types, Compilation & Runtime Pipeline

### File Types:
1. **`.sym` (Symblic Source File):** Standard code file (e.g. `examples/04-family-logic.sym`,
   `symblic/lang/library/units.sym`).
2. **`.symd` (Symblic Literate Document / Paper):** Markdown with embedded executable ```` ```symblic ````
   blocks (examples in `docs/reference/papers/`).
3. **`run.lock.json` (Execution Lockfile):** a finished run frozen into one file: the program's SHA-256,
   inputs, options (including seeds), imported module sources, each statement's fingerprint, and the recorded
   model replies. Replay serves those replies through an applicator that refuses every other call, so it asks
   no model. A lock is refused for different program text, inputs or options, or under a different kernel
   identity ([SPEC.md](SPEC.md) §8, `symblic/kernel/lockfile.py`).

### Compilation & Execution Pipeline:
```
                  ┌───────────────────────────────┐
                  │      SOURCE CODE (.sym)       │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│ 1. SPLITTER & TOKENIZER (split_statements, tokenize)              │
│    • Recognizes English keywords & Unicode logic (∧, ∨, ¬, →, ∈)  │
│    • A line that is no statement and no formal expression is      │
│      prose: it becomes a Text ask (so pseudo-code passes check)   │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│ 2. PARSER (symblic.Parser)                                        │
│    • Line-based statements; recursive descent for expressions     │
│    • One AST class, Node, whose kind is let, ask, ensure, fact,   │
│      rule, function, routine, ...                                 │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│ 3. STATIC CHECKER (symblic.check)                                 │
│    • Names, scopes and type compatibility                         │
│    • Single assignment: a name is bound once per scope            │
│    • A predictability score (0-100) per ask: a guide from the     │
│      text alone, not a probability, not validated                 │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│ 4. EXECUTION (symblic.kernel.run.Run)                                    │
│    ┌─────────────────────────┐     ┌────────────────────────────┐ │
│    │ DETERMINISTIC KERNEL    │     │ MODEL APPLICATOR (AI)      │ │
│    │ • Exact rational math   │     │ • Type -> JSON Schema      │ │
│    │ • Datalog engine        │     │   (none for Code answers)  │ │
│    │ • Exact adapters, incl. │     │ • Builds the capsule       │ │
│    │   the quadratic solver  │     │ • CLIs and Ollama via      │ │
│    │ • Pure functions        │     │   fleet_runner on worker nodes;  │ │
│    │   (no model call)       │     │   ChatGPT/Gemini via the   │ │
│    └────────────┬────────────┘     │   browser daemon           │ │
│                 │                  └─────────────┬──────────────┘ │
│                 ▼                                ▼                │
│    ┌─────────────────────────────────────────────────────────┐    │
│    │ 5. CHECKS, RETRIES & FINGERPRINTS                       │    │
│    │    • evaluate ensure checks                             │    │
│    │    • on failure: restore the snapshot, re-ask with the  │    │
│    │      rejected value and the failed condition            │    │
│    │    • every binding and output gets a fingerprint (16    │    │
│    │      hex digits of SHA-256 over canonical JSON); the    │    │
│    │      run's fingerprint hashes them in order             │    │
│    └─────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────┘
```

In 2.5 a prose line still passes `check` under the default profile, now with a warning ("implicit prose executes
a model call; write an explicit typed ask"), and the `explicit` and `verified` profiles refuse it.

Fingerprints are compact comparison keys, not signatures or collision-free proofs ([SPEC.md](SPEC.md) §3).

---

## 5. Language Reference & Syntax

This is a summary; [SPEC.md](SPEC.md) is the complete reference.

### Exact Rational Arithmetic
```symblic
program ExactMath.
let x = 0.1 + 0.2.
assert x = 0.3 because "exact decimal rationals, no 0.30000000000000004 bugs".

let fraction = 1 / 3.
assert fraction * 3 = 1.
```

### The Type System
- `Int`, `Int in 0..100` (bounded integers)
- `Number`, `Number in 0..1`, `Number to 2 places` (exact rationals)
- `Bool` (`true`, `false`)
- `Text`, `Text up to 50 words` (Unicode NFC, line endings unified, outer white space removed)
- `one of {red, green, blue}` (strict enums; options may carry definitions)
- `List of T length N` or `length a..b` (indexed from 1)
- `Set of T` (unique mathematical sets)
- `Record {k: T, ...}` (key-value structures)
- `Svg`, `Any`, and (2.4) `Code`, optionally with a language: `Code js`, `html`, `css`, `python`, `json`,
  `sql` or `sh`

### The Model Bridge (`ask`)
Grammar specification:
```text
ask name: Type "instruction {expr}" [for each v in xs] [from a, b] [by app] [with options]
```
**Options** (the main ones; [SPEC.md](SPEC.md) §4 has all of them):
- `effort=low | medium | high | max | ultra`: answer only; reason then answer (default); 3 votes; 5 votes;
  5 votes and then one round in which each applicator sees the anonymised candidates
- `votes=N` (self-consistency sampling; at most 25): for local models, sample 0 runs at temperature 0 and the
  others at 0.7 with their own seeds; cloud CLIs take no temperature
- `context=none | last N | relevant | facts | all | [a, b]` (default `none`: only the `from` names)
- `by=applicator` (e.g. `claude:haiku`, `codex`, `ollama:qwen3:4b-instruct@node-a`), a list, or a group
- `route=escalate`: try applicators in the declared order and accept the first answer that passes the ask's
  anchored checks; failed attempts are not votes. `route=search` (2.4): checked candidates in parallel
  (`samples` up to 25, `rounds` up to 20)
- `families=N`, `permute=K`, `vote=median` with `within=T`, `retries=N`, `solve`, `ambiguous`, `examples`

### Datalog Horn Clauses
```symblic
fact parent(ada, ben).
fact parent(ben, cleo).

rule ancestor(X, Y) if parent(X, Y).
rule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).

let cleo_ancestors = query ancestor(Who, cleo).
# Result: ["ada", "ben"], computed in the Kernel
```

### Functions vs. Routines
```symblic
# Pure Kernel function: no model call, deterministic
function c_to_f(c: Number) -> Number = c * 9 / 5 + 32.

# Reusable model procedure: within one run, the same arguments reuse the memoised answer
routine sentiment_of(text: Text) -> one of {pos, neg, neu} with effort=high do
    ask s: one of {pos, neg, neu} "Analyze sentiment: {text}"
    return s.
end.
```

### Tutorial Verification Examples

#### Spider Study (Math + Bounded Fact)
```symblic
program SpiderStudy.
note The kernel computes math; the model supplies domain facts.

let legs_per_side = 4.
let total_legs = legs_per_side * 2.

ask spider_legs: Int in 0..20 "How many legs does a spider have?" with effort=low
ensure spider_legs = total_legs else retry because "spiders have 4 pairs of legs".

show [total_legs, spider_legs] as "verified_agreement".
```

#### Invoice Extraction
```symblic
program InvoiceParser.

given raw_invoice: Text = """
INVOICE #INV-4921
Vendor: Apex Cloud Services
Items: 4x Pro Server Instances ($50 each), 1x Setup Fee ($25)
Total: $225
"""

define LineItem as Record {name: Text, quantity: Int, unit_price: Number}.
define Invoice as Record {invoice_id: Text, vendor: Text, items: List of LineItem, reported_total: Number}.

ask parsed: Invoice "Extract invoice information." from raw_invoice with effort=high

# Arithmetic consistency, checked in the Kernel:
let calculated_total = sum([item.quantity * item.unit_price for item in parsed.items]).
ensure calculated_total = parsed.reported_total else retry because "line items do not add up to total".

show parsed as "verified_invoice".
```

This check establishes internal consistency only. A fabricated answer with one item of quantity 1, unit price
1 and total 1 passes it, and so does an empty item list with total 0; `check` warns about the second
(`SYM_VACUOUS`). Grounding the numbers in the text closes part of the gap. In the program above, replace the
`Invoice` definition with the first line below and add the three checks after the first `ensure`:

```symblic
# Fragment: changes to InvoiceParser above, not a standalone program.
define Invoice as Record {invoice_id: Text, vendor: Text, items: List of LineItem length 1..50, reported_total: Number}.
ensure parsed.reported_total in numbers(raw_invoice) else retry because "the total must be a number written in the invoice".
ensure all item in parsed.items: item.unit_price in numbers(raw_invoice) else retry because "each unit price must be written in the invoice".
ensure quotes(raw_invoice, parsed.vendor) else retry because "the vendor must be copied from the invoice".
```

With these added, the fabricated and empty answers are rejected. An answer with one item of quantity 1 at
225 still passes: each number is written in the invoice, but nothing checks which line it belongs to
([SPEC.md](SPEC.md) §7, §11).

---

## 6. Architectural Comparison: Symblic vs. Python & Other Languages

| Feature / Dimension | Symblic 2.4 | Python (Standard Library) | Python AI Frameworks (LangChain / DSPy) | Logic Languages (Prolog / Datalog) | Systems Languages (Rust / C++) |
|---|---|---|---|---|---|
| **Primary Purpose** | **Neuro-Symbolic DSL** | General-purpose scripting & data science | Chaining prompts & tool orchestration | Relational and logical programming | Systems programming & high-performance computing |
| **Model Integration** | **Native first-class keyword** (`ask`) | External SDKs and HTTP clients | Library classes (`dspy.Predict`, `Chain`) | None | External HTTP/C bindings |
| **Arithmetic Precision** | **Exact rationals by default** ($0.1+0.2=0.3$); transcendental functions as 30-place Decimal approximations | IEEE-754 Floats (`fractions` available) | IEEE-754 Floats | Floats / Integers | IEEE-754 Floats |
| **Multi-Hop Logic** | **Built-in Datalog** (`fact`, `rule`, `query`); small recursive programs (§2) | Manual algorithms or external graph libs | LLM multi-step reasoning (unverified) | **Native first-class engine** | Manual graph data structures |
| **Context Management** | **Capsule rebuilt per ask** from author-chosen context (`from`, `context=`) | Manual string formatting | Program-controlled; DSPy builds each module's prompt from its signature; chat-memory components accumulate history | N/A | Manual buffer handling |
| **Self-Correction & Errors** | **Transactional, bounded retries** (`ensure ... else retry`) | `try/except` with manual state recovery | Validate-and-repair loops (DSPy Assertions / Refine, Instructor) | Backtracking search | `Result<T, E>` / Exceptions |
| **Multi-Model Consensus** | **Built-in voting across applicators**: agreement, entropy, families by lineage; agreement is not correctness | Must write custom `asyncio` logic | Limited (`dspy.majority`, one model) | None | Must write multi-threaded clients |
| **Deterministic Replay** | **Hash-pinned lockfiles** (`run.lock.json`): recorded replies, no model call; not signed | Non-deterministic across model runs | Non-deterministic across model runs | Deterministic | Deterministic |
| **Execution Speed** | Interpreted Python: about 1 ms to `check` a 6-line program and 2–6 ms for small in-memory runs on the host; a 32×32 exact solve 0.35 s; recursive Datalog slows quickly (§2). Runs with asks are dominated by model time | Interpreted bytecode | Python plus model latency | Depends on the engine (not measured here) | Compiled native code |

Sources for the framework columns: [PRIOR-ART.md](PRIOR-ART.md) (DSPy, DSPy Assertions, validate-and-repair
loops). Symblic timings: measured 2026-10-04 in an isolated copy of the 2.4 sources (§8).

---

## 7. Empirical Cluster Receipts: Local Model Capabilities & Limits

These receipts come from [RESULTS.md](RESULTS.md) and [SPEC-SHEETS.md](SPEC-SHEETS.md). Receipts 1 and 2 are
historical (version 2.0, 2026-10-02; the operator paused that benchmark with 512 results saved). Models: Claude
Haiku, Claude Sonnet and Codex in the cloud; qwen3:4b, llama3.2:1b, gemma3:4b and phi4-mini on the worker nodes'
CPUs. Samples are small; read each receipt with its limits.

### 1. Multi-Hop Relational Logic (Family Trees, 15-Task Evaluation)
- **Design:** in the Symblic arm the model only extracts `parent(...)` facts from a shuffled story, and Datalog
  rules derive the answer. In the direct arm the model reasons the answer itself.
- **qwen3:4b (worker node CPU):** direct 9 / 15 (60%), Symblic + Datalog 12 / 15 (80%); median time 296 s → 96 s.
  RESULTS.md names a shorter answer (a list of facts instead of a chain of reasoning) as a likely reason for the
  speed-up, though answer lengths were not measured, and reports that with correct rules every remaining error
  was an extraction error.
- **llama3.2:1b:** 0 / 15 → 3 / 15 (20%), median time 26 s → 60 s (slower).
- **Claude Haiku:** 15 / 15 in both arms, 13 s → 9 s.
- **Limits:** one run, 15 generated items, no significance test reported. For a net gain of 3 items, an
  exact paired (McNemar) test gives at best a two-sided p of 0.25, so the gain is not distinguishable from
  chance at this size. The arms differ in what the model must produce, so the receipt supports "extraction plus
  kernel derivation worked better here", not a general causal effect.

### 2. Multi-Model Local Councils & Consensus Limits
- **Task:** 24 generated arithmetic word problems in the style of GSM-Symbolic (Mirzadeh et al. 2024).
- **Council of 5× `qwen3:4b`** across worker nodes, typed answer, 5 votes: **18 / 18** completed cells correct
  (median 121 s). The same council with `effort=ultra`: 19 / 19 (median 596 s). Formula plus kernel
  (`key=eval(it)`): 18 / 20.
- **Cloud models, direct:** Haiku 20 / 20, Sonnet 24 / 24, Codex 24 / 24.
- **Single small models:** 3–4 items each, too few to compare. The draft's statement that "a single small
  model frequently failed" is not supported by these data.
- **Limits:** completed cells only, no paired baseline. 18 of 18 does not exclude a true success rate of 85%
  at the 5% level ($0.85^{18} \approx 0.054$; `stats.binomial_at_least`).
- *Literature:* majority voting helps mainly where errors decorrelate; the condition that each voter be right
  more than half the time comes from independent yes/no votes and does not carry over to correlated samples or
  several wrong answers. The cited knowledge-heavy and debate results include failures: The Avengers, a routed
  council of about 7B models, trails frontier models on MedQA and GPQA, and in the cited 7–8B settings debate
  lost to voting or direct baselines (Debate or Vote; Talk Isn't Always Cheap; SLM-MUX). See
  [PRIOR-ART.md](PRIOR-ART.md).

### 3. Checked Escalation (`route=escalate`)
Six synthetic cases, 2026-10-03, with the same two-call ceiling per cell:
- **llama3.2:1b:**
  - Natural prompt: 0 / 6 correct, 1 / 6 wrong answer accepted, 5 / 6 runs failed.
  - Typed answer alone: 0 / 6 correct, and **6 / 6 wrong answers accepted** as valid typed answers.
  - **Checked escalation:** 6 / 6 correct and 0 / 6 wrong accepted. Every success came from the conditional
    Claude Haiku fallback.
- **qwen3:4b, same six cases:** natural 4 / 6 (2 wrong accepted), typed 4 / 6 (2 wrong accepted), checked
  escalation 6 / 6 (0 wrong accepted; Haiku recovered the two failures).
- *Receipt Context:* the checks were executable reference predicates. The result shows that this package
  rejected the observed wrong candidates and recovered them with a stronger fallback. The small models were not
  made correct, and six cases support no statistical claim.

### 4. Spec-Sheet Builds by Local Models (Symblic 2.4, 2026-10-04)
- `examples/tetris.sheet.md` (25 units, 120 examples) was built into `tetris.html` by local models only:
  qwen3:4b-instruct, phi4-mini and gemma3:4b in Ollama on CPU-only worker nodes. The page passes **39 of 39 required
  checks** of an independent harness; the 2 advisory checks are not met.
- Development took 14 incremental builds, 421 model calls and 21 model-hours.
- A from-scratch validation (run `3566050e304f`, nothing kept, no cache) passed 39 / 39 again. All 25 units
  were accepted on their first attempt; it took 141 calls and 8.7 model-hours.
- About 30% of the page script's non-trivial lines appear word for word in the sheet.
- *Limits:* one task, whose sheet was refined while the models were being tried on it. A unit that passes its
  examples can still be wrong on inputs no example covers; an independent test of the whole file is required
  ([SPEC-SHEETS.md](SPEC-SHEETS.md), "What a passing build establishes").

---

## 8. Backend Architecture: Python Runtime & Native Kernel Tradeoffs

1. **Kernel Evaluation Overhead vs. Inference Latency:**
   Model calls take seconds to minutes. In the receipts above, Claude Haiku took a median of 6–13 s per task,
   and qwen3:4b on a worker node CPU 96–296 s. The Tetris validation used 141 calls in 8.7 model-hours, about 3.7
   minutes per call, and the local call timeout is 3 600 s. Typical kernel work is small by comparison:
   - `check` of the 6-line ExactMath program: about 0.9 ms, and small in-memory runs of the examples in §5 and
     §10: 2–6 ms (measured 2026-10-04 on the host, a 6-core desktop CPU under load, in an isolated copy of the 2.4
     sources);
   - a 32×32 exact quadratic solve: 0.35 s (the adapter's recorded scale profile, same machine, 2026-10-03).

   Recursive Datalog is the exception (§2): its cost grows steeply with the graph.
2. **Where a Native Kernel (Rust/C++), or a Better Algorithm, Matters:**
   - **Recursive Datalog over graphs larger than a few hundred derived facts.** Today the engine evaluates
     naively and stops at its step budget long before its 200 000-fact limit. Semi-naive evaluation and
     indexed joins (Ullman 1988) are the standard first remedy, before any native port.
   - High-throughput client-side deployment via **WebAssembly (WASM)** without a Python runtime: proposed, not
     attempted.
   - Embedding in memory-constrained devices: proposed; no footprint has been measured.
3. **Realistic Engineering Outlook:**
   Claims of "10x–100x end-to-end application speedups" are unmeasured hypotheses until real-world parsing and
   kernel workloads are profiled separately from model inference. The current architecture keeps Python for
   orchestration and keeps the kernel semantics in a pure, tested core (`symblic/kernel/language.py` does no I/O).

---

## 9. Large Contexts & Codebases: Relational Fact Extraction (Proposal)

### The Problem:
Long prompts with many source files use the middle of the context worst ("Lost in the Middle", Liu et al.,
TACL) and degrade as length grows (Context Rot; [PRIOR-ART.md](PRIOR-ART.md) [LostMiddle], [ContextRot]).
They also cost more tokens.

### The Proposed Approach: Codebase-as-a-Datalog-Database
**Automatic codebase fact extraction remains proposed.** Datalog, the `graphs` library (`reachable`,
`cyclic`, `linked` over `edge(X, Y)` facts), and asks with explicit `from` sources already exist. Facts written
by hand or generated elsewhere can be loaded as `fact` lines. The installed task-card builder now resolves a
spec sheet's declared `Uses` edges, supplies the full transitive code/contract closure and computes which
accepted branches can be reused after edits. It is not a JavaScript dependency extractor or a proof that
the author's declarations are complete; isolated unit checks expose some undeclared dependencies.

1. **Fact Extraction (proposed):** A static parser would turn declared AST structures into Datalog facts
   (`fact defines("auth.py", "login")`, `fact calls("api.py", "login")`).
2. **Blast Radius Analysis (proposed):** The Kernel would compute the reachability closure of modified symbols
   before any model is asked.
3. **Micro-Capsules:** automatic affected-source slices remain proposed. The installed spec-sheet cards supply
   complete declared transitive dependencies and refuse an oversized required capsule before dispatch.
   Ordinary `context=relevant` still selects by word overlap, not by dependency.
4. **Scope & Limitation:** A static code graph captures declared syntax; it does **not** capture dynamic
   dispatch, runtime configuration, generated code, or reflection unless the extractor explicitly models them.
   Reachability guarantees are exact only relative to the extracted graph.

---

## 10. Finite Quadratic Minimization & Symblic 2.2 Integration

Since Symblic 2.2 (current: 2.5), the deterministic Kernel includes the exact variational solver documented
in [`VARIATIONAL.md`](VARIATIONAL.md) (`symblic/adapters/variational.py`, adapter version 1).

### 1. Implemented Capabilities
The module solves the explicitly supplied finite quadratic problem:
$$H(x) = \tfrac{1}{2} x^T A x - b^T x, \quad x \in \mathbb{R}^n$$
when all input coefficients are rational and $A$ is symmetric positive definite (SPD), for dimensions
$n \le 32$.

- **Exact Arithmetic:** Uses unpivoted $LDL^T$ factorization over exact rationals (`fractions.Fraction`).
  Entries must be integers or fractions; every value is capped at 4 096 bits and the work at 200 000
  operations. Singular matrices (such as the pure-Neumann case) and indefinite ones are refused.
- **Separate Witness Verification:** The verifier checks $A = L \text{diag}(D) L^T$ with $D_i > 0$ and verifies
  that the residual $Ax - b = 0$ exactly, proving that $x$ is the unique global minimum of the discrete encoded
  problem. The verifier never calls the factorization or solve routines; it shares their exact-arithmetic
  helper and energy function, so its independence is partial.
- **Scope:** these are kernel builtins only. `solve=true` still works by enumeration (at most 20 000 values),
  and nothing assembles $A$ and $b$ from a PDE: the author supplies them.
- **Builtin Functions:**
  - `quadratic_minimize(A, b)`
  - `quadratic_verify(A, b, receipt)`

```symblic
let A = [[4, 1], [1, 3]].
let b = [1, 2].
let result = quadratic_minimize(A, b).
assert quadratic_verify(A, b, result).
assert result.x = [1/11, 7/11].
assert result.min_energy = -15/22.
show result.x.
```

### 2. What the Energy Analogy Does NOT Prove
- **No Proof of Unique Prompt Meaning:** An entropy objective over model responses is an analogy; it does not
  constitute a Lyapunov energy functional on semantic space. Two models can agree on a false extraction
  (yielding zero entropy). Lowering cross-model disagreement does not mathematically prove convergence to the
  author's intended meaning.
- **Continuum PDE vs. Discrete Solver:** The continuum variational derivation behind the vorticity example
  ([VORTICITY-CONSTRUCTION.md](VORTICITY-CONSTRUCTION.md)) ($\nabla \cdot (y \nabla \phi) = \Omega$) requires vanishing
  boundary integrals, coercivity, and appropriate Sobolev spaces. In Symblic, the solver is strictly a finite,
  discrete rational matrix solver; it does not assemble PDEs, infer boundary conditions, or certify physical
  continuum components.
- **Physical Strength Invariants:** In CAD/3D modeling, strain energy checks require material constitutive
  laws, boundary constraints, load distributions, and mesh convergence; an energy threshold alone does not
  certify physical component strength.

---

## 11. High-Performance Computing (HPC) Execution & Distributed Scaling (Proposals)

**Status: none of this section is built.** Symblic runs orchestrate on the host (page and API runs as
`symblic-<id>` units in `a systemd slice for work`; `tools/symblic run` in the terminal under `nice 10`) and place CLI and
Ollama calls on the worker nodes through the fleet runner ([SPEC.md](SPEC.md) §6, §8). There is no HPC, InfiniBand or SLURM
integration. REVIEW-2.3 recorded an outcome for each proposal below ([REVIEW-2.3.md](REVIEW-2.3.md),
HPC-FOUNDATIONS).

```
                            ┌────────────────────────────────────────┐
                            │  SYMBLIC ON HPC (PROPOSAL, NOT BUILT)  │
                            └──────────────────┬─────────────────────┘
                 ┌─────────────────────────────┴─────────────────────────────┐
                 ▼                                                           ▼
    ┌──────────────────────────┐                                ┌──────────────────────────┐
    │  PATH A: HPC INFERENCE   │                                │   PATH B: HPC TRAINING   │
    │  & ORCHESTRATION RUNTIME │                                │   & REINFORCEMENT (RLVR) │
    ├──────────────────────────┤                                ├──────────────────────────┤
    │ • Multi-node tensor      │                                │ • Train an Autoformalizer│
    │   parallelism (vLLM/SGL) │                                │   (English → .sym AST)   │
    │ • More samples & search  │                                │ • Train an Applicator for│
    │ • Parallel Datalog       │                                │   1-shot schema contract │
    │                          │                                │ • RL with Verifiable Re- │
    │                          │                                │   wards (Kernel = Reward)│
    └──────────────────────────┘                                └──────────────────────────┘
```

### Path A: HPC Execution Runtime
1. **Multi-Node Tensor-Parallel Inference (not built):** vLLM or SGLang can serve 70B–671B open models across
   nodes, but Symblic has no applicator for such an endpoint, and a new engine would need an admitted launch
   path.
2. **Test-Time Scaling to $N=100\text{--}1{,}000$ and Sequential Monte Carlo (rejected):** votes are clamped to
   25 per ask. More votes from the same models are mostly correlated repeats, and more votes are not SMC
   ([REVIEW-2.3.md](REVIEW-2.3.md), HPC-FOUNDATIONS row 2; [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)). What
   exists: checked `route=search` (up to 25 candidates per round, up to 20 rounds) and adaptive `ahead` voting.
3. **High-Performance Kernel Workloads (deferred):**
   - **Parallel Datalog (Soufflé, 64–128 cores):** deferred; no measured workload needed it. Today's engine is
     single-threaded and naive (§2); it reaches its step budget at a few hundred derived facts, so the first
     step would be a better algorithm, not more cores.
   - **BLAS/LAPACK/PETSc for numerical construction:** deferred. Silently replacing exact arithmetic would
     violate the existing rational contract. An explicit approximate constructor is compatible with that
     contract when it supplies a separately checked rational witness, or with a separately declared residual,
     interval and error contract. The existing exact SPD minimizer remains limited to $n \le 32$; it does not
     assemble a PDE. Benchmark an optional constructor against the current exact route before adoption.
4. **Scheduler Syntax in Asks (rejected):** placement belongs to the host, not to program text, and the
   existing `@node` form already covers it ([REVIEW-2.3.md](REVIEW-2.3.md), HPC-FOUNDATIONS row 1). The proposed
   line is refused by `check` ("unknown ask option 'nodes'"):
   ```symblic
   ask result: Report "Analyze fleet telemetry" with by="hpc:slurm", nodes=4, gpus=8
   ```
   The supported form names an applicator and, optionally, a node:
   `by="ollama:qwen3:4b-instruct@node-a"`.

---

## 12. HPC Training & Reinforcement Learning with Verifiable Rewards (RLVR) (Proposals)

**Status: deferred; nothing has been trained.** REVIEW-2.3 deferred this as a large, compute-heavy research
project with no baseline measurement, and called its reward claim wrong as stated
([REVIEW-2.3.md](REVIEW-2.3.md), HPC-FOUNDATIONS row 4). No training code exists.

### What Should (and Should Not) Be Trained
- **The Deterministic Kernel is NEVER trained:** Exact rational math, Datalog fixpoints, and $LDL^T$ algebraic
  solvers are exact algorithms. Training a network to compute $0.1+0.2$ or evaluate Datalog would replace an
  exact result with an approximate one that can be wrong.
- **Proposed specialised models** (for example 7B, 14B or 32B), for three roles:
  1. **The Autoformalizer:** English requirements to programs that pass `check`. Passing `check` does not
     decide meaning. Today the Interpreter page helps the operator refine a request into explicit requirements
     and compiles it to a checked program ([INTERPRETER.md](INTERPRETER.md)); the host executor's planner writes
     programs with existing models; and a spec sheet compiles to a program without any model, whose asks then
     call models to write each unit ([SPEC-SHEETS.md](SPEC-SHEETS.md)).
  2. **The Schema Contract Reader:** schemas already constrain the reply where an engine supports it (Ollama
     `format`; the Claude, Codex and AGY schema flags; not Copilot or the browser engines), and the kernel
     checks every reply. `Code` answers send no schema.
  3. **RLVR / GRPO:** the kernel's `ensure`/`assert` verdicts are deterministic and reproducible, which makes
     them verifiable rewards in the RLVR sense (Lambert et al. 2024, who name RLVR; Shao et al. 2024 introduced
     GRPO, with a learned reward model). They are not "non-gameable": a reward is gameable wherever its
     predicate is weaker than the task ([SPEC.md](SPEC.md) §5).

### Would Training Make Significant Improvements?
- **Speed & Turnaround:** unmeasured. The draft's ">98% first-pass schema compliance" figure has no source.
  Retries follow failed checks as well as malformed output. In the Tetris validation every accepted unit
  passed on its first attempt; the cost was inference time (141 calls, 8.7 model-hours), not retry loops.
- **Accuracy:** unmeasured. In the two escalation pilots a schema alone gave no gain ([RESULTS.md](RESULTS.md)).
  A claim would need held-out, independently labelled tasks.

### Could Training Cause Symblic to be WORSE? (Critical Failure Modes)
**Yes, it could.** None of these has been observed here, because nothing has been trained.
1. **Reward Hacking / Goodhart's Law:**
   A policy rewarded only for passing `ensure` conditions can learn shortcuts that satisfy the check while
   violating the intent (Amodei et al. 2016).
   * *Example:* an extraction with quantity 1, unit price 1 and total 1 satisfies $Q \times P = T$ for any
     invoice. This is an executed counterexample ([RESULTS.md](RESULTS.md), 2.2 section; §5 above), not a case in
     the test suite. A model trained on that reward could learn the shortcut. Symblic 2.3's defence is grounding
     (`numbers`, `quotes`, `text.quoted_number_in`); a reward would need grounding and a held-out evaluation.
2. **Catastrophic Forgetting of Linguistic Nuance:**
   Heavy fine-tuning on programming syntax can degrade broad reading ability, the capability the model is there
   for (catastrophic interference: McCloskey & Cohen 1989; Kirkpatrick et al. 2017). Unmeasured here.
3. **Confidence Distortion:**
   Post-training can worsen a model's calibration (OpenAI 2023, GPT-4 Technical Report). Symblic's consensus
   reads no model confidence, though: it groups answers by fingerprint, weights them by author-given
   applicator weights and reports entropy over the answers. An overconfident model affects a vote only through
   its answers. Correlated wrong answers raise agreement, which is why agreement is never treated as
   correctness and families are counted by lineage ([SPEC.md](SPEC.md) §4–5).

### Parameters & Data to Train On (proposal; none of this exists)
- **Base Models:** pre-trained base weights (e.g. Qwen-2.5-14B-Base or Llama-3.1-8B-Base).
- **Dataset Composition:**
  1. 100,000+ pairs of `(Unstructured Document, Typed Schema, Inhabitant that passed its checks)`.
  2. 50,000+ pairs of `(Plain English Intent, .sym program that passes check)`.
  3. Negative trajectories: failed extractions paired with the kernel's rejection message and the repaired
     state. A run's record already keeps every reply (`calls.jsonl`), a `retry` row each time a failed check
     sends its ask back (`trace.jsonl`) and, for a check that ran out of retries, up to six of the answers it
     rejected (`diagnoses` in the report). It does not keep the feedback sent with a retry: that is part of the
     prompt, which the record holds only as a hash. the fleet runner also writes the full prompt of each CLI or Ollama
     call to its own run folder (`prompt.txt`).
- **Hyperparameters:** a low learning rate ($\sim 1 \times 10^{-5}$ for SFT, $1 \times 10^{-6}$ for
  RL/GRPO) and a KL-divergence penalty ($\beta = 0.05\text{--}0.1$) are unvalidated starting guesses. A KL
  penalty limits divergence from the reference model; it does not by itself preserve reading ability.

---

## 13. Multi-frame checking: background

A multi-frame design rationale ([EVIDENCE.md](EVIDENCE.md)) informs the emphasis on acquisition provenance,
distinct methods, declared assumptions and attempts to find failures. This is a design influence, not empirical evidence that Symblic improves accuracy.
[EVIDENCE.md](EVIDENCE.md) gives the permitted engineering interpretation.

### Operational evidence, rather than a new score

| Mechanism | Existing support | Constructive extension |
|---|---|---|
| Acquisition provenance | Source, time, capability, model lineage and assumptions in evidence records | Bind every method result to an exact claim revision, domain and units |
| Conditional derivation | Epistemic envelopes retain originating premises and receipt scopes | Show the assumptions still required when a checked artifact is consumed |
| Diversity | Families counted by lineage; independence explicitly unestablished | Measure which seeded failure classes each acquisition method catches; shared input faults remain shared |
| Disagreement and invalidation | RC2 preserves contested votes and unavailable/mismatched dependency support; the pure evaluator separately processes supplied revisions, withdrawals and disagreement records | The installed notebook retains imported snapshots, operator revisions, disagreement history and selected support; 32 Python checks and two browser journeys passed. It does not mutate completed runs. Method selection by additional failure coverage per measured cost remains an experiment |
| Reproducibility | Source/kernel pins and replay records | Compare independent source or behavioral measurements with repeated model readings under matched budgets |

These operations keep empirical acquisition separate from formal deduction. A proof checker can establish
an encoded consequence of premises; it does not observe the world or establish those premises. Several
models reading one defective source do not become independent instruments simply because their names differ.
The next evidence experiment should use a claim-by-method-by-failure-mode matrix, retain unresolved cells,
and report the full planned denominator. [RESEARCH-TRANSFER.md](RESEARCH-TRANSFER.md) specifies that experiment.

Historical proposals for a native three-value `frame` enum, an automatic independence certificate and a
single concordance score did not supply those mechanisms. That does not rule out useful new evidence
acquisition, method comparison or source-invalidation functionality. The existing provenance and observation
interfaces remain available, and broader mechanisms can be admitted through explicit contracts and tests.

---

## 14. The Shippable Product Roadmap (Proposals)

**Status: none of these is built as proposed; each item says what exists now** (the lockfiles and replay in
item 4 existed before the roadmap). They are steps toward a production-grade product:

1. **Single Standalone Native Binary:** not built. Today `tools/symblic` (bash plus Python) is the command line;
   the kernel and its first-party modules use only Python's standard library, while applicators depend on the fleet runner,
   the agent CLIs and Ollama. The draft's installer line (`curl ... symblic.dev/install.sh`) was removed: no
   installer exists, and no code or configuration refers to that domain.
2. **VS Code Extension & Language Server Protocol (LSP):** not built. `check` already reports syntax errors,
   type mismatches and reserved names (`let count = 1.` gives "count is a builtin function name"), and the page's
   Preview shows the exact capsule and JSON Schema of the first ask (no token count). The page's editor also
   re-runs `check` 450 ms after each edit and marks errors and warnings in the gutter
   (`web/studio/symblic-page.js`, `scheduleCheck`, `paintDiag`); that runs in the browser page, not in an
   editor extension or a language server.
3. **Pluggable Multi-Backend Adapters (`symblic.toml`):** not built. Applicators are named in program text, and
   the host places calls.
4. **Deterministic Packaging & Replay:** `run.lock.json` exists and replays with no model call. There are no
   versioned packages such as `units@2.2.0` or `variational@2.2.0`: locks pin library modules by source hash, and
   the variational adapter is version 1 in the kernel identity. No CI checks locks.
5. **WebAssembly (WASM) Playground:** not built or attempted. Startup, memory and conformance would need to be
   measured first ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).

---

## 15. Strategic Roadmap for Future Verification Extensions

The following are **research proposals** for future versions. None is built. `check` refuses the syntax of
items 1 and 2 and the `within` form of item 3; `assert always (…).` passes `check` as a call to an unknown
function and fails when run ("unknown function always").

#### 1. Refinement Types (Proposal; not built)
Types bounded by arbitrary kernel predicates. Today bounded types (`Int in a..b`, enums, lengths) and `ensure`
checks cover part of this.
```pseudocode
# Proposed Refinement Types Syntax:
define EvenInt as Int where it mod 2 = 0.
define ValidEmail as Text where contains(it, "@") and contains(it, ".").
```

#### 2. Calibrated Uncertainty (Proposal; not built)
Distribution types for tracking sampling variance. Today a vote reports agreement and entropy over answers,
which are not calibrated probabilities, and `stats.binomial_at_least` / `binomial_at_most` give exact
binomial tails.
```pseudocode
# Proposed Probabilistic Type Syntax:
ask risk: Distribution of Number in 0..1 "Assess credit default probability"
assert risk.confidence_interval(0.95).upper < 0.15.
```

#### 3. Linear Temporal Logic for Trajectories (Proposal; not built)
Multi-step safety invariants over execution traces. Today `assert` checks a condition when it runs.
```pseudocode
# Proposed Temporal Invariant Syntax:
assert always (account.balance >= 0).
assert eventually (order.status = "shipped") within 48 hours.
```

#### 4. Native SMT Solver Integration (Z3) (deferred)
Z3 could discharge supported arithmetic and quantifier constraints. Soundness and decidability are distinct:
sound procedures can return `unknown` or fail to terminate on an unrestricted fragment. An adapter needs an
explicit supported theory, resource limit, encoding contract and certificate/trust policy. Enumeration already
decides the bounded cases Symblic currently admits; an optional solver should earn adoption on cases where
it improves coverage or cost ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).

#### 5. Formal Proof Export (Lean 4) (not built)
Compiling Symblic specifications into theorem statements for an external prover. Proof terms for
natural-language extraction are not well defined ([REVIEW-2.3.md](REVIEW-2.3.md), INTENSE-CRITIQUE row 3); an
optional Lean/SMT adapter over a declared finite fragment is listed as a research direction
([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).

---

## 16. Possible Applications & Assurance Boundaries

Symblic could express checks in these domains. None has an example program or test in the repository unless
noted. A check establishes conformance to its encoded predicate over the facts a program was given
([SPEC.md](SPEC.md) §5). Recursive Datalog fits only small graphs today (§2).

1. **Contract Clause Auditing:** extract liability caps and indemnification clauses into Records (a model
   judgement), then find clause conflicts among the extracted records with Datalog.
2. **KYC / AML Ownership Tracing:** with declared ownership facts, the `graphs` library's `cyclic` finds
   circular control and `reachable` traces ownership chains.
3. **Data-Flow Reachability (e.g. GDPR):** model read/write permissions as a graph and check whether a path
   reaches personal data. A path found or not found holds for the modelled graph only; the check prevents
   nothing by itself and says nothing about flows the model leaves out.
4. **Pediatric & Renal Dosage Arithmetic:** `symblic/lang/library/units.sym` (exists) converts units exactly, with lossless
   round trips, and asserts can enforce dosage thresholds. *(Boundary: programmatic checks ensure arithmetic
   consistency, not medical diagnosis.)*
5. **Accounts Payable Three-Way Matching:** purchase order, receiving log and invoice as records, compared with
   `records.agree` and arithmetic. Agreement on shared fields is not correctness.
6. **Supply Chain Blast Radius:** reachability over declared supplier edges (`graphs`).
7. **Cloud RBAC Access-Control Auditing:** check, over the declared role graph, that no contractor role reaches
   an administrator role. This is complete only if the graph is.
8. **The host executor Task Orchestration (exists):** the host executor runs Symblic programs. An action with a key
   (`act booked = calendar.add(...) with key="review-{today}".`) happens at most once per ledger; an unknown
   outcome stops the run until the operator says what happened. This is not exactly-once execution
   (`symblic/kernel/effects.py`).
9. **Literate Research Documents (`.symd`) (exists):** papers with executable Symblic blocks, reproduced by
   several agent groups ([RESULTS.md](RESULTS.md) §7.3). A complete run of a paper can be locked in a
   `run.lock.json` and replayed with no model ([SPEC.md](SPEC.md) §11); no paper's lock is kept in
   `docs/reference/papers/`.

---

## 17. How to Explain Symblic (Conceptual & Developer Summary)

- **The 30-Second Elevator Pitch:**
  *"Symblic turns detailed instructions into small construction contracts. A model receives the current task
  and its required dependencies, constructs code or another artifact, and gets bounded repair feedback when
  a check fails. Accepted state becomes the next task's explicit memory. Generic proof, source and behavioral
  checks let the same runtime support many projects while keeping the author in charge of the specification."*
- **The Non-Technical Analogy (Work Card and Durable Progress):**
  *"A worker starts each shift with an exact work card, the necessary plans and an inspected record of what
  is already built. The worker constructs the next piece. The inspector checks its stated obligations and
  records accepted progress. Another worker can then continue without remembering the previous conversation."*
  The card must contain the dependencies the work needs; the worker must be capable of the assigned primitive;
  the inspection covers its declared contract. Those three conditions can be tested and improved separately.
- **The Developer Summary:**
  *"Symblic is a neuro-symbolic DSL. It replaces unstructured prompt glue with a first-class `ask` keyword,
  exact rational arithmetic, an embedded Datalog engine for small graph queries, a capsule rebuilt for each ask
  from declared context (no accumulated chat history), transactional, bounded retries (`ensure ... else
  retry`), and hash-pinned lockfiles that replay recorded replies without a model."*
- **The One-Liner:**
  **"Symblic programs model construction through explicit tasks, checked artifacts and durable state."**

---

## 18. Focused Minimalist Visual Identity

The visual identity is modernist and monochrome, after the **International Typographic Style** (Swiss Style)
and designers such as Massimo Vignelli; Dieter Rams, an industrial designer, is a further influence:
- **Monochrome:** the SVG marks use black or near-black (`#000000`, `#0A0A0A`, `#0A0B0E`, `#0D0E12`) and white or
  near-white (`#FFFFFF`, `#F5F6F8`); the Quine and turnstile marks each add a grey (`#8A8F9A`, `#7B8290`). Zero
  gradients, zero neon glow, zero circuit decoration.
- **Rooted in Mathematical Logic:**
  1. **Semantic Entailment ($\models$):** Denotes that a model satisfies a formal sentence.
  2. **Syntactic Turnstile ($\vdash$):** denotes provability in logic. The proof lane checks supplied
     derivations in a named fragment; the symbol does not turn every model answer into a proof.
  3. **Quine Corner Brackets ($\ulcorner \dots \urcorner$):** Quine's notation for quasi-quotation.
  4. **The Statement Period (`.`):** Anchors completed formal statements.

### Brand Assets (`docs/reference/`; present in the working tree, not committed to git as of 2026-10-04):
- `docs/reference/symblic-minimal-geometric.jpg` (not included in this repository): Primary geometric mark (double turnstile $\models$ and
  statement point `.`).
- `docs/reference/symblic-minimal-bracket.jpg` (not included in this repository): Interlocking Quine logic brackets ($\ulcorner \lrcorner$).
- `docs/reference/symblic-minimal-quine.svg` & `.png`: Monoline orthogonal logic mark.
- `docs/reference/symblic-minimal-turnstile.svg` & `.png`: Vertical truth axis with assertion crossbars.

---

## 19. CLI Command Reference

```bash
# Statically check syntax, types, and capability contracts (no model)
tools/symblic check my_program.sym

# Preview the exact capsule and JSON Schema of the first ask (no model call)
tools/symblic preview my_program.sym

# Run with Claude (--dir FOLDER keeps the run record)
tools/symblic run my_program.sym --by claude:haiku

# Run locally on the worker node cluster
tools/symblic run my_program.sym --by ollama:qwen3:4b-instruct@node-a

# Run the test blocks of a library module (kernel only unless --by)
tools/symblic test units                         # or: python3 symblic/lang/abstraction.py test symblic/lang/library/units.sym

# Freeze a finished run folder into a lockfile (writes <run_folder>/run.lock.json)
tools/symblic lock <run_folder>                  # or: python3 symblic/kernel/lockfile.py lock <run_folder>

# Replay a frozen run offline with zero model calls
tools/symblic lock replay <run_folder>/run.lock.json   # or: python3 symblic/kernel/lockfile.py replay <lock file>
```

---

## 20. Symblic and Human Intersubjectivity: Background and Proposals

This section summarises arguments from philosophy, sociology and psychology that the draft drew on, and the
proposals it made for Symblic. The arguments are summarised, not endorsed as proofs; the proposals carry their
REVIEW-2.3 outcomes.

### 20.1 The Epistemic Chasm: Why Humans Misunderstand Each Other
1. **Thomas Nagel (1974) & Ludwig Wittgenstein (1953):** Nagel argues that conscious experience has a
   subjective, first-person character that objective description leaves out. In §293 of *Philosophical
   Investigations*, Wittgenstein's "beetle in a box" argues that the meaning of public words cannot rest on
   private objects that no one else can check; meaning lives in public, rule-governed language-games
   (*Sprachspiele*).
2. **Donald Davidson (1984):** interpretation must assume that a speaker is mostly rational and mostly right
   (the Principle of Charity). In later work Davidson argues that knowledge of other minds arises in
   "triangulation" between two speakers and a shared world.
3. **Niklas Luhmann (1984):** *Double Contingency* (*doppelte Kontingenz*): Ego and Alter are opaque to each
   other. Luhmann describes communication as a synthesis of three selections: information, utterance and
   understanding.
4. **Lee Ross and Andrew Ward (1996):** *Naïve Realism* describes a tendency to take one's own perception as
   unbiased and to explain disagreement by the other side's ignorance, bias or bad faith.

### 20.2 Is "True Empathy" Possible?
- **Affective Empathy:** Paul Bloom (*Against Empathy*, 2016) argues that empathy is parochial and biased;
  Tania Singer and Olga Klimecki (2014) distinguish empathic distress, which exhausts, from compassion.
- **Phenomenological Isomorphism:** on Levinas's account the other person remains irreducibly other (*Totality
  and Infinity*). Whether one person could have another's exact experience is a philosophical question, not a
  settled result.
- **"Epistemically Secure Intersubjective Alignment":** the draft proposed defining empathy as "the verifiable
  minimization of mutual prediction error between modeled needs and validated agency across independent
  observational frames" and attributed this to the multi-frame rationale. The definition is the draft's own: that rationale concerns
  checking claims and does not discuss empathy. Symblic has no mechanism that measures prediction error between
  people.

### 20.3 Four Proposals and Their Outcomes
1. **Four-Part Typing of Speech Acts** (`Observation`, `Affect`, `Need`, `Request`): rejected as built-in types;
   the existing type system already expresses them ([REVIEW-2.3.md](REVIEW-2.3.md), INTERSUBJECTIVITY row 1).
   The four parts are Marshall Rosenberg's Nonviolent Communication (observations, feelings, needs,
   requests), not Habermas's validity claims (truth, rightness, sincerity), which the draft mixed with them.
   The related reconciliation proposal was built as the example `tests/kernel/fixtures/13-two-accounts.sym`
   (INTERSUBJECTIVITY row 6). It splits two accounts into the four parts and rejects any item not quoted word for
   word from its own account. Which kind an item is, and which observations match, are model judgements.
2. **Aumann Common Knowledge:** deferred as an engine (INTERSUBJECTIVITY row 5); the finite partition model was
   built: `knows_event`, `common_partition`, `common_knowledge`, `posterior_given` and `agreement_process`
   compute on partitions of at most 64 states that a program declares ([KNOWLEDGE.md](KNOWLEDGE.md); Aumann
   1976). A transcript is not a partition; the result says nothing about what a person or a model knows.
3. **Naïve-Realism Checks** (`inferred_intent != verified_fact`): rejected. Beyond quote grounding (`quotes`),
   deciding what is an inference rests on model judgement the kernel cannot verify (INTERSUBJECTIVITY row 4).
4. **Costly Signaling & Commitment Witnessing:** deferred. It would touch personal data and needs its own
   contract and consent; no use case exists, and the costly-signal framing is wrong (INTERSUBJECTIVITY row 7).

---

## 21. Expanded Minimalist Formal Logic Icon Suite

The marks follow the monochrome, modernist style of §18. Each is a design motif drawn from a tradition in
logic, not a claim about Symblic's semantics:

| Icon Asset | Logic Tradition & Motif | File Paths |
| :--- | :--- | :--- |
| **Gentzen Sequent Mark** | Gerhard Gentzen (1934) Natural Deduction: Horizontal deduction fraction bar with orthogonal premise markers and conclusion point (`.`). | `docs/reference/symblic-minimal-gentzen.svg`<br>`docs/reference/symblic-minimal-gentzen.svg`<br>`symblic_icon_gentzen_sequent_1791055152929.jpg` |
| **Tarski Double Turnstile** | Alfred Tarski (1933) Model Theory: Dual parallel vertical axiom pillars with orthogonal semantic entailment arms ($\models$). | `docs/reference/symblic-minimal-tarski.svg`<br>`docs/reference/symblic-minimal-tarski.svg`<br>`symblic_icon_tarski_double_turnstile_1791055180316.jpg` |
| **Frege Assertion Stroke** | Gottlob Frege (1879) Begriffsschrift: Stepped deductive monogram with vertical judgment stroke and statement terminator. | `docs/reference/symblic-minimal-frege.svg`<br>`docs/reference/symblic-minimal-frege.svg`<br>`symblic_icon_frege_turnstile_1791055032789.jpg` |
| **Quine Proof Brackets** | W.V.O. Quine: Razor-sharp 90-degree interlocking corners ($\ulcorner \dots \lrcorner$), Quine's quasi-quotation marks, on matte obsidian. | `docs/reference/symblic-minimal-quine.svg`<br>`docs/reference/symblic-minimal-quine.svg`<br>`symblic_icon_quine_bracket_1791055014379.jpg` |
| **Categorical Flow** | Curry-Howard / Category Theory: Orthogonal proof vectors and commutative diagram pathways. | `docs/reference/symblic-minimal-commutative.svg`<br>`docs/reference/symblic-minimal-commutative.svg`<br>`symblic_icon_categorical_flow_1791055051617.jpg` |
| **Monolithic Logic 'S'** | Pure architectural monogram fused from formal turnstiles and deduction axes. | `docs/reference/symblic-minimal-turnstile.svg`<br>`docs/reference/symblic-minimal-turnstile.svg`<br>`symblic_icon_monolithic_s_1791055065932.jpg` |

The `symblic_icon_*.jpg` drafts are not in the repository; they stayed in the drafting agent's own working folder. The SVG and PNG files are in
`docs/reference/`.

---

## 22. Intersubjective & Epistemic Proposals for the Core: Outcomes

The draft said that this research "exposes core design defects in v2.0–v2.2 and yields six concrete language
improvements". REVIEW-2.3 checked each against the code ([REVIEW-2.3.md](REVIEW-2.3.md), EPISTEMIC-IMPROVEMENTS
and INTERSUBJECTIVITY tables). Two small additions were built; the rest already existed, was deferred, or was
rejected.

### 22.1 The Draft's Five Claimed Deficiencies, Checked
1. **"Single-World Fallacy":** the draft said contracts assume one global truth and crash on perspectival
   discrepancies. They do not crash: a failed check retries and then fails the run with a report. A program can
   hold several accounts as separate records (example 13).
2. **"Beetle in the Box":** a real limitation: a word can mean different things to the author and the model.
   Tools exist for it: `term ... means` definitions, option definitions, `ambiguous=true` readings, and
   `tighten` with held-out panels ([SPEC.md](SPEC.md) §12).
3. **"Absence of Epistemic Modality":** provenance exists. Every binding carries its mechanism and evidence;
   observations carry their capability, hashes and time; flow labels are checked statically (REVIEW-2.3,
   "Recurring errors"). Typed modalities (`Belief`, `Observation`, `Knowledge`, `CommonKnowledge`) are deferred.
4. **"Single-frame checking":** the draft said one model checks one prompt. Symblic has votes, efforts,
   families, any number of checks per ask, checked escalation and `tighten` (REVIEW-2.3, "Recurring errors").
   Correlated blind spots are a real limit: agreement is not correctness.
5. **"Cheap Talk Invariants":** a real weakness: a check can accept a degenerate answer such as an empty list
   with total 0 (§5). Symblic 2.3 added the `SYM_VACUOUS` warning and the grounding builtins `numbers`, `quotes`
   and `text.quoted_number_in`.

### 22.2 The Six Proposed Upgrades and What Happened
1. **First-Class Epistemic Modality Types:** deferred; most of the provenance already exists (EPISTEMIC row 1).
2. **Multi-Frame Concordance Contracts:** rejected. Without the analogy the mechanism is a conjunction of
   checks, which `ensure`, `assert` and `observe` already express; the concordance score adds nothing
   (EPISTEMIC row 2).
3. **Davidsonian Triangulation Pass:** rejected as new. Probing a panel before a run and rewriting ambiguous
   asks already exist as `tighten`, readings and test certificates (EPISTEMIC row 3).
4. **Principle of Charity Auto-Repair:** built in 2.3 as retry feedback carrying the kernel's values for the
   parts of the failed check that depend on the answer alone; no model-written diagnosis (EPISTEMIC row 4).
5. **Non-Degeneracy Witnesses:** the span witnesses were built (`numbers`, `quotes`,
   `text.quoted_number(_in)`); they show that a number is written in a copied span, not what it describes. The
   entropy floor was rejected: the entropy of one text is undefined without a probability model (EPISTEMIC row
   5; REVIEW-2.3, "Recurring errors about the mathematics").
6. **Aumann Common Knowledge Graph:** rejected as a state machine for agents; the finite partition model was
   built (§20.3). Nothing here prevents "hallucination spirals" (EPISTEMIC row 6).

---

## 23. Theoretical and Systems Critique of Symblic, Checked Against the Code

The draft listed seven "foundational defects". Each is checked below against the code and
[REVIEW-2.3.md](REVIEW-2.3.md) (CRITIQUE-AND-LIMITATIONS table; "Recurring errors"). Several describe real
limits; several misdescribe the implementation.

### 23.1 The Seven Claimed Defects
1. **Decidability:** Symblic does not prove theorems about programs; it executes them. A run evaluates one
   path under a step budget (`MAX_STEPS = 200 000` kernel steps). This is not bounded model checking, which
   explores every execution up to a bound (Biere et al. 1999). What it can establish exhaustively: for an ask
   with a finite answer domain (at most 20 000 values), enumeration decides whether the checks admit no
   answer, exactly one, or several ([SPEC.md](SPEC.md) §5). A passed check establishes that this run's value
   conforms to the predicate.
2. **Capsule Context:** the draft said capsules enforce "total context sterilization". They do not: the
   author chooses the context (default: only the `from` names), and the capsule reports what did not fit. The
   real risk is an author passing too little. `check`'s per-ask risk report (`ask_risk`) notes an ask that
   mentions a bound name it is not given, or a pronoun with nothing to resolve (CRITIQUE row 2).
3. **Goodhart's Law & Vacuous Truth:** a real risk. A weak check can accept a degenerate answer; the §5 invoice
   check accepts an empty list with total 0. How often this happens is unmeasured, and a prompted model is not
   optimizing against the check, but retries do select answers that pass it. Symblic 2.3 added the
   `SYM_VACUOUS` warning and the grounding builtins (CRITIQUE row 3).
4. **Determinism Across Hardware:** GPU reduction order and batching do change model outputs, even at
   temperature 0 ([PRIOR-ART.md](PRIOR-ART.md) [TML-nondet], [FP32]). That affects fresh generation, not
   replay: a lock replays recorded replies and asks no model ([SPEC.md](SPEC.md) §8). The FLP result (Fischer,
   Lynch & Paterson 1985) concerns asynchronous processes reaching agreement under crash faults; one
   coordinator counting replies is not that problem (REVIEW-2.3, "Recurring errors about the mathematics").
5. **Quine-Duhem:** Symblic does not assume that the model is at fault. Before any model call, enumeration
   reports a contradictory or underdetermined finite contract. When retries run out, the report says whether
   every attempt gave the same answer (pointing at the check, the type or the input) or a different one each
   time (pointing at ambiguous wording). The report is a hint, not a verdict ([SPEC.md](SPEC.md) §5). Whether
   prose input contradicts itself cannot be decided in general.
6. **Paradigm Mixing:** a usability concern, unmeasured. Pure functions and model routines are separate
   constructs, and modules separate libraries ([SPEC.md](SPEC.md) §11). Forced separation into files was
   rejected (CRITIQUE row 6).
7. **Cost of Impossible Tasks:** a real risk: an ill-posed ask can consume retries and escalation calls before
   failing. Bounds exist: `retries` at most 5, `max_calls` (default 2 000 per run), and escalation stops at the
   first passing answer or fails. An information-theoretic early exit is deferred until measured (CRITIQUE row
   7). Votes are not presented as independent: evidence says `independence: not_established`.

### 23.2 Proposed Remedies and Their Outcomes
- **SMT Integration (Z3):** deferred under an explicit theory, resource and trust contract (§15.4).
- **Hierarchical Anaphoric Capsules:** `ask_risk` reports some missing names and unresolvable pronouns; a
  warning does not reconstruct sufficient context. Installed task cards add explicit dependency closure for
  spec sheets (§9). Automatic discourse resolution and verified source summarization remain research.
- **Entropy Floors & Grounding Witnesses:** the `SYM_VACUOUS` warning and grounding builtins were built; the
  entropy floor was rejected (CRITIQUE row 3).
- **Tolerant Proof Witnesses for GPU Replay:** rejected; replay does not re-run models (CRITIQUE row 4).
- **Quine-Duhem Diagnostic Engine:** built in 2.3 as the retry-exhaustion report (CRITIQUE row 5).
- **Strict Module Separation:** rejected; no mechanism was given, and functions and routines already separate
  pure code from model calls (CRITIQUE row 6).

---

## 24. Adversarial Critique: Proof Theory, Information Flow and Effects, Checked Against the Code

The draft's adversarial audit is checked below against the code and [REVIEW-2.3.md](REVIEW-2.3.md)
(INTENSE-CRITIQUE table). Two of its concrete claims about the code are wrong as stated; one points at a real
host-policy risk.

### 24.1 The Seven Claimed Contradictions
1. **Curry-Howard:** correct that Symblic 2.4 has no proof terms, cut elimination or normalization, and that
   checking a model's JSON answer is an empirical check, not a deductive proof. Symblic does not claim otherwise
   (§2, item 5; [SPEC.md](SPEC.md) §5). Symblic 2.5 adds a checker for supplied proof terms in a bounded
   fragment; a checked answer is still not a proof that it is right. The kernel evaluates Symblic expressions
   itself and never calls Python's `eval`; Symblic's `eval(text, ...)` parses a formula as a Symblic expression
   ([SPEC.md](SPEC.md) §7). Generating proof terms for natural-language extraction was rejected as ill-defined
   (INTENSE row 3).
2. **Formalization Loss (Montague):** a fixed schema can drop modality, caveats and irony. Authors can add
   fields for caveats or confidence, and `ambiguous=true` collects alternative readings. Nothing in Symblic
   claims "mathematically proven certainty" over extracted premises (INTENSE row 5).
3. **Rice's Theorem:** Rice (1953) shows that no algorithm decides a non-trivial semantic property for every
   program. It does not concern checking one value in one run (REVIEW-2.3, "Recurring errors about the
   mathematics"). Symblic claims neither decidability of program properties nor a sound static verifier; its
   limits (the step budget, the enumeration cap) are explicit, bounded failures (INTENSE row 4).
4. **The `steered` Label (`symblic/kernel/effects.py:29-34`):** the label is real; "laundering" is not. Text from
   outside the operator's control (a web page, a stranger's mail) is labelled `untrusted`. Such a value cannot
   become an argument of an `act` unless the program names that argument in `allow_untrusted=["arg"]`, for text
   meant to be carried as data (a note that stores a page); a capability that `instructs` an agent allows no
   such exception ([EFFECTS.md](EFFECTS.md) §5). Passed through a closed type (`Bool`, a choice, a small `Int`
   range), untrusted text becomes `steered`: it can choose among actions the program itself wrote, and that is
   reported. `needs_owner` marks a weighty act that outside text chose, or wrote part of through
   `allow_untrusted`, so that a host must not approve it on its own (`symblic/kernel/effects.py:89-92`). In
   the host executor's guarded mode a weighty steered act waits for the operator unless the operator has set `approve` to `auto` and
   turned on `approve_steered`; one whose arguments outside text wrote always waits. Its default full mode, the
   operator's decision of 2026-10-03, approves both (`host_executor.py:46-49, 155-165`; `host_executor_host.py:189-199`).
   So in full mode, injected text can choose which program-written action fires and, where a program opts in
   with `allow_untrusted`, write that argument, with no operator approval (INTENSE row 1).
5. **Shortcut Learning:** no training pipeline exists (INTENSE row 6). If one were built, reward hacking would
   be a real risk (Amodei et al. 2016; on shortcut learning, Geirhos et al. 2020). Binary rewards are standard in
   RLVR and are not by themselves a cause of collapse ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).
6. **Irreversible Effects:** the premise is false for Symblic. An `act` between an ask and a check that may
   re-ask it is refused, statically and at run time, so a retry never has to undo an effect ([SPEC.md](SPEC.md)
   §5; `symblic/kernel/effects.py:26-28`). Effects outside retry regions are written to a durable ledger as an intent
   row before the call and an outcome row after it; an unknown outcome stops the run for the operator.
   Compensating actions (sagas) are deferred (INTENSE row 2).
7. **Automation Bias:** a real risk: a passed check can be over-trusted. The draft cited Rozenblit & Keil's
   illusion of explanatory depth, which concerns people overrating their own understanding; over-reliance on
   automated aids is studied as automation bias (e.g. Parasuraman & Riley 1997). Symblic 2.3's the host executor run
   view lists the checks a run evaluated, or says that nothing tested the answers (INTENSE row 7). Fingerprints
   are comparison keys, not certificates ([SPEC.md](SPEC.md) §3).

### 24.2 Risk Matrix, Corrected

| Claimed vulnerability | Source named in the draft | What the code does | Assessment |
| :--- | :--- | :--- | :--- |
| **No proof terms** | Proof Theory (Howard 1969) | No proof terms in 2.4 (2.5 checks supplied ones in a bounded fragment); answer checks are empirical; the spec says so | Accurate for 2.4; not a contradiction, since no answer check is claimed as a proof |
| **Schema loss of nuance** | Formal Semantics (Montague 1970) | Author-defined record fields; `ambiguous` readings | Real design risk for authors; no certainty is claimed |
| **"Verification trilemma"** | Computability Theory (Rice 1953) | Explicit step budget and enumeration cap; no decidability or soundness claim | Misapplied theorem |
| **`steered` decisions** | Confused Deputy (Hardy 1988) | Untrusted text cannot write act arguments unless the program opts in with `allow_untrusted`; steered choices reported; `needs_owner` flags weighty acts; full mode approves steered and opted-in acts | Real host-policy risk in full mode; "laundering" is false |
| **Shortcut learning** | Statistical Learning (Geirhos 2020) | No training pipeline | Not applicable today |
| **Irreversible effects** | Transactions (Gray 1981) | Acts refused in retry regions; durable intent/outcome ledger | Premise false |
| **Automation bias** | Cognitive Science (Rozenblit & Keil 2002) | Run view lists evaluated checks or says none ran | Real human-factors risk; partly mitigated |

---

## 25. Quantum Mathematics and Symblic (Q-Symblic): Proposals and What Was Built

The draft claimed that quantum mechanics "provides the foundational mathematics required to resolve Symblic's
deepest classical bottlenecks". That claim is withdrawn. Nothing in Symblic is quantum, and a language model's
output distribution is a classical probability distribution, not a quantum state ([REVIEW-2.3.md](REVIEW-2.3.md),
"Recurring errors about the mathematics"). REVIEW-2.3 rejected the guarantees and built a few exact, finite
computations that the proposals named. Each mapping below states what was proposed and what happened.

### 25.1 The Six Proposed Quantum Mappings
1. **Birkhoff-von Neumann Quantum Logic (1936):** the proposal was to replace Boolean propositions with
   projection operators on a Hilbert space. Rejected: nothing defines which matrices would stand for a
   program's propositions or how to estimate them from model calls, and `and` keeps its Boolean meaning
   (QUANTUM-FOUNDATIONS row 2). Built: exact rational projector algebra, `is_projector`, `commutator` and
   `commutes`, for matrices up to 8 × 8 ([OPERATORS.md](OPERATORS.md)).
2. **Quantum Cognition (Busemeyer & Bruza 2012):** when an outcome can be reached along two unobserved paths,
   quantum probability adds an interference term $2 \cos(\theta) \sqrt{p_1 p_2}$ to the classical sum
   $p_1 + p_2$. These models are used to describe how people's judgements depart from classical probability,
   including question-order effects. The proposal to replace Symblic's probabilities with them was rejected
   (QUANTUM-FOUNDATIONS row 3). Built: `ordered_probability` gives what the projector model predicts for yes/no questions asked in
   order, including the QQ equality (Wang & Busemeyer 2013), and `order.qq_gap` measures the matching quantity
   from counted answers. `permute=K` measures how a vote depends on option order. These compute on a model the
   author supplies; they do not describe a language model's internal state.
3. **DisCoCat and the ZX-Calculus:** DisCoCat is due to Coecke, Sadrzadeh & Clark (2010); the draft credited
   "Coecke, Abramsky, Clark". Categorical quantum mechanics is Abramsky & Coecke (2004), and the ZX-calculus is
   Coecke & Duncan (2011). The proposal, a semantic normal form that would fix what a model answers, was
   rejected as a claim; the construction is a deferred research direction: compare a small tensor pipeline
   with structured extraction on negation and role reversal (QUANTUM-FOUNDATIONS row 5;
   [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).
4. **Measurement and Einselection (Zurek 2003):** the proposal modelled the network's latent space as a density
   matrix, checks as POVMs, and typed outputs as einselection. Rejected: there is no mechanism beyond the typed
   schema and parser, and the quantities cannot be observed from black-box model calls (QUANTUM-FOUNDATIONS rows
   3–4).
5. **Ising Hamiltonians:** the draft said this "generalizes" the SPD quadratic solver and solves constraints by
   Simulated Quantum Annealing and the Rayleigh-Ritz principle, "bypassing classical local minima". That is
   false. Minimizing an SPD quadratic over $\mathbb{R}^n$ is one linear solve with a unique minimizer (Boyd &
   Vandenberghe 2004, Example 4.5). Finding a ground state of an Ising spin glass over $\{-1, +1\}^n$ is NP-hard
   in general (Barahona 1982), and ground states need not be unique. Annealing is a heuristic with no
   optimality guarantee. Rayleigh-Ritz concerns eigenvalue problems and does not remove the hardness. The
   QUBO/annealing route was deferred, and a classical solver backend waits for evidence that real programs hit
   the 20 000-value enumeration cap. Built instead: `ising_minimize` and `ising_energy` evaluate every state of
   at most 16 spins, with
   $E(s) = -\sum_i h_i s_i - \sum_{i<j} J_{ij} s_i s_j$, and report the exact minimum and how many states attain
   it. No annealing ([DISCRETE.md](DISCRETE.md); QUANTUM-FOUNDATIONS row 6).
6. **Linear Types & No-Cloning (Wootters & Zurek 1982; Girard 1987):** the draft said Symblic "implements" linear
   logic for capabilities with compile-time security. It does not, and no-cloning does not imply linear logic or
   capability security (REVIEW-2.3, "Recurring errors about the mathematics"). Capabilities are catalogue names,
   not values. Built: the `SYM_SAME_KEY` warning for two `act` statements on one path with the same capability
   and literal key; affine one-use handles are a research direction (QUANTUM-FOUNDATIONS row 7).

---

## 26. Quantum Mechanics and Computational Determinism: What Is Deterministic in Symblic

A question the draft raised: *Does introducing quantum mechanics make Symblic less deterministic?*

**No quantum mechanics was introduced, so the question does not arise.** The 2.3 operator and Ising adapters
are exact rational computations, as deterministic as the rest of the kernel. Kernel determinism concerns the
kernel's own computation and replay; it does not make model outputs deterministic.

### 26.1 Physics and Simulation
- **Schrödinger Evolution ($i\hbar \partial_t |\psi\rangle = \hat{H} |\psi\rangle$):** for a closed system the
  evolution is linear, unitary and deterministic: $|\psi(0)\rangle$ determines the state at all later times.
- **Born Rule (Born 1926):** a measurement's outcomes have probabilities given by squared amplitudes. Computing
  those probabilities exactly is deterministic; drawing an outcome is not. Symblic simulates no quantum system:
  the operator adapter handles real symmetric projectors only, with no complex amplitudes, density matrices or
  non-projective measurements ([OPERATORS.md](OPERATORS.md)).

### 26.2 What Is and Is Not Deterministic in Symblic
- **Kernel:** the same program, inputs and kernel identity give the same values and fingerprints. The
  cross-host conformance receipt tested this on a fixed corpus ([RESULTS.md](RESULTS.md)).
- **Replay:** a lock serves recorded replies and asks no model. The 2.2 quadratic run, locked and replayed, gave
  the same fingerprint with zero model calls ([RESULTS.md](RESULTS.md)).
- **Fresh model calls:** not deterministic in general. GPU arithmetic and batching vary outputs; Symblic records
  the replies.

The draft's three reasons for calling Symblic "pseudo-deterministic", corrected:
1. **Prompt order effects:** a different order is a different prompt, not hidden nondeterminism. `permute=K`
   (2.3) measures whether a vote's winner survives K orders of its options.
2. **Retries:** they are not a random walk. Each retry carries the rejected value and the failed condition (and,
   without a `because`, the kernel's values), samples use recorded seeds, and retries are capped at 5.
3. **GPU non-associativity:** it varies fresh generation; it does not break replay, which serves recorded
   replies (REVIEW-2.3, "Recurring errors about Symblic").

### 26.3 Proposed "Quantum" Remedies and Their Outcomes
1. **Density Matrices "eliminating prompt-order drift before generation begins":** built in 2.3 in a reduced
   form as `permute=K` (QUANTUM-DETERMINISM row 1), which measures order sensitivity. Nothing eliminates it, so
   the claim as stated does not hold.
2. **"Confluent" ZX-Calculus Rewriting:** false as stated. Backens (2014) and Vilmart (2019) are completeness
   results, not confluence results. The claim was rejected; a bounded checker of circuit rewrites by exact
   matrix equality is a deferred research direction (QUANTUM-DETERMINISM row 2).
3. **Ising Ground States with "a unique global minimum":** false. The minimum energy is a single number, but the
   states that attain it need not be unique: with no field, flipping every spin gives another ground state.
   Finding one is NP-hard in general (Barahona 1982). Built: exhaustive `ising_minimize`, which reports how many
   ground states there are (QUANTUM-DETERMINISM row 3).
4. **No-Cloning "eradicating concurrency race conditions":** false; no-cloning does not imply it. Symblic's
   bindings are immutable (single assignment), which already rules out the races described
   (QUANTUM-DETERMINISM row 4).
5. **Cyclotomic Number Fields "eliminating GPU reduction drift":** rejected. The kernel is already exact, and GPU
   drift happens inside model inference, which kernel arithmetic cannot change; replay sidesteps it
   (QUANTUM-DETERMINISM row 6).

---

## 27. Mathematical Physics: The September 2026 Navier-Stokes Announcement and Physics Proposals

### 27.1 The Navier-Stokes Announcement
- **What was announced:** on 8 September 2026 OpenAI reported a Lean-formalised proof of finite-time blow-up
  for the 3D Navier-Stokes equations under a smooth external force
  ([announcement](https://openai.com/index/navier-stokes-solution/)). When reported it was unrefereed and its
  credit was disputed
  ([Smithsonian](https://www.smithsonianmag.com/smart-news/ai-may-have-solved-a-longstanding-math-problem-with-a-million-dollar-prize-it-ignited-a-controversy-over-who-gets-credit-180989472/);
  [REVIEW-2.3.md](REVIEW-2.3.md)).
- **What the draft added, corrected:** a forced blow-up is not a loophole. Fefferman's official Clay problem
  statement lists breakdown of solutions with a forcing term (statements C and D) as a resolution. The draft's
  claims that "the mathematical community (Tao, Buckmaster) revealed that the AI engaged in Specification Gaming"
  and that the solution has fluids "vaporizing at the atomic scale" cite no source, and REVIEW-2.3 found them
  unsupported. Nothing in Symblic depends on them (REVIEW-2.3, "Recurring errors about the mathematics").
- **The lesson that does hold:** a machine-checked proof proves the statement as formalised. Whether that
  statement is the intended problem must be reviewed separately, and physical conservation laws do not close
  that gap. The same holds for Symblic: a passed check establishes conformance to the encoded predicate
  ([SPEC.md](SPEC.md) §5).

### 27.2 Physics Proposals and Their Outcomes
These are the historical proposal outcomes; item 5 has a finite implementation. Later constructive
experiments remain available under [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md).
1. **Sobolev Spaces & BKM Regularity:** rejected. The Beale-Kato-Majda criterion (Beale, Kato & Majda 1984) is a
   blow-up criterion for smooth solutions of the 3D Euler equations (the same criterion holds for
   Navier-Stokes): the solution can be continued past time $T$ exactly when $\int_0^T \|\omega\|_{L^\infty} dt < \infty$. That
   integral is of the vorticity's maximum, not enstrophy ($\int |\omega|^2 dx$). It detects blow-up; it does not
   prevent it. No computable "vorticity" exists for an execution trace, and no `enstrophy` builtin exists (a
   call fails with "unknown function enstrophy"). What exists: step, depth and call budgets (PHYSICS row 1).
2. **Symplectic Geometry & Noether Currents (Arnold 1989; Noether 1918):** rejected. As checks they are either
   vacuous ($d(dq \wedge dp) = 0$ holds for every trajectory) or wrong for the stated system (energy is not
   conserved in viscous flow). What exists: conservation asserts the author writes, such as ledger balances
   (PHYSICS row 2).
3. **Wilsonian Renormalization Group (Wilson 1971):** rejected. The premise about capsules is false, and a hidden
   model summariser would add an unchecked, lossy step. Source-linked summaries measured against full text are
   a research direction (PHYSICS row 3; [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).
4. **Information Geometry (Amari 1985, 1998):** the claim was rejected. No natural-gradient code exists. The
   quadratic solver accepts any rational SPD matrix up to 32 × 32, so a supplied Fisher matrix $F$ and gradient
   $g$ would give one natural-gradient direction $F^{-1} g$ by one exact solve. Natural-gradient descent is an
   iterative method that needs $F$ at every step, and one solve is not motion along a geodesic. Comparing
   ordinary and natural-gradient updates on a small explicit distribution is a deferred research direction
   (PHYSICS row 4).
5. **Optimal Transport (Villani 2009; Kantorovich 1942):** built in a reduced form. `vote=median` takes the
   weighted lower median, a Wasserstein-1 barycenter of point answers on the line. If more than half the total
   weight remains within a bounded interval, outliers cannot move the median outside that interval; a
   minority can still change which interior value is selected. `within=T` reports agreement around it, and `wasserstein1` gives the exact 1D Wasserstein-1
   distance ([TRANSPORT.md](TRANSPORT.md)). The Wasserstein-2 barycenter of point answers would be their
   weighted mean, which one outlier moves without bound. Majority voting stays the default; `vote=median` is
   opt-in for numeric answers (PHYSICS row 5).

---

## 28. Analogies from Higher Physics and Mathematics: Proposals and Outcomes

The draft said these frameworks elevate Symblic "into a truly unified computational universe". None is
implemented. REVIEW-2.3 rejected each guarantee and built two small mechanisms where a computable core existed
([REVIEW-2.3.md](REVIEW-2.3.md), GRAND-UNIFICATION table).

### 28.1 The Six Proposals
1. **Navier-Stokes and Leray Projection:** Tao (2016) proves finite-time blow-up for an averaged Navier-Stokes
   equation; it does not prove that Navier-Stokes simulates a Turing machine. Leray-projection contracts were
   deferred. Built instead: `reconcile`, the nearest values that satisfy explicit linear constraints, reported
   as a repair with how far each value moved; nothing is projected silently ([PROJECTION.md](PROJECTION.md);
   GRAND row 1). Failed checks are not "eliminated": they retry or fail the run.
2. **AdS/CFT (Maldacena 1998) and Ryu-Takayanagi (2006):** rejected. AdS/CFT is a conjecture about specific
   physical theories, the Ryu-Takayanagi formula applies to holographic theories, and no definable mechanism
   detects hallucinations this way. The measurable uncertainty signals that exist (vote entropy, lists of
   readings) are explicitly not correctness checks (GRAND row 2).
3. **String Worldsheets (Polyakov 1981):** rejected; no engineering content (GRAND row 3). No construction makes
   programs immune to prompt injection; Symblic's defence is its information-flow labels (§24.1, item 4).
4. **Mirror Symmetry (Candelas et al. 1991) & T-Duality:** rejected as unsound or without content (GRAND rows
   4–5). Renaming a hard constraint problem does not make it tractable.
5. **Topos Theory and Čech Cohomology (SGA 4):** whether local answers glue is decided on their overlaps (degree
   0), not by $\check{H}^1$. Built: `records.conflicts` and `records.agree`, agreement of two records on the
   fields they share; agreement is not correctness (GRAND row 6).
6. **Homotopy Type Theory and Univalence:** rejected as a claim, construction deferred. Univalence turns a
   given equivalence into an identity; it constructs none. Explicit forward and backward record mappings,
   checked by round trips on a finite domain, are a research direction (GRAND row 7). Named types already
   resolve structurally.

---

## 29. The "Universal Epistemic Operating System" Proposal: Status

The draft combined the proposals above into a five-layer "Universal Epistemic Operating System". The table
records those historical proposals, not the complete current architecture. The practical operating layer now
combines explicit claims and dependencies, checked model/human construction, durable execution, reproducible
records and typed agent graphs. The installed task-card and delegation additions extend that layer (§29.3).

### 29.1 The Five Proposed Layers

| Layer | Proposed component | Outcome | What exists |
|---|---|---|---|
| 5. Intersubjective coordination | Typed speech acts (`Observation`, `Affect`, `Need`, `Request`) | Rejected as built-in types | Example `13-two-accounts.sym` with quote checks |
| 5 | Aumann common-knowledge partitions | Deferred as an engine; finite model built | `common_knowledge` and related builtins on declared partitions (≤ 64 states) |
| 5 | Multi-frame adequacy | Rejected | Provenance labels; families counted by lineage |
| 4. "Holographic semantic compiler" | AdS/CFT and Ryu-Takayanagi surfaces | Rejected | Nothing |
| 4 | ZX-calculus tensor networks | Claim rejected; construction deferred | Nothing |
| 4 | Univalence for schema transport | Claim rejected; construction deferred | Named types resolve structurally |
| 3. "Fluid runtime" | Leray projection | Deferred | `reconcile` (explicit, reported repair) |
| 3 | BKM "enstrophy" bounds | Rejected | Step, depth and call budgets |
| 3 | Renormalization-group context compression | Rejected | Author-chosen context; capsule reports omissions |
| 2. Quantum logic & solver | Orthomodular projection lattices | Rejected | Rational projector algebra (≤ 8 × 8) |
| 2 | POVM measurement and decoherence | Rejected | Nothing |
| 2 | Ising ground states via simulated quantum annealing | Deferred (no annealing); exhaustive form built | `ising_minimize` (≤ 16 spins, with the ground-state count) |
| 1. Kernel | Cyclotomic number fields | Rejected | Exact rationals; 30-place Decimal for transcendental functions |
| 1 | Linear logic / no-cloning for capabilities | Built in a reduced form (`SYM_SAME_KEY`); linear types deferred | `SYM_SAME_KEY` warning |
| 1 | Symplectic 2-form conservation | Rejected | Author-written conservation asserts |

### 29.2 An Analogy: Continuous and Discrete Computation
As an analogy only: a neural model computes with continuous vectors and then samples discrete tokens, while the
kernel computes with exact discrete values. The draft called this "the computational manifestation of the
wave-particle duality" and "the quantum field theory of computation". That is a metaphor with sharp limits:
nothing in Symblic is quantum, no duality theorem connects the two parts, and neither part is "incorruptible".
A run is only as right as its checks, its inputs and its code. What Symblic actually joins is a typed model
call and an exact evaluator, connected by checks the author writes.

### 29.3 Constructive operating layer: installed foundation and construction interfaces

| Capability | Concrete mechanism | Status updated 5 October 2026 |
|---|---|---|
| Human formal statements and model proofs | Controlled formula parser, finite-domain lowering, nested and flat natural-deduction certificates | Existing reform proof lane; checks caller-held premises/goals |
| Fresh-context project construction | Spec-sheet units, exposed examples, checked code and assembly | Existing local-model case study; installed task cards add full declared dependency closure |
| Portable project memory | Source/runtime/contract/dependency pins, exact artifacts, local rechecks and manifests | Installed in `symblic/spec/contracts.py` and `symblic/spec/build.py`; not a fresh-generation uniqueness guarantee |
| Agent-callable operations | Bounded templates compile into native programs and return canonical accepted values | Installed in `symblic/delegate/contracts.py` and `symblic/delegate/run.py`; existing admission and execution pins retained |
| Evidence and orchestration | Runtime conditional provenance and dependency checks; separate snapshot notebooks for operator revisions/disagreements; typed graphs, durable recovery and frozen policy comparison | RC2 foundation is deployed. The notebook is included in the later 5 October reform. Its 32 Python checks and two browser journeys are component evidence, not a new model measurement. Notebook edits cannot mutate completed runs; see [REFORM-3](REFORM-3.md) |
| One-step proof construction, adaptive decomposition and learned graph topology | Small construction actions with generic checking and measured routing | Incremental sessions are installed; broader adaptive/learned mechanisms remain experiments |

The proposed architectural name **Symblic Cognitive Fabric** describes this composition of constructors,
checkers, persistent state and agent graphs. It is not a claim that an agent graph has become a neural tensor
or that its novelty is established. [RESEARCH-TRANSFER.md](RESEARCH-TRANSFER.md) specifies the next measurable
advances, including a vorticity-derived numerical construction task that adds no domain solver to the kernel.

---

## References

Primary sources for results named above. Machine-learning and agent literature is cited through the keys in
[PRIOR-ART.md](PRIOR-ART.md), whose reference list gives links. A work named in the text without an entry here
is named without a full citation.

- Abramsky, S., and Coecke, B. (2004). A categorical semantics of quantum protocols. *Proceedings of the 19th
  IEEE Symposium on Logic in Computer Science (LICS 2004)*.
- Amari, S. (1985). *Differential-Geometrical Methods in Statistics*. Lecture Notes in Statistics 28, Springer.
- Amari, S. (1998). Natural gradient works efficiently in learning. *Neural Computation* 10(2), 251–276.
- Amodei, D., et al. (2016). Concrete problems in AI safety. arXiv:1606.06565.
- Apt, K. R., Blair, H. A., and Walker, A. (1988). Towards a theory of declarative knowledge. In J. Minker
  (ed.), *Foundations of Deductive Databases and Logic Programming*, Morgan Kaufmann.
- Arnold, V. I. (1989). *Mathematical Methods of Classical Mechanics*, 2nd ed. Springer.
- Aumann, R. J. (1976). Agreeing to disagree. *The Annals of Statistics* 4(6), 1236–1239.
- Backens, M. (2014). The ZX-calculus is complete for stabilizer quantum mechanics. *New Journal of Physics* 16,
  093021.
- Barahona, F. (1982). On the computational complexity of Ising spin glass models. *Journal of Physics A:
  Mathematical and General* 15, 3241–3253.
- Beale, J. T., Kato, T., and Majda, A. (1984). Remarks on the breakdown of smooth solutions for the 3-D Euler
  equations. *Communications in Mathematical Physics* 94(1), 61–66.
- Biere, A., Cimatti, A., Clarke, E., and Zhu, Y. (1999). Symbolic model checking without BDDs. *TACAS 1999*.
- Birkhoff, G., and von Neumann, J. (1936). The logic of quantum mechanics. *Annals of Mathematics* 37(4),
  823–843.
- Bloom, P. (2016). *Against Empathy: The Case for Rational Compassion*. Ecco.
- Born, M. (1926). Zur Quantenmechanik der Stoßvorgänge. *Zeitschrift für Physik* 37, 863–867.
- Boyd, S., and Vandenberghe, L. (2004). *Convex Optimization*. Cambridge University Press. Example 4.5, printed
  pp. 140–141 ([VARIATIONAL.md](VARIATIONAL.md)).
- Busemeyer, J. R., and Bruza, P. D. (2012). *Quantum Models of Cognition and Decision*. Cambridge University
  Press.
- Candelas, P., de la Ossa, X. C., Green, P. S., and Parkes, L. (1991). A pair of Calabi-Yau manifolds as an
  exactly soluble superconformal theory. *Nuclear Physics B* 359, 21–74.
- Clark, H. H., and Brennan, S. E. (1991). Grounding in communication (linked in [PRIOR-ART.md](PRIOR-ART.md)).
- Coecke, B., and Duncan, R. (2011). Interacting quantum observables: categorical algebra and diagrammatics.
  *New Journal of Physics* 13, 043016.
- Coecke, B., Sadrzadeh, M., and Clark, S. (2010). Mathematical foundations for a compositional distributional
  model of meaning. Lambek Festschrift, special issue of *Linguistic Analysis*. arXiv:1003.4394.
- Davidson, D. (1984). *Inquiries into Truth and Interpretation*. Oxford: Clarendon Press.
- Fefferman, C. L. Existence and smoothness of the Navier–Stokes equation. Clay Mathematics Institute, official
  problem description.
- Fischer, M. J., Lynch, N. A., and Paterson, M. S. (1985). Impossibility of distributed consensus with one
  faulty process. *Journal of the ACM* 32(2), 374–382.
- Geirhos, R., et al. (2020). Shortcut learning in deep neural networks. *Nature Machine Intelligence* 2,
  665–673.
- Girard, J.-Y. (1987). Linear logic. *Theoretical Computer Science* 50(1), 1–101.
- Gray, J. (1981). The transaction concept: virtues and limitations. *Proceedings of VLDB 1981*.
- Hardy, N. (1988). The confused deputy (or why capabilities might have been invented). *ACM SIGOPS Operating
  Systems Review* 22(4), 36–38.
- Harnad, S. (1990). The symbol grounding problem. *Physica D* 42, 335–346.
- Kirkpatrick, J., et al. (2017). Overcoming catastrophic forgetting in neural networks. *Proceedings of the
  National Academy of Sciences* 114(13).
- Lambert, N., et al. (2024). Tülu 3: pushing frontiers in open language model post-training. arXiv:2411.15124.
- Luhmann, N. (1984). *Soziale Systeme*. Frankfurt am Main: Suhrkamp.
- Maldacena, J. (1998). The large N limit of superconformal field theories and supergravity. *Advances in
  Theoretical and Mathematical Physics* 2, 231–252.
- Mirzadeh, I., et al. (2024). GSM-Symbolic: Understanding the limitations of mathematical reasoning in large
  language models. arXiv:2410.05229.
- Nagel, T. (1974). What is it like to be a bat? *The Philosophical Review* 83(4), 435–450.
- Noether, E. (1918). Invariante Variationsprobleme. *Nachrichten von der Gesellschaft der Wissenschaften zu
  Göttingen, Mathematisch-Physikalische Klasse*.
- OpenAI (2023). GPT-4 technical report. arXiv:2303.08774.
- Parasuraman, R., and Riley, V. (1997). Humans and automation: use, misuse, disuse, abuse. *Human Factors*
  39(2), 230–253.
- Polyakov, A. M. (1981). Quantum geometry of bosonic strings. *Physics Letters B* 103(3), 207–210.
- Rice, H. G. (1953). Classes of recursively enumerable sets and their decision problems. *Transactions of the
  American Mathematical Society* 74(2), 358–366.
- Ross, L., and Ward, A. (1996). Naive realism in everyday life: implications for social conflict and
  misunderstanding. In E. S. Reed, E. Turiel and T. Brown (eds.), *Values and Knowledge*, 103–135. Erlbaum.
- Rozenblit, L., and Keil, F. (2002). The misunderstood limits of folk science: an illusion of explanatory
  depth. *Cognitive Science* 26(5), 521–562.
- Ryu, S., and Takayanagi, T. (2006). Holographic derivation of entanglement entropy from AdS/CFT. *Physical
  Review Letters* 96, 181602.
- Shao, Z., et al. (2024). DeepSeekMath: pushing the limits of mathematical reasoning in open language models.
  arXiv:2402.03300.
- Stegenga, J., and Menon, T. (2017). Robustness and independent evidence. *Philosophy of Science*,
  doi:10.1086/692141.
- Tao, T. (2016). Finite time blowup for an averaged three-dimensional Navier-Stokes equation. *Journal of the
  American Mathematical Society* 29(3), 601–674.
- The Univalent Foundations Program (2013). *Homotopy Type Theory: Univalent Foundations of Mathematics*.
  Institute for Advanced Study.
- Ullman, J. D. (1988). *Principles of Database and Knowledge-Base Systems*, Vol. I. Computer Science Press.
- van Emden, M. H., and Kowalski, R. A. (1976). The semantics of predicate logic as a programming language.
  *Journal of the ACM* 23(4), 733–742.
- Vardi, M. Y. (1982). The complexity of relational query languages. *Proceedings of the 14th ACM Symposium on
  Theory of Computing (STOC 1982)*.
- Villani, C. (2009). *Optimal Transport: Old and New*. Springer.
- Vilmart, R. (2019). A near-minimal axiomatisation of ZX-calculus for pure qubit quantum mechanics.
  *Proceedings of the 34th Annual ACM/IEEE Symposium on Logic in Computer Science (LICS 2019)*. Preprint:
  arXiv:1812.09114, titled "A near-optimal axiomatisation of ZX-calculus for pure qubit quantum mechanics".
- Wang, Z., and Busemeyer, J. R. (2013). A quantum question order model supported by empirical tests of an a
  priori and precise prediction. *Topics in Cognitive Science* 5(4), 689–710.
- Wilson, K. G. (1971). Renormalization group and critical phenomena, I and II. *Physical Review B* 4, 3174 and
  3184.
- Wittgenstein, L. (1953). *Philosophical Investigations*, §293.
- Wootters, W. K., and Zurek, W. H. (1982). A single quantum cannot be cloned. *Nature* 299, 802–803.
- Zurek, W. H. (2003). Decoherence, einselection, and the quantum origins of the classical. *Reviews of Modern
  Physics* 75(3), 715–775.
