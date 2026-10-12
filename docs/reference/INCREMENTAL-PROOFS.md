# Incremental proof sessions: one inference per fresh context

`symblic/adapters/proof_session.py` lets a model build a flat natural-deduction proof
(`symblic/adapters/proof_steps.py`, [PROOF-STEPS.md](PROOF-STEPS.md)) one inference at a
time. Each model call sees only the current task card and proposes exactly one
`{rule, args, formula}` candidate. The host names it `s1`, `s2`, … and checks it
against the caller's premises and goal. Nothing is searched for. There is no
second calculus: every check runs `symblic.adapters.proof_steps.check_prefix`, which
shares its inference code with `verify`, and completion is decided by the
existing `verify`.

The optional [command wire](PROOF-COMMANDS.md) renders the same frontier formulas
as controlled text and translates one explicit command into that same candidate.
JSON remains the default; the session ledger and inference checker are unchanged.

This is an implementation contract. The checks described below use injected fake
constructors and do not establish real-model quality or cost. Model experiments
require separate frozen task, information, budget and outcome records.

## Trust boundary

- **Caller-held sequent.** The caller supplies premises and goal on every
  `append`. The state embeds a copy for the task card, and its SHA-256 hashes
  must match both that embedded copy and the caller's sequent. A candidate can
  never change premises, goal, earlier lines or IDs.
- **The state is a raw ledger, not authority.** It stores only the accepted
  steps, never inferred formulas. Every `append` and `frontier` rechecks the
  whole stored prefix. A ledger edited into another *valid* derivation is just
  a different valid prefix. A ledger with an invalid line, foreign IDs, wrong
  hashes or lines after completion is refused.
- **Model proposes, kernel decides.** The checker never completes formulas,
  picks rules, invents premises or reports a next step. A refusal hint is fixed
  text describing the rule's requirement.
- **Conditional result.** Completion attests only that the goal follows from
  the declared premises in intuitionistic propositional logic. Premise truth
  and consistency are not checked. Failing to finish does not make the goal
  false.

## Native builtins

The native runtime registers these three names in `symblic.ADAPTERS` under the existing
`symblic.adapters.proof_adapter` row. Each adapter function receives `(kernel, node, …)`
as usual. Every call charges the calling run's kernel step budget through
`kernel.budget.tick`; there is no separate session budget. A host budget
exception always propagates and is never turned into `valid=false`.

| Builtin | Returns | Failure |
| --- | --- | --- |
| `proof_session_start(premises, goal)` | state | invalid sequent: `SymblicError(kind='check', 'proof session: <code>')` before any model call |
| `proof_session_frontier(state)` | frontier | invalid or forged state: the same `check` error |
| `proof_session_append(premises, goal, state, candidate)` | result | never raises for bad values; refusals are `valid=false` results |

`append` converts its arguments without refusing anything. A boolean, a
non-integral number, a set or an over-deep value inside a model's `formula`
becomes a finite candidate refusal (`input_type`, `depth_limit`, …) with the
prior state intact, not a run error. The pure module offers the same functions
as `start(premises, goal, *, tick=None)`, `frontier(state, *, tick=None)` and
`append(premises, goal, state, candidate, *, tick=None)`, where `tick` is a
no-argument callback. In the pure API, `start` and `frontier` raise
`symblic.adapters.proof.ProofError(code)`.

These session entry points were introduced in adapter version 3
(`kernel_id()['proof']`). The optional command-wire prototype raises that adapter
to version 4 without changing the session inference rules.
The certificate format and `symblic.adapters.proof_steps.VERSION` stay at 1, and
`verify` semantics are unchanged. A one-off differential run during development
compared 104,780 generated certificates and found identical receipts, tick counts
and budget-stop points before and after the refactor. The existing proof suites
remain the committed regression.

## State

```json
{"version": 1, "format": "symblic-proof-session", "certificate_version": 1,
 "premises": {"a": ["atom", "A"], "if_a": ["implies", ["atom", "A"], ["atom", "B"]]},
 "goal": ["atom", "B"],
 "steps": [{"id": "s1", "rule": "premise", "args": ["if_a"], "formula": null}],
 "hashes": {"premises": "<sha256>", "goal": "<sha256>"}}
```

- Step IDs are exactly `s1 … sN`, in order.
- Premises are stored sorted by name.
- Hashes are `symblic.adapters.proof._hash` values, the same ones `verify` receipts report.
- A state contains only text, integers, lists, records and `null`, never
  booleans, so it round-trips through language values unchanged.

## Frontier (the task card)

```json
{"goal": ["atom", "B"],
 "premises": {"a": ["atom", "A"], "if_a": ["implies", ["atom", "A"], ["atom", "B"]]},
 "lines": [{"id": "s1", "rule": "premise", "formula": ["implies", ["atom", "A"], ["atom", "B"]], "free": []}],
 "next_id": "s2", "complete": false, "steps_left": 511}
```

The frontier holds exactly what the next inference needs:
- every rechecked earlier line, with its inferred formula, its rule (to show which
  lines are `assume` lines that can be discharged) and its free assumption IDs
  in line order;
- the named premises;
- the goal.

It holds no target proof, rejected attempts, hashes or search hints.
`next_id` is null once the session is complete or full. A complete state's
frontier also requires an accepting `verify` receipt.

## Append result

| Field | Meaning |
| --- | --- |
| `valid` | the candidate was accepted as line `next_id` |
| `rejected` | `null`, `"state"`, `"session"` or `"candidate"` |
| `error`, `hint`, `rejected_step` | finite code, fixed text and zero-based line index (the candidate's index for candidate refusals) |
| `step`, `line` | the stored `{id, rule, args, formula}` and the inferred `{id, rule, formula, free}`; null unless valid |
| `state` | the new state if valid, the unchanged prior state for `candidate`/`session` refusals, null for `state` refusals |
| `frontier`, `next_id`, `complete`, `hashes` | describe the returned state, so the next ask needs no extra `frontier` call |
| `certificate`, `receipt` | when the returned state is complete: the flat certificate (`result` = its last line) and the existing `verify` receipt |
| `checks` | line inferences performed by this call |
| `version`, `format`, `logic`, `scope`, `conditional_on_premises`, `consistency` | `1`, `symblic-proof-session`, the logic, `derivation_from_declared_premises`, `true`, `not_checked` |

Refusal precedence is state first, then session, then candidate. A candidate
refusal is returned only after the stored prefix has been rechecked, so a forged
ledger is never passed back as "intact". A session is complete only when a newly
accepted line has no free assumptions, exactly equals the caller's goal, and
`verify` accepts the certificate. A ledger can never continue past its first
such line. `append` on a complete state returns `session_complete` together
with that state's certificate and receipt.

### Finite codes

- **`state`:** `state_shape`, `state_version`, `state_step_id`, `state_hash`,
  `sequent_mismatch`, `state_after_complete`, `step_limit`, scanner limits, and
  any checker code for a stored line (with `rejected_step`).
- **`session`:** `session_complete`, `step_limit`.
- **`candidate`:**
  - shape: `candidate_shape`, `rule`, `rule_arity`, `unexpected_formula`, `formula_shape`;
  - references: `unknown_premise`, `unknown_or_forward_reference`;
  - inference: `and_expected`, `implies_elim_mismatch`, `assumption_reference`,
    `or_expected`, `branch_assumption_collision`, `branch_assumption_mismatch`,
    `or_elim_mismatch`, `branch_scope`, `false_expected`;
  - bounds: `input_type`, `unicode`, `cycle`, `text_limit`, `depth_limit`,
    `node_limit`, `byte_limit`, `work_limit`, `output_limit`.

`symblic.adapters.proof_session.HINTS` maps candidate and session codes to short fixed
sentences. `STATE_HINT` is the single message for state refusals. No hint or
code contains caller- or model-supplied text.

## Prefix checker

`symblic.adapters.proof_steps.check_prefix(premises, goal, steps, *, tick=None, max_bytes=None)`
runs `verify`'s preflight scan, sequent checks and per-line inference over zero
or more ordered lines, and selects no result. On success it returns
`lines: [{id, rule, formula, free}]` as detached JSON, with free IDs sorted as
text. On refusal it returns a finite `error` and, for a line, `rejected_step`.
A line table whose compact JSON exceeds `max_bytes` (default `MAX_BYTES`) is
refused as `output_limit`, so shared DAG structure cannot expand without bound.

## Limits and cost

- At most 512 lines (`steps_left`).
- Each internal check has `verify`'s limits: 256 premises, 64 structural depth,
  20,000 scanned nodes, 262,144 counted bytes, 4,096 characters per text and
  200,000 work units.
- The frontier's line table is bounded by 262,144 bytes, and the sequent by the
  input scan. A frontier is therefore at most about 512 KB, far above useful
  prompt sizes: root's verified packing budget is the practical bound.
- Every call rechecks the whole prefix, so one call costs work proportional to
  the proof so far, and a whole session is quadratic in its length. This is the
  price of never trusting stored inferences.
- An accepted candidate costs one checking pass; a refused one costs up to two.
  In the language, each argument node also costs one tick to convert.
- Completion re-runs `verify` once.
- Run budgets: the default 200,000 kernel steps covers short proofs. Long
  sessions should raise `max_steps`.

## Native compiler integration

The compiler uses the existing verified `ask`/`ensure` loop, one ask per
inference. The default `context=none` gives each ask a fresh context with only
its `from` values:

```text
let s0 = proof_session_start(premises, goal).
let f1 = proof_session_frontier(s0).
ask c1: <symblic.adapters.proof_session.CANDIDATE_TYPE> "Propose exactly one next inference for frontier. Follow proof_rules." from f1, proof_rules with effort=low, route=escalate, retries=2
let a1 = proof_session_append(premises, goal, s0, c1).
ensure a1.valid else retry because "Propose one inference the checker accepts.".
let f2 = a1.frontier.
… repeat with a1.state, stopping when aK.complete …
let verification = proof_steps_check(premises, goal, aK.certificate).
```

- `CANDIDATE_TYPE` is
  `Record {rule: one of {<the eleven rules>}, args: List of Text length 0..5, formula: Any}`.
  It compiles to an enum-constrained schema and has no `id` field.
  `candidate_schema()` is the equivalent detached JSON Schema.
- `rules()` returns detached generic rule text and an unrelated one-line
  example. It takes no task input, so it cannot contain a target proof.
- An ensure-retry re-asks the same inference with the runtime's normal repair
  feedback. The next ask sees only its own task card. A `state` or `session`
  refusal cannot be fixed by retrying.
- The run's shared call budget bounds all inferences: when it runs out, the run
  fails rather than accepting a partial proof.
- The integration installed in the 5 October reform registers the session builtins, includes
  `symblic/adapters/proof_session.py` in required execution pins, records its semantic
  version in kernel identity, and compiles incremental tasks through
  `symblic.adapters.logic`. The [5 October release evidence](evidence/2026-10-05-reform-install.json) records installation and its scoped live checks.
- Command mode adds the versioned helper and its two adapter names; see
  [PROOF-COMMANDS](PROOF-COMMANDS.md). It retains the same accepted step ledger,
  authority separation, final verifier and total native call budget.

## Tests

`tests/adapters/test_symblic_proof_session.py` uses no models, stores or processes. It
covers:
- the pure API and host IDs, with receipts compared to `verify`;
- prior-state preservation for every candidate refusal;
- implication discharge across calls, discharge by identity rather than an equal
  formula, open goal lines, disjunction branch scope, and vacuous and falsity
  rules;
- candidate forgery (IDs, sequents, state, conclusions);
- recheck of imported states (edited lines, IDs, envelope, hashes, foreign
  sequents, continuation past completion);
- limits and work bounds;
- host budget propagation from every entry point;
- `check_prefix`/`verify` agreement;
- replay of the flat-certificate corpus;
- generated sessions checked against `check_prefix`, `verify`, the independent
  nested-term checker and a Boolean truth-table sanity oracle.

Native tests drive the adapter with language values and a kernel-only program.
A fake-constructor `Run` of the fresh-context loop repairs a rejected
inference, shows that later prompts exclude the rejected attempt, checks the
enum schema, and fails under a too-small shared call budget. Builtins are
registered in tests only while absent from `symblic.BUILTINS`.
