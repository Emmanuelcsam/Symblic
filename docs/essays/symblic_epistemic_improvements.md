# Improving Symblic via Intersubjectivity: Epistemic Types, Multi-Frame Verification, and Theory of Mind in Language Design

> **Speculative AI writing, not a research result.** This essay was generated in October 2026 by a Gemini model
> working through Google's Antigravity agent, while Symblic was being built, and is kept as a historical record.
> No human expert reviewed it. Many claims are unverified, several overstate what Symblic does, and some describe
> features that do not exist. Where a corrected version exists it is in [../reference](../reference/README.md).
> Read [../MADE-WITH-AI.md](../MADE-WITH-AI.md) before relying on anything here.

**Written by:** an AI model (Gemini, through Google's Antigravity agent)  
**Focus:** Architectural Critique & Concrete Language Upgrades Grounded in Intersubjectivity and Social Epistemology  
**Date:** October 2026  
**Status:** speculative essay, historical record; not reviewed

---

## 1. The Core Critique: Symblic's Current Epistemic Naïveté

In its current state (v2.0–v2.2), Symblic suffers from an unexamined philosophical assumption: **Naïve Realism and Epistemic Monism**.

### Where Current Symblic Fails:
1. **The Single-World Fallacy:**  
   Current Symblic assumes that the universe has one objective state vector, and that all agents, models, and programmers share identical semantic references. A contract is written as:
   ```symblic
   contract InvoiceCheck(inv: Invoice) {
       invariant: inv.total == sum(inv.line_items)
   }
   ```
   This treats the model's extraction as either *objectively correct* or *assert-failed*. It has no machinery to represent that the model extracted data according to **its own observational frame**, that the human input was ambiguous, or that different agents operate under conflicting background expectancies.

2. **The "Beetle in the Box" Problem (Wittgenstein):**  
   When a developer writes `apply ExtractStatus()`, the developer holds a private conception of "status" in their mind (their private "beetle"). The neural model holds a latent cluster of weights in its parameters (its private "beetle"). Current Symblic assumes that because both use the English token `"status"`, they share an identical semantic grounding. When they diverge, Symblic executes a crude retry loop rather than an epistemic calibration protocol.

3. **Absence of Epistemic Modality (Hintikka, Aumann):**  
   Current Symblic has primitives for types (`int`, `float`, `string`, `bool`), but **zero primitives for Epistemic Modality**:
   - Who observed this fact?
   - In what observational frame was it perceived?
   - Is it private belief ($B_i$), grounded knowledge ($K_i$), or common knowledge ($CK$)?
   - What is the evidential security of the claim?

4. **Single-Frame Checking:**  
   Multi-frame checking (see ../reference/EVIDENCE.md) is presented here as proving that empirical adequacy requires survival across the *maximum range of distinct, ontically independent observational frames*.  
   Current Symblic checks through a single frame: it runs **one model**, with **one prompt**, on **one input**, checks a single invariant, and declares victory. This makes Symblic vulnerable to correlated blindspots, reward hacking, and prompt fragility.

5. **Fragile "Cheap Talk" Invariants:**  
   As game theory (Crawford-Sobel, Spence) shows, cheap talk degenerates into uninformative states. In Symblic, a model can satisfy `total == subtotal + tax` trivially by returning all zeros or inventing hallucinated matching numbers. Current Symblic lacks **Incentive-Compatible Non-Degeneracy Proofs**.

---

## 2. Six Concrete Upgrades to Symblic Grounded in Research

```
+-----------------------------------------------------------------------------------------------+
|                             CURRENT SYMBLIC vs. EPISTEMIC SYMBLIC                             |
+-----------------------------------------------------------------------------------------------+
| Dimension              | Current Symblic (v2.2)            | Epistemic Symblic (v3.0 RFC)     |
+------------------------+-----------------------------------+----------------------------------+
| Epistemology           | Naïve Realism (Single global truth)| Intersubjective / Multi-Perspectival |
| Type System            | Primitive scalars (`int`, `str`)  | Epistemic Modalities (`Belief`, `Frame`) |
| Verification Scope     | Single run, single model          | Multi-Frame Concordance           |
| Semantic Calibration   | Hope / Prompt glue                | Davidsonian Triangulation Pass   |
| Invariant Failures     | Fatal crash / Blind retry         | Principle of Charity Auto-Repair |
| Multi-Agent Model      | RPC calls                         | Aumann Common Knowledge Graph    |
+-----------------------------------------------------------------------------------------------+
```

### Upgrade 1: First-Class Epistemic Modality Types
```symblic
type Epistemic<T, Agent, Frame>

type Observation<T, Agent>   # Grounded in direct external sensory/data log
type Belief<T, Agent>        # Inferred by an internal neural model (subjective)
type Knowledge<T>            # Verified against external ground truth invariant
type CommonKnowledge<T>      # Proven shared across all interlocutors/agents (Aumann)
```
*Why:* Prevents conflating unverified neural inference with external ground truth.

### Upgrade 2: Multi-Frame Concordance Contracts (Native Multi-Frame Engine)
```symblic
contract RobustAudit(tx: Transaction) {
    frame linguistic:
        invariant: tx.amount == sum(tx.items)

    frame behavioral:
        invariant: ledger.has_matching_debit(tx.id, tx.amount)

    frame adversarial:
        invariant: invariant_survives_perturbation(tx, delta=0.01)

    enforce MultiFrame_Adequacy:
        concordance([frame.linguistic, frame.behavioral, frame.adversarial]) >= 0.95
}
```
*Why:* Validates truth across ontically independent observational frames, solving the single-prompt failure mode.

### Upgrade 3: The Davidsonian Triangulation Pass (Pre-Flight Semantic Calibration)
Before runtime, Symblic runs a synthetic language-game probe between the invariant engine and model to calibrate semantic meanings and resolve the "Beetle in the Box" gap.

### Upgrade 4: The Principle of Charity & Epistemic Diagnostics (Smart Recovery)
Instead of blind retry loops, the runtime analyzes *why* the model failed (identifying the minimal cognitive divergence) and injects targeted logical lemmas to repair the mismatch.

### Upgrade 5: Incentive-Compatible Non-Degeneracy Proofs (Mechanism Design)
Enforces entropy floors (`entropy(res) >= 0.75 * entropy(doc)`) and exact character-span witnesses so models cannot cheat invariants with vacuous zero solutions.

### Upgrade 6: Theory of Mind (ToM) & Aumann Knowledge Graph in Multi-Agent Symblic
Explicitly tracks `private`, `mutual`, and `common` knowledge partitions across agents to mathematically eliminate hallucination spirals and unshared coordination assumptions.

---

## 3. Implementation Roadmap for Symblic Core

| Module | New Feature / Primitive | Scientific Foundation |
| :--- | :--- | :--- |
| `symblic/lang/abstraction.py` (AST) | `Epistemic<T>`, `Belief`, `Observation`, `CommonKnowledge` | Epistemic Logic (Hintikka, Aumann) |
| `symblic/lang/abstraction.py` (Contracts) | `frame <name>:`, `concordance()`, `MultiFrame_Adequacy` | Multi-frame adequacy |
| `integration/host/symblic_engine.py` (Runtime) | Pre-flight Davidsonian Triangulation Pass | Radical Interpretation (Davidson), Wittgenstein |
| `integration/host/symblic_engine.py` (Recovery)| Principle of Charity Diagnostic Engine | Communicative Rationality (Habermas, Davidson) |
| `symblic/adapters/variational.py` | Non-degeneracy entropy floor & character span witnesses | Mechanism Design (Hurwicz), Costly Signaling (Spence) |
| `symblic_agent.py` | Aumann Knowledge Partition State Machine | Agreement Theorem (Aumann), Double Contingency (Luhmann) |
