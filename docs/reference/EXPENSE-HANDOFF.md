# A source-bound expense handoff between agents

This executable example strengthens the expense demonstration in
[the token and architecture report](SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md).
Checking eight rows and a $60 hotel excess cannot establish that the rows,
amounts, categories, or source occurrences are right. Six invented uncapped
charges plus two $280 hotel rows pass those predicates. The focused regression
keeps that counterexample.

The replacement uses existing language statements, source contracts, the native
runner and admitted Applicators. There is no new expense kernel, model template,
provider route, or expected-answer lookup. This is an integration demonstration,
not evidence that an LLM is necessary for this small parsing task or that the
extra requests improve model quality or token cost.

## Files and responsibilities

- [expense-handoff.json](../../examples/expense-handoff.json): caller-owned exact trip
  text, revision and hash; eight unique item IDs with explicit Unicode code-point
  regions; exact labels/currencies; category and day decisions; rational currency
  rates and reimbursement caps. It contains no expected totals.
- [expense-handoff.sym](../../examples/expense-handoff.sym): the executable project.
  A first fresh request proposes one named item witness and repeats its caller
  category. A second fresh request constructs numeric label/value witnesses
  through `text.witnessed_number_in`. Existing `verify_source_items` checks the
  first proposal and the complete assembled catalog. All final arithmetic is
  native exact rational arithmetic.
- [expense_handoff.py](../../examples/expense_handoff.py): a small example host that
  validates the caller JSON, pins inputs/program/runtime/options, invokes native
  `Run`, and exports or rechecks the complete canonical output. It computes no
  expense answers. Its prepared directory retains the authoritative handoff,
  native call/check records, output artifact, and artifact receipt.

The caller has already resolved the category and date questions. Agreement with
those decisions establishes compliance with the caller contract, not that the
real-world category or date is correct. Regions are distinct even when two hotel
amounts and quotes are identical. Completeness means every item in the explicit
caller catalog appears exactly once. It says nothing about expenses the caller
left out of that catalog.

## Prepare, hand off, run, check

Run from the repository containing these example files. `prepare` and `check`
make no provider calls. `run` is the only provider-capable command; it uses the
existing admitted local launcher, explicit worker node placement, and thermal guard.
Before an actual run, follow the normal fleet placement/power contract and choose
an available installed tag. The route below is an example, not a reservation or
an availability claim.

```sh
python3 examples/expense_handoff.py prepare \
  examples/expense-handoff.json \
  --dir /tmp/my-expense-handoff \
  --by ollama:llama3.2:1b@node-f --retries 0 --agent-json
```

The directory must be new. Retain the returned `handoff_sha256` separately from
the directory. A parent agent can give a child this concrete instruction:

> Use the prepared expense handoff at `/tmp/my-expense-handoff`, with the exact
> handoff SHA I supplied separately. Execute its existing native project without
> changing the source, caller inputs, route, or acceptance policy. Return the
> machine result and, only if `accepted` is true, the complete `artifact.canon`
> with its SHA and encoding. On failure return the recorded error and progress;
> do not replace an amount/category, omit an item, or manufacture a passing total.

```sh
python3 examples/expense_handoff.py run \
  /tmp/my-expense-handoff --expect CALLER_RETAINED_HANDOFF_SHA --agent-json

python3 examples/expense_handoff.py check \
  /tmp/my-expense-handoff --expect CALLER_RETAINED_HANDOFF_SHA --agent-json
```

Substitute the actual 64-character SHA for the placeholder. Repeating `run` in
the same directory reuses native recorded calls and resumes under the same
source identity and native durable budget. `check` has no model connection: a
missing recorded answer refuses instead of filling the gap. It re-executes the
checks/arithmetic from the recorded proposals, then requires equality with the
saved full artifact and receipt. An interrupted run may be incomplete; it does
not yield an accepted output until every item and final check succeeds.

Read `accepted` and the native `report.status` first, then `determinism_summary`
if present, then the scoped source receipts and assurance fields. A failed
invocation never exposes a prior artifact as its newly accepted output. An old
artifact file may still exist; the current result controls acceptance.

Transfer the complete prepared directory and caller-retained handoff SHA to a
compatible checkout for offline rechecking, or consume only the accepted
canonical artifact after checking its SHA. The output is `symblic-canon-vN`
(the actual version is in the receipt), not display-truncated JSON or rounded
currency strings. Rational tags preserve the exact numerator and denominator.
File hashes are integrity bindings, not signatures or proof of authorship.
A receiver must trust the original caller-held fingerprint and runtime host.
Changed runtime pins require a newly reviewed preparation; do not silently
replace pins to force an old handoff through.

## Checks and limits

Every proposal receives only the current small source slice, its contract, and
for item selection the caller category. `context=none` plus explicit `from`
controls selected raw values. Native provenance still records dependency
identities and checks; this does not promise erasure of a provider's logs or
memory, and unrelated parent raw histories are not included in these prompts.

Field checks require the exact caller label, its declared source region,
`label + space + signed decimal + space + currency`, and exact source identity,
revision, hash and offsets. They reject digit/sign truncation, wrong amount
quotes, unsupported currency/layout, extra model-supplied contract fields, and
misplaced labels. Offsets count Unicode code points, not UTF-8 bytes or browser
UTF-16 units. No arbitrary paraphrase, alias, negation or category inference is
being certified. The example explicitly refuses negative amounts after exact
extraction; refund policy needs a separate caller-reviewed program.

The final assembled rows must cover the entire nonempty declared catalog with
unique IDs and exact original source spans. Hotel charges share a daily cap
using caller-supplied dates; ordinary meals have a per-item cap; travel and
client meals remain uncapped under this caller policy. Rates use caller-supplied
positive integer numerators/denominators. Arithmetic and accounting identities
are checked, but no expected $60 answer is embedded in the program.

The host accepts at most 32 disjoint items, 512 code points per item, 16000 code
points of source, and retries 0 or 1. It fixes verified/strict coercion, a 24000
character context budget, 200000 kernel steps and sequential execution.
The native single-candidate automatic route has `allow_cloud=false`,
`max_calls = 2 × item_count × (retries + 1)`, and a shared repair ceiling
`2 × item_count × retries`. This is a ceiling across resumed charged native
applicator dispatches; confirmed pre-dispatch refusals are refunded by the
existing runtime and remain distinguishable from provider work. It is not a
guarantee about token use, provider success, wall time, or identical new model
answers. Cancellation/provider timeouts follow the native host policy.

The example does not use the generic delegation templates because its compound
catalog/category/field contracts span a small project. The handoff shape follows
the same principle: fixed caller contract, model-constructed candidate, native
checks, exact accepted output. No hidden stronger model, semantic oracle, or
unchecked fallback repairs a refusal.

## Verification and present status

The focused test command uses fake Applicators only:

```sh
python3 -m unittest tests.examples.test_symblic_expense_handoff
```

Tests exercise a valid complete native run, exact rational accounting, one-item
raw-context isolation, wrong category/amount/sign/unit/layout, duplicate/omitted
or foreign IDs, changed source/contract, repeated hotel occurrences, Unicode,
same-day caps, native durable replay, and artifact mutation. Expected fixture
totals are held in tests, not in constructor inputs or acceptance assertions.
Passing those finite checks does not prove general extraction soundness, source
truth, model quality, or universal equivalence. This delivery is isolated
example code and fake-provider evidence; it has not been run against a real
model or deployed by this task.
