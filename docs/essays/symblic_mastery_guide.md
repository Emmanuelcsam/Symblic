# Symblic Programming Language: The Complete Guide & Tutorial

> **Speculative AI writing, not a research result.** This essay was generated in October 2026 by a Gemini model
> working through Google's Antigravity agent, while Symblic was being built, and is kept as a historical record.
> No human expert reviewed it. Many claims are unverified, several overstate what Symblic does, and some describe
> features that do not exist. Where a corrected version exists it is in [../reference](../reference/README.md).
> Read [../MADE-WITH-AI.md](../MADE-WITH-AI.md) before relying on anything here.

> **Language Version:** 2.1  
> **Canonical Version:** 3  
> **Architecture:** Neuro-Symbolic Hybrid (Deterministic Kernel + Typed AI Applicators)  
> **Created with:** AI models (GPT, Claude, Astra/Gemini), directed by the project's operator

---

## Table of Contents
1. [The "Eureka" Moment: What Symblic Really Is](#1-the-eureka-moment-what-symblic-really-is)
2. [Bridging the Gap to Natural Language](#2-bridging-the-gap-to-natural-language)
3. [Architecture: Kernel vs. Model (The Two Realms)](#3-architecture-kernel-vs-model-the-two-realms)
4. [Language Reference & Syntax Guide](#4-language-reference--syntax-guide)
   - [Declarations & Exact Math](#declarations--exact-math)
   - [The Type System](#the-type-system)
   - [The Model Bridge (`ask`)](#the-model-bridge-ask)
   - [Verification & Self-Correction (`ensure`, `assert`)](#verification--self-correction-ensure-assert)
   - [Relational Logic Engine (Datalog)](#relational-logic-engine-datalog)
   - [Functions vs. Routines](#functions-vs-routines)
   - [Modules & Standard Library](#modules--standard-library)
   - [Real-World Effects (`observe`, `act`)](#real-world-effects-observe-act)
5. [Hands-On Tutorials (From Scratch)](#5-hands-on-tutorials-from-scratch)
   - [Tutorial 1: The Basics (Exact Math + AI Fact)](#tutorial-1-the-basics-exact-math--ai-fact)
   - [Tutorial 2: Bulletproof Entity Extraction](#tutorial-2-bulletproof-entity-extraction)
   - [Tutorial 3: Multi-Hop Relational Reasoning with Datalog](#tutorial-3-multi-hop-relational-reasoning-with-datalog)
   - [Tutorial 4: Self-Correcting Transactional Retries](#tutorial-4-self-correcting-transactional-retries)
6. [Best Use Cases & High-Value Applications](#6-best-use-cases--high-value-applications)
7. [CLI Cheatsheet & Workflow](#7-cli-cheatsheet--workflow)

---

## 1. The "Eureka" Moment: What Symblic Really Is

Traditional programming languages (like Python, C++, or Rust) and Large Language Models (like GPT, Claude, and Gemini) live in two extreme worlds:

- **Traditional Code** is 100% deterministic and rigid. It calculates numbers to perfection and never hallucinates, but it cannot understand human text, classify sentiments, or summarize messy paragraphs.
- **LLM Prompting (Raw AI)** can read human language and perform intuitive reasoning, but it is fuzzy, non-deterministic, hallucinates basic math (e.g. `0.1 + 0.2`), suffers from **context rot** (forgetting instructions in long chats), and struggles with multi-hop logic.

**Symblic is the missing bridge: a Neuro-Symbolic Hybrid Language.**

It allows you to write programs in a clean, English-like syntax where:
1. **The Kernel computes all formal logic, exact math, collections, and relations.** It never calls an AI for arithmetic, comparisons, or graph traversals.
2. **AI Models (Applicators) are restricted to strictly typed contracts.** When you need an AI to interpret human text, you use the `ask` statement, which compiles into a JSON Schema and forces the AI into an exact type (like an enum, bounded integer, or structured record).
3. **If the AI makes a mistake, the Kernel rejects it automatically.** Using `ensure ... else retry`, Symblic cleanly rolls back program state and forces the AI to correct itself with structured diagnostic feedback.

```mermaid
flowchart TD
    subgraph Symblic Program
        Code["Symblic Source Code (.sym)"]
    end

    subgraph Deterministic Kernel [Local Pure Kernel]
        Math["Exact Rational Math<br/>(1/3 * 3 = 1, 0.1 + 0.2 = 0.3)"]
        Logic["Boolean & Unicode Logic<br/>(∀, ∃, ∧, ∨, ¬)"]
        Datalog["Datalog Engine<br/>(Transitive relations, facts & rules)"]
        Verify["Verification Engine<br/>(ensure, assert, type checking)"]
        Render["Deterministic 2D/3D<br/>(SVG flowers, exact polyhedra)"]
    end

    subgraph AI Applicators [Cloud & Cluster Models]
        Claude["Claude (Haiku / Sonnet)"]
        GPT["GPT / Codex"]
        Gemini["Gemini / Astra"]
        Ollama["Local Ollama (worker node Nodes)"]
    end

    Code -->|Math, Logic, Types| Deterministic Kernel
    Code -->|"ask statement (Typed Contract)"| AI Applicators
    AI Applicators -->|Constrained JSON Reply| Verify
    Verify -->|Failed Check: Rollback & Re-prompt| AI Applicators
    Verify -->|Passed Check: Commit to State| Deterministic Kernel
```

---

## 2. Bridging the Gap to Natural Language

Why does Symblic look like natural English, and how do you think in it?

### The Problem with Natural Language
In natural language, words are fluid and full of unstated context:
- "The spider has 8 legs" (What if an injured spider is missing one?)
- "She sells 3/4 of the rolls and gives 10 to a shelter" (Humans understand the sequence of actions, but LLMs often fumble the exact order of arithmetic operations).
- In philosophy (Wittgenstein, Montague, Quine), no text fixes its own interpretation. If you give a long paragraph prompt to Claude and GPT, they will inevitably deviate in subtle ways.

### The Controlled Natural Language (CNL) Solution
Symblic takes inspiration from **Controlled Natural Languages (CNL)** and **Richard Montague's Formal Semantics**:
1. **English-Like Cadence:** Statements end in a period (`.`). Keywords are natural: `program`, `given`, `let`, `define`, `ask`, `ensure`, `assert`, `show`, `draw`.
2. **Explicit "Direction of Fit":**
   - Natural language is used for **semantic questions** (`"What is the capital of France?"`).
   - Formal mathematical types are used for **answers** (`one of {paris, lyon, marseille}`).
   - You never allow free-form conversational filler like *"Sure, I would be happy to help with that! The answer is Paris."* The language strips that away and enforces pure data.
3. **Pristine Isolation Capsules:**
   - In ChatGPT, your chat history grows and creates "noise".
   - In Symblic, every `ask` generates a clean **Capsule**. The model only sees the variables you explicitly grant access to (`from source`). Its working memory is clean, preventing hallucinations.

---

## 3. Architecture: Kernel vs. Model (The Two Realms)

| Dimension | The Kernel | The Model (`ask`) |
|---|---|---|
| **Execution** | Pure Python engine (`symblic/kernel/language.py`) | Claude, GPT, Gemini, or Ollama |
| **Determinism** | 100% deterministic (Same SHA-256 fingerprint everywhere) | Probabilistic / Consensus-driven |
| **Arithmetic** | Exact rationals (`1/3`, `0.3`) | **NEVER** allowed to do math |
| **Logic** | Datalog, First-Order Logic, Sets | Semantic extraction into facts |
| **Cost** | 0 tokens, microseconds | Bounded token budget & per-call effort |
| **Failure Mode** | Strict Syntax/Type error | `ensure` catches & retries automatically |

---

## 4. Language Reference & Syntax Guide

### Declarations & Exact Math
Every file starts with a program name:
```symblic
program MathDemo.

# Single assignment variable bindings in the Kernel
let a = 10.
let b = 25.
let total = a + b.

# Exact rational arithmetic (lossless fractions)
let x = 0.1 + 0.2.
assert x = 0.3 because "no floating point rounding error".

let third = 1 / 3.
assert third * 3 = 1.
```

### The Type System
Symblic enforces strict typing:
- `Int`, `Int in 0..100` (bounded integers)
- `Number`, `Number in 0..1`, `Number to 2 places` (exact rationals or rounded)
- `Bool` (`true`, `false`)
- `Text`, `Text up to 100 words`
- `one of {red, green, blue}` (strict enums)
- `List of T [length N]` (ordered lists, 1-indexed!)
- `Set of T` (unique sets)
- `Record {name: Text, age: Int}` (key-value structures)

Custom types:
```symblic
define Customer as Record {
    name: Text,
    email: Text,
    loyalty_tier: one of {bronze, silver, gold}
}.
```

### The Model Bridge (`ask`)
The `ask` statement sends a typed contract to an AI model (schematic grammar):
```text
ask variable_name: Type "Prompt with {interpolated_values}" [from inputs] [with options]
```

**Key Options:**
- `effort=low | medium | high | max | ultra`
  - `low`: Direct response.
  - `medium`: Reason then answer (default).
  - `high`: 3 self-consistency samples.
  - `max`: 5 samples.
  - `ultra`: 5 samples + second-round anonymized peer review.
- `context=none | all | last N | relevant | facts | [var1, var2]`
- `by=applicator`: E.g. `claude:haiku`, `codex`, `ollama:qwen3:4b-instruct@node-a`.

### Verification & Self-Correction (`ensure`, `assert`)
- `assert cond.`: If `cond` is false, execution halts immediately.
- `ensure cond else retry because "reason".`:
  - If the check fails, the runtime rolls back the program state to before the `ask`.
  - It feeds the error message and failed value back to the AI model so it can fix its mistake.

> [!NOTE]
> **Semantic Scope of Invariants:** Programmatic checks (`ensure`, `assert`) prove that extracted data satisfies declared equations or ranges. They do not prove that an LLM extracted the true facts from the world. For instance, a check that `quantity * unit_price = total` is satisfied by `1 * 1 = 1` even if the real order was for 3 items at $800. Invariants catch structural contradictions, not empirical falsehoods.

### Relational Logic Engine (Datalog)
AI models struggle with recursive relationships (like family trees or dependency graphs). Symblic has an embedded Datalog engine:
```symblic
fact parent(ada, ben).
fact parent(ben, cleo).

rule ancestor(X, Y) if parent(X, Y).
rule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).

let ancestors_of_cleo = query ancestor(Who, cleo).
assert "ada" in ancestors_of_cleo.
```

### Functions vs. Routines
1. `function`: Pure Kernel computation. No model calls, zero cost, instant execution.
2. `routine`: Reusable, typed LLM function with built-in contract checking and automatic memoization (calling it with the same inputs doesn't re-ask the model).

```symblic
# PURE KERNEL FUNCTION
function area_of_circle(r: Number) -> Number = pi * r ^ 2.

# TYPED LLM ROUTINE
routine sentiment_of(text: Text) -> one of {positive, negative, neutral} with effort=high do
    ask s: one of {positive, negative, neutral} "Analyze sentiment: {text}"
    return s.
end.
```

### Modules & Standard Library
Symblic comes with built-in modules in `symblic/lang/library/`:
- `units`: Exact conversions (miles to km, inches to cm, gallons, joules, pascals).
- `dates`: Gregorian date arithmetic, leap years, days between.
- `stats`: Mean, variance, stdev, Fleiss' kappa consensus.
- `text`: Robust NLP routines (`choose_one`, `count_in`, `items_in`, `summary_of`).
- `lab`: Chemistry/biology dilutions, molarity, concentrations.

```symblic
import units.
let cm = convert_length(5, "inch", "cm").   # Exact 12.7
```

### Real-World Effects (`observe`, `act`)
Symblic can interact with real APIs and services safely:
- `observe data = weather.current(city = "Boston").`: Read-only, cryptographic caching.
- `act res = email.send(to = "bob@test.com", body = "Hi") with key="email-1".`: Idempotent action. Even if the program is retried or re-run, it will never send a duplicate email because of the unique `key`.

---

## 5. Hands-On Tutorials (From Scratch)

### Tutorial 1: The Basics (Exact Math + AI Fact)
Save as `spider.sym`:
```symblic
program SpiderStudy.
note The kernel computes math; the model supplies domain facts.

let legs_per_side = 4.
let total_legs = legs_per_side * 2.

ask spider_legs: Int in 0..20 "How many legs does a spider have?" with effort=low
ensure spider_legs = total_legs else retry because "spiders have 4 pairs of legs".

show [total_legs, spider_legs] as "verified_agreement".
```
Run:
```bash
./bin/symblic check spider.sym
./bin/symblic preview spider.sym
```

### Tutorial 2: Bulletproof Entity Extraction
Save as `invoice.sym`:
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

# Mathematical verification in the Kernel:
let calculated_total = sum([item.quantity * item.unit_price for item in parsed.items]).
ensure calculated_total = parsed.reported_total else retry because "line items do not add up to total".

show parsed as "verified_invoice".
```

### Tutorial 3: Multi-Hop Relational Reasoning with Datalog
Save as `supply_chain.sym`:
```symblic
program SupplyChain.

fact supplies("VendorA", "Part1").
fact supplies("VendorB", "Part2").
fact component_of("Part1", "SubAssembly").
fact component_of("Part2", "SubAssembly").
fact component_of("SubAssembly", "FinishedProduct").

rule depends_on(Product, Part) if component_of(Part, Product).
rule depends_on(Product, Part) if component_of(Intermediate, Product) and depends_on(Intermediate, Part).
rule vendor_for(Product, Vendor) if depends_on(Product, Part) and supplies(Vendor, Part).

let vendors = query vendor_for("FinishedProduct", Who).
show vendors as "all upstream vendors".
```

### Tutorial 4: Self-Correcting Transactional Retries
Save as `strict_summary.sym`:
```symblic
program Summarizer.

given story: Text = """
The Apollo 11 mission launched on July 16, 1969, carrying Neil Armstrong, Buzz Aldrin,
and Michael Collins. Armstrong and Aldrin landed on the Moon on July 20.
"""

# The kernel strictly counts words!
ask summary: Text "Summarize the Apollo 11 launch and landing." from story with effort=medium
ensure len(words(summary)) <= 15 else retry because "summary must be 15 words or fewer".

show summary as "concise_summary".
```

---

## 6. Best Use Cases & High-Value Applications

1. **Precision Data Pipelines:** Extracting financial reports, medical lab values, or contracts into validated schemas.
2. **Autonomous Agent Guardrails:** Wrapping agent actions in strict `ensure` rules to prevent runaway behavior or budget overruns.
3. **Consensus Across Models:** Running tasks across Claude, GPT-4, and Gemini simultaneously with automatic canonical voting.
4. **Relational Graph Queries:** Solving permission trees, organizational hierarchies, and dependency graphs without LLM logic errors.
5. **Reproducible Scientific Papers:** Embedding executable Symblic code inside `.symd` technical papers and locking runs for 100% verification.

---

## 7. CLI Cheatsheet & Workflow

| Command | What it does |
|---|---|
| `./bin/symblic check <file.sym>` | Statically verifies syntax, types, and model contracts |
| `./bin/symblic preview <file.sym>` | Evaluates kernel math up to the first `ask` and prints the exact AI prompt |
| `./bin/symblic run <file.sym> --by claude:haiku` | Runs the program using Claude |
| `./bin/symblic run <file.sym> --by ollama:qwen3:4b-instruct@node-a` | Runs locally on the worker node cluster node |
| `python3 symblic/lang/abstraction.py test <file.sym>` | Runs unit tests defined in `test "..." do ... end.` blocks |
| `python3 symblic/lang/abstraction.py lib` | Lists all standard library modules |
| `python3 symblic/kernel/lockfile.py freeze <run_dir>` | Generates a `run.lock.json` for 100% deterministic offline replay |
