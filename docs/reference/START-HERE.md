# Start using Symblic

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

For the current direct-English terminal, all agent/node choices, recovery,
command reference and consolidated history, see the
[full Symblic record — 2026-10-06](2026-10-06-full-symblic.md).
The focused [terminal guide](TERMINAL.md) explains everyday use.
For selected-device ChatGPT/Gemini asks, see [Browser providers](BROWSER-PROVIDERS.md):
registered placement, installed protocol, loaded daemon and account readiness are separate checks.

The language page opens **English** with one instruction field. Expand **Agents**
to configure 1–24 mixed members, exact devices, models and individual profiles.
Choose checked statements or project-agent tasks in that same editor. The header
keeps English, Native and Runs visible; the expandable tool list retains all other
views. [English statements](ENGLISH-STATEMENTS.md) explains the two execution contracts.
Start in [Forge](FORGE.md) when an idea still needs decisions: its creative lenses,
configurable proposal teams and atomic-writing coach lead to reviewed construction units.

Symblic lets a model propose small typed answers while an exact interpreter handles calculations, constraints, provenance and execution. This can make a lightweight model useful on a larger task when its parts have adequate checks. It does not guarantee that any model can solve an arbitrary complex problem, or that a weak specification captures everything you intended.

## Start with one checkable task

Open **Native** (the Write view), choose an installed model under **Who applies the asks**, and enter:

```symblic
ask root: Int in 1..9 "Find the positive integer whose square is nine."
ensure root * root = 9 else retry.
show root.
```

The editor checks source syntax as you type; **Preview** runs the deterministic prefix and shows where an answer is needed; **Run** invokes your chosen model through the admitted runner. An explicit model choice remains the choice; unavailable resources are visible failures or inconclusive checks. **Choose agents…** exposes advanced model, node, effort and multi-agent choices. **Check the machines** refreshes installed inventory without loading a model. Saved names do not by themselves establish readiness.

Incorrect source is underlined in **Write** and **English**. Click a problem, or use **F8** and **Shift+F8**, to inspect it. English also shows a source-linked circuit of inputs, workers, selected memory and check gates. [Underlines and instruction circuits](EDITOR.md) explains the controls and what the source checks establish.

The **English** example **Moving white dot** preserves the [thirty-four original English statements](../../examples/english/moving-dot.english.txt). Check them, choose a model, and run the build. Nine small implementation tasks pass through the ordinary native runner, JavaScript checks, and the exact browser interpreter before any completed implementation is exposed. A failed pixel build offers **Retry remaining tasks**: it preserves the original English and failed run, locally rechecks accepted functions, and starts a separate run for the remaining work. After the build completes, **Open display** runs the accepted functions on the device opening Symblic. Each frame computes its position, clears and draws the binary buffer, presents it, observes a browser rendering opportunity, then waits at least one sixtieth of a second before computing the next frame. Playback makes no model calls.

This English entry is a supported, checked grammar: inconsistent quantities and unsupported clauses are refused with source diagnostics. It is not arbitrary-English understanding. The browser interprets accepted functions as bounded data and supplies the display and timer primitives. The original physical-display obligations remain visible: browser device-pixel measurements do not attest the monitor panel, RGB zero does not measure optical black, and a rendering callback does not establish completed physical scanout. The requested wait is a minimum elapsed software delay after a rendering opportunity, so it is not a promise of exactly sixty frames per second.

The saved Qwen dot run (recorded on the original host; not public) completed on October 6, 2026. It retained seven rechecked functions from a failed build and generated the remaining two, with no further retries. Independent checks covered all eight hundred horizontal positions, and the live browser completed its natural wrap. [Verification record](evidence/2026-10-06-english-dot.json) separates the software results from the unverified physical requirements. Open the saved run and choose **Open display**; playback makes no model calls.

For a builder and critic, open **Workcards**, keep its square-root example, select the two models, **Prepare checked team**, then **Open in Write**. Inspect the generated source before running. Each proposal must satisfy your executable predicates and the critic; agreement cannot override a failed predicate. [Workcards and typed program holes](WORKCARDS.md) explain the terminal interface and multiple reviewers.

## Examples of useful projects

| Project | Small model's part | What Symblic can check or execute |
|---|---|---|
| A game or terminal animation | Propose a small rule, update function or display component | Check examples and invariants, assemble verified parts, run bounded loops; [CMatrix example](../../examples/cmatrix.sym) |
| Invoice or table processing | Extract one explicitly typed field at a time with its source evidence | Check types, ranges, arithmetic totals and supplied source spans; a matching number alone does not establish the right item |
| Scheduling | Propose assignments for a bounded set of people, rooms and times | Check no overlaps, required coverage and declared availability; exact finite solvers can handle supported constraint subsets |
| Scientific calculations | Propose a finite field or parameter candidate | Compute exact residuals, declared units and supported energy/certificate checks; [worked field construction](VORTICITY-CONSTRUCTION.md) |
| Code generation | Fill visible typed holes or propose one tested function | Parse each choice, run finite tests, reject counterexamples and preserve failed attempts; finite tests are not a universal proof |
| A recurring workflow | Supply a checked program for each bounded step | Schedule with the fleet runner, launch admitted native runs, wait, join, update durable operator state and retain uncertain outcomes; [Supervisor](SUPERVISOR.md) |
| Specializing a small model | Reuse eligible accepted examples from chosen runs | Export provenance, freeze split groups, train a LoRA adapter, compare baseline and adapter on the same held-out prompts; [distillation](DISTILLATION.md) |

Break a large problem into a sequence of small contracts. Give each part an explicit input, answer type, acceptance predicates and call limit. Feed only accepted results to the next stage, and keep an independent end-to-end check for the assembled result. Missing premises or incomplete checks still require your judgment.

## Loops, decisions and waits

Native `if` / `elif` / `else`, Boolean implication and biconditional expressions, bounded `for` loops, functions and supported finite logic adapters are available. A `for` iteration has its own scope; it is not an unrestricted mutable `while` loop. The language does not implement every formal logic.

For persistent waits and recurring execution, use a **Supervisor** workflow. Its `delay` and bounded `wait` steps survive browser disconnects; the fleet runner's minute reconciliation pulse makes them suitable for automation, not subsecond animation timing. Put conditions over model or tool results inside the native program so the normal flow and effect checks still apply.

## What the current evidence establishes

A real two-call local Llama3.2 1B builder/critic task returned `3`, and native checks verified its square and sign. A larger Qwen3 4B finite-field example completed with 20 calls and no repairs, with a zero residual under its declared equations. These are demonstrations on named tasks, not a model ranking or a guarantee of arbitrary reasoning.

The Qwen2.5 0.5B training pilot performed four actual LoRA updates. Its frozen three-item comparison changed from 0/3 to 1/3 reference agreement, and a separate physics question still failed. That small result establishes a functioning training/inference path, not a general accuracy gain. Keep failed outputs, refusals and resource limits in the record.

The **?** help button explains individual controls. [Portable execution](PORTABLE-FINITE.md) gives the measured Linux x86/ARM subset and its exclusions.
