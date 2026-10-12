# Optional compact capsule annotations

The native `capsule=compact` option installed in the 5 October reform shortens selected provenance
annotations. `full` remains the default. This changes presentation, not the
accepted task values, provenance records or logical checks. It is not evidence
that a model becomes more accurate or that complete tasks cost less.

```symblic
use capsule=compact.
let amount = 7.
ask doubled:Int "Double amount." from amount with effort=low.
ask description:Text "Describe amount." from amount with capsule=full,effort=low.
```

A per-ask option overrides the `use` or routine default. Host `Run` options can
also set `capsule`. The pure rendering API is
`S.capsule(..., presentation="compact")`. Values are exactly `full` or `compact`;
an invalid value refuses before that ask dispatches. These option words are not
shadowed by ordinary variables. Agents can also set `"capsule":"compact"` on
the [delegation task envelope](AGENT-DELEGATION.md). Template compiler version5
binds this choice into the source, options and contract ID; saved declarations
reject a changed presentation on recovery. No new provider is required.

## Retained information and identity

Compact omits only the top-level annotation fields `claim_sha256`,
`value_sha256` and `conditional_roots_sha256`, and only when their values are
exact lowercase 64-hex strings. It preserves all other fields: status, origin,
support, root origins/counts, uncertainty, completeness, omitted-root counts and
empirical-truth flags. Unknown hash fields, malformed digest values and nested
fields remain visible. Actual selected task values are never transformed,
even when those values contain a field with one of these names.

The context manifest retains the complete detached provenance table and all
included/omitted row receipts. Fact groups compare the full provenance identity,
so different roots with matching compact summaries never merge into one group.
Compact adds an explicit prompt notice that the exact annotation hashes remain
in the host manifest.

Manifest/kernel capsule semantics are version **5**, following version4's
invisible-header quoting and exact closed-code-fence preservation. Manifest
fields record `presentation`, `annotation_omission_scope` and
`annotation_omissions`; the latter lists only fields removed from annotations
actually displayed. Entirely withheld annotations remain separately reported
by `provenance_withheld`.

Compact-only `context_identity_sha256` binds the full provenance table,
included/omitted rows, execution profile, context budget and annotation
projection. The call key incorporates this identity as well as the actual
request. Changed hidden roots cannot reuse a matching visible prompt's cached
answer or replay entry. Full presentation retains the previous call-key shape.
Kernel/runtime version checks still apply to both presentations.

## Budgets and recovery

Verified context accounting includes the system string, complete prompt and
canonical serialized response schema, measured in Unicode characters. Compact's
notice counts too; a capsule with little provenance can become larger. Optional
rows can fit differently under the same budget. Required values still refuse
on overflow rather than being silently truncated. Legacy row accounting retains
its documented scope; annotation withholding remains explicit.

Voting, escalation, search, native reasoning, Code answers, foreach, routines
and repairs receive the selected presentation. Each repair retains full context
identity and accounts for its actual sent prompt. Call budgets, fatal provider
failures, proof-command checks and external-effect restrictions are unchanged.
No provider call is added by selecting compact.

## Evidence and measurement scope

Twenty focused fake-provider checks passed on the private current-stage rebase,
including four exact frozen version4 full-presentation cases, full provenance
retention, group separation, compact cache/replay identity, request budgets,
call-route propagation, version4 quoting, proof-command integration and fatal
provider refusal. They establish those tested contracts, not model quality.

Root integration repeated those 20 checks and added five delegation checks:
default/explicit-full parity, validation and discovery, unchanged acceptance and
repairs, standalone compiled-source behavior, presentation drift on recovery,
and zero-call arithmetic. Existing delegation/routing checks also passed. One
new test initially compared the internal tuple with a JSON list; its corrected
assertion uses the declared canonical output representation.

A separate offline measurement counted **saved system + two line breaks +
saved prompt** on earlier frozen prototype strings. It excluded the response
schema, provider wrappers, outputs, authoring, retries and checker work. Those
counts do not measure current complete provider requests or end-to-end savings.

| Earlier frozen pair | cl100k full → compact | o200k | Qwen3 | Phi4-mini | Gemma3 |
|---|---:|---:|---:|---:|---:|
| Synthetic integer, each profile | 622 → 469 | 615 → 463 | 640 → 469 | 615 → 463 | 733 → 490 |
| Synthetic code, each profile | 623 → 470 | 618 → 466 | 641 → 470 | 618 → 466 | 738 → 495 |
| Classification pair | 892 → 513 | 887 → 508 | 1073 → 513 | 887 → 508 | 1098 → 528 |

The offline evidence pins `tiktoken`0.14.0, `tokenizers`0.23.2, tokenizer files,
merge ranks and exact input strings. It ran with networking disabled and zero
model calls. Equal Phi/o200k counts are observations on these strings, not a
claim that those tokenizers are interchangeable. The current version4 full
fixtures preserve newer system instructions; the older measured counts must
not be relabeled as a new runtime measurement. A quality/cost comparison needs
matched information, validators, budgets, feedback and all assigned attempts.
