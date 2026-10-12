# Symblic 2.5 — specification

For bounded objective-to-program construction through this native runtime, see [MICA](MICA.md). Its outputs are checked JavaScript function scripts or closed ES-module bundles; generated specifications and finite tests do not establish general correctness. Research provenance is in [MICA-SOURCES.md](MICA-SOURCES.md).

Symblic separates executable meaning from model interpretation. Its **kernel** evaluates formal
expressions, logic, sets, Datalog and drawings; an `ask` obtains a typed model answer under an explicit
context policy and optional predicates. Equal formal inputs under the same semantic kernel are intended
to give equal results when execution succeeds within its limits. This does not establish that a formal
statement captures an author's intention or that a model's answer describes the world correctly.

This specification describes the installed reform, language version **2.5**, canonical version **3**.
The [5 October release evidence](evidence/2026-10-05-reform-install.json) and later
parser receipt (not included in this repository) record installation and scoped live checks,
not fresh cross-machine conformance or model-performance results. Historical model results remain in [RESULTS.md](RESULTS.md). See [EVIDENCE.md](EVIDENCE.md) for
provenance and assurance limits, and [PRIOR-ART.md](PRIOR-ART.md) for the research comparison.

| file | role |
|---|---|
| `symblic/kernel/language.py` | pure: lexer, parser, types, values and canonical form, kernel, Datalog, plan/check, capsule, reply parsing, consensus |
| `symblic/adapters/render.py` | pure: deterministic SVG drawings (`flower`, `rose`, `polygon`) in Decimal arithmetic |
| `symblic/kernel/run.py` | the interpreter (`Run`) and the runner process (`--dir FOLDER [--resume]`) |
| `symblic/providers/applicators.py` | applicators: `ollama` (an Ollama server over HTTP), `command:NAME` (a local program the operator configures) and `fake`; the original host also supplied agent CLIs, browser chats, councils and delegation, which are not in this repository |
| `integration/host/symblic_engine.py` | `/api/automation/symblic/` (operator-only, routed by `automation_engine.handle`) |
| `symblic/bench/bench.py` | the benchmark (identity, arithmetic, logic, flowers, shapes, tighten) against ground truth |
| `symblic/adapters/geometry.py` | pure: exact polyhedra (solid validity, exact congruence/similarity, canonical form, drawing) |
| `symblic/authoring/tighten.py` | candidate rewrites, panel diagnostics, fidelity obligations and explicit adoption (§12) |
| `web/studio/symblic.html`, `symblic-page.js`, `symblic.css` | the page: Write, Plan, Runs, Compare, Language, Evidence |
| `examples/*.sym` | example programs (all pass `check`; tests run the kernel ones) |
| `symblic/lang/abstraction.py`, `symblic/lang/library/*.sym` | functions, routines, modules, tests and the standard library (§11) |
| `symblic/authoring/paper.py`, `symblic/kernel/lockfile.py`, `integration/host/symblic_lang_api.py` | `.symd` papers and their reproduction, lockfiles, their routes (§11) |
| `symblic/kernel/evidence.py`, `symblic/kernel/certificates.py` | observation provenance, predicate receipts, source/module/kernel-pinned test certificates |
| `symblic/kernel/effects.py` | registered capability observations/actions, static checks and durable outcome ledgers |
| `symblic/kernel/embed.py` | version-pinned `check`/`run` embedding API with cancellation and event callbacks |
| `symblic/adapters/variational.py` | bounded exact rational SPD quadratic minimization and independent witness verification ([contract](VARIATIONAL.md)) |
| `symblic/adapters/transport.py`, `symblic/adapters/discrete.py`, `symblic/adapters/knowledge.py`, `symblic/adapters/projection.py`, `symblic/adapters/operators.py` | further exact, bounded adapters (§7): 1D Wasserstein-1 distance ([contract](TRANSPORT.md)), ground states of a small Ising model ([contract](DISCRETE.md)), knowledge on a finite set of states ([contract](KNOWLEDGE.md)), the nearest values satisfying linear constraints ([contract](PROJECTION.md)), rational projectors and ordered-question probabilities ([contract](OPERATORS.md)) |
| `symblic/kernel/diagnose.py` | pure: what the kernel can say about a check without a model (retry feedback values, empty-answer and shared-key warnings, option rotations) |
| `symblic/kernel/execution_pins.py` | optional execution receipts: source, inputs, loaded runtime, frozen libraries and used capability contracts |
| `symblic/intent/records.py`, `symblic/intent/store.py`, `integration/host/symblic_intent_api.py` | natural-language interpretation contract, private durable sessions and checked the host executor handoff ([guide](INTERPRETER.md)) |

## Current 2.5 contracts

The original model-backend programming idea remains: a model constructs a typed answer, program,
source witness or formal proof, and an independent check decides whether the candidate satisfies the
encoded contract. A precise statement can improve construction conditions. It cannot promise that a
model will find an answer, repeat its answer, or satisfy an unstated intention.

| Contract | Operational rule in this checkout |
|---|---|
| Execution profile | `use profile=legacy`, `explicit` or `verified`; default `legacy`. A host `options['profile']` may strengthen, never weaken, the declared profile. Declarations are program-level and cannot change in a block. |
| Implicit calls | Legacy bare prose remains a model ask with a diagnostic. Explicit and verified reject it before dispatch. A bare Boolean expression is still a displayed query; `assert` or `ensure` creates an obligation. |
| Verified function purity | Functions and defaults cannot transitively execute routines or external adapters. Static summaries are conservative; runtime purity guards also cover imported closures and module initialization. Legacy function-to-routine bridges remain available. |
| Answer transformations | `coercion=strict` rejects undeclared scalar/container/key/enum conversions and discarded fields. Verified defaults to strict; an explicit coercion option is recorded. Legacy conversions remain available. Declared rounding and set equivalence are still supported. Transformation receipts pin raw and canonical values. |
| Contested answers | Verified refuses contested voting results even with `strict=false`. Agreement remains an observation about supplied samples; it does not establish their truth or independence. |
| Context and evidence | Caller-selected required values must fit; manifests record exact prompt/value identities and optional omissions (§4). Host-assigned claim lineage retains premise conditions through subsequent arithmetic, checks and derived values. |
| Module state | Verified defaults to module identities and isolated Datalog predicates; legacy defaults to shared predicates. Exact host overrides are explicit and replay-pinned ([LANGUAGE-3](LANGUAGE-3.md)). Shared vocabulary is still checked for conflicts. |
| Formal construction | `proof_parse`, `proof_check`, `proof_valid`, `proof_render` and `finite_parse`, `finite_expand`, `finite_check` use caller-held goals/premises/domains and candidate proof terms. They check bounded derivations rather than search for a proof. |
| Exact text relationships | Source witnesses verify caller-declared field, span and finite coverage contracts; free paraphrases remain proposals ([SOURCE-WITNESSES](SOURCE-WITNESSES.md)). |
| Measurements | Explicit quantity records retain dimensions, interval bounds, provenance and validity. Bare `Number` keeps its earlier meaning ([QUANTITIES](QUANTITIES.md)). |

The empty record literal is `{:}`; `{}` retains its existing meaning as the empty set.
`show`, `text()` and interpolation also render an empty record as `{:}`. Version
2.4 rendered that record as `{}`; text comparisons must use the new spelling.
Canonical value encoding and value fingerprints are unchanged (canonical form 3).
For example, a closed proof needs no caller premises:

```symblic
use profile=verified.
let goal = proof_parse('"P" implies "P"').
let certificate = {version: 1, proof: ["implies_intro", "h", ["atom", "P"], ["hypothesis", "h"]]}.
let receipt = proof_check({:}, goal, certificate).
assert receipt.valid and len(receipt.used_premises) = 0.
```

This is intuitionistic propositional natural deduction, including elimination from falsity. It is
not a paraconsistent proof calculus or a general English parser. Quoted sentences are opaque atoms;
empirical truth and premise consistency are not checked. The finite frontend expands explicitly
ordered domains into bounded ground conjunctions/disjunctions; a successful proof is conditional on
those exact domains and premises. Empty domains have explicit semantics. See
[PROOF-TERMS](PROOF-TERMS.md) and [FINITE-LOGIC](FINITE-LOGIC.md) for grammar and limits.

`POST logic/compile` takes named `premises`, `goal`, optional `domains`, and `calls` (1–6). It returns
source, inputs, options and a formalization identity without calling a model. Running the returned
program uses the normal checked construction/retry route. Failure to construct a proof does not show
that the goal is false. Graph execution and policy-learning integration have their own status and
recovery requirements; no universal autonomous operating-system capability follows from these APIs.
[REFORM-3](REFORM-3.md) records component checks and remaining integration work.

## Declared raw JSON Code answers

The explicit suffix `Code json schema "<literal JSON schema>"` requests one raw JSON document and keeps its exact original text, including whitespace, Unicode spelling and numeric lexemes. The schema operand is literal data with no interpolation, file access or evaluation. For example:

```symblic
ask result: Code json schema "{\"type\":\"object\",\"properties\":{\"answer\":{\"type\":\"integer\"}},\"required\":[\"answer\"],\"additionalProperties\":false}" "Return answer as the integer one.".
```

The value remains Code text. This mode does not strip a fence, unwrap an `answer` property, or rebuild text from a provider's parsed object. An exact shape check is independent of later application checks; it does not prove the answer true. Ordinary `Code json` without `schema` retains the fenced-Code behavior below.

The closed subset admits primitive types, scalar const/enum, closed objects, homogeneous arrays, integer bounds, string/item lengths and at most eight complete `anyOf` alternatives. `{}` admits any bounded JSON value. Unknown keywords, references, patterns, conditionals and noninteger numeric schema bounds are refused. Limits are 32KiB/16 levels/4,096 schema nodes and 400,000 reply characters/1.6MB UTF-8/32 data levels/50,000 values/250,000 validation steps. Duplicate keys, nonfinite numbers and invalid Unicode scalars are rejected. An exhausted check is resource/verification unknown and supplies no failed-quality observation or automatic repair; a completed negative shape check is a rejected candidate.

The full schema argument and readable prompt enter existing context accounting, call identity and durable journals before dispatch. Prompt display may factor repeated descriptions; the provider still receives the full expanded schema. Unsupported provider grammar is a visible failure and is never retried with the constraint removed. An explicit failed-launch refusal retained in the authoritative call journal is ungraded verification unknown; error wording alone cannot establish that refusal. The inspected local Ollama route uses its existing format argument; other providers' capabilities and model-quality benefits are not established here. The current adapter can require all listed object properties, so MICA represents optional fields as complete closed alternatives.

New MICA requests that omit `context_chars` default to 32,768 characters, including the full schema cost. Explicit budgets and every already normalized/frozen 24,000- or 40,000-character request keep their original value; this does not change native language defaults or raise an existing run allowance.

Parser/helper and normalizer asset pins change kernel identity. Earlier pinned execution/resume requires its original coherent source closure; read-only historical artifacts are unchanged. See [Declared JSON output shape](STRUCTURED-JSON.md) for exact behavior and limits.

## Preserved 2.4 code-generation contracts

Version 2.4 (2026-10-04) added support for building larger artifacts one checked step at a time:

- **`Code [js|html|css|python|json|sql|sh]`** without the explicit JSON schema suffix is an answer type. The model ends its reply with a fenced code
  block, and the kernel takes the last fenced block, or else the whole reply. No JSON schema is sent and no
  reasoning field is asked for. This avoids requiring code to be escaped inside a JSON string; relative
  model success still requires measurement. Code keeps its characters; only line endings are unified and outer blank lines dropped.
- **`js_test(source, cases)` and `js_run(source, call)`** are an exact adapter. They run JavaScript in a fresh V8
  context per case, inside the Landlock sandbox, with no clock, randomness or I/O ([JS.md](JS.md)). The adapter
  and node versions are in the kernel identity. Both are in `EVAL_DENIED` and the new `SPECULATION_DENIED`:
  `check`, static warnings, empty-answer probes and enumeration never run them.
- **`route=search`** with `samples=K` (1-25, default one per applicator) and `rounds=N` (1-20, default 1) is checked
  search in parallel. K candidates take the applicators in turn with their own seeds: the first at temperature 0,
  the others at 0.7, unless a temperature is set. Each is repaired against its own failures up to `retries` times.
  The selected answer is the pass with the fewest attempts, with ties going to the lowest index, never the first
  to arrive, so the same replies always select the same answer. It is taken as soon as no other candidate can
  still do better, and the others stop before their next attempt. A round with no pass is followed by a fresh one
  (new seeds, no carried feedback). After the last round the run fails at
  the ask, as escalation does. Search needs an anchored `ensure ... else retry` contract, like escalation, and
  refuses voting options.
- **Checked escalation and search use `because`.** A failing check's `because` text reaches the model as written,
  as on the ensure-retry path, followed by bounded answer-only detail when available (§5).
  A rejected `Code` answer is shown back whole (up to 16 000 characters), with "write
  the corrected, complete code".
- **Spec sheets** ([SPEC-SHEETS.md](SPEC-SHEETS.md), `symblic/spec/sheets.py`) compile a strict Markdown description of
  a file into a Symblic program, deterministically. Each unit is a fresh-context `Code js` ask that shows the code
  of the units it uses, then a `js_test` against the sheet's examples, then `ensure ... else retry because`. The
  file is assembled from passing units only. `compile --keep RUN [--redo NAME]` reuses earlier accepted
  leading units as tested literals; `diagnose --run RUN` groups failed examples. The Build page retains its
  Keep action. Accepted source is read by fingerprint, not from truncated trace previews.

Version 2.3 changes what a program can ask of the kernel and of a vote, and what a failed check tells the
next attempt. It adds: the builtins `numbers(text)` and `quotes(passage, quote)` (§7); five exact adapters
(§7); the ask options `permute` and `vote=median` with `within` (§4); model families counted by lineage (§4);
kernel-computed values in retry feedback, a report when retries run out, and the warnings `SYM_VACUOUS` and
`SYM_SAME_KEY` (§5); the library functions `text.quoted_number`, `text.quoted_number_in`, `records.conflicts`,
`records.agree`, the `order` module and exact binomial tails in `stats` (§11). `Any` now has the JSON Schema
`{}` (any JSON value; a provider whose structured output accepts only a schema subset, such as a strict output
schema, may refuse it: give such a field a concrete type when routing to it). Retry requests differ from 2.2, so a 2.2 lock or execution pin is refused under 2.3, as every change of
kernel identity is. The new builtin names are reserved where builtin names already were: a 2.2 program that names a `let`, `given`, `ask`, `group`, `delegate`, `observe` or `act` result, an imported name, a function or a routine one of `numbers`, `quotes`, `wasserstein1`, `ising_minimize`, `ising_energy`, `knows_event`, `common_partition`, `common_knowledge`, `posterior_given`, `agreement_process`, `reconcile`, `is_projector`, `commutator`, `commutes`, `ordered_probability`
must rename it (none in this repository did). `check` now refuses a builtin-spelled `observe`/`act` result or imported name before anything runs; 2.2 refused it only when binding, after the effect. A loop variable or a parameter may still be spelled like a builtin: a name read as a value is always its binding, and a call always means the builtin.
The checks that follow values (information flow, retry anchoring, evidence receipts) now see every name a statement reads, whatever its spelling: until 2.3 they skipped capitalised, `_`-prefixed and builtin-spelled names, and bare query arguments. Only a query's own bare `Capitalised` or `_` argument is a logic variable; a bare lowercase argument is its binding when one exists, else an atom (as in a `fact`, §2). [REVIEW-2.3.md](REVIEW-2.3.md) records where these came from and what was rejected.

Version 2.2 added `quadratic_minimize(A, b)` and `quadratic_verify(A, b, receipt)` to the pure
kernel. Their domain is a finite rational symmetric positive-definite matrix of dimension at most 32;
the implementation imposes bit and work limits. They establish properties of that supplied quadratic,
not of an inferred PDE, physical system or natural-language meaning. Canonical form remains 3, but the
semantic kernel identity also pins the variational adapter version.

The **Interpreter** page helps an operator refine a request into explicit requirements and questions, then
compile it to checked Symblic. It preserves earlier operator text and records model proposals as proposals.
Its generated programs must use explicit statements and typed questions. A successful check establishes
the encoded checks, not equivalence to the operator's unexpressed intention. Translation and execution have
separate displayed model budgets; interpreter calls share one durable budget across retries and phases.
Compilation now includes retained sources, examples, assumptions and optional operator-declared check
expressions, failing explicitly if the complete input exceeds its limit. Coverage artifacts pin source,
inputs and requirements and distinguish predicate presence from execution. An assertion found in source
is not an executed requirement receipt or a proof of prose equivalence; unmapped requirements remain
visible. Examples supplied to the compiler are exposed specification examples, not held-out tests.

Optional `Run` execution pins refuse incompatible source, inputs, runtime or capability contracts before
any statement executes. Imports use captured standard-library sources; saved or uncaptured imports are
refused in this mode. This is a compatibility check for a trusted local runtime, not an authenticity
signature or a sandbox for arbitrary Python extensions.

## 1. Lexical structure

- A statement is one line ending in an optional period. It continues while a bracket or a string is open,
  after a trailing backslash, or onto lines that start with `with`, `from`, `by`, `where` or `for each`.
- Keywords at the start of a statement are case-insensitive: `program note section module use given let
  define fact rule ask ensure assert expect if elif else end for show return draw group forget pin delegate`.
- `program`, `note`, `section`/`module` keep the rest of their line verbatim.
- A line whose first word is not a keyword is **formal** when it parses as one expression that carries something
  symbolic (a symbol operator, a number or string, brackets, a call, `true`/`false`): `x = 4.`, `not false.` and
  `all v in [1, 2]: v > 0.` are `show`s. Otherwise it is **prose**: an ask with a Text answer named `step1`,
  `step2`… in the legacy profile (Symblic v1's form); a sentence made only of words ("Price is high.") stays prose. `Continue with
  context.` gives it `context=all`. v1 directives `Use Model: …`, `Use Provider: …` become `use` options.
- A prose line whose first word is one edit away from a keyword and that parses as that keyword's statement
  (`lett y = 2.`) is a syntax error ("did you mean `let`?"), never a model call. More distant typos
  can still be legacy prose; explicit/verified reject all implicit prose calls.
- Comments: `#` to the end of the line; a whole line starting with `//`.
- Strings: `"…"`, `'…'`, triple-quoted for several lines. `{expression}` inside a string is interpolated;
  `{{` and `}}` are literal braces.
  Parser revision 3 preserves a literal backslash immediately before doubled braces, including
  generated JavaScript regular expressions. Legacy `\{` / `\}` escapes still read as literal braces;
  NUL and SOH characters remain data rather than internal interpolation markers. The parser revision
  participates in the kernel identity, so prior run evidence retains its original identity.
- Numbers are exact decimals (`0.1` is 1/10). `a..b` is an inclusive integer range.
- Unicode logic is accepted: `∧ ∨ ¬ → ↔ ∈ ∉ ∪ ∩ ∖ ⊆ ∀ ∃ ≠ ≤ ≥ × ÷`.

## 2. Statements

| statement | meaning |
|---|---|
| `program Name.` | the program's name |
| `use key=value, …` | defaults for later asks, including `by effort context votes ahead weight retries temperature seed budget agree strict tools route coercion`; `profile` is a program declaration |
| `given x: T = default.` | an input; required when there is no default |
| `let x: T = expr.` | a kernel binding (single assignment: a name is bound once per scope) |
| `define Name as T.` | a named type |
| `term word means "definition".` | shared vocabulary: every ask whose text mentions the word gets the definition in its capsule (DEFINITIONS) |
| `group g = ["claude:haiku", {app: "ollama:qwen3:4b-instruct@node-a", weight: 2}].` | named applicators |
| `fact p(a, b), q(c).` | Datalog facts (ground: no logic variables); a bare lowercase name is an atom unless it is bound |
| `rule head(X, Y) if p(X, Z) and q(Z, Y) and not r(X) and Y != X.` | Horn rule; Uppercase names are logic variables; negation is stratified; rules must be range-restricted (`N = A + 1` binds N) |
| `ask x: T "instruction {expr}" [for each v in xs] [from a, b] [by app] [with options]` | a model statement (§4) |
| `ensure cond [else retry|fail|warn] [because expr].` | a postcondition; `retry` re-runs the statements from the ask it reads (§5) |
| `assert cond.` / `expect cond.` | a hard check: the run fails if the encoded predicate is false |
| `if c then … elif c then … else … end.` | branches bind into the same scope; `check` treats a name as bound after the `if` only when every branch binds it (a missing `else` binds nothing), and reading a name only some branches bind is an error |
| `for v in xs do … end.` | a child scope per iteration; every name bound inside becomes a list after `end` |
| `show expr [as label].` / `return expr.` | outputs; a bare expression line (`4 + 4 = 8.`) is a `show` |
| `draw expr [as "file.svg"].` | saves a kernel drawing |
| `forget a, b.` | hides results from later contexts (they stay usable by name and by `from`) |
| `pin a with weight=8.` | raises a result's weight |
| `delegate job = "task" to "AGENT" [with cwd=…].` | asks the embedding host to start a coding agent (the applicators object must provide `delegate`); needs side effects allowed |

## 3. Types and values

`Int`, `Int in a..b`, `Number`, `Number to N places`, `Number in a..b`, `Bool`, `Text`, `Text up to N words`,
`one of {a, b, pale-yellow}` (options may carry operational definitions: `one of {fruit: "the seed-bearing part
grown from a flower", vegetable means "…"}`, shown to every applicator with the option; options are words, distinct
after case/space/punctuation normalisation; numbers use `Int in a..b`, true/false use `Bool`),
`List of T [length n | length a..b]`, `Set of T`, `Record {f: T, …}`, `Svg`,
`Any` (including a valid `null` answer), and named types. Record literals use `{f: value}` and `{:}`;
`{}` is the empty set. A type compiles to JSON Schema (§4) and checks the reply. With legacy
coercion (`coerce`), accepted conversions include integers
from `"8"` or `8.0`; numbers exactly (floats read through their decimal repr), rounded half-up when
`to N places`; enums by case/space/punctuation-insensitive match to exactly one option; booleans from
`true/false/yes/no`; records ignore extra fields and match field names case-insensitively; lengths and
ranges are enforced by the kernel independently of provider schema support. Strict coercion refuses
fuzzy key/enum matching, dropped fields and undeclared scalar/container conversions; declared numeric
wire strings, rounding and set deduplication remain supported.

Count positions in `to N places`, `up to N words`, and list/set `length` bounds
require integer literal spelling. For example, `length 2` is valid; `length 2.0`
and `length 2e0` are syntax errors, even though those spellings are valid numeric
expressions elsewhere. Parser revision 2 reports an invalid count at its exact
line and column, including nested declarations, instead of exposing a raw
conversion exception. This retains the existing integer conversion behavior;
it introduces no new accepted-count limit. A recognized keyword typo with an
invalid count also refuses rather than becoming an implicit prose request.

Numeric strings must be a whole signed decimal, scientific notation or fraction. `"26.2 miles"`,
`"26.2 km"`, currency, percentages and explanatory prose are refused as `Number`; numbers are never
extracted from them. Represent a quantity with an explicit unit field and perform its conversion in
the kernel (the existing `units` and `lab` libraries provide conversions and recipe conventions).
Text coercion applies NFC, normalizes line endings, strips outer whitespace and removes trailing whitespace per line; enum matching
normalizes case/space/punctuation as above. These input conversions are distinct from the exact
canonical identity of an already constructed string.

**Canonical form** (`symblic.canon`, `CANON_VERSION` 3): integers stay integers; other rationals are `{"#q": "p/q"}`
(a record key that itself starts with `#` is escaped, so a record can never collide with a tag);
text retains its exact code points, whitespace and line endings; sets are sorted by canonical JSON; record
keys are sorted; drawings are their SHA-256. Typed set members and Datalog facts distinguish `true`
from `1` and preserve structured values. Numerically equal rational representations have one numeric
identity. `canon_text` is a separate, explicit normalization helper, not the identity rule for strings.
A **fingerprint** is the first 16 hex digits of SHA-256 over
the canonical JSON (sorted keys, no spaces). A run's fingerprint hashes every top-level binding's and
every output's fingerprint in order. Fingerprints are compact comparison keys, not collision-free proofs
or signatures. Version-2 fingerprints must not be used as version-3 conformance expectations.

**Determinism classes** (shown per statement): `exact` (kernel), `closed` (Bool, enum, Int range of at
most 1001 values, records of those), `structured` (numbers, lists, records), `open` (text), `observed`
(capability acquisition), `effect` (external actions). A class describes the computation's mechanism,
not a probability of correctness.

## 4. Asks

For each ask the interpreter builds a **capsule** (`symblic.capsule`): system instructions,
program/statement identity, selected context and declared facts, definitions, examples, candidates,
repair feedback and answer format/schema. Runtime context labels identify conditional premises and
proposals. Weight ≥5 changes packing/display priority; it is not truth, authority or a guarantee of
model attention. Compatibility callers without provenance retain explicitly qualified `KNOWN` labels.

`from` names and explicit `context=[...]` names are required. They must fit as complete selected
values or packing fails before a call. Other selected context is optional, ordered deterministically
by required status, weight and row identity. Included/omitted manifest entries retain claim/value/display
hashes and reasons; no omitted optional row is described as necessarily lower weight. Ancestry remains
lineage metadata: forgotten or unrequested parent values are not automatically expanded into prompts.

The default budget is 12,000 Unicode characters. In verified execution it covers the system string,
serialized schema and complete prompt, including fixed formatting, definitions, examples and feedback.
Each repair is rechecked before dispatch. Legacy/explicit budgeting retains the historical context-row
scope, while recording total request characters separately. These counts are not provider tokens and
do not include a provider's hidden wrappers. Paper compilation can already have omitted or truncated
prose before this runtime boundary; inspect its warnings as well ([LANGUAGE-3](LANGUAGE-3.md)).

The installed capsule manifest 5 retains the legacy/explicit row accounting
introduced in manifest 3.
Its provenance annotations have a separate allowance equal to the row budget;
withheld annotations remain in a detached, deduplicated manifest table addressed
by each row's `provenance_sha256`. That table is bounded to 16 MiB and overflow
refuses before dispatch. Facts share explicitly opened and closed provenance
groups, so a later group cannot inherit an earlier group's attribution. Verified
execution includes these annotations and delimiters in the complete request budget.
Packing and display preserve numeric declaration/fact order.

Definitions display as JSON-quoted author text. Statement lines imitating host
headers or provenance rows are visibly quoted. This preserves their authored
meaning while distinguishing them from host metadata; it does not establish
that a model will ignore every adversarial instruction. Omitted optional context
produces one `SYM_CONTEXT_OMITTED` warning per statement line.

| option | values |
|---|---|
| `context` | `none` (default: only `from` names), `all` (every visible result with weight > 0; facts too), `last N`, `relevant` (top 6 by word overlap with the instruction: deterministic), `facts`, `[a, b]` |
| `effort` | `low` (answer only), `medium` (reason, then answer; default), `high` (3 votes), `max` (5 votes), `ultra` (5 votes, then each applicator sees up to 6 anonymised candidates with their reasons once and answers again; the second round decides) |
| `votes` | number of samples (at least one per applicator); sample 0 runs at temperature 0, the others at 0.7 with seeds `seed + i` (local models; cloud CLIs take no temperature) |
| `ahead` | first-to-ahead-by-k: sample a batch per applicator at a time and stop once the leading answer has k more votes than the next |
| `key` | a kernel expression over `it`: votes are grouped by `key(it)`'s fingerprint (`key=eval(it)`: formulas with the same value agree); an answer the kernel cannot key is discarded before the vote (red flag) |
| `agree`, `strict` | the share the winner needs (default 0.5; a tie at the top is contested); with `strict` a contested ask fails the run |
| `families` | N: the winning answer must be backed by at least N model families, else the ask is contested. Families are counted by lineage (below): a largest set of supporters whose known lineages do not overlap. This is a diversity filter, not evidence of statistical independence |
| `weight` | 0–10; 0 excludes ordinary implicit selection, while explicit `from`/context names remain usable; ≥5 gives packing/display priority |
| `retries` | repair attempts per sample and ensure-retries (default 2, at most 5) |
| `by` | an applicator, a list, or a group (§6) |
| `tools` | `none` (default) or `web` (claude/codex only, the fleet runner's web profile) |
| `temperature`, `seed`, `budget` | as above (a program's exact `0.7` reaches the applicator and the replay key as the float 0.7) |
| `vote` | `whole` (one fingerprint per answer), `fields` (a record voted field by field; if the assembled record fails a whole-record `ensure`, the most common whole record is substituted without a model call before anyone is re-asked), `auto` (fields when a record has ≥ 3 valid answers), `median` (numeric answers: the weighted lower median, below) |
| `within` | with `vote=median`: an exact tolerance T ≥ 0; answers within T of the median support it (default 0) |
| `permute` | K (2 to 6), on a vote whose answer type has a `one of`: the vote is taken K times with the options listed in K rotated orders (statement, answer format and schema), same seeds and temperatures; all samples are pooled. The ask is stable only when every rotation has a valid, uncontested winner and they are all the same; otherwise it is contested (`unstable_order`; `meta.permutation` says which orders gave no valid answer, which were contested, and whether the winners differ), a warning says so, and with `strict` the run fails. Not with `ahead`, `vote=median` or `route=escalate`. K rotations cost K times the calls, and rotations by the same models are not independent readers |
| `examples` | `[[question, answer], …]` worked examples, type-checked, shown identically to every applicator |
| `solve` | let the kernel answer when enumeration finds exactly one value that passes the ask's checks (§5) |
| `determine` | Boolean, default `true`. `false` skips runtime finite-domain enumeration and empty-answer probes; returned answers still undergo their ordinary type and predicate checks. Incompatible with enabled `solve` or only `kernel` applicators (§5) |
| `route` | `vote` (default); `escalate`: try applicators in declared order and accept the first answer passing a supported kernel contract (§5), with no voting or confidence inference; `search`: checked candidates in parallel; the pass with the fewest attempts, then the lowest index, wins (2.4, above) |
| `samples`, `rounds` | with `route=search`: candidates per round (1-25, default one per applicator) and fresh rounds after a round with no pass (1-20, default 1) |
| `ambiguous` | `true`: each applicator also returns `"readings"`, the statement's alternative readings (≥ 2) when it sees more than one; they are recorded in `meta.ambiguity` and as a run warning. `fail`: the run stops (kind `ambiguous`) when any reader lists two readings |

**Answer schema.** `{"answer": T}`; models without native reasoning get `{"reasoning": string, "answer":
T}` with the reasoning field first. Schema transport and constrained decoding depend on the applicator;
there is no universal guarantee of free reasoning followed by constrained decoding. Agent CLIs (claude, codex, agy,
copilot) reason natively, so their schema has no reasoning field (on Claude such a field can be refused);
the engine gets the effort instead (`low→low … ultra→max`; codex max→xhigh; agy without a model gets none).

**Consensus** (`symblic.consensus`): valid answers grouped by fingerprint, weighted by applicator weight;
ties go to the group whose first supporter comes earliest in applicator order, then the smaller canonical
form — never to arrival order. Reported: agreement (winner's share), distinct answers, entropy in bits and
normalised by log2 of the number of answers (so a 2-way split of 7 answers reads lower than a 7-way split), the
model families behind the winning answer, the tally, and every sample (applicator, node, round, latency,
reuse, readings, rotation). A capsule lists DEFINITIONS (terms the instruction mentions) and WORKED
EXAMPLES when the program gives them; both are computed per ask (and per item of `for each`).

**Median vote** (`symblic.consensus_median`, `vote=median`): for Int and Number answers. The winner is the
weighted lower median: the smallest answer whose cumulative weight reaches half the total, so it is always a
value some applicator gave. It resists some outliers, but changing a minority can still change the
selected median when the remaining distribution straddles the decision boundary. `agreement` is the share of weight
within `within` of it; `spread` reports the smallest and largest answer and the weighted median absolute
deviation. Weights and the tolerance are exact. A median of wrong readings is wrong: the vote measures
agreement, as every vote does.

**Families by lineage** (`family_of`, `lineage_of`, `families_of`). A label's family is the maker of its base
weights: the model it names (`copilot:claude-sonnet-4.5` is anthropic), else the engine's own maker. A
distilled model descends from two makers, its base weights and the teacher whose outputs trained it
(`ollama:deepseek-r1:7b` is alibaba and deepseek; the table is from the Ollama library page read on
2026-10-03, and the `8b` and `latest` tags are left unattributed because the tag has pointed to different
bases). A front-end that names no model (`copilot`, `council`) and a model of unknown lineage are
`unattributed` and add no family. `families_of` returns a largest set of supporters whose lineages do not
overlap, so a distill and its base, or two distills of one teacher, count once. Evidence records the model a
reply reports beside the requested label and says which the lineage was read from. Family labels do not
establish independent errors.

Applicator records may additionally declare `mode`, `sources` and `assumptions`. These are provenance
labels supplied by the author; they change neither votes nor confidence. Evidence records shared
dependencies, missing declarations and `independence: not_established`. Repeated or memoised values
retain their earlier observation dependencies. See [EVIDENCE.md](EVIDENCE.md).

## 5. Checks and retries

`ensure c else retry` is anchored to the nearest earlier ask in the same block that it reads: directly, through
the bindings between them, or through the knowledge base (a `fact` built from the answer feeds a `query`/`holds`
in the check, also through rules). **Retries are transactional:** the run's state is snapshotted when the anchor
ask starts, and a failed check restores it (bindings and their weights, facts and rules, outputs, warnings,
notes, types, terms, groups, defaults, routine memo entries and declarations) before the ask runs again,
with feedback naming rejected values and the failed condition. Feedback may also carry bounded details
computed from the answer alone, including when an author supplied `because` text
(`half = 1.5`, or `fails for i = {…} (item 3 of 4)` for a supported quantifier).
A part that reads any other name (an input, an observation, another statement's result) is never
evaluated for this, shown or named: showing it would hand the model the expected value. A `because` message is
used as written; any automatic detail is appended separately. Only earlier executed bindings can authorize
that detail: a later shadowing `let` cannot make an earlier input answer-derived. Calls, audit events and pinned module
source records remain as evidence and replay inputs. A retry is not an erasure of its history. Effects
in a retry region are refused; static analysis follows locally declared routine calls, and runtime gates
cover executed extensions. Ledger-backed observations may be retried: the same acquisition key reuses
its outcome, while changed arguments identify a new read. After the retry limit the run fails at the ensure, and `report.diagnoses` records the
answers that check rejected and their pattern: `same` (every attempt gave one answer, so the check, the answer
type or the input may be what is wrong), `different` (each attempt differed, so the statement may be read in
more than one way) or `mixed`. The pattern is a hint for the author, never a verdict; checked escalation
reports it the same way.
`ensure … else warn` records a warning; `else fail` and `assert` fail immediately. Agreement is never treated
as correctness. Checks establish **conformance to the encoded predicates**, conditional on the kernel,
inputs and assumptions. A weak, mistaken or circular predicate can accept a wrong answer.

Failed `assert`/`expect` statements (including those in `test` bodies) can append `In this check:` details
to the author's report. These may show condition inputs visible to the author; that authority is not used
for model feedback. Optional explanations reuse the existing diagnostic helper under a conservative
envelope: 512 AST work items, 24 structural levels, 8,192 characters and 32,768 exact-number bits, with
separate equivalent limits for input values and 2,000 diagnostic steps. Final detail remains at most
400 characters. Queries, helpers, adapters, dynamic evaluation, comprehensions and potentially growing
text/container operations are excluded. Unsupported or oversized expressions simply omit the detail;
the original check, failure, acceptance rules and program budget remain unchanged. Retry prompt budgets
include the appended text and can refuse before another model call.

**Warnings about the checks themselves.** `SYM_VACUOUS`: the checks anchored to an ask accept its empty answer
(an empty list or set, `""`, 0, or a record of those), so they cannot tell an empty answer from a real one.
`check` reports it when the checks read the answer alone; a run reports it whenever its kernel can evaluate
them. A legitimately empty answer also triggers it, so it is a warning and never a refusal.
`SYM_SAME_KEY`: two `act` statements that can run on one path name the same capability and the same literal
key. An action with a key happens once ([EFFECTS.md](EFFECTS.md)), so the later statement would be served the
earlier one's outcome whatever its arguments say. Statements in different branches of one `if` are not
compared.

**Determination by enumeration.** When an ask's type has a finite domain (Bool, enums, Int ranges, records and
sets of those, fixed-length lists; at most 20 000 values) the interpreter can evaluate candidates against
supported anchored checks. The current evaluator accepts intervening `let`/`ensure` statements with
builtin kernel calls only: no user functions, routines, extensions or nested model calls, and no `for each`
ask. Its report includes domain size, evaluated count, `exhaustive`, witnesses and a verdict. Enumeration
may stop once many passing values establish underdetermination; an incomplete search is never a uniqueness
proof. An exhaustive empty result is `contradictory` and fails before a model call; one passing canonical
value is `determined`; several are `underdetermined`. Unsupported or over-limit domains have no such proof.
With `solve` (or only `kernel` applicators), a determined ask returns the unique value with zero model calls.

When the existing `solve` option can be read without evaluation as off and the ask has a model applicator,
runtime enumeration and the empty-answer probe share an optional allowance: at most 50,000 admitted kernel
steps and one quarter of the run's remaining steps. Each admitted charge also spends the real run budget;
retries never refund it. Reaching this allowance stops optional assessment and leaves the ordinary model
and returned-answer checks in place. A partial scan with zero or one passing values is `unassessed` with
reason `budget`, never contradictory or unique. Two checked witnesses establish underdetermination even
without an exhaustive scan. Explicit `solve=true`, `solve=auto`, kernel-only applicators and dynamic solve
expressions retain full-budget enumeration. `determine=true` enables assessment under this policy; it does
not force exhaustive search. The allowance counts admitted kernel charges, not CPU time, memory or work
performed before an aggregate charge. An oversized refused charge latches the shared allowance exhausted.

`determine=false` explicitly selects model construction without runtime speculative assessment. It skips
both enumeration and the runtime empty-answer probe, even for a one-value domain. It does not weaken the
checks applied to an actual answer, including retries, checked escalation and search. The determinacy
receipt remains `unassessed` with reason `author_disabled`; it records no passing set or uniqueness result.
Use `solve=false` with this option: enabled `solve` or a kernel-only applicator list is a configuration
error before dispatch. Like other ask options, `determine` can be set with `use` or host defaults and
overridden on an ask; each explicit value must be a Boolean. This is a runtime control, not a switch that
disables source checking or the separate `check` command's static lints.
Uniqueness concerns the declared domain and predicates, not their faithfulness to an external target.
Every attempt's determination is retained in `report.evidence.determinations` and a `determination`
trace event, including witnesses on failure. Partial scans retain `domain`, `evaluated`, `accepted`,
`exhaustive`, `reason` and `assessment_budget` there; the concise `report.determinacy.asks` receipt retains
the unassessed reason. Exhaustion of the shared runtime probe allowance also emits an `optional-assessment`
trace event with its limit and admitted charge. A real run-budget failure or stop still propagates.
A kernel-only underdetermined ask fails with
`SYM_UNDERDETERMINED`; it never chooses one admissible value and calls it unique.

**Explicit finite fallback after rejected proposals.** A top-level sequential Text or enum ask can
opt in with `fallback_choices=["expression one", "expression two"]`. This is a per-ask source literal,
not a `use` or host default: 1–16 distinct exact strings, each at most 4,096 UTF-8 bytes and valid under
the strict native answer decoder. It requires the verified profile, `constructor="off"`,
`determine=false`, `solve=false` and the ordinary vote route. Exactly one anchored
`ensure ... else retry` must follow, with only supported pure function and `let` declarations between.
Combine all local predicates in that one conjunction. Recursion, effects, routines, dynamic evaluation,
external adapters and nested asks in this retry window are refused before dispatch.

After a typed model proposal fails and exhausts its correction budget, the interpreter restores the
pre-ask snapshot, binds the next authored candidate, and runs the ordinary declarations and original
check again. It adopts the first passing candidate in source order; at most the menu size is tried,
with no additional model calls. This is post-rejection finite completion, separate from speculative
`determine` assessment, and establishes no uniqueness. Type/domain failures within the check reject a
candidate. Provider refusal, an answer that cannot bind, stop, unavailable checks and resource/budget
failures remain visible failures, never evidence against a candidate. Unaccepted provisional bindings
are removed on interruption or failure. If every candidate fails, the run fails.

Accepted host choices carry `answered_by_finite_fallback`, an exact source/menu/predicate/kernel receipt,
and a `finite_fallbacks` report row with trial count and surviving check ID. Their origin is the host;
model identities, votes and agreement are not attributed to the replacement. Original model calls and
failed attempts remain recorded. Replay and resume retain this distinction. Passing these predicates
does not establish that the authored menu or checks fully represent the user's objective.

**Checked escalation.** `route=escalate` requires this supported contract. It tries applicators in their
declared order, checks each typed candidate before selecting it, and stops at the first passing answer.
Repairs are bounded and disclose the prior answer and failed predicate. Author `because` text and
appended answer-only detail follow the same bounds and disclosure rules above.
Explicit voting options,
multi-family requirements and `effort=ultra` are incompatible. If no candidate passes, the run fails.
An escalation's legacy `agreement=1` field means `single_selected_answer`, not unanimity; aggregate
agreement excludes it and other single-answer/kernel-only cases, and requires at least two valid
answers in the final voting round. Failed attempts are not votes. Certificates can restrict eligible
applicators but never bypass the candidate checks. See [EVIDENCE.md](EVIDENCE.md).

**Embedded automatic routing.** An embedder can pass `by="auto"` and an `auto_route`
object with 1–12 concrete `candidates`, `max_calls`, `repairs`, and `allow_cloud`.
Without explicit voting/route options, candidates are tried in order. A supported
anchored contract is checked before binding; otherwise acceptance establishes only
the declared type (`validation_scope=declared_type_only`), not semantic correctness.
The automatic route reports no measured agreement. Explicit voting uses the primary
candidate; councils are separate orchestration, never hidden inside this call budget.
An `ambiguous=fail` response stops rather than escalating. A protected acquisition
(`lab-confidential`, `confidential`, or `mixed`) keeps later automatic asks local for
the rest of the run, including after a routine or loop exits. This conservative rule
does not claim minimal information-flow analysis. Explicit program applicators remain
explicit choices; `auto` is an interpreter option, not a provider engine.

Runnable examples: [checked routing and kernel solving](../../examples/11-checked-routing.sym) and
[finite ambiguity witnesses](../../examples/12-finite-ambiguity.sym). The first runs without models with
`tools/symblic run examples/11-checked-routing.sym --by kernel --max-calls 0 --json`.
The second intentionally fails with `SYM_UNDERDETERMINED`, witnesses `[2, 3]` in
`evidence.determinations`, and zero calls; inspect its JSON report rather than treating a nonzero
exit status as an unexpected test failure.

## 6. Applicators and placement

Spec: `engine[:model][@node][+effort][*weight]`. The engine names the language knows are
`kernel claude codex agy mistral copilot gemini chatgpt ollama command council fake`
(`symblic.kernel.language.ENGINES`). The applicators shipped in this repository
(`symblic/providers/applicators.py`) run three of them: `ollama` (one HTTP call to an Ollama server; the
answer's JSON Schema becomes Ollama's `format`, and temperature and seed are recorded), `command:NAME` (a
program the operator configured as `SYMBLIC_COMMAND_<NAME>`: prompt on stdin, answer on stdout; use it to wrap
an agent CLI) and `fake` (scripted answers for tests). The other names label agent CLIs, browser chat services
and councils; an embedder may supply applicators for them, and the original host did. `kernel` solves
supported unique finite contracts and refuses other asks.

**Placement on the original host (2026-10-02).** On the private machine Symblic was built on, a CLI or Ollama
call without `@node` went to one of a few worker nodes (for Ollama one that had the model, for a CLI one where
that agent was signed in, preferring the node with the fewest of the run's calls in flight), after a capacity
check by the host's job runner. That scheduler is not part of this repository. Here an `ollama` call goes to the
server its `@HOST` names, or to a server listed in `SYMBLIC_OLLAMA_HOSTS` that has the model.

## 7. Kernel

Exact rationals for `+ - * / // mod ^` (integer powers exact; fractional powers, `sqrt` of non-squares,
`sin cos exp ln radians pi e` are Decimal series at 40 digits, rounded to 30 places, with a fixed local
Decimal context). These transcendental values are deterministic approximations, not exact real numbers.
Comparisons chain (`1 < x < 3`); `=` is equality in expressions; `in`, `subset`,
`divides`; `all/any/none x in xs: p`; comprehensions `[e for x in xs if c]`; records `r.f`; lists index
from 1 (negative from the end); `if c then a else b`. Builtins: see the page's Language screen or
`symblic.BUILTIN_DOCS`. `eval(text, name=value)` parses a model's formula as a Symblic expression and
evaluates it with only the names given (no Python `eval`), without `eval`, `matches` or the renderers.
Parser revision 1 keeps a 60-level syntactic nesting bound and separately limits
constructed expression trees to 128 nodes along a branch. Long shallow collections
and comparison chains remain supported. Oversized formal structures produce syntax
errors and never become model requests. Terminal-period comment scanning uses one
linear pass over the statement. Both depth limits are part of kernel identity.

Default limits: 200 000 kernel steps, 100 000-item ranges, 200 000 facts, 400 asks per run (`max_asks`),
2 000 fresh model calls (`max_calls`, shared by votes, repairs and escalation), and 4 000
digits for any numerator or denominator (literals, powers, every builtin result), below CPython's default
int-to-text limit. Supported runtime configurations and input limits remain part of the
compatibility contract; a language bound is not proof of behavior under arbitrary interpreter settings. Text builtins read non-text
values through `show` (sets in canonical order), never Python's `str`, so nothing depends on the hash seed.
`numbers(text)` returns the plain decimal numerals written in a text (at most 20 000 characters), in order,
as exact numbers: an optional `-` or `−` sign, ASCII digits with optional comma thousands groups, an optional
decimal part (`"$1,250.00 for 3 (−5.5%)"` gives `[1250, 3, -5.5]`). A numeral that is part of a longer token, a
fraction or date with `/`, a power, an unspaced product, scientific notation, a decimal comma or a non-ASCII
digit is not read, so that no fragment passes for a number; nor is a numeral after a dash or ± (`–5`), in spaced
scientific notation (`6.02 × 10²³`), or in digit groups joined by spaces or apostrophes (`1 250 000`), which a reader
cannot tell from several numbers. `quotes(passage, quote)` is true when the quote
occurs in the passage with the same characters and case after normalisation (both in NFC, runs of white space
read as one space) and as whole words and whole numerals (a letter keeps its combining marks), so `"20"` is not a quote of `"120"`, `"5"` is not a quote of
`"-5"` and `"1 MW"` is not a quote of `"1 mW"`; an empty quote is false. Both are lexical: a number written in
a quoted span says nothing about what it measures, its unit, or whether the passage is right
(`text.quoted_number`, §11).

`matches` uses a bounded regex profile: pattern length at most 300, input length at most 20 000,
no groups, alternation or back-references, and at most one repetition operator outside character
classes. A conservative work estimate consumes kernel budget before matching; some otherwise valid
patterns are refused. These language budgets do not constitute an OS-level resource sandbox.

**Exact adapters.** Fixed first-party modules give the kernel bounded exact computations beyond expressions;
each has a contract document that states its domain, limits and what the result does not establish, and its
version is part of the kernel identity. `quadratic_minimize`, `quadratic_verify` ([VARIATIONAL.md](VARIATIONAL.md));
`wasserstein1` ([TRANSPORT.md](TRANSPORT.md)); `ising_minimize`, `ising_energy`: every state of at most 16
spins, the minimum and how many states attain it ([DISCRETE.md](DISCRETE.md)); `knows_event`,
`common_partition`, `common_knowledge`, `posterior_given`, `agreement_process`: Aumann's partition model on at
most 64 states ([KNOWLEDGE.md](KNOWLEDGE.md)); `reconcile`: the nearest values that satisfy exact linear
constraints, reported as a repair ([PROJECTION.md](PROJECTION.md)); `is_projector`, `commutator`, `commutes`,
`ordered_probability`: rational projectors and what the projector model predicts for ordered yes/no questions
([OPERATORS.md](OPERATORS.md)). They compute on the numbers a program supplies. None of them says anything
about the meaning of a text or about a model.

Datalog uses stratified, closed-world negation: absence from the relevant completed relation permits
`not p(...)`; it is not evidence that `p` is false in the external world. Positive compound arguments
must use already-bound variables, and rule scans consume the kernel budget.

**Kernel identity.** Every report carries `kernel` (`symblic.kernel_id()`): language, canonical-form, geometry
and adapter versions, the Unicode database version (text classes follow it) and the digit limit, hashed into `id`.
Fingerprints are compared only under the same semantic identity and input/module sources. The historical
8-machine experiment in `kernel-identity.json` used the earlier regime: evidence for those programs then,
not conformance evidence for this 2.5 reform or a proof for every program. Current-version receipts
are reported separately in [RESULTS.md](RESULTS.md).

**Geometry** (`symblic.adapters.geometry`, v2). A shape is `{vertices: [[x, y, z], …], faces: [[1, 2, 3], …]}`, exact.
`solid_check(s)` decides `valid_solid`: every face a flat, strictly convex polygon; no two faces on the same
vertices; every vertex used; every edge on exactly two faces; consistently orientable, connected, no pinch
vertex; positive volume; convex with the surface wrapping its hull exactly once (so it cannot intersect
itself); a closed non-convex surface is undecided. `similar`, `congruent` and `congruent_points` find an exact
similarity or rigid motion (reflections allowed) by search over base points (faces must map onto faces except
for `congruent_points`); the distance signature is only a necessary condition. `sameness(answer, target)`
reports schema_valid, valid_solid, similar, congruent, same_placement (equal canonical form) and identical.

Drawings: `flower(petals 3–36, color, center, shape round|pointed|heart|teardrop|spatula|fringed,
layers 1–4, length 0.2–1, width 0.1–1, rotation, leaves 0–6, stem, size, background, center_size)` (or a
record), `rose(k, color, size)`, `polygon(sides, color, size)`. Coordinates are rounded half-even to 0.01
and attributes written in a fixed order: equal arguments under the same renderer semantics are intended
to produce equal bytes. Conformance tests establish this only on the tested platforms and cases.

## 8. Runs, records and replay

A run folder holds `program.sym`, `meta.json`, `state.json` (status, bindings, outputs, fingerprint,
progress), `trace.jsonl` (a row per statement), `calls.jsonl` (every model call keyed by SHA-256 of
`[2, applicator, system, prompt, schema, sample, temperature, seed, engine effort, tools]`) and
`artifacts/`, plus versioned evidence and any capability ledgers. Its report records `kernel` (§7).
Cached answers can be reused only for matching request keys. A complete, compatible lock pins source,
modules, kernel and recorded inputs; strict replay refuses missing answers or incompatible pins and
does not invoke a fresh model. Historical records without sufficient pins are not silently upgraded.
External outcomes require their own ledger receipts; an unknown non-idempotent outcome fails closed
instead of claiming exactly-once execution. Runs are units `symblic-<id>` in `a systemd slice for work` (MemoryMax 600M,
CPUQuota 50%, nice 10, idle IO): they only orchestrate. Stop is `systemctl --user stop`; resume relaunches
with `--resume`.

New runs also record `call-events.jsonl`: the final invocation's per-request reply
sequences, including transport failures and cache reads. Locks retain those outcomes
and fatal flags so replay follows the recorded fallback sequence. Ordinary resume
can retry a failed provider call; replay only serves recorded replies. Automatic
routes reserve each fresh call in a durable, locked `model-budget.json` before
dispatch. Its source-scoped total survives resume, including interrupted attempts;
cached/replayed replies cost no new calls. A missing journal is seeded conservatively
from prior call rows; a damaged journal prevents new calls. `calls` counts fresh calls
in this invocation, while `model_budget.used` reports the source-scoped usage.

**Embedding.** `symblic.kernel.embed.check(source, kernel_id=...)` and
`symblic.kernel.embed.run(source, inputs=..., applicators=..., options=..., on_event=..., stop=...,
kernel_id=..., folder=...)` provide API version 1. A mismatched required kernel ID fails before model
execution. `run` returns `status` (`done`, `failed`, `stopped`), outputs, bindings, kernel and evidence.
The lower-level interpreter is `symblic.kernel.run.Run(...).execute()`; persisted/event trace rows are separate
from the report's binding and output lists.
Errors include `kind`, stable `SYM_<KIND>` code, message and source location when available. Inspect
status and diagnostics rather than assuming an output implies success. `options['stop']` accepts a
threading event. `options['on_event']` receives detached, sequence-numbered trace rows after recording;
a callback failure becomes a visible `event` error and stops subsequent statements. A stream is an audit
of execution, including failed attempts, not a claim that each intermediate binding was committed.

```python
import symblic as S
import symblic.kernel.embed as sym

events = []
report = sym.run("let total = 1/10 + 2/10.\nreturn total.\n",
                 kernel_id=S.kernel_id()['id'], on_event=events.append,
                 options={'by': 'kernel', 'max_calls': 0})
assert report['status'] == 'done'
assert report['outputs'][0]['text'] == '0.3'
```

## 9. API (`/api/automation/symblic/`, operator-only)

`GET meta | runs | run?id= | artifact?id=&name= | compares | compare?id= | programs | evidence | tightens |
tighten?id=`; `POST check | preview | run | stop | resume | delete | compare | programs/save | programs/delete |
tighten | tighten/stop`. `tighten {source, inputs, panel: [...], clarifier, rounds}` starts a runner unit
`symblic-tighten-<id>` (`symblic/authoring/tighten.py job`) whose private `result.json` holds each round's per-ask
diagnosis, readings and rewrites and the tightened program (the page's Tighten screen).
`preview` runs the kernel up to the first ask and returns that ask's exact capsule and schema; nothing
reaches a model. `compare` starts one run per applicator and lines statements up by fingerprint
(unanimous statements, pairwise identity, identical whole runs out of all runs).

## 10. Automation Studio nodes

`agent` (one typed answer from any applicator), `council` (template), a three-agent delegation node
(delegates and returns the agent id), `symblic` (a program whose `given` inputs come from workflow variables;
results come back as `symblic_<name>` and `symblic_fingerprint`). They share the workflow's stop event. These
workflow nodes belonged to the original host's automation page; only the page's static files are in `web/studio`.

## 11. Building programs from parts (docs/reference/LANGUAGE-3.md)

`function f(x: T, y: T = default) -> T = expr.` is a kernel expression function; verified
execution enforces transitive purity, while legacy permits the historical routine bridge. `routine r(x: T) -> T [with
options] do … return expr. end.` is a typed model function: its asks take the normal path, its options are
defaults only inside it, and within one run the same closure, arguments and defaults reuse a memo entry
with its original evidence dependencies. `import NAME [as
g]`, `import a, b from NAME` and `import "Saved program" as g` load a declarations-only module from
`symblic/lang/library/` or the saved programs; its source is recorded in the run folder. `test "…" do … end.` is
skipped in a run and run by `tools/symblic test`/`certify`. A `.symd` paper (Markdown with ```` ```symblic ````
blocks) compiles deterministically: definitions become terms, section prose becomes the asks' default
context, and diagnostics keep the paper's line numbers; comparing agents on a paper reports the lines they
read differently. A compatible complete run can be locked (`run.lock.json`) and replayed with no model.

Library additions in 2.3. `text.quoted_number(passage, quote, value)`: the quote is a span of the passage
(`quotes`) and the value is one of the numbers written in it; `text.quoted_number_in(what, passage)` asks for a
number with the span that states it and retries until that holds. This closes a gap that arithmetic checks
leave open: an extraction such as `{quantity: 1, unit_price: 1, total: 1}` is internally consistent for any
invoice. It establishes that the number is written in a span copied from the passage, not which thing the
number describes. `records.conflicts(a, b)` lists the fields two records share whose values differ and
`records.agree(a, b)` is true when there are none: for two observations of one thing through different
capabilities. Agreement on shared fields is not correctness. `order` computes order effects and the QQ gap from
counts of answers to two yes/no questions asked in both orders, and `stats.binomial_at_least` /
`binomial_at_most` are exact binomial tails (18 passes out of 18 leave a true rate of 85% unexcluded at the
5% level). Examples: [13-two-accounts.sym](../../tests/kernel/fixtures/13-two-accounts.sym),
[14-question-order.sym](../../examples/14-question-order.sym).

**Trusted extensions.** `Extension` supports pure `check(node, scope)` and `check_program(program)` hooks.
`scope` is the frozenset of names bound before the statement; the whole-program hook runs once per used
extension keyword. Hooks return `None`, a diagnostic, or an iterable of `SymblicError`/diagnostic dictionaries
(optional `severity='warning'`). They must not execute statements, load sources, perform I/O or call models.
Hook failures become diagnostics. Effect extensions default to the runner's preview/replay/side-effect
gates; `self_gating=True` is a trusted Python extension's explicit responsibility to enforce equivalent
ledger protection. Fixed first-party registration imports geometry, `symblic.lang.abstraction`, optional `symblic.kernel.effects`,
and the inert variational module at the end of `symblic/kernel/language.py`. The fixed adapter-table modules and transport
are loaded on first use; `kernel_id()` may import them to read versions. Import-order behavior is part
of the adapter contract; do not describe every adapter as lazy.
Symblic source cannot choose a Python import. Extensions are trusted code, not a security sandbox.

## 12. Predictability: measuring and raising agreement

- `check` scores each ask statically (`asks_detail`, `predictability` 0–100): free-text answers, numbers without
  places or units, vague or relative words, pronouns, spatial words without a frame (axes, origin, coordinates),
  time references without a date, bare quantifiers, units with several definitions (ton, pound, gallon, mile,
  billion, year…), slash dates, rounding without a rule, letter- or number-named options, options without
  definitions. It is a guide from the text alone, not a probability; it was written alongside the first
  measurements, so it is not validated by them.
- `ambiguous=true` asks every reader for the statement's alternative readings (§4).
- `permute=K` measures whether a closed answer survives K orders of its options (§4).
- `symblic.authoring.tighten.tighten(program, inputs, panel, applicators, clarifier)` probes and proposes
  candidate rewrites. Its diagnostics classify observed disagreement/readings; labels such as `capability`
  are heuristics, not a causal diagnosis. `candidate_program` is available for experiments while `program`
  retains the original until adoption. The audit pins both sources, original requirements, mappings and
  fidelity obligations. Agreement, parse success and modal-answer leak checks do not prove intent fidelity.
  An exact recorded host decision can adopt an unassessed change under the existing operator action, while
  failed obligations or a prohibition on meaning changes remain binding. A predeclared AST-equivalence
  policy is narrower than prose equivalence. Candidate probes do not silently adopt the rewrite.
  Exposed examples are specification data; held-out outcomes require a disjoint, frozen evaluation.
- What can be claimed: the kernel supplies specified executable meaning for supported formal expressions;
  exhaustive checking can establish a unique admitted answer in a declared finite domain. For model
  interpretation, agreement is measured per panel. Report predicate conformance, independently judged
  target correctness, coverage and semantic faithfulness separately. A list of alternative readings is
  useful evidence of ambiguity, not proof that all readings have been found.
