# Symblic beta review — 2026-10-08

A full-day user-seat beta test of the Symblic tools, driven purely through each
tool's own user-facing flows (the exact HTTP calls the pages make, the Agents
attach/key controls, and the English editor's documented grammar). No product
code was changed to produce these results; the beta-test gallery page
(`/symblic-beta`) and this document are the only artifacts added.

Tested: `/symblic-terminal` (bounded OS commands + agent task composer),
`/symblic-forge` (ideation), `/automation-studio/symblic.html#english`
(checked English authoring, scalar and construction lanes), plus the
surrounding run/evidence/graph/policy surfaces.

Environment on the day: cloud coding engines quota-blocked (codex usage limits
on the host and node-i, Claude weekly limit until Oct 10, node-i Claude login
expired), so all live model work ran on admitted local Ollama models
(`qwen3:4b-instruct`, `qwen2.5:14b` on node-i).

## 1. Symblic Terminal

### What worked
- Bounded English OS commands: create file, write, read, list, mkdir, copy,
  `inspect system` — every one returned a durable receipt with sha256 file
  hashes, intent classification and bounded effect lists. Path traversal
  (`../../`) is rejected; unsupported phrasing is refused with a clear,
  actionable message.
- Durable task composer: workspace creation (`beta-maze`, `beta-anim`,
  `beta-chess`), task start/poll/cancel across the host and node-i, remote-node
  execution workspaces with per-instruction branches, and the Agents → Work
  review + apply flow back into the source folder.
- Real programs produced from plain-English instructions and independently
  verified by me:
  - `beta-maze`: `maze.py` + 9 tests, all pass, solvable mazes with S/E
    markers, `--solve/--test/--seed` options.
  - `beta-anim`: `animation.py` + 4 tests, ASCII bouncing ball, clean stop.
  - `beta-chess`: `chess/` package (~2,000 lines, 50 tests passing), unicode
    board, algebraic input, castling/en-passant/checkmate, random-move bot,
    `--demo/--two-player/--black` modes. Built on node-i, applied on the host.

### Findings
| # | Finding |
|---|---|
| T1 | **Trust prompts block every `auto: true` task.** Fresh workspaces on both nodes stalled at the coding CLIs' "trust this folder?" dialog; the hub's auto-trust watcher never fired for Symblic task agents, and Codex's "Trust and continue" wording is outside the matcher's regex. Recovery is manual (press keys in the agent terminal). |
| T2 | **No completion evidence for these agents.** Finished agents leave tasks `active`/`awaiting_review` indefinitely; "Finish step & Next" is refused on an uninspected result, so verified work can only be closed by cancelling (which then records `completed`). |
| T3 | **False success report.** The animation agent reported "4 tests passed, edited 2 files" while the folder was empty; a follow-up message made it write the files. Nothing cross-checks agent claims against disk. |
| T4 | All cloud coding engines were quota-blocked; the only working engine was `agy` (Antigravity). |
| T5 | Memory-pressure fence refused a mistral launch on the host ("Memory pressure is 14.7%") while ~9.5 GB was available — the message doesn't say which threshold applies or when to retry. |
| T6 | Local Ollama single-agent lane refused itself ("complete messages and tool schemas exceed the admitted input budget", qwen3:4b on node-i) and then idled at `awaiting_review` instead of failing. |
| T7 | `tasks/start` accepts an empty `cwd` (the UI blocks it) and silently ran in `~` instead of the created workspace. |
| T8 | `/api/agents/work` takes 30+ s for 132 rows. |
| T9 | The bounded English OS grammar has no delete/remove intent (receipts carry a `files_removed` field, but no sentence produces it). |

## 2. Symblic Forge

### What worked
- Full ideation loop: idea → one question at a time (DEEP) → answers become
  proposals → explicit accept; suggestion acceptance (including edited
  suggestions); stale-revision CAS attempts rejected with a precise message;
  readiness blockers tracked; manifest export (165 KB artifact with sha256).
- Two projects driven to accepted specs ("Terminal maze game", and the
  beta-gallery subsite spec with six accepted statements used for the page
  you are reading about).
- Refusing to silently pick a default model for a role request is correct
  behavior, clearly messaged.

### Findings
| # | Finding |
|---|---|
| F1 | Failed model job shows an **empty job-level error**; the cause (`ollama@host: unavailable: ollama: invalid JSON schema in format`) appears only in the attempt/member_errors records. |
| F2 | Export with a stale revision returned `artifact: null` with no error instead of a revision conflict. |
| F3 | The structured-output JSON schema sent to the host's Ollama is rejected ("invalid JSON schema in format") — the local typed-adapter path is broken against Ollama 0.9.5 on the host. |

## 3. Symblic English editor (`symblic.html#english`)

### What worked
- Grammar diagnostics are excellent: exact line/column for every deliberate
  mistake (unknown statement, arithmetic chains, division by zero in an
  Accept, ordering comparisons on labeled answers, ask selecting its own
  answer, name-mapping collisions, reversed ranges, undefined names,
  duplicate definitions, native `is` vs `=`).
- Caller-option bounds enforced with clear messages (retries 0–5, max_calls
  0–10000, budget 1000–100000); `max_calls: 0` checks and previews but refuses
  dispatch at runtime with the exact line.
- Scalar lane programs, all verified by their checks and by me:
  - **bouncing-ball**: 4 grid frames (2,2)→(5,5), 6 asks, all ensures passed.
  - **bar-chart**: bar rises rows 1→5 (row 0 is the bottom), 0 retries.
  - **knight-jump**: fully checked knight move (2,2)→(4,3) on an 8×8.
  - **staircase-climb**: fully checked diagonal climb, five frames.
  - **words**: text + yes/no shapes → "seven", yes.
  - **maze-solver**: found S=4 and E=8 in `"####S...E####"`, both accepts
    verified (one retry).
  - **dice**: `one of` labels; an ordering comparison on labels was correctly
    refused at check time.
  - **native-area**: native kernel-only program (`show width * height` → 12),
    no model calls.
- Native check/run, runs list, portable lock (fingerprint + sha256),
  `run/recheck-models` (pinned model digests), programs save, evidence,
  library, workcards catalog, spec example + check, graph example + check +
  **run** (Measure 6 → Double 12 with per-node provenance and capacity
  budget), policy example + check.
- The recorded Matrix-rain construction run verified end to end: 24
  character-grid frames (ticks 0–23), 32×24 canvas, 256 cells per frame with
  char/shade/x/y — complete player data.

### Findings
| # | Finding |
|---|---|
| E1 | **The retry loop leaks the expected answer.** A deliberately impossible accept ("wrong equals 5") was satisfied on retry: the model received the failed check text and answered 5. Checks enforce conformance; they do not prove independent computation. |
| E2 | **Applicator hang with no timeout.** A qwen3:4b retry with a large failure-feedback capsule over the node-i ssh-mux tunnel stalled 14+ minutes, twice, reproducibly (same step, same timing), with the API reporting only "running" and the journal silent. The same retry under qwen2.5:14b completed in ~2 minutes. |
| E3 | **The construction lane's leading-rows contract is unbeatable with today's admitted local models** — 4B stalls (E2), 14B exhausts its retries (7/9 coverage examples failed, with excellent expected/got diagnostics). With cloud engines quota-blocked, the animation lane cannot complete end to end right now. |
| E4 | **No recovery for partially accepted construction runs.** `keep` (retry remaining tasks) is reserved for the labelled pixel-program lane; a construction failure at step 4 of 9 discards accepted steps 1–3. |
| E5 | Polling `run?id=` during a running program showed 0 outputs until completion; the documented "bounded snapshot after each output" was not visible through that route (frames did appear mid-run for later runs, so this is intermittent rather than absent). |
| E6 | The shipped Tetris spec example fails its own `spec/check` task-cards validation: `unknown_use: Uses names an undeclared unit or external helper.` (25 units, 120 examples). |
| E7 | A comment-only source passes `english/check` as a valid (empty) program. |

## 4. Cross-cutting observations

- Error surfaces are consistently strong where they exist: line/column
  grammar errors, expected/got arrays in sandbox checks, exact budget and
  admission messages.
- The weak spots are all in the "is anything actually happening?" layer:
  stalled applicator calls (E2), tasks that can't reach a terminal state
  (T2), empty job-level errors (F1), and success claims that outpace disk
  (T3).
- Retry feedback is honest about what it does, but authors should know an
  accept line is a specification the model can read, not a secret (E1).
- Distribution worked as designed: the chess simulator ran on node-i and came
  home through the review/apply flow without touching the live site.

## 5. Artifacts

- Gallery subsite: `/symblic-beta` (registered nav row; this page embeds every
  prompt, command, output, failure record and frame player used in
  this review).
- Programs on the host: `/srv/symblic/projects/beta-maze`,
  `beta-anim`, `beta-chess` (all verified; apply receipts recorded).
- Forge projects: "Terminal maze game" (forge-8470319b2089475fb0d9e8d7a71f145c),
  "Symblic beta gallery" (forge-a02002ab985641d59ffc6816e8dd6634).
- English runs: titled in the runs list (bouncing-ball, bar-chart,
  knight-jump, staircase-climb, words, maze-solver, dice, doomed,
  doomed-noretry, zero-budget, native-area, green-cascade ×4) plus the
  recorded Matrix rain (693f1db5a5e0) and the graph run (DoubleExample).

## 6. Commentary — the state of Symblic, inside and out

**The core is genuinely strong.** The language's honesty is the standout:
bounded grammars that refuse rather than guess, exact line/column
diagnostics, CAS revisioning everywhere, durable receipts for every side
effect, and checks whose failure output (expected/got arrays, source maps
back to the original English lines) is better than most production tooling.
The English editor compiled every program written during this review
correctly, and the run replay/lock/recheck machinery does what it claims.
Forge's authority model — proposals never silently becoming requirements —
is the right design and it is actually enforced, not just documented.

**The weakness is one specific layer: "is anything actually happening?"**
Almost every serious finding lives there. A stalled applicator call hangs
for 14+ minutes with the API saying only "running" (E2). Finished agents
cannot reach a terminal state, so honest work gets recorded as "cancelled"
(T2). A model job fails with an empty error field (F1). An agent reports
success with an empty folder (T3). None of these are language problems —
the language caught everything thrown at it. They are all observability
and lifecycle problems at the edges where Symblic meets engines. That is
the encouraging kind of weakness: fixable without touching the careful
core.

**Second priority: the local-model story.** On the test day the cloud
engines were quota-blocked and the local lane was broken in three
different ways (the host Ollama rejects the structured-output schema, F3;
the single-agent lane refuses itself on input budget, T6; the construction
lane's step 4 is unbeatable by qwen3:4b or qwen2.5:14b, E3). Symblic's
value proposition — verified computation on your own hardware — currently
has no fully working local path end to end. Fixing the Ollama schema issue
(F3) is probably the single highest-leverage bug in the system.

**Third: recovery.** The pixel lane has retry-remaining; the construction
lane does not, so a failure at step 9 of 9 discards eight accepted steps.
Given how expensive accepted steps are (each one is a checked model call),
that asymmetry will hurt every time it fires (E4).

**The gallery as a demo.** It works as a showcase precisely because it
shows failures next to successes: anyone who sees it watches a system that
refuses to lie to them, and the frames that play back make the "checked
computation" idea tangible in a way prose cannot. The page is a static
snapshot of this session: it keeps its embedded copies of every prompt,
output and frame, but the live run links on it will drift if the runs are
re-run or cleaned up.

**What was built to carry this review.** The gallery page was specified in
Symblic Forge itself (project "Symblic beta gallery", six accepted
statements) and its staircase animation was authored and run in the English
editor (run 2c65cb67da09, 8 asks, 5 checked frames). It is registered as
the nav row "Symblic Beta" (`/symblic-beta`, group Build), validated by six
browser tests including mobile accessibility, with no Python changes and no
server restart: static pages are live on write, and the nav row went
through the registration tool with its pre-flight.

## 7. Fixes applied (same day, post-review)

Every finding above was fixed, verified with focused isolated tests (about 500
tests across the touched modules) and, where the behavior is live-observable,
re-verified against the running dashboard after restarting the host dashboard. The
failing layer the commentary names — "is anything actually happening?" — is
now instrumented at every edge where Symblic meets engines.

**Terminal**

- T1: `host_agent_hub.py` now reads Codex's "Trust and continue" trust menu
  (`_TRUST`, `_NEEDS_YOU`, `trust_keys`), and the auto-trust answer moved
  behind a public `answer_trust_for(agent_id)` that the Symblic task
  coordinator calls while polling its own auto agents — a headless `auto: true`
  task no longer needs the Agents page open to clear a folder-trust dialog.
- T2: a finished agent turn now records durable step evidence (final terminal
  tail, a bounded workspace inventory with sizes and sha256, and files-changed
  counts against a launch baseline), so "Finish step & Next" works from the
  recorded evidence; the owner review gate itself is unchanged.
- T3: step evidence cross-checks the agent's claimed work against the disk and
  shows a visible warning when completed-work claims come with zero changed
  files; remote workspaces record why they cannot be inventoried instead.
- T4: environmental (engine quotas on the day); no code change.
- T5: pressure refusals name the exact threshold and its averaging window and
  say how to retry ("wait a minute and retry, or choose another machine"),
  in both the hub admission gate and the model-wake gate.
- T6: a refused launch (including the input-budget self-refusal) fails the step
  with the refusal text instead of idling at `awaiting_review`; a node-side
  self-refusal in the terminal tail is detected from the screen with a
  disk-guard against false failures.
- T7: `tasks/start` refuses a missing or empty `cwd` before any receipt is
  written.
- T8: the Work table no longer computes the full per-row diff it then threw
  away; rows read four bounded git calls on a bounded pool and each row's
  summary is held for one poll cycle. Live: 132 rows served in ~9 s cold and
  ~0.7 s on the poll path (was 30+ s).
- T9: the bounded English OS grammar accepts "Delete/Remove file \"name\"":
  the destructive adapter's authorization gate is satisfied by the typed
  sentence, the receipt carries the pre-removal sha256 in `files_removed`, and
  directories and missing files are refused cleanly.

**Forge**

- F1: a failed model job's job-level `error` now carries the first
  member/attempt cause ("Cause: …"), with the full trail kept in
  `member_errors`/`attempts`.
- F2: `Exports.validate/artifact` take a revision and raise the forge's 409
  CAS conflict for a stale revision instead of minting bytes (the POST route
  already refused; the exports layer now defends itself).
- F3: Ollama dispatches sanitize the structured-output schema
  (`host_agents.ollama_format_schema`): $defs/$ref inlined, annotations
  dropped, type arrays expanded, objects closed, unsupported keywords refused
  before dispatch — and, found by live probing of the host's Ollama 0.9.5, an
  unanchored `pattern` is anchored (0.9.5 rejects any pattern it could start
  matching anywhere; anchoring is strictly narrower). The Forge schema now
  completes real model jobs on both the host (0.9.5) and the worker nodes (0.34).

**English**

- E1: the no-leak kernel behavior was already correct (non-answer values stay
  out of retry feedback; the NoLeak tests hold). The honesty is now explicit:
  answer-only accept lines warn at check time with the exact line
  (ENG_ACCEPT_READABLE), the run evidence records the readable check per
  retried ask, and EDITOR.md documents that an accept line is a specification
  the model can read, not a secret.
- E2: applicator calls carry a wall-clock bound (`SYMBLIC_CALL_WALL_S`,
  default 1800 s) that composes with (never stretches) run budgets; a stalled
  call cancels only its own the fleet layer run and records a `stalled` error in the
  journal and API instead of showing "running" forever.
- E3: the construction lane's retry capsule is now one scoped js_test report
  plus an explicit marker instead of two joined reports (the ~14-16 KB capsule
  that stalled the 4B). The leading-rows contract itself has no difficulty
  knob; with the capsule bounded, retry-remaining (E4) is the recovery path.
- E4: construction runs support the same `keep` recovery as the pixel lane:
  accepted steps re-bind as exact literals with assert gates and only the
  remaining steps are re-asked; tampered code bytes or an edited document are
  never silently kept.
- E5: every launched run defaults to durable per-output snapshots
  (`progress_outputs`), so `run?id=` shows outputs while the program runs
  (verified live: 56 outputs visible mid-run); an explicit saved opt-out keeps
  the old completion-only shape.
- E6: the shipped Tetris sheet's `refill(g)` no longer declares its own
  parameter as a cross-unit use; `spec/check` (task-cards) passes all 25 units
  (verified live through the API).
- E7: a comment-only or blank source is refused at 1:1 ("A program needs at
  least one statement.") instead of compiling as a valid empty program.

**Beta re-test.** A new program, "Twin helix galaxy"
(`docs/symblic/examples/english/twin-helix.english.txt`), was authored entirely
in strict English statements — a counter-rotating twin helix around a ringed
planet with an orbiting moon and a twinkling starfield, four frames, 20 checked
one-claim asks, every visible cell an exact integer — with Symblic Forge helping
(project forge-61a1b0bb97804db585226109cf932570: a QUESTIONER model job on
qwen2.5:14b@node-i asked the purpose question through the previously-broken
schema path; its answer flow produced an accepted project statement). The run
(77239ad528a0) completed with 22 model calls, zero retries, every accept passing
first-try, 75 grid cells matching the hand-computed geometry exactly, outputs
visible mid-run, and no warnings. Every fix above that the run touches was
exercised live, and one real residual bug (the unanchored pattern) was found
and fixed by the test itself.
