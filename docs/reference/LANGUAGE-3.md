# Symblic: the abstraction layer (functions, routines, modules, tests, papers, locks)

The installed Symblic 2.5 reform executes formal statements in a kernel and obtains typed answers through model applicators
([SPEC.md](SPEC.md)). This layer builds larger programs from reusable declarations and tests. The file
name is historical; this is not a separate language-version-3 specification. Updated 2026-10-04 for
canonical form 3, execution profiles and module namespaces. Deployment status reconciled
5 October 2026: the reform is installed; [5 October release evidence](evidence/2026-10-05-reform-install.json) and
[REFORM-3](REFORM-3.md) distinguish live checks from component verification. The existing
evidence/certificate contracts remain in [EVIDENCE.md](EVIDENCE.md).

1. A routine is to an ask what a function is to an instruction: a named, typed, reusable contract.
2. A module is a library of such contracts, plus the vocabulary that pins their words.
3. A paper is a program written as a technical document.
4. A compatible, complete lock supports replay without a fresh model call.

| file | role |
|---|---|
| `symblic/lang/abstraction.py` | the `function`, `routine`, `import` and `test` statements (core extensions), `run_tests`, `certify`, `crystallise`, `library`/`describe_module`, CLI |
| `integration/host/symblic_lang_api.py` | their routes under `/api/automation/symblic/` (library, module, tests, paper/*, lock, lock/replay, and `lang/*`: certify and crystallise as background jobs in their own unit `symblic-lang-<id>`, started from the page's Language and Write screens) |
| `symblic/lang/library/*.sym` | the standard library: `units`, `stats`, `dates`, `constants`, `lab`, `kinship`, `graphs`, `text`, `records`, `order` |
| `symblic/authoring/paper.py` | literate papers (`.symd`): compile, check (paper line numbers), reproduce across cohorts, CLI |
| `symblic/kernel/lockfile.py` | lockfiles: freeze a finished run, replay with no model, measure drift, CLI |
| `docs/reference/papers/*.symd` | example papers |
| `tests/lang/test_symblic_lang.py`, `test_symblic_paper.py`, `test_symblic_lock.py` | fakes and temporary folders only |

The statements are registered through the core extension hooks (`symblic.Extension`). symblic/kernel/language.py imports
symblic.lang.abstraction at its end, so every parse and check sees them, whichever module is imported first.

## 0. Grammar of the new statements

The new statements are in the notation of SPEC.md. A statement ends with a period. `Type` and `Expr` are SPEC's types and expressions; `Options` is `key = Expr {"," key = Expr}` with the keys of `use`, except `max_asks` and `side_effects`.

```
function  ::= "function" Name "(" [Param {"," Param}] ")" ["->" Type] "=" Expr "."
routine   ::= "routine" Name "(" [Param {"," Param}] ")" ["->" Type] ["with" Options] ["do"] "."
              {Statement}            (a `return Expr.` ends the call)
              "end" "."
Param     ::= Name [":" Type] ["=" Expr]          (parameters with defaults come last; at most 16)
import    ::= "import" Module ["as" Name] "."
            | "import" Name {"," Name} "from" Module "."
            | "import" String ["as" Name] "."    (a saved program)
Module    ::= [a-z][a-z0-9_]*                      (symblic/lang/library/Module.sym)
test      ::= "test" String ["do"] "." {Statement} "end" "."
call      ::= Name "(" Args ")" | Name "." Name "(" Args ")"     (a qualified call: module alias)
Type      ::= … | Name "." Name                    (a module's type)
```

`import` and `test` are written in lower case, and `function`/`routine` are followed by `Name (`. A line that only starts with one of those words ("Import the data.", "Test it twice.") stays a plain-language step only under legacy execution; explicit/verified profiles refuse implicit
model calls. Names of functions and routines are their own namespace; builtins are reserved.

### Execution profiles and formal statements

`use profile=legacy.`, `use profile=explicit.` and `use profile=verified.` are program declarations.
Legacy is the default; the host may strengthen a declared profile but cannot weaken it or change it in
a nested block. Explicit calls keep legacy conversion/module behavior unless a stronger option is
selected; verified defaults to strict answer coercion and isolated module predicates, adds transitive
purity guards and refuses contested voting. An explicit recorded coercion setting can change its default.
A bare `1 = 2.` still displays false; `assert 1 = 2.` creates a failing obligation.

`{:}` is the empty record; `{}` remains the empty set. The proof builtins use ordinary record/list
values, so human formal statements need no alternate project format:

```symblic
use profile=verified.
let domains = {People: ["Ada", "Ben"]}.
let premises = {everyone: finite_parse('forall x in People: Kind(x:People)')}.
let goal = finite_parse('Kind(People["Ada"])').
let certificate = {version: 1, proof: ["and_left", ["premise", "everyone"]]}.
let receipt = finite_check(domains, premises, goal, certificate).
assert receipt.valid.
```

The caller declares exact finite domains; the model or author constructs a term over the expanded
propositional formulas. The checker does not infer that the listed people exhaust reality, establish
premise truth, or search for a proof. `proof_parse` supports quoted atoms and propositional connectives;
`finite_parse` adds explicitly sorted finite quantification. See [PROOF-TERMS](PROOF-TERMS.md),
[FINITE-LOGIC](FINITE-LOGIC.md) and the operator-only `logic/compile` interface in [SPEC](SPEC.md).

## 1. Functions

```
function hyp(a: Number, b: Number = 4) -> Number = sqrt(a ^ 2 + b ^ 2).
function fact(n: Int) -> Int = if n = 0 then 1 else n * fact(n - 1).
```

- A function is one kernel expression.
- Arguments go by position or by name. Defaults are evaluated in the scope where the function was defined.
- Parameter and result types are checked with the same `check_value` as `let x: T`.
- Recursion is allowed up to 32 nested calls. Every evaluation step counts against the run's kernel budget.
- In the `verified` profile a function cannot call a routine or external adapter, even through another function. Its expression and defaults execute under the same purity guard. The `legacy` profile preserves the historical function-to-routine bridge; it is not a pure-function guarantee.
- A name is defined once while it is in scope. A sibling scope may reuse it: two tests, or two calls of a routine that each define a helper.
- Builtin names are reserved: builtins always win, so a shadowing definition is refused.

## 2. Routines: typed LLM functions with contracts

```
routine colour_of(thing: Text) -> one of {red, green, yellow} with effort=high do
  ask c: one of {red, green, yellow} "What colour is {thing}?"
  ensure c != "green" or thing != "banana" else retry.
  return c.
end.
let a = colour_of("banana").
```

- **Scope.** Each call runs the body in a fresh scope. Its parent is the scope where the routine was defined, so a routine cannot see its caller's names. Names bound inside a routine stay inside it.
- **Return.** `return EXPR.` ends the call, from inside `if` and `for` blocks too. A routine that ends without `return` is an error.
- **The asks inside.** They are ordinary asks: same capsule, typed schema, votes and consensus, `ensure … else retry` with feedback, and the replay record. Nothing about model execution is new.
- **Options.** The options after `with` are the defaults for the asks inside the routine, and only there. The caller's `use` defaults still apply to anything the routine does not set. This is how a library routine leaves the choice of applicator to the program that imports it.
- **Memoisation within a run.** The same lexical closure, full canonical arguments and defaults reuse the recorded value without asking again. A deterministic declaration identity separates helpers created in different enclosing calls. Memo entries retain the original class and observation dependencies; reuse is not a fresh observation or an increase in agreement. Retry rollback restores declarations and memo state.
- **Class.** The class of a `let`/`show` that calls a routine is the worst class of the asks it ran: `let a = colour_of(…)` is `closed`, not `exact`. This uses the core's `kernel.klass` hook.
- **Where a call may appear.** A routine call must be its own statement (`let x = r(…)`), in the run's thread. Inside an ask's text or a parallel `for each` ask it is refused.

## 3. Modules

```
import units.                         # everything public, unqualified
import stats as st.                   # st.variance(xs); constants as st.NAME; types as st.T
import fleiss_kappa, variance from stats.
import "My saved program" as mine.    # an operator-saved program used as a module
```

- **Where modules come from.** A module is a Symblic program from `symblic/lang/library/NAME.sym` (`NAME` matches `[a-z][a-z0-9_]*`), or a quoted saved program. No other path can be named.
- **What a module may contain.** Only declarations: `function`, `routine`, `define`, `term`, `let`, `fact`, `rule`, `import`, `test`, `assert`. Verified-profile module initialization cannot call routines or external adapters, including transitively through helpers. A routine declaration is inert and may be called explicitly after import. Legacy initialization retains its historical behavior.
- **Lexical isolation.** A module has its own variable scope. Verified-profile callables, types and Datalog predicates use an immutable namespace derived from the exact module key, source hash and module-logic semantic version. Importing the same source under two aliases shares one module identity; distinct saved titles remain distinct even when their punctuation normalizes alike.
- **Private names.** Names starting with `_` are not exported.
- **Vocabulary.** Terms remain shared. A term that means something different in two places is an error.
- **Datalog ownership.** Verified modules own the predicates they declare in facts and rule heads, including declarations inside routines. Every query, positive/negative rule literal and nested expression is rewritten into that namespace. Reading an undeclared external predicate fails; a fact hidden only in a skipped test does not declare an input. Modules import relations explicitly, read-only. Imported relations cannot also be defined locally. Legacy-profile modules retain shared global facts and rules.
- **Recorded source and semantics.** The source, SHA-256, module-logic version, namespace mode and imported predicate identities are written to `modules.json`. Resume/replay uses those sources even if the library changes, and refuses mismatched modes or identities. Historical records without namespace metadata replay only with shared semantics. The semantic kernel identity also records the module-logic version.

A public caller uses a module query helper, for example a module containing:

```symblic
fact edge(a, b).
function edges() = query edge(X, Y).
```

After `import "Edges" as e.`, the caller uses `let rows = e.edges().`. A top-level
`query e.edge(X, Y)` does **not** install a public predicate alias. Inside another
isolated module, an explicit import does bind that relation:

```symblic
import "Edges" as e.
rule connected(X, Y) if e.edge(X, Y).
function connections() = query connected(X, Y).
```

`import edge from "Edges".` binds `edge` read-only within an isolated module and
re-exports that relation for further explicit imports. Ambiguous unqualified imports
fail. To extend a relation, define a distinct local rule over the imported relation.

The standard `kinship` and `graphs` libraries intentionally consume global input
facts. Preserve that composition under verified execution with exact host options:

```python
options = {"profile": "verified", "module_logic": {
    "lib:kinship": "shared", "lib:graphs": "shared"
}}
```

The mapping accepts exact `lib:NAME` or `saved:NAME` keys with `shared` or `isolated`.
It is an explicit compatibility policy, recorded for replay. Other verified modules
remain isolated; legacy execution defaults to shared predicates.

**The standard library** (`python3 symblic/lang/abstraction.py lib`, `doc NAME`):

| module | contents |
|---|---|
| `units` | exact conversions (length, mass, volume, pressure, energy, temperature) from exact definitions (1959 yard and pound, US gallon 231 in³, standard gravity, thermochemical calorie). Also terms that give every ask mentioning a unit its definition; `ton` is defined as ambiguous on purpose. |
| `stats` | exact variance/stdev/weighted mean; agreement measures: modal share, pairwise identity, entropy in bits, Fleiss' kappa (exact rational; it reproduces the published worked example exactly: 4211/20059 ≈ 0.210); exact binomial tails `binomial_at_least(k, n, p)`, `binomial_at_most(k, n, p)` (2.3: 18 passes out of 18 leave a true rate of 85% unexcluded at the 5% level). |
| `records` | (2.3) `conflicts(a, b)`: the fields two records share whose values differ; `agree(a, b)`: none differ. Agreement on shared fields is not correctness. |
| `order` | (2.3) yes/no questions A and B asked in both orders, from counts `{yy, yn, ny, nn}`: `share_a_yes`, `share_b_yes`, `share_different`, `order_effect_a`, `order_effect_b` (A asked first minus B asked first) and `qq_gap`, which a projector model predicts to be 0 (Wang and Busemeyer 2013). A gap near 0 does not show that model is right. Example: `examples/14-question-order.sym`. |
| `kinship`, `graphs` | Datalog relations (ancestor, cousin, …; reachable, cyclic, …). A model extracts facts; the kernel computes the hops. |
| `dates` | exact Gregorian arithmetic: leap years, days in a month or year, day numbers, days between, weekday, add days (Hinnant's algorithms; checked against Python's `datetime` from year 1 to 9999); terms for leap and common year |
| `lab` | named recipe conventions as terms (w/w, w/v, v/v, dry-weight basis, ppm, IUPAC STP and SATP) and their arithmetic: wt% masses, slurry masses on a dry-weight or a whole-slurry basis, dilution (C1V1 = C2V2), moles and molarity. A paper still states which convention it uses. |
| `constants` | the SI 2019 defining constants (exact by definition) and exact derived ones (R = N_A k, F = N_A e); import qualified: `import constants as si.` |
| `text` | routines for language work, each a contract with a kernel check:<br>• `yes_or_no` (Bool)<br>• `choose_one` (answers with the option's number, a closed type)<br>• `count_in`, `number_in`<br>• `items_in`: every item must occur word for word in the passage, or the ask is retried<br>• `summary_of`: the word limit is checked<br>• `same_meaning`<br>• (2.3) `quoted_number(passage, quote, value)`: the quote is a span of the passage (`quotes`: same letters and case after NFC and white-space normalisation, whole words and whole numbers) and the value is written in it; `quoted_number_in(what, passage)` asks for a number with that span and retries until it holds. Lexical only: not which thing the number describes, its unit or its truth |

The additive `text.witnessed_number_in`, `text.witnessed_summary_of` and `text.witnessed_items_in`
routines take a separate caller-held source and contract. They check exact code-point spans, field
relationships or declared finite coverage, return scoped receipts, and require strict candidate shapes.
Legacy free-form routines remain available; length and occurrence checks keep their limited meanings.
See [SOURCE-WITNESSES](SOURCE-WITNESSES.md). Explicit quantity builtins are additive too; they do not
change the existing `units` library or infer measurements from bare numbers ([QUANTITIES](QUANTITIES.md)).

## 4. Tests and certification

```
test "the inch is exact" do
  assert convert_length(1, "inch", "cm") = 2.54.
end.
```

- Tests are skipped in a normal run.
- `run_tests(source, applicators)` (CLI `python3 symblic/lang/abstraction.py test FILE|MODULE [--by APP]`) runs the program's declarations, then each test in its own scope. Top-level asks and outputs are skipped.
- Kernel library tests execute without a model; the legacy `text` certification tests call the supplied
  applicators. Report results for their actual source/kernel versions rather than treating an old pass
  as current conformance.
- `certify(source, cohorts, applicators_for)` (CLI `certify MODULE --cohort A --cohort B`) runs the tests once per cohort of agents, each from an empty record, and reports each test's pass rate.
- A routine's **test conformance for a cohort** means that the recorded tests passed for that cohort. Passing is decided by encoded assertions, not agreement; those assertions may still be incomplete or mistaken.

`certify ... --certificate-out PATH` writes a checksum-protected artifact, atomically and with private
file permissions. The report records the source hash, semantic kernel, each cohort's terminal status,
test outcomes/calls and the module sources actually imported. Module drift between cohorts prevents
aggregate qualification. Missing historical provenance is not filled from the current environment.

A certificate may restrict `tools/symblic run ... --certificate FILE` to eligible single-applicator cohorts
and checked escalation. Qualification requires a complete, nonempty, passing suite and actual model
calls: kernel-only tests do not exercise or qualify the named candidate. A council's tests do not qualify
each member separately. Runtime candidates must still pass the current predicate checks.

Certificate scope is the observed tests under the pinned source/module/kernel versions. Its checksum
is not an issuer signature, and requested model labels do not pin a hosted provider's weights or prove
current competence. See [EVIDENCE.md](EVIDENCE.md) for the full limits.

## 4b. Crystallisation: compiling a routine's answers into the kernel

`crystallise(source, routine, domain, applicators, min_agreement=1.0)` (CLI `python3 symblic/lang/abstraction.py
crystallise FILE --routine NAME --domain '[...]' --by APP [--out M.sym]`) works in four steps:
1. It asks the routine once per input of a finite domain, each input with the routine's own votes.
2. It keeps an answer only when every ask behind it reached the agreement bar.
3. It writes the kept answers as a module: a table and a kernel function with the routine's name and signature.
4. That module also carries a self-test and its provenance: the program's SHA-256, who answered, the date, and how many inputs were kept.

Importing the module answers those inputs with class `exact` and no model. An input outside the table fails instead of guessing; call the routine for those. The provenance notes name the agents that answered, their model families, and `kernel_id()`, so a reader sees who agreed and under which canonical regime. `workers=N` asks N inputs at a time, each worker on its own copy of the program, and the table keeps the domain's order. Nested memoised answers retain the agreement evidence of the original asks. The lookup is deterministic; the truth of its entries still requires an independently justified reference. Agreement does not verify the table:
- Literals are written so that they read back to the same canonical fingerprint.
- Drawings are refused; empty records serialize as `{:}` and retain their record identity.

## 5. Papers (`.symd`): a technical paper that agents execute

A paper is Markdown:
- Its prose explains.
- Its definitions (`- **word**: meaning` or `**word** means …`) become `term`s that hold for the whole paper.
- Its ```` ```symblic ```` blocks are the statements. Other code blocks are prose.
- Front matter between `---` lines sets defaults (`by`, `effort`, `votes`, `agree`, `retries`, `budget`, `temperature`, `seed`, `tools`) and `context: sections | section | none`.

Compiling is deterministic and source-mapped:
1. Front matter, then the title, then every definition.
2. Then each section's header and generated context bindings, with `use context=[paper_definitions,
   section_0, …, section_N]` for the selected sections. These are weight-5 Text bindings, not evidence
   that a model understood or attended to the whole paper.

The compiler and runner have separate bounds. Section prose is truncated to its first 8,000 characters
with a compiler warning. With `context: sections`, definitions and the current section are selected,
then the introduction, then earlier sections nearest-first when they fit a 10,000-character prose
selection target. Definitions plus the current section may already exceed that target; later sections
are omitted with warnings. Selected names return to paper order. `context: section` considers only the
introduction and current section; `none` supplies no generated context. An ask's own `context=` wins.

Runtime explicit context names are required and must fit the capsule budget. Verified runtime accounting
also counts system, schema, definitions, formatting and repair text before dispatch. It can therefore
refuse a paper whose compiler selection succeeded. Runtime manifests record the selected binding values;
they do not reconstruct source prose already truncated or omitted by compilation. Ancestor lineage is
metadata, not automatic access to every earlier raw value. Inspect both sets of diagnostics; the paper
compiler has no requirement-completeness proof.

Historical cube-paper measurements (2026-10-02, before canonical version 3), with claude:haiku,
claude:sonnet, claude:opus and codex:
- **narrow context** (own section only): the readers never saw the edge length stated one section earlier. Each needed 2 kernel re-asks (`ensure` feedback) before all four reached the same fingerprint, `bf548ea196d3ca27`.
- **cumulative context**: all four gave that identical record on the first attempt, with 0 re-asks.

qwen3:4b failed both arms (faces that are not flat, open edges).

The definitions go into the context as well as being terms. A term attaches by itself only when an ask's own instruction uses the word, but a paper's words are often in what the ask reads: in the furnace example, the protocol says "room temperature" while the instruction only says "list the steps".

`check_paper` reports diagnostics and the plan at the paper's own line numbers. It also runs a deterministic **lint** for vague quantities: a percentage with no basis, "about"/"approximately" with a number, "a few"/"a couple of", "slowly"/"briefly", "room temperature"/"overnight". A phrase the paper defines is not reported. It flags both drafts (furnace and slurry) before any agent is asked, and none of the defined papers.

**Reproduction** (`reproduce(paper, cohorts, runner)`, CLI `python3 symblic/authoring/paper.py reproduce PAPER --cohort A --cohort B`):
1. The compiled paper runs once per cohort, each from an empty run record; shared training data and model conventions still remain.
2. Every final top-level result is lined up by fingerprint.
3. Each statement where the cohorts differ is reported with its paper line and section. That locates a difference to investigate: ambiguity, a knowledge/extraction error or another cause. It does not by itself prove underspecification. `symblic.authoring.tighten.tighten` can propose a rewrite; the author must assess whether its assumptions preserve the intended claim.

The paper **reproduces** when every cohort finishes with the same run fingerprint under the same semantic regime. The score is the share of model-dependent statements that are identical across cohorts. This is a measured identity criterion; common errors can reproduce too. Kernel results depend on their formal inputs, sources and implementation version.

Examples:
- `docs/reference/papers/scaling-a-recipe.symd`.
- `furnace-schedule-draft.symd` and `furnace-schedule.symd`: the same protocol, written loosely and then with its vague words defined. This pair is the paper → reproduce → tighten loop.
- A reader extracts the recipe's lines as typed records, and the kernel converts and scales them exactly.
- With a careful reader, 1.5 cups of milk for 6 of the recipe's 4 servings is 540 mL, and 200 g of flour is 300 g, exactly.

## 6. Locks

`make_lock(run_folder)` freezes a finished run into one file. It contains:
- the program text and its SHA-256, the inputs and options;
- the modules it used, their actual source hashes and the semantic kernel identity;
- every model answer;
- each top-level result's line, name, class and fingerprint;
- versioned evidence and supported observation/action ledger records.

The lock carries an integrity SHA-256. An edit without a matching checksum is refused, but a writer can
recompute the checksum: this is not a digital signature or an authenticated issuer claim.

`replay(lock)` first validates compatible source/module/kernel and evidence pins, then rebuilds a temporary run folder with an applicator that refuses fresh calls. It either reproduces the locked fingerprint using recorded outcomes or fails. Missing answers/effect receipts and incompatible or legacy unpinned records do not trigger a fresh model call or external action.

`drift(lock, fresh_report)` lists statements with different recorded outcomes. Interpret these under
their recorded semantic versions and inputs; a changed model-derived input can change a later kernel result.

CLI: `python3 symblic/kernel/lockfile.py lock RUN_FOLDER`, `show LOCK`, `replay LOCK`.

## 7. Measured (2026-10-02, real agents on the worker nodes)

The table below preserves historical measurements and fingerprints from the earlier implementation.
It is not a rerun under language 2.1/canonical 3, and historical uses of "certified" describe test passes,
not the new pinned certificate artifacts. These small case studies do not establish general parity
between small and frontier models. New-version receipts are tracked separately in [RESULTS.md](RESULTS.md).

Results are in `automation_data/symblic/bench/lang-20261002*` (private). Each cohort is one agent CLI that starts from an empty record (its own run folder), effort=high (3 votes per ask). The script is `tools/scripts/symblic_lang_bench.py`: a thermal hold at 85 °C until every worker node reads below 75 °C, node-h and node-i avoided, at most 2 concurrent qwen calls.

| experiment | cohorts | outcome |
|---|---|---|
| `certify text` (5 certification tests) | claude:haiku, codex, agy | 5/5 each (190–240 s per cohort). `items_in` passed its lexical checks with reported 100% agreement; completeness and semantic grounding were not established. |
| `certify text` | ollama:qwen3:4b-instruct (worker node CPU, two cohorts) | 4/5 each (48 and 54 min; calls of 30–580 s on busy worker nodes). `summary_of` is **not certified** for qwen: both cohorts' summaries stayed over the 12-word limit after their retries (13 and 14 words), and the kernel refused them. Across all five cohorts, 4 of the 5 routines are certified. |
| `scaling-a-recipe.symd`, five cohorts | claude:haiku, codex, agy, qwen3:4b ×2 | **results reproduce**: the 4 cohorts that finished, **including both qwen3:4b cohorts** (a 4-billion-parameter model on worker node CPUs), all produced `6f9f0545592d6906`. That is the cloud run's fingerprint, and all four are correct. agy did not finish (provider outage; coverage 4/5). |
| `scaling-a-recipe.symd` | claude:haiku, codex, agy | **reproduces**: one run fingerprint `6f9f0545592d6906`, 3/3 correct (540 / 45 / 7.5 mL, 300 g), 6 calls each |
| `furnace-schedule-draft.symd` (vague words) | claude:haiku, codex, claude:sonnet | **does not reproduce**: 3 cohorts, 3 different `steps` readings, traced to paper line 22. Totals ≈574, ≈862 and 1205/3 min: 1/3 matched the intended reference despite the ambiguous wording. |
| `furnace-schedule.symd` (words defined) | same | **reproduces**: `93a84f87d61c14f4`, 3/3 correct (1205/3 min). In an earlier run with haiku and codex (agy failed: provider outage), only the *results* reproduced: haiku filled a field the paper said to leave at 0. |
| `furnace-schedule-contract.symd` (a routine returns only what the result needs) | same | **reproduces**: `05907ee2df654a99`, 3/3 correct |
| `furnace-schedule.symd` → Tighten → held-out cohorts (recorded run) | probes haiku, codex, agy, qwen; clarifier sonnet; held out: opus, gemma3:4b, granite3.3:2b, phi4-mini | **before**: the held-out readers read the steps 4 different ways; only opus reached the defined paper's fingerprint. **After** 2 automatic rewrites (probe agreement 0.33 → 0.67 → 1.0): opus, granite3.3:2b and phi4-mini all produce `93a84f87d61c14f4` (gemma: Ollama crashed, an outage). On this paper, the two completed small-model runs matched the Opus run; this is not a general capability comparison. |
| `slurry-draft.symd` ("200 g of a 40% slurry with 1% dispersant"; readers compute the masses) | same | **reproduces**: `ed86f68967edf163`, all three weigh 80 g alumina, **2 g dispersant**, 118 g water. That is 1% of the whole slurry, while dispersant is usually dosed on the dry powder. The powder is named "alumina" here for publication. |
| `slurry.symd` (both percentage bases defined; the kernel computes the masses) | same | **reproduces**: `4c0232659b24137e`, 80 g, **0.8 g**, 119.2 g (dry-weight basis, as defined) |

The slurry pair shows a limit of the method. Disagreement can reveal underspecification or a reader error; agreement does not establish a faithful specification. Three model families read the vague draft the same way, by a shared default, so reproduction alone could not flag it. Only stating the convention (a definition) made the paper say what its author means. Asking each reader for the readings it sees is what exposed it. The recorded readings probe (`ambiguous=true`, used by Tighten), run on the same draft: two of three readers listed the dry-basis reading word for word ("dispersant is 1% of alumina mass: … 0.8 g … 119.2 g") while answering 2 g. Picking between readings is the author's decision. Tightening makes the choice explicit and visible; it does not make it right. The first clarifier, told to prefer "the most widely used convention", pinned the whole-slurry basis.

Read with care:
- Few runs per condition and a few cohorts each; local-model coverage varies by experiment as the table records.
- These are descriptive case studies, not population-level accuracy estimates.
- What they do show:
  - disagreements in these papers were located by line for investigation;
  - defining its words made three different agents produce identical runs;
  - moving what the kernel can compute out of the reader's hands removed the one residual difference by construction.

## 8. What this layer does and does not claim

- **By construction:**
  - Supported kernel computations specify repeatable results for equal formal inputs and a compatible semantic regime, within resource limits.
  - A compatible, complete lock replays without fresh model calls; missing or mismatched records fail.
  - A routine memo entry reuses one result per closure, canonical argument tuple and defaults within a run, preserving its provenance.
- **Measured, per agent set:**
  - whether a paper reproduces across cohorts, and where it does not;
  - whether a routine's certification tests pass for every cohort.
- **Not claimed:** that different models give identical open text, that agreement establishes correctness, or that passing `ensure`/`assert` proves fidelity to author intent. Predicates establish conformance to encoded requirements; independently validated references are needed for target correctness.
- **Limits:**
  - Legacy/shared-mode Datalog predicates are global. Verified isolated modules use explicit ownership
    and read-only predicate imports; shared compatibility exceptions are recorded.
  - Routines run sequentially in the run's thread.
  - Qualified callable/type/constant access is available to callers. Qualified Datalog imports bind
    relations inside isolated modules; top-level callers use exported query helpers rather than an
    automatically installed public predicate alias.
