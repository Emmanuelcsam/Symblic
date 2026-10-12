# Durable finite policy experiments

**Status: integrated in Symblic 2.5 and included in the live RC2 release.** The
store, native graph runner, operator API and Automation Studio Policies interface
are connected. The release smoke-checks the pure example/check route; component
checks use temporary stores and fake providers. No new real-model routing
improvement or statistical generalization result is claimed.

`symblic/policy/store.py` turns the pure selector into a host-driven experiment
lifecycle. It starts no worker, opens no global data directory, calls no provider,
and never adopts a selected policy automatically. The host supplies an authorized
private root and trusted execution/recovery callbacks. Hashes are integrity pins
relative to the host's saved freeze identity; they are not signatures.

## Freeze before execution

`case_fixture(input_value, expected, family_hash=..., exposure_hashes=...)` builds
an evaluator-owned exact-output fixture and its case/input/family/exposure hashes.
Both training and heldout fixtures must be supplied to
`PolicyExperiment.freeze(root, ident, training_plan, heldout_plan,
training_fixtures, heldout_fixtures, cost_unit=..., host_identity=...)` before any
assignment runs.
The plan schemas and exact objective are documented in `POLICY-LEARNING.md`.
Cases and policies must match their pins. Declared split-resource identities must
be disjoint across every role. This is a declared exposure audit, not a detector
for hidden model pretraining or semantically duplicated examples.

Save `experiment.freeze_hash` in the host's existing private job record. Reopen
with `PolicyExperiment(root, ident, expected_freeze_hash=that_hash)`. Repeating the
same freeze is idempotent; changing a frozen file requires a new experiment ID.
All plan, fixture, intent, outcome, result, selection and evaluation files use
bounded canonical JSON. Experiment directories are private to the current UID;
files are mode 0600, directories 0700. A per-experiment flock serializes mutation.
Files are fsynced before exclusive publication and parent-directory fsync. An
interrupted publication can leave a private `.pending-*` hardlink; it does not
invalidate an already complete immutable file. The module does not register a
new application data path or alter the dashboard's private-store registry.

## Host API

- `assignments('training')` returns the complete frozen candidate × case matrix.
  Each descriptor contains `assignment_id`, `stage`, `candidate_sha256`,
  `case_hash`, `policy`, and `state` (`pending`, `inflight`, `terminal`).
- `run_assignment(stage, candidate_sha256, case_hash, runner=trusted_callback)`
  writes a durable intent before calling the runner. The request contains the
  frozen policy, case input, common budget and cost-unit definition. Expected
  outputs and heldout fixtures are never added to a training request.
- `seal_training()` requires every planned assignment to have a verified terminal
  result and complete known accounting, runs the pinned pure selector, and freezes
  the selection. Existing results remain readable; further training cannot alter
  selection. `selection()` reads and replays training evidence only, without
  opening heldout files.
- `assignments('heldout')` is available only after training seal. It exposes only
  the selected policy and baseline across the already frozen heldout cases.
  `seal_heldout()` compares those policies and writes the immutable evaluation.
  It cannot reselect a different policy using heldout scores.
- `status()` returns the stage (`training`, `heldout`, `evaluated`), frozen hashes,
  candidate policies, pending/inflight/terminal counts and assignment IDs, and
  selection/evaluation when available. It excludes fixture inputs, expected
  outputs and raw provider data. Candidate policy contents are host-supplied;
  the host must not publish confidential policies to unauthorized viewers.

A runner request has exactly these fields:

```text
version, assignment_id, experiment_sha256, stage, candidate_sha256, case_hash,
policy, input, budget, cost_unit
```

The injected runner returns a bounded exact JSON object:

```python
{
    "status": "done",  # or failed/refused/uncertain
    "output": exact_output,
    "attempts": [{
        "id": stable_host_attempt_id,
        "request_sha256": pinned_attempt_request,
        "calls": known_nonnegative_integer,
        "cost_units": known_nonnegative_integer,
        "status": "done",  # or failed/refused
    }],
    "checks": [{
        "scope": "encoded_predicate",  # schema/formal_proof/source_witness also supported
        "passed": True,
        "subject_sha256": digest_of_exact_output,
        "checker_sha256": pinned_checker_or_predicate,
    }],
    "complete": True,
    "effects": "none",  # or settled
}
```

Callbacks are trusted host code, never import strings or candidate-supplied
executors. Every attempt must be retained, including retries, unsuccessful calls
and rejected answers. Attempt IDs cannot be reused across assignments. Unknown
costs, incomplete calls, unresolved effects and exceeded budgets block sealing.
The fixed scorer grants `max_score` only for a done outcome whose full exact JSON
output equals the evaluator-owned expected value and whose supplied checks all
pass. A schema check alone cannot grant a wrong answer a score. Failed and refused
outcomes remain in the denominator with zero score and their complete costs.
Receipts explicitly do not establish empirical truth, statistical confidence or
causal improvement.

## Recovery

A completed assignment is returned idempotently without calling the runner again.
If an outcome was fsynced before interruption, the store can finish publishing its
result without execution. An intent with no accepted outcome remains inflight;
calling `run_assignment` again does not redispatch it. Use
`reconcile_assignment(..., resolver=trusted_journal_query)` to query the original
host execution by identity. Original uncertain/rejected outcomes remain immutable;
a reconciled outcome is recorded separately. The resolver must not create new
work. The library cannot enforce this property on arbitrary injected Python code.

## Executable graph route selection

`symblic.policy.graph.GraphPolicyRunner(folder, applicators, stop=None)` is the
provided trusted runner for routing-policy candidates. Fixture input is exactly
`{"graph": graph_spec, "output_node": node_id}`; candidate policy is the graph
routing policy. `validate_case(input_value, policy, budget=...)` admits that shape,
output node, effect-free graph and common budget before freezing. Native graph
execution separately verifies source, profiles, routes, schemas and runtime pins.
The integrated API performs those full preflight checks for every candidate and
case before launching a study. Other Python hosts must perform equivalent
admission themselves; the generic store does not infer a runner's semantics.

The scorer sees the chosen output node's exact value in the final iteration.
Every node must finish under its encoded graph contract for status `done`.
`cost_unit` is exactly `provider_calls`: one unit per issued Applicators.call
intent, including failed/refused requests. It is not dollars, tokens, elapsed time,
or a provider billing assertion. Receipts aggregate all calls for each immutable
node attempt, including graph retries. Graph reservation must fit both common
experiment caps and may be at most 64, preserving the selector's attempt bound.
Effects and arbitrary candidate executors are unsupported in this wrapper.

Use the runner with `run_assignment`; use `runner.resolve` with reconciliation.
`resolve` revalidates existing graph journals and never invokes `execute` or makes
a provider call. A still-incomplete graph remains unresolved. A new policy can be
used only in a separately frozen future graph run. This is measured finite routing
selection, not neural backpropagation or an open-ended self-improving optimizer.

## Implementation and host identity

The freeze manifest also pins the source hashes of the policy selector, durable
store, graph-policy wrapper and both graph modules. The store records their
import-time source identities and refuses on-disk changes until a fresh worker is
used. A fresh worker still must match the experiment's original implementation
pins. The bounded execution helper checks Python caches that could otherwise load
bytecode from different source. These are compatibility/integrity checks, not
attestation against arbitrary in-process monkeypatching or a malicious host.

`freeze(..., host_identity=None)` additionally binds a host-defined bounded exact
JSON runtime/measurement contract. A native graph host should freeze its verified
execution module/library hashes and graph implementation identity here. On view,
resume and before each assignment, call `assert_host_identity(current_identity)`;
a changed runtime refuses with `host_identity_pin`. The generic injected-runner
store does not guess the host's dependencies. `status()` exposes only
`host_identity_sha256` and implementation hashes, not the underlying private host
configuration. `None` remains valid for generic experiments whose host does not
supply additional identity; this does not claim cross-runtime comparability.

The integrated API supplies a non-null native runtime identity containing the
current kernel, registered execution-module/library hashes and execution pin
identity. It checks this identity when opening an audited view, exporting the
selection, starting a worker and before every assignment. A completed selection
does not retain current assurance after implementation or native runtime drift.

## Operator API, interface and current evidence

The existing Symblic engine routes `/api/automation/symblic/policy/` to
`integration/host/symblic_policy_api.py`; every HTTP route requires proven operator identity.
`GET example` and `POST check` do not create experiments or call providers.
`POST run` can require the reviewed plan hash and freezes the exact candidates,
fixtures, objective, budget and identities before using the existing job launcher.
Experiments live below the existing private Symblic data root.

`GET runs`, `GET run?id=...`, `GET selected?id=...`, and `POST stop`/`resume`
support inspection and recovery. Shared graph job controls reserve one launch
generation, suppress duplicate pending launches during startup grace, persist
cancellation before stopping, and reject delayed or superseded workers. An
inactive interrupted stop can resume under a new generation; the old cancellation
marker remains. Malformed metadata and job records fail visibly rather than
granting a run or selection status.

The list shows recorded status. An opened view checks current host identity and,
once selected, audits completed native graph receipts through a no-dispatch
adapter. An evaluated view includes heldout receipts. The selected-policy endpoint
audits training evidence only and compares native graph outcomes with the store's
immutable outcomes; it does not consult heldout results to choose or export a
different policy. Missing or changed evidence produces unavailable/refusal, with
no automatic model replay. These checks rely on the declared exact-output scorer
and trusted host boundary; they cannot establish that a test captures the operator's
full intent or detect undisclosed training exposure.

The Policies interface exposes the editable experiment, Check, Run, saved status,
stage/accounting receipts and recovery controls. Editing invalidates the checked
plan. Its explicit “Copy selected policy to Graphs draft” action reopens the
selection through the audited endpoint and changes only a future graph draft.
That graph must be checked again before execution. No ongoing run is changed and
no selected policy is adopted automatically.

Focused tests exercise the actual store/graph/API chain with fake Apps, including
known call costs, heldout isolation, frozen-source changes, terminal idempotency,
operator gating and cancellation generations. API adversaries cover malformed
records, interrupted stops and host-identity drift. Fresh remote checks of the
final frozen integration remain distinct from earlier component results; do not
sum overlapping suites into a release or reliability claim.
