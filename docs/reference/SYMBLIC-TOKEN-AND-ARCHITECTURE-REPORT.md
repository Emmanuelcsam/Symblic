# Symblic: Token Economics, Neuro-Symbolic Architecture & Agent Ergonomics

> **AI-generated report, unverified.** This report was written by AI agents from a working dialogue on
> 2026-10-04. Its figures are unreplicated claims from that dialogue (see the clarification below), and
> several sections describe the original private host rather than this repository. See
> [../MADE-WITH-AI.md](../MADE-WITH-AI.md).
**A Comprehensive Compendium of Findings, Benchmarks, and Systems Analysis**

- **Date:** October 4, 2026
- **Authors & Dialogue:** the operator, Antigravity (Gemini 3.8 Flash), Claude (terminal `f5b1`), Codex (terminal `69f0`)

> **Evidence clarification — 2026-10-05.** This document preserves the October 4 dialogue's proposals and reported figures. The original full prompts, output transcripts, tokenizer pins and provider usage receipts are not supplied here; its numerical savings and cluster success rates are **unreplicated historical claims**, not current measured guarantees. Revised explanations below distinguish implemented interfaces, conditional checks and proposed experiments. Examples are historical illustrations unless linked to a checked fixture. No feature or hardware class is excluded by this review.

The subsequent [144-cell matched integration pilot](REFORM-3.md#completed-matched-integration-pilot--5-october-2026-utc)
found 30/48 correct microtask outcomes in both plain and template arms. Recorded
input tokens were 7,608 versus 44,680, with 336 output tokens in each arm; schema
tokens and authoring costs were unknown. That frozen version predates compact
capsules and proof commands. It establishes neither the savings proposed here nor
the effectiveness of later optimizations; those require their own measurements.

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Token Economics: The Unicode Trap & ASCII Efficiency](#2-token-economics-the-unicode-trap--ascii-efficiency)
3. [Symblic Core Architecture: The 0-Token Kernel & Sterile Capsules](#3-symblic-core-architecture-the-0-token-kernel--sterile-capsules)
4. [Reported Benchmark: Trip Expense & Policy Auditor](#4-reported-benchmark-trip-expense--policy-auditor)
5. [The Agent Authoring Tax (Meta-Generation Economics)](#5-the-agent-authoring-tax-meta-generation-economics)
6. [Is Symblic Pointless? (Deconstructing the Conceptual Critique)](#6-is-symblic-pointless-deconstructing-the-conceptual-critique)
7. [Reliability of Model Arithmetic and Formal Construction](#7-reliability-of-model-arithmetic-and-formal-construction)
8. [Bytes on the Kernel vs. Model Weights](#8-bytes-on-the-kernel-vs-model-weights)
9. [Systems Architecture: CPU Logic Engine vs. GPU CUDA Kernels](#9-systems-architecture-cpu-logic-engine-vs-gpu-cuda-kernels)
10. [Multi-Model Unification: Token Sequences vs. Semantic Contracts](#10-multi-model-unification-token-sequences-vs-semantic-contracts)
11. [Cross-Agent Dispatch & Actionable Directives for Claude and Codex](#11-cross-agent-dispatch--actionable-directives-for-claude-and-codex)

---

## 1. Executive Summary

This dialogue proposes reducing repeated agent authoring and request overhead through reusable contracts, scoped context and local checks. It does **not** establish universal token savings, guaranteed model correctness or a required CPU/GPU split.

The historical 27.1% total-token, 61% output-token and 57.1% cumulative savings below are distinct reported quantities, not one generation-token range. Missing fixtures and inconsistent accounting prevent adoption as current benchmark results. The useful engineering objective is accepted task outcomes per measured total cost while retaining model construction of proofs, code and witnesses.

---

## 2. Token Economics: The Unicode Trap & ASCII Efficiency

Prompt optimization often attempts to substitute English words with symbols to save characters. In subword tokenizers (e.g. OpenAI's `cl100k_base`, `o200k_base`, Google SentencePiece), **characters $\neq$ tokens**.

### Historical routing figures (original complete fixture not supplied)

| Format | Text Sample | Characters | Tokens (`o200k`) | Token Delta |
| :--- | :--- | :--- | :--- | :--- |
| **1. Verbose English** | *"You are a routing agent. If the query type is technical support, assign it to Tier-2..."* | 293 chars | **61 tokens** | *Baseline* |
| **2. ASCII Symbolic** | `ROLE: Router`<br>`? tech_support -> Q:Tier2_Eng, prio:HIGH`<br>`? billing -> Q:Finance, prio:MED`<br>`* ELSE -> Q:General, prio:LOW` | 133 chars | **47 tokens** | **-23.0%** |
| **3. Unicode Hieroglyphic**| `ROLE: 🔀`<br>`🛠️ ➔ 🏢Eng-2, 🔴`<br>`💳 ➔ 🏢Fin, 🟡`<br>`* ➔ 🏢Gen, 🟢` | 46 chars | **45 tokens** | **-26.2%** |
| **4. Structured JSON** | `{"role": "router", "rules": [{"type": "tech_support", ...}]}` | 220 chars | **68 tokens** | **+11.5%** |

### Character reduction versus token reduction
In Format #3, reducing text from 293 characters to 46 characters (an 84% reduction in text length) saved only **2 tokens** over clean ASCII.

```
ASCII Word / Symbol       Bytes (UTF-8)      BPE Tokens
--------------------------------------------------------
if                        [105, 102]         1 token
->                        [45, 62]           1 token
&&                        [38, 38]           1 token
user                      [117, 115, ...]    1 token

Unicode Glyph / Emoji     Bytes (UTF-8)      BPE Tokens
--------------------------------------------------------
✓                         [226, 156, 147]    1-2 tokens
➔                         [226, 158, 148]    2 tokens
∈                         [226, 136, 136]    2 tokens
🔒                        [240, 159, 148, 146] encoding-dependent
⚠️                        [226, 154, 160...] encoding-dependent
⏱️                        [226, 143, 177...] encoding-dependent
```

> **Measured comparison required:** Unicode is not categorically more expensive. The reported table itself gives 45 Unicode tokens versus 47 ASCII tokens; the full strings are absent, so those figures remain unreplicated. Prefer clear representations and measure the complete request with its exact tokenizer. Preserve source Unicode and semantic distinctions.

---

## 3. Symblic Core Architecture: The 0-Token Kernel & Sterile Capsules

Symblic separates computation into two distinct domains:

```
┌────────────────────────────────────────────────────────┐
│                   SYMBLIC PROGRAM                      │
│         (e.g., docs/symblic/examples/05-word-problem.sym)       │
└───────────────────────────┬────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
┌───────────────────────────┐ ┌───────────────────────────┐
│     AI APPLICATOR         │ │     SYMBLIC KERNEL        │
│    (Claude, GPT, Ollama)  │ │   (Local Deterministic)   │
├───────────────────────────┤ ├───────────────────────────┤
│ • Candidate Construction  │ │ • Exact Rational Math     │
│ • Unstructured Input      │ │   (1/3 * 3 = 1)           │
│ • Rigid JSON Schemas      │ │ • Datalog Horn Clauses    │
│ • Invariant Rollback      │ │ • Assertions & Contracts  │
│ • Sterile Capsules        │ │ • No Provider Call        │
└───────────────────────────┘ └───────────────────────────┘
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
Parse unstructured travel notes across Tokyo and San Francisco, convert JPY to USD ($1 \text{ JPY} = 0.0067 \text{ USD}$), apply daily hotel caps ($250/night) and meal caps ($75/meal), exempt client entertainment and airfare, verify invariants, and calculate reimbursable vs. disallowed totals.

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

**Contract gap:** Eight rows and a $60 excess do not prove correct extraction. A duplicate source expense, omitted item paired with an invented replacement, incorrect category or altered uncapped amount can satisfy these checks. A real extraction contract should require source-item identities, coverage, uniqueness, currency/unit checks and explicit policy assumptions. The existing `source_list_contract(..., catalog=...)` / `verify_source_items` already enforce exact declared item membership, coverage and uniqueness; `source_field_contract` / `verify_source_field` check literal field association, units and numeric boundaries. The text library exposes model-constructed `witnessed_items_in` and `witnessed_number_in` receipts. This historical example does not compose those capabilities. The shipped executable [expense handoff](EXPENSE-HANDOFF.md) now combines them using ordinary Symblic statements: separate caller contracts, one-item fresh requests, exact source fields, complete unique catalog coverage and rational accounting. Category/date decisions and the catalog universe remain explicit caller premises; unsupported prose interpretations remain unresolved. See [source witnesses](SOURCE-WITNESSES.md). These are fixture-specific expected outcomes, not permission to leak the answer into an evaluated extraction arm.

### Historical reported figures (`o200k_base`; unreplicated)

#### Turn 1: Extraction & Audit Calculations
| Metric | Without Symblic (Just LLM) | With Symblic (Aided) | Difference |
| :--- | :--- | :--- | :--- |
| **Input / Prompt Tokens** | 242 | 371 *(includes JSON schema)* | +129 |
| **Output / Generation Tokens**| **574** | **224** *(strictly JSON array)* | **-350 (-61.0%)** |
| **Kernel Computation Tokens** | N/A *(LLM did it in CoT)* | **0 tokens** *(exact rational)* | **0 tokens** |
| **Total Tokens Consumed** | **816** | **595** | **-221 (-27.1%)** |

#### Turn 2: Follow-up Action ("Draft Manager Notification Email")
* **Historical baseline assumption:** The report says the next prompt has 851 tokens while describing it as 816 + 574 + a user prompt; that arithmetic is inconsistent. A fair baseline may also pass a compact validated state.
  **Turn 2 Total = 919 tokens.**
* **With Symblic:** Only selected prior values are included in this hypothetical next request. Kernel passes only `from total_reimbursable, total_disallowed` (81 prompt tokens + 68 generation tokens).  
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

## 8. Bytes on the Kernel vs. Model Weights

A common point of confusion is what "bytes on the kernel" refers to.

### Comparison Table
| Concept | What It Is in Symblic |
| :--- | :--- |
| **The Kernel** | A Python interpreter with deterministic computation and explicitly mediated effectful operations ([`class Kernel`](../../symblic/kernel/language.py#L2404)). It does exact math, logic rules, and invariant checks. These deterministic operations need no model call; the broader runtime dispatches `ask`. |
| **Model Weights** | Gigabytes of frozen neural network parameters (floating-point numbers) stored on disk/GPU VRAM. The ordinary `ask` interface requests inference and does not implement weight training. This is not a ban on future explicitly versioned learning backends. |
| **Bytes** | The raw digital data (UTF-8 source files, binary outputs, canonical JSON, and SVG drawings) that Symblic hashes using SHA-256 for cryptographic lockfile verification. |

### How Code Directly Affects Bytes
1. **Exact Rational Memory Allocation:** `let third = 1/3` creates exact integer numerator/denominator pairs in RAM, preventing IEEE-754 floating-point drift.
2. **Canonical Output Serialization:** Canonical serialization targets reproducible outputs for supported values and pinned runtime/adapter behavior; finite cross-host tests do not prove universal equivalence of all rendering or external code.
3. **SHA-256 Lockfile Hashes:** Modifying a single character or space in `program.sym` changes the raw input bytes, immediately altering the cryptographic execution fingerprint.

---

## 9. Systems Architecture: CPU Logic Engine vs. GPU CUDA Kernels

The current Python logic engine and neural inference backend have different workloads. CPU execution is a practical baseline for the existing interpreter; accelerated logic remains a legitimate experiment.

CUDA uses SIMT execution; divergent branches can reduce utilization, but this does not establish a universal CPU/GPU speed ratio. CUDA supports general integer operations and memory facilities, not only tensor multiplication. [NVIDIA's SIMT guide](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/writing-cuda-kernels.html) describes the execution model.

The original **10–50× slowdown**, **50 ns for 2 KB**, and **<0.001% overhead** figures were not measured here. Payload size divided by link bandwidth omits launch, synchronization, allocation and transfer latency. Benchmark the actual end-to-end path before deciding placement. Exact arithmetic, integer overflow and reduction ordering need an explicit implementation contract on any device. Floating-point reproducibility depends on operations and configuration; it is not a universal prohibition on GPU verification. [NVIDIA's floating-point guidance](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/mathematical-functions.html) states operation-specific accuracy and behavior.

A useful experiment compares pinned CPU and accelerated implementations on the same logic corpus, including branch-heavy and batchable cases, with observable-result equality, memory, latency, startup cost and failures recorded. No model-performance improvement follows from hardware placement alone.

---

## 10. Multi-Model Unification: Token Sequences vs. Semantic Contracts

Token IDs are meaningful relative to a tokenizer and vocabulary; arbitrary existing IDs cannot be passed unchanged between unrelated model families. Decode/re-encode adapters, shared vocabularies and trained interfaces are possible. The original “physically impossible” claim was too broad; this document does not establish a universal vocabulary size or one embedding dimensionality.

Symblic's useful common interface is a declared request, typed candidate and checked result with model/runtime identity. Identical text can produce identical or different answers across models; canonical value agreement does not establish truth or independent evidence.

Models may construct **proofs, programs, plans and witnesses**, as well as extract observations. A checker rejects only violations it can express and evaluate. A wrong extraction or insufficiently specified answer can pass. See [proof construction](PROOF-STEPS.md), [incremental proofs](INCREMENTAL-PROOFS.md) and [agent delegation](AGENT-DELEGATION.md).

Checked escalation can try a declared small-model route and then another route within recorded budgets. Count every attempt, repair, refusal and fallback separately. Local inference still has compute and energy cost; acceptance is not automatically sub-second. The original report's **100% failed 1B tasks / 100% rejection / zero corrupt outputs** has no attached population, exact validators or complete attempt ledger, so it is not adopted as a current performance result. Host state can be committed conditionally; already dispatched external effects cannot generally be rolled back.

---

## 11. Cross-Agent Dispatch & Actionable Directives for Claude and Codex

On October 4, 2026, at 20:45 (host local time), these findings were formally transmitted to:
* **Claude (`PTY f5b1` / `dash-f5b1788209dd`)**
* **Codex (`PTY 69f0` / `dash-69f01f8dfe0b`)**
* **Shared Coordination Log:** `~/.local/state/symblic-reform-coordination-20261004.md` (a private record of the original host)

### Historical proposals dispatched (not new agent authority):
1. **Epistemic Stance:** Do not take these findings as dogma; verify and falsify them independently in local test benches.
2. **Parameterized Templates:** Create reusable `.sym` template skeletons in `host_executor_lib/` or `symblic/lang/library/` so agents instantiate schemas rather than synthesizing raw AST grammar from scratch.
3. **Parent-to-Child Delegation Wrappers:** Standardize a native agent wrapper (`symblic.delegate(capsule, subagent)`) that enforces contract boundaries and transactional state rollback on subagents.
4. **Machine-Readable Linter:** Expose `tools/symblic check --agent-json` so agents receive structured, actionable syntax error diagnostics without parsing human CLI output.
5. **Sterile Capsules in Agent Squads:** Enforce context isolation in multi-agent pipelines (squads / the three-agent pipeline / the host executor) to prevent 100k+ token context rot across multi-turn workflows.

**Implementation status clarification:** The installed [agent card](AGENT-CARD.md) documents `check --agent-json`, named typed delegation templates and durable result transport. [Task cards](TASK-CARDS.md) preserve dependency declarations and construction checks; [incremental proofs](INCREMENTAL-PROOFS.md) support checked step construction. These fulfill substantial parts of the historical interface proposals. The [5 October release evidence](evidence/2026-10-05-reform-install.json) records installation and its scoped live checks; earlier measurements retain their frozen runtime. The hypothetical `symblic.delegate(capsule, subagent)` call is not the exact public API; use the documented CLI/API contract.
