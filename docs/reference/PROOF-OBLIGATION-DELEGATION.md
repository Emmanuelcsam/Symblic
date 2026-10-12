# Exact intermediate obligations for fresh proof children

`symblic.delegate/proof_step_obligation/7` accepts one selected inference only
when it derives the caller's exact intermediate formula with exactly the declared
free assumptions. It preserves the original session goal. A parent can therefore
name each milestone in a proof and send each step to a fresh child context.

```python
task = {
    "template": "proof_step_obligation",
    "params": {
        "session": caller_owned_session,
        "commands": ["and_left s1", "premise a", "implies_elim s2 s1"],
        "obligation": {"formula": '"B"', "open_assumptions": []},
        "require_complete": False,
    },
    "calls": 3,
    "capsule": "compact",
}
```

The original [`proof_step/6`](PROOF-STEP-DELEGATION.md) remains available for any
valid next inference. Its contracts and those of the earlier five templates are
unchanged. Catalog version 7 adds this separate, stricter template.
Execution pins still identify the installed compiler bytes; updating the compiler
changes those pins and the wrapper's routing identity, even when an older
template's base contract ID is preserved.

## Formula and assumption authority

`params.obligation` is required. Its `formula` uses the existing controlled
propositional syntax: quoted atoms, `false`, `not`, `and`, `or`, `implies` and
parentheses. Compilation parses it into the native formula AST and derives an
explicit reading. Equivalent spellings that parse to the same AST produce the
same obligation identity; logically equivalent but structurally different ASTs
remain different obligations. No theorem search or semantic rewriting occurs.

`open_assumptions` defaults to `[]`. It denotes an exact set of free assumption
IDs, not a list of optional permissions. A matching `assume` command cannot satisfy
the empty default: its own ID is free. For an intentional new assumption, explicitly
name the session's known next line ID. Existing IDs must name `assume` lines in
the checked prefix. Unknown, other future, non-assumption and duplicate IDs refuse
before dispatch. The declared set canonicalizes into session line order, so `s2`
precedes `s10`, matching native session receipts.

`require_complete=true` additionally requires the original goal to be closed.
Compilation refuses this option if the obligation AST differs from that goal or
the requested assumption set is nonempty. Other unreachable obligations consume
only the declared attempt budget and return no accepted result; exhaustion does
not establish that a proposition is false.

The obligation, menu, premises and prefix remain caller-owned input data. Formula
text never becomes program source. The exact AST, rendered reading and canonical
assumption list are bound into the contract, inputs and returned handoff. Session
hashes establish integrity under the supplied request; they do not authenticate
the caller or establish premise truth and consistency.

## Selected-only native checks

The model sees the frontier, exact ordered commands, obligation AST and reading,
assumption IDs, completion requirement and generic rules. It returns a one-based
integer. Native indexing retrieves that unchanged command. The existing checker
validates only selected candidates, then native `ensure` statements require:

1. A valid inference under the original session.
2. Exact equality with the obligation formula AST.
3. Exact equality with the canonical free-assumption list.
4. Original goal closure when explicitly required.

A closing certificate is also independently checked. No menu entry is ranked,
filtered or evaluated as an inference before selection. The template pins
`context=none`, strict coercion, `determine=false` and `solve=false`, retaining the
existing ordinal interface and execution accounting.

Defaults remain 3 total calls (allowed 1–6), 24,000 context characters, 200,000
kernel steps, no effects and parallelism 1. Required context overflow refuses
before dispatch. Full capsules remain default and compact capsules opt-in. The
default local ladder advances after a rejected selection and allocates zero
same-rung repairs. An explicit single-model route uses the existing bounded native
retry feedback, including the fixed formula/scope failure instructions. This
template does not change routing or introduce cross-rung feedback.

## Acceptance and parent adoption

The accepted value retains `choice`, `command`, `menu_member`, the unchanged
native `inference` receipt and `handoff`, and adds `obligation_satisfied: true`.
These three fields express separate conclusions:

| Field | Established condition |
| --- | --- |
| `inference.valid` | The selected inference passes the native calculus |
| `obligation_satisfied` | Its formula and free assumptions match this milestone |
| `inference.complete` | It closes the original session goal with a checked certificate |

An intermediate milestone can be satisfied without completing the proof. Multiple
commands may satisfy one obligation and return different valid ledgers; this
contract does not establish byte-identical output across models.

Use [the parent handoff helper](../../examples/proof_step_obligation_handoff.py) to
recompile the original caller request, independently recheck only the returned
command, verify both obligation predicates, and compare the complete canonical
receipt with type-sensitive bounded JSON identity. It adopts a raw checked state
only after all checks pass. Canonical escaped record keys are handled explicitly;
malformed, cyclic, nonfinite, subclassed or oversized result projections refuse.
Bind `expected_contract_id` when sending a reviewed request to a child.

[The runnable request](../../examples/proof-step-obligation.task.json) and the helper's
three-child example exercise the interface with fake providers. Tests cover
off-target valid inferences, default closed scope, explicit assumptions,
discharge, IDs above `s9`, forged handoffs, exact old-contract parity and fresh
contexts. Model quality and token economics for this new interface remain
unmeasured. The separate small-model pilot is a proposal, not a launched or
completed evaluation.
