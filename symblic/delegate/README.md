# symblic/delegate: hand one bounded task to a small agent

A parent program, a person or another agent often needs one small, well-defined thing done by a model: put data into a
typed shape, classify into fixed categories, pick one line of a text and prove where it came from, take one step of a
proof. A **delegation template** turns such a request into an ordinary Symblic program whose checks decide what is
accepted. The parent gets back an exact, checked value, or a refusal with the reason; never an unchecked answer.

## The modules

| module | what it does |
|---|---|
| `contracts.py` | the templates: `catalog()` (each template's JSON request schema and what acceptance does and does not establish), `compile_task(request)` (the program, its inputs and options, a stable contract id), `inspect_task(request)`; pure, runs nothing |
| `run.py` | `run_task(request, by=..., applicators=..., folder=...)`: compile, pin the kernel sources (execution pins), run on the kernel's runner, return the exact canonical value only after success; `verify_declaration` checks a saved run before resume or replay; the `delegate` command |

Templates: `typed_transform`, `enum_classification`, `witnessed_line`, `exact_arithmetic` (computed by the kernel, no
model), `proof` (including incremental, one checked command at a time), and four proof-step variants (`proof_step`,
`proof_step_obligation`, `proof_step_focus`, `proof_step_card`) for handing a single inference of a larger proof to a
fresh child agent with a projected, bounded view of the proof so far.

**Routing.** With `--by` the caller names one applicator or an ordered list (up to 12) for the kernel's automatic route.
Without it, a template that may call a model uses a local-only ladder of small Ollama models (llama3.2:1b,
granite3.3:2b, qwen3:4b-instruct) within the template's own call ceiling, and never falls back to a cloud model. The
ladder reflects the models installed when it was written (October 2026), not a measured ranking.

## Try it

```
python3 -m symblic.delegate.run catalog                                       # no model
python3 -m symblic.delegate.run check examples/agent-handoff.task.json --json # no model
python3 -m symblic.delegate.run run examples/agent-handoff.task.json \
  --by ollama:qwen3:4b-instruct --dir /tmp/handoff                            # asks the model
python3 examples/proof_step_handoff.py                                        # a parent with fake children; no model
```

`examples/` holds a task file for most templates and four parent programs for the proof-step variants;
`examples/expense_handoff.py` is a complete hand-off with pinned inputs and an exact replay.

## What acceptance means

The catalog states the limits (`catalog()`, fields `assurance` and `semantic_validation`). In general: passing establishes that the declared
checks held for this answer (a schema, a membership, an exact span of the source, a valid inference under the caller's
premises); it does not establish factual truth, instruction fidelity beyond those checks, or that the premises are true.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/delegate -t .
```

Fake models only. Frozen fixtures (`tests/fixtures/symblic_delegate_v5..v8_parity.json`) pin that earlier templates'
compiled contracts stay byte-identical as templates are added. Two tests compare the kernel's preview with the first
real request and are skipped where the kernel's bounded preview process is unavailable. The host-only HTTP route tests
are `tests/integration/test_symblic_delegate_routes.py` (skipped without that host).
