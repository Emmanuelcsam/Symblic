# Documentation conformance inventory

`tools/scripts/symblic_docs_audit.py` inventories the documentation tree and checks an
explicit finite manifest of examples. An inventory is a coverage record. A
successful case is evidence about that exact fence, source hash and native
runtime; unknown examples remain unassessed.

Use the system Python, which already supplies `markdown-it-py==3.0.0`:

```sh
python3 tools/scripts/symblic_docs_audit.py inventory --root docs/reference --output /tmp/symblic-docs-inventory.json
python3 tools/scripts/symblic_docs_audit.py verify --root docs/reference --inventory /tmp/symblic-docs-inventory.json
python3 tools/scripts/symblic_docs_audit.py check --root docs/reference --manifest docs/reference/documentation-cases.json --runtime-root . --output /tmp/symblic-docs-checks.json
```

Output files are created exclusively. Choose a new destination for another run.
`verify` returns a nonzero exit code on changed, added or removed files, changed
fence maps, or a modified inventory. The manifest is reviewed data; the tool
never promotes a fence to an execution case automatically.

Every regular file is listed and hashed. UTF-8 text without NUL bytes is parsed
with the CommonMark preset; binary files remain explicit exclusions. Fences
retain their language, complete info string, line range, closing status, raw
content SHA-256 and normalized parser-content SHA-256. These two hashes differ
for CRLF lines or container indentation. Every run of three or more backticks
or tildes is also indexed, including literal markers inside a larger fence and
inline mentions outside one. Unrecognized delimiter candidates stay visible for
review. Nesting is bounded to 64 containers; file count, bytes, lines, fences and
delimiter counts are capped, with refusal rather than silent truncation.

Language tags give only conservative classifications. Shell blocks are never
run; `text`/`markdown` blocks are prose; `pseudocode` blocks are proposals.
Unclosed and uncontracted examples require review. The conformance receipt joins
declared executable or expected-failure cases to inventory fence IDs. Other
Python, JavaScript and Symblic blocks acquire no passing status from their tag.

Each manifest case identifies one fence and its exact raw content hash, an
`execute` or static `check` action, expected status and expected native error
kind. All pins validate before the first worker starts. `check` uses the native
static checker. `execute` permits only the small reviewed statement/expression
and builtin sets named in the script. Imports, model asks, effects, delegation,
dynamic evaluation, JavaScript execution, routines and retry actions are
refused before native execution.

Every case receives a fresh temporary working directory and native Python
process (the checkout's `.venv/bin/python` when present, otherwise the invoking
Python), with one CPU affinity, a 768 MiB address-space ceiling, a 15-second CPU
ceiling and a 20-second wall deadline. Native execution has a 20,000-step budget,
zero model calls, constructor/determination/solve disabled, rejecting applicator
and effect hosts, and no run folder. Socket connections and child-process launch
are refused during checking. Temporary artifacts cause failure. The receipt
retains native source identities, kernel identity, actual check count, exact
output canonical forms and explicit failure status.

This checks documentation examples against the current implementation. It does
not prove all prose claims, adequate operator-intent predicates, empirical truth,
arbitrary code safety, or cross-runtime equivalence. In particular, a deliberately
weak-contract example may execute successfully while its documented caveat
remains the point of the example.
