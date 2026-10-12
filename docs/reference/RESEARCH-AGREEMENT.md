# Symblic: getting different LLMs to give the same answer

Research survey, 2026-10-02. Companion to [PRIOR-ART.md](PRIOR-ART.md) (which already covers PAL/Logic-LM/LINC,
self-consistency, MoA, MAKER, inference nondeterminism, "Let Me Speak Freely" and constrained decoding; those are
cited here only by reference) and [RESULTS.md](RESULTS.md) (Symblic's own measurements).

**Question.** Different applicators (Claude, Codex/GPT, Gemini, qwen3:4b, llama3.2:1b, gemma3:4b, phi4-mini,
granite3.3:2b) receive the same Symblic statement. How do we make them return the same canonical answer as often as
possible, and how do we detect and repair the statements where they diverge?

**Evidence markers.** [V] = abstract or full text opened in this survey and the number read there.
[S] = only a search-result snippet or secondary summary was seen, so treat the number as unconfirmed.
[U] = a standard reference that was not reopened here. Venue is given only where the opened page states it.

---

## 0. Findings and scope

1. Use deterministic checking and exact solving where their supported scope fits. Models can also construct proofs, programs, plans and candidate decompositions; checking these does not require hand-coding each solution into the kernel. Divergence can arise in interpretation, construction, verification or selection, and needs separate measurement.
2. Close the answer space. Typed asks raised Symblic's pairwise identity from 62% to 78% over all 7 applicators, and
   from 71% to 94% without llama3.2:1b (a subset chosen after seeing the data; RESULTS.md).
   Decomposing Likert judgments into yes/no checklists raised Krippendorff's α across 12 evaluator models from
   0.09 to 0.48 (CheckEval).
3. Write operational definitions with boundary cases. Detailed "constitution" definitions cut cross-model label
   disagreement by up to 57× compared with paragraph definitions (Berlin & Swanda 2026). Small models often ignore
   definitions and go by label names, so the decisive criterion must also be in the option name.
4. Treat disagreement between capable models as a measure of the specification. High cross-model divergence predicts
   spec problems 5–13× (Zhang et al. 2025) and locates codebook ambiguities (He et al. 2026). Specs repaired against
   one model's disagreement improve *other* models by 10.48% (SpecFix). Build a disagreement → contrastive question →
   amended statement loop.
5. Remove positional and label artefacts. Option order alone moves MCQ accuracy by 13–75 points, and models have
   option-ID priors (A/B/C/D). Removing IDs cut gpt-3.5's selection bias (RStd 5.5 → 1.0). Present options by
   value, in a fixed canonical order, and probe important asks with a permutation test.
6. Vote on meaning, not text: execution, kernel value or geometry equivalence. Behavioural clustering of code cut
   errors on answered items from about 65% to 2% (Ravuri & Amarasinghe 2025).
7. Keep an independent first round as a baseline. A cited debate model has a martingale result under its update assumptions; its experiments find voting explains much of the gain. This is not an impossibility theorem for interaction that obtains new observations, tool results or checked proofs. Compare such interaction at matched total budgets and record conformity as well as added evidence.
8. Agreement is not correctness. Model errors are correlated: two models that are both wrong pick the same wrong
   answer 60% of the time (Kim et al. 2025), and 48% of a frontier model's ≥0.8-agreement GPQA answers were wrong
   (Ding 2026). A pure kernel `ensure` establishes its encoded predicate on the supplied values, conditional on the implementation and premises; it does not establish arbitrary world truth or faithful interpretation.
9. Report chance-corrected agreement (Krippendorff's α, nominal, missing data allowed) with a **cluster bootstrap
   over statements**. Split agreement into correct-agreement and wrong-agreement, and give error consistency.
   Symblic's current Wilson intervals over answer *pairs* are too narrow (§8.6).
10. Gaps found: no peer-reviewed study measures how often *different* LLMs produce *equivalent* geometry or code from
    the *same* formal spec, and none compares CoT with direct answering *for cross-model agreement*. Symblic can
    publish both.

---

## 1. Prompt sensitivity and paraphrase consistency

### Evidence

**Format sensitivity**
- **Sclar, Choi, Tsvetkov, Suhr, ICLR 2024** [V] [Sclar]:
  - Meaning-preserving formatting changes give "performance differences of up to 76 accuracy points" (LLaMA-2-13B, few-shot).
  - The sensitivity persists with larger models, more examples and instruction tuning.
  - "Format performance only weakly correlates between models". The format that is best for one model is not best for another.
  - FormatSpread reports the interval of expected performance over sampled plausible formats.
- **Voronov, Wolf, Ryabinin, ACL Findings 2024** [V] [Voronov]:
  - 21 models (770M–70B). A poor template can reduce the strongest models "to a random guess level".
  - "The best templates do not transfer between different setups and even between models of the same family."
  - Fix: Template Ensembles, which average predictions across templates.
- **Mizrahi et al., TACL** [V] [Mizrahi]: 6.5M instances, 20 LLMs, 39 tasks. Single-template evaluation is brittle, so they call for multi-prompt evaluation.
- **Errica et al., NAACL 2025** [V] [Errica]:
  - *Sensitivity*: prediction change across rephrasings, needs no ground truth.
  - *Consistency*: variation across rephrasings for items of the same class.
  - Both are complementary to accuracy.
- **PromptBench / PromptRobust, Zhu et al.** [V] [PromptBench]: 4,788 adversarial prompts (character, word, sentence and semantic levels) across 8 tasks and 13 datasets. "Contemporary LLMs are not robust to adversarial prompts."

**Paraphrase consistency**
- **ParaRel, Elazar et al., TACL 2021** [V] [ParaRel]: 328 paraphrases of 38 relations. Pretrained LMs are "poor" at consistency, and it varies strongly by relation.
- **Generator–validator consistency, Li et al.** [V] [GVCons]:
  - GPT-4 is GV-consistent only 76% of the time: it answers a question but does not validate its own answer when asked differently.
  - Consistency fine-tuning raised Alpaca-30B from 60% to 93%.
- **Moore, Deshpande, Yang, EMNLP Findings 2024** [V] [Moore]: a useful counterpoint. On 8,000 value-laden questions, models were "relatively consistent across paraphrases, use-cases, translations", less so on controversial topics.
- **Raj et al. 2022** [V] [Raj]: semantic (meaning-level) consistency metrics track human judgments better than lexical ones.

**Option order and label/ID bias**
- **Pezeshkpour & Hruschka** [V] [Pezeshkpour]:
  - Reordering MCQ options gives "a considerable performance gap of approximately 13% to 75%".
  - Bias is worst when the model is torn between its top 2–3 candidates.
  - Calibration recovered up to 8 points.
- **Zheng et al., ICLR 2024 (spotlight)** [V] [PriDe]. Selection bias comes from option-ID *token* priors.
  - MMLU with a uniform gold distribution: llama-30B chose A/B/C/D 34.6/27.3/22.3/15.8%; gpt-3.5-turbo 22.5/25.6/32.3/19.6%.
  - Moving the gold answer to D cost gpt-3.5 6.3 points.
  - Cyclic permutation (×4 cost) cut recall s.d. from 5.5 to 1.1.
  - PriDe (5% of items for prior estimation, ×1.15 cost) cut it to 2.8.
  - **Removing option IDs** cut it to 1.0, with a slight accuracy loss.
- **MT-Bench judges, Zheng et al., NeurIPS 2023 D&B** [V] [MTBench]:
  - With the two answers swapped, judgments stayed consistent for GPT-4 65.0%, GPT-3.5 46.2% and Claude-v1 23.8% of the time.
  - Mitigation: judge both orders and count a win only if it is consistent, otherwise a tie.
- **Wang et al., "LLMs are not fair evaluators"** [V] [WangFair]:
  - Reordering alone let Vicuna-13B "beat" ChatGPT on 66 of 80 queries.
  - Fix: Balanced Position Calibration, which averages over orders.
- **Halterman & Keith** [V] [Codebook]: "all models are sensitive to the order that categories are described in the codebook".

**Label bias and calibration**
- **Contextual calibration, Zhao et al., ICML 2021** [V] [Calibrate]: majority-label, recency and common-token biases. A content-free input ("N/A") estimates the prior, giving up to +30.0 points absolute.
- **Example order, Lu et al., ACL 2022** [V] [FantOrder]: order alone spans "near state-of-the-art" to "random guess". Good orders "don't transfer across different models".
- **Fei et al., ACL 2023** [V] [FeiLabel]: domain-label bias. Domain-context calibration gives up to +37% macro-F1.
- **Reif & Schwartz, NAACL 2024** [V] [ReifLabel]: 279 tasks, 10 LLMs. Substantial label bias remains *after* debiasing.
- **Batch Calibration, Zhou et al., ICLR 2024** [V] [BatchCal]: zero-shot, inference-only calibration from batch statistics.

### Verdict
Surface form (format, template, option order, IDs, example order) is a first-order source of divergence. It is
**model-specific**: Sclar and Voronov find that the best form does not transfer, so it creates *cross-model*
disagreement even when every model "knows" the answer. Three remedies are measured:
- Removing the artefact: no option IDs, a fixed order.
- Averaging over it: permutations, templates.
- Calibrating it out: content-free or batch priors, which needs logprobs.

### Implication for Symblic
- The capsule is already one fixed format, which removes *within-run* variation. It cannot remove a model's private
  format preference, so measure it with a format and paraphrase probe (rule R16).
- Render `one of {…}` options as values, in canonical order, without letters.
- For ordered judgments (pairwise comparisons inside an ask), always evaluate both orders.

---

## 2. Ambiguity, underspecification and disagreement as a detector

### Evidence

**How ambiguous are real instructions, and do LLMs notice?**
- **AmbiEnt, Liu et al., EMNLP 2023** [V] [AmbiEnt]: 1,645 examples. GPT-4's disambiguations were judged correct only 32% of the time, against 90% for the human-written ones.
- **AmbigQA, Min et al., EMNLP 2020** [V] [AmbigQA]: "over half of the questions in NQ-open are ambiguous" (14,042 annotated questions), mostly from event and entity references.
- **CLAMBER, Zhang et al., ACL 2024** [V] [CLAMBER]: about 12K items. CoT and few-shot give only "marginal enhancements in identifying ambiguity" and "may result in overconfidence".
- **Tamkin et al.** [V] [Tamkin]: AmbiBench, six ambiguously specified tasks. Scale plus human-feedback training approaches human accuracy. Fine-tuning on a few ambiguous in-context examples helps a lot.
- **Yang et al., ACL Findings 2026** [V] [Underspec]:
  - LLMs infer unspecified requirements by default 41.1% of the time.
  - **Underspecified prompts are 2× as likely to regress across model or prompt changes**, with drops above 20%.
  - Simply listing every requirement does not reliably help; requirements-aware optimization gains 4.8%.

**Clarifying questions**
- **Qulac, Aliannejadi et al., SIGIR 2019** [V] [Qulac]: one clarifying question gives over 170% P@1 improvement in retrieval.
- **CLAM, Kuhn, Gal, Farquhar** [V] [CLAM]: detect, ask, answer. It improves accuracy on mixed ambiguous and unambiguous questions.
- **Zhang & Choi, "Clarify When Necessary"** [V] [IntentSim]: intent-sim uncertainty. Clarifying only 10% of examples doubles the gain over choosing which to clarify at random.
- **CLARINET, Chi et al.** [V] [CLARINET]: clarification questions conditioned on the retrieval distribution.
- **APA, Kim et al.** [V] [APA]: aligning models to their *perceived* ambiguity.

**Sampling disagreement as an ambiguity and uncertainty signal**
- **Semantic entropy (Kuhn et al., ICLR 2023; Farquhar et al., Nature 2024)** [V] [SemUnc][SemEntropy]:
  - Clusters answers by bidirectional entailment and computes entropy over the clusters.
  - AUROC 0.790, against 0.691 for naive entropy and 0.698 for P(True), stable at 0.78–0.81 across LLaMA, Falcon and Mistral.
  - The discrete (black-box) variant counts cluster frequencies.
  - Stated limit: it "does not help when LLM outputs are systematically bad". Consistent errors are invisible.
- **Cole et al., EMNLP 2023** [V] [Cole]: repetition among sampled outputs is the best answer/abstain signal, with especially large gains on *inherently ambiguous* questions.

**Cross-model disagreement localizes specification problems** (the core question)
- **Zhang, Sleight, Peng, Schulman, Durmus 2025 (Anthropic Fellows / Anthropic / Thinking Machines)** [V] [StressSpec]:
  - Over 300K scenarios, 12 frontier models. Disagreement is the s.d. of value-classification scores across models.
  - "High-disagreement scenarios exhibit 5–13× higher rates of frequent specification violations".
  - Qualitative analysis traced divergence to "direct contradiction and interpretive ambiguities" in the specs.
- **He et al. 2026** [V] [ExpertsRise]:
  - 6 models from different providers (GPT 5.1, Gemini 2.5 Pro, Claude Sonnet 4.5, Qwen3 Coder 480B, DeepSeek V3.2, Mistral Large 3) label 6,595 utterances.
  - High-disagreement items reach weighted F1 0.295 with the initial codebook, against 0.660 for low-disagreement items.
  - Targeting expert effort at disagreements ("rationale labeling") gives 64.9% accuracy, against 57.8% for a fully expert-revised codebook.
- **Gorbett & Jana 2026** [V] [CrossModelPPL]: a second model's perplexity on the first model's answer flags confident errors. AUROC 0.75 on MMLU, against 0.59 for within-model entropy.

**Code: inter-sample divergence as a requirement-ambiguity detector**
- **ClarifyGPT, Mu et al.** [V] [ClarifyGPT]:
  - Sample n programs, run them on generated inputs, and treat the requirement as ambiguous if outputs differ.
  - Clusters by output, then asks targeted questions.
  - GPT-4 on MBPP-sanitized: 70.96% → 80.80% pass@1. Four-benchmark average: 68.02% → 75.75%.
- **SpecFix, Jia et al., ASE 2025** [V] [SpecFix]:
  - Repairs the *description* to minimize semantic entropy over program equivalence classes.
  - Modified 43.58% of descriptions, +30.9% pass@1 on those, +4.09% overall.
  - **Descriptions repaired for one model improved other models by 10.48%.**
- **HumanEvalComm, Wu & Fard** [S] [HumanEvalComm]: 762 HumanEval variants made ambiguous, inconsistent or incomplete. Over 60% of responses still write code instead of asking; pass@1 falls 35–52%.

### Verdict
- Ambiguity is common (over half of NQ-open) and models rarely flag it themselves (AmbiEnt 32%; CLAMBER).
- **Disagreement among samples or models is a useful diagnostic, not a uniquely best detector.** Several lines of evidence show
  it localizes ambiguous or underspecified *instructions*, not just hard items: spec stress-testing, codebook
  revision, ClarifyGPT and SpecFix.
- Most usefully for Symblic, a spec repaired against disagreement transfers across models (SpecFix +10.48%).
- Caveat: agreement does not exonerate a statement. Shared misreadings produce confident unanimous wrong answers
  (Farquhar's limit; §6).

### Implication for Symblic
Make "contested" a first-class diagnostic of the *statement*, not only of the run:
- Cluster answers by fingerprint, show the two largest clusters with the applicators behind each, and generate a
  *contrastive* clarification: "what in the instruction makes X and Y both defensible?".
- Have the author amend the statement, and re-run (rule R5).

---

## 3. Techniques that increase cross-model agreement

### Evidence

**LLMs as annotators: agreement numbers**
- **Gilardi, Alizadeh, Kubli, PNAS 2023** [V] [Gilardi]:
  - "Intercoder agreement" was about 56% for MTurk, 79% for trained annotators, 91% for ChatGPT at temperature 1 and 97% at 0.2.
  - Note: ChatGPT's figure is *test–retest of one model* (two runs), not cross-model.
  - Accuracy beat MTurk by about 25 points on average.
  - Lower temperature "seems to increase consistency without decreasing accuracy".
- **Törnberg 2023** [V] [Tornberg23]: GPT-4 had higher accuracy and reliability than experts and crowd workers on political-affiliation labels.
- **Törnberg, Sociologica 2024** [V] [Tornberg24]: best practices, including structured prompts, prompt-stability analysis, validation against humans and reporting versions and parameters.
- **Reiss 2023** [V] [Reiss]: small prompt wording changes and plain repetition changed ChatGPT's labels. Aggregating repeated runs helps, but validation is required.
- **Prompt Stability Score, Barrie, Palaiologou, Törnberg** [V] [PSS]:
  - Krippendorff's α across repeated runs (intra-PSS) and across paraphrased prompts (inter-PSS), with bootstrap; about 3.1M classifications.
  - Intra-PSS is mostly above 0.8. Stability falls as paraphrases drift and temperature rises.
  - Recommends investigating anything below 0.8.
- **Rating Roulette, Haldar & Hockenmaier, EMNLP Findings 2025** [V] [Roulette]:
  - Intra-rater α on MT-Bench: Llama 3.1 0.265, DeepSeek-R1 0.507, Qwen 3 0.563.
  - **Majority vote across runs beat the best single run.**
  - Greedy decoding reduced reliability variance but *degraded* accuracy.
  - Few-shot and CoT gave no reliability gain (their App. C.2).
  - Raw accuracy (0.827) far overstates chance-corrected agreement (α 0.478) between human judges.

**Codebooks and definitions**
- **Halterman & Keith, Political Analysis 2025** [V] [Codebook]:
  - Zero-shot codebook following by open 7–8B models is weak (weighted F1 0.21–0.65).
  - Dropping the class definition sometimes *helped*. Models rely on label semantics: generic or swapped labels hurt.
  - Models ignored exclusion criteria.
  - Instruction tuning raised Mistral-7B on BFRS from 0.53 to 0.82.
- **Mohammadi et al., EMNLP 2025** [V] [LabelDefs]: definitions "can enhance accuracy", but their use "is neither guaranteed nor consistent". General tasks default to parametric knowledge; domain-specific tasks are more receptive.
- **Berlin & Swanda 2026** [V] [Constitution]:
  - Cross-model disagreement against Opus 4.6, counted per 1,000 conversations, for GPT-5.4 (full, Mini and Nano), Gemini 3.1 Pro and Safeguard 20B.
  - Primary-table recheck, 2026-10-04: harassment intent for GPT-5.4 Mini falls from 22.9 to 0.4 disagreements per 1,000, about 57.3×. The earlier example 47.2 → 1.5 is GPT-5.4 harassment **content**, about 31.5×, not Gemini 3.1. These are rounded, uncertainty-bearing estimates of disagreement with Opus, not a Symblic accuracy improvement. [Table 2](https://arxiv.org/html/2605.24247v1#S4.T2)
  - Three LLMs reading the same constitution were *more unanimous than three humans* on all three categories.

**Decomposition into atomic questions**
- **CheckEval, Lee et al., EMNLP 2025** [V] [CheckEval]:
  - Decomposed yes/no checklists against G-Eval Likert scoring, 12 evaluator models (GPT-4o family, Llama 3.1, Mistral, Qwen 2.5 and Gemma 2 at 7B–123B).
  - Inter-evaluator Krippendorff's α on SummEval: 0.09 → 0.48 for all models, 0.05 → 0.67 for large models.
  - Lower sensitivity to the choice of evaluator model.
- **TICK, Cook et al. 2024** [V] [TICK]: generated yes/no checklists. LLM–human exact agreement 46.4% → 52.2%; human inter-annotator agreement 0.194 → 0.256.
- **FollowBench, Jiang et al., ACL 2024** [V] [FollowBench]: adds one constraint per level (content, situation, style, format, example). Compliance degrades as constraints pile up.
- **IFEval, Zhou et al. 2023** [V] [IFEval]: 25 types of *verifiable* instructions (about 500 prompts), so compliance is checked by code, not by a judge. This is the same idea as Symblic's `ensure`.

**Few-shot examples**
- **Min et al., EMNLP 2022** [V] [MinDemos]: random labels in demonstrations "barely hurt". What matters is the label space, the input distribution and the format. So examples mainly *pin the format and the label set*.
- **Order and bias**: order effects (Lu) and recency, majority and domain biases (Zhao, Fei) apply. See §1.

**Chain of thought and temperature**
- **Sprague et al., ICLR 2025** [V] [ToCoT]: 14 models, 20 datasets. CoT helps mainly math and logic. On MMLU, direct answering is almost identical unless the question or response contains "=".
- **Renze & Guven, EMNLP Findings 2024** [V] [Temp]: 9 LLMs. Temperature 0.0–1.0 had no statistically significant effect on MCQ accuracy.
- No study was found that measures **cross-model** agreement for CoT against direct answering. That is a gap; within-model evidence is above (Rating Roulette; CLAMBER's overconfidence).

**Aggregation**
- **Universal Self-Consistency, Chen et al. 2023** [V] [USC]: the LLM picks the most consistent of the free-form candidates. It matches execution-based voting on code without executing anything.
- **Kamen & Kamen 2025** [V] [eLLM]: a 10-LLM ensemble gave up to 65% F1 improvement over the best single model in zero-shot taxonomy categorization.
- **Ding 2026** [V] [Ding]: cross-model agreement predicts correctness only weakly (ρ 0.20–0.59).

**Per-field voting for records**
No primary study of field-level voting across heterogeneous LLMs was opened. Practitioner reports [S] note that
independent per-field votes can assemble a record no model produced, breaking cross-field logic. Symblic already
documents this risk in `consensus_fields`.

### Verdict
The strongest measured levers on *cross-model* agreement are:
1. **Precise operational definitions with boundaries and edge cases**: up to 57×.
2. **Decomposition into atomic binary checks**: α 0.09 → 0.48 across 12 models.
3. **Closed outputs**: RESULTS.md; Murin in PRIOR-ART.

Then come low temperature for test–retest stability, voting over repeated or diverse samples, and fixed examples to
pin format and label space. Definitions are *necessary but not sufficient* for small models, which follow label
names. CoT is not an agreement lever outside math and logic.

### Implication for Symblic
- Promote `define` from a type alias to a *glossary with boundaries*: each option gets a meaning, includes and
  excludes, and an edge case.
- Provide a checklist idiom: one Bool ask per criterion, combined by kernel rules.
- Choose `effort` per determinism class.

---

## 4. Convergence and conventions in LLM populations

### Evidence

**Naming games and conventions**
- **Ashery, Aiello, Baronchelli, Science Advances 2025** [V] [Ashery]:
  - Naming game with N = 24 agents (up to 200), name pool W = 10 (up to 26), memory H = 5, payoff +100/−50.
  - Models: Llama-2-70b-Chat, Llama-3-70B, Llama-3.1-70B, Claude-3.5-Sonnet.
  - A global convention emerges by round 15 for all but Llama-2.
  - **Collective bias** appears even when individuals look unbiased, and the preferred names differ by model.
  - A **committed minority** can overturn the convention. The critical mass ranges from about 2% (Llama-3-70B) to 67% (Llama-2-70b), depending on the model.
- **Mehdizadeh & Hilbert 2026** [V] [Topology]: 432 networked naming-game runs, 16 agents, 8 topologies. Memory depth and topology interact, and centralized networks can lock into fragmented plateaus. Choices fit Fictitious Play.

**Reference games and conceptual pacts**
- **Hua & Artzi, COLM 2024** [S] [ICCA]: MLLMs understand a partner's increasingly efficient language but do not make their *own* more efficient; only heavy prompting elicits this in GPT-4.
- **Jones, Lombardi, Mahowald, Bergen 2026** [V] [JonesConv]:
  - AI–AI and human–human pairs both form conventions: accuracy and consistency rise, length falls.
  - **Human–AI pairs do not.** Even with length matched, accuracy and lexical overlap lag, which the authors attribute to missing "shared interpretative biases".
- **Wang et al. 2026** [V] [NoPacts]: MLLM dyads on KTH Tangrams are verbose from round 1, with near-ceiling label overlap that is "statistically indistinguishable between real and pseudo dyads". Their alignment comes from *shared task vocabulary*, not interaction history.

**Consensus dynamics**
- **Yazici et al., ICASSP 2026** [V] [DeGrootLLM]:
  - Networked LLM agents reach consensus with exponentially decaying disagreement, and the transient rate follows the graph's second eigenvalue, as DeGroot predicts.
  - **But the limiting opinion departs from DeGroot's centrality-weighted forecast** and depends on the topic and the models' inherent biases.
  - Instructing the weights in the system prompt makes consensus more likely.
- **Chuang et al. 2024** [V] [Chuang]: LLM agents drift toward the scientifically accurate consensus unless confirmation bias is induced, which produces fragmentation.

**Debate and conformity**
- **Choi, Zhu, Li, NeurIPS 2025 (spotlight)** [V] [DebateVote]: across 7 benchmarks, **majority voting accounts for most of multi-agent-debate gains**. Their theoretical martingale argument depends on the stipulated belief-update process; it is not a statement about every tool-using or proof-producing interaction. [Primary paper](https://arxiv.org/html/2508.17536v1)
- **Estornell & Liu, NeurIPS 2024** [S] [Estornell]: similar models produce static debates that converge to the majority (an "echo chamber"), even when the majority shares a misconception.
- **BenchForm, Weng et al., ICLR 2025 (oral)** [V] [BenchForm]: LLMs show conformity in multi-agent protocols, depending on interaction count and majority size. Personas and reflection reduce it.

### Verdict
- Populations of LLMs converge readily: conventions within about 15 rounds, exponential consensus. But *what* they
  converge to is set by shared priors and biases, not by truth or network weights.
- Small committed minorities can flip a convention.
- Inter-LLM lexical alignment largely reflects shared vocabulary, which is good news for Symblic: models already share
  the default meanings of common words. The risk lies in the words whose defaults differ.
- Interaction can add conformity. Whether it adds useful information depends on what evidence or construction it introduces; measure this rather than treating all interactions as information-free.

### Implication for Symblic
- Do not get agreement by letting applicators see each other. Get it from the statement.
- Keep the first, independent round as the primary vote. Treat `ultra` as an optional second opinion whose
  flip-to-majority rate is recorded.
- Model-proposed identifiers require explicit binding, namespace and collision checks. A coined name supplies no authority or cross-agent meaning by itself.

---

## 5. Spec-to-artifact reproducibility (CAD, 3D, code)

### Evidence: CAD

**Benchmarks** (every model is compared to ground truth, never to another model)
- **CADPrompt / CADCodeVerify, Alrashedy et al.** [V] [CADPrompt]: 200 prompts with expert CadQuery code. VLM-generated validation questions as feedback gave GPT-4 7.30% lower point-cloud distance and +5.0% success.
- **Text2CAD, Khan et al., NeurIPS 2024 (spotlight)** [V] [Text2CAD]: about 170K DeepCAD models with 660K descriptions, from abstract ("two concentric cylinders") to expert (explicit centres, radii and extrusion depths).
- **Text2CAD-Bench, Wang et al. 2026** [V] [T2CBench]:
  - 600 curated CadQuery tasks in 4 levels, scored with Chamfer (30K points), voxel IoU at 256³ and invalidity rate.
  - 7 general LLMs, including GPT-5.2, Claude-4.5-Sonnet, Gemini-3-Flash, DeepSeek-V3.2 and Qwen3-max.
  - Best L1 IoU is 0.59 (GPT-5.2). **Invalidity rises from about 15% at L1 to 70–90% at L3.**
  - Procedural ("sequence") prompts beat geometric descriptions on the hardest level (GPT-5.2 CD 82.94 vs 93.46).
- **Query2CAD, Badagabettu et al.** [V] [Query2CAD]: FreeCAD macros with GPT-4 Turbo: 53.6% first-attempt success, +23.1% after refinement.
- **Text-to-CadQuery, Xie & Ju 2025** [V] [T2CQ]: fine-tuned 6 open LLMs; the best "exact match" is 69.3%. Note: that "match" is a **Gemini 2.0 Flash judgment of renders**, not geometric equality.

**Comparing geometry**
- **Haag et al. 2026, verifier-free CAD consensus selection** [V] [CADConsensus]:
  - Sample several programs, compile them, and pick the candidate that agrees most with the others, using geometric and topological agreement.
  - Chamfer is 1–10% lower than random selection.
  - This is the 3D analogue of voting on fingerprints.
- **B-rep matching, Jones et al., ACM TOG 2023** [V] [BRepMatch]: learned correspondence between B-reps across CAD systems. Topology identity across systems is itself a research problem.

**Other**
- **Makatura et al. 2023** [V] [Makatura]: GPT-4 across the design and manufacturing workflow, with benefits and stated limits.
- CAD-Recode, LLM4CAD, AIDL and the SVG/TikZ literature are covered in PRIOR-ART §10.
- BlenderGPT and "LLMs construct 3D objects from text": not verified in this survey.

### Evidence: code equivalence
- **Ouyang, Zhang, Harman, Wang, ACM TOSEM 2025** [V] [Ouyang]:
  - Same prompt and same model (ChatGPT): **75.76% (CodeContests), 51.00% (APPS) and 47.56% (HumanEval) of tasks had zero equal test outputs across requests.**
  - Temperature 0 reduces but does not remove this.
- **Execution-based equivalence for selection**:
  - MBR-exec [V] [MBRexec] (EMNLP 2022) marginalizes over programs with identical execution results.
  - CodeT [V] [CodeT] uses dual execution agreement: HumanEval pass@1 65.8%, +18.8 over code-davinci-002.
- **Functional clustering, Ravuri & Amarasinghe 2025** [V] [FuncCluster]:
  - Cluster programs by identical I/O on self-generated tests; the largest cluster's mass is the confidence.
  - LiveCodeBench error on answered items falls from about 65% to 2%; 0% error at a conservative threshold while answering 15.6%.
  - **Residual errors come from "prompt misinterpretation rather than generation noise".**
- **Cross-model code ensembles, Mahmud et al. 2025** [V] [CodeEnsemble]: CodeBLEU plus CrossHair differential testing to vote across LLMs. HumanEval 90.2% against GPT-4o's 83.5%; LiveCodeBench 50.2% against 43.4%.
- **Specificity**:
  - PartialOrderEval, Zi, Menon, Guha 2025 [V] [PartialOrder]: pass@1 scales with prompt detail; explicit I/O specs, edge cases and stepwise breakdowns drive the gains.
  - ClarifyGPT and SpecFix: §2.

### Verdict
- **No study in this historical search measured cross-model equivalence of generated geometry for the same spec.** The reported invalidity rates motivate testing; they do not show that checked model-generated geometry is impossible.
- Equal I/O on shared tests establishes agreement on those tests, not general program equivalence. Remaining divergence can arise from spec ambiguity, construction errors or an inadequate verifier.
- Closed parameter records plus deterministic rendering are one useful design. Models may also construct code or constraints, with sandboxed execution, declared artifact equivalence and independent checks.
  RESULTS.md shows identical drawing bytes from 5 capable applicators on 6 essays.

### Implication for Symblic
- Models emit closed `Record` specs (dimensions with units, enumerated features). The kernel builds geometry.
- For generated code, compile and execute in the declared sandbox. A versioned canonical mesh key can support exact grouping. Pairwise IoU or Chamfer thresholds need not be transitive and therefore are not equivalence keys; use an explicit clustering policy, report its thresholds and retain original artifacts. Tested similarity must not become a claim of identity.

---

## 6. Measuring agreement properly

### Evidence

**Chance-corrected agreement coefficients**
- **Krippendorff's α** [V] [Kripp2011][KrippBoot]:
  - α = 1 − D_o/D_e. It allows any number of coders, missing data (via the coincidence matrix) and any metric (nominal, ordinal, interval, ratio).
  - Bootstrap note (revised 2016): resample pairs of values while holding D_e fixed; X = 20,000 resamples; α_min = 0.800; report q = P(α < α_min).
  - Hayes & Krippendorff (2007) proposed α as the standard [U] [HayesKripp].
- **Cohen's κ (1960)**, **Fleiss' κ (1971)** [U]: chance from marginals. **Bennett's S (1954) / Brennan–Prediger** [U]: chance = 1/k, the right baseline when a closed type fixes k.
- **Gwet's AC1 (2008)** [U] [Gwet]: robust to the "kappa paradox" (high agreement but low κ under skewed prevalence; Feinstein & Cicchetti 1990 [U]).

**Agreement vs accuracy**
- **Error consistency, Geirhos, Meding, Wichmann, NeurIPS 2020** [V] [ErrCons]: κ over correct/incorrect with c_exp = p₁p₂ + (1−p₁)(1−p₂). It separates "agree because both are accurate" from "agree on *which* items they fail".
- **CAPA, Goel et al., ICML 2025** [V] [CAPA]:
  - c_exp = p̄₁p̄₂ + (1−p̄₁)(1−p̄₂)·mean_x 1/(|O(x)|−1). Two wrong models agree by chance only if they pick the same wrong option.
  - κ_p = (c_obs − c_exp)/(1 − c_exp).
  - Findings: judges favour models similar to themselves; "model mistakes are becoming more similar with increasing capabilities".
- **Kim, Garg, Peng, Garg, ICML 2025** [V] [CorrErr]: over 350 LLMs. **When two models both err, they agree 60% of the time** on one leaderboard. Larger and more accurate models have more correlated errors even across providers.
- **Ding 2026** [V] [Ding] and Farquhar's limit (§2) both show that unanimity can be confidently wrong.

**Percent agreement inflates**
- Rating Roulette [V]: accuracy 0.827 against α 0.478 for the same human judges. Report chance-corrected values.

### Verdict
For Symblic's data (several applicators, many statements, missing or invalid answers, mixed answer types):
- Use **Krippendorff's α (nominal on fingerprints)** as the headline.
- Use **Bennett's S per closed statement** (known k).
- Use the **CAPA or error-consistency** family when ground truth exists.
- Use a **cluster bootstrap over statements** for uncertainty.

---

## 7. Engineering rules for Symblic (ranked by expected effect on cross-model agreement)

The ranking combines measured effect size with how much of Symblic's workload each rule touches.
"Status" says what exists in `symblic/kernel/language.py` today (read 2026-10-02) and what is new. Effects marked *(inference)*
are extrapolations, not measured for Symblic.

This is a historical proposal matrix. Current implementation status belongs to [REFORM-3.md](REFORM-3.md), [SPEC.md](SPEC.md) and their tests; a row marked "new" below does not establish a present-day missing feature. No rule may improve agreement by silently removing a task requirement or changing the intended answer space.

| # | Rule | Evidence | Status |
|---|---|---|---|
| R1 | **Separate construction from checking.** Use exact solving where supported; models may construct proofs, programs, plans and parameters, checked against explicit obligations. | RESULTS §3–4 (Datalog, flowers); PRIOR-ART §5 (PAL, Logic-LM, ANVIL: errors concentrate in formulation) | exists; keep as a style rule |
| R2 | **Close every ask that can be closed.** Bool, `one of`, bounded Int, or a Record of those; Text only when the output is prose. Preserve required distinctions such as explicitly absent versus not mentioned; improve definitions or record uncertainty instead of merging meanings for agreement. | RESULTS §2: 62% → 78% pairwise (all), 71% → 94% (without llama3.2:1b); CheckEval Likert → binary; Murin (PRIOR-ART) | exists; add a linter warning on Text asks feeding later logic |
| R3 | **Operational definitions per option** (`define` as a glossary): meaning, includes, excludes, one edge case, in the capsule for every applicator. | Constitution: up to 57× fewer cross-model disagreements, 3 LLMs more unanimous than 3 humans; Codebook / LabelDefs: small models under-use definitions | new: `define X as one of {a: "…", b: "…"}` |
| R4 | **Put the decisive criterion in the option name** (`stated-in-text`, `inferred`, `not-stated`, not `A/B/C` or vague nouns). | Codebook (label semantics dominate; swapped labels hurt); PriDe (ID priors) | new style rule; checker warns on single-letter or numeric option names |
| R5 | **Disagreement → contrastive clarification → amended statement.** When capable applicators split, show the two biggest clusters and their supporters, generate "what wording admits both?", let the author amend, and re-run. Keep the amendment history. | SpecFix (+10.48% transfer to other models); ClarifyGPT; StressSpec (5–13×); ExpertsRise; IntentSim (clarifying 10% doubles the gain) | new (Compare screen + `check --contested`) |
| R6 | **Decompose multi-criteria judgments into atomic Bool asks combined by kernel rules** (checklist idiom). | CheckEval α 0.09 → 0.48 (0.05 → 0.67 large models); TICK; FollowBench degradation with constraint count | new idiom and example program |
| R7 | **Static underspecification linter**: missing units, rounding (`to N places`), time reference ("current", "recent"), scope words ("main", "large"), tie rules for lists (order, duplicates), an explicit "cannot be determined" option, and an empty-input case. | Underspec (2× regression across model changes); AmbigQA (>50% ambiguous); PartialOrder (I/O spec, edge cases) | new in `check` |
| R8 | **Vote on meaning: equivalence keys.** `key=eval(it)` exists. Add declared canonical quantization, order-insensitive set/multiset keys where appropriate, bounded execution signatures and canonical mesh hashes. Pairwise distance thresholds are not automatically equivalence relations. | MBR-exec; CodeT; FuncCluster (65% → 2%); CADConsensus; semantic entropy | partly exists; extend |
| R9 | **Options as values in canonical order, no letter IDs, the same for every applicator.** For pivotal closed asks, an optional permutation probe (k cyclic rotations) counts the ask as stable only if the answer survives. | PriDe (no IDs: RStd 5.5 → 1.0; cyclic: 5.5 → 1.1 at ×4); Pezeshkpour (13–75 points); MTBench (judge both orders); Codebook (category order matters) | ordering: verify; probe: new `with permute=k` |
| R10 | **Admit applicators per statement class by measured reliability.** The familiar p > 0.5 condition concerns binary voting under additional assumptions; do not apply it universally to multiclass or correlated panels. Freeze selection/weights using separate calibration data. | RESULTS (llama3.2:1b drives most divergence, 6/16 correct); MAKER (PRIOR-ART) | new: per-class weights from bench data |
| R11 | **Report families and samples separately.** A diverse-family quorum is an optional explicit policy; family names do not establish error independence. Preserve literal panel unanimity as a separate metric. | CorrErr (60% shared wrong answers); CAPA (errors converging with capability) | new quorum rule |
| R12 | **Fixed shared examples** (`example` lines): 1 per option, balanced, canonical order, identical for all applicators. They pin label space and format, not knowledge. | MinDemos; FantOrder; Calibrate (recency and majority bias); FeiLabel | new statement or option |
| R13 | **Measure effort policies by task class.** Compare direct answers, provider-supported reasoning and separate construction/checking under equal total budgets; no universal reasoning ban or required reasoning field follows from these studies. | ToCoT (CoT helps mainly math and logic); Roulette (CoT no reliability gain); CLAMBER (overconfidence); Let Me Speak Freely (PRIOR-ART) | exists (`effort`); set class defaults |
| R14 | **Declare sampling policy.** Temperature 0 is a useful reproducibility treatment, not a guarantee or universal optimum; compare repeated sampling and model diversity with identical budgets. | Gilardi (97% vs 91% test–retest); Temp (no accuracy cost 0–1); Roulette (greedy trades accuracy); Ouyang (T = 0 still nondeterministic) | exists (sample 0 at T = 0) |
| R15 | **Independent vote first; interaction only as a recorded second opinion.** The first round is the primary record. Log each applicator's flip-to-majority in `ultra` and never show counts ("4 of 5 said X") to an applicator. | DebateVote (martingale); Estornell (echo chamber); BenchForm (conformity); Ashery (collective bias, committed minority); RESULTS §5 (ultra +0, ×5 time) | exists; change reporting |
| R16 | **Paraphrase and format probe** in `compare`: render each ask in its canonical capsule plus 2 meaning-preserving variants and report inter-PSS α per applicator. A low α marks the *statement* as fragile. | Sclar (76 points; weak cross-model correlation); Voronov (no transfer; template ensembles); PSS; Errica | new bench mode |
| R17 | **One explicit abstain value** ("not determinable from the given input") for extraction asks, defined in the glossary. Never two near-synonymous abstain values. | Cole (abstention from repetition); Murin (PRIOR-ART: absent vs not-mentioned was the main disagreement); HumanEvalComm (models guess instead of asking) | new style rule |
| R18 | **Per-field voting with a dependency guard.** Vote field by field only over fields that no `ensure` links; otherwise vote on the joint sub-record. Report `agreement_whole` next to the field minimum. | `consensus_fields` docstring; [S] practitioner reports; *(inference)* | exists; add the guard |
| R19 | **Prior calibration for local models with logprobs** (optional): for `one of` asks on Ollama, estimate the option prior with a content-free input and divide it out (contextual calibration), or use PriDe on a 5% sample. | Calibrate (+30 points); BatchCal; PriDe | new, optional |
| R20 | **Check identifier binding and authority.** A model may propose names, but the host validates namespaces, collisions and references. An invented name alone cannot create a capability or trusted fact. | Ashery (conventions are biased and flippable); NoPacts (alignment comes from shared vocabulary) | style rule |
| R21 | **Support several checked construction paths.** Compare parameter records plus rendering with model-generated code, constraints or proofs. Sandbox execution and declare canonicalization, test scope and fidelity obligations. | RESULTS §4 (identical bytes); T2CBench (invalidity 15% → 70–90%; IoU ≤ 0.59); CADConsensus | exists for flowers; extend to CAD |
| R22 | **Pin and record the version of each applicator**, including CLI and model ID and engine fingerprint, and re-measure α when it changes. | PRIOR-ART §8 (drift; endpoint inequality) | partly exists (calls.jsonl) |
| R23 | **Agreement never certifies.** Contested asks fail under `strict`; unanimous asks still run `ensure`. Report wrong-agreement whenever ground truth exists. | Ding (48% of high-agreement GPQA wrong); SemEntropy limit; CorrErr | exists as a principle; add the metrics |

**Expected order of impact on Symblic's mix of statements** *(inference)*:
- **Large:** R1–R3 and R5. They remove the main causes of divergence: computation, open answers, undefined terms and
  statements with two readings.
- **Medium:**
  - R4, R6, R7: precision of what is asked.
  - R8: counts equivalent answers as equal.
  - R9: a medium effect on MCQ-like asks.
  - R10, R11: who votes.
- **Small but cheap:** R12–R20.
- **R21–R23:** keep scope and claims honest.

---

## 8. Metrics to report

Notation:
- **Statements (units):** u = 1…N.
- **Applicators:** a = 1…M, with family f(a).
- **Answers:** x_{ua} is the canonical fingerprint of the valid answer from applicator a on statement u, or missing.
- **Valid answers on u:** m_u. **Distinct fingerprints on u:** K_u. **Closed option count:** k_u (for `one of`,
  Bool = 2, Int in a..b = b−a+1; undefined for open types).
- **Answers in cluster c on u:** n_{uc}.

### 8.1 Per statement (shown in Trace / Compare)
- Validity: v_u = m_u / (applicators asked).
- Winner share (exists): A_u = max_c n_{uc} / m_u, weighted by applicator weight when weights are used.
- Pairwise identity: P_u = Σ_c n_{uc}(n_{uc} − 1) / (m_u(m_u − 1)).
- Optional Bennett's S for k_u > 1: S_u = (P_u − 1/k_u) / (1 − 1/k_u), explicitly using a uniform-category chance model. Cardinality alone does not justify that null; omit it when inappropriate or undefined.
- Discrete semantic entropy in bits: H_u = −Σ_c (n_{uc}/m_u) log₂(n_{uc}/m_u).
  - If normalized, divide by log₂ min(m_u, k_u), or by log₂ m_u for open types.
  - The current code divides by log K_u (distinct groups). Every even split then reads 1.0, so a 2-way and a 7-way split look the same.
- Family support: report distinct recorded model families separately. Panel unanimity means K_u = 1 and v_u = 1; a diverse-family quorum is an additional declared policy. Neither proves independent errors or sources.
- Flags:
  - *contested*: A_u < agree.
  - *split*: the top two clusters each hold ≥ 25% and each contains an admitted applicator. This sends the statement to the R5 diagnostic loop; it does not establish semantic ambiguity.

### 8.2 Corpus level: Krippendorff's α (nominal, missing data allowed)
Coincidence matrix over fingerprints c, k:

    o_ck = Σ_u  [ Σ_{a≠b} 1(x_ua = c) · 1(x_ub = k) ] / (m_u − 1)      (units with m_u ≥ 2 only)
    n_c  = Σ_k o_ck,   n = Σ_c n_c
    D_o  = Σ_{c≠k} o_ck / n
    D_e  = Σ_{c≠k} n_c n_k / (n(n − 1))
    α    = 1 − D_o / D_e  =  1 − (n − 1) · Σ_{c≠k} o_ck / Σ_{c≠k} n_c n_k

Notes:
- Pool α only when categories have the same interpretation across items. Giving every statement its own fingerprint categories drives D_e toward 1 and can reduce α to a restatement of identity; do not present that construction as meaningful chance correction.
- For comparable numerical outcomes, interval α can use δ²(c, k) = (value_c − value_k)². Stratify by quantity, unit and task scale, or preregister a meaningful normalization. Pooling unrelated dollars, metres and counts is uninterpretable.
- Report α per determinism class (closed, structured, open) and per applicator subset. **Define the subsets before
  the run.** The "without llama3.2:1b" figure in RESULTS.md was chosen after seeing the data.
- Leave-one-applicator-out α: the change in α when applicator a is dropped identifies the dissenter.

### 8.3 Fleiss κ (complete data, the same k for every statement; closed suites only)
    P̄ = (1/N) Σ_u P_u,   p_c = (1/(N·m)) Σ_u n_uc,   P̄_e = Σ_c p_c²,   κ = (P̄ − P̄_e) / (1 − P̄_e)

If prevalence is skewed (one option dominates) and κ is low despite high P̄, also report **Gwet's AC1**
(chance = Σ_c p_c(1 − p_c)/(k − 1)).

### 8.4 Agreement vs correctness (when ground truth g_u exists)
The pairwise metrics below are conditional on both answers being available. Also report correct, false-accept, abstain, malformed, refusal and missing outcomes over **all frozen assigned attempts**, plus contract acceptance, costs and fallback usage. Do not let dropping failures improve the headline denominator. The matched evaluation protocol implements this distinction; see [MATCHED-EVALUATION.md](MATCHED-EVALUATION.md).
For each applicator pair (a, b) over the statements both answered:
- Correct agreement: CA = Pr[x_ua = x_ub = g_u].
- Wrong agreement: WA = Pr[x_ua = x_ub ≠ g_u]. **Share of agreement that is wrong:** WA / (CA + WA).
- Disagreement: D = 1 − CA − WA.
- Error consistency, discrete CAPA (Goel et al.):
  - c_obs = Pr[x_ua = x_ub].
  - c_exp = p_a p_b + (1 − p_a)(1 − p_b) · mean_u 1/(k_u − 1), where p_a and p_b are the two applicators' accuracies.
  - κ_ab = (c_obs − c_exp)/(1 − c_exp).
  - For open types there is no k_u. Use the binary form c_exp = p_a p_b + (1 − p_a)(1 − p_b) on correct/incorrect (Geirhos), which treats "both wrong" as agreement and so *overstates* wrong-answer agreement; say which form was used.
- Consensus value: the accuracy of the consensus vs the best single applicator vs an oracle (any applicator correct).
  Also coverage vs accuracy when contested asks abstain.

### 8.5 Stability metrics (statement fragility)
- **Test–retest (intra-PSS):** α over repeated identical calls per applicator.
- **Paraphrase stability (inter-PSS):** α over canonical and paraphrased renderings per applicator (R16).
- **Permutation invariance:** the share of closed asks whose answer is unchanged under k cyclic option rotations (R9).
- **Flip-to-majority rate** in `ultra`: Pr[the round-2 answer moves to the round-1 plurality | it differed in round 1] (R15).

### 8.6 Uncertainty: cluster bootstrap over statements
Pairs and samples within a statement are not independent.
- RESULTS.md's "62% (207/336; 95% CI 56–67)" applies a Wilson interval to 336 pairs that come from only 16 questions
  (21 pairs each). There are 16 question clusters; the effective sample size and interval depend on within-question dependence and cannot be inferred from that count alone. Treating all pairs as independent is unjustified.
- Procedure:
  1. Draw B = 10,000 resamples of the statements with replacement, keeping each statement's full answer set.
  2. Recompute α, mean P_u, unanimity and the other metrics on each resample.
  3. Report percentile 95% intervals and q = Pr[α* < 0.80].
- Optional: a two-way bootstrap that also resamples applicators, to generalize beyond this panel.
- Krippendorff's own pair-resampling bootstrap (20,000 resamples, D_e fixed) is acceptable for α alone.
- Thresholds such as α ≥ 0.80 are conventions, not universal reliability certificates; choose acceptable error and coverage for the task before evaluation.
- Choose sample size using task families, effect sizes, acceptable error and uncertainty. A historical suggestion of 50–100 statements per cell is not a power calculation; 16 questions provide weak grounds for ranking these rules.

### 8.7 Minimal report table (per suite × condition)
| field | definition |
|---|---|
| N statements, M applicators, families | panel, fixed before the run |
| validity | Σ valid / Σ asked |
| unanimous (≥2 families) | count / N, bootstrap CI |
| mean P_u, mean S_u (closed) | §8.1, bootstrap CI |
| α nominal (α interval for numbers) | §8.2, bootstrap CI, q(α < 0.8) |
| accuracy, consensus accuracy | when ground truth exists |
| CA, WA, WA share, mean κ_ab | §8.4 |
| intra-PSS, inter-PSS, permutation invariance | §8.5, when probes were run |
| contested and ambiguous statements | IDs, sent to the R5 loop |

---

## 9. What Symblic can measure next with the existing bench (no new infrastructure)

Each A/B pair runs on the same panel and statements, reports α with a cluster-bootstrap CI (§8.6), and resumes in a
cool period, per RESULTS §7.

1. **Definitions:** paragraph vs constitution-style `define` (R3).
2. **Option rendering:** letters vs values; canonical vs shuffled order (R9).
3. **Effort:** `low` vs `medium` on closed classification asks. This fills the CoT-vs-direct *cross-model* gap.
4. **Disagreement loop:** before and after a single R5 amendment on the contested identity questions. This tests
   whether a repair transfers to applicators that were not used to find it, the SpecFix claim.
5. **CAD equivalence:** the same parametric spec to every applicator as CadQuery code vs as a closed Record.
   Measure the IoU-bucket fingerprint identity. This closes the cross-model geometry gap (§5).

---

## 10. References

Markers: [V] opened in this survey, [S] snippet or secondary only, [U] standard reference not reopened.

**Prompt sensitivity and order bias**
- [Sclar] Sclar, Choi, Tsvetkov, Suhr. Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design. ICLR 2024. https://arxiv.org/abs/2310.11324 [V]
- [Voronov] Voronov, Wolf, Ryabinin. Mind Your Format. ACL Findings 2024. https://arxiv.org/abs/2401.06766 [V]
- [Mizrahi] Mizrahi et al. State of What Art? A Call for Multi-Prompt LLM Evaluation. TACL. https://arxiv.org/abs/2401.00595 [V]
- [Errica] Errica et al. What Did I Do Wrong? Quantifying LLMs' Sensitivity and Consistency to Prompt Engineering. NAACL 2025. https://arxiv.org/abs/2406.12334 [V]
- [PromptBench] Zhu et al. PromptRobust (PromptBench). https://arxiv.org/abs/2306.04528 [V]
- [ParaRel] Elazar et al. Measuring and Improving Consistency in Pretrained Language Models. TACL 2021. https://arxiv.org/abs/2102.01017 [V]
- [GVCons] Li, Shrivastava, Li, Hashimoto, Liang. Benchmarking and Improving Generator-Validator Consistency of LMs. https://arxiv.org/abs/2310.01846 [V]
- [Moore] Moore, Deshpande, Yang. Are LLMs Consistent over Value-laden Questions? EMNLP Findings 2024. https://arxiv.org/abs/2407.02996 [V]
- [Raj] Raj, Rosati, Majumdar. Measuring Reliability of LLMs through Semantic Consistency. NeurIPS 2022 ML Safety Workshop. https://arxiv.org/abs/2211.05853 [V]
- [Pezeshkpour] Pezeshkpour & Hruschka. LLMs Sensitivity to the Order of Options in Multiple-Choice Questions. https://arxiv.org/abs/2308.11483 [V]
- [PriDe] Zheng, Zhou, Meng, Zhou, Huang. Large Language Models Are Not Robust Multiple Choice Selectors. ICLR 2024. https://arxiv.org/abs/2309.03882 (numbers from https://arxiv.org/html/2309.03882) [V]
- [MTBench] Zheng et al. Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023 D&B. https://arxiv.org/abs/2306.05685 [V]
- [WangFair] Wang et al. Large Language Models are not Fair Evaluators. https://arxiv.org/abs/2305.17926 [V]
- [Calibrate] Zhao, Wallace, Feng, Klein, Singh. Calibrate Before Use. ICML 2021. https://arxiv.org/abs/2102.09690 [V]
- [FantOrder] Lu et al. Fantastically Ordered Prompts. ACL 2022. https://arxiv.org/abs/2104.08786 [V]
- [FeiLabel] Fei, Hou, Chen, Bosselut. Mitigating Label Biases for In-context Learning. ACL 2023. https://arxiv.org/abs/2305.19148 [V]
- [ReifLabel] Reif & Schwartz. Beyond Performance: Quantifying and Mitigating Label Bias in LLMs. NAACL 2024. https://arxiv.org/abs/2405.02743 [V]
- [BatchCal] Zhou et al. Batch Calibration. ICLR 2024. https://arxiv.org/abs/2309.17249 [V]

**Ambiguity and clarification**
- [AmbiEnt] Liu et al. We're Afraid Language Models Aren't Modeling Ambiguity. EMNLP 2023. https://arxiv.org/abs/2304.14399 [V]
- [AmbigQA] Min, Michael, Hajishirzi, Zettlemoyer. AmbigQA. EMNLP 2020. https://arxiv.org/abs/2004.10645 [V]
- [CLAMBER] Zhang et al. CLAMBER. ACL 2024. https://arxiv.org/abs/2405.12063 [V]
- [Tamkin] Tamkin, Handa, Shrestha, Goodman. Task Ambiguity in Humans and Language Models. https://arxiv.org/abs/2212.10711 [V]
- [Underspec] Yang, Shi, Ma, Liu, Kästner, Wu. What Prompts Don't Say. ACL Findings 2026. https://arxiv.org/abs/2505.13360 [V]
- [Qulac] Aliannejadi, Zamani, Crestani, Croft. Asking Clarifying Questions in Open-Domain Information-Seeking Conversations. SIGIR 2019. https://arxiv.org/abs/1907.06554 [V]
- [CLAM] Kuhn, Gal, Farquhar. CLAM: Selective Clarification for Ambiguous Questions. https://arxiv.org/abs/2212.07769 [V]
- [IntentSim] Zhang & Choi. Clarify When Necessary. https://arxiv.org/abs/2311.09469 [V]
- [CLARINET] Chi, Lin, Lin, Klein. CLARINET. https://arxiv.org/abs/2405.15784 [V]
- [APA] Kim et al. Aligning Language Models to Explicitly Handle Ambiguity. https://arxiv.org/abs/2404.11972 [V]
- [SemUnc] Kuhn, Gal, Farquhar. Semantic Uncertainty. ICLR 2023. https://arxiv.org/abs/2302.09664 [V]
- [SemEntropy] Farquhar, Kossen, Kuhn, Gal. Detecting hallucinations in LLMs using semantic entropy. Nature 2024. https://www.nature.com/articles/s41586-024-07421-0 (read via https://pmc.ncbi.nlm.nih.gov/articles/PMC11186750/) [V]
- [Cole] Cole et al. Selectively Answering Ambiguous Questions. EMNLP 2023. https://arxiv.org/abs/2305.14613 [V]
- [StressSpec] Zhang, Sleight, Peng, Schulman, Durmus. Stress-Testing Model Specs Reveals Character Differences among Language Models. 2025. https://arxiv.org/abs/2510.07686 [V]
- [ExpertsRise] He, Zhou, Vanacore, Kizilcec, Huang. Experts Rise Where LLMs Disagree. 2026. https://arxiv.org/abs/2609.26926 [V]
- [CrossModelPPL] Gorbett & Jana. Cross-Model Disagreement as a Label-Free Correctness Signal. 2026. https://arxiv.org/abs/2603.25450 [V]
- [ClarifyGPT] Mu et al. ClarifyGPT. https://arxiv.org/abs/2310.10996 (method: https://ar5iv.labs.arxiv.org/html/2310.10996) [V]
- [SpecFix] Jia, Morris, Ye, Sarro, Mechtaev. Automated Repair of Ambiguous Problem Descriptions for LLM-Based Code Generation. ASE 2025. https://arxiv.org/abs/2505.07270 [V]
- [HumanEvalComm] Wu & Fard. HumanEvalComm. https://arxiv.org/abs/2406.00215 [S]

**Annotation, agreement techniques**
- [Gilardi] Gilardi, Alizadeh, Kubli. ChatGPT Outperforms Crowd-Workers for Text-Annotation Tasks. PNAS 120(30), 2023. https://arxiv.org/abs/2303.15056 [V, full text]
- [Tornberg23] Törnberg. ChatGPT-4 Outperforms Experts and Crowd Workers in Annotating Political Twitter Messages. https://arxiv.org/abs/2304.06588 [V]
- [Tornberg24] Törnberg. Best Practices for Text Annotation with LLMs. Sociologica 18(2), 2024. https://sociologica.unibo.it/article/view/19461 [V]
- [Reiss] Reiss. Testing the Reliability of ChatGPT for Text Annotation and Classification. https://arxiv.org/abs/2304.11085 [V]
- [PSS] Barrie, Palaiologou, Törnberg. Prompt Stability Scoring for Text Annotation with LLMs. https://arxiv.org/abs/2407.02039 [V]
- [Roulette] Haldar & Hockenmaier. Rating Roulette: Self-Inconsistency in LLM-As-A-Judge Frameworks. EMNLP Findings 2025. https://aclanthology.org/2025.findings-emnlp.1361.pdf [V, full text]
- [Codebook] Halterman & Keith. Codebook LLMs. Political Analysis 2025. https://arxiv.org/abs/2407.10747 [V]
- [LabelDefs] Mohammadi et al. Do LLMs Adhere to Label Definitions? EMNLP 2025. https://arxiv.org/abs/2509.02452 [V]
- [Constitution] Berlin & Swanda. Improving Labeling Consistency with Detailed Constitutional Definitions and AI-Driven Evaluation. 2026. https://arxiv.org/abs/2605.24247 [V]
- [CheckEval] Lee et al. CheckEval. EMNLP 2025. https://arxiv.org/abs/2403.18771 [V]
- [TICK] Cook et al. TICKing All the Boxes. https://arxiv.org/abs/2410.03608 [V]
- [FollowBench] Jiang et al. FollowBench. ACL 2024. https://arxiv.org/abs/2310.20410 [V]
- [IFEval] Zhou et al. Instruction-Following Evaluation for LLMs. https://arxiv.org/abs/2311.07911 [V]
- [MinDemos] Min et al. Rethinking the Role of Demonstrations. EMNLP 2022. https://arxiv.org/abs/2202.12837 [V]
- [ToCoT] Sprague et al. To CoT or not to CoT? ICLR 2025. https://arxiv.org/abs/2409.12183 [V]
- [Temp] Renze & Guven. The Effect of Sampling Temperature on Problem Solving in LLMs. EMNLP Findings 2024. https://arxiv.org/abs/2402.05201 [V]
- [USC] Chen et al. Universal Self-Consistency for LLM Generation. https://arxiv.org/abs/2311.17311 [V]
- [eLLM] Kamen & Kamen. Majority Rules: LLM Ensemble is a Winning Approach for Content Categorization. https://arxiv.org/abs/2511.15714 [V]
- [Ding] Ding. When LLMs Agree, Are They Right? 2026. https://arxiv.org/abs/2607.08065 [V]

**Populations, conventions, debate**
- [Ashery] Ashery, Aiello, Baronchelli. Emergent social conventions and collective bias in LLM populations. Science Advances 11(20), 2025. https://www.science.org/doi/10.1126/sciadv.adu9368 (read via https://pmc.ncbi.nlm.nih.gov/articles/PMC12077490/) [V]
- [Topology] Mehdizadeh & Hilbert. Exploring the Topology and Memory of Consensus. 2026. https://arxiv.org/abs/2606.04197 [V]
- [ICCA] Hua & Artzi. Talk Less, Interact Better. COLM 2024. https://arxiv.org/abs/2408.01417 [S]
- [JonesConv] Jones, Lombardi, Mahowald, Bergen. LLMs and people both learn to form conventions — just not with each other. 2026. https://arxiv.org/abs/2602.08208 [V]
- [NoPacts] Wang, Mishra, Özyürek, Rubio-Fernández, Ghaleb. Aligned but Not Partner-Specific. 2026. https://arxiv.org/abs/2606.08081 [V]
- [DeGrootLLM] Yazici, Kayaalp, Taga, Sayed. Opinion Consensus Formation Among Networked LLMs. ICASSP 2026. https://arxiv.org/abs/2601.21540 [V]
- [Chuang] Chuang et al. Simulating Opinion Dynamics with Networks of LLM-based Agents. https://arxiv.org/abs/2311.09618 [V]
- [DebateVote] Choi, Zhu, Li. Debate or Vote. NeurIPS 2025. https://arxiv.org/abs/2508.17536 [V]
- [Estornell] Estornell & Liu. Multi-LLM Debate: Framework, Principals, and Interventions. NeurIPS 2024. https://proceedings.nips.cc/paper_files/paper/2024/file/32e07a110c6c6acf1afbf2bf82b614ad-Paper-Conference.pdf [S]
- [BenchForm] Weng, Chen, Wang. Do as We Do, Not as You Think: the Conformity of LLMs. ICLR 2025. https://arxiv.org/abs/2501.13381 [V]

**Spec to artifact**
- [CADPrompt] Alrashedy et al. Generating CAD Code with Vision-Language Models for 3D Designs. https://arxiv.org/abs/2410.05340 [V]
- [Text2CAD] Khan et al. Text2CAD. NeurIPS 2024. https://arxiv.org/abs/2409.17106 [V]
- [T2CBench] Wang et al. Text2CAD-Bench. 2026. https://arxiv.org/abs/2605.18430 (details: https://arxiv.org/html/2605.18430v1) [V]
- [T2CQ] Xie & Ju. Text-to-CadQuery. 2025. https://arxiv.org/abs/2505.06507 [V]
- [Query2CAD] Badagabettu, Yarlagadda, Barati Farimani. Query2CAD. https://arxiv.org/abs/2406.00144 [V]
- [CADConsensus] Haag, Kacan, Fuchs, Lohse. Test-Time Scaling for CAD Generation via Verifier-Free Consensus Selection. 2026. https://arxiv.org/abs/2608.09706 [V]
- [BRepMatch] Jones, Noeckel, Kodnongbua, Baran, Schulz. B-rep Matching for Collaborating Across CAD Systems. ACM TOG 42(4), 2023. https://arxiv.org/abs/2306.03169 [V]
- [Makatura] Makatura et al. How Can LLMs Help Humans in Design and Manufacturing? https://arxiv.org/abs/2307.14377 [V]
- [Ouyang] Ouyang, Zhang, Harman, Wang. An Empirical Study of the Non-determinism of ChatGPT in Code Generation. ACM TOSEM 2025. https://arxiv.org/abs/2308.02828 [V]
- [MBRexec] Shi et al. Natural Language to Code Translation with Execution. EMNLP 2022. https://arxiv.org/abs/2204.11454 [V]
- [CodeT] Chen et al. CodeT: Code Generation with Generated Tests. https://arxiv.org/abs/2207.10397 [V]
- [FuncCluster] Ravuri & Amarasinghe. Eliminating Hallucination-Induced Errors in LLM Code Generation with Functional Clustering. 2025. https://arxiv.org/abs/2506.11021 [V]
- [CodeEnsemble] Mahmud, Duan, Pasareanu, Yang. Enhancing LLM Code Generation with Ensembles. 2025. https://arxiv.org/abs/2503.15838 [V]
- [PartialOrder] Zi, Menon, Guha. More Than a Score: Probing the Impact of Prompt Specificity on LLM Code Generation. https://arxiv.org/abs/2508.03678 [V]

**Agreement statistics and correlated errors**
- [Kripp2011] Krippendorff. Computing Krippendorff's Alpha-Reliability (2011). https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff%27s%20Alpha-Reliability.pdf [V]
- [KrippBoot] Krippendorff. Bootstrapping Distributions for Krippendorff's Alpha (rev. 2016). https://asc.upenn.edu/sites/default/files/2021-03/Algorithm%20for%20Bootstrapping%20a%20Distribution%20of%20Alpha.pdf [V]
- [HayesKripp] Hayes & Krippendorff. Answering the Call for a Standard Reliability Measure for Coding Data. Communication Methods and Measures 1(1):77–89, 2007. https://www.asc.upenn.edu/sites/default/files/2021-03/Answering%20the%20Call%20for%20a%20Standard%20Reliability%20Measure%20for%20Coding%20Data.pdf [U]
- [Gwet] Gwet. Computing inter-rater reliability and its variance in the presence of high agreement. Br. J. Math. Stat. Psychol. 61(1):29–48, 2008. https://agreestat.com/papers/bjmsp2008_interrater.pdf [U]
- Cohen (1960) κ; Fleiss (1971) κ; Bennett, Alpert & Goldstein (1954) S; Brennan & Prediger (1981); Feinstein & Cicchetti (1990) kappa paradoxes; Krippendorff (2004) *Content Analysis*, 2nd ed. (0.667 floor) [U]
- [ErrCons] Geirhos, Meding, Wichmann. Beyond Accuracy: Error Consistency. NeurIPS 2020. https://arxiv.org/abs/2006.16736 [V]
- [CAPA] Goel et al. Great Models Think Alike and this Undermines AI Oversight. ICML 2025 (PMLR 267). https://arxiv.org/abs/2502.04313 ; https://proceedings.mlr.press/v267/goel25b.html [V]
- [CorrErr] Kim, Garg, Peng, Garg. Correlated Errors in Large Language Models. ICML 2025. https://arxiv.org/abs/2506.07962 [V]

**Not verified in this survey:**
- Exact FollowBench and IFEval scores.
- Estornell & Liu's and Hua & Artzi's numbers (snippets only).
- HumanEvalComm's numbers (snippet).
- CADSmith (arXiv 2603.26512; snippet only, not used).
- BlenderGPT and "LLMs construct 3D objects from text".
- Practitioner claims about per-field voting breaking cross-field consistency.
- Any venue not printed on the page that was opened.
