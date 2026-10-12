# Source-linked context experiments

`symblic.experiments.context.catalog()` returns two synthetic examples and their
contracts. `run(experiment_id, data)` returns JSON-safe `arithmetic`, `results`,
`checks`, `limits` and `sources`. Invalid inputs raise `ValueError` with a short
code; no input text is echoed. The module is inert and makes no provider, file,
network, store or execution calls. These operations are available to a host's
experiment envelope; this module does not change native prompt construction.

## Extractive compression

`extractive-compression` takes exactly:

- `source`: `id`, positive integer `revision`, SHA-256 of exact UTF-8 `text`, and
  that `text`.
- `spans`: one to 64 records with unique `id`, Unicode code-point `start`/`end`
  offsets, Boolean `required`, and integer `priority` from 0 to 1000.
- `budget_bytes`: integer 0 to 65536; `query_terms`: up to 16 distinct terms;
  `merge_fanout`: integer 2 to 8.

It first selects every required span. Overlapping and adjacent intervals merge,
so shared evidence is not duplicated. Separate excerpts are joined by a newline,
an ellipsis and a newline. If that exact rendering exceeds the budget, the result
is `refused` with `required_budget` and no compressed output. It never silently
drops a required exception. Remaining spans are admitted by declared priority,
then source position and ID, whenever their merged rendering fits. This is a
deterministic greedy method; it makes no optimality claim.

The hierarchy groups the final exact source intervals with the declared fanout.
Each node records its intervals, covered span IDs, exact byte count and text hash.
Every merge stays within budget, and the root hash equals the compressed text
hash. Source text is never paraphrased or rewritten.

The result also reports full-source and simple keyword-retrieval baselines.
Retrieval ranks declared spans by how many case-folded query terms occur in them,
then by source position and ID, admitting matching spans that fit. It receives no
special mandatory-span treatment; its missing required IDs remain visible. This
comparison measures retention of caller-declared spans and exact bytes, not
whether the caller identified all semantically necessary information or whether
a model completes a downstream task. A supplied-source pin detects stale text.

## Scoped hash sidecar

`pinned-hash-sidecar` encode input is `{operation: "encode", card: ...}`. The card
has `id`, positive integer `revision`, `sha256` of canonical JSON content, and
`content`. Canonical JSON sorts object keys, uses compact separators and preserves
Unicode. Content supports objects, arrays, strings, integers, Booleans and null;
floating-point values are refused.

Repeated string values that are complete lowercase SHA-256 digests, optionally
prefixed by `sha256:`, receive deterministic short references such as `@h1`.
Dictionary keys stay literal. Original strings beginning with `@` gain an escape
`@`, so a literal `@h1` or a preexisting reference-shaped object cannot collide
with the encoding. All other content is retained exactly.

Decode input is `{operation: "decode", expected: ..., envelope: ...}`. `expected`
contains caller-pinned `id`, `revision` and content `sha256`, independently of the
envelope. Decode verifies that scope, envelope integrity, exact reference use and
the reconstructed content hash. Stale revisions, cross-card references, unknown
or duplicate references, unused sidecar entries and forged values refuse. A
resealed envelope cannot replace the caller's expected content pin. These hashes
establish integrity relative to the supplied pin, not source authentication.

The result measures original content, shortened model payload, sidecar and total
envelope bytes separately. A smaller payload does not imply a smaller complete
transport; sidecar overhead remains visible. Source information that a model
must read cannot be replaced by an opaque reference. This is structured hash
transport, not universal lossless text compression.

All trees are bounded to 4096 nodes and depth 16, with at most 128 members per
container, 64 references, 65536 content bytes and 131072 input/sidecar-envelope
bytes. Comparison responses have a separate 524288-byte cap because they retain
several source views. The complete result is checked against that cap before
returning. Exact byte accounting occurs before building the full serialization. Token counts are
explicitly **unmeasured**: no tokenizer is called or approximated. Regression
tests cover preserved exceptions, Unicode offsets, overlapping spans, hierarchy
reconstruction, budget refusal, stale source pins, literal reference collisions,
forged/resealed/cross-card references and independent byte accounting.
