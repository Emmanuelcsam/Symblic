# symblic.distill — distillation research tooling

**Status: research tooling, no claim attached.** The question behind it: if a small model's answers are accepted
only when a Symblic program's own checks pass, can those accepted answers be used to fine-tune a model? This
package builds the pipeline to try that carefully. It does **not** show that the answer is yes. The one pilot
that ran end to end (a 0.5B model, four LoRA optimizer steps on 2 CPUs, 111 seconds, 4.5 GiB peak memory) matched
0 of 3 held-out answers before training and 1 of 3 after, which is no evidence of improvement (paired exact
p = 1). A separate physics question failed in both arms. Details and limits: `docs/reference/DISTILLATION.md`.

Like the rest of Symblic, this code was written by AI coding agents.

## What is in this package

| Module | Role | Heavy dependencies |
|---|---|---|
| `datasets.py` | Pure core: records -> dataset, frozen leakage-aware splits, training and evaluation plans, output checks, exact paired comparison. | none (stdlib) |
| `export.py` | Replays one accepted Symblic run with no model (in a child process) and emits a record per accepted scalar answer. | the Symblic kernel |
| `contracts.py` | Builds the trusted *contract bundle* (original program, closed predicates, pinned runtime) the native checker needs. | the Symblic kernel |
| `checkers.py` | Native scalar checker: re-runs the original program's predicates on a new answer, in a resource-limited child process. | the Symblic kernel |
| `worker.py` | Runs one prepared training, evaluation or inference job with the LoRA backend. | torch, transformers, peft, safetensors, tokenizers (optional, pinned) |
| `cli.py` | Command line for every step: `python3 -m symblic.distill.cli --help`. | none until a command needs it |

## How the pieces fit

```
accepted Symblic run folders
   │ export-run (export.py)               replay with no model, keep accepted scalar answers + native receipts
   ▼
records.json ── build (datasets.py) ──► dataset.json ── split ──► splits.json (train / validation / test)
   │                                                                │
   │ export-contracts (contracts.py)                                │ plan-train, prepare-train
   ▼                                                                ▼
contract bundle (staged at checkers.BUNDLE_FILE)        training job dir ── worker.py run ──► LoRA checkpoint
   │ checker-identity                                               │
   ▼                                                                ▼
plan-eval (checker = schema | schema_and_reference | schema_and_native) ── prepare-eval ── worker.py run
                                                                    │
                                                                    ▼
                                                     compare: exact paired baseline vs trained outcomes
```

Every artifact is canonical JSON with its own SHA-256, and every later step pins the digests of the earlier ones.
Nothing is overwritten; a changed input refuses instead of being silently re-used. The worker never downloads:
models are local Hugging Face snapshots pinned by a file manifest (`model-manifest`), loaded offline with
`trust_remote_code` off and safetensors only.

## What is measured machinery and what is not

* Measured and tested: the file formats, pinning, split leakage rules, resumable checkpointing, the refusal paths
  and the native checker's isolation (tests/distill, all with fake backends).
* Exercised once, at toy scale: real LoRA training, evaluation and inference (the pilot above).
* Not implemented: GRPO / verifiable-reward training (`grpo-status` explains what is missing), GPU training.
* Not established: that any of this improves a model.

## Run it

```sh
python3 -m symblic.distill.cli --help
python3 -m symblic.distill.cli grpo-status
```

The `launch` and `launch-infer` commands print the exact worker command (argv and environment) instead of running
it; run that yourself in a resource-limited environment, for example:

```sh
python3 symblic/distill/worker.py run --job-dir JOB --models-root MODELS --backend torch-lora
```

## Tests

```sh
cd <repository root>
DASH_TEST=1 python3 -m unittest discover -s tests/distill -t .
```

The tests use fake training and generation backends; no model, download or network is used. They take about five
minutes because the native checker runs every check in a fresh child process.

## Only in the original host

In the system this came from, the training worker ran inside an admitted, resource-limited unit on a separate
compute machine, and a contract bundle was staged by the machine's administrator. Here you are that operator:
choose where the worker runs and stage the bundle at the fixed path in `checkers.BUNDLE_FILE`
(`~/.local/state/symblic-distill/native-contracts.json`).
