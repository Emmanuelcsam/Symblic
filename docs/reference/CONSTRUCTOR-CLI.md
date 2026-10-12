# Optional constructor from the native CLI

The language CLI is `tools/symblic`; its normal commands and default model
construction are unchanged. `tools/symblic run --help` lists the optional controls.
Enabling a constructor requires the separately [provisioned host runtime](CONSTRUCTOR-PROVISIONING.md).

```sh
tools/symblic run docs/symblic/examples/constructor.sym \
  --constructor linear --dir /tmp/my-symblic-construction \
  --by ollama:llama3.2:1b --max-calls 2 --agent-json
```

The example defines its own arithmetic contract. This is a usage example, not a
measured model or solver result. Choose a new private run folder and an admitted
applicator available on the host. Model fallback uses the existing registered
provider path and its ordinary call budget; the constructor has separate limits.
No solver executable, runtime path or configuration file can be supplied through
these flags. The trusted host owns the fixed pinned runtime configuration.

| Mode | Behavior |
| --- | --- |
| omitted or `off` | Original CLI options and behavior. |
| `linear` | Try the bounded linear constructor on supported asks; every adopted candidate must pass the original native checks. |
| `linear_diagnose` | Record the checked constructor outcome, then leave answer construction to the ordinary model path; candidate values are not added to the model context. |

Enabled modes require `--dir`. They explicitly set host `determine=false` and
`solve=off`; they do not replace the language's native solve modes. Original
per-ask settings, route restrictions and unsupported-fragment refusals remain
visible. A constructor not-attempted or unsupported result does not prove the
ask false. One accepted witness does not establish uniqueness or empirical truth.
The report retains `solver_proposal` lineage separately from model agreement.

Limits are exact positive decimal integers, checked against native host policy
before any run-folder write:

| Flag | Default | Maximum |
| --- | ---: | ---: |
| `--constructor-attempts` | 16 | 64 |
| `--constructor-milliseconds` | 80000 | 320000 |
| `--constructor-attempt-ms` | 5000 | 5000 |
| `--constructor-resource-limit` | 100000 | 1000000 |

Total milliseconds must accommodate one per-attempt allowance. The work limit
is a configured Z3 allocation, not a claim about an exact measured global hard
cap. Limits require an enabled constructor mode; supplying limits alone or with
`off` refuses rather than dropping them. These flags apply only to `run`, not
`check`, `preview`, or `replay`.

For a constructor folder, repeating the exact original run command retains the
source, inputs and normalized options and reuses recorded outcomes. A changed
source, input, policy, kernel, malformed record or unknown outcome refuses without
overwriting its original source or metadata. Constructor resume preflight reads
regular bounded files only: source up to four times the language's character
ceiling in UTF-8 bytes, metadata up to 16 MiB, kernel record up to 64 KiB, and the
existing constructor configuration/journal limits. Other ordinary CLI folders
keep their earlier behavior.

```sh
tools/symblic replay /tmp/my-symblic-construction --agent-json
```

Replay uses saved policy and exact records; it does not accept constructor
flags, look up a solver installation, or dispatch a solver. Inspect the returned
status and provenance, not only numeric equality. `--agent-json` keeps the report
on stdout and native progress on stderr; invalid constructor policy returns a
structured failed result and nonzero exit. Unrecognized arguments retain the
CLI's ordinary argparse error convention.

## Parent-to-child native handoff

The prompt states the intended task; the declared type and anchored `ensure`
predicates define acceptance. Keep source, inputs, policy and run records together.
For the checked-in example, this recipe permits no model fallback:

```sh
tools/symblic check docs/symblic/examples/constructor.sym --agent-json
symblic_record="$(mktemp -d /tmp/symblic-constructor.XXXXXX)"
tools/symblic run docs/symblic/examples/constructor.sym \
  --constructor linear --dir "$symblic_record" \
  --by ollama:llama3.2:1b --max-calls 0 --agent-json > constructor-result.json
python3 - <<'PYTHON'
import json
from pathlib import Path
report = json.loads(Path('constructor-result.json').read_text())
assert report['status'] == 'done', report.get('error')
assert report['calls'] == 0
assert report['determinism_summary']['answered_by_constructor'] == 1
assert report['outputs'][-1]['canonical'] == 22
PYTHON
tools/symblic lock "$symblic_record"
tools/symblic lock replay "$symblic_record/run.lock.json"
```

The native lock command has no `--agent-json` flag. Machine hosts may use
`symblic.kernel.lockfile.load_lock` and `symblic.kernel.lockfile.replay`, retaining the returned match
fields. Replay requires compatible source/semantic implementation and the exact
records; it reads no solver installation and performs no new construction.

Unsupported constraints or an unavailable runtime can use an authorized model
fallback when the model-call budget permits. With the zero-call budget above,
that path fails visibly before a provider call. A successful model fallback has
model lineage and must not be described as constructor success. Unknown launch
or unconfirmed cleanup blocks fallback. Missing constructor records with retained
attempt evidence require explicit recovery; deleting all host evidence is not
a way to obtain authenticated fresh history.

This is a native source workflow. Existing `delegate` task schemas retain their
exact compiled policies and do not accept injected constructor options. Use their
normal [delegation contracts](AGENT-DELEGATION.md) for a delegated model task.

## Recovery inspection after lost context

```sh
tools/symblic constructor inspect RUN_FOLDER --agent-json
```

Prints one compact JSON object (sorted keys) and writes nothing. It reads a
fixed list of paths in RUN_FOLDER: `program.sym`, `meta.json`, `kernel.json`,
`state.json`, `trace.jsonl`, the constructor configuration and journal, and
the eight `constructor-events.torn-<0..7>.bin` slots. For the journal lock,
`calls.jsonl` and `run.lock.json` it checks presence only. It never lists the
folder, follows a symlink, opens a FIFO, takes or creates the journal lock,
imports a solver, or starts a model or worker. Each file has a byte bound
(source 4 × the character ceiling, history and metadata 16 MiB, configuration
64 KiB, journal 8 MiB, slots 256 KiB). An oversized, duplicate-key,
non-finite, non-regular or unreadable record becomes a reason code. The only
process started is the existing `node --version` probe inside `kernel_id()`.

`classification` is the first of these that holds:

| Classification | Meaning |
| --- | --- |
| `folder_absent`, `folder_unsafe` | Nothing was read (exit 1). `inspection_failed` (exit 1, last in order) means the inspector itself stopped: no evidence either way. |
| `snapshot_inconsistent` | A path changed during the read (lstat before and after). Inspect again; do not act on it. |
| `records_damaged` | Malformed, unsafe or contradictory records (source, inputs or mode differ from the journal pins). |
| `journal_torn` | The journal ends inside a row. `journal.torn.torn_sha256` is what the operator confirms in `repair_torn_tail`. |
| `repair_unfinished` | A quarantine slot holds bytes that no repair row records (an interrupted repair). |
| `attempt_blocked` | A worker was not confirmed reaped. |
| `attempt_uncertain` | An announced attempt has no recorded end. It may have run. |
| `records_incomplete` | Only one of the configuration and the journal exists. |
| `history_unknowable` | Records are missing, but a lock, a slot, activity, a constructor breadcrumb, or a snapshot without the supported marker remains, or unreadable history cannot rule out work. |
| `attempts_settled` | Valid records; every attempt has an end. |
| `no_attempt_recorded` | Valid records with no announced attempt. |
| `no_constructor_history` | No records, byproducts or retained constructor activity. This is absence of evidence: a folder whose artifacts were all deleted looks the same. |

Other fields:
- `reasons`: every condition seen.
- `mode`: the mode from `meta.json`, configuration and journal pins.
- `kernel`: the current and recorded identities, and `compatibility` (`same`, `changed`, `unreadable` or `unknown`).
- `journal`: pins, `charged` and `remaining` allowance, phase per attempt, and the last row hash.
- `records`: the sha256 and byte count of each file read.
- `history`: the `state.json` status and marker.
- `native_gate`: the verdict of the native missing-record gate.
- `next_steps`: each step names the authority it needs (`agent`, `owner` or `none`).

Only `constructor_bridge: 2` (an exact integer) counts as a checkpointed
snapshot. A missing, boolean, float, text or other-number marker on an
unfinished enabled run counts as ambiguous. Exit 0 means a report was
produced, whatever its classification. A usage error exits 2 with the
ordinary argparse message.

`authorizes_retry` is always `false`. The report is a snapshot of files
another process may be writing, not authenticated host state. It does not make
an uncertain dispatch safe to retry. Only the operator reconciles, repairs or
deletes.

Parent-to-child template. The parent pastes its own inspection into the task;
the child re-inspects and stops if anything differs:

```text
Constructor run folder: RUN_FOLDER
Parent inspection (classification, journal.records sha256, last_row_sha256):
  CLASSIFICATION / JOURNAL_SHA256 / LAST_ROW_SHA256
1. Run: tools/symblic constructor inspect RUN_FOLDER --agent-json > inspect.json
2. If classification, records.journal.sha256 or journal.last_row_sha256 differ
   from the parent's, or snapshot.consistent is false: stop and report both.
3. Act only on next_steps whose authority is "agent". For "owner" or "none",
   report the step to the parent; never retry, reconcile, repair or delete.
4. To continue an attempts_settled run, repeat the parent's exact original run
   command (same source, inputs, options, --dir). Otherwise start a new run in
   a NEW folder.
```
