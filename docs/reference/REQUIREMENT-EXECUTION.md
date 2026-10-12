# Observed requirement checks

The Interpreter's saved view has an additive `execution_coverage` field. The
original requirement-to-program map remains a static syntax-presence artifact.
The new field joins that map to the exact linked run of the host executor, without
changing run readiness, starting work, or rewriting any saved artifact.

A join requires the same intent content revision and digest, handoff identity,
source bytes, exact inputs and recorded execution pins. Intent digests and native
receipt digests use their respective existing formats. A current parser/runtime
must still validate the recorded pins; an unavailable historical runtime leaves
the observation unknown rather than weakening its pins.

Only checks retained in a final `done` or `failed` native report count. Their
self-digests, source/kernel identity, predicate AST hash, strict Boolean result,
binding hashes and matching full trace check/status are checked. Where a root
statement is uniquely attributable, its predicate display text must also match
the native renderer. A trace-only check from rolled-back work cannot satisfy a
requirement. A mapped dead branch can therefore remain unobserved even when the
run finishes successfully. A failed run can retain an observed failing check.

The view reports observed pass/fail counts, partially observed mappings,
unobserved locations, and ambiguous attribution separately. Native check receipts
do not identify a column, module, call occurrence or every loop obligation.
Duplicate line/kind/predicate locations and programs with imports remain
ambiguous for this join. A passing observation does not establish that all
possible occurrences ran. Model-proposed predicates retain their origin and do
not become owner-declared requirements merely because a check passed.

Reads are confined to the already-linked run. Regular files and complete JSON
lines are required; symlinks at the run or file boundary, concurrent changes,
missing files, malformed data and exceeded bounds return unknown. Limits are
400,000 source bytes, 8 MB per state/metadata file, 16 MB and 50,000 rows for the
full trace, and 20,000 retained checks. The reader creates no directories and
performs no unit probe. A running or stopped run has no final observation here.

Consistency of owner-controlled stored records is the guarantee. These hashes
do not authenticate external history. Encoded predicate execution does not prove
that the predicate captures the owner's meaning, establish external truth, or
record owner acceptance. The UI labels those limits and preserves the raw JSON
for inspection.

Code: `symblic/intent/requirement_execution.py` (`derive`, `view`; tests:
`tests/intent/test_symblic_requirement_execution.py`), called on the host by `execution_coverage` in
`integration/host/symblic_intent_api.py`, which needs the original host (`integration/host/README.md`; tests:
`tests/integration/test_symblic_intent_api.py`).
