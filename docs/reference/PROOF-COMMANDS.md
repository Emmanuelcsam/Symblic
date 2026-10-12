# One command per proof inference

Implemented, independently reviewed and included in the installed 5 October 2026
reform; see the [5 October release evidence](evidence/2026-10-05-reform-install.json). This is an optional input format for
the existing incremental proof session. Installation does not establish measured
improvement on small models. JSON remains the default, and the existing
whole-term and flat-certificate formats remain.

The model supplies one text command, such as `premise p` or
`implies_elim s2 s1`. A mechanical parser translates it to the existing
`{rule, args, formula}` candidate. It inserts `formula: null` only for rules that
take no formula. Every rule and argument is still chosen by the constructor.
The unchanged `symblic.adapters.proof_session.append` checks that candidate, and the
unchanged flat verifier decides completion. No missing proof step is generated.

## Enable it explicitly

[This complete delegation task](../../examples/incremental-command.task.json) selects
`params.inference_format="command"` with
`params.certificate_format="incremental"`:

```json
{
  "template": "proof",
  "calls": 6,
  "params": {
    "premises": "a: \"A\"\nrule: \"A\" implies \"B\"",
    "goal": "\"B\"",
    "certificate_format": "incremental",
    "inference_format": "command",
    "step_limit": 3
  }
}
```

```sh
tools/symblic delegate check examples/incremental-command.task.json --agent-json
tools/symblic delegate run examples/incremental-command.task.json --by ollama:granite3.3:2b --agent-json
```

Inspection calls no model. Execution uses the existing native runner and admitted
applicators. Omitted `--by` uses the delegation local ladder; an explicit string
retains the template's bounded repairs. All inferences and repairs share `calls`.
The command wire does not raise the 1–32 accepted-step or 1–64 call ceilings.

The pure `symblic.adapters.logic.compile_task` and operator `logic/compile` body accept the
same `inference_format` field at their top level. The existing delegate CLI/API
accepts it under proof `params`. Its values are exactly `json` or `command`.
Any supplied inference format on a nonincremental task is refused before
dispatch. The compiler records the selected format in `formalization`, its
identity, generated source and generic rule input. Delegation records retain the
exact original request. There is no new provider backend or store.

## Syntax and references

Return one command string. The native response schema still carries that string
as its `answer`; it is not a separate raw provider protocol. Commands have no
assigned ID, JSON formula object, code fence, comment or second line. Spaces and
tabs can separate tokens. Rule names and host IDs are exact and case-sensitive.

| Command | Explicit operands |
| --- | --- |
| `premise NAME` | Exact named premise |
| `assume :: FORMULA` | New assumption formula |
| `implies_intro ASSUME_LINE BODY_LINE` | Assumption to discharge, then body |
| `implies_elim IMPLICATION_LINE ANTECEDENT_LINE` | Implication, then its exact antecedent |
| `and_intro LEFT_LINE RIGHT_LINE` | Two earlier lines |
| `and_left CONJUNCTION_LINE` | Earlier conjunction |
| `and_right CONJUNCTION_LINE` | Earlier conjunction |
| `or_left LEFT_LINE :: RIGHT_FORMULA` | Existing left disjunct and explicit other formula |
| `or_right RIGHT_LINE :: LEFT_FORMULA` | Existing right disjunct and explicit other formula |
| `or_elim OR_LINE LEFT_ASSUME LEFT_BODY RIGHT_ASSUME RIGHT_BODY` | Disjunction and two explicit branch pairs |
| `false_elim FALSE_LINE :: TARGET_FORMULA` | Falsity line and explicit target formula |

Premise names are keys in the current `premises` map. A bare name is an ASCII
letter followed by up to 63 ASCII letters, digits or underscores, matching the
logic compiler's names. The pure command API also accepts a JSON-quoted exact
premise name, such as `premise "source name"`, preserving the broader session
API's names. Quoting never changes or normalizes a name. A premise named `s1`
is still read as a premise by `premise s1`.

Other arguments must be current host IDs `s1`, `s2`, …, at most `s512` under the
existing session limit. Leading-zero aliases, quoted line IDs, forward references
and invented IDs refuse. The host assigns the new line's ID. Commands cannot
submit a replacement state, premise set, goal, conclusion or receipt.

Only the four formula-bearing rules accept `::`. The complete suffix is parsed
by the existing `symblic.adapters.proof.parse_formula`: JSON-double-quoted opaque atoms,
`false`, `not`, `and`, `or`, `implies`, and parentheses. Its precedence and scope
are unchanged. For example, `assume :: "A" implies "B"` explicitly assumes that
implication; `assume :: A` and JSON formula objects refuse. Quoted `"false"` is
an atom; bare `false` is falsity. Unicode and normalization distinctions remain
exact. Encode line breaks in quoted names or atoms with JSON escapes; literal
CR, LF, NEL, U+2028 and U+2029 in a command are refused.

## Fresh context and unchanged acceptance

`proof_command_frontier(state)` rechecks the same session prefix and returns the
same goal, named premises, earlier lines, inference rules, free assumption IDs,
line order, completion flag, next ID and remaining-step count. Formula ASTs are
rendered as fully scoped controlled text. Parsing each displayed formula
reconstructs the original AST. Unicode line separators are escaped so a displayed
formula can be copied into a single command. There is no simplification, inferred
next step, target proof, omitted premise or hidden constructor history.

Each generated ask still has `context=none` and requires its current frontier
and generic proof rules. A required packet that cannot fit refuses before a
provider call. Rejected commands appear only in that inference's ordinary repair
feedback; they are not accepted lines in the next frontier.

Native builtins are `proof_session_command(premises, goal, state, command)` and
`proof_command_frontier(state)`, in the existing proof adapter. The pure module
`symblic.adapters.proof_command` offers:

- `parse(state, command, tick=None)`: recheck state, translate exact syntax and
  confirm existing references; returns a candidate, not an acceptance receipt.
- `append(premises, goal, state, command, tick=None)`: translate and call the
  unchanged session append; returns its complete result contract.
- `frontier(state, tick=None)`: checked equivalent-information text view.
- `rules()`: detached generic instructions, independent of the task.

`parse` and `frontier` raise finite `ProofError` codes. `append` returns syntax
errors as candidate refusals only after the original state has been rechecked.
Invalid/foreign state and completed/full-session refusals retain the original
session precedence. Host budget exceptions propagate. Syntax hints are fixed
grammar instructions, never a generated next proof step.

Completion still requires a closed line exactly equal to the caller's goal and
an accepting flat-checker receipt. Free assumptions, disjunction branch isolation,
discharge identity, vacuous discharge and elimination from falsity retain their
existing meanings. A result remains conditional on caller premises and finite
domains; truth and consistency are not established. Failure leaves the goal
unresolved.

## Bounds and identity

The command input is bounded by the existing 262,144-byte formula input ceiling,
with a character preflight before UTF-8 encoding. Its candidate uses the existing
AST depth/node/text/byte scanner. Each internal work-charger scope has a
200,000-unit allowance. Command translation has its own scope; text-frontier
rendering has another. Existing session loading, prefix checking and any final
certificate verification use their existing separate bounded scopes. A whole
pure `parse`, `append` or `frontier` call can therefore span multiple allowances;
200,000 is not its aggregate work ceiling. Native calls pass the same host tick
through every phase, so charged work accumulates against one kernel budget
without resetting between those scopes. A large otherwise valid command can
exhaust translation work before reaching its byte ceiling.
The rendered frontier has a finite 524,288-byte output ceiling, and each formula
still has the existing parser/renderer limits. Additional presentation work can
cause a resource refusal where another representation fits; it never weakens a
logical check. Native prompt and total call limits remain separate.

This addition versions the command helper (1), proof adapter (4), logic compiler
(5), and delegation template compiler (4; subsequently 5 for capsule selection).
The original proof-session and flat
certificate versions remain 1. Kernel identity includes the command module, and
required execution pins include its source. These are local compatibility
identities, not authentication or a proof of whole-runtime soundness.

The root integration ran 127 Python checks and five browser journeys, including
desktop light and phone dark selection and a visible refusal when an older backend
does not honor the selected command format. These checks cover all eleven inference rules, command/JSON candidate and
receipt agreement, formula scopes and Unicode, malformed commands, wrong arity,
foreign/tampered sessions, branch leakage, context/call limits, fresh-context
repair, finite-domain construction, final-checker refusal, delegation records
and source-only CLI inspection. They use fake constructors. Any model-quality or
cost comparison needs a separate frozen evaluation with both formats receiving
the same proof information and clearly accounted construction budgets.

The 5 October supplied-frontier diagnostic (not included in this repository)
completed twelve one-call assignments without repairs. Commands delivered two of
six accepted certificates (the two Qwen 4B configurations), JSON zero of six; the
1B and 2B models accepted none. Both formats received the same premises, goal,
checked prefix and rule semantics, with format-specific instructions and schemas.
This isolates one inference interface, not whole-proof discovery. Schema validity
was 12/12, distinct from logical validity. See [the measured scope](REFORM-3.md#completed-matched-integration-pilot--5-october-2026-utc)
for costs, rejected cases and repeated-configuration limits.

A later exact-command menu diagnostic (not included in this repository)
compares Text and Enum selection from the same three caller-authored commands.
It records 2/6 versus 3/6 goal-closing answers on one supplied frontier and
keeps format validity separate from inference validity. It uses a different
frozen runtime/information setup from the earlier JSON/command diagnostic.
