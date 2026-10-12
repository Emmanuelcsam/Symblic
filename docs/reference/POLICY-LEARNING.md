# Bounded finite-candidate policy selection, version 1

`symblic/policy/learning.py` selects among frozen routing/topology policies using
predeclared training cases, exact host-declared scores, and all-attempt accounting.
This is **finite-candidate policy selection**, not neural backpropagation, graph
optimization, a theorem checker, or a causal experiment. Policies are opaque
bounded JSON; the module neither imports a graph implementation nor executes a
policy. No models, providers, services, live stores, or deployment calls occur.

## Authority and workflow

1. The host freezes candidate policies, a baseline, the objective, common budgets
   and training cases in a training plan. Freeze its canonical SHA256 **before**
   collecting outcomes. Assign every candidate to every case: the Cartesian
   assignment matrix is implicit and cannot be narrowed by outcome records.
2. Separately freeze a heldout plan naming the training-plan hash and heldout
   case metadata. Call `validate_split(training_cases, heldout_cases)` before
   collecting outcomes. The selector does not receive this audit result, the
   heldout plan/hash, or any heldout records, order or metadata.
3. Collect and retain training records including every attempt. Pin the complete
   ledger snapshot. Run `select` with the trusted plan and ledger pins. Freeze
   the returned selection and its canonical hash **before opening heldout
   outcomes**. A missing assignment is scored/accounted for, not dropped.
4. Collect heldout records for exactly the frozen selected candidate and declared
   baseline under the same caps and objective. Pin that snapshot and run
   `evaluate_heldout`. It replays the training-only selection, checks the frozen
   selection pin/content, audits split separation, and then evaluates heldout.
   It never reselects, repairs, changes a threshold, or modifies any policy.
5. Keep all original plans, snapshots and receipts. Integration may use the
   selected hash for **future runs only**. This module makes no historical
   rewrites or operational changes. It does not install a policy.

Pins must come from trusted host storage, not from a model response. Hashes detect
changes relative to those pins; they are not signatures or evidence of when a
plan was created. This module cannot prove temporal predeclaration, that a host
reported every actual attempt, or that a model never saw heldout information.
It audits declared hashes and exact supplied records. Repeatedly tuning against
heldout results would destroy the claimed heldout status; use a newly frozen,
separated evaluation set for a subsequent selection round.

## Public APIs

- `digest(value)` returns SHA256 of bounded canonical JSON: sorted dictionary
  keys, compact separators, ensure_ascii=False UTF-8. Lists retain order.
- `validate_split(training_cases, heldout_cases)` returns hashes and a declared
  separation receipt, or raises `PolicyError`. It is separate from selection.
- `select(training_plan, training_records, *, expected_plan_hash,
  expected_records_hash)` returns the exact selected policy and training receipt.
- `evaluate_heldout(training_plan, training_records, selection, heldout_plan,
  heldout_records, *, pins)` returns the frozen comparison receipt.
- `load_json(path)` is the CLI's bounded strict JSON-file reader.

Invalid schemas, changed pins, budget violations and no eligible candidate raise
`PolicyError` with a finite diagnostic code, never caller text. No fallback
policy silently replaces a rejected choice. Inputs must not be concurrently
mutated during an API call. All returned content is detached from input objects.
The selected policy is returned as **immutable canonical JSON text** under
`selected.policy_json`, with its SHA256 under `selected.sha256`. The surrounding
JSON receipt is editable by its consumer; the frozen selection hash detects such
edits, and heldout evaluation independently replays the exact expected selection.
Use `json.loads(selected['policy_json'])` to recover the exact policy value.

## Exact input schemas

All dictionary fields below are required; unknown fields are rejected. Only the
opaque `policy` value has no semantic schema beyond bounded exact JSON.

Training plan:

```json
{
  "version": 1,
  "candidates": [{"sha256": "<policy SHA256>", "policy": {"route": "example"}}],
  "baseline": "<one declared policy SHA256>",
  "cases": [{
    "case_hash": "<SHA256>",
    "family_hash": "<SHA256>",
    "input_hash": "<SHA256>",
    "exposure_hashes": ["<SHA256>"]
  }],
  "budget": {"max_calls": 4, "max_cost_units": 100},
  "objective": {
    "max_score": 10,
    "score_weight": 100,
    "call_weight": 1,
    "cost_weight": 1,
    "unknown_cost": "budget",
    "tie_break": "policy_sha256_ascending",
    "min_heldout_gain": 1
  }
}
```

Hash placeholders above must be replaced by 64 lowercase hexadecimal characters.
A candidate's hash must equal `digest(policy)`. Candidate hashes and case hashes
must be unique. The baseline must be one of those candidates. Candidate and case
list order does not affect ranking, though the source hash preserves that order.
Case metadata is host-declared identity/provenance, not a body of runnable code.

Training and heldout **record lists** use the same row schema:

```json
{
  "candidate": "<policy SHA256>",
  "case": "<assigned case SHA256>",
  "status": "success",
  "score": 8,
  "attempts": [
    {"calls": 1, "cost_units": 7},
    {"calls": 2, "cost_units": null}
  ]
}
```

A row represents the final declared outcome of one assignment, with **all** its
attempts, including failures and repairs before any eventual success. Repeated
rows for the same assignment are rejected, not treated as opportunities to pick
the best result. Attempt list order is retained in the record identity.
Statuses are exactly `success`, `failed`, `refused`; failed/refused scores must
be integer zero. Success scores range from 0 to `max_score`, inclusive. There
is no inferred scoring rubric: scores are host-supplied measurements, not truths
established by the optimizer. A zero-call successful deterministic policy is
allowed; a refusal with no attempts explicitly declares no calls/cost occurred.
An absent row means **missing**, which is different from a recorded refusal.

Each attempt declares nonnegative integer `calls` and either nonnegative integer
`cost_units` or null for unknown cost. Cost units have one host-declared meaning
throughout an experiment; do not mix currencies, time units or billing regimes.
They are never floats or estimates silently treated as known. Calls and known
costs sum over **every** attempt. Observed totals above the common per-assignment
budget are rejected for the whole input. No per-candidate or per-row budget
override is allowed. Different actual consumption below the common caps is
permitted and is part of the objective.
Both budget fields permit zero. In particular `max_calls: 0` supports a
deterministic-only experiment and rejects any reported model call. It does not
make otherwise unknown costs known.

## Exact objective, denominators and uncertainty

Every candidate has the same denominator: the number of predeclared cases.
Its score is the sum of final assignment scores; failed, refused and missing
assignments contribute zero. No success-only averages or outcome-filtered cases
are used. Missing rows remain explicit receipt rows with null record hash.

For each assignment:

- Observed calls sum all attempts. Missing rows have no observed calls, one
  unknown-call assignment, and are charged the entire `max_calls` allowance.
- Known cost sums all integer cost entries. Every null entry is counted as an
  unknown-cost item; an absent assignment contributes one unknown-cost item.
- If any cost is unknown, the assignment is charged the **entire**
  `max_cost_units`, including its known portion, not that allowance plus known
  cost. Otherwise its charge is the exact known total.
- With predeclared `unknown_cost: "reject"`, any candidate with missing or
  unknown-cost assignments is ineligible. With `"budget"`, it remains eligible
  at the declared charges. Missing cases still stay in its denominator.

The integer ranking value is:

```text
utility_sum = score_weight * score_sum
            - call_weight * charged_calls
            - cost_weight * charged_cost_units
```

Select the greatest utility sum, breaking exact ties by ascending policy SHA256.
Because all candidates share the denominator, this equals ranking mean utility
without rounding or floating point. `score_weight` and `max_score` are positive;
other weights and `min_heldout_gain` are nonnegative. All are exact integers.
Budget-charging unknown costs is a **declared ranking convention**, not evidence
that actual costs are known or truly below the cap. The host must enforce real
resource limits. Unknown accounting cannot establish heldout improvement.

Training receipts retain the source-plan and record-list hashes, baseline,
objective, full assignment matrix count, each candidate's denominator/status
counts, score sums, observed versus charged calls, known versus unknown costs,
utility and eligibility. Every observed assignment has a hash of its full input
row (including every attempt); missing assignments are explicit. Receipts report
`measurement_status: host_declared_not_verified`, `confidence: not_established`
and `causality: not_established`. A better training score is not a generalization,
confidence, statistical significance or causal claim.

## Heldout schema and result

Heldout plan is exactly:

```json
{"version": 1, "training_plan_hash": "<frozen training plan hash>", "cases": []}
```

Replace the empty illustrative `cases` list with 1–256 case entries in the same
schema as training. No outcomes, ordering preferences, baseline overrides or
objective overrides are accepted in this plan. Heldout records may mention only
the selected candidate and baseline; if they coincide, there is one assignment
per case, not duplicate rows.

`pins` for evaluation contains exactly `training_plan`, `training_records`,
`selection`, `heldout_plan`, and `heldout_records`, each the trusted canonical
hash of the corresponding argument. The training-only `select` call receives
only its training arguments and the two training pins. Changing heldout
metadata, record values or order cannot change those selector arguments.

Split audit rejects overlap in case, family and input hashes. It also compares
all case, family, input and exposure hashes **together** across splits. A complete
heldout case or family disclosed as a training exposure is leakage even when
its hash differs from the heldout input alone. Changing the metadata role
cannot conceal the same declared resource. Exposure lists must be unique
within each case. Shared declared resources across splits are conservatively
rejected, even if the host believes that resource harmless.
Hash spelling cannot establish the adequacy of provenance declarations.

The evaluator returns both candidates' full matched summaries and exact mean
utility gain as `{numerator, denominator}`. `improvement: true` requires:

1. A selected policy different from baseline.
2. Complete records for both policies on every heldout case, with no unknown
   costs. Recorded failures/refusals remain in the denominator and may be compared.
3. Strictly positive utility gain that also meets the predeclared per-case
   `min_heldout_gain` threshold (checked by exact integer multiplication).

Otherwise `comparison` is `not_established`; there is no replacement choice.
A true result is labeled `observed_improvement` under the declared measurements,
not a confidence bound, causal conclusion or proof of future performance.

## Graph-runtime integration boundary

The selector currently consumes records and returns an opaque policy. It does
not collect graph evidence or install routes. A graph adapter must supply these
separate operational checks before treating the result as an executed learning
workflow:

- Freeze the exact graph/policy payload, caller-held task and acceptance
  contracts, checker/kernel versions, model routes, exposure identities,
  cost-unit definition, caps and scoring procedure before collecting outcomes.
  Validate the selected payload against the graph's actual schema; a valid
  policy digest alone is not an executable graph or an authority grant.
- Derive outcome rows from immutable run/attempt receipts linked to the
  experiment, policy and case identities. Count every provider dispatch,
  retry, repair, losing search branch and recovered attempt exactly once.
  Replayed cached evidence is not a fresh independent observation. This
  selector's aggregate `attempts` schema cannot itself detect omitted or
  duplicated underlying events; the adapter must reconcile the event ledger.
- Score actual terminal outcomes using the frozen external scorer. A model's
  claimed score, its self-authored acceptance record, or a schema-only pass
  cannot establish task success. Formal, source-witness and predicate checks
  keep their respective conditional scopes; empirical truth remains unresolved.
  Timeouts, exhausted budgets and rejected answers remain failures in the
  planned denominator. Report unknown costs as unknown, including after
  interruption; do not turn missing measurement into a zero-cost success.
- Enforce budgets during execution, not only after receiving these summaries.
  These caps are per candidate/case assignment. Total experiment reservations
  must also cover the complete assignment matrix, plus any explicitly declared
  preparation or scoring costs. Applying the per-assignment cap as an aggregate
  experiment cap would silently change which candidates get evaluated.
- Keep heldout outcomes outside candidate constructors, prompts, route
  selectors and repair feedback. Preserve the frozen training choice while
  evaluating it. Record use of an evaluation set so that repeated adaptive
  tuning cannot be described as a fresh heldout comparison merely by repinning
  the same records. Hash checks do not enforce that host workflow themselves.
- Admit an adopted policy only to a new run with its new policy hash and the
  original caller capabilities. Do not rewrite historical graphs/results,
  increase access, or modify an in-flight run because a training utility was
  larger. If claiming measured improvement, retain the complete heldout
  comparison and its exact scope; a failed comparison never becomes a new
  selected policy inside this evaluator.

The independent audit adds cross-role leakage cases, zero-call experiments,
exact fractional mean-gain boundaries, repeated unknown-cost attempts, aggregate
versus assignment budgets, extreme signed integer utilities, and missing/refused
outcomes. These tests validate the finite selector's accounting; they do not
replace the graph adapter's execution and adoption checks.

## Bounded CLI and verification

```bash
python3 symblic/policy/learning.py hash training-plan.json
python3 symblic/policy/learning.py hash training-records.json
# Store those hashes as training_plan/training_records in selection-pins.json.
python3 symblic/policy/learning.py select \
  --plan training-plan.json --records training-records.json --pins selection-pins.json
# Save stdout as a NEW selection.json; pin it before viewing heldout outcomes.
python3 symblic/policy/learning.py hash selection.json
python3 symblic/policy/learning.py evaluate \
  --training-plan training-plan.json --training-records training-records.json \
  --selection selection.json --heldout-plan heldout-plan.json \
  --heldout-records heldout-records.json --pins evaluation-pins.json
```

The CLI reads only explicitly named regular JSON files and writes exact JSON to
stdout. It does not write source files, overwrite history, read environment
credentials, execute policy values, or contact providers. Errors return finite
JSON diagnostics and exit 2. It rejects duplicate JSON keys, non-integer numeric
syntax (including `1.0`), NaN/infinities, invalid Unicode and device/FIFO inputs.
No line-by-line unbounded stream is supported.

Resource limits: 2,000,000 conservatively counted bytes, 50,000 input/output
nodes, depth 40, strings 16,384 characters, at most 32 candidates, 256 cases,
1,024 candidate/case assignments, and 64 attempts per assignment. Policy canonical
JSON text must also fit the string bound. Schema integers are at most 10^12;
opaque JSON and exact aggregate receipt integers are bounded by 10^30. Booleans
are allowed as opaque policy data but never as numeric score/cost/budget/version
fields. Cycles, custom Python types, floats and schema extras are rejected. All
loops are bounded by these limits. The receipt is checked against output bounds.

Independent tests enumerate small score assignments and compute the expected
winner separately, and attack leakage, changed pins, forged frozen selections,
missing denominators, unknown costs, per-choice budget overrides, all-attempt
charges, ties, split identity/exposure overlap and CLI parsing. The earlier proof
and finite-logic modules are unchanged. Root integration remains separate and
gated; this package makes no live changes.
