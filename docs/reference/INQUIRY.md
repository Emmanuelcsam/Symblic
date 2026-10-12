# Choosing the next evidence method

`symblic.inquiry.selection.plan(assessment)` selects a bounded next check from recorded
method evidence. It makes method diversity operational: a new check can add
coverage of a declared failure, distinguish supplied alternatives, or expose a
shared dependency. Repeating an existing check does not automatically add new
coverage. Different model names do not establish independent observations.

The planner is pure and uses only the standard library. It reads no files, changes
no notebook or run, calls no model, and starts no worker. A recommendation can be
handed to an existing admitted graph path. That host must independently check
current authorization, availability, budget and all pins before dispatch.
`authorizes_execution` is always `false`.

## Use the planner

Open **Inquiry** in Symblic, fill the synthetic example, and select **Plan next
check**. The advanced JSON editor retains the full assessment. The result shows
support separately from inquiry status, measured additional coverage, unknowns,
the retained Pareto frontier and shared dependencies. Editing the input clears
the previous result. This page does not save records or execute recommendations.

The same operations are available locally:

```sh
tools/symblic inquiry example --agent-json > assessment.json
tools/symblic inquiry plan assessment.json --agent-json
```

The CLI reads at most 1 MiB from a regular file, refuses symlinks and special
files, and exits with status 1 for refused input. Standard input is not supported;
provide the saved assessment's file path. Output is JSON with or without
`--agent-json`.

Operator-only HTTP routes are `GET /api/automation/symblic/inquiry/example` and
`POST /api/automation/symblic/inquiry/plan`. The example returns
`{version, kind: "synthetic_fixture", assessment}`. Planning accepts exactly
`{"assessment": <object>}` or `{"assessment_json": "<raw JSON text>"}`. Use the
raw-text form to preserve duplicate-key detection through an HTTP JSON decoder;
the browser editor does this. Invalid input returns HTTP 400 with a stable
`detail.code` and `detail.path`. Unsupported inquiry actions return HTTP 404.

`example()` evaluates three tiny integer predicates against declared synthetic
faults and alternatives. Its cost unit counts specified primitive operations
over those fixtures; it is neither elapsed time nor a production admission. The
nonnegative check initially covers reversal. Total and length checks add
different coverage and distinctions, so both remain on the frontier. Actual
projects supply their own versioned receipts and independently verified costs.

## Wire contract

All records use exact JSON: strings, integers, booleans, null, arrays and objects.
Floats, duplicate object keys, unknown fields and duplicate IDs refuse. Use
`loads(raw)` when reading JSON text; a Python dictionary cannot reveal duplicate
keys already discarded by another decoder. `InquiryError.code` and `.path`
identify refusals without echoing input values.

`Reference` is `{id, revision, sha256}`, matching the notebook's claim-reference
shape. Revisions are positive integers; hashes are lowercase SHA-256 strings.
These bind caller-supplied records. They are not signatures or empirical proof.

An assessment has exactly these fields:

| Field | Value |
|---|---|
| `schema` | `symblic.inquiry.assessment.v1` |
| `claim` | Current `Reference` |
| `scope` | The scope record below |
| `scope_sha256` | `scope_digest(scope)` |
| `dependencies` | Current dependency references; unique IDs |
| `methods` | Candidate method records below |
| `receipts` | Observed fixture receipts below, including unsuccessful planned observations |
| `used_receipt_ids` | Receipts whose methods have already been used in this assessment |
| `budget` | `{unit, remaining}`; one declared unit and nonnegative integer amount |
| `support` | `{status, reason}` |
| `inquiry` | `{status, reason, history}`; history entries are `{status, reason, scope_sha256}` |

The scope has exactly `id`, `revision`, `claim`, `domain`, `units`,
`outcome_schema_sha256`, `faults` and `alternatives`. Each fault is
`{id, fixture_sha256}`; each alternative is `{id, definition_sha256}`. Either
finite list may be empty. The current claim must equal the scope's claim.
Changing a claim, scope, fixture or alternative requires newly associated
receipts; old scope receipts refuse rather than silently carrying forward.
Historical inquiry entries may retain earlier scope hashes.

A method has exactly:

| Field | Value |
|---|---|
| `id`, `revision`, `implementation_sha256` | Versioned method identity |
| `acquisition` | References identifying sources, instruments and preprocessing |
| `interpretation` | References identifying readers, models or interpretation procedures |
| `assumptions` | References identifying calibration and other common assumptions |
| `authorized` | Strict Boolean supplied by the caller |
| `available` | Boolean or `null` for unknown |
| `cost` | `{amount, receipt_sha256}` in the assessment's budget unit, or `null` for unknown |

`method_digest(method)` pins its ID, revision, implementation and three dependency
roles. Admission, availability and cost remain current assessment inputs, so
changing availability does not invalidate earlier method measurements. The final
recommendation additionally pins the entire assessment, including these inputs.
The planner does not open the cost receipt or authenticate its measurement.

Each fixture receipt has exactly `id`, `scope_sha256`, `method_id`,
`method_sha256`, `status`, `faults` and `predictions`.

- `status` is `completed`, `failed`, `timed_out`, `unavailable` or `unperformed`.
- A fault row is `{id, fixture_sha256, outcome, witness_sha256}`. Outcomes are
  `caught`, `missed`, `unassessed` and `unavailable`. A catch or miss requires a
  witness hash; the other outcomes require `null`.
- A prediction row is `{id, definition_sha256, outcome_sha256}`. Its ID names a
  declared alternative. Different supplied outcome hashes distinguish those
  alternatives for this method. A null hash retains an unknown prediction.

Receipts bind the exact method and assessment scope. Their observed content is
input, not independently authenticated evidence: an integration must validate
underlying run records before constructing these inputs. Only completed receipts
contribute measured coverage or discrimination. Every status remains in the
output's `planned_receipts`; unsuccessful work cannot disappear from the count.

## Selection and uncertainty

For each method, the planner collects its observed catches and its distinguishable
alternative pairs. A caught/missed conflict on the same fixture removes that
fixture from demonstrated coverage. Conflicting predictions for one alternative
cannot establish discrimination involving that alternative. Unassessed and
missing observations remain visible. Predictions from different methods are
never combined into a fictitious within-method prediction.

Baseline coverage is the union of the already used methods' demonstrated
coverage. A second method missing a fault does not erase another method's catch.
Candidates report the additional uncovered faults and alternative pairs they
would address. This is coverage of finite declared fixtures; it is not the
probability of detecting an arbitrary real-world error.

A stale/missing dependency, denied authority, unavailable/unknown availability,
unknown cost, exceeded budget, or absence of measured additional benefit excludes
a method from selection. Stale methods and their historical receipts stay
visible. When a used receipt has stale dependencies, `support_binding` reports
that staleness; it does not relabel the caller's support as truth or falsehood.

The Pareto frontier retains methods that another eligible method cannot match
or improve on **both coverage sets** at equal or lower cost. Counts alone do not
make different faults interchangeable. All incomparable candidates remain in
`pareto_frontier`. The lexically first method ID is the explicit stable selection
rule. No hidden weights, universal confidence score or independence multiplier
is used.

Support and inquiry stay separate. Support states are `unassessed`,
`conditional`, `supported`, `contested`, `unavailable` and `withdrawn`; these are
caller-supplied and retained unchanged. Inquiry states are `planned`, `running`,
`completed`, `stopped` and `awaiting_evidence`. A running inquiry yields
`await_current_inquiry`; a withdrawn claim yields `claim_withdrawn`. A stopped or
completed inquiry with a useful admitted candidate yields `reopen_recommended`,
retaining the earlier reason/history. With no candidate, the result is
`no_admissible_measured_gain`, not a claim that all possible inquiry is exhausted.

The result schema is `symblic.inquiry.plan.v1`. A non-null recommendation has
schema `symblic.inquiry.recommendation.v1`, an exact input-derived ID, claim,
scope/method/assessment hashes, supporting receipt IDs, cost, new coverage,
selection reason and `authorizes_execution: false`. Store or execute it only
through existing host policy; the pure planner grants neither authority.

## Minimal example

This synthetic example recommends an instrument check that catches a declared
calibration fault. No instrument is invoked.

```python
import symblic.inquiry.selection as inquiry

h = inquiry.digest
claim = {"id": "reading", "revision": 1, "sha256": h("caller claim")}
source = {"id": "instrument", "revision": 1, "sha256": h("instrument v1")}
scope = {
    "id": "reading-check", "revision": 1, "claim": claim,
    "domain": "synthetic measurement", "units": "dimensionless",
    "outcome_schema_sha256": h("exact integer"),
    "faults": [{"id": "calibration", "fixture_sha256": h("fixture")}],
    "alternatives": [],
}
method = {
    "id": "calibration-check", "revision": 1, "implementation_sha256": h("checker"),
    "acquisition": [source], "interpretation": [], "assumptions": [],
    "authorized": True, "available": True,
    "cost": {"amount": 2, "receipt_sha256": h("measured cost")},
}
scope_hash = inquiry.scope_digest(scope)
assessment = {
    "schema": inquiry.ASSESSMENT, "claim": claim, "scope": scope,
    "scope_sha256": scope_hash, "dependencies": [source], "methods": [method],
    "receipts": [{
        "id": "fixture-run", "scope_sha256": scope_hash,
        "method_id": method["id"], "method_sha256": inquiry.method_digest(method),
        "status": "completed", "predictions": [],
        "faults": [{"id": "calibration", "fixture_sha256": h("fixture"),
                    "outcome": "caught", "witness_sha256": h("observed rejection")}],
    }],
    "used_receipt_ids": [], "budget": {"unit": "milliseconds", "remaining": 5},
    "support": {"status": "conditional", "reason": "Calibration remains an assumption."},
    "inquiry": {"status": "planned", "reason": "Check calibration.", "history": []},
}
recommendation = inquiry.plan(assessment)["recommendation"]
assert recommendation["method_id"] == "calibration-check"
assert recommendation["authorizes_execution"] is False
```

## Bounds and checks

Limits are 64 methods, 256 receipts, 128 faults, 16 alternatives, 256 current
dependencies, 32 references per method role, and 64 inquiry-history entries.
IDs have at most 160 ASCII identifier characters; other strings have at most
4096 characters. Exact integers are bounded by `2**53 - 1`. Input and output
each obey a 1 MiB bound, 65,536 visited JSON nodes and nesting depth 16. Repeated
aliases spend work for every occurrence; cyclic inputs refuse. An output that
would exceed bounds refuses instead of returning truncated evidence.

The isolated test suite covers shared acquisition, calibration changes,
repetition, unsuccessful outcomes, conflicting evidence, stopped/reopened
inquiry, stale pins, unknown costs, exact Pareto behavior, no execution authority,
input preservation, duplicate IDs, numeric/schema errors and resource bounds.
Those checks establish behavior of this planner. They do not establish real
measurement accuracy, empirical independence or model-quality improvement.
