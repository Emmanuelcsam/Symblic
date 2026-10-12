# symblic/memory: notebooks that keep claims between runs

**What this package explores.** A Symblic run records *claims*: values it derived, premises it was given, model
proposals it accepted after checks (see `symblic/kernel/epistemic.py`). This package asks whether those claims
can be kept *between* runs without losing track of where they came from: a later task should receive exactly the
support it depends on, and should be refused when that support was withdrawn, contested or has gone stale.

**Status: prototype.** The storage rules are tested (28 unit tests with temporary directories, including
concurrent writers and injected write failures). It was used only inside the original host, through the host
API described below, and nothing here measures whether a claim is true: every snapshot says
`"empirical_truth": "not_established"`.

## The module

| Module | What it does |
| --- | --- |
| `notebooks.py` | `create(path, ...)`, `view(path)`, `change(path, command)` and `context(path, ...)` over one notebook directory. |

A notebook is one private directory (mode `0700`) holding `notebook.json`, an append-only, hash-chained list of
events, and a lock file:

```
create ──► event 1: imported claims (with their original origins and check receipts) + attached values
change ──► add / revise / withdraw a claim, open / resolve a disagreement, attach a value  (one event each)
view   ──► replays every event, re-checks every hash, returns current claims + their assessments
context──► selected claims + their full dependency closure, packed into a bounded text budget
```

Rules worth knowing before you use it:

- **Compare-and-swap with idempotent retries.** Every change names the head hash it expects
  (`expected_head`) and an `operation_id`. A stale head is refused with code `conflict`; repeating the same
  operation returns the recorded result; reusing an operation ID for a different command is refused.
- **Imported claims keep their provenance; later edits cannot invent any.** Only `create(trusted_claims=...)`
  imports claims that carry origins and check receipts. Claims added with `change` are always premises stated
  by the notebook's user (origin `owner_premise` in the kernel's vocabulary) and cannot carry receipts.
- **Context refuses weak support.** `context()` fails with `unavailable_support` if any claim in the
  selected closure is withdrawn, contested, refuted, stale, or a summary with incomplete lineage.
- **Integrity, not authentication.** The hashes detect damage and replay errors. Anyone who can write the
  directory can rewrite it; the caller decides who may call these functions.

## Outside this package

- `integration/host/symblic_memory_api.py` is the original host's HTTP and command-line front end. It imports
  claims from the host's finished run folders (checking the kernel identity, execution pins and, for solver
  proposals, the constructor journal from `symblic/constructor/records.py`). It needs the host's run store, so it
  does not run here.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/memory -t .
```

Run from the repository root. Everything happens in temporary directories; no model, network or worker is used.
The host API's tests are in `tests/integration/test_symblic_memory_api.py` and skip without the host.

Further reading: `docs/reference/EPISTEMIC-MEMORY.md`.
