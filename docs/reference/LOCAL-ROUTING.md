# Local model routing for delegated templates

This routing interface is included in the installed 5 October reform; see [5 October release evidence](evidence/2026-10-05-reform-install.json). Installation and real-model evaluation remain separate. The routing policy helps choose the next constructor after a detectable failure; it does not make an accepted answer semantically correct.

`symblic.delegate.run.prepare()` compiles the existing template and selects one native `Run` policy. The template source, input bindings, checks and base `contract_id` stay unchanged. A separate `routing_id` binds the complete canonical routing plan and execution options, including their execution-pin receipt, to that base contract.

## Choice and authority

| Caller `by` | Native behavior |
| --- | --- |
| Omitted, model template | Ordered local ladder with shared zero repairs |
| Omitted, exact arithmetic | No model route; zero model calls |
| One string | Existing explicit single-applicator behavior, including template retries |
| List of 1–12 distinct strings | Exactly that ordered route, including a singleton list; shared zero repairs |

The default observed installed order is `ollama:llama3.2:1b`, `ollama:granite3.3:2b`, then `ollama:qwen3:4b-instruct`. Ascending parameter count is a heuristic, not a quality ranking. No availability reservation or provider request occurs during preparation. The earlier proposed 3B and 8B tags were catalog entries without corresponding installed-model evidence in this review; they are not default rungs.

The default allows local applicators only. A cloud engine is permitted only when explicitly named by the caller. A protected acquisition still restricts native automatic routing to local engines. The API validates the entire raw `by` value: it rejects oversized or empty lists, malformed items and duplicate names without truncating or collapsing lists. Selecting different names does not establish independent models or authenticated model-family identity.

The existing explicit single-string council option is preserved. Its native dispatch is one applicator call; this wrapper does not establish a ceiling over the council's nested provider calls. Councils and the kernel cannot be hidden inside an automatic route list.

```text
python3 symblic/delegate/run.py run task.json --agent-json
python3 symblic/delegate/run.py run task.json --by ollama:qwen3:4b-instruct --agent-json
python3 symblic/delegate/run.py run task.json --by ollama:llama3.2:1b --by ollama:granite3.3:2b --agent-json
```

## Shared repair policy

The delegated automatic route contains:

```json
{
  "by": "auto",
  "auto_route": {
    "candidates": ["ollama:llama3.2:1b", "ollama:granite3.3:2b", "ollama:qwen3:4b-instruct"],
    "max_calls": 3,
    "repairs": 0,
    "declared_repairs": "shared",
    "allow_cloud": false
  }
}
```

Every model template already declares `route=escalate`. Without the opt-in, the native runner gives each candidate the template's declared retries. A one-shot template can therefore spend its whole call ceiling repairing the first candidate. The new `declared_repairs="shared"` policy applies the native shared correction allowance to these declared routes. With zero shared repairs, a rejected sample advances to the next rung.

The opt-in does not remove the mandatory anchored `ensure ... else retry` contract, alter an explicit single-model choice, or raise the template's call ceiling. Each ask starts at the first rung; all asks share the same ceiling. No candidate is adopted unless it passes the template's native type and encoded predicate checks. Incremental proofs still check each proposed inference through the existing proof-session adapter.

`max_calls` counts charged native applicator dispatches. A confirmed pre-dispatch refusal is refunded because no model saw the prompt. A missing-model response currently marked `fatal` rather than `refused` still consumes a charge. Returned failures and cancelled or uncertain dispatches are not assumed free. With a run directory, the native budget ledger reserves before dispatch and retains charges across resumes; cached replies do not dispatch again. An in-memory invocation has no cross-process persistence.

## Identity and durable verification

The API preserves the prepared `by="auto"` and `auto_route` options only through the server-created delegation contract. Generic run options cannot silently substitute an arbitrary routing policy. The same pure `verify_declaration()` reconstructs and checks:

- the original template request, base contract, exact source and inputs;
- the canonical requested route, cloud permission and shared-repair policy;
- every allowed execution option and the execution-pin receipt;
- the separate `routing_id`.

Verification occurs before API launch, before API resume, before worker provider construction/dispatch, and when returning the compact result. A worker refusal writes a separate `delegation-refusal.json`; it preserves an existing state record and creates a failed state only for a run that has no prior state. Legacy declarations retain their explicit single-string behavior and reject unbound automatic-route options.

For model templates, pins also include `symblic/providers/applicators.py` and `symblic/providers/ollama_call.py` when those names are admitted to the execution registry and their files exist. Exact arithmetic keeps the pure required-file path. These are code-compatibility pins, not model-weight attestation. The entire the fleet runner host is not claimed as part of the language kernel's identity.

Hashes detect changed or misfiled records. They do not authenticate an operator or defeat a host writer who replaces an entire record and its hashes. Operator API authorization remains a separate existing boundary.

## Receipts and limits

`routing.asks` is static disclosure. `full_attempt_budget_reach` assumes every visited rung spends its stated samples; `reach` permits free pre-dispatch refusals, so it can exceed the charged-call ceiling. Neither value forecasts success or reserves capacity.

The direct helper returns the requested plan, `routing_id`, current-invocation `calls`, durable `model_budget`, cached-request count, filters and completed-rung summaries. A summary's `sample_attempts` can include cached replies; it is not a provider-call counter. An exception can interrupt a rung before a summary is emitted, and the receipt explicitly states that limitation. Native call and budget records retain the underlying accounting.

The API compact result returns the bound policy and call/budget totals; it explicitly labels the native trace as not included in that compact result. It does not claim an omitted trace is empty. Detailed records remain in the existing run interface and private run folder.

An accepted enum classification proves only membership in the caller's categories. A source witness proves only its declared association and extraction checks. Agreement, a larger model, or a different route never upgrades these scopes to empirical truth. Finite fake-provider checks establish routing and accounting behavior; they are not a model-quality benchmark.

## Focused verification

The isolated tests use deterministic fake providers, temporary stores and fake launchers. They cover default ordering, explicit strings and lists, shared and legacy repair behavior, checked proof-step escalation, refunded refusals, charged failures, total and durable budgets, cached resumes, strict API validation, exact policy/pin drift refusal, worker pre-dispatch verification, preserved prior state, and compact result identity. The existing automatic-route and budget suites are also run against the small native-runner hunk. No model or fleet job is launched by these tests.
