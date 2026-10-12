# What the review documents proposed, and what Symblic 2.3 does with it

2026-10-03. Nine documents in this folder were written by an assistant that was asked to criticise Symblic
and to connect it with other fields:

`EPISTEMIC-IMPROVEMENTS.md`, `CRITIQUE-AND-LIMITATIONS.md`, `INTENSE-CRITIQUE-AND-LIMITATIONS.md`,
`INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md`, `HPC-FOUNDATIONS.md`,
`QUANTUM-FOUNDATIONS-OF-SYMBLIC.md`, `QUANTUM-DETERMINISM-ANALYSIS.md`,
`PHYSICS-AND-ADVANCED-MATHEMATICS.md`, `GRAND-UNIFICATION-AND-STRING-THEORY.md`.

Their headers name other authors and call them canonical, a specification or a proof. They are proposals.
Their example programs are not Symblic (`contract`, `invariant`, `apply`, `struct`, `kernel` blocks and braces
do not exist in the language), and nothing in them had been implemented.

Each document was read against the code by a separate reader with four questions: with the analogy removed,
what mechanism is proposed; is each claim true; does Symblic already do it; what is the smallest form that
can be tested. The readers returned 63 proposals and 120 factual errors. This file records the outcome.
[SPEC.md](SPEC.md) is the specification of what was built.

## Outcome

| outcome | proposals |
|---|---|
| built in 2.3, each in a reduced form | 12 |
| already present | 2 |
| deferred, with the reason | 12 |
| claim rejected; the construction deferred as a research direction | 5 |
| rejected: no computable definition, or false as stated | 32 |

Rejected is a verdict on a claim or a promised guarantee, not on the mathematics behind it. The operator asked for
the constructive proposals to be pursued on their own merits (2026-10-03), so a construction that can be
computed and tested is kept as a research direction even where the document's guarantee is rejected. Where a
rejected claim named a real finite computation, 2.3 built that computation exactly and says what it does not
establish: the ground states of a small Ising model, Aumann's partition model of knowledge, projectors and the
probabilities of ordered questions, and the nearest values that satisfy linear constraints. The per-document
tables below say so beside each such row. The adoption ledger [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md)
lists further constructions as experiments.

The pattern is the same in every document. A real weakness is named (a check that an empty answer passes, an
answer that depends on the order of the options, a count of "families" that counts a distilled model twice).
A theorem from another field is then attached to it, and the theorem is what gets rejected: its hypotheses do
not hold for a model that returns text, or the quantity it needs cannot be computed from one. What is left is
the part with a definite meaning and a test, and it was built in a reduced form. Five further constructions
are computable and deferred with a next step (tensor semantics, verified circuit rewrites, affine one-use
handles, natural-gradient comparisons, explicit schema mappings). None of them carries the documents' universal
guarantees: no construction here prevents hallucination or injection, or makes model answers deterministic.

## What 2.3 adds

| addition | what it does | what it does not establish |
|---|---|---|
| retry feedback with kernel values | When an `ensure ... else retry` fails without a `because`, the next attempt is told what the kernel computed for the parts of the check that depend on the answer alone (`sum(...) = 90; inv.total = 100`; `fails for i = {...} (item 3 of 4)`). | A part that reads anything else is never evaluated for display: showing it would hand the model the expected answer. |
| retry-exhaustion report | When retries run out, `report.diagnoses` and the error say whether every attempt gave the same answer or a different one each time. | It is a hint about where to look (the check, or the wording). It decides nothing. |
| `SYM_VACUOUS` warning | `check` and the run warn when an ask's anchored checks accept the empty answer (an empty list, `""`, 0, a record of those). | A legitimately empty answer also triggers it; it never refuses. |
| `SYM_SAME_KEY` warning | Two `act` statements on one path with the same capability and the same literal key: the second would be served the first one's outcome. | Statements in different branches of one `if` are not compared. |
| `permute=K` | A vote is taken under K rotations of the option order; the ask is stable only when every rotation has a valid, uncontested winner and they are all the same (R9 of [RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md)). | Rotations by the same models are not independent readers. |
| `vote=median`, `within=T` | Numeric answers: the weighted lower median, the share of weight within T of it, and the spread. | A median of wrong readings is wrong. |
| families by lineage | A distilled model counts with its base weights and its teacher; a front-end counts by the model it names; an unknown lineage adds no family. | Different lineages are not independent errors; evidence still says `independence: not_established`. |
| `numbers(text)`, `quotes(passage, quote)` | Kernel builtins: the plain decimal numerals written in a text; whether a span occurs in a passage with the same letters and case after NFC and white-space normalisation, as whole words and whole numerals. | Lexical occurrence only. |
| `text.quoted_number`, `text.quoted_number_in`, `records.conflicts`, `records.agree` | Library: a reported number must be written in a span copied from the passage; two records agree on the fields they share. | Not the entity, the unit, the relation or the truth of the statement. Agreement on shared fields is not correctness. |
| checks in the host executor run view | A run lists the checks it evaluated, or says that nothing tested the answers. | A passed check is conformance to that predicate. |
| `ising_minimize`, `ising_energy` ([DISCRETE.md](DISCRETE.md)) | Every state of at most 16 spins: the exact minimum energy, how many states attain it, the first ground states. | The minimum is exact for the supplied numbers; that they encode a real problem is the author's claim. No annealing. |
| `knows_event`, `common_partition`, `common_knowledge`, `posterior_given`, `agreement_process` ([KNOWLEDGE.md](KNOWLEDGE.md)) | Aumann's partition model on at most 64 states: knowledge, common knowledge (the meet), exact posteriors, and the Geanakoplos-Polemarchakis announcements. | It computes on partitions a program declares. A transcript is not a partition; it says nothing about what a person or a model knows. |
| `is_projector`, `commutator`, `commutes`, `ordered_probability` ([OPERATORS.md](OPERATORS.md)); library `order` | Rational projectors up to 8 x 8 and what the projector model predicts for yes/no questions asked in order, including the QQ equality; `order.qq_gap` computes the matching quantity from counted answers. | A prediction of a model the author supplies. A language model's state is not a quantum state; unequal conditional probabilities are not an order effect. |
| `reconcile` ([PROJECTION.md](PROJECTION.md)) | The nearest values (optionally weighted) that satisfy exact linear constraints, and how far they moved. | The result is a repair, not what was observed; satisfying the constraints does not make the values right. |
| `wasserstein1` ([TRANSPORT.md](TRANSPORT.md)) | The exact Wasserstein-1 distance between two finite weighted distributions on the line. | A distance between the numbers supplied; no semantic similarity. |
| `stats.binomial_at_least`, `binomial_at_most` | Exact binomial tails. | 18 passes out of 18 do not exclude a true rate of 85% at the 5% level. |

`Any` now has the JSON Schema `{}` (it advertised `string` while the kernel accepted every JSON shape). The new
builtin names are reserved, so a 2.2 program that binds one of them (`reconcile`, `commutes`, `numbers`, …)
must rename it; none in this repository did. There is one new example, [13-two-accounts.sym](../../tests/kernel/fixtures/13-two-accounts.sym).

## Recurring errors about Symblic

- "One model, one prompt, one invariant": the language has votes, efforts, families, groups, any number of
  checks per ask, checked escalation and `tighten` (SPEC §4, §5, §12).
- "A failed check crashes, or blames the model": retries are transactional with feedback; determination
  reports a contradictory or underdetermined contract before any model is asked.
- "No provenance": every binding carries its mechanism and evidence; observations carry capability, hashes and
  time; flow labels are checked statically ([EVIDENCE.md](EVIDENCE.md), [EFFECTS.md](EFFECTS.md)).
- "Votes are treated as independent": every evidence record says `independence: not_established`.
- "Capsules wipe the context": the author chooses the context policy; the capsule reports what did not fit.
- "Replay breaks when GPUs differ": a replay serves recorded replies and asks no model.
- "Symblic claims proofs, soundness, total determinism": SPEC §5 says a check establishes conformance to the
  encoded predicate and that a weak predicate can accept a wrong answer.
- "Outside text can make an action fire with the attacker's arguments": untrusted text cannot become an
  argument; it can steer a choice among actions the program wrote, which is labelled, reported, and held for
  the operator in guarded mode. In the host executor's full mode the operator has approved such actions in advance.
- A module `symblic_agent.py`, a test-suite invoice counterexample and a `check_ok: 16` receipt are cited; none
  exists.

## Recurring errors about the mathematics and the physics

- The entropy of one text is undefined without a probability model, so an "entropy floor" has nothing to
  compare. A correct extraction carries far less information than its source.
- Aumann's agreement theorem needs common priors and common knowledge of posteriors. Common knowledge cannot be
  reached over unreliable messages (Halpern and Moses 1990). Mutual knowledge means everyone knows the fact.
- Crawford and Sobel (1982) show that cheap talk can be informative when interests are close; Spence (1973)
  needs a cost that differs by type. A prompted model has no utility function, so "truth-telling as a dominant
  strategy" has no subject.
- FLP (1985) is about asynchronous processes reaching agreement under crash faults; one coordinator counting
  replies is not that. Rice's theorem is about properties of all runs of a program, not one value of one run.
- ZX-calculus results are completeness theorems, not confluence. Ising ground states need not be unique (with
  no field, flipping every spin keeps the energy) and finding one is NP-hard in general (Barahona 1982);
  annealing is a heuristic. `ising_minimize` therefore enumerates, caps the size and reports the count. No-cloning does not imply linear logic.
  Non-commuting projector updates are order-dependent by definition. A softmax output is a classical
  distribution, not a density matrix.
- The exact quadratic solver minimises a convex quadratic over the rationals with one linear solve. It is not
  an Ising problem, a Rayleigh-Ritz eigenproblem or a natural-gradient method.
- The Wasserstein-2 barycenter of point answers is their weighted mean, which one outlier moves without bound.
  The Wasserstein-1 barycenter is the weighted median; that is the form built (`vote=median`).
- Tao (2016) proves finite-time blowup for an averaged Navier-Stokes equation; it does not prove that
  Navier-Stokes simulates a Turing machine. Beale, Kato and Majda (1984) give a blowup criterion, not a bound
  that prevents blowup. Energy is not conserved in viscous flow. `d(dq ∧ dp) = 0` holds for every trajectory.
- A forced blowup is not a loophole in the Clay problem: Fefferman's statement lists breakdown with a forcing
  term (statements C and D) as a resolution. The announcement the document builds on is real: OpenAI reported
  on 8 September 2026 a Lean-formalised proof of finite-time blowup under a smooth force
  ([announcement](https://openai.com/index/navier-stokes-solution/)); when it was reported it was unrefereed
  and its credit disputed ([Smithsonian](https://www.smithsonianmag.com/smart-news/ai-may-have-solved-a-longstanding-math-problem-with-a-million-dollar-prize-it-ignited-a-controversy-over-who-gets-credit-180989472/)).
  The document's further claim, that a model gamed the evaluation, is not supported. Nothing in 2.3 depends on it.
- AdS/CFT is a conjecture; the Ryu-Takayanagi formula applies to holographic theories; mirror symmetry is not
  proved for every Calabi-Yau; whether local answers glue is decided on overlaps (degree 0), not by H¹;
  univalence turns a supplied equivalence into an identity and constructs none.

## Per document

Each summary below is the reader's assessment of the document's claims against the code. "Rejected" rejects a claim or a
guarantee; "Claim rejected; construction deferred" keeps a computable construction as a research direction,
with its next step in [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md).

### EPISTEMIC-IMPROVEMENTS.md

Without the philosophy, the document proposes six things. Four already exist in some form: provenance labels on values (meta.evidence.mechanism, observation evidence, untrusted/steered/personal flow labels), multi-check and multi-engine agreement (several ensures, votes, families, observe), pre-flight probing of meaning (tighten, ambiguous=true readings, term definitions, test certificates), and per-agent visibility with approval gates (capsules with context=none by default, needs_owner). The one critique that holds is that a predicate can be vacuously satisfied. From that, two small additions survive: an exact case-sensitive quote builtin for grounding, and automatic kernel-computed counterexample values in retry feedback. The entropy floor, "semantic offset vector", dominant-strategy, concordance and Aumann claims have no defined mechanism, or they misapply the theorems they cite.

| proposal | outcome | why |
|---|---|---|
| Epistemic modality types (Observation/Belief/Knowledge/CommonKnowledge) with a static gate | Deferred | Most of the provenance already exists. The remaining static rule is small, but whether it is worth having depends on how often unchecked model output reaches acts today. |
| Multi-frame concordance contracts (multi-frame engine) | Rejected | Once the analogy is removed, the mechanism is a conjunction of checks, some of which read external data, and Symblic already expresses that with ensure/assert plus observe. The concordance score adds nothing, and the perturbation frame is undefined. |
| Davidsonian triangulation pass (pre-flight probes) | Rejected | The sound part, probing a panel before a run and rewriting ambiguous asks, already exists as tighten, ambiguous readings and test certificates. Measured gains still need a held-out panel (SPEC.md). |
| Principle-of-charity diagnostics on check failure | Built in 2.3 | Retry feedback carries the kernel's values for the parts of the failed check that depend on the answer alone. No model-written diagnosis. |
| Non-degeneracy constraints: entropy floor and exact span witnesses | Built in 2.3 | `numbers`, `quotes`, `text.quoted_number`, `text.quoted_number_in`: a reported number must be written in a span copied whole from the passage. This is lexical occurrence, not the entity, the unit or the truth. The entropy floor is rejected. |
| Aumann knowledge-partition state machine for multi-agent systems | Rejected | The workable parts (what each ask sees, and operator approval before consequential acts) already exist. The remainder is a relabelling of sets of facts with mathematical guarantees it does not have. The finite partition model the theorem is about is now computable (`common_knowledge`, `agreement_process`; KNOWLEDGE.md). |

### CRITIQUE-AND-LIMITATIONS.md

Once the analogies are set aside (Goedel, Grice, Goodhart, FLP, Quine-Duhem), the document has one sound engineering point. Weak ensure predicates can accept degenerate answers, such as an empty item list that satisfies a sum and an all-quantifier. Symblic can already express the fix (List length 1..N, contains() grounding), and SPEC section 5 already admits the risk, but the checker never warns about such predicates. Most of the other diagnoses misdescribe the code. Replay serves recorded replies, so GPU drift does not affect it. Votes are explicitly not treated as independent. Context is chosen by the author through from/context. Non-stratified Datalog is rejected. Ensure failures are not blamed on the model. The roadmap table names remedies without mechanisms.

| proposal | outcome | why |
|---|---|---|
| Integrate an SMT solver (Z3) for inductive proofs of invariants | Deferred | It is sound only for a small decidable fragment. It brings a new heavy dependency, and the useful finite case is already covered by determine(). |
| Hierarchical memory summarization and anaphora pointers for capsules | Already present | `ask_risk` already reports an ask that mentions a bound name it is not given, and a pronoun with nothing to resolve against. An ask with no inputs is legitimate, and its capsule says "nothing beyond the statement itself". |
| Information-entropy floors and exact grounding witnesses against vacuous answers | Built in 2.3 | A warning (`SYM_VACUOUS`) when an ask's anchored checks accept the empty answer, at check time and at run time. The entropy floor is rejected. |
| Logit clamping, tolerant proof witnesses and seed enclaves for cross-hardware determinism | Rejected | It rests on a false premise: replay does not re-run models. Tolerant grouping and seeds already exist. |
| Automated specification-vs-model diagnostic engine (Quine-Duhem) | Built in 2.3 | When retries run out, the report says whether the rejected answers were all the same or all different, as a hint and never as a verdict. |
| Strict module separation of logic, flow and prompts | Rejected | No concrete mechanism is given. The function/routine split already separates pure code from model calls, and forced file separation would only add ceremony. |
| Information-theoretic early exit and confidence routing for escalation | Deferred | The budgets and pre-call exits already exist. The stop rule should come only after measuring how often convergent rejection happens in real escalation runs (RESULTS.md has checked-escalation rows to extend). |

### INTENSE-CRITIQUE-AND-LIMITATIONS.md

Without the analogies, the document makes one real point. Its two concrete claims about the code are wrong as stated. Steered values are not laundered: the language reports `needs_owner` for consequential acts. Retries refuse acts statically and at runtime and never roll back effects. What is real is that the host executor's default full mode (host_executor.py) auto-approves exactly the steered `money`/`destructive` acts the document worries about. That is a host-policy decision the operator made, not a flaw in the flow labels. The remaining proposals (proof terms, sagas, transparency) are either already disclaimed or partly implemented in SPEC/EFFECTS, or they lack an engineering design.

| proposal | outcome | why |
|---|---|---|
| Un-launderable information flow (stop untrusted->steered from enabling consequential acts) | Already present | The flow labels and `needs_owner` exist. the host executor's guarded mode with automatic approval holds exactly these actions; full mode approving them is the operator's setting of 2026-10-03. |
| Two-phase commit / compensating sagas for external effects | Deferred | The premise (rollback of effects) is false; the existing design already avoids it. Compensation is a sound new feature, but it is only useful once real programs chain several acts. |
| Constructive proof-term generation | Rejected | It attacks a claim the spec does not make. Proof terms for natural-language extraction are not well-defined. |
| Remove 'soundness/decidability' overclaim (verification trilemma) | Rejected | It targets a claim that is not made. The limits are already explicit, bounded failures. |
| Preserve modality and hedges in extraction (anti-'Procrustean' schemas) | Rejected | No mechanism is proposed. Authors can already add caveat or confidence fields to a Record type. |
| Avoid shortcut learning when training on invariant rewards | Rejected | It criticises a training pipeline that does not exist, and its mathematical argument is wrong. |
| Transparency about what a check proves (counter automation bias) | Built in 2.3 | The host executor run view lists the checks a run evaluated, or says that nothing tested the answers. |

### INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md

Without the philosophy, the document proposes one user-level program: ask a model to split a heated message into observations, feelings, needs and requests, filter the result with substring checks, then compare two such records by exact string membership. Symblic can already express all of this with `define ... as Record`, `one of`, `ask`, `ensure ... else retry`, `contains`, comprehensions and the `text` library. The section 6 code is not Symblic syntax, and its reconciliation kernel cannot work on model-paraphrased text. The only useful additions are a worked example or library module with a closed needs vocabulary, quote-grounded observations and model-judged equivalence (it needs no language change), and possibly an epistemic-knowledge rule library over the existing Datalog engine.

| proposal | outcome | why |
|---|---|---|
| Four first-class intersubjective types (Observation, Affect, Need, Request) | Rejected | The existing type system already expresses it. New primitives would add domain vocabulary to the core without any new checkable semantics. |
| LLM autoformalizer 'applicator' that parses dialogue into an IntersubjectiveFrame | Rejected | This is an ordinary ask. The useful grounding check already exists as a library pattern. |
| EpistemicHygiene contract: keyword invariants for observations, feelings and requests | Rejected | The mechanism already exists. The proposed predicates do not test what they claim to, and SPEC.md already warns that a weak predicate can accept a wrong answer. |
| Naive-realism audit: mark each claim as observed fact vs unverified inference | Rejected | The valid core is a user-level schema plus an existing ensure pattern. Any detection beyond quote grounding rests on model judgment that the kernel cannot verify. |
| Aumann common-knowledge partition engine | Deferred | Sound as finite-model reasoning, and Datalog can compute it. But it has no shown use for Symblic's programs, and the Aumann diagnosis part is unsound. The finite partition model is built (`knows_event`, `common_partition`, `common_knowledge`, `posterior_given`, `agreement_process`; KNOWLEDGE.md): it computes on partitions a program declares and says nothing about what a person knows. |
| ReconcilePerspectives kernel: confirmed vs contested facts, mutual needs, alignment score | Built in 2.3 | An example program (`examples/13-two-accounts.sym`): closed vocabulary, quoted spans, model-judged equivalence stated as such, no score. |
| Costly-signaling commitment witness and 'cryptographic alignment certificate' | Deferred | This would touch personal-data integrations and other people's data, which need their own contracts and consent. There is no use case yet, and the certificate and costly-signal framing is wrong. |
| Multi-frame evidential security with ontically independent frames | Rejected | Symblic already records sources and modes and refuses to claim independence. The document adds no mechanism for establishing independence, only the analogy. |

### HPC-FOUNDATIONS.md

Once the analogies are set aside, the document offers a wish list (SLURM syntax, 100 to 1000 votes, Soufflé/PETSc backends, RLVR training, frame tags, lineage checks, perturbation tests, and a product roadmap). Its philosophy section is background only, and much of what it proposes already exists: frame tags as applicator/observation mode/sources/assumptions, the `families=` diversity filter, `independence: not_established`, replay locks with run.lock.json, and panel probing in symblic.authoring.tighten. It also misstates the runtime's limits, since votes are capped at 25 and the variational solver is an exact, bounded rational solver. Two small parts survive. One is a base-model lineage table so that `families=` stops counting distills and multi-vendor front-ends as separate families. The other is a re-ask stability report (paraphrased or perturbed asks, run on a different panel) that never raises the assurance level.

| proposal | outcome | why |
|---|---|---|
| Scheduler syntax in asks (by="hpc:slurm", nodes=, gpus=) | Rejected | Resource placement belongs in the host, not in program text, and the existing @node/placement layer already covers it. Putting it in the language would also hurt replay portability. |
| Scale votes to 100-1000 and add sequential Monte Carlo search | Rejected | Adaptive sampling (ahead) and checked escalation already exist. Raising N mostly buys correlated repeats, and SMC does not apply to whole-answer CLI calls. |
| Parallel kernel backends: Soufflé Datalog and BLAS/LAPACK/PETSc for the variational solver | Deferred | No measured workload needs millions of facts, and the solver half contradicts the exact-arithmetic contract. |
| RLVR/GRPO training of an autoformalizer and schema reader with ensure/assert as reward | Deferred | This is a large, compute-heavy research project with no baseline measurement. The reward claim is wrong as stated, and no task-level evaluation exists to detect Goodhart effects. |
| Native frame declarations (frame=instrumental(...)/experiential(...)) | Rejected | Provenance labels already exist with the right caveat (no confidence bonus). A three-way frame enum would add vocabulary, not a mechanism. |
| Lineage-aware family counting for consensus | Built in 2.3 | Model families are counted by lineage; a model of unknown lineage adds no family. |
| Evidential-security perturbation pass | Deferred | `permute` is the deterministic probe. Stability under paraphrase needs a held-out panel before its number means anything. |
| Automatic alternative-check compiler pass (model-generated alternative verification frames) | Rejected | The sound part, kernel checks the author writes and enumeration-based determination, already exists. Auto-generating checks with models adds circular predicates, and SMT is a separate large project with no stated workload. |

### QUANTUM-FOUNDATIONS-OF-SYMBLIC.md

Once the analogies are set aside, the document contributes two usable engineering ideas, and the code already covers most of both. The first is to measure order sensitivity inside one ask (a permutation probe). The second is to stop one action from running twice, which effect identity already does. Everything else either swaps in physics vocabulary for mechanisms Symblic already has (typed schemas, agreement thresholds, finite enumeration) or rests on false claims. The worst of these are that the SPD quadratic solver is "isomorphic" to an Ising ground-state problem and that Symblic "assumes independence" between asks, when capsules actually isolate them.

| proposal | outcome | why |
|---|---|---|
| Order-effect tracking between sequential asks (density matrix rho, projective updates) | Built in 2.3 | `permute=K`: K rotations of the option order (R9 of RESEARCH-AGREEMENT.md). |
| Propositions as projection operators (orthomodular quantum logic) instead of Bool | Rejected | Nothing defines which matrices LinguisticFrame and BehavioralFrame are, how they would be estimated from black-box model calls, or what a commutator value would decide. The real problem underneath, ambiguous instructions, is already handled by `ambiguous` readings and tighten. The finite rational algebra is built (`is_projector`, `commutator`, `commutes`; OPERATORS.md) as a modelling tool; `and` keeps its Boolean meaning. |
| ensure compiled to a POVM; Born-rule pass probability; minimum_amplitude and von_neumann_entropy_threshold | Rejected | The measurable parts (share of samples agreeing, entropy of the vote) already exist. The quantum parts refer to quantities that cannot be observed. What the projector model predicts for ordered yes/no questions is computable (`ordered_probability`; OPERATORS.md), and `order.qq_gap` measures the matching quantity on counts of real answers. |
| Decoherence and einselection as the mechanism that yields typed outputs | Rejected | There is no mechanism beyond the typed schema and parser that already exist. |
| DisCoCat / ZX-calculus intermediate representation instead of passing text to models | Claim rejected; construction deferred | The claim (a semantic normal form that fixes what a model answers) is rejected. The construction is a research direction: compare a small tensor pipeline with structured extraction on negation and role reversal (RESEARCH-ADOPTION.md). |
| Compile finite constraints to QUBO/Ising and solve by annealing or VQE on ensure failure | Deferred | The quantum and annealing parts are heuristics with no proof of optimality, uniqueness or unsatisfiability, which is weaker than what Symblic has now. A classical solver backend is sound, but it needs evidence that real programs hit the 20 000 cap before it is worth adding a dependency. The exact finite form is built: `ising_minimize` evaluates every state of at most 16 spins and reports how many attain the minimum (DISCRETE.md). No annealing. |
| Linear (use-exactly-once) capability types justified by no-cloning | Built in 2.3 | A warning (`SYM_SAME_KEY`) when two `act` statements on one path share a capability and a literal key: the second would be served the first one's outcome. Linear types for capabilities are deferred: capabilities are catalogue names, not values; affine handles for one-use resources are a research direction (RESEARCH-ADOPTION.md). |

### QUANTUM-DETERMINISM-ANALYSIS.md

Set the physics aside and the document has almost no engineering content. Its sound points are already in Symblic or are generic: exact arithmetic gives reproducible results (the kernel already uses exact rationals plus a fixed-context Decimal), seeded solvers can be replayed, and LLM outputs can depend on prompt order. Its main mathematical claims are wrong: ZX confluence and a unique Ising ground state, and no-cloning does not imply linear logic or race freedom. It also misdescribes retries, locks and replay. The only new testable idea is to measure order sensitivity by permuting the KNOWN items in a capsule.

| proposal | outcome | why |
|---|---|---|
| Density-operator tracking of prompt order (projector updates, commutators) | Built in 2.3 | `permute=K` (the same mechanism as above). |
| ZX-calculus graph rewriting for semantic composition | Claim rejected; construction deferred | Confluence is false as stated and no rewrite reaches the model answer. A bounded adapter that checks supported circuit rewrites by exact matrix equality is a research direction (RESEARCH-ADOPTION.md). |
| Compile multi-variable constraints to an Ising Hamiltonian and solve for the ground state | Deferred | The Ising/annealing route is incomplete and its uniqueness claim is false. An exact solver backend extending the existing determination is sound. The exact finite form is built: `ising_minimize` (at most 16 spins, exhaustive, with the number of ground states; DISCRETE.md). |
| Linear 'QLinear' types justified by no-cloning to prevent races across nodes | Claim rejected; construction deferred | No-cloning does not imply it, and immutable bindings already rule out the races described. Affine handles for genuinely one-use resources are a research direction (RESEARCH-ADOPTION.md). |
| Guard 1: never sample; use exact projection, expectation and argmax | Rejected | No quantum state exists in Symblic to project. The model-side analogue (temperature 0, a fixed seed, record and replay) is already implemented. |
| Guard 2: cyclotomic exact arithmetic to remove floating-point/GPU drift | Rejected | Kernel determinism is already achieved. The GPU drift it targets sits in model applicators, and replay sidesteps that by recording replies. |
| Guard 3: pin annealer seed and schedule to the input's SHA-256 | Rejected | It depends on proposal 3's annealer, which should not be built. Seed pinning is already the convention for model calls. |

### PHYSICS-AND-ADVANCED-MATHEMATICS.md

The physics in the document is analogy, and none of it carries over to prompts or programs. "Cognitive enstrophy", "epistemic curl" and "semantic operators" have no definitions that anything could compute. The example code is not Symblic syntax: it uses contract, invariant, var and braces. The parts that would already work in Symblic are its step and call budgets, conserved-quantity asserts, weight-ranked context packing and a quadratic solver that accepts any positive-definite matrix. The one small thing worth adding is an opt-in robust numeric aggregate, a weighted median with reported spread, for numeric asks; this replaces the proposed Wasserstein barycenter.

| proposal | outcome | why |
|---|---|---|
| BKM 'NonBlowup' contract over execution traces | Rejected | The proposal has no computable quantity. The useful part, bounding runaway iteration and model calls, already exists as step, depth and call budgets. |
| Symplectic and Noether invariant contracts on state transitions | Rejected | The new checks are either vacuous (d of an exact form) or wrong for the stated system (energy in viscous flow). The sound part, exact conservation asserts, already exists. |
| Wilsonian RG context compression for capsules | Rejected | The premise about capsules is false. A hidden model summariser would also add an unchecked, lossy step that the capsule's provenance would not show. |
| Fisher-Rao natural-gradient variational solver | Claim rejected; construction deferred | The solver already accepts any rational SPD metric, and natural gradient is not one exact solve. Comparing ordinary and natural-gradient updates on a small explicit distribution is a research direction (RESEARCH-ADOPTION.md). |
| Wasserstein-barycenter consensus instead of majority voting | Built in 2.3 | `vote=median` with `within`: the weighted lower median, with the spread reported. |
| Physical invariant 'contract' construct as a defence against specification gaming | Rejected | It adds no mechanism beyond functions plus ensure/assert, which already exist. The announcement it starts from is real (OpenAI, 8 September 2026: a Lean-checked forced blow-up result, disputed and unrefereed when reported); the added claim that a model gamed the specification is unsupported, and a forced blow-up is a resolution the Clay statement lists, not a loophole. |

### GRAND-UNIFICATION-AND-STRING-THEORY.md

Once the analogies are set aside, the document has very little engineering content. Navier-Stokes, AdS/CFT, worldsheets, mirror symmetry and T-duality give no mechanism that could be implemented or tested on prompts, and several of its claims about the physics and maths are wrong. Two small mechanisms survive. First, merging partial answers from several applicators and reporting where they conflict on shared fields (the sheaf gluing check, with no cohomology involved). Second, possibly, an exact projection of a numeric answer onto linear constraints that is reported as a repair. Symblic already covers schema identity (named types resolve structurally) and much of the 'check before the fact' idea (enumeration, schema-constrained answers).

| proposal | outcome | why |
|---|---|---|
| Leray-projection contracts (continuous invariant projection instead of after-the-fact checks) | Deferred | The fluid framing has no content. The surviving core is sound but alters model answers silently unless carefully reported. The exact form is built as an explicit repair: `reconcile(x, C, d)` returns the nearest values with C x = d and how far they moved (PROJECTION.md). Nothing is projected silently. |
| Ryu-Takayanagi surface check for hallucination (HolographicIntegrity contract) | Rejected | No definable mechanism survives. The only measurable uncertainty signals (vote entropy, reading lists) already exist and are explicitly not correctness checks. |
| Worldsheet / Virasoro execution making programs immune to prompt injection | Rejected | There is no engineering content. The real problem is handled by information-flow labels, which the document does not mention. |
| Mirror-symmetry solver: map hard symbolic constraints to linear ODEs in the 'neural' domain | Rejected | Unsound. No mechanism is defined. |
| T-duality compilation of large swarm programs into micro-capsules | Rejected | No engineering content. |
| Sheaf consensus: glue local agent answers, report the obstruction to agreement | Built in 2.3 | Library functions `records.conflicts` and `records.agree`: agreement of two records on the fields they share (the degree-0 gluing condition). A cellular sheaf with explicit restriction maps is a research direction (RESEARCH-ADOPTION.md); no cohomology claim is made. |
| Univalence: automatic invariant transport between isomorphic schemas | Claim rejected; construction deferred | Univalence constructs no equivalence. Explicit forward and backward record mappings, checked by round trips on a finite domain, are a research direction (RESEARCH-ADOPTION.md). |

## Defects found while building 2.3, not changed by it

These predate 2.3 and are outside its scope; each is reproducible from the description.

- A loop that asks the same question without varying its text or seed reuses earlier answers from the run's
  call cache: the capsule's statement counter is clamped to the program's statement count
  (`min(self.no, self.total)` in `symblic/kernel/run.py`), so later iterations send identical requests. Give such asks a
  per-iteration `seed`, as example 14 does.
- `import M as M.` fails for a module that defines a type ("type dates.Date is already defined",
  `symblic.lang.abstraction._alias_type`); `import a, b from M.` works.
- `check` reports "unknown type" for an imported type in a `let` annotation (`let x: dates.Date = ...`), which
  runs correctly.
- `check` accepts `import text as text.`, which a run refuses ("text is a builtin function name").
- A line the checker does not recognise is read as a natural-language instruction (a prose ask), so pseudo-code
  passes `check`. the host executor's planner refuses such lines (`host_executor_plan.prose_lines`); `check` itself does not.
