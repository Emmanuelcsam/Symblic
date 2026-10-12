# Differential questions for code specifications

`symblic/spec/compare.py` compares explicitly supplied JavaScript candidates
without calling a model. It reruns every exposed unit example against each
whole assembled candidate, using that unit's declared test setup. Candidates
that pass every exposed check can then be compared on the same caller-supplied
probe expressions.

Different valid JSON results produce a proposed example question. The result
lists observed alternatives and leaves `expected_json` unset. It neither chooses
a majority answer nor modifies the operator's specification. The operator resolves
the intended behavior and may add an example through the existing editing flow.

The module, `spec/compare` API and Build interface are included in the installed
5 October reform; see the [5 October release evidence](evidence/2026-10-05-reform-install.json). Its focused tests exercise
fake result protocols and the existing local JavaScript sandbox. Those component
tests are not a model-quality benchmark or a live test of every comparison.

## Three distinct comparisons

| Comparison | What it establishes | What it does not establish |
| --- | --- | --- |
| Exact source agreement | Identical ordered script pieces, including their boundaries. | That the shared program meets the intended behavior. |
| Exposed-check validity | This assembled candidate passed all recorded unit examples under each unit's setup. | Arbitrary prose compliance, untested behavior, or optional declaration policies from a separate build. |
| Probe agreement or divergence | Eligible candidates returned equal or different JSON observations on these explicit expressions. | Universal equivalence, authenticated model independence, or which answer is correct. |

Errors, timeouts, malformed JSON and output-limit failures are unresolved
observations, not alternative answer votes. A valid divergence between two
eligible candidates can still be reported when another eligible candidate has
an unresolved observation; that incomplete coverage remains visible. Agreement
requires at least two eligible observations and no unresolved eligible candidate
on that probe. Candidates that failed or could not finish their exposed checks
remain listed but are excluded from the comparison.

Labels are caller-supplied attribution. Calling candidates “model A” and “model B”
does not prove their origin, acquisition method, independence or model family.

## API and executable example

```python
compare(sheet, candidates, probes, *, deadline_seconds=30, externals=())
```

`sheet` is a strict task-card spec with one `.js` output. Each candidate has
exactly `label` and `source`; source is JavaScript text or an ordered list of
script pieces. Supply the already assembled candidate, not a path or unexpanded
template. The helper preserves piece boundaries because separate classic
scripts can have different declaration behavior from a joined string.

A probe is either an expression string or an object with `id`, `expression` and
an optional exact plan `unit_id`. A string gets a stable positional probe ID.
Without `unit_id`, the expression runs after the candidate alone. With one, that
unit's setup runs first for every candidate. The helper does not infer a setup
from a function name. External Uses names require the explicit `externals`
argument; names alone do not provide an implementation.

```python
from symblic.spec.compare import compare

sheet = '''# output.js
## Unit `f(x)`
Return x+1 for integer inputs.
Examples:
    f(1) ==> 2
## Assemble `output.js`
    /*UNITS*/
'''
candidates = [
    {'label': 'candidate-A', 'source': 'function f(x){return x+1;}'},
    {'label': 'candidate-B', 'source': 'function f(x){return x===-7?900:x+1;}'}
]
result = compare(sheet, candidates, ['f(1)', 'f(-7)'])
assert all(row['eligible_for_comparison'] for row in result['candidates'])
assert [row['status'] for row in result['probes']] == ['agreement', 'divergent']
assert result['proposed_examples'][0]['expected_json'] is None
```

Both candidates pass the single exposed sample. The new probe exposes a
behavioral difference that sample missed. The prose already states an intended
rule; this tool does not decide arbitrary prose meaning or replace that rule
with an observed majority.

CLI input is one JSON object containing `sheet`, `candidates`, `probes`, and
optional `deadline_seconds` and `externals`. The file is read without rewriting
it:

```sh
python3 symblic/spec/compare.py request.json --agent-json
```

The CLI always emits JSON. Exit zero means it produced a review record; inspect
the record's `status` and every candidate/probe outcome. It does not mean all
candidates passed. Invalid input produces a structured error and a nonzero exit.

## Recorded evidence

The report includes sheet and strict-plan hashes, candidate source and piece
hashes, exposed-check and probe identities, runtime and sandbox asset identities,
candidate order, every exposed-check outcome, every requested probe outcome,
and proposed example questions. No hidden test or reference implementation is
inserted into constructor data. The helper launches no constructor at all.

Python source hashes describe the files present on disk at comparison time;
they are explicitly not an attestation that an already imported Python module
has identical loaded code. The existing JavaScript adapter separately freezes
the actual runner and sandbox asset bytes used for dispatch. Exact loaded-Python
attestation requires the broader host runtime identity mechanism.

`candidates[].exposed_checks` is `passed`, `failed` for a known example mismatch,
or `unresolved` when no mismatch was observed but an example lacks a valid
result. Individual results preserve syntax errors, runtime errors and budgets.
`eligible_for_comparison` requires every exposed result to pass. Probe values
remain JSON text, with both an exact JSON-text hash and a semantic-value hash.

Grouping uses the existing `symblic.js.check.same` semantics: object key order does
not matter, list order does, numerically equal JSON numbers compare equally,
and booleans remain distinct from numbers. Semantic fingerprints use tagged
canonical values and exact decimal digits, avoiding float rounding and the
`true == 1` mistake. These fingerprints identify this comparison relation, not
arbitrary JavaScript behavior.

The existing adapter serializes `undefined` as JSON null and nonfinite numbers
as tagged JSON records. Those representation choices can erase distinctions
that another JavaScript observer would see. This tool records their scope; it
does not claim complete observational equivalence. A finite agreement is always
limited to the supplied expressions and sandbox environment.

Source or asset drift detected during the operation marks the review partial,
retains its observations, and suppresses proposed examples as usable conclusions
from that mixed runtime. Hashes are integrity references, not signatures.

## Bounds and execution

The existing required JavaScript sandbox executes candidate code. There is no
host execution fallback, direct provider, alternate process launcher or new
runtime. Every case uses a fresh V8 context. Expected examples are parsed as
JSON data and never inserted into executable probe expressions.

| Bound | Limit |
| --- | ---: |
| Explicit candidate labels | 1–8, unique, at most 128 characters each |
| Explicit probes | 1–64, unique IDs, at most 4,000 expression characters |
| Declared candidate-case evaluations | 2,048 total across examples and probes |
| Request JSON | 4 MiB |
| Candidate plus selected setup | Existing adapter limit: 400,000 characters and 200 pieces |
| Common execution deadline | 0.1–120 seconds, default 30 |
| One sandbox stdout response | 512 KiB, bounded during streaming |
| One retained JSON value | 32 KiB |
| Total retained JSON-value text | 1 MiB |
| One parsed value | 16,384 nodes and depth 32 |

The deadline begins before validation and is passed unchanged to every sandbox
dispatch. Native per-case and heap limits remain in force. Bounded report
assembly and serialization follow execution; elapsed time is recorded rather
than represented as an exact real-time scheduling guarantee.

Exposed checks run in unit-order rounds across candidates, including after an
earlier known mismatch. Consecutive probes with the same setup are grouped in
batches of at most eight; each case still gets a fresh context. Candidate order
is explicit. A deadline can censor later observations, which remain listed as
budget or unassessed outcomes. Equal ceilings do not imply equal completed work.

`work.declared_evaluations` counts the full input comparison workload;
`requested_evaluations` counts cases passed to the sandbox API, including a
request that times out before returning results. It is not a claim that every
requested expression finished. There are no inference costs or model success
rates in this helper's report.
