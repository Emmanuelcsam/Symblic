# Quantum Mechanics and Computational Determinism: Does Quantum Mathematics Weaken or Strengthen Symblic's Invariants?

> **Speculative AI writing, revised; not a research result.** The first version of this document was generated
> by an AI model (Gemini, through Google's Antigravity agent) in October 2026, and a later AI coding agent
> corrected it against the code. No human expert has reviewed it. Its mathematics, physics and philosophy are
> not results of this project, and the links it draws to Symblic are analogies unless a section names working
> code and tests. See [../MADE-WITH-AI.md](../MADE-WITH-AI.md).

**Author:** an AI assistant (the Antigravity CLI agent, agy), asked to connect Symblic with other fields. The original header read a person and a "Codex Integration Team"; no record shows Codex writing or integrating this document.

**Focus:** what the mathematics of quantum mechanics says about determinism, which parts of it Symblic computes, and where Symblic's non-determinism actually comes from

**Date:** written 2026-10-03 against Symblic 2.2; corrected 2026-10-04 against Symblic 2.4, and its statements about the code re-checked against Symblic 2.5 the same day

**Status:** proposal, reviewed. Not a proof and not a specification: [SPEC.md](SPEC.md) specifies what was built. [REVIEW-2.3.md](REVIEW-2.3.md) records the outcome of each of this document's seven proposals:
- one built in a reduced form in 2.3 (`permute=K`);
- one deferred: the Ising route. Its exact finite form, `ising_minimize`, was built;
- two with the claim rejected and the construction kept as a research direction: ZX rewriting, and one-use resource types;
- three rejected: the three "guards" of §5.

This corrected text keeps the original structure. Mathematics that is right is kept and stated with its conditions. Each part then says what Symblic does and what became of the proposal. False claims have been replaced in place. "Q-Symblic" is this document's name for the proposed extension; no such language, mode or module exists. The one program listing, which is not Symblic, is marked as proposed syntax.

---

## Executive Summary

A common first reaction to applying quantum mechanics to computing is: *"Quantum mechanics is fundamentally probabilistic; therefore, applying quantum math must make Symblic non-deterministic."*

**The conclusion does not follow.** For finite-dimensional systems, the mathematics of quantum mechanics is linear algebra: state vectors, matrices, projectors and the probabilities they define. Computed with exact arithmetic, these quantities come out the same every time, as any exact computation does. Randomness appears only when a program simulates a measurement by drawing a random outcome.

**Quantum mathematics does not make Symblic more deterministic either.** The original claimed it makes Symblic "strictly more deterministic". It changes neither of the two parts that matter:
- **The kernel** was already deterministic before any quantum construction was added. It uses exact rationals; its transcendental functions are Decimal series in a fixed context ([SPEC.md](SPEC.md) §7). The operator builtins added in 2.3 compute with exact rationals, so they are deterministic too.
- **Model answers** are as variable as before. A model samples its text, and no construction in Symblic makes its answers deterministic ([REVIEW-2.3.md](REVIEW-2.3.md), "Outcome"). On 2026-10-04, local models of about 4B parameters built the Tetris page again, from scratch and from its final spec sheet. The page they produced differs from the first build, which had been assembled over 14 incremental builds while the sheet and the kernel changed. Both pages passed all 39 required checks of the independent harness ([SPEC-SHEETS.md](SPEC-SHEETS.md), "The Tetris record").

Two things must be kept apart:
1. **Measurement (the Born rule).** The theory predicts the *probabilities* of measurement outcomes, not which outcome occurs. Whether a measurement involves a physical "collapse" depends on the interpretation.
2. **The rest of the formalism.**
   - A closed system evolves under the Schrödinger equation deterministically, linearly and reversibly.
   - An open system's density matrix also evolves deterministically, but in general not reversibly.
   - Projectors, commutators and outcome probabilities are functions that can be computed exactly.
   - Diagrammatic calculi such as ZX are a notation for the same linear maps. They are not a further source of dynamics.

What Symblic computes that bears on this document is small and exact:
- `is_projector`, `commutator`, `commutes` and `ordered_probability`, on real rational matrices up to 8 × 8 ([OPERATORS.md](OPERATORS.md));
- `ising_minimize`, which evaluates every state of a classical Ising model with at most 16 spins (§3.3; [DISCRETE.md](DISCRETE.md)).

The following are not part of Symblic: orthomodular lattices as a logic, density operators, ZX-calculus, a compiler from constraints to Ising Hamiltonians, and annealers. Prompt order is measured rather than modelled: `permute=K` repeats a vote with the options in K rotated orders.

---

## Table of Contents
1. [Schrödinger vs. Born: The Two Equations of Quantum Mechanics](#1-schrödinger-vs-born-the-two-equations-of-quantum-mechanics)
2. [Where Symblic Is Deterministic, and Where It Is Not](#2-where-symblic-is-deterministic-and-where-it-is-not)
3. [What Quantum Mathematics Can and Cannot Remove](#3-what-quantum-mathematics-can-and-cannot-remove)
   - 3.1 Non-Commuting Projectors and Prompt Order
   - 3.2 ZX-Calculus: Complete, Not Confluent, and Not in Symblic
   - 3.3 Ising Ground States: Exact up to 16 Spins, Not Always Unique, NP-hard in General
4. [The No-Cloning Theorem and Concurrency](#4-the-no-cloning-theorem-and-concurrency)
5. [Where Non-Determinism Enters, and What Symblic Does About It](#5-where-non-determinism-enters-and-what-symblic-does-about-it)
6. [Summary: The Proposal Against Symblic 2.4](#6-summary-the-proposal-against-symblic-24)
7. [Conclusion](#conclusion)
8. [References](#references)

---

## 1. Schrödinger vs. Born: The Two Equations of Quantum Mechanics

To see why quantum mathematics does not by itself introduce randomness, separate the theory's law of motion from its rule for measurement outcomes. The theory has other postulates too, such as how systems combine; these two are the ones that bear on determinism.

```
+---------------------------------------------------------------------------------------------------+
| THE SCHRÖDINGER EQUATION (evolution of a closed system; H self-adjoint and time-independent)      |
|   iħ ∂/∂t |ψ(t)⟩ = H |ψ(t)⟩   ===>   |ψ(t)⟩ = e^{-iHt/ħ} |ψ(0)⟩                                   |
|   - Deterministic, linear and reversible: e^{-iHt/ħ} is unitary.                                  |
|   - Given |ψ(0)⟩, the state at every time t is uniquely determined.                               |
|   - The law has no random element. The state it evolves still assigns probabilities to            |
|     measurement outcomes, through the rule below.                                                 |
+---------------------------------------------------------------------------------------------------+
                                                  vs.
+---------------------------------------------------------------------------------------------------+
| THE BORN RULE (probabilities of measurement outcomes; Born 1926)                                  |
|   P(outcome = i) = |⟨e_i | ψ⟩|^2      (normalised |ψ⟩, measured in the orthonormal basis {e_i})   |
|   - Gives the probability of each outcome, not which outcome occurs.                              |
|   - In the standard formulation, this is where probability enters the theory. Whether             |
|     anything physically 'collapses' depends on the interpretation: Everett (1957) and             |
|     Bohm (1952) have no collapse.                                                                 |
+---------------------------------------------------------------------------------------------------+
```

Symblic simulates no measurement: nothing in it draws a random outcome from a quantum state. Its only code from the quantum formalism is `symblic/adapters/operators.py`, which works on real rational matrices of dimension at most 8. It tests whether a matrix is an orthogonal projector and computes commutators. It also computes `ordered_probability`, the probability of a sequence of yes/no answers when each answer projects the state: |M_k ⋯ M_1 s|² / |s|². That is the Born rule applied to a sequence of projective measurements, returned as an exact fraction; nothing is sampled. The code has no time evolution, no complex amplitude and no density matrix ([OPERATORS.md](OPERATORS.md), "What it does not establish").

With exact rational arithmetic, which the kernel uses, a matrix product has one answer on every machine. The kernel's cross-machine record covers two programs, not matrix products. On 2026-10-02, `02-flower-formal.sym` and `10-kernel-identity.sym`, which between them use exact rationals, Decimal trigonometry, Datalog and drawings, each gave the same fingerprint and the same drawing hashes on all eight machines tested: seven x86_64 and one aarch64 ([kernel-identity.json](kernel-identity.json)). [SPEC.md](SPEC.md) §7 limits that record to those programs under that day's kernel.

Floating point is different. The same sequence of IEEE operations gives the same result, but adding the same numbers in a different order can round differently. In double precision, (0.1 + 0.2) + 0.3 is 0.6000000000000001, while 0.1 + (0.2 + 0.3) is 0.6. Parallel code whose order of additions varies, between machines or between runs, can therefore differ in the last bits. So the original's "Û|ψ⟩ is as strictly deterministic as evaluating 2 + 2 = 4" holds for exact arithmetic. In floating point it holds only for a fixed order of operations.

---

## 2. Where Symblic Is Deterministic, and Where It Is Not

The original said that Symblic "claims total determinism via exact rational arithmetic and SHA-256 lockfiles", and that this is "a leaky abstraction masking massive internal stochasticity". Symblic makes no such claim. The specification's claim is narrower ([SPEC.md](SPEC.md), introduction):
- equal formal inputs under the same semantic kernel are intended to give equal results, when execution succeeds within its limits;
- this does not establish that a model's answer describes the world correctly.

Every statement is labelled with a determinism class (SPEC.md §3). The class describes the mechanism, not a probability of correctness:
- `exact` for the kernel;
- `closed`, `structured` or `open` for model answers, by answer type;
- `observed` and `effect` for the outside world.

```
[ A Symblic run ]
  1. Kernel statements      --> exact: the same inputs under the same kernel identity give the same result
  2. Model calls (ask)      --> sampled: by default sample 0 at temperature 0, the others at 0.7, seeds seed + i;
                                temperature and seed reach local Ollama models, the cloud CLIs take neither
  3. A failed ensure        --> a bounded re-ask with feedback, after the run's state is restored
  4. The record             --> every call stored under the SHA-256 of its request; replay serves the
                                stored replies and calls no model; a fresh run can differ, and drift says where
```

### The Three Sources of Non-Determinism, as They Stand

1. **Prompt order.** A model's answer depends on its whole input, including the order of its parts. In one study of GPT-4 and InstructGPT answering multiple-choice questions zero-shot, accuracy under the most and under the least favourable option order, chosen with the correct answers known, differed by about 13 to 75 points, depending on the model and the benchmark (Pezeshkpour and Hruschka 2023). Models also carry priors for option labels (Zheng et al. 2024). Full entries and figures are in [RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md). Symblic measures this rather than assuming it away:
   - `permute=K` takes a vote K times, with the options listed in K rotated orders. The ask is stable only when every rotation has the same valid, uncontested winner; otherwise it is reported as contested (SPEC.md §4).
   - Question order can be measured by asking two questions in both orders and counting the answers. The `order` library computes the order effects and the QQ gap, and [example 14](../../examples/14-question-order.sym) does this.
   - These measurements have two limits. Rotations by the same models are not independent readers. And nothing permutes the KNOWN items inside a capsule: that probe, the one new testable idea REVIEW-2.3 found in this document, is not built.

   The original added that Symblic's "type system assumes commutativity (A ∧ B ≡ B ∧ A)". That identity does hold for the kernel's `and` on two Boolean values, as for any conjunction, but it is a fact about values that already exist, not an assumption about prompts. The kernel's `and` is evaluated left to right with short-circuit (`symblic/kernel/language.py`, `Kernel._bin`), so the order of evaluation can still matter: `false and (1 / 0 = 1)` is false, while `(1 / 0 = 1) and false` fails with division by zero. It combines answers after they exist and makes no assumption about how a model's answers depend on the order of a prompt.

2. **Retries.** When an `ensure ... else retry` check fails, the run restores its state to what it was when the anchored ask started (bindings, facts, outputs and the rest) and asks again (SPEC.md §5):
   - The new request names the rejected answers and the failed condition.
   - When the check has no `because`, it also gives the values the kernel computed from the answer alone.

   This loop is in `Run.exec_block` (`symblic/kernel/run.py`). The original cited line 1280 of `symblic/kernel/run.py`, which does not hold it: that line held vote-keying code in 2.4 and is part of the `ambiguous` check in 2.5. Whether a later attempt passes depends on the model's next answer, so it cannot be known in advance. That does not make it a "random walk":
   - the number of attempts is bounded (`retries`, default 2, at most 5);
   - every attempt is recorded, and a replay follows the same path from the recorded replies;
   - when retries run out, the report says whether the rejected answers were all the same, all different or mixed, as a hint to the author (SPEC.md §5).

3. **Floating point in model inference.** A fresh model call can return different text on different hardware or software, even at temperature 0, for example because sums taken in a different order can round differently (§1).
   - **This cannot break replay.** Replay serves the recorded replies. A call the record does not hold fails the replay instead of reaching a model (`symblic/kernel/lockfile.py`, module docstring and `replay`; SPEC.md §8).
   - **It does affect a fresh run,** which Symblic treats as a new observation: `drift` compares a fresh run with a lock and lists the statements whose fingerprints changed.
   - The original's "CUDA warp" example does not describe the Tetris record either: there the local models ran on CPU-only worker nodes.

In short, the kernel is deterministic and model calls are not. Symblic records the model calls, so a run can be replayed exactly, and it labels which statements depend on a model.

---

## 3. What Quantum Mathematics Can and Cannot Remove

The original said that applying quantum structures "removes this stochastic fragility". None of them can. The variability is in the model: in its sampling, and in how its answer depends on its input. A computation the kernel performs after the model has answered cannot change what the model said. Each structure is taken in turn below.

### 3.1 Non-Commuting Projectors and Prompt Order

Two projectors need not commute. The commutator
$$[\hat{P}_A, \hat{P}_B] = \hat{P}_A \hat{P}_B - \hat{P}_B \hat{P}_A$$
is zero for some pairs and non-zero for others. Quantum logic goes back to Birkhoff and von Neumann (1936). In it, propositions are projectors, and the lattice they form is not distributive.

When the answer to question A is "yes", the Lüders rule (Lüders 1951) updates a density matrix as
$$\rho_{t+1} = \frac{\hat{P}_A \rho_t \hat{P}_A}{\text{Tr}(\hat{P}_A \rho_t \hat{P}_A)}, \qquad \text{Tr}(\hat{P}_A \rho_t \hat{P}_A) > 0 .$$
Given the recorded answer, this is an exact, deterministic matrix map. It is also order-dependent by construction: when the projectors do not commute, A then B can give a different state, and different probabilities, from B then A. So it cannot produce the "canonical, order-invariant representation" the original claimed. It predicts order effects; it does not remove them. Nothing in Symblic computes a phase shift, or any other prediction of what a model will answer, "before generation". What it computes before a call concerns the program: the determination of §3.3, and the static `predictability` score of `check`, which is a guide from the text alone, not a probability (SPEC.md §12).

Applied to language models, this model is an analogy, and Symblic states its limits:
- `ordered_probability` computes the model's prediction exactly, for a pure real state and real projectors. Take A = [[1, 0], [0, 0]], B = [[1/2, 1/2], [1/2, 1/2]] and the state (2, 1). P(A yes) is 4/5 when A is asked first and 1/2 when B is asked first ([OPERATORS.md](OPERATORS.md); this example was re-run through the 2.4 and 2.5 kernels for this correction).
- The model also predicts the QQ equality (Wang and Busemeyer 2013). The `order` library computes the matching quantity from counted answers.
- It does not estimate projectors or a state from a language model:
  - nothing defines which matrix a prompt would be;
  - a model's hidden state is not a quantum state;
  - no density matrix is tracked for any ask.
- The algebra has real symmetric matrices only. Complex projectors, density matrices and non-projective measurements are not represented (OPERATORS.md).

REVIEW-2.3 outcome for "Density-operator tracking of prompt order": built in 2.3 in a reduced form, as `permute=K`, which measures option-order sensitivity directly.

### 3.2 ZX-Calculus: Complete, Not Confluent, and Not in Symblic

These are two different formalisms:
- **DisCoCat** (Coecke, Sadrzadeh and Clark 2010) composes the meanings of words, given as vectors and tensors, along a sentence's grammatical structure.
- **The ZX-calculus** (Coecke and Duncan 2011) is a graphical language for linear maps between qubits, drawn with green (Z) and red (X) spiders. It is about qubit processes, not sentences.

Quantum natural-language tools such as lambeq (cited in [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)) turn DisCoCat diagrams into quantum circuits.

Three rules of the calculus. The first two are drawn schematically: spider fusion adds phases, and Hadamards on every leg change a spider's colour. The third panel only names the bialgebra rule; it does not draw it.

```
          Spider Fusion:           Color Change:              Bialgebra:
       O---( Z_α )---O          [ H ]---( Z_α )---[ H ]     ( Z ) === ( X )
             |                         |                       \     /
       O---( Z_β )---O                 v                        \   /
             |                  O---( X_α )---O                ( X ) === ( Z )
             v
       O---( Z_{α+β} )---O
```

The original said the ZX rewrite system "is provably confluent (Backens 2014, Vilmart 2019)", and: "Regardless of the order in which compiler rewrite rules are applied, the graph always reduces to the exact same canonical normal form." That is false as stated:
- **Those are completeness results.** Backens (2014) proves completeness: every equation between stabilizer diagrams that holds for the linear maps they denote can be derived from the rules. The original does not say which Vilmart 2019 paper it means. Vilmart's LICS 2019 paper gives complete axiomatisations of the general ZX-calculus, for pure qubit quantum mechanics: completeness again.
- **Completeness is not confluence.** The rules are equations that can be applied in either direction. Reaching one normal form whatever the order of the rewrites would need an oriented rule set that terminates and is confluent on the fragment in question; completeness provides neither. A fixed normalisation procedure is a different claim, about that procedure, and needs its own proof.

Even unique normal forms would not make natural-language meaning deterministic:
- DisCoCat gives a composition rule, not correct word meanings (RESEARCH-ADOPTION.md).
- No rewrite acts on what a model answers.
- The comparison with "classical string parsing" also fails. A deterministic parser, such as Symblic's own (`symblic/kernel/language.py`), already maps the same text to the same program every time.

Symblic contains no ZX-calculus or DisCoCat code. REVIEW-2.3 outcome: claim rejected; construction deferred as a research direction. That direction is a bounded adapter that checks supported circuit rewrites by exact matrix equality (RESEARCH-ADOPTION.md, "ZX-calculus and exact algebraic amplitudes").

### 3.3 Ising Ground States: Exact up to 16 Spins, Not Always Unique, NP-hard in General

The original said: "In Symblic 2.2, complex multi-variable constraints cause the runtime to loop and retry heuristically." In fact, finite constraints are handled before any model is asked (SPEC.md §5, "Determination by enumeration"). When two conditions hold, the interpreter evaluates the candidates first: the ask's answer type has a finite domain (at most 20 000 values), and its anchored checks are supported. It stops once more than 50 candidates pass, which already shows that the ask is underdetermined. The outcomes:
- **No passing value:** the contract is `contradictory`, and the run fails before a model call.
- **Exactly one:** it is `determined`, and with `solve` the kernel returns it with zero model calls.
- **Several:** it is `underdetermined`, and the kernel never picks one and calls it unique.

Retries with feedback apply to model answers that fail a check. Separate exact builtins handle explicit numeric problems:
- `quadratic_minimize` minimises ½xᵀAx − bᵀx for a supplied rational symmetric positive-definite A of dimension at most 32, and returns an LDLᵀ witness (`L`, `D`, `x`) that `quadratic_verify` checks ([VARIATIONAL.md](VARIATIONAL.md));
- `reconcile` returns the nearest values that satisfy exact linear constraints ([PROJECTION.md](PROJECTION.md)).

`solve` uses enumeration only; none of these builtins is connected to it.

The proposed route was to compile constraints to an Ising Hamiltonian,
$$\hat{H} = \sum_i h_i \hat{\sigma}_i^z + \sum_{i < j} J_{ij} \hat{\sigma}_i^z \hat{\sigma}_j^z ,$$
and find its ground-state energy,
$$E_0 = \min_{\langle\psi|\psi\rangle = 1} \langle \psi | \hat{H} | \psi \rangle .$$
The variational formula is right. Because this H is diagonal in the spin basis, the minimum is attained at a basis state, so E_0 is the minimum over the 2^n classical spin assignments. Nothing quantum is needed to state or compute it. No compiler from Symblic constraints to h and J exists.

Two of the original's claims are false:
- **"The ground state of a discrete physical Hamiltonian is a unique, mathematically exact eigenvector."** Ground states need not be unique:
  - With no field, flipping every spin leaves the energy unchanged, so ground states come in pairs.
  - Frustration adds more: three antiferromagnetic bonds on a triangle have six ([DISCRETE.md](DISCRETE.md)).
  - When the minimum is degenerate, the ground states span a subspace, not one vector.
  - For example, `ising_minimize([0, 0], [[0, 1], [1, 0]])` returns degeneracy 2, with states [−1, −1] and [1, 1]. This was run through the 2.4 and 2.5 kernels for this correction.
- **"… the adiabatic variational solver minimizes the Hamiltonian deterministically."** Symblic has no adiabatic or annealing solver. The contract of `symblic/adapters/discrete.py` says "No floating point, sampling, annealing, heuristic, model, service or I/O". The general problem is hard:
  - Finding an Ising ground state is NP-hard in general (Barahona 1982), so no known method finds exact ground states in polynomial time on every instance.
  - Annealing, whether classical or simulated-quantum, is a heuristic. It returns a low-energy state with no certificate that it is a ground state.
  - Specific adiabatic algorithms have hard instances (Altshuler, Krovi and Roland 2009). That does not show that every adiabatic path fails (Dickson and Amin 2011). RESEARCH-ADOPTION.md cites both.

What exists is `ising_minimize(h, J)` ([DISCRETE.md](DISCRETE.md)):
- **What it does:** it evaluates every one of the 2^n states, for n ≤ 16, with exact rational arithmetic. It returns the minimum energy, how many states attain it, and the first 16 of them.
- **Sign convention:** its energy is E(s) = −Σ h_i s_i − Σ_{i<j} J_ij s_i s_j. The Hamiltonian above, written with plus signs, is therefore minimised by passing −h and −J.
- **Encoding:** that h and J encode a real problem is the author's claim; the module does not check it.

The exact quadratic solver is not an Ising method. Minimising a convex quadratic over the rationals is one linear solve; the Ising problem is a binary optimisation (REVIEW-2.3.md, "Recurring errors about the mathematics and the physics").

The original contrasted all this with "a stochastic LLM guessing numbers until an assertion passes". Symblic's answer to that is enumeration. With `solve` (or only `kernel` applicators), a value that the checks determine is returned by the kernel with no model call. When a model applicator is used without `solve`, the determination is still computed and recorded, and a contradictory contract stops the run before any call, but a model is asked and its answer must pass the same checks.

REVIEW-2.3 outcome: deferred. A classical exact solver backend that extends determination is sound. The annealing route is incomplete, and its uniqueness claim is false.

---

## 4. The No-Cloning Theorem and Concurrency

In a distributed system, non-determinism comes from timing: the order in which messages, replies and failures arrive. Races on shared mutable state are one way that timing changes results. A Symblic run is orchestrated on the host (SPEC.md §8). Its CLI and Ollama calls go to the worker nodes unless a call names the host (SPEC.md §6).

**What no-cloning says.** The no-cloning theorem (Wootters and Zurek 1982; Dieks 1982) says that no unitary U, indeed no linear map, satisfies U(|ψ⟩|0⟩) = |ψ⟩|ψ⟩ for **every** state |ψ⟩. The original wrote this as U(|ψ⟩|0⟩) ≠ |ψ⟩|ψ⟩, which is false for particular states: the states of one orthonormal basis can be copied (a CNOT copies |0⟩ and |1⟩).

**What it does not say.** The original said that no-cloning "enforces Girard's Linear Logic". It does not:
- Linear logic (Girard 1987) is a proof system in which a hypothesis cannot be freely duplicated or discarded.
- Some quantum programming languages use linear or affine types so that a program cannot express copying a qubit. That is a design choice that matches no-cloning.
- For a classical resource such as a token, no-cloning is at most an analogy. Classical data can be copied, so "use once" has to be enforced by a rule and a record.

The original's example is not Symblic:
- `check` refuses it at the first `delegate` line, with `expected 'to'`. A real delegation reads `delegate job = "task" to "triad".` (SPEC.md §2).
- `QLinear` and `consume` do not exist.

It is kept here as proposed syntax, with its comments corrected:

```text
# Proposed syntax, not Symblic. `check` refuses it at the first delegate line ("expected 'to'").
# The proposal's claim: handing one value to two workers is a race.
let shared_token = auth.get_token()
delegate worker_1(shared_token)
delegate worker_2(shared_token)

# The proposal: a one-use type, so a second use would be refused before the run (not built).
let q_token: QLinear[AuthToken] = auth.get_token()
delegate worker_1(consume(q_token))
# delegate worker_2(q_token)   <- the second use the proposal would refuse
```

What Symblic does about the races the example describes:
- **Values are immutable.** A name is bound once per scope (SPEC.md §2).
  - `let token = "abc".` followed by `let token = "def".` is refused, both by `check` ("token is bound twice (Symblic names are immutable)") and by a run ("token is already bound (line 1); Symblic names are immutable").
  - A value given to two asks or two agents is copied into each capsule or task, and neither can change it for the other.
  - So the race in the example cannot happen on a Symblic value.
- **Parallel replies are combined by a fixed rule.** Votes and `route=search` run their calls in parallel, but arrival order never decides the result:
  - A vote's ties go to the answer whose first supporter is earliest in the declared applicator order, then to the smaller canonical form, never to whichever reply arrived first (`symblic/kernel/language.py`, `consensus`).
  - Search selects the pass with the fewest attempts, then the lowest index, never the first to arrive (SPEC.md §4, `route`).
  - The same replies give the same result, whatever order they arrive in.
- **External actions are claimed under a lock.** An `act` has an identity: the SHA-256 of its capability and arguments, or its key.
  - The ledger claims that identity under an exclusive lock, so the same action is performed automatically at most once, with explicit uncertainty when its outcome is unknown. This is not exactly-once ([EFFECTS.md](EFFECTS.md) §4).
  - `SYM_SAME_KEY` warns when two `act` statements on one path share a capability and a literal key, because the second would be served the first one's outcome (SPEC.md §5). 2.3 built this warning as the reduced form of the same proposal in [QUANTUM-FOUNDATIONS-OF-SYMBLIC.md](QUANTUM-FOUNDATIONS-OF-SYMBLIC.md).
- **What remains outside the language:** what two delegated agents do to the same outside files or services. A one-use type on a Symblic name would not change that either.

Freedom from data races does not make a concurrent program deterministic, because independent replies can still arrive in different orders. That is why Symblic combines them by a fixed rule rather than by arrival.

REVIEW-2.3 outcome for "Linear 'QLinear' types justified by no-cloning to prevent races across nodes": claim rejected; construction deferred. No-cloning does not imply such types, and immutable bindings already rule out the races described. Affine handles for genuinely one-use resources are a research direction (RESEARCH-ADOPTION.md, "Linear capabilities and no-cloning").

---

## 5. Where Non-Determinism Enters, and What Symblic Does About It

The original proposed three "guards" to "guarantee that quantum mathematics never weakens determinism". None was built, and REVIEW-2.3 rejected all three. Each is given below with what exists instead.

### Guard 1: Never Sample (proposed; rejected)
* **The concern:** a program that simulates a Born-rule measurement, drawing an outcome with probabilities |c_i|², introduces randomness.
* **The proposal:** the runtime "never samples". It would compute instead:
  1. the projection P̂|ψ⟩;
  2. the expectation ⟨Â⟩ = Tr(Âρ), as a rational number;
  3. the "maximal eigenstate", by argmax.
* **What exists in the kernel:** the kernel never samples. Where it computes quantities from the quantum formalism, it returns them exactly: `ordered_probability` returns the probability of a sequence of projective answers as a fraction (OPERATORS.md). There are no density matrices, so there is no Tr(Âρ), and the kernel has no eigenvalue solver (`ising_minimize` finds its ground states by enumeration).
* **What exists for model calls:** model calls do sample, and the proposal does not reach them.
  - By default, sample 0 runs at temperature 0 and further samples at 0.7, with seeds seed + i.
  - Temperature and seed reach local Ollama models only; the cloud CLIs take neither (SPEC.md §4; `symblic/providers/applicators.py`).
  - Every reply is recorded, so a replay needs no model (SPEC.md §8).
* **REVIEW-2.3 outcome:** rejected. Symblic has no quantum state to project, and the model-side analogue (temperature 0, a fixed seed, record and replay) already exists.

### Guard 2: Exact Arithmetic with Cyclotomic Fields (proposed; rejected)
* **The concern:** floating-point addition is not associative. (a + b) + c and a + (b + c) can round differently, so a parallel sum whose order changes can change the result (§1 has an example).
* **The proposal:** compute quantum phases and amplitudes over cyclotomic number fields ℚ(ζ_n) and dyadic rationals, writing e^{iπ/4} = (1 + i)/√2 symbolically, for "bitwise-identical evaluation on every CPU and GPU in the cluster".
* **What holds:** the identity e^{iπ/4} = (1 + i)/√2 is correct, and the number lies in ℚ(ζ_8).
* **What exists:** Symblic has no complex or cyclotomic arithmetic.
  - The kernel computes with exact rationals, and its transcendental functions are Decimal series in a fixed context (SPEC.md §7). The operator builtins take real rational matrices only.
  - The kernel runs in Python on CPUs; nothing in it runs on a GPU. Its arithmetic avoids the platform's floating point and libm: exact rationals, and Decimal series in a fixed context. The eight-machine record of §1 is consistent with that design; it covers two programs.
  - The floating-point drift the proposal targets is in model inference, outside the kernel, and replay sidesteps it by serving recorded replies.
* **REVIEW-2.3 outcome:** rejected. Kernel determinism is already achieved; the drift sits in the model applicators.

### Guard 3: Seeded Annealing (proposed; rejected)
* **The proposal:** when Ising Hamiltonians are solved by simulated quantum annealing (SQA) on classical hardware, pin three things to the SHA-256 of the input problem: the random seed, the number of Trotter slices P and the imaginary-time step Δτ. The original said: "The solver path is 100% deterministic and reproducible."
* **What holds:** a seed derived from the input makes a given implementation repeat exactly on the same software. It does not make the result optimal or certify it; SQA remains a heuristic (RESEARCH-ADOPTION.md, Ising row).
* **What exists:** no annealer of any kind. `ising_minimize` needs no seed, because it evaluates every state. Seeds are the convention for model calls (`seed`, SPEC.md §4).
* **REVIEW-2.3 outcome:** rejected as a determinism or optimality guarantee. A bounded seeded heuristic remains an admissible experimental constructor under [RESEARCH-ADOPTION](RESEARCH-ADOPTION.md): retain the original constraints, check every proposed witness, report the seed and implementation identity, account for search costs, and distinguish an accepted feasible candidate from a certified optimum. No annealer is implemented by this document.

---

## 6. Summary: The Proposal Against Symblic 2.4

| Dimension | Proposed ("Q-Symblic") | Symblic 2.4 | REVIEW-2.3 outcome |
| :--- | :--- | :--- | :--- |
| **Logic** | An orthomodular projection lattice instead of Boolean logic, for "exact context modeling" | Two-valued `and`/`or`/`not` on values the kernel has computed; it does not model prompts. A projector algebra is available as exact builtins for modelling (`is_projector`, `commutator`, `commutes`; real rational matrices, at most 8 × 8) | Not one of this document's seven proposals. The same proposal in [QUANTUM-FOUNDATIONS-OF-SYMBLIC.md](QUANTUM-FOUNDATIONS-OF-SYMBLIC.md) was rejected, and the finite algebra was built |
| **Prompt order** | Track order with a density operator and commutators | Measured, not modelled: `permute=K` for option order; the `order` library and example 14 for question order, from counted answers. `ordered_probability` gives the projector model's prediction for supplied matrices | Built in a reduced form (`permute=K`) |
| **Semantic composition** | ZX-calculus graph rewriting with a "provably unique normal form" | Typed asks: the instruction is interpolated text, and the answer schema is compiled from the type. The reply is parsed and checked against the type, and anchored checks test it | Claim rejected; construction deferred |
| **Constraint solving** | Ising ground-state minimisation by an annealer | Determination by enumeration (at most 20 000 values) before any model call; `solve` uses enumeration only. Separate exact builtins: `ising_minimize` (exhaustive, at most 16 spins) and `quadratic_minimize` (exact SPD, at most 32 unknowns) | Deferred; the exact finite form was built |
| **Concurrency** | Linear "QLinear" types from no-cloning, "provably data-race free" | Immutable bindings. Parallel replies combined by a fixed rule, never by arrival. The effect ledger: at most one automatic performance per action identity. The `SYM_SAME_KEY` warning | Claim rejected; construction deferred |
| **Determinism** | "Provably Unitary & Confluently Deterministic" | Kernel: deterministic (exact rationals; Decimal series in a fixed context for transcendental functions). Model answers: sampled, recorded and possible to replay from the record; a fresh run can differ, and `drift` says where | Guards 1-3 rejected |

---

## Conclusion

Using the mathematics of quantum mechanics in the kernel does not make Symblic less deterministic: the 2.3 operator builtins (and the classical `ising_minimize`) are exact computations, and the kernel as a whole is deterministic (exact rationals, and Decimal series in a fixed context for transcendental functions; SPEC.md §7). It does not make Symblic more deterministic either.

The original's closing claims do not hold:
- It said that classical Boolean logic is "too rigid to model the non-linear, contextual nature of neural language models". The kernel's logic does not model the network at all. It checks typed answers after a model returns them. Where a model's answer depends on context, Symblic measures that rather than modelling it: `permute` and the `order` library measure order effects, and `ambiguous` readings record the other readings that models see in a statement.
- It said that quantum formalism can "tame neural stochasticity into a 100% reproducible, deterministic science". No construction in Symblic, quantum or not, makes a model's answers deterministic.

What Symblic does instead:
- it keeps exact computation in a deterministic kernel;
- it records every model call, replays a run from the record without any model, and reports where a fresh run differs (`drift`);
- it checks model answers against encoded predicates, which establishes conformance to those predicates, not correctness (SPEC.md §5);
- it measures order sensitivity instead of assuming it away.

The from-scratch Tetris rebuild of 2026-10-04 shows the split:
- The model side varies: from the final sheet, with nothing kept, the rebuild produced a different page. The first page had been assembled over 14 incremental builds while the sheet and the kernel changed, so the two builds are not a controlled measure of sampling alone.
- The kernel's checks decided which units were accepted.
- An independent harness then graded both pages at 39 of 39 required checks.

---

## References

These are primary sources for the results named above. An entry gives a venue only where it is certain. The arXiv identifiers were checked on arXiv on 2026-10-04; all but Vilmart's are also linked in [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md) and [RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md).

- Altshuler, B., Krovi, H., and Roland, J. (2009). "Adiabatic quantum optimization fails for random instances of NP-complete problems." arXiv:0908.2782.
- Backens, M. (2014). "The ZX-calculus is complete for stabilizer quantum mechanics." *New Journal of Physics* 16, 093021. arXiv:1307.7025.
- Barahona, F. (1982). "On the computational complexity of Ising spin glass models." *Journal of Physics A: Mathematical and General* 15, 3241–3253.
- Birkhoff, G., and von Neumann, J. (1936). "The logic of quantum mechanics." *Annals of Mathematics* 37, 823–843.
- Bohm, D. (1952). "A suggested interpretation of the quantum theory in terms of 'hidden' variables. I." *Physical Review* 85, 166–179.
- Born, M. (1926). "Zur Quantenmechanik der Stoßvorgänge." *Zeitschrift für Physik* 37, 863–867.
- Coecke, B., and Duncan, R. (2011). "Interacting quantum observables: categorical algebra and diagrammatics." *New Journal of Physics* 13, 043016.
- Coecke, B., Sadrzadeh, M., and Clark, S. (2010). "Mathematical foundations for a compositional distributional model of meaning." *Linguistic Analysis*, Lambek Festschrift special issue. arXiv:1003.4394.
- Dickson, N. G., and Amin, M. H. S. (2011). "Does adiabatic quantum optimization fail for NP-complete problems?" *Physical Review Letters* 106, 050502. arXiv:1010.0669, where it is titled "Does adiabatic quantum optimization truly fail for NP-complete problems?".
- Dieks, D. (1982). "Communication by EPR devices." *Physics Letters A* 92, 271–272.
- Everett, H. (1957). "'Relative state' formulation of quantum mechanics." *Reviews of Modern Physics* 29, 454–462.
- Girard, J.-Y. (1987). "Linear logic." *Theoretical Computer Science* 50, 1–101.
- Lüders, G. (1951). "Über die Zustandsänderung durch den Meßprozeß." *Annalen der Physik* 8, 322–328 (the publisher's online record numbers it volume 443 and dates it 1950).
- Pezeshkpour, P., and Hruschka, E. (2023). "Large language models sensitivity to the order of options in multiple-choice questions." arXiv:2308.11483.
- Vilmart, R. (2019). "A near-minimal axiomatisation of ZX-calculus for pure qubit quantum mechanics." *Proceedings of LICS 2019*. arXiv:1812.09114, where it is titled "A near-optimal axiomatisation of ZX-calculus for pure qubit quantum mechanics".
- Wang, Z., and Busemeyer, J. R. (2013). "A quantum question order model supported by empirical tests of an a priori and precise prediction." *Topics in Cognitive Science* 5(4), 689–710.
- Wootters, W. K., and Zurek, W. H. (1982). "A single quantum cannot be cloned." *Nature* 299, 802–803.
- Zheng, C., Zhou, H., Meng, F., Zhou, J., and Huang, M. (2024). "Large language models are not robust multiple choice selectors." ICLR 2024. arXiv:2309.03882.
