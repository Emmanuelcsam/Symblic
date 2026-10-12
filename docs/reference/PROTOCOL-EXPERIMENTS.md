# Finite protocol replay and compensation planning

`symblic/experiments/protocols.py` implements three pure, bounded folds over a
caller-supplied ordered event stream. `catalog()` supplies editable examples and
`run(id, data)` returns exact JSON with `arithmetic`, `results`, `checks`, `limits`
and `sources`. No run sends a message, claims a resource, writes a ledger or
performs a compensation. These are reusable state-machine mechanisms; their
integration with a durable authenticated transport remains a separate task.

Every event has an ASCII `id` and a `kind`. Replaying an identical event ID and
content has no second effect; reusing that ID with different content refuses the
entire replay. First-occurrence order is authoritative. Truncated streams expose
missing acknowledgements or uncertain attempts rather than inventing outcomes.

## Exact-revision acknowledgements

`revision-acknowledgements` accepts `{"events": [...]}`. Its event forms are:

| Kind | Fields in addition to `id`, `kind` |
| --- | --- |
| `publish` | `message`, `revision`, `digest`, `recipients` |
| `receive` | `message`, `revision`, `digest`, `recipient` |
| `ack` | The receive fields, plus `receipt` naming an earlier receive event |

A message begins at revision 1 and advances by exactly one. Each revision fixes
its content digest and recipient list. An acknowledgement must match a prior
receive record on all four fields: message, revision, digest and recipient.
Receiving alone does not acknowledge. The result retains old acknowledgements
but reports current completion using only the latest published revision and its
required recipients. Republishing unchanged bytes as a new revision still
requires acknowledgement of that new revision.

These checks establish consistency of the supplied records. A digest is not an
authentication signature, and an `ack` row cannot prove that a person read or
understood a message.

## One-use ownership across branches

`one-use-resources` accepts `{"events": [...]}`. `issue` names a logical resource,
branch and operator. `transfer` names the source and destination branch/operator pairs
and `expected_revision`. `consume_intent` names the current branch and operator,
`expected_revision`, and a fresh `attempt` ID. Transfers and intents require an
exact current revision and ownership match.

An issued or transferred resource becomes `uncertain` as soon as a consumption
intent appears. While uncertain it cannot transfer or admit another use. A
`consume_result` names the resource, exact pending attempt, an `evidence` digest
and an outcome: `consumed`, `not_consumed` or `unknown`. An explicit `resolve`
event has the same fields but must choose one of the two definite outcomes.
Unknown receipts remain in history; they do not clear the intent.

Definite consumption is terminal. Definite non-consumption restores the previous
operator and available state, permitting a new explicit intent with a new attempt
ID and the current revision. Old terminal evidence cannot settle a later
attempt. Neither outcome triggers automatic redispatch. Each unique transition
advances the revision, including a new unknown receipt. Logical resource IDs and
attempt IDs cannot be reused within the supplied stream.

## Saga compensation planning

The compensation and log-recording motivation follows Garcia-Molina and Salem's
[Sagas (1987)](https://www.cs.princeton.edu/research/techreps/598). The adapter
implements an inert finite plan; it does not supply the paper's database
transaction machinery or an external atomicity guarantee.

`saga-compensation-plan` accepts `steps`, `events` and a Boolean `rollback`.
Each step declares `id`, a distinct `compensation` ID, and prerequisite IDs in
`requires`. The declared graph must be acyclic. Original and compensation IDs
cannot overlap.

An `intent` event names `step`, `action` and a fresh `attempt`. The action must
be either that step's original ID or its exact declared compensation ID.
`outcome` and `resolve` add an evidence digest and outcome; ordinary outcomes
allow `done`, `not_done`, `unknown`, while resolutions must be definite. Every
outcome must match the currently pending attempt for that exact step/action.

A forward intent requires all original prerequisites to be done. A compensation
intent requires its original to be done and all affected direct dependents to
have completed their compensations. Unknown dependent originals block an
ancestor's compensation too. The same rule applies transitively through the
validated execution history. Missing or unknown compensation outcomes remain
uncertain and never produce a blind retry. A definite `not_done` result can
permit a new explicit attempt; it does not reuse the old identity.

The first compensation intent starts rollback permanently for the recorded
history, including when that intent has no outcome. Setting the current
`rollback` request to false cannot undo this fact or permit new forward intents.
Late matching outcomes can still close existing pending attempts. Before any
compensation intent, `rollback` only requests an inert current plan; it is not a
persisted historical command.

`reverse_dependency_order` presents the declared order, with deterministic
lexical tie ordering. `ready_compensations` contains only actions eligible now,
with original/compensation links and their completed compensation prerequisites;
it is not an executable batch containing future dependent actions. Blocked and
uncertain records retain their reasons and attempt IDs. Completed rollback means
all recorded completed originals have completed compensations and no attempt is
uncertain; it does not certify restoration of any external world state.

## Bounds, validation and integration limits

Inputs admit at most 256 events, 16 messages/resources/steps, eight recipients or
prerequisites, 48-character identifiers and 64-character lowercase SHA-256
references. Structural checks precede replay: 128 KiB input, depth 16, 20,000
JSON nodes, exact integers/Booleans and no floats, cycles or malformed Unicode.
The complete returned result is limited to 512 KiB. Errors use fixed diagnostic
codes without echoing supplied contents. The module records its loaded source
identity for the host registry's integrity checks.

The 18 isolated tests cover reconnect duplication and conflicts; stale revisions;
crashes after receipt or intent; branch/operator/revision mismatches; old evidence
against a later attempt; forward and compensation prerequisites; monotone
rollback; graph cycles; bounded exact input; and every prefix of the examples.
Tests perform no real messages, model calls or host effects.

Erased or invented histories, forged evidence references and two logical IDs for
one physical resource cannot be detected by a stateless fold. Callers must supply
durable ordering, authenticated writers, resource identity and verified external
receipts when using these mechanisms operationally. The existing
[effects ledger](EFFECTS.md) and [agent graph runtime](AGENT-GRAPHS.md) retain their
own durability, admission and recovery contracts; this experiment does not
silently replace or extend their execution paths.
