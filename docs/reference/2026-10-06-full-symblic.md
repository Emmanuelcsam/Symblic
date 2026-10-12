# Full Symblic record — 6 October 2026

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

This is the current consolidated guide to Symblic, the revamped Symblic Terminal, the hosted SymblicOS workspace, and Claude Cloud CLI. It explains how to use them, how their contracts fit together, what the retained experiments measured, and how to distinguish an accepted result from a running agent or an unverified claim.

**Record date:** 2026-10-06. **Native language:** Symblic 2.5, canonical representation version 3. **Scope:** the source and public documentation in the host-checkout checkout, plus the explicitly identified installed integrations. This book supersedes older master books for current user journeys and runtime behavior; their historical observations remain historical evidence. It does not incorporate private transcripts, credentials, raw research stores, or personal model histories.

The requested documentation ingestion preceded implementation. The collaborating reviewers collectively read the 125 public matching documents identified for that initial pass. Later changes added documentation and altered existing contracts. The catalogue at the end records the actual Markdown inventory at this book's construction rather than treating an earlier document count as a permanent fact.

**Verification status:** obtained regression, deployment and live-journey results are listed in [Chapter 21](#21-verification-record-and-live-sign-off), with their scope. The final two-line discrete Qwen trial completed natively, with distinct fresh teams in one workspace and confirmed cleanup. The final README was inspected and applied through the normal Work route, and independent tests passed against the resulting source project. These are scoped results for the recorded workflows, not a guarantee that an arbitrary requested program will be correct. Reading this book, installing an executable, or loading a page alone does not establish that a provider is authenticated or that an arbitrary requested program works.

## Contents

1. [The practical starting point](#1-the-practical-starting-point)
2. [Four ways to give an instruction](#2-four-ways-to-give-an-instruction)
3. [The terminal workspace and its controls](#3-the-terminal-workspace-and-its-controls)
4. [Fresh contexts, explicit dependencies and persistent files](#4-fresh-contexts-explicit-dependencies-and-persistent-files)
5. [Agents, three Qwen seats and execution machines](#5-agents-three-qwen-seats-and-execution-machines)
6. [Projects, files, normal shells and remote checkouts](#6-projects-files-normal-shells-and-remote-checkouts)
7. [Durable task records, recovery and cancellation](#7-durable-task-records-recovery-and-cancellation)
8. [The bounded OS command language](#8-the-bounded-os-command-language)
9. [Native Symblic language and exact execution](#9-native-symblic-language-and-exact-execution)
10. [Model asks, checks, context and routing](#10-model-asks-checks-context-and-routing)
11. [Checked English and generated displays](#11-checked-english-and-generated-displays)
12. [Workcards, steps, task cards and spec sheets](#12-workcards-steps-task-cards-and-spec-sheets)
13. [Proofs, finite mathematics and research adapters](#13-proofs-finite-mathematics-and-research-adapters)
14. [Graphs, delegation, effects, memory and supervisors](#14-graphs-delegation-effects-memory-and-supervisors)
15. [A cloud-agent CLI (removed)](#15-claude-cloud-as-a-practical-cli)
16. [Local source tools and pinned upstream repositories](#16-local-source-tools-and-pinned-upstream-repositories)
17. [Command reference](#17-command-reference)
18. [HTTP and source architecture reference](#18-http-and-source-architecture-reference)
19. [How Symblic developed and what it has built](#19-how-symblic-developed-and-what-it-has-built)
20. [Practical recipes and diagnosis](#20-practical-recipes-and-diagnosis)
21. [Verification record and live sign-off](#21-verification-record-and-live-sign-off)
22. [Operational boundaries and future work](#22-operational-boundaries-and-future-work)
23. [Complete documentation catalogue](#23-complete-documentation-catalogue)

## 1. The practical starting point

Open **/symblic-terminal** (also available as **/symblic-terminal.html**). Write the outcome you want, select the agent and machine, choose a working folder, and run the instruction. An ordinary request can be direct English:

~~~text
Create snake.py in this folder. Make a small retro Snake game with a black-and-white screen. Use arrow keys to move, show the score, and use R to restart. Keep movement and collision logic separate from drawing. Add tests for wall collisions, food collection, and restarting. Run the tests and tell me how to launch the game.
~~~

That is an agent task. It launches the selected existing tool-capable agent through the admitted Agents hub. The agent can inspect its workspace, create source files, run the tools its native environment permits, and report the result. The terminal retains the task identity and a link to the agent's persistent terminal. Its task card does not convert the words “game created” into proof that a game exists or runs: the source files, actual test output, and user-visible behavior supply that evidence.

For an empty project, use **New project** in the folder controls. A valid project name creates a managed directory with a Git baseline, making it suitable for the existing remote-checkout workflow. Reusing the same managed name returns the same completed workspace; an unrelated existing directory is never silently initialized or overwritten. This is useful when the task is “make a game” and there is no repository yet. For an existing project, choose its folder directly.

**Model** and **Effort** are visible in the main composer. Open extra controls when a task needs planner, builder and reviewer role settings, council configuration, an explicit context note, or the full native agent workspace. The terminal's expandable panels provide the normal Linux shell, full file browser, Agents, native Symblic editor, the fleet runner, the autonomous agents and cluster controls. The merger is practical access to their real existing interfaces and lifecycle contracts, not a claim that all those systems have one interchangeable execution API.

The same direct task composer also appears above the existing checked-English editor on **/automation-studio/symblic.html#english**. That placement addresses the original usability goal: ordinary English should be able to ask a chosen agent to do useful work. The checked grammar remains immediately available for tasks where explicit typed answers and predicates are valuable.

Use **One instruction** for one cohesive instruction, **Fresh task per line** for a sequence with a new agent session on each nonblank line, and **Three Qwen · plan / build / review** for an enforced plan → build → review loop with Qwen in all three seats. These are the mode labels shown in the composer; this book also calls the last choice Three Qwen. In Three Qwen mode, **New team for each line** optionally starts a separate fresh team for each nonblank instruction line. These choices describe different execution structures. None is a universal quality ranking. A small well-specified task may need only one model; a larger construction may benefit from criticism and independent checks; an exact calculation should use the deterministic kernel when the needed operation is already supported.

## 2. Four ways to give an instruction

The word “English” previously covered different mechanisms, which made capability expectations confusing. The current interfaces expose four distinct lanes:

| Lane | What enters | What performs the work | What success establishes |
| --- | --- | --- | --- |
| Direct agent task | Arbitrary operator instruction and selected options | The existing Agents hub and chosen native agent | An agent session was admitted; later completion evidence or operator acknowledgement records that its turn finished |
| Fresh-line task sequence | Up to 64 nonblank instruction lines | A separate new agent session for each line, sharing the selected workspace | Each completed line has its own lifecycle; the assembled objective still needs appropriate checks |
| Checked English | The documented atomic English grammar or supported construction vocabulary | A deterministic compiler followed by native Symblic execution and checks | Accepted values or code satisfy the encoded checks under the recorded runtime |
| Bounded OS command | An exact supported file/system command such as Read "note.txt" | Named deterministic filesystem/process adapters | The receipt records the actual supported operation and its verification |

Native Symblic source is another authoring form for the checked execution lane. The normal shell is also present: commands, pipes, interactive applications and shell scripts belong in **Shell**, using its persistent tmux session. A shell's flexibility is not implemented by passing every sentence from the bounded OS parser to an unrestricted shell.

Choose the lane by what you need. “Implement a Snake game” belongs in the direct agent composer. “Ask for an integer between one and nine, then accept it only if its square is nine” is a checked statement. “Append this exact text to this exact sandbox file” can be a deterministic OS command. “Run this project's test runner and inspect its output interactively” fits the normal shell or an authorized agent.

A new agent conversation reduces accumulated conversational context. It does not remove the agent's normal repository instructions, its explicitly supplied context, or the files in its workspace. Conversely, a sterile native ask receives only the selected values and capsule material allowed by its native policy; it does not automatically receive filesystem tools. A typed answer containing Python code is still an answer until a separate authorized mechanism writes, checks or runs it.

## 3. The terminal workspace and its controls

The standalone terminal consists of symblic-terminal.html, symblic-terminal.css, symblic-terminal.js and the reusable symblic-task-composer.js. The English page mounts the shared composer rather than maintaining a second hardcoded agent picker. This prevents the terminal and the English page from drifting into separate lists of “supported agents.”

The agent catalogue comes from the existing Agents backend. The composer exposes the selected engine, model, effort, machine and working directory, plus advanced native options where applicable. Three-agent-pipeline seats are independent choices. Council and squad structures retain their native configuration. The full **Agents & teams** panel remains the place for the complete engine settings, interactive messages, work review and applying a branch.

The main action is **Run instruction**. Ctrl/Cmd+Enter submits from the composer. A multiline default-mode prompt is one task; choosing **Fresh task per line** makes nonblank lines separate tasks in sequence. Three Qwen offers its own **New team for each line** checkbox: off means one complete team task; on means one fresh discrete team per nonblank line. The exact original multiline instruction and this setting are retained in the durable request identity. The browser keeps the exact pending submission identity when a response is lost. Reconnection checks the server's durable record instead of blindly launching a second copy. Resetting an unsent or uncertain browser form is not cancellation of an operation the server already received.

Task cards show the instruction, state, linked agent, output when available, and lifecycle controls. **Finish step & Next** is an explicit acknowledgement for placements without a trustworthy automatic turn-completion adapter. It stops the owned current agent before allowing the next fresh session to start. **Finish task** is the corresponding manual acknowledgement on the final step. **Resume / recover coordinator** recovers the coordinator or an unambiguously identified owned launch. **Cancel task** acts on that task and its owned agent; it is not a blanket cancellation command for unrelated agents or detached external services.

The card also shows the actual **Execution workspace** and its machine. If that checkout differs from the selected source folder, the card lists both and explains that changes remain in the execution workspace until reviewed and applied through **Agents → Work**. This distinction matters for remote agents and native worktrees: task completion does not automatically copy files back into the original project.

Panels are lazy. Opening **Shell** creates its frame; collapsing and reopening it retains the same frame and tmux session rather than opening another terminal. Its initial machine follows the selected machine; once open, the shell's own machine/session controls govern that persistent shell. Each panel also offers **Open full page**, so a compact embedded workspace does not remove advanced controls.

| Panel | Native surface | Typical use |
| --- | --- | --- |
| Shell | /terminal | Interactive Linux commands, pipes, program execution, reconnecting to tmux |
| Files | /files | Browse, edit, upload, download and inspect files on the dashboard host; remote work uses its shown execution workspace and Work review |
| Agents & teams | the agent hub | Full engine registry, native sessions, teams, messages, work review |
| Symblic editor | /automation-studio/symblic.html | Source, checked English, construction, graphs, runs and evidence |
| the fleet runner | the fleet runner page | Existing plans, capability execution and admitted fleet work |
| the autonomous agents | the autonomous-agent page | The operator's autonomous workstation and its model router |
| Cluster | /cluster | Node inventory, placement, reservations and power controls |
| OS commands | The bounded SymblicOS adapter | Exact sandbox file commands and execution receipts |

Output is inserted as text. Browser tests replace WebSocket before loading the page and intercept APIs, so testing the interface does not accidentally open a real shell. Desktop/light and phone/dark behavior, retained collapsible panels, output bounds and horizontal overflow are part of the acceptance work. Current UI details and their separate verification record are in [TERMINAL.md](TERMINAL.md).

## 4. Fresh contexts, explicit dependencies and persistent files

The central design is to make each unit of work understandable from a small declared input. Large tasks become explicit stages: plan a component, propose an implementation, criticize it, check the result, and pass only what the next stage needs. A reset helps only if the next instruction still contains the information needed to act correctly.

Fresh-line agent mode starts a new session for each nonblank line. It sends the line, the explicit context note, an instruction to follow the repository's working rules, and the standard task wrapper. It does not append the previous conversation. The same workspace remains available, so later lines can inspect files created earlier. That persistence is intentional: resetting conversational history while deleting the program would defeat incremental construction.

The same file-sharing rule applies to Three Qwen with **New team for each line** enabled. Each line gets a new planner, a fresh implementer conversation on every build attempt, and a fresh reviewer. An accepted native stage receipt can advance the sequence, but the prior team must first be positively stopped. A failed or unknown stage blocks automatic continuation. General three-agent-pipeline conversations continue to use explicit completion review.

For example:

~~~text
Create a pure Python game_state.py module for a grid Snake game. Include movement, food placement, collision detection and restart behavior. Keep drawing out of this file.
Write tests/test_game_state.py covering movement, growth, self-collision, wall-collision and restart. Run the tests and fix failures in the module.
Create snake.py as a minimal graphical front end using game_state.py. Document installation and the exact launch command in README.md.
Review the complete program against those requirements. Run the tests again and report any untested display behavior.
~~~

Each line is a new agent session in the same project. This is an orchestration recipe, not an executable formal specification of Snake. The second agent can still misunderstand a requirement, and a test suite can omit a defect. The final line should therefore inspect the assembled program, not merely trust that each predecessor declared success.

Native Symblic uses a more precise dependency mechanism. An ask can select named values with **from**, and policies can set context to none or use other documented capsule selection rules. Required values, the instruction, system text, schema and repair material must fit the configured character budget. A required dependency is never silently truncated to make a request fit. Optional material may be omitted with its omission recorded.

The compact capsule option removes selected annotation overhead while preserving actual selected values and provenance in the retained manifest. It is not a compression scheme that rewrites an accepted value or hides a different prompt behind the same cache identity. Context limits are measured in the units the implementation records—usually Unicode characters—not assumed to be tokens, GPU bytes or a provider's real context capacity.

Repository instructions and selected source can still be large or ambiguous. The new symblic-context command helps gather a bounded source map from exact named files. It reports symbols, selected literal matches, hashes and omissions. It does not crawl personal histories, load a model, or infer that static call edges prove runtime behavior. When a task needs more information, enlarge its explicit source set or split it more carefully.

## 5. Agents, three Qwen seats and execution machines

The user selects the agent through the same registry used by Agents. Available model names and readiness are observations from that registry and its caches, not a fixed list of four local models. An exact saved selection may remain visible when it is absent from current cached inventory; the interface marks that selection as unverified rather than silently replacing it.

On first load, an online remote machine with no probe result triggers one metadata refresh through the existing catalogue route. The composer watches cached updates every five seconds for at most one minute, retaining the instruction and saved engine/model/machine/role choices. An unprobed machine is labeled **availability unknown**. Persistent unknown state does not trigger an automatic refresh loop; **Refresh agents** remains available for another explicit check. Discovery performs no model generation, and a refreshed catalogue still does not replace the mandatory fresh selected-node admission probe at launch.

The general three-agent pipeline has a **mastermind** seat that plans, an **implementer** seat that edits, and an optional **AI review** seat that critiques. **Three Qwen** selects the new native discrete controller, with all three seats explicitly configured as Ollama and each exact selected Qwen model retained. This controller enforces the sequence rather than asking an unconstrained planner to remember to delegate. It requires the **Let the agent run its tools automatically** checkbox under **Folder, context and execution**. This is the native Auto setting; a non-automatic request is refused before work starts. Each seat is a distinct role, but three roles using one model are not three statistically independent sources of truth.

The discrete workflow is:

1. A fresh read-only planner receives the original task and returns a short plan. The planner has no file or shell tools.
2. A fresh the CLI agent implementer conversation receives the task, plan and any previous review issues. The discrete local builder exposes read, save, append and shell tools; the CLI agent also supplies its native complete tool. This lane omits the separate patch tool after real small-model trials repeatedly produced invalid patch syntax. Files can still be changed through save, append or shell. Ordinary local coding retains its existing five-tool selection, including patch.
3. The controller records a Git checkpoint, gathers the cumulative candidate diff and gives a fresh read-only reviewer the task, bounded implementation report and diff.
4. Strict review JSON accepts the candidate or returns explicit issues for another fresh build/review round. At most three build/review rounds run; the bound is deterministic.

| Discrete control | Current bound or behavior |
| --- | --- |
| Prepared task | At most 20,000 native JavaScript UTF-16 code units, including all working defaults, repository context and explicitly attached/upload context |
| Seats | Three explicit Ollama seats; the terminal Qwen preset additionally requires selected Qwen model names |
| Automatic tools | Auto is required; discrete mode does not silently override a false setting |
| Planner output | 256 generated tokens; fresh read-only planner |
| Reviewer output | 512 generated tokens; fresh read-only reviewer each round |
| Planner/reviewer context | 8,192 requested tokens, with thinking disabled for this discrete path |
| Plan retained for later stages | At most 4,000 characters |
| Implementer report | Bounded retained report; review capsule includes at most 2,000 report characters |
| Implementer model calls | At most six provider generation dispatches per discrete build invocation, including auxiliary calls |
| Implementer elapsed check | After 600 seconds from guard startup, the next generation yields; an active model/tool operation is allowed to finish |
| Cumulative review diff | At most 20,000 characters; total review capsule has an explicit approximately 26,000-character budget |
| Machine-derived change summary | At most 3,000 characters within remaining evidence space; exact per-file line counts and zero-context patch with omissions labelled |
| Retries | At most three build/review rounds; implementer conversation identity starts empty each round |
| Review decision | Exact structured JSON; duplicate keys, malformed fields and acceptance with issues are refused |

These character and token limits describe different units. They are not interchangeable promises that every possible 20,000-unit task fits every model tokenizer. The task limit follows native JavaScript UTF-16 units; an astral character such as an emoji occupies two units. The hub validates the entire expanded task, not just the initial instruction, then sends exactly that frozen prompt file. Remote checking precedes reservation and provisioning; local checking precedes admission and spawn. Oversized prepared input is refused rather than silently clipping the original objective. Optional source context should be deliberately selected and kept small.

The review path verifies Git evidence instead of accepting an implementer's prose as the diff. External Git diff helpers and text conversion are disabled. A missing or corrupt baseline becomes unknown; a binary or incomplete/truncated diff cannot be accepted. Acceptance also requires unchanged reviewed HEAD and no unreviewed source changes within the checkpoint scope, checking HEAD around the final status read. The status check uses the same exclusions as the checkpoint: generated Python cache artifacts are excluded, while an untracked source file added during review prevents acceptance. Operator edits observed during review are preserved and prevent acceptance. Existing operator changes can be carried in the initial baseline according to the normal hub checkout contract.

The reviewer also receives a machine-derived JSON summary of per-file added and removed line counts and a zero-context patch from the same immutable base and HEAD. The summary records omissions and uses remaining evidence space, preserving the full patch allowance. Current checkpoint evidence precedes the chronological process tail. The prompt distinguishes added/removed lines from unchanged diff context, and old reads or full-file saves from the current source. This responds to a real reviewer misreading of historical output. It improves the representation without establishing that the reviewer will always reason correctly.

A completed receipt means **the native reviewer accepted this candidate under those controls**. The implementer's statement that tests passed remains reported evidence until an independent runner executes the tests against the retained source. Neither model agreement nor the completed task label proves the full user objective. This distinction is the reason to request concrete tests and inspect or independently run the resulting program.

Each external stage has a durable intent before work or a model call. Stage outcomes are flushed to the session file and its directory. A crash between intent and result becomes unknown and is never automatically replayed. Completed resume reads the retained result without new model calls; failed or unknown executions require inspection instead of silently repeating side effects. Native SIGINT, SIGTERM and SIGHUP handlers persist uncertainty, interrupt and reap an owned detached implementer, and forbid later stages. Scope-level shutdown supplies a separate operator-controlled termination check described below.

Remote local coding and the remote three-agent pipeline now use the existing agent-hub launch path. They do not open an alternate SSH executor to bypass power admission. A selected node must be registered, respond to the fresh admission probe, have the needed local coding/three-agent-pipeline tooling, and expose the requested model inventory. Cached offline, missing-runtime or low-memory picker entries do not veto this required fresh probe; conversely, a stale ready entry cannot authorize launch. Genuine prelaunch metadata, runtime or model-capacity refusals are marked as refused, rather than implying a possibly dispatched task. A CLI seat additionally needs its own installed and authenticated CLI on that node. Browser seats use their supported browser placement and are not silently replaced by another provider.

The installed CLI-agent provider interface uses **local/MODEL** for an OpenAI-compatible local service, as documented in that agent's official provider reference. The hub now supplies the selected machine's loopback Ollama **/v1** endpoint explicitly in both supported base-URL environment names and uses a non-secret local placeholder key. The native three-agent pipeline's Ollama implementer uses the same compatible provider form and its configured Ollama endpoint. This repairs executable compatibility; the terminal still admits the exact selected model and machine before launch. It does not redirect an unknown provider to a paid account.

The shared **the local CLI-agent wrapper** adapter also aligns the actual Ollama context with admission. Ollama's OpenAI-compatible endpoint does not accept a context-size parameter, so the adapter derives a managed model alias with **num_ctx=8192**, following the [official local-context configuration](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size). The original selected model and its digest remain the task's identity. The alias uses the same immutable weight blobs, template, system prompt, other parameters and model metadata; only the requested context setting changes. The adapter verifies inheritance and the alias digest before inference. Ollama can emit parameter keys in different orders, so the fingerprint compares top-level parameter groups canonically while preserving repeated values' order and exact quoted template/license content. Version 1 ownership receipts can migrate to version 2 only after revalidating the same immutable source, owned alias and context; this never repeats creation or overwrites a model. Internal aliases are filtered from model pickers and cannot recursively become a new user selection.

A private receipt records the selected digest, alias, context and metadata fingerprint before creation. An unrelated preexisting alias, a changed source digest, an incompatible alias or a missing/ambiguous receipt is refused without overwriting another model. A lost creation acknowledgement can be reconciled against the retained intent and exact resulting metadata; absence does not trigger an automatic second creation. Model aliases reuse the installed weights; this is context configuration, not training or a claim of a stronger underlying model.

The adapter launches the installed isolated the CLI agent Python through a process-local guard, with a short system prompt unless one was explicitly supplied. It captures the initial operator instruction at the chat entry before session or turn hooks, then pins complete operator messages during preparation, verifies earlier operator text survives later turns, and checks the final request after generation hooks. Native tool schemas count toward the final estimated input budget. The outgoing provider must be the verified alias on the admitted loopback endpoint; a configuration change cannot silently route the task to a personal cloud provider. Automatic display-name generation is disabled because the hub already assigned a stable session identity.

The actual outgoing implementation response is bounded to 1,024 tokens, with a 7,168-token estimated input allowance inside the 8,192 context. The estimate uses the installed client's tokenizer; the server remains authoritative and may refuse a request. If complete operator instructions cannot fit, the adapter reports a refusal and asks for a smaller explicit task instead of silently deleting or abbreviating the objective. Ordinary local coding retains native reduction of tool-result context while pinning the operator request. The discrete build checks the complete log before native reduction and uses a fresh-context handoff when that log exceeds its bound; the provider boundary separately counts the actual serialized message and tool-schema payload.

Discrete builds additionally use an invocation-wide generation budget: six actual provider dispatches, with a 600-second elapsed check before the next dispatch. This clock is not a hard wall-time timeout. It never interrupts an active generation or tool action; completed edits and tool results remain available when the next call yields. All generation calls count, including auxiliary hooks, and neither another queued prompt nor later environment changes reset the budget. A failed or uncertain provider dispatch also consumes its attempt. Ordinary local coding and the general three-agent pipeline do not acquire this optional budget automatically.

The native complete tool can finish after the last allowed response, including a response that crosses the elapsed limit. Completion does not require another model call. Therefore call/time admission happens at the actual provider boundary, while preparation continues to validate exact identity and the full context before native reduction. A subsequent generation still yields when the budget is exhausted. The installed-client checks cover both completion boundaries explicitly.

For a budget-enabled discrete build, later context pressure also produces a partial handoff after at least one acknowledged provider dispatch. The exact endpoint, alias, original operator instruction and initial system instructions must validate first. Reaching six calls or the elapsed limit then yields before a later context-size error; a still-growing message/tool payload can also yield while calls remain. The next critic and build receive fresh contexts through the existing bounded rounds. An initially oversized request remains a refusal, even after long startup or an unacknowledged failed dispatch, and ordinary unbudgeted overflow behavior stays unchanged. The guard checks the complete discrete log before native preparation and again at the native reducer after context enrichment. It validates the admitted local model and client endpoint before deciding a pre-reduction handoff. The final provider boundary separately catches actual message/tool-schema overflow. This revision adds no instruction shortening or rewriting.

The guard reports a distinct partial handoff using exit 75 and the exact stderr marker **SYMBLIC_BUILD_BUDGET_EXHAUSTED**. The discrete controller recognizes **YIELDED** only when both match, checkpoints the candidate and sends a fresh critic the partial status plus bounded actual tool-output evidence. That evidence is untrusted execution output, not proof that the objective passed. A critic's acceptance of a yielded round cannot finish the team: another fresh build must finish within its budget. When the candidate appears correct and the reported checks pass, the critic can request only fresh verification and completion without inventing a source defect. Three exhausted build/review rounds terminate visibly with the files preserved. Other exit-75 errors do not become a successful or yielded result. The native task instructions tell the builder to use tools, examine failing expectations against the original request and avoid rewriting unchanged files.

Within budget-enabled discrete builds, a supported session-start hook replaces only the CLI agent's prose-only automatic continuation hook after tool initialization. A plan, diagnosis or promise to edit now receives an explicit reminder to perform unfinished operator-requested edits and checks using tools. Two such prose replies do not implicitly complete the build. The original objective remains exact and pinned; explicit completion still goes through the native complete tool and the separate critic. The six-call/elapsed budget remains the bound if prose continues. Ordinary the CLI agent behavior is unchanged, and an unexpected replacement or missing native hook refuses instead of silently guessing its semantics.

The discrete Ollama implementer's final wrapper now explicitly asks for a short truthful report of files changed and actual check outcomes, followed by the native **complete** tool with empty arguments **{}**. The report precedes that call; it does not replace it. A real run showed that the former shared instruction to finish with prose conflicted with this lane's explicit completion mechanism. Only this discrete Ollama wrapper changes; ordinary engines retain their final-report wording and the exact original operator instruction is preserved.

On process exit the adapter waits for its child, then verifies unloading through the selected node's **/api/ps**. SIGINT, SIGTERM and SIGHUP are forwarded, with a five-second escalation to SIGKILL for an unresponsive direct child; it remains in the existing owned process group. The hub can invoke **the local CLI-agent wrapper --unload-selected ORIGINAL_MODEL** at a proven idle or stopped boundary. That operation checks an existing owned alias and never creates one. An already absent model is idempotent success; missing state or a still-loaded alias is not reported as a successful unload. General human shell use and native team cancellation continue to rely on their scope/ownership controls for any additional descendants.

Model admission uses the chosen node's Ollama service memory limit and available memory. It does not reject a worker node task because the host lacks GPU room. The estimate includes the model weights, runtime overhead and an 8,192-token context allowance; it is an admission estimate, not a measurement of the eventual run. A model fitting physical RAM can still exceed its service cgroup. An already loaded local model or another active local coding reservation can prevent a new launch.

The source-only the CLI agent/the local CLI-agent wrapper/three-agent-pipeline runtimes and optional source tools were installed and discovered on node-a, node-b, node-d, node-f, node-h and node-i during this revision. All six passed runtime prerequisite checks and reported local/three-agent-pipeline tooling ready in the fresh catalogue. Model admission remains machine-specific: the verified Ollama service ceilings are 12 GiB on the initial node-a/b/f test nodes and node-d, 3 GiB on node-h, and 26 GiB on node-i. node-h can therefore refuse a 4B model with an 8,192-token context despite having the coding runtime installed. These dated observations do not promise identical models, login state or available capacity. Consult the live catalogue and the final verification appendix for each actual task.

Before a remote launch, the hub saves a row naming the node with an active reservation. Only then does it check the power fence. A refusal removes a pre-launch reservation without provisioning or launching work. Once a spawn may have occurred, a lost acknowledgement preserves the row and checkout as unknown. Resume and removal cannot treat an uninspectable remote terminal as safely absent.

Remote the CLI agent receives a stable unique conversation name containing its agent ID. Resume uses that name and the saved model, rather than choosing whichever conversation happens to be newest. The remote three-agent pipeline looks up its native session by both team name and workspace and validates the returned identifier. A matching name in another workspace cannot substitute for the task's session. The discrete three-agent pipeline uses a native name containing the unique agent ID, bounded to the native 32-character limit. Reusing a human-readable display name cannot cause adoption of an older completed receipt.

The native local/three-agent-pipeline process enters a separate scope in a systemd work slice on the selected node. New discrete teams use **symblic-agent-<eight-hex-agent-id>.scope**, with that derived identity saved before spawn. The scope collects detached implementer descendants, uses control-group termination and is collected after becoming inactive. Arbitrary supplied unit names or slices cannot substitute for this owned unit. The terminal socket remains the host's existing terminal socket. Closing a browser does not terminate its tmux session. Model unloading targets the selected node's own loopback Ollama endpoint; an unknown remote observation must not unload the host's model or declare remote work finished.

## 6. Projects, files, normal shells and remote checkouts

There are three distinct filesystem locations to understand:

1. The **agent working folder** is the project selected in the composer.
2. A **remote agent checkout** is the admitted branch checkout created on the selected machine.
3. The **bounded OS-command filesystem** is the separate SymblicOS user-files root shown in that panel.

Changing the agent working folder does not silently change the bounded OS adapter's root. Likewise, a remote branch is not automatically merged into the live dashboard checkout. Files and Work views let the operator inspect and apply changes using the existing workflow.

Managed projects live beneath the configured SymblicOS root's projects directory. New project names contain 1–64 lowercase letters, digits, hyphens or underscores and begin with a letter or digit. Creation uses an exclusive directory operation and a per-name lock. Git initialization disables inherited hooks, templates, global configuration and signing. The initial empty commit provides the baseline required by the remote checkout machinery.

The workspace receipt identifies the name, absolute working directory, baseline commit and readiness state. A repeat request returns an already completed managed project. A symlink, unrelated existing directory, malformed marker, missing Git directory or interrupted initialization is preserved and refused. A recovery operation should inspect that retained directory or use a different name; it should not overwrite unknown existing work.

The remote hub carries the selected branch to the node's bare mirror and creates its own checkout. Existing uncommitted work may be carried as an explicit baseline according to the established Agents contract. Work review compares the agent's changes against that baseline. The mirror and checkout mechanism is an existing operator workflow, distinct from Claude Cloud's much narrower allowlisted source snapshot.

Work → Apply merges the selected agent changes into their source project without creating an operator commit, and refuses the whole apply if files conflict. Its dashboard-restart notice is bound to the resolved identity of the actual serving repository. Applying a Python game or another project's file named server.py does not request a dashboard restart. Applying changed server code to the dashboard itself still reports that its process must be restarted to load the change.

The native three-agent pipeline can create a new **triad/** branch inside that remote checkout. The hub resolves the actual branch from an exact native session-name and cwd match, retaining it separately as **git.remote.sourceBranch**. The local **agents/** mirror branch and original baseline remain stable. Synchronization stages a fetch at a fresh temporary ref, checks baseline ancestry and prior fetched-tip ancestry, compare-and-swaps the retained tracking ref, and fast-forwards the local mirror. Divergent local work or rewritten native history is refused without a reset. Work review therefore includes actual native three-agent-pipeline commits instead of reading an unused original branch.

Remote commit verifies the native checked-out branch before adding or committing files. Commit and discard reject another active operator of the same node and checkout directory, even if the later team changed its branch name. Discard refuses unknown liveness. Workspace identity is the actual selected node and directory, not just a branch label.

For an explicitly selected local native worktree, completion and the next line must use the actual mapped worktree folder. The metadata lookup checks the selected source repository, native mainRoot, mapped source subdirectory, Git's registered worktree and branch, common Git directory, HEAD branch and baseline ancestry. It never accepts a matching team name alone. If the operator selected a subdirectory, the next instruction uses its corresponding native worktree subdirectory when present. Missing identity blocks advancement instead of sending the next line back to an unrelated source checkout.

For subsequent fresh lines on a remote machine, the coordinator passes **workspaceFrom** with the previous owned agent ID. The hub requires the same node and original source folder, a recorded remote checkout and an inactive predecessor. Under the store lock it reserves that same branch before releasing the lock. Another active writer cannot take that workspace, and a pre-launch failure cannot delete the predecessor's checkout.

Use Shell for all ordinary terminal capabilities: changing directories, running a program, reading logs, installing project dependencies in an appropriate environment, using pipes, and interacting with programs. Those actions follow the existing shell and agent authority rules. The bounded OS grammar intentionally remains small and deterministic; it should not pretend to be a complete shell.

## 7. Durable task records, recovery and cancellation

The direct task backend is integration/host/symblicos_tasks.py. It owns coordination, not a second provider implementation. Actual launches go through agent_hub.start with the selected options and an exact per-step group identity.

A client_request_id is required. It accepts 1–160 letters, digits, dots, colons, underscores or hyphens. The task ID is derived from that request ID; the retained request digest binds the exact instruction, mode, options and explicit context note. Repeating the same request returns the same task. Reusing its identity for different instructions or settings returns a conflict.

The instruction must be nonempty, contain no NUL and stay within 60,000 characters. Fresh-line mode permits up to 64 nonblank lines. An explicit context note is bounded to 12,000 characters, and each actual instruction plus its wrapper and context is checked against the agent prompt limit before launch. Engine, node, model, effort and directory have validated types; a machine must be selected explicitly.

The task record is written through atomic replacement with a file flush and parent-directory flush before a worker is started. Per-task file locks serialize record changes across processes. A distinct worker lock prevents two coordinators from advancing the same task simultaneously. Records include revisions, timestamps, options, steps, agent identities, URLs and outcomes.

| State | Interpretation |
| --- | --- |
| queued | A retained step has not been dispatched |
| dispatching | Launch intent was retained; a response may still be in flight |
| active | The owned agent identity is recorded and can be observed |
| awaiting_review | The placement lacks automatic completion evidence; inspect it before Next |
| finishing | The operator or coordinator is ending the current owned execution surface |
| completed | The recorded agent turns finished or were acknowledged; arbitrary objective correctness is not implied |
| cancelling / cancelled | Cancellation was requested or the coordinator's owned work was stopped |
| failed | A definite failure/refusal is recorded |
| unknown | An external operation or coordinator transition cannot be safely classified |

Native automatic turn-completion evidence applies to supported locally placed Claude, Codex and AGY sessions, plus explicitly discrete three-agent-pipeline sessions on the selected local or remote machine. The discrete adapter reads only an exact identity-matched version-1 receipt: status, round and an error of at most 500 characters. Planning/building/reviewing are active stages; completed means reviewer acceptance; failed and unknown block advancement. Missing or malformed metadata is no completion evidence. The general three-agent pipeline still uses the explicit review/Next path, as do placements without another authoritative adapter. A quiet screen, old chat message or round counter is never a completion event.

Before advancing, the coordinator stops the prior owned agent. For a new discrete team this requires terminating its exact named scope and observing systemd inactive/dead or not-found/inactive/dead state. Killing tmux alone is insufficient because an implementer can have detached children. Active, missing, malformed or unreachable scope evidence retains the reservation and prevents a successor. Resume and remove enforce the same scope identity and termination requirement. Local scope control uses the exact derived unit; remote control uses the existing registered-node transport. No whole slice or shared tmux server is stopped.

Council and squad parent rows retain their per-step group and launch intent before starting. New squads also have a named owned workload scope for detached gates and reviewers. Their Stop operation records cancellation, fences in-flight worker launches, confirms parent containment and stops only workers established by the ledger or a unique unresolved launch marker. A received HTTP error is not automatically proof that a worker never started: only an explicit refusal clears that launch intent. Generic error responses and malformed success acknowledgements remain available for exact-marker reconciliation. Historical unscoped parents and unresolved worker identities block completion instead of silently authorizing a next line.

On reconnect, task retrieval can identify a coordinator that disappeared during dispatch or finishing. Such a record becomes unknown rather than replaying the instruction. Resume can adopt a launch only when exactly one retained Agents row matches the exact per-step group. Zero matches or several matches cannot prove which side effect occurred.

Cancel stops the task coordinator and its owned execution surface; for new discrete teams this includes the derived workload scope and its descendants, with positive stop evidence required. Provider-side work, already launched external processes or a cloud service can continue outside that surface. The cancellation receipt states this scope. Browser reset and local watcher interruption are even narrower: neither proves remote cancellation.

Task history retains the newest bounded set of records, and task detail includes a bounded terminal view when available. If the terminal cannot be read, the receipt remains available with an observation error. Private task records and raw agent histories remain in their private stores; this book lists their contracts without copying their contents.

## 8. The bounded OS command language

The OS panel preserves the deterministic file-command interpreter. It recognizes the whole submitted sentence with anchored patterns, parses quoted values as literals, and rejects unmatched text. Finding a supported phrase inside a larger sentence is not permission to execute it.

The following forms describe the supported grammar. Paths and payloads should be quoted. A final period is optional. Double-quoted or single-quoted literals support escaped characters through the literal parser.

| Intent | Example |
| --- | --- |
| Create empty file | Create a text file named "note.txt". |
| Locate exact file | Find "note.txt". |
| Read file | Read "note.txt". |
| Replace contents | Write "hello" to "note.txt". |
| Replace contents, alternate wording | Replace contents of "note.txt" with "hello". |
| Find and write | Find "note.txt" and inside it write "hello". |
| Append | Append "\nsecond line" to "note.txt". |
| Make directory | Create directory "games". |
| List root | List files. |
| List directory | List files in "games". |
| Copy | Copy "note.txt" to "copy.txt". |
| Move | Move "copy.txt" to "games/copy.txt". |
| Flush persistent changes | Save the file "note.txt". |
| Inspect processes | Inspect running processes. |
| Inspect model inventory | Inspect models. |
| Inspect host/runtime | Inspect system. |

“Save the file” without a path uses the adapter's supported state semantics. It is not a general editor command that discovers any arbitrary currently open file. The filesystem root is explicit and separate from the agent folder. Traversal, symlink escape and unsupported operations are refused by the boundary. Mutations use the appropriate atomic file mechanisms and retain before/after information where relevant.

The process implementation can inspect processes, but the public imperative grammar does not expose unrestricted launch or termination sentences. Use the normal Shell or a chosen agent for those capabilities. Similarly, “inspect models” reports inventory; it does not perform a health inference for every model or load them merely to populate the screen.

An OS command stores its exact instruction and request ID before effects. Its execution ID is derived from the stable request ID. Concurrent duplicates share a lock, and a repeat returns the retained result. A different instruction under the same request ID is refused. An interrupted receipt is not used as an excuse to repeat an append, copy, move or other uncertain mutation.

The canonical receipt includes execution ID; original and normalized instruction; start/completion times; action category; actual target hostname; native runtime version and digest; compiled representation when applicable; files read, created, modified and removed; processes started/stopped; network endpoints; model names and available digests; validation checks/results; stdout/stderr; result status; and final result. Empty fields mean no such event was recorded, not proof of an unimplemented capability.

Explicit native syntax accepted in this legacy OS panel is sent to the compiler bridge. Its success message means **compiled successfully**. It does not run the native program there. Use the full Symblic editor or native CLI to execute it. The intent display is also an ordinary Symblic representation of intent data, not a claim that synthetic fs.* capabilities have been registered in the native effects catalogue.

The standalone development listener on loopback port 8990 is not the complete operator dashboard. Browser entry redirects to the integrated dashboard terminal so the shared catalogue, file browser and authenticated APIs are available. Its legacy API is constrained to its documented local-development boundary. There is no justification for tunnelling a worker node's unauthenticated development listener into the live dashboard.

## 9. Native Symblic language and exact execution

The native language separates exact computation from externally proposed answers. An integer arithmetic expression is evaluated by the kernel. An ask obtains a candidate from an applicator. An ensure or assert tests an encoded predicate. An observation records acquired evidence. An action can change an external system through a registered capability.

Start with a small explicit contract:

~~~symblic
program PositiveRoot.
use profile=verified.
ask root: Int in 1..9 "Find the positive integer whose square is nine."
ensure root * root = 9 else retry.
show root.
~~~

This program checks a precise integer condition. It does not depend on a prose explanation being persuasive. A model returning 4 is rejected. An unavailable model, malformed answer or exhausted retry budget remains a visible unsuccessful construction rather than a fabricated answer. Once the result is accepted, the recorded source, values, checks and identities explain what was established.

The three execution profiles are legacy, explicit and verified. Legacy preserves historical prose-as-ask behavior, with diagnostics. Explicit rejects implicit model calls. Verified adds stronger purity, coercion, voting and evidence rules. A host can strengthen the declared profile but cannot weaken it. Profiles belong to the program and cannot be secretly changed inside a block.

Statements generally end in an optional period and may continue while strings or brackets remain open or through documented continuation forms. Keywords are case-insensitive at statement starts, subject to the specific abstraction-layer grammar. Comments use a hash to end of line or a whole line beginning with two slashes. Numbers are exact decimals/rationals, and inclusive integer ranges use two dots.

| Native form | Role |
| --- | --- |
| program, note, section, module | Name and organize a program |
| use | Set ask defaults and declare the execution profile |
| given | Declare an input, optionally with a default |
| let | Bind a deterministic expression once per scope |
| define | Introduce a named type |
| term | Supply an operational vocabulary definition to matching asks |
| group | Name applicators and optional weights |
| fact, rule | Declare finite Datalog facts and stratified rules |
| ask | Request a typed answer with explicit context/routing options |
| ensure | Require a predicate, optionally retrying, failing or warning |
| assert, expect | Require a hard predicate |
| if, elif, else, end | Conditional execution |
| for, end | Bounded iteration with a child scope per iteration |
| show, return | Emit a value |
| draw | Save a deterministic drawing |
| forget, pin | Control later context selection without deleting bindings |
| delegate | Dispatch through an explicitly enabled agent integration |
| function, routine | Reusable deterministic or model-backed computation |
| import, test | Load a module and express executable examples/contracts |
| observe, act | Acquire capability evidence or perform an authorized effect |

Types include Int, bounded Int, Number, explicitly rounded/bounded Number, Bool, Text, word-bounded Text, finite enums, List, Set, Record, Svg, Any and named types. Code answers distinguish supported source languages and preserve code characters rather than requiring code to be escaped inside a JSON string. A schema is a requested wire shape; the kernel independently validates the received value.

Strict coercion rejects undeclared fuzzy key matches, ignored fields and scalar/container conversions. Legacy coercion remains available where the contract explicitly permits it. Numeric parsing does not silently extract 26.2 from “26.2 miles”: model-provided quantities need an explicit unit or an appropriate quantity contract. A parser error in a bound should remain a syntax diagnostic rather than accidentally becoming an implicit prose request.

Canonical representation version 3 preserves exact string identity, distinguishes typed values such as true and 1, sorts sets and record keys, and represents non-integer rationals explicitly. It prevents collisions between reserved canonical tags and ordinary record keys. Fingerprints are compact comparison keys derived from SHA-256; they are not signatures or mathematical guarantees that arbitrary external facts are correct.

A function has typed parameters and an expression body. A routine can contain asks and statements and return a value. Modules come from the standard library or saved source, with their identities retained. Verified function purity forbids transitive model/effect behavior in supposedly exact functions, including imported closures and initialization paths covered by the runtime guard.

Check, Preview, Run and Replay have different purposes. Check parses and analyzes source without a model call. Preview executes the deterministic prefix and reveals what an upcoming ask would send. Run performs the admitted computation. Replay consumes compatible recorded replies with no provider dispatch. A lock retains a portable record of source and identities for replay; it is not a certificate that a deployment or physical experiment occurred.

## 10. Model asks, checks, context and routing

An ask names its result type and instruction. It can select values from previous accepted results, choose an applicator or group, and set documented options such as retries, samples, rounds, seed, temperature, context budget, agreement policy, coercion and routing.

For a sequential route, escalation can move among allowed applicators after check failures under the recorded policy. Search can explore multiple candidates and repair attempts. Candidate selection is based on the defined deterministic ranking over the observed replies, including attempt count and candidate index, rather than whichever network response happened to arrive first.

The native call budget counts actual candidate, critique, repair and escalation work. A “three models” interface does not mean exactly three calls: a critic can reject, an implementer can revise, and an unavailable backend can stop the route. A useful report records calls, accepted attempts, rejected attempts, resource limits and the selected result's origin.

Retry feedback comes from the encoded failed checks and the caller's because text. Bounded concrete values can make it easier for a small model to repair a specific defect. Feedback is not permission to weaken a predicate until the candidate passes. Vacuous checks and repeated answer keys receive diagnostics because a superficially formal contract can still accept the wrong behavior.

Voting records agreement among observed candidates. Weighted or median voting and option permutations have explicit semantics. Verified mode refuses contested results under its contract. Agreement cannot turn a false predicate true, and several calls to the same model or family should not be described as independent experts without evidence.

Execution pins bind the actual source, inputs, loaded runtime, frozen modules and capability contracts. Optional model-identity observations record the manifest seen at the provider boundary. A requested model name alone is not a cryptographic identity; an observed manifest is not hardware attestation of loaded weights. Strict model-pin mode requires the supported identity evidence and refuses when it is unavailable.

Semantic checking and runtime execution intentionally differ. JavaScript execution adapters are not run during ordinary static checks or speculative enumeration. A function that passed finite js_test cases has evidence for those cases; it has not received an unrestricted theorem of correctness. Accepted code can still require a final assembled-program test and a real browser or application check.

Native artifacts retain more than a summary trace. Full accepted source must be recovered by its recorded identity, not reconstructed from a truncated screen preview. Replay and checkpoint reuse revalidate the applicable source and dependency identities before preserving prior accepted work. Changes to the compiler, runtime or contract can invalidate reuse rather than silently mix incompatible evidence.

## 11. Checked English and generated displays

The checked-English editor is the original direct-instruction idea expressed as a bounded language. It accepts an explicit vocabulary and compiles each statement to ordinary native Symblic. Unsupported clauses receive source positions. The arbitrary-English composer above it provides a different path when the task is outside that grammar.

The basic grammar includes Remember, Ask for, Using only, Accept only if, Show and Display. An ask has a declared shape: a whole number, a bounded whole number, a number, a bounded number, text, yes/no or a finite set of labels. Comparisons include equals, does not equal, at least, at most, more than and less than. An operand may contain one arithmetic step; longer expression chains must be split rather than assigned ambiguous English precedence.

~~~text
Remember width is 20.
Remember 'row 0' is 6.
Ask for 'row 1' as a whole number: "Subtract 1 from the numeric CONTEXT value named row_0. Return the difference.".
Using only 'row 0'.
Accept only if 'row 1' equals 'row 0' minus 1.
Accept only if 'row 1' is at least 0.
Display 7 at column 5 and row 'row 1' on a grid width columns by 7 rows.
~~~

Names map deterministically to readable native identifiers. Duplicate definitions, collisions after normalization, undefined names, forward references and self-selected answers are rejected. The instruction text inside the Ask for quotes is retained, while the worker's context uses the mapped name. **See next task** exposes that exact combination so the author can inspect what the model will receive.

The compiled direct-step program uses the verified profile and explicit context selection. Defaults are two corrections, 64 model calls and 12,000 context characters, unless the selected entry changes them within supported limits. A zero call budget allows checking/previewing but refuses model dispatch.

The construction extension supports the documented moving-dot and Matrix-rain specifications. Those examples compile into small model tasks with implementation interfaces, finite tests and selected accepted dependencies. They do not establish that every sentence describing a game can be compiled into a formally checked program automatically.

The original English, source map, compiler identity and compiled program remain with a saved run. Resume uses that saved program and its execution pins rather than recompiling under a newer compiler. A stale loaded compiler requires the appropriate dashboard restart before a new compilation. Native run refuses to overwrite an English-authoring record.

Running snapshots publish bounded outputs. The existing contract limits a running snapshot to 128 recent outputs and 1 MiB of output data, with omissions identified. The final retained report is the place for the complete result. Retry removes rolled-back output from the running view instead of leaving a rejected frame visible as accepted progress.

Playback interprets accepted bounded code/data and makes no new model calls. A browser drawing opportunity and a requested minimum software delay do not attest physical monitor scanout or guarantee exactly 60 frames per second. A zero RGB value does not measure optical black. The display examples retain those distinctions while providing useful actual software behavior.

The typed-answer worker picker now uses the existing SymblicPicker catalogue. This restores discovered model/machine choices without pretending every interactive team can substitute for a typed applicator. Full tool agents, councils and native teams belong in the direct composer or their native workspace when the goal is to edit or run a project.

## 12. Workcards, steps, task cards and spec sheets

[Workcards](WORKCARDS.md) are interfaces to the native language, rather than a second model service. Their preparation produces source, inputs and execution options that can be inspected in Write. The same parser, type checker, interpreter, model admission and saved-run evidence apply.

**Slots** put visible holes into a caller-authored template. Every hole declares its category, instruction and finite menu. Categories are expression, identifier and type. Every menu item must parse in the declared category; parsing does not establish that it solves the objective. The worker chooses a bounded one-based index. Expression replacements are parenthesized, and replacement traverses the original template only. A selected expression cannot create new holes that receive another replacement pass. The reserved delimiter is a pair of square brackets around the hole name; nested literal lists need the documented spacing.

**Teams** separate a builder from one to three reviewers. The builder supplies a typed answer, the kernel evaluates caller-authored predicates, and reviewers examine that candidate, the checks, explicit inputs and preceding reviews. Acceptance requires the predicates and every reviewer to pass. Review agreement cannot turn a failed arithmetic predicate into a success. Up to four rounds are supported, with a bound of rounds multiplied by one plus the reviewer count. A reviewer can reject a correct answer; several seats using one model are not independent experiments. Each role has an exact route so nested fan-out cannot silently multiply the declared call budget.

**Steps** construct reusable functions in order. A step gives one instruction, a signature, explicit accepted dependencies, possible expressions and local checks. Only accepted earlier functions named in its dependency list enter the worker's context. A deeper dependency must be named explicitly. The completed record keeps the model's selected expression and its original one-based index. Final assembly validates the saved source, inputs, runtime pins and passing receipts again; a browser assertion that the step passed is insufficient.

Finite completion is available but off by default. After the configured model attempts fail a bound local check, it tests the authored menu in order and accepts the first passing choice. The receipt distinguishes the rejected model answer from the engine-selected replacement. This fallback does not run after every kind of provider or resource failure, does not prove the passing choice unique, and does not backtrack through already accepted steps when a final combined check fails. It is an explicit finite search under the declared checks.

The parcel example has thirteen functions: area, volume, dimensional weight, chargeable weight, billing units, base price, oversize decision, fee, subtotal, promotion, net price, rounded tax and final price. The surrounding loop, possible expressions and tests are authored inputs. Once assembled, the program evaluates new parcels with zero model calls. The caller controls both what a worker may propose and what is sufficient to accept it. This is particularly useful when a small model can select or repair one function more reliably than it can invent an entire architecture at once.

**Task cards** make a bounded objective and its evidence visible to a worker. Their specialized proof counterparts expose an allowed focus, obligation or proof step instead of asking for an unrestricted full proof. They support reviewable delegation: an agent receives an explicit boundary, and returned work is checked against that boundary before it is accepted. See [Task cards](TASK-CARDS.md), [Proof task cards](PROOF-TASK-CARD.md) and the proof delegation references in the catalogue.

**Spec sheets** describe one output file as small units. Shared conventions, signatures, explicit dependencies, test setup and examples form the construction contract. Compilation is deterministic: the model does not write the native program. Each unit is asked in a fresh context; sandboxed JavaScript tests examine candidates; only passing units are assembled. Multiple routes and samples can be tried within the configured rounds, correction and call limits. Accepted old units can be reused only after the relevant pins and checks are validated. The generated file is an artifact, and its end-to-end behavior still needs separate checks.

These interfaces are complementary. Slots are useful when the alternatives are enumerable. Steps build connected pure functions. Teams add critique of an answer. Spec sheets give models more freedom to implement code under unit contracts. Direct agents are the appropriate surface when the task needs unrestricted project exploration, shell commands and ordinary programming tools.

## 13. Proofs, finite mathematics and research adapters

The proof and mathematics features are extensive enough that their exact contracts remain separate documents. [Proof terms](PROOF-TERMS.md), [proof commands](PROOF-COMMANDS.md), [incremental proofs](INCREMENTAL-PROOFS.md) and [proof steps](PROOF-STEPS.md) define the supported construction and checking rules. The important separation is between a model proposing a term or next step and a trusted checker accepting it. Natural-language confidence, a reviewer vote or a polished derivation cannot substitute for the checker result.

The authoring grammar is discoverable rather than guessed. Its catalogue, exported JSON or EBNF and context-sensitive menu let an agent request the available forms for the selected profile and session. Proof focus, obligation and step delegation narrow the subproblem presented to an agent. A returned object must fit the chosen task and the surrounding proof state; a new proof assertion does not become an assumption merely because a model wrote it.

[Finite logic](FINITE-LOGIC.md) and [discrete mathematics](DISCRETE.md) cover supported finite domains and exact constructions. Bounded loops and explicit finite sets can make exhaustive checks possible, but “finite” alone is not a claim that a problem will fit the resource budget. A large declared domain can still be expensive. Unsupported formulas, missing premises and exhausted limits need explicit outcomes rather than optimistic interpretation.

The optional constructor path uses supported solver-backed proposals under bounded attempts and time. Constructor provenance remains distinct from a model proposal. The presence of an expression solver does not make every language expression solvable, and its resource limit is the configured solver work allocation rather than a measured global operating-system memory ceiling. Constructor inspection, saved locks and provisioning documentation explain how to identify what actually produced an answer.

Scientific adapters retain units, discretization choices and model assumptions. [Quantities](QUANTITIES.md), [variational methods](VARIATIONAL.md), [transport](TRANSPORT.md), [projection](PROJECTION.md), [differential specs](DIFFERENTIAL-SPECS.md), [research geometry](RESEARCH-GEOMETRY.md) and [physics and advanced mathematics](PHYSICS-AND-ADVANCED-MATHEMATICS.md) explain different supported calculations. A zero residual for a declared finite field establishes that calculation under those equations. It does not establish a solution to every continuous physical system that inspired the notation.

Research agreements, source witnesses and solver provenance make it possible to ask where a claim came from and what accepted it. A source span can establish that a document contains a statement, while independent arithmetic checks establish arithmetic consequences. Those are different kinds of evidence. A source can be wrong, an instrument can be stale, and a mathematical model can omit a real-world effect even when its internal calculation is exact.

The papers interface compiles and checks the supported paper format and can reproduce it with explicit cohorts. Multiple cohorts enable measured agreement; agreement is not automatically truth, independence or universal validity. Likewise, the quantum and unification documents contain conceptual analysis and carefully bounded proposals. Their inclusion in this catalogue is not a claim that the implementation solves the open problems named in their titles.

Use the framework to keep a research claim small enough to audit: name the finite inputs, choose units, preserve the observation or source, state the equations, run the checker, and retain the output and limitation. Expand the claim only when a new independent check supports the expansion. This discipline is also useful for ordinary programs: a test of one function, a test of a composed program and a live deployment observation answer different questions.

## 14. Graphs, delegation, effects, memory and supervisors

The graph layer makes dependencies and policy visible. [Agent graphs](AGENT-GRAPHS.md) describes the graph execution contract. [Graph composition](GRAPH-COMPOSITION.md) assembles reusable graph definitions into an ordinary graph and policy draft. Definitions have named ports, instances bind those ports, and generated names separate repeated local nodes. Composition preserves definition digests and the mapping back to instances. It is a structural operation; composing a valid graph does not execute its agents.

Delegation templates expose bounded requests that can be checked and compiled before execution. An agent is given the declared problem, allowed context and expected result shape. Routes remain explicit, and a missing or unavailable route does not authorize an unrecorded provider substitution. The CLI offers catalogue, check, compile and run stages so a prepared request can be reviewed without spending a model call.

Effects add two important native statements. **observe** reads through a declared capability; **act** requests a change through one. The capability is named, arguments are named expressions, and results can be typed. These are connected to the host through the host executor. They are distinct from **ask**, which requests a model judgment. The evidence therefore records whether a value was proposed by a model, reported by an instrument or returned by an action service.

An action receipt establishes what was requested and what the service answered. It cannot automatically establish every external consequence. When an action may have happened but its acknowledgement was lost, replaying the request can be harmful. Durable effect journals preserve that uncertainty. Reconnect and reconciliation must inspect recorded action identity and evidence instead of turning every timeout into a new action. This same principle now governs direct task launches, remote agent reservations and Claude Cloud messages.

[Epistemic memory](EPISTEMIC-MEMORY.md) represents claims and changes with evidence rather than treating a long chat transcript as an unquestionable memory bank. Its API exposes list, create, view, change and context operations. A selected context is an explicit input to later work. It does not make all previous sessions available implicitly. This fits the central design: persistent state can be structured and selected while each model turn remains bounded.

A **Supervisor** workflow adds durable orchestration around exact native programs. Definitions are checked and frozen when saved. Supported workflow examples include run, join, delay, bounded wait and operator-state update steps. Dependencies determine which steps may advance, and maximum parallelism bounds simultaneous children. Each child retains its native run and evidence. The minute reconciliation pulse is suitable for recurring automation and recovery; it is not a subsecond animation clock.

Saving a workflow does not execute it. Run once creates a firing; refresh reads it; advance reconciles known children and performs ready transitions. Browser reconnects do not create another firing. A wait has an explicit condition and boundary. A stopped or unknown child cannot be silently treated as successful just to let dependents run.

The direct task manager and Supervisor solve related but separate problems. Direct tasks organize conversational coding agents, including fresh sessions per line. Supervisor organizes checked native programs and host effects. Their stores, identifiers and completion evidence differ. Both share the requirement that work be saved before launch and that uncertainty remain visible.

the fleet runner provides admitted execution and placement, while councils provide structured deliberation and squads provide owned work packages with command gates. the autonomous agents retain their native autonomous workstation interfaces. The terminal brings their existing workspaces into reach; it does not replace their authority rules, journals or acceptance semantics with a single generic “done” flag.

## 15. Claude Cloud as a practical CLI

*Removed for publication.* This section described a command-line wrapper for a cloud coding agent that belonged to the original host, not to Symblic. It is not in this repository.

## 16. Local source tools and pinned upstream repositories

Local models benefit from better source retrieval and explicit interfaces without needing an unbounded context window. Two source tools are installed in an isolated environment and integrated through **tools/symblic-context**:

| Upstream | Pinned revision | Integrated purpose |
| --- | --- | --- |
| [Aider-AI/grep-ast](https://github.com/Aider-AI/grep-ast/tree/9a2c49b00852d012dc97850a3c0b3248f15bd043) | 9a2c49b00852d012dc97850a3c0b3248f15bd043 | Show literal matches with useful surrounding syntax. |
| the CLI agent's contributed-tools repository | 0f5ba1f9859db2b510bfa0f7a2d7cca2f9f431b3 | Install its code-graph package for named symbols and static call relationships. |

The installer checks out these exact commits. Existing dirty or differently pinned clones are refused rather than reset. Build input comes from Git archives, keeping the reviewed clones unmodified. Dependencies and parser versions are pinned, and the resulting installation receipt is private. The tools do not mutate the service Python environment.

Run the following relative installer and **bin/** commands from **the host checkout on the host**. After installation, **symblic-context** is also available on PATH for use from a project directory on the host and the provisioned nodes; its **--root** argument still selects the explicit source root.

~~~sh
python3 tools/scripts/install_symblic_tools.py
tools/symblic-context doctor
tools/symblic-context pack --root /path/to/project --file app.py --query collision --max-chars 12000
tools/symblic-context --help
~~~

The pack command accepts --root, repeated --file, --query and --max-chars. Packs read only explicitly named source files, never automatically walk a repository or import its modules. One pack accepts 1–24 files, each at most 256,000 bytes and at most 1,000,000 bytes total. Supported source suffixes cover Python, JavaScript, TypeScript, JSX/TSX, Rust, Go, Java, C/C++, C#, Ruby and PHP. Hidden paths, private or history directories, common data-store names, vendor trees, traversal, absolute paths and symlinks are refused.

The reader checks regular UTF-8 text, excludes NUL bytes and verifies file identity and metadata before and after reading. The optional codegraph parser operates on an immutable temporary snapshot. Python has a standard-library AST fallback, and unsupported parser cases remain diagnostic. A literal search is bounded to 240 characters and at most forty matches; it is not a user-supplied regular expression.

The excerpt budget is configurable between 1,000 and 48,000 characters, default 12,000. Metadata sits outside that excerpt/symbol budget. Every file gets a SHA-256 digest; omissions and truncation remain in the result. Static calls and symbol relationships are navigation evidence, not runtime execution proof. Review a context pack before sending it to a cloud provider.

Node installation uses **integration/host/scripts/install_symblic_node.py BUNDLE** inside an already admitted cluster job. The bundle contains reviewed three-agent-pipeline source, exactly one CLI-agent wheel, the context helper and installers. It installs runtime binaries under the node's own home, verifies Node.js 18 or newer, creates isolated Python environments and runs help/version/doctor checks. An existing command wrapper not owned by this installer is preserved and causes an explicit refusal.

The bundle excludes accounts, conversation histories, SSH keys and browser profiles. It creates local commands for the CLI agent, the local CLI-agent wrapper, triad and symblic-context; it does not make provider accounts appear on another machine. The installer records the wheel digest and resolved command paths. Invocation must use the existing admitted cluster path so power reservations and fences cover installation work.

On October 6, the source-only runtime and retrieval tools were installed on node-a, node-b and node-f, then node-d, node-h and node-i. Help/version/doctor checks and fresh local/three-agent-pipeline capability discovery succeeded on all six. The additional installations used admitted jobs bounded to 25% CPU and 512 MiB each; observed durations were 35.340 seconds on node-d, 246.780 seconds on node-h and 24.924 seconds on node-i. node-h peaked at approximately 210 MiB without an out-of-memory event. Installation did not change Ollama service budgets: node-d remained at 12 GiB, node-h at 3 GiB and node-i at 26 GiB. Those observations establish installed tools and configured ceilings; the separately recorded coding-agent runs establish whether a particular prompt actually completed.

Adding an upstream repository is useful only after its behavior is connected to a real task. Here, retrieval has a bounded, tested adapter; the CLI agent and the three-agent pipeline have selected-node launch, identity and recovery contracts; installation has receipts. Merely cloning a project is not counted as a new working model capability.

## 17. Command reference

Commands below are current interfaces in this checkout. Relative **tools/symblic**, **tools/symblic-workcard** and other **bin/** commands are run from **the host checkout on the host**; these paths do not claim the full native language checkout is installed in a selected worker node shell. Node-installed commands are listed separately in Chapter 16. Run command help before automating optional arguments; the linked subsystem documents give examples and artifact formats. Paths marked RUN, FILE or DIRECTORY are caller-selected paths, not literal names. New run directories must satisfy each command's empty-directory requirement.

### Native language and authoring

| Command | Purpose and principal options |
| --- | --- |
| tools/symblic check FILE | Parse and check native source without executing asks. |
| tools/symblic preview FILE | Execute the deterministic prefix and describe where an answer is needed. |
| tools/symblic run FILE | Execute with --by, repeated --input name=value, --dir, --max-calls and optional --certificate. |
| tools/symblic replay RUN | Recheck retained native execution evidence under the supported replay contract. |
| tools/symblic english check FILE | Validate the supported English grammar and source diagnostics. |
| tools/symblic english compile FILE | Emit its native source and authoring metadata without model execution. |
| tools/symblic english preview FILE | Inspect the compiled deterministic prefix. |
| tools/symblic english run FILE | Compile and run; --by, --dir, --max-calls, --retries and --budget apply. |
| tools/symblic english resume RUN | Resume saved English construction with retained source and execution pins. |
| tools/symblic english examples | List supported English examples. |
| tools/symblic test FILE | Run declared native tests; use --by only when model participation is intended. |
| tools/symblic certify FILE | Produce the supported cohort/test certificate, with repeated --cohort and --certificate-out. |
| tools/symblic lib | Inspect supported native library information. |
| tools/symblic doc MODULE | Inspect a named standard-library module, for example tools/symblic doc units. The module argument is required. |
| tools/symblic grammar catalog | List authoring grammar entries. |
| tools/symblic grammar export | Export JSON or EBNF with --entry, --profile and --format. |
| tools/symblic grammar check FILE | Check a grammar-related request in the selected profile. |
| tools/symblic grammar menu | Obtain a context menu, optionally with --session and --profile. |

Base native commands support **--json** and **--agent-json**. Repeated **--input** values are interpreted as JSON when valid and otherwise as text. The default maximum call budget is 2,000; choose a smaller explicit bound for routine work. **--strict-model-pins** requires the supported version-one model identity record for a run.

Constructor options on the base CLI are **--constructor off|linear_diagnose|linear**, **--constructor-attempts**, **--constructor-milliseconds**, **--constructor-attempt-ms** and **--constructor-resource-limit**. Constructor execution requires run and a retained directory; enabled constructor modes disable the ordinary determine/solve path. Defaults are sixteen attempts, 80,000 total milliseconds, 5,000 milliseconds per attempt and 100,000 solver resource units; supported ceilings are 64, 320,000, 5,000 and 1,000,000 respectively.

English defaults are ollama:qwen3:4b-instruct, 64 calls, two corrections and a 12,000-character budget. A chosen route must actually be installed and admitted. JSON output switches do not relax model, source or receipt checks.

### Construction, graphs, memory and research

| Command family | Subcommands and key inputs |
| --- | --- |
| tools/symblic-workcard | catalog, prepare, fill, compile, run, result; --kind slots\|team\|steps, --request, --answers, --by, --dir, --retries, --context-budget, --finite-fallback. |
| tools/symblic spec | check, compile, run, checkpoint, manifest, verify; a sheet/run path plus the construction options below. |
| tools/symblic constructor | inspect RUN, optionally --agent-json. |
| tools/symblic lock | RUN creates a lock; show PATH and replay PATH inspect/replay it; --out chooses the lock output. |
| tools/symblic graph | catalog, example, compose FILE; compose accepts --flat for the ordinary graph/policy draft; JSON is the normal output. |
| tools/symblic delegate | catalog, check, compile, run; --template, repeated --by, --dir and JSON output. |
| tools/symblic memory | list, create, view, change, context; view takes an ID and other mutating/query forms use the documented request JSON. |
| tools/symblic inquiry | example or plan FILE; returns the supported JSON plan. |
| tools/symblic paper | compile, check, reproduce FILE; --out for compilation, repeated --cohort for reproduction and --json. |
| tools/symblic experiments | list, example EXPERIMENT, run EXPERIMENT FILE, verify FILE; stdin is available where the run form accepts a dash. |

Workcard corrections accept 0–5, default two; context budget accepts 1,000–100,000 characters, default 12,000. Finite fallback is opt-in and exposes the actual origin of each selected expression.

Spec construction accepts repeated **--by**, **--dir**, **--samples**, **--retries**, **--rounds**, **--budget**, **--presentation**, **--declaration-contracts**, repeated **--external** and **--redo**, **--keep**, **--manifest**, **--output-sha256**, **--manifest-sha256**, **--recheck-seconds** and JSON output. Defaults are one sample, three corrections, three rounds, 24,000 context characters, compact presentation and a thirty-second recheck allowance. Manifest and output digests bind the artifact being verified; a successful older build cannot validate changed bytes.

Some lower-level modules expose additional specialist commands. For example, the native language module contains crystallisation and job support. Their existence does not mean the top-level tools/symblic wrapper accepts every module subcommand as an alias. Use the documented module entry point when the wrapper's help does not list a command.

### Distillation

The distillation CLI separates data preparation, frozen plans, worker execution and comparison. **launch** and **launch-infer** print an explicit command/manifest; neither silently starts training.

| Subcommand of tools/symblic-distill | Required inputs and important options |
| --- | --- |
| hash | FILE. |
| native-check | --dataset, --item-id, --answer-json, --native-checker. |
| export-contracts | --runs, --dataset, --out; optional --repo. |
| export-run | --run-dir, --group-key, --out; optional --repo and --lock-file. |
| build | --records, --out; optional --allow-unavailable-model-identity or --lenient rejection reporting. |
| split | --dataset, --seed, --out; --ratios defaults 80,10,10; --exposures and --group-by control leakage grouping. |
| model-manifest | --model-dir pins a local model snapshot. |
| plan-train | --dataset, --splits, --model-spec, --out; optional --options and --method, default sft_lora. |
| prepare-train | --dataset, --splits, --plan, --jobs-root, --name; optional --expect-plan-sha256. |
| plan-eval | --dataset, --splits, --plan, --out; --max-new-tokens, --prior-test-uses, --checker and optional --native-checker. |
| checker-identity | --name for a registered trusted native checker. |
| prepare-eval | --eval-plan, --plan, --adapter-manifest-sha256, --jobs-root, --name. |
| launch | --job-dir, --models-root, --python; optional --adapter-dir. |
| launch-infer | --plan, --prompt, --out, --models-root, --python; --arm, --adapter-dir, --adapter-manifest-sha256, --max-new-tokens, --dataset and --splits. |
| compare | --eval-plan and --outcomes; compare recorded results without provider execution. |
| grpo-status | Report the verifiable-reward/GRPO adapter's actual status. |

Training and evaluation datasets are pinned separately. Splits group related sources and digit skeletons by default, reducing a known class of train/test leakage. A frozen evaluation compares baseline and trained artifacts on the same declared prompts. One tiny pilot does not establish a broad accuracy gain, and reference agreement alone is not an independent scientific check.

## 18. HTTP and source architecture reference

The browser is a client of the existing dashboard. The hosted runtime reuses operator identity checks, shared engine discovery, admitted launch paths, tmux sessions and atomic stores. The standalone legacy listener on port 8990 redirects its browser entry to the integrated dashboard. Its bounded OS API stays loopback-only; it is not a second public management server.

| Layer | Main sources | Responsibility |
| --- | --- | --- |
| Terminal page | symblic-terminal.html (not included in this repository), CSS (not included in this repository), JavaScript (not included in this repository) | Minimal composer, task cards, collapsible controls and native workspaces. |
| Shared direct composer | symblic-task-composer.js (not included in this repository) | Same agent catalogue and task submission flow in terminal and English. |
| Hosted API | ../../symblicos_engine.py | Operator checks, host checks, route dispatch, task lifecycle and catalogues. |
| Direct tasks | ../../symblicos/tasks.py | Durable request identity, launches, progress, fresh lines, recovery and cancellation. |
| Managed projects | ../../symblicos/workspaces.py | Safe project names, managed directory identity, empty Git baseline and idempotent creation. |
| Bounded OS requests | ../../symblicos/intake.py, ../../symblicos/terminal_server.py | Full-sentence parsing, selected named adapters and file/process/model/system reports. |
| OS receipts | ../../symblicos/receipts.py | Durable per-request records and journal. |
| Model metadata | ../../symblicos/model_engine.py | Shared catalogue and registered applicator checks without a separate direct Ollama bypass. |
| Agent launch and state | the agent hub, the agent hub, the agent hub | Engine selection, local/remote tmux lifecycle, worktrees, reservations and model admission. |
| Cloud task transport | ../../scripts/claude_cloud_agent.py, ../../scripts/claude_cloud_console.py | Source-only snapshot, exact cloud identity, durable messages, console and artifact validation. |
| Source context | ../../symblic_context.py, ../../scripts/install_symblic_tools.py | Bounded source packs, pinned retrieval tools and installation receipts. |

These entries are repository-relative references from this book. Source modules are authoritative for current argument validation; historical line numbers are not stable identifiers. The original host's system map and contracts are not part of this repository.

The integrated prefix is **/api/symblicos/**:

| Method and suffix | Input | Result or purpose |
| --- | --- | --- |
| GET catalog | Optional refresh flag | Shared available engines, model choices and machines. Refresh queues existing serial background metadata probes; the returned snapshot can still be cached and reports refreshing. It does not run a model. |
| GET vitals | None | Actual host/runtime information and bounded capabilities. |
| GET tasks | None | Retained task summaries. |
| GET tasks/get | id | One task snapshot and its current owned-agent observation. |
| POST tasks/start | Exact request object below | Durable task identity saved before launch. |
| POST tasks/control | id and action cancel, next or resume | Owned-session control or explicit recovery. |
| POST workspace/create | name | cwd, path, name, created and baseline for a managed project. |
| POST terminal/submit | instruction and client_request_id | Bounded OS execution or native-source compilation receipt. |
| GET terminal/history | None | Retained bounded-terminal history. |
| GET receipt | id | One receipt; the receipt/ID path form is also supported. |

The task request includes **client_request_id**, **instruction**, **mode**, **fresh_lines**, **engine**, **model**, **effort**, **node**, **cwd**, **worktree**, **auto**, **roles**, **council**, **squad**, **context_note**, **context**, **attachments**, **deepResearch** and **workingDefaults**, as applicable to the selected engine. Mode is agent, lines or qwen. The optional boolean **fresh_lines** applies to qwen and selects one new team per nonblank line; its default is false. Qwen mode sets the internal hub **discrete** flag and validates three explicit Qwen/Ollama seats. Unsupported shapes are refused before launch. The task manager does not invent an engine-specific option after the user submits a different one.

Instructions are bounded to 60,000 characters, a shared context note to 12,000 and a line sequence to 64 nonblank lines. Discrete Qwen also checks every prepared line plus its actual wrapper and context against the native 20,000-UTF-16-unit task maximum, including later hub defaults and attached context in the final hub check. Client request IDs are 1–160 permitted identifier characters. The durable internal task ID derives from the request ID, and a separate digest binds the exact complete payload. The same ID with different options is a conflict even if the visible instruction happens to match.

Automatic operation defaults on, own-worktree defaults off, and the selected machine is explicit. These are per-task settings and do not turn every subsystem into a universal unattended action system. A provider login prompt, missing executable or admitted resource refusal remains visible. The direct task manager starts engines only through the existing hub.

Mutation routes require the correct execution host. The hosted module is restart-gated, so a static page update alone does not prove its new Python route is loaded. A missing API is handled as an actionable UI error. After an authorized dashboard restart, verify the new process identity and the actual route behavior.

Remote starts persist the named node and reserved checkout before checking the power fence. Native tmux runs under the existing per-node terminal socket; workloads enter their own work scope. Every remote local/three-agent-pipeline start and resume freshly probes the exact registered node, with a sixty-second metadata bound; missing evidence refuses before launch. The selected node's probe supplies installed models, model byte sizes, free RAM, Ollama loaded state, runtime tools and service memory ceiling. The local/three-agent-pipeline check budgets 8,192 tokens and reserves RAM headroom. Host RAM alone cannot override an undersized Ollama service cgroup.

Local the CLI agent agents receive a stable unique session name derived from the display name and agent ID. Resume uses that exact identity. The remote three-agent pipeline resolves a native session by both team name and checkout. Unknown transport, missing tmux or malformed state is not proof of absence. Stop, resume, remove and listing preserve reservations when liveness is unknown. A confirmed absent session is treated differently from a failed connection.

Fresh remote lines use **workspaceFrom** only for the owned prior inactive agent on the same node and source directory. The new agent obtains the same remote checkout without provisioning a replacement. Reservation checks prevent two active writers from reusing it simultaneously. A failed successor launch cannot delete the predecessor's workspace.

## 19. How Symblic developed and what it has built

The initial goal was direct language that gives a model one well-defined task at a time, preserving objective control and resetting irrelevant context. The early experiments explored whether small local models could do useful work when exact computation, selected context and acceptance rules belonged to an interpreter. The resulting architecture moved much of the burden from an ever-longer conversation into explicit program structure.

Typed asks separated a proposed value from the check that accepts it. Routing made the chosen worker visible. Retries supplied a narrow counterexample instead of a whole accumulated transcript. Native arithmetic and control flow made deterministic work independent of model fluency. Saved evidence then made a successful output possible to replay and a rejected attempt inspectable.

Later work expanded authoring and composition: checked English, code contracts, spec sheets, proof terms, finite mathematical adapters, workcards, graph composition, delegation, epistemic memory, supervisors and distillation. These layers retained the same useful distinction: an agent may propose, while a named checker or effect service establishes a specific result under its own contract.

The terminal overhaul on October 6 addressed a usability gap. The original checked English editor was useful for its supported language, but the operator also wanted ordinary English to command any available agent to build files and run tools. The new direct composer provides that flow, while the original strict grammar remains available. A durable task layer supports reconnect and fresh-context lines. Native workspaces expose the broader tools without forcing their advanced controls into the default prompt area.

### Recorded constructions and what their evidence means

| Construction | Recorded result | Appropriate interpretation |
| --- | --- | --- |
| Small arithmetic comparison | An earlier eighteen-item record reported 18/18 for the compared setup. | A result on those arithmetic items, not proof of general parity with Opus or every larger model. |
| Builder/critic root example | Two local Llama3.2 1B calls returned 3; native sign and square predicates passed. | A working small-model team on a bounded mathematical answer. |
| Finite vorticity construction | Qwen3 4B used twenty calls with no repairs; the declared finite equations had zero residual. | Exact evidence for the specified field and equations, not an unrestricted fluid-dynamics theorem. |
| Tetris spec sheet | Twenty-five units and 120 authored examples; two builds passed 39 independent checks. | A substantial checked construction with model-written units and authored architecture/tests. |
| Moving white dot | Nine implementation tasks; a saved recovery kept seven rechecked functions and generated two remaining ones. | Accepted software playback with position/wrap checks, not physical display attestation. |
| Matrix rain | Nine accepted tasks, ten model calls, one rejected candidate; 44 frozen held-out checks passed. | A measured checked English construction with independent software validation. |
| Parcel functions | Two Llama3.2 1B builds each assembled thirteen functions with explicit finite replacements for rejected proposals. | Useful bounded construction with model and engine contributions separately recorded. |
| Small-model distillation pilot | Four Qwen2.5 0.5B LoRA updates; frozen three-item reference agreement changed from 0/3 to 1/3. | A functioning training/evaluation path, too small for a broad improvement claim. |
| Claude Cloud smoke program | Empty-source task created a pure greeting module and tests; follow-up added a third case and published a current-turn report. | Two real native cloud turns and scanned returned source, with local replay tracked separately. |

The first recorded Tetris path needed 421 model calls and about twenty-one model-hours across incremental attempts. A later from-scratch build used 141 calls and about 8.7 model-hours. Roughly thirty percent of the resulting script was verbatim authored sheet material. These figures matter: an impressive completed game does not imply cheap, automatic or unauthored construction. The useful result is that small local models produced tested components within an explicit architecture, and the artifact passed separate checks.

Matrix rain began with an incomplete decomposition. Its first baseline used nine calls and accepted five tasks while rejecting four, including a trail-cell/leader-row mismatch. The revised sixty-sentence specification completed on node-f with Qwen3 4B in about 1,115.5 seconds, nine accepted tasks and ten calls. No host candidate fallback supplied the accepted functions. Forty-four held-out checks were frozen before that second run; independent validation examined ninety-nine full frames and 18,057 cells without a shape failure.

That Matrix record also distinguishes available dependencies from actual function calls. The final program called all nine functions, but one head-update implementation expressed a wrap inline rather than using a selected movement dependency. Supplying a dependency does not force a model to call it. If use of a particular abstraction is part of the objective, that requirement needs its own check.

The two parcel builds used different choice orders. One retained five of thirteen model proposals and replaced eight with the explicit finite engine; the other retained seven and replaced six. They each used thirteen model calls and the same 128 predeclared cases. These are not 256 distinct held-out cases, and the earlier adaptive attempts are not a matched comparison. The record keeps the initial model errors, the finite search trials and the completed artifact separate.

One parcel defect was especially instructive: weak tax checks could accept a locally plausible rounding expression that failed a combined calculation. Adding an already public distinguishing case rejected thirty-nine distractors while retaining the thirteen intended expressions. Better contracts, rather than a claim that context reset alone fixes reasoning, supplied the missing control.

The distillation pilot's separate physics question still failed. Keeping that result is necessary to understand the measured scope. The system can export eligible accepted examples and run a pinned training/evaluation workflow; this small pilot does not show general physics competence or justify discarding independent checks after training.

The design's practical strength is compositional control: small tasks, explicit interfaces, bounded state, selected evidence, reliable tools and independent acceptance. Its historical evidence supports that approach on the named tasks. It does not yet supply a matched broad benchmark proving three Qwen seats universally equal any named frontier model.

## 20. Practical recipes and diagnosis

**Build a new project.** Open the terminal, choose New project, enter a lowercase project slug and let the managed project operation return its folder. Pick the agent and machine, then describe the deliverable and its acceptance criteria. Ask it to save actual files, run tests and report how to launch the result. The project operation does not start the agent; Run does. A lost creation response is recoverable by repeating the same managed name.

**Use three Qwen roles.** Choose the Qwen team mode, select an installed Qwen model for each role and an eligible node, and keep automatic tools enabled. The native controller enforces plan → build → review with at most three build/review rounds. Keep the planning task, implementation task and review criterion explicit. The roles can share a model or use distinct installed models that each pass the node's memory admission. Inspect the resulting code and tests. Agreement is useful critique, but the actual program must still run.

**Split work into fresh contexts.** Choose **Fresh task per line** and write one self-contained instruction per nonblank line. Put reusable acceptance criteria in the shared context note. Tell later steps which files to inspect. An example sequence is: create the game module; add tests for movement and collisions; review and repair failures; write a short usage guide. The existing files persist, while a new agent session receives the next line. For a full new Qwen team per instruction, choose **Three Qwen · plan / build / review** and enable **New team for each line**. Its explicit native accepted receipt can advance after the previous scope is stopped. Use Finish step & Next when the chosen engine lacks authoritative automatic completion.

**Retain ordinary terminal power.** Open Shell for commands requiring a real shell, existing sessions for tmux continuity and Files for browsing. A command such as a pipeline, package operation or service inspection is a shell operation unless an agent is explicitly asked to perform it. The bounded OS English panel deliberately implements its listed file/system verbs only.

**Choose a different computer.** Select Machine before Run. Refresh agents after installing tools or changing model availability. Check the exact selected node's capabilities, not the coordinator's inventory. A missing provider login must be completed on that node through its normal provider flow. Browser profiles, tokens and accounts are not copied by runtime installation.

**Recover after losing the browser.** Reopen the task list and inspect the durable task and owned session. Resume reconciles evidence; it does not immediately re-run the prompt. If a launch is unknown, inspect the native session and reservation. Do not create a new task with the same external effect merely to make the status look cleaner.

**Collect a remote project.** Use the existing Work workflow to inspect commits and synchronize the remote branch. Apply performs the existing reviewable three-way operation against the carried baseline. It is separate from a task's conversational completion. A returned branch is not automatically merged or published.

**Use precise checked English.** Open the original checked editor, load a supported example and review its source-linked diagnostics. Check and Preview before Run. Select a typed applicator from the current picker. When authoring a new unsupported sentence, either express it in the documented grammar or use direct agent mode for ordinary programming.

**Give a small model source context.** Produce a bounded source pack from explicit files. Inspect omitted symbols and excerpt limits. Supply the exact pack or selected files to the task. A pack can make an interface visible; it cannot prove a dynamic call graph complete or replace tests of the edited behavior.

**Use Claude Cloud repeatedly from a shell.** Run a new task with a short ID, watch it, read its report, then prompt the same ID with the next instruction. Resume opens the steering console. Use a new ID only when a new cloud context is intended. Wait for the report naming the newest message before treating the old completion as the new result.

**Diagnose “nothing happened.”** First distinguish refused, waiting, running, awaiting review and unknown. A resource refusal means choose another admitted node/model or release unrelated work; it is not a reason to call Ollama directly. Waiting for a provider prompt requires the native provider view. An unavailable hosted API may mean Python changes have not been loaded. An unchanged cloud branch may mean the provider has not pushed a protocol report; check the native conversation.

**Diagnose a failed program.** Preserve the failing input, exact artifact digest and test output. Reduce the failure to a local predicate or focused acceptance command. Repair the earliest missing contract, then rerun the relevant downstream checks. A model's statement that it tested the code is a claim until the test output and tested source are retained together.

## 21. Verification record and live sign-off

The counts below are scoped observations. They must not be added together as a unique-test total: broader suites can include the same focused tests. Isolated tests replace providers, stores and launch interfaces; browser tests replace API/WebSocket behavior before loading the page. They do not execute the operator's real accounts.

| Area | Recorded check | Status and scope |
| --- | --- | --- |
| Claude Cloud console and transport | 47 isolated tests | Passed; source allowlists, durable messages, uncertain sends, modes, watcher freshness, fake provider results and console paths. |
| Agent hub, remote lifecycle and task coordination | 296 combined tests on node-a, 13.744 seconds | Passed; includes fresh admission, native branch synchronization, exact completion identity, validated worktree handoff, discrete scope termination, provider wiring and durable tasks. Git repositories are temporary; transports and systemd are controlled fakes. |
| Work → Apply repository identity | Four focused tests, 0.827 seconds | Passed; external Python/server/service files apply without a dashboard-restart claim, while resolved serving-repository identity retains the correct restart notice. Carried-work and named-commit apply paths remain covered. |
| Cached-negative admission repair | Eleven focused checks, 1.19 seconds | Passed; stale offline/runtime/RAM entries cannot block a fresh-ready start or resume, while genuine missing runtime and capacity refuse before provisioning. |
| Source context | Six isolated context tests | Passed; explicit-source boundaries, snapshot integrity and bounded retrieval. |
| Terminal browser | Fifteen isolated browser cases | Passed in the complete combined 35-case run; direct tasks, exact selections, collapsible controls, recovery, managed projects, actual workspace display and first-load metadata discovery. |
| Later primary-action placement check | One focused browser case, 4.974 seconds | Passed after moving the unchanged Run/reconnect actions and status ahead of advanced/team settings. The case checks normal and Qwen modes at 1365×900: Run precedes advanced controls, is visible without opening them, and creates no horizontal overflow. This is a later targeted delta, not a second complete 35-case run. |
| Existing English and construction browser paths | Twenty cases | Passed in the same complete combined run: 35/35 overall, 44.725 seconds, zero failures or skips. Retained editor/circuit behavior alongside the direct composer; API and WebSocket transports were replaced before loading the pages. |
| SymblicOS fixture smoke CLI | Twenty-one fixture checks | Passed in a temporary root; no live providers, network or process launch. |
| Acceptance and release-evidence regression | Nine isolated tests | Passed; truthful counts/scopes and no invented boot, framework, physical or model verification. |
| Durable task and workspace backend | Fifty-three isolated tests | Passed; durable starts, recovery, bounded OS behavior and managed workspaces. |
| Fresh remote admission | Six focused tests in a ninety-test combined run | Passed with 31 remote lifecycle and 53 SymblicOS cases; fresh selected-node evidence required on start and resume. |
| Managed the CLI agent adapter | Sixteen isolated JavaScript cases and thirty-seven pure Python guard cases | Passed; immutable alias proof, no uncertain create replay, whole operator instruction, actual tool-payload bounds, provider identity, signals and confirmed unload. Python coverage includes generation-budget, prose-continuation and context-handoff cases: counters, elapsed time, auxiliary/queued calls, invalid configuration, no implicit prose completion, later size pressure, initial oversize refusal, identity mutation before exhausted-budget handoff, completion after the last allowed response, unchanged raw-context protection and unchanged ordinary mode. Captured public Ollama metadata verifies parameter-order normalization and migration of an owned creating receipt without another create call. Installed wrapper journey is recorded separately. |
| Installed managed the CLI agent runtime | Five isolated actual-CLI journeys on node-b, 89 assertions, 31.640 seconds | Passed: 18 success assertions for exact alias/payload, complete prompt and real temporary save→complete; 13 oversized-prompt refusal assertions; 14 initial TURN_PRE objective-mutation refusal assertions; 19 bounded-build handoff assertions; 25 prose-continuation assertions. The first two negative cases refuse before any chat HTTP/file action. The one-call handoff saves the real temporary file, makes exactly one generation request, exits 75 with the exact marker before a second call, and confirms unload without claiming completion. The final journey sends two prose-only replies, then an actual save and native complete in four calls: both continuation messages request unfinished tools/edits/checks, the exact original operator text survives every call, the saved file is verified, and models unload. Fake local API only; actual installed CLI-agent (0.34) executed. |
| Discrete tool-set installed-runtime delta | Two actual-CLI journeys on node-b, 46 assertions, 17.489 seconds | Passed on the final v10 implementation: 20 bounded-handoff assertions and 26 prose-continuation assertions. Every actual request used append/complete/read/save/shell with no patch schema; ordinary fixture tools retain patch. These are focused reruns of two journeys from the preceding 89-assertion record, not an additional disjoint total or a newly completed five-journey batch. Actual the CLI agent ran against the isolated fake local API. |
| Context-handoff installed-runtime validation | Seven actual-CLI journeys on node-b, 129 assertions, 62.244 seconds | Passed on guard 5c7a1580: normal oversized input 13 and initial operator mutation 14; discrete oversized input 14 and operator mutation 15; bounded call handoff 20; prose continuation 26; context handoff 27. The four refusal journeys made zero generation calls. The context journey completed a real save and a native read of all 1,601 lines, then exited 75 before a third HTTP generation at two of six allowed calls, preserving the exact original operator text, file and confirmed unload. All providers are local fakes. This is a new scoped batch with overlap with earlier fixture records, not a disjoint total. |
| Completion-boundary installed-runtime validation | Nine actual-CLI journeys on node-b, 182 assertions, 90.290 seconds | Passed on guard 16c36d36: 26 checks for save→complete at the two-call limit and 27 checks for a final complete response delayed 10.2 seconds across a ten-second elapsed limit. Both return zero after exactly two HTTP generations, preserving the exact original instruction and saved file, confirming native completion and model unload. The preceding seven refusal/context/handoff/continuation journeys also passed on this exact guard. All APIs are local fakes; this overlapping batch is not added to prior counts as unique coverage. |
| Team recovery and containment | 104 combined tests, 106.573 seconds | Passed; task manager, council/squad identity, in-flight launch fencing, squad scope and owned-worker cleanup. |
| Squad answered-but-uncertain launch regression | Forty-two squad stop/runner/reliability tests, 12.084 seconds | Passed; includes spawned worker followed by HTTP error, malformed success identity, explicit refusal and exact-owned cleanup. |
| Native three-agent-pipeline suite | 119 tests on node-a, 35.901 seconds, zero failures/skips | Passed on the combined review-clarity and explicit-completion prompt revision. Includes the earlier 110-case four-tool/runtime suite, seven review-evidence cases and two actual fake-child spawn cases comparing ordinary/discrete prompts while preserving the exact operator instruction. Covers partial critic handoff, detached fake-child cancellation, uncertain stage recovery, captured-metadata receipt migration and ordinary engine behavior. Pure Python guard and actual installed-client checks are recorded separately. |
| Native review checkpoint scope | Four focused checks, 4.319 seconds | Passed; actual generated Python cache files are excluded consistently, while untracked source added during review and tracked operator changes prevent acceptance. |
| JavaScript sandbox adapter | 54 tests, 25.950 seconds | Passed, no skips; actual sandbox behavior plus mocked capability probes. Adapter version 8 checks Landlock network-isolation ABI at least 4 before reporting available. |
| Constructor import markers | Fourteen tests, 6.092 seconds | Passed; complete constructor registry and identical existing marker handling preserve authored source. |
| Epistemic regression fixtures | Forty-one methods, 24.186 seconds | Passed after test-domain and semantics-identity repairs; frozen oracle and production semantics unchanged. |
| Broad Symblic/SymblicOS regression | 203/203 modules with passing outcomes; 3,389 covered case executions; zero unresolved skips | Resolved coverage ledger: 140 remote modules / 2,342 executions plus 63 full-environment local modules / 1,047 executions. Earlier failures and reruns remain recorded; this is offline fake-provider and temporary-store coverage. |
| Final expanded discrete prompt | Five focused checks, 1.326 seconds | Passed; native UTF-16 limit, full defaults and context, exact local/remote prompt files, and refusal before admission/provision/spawn. |
| Node tool installation | the CLI agent/the local CLI-agent wrapper/three-agent-pipeline help/version and context doctor on node-a/b/d/f/h/i | Live prerequisite checks passed; isolated runtime installation and source-only bundles through the admitted cluster path. All six now have the combined v12 runtime: context handoff, review-evidence clarification, explicit discrete completion and completion-boundary correction, with 44 exact application-file pins, the reviewed the CLI agent wheel and help/version/context doctor checks verified per node. These installation checks made no model calls. Model capacity remains independently admitted, including node-h's unchanged 3 GiB Ollama ceiling. |
| Dashboard deployment and responsive layout | Latest restart 3297765→3325190; HTTP 200; final desktop 1365×900 and dark phone 390×844 checks | Passed: all ten engine choices visible, text controls at least 16 px, no horizontal overflow, zero unopened lazy-panel iframes, and Run instruction placed before advanced settings and visible in the initial desktop view. The restart loads the repository-specific Apply notice; later static UI changes require no Python restart. This is deployment/UI evidence; the model task is recorded separately. |
| Live task-card reconnect | Reloads during active work, final desktop/dark-phone checks, and the completed two-step card | Passed: the existing card returned exactly once with zero POST tasks/start requests, the correct execution machine/workspace, separate the host source folder and Review/apply link. The final reload visibly retained both completed steps and introduced no overflow or duplicate submission. No unopened lazy-panel iframe was introduced. The operator closed only the dedicated test browser session afterward, preserving other sessions. |
| Claude Cloud live smoke | New empty-source task and a follow-up | Both native turns completed; exact current message receipt observed, returned source scanned and fetched. |
| Local replay of cloud artifact | Pure greeting module and three unit tests | Passed, 3/3 on Python 3.12.3 in private scratch; no live patch apply. |
| Checked English live compile/check | Falling-number construction, six separate context-none asks, max_calls=0 | Passed on the loaded route; establishes checked compilation without claiming model generation. |
| Saved model-free API runs | Checked English output 42 and native JavaScript output 5 | Passed through the actual API and existing systemd launcher; by=kernel, max_calls=0 and calls=0. This proves execution routes without implying model availability. |
| Bounded OS live journey | Create, write, read and repeat the same write request | Passed on the restarted dashboard; repeated write returned the original receipt, with no model invocation. |
| Independent live Qwen candidate validation | Immutable first-round 14B candidate; eight test methods, 0.090 seconds | Passed in isolated private scratch: the six generated tests plus two independent methods covering 900 movement cases and four invalid directions. Reconstructed source hashes match the checkpointed candidate. This validates that candidate; the originating build yielded and native team acceptance and second-line handoff remain separate. The later reviewed operator Apply is recorded below. |
| Reviewed operator Apply of Qwen candidate | Normal Work/Apply route; one changed test file, followed by six tests | Passed: the independently reviewed first-round candidate was applied to the owned source project without committing or restarting; six tests passed in 0.076 seconds. This is an operator-accepted application, not a native accepted receipt or proof of fresh-line advancement. |
| Discrete Qwen live coding journey | Actual browser-submitted v12 task with three explicit qwen2.5:14b seats on node-i and two fresh lines | Passed: both native teams completed in round one with implementer SUCCESS/exit zero, six tests passing and reviewer acceptance. They have distinct conversation identities and share the exact workspace. The first accepted commit makes no changes; the second adds only README and preserves both Python hashes. The earlier operator-applied candidate remains separately identified. |
| Final native workload cleanup | Exact two task-owned scopes/cgroups plus selected-node Ollama state | Passed after the two-line task completed: both scopes are not found/inactive/dead, both derived cgroups are absent with no owned process IDs, and /api/ps reports no loaded models. This is positive task-specific cleanup evidence. |
| Final reviewed README Apply and independent source checks | Actual Work diff, operator review, normal Apply and isolated system Python | Passed: the accepted second commit changes only the 15-line README; its example and test command were reviewed, both Python hashes remained unchanged, and normal Apply added only README without committing or restarting. Eight post-Apply methods passed: six generated and two independent methods covering 900 movement cases plus four invalid directions. Measured wall time was 0.116 seconds; the unittest runner reported 0.016 seconds. |
| Full integrated live journey | Actual browser submission, native two-line task, fresh workspace handoff, Work review/Apply and cleanup | Passed for the recorded v12 journey. It used three explicit qwen2.5:14b seats on node-i, two fresh teams, native first-round acceptance for both lines, responsive reconnect without duplicate launch, separately reviewed final Apply, independent source tests and confirmed scope/model cleanup. Each broader capability retains its own scope and prerequisites in this chapter. |

The broad ledger reconciles retained runs rather than overwriting an earlier failing exit status. Initial remote staging lacked some library assets and test dependencies, and older worker node kernels correctly refused the required Landlock network-isolation capability. Those 63 modules were rerun locally with their actual assets and dependencies. A remote JSON-schema dependency skip was rerun successfully. Three initial local failures concerned the deliberately changing kernel identity fixture, a runtime source-identity refusal during concurrent JavaScript edits, and a legacy oracle generator accidentally sampling a newer provenance origin. Focused 71-case core/delegate and 41-method epistemic reruns passed after the narrow repairs. The original failed batch remains failed in the raw log; the resolved per-module evidence establishes the final 203-module coverage.

The first context-pressure installed-runtime fixture deliberately remains a failed run in the record. Its guard passed the pure ordering checks, but native preparation reduced a roughly 31,494-token read result to about 1,000 tokens before the final wire guard, allowing an unwanted third request. The corrected guard now checks full context before native preparation and immediately before the reducer after enrichment. Its exact source SHA-256 is **5c7a1580c32ade593aec7e267ea587599da0f96ca2dea81f82fa3ccd49752f08**. Thirty-four pure tests passed, and the subsequent seven-journey installed-client batch passed all 129 assertions without weakening the large-read fixture. The actual two-call context handoff is distinct from a six-call budget handoff and from rejecting an initially oversized instruction.

A later actual-client boundary check found that the early pre-reduction call/time check ran before the CLI agent could recognize an already emitted native complete tool. Both a complete response at the two-call limit and a delayed final response crossing its elapsed limit incorrectly returned exit 75. The narrow correction removes only that early call/time check; full operator/system/model/endpoint and pre-reduction context checks remain, and the final provider boundary still refuses another generation. The final guard SHA-256 is **16c36d36ecd35389c18814427f7d434afc4e3a98e28147e2ea1ee5a40c58911f**. All 37 pure guard cases passed, followed by all 182 assertions across the nine installed-client journeys. Both failing baseline receipts remain part of the diagnostic record. This completes the measured completion-boundary repair without adding a special completion parser or allowing an extra model call.

The native three-agent-pipeline full suite initially exposed a separate team-inbox ordering defect when messages shared a millisecond. The fix adds monotonic timestamp allocation for lexical filenames while retaining the schema and legacy reader. Eight focused team cases, including four new cases, passed. The latest completed native suite passed 119/119 in 35.901 seconds, adding seven review-evidence cases and two discrete-completion prompt cases to the earlier acceptance-scope, generated-metadata parameter-order, bounded-build critic-handoff and discrete-only tool-selection corrections. These are native controller and messaging tests with controlled providers, distinct from the live Qwen model task.

The bounded-build v8 source-only node bundle has SHA-256 **338d1f41a36eef5f736920a681127452e25a18de297faa4752d3acb0b8e734be**. It was installed through admitted jobs on the initial node-a/b/f nodes, then extended to node-d/h/i with exact runtime pins, the CLI agent (0.34) wheel and context doctor checks. The subsequent v9 bundle, **006d532560dd82f9e7cb1cb937de987071c39e1c9acf1f5a3ffefc4b3b863fe6**, includes the prose-continuation guard validated by the final 89-assertion fixture. Its admitted rollout completed on all six worker node nodes: each verified 44 exact application-file pins, the reviewed the CLI agent wheel and help/version/context doctor checks, without model inference. The final v10 bundle, **a60f6d588b34540d6e5f94487c7bcfcf03ac6c55bda2852c15bd923effd3d649**, retains that same guard and changes only the discrete local builder's tool selection. It was installed on all six nodes with the same 44 application-file pins, wheel and prerequisite checks verified. The v10 native 110-case suite and two relevant actual-CLI journeys passed before rollout. The v11 bundle, **a2c28e583218e8df016ed23575f3fdc03fd267db94fdcc6c1cb9d6d863d47884**, then added the verified pre-reduction context guard and its fixture. It contains 45 allowlisted files and is 2,086,533 bytes. All six nodes completed the admitted v11 install, with 44 application-file identities, the reviewed wheel and help/version/doctor checks verified. The seven-journey 129-assertion installed-client batch passed on that exact guard before deployment. The combined v12 bundle, **81c680f8c72d741548438cb84268c03cb17a20ad04dec9b2ff4400ce2ea16afc**, contains 45 allowlisted files and is 2,093,043 bytes. It combines the clarified review evidence, discrete complete-tool instruction and final completion-boundary guard. All six nodes completed installation and verified 44 application-file identities, the reviewed wheel and help/version/doctor checks. The admitted installation took 15.402 seconds on node-i and 13.767–18.667 seconds across the other five nodes. It changed no power setting or model-service memory ceiling and made no inference call. Bundle identity binds source, not model-task acceptance. The installed-runtime fixture journeys use an actual CLI-agent executable with a fake local API, while the separately recorded Qwen task uses the real selected model.

The earlier real Qwen trials exposed integration boundaries that the focused checks now cover: native branch tracking, provider naming, Ollama context configuration, canonical metadata order, finite implementer handoff and prose-only automatic continuation. The last bounded node-f trial was cancelled with an unknown native stage in round three, after a second-round partial invalid patch, a budget handoff and fresh critic revision request. The owned workload scope was confirmed inactive and the model list empty; no accepted candidate or fresh-line handoff is claimed for that trial. A critic's incorrect mathematical explanation was treated as a model output, not proof. A subsequent v9 node-i trial also produced invalid patch attempts and yielded; it was cancelled with its exact owned scope confirmed inactive and Ollama empty. The v10 trial was then submitted by clicking the actual browser composer: one HTTP 200 acknowledgement accepted a two-line task on node-i with three explicit Qwen 4B seats, fresh-team-per-line selected and the normal working defaults enabled. The v10 build subsequently failed when its completed tool history and schemas exceeded the input bound at the next generation, instead of handing the completed work to the fresh critic. The new discrete guard correction addresses that lifecycle boundary. The next trial was submitted once through the actual browser composer on node-i using three explicit **qwen2.5:14b** seats, two fresh lines, normal working defaults and the retained baseline. The server returned HTTP 200 with a new durable task identity, rather than a duplicate submission. Its first build completed read, save and shell work, passed the six generated tests, and then yielded with exit 75 at the next generation after the 600-second elapsed boundary. The new candidate passed independent checks described below. The first critic incorrectly described unchanged interior tests as edits; its verdict was not accepted as independent evidence. A later build preserved the correct candidate and reported finished checks in prose, exposing a conflict between the implementer wrapper and native explicit completion. The operator cancelled this v11 run after retaining the candidate and evidence. The combined v12 source clarifies current diff versus historical output and explicitly instructs the discrete builder to call complete. After v12 was verified on node-i, the actual browser composer submitted the final two-line task once, receiving HTTP 200 with duplicate=false. It uses three explicit qwen2.5:14b seats and fresh teams for each line: first run the existing six tests without editing, then write the README while preserving both Python files and rerunning the tests. The first line then completed natively in round one. The coordinator started a distinct second native session in the exact same execution workspace, preserving the files while resetting all team contexts. The second line subsequently completed natively in round one as well. The accepted README was then independently inspected and applied through the normal Work route; the resulting source project passed the separate final checks described below. Observed elapsed time on the earlier CPU run does not establish that prefill, hidden reasoning or a power setting caused its speed.

The final v12 first-line receipt records native **completed**, round one, implementer **SUCCESS** with exit zero, six actual tests passing and a reviewer acceptance. The accepted baseline and HEAD are both **4655bc94509a41cfbe4a6355d2cb92fa0b22e33f**: the selected diff is empty, both Python hashes are unchanged, and README was absent at that accepted commit, matching the first line’s no-edit instruction. A metadata collector after handoff confirmed the exact first-team scope was not found/inactive/dead, its derived cgroup was absent and it owned no remaining processes. The second team started 3.915 seconds after the first step finished, with a different native identity in the same workspace. That intermediate collector correctly treated the model loaded for the active second step as expected. A later final collector separately confirmed both exact scopes and cgroups absent, no owned process IDs, and no loaded Ollama models after the durable task reached completed with no error.

The v12 second accepted commit is **a567d76d9fe8b1233bceb883c834d8e7117f22ad**. It adds only a 15-line, 412-byte README with SHA-256 **4d8adc0fe02218c630b33e15429f6fb6abff2362d68f1f5bff08e78ec76c7318**. Both Python files retain the exact hashes of the first accepted commit. The native receipt reports completed in round one, implementer SUCCESS with exit zero, six actual tests passing and reviewer acceptance. The two implementer conversation identities differ. The first step took 352.825 seconds and the second 690.877 seconds from their durable step timestamps; these are whole-step durations, including role transitions, rather than individual model-generation measurements. They demonstrate this particular two-line workflow, not a general speed comparison or arbitrary-program guarantee.

The first 14B checkpoint is **f1ed8caed23787a3d7b43e76d4898aa59ed376b0**. Its complete 947-character diff makes four targeted changes to wall-test inputs while retaining the Snake rules implementation. The coordinating operator reconstructed the exact candidate from that immutable diff into isolated private scratch, inspected the code, verified both source hashes, and ran eight methods: the six generated tests and two independent methods covering 900 movement cases plus four invalid directions. All passed in 0.090 seconds. The 1,054-byte **snake_rules.py** has SHA-256 **92c03383b348eaa3f61923b57e0c177e39df8e4f911f79541e512929dfeffbab**; the 1,429-byte **test_snake_rules.py** has SHA-256 **954385df9ffe3bea126b51e4296a7940007d90f7dc8bc5280132ca383b085e15**. No manual program repair supplied those candidate changes. Because the originating build yielded, those checks did not mark it natively completed or advance the second line. After reviewing that exact candidate, the coordinating operator separately used the normal Work/Apply route to apply the one changed test file to the owned source project. Apply neither committed nor restarted the project; all six source-project tests then passed in 0.076 seconds. This was an operator-accepted application of independently checked model work, not a native team acceptance. The subsequent successful v12 native two-line trial started from that retained baseline and is accounted for separately above.

The finished example is available at **~/symblicos/projects/symblic-qwen-demo-20261006** on the host. It contains **snake_rules.py**, **test_snake_rules.py** and the accepted **README.md**. The pure Python `move_head(head, direction, width, height)` function moves one grid cell for up/down/left/right, returns None on a wall collision and raises ValueError for an unknown direction. For example, moving right from (2, 2) on a 5×5 grid returns (3, 2). This constructed artifact demonstrates a small rules module, its tests and documentation.

The operator inspected the final Work diff and the README’s 65 whitespace-separated words, including its example and test command. Normal Work/Apply added only README to that source project, without creating a commit or restarting anything. The 412-byte README hash matched the accepted native commit, and both Python file hashes remained unchanged. Isolated system Python then passed eight methods against the applied source: six generated tests and two independent methods covering 900 moves plus four invalid directions. The measured wall time was 0.116 seconds, with 0.016 seconds reported by the unittest runner. The additional independent methods remain verification evidence; the project’s six included tests can be rerun from its directory:

```bash
cd ~/symblicos/projects/symblic-qwen-demo-20261006
python3 -m unittest -v test_snake_rules.py
```

node-i also received the already-established **qwen2.5:14b** model with immutable digest **7cdf5a0187d5c58cc5d369b255592f7841d1c4696d45a8c8a9489440385b22f6**, matching the existing the host asset. The native metadata reports 8,988,124,069 bytes, Q4_K_M quantization, 14.8B parameters, tool capability and a 32,768-token source context. The managed coding alias still uses the admitted 8,192 context. The node had 28.630 GiB available RAM and a 26 GiB Ollama ceiling at the check; the existing admission estimate was 13.722 GiB. The pull took 222.596 seconds, preserved all five prior base tags and left no loaded model. These are inventory/capacity observations before the live trial, not quality results or permanent free-memory guarantees.

A short metadata sample during the 14B run distinguished model residence from full service accounting. All memory units below are binary GiB; values are rounded, and the observations apply to that sample only.

| Measured quantity | Observation | Scope |
| --- | --- | --- |
| Admission estimate at 8,192 context tokens | 13.7217 GiB | Predicted placement requirement, not measured model residence |
| Ollama model residence from /api/ps | 10.1178 GiB | The CPU-only model reported by the service |
| Complete Ollama service cgroup | 25.9814 GiB of a 26 GiB ceiling | Includes anonymous memory, file cache and other service accounting |
| Anonymous memory | 10.1973 GiB | One component of the cgroup total |
| File cache | 15.5471 GiB, including 13.8930 GiB inactive file pages | Inactive pages are a subset, not an additional allocation |
| CPU sample | Approximately 800% across a one-second sample | Aggregate CPU use, not measured application throughput |
| Follow-up pressure sample | 2.0008 seconds; zero new OOM, OOM-kill or max-limit events; zero swap | Reported pressure averages were 0.00; this short window does not establish the complete run's resource behavior |

The recorded ten-minute the temporary high-power mode lease used during the earlier live work expired or was restored, and all eight eligible physical nodes returned to their recorded non-boosted state. There was no active boost at that verification point. Sampling different CPU frequencies before and during the lease does not establish a performance benefit; node placement, capacity admission and subsequent acceptance evidence are recorded independently.

The live Cloud task initially returned a greeting module and two tests. A follow-up added an empty-name case. The watcher finished only after the new message ID was reported, and the second verified patch contained the third test. The cloud-side report says all three passed. A separate local replay passed all three returned tests under Python 3.12.3 in private scratch; the table records it independently.

The acceptance CLI formerly risked presenting fixture operations as a broad live success. It now runs its twenty-one checks in a temporary root and labels that scope. Release manifests are pure evidence summaries: absent or malformed evidence remains unverified, fixture checks establish component-tested status only, and assertions alone cannot declare a booted OS, physical hardware measurement, real model execution or full framework integration verified.

Final verification should record the exact failed/passed module counts, any repaired failures and rerun scope, the loaded dashboard process, the actual selected node, task IDs or safe artifact identifiers, and cleanup of temporary workloads. Private logs remain private. This chapter can be updated with concise receipts without copying account URLs, credentials, raw conversations or personal data.

## 22. Operational boundaries and future work

SymblicOS currently means a hosted Linux workspace and orchestration surface. The current work does not build or boot a standalone operating system. The shell, file tools and native agent workspaces run on existing computers with their existing kernels, services, identities and admission controls.

The ordinary-English composer is a tool-agent interface. Its success depends on the selected engine, available tools, task clarity and observed execution. The checked English compiler covers a specified grammar. Keeping these routes visible gives the operator both broad expressiveness and precise bounded semantics without claiming that arbitrary prose is automatically a proof.

Fresh context limits conversational accumulation but does not erase code defects, bad specifications or unsafe dependencies already present in files. A good step must carry enough explicit context to finish its objective, and later checks must examine the assembled program. Excessive decomposition can also cost time and lose necessary relationships. Measure task completion, calls, wall time and independent acceptance together.

Native cloud attachment is account-controlled. The repaired console supplies useful durable prompting and result collection now, while preserving the provider URL when native attachment is refused. It does not emulate permissions, invent an answer stream or treat local detachment as cloud cancellation.

Cluster breadth is conditional on actual node readiness. Installed source, a model tag and sufficient host RAM are separate facts. Admission also checks the service memory ceiling and active work. Browser accounts stay with their node. A power fence or guest isolation boundary is not a temporary inconvenience to bypass. Unknown liveness retains reservations because work may still be running.

The next useful improvements should follow observed friction: expand checked authoring forms with executable conformance cases; add more engine-specific native completion evidence; measure matched Qwen-team and single-agent tasks; improve contracts that reject real defects; and evaluate retrieval and distillation on frozen independent sets. New adapters should state what they read, what they can change, how they recover and what their tests establish.

The practical goal is already concrete: type an objective, select the worker and computer, retain the work and inspect the result. The framework's long-term value comes from making that path reliable and understandable while preserving exact checks where exact checks are possible.

## 23. Complete documentation catalogue

This catalogue covers every public Markdown document under docs/reference other than this book at the time of assembly. It includes current contracts, guides, measured evidence, examples and historical analysis. A title is not a verification claim. Prefer the current specification, terminal guide and dated receipts when a historical narrative differs from running code.

The original host also had its own guides (agent operation, power management, its task executor and subsystem contracts); they are not part of this repository.

**Catalogue size:** 101 documents, plus this book.

| Path | Document title |
| --- | --- |
| [AGENT-CARD.md](AGENT-CARD.md) | Use Symblic from another agent |
| [AGENT-DELEGATION.md](AGENT-DELEGATION.md) | Reusable delegation contracts |
| [AGENT-GRAPHS.md](AGENT-GRAPHS.md) | Contracted agent graphs: planner, durable runtime and operator interface |
| [AMBIGUITY-BENCH.md](AMBIGUITY-BENCH.md) | Ambiguous-request benchmark |
| [AUTHORING-GRAMMAR.md](AUTHORING-GRAMMAR.md) | Write Symblic with the installed parser contract |
| [COMPACT-CAPSULES.md](COMPACT-CAPSULES.md) | Optional compact capsule annotations |
| [CONSTRUCTOR-CLI.md](CONSTRUCTOR-CLI.md) | Optional constructor from the native CLI |
| [CONSTRUCTOR-LOCKS.md](CONSTRUCTOR-LOCKS.md) | Constructor records and portable locks |
| [CONSTRUCTOR-PROVISIONING.md](CONSTRUCTOR-PROVISIONING.md) | Provision the optional linear constructor |
| [CONSTRUCTORS.md](CONSTRUCTORS.md) | Optional checked constructors |
| [CONTEXT-EXPERIMENTS.md](CONTEXT-EXPERIMENTS.md) | Source-linked context experiments |
| [CRITIQUE-AND-LIMITATIONS.md](CRITIQUE-AND-LIMITATIONS.md) | Critical review of Symblic's contracts and usefulness |
| [DEVELOPMENT-AND-USE-CASES.md](DEVELOPMENT-AND-USE-CASES.md) | Symblic development roadmap and application candidates |
| [DIFFERENTIAL-SPECS.md](DIFFERENTIAL-SPECS.md) | Differential questions for code specifications |
| [DISCRETE.md](DISCRETE.md) | Exact ground states of a small Ising model |
| [DISTILLATION.md](DISTILLATION.md) | Symblic distillation (SFT/LoRA), version 1 |
| [DOCUMENTATION-CONFORMANCE.md](DOCUMENTATION-CONFORMANCE.md) | Documentation conformance inventory |
| [EDITOR.md](EDITOR.md) | Underlines and your instruction circuit |
| [EFFECTS.md](EFFECTS.md) | Symblic effects — `observe` and `act` |
| [ENGLISH-STATEMENTS.md](ENGLISH-STATEMENTS.md) | English statements (`symblic.english.compiler`, version `symblic-english/1`) |
| [EPISTEMIC-IMPROVEMENTS.md](EPISTEMIC-IMPROVEMENTS.md) | Improving Symblic via Intersubjectivity: Epistemic Types, Multi-Frame Verification, and Theory of Mind in Language Design |
| [EPISTEMIC-MEMORY.md](EPISTEMIC-MEMORY.md) | Durable epistemic notebooks |
| [EVIDENCE.md](EVIDENCE.md) | Symblic evidence and assurance |
| [EXECUTION-PINS.md](EXECUTION-PINS.md) | Execution pins (receipt version 2) |
| [EXPENSE-HANDOFF.md](EXPENSE-HANDOFF.md) | A source-bound expense handoff between agents |
| [EXPERIMENTS.md](EXPERIMENTS.md) | Executable research mechanisms |
| [FINITE-LOGIC.md](FINITE-LOGIC.md) | Explicit finite-domain logic, version 1 |
| FINITE-TRANSPORT-EXPERIMENTS.md (not included in this repository) | Finite sheaf and schema transport experiments |
| [GRAND-UNIFICATION-AND-STRING-THEORY.md](GRAND-UNIFICATION-AND-STRING-THEORY.md) | Mathematical research for Symblic: constructions, hypotheses and tests |
| [GRAPH-COMPOSITION.md](GRAPH-COMPOSITION.md) | Reusable graph fragments |
| [HPC-FOUNDATIONS.md](HPC-FOUNDATIONS.md) | Symblic on high-performance computing (HPC): proposals and status |
| [INCREMENTAL-PROOFS.md](INCREMENTAL-PROOFS.md) | Incremental proof sessions: one inference per fresh context |
| [INQUIRY.md](INQUIRY.md) | Choosing the next evidence method |
| [INTENSE-CRITIQUE-AND-LIMITATIONS.md](INTENSE-CRITIQUE-AND-LIMITATIONS.md) | Symblic: critical review, counterexamples and unresolved limits |
| [INTERPRETER.md](INTERPRETER.md) | From an idea to a checked program |
| [INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md](INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md) | Symblic and Human Intersubjectivity: Formalizing Empathy, Bridging Perceptual Chasms, and the Architecture of Unified Communication |
| [JS-CONTRACTS.md](JS-CONTRACTS.md) | Optional JavaScript declaration contracts |
| [JS.md](JS.md) | JavaScript checks (`js_test`, `js_run`) |
| [KNOWLEDGE.md](KNOWLEDGE.md) | Knowledge on a finite set of states |
| [LANGUAGE-3.md](LANGUAGE-3.md) | Symblic: the abstraction layer (functions, routines, modules, tests, papers, locks) |
| [LOCAL-ROUTING.md](LOCAL-ROUTING.md) | Local model routing for delegated templates |
| [MATCHED-EVALUATION.md](MATCHED-EVALUATION.md) | Matched evaluation protocol |
| [NATURAL-LANGUAGE-BRIDGE.md](NATURAL-LANGUAGE-BRIDGE.md) | From human statements to checked Symblic programs |
| [NOTES-2026-10-02.md](NOTES-2026-10-02.md) | Symblic: prompts, discoveries and answers (2026-10-02 → 2026-10-03) |
| [OPERATORS.md](OPERATORS.md) | Exact finite operators and question order |
| [PHYSICS-AND-ADVANCED-MATHEMATICS.md](PHYSICS-AND-ADVANCED-MATHEMATICS.md) | Modern Mathematical Physics and Symblic: The 2026 Navier-Stokes Announcement and Five Proposed Borrowings |
| [POLICY-EXPERIMENTS.md](POLICY-EXPERIMENTS.md) | Durable finite policy experiments |
| [POLICY-LEARNING.md](POLICY-LEARNING.md) | Bounded finite-candidate policy selection, version 1 |
| [PORTABLE-FINITE.md](PORTABLE-FINITE.md) | Portable verified programs, format 2 |
| [PRIOR-ART.md](PRIOR-ART.md) | Symblic: prior-art survey and research scope |
| [PROJECTION.md](PROJECTION.md) | Exact adjustment to affine constraints |
| [PROOF-COMMANDS.md](PROOF-COMMANDS.md) | One command per proof inference |
| [PROOF-FOCUS-DELEGATION.md](PROOF-FOCUS-DELEGATION.md) | A focused context for one caller-owned proof obligation |
| [PROOF-OBLIGATION-DELEGATION.md](PROOF-OBLIGATION-DELEGATION.md) | Exact intermediate obligations for fresh proof children |
| [PROOF-STEP-DELEGATION.md](PROOF-STEP-DELEGATION.md) | One checked proof step per delegated child |
| [PROOF-STEPS.md](PROOF-STEPS.md) | Flat natural-deduction proof certificates |
| [PROOF-TASK-CARD.md](PROOF-TASK-CARD.md) | One exact proof obligation as a numbered task card |
| [PROOF-TERMS.md](PROOF-TERMS.md) | Proof terms, version 1 — integrated 2.5 interface |
| [PROTOCOL-EXPERIMENTS.md](PROTOCOL-EXPERIMENTS.md) | Finite protocol replay and compensation planning |
| [QUANTITIES.md](QUANTITIES.md) | Exact quantities and measurement intervals |
| [QUANTUM-DETERMINISM-ANALYSIS.md](QUANTUM-DETERMINISM-ANALYSIS.md) | Quantum Mechanics and Computational Determinism: Does Quantum Mathematics Weaken or Strengthen Symblic's Invariants? |
| [QUANTUM-FOUNDATIONS-OF-SYMBLIC.md](QUANTUM-FOUNDATIONS-OF-SYMBLIC.md) | Quantum Mathematical Foundations for Neuro-Symbolic Computation: Applying Quantum Mechanics to Symblic |
| [REFORM-3.md](REFORM-3.md) | Symblic reform: executable statements, conditional evidence and agent networks |
| REQUIREMENT-EXECUTION.md (not included in this repository) | Observed requirement checks |
| [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md) | Research adoption for Symblic |
| [RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md) | Symblic: getting different LLMs to give the same answer |
| [RESEARCH-GEOMETRY.md](RESEARCH-GEOMETRY.md) | Supplied geometry experiments, version 1 |
| [RESEARCH-LANGUAGE.md](RESEARCH-LANGUAGE.md) | Symblic: can a formal description force the same result from any reader? |
| [RESEARCH-TRANSFER.md](RESEARCH-TRANSFER.md) | Research transfer: fresh-context construction and the cognitive fabric |
| [RESULTS.md](RESULTS.md) | Symblic — measured results and their scope |
| [REVIEW-2.3.md](REVIEW-2.3.md) | What the review documents proposed, and what Symblic 2.3 does with it |
| [SOLVER-PROVENANCE.md](SOLVER-PROVENANCE.md) | Solver proposal provenance |
| [SOURCE-WITNESSES.md](SOURCE-WITNESSES.md) | Source witnesses in ordinary Symblic |
| [SPEC-SHEETS.md](SPEC-SHEETS.md) | Spec sheets: building a file from small checked units |
| [SPEC.md](SPEC.md) | Symblic 2.5 — specification |
| [START-HERE.md](START-HERE.md) | Start using Symblic |
| [STEPS-EVIDENCE.md](STEPS-EVIDENCE.md) | What the small-model construction test achieved |
| [STEPS.md](STEPS.md) | Build one checked step at a time |
| [STUDY-GUIDE.md](STUDY-GUIDE.md) | Symblic study guide and executable tutorial |
| [SUPERVISOR.md](SUPERVISOR.md) | Durable Symblic workflows |
| [SYMBLIC-BREAKTHROUGH-COMPENDIUM.md](SYMBLIC-BREAKTHROUGH-COMPENDIUM.md) | Symblic: Architectural Compendium |
| [SYMBLIC-COMPLETE-MASTER-RECORD.md](SYMBLIC-COMPLETE-MASTER-RECORD.md) | Symblic: The Complete Master Record & Technical Compendium |
| [SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md](SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md) | Symblic: Systems, Hardware & Offensive Security Deep Dive |
| [SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md](SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md) | Symblic: Token Economics, Neuro-Symbolic Architecture & Agent Ergonomics |
| [TASK-CARDS.md](TASK-CARDS.md) | Task cards and portable builds |
| [TERMINAL.md](TERMINAL.md) | Symblic Terminal |
| [THE-OVERALL-BREAKTHROUGH.md](THE-OVERALL-BREAKTHROUGH.md) | Symblic's architectural thesis and the evidence it needs |
| [TRANSPORT.md](TRANSPORT.md) | Exact finite one-dimensional transport |
| [VARIATIONAL.md](VARIATIONAL.md) | Exact finite quadratic minimization |
| [VORTICITY-CONSTRUCTION.md](VORTICITY-CONSTRUCTION.md) | Constructing a finite energy witness |
| [WORKCARDS.md](WORKCARDS.md) | Typed workcards and reviewer roles |
| benchmarks/AMBIGUITY-DATA.md (not included in this repository) | Finite operator-intent dataset, version 1 |
| [examples/agent-handoff.sheet.md](../../examples/agent-handoff.sheet.md) | handoff.js |
| [examples/tetris.sheet.md](../../kits/tetris/sheets/tetris.sheet.md) | tetris.html |
| [grammar/README.md](grammar/README.md) | Authoring contract 1 |
| [papers/README.md](papers/README.md) | Writing a paper that reproduces |
| [reinforcements/benchmark-review.md](reinforcements/benchmark-review.md) | Benchmark statistics reinforcement: bounded first pass |
| [reinforcements/communication-review.md](reinforcements/communication-review.md) | Symblic spec self-sufficiency replication |
| [reinforcements/contract-audit.md](reinforcements/contract-audit.md) | Symblic contract audit: bounded offline reinforcement |
| [reinforcements/cube-protocol.md](reinforcements/cube-protocol.md) | Cube reconstruction protocol: exact shape, placement, and agreement |
| [reinforcements/semantics-review.md](reinforcements/semantics-review.md) | Symblic semantics review: compiler-design pass |

Non-Markdown companions include native examples under examples/, grammar and parser resources, crystals, machine-readable claims/documentation cases, and scoped JSON evidence under evidence/. Follow the containing guide for their schema and intended checks; a data file is not a separate live verification.

## 24. Addendum — 7 October 2026: Forge

This addendum continues the 6 October record without replacing its language, Terminal, agent or cluster contracts. The next requested work added a separate requirements application from `idesign1.txt` through `idesign5.txt` (Forge), alongside two other website capabilities of the original host that are not described here. They are connected website capabilities with separate authority and execution boundaries.

The detailed guides are [Symblic Forge](FORGE.md) and the [154-unit Forge acceptance map](FORGE-ACCEPTANCE.md). The [7 October release evidence](2026-10-07-forge-integrations-evidence.json) is the final source for exact release hashes, test receipts and subsequent live status. Counts and observations below describe their stated checkpoints; overlapping regression suites must not be added together as independent cases.

### 24.1 The new workflow and its boundaries

| Workspace | What the operator does | What the result establishes |
| --- | --- | --- |
| `/symblic-forge` | Refine an idea, explicitly accept decisions, link engineering records, validate and freeze a handoff | A reviewed specification and retained instruction artifacts; no project execution |
| `/symblic-terminal` | Deliberately submit a selected-agent task or fresh-context sequence | The execution receipts described in the original chapters |

Forge does not silently start Terminal agents, CAD, Python jobs or infrastructure. A model proposal is not an accepted requirement; an accepted requirement is not an implementation; compiler validity is not application correctness. The operator chooses when to cross each boundary.

### 24.2 Forge: from original intention to accepted decisions

The five design inputs comprise 2,148 lines and 96,637 bytes. Their 154 named construction units are mapped to code and checks in the acceptance guide. They specified a separate requirements and ideation application, rather than another automatically executing chat box. The application preserves the original idea, including its spacing and line breaks, while progressively making decisions explicit.

A normal start is:

1. Open `/symblic-forge`, enter an intention and press Enter. Shift+Enter inserts a newline.
2. Answer the current bounded question, edit a suggested answer or defer the decision.
3. Review the resulting atomic proposals. **Accept statement** makes a statement authoritative; accepting a suggested answer first records an answer and creates proposals.
4. Open **Specification & engineering workspace** to connect requirements to objectives, criteria, architecture, components and isolated construction units.
5. Resolve readiness blockers, check generated native source, inspect exports and explicitly **Freeze build handoff** when ready.

Normal new projects have no accepted defaults. In particular, a new Snake idea does not silently acquire a renderer, board size, rules or implementation language. **Project… → Load Snake demonstration** instead creates a separate, labelled example with recorded choices, 29 accepted decisions and three construction units. It does not implement a game or overwrite the current project.

The interface supports five refinement modes:

| Mode | Decision behavior |
| --- | --- |
| DEEP | One independent consequential decision at a time |
| RAPID | Up to five independent questions |
| EXPLORE | Up to three explicit alternatives |
| PRECISION | Quantities, units, tolerances, interfaces and observable checks |
| CHALLENGE | Contradictions and challenges to accepted choices |

Focus, Overview, Skip animation and Clear transcript change presentation, not project authority. Complete stored text is immediately available to assistive technology and exports; animation does not control whether a decision exists. Reduced motion, phone layouts, visible keyboard focus and inputs of at least 16px are supported. Ctrl/Cmd+K opens the command palette; Alt+Up/Down selects suggestions, Alt+A accepts a highlighted suggestion and Alt+D defers the current question. These suggestion controls do not bypass statement acceptance.

Records use stable IDs, never display positions. Requirements, answers, questions, engineering entities and evidence retain source links and revisions. **Originating decisions** follows provenance; **Inspect** exposes the complete record. Operator originals, answers, model suggestions, deterministic consequences, imported material and compiler information remain distinguishable.

Editing accepted text returns the changed version to proposal review. A proposed replacement preserves the existing requirement until its own explicit acceptance. Removed records retain history. Assumptions remain quarantined, parking-lot material stays outside the accepted specification, and promotion creates a proposal. Scope has separate in-scope, out-of-scope and undecided collections; definitions and aliases preserve the operator's terminology.

Snapshots capture branch states without recursively copying older snapshots. Restore first saves a safety snapshot. Branch comparison is symmetric, and selected merges enter the destination as proposals. Undo and redo append recorded transitions rather than erasing history; a divergent edit clears redo. Previously frozen handoffs remain historical artifacts after later changes.

### 24.3 Engineering structure, quantities and controlled model assistance

Forge's engineering records cover objectives and their hierarchy; observable criteria; architecture candidates; components with responsibilities, inputs, outputs, state and effects; isolated units with dependencies, checks, paths and forbidden assumptions; agent permission plans; exact model policies; cluster placement/resource plans; invariants; negative checks; and evidence.

Domain coverage includes web applications, games, agents, clusters, operating systems, science, hardware and research, with additional classification for desktop, CLI, embedded, robotics, electronics, mechanical and data work. Templates activate relevant questions rather than inventing facts. A dimension can be declared not applicable only with an explicit reason.

Derived checks identify declared graph cycles, missing inputs, dependencies and checks, orphaned requirements/components, incompatible structured decisions and resource quantities with units. Memory, storage and concurrency remain numeric in the UI; structured inventory JSON survives editing. Cached discovery is incomplete evidence. Only a suitably explicit, complete accepted inventory supports a claim that a needed resource is absent.

These checks do not prove arbitrary prose equivalent, establish physical feasibility or discover every possible dependency. Model criticism and operator review remain necessary for issues beyond the structured rules. Readiness combines blockers and accepted engineering structure; a colour or score cannot override unresolved mandatory work. Lifecycle labels, including EXECUTION_TRANSFERRED, are not execution proof.

The optional model roles are **IDEATOR**, **QUESTIONER**, **CRITIC** and **SPECIFIER**. The picker uses the existing provider registry and exact node-specific applicators, such as `ollama:qwen3:4b-instruct@node-f`. Cloud, CLI and web selections require the role's explicit remote-context setting. Native calls use the existing admitted Symblic/the fleet runner path with tools disabled.

A request freezes its role, app, optional ordered fallbacks, revision, branch, semantic fingerprint, context hash and private validation snapshot. It sends selected project context rather than a cumulative brainstorming history; the critic does not receive the full transcript. Attached private files and retained validation snapshots are not automatically sent to models. Up to three distinct selected models may provide independent proposals; agreement does not vote a requirement into acceptance.

Results must satisfy bounded structured JSON contracts. Invented IDs, hidden-reasoning fields, invalid entities and unauthorized authority fields are refused. An old-revision result remains inspectable but cannot be adopted into a changed branch. Importing valid output creates proposals only. Optional improvement, simplification, normalization and compiler-repair proposals retain source mappings and before/after review. Repair previews bind to the exact source hash, diagnostic and Unicode code-point range; preview neither accepts the change nor executes it.

There are at most three queued, running or unknown proposal requests. Dispatch intent is durable before the worker acts; a worker claims a queued request once. Reload and polling read existing state. Unknown delivery is not automatically repeated. Stop targets the exact owned orchestration service.

### 24.4 Forge exports, commands and recovery

| Export | Intended use |
| --- | --- |
| `manifest` | Complete schema, accepted/proposed state, history, branches, snapshots and fingerprint |
| `brief` | Human-readable accepted design and remaining work |
| `prompt` | Accepted requirements without proposal/history material |
| `construction` | Bounded human instructions ending in `Finish this step.` |
| `tasks` | Dependency-aware task cards with inputs, outputs, checks, criteria and constraints |
| `sheet` | Structured accepted specification; distinct from the historical Markdown JS-sheet grammar |
| `symblic` | Actual current native syntax checked by the installed parser/compiler |

Accepted paths and declared/required symbols survive task cards, sheets, human construction instructions and native ask capsules exactly. JSON-quoted construction labels preserve embedded quotes and newlines as data; no path is opened or executed by export. Native export uses exact literal bindings and Text asks with explicit dependencies under `profile=verified, context=none, determine=false, solve=false`. Prose checks remain instructions, not fabricated executable predicates. Source mapping connects diagnostics to requirement and unit IDs. Checking arbitrary editor text is separate from validating the generated accepted project.

Artifacts retain exact bytes, SHA-256, source revision and semantic fingerprint. Reads verify artifact integrity. Compiler receipts record actual compiler/source identity. Loaded exporter/compiler hashes are distinguished from disk hashes; changed code requires the normal dashboard restart before new validation can receive a current receipt. Invalid native source cannot receive a valid export badge, and imported historical metadata cannot grant current compiler or handoff authority.

**Freeze build handoff** requires structural readiness and a new current-compiler check. One transaction saves the immutable manifest, native source, task cards, sheet, construction plan and handoff receipt. The receipt explicitly records `execution_started: false`. Later edits require fresh validation without deleting the earlier handoff.

Useful command families are:

- Inspect: `/status`, `/spec`, `/proposed`, `/questions`, `/conflicts`, `/assumptions`, `/completeness`, `/history`, `/search`, `/source`, `/exports`, `/jobs`.
- Engineer: `/objectives`, `/architecture`, `/components`, `/units`, `the agent hub`, `/models`, `/cluster`, `/tests`, `/invariants`, `/forbidden`, `/evidence`, `/scope`, `/parked`, `/vocabulary`.
- Refine: `/idea TEXT`, `/park TEXT`, `/accept ID`, `/reject ID`, `/question ID`, `/defer ID`, `/mode DEEP`, `/model QUESTIONER`.
- Preserve and hand off: `/snapshot NAME`, `/branch NAME`, `/compare FIRST SECOND`, `/undo`, `/redo`, `/recover`, `/validate`, `/validate SOURCE`, `/export FORMAT`.

The guide includes the full palette and presentation commands. `/validate` does not execute native asks, and `/export` does not launch a build.

Private state lives in `symblic_forge_data/forge.sqlite3`, with an isolated-environment override. SQLite WAL, FULL synchronization, revision compare-and-swap and transactions retain projects, append-only events, HTTP intents/outcomes, model jobs and artifact bytes. Worker imports are inert, and all `/api/symblic-forge/` routes require the operator gate.

Every mutation carries a stable action ID; project changes also carry the displayed revision. An identical confirmed request returns its existing outcome. Reusing its ID with different content or a different action envelope is refused. Recovery reads retained receipts. If an action never reached the server, an explicit same-ID retry is available only after a missing receipt is established; ambiguous delivery is not silently resent. Conflicting tabs must reload. Recovery and Stop use conditional state transitions so they cannot overwrite a concurrent completed worker result. Browser persistence failures release the busy state and show the problem.

Uploads are bounded inert TXT/JSON/CSV or signature-checked PDF/PNG/JPEG; active HTML/SVG is refused. User text is rendered as text, not evaluated markup. Attachments remain private. The implementation declares request, attachment, collection and selected-context limits; these are not token counts or claims about a model's context capacity. Refinement itself has no arbitrary conversation-round cutoff.

### 24.5 Forge verification and actual use

Forge verification includes **118 distinct unit methods and three integration tests in one passing 121-test run (33.662 seconds)**, plus **ten passing browser tests (55.906 seconds)**. A subsequent focused browser check clicked all seven export formats, verified downloaded bytes against retained hashes, and froze the handoff (37.843 seconds). The final audit found and repaired missing unit paths and symbol contracts in exported instructions. **19 export methods passed in 7.793 seconds**, including the new literal-data regression, and **29 API/integration methods passed in 13.080 seconds**. The seven-download/frozen-handoff browser journey passed again in **13.456 seconds**. These overlapping runs cover **122 distinct methods** in total. The core suite additionally exercised 39 subtests. These counts do not add overlapping earlier passes. Offline tests isolate stores and fake models, workers, nodes and external services; compiler checks use the actual pure native parser/checker without executing asks. Browser journeys use real page assets with a temporary API/core fixture and cover authority, editing, provenance, recovery, history, compiler checks, engineering forms, numeric resources, structured inventory, model nonreplay, explicit Stop, uploads, mobile behavior, reduced motion and hostile text rendered as data.

Ordinary explicit pixel answers now follow the same quantity path as the example: `eight hundred pixels` and `600 pixels` preserve their exact text, become typed proposed facts, and derive **480,000 px² only after separate acceptance**. Ambiguous or unsupported quantities remain unnormalized. Accepted prompt, task, construction and native exports retain fact labels/units alongside the original text, so a short answer keeps its width or height meaning. This ordinary flow was checked in the real website, compiled and reloaded with the same accepted prompt hash. Its incomplete overall design remained structurally unready despite valid native syntax. The final live API check explicitly edited and accepted `snake/src/state.js` in the retained Snake demonstration. It revalidated with the updated exporter and froze a new handoff at source revision **15**, leaving project revision **16** and preserving both earlier handoffs. All five retained artifact hashes matched their retrieved bytes; the accepted path and required/defined symbols survived the instruction exports. A subsequent read restored the same handoff. The ordinary-answer project was also revalidated at revision **11**; its generated source hash stayed unchanged.

Separately, a live request selected **`qwen3:4b-instruct@node-f`** through the admitted provider path. It completed in **36.5 seconds** with schema-valid proposals. Those proposals were imported as proposed records; no requirement was automatically accepted and no project was implemented by that call.

The live labelled Snake demonstration also exercised a deliberately accepted conflict and the **Keep First** resolution. Its resulting state had **29 accepted requirements, zero conflicts and three isolated construction units**. The initial UI journey generated native source, validated it, froze a five-artifact handoff, downloaded and hash-verified every artifact, then checked snapshot/reload recovery at revision 8. After the final quantity/export fixes and restart, a second handoff froze source revision 9; snapshot/reload confirmed project revision 11, preserving both handoffs. All five new artifact downloads matched their retained hashes. The native kernel was `7bf8c94958d86fc7`, with all seven current loaded compiler/export source identities matching disk. The frozen receipt still recorded `execution_started: false`. These observations establish the recorded design, compiler, artifact and recovery workflow; they do not claim that the demonstration generated or ran Snake.

The focused task checks are not a whole-checkout green claim. Broader checks encountered unrelated failures in the shared working tree; the release evidence records their scope and the focused registration/private-route/backup checks separately. Those results must not be concealed by adding successful counts together.

### 24.6 to 24.8 (removed)

*Removed for publication (24.6 to 24.8).* These subsections described two other applications of the original host (a CAD model integration and a self-hosted compute runtime) that are not part of Symblic or of this repository.

### 24.9 How this extends the original Symblic work

The final coordinated dashboard restart changed the process id and returned HTTP 200 for all six checked website surfaces. Forge's loaded compiler/source identities matched disk after that restart. HTTP reachability is recorded separately from the model, geometry and native-job outcomes above.

The original language and Terminal work sought explicit objectives, bounded context and deliberate execution through selected agents. Forge supplies the earlier phase: preserving an idea, resolving decisions, recording acceptance and creating auditable isolated work instructions. 
Together they make more of the website usable without merging every operation into one unbounded conversation. The original compiler, fresh-line execution, provider identity, workspace isolation and stop/recovery contracts remain in force. Future work can add stronger semantic analysis and further integrations, but those capabilities must earn their own source, test and live evidence. None is implied by an installation, a proposal, a valid syntax receipt or the success of a different example.


## 25. Configurable teams and focused authoring — 2026-10-07 follow-up

This section records the operator's subsequent correction: three Qwen workers were an example of collaboration, not a fixed product limit. Forge and the English editor now use a shared configurable team contract. The focused interface keeps the common writing action visible and puts detailed choices in expandable controls. Earlier dated receipts remain historical; the new agent-control evidence (not included in this repository) distinguishes the additional implementation, isolated verification and live observations.

### 25.1 One English editor and retained tools

The initial language page opens English. The header exposes English, Native and Runs; the expandable searchable tool list retains all 19 existing views and their deep links. Examples, statement-worker limits and the instruction circuit are collapsed. The same instruction field supports checked statements and project-agent tasks. These workflows have different execution contracts, but no longer require separate competing English text boxes. Draft and pending-intent recovery retain exact text across the language page and Terminal. A pending request locks source, workflow and team until reconciliation; reload does not dispatch again.

**Agents** lives inside English statements. Expand it to enable an explicit team, set its size and edit each row. Disabling the explicit team preserves native per-statement `by` choices and saved older drafts. A server without the versioned team capability refuses the new selection visibly rather than silently running the old default. Check, preview, Run and retry retain the same team alongside the exact source. Native source mapping and authoring receipts include that sidecar selection. The complete legacy native/provider picker and project aggregate workflows remain accessible.

The page retains the existing theme, keyboard navigation, touch targets and 16-pixel input minimum. Disclosure states survive immediate selection changes; stale detached toggle events cannot collapse the replacement row. Team labels use text nodes, including operator-written characteristics. User text never becomes markup.

### 25.2 Exact team contract

A version-1 team contains **1–24 members**. This is a visible request bound, not a fixed collaboration preset or a physical concurrency claim. Each member has a unique stable identity, even when several use the same model. Add, duplicate, remove, reorder or set the count. Increasing the count copies the last row with new identities; subsequent edits can mix any supported individual providers and registered devices.

The retained fields are `id`, `engine`, `model`, `node`, `effort`, `role`, `characteristics`, `instruction`, `settings` and `weight`. Engine aliases normalize `local` to `ollama` and `gpt` to `chatgpt`. Devices are exact registered IDs, never an implicit `auto` or all-workers pool. Ollama requires an exact model; an empty model for a supported cloud/browser provider explicitly requests its default. Cached inventory is advisory; actual dispatch checks readiness, capacity and fences again. The system does not silently choose another device or model.

Role is bounded to 160 characters, characteristics to 2,000, member instructions to 6,000 and model IDs to 160. Unknown keys, invalid IDs, nonfinite numbers and unsupported settings refuse. Checked/proposal Ollama calls support temperature 0–2 and integer seed 0–2,147,483,647. Effort options are the intersection of the actual adapter and selected model, refreshed as the model field changes. Project coding sessions have their own real effort catalogue and do not implement temperature/seed. Checked vote weights range from 0.1 to 10; project teams refuse a nondefault weight because sequential coding sessions do not vote. Forge displays its weight as checked-statement metadata, not automatic acceptance authority.

Malformed intermediate numeric input, such as typing `1e`, remains invalid. The browser's empty string for that incomplete exponent must not be mistaken for an instruction to remove an override. The shared editor blocks submission until the field is completed or explicitly cleared, including across a row redraw.

Individual adapters cover Ollama, Claude Code, Codex, Antigravity, Copilot CLI, ChatGPT web and Gemini web subject to installed runtime and account readiness. The three-agent pipeline, councils and squads retain their native project controls. A composite agent is not falsely advertised as an ordinary typed-return seat when its nested membership or tools cannot meet that contract. Catalogue visibility, installation, sign-in and a successful task are distinct facts.

### 25.3 Checked statements, fresh contexts and recovery

An explicit checked team lowers into existing native applicators and search/group controls. Existing types, declared dependencies, retries, voting and checks remain authoritative. The original source is preserved. A source-level explicit selection cannot be silently replaced. Profiles are supplied as operator-selected role data before capsule accounting and cache hashing; they cannot replace the objective, type/schema, selected context or checks. Every statement starts fresh member requests. Only explicitly declared dependencies carry forward.

The existing checked-winner search rule can stop unnecessary later candidates. Selecting five members therefore configures five candidates; it does not promise all five are called after an earlier candidate has already satisfied that rule. Repeated models and agreeing answers do not establish statistical independence or correctness. Preview identifies the first member and explains that execution uses the configured team.

Member identity, profile digest and exact request context appear in evidence. Profiled provider dispatch persists its intent before the external call and retains the outcome after the durable call record. An ambiguous or missing established outcome cannot be automatically replayed; an exact accepted cached result can be reused. English retry keeps the exact source and team. Kernel identity and required execution-source pins include the shared team helper, preventing an old semantic identity from silently resuming under new profile behavior. Finite temperatures/weights in CLI run metadata are supported without relaxing the separate exact editor-authoring JSON grammar.

### 25.4 Project teams and devices

`POST /api/symblicos/tasks` accepts `mode: "team"`, the versioned team, the shared instruction, workspace and existing automatic/worktree/context options. With fresh-line execution selected, each nonblank instruction line is a separate task context for each selected member. Otherwise the full instruction is one task. Receipts expose member index, instruction index and planned session count.

Members run in the selected order through the existing Agents hub launch path. Each session receives its own profile, current instruction and explicitly supplied context, rather than the previous session's chat. On a given device, the next session can reuse that device's prior checkout only after the previous process is positively stopped. Different devices have independent source-based checkouts. **Work diff / Apply** is the explicit review and transfer path; no invisible cross-device merge occurs.

Native turn-completion evidence advances supported sessions. Where the provider does not supply trustworthy completion evidence, the operator uses inspected **Finish & Next**. Terminal silence is not completion proof. Persisted dispatch identity, unique-group recovery, stop confirmation and receipt/profile drift checks fence duplicate or mismatched execution. Cancellation affects only owned work and is durable across reconnect. Unsupported project sampling or vote controls refuse rather than appearing to work.

### 25.5 Forge teams and critique

**Ask agents** opens the shared member editor for the current prompt. **Thinking tools → Configure agents** saves a per-project browser draft without dispatch. The common task focus is IDEATOR, QUESTIONER, CRITIC or SPECIFIER; each member can independently have a custom role, characteristics and instructions. The request's exact team, strategy, revision, fingerprint and context hashes are retained. Cloud/web context sharing is an explicit request choice. An explicit team never inherits a legacy role's fallback models.

Choose independent perspectives or proposals followed by critique. Calls are sequential admitted tool-free proposal requests, each with fresh context. The critique pass receives frozen validated first-pass proposals and the explicit current objective. Excessive peer context refuses instead of being truncated. Successful members are retained when another fails; the job becomes partial and displays member errors. Several successful outcomes can be selected and imported in one transaction against the original revision, avoiding the old failure where adopting one result made every other result stale. Import still creates proposals, never accepted requirements.

Proposal contexts can explicitly request creative exploration, precise specification or edge-case investigation, alongside refinement, improvement, simplification, normalization and compiler repair. Task roles are response contracts, not a fixed set of personalities. Member-specific profiles distinguish repeated models in actual requests and caches. Changing projects while model choices are loading invalidates the pending dialog rather than binding an earlier prompt to the new project.

### 25.6 Creative lenses and atomic instruction teaching

The idea workshop offers eight lenses: smallest useful version, user journey, representation, boundaries, failure/recovery, resource fit, verification and alternatives. Each supplies concrete choices, tradeoffs and edge cases. The operator can ask the configured team to explore a lens, provide a custom request, park an idea without changing scope, or move into the writing coach. These aids are suggestions; they do not invent accepted requirements.

The deterministic coach asks for one action, exact inputs, expected output, an observable check and bounded context. It explains why each field matters, flags possible multiple actions and subjective wording, preserves numeric values/units/paths, and shows missing fields. Broad requests for previous conversation are refused. Examples cover a pure Snake movement step, CSV validation and interrupted-save recovery; all are labelled illustrative. No model is called by opening or previewing the coach.

The preview produces a five-line human instruction: ask for the action, use the named input/context, produce the output, perform the check and finish the step. The operator can edit its exact text. It is not falsely presented as arbitrary-English compiler syntax. **Add as a proposal** retains the reviewed wording. **Prepare a construction unit** additionally asks for an accepted component, explicit accepted dependencies and optional target paths. With no component, a focused form proposes one and preserves the coach draft while the component is reviewed.

Instruction and linked unit are created together, both proposed. The unit objective preserves the full reviewed text, including edits, rather than reverting to the original action. Structured input/output/check fields remain separately visible for review. Both records appear together under Proposed and require separate acceptance. Accepted task cards and construction/native exports retain the requirement, explicit capsule, paths and checks. Current compiler validation creates separate native source with fresh explicit context. Neither a complete form nor a valid native Text ask claims the requested program or its behavioral checks have run.

Browser preview requests have draft-generation, view, project and revision guards. Editing while an earlier preview is in flight cannot restore old wording, re-enable an old proposal button or mix an old objective with new structured fields. Opening the workspace twice cannot append duplicate forms.

### 25.7 Verification record for this follow-up

The combined isolated Forge backend run passed **141 tests in 36.915 seconds**, across core, model requests, API/store, mixed-team/coaching, coach construction, exports and integration. The initial three construction-test errors were invalid short fixture request IDs; corrected fixtures passed and were included in the full run. The tests use temporary stores and fake provider/worker calls; native export validation uses the actual pure compiler.

The checked/project implementation passed **75 focused tests in 36.784 seconds** and **96 legacy tests in 80.630 seconds**. The former includes five-member checked execution, exact profiles/settings, cache-only resume, no replay after unknown dispatch, real English pixel compilation and per-device project checkout continuation. Exact module lists and source revisions belong to the evidence receipt; overlapping reruns are not added to a fabricated total.

The English/shell/Terminal frontend scope has **79 distinct passing cases** across seven suites. These include all retained views, one shared source field, five mixed members, old-server refusal, exact pending retry across pages, constructor/native picker compatibility, real isolated English-circuit journeys, desktop/phone dark layouts, accessibility and no overflow. Eight local guide links, 44 page assets and three existing integrity pins resolved.

The subsequent Forge and numeric-control browser run passed **17 tests in 49.300 seconds**: fourteen Forge journeys and three actual Chromium numeric-control regressions. It includes the coached requirement/component/unit/compiler journey, stale-preview refusal, five mixed members, explicit model-stop/reload, seven export downloads, proposal authority and a 400-statement fixture. Earlier browser runs exposed duplicate coach rendering and native disclosure-toggle races; their fixes were exercised by the passing run. Additional final model-dialog race, runtime deployment and live receipts are recorded separately in the linked evidence, rather than inferred from these tests.


### 25.8 Selected-device browser proposals

The new typed-proposal v1 lane supports ChatGPT/Gemini checked answers and Forge proposals through the selected registered device's own browser runtime. It reuses the existing browser admission and holds, rather than exposing `/ask` through the sign-in relay or adding an SSH bypass. The node's profile and credentials remain on that node. Installation, loaded daemon identity, account sign-in and model availability remain separate observations.

the fleet runner's cached read-only probe observes installed protocol version and the SHA-256 of `chatgpt.js` plus `typed-requests.cjs`. The team catalogue compares that with the controller's expected source and labels absent, mismatched or matching installation evidence. Every actual request additionally verifies the running daemon's import-time protocol/source hash. Copying files cannot make a still-running old daemon appear current. Runtime updates use the existing admitted idle installer and preserve busy or unknown work.

The host persists a request identity before admission. The node fsyncs accepted intent and its index before queueing a fresh owned window. The only admitted start data are exact ID, site, model and full prompt; no existing chat URL, upload or host coding tool is accepted. Full prompt is bounded to 100,000 UTF-16 code units without truncation. A duplicate identity never sends the prompt again; different content under the same identity refuses. A lost acknowledgement is observed through status. A restarted unfinished operator becomes unknown rather than replaying.

Gemini confirms the exact enabled visible mode before sending. ChatGPT confirms that the requested model slug is in the signed-in account catalogue and records the requested new-chat parameter; it cannot attest a serving-model weight digest. Empty model means the explicitly requested account default. Provider-side behavior and distinct model independence are not inferred from these labels.

Cancel targets only the window named for that exact typed request. Confirmed local closure does not prove that provider-side generation stopped; that fact remains unknown. An uncertain closure, failed status transport or ambiguous dispatch retains the browser hold. Finishing one reply does not release the whole daemon's hold; the existing browser/unit/cgroup reconciliation owns that proof. A positively proven initial non-admission consumes no native model-call budget. Unknown post-dispatch delivery is not refunded as a false no-call claim. Historical-source receipts cannot be relabelled as current.

The isolated browser-lane verification passed **39 Python tests plus 27 subtests in 8.67 seconds** and **31 Node cases in 46.433 seconds**. A prior overlapping 34-case Node run also covered runtime maintenance. These fixtures include a real native runner through the adapter to a fake transport and the real typed CLI against a fake loopback daemon. They made no provider/account call. The [browser provider guide](BROWSER-PROVIDERS.md) documents installation, identity, recovery and operational bounds; the dated evidence separately records actual runtime deployment and account readiness.
