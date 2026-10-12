# Source witnesses in ordinary Symblic

The bounded source adapter checks exact relationships to retained source text.
The model proposes the spans or item selection; the caller supplies the source
and acceptance contract separately. These checks do not establish source truth,
general semantic entailment, or the adequacy of the caller's requirements.
The adapter and text-library integration are included in the installed 5 October
reform; see the [5 October release evidence](evidence/2026-10-05-reform-install.json). Fake-constructor tests remain
component evidence, not a live model benchmark.

All functions are lazy first-party builtins. They take ordinary records and
lists, use the existing kernel budget, and open no store or provider. Source
identity includes its ID, positive revision, exact text, and SHA-256. Spans use
zero-based Unicode code-point offsets with an exclusive end, not JavaScript
UTF-16 positions or byte offsets. No case folding, Unicode normalization,
currency interpretation, or unit guessing is implicit.

## Caller-held contracts

```symblic
let source = source_record("invoice", "Invoice total: 120 dollars. Number of items: 3.").
let contract = source_field_contract("total", source, ["Invoice total"],
    source_span(source, 0, len(source.text)), ". ", ": ", " dollars", unit="dollars").
let candidate = {contract_sha256: contract.sha256,
    label: source_span(source, 0, 13), value: source_span(source, 15, 18)}.
let receipt = verify_source_field(source, contract, candidate).
assert receipt.accepted and receipt.value.numerator = "120".
assert receipt.assurance.source_truth = "not_established".
```

The field contract specifies exact aliases, region, separator, prefix, suffix,
and optional unit/currency literals or entity witness. Exactly one label must
occur in the region. The entire separated field must match the declared
label/prefix/signed-decimal/suffix template. Repeated labels, a number from the
wrong clause, a changed sign or unit, negation, and unsupported qualifications
refuse. In the installed grounding rules 4, a prefix, suffix, separator or region
boundary inside a written number refuses as `ambiguous_number_boundary`.
For example, a comma cannot truncate `1,200` to `1`, and a prefix cannot strip
the sign from `-5` or select `20` from `120`. The boundary recognizer includes
decimal/grouping marks, fraction/product operators, exponents and powers; a
suffix cannot turn `3/4` into `3` or `10²` into `10`. This does not add those forms to the
accepted signed-decimal grammar. ASCII spaces separate numeric tokens, so the
caller must resolve layouts such as `1 200` explicitly.

Unsupported layouts remain available for uncertain language work or
a separately defined acceptance procedure; the checker does not pretend to
understand them. The returned number is derived from the verified source span
as decimal text plus exact numerator and denominator strings.

`verify_source_field(source, contract, candidate)` receives the authoritative
contract separately. Candidates have only `contract_sha256`, `label`, and
`value`. A changed contract hash or an embedded replacement contract is rejected.
A digest is an integrity identifier, not proof of authority: the calling program
must supply the source and contract it intends to trust. Feeding a model-created
contract into the caller argument does not make it operator-authored.

## Summary and enumeration coverage

`source_summary_contract(id, source, required, joiner="\n…\n", max_spans=64)`
takes named required spans: `[{id: "exception", span: witness}, ...]`.
`verify_source_summary(source, contract, candidate)` expects
`{contract_sha256, spans, text}`. Selected spans must be nonempty, disjoint and
in source order. The installed rules also require whole-word/whole-number boundaries
unless the caller explicitly declared that exact required boundary. Selecting
`safe` from `unsafe` therefore refuses. Numeric span checks reuse the kernel's
`quotes()` boundary rules, including grouped digits, scientific notation and
signs. Source offsets stay exact; repeated whitespace is collapsed only for
boundary analysis. Intra-word apostrophes and hyphens receive additional checks,
so these witness rules can be stricter than `quotes()`. `text` must equal their exact concatenation using the declared
joiner. Every required span must be covered. A known exception omitted from the
selection fails even if the result is short and every remaining word is quoted.
Undeclared qualifications and semantic sufficiency remain unresolved.

`source_list_contract(id, source, require_nonempty=false)` accepts an optional
`catalog=` argument containing a finite catalog of named spans. Omit that
argument when the universe of items is unknown.
`verify_source_items(source, contract, candidate)` expects
`{contract_sha256, items: [{id, span}, ...]}`. Returned IDs/spans must be distinct.
With a catalog, every declared item must be present with its exact witness and
no undeclared item may appear. An empty answer fails a nonempty catalog or a
`require_nonempty` obligation. Without a catalog, supported returned items do
not establish completeness: `enumeration_complete` is `"unknown"`, including
for an empty list. The installed rules reject overlapping item spans and partial
tokens without a caller-held catalog; an exact catalog retains its declared
boundaries. For example, selecting `lead` from `lead-free` refuses without a
catalog. Selecting the separate parts of `copper-nickel` requires an explicit
catalog declaring those boundaries; the complete compound remains available
without that catalog. An explicitly empty catalog differs from an unknown one.

Free-form paraphrases use `source_proposed_summary(source, text, links)` if a
record with checked citation spans is useful. The result remains a
`model_proposal` with `status="unknown"`; exact citation links do not validate
the paraphrase's claims.

## Model construction in the existing text library

The following additive routines accept caller-held `(source, contract)` and
return the full checked receipt:

- `text.witnessed_number_in`: the model constructs label and value witnesses.
- `text.witnessed_summary_of`: the model selects exact summary spans.
- `text.witnessed_items_in`: the model proposes the required item witnesses.

Import with `import text as text_ops.` and call, for example,
`text_ops.witnessed_number_in(source, contract)`. Configure an applicator and
budget through existing `use`/run options. The source and contract are required
context; overflow fails before a call. Candidates use strict record coercion
in every execution profile, so extra candidate-supplied authority fields cannot
be silently discarded. Failed witness checks enter the existing bounded retry
path. The host records model proposal lineage; the returned receipt proves only
the encoded source relationship and declared coverage.

Existing `number_in`, `quoted_number_in`, `items_in`, `summary_of`, and other
text routines retain their APIs and behavior in legacy and verified profiles.
Their existing checks are limited: quote occurrence cannot validate a referent,
and a word limit cannot validate a summary. The new routines are an explicit
choice, not an automatic restriction or a silent upgrade to stronger semantics.
Dimensioned source data can be mapped into the separate
[quantity API](QUANTITIES.md) only using caller-declared units and uncertainty.
