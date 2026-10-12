# Benchmark statistics reinforcement: bounded first pass

This is a read-only source audit of `symblic/bench/bench.py` (`Bench`, suite cell builders,
`_base`, `_prose_correct`, `short_by`, `report`, `main`) against SPEC §§3–5, 8 and
PRIOR-ART's agreement/council limits. It includes an independent stdlib-only helper,
`tools/scripts/symblic_reinforcement_stats.py`. Core runner, UI and API adoption remain
with c6d9/2272. No benchmark stores were read, no models called, and no new performance
measurements are claimed. Examples and tests use synthetic data only.

## Source findings and concrete adoption priorities

| Priority | Current behavior | Consequence and proposed correction |
|---|---|---|
| P0 | `report` knows only supplied rows; `Bench.done` overwrites cell outcomes, and transient failed rows can disappear during resume. | Entirely missing cells/conditions and prior failures cannot be recovered from the report. Freeze a planned manifest **before dispatch**, including actual `--quick` truncation and exclusions; preserve raw attempts separately. Report scheduled, missing and failed counts. |
| P0 | Identity unanimity uses only successful rows with hashes and at least two survivors. | Two agreeing survivors from a larger failed panel count as unanimous. Label survivor unanimity and complete scheduled-panel unanimity separately; show coverage alongside both. |
| P0 | `pct` applies Wilson intervals to pairwise identity, pooled correctness and repeated shapes. | Agent pairs overlap in agents and items; repeats share item/model, and generated examples share templates. These are not independent Bernoulli observations. Remove these intervals or justify a cluster-aware design. The helper emits descriptive counts/rates only. |
| P0 | Arithmetic/logic matching intersects item sets of observed `(condition, by)` keys; failures count as “finished”, entirely absent lanes are invisible, and the matched table appears only for unequal sets. | Use manifest lanes and show complete, valid, scored matches even when item sets have equal size. Also show exclusions and all-scheduled verified success so failure selection remains visible. |
| P1 | `short_by` reduces multi-member councils to member count/model or “mixed”. | Distinct node panels and mixed model compositions can merge. Keep exact `by` strings; record model labels and node placement explicitly. Five nodes running one model are one distinct model label, not five independent models. |
| P1 | `_prose_correct` uses token/subsequence/substring heuristics: a list may contain extra answers, dict values need not match keys, and a number can appear in an otherwise wrong response. | Helper correctness is **scorer-labelled**, not an independently validated truth judgment. Audit adjudication fixtures before making accuracy claims. Use an explicit answer parser and typed comparison for a content endpoint; retain normalized text identity as its own endpoint. |
| P1 | Identity prose hashes normalized text; typed asks hash canonical typed answers. Flower hashes drawing bytes. | These are different equivalence relations. Report each endpoint separately; improved identity can reflect canonicalization rather than improved reasoning. Do not compare hash strings across conditions or infer correctness from identity. |
| P1 | Symblic suite rows often omit actual node; council rows omit per-member outcomes. `ok` sometimes means a binding exists rather than the run completed. | Emit actual placement/member provenance and a defined validity endpoint. The helper excludes error-flagged outcomes even with `ok=true`; missing node stays unknown. Aggregate council rows cannot measure member independence or internal failed samples. |
| P2 | `_base` drops arithmetic `noop`, so built-in producers do not populate the report's irrelevant-sentence subset. Arithmetic report also silently excludes legacy item IDs. | Carry planned template/no-op/generator-version metadata and explicitly report exclusions. The helper does not filter legacy IDs or fabricate those strata. |
| P2 | Replay reuses answered calls; `--quick` slices the combined ordered cell list to 40. | Replayed calls are not fresh replications. Quick mode may cover only an early suite/applicator subset. Record replay status and exact scheduled list; do not describe quick mode as a balanced all-suite benchmark. |

These are findings from this checkout's source, not measured effect sizes or claims
about outcomes of any running benchmark.

## Manifest and CLI contract

The CLI reads only the two explicitly named local files and prints JSON to stdout:

```sh
python3 tools/scripts/symblic_reinforcement_stats.py \
  --manifest /path/to/offline/manifest.json \
  --rows /path/to/offline/selected-results.jsonl > /path/to/offline/analysis.json
```

There is no default store, runner import, network, worker, or service operation.
Malformed input exits 2 with `analysis failed:` on stderr; no partial report is printed.
A manifest is a JSON object with integer `schema_version: 1` and a nonempty `cells` list:

```json
{
  "schema_version": 1,
  "cells": [
    {"cell":"identity|spider|prose|ollama:m@node-a",
     "suite":"identity", "item":"spider", "condition":"prose",
     "by":"ollama:m@node-a", "models":["ollama:m"], "node":"node-a"},
    {"cell":"identity|spider|symblic|ollama:m@node-a",
     "suite":"identity", "item":"spider", "condition":"symblic",
     "by":"ollama:m@node-a", "models":["ollama:m"], "node":"node-a"}
  ]
}
```

Required fields per cell: nonempty strings `cell`, `suite`, `item`, `condition`, `by`,
and a nonempty list `models` of distinct exact model/version labels. Declare council
member model labels explicitly; repeated samples of one model do not add labels.
Unknown versions should have an explicit unresolved label and prevent claims about
version-specific behavior. `node` and `repeat` are optional nonempty strings; omitted
repeat is `"0"`. Use repeats for shape `r0`, `r1`, etc. Keep resolved node names when
known; omitted placement means unknown, not an inferred worker node. The manifest's model
labels describe the plan, not independently verified serving identities.

`cell` has four nonempty pipe-delimited components, with its first two equal to
`suite` and `item`. Its last two are runner-specific opaque scheduling tokens: logic
uses `datalog` in the ID but `symblic-datalog` in the row; shapes use `r0` instead of
`shape`; councils use `council` instead of their full member string. The manifest must
supply the actual row's condition and full `by`; do not reconstruct these from tokens.
Duplicate IDs or duplicate logical `(suite,item,condition,by,node,repeat)` cells fail.
Unexpected outcome IDs and conflicting outcome metadata fail rather than disappearing.

Each outcome is a JSONL object with `cell`, boolean `ok`, optional boolean/null
`correct`, optional nonempty string/null `hash`, and optional string `node`.
Existing extra benchmark fields are permitted. Supplied `suite/item/condition/by/repeat`
must match the manifest; known planned and observed nodes must match. Runner exception
rows with only `cell/ok/error` are supported through manifest metadata. Truth is not
recomputed: the runner's validated/scored boolean is the endpoint. Nonempty `error`
invalidates an otherwise `ok=true` row for this conservative report.

Select exactly one outcome per cell **outside this helper** according to a frozen
retry policy (e.g. first scheduled attempt versus final retry-inclusive result).
Differing duplicate rows, even differing only in timestamps, fail visibly. Exact
JSON-equivalent duplicates are collapsed, counted and never inflate denominators.
Raw append-only retry logs need deliberate preprocessing; the helper will not silently
choose last-write-wins. Its `failed_or_error` counts failed selected cell attempts,
not hidden provider calls or historical retry attempts. Preserve/report those costs
and counts separately when the coordinator adds attempt provenance.

## Output and interpretation

- `coverage` shows scheduled/observed/missing/failed/error-flagged/valid counts.
  `verified_correct_over_scheduled` includes absent, invalid and unscored cells in
  its denominator, as lack of verified success; it does not assert they gave wrong
  answers. `correct_over_valid_scored` is conditional correctness with explicit
  unknown-score count. Zero denominators yield `null`, never a fabricated zero.
- `identity_counts` lists distinct exact model labels, full applicator count, observed
  node labels and `(suite,item)` clusters. Independent model/item counts are `null`:
  distinct IDs cannot establish statistical independence. `cell_identities` retains
  every full strategy and known planned/observed node without council shortening.
- `agreement_by_item` groups `(suite,item,condition,repeat)`, using only valid hashes.
  It reports fingerprint coverage, descriptive pair identity, survivor unanimity,
  complete-panel unanimity and shared-wrong unanimity among hashed survivors.
  A valid answer without a hash cannot complete a panel. A single responder cannot
  be unanimous. Shared wrong flags require every hashed survivor's score to be false;
  unknown scores do not establish a shared error. Repeats are separated here.
- `matched_comparisons` constructs every planned lane `(condition,by,node,repeat)`
  within each suite and uses only items scheduled in **every** lane with a valid,
  boolean-scored selected outcome in every lane. It reports all exclusions, matched
  accuracy and paired right-minus-left correctness differences with aligned item
  scores. All lanes remain visible even if a condition is completely missing.
  Repeats remain explicit lanes, not extra independent items. The all-lane intersection
  can be small; select a predeclared comparison-specific manifest/snapshot when only
  a particular contrast is scientifically meaningful. Do not choose the subset after
  observing scores. Shape style comparisons need a predeclared common object/item
  alignment; this helper does not guess that different item IDs are the same object.

No CI, p-value, chance-adjusted agreement, independence estimate or optional bootstrap
is implemented. This is intentional: fixed handpicked identity questions and shared
arithmetic templates do not establish an iid item population. A future justified
bootstrap would resample whole matched item clusters, preserving all lanes/repeats,
use an explicit seed and bounded draw count, and consider template/object clustering
when appropriate. Item bootstrapping alone does not capture provider drift or shared
model errors; completeness conditioning does not repair nonrandom missingness.

Kim et al.'s original [Correlated Errors in Large Language Models](https://arxiv.org/abs/2506.07962)
(ICML 2025; abstract verified 2026-10-02) reports substantial error correlation across
models, including agreement when both err. This supports caution about independence
and agreement-as-truth; it does not quantify correlation for this Symblic workload.
The choice of descriptive-only reporting is this patch's methodological proposal.

## Coordinator adoption checklist and validation

Freeze the actual schedule after suite filters/quick truncation; include model/version,
condition, repeat, placement, generator seed/version and comparison alignment. Keep
all attempt receipts separately. Decide the retry endpoint and audit the truth scorer.
Then call the helper on a local selected-outcome snapshot and review missing/error and
unknown fields before interpreting matched improvements. Do not infer council sample
counts or reliability from aggregate `agreement` metadata. No runner integration is
required to review this patch.

Focused synthetic checks:
`python3 -m unittest discover -s tests -p test_symblic_reinforcement_stats.py`.
They cover survivor-only unanimity, shared wrong answers, missing/error/unscored cells,
incomplete and entirely absent condition matrices, duplicates, invalid manifests and
outcomes, node/model/repeat identities, deterministic ordering, and the CLI using temp
files. These validate accounting, not any model's reasoning performance.

Patch validation on the isolated reinforcement branch: 10 unittest tests passed;
`bin/devcheck` passed (one selected module, one worker; 10 tests and 20 subtests).
Compile, built-in rules, secret screening and page checks passed. The tool reported
ruff, ast-grep, shellcheck and gitleaks absent, so their respective checks were skipped;
no missing tools were installed. `git diff --check` and CLI `--help` also passed.
