# Proof terms, version 1 — integrated 2.5 interface

`symblic/adapters/proof.py` is a bounded, stdlib-only checker for **intuitionistic
propositional logic**. It has no IO, model calls, import-time registration, or
proof search. A human or LLM constructs a derivation; the checker infers its
conclusion by checking local natural-deduction rules. It neither discovers the
meaning of prose nor establishes the truth or consistency of premises.

## Caller API and trust boundary

```python
from symblic.adapters.proof import parse_formula, verify

p = parse_formula('"The switch is on"')
goal = ['implies', p, p]
receipt = verify({}, goal, {
    'version': 1,
    'proof': ['implies_intro', 'h', p, ['hypothesis', 'h']],
})
assert receipt['ok']
```

`verify(premises, goal, certificate)` receives authoritative premises and goal
from the caller. Premises are a dictionary of nonempty names to formulas. The
certificate dictionary has **exactly** `version` (integer 1, never bool/float)
and `proof`. No certificate-supplied goal, premises or intermediate claimed
conclusions are accepted. Formula equality is exact structural equality: no
renaming, normalization, truth tables or theorem search.

Formula JSON ASTs are `['atom', text]`, `['false']`, or
`[operator, A, B]` with operator `and`, `or`, `implies`. Negation is
`['implies', A, ['false']]`. Atoms are opaque arbitrary Unicode strings (including
empty strings). `"P(x)"`, `"P(y)"`, and `"∀x P(x)"` are unrelated propositions;
no variables, substitutions or quantifiers are implied in this checker. The separate
[finite frontend](FINITE-LOGIC.md) lowers explicit-domain quantifiers into this fragment; unrestricted
first-order logic is not implemented. Unicode is not normalized; unpaired surrogates are rejected.

## Exact term grammar

All terms are JSON lists with the following exact positional arities.

| Term | Inferred conclusion / condition |
| --- | --- |
| `['premise', name]` | The named caller premise |
| `['hypothesis', name]` | The named lexically active hypothesis |
| `['implies_intro', name, A, body]` | `A implies B`, where body derives B under name:A |
| `['implies_elim', function, argument]` | B, from function:A implies B and argument:A |
| `['and_intro', left, right]` | A and B from left:A and right:B |
| `['and_left', pair]` | A from pair:A and B |
| `['and_right', pair]` | B from pair:A and B |
| `['or_left', value, B]` | A or B from value:A |
| `['or_right', value, A]` | A or B from value:B |
| `['or_elim', value, left_name, left_body, right_name, right_body]` | C from value:A or B, left_body:C under left_name:A, right_body:C under right_name:B |
| `['false_elim', value, target]` | target from value:false |

Introduction discharges only its own lexical assumption. Disjunction branches
have separate scopes and must infer exactly the same conclusion. Active-name
shadowing (including caller premise names) is rejected. The two branch names
must differ; disjoint scopes may reuse names. Vacuous discharge is allowed.
Hypotheses cannot impersonate premises, escape a scope, or appear at top level.
There is no recursion, reference to a derived proof by name, excluded-middle
rule, or double-negation-elimination rule.

Explosion is intentional: a caller premise `false` allows any target through
`false_elim`. Contradictory premises may likewise derive false. This module does
**not** check consistency or real-world truth.

## Receipts and limits

Every receipt includes `ok`, `version`, `logic`, `conclusion`, `used_premises`,
`open_assumptions`, `checks`, `hashes`, `conditional_on_premises: true`, and
`consistency: 'not_checked'`. Success requires exact equality with the caller
goal. `used_premises` lists sorted names referenced anywhere in the checked
term (not a minimized logical dependency set). Successful open assumptions are
always empty. `checks` counts visited inference nodes, including partial work
on failure; it is not a confidence measure.

Rejected inputs return `ok: false`, a finite `error` code, null conclusion,
empty premise/assumption lists and empty hashes. Empty assumption lists on
failure do not assert that a derivation was closed. Codes describe shape/type,
name/scope, inference mismatch, goal mismatch, version, Unicode, cycle, or
resource failures; they never echo caller text. No RecursionError escapes.
Parser and renderer instead raise `ProofError` with a finite code.

Success hashes are SHA-256 of compact, sorted-key, UTF-8 JSON (ensure_ascii=False):
`premises`, `goal`, `certificate`, and `judgment`. The judgment hashes
`[VERSION, LOGIC, premises, goal, certificate]`. These bind unused premises too;
they are content identities, not signatures or implementation/source pins.
Receipts are detached from caller inputs. Callers must not mutate inputs during
verification. Only exact built-in dict/list/str types and the certificate integer
are accepted; Python subclasses and non-JSON objects are refused.

Fixed limits are public constants: MAX_DEPTH=64, MAX_NODES=20,000,
MAX_BYTES=262,144, MAX_TEXT=4,096, MAX_WORK=200,000. The iterative preflight walks
**all** inputs together inside `[premises, goal, certificate]`, including unused
premises, keys, repeated occurrences of shared objects and unknown fields.
Depth starts at zero on that envelope. Byte accounting conservatively charges
JSON-escaped UTF-8 string bytes plus punctuation per visited value; it is not a
wire-size promise. Cycles fail. Each inferred formula is independently bounded,
and its expanded node count is charged to aggregate work, preventing inferred
or shared-tree expansion from bypassing limits. Resource refusals do not mean a
proposition is unprovable. There are no configurable unbounded modes.

## Human-readable formulas

`parse_formula(text)` accepts JSON double-quoted propositions and lowercase
`false`, `not`, `and`, `or`, `implies`, with parentheses. Precedence, highest
first: `not`, `and`, `or`, `implies`. Implication associates right; conjunction
and disjunction associate left. `not A` desugars to `A implies false`.
Quoted `"false"` is an atom; bare `false` is falsity. JSON escapes are supported.
No bare propositions or natural-language interpretation are accepted.

`render_formula(formula)` fully parenthesizes binary operators and JSON-quotes
atoms. For accepted renderings, parsing reconstructs the exact AST. Input text,
tokens, recursive parsing and resulting ASTs are bounded. Excess parentheses can
hit the parser depth bound even when they describe a small formula.

## Existing Symblic 2.5 integration

The pure checker remains separate from the language adapter. In the installed 2.5 runtime,
`symblic/adapters/proof_adapter.py` exposes `proof_check`, `proof_valid`, `proof_parse` and `proof_render` through
`symblic/kernel/language.py`'s fixed lazy `ADAPTERS` table. Each wrapper charges the existing kernel budget and converts
exact native values without handing the candidate authority over the goal or premises. Integral
Symblic rationals may represent the integer certificate version; booleans and arbitrary numeric
coercion are not accepted as proof values. The wrapper adds `valid` as the language predicate while
retaining the pure receipt's `ok`, and names its scope `derivation_from_declared_premises`.

```symblic
use profile=verified.
let goal = proof_parse('"P" implies "P"').
let certificate = {version: 1, proof: ["implies_intro", "h", ["atom", "P"], ["hypothesis", "h"]]}.
let checked = proof_check({:}, goal, certificate).
assert checked.valid and len(checked.used_premises) = 0.
```

`{:}` supplies an empty record of premises; `{}` is still an empty set. The certificate above is
human-written. A model can construct the same certificate type through a normal explicit ask followed
by a checked retry contract. Direct computation remains available too; the checker does not generate
missing steps or search for a derivation.

The operator-only `POST /api/automation/symblic/logic/compile` interface and Logic tab compile named
controlled-formula premises and a goal into an ordinary program. `symblic.adapters.logic.compile_task` makes no
provider call. The returned program declares `profile=verified`, holds authoritative inputs outside
the candidate, asks for a proof term and checks `verification.valid` through the existing bounded
escalation/retry route. `calls` is an explicit 1–6 budget. Supplying `domains` selects the finite frontend
([FINITE-LOGIC](FINITE-LOGIC.md)); omitting it uses propositional syntax.

The kernel identity includes proof-checker, adapter, finite-frontend and profile versions. Both
`symblic.kernel.execution_pins.PYTHON_FILES` and `REQUIRED_FILES` include the checker, finite frontend, adapter and
profile implementation. Those optional execution pins bind source implementations; proof receipt
hashes alone do not replace them. Source/kernel/module compatibility, context manifests, retry
snapshots and evidence lineage use the existing runner rather than a separate proof-execution store.

These wrappers and the compiler have isolated fake-constructor and kernel-only checks. They are
implemented and included in live RC2; this is not a real-model theorem-proving success measurement.
A checked derivation remains conditional on its used premises. Proof receipts are distinct from
`symblic.kernel.certificates`, whose scope is observed named tests. See [SPEC](SPEC.md), [LANGUAGE-3](LANGUAGE-3.md)
and [REFORM-3](REFORM-3.md) for operational profiles and component status.

Verification uses all inference rules, lexical and branch mutations, malformed
and oversized inputs, parser roundtrips, and independent exhaustive Boolean
interpretation across generated small formula/proof families. Boolean validity
is necessary but insufficient for intuitionistic derivability. Passing tests
is **not a proof of checker soundness**; the checker still warrants
independent rule/implementation review despite passing these implementation checks.
