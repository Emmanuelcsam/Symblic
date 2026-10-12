# Solver proposal provenance

Symblic distinguishes solver proposals from model proposals and checked
derivations. The pure claim format is integrated with the optional
[constructor runtime](CONSTRUCTORS.md), its durable journal, native validation,
portable locks and notebook import checks. Solver installation is a separate
[host provisioning](CONSTRUCTOR-PROVISIONING.md) operation.

`solver_proposal` distinguishes a solver-constructed value from a model proposal
and a checked derivation. Passing an encoded schema or predicate does not establish
empirical truth, uniqueness, or the truth of the inputs. The proposal contributes
its own conditional root alongside the roots of its declared dependencies.

| Record | Format |
| --- | --- |
| Existing six claim origins | 1, unchanged |
| `solver_proposal` claim | 2 only |
| Schema, predicate and derivation receipts | 1, unchanged |
| Context manifest | 1, unchanged |
| Epistemic semantics in `kernel_id()` | 2, a separate marker |

The two claim versions have the same fields and byte/hash encoding. Version 2
admits only `solver_proposal`; version 1 admits only the existing origins. Old
readers refuse version 2 instead of interpreting it as a model or operator claim.
Existing valid claim and receipt bytes and hashes remain unchanged. The added
semantic marker changes kernel identity, so execution pins must be refreshed
through the normal reviewed integration process.

The default solver status is `unknown` and support is `premise`. Declarations
of `contested` or `refuted`, disagreements and withdrawal retain their existing
meaning. A solver claim cannot request `conditional` status or carry any
`encoded_derivation` receipt, including a failed or zero-input receipt. A separate
`derived` claim may use a solver proposal as a dependency; its checked conclusion
then remains conditional on that proposal and its input roots.

The existing pure API constructs a host-supplied envelope:

```python
import symblic.kernel.epistemic as EP

content = {"value_sha256": EP.digest({"#q": "1/2"})}
proposal = EP.make_claim("example.solver", content, origin="solver_proposal")
assessment = EP.evaluate([proposal])["example.solver"]
assert proposal["version"] == 2
assert assessment["status"] == "unknown"
assert assessment["support"] == "premise"
assert assessment["empirical_truth"] == "not_established"
```

This example illustrates the data contract; it supplies no solver execution
evidence. `make_claim`, `validate_claim` and `receipt` are trusted-host APIs, not
attestation validators for arbitrary client uploads. Hashes bind exact data and
references; they are not signatures. Claim content stays bounded exact JSON and
has no solver-specific required metadata at this pure boundary. In particular,
content fields such as `unique`, `confidence`, or a purported outcome ID grant
no assurance. The runner bridge verifies the durable constructor outcome, exact
source/options/input identities and original native checks before creating this
origin. An ordinary model reply retains model lineage, including a reply made
after an unavailable or diagnostic constructor attempt.

Changing or withdrawing a dependency invalidates downstream support through its
exact revision/hash reference. Conflicts retain both alternatives and disable
affected support; they do not imply arbitrary conclusions. The pure context
manifest includes required dependency closure and reports unavailable support
explicitly. It does not itself forbid inspecting stale claims. Its exact byte
or character budget includes caller-supplied fixed text; those units are not
model tokens.

The notebook can import mixed version 1/version 2 claims through its trusted
host parameter. It keeps hash-only values hash-only
until an exact attachment is verified. Fresh notebook context refuses stale,
withdrawn, contested, refuted or incomplete support. Withdrawal retains the
solver origin and checks in a new version 2 revision. An operator edit instead
creates a version 1 `owner_premise`, clears checks and preserves the original
solver claim in history. The operator API additionally validates the constructor
bundle and selected accepted outcome before importing solver-origin run claims.
Arbitrary uploaded claims do not establish an executed solver outcome.

The pure format retains byte-bound preflight and existing depth, node,
reference and receipt limits. The integrated runtime pins constructor
implementation identity and carries the additional records in version 3 locks;
ordinary locks retain version 2. See [lock semantics](CONSTRUCTOR-LOCKS.md).
Constructor acceptance never counts as model agreement.
