# Optional checked constructors

Installed and live-verified on 5 October 2026; see the
initial release receipt (not included in this repository) and the
[recovery and controls amendment](evidence/2026-10-05-constructor-recovery-controls.json).

The optional constructor integrates with the statement runner, CLI and operator
API. Journal version 3 and shared Run/CLI/API recovery gates preserve recorded
attempts. Existing model, kernel, graph and delegation paths remain available.
The host must separately provision the pinned solver environment before enabling
construction; see [provisioning](CONSTRUCTOR-PROVISIONING.md).

A constructor proposes an exact value for a supported formal contract. Symblic
checks that value using the original native type and anchored predicates, records
the outcome, and then binds it through the ordinary statement runner. A later
statement receives the same dependency provenance as other native values.

The first constructor supports a bounded linear Bool/Int/rational fragment and
flat records. It uses a separately pinned, bounded worker. Unsupported language
features retain their existing execution path; the constructor does not simplify
or erase the source to make it fit its fragment.

```symblic
given base: Int = 10.
ask next: Int "Construct the next integer."
ensure next = base + 1 else retry.
let doubled = next * 2.
show doubled.
```

The host selects the mode in the native runner or operator API:

```json
{
  "constructor": "linear",
  "determine": false,
  "profile": "verified",
  "constructor_limits": {
    "attempts": 16,
    "milliseconds": 80000,
    "attempt_ms": 5000,
    "resource_limit": 100000
  }
}
```

Supply the ordinary model applicator separately for any permitted fallback.
`off` is the default. `linear_diagnose` records checked constructor candidates and
continues the original model path; it exposes none of those candidates or private
constants in the model's prompt. `linear` can bind a checked candidate directly.
The existing `solve` setting keeps its finite native meaning and remains off for
this first constructor path. No program or API field supplies a worker executable,
package path, SMT-LIB program or raw provenance assertion.

The initial constructor path is sequential ordinary voting-route asks, using an
explicit applicator. Search, escalation, automatic routing and `for each` retain
their current behavior and report that construction was not attempted. An authored
native-determination override is preserved. Nonempty program `use` defaults and
ask-local options remain outside this first fragment; use the explicit host
profile for the example. They fall back visibly rather than being discarded.

Each eligible attempt has one deadline across preflight, journal reservation,
worker execution and final native checks. The host additionally admits the child
within the existing 600 MiB runner envelope: a 256 MiB address-space cap, measured
parent headroom and an 88 MiB reserve. The worker has no model, network or effect
authority. Resource refusal retains an explicit disposition. The attempt budget
is separate from model calls and remains charged across resume and retry rollback.
`resource_limit` sets the recorded Z3 work allocations for its bounded checks;
it is not a measured global CPU-instruction cap. The process deadline and OS
limits apply separately.

Before launch the runner durably records its source, inputs, semantic identity,
constructor configuration, dependency identities and allowance. It commits an
accepted outcome only after every counted witness passes the original native
checks under the shared remaining kernel budget. Ordinary source ensures still
execute after binding. An unconfirmed launch, missing outcome or unreaped worker
blocks subsequent work until explicit recovery; it never silently retries or
starts a fallback model.

Selection is canonical among the at most two recorded checked witnesses. One
witness does not establish uniqueness, and solver-reported UNSAT does not establish
a contradiction. Exact replay rechecks and reuses the recorded selected value;
it launches neither a solver nor a model. Fresh construction can produce a
different finite candidate set. A fixed seed is not a portable-output guarantee.

Constructor answers report `answered_by="constructor"`, zero model votes and
no measured agreement. Their version-2 `solver_proposal` claims remain unknown
premises with exact native schema/predicate receipts. Downstream derived claims
remain conditional on the solver proposal and its inherited premise roots.
The retained journal outcome identifies the proposal; it is not evidence of
empirical truth. Existing version-1 origins and receipt/container formats remain
unchanged.

Notebook imports of a solver proposal require its exact configuration, journal
outcome and native-check relationship. The imported notebook records the journal
snapshot hash and then follows existing revision/withdrawal behavior. A missing
journal cannot be replaced by a client assertion. Constructor-bearing portable
locks use a distinct version and preserve that provenance; ordinary version-2
locks remain supported. Export of repaired journals currently refuses; retain
the original run records for inspection. See [lock semantics](CONSTRUCTOR-LOCKS.md).

The initial release source passed 204 integrated native checks and a separate 66-method
compatibility suite; some methods overlap. The journal contributes 71
producer/regression checks. Earlier review failures and targeted passing repeats
are retained. A two-statement probe verifies that helper temporary bindings
never become premises, while each selected result retains its actual parent.

That initial frozen source completed four handwritten contracts and four exact
portable replays through the fixed host solver, with zero model calls and all
four worker children reaped. Its measured cgroup peak was 99,962,880 bytes under
a 600 MiB limit. The six-command native CLI journey covered check, run, resume,
replay, lock and lock replay. A live operator API run then constructed the example's
value, produced `22`, resumed with unchanged epistemic records, and replayed its
version-3 lock with zero model calls. The original failing prototype is retained:
its values passed, but portable replay exposed temporary helper bindings.
These are finite solver/runtime checks, not a model-quality benchmark or a
universal determinism proof. Separate cancellation and parent-memory refusal
evidence is tied to its earlier recorded source.

The current amendment (kernel `59c87dc8a638abce`, constructor bridge 2) passes
226 focused methods, a separate 66-method compatibility selection and 29 mocked
browser journeys, including phone/dark behavior. It repeats the six-command
zero-model CLI journey. Live API run `99fe6ef1c652` produced `22`, retained the
same three journal rows and exact epistemic registry across resume, and replayed
its version-3 lock with zero model calls. These results concern this exact source;
the four-contract resource measurements above remain tied to the initial release.

In the Write tab, open **Checked construction**, enable the checkbox, and select
a mode and model-call budget under Advanced. The default budget is zero; an ask
that needs a model then fails visibly. The server feature marker enables these
controls without inspecting solver packages. A paper uses its existing path.
Prepared Logic/delegation/reopened-run policies retain their own exact options,
including any already-bound construction setting. No separate control overrides
their call budget. A saved setting blocks Run when the server cannot honor it.

Recovery checks inspect bounded, structured host records. Before announcing an
attempt, the runner writes and syncs `constructor_activity` in `state.json` and
syncs the folder. Later running and final snapshots retain it durably. The lock
and all eight fixed quarantine paths also establish retained activity when
primary records are missing. Enabled snapshots record `constructor_bridge: 2`;
a non-completed older snapshot without that field requires explicit recovery.
The shared retained-history check also prevents a missing journal from turning a
recorded fallback attempt into an ordinary version-2 lock. Every quarantine path
refuses export, including a repair interrupted before its audit row.

Cloud review reproduced the original crash gap and checked 576 crash/deletion
combinations plus 24 durable-save failure cases. Root reproduced its findings,
added targeted regressions and checked 192 legacy-resume combinations. With the
state record retained, direct enabled legacy resume now refuses redispatch.
Ordinary old off-mode behavior is preserved: changing a legacy folder to off
after removing constructor records can still erase that old ambiguity. The
pre-install inventory had no unfinished enabled-constructor runs to migrate.
These are process-crash checks; they do not model storage power loss.

Recovery checks inspect bounded, structured host records. A configuration/journal
presence mismatch or retained attempt evidence requires explicit recovery before
Run, CLI or API resume can proceed. Completed zero-attempt runs remain usable.
Unfinished enabled history can be conservatively ambiguous. Deleting every
relevant host record cannot authenticate or reconstruct the erased history.
See [the CLI handoff](CONSTRUCTOR-CLI.md) and [host provisioning](CONSTRUCTOR-PROVISIONING.md)
for the exact entry points.
