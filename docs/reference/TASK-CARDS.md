# Task cards and portable builds

Implementation workstream, 4 October 2026; deployment status updated 5 October.
These additions are included in the installed reform. See the [5 October release evidence](evidence/2026-10-05-reform-install.json)
and [REFORM-3](REFORM-3.md); earlier RC2 results retain their recorded scope.

Task cards turn a spec sheet into ordinary Symblic statements. Each model request
contains one unit's complete contract, the shared specification, and the exact
code and contracts of every declared transitive dependency. Previous chat and
unrelated unit code are absent. The host retains progress and evidence between
requests. The worker can start each unit with fresh context.

The compiler offers `presentation='compact'` (the default) and
`presentation='full'`. Compact presents the required declarations and signature
directly, followed by labeled project instructions, unit behavior, dependencies,
setup and exposed examples. Full presents the structured authoritative task
record. Both include the same task-bearing fields and exact transitive dependency
code. The instruction names the actual requested declarations; it does not ask
the model to implement a task-card protocol or interpreter.

Compact displays identical project-wide fields once and explicitly applies them
to the requested unit and every dependency. It preserves each dependency's full
heading, names, body, Uses, setup and examples. External requirements and their
resolution scope are explicit in both views. Opaque unit IDs and contract hashes
may be omitted from the compact text; the complete plan, compiler settings,
runtime identity and authoritative dynamic cards remain in the generated source
and compiler result. The native request record pins the exact model-facing
prompt. Unknown task fields fail compilation until the projection accounts for
them; they are never silently dropped.

The generated source binds identical project and unit records once and shares
those exact values across cards. A pure Symblic formatter renders compact unit
fields. This avoids repeatedly embedding parent contract literals and preserves
the existing native source-size limit; the model still receives every required
dependency's full code and task fields.

This is an interface improvement to test, not an established accuracy or token
saving result. The developmental fixtures use only their declared requirements
and exposed examples. No held-out answers or reference implementations are added
to the constructor's prompt.

In Build, select **Task cards with dependency-aware reuse**. `Uses:` names form a
directed acyclic graph. The checker refuses unknown names, cycles and generated
name collisions; it computes stable unit identities, execution order and layers.
The native compiler currently executes those units in topological order. Existing
candidate search can ask several models about one unit. Exposed graph layers do
not themselves imply concurrent unit execution.

Every unit is checked with only its declared dependency closure and test setup.
After construction, the combined unit code is checked against every unit's
examples. For `.js` outputs, the complete assembled template is checked too, so a
template cannot silently replace a function after its unit check. For HTML or
other containers, the checks cover the combined JavaScript units; browser layout,
DOM interactions, other scripts and packaging need their own acceptance checks.

## Optional exact declaration contracts

`declaration_contracts` is an opt-in mapping from a stable **unit ID**, as returned
by `spec check`, to a JavaScript declaration contract:

```json
{"version":1,"exports":{"first":"function"}}
```

Each policy's export names must exactly match that unit's declared names. Kinds
are `function`, `class`, `const`, `let` or `var`. The mapping may cover only some
units. Unmapped units retain the existing Code and example-check path; an empty
mapping enables no declaration policy. Invalid IDs, extra or missing export names,
unsupported versions and unknown policy fields fail before any model request.

The optional checker parses ECMAScript 2022 script syntax with pinned Acorn in the
existing required sandbox. It checks exact top-level names and declaration kinds,
refuses wrappers, imports, exports, top-level returns and extra declarations, and
restricts eager initialization to its documented passive loading policy. It does
not check function arity, mathematical meaning, all behavior after invocation or
general JavaScript purity. The unit's tests and project-level checks remain
necessary. See [the declaration adapter](../../symblic/js/contract.py) for the
precise supported loading forms.

Every new candidate for a covered unit passes `js_declarations_check` under
`ensure ... else retry` before example execution. Its scoped parser diagnostic is
available for repair. A kept artifact uses an assertion against the same policy;
self-issued receipts do not bypass that local check. Checkpoint and manifest
export recheck the declaration surface again, sharing the aggregate deadline with
all isolated, joined and final-template example checks. A parser budget outcome
is reported as budget exhaustion, not evidence that the program is semantically
wrong.

The context setting is an exact character budget for the native system string,
schema and prompt, including repair feedback. A required card that does not fit
is refused before dispatch. No dependency is silently truncated. Model tokens
and billing usage are separate measurements.

## Reuse and exact artifacts

Select an earlier task-card run to recheck its accepted code. An unchanged branch
can be kept even when an earlier unrelated branch needs rebuilding. Changed unit
contracts, dependency artifacts or runtime identity invalidate reuse. Every kept
unit still runs its applicable declaration policy and examples again; a supplied
receipt never bypasses execution. Presentation and the normalized declaration
mapping are part of the runtime identity. Changing either currently invalidates
reuse conservatively, including when only one unit's optional policy changed.
Enabling a policy therefore cannot silently keep artifacts checked without it.
Legacy sequential sheets and leading-unit Keep remain available.

**Recheck and export build manifest** produces exact code bytes, ordered exports,
complete contracts, dependency identities, scoped host check receipts, runtime
identity and the assembled output's full SHA-256. Import it on another agent or
host through Build or the CLI. Inspect recorded identities first; current runtime
compatibility and local checks determine whether code can be kept.

Manifest hashes establish integrity against a caller-held identity. They are not
signatures. The pure manifest verifier checks recorded relationships; importing a
manifest into a build executes its retained code's checks again. Fresh model
construction records its own artifact hash; exact artifact transfer uses the
retained bytes and an expected output or manifest hash.

Export/recovery explicitly runs the local sandbox. The HTTP operation has an
aggregate 30-second recheck budget; exhaustion is reported as a budget outcome,
not a wrong program. CLI callers can select 1–1800 seconds. No model is called by
check, checkpoint, export or verify.

```sh
tools/symblic spec check project.sheet.md --agent-json
record="$(mktemp -d /tmp/symblic-project.XXXXXX)"
tools/symblic spec run project.sheet.md --by ollama:granite3.3:2b --samples 1 --retries 1 --rounds 1 --dir "$record" --agent-json > project-result.json
tools/symblic spec manifest "$record" --recheck-seconds 60 > project.manifest.json
tools/symblic spec verify project.manifest.json --agent-json
tools/symblic spec run project.sheet.md --by ollama:llama3.2:1b --manifest project.manifest.json --agent-json
tools/symblic spec compile project.sheet.md --by ollama:llama3.2:1b --presentation full --declaration-contracts declarations.json --agent-json > compiler-envelope.json
```

`spec run` preserves the complete compiler envelope: profile, parallelism, ask
and call limits, source-embedded plan, presentation, declaration policies,
dependency contracts and reuse decisions. It adds execution pins and uses the
existing native runner and admitted applicators. The `--by` option is required;
repeating it selects the task-card compiler's existing candidate-search inputs,
not the delegation template's automatic ladder.

With `--dir`, use a new empty directory. It retains `program.sym`, complete
`compiler.json`, pinned `meta.json`, the native run records and `spec-result.json`.
Only an `accepted=true` result contains `output.text` with the exact assembled
bytes and their full `output.sha256`. `output.file` is the caller's template
label; the command does not write to that path. Progress goes to stderr; stdout
is one JSON result, and failures/stops exit nonzero. `SIGINT`/`SIGTERM` request
native cooperative cancellation; cleanup cancels only this command's owned calls.
Without `--dir`, there is no durable record for later checkpoint or recovery.

Optionally supply `--output-sha256` to require a previously known exact artifact.
A mismatch returns no accepted output even if the native exposed checks passed;
`native_status` and `observed_output_sha256` preserve that distinction. This is
byte identity, not semantic canonicalization. The requirement is bound into the
compiled plan and saved record. Later `checkpoint` and `manifest` commands retain
it even when the flag is omitted; a different explicit hash refuses instead of
replacing the recorded requirement. Complete exports must match. An incomplete
checkpoint retains accepted independent pieces and reports the final output hash
as `pending_incomplete`, with no claim that it matched. Older records without an
output-hash requirement keep their existing behavior. Initial contract files are
created exclusively with mode 0600 before any content is written.

Use `--keep PRIOR_DIR` or `--manifest FILE` in a new build to recheck and retain
eligible prior artifacts under that new build's declared contract.
The CLI refuses a nonempty run directory rather than implicitly resuming it.

`spec compile` remains source-only without `--agent-json`, and returns the full
compiler envelope with it. Passing only that source to generic `tools/symblic run`
does not carry the compiler's host options. Use `spec run`, or explicitly provide
the full returned source, inputs and options to native `Run`.

For a complete small example, use
[agent-handoff.sheet.md](../../examples/agent-handoff.sheet.md) in the commands above.
It has a `double` unit, an independent `ready` unit and a `next` unit that declares
`Uses: double`. The `next` request receives the complete `double` contract and
exact accepted code; unrelated `ready` code is absent. Its exposed examples
check finite cases, not all integer inputs. A parent can transfer the completed
manifest and verify the caller-held output hash before local reuse checks.

Construct an opt-in policy map from the exact plan instead of guessing unit IDs:

```python
import json
from pathlib import Path
import symblic.spec.sheets as SP
import symblic.spec.contracts as C
import symblic.spec.build as B

sheet = Path('project.sheet.md').read_text()
plan = C.plan(SP.parse(sheet))
first_unit = plan['units'][0]
# Choose kinds to match this caller's actual contract; this example requests functions.
policies = {first_unit['id']: {
    'version': 1, 'exports': {name: 'function' for name in first_unit['exports']}
}}
settings = B.compiler_settings(plan, presentation='compact', declaration_contracts=policies)
Path('declarations.json').write_text(json.dumps(settings['declaration_contracts']))
compiled = B.compile_cards(sheet, ['fake:constructor'], declaration_contracts=policies)
assert compiled['settings'] == settings
```

Compiling this example invokes no model. Executing its resulting program requires
an actual registered applicator (or a fake applicator in isolated tests).

`symblic.spec.contracts` is the pure contract/manifest API. `symblic.spec.build`
compiles the native program and rechecks run records. `integration.host.symblic_engine` exposes
`spec/check`, `spec/run`, `spec/verify` and `spec/manifest` under the existing
operator-gated Symblic prefix. Browser polling never performs a recheck.

External `Uses:` names are explicit declarations. The pure card marks them as
external requirements; the declaration alone does not carry an implementation.
In a code build, executable helper definitions must come from its supplied test
setup or the pinned JavaScript environment. No hidden host variables are loaded.

## Construction networks

An **Epistemic Construction Network** is a graph of constructor tasks, acceptance
checks, explicit memory views and recorded state transitions. Symblic supplies
the statement language; task cards supply dependency memory; the graph runtime
supplies bounded orchestration and recovery. Models or humans can supply the
constructed code, proof or witness. General checkers decide the encoded acceptance
conditions. Direct exact computation remains available for tasks where it is the
cheapest correct implementation.

The architecture supports experiments in routing, decomposition and graph
topology. A learned routing improvement must be measured on frozen held-out
tasks with complete authoring, repair, checker and inference costs. A graph of
agents is not claimed to inherit neural-network training guarantees merely by
being called a network.
