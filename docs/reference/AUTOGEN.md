# Symblic Autogen: more agents when one is not enough

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

Autogen adds a search above the Symblic task engine (`integration/host/symblicos_tasks.py`, one fresh agent per statement). By default one agent works on each statement (`candidates` 1); `candidates` 2–4 is optional parallel sampling, never a requirement. Autogen regenerates a failed statement with a different strategy, splits a statement into smaller statements, hands a worker's checkpoint to a successor with a fresh context, and runs perpetual lanes generation after generation. Every attempt is an ordinary durable task. Code decides every verdict; an agent's own words never change state.

In bounded mode (the default), per-node counts and one global budget (`agents_max`, `wall_seconds`) bound the run. In `until_done` mode, novelty and progress rules replace the per-node counts, and `agents_max` and `wall_seconds` are 0 (unlimited) unless given. [RECURSION.md](RECURSION.md) is that mode's contract.

| Part | File | Role |
|---|---|---|
| Policy | `symblic/autogen/policy.py` | Pure: validates the policy, lints statements, plans checks, classifies failures, fingerprints states, decides the next action, renders worker prompts. No I/O. |
| Coordinator | `symblic/autogen/coordinator.py` (`AutogenManager`) | Durable run record, child tasks, verdicts, remote staging, promotion. |
| Routes | `integration/host/symblicos_engine.py` | `/api/symblicos/autogen*`, operator-only. |
| CLI | `tools/symblic-task` | `start --autogen ...`, `autogen list/catalog/get/wait/cancel/resume`. |
| Page | `web/hub/autogen.js`, `autogen.css` | The `/symblic/#autogen` panel. |
| Tests | `tests/autogen/test_policy.py`, `tests/autogen/test_coordinator.py`, `tests/integration/test_symblicos_autogen_hub_lane_v2.py`, `tests/integration/test_symblic_task_cli_autogen.py` | Fake hub, fake runner, injected clock, temporary stores. `tests/integration/test_symblicos_autogen_hub_lane_v2.py` drives the coordinator in `until_done` mode. |
| Recursion contract | `docs/reference/RECURSION.md` | `until_done`: recursive decomposition without clock or count caps, the test designer and its sandbox, self-split, the perpetual dedup index. |

Status, 2026-10-11 00:52 (host local time):

- **Bounded mode** is implemented with focused tests; these docs did not run them.
- **The routes are installed.** The dashboard was restarted at 00:51:05, after the last edits to `integration/host/symblicos_engine.py` (00:11), `symblic/autogen/policy.py` (00:37) and `symblic/autogen/coordinator.py` (00:50). The modules load on the first autogen request, so the routes serve this code unless the files change again first. Four runs are recorded: one bounded run, one `until_done` run (completed at 00:32) and two perpetual lanes.
- **`until_done` and the other v2 parts** (test designer, self-split, dedup index; [RECURSION.md](RECURSION.md)) have focused tests for the policy, the CLI and the coordinator. These docs ran four of them. RECURSION.md's Status gives the details.

This page describes the code as it stood at 00:52 on 2026-10-11. Open defects are listed at the end.

## Light local models: the kernel lane

`engine local` runs attempts as kernel builds of a spec sheet, never as hub tasks: `tools/symblic-task start --sheet
SHEET.md --engine local --model MODEL --node NODE --autogen --until-done` (contract: [LOCAL-AUTOGEN.md](LOCAL-AUTOGEN.md);
beta record: [LOCAL-BETA-REPORT-2026-10-11.md](LOCAL-BETA-REPORT-2026-10-11.md)). The operator's rule: light models run on
the worker nodes, never on the host, and are the models this lane is for.

## Policy

`POST autogen/start` takes an `autogen` object (or `true` for every default). `symblic.autogen.policy.normalize` refuses unknown keys, out-of-range values, booleans in integer fields, non-boolean switches and unsafe commands. `GET autogen/catalog` returns the same `LIMITS` and `DEFAULTS`. `DEFAULTS` holds the bounded values of `agents_max` and `wall_seconds`. With `until_done`, `normalize` puts 0 (unlimited) in their place unless they are given.

| Field | Range | Default | Meaning |
|---|---|---|---|
| `candidates` | 1–4 | 1 | Agents launched together for one statement in its first wave. The default, 1, is one agent per statement; 2–4 is optional parallel sampling. |
| `regenerate` | 0–8 | 2 | Further attempts after the first wave fails. With `until_done` it is not a cap; it only sets `next_strategy`'s per-strategy quota. |
| `depth` | 0–3 | 0 | How many times a statement may be split into smaller statements. With `until_done` the limit is `HARD_DEPTH` (12) instead. |
| `children` | 2–8 | 4 | Most lines a split may have. |
| `generations` | 1–16 | 3 | Handoff successors per statement, or the generation cap of a perpetual lane. With `until_done` it is not a cap. |
| `agents_max` | 1–96; 0 only with `until_done` | 24; with `until_done`, 0 unless given | Global launch cap for the whole run. It counts every kind of attempt, including designers, planners, handoffs and perpetual generations. 0 means unlimited. A resume can raise a spent cap (`extend`). |
| `attempt_seconds` | 120–14400 | 3600 | An attempt that has been running longer than this is cancelled as `TIMEOUT`, in both modes. |
| `wall_seconds` | 300–172800; 0 only with `until_done` | 21600; with `until_done`, 0 unless given | The run deadline (`created + wall_seconds`). 0 means no deadline. A resume can raise a spent deadline (`extend`); the new value counts from the resume. |
| `interval_seconds` | 60–86400 | 900 | The pause between perpetual generations. |
| `feedback_chars` | 200–6000 | 2000 | The longest feedback note a `feedback` regeneration receives. |
| `strategies` | non-empty subset of `fresh`, `feedback`, `other_node`, `other_engine` | `fresh, feedback, other_node, other_engine` | The regeneration rotation; duplicates are dropped. `stronger_model` stays in the constant, but `normalize` refuses it until a model ladder is wired. |
| `perpetual` | bool | false | Makes every statement a perpetual lane. It requires `candidates` 1 and `depth` 0. |
| `checks` | `{"<0-based statement index>": [commands]}` | `{}` | The operator's public acceptance commands for each statement. |
| `final` | [commands] | `[]` | Commands that run in the project workspace after every statement is accepted. |
| `hidden` | [commands] | `[]` | A run-level gate. These commands run once in `_finish`, in the project folder, after every statement is accepted. Only rc and pass/fail are recorded; their output never reaches a prompt, the record or the API. |
| `syntax` | bool | true | Syntax-checks every named file by its extension. |
| `require_change` | bool | true | Refuses a statement that writes files when no workspace file changed. |
| `until_done` | bool | false | Regenerate until done. The count caps above stop ending a statement, `stuck` replaces `fail`, and a node is split when it stops making progress. Contract: [RECURSION.md](RECURSION.md). |
| `novelty_limit` | 1–8 | 2 | With `until_done`: the `stale_count` at which the statement is split. That count is the work attempts since the last progress that ended with a semantic failure, a `TIMEOUT` or a handoff without progress. |
| `self_split` | bool | true | Where a split can be accepted (below the depth limit, not a perpetual lane), every worker's instruction offers `AUTOGEN-SPLIT.txt` for a statement too big for one context. A valid split counts only when the worker's own checks fail, and a genuine pass on the node beats it. |
| `designer` | bool | false | Before the first wave of a statement that names a file, an independent agent writes `AUTOGEN-TESTS.sh`. The script is admitted only if it fails with a genuine exit (1–123) on an empty folder. It then runs as a `designed` check on a copy of every later candidate's files, and is retired once two candidates in a row fail only on it. |
| `saturation` | 0–16 | 0 | Perpetual lanes: the lane stops once this many promoted generations in a row add no new key to the dedup index. 0 means never. |

Further constraints:

- When `agents_max` is non-zero, `candidates + regenerate` must not exceed it.
- `agents_max` 0 and `wall_seconds` 0 are refused unless `until_done` is true.
- Each command is a non-empty string of at most 2000 characters with no NUL.
- A command is refused when `UNSAFE_COMMAND` matches it: `sudo`, `su`, `mkfs`, `shutdown`, `reboot`, `systemctl`, `ssh`, `scp`, `rsync`, `curl`, `wget`, `pip install`, `git push`, `docker`, `kill`/`killall`, `rm -rf /`, or `dd `. These words are matched at the start of a command, after `; & | (`, after whitespace, or after a quote or backtick. This is a refusal list, not a sandbox: an admitted command runs with the dashboard user's rights.
- The policy's `sha256` is computed over the policy without the coordinator's catalogue of `engines` and `nodes`.

## Submission

`AutogenManager.submit` accepts exactly the fields `client_request_id`, `instruction`, `engine`, `model`, `effort`, `node`, `cwd`, `context_note`, `headless` and `autogen`. It refuses a start when any of these holds:

- `client_request_id` does not match `[A-Za-z0-9_.:-]{1,160}`.
- The instruction does not have 1–64 nonblank lines.
- `cwd` is not an existing absolute folder, or `cwd/.git` is not a directory.
- `node` is empty.
- `engine` is not in `agent_hub.ENGINES`, or is not one of `ADMITTED_ENGINES` (agy, claude, codex, mistral, copilot). The default engine is `agy`.
- `symblic.autogen.policy.lint` reports an error, for example a line shorter than 20 characters, more than 64 lines, or more than 60000 characters in total.
- The context note is longer than 12000 characters.

Lint warnings do not refuse a start.

The run id is `autogen-` followed by the first 24 hex characters of `sha256(client_request_id)`. The request digest covers the lines, the base settings and the policy. Repeating a request id with the same digest returns the existing run with `duplicate: true`. Repeating it with a different digest returns 409.

At submit time the coordinator also records which alternatives the rotation may use:

- `other_engine` may choose from `ENGINES` ∩ `ADMITTED_ENGINES`.
- `other_node` may choose from the nodes that `agent_hub.fleet_nodes(refresh=False)` reports online at submit time.

Resuming a `stuck` run re-reads both lists (`_refresh_catalogue`).

## Decision procedure

On each pass the coordinator acts on the first statement node in execution order that is not accepted (`_current`). Children of a split node run before the next top-level statement. The pass first observes that node's queued and running attempts, then applies `symblic.autogen.policy.decide(node, policy, budget, now)`. The decision is pure and is appended to `node.decisions`, which keeps the last 40; a wait that repeats the previous decision is not appended again.

The list below is bounded mode. With `until_done` the rules keep this order, but the count caps are replaced by novelty and progress rules, and `stuck` replaces `fail`; [RECURSION.md](RECURSION.md), section 3, is that procedure. The rules apply in this order:

1. If the node is `accepted`, `failed`, `split` or `stuck`, the decision is **stop**.
2. If any attempt is `accepted`, the decision is **accept**. Non-planner attempts come first, so a genuine pass beats a self-split; otherwise the first accepted attempt in record order wins. A perpetual node never accepts an attempt.
3. If any attempt is queued or running, the decision is **wait**:
   - when the run deadline has passed, every running attempt is cancelled as `TIMEOUT`;
   - otherwise, attempts running longer than `attempt_seconds` are cancelled as `TIMEOUT`.

   Attempts in `unknown` or `promoting` also mean **wait**.
4. For a perpetual node, the first matching rule applies:
   - when `generation >= generations`, the decision is **accept** with no attempt;
   - when `saturation` is set and `stale_generations >= saturation`, the decision is **accept** with no attempt;
   - when more than `regenerate` generations in a row failed, the decision is **fail**;
   - when the budget is exhausted, the decision is **fail**;
   - when `interval_seconds` has not passed since the last attempt finished, the decision is **wait**;
   - otherwise the decision is **perpetual_next**. After failures, the next generation carries the next strategy's placement overrides; when no strategy is eligible, the decision is **fail**.
5. If the node has no candidate, regeneration or handoff attempt yet (designers and planners do not count), the first matching rule applies:
   - when the budget is exhausted, the decision is **fail**;
   - when `designer` is on, the statement names a file and no designer has run, the decision is **design**;
   - otherwise the decision is **launch** with `min(candidates, agents_max - agents_started)` attempts, at least 1.
6. If a `handoff` attempt has no successor yet (no attempt names it in `from`), the decision is **handoff** to the next generation. Handoffs are counted per node (`handoffs`, never reset).
   - When the budget is exhausted, the decision is **fail**. This test comes first.
   - When the generations are used up, the decision is **decompose** with `remaining`: a planner splits what the checkpoint lists as left. This needs the depth to allow another level, no planner so far and no refused split; otherwise the decision is **fail**. Before the children are created, the last handoff's checkout is applied to the project folder (`_promote_partial`), so the split may leave out the files that handoff's checkpoint lists.
   - A local successor continues in its predecessor's checkout (`cwd` = that workspace, no new checkout).
   - A remote handoff is refused as `REFUSAL` ("remote handoff unsupported"), because the task engine's submit options have no `workspaceFrom`.
7. If the budget is exhausted (agents or deadline), the decision is **fail**.
8. If the last failure is `CONFLICT`, two conflicts in a row are **fail**. One conflict gets one **regenerate** with strategy `conflict_retry` on the same engine and machine.
9. While the attempts used (not counting planners, designers and handoffs) are fewer than `candidates + regenerate`, the decision is **regenerate** with the next eligible strategy whose fingerprint the node has not tried (`_novel_strategy`). `fresh` is the fallback after every other eligible strategy.
10. The decision is **decompose**, which launches one planner, when all of these hold:
    - `depth` is greater than the node's depth;
    - the node has had no planner;
    - no split was refused;
    - the failures are semantic: two semantic failures, or a last semantic failure of `CHECK_FAILURE`, `CLAIM_MISMATCH`, `NO_OUTPUT` or `HIDDEN_FAILURE`.
11. Otherwise the decision is **fail**, naming the failures. The run becomes `failed`.

A wave the budget refuses entirely, with nothing recorded on the node, ends the node **fail** (`_launched`), so no pass repeats the refused decision.

**Strategy rotation** (`next_strategy`) depends on the last failure:

- After `INFRASTRUCTURE`, `REFUSAL`, `TIMEOUT` or `FETCH_FAILURE`, it tries `other_node`, then `other_engine`, then `fresh`. Feedback is never used after these failures.
- After `SYNTAX`, `CHECK_FAILURE`, `CLAIM_MISMATCH` or `NO_OUTPUT`, `feedback` comes first, when it is enabled.
- After `HIDDEN_FAILURE`, `feedback` is never used.
- `feedback` is used at most twice per node.
- `other_engine` and `other_node` are skipped when the catalogue has no alternative.
- Each strategy may be used `max(1, ceil(regenerate / len(strategies)))` times per rotation. The count starts at `rotation_start`, which a resume of a stuck run moves forward.
- `fresh` is the fallback when it is in `strategies`, and after a placement failure even when it is not.

**Cycle refusal.** A regeneration carries `fingerprint` = sha256 of (statement, depth, strategy, last failure class, placement overrides). The node keeps the fingerprints it has tried: `fingerprints` (the last 128) plus `last_fingerprint`. `_novel_strategy` skips a strategy whose fingerprint is already in that set and tries the next one. When none is left, the node falls through to decompose or fail. `feedback` and `fresh` are exempt in bounded mode, where the regeneration count bounds them. With `until_done` they are exempt only while the last finished work attempt made progress (`recent_progress`).

**Failure classes** (`classify`) are checked in this order:

| Order | Condition | Class |
|---|---|---|
| 1 | The task is `unknown`. The coordinator marks the attempt and the run `unknown` before classifying; nothing is relaunched. | `UNKNOWN` |
| 2 | The task was cancelled | `CANCELLED` (`TIMEOUT` when the attempt carries `timeout_requested`) |
| 3 | The task failed and its error mentions a refusal | `REFUSAL` |
| 4 | The task failed for any other reason (including admission, budget, "not installed" and "Pick a…") | `INFRASTRUCTURE` |
| 5 | The verdict passed | no class |
| 6 | A valid checkpoint with a non-empty `left` exists (never on a perpetual lane) | `CONTEXT_EXHAUSTED` |
| 7 | A `fetch` (staging) check failed | `FETCH_FAILURE` (infrastructure: another machine next) |
| 8 | The step evidence carries a claim warning | `CLAIM_MISMATCH` |
| 9 | An `exists`, `absent` or `change` check failed | `NO_OUTPUT` |
| 10 | A `syntax` check failed | `SYNTAX` |
| 11 | A `command`, `designed` or `design` check failed | `CHECK_FAILURE` |
| 12 | A `hidden` check failed | `HIDDEN_FAILURE` |
| 13 | `files_changed == 0` | `NO_OUTPUT` |
| 14 | Anything else | `UNKNOWN` |

A task that did not complete is never a pass, whatever its workspace shows. `CONFLICT` is not a `classify` result. `_promote` sets it when the hub's `apply` returns a non-empty `conflicts` list, or when commit or apply raises an error whose text mentions a clash or a conflict. The live `agent_hub.apply_work` raises "Nothing was applied: N file(s) clash…". Any other exception makes the attempt `INFRASTRUCTURE` ("apply refused: …").

Hidden commands no longer classify attempts: they run once at the end (`HIDDEN_FAILURE` is the class for that run-level gate's failure in reports).

When a launch raises `TaskError`, the attempt fails as `REFUSAL` if the message contains "refus" and as `INFRASTRUCTURE` otherwise. The launch still counts against `agents_max`.

**Budget.** `budget.agents_started` increases by one when each launch intent is recorded, before the task is submitted. `_launch_wave` refuses a launch once `agents_max` is non-zero and `agents_started >= agents_max` (event `launch_refused`); when that refuses a whole wave, `_launched` ends the node (`failed`, or `stuck` under `until_done`). The cap and the deadline apply to the whole run, not to each statement. With `until_done`, both may be 0, and then neither ever stops a launch.

## Verdicts: code only

`_verdict` builds the checks from `plan_checks(statement, index, policy)`.

**Existence.** Each file the statement names (`file X`, `the files A, B and C`, or a bare `name.js`/`.py`/`.html`/`.css`/`.json`/`.md`/`.txt`/`.sh`/`.svg`) must be present in the attempt's workspace listing. A listed file counts when its path equals the name or ends with `/name`. A read-only statement skips this check. A statement is read-only when it starts with read, inspect, check, verify, test, run, monitor, watch, research, index, scan, summarize or collect. A read-only statement that also uses a word starting with creat, writ, produc, generat, record or append keeps the check.

**Syntax**, when `syntax` is on:

| Extensions | Command |
|---|---|
| `.js`, `.mjs`, `.cjs` | `node --check` |
| `.py` | `ast.parse` through `python3` |
| `.sh`, `.bash` | `bash -n` |
| `.json` | `json.load` |

Other extensions get no syntax check.

**Public commands.** The commands in `checks["<index>"]` run for top-level statements only. A split child is keyed by its node id, so it gets none.

**Hidden commands** do not run per attempt. They run once in `_finish`, in the project folder, after every statement is accepted. Only rc and pass/fail are stored, with `public: false`.

**Change.** When `require_change` is on and the statement is not read-only, every primary named file must be in the attempt's change set. Otherwise the coordinator adds a failing `change` check for it, and a change set with no files fails as a whole. Locally the change set comes from the task evidence, or from `git` in the checkout when that evidence is truncated (the task engine's inventory stops at `INVENTORY_FILES = 200`). Remotely it comes from `git diff --name-only <base> <fetched ref>`. Autogen's control files never count. When no change set can be read, no change check is added. A reopened parent (`until_done`, after its assembled result failed) must change something, not every named file.

**Claim.** A claim warning in the step evidence becomes a failing `claim` check. The task engine raises that warning when the agent's final text claims work and no file changed.

**Designed test.** With `designer` on, a node's admitted `AUTOGEN-TESTS.sh` runs as a `designed` check against a throwaway copy of each candidate's files (without `.git`; at most 20000 entries), never the candidate's checkout. It runs inside the Landlock sandbox (`sandbox_prefix`: `env -i`, then `symblic/sandbox/landlock.py --require --no-unix --net-connect 1`). When `systemd-run` and `XDG_RUNTIME_DIR` are available and a one-time probe of the user bus succeeds, it also runs inside a transient user scope under `a systemd slice for work` (`TasksMax=64`, `MemoryMax=1G`), which is stopped afterwards. `systemd-run` gets `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` explicitly, because the check runner scrubs the environment. The row records `sandbox: 'landlock+scope'`, or `'landlock'` without a scope. A launcher refusal (exit 125) is a failed check, never an unsandboxed run. `design_valid` is an advisory refusal list, and UDP stays open in the sandbox. See [RECURSION.md](RECURSION.md), section 2.1.

Commands run as `bash -c COMMAND` in the verification folder. The environment contains only `PATH`, `HOME`, `LANG=C.UTF-8` and `TMPDIR`. They run at nice 10 with a 120 s timeout (a timeout gives rc 124). Output keeps the last 4000 characters, and each check stores its last 1500. A command passes only when it exits with rc 0.

**Feedback.** A `feedback` regeneration receives `feedback_note`: only the failed checks marked `public: true` whose kind is `exists`, `absent`, `syntax`, `command`, `change`, `claim` or `designed`, each output cut to 800 characters, the whole note cut to `feedback_chars`. It is prepended to the context note. Hidden and fetch results and other candidates' code are never included.

**Final commands** run in the project workspace (`base.cwd`) after every node is accepted. If any fails, the run ends `failed` with "Every statement was accepted, but a final check failed". The coordinator does not regenerate after a final failure.

## Placement, staging and promotion

Each attempt is submitted to the task engine with `mode: agent`, `worktree: true`, `auto: true`, `auto_next: true` and `headless` taken from the base settings. The task therefore runs in the hub's own checkout:

- **Locally**, that checkout is `<project>.agents/<agent name>-<stamp>` beside the project. It starts from the project's `HEAD` plus its uncommitted files (`the agent hub` carry-over).
- **On a worker node**, it is the provisioned checkout on that node.

**Local verification** runs in the candidate's checkout (`step.agent.git.cwd`).

**Remote verification** first stages the result at home. The coordinator runs `work_action('commit')` on the node, which commits there and fetches the branch home. It then runs `git -C <main_root> worktree add --detach -f <symblic/os root>/state/autogen/staging/<run>/<attempt> refs/agents-nodes/<node>/<branch>`, runs the checks there, and removes the staging worktree with `git worktree remove --force`. A staging failure becomes a failed `fetch` check (`FETCH_FAILURE`), which never reaches a feedback note. The remote change set is `git diff --name-only <base> <fetched ref>`.

**TUI agents** stop at the task engine's review gate: the step is `awaiting_review` and the agent is not running. The coordinator computes the verdict and then closes the task itself, with `tasks.control(id, 'next')` when the attempt passed and `'cancel'` when it failed. A failed close is recorded as the event `close_failed`. When a remote child sits at that gate with its agent still running and no evidence (its task coordinator was lost to a dashboard restart), the autogen coordinator drives one task-engine observation pass itself (`_gated_live`; event `child_observe_failed` on an unexpected error).

**Promotion** happens when a node is accepted. The coordinator calls `agent_hub.work_action('commit', agent_id)` and then `work_action('apply', agent_id)`. Apply is `agent_hub.apply_work`, a per-file 3-way merge of the candidate's base, its branch tip and the project's working copy, written into the working copy without a commit there. A clash raises "Nothing was applied: N file(s) clash…". The attempt then fails as `CONFLICT` (event `promotion_failed`). It gets one retry on the same engine and machine; a second conflict in a row ends the node (`failed`, or `stuck` under `until_done`). After a successful apply, every other queued or running attempt of that node is cancelled and recorded as `failed`/`CANCELLED` with "another candidate was accepted first".

**Planner attempts** write `AUTOGEN-SPLIT.txt`. `parse_split` requires all of the following:

- 2 to `children` lines;
- no lint errors;
- every file the parent names is named by some child;
- every line names the workspace folder itself, and no other folder;
- no line repeats the parent statement.

A valid split creates child nodes `<parent>.<i>` at `depth + 1`, using the parent's engine and node, and marks the parent `split`. The parent becomes `accepted` (winner `children`) only when every child is accepted and the parent's own checks then pass in the project folder (`_settle`, `_parent_verdict`). Otherwise, in bounded mode, the parent and the run fail; under `until_done` the parent is reopened and worked on as a whole ([RECURSION.md](RECURSION.md)). A planner's checkout is never promoted.

In bounded mode `decide` launches at most one planner per node, so a failed split ends in **fail**; `until_done` re-plans on another engine and machine.

A worker may also write the split file itself (self-split, with `self_split` on). When its own checks fail and the depth limit allows another level, the attempt becomes the node's planner and supersedes its rivals, and its files are not promoted. A split of the remaining work, after stalled handoffs, first applies the last handoff's checkout (`_promote_partial`, event `partial_promoted`); if that handoff has no agent identity or the apply is refused, the node ends. A parent split a second time keeps its first children as history and numbers the new ones after them (`n0.2`, `n0.3`) ([RECURSION.md](RECURSION.md)).

## Record and events

The record root is `<symblic/os root>/state/autogen/`. The symblic/os root is `SYMBLICOS_ROOT`, by default `~/symblicos`.

| File | Contents |
|---|---|
| `autogen-<24 hex>.json` | The run row, written atomically (`atomic_json`) after every change. |
| `autogen-<24 hex>.events.jsonl` | Append-only events, each `{at, seq, event, …}`, fsynced. |
| `autogen-<24 hex>.lock` | Serializes record writes. |
| `autogen-<24 hex>.worker.lock` | Held by the one live coordinator thread for the run. |
| `autogen-<24 hex>.alive` | The heartbeat: the coordinator's process id, touched while it drives the run. |

The coordinator module's docstring says `run-<id>.json`; the code writes `<run id>.json` as shown here.

The event names are: `submitted`, `decision`, `launch_intent`, `launched`, `launch_recovered`, `launch_failed`, `launch_refused`, `attempt_accepted`, `attempt_handoff`, `attempt_failed`, `attempt_timeout`, `attempt_unknown`, `attempt_self_split`, `child_observe_failed`, `design_done`, `design_failed`, `design_retired`, `items_indexed`, `index_write_failed`, `index_unreadable`, `generation_done`, `promoted`, `promotion_failed`, `promotion_in_doubt`, `partial_promoted`, `node_accepted`, `node_split`, `node_failed`, `node_stuck`, `parent_reopened`, `close_failed`, `cancel_failed`, `cancel_requested`, `resumed`, `budget_extended`, `catalogue_refreshed`, `cancelled`, `completed`, `final_failed`, `run_unknown` and `staging_drop_failed`.

Perpetual lanes also keep a dedup index, `AUTOGEN-INDEX.jsonl`, in the project folder. It is a control file ([RECURSION.md](RECURSION.md), section 3.1). The v2 node and attempt fields are listed in [RECURSION.md](RECURSION.md), section 4.

Each child task keeps its own record under `<symblic/os root>/state/tasks/task-<32 hex>.json`. The task id is `sha256` of the child request id `<client_request_id>:<node id>-a<ordinal>`. Before submitting, the coordinator writes the intent, including the exact task body, into the run record. If it dies between that write and recording the task id, the next pass re-submits the same body under the same request id. The task engine then returns the reserved task (event `launch_recovered`), so the attempt is never launched twice.

## Handoff protocol for workers

Every candidate, regeneration, handoff and perpetual instruction ends with `worker_suffix`. It tells the worker to finish the one statement and stop, and to treat only files on disk as results. When `self_split` is on, it also offers `AUTOGEN-SPLIT.txt` for a statement too big for one context. When `generations > 1` or the run is perpetual, a worker that nears the end of its context must write two files before stopping:

- `HANDOFF.md` with the headings `Done`, `Left` and `Files`, one line per file touched;
- `AUTOGEN-CHECKPOINT.json` with `{"version": 1, "done": [...], "left": [...], "files": [...]}`.

The coordinator reads the checkpoint from the attempt's workspace (at most 20000 bytes). It is accepted only when all of these hold:

- the file is not older than the attempt start minus 5 s;
- it parses as JSON with `version` 1;
- `done`, `left` and `files` are lists of strings;
- every entry in `files` exists in the workspace, by exact relative path;
- `done` and `left` are not both empty.

A valid checkpoint makes a non-passing attempt `CONTEXT_EXHAUSTED`. The attempt becomes `handoff`, and the next decision launches generation `g + 1` with `handoff_prompt`. That prompt gives the checkpoint's Done (≤1500 characters), Left (≤1500) and Files (≤800), and tells the successor to read the files on disk first, not redo listed work, and finish what is left. An invalid checkpoint is ignored, and the attempt is classified on its checks. A checkpoint's `done` list never counts as progress on its own. With `until_done`, once two handoffs in a row add no progress (`handoff_stale`), the remaining work is split instead, after the last handoff's checkout has been applied ([RECURSION.md](RECURSION.md), section 3, rule 6).

## Perpetual lanes

A perpetual lane is for monitoring and indexing work that repeats. It runs one generation at a time. In bounded mode it never runs more than `generations` successful generations; with `until_done` there is no generation cap.

- Each generation's instruction is `perpetual_prompt`. It asks for one bounded batch, then the checkpoint file and `HANDOFF.md`, with `done` covering this and earlier generations and `left` as the cursor for the next generation. The cursor comes from the last `generation_done` attempt (only promoted generations store a checkpoint), so a failed generation never moves the cursor.
- A generation that passes its checks is promoted immediately and becomes `generation_done`, and the node's generation advances.
- A failed generation does not advance the counter. The next generation launches after `interval_seconds`, with the strategy rotation's placement overrides, still bounded by `agents_max` and the deadline. More than `regenerate` failed generations in a row fail the lane. With `until_done`, the lane becomes `stuck` instead, once no untried strategy is left.
- When the cap is reached, or `saturation` generations in a row add no new key to the dedup index, the node is accepted with winner `generations`.
- Once a passing generation has been promoted, `_promote_generation` indexes the sources or findings it listed under `items` in its checkpoint (`_index_items`). Items may be strings or objects; `checkpoint_valid` reduces an object to text with `item_text` (DOI, URL, title and similar fields). Each item gets a key from `items_key` (`doi:`, `url:` for the URL's first word, or `text:`), and new keys are appended to `AUTOGEN-INDEX.jsonl` in the project folder. The next generation is told how many items exist and what the most recent keys are. Each promoted generation also clears the lane's tried fingerprints ([RECURSION.md](RECURSION.md), section 3.1).
- `perpetual` applies to every statement of the run, and statements still run in order. A later statement starts only after the earlier lane reaches its cap.

## API

All routes are under `/api/symblicos/`, behind `handler.require_owner` (a loopback request without a proxy-forwarding header counts as the operator). `submit`, `control` and every coordinator pass also require `host_check()`, which allows only the runner host and otherwise answers 503. Errors are `{"error": text}` with the error's status (400, 404, 409 or 503).

```
GET  autogen                         -> {"runs": [run rows, newest file mtime first, at most 100]}
GET  autogen/get?id=RUN_ID[&tasks=1] -> {"run": row (+ "tasks": {task_id: task row} with tasks=1)}
GET  autogen/catalog                 -> {"version": 1, "limits": {field: [low, high]}, "defaults": {...},
                                         "strategies": [...], "all_strategies": [...], "failure_classes": [...],
                                         "handoff_file": "HANDOFF.md", "checkpoint_file": "AUTOGEN-CHECKPOINT.json"}
POST autogen/start   {"client_request_id": "...", "instruction": "line 1\nline 2", "engine": "agy",
                      "model": "", "effort": "", "node": "node-i", "cwd": "~/symblicos/projects/NAME",
                      "context_note": "...", "headless": true, "autogen": {...policy...}}
                                     -> {"run": row, "duplicate": false|true}
POST autogen/control {"id": RUN_ID, "action": "cancel"|"resume", "extend"?: {"agents_max": N, "wall_seconds": S}} -> {"run": row}
```

The run row read by `get` (and by `autogen`, which calls `get` for each run) contains:

- the run fields `id`, `client_request_id`, `request_digest`, `version`, `status` (`queued|active|completed|failed|cancelled|unknown|stuck`), `error`, `created`, `updated`, `cancel_requested`, `seq`, `base` {engine, model, effort, node, cwd, context_note, headless}, `policy` (normalized, with `sha256`, `engines` and `nodes`), `lines`, `budget` {agents_started, agents_max, deadline}, `nodes`, `order`, `final` ({checks, passed} or null) and, after a resume, `resumed`;
- `resume_required`, true when the status is `queued` or `active` and there is no fresh heartbeat from this process (`_alive`);
- `summary` (`symblic.autogen.policy.summary`).

The row returned by `start` is the stored record, without `resume_required` or `summary`.

A node is:

```
{id ("n0", "n0.1"), index, parent, depth, statement, status (pending|accepted|failed|split|stuck),
 attempts, children, generation, handoffs, perpetual, winner ("" | attempt id | "children" | "generations"),
 last_fingerprint, fingerprints, split_refused, planners, needs_design, designed, progress, stale,
 progress_recent, handoff_progress, items_total, stale_generations, recent_items?,
 fingerprints_archive?, rotations?, rotation_start?, handoff_stale, integrations?, designed_only?, designed_retired?,
 parent_verdict?, engine, node, decisions [{at, action, reason, ...}], error?}
```

An attempt is:

```
{id ("n0-a1"), kind (candidate|regen|designer|planner|handoff|perpetual|integration), strategy, engine, node, model,
 generation, request_id, task_id, status (queued|running|promoting|accepted|superseded|failed|handoff|generation_done|design_done|split_done|unknown),
 started, finished, failure, verdict {passed, checks [{kind, file?, command?, passed, output, public, sandbox?}],
 files_changed, report, staging?, changed?}, workspace, agent_id, error, from, duplicate,
 checkpoint?, split?, self_split?, progress?, items_new?, items_listed?, partial_promoted?, applied?, body? (only until the task id is recorded)}
```

Each attempt's agent terminal is linked from `GET /api/symblicos/tasks/get?id=<task_id>` at `steps[0].url`.

`control` behaves as follows:

- `cancel` sets `cancel_requested`. The next pass cancels every queued or running attempt that has a task id and ends the run `cancelled`.
- `cancel` on a run in `unknown` cancels its live children and ends it `cancelled`; on `completed`, `failed` or `cancelled` it returns the run unchanged. A coordinator exception cancels the run's live children before the run is marked `unknown`.
- `resume` re-attaches the coordinator thread. A run in `unknown` returns to `queued`, and its error is cleared. Recorded attempts are observed again, never launched twice.
- `resume` on a `stuck` run first applies `extend` (`_extend_budget`; 0 lifts a cap under `until_done`). It answers 409, changing neither the record nor the event log, while a cap is still spent. It then reopens every stuck node with a new rotation and re-reads the engine and machine lists ([RECURSION.md](RECURSION.md), section 3.2). `cancel` ends a `stuck` run as `cancelled`.

## CLI

```sh
tools/symblic-task workspace NAME                                   # git-initialised, with a baseline commit
tools/symblic-task start --lines lines.txt --root ~/symblicos/projects/NAME --node node-i --engine agy \
    --autogen --until-done --agents-max 0 --wall-seconds 0       # one agent per line, no clock or count caps
tools/symblic-task start --lines lines.txt --root ~/symblicos/projects/NAME --node node-i --engine agy \
    --autogen --candidates 2 --regenerate 3 --decompose 1 --agents-max 12 \
    --check '0:node --check app.js' --final 'node --check app.js' --hidden 'node test/hidden.js'   # bounded, 2 candidates
tools/symblic-task autogen wait RUN_ID          # one line per status change; exit 1 failed/unknown/cancelled/stuck, 4 at --max,
                                              # 0 completed OR coordinator absent twice in a row: read the printed "next:"
tools/symblic-task autogen get RUN_ID --tasks   # the tree, failed public checks, terminal links
tools/symblic-task autogen list | catalog | cancel RUN_ID | resume RUN_ID [--agents-max N] [--wall-seconds S]
```

- Any autogen flag makes `start` an autogen run. The flags are:
  - `--autogen`;
  - `--candidates`, `--regenerate`, `--decompose` (depth), `--children`, `--handoff` (generations), `--perpetual SECONDS` (perpetual with that interval);
  - `--agents-max`, `--attempt-seconds`, `--wall-seconds`, `--strategies a,b`;
  - `--check 'INDEX:cmd'` (0-based, repeatable), `--final`, `--hidden`, `--no-syntax`, `--allow-no-change`, `--no-headless`;
  - `--until-done`, `--designer`, `--no-self-split`, `--novelty-limit N`, `--saturation N`.
- One agent per line is the default (`--candidates 1`). More candidates are optional parallel sampling.
- `--agents-max 0` and `--wall-seconds 0` mean unlimited. They are accepted only with `--until-done`; the CLI checks the policy locally with the same `normalize`, and the server checks it again.
- With `--until-done` and neither flag, both are 0. An explicit value is a safety cap, and the run then ends `stuck`, never `failed`.
- `--parallel`, `--worktree`, `--auto-next`, `--no-auto` and `--mode agent` are refused for autogen runs.
- The CLI lints the lines and caps `--id` at 120 characters.
- It prepends a note to the context note telling each candidate that it works in its own checkout of the named folder and must never write into the folder itself.
- Without `--node` it sends `host`; pass a worker node for real work.
- For a `stuck` run, `autogen wait` exits 1 and prints `resume: symblic-task autogen resume RUN_ID [--agents-max N] [--wall-seconds S] after changing the statement, the checks or the catalogue`. `autogen resume` reopens the run ([RECURSION.md](RECURSION.md), section 3.2). Its `--agents-max` and `--wall-seconds` raise a spent cap (0 lifts it under `until_done`). On a 409 the CLI prints the server's message and the matching flag.
- `autogen get`, and `autogen wait` when it ends, show an unlimited cap as `unlimited` and add `until done` to the budget line. They also show each node's `stale` count, its progress (files, checks, done) and, for perpetual lanes, its indexed items. While polling, `wait` prints only the compact status line. They also show `handoff stale` and `integrations` counts, and print an integration attempt as "integration check failed".
- `autogen catalog` lists the limits, the defaults and the switches, plus a line on what 0 means with `until_done`.

## Hub panel

`/symblic/#autogen` (`web/hub/autogen.js`) shows a statement editor, agent type, machine, model and effort, the workspace (or Create workspace), the context note, every policy field with the limits from `autogen/catalog`, the strategies, public checks numbered **from 1** (`STATEMENT_NUMBER: command`), final and hidden commands, and the switches.

The v2 controls appear only when the catalogue lists them: limits for `novelty_limit` and `saturation`, and boolean defaults for `until_done`, `designer` and `self_split`. An older server gets a note instead, and the panel never sends fields it would refuse. The controls are:

- **Until done.** Switching it on sets "Agents for the whole run" and "Hours for the whole run" to 0 (unlimited); switching it off restores the earlier values. While it is on, regenerations, split depth and generations are marked "Not a cap until done".
- **Test designer** and **Self-split** switches.
- The fields "Attempts without progress before a split" (`novelty_limit`) and "Perpetual generations with nothing new before the lane stops" (`saturation`).

The panel sends Start exactly once. The request id is a draft id (`autogen-ui-<uuid>`) that is retired only when the server records the run. If the outcome is unknown, the panel derives the expected run id with the same SHA-256 and observes that run without re-sending the start.

Opening a run only reads it, polling every 10 s. Cancel and Resume are explicit buttons, and each attempt links to its task terminal.

A `stuck` run is not polled. Resume and Cancel stay available for it, with the hint "Resume after changing the statement, the checks or the catalogue". Once a cancel is pending, the panel polls the run again and offers no Resume.

For an `until_done` run, the budget reads "unlimited", with no bar, when `agents_max` is 0, and "No deadline: no clock ends this run" when `wall_seconds` is 0. Each node shows its measured progress, its stall count against `novelty_limit` and, for a perpetual lane, its indexed items.

For a stuck run, the panel also shows a "Raise a spent cap with Resume (optional)" box with agents and hours fields. Blank leaves a cap as it is; 0 lifts it for an `until_done` run; hours count from the resume. A 409 refusal is shown verbatim. Integration attempts are labelled "integration check", a reopened split shows as "split (history)", and nodes carry "N handoffs without progress" and "reopened N× after integration" tags.

## Traps

- **A git workspace is required.** Candidates are own checkouts, and promotion is commit → apply. `cwd/.git` must be a directory, so a linked worktree (where `.git` is a file) is refused. `symblic-task workspace NAME` creates one with a baseline commit.
- **Remote results are verified at home.** The branch fetched from the worker node is staged under `<symblic/os root>/state/autogen/staging/<run>/<attempt>` and removed afterwards (leftovers are pruned before a new add). Remotely the change set is `git diff --name-only <base> <fetched ref>`.
- **TUI agents end at the review gate.** Such agents (for example interactive agy or claude) stop at `awaiting_review`. The coordinator, not the operator, presses Next or Cancel after its verdict. Do not press Next on an autogen child task yourself.
- **`agents_max` is global.** Planners, handoffs, perpetual generations and refused launches all count. A wide first wave on many statements can exhaust the budget before later statements start, and then the run fails.
- **Feedback carries public check output only.** Write public checks whose output helps a fresh agent, and keep acceptance secrets in `hidden`.
- **Re-attachment after a restart.** `GET autogen` and `autogen/get` re-attach a coordinator to a queued or active run updated within the last two hours whose cancel is not pending (the same window as the task engine); older runs need `symblic-task autogen resume RUN_ID` or the page's Resume. Liveness is the heartbeat file (`<run id>.alive`), never the worker lock. A heartbeat counts only when it is fresh (within 300 s) and was written by this process, so one left by the process before a restart counts as dead at once.
- **Public checks follow statement indexes.** They key on the top-level statement index (0-based in the CLI, 1-based in the panel). Split children get no operator commands.
- **`until_done` has its own traps:** code-verified progress, conflicts, self-split rules, reopened parents, and the designer's reach. See [RECURSION.md](RECURSION.md), section 6.
- **A named file must be part of the attempt's change set.** For a statement that writes, every primary named file must appear in the attempt's added/modified set (task evidence, or `git status`/`git diff` in the checkout when the evidence is truncated); autogen's own control files never count. Delete/Remove statements are checked by absence; Rename/Move by the destination only.

## Limits

- An accepted statement passed exactly the declared checks, and the task completed. The checks are:
  - the named files exist and changed;
  - the syntax checks pass;
  - the operator's public commands exit 0;
  - the change and claim checks pass;
  - the designed test passes, when there is one.

  A split parent is accepted only when its own checks pass after its children. The run completes only when the operator's `final` and `hidden` commands also exit 0 in the project folder. That is the only correctness claim autogen makes. A statement with no named files and no commands is accepted on very little evidence.
- No success rates, cost figures or comparisons with single-agent runs have been measured, in either mode. One `until_done` run has been recorded; it has no measured result. Test counts in the suites are software verification, not model results.
- Hidden commands run once at the end; only rc and pass/fail are recorded, never their output.
- The unsafe-command list refuses obvious mistakes. It does not confine commands. Model-written test scripts (the designer's) also run in the Landlock sandbox, on a copy and, when available, in a systemd scope. That sandbox does not block UDP.
- `until_done` with `agents_max` 0 and `wall_seconds` 0 has no clock or count stop. A run ends when every node is accepted, when a node is stuck, or when a `final` or `hidden` command fails.
- Nothing restarts itself, and no run resumes without an explicit resume. A `stuck` run waits for the operator.

## Review history

The first revision (21:22, 2026-10-10) was reviewed by three local adversarial lanes and one independent Claude cloud review (24 findings, D1 to D24, plus 14 crash transitions). Every finding was fixed or explicitly refused in the second revision (22:30): worktree localization of prompts (`CHECKOUT_LOCK` prepended, the project path rewritten to the working folder), locked read-modify-write of the record, hidden checks as a run-level gate, named-file change requirements, verb-aware checks, strategy rotation and cycle rules, perpetual cursor and failure caps, handoff continuation in the predecessor's checkout (remote handoff refused), cancel on unknown runs, re-attachment after restarts, staging under the state folder, process-group kills for checks, and gap-free event sequence numbers. The remaining known limits: operator `final` commands run again if the process dies inside `_finish`; a crash between appending an event and writing the record can leave an event the record never shows; remote handoff waits for `workspaceFrom` in the task engine's options.

The v2 revision (2026-10-11, 00:03) added, from the code, `until_done`, the test designer and its sandbox, self-split and the perpetual dedup index, with [RECURSION.md](RECURSION.md) as the contract for `until_done`. It has not been reviewed.

The v3 revision (2026-10-11, 00:42) followed the code changes made between 00:00 and 00:37: stall counters derived from the attempts, code-verified progress, conflicts from apply errors, `stuck` in place of every node failure under `until_done`, reopened parents, split-remaining promotion, a resume that can raise a spent cap, a designed check on a copy inside a systemd scope, designed-test retirement, index writes after promotion, item objects and URL-only item keys, and heartbeat liveness by process. It has not been reviewed.

The v4 revision (2026-10-11, 00:49) followed the fixes of 00:44: a second split numbers its children after the first, a refused extension leaves no event, a split of the remaining work without an agent identity ends the node, and the scope is used only after a bus probe. The scope-environment defect found while checking that probe was fixed at 00:50: `systemd-run` now gets the bus variables. It has not been reviewed.
