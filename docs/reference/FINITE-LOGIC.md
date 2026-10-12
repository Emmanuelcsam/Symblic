# Explicit finite-domain logic, version 1

`symblic/adapters/finite_logic.py` is a pure bounded front end to `symblic/adapters/proof.py`.
It implements **finite-domain expansion into intuitionistic propositional
logic**, not unrestricted first-order logic. A quantifier ranges over exactly
the caller's enumerated list. The user/model must construct a proof of the
expanded goal; the front end only substitutes domain members and checks source
well-formedness and resource bounds. It does not search for proofs, enumerate
truth assignments, evaluate predicates, or infer meaning from English.

## API and authority

```python
import symblic.adapters.finite_logic as F

# Explicitly supplied by the caller, not the candidate certificate:
domains = {'People': ['Ada', 'Ben']}
premises = {'everyone': F.parse_formula('forall x in People: Kind(x:People)')}
goal = F.parse_formula('Kind(People["Ada"])')

expanded = F.expand(domains, premises, goal)
# expanded['premises'] and expanded['goal'] are symblic.adapters.proof formula ASTs.
receipt = F.verify(domains, premises, goal, {
    'version': 1,
    'proof': ['and_left', ['premise', 'everyone']],
})
assert receipt['ok']
```

`expand(domains, premises, goal)` returns expanded premises/goal, source and
expanded hashes, finite domain sizes and conservative expansion bounds. It
raises `FiniteLogicError` with a finite code on invalid inputs.

`verify(domains, premises, goal, certificate)` returns a receipt and delegates
to the **unchanged** public `symblic.adapters.proof.verify` API. The certificate is exactly
that verifier's `{'version': 1, 'proof': Term}` envelope. Certificate fields
claiming domains, goal, premises or intermediate conclusions are rejected.
The front end never reads authoritative inputs from the certificate. Ordinary
proof-term annotations are **expanded propositional ASTs**, not source quantified
formulas; `expand` gives their exact representation. There are no extra witness
or quantifier proof rules. Existential witnesses are represented by ordinary
`or_left`/`or_right` introductions into the fixed expanded tree.

All inputs must be exact built-in JSON-like types, not subclasses, custom
objects or cyclic graphs. Callers must not mutate inputs during verification.
The pure frontend is integrated into the Symblic 2.5 runtime through the existing proof adapter and is
included in live RC2. The release does not turn finite expansion into unrestricted first-order logic or
claim model success. The original propositional verifier API is reused without new inference rules.

## Source JSON AST

Domains are a dictionary from ASCII identifiers to **ordered, duplicate-free
lists of strings**. Members need not be identifiers; even `""` is a valid
explicit member. The order is authoritative, determines expansion shape and is
included in source identities. Different domains are distinct sorts even when
they contain identical member strings.

Premises map identifier names to source formulas. Source formulas are:

| AST | Meaning |
| --- | --- |
| `['atom', text]` | Opaque quoted proposition |
| `['false']` | Falsity |
| `['and', A, B]`, `['or', A, B]`, `['implies', A, B]` | Binary propositional connectives |
| `['pred', symbol, [term, ...]]` | Predicate application, including zero-argument predicates |
| `['forall', variable, domain, body]` | Conjunction of body instances for domain members |
| `['exists', variable, domain, body]` | Disjunction of body instances for domain members |

Term ASTs have explicit types:

- `['var', variable, domain]`: a lexically bound variable of the named sort.
- `['const', domain, member]`: an explicitly typed member of a declared domain.

There are no function terms, implicit variables, built-in equality, arithmetic,
negation-as-failure, unbounded quantifiers, or automatic predicate facts.
Negation is implication to falsity. A predicate symbol's ordered argument sorts
and arity must agree across **all** source premises and the goal. Signatures
are determined from these caller-authored source occurrences; they are never
supplied by a candidate. No separate signature registry is required.

Undeclared domains, free variables, sort mismatches, constants outside their
domain and any active variable shadowing are errors. Reusing a binder in separate
scopes is allowed. Substitution uses an environment keyed by validated lexical
variables and replaces typed term nodes only, never string fragments. Member
strings such as `"x"` cannot capture variables. Validation visits bodies even
under empty quantifiers, so emptiness cannot conceal ill-formed source.

Identifiers (domains, predicate symbols, variables and premise names) match
`[A-Za-z_][A-Za-z_0-9]*`, are at most 64 characters, and exclude syntax keywords.
Strings are exact NFC Unicode; non-NFC strings are **rejected**, never silently
normalized. Surrogates, format characters (including bidi overrides/zero-width
controls), and control characters except newline, CR and tab are rejected in
source text values. Non-ASCII identifier lookalikes are rejected. Ordinary
non-ASCII member/proposition text remains supported. The parser uses ASCII
whitespace outside quoted strings. This is a formal spelling policy, not a
claim to resolve all visually confusable prose.

## Controlled human syntax

```text
forall x in People: Kind(x:People)
exists x in People: Kind(x:People) and Knows(x:People, People["Ada"])
(forall x in People: Kind(x:People)) implies "Everyone on this list is kind"
```

Variables use `x:People`; constants use `People["Ada"]`. Predicate arguments
must always be explicitly typed. JSON double-quoted standalone strings are
opaque propositions. Thus `"Kind(x:People)"` does not mean `Kind(x:People)`.
Quoted English makes no automatically inferred assertions about predicates.

Highest-to-lowest connective precedence is `not`, `and`, `or`, `implies`.
Implication associates right; `and` and `or` associate left. A quantifier body
extends to the end of the current parenthesized expression (or input), including
all binary connectives. Parenthesize the quantifier to end its scope early.
`not` desugars to implication to false. Bare `false` is falsity; `"false"` is an
opaque proposition. Keywords are lowercase. `parse_formula(text)` constructs
source AST only; `expand`/`verify` perform caller-domain and scope validation.
No natural-language parsing or implicit spelling conversion is attempted.

## Exact lowering and namespaces

Ground predicate applications become propositional atoms whose text is compact
UTF-8 JSON of `['predicate', symbol, [[domain, member], ...]]`. Quoted source
propositions become atoms whose text is compact JSON of `['proposition', text]`.
Both namespaces are encoded, so no caller string can impersonate a predicate by
looking like its encoded text. Domain sorts and argument positions are retained.
No hashing is used for atom identity and no predicate interpretation is assumed.

Universal instances are joined by `and`, existential instances by `or` in
caller list order. Trees are balanced: split each contiguous range at
`(start + end) // 2`, recursively joining the left and right ranges. For one
member, use the body directly. For no members, `forall` is
`['implies', ['false'], ['false']]` and `exists` is `['false']`.
This is empty-domain finite semantics, not a nonempty-domain first-order axiom.

## Bounds and receipts

Preflight scans every input, including unused domains/premises, repeated shared
subtrees and the certificate. Bounds: source envelope depth 48, input nodes
12,000, conservatively counted input bytes 262,144, source text 1,024 characters,
128 members per domain and 1,024 members in total. Certificates may use expanded
atom text up to the original verifier's 4,096-character bound. Exact integer 1
is required for certificate version; bools/floats are rejected.

A structural analysis computes aggregate expanded formula nodes, conservative
UTF-8 JSON output bytes and expansion work **before materializing any Cartesian
product**. Limits are 8,000 output nodes, 100,000 output bytes, and 50,000 expansion
work units. Formulas from all premises and the goal share these limits. The
analysis checks bodies even when a multiplier is zero, but does not materialize
those bodies. Predicate byte estimates conservatively include namespace escaping
and the widest member of each referenced domain. Limits can refuse an otherwise
small actual expansion. Generated formula depth/text are also checked locally
against downstream limits; the original verifier retains all its independent
combined input/inference limits. `expand` succeeding does not promise that an
arbitrarily large certificate will fit those limits.

Receipts include `version`, `logic`, `ok`, `conditional_on_domains: true`,
`conditional_on_premises: true`, `consistency: 'not_checked'`, `proof_receipt`,
and `hashes`. Once expansion succeeds they include `domain_sizes` and
`expansion_bounds` as well. Errors are finite codes with no caller text. Source
failure yields no proof receipt; proof failure returns the original failed
receipt under `proof_receipt` and outer `error: 'proof_rejected'`. No
RecursionError escapes. Returned outputs are detached from inputs.

Hashes use SHA-256 over compact, sorted-key, ensure_ascii=False UTF-8 JSON:

- `domains`, `premises`, `goal`: the complete respective caller source inputs.
- `source`: `[VERSION, LOGIC, domains, premises, goal]`.
- `expanded_premises`, `expanded_goal`: the respective lowered inputs.
- On success, `judgment`: `[VERSION, LOGIC, source_hash, proof_judgment_hash]`.

The embedded proof receipt carries the original proof version, logic, checks,
conclusion, premise dependencies and certificate/expanded-judgment hashes.
Changing even an unused domain changes the outer identity. A proof may remain
valid under some changed caller inputs; that produces a **different judgment**,
never evidence that the earlier domain declaration was preserved. Consumers must
compare source/judgment hashes to their trusted expected inputs, not just accept
`ok` from an untrusted stored receipt. Hashes are not signatures or source pins.

Success is conditional on the declared finite domains and premises. It does not
establish that a domain is exhaustive in reality, any predicate or quoted
proposition is true, or premises are consistent. Explosion remains available
from false premises. This package does not attempt to prove unrestricted
first-order theorems or discharge real-world modeling assumptions.

## Verification and integration boundary

Tests independently interpret the source finite quantifiers over every Boolean
interpretation for small domains and compare to the expanded formula. They also
exercise actual proof certificates, empty/singleton domains, two-domain lexical
substitution, namespace separation, source identity/domain changes, schema and
Unicode rejection, and pre-materialization Cartesian-product limits. Boolean
interpretation tests are evidence about lowering, not a proof of intuitionistic
checker soundness or a runtime decision procedure.

The installed 2.5 integration exposes `finite_parse`, `finite_expand` and `finite_check` through
`symblic/adapters/proof_adapter.py` and the fixed lazy adapter table. `finite_check(domains, premises, goal,
certificate)` keeps the first three inputs under caller authority, charges the existing kernel budget,
and adds `valid` plus scope `derivation_from_declared_finite_domains_and_premises` to the pure receipt.
Kernel identity and optional source execution pins include this frontend, the proof checker and wrapper.

```symblic
use profile=verified.
let domains = {People: ["Ada", "Ben"]}.
let premises = {everyone: finite_parse('forall x in People: Kind(x:People)')}.
let goal = finite_parse('Kind(People["Ada"])').
let certificate = {version: 1, proof: ["and_left", ["premise", "everyone"]]}.
let checked = finite_check(domains, premises, goal, certificate).
assert checked.valid.
```

The Logic tab accepts optional finite-domain JSON. Its operator-only `logic/compile` API receives
`premises`, `goal`, `calls` and optional `domains`; compilation parses and bounds the task without
calling a model. The emitted verified-profile program supplies the expanded formulas and generic proof
rules as required context, asks a model to construct a certificate, then checks it against the original
caller domains/premises/goal through `finite_check`. The normal bounded retry route handles rejected
candidates. This is proof construction followed by checking, not kernel proof search.

Kernel-only and injected-constructor compiler/API tests cover this integration. They do not establish
checker soundness, empirical truth, unrestricted first-order capability or real-model success rates.
The implementation is live in RC2; these limits still apply to the deployed path.
See [SPEC](SPEC.md), [PROOF-TERMS](PROOF-TERMS.md) and [REFORM-3](REFORM-3.md) for current status.
