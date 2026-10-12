# Quantum Mathematical Foundations for Neuro-Symbolic Computation: Applying Quantum Mechanics to Symblic

> **Speculative AI writing, revised; not a research result.** The first version of this document was generated
> by an AI model (Gemini, through Google's Antigravity agent) in October 2026, and a later AI coding agent
> corrected it against the code. No human expert has reviewed it. Its mathematics, physics and philosophy are
> not results of this project, and the links it draws to Symblic are analogies unless a section names working
> code and tests. See [../MADE-WITH-AI.md](../MADE-WITH-AI.md).

**Author:** an AI assistant (the Antigravity CLI agent, agy), asked to connect Symblic with other fields. The original header read a person and a "Codex Integration Team"; no record shows Codex writing the original text.

**Focus:** quantum logic, quantum probability and question order, categorical models of meaning (DisCoCat, ZX-calculus), measurement and decoherence, Ising ground states, linear logic and no-cloning; for each, what it would mean for Symblic and what became of the proposal

**Date:** written 2026-10-03 against Symblic 2.2; corrected 2026-10-04 against Symblic 2.4 and rechecked against Symblic 2.5 the same day

**Status:** proposal, reviewed. Not a specification: [SPEC.md](SPEC.md) specifies what was built. [REVIEW-2.3.md](REVIEW-2.3.md) records the outcome of each of this document's seven proposals: two built in reduced form in 2.3, one deferred, one claim rejected with its construction kept as a research direction, three rejected.

This corrected text keeps the original structure. Mathematics that is right is kept and stated precisely. Each part then says what Symblic does, what was proposed, and what happened to it. False claims have been replaced in place. Blocks marked "proposed syntax" are not Symblic and do not run; blocks marked `symblic` pass `check` under 2.4 and 2.5. "Q-Symblic" is this document's name for the proposed extension; no such language, mode or module exists.

---

## Executive Summary

Symblic's kernel uses two-valued Boolean logic (`and`, `or`, `not`, `xor`, `implies`, `iff`), stratified Datalog and exact rational arithmetic. The probabilities it reports are classical: the share of a vote that backs the winner, the entropy of a vote, exact binomial tails, posteriors on a finite partition. Since 2.3 it can also compute, exactly, what the projector (quantum-probability) model of question order predicts for matrices a program supplies ([OPERATORS.md](OPERATORS.md)).

The original summary said this classical base creates "fundamental friction" with deep learning, because transformers "operate in high-dimensional continuous Hilbert spaces, exhibit contextual non-commutativity, and suffer from prompt-order interference". What holds is narrower:

- A transformer's activations are real (floating-point) vectors in $\mathbb{R}^d$. That is a real inner-product space, so "Hilbert space" is true only in that trivial sense. Complex amplitudes, measurement by projection and the Born rule are not part of how a transformer computes, and its output for the next token is an ordinary probability distribution (a softmax).
- Language models' answers can depend on the order of the options and of the in-context examples (Zhao et al. 2021; Lu et al. 2022; Pezeshkpour & Hruschka 2023; Zheng et al. 2024; figures and full entries in [RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md)). Whether such effects follow the projector model is an open empirical question. This repository has no measurement of it.
- Nothing in this repository measures a conflict between a Boolean kernel and how a model computes. The kernel checks typed answers after a model returns them; it does not model the network.

The original also said the document would "demonstrate how core quantum principles resolve Symblic's deepest theoretical limitations". It demonstrated nothing. It proposed five connections in its summary and a sixth in §2.2, and REVIEW-2.3 read them against the code as seven proposals (it splits measurement into one proposal about POVMs and one about einselection). The outcomes:

1. **Birkhoff–von Neumann quantum logic** (propositions as projectors instead of `Bool`): rejected. Nothing defined which matrix a proposition would be, or how one could be estimated from model calls. The finite algebra was built as a modelling tool: `is_projector`, `commutator` and `commutes` on real rational matrices up to 8×8. `and` keeps its Boolean meaning (§1).
2. **DisCoCat and ZX-calculus** as an intermediate representation: the claim (a semantic normal form that fixes what a model answers) is rejected. The construction is kept as a research direction: compare a small tensor pipeline with structured extraction ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md); §3).
3. **Measurement theory** (a model's state as a density matrix, `ensure` as a POVM, typed outputs from decoherence): rejected, as two proposals (POVMs; decoherence and einselection). The measurable parts already existed (vote agreement and vote entropy). 2.3 added two related tools (§2, §4):
   - `ordered_probability`, the projector model's exact prediction for ordered yes/no questions;
   - the `order` library, which computes the matching quantities (the order effects and `order.qq_gap`) from counted answers.
4. **Ising/QUBO with annealing or VQE**: deferred. Annealing and VQE are heuristics: a state they return carries no proof of optimality, uniqueness or unsatisfiability. What was built is exact: `ising_minimize` evaluates every state of at most 16 spins and reports the minimum and how many states attain it. There is no annealing (§5).
5. **Linear types justified by no-cloning**: built in reduced form, as the `SYM_SAME_KEY` warning. Linear types are deferred, because capabilities are catalogue names, not values. Separately, effect identity already gives at most one automatic performance per action identity (§6).
6. **Density-matrix tracking between sequential asks** (§2.2): REVIEW-2.3 records it as built in reduced form, as `permute=K`. That probes option order inside one ask; no density matrix is tracked. Question order between asks can be measured with the `order` library and example 14; no such run is stored yet (§2.2).

None of these constructions makes model answers deterministic or prevents hallucination ([REVIEW-2.3.md](REVIEW-2.3.md)).

---

## Table of Contents
1. [Quantum Logic vs. Classical Boolean Lattices](#1-quantum-logic-vs-classical-boolean-lattices)
   - 1.1 Distributivity: Boolean Lattices and Subspace Lattices
   - 1.2 Closed Subspaces and Projection Operators
   - 1.3 Non-Commuting Projectors and Order Effects
2. [Quantum Cognition: Interference and Decision Geometry](#2-quantum-cognition-interference-and-decision-geometry)
   - 2.1 The Conjunction Fallacy and Probability Amplitudes
   - 2.2 Question Order and Sequential Asks
3. [Categorical Quantum Mechanics: DisCoCat and Tensor Networks](#3-categorical-quantum-mechanics-discocat-and-tensor-networks)
   - 3.1 Compact Closed Monoidal Categories (Abramsky & Coecke; Coecke, Sadrzadeh & Clark)
   - 3.2 ZX-Calculus and Tensor Networks
4. [Measurement and Decoherence: What an Ask Does](#4-measurement-and-decoherence-what-an-ask-does)
   - 4.1 Model State: Hidden Vectors, Softmax and Density Matrices
   - 4.2 POVMs, and What `ensure` Does
   - 4.3 Decoherence and Einselection (Zurek 2003)
5. [Hamiltonian Variational Optimization: SPD Quadratics and Ising Spin Glasses](#5-hamiltonian-variational-optimization-spd-quadratics-and-ising-spin-glasses)
   - 5.1 Mapping Symblic Constraints to Quadratic Unconstrained Binary Optimization (QUBO)
   - 5.2 The Rayleigh-Ritz Variational Principle
6. [Linear Logic and the Quantum No-Cloning Theorem](#6-linear-logic-and-the-quantum-no-cloning-theorem)
   - 6.1 The No-Cloning Theorem (Wootters & Zurek 1982)
   - 6.2 Girard's Linear Logic and the Proposed Linear Capabilities
7. [The Q-Symblic Concrete Syntax: What Was Proposed and What Exists](#7-the-q-symblic-concrete-syntax-what-was-proposed-and-what-exists)
8. [Summary: What the Quantum Proposals Changed in Symblic](#8-summary-what-the-quantum-proposals-changed-in-symblic)
- [Where This Document Came From](#where-this-document-came-from)
- [References](#references)

---

## 1. Quantum Logic vs. Classical Boolean Lattices

### 1.1 Distributivity: Boolean Lattices and Subspace Lattices
In a Boolean algebra the lattice of propositions $\mathcal{L}$ is **distributive**:
$$A \wedge (B \vee C) = (A \wedge B) \vee (A \wedge C)$$
Symblic's kernel is Boolean in this sense: `and`, `or` and `not` act on `Bool` values and obey this law.

In 1936, Garrett Birkhoff and John von Neumann ("The logic of quantum mechanics", *Annals of Mathematics* 37, 823–843) proposed that the experimental propositions of quantum mechanics correspond to the closed subspaces of a Hilbert space. "And" is intersection, "or" is the closed linear span and "not" is the orthogonal complement. That lattice is not distributive. In finite dimension it is modular, the weaker law Birkhoff and von Neumann proposed in place of distributivity. In infinite dimension it is only orthomodular (Landsman 2017, §2.10, Theorem 2.49).

```
BOOLEAN LATTICE (distributive):
  A ∧ (B ∨ C) = (A ∧ B) ∨ (A ∧ C) for every A, B, C
  ∧ and ∨ are commutative

LATTICE OF CLOSED SUBSPACES (orthomodular; modular in finite dimension; not distributive):
  A ∧ (B ∨ C) can differ from (A ∧ B) ∨ (A ∧ C)
  ∧ and ∨ are still commutative: A ∧ B = B ∧ A is the intersection
  what need not commute is the product of projectors P_A P_B, i.e. projecting in sequence
```

The smallest example uses three distinct lines $S$, $A$, $B$ through the origin of $\mathbb{R}^2$:
- $A \vee B = \mathbb{R}^2$, so $S \wedge (A \vee B) = S$;
- $S \wedge A = S \wedge B = \{0\}$, so $(S \wedge A) \vee (S \wedge B) = \{0\} \neq S$.

The failure needs projectors that do not commute: projectors that commute pairwise generate a Boolean, distributive lattice.

### 1.2 Closed Subspaces and Projection Operators
The original said that "in natural language and LLM reasoning, distributivity fails routinely". Its example used three propositions:
- $S$: the topic is financial investment;
- $A$: "bank" means a financial institution;
- $B$: "bank" means a river edge.

It said that evaluating $(S \wedge A) \vee (S \wedge B)$ "forces collapse" and creates a contradiction. It does not. Classically, with $S$ and $A$ true and $B$ false, both $S \wedge (A \vee B)$ and $(S \wedge A) \vee (S \wedge B)$ are true. The example shows that a word can be read in two ways. That is a question of which proposition a sentence expresses, not a failure of the distributive law. Nothing in this repository shows distributivity failing in language-model reasoning.

Symblic handles the underlying problem, ambiguous instructions, without changing its logic ([SPEC.md](SPEC.md) §§2–4, §12):
- `ambiguous=true` asks each model for the readings it sees, and `ambiguous=fail` stops the run when one lists two;
- `term bank means "..."` gives every ask that mentions the word the same definition;
- `one of {...}` options can carry operational definitions;
- `tighten` probes a panel of models and rewrites the asks they read differently.

The projection-operator formulation itself is standard. A proposition corresponds to an orthogonal projector $\hat{P} = \hat{P}^2 = \hat{P}^\dagger$ onto a closed subspace $\mathcal{H}_A$ of a Hilbert space $\mathcal{H}$, and:
- **Negation:** $\hat{P}_{\neg A} = \hat{I} - \hat{P}_A$, the projector onto the orthogonal complement $\mathcal{H}_A^\perp$.
- **Conjunction:** $\hat{P}_{A \wedge B} = \lim_{n \to \infty} (\hat{P}_A \hat{P}_B)^n$, a strong limit by von Neumann's alternating-projection theorem. It is the projector onto $\mathcal{H}_A \cap \mathcal{H}_B$.
- **Disjunction:** $\hat{P}_{A \vee B} = \hat{I} - \hat{P}_{\neg A \wedge \neg B}$, the projector onto the closure of $\mathcal{H}_A + \mathcal{H}_B$. It equals $\hat{P}_A + \hat{P}_B$ only when $\hat{P}_A \hat{P}_B = 0$; otherwise $\hat{P}_A + \hat{P}_B$ is not a projector, so the original's "$\hat{P}_A \oplus \hat{P}_B$" does not describe the disjunction.

**Proposed:** represent every Symblic proposition this way instead of as a `Bool`. **Outcome: rejected** ([REVIEW-2.3.md](REVIEW-2.3.md)). Nothing defined which matrices a proposition would be, how they could be estimated from black-box model calls, or what a commutator value would decide.

**Built instead (2.3):** the finite algebra, as an exact modelling tool ([OPERATORS.md](OPERATORS.md)):
- `is_projector(P)`, `commutator(A, B)` and `commutes(A, B)`;
- real rational matrices up to 8×8 only: complex projectors are not represented;
- `and` keeps its Boolean meaning.

### 1.3 Non-Commuting Projectors and Order Effects
Two propositions $A$ and $B$ are compatible if and only if their projectors commute:
$$[\hat{P}_A, \hat{P}_B] = \hat{P}_A \hat{P}_B - \hat{P}_B \hat{P}_A = 0$$
When $[\hat{P}_A, \hat{P}_B] \neq 0$ they are incompatible. In the projector model an answer replaces the state by its projection (the Lüders rule, Lüders 1951). Asking $A$ first can then change the probabilities of the answers to $B$.

The original called this "the exact mathematical framework needed to handle prompt order effects in AI pipelines". It is one candidate model of order effects, proposed for human judgments (Busemeyer & Bruza 2012; Wang & Busemeyer 2013). Whether a language model's order effects follow it is untested here. Symblic computes what the model predicts for supplied matrices (`ordered_probability`, [OPERATORS.md](OPERATORS.md)), and the `order` library measures the matching quantities from counted answers (§2.2). The runtime never applies the model on its own: these are builtins and library functions that a program calls.

---

## 2. Quantum Cognition: Interference and Decision Geometry

### 2.1 The Conjunction Fallacy and Probability Amplitudes
In classical (Kolmogorov) probability a conjunction is never more probable than either of its parts:
$$\mathbb{P}(A \wedge B) \le \mathbb{P}(A)$$
Tversky and Kahneman (1983) showed that people's probability *judgments* often violate this rule. In the Linda problem, many people rate "bank teller and active feminist" as more probable than "bank teller". The rule itself holds; the judgments break it. Tversky and Kahneman's own explanation was the representativeness heuristic. The original also said that "language understanding" systematically violates the bound. The cited work is about people's judgments (of probability, and in Busemeyer and Bruza's book also of membership in combined concepts); it says nothing about language models.

The original said quantum probability "resolves" this. It is one model that reproduces the pattern. In it, probabilities are squared lengths of projections of a state vector:
$$|\psi\rangle = \sum_i c_i |e_i\rangle, \quad c_i \in \mathbb{C}, \quad \mathbb{P}(i) = |c_i|^2$$
A judged conjunction can be read as a sequence of projections, $\|\hat{P}_B \hat{P}_A \psi\|^2$. When the projectors do not commute, this can exceed $\|\hat{P}_B \psi\|^2$ (Busemeyer, Pothos, Franco & Trueblood 2011; Busemeyer & Bruza 2012).

Take a complete set of orthogonal projectors $\{\hat{P}_{A_k}\}$, so that $\sum_k \hat{P}_{A_k} = \hat{I}$, and a unit vector $|\psi\rangle$. Then
$$\mathbb{P}(B) = \|\hat{P}_B |\psi\rangle\|^2 = \left\|\hat{P}_B \sum_k \hat{P}_{A_k} |\psi\rangle\right\|^2 = \sum_k \mathbb{P}(A_k)\, \mathbb{P}(B \mid A_k) + \underbrace{2 \sum_{j < k} \text{Re}\left(\langle \psi | \hat{P}_{A_j} \hat{P}_B \hat{P}_{A_k} | \psi \rangle\right)}_{\text{interference term } \mathcal{I}}$$
Here $\mathbb{P}(A_k)\, \mathbb{P}(B \mid A_k) = \|\hat{P}_B \hat{P}_{A_k} \psi\|^2$ is the probability of "$A_k$, then $B$" under the Lüders rule. When $\hat{P}_B$ commutes with every $\hat{P}_{A_k}$, $\mathcal{I} = 0$ and the classical law of total probability holds.

```
Classical law of total probability:
  P(B) = ∑ P(A_k) * P(B | A_k)

The same quantity in the projector model:
  P(B) = ∑ P(A_k) * P(B | A_k) + 2 ∑_{j<k} cos(θ_jk) * √(P(A_j)P(B|A_j)P(A_k)P(B|A_k))
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                 interference term; cos(θ_jk) = Re⟨u_j, u_k⟩ / (|u_j| |u_k|)
                                 with u_k = P_B P_A_k ψ
```

When $\cos\theta_{jk} > 0$ the term raises $\mathbb{P}(B)$ above the classical value, and when it is negative it lowers it. The original said this explains "why specific contextual framings dramatically boost target semantic extractions". Nothing supports that. In a cognitive model the angles are parameters fitted to data, and no measurement in this repository connects a prompt's framing to such a term.

A worked case, computed exactly by Symblic's kernel with no model call:

```symblic
program Sequence probabilities in the projector model.
note Kernel only. A projects onto the line through (1, 0), B onto the line through (1, 1); the state is (1, -1).
let A = [[1, 0], [0, 0]].
let B = [[1/2, 1/2], [1/2, 1/2]].
let s = [1, -1].
let b_alone = ordered_probability(s, [{projector: B, yes: true}]).
let a_then_b = ordered_probability(s, [{projector: A, yes: true}, {projector: B, yes: true}]).
let nota_then_b = ordered_probability(s, [{projector: A, yes: false}, {projector: B, yes: true}]).
assert b_alone = 0 and a_then_b = 1/4 and nota_then_b = 1/4.
show b_alone - (a_then_b + nota_then_b) as "interference term".
```

Asked alone, "B yes" has probability 0. "A yes, then B yes" has probability 1/4, so in this model the sequence is more probable than its last part alone. The interference term is −1/2. These are predictions of the model for these matrices. They say nothing about people or language models ([OPERATORS.md](OPERATORS.md), "What it does not establish").

### 2.2 Question Order and Sequential Asks
The original used two asks. With their types defined and the email given, they pass `check`:
```symblic
define Sentiment as Bool.
define Action as Bool.
given email: Text.
ask x: Sentiment "Is this email aggressive? {email}"
ask y: Action "Should we escalate to legal? {email}"
```

It claimed that "executing x before y produces a different posterior than executing y before x", and wrote this as $\mathbb{P}(y = 1 \mid x = 1) \neq \mathbb{P}(x = 1 \mid y = 1)$. That inequality is not an order effect. In ordinary probability the two conditionals share a numerator, $\mathbb{P}(x = 1, y = 1)$, and have different denominators, so they usually differ. An order effect compares the answer to one question across the two orders ([OPERATORS.md](OPERATORS.md), "What it does not establish").

It also said that "current Symblic assumes independence". It does not ([REVIEW-2.3.md](REVIEW-2.3.md)). Each ask's context policy sets what it sees ([SPEC.md](SPEC.md) §4):
- With the default, `context=none`, an ask is shown only the names in its `from`. So `y` above is not shown `x`'s answer, and it is asked the same thing whichever runs first. Swapping the two lines changes only the statement number on the capsule's first line (`PROGRAM: ... (statement N of M)`).
- When a later ask is given an earlier answer (`from x`, or a wider `context`), it is shown that answer, and `preview` shows the exact capsule.
- Symblic keeps no joint distribution over asks, and vote evidence records `independence: not_established`.

**Proposed:** Q-Symblic would track a density matrix $\rho$ of the conversational state and update it by projection after each ask (the Lüders rule):
$$\rho_{t+1} = \frac{\hat{P}_{x} \rho_t \hat{P}_{x}}{\text{Tr}(\hat{P}_{x} \rho_t \hat{P}_{x})}$$

**Outcome:** no density matrix is tracked, and text replies do not directly expose one. A researcher could fit a latent probabilistic model to observed response counts, but that would be a modeling choice with identifiability assumptions, not discovery of quantum neural dynamics. REVIEW-2.3 records this proposal as built in reduced form as `permute=K`. What exists is three separate, smaller tools:
- **`permute=K`: option order within one ask.**
  - A vote on a `one of` answer is taken under K rotations of the option order (K from 2 to 6), with the same seeds and temperatures.
  - The ask is stable only if every rotation has the same uncontested winner. Otherwise it is contested (`unstable_order`), and with `strict` the run fails ([SPEC.md](SPEC.md) §4; tests: `tests/kernel/test_symblic_run23.py`, `Permute`).
  - It costs K times the calls, and rotations by the same models are not independent readers.
  - No stored run in this checkout's run folders uses it (2026-10-04), so there is no measured rate of order instability for real models yet.
- **The `order` library and example 14: the order of two questions.**
  - [14-question-order.sym](../../examples/14-question-order.sym) asks two yes/no questions in both orders, with a seed per sample. `order.order_effect_a`, `order.order_effect_b` and `order.qq_gap` compute the order effects and the QQ gap exactly from the counts.
  - It measures the applicators it is run with, under those words. With few samples, a gap of 0 is easily reached by chance.
  - No run of it against models is stored in this checkout's run folders (2026-10-04).
- **`ordered_probability`: the model's prediction.**
  - It gives the exact probability of a sequence of yes/no answers for a supplied real state and real projectors, including the QQ equality.
  - It handles pure states only: density matrices and complex projectors are not represented ([OPERATORS.md](OPERATORS.md)).

A useful future comparison would fit the projector model and classical latent-state/Markov baselines on training question pairs, freeze their parameters, and compare held-out predictive loss with sampling uncertainty. A small QQ gap or an order effect alone cannot identify a uniquely quantum mechanism. This preserves the proposed probabilistic modeling experiment without claiming it has been run.

---

## 3. Categorical Quantum Mechanics: DisCoCat and Tensor Networks

### 3.1 Compact Closed Monoidal Categories (Abramsky & Coecke; Coecke, Sadrzadeh & Clark)
The original opened with "in our prior critique, we demonstrated that Montague Grammar fails because natural language is non-compositional and distributional". No such demonstration exists. The prior critique ([INTENSE-CRITIQUE-AND-LIMITATIONS.md](INTENSE-CRITIQUE-AND-LIMITATIONS.md) §2) made an argument, and REVIEW-2.3 rejected its proposal because it gave no mechanism.

Montague's approach is compositional: the meaning of a compound expression is a function of the meanings of its parts and of how they are combined, and an ambiguous string gets one derivation per reading ([RESEARCH-LANGUAGE.md](RESEARCH-LANGUAGE.md) §2.3). Isolated word-vector representations do not by themselves specify sentence composition; distributional models in general can include composition, as [DisCoCat itself proposes](https://arxiv.org/abs/1003.4394). Context dependence does not establish that language is non-compositional.

DisCoCat ("distributional compositional categorical") is the framework of Coecke, Sadrzadeh and Clark, "Mathematical foundations for a compositional distributional model of meaning" (*Linguistic Analysis* 36, 2010; arXiv:1003.4394). The original said it "solved this problem". It proposes a way to combine the two approaches:
1. **Pregroup grammars** give the grammatical types and their reductions. Lambek introduced them in 1999; the original's "Lambek 1958" is his earlier syntactic calculus.
2. **Finite-dimensional vector spaces**, a compact closed category, give the meanings. Finite-dimensional Hilbert spaces (**FdHilb**) have the same structure, and categorical quantum mechanics uses it to describe quantum protocols (Abramsky & Coecke 2004).

A compact closed category $\mathcal{C}$ has:
- a symmetric tensor product $\otimes$ with unit object $I$;
- for every object $A$, a dual object $A^*$ with a unit $\eta_A : I \to A^* \otimes A$ and a counit $\varepsilon_A : A \otimes A^* \to I$ that satisfy the "yanking" (snake) equations.

In **FdHilb**, $\eta$ is, up to normalisation, the Bell state $|\Phi^+\rangle$, and $\varepsilon$ is the matching effect. In vector-space semantics, $\varepsilon$ is tensor contraction.

```
          [ Subject: Noun (N) ]       [ Transitive Verb (N.r ⊗ S ⊗ N.l) ]       [ Object: Noun (N) ]
                   |                                |      |      |                         |
                   |                                |      |      |                         |
                   +-----------( ε_N )--------------+      |      +------( ε_N )------------+
                                                           |
                                                           v
                                              [ Sentence meaning: a vector in S ]
```

The framework gives a rule for composing meanings. It does not supply correct word meanings, and their quality has to be measured on a task ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).

### 3.2 ZX-Calculus and Tensor Networks
The original said that in Q-Symblic "the compiler does not pass unstructured strings to an LLM. It parses language into ZX-Calculus Diagrams". Neither half describes Symblic:
- An ask already sends a structured capsule ([SPEC.md](SPEC.md) §4): the known values its context policy allows, the statement, any definitions and worked examples, and an answer format with a JSON Schema for the declared type (none for a `Code` answer, which ends in a fenced code block).
- No ZX or DisCoCat code exists.

ZX-calculus is a graphical calculus for linear maps between qubits, such as quantum circuits. It was introduced by Coecke and Duncan; their full paper is "Interacting quantum observables: categorical algebra and diagrammatics" (*New Journal of Physics* 13, 043016, 2011). It is not a parser for natural language.

Backens ("The ZX-calculus is complete for stabilizer quantum mechanics", *New Journal of Physics* 16, 093021, 2014) proved completeness for the stabilizer fragment: every true equation between such diagrams can be derived. Completeness is not confluence. It gives no unique normal form that every order of rewriting reaches ([REVIEW-2.3.md](REVIEW-2.3.md)).

- **Z spiders (green)** copy the Z (computational) basis states and carry phases about the Z axis.
- **X spiders (red)** do the same for the X basis.
- **Tensor networks:**
  - The original said semantic contracts are evaluated by tensor-network contraction with "O(N) efficiency for matrix product states". Symblic evaluates no contract that way.
  - Take a matrix product state of N sites with physical dimension d and bond dimension χ. Exact contraction of an inner product of two such states costs about $O(N d \chi^3)$ (Schollwöck 2011). That is linear in N only while χ is held fixed.
  - Exact contraction of a general tensor network is #P-hard (Schuch, Wolf, Verstraete & Cirac 2007).

**Outcome** ([REVIEW-2.3.md](REVIEW-2.3.md)): the claim, a semantic normal form that fixes what a model answers, is rejected. The construction is kept as a research direction. [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md) records two next steps:
- compare a small compositional tensor pipeline with existing structured extraction on subject/object reversal, negation and paraphrase, starting from an existing library (lambeq);
- separately, an optional bounded adapter that checks supported circuit rewrites by exact matrix equality.

---

## 4. Measurement and Decoherence: What an Ask Does

The original drew this pipeline:
1. a model's "latent superposition", $|\psi\rangle = \sum c_i |\text{semantic state}_i\rangle$;
2. "system-environment entanglement" with a Symblic contract;
3. decoherence and einselection;
4. a "classical deterministic outcome": an eigenstate `|invariant_passed⟩` "with Certificate SHA-256".

None of these steps exists as described. Step 4 has a smaller real counterpart, the predicate receipt (below). This is what happens to an ask ([SPEC.md](SPEC.md) §§3–5, §8):

```
[ CAPSULE ]  the known values its context policy allows, the statement, definitions, examples,
             and the answer format (a JSON Schema for the declared type; none for Code)
     |
     v  one call per sample, to an applicator (a CLI agent, Ollama on a worker node, a browser model, ...)
[ REPLY TEXT ]  one decoded output per call
     |
     v  parse and coerce to the declared type; a reply that does not fit is discarded or repaired
[ TYPED ANSWERS ]
     |
     v  the vote (agreement, distinct answers, entropy, families), then the ensure/assert predicates,
     |  each leaving a predicate receipt in the run's evidence
[ BINDING ]  the value; its fingerprint, the first 16 hex digits of SHA-256 over canonical JSON
             (a comparison key, not a certificate or a signature); its evidence (the observations)
     |
     v  every request and reply is recorded, keyed by SHA-256 of the request
[ REPLAY ]   serves the recorded replies and asks no model
```

The quantum terms in the original diagram are an analogy, and it breaks in three places:
- A model's reply is one sample from a classical distribution over texts, not the outcome of a projective measurement on a quantum state.
- No Hamiltonian couples the reply to the check.
- The check is a Boolean predicate that the kernel evaluates on the parsed answer.

The original's "Certificate SHA-256" corresponds to something smaller. Each `ensure`, `assert` or `expect` that a run evaluates leaves a predicate receipt in the run's evidence: the hashes of the predicate and of the program source, the line, whether the check passed, the hashes of the bindings it read, the kernel identity and the scope `encoded_predicate`, identified by SHA-256 over those contents (`symblic.kernel.evidence.check_receipt`). It records that this encoded predicate was evaluated on those values, nothing more; [EVIDENCE.md](EVIDENCE.md) says it is not a standalone formal proof certificate. Separately, test certificates (`symblic/kernel/certificates.py`) attest to recorded test outcomes only, never future correctness. Since 2.5 the kernel can also check a proof certificate: a natural-deduction derivation in intuitionistic propositional logic, supplied by a person or a model, for a goal and premises the program states (`proof_check`; [PROOF-TERMS.md](PROOF-TERMS.md)). A valid one shows that the goal follows from those premises, not that the premises are true.

### 4.1 Model State: Hidden Vectors, Softmax and Density Matrices
The original said a foundation model "prior to token generation exists in a high-dimensional vector space $\mathbb{R}^d \subset \mathcal{H}$. Its latent representation is an un-collapsed density matrix". It is not ([REVIEW-2.3.md](REVIEW-2.3.md): "A softmax output is a classical distribution, not a density matrix"):
- A transformer's hidden state is a real vector.
- Its output for the next token is a softmax: a classical probability distribution over the vocabulary.
- A classical distribution can be written as a diagonal density matrix, but that adds nothing.
- [OPERATORS.md](OPERATORS.md) states that a language model's hidden state is not a quantum state.

The definitions themselves are standard. A density matrix is
$$\rho = \sum_{k} p_k |\psi_k\rangle \langle \psi_k |, \quad \text{Tr}(\rho) = 1, \quad \rho \ge 0,$$
and its von Neumann entropy is
$$\mathcal{S}(\rho) = -\text{Tr}(\rho \ln \rho).$$
For a diagonal $\rho$ this is the Shannon entropy of the diagonal, in nats.

What Symblic measures is the entropy of a vote ([SPEC.md](SPEC.md) §4, Consensus): the entropy of the distinct valid answers, in bits and also normalised by log₂ of the number of answers. It describes disagreement among the samples taken. It is not a model's internal state, and it is not a correctness score.

### 4.2 POVMs, and What `ensure` Does
In quantum mechanics an observable $\hat{M}$ has a spectral decomposition $\hat{M} = \sum_m m \hat{P}_m$. A generalized measurement (POVM) is a set of operators $\{ \hat{E}_m \}$ with
$$\sum_m \hat{E}_m = \hat{I}, \quad \hat{E}_m \ge 0.$$
The Born rule (Born 1926), in its general form for a density matrix $\rho$, gives the probability of outcome $m$ as $\text{Tr}(\hat{E}_m \rho)$. A pair made of a projector $\hat{E}_{\text{pass}}$ and $\hat{E}_{\text{fail}} = \hat{I} - \hat{E}_{\text{pass}}$ is a projection-valued measure: the special case of a POVM whose elements are projectors.

**Proposed:**
- compile each `ensure` to such a pair, and report $\mathbb{P}(\text{pass}) = \text{Tr}(\hat{E}_{\text{pass}} \rho)$;
- add options such as `minimum_amplitude` and `von_neumann_entropy_threshold`.

**Outcome: rejected** ([REVIEW-2.3.md](REVIEW-2.3.md)). There is no $\rho$ and no invariant subspace to project onto, so these quantities cannot be observed.

What `ensure` does ([SPEC.md](SPEC.md) §5): the kernel evaluates its condition, a Boolean expression, on the parsed answer. Then:
- `else retry` re-asks with feedback: the rejected values, the failed condition, and what the kernel computed for the parts of the condition that read the answer alone;
- `else fail` stops the run;
- `else warn` records a warning.

A passing check establishes conformance to the encoded predicate, and a weak predicate can accept a wrong answer.

The measurable counterpart of a "pass probability" is a pass frequency over repeated samples:
- `stats.binomial_at_least` and `stats.binomial_at_most` give exact binomial tails for it. For example, 18 passes out of 18 do not exclude a true pass rate of 85% at the 5% level ([REVIEW-2.3.md](REVIEW-2.3.md)).
- A threshold on such a frequency is a decision policy, not a passed predicate ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).

### 4.3 Decoherence and Einselection (Zurek 2003)
Einselection is environment-induced superselection. When a quantum system interacts with its environment, interference is destroyed between all but a preferred set of "pointer" states (Zurek, "Decoherence, einselection, and the quantum origins of the classical", *Reviews of Modern Physics* 75, 715–775, 2003).

The original asked, "Why does the fuzzy neural distribution collapse into a crisp deterministic string?" Its answer was einselection:
- the Symblic runtime as the measuring apparatus;
- "invariant Hamiltonians" causing phase damping ($e^{-\gamma t} \to 0$);
- the declared types (`Int`, `Bool`, `Record`) as the pointer states that survive.

**Outcome: rejected** ([REVIEW-2.3.md](REVIEW-2.3.md)): there is no mechanism beyond the typed schema and the parser, which already exist.

What happens instead:
- **One string, not a collapse.** A model produces one output per call by its decoding procedure: sampling at the given temperature, or (nearly) greedy decoding at temperature 0. By default Symblic runs sample 0 at temperature 0 and further samples at 0.7 with seeds `seed + i` (a `temperature` option overrides this, as example 14 does); this applies to local models, as cloud CLIs take no temperature ([SPEC.md](SPEC.md) §4).
- **Typed, not decohered.** Where the provider supports it (Ollama's `format`), the answer schema constrains the reply. `coerce` then checks the reply against the declared type, and a reply that does not fit is discarded or repaired ([SPEC.md](SPEC.md) §§3–4).
- **Determinism belongs to the kernel, not the model.**
  - Equal formal inputs under the same semantic kernel are intended to give equal kernel results ([SPEC.md](SPEC.md)). A fresh model call's reply can vary ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)). Temperature 0 makes decoding (nearly) greedy, so a local model is expected to repeat its reply to an identical request; example 14 assumes this, which is why it samples at 0.7 (§2.2). Nothing in this repository measures how often the reply repeats.
  - Replay is deterministic because it serves the recorded replies and asks no model ([SPEC.md](SPEC.md) §8).
  - An ask's determinism class (`closed`, `structured`, `open`) describes its mechanism, not a probability of correctness.

---

## 5. Hamiltonian Variational Optimization: SPD Quadratics and Ising Spin Glasses

Since 2.2, `symblic/adapters/variational.py` (adapter version 1) has given the kernel two builtins, `quadratic_minimize(A, b)` and `quadratic_verify(A, b, receipt)` ([VARIATIONAL.md](VARIATIONAL.md)):
- `quadratic_minimize` returns the exact minimum of
  $$H(x) = \frac{1}{2} x^T A x - b^T x, \qquad x \in \mathbb{R}^n,$$
  for an explicitly supplied rational, symmetric positive-definite $A$ with $n \le 32$. It factors $A = L\,\text{diag}(D)\,L^T$ exactly, solves $Ax = b$, and returns the factors as a witness.
- `quadratic_verify` checks that witness separately.
- They are not connected to `solve=true`, which still works by enumeration.
- They are not a PDE or vorticity solver.

The original said that "in quantum physics, this is mathematically isomorphic to finding the Ground State of an Ising Spin Glass Hamiltonian". That is false ([REVIEW-2.3.md](REVIEW-2.3.md)). The two problems differ in their domain and in their difficulty:
- With $A$ positive definite, $H$ is strictly convex over $\mathbb{R}^n$. Its unique minimiser solves the linear system $Ax = b$, which takes one linear solve (Boyd & Vandenberghe 2004, Example 4.5).
- An Ising ground state minimises a quadratic function of $n$ spins, each $-1$ or $+1$. Ground states need not be unique: with no field, flipping every spin keeps the energy. Finding one for a general spin glass is NP-hard (Barahona 1982).

The quadratic solver is also not a Rayleigh-Ritz eigenvalue problem (§5.2; [REVIEW-2.3.md](REVIEW-2.3.md)).

### 5.1 Mapping Symblic Constraints to Quadratic Unconstrained Binary Optimization (QUBO)
An Ising model on $n$ spins has the Hamiltonian
$$\hat{H}_{\text{Ising}} = \sum_{i} h_i \hat{\sigma}_i^z + \sum_{i < j} J_{ij} \hat{\sigma}_i^z \hat{\sigma}_j^z,$$
where $\hat{\sigma}^z = \begin{pmatrix} 1 & 0 \\ 0 & -1 \end{pmatrix}$ is the Pauli $Z$ matrix. This operator is diagonal: its eigenvalues are the classical energies of the $2^n$ spin states.

The original said that "any set of discrete Symblic constraints (satisfiability, graph routing, budget allocation, schedule validation) can be mapped to an Ising Hamiltonian". In principle, constraints over a finite domain can be written as a penalty QUBO, and many NP-complete problems have published Ising formulations (Lucas 2014). Such encodings often need auxiliary spins and carefully chosen penalty weights, and their size depends on the constraints. Symblic has no such compiler; `compile_to_qubo` does not exist.

The original's example encoded `ensure (x1 xor x2) and (x2 or not x3)` as "$H_{\text{Ising}} = -2\sigma_1^z\sigma_2^z + \sigma_2^z\sigma_3^z + h_1\sigma_1^z \ldots$". It called this a "mathematical isomorphism" and wrote "minimum energy $E_0$ ⟺ exact invariant satisfaction". Those terms have the wrong signs:
- Under the original's own sign convention, $-2\sigma_1^z\sigma_2^z$ favours equal spins, the opposite of xor.
- The two ground states of $-2\sigma_1^z\sigma_2^z + \sigma_2^z\sigma_3^z$ are $(-1,-1,+1)$ and $(+1,+1,-1)$, and both violate the constraint.

A correct penalty encoding, with $x_i = (1 + s_i)/2$, charges one unit for each violated part:
$$P = \underbrace{x_1 x_2 + (1-x_1)(1-x_2)}_{\text{violated when } x_1 = x_2} + \underbrace{(1 - x_2)\,x_3}_{\text{violated when } x_2 = 0,\ x_3 = 1} = \tfrac34 - \tfrac14 s_2 + \tfrac14 s_3 + \tfrac12 s_1 s_2 - \tfrac14 s_2 s_3$$
The minimum of $P$ is 0 exactly when the constraint can be satisfied, and the ground states are then the satisfying assignments. "Minimum energy ⟺ satisfaction" holds only for an encoding built this way, with its constant tracked.

Symblic can check this encoding exactly with `ising_minimize` (since 2.3, [DISCRETE.md](DISCRETE.md)). It uses $E(s) = -\sum_i h_i s_i - \sum_{i<j} J_{ij} s_i s_j$ and leaves out constants. So $P = E + \tfrac34$, with $h = (0, \tfrac14, -\tfrac14)$, $J_{12} = -\tfrac12$ and $J_{23} = \tfrac14$:

```symblic
let h = [0, 1/4, -1/4].
let J = [[0, -1/2, 0], [-1/2, 0, 1/4], [0, 1/4, 0]].
let g = ising_minimize(h, J).
assert g.energy = -3/4 and g.degeneracy = 3.
show g.states.
```

It shows `[[-1, 1, -1], [-1, 1, 1], [1, -1, -1]]`: three ground states at $E = -\tfrac34$, which is $P = 0$, one for each satisfying assignment. Two limits apply ([DISCRETE.md](DISCRETE.md)):
- It evaluates all $2^n$ states, so it is limited to 16 spins.
- That the numbers encode the intended problem is the author's claim; the adapter does not check it.

For a finite constraint like this one, Symblic needs no Ising encoding at all. When an ask's type has a finite domain of at most 20 000 values and its anchored `ensure` uses only builtin kernel calls, the kernel checks the candidates against that `ensure` by enumeration ([SPEC.md](SPEC.md) §5). Take an ask of type `Record {x1: Bool, x2: Bool, x3: Bool}` with this `ensure` and `solve=true`:
- the kernel evaluates all 8 values, finds that 3 pass, and reports `underdetermined` with witnesses;
- asked of the kernel alone (`by kernel`), the run fails with `SYM_UNDERDETERMINED` rather than pick one, after zero model calls.

### 5.2 The Rayleigh-Ritz Variational Principle
For a Hermitian $\hat{H}$, the lowest eigenvalue bounds the energy of every trial state:
$$E_0 = \min_{|\psi\rangle} \frac{\langle \psi | \hat{H} | \psi \rangle}{\langle \psi | \psi \rangle} \le \frac{\langle \psi_{\text{trial}} | \hat{H} | \psi_{\text{trial}} \rangle}{\langle \psi_{\text{trial}} | \psi_{\text{trial}} \rangle}$$
For the diagonal Ising operator of §5.1, $E_0$ is simply the smallest classical energy, so the principle does not make the search easier. It is also not the problem `quadratic_minimize` solves: minimising the Rayleigh quotient is an eigenvalue problem, and minimising $H(x)$ is a linear solve.

The original said that when an invariant fails, "instead of performing blind token retries, the Q-Symblic solver executes Variational Quantum Eigensolving (VQE) or Simulated Quantum Annealing (SQA)". Both halves are wrong:
- **Retries are not blind** ([SPEC.md](SPEC.md) §5).
  - A failed `ensure ... else retry` restores the run's state. It then re-asks with feedback: the rejected values, the failed condition, and the kernel's values for the parts that depend on the answer alone.
  - Retries are bounded (default 2, at most 5). When they run out, the report says whether the rejected answers were all the same, all different, or mixed.
  - `route=escalate` and `route=search` check every candidate before accepting one.
- **No VQE, SQA or annealing exists.**
  - REVIEW-2.3 deferred them. A heuristic candidate alone does not certify optimality, uniqueness or unsatisfiability. This is a weaker assurance than complete enumeration but can search domains beyond the enumerator's resource limit; it is not a reason to forbid the capability.
  - The original source search found only the discrete adapter's statement that it used no annealing. This is historical search evidence, not a capability restriction or a current exhaustive source audit.

An optional bounded search backend could propose assignments while an independent checker evaluates their constraints and objective. Record `best found`, `proved optimal`, `unsatisfiable` and `unknown` as different outcomes; compare against classical search at matched budgets. No such backend or advantage is established here. A constraint-to-QUBO compiler would also need to expose auxiliary variables, penalty bounds and witness reconstruction so the encoding can be checked against the original constraints.

The proposed schedule, for reference, is that of quantum annealing (Kadowaki & Nishimori 1998) and, when run slowly enough, of adiabatic quantum computation (Farhi, Goldstone, Gutmann & Sipser 2000):
1. Start in the ground state of a transverse-field driver $\hat{H}_{\text{driver}} = -\sum_i \hat{\sigma}_i^x$.
2. Change the Hamiltonian slowly to the problem:
   $$\hat{H}(t) = \left(1 - \frac{t}{T}\right) \hat{H}_{\text{driver}} + \frac{t}{T} \hat{H}_{\text{problem}}$$
3. Rely on the adiabatic theorem (Born & Fock 1928). A system that starts in the ground state stays close to the instantaneous ground state if the Hamiltonian changes slowly enough compared with the gap above it. The usual rule of thumb is $T \gg 1/\Delta_{\min}^2$, times a matrix-element factor. Rigorous bounds have further terms (Jansen, Ruskai & Seiler 2007).

The original concluded that the system "is guaranteed to reach the globally optimal invariant-satisfying state without getting trapped in local classical minima". That guarantee does not hold:
- Under its conditions, the theorem gives closeness to the ground state, with high probability. The time it needs depends on the minimum gap $\Delta_{\min}$, which is not known in advance for a given instance. Altshuler, Krovi and Roland (2010) argued that along the linear path above, random instances of some NP-complete problems have a $\Delta_{\min}$ that becomes exponentially small in $n$, so $T$ must grow exponentially. That does not show that every other path fails ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)).
- SQA is a classical Monte Carlo simulation of quantum annealing (Santoro, Martoňák, Tosatti & Car 2002), and VQE is a hybrid quantum-classical variational method (Peruzzo et al. 2014). Neither carries the adiabatic theorem's assurance.
- Whether quantum annealing finds ground states more efficiently than classical algorithms such as simulated annealing was, in Young's words, "hotly debated at present" (Young 2021, ch. 22, note 2).

---

## 6. Linear Logic and the Quantum No-Cloning Theorem

### 6.1 The No-Cloning Theorem (Wootters & Zurek 1982)
The theorem (Wootters & Zurek, "A single quantum cannot be cloned", *Nature* 299, 802–803, 1982; independently Dieks 1982) says that no unitary $U$ satisfies
$$U (|\psi\rangle \otimes |0\rangle) = |\psi\rangle \otimes |\psi\rangle \quad \text{for every state } |\psi\rangle .$$
A unitary can copy the states of one orthonormal basis: CNOT copies $|0\rangle$ and $|1\rangle$ onto a target in $|0\rangle$. Linearity forbids copying their superpositions as well (Young 2021, §4.2).

The original gave the theorem as a quotation. The sentence is a paraphrase, not a quotation from the paper. Its formula, $U (|\psi\rangle \otimes |0\rangle) \neq |\psi\rangle \otimes |\psi\rangle$, also reads as "for every $U$ and every $\psi$", which is false.

Classical data, by contrast, can be copied, and programs copy it all the time. The original said this "causes critical vulnerabilities in agentic systems", such as double-spending tokens or capabilities and leaking private data into several subagent branches. Those are real risks in general. Symblic handles them with explicit rules, not by preventing copies:
- **Names are immutable.** A name is bound once per scope, and rebinding it is an error ("Symblic names are immutable").
- **An action happens at most once per identity** ([EFFECTS.md](EFFECTS.md) §4).
  - An `act`'s identity is a SHA-256 hash over its capability and arguments, or over its capability and key when it has a key.
  - In one ledger, an identity is performed at most once automatically.
  - An unknown outcome of a non-idempotent action stops the run until the operator settles it.
  - This is not exactly-once: the world can act and the record be lost.
- **Capabilities are not values.** A capability is a name in the host's catalogue, with an effect class and an approval policy (`auto`, `confirm` or `never`). A program cannot copy or pass one ([EFFECTS.md](EFFECTS.md) §3).
- **Private data has flow rules** ([EFFECTS.md](EFFECTS.md) §5).
  - A `personal` value may not be an argument of a capability with `egress`.
  - An ask shown personal data raises a warning that names the applicator.
  - Text that someone outside controls may not be an action's argument unless the author names that argument in `allow_untrusted`, and it is never an agent's or a program's instructions.
  - When outside text chose an action or wrote part of it, and the capability is weighty (an effect class such as `money` or `destructive`, or one that instructs an agent), the host is told `needs_owner`.
  - Each ask sees only what its context policy names (`context=none` by default).

### 6.2 Girard's Linear Logic and the Proposed Linear Capabilities
Jean-Yves Girard's linear logic ("Linear logic", *Theoretical Computer Science* 50(1), 1–101, 1987) treats hypotheses as resources. Without the exponential modality `!`, a hypothesis can be neither duplicated (there is no contraction rule) nor discarded (there is no weakening rule). `!A` restores both, under control.

The original said that "category theory proves that Linear Logic is the internal language of symmetric monoidal categories with duals (Hilbert spaces)". As stated that is wrong:
- Categorical models of classical multiplicative linear logic are *-autonomous categories (Barr 1979; Seely 1989).
- Compact closed categories, such as finite-dimensional Hilbert spaces with ⊗, are the degenerate *-autonomous categories in which ⊗ and ⅋ coincide. Infinite-dimensional Hilbert spaces are not compact closed.
- The correspondence is one of structure. The no-cloning theorem implies neither linear logic nor any typing rule for a classical program ([REVIEW-2.3.md](REVIEW-2.3.md)).

```
# proposed syntax (not Symblic: `type ... [T]`, brace-delimited bodies and `consume` do not exist, and capabilities are not values)
type QCapability[T]  # Linear: Must be consumed exactly once!

routine TransferFunds(cap: QCapability[BankAccess], amount: Int) {
    act bank.execute(consume(cap), amount)
}
```

The original said that a second use of `cap` would be rejected at static check time "based on the Quantum No-Cloning Theorem". Nothing in Symblic rejects it: the type does not exist. In Symblic an `act` may not appear inside a `function`, `routine` or `test` at all ([EFFECTS.md](EFFECTS.md) §2).

**Outcome** ([REVIEW-2.3.md](REVIEW-2.3.md)): built in 2.3 in reduced form, as a warning. Linear types for capabilities are deferred. Affine handles for genuinely one-use local resources are a research direction ([RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)). The warning, `SYM_SAME_KEY`, fires when two `act` statements that can run on one path name the same capability and the same literal key, because the second would be served the first one's outcome:

```symblic
act a = notes.write(text="one") with key="daily".
act b = notes.write(text="two") with key="daily".
```

`check` reports at line 2: `act notes.write: the key "daily" is also used at line 1; an action with a key happens once, so this statement would get that one's outcome`. Without a host catalogue that declares `notes.write`, it also warns that the capability is unchecked. The warning never refuses a program, and statements in different branches of one `if` are not compared ([SPEC.md](SPEC.md) §5; tests: `tests/kernel/test_symblic_diagnose.py`, `SameKey`).

---

## 7. The Q-Symblic Concrete Syntax: What Was Proposed and What Exists

The original presented a `module QuantumEpistemicEngine { ... }` as "how these mathematical physics principles translate into concrete Symblic language extensions". It is not Symblic, and none of it was built:
- Brace-delimited blocks, `struct`, `contract`, `invariant`, `kernel` blocks and `var` do not exist in the language ([REVIEW-2.3.md](REVIEW-2.3.md)). Braces appear only in records, sets, `one of` options and string interpolation ([SPEC.md](SPEC.md) §§1, 3).
- There are no `qask`, `povm`, `anneal`, `compile_to_qubo` or `variational_quantum_solve`.
- Its last line was `assert ground_state.energy == 0.0, "Constraints are mathematically unsatisfiable."` That conclusion would be wrong: when a heuristic solver (VQE, QAOA) fails to reach energy 0, it has not shown that no satisfying state exists.

What it proposed, part by part, and what exists:

| Proposed part | Outcome | What exists in 2.5 |
|---|---|---|
| `StateVector`, `DensityMatrix` and complex `Observable` types | Rejected (§1, §4) | Real rational matrices and vectors as ordinary lists; `is_projector`, `commutator`, `commutes`, `ordered_probability` ([OPERATORS.md](OPERATORS.md)) |
| `contract QuantumIntersubjectiveCheck`: trace 1, positive semidefinite, `commutator(Obs.LinguisticFrame, Obs.BehavioralFrame) == 0.0` | Rejected: the "frames" are undefined matrices | `assert commutes(A, B)` on matrices the program supplies |
| `qask ... by povm(basis="computational", von_neumann_entropy_threshold=0.45)`, `ensure ... with minimum_amplitude=0.85 else anneal(...)` | Rejected; annealing deferred | `ask` with a `one of` type, `votes`, `permute=K` and `strict`; vote agreement and entropy; `ensure ... else retry`, `else fail` or `else warn` |
| `kernel SolveScheduleInvariants`: `compile_to_qubo`, `variational_quantum_solve(optimizer="vqe_qaoa")` | Deferred | Enumeration of finite domains (`solve=true`, at most 20 000 values); `ising_minimize` (at most 16 spins); `quadratic_minimize` (SPD, n ≤ 32) |

The following program uses only what exists. It runs in the kernel with no model call (`tools/symblic run FILE --by kernel --max-calls 0`):

```symblic
program Exact computations from this document.
note Kernel only: no model is asked.
let A = [[1, 0], [0, 0]].
let B = [[1/2, 1/2], [1/2, 1/2]].
let state = [2, 1].
assert is_projector(A) and is_projector(B) and not commutes(A, B).
let a_first = ordered_probability(state, [{projector: A, yes: true}]).
let a_second = ordered_probability(state, [{projector: B, yes: true}, {projector: A, yes: true}]) + ordered_probability(state, [{projector: B, yes: false}, {projector: A, yes: true}]).
assert a_first = 4/5 and a_second = 1/2.
let h = [0, 1/4, -1/4].
let J = [[0, -1/2, 0], [-1/2, 0, 1/4], [0, 1/4, 0]].
let g = ising_minimize(h, J).
assert g.energy = -3/4 and g.degeneracy = 3.
let q = quadratic_minimize([[4, 1], [1, 3]], [1, 2]).
assert quadratic_verify([[4, 1], [1, 3]], [1, 2], q) and q.x = [1/11, 7/11].
show g.states.
```

It ends `done` with 0 asks and 0 calls, and shows `[[-1, 1, -1], [-1, 1, 1], [1, -1, -1]]`. Its first part is the order effect worked in [OPERATORS.md](OPERATORS.md): P(A yes) is 4/5 when A is asked first and 1/2 when B is asked first.

The closest working form of the proposed `qask` asks a model, so it needs an applicator:

```symblic
program Withdrawal or deposit.
define Intent as one of {withdraw, deposit, query}.
given transcript: Text.
ask intent: Intent "Which request does this transcript make? {transcript}" with votes=3, permute=3, strict=true
ensure intent != "query" else fail because "this program handles withdrawals and deposits only".
return intent.
```

The vote is taken under three rotations of the option order, at three times the calls of one vote. With `strict`, a contested vote, or a winner that changes with the order, fails the run. The `ensure` is an ordinary Boolean check on the typed answer, not a measurement.

---

## 8. Summary: What the Quantum Proposals Changed in Symblic

| Limitation the original named | Mathematics it invoked | What Symblic 2.5 has (REVIEW-2.3 outcome) |
| :--- | :--- | :--- |
| "Distributive Boolean Logic fails on language nuance" | The Birkhoff–von Neumann lattice of closed subspaces | `and` stays Boolean. Ambiguity is handled by `ambiguous` readings, `term` definitions, defined options and `tighten`. Projector algebra as a modelling tool: `is_projector`, `commutator`, `commutes` (rejected as a replacement for `Bool`; finite algebra built) |
| "Prompt order destroys inference calibration". What holds: answers can depend on option and example order | Quantum probability and interference | `permute=K` probes option order inside one ask. The `order` library and example 14 measure question-order effects and the QQ gap from counts. `ordered_probability` computes the projector model's prediction. No density matrix (built in reduced form) |
| "Montague Grammar destroys semantic context" | DisCoCat, ZX-calculus | Nothing built. A tensor-pipeline comparison and a bounded circuit-rewrite checker are research directions (claim rejected; construction deferred) |
| "Brittle 0/1 boolean assert failures" | POVMs, decoherence | Checks stay exact predicates. Failures are handled by retries with feedback, `else warn`, checked escalation and search. Numeric answers can use `vote=median` with `within`. Pass rates have exact binomial tails (rejected) |
| "Exponential combinatorial retry loops" | Ising ground states, Rayleigh–Ritz, annealing | Retries are bounded (default 2, at most 5), and a run's default limit is 2 000 fresh model calls. Finite domains with supported anchored checks are decided by enumeration (at most 20 000 values), and `ising_minimize` is exact up to 16 spins. No annealing or VQE (deferred) |
| "Double-spending of capabilities & tokens" | The no-cloning theorem, linear logic | Immutable names; at most one automatic performance per action identity; the `SYM_SAME_KEY` warning; catalogue approval policies and flow labels. Linear types deferred; affine one-use handles are a research direction (built in reduced form) |

---

## Where This Document Came From

The original's closing section said the treatise "has been formally committed" to three places. It had been saved there, not committed: on 2026-10-04, when this correction was written, `git status` still showed the file as untracked (`??`). The three places are:
1. This file, `docs/reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md`, written 2026-10-03 at 16:04 (host local time).
2. A shorter copy in the agy session's "brain" folder, `~/.gemini/antigravity-cli/brain/cb867bcf-a440-490a-9c7f-a37ea83e1eb5/symblic_quantum_foundations.md`. It keeps the original claims.
3. [SYMBLIC-BREAKTHROUGH-COMPENDIUM.md](SYMBLIC-BREAKTHROUGH-COMPENDIUM.md) §25, which summarised the original claims. It was corrected in the same 2026-10-04 set and now states each proposal and what became of it.

[REVIEW-2.3.md](REVIEW-2.3.md), section "QUANTUM-FOUNDATIONS-OF-SYMBLIC.md", records what was done with each proposal.

---

## References

Primary sources for the results named above. A local copy is given where one exists.

- Abramsky, S., & Coecke, B. (2004). A categorical semantics of quantum protocols. *Proceedings of the 19th Annual IEEE Symposium on Logic in Computer Science (LICS 2004)*.
- Altshuler, B., Krovi, H., & Roland, J. (2010). Anderson localization makes adiabatic quantum optimization fail. *Proceedings of the National Academy of Sciences* 107. arXiv:0908.2782.
- Backens, M. (2014). The ZX-calculus is complete for stabilizer quantum mechanics. *New Journal of Physics* 16, 093021. arXiv:1307.7025.
- Barahona, F. (1982). On the computational complexity of Ising spin glass models. *Journal of Physics A: Mathematical and General* 15, 3241–3253.
- Barr, M. (1979). *\*-Autonomous Categories*. Lecture Notes in Mathematics 752, Springer.
- Birkhoff, G., & von Neumann, J. (1936). The logic of quantum mechanics. *Annals of Mathematics* 37, 823–843.
- Born, M. (1926). Zur Quantenmechanik der Stoßvorgänge. *Zeitschrift für Physik* 37, 863–867.
- Born, M., & Fock, V. (1928). Beweis des Adiabatensatzes. *Zeitschrift für Physik* 51, 165–180.
- Boyd, S., & Vandenberghe, L. (2004). *Convex Optimization*. Cambridge University Press. Example 4.5 (§4.2.3), printed pp. 140–141., PDF page 154.
- Busemeyer, J. R., & Bruza, P. D. (2012). *Quantum Models of Cognition and Decision*. Cambridge University Press.
- Busemeyer, J. R., Pothos, E. M., Franco, R., & Trueblood, J. S. (2011). A quantum theoretical explanation for probability judgment errors. *Psychological Review* 118(2), 193–218.
- Coecke, B., & Duncan, R. (2011). Interacting quantum observables: categorical algebra and diagrammatics. *New Journal of Physics* 13, 043016.
- Coecke, B., Sadrzadeh, M., & Clark, S. (2010). Mathematical foundations for a compositional distributional model of meaning. *Linguistic Analysis* 36 (Lambek Festschrift). arXiv:1003.4394.
- Dieks, D. (1982). Communication by EPR devices. *Physics Letters A* 92(6), 271–272.
- Farhi, E., Goldstone, J., Gutmann, S., & Sipser, M. (2000). Quantum computation by adiabatic evolution. arXiv:quant-ph/0001106.
- Girard, J.-Y. (1987). Linear logic. *Theoretical Computer Science* 50(1), 1–101.
- Jansen, S., Ruskai, M. B., & Seiler, R. (2007). Bounds for the adiabatic approximation with applications to quantum computation. *Journal of Mathematical Physics* 48.
- Kadowaki, T., & Nishimori, H. (1998). Quantum annealing in the transverse Ising model. *Physical Review E* 58, 5355.
- Lambek, J. (1958). The mathematics of sentence structure. *American Mathematical Monthly* 65(3), 154–170.
- Lambek, J. (1999). Type grammar revisited. In *Logical Aspects of Computational Linguistics* (LACL '97), Lecture Notes in Computer Science 1582, Springer.
- Landsman, K. (2017). *Foundations of Quantum Theory: From Classical Concepts to Operator Algebras*. Fundamental Theories of Physics 188, Springer. §2.10, Theorem 2.49.
- Lucas, A. (2014). Ising formulations of many NP problems. *Frontiers in Physics* 2, 5. arXiv:1302.5843.
- Lüders, G. (1951). Über die Zustandsänderung durch den Meßprozeß. *Annalen der Physik*.
- Peruzzo, A., McClean, J., Shadbolt, P., Yung, M.-H., Zhou, X.-Q., Love, P. J., Aspuru-Guzik, A., & O'Brien, J. L. (2014). A variational eigenvalue solver on a photonic quantum processor. *Nature Communications* 5, 4213.
- Santoro, G. E., Martoňák, R., Tosatti, E., & Car, R. (2002). Theory of quantum annealing of an Ising spin glass. *Science* 295, 2427–2430.
- Schollwöck, U. (2011). The density-matrix renormalization group in the age of matrix product states. *Annals of Physics* 326, 96–192.
- Schuch, N., Wolf, M. M., Verstraete, F., & Cirac, J. I. (2007). Computational complexity of projected entangled pair states. *Physical Review Letters* 98, 140506.
- Seely, R. A. G. (1989). Linear logic, \*-autonomous categories and cofree coalgebras. In *Categories in Computer Science and Logic*, Contemporary Mathematics 92, American Mathematical Society.
- Tversky, A., & Kahneman, D. (1983). Extensional versus intuitive reasoning: the conjunction fallacy in probability judgment. *Psychological Review* 90(4), 293–315.
- Wang, Z., & Busemeyer, J. R. (2013). A quantum question order model supported by empirical tests of an a priori and precise prediction. *Topics in Cognitive Science* 5(4), 689–710.
- Wootters, W. K., & Zurek, W. H. (1982). A single quantum cannot be cloned. *Nature* 299, 802–803.
- Young, P. (2021). *An Undergraduate Course on Quantum Computing*, 2nd edition (UC Santa Cruz lecture notes). §4.2 (the no-cloning theorem); ch. 22, note 2 (quantum versus simulated annealing).
- Zurek, W. H. (2003). Decoherence, einselection, and the quantum origins of the classical. *Reviews of Modern Physics* 75, 715–775.
- Order sensitivity in language models: Zhao et al. (ICML 2021), Lu et al. (ACL 2022), Pezeshkpour & Hruschka (arXiv:2308.11483), Zheng et al. (ICLR 2024). Full entries are in [RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md).
