# Contracted agent graphs: planner, durable runtime and operator interface

`symblic/graph/planner.py` plans bounded graphs and reduces events without executing or
writing anything. `symblic/graph/run.py` now supplies executable composition via
existing `symblic.kernel.run.Run` and `Store`, injected registered Applicators, and an
optional existing effects host. It starts no worker on import and supplies no
provider, HTTP, SSH, subprocess or effect executor. The 2.5 source now connects it
to operator-only graph APIs and the Graphs interface in Automation Studio; that path
is included in the live RC2 release. The release smoke-checks the page and pure
example/check route, while component tests use injected providers. No performance
improvement, learning or backpropagation is claimed.

## APIs and node contract

`freeze_graph(spec, policy)` returns a detached version-1 object containing graph,
policy and their hashes. `derive(frozen, ledger)` returns ready actions, attempt
histories, call reservations and graph status. `event(...)` constructs a pinned
ordered event. `GraphRun(frozen, folder, applicators, stop=None, *, effects=None,
reviewed_hashes=None, checkpoint=None).execute()` performs sequential composition
and returns that derived graph state. The supplied folder is private; the caller
owns authorization, job placement, registered dispatch, cloud opt-in, deny-list
registration and presentation. GraphRun does not instantiate an Applicators client.

The graph has `id`, `nodes`, `iterations` (1–32), `max_calls` (1–10000).
Every node retains the planner’s fields:

- `id`: stable ASCII letter followed by letters/digits/underscores, ≤64 characters.
- `source`: explicit Symblic program, ≤32 KiB; `contract`: nonempty authored
  statement contract; `output_schema`: declared schema.
- `inputs`: named `{"node": "Other"}` or `{"literal": ENVELOPE}` references.
  `{"node": "Other", "delay": 1, "seed": ENVELOPE}` reads the prior iteration;
  delay zero is default, delay one requires a seed, other delays are refused.
  All references must exist and the topology without delayed edges must be a DAG.
- `join`: `require_all` waits for supported successful dependencies, blocking on
  any unresolved result; `collect_unresolved` waits for terminal dependencies and
  supplies complete status/error/result/origin records instead of bare values.
- `allowed`: nonempty lists `routes`, `providers`, `models`, `nodes` and boolean
  `local_only`. Restrictions intersect and cannot be relaxed by a policy.
- `effect_risk`: `none`, `read` or `write`; `retries` (0–8) permits extra attempts
  only after definitely known retryable failures; `call_limit` reserves the entire
  attempt; `max_calls` caps all node attempts and iterations; `max_iterations`
  must cover the graph’s explicit iteration count.

Executable nodes additionally declare `output_binding`, optional `checks` (≤32
predicate strings, each ≤4096 characters) and optional `assumptions` (≤128 entries).
The output binding is explicit; the adapter never guesses from a last printed
value or truncated trace. Each declared predicate must refer to that binding and
parse as exactly one formal assertion. `compile_node(spec, inputs, libraries=...,
allow_effects=...)` appends these checked predicates as native assertions to the
supplied source. It returns the compiled source, separate frozen inputs, hashes,
kernel identity, predicate identities/lines and constrained Run options. Inputs
must exactly match unique top-level `given` declarations. Values never become
source. Both original-source and compiled-source identities are retained.

For example, the essential runtime fields of an arithmetic node are:

```python
node.update(source='given x: Int.\nlet answer = x + 1.',
            output_binding='answer', output_schema={'type': 'integer'},
            checks=['answer = x + 1'], assumptions=['x uses the declared unit'])
frozen = freeze_graph(graph_spec, routing_policy)
state = GraphRun(frozen, private_folder, registered_applicators, stop=stop).execute()
```

The scheduler processes all nodes of one iteration before starting another. It
uses sorted ready batches, then executes each selected node sequentially with
Run’s parallelism set to one. Reservations pessimistically charge full call_limit
before started, never refund it, and cap each ready batch. The per-attempt call
journal separately bounds actual issued calls across every restart; internal Run
repairs share that cap. Native invocation call counters are diagnostic and may
include receipt-backed reads; `issued_calls` and graph reservations identify the
durable budget. A future bounded parallel lane must reserve each member under
flock, retain one durable attempt identity per member and deterministic reducer
ordering; **parallel graph dispatch is not implemented**.

## Results: contract support is not factual truth

An envelope retains exact JSON value identity, supported/contested/unknown outcome,
evidence, assumptions, provenance and `independence=not_established`. Existing
Symblic check receipts are retained directly; complete observed model/node and
binding evidence remain in the referenced immutable native report. Finite report
floats are tagged `finite_float_repr` when included in exact envelopes rather than
silently rounded. Kernel outputs are transported as exact JSON integers, booleans,
text, arrays and records. Nonintegral rationals require an explicit exact JSON
representation authored by the node; the adapter refuses to use rounded display
text as a numeric result.

`supported` in an executable graph means **supported under the declared encoded
node contract**. The envelope reports `scope=node_contract`,
`assurance=supported_under_encoded_contract`, `source_truth=contingent`, output
binding/hash, schema, accepted predicate receipts, graph/policy and execution pins.
Receipts must match the compiled predicate identities and final output binding
hash. The schema is checked through the existing FX schema checker, with unsupported
keywords refused beforehand. Adequacy of those predicates to intent or reality
remains an assumption. A typed output, unanimous guess, successful computation or
free-text contract alone does not produce supported: without declared predicate
receipts its outcome is unknown. Contested asks or unresolved collected inputs
produce contested envelopes and block downstream require_all gates. Input failures
and all provenance remain visible. Overall graph success describes checked graph
completion; it does not establish factual truth.

## Durability and recovery

GraphRun holds an exclusive `.graph.lock` flock for its execution, including calls.
A concurrent instance waits, then validates the full graph and every historical
attempt; it does not dispatch the same node twice. Cancellation uses the injected
stop event passed into Run and Apps requests, then writes a durable cancel event.
Completed and canceled resumes make zero model/effect calls. Cancellation does not
resolve uncertainty and does not kill unrelated workers.

Before dispatch it atomically writes and fsyncs `graph-pins.json`: frozen graph and
policy, kernel identity, all available registered execution modules and libraries,
`symblic/graph/planner.py` and `symblic/graph/run.py`, catalogue and scheduler identity.
Graph modules also check their process-import and cached-bytecode identities.
Optional reviewed_hashes must match the entire captured file map. These are local
integrity/compatibility pins, not signatures or authority. Graph-specific pins
supplement the existing execution registry. The 2.5 adapter explicitly requests
`execution_profile="verified"` from
the checker and `profile="verified"` from Run. Source declarations are preserved
and cannot weaken that host profile; this integrated adapter requires the pinned
2.5 profile and epistemic interfaces.

Each attempt lives under the supplied folder at
`attempts/IterNNN_Node_AttemptNN/`. Its durable `attempt-pins.json` contains the exact
ready action, compiled bridge and existing `symblic.kernel.execution_pins` pins. Libraries are
captured in execution pins and served by the existing language resolver. Started is
appended/fsynced to `graph-events.jsonl` **before** Run can execute. Native calls,
trace and state are kept by Run’s Store in that same folder.

The restrictive wrapper appends/fsyncs a call intent to `graph-calls.jsonl` before
injected Apps.call, then fsyncs a checked outcome after return. The journal retains
context, ordinal, native call key and complete-request hash. It conservatively
charges every issued intent, including provider refusals; it never resets or refunds
its budget on restart. Exceptions or invalid/mismatched attribution after issue
leave an unfinished intent. A standing intent is unknown: no model/effect is
redispatched, and a graph retry cannot make a new reservation for it.

Known outcomes are replayed through the existing Run cache and receipt wrapper,
including failed-call replies needed to recover correction paths. Starting Run
again in the same attempt folder is recovery, not a new graph attempt/reservation.
The adapter independently validates native cache entries against durable wrapper
receipts because native Store’s older JSONL reader ignores malformed lines. Missing,
partial, duplicated-field, reordered, conflicting or mismatched pins/logs are
refused without silently skipping corruption. GraphRun never truncates a log.
Unknown effect intents are checked before Run resumes, including read/idempotent
intents: this adapter does not exploit FX’s optional takeover to repeat them.

After Run ends, GraphRun fsyncs `graph-result.json` with result, native report and
issued-call count **before** the graph completion event. A crash in this window
commits the existing durable result on resume, without repeating Run/model calls.
A known completed effect interrupted before the graph result can be recovered by
the existing FX ledger without another host performance. A corrupt result is not
recomputed. The trusted checkpoint callback can simulate crash boundaries in tests;
it is not an untrusted plugin API. This is at most one automatic dispatch per
recorded call identity with explicit uncertainty, not exactly-once external effects.

## Routing and effects support matrix

| Capability | Current adapter behavior |
|---|---|
| Exact registered single model/provider/physical node | Enforced on every injected Apps.call, including repair and routine asks; replies must report exact successful model/node attribution. Explicit error attribution mismatches also stop recovery. |
| Local-only | Engine class comes from existing LOCAL_APPLICATOR_ENGINES, never a local flag or local CLI placement; conflicting route metadata is refused before dispatch. |
| Source by override | Only the exact frozen route is permitted; a disallowed branch/call is refused before Apps.call. |
| Automatic source routing | Refused without a resolved native auto policy; no fallback. This lane deliberately uses its own durable wrapper budget rather than resetting/reserving native automatic budgets for replayed failed calls. |
| Councils, delegation, model tools | Explicitly unsupported: nested calls/effects cannot hide in a single node reservation. Use declared graph nodes or a future contracted registered adapter. |
| Functions, routines, if/for, formal kernel operations | Existing language, kernel work bounds and Run are reused; native static checking applies. |
| Standard library imports | Supported when sources and transitive imports are registered, statically inspected and captured in execution pins. Saved/uncaptured imports are refused. |
| Implicit prose asks, arbitrary extensions, JS/process adapters | Explicit refusal before any node dispatch; no tiny alternate language or subprocess executor is generated. |
| Existing observe/act host | Supported only with explicit host, catalogue, idempotent_by_id=True, compatible execution pins and fsynced FX ledger. Runtime effects go only through existing FX and host.perform. Missing support gives an Unsupported error, while the pure planner still retains effectful nodes. |
| Program-scope effect ledgers | Not injected by this version; native scope=program reports its missing host ledger explicitly. Run-scope effect identity/recovery is supported. |
| Effectful graph retries | Explicitly unsupported until cross-attempt effect identity recovery is contracted; node retries must be zero. Completed effects in the same attempt replay from FX’s ledger. |
| Unknown/interrupted effects | Never automatically performed/replayed by this adapter, even when the existing host advertises idempotency; ownership/reconciliation stays in its established recovery path. |
| Cross-node protected/untrusted provenance | Conservatively preserved: private inputs/acquisitions and use of a private capability forbid cloud model calls, including loop/child scopes; private input egress and untrusted input acts are denied before host.perform. The adapter does not pretend a given value erased its incoming labels or that it can prove finer cross-node flow. |
| Output schema | Existing FX subset: type, enum, const, properties, required, boolean additionalProperties, items, size and integer numeric bounds; annotations allowed. Regex patterns, refs and combinators explicitly unsupported. |

The wrapper validates requested exact engine/model/node and actual engine locality
before dispatch, and verifies observed attribution after return. It is not a sandbox
against a malicious injected Python Apps implementation; the caller must inject
existing registered paths that honor exact placement and existing operator/cloud/
capability gates. No private workspace/tool capabilities are given to a model by
this module.

## Operator API and Graphs interface

`integration.host.symblic_engine` routes `/api/automation/symblic/graph/` to
`integration/host/symblic_graph_api.py`. Every HTTP route requires the existing proven operator
identity. `GET example` and `POST check` validate or return a document without
creating a run or making model calls. Check performs native source/profile,
route, schema and output-binding admission. `POST run` accepts optional reviewed
graph/policy hashes, freezes the document in the existing private Symblic data
root, and uses the existing job launcher. The web job accepts effect-free graphs;
the separate injected Python host interface retains the effects capabilities
documented above.

`GET runs`, `GET run?id=...`, and `POST stop`/`resume` expose saved execution and
recovery. A job reserves a random generation under a control lock before launch;
the launcher runs outside that lock. Pending resumes within the startup grace
period do not create another launch. A worker must present the current generation
and a starting job before execution. Stop persists its generation's cancellation
marker before waiting for the worker; a delayed or superseded worker cannot start
or overwrite a later generation. A confirmed inactive interrupted stop exposes
Resume, which reserves a new generation while retaining the old marker. This
control protocol supplements the graph's durable attempt journal; it does not
resolve an unknown provider/effect outcome.

Job records have validated shapes and generation identities. Metadata must match
the folder and frozen graph/policy hashes. Malformed records produce explicit
errors or unavailable list rows. Saved-run lists show recorded status without a
full native receipt audit. Opening a terminal run audits native pins, attempts and
journals through a no-dispatch adapter; missing, altered or incompatible evidence
cannot retain current success assurance. Such failures disable automatic resume.

The Graphs interface loads a deterministic example, keeps an editable JSON draft,
shows dependencies, checks and call reservations, and enables Run only for the
currently checked draft. Edits invalidate that check. It displays saved node
outcomes, full receipts, failures, Stop and eligible Resume controls. Reservations
are distinguished from issued calls. A policy copied from an experiment changes
only a future draft, which must be checked again; existing runs retain their pins.

## Reusing groups of nodes

The installed [composition interface](GRAPH-COMPOSITION.md) expands named inline
fragments with typed public ports into this same flat contract. Each leaf keeps
its source, checks, permissions and limits. Expansion creates no worker or run;
the ordinary Check → Run path and saved flat recovery remain authoritative.
The [5 October graph release](evidence/2026-10-05-graph-composition.json) records
live expansion/checks and a temporary-store, zero-model native computation.

## Limits and routing evidence

The planner caps 128 nodes/routes/inputs/evidence entries, 32 iterations, 10000
events, 24 JSON levels, 50000 items and 1 MB per pure JSON snapshot. The adapter caps
private JSON files at 8 MB, 10000 rows/files and bounded directory depth; symlinked
files/attempts are refused. Larger graphs/logs need an explicit future checkpoint
format rather than truncation. Persist exact JSON values, never float graph inputs.

`choose_route` uses fixed frozen order and intersects declared permissions.
`evaluate_policy` computes deterministic exact rational descriptive cost/success
statistics only from explicitly training-labeled observations. Held-out entries
are excluded, unlabeled entries refused, learner_supported=False and
performance_improvement_established=False. No policy training/optimization occurs
in these descriptive helpers. The separate finite candidate experiment lifecycle
is described below.

The integrated API injects registered Apps and the job cancellation signal;
GraphRun still has no autonomous provider or fleet executor. Focused tests use
fake Apps/hosts and temporary folders, forbid real dispatch, and
cover nonzero calls, joins/feedback, gates, budgets/restarts, pins/corruption,
concurrency, cancellation, attribution errors and model/effect crash boundaries.
API adversaries also cover pending/late workers, malformed control records,
metadata identity and current native-evidence audits. These checks exercise the
implementation; they do not prove checker soundness, semantic adequacy or fleet
availability. Exact commands and current frozen-source outcomes belong in the
release record rather than an aggregate count assembled from overlapping suites.

## Symblic 2.5 integration

Native graph nodes use the `verified` execution profile in both static checking
and `Run`; a source declaration cannot weaken that host choice. Consequently,
contested consensus/family requirements stop before downstream derivation rather
than yielding a legacy contested binding. Numeric strings representing exact
rational values remain an explicit wire format; extracting numbers from prose is
an undeclared transformation and is refused.

Graph-produced values preserve host-recorded epistemic origins across node
boundaries. A `given` receiving a prior node's value represents a checked transport
derivation, conditional on the original premises/model proposals. It does not
become a new operator assertion. Literal and seed envelopes remain caller premises;
model/caller-supplied evidence fields cannot forge a native node attestation.
Claims contain canonical value hashes, and context packing sends only selected
current values with origin/root summaries. It does not expand ancestral content.

Durable routing-policy experiments are described in `POLICY-EXPERIMENTS.md`.
They freeze train/heldout fixtures, route candidates, budgets and objective before
execution; graph journals provide actual attempt accounting. This implements
finite candidate routing selection for future runs, with declared exact-output
scoring. It makes no backpropagation, causal-gain or universal-learning claim.

Graph provenance contains direct producer node/iteration/attempt identities and
value, envelope, evidence and input hashes. It does not recursively copy parent
envelopes. Complete historical values and evidence remain in the graph ledger and
native attempt reports. Each output carries its full binding claim/assessment and
a pinned native-report reference with claim counts and registry hashes. A child
loads the complete required claim closure only from the producer path derived from
validated host graph events; model-supplied paths and literal evidence cannot
select files. Report hashes are checked before replay and transport. Existing
lineage summaries retain `lineage_complete=false`; compact transport does not
claim to reconstruct missing ancestry. Aggregated private/untrusted labels survive
every intermediate computation and continue to gate model/effect dispatch.
