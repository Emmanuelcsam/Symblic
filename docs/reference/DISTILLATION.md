# Symblic distillation (SFT/LoRA), version 1

**Status:** implemented and locally verified, including an admitted real CPU pilot.
- **Implemented:** accepted-run export, dataset/split/plan/compare, durable job worker, explicit adapter inference, and `tools/symblic-distill`.
- **Tested:** 53 isolated core tests and 6 exporter tests; native export from four actual accepted runs; real LoRA training, frozen heldout comparison, checkpoint verification and inference on node-i (§10).
- **Limits:** v1 supports CPU training only. Native generation checking supports registered closed pure scalar contracts (§11); unsupported contexts refuse. GRPO is unsupported. The pilot does not establish general accuracy improvement.
- **Execution:** imports are inert. The planner CLI prints launch manifests; the explicit worker commands perform training/inference through the operator's admitted runner. Provisioning, model snapshots and cluster admission remain caller-owned.

**What it is:** supervised fine-tuning of a LoRA adapter on answers that Symblic runs already accepted under
their native checks, with a frozen held-out baseline-vs-trained comparison. Verifiable-reward/GRPO is
**unsupported** (see the end).

## 1. Environment (root provisions; verified 2026-10-06)

| package | exact pin | used for |
|---|---|---|
| Python | 3.12 (≥3.10) | |
| torch | 2.14.1 (`+cpu` wheel from the PyTorch CPU index on CPU nodes) | model, AdamW, `torch.load(weights_only=True)` |
| transformers | 5.18.0 | `AutoTokenizer`/`AutoModelForCausalLM.from_pretrained(local_files_only=True, trust_remote_code=False, use_safetensors=True, dtype=…)` |
| peft | 0.21.2 | `LoraConfig`, `get_peft_model`, `PeftModel.from_pretrained(…, is_trainable=…)` |
| safetensors | 0.8.0 | adapter/weights format |
| tokenizers | 0.23.2 | transformers dependency |

- **Not used:** trl, datasets, accelerate, bitsandbytes, deepspeed.
- **Version gate:** `preflight` refuses (`package_version_mismatch`) unless the installed versions equal the
  plan's `packages` exactly. The `+cpu`/`+cuNNN` local suffix is ignored.
- **How the APIs were checked:** the pinned set was co-installed in a scratch venv (Python 3.11.15, torch
  `2.14.1+cu130` from PyPI, because the PyTorch CPU index is not reachable from the cloud session). The
  signatures used here were introspected there, and peft's LoRA docs were read at tag `v0.21.2` and
  transformers' model docs at `v5.18.0`.
  - In transformers 5.18, `dtype` is the parameter; `torch_dtype` is kept only for backward compatibility.
  - peft 0.21.2 writes `adapter_model.safetensors` and `adapter_config.json`.
- **Offline:** the worker sets `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_DATASETS_OFFLINE=1` and
  `HF_HUB_DISABLE_TELEMETRY=1` before importing transformers, and passes `local_files_only=True` everywhere.

**Model format:** a local Hugging Face snapshot directory under the worker's `--models-root`:

- it needs `config.json`, the tokenizer files and `*.safetensors` weights;
- any symlink, `*.bin/.pt/.pth/.pkl/.pickle/.ckpt` or `*.py` file is refused (`model_format_unsupported`);
- `trust_remote_code` is never enabled;
- Ollama/GGUF blobs cannot be trained.

For the smoke run: `Qwen/Qwen2.5-0.5B-Instruct` at commit `7ae557604adf67be50417f59c2c2f167def9a775`. Its
Qwen2 attention projections match the default LoRA targets `q_proj, k_proj, v_proj, o_proj`, and it has a
chat template, which the worker uses.

**Measured CPU pilot:** 0.5B float32, 2 CPUs, 4 optimizer steps at a 1024-token training limit, complete training/evaluation/inference in 111.3 seconds and 4.5 GiB peak RAM (§10). Larger models have not been measured. CUDA and QLoRA are unsupported in v1; CPU RNG is checkpointed, so CUDA is refused rather than promising incorrect dropout resume.

## 2. Input: accepted Symblic ask records (exact schema, version 1)

The caller (root's exporter) derives one record per accepted ask from a run folder it chose explicitly.
This module never scans stores. Unknown fields are rejected. `sha256` is 64 lowercase hex.
`H(v) = sha256(canonical JSON)`, where canonical JSON means sorted keys, `(',', ':')` separators,
`ensure_ascii=False`, UTF-8 and no floats.

```json
{
  "version": 1,
  "run_id": "run-label",
  "source_sha256": "<sha256 of the program source>",
  "statement_sha256": "<sha256 of the ask statement>",
  "kernel_id": "<16 hex, symblic kernel_id()['id']>",
  "checker": {"id": "symblic-native", "version": 1, "sha256": "<checker identity>"},
  "model": {"requested": "ollama:qwen3:4b@node-a", "observed": "qwen3:4b",
            "identity": "observed", "digest": "<sha256 of the observed model manifest>"},
  "prompt": {"system": "<exact system text>", "user": "<exact prompt text>", "sha256": "H([system, user])"},
  "answer": {"type": "integer|boolean|string|label", "value": 6, "sha256": "H(value)",
             "fingerprint": "H(value)[:16]  (= symblic.fingerprint)", "labels": ["only", "for", "label"]},
  "acceptance": {"status": "accepted", "vote": "single|uncontested",
                 "determination": "typed_answer|unique_in_declared_domain|author_disabled",
                 "checks": [{"id": "<receipt sha256>", "predicate_sha256": "<sha256>", "passed": true,
                             "scope": "encoded_predicate", "kernel_id": "<same kernel>",
                             "predicate": "optional text"}]},
  "group_key": "optional caller grouping label",
  "exposure_hashes": ["optional sha256 of content already exposed elsewhere"],
  "request_sha256": "optional", "capsule_sha256": "optional",
  "sensitivity": "shareable|internal (optional)"
}
```

**Refused with a finite code:**

| code | cause |
|---|---|
| `missing_identity` | a missing or malformed identity |
| `prompt_hash_mismatch`, `answer_hash_mismatch`, `answer_fingerprint_mismatch` | a recorded hash does not match the content |
| `model_identity_drift` | the model identity drifted |
| `model_identity_unavailable` | no model identity, unless `--allow-unavailable-model-identity`, which is recorded in the dataset |
| `unsupported_outcome` | a status other than accepted |
| `ambiguous_outcome` | a contested vote |
| `acceptance_checks_missing` | zero checks |
| `check_not_passed`, `kernel_mismatch` | a check that did not pass, or one under another kernel |
| `unsupported_answer_type` | numbers with fractions, records, lists or code |
| `answer_not_in_labels` | a label outside its declared set |
| `duplicate_identity`, `conflicting_answers` | a duplicate item, or the same prompt with different answers |
| `secret_like_field`, `secret_like_content` | secret-like keys or values: password/token/api key/cookie/bearer/private key, `sk-…`, `ghp_…`, `AKIA…`, PEM keys, JWTs |
| `private_record` | `sensitivity` private/confidential |

The secret screen is a pattern check, not proof that no private data remains. Root must export only
shareable runs.

**Acceptance scope:**
- **Proves:** this model produced this typed answer to this exact prompt, and the listed native predicates
  passed under the recorded kernel/checker.
- **Does not prove:** the answer's truth, adequacy to intent, novelty to any model, independence, or that
  training helps.

The training target is the applicator reply shape: `{"answer":<value>}`.

## 3. Commands (CLI: `tools/symblic-distill`; every `--out` must not exist; JSON on stdout; refusals exit 2)

```bash
# 1. dataset from explicitly chosen records (a JSON list)
tools/symblic-distill build --records records.json --out dataset.json
# 2. freeze splits (deterministic from the seed; groups never straddle splits)
tools/symblic-distill split --dataset dataset.json --seed smoke-1 --ratios 70,10,20 \
    [--exposures exposures.json] [--group-by source,digit_skeleton] --out splits.json
# 3. pin the local snapshot root prepared (hashes every file; prints files_sha256)
tools/symblic-distill model-manifest --model-dir /models/qwen2.5-0.5b-instruct
# model-spec.json: {"dir": "qwen2.5-0.5b-instruct", "repo_id": "Qwen/Qwen2.5-0.5B-Instruct",
#                   "revision": "7ae557604adf67be50417f59c2c2f167def9a775", "files_sha256": "<from step 3>"}
# 4. freeze the training plan (options are optional; defaults below)
tools/symblic-distill plan-train --dataset dataset.json --splits splits.json \
    --model-spec model-spec.json --options options.json --out plan.json
# 5. training job directory: train/validation rows only, never test rows
tools/symblic-distill prepare-train --dataset dataset.json --splits splits.json --plan plan.json \
    --jobs-root /srv/distill-jobs --name smoke-train --expect-plan-sha256 <plan_sha256>
# 6. print (not run) the worker command for the admitted runner
tools/symblic-distill launch --job-dir /srv/distill-jobs/smoke-train --models-root /models \
    --python /opt/distill-venv/bin/python
#    -> root runs exactly argv with env (shell=False) inside its admitted unit:
#    python symblic/distill/worker.py run --job-dir … --models-root … --backend torch-lora
#    result.json: checkpoint "step-NNNNNNNN" and checkpoint_manifest_sha256
# 7. freeze the evaluation (same held-out prompts and budgets for both arms; greedy)
tools/symblic-distill plan-eval --dataset dataset.json --splits splits.json --plan plan.json \
    --checker schema_and_reference --max-new-tokens 64 --out eval-plan.json
# 8. evaluation job pinned to exactly one trained checkpoint
tools/symblic-distill prepare-eval --eval-plan eval-plan.json --plan plan.json \
    --adapter-manifest-sha256 <checkpoint_manifest_sha256> --jobs-root /srv/distill-jobs --name smoke-eval
tools/symblic-distill launch --job-dir /srv/distill-jobs/smoke-eval --models-root /models \
    --python /opt/distill-venv/bin/python \
    --adapter-dir /srv/distill-jobs/smoke-train/checkpoints/step-NNNNNNNN
#    result.json: every (arm, item) outcome and the comparison
# 9. explicit inference: the trained model answers a NEW caller prompt (and the baseline, for contrast)
tools/symblic-distill launch-infer --plan /srv/distill/plan.json --prompt /srv/distill/prompt.json \
    --out /srv/distill/infer-trained.json --models-root /models --python /opt/distill-venv/bin/python \
    --arm trained --adapter-dir /srv/distill-jobs/smoke-train/checkpoints/step-NNNNNNNN \
    --adapter-manifest-sha256 <checkpoint_manifest_sha256> --max-new-tokens 64 \
    --dataset /srv/distill/dataset.json --splits /srv/distill/splits.json
# 10. re-run the pure comparison from saved outcomes at any time
tools/symblic-distill compare --eval-plan eval-plan.json --outcomes outcomes.json
tools/symblic-distill grpo-status
```

**Training options:** `options.json`, exact ints, with decimals as strings (floats refused). The defaults are:

```json
{"epochs": 1, "max_steps": 1000, "batch_size": 1, "grad_accum": 8, "max_seq_len": 1024, "seed": 1234,
 "checkpoint_every": 50, "lora_r": 8, "lora_alpha": 16, "learning_rate": "0.0002",
 "lora_dropout": "0.05", "weight_decay": "0", "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
 "dtype": "float32", "device": "cpu"}
```

A smoke run might use `{"max_steps": 20, "grad_accum": 2, "checkpoint_every": 5, "max_seq_len": 512}`.

- `float16` on CPU is refused.
- **One step** is `grad_accum` micro-batches of `batch_size` items. The micro-batch order per epoch is
  `sha256(seed:epoch:item_id)`, so a resumed run continues the same schedule.

**Trained-adapter inference:** the evaluation job runs both arms:
- `baseline` is the pinned base snapshot;
- `trained` is the same snapshot plus `PeftModel.from_pretrained(base, checkpoint, is_trainable=False)`.

Both arms use the exact frozen test prompts (system + user through the tokenizer's chat template), greedy
decoding and the same `max_new_tokens`. The pinned adapter must verify:
- its MANIFEST digest equals `adapter_manifest_sha256`;
- every file hash matches;
- its plan and model identity match.

**Explicit inference (`infer`):** answers ONE caller-supplied prompt.
- **Input:** `prompt.json` = `{"version": 1, "system": "...", "user": "...", "answer_type"?: "integer|boolean|string|label",
  "labels"?: [...]}`.
- **Arms:** `--arm trained` loads the exact base snapshot plus the pinned, verified adapter (same checks as
  above; adapter pin required). `--arm baseline` loads the base only and refuses an adapter.
- **Receipt:** written once to `--out` (never overwritten). It binds:
  - the plan hash;
  - the model repo, revision and files hash;
  - the adapter's MANIFEST digest, step, identity and file hashes;
  - backend identity and package versions;
  - options (greedy, `max_new_tokens`, dtype, device, seed);
  - the exact prompt and its hash;
  - the output text and its hash;
  - an optional structural check (when `answer_type` is given);
  - `receipt_sha256`.
- **Dataset overlap:** with `--dataset/--splits`, the receipt lists any dataset item whose prompt equals this
  one (exactly, or after normalization) and its split. `novelty` stays `not_established` either way.
- **Claims:** `quality: not_established`, `native_verification: not_performed` (a free prompt has no
  contract), `promotion: never_automatic`.

There is no promotion. An adapter is never merged, converted to GGUF, installed into Ollama or used by
Symblic routes by this code.

## 4. Splits, leakage and exposure

Items are joined into groups (union-find), and a whole group goes to one split. Groups always join on:
- the same prompt hash;
- the same normalized prompt (NFKC, casefold, collapsed whitespace);
- the same caller `group_key`;
- a declared exposure hash that equals another item's prompt hash or exposure hash.

Optional `group_by`, both on by default and recorded in the manifest:
- **`source`:** the same program source. All asks of one run program stay together.
- **`digit_skeleton`:** prompts identical after replacing digit runs. Templated items such as "What is 3
  plus 3?" and "What is 5 plus 5?" stay together.

These are conservative. A dataset from one program or one template cannot be split (`empty_test_split`).
Turning a grouping off is a deliberate, recorded choice (`split --group-by source`, or `--group-by ''`). These are text heuristics, not paraphrase or semantic-duplicate detection.

**Exposure:** an `exposures.json` row is `{"item_id", "kind":
"prompt_or_feedback|prior_training|prior_evaluation|published", "evidence_sha256"}`. It makes that item's
whole group test-ineligible.

**Novelty:** `novelty` is always `not_established`. Disjoint hashes say nothing about pretraining data.

**What refuses:**
- `verify_splits` recomputes the manifest from the dataset and refuses any change (`splits_changed`) or
  overlap;
- `training_job` rebuilds the train/validation IDs and refuses a test item (`test_reuse_as_training`);
- an evaluation records `prior_test_uses`, and `heldout_status` becomes `reused` when it is above 0.
  Repinning cannot make a reused set fresh.

## 5. Worker, state and recovery

- **Inert on import.** `run()` takes an exclusive non-blocking `flock` on `JOB/lock`; a second worker gets
  `job_busy`. Paths must not contain symlinks. Every write is temporary file → fsync → rename → directory
  fsync.
- **State:**
  - `state.json` keeps the status and an append-only history (bounded to 200 events) of attempts, failures,
    interruptions and quarantines.
  - A torn `state.json` (`torn_state`) or an unknown version (`unknown_state`) refuses without writing.
  - A `running` state found at start is recorded as an interrupted attempt with an unknown outcome.
- **Checkpoints:** `checkpoints/step-NNNNNNNN/` holds the backend's files (adapter, `optimizer.pt` with the
  optimizer and CPU RNG state) and a `MANIFEST.json`, written last, with every file's sha256 and
  identity = {job, plan, model files, backend identity}.
- **Resume:**
  - It uses the highest checkpoint that verifies.
  - Torn `.tmp-*` directories and checkpoints that fail verification are moved to `checkpoints/quarantine/`
    and kept.
  - A checkpoint from another job, plan, model or backend refuses (`checkpoint_identity_mismatch`); it is
    never deleted or silently restarted.
- **Failures:** a missing package, a version mismatch, no CUDA, a missing model, a manifest mismatch or a
  load failure leaves a `failed` status with its code, `completed: false` and the retained state. Nothing
  reports trained.
- **Evaluation resume:** it keeps every recorded outcome. An interrupted in-flight item is re-run with its
  attempt count incremented. A generation exception is an `error` outcome; an arm whose model cannot load is
  `unavailable` for every pending item.
- **Result:** `result.json` is written once. A re-run returns it (and repairs a state left `running` by a
  crash after the write).

## 6. Comparison (pure, `compare`)

- **Denominator:** the frozen test set. Every planned (arm, item) counts: `passed`, `failed`, `error`,
  `unavailable`, `interrupted`, or `missing` when no row exists. Duplicate or unplanned rows refuse.
- **Pass rates:** exact rationals, with a 95% Wilson interval.
- **Paired discordance:** baseline-only versus trained-only passes, with an exact two-sided binomial
  (McNemar) p-value.
- **Verdict:** `comparison` is `difference_observed_under_declared_checker` or `no_difference_observed`
  only when both arms are complete; otherwise it is `not_established`.
- **Checkers** (frozen in the evaluation plan, with an explicit `scope`):
  - `schema` (`structural_answer_schema`): the reply is exactly one JSON object `{"answer": v}` with the
    declared type or label.
  - `schema_and_reference` (`…_and_reference_hash_agreement`): also requires equality with the stored
    accepted (teacher) answer. Each outcome records `reference_match`. This is **agreement**, never native
    verification: that answer was itself only predicate-checked.
  - `schema_and_native` (`…_and_native_encoded_predicates`): a pinned trusted native checker (§6a) re-runs the
    item's own predicates on the generated answer. Each outcome records `native` = `{ran, passed, scope,
    kernel_id, receipts, checker_module_sha256, checker_id}`. Items carry a contract, never the stored answer.

  The p-value is descriptive for this frozen item set; no generalization, causal or quality claim is made.

## 6a. Native checker registration (root; trusted code only)

The fixed module `symblic/distill/checkers.py` registers `symblic-native-scalar-v1` for the bounded subset in §11. It requires an explicitly staged trusted private contract bundle; missing, changed or unsupported contracts refuse. The module path is fixed; no CLI or config option can name another module or executable.

```python
CHECKERS = {'symblic-native-scalar-v1': Factory}      # Factory() -> checker
# checker.identity() -> {'id', 'version', 'kernel_id', 'contract_version', 'source_sha256'}
# checker.check(contract, answer) -> {'passed': bool, 'scope': 'encoded_predicate', 'kernel_id': str,
#                                     'receipts': ['<sha256>', ...]}
```

`contract` = `{source_sha256, statement_sha256, kernel_id, checker, predicate_sha256s, answer_type,
labels?}`. It holds no accepted answer. Root's checker resolves the original program from its own trusted
storage and runs the native type coercion and those predicates on `answer` (for example via `symblic.kernel.run`
on the original source with the answer bound), returning only the predicate receipts. Then:

```bash
tools/symblic-distill checker-identity --name symblic-native-scalar-v1 > checker-pin.json   # module sha256 + identity
tools/symblic-distill plan-eval ... --checker schema_and_native --native-checker checker-pin.json --out eval-plan.json
```

At evaluation, the worker re-hashes the module and compares it and the checker identity with the pin.

| situation | result |
|---|---|
| module missing, source changed, name unknown or identity changed | the job **fails** before any generation (`checker_unavailable`, `checker_source_mismatch`, `checker_identity_mismatch`); nothing passes |
| schema-invalid reply | `failed` (checker not run) |
| item kernel ≠ checker kernel | `unavailable` |
| checker exception or malformed receipt | `error` |
| receipt with `passed: true` | the only way to pass |

The module is executed from its exact hashed bytes, with the same trust as importing repository code.

## 7. Verifiable reward / GRPO: unsupported

`plan-train --method grpo` refuses with `grpo_unsupported`; `grpo-status` lists the gap:
- an in-process native-checker reward pinned to kernel/checker identity, which never uses held-out or
  reference answers;
- recorded group sampling;
- a verified policy-gradient update with a reference model, a KL term and resume semantics;
- generation throughput that needs admitted GPU placement.

This remains outstanding work for root; the operator's broader training request is not complete.

## 8. Integration status and remaining work

The local exporter, private dataset preparation, pinned environment/model, admitted CPU run, checkpointed training, comparison and explicit trained-adapter inference have executed (§10). The worker is not automatically dispatched, installed as an Ollama model, promoted, or connected to the dashboard's model selector.

Remaining: expand the native checker beyond its closed pure scalar subset (§11), implement verifiable-reward/GRPO, and collect a substantially larger independently grouped evaluation before making accuracy claims. `schema_and_reference` always reports agreement only, independently of whether the separate native checker is registered.

## 9. Repeatable admitted CPU run recipe (example paths)

Assumptions: the private job root is `/srv/distill` (gitignored, never the host). The snapshot is
`/models/qwen2.5-0.5b-instruct` (Qwen/Qwen2.5-0.5B-Instruct @ `7ae557604adf67be50417f59c2c2f167def9a775`),
and the venv is `/opt/distill-venv` (CPython 3.12.14, torch 2.14.1+cpu, transformers 5.18.0, peft 0.21.2,
safetensors 0.8.0, tokenizers 0.23.2). `records.json` is the exporter's output. Use as few as about 20
records, as long as the split leaves ≥1 test item. Every `--out` must be new.

```bash
cd <repo> && S=tools/symblic-distill && R=/srv/distill && PY=/opt/distill-venv/bin/python
mkdir -p -m 700 $R/jobs
$S build --records $R/records.json --out $R/dataset.json
$S split --dataset $R/dataset.json --seed smoke-20261006 --ratios 70,10,20 --out $R/splits.json
#   If grouping leaves an empty split, collect more independent task families.
#   Keep the source/digit/family grouping; do not split near-duplicates to manufacture a heldout set.
$S model-manifest --model-dir /models/qwen2.5-0.5b-instruct          # -> files_sha256
cat > $R/model-spec.json <<'JSON'
{"dir": "qwen2.5-0.5b-instruct", "repo_id": "Qwen/Qwen2.5-0.5B-Instruct",
 "revision": "7ae557604adf67be50417f59c2c2f167def9a775", "files_sha256": "<files_sha256>"}
JSON
cat > $R/options.json <<'JSON'
{"max_steps": 20, "batch_size": 1, "grad_accum": 2, "checkpoint_every": 5, "max_seq_len": 512,
 "learning_rate": "0.0002", "lora_r": 8, "lora_alpha": 16, "dtype": "float32", "device": "cpu"}
JSON
$S plan-train --dataset $R/dataset.json --splits $R/splits.json --model-spec $R/model-spec.json \
    --options $R/options.json --out $R/plan.json                      # -> plan_sha256
$S prepare-train --dataset $R/dataset.json --splits $R/splits.json --plan $R/plan.json \
    --jobs-root $R/jobs --name smoke-train --expect-plan-sha256 <plan_sha256>
$S launch --job-dir $R/jobs/smoke-train --models-root /models --python $PY > $R/launch-train.json
#   ROOT: run launch-train.json argv with its env (shell=False) in the admitted node-i unit. Re-running the same
#   argv after an interruption resumes from the last verified checkpoint.
#   -> $R/jobs/smoke-train/result.json: checkpoint step-00000020, checkpoint_manifest_sha256
$S plan-eval --dataset $R/dataset.json --splits $R/splits.json --plan $R/plan.json \
    --checker schema_and_reference --max-new-tokens 64 --out $R/eval-plan.json
$S prepare-eval --eval-plan $R/eval-plan.json --plan $R/plan.json \
    --adapter-manifest-sha256 <checkpoint_manifest_sha256> --jobs-root $R/jobs --name smoke-eval
$S launch --job-dir $R/jobs/smoke-eval --models-root /models --python $PY \
    --adapter-dir $R/jobs/smoke-train/checkpoints/step-00000020 > $R/launch-eval.json
#   ROOT: run it -> $R/jobs/smoke-eval/result.json (all outcomes + comparison; reference AGREEMENT only)
cat > $R/prompt.json <<'JSON'
{"version": 1, "system": "<the same system text the records use>", "user": "<a new prompt>",
 "answer_type": "integer"}
JSON
$S launch-infer --plan $R/plan.json --prompt $R/prompt.json --out $R/infer-trained.json --models-root /models \
    --python $PY --arm trained --max-new-tokens 64 --dataset $R/dataset.json --splits $R/splits.json \
    --adapter-dir $R/jobs/smoke-train/checkpoints/step-00000020 \
    --adapter-manifest-sha256 <checkpoint_manifest_sha256> > $R/launch-infer-trained.json
$S launch-infer --plan $R/plan.json --prompt $R/prompt.json --out $R/infer-baseline.json --models-root /models \
    --python $PY --arm baseline --max-new-tokens 64 --dataset $R/dataset.json --splits $R/splits.json \
    > $R/launch-infer-baseline.json
#   ROOT: run both -> $R/infer-trained.json / infer-baseline.json (output text + full identity receipt)
```

This recipe illustrates configurable parameters. The completed local pilot used four steps and a 1024-token training limit; its measured timings are in §10. Other sizes and configurations require their own admitted resource measurement.

**Training context limit:** when prompt plus target exceeds `max_seq_len`, the backend truncates the prompt from the left while retaining the entire target. That can remove instructions or needed context; this is not lossless training of the original capsule. Select a sufficient limit and inspect token lengths for your data. Inference uses the supplied prompt, subject to the model’s context capacity.

**What a successful smoke run shows:**
- **Shows:** the pipeline executes end to end with real libraries, the adapter loads, and the trained model
  answers a new prompt.
- **Does not show:** that quality improved, unless a complete frozen comparison says so under its declared
  checker scope. Even then, it is only for that item set.


## 10. Local accepted-run exporter and actual pilot

`tools/symblic-distill export-run --run-dir /private/symblic/runs/RUN_ID --group-key TASK_FAMILY --out /private/records.json` reconstructs the exact system/user prompts through an isolated native lock replay. Use `--lock-file /private/RUN_ID.lock.json` when the lock is retained separately, and `--repo /path/to/pinned/native/repo` when running a staged candidate. It requires a finished state matching that lock, zero fresh model calls, unchanged native evidence, observed pinned model identity, an unambiguous scalar answer, and a passed native predicate that references that exact answer hash. It excludes oracle/peer/feedback-exposed observations and unsupported record/list/fraction answers. The stdout receipt pins the input files, lock, replay fingerprint, accepted count and rejected reasons. Save it privately. Original run stores are read only; no cloud transport is involved. Related runs must use the same caller-supplied task family; keep default source and digit grouping at split time.

A local pilot executed on 2026-10-06 UTC, on an admitted node-i CPU job with 2 CPUs and 8 GiB RAM. The pinned Qwen2.5-0.5B snapshot and documented package versions trained a rank-4 LoRA adapter for four optimizer steps. The full training/evaluation/inference job finished in 111.3 seconds with 4.5 GiB peak memory. No base weights were replaced or adapter promoted.

The source data came from four actual accepted Symblic runs; all four native replays reproduced their fingerprints with zero fresh model calls. Twenty-two eligible scalar observations produced 21 unique dataset items (one duplicate identity rejected). Three task families remained intact, yielding 9 training, 9 validation, and 3 test items. The initial 60/20/20 requested allocation had no validation items because whole groups would not fit; before any training/evaluation, ratios were adjusted to 40/43/17 to reserve one intact group per split. No grouping was weakened and no split was selected using model scores.

Under the frozen reference-agreement checker, the baseline matched 0/3 heldout answers and the adapter matched 1/3. All baseline completions failed the strict JSON schema under the 48-token budget; all three trained completions were valid JSON, two with wrong answers. This tiny result does not establish a general accuracy gain (paired exact p=1), novelty, or native verification of the generated answers. A separate falling-height question also failed: both arms answered 135, while direct evaluation gives 50. Keep that failure visible. Training capability and checkpointed inference are functional; reliable reasoning is not established by this pilot.

A bounded native scalar checker is now implemented (§11). The earlier reference-agreement measurements remain unchanged and must not be called native predicate verification. GRPO remains unsupported.

A subsequent admitted verification compared checkpoint steps 1 and 4: all 192 adapter tensors changed, maximum absolute tensor delta 0.0006021472. Reopening the completed training job returned the same result without invoking a backend; checkpoint digest and base-model file manifest were unchanged. Both baseline and trained adapters answered a separate `3 + 4` prompt with integer 7. That confirms useful basic inference, not broad reasoning accuracy.


## 11. Fixed native scalar checker and durable trusted contracts

The `symblic-native-scalar-v1` registry implementation evaluates the supplied answer with the native type coercer and native `Kernel`, using the original predicate AST. It contains no stored accepted answer and does not compare against a reference answer. A fresh isolated Python process verifies the frozen runtime source hashes, loaded-module identities and kernel ID. It parses the original source independently and requires the ask name/type and every predicate AST/hash/line to match that source. Predicates have a 100,000-step budget. A constant `-I -B` bootstrap executes the worker-loader’s exact approved checker bytes, preserving `__file__`, with scrubbed environment, child-only 5-second CPU / 512-MiB address-space / 256-KiB file-output limits and a 15-second wall timeout. Input is bounded to 16 MiB; parent output reads are bounded to 64 KiB. Parent limits are unchanged. Changed on-disk checker bytes refuse; child receipts bind the actual captured checker SHA. No applicator or effect runner is instantiated.

Supported: top-level asks with top-level checks of integer/boolean/string/label answers with pure literal/arithmetic/comparison/collection predicates, including bounded comprehensions and calls to `abs`, `sum`, `product`, `min`, `max`, `len`, or `count`. Context bindings must be exact, created before the ask, have closed recorded dependency provenance, and exclude the target answer. Nested or conditional checks, queries, custom functions, external adapters, unresolved/conditional dependencies, post-answer context, changed source or kernel, and unknown contracts refuse; they never pass through reference agreement. A predicate may admit several answers: tests demonstrate that both 3 and 100 pass `candidate > 2`, while 2 and wrong JSON types fail.

Runtime snapshots retain the broad `symblic*.py` source hashes and include every dependency in
`symblic.kernel.execution_pins.PYTHON_FILES`, including registered sources with other prefixes. Loaded-code identity
checks use that explicit semantic registry: importing an inert API wrapper does not register it as a
semantic module, while its disk bytes remain pinned. Missing registered source pins refuse as
`incomplete_native_runtime`; retain old bundles and their original checker/runtime rather than relabeling them.

Export a bundle from explicit trusted run/lock paths and the already verified dataset:

```bash
tools/symblic-distill export-contracts --repo /private/frozen-native-runtime \
  --runs /private/run-list.json --dataset /private/dataset.json --out /private/native-contracts.json
```

`run-list.json` is an array of `{"run_dir":"/private/run","lock_file":"/private/run.lock.json"}` entries (`lock_file` is optional when the run directory holds `run.lock.json`). Export repeats strict native lock replay with zero fresh calls and captures the actual predicate inputs. It reports unsupported items explicitly. The bundle includes the original source, closed predicate context, source/runtime/checker identities and replay receipts; keep it private and never send it to a model or cloud task.

After reviewing the bundle, stage it as a regular private file at `~/.local/state/symblic-distill/native-contracts.json`, then run `tools/symblic-distill checker-identity --name symblic-native-scalar-v1 > /private/checker-pin.json`. The pin binds both module bytes and bundle/runtime identity. Use that pin with `plan-eval --checker schema_and_native --native-checker /private/checker-pin.json`. Changing the bundle requires a new pin and evaluation plan. Retain old frozen runtimes for old contracts; a new kernel must never silently relabel old evidence.

The actual pilot bundle freezes kernel `59c87dc8a638abce` from the retained pre-D17 runtime. It supports 6 of the 21 unique dataset items. Rechecking the six original accepted teacher outputs produced six native passes; adding one to each answer produced six native failures. This is reused teacher evidence and checker validation, **not** student accuracy evaluation. The three prior heldout vorticity items have nonclosed/post-answer context and are refused by this version, so no native improvement score is claimed for that heldout set. The prior 0/3 versus 1/3 reference result and failed physics example remain unchanged.

For an explicit local check of a recorded scalar (no model call):

```bash
tools/symblic-distill native-check --dataset /private/dataset.json --item-id ITEM_SHA256 \
  --answer-json '3' --native-checker /private/checker-pin.json
```

This registration is local to the root machine and its retained pre-D17 runtime. It is not deployed on node-i: the training worker uses a different Python installation and does not have this retained runtime path. Do not claim native generation evaluation on node-i from these local checks. Export refuses state/lock/call files changed across replay or reread; it pins the exact bytes parsed. The statement SHA remains the replay-validated contextual observation/capsule identity, not a raw ask-AST digest.
