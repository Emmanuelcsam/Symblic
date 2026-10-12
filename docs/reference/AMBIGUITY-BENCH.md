# Ambiguous-request benchmark

This suite measures a small, specified part of the perspective gap: recognizing
when a request leaves an essential field unresolved, selecting that field for
clarification, and producing the stipulated specification after the operator answers.
It is available through `symblic/bench/bench.py --suite ambiguity` and the separate
`symblic/bench/ambiguity.py` runner. It does not modify the language or deploy an API.

## Data and interpretation

The [dataset contract](../../symblic/bench/data/ambiguity-v1.md) describes 42 synthetic cases:
14 scenario families, seven domains, 21 development cases and 21 held-out cases.
Families do not cross splits. Each family has two identical public requests with
different private operator intentions, plus an explicit clear control. Field positions
are counterbalanced. Labels were independently reviewed with finite reference
calculations. They are author-stipulated intentions, not discovered external truth.

The held-out scenarios were authored separately from the runner, and their gold
answers were withheld from the coordinator's prompt development. They are published
fixtures, not a claim of secrecy or absence from a model's training data. Do not
tune prompts on held-out performance and continue calling the same split unseen.
Every ambiguous fixture currently has one missing field; wider conversations,
conflicting requirements and multi-round clarification need separate datasets.

The model sees the request, context and output-field definitions. It returns
`{action, values, questions}`. Questions are field names, not free-form question
text. The scorer checks exact JSON types, complete field sets and exact stipulated
values. It does not judge the quality of a natural-language question or certify
that a real person's intent has been captured. This is a protocol benchmark, not
an end-to-end test of the Interpreter's UI, analysis or compilation path.

## Conditions and endpoints

| Condition | Information | Calls per cell | Success endpoint |
|---|---|---:|---|
| `direct` | Public request and response instructions | 1 | Exact clear answer, or exactly the necessary clarification fields |
| `typed` | Same public information through a typed Symblic ask | 1 | Same initial interpretation endpoint |
| `clarify` | Typed initial response; scripted operator answers only requested unresolved fields | At most 2 | Exact final specification with every necessary field resolved |
| `oracle_direct` | Public request plus all scripted operator answers upfront, direct JSON response | 1 | Exact supported final specification |

`direct` already requests structured JSON; it is not an unconstrained prose
baseline. The typed arm uses the kernel's schema machinery, but both arms score
the same strict original inner JSON record: canonicalization cannot hide extra
keys or duplicate keys. The standard Symblic `answer` envelope is accepted in
either arm; its reasoning metadata is not scored. If a provider returns only
already-decoded JSON, duplicate keys lost upstream cannot be detected; records
state whether original text was available. Neither arm receives gold predicates or correctness
feedback for repairing its answer. Payloads enter Symblic as data, never as source.

An answer can coincidentally match a hidden operator intention and still be an
unsupported commitment. That is recorded separately and does not count as success
before clarification. Asking unnecessary questions fails the clear controls.
The two initial-interpretation arms and two final-specification arms have different
endpoints. Clarification also changes information and cost: a higher final score
does not isolate an effect of syntax or prove that a smaller model became smarter.

## Running

Use an explicit applicator and a fresh output folder. No provider is created or
called by a dry run or a report-only command. For example, this creates assignments
for one complete development family, all four conditions, without model calls:

```sh
python3 symblic/bench/bench.py --suite ambiguity \
  --ambiguity-apps ollama:qwen3:4b-instruct --ambiguity-split dev \
  --quick --dry-run --out ~/.local/state/symblic-ambiguity/dev-v1
```

Before an actual experiment, verify the named model and admitted worker node capacity
using the existing fleet workflow. Then repeat the command with `--resume` instead
of `--dry-run`. The suite invokes providers only through `symblic.providers.applicators`, with
tools disabled, its thermal guard enabled and `--avoid node-h` by default.
Orchestration is sequential; model work uses the existing admitted placement path.
Effort is fixed to low; other effort or non-unit weight suffixes are refused.
This bounded protocol accepts individual model applicators, not councils, a host model service or
the kernel as an applicator. A future council condition needs separate internal
call and cost accounting; existing host-executor council support is unchanged.
No email, calendar, browsing, shell or world-changing capability is supplied.

A full split assigns 84 cells and at most 105 provider calls **per applicator**.
A quick split selects a complete scenario family before expanding conditions and
applicators; it does not truncate the expanded matrix. Use
`--ambiguity-conditions direct,typed` to select a smaller explicit comparison.
Freeze the protocol and select the applicators before assigning `--ambiguity-split
heldout` in a different output folder. This implementation ships no real-model
performance claim; its regression results use fake providers.

```sh
python3 symblic/bench/bench.py --suite ambiguity --report-only \
  --out ~/.local/state/symblic-ambiguity/dev-v1
```

## Records and recovery

`ambiguity-manifest.json` records every assigned cell, dataset digest, split,
applicator, condition, call limit, kernel identity and relevant module hashes.
Changing those inputs requires a new folder. Local integrity hashes detect
accidental damage; they are not signatures or protection against an author who
rewrites both data and hashes.

`ambiguity-cells/` holds one atomic, fsynced record per cell. Each provider-call
intent is persisted before dispatch, and each returned response afterwards.
Completed failures stay completed failures. A process interrupted after an intent
leaves an uncertain cell, which `--resume` never redispatches automatically.
Resuming a folder without its assignment manifest is refused before any dispatch.
`--retry` is refused for this suite. An explicitly new experiment belongs in a new
folder, with its previous exposure disclosed; it must not replace first attempts.

`ambiguity-summary.json` and `report.md` keep all assigned cells in the denominator,
including failed, pending, uncertain and damaged records. They report initial
decisions, exact supported finals, unsupported commitments, clear controls, costs,
and family counts. Provider failures are not silently converted into model answers.
Paired summaries compare the same endpoint and show shared non-successes and the
cases only one method gets right. Cases with no attempt by one arm are separately
visible; the paired observed denominator includes only jointly attempted cases.
Twins and scenario families are dependent observations. Provider or method labels
do not establish independent errors, and this suite makes no population confidence
or universal semantic-accuracy claim.

Tests: `tests/bench/test_symblic_bench_ambiguity.py` and
`tests/bench/test_symblic_bench_ambiguity_cli.py`; all stores temporary, providers fake.
