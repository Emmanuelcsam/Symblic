# Write Symblic with the installed parser contract

The source-only `grammar` commands expose current syntax, options, bounds and
checked examples. They call the existing parsers; they do not run a program,
ask a model, choose a proof step or start a provider. This is an additive authoring
interface, not a new language implementation.

```sh
tools/symblic grammar catalog --agent-json
tools/symblic grammar export --entry program --format ebnf
tools/symblic grammar check my-program.sym --agent-json
```

For an agent handoff: provide the catalog, a relevant EBNF export, your task and
separate input data. Ask the agent to return source plus the `grammar check`
result. Then use the ordinary `tools/symblic check my-program.sym --agent-json`
for additional static diagnostics and your normal reviewed execution path for
actual type/predicate checks. Do not treat parser acceptance as a completed task.

A small authoring pattern is:

```symblic
use profile=verified, context=none, coercion=strict.
given data: Text.
ask answer: Bool "Decide from {data}." from data.
show answer.
```

Pass the actual data as the host's named `data` input. Never concatenate arbitrary
caller text into formal source. The example deliberately has no correctness
predicate: it demonstrates valid syntax, not validated classification.
For a compound example with source-field and complete-catalog checks, see
[EXPENSE-HANDOFF](EXPENSE-HANDOFF.md). For reusable request envelopes, see
[AGENT-DELEGATION](AGENT-DELEGATION.md).

## Select the correct parser

| Entry | Authority | Acceptance establishes |
| --- | --- | --- |
| `program` | `symblic.parse` | Parsing and the selected execution profile's parser restrictions |
| `formula` | `symblic.adapters.proof.parse_formula` | A bounded controlled propositional formula AST |
| `proof-command` | `symblic.adapters.proof_command.parse` | Command syntax and references against the supplied, rechecked current session |

Program authoring defaults to `verified`. An explicit `--profile legacy` or
`--profile explicit` selects that existing parser policy for this check; it
changes no runner or saved program. Profiles are not options for formula or
proof-command syntax.

The catalog derives keyword/extension names, allowed `ask`/`use` options
(including `capsule`), operator aliases and builtin callable-name exclusions
from the installed implementation. Versions and limits are read from those
modules. `contract_id` binds that exported authoring metadata and grammar/example
hashes. It is not a loaded-code attestation, runtime lock, authenticity signature
or guarantee that future parser versions behave identically.

The [program EBNF](grammar/program-subset.ebnf) is a **portable authoring subset**:
explicit statements, common types and expressions, routines and blocks. Use one
statement/header/end per physical line. It prefers ASCII names, lowercase
keywords, explicit types and periods. The real parser also accepts additional
forms, Datalog, effect extensions, single/triple quotes, Unicode identifiers and
operators, and legacy prose. Those capabilities remain available. The exported
EBNF does not implement or validate the whole extension language, enforce all
side conditions, or serve as a provider decoding grammar.

## Three text syntaxes, three boundaries

- **Core program strings** support `{name}` interpolation; double braces `{{`
  and `}}` represent literal braces. They are not JSON strings: core source
  `"\u0061"` contains the six characters `\u0061`, while a proof atom using that
  JSON escape denotes `a`. Use named inputs for arbitrary external text.
- **Controlled formulas** use JSON-double-quoted opaque atoms, bare `false`,
  `not`, `and`, `or`, `implies` and parentheses. Keywords are lowercase. Core
  aliases such as `∧` or `→` are not formula operators here. `"false"` is an
  atom; `false` is falsity. Empty atom text is allowed. `not` binds most tightly,
  then `and`, `or`, and right-associative `implies`. See [formula EBNF](grammar/formula.ebnf).
  The existing [finite-domain frontend](FINITE-LOGIC.md) is a separate syntax/API;
  this entry neither replaces it nor accepts unrestricted quantified formulas.
- **Proof commands** are one physical line with exact rule names and current
  host line IDs. Formula-bearing rules introduce their complete controlled
  formula with `::`. Premise names can be JSON-quoted; line IDs cannot.
  The native answer string remains inside its enclosing response object when
  that schema is requested. See [command EBNF](grammar/proof-command.ebnf) and
  [PROOF-COMMANDS](PROOF-COMMANDS.md).

Unicode proposition text and premise names remain exact, including normalization
form. For example, precomposed `é` and decomposed `e` plus U+0301 are different
atoms. Core identifiers follow the implementation's Unicode word classes, so
not every arbitrary Unicode string is an identifier; the portable subset avoids
that ambiguity. Core `{:}` is an empty record, while `{}` is an empty set.

```sh
tools/symblic grammar check claim.formula --entry formula --agent-json
tools/symblic grammar check next-command.txt --entry proof-command \
  --session current-session.json --agent-json
```

`current-session.json` must be the caller's original current session, not a new
state proposed by the constructor. Its existing prefix is rechecked. The command
check translates the candidate but does not append it or determine whether that
inference is legal. For example, `and_left s1` passes syntax/reference checking
when `s1` exists even if that line is not a conjunction. The ordinary
`proof_session.append`/flat checker must still reject that inference.

## Optional finite command-menu schema

This operation exports only exact commands supplied by the caller. It does not
enumerate rules, synthesize operands, search for a proof, rank choices, select an
answer or omit an invalid inference because of its semantics.

```sh
tools/symblic grammar menu authored-commands.json \
  --session current-session.json --agent-json
```

`authored-commands.json` is a JSON array of 1–32 distinct exact command strings.
Every string must parse and reference the **same unchanged** session. An earlier
menu entry does not create a line for a later one. The result retains exact
order/text, translated candidates, source hashes and parser versions. `schema`
is a JSON Schema string enum; `native_answer_schema` wraps it in the ordinary
closed `{"answer": ...}` object. The caller can inspect both before using an
existing provider integration. No backend is configured by this command, and
`provider_schema_support` remains `not_established`.

A source-only Python example using the existing session API:

```python
import symblic.authoring.helpers as A
import symblic.adapters.proof_session as R

original = R.start({"p": ["atom", "A"]}, ["atom", "B"])
menu = A.command_menu(original, ["premise p", 'assume :: "B"'])
assert menu["ok"]
assert menu["inference_validity"] == "not_checked"
assert original["steps"] == []
```

The parent must still enforce its original premises/goal and invoke the existing
append/checker after construction. A schema-valid choice need not advance or
complete the proof, and no source truth follows from a proof under premises.

## Read the machine result and bounds

`ok` and `parser_status` report this operation's bounded parser outcome.
`reference_status` is separate. `inference_validity` and `proof_completion` remain
`not_checked`; `execution` remains `not_run`. Errors retain native diagnostics or
explicit resource/contract refusal codes. Budget refusal does not prove that the
input is impossible or mathematically false.

This helper admits at most 256 KiB of UTF-8 per source/file/request, JSON depth 64
and 20000 visited nodes, plus at most 32 menu commands. Proof parsing shares a
200000-unit checker-work budget per operation. The native parsers retain their
own limits. The helper may therefore refuse a request that a lower-level parser
could accept under another budget. File size/type is checked before reading;
JSON/session bounds are checked before invoking the proof-command parser. This
is finite resource accounting, not a wall-time promise.

[conformance.json](../../symblic/authoring/grammar/conformance.json) records 50 positive/negative cases
against the actual parsers, including exact quotes, Unicode, operator scope,
empty records, references and malformed commands. The focused suite also checks
all eleven command forms, bounds, unchanged sessions, machine CLI output and the
syntax-versus-inference counterexample:

```sh
python3 -m unittest tests.authoring.test_symblic_authoring
```

These are finite conformance tests, not a proof that the EBNF describes every
accepted input or that well-formed model output is correct. This source-only
authoring interface is included in the installed 5 October reform; see the
[release evidence](evidence/2026-10-05-reform-install.json). The separate [finite-menu diagnostic](evidence/2026-10-05-command-menu-pilot.json)
measured six paired configurations on one supplied frontier; it does not establish
general model-quality or provider-decoding improvement.
