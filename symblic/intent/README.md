# symblic/intent: writing down what was asked before compiling it

**What this package explores.** Most failures of "turn my request into a program" start before any code: the
request was ambiguous, an assumption was silently made, or a requirement was dropped. This package keeps an
explicit, revisioned *intent record* between a person's request and the Symblic program compiled from it:
the original request is kept verbatim, a model may only *propose* a goal, requirements, assumptions, questions
and examples, only the person (the "owner" of the request) can answer, adopt, retire or rewrite, and every
compiled program is checked and pinned to the exact record it came from. Afterwards it can say which
requirements the program checks and what those checks observed when it ran.

**Status: prototype.** The record rules, the coverage mapping, the session store and the run join are covered by
67 unit tests. The interpreter that drove them (model jobs, HTTP routes, the handoff to a runner) only ran
inside the original host and is kept in `integration/host/`.

## The modules

| Module | What it does |
| --- | --- |
| `records.py` | The intent record and its event rules: `new_intent`, `apply_event` (proposal, answer, assumption, requirement, predicate, rewrite, applicator, checked, handed_off), `validate`, `readback`, `compiler_prompt`, `coverage_manifest`, `prepare_handoff`. Pure. |
| `coverage.py` | `requirement_coverage(state, source, inputs)`: where each requirement's predicate appears in a compiled program, matched by syntax shape. Presence only, never execution. Pure. |
| `requirement_execution.py` | `derive` / `view`: joins a handed-off intent with the run's own records (bounded, no-follow reads) and counts the check receipts at each requirement's locations. Read-only. |
| `store.py` | One private, atomically replaced `record.json` per session, with the model-call budget (`reserve`): failed or uncertain calls stay spent. |

## The flow

```
request ──new_intent──► record (request verbatim, sources hashed)
model proposal ──apply_event('proposal', actor='model')──► goal, requirements, assumptions, ≤3 questions
owner answers / adopts / retires / sets predicates ──apply_event(actor='owner')──► new content revision
compiled program ──checked artifact (kernel id, module hashes, catalogue, policy, sources)──► 'checked'
                 └─ coverage.requirement_coverage: which predicates appear where
handoff to an executor ──'handed_off' (kind host_plan / host_run)──► run
run records ──requirement_execution.view──► per requirement: observed / partially observed / failed / unobserved
```

Every view keeps `intent_fidelity: unassessed` and `owner_acceptance: not_established`: passing checks show that
the encoded predicates held on that source and those inputs, not that they capture what was meant.

## Outside this package

- `integration/host/symblic_intent_api.py`: the original host's interpreter routes and background model jobs
  (sessions under the host's data root, the host's model policy and capability catalogue, the handoff to the
  host's program runner). Host-only.
- `web/studio/symblic-intent.js`: the interpreter page of the original host's UI; its offline checks are in
  `tests/integration/test_symblic_intent_page.py`.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/intent -t .
```

Run from the repository root. Temporary folders and in-memory records only; no model, network or worker. The
host interpreter's tests (`tests/integration/test_symblic_intent_api.py`, `test_symblic_intent_selection.py`)
skip without the host.
