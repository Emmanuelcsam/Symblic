# Symblic: can a formal description force the same result from any reader?

Original survey: 2026-10-02. Scope corrections: 2026-10-04. Companion to [PRIOR-ART.md](PRIOR-ART.md) (LLM systems, determinism, councils), [SPEC.md](SPEC.md)
and [RESULTS.md](RESULTS.md). This document covers the language side: logic and philosophy of language, human
communication research, controlled languages and engineering practice, and description length.

Historical survey method: sources were reported as opened with WebFetch or downloaded as text, with
bibliographic checks against Crossref, Europe PMC or publishers. This is not a fresh verification of
every historical empirical figure or philosophical inference. Secondary and unopened sources below
remain background pointers, not primary evidence for a new Symblic capability. Labels used below:

- **[secondary]**: the claim comes from an encyclopedia, a textbook page or a review, not from the original work.
- **[snippet]**: seen only in a search-engine summary; the page itself was not opened.
- **[not opened]**: the citation was checked, but the text of the work was not read in this survey.

The original author reported other entries as read on opened pages. Current operational claims must
match [SPEC](SPEC.md); the 2.5 reform does not inherit universal execution guarantees from this survey.

---

## 1. What the evidence supports

1. **True and provable.** Every finite structure with a finite vocabulary can be described up to isomorphism by one
   first-order sentence [Dawar]. A cube can be described exactly, whether as 8 vertices with their adjacencies or as 8
   explicit points in a stated frame. Formal geometric decision procedures require a specified vocabulary,
   theory and encoding; this does not make arbitrary English claims mechanically decidable [Tarski-ax].
2. **A conditional executable contract.** Equal formal inputs under fixed compatible semantics specify
   equal successful results within supported bounds. The historical eight-machine fingerprint experiment
   tested particular programs/versions, not every interpreter or the new 2.5 reform ([RESULTS.md](RESULTS.md)).
3. **False as stated: "this goes for everything."**
   - A first-order theory with an infinite model cannot determine that model up to isomorphism across all cardinalities [SEP-FOMT]. This does not prevent a theory from being categorical at a specified cardinality, or a finite description from defining a particular infinite computable object under a fixed interpretation.
   - Second-order categoricity (arithmetic, the reals) relies on full semantics, which has no complete proof system [SEP-HOL].
   - Some objects have no description shorter than the object itself, and the shortest description cannot be computed [Kolmogorov].
4. **False as stated: "agents who knew nothing."** No finite text fixes its own interpretation [Wittgenstein §201][Kripke][Quine][Putnam][Harnad].
   Description length itself is only defined relative to an interpreter [Kolmogorov invariance]. Shared primitives
   are what a description needs before it can work; the description cannot supply them.
5. **Measured in humans, one-way prose fails often.**
   - One-way Lego instructions: 39% of models built wrong, against 5% when the instructor could see the builder [Clark-Krych].
   - Biology papers: 0 of 193 experiments were described well enough to replicate without asking the authors [Errington].
   - Imagining a cube: 1 of 20+ people located its corners after reorienting it [Hinton].
6. **Controlled language helps but does not reach identity.**
   - Simplified Technical English improves comprehension of complex procedures [Shubert][Chervak].
   - Assembly instructions designed on cognitive principles cut assembly time by 35% and errors by 50% [Heiser].
   - A language that is at once fully precise, fully expressive, fully natural and simple is "practically impossible" [Kuhn].
7. **LLM readers add their own failure modes.**
   - They presume common ground instead of checking it [Shaikh].
   - They recognise ambiguity poorly: GPT-4's disambiguations were judged correct 32% of the time, against 90% for humans' [AmbiEnt].
   - Formatting alone can swing accuracy by up to 76 points [Sclar].
   - They resolve spatial prepositions correctly only 26% of the time, and pronouns 25.5% [Kranti].
8. **Defensible version.** A finite object can be specified up to a stated equivalence in a vocabulary whose
   primitives have fixed, mechanically executed meanings.
   - Pure evaluation is repeatable under equal inputs and compatible runtime/module semantics, conditional
     on successful bounded execution. Replay of recorded model outcomes is a separate contract.
   - Fresh construction by an agent has a measured success/identity rate; precision alone cannot guarantee it.
9. **For Symblic.** Keep exact computation, model construction of checkable proofs/programs/witnesses,
   and uncertain empirical judgment as complementary paths. The kernel can check general rules without
   solving each task. Measure intent fidelity, task correctness, cost and fresh-run agreement separately.

---

## 2. Q1 — Can a description fix its object uniquely? (logic and philosophy of language)

### 2.1 Model theory: what a finite text can and cannot pin down

| Result | Source | What it means for "describe a cube" |
|---|---|---|
| A theory is *categorical* if it has one model up to isomorphism. "There are no categorical first-order theories with infinite models", because of the upward Löwenheim–Skolem theorem; the best possible is one model per infinite cardinality. | Hodges & Scanlon, SEP "First-order Model Theory", rev. 2024-01-25, §§2, 5.1 [SEP-FOMT] | Any description that relies on an infinite domain (the real line, all integers) admits unintended, non-isomorphic readers' worlds. |
| Downward Löwenheim–Skolem: "If a countable collection of first-order sentences has an infinite model, then it has a model whose domain is only countable." Skolem's paradox follows. | Bays, SEP "Skolem's Paradox", rev. 2025-02-05, §1 [SEP-Skolem] | A formal text does not even fix the size of its subject matter. |
| On finite structures, "any finite structure is completely described up to isomorphism by a single sentence" (a sentence φ_A listing n elements, every relation tuple and every non-tuple). | Dawar, *Model Theory on Finite Structures*, lecture notes, p. 3 [Dawar] | The combinatorial cube (8 vertices, 12 edges, 6 faces, incidence) is exactly describable. **This is the true core of the operator's hypothesis.** |
| Second-order Peano arithmetic is categorical (models are isomorphic to ℕ), and the completeness axiom with the ordered-field axioms "characterizes the ordered field of real numbers up to isomorphism". However, "there is no hope of a Completeness Theorem for second-order logic"; Henkin semantics restores completeness and gives up categoricity. Quine called second-order logic "set theory in sheep's clothing" (§5.3). | SEP "Second-order and Higher-order Logic", rev. 2024-08-31, §§1, 5.1–5.3, 9.1 [SEP-HOL] | Categoricity for infinite objects is available only by presupposing a fixed background interpretation of "all subsets". A reader who does not share that background is not forced. |
| Tarski's first-order Euclidean geometry is consistent, complete and decidable through quantifier elimination over real closed fields. It is not categorical: every real closed field F gives a model F². | Tarski's axioms, Wikipedia [secondary]; Tarski & Givant, BSL 5(2), 1999 [not opened] [Tarski-ax] | Every first-order claim about a described cube can be checked mechanically, for example "all 12 edges have length 10" or "the body diagonal is 10√3". A checker can therefore verify geometry, even though the theory does not single out ℝ. |
| Putnam, "Models and Reality" (JSL 45(3):464–482, 1980): operational and theoretical constraints together cannot fix the intended model. Any further constraint offered is "just more theory" and is reinterpreted with the rest. | SEP "Skolem's Paradox" §3.4 [SEP-Skolem]; Putnam 1980 [not opened] | Adding more sentences cannot, on its own, fix how the words are interpreted. What fixes the interpretation must lie outside the text: a shared practice or a shared machine. |

**Russell's definite descriptions.** "The F is G" means: there is an F, at most one thing is F, and it is G. An
incomplete description such as "the table" needs context to "flesh out the description", and how context does this is
"philosophically problematic" (SEP "Descriptions", rev. 2022-09-21) [SEP-Desc]. "The cube" in a Symblic program
identifies an object only if the program's own state makes exactly one thing satisfy "cube".

### 2.2 Why no finite text forces its own interpretation

- **Wittgenstein, Philosophical Investigations §§185–242.**
  - A pupil taught "+2" continues 1000, 1004, 1008, and insists "I did go on in the same way" (§185).
  - "No course of action could be determined by a rule, because every course of action can be made out to accord with the rule" (§201).
  - Agreement must be "not only agreement in definitions but also … in judgments" (§242), and agreement "in form of life" (§241).
  - Source: SEP "Wittgenstein", rev. 2026-09-17 [SEP-Witt].
- **Kripke's "quus".** x ⊕ y = x + y if x, y < 57, and 5 otherwise. No fact about past usage settles that "+" meant plus.
  Kripke's skeptical solution replaces such facts with assertibility conditions grounded in agreement with a community
  (IEP "Kripke's Wittgenstein") [IEP-Kripke].
- **Quine.** One stimulus can be translated as "rabbit", "rabbithood is manifesting itself" or "undetached rabbit
  parts" (inscrutability of reference). Quine himself later called holophrastic indeterminacy a "conjecture", not a
  proof (SEP "Quine", rev. 2023-07-06, §6.2) [SEP-Quine].
- **Quine's regress against conventions all the way down.** Infinitely many logical truths cannot all be stipulated,
  and applying a finite set of conventions already requires logic (SEP "Convention", rev. 2024-02-22) [SEP-Conv]. A
  definitions section cannot define its own rules of inference.
- **Goodman's "grue".** An object is grue if it is examined before time t and green, or not so examined and blue. All
  past evidence supports "grue" exactly as well as "green". Goodman's answer is entrenchment: we project the predicates
  we have historically used (SEP "Goodman", rev. 2024-02-08, §5.3–5.4) [SEP-Goodman]. A reader extends a pattern the
  way its history inclines it to. Two agents trained differently can extend the same examples differently.
- **Davidson.**
  - Radical interpretation relies on the principle of charity: interpret speakers as holding true beliefs "wherever it is plausible".
  - In "A Nice Derangement of Epitaphs" (1986), conventions "facilitate understanding" but "cannot be the basis" for it; interpreters keep "continually adjusting".
  - Source: SEP "Davidson", rev. 2023-04-28, §§3.3, 3.5 [SEP-Davidson].
- **Lewis.** A convention is an arbitrary, self-perpetuating solution to a recurring coordination problem, held in place
  by common knowledge. Signaling games show how meaning can arise from coordinated practice [SEP-Conv].
- **The symbol grounding problem** (Harnad, Physica D 42:335–346, 1990). Learning meaning from symbols alone is like
  "trying to learn Chinese from a Chinese/Chinese dictionary alone". Symbols must bottom out in non-symbolic, iconic and
  categorical representations [Harnad].
- **LLMs.**
  - Bender & Koller (ACL 2020): "a system trained only on form has a priori no way to learn meaning" [BenderKoller].
  - Piantadosi & Hill (2022) answer that meaning can arise from conceptual role, "the relationships between internal representational states" [PiantadosiHill].
  - For Symblic the debate does not need settling. Either way, two models from different families have *different* histories ("entrenchment"), so their interpretations agree only where training made them converge or where the program removes the choice.

**What this implies.** A description works only against a background that the reader already shares: primitives,
logic, and conventions for frames, units and defaults. The background can be:

- a human practice (Wittgenstein, Lewis);
- training that happens to coincide (LLMs);
- a **mechanical interpreter** that executes the primitives. Only this option makes interpretation identical by construction.

### 2.3 How formal semantics removes ambiguity

- **Montague.** "There is in my opinion no important theoretical difference between natural languages and the artificial
  languages of logicians." Compositionality: "The meaning of a compound expression is a function of the meanings of its
  parts and of the way they are syntactically combined." Scope ambiguity ("Every man loves a woman") is handled by giving
  *different derivations* for different readings, so each derivation has one meaning (SEP "Montague Semantics", rev.
  2025-02-05, §§1.1–1.2, 2.5) [SEP-Montague]. Lesson: ambiguity disappears only when the *parse* (the derivation), not
  just the string, is fixed.
- **Discourse Representation Theory** (Kamp 1981, Heim 1982). A discourse builds a structure of discourse referents and
  conditions. Pronouns resolve only to referents that are *accessible*, which handles donkey sentences ("If Pedro owns a
  donkey, he beats it") (SEP "DRT") [SEP-DRT]. ACE uses DRSs as its target representation [ACE].
- **Attempto Controlled English interpretation rules (ACE 6.7)** [ACE-IR]. "Each ACE sentence has only one meaning", achieved by fixed rules:
  - prepositional phrases "modify the verb not the noun";
  - quantifier scope follows textual position;
  - "*and* > *or* > *,and* > *,or*";
  - a pronoun resolves to "the most recent accessible noun phrase that agrees in gender and number";
  - plurals are collective by default, and "each of" marks the distributive reading.
- **Propositions as types (Curry–Howard).** A specification is a type, and a program that inhabits it is a proof (Wadler,
  CACM 58(12):75–84, 2015) [Wadler]. This requires a type system that represents the propositions and checks their proof rules. A typed JSON answer plus a Boolean `ensure` establishes its declared shape and encoded predicate, not an arbitrary proposition. Symblic's separate [proof certificate lane](PROOF-TERMS.md) checks a supplied derivation from explicit premises; a model can construct that derivation while the checker validates it.

### 2.4 The cube, worked through

| Description | Fixes the cube up to | Who must share what |
|---|---|---|
| "a cube" | the reader's concept | Everything. Hinton (Cognitive Science 3:231–250, 1979): over 20 people, "many of them research workers in vision", imagined a cube resting on a corner with the body diagonal vertical, and only **one** located the other corners. Most "assumed that there were four remaining corners" in a horizontal square; the correct answer is six corners in a zigzag at 1/3 and 2/3 of the height [Hinton]. Knowing what "cube" means did not make the derived facts available. |
| Euclid XI Def. 25: "a solid figure contained by six equal squares" [Euclid] | similarity (no size, position or orientation) | "solid", "square", "equal", "contained", which bottom out in undefined primitives |
| + edge length 10 mm | congruence (rigid motion, possibly reflection) | units and a metric |
| + frame: origin, axis directions, handedness, which corner sits where | identity (one point set) | the frame convention |
| an explicit vertex list (8 exact points) or a kernel call with every option stated | identity, by construction | the interpreter only |

Two real formal languages already disagree about what "cube" means by default:

- OpenSCAD `cube(10)` has `center = false` by default: "one corner at (0,0,0)", in "the first (positive) octant" [OpenSCAD].
- CadQuery `Workplane.box(10, 10, 10)` has `centered = True` by default: "the box will be centered around the reference point" [CadQuery].

Both are formal and deterministic, and they still produce different solids from the same intent. **Formality fixes
meaning only inside one interpreter. Across interpreters, every default must be stated.**

### 2.5 Verdict on Q1

- **Precise true version.** A finite structure is specified up to isomorphism (or up to a stated geometric equivalence)
  by a finite sentence in a shared vocabulary with fixed semantics. That fixes a formal target, not a
  model's ability to construct it. Supported geometric checks run under their declared domains and resource
  bounds; an arbitrary statement about geometry is not automatically within the implemented fragment.
- **False parts.**
  - "No matter who": the reader must share the primitives.
  - "This goes for everything": it fails for infinite objects in first-order logic, for incompressible objects, and for anything whose primitives are not mechanically fixed.
  - "Force conclusions": logic forces conclusions only *given* an interpretation and rules of inference that the reader already accepts (Quine's regress, Wittgenstein §201).

---

## 3. Q2 — What human communication research says about describing objects for reproduction

### 3.1 Referential communication: descriptions shrink, and the shrunk forms are private

- **Krauss & Weinheimer** (Psychonomic Science 1:113–114, 1964; JPSP 4:343–346, 1966) [KW64][KW66]. With repetition,
  reference phrases shrink. The widely cited example is "the one that looks like an upside-down martini glass in a wire
  stand", which becomes "martini" [snippet; papers not opened].
- **Clark & Wilkes-Gibbs** (Cognition 22:1–39, 1986) [CWG]. Eight pairs of Stanford students, a director and a matcher,
  arranged 12 tangram figures across six trials (576 placements).
  - Directors used "an average of 41 words per figure in trial 1 but only 8 words per figure in trial 6" (F(1,35) = 44.31, p < .001).
  - Turns per figure fell from 3.7 to about 1.
  - Trial 1 descriptions were indefinite and descriptive ("a person who's…"); later ones were definite labels ("the ice skater").
  - They proposed the **principle of least collaborative effort**: partners minimise their joint work, not each speaker's own.
- **Brennan & Clark** (JEP:LMC 22:1482–1493, 1996) [BC96]; summarised by Brennan (ISSD-96) [Brennan96].
  - Once a pair establishes a **conceptual pact**, speakers keep using it even when a shorter term would do: in "46-52% of the time" they reused the earlier, more specific term.
  - The pact is *partner-specific*. "Speakers with new addressees were more likely to switch to basic level terms."
- **Furnas, Landauer, Gomez & Dumais** (CACM 30(11):964–971, 1987) [Furnas].
  - Two people chose the same term for the same thing with probability under 0.20 (0.07–0.18).
  - Even with 20 synonyms per command, agreement reached only about 80% (as summarised in [Brennan96]).
- **Hawkins, Frank & Goodman** (Cognitive Science, 2020; arXiv 1912.07199) [Hawkins19]. Over 15,000 utterances: pairs
  reach "idiosyncratic but efficient and stable solutions"; "syntactic units drop out in clusters following positive feedback".
- **Garrod & Anderson** (Cognition 27:181–218, 1987) [GA87] and **Pickering & Garrod** (BBS 27:169–190, 2004) [PG04].
  In the maze game, pairs converge on a shared description scheme. The interactive alignment model explains convergence
  as priming at several levels at once [secondary; neither abstract opened].

**Implication for Symblic.** Readers may already share conventional vocabulary, but a fresh agent has not necessarily received a project's negotiated meanings. Carry task-specific definitions and their source/dependency context explicitly, then test transfer to readers that did not participate in defining them. This is a sufficiency experiment, not proof that a glossary captures every needed assumption.

### 3.2 Grounding and monitoring: interaction is what makes human instruction reliable

- **Clark & Brennan** (1991, *Perspectives on Socially Shared Cognition*, pp. 127–149) [CB91]. The grounding criterion:
  partners "mutually believe that the partners have understood what the contributor meant to a criterion sufficient for
  current purposes". The purpose and the medium change what grounding costs [secondary summary; PDF located at Stanford, not read in full].
- **Clark & Krych** (JML 50:62–81, 2004) [ClarkKrych] is the closest human analogue of the operator's experiment. A director
  instructed a builder to assemble 10 Lego models in three conditions: workspace visible, workspace hidden, or
  instructions recorded on audiotape (one-way, like a written paper).
  - Model errors were 5% when interactive and **39%** when non-interactive. Block errors were 0.8% (7/826) and 12.5% (74/590).
  - "Builders made eight times as many model errors, and 14 times as many block errors."
  - Variation between directors was "enormous": from 2 to all 10 models wrong. "The most accurate pair in the non-interactive condition was only as good as the least accurate pair in the interactive condition."
  - The worst director's tape gave a *second* builder about as many errors (9 models, 47% of blocks). "The directors are largely responsible for this variation." **The description, not the builder, carried the error.**
- **HCRC Map Task** (Anderson et al., Language and Speech 34(4), 1991) [MapTask]. 128 dialogues; a giver guides a
  follower along a route. The two maps differ by design: landmarks are absent from one map, renamed, or duplicated. Much
  of the dialogue is spent discovering that the assumed shared context is not shared.
- **Minecraft Collaborative Building** (Narayan-Chen, Jayannavar & Hockenmaier, ACL 2019) [MinecraftACL]. An Architect
  sees a target block structure and instructs a Builder by chat; the corpus has 509 dialogues. Generating architect
  instructions is "challenging".
- **LLMs as Builders.**
  - Kranti, Hakimov & Schlangen (2024) [Kranti]: best net-action F1 was 0.39 (GPT-4) and 0.33 (Llama-3-70B), against 0.21 for the earlier BAP baseline.
    - 75.42% of test utterances contain spatial prepositions, but code was correct for only 26.03% of them.
    - Shape references were handled correctly in 18.26% of cases, and anaphora (46.81% of utterances) in 25.53%.
    - Underspecified architect instructions were a separate error class.
  - Madge & Poesio (2024) [MadgePoesio]: builder accuracy was 37.6% for GPT-4 and 6.3% for Vicuna-13B; small models broke the response format.
- **IGLU** (Kiseleva et al. 2022) [IGLU, snippet]. The Builder may ask clarifying questions; the dataset has about 9,000 utterances and over 1,000 clarification questions.

### 3.3 Egocentrism and the curse of knowledge: writers overrate their own clarity

- **Keysar, Barr, Balin & Brauner** (Psychological Science 11:32–38, 2000) [Keysar00]. In eye tracking, addressees
  "considered objects as potential referents even when the speaker could not see those objects". People use an
  "egocentric heuristic" and then correct with mutual knowledge.
- **Keysar, Lin & Barr** (Cognition 89:25–41, 2003) [Keysar03]. Participants knew that the director could not know what
  was in a bag, yet "often took it as the referent of the director's description, sometimes even attempting to … [move]
  the bag itself".
- **Schober** (Cognition 47:1–24, 1993) [Schober].
  - Speakers set spatial perspective ("my left", "your right", "closer to both of us") differently with real partners than with imagined ones.
  - "Pairs varied idiosyncratically in the perspective-setting strategies they picked."
  - Speakers were "more explicit about whose perspective they were taking when they held the floor for only one description".
- **Camerer, Loewenstein & Weber** (JPE 97:1232–1254, 1989) [Camerer]. "Better-informed agents are unable to ignore
  private information even when it is in their interest to do so." Market forces reduced this curse of knowledge "by
  approximately 50 percent but do not eliminate it".
- **Newton** (1990, Stanford dissertation) [secondary, popularised by Heath & Heath]. Tappers predicted that listeners
  would recognise 50% of tapped songs; listeners recognised about 2.5% of 120.
- **Levinson** (*Space in Language and Cognition*, CUP 2003) [Levinson; not opened]. Languages and speakers differ in
  their default frame of reference: intrinsic, relative or absolute.

**Implication.** The author of a description is the worst judge of whether it is complete. Descriptions have to be
tested on readers who do not share the author's context.

### 3.4 Pragmatics: what readers add to the literal text

- **Grice** ("Logic and Conversation", 1975) [Grice; SEP-Impl]. The Cooperative Principle and four maxims:
  - Quantity: "be as informative as required";
  - Quality;
  - Relation: "be relevant";
  - Manner: "avoid obscurity and ambiguity, and strive for brevity and order".

  Conversational implicatures are cancellable. Scalar implicature ("some" implicates "not all") is a standing source of
  divergence: one reader takes the literal meaning, another the pragmatic one.
- **Relevance theory** (Wilson & Sperber 2004) [RT, not opened]. An utterance creates an expectation of *optimal*
  relevance. Hearers accept the first interpretation that is relevant enough for the effort spent.
- **Berry, Kamsties & Krieger**, *From Contract Drafting to Software Specification: Linguistic Sources of Ambiguity*
  (2003) [Berry].
  - "Unrecognized or unconscious disambiguation" is when a reader, "totally oblivious to other meanings", "takes [the first meaning that comes to mind] as the only meaning", and that meaning "may be entirely wrong".
  - The problem "is exacerbated if the author … is unavailable for questioning". That is the normal situation for a Symblic applicator.
  - Named hazards: "all", "each", "every"; the position of "only", "also" and "even"; and/or precedence; quantifier words; "that" vs "which"; pronouns referring to ideas.

### 3.5 Instruction design research

- **Agrawala et al.** (SIGGRAPH 2003) [Agrawala] and **Heiser et al.** (AVI 2004, pp. 311–319) [Heiser]. Studies of
  people producing and using TV-stand assembly instructions gave these principles:
  - step-by-step, with one diagram for each major step and "no steps … omitted";
  - a clear and explicit order;
  - parts added in each step visible;
  - mode of attachment visible;
  - action diagrams rather than structural ones;
  - arrows and guidelines;
  - "avoid changing viewpoints";
  - stable orientations.

  Results:
  - Instructions generated from these principles "significantly improve performance time by an average of 35% and reduce error rates by an average of 50%".
  - Mean errors were 0.5 with the computer-generated instructions, 0.6 with the factory instructions and 1.6 with hand-drawn ones.
  - Participants given an exploded view complained that "order of assembly operations was not explicitly depicted".
- **Novick & Morse** (Memory & Cognition 28:1242–1256, 2000) [NovickMorse]. 180 students folded origami from text only,
  text plus a final-state diagram, or text plus step-by-step and final-state diagrams. A final diagram helped as much as
  step diagrams only when the steps could easily be inferred from it. Otherwise it was no better than text alone.
  **A picture of the goal is not a substitute for the steps.**
- **LeFevre & Dixon**, "Do written instructions need examples?" (Cognition and Instruction 3:1–30, 1986) [LeFevreDixon].
  When the text and a worked example were deliberately made to contradict each other, learners followed the example
  [secondary description; paper not opened].
- **Eiriksdottir & Catrambone** (Human Factors 53:749–770, 2011) [EiriksdottirCatrambone]. There is "a trade-off between
  usability and learnability. Specific instructions help initial performance, whereas more general instructions … help
  learning and transfer." For good initial performance, "instructions should highly resemble the task at hand".
- **Dixon** (JVLVB 21:70–84, 1982; JEP:LMC 13:18–26, 1987; JML 26:24–35, 1987) [Dixon; not opened]. Readers build a
  hierarchical mental plan from written directions.

### 3.6 LLM-specific communication findings

- **Shaikh et al.** (NAACL 2024) [Shaikh]. "Compared to humans, LLMs generate language with less conversational grounding,
  instead generating text that appears to simply presume common ground." Preference-optimisation training *reduces* grounding acts.
- **Hua & Artzi** (COLM 2024) [HuaArtzi]. Multimodal LLMs understand increasingly concise references but "do not
  spontaneously make their own language more efficient". GPT-4 did so only "with heavy-handed prompting".
- **Hawkins et al.** (CoNLL 2020) [Hawkins20]. Neural language models "are not able to flexibly and interactively adapt
  those conventions on the fly as humans do".
- **AmbiEnt** (Liu et al., EMNLP 2023) [AmbiEnt]. GPT-4's generated disambiguations were judged correct "only 32% of the
  time … compared to 90%" for the dataset's human-written ones.
- **Sclar et al.** (ICLR 2024) [Sclar]. Prompt formatting changes caused "performance differences of up to 76 accuracy
  points" (LLaMA-2-13B). The effect persists with larger models, more few-shot examples and instruction tuning.
- **ClarifyGPT** (Mu et al., 2023 preprint) [ClarifyGPT]. Detecting ambiguity and asking clarifying questions raised
  GPT-4's Pass@1 from 70.96% to 80.80% on MBPP-sanitized, and from 68.02% to 75.75% averaged over four benchmarks.
- **Internal result** ([RESULTS.md](RESULTS.md) §2). Typed Symblic asks raised pairwise cross-agent identity from 62% to
  78% (94% without llama3.2:1b), while correctness stayed at 88%. Structure raises identity, not truth.

### 3.7 Verdict on Q2

- The hypothesis is the "audiotape condition", and in humans it is the high-error, high-variance condition: 39% vs 5%
  [ClarkKrych]. Variance is driven by the quality of the description, so better descriptions help.
- The cited communication experiments motivate feedback and repair under their tested conditions;
  they do not establish a near-zero error rate for people or models on arbitrary technical tasks.
- The cited LLM experiments report ambiguity, grounding and surface-form failures on their particular
  tasks; they do not supply one universal comparison with human communication.
- Symblic therefore needs a substitute for the feedback channel. Options:
  - mechanical checks of the result (invariants);
  - a typed "ambiguous" outcome instead of a silent guess;
  - pre-flight tests of descriptions on fresh agents.

---

## 4. Q3 — Controlled languages and engineering practice

### 4.1 ASD-STE100 Simplified Technical English

- **Origin and status** [STE-site]. Developed in the early 1980s as AECMA Simplified English for aviation maintenance
  manuals, because "80%" of airline customers' maintenance readers "are not native English speakers". Required by ATA
  i2200 and S1000D.
- **"One word – one meaning"** [STE-site]. "Start" was chosen over "begin", "commence", "initiate" and "originate". "To
  fall" means "to move down by the force of gravity", not "decrease". Each word has one part of speech. Company-specific
  "technical names" and "technical verbs" are allowed by rule.
- **Issue 9** (15 January 2025) [STE-site][tcworld]. 53 writing rules (31 refined), 555 dictionary entries updated; the
  dictionary has about 900 approved words [secondary].
- **Rules reported in secondary sources** [STE-wiki, secondary; the standard itself was not opened]:
  - at most 20 words per procedural sentence and 25 per descriptive sentence;
  - one instruction per sentence;
  - imperative, active voice;
  - no omitted articles;
  - noun clusters of at most three words;
  - at most six sentences per paragraph.
- **Evidence.**
  - Shubert, Spyridakis, Holmback & Coney (JTWC 25:347–369, 1995) [Shubert]: SE "significantly improved the comprehensibility of more complex documents", with essentially the same completion time [abstract via index].
  - Chervak, Drury & Ouellette (HFES 1996, pp. 303–307) [Chervak]: 175 practising aircraft maintenance technicians and 16 workcards. "Comprehension was significantly improved with Simplified English, particularly for the Difficult workcards and for non-native English speakers."
  - Chervak & Drury (Occupational Ergonomics, 2003) [ChervakDrury; snippet]: task errors fell with SE but rose with a *hybrid* version that mixed SE and original text.
  - An FAA language-error study (941 maintenance personnel) found errors were caught when the reader "asked for assistance or clarification" or "appeared perplexed", which relies on feedback from the recipient [ASW2007].

### 4.2 Logic-backed controlled languages

- **Attempto Controlled English** [ACE][ACE-IR]. A deterministic parse to DRS, FOL, OWL or TPTP using the fixed
  interpretation rules in §2.3. Kuhn classifies it P4 E3 N4 S3.
- **Kuhn's PENS classification** (Computational Linguistics 40(1):121–170, 2014; 100 English-based CNLs) [Kuhn].
  - **P4**, deterministically interpretable: "fully formal on the syntactic level"; each text maps to one formal representation "or a small set of all possible representations", which "may be underspecified" and need background axioms.
  - **P5**, fixed semantics: "Each text has exactly one meaning, which can be automatically derived … without the help of heuristics or external resources."
  - "The perfect class P5 E5 N5 S5" (fully precise, expressive, natural and simple) is "practically impossible".
  - **This is the most direct evidence against a perfectly natural *and* perfectly determining language.** Every CNL trades naturalness for precision.
- **Logical English** (Kowalski & Datoo, AI and Law 30:163–197, 2021) [LogicalEnglish]. Sentences come from declared
  templates, nouns mark typed variables, pronouns are disallowed, and programs compile to Prolog or ASP. In one 2026
  traffic-rule study it did not beat direct translation (see [PRIOR-ART.md](PRIOR-ART.md) §4).
- **Grammatical Framework** (Ranta, JFP 14(2):145–189, 2004) [GF]. One abstract syntax (a logical framework) with several
  concrete syntaxes, used for both parsing and generation. One meaning can have many surface renderings, all generated
  from the same tree. This is the right model for Symblic: one canonical abstract statement, many renderings.

### 4.3 Requirements engineering

- **EARS** (Mavin, Wilkinson, Harwood & Novak, IEEE RE'09; Rolls-Royce) [EARS]. Generic order: "While <precondition>,
  when <trigger>, the <system name> shall <system response>". Patterns: ubiquitous, state-driven (While), event-driven
  (When), optional feature (Where), unwanted behaviour (If … then), and complex. Claimed to reduce "or even eliminate"
  common natural-language requirement problems. Users include Airbus, Bosch, Honeywell, Intel, NASA and Rolls-Royce
  [vendor page; no controlled study opened].
- **RFC 2119 and RFC 8174 (BCP 14)** [RFC2119][RFC8174].
  - MUST means "an absolute requirement"; SHOULD means valid reasons to deviate may exist "but the full implications must be understood"; MAY means "truly optional".
  - The keywords should be used "sparingly", only "where it is actually required for interoperation or to limit behavior which has potential for causing harm" (RFC 2119 §6).
  - RFC 8174 adds that the words have these meanings "only when they are in all capitals".
- **NASA Systems Engineering Handbook, Appendix C** [NASA-C].
  - "Shall" means a requirement, "will" a fact or declaration of purpose, and "should" a goal.
  - One requirement per statement.
  - Requirements must be free of indefinite pronouns ("this", "these") and of terms such as "as appropriate", "etc.", "and/or" and "but not limited to".
  - Requirements must be "complete with tolerances".
  - Terms to avoid include "flexible, easy, sufficient, safe, ad hoc, adequate, accommodate, user-friendly, usable, when required, if required, appropriate, fast, portable, light-weight, small, large, maximize, minimize, robust, quickly, easily, clearly".
- **INCOSE Guide to Writing Requirements**, v4 (2023) [INCOSE; secondary]. Characteristics of a requirement:
  necessary, appropriate, unambiguous ("can be interpreted in only one way"), complete, singular, feasible, verifiable,
  correct and conforming. The rules include defining every term, avoiding vague terms and escape clauses, one thought
  per statement, and consistent units. Rule numbers are not given here because the guide was not opened (vendor pages
  number them differently).
- **ISO/IEC/IEEE 29148:2018** [ISO29148; not opened]. Uses similar characteristics: unambiguous, complete, singular,
  feasible, verifiable, traceable.

### 4.4 Operational practice

- **Flight-deck checklists** (Degani & Wiener, NASA CR 177549, 1990; NTRS ARC-12823; Human Factors 35:345–359, 1993)
  [DeganiWiener]. Their analysis covers function, format, length and use. Checklist problems recur in marine, nuclear and
  chemical-process work [abstract only; detailed recommendations not opened].
- **Five-paragraph operations order and commander's intent** [OPORD; secondary].
  - The order has five paragraphs: Situation, Mission, Execution, Sustainment, Command and Signal.
  - The Execution paragraph begins with the commander's intent, "a clear and concise expression of the purpose of the operation and the desired military end state". It lets subordinates "act to achieve the commander's desired results without further orders, even when the operation does not unfold as planned".
  - Doctrine: ADP 6-0 [secondary; Army publications site blocked automated fetch].
  - Lesson: militaries do not try to anticipate every case. They state purpose and end state so that a reader can resolve the unforeseen consistently.
- **Plain-language drafting.** The federal guideline "use *must*, not *shall*" could not be verified: the old page now
  redirects to a digital.gov landing page [not verified]. NASA's shall/will/should definitions and RFC 8174's
  capitals-only rule are the verified equivalents.

### 4.5 Laboratory protocols

- **Reproducibility Project: Cancer Biology** (Errington, Denis, Perfito, Iorns & Nosek, eLife 2021) [Errington].
  - "None of the 193 experiments were described in sufficient detail in the original paper to enable us to design protocols to repeat the experiments."
  - Key reagents were requested for 136 of 193 experiments (70%).
  - Authors were not at all helpful, or did not respond, for 61 experiments (32%).
  - 67% of the registered experiments needed modification; only 50 of 193 (26%) were completed [ErringtonMain].
- **Vasilevsky et al.** (PeerJ 1:e148, 2013) [Vasilevsky]. "54% of resources are not uniquely identifiable in
  publications, regardless of domain, journal impact factor, or reporting requirements."
- **protocols.io** (Teytelman et al., PLoS Biology 2016) [Teytelman]. Know-how "frequently remains restricted to the
  research group that developed the method". The platform responds with runnable step-by-step protocols, immutable
  versions, forks and DOIs.

### 4.6 Formal specification

- **TLA+** [TLA]: "the best way to describe things precisely is with simple mathematics", checked with the TLC model checker and the TLAPS proof system.
- **AWS** (Newcombe et al., CACM 58(4):66–73, 2015) [AWS]. TLA+ was used on 10 large systems and found bugs needing traces of 35 steps.
  - Prose design documents "are often ambiguous, or omit critical aspects such as partial failure or the granularity of concurrency".
  - "We need all of the engineers to have the same mental model … talk and design documents can be ambiguous or incomplete … a formal specification is precise, short, and can be explored and experimented upon with tools."
- **Alloy** [Alloy]: "An Alloy model is a collection of constraints that describes (implicitly) a set of structures", and its analyzer "finds structures that satisfy them".
  - **This is the right test of the operator's hypothesis. A description is "perfect" for an object exactly when its set of models, up to the stated equivalence, has one element. A solver can count the models in a bounded scope.**
- **Z (ISO/IEC 13568:2002), VDM (ISO/IEC 13817-1) and the B-Method (Abrial 1996)** [not opened]: standardised model-based notations with fixed semantics.
- **Specification by Example** (Adzic, Manning 2011) [Adzic]: realistic examples serve as "living, reliable documentation" that is continuously checked against behaviour.
- **Gherkin** (Cucumber) [Gherkin]. Given describes "the initial context", When "an event, or an action", and Then "an expected outcome".
  - However, "keywords are not taken into account when looking for a step definition".
  - **The natural-language step means nothing until code binds it.** The meaning lives in the step definitions, which is the "shared interpreter" point made concrete.

### 4.7 Geometry and generative description

- **Representation schemes for solids** (Requicha, ACM Computing Surveys 12(4):437–464, 1980) [Requicha; metadata
  checked, text not opened]. The standard properties of a representation are domain, validity, unambiguity
  (completeness: a representation denotes one solid) and uniqueness (a solid has one representation). CSG is generally
  described as unambiguous but not unique. For Symblic: many texts may denote one cube, which is acceptable, but no text
  may denote two cubes.
- **OpenSCAD and CadQuery** [OpenSCAD][CadQuery]: the conflicting cube defaults described in §2.4.
- **STEP, ISO 10303** [not opened]: the exchange standard for exact product geometry.
- **L-systems** ([PRIOR-ART.md](PRIOR-ART.md) §10, [ABOP]). "All plants generated by the same deterministic L-system are
  identical". Stochastic L-systems vary with the seed, and the turtle parameters are part of the specification.
- **Shape grammars** (Stiny & Gips, IFIP 1971/72, "Shape grammars and the generative specification of painting and
  sculpture") [not verified; Crossref found only Stiny's related 1975 chapter]. Rule-based generation of designs from an
  initial shape.

### 4.8 Verdict on Q3

Every field that needs "anyone reads it the same way" uses the same small set of tools:

- a closed vocabulary with one meaning per word;
- one action per statement;
- fixed templates;
- explicit units, tolerances and frames;
- banned vague words;
- unique identifiers for external resources;
- verifiable end states;
- a channel for questions.

Controlled-language studies support improvements under particular experimental conditions, not a
universal effect size. Executable semantics give a formal target for TLA+ checks, Gherkin steps or
CAD kernels; actual behavior still depends on the supplied model, implementation and successful
execution. Neither a formal target nor better prose forces a model to construct the intended result.

---

## 5. Q4 — How much must be said to fix an object?

- **Kolmogorov complexity** (Kolmogorov 1965; Solomonoff 1964; Chaitin 1969; Li & Vitányi) [Kolmogorov; secondary].
  - The invariance theorem: for two universal description languages, |K₁(s) − K₂(s)| ≤ c, where c is the length of an interpreter for one written in the other, "regardless of the object".
  - K is uncomputable.
  - Consequences for the hypothesis:
    - A description is short only *relative to an interpreter*. For a reader who "knows nothing", the description must include the interpreter (the constant c), and the interpreter must itself be written in something the reader already runs. This is the information-theoretic form of Quine's regress.
    - Most strings are incompressible, so some objects have no description shorter than a full listing.
    - No procedure finds the shortest description in general.
- **Minimum Description Length** (Rissanen, Automatica 14:465–471, 1978) [Rissanen]: the practical form, which trades model length against data length.
- **Referring expressions: how much to say.**
  - Dale & Reiter (Cognitive Science 19(2), 1995) [DaleReiter].
    - Finding the shortest distinguishing description ("Full Brevity") is NP-hard.
    - Humans do not use it: "Human speakers in many cases include unnecessary modifiers", for example "the white bird" when "the bird" suffices.
    - The Incremental Algorithm adds attributes in a preferred order.
  - Pechmann (Linguistics 27:89–110, 1989) [Pechmann]: eye tracking links over-specification to incremental speech production.
  - Engelhardt, Bailey & Ferreira (JML 54:554–573, 2006) and Koolen et al. (J. Pragmatics 43:3231–3250, 2011): further studies of over-specification [metadata checked; not opened].
  - Degen, Hawkins, Graf, Kreiss & Goodman (Psychological Review 127:591–621, 2020) [Degen]. "Reference is usefully redundant". A continuous-semantics RSA model explains why colour is over-specified more than size, and why atypical features increase modification.
  - Rubio-Fernández (Frontiers in Psychology 7:153, 2016) [RubioFernandez]. Redundant colour adjectives "facilitate object identification". English speakers produced them more than Spanish speakers (0.95 vs 0.59 in polychrome displays), which is linked to adjective position.
  - Frank & Goodman (Science 336:998, 2012) [FrankGoodman]. A model in which speakers are informative and listeners use Bayesian inference fits referential-game judgments "close, parameter-free".
- **The cube as a reference object.**
  - Shepard & Metzler (Science 171:701–703, 1971) [ShepardMetzler]: objects built from 10 cubes. The time to judge that two drawings show the same object rises linearly with the angle between them.
  - Hinton (1979) [Hinton]: §2.4 above. "The psychologically relevant measure of complexity would then depend on how the cube was represented rather than on its objective properties alone."

**Verdict on Q4.** The length needed is set by what the reader's interpreter already contains. Against a CAD kernel,
`cube(10, center=false)` is complete. Against a reader that knows nothing, no finite length is enough. Redundancy is
not waste. A second, independent statement of the same fact (coordinates *and* edge lengths) lets a reader or a checker
detect misreadings. Human speakers add such redundancy spontaneously, and listeners benefit from it.

---

## 6. Design rules for Symblic

These are authoring proposals, not additional parser requirements or claims that every rule is implemented. Formal syntax needs exact interpretation; prose can remain expressive when explicitly separated from that syntax. Sources motivate experiments, not universal bans on ordinary language. Current implemented contracts are in [SPEC.md](SPEC.md) and [REFORM-3.md](REFORM-3.md).

1. **Fix the interpreter, not just the text.** Every primitive is either executed by the kernel or defined in the
   program in terms of kernel primitives. Undefined formal names must be diagnosed; explicitly marked prose instructions remain model-interpreted and need separate fidelity checks.
   [Kolmogorov invariance][Wittgenstein §201][Harnad][Gherkin: keywords are not used for matching]
2. **Explicit formal vocabulary and aliases.** Declare project terms and resolve aliases to the same formal identifier. Flag conflicting definitions; do not ban synonyms in human explanations. [STE][Furnas: two people chose the same term with p < 0.20]
3. **Define every term once, before use, inside the program.** Never rely on a label negotiated with an earlier
   applicator. Conceptual pacts are partner-specific and do not transfer to a fresh agent. [BC96][Hawkins19][INCOSE]
4. **Keep each step focused and dependency-complete.** Split independently checkable requirements where useful, but retain needed conditions, exceptions and definitions. A 20-word authoring warning can be optional; it is not a correctness bound. Choose granularity using held-out quality and total cost. [STE 20-word rule][NASA one requirement][INCOSE singular][Heiser one step per diagram]
5. **Fixed templates with keyword-marked conditions and capitals-only modal words.** Use `while … when … if … then … must`,
   EARS-style. MUST, SHOULD and MAY carry meaning only in capitals. [EARS][RFC2119][RFC8174][NASA shall/will/should]
6. **Publish and enforce deterministic interpretation rules.** Fix the parse, not just the string: quantifier scope by
   textual order, and/or precedence, collective plurals with `each` marking the distributive reading, and attachment.
   [ACE-IR][SEP-Montague]
7. **Resolve references explicitly.** Repeat names or use a documented scope/resolution rule; flag unresolved pronouns rather than banning all anaphora. One cited LLM-builder study reported 25.5% correct anaphora resolution, not a universal rate.
   [Kranti][NASA][LogicalEnglish][SEP-DRT]
8. **State the reference frame for every spatial statement:** origin, axis directions, handedness, units and the
   viewpoint, if any. Never say left, right, above or front without a frame; use coordinates. [Schober][Levinson][Kranti: 26% on spatial prepositions][Hinton][ShepardMetzler]
9. **State every default.** For example, `cube(10, center=false)` or "corner at origin, edges along +x, +y, +z". Never
   rely on a library's default, because formal languages disagree. [OpenSCAD vs CadQuery]
10. **Exact numbers, explicit units and tolerances on every quantity.** Prefer exact rationals or decimals; give ± or
    ≤/≥ tolerances where measurement is involved. [NASA tolerances][INCOSE units][SPEC exact decimals]
11. **Quantify explicitly and avoid implicature triggers.** Write `exactly 6`, `each`, `at least 1`. Avoid bare "some",
    "all", "any", floating "only", and "and/or". Scalar implicature ("some" read as "not all") divides literal readers
    from pragmatic ones. [Berry][SEP-Impl]
12. **Lint unmeasured acceptance criteria.** If adequate, robust, fast or small determines acceptance, request an operational definition or a declared judgment outcome. Keep descriptive prose and precise adverbs such as "exactly"; spelling is not a semantic verifier. [NASA-C][INCOSE]
13. **State the target equivalence:** `identical`, `congruent` (up to rigid motion), `similar` or `isomorphic`. A
    description is complete only relative to its stated equivalence. [Dawar][Euclid fixes the cube only up to similarity]
14. **Give both the steps and the checkable end state.** Steps alone accumulate silent errors. A goal alone works only
    when the steps are easy to infer. Write the end state as kernel `ensure` invariants, for example: 8 vertices, 12
    edges of length 10, all face angles 90°. [NovickMorse][Heiser][OPORD intent and end state][Gherkin Then][INCOSE verifiable]
15. **Every worked example is mechanically checked against the rules.** Readers follow the example when example and
    text conflict, so an inconsistent example silently wins. [LeFevreDixon][Adzic]
16. **Prefer closed answer types and canonical forms:** enums, booleans, integers, rationals, declared atoms, vertex
    lists. Canonicalise before comparing. [Kuhn P5][Sclar][RESULTS.md: typed asks 62%→78% identity]
17. **Add deliberate redundancy as cross-checks.** Give the same fact in two independent forms, such as coordinates and
    edge lengths, or a count and a list, and let the kernel verify that they agree. [Degen][RubioFernandez][DaleReiter]
18. **Each judgment statement states its purpose and acceptable end state, not only the action,** so that unforeseen
    cases are resolved consistently. [OPORD commander's intent, secondary][Grice relation]
19. **Pin every external resource by a unique identifier, version and hash:** model IDs, datasets, files, kernel
    version. [Vasilevsky: 54% of resources unidentifiable][Errington: 0/193][Teytelman versioning]
20. **Give the applicator a typed way to say "ambiguous" or "underdetermined", and treat it as a result, not a
    failure.** LLMs presume common ground unless they are made to do otherwise. [ClarkKrych][Shaikh][ClarifyGPT +7.7–9.8 points][Berry: author unavailable][ASW2007]
21. **Test important descriptions on fresh readers.** Compare canonical results and independently judged correctness on a predeclared panel. Record model families without assuming their errors are independent. Reader failure and specification failure are competing explanations; agreement alone identifies neither. [Camerer][Newton, secondary][Keysar03][ClarkKrych: the worst director's tape failed a second builder]
22. **Check uniqueness mechanically where possible.** For finite or bounded descriptions, ask a solver how many models
    satisfy the statements up to the stated equivalence. More than one means the description underdetermines its
    object within the searched scope; zero means inconsistent within that scope. Report bounds and timeouts. Some geometric encodings reduce to decidable real-closed-field formulas; arbitrary geometry or English does not. Tasks may intentionally allow several correct artifacts, so uniqueness is required only when the stated outcome requires identity. [Alloy][Dawar][Tarski-ax]
23. **Do not mix controlled and free language in one statement.** Prose is allowed only in explicitly marked
    instruction strings, never inside the formal part. [ChervakDrury hybrid, snippet][Kuhn]
24. **Render each statement in one canonical surface form before sending it to any applicator,** in GF style: one
    abstract statement and one rendering. Formatting alone moved accuracy by up to 76 points. [Sclar][GF]
25. **Specify both local work and its purpose.** Measure the tradeoff between detailed steps, useful abstraction and fresh-reader success. A model may construct a proof, program or decomposition; the host checks the declared obligations rather than requiring all solutions to be hand-coded kernel operations. [EiriksdottirCatrambone][Heiser]

---

## 7. Experiment designs

Common protocol for all five experiments:

- **Applicators:** the [RESULTS.md](RESULTS.md) set (Claude Haiku/Sonnet/Opus, Codex, agy, qwen3:4b, llama3.2:1b), each in a fresh context per item, with 5 samples per applicator per item.
- **Comparison:** outputs are canonicalised and fingerprinted. Report pairwise identity, unanimity and chance-corrected agreement (Fleiss' κ or Krippendorff's α) with bootstrap 95% CIs.
- **Correctness:** reported separately against ground truth computed by the kernel, because agreement is not correctness ([PRIOR-ART.md](PRIOR-ART.md) §12.7).
- **Pre-registration:** register predictions before running.

### E1. The cube ladder: does formality buy identity, and where does it stop?

- **Items.** Five description levels for the same object, an axis-aligned cube of edge 10 mm with one corner at the
  origin:
  - L0: "a cube of side 10 mm".
  - L1: Euclid's definition plus size.
  - L2: STE-style prose with frame and units.
  - L3: Symblic statements with a frame, stated defaults and `ensure` invariants.
  - L4: a kernel call with every option explicit.
- Add three harder targets:
  - the Hinton pose: resting on a vertex, body diagonal vertical;
  - a 10-cube Shepard–Metzler polycube;
  - a cube with one edge chamfered by a stated amount.
- **Task.** Output 8 vertex coordinates (or a polycube voxel list) as canonical JSON.
- **Measures:**
  - exact identity after canonicalisation;
  - which equivalence class the output reaches (identical, congruent, similar, not a cube);
  - invariant pass rate (edge lengths, right angles, vertex count);
  - Chamfer and Hausdorff distance to ground truth;
  - for the Hinton pose, whether vertex heights are 1/3 and 2/3 of the diagonal.
- **Solver check.** Where a finite faithful encoding is supplied, count admitted candidates up to the
  declared equivalence. Record encoding assumptions and bounded scope; this is not a generic model count
  for arbitrary prose or an infinite geometric domain.
- **Predictions:**
  - Test whether additional specification raises fresh-construction identity; monotonicity is a hypothesis,
    since added complexity can also impede a model. L4 has two different conditions: direct kernel
    execution and a model asked to construct the explicit call. Only the former fixes the calculation.
  - Measure which equivalence classes L0–L1 actually reach rather than presuming correctness up to scale.
  - Test whether the Hinton pose produces more failures at L0–L2 for the chosen small models.
  - Compare bounded solution multiplicity with observed agreement. A unique admitted value does not
    guarantee construction success, and a solver count does not determine a model's output distribution.
- **Tests:** the core hypothesis directly, and rules 8, 9, 13, 14 and 22.

### E2. Tangram conventions across agent populations

- **Task.** A director agent and a matcher agent play six rounds of a 12-figure tangram (or abstract polygon) matching
  game, as in Clark & Wilkes-Gibbs. Figures are given to the director as images (multimodal models) or as exact polygon
  coordinates (text models).
- **Phase 1.** Same-family pairs. Measure words per figure by round (human baseline: 41 falling to 8), turns per figure
  and accuracy.
- **Phase 2, transfer.** Give the round-6 labels to a *new* matcher from another family with no history (Brennan &
  Clark's partner switch). Measure the accuracy drop.
- **Phase 3, exported pact.** The director must also write a glossary that defines each label in a closed vocabulary.
  Give the label plus glossary to fresh matchers. Measure recovery.
- **Predictions:**
  - Phase 1: LLM directors shorten less than humans unless prompted [HuaArtzi].
  - Phase 2: accuracy falls sharply.
  - Phase 3: much of the drop is recovered.
- **Tests:** whether conventions must be explicit and in the program (rule 3), and whether cross-population identity
  requires a written pact.

### E3. One-way build instructions: free prose vs STE vs Symblic, with and without feedback

- **Task.** Writer agents produce build instructions for 20 voxel structures, as in the Minecraft Collaborative Building
  Task, in four styles:
  - free prose;
  - STE-style prose (20-word sentences, one action each, closed vocabulary);
  - a *hybrid* mixing STE and free prose;
  - Symblic statements with frame and invariants.

  Builder agents of every family execute the instructions.
- **Two channel conditions:**
  - one-way, the "audiotape" condition;
  - builders may return a typed clarification question, answered once by the writer.
- **Measures:**
  - model errors (structure not identical) and block errors (per-block precision and recall, net-action F1), in Clark & Krych's units;
  - variance between writers, testing whether the description or the builder carries the error by re-running the worst writer's text with fresh builders;
  - tokens and time.
- **Predictions:**
  - Symblic < STE < free prose for one-way errors.
  - The hybrid does worse than STE [ChervakDrury].
  - Clarification narrows the gap, as in the 5% vs 39% human result.
  - Between-writer variance dominates between-builder variance.
- **Tests:** rules 4, 5, 20 and 23, and the "perfect paper, no questions" form of the hypothesis.

### E4. Ambiguity audit: interpretation entropy and the effect of deterministic rules

- **Items.** 120 short statements, 10 for each of 12 known ambiguity types:
  - quantifier scope;
  - PP attachment;
  - and/or precedence;
  - "only" placement;
  - scalar "some";
  - collective vs distributive plurals;
  - pronoun reference;
  - left/right without a frame;
  - library defaults (cube centre);
  - units omitted;
  - vague adjectives;
  - "the X" with two Xs in context.

  Sources: [Berry], [AmbiEnt], [ACE-IR]. Each item has a closed set of readings.
- **Conditions:**
  - plain;
  - plain plus a preamble stating ACE-style interpretation rules;
  - Symblic-parsed, so that the parser either rejects the item or fixes one reading;
  - each condition in three surface formats with identical content.
- **Measures:**
  - entropy of the chosen readings across applicators;
  - the rate at which applicators *flag* ambiguity unprompted [Shaikh];
  - format sensitivity, measured as the change in the reading distribution across surface variants [Sclar].
- **Predictions:**
  - Plain items show high entropy and a low flag rate.
  - The preamble helps large models and not small ones.
  - Parser enforcement drives entropy to zero for the types it covers and exposes the rest as rejections.
- **Tests:** rules 6, 7, 11, 12 and 24, and how far "write it carefully" goes without mechanical enforcement.

### E5. Curse of knowledge and the cold-reader loop

- **Task.**
  1. Writer agents see a random target: a polycube of 6–12 unit cubes, or a small labelled graph. They write a
     description and *predict* the fraction of fresh readers who will reconstruct it exactly.
  2. Readers from all families reconstruct it.
  3. In a second condition, the writer revises its description until two fresh readers from different families
     produce identical, correct reconstructions, with a cap of 3 revisions.
- **Measures:**
  - calibration gap, predicted minus actual success: the Newton and Camerer analogue;
  - success against description length, giving an empirical MDL curve;
  - the effect of the loop on new held-out readers;
  - the effect of redundancy: descriptions with and without an extra invariant, such as a vertex count or bounding box.
- **Predictions:**
  - Writers are overconfident.
  - Success rises with length and then plateaus.
  - Redundancy raises success at a fixed number of revisions.
  - The loop generalises to held-out readers better than a single high-effort write.
- **Tests:** rules 17, 21 and 22, and whether "a perfectly written paper" can be reached by an automated process rather
  than by authorial skill.

---

## 8. What this means for Symblic now (mapping to [SPEC.md](SPEC.md))

The following list records the original survey's gap assessment, not a fresh absence audit. The 2.5 reform adds explicit execution profiles, context manifests, typed abstention, proof checking, finite uniqueness/countermodel outcomes and candidate-versus-adopted rewrite records; consult [REFORM-3.md](REFORM-3.md). The remaining experiments include source-linked context sufficiency, fresh-reader transfer of project definitions, fidelity-preserving clarification and equivalence checks for additional artifact domains. A passing finite test suite must not be relabeled general program equivalence.

- **Already aligned:**
  - the kernel decides what is decidable (rule 1);
  - typed `ask`s give closed answers (rule 16);
  - `ensure` and `assert` give checkable end states (rule 14);
  - exact decimals (rule 10);
  - context capsules (rule 3, partly).
- **Gaps the research points to:**
  - a parser-level vocabulary and vague-word lint (rules 2, 12);
  - deterministic interpretation rules for the prose inside `ask` strings, or a lint that flags pronouns, frames and quantifiers (rules 6–8, 11);
  - an `ambiguous` outcome on every ask (rule 20);
  - a canonical renderer for capsules (rule 24);
  - a uniqueness checker for drawings and structures (rule 22);
  - a cold-reader pre-flight that runs a statement on two fresh applicators before a long run (rule 21).
- **Claims to make:**
  - "Identical by construction for kernel statements."
  - "Agreement is measured for interpreted statements."
  - "Descriptions are verified against stated invariants and tested on fresh readers."
- **Claims not to make:** "any agent who knows nothing reproduces any object from a perfect paper".

---

## 9. References

### Logic and philosophy of language
- [Dawar] Dawar, A. *Model Theory on Finite Structures* (lecture notes, Univ. of Wales Swansea). https://www.cl.cam.ac.uk/~ad260/talks/fmt-swansea1.pdf
- [SEP-FOMT] Hodges, W. & Scanlon, T. "First-order Model Theory", SEP, rev. 2024-01-25. https://plato.stanford.edu/entries/modeltheory-fo/
- [SEP-HOL] "Second-order and Higher-order Logic", SEP, rev. 2024-08-31. https://plato.stanford.edu/entries/logic-higher-order/
- [SEP-Skolem] Bays, T. "Skolem's Paradox", SEP, rev. 2025-02-05. https://plato.stanford.edu/entries/paradox-skolem/
- [Putnam] Putnam, H. "Models and Reality", J. Symbolic Logic 45(3):464–482, 1980. https://www.jstor.org/stable/2273415 [not opened]
- [Tarski-ax] "Tarski's axioms", Wikipedia [secondary]. https://en.wikipedia.org/wiki/Tarski%27s_axioms ; Tarski & Givant, "Tarski's System of Geometry", Bull. Symbolic Logic 5(2), 1999 [not opened]
- [SEP-Witt] "Ludwig Wittgenstein", SEP, rev. 2026-09-17. https://plato.stanford.edu/entries/wittgenstein/
- [IEP-Kripke] "Kripke's Wittgenstein", Internet Encyclopedia of Philosophy. https://iep.utm.edu/kripkes-wittgenstein/ ; Kripke, *Wittgenstein on Rules and Private Language*, Harvard UP 1982 [not opened]
- [SEP-Quine] Hylton, P. "Willard Van Orman Quine", SEP, rev. 2023-07-06. https://plato.stanford.edu/entries/quine/
- [SEP-Goodman] Cohnitz, D. & Rossberg, M. "Nelson Goodman", SEP, rev. 2024-02-08. https://plato.stanford.edu/entries/goodman/
- [SEP-Davidson] Malpas, J. "Donald Davidson", SEP, rev. 2023-04-28. https://plato.stanford.edu/entries/davidson/
- [SEP-Conv] "Convention", SEP, rev. 2024-02-22. https://plato.stanford.edu/entries/convention/
- [Harnad] Harnad, S. "The Symbol Grounding Problem", Physica D 42:335–346, 1990. https://arxiv.org/abs/cs/9906002
- [BenderKoller] Bender, E. & Koller, A. "Climbing towards NLU", ACL 2020, pp. 5185–5198. https://aclanthology.org/2020.acl-main.463/
- [PiantadosiHill] Piantadosi, S. & Hill, F. "Meaning without reference in large language models", 2022. https://arxiv.org/abs/2208.02957
- [SEP-Montague] Janssen, T. & Zimmermann, T. E. "Montague Semantics", SEP, rev. 2025-02-05. https://plato.stanford.edu/entries/montague-semantics/
- [SEP-DRT] "Discourse Representation Theory", SEP. https://plato.stanford.edu/entries/discourse-representation-theory/
- [SEP-Desc] "Descriptions", SEP, rev. 2022-09-21. https://plato.stanford.edu/entries/descriptions/
- [Wadler] Wadler, P. "Propositions as Types", CACM 58(12):75–84, 2015. https://doi.org/10.1145/2699407
- [Euclid] Euclid, *Elements* XI Def. 25 (Joyce ed.). https://mathcs.clarku.edu/~djoyce/elements/bookXI/defXI25.html

### Human communication and instructions
- [KW64] Krauss, R. & Weinheimer, S. Psychonomic Science 1:113–114, 1964. https://doi.org/10.3758/BF03342817 [not opened]
- [KW66] Krauss, R. & Weinheimer, S. JPSP 4:343–346, 1966. https://doi.org/10.1037/h0023705 [not opened]
- [CWG] Clark, H. & Wilkes-Gibbs, D. "Referring as a collaborative process", Cognition 22:1–39, 1986. https://web.stanford.edu/~clark/1980s/Clark.Wilkes-Gibbs.86.pdf
- [BC96] Brennan, S. & Clark, H. "Conceptual pacts and lexical choice in conversation", JEP:LMC 22:1482–1493, 1996. https://doi.org/10.1037/0278-7393.22.6.1482
- [Brennan96] Brennan, S. "Lexical entrainment in spontaneous dialog", ISSD-96, pp. 41–44. https://www.cs.columbia.edu/~julia/papers/brennan96.pdf
- [Furnas] Furnas, G. et al. "The vocabulary problem in human-system communication", CACM 30(11):964–971, 1987. https://doi.org/10.1145/32206.32212
- [Hawkins19] Hawkins, R., Frank, M. & Goodman, N. "Characterizing the dynamics of learning in repeated reference games". https://arxiv.org/abs/1912.07199
- [GA87] Garrod, S. & Anderson, A. Cognition 27:181–218, 1987. https://doi.org/10.1016/0010-0277(87)90018-7 [not opened]
- [PG04] Pickering, M. & Garrod, S. BBS 27:169–190, 2004. https://doi.org/10.1017/S0140525X04000056 [not opened]
- [CB91] Clark, H. & Brennan, S. "Grounding in communication", 1991. https://doi.org/10.1037/10096-006
- [ClarkKrych] Clark, H. & Krych, M. "Speaking while monitoring addressees for understanding", JML 50:62–81, 2004. https://doi.org/10.1016/j.jml.2003.08.004
- [MapTask] HCRC Map Task design. https://groups.inf.ed.ac.uk/maptask/maptask-description.html ; Anderson et al., Language and Speech 34(4), 1991
- [MinecraftACL] Narayan-Chen, A., Jayannavar, P. & Hockenmaier, J. ACL 2019, pp. 5405–5415. https://aclanthology.org/P19-1537/
- [Kranti] Kranti, C., Hakimov, S. & Schlangen, D. 2024. https://arxiv.org/abs/2406.17553
- [MadgePoesio] Madge, C. & Poesio, M. "Large Language Models as Minecraft Agents", 2024. https://arxiv.org/abs/2402.08392
- [IGLU] Kiseleva, J. et al. 2022. https://arxiv.org/abs/2205.02388 [snippet]
- [Keysar00] Keysar, B. et al. Psychological Science 11:32–38, 2000. https://doi.org/10.1111/1467-9280.00211
- [Keysar03] Keysar, B., Lin, S. & Barr, D. Cognition 89:25–41, 2003. https://doi.org/10.1016/S0010-0277(03)00064-7
- [Schober] Schober, M. "Spatial perspective-taking in conversation", Cognition 47:1–24, 1993. https://doi.org/10.1016/0010-0277(93)90060-9
- [Camerer] Camerer, C., Loewenstein, G. & Weber, M. JPE 97:1232–1254, 1989. https://doi.org/10.1086/261651
- [Levinson] Levinson, S. *Space in Language and Cognition*, CUP 2003. https://doi.org/10.1017/CBO9780511613609 [not opened]
- [Grice] Grice, H. P. "Logic and Conversation", 1975. https://doi.org/10.1163/9789004368811_003 ; [SEP-Impl] "Implicature", SEP, rev. 2024-01-10. https://plato.stanford.edu/entries/implicature/
- [RT] Wilson, D. & Sperber, D. "Relevance Theory", 2004. https://www.phon.ucl.ac.uk/publications/WPL/02papers/wilson_sperber.pdf [not opened]
- [Berry] Berry, D., Kamsties, E. & Krieger, M. *From Contract Drafting to Software Specification: Linguistic Sources of Ambiguity*, 2003. https://cs.uwaterloo.ca/~dberry/handbook/ambiguityHandbook.pdf
- [Agrawala] Agrawala, M. et al. SIGGRAPH 2003. https://graphics.stanford.edu/papers/assembly_instructions/
- [Heiser] Heiser, J. et al. AVI 2004, pp. 311–319. https://doi.org/10.1145/989863.989917
- [NovickMorse] Novick, L. & Morse, D. Memory & Cognition 28:1242–1256, 2000. https://doi.org/10.3758/BF03211824
- [LeFevreDixon] LeFevre, J. & Dixon, P. Cognition and Instruction 3:1–30, 1986. https://doi.org/10.1207/s1532690xci0301_1 [finding via secondary]
- [Dixon] Dixon, P. JVLVB 21:70–84, 1982. https://doi.org/10.1016/S0022-5371(82)90456-X [not opened]
- [EiriksdottirCatrambone] Eiriksdottir, E. & Catrambone, R. Human Factors 53:749–770, 2011. https://doi.org/10.1177/0018720811419154
- [Shaikh] Shaikh, O. et al. "Grounding Gaps in Language Model Generations", NAACL 2024. https://arxiv.org/abs/2311.09144
- [HuaArtzi] Hua, Y. & Artzi, Y. "Talk Less, Interact Better", COLM 2024. https://arxiv.org/abs/2408.01417
- [Hawkins20] Hawkins, R. et al. "Continual adaptation for efficient machine communication", CoNLL 2020. https://arxiv.org/abs/1911.09896
- [AmbiEnt] Liu, A. et al. "We're Afraid Language Models Aren't Modeling Ambiguity", EMNLP 2023. https://arxiv.org/abs/2304.14399
- [Sclar] Sclar, M. et al. ICLR 2024. https://arxiv.org/abs/2310.11324
- [ClarifyGPT] Mu, F. et al. 2023 (preprint). https://arxiv.org/abs/2310.10996

### Controlled languages and engineering practice
- [STE-site] ASD-STE100. https://www.asd-ste100.org/about.html ; https://asd-ste100.org/about_STE.html
- [tcworld] "ASD-STE100 Issue 9". https://www.tcworld.info/e-magazine/column/asd-ste100-issue-9-setting-a-standard-for-technical-documentation
- [STE-wiki] "Simplified Technical English", Wikipedia [secondary]. https://en.wikipedia.org/wiki/Simplified_Technical_English
- [Shubert] Shubert, S. et al. JTWC 25:347–369, 1995. https://doi.org/10.2190/WG69-D74B-4DLL-2WBK
- [Chervak] Chervak, S., Drury, C. & Ouellette, J. HFES 40:303–307, 1996. https://doi.org/10.1177/154193129604000502
- [ChervakDrury] Chervak, S. & Drury, C. Occupational Ergonomics, 2003. https://content.iospress.com/articles/occupational-ergonomics/oer00053 [snippet; HTTP 403]
- [ASW2007] "Simplified Technical English", AeroSafety World, Aug 2007. https://flightsafety.org/wp-content/uploads/2016/11/asw_aug07_p16-21.pdf
- [ACE] Attempto Controlled English. http://attempto.ifi.uzh.ch/site/description/ ; [ACE-IR] http://attempto.ifi.uzh.ch/site/docs/ace_interpretationrules.html
- [Kuhn] Kuhn, T. Computational Linguistics 40(1):121–170, 2014. https://arxiv.org/abs/1507.01701
- [LogicalEnglish] Kowalski, R. & Datoo, A. AI and Law 30:163–197, 2021. https://doi.org/10.1007/s10506-021-09295-3
- [GF] Ranta, A. JFP 14(2):145–189, 2004. https://doi.org/10.1017/S0956796803004738
- [EARS] Mavin, A. EARS. https://alistairmavin.com/ears/ ; Mavin et al., IEEE RE'09
- [RFC2119] https://www.rfc-editor.org/rfc/rfc2119 ; [RFC8174] https://www.rfc-editor.org/rfc/rfc8174
- [NASA-C] NASA SE Handbook, Appendix C. https://www.nasa.gov/seh/appendix-c-how-to-write-a-good-requirement
- [INCOSE] INCOSE Guide to Writing Requirements v4 [secondary]. https://www.jamasoftware.com/requirements-management-guide/writing-requirements/incose-requirements-writing-guide/
- [ISO29148] ISO/IEC/IEEE 29148:2018 [not opened]
- [DeganiWiener] Degani, A. & Wiener, E. https://ntrs.nasa.gov/citations/19920000775 ; Human Factors 35:345–359, 1993. https://doi.org/10.1177/001872089303500209
- [OPORD] "Operations order", Wikipedia [secondary]. https://en.wikipedia.org/wiki/Operations_order ; Army article on mission command (Perna, 2019). https://www.army.mil/article/215297/mission_command_requires_sharp_commanders_intent
- [Errington] Errington, T. et al. "Challenges for assessing replicability in preclinical cancer biology", eLife 2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC8651289/ ; [ErringtonMain] https://pmc.ncbi.nlm.nih.gov/articles/PMC8651293/
- [Vasilevsky] Vasilevsky, N. et al. PeerJ 1:e148, 2013. https://doi.org/10.7717/peerj.148
- [Teytelman] Teytelman, L. et al. PLoS Biology 2016. https://doi.org/10.1371/journal.pbio.1002538
- [TLA] Lamport, L. TLA+. https://lamport.azurewebsites.net/tla/tla.html
- [AWS] Newcombe, C. et al. CACM 58(4):66–73, 2015. https://doi.org/10.1145/2699417 ; PDF https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf
- [Alloy] https://alloytools.org/about.html
- [Adzic] Adzic, G. *Specification by Example*, Manning 2011. https://www.manning.com/books/specification-by-example
- [Gherkin] https://cucumber.io/docs/gherkin/reference/
- [Requicha] Requicha, A. ACM Computing Surveys 12(4):437–464, 1980. https://doi.org/10.1145/356827.356833 [not opened]
- [OpenSCAD] https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Primitive_Solids
- [CadQuery] `Workplane.box`, cadquery/cq.py. https://github.com/CadQuery/cadquery/blob/master/cadquery/cq.py
- [ABOP] Prusinkiewicz, P. & Lindenmayer, A. *The Algorithmic Beauty of Plants*, 1990 (see PRIOR-ART.md).

### Description length and reference
- [Kolmogorov] "Kolmogorov complexity", Wikipedia [secondary], citing Kolmogorov 1965 and Li & Vitányi 2008. https://en.wikipedia.org/wiki/Kolmogorov_complexity
- [Rissanen] Rissanen, J. Automatica 14:465–471, 1978. https://doi.org/10.1016/0005-1098(78)90005-5
- [DaleReiter] Dale, R. & Reiter, E. Cognitive Science 19(2), 1995. https://arxiv.org/abs/cmp-lg/9504020
- [Pechmann] Pechmann, T. Linguistics 27:89–110, 1989. https://doi.org/10.1515/ling.1989.27.1.89 [not opened]
- [Engelhardt] Engelhardt, P., Bailey, K. & Ferreira, F. JML 54:554–573, 2006. https://doi.org/10.1016/j.jml.2005.12.009 [not opened]
- [Koolen] Koolen, R. et al. J. Pragmatics 43:3231–3250, 2011. https://doi.org/10.1016/j.pragma.2011.06.008 [not opened]
- [Degen] Degen, J. et al. Psychological Review 127:591–621, 2020. https://doi.org/10.1037/rev0000186 ; https://arxiv.org/abs/1903.08237
- [RubioFernandez] Rubio-Fernández, P. Frontiers in Psychology 7:153, 2016. https://doi.org/10.3389/fpsyg.2016.00153
- [FrankGoodman] Frank, M. & Goodman, N. Science 336:998, 2012. https://doi.org/10.1126/science.1218633
- [ShepardMetzler] Shepard, R. & Metzler, J. Science 171:701–703, 1971. https://doi.org/10.1126/science.171.3972.701
- [Hinton] Hinton, G. Cognitive Science 3:231–250, 1979. https://www.cs.toronto.edu/~fritz/absps/cube.pdf

### Not verified in this survey
- The "martini" example from Krauss & Weinheimer: secondary description only.
- Newton's tapper study (2.5% vs 50%): secondary only, from an unpublished dissertation.
- STE sentence-length and paragraph rules: secondary sources; the Issue 9 standard was not opened.
- Chervak & Drury 2003 hybrid result: search snippet only (HTTP 403).
- INCOSE rule numbers and ISO 29148 wording: secondary sources only.
- Commander's intent wording and ADP 6-0: secondary; the Army publications site blocked fetching.
- Federal plain-language guidance to use "must" over "shall": the page could not be reached.
- Requicha's definitions: from standard knowledge of the paper; the text was not opened.
- Stiny & Gips 1972: citation not confirmed.
- Pickering & Garrod and Garrod & Anderson findings: summarised from secondary knowledge.
- Engelhardt 2006, Koolen 2011, Pechmann 1989, Dixon 1982 and 1987, Levinson 2003, Putnam 1980, Kripke 1982: bibliographic details checked, texts not read.
- IGLU dataset sizes: search snippet only.
