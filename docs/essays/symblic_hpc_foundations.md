# Symblic on High-Performance Computing (HPC)

> **Speculative AI writing, not a research result.** This essay was generated in October 2026 by a Gemini model
> working through Google's Antigravity agent, while Symblic was being built, and is kept as a historical record.
> No human expert reviewed it. Many claims are unverified, several overstate what Symblic does, and some describe
> features that do not exist. Where a corrected version exists it is in [../reference](../reference/README.md).
> Read [../MADE-WITH-AI.md](../MADE-WITH-AI.md) before relying on anything here.

**Written by:** an AI model (Gemini, through Google's Antigravity agent), October 3, 2026  
**System Specifications:** Symblic 2.2 | Canonical Format 3  
**Status:** speculative essay kept as a historical record; not reviewed. The corrected version is [../reference/HPC-FOUNDATIONS.md](../reference/HPC-FOUNDATIONS.md).

---

## Executive Summary

This paper establishes the engineering architecture for developing and executing **Symblic** on **High-Performance Computing (HPC)** systems.

It answers four critical design questions:
1. **HPC Execution:** How Symblic runs distributed inference, large-scale Monte Carlo search, parallel Datalog, and continuous SPD variational solvers across multi-node clusters.
2. **HPC Training & RLVR:** How reinforcement learning with verifiable rewards (RLVR) can train specialized autoformalizers and schema readers using the Symblic Kernel as an objective, non-gameable reward function.
3. **Training Risks & Failure Modes:** Why training the wrong components causes catastrophic failure (reward hacking, Goodhart's law, degenerate shortcuts, catastrophic forgetting of language nuance, calibration collapse).
4. **The Shippable Product Roadmap:** The path to shipping Symblic as a standalone, zero-dependency production tool.

---

## Part 1: Developing Symblic on an HPC System

```
                            ┌────────────────────────────────────────┐
                            │           SYMBLIC ON HPC               │
                            └──────────────────┬─────────────────────┘
                 ┌─────────────────────────────┴─────────────────────────────┐
                 ▼                                                           ▼
    ┌──────────────────────────┐                                ┌──────────────────────────┐
    │  PATH A: HPC INFERENCE   │                                │   PATH B: HPC TRAINING   │
    │  & ORCHESTRATION RUNTIME │                                │   & REINFORCEMENT (RLVR) │
    ├──────────────────────────┤                                ├──────────────────────────┤
    │ • Multi-node tensor      │                                │ • Train an Autoformalizer│
    │   parallelism (vLLM/SGL) │                                │   (English → .sym AST)   │
    │ • Test-time search &     │                                │ • Train an Applicator for│
    │   Monte Carlo rollout    │                                │   1-shot schema contract │
    │ • Heavy parallel Datalog │                                │ • RL with Verifiable Re- │
    │   & large-scale SPD solve│                                │   wards (Kernel = Reward)│
    └──────────────────────────┘                                └──────────────────────────┘
```

### 1.1 Path A: HPC Execution & Distributed Scaling

Deploying the Symblic execution runtime onto an HPC cluster (interconnected via high-speed InfiniBand, SLURM scheduler, multi-GPU nodes) enables four major capabilities:

1. **Distributed Multi-Node Inference:**  
   Serve frontier open-weight models (such as Llama-3.1-405B, DeepSeek-R1-671B, or Qwen-2.5-72B) across multi-GPU nodes using `vLLM` or `SGLang` with tensor and pipeline parallelism behind a unified local API endpoint.
2. **Massive Test-Time Scaling (Monte Carlo Search):**  
   Symblic’s `votes=N` and `effort=ultra` directives can scale from $N=5$ on desktop workstations to $N=100\text{--}1,000$ in parallel across cluster nodes. This enables sequential Monte Carlo (PPDL-style) and best-of-$N$ searches over difficult formal contracts.
3. **High-Performance Deterministic Kernel Workloads:**  
   - **Parallel Datalog Scaling:** For codebase AST graphs containing millions of facts, compiling the Datalog engine via high-performance parallel backends (such as Soufflé Datalog) utilizing 64–128 CPU cores.
   - **Parallel Linear Solvers:** Linking the Kernel's Symblic 2.2 variational solver to parallel BLAS/LAPACK or PETSc routines for high-dimensional spatial and physical optimization.
4. **SLURM Job Scheduler Directives:**  
   Add native cluster scheduler syntax to Symblic:
   ```symblic
   ask result: Report "Analyze fleet telemetry" with by="hpc:slurm", nodes=4, gpus=8
   ```

---

### 1.2 Path B: HPC Training & Reinforcement Learning with Verifiable Rewards (RLVR)

#### What Should (and Should Not) Be Trained
- **The Deterministic Kernel is NEVER trained:** Exact rational math ($0.1 + 0.2 = 0.3$), Datalog fixpoints, and $LDL^T$ algebraic solvers are exact mathematical algorithms. Training a neural network to calculate numbers or evaluate Datalog is an anti-pattern that re-introduces hallucination.
- **The Specialized Symblic Models:** HPC training is applied to train a dedicated model (e.g. 7B, 14B, or 32B) for three specific capabilities:
  1. **The Autoformalizer:** Translating ambiguous human English requirements into syntactically and semantically valid `.sym` programs.
  2. **The Schema Contract Reader:** Fine-tuning an applicator to output strict JSON schemas on the first attempt without format retries.
  3. **Reinforcement Learning with Verifiable Rewards (RLVR / GRPO):** Using the Symblic Kernel's `ensure` and `assert` blocks as an **objective, non-gameable reward function**.

#### Would Training Make Significant Improvements?
- **Speed & Latency:** **Yes, for turnaround time.** A fine-tuned 7B/14B model achieving >98% first-pass schema compliance eliminates multi-round retry loops, drastically cutting latency and token consumption.
- **Accuracy on Formal Tasks:** **Yes, for specialized formal translation.** A model trained on formal specifications learns to map domain rules directly into executable contracts.

---

### 1.3 Critical Failure Modes: Can Training Make Symblic Worse?

**Yes, if not strictly controlled.** In reinforcement learning and fine-tuning, three major failure modes can degrade performance:

1. **Reward Hacking / Goodhart's Law:**  
   If an RL policy is rewarded purely for passing `ensure` conditions, it learns degenerate shortcuts that satisfy the programmatic constraint while violating real-world intent.
   * *The Counterexample:* In our test suite, extracting `quantity=1, unit_price=1, total_price=1` satisfies the formula $Q \times P = T$, even when the raw invoice stated 3 laptops at $800 each. A model over-trained on arithmetic rewards will cheat the verification equation.
2. **Catastrophic Forgetting of Linguistic Nuance:**  
   Heavily fine-tuning an LLM on programming language syntax degrades its broad commonsense reasoning, world knowledge, and reading comprehension—the exact subjective perceptual capabilities for which the model was integrated.
3. **Confidence Distortion & Calibration Collapse:**  
   Fine-tuned models frequently become dogmatically overconfident. In multi-model consensus, if a fine-tuned model becomes stubbornly wrong, its calibrated entropy collapses, polluting the ensemble.

#### Training Parameters & Dataset Composition
- **Base Models:** Pre-trained base weights (e.g. Qwen-2.5-14B-Base or Llama-3.1-8B-Base).
- **Dataset Composition:**
  1. 100,000+ pairs of `(Unstructured Document, Typed Schema, Verified Inhabitant)`.
  2. 50,000+ pairs of `(Plain English Intent, Verified Executable .sym Code)`.
  3. Negative trajectories: failed extractions paired with the kernel's exact rejection message and the successful repaired state.
- **Hyperparameters:** Low learning rate ($\sim 1 \times 10^{-5}$ for SFT, $1 \times 10^{-6}$ for RL/GRPO), strict KL-divergence penalty ($\beta = 0.05\text{--}0.1$) to prevent drift from the base model's linguistic comprehension.

---

## Part 2: (Removed for publication)

> *Edited for publication:* a section summarizing a private philosophy text was removed.

---

## Part 3: The Shippable Product Roadmap

To transition Symblic from an internal research language into a production-grade software product:

1. **Single Standalone Native Binary (Zero-Dependency CLI):**  
   Package the Kernel, parser, Datalog engine, and variational solver into a single static native binary (`symblic` CLI) using Rust or compiled standalone C/Python. Installation:
   (No installer exists; this command was invented by the essay's author. See [README.md](../../README.md), "Try it in ten minutes".)
2. **VS Code Extension & Language Server Protocol (LSP):**  
   Real-time diagnostics for syntax errors, reserved word collisions (preventing `count` clashing), type mismatches, and a live "Capsule Preview" panel showing the exact JSON Schema and token footprint.
3. **Pluggable Multi-Backend Adapters (`symblic.toml`):**  
   Unified declarative configuration across local Ollama instances, worker node cluster nodes, and cloud APIs.
4. **Deterministic Packaging & Replay (`sympkg`):**  
   Pinned standard library versions (`units@2.2.0`, `variational@2.2.0`) and CI-checked `run.lock.json` lockfiles for offline execution with zero API calls.
5. **WebAssembly (WASM) Playground:**  
   Compile the deterministic Kernel to WASM for in-browser execution with instant feedback.
