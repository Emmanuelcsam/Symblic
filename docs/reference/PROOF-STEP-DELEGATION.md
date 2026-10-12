# One checked proof step per delegated child

`proof_step` is an optional catalog template, `symblic.delegate/proof_step/6`.
A parent gives a child its caller-owned session and an exact ordered list of
commands. The child returns a one-based choice number. Native indexing retrieves
that unchanged command, and `proof_session_command` checks its inference against
the original session. No command is synthesized, corrected, ranked or removed.

The template uses the native `determine=false` option to keep inference construction with the model.
It has no measured model-quality result yet.
The completed 12-cell command-Text versus command-Enum experiment used a different
interface; its results do not measure this ordinal interface.

## Request and authority

```python
task = {
    "template": "proof_step",
    "params": {
        "session": caller_owned_session,
        "commands": ["and_left s1", "premise a", "implies_elim s2 s1"],
        "require_complete": False,
    },
    "calls": 3,
    "capsule": "compact",
}
```

The parent owns the premises, goal, checked prefix and menu. A self-consistent
session hash is an integrity binding, not authentication or permission to adopt
another parent's state. The application remains responsible for caller access.
Before any model call, the compiler rechecks the whole prefix, refuses a completed
or exhausted session, and parses every command against that same prefix. A legal
but mathematically invalid command stays visible for the native checker to reject.
Commands that refer to unknown premises or future lines refuse the whole request.

Supply 1–32 unique exact command strings. Their order, whitespace, punctuation,
Unicode and quoting are retained. Singleton menus and distinct commands that
normalize to the same spelling are supported because the model chooses an integer,
not a string Enum. The bounded integer follows the existing recorded strict numeric
wire policy, which can normalize exact numeric strings. Caller commands never
become source text; they remain separate input data.

`require_complete` defaults to `false`: acceptance establishes one valid partial
step, and the parent must inspect `inference.complete` before claiming a completed
proof. With `true`, a valid nonclosing step is rejected by an anchored native check.
Whenever a selected step closes the goal, its certificate is independently checked
again with `proof_steps_check` before returning an accepted result. Conclusions
remain conditional on caller premises; premise truth and consistency are unassessed.

## Execution and accepted output

The compiler pins `context=none`, strict coercion, `determine=false` and `solve=false`.
No pre-dispatch inference enumeration, empty-answer inference probe, host selection
or correct-choice filtering is permitted. Native retry/escalation checks actual
model proposals under the caller's call ceiling. The default local route and all
existing limits remain unchanged: 3 calls (allowed 1–6), 24,000 context characters,
200,000 kernel steps, no side effects, parallelism 1. Full capsules remain the
default; compact capsules remain an explicit option. Required context overflow
refuses before dispatch. No wall-time guarantee is invented by this template.

The accepted canonical value has these fields:

| Field | Meaning |
| --- | --- |
| `choice` | Bounded one-based selection |
| `command` | Exact caller command at that index |
| `menu_member` | Native membership result, true for an accepted selection |
| `inference` | Whole unchanged native append receipt, including validity, completion, step, state and optional certificate |
| `handoff` | Exact source-session SHA-256, ordered-command SHA-256, menu ID, completion requirement and caller-authority boundary |

The normal wrapper retains `contract_id`, `routing_id`, execution pins, native
receipts, result encoding and call accounting. A failed run exposes no accepted
canonical result. Bind `expected_contract_id` when handing a reviewed task to a
child; changes to the source session, menu order, requirement, limits or presentation
change the compiled contract ID. Hashes alone are not remote-agent authentication.

See [the runnable task](../../examples/proof-step.task.json) and
[the parent-to-child example](../../examples/proof_step_handoff.py). It runs three
fresh fake children and rechecks only each returned selection before adopting the
next state. The helper compares the unchanged native receipt in the declared
canonical encoding and returns a raw checked state. This avoids treating escaped
canonical record keys as raw input when a premise name begins with `#`. The helper
uses type-sensitive JSON identity (booleans differ from integers) and refuses
malformed, cyclic or oversized result projections under the delegation JSON limits.

## Compatibility and evidence boundaries

Catalog version 6 adds this template. Existing five template IDs and executable
core versions stay at 5; existing source, input, option, assurance and contract
identities are preserved. Exact baseline fixtures cover all five templates in
full/compact presentation and proof terms, steps, incremental JSON and incremental
command formats.

Membership, inference validity and goal closure are distinct checks. None claims
that the menu is complete, the selected proof is uniquely desirable, a model always
succeeds, or different models choose the same output. Fake-provider checks establish
compiler and execution behavior; actual ordinal selection quality remains unmeasured.
