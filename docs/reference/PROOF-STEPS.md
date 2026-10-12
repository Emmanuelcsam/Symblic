# Flat natural-deduction proof certificates

`symblic/adapters/proof_steps.py` adds a flat, line-by-line certificate format for the same
intuitionistic propositional logic as `symblic/adapters/proof.py`. The existing nested
proof-term checker and every existing term remain available. This module performs
no proof search, model calls, formula completion or premise invention. The model
or human author must supply every inference and its dependencies.

This format addresses a concrete usability failure in the prior nested format:
the first 39 calls in one preliminary model evaluation yielded 29 rejected and 10
malformed certificates, with no accepted proof. That evaluation exercised the old
nested format. **No model acceptance-rate improvement has yet been measured for
the new flat format.** The tests described below establish bounded checker behavior
and agreement with an independent translation into the existing checker; they do
not establish that models can reliably generate these certificates.

## Public contract

```python
verify(premises, goal, certificate, tick=None)
certificate_schema()
```

`tick` is a no-argument host budget callback. Budget exceptions raised by the host
propagate, rather than being mislabeled as invalid logic. `certificate_schema()`
returns a detached, uniform JSON Schema for generation. It constrains the outer
shape; the verifier remains authoritative for formulas, references, arity, scope
and the conclusion. An adapter must keep premises and goal outside model control.

The certificate has exactly `version`, `steps`, and `result`. Every step has exactly
`id`, `rule`, `args`, and `formula`. IDs are a letter followed by at most 63 ASCII
letters, digits or underscores. IDs are unique. Except for an external premise
name in the `premise` rule, arguments reference previously declared steps only.
Forward/self references, missing references and duplicate IDs are rejected.
Premise names and step IDs have separate namespaces.

Here is modus ponens from caller-held premises `if_a: A implies B` and `a: A`:

```json
{
  "version": 1,
  "steps": [
    {"id": "p", "rule": "premise", "args": ["if_a"], "formula": null},
    {"id": "q", "rule": "premise", "args": ["a"], "formula": null},
    {"id": "r", "rule": "implies_elim", "args": ["p", "q"], "formula": null}
  ],
  "result": "r"
}
```

For this example the host calls:

```python
A, B = ["atom", "A"], ["atom", "B"]
receipt = verify({"if_a": ["implies", A, B], "a": A}, B, certificate)
```

Formulas are unchanged: `["atom", name]`, `["false"]`, or
`["and"|"or"|"implies", left_formula, right_formula]`. `not A` is represented as
`A implies false`. The existing `parse_formula` and `render_formula` functions
continue to support controlled formal text. Atoms and premises are declarations;
the checker does not establish their empirical truth or consistency.

## Rules

| Rule | Arguments | `formula` | Inference |
| --- | --- | --- | --- |
| `premise` | `[premise_name]` | `null` | The caller's declared formula |
| `assume` | `[]` | Assumed formula | Opens an assumption identified by this step ID |
| `and_intro` | `[left, right]` | `null` | `left and right` |
| `and_left` | `[pair]` | `null` | Left member of a conjunction |
| `and_right` | `[pair]` | `null` | Right member of a conjunction |
| `implies_elim` | `[implication, argument]` | `null` | Consequent, requiring exact antecedent match |
| `implies_intro` | `[assume_step, body]` | `null` | Assumed formula implies body; discharges precisely that assumption ID |
| `or_left` | `[value]` | Other/right formula | `value or formula` |
| `or_right` | `[value]` | Other/left formula | `formula or value` |
| `or_elim` | `[choice, left_assume, left_body, right_assume, right_body]` | `null` | Common branch conclusion, discharging the two corresponding assumptions |
| `false_elim` | `[absurdity]` | Target formula | Target, requiring a derivation of `false` |

An `implies_intro` or `or_elim` discharge argument must refer directly to an
`assume` step. Matching formulas do not make distinct assumption IDs interchangeable.
The two disjunction-branch assumptions must be distinct and exactly match the
choice's left and right formulas. The branch conclusions must match. A branch
assumption cannot occur freely in the opposite branch or the disjunction being
eliminated. This gives the flat representation explicit local branch scope.

The verifier infers each line's formula, free assumption IDs and used external
premises. An implication removes its discharged ID only from its body's free set.
A disjunction elimination combines the choice's free set with each branch's free
set after its own discharge. Shared subproofs retain their original free sets;
using a discharged assumption elsewhere does not make that use closed. The
selected result must have **no free assumptions** and must exactly match the
caller-held goal. Vacuous discharge is valid. Unused assumptions may remain open
on unused lines, but every unused line still must be well formed and correctly
inferred. The receipt's used premises are those needed by the selected result.

For example, `A implies A` uses two lines:

```json
{
  "version": 1,
  "steps": [
    {"id": "h", "rule": "assume", "args": [], "formula": ["atom", "A"]},
    {"id": "out", "rule": "implies_intro", "args": ["h", "h"], "formula": null}
  ],
  "result": "out"
}
```

## Bounds and receipts

The whole input is scanned before inference, including unused premises/steps,
keys, repeated shared structures, cycles and text encodings. Limits are 512 steps,
256 premises, 64 structural depth, 20,000 scanned nodes, 262,144 conservatively
counted bytes, 4,096 characters per text and 200,000 aggregate work units. Expanded
inferred formulas are checked and charged at each line, so repeated DAG references
cannot conceal exponential formula growth. Booleans/floats/custom Python objects
are refused; `null` is permitted for the required unused `formula` field.

The result follows the existing checker's receipt conventions: `ok`, `logic`,
`version`, `conclusion`, `used_premises`, `open_assumptions`, `checks`, `hashes`,
`conditional_on_premises=true` and `consistency=not_checked`. `format` distinguishes
this format's judgment identity from nested terms. Rejections have a finite
`error` code, and a zero-based `rejected_step` when the failure concerns a line.
No successful conclusion or judgment hash is returned on rejection. `checks`
counts checked lines; it is not confidence, independence or empirical evidence.

`tests/adapters/test_symblic_proof_steps.py` covers every rule, small generated formulas,
mutated rules/references, branch scope, vacuous discharge, assumption escape,
caller-held contract forgery, malformed unused data and resource limits. Each
accepted test proof is independently expanded with fresh bound names into the
existing nested-term checker and also checked against Boolean valuations as a
necessary soundness sanity check. Boolean truth tables are not the runtime
verifier and do not prove completeness for intuitionistic logic.

## Native language and compiler integration

The additive builtins are `proof_steps_check(premises, goal, certificate)`,
`proof_steps_valid(premises, goal, certificate)` and
`finite_steps_check(domains, premises, goal, certificate)`. Existing `proof_check`,
`proof_valid` and `finite_check` retain the nested format. The new bridge accepts
exact JSON null for the uniform unused `formula` field; the old term bridge's
wire contract is unchanged. JSON input/model answers can provide these records;
this change does not add a `null` literal to the source language.

`compile_task({... , "certificate_format": "steps"})` selects the flat lane.
The only accepted formats are `steps` and `terms`; omitting the field preserves
the old `terms` default. The returned `formalization.certificate_format` names the
actual format, and the formalization hash binds it. The compiler emits the
existing verified `ask`/`ensure` workflow, with a uniform record type: version
exactly 1, 1–512 step records, the fixed rule enumeration, 0–5 text arguments per
step, formula `Any`, and text result ID. Its existing schema-aware Applicators
path supplies that shape to models; there is no provider bypass.

The prompt supplies rule descriptions and a small unrelated generic example. It
does not supply the current task's proof, search for one, or move certificate
construction into a special-purpose kernel solver. Checker rejection uses the
existing bounded repair path and shared call budget. Extra model-returned
premises/goals/conclusions are rejected under strict record validation.

For finite-domain tasks, the compiler supplies the deterministic authoritative
expansion as context. `finite_steps_check` independently expands the original
caller-held domains/premises/goal, then verifies the flat steps against that
expansion. Its receipt is conditional on both declared premises and finite
domains, retains domain sizes/source and expansion hashes, and binds the flat
format in the final judgment identity. Model-supplied expansions cannot replace
that authority. Domain order remains part of the declared expansion contract.

`symblic/adapters/proof_steps.py` is required in execution pins and has a kernel identity
component. The proof adapter's version is 2 for the additive entry points. Tests
cover injected model construction, rejected-then-correct repair, exhausted call
budgets, contract forgery, scope escape, finite-domain order changes, null wire
boundaries and unchanged default nested execution.

Both nested and flat input scanners now use iterator frames, keeping pending
traversal state proportional to depth. They continue counting every expanded
occurrence of aliased data and reject cycles; sharing does not bypass work caps.
The scaled resource regression measures maximum frontier frames deterministically
and confirms that a host budget exception stops before wide pending allocations.
This scanner correction changes implementation hashes, while preserving proof
formats and inference semantics. Earlier model evaluations of the old nested
checker must be attributed to their original implementation snapshot.
