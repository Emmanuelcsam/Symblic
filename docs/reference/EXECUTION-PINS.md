# Execution pins (receipt version 2)

An optional execution receipt binds a reviewed program to exact source text,
finite JSON input values, the semantic kernel ID, an explicit first-party file
registry, captured standard-library source, and the normalized contracts of
capabilities named by the program. It detects incompatible changes before any
statement runs. It does not prove the program expresses the operator's intent.

```python
import symblic.kernel.execution_pins as X
from symblic.kernel.run import Run

pins = X.build(source, inputs, reviewed_module_hashes, capabilities=catalogue)
report = Run(source, inputs, applicators,
             {"execution_pins": pins, "effects": host}).execute()
```

`reviewed_module_hashes` maps approved repository-relative filenames to their
SHA-256 hashes at review time. The fixed registries in
[`symblic/kernel/execution_pins.py`](../../symblic/kernel/execution_pins.py) define accepted dependencies:
this revision registers **43 Python files, 35 required and 8 optional**, plus
10 capturable `.sym` libraries. Unknown paths and missing required files refuse.
`build` verifies the reviewed hashes against current bytes and the process's
initial snapshot before returning a receipt.

Required files include the exact arithmetic/transport adapters, proof checkers
and adapter, execution profiles, epistemic and source-witness checks, quantities,
proof sessions, **`symblic/adapters/proof_command.py`**, **`symblic/authoring/helpers.py`**, delegation and task-card helpers,
the JS declaration checker, and **`symblic/kernel/identity.py`**. The semantic kernel ID
also records adapter versions, capsule and epistemic runtime versions, Unicode,
and module-logic semantics; see [`kernel_id()`](../../symblic/kernel/language.py).

The eight optional files are `symblic/providers/ollama_call.py`, `symblic/providers/applicators.py`,
`symblic/intent/records.py`, `symblic/spec/sheets.py`, and `host_executor_host.py`, `host_executor_plan.py`,
`host_executor_routing.py`, `host_executor_run.py`. Optional means they need not appear in
every reviewed hash map. A selected optional file must match its reviewed hash;
a loaded registered file is audited even if omitted from that map. Pure runs can
use a deployment without the optional provider helper. This finite registry does
not claim to pin every host integration or Python dependency.

`validate(pins, source, inputs)` returns a detached validated receipt or raises
`SYM_VERSION`. The runner invokes `prepare(run)` before parsing or evaluating its
first statement when `execution_pins` is supplied. A malformed receipt, changed
source/input, incompatible loaded code, changed pinned file, missing library
snapshot, or changed capability contract fails before a model or effect call.
Without that optional field, this receipt gate is not applied.

**Version-1 execution receipts refuse under version 2.** They are not silently
upgraded: review the coherent new source set and build a new receipt in a fresh
worker. The execution-receipt version is separate from the language and canonical
versions; changing the receipt format does not itself redefine program arithmetic.

## Loaded source identity

[`symblic/kernel/identity.py`](../../symblic/kernel/identity.py) records the actual importing
module frame and its globals. Each registered module's early marker compares its
executing module code object with a fresh compilation of the exact bounded source
bytes, before first-party dependency imports. The helper records its own frame.
This catches an already-loaded old helper even if the file is replaced before the
kernel's initial snapshot; matching the newer disk hash alone is insufficient.

The kernel captures the registered Python and runtime-asset files once at its
initial import boundary. Pin construction and validation audit the registered
copies currently in `sys.modules`, including aliases and `__main__`, against that
snapshot and current disk bytes. Unmarked globals, copied or changed markers,
stale executing bytecode, or a copy from another installation refuse. Initial
capture problems stay recorded; loading the helper later cannot retroactively
certify an older unmarked process. Validation audits again after `kernel_id()`
may have loaded further adapters. Fresh imports in either kernel/helper order
are supported.

The existing cache check remains: a Python cache the interpreter could accept
must agree with freshly compiled source, including same-size timestamp collisions
and unchecked hash caches. Runtime assets are also compared with the initial
snapshot. A pinned worker therefore needs one coherent deployment; replacing
files requires a fresh worker and reviewed pins.

`symblic/providers/ollama_call.py` has a controller-only marker. Its standalone
`python -I -S observer.py` form stays stdlib-only and does not import the identity
helper. A controller import records identity when that helper is present. An
older unmarked controller import cannot later qualify for pinned execution.
This preserves the standalone observer's packaging without exempting loaded
controller copies from the audit. Its provider-manifest observations are separate
from execution pins and do not attest model weights.

Import identity is bounded to 8 MB per source, 64 MB of aggregate source bytes
admitted to its compilation cache, 256 records/compiled entries, and at most
256 registered files. Audits inspect at
most 32,768 loaded module entries and read at most 64 MB of source. Exceeding these
bounds refuses pinned execution. These are local source compatibility checks
under a trusted interpreter/host, not signatures, package authentication, a code
sandbox, or protection against malicious in-process mutation, custom importers
that misrepresent execution, or filesystem races. They do not prove semantic
correctness or authenticate a model's loaded weights.

## Libraries, capabilities and inputs

Standard-library files supplied in the reviewed hash map are stored as source
snapshots. Imports use those snapshots, including during resume; changed live
`.sym` files and old `modules.json` entries cannot substitute other source.
Saved-program imports and unlisted libraries refuse. This finite registry
currently contains constants, dates, graphs, kinship, lab, stats, text, units,
records, and order. The additive witness routines are included in the captured
`text.sym` source when that library is reviewed.

`capabilities` accepts descriptor rows or a normalized map. The receipt selects
syntactically named `observe`/`act` contracts, including those in captured module
source. Comparison includes the full normalized descriptor, particularly
`instructs`, `egress`, argument schema, effect class, policy, and sensitivity.
Host registries can also contain legacy names outside the effects grammar (for
example, bare `calc`). Those names cannot be used by Symblic and are excluded,
as in the effects catalogue normalizer. Duplicate addressable names still refuse,
even when unrelated to the reviewed program; a legacy entry cannot substitute
for a required capability.
Before live execution the host's metadata is read once, compared, then retained
for the effect interpreter's later metadata lookup. The host still performs
operations through its normal executor. Replay reads only the run's recorded
`effects-catalogue.json`; a missing or mismatched record refuses without consulting
a live host. Capability implementations and external services remain outside this
receipt's code registry.

Input identity uses exact UTF-8 text and sorted, compact finite JSON. JSON booleans,
integers, floating-point numbers, nulls, arrays, and objects remain distinct in
the receipt; no text normalization or numeric coercion occurs. Python-only values,
non-string object keys, nonfinite numbers, and oversized structures refuse. Limits
are 8 MB encoded JSON, 100,000 visited values/keys, nesting depth 64, and the
kernel's bounded source and integer sizes. Nested input data is detached before
execution.

Receipt hashes detect damage and drift; they are not signatures or authorization.
An authorized operator can construct another program and another receipt. External
events, model replies, truth of assertions, and the adequacy of an encoded
specification remain separate questions. The API/the host executor integration must pass
and persist the optional field explicitly; installing this helper alone does
not make every native run pinned.
