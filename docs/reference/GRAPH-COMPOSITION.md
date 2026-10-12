# Reusable graph fragments

Reusable graph authoring, 5 October 2026. Inspect the installed catalog with
`tools/symblic graph catalog --agent-json` before handing a composition to an agent.

Define a group of ordinary Symblic graph nodes once, name its public input and
output ports, and instantiate it more than once. Expansion produces an ordinary
flat graph. Each leaf retains its source, checks, permissions and call limits;
the existing graph runner performs execution and recovery.

## Agent entry

These commands make no model calls and create no run record:

```sh
tools/symblic graph catalog --agent-json
tools/symblic graph example --agent-json > reusable.json
tools/symblic graph compose reusable.json --agent-json > expansion.json
tools/symblic graph compose reusable.json --flat > flat-graph.json
```

The example uses the same two-node fragment twice. Each instance adds one to its
input and doubles the result: the supplied value 3 becomes 8, then 18. It uses
native arithmetic and needs zero model calls. Replace leaf source with explicit
asks and suitable checks to construct model-backed fragments.

The full expansion response contains `ok`, `version`, `draft`, `manifest` and
`scope`. `draft` contains exactly `graph` and `policy`. `--flat` returns only that
ordinary draft. A malformed input exits nonzero with `ok:false`; the CLI rejects
duplicate JSON keys, non-finite numbers and documents over the byte limit.

The parent agent retains the composition and expansion manifest, reviews the
flat graph, then uses the existing host's graph check and run interface. CLI
expansion does not authorize dispatch or promise that a particular host supports
every leaf's effects or route.

## Document and ports

The outer JSON has exactly `composition` and `policy`. The policy uses the
existing [graph routing contract](AGENT-GRAPHS.md). Composition version 1 has
exactly these fields:

| Field | Meaning |
|---|---|
| `version` | Integer `1` |
| `id` | Ordinary graph identifier |
| `definitions` | Map of definition names to inline fragment bodies |
| `instances` | Instance records with `id`, `definition`, `sha256`, `inputs` |
| `nodes` | Optional additional leaves, represented by an empty list when unused |
| `iterations` | One shared parent iteration clock |
| `max_calls` | One shared parent call cap |

A definition has exactly `nodes`, `inputs` and `outputs`. Its nodes are ordinary
complete leaf contracts, with public input slots omitted from their `inputs`
maps until expansion. Declare a port by naming its targets, for example:

```json
{"request":{"targets":[{"node":"Draft","input":"x"}]}}
```

The target source must declare an explicit top-level `given x: Int.` or another
supported native type. Preceding local type definitions work; imported type
aliases are not resolved by this authoring interface. An explicit `Any` gives
no structural guarantee. Fanout requires identical resolved types and join
modes. A public port cannot overwrite an existing internal input.

An output declaration such as `{"answer":{"node":"Check"}}` aliases that
leaf's complete output binding and schema. It does not extract a field or imply
that every other leaf succeeded. Use an ordinary join node when all branch
results are required. Unexported leaves remain part of the graph and can fail it.

An instance's inputs must bind every public input port exactly once. Values can
be literal envelopes, top-level node references, or an instance output such as
`{"instance":"First","port":"answer"}`. Ordinary `delay:1` and seed fields
retain the existing feedback semantics. References inside a definition name
only its own leaves or literal envelopes. External references cannot reach
private generated leaf IDs.

The instance's `sha256` must equal `symblic.graph.compose.definition_digest(body)`
for the exact definition. After editing an inline definition, explicitly repin
the instances and recheck the whole document. For a caller-owned file:

```python
import json
from pathlib import Path
import symblic.graph.compose as C

path = Path('reusable.json')
document = json.loads(path.read_text())
composition = document['composition']
for instance in composition['instances']:
    body = composition['definitions'][instance['definition']]
    instance['sha256'] = C.definition_digest(body)
path.write_text(json.dumps(document, indent=2) + '\n')
```

This explicitly replaces the author's expected digest. It is a source-integrity
operation, not proof that the changed fragment fulfills its purpose.

## Operator API and interface

`GET /api/automation/symblic/graph/composition-example` returns the example.
`POST /api/automation/symblic/graph/compose` accepts the outer document and
returns the expansion plus `check`, which reports the existing web host's
admission result. Both are operator-gated and read-only. Unsupported web effects,
routes or output schemas refuse before draft adoption.

In Graphs, the separate advanced composition editor offers **Expand to flat
draft**. Expansion preserves the composition for review and invalidates the
previous flat-graph check. Continue with **Check graph**, then **Run checked
graph**. An edit or navigation while expansion is pending prevents a late
response from replacing the draft. Errors preserve the input.

The browser accepts JSON integer literals only within
`-9007199254740991` to `9007199254740991`; larger exact integers remain available
through the Python-backed CLI. Fractional and exponent-form JSON numbers are
not part of the native graph contract. The editor checks original number text
before JSON parsing or dispatch and refuses unsafe response numbers before draft
adoption. Quoted numbers and source text remain ordinary strings. Keep the
original file and use `tools/symblic graph compose FILE.json --flat` for larger
exact integers, then send the flat document through a transport preserving its
bytes. This browser check is not a lossless JSON parser; shared response decoding
cannot recover numeric notation already discarded by that decoder.

The browser retains composition text and expansion provenance in its session.
Editing the flat draft detaches the old manifest from the current graph. Saved
runs contain their frozen flat graph and native receipts; they do not promise
recovery of the original reusable source. Retain that source separately.

## Bounds and evidence

Version 1 permits one expansion level, at most 32 definitions, 32 instances and
32 ports in each direction per definition. Both declared and expanded leaf
counts are capped at 128. Existing JSON byte/depth/item limits apply before and
after expansion. Unused definitions and nested instances refuse.

There are no definition clocks, group budgets or per-instance permission
overrides. Every leaf keeps its original limits, and the complete flat graph
must satisfy the existing cycle, delayed-seed, route and ledger contracts.
Producer-schema subtyping is not inferred from port declarations; the existing
native input and output checks still decide admissibility.

The manifest binds the exact composition, definitions, expander source, leaf
sources, flat graph and policy hashes, with readable port and node mappings.
It describes authoring provenance. It grants no new permissions, makes no
truth claim and is never used instead of the runner's own frozen contract.
