# Symblic effects — `observe` and `act`

Symblic 2 has one statement that leaves the kernel: `ask`, a typed question to a model. This document specifies
two more, added by `symblic/kernel/effects.py` through the extension hooks (no kernel edit):

    observe NAME [: TYPE] = family.name(arg = expr, ...) [with OPTIONS].
    act    [NAME [: TYPE] =] family.name(arg = expr, ...) [with OPTIONS].

`observe` reads the world through a declared capability. `act` changes it through one. Code: `symblic/kernel/effects.py`;
tests: `tests/kernel/test_symblic_effects.py` (fake host only). The host that connects them to this site is the host executor
(`the host executor specification (not included)`).

## 1. Why three statements

The three differ in what must fit what (Searle's *direction of fit*, after Anscombe's shopping list):

| statement | says | fit | what the interpreter can check |
|---|---|---|---|
| `ask` | a model's judgment | words must fit the world, as the model believes it | the type, and the checks the program states |
| `observe` | what an instrument reported | words must fit the world, as the instrument measured it | the type, the capability, the arguments, the time, the result hash |
| `act` | a change to make | the world must come to fit the words | that it was requested once, and what the service answered |

An ask and an observation can both be wrong, but in different ways: a model can misremember, an instrument can
be broken or stale. Agreement between two models reading the same text shares that text's faults; an
observation acquired by the interpreter through a different route does not share the model's. That is the
reason to keep them apart in the record (§6), and it is the only sense in which this document speaks of
independent evidence. Nothing here measures independence.

## 2. Syntax

- The capability is a dotted lower-case name (`calendar.free_busy`). Arguments are named; values are any
  kernel expression. A sentence that merely starts with the word ("Observe the sky.") stays prose.
- `observe` must bind a name. `act` may.
- A type after the name reads the result like a model's answer (`symblic.coerce`): records keep only the named
  fields. Without a type the result is bound as it came.
- Options (`with`): `key` (text naming this action, §4), `scope` (`run` or `program`, §4), `timeout` (seconds),
  `mode` and `sources` (evidence labels, §6), `weight`, and for `act` only `allow_untrusted` (§5).
- Neither statement may appear inside a `function`, `routine` or `test`. An `act` may not stand between an `ask`
  and the `ensure ... else retry` that may re-ask it; an `observe` may (ask a query, look, re-ask).

## 3. Capabilities and typing

A host declares a **catalogue**: for each capability its effect class (`read`, `compute`, `write-local`,
`write-external`, `device`, `destructive`, `money`), approval policy (`auto`, `confirm`, `never`), a JSON
Schema for its arguments, and the flags `idempotent`, `untrusted` (it returns text someone outside controls),
`sensitivity`, `egress` (its arguments leave the machine) and `instructs` (its arguments are instructions an
agent or a program then follows: start an agent, run a program).

`symblic.kernel.effects.check(source, catalogue)` is `symblic.check` plus, from the text alone:

- the capability exists; `observe` is used only for a `read`; a capability with policy `never` is refused;
- argument names are the declared ones, required ones are present, literal values fit the schema;
- placement (§2) and information flow (§5).

At run time every argument is evaluated by the kernel and checked against the schema before the host is
asked. The schema subset: `type, enum, const, properties, required, additionalProperties, items, minItems,
maxItems, minimum, maximum, minLength, maxLength, pattern`. `true` is not `1`. Every element is checked; a
value over 50 000 nodes, 32 levels or 1 MB is refused, never truncated.

A run is **pinned** to the capabilities it names as they were when it began: they are frozen in
`effects-catalogue.json` beside the ledger (`{version, digest, capabilities}`). If one of them changes
(effect, policy, arguments, flags), the run refuses to continue; the rest of the catalogue may grow. The
contract of a capability is `effect, policy, params, idempotent, untrusted, sensitivity, egress, instructs`
(`CONTRACT_KEYS`); the same digest pins every attempt in a ledger, so the pin also holds between different
runs that share a program's ledger (§4, Recovery).

## 4. Execution: the ledger

Identity of an observation, and of an action without a key: `effect_id = SHA-256([2, capability, canonical
arguments, key])`. It says what is asked of the world, not where in the program. So in one ledger the same
call with the same arguments happens once.

An action WITH a key is its key: `effect_id = SHA-256([2, capability, null, key])`. `act ... with
key="digest-2026-10-03"` names one action; a later call under that name is the same action whatever its
arguments say by then (a count that moved, a text a model rewrote), and it is served the recorded outcome
with a note in the trace. Two deliberate actions get two keys. A key that cannot change inside a `for` is
reported as a warning, because the action then happens once for the whole loop.

**Recovery.** An attempt that was interrupted, or whose outcome is unknown, may still have happened. When a
later run reaches the same identity it does not start a similar action beside it: it continues THAT request,
and the request is one record. Every row of an attempt (intent, outcome, the operator's resolution, a run's copy)
carries its arguments and their hash, the full contract of the capability as it was (`spec`, `spec_sha256`),
the source that wrote the arguments, and how it had to be approved (`influence`, `influence_origin`,
`needs_owner`). The continuing run sends those arguments under those labels; its own statement can raise the
requirements and never lower them. An action is continued only when the record is complete, matches its
hashes, and the capability's contract is unchanged; the arguments are checked against the schema again before
they are sent. Otherwise (the capability changed, an older writer left a row without its contract or labels,
the arguments no longer fit) nothing is sent and nothing new is written: the run stops as `uncertain`, the
standing row keeps saying unknown, and only the operator's word settles it. An unknown is never rewritten as
`failed` by a run that performed nothing, because `failed` permits a fresh attempt with other arguments.
After a definite failure a new attempt is a new request and uses its own arguments and labels. A read is
simply asked again.

`effects.jsonl` in the run folder is append-only, one JSON row per line:

1. **claim**: under an exclusive lock, the file is re-read and an `intent` row is written and synced, unless
   an outcome or someone else's live intent already stands;
2. the host performs the call;
3. an outcome row is written: `done` (with the result and its hash), `failed` (the host says nothing
   happened) or `unknown` (it may have happened).

Rules that follow:

- **Resume and retry** take a `done` outcome from the ledger and call nothing. The served row must match the
  hashes written with it, else the ledger counts as altered and nothing is served.
- **Replay** (`replay` option) never calls anything, needs no host, reads only the run folder, and refuses a row
  recorded under another program text. A resume, in contrast, may continue an edited program: an action must
  not fire again because a line moved.
- **Preview** stops at the first observe/act.
- **Unknown outcome**: for an `act` whose capability is not idempotent, the run stops (`uncertain`) until the
  operator says whether it happened (`symblic.kernel.effects.resolve`). A read, an idempotent action, or any call
  through a host that is idempotent by effect id (it hands the id to the service as its request id) is started
  again.
- **Shared ledgers** (`scope=program` with a `key`): runs of the same program share one ledger, so "send
  today's digest" happens once however often the program runs. Runs claim atomically across processes; a run
  that meets a live claimant waits for its outcome and takes it. Each run copies what it used into its own
  folder, so its replay needs nothing else.
- A row that cannot be read marks the ledger damaged: recorded outcomes are still served, nothing new is
  performed. An unfinished last row is cut off (no call follows an unfinished intent).
- `side_effects` must be allowed by the host for any `act`; a run has a limit on observations plus actions,
  counted over the whole run folder, so a resume does not get a fresh allowance.
- The host is told how often an action already ended `failed` (`failures`), so it can make the next attempt
  a new request while an attempt after an interruption stays the same request.
- An unfinished action of the program's ledger (`unknown`, or another run's standing intent) is copied into
  the run's own ledger, so the run can show what blocks it and the operator can resolve it from there.

What this is, exactly: **at most one automatic performance per identity, with explicit uncertainty.** It is
not exactly-once. The world can act and the record be lost; then a person, or a service that remembers the
request id, decides.

## 5. Information flow

Three labels on values, computed from the program text:

- `untrusted`: text someone outside controls. It comes from capabilities declared `untrusted` and follows
  every value computed from it: through `let`, through facts, and through an `ask` that was shown it (by
  interpolation, `from`, or a wide context).
- `steered`: what `untrusted` becomes when it passes through a closed type (`Bool`, `one of {...}`, a small
  `Int` range), and what a condition or a loop over such data puts on the statements inside it. The outside
  text then only chose among alternatives the program itself wrote.
- `personal`: data from capabilities with a non-public sensitivity.

Rules:

1. An `untrusted` value may not be an argument of an `act` (nor the task of a `delegate`). Outside text never
   writes an action. An author may name an argument in `allow_untrusted=["arg"]` where the text is meant to be
   carried (a note that stores a page, a message that forwards one); the act's influence is then `untrusted`.
   For a capability that `instructs` there is no such exception: outside text is never an agent's or a
   program's instructions.
2. A `steered` act is allowed and reported (`influence`, `origin`). The host is told `needs_owner` when outside
   text chose the action (`steered`) or wrote part of it (`untrusted`) and the capability is weighty: a
   consequential effect class (`write-external`, `device`, `destructive`, `money`) or one that `instructs`.
   The host executor approves a steered one only under the operator's standing setting, and one that outside text wrote
   never: the operator reads the exact words first.
3. A `personal` value may not be an argument of a capability with `egress`.
4. An `ask` shown personal data is a warning naming the applicator.
5. A value read with an `untrusted` argument is `untrusted` too: a tool may hand its arguments back (a search
   that quotes its query), so passing outside text through a read does not wash it.

What a value reads (2.3; until then each gap below passed the check with influence `none`):

- A call reads its arguments and what its callee reads: the free names of a function's or routine's body
  (its own parameters excluded, never a caller's) and of its defaults, looked up when it is called, joined
  with what its defining scope held when it was defined (a function defined in a loop keeps that pass's
  value after the name is bound again outside), and with the condition or loop that chose to define it.
  Calls are followed transitively, recursion included. A callee that queries carries the knowledge base's
  labels; facts a routine asserts join it; a `delegate` inside a routine is checked where the routine is
  called. A library module's callables read only their arguments, unless the module queries the knowledge
  base, asks with a wide context (its own or the program's `use` default) or calls back into the program; a
  call the check cannot resolve (a saved module, a name nobody defined) is treated as reading everything.
- An `ask` reads every option it evaluates (`examples=` is shown to the model). Its context is its own
  option; else, inside a routine that sets `with context=`, that option (for the routines it calls as well);
  else the program's `use context=` (once a wide default appears, later asks without their own option count
  as wide).
- A loop variable is the item inside the loop only: after `end`, a binding of the same name outside reads as
  it did before.
- Exactly one branch of an `if` runs: each branch starts from what was bound before the `if` (not from a
  sibling branch), reaching a branch is decided by its condition and every condition above it, and afterwards
  a name carries what it carries on any path.
- A rule reads the bindings it names when a query derives from it, so every later query reads them; a
  `given` without an input reads its default; a `context=[...]` item that is not a bare name (its text names
  the binding) counts as a wide context.

Limits, stated plainly. The analysis is per statement and conservative; it has no proof of noninterference.
A closed type bounds what outside text can cause to the program's own alternatives; it does not make the
choice trustworthy (a hostile message can still say "choose delete"), which is why rule 2 exists. It does not
model timing, termination, or how often a loop runs beyond marking the loop body steered. The planner that
writes a program is trusted input from the operator; if the operator pastes hostile text into a request, nothing
here detects it.

## 6. Evidence

Every bound result carries `meta.evidence`:

    {mechanism: "observation" | "effect", capability, effect_id, args_sha256, result_sha256, acquired_at,
     trusted_acquisition: true, replayed, declaration: {mode, sources, origin}, untrusted, sensitivity,
     independence: "not_established"}

`trusted_acquisition` means the interpreter obtained the value through the host; no model asserted it.
`mode` defaults to `capability:<family>` and can be declared by the author. These are records of method and
source, not weights: nothing counts votes, and `independence` is never established by this module.

## 7. Host interface

    host.catalogue() -> rows                     # optional; else the process's catalogue is used
    host.perform(effect, stop) -> {"status": "done", "result": ..., "receipt": ...}
                                | {"status": "failed" | "denied", "error": ...}      # nothing happened
                                | {"status": "unknown", "error": ...}                # it may have happened
    host.idempotent_by_id = True                 # optional: perform() for the same effect id continues, never repeats

`effect` = `{id, kind, capability, args, key, line, scope, effect, policy, idempotent, attempt, failures,
timeout, influence, influence_origin, needs_owner}`. A host that sets `idempotent_by_id` promises it for every
run that shares the ledger, not only inside one run. Run options read: `effects` (the host), `effects_ledger` (path of a
program ledger), `max_effects`, `effects_wait`, and the core's `side_effects`, `replay`, `preview`.

## 8. Related work (each checked at its source on 2026-10-03)

The parts exist; the claim here is only about their combination in one small statement language.

- Debenedetti, Shumailov, Fan et al., *Defeating Prompt Injections by Design* (CaMeL), arXiv:2503.18813, 2025:
  control and data flow are extracted from the trusted query so untrusted data cannot change the program,
  with capabilities against exfiltration. Closest to §5 and to planning before reading outside text.
- Costa, Köpf, Kolluri et al., *Securing AI Agents with Information-Flow Control* (Fides), arXiv:2505.23643,
  2025: confidentiality and integrity labels with deterministic enforcement. Closest to the labels of §5.
- Wu, Cecchetti, Xiao, *System-Level Defense against Indirect Prompt Injection Attacks: An Information Flow
  Control Perspective*, arXiv:2409.19091, 2024: structured plans plus a security monitor.
- Beurer-Kellner, Buesser, Creţu et al., *Design Patterns for Securing LLM Agents against Prompt Injections*,
  arXiv:2506.08837, 2025: plan-then-execute, dual LLM and related patterns. A tool-less model reading outside
  text and returning a fixed category is one of them, so "closed values cross the boundary" is not new.
- Shi, He, Wang et al., *Progent: Securing AI Agents with Privilege Control*, arXiv:2504.11703, 2025: symbolic
  policies over tool calls and their arguments, enforced deterministically.
- Meyerson, Paolo, Dailey et al., *Solving a Million-Step LLM Task with Zero Errors* (MAKER), arXiv:2511.09030,
  2025: extreme decomposition with voting. A contrast, not an ancestor: it relies on agreement between model
  calls, which §1 does not count as independent evidence.
- Durable-execution engines (Temporal, Restate, Azure Durable Functions) journal external results and serve
  them on replay, and their own documentation warns that an activity can run more than once before its result
  is recorded. §4's choice for that window is to stop and ask. Not checked at source by me: stated from an
  outside review (`fable-gpt-priorart-review.txt`, private); verify before citing.
- Effect systems (Koka, Eff), classic information-flow languages (JFlow/Jif, LIO) and object capabilities (E)
  are the programming-language background for §3 and §5. Also from that review, not checked at source by me.
- J. R. Searle, *A Taxonomy of Illocutionary Acts* (1975) for directions of fit, and G. E. M. Anscombe,
  *Intention* (1957, §32) for the shopping list. Cited from memory of the standard texts; page details not
  checked for this document.

Claims this document does not make: first typed tool language, first use of information-flow control for
agents, first plan-then-execute design, exactly-once effects, or that a closed type makes a value trustworthy.
