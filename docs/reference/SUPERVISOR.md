# Durable Symblic workflows

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

The **Supervisor** tab in `/symblic.html` runs an operator-defined workflow of exact
native Symblic programs. It adds durable orchestration around the host executor; it does
not change the language meaning of `every` (a quantifier) or invent executable
parser keywords. The host executor and the fleet runner remain the execution, admission, approval
and effect-journal boundaries.

Start with **Load example**, **Save workflow**, then **Run once**. Saving checks
and freezes the programs without executing them. The example starts two exact
calculations independently, joins their successful native results, checks a
bounded operator-state condition and increments a persistent counter. Open each
native run to see its actual result and evidence. **Refresh** reads saved state;
**Advance once** reconciles known child runs and performs ready transitions.
Browser reconnects never create another firing.

## Workflow format

```json
{
  "version": 1,
  "name": "Two calculations, then join",
  "max_parallel": 2,
  "state": {"completed": 0, "ready": true},
  "steps": [
    {"id": "left", "kind": "run", "source": "let x = 2 + 3.\nassert x = 5.\nshow x.\n", "deadline_s": 120},
    {"id": "right", "kind": "run", "source": "let x = 7 * 6.\nassert x = 42.\nshow x.\n", "deadline_s": 120},
    {"id": "joined", "kind": "join", "after": ["left", "right"]},
    {"id": "ready", "kind": "wait", "after": ["joined"], "until": {"state": "ready", "equals": true}, "within_s": 300},
    {"id": "count", "kind": "set", "after": ["ready"], "changes": {"completed": {"increment": 1}}}
  ]
}
```

A definition is immutable after saving. Create a new workflow to change its
programs, input values, dependencies or permission ceilings. State and schedule
edits use the saved revision; stale tabs cannot overwrite newer operator changes.

| Step | Behavior |
| --- | --- |
| `run` | Starts its exact checked native `source`, `inputs` and `options` in the host executor. `deadline_s` defaults to 3600. |
| `join` | Completes when every `after` dependency succeeded. |
| `delay` | Waits at least `seconds`, then completes on a later tick. |
| `wait` | Tests `until` on each tick, completing if true or failing locally after `within_s`. |
| `set` | Atomically updates durable operator state using `{"set": JSON}` or `{"increment": number}`. |

All steps can have `after: [step IDs]` and an immediate `when` precondition.
Conditions are either `{"state":"name","equals":JSON}` (exact JSON comparison)
or `{"step":"id","status":"done"}`; status may be `done`, `failed` or `running`.
A false `when` skips the step. A `wait` rechecks its condition until its bound.
Use explicit `after` dependencies when a precondition needs another step to
finish. The graph has no dependency cycles. Independent run steps can execute
concurrently; `max_parallel` is 1–4. A join is actual observation of successful
child completion, not just successful submission.

The supervisor checks operator state and mechanical native status. Predicates over
tool observations, model answers or physical conditions belong inside the native
Symblic program, before its actions, using its existing assertions and effect
flow checks. The supervisor does not reinterpret a native result string as a
Boolean, trusted state or a new program input. A native program's `done` status
establishes its own encoded checks, not the truth of every real-world premise.

## Failure and compensation

Give a handler step `"on_failure":"step-id"` to run it only after that step's
**definite** failure. A handler can be another native program, including an
operator-authored compensating action. Its own submission and effects get separate
receipts. A dependency failure skips ordinary downstream steps. Successful
compensation does not turn the original failed workflow into a success.

```json
{
  "version": 1,
  "name": "Record an exact failure",
  "steps": [
    {"id":"check","kind":"run","source":"assert 2 + 2 = 5.\n"},
    {"id":"record","kind":"set","on_failure":"check","changes":{"failed":{"set":true}}}
  ]
}
```

A deadline marks a native step **overdue**. It does not kill the child, declare an
external action failed or start compensation. A stopped worker, unreadable
native record or unresolved native effect is **unknown**. Open the native run,
resolve its own uncertain effects, then refresh/advance the workflow. A failed
native run may have completed earlier effects; compensation must account for
those recorded results. The supervisor never automatically resends the original
operation.

Before each submission the journal records its exact identity and execution
pins. If a process dies after this intent but before the native handle is saved,
the step remains unknown. Raw native status and both ordinary/delegation journals
are inspected without repairing or truncating damaged bytes; unreadable, partial
or unfamiliar records cannot authorize compensation. **Reconcile** accepts only a native run matching its
unique prompt marker, source, exact inputs and pins (and explicit applicator), with no broader effective permission ceilings.
A different run cannot be attached to clear uncertainty. If no native handle can
be established, the workflow remains unresolved; inspect the host executor before making
an independent new workflow. There is no “assume it did not happen” retry.

**Pause workflow** prevents further supervisor transitions and disables its
reconciliation pulse. Already running native children keep their own execution
and recovery rules. **Resume workflow** restores the bounded reconciliation
clock. Disable scheduled firings separately if no further recorded triggers are
wanted; a firing while paused is recorded as skipped.

## Real scheduling and event firings

Schedules are native fleet-runner cron triggers, using its configured timezone (an IANA name such as
Europe/Paris), misfire handling, host gate and trigger fire ledger. The
Supervisor's advanced schedule form accepts five fields, for example:

- `0 9 * * *`: daily at 09:00.
- `*/5 * * * *`: every five minutes.
- `0 9 * * 1-5`: weekday mornings.

the fleet runner starts declared `executor.supervise` with the workflow ID. Only the
scheduler-minted trigger/mission/step context can claim a firing. Duplicate
delivery of that identity returns the same recorded firing. If an earlier firing
is unfinished, the new one is recorded as skipped rather than overlapping it.

A separate fleet-runner minute pulse, `executor.supervisor_tick`, reconciles child
runs and bounded waits. Its identity is saved and its trigger installed **before**
any native child is submitted. The pulse disables after completion, pause or an
unresolved/overdue outcome that needs operator attention. Unknown native status with
a known handle is polled only within the original bound. There is no supervisor
worker daemon or independent clock. Minute pulses can run late under scheduler
load or downtime; `seconds` and deadlines are wall-clock timestamps evaluated at a
tick, not promises of subsecond dispatch. System clock adjustments can move the
observed boundary; this is not a monotonic physical timing guarantee. The operator deleting or disabling a pulse
is respected until an explicit resume.

Existing fleet-runner event triggers can be attached in the advanced schedule form.
First configure the actual fleet-runner event watcher/producer and its trigger with an
action shaped as:

```json
{
  "type": "mission.start",
  "kind": "single",
  "spec": {
    "tool": "executor.supervise",
    "args": {"workflow": "w_REPLACE_WITH_SAVED_ID"}
  },
  "policy": {"release":"local","tools":"none","external_send":false}
}
```

Attach its existing `t_...` ID. The supervisor pins its kind, match specification
and action; changing that trigger requires another attachment. File, webhook,
calendar or email kinds are not claims that a watcher is installed or receiving
real events: the fleet runner must actually record and dispatch a matching occurrence.
The supervisor creates no event poller. Event payload is never copied into
`given`, native source, inputs or persistent operator state. Only trigger, mission
and step identifiers are retained as firing metadata.

## Inputs, policies and resources

Each native run retains the original source and supplied inputs plus execution
pins for kernel modules, imported libraries and used capability contracts. Any
clock inputs supplied automatically by the host executor are frozen **when saving the
workflow** and shown in its frozen receipt. Use an explicit native observation
inside the program when a later firing needs current external time or state.
Editing a saved program elsewhere does not change this workflow.

A run step's optional `options` accepts `by` (exact applicator), `model_policy`,
`mode`, `side_effects` and a lower-only `max_effects` limit. Current settings are captured as permission ceilings;
current operator settings may lower them again at dispatch. A missing `by` uses the
existing routing policy; a supplied choice is forwarded exactly. Confidential
work must use `model_policy: {"allow_cloud":false}` and local applicators. Model
calls and effects keep the host executor's per-run budgets and admission paths.

Limits: 32 steps; 4 concurrent native children; 64 persistent state keys; 7 days
per wait/deadline; 100 recorded firings per saved workflow; 8 attached event
triggers; a 4 MB saved record. The most recent 1500 journal transitions are kept
with monotonic sequence numbers; firing identities and native handles remain in
the bounded job list. At capacity, create a new workflow explicitly. Persistent
state is operator-defined JSON and mechanical counters, not a mailbox for untrusted
model output.

## CLI and API

The CLI talks to the same operator-only loopback API; it does not import and execute
a workflow in the caller's process:

```sh
.venv/bin/python integration/host/symblic_supervisor_api.py create --file workflow.json --request-id save-demo-1
.venv/bin/python integration/host/symblic_supervisor_api.py start --id w_REPLACE --request-id run-demo-1
.venv/bin/python integration/host/symblic_supervisor_api.py view --id w_REPLACE
.venv/bin/python integration/host/symblic_supervisor_api.py tick --id w_REPLACE
```

Reuse the **same request ID after a lost reply**. A new identity asks for another
firing. `--file` supplies the request JSON for state, pause, schedule, bind and
reconcile; include the shown revision for edits. Routes live under
`/api/automation/symblic/supervisor/`: GET `list`, `view`; POST `create`, `start`,
`tick`, `state`, `pause`, `schedule`, `bind`, `reconcile`, `simulate`. The API uses
both the operator check and the host's identity check. Private records are under the existing
private `automation_data/symblic/supervisors/` tree.

**Simulate control flow** never executes a native program, tool, model, wait or
clock. It uses explicit synthetic `outcomes` keyed by native step ID (`done`,
`failed`, `unknown`); unspecified native outcomes stay unknown. Its wait total is
a serial control-flow illustration, not a measured parallel execution time.
Simulation is labelled separately and is not an execution receipt.

Python/API/tool declaration installation is restart-gated. The Dashboard and
the fleet runner worker must both see the two new host-executor declarations. Missing APIs
remain visible errors; opening the page performs no model launch or schedule
installation.
