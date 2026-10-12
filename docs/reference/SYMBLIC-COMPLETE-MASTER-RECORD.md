# Symblic: The Complete Master Record & Technical Compendium

> **AI-generated report, unverified.** This report was written by AI agents from a working dialogue on
> 2026-10-04. Its figures are unreplicated claims from that dialogue (see the clarification below), and
> several sections describe the original private host rather than this repository. See
> [../MADE-WITH-AI.md](../MADE-WITH-AI.md).
**A Comprehensive Synthesis of Token Economics, Systems Architecture, Hardware Placement, Enterprise Patterns, and Offensive Security**

- **Date:** October 4, 2026
- **Permanent Path:** [`docs/reference/SYMBLIC-COMPLETE-MASTER-RECORD.md`](SYMBLIC-COMPLETE-MASTER-RECORD.md)
- **Primary Source Files:** [`tools/symblic`](../../tools/symblic), [`symblic/kernel/language.py`](../../symblic/kernel/language.py), [`symblic/kernel/run.py`](../../symblic/kernel/run.py), [`symblic/kernel/effects.py`](../../symblic/kernel/effects.py), [`docs/reference/SYMBLIC-BREAKTHROUGH-COMPENDIUM.md`](SYMBLIC-BREAKTHROUGH-COMPENDIUM.md), [`tests/kernel/test_symblic_adversarial.py`](../../tests/kernel/test_symblic_adversarial.py)
- **Active Dialogue & Entities:** the operator, Antigravity (Gemini 3.8 Flash), Claude (terminal `f5b1`), Codex (terminal `69f0`) and one other human participant

> **Evidence clarification — 2026-10-05.** This document preserves the October 4 dialogue's proposals and reported figures. The original full prompts, output transcripts, tokenizer pins and provider usage receipts are not supplied here; its numerical savings and cluster success rates are **unreplicated historical claims**, not current measured guarantees. Revised explanations below distinguish implemented interfaces, conditional checks and proposed experiments. Examples are historical illustrations unless linked to a checked fixture. No feature or hardware class is excluded by this review.

---

## Table of Contents
1. [Executive Summary & Thematic Overview](#1-executive-summary--thematic-overview)
2. [Token Economics: The BPE Mechanics & The Unicode Hieroglyphic Trap](#2-token-economics-the-bpe-mechanics--the-unicode-hieroglyphic-trap)
3. [Symblic Core Architecture: The 0-Token Kernel & Sterile Capsules](#3-symblic-core-architecture-the-0-token-kernel--sterile-capsules)
4. [Reported Benchmark: Trip Expense & Policy Auditor](#4-reported-benchmark-trip-expense--policy-auditor)
5. [The Agent Authoring Tax (Meta-Generation Economics)](#5-the-agent-authoring-tax-meta-generation-economics)
6. [Is Symblic Pointless? (Deconstructing the Conceptual Critique)](#6-is-symblic-pointless-deconstructing-the-conceptual-critique)
7. [Reliability of Model Arithmetic and Formal Construction](#7-reliability-of-model-arithmetic-and-formal-construction)
8. [Cross-Agent Dispatch to Claude and Codex](#8-cross-agent-dispatch-to-claude-and-codex)
9. [Bytes on the Kernel vs. Model Weights](#9-bytes-on-the-kernel-vs-model-weights)
10. [How Code Affects Bytes Directly on the Kernel](#10-how-code-affects-bytes-directly-on-the-kernel)
11. [Hardware Systems: CPU Logic Engine vs. GPU CUDA Kernels](#11-hardware-systems-cpu-logic-engine-vs-gpu-cuda-kernels)
12. [The Multi-Model Token Paradox & The High-Dimensional Black Box](#12-the-multi-model-token-paradox--the-high-dimensional-black-box)
13. [Is Symblic a Brute-Force Attack?](#13-is-symblic-a-brute-force-attack)
14. [Enterprise Architecture: Integrating Red Hat Logic](#14-enterprise-architecture-integrating-red-hat-logic)
15. [Offensive Security: Integrating Black Hat Methodologies](#15-offensive-security-integrating-black-hat-methodologies)
16. [Master Comparative Reference Matrix](#16-master-comparative-reference-matrix)

---

## 1. Executive Summary & Thematic Overview

This historical synthesis brings together token-accounting proposals, scoped model requests, checked construction, hardware placement and adversarial verification. Its useful proposals remain available; the original universal savings, impossibility and security claims are not established.

The present review preserves the expense example and reported numerical tables as historical material, repairs inconsistent accounting, and treats GPU kernels, solver construction, incremental rule matching and effect-policy extensions as scoped experiments. Models can construct formal artifacts; they are not restricted to perception. Installed interfaces and finite evidence should be read through [agent entry](AGENT-CARD.md), [task cards](TASK-CARDS.md) and [matched evaluation](MATCHED-EVALUATION.md). The [5 October release evidence](evidence/2026-10-05-reform-install.json) records installation; it does not turn the research proposals below into completed capabilities.

---

## 2. Token Economics: The BPE Mechanics & The Unicode Hieroglyphic Trap

Modern Large Language Models tokenize input strings using subword Byte-Pair Encoding (BPE), such as OpenAI's `cl100k_base` and `o200k_base`, or Google's SentencePiece. In these tokenizers, **character count does not determine token count**.

### Historical routing figures (original complete fixture not supplied)

A routing policy was encoded into four distinct representations and measured across `cl100k_base` and `o200k_base`:

| Representation Format | Example Text | Character Count | Token Count (`o200k`) | Token Delta vs. English |
| :--- | :--- | :--- | :--- | :--- |
| **1. Verbose Natural Language** | *"You are a routing agent. If the query type is technical support, assign it to Tier-2..."* | 293 chars | **61 tokens** | *Baseline* |
| **2. Clean ASCII Symbolic** | `ROLE: Router`<br>`? tech_support -> Q:Tier2_Eng, prio:HIGH`<br>`? billing -> Q:Finance, prio:MED`<br>`* ELSE -> Q:General, prio:LOW` | 133 chars | **47 tokens** | **-23.0%** |
| **3. Unicode Hieroglyphic** | `ROLE: 🔀`<br>`🛠️ ➔ 🏢Eng-2, 🔴`<br>`💳 ➔ 🏢Fin, 🟡`<br>`* ➔ 🏢Gen, 🟢` | 46 chars | **45 tokens** | **-26.2%** |
| **4. Structured JSON** | `{"role": "router", "rules": [{"type": "tech_support", ...}]}` | 220 chars | **68 tokens** | **+11.5%** |

### Character reduction versus token reduction
In Format #3, compressing text from 293 characters to 46 characters (an 84% reduction in text length) yielded only **2 tokens** of additional savings over clean ASCII.

When inspecting the raw byte streams of these characters:
```
Symbol / Word             UTF-8 Byte Sequence                BPE Token Count
----------------------------------------------------------------------------
if                        [105, 102]                         1 token
->                        [45, 62]                           1 token
&&                        [38, 38]                           1 token
user                      [117, 115, 101, 114]               1 token
role                      [114, 111, 108, 101]               1 token

✓                         [226, 156, 147]                    1 to 2 tokens
➔                         [226, 158, 148]                    2 tokens
∈                         [226, 136, 136]                    2 tokens
∧                         [226, 136, 167]                    2 tokens
🔒                        [240, 159, 148, 146]               encoding-dependent
⚠️                        [226, 154, 160, 239, 184, 143]     encoding-dependent
⏱️                        [226, 143, 177, 239, 184, 143]     encoding-dependent
```

> **Measured comparison required:** Unicode is not categorically more expensive. The reported table itself gives 45 Unicode tokens versus 47 ASCII tokens; the full strings are absent, so those figures remain unreplicated. Prefer clear representations and measure the complete request with its exact tokenizer. Preserve source Unicode and semantic distinctions.

---

## 3. Symblic Core Architecture: The 0-Token Kernel & Sterile Capsules

Symblic is a neuro-symbolic domain-specific language designed to establish a strict boundary between probabilistic neural models and deterministic formal computation.

```
┌────────────────────────────────────────────────────────────────────────┐
│                          SYMBLIC PROGRAM (.sym)                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│        AI APPLICATOR            │   │         SYMBLIC KERNEL          │
│    (Claude, GPT, Ollama)        │   │     (Local CPU Execution)       │
├─────────────────────────────────┤   ├─────────────────────────────────┤
│ • Candidate Construction        │   │ • Exact Rational Arithmetic     │
│ • Unstructured Natural Language │   │   (1/3 * 3 = 1; 0.1+0.2=0.3)    │
│ • Rigid JSON Schemas            │   │ • Datalog Horn Clauses          │
│ • Sterile Context Capsules      │   │ • Invariant Assertions (`ensure`)│
│ • Transactional State Rollback  │   │ • No Provider Call             │
└─────────────────────────────────┘   └─────────────────────────────────┘
```

### Operational scope

1. **Local checked computation:** Deterministic arithmetic and relation evaluation need no provider call, but consume CPU, memory and sometimes transport tokens. Exact arithmetic is conditional on input values, program semantics and implementation correctness.
2. **Scoped capsules:** `from` selects dependencies within the configured context policy. Definitions, facts, schemas, provenance and repair feedback can also be present. Use the declared context mode and inspect the actual request. Records and caches may retain capsules; omission from the next request is not secure deletion.
3. **Typed acceptance:** Schemas and parsers define accepted values. Backend constrained decoding is capability-dependent; otherwise malformed responses are refused or repaired. Schema validation alone does not prove factual correctness.
4. **Model construction:** Models can generate expressions, code, proofs and witnesses, not only perceptual extractions. General checkers evaluate the declared obligations; they need not contain a handwritten solution to each task. See [task cards](TASK-CARDS.md) and [incremental proofs](INCREMENTAL-PROOFS.md).

---

## 4. Reported Benchmark: Trip Expense & Policy Auditor

The October 4 narrative attributes its illustrative audit program to [`scratch/expense_auditor.sym`](the host checkout/scratch/expense_auditor.sym).

### The Task
Process unstructured travel notes from a multi-city trip:
* Tokyo: Lunch 4500 JPY, Flight to SFO 850 USD.
* SFO: Hotel 280 USD (Night 1), Client Dinner 140 USD, Taxi 45 USD.
* SFO: Hotel 280 USD (Night 2), Lunch 35 USD, Coffee 8 USD.
* **Policies:** Convert JPY at $1 \text{ JPY} = 0.0067 \text{ USD}$. Cap hotel at $250.00/night. Cap regular meals at $75.00/meal. Exempt client meals and travel from caps. Calculate total claimed, approved reimbursable, and disallowed excess ($60.00). Enforce invariants.

### Historical illustrative program (not a complete acceptance contract)
```symblic
program ExpenseAuditor.

given trip_notes: Text = """
Trip to Tokyo and San Francisco (March 2026).
March 12: Lunch in Tokyo 4500 JPY. Flight to SFO 850 USD.
March 13: Hotel in SFO 280 USD. Dinner with client 140 USD. Taxi 45 USD.
March 14: Hotel in SFO 280 USD. Lunch 35 USD. Coffee 8 USD.
"""

define Expense as Record {
  day: Text,
  cat: one of {meal, hotel, travel, client_meal},
  amount: Number,
  currency: one of {USD, JPY}
}.

# 1. One extraction ask; retries can make additional model calls
ask items: List of Expense "Extract each expense line with its day, category, amount, and currency." from trip_notes with effort=low
ensure len(items) = 8 else retry because "there are exactly 8 expense lines".

# 2. Pure Symblic Kernel (0 TOKENS, Exact Rational Arithmetic)
let usd_items = [
  {day: e.day, cat: e.cat, usd: if e.currency = "JPY" then e.amount * 67 / 10000 else e.amount}
  for e in items
].

let approved_items = [
  {
    day: e.day, cat: e.cat, original_usd: e.usd,
    approved_usd: if e.cat = "hotel" and e.usd > 250 then 250
                  else if e.cat = "meal" and e.usd > 75 then 75
                  else e.usd
  }
  for e in usd_items
].

let total_claimed = sum([e.original_usd for e in approved_items]).
let total_reimbursable = sum([e.approved_usd for e in approved_items]).
let total_disallowed = total_claimed - total_reimbursable.

ensure total_reimbursable <= total_claimed else retry because "approved amount cannot exceed claimed".
assert total_disallowed = 60 because "two hotel nights exceed $250 cap by $30 each".

show total_claimed as "total_claimed_usd".
show total_reimbursable as "approved_reimbursement_usd".
show total_disallowed as "disallowed_excess_usd".
```

### Historical reported static analysis (not rerun here)
```
ExpenseAuditor: ok · profile {'exact': 13, 'open': 1}
```
* **13 statements** (math, currency conversion, policy caps, invariants, assertions) run in the Kernel for **0 tokens**.
* **1 statement** (`ask items`) runs against the model.

### Historical reported runtime output (not independently reproduced)
```
Status: done
Outputs:
  total_claimed_usd: 1668.15
  approved_reimbursement_usd: 1608.15
  disallowed_excess_usd: 60
Exact Kernel Steps vs Model Ask: {'exact': 6, 'open': 1}
```

**Contract gap:** Eight rows and a $60 excess do not prove correct extraction. A duplicate source expense, omitted item paired with an invented replacement, incorrect category or altered uncapped amount can satisfy these checks. A real extraction contract should require source-item identities, coverage, uniqueness, currency/unit checks and explicit policy assumptions. The existing `source_list_contract(..., catalog=...)` / `verify_source_items` already enforce exact declared item membership, coverage and uniqueness; `source_field_contract` / `verify_source_field` check literal field association, units and numeric boundaries. The text library exposes model-constructed `witnessed_items_in` and `witnessed_number_in` receipts. This historical example does not compose those capabilities. A reusable expense/delegation template could do so while keeping undeclared categories and unsupported prose interpretations explicitly unresolved. See [source witnesses](SOURCE-WITNESSES.md). These are fixture-specific expected outcomes, not permission to leak the answer into an evaluated extraction arm.

### Historical reported figures (`o200k_base`; unreplicated)

#### Turn 1: Extraction & Calculations
| Metric | Without Symblic (Just LLM) | With Symblic (Aided) | Difference |
| :--- | :--- | :--- | :--- |
| **Input / Prompt Tokens** | 242 | 371 *(includes JSON schema)* | +129 |
| **Output / Generation Tokens** | **574** *(CoT reasoning)* | **224** *(strictly JSON array)* | **-350 (-61.0%)** |
| **Kernel Computation Tokens** | N/A *(LLM did it)* | **0 tokens** *(exact rational)* | **0 tokens** |
| **Total Tokens Consumed** | **816** | **595** | **-221 (-27.1%)** |

#### Turn 2: Follow-up Pipeline Step ("Draft Notification Email")
* **Historical baseline assumption:** The report says the next prompt has 851 tokens while describing it as 816 + 574 + a user prompt; that arithmetic is inconsistent. A fair baseline may also pass a compact validated state.
  **Turn 2 Total = 919 tokens.**
* **With Symblic:** Only selected prior values are included in this hypothetical next request. Kernel calls `ask email: Text from total_reimbursable, total_disallowed` (81 prompt tokens + 68 generation tokens).  
  **Turn 2 Total = 149 tokens (-83.8% savings).**

#### Cumulative 2-Turn Total
* **Without Symblic:** 1,735 tokens
* **With Symblic:** 744 tokens (**57.1% overall savings**)

---

## 5. The Agent Authoring Tax (Meta-Generation Economics)

The October 4 narrative reports **620** authoring tokens, about **120** tool/validation tokens, about **150** repair tokens, **595** execution tokens and a **1,435** total against **816** for the baseline. These are unreplicated figures. Moreover, the listed components sum to **1,485**, not 1,435; the original total and its four-run break-even are internally inconsistent.

For fixed setup cost `A`, baseline cost per run `R` and Symblic cost per run `S`, reuse breaks even at the least integer `n` with `A + n*S <= n*R`, if `R>S`. With the listed setup components, `A=890`, `R-S=221`, so this hypothetical accounting crosses at **5 runs**. Treating the reported total as authoritative would instead imply `A=840` and 4 runs. Neither calculation reconstructs missing measurements.

Measure authoring labor where observed; keep it unknown otherwise. Include all system/prompt/schema/feedback tokens, failed attempts, fallback, cache treatment and checker cost. Reusable templates can reduce setup effort, but a one-shot task is not automatically a bad use and reuse is not automatically beneficial. Parameterized templates and typed parent/child contracts are already represented by the installed [agent interface](AGENT-CARD.md); local-model quality and savings still need matched measurements.

---

## 6. Is Symblic Pointless? (Deconstructing the Conceptual Critique)

Symblic is an orchestration and assurance interface, not a new arithmetic capability unavailable to ordinary programming languages. Python already supplies exact rational arithmetic through [fractions.Fraction](https://docs.python.org/3/library/fractions.html); other ecosystems also provide exact numeric and verification tools.

Its proposed value is integrating scoped requests, typed candidates, checked construction, provenance, replay and bounded recovery. A formal task can use deterministic code, a model constructor, a solver or a hybrid depending on authoring cost and available algorithms. Creative tasks may still benefit from explicit constraints and evidence. Neither category is categorically excluded.

Compare against an engineered baseline with the same information, checker access, model, budget and feedback—not a deliberately unscoped chat. See [matched evaluation](MATCHED-EVALUATION.md).

A checked arithmetic result is conditional on the extracted values and modeled policy. If a receipt amount is misread, exact downstream arithmetic can still yield the wrong reimbursement. Source witnesses can bind a cited location; they do not by themselves prove that the source is accurate or that the interpretation is complete. Preserve the model's role as constructor and expose those assumptions to the caller.

---

## 7. Reliability of Model Arithmetic and Formal Construction

A directly generated answer is not automatically an exact arithmetic execution. Models can learn procedures and construct derivations; extra autoregressive steps, external memory and tools change the computation available beyond one forward pass. This motivates checked construction, not a categorical claim that LLMs cannot perform formal logic.

The historical `4500 = 1 token, 4501 = 2 tokens` example is incorrect for both named encodings: the independent pinned `tiktoken==0.9.0` ordinary-text fixture counted **2 and 2** for `cl100k_base` and `o200k_base`. Tokenization is a controlled experimental factor, not a universal incapacity argument. The [encoding implementation](https://github.com/openai/tiktoken/blob/0.9.0/tiktoken_ext/openai_public.py) makes tokenizer-specific grouping explicit; these counts are not Ollama billing or local-model counts.

[GSM-Symbolic](https://arxiv.org/abs/2410.05229) reports sensitivity to numerical and irrelevant-clause perturbations in the models and tasks it tested, including drops up to 65%. The authors' interpretation is not a theorem that every model is incapable of deduction. Preserve checked proof/code construction and evaluate actual success, false acceptance, abstention and total cost under a frozen task distribution.

---

## 8. Cross-Agent Dispatch to Claude and Codex

On October 4, 2026, at 20:45 (host local time), these findings were formally transmitted to:
* **Claude (`PTY f5b1` / `dash-f5b1788209dd`)**
* **Codex (`PTY 69f0` / `dash-69f01f8dfe0b`)**
* **Shared Coordination Log:** `~/.local/state/symblic-reform-coordination-20261004.md` (a private record of the original host)

### Historical proposals dispatched (not new agent authority):
1. **Epistemic Warning:** Do not take these findings as dogma; verify and falsify them independently in local test benches.
2. **Parameterized Templates:** Provide `.sym` macro skeletons so agents instantiate variables rather than writing the entire AST from scratch.
3. **Parent-to-Child Delegation Wrappers:** Standardize a native agent wrapper (`symblic.delegate(capsule, subagent)`) that enforces contract boundaries and transactional state rollback on subagents.
4. **Machine-Readable Linter:** Expose `tools/symblic check --agent-json` so agents receive structured, actionable syntax error diagnostics without parsing human CLI output.
5. **Sterile Capsules in Agent Squads:** Enforce context isolation in multi-agent pipelines (squads / the three-agent pipeline / the host executor) to prevent 100k+ token context rot across multi-turn workflows.

---

## 9. Bytes on the Kernel vs. Model Weights

| Concept | What It Is in Symblic |
| :--- | :--- |
| **The Kernel** | A Python interpreter with deterministic computation and explicitly mediated effectful operations ([`class Kernel`](../../symblic/kernel/language.py#L2404)). It does exact math, logic rules, and invariant checks. These deterministic operations need no model call; the broader runtime dispatches `ask`. |
| **Model Weights** | Gigabytes of frozen neural network parameters (floating-point numbers) stored on disk/GPU VRAM. The ordinary `ask` interface requests inference and does not implement weight training. This is not a ban on future explicitly versioned learning backends. |
| **Bytes** | The raw digital data (UTF-8 source files, binary outputs, canonical JSON, and SVG drawings) that Symblic hashes using SHA-256 for cryptographic lockfile verification. |

---

## 10. How Code Affects Bytes Directly on the Kernel

1. **Exact Rational Memory Allocation:** `let third = 1/3` creates exact integer numerator/denominator pairs in RAM, preventing IEEE-754 floating-point drift.
2. **Canonical Output Serialization:** Canonical serialization targets reproducible outputs for supported values and pinned runtime/adapter behavior; finite cross-host tests do not prove universal equivalence of all rendering or external code.
3. **SHA-256 Lockfile Hashes:** Modifying a single character or space in `program.sym` changes the raw input bytes, immediately altering the cryptographic execution fingerprint.

---

## 11. Hardware Systems: CPU Logic Engine vs. GPU CUDA Kernels

The current Python logic engine and neural inference backend have different workloads. CPU execution is a practical baseline for the existing interpreter; accelerated logic remains a legitimate experiment.

CUDA uses SIMT execution; divergent branches can reduce utilization, but this does not establish a universal CPU/GPU speed ratio. CUDA supports general integer operations and memory facilities, not only tensor multiplication. [NVIDIA's SIMT guide](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/writing-cuda-kernels.html) describes the execution model.

The original **10–50× slowdown**, **50 ns for 2 KB**, and **<0.001% overhead** figures were not measured here. Payload size divided by link bandwidth omits launch, synchronization, allocation and transfer latency. Benchmark the actual end-to-end path before deciding placement. Exact arithmetic, integer overflow and reduction ordering need an explicit implementation contract on any device. Floating-point reproducibility depends on operations and configuration; it is not a universal prohibition on GPU verification. [NVIDIA's floating-point guidance](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/mathematical-functions.html) states operation-specific accuracy and behavior.

A useful experiment compares pinned CPU and accelerated implementations on the same logic corpus, including branch-heavy and batchable cases, with observable-result equality, memory, latency, startup cost and failures recorded. No model-performance improvement follows from hardware placement alone.

---

## 12. The Multi-Model Token Paradox & The High-Dimensional Black Box

Token IDs are meaningful relative to a tokenizer and vocabulary; arbitrary existing IDs cannot be passed unchanged between unrelated model families. Decode/re-encode adapters, shared vocabularies and trained interfaces are possible. The original “physically impossible” claim was too broad; this document does not establish a universal vocabulary size or one embedding dimensionality.

Symblic's useful common interface is a declared request, typed candidate and checked result with model/runtime identity. Identical text can produce identical or different answers across models; canonical value agreement does not establish truth or independent evidence.

Models may construct **proofs, programs, plans and witnesses**, as well as extract observations. A checker rejects only violations it can express and evaluate. A wrong extraction or insufficiently specified answer can pass. See [proof construction](PROOF-STEPS.md), [incremental proofs](INCREMENTAL-PROOFS.md) and [agent delegation](AGENT-DELEGATION.md).

Checked escalation can try a declared small-model route and then another route within recorded budgets. Count every attempt, repair, refusal and fallback separately. Local inference still has compute and energy cost; acceptance is not automatically sub-second. The original report's **100% failed 1B tasks / 100% rejection / zero corrupt outputs** has no attached population, exact validators or complete attempt ledger, so it is not adopted as a current performance result. Host state can be committed conditionally; already dispatched external effects cannot generally be rolled back.

---

## 13. Is Symblic a Brute-Force Attack?

Repair is bounded candidate search with feedback; it need not enumerate the space uniformly. A vocabulary-size calculation does not prove that useful search is impossible or that feedback guarantees convergence.

Failed predicates can supply specific feedback, but a weak predicate can also reward the wrong result. For example, universal checks over an empty list may pass unless non-emptiness or source coverage is required. Define completeness, identity and negative examples where the task needs them. `--max-calls` bounds provider dispatches, **not tokens**; request/output limits, local checker work and elapsed time need their own accounting.

SMT or symbolic execution is a useful **optional constructor** for supported formulas. It is not a universal replacement for model construction: translation fidelity, solver theory, finite bounds, resource limits and unknown results remain explicit. A solver can produce a candidate or proof artifact which an appropriate independent checker then validates. [Programming Z3](https://z3prover.github.io/papers/programmingz3.html) documents supported theories and solver interfaces. No general zero-latency or completeness claim is made.

---

## 14. Enterprise Architecture: Integrating Red Hat Logic

These are design proposals, not evidence that the named enterprise products or every analogous feature are installed in Symblic.

1. **Incremental rule matching:** Compare a Rete-style or indexed evaluation strategy with the existing Datalog engine on frozen workloads. Preserve stratification, retractions, provenance roots, bounded evaluation and replay results. The earlier “millions of facts in microseconds” statement lacks a workload and measurement; it does not justify replacing the engine or restricting models to extraction.
2. **Explicit effect authority:** SELinux contexts are policy labels, not cryptographic signatures. Its mandatory access policy is a useful architectural analogy. [Red Hat's SELinux documentation](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/using_selinux/getting-started-with-selinux_using-selinux) describes subject/object labels and access rules. Symblic's actual [effect contract](EFFECTS.md) must govern dispatch; `UNTRUSTED_TAINT` and `act send_email(...)` here are conceptual placeholders, not asserted native builtins. Provenance hashes bind content and do not grant authority or prove origin by themselves.
3. **Durable desired-state reconciliation:** Preserve attempt identities, host authority, cumulative budgets and unresolved external outcomes. An idempotent adapter must define the operation's idempotency key and reconciliation protocol. Merely using `given` or `ensure` neither makes an operation idempotent nor undoes a remote action.

---

## 15. Offensive Security: Integrating Black Hat Methodologies

Adversarial methods are useful engineering work, not a proof that the whole system is impenetrable.

- **Schema-aware and mutation fuzzing:** Extend the existing [adversarial tests](../../tests/kernel/test_symblic_adversarial.py) with Unicode/header injection, malformed structures, duplicate identities, forged receipts, resource exhaustion and restart cases. Check false acceptance and unintended effects as well as parser crashes. A candidate passing `ensure` is insufficient as the test oracle when that predicate is itself incomplete.
- **Symbolic construction:** Preserve the proposal to generate satisfying inputs or counterexamples in a supported formal fragment. A bounded solver can avoid a model call while still consuming time and memory. Recheck results and record unsupported/unknown outcomes; no general zero-latency or 100%-certainty result is established.
- **Taint and capability boundaries:** Test each actual data-to-effect path against the configured [effect policy](EFFECTS.md), host authorization and sandbox. A generic prompt or label cannot guarantee that every indirect injection is blocked. Hash integrity, source fidelity, predicate satisfaction and execution authority remain distinct obligations.

These tests should retain raw public fixtures, frozen source/runtime identities and all assigned outcomes. Report finite coverage and any residual unsupported boundaries.

---

## 16. Master Comparative Reference Matrix

| Dimension | Engineering comparison | Symblic acceptance scope |
|---|---|---|
| Arithmetic | Ordinary languages can also provide exact types | Encoded exact operations on declared values |
| Context | Any agent can pass selected state; compare equivalent baselines | Recorded dependency selection and provenance, not deletion |
| Construction | Models, code and solvers can each construct artifacts | General validators check declared obligations |
| Recovery | Host commits and external actions have different boundaries | Durable identities and unresolved outcomes must survive retry |
| Consensus | Agreement is not independent evidence or truth | Value grouping under an explicit equality contract |
| Security | OS isolation, capabilities and application checks complement one another | Finite tested boundaries; no impenetrability claim |
| Cost | Authoring, full requests, failures and fallback all count | Frozen matched assignments and observed telemetry |
| Acceleration | CPU/GPU and incremental matching are workload-dependent | Semantic parity and measured resource use before adoption |

---


**Implementation status clarification:** The installed [agent card](AGENT-CARD.md) documents `check --agent-json`, named typed delegation templates and durable result transport. [Task cards](TASK-CARDS.md) preserve dependency declarations and construction checks; [incremental proofs](INCREMENTAL-PROOFS.md) support checked step construction. These fulfill substantial parts of the historical interface proposals. The [5 October release evidence](evidence/2026-10-05-reform-install.json) records installation and its scoped live checks; earlier measurements retain their frozen runtime. The hypothetical `symblic.delegate(capsule, subagent)` call is not the exact public API; use the documented CLI/API contract.
