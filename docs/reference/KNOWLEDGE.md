# Knowledge on a finite set of states

`symblic/adapters/knowledge.py` computes exactly on the partition model of knowledge (Aumann 1976) and on the
announcement process of Geanakoplos and Polemarchakis (1982). Every input is a finite list that the program
writes down; every number is an exact rational. It makes no model calls, does no I/O and runs nothing on import.

## The model

The states are the integers `1..n`, with `n` at most 64. An agent's information is a **partition** of the
states: a list of cells, each a list or set of states, that covers every state exactly once. At state `w` the
agent cannot tell apart the states of the cell that contains `w`. An **event** is a list or set of states. At
state `w` an agent **knows** an event when its cell containing `w` lies inside the event.

The **meet** of several partitions is the finest partition that each of them refines: two states share a cell
of the meet when a chain of states links them, each consecutive pair sharing a cell in some agent's partition.
An event is **common knowledge** at `w` when the cell of the meet containing `w` lies inside the event. Aumann
(1976) states common knowledge in this form; it agrees with the hierarchy "everyone knows the event, everyone
knows that everyone knows it, and so on". The tests check that agreement by brute force on random models.

## The builtins

| Builtin | Result |
| --- | --- |
| `knows_event(partition, event, state)` | Bool: the agent's cell containing `state` lies inside `event` |
| `common_partition(partitions)` | the meet of 1 to 8 partitions: cells sorted, cells ordered by their smallest state |
| `common_knowledge(partitions, event, state)` | Bool: the meet cell containing `state` lies inside `event` |
| `posterior_given(prior, cell, event)` | the exact conditional probability of `event` given `cell` |
| `agreement_process(priors, partitions, event, state)` | the record described below |

A **prior** is a list of `n` non-negative exact numbers with a positive sum; it is normalised, so `[1, 1, 2]`
and `[1/4, 1/4, 1/2]` are the same prior. For `posterior_given`, `n` is the length of the prior; a cell of zero
prior weight is refused, because the conditional probability is undefined there.

`FUNCTIONS` maps the five names to wrappers with the kernel calling convention `fn(kernel, node, *args)`; they
charge the kernel's step budget. The same computations are plain Python functions with the same names, taking
optional `budget=` (a Symblic `Budget`) and `node=` keywords. `VERSION = 1` identifies these semantics.

## The announcement process

`priors` is one prior, used by every agent, or a list of `m` priors, one per agent, where `m` is the number of
partitions. Agents `1..m` speak in turn, agent 1 first. A public set `W` starts as all `n` states; an agent's
current cells are its cells intersected with `W`.

1. The speaker announces its posterior of the event given its current cell at the true state.
2. The listeners learn that the true state lies in the union of the speaker's current cells that give the
   announced number. Every state of `W` whose speaker cell gives a different number leaves `W`, and every
   agent's information is intersected with the new `W`. The true state never leaves; the speaker learns
   nothing from its own announcement.
3. The process stops when `m` consecutive announcements remove no state. It has then **converged**. If the
   first `m` announcements remove nothing, it stops after `m`; a single agent stops at its first announcement
   that removes nothing.

The process always converges within `n·m` announcements, at most 512. At any state of `W` the same
announcements would have been made, so an agent's information there is its cell intersected with `W`. An
announcement that removes something removes at least one state, so there are at most `n - 1` such
announcements. Before each of them there are at most `m - 1` announcements that remove nothing (`m` in a row
stop the process), and the process ends with exactly `m`. That makes at most `(n - 1)·m + m = n·m`. The module
loops at most `n·m` times. If that bound were ever reached without convergence, the call raises a
`SymblicError` of kind `runtime` (an internal defect) and returns nothing: no posterior and no `agreed` is ever
reported for a process that has not converged.

Why the posteriors agree with a common prior: after convergence each agent's last announcement removed nothing,
so every current cell of agent `i` inside `W` has positive weight (or the call would have refused) and gives the
same posterior `q_i`. `W` is the disjoint union of these cells, so `P_i(A and W) = q_i · P_i(W)`, that is
`q_i = P_i(A | W)`. With one common prior every `q_i` equals `P(A | W)`. With different priors `P_i(A | W)` can
differ: the agents then hold their posteriors as common knowledge and still disagree.

If a current cell of the speaker inside `W` has zero weight under the speaker's prior, the speaker's posterior
there is undefined. The call refuses (kind `check`) and names the agent, the announcement and the cell. Another
convention would drop such states from `W`; this module does not choose one. A prior with no zero entries never
meets this case.

The result record (the module recomputes `posteriors` from the final `W` and checks them against the last
announcements):

| Field | Meaning |
| --- | --- |
| `posteriors` | each agent's posterior given its final information, agent 1 first; it equals its last announcement |
| `agreed` | Bool: all `posteriors` are equal |
| `announcements` | the full number of announcements made, at most `n·m` |
| `history` | the first 64 announced numbers in order; announcement `k` is made by agent `((k - 1) mod m) + 1` |
| `history_truncated` | Bool: more than 64 announcements were made |
| `common_prior` | Bool: every agent's normalised prior is the same distribution (always true when one prior is given) |
| `converged` | Bool: the stopping rule ended the process; true in every returned record |

## Domain and limits

| Limit | Value | Meaning |
| --- | ---: | --- |
| `MAX_STATES` | 64 | states, and so cells and entries of any list of states |
| `MAX_AGENTS` | 8 | partitions in one call |
| `MAX_BITS` | 4096 | bits of a prior entry's numerator or denominator, of its common denominator and of each weight |
| `MAX_HISTORY` | 64 | announced numbers kept in `history` |
| `MAX_ANNOUNCEMENTS` | 512 | the largest `n·m`; no admissible process is longer |

A prior is used as integer weights: each entry multiplied by the prior's common denominator. The bit limit
applies to those weights too, so no intermediate number grows past about 8200 bits.

Refusals raise `KnowledgeError`, a `SymblicError`:

- kind `type`: a value of the wrong kind: not a list or set, a state that is not a whole number, a float, a
  bool, text, a malformed `Fraction`, or priors that mix numbers and lists;
- kind `check`: values that do not form the model: a state in two cells or listed twice, a state in no cell, an
  empty cell, a state outside `1..n`, no partitions, partitions of different state sets, an empty prior, a
  negative entry, a prior that sums to zero, a cell of zero weight, priors that do not match the agents or the
  states;
- kind `budget`: a hard limit from the table above.

Every call validates sizes first and charges the kernel's step budget before each part of the work, in
proportion to it: list entries, the meet, and before every announcement the size of `W`. The largest admissible
`agreement_process` call charges at most about 71,000 steps (the kernel's default is 200,000 per run); an exhausted
budget raises the kernel's own error. Results are the kernel's values: tuples for lists, Booleans, and numbers
normalised as the kernel does (`1`, not `1/1`). Lists of states may be given in any order. Sets are read in
increasing order, so results and refusal messages are the same on every machine.

One measurement on 2026-10-03 (CPython 3.12.3, a 6-core desktop CPU, machine under load) took 4.5 ms for the
137-announcement process in the tests (11,044 steps) and 2.9 ms for 8 agents on 64 states with 2000-bit prior
weights. These are single observations, not guarantees.

## What this does not establish

- It computes on the finite model that the program writes down. It says nothing about what a person or a
  language model actually knows.
- A transcript is not a partition. Which states an agent can tell apart is the author's claim about the
  situation; this module checks only that the declared partitions are partitions.
- Common knowledge here is a property of the declared partitions. Two agents giving the same answer, or a fact
  appearing in a shared document, does not make it common knowledge in this sense.
- The agreement theorem applies only to a converged process and only with a common prior, and it needs the
  common prior that is passed in. The module never returns an interrupted process; a process cut off early
  would prove nothing. With different priors the process can end with common knowledge of unequal posteriors.
- Agreeing on a posterior is not being right. In the example below both agents end at 1/3 for the event
  `{3, 4}`, yet at the true state 1 the event is false.
- Exact arithmetic makes the computation exact for the numbers supplied. It does not make a prior, a partition
  or an event a good description of anything.

## Example

The nine-state example of Geanakoplos and Polemarchakis: uniform prior, event `{3, 4}`, true state 1. Agent 1
announces 1/3 (states 7 to 9 leave `W`), agent 2 announces 1/2 (5 and 6 leave), agent 1 announces 1/3 (4 leaves).
Agent 2 then announces 1/3 and agent 1 announces 1/3 again; neither removes a state, so the process stops after
five announcements. Agent 2's posterior went from 1/2 to 1/3. The kernel computes everything; no model is asked.

```symblic
program Two agents announce posteriors.
note The nine-state example of Geanakoplos and Polemarchakis (1982). The kernel computes; no model is asked.
let p1 = [[1, 2, 3], [4, 5, 6], [7, 8, 9]].
let p2 = [[1, 2, 3, 4], [5, 6, 7, 8], [9]].
let a = [3, 4].
let uniform = [1, 1, 1, 1, 1, 1, 1, 1, 1].
let low = [1, 2, 3, 4, 5, 6].
assert knows_event(p1, low, 1) and knows_event(p2, low, 1).
assert not common_knowledge([p1, p2], low, 1).
show common_partition([p1, p2]) as "meet".
show posterior_given(uniform, [1, 2, 3, 4], a) as "agent 2 before talking".
let talk = agreement_process(uniform, [p1, p2], a, 1).
assert talk.converged and talk.agreed and talk.common_prior.
show talk.history as "announcements".
show talk.posteriors as "posteriors".
```

Both agents know `{1, ..., 6}` at state 1, but it is not common knowledge: the meet is a single cell.
Expected output (the label and value of each `show`):

```text
meet: [[1, 2, 3, 4, 5, 6, 7, 8, 9]]
agent 2 before talking: 0.5
announcements: [1/3 (≈0.333333333333), 0.5, 1/3 (≈0.333333333333), 1/3 (≈0.333333333333), 1/3 (≈0.333333333333)]
posteriors: [1/3 (≈0.333333333333), 1/3 (≈0.333333333333)]
```

`tests/adapters/test_symblic_knowledge.py` runs this program with the five functions attached to the kernel and compares
these lines. Its other tests cover hand-worked models with the steps in comments: known by both but not common
knowledge, a common-knowledge case, meets by hand, exact posteriors, the nine-state process at several true
states, different priors that end apart, three agents, one agent, a zero-weight refusal and two processes of
137 and 130 announcements. They also cover every refusal kind, the step budget, canonical form and seeded
brute-force comparisons. Those compare the meet with all set partitions, common knowledge with the knowledge
hierarchy, posteriors with direct fractions, and the process with an independent refinement of whole partitions.

## Sources

- R. J. Aumann, "Agreeing to disagree", *The Annals of Statistics* 4(6), 1976, pp. 1236–1239.
- J. D. Geanakoplos and H. M. Polemarchakis, "We can't disagree forever", *Journal of Economic Theory* 28,
  1982, pp. 192–200.
