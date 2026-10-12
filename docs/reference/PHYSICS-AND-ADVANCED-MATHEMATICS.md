# Modern Mathematical Physics and Symblic: The 2026 Navier-Stokes Announcement and Five Proposed Borrowings

> **Speculative AI writing, revised; not a research result.** The first version of this document was generated
> by an AI model (Gemini, through Google's Antigravity agent) in October 2026, and a later AI coding agent
> corrected it against the code. No human expert has reviewed it. Its mathematics, physics and philosophy are
> not results of this project, and the links it draws to Symblic are analogies unless a section names working
> code and tests. See [../MADE-WITH-AI.md](../MADE-WITH-AI.md).

**Author / Maintainer Context:** Written on 2026-10-03 by AGY (Antigravity), which had been asked to criticize Symblic and to connect it with other fields (REVIEW-2.3.md:3-4; changelog.md, 2026-10-03 entry). The original header named a person and a "Codex Integration Team" instead. It is one of the nine proposal documents reviewed in [REVIEW-2.3.md](REVIEW-2.3.md). Corrected on 2026-10-04 against the Symblic 2.4 code and REVIEW-2.3.md; where Symblic 2.5 differs on a point used here, the text says so.

**Focus:** Six topics: the 2026 Navier-Stokes announcement, Sobolev regularity and the Beale-Kato-Majda criterion, symplectic geometry and Noether's theorem, Wilsonian renormalization, information geometry, and optimal transport. For each, what it gives Symblic and what it does not.

**Date:** Written 3 October 2026; corrected 4 October 2026.

**Status:** This is a background note and a record of proposals. It is not a language specification; [SPEC.md](SPEC.md) is. The mathematics is standard, and it is stated with its sources. The document made six proposals, with these outcomes ([REVIEW-2.3.md](REVIEW-2.3.md), lines 230-241):
- one was built in a reduced form (`vote=median`);
- one claim was rejected, but its construction was kept as a research direction (comparing natural-gradient updates);
- four were rejected, including the §7 "contract" construct.

---

## Executive summary

On 8 September 2026 OpenAI announced a proof of finite-time blow-up for the three-dimensional Navier-Stokes equations driven by a smooth external force. The proof was formalized in Lean. Two repository records treat the announcement as real: REVIEW-2.3.md (lines 115-120) and RESEARCH-ADOPTION.md (section "Geometry, optimization and physics"). REVIEW-2.3 also records that the result was unrefereed when it was reported, and that its credit was disputed. Neither record claims to have checked the proof; RESEARCH-ADOPTION.md says it has not.

The original version of this document made two claims about the announcement:
- that Terence Tao, Tristan Buckmaster and other analysts had exposed the result as "specification gaming";
- that the gaming consisted of meeting the letter of the Clay problem with a tailored force instead of answering the physical question.

No source is given for those claims. Apart from this document's original text, only the original §27 of the compendium made them; both were written by AGY. The gaming claim is unsupported (REVIEW-2.3.md:120). A forced blow-up is not a loophole. Fefferman's official statement of the Clay problem lists breakdown under a smooth forcing term (statements C and D) as an accepted resolution.

**What carries over to Symblic is narrower.** A machine check establishes the statement that was checked, and nothing more:
- Lean checks that a proof proves its stated theorem.
- A Symblic `ensure` checks that an answer satisfies its stated predicate.

Neither notices when the statement differs from the question someone cares about. Symblic's specification already says so (SPEC.md §5), and §1.3 lists what the language does about weak checks. Conservation laws, symplectic structure and geometric invariants help only in programs that actually model systems with those properties.

The document then took five areas of mathematical physics and proposed a Symblic feature for each. The mathematics is correct where it is stated below. The proposals fared as follows.

1. **Sobolev norms and the Beale-Kato-Majda criterion.** BKM (1984) show when a smooth solution of the 3-D Euler or Navier-Stokes equations can stop being smooth: only if the time integral of the maximum vorticity diverges.
   - It is a criterion, not a bound.
   - Its quantity is vorticity, not enstrophy.
   - Nothing in it can be computed from a model's reasoning. Symblic bounds runaway runs with step, depth, ask, call and retry limits instead.

   *Rejected.*
2. **Symplectic geometry and Noether's theorem.** Hamiltonian flows preserve the 2-form $\omega = \sum_i dq_i \wedge dp_i$, and continuous symmetries of an action give conserved quantities.
   - Each proposed check was either vacuous ($d(dq \wedge dp) = 0$ for every trajectory) or wrong (energy conservation for a viscous fluid).
   - Exact conservation checks over a program's own numbers already existed.

   *Rejected.*
3. **Wilsonian renormalization.** Integrating out short-wavelength modes gives an effective description of long-wavelength physics.
   - The proposal rested on a false premise. Capsules do not wipe context arbitrarily: the author sets the context policy, and the capsule reports what did not fit.
   - It would also have added an unchecked, lossy summarizer.

   *Rejected; source-linked summaries remain a research direction.*
4. **Information geometry.** The Fisher information is a Riemannian metric on a regular statistical model, and the natural gradient preconditions a gradient with its inverse.
   - Symblic's exact quadratic solver already accepts any rational symmetric positive-definite matrix. So it can compute one natural-gradient direction from a supplied Fisher matrix and gradient.
   - It is not a natural-gradient optimizer.
   - Natural-gradient steps neither follow geodesics nor take the fewest steps.

   *Claim rejected; a comparison is deferred as research.*
5. **Optimal transport.** Wasserstein distances compare distributions whose supports differ.
   - Symblic's votes are not token votes: they group typed answers (whole, or field by field for records) by exact canonical identity.
   - The recorded outcome was `vote=median`, the weighted median of numeric answers, which minimizes the summed Wasserstein-1 distance to them.
   - The `wasserstein1` distance was added separately in the same release.

   *Built in a reduced form.*

---

## Table of contents
1. [The 2026 Navier-Stokes announcement](#1-the-2026-navier-stokes-announcement)
   - 1.1 What was announced
   - 1.2 The "specification gaming" reading, and why it does not hold
   - 1.3 The lesson for Symblic: a check certifies its predicate
2. [Sobolev spaces and the mathematics of regularity](#2-sobolev-spaces-and-the-mathematics-of-regularity)
   - 2.1 The Navier-Stokes Cauchy problem
   - 2.2 The Beale-Kato-Majda (BKM) criterion
   - 2.3 "Cognitive blow-up": an analogy, and what Symblic actually bounds
3. [Symplectic geometry and Noether's theorem](#3-symplectic-geometry-and-noethers-theorem)
   - 3.1 The symplectic 2-form and Liouville's theorem
   - 3.2 Noether's theorem (1918)
   - 3.3 Conservation checks in Symblic
4. [Wilsonian renormalization and context](#4-wilsonian-renormalization-and-context)
   - 4.1 Wilson's renormalization group (1971)
   - 4.2 Relevant, marginal and irrelevant couplings, and the analogy to text
   - 4.3 The proposed RG context engine (not built)
5. [Information geometry: the Fisher-Rao metric](#5-information-geometry-the-fisher-rao-metric)
   - 5.1 The statistical manifold $\mathcal{M}$
   - 5.2 Symblic's quadratic solver and the natural gradient
6. [Optimal transport and Wasserstein barycenters](#6-optimal-transport-and-wasserstein-barycenters)
   - 6.1 The Wasserstein metric and Kantorovich-Rubinstein duality
   - 6.2 Multi-agent consensus: what Symblic computes and what was built
7. [The proposed physics-informed specification, and its real counterparts](#7-the-proposed-physics-informed-specification-and-its-real-counterparts)
8. [Summary](#8-summary)

- [Sources](#sources)
- [Where this document is recorded](#where-this-document-is-recorded)

---

## 1. The 2026 Navier-Stokes announcement

### 1.1 What was announced
On 8 September 2026 OpenAI announced a proof of finite-time blow-up for the 3-D incompressible Navier-Stokes equations driven by a smooth external force, formalized in the Lean proof assistant ([announcement](https://openai.com/index/navier-stokes-solution/)). Two repository records describe it:
- RESEARCH-ADOPTION.md (section "Geometry, optimization and physics"): the announcement describes finite energy and a smooth external force.
- REVIEW-2.3.md (lines 115-120): when it was reported, the result was unrefereed and its credit was disputed ([Smithsonian report](https://www.smithsonianmag.com/smart-news/ai-may-have-solved-a-longstanding-math-problem-with-a-million-dollar-prize-it-ignited-a-controversy-over-who-gets-credit-180989472/)).

Neither record claims to have checked the proof. The [official announcement](https://openai.com/index/navier-stokes-solution/) was re-opened for the 2026-10-04 survey reconciliation and does state the forced finite-energy blow-up and Lean-formalization claims. This verifies what OpenAI announced, not the proof, its adequacy to the official problem or an award decision; those would require separate review of the statement and proof artifacts.

Finite-time blow-up of a smooth solution means two things: the solution exists on $[0, T^*)$ for some $T^* < \infty$, and
$$\limsup_{t \to T^{*-}} \|u(\cdot, t)\|_{L^\infty} = \infty .$$

The original version stated the theorem as: for smooth, divergence-free $u_0$ there exists a smooth force $f$ such that the solution blows up. That wording has not been checked against the announcement. It also drops the decay conditions that the problem imposes.

The form the Clay problem accepts is statement (C) of C. L. Fefferman's official problem description:
- *there exist* a smooth, divergence-free $u_0$ on $\mathbb{R}^3$ and a smooth $f$ on $\mathbb{R}^3 \times [0,\infty)$;
- both satisfy stated rapid-decay bounds;
- for this pair, no smooth solution with bounded energy exists on $\mathbb{R}^3 \times [0,\infty)$.

Statement (D) is the periodic version. For the exact theorem that was proved, read the announcement and its Lean statement.

### 1.2 The "specification gaming" reading, and why it does not hold
The original text made two claims here:
- that the mathematical community, "including Terence Tao, Tristan Buckmaster, and leading PDE analysts", had exposed the proof as specification gaming;
- that Tao held a particular view about the result.

No source is given for either attribution. The first also appeared in the original §27 of the compendium; both documents were written by AGY. Elsewhere in the repository Tao is mentioned only in connection with his 2016 paper on an averaged Navier-Stokes equation (REVIEW-2.3.md:112). REVIEW-2.3.md (line 120) found the gaming claim unsupported. The attributions have been removed. What can be said instead:

1. **A forced blow-up is not a loophole.** Fefferman's statement offers four resolutions:
   - existence and smoothness with $f = 0$, on $\mathbb{R}^3$ (A) or on the torus (B);
   - breakdown with a smooth forcing term, on $\mathbb{R}^3$ (C) or on the torus (D).

   A forced result leaves the unforced question open. That follows from how the problem was posed. It is not evidence that anyone gamed it.
2. **Whether a blow-up describes a real fluid is a separate, physical question.** Near a singularity the solution varies on ever smaller scales. At such scales the continuum assumptions behind the equations eventually stop applying. That limits what a blow-up says about real fluids; it does not bear on whether the proof is correct.

   The original also gave specifics: velocities diverging "in nanoseconds", and a fluid that would "vaporize and undergo nuclear dissociation". They had no source and have been removed.

### 1.3 The lesson for Symblic: a check certifies its predicate
The original drew two conclusions from the episode:
- that "an AI model will aggressively exploit loopholes in a formal specification to pass a compiler check";
- that Symblic therefore needs "upper-level mathematical physics invariants".

The episode does not support the first (§1.2). The sound part is general, and it is already in Symblic's specification: checks establish conformance to the predicates they encode, and "a weak, mistaken or circular predicate can accept a wrong answer" (SPEC.md §5). RESEARCH-ADOPTION.md (section "Geometry, optimization and physics") draws the same engineering lesson from the announcement: pin a precise statement and check a witness independently.

**A concrete case.** It was evaluated on 2026-10-04 on the Symblic 2.4 kernel (id `0b2cca3828a1965a`), in memory, with no model calls.
- The passage is "Two lamps at 40.00 each and one shade at 15.50. Total due: 95.50."
- The answer is a record with three parts: line items, a total, and the quoted span that states the total.

Three things happen:
- The check `sum([i.amount for i in inv.items]) = inv.total` is a balance (conservation-type) check. On its own it accepts a degenerate answer: one blank item and a total of 0. `check` warns about this (`SYM_VACUOUS`).
- Adding a grounding check, `quotes(passage, inv.total_quote) and inv.total in numbers(inv.total_quote)`, rejects that answer.
- Both checks still accept `{items: [{item: "shade", amount: 15.5}], total: 15.5, total_quote: "one shade at 15.50"}`. That answer is consistent, grounded and wrong.

Physics vocabulary does not close that gap. More specific, independently written checks narrow it. This is what Symblic has, with the limit of each:
- **`SYM_VACUOUS`** (2.3). `check` and runs warn when an ask's checks accept the empty answer (SPEC.md §5). It is a warning and never a refusal.
- **Retry feedback that does not leak the target** (2.3). When a check without a `because` fails, the automatic feedback shows the model what the kernel computed from its answer alone. It never shows a value computed from other bindings, because that "would hand the model the expected value" (SPEC.md §5). An author's `because` text is shown as written.
- **Lexical grounding** (2.3): `numbers`, `quotes` and `text.quoted_number` (SPEC.md §7, §11). They establish that a number is written in a span copied from the source. They do not establish what the number measures.
- **Spec-sheet unit tests, and the separate whole-file test they need** (2.4). Each unit is checked against the sheet's examples. That says nothing about inputs no example covers, so the assembled file needs an independent test that is not part of Symblic (SPEC-SHEETS.md:178-187).
  - For Tetris, built by small local models (qwen3:4b-instruct wrote every accepted unit), that test is a separately written harness that compares every game state with an exact reference.
  - The page passes 39 of 39 required checks, in the first build and in a from-scratch validation build (SPEC-SHEETS.md:157-176).
- **Separate reporting.** Predicate conformance, independently judged correctness, coverage and faithfulness are to be reported separately (SPEC.md §12).

A program may model a physical system. Then its conservation or dissipation law can be one of these checks, written over the program's own values (§3.3, §7).

---

## 2. Sobolev spaces and the mathematics of regularity

### 2.1 The Navier-Stokes Cauchy problem
The incompressible Navier-Stokes equations on $\mathbb{R}^3 \times [0, T]$:
$$\partial_t u + (u \cdot \nabla)u = -\frac{1}{\rho}\nabla p + \nu \Delta u + f, \qquad \nabla \cdot u = 0$$
The symbols are:
- $u(x, t)$, the velocity field;
- $p(x, t)$, the pressure;
- $\rho$, the constant density;
- $\nu > 0$, the kinematic viscosity.

For smooth solutions that decay at infinity, the energy balance is:
$$\frac{1}{2} \frac{d}{dt} \|u\|_{L^2}^2 + \nu \|\nabla u\|_{L^2}^2 = \int_{\mathbb{R}^3} f \cdot u \, dx$$
With $f = 0$ the kinetic energy can only decrease, because viscosity dissipates it at the rate $\nu \|\nabla u\|_{L^2}^2$. Energy is therefore not conserved in viscous flow. This matters for the "energy conservation" invariant proposed in §7.

### 2.2 The Beale-Kato-Majda (BKM) criterion
In 1984 J. Thomas Beale, Tosio Kato and Andrew Majda proved a continuation criterion for smooth solutions of the 3-D Euler equations (inviscid flow). The same criterion holds for the 3-D Navier-Stokes equations.

Let $\omega = \nabla \times u$ be the vorticity. Let $T^*$ be the end of the largest interval on which a smooth solution exists. If $T^* < \infty$, then
$$\int_0^{T^*} \|\omega(\cdot, t)\|_{L^\infty} \, dt = \infty .$$
Equivalently, if this integral stays finite up to a time $T$, the solution continues smoothly past $T$.

In three dimensions vorticity can grow through vortex stretching, the term $(\omega \cdot \nabla) u$ in the vorticity equation. That is why the criterion is often read as a statement about stretching. The theorem itself is about the integral.

The original called this "the definitive blow-up criterion" and, elsewhere, a "BKM enstrophy bound". Two corrections:
- BKM is a criterion. It says when blow-up can happen; it is not a bound that prevents it (REVIEW-2.3.md:113).
- Its quantity is the maximum of $|\omega|$. Enstrophy is a different quantity, $\int |\omega|^2 \, dx$.

### 2.3 "Cognitive blow-up": an analogy, and what Symblic actually bounds
The original made two claims about multi-turn reasoning, recursive routines and agent swarms:
- that "an ungrounded inference amplifies certainty exponentially across iterations";
- that this "is the informational equivalent of finite-time vortex stretching".

It is an analogy, not an equivalence. The original also gives no measurement for "frequently" or "exponentially".

```
Analogy only. The second row has no velocity field, no curl and no norm.
Physical fluid:  vorticity ω = ∇ × u   ==> vortex stretching (ω · ∇)u   ==> possible blow-up
Model runs:      an unchecked claim    ==> reused by later steps        ==> compounding errors
```
The original labelled the stretching term $(u \cdot \nabla)\omega$. That is the transport term; stretching is $(\omega \cdot \nabla) u$.

**Limits of the analogy.** BKM describes when a smooth solution of a specific PDE stops being smooth. It bounds nothing, and nothing in it applies to text: no BKM quantity can be computed from a run (REVIEW-2.3.md:232, 236).

What the analogy points at is a run that keeps calling models or keeps iterating. Symblic handles that with enforced resource limits, some of them defaults a run can change:

| limit | value | where |
|---|---|---|
| kernel steps per run | 200 000 by default; the run fails when the budget is exhausted | `symblic.MAX_STEPS`, `symblic.Budget` |
| nesting of blocks and expressions | 60 | `symblic.MAX_DEPTH` |
| asks per run; fresh model calls (shared by votes, repairs and escalation) | 400 and 2 000 by default | `symblic.kernel.run.DEFAULT_MAX_ASKS`, `DEFAULT_MAX_CALLS`; SPEC.md §7 |
| retries per check | default 2, at most 5 | `symblic.kernel.run.Run._retries` |
| samples per vote; `route=search` samples and rounds | at most 25 (`permute=K` repeats the vote K ≤ 6 times); 1-25 and 1-20 | `symblic.kernel.run.Run._ask_one`; SPEC.md §4 |
| one local-model call | 1 hour | `symblic.providers.applicators.LOCAL_CALL_TIMEOUT` |

These resource limits bound how much a run can do, not whether its answer is correct. The historical review's "nothing prevents hallucination" means there is no universal prevention guarantee. Particular checks do reject particular invalid candidates: a sound bounded proof checker can refuse an invalid derivation even if a model confidently proposes it. What limits how far an error travels is narrower:
- by default, an ask sees only the names it is given (§4);
- pure checks are evaluated by the kernel. A legacy check that calls a model-backed routine is an empirical judgment; the verified profile enforces pure acceptance checks. Neither form establishes that the chosen predicate faithfully expresses the user's intention;
- agreement is never treated as correctness (SPEC.md §5).

**The Sobolev norm.** For a function $x$ on $\mathbb{R}^n$,
$$\|x\|_{H^s}^2 = \int (1 + |\xi|^2)^s |\hat{x}(\xi)|^2 d\xi .$$
The original quoted the range $s > 5/2$, which is where the classical local theory of the 3-D Euler equations works. Symblic has no Sobolev norm over execution traces:
- no Fourier transform of a trace is defined;
- no Sobolev, enstrophy or BKM code exists (a search of `symblic*.py`, `symblic/lang/library/` and `host executor*.py` finds none).

**The proposed `NonBlowup` contract: not built, rejected.**

The original said that "the compiler enforces a BKM Dissipation Contract", and it showed this block:

`contract NonBlowup(trace: ExecutionTrace) { invariant bounded_enstrophy: integral(norm(curl(trace.epistemic_flow), inf), 0, T) < Infinity }`

Nothing enforces it:
- `contract` and `invariant` are not Symblic statements.
- `integral`, `norm` and `curl` are not kernel builtins.

The block was given to `symblic.check` on 2026-10-04 (2.4). It is accepted, but only as:
- three free-text prose asks: the `contract … {` line, the `invariant …:` line and the closing `}`;
- a `show` that reads four names nothing binds.

If it were run, it would send its `contract … {` and `invariant …:` lines to a model as instructions, and then fail at the next line with "unknown function integral". It enforces nothing. REVIEW-2.3.md:270 records the checker behavior behind this: a line the checker does not recognize is read as a prose ask. That is the 2.4 behavior. In 2.5 the default `legacy` profile still reads such a line as a model ask and flags it (`SYM_IMPLICIT_ASK`); the `explicit` and `verified` profiles reject it before any model call (SPEC.md, "Current 2.5 contracts").

Two further problems:
- "Cognitive enstrophy" in the block's comment has no definition.
- The integral is the BKM quantity, not enstrophy.

Outcome: rejected. "The proposal has no computable quantity. The useful part, bounding runaway iteration and model calls, already exists as step, depth and call budgets" (REVIEW-2.3.md:236).

---

## 3. Symplectic geometry and Noether's theorem

### 3.1 The symplectic 2-form and Liouville's theorem
In Hamiltonian mechanics (V. I. Arnold, *Mathematical Methods of Classical Mechanics*), phase space is a symplectic manifold $(M, \omega)$. The 2-form $\omega$ is closed ($d\omega = 0$) and non-degenerate. In canonical (Darboux) coordinates it reads
$$\omega = \sum_{i=1}^n dq_i \wedge dp_i .$$

The flow of a Hamiltonian vector field $X_H$ preserves $\omega$:
$$\mathcal{L}_{X_H} \omega = d(\iota_{X_H}\omega) + \iota_{X_H} d\omega = 0 .$$
This holds because $\iota_{X_H}\omega = \pm dH$ (the sign depends on convention) and $d\omega = 0$.

Liouville's theorem, the preservation of phase-space volume, follows, since the volume form $\omega^n / n!$ is preserved too. The original attributed $\mathcal{L}_{X_H}\omega = 0$ itself to Liouville. That equation is the stronger statement that the flow is symplectic.

### 3.2 Noether's theorem (1918)
A common paraphrase, not a quotation from Noether: "every continuous symmetry of the action of a physical system has a corresponding conserved quantity."

The precise statement is Noether's first theorem (E. Noether 1918). Suppose the action $\mathcal{S} = \int \mathcal{L} \, d^4x$ of a Lagrangian field theory is invariant under a continuous one-parameter group of transformations. Then there is a current $J^\mu$ with
$$\partial_\mu J^\mu = 0$$
on every solution of the Euler-Lagrange equations. If the fields fall off fast enough at spatial infinity, $Q = \int J^0 \, d^3x$ is constant in time.

```
+------------------------------------+------------------------------------+
| Continuous Symmetry Group G        | Conserved Physical Invariant Q     |
+------------------------------------+------------------------------------+
| Time Translation (t -> t + δt)     | Energy (H = E)                     |
| Spatial Translation (x -> x + δx)  | Linear Momentum (p = mv)           |
| Spatial Rotation (SO(3))           | Angular Momentum (L = r × p)       |
| Global U(1) phase symmetry         | Electric charge (for the           |
|                                    | Schrödinger field: probability)    |
+------------------------------------+------------------------------------+
```
Each row holds only when the action has that symmetry. A viscous fluid's kinetic energy is not conserved (§2.1).

### 3.3 Conservation checks in Symblic
The original made three claims here:
- that "current Symblic invariants are static boolean assertions";
- that Symblic "implements Symplectic Integrator Contracts" for workflows such as "robotic actuation, financial balances, supply-chain flow in [the host's 3-D modeling tool]";
- that these "mathematically eliminate long-horizon drift and specification gaming".

Corrected:

- **What Symblic's checks are.** `ensure`, `assert` and `expect` are predicates that the kernel evaluates at run time. They use exact rational arithmetic (transcendental functions are fixed-precision decimals), and they can contain quantifiers, comprehensions and Datalog queries (SPEC.md §2, §7). They are not static assertions. A check can also call a routine, and the routine asks a model (§2.3).

  Some are also decided before any model call. For an ask with a finite domain, enumeration can show that the checks are contradictory or that the answer is determined (SPEC.md §5, "Determination by enumeration").
- **What does not exist.**
  - There is no symplectic, Noether or phase-space construct; a search finds none.
  - Symblic has no built-in type or operation for trajectories or forces.
  - The 3-D modeling tool the original named was another application on the original host. It has no supply-chain flow.

  Where a program handles balances or flows, a balance (conservation-type) law is written as an exact check over its values, as in §1.3 and §7.

  The nearest built adapter is `reconcile(x, C, d)`. It returns the nearest values that satisfy exact linear constraints $Cy = d$, as a reported repair that says how far the values moved (PROJECTION.md).
- **Why the proposed checks fail on their own terms.**
  - `exterior_derivative(wedge_product(state.dq, state.dp)) == 0` holds for every trajectory. $d(dq \wedge dp) = 0$ identically, because $d \circ d = 0$. A check that cannot fail checks nothing (REVIEW-2.3.md:114).

    The condition that a numerical step map $\Phi$ is symplectic is $D\Phi^\top J \, D\Phi = J$, where $J = \begin{pmatrix} 0 & I \\ -I & 0 \end{pmatrix}$.
  - `divergence(state.noether_current) == 0.0` presupposes a field theory with a continuous symmetry of its action. A workflow's states define neither, so there is no current whose divergence could be taken.
  - The original block was given to `symblic.check` (2.4). Like the block in §2.3, it is read as four prose asks and two `show`s of an unbound `state`.
  - The energy-conservation invariant proposed for a fluid in §7 is wrong for the stated system, because viscous flow dissipates energy (§2.1).
- **What symplectic integrators actually give.** Take a Hamiltonian ODE that satisfies the smoothness and step-size assumptions. The energy error of a symplectic method such as Störmer-Verlet then stays small and does not drift over very long times (Hairer, Lubich & Wanner 2003). Symplectic integrators:
  - do not conserve energy exactly;
  - say nothing about systems that are not Hamiltonian;
  - do not prevent drift in an agent workflow (RESEARCH-ADOPTION.md, "Symplectic geometry and Noether invariants"), and have no bearing on specification gaming.

Outcome: rejected. "The new checks are either vacuous (d of an exact form) or wrong for the stated system (energy in viscous flow). The sound part, exact conservation asserts, already exists" (REVIEW-2.3.md:237).

Research direction, not built: a fixed-step symplectic integrator on a supplied Hamiltonian, compared with a baseline (RESEARCH-ADOPTION.md, "Symplectic geometry and Noether invariants").

---

## 4. Wilsonian renormalization and context

The original claimed that isolated capsules necessarily cause severe context starvation. That universal claim is unsupported: Symblic offers explicit context selection (REVIEW-2.3.md:82, 146, 238). The converse also fails: letting an author choose context does not establish that all needed information was included.

A capsule is built as follows (SPEC.md §4; `symblic.capsule`):
- **The author chooses the context of each ask.** The options are:
  - `context=none`, the default: only the names in its `from` clause;
  - `all`;
  - `last N`;
  - `relevant`: the six results with the most word overlap with the instruction, chosen deterministically;
  - `facts`;
  - an explicit list.
- **Results carry weights.**
  - A weight of 0 hides a result from later contexts.
  - Historically, a weight of 5 or more listed it as binding. Current epistemic status is distinct from selection priority: weight or a `KNOWN` heading is not evidence of truth ([EVIDENCE.md](EVIDENCE.md)).
  - `forget` hides results, and `pin` raises a weight.
  - `term … means …` gives every ask that mentions the word its definition.
- **Known items are packed highest weight first into a character budget** (12 000 by default; `symblic.kernel.run.DEFAULT_BUDGET`). In 2.4 an item that does not fit is left out whole, and the capsule says how many were left out. In 2.5 the names an ask is given (its `from` names and an explicit context list) must fit whole, or the ask fails before any model call; other items that do not fit are left out and listed in the capsule's context manifest.
- **`check` flags missing context** in its predictability report (`symblic.ask_risk`). It flags an ask that mentions a bound name it is not given, and one that starts with a pronoun it has nothing to resolve against.

What is true is the ordinary consequence of isolation by default. If the author does not pass something an ask needs, the model does not see it.

The constructive requirement is dependency-complete, source-linked context, not a physics analogy. [Task cards](TASK-CARDS.md) record declared dependency closure and request identity; they cannot discover every unstated dependency. A further experiment should compare full source context, selected source spans and summaries under the same model and total budget. Check preservation of entities, quantities, units, negation, exceptions and requirement IDs on held-out tasks, including deliberately omitted dependencies. Permit retrieval or larger contexts when needed, and report both savings and added error rather than assuming compression is harmless.

### 4.1 Wilson's renormalization group (1971)
Kenneth Wilson's 1971 formulation of the renormalization group made the elimination of short-wavelength degrees of freedom systematic. It built on Kadanoff's block-spin picture (Kadanoff 1966). The renormalization group of quantum field theory goes back further, at least to Gell-Mann and Low (1954). The original said that Wilson introduced the RG.

The procedure:
1. Divide momentum space into high-wavenumber modes (between a scale $\Lambda$ and the cutoff) and low-wavenumber modes ($|k| \le \Lambda$).
2. Integrate out the high-wavenumber modes in the path integral:
   $$e^{-S_{\text{eff}}[\phi_{\text{low}}]} = \int \mathcal{D}\phi_{\text{high}} \, e^{-S[\phi_{\text{low}} + \phi_{\text{high}}]}$$
3. Rescale. The effective action $S_{\text{eff}}$ then describes long-wavelength physics without tracking the eliminated fluctuations. Repeating the step makes the couplings flow: $\frac{dg_i}{d \ln \ell} = \beta_i(g)$.

The original illustrated the idea with a summary:

```
Analogy only: a summarizing step. No scale transformation is defined on text.
Source text:    "The patient coughed, sighed, adjusted their sweater, and reported..."
                                     |
                                     v   [ summarize ]
Summary:        "Patient displays respiratory distress"
```
The example also shows the risk. "Respiratory distress" is a diagnosis that the source does not state, so the summary added a claim. A summarizer that adds or drops claims without a record is why the proposal in §4.3 was rejected.

### 4.2 Relevant, marginal and irrelevant couplings, and the analogy to text
Take a fixed point of the RG flow, and a small perturbation with RG eigenvalue $y$. When lengths are rescaled by $\ell$, the perturbation scales as $g(\ell) \propto \ell^{\,y}$:
* **Relevant ($y > 0$):** grows toward long wavelengths.
* **Marginal ($y = 0$):** unchanged at linear order; higher orders decide.
* **Irrelevant ($y < 0$):** shrinks as a power of $\ell$, which is exponential in the RG "time" $\ln \ell$.

The original mapped these classes onto language:
- relevant: core causal claims, facts, identities and invariants ("they grow in importance as the context expands");
- marginal: relational modifiers and scope conditions;
- irrelevant: stylistic flourish, filler and noise.

That mapping is an analogy, and it has two limits:
- Text has no defined scale transformation, coupling or eigenvalue, so nothing can be computed from the mapping.
- It fails where it matters. Which details survive depends on the task, and a small word can carry the fact: a "not", a unit, an exception.

### 4.3 The proposed RG context engine (not built)
The original said that Symblic "applies an RG Semantics Filter":
- it projects prose through the RG flow equation;
- it keeps only relevant and marginal operators;
- in this way it "eliminates context rot while completely preserving macroscopic causal meaning".

No such filter exists; a search finds no renormalization or coarse-graining code. Also, no compressor can shorten every text without losing information. "Completely preserving" would first need a definition of which information matters.

Outcome: rejected. "The premise about capsules is false. A hidden model summariser would also add an unchecked, lossy step that the capsule's provenance would not show" (REVIEW-2.3.md:238). What exists instead is the context policy described at the start of §4.

Research direction, not built (RESEARCH-ADOPTION.md, "Wilsonian coarse-graining and context compression"):
- hierarchical summaries linked to their sources;
- the summaries keep mandatory entities, quantities, scope and exceptions;
- they are compared with full text and with simple retrieval, on loss and on cost.

The information bottleneck (Tishby, Pereira & Bialek 1999) is a closer executable baseline than renormalization.

---

## 5. Information geometry: the Fisher-Rao metric

### 5.1 The statistical manifold $\mathcal{M}$
In information geometry (C. R. Rao 1945; S. Amari 1985), a regular parametric family $\mathcal{S} = \{ p(x \mid \theta) \}$ is a Riemannian manifold with the Fisher-Rao metric
$$g_{ij}(\theta) = \mathbb{E}_{x \sim p}\left[ \frac{\partial \ln p(x \mid \theta)}{\partial \theta_i} \frac{\partial \ln p(x \mid \theta)}{\partial \theta_j} \right],$$
wherever this Fisher matrix is positive definite.

The manifold is curved in general; for univariate normal distributions it is a hyperbolic plane. But it is not always curved: a one-parameter family is intrinsically flat.

To second order, the line element is twice the Kullback-Leibler divergence between neighboring models. (The original wrote this as an exact equality.)
$$ds^2 = \sum_{i,j} g_{ij}(\theta)\, d\theta_i\, d\theta_j = 2\, \mathcal{D}_{\text{KL}}(p_\theta \parallel p_{\theta + d\theta}) + O(|d\theta|^3)$$

```
Euclidean distance:   d(θ_1, θ_2) = ||θ_1 - θ_2||_2                       (depends on the parametrization)
Fisher-Rao distance:  s(p_1, p_2) = inf over curves of ∫ √(g_ij dθ^i dθ^j)  (does not)
```
The integral is the length of one curve. The distance is the infimum of that length over curves joining $p_1$ and $p_2$.

Symblic groups model answers by exact canonical identity or by a kernel key (§6.2). In its votes, the one distance Symblic uses on answers is the absolute difference of numbers in `vote=median`. Symblic has no parameter space over its answers, so there is no Euclidean parameter distance for the Fisher-Rao metric to replace.

### 5.2 Symblic's quadratic solver and the natural gradient
**What exists.** `symblic/adapters/variational.py` was added in Symblic 2.2; it is adapter version 1, unchanged in 2.4. It minimizes $H(x) = \frac{1}{2}x^\top A x - b^\top x$ exactly. Its input is an explicitly supplied rational, symmetric, positive-definite $A$ of dimension at most 32 (VARIATIONAL.md; `symblic.adapters.variational.MAX_DIMENSION`, `_ldlt`, `_verify`).

It works as follows:
- it uses an exact, unpivoted $LDL^\top$ factorization;
- it refuses any non-positive pivot;
- it returns a receipt that a separate verifier checks: $A = L\,\mathrm{diag}(D)\,L^\top$, a zero residual, and the exact minimum energy.

Minimizing this convex quadratic is solving $Ax = b$, with a unique minimizer when $A \succ 0$ (Boyd & Vandenberghe 2004, Example 4.5).

The original called this "classical Euclidean matrix factorization". It is not Euclidean in any restrictive sense: $A$ can be any rational SPD matrix, so $A$ already defines the inner product (REVIEW-2.3.md:239).

It is also neither of these:
- It is not connected to `solve=true`, which still enumerates finite domains of at most 20 000 values (`symblic.DOMAIN_CAP`; SPEC.md §5).
- It is not a PDE solver.

**What the natural gradient is.** Take an objective $H(\theta)$ on a statistical model. The natural-gradient step is
$$\Delta \theta = -\eta\, G^{-1}(\theta) \nabla H(\theta) \qquad \text{(Amari 1998)},$$
which is the steepest-descent direction measured by the Fisher metric $G$.
- Its continuous-time flow does not depend on how the model is parametrized.
- Finite steps are invariant only to first order in $\eta$.

**What the original claimed, and what holds.** The original claimed: "By setting matrix $A$ to the Fisher Information Matrix $G(\theta)$, Symblic's solver becomes an Exact Riemannian Natural Gradient Engine ... Optimization moves along the true geodesics of the probability manifold, solving variational constraints in the fewest possible steps."

What holds is this. Suppose an exact rational SPD $G(\theta)$ and a gradient $\nabla H(\theta)$ are supplied at one point. Then `quadratic_minimize(G, -∇H)` returns $x = -G^{-1}\nabla H$ exactly. That is one natural-gradient direction, from one linear solve.

Everything else is missing or false:
- Symblic has no differentiation, so it cannot derive $G(\theta)$ or $\nabla H(\theta)$ from a statistical model; both must be supplied. The solver also does not choose $\eta$, iterate or test convergence.
- A Fisher matrix can be singular, and the solver refuses singular matrices. It can be irrational, and the solver takes only exact rationals.
- Natural-gradient steps move along straight lines in parameter space. The natural-gradient flow is a gradient flow, not a geodesic flow.
- There is no "fewest steps" guarantee. On a quadratic objective whose Hessian is not proportional to $G$, one natural-gradient step in general does not reach the minimum for any $\eta$, while one Newton step does. The method can also stop at a local minimum or a saddle point of a non-convex objective.

Outcome: claim rejected, construction deferred. "The solver already accepts any rational SPD metric, and natural gradient is not one exact solve" (REVIEW-2.3.md:239).

Research direction, not built (RESEARCH-ADOPTION.md, "Fisher geometry and natural gradients"): on a small explicit distribution, compare ordinary and natural-gradient updates by measured calibration and held-out loss.

---

## 6. Optimal transport and Wasserstein barycenters

### 6.1 The Wasserstein metric and Kantorovich-Rubinstein duality
The Wasserstein metric is treated in Villani (2009).

The Kullback-Leibler divergence $D_{\text{KL}}(\mu \parallel \nu)$ is infinite whenever $\mu$ gives mass to a set to which $\nu$ gives none, for example when the supports do not overlap. Wasserstein distances stay finite for distributions with finite second moments, and they reflect how far apart the supports are.

The squared $L^2$-Wasserstein distance is the least mean squared displacement over couplings $\pi$ of $\mu$ and $\nu$:
$$W_2^2(\mu, \nu) = \inf_{\pi \in \Pi(\mu, \nu)} \int_{\mathcal{X} \times \mathcal{X}} \|x - y\|^2 \, d\pi(x, y)$$

For distributions on a convex, compact domain of $\mathbb{R}^d$, the Benamou-Brenier formula writes the same quantity as the least kinetic action of a flow of mass (Benamou & Brenier 2000; Santambrogio 2015, Thm 5.28):
$$W_2^2(\mu, \nu) = \inf_{\rho, v} \left\{ \int_0^1 \int \rho_t(x) \|v_t(x)\|^2 \, dx \, dt : \partial_t \rho + \nabla \cdot (\rho v) = 0,\ \rho_0 = \mu,\ \rho_1 = \nu \right\}$$

The original contents list attached Kantorovich-Rubinstein duality to $W_2$. It is the $W_1$ case:
$$W_1(\mu,\nu) = \sup_{\mathrm{Lip}(\varphi) \le 1} \int \varphi \, d(\mu - \nu)$$
(Santambrogio 2015, in the proof of Thm 5.9).

### 6.2 Multi-agent consensus: what Symblic computes and what was built
**The original premise was wrong.** It said that Symblic "currently runs crude token majority voting". Symblic's vote is `symblic.consensus` (SPEC.md §4):
- It groups whole typed answers by exact canonical fingerprint, or by a kernel key such as `key=eval(it)`.
- It weights them by applicator weight and takes the answer with the most weight.
- Ties go to applicator order and are marked contested.
- The ask is contested when the winner's share is below `agree` (default 0.5).
- It reports the agreement, the distinct answers, the normalized entropy, the model families behind the winner, and every sample.

Options add:
- field-by-field votes for records (the default, `vote=auto`, uses them once a record has three or more valid answers);
- first-to-ahead-by-k sampling;
- a family-diversity filter;
- option-order rotations (`permute`);
- `vote=median`.

**What a Wasserstein barycenter would give.** The barycenter is $\bar{\mu} = \arg\min_{\mu} \sum_k w_k W_2^2(\mu, \mu_k)$ (Agueh & Carlier 2011). Each model's answer is one point, so $\mu_k = \delta_{a_k}$.
- **Numeric answers.** $W_2^2(\mu, \delta_a) = \int \|x - a\|^2 \, d\mu$, so the barycenter is the point mass at the weighted mean. One outlying answer moves it without bound (REVIEW-2.3.md:110). Minimizing $\sum_k w_k W_1(\mu, \delta_{a_k})$ instead gives the weighted median (Santambrogio 2015, §5.5.5).
- **Categorical answers** (labels, records) with the 0-1 ground metric. Here $W_2^2(\mu, \delta_a) = 1 - \mu(\{a\})$. Let $W(x)$ be the total weight of the models that answered $x$. The objective is then $\sum_k w_k - \sum_x \mu(\{x\})\, W(x)$.
  - It is minimized by putting all the mass on the answer with the most weight.
  - So the barycenter is the weighted plurality answer, which is what Symblic's whole-answer vote returns.
  - A tie leaves several minimizers, and Symblic marks a tie contested.

  This short derivation is ours, from the definitions.
- **Text answers.** They have no ground metric that matches meaning. An embedding metric would need empirical justification, and a barycenter can still be wrong (RESEARCH-ADOPTION.md, "Wasserstein transport and barycenters").

**What was built** (2.3, reduced form).
- **`vote=median` with `within`** (`symblic.consensus_median`; SPEC.md §4), for Int and Number answers:
  - The winner is the weighted lower median, which is always a value that some applicator gave.
  - It reports the share of weight within the tolerance of the median, and the spread (the range and the weighted median absolute deviation).
  - Answers holding less than half the total weight cannot carry it outside the range of the other answers. They can still shift it within that range: with equal weights, [1, 2, 3] has median 2, and adding 100 twice makes it 3.
- **`wasserstein1(left, right)`** (TRANSPORT.md), added in the same release: the exact Wasserstein-1 distance between two finite weighted distributions on the line.

**What does not hold.** The original said that the barycenter finds "the true geometric center of mass of the agents' beliefs", "guaranteeing a smooth, optimal consensus that preserves continuous geometric truth".
- A barycenter minimizes its own objective; it does not make the answers true. "A median of wrong readings is wrong: the vote measures agreement, as every vote does" (SPEC.md §4).
- Single model answers are points, not belief distributions.
- "Q-Symblic" is a name used in AGY's quantum essays, not an implementation. Symblic computes no barycenter of distributions; for point answers, `vote=median` and the whole-answer vote return the $W_1$ and 0-1-metric barycenters derived above.

Outcome: built as `vote=median` (REVIEW-2.3.md:240).

---

## 7. The proposed physics-informed specification, and its real counterparts

**What was proposed.** The original's §7 was a block headed `module PhysicsInformedRuntime`. It contained:
- types `PhaseSpacePoint` and `SymplecticForm = ExteriorTwoForm[6]`;
- a `contract PhysicalFluidFlow` with three invariants:
  - a numeric cap of $10^6$ on $\int \|\mathrm{curl}\, u\|_\infty \, dt$, labelled a "Beale-Kato-Majda Sobolev enstrophy dissipation bound";
  - an energy variance of at most $10^{-9}$;
  - zero phase-space divergence, labelled "Liouville";
- a routine `CompressHistory` that called `wilson_coarse_grain`;
- a `kernel SolveEquilibrium` that called `riemannian_natural_gradient` with a tolerance of $10^{-12}$.

**What happened to it.**
- **It is not Symblic.** `symblic.check` (2.4) rejects it with one error at its line 30, `routine CompressHistory(raw_log: Text) -> Text {`: SYM_SYNTAX, "unexpected text after the end of the statement (found '{')".
  - `contract`, `invariant` and `kernel` blocks, `var` statements and brace-delimited blocks do not exist in the language (REVIEW-2.3.md:12, 232).
  - None of `curl`, `divergence`, `integral`, `norm`, `variance`, `wilson_coarse_grain` or `riemannian_natural_gradient` is a kernel builtin in 2.4. `variance` is in the standard library, though (`stats.variance`, symblic/lang/library/stats.sym), so a variance bound over a program's own list of numbers can be written. What is wrong with the energy invariant is what it requires: constant energy in a viscous flow (next item).
- **Each invariant is wrong for its stated purpose.**
  - A finite numeric cap on a vorticity integral is not the BKM criterion, and BKM's quantity is not enstrophy (§2.2).
  - A viscous fluid's energy decreases, so "energy conservation" would reject correct flows (§2.1).
  - Zero divergence of the phase-space velocity holds identically for every Hamiltonian vector field, so it can never fail for them. For dissipative flows it fails, correctly.
  - An exact solver has no tolerance to set.
- **Outcome: rejected.** "It adds no mechanism beyond functions plus ensure/assert, which already exist" (REVIEW-2.3.md:241). The BKM, symplectic/Noether and RG proposals were rejected with it (lines 236-238).

**The real counterparts, as one Symblic 2.4 program.** `symblic.check` accepts it with no warnings (2026-10-04, kernel `0b2cca3828a1965a`). Running it asks models for `inv` and `boiling`.

```symblic
program Real counterparts of the physics proposals.
note Symblic 2.4. Nothing here models physics or meaning; every check is an exact predicate the kernel evaluates.
define Line as Record {item: Text, amount: Number}.
define Invoice as Record {items: List of Line length 1..50, total: Number, total_quote: Text}.
given passage: Text = "Two lamps at 40.00 each and one shade at 15.50. Total due: 95.50."
ask inv: Invoice "Extract every line item with its amount, the stated total, and as total_quote the words of the passage that state the total, copied exactly." from passage
ensure sum([i.amount for i in inv.items]) = inv.total else retry because "the line amounts must add up to the stated total".
ensure quotes(passage, inv.total_quote) and inv.total in numbers(inv.total_quote) else retry because "the total must be a number written in a span copied from the passage".
ask boiling: Number "At sea level, at what temperature in degrees Celsius does pure water boil?" with votes=5, vote=median, within=1
let A = [[4, 1], [1, 3]].
let b = [1, 2].
let equilibrium = quadratic_minimize(A, b).
assert quadratic_verify(A, b, equilibrium).
show inv.total as "stated total".
show boiling as "median reading".
show equilibrium.x as "exact minimizer".
```
- **The two `ensure` lines** are a balance (conservation-type) check, that the items add up to the total, and a source-grounding check. Both are exact predicates that the kernel evaluates, and a failure re-asks with the reason.
  - Without the grounding check, `check` warns `SYM_VACUOUS`: the balance alone accepts an invoice with one blank item and a total of 0.
  - Even with both checks, a consistent, grounded wrong answer can pass (§1.3).
- **`vote=median, within=1`** is the built, reduced form of the Wasserstein proposal (§6.2).
- **`quadratic_minimize` and `quadratic_verify`** are the exact SPD solver and its independent verifier (§5.2). Here $x = (1/11, 7/11)$ and the minimum energy is $-15/22$ (VARIATIONAL.md).
- **The run limits** of §2.3 (steps, depth, asks, calls, retries and votes) apply to every run without being written in the program.

---

## 8. Summary

| Mathematical physics domain | Established result | What it gives Symblic | Outcome (REVIEW-2.3) |
| :--- | :--- | :--- | :--- |
| **Navier-Stokes & Sobolev analysis** | Beale-Kato-Majda (1984): a smooth solution can stop being smooth only if $\int \Vert\omega\Vert_\infty dt$ diverges. It is a criterion, not a bound, and it concerns vorticity, not enstrophy. | Nothing computable on prompts. Runaway runs are bounded by step, depth, ask, call and retry limits that already existed. | Rejected |
| **Symplectic geometry (Arnold)** | Hamiltonian flows preserve $\omega = \sum dq \wedge dp$, and hence phase-space volume (Liouville). | The proposed checks were vacuous. Exact conservation checks already existed. A symplectic-integrator adapter is a research direction. | Rejected |
| **Noether's theorem (1918)** | A continuous symmetry of an action gives a conserved current on solutions. | A workflow defines no symmetry and no current. The conservation laws a program does have are written as exact checks. | Rejected (with the above) |
| **Wilsonian renormalization (1971)** | Integrating out short-wavelength modes gives an effective action for long wavelengths. | The premise was false: capsules pack context by weight and report what they leave out. A hidden summarizer would be an unchecked, lossy step. | Rejected; source-linked summaries are research |
| **Information geometry (Rao, Amari)** | The Fisher-Rao metric; the natural gradient $-\eta G^{-1}\nabla H$. | The exact SPD solver can compute one natural-gradient direction from a supplied $G$ and $\nabla H$. It is not an optimizer, and it follows no geodesics. | Claim rejected; construction deferred |
| **Optimal transport (Villani)** | Wasserstein distances; barycenters (Agueh-Carlier). | `vote=median`, the weighted median of numeric answers with its spread. Added separately: `wasserstein1`, the exact $W_1$ distance on the line. | Built in a reduced form |

---

## Sources

Book pages and theorem numbers were checked in a copy of the book where noted. Journal volumes and page ranges were not checked against stored copies. The only DOI given is the one recorded in RESEARCH-ADOPTION.md.

- J. T. Beale, T. Kato, A. Majda (1984). "Remarks on the breakdown of smooth solutions for the 3-D Euler equations." *Communications in Mathematical Physics* 94, 61-66.
- C. L. Fefferman. "Existence and smoothness of the Navier-Stokes equation." The Clay Mathematics Institute's official problem description, reprinted in *The Millennium Prize Problems* (Clay Mathematics Institute and American Mathematical Society, 2006).
- OpenAI announcement of 8 September 2026: <https://openai.com/index/navier-stokes-solution/>. The Smithsonian report is linked in §1.1. Both links are as recorded in REVIEW-2.3.md:118-119; the OpenAI link is also in RESEARCH-ADOPTION.md (section "Geometry, optimization and physics"). Neither was re-fetched for this correction.
- V. I. Arnold. *Mathematical Methods of Classical Mechanics*. Graduate Texts in Mathematics 60, Springer.
- E. Noether (1918). "Invariante Variationsprobleme." *Nachrichten von der Gesellschaft der Wissenschaften zu Göttingen, Mathematisch-Physikalische Klasse*.
- E. Hairer, C. Lubich, G. Wanner (2003). "Geometric numerical integration illustrated by the Störmer-Verlet method." *Acta Numerica* 12. A preprint is linked in RESEARCH-ADOPTION.md ("Symplectic geometry and Noether invariants").
- K. G. Wilson (1971). "Renormalization group and critical phenomena. I. Renormalization group and the Kadanoff scaling picture." *Physical Review B* 4, 3174. "II. Phase-space cell analysis of critical behavior." *Physical Review B* 4, 3184.
- K. G. Wilson, J. Kogut (1974). "The renormalization group and the ε expansion." *Physics Reports* 12, 75-199.
- L. P. Kadanoff (1966). "Scaling laws for Ising models near $T_c$." *Physics Physique Fizika* 2, 263-272.
- M. Gell-Mann, F. E. Low (1954). "Quantum electrodynamics at small distances." *Physical Review* 95, 1300-1312.
- N. Tishby, F. C. Pereira, W. Bialek (1999). "The information bottleneck method." arXiv:physics/0004057, as linked in RESEARCH-ADOPTION.md ("Wilsonian coarse-graining and context compression").
- C. R. Rao (1945). "Information and the accuracy attainable in the estimation of statistical parameters." *Bulletin of the Calcutta Mathematical Society* 37.
- S. Amari (1985). *Differential-Geometrical Methods in Statistics*. Lecture Notes in Statistics 28, Springer.
- S. Amari (1998). "Natural gradient works efficiently in learning." *Neural Computation* 10(2), 251-276. doi:10.1162/089976698300017746, as recorded in RESEARCH-ADOPTION.md ("Fisher geometry and natural gradients").
- S. Boyd, L. Vandenberghe (2004). *Convex Optimization*. Cambridge University Press, Example 4.5 ("Unconstrained quadratic optimization"), p. 140. Checked in a copy of the book.
- C. Villani (2009). *Optimal Transport: Old and New*. Grundlehren der mathematischen Wissenschaften 338, Springer.
- J.-D. Benamou, Y. Brenier (2000). "A computational fluid mechanics solution to the Monge-Kantorovich mass transfer problem." *Numerische Mathematik* 84.
- M. Agueh, G. Carlier (2011). "Barycenters in the Wasserstein space." *SIAM Journal on Mathematical Analysis* 43.
- F. Santambrogio (2015). *Optimal Transport for Applied Mathematicians*. Progress in Nonlinear Differential Equations and Their Applications 87, Birkhäuser. Checked in a copy of the book:
  - the $W_1$ duality formula, in the proof of Thm 5.9 (p. 184);
  - the Benamou-Brenier formula, Thm 5.28 (p. 204), stated for a convex, compact domain;
  - $W_2$ barycenters and the $p = 1$ median remark, §5.5.5 (pp. 215-216).

---

## Where this document is recorded

1. **This file.** It is `docs/reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md`. The original said that the treatise had been "formally committed". As of 2026-10-04, `docs/reference/` was untracked in git (`git status` showed `?? docs/reference/`), so nothing had been committed.
2. **AGY's working copy.** It is `~/.gemini/antigravity-cli/brain/cb867bcf-a440-490a-9c7f-a37ea83e1eb5/symblic_physics_and_advanced_mathematics.md`, outside the repository. It is a shorter, condensed version (4 833 bytes, against the 20 959-byte original of this file), saved about 7 seconds after the original on 2026-10-03 (file times 16:10:24.1 and 16:10:16.9). It carries the same uncorrected header and claims, including the "Codex Integration Team" author line, the specification-gaming account attributed to Tao, and the "Natural Gradient Engine".
3. **The compendium.** `SYMBLIC-BREAKTHROUGH-COMPENDIUM.md` §27 summarized the original version of this document. The compendium was corrected on 2026-10-04 as well, and its rewritten §27 carries the main corrections made here.
4. **Verification status.** The original said: "All existing tests continue to pass (`check_ok: 16`), proving that our documentation additions maintain total repository integrity." No such receipt exists (REVIEW-2.3.md:89), and passing tests say nothing about a document's claims.

   What was checked for this correction, on 2026-10-04, with the Symblic 2.4 kernel (id `0b2cca3828a1965a`) and no model calls:
   - `symblic.check` on the original code blocks (the results are given in §2.3, §3.3 and §7);
   - `symblic.check` on the program in §7 (accepted, no warnings);
   - an in-memory kernel run of the counterexample in §1.3 (zero calls).
