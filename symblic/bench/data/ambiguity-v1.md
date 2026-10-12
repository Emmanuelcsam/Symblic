# Finite owner-intent dataset, version 1

`ambiguity-v1.json` is an agent-authored synthetic dataset for testing structured request interpretation and field clarification. It contains **42 cases in 14 scenario families**: seven development families and seven held-out families, each with two ambiguous owner worlds and one clear control. Each split has 14 ambiguous cases and seven clear controls.

Gold values represent the preference assigned by the dataset author to a synthetic owner. They are not measurements of real owners, independently observed world truth, or judgments made by an evaluator model. Arithmetic and selection rules are explicit, so implementations can check the resulting finite outputs without grading prose.

## What the pairs establish

Within a family, the two ambiguous cases have byte-equivalent `request`, `context` and `fields` values. Their owner preferences and resulting gold outputs differ. Both worlds are consistent with the information initially supplied. A reader cannot identify the assigned owner world from that public information alone.

The clear control supplies the missing preference in the request. Some context describes an incomplete stored setting; the current owner's explicit request resolves that omission. A clear control requires no clarification.

Every ambiguous case in this first version has **one unresolved field**. This deliberately small benchmark tests recognition of that field, use of the scripted answer, preservation of already specified information, and the corresponding finite transformation. It does not cover multi-stage preference discovery, unrestricted ambiguity, competing goals, or free-form conversational skill.

## Case contract

The dataset root has `version`, `provenance`, and `cases`. Each case has:

| Field | Meaning |
|---|---|
| `id` | Unique stable case identifier; never provider-visible. |
| `family` | Scenario family used for split and clustered reporting. |
| `domain` | One of units, scope, referents, time, order, quantifier, rounding. |
| `split` | `dev` or `heldout`; an entire family belongs to one split. |
| `public_group` | Shared by the ambiguous twins; a clear control has its own group. |
| `request` | Synthetic owner's natural-language request. |
| `context` | All additional public records, rules and conventions. |
| `fields` | Ordered output fields: name, description, type, and optional choices. |
| `gold.values` | Complete authored output, with exactly the declared field names. |
| `gold.clarify_fields` | Unresolved field names for the assigned world; empty for controls. |
| `gold.owner_answers` | Scripted typed answers, with keys exactly matching `clarify_fields`. |

Field types are `text`, `integer`, `boolean`, and `text_list`. JSON booleans are not integers. Lists have the exact order specified by the request or field description. Text matching is exact under the benchmark's declared normalization; no embedding or model judge establishes equivalence. Optional choices restrict values to a finite typed domain. This dataset does not require floating-point values or approximate comparisons.

Only `request`, `context` and `fields` belong in the provider-visible case view. Do not serialize an entire case into a prompt. `gold`, unresolved-field names, split labels, family identifiers and world-specific IDs must remain outside provider requests, repair feedback and examples. Resume keys may include these identifiers and dataset hashes, but those keys must not become model instructions.

## Clarification protocol

All conditions use the same public task and field descriptions. The response protocol is:

```json
{
  "action": "answer",
  "values": [{"field": "field_name", "value": "typed value"}],
  "questions": []
}
```

`action` is `answer`, `clarify` or `abstain`. `questions` contains at most three field names. For `clarify`, the scripted owner returns only the requested fields' available answers. A returned value is used as evidence of that synthetic owner's choice, not as an independently verified fact about the world.

Unknown, repeated, or already resolved field requests must be counted explicitly; they do not earn new useful-question credit. `owner_answers` intentionally contains only the fields that were unresolved. A request for another field must not reveal extra gold output. The harness must define its no-answer response consistently across cases.

This interface measures selection of a useful **field ID**, not the linguistic quality, politeness or semantic adequacy of a free-form question. The public field menu helps every condition identify the output contract. Results must retain that limitation.

## Families and split boundary

| Domain | Development family | Held-out family |
|---|---|---|
| Units | Bottle volume labeling and conversion | Scale-dependent temperature alert |
| Scope | Item versus invoice discount | Directory versus recursive export selection |
| Referents | Repeated synthetic contact name | Possessive-pronoun ownership annotation |
| Time | Missing AM/PM in a dated reminder | Inclusive versus exclusive cutoff day |
| Order | Reading direction versus physical tile order | Numeric ticket-score sorting direction |
| Quantifier | Some versus all members of a team | Any versus all tags on a card |
| Rounding | Nearest-integer tie convention | Directional snapping onto a reporting grid |

Held-out scenarios use different entities, operations and prose from development families. The domain concepts intentionally overlap: this tests transfer to new scenarios within seven declared dimensions, not generalization to entirely unseen semantic concepts. The twins and their clear control must never be split across development and evaluation.

Field order is counterbalanced within each split: the unresolved field is first in three families, last in three, and in the middle in one three-field family. Thus an always-first or always-last query identifies the unresolved field in only 6 of 14 ambiguous cases per split. Each family uses exactly the same field order for its twins and clear control, so ordering does not signal whether clarification is needed. This removes the original positional shortcut; it does not establish that every possible dataset shortcut has been eliminated.

Dates, contact IDs, paths, records and device readings are synthetic. Time cases use fixed dates and UTC; there is no reliance on the current clock, live calendars, daylight-saving transitions or geographic conventions. Requests involving drafts, reminders and exports ask only for structured descriptions. No real message, schedule, file operation or device action is needed.

## Conditions and assessment boundaries

The intended comparison includes direct structured output, typed output with encoded checks, and typed output with scripted clarification. The first two may abstain or indicate a need for clarification. They must not be penalized as semantically wrong merely for declining to invent the hidden preference.

Before clarification, distinguish:

- valid structure and compatibility with the supplied public information;
- explicit abstention or an appropriate unresolved-field request;
- commitment to one plausible reading without evidence selecting it;
- exact match to the assigned hidden gold, which may be a lucky guess.

A different public-compatible world is not a demonstrated misreading of the original request. A hidden-gold match without resolving the missing field is not proof that intended meaning was recovered. After a sufficient owner answer, exact output matching tests whether the protocol used that answer and preserved the stated constraints.

Report clear controls separately: their original request already resolves the preference, so correct output with no necessary questions is the target. Include original-field preservation, invalid output, useful/redundant/repeated questions, unresolved outcomes, wrong answers after clarification, provider failures, and total calls, tokens and elapsed time. Do not replace these with a single agreement score.

The clarification condition receives additional information. An optional direct-output control supplied with exactly the same owner answers can separate that information benefit from the effect of typing or execution. Without it, the comparison evaluates the entire interaction protocol. Matching call limits alone does not match information.

## Integrity and reporting

Freeze dataset, prompt, schema, oracle-protocol and evaluator versions before held-out execution. Include their hashes in result identity so resuming under changed labels or prompts cannot silently reuse old outcomes. Give every case and condition a fresh model interaction; prior twin answers must not enter the next twin's context.

Retain all attempted cases and infrastructure failures in reported denominators. Report development and held-out results separately. The two worlds of a public group and the three variants of a family are dependent observations. Use paired comparisons and family-clustered uncertainty when justified; there are only seven held-out family groups, so broad generalization would be weak.

“Held-out” means reserved from prompt and harness tuning. Dataset authors and reviewers necessarily see the cases. It does not mean unknown to all developers, absent from model pretraining, or permanently protected after public release. If evaluation cases guide later prompt, route, checker or repair changes, record that exposure and use new families for a fresh held-out claim.

This dataset supports a bounded test of authored intent under an explicit interaction protocol. It cannot establish shared subjective experience, general semantic truth, statistical independence of readers, or general improvement in a model's underlying reasoning ability.
