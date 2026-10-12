# Autonomous recursive decomposition (autogen `until_done`)

This is the contract for autogen's `until_done` mode (v2). One agent works on each statement; failed work is regenerated until code accepts it, work one agent cannot finish is split into smaller statements or handed to a successor, and a statement stops only when nothing novel is left to try. The page describes `symblic/autogen/policy.py` (pure policy) and `symblic/autogen/coordinator.py` (`AutogenManager`) as they stood at 00:52 (host local time) on 2026-10-11; the policy was last written at 00:37 and the coordinator at 00:50. Bounded mode, verdicts, promotion, the API and the record layout are in [AUTOGEN.md](AUTOGEN.md); this page covers what `until_done` changes.

**Status, 2026-10-11 00:52.**

- **Implemented** in the working tree. Both modules are untracked in git and changed several times during the evening.
- **Focused tests** now cover parts of it:
  - `tests/autogen/test_policy.py`: the pure policy, including the stall counters, named-file progress, the probe exit rule and a spent budget at a stalled handoff;
  - `tests/integration/test_symblic_task_cli_autogen.py`: the CLI flags, unlimited caps and stuck hints;
  - `tests/integration/test_symblicos_autogen_hub_lane_v2.py`: 32 coordinator tests, covering until_done regeneration, stall splits, self-split, reopened parents, the designer, handoff stalls, budgets, stuck and resume, the dedup index, the sandbox and gated remote turns.

  These docs ran four of those tests, and they passed: the three for the 00:44 fixes and the end-to-end check of the scoped designed test.
- **Throwaway checks**, not in the repository, cover the behaviour described here: 20 assertions on the pure policy, 12 coordinator journeys over the suite's `Harness` (temporary stores, fake hub, fake check runner, injected clock), and real runs of `sandbox_prefix` and `_designed_check` on temporary folders. The item-key, item-object and heartbeat changes made after those runs (00:27–00:37) were checked with direct calls only, and the 00:44 fixes with the three repository tests above and a re-run of the re-split journey. These are software checks, not model results.
- **Live status.** The dashboard was restarted at 00:51:05, after the last edits to both modules (00:37 and 00:50). The modules load on the first autogen request after that restart, so the routes serve this code unless the files change again first.
- **Runs.** One `until_done` run has been recorded, and it completed at 00:32.

## 1. What the operator asked for

The operator set these requirements:

- One agent works on each line by default.
- Each agent's statement is regenerated until its code checks pass, unless the agent hands off its context through a checkpoint or splits off the part it cannot do.
- In `until_done` mode, no time or count cap ends the work while something novel remains. Novel means a strategy fingerprint the node has not tried, or measurable progress.
- The master coordinator spawns as many agents as that takes.

The code implements them as follows:

- `candidates` defaults to 1 (`DEFAULTS`), so one agent works on a statement at a time. `candidates` 2–4 is optional parallel sampling.
- `until_done: true` makes `decide()` use the novelty and progress rules in place of the count caps. Wherever bounded mode would end a node `failed`, `until_done` ends it `stuck` or reopens it.
- With `until_done`, `normalize` sets `agents_max` and `wall_seconds` to 0 (unlimited) unless they are given. It accepts 0 for either field only in this mode.
- **Novelty** is a strategy whose `fingerprint` the node has not tried (`_novel_strategy`).
- **Progress** is measured by code only.
  - `progress_metrics(verdict, checkpoint, named)` counts the files named by passed checks, and the changed paths the statement names (by path or by file name).
  - `is_progress` is true for a new named file or for more passing checks.
  - The checkpoint's `done` list is recorded, but it never counts as progress on its own.
- **The stall counters are derived from the attempts:** `stale_count`, `handoff_stale` and `recent_progress`. `AutogenManager.advance` copies them into the node (`stale`, `handoff_stale`, `progress_recent`) before every decision.
- **Launches.** `AutogenManager.advance` launches every attempt through `_launch_wave`, whose budget test refuses a launch only when `agents_max` is non-zero and has been reached. When the budget refuses a whole wave, `_launched` ends the node `stuck`, so no pass repeats a refused decision.

These floors still hold in `until_done` mode:

- `attempt_seconds` (120–14400 s, default 3600; 0 is not accepted) still cancels a single hung attempt as `TIMEOUT`.
- `HARD_DEPTH` (12) replaces `depth` as the deepest level a split may create.
- `novelty_limit` (1–8, default 2) is the `stale_count` at which a node is split.
- An explicit `agents_max` or `wall_seconds` works as a safety cap. When it is spent, the node ends `stuck`, never `failed`, and a resume must raise the cap (section 3.2).
- `lint` and `parse_split` still decide what a statement or a split line may look like. For example, a line shorter than 20 characters is refused.

## 2. Research mechanisms and where they live

The operator named eight papers. This table maps each one to the mechanism autogen implements and to the functions that implement it. It makes no claim about the papers beyond this mapping, and no mechanism has been measured against a paper's results.

| Operator's name | Mechanism in autogen | Functions | Limits of this implementation |
|---|---|---|---|
| Parsel; ANPL | **Hierarchical split with explicit per-line interfaces.** A planner writes `AUTOGEN-SPLIT.txt` with 2 to `children` statements. Each line names its own file, says "in the current working folder" and repeats every count, name and interface the parent fixes. A worker may answer "too big" itself with the same file (self-split); its instruction offers this only where a split can be accepted. | `split_prompt`, `split_remaining_prompt`, `parse_split`, `delocalize`. Worker side: `worker_suffix(..., can_split)` offers the split below the depth limit and outside perpetual lanes; `_verdict` probes for the file with `_planner_verdict(quiet=True)`; `_observe` makes the attempt the node's planner (`attempt_self_split`); `_accept` supersedes its rivals; `_split` creates the children. | Interfaces are prose inside each line, and nothing compares one child's interface with its siblings'. A planner split or a self-split promotes nothing: the children start from the project folder. |
| CodePlan | **Dependency-aware ordering of nodes.** The children of a split node run in the planner's order, before any later statement. A split parent is judged only after all its children are accepted. Under `until_done`, a parent that fails its own checks is reopened and worked on as a whole. | `_current` (a depth-first walk of `order`), `_settle`, `_parent_verdict` (the parent's own `plan_checks`, run in the project folder) | The order is the line order plus the split order. There is no dependency graph and no change-impact analysis. One node is active at a time. |
| CodeT; AgentCoder | **Generated tests select candidates.** With `designer` on, an independent attempt writes `AUTOGEN-TESTS.sh` before any candidate of the node exists. Code admits the script only if it fails, with a genuine exit code, on an empty folder. It then runs as a `designed` check on a copy of each later candidate's files. A script that alone blocks two candidates in a row is retired (section 2.1). | `designer_prompt`, `design_valid`, `design_probe_ok`, `_designer_verdict`, `_designed_check`, `_designed_outcome`, `sandbox_prefix` | There is one script per node, written once. Candidates are not ranked by test agreement: with `candidates` > 1, the first accepted attempt in record order wins. The designer is best effort, so a failed designer does not block candidates. |
| AFlow | **Strategy rotation chosen by evidence.** The last failure class orders the strategies, and a repeated search state is refused. | `next_strategy`, `_novel_strategy`, `fingerprint` | The rotation is a fixed rule over failure classes. It is not a learned or searched workflow, and no success statistics feed it. |
| Agent Contracts | **Checks per statement and per subtree, budgets per run.** Every statement has its own code checks, a split parent is re-checked after its children, and `final` and `hidden` gate the run once. Bounded mode caps attempts, depth and generations per node, and agents and time per run. `until_done` replaces the per-node count caps with the novelty and progress rules. | `plan_checks`, `_verdict`, `_parent_verdict`, `_finish`, `decide`, `normalize`, `_extend_budget` | Budgets are run-wide (`budget.agents_max`, `budget.deadline`), and a resume can raise a spent cap. There is no per-subtree budget. |
| Recursive Models for Long-Horizon Reasoning | **Fresh contexts with external checkpoints.** A worker near its context limit writes `HANDOFF.md` and `AUTOGEN-CHECKPOINT.json`. A successor with a fresh context continues in the same checkout. When two handoffs in a row add nothing, the remaining work is split, and the last handoff's checkout is promoted first so the children start from its files. | `worker_suffix`, `checkpoint_valid`, `handoff_prompt`, `handoff_stale`, `decide` (split remaining), `split_remaining_prompt`, `_promote_partial`, `parse_split(..., present)` | The checkpoint is the worker's own summary. Code checks its shape and that the files it lists exist, and never counts its `done` list as progress. Remote handoff is refused. |

What is not implemented:

- **No learned policy.** Every decision is the fixed rule in `decide()`.
- **No model ladder.** `stronger_model` is still listed in `STRATEGIES`, but `normalize` refuses it and nothing fills `node['stronger_models']`.
- **No remote handoff.** A successor must start in its predecessor's checkout, and the task engine's submit options (`OPTIONS` in `integration/host/symblicos_tasks.py`) have no `workspaceFrom`. The engine sets that option only between the steps of a single task. `_intent` records such a successor as a `REFUSAL` and does not launch it.
- **No parallel nodes.** One statement node is active at a time. The only parallelism is `candidates` (at most 4) inside a node.
- **No per-subtree budget.**

### 2.1 The test designer and its sandbox

When `designer` is on and the statement names a file (`needs_design`), `decide` returns `design` before the first wave. The designer attempt receives `designer_prompt`, with no worker suffix. It must write `AUTOGEN-TESTS.sh`, a bash script that exits 0 only when the statement has been carried out. `_designer_verdict` admits the script only when all of these hold:

1. **The file is this attempt's own.** An `AUTOGEN-TESTS.sh` older than the attempt's start (minus 5 s) was inherited from the project or an earlier attempt and is refused (`_predates`; local attempts only).
2. **`design_valid` accepts it without running it.** The script must start with a bash shebang, be at most 8000 characters long (`DESIGN_MAX_CHARS`), contain no command from the `UNSAFE_COMMAND` list, and contain no `cd /` or `../`. This is an advisory refusal list, not a confinement: a script can run anything the list does not name. The sandbox below is what confines it.
3. **`bash -n` parses it.**
4. **It fails for real on an empty folder.** Run in an empty temporary folder inside the Landlock launcher, it must exit with a code from 1 to 123 and print no `symblic.sandbox.landlock:` message (`design_probe_ok`). The other exits mean:
   - 0: the script tests nothing;
   - 124: the runner's timeout;
   - 125: the launcher refused to run it;
   - 126 or 127: the interpreter is missing or not runnable.

The admitted text is stored on the node as `designed`. For every later candidate, `_designed_check` does the following:

- It copies the candidate's files (or its remote staging checkout) to a throwaway folder (`_copy_workspace`), without `.git`. A folder with more than 20000 entries (`COPY_LIMIT`), or a failed copy, gives a failed `designed` check ("the designed test was not run").
- It writes the script into the copy as `AUTOGEN-TESTS.sh`, beside the files it tests.
- It runs the script with the copy as its working folder, inside the Landlock launcher. The run also goes inside a transient user scope (`_scope`: `--slice a systemd slice for work`, `TasksMax=64`, `MemoryMax=1G`) when all three of these hold: `systemd-run` is on `PATH`, `XDG_RUNTIME_DIR` is set, and a one-time probe succeeds (`systemd-run --user --scope --quiet --slice a systemd slice for work -- /bin/true`, cached per process in `_SCOPE`). `_stop_scope` stops that unit afterwards so leftover processes die. When the probe fails, the check runs without a scope. The check runner scrubs the environment, so `_scope` passes `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` to `systemd-run` explicitly (`env` before it). The sandbox prefix after it still gives the script only its own minimal environment.
- It records the result as a `designed` check with `sandbox: 'landlock+scope'` (`'landlock'` when no scope was used).

The candidate's own checkout is never touched, so nothing the script writes can be promoted. The designer never sees a candidate: it runs in its own checkout before the node's first candidate is launched.

**Retirement.** `_designed_outcome` counts the candidates in a row whose only failing check is `designed` (`designed_only`). At two, the script is retired: `designed` is cleared, the text is kept as `designed_retired`, and the event `design_retired` is recorded. A candidate that fails any other check resets the count.

**Sandbox.** Both runs go through `sandbox_prefix`:

- `env -i` with only `PATH` (the system directories plus the node runtime's bin folder), `HOME` and `TMPDIR` (both a throwaway folder) and `LANG`;
- then the repository's Landlock launcher `symblic/sandbox/landlock.py`, with `--require --no-unix --net-connect 1`.

Inside the sandbox:

- The working folder and the throwaway home are the only writable places, apart from the launcher's standard device nodes and `/dev/shm`. The working folder is the empty folder for the probe and the copy for a candidate.
- The launcher's system directories and the node runtime are read-only.
- The rest of `$HOME` is absent, including the dashboard repository, `.env` and `~/.ssh`.
- `--net-connect 1` allows TCP connect only to port 1 and denies TCP bind. A seccomp filter closes the ways around those rules.
- `--no-unix` makes Unix socket creation fail, abstract sockets included. `socketpair` still works.
- Landlock scoping (ABI 6 or later; the host reports ABI 8) stops signals to processes outside the sandbox.
- **UDP is not blocked.** Landlock's network rules cover TCP only, and the filter admits UDP sockets.

The probe's check row records `sandbox: 'landlock'`; a candidate's row records what was used. With `--require`, the launcher exits 125 (`SANDBOX_REFUSED`) when Landlock, its network rules or one of its seccomp filters is unavailable. The coordinator records that exit as a failed `design` or `designed` check ("the sandbox refused …"), never as an unsandboxed run. bwrap is not used, because the host refuses unprivileged user namespaces: `kernel.apparmor_restrict_unprivileged_userns` read 1 on 2026-10-10, and a bwrap probe failed by hand the same evening.

Real runs on temporary folders, 2026-10-10 and 2026-10-11:

| Action | Result |
|---|---|
| `sandbox_prefix`: write to the working folder or the throwaway home | Allowed |
| `sandbox_prefix`: write to `/tmp` | Denied |
| `sandbox_prefix`: read `~/.ssh` or the dashboard repository | Denied |
| `sandbox_prefix`: TCP connect to 127.0.0.1:8080 | Denied |
| `sandbox_prefix`: UDP send to 127.0.0.1:9 | Allowed |
| `sandbox_prefix`: run `node` | Allowed |
| `_designed_check` with the scope patched out | The script rewrote `alpha.py` in the copy, saw no `.git`, and found itself beside the files. The candidate's `alpha.py` was unchanged, the check passed, and the row recorded `landlock`. |
| `_designed_check` with the scope (coordinator of 00:50) | The check passed and recorded `landlock+scope`. The script's write landed in the copy, and the candidate was untouched. The repository test `Sandbox.test_a_designed_check_really_runs_in_a_copy_under_the_scope_and_landlock` also passed. |

Inside the sandbox, the environment held only `HOME`, `LANG`, `PATH` and `TMPDIR`, plus the shell's own variables. The dashboard service's environment has `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` (checked by name on 2026-10-11), so its probe succeeds and the scope gets both variables.

## 3. The `until_done` decision procedure

Before every decision, `advance` refreshes the node's `stale`, `handoff_stale` and `progress_recent` from its attempts. Then `decide(node, policy, budget, now)`, which is pure, runs once per coordinator pass, for the current node only. With `until_done` on, it applies these rules in order:

1. **Closed node.** A node that is `accepted`, `failed`, `split` or `stuck` gets `stop`.
2. **Accepted.** If an attempt passed every code check, the decision is `accept`. Non-planner attempts come first, so a genuine pass beats a self-split; otherwise the first accepted attempt in record order wins. A perpetual node never accepts an attempt.
3. **Running.** If attempts are queued or running, the decision is `wait`.
   - If the run deadline has passed, every running attempt is cancelled as `TIMEOUT`.
   - Otherwise, an attempt running longer than `attempt_seconds` is cancelled as `TIMEOUT`. This is the one clock that still applies when `wall_seconds` is 0.
   - Attempts in `unknown` or `promoting` also lead to `wait`.
4. **Perpetual lanes** follow their own rules (section 3.1).
5. **First wave.** This rule applies while the node has no candidate, regeneration, handoff or integration attempt; planners and designers do not count.
   - If the budget is exhausted, the decision is `stuck`.
   - Otherwise, if `designer` is on, the node `needs_design` and no designer has run, the decision is `design`.
   - Otherwise, the decision is `launch` with `candidates` attempts: 1 by default. With a non-zero `agents_max`, it launches at most what is left of the budget, and never fewer than 1.
6. **Pending handoff.** This rule applies when an attempt ended in `handoff` and no attempt names it in `from`.
   - If the budget is exhausted, the decision is `stuck`. This test comes first.
   - If the last two handoffs made no progress (`handoff_stale` ≥ 2), the decision is `decompose` with `remaining`: a planner receives `split_remaining_prompt` over that attempt's checkpoint. This needs the node to be shallower than `HARD_DEPTH`, no refused split, and no planner so far. Otherwise the decision is `stuck` ("handoff generations exhausted").
   - Otherwise, the decision is `handoff` to generation `handoffs + 1`.
7. **Budget.** If `agents_max` is non-zero and has been reached, or a deadline is set and has passed, the decision is `stuck`.
8. **Promotion conflict.** If the last failure is `CONFLICT`, two conflicts in a row end the node `stuck` (bounded mode: `fail`). One conflict gets a single `conflict_retry` on the same engine and machine, from the new base. `_promote` records `CONFLICT` both when the hub reports `conflicts` and when the apply raises an error that mentions a clash or a conflict, as `agent_hub.apply_work` does.
9. **Stall.** The decision is `decompose` when all of these hold:
   - `stale_count` ≥ `novelty_limit`;
   - at least one failure is semantic (any class outside `NON_SEMANTIC`);
   - the node is shallower than `HARD_DEPTH`;
   - the node has had no planner.

   `stale_count` counts the finished work attempts since the last one that made progress, when they ended with a semantic failure, a `TIMEOUT`, or a handoff without progress. Placement failures (`INFRASTRUCTURE`, `REFUSAL`, `CANCELLED`, `CONFLICT`, `FETCH_FAILURE`) do not count. A statement that keeps failing without progress is therefore split before the strategy rotation is used up on it.
10. **Novel strategy.** If `_novel_strategy` finds a strategy whose fingerprint has not been tried, the decision is `regenerate` with that strategy.
    - No count limits this rule; the `candidates + regenerate` limit applies only in bounded mode.
    - `next_strategy`'s per-strategy quota (counted from `rotation_start`) and its limit of two `feedback` attempts still apply. `fresh` is the fallback.
    - `feedback` and `fresh` may repeat a fingerprint that was already tried only while `recent_progress` is true, that is, while the last finished work attempt made progress. A refused launch, a timeout or any attempt without progress ends this exemption.
11. **First split.** If the node is shallower than `HARD_DEPTH`, at least one failure is semantic, the node has had no planner and no split was refused, the decision is `decompose`.
12. **Re-plan.** If a planner has failed (its split was refused or never written), the node is shallower than `HARD_DEPTH` and at least one failure is semantic, the decision is `decompose` with `replan`. The new planner runs on the first (engine, machine) pair that no planner of this node has used, drawn from the node's own placement and the policy's `engines` × `nodes`. Each pair is tried once.
13. **Nothing left.** The decision is `stuck`. The reason names the failures and says "every novel action at this subdivision was tried". The coordinator records `node_stuck`, the run's status becomes `stuck`, and the coordinator stops. Resume reopens the run (section 3.2).

Outside `decide`, a node ends `stuck` in two more cases:

- `_launched`: the budget refused a whole wave.
- `_promote_partial`: the handoff chain's work could not be applied before a split of the remaining work, or that handoff attempt has no agent identity.

A split parent whose assembled result fails is reopened instead (section 6).

### 3.1 Perpetual lanes

- **No generation cap.** `generations` caps a lane only in bounded mode.
- **Saturation.** With `saturation` set to N > 0, the lane is accepted (winner `generations`) once N promoted generations in a row have added no new index key (`stale_generations` ≥ N). A generation that lists no items counts too. With `saturation` 0 the lane never stops this way.
- **Failures.**
  - Failed generations since the last `generation_done` never fail the lane.
  - The next generation takes the placement overrides of the first strategy whose fingerprint is untried (`_novel_strategy`). When none is left, the lane becomes `stuck`.
  - Each promoted generation archives and clears the lane's fingerprints, so the tried set covers only the failures since the last promoted generation.
  - Generations are not work attempts, so `recent_progress` is never true for a lane, and no fingerprint repeats in between.
- **Budget and interval.** An exhausted budget makes the lane `stuck`. Otherwise the lane waits `interval_seconds` after the last attempt finished, then the decision is `perpetual_next`.
- **Dedup index.** `_promote_generation` calls `_index_items` under the run lock, after the generation's promotion succeeded, so only promoted items enter the index. `_index_items`:
  - reads `AUTOGEN-INDEX.jsonl` in the project folder leniently: undecodable bytes are replaced and bad lines skipped. A path that is a symlink or not a regular file is refused with the event `index_unreadable`, and that generation adds nothing;
  - takes the checkpoint's `items`, which `checkpoint_valid` has already reduced to text. Strings are kept as given (≤ 400 characters). An object is reduced by `item_text` to its identifying fields (`doi`, `url`, `link`, `href`, `title`, `name`, `text`, `source`, `id`, in that order, joined by ` | `). An item that is neither, or an object with none of those fields, makes the checkpoint invalid;
  - turns every entry into a key with `items_key`:
    - `doi:<doi>` when the entry contains a DOI;
    - `url:<url>` when the entry starts with a URL: the URL's first word, without its scheme, `www.`, fragment or trailing slash, lowercased, so a title after the URL does not change the key;
    - `text:<text>` otherwise, lowercased and with whitespace collapsed.
    - Every key is cut to 200 characters after its prefix;
  - counts rows this same attempt wrote earlier (a crash between the append and the record write) as its own new items, so a replay neither drops nor doubles them;
  - appends the new rows `{key, item (≤400 characters), run, attempt, generation, at}` in one write, through `O_NOFOLLOW` and an exclusive `flock`;
  - updates `items_total`, `recent_items` and `stale_generations` on the node, and `items_new` and `items_listed` on the attempt;
  - records `items_indexed` only when the generation listed items, and `index_write_failed` when the append fails.

  The next generation's prompt (`perpetual_prompt` with the index) gives the total and up to 30 recent keys, and asks for new items only.
- **A lane that never ends.** With `saturation` 0, `agents_max` 0 and `wall_seconds` 0, a lane never ends by itself. Nodes run in order, so no later statement ever starts. Cancel the run to end it.

### 3.2 Stuck and resume

`stuck` is terminal until the operator resumes the run:

- `advance` stops driving the run.
- `_resume_stranded` never re-attaches a stuck run.
- `tools/symblic-task autogen wait` returns exit 1.
- The `/symblic/#autogen` panel stops polling it.

`cancel` ends a stuck run as `cancelled`.

`resume` (`control(run_id, 'resume', extend=None)`) works in this order:

1. **Budget first** (`_extend_budget`).
   - `extend` may carry `agents_max` and `wall_seconds`. Each must be a whole number; 0 means unlimited and needs `until_done`, and other values must fall within `LIMITS`.
   - A given value replaces the run's cap. A new `wall_seconds` counts from the resume. The event `budget_extended` is recorded.
   - If a cap is still spent after that, the resume is refused with 409, and neither the record nor the event log changes. `budget_extended` is recorded only for an extension that is accepted.
2. **Every stuck node is reopened.**
   - It returns to `pending`, with `progress_recent` false, `handoff_progress` true and `rotations` increased by 1.
   - Its tried fingerprints are moved to `fingerprints_archive` (which keeps the last 512) and cleared.
   - `rotation_start` is set to the number of recorded attempts, so `next_strategy`'s per-strategy quotas start over.
   - Every attempt that ended in a handoff is marked as progress (`progress.reopened`), so a stalled handoff chain gets a successor again.
3. **`_refresh_catalogue`** re-reads the admitted engines (`ADMITTED_ENGINES` ∩ the hub's `ENGINES`) and the machines that are online. It records `catalogue_refreshed` when either list changed.
4. **The run returns to `queued`** and records `resumed`.

Resume leaves the recorded attempts, `planners`, `split_refused` and `needs_design` unchanged. `stale_count` therefore still counts the failures since the last progress, and the designer never runs twice.

To raise a spent cap:

- **CLI:** `tools/symblic-task autogen resume RUN_ID --agents-max N --wall-seconds S`. On a 409 it prints the server's message and the matching flag.
- **Panel:** the "Raise a spent cap with Resume (optional)" box has agents and hours fields. Blank leaves a cap as it is; 0 lifts it for an `until_done` run.

## 4. Record fields and events

These node fields are new in v2. `AutogenManager._node` creates the first group; the others appear when first written.

| Field | Meaning | Written by |
|---|---|---|
| `needs_design` | True when `designer` is on, the statement names a file and the node is not perpetual. Cleared when the designer ends, whether it succeeded or not. | `_node`, `_observe` |
| `designed` | The admitted test script (≤ 8000 characters). Cleared when the script is retired. | `_observe`, `_designed_outcome` |
| `planners` | Planner attempts launched, plus self-splits. | `_intent`, `_observe` |
| `stale` | `stale_count`: work attempts since the last progress that ended with a semantic failure, a `TIMEOUT` or a handoff without progress. | `advance`, `_progress`, `control` |
| `handoff_stale` | `handoff_stale`: trailing handoffs in a row without progress. | `advance`, `_progress` |
| `progress` | `{files, checks, done}`: the node's best values so far (`merge_progress`). `done` is kept for the operator and never counts on its own. | `_progress` |
| `progress_recent` | `recent_progress`: the last finished work attempt made progress. It lets `fresh` and `feedback` repeat a fingerprint. | `advance`, `_progress`, `control` |
| `handoff_progress` | Still written, by `_progress` for handoffs and by a resume, but no rule reads it any more (`handoff_stale` replaced it). | `_progress`, `control` |
| `items_total`, `recent_items`, `stale_generations` | Index keys this node added, the last 30 of them, and promoted generations in a row that added none. | `_index_items` |
| `designed_only`, `designed_retired` | Candidates in a row that failed only the designed test, and the script retired at two. | `_designed_outcome` |
| `rotations`, `rotation_start`, `fingerprints_archive` | Resumes of a stuck node, where the current rotation's attempts begin, and cleared fingerprints (the last 512; perpetual lanes also archive here after each promoted generation). | `control`, `_promote_generation` |
| `integrations` | How many times the parent was reopened after its assembled result failed. | `_settle` |

New status values:

- A node or a run can be `stuck`.
- An attempt of kind `designer` (strategy `design`) ends `design_done` when its script is admitted, and `failed` otherwise.
- An attempt of kind `integration` (id `<node>-i<n>`) is synthetic. No task runs for it: it is recorded `failed`, with `CHECK_FAILURE` and the parent's verdict.
- A planner whose split was undone by a reopening becomes `split_done`. If the reopened parent is split again, its earlier children stay in `nodes` as history but are no longer listed in its `children`. `_split` numbers the new children after every node that has this parent, so they become `n0.2` and `n0.3`.
- The rivals of a winning self-split become `superseded`.

New planner strategies:

- `split` is the plain split.
- `split_remaining` splits what is left after stalled handoffs. Its `from` is the handoff attempt it continues, and that attempt gets `partial_promoted` once its checkout has been applied.
- `replan` is a re-plan on another engine and machine.
- A candidate that splits itself becomes kind `planner`, strategy `self_split`, with `self_split: true` and `split: [lines]`.

New attempt fields:

- A candidate, regeneration or handoff whose task ended carries `progress: {files, checks, done, new}`, also when it produced no verdict. After a resume, a handoff also carries `reopened`. Attempts that the coordinator cancelled, or that were refused at launch, carry none.
- Perpetual generations carry `items_new` and `items_listed`.

New check rows:

- `designed`: the designed test run against a candidate, with `sandbox`.
- `design`: the designer verdict. It carries `sandbox` once the script has been run.
- `split`: a split file that was refused, written at the depth limit, or inherited.

New events: `attempt_self_split`, `design_done`, `design_failed`, `design_retired`, `items_indexed`, `index_write_failed`, `index_unreadable`, `node_stuck`, `parent_reopened`, `partial_promoted`, `budget_extended` and `catalogue_refreshed`. `summary()` adds `stale` (computed by `stale_count`), `progress` and `items_total` to each node, and `until_done` to the run.

## 5. Worked example

Take a statement too big for one agent, shortened here to two files: `Create the files alpha.py and beta.py in the folder ~/symblicos/projects/demo with the functions alpha and beta.` The policy is `{"until_done": true}`, which gives `candidates` 1, `novelty_limit` 2, `self_split` on, `designer` off, `agents_max` 0 and `wall_seconds` 0.

| Pass | State | Decision |
|---|---|---|
| 1 | No attempts. | `launch` 1: `n0-a0` (candidate, `fresh`). |
| 2 | `n0-a0` ended without writing anything the checks name. Its `exists` and `change` checks failed, so its class is `NO_OUTPUT`. Its metrics are 0 files and 0 checks, which is no progress. `stale_count` is 1. | `regenerate` with `feedback`, the first choice after `NO_OUTPUT`. `n0-a1` receives the failed public checks in its context note. |
| 3 | `n0-a1` failed the same way. `stale_count` is 2, which equals `novelty_limit`. | `decompose`: planner `n0-a2` receives `split_prompt`. |
| 4 | The planner wrote two lines, one for `alpha.py` and one for `beta.py`, and `parse_split` admitted them. | `accept`, then `_split`. `n0` becomes `split`, with children `n0.0` and `n0.1` at depth 1 (`node_split`). Nothing is promoted. |
| 5 | `_current` returns `n0.0` before any later statement. | Each child gets `launch` 1. Each writes its file, passes `exists` and `syntax` and the change requirement, and is accepted and promoted (commit, then apply). |
| 6 | Both children are accepted. | `_settle` runs `_parent_verdict`. `n0`'s own checks pass in the project folder, so `n0` is accepted with winner `children`. |
| 7 | Every node is accepted. | `_finish` runs the `final` and `hidden` commands, and the run ends `completed`. |

The run launched five agents: `n0-a0`, `n0-a1`, the planner `n0-a2`, and one for each child.

- **If the parent's checks had failed in pass 6**, `_settle` would reopen `n0` (`parent_reopened`).
  - A failed `integration` attempt carries the parent's failed checks.
  - The planner becomes `split_done`.
  - `n0` is worked on as a whole again, from a project folder that now holds the children's files. Its next candidates must change something, but not every named file again.
  - In bounded mode, the run would end `failed` instead.
- **With `self_split` on**, `n0-a0` could instead have written `AUTOGEN-SPLIT.txt` in pass 2. Its checks would fail by construction, so `_observe` would make it the node's planner (`attempt_self_split`), it would supersede any rival, and pass 4 would follow at once.

One of the scratch journeys (see Status) drove exactly this sequence, and another drove the reopening.

## 6. Limits and traps

- **Progress is code-verified.** Progress is a new named file (from a passed `exists`, `syntax` or `designed` check, or a changed path the statement names) or more passing checks.
  - Both are bounded by the statement, so writing scratch files or a longer `done` list cannot keep a node "progressing".
  - A statement that names no file can progress only by passing more checks.
- **Placement failures end the plain-retry exemption.**
  - Placement failures do not count toward `stale_count`.
  - Any finished attempt without progress makes `recent_progress` false, so `fresh` and `feedback` stop repeating tried fingerprints. That includes a refused launch or a timeout, neither of which carries a progress record.
  - In a scratch check, a node that had made progress and then met repeated `INFRASTRUCTURE` failures went to `feedback`, one `fresh` retry, and then a split.
- **Conflicts.** A clash with the operator's edits in the project folder is `CONFLICT`. It gets one retry on the same engine and machine, and two in a row end the node `stuck`.
- **A self-split.**
  - A self-split wins only when the worker's own checks fail, and a genuine pass on the same node beats it.
  - A winning self-split supersedes accepted rivals and cancels running ones. The splitting worker's partial files are never promoted.
  - At the depth limit (`HARD_DEPTH` in `until_done`, `depth` in bounded mode), the split file becomes a failing `split` check instead. The worker instruction offers the split only below the depth limit and outside perpetual lanes.
  - A split file older than the attempt was inherited: the self-split probe ignores it, and a planner's is refused.
- **Splits and files.**
  - Planner splits and self-splits promote nothing.
  - A split of the remaining work first applies the last handoff's checkout to the project folder (`_promote_partial`, `partial_promoted`). `parse_split` then lets the lines omit the files that handoff's checkpoint lists.
  - If that apply is refused, or the handoff attempt has no agent identity, the node ends `stuck` (bounded mode: `failed`).
- **A reopened parent.**
  - The parent is worked on as a whole. Its regenerations get the parent's failed checks as feedback, and its candidates must change something, not every named file.
  - Its `split_done` planner still counts as a planner, so the stall rule does not split it again. A re-plan or a self-split can split it again. The new children are numbered after the old ones (`n0.2`, `n0.3`), and the old ones stay in `nodes` as history.
- **The designer is best effort.**
  - These end the designer with `design_failed`: no script; an inherited script; a script `design_valid` refuses; a script `bash -n` cannot parse; a script the sandbox refuses to run; a script whose empty-folder run is not a genuine failing exit. `needs_design` is then cleared, and candidates run without a designed test.
  - The designer runs at most once per node, and only before the first wave.
  - Its script checks that node's candidates only. The split parent's verdict does not run it, and each child gets its own designer when it names a file.
  - A failing `designed` check is classified `CHECK_FAILURE`, and its output reaches the next feedback note. Two candidates in a row that fail only on it retire it.
  - `design_valid` is advisory, and UDP stays open in the sandbox.
  - When the one-time bus probe fails, designed checks run without a scope and record `landlock`, so a missing bus never fails a check or retires a script.
- **The index is a control file.**
  - The coordinator writes `AUTOGEN-INDEX.jsonl`, under the run lock, directly into the project folder.
  - The file is in `CONTROL_FILES`, so it never counts as an attempt's change or progress.
  - The file persists across runs, so de-duplication spans every run that uses the same project folder. The prompt's known-keys hint, however, counts only this node's additions (`items_total`, `recent_items`).
- **Stuck is terminal until resume.** Nothing re-attaches a stuck run, and a resume refuses (409) while a cap is still spent (section 3.2).
- **What still ends a run.** Under `until_done` no node ends `failed`: `decide`, conflicts, refused waves and refused partial promotions end it `stuck`, and a failing split parent is reopened. The run still ends:
  - `failed`, when a `final` or `hidden` command fails in `_finish`;
  - `unknown`, after a coordinator exception or an attempt in an unknown state;
  - `cancelled`, on the operator's cancel.
- **The record grows without bound.** Attempts are never pruned, and integration attempts add to them. Some lists are capped:
  - `decisions` keeps 40;
  - `fingerprints` keeps 128, so an older fingerprint drops out of the tried set and counts as novel again;
  - `fingerprints_archive` keeps 512;
  - `recent_items` keeps 30.

## Unproductive splits end (2026-10-11)

A split child carries `parent_progress`, its parent's best code-verified evidence at the moment of the split
(named files, passing checks, accepted spec-sheet units). A child that never beats it (`unproductive_split`:
`is_progress(parent_progress, progress)` is false) may regenerate but is never decomposed again, and its terminal
reason says so ("this split made no progress over its parent (units 1 vs 1, ...), so it is not split again").
Why: on 2026-10-11 qwen2.5-coder:3b split `cellsOf` into sub-units, could not write the first sub-unit, split that
one again, and so on to depth 4 (sheets of 5, 8, 13 units, each attempt accepting the one `SHAPES` unit the
parent already had); `until_done` would have allowed `HARD_DEPTH` 12. The rule is code-owned: the stall is in
the leaves, not in the size of the statement, so more splitting cannot help. A root node is never unproductive.

