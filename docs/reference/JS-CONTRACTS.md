# Optional JavaScript declaration contracts

`symblic.js.contract.check(source, contract)` parses one candidate script and
checks its exact top-level declaration surface. It never executes the candidate,
tests its function bodies, discovers an implementation, or replaces `js_test`.
The optional native entry point is `js_declarations_check(source, contract)`.
Hosts must register it and pin its runtime assets before using that entry point;
the native registration and pinned assets are included in the installed 5 October
reform. See the [5 October release evidence](evidence/2026-10-05-reform-install.json) for installation scope.

```json
{"version":1,"exports":{"advance":"function","State":"class","LIMIT":"const"}}
```

`exports` is an exact map of required top-level binding names to declaration
kinds: `function`, `class`, `const`, `let` or `var`. It allows at most 128 names,
each an ASCII JavaScript identifier of at most 128 characters (including `$` and
`_`). No extra fields or undeclared bindings are accepted. The term “exports”
here means the unit's declared names in a classic script, not ECMAScript module
`export` syntax. An empty map permits a script with no declarations.

This provides a concrete check for a task-card instruction such as “define only
the required functions.” It catches misspelled names, additional helpers at the
top level, duplicate declarations and wrappers that install names indirectly.
Helpers may instead be local to a required function when the project contract
permits that structure. Source and contract changes require a new receipt.

## The optional loading policy

Acorn 8.8.1 parses ECMAScript 2022 **script** syntax into an AST. The checker
inspects AST nodes; it does not infer declarations with regular expressions.
Its optional policy accepts:

- Function declarations, including async and generator functions. Their bodies
  and parameter defaults are parsed but never executed or behaviorally checked.
- Class declarations without inheritance, computed keys or static blocks.
  Ordinary methods, getters/setters, constructors and instance-field initializers
  are deferred code and may contain normal JavaScript. Static field initializers
  must meet the passive initializer policy below.
- `const`, `let` and `var` declarations with simple identifier declarators.
  Each name must have that exact kind in the contract. Uninitialized `let`/`var`
  are permitted; destructuring is outside this policy.
- Empty semicolons and a literal `"use strict"` directive.

Passive initializers are literals, numeric-literal unary `+`/`-`, templates
without interpolation, arrays of passive values, object properties with ordinary
noncomputed keys and passive values, function/arrow expressions, and class
expressions meeting the class policy. Object methods are deferred functions.
Calls, constructors, reads of other bindings/properties, spreads, shorthand
properties, computed keys, object getters/setters, interpolation and general
operator expressions are refused. For example, `const x = (() => work())()` is
a declaration syntactically but performs eager work, so this policy refuses it.

Top-level expression statements, assignments, loops, conditionals and other
executable statements are refused. Top-level returns and module import/export
forms do not parse in this script mode. A comment or string containing text such
as `function hidden()` does not create a binding. Escaped spellings such as
`function \u0066(){}` are resolved by Acorn to the actual identifier `f`.

These restrictions define this optional contract; they are not claims about
which JavaScript constructs are valid in general. Existing `Code`, `js_test`
and `js_run` behavior remains available without the contract. Acceptance does
not establish that loading can never throw, that later invocation is safe or
correct, that dependencies exist, or that the source meets the user's intent.
Continue to run independent examples and project-level checks in the existing
[JavaScript sandbox](JS.md).

## Isolation, bounds and identities

Only the fixed runner and parser execute. Candidate text reaches
`acorn.parse`; it is never sent to `eval`, `Function`, `vm`, `require` or an
operating-system command. The Python host copies frozen parser, runner and
`symblic/sandbox/landlock.py` bytes into an empty temporary directory, then uses the
existing required sandbox path: Landlock, no Unix sockets, the same restricted
network policy as `js_test`, a scrubbed environment, Node's installation read/exec
access, and string code generation disabled. If required isolation is unavailable,
the operation refuses. There is no unsandboxed fallback.

| Bound | Value |
| --- | --- |
| Source | 400000 UTF-8 bytes |
| Encoded request | 500000 bytes |
| Acorn tokens / scanned AST nodes | 50000 each |
| Scanned AST depth | 128 |
| Top-level declarations | 128 |
| Reported diagnostics | 32, with an explicit truncation flag |
| V8 heap | 128 MB (not a total process-RSS guarantee) |
| Parser subprocess wall time | 5 seconds, or a smaller caller deadline |
| Parser result payload | 65536 bytes |

Token counting runs during parsing; the AST bounds apply after parsing. A parser
stack overflow is a resource refusal. The wall/heap bounds cover parser work
before an AST is available. A timeout kills only the newly created parser process
group. The native adapter charges ten kernel steps before launching; its subprocess
limits are separate from that charge. Adapter 3 also inherits a trusted host
`symblic.js.check.verification_deadline_scope` deadline in both direct `check` calls and
the native builtin. An explicit later deadline cannot enlarge that scoped limit;
missing scope preserves the existing five-second parser cap. Native candidate
threads establish their own scope and restore it afterward. This is a resource
boundary, not additional evidence about candidate behavior.

The vendored parser is copied without modification from the installed
`/usr/share/nodejs/acorn/dist/acorn.js`, package version 8.8.1. Its SHA-256 is
`cb3b2d439857d6e4514d23a1219f6354c23498f5fa81fdf2691a5a9e53de43c0`.
The MIT/Expat notice and local package provenance are retained in
`symblic_js_contract_LICENSE.txt`. This is a pinned local version, not a claim
that it is the newest Acorn release. Changing parser grammar requires a reviewed
version/identity update.

The module freezes runner/parser/license/sandbox bytes per process and refuses
later disk drift before parsing. `VERSION` includes adapter version, Acorn version,
Node version and the combined asset identity. The receipt includes:

- `passed` and `status`: `accepted`, `invalid`, `budget` or internal `error`;
- bounded declaration rows, diagnostic codes, locations and fixed hints;
- `source_sha256` over the exact UTF-8 source;
- `contract_sha256` over the versioned, sorted, compact JSON contract;
- parser syntax mode/version, Node version, and each runtime asset hash;
- a bounded `report` suitable for explicit repair feedback.

An invalid declaration or syntax error is different from resource exhaustion.
Malformed caller contracts, missing isolation/runtime assets, asset drift and
malformed parser responses raise a typed `JsError`. Neither failure establishes
anything about the function's intended behavior. Receipts are content-bound
local observations, not signatures or portable authenticity certificates.

## Host integration

1. Register `FUNCTIONS['js_declarations_check']` from the new module. Include it
   in the same speculative-execution exclusions as the existing JS subprocess
   adapters; a static check must not start a parser subprocess.
2. Add the new Python module, runner, parser and license to the appropriate
   execution-pin/asset allowlists and bind the module's `VERSION` in kernel identity.
3. Only when the caller requests the contract, check the candidate unit's own
   source against its declared names. Do not apply one unit's export map to the
   concatenation of unrelated dependencies.
4. Require `.passed`, then run the unit examples and final project checks.
   Preserve the exact source/contract identities and resource status in evidence.
   Agreement or a passing example must not bypass a rejected declaration contract.

Tests use synthetic code, real isolated parsing and injected process failures.
They cover wrappers, wrong/duplicate names, eager initializers, classes,
comments/strings/escaped identifiers, context-free source identity, finite
diagnostics, parser limits, asset drift and refusal when sandbox startup fails.
They do not execute the candidate or measure model construction success.
