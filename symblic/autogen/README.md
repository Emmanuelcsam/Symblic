# symblic/autogen: regenerate, split and hand off agent attempts until code accepts them

> **Status: experimental.** Every rule here is unit-tested with fakes. Real runs were few, and on a
> private machine that is not part of this repository; what they showed is summarized under
> [What was measured](#what-was-measured), including the part that did not work.
>
> Like all of Symblic, this package was written by AI coding agents (Claude Code, Codex and others)
> working under the direction of one person. Read it as an agent-built prototype, not as a reviewed
> library.

## What autogen is

A Symblic *task* is a list of precise statements, one per line ("Create the file app.py in the
folder /work/project with a function named main."). Each statement is carried out by a **fresh**
coding agent that sees only that statement, and it is accepted only by **code**: the files it names
exist and were changed by that attempt, they parse, and they pass the operator's commands.

Autogen adds regeneration on top. For each statement it can:

- launch several independent **candidates** and keep the first one code accepts;
- **regenerate** a failed statement with a different strategy (`fresh`, `feedback` with the public
  check output, `other_node`, `other_engine`), refusing to repeat a search state it already tried;
- **decompose** a statement into 2 to `children` smaller statements when regeneration stops helping
  (a planner attempt writes `AUTOGEN-SPLIT.txt`; a worker may also answer "too big" with that file);
- **hand off** to a successor with a fresh context when a worker runs out of context
  (`HANDOFF.md` + `AUTOGEN-CHECKPOINT.json`, whose listed files must exist on disk);
- run **perpetual lanes** for monitoring or research work, generation after generation, with a
  deduplicated item index (`AUTOGEN-INDEX.jsonl`) and a saturation stop;
- let an independent **test designer** write `AUTOGEN-TESTS.sh` before any candidate exists; the script
  counts only if it fails on an empty folder, and it runs sandboxed against a throwaway copy of each
  candidate's files.

Nothing an agent *says* changes state. A worker that claims "done" while no file changed, a split that
drops a file, or a checkpoint that names files absent from disk is refused by code.

## How the pieces fit

```
task text ─► AutogenManager.submit()  ─►  run record  <root>/state/autogen/<run id>.json
                                           + append-only <run id>.events.jsonl
             AutogenManager.advance()  (a background thread per run, or called by hand in tests)
                │
                ├─ policy.decide(node) ─► wait | launch | regenerate | decompose | handoff
                │                          | perpetual_next | design | accept | fail | stuck
                │
                ├─ agent attempts ──► TaskRunner (runner.py)  ◄── your agent launcher goes here
                │                     submit / get / control / promote / fetch_remote
                │
                └─ spec-sheet attempts ──► kernel_lane.py: a `tools/symblic run` build per attempt,
                                           in its own checkout (git_checkouts.py)

verdict:    files exist and changed · syntax by extension · the operator's commands ·
            the designed test (sandboxed) · claim vs disk
promotion:  a durable intent, then commit in the attempt's checkout → per-file 3-way apply into
            the project folder (never a commit in the project; any clash refuses everything)
```

| File | What it is | Depends on |
|---|---|---|
| [`policy.py`](policy.py) | Pure rules: `normalize` (the policy object), `lint`, `plan_checks`, `classify`, `progress_metrics`, `decide`, the worker prompts. No I/O. | standard library |
| [`coordinator.py`](coordinator.py) | `AutogenManager`: run records, attempts, verdicts, promotion, cancel and resume, crash recovery. | policy, runner, kernel_lane, durable; git; the Landlock launcher for designed tests |
| [`runner.py`](runner.py) | The `TaskRunner` protocol, the task record it returns, evidence helpers, `KernelOnlyRunner`, and the documented `FakeTaskRunner`. | standard library |
| [`kernel_lane.py`](kernel_lane.py) | Attempts of `local` runs: spec-sheet builds with small local models, the typed split planner, run-folder parsing. | symblic.spec.sheets, symblic.js (sandboxed checks), git_checkouts, `tools/symblic` |
| [`git_checkouts.py`](git_checkouts.py) | An own git worktree per attempt (`<project>.autogen/<name>-<stamp>`, branch `autogen/...`) and the 3-way apply of an accepted one. | git |
| [`workspaces.py`](workspaces.py) | Managed empty git project folders (`<root>/projects/<name>`). | git |
| [`durable.py`](durable.py) | Crash-safe JSON writes. | standard library |

## Using it

```python
from symblic.autogen.coordinator import AutogenManager

manager = AutogenManager('/path/to/state-root', task_runner=MyRunner())   # MyRunner implements TaskRunner
run = manager.submit({
    'client_request_id': 'calc-1',                      # stable: the same id and body return the same run
    'instruction': 'Create the file calc.py in the folder /work/calc with add(a, b) returning a + b.\n'
                   'Run python3 -m unittest in the folder /work/calc and write verify.txt with one line: pass or the error.',
    'engine': 'claude', 'node': 'this-machine', 'cwd': '/work/calc',          # cwd must be a git repository
    'autogen': {'candidates': 2, 'until_done': True, 'checks': {'0': ['python3 -c "import calc"']}},
})['run']
# background=True (the default) drives the run in a thread; manager.get(run['id']) reads it.
```

There is no agent launcher in this repository. `TaskRunner` (in [`runner.py`](runner.py)) documents
every method and every field of the task record the coordinator reads, and `FakeTaskRunner` is a
complete in-memory implementation you can read as an example. The only real runner that existed drove
the original host's agent hub; it is kept for reference in
[`integration/host/symblicos_tasks.py`](../../integration/host/symblicos_tasks.py) (`TaskManager` and the
`HubTaskRunner` adapter) and does not run outside that host.

Without a runner, `AutogenManager(root)` uses `KernelOnlyRunner()`: only spec sheets on the kernel lane
can run. Pass `KernelOnlyRunner(nodes=['node-a'])` to name the machines that serve local models.

## The policy: bounded mode and `until_done`

`policy.normalize` validates the `autogen` object of a request; unknown fields and out-of-range values
are refused.

| Field | Default | Range | Meaning |
|---|---|---|---|
| `candidates` | 1 | 1-4 | independent attempts launched together for one statement |
| `regenerate` | 2 | 0-8 | further attempts after the first wave fails (bounded mode) |
| `depth` | 0 | 0-3 | how many times a statement may be split (bounded mode; `until_done` allows 12) |
| `children` | 4 | 2-8 | statements one split may produce |
| `generations` | 3 | 1-16 | handoff successors, or perpetual generations (bounded mode) |
| `agents_max` | 24 | 1-96 | launches per run (0 = unlimited, `until_done` only) |
| `attempt_seconds` | 3600 | 120-14400 | one attempt's time limit (holds in every mode) |
| `wall_seconds` | 21600 | 300-172800 | the run's time limit (0 = unlimited, `until_done` only) |
| `interval_seconds` | 900 | 60-86400 | pause between perpetual generations |
| `novelty_limit` | 2 | 1-8 | attempts without progress before an `until_done` node is split |
| `saturation` | 0 | 0-16 | perpetual: generations in a row with no new item before the lane stops |
| `strategies` | fresh, feedback, other_node, other_engine | | the regeneration rotation (`stronger_model` is refused: nothing provides a model ladder) |
| `checks`, `final`, `hidden` | | | the operator's commands: per statement, at the end, and hidden at the end (their output never reaches a prompt or the record) |
| `until_done`, `self_split`, `designer`, `perpetual`, `syntax`, `require_change` | | | switches |

**Bounded mode**: the counts are caps; a node that exhausts them `fails`.
**`until_done`**: a node keeps regenerating while it has an untried strategy fingerprint or made
progress on its last attempt; after `novelty_limit` attempts without progress it is split; when nothing
novel is left at the smallest subdivision it ends **`stuck`**, never `failed`. A stuck run can be
resumed after the operator changes something (the statement, the checks, the catalogue of nodes and
engines); a resume starts a new rotation. Explicit `agents_max` or `wall_seconds` still act as safety
caps.

Every attempt's outcome is classified (`policy.FAILURE_CLASSES`): `INFRASTRUCTURE` and `REFUSAL` (the
placement's fault: move to another node or engine), `SYNTAX`, `CHECK_FAILURE`, `CLAIM_MISMATCH`,
`NO_OUTPUT` (the statement's fault: feedback first), `HIDDEN_FAILURE` (never fed back), `TIMEOUT`,
`CONTEXT_EXHAUSTED` (a handoff), `CONFLICT` (the project changed during promotion: one retry on the same
placement), `CANCELLED`, `FETCH_FAILURE`, `UNKNOWN`.

## Progress, and the unproductive-split rule

Progress is measured by code only (`policy.progress_metrics`, `is_progress`): a **new named file**, **more
passing checks**, or, on the kernel lane, **more accepted units** than the node's best so far. A
checkpoint's own "done" list is recorded but never counts: it is the worker's claim.

**Unproductive splits end** (`policy.unproductive_split`). A split child carries `parent_progress`, the
parent's best evidence at the moment of the split. A child that never beats it may regenerate, but it
is never split again, and its terminal reason says so ("this split made no progress over its parent
(units 2 vs 2, checks 0 vs 0), so it is not split again"). The rule exists because of a measured
failure, described next.

## The kernel lane: spec sheets with small local models

Small local models (0.5B to 4B parameters) cannot drive a CLI coding agent: with the agent harness that
was tried, the tool schemas alone exceeded its 7168-token input budget, and a 1B model answered by
echoing a schema. So a run with `engine: 'local'` takes **one spec sheet** (see
[docs/reference/SPEC-SHEETS.md](../../docs/reference/SPEC-SHEETS.md)) as its only statement, and every
attempt is a **kernel build**: the sheet is compiled into one fresh-context ask per unit, every answer
is checked by the sandboxed JavaScript checker against the sheet's examples, and the file is assembled
from passing units only. A later build keeps the units an earlier build accepted.

When a build stalls, the planner is a **typed** kernel ask: the model must answer 2 or 3 objects
`{name, args, contract, examples}`, and the type becomes Ollama's JSON-schema `format`, so decoding
cannot leave that shape. The kernel then checks that every name is a new identifier and every example
calls its own unit; code checks the rest (`kernel_lane.split_sheet`) and writes one refined sheet whose
stalled unit now calls the new sub-units and keeps its own examples as the integration check.

What runs without the original host: the coordinator, checkouts, compilation, the build process
management, run-folder parsing, verdicts and promotion. What does not: the model calls. A build reaches
its model through the kernel's `ollama:MODEL@NODE` applicator in `symblic/providers`, which on the
original host went through that host's admission-checked launcher. Elsewhere a build ends with an
`INFRASTRUCTURE` failure (recorded with its log) until a provider route to your Ollama nodes exists.
Details: [docs/reference/LOCAL-AUTOGEN.md](../../docs/reference/LOCAL-AUTOGEN.md).

## What was measured

All of this ran on one private deployment on 2026-10-10 and 2026-10-11 (one coordinating machine and a
handful of small CPU-only nodes). The run records are not part of this repository.

**Software checks.** The suites in `tests/autogen/` (fakes only) and the host-engine journeys in
`tests/integration/test_symblicos_autogen_hub_lane*.py` (fake hub). They show that the rules do what
they say on fixed inputs; they say nothing about how often agents or models succeed.

**CLI-agent runs (the agent-task lane, through the original host's runner).**
- The first real run: three statements, two candidates each on one node with a cloud-backed CLI coding
  agent; every statement was accepted and promoted, 6 of 10 allowed launches were used, 9 minutes, and
  the final command passed in the project folder.
- Two `until_done` demonstrations (a six-file calculator and a perpetual research lane) stalled when the
  host process restarted: a review-gated task whose watcher died was never observed again. That led to
  the coordinator driving such a task itself (`advance` of a gated, still-running step) and to
  re-attaching coordinators after a restart. A later perpetual run ran three generations (9 distinct
  index rows); across the perpetual lanes, 15 distinct DOIs were indexed and none was repeated.

**Small local models on the kernel lane (the part that did not work).** Three autogen runs used a 3B
coder model (qwen2.5-coder:3b) on a 4-unit sheet (`SHAPES/COLORS`, `cellsOf`, `emptyBoard`, `fits`):

| Run | Code | What happened | End |
|---|---|---|---|
| 1 | free-text planner | three builds stopped at `cellsOf` (1 of 4 units); the planner's answer restated the stalled unit or its examples; re-plans on other nodes found no model there or answered with one section instead of two or three | stuck after 10 attempts |
| 2 | typed planner, model-aware placement | the typed split was accepted by code for the first time (`cellsOf` → `getPieceCells`, `handleO`); the child stalled on `getPieceCells`, was split again (8 units), and again (13 units); every level accepted only the one unit its parent already had | cancelled at depth 4 after 17 launches |
| 3 | plus the unproductive-split rule | split accepted; the child wrote one more unit (2, beating its parent's 1) and stalled; one more split was allowed; the grandchild stayed at 2 units through four attempts | stuck at depth 2 by the new rule |

So the typed split planner did get usable splits out of a 3B model, but recursion never lifted the model
over a unit it could not write. In the same session, changes to the sheet's wording made the difference
instead, in ordinary kernel builds without autogen: numbered-step contracts raised the same 3B model from
1 to 3 of the 4 units, and with the units each unit uses shown as signatures it wrote all four from their
contracts on the first try. For models this small, wording and examples moved the result; decomposition
did not.

**Not measured:** whether decomposition improves small models in general; whether candidates ranked by
test agreement would beat "first accepted" (they are not ranked); how any of this compares with the
results of the papers below.

## Ideas it borrows, and where they live

Autogen implements small, named mechanisms inspired by these works. It does not reproduce them, and no
result of theirs carries over to this code.

| Work | Mechanism here | Where |
|---|---|---|
| Parsel — Zelikman, Huang, Poesia, Goodman, Haber (2022). *Parsel: Algorithmic Reasoning with Language Models by Composing Decompositions.* [arXiv:2212.10561](https://arxiv.org/abs/2212.10561), [code](https://github.com/ezelikman/parsel) | hierarchical splits with explicit per-line interfaces; worker self-splits | `split_prompt`, `parse_split`, `_planner_verdict` |
| ANPL — Huang, Nan, Hu, Jin, Peng, Wen, Zhang, Du, Guo, Pu, Chen (2023). *ANPL: Towards Natural Programming with Interactive Decomposition.* [arXiv:2305.18498](https://arxiv.org/abs/2305.18498), [code](https://github.com/IPRC-DIP/ANPL) | the same split mechanism; the typed unit decomposition of a stalled spec-sheet unit | `split_prompt`, `kernel_lane.split_program`, `split_sheet` |
| CodePlan — Bairi, Sonwane, Kanade, D C, Iyer, Parthasarathy, Rajamani, Ashok, Shet (2023). *CodePlan: Repository-level Coding using LLMs and Planning.* [arXiv:2309.12499](https://arxiv.org/abs/2309.12499) | children run in order before later statements; a split parent is judged only after its children | `_current`, `_settle`, `_parent_verdict` |
| CodeT — Chen, Zhang, Nguyen, Zan, Lin, Lou, Chen (2022). *CodeT: Code Generation with Generated Tests.* [arXiv:2207.10397](https://arxiv.org/abs/2207.10397), [code](https://github.com/microsoft/CodeT) | an independently generated test gates candidates | `designer_prompt`, `_designer_verdict`, `_designed_check` |
| AgentCoder — Huang, Zhang, Luck, Bu, Qing, Cui (2023). *AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation.* [arXiv:2312.13010](https://arxiv.org/abs/2312.13010), [code](https://github.com/huangd1999/AgentCoder) | a separate test-designer agent that never sees the candidates | same |
| AFlow — Zhang, Xiang, Yu, Teng, Chen, Chen, Zhuge, Cheng, Hong, Wang, Zheng, Liu, Luo, Wu (2024). *AFlow: Automating Agentic Workflow Generation.* [arXiv:2410.10762](https://arxiv.org/abs/2410.10762), [code](https://github.com/FoundationAgents/AFlow) | a strategy rotation chosen by evidence, with repeated search states refused (a fixed rule here, not a searched workflow) | `next_strategy`, `_novel_strategy`, `fingerprint` |
| Agent Contracts — Ye, Tan (2026). *Agent Contracts: A Formal Framework for Resource-Bounded Autonomous AI Systems.* [arXiv:2601.08815](https://arxiv.org/abs/2601.08815) | checks per statement and per subtree, budgets per run | `plan_checks`, `_finish`, `normalize`, `_extend_budget` |
| Recursive Models for Long-Horizon Reasoning — Yang, Srebro, Li (2026). [arXiv:2603.02112](https://arxiv.org/abs/2603.02112) | fresh contexts with external checkpoints; splitting what is left when handoffs stall | `worker_suffix`, `checkpoint_valid`, `handoff_prompt`, `split_remaining_prompt` |

Tools it relies on: [git worktree](https://git-scm.com/docs/git-worktree) and
[git merge-file](https://git-scm.com/docs/git-merge-file) (checkouts and the 3-way apply);
[Landlock](https://docs.kernel.org/userspace-api/landlock.html) through `symblic/sandbox/landlock.py`
(model-written test scripts); [systemd-run](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html)
transient scopes (optional resource limits); [Ollama](https://github.com/ollama/ollama) and its
[structured outputs](https://ollama.com/blog/structured-outputs) (the typed planner's `format`). The model
in the measurements is Qwen2.5-Coder ([Hui et al., 2024, arXiv:2409.12186](https://arxiv.org/abs/2409.12186);
[Ollama page](https://ollama.com/library/qwen2.5-coder)). A longer design record, written while the code
was built, is in [docs/reference/AUTOGEN.md](../../docs/reference/AUTOGEN.md) and
[docs/reference/RECURSION.md](../../docs/reference/RECURSION.md).

## Safety notes and known limits

- Model-written test scripts run through the Landlock launcher: only the throwaway copy and a scratch
  home are writable, `$HOME` is hidden, TCP is blocked, the environment is built from scratch, and a
  missing Landlock is a visible refusal (exit 125), never an unsandboxed run. Linux only. UDP is not
  blocked, and the unsafe-command screen in `policy.py` is advisory, not a sandbox.
- The operator's own check commands run unsandboxed (they are the operator's), at low priority, with a
  scrubbed environment and a timeout that kills the whole process group.
- A remote handoff is refused: a successor cannot be started in another machine's checkout.
- Checkouts and branches (`<project>.autogen/`, `autogen/*`) are never pruned: they are evidence.
- Designed tests and kernel builds run in transient systemd user scopes under the slice `symblic.slice`
  when a user bus is available (`SYMBLIC_SCOPE_SLICE` changes the slice, `SYMBLIC_SCOPE=0` turns the
  scopes off). `SYMBLIC_EXECUTION_HOST` fences execution to one machine; it is unset by default.

## Tests

```sh
DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .          # standalone, fakes only
DASH_TEST=1 python3 -m unittest discover -s tests/integration -t .      # includes the host-engine journeys (fake hub)
```

`tests/autogen/`: `test_policy.py` (the pure rules), `test_coordinator.py` (journeys over
`FakeTaskRunner`), `test_runner.py`, `test_kernel_lane.py` (a fake kernel; plus the real process
mechanics against a stand-in for `tools/symblic`, the real git checkout and apply, and the sandboxed
JavaScript check when node is available), `test_git_checkouts.py`, `test_workspaces.py`,
`test_sandboxed_checks.py` (the real Landlock launcher; skipped where it is unavailable) and
`test_task_cli_sheets.py` (the command line's sheet start; skipped when it cannot load). No test calls a
model, starts a real build or contacts a network; `kernel_lane.run` refuses the real `tools/symblic`
under `DASH_TEST=1`.
