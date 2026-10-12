# symblic/forge: from a vague idea to reviewed requirements and build instructions

**What this package explores.** Before a model writes code, someone has to decide what should be built. The
Forge is a requirements workbench built on one rule: **models propose, only the operator accepts.** A project
starts from an incomplete intention ("I want a simple snake game"); the Forge asks bounded questions, keeps
assumptions in quarantine until they are accepted, records every decision with its provenance, and grows an
engineering structure (objectives, acceptance criteria, architecture, components, isolated construction units,
agent / model / machine plans, invariants, forbidden behaviour). When it is ready, it exports task cards, a
construction plan and a Symblic program checked by the real compiler, and freezes a handoff. It never builds
the project it describes.

**Status: prototype.** The state machine, store, exports, coaching and model jobs are covered by 98 unit tests
(temporary SQLite stores, fake model providers). The Forge's web page and HTTP routes belonged to the original
host and are not shipped here (`integration/host/symblic_forge.py`, `symblic_forge_bridge.py`), so in this
repository the Forge is a Python library.

## The modules

| Module | What it does |
| --- | --- |
| `core.py` | The project document and its ~60 pure transitions (`transition(project, action, payload)`), `analyze` (readiness, blockers, contradictions, coverage), `fingerprint`, branches, snapshots, merges, `snake_demo`. |
| `catalog.py` | The question catalogue: modes, roles, engineering dimensions, ideation lenses, per-domain questions and trade-off notes; `classify` and `questions_for`. Data, no decisions. |
| `coach.py` | Coaching for one atomic construction instruction (one change, exact input and output, a check, named context): `preview`, `lens`, `overview`, teaching `EXAMPLES`. |
| `exports.py` | Task cards, construction plan, native Symblic source, spec sheet and brief from accepted records; `validate` runs the native checker and pins the compiler source files it used. |
| `models.py` | Explicit model proposal jobs: `build_request` for a role (IDEATOR, QUESTIONER, CRITIC, SPECIFIER) and `run_job`, which dispatches each attempt once, after recording it. |
| `store.py` | SQLite persistence: revision compare-and-swap, request-idempotent mutations, append-only history, artifacts, model jobs. Default location `~/.local/share/symblic/forge` (or `$SYMBLIC_FORGE_DATA`). |
| `watch.py` | A read-only health summary of the store for a status page. |

## Using it from Python

```python
from symblic.forge import core as C, exports as E
from symblic.forge.store import Store

store = Store('/tmp/forge-demo')                      # or Store() for the default location
project = store.create('I want a simple snake game', '', '', 'create-1')
print(C.analyze(project)['next_question'])              # the next undecided question
demo = C.snake_demo()                                   # a fully decided, labelled example project
print(E.artifact(demo, 'construction')['text'][:400])   # also 'tasks', 'sheet', 'brief', 'prompt', 'manifest', 'symblic'
print(E.validate(demo)['ok'])                           # the generated Symblic program, checked by the compiler
```

Model help is explicit: build a request with `symblic.forge.models.build_request(...)`, reserve it in the
store, and run it with `run_job(job_id, store=store, applicators=...)` using an applicator from
`symblic/providers` (a local Ollama model, an agent command line, or a fake for experiments).

## Limits worth knowing

- Accepting is always a separate, explicit transition. Model agreement accepts nothing.
- A validation receipt says the generated program parses and type-checks; `executed` is always false.
- Remote providers are refused for a role unless the operator explicitly allowed them.
- If the compiler source changes on disk while a process runs, validation refuses ("restart required")
  instead of issuing a receipt for code that is not the code running.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/forge -t .
```

Run from the repository root (a few minutes). Temporary stores and fake applicators only; no model, network
or worker. The original host's Forge routes and handoff bridge are tested in `tests/integration/` and skip
without the host.

User guide of the original application: `docs/reference/FORGE.md`, `docs/reference/FORGE-ACCEPTANCE.md`.
