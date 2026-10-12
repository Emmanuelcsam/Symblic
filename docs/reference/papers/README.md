# Writing a paper that reproduces

A Symblic paper (`.symd`) is a technical document that groups of agents execute. It **reproduces** when any
new group of agents, starting from nothing, gets the identical run: the same fingerprint, so the same
answers byte for byte. These rules come from measured runs (LANGUAGE-3.md §7), not from taste.

## The loop

1. **Write** the paper: Markdown prose, a `## Definitions` list, and ```` ```symblic ```` blocks for the steps.
2. **Check** it: Write → the editor shows a *paper* pill, or run `tools/symblic check PAPER.symd`. Errors come back on the paper's own lines, and so do warnings about vague quantities (a % with no basis, "about 3", "slowly", "a couple of", "room temperature") until you define them.
3. **Reproduce** it: Write → Compare agents (tick at least 3 different agents), or run `tools/symblic paper reproduce PAPER.symd --cohort claude:haiku --cohort codex --cohort claude:sonnet`. Each agent starts from an empty record.
4. **Read the verdict:**
   - *reproduces*: every group got the identical run.
   - *results reproduce*: same outputs, but some intermediate reading differs.
   - *does not reproduce*: the report names each **paper line** that was read differently. Lines marked "inherited" only follow from those.
5. **Tighten** the lines it names (by hand, or with Tighten), then reproduce again with *different* agents.

## Rules that made the furnace paper reproduce

The draft gave three agents three different furnace runs (≈574, ≈862 and ≈402 minutes). The final version gave all three the identical run.

1. **Define every word a reader could take two ways.** "Room temperature", "slowly", "a couple of hours" and "about 3 °C per minute" each became a definition with a number. Definitions reach every ask in the paper, even when the word appears only in the text the ask reads. Each ask also reads every earlier section, so state a fact once, before the step that needs it.
2. **Never take from a reader what the kernel can compute.** A ramp's duration follows from its temperatures and rate. Asking for it anyway let one agent fill it in and another leave it at 0. Ask for the facts; let the kernel do the arithmetic.
3. **State the contract in a routine.** When a reading has parts the result does not need, read it inside a `routine` that returns only what matters. Its inner answers stay inside, and the fingerprint covers only the contract:

   ```
   routine read_steps(text: Text) -> List of Step do
     ask raw: List of Step "List the heating steps of the protocol in order." from text
     ensure len(raw) = 3 else retry because "the protocol has three steps".
     return [{kind: s.kind, ..., minutes: if s.kind = "hold" then s.minutes else 0} for s in raw].
   end.
   ```
4. **Use closed answers where you can:** `one of {…}`, `Bool`, `Int in a..b`, records of those. A closed answer is either identical or visibly different; free text almost never is.
5. **Check with the kernel, not with agreement.** `ensure` / `assert` (`len(steps) = 3`, `pick <= len(options)`, an item must occur in the passage) are what make a result correct. Agents can agree on a wrong answer.
6. **Agreement does not prove a paper is specified.** "1% dispersant" was read as 1% of the whole slurry by all three model families, identically, while ceramics usually doses dispersant on the dry powder. Every percentage, every "about" and every unit basis needs its convention written down, whether or not the readers disagree. Asking readers for the readings they see (Tighten does) exposed the dry-basis reading that unanimous answers hid. Choosing between readings stays yours: tightening makes a choice explicit, not right.
7. **When renaming a vague word, name the convention; never swap in a specific instance.** "Days in a year" should become "365 (a common year)", not "the year 2026": an instance needs more knowledge than the original and made readers disagree more (measured by the tighten loop).

## Examples here

| paper | shows |
|---|---|
| `scaling-a-recipe.symd` | typed extraction plus exact unit arithmetic; reproduced across three agents |
| `furnace-schedule-draft.symd` | what an ordinary protocol does: three agents, three runs |
| `furnace-schedule.symd` | the same protocol with its words defined |
| `furnace-schedule-contract.symd` | plus a routine contract: reproduces by construction of what is compared |
| `slurry-draft.symd`, `slurry.symd` | a vague recipe all readers misread the same way (it reproduces, and shows why agreement is not enough), then the defined version |

Once a paper reproduces, **Lock** one run (Runs → Lock). The lock replays that exact run with no model at all, so the result can travel with the paper.

## Note for this repository

The slurry and furnace papers originally named a different powder; for publication it is called
"alumina" in the papers and in the records that quote them ([../RESULTS.md](../RESULTS.md),
[../LANGUAGE-3.md](../LANGUAGE-3.md), [../NOTES-2026-10-02.md](../NOTES-2026-10-02.md)). The runs recorded there
used the original wording; their numbers are unchanged, and the papers' structure and arithmetic are the same.
