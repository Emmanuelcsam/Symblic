# Constructor records and portable locks

The constructor bridge and journal-v3 reader preserve accepted values and their
provenance in portable locks. Replaying a lock does not need a solver installed.

An ordinary finished run still produces the existing version 2 lock, with the
same fields and bytes under the same recorded timestamp. Merely saving an unused
constructor configuration does not change that format. Existing version 2 locks
remain readable and can be replayed under their original semantic kernel.

A finished run with `constructor-events.jsonl` instead produces a version 3
lock. Its additional `constructor` bundle contains:

- The exact canonical ASCII `constructor-config.json` text and SHA-256.
- The exact ASCII journal text and SHA-256, validated by the journal's strict
  reader. No malformed or torn row is skipped.
- The complete recorded epistemic registry, including claim versions, origins,
  dependency references, receipt IDs and recorded assessments.
- Final binding names, lines and value hashes with their exact epistemic records.

The journal's opening pins must agree with source, input, kernel, configuration,
implementation and worker identities. Input hashing uses the existing
`symblic.kernel.evidence.digest(inputs)` on the run's JSON inputs. It does not apply a
second canonical-value conversion. Configuration hashing uses
`SHA256(journal.canonical(config).encode('ascii'))`; the implementation-map hash
uses the same encoding. These encodings are deliberately distinct from native
value hashes and the journal's domain-separated candidate hashes.

Every solver claim must identify an accepted selected outcome, its native
validation record and exact value. The binding fingerprint must agree with the
claim's canonical value hash. The recorded lifecycle must confirm dispatch,
reaping, complete capture and integer exit code zero; request time/work/memory
limits must match their recorded counterparts and stay within the intent's
reservation. Complete `accepted`, `diagnosed` and `no_candidate` receipts also
bind the protocol-3 effective OS limits, allocated per-check Z3 work budgets and
private library path. This validates recorded settings; it does not measure an
OS limit's enforcement or turn a solver's UNSAT report into a native proof. The
fixed current worker profile uses 256 MiB address space.
Hashes preserve recorded relationships; they do not authenticate a malicious
host or establish empirical truth.

Unknown or unreaped attempts refuse export. Repaired journals currently also
refuse version 3 export because their retained quarantine files are not yet
packaged. The original run and repair evidence stay intact; the lock does not
pretend the repaired stream alone is a portable complete record. Export checks
all eight fixed quarantine paths even when an interruption prevented the repair
audit row from being appended. It also checks a retained journal lock and the
shared bounded state/trace history when the primary journal is missing. An
accepted solver claim, diagnostic/fallback receipt or activity checkpoint cannot
silently lose its constructor history by becoming a version 2 lock. An unused
configuration alone, without retained activity, preserves ordinary lock parity.
See the [recovery amendment](evidence/2026-10-05-constructor-recovery-controls.json).

Replay reconstructs the exact records in a fresh private folder and sets the
native `replay=True` and `side_effects=False` options. Its applicator refuses
uncached model calls and external effects. Runtime paths inside configuration
are historical pins, not execution authorization. Record validation does not
open solver packages or executables. The integrated constructor
bridge uses journal replay and dispatches no solver in this mode.

Version 3 success requires the original fingerprint and existing evidence checks
plus an exact match of the epistemic registry, selected binding provenance and
restored constructor records. It does not normalize away originating outcome
hashes, solver origins, receipt identities or replay flags inside those records.
The result adds `constructor_match`; version 2 result fields stay unchanged.
`drift()` separately retains value-match counts and reports whether constructor
provenance matched. Equal values with different origins/outcomes are not reported
as the same version 3 run.

## Shared configuration API

`symblic.constructor.records` provides `validate_config`, `config_hash`,
`implementation_hash`, `parse_config`, `read_config`, `save_config`,
`read_journal`, `validate_journal`, `bind_journal`, `validate_worker_evidence`,
and `validate_solver_claim`.
Validation is pure. File helpers use only a caller-selected run folder; imports
are inert. Refusals are `RecordsError` with a short `code` and `details`.

`validate_worker_evidence(outcome, request, config=None)` is the common boundary
for fresh commit, replay adoption and portable export. It returns `True` for the
three validated full-reply dispositions and `False` for structurally valid
partial dispositions such as timeout. `False` never claims complete capture.
Supplying configuration additionally binds its mode, limits and exact private
import root; null runtime cannot support a full worker reply. Native candidate
checking and selected claim validation remain separate required steps.

The exact configuration fields are `version: 1`, `mode` (`linear` or
`linear_diagnose`), `selection_policy: "canonical_min_v1"`, `limits`, `runtime`
and `implementation`. All limits are exact positive integers:

| Limit | Default | Maximum |
| --- | ---: | ---: |
| `attempts` | 16 | 64 |
| `milliseconds` | 80000 | 320000 |
| `attempt_ms` | 5000 | 5000 |
| `resource_limit` | 100000 | 1000000 |

The total milliseconds must accommodate at least one declared attempt. Actual
elapsed cost and solver counters remain separate evidence; these configured
ceilings do not claim a measured work counter is a perfect hard cap.

`runtime` is null or the pinned helper runtime object with exactly `python`,
`python_sha256`, `worker_sha256`, `z3_version`, `package` and `purelib`. Structural
validation checks path/hash shapes without resolving these paths. Package maps
contain at most 256 entries. `implementation` pins exactly
`symblic/constructor/core.py`, `symblic/constructor/journal.py`,
`symblic/constructor/records.py`, `symblic/linear/constructor.py`,
`symblic/linear/worker.py` and `symblic/linear/resources.py`.

Configuration files are bounded to 64 KiB and must already be canonical ASCII
JSON. Duplicate keys, noncanonical text, floats, symlinks and special files
refuse. Creation publishes a synced private temporary file without overwriting
an existing destination, syncs the directory, and permits only an exact existing
match. A retry confirms the existing file/directory durability. Cleanup failures
cannot replace an original stop or interrupt; secondary failures are annotated.

The whole lock retains its existing 50,000,000-byte load ceiling. Constructor
journals retain their reader's 8 MiB ceiling. The new provenance bundle admits at
most 8192 claims/assessments and 8192 final binding rows within a 16 MiB encoded
budget; each individual record is subject to the epistemic JSON bounds. Excess
or incomplete provenance refuses export rather than being truncated. These are
portability bounds, not a reduction of native program execution limits.
