# Improving Symblic via Intersubjectivity: Epistemic Types, Multi-Frame Verification, and Theory of Mind in Language Design

> **Speculative AI writing, revised; not a research result.** The first version of this document was generated
> by an AI model (Gemini, through Google's Antigravity agent) in October 2026, and a later AI coding agent
> corrected it against the code. No human expert has reviewed it. Its mathematics, physics and philosophy are
> not results of this project, and the links it draws to Symblic are analogies unless a section names working
> code and tests. See [../MADE-WITH-AI.md](../MADE-WITH-AI.md).

**Author:** an AI assistant (the Antigravity CLI agent, agy), asked to criticise Symblic and to connect it with other fields. The original header credited a person and a "Codex Integration Team"; no record shows Codex writing or integrating this document.

**Focus:** a critique of Symblic and six proposed changes, motivated by work on intersubjectivity, the multi-frame design rationale ([EVIDENCE.md](EVIDENCE.md)) and social epistemology, with the outcome of each

**Date:** written 2026-10-03 against Symblic 2.2; corrected 2026-10-04 against Symblic 2.4

**Status:** proposal, reviewed; not a specification. [SPEC.md](SPEC.md) specifies what was built. [REVIEW-2.3.md](REVIEW-2.3.md) records the outcome of each proposal: two were built in reduced form in 2.3, one was deferred and three were rejected.

False claims have been replaced where they stood. Blocks marked "proposed syntax" are not Symblic. `check` accepts them anyway: it reads most of their lines as prose, that is, as plain-language instructions to a model, so in a program they would become model calls, not the constructs they describe (REVIEW-2.3.md, "Defects found while building 2.3, not changed by it"). Blocks marked `symblic` pass `check` under 2.4 and 2.5.

The corrections describe Symblic 2.4. Symblic 2.5 (Reform 3), installed on 2026-10-04 after this correction, is not reviewed here ([REFORM-3.md](REFORM-3.md)).

---

## 1. The Core Critique, Checked Against the Code

The original said that Symblic (v2.0–v2.2) rests on "naïve realism and epistemic monism": one global truth and one shared meaning. The code did not match that description at 2.2, and it does not now:
- SPEC.md separates executable meaning from model interpretation.
- It states that a result does not establish "that a formal statement captures an author's intention or that a model's answer describes the world correctly".
- A passing check establishes conformance to the encoded predicate, and agreement is never treated as correctness.
- Evidence records say `independence: not_established`.

Two narrower points do hold: Symblic has no modal types, and a weak check can accept a degenerate answer.

### What the critique claimed, and what holds

1. **The "single-world" claim.** The original said Symblic assumes one objective state of the world and identical meanings for every agent, and it showed a `contract ... { invariant: ... }` block as Symblic code. Symblic has no `contract` or `invariant` statements and no brace-delimited blocks. Braces appear only in types (`Record {...}`, `one of {...}`), in record and set values, and in string interpolation. The check is an `ensure` after the `ask` it constrains:
   ```symblic
   define Item as Record {name: Text, amount: Number}.
   define Invoice as Record {items: List of Item, total: Number}.
   given doc: Text.
   ask inv: Invoice "Extract every line item with its amount, and the invoice total.\nINVOICE:\n{doc}"
   ensure inv.total = sum([i.amount for i in inv.items]) else retry.
   ```
   Passing that check does not mark the answer "objectively correct". The answer's evidence lists the model observations behind it, with the assurance `typed_answer`, and the check's receipt has the scope `encoded_predicate`.

   Ambiguity and disagreement are measured rather than assumed away (Upgrade 3):
   - alternative readings (`ambiguous`) and panel probing (`tighten`);
   - definitions on terms and options, and option-order probes (`permute`);
   - the vote record: the tally, the distinct answers, the vote entropy and the model families.

   What holds is that Symblic cannot see a model's internal "frame". It records what each model answered, under which request, and what the author declared about the method (`mode`, `sources`, `assumptions`). These declarations are labels, not measurements of independence.

2. **The "beetle in the box" (Wittgenstein), as an analogy.** In *Philosophical Investigations* §293, the word "beetle" works in the shared language whatever is in each person's private box, because the private object plays no part in how the word is used. Applied to a developer's idea of "status" and a model's weights, the analogy is fair. Its lesson is that meaning has to be fixed by public criteria.

   The original's claims about Symblic are wrong.
   - `apply ExtractStatus()` is not Symblic.
   - Symblic does not assume that a shared word means a shared grounding. Authors give public criteria: `one of` options with definitions, `term ... means`, worked `examples=` and checks. Since 2.4, spec sheets add worked examples that the model's code must reproduce.
   - Divergence does not get "a crude retry loop". A failed `ensure ... else retry` re-asks with the rejected answers and the failed condition. Since 2.3, when the check has no `because`, the re-ask also carries the kernel's values for the parts that depend on the answer alone.

3. **No modal types (Hintikka, Aumann).** The original listed Symblic's types as `int`, `float`, `string` and `bool`. The actual types are:
   - `Int` (optionally a range) and `Number` (exact: a rational, never a float; optionally rounded to N places or ranged);
   - `Bool`, `Text`, `one of {...}`, `List`, `Set`, `Record`, `Svg` and `Any`;
   - named types, and since 2.4 `Code`.

   It is true that no type expresses belief, knowledge or common knowledge in the sense of epistemic logic (Hintikka 1962). The original's questions are answered by records kept at run time:
   - **Who observed it.** A model answer records the applicator, the model and node the reply reported, the attempt and round, and hashes of the request, capsule and statement. An `observe` result records the capability, a hash of its arguments, the time and a hash of the result.
   - **In what frame.** The author can declare `mode`, `sources` and `assumptions`. These change neither votes nor confidence.
   - **Belief or knowledge.** Values other than ask answers record their mechanism (`input`, `kernel_computation`, `model_derived`, `observation`, `effect`, `aggregation`) and their parents' hashes. Each statement also has a determinism class. Since 2.3, common knowledge in Aumann's sense (1976) can be computed on finite partitions that a program declares ([KNOWLEDGE.md](KNOWLEDGE.md)); this says nothing about what a person or a model knows.
   - **How secure.** An ask's assurance is `unique_in_declared_domain` (exhaustive enumeration found exactly one passing value) or `typed_answer`. Check receipts cover the encoded predicate only.

   The static checker uses one related property: the information-flow labels that guard actions (Upgrade 1).

4. **Multi-frame checking.** The original said that checking across many observational frames "proves" empirical adequacy. That overstates a design rationale; see EVIDENCE.md.
   - A label in a program cannot establish that two routes are independent (compare Stegenga and Menon on ontic independence; Upgrade 2).

   The original also said Symblic "runs one model, with one prompt, on one input, checks a single invariant, and declares victory". That was false at 2.2 and is false now.
   - An ask can take several votes, from one model or from a group (`votes`; `effort=high` gives 3, `max` gives 5, and `ultra` gives 5 plus a round in which the models see the anonymised candidates).
   - It can require support from N model families (`families=N`).
   - It can escalate through models until one passes (`route=escalate`), or search with checked candidates in parallel (`route=search`, new in 2.4).
   - Any number of `ensure` and `assert` lines can check one answer.
   - The result is reported as a typed answer that passed the encoded predicates, never as a verified truth.

   What holds is that errors can be correlated across models. Symblic states this rather than claiming to solve it:
   - Family counts are "a diversity filter, not evidence of statistical independence".
   - Option rotations by the same models "are not independent readers".
   - Evidence keeps `independence: not_established`.
   - A weak predicate can accept a wrong answer (SPEC.md §5).

   Symblic 2.4 has no reward signal and no training loop, so "reward hacking" can only mean a model satisfying a weak check (point 5). Prompt fragility is measured (`tighten`, `ambiguous`, `permute`), not removed.

5. **Weak checks ("cheap talk", as an analogy).** The original said: "As game theory (Crawford–Sobel, Spence) shows, cheap talk degenerates into uninformative states." That misreads both results.
   - Crawford and Sobel (1982) show that costless messages can carry information in equilibrium when the parties' interests are close enough, and that the most informative equilibrium carries more the closer they are. An uninformative ("babbling") equilibrium always exists, and once interests diverge far enough it is the only one.
   - Spence (1973) concerns costly signals, which are informative because their cost differs by type.
   - A prompted model has no utility function, so neither result applies directly.

   The engineering point is right, and REVIEW-2.3 found it to be the one critique in this document that holds. A check that tests only arithmetic accepts an empty list with a total of 0, or invented numbers that add up.
   - Since 2.3, Symblic warns (`SYM_VACUOUS`) when an ask's checks accept the empty answer. `check` gives the warning when the checks can be evaluated on the empty answer without any other value, and a run gives it whenever its kernel can evaluate them. Both evaluate only checks built from kernel builtins: a check that calls a library function, such as `text.quoted_number`, gets no warning (Upgrade 5).
   - For the program above, `check` reports: "inv: its checks accept the empty answer {items: [], total: 0}; add a check that an empty answer fails".
   - Invented numbers that are consistent with each other can be caught only by a check against something the model did not write: the source text (`quotes`, `text.quoted_number`; Upgrade 5) or an observed record (Upgrade 2).

---

## 2. Six Proposed Upgrades, and What Became of Them

The original said Symblic "must absorb the proven mechanics of human intersubjectivity, cognitive science, and social theory". It gave no evidence that these theories work as mechanisms in programs that call language models. REVIEW-2.3 read each proposal against the code, with the analogy removed, and asked four questions:
- What is the mechanism?
- Is each claim true?
- Does Symblic already do it?
- What is the smallest form that can be tested?

Two proposals were built in reduced form in 2.3, one was deferred and three were rejected.

| Dimension | Original's description of 2.2 | Symblic 2.4 | Proposal ("v3.0 RFC"; no such version) and outcome |
|---|---|---|---|
| Epistemology | Naïve realism: a single global truth | Answers recorded with the observations behind them; checks establish conformance; agreement is never correctness | "Intersubjective, multi-perspectival": no mechanism beyond the six below |
| Type system | Primitive scalars | Exact numbers and ranges, choices with definitions, lists, sets, records, `Any`, `Code`; provenance kept as evidence records | Epistemic modality types: **deferred** (Upgrade 1) |
| Verification scope | Single run, single model | Votes, efforts, groups, `families=N`, escalation, search, many checks per ask, `observe` | Multi-frame concordance: **rejected** (Upgrade 2) |
| Semantic calibration | "Hope / prompt glue" | Definitions, examples, readings, `tighten`, `permute`, the predictability score, spec-sheet examples (2.4); the Interpreter's read-back and questions | Triangulation pass: **rejected**; its sound part already existed (Upgrade 3) |
| Check failures | "Fatal crash / blind retry" | Transactional retry with the rejected answers, the failed check and (2.3) kernel values; a report when retries run out; contradictory finite contracts caught before any model call | Charity diagnostics: **built in reduced form** in 2.3 (Upgrade 4) |
| Degenerate answers | (not in the original table) | `SYM_VACUOUS`; `quotes`, `numbers`, `text.quoted_number` (2.3) | Span witnesses **built**; entropy floor **rejected** (Upgrade 5) |
| Multi-agent model | "RPC calls" | Context policy (only `from` names by default); flow labels and `needs_owner`; finite partition model (2.3) | Knowledge-partition state machine: **rejected** (Upgrade 6) |

---

### Upgrade 1: First-Class Epistemic Modality Types

**Outcome: deferred** (REVIEW-2.3). Most of the provenance already exists. Whether the remaining static rule is worth having depends on how often unchecked model output reaches actions.

#### Proposed syntax (not Symblic; not built)
```
type Epistemic<T, Agent, Frame>
type Observation<T, Agent>   # read from an external sensor or data log
type Belief<T, Agent>        # inferred by a model
type Knowledge<T>            # passed checks: conformance to a predicate, not external ground truth
type CommonKnowledge<T>      # Symblic computes Aumann's notion on a declared partition model; that says nothing about what models or people know
```

#### What it would add, and what exists
The aim was to stop an unverified model extraction from being used as an external observation without an explicit check. No such types exist, and no such compiler rule.

What does exist is provenance on every binding (§1, point 3) and a static information-flow check for actions ([EFFECTS.md](EFFECTS.md) §5):
- Text from a capability declared `untrusted` may not become an argument of an `act` unless the author names it in `allow_untrusted`. That exception is never allowed for a capability that instructs an agent.
- Untrusted text that passes through a closed type becomes `steered`.
- The host is told `needs_owner` when outside text chose or wrote a consequential act.

Whether that act then waits is host policy:
- the host executor's guarded mode holds it for the operator. It approves a steered act automatically only if the operator has enabled that, and an act whose arguments outside text wrote always waits.
- Full mode approves both. It has been the operator's default since 2026-10-03.

The flow rules themselves apply in both modes. The analysis is conservative and has no proof of noninterference.

What is not covered is an answer that was never shown outside text. It carries no label, so nothing requires a check before an `act` uses it. That is the deferred rule. [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md) records the next step: library records for observed, reported, inferred and derived claims, with a checked conversion whenever assurance changes, and no unchecked wrapper named `Knowledge`.

---

### Upgrade 2: Multi-Frame Concordance Contracts (proposed as a "multi-frame engine")

**Outcome: rejected** (REVIEW-2.3). With the analogy removed, the mechanism is a conjunction of checks, some of which read external data. Symblic already expresses that with `ensure`/`assert` plus `observe`. The concordance score adds nothing, and the perturbation frame is undefined.

The multi-frame rationale is not a verification procedure. [EVIDENCE.md](EVIDENCE.md) states how Symblic applies it, as a design rationale rather than as evidence that accuracy improves:
- it records acquisition modes, common sources, assumptions and derived dependencies;
- it keeps external observation distinct from model recall.

#### Proposed syntax (not Symblic; not built)
```
contract RobustAudit(tx: Transaction) {
    frame linguistic:      # the answer's internal consistency
        invariant: tx.amount == sum(tx.items)
    frame behavioral:      # ledger read from outside the model: a second route; independence not established
        invariant: ledger.has_matching_debit(tx.id, tx.amount)
    frame adversarial:     # undefined: nothing says what a perturbation is or what surviving it means
        invariant: invariant_survives_perturbation(tx, delta=0.01)
    enforce MultiFrame_Adequacy:  # all checks pass: conformance to the checks, not truth
        concordance([frame.linguistic, frame.behavioral, frame.adversarial]) >= 0.95
}
```
- **Frames 1 and 2 are two checks.** In Symblic the first is an `ensure` on the answer. The second reads the ledger through a capability (`observe`) and compares the two with an `ensure`. That second route is real, because it reads data the model did not write. `records.agree` and `records.conflicts` (2.3) compare two records of one thing on their shared fields.
- **Frame 3 has no definition.** The defined probe is `permute=K`, which asks a closed question with its options in K orders. A paraphrase-stability report is deferred until a held-out panel exists.
- **The concordance score adds nothing.** Over three pass/fail checks, "concordance ≥ 0.95" just means that all of them pass.

#### What the proposal claimed, corrected
The original said this "eliminates prompt fragility and model hallucinations" and "forces Symblic programs to gather evidence from ontically independent sources". It does neither.
- Checks that share a failure mode pass together, and a model can be wrong in ways no check tests.
- A label cannot make sources independent. Independence needs assumptions about how each source fails, and method labels do not supply them (Stegenga and Menon 2017).

What a second, external check does give a program is a way to reject an answer that only the model's own text supports.

---

### Upgrade 3: The Davidsonian Triangulation Pass (Pre-Flight Semantic Calibration)

**Outcome: rejected** (REVIEW-2.3). Its sound part already exists as `tighten`, ambiguous readings and test certificates: probing a panel before a run, and rewriting ambiguous asks. Measured gains still need a held-out panel.

Davidson argued that the content of thought and speech is fixed by triangulation: two creatures respond to each other and to shared objects ("Rational Animals", 1982, and "Three Varieties of Knowledge", 1991, both in *Subjective, Intersubjective, Objective*, 2001). For an author and a model the analogy is only partial, because they share text, not a world.

#### What was proposed (not built)
The compiler would have:
1. synthesised three probe examples from the contract's invariants;
2. run them and compared the answers with the invariants;
3. on "semantic drift" (reading "gross revenue" as "net revenue"), computed a "Semantic Offset Vector" and adjusted the prompt.

None of this exists, and the vector has no definition. Probes derived from the invariants can test only what the invariants state. If no check separates gross revenue from net revenue, an answer that confuses them passes every such probe.

#### What exists before a run
- **The Interpreter page.** Before a program exists, it reads an operator's request back as a proposed goal, requirements and assumptions. It asks questions that separate outcomes that matter, such as the units, or an image versus an editable 3D object, with at most three pending at once. It keeps the original request and earlier answers, and translates the result into a checked program. Model proposals stay labelled as proposals, and a passing check establishes the encoded checks, not equivalence to the operator's intention ([INTERPRETER.md](INTERPRETER.md)).
- **`tighten`.** Every panel member answers every ask, with a fresh context, temperature 0 and readings on. Each ask is then diagnosed as `converged`, `format`, `ambiguous`, `capability` or `divergent`. A clarifier rewrites the non-converged asks with explicit units, conventions and definitions, and the asks are probed again. A rewrite that leaks the most common answer is refused. The fair test of a rewrite is a held-out panel.
- **`ambiguous`.** `ambiguous=true` records each model's alternative readings. `ambiguous=fail` stops the run when a model lists two.
- **`check` and `preview`.** `check` scores each ask's wording for known sources of disagreement (a predictability score from 0 to 100, which is a guide and not a probability). `preview` runs the kernel up to the first ask and shows the exact capsule and schema it would send, without calling a model.
- **Test certificates.** These tie recorded test outcomes to the source, modules and kernel, and they attest only to the tests observed.
- **Spec sheets (2.4).** A spec sheet states each unit's meaning as worked examples, and the model's code must reproduce them in `js_test` before it is accepted.
  - Small local models (qwen3:4b-instruct, phi4-mini, gemma3:4b) built Tetris this way.
  - The page passed 39 of 39 required harness checks, in two separate builds ([SPEC-SHEETS.md](SPEC-SHEETS.md)).
  - A unit that passes its examples can still be wrong on inputs the examples do not cover.

#### What these features do
The original said the pass "solves the Beetle in the Box problem" and that "meaning is publicly calibrated through verified language games". None of these features solves that philosophical problem. They make an intended meaning public, as definitions, examples and checks, for the cases those cover. They also measure where models still read a statement differently.

---

### Upgrade 4: The Principle of Charity & Epistemic Diagnostics (Smart Recovery)

**Outcome: built in reduced form in 2.3** (REVIEW-2.3). Retry feedback carries the kernel's values for the parts of a failed check that depend on the answer alone. No model writes a diagnosis.

Davidson argued, without proving it, that interpretation requires charity: reading a speaker so that most of what they say comes out true, and their beliefs rational, by the interpreter's lights ("Radical Interpretation", 1973, in *Inquiries into Truth and Interpretation*, 1984).

#### What happens when a check fails
The original said that in 2.2 a failed check either crashed or sent back an unhelpful message ("invariant failed: total == 100"). That is not so. Retries were already transactional, and the next attempt was told the rejected answers and the check they failed. Since 2.3, when the check has no `because`, the feedback also gives the kernel's values for the parts that depend on the answer alone. For the program in §1, point 1, the 2.4 kernel sends (values illustrative):
```text
Attempt 2. These answers were rejected: {…}. Each failed the check `inv.total = sum(comp)`.
Give an answer that passes it. In the last answer: inv.total = 100; sum(comp) = 90.
```
- 2.4 prints a list comprehension inside a check as `comp`, so the model is not shown what was summed. SPEC.md §5 shows the intended text.
- A part that reads anything else (an input, an observation, another result) is never shown, because that would hand over the expected value.
- When the check has a `because` message, it is passed on as written instead.
- When retries run out, the report says whether the attempts gave the same answer each time (look at the check, type or input), a different one each time (the statement may be read several ways), or a mix. This is a hint, never a verdict. It came from a proposal in [CRITIQUE-AND-LIMITATIONS.md](CRITIQUE-AND-LIMITATIONS.md), not from this one.
- The feedback lists the last five rejected answers, each cut to at most 200 characters. In 2.4, checked escalation and search (`route=escalate`, `route=search`; spec sheets use search) show a rejected `Code` answer back whole, up to 16 000 characters. A JavaScript test report quotes the text of the line where an error happened ([JS.md](JS.md)).

#### What was proposed and not built
The runtime would have generated hypotheses about the failure and named a cognitive bias (the original's example was "Scope Generalization Error"). It would then have injected a narrower "charitable invariant" and re-asked with "the exact logical lemma". None of this exists.
- Such a diagnosis would be a model's judgement, and nothing in the program could check it.
- The injection would change what the program checks without its author.

A run never rewrites a check. `tighten` proposes rewritten asks in a separate job, whose result the author reads.

---

### Upgrade 5: Non-Degeneracy Checks (proposed under a mechanism-design framing)

**Outcome: built in reduced form in 2.3** (REVIEW-2.3). Two things were built:
- exact quote grounding (`quotes`, `numbers`, `text.quoted_number`, `text.quoted_number_in`);
- the `SYM_VACUOUS` warning, from the matching proposal in [CRITIQUE-AND-LIMITATIONS.md](CRITIQUE-AND-LIMITATIONS.md).

The entropy floor was rejected.

The original grounded this upgrade in Crawford–Sobel cheap talk and in the mechanism design of Hurwicz, Maskin and Myerson. Those results concern agents that have preferences and choose strategies. A prompted model has neither, so the results give an analogy, not a guarantee. The requirement stands on its own: a check should not accept a degenerate answer.

#### The problem (correct as stated)
Asked for items with `sum(items) == total`, a model can return an empty list with a total of 0 and satisfy the check trivially.

#### The proposal, and what was built
```
# proposed syntax (not Symblic)
contract NonDegenerateExtraction(doc: Document, res: Result) {
    invariant: res.total == sum(res.items.amount)      # 1. exists as ensure
    invariant non_vacuous:                              # 2. rejected (below)
        entropy(res) >= 0.75 * entropy(doc)
    invariant grounded_witness:                         # 3. built in 2.3 as quotes / text.quoted_number
        forall item in res.items:
            doc.contains_exact_span(item.source_span)
}
```
- **The entropy floor is rejected.** The entropy of a single text is undefined without a probability model. Read as information content, a correct extraction carries far less than its source, so such a floor would reject correct answers.
- **The span witness was built.**
  - `quotes(passage, quote)` is true when the quote occurs in the passage with the same characters and case, as whole words and numerals, after NFC and white-space normalisation. So "20" is not a quote of "120".
  - `numbers(text)` returns the plain decimal numerals written in a text; some written forms (a decimal comma, a fraction, spaced digit groups) are deliberately not read (SPEC.md §7).
  - `text.quoted_number` combines the two:
```symblic
import quoted_number from text.
define Item as Record {name: Text, amount: Number, quote: Text}.
define Invoice as Record {items: List of Item, total: Number}.
given doc: Text.
ask inv: Invoice "Extract every line item with its amount and, as quote, the words of the invoice that state the amount, copied exactly. Also give the invoice total.\nINVOICE:\n{doc}"
ensure len(inv.items) > 0 else retry because "the invoice lists at least one item".
ensure all x in inv.items: quoted_number(doc, x.quote, x.amount) else retry because "each quote must be copied exactly from the invoice and must contain the amount".
ensure inv.total = sum([i.amount for i in inv.items]) else retry.
```
The `len` check matters. Without it the empty answer passes every check, and nothing warns: `quoted_number` is a library function, so neither `check` nor a run evaluates these checks against the empty answer. Written with the builtins instead (`quotes(doc, x.quote) and x.amount in numbers(x.quote)`), the same checks do get `SYM_VACUOUS` from both. With the `len` check, an invoice that really lists no items fails the run after its retries; a program that must accept such invoices has to allow for them explicitly (RESEARCH-ADOPTION.md). `SYM_VACUOUS` itself is never a refusal, because an empty answer can be legitimate (SPEC.md §5).

#### What this establishes
The original said the model then "cannot take the lazy path or fabricate numbers", and that "truth-telling is made the strictly dominant strategy". Neither holds.
- These checks reject an empty answer (given the `len` check) and a number that is not written in a span copied from the source.
- They do not check which item, unit or relation the number belongs to. A consistent extraction can quote the wrong item's amount; [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md) keeps this as a standing counterexample.
- They do not check that the list is complete, and the total is compared only with the listed amounts. An answer that lists one item, with that item's amount as the total, passes every check.
- A "dominant strategy" needs agents with utilities.

---

### Upgrade 6: Theory of Mind (ToM) & Aumann Knowledge Graph in Multi-Agent Symblic

**Outcome: rejected** (REVIEW-2.3). The workable parts already exist: what each ask sees, and approval before consequential acts. The rest relabels sets of facts with guarantees it does not have. The finite partition model that the theorem is about was built separately in 2.3 ([KNOWLEDGE.md](KNOWLEDGE.md)).

In Aumann's model (1976):
- an agent's information is a partition of a set of possible states;
- an event is common knowledge at a state when the cell of the partitions' meet that contains the state lies inside the event.

Which states an agent can tell apart is the author's modelling assumption. A transcript of what an agent was shown is not a partition.

#### Proposed syntax (not Symblic; not built)
```
system CollaborativeTask {
    agent Researcher
    agent Verifier
    user Operator
    epistemic_state {
        private(Researcher): raw_model_scratchpad
        private(Verifier): verification_seed
        mutual([Researcher, Verifier]): draft_proposal      # each knows it; whether each knows the other knows is left open
        common([Researcher, Verifier, Operator]): {         # everyone knows, everyone knows that everyone knows, and so on
            contract_spec, safety_bounds, approved_actions
        }
    }
    transition PromoteToCommonKnowledge(fact: Proposal) {  # proof plus approval does not create common knowledge
        require: Verifier.proves(fact) and Operator.approves(fact)
        ensures: fact in common([Researcher, Verifier, Operator])
    }
}
```
The original's comments in this sketch were wrong on two points, and the transition does not work:
- **Mutual knowledge** means that everyone knows the fact. It does not mean "neither knows the other knows it".
- **Common knowledge** is the unending hierarchy (Lewis 1969; Aumann 1976), not "certified shared reality".
- **A proof plus an approval does not create common knowledge.** Each party would also need to know that the others received the fact, and so on up the hierarchy. Over unreliable messages, common knowledge cannot be reached at all (Halpern and Moses 1990).

The proposed module, `symblic_agent.py`, does not exist.

#### What exists
- **Context.** Each ask sees its own text, with anything it interpolates, and what its context policy allows (by default, the names in its `from` list). Its evidence records the capsule's hash.
- **Flow labels and `needs_owner`.** See Upgrade 1.
- **Check receipts.** These record which statement checked which predicate on which bindings.
- **The finite model.** Its builtins compute exactly on at most 64 states and 8 agents. With a common prior, the announcement process (Geanakoplos and Polemarchakis 1982) ends in equal posteriors. Agreeing on a posterior is not the same as being right.

#### What the proposal claimed, corrected
The original said that tracking the partition "mathematically eradicates multi-agent coordination collapse". The theorem it cites does not say so: Aumann's (1976) is about posteriors under a common prior, not about coordination. The failure it describes is a real risk: A acts on a fact believing B checked it, while B believes A did. The guards are explicit context, check receipts, and approval before consequential acts where the host's mode requires it.

[RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md) records the next step: a finite acknowledgement protocol stating who received which revision, who acknowledged it, and what remains unknown. Acknowledgements do not supply common knowledge.

---

## 3. Summary of Proposed Changes to Symblic Core

Four of the six module descriptions in the original table were wrong, and one of the modules does not exist.

| Module named | Proposed feature | What the module is | Status in 2.4 | Named source of the idea |
| :--- | :--- | :--- | :--- | :--- |
| `symblic/lang/abstraction.py` ("AST") | `Epistemic<T>`, `Belief`, `Observation`, `CommonKnowledge` | Functions, routines, modules and tests; the parser and types are in `symblic/kernel/language.py` | Deferred; provenance exists as evidence records | Epistemic logic (Hintikka 1962; Aumann 1976) |
| `symblic/lang/abstraction.py` (contracts) | `frame`, `concordance()`, `MultiFrame_Adequacy` | As above (routines carry `ensure` contracts) | Rejected; `ensure` plus `observe` cover the defined part | multi-frame rationale |
| `integration/host/symblic_engine.py` ("runtime") | Davidsonian triangulation pass | The operator-only HTTP API. The interpreter is `symblic/kernel/run.py`; panel probing is `symblic/authoring/tighten.py` | Rejected; `tighten`, readings, certificates and spec sheets exist | Davidson; Wittgenstein |
| `integration/host/symblic_engine.py` ("recovery") | Charity diagnostic engine | As above. Retry feedback is in `symblic/kernel/run.py` and `symblic/kernel/diagnose.py` | Built in reduced form: kernel values in feedback (the report when retries run out came from CRITIQUE-AND-LIMITATIONS.md) | Davidson; Habermas |
| `symblic/adapters/variational.py` | Entropy floor and character-span witnesses | Exact minimiser of a supplied rational symmetric positive-definite quadratic (n ≤ 32, with an LDLᵀ certificate); unrelated to extraction | Entropy floor rejected. Spans built as `quotes`/`numbers` (`symblic/kernel/language.py`) and `quoted_number` (`symblic/lang/library/text.sym`) | Mechanism design (Hurwicz, Maskin, Myerson); costly signalling (Spence 1973) |
| `symblic_agent.py` | Knowledge-partition state machine | Does not exist | Rejected; the finite partition model is in `symblic/adapters/knowledge.py` | Agreement theorem (Aumann 1976); double contingency (Luhmann 1984) |

The last column names where each idea came from. Those works motivated the proposals; they do not show that the proposals work.

---

## 4. Conclusion: What Survives

The original concluded that these changes would turn Symblic "from a simple neuro-symbolic validator into an epistemic coordination engine". It said Symblic would then no longer treat the model as "a magical oracle", and would have "provable common knowledge". None of this holds as stated:
- Symblic did not treat the model as an oracle before. It records a model's answer with the observations behind it, and it treats a passing check as conformance to the author's predicate.
- Symblic can compute common knowledge only inside a finite model that a program declares. That model is now built; its result says nothing about what a model or a person knows ([KNOWLEDGE.md](KNOWLEDGE.md)).
- An "authentic communicative encounter" is a metaphor.

What survives is engineering. From this document, 2.3 built two features in reduced form:
- kernel values in retry feedback;
- exact quote grounding, with the empty-answer warning from CRITIQUE-AND-LIMITATIONS.md.

The type rule for unchecked model output is deferred. The rest was already present or had no computable definition. Symblic remains a language whose kernel computes exactly and whose model answers are typed, checked and recorded. Its limits are stated in [SPEC.md](SPEC.md) and [EVIDENCE.md](EVIDENCE.md).

## Sources

- R. J. Aumann, "Agreeing to disagree", *The Annals of Statistics* 4(6), 1976, pp. 1236–1239.
- V. P. Crawford and J. Sobel, "Strategic information transmission", *Econometrica* 50(6), 1982, pp. 1431–1451.
- D. Davidson, *Inquiries into Truth and Interpretation*, Oxford: Clarendon Press, 1984 (includes "Radical Interpretation", 1973).
- D. Davidson, *Subjective, Intersubjective, Objective*, Oxford: Clarendon Press, 2001 (includes "Rational Animals", 1982, and "Three Varieties of Knowledge", 1991).
- J. D. Geanakoplos and H. M. Polemarchakis, "We can't disagree forever", *Journal of Economic Theory* 28, 1982, pp. 192–200.
- J. Y. Halpern and Y. Moses, "Knowledge and common knowledge in a distributed environment", *Journal of the ACM* 37(3), 1990, pp. 549–587.
- J. Hintikka, *Knowledge and Belief: An Introduction to the Logic of the Two Notions*, Ithaca: Cornell University Press, 1962.
- D. Lewis, *Convention: A Philosophical Study*, Cambridge, MA: Harvard University Press, 1969.
- M. Spence, "Job market signaling", *The Quarterly Journal of Economics* 87(3), 1973, pp. 355–374.
- J. Stegenga and T. Menon, "Robustness and independent evidence", *Philosophy of Science* 84(3), 2017, pp. 414–435, doi:10.1086/692141.
- L. Wittgenstein, *Philosophical Investigations*, trans. G. E. M. Anscombe, Oxford: Blackwell, 1953, §293.
- Named without a full citation: Hurwicz, Maskin and Myerson (mechanism design; Nobel memorial prize in economics, 2007); Habermas (communicative rationality); Luhmann (double contingency, *Soziale Systeme*, 1984).
