# Durable epistemic notebooks

`symblic/memory/notebooks.py` adds private, persistent revision history to the existing
[epistemic claim contracts](../../symblic/kernel/epistemic.py). It keeps the distinction
between a premise, a model proposal and a checked derivation when evidence moves
between tasks. Revising or withdrawing a dependency changes its exact reference;
dependent claims then become unavailable until their support is rebuilt.

This module, operator API, Memory tab and local CLI are included in the installed
5 October reform. The [5 October release evidence](evidence/2026-10-05-reform-install.json) records the scoped live checks;
the notebook component tests below remain tests with temporary stores and fakes.

## What the notebook preserves

Each claim has an ID, revision, exact content hash, origin, dependency references
and scoped check receipts. Imports retain the host run's original envelopes.
Operator additions and revisions always create `owner_premise` claims with
`unknown` status and no check receipts. Editing a previously checked conclusion
therefore does not preserve its earlier derivation attestation.

The notebook calls the existing `symblic.kernel.epistemic.evaluate` rules. An admissible
premise is available **as a premise**; a checked derivation remains conditional
on its recorded roots. Schema acceptance, operator agreement, an exact hash and a
valid proof do not establish the empirical truth of those roots. Hashes bind
recorded content; they are not signatures against someone able to rewrite the
private store.

Dependencies name exact revisions and hashes. Revising a premise makes an old
dependent reference stale, including when the new text happens to be identical.
Withdrawing creates a retained revision marked withdrawn. Neither operation
silently deletes descendants or asserts that their conclusions are false.

Disagreements retain at least two exact current claim references. An active
disagreement blocks their use as support and therefore blocks affected
descendants. Revising or withdrawing a participant archives that disagreement
with its original references; it does not silently move the objection to a new
statement. An operator may also explicitly close a disagreement with a recorded
reason. Closing it does not certify either alternative as true. These records
do not implement unrestricted paraconsistent theorem proving.

## Pure host interface

The module starts no store, worker, provider or effect on import. The caller
chooses and authenticates access to a private directory. API clients must not
provide `trusted_claims`, receipts or invented origins; only the host may import
an existing run registry after validating its source and runtime identity.

```python
create(path, *, title, operation_id, trusted_claims=None, selected_ids=None,
       trusted_values=None, source=None)
view(path)
change(path, command)
context(path, *, selected_ids, budget, prefix='', suffix='', fixed_parts=(),
        unit='characters', expected_head=None)
```

`path` is a directory, not a JSON filename. `create` imports only the selected
IDs and their available dependency closure. An omitted selection imports no
claims; a host UI may offer an explicit “select all” action. The entire supplied
`trusted_claims` list must fit the notebook claim bound, so a host reading a
larger run should select its closure before calling this interface.

Every change requires `operation_id`, `expected_head` and `action`:

| Action | Additional fields | Result |
| --- | --- | --- |
| `add` | `claim_id`, `content`, optional `depends_on` IDs | New operator premise; IDs cannot overwrite an existing claim. |
| `revise` | `claim_id`, `content`, optional `depends_on` IDs | Next revision, operator origin, no retained checks. Omitted dependencies mean an empty new dependency list. |
| `withdraw` | `claim_id` | Next revision marked withdrawn; original history remains. |
| `disagree` | `disagreement_id`, `claim_ids` | Active disagreement pinned to current nonwithdrawn revisions. |
| `resolve` | `disagreement_id`, optional `reason` | Retained closure of an active disagreement. |
| `attach_value` | `claim_id`, `value` | Exact canonical value accepted only against the claim's recorded `content.value_sha256`. |

Unknown fields are refused. A field named `checks` inside operator content is
ordinary content, not a receipt. The same rule applies to content that says
`status: true` or claims to be a proof.

Here is an executable example using a temporary store and no models. The child
is an operator-authored dependent note, not a certified logical inference:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import symblic.memory.notebooks as M

with TemporaryDirectory() as temporary:
    path = Path(temporary) / 'notebook'
    book = M.create(path, title='Project assumptions', operation_id='create-1')
    book = M.change(path, {
        'operation_id': 'add-a', 'expected_head': book['head'],
        'action': 'add', 'claim_id': 'a', 'content': 'The input list is finite.'
    })
    book = M.change(path, {
        'operation_id': 'add-b', 'expected_head': book['head'],
        'action': 'add', 'claim_id': 'b', 'content': 'Plan using assumption a.',
        'depends_on': ['a']
    })
    packet = M.context(path, selected_ids=['b'], budget=20000,
                       prefix='Review this plan.', fixed_parts=['SYSTEM TEXT'],
                       expected_head=book['head'])
    assert packet['closure_ids'] == ['a', 'b']
    book = M.change(path, {
        'operation_id': 'revise-a', 'expected_head': book['head'],
        'action': 'revise', 'claim_id': 'a', 'content': 'The input may be infinite.'
    })
    assert not book['assessments']['b']['admissible']
    assert len(book['history']) == 3
```

`create`, `view` and `change` return current `claims`, all retained claim
`history`, current `assessments`, `disagreements.active` and
`disagreements.historical`, exact `head`, `event_count`, source metadata,
current value attachments, and event metadata. Mutation responses also return
`operation_id`, `idempotent` and `operation_head`.

`MemoryError` supplies `code`, `details` and `as_dict()`. A stale new command
returns `conflict`. Retrying an identical previously committed command returns
the current snapshot and that operation's original head, without appending an
event. Reusing its operation ID with different fields returns
`idempotency_conflict`. After a genuine conflict, inspect the new head and use a
new operation ID for the intended revised command.

## Fresh context and materialized values

`context` exports only selected claims and their complete recorded dependency
closure. Unselected notebook content is not rendered into the prompt. It
refuses missing dependencies, stale derivations, withdrawn, contested or refuted
support, and explicit bounded-lineage summaries. Incomplete imports remain
inspectable in `view`; being retained does not make them usable as complete
support.

The returned manifest includes exact IDs, revisions and hashes, the rendered
prompt and its hash, and the hashes of every declared fixed prompt part. All
selected dependencies are required. If they and the fixed overhead exceed the
budget, export fails explicitly instead of dropping a required premise.
Budgets measure Unicode code points (`characters`) or encoded UTF-8 bytes
(`utf8_bytes`), not model tokens. Prefix, suffix, value-availability metadata,
attached values and `fixed_parts` are charged. A receiving application must
declare its own system text, schema and other wrapper text before relying on
this budget; arbitrary later additions are outside it.

Many native run claims store only `content.value_sha256`. The notebook does not
reconstruct a value from that hash or turn a display string into an exact
value. These claims report `value_availability: hash_only`. They can be exported
as explicitly scoped provenance records, but the packet reports
`all_referenced_values_available: false`. It is not a complete input-value
packet for executing the next task.

A host may attach an existing canonical output or the operator may submit an exact
canonical value through `attach_value`. Both paths require its
`symblic.kernel.epistemic.digest(value)` to equal the recorded hash. This checks
identity, not truth or authenticity. An attachment belongs to one exact claim
revision; a later revision is not automatically given the old attachment.
Historical attachments remain in the retained event ledger, while `view.values`
and a context packet expose only attachments for current revisions. Rational
values use the runtime's canonical JSON representation; floats are not accepted
as exact notebook values.

## Persistence, limits and verification

`notebook.json` contains one canonical bounded document with retained events and
claim revisions. `notebook.lock` serializes access using `flock`. Each mutation
checks the expected head under the exclusive lock, validates the entire proposed
transaction, fsyncs a private temporary file, atomically replaces the document,
then fsyncs the directory. The document is rewritten at each commit; “append
only” describes retained logical history, not an unbounded append-only file.

An error before replacement preserves the prior document. If directory sync
fails after replacement, the operation returns `durability_uncertain`: reread or
retry the same operation ID. Torn, noncanonical or inconsistent files are
refused without overwriting them. The module does not attempt automatic repair
of corrupted storage. It requires a user-owned private directory and private
regular store files, rejects final-component symlinks and hard-linked files,
and assumes the trusted host controls the parent path.

| Bound | Limit |
| --- | ---: |
| Canonical notebook file | 8 MiB |
| Retained events | 2,048 |
| Retained claim revisions | 4,096 |
| Current claims | 1,024 |
| Direct dependencies per claim | 64 |
| Aggregate conditional-root references | 32,768 |
| Ledger JSON traversal | 500,000 nodes; 40 nested traversal frames |
| One claim | Existing epistemic bounds, including 262,144 encoded bytes and depth 24 |
| Lock acquisition wait | 5 seconds |

Limits cause explicit refusal without deleting history. Listing notebooks should
use directory metadata and defer full replay and support assessment until one is
opened. There is no cheap authenticated summary index in this implementation.

The focused tests use only temporary files and fake failures. They cover
dependency revision and withdrawal, active and historical disagreements,
receipt-clearing operator edits, fresh selected contexts and exact budget
boundaries, missing lineage, value hashes, independent processes competing on
one head, concurrent duplicate retries, torn files, private-path checks, failed
replacement, post-replacement uncertainty and resource bounds. They establish
the checked behaviors of this implementation, not universal epistemic accuracy
or formal soundness of every host adapter.
