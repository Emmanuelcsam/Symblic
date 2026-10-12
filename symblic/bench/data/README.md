# symblic/bench/data — benchmark inputs

Everything here is input data for the runners in `symblic/bench`. All of it is synthetic and was written by AI
agents for these benchmarks; none of it is personal or real-world data.

| Path | Used by | What it is |
|---|---|---|
| `ambiguity-v1.json` | `ambiguity.py` (`--suite ambiguity`) | 42 synthetic request-interpretation cases in 14 families (7 development, 7 held-out). Each family has two ambiguous twins with identical public text and different hidden preferences, plus one clear control. |
| `ambiguity-v1.md` | readers | The dataset's design: case fields, the clarification protocol, the split boundary and what the labels can and cannot establish. |
| `matched-example-v1.json` | `matched.py` (`--suite matched --matched-manifest`) | A small example manifest (three cases, direct and typed arms) that uses `fake:` applicators, for trying the protocol without a model. |
| `local_beta/config.example.json` | `local_beta.py` | Example configuration: allowed models, node labels, fixtures and batches. Copy it and edit the nodes and models. |
| `local_beta/fixtures/native/*.sym` | local beta lane 2 | Small Symblic programs with typed asks and `ensure` checks; `small-model-math.sym` makes no model call (a kernel-only control). |
| `local_beta/fixtures/english/*.english.txt` | local beta lane 3 | Plain-English statements compiled to checked asks. |
| `local_beta/fixtures/delegate/*.task.json` | local beta lane 4 | Delegate templates (witnessed line selection, closed classification). |

The SHA-256 of `ambiguity-v1.json` is part of every ambiguity plan's identity: editing the file creates a different
benchmark, and an existing results folder refuses to resume with it. Make a new versioned file instead.
