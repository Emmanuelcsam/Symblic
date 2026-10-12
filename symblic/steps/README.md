# symblic/steps: step constructions

The most constrained way to let a model build a program. The author writes the steps; for each function: its name,
parameters, return type, the earlier functions it may use, a list of candidate expressions and checks, plus final
checks over the whole program. The model's only job, step by step and in a fresh short context, is to answer with the
**number** of the right expression. The kernel defines the function from that exact expression and runs the step's
checks; a failure is retried with the reason. A model never writes code here, and the module never ranks choices.

## The modules

| module | what it does |
|---|---|
| `construction.py` | `prepare` (validate a request), `compile_sequence` (the Symblic program, one model request per step), `assemble` (the finished program from the accepted choices) |
| `recovery.py` | `from_folder`: read a finished run back and accept it only if everything agrees (program, inputs, execution pins, kernel, every check receipt, every attribution), then assemble the program; `prepare`: compile with execution pins, ready to run |

With `finite_fallback`, after the model's retries fail the kernel may try the author's choices in order; the record then
says the host, not a model, selected that step, and `from_folder` reports both counts (`model_selected_steps`,
`finite_selected_steps`).

## Try it

```
python3 -m symblic.authoring.workcards compile --kind steps --request examples/steps-parcel.json \
  --by ollama:qwen3:4b-instruct                                                  # no model: prints the program
python3 -m symblic.authoring.workcards run --kind steps --request examples/steps-parcel.json \
  --by ollama:qwen3:4b-instruct --dir /tmp/parcel-run                            # asks the model
python3 -m symblic.authoring.workcards result --kind steps --dir /tmp/parcel-run   # read back; no model
```

`examples/steps-parcel.json` builds 13 parcel-pricing functions; `examples/steps-parcel-built.sym` is the assembled
result, which runs with zero model calls on `examples/steps-parcel-inputs.json`.

## Status

Tested with fake models, including every tampering case of a saved run. `from_folder`'s checks are local consistency
checks over files on disk, not signatures. `recovery.py` came from the original host's HTTP glue; the route that
looked runs up by id stays in `integration/host/symblic_steps_api.py`.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/steps -t .
```
