# symblic/graph: agent graphs that never repeat an uncertain call

**What this package explores.** Many agent frameworks wire models together and hope for the best. An agent
graph here is a small, explicit workflow whose every step is a Symblic program with a contract: each node
declares its inputs (literal values or other nodes' results, optionally delayed by one iteration), the exact
applicator routes it may use, its output schema and the checks its output must pass. The question explored is
how far such a graph can be made *durable and honest*: frozen before it runs, executed one attempt at a time,
resumable after a crash without ever sending an uncertain model call or effect twice, and reporting
`unknown` instead of guessing.

**Status: prototype.** 106 unit tests cover the planner, the durable executor (with crash points, stops,
corrupted ledgers, capacity limits and loaded-code identity checks) and composition, all with fake applicators
and fake effect hosts. It has not been run as a long-lived service outside the original host.

## The modules

| Module | What it does |
| --- | --- |
| `planner.py` | Pure. `freeze_graph(spec, policy)` validates and pins a graph and its routing policy (every node compiled against the kernel, no undelayed cycles, worst case within the ledger). `Replay` / `derive(frozen, ledger)` fold the event ledger and return the deterministic ready batch. `envelope` wraps values with their outcome, evidence and provenance. |
| `run.py` | `GraphRun(frozen, folder, applicators, stop, effects=None).execute()`: runs each node attempt as an ordinary `symblic.kernel.run.Run` with execution pins, journals each model call before dispatch, records results, resumes after a crash, and refuses to continue if the graph code on disk changed. |
| `compose.py` | Reusable groups of nodes: inline definitions pinned by SHA-256, instantiated several times and expanded into one flat graph for the ordinary freezer. `python3 -m symblic.graph.compose catalog | example | compose FILE [--flat]`. |

## How a graph runs

```
spec + policy ──freeze_graph──► frozen graph (graph_hash, policy_hash)
                                   │
GraphRun.execute() ── per ready node attempt ─────────────────────────────────────────────┐
   graph-events.jsonl: 'started' row (route, inputs hash, call reservation)               │
   attempts/IterNNN_<node>_AttemptNN/: an ordinary run folder                             │
       graph-calls.jsonl: intent row ──► applicators.call(request) ──► outcome row        │
   'succeeded' | 'failed' | 'unknown' row ◄── output checked against schema and checks ───┘
crash ──► execute() again: known outcomes are replayed; an intent without an outcome stays unknown
```

A node result is `supported` only when its output matches the declared schema, every declared check on the
output binding passed in that run, and all its inputs were themselves supported; a contested answer or input
makes it `contested`, and an output with no check receipts stays `unknown`. `independence` is always
`not_established`, and `source_truth` is `contingent`: a check that passed shows the encoded contract held. Effects (`observe` / `act`) run only through a host object you
pass, which must be idempotent by ID. A stop either cancels durably or interrupts so the run can resume.

## Try it

```
python3 -m symblic.graph.compose example > reusable-graph.json
python3 -m symblic.graph.compose compose reusable-graph.json --flat
```

Running a frozen graph needs applicators: `symblic/providers` (a local Ollama model or an agent command
line) or a fake, as in `tests/graph/test_symblic_graph_run.py`.

## Outside this package

`integration/host/symblic_graph_api.py` is the original host's graph job service (HTTP routes, one background
worker per job with launch generations and a worker lease). It needs the host and is kept for reference; its
tests are in `tests/integration/` and skip without the host. `symblic/policy/graph.py` runs routing-policy
experiments on top of `GraphRun`.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/graph -t .
```

Run from the repository root. The suite is slow (10 to 25 minutes depending on the machine): every node
attempt builds execution pins. One test runs a private copy of the package in a child interpreter. No model,
network or worker is used.

Further reading: `docs/reference/AGENT-GRAPHS.md`, `docs/reference/GRAPH-COMPOSITION.md`.
