# JavaScript checks (`js_test`, `js_run`)

`symblic/js/check.py` lets a program check JavaScript. The usual case is code a model wrote in a `Code js` ask, tested
against examples the author wrote. Running the code is how the kernel decides whether an answer passes. No model is
asked, and no judgement is made beyond the examples.

```symblic
ask add: Code js "Write a JavaScript function add(a, b) that returns a + b." by "ollama:qwen3:4b-instruct".
let t = js_test(add, [["add(2, 3)", "5"], ["add(-1, 1)", "0"]]).
ensure t.passed else retry because t.report.
```

A unit written by a small model can be asked as `Code js unit NAME reusing A, B` (2026-10-10): the kernel then
takes the fenced block that declares NAME, restores a dropped `function` keyword, and cuts the answer's own
top-level copies of the reused names before binding it (`symblic.js.normalize`, parse-only Acorn). The bound text
is what js_test tests and what the file holds. A plain `Code js` answer is unchanged.

## What it computes

- **`js_test(source, cases)`** returns the record `{passed, total, failed, report}`.
  - `source` is a text, or a list of texts (pieces). Pieces run in order as separate classic scripts in one realm,
    like consecutive `<script>` blocks: each piece's `const`s and functions are visible to the pieces after it.
    - A piece that replaces a function an earlier piece defined fails with "it defines f again" (adapter 3). A
      classic script lets a function be declared twice and silently keeps the last one. In the Tetris build, a
      unit that pasted in its own copies of two earlier units' functions broke every check after it.
      Adapter 9 also rejects duplicate global function declarations before execution: some Node versions silently
      ignore a declaration after the earlier binding is protected. A pinned Acorn 8.8.1 parser reads ECMAScript
      2022 scripts, including escaped names, async/generator declarations and sloppy block functions that can
      create global bindings. Nested functions, local block bindings and same-piece classic declarations retain
      their ordinary scope. Candidate code cannot replace this parser or its declaration records.
      Adapter 10 also resolves identifier writes against lexical and function scopes. Assignments,
      updates, destructuring, loop targets and deletes that resolve to prior global callables are
      rejected before execution. Deferred writes in function bodies, defaults and instance fields
      are checked against the call-time globals, including functions from the same piece. This is
      a conservative capability check: unreachable writes can also be rejected. Local shadowing,
      mutable data and first-piece initialization retain their ordinary behavior.
      Where property access, destructuring, classes, legacy reflection or `with` can bypass that
      resolution, a second independent realm runs with the artifact's normal writable bindings.
      Retained callable replacements or different serialized example results reject the candidate.
      This comparison covers the supplied examples; a temporary reflective change restored before
      observation with an identical result is not proof of a faulty example and can pass.
      The comparison is deliberately conservative: inspecting a dependency's writable/configurable
      descriptor can produce different results in protected and ordinary realms even without a write.
      Such a difference is refused; a `redefine` result from this comparison is not proof that the
      candidate attempted mutation. Native class-name scope, including its temporal dead zone in
      a class heritage expression, is preserved.
    - A `const`, `let` or `class` declared again fails as "already declared".
  - `cases` is a list of `[call, expected]` pairs, both text. `call` is a JavaScript expression, evaluated after
    `source`. `expected` is the JSON text of the value the call must give.
  - Values compare as JSON:
    - objects compare by key, regardless of order;
    - lists compare in order;
    - numbers compare by value, so `0.5` equals `0.50`;
    - `true` never equals `1`.
  - A NaN or Infinity result never equals the `null` that `JSON.stringify` would turn it into.
  - `report` lists up to six failing cases with the expected value and what came back: the value or a semantic
    error together with the text of the line where it happened ("in this line: ..."). It gives the line's text,
    not its number, because the tested source is usually several pieces joined (test helpers, earlier units, the
    answer). A number in that joined text sent 4B models looking in the wrong place. An error in an earlier piece
    says "in this line of the code run before it". When the code does not parse, or redefines a function, the
    report says so once. The installed adapter is version 12; the kernel identity names
    its version, Node version and frozen runner/sandbox/child-limiter/parser/license hashes.
- **`js_run(source, call)`** returns the JSON value of one call as a Symblic value: lists become lists, objects
  become records, numbers are read exactly from their decimal form. A semantic failure is an error of kind `js`; an incomplete check raises `resource` or `unavailable`.

## Isolation

The adapter has two layers. The OS sandbox is the boundary; the inner realm makes results depend only on the
inputs.

1. **The node process** runs inside `symblic/sandbox/landlock.py --require --no-unix --net-connect 1`:
   - Landlock: system directories read-only, node's own install read and exec, and an empty private scratch
     directory as the only writable place. The runner, pinned parser and its license are copied there, so the repository, `.env`,
     `secrets_data/` and the rest of `$HOME` are not visible.
   - No TCP: connect is allowed only to port 1, where nothing listens, and bind is denied. No unix sockets.
   - No new privileges, a new session and an environment built from scratch.
   - Node runs with a 256 MiB V8 heap and `--disallow-code-generation-from-strings`.
2. **Every case** runs in a fresh V8 context (node's `vm`):
   - The context is built from a null-prototype object, and nothing from the host realm is passed in. Only JSON
     text comes back, serialized inside the context.
   - The serializer captures its original intrinsics in an immutable lexical
     binding before candidate code runs. Replacing or shadowing `JSON`, `Number`
     or `String` cannot replace the checker's serializer. The name
     `__symblicEncodeResult` is reserved for that binding.
   - Earlier global callable bindings are protected against replacement,
     deletion and lexical shadowing before subsequent pieces and calls run.
     Host-retained descriptors check function identity without consulting
     candidate-controlled `Object`, `JSON` or `Symbol`. This protects bindings;
     ordinary mutable data, closure state and getter/setter behavior remain
     JavaScript semantics, and are assessed only by the supplied examples.
     Identifier-write preflight runs entirely in the trusted parser realm. Reflection checks use
     ordinary, separate VM contexts; no host Proxy, host exception, callback or callable is exposed
     to candidate code. Both executions retain the same per-script limits and share one bounded aggregate allowance.
     Retained callable changes are checked even when later source/call evaluation throws; a timeout
     or resource interruption remains inconclusive and cannot be reclassified as a candidate verdict.
   - Code generation from strings (`eval`, `new Function`) is off inside the context, which closes the
     constructor-chain escape.
   - `Math.random` throws, `Date` is fixed at 1700000000000, `console` is a no-op, and microtasks run within the
     time limit.

The second layer is not a security boundary on its own; node's documentation says so. It is there for
determinism: no clock, no randomness and no state shared between cases.

## Limits

- 3 s per case evaluation in each realm (and per loaded script), with one or two realms per case.
- A wall-clock limit for the whole check: 15 s plus 7 s per case by default. In general the
  allowance is `15 + cases * (2 * case_ms / 1000 + 1)` seconds, conservatively budgeting both
  protected and ordinary executions. An explicit/scoped deadline can only shorten it. This is
  an aggregate cap, not a guarantee that all individually bounded scripts in a suite will finish.
- A child-only CPU limit of the rounded-up wall allowance (at most 816 CPU seconds), and 2 GiB
  of address space. Long dual-realm suites can still exhaust that independent CPU ceiling;
  the observation is inconclusive. A smaller inherited limit stays in force. Address space includes Node
  reservations; it is not a measured RSS or aggregate cgroup memory ceiling.
- The limiter starts before the existing sandbox. Parent-death cleanup kills the owned
  child if its request worker exits; timeout/output overflow still kill and reap its process group.
- Stdout is capped at 8 MiB and stderr at 64 KiB during streaming. A caller may
  lower the stdout cap and supply one aggregate monotonic deadline. Overflow
  raises a budget error; the owned process group is killed and reaped.
  Trusted host code can enter `symblic.js.check.verification_deadline_scope(deadline)` with an
  absolute finite monotonic time. Nested scopes use the earlier deadline; leaving a scope
  restores the previous context, including after exceptions. JavaScript tests, `js_run`
  and declaration checks combine explicit deadlines with this inherited limit. A native
  candidate worker enters its own scope; thread pools do not implicitly inherit it.
  This bounds checker work during candidate evaluation as well as final host checks.
  Candidate text cannot extend the trusted limit.
- At most 200 cases, 400 000 characters of source, 4 000 characters per call and 200 000 per expected value.
- Declaration preflight parses each piece once with at most 100 000 tokens, 100 000 visited AST nodes and
  256 visited AST levels. Parser stack, memory or budget exhaustion leaves the check inconclusive.
- The kernel's step budget is charged 10 steps per case. The JavaScript itself is bounded by the time and memory
  limits, not by kernel steps.

A timed-out case is observed again before the check is called inconclusive (2026-10-11): up to
`REOBSERVE` (2) more rounds, each after a bounded wait (`CALM_WAIT_S`, 90 s, never past the
deadline) for the host's 1-minute load per CPU to drop to `CALM_LOAD` (1.5) and its I/O pressure
(`/proc/pressure/io` some avg10) to `CALM_IO` (40 %). Only cases of kind
`timeout` run again; a pass, a mismatch, a syntax or runtime error, a memory or unavailable
observation never does. A re-run row carries `reobserved: round`, and the `js_test` report
carries `reobserved: n` when any case was re-run. Why: 3 s of wall time on the host at load 38
(6 CPUs) is a fraction of a second of CPU; two Kirby build rounds failed "inconclusive" on
finite, trivial code without one repair request. A case that still times out after the last
round stays inconclusive, and the reason says how many re-observations were made.

A timeout, exhausted memory, interrupted child or unavailable runtime is **inconclusive**.
`js_test` cannot return a pass/fail verdict for that check: it raises `resource` (or
`unavailable` when the runtime cannot start). Run stops with that visible reason, without
repairing, escalating or rejecting the candidate. This also applies inside an inline
`ensure`, search/escalation validation and test blocks. An aggregate deadline/output
budget remains kind `budget` and likewise cannot trigger answer repair. A test row is
`inconclusive`, excluded from `failed`, and cannot certify a routine. The remaining tests
are not run after the resource interruption. A real mismatched result or syntax/runtime
error still fails the example normally. The low-level comparison API retains unresolved
observations, so missing evidence can never establish agreement.

Load can change whether a bounded check finishes. A completed finite observation is
separate from the ability to finish it; increasing a budget requires a new execution,
not automatic extra model calls.

## Determinism and identity

The adapter's version and the node version are part of `symblic.kernel_id()` (for example `js: 12+node22.17.0+assets…`):
another JavaScript engine may give other results. A host without node reports `9+node-none+assets…`, and a check there
fails with kind `unavailable`.

Availability additionally requires the current sandbox's network-isolation Landlock ABI (at least 4).
The read-only capability query neither starts Node nor installs sandbox restrictions in the caller.
A machine with Node but an older or unavailable Landlock ABI reports unavailable before any candidate
process starts. The child still enforces all filesystem, network, socket and process restrictions:
the preliminary check is necessary evidence, not a guarantee that every bounded execution will finish.

`js_test` and `js_run` are in `EVAL_DENIED`, so model text passed through `eval()` cannot start a process. They
are also in `SPECULATION_DENIED`: they run only when a check decides a real answer. `check`, static warnings,
empty-answer probes and enumeration never run them.

## What a pass does not establish

A pass establishes that the code gives the listed values for the listed calls under this engine, and nothing about
calls the examples do not make. Examples written by the same author as the specification can share its mistakes.
The adapter does not review code for safety, style or performance, and running untrusted code here is safe only
because of the sandbox above.

The observation is JSON serialization of the expression result. It preserves
ordinary `toJSON` behavior and maps top-level `undefined` to null; it is not an
observation of every possible property of a JavaScript value. No finite example
set establishes equivalence for inputs it never evaluates.


## CLI, preview and test process limits

`tools/symblic` enters `symblic/kernel/process_limits.py` before loading the interpreter. The CLI has
120 CPU seconds and 2 GiB address space, with no wall timer on admitted model waits.
The limits cover this local interpreter and its local children; provider/model services
retain their existing admission and resource policies. Already admitted calls tracked
by `symblic.providers.applicators` are cancelled on CLI exit. The helper can wrap other first-party
entrypoints using `python symblic/kernel/process_limits.py cli --file SCRIPT.py [args...]` or
`cli --module MODULE [args...]`.

HTTP preview and kernel-only tests run in separate children: preview allows 10 CPU
seconds / 30 wall seconds; tests allow 30 CPU seconds / 60 wall seconds. Each has
2 GiB address space, a 2 MiB request, 8 MiB stdout and 64 KiB stderr ceiling. Limits
are installed only by the executable child entrypoint. Importing the helper or calling
an API cannot change the dashboard's limits. A missing limit/cleanup facility refuses
work visibly rather than falling back to an unbounded process. Existing hosted run
units still have their 600 MiB cgroup/50% CPU envelope; these interpreter allocation
ceilings do not replace that aggregate protection.

The adapter bump and exact limiter bytes participate in kernel identity. Retain the
complete old runtime for existing records; do not relabel an old replay with version 8.
The 6 October availability repair changes adapter identity from 7 to 8. Start a fresh worker for the
new adapter; preserve old records and their original pins rather than silently resuming under new identity.
The 7 October declaration preflight changes adapter identity from 8 to 9. Existing execution pins already include
the exact Acorn and license assets; adapter 9 additionally freezes and copies those same assets for every JavaScript
check. Missing assets refuse execution, changed parser bytes refuse the pinned version, and later asset drift
requires a fresh worker. Preserve prior records and runtime snapshots; do not relabel their verdicts as adapter 9.
