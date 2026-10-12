# Symblic Terminal

> **Describes the original host.** Much of this document is about pages, services or machines of the private
> host Symblic was built on (its web server, job runner, agent hub or worker nodes). Those parts are not in this
> repository; see [../../integration/host/README.md](../../integration/host/README.md) for the code that remains and
> [README.md](README.md) for how to read these records.

Updated 2026-10-06. The hosted terminal is `/symblic-terminal.html` (also `/symblic-terminal` once registered). It brings the existing agent, shell, file, cluster and Symblic interfaces into a focused command workspace. It is a dashboard application running on Linux. It is not a replacement operating-system kernel.

Added 2026-10-07: [Symblic Forge](FORGE.md) at `/symblic-forge` is the separate ideation/specification workspace built from the five iDesign documents. Use it to review requirements, architecture, units and a frozen handoff before giving an implementation instruction here. Forge does not run the project during ideation. The original host also offered other, unrelated capabilities on the same website; they are not part of this repository.

## Give an agent a direct instruction

Write the result you want, choose an agent, model, effort and machine, and open **Folder, context and execution** to select the working folder. Press **Run instruction** or Ctrl/Cmd+Enter. A multiline instruction is one task in the default mode.

Example:

> Create snake.py in this folder. Make a small retro Snake game with a minimal black-and-white screen. Use arrow keys, show the score and add R to restart. Add tests for movement and collisions. Run the tests and tell me how to launch it.

The instruction starts a real agent through the existing admitted hub. The task owns a durable record and links to its persistent agent terminal. Starting an agent is not a claim that the objective was completed: inspect its output, files and test evidence. The task card reports native completion when an adapter supports it; otherwise finish the inspected step explicitly.

The engine, model and effort catalogues come from the same registry and saved model metadata as `the agent hub`. Current entries include the three-agent pipeline, ChatGPT web, Gemini web, Claude Code, Codex, Antigravity, Copilot, local Ollama, Council and Squad; the live registry is authoritative. Installed Ollama names from fleet metadata also appear. Initial loading reads cached metadata. If an online remote node is explicitly unprobed, the composer requests discovery once through `catalog?refresh=1`; **Refresh agents** also requests it explicitly. Selecting a model does not load it. A stale or missing API has a visible message; no hidden model substitute is selected. Switching into Three Qwen clears incompatible model/effort choices; an exact selected Qwen model stays selected. A missing saved agent remains visibly unverified and must be refreshed or explicitly replaced before a run. The machine menu reports offline or unsupported placements; unprobed readiness is labelled **availability unknown**. Admission still decides whether the selected workload can start now.

The agent working folder is explicit. **Browse folders** uses the existing operator folder API on the dashboard host; remote agents use the hub's admitted checkout mechanism. **Use a separate git checkout** retains changes on its own branch for inspection and applying through Agents → Work. It is off by default in this composer so the simplest local instruction edits the selected folder directly. The optional automatic-tools switch maps to the engine's existing execution mode. Engine-specific settings remain available in the complete Agents workspace.

Each saved task card names its reported **Execution workspace** and node. When that workspace differs from the selected source folder, the card shows both paths and a **Review / apply work** link to Agents → Work. Remote or separate-checkout changes remain in that execution workspace until reviewed and applied; the general **Files** panel browses the dashboard host and does not switch to the agent's remote workspace.

Machine discovery is asynchronous. After the automatic first-load request or **Refresh agents**, the composer reads cached updates every five seconds for up to one minute and keeps that in-progress scope visible. Repeated unprobed responses never repeat the automatic discovery request. Saved engine, model, role, node and instruction choices remain intact as inventories arrive. After the bounded watch ends, still-unknown nodes remain visibly unknown and the user can request another refresh. Discovery reads runtime/model metadata and does not generate model output. A cached response does not establish that all probes have completed; actual selected-node admission checks readiness again.

**New project**, beside the folder browser, creates a managed private git project under the configured SymblicOS projects root and fills in the working folder. Use a 1–64 character lowercase name with letters, digits, hyphens or underscores. The backend creates the initial repository baseline needed by remote agents. Repeating the same valid managed name reconnects to that project without overwriting it, including after a lost reply; an unrelated existing directory is refused. Creating a project does not start an agent.

## Fresh contexts and teams

**Fresh task per line** treats each nonblank line as a separate instruction. Every agent receives that line and the explicit **Shared context for each fresh task**, together with applicable repository instructions. Earlier chat transcripts are not copied into the new task. Files in the selected workspace remain available; fresh context is not filesystem isolation or provider-history deletion. The coordinator runs steps in sequence. A quiet terminal does not establish completion.

When automatic completion evidence is unavailable, the card says **Running · manual finish**. The agent may still be working. Inspect its result before using **Finish step & Next**: this acknowledges the result, stops only the current owned agent session and advances to a fresh session. The final step says **Finish task**. The backend's saved state for this manual lane remains `awaiting_review`; it does not mean the agent has finished. The backend preserves files and receipts. Unknown dispatch or termination outcomes remain visible and cannot advance by guessing. **Resume / recover coordinator** is shown when persisted work needs recovery. Remote placement and workspace reuse use the same hub contracts as Agents; unsupported combinations fail with the backend explanation.

**Three Qwen** selects the three-agent pipeline with three required Ollama roles: planner, builder and reviewer. Its discrete controller uses fresh role contexts, permits at most three build/review rounds and records native stage receipts for progress. Each discrete build invocation permits at most six provider calls and checks a 600-second budget before another call; it allows the active call or tool to finish. Reaching this limit retains the files and hands partial work to a fresh critic. A yielded build alone never counts as completed work. Choose the exact Qwen model and machine. Expand **Team roles** to choose distinct Qwen models per role. Check **New team for each line** to combine this mode with a new team context for every nonblank line, running sequentially in the selected workspace. The normal unchecked setting sends the complete multiline instruction to one team. For this preset, the browser sends `fresh_lines: true` at the task-request level when **New team for each line** is checked. Configured project teams use the same explicit field. For the ordinary three-agent pipeline the same role controls select each seat's engine, model and effort from native metadata; manual completion remains explicit when native completion evidence is unavailable. The native task limit is 20,000 UTF-16 code units for the complete prepared task, including working defaults, repository context, selected files and uploaded context (an emoji counts as two units). Oversized tasks are refused before launch and are never silently cut. Three roles are a collaboration method, not proof of model independence or universal correctness.

The bounded local builder uses `save,append,shell,read` plus the CLI agent's native `complete` tool. Its discrete invocation omits `patch`, so file changes use the exposed save/append or shell tools. Ordinary Ollama agent invocations retain their existing `patch` tool, and other engines keep their own tool sets.

After at least one acknowledged provider dispatch, later context pressure can also yield retained work to a fresh critic. The discrete guard checks the full context before native history reduction, including context added by enrichment. An oversized first request still refuses; changed operator/system instructions or provider identity remain hard errors. A context-pressure yield uses the same bounded handoff receipt and does not establish completion.

**Council** provides the existing template catalogue and exact editable stage/member specification. Its members read, propose, critique and synthesize; use the native Council handoff to send the result to an implementer. **Squad** accepts its native options and links to the complete package, acceptance, review and apply workflow. The **Agents & teams** workspace contains the full visual editors, engine settings, context attachments, messages, diffs and apply controls.

## Reconnect and saved work

A task submission has a client request ID and its exact request body. Until the server acknowledges a saved task, the browser retains both in session storage. A lost or unreadable reply locks the form and offers **Reconnect this submission**. This repeats the same identity and body, including after a reload. It does not invent a new task ID. A definite client refusal releases the pending request. The server validates identity reuse against the saved payload.

Reloading reads catalogues and task history; it does not submit instructions or open a shell. Active task cards poll read-only status and bounded terminal output. **Cancel task** and **Finish step & Next** are explicit task controls. **Refresh result** retrieves the exact saved task. Unknown launch outcomes require recovery evidence. The optional **Keep saved task; start a new draft** clears only the browser's pending form; it does not cancel work already received by the server.

## Native tools, kept intact

Buttons expand existing workspaces only when clicked. Closing a panel keeps its iframe and shell session; reopening it does not create another iframe.

| Button | Existing capability |
| --- | --- |
| Shell | Persistent tmux terminal, interactive programs, pipes, node/session selection and normal Linux commands |
| Files | Dashboard-host file browser, editor, uploads and downloads; remote task files are inspected through the agent terminal and reviewed/applied through Agents → Work |
| Agents & teams | All hub engines, three-agent-pipeline seats, councils, squads, agent messages, work review and applying changes |
| Symblic editor | Native source, checked English, Workcards, graphs, logic, memory, policies, saved runs and evidence |
| the fleet runner | Existing plans, capabilities and admitted fleet execution |
| the autonomous agents | Autonomous workstation and its fleet model router |
| Cluster | Nodes, activity, admitted compute and power controls |
| OS commands | Bounded legacy SymblicOS file commands and their durable receipts |

The fleet runner and the autonomous agents run through their own embedded native interfaces. They are not advertised as interchangeable hub engine IDs. Every panel also has an **Open full page** link. The shell uses the selected machine when first opened; afterward its own node/session menus control that persistent shell.

The **OS commands** panel preserves the original bounded command interpreter. It names its separate filesystem root and dashboard hostname; those commands do not use the agent working-folder selection. Examples include `Create a text file named "note.txt".`, `Write "hello" to "note.txt".`, `Read "note.txt".`, `List files.`, `Create directory "games".`, `Copy "note.txt" to "copy.txt".` and `inspect system`. Unsupported text produces a refusal. Every received operation has a receipt. Lost replies retain the exact request ID for reconnecting. Opening the panel or reading receipt history does not execute a command.

## English page integration

`/automation-studio/symblic.html` opens **English statements** by default. One editor serves both
**Checked statements** and **Agent task**. Switching workflows keeps its exact text and never
starts work. **Agents · N members**, immediately below the editor, holds the shared detailed
team editor: 1–24 explicit engines/models/devices, efforts, roles, characteristics, member
instructions and applicable settings, with count/add/duplicate/remove/reorder controls.

**Use configured team** applies those seats to the same checked statements: every Ask gets fresh
profiled typed requests and retains native checks, selected dependencies, recovery and visual
playback. It overrides the older single-worker selector only when enabled. Missing team API
capability or unsupported choices produce a visible refusal. The single statement picker still
uses the discovered typed-answer catalogue. See [English statements](ENGLISH-STATEMENTS.md) for
the grammar and exact team semantics.

For **Agent task**, a configured team maps to durable `mode: team` tasks. Members run sequentially
with fresh sessions in selected order; **New team for each line** repeats that order for each
nonblank instruction line. Confirmed stopping precedes advancement. A member reuses earlier
team files on its own device; different devices have separate checkouts and no implicit file
transfer or peer-chat history. Each step identifies its member, engine, model and device.
Native completion or explicit operator finish is recorded; neither is independent proof of the
whole objective. Temperature/seed overrides are refused for these native project-agent seats.
The standalone single-agent, three-agent-pipeline, council and squad workflows remain accessible with the
configured-team switch off. Their aggregate modes are not treated as individual team seats.

The English integration binds the shared durable task composer to that one editor. It does not
maintain a competing hidden instruction. A lost reply retains the original exact payload and
request ID, displays the retained instruction and locks editing until reconnect or an explicit
new draft. Terminal's existing standalone composer remains available. Advanced examples,
limits and instruction circuits are collapsed; all 19 Symblic views remain in the searchable
**All Symblic tools** menu, with English/Native/Runs shortcuts and existing deep links intact.

## Cheat sheet and local context tools

The terminal's expandable cheat sheet contains task examples, fresh-line examples, checked English, shell commands and keyboard shortcuts. Its Claude Cloud card shows `claude-cloud run 'Create a small retro Snake game.' --id snake`, `claude-cloud prompt snake 'Add tests for movement and collisions.'`, `claude-cloud resume snake` and `claude-cloud report snake`. Run these in Shell on the host, where the authenticated cloud client and artifact collector are installed; the task itself runs in Claude Cloud. The hub's Claude engine is Claude Code. Cloud candidate work is retrieved as a patch for review and is not automatically applied to the selected local folder. The cheat sheet links to [the full 2026-10-06 record](2026-10-06-full-symblic.md).

Run the repository CLI commands in a normal shell on the host, from `the host checkout`:

```sh
tools/symblic --help
tools/symblic-workcard --help
```

The installed context helper can be used in a normal shell on an admitted node where `symblic-context doctor` reports it available. Set `--root` to the project directory:

```sh
symblic-context doctor
symblic-context pack --root ./project --file game.py --query move --max-chars 12000
```

The context command is read-only and bounded. `doctor` reports actual tool availability. The pack is explicit source context for a fresh task; a short pack does not establish that it contains every relevant dependency.

## UI implementation and checks

The standalone page uses `symblic-terminal.html`, `symblic-terminal.css`, `symblic-terminal.js` and the shared `symblic-task-composer.js`. The English page reuses the composer through `web/studio/symblic.html` and `symblic-english.js`. Backend task behaviour belongs to `integration/host/symblicos_tasks.py` and `integration/host/symblicos_engine.py`. Files and task history remain in their existing private stores; no new public transcript store was added.

UI verification uses `tests/browser/symblic-terminal.mjs`, with every API intercepted and WebSocket replaced before page load. Its 15 cases cover desktop/light and phone/dark rendering, complete catalogues, exact task payloads, fresh lines, cancellation, uncertain submit/reload/idempotent reconnect, Qwen roles and fresh teams per line, mode-change model compatibility, unavailable saved-agent recovery, deferred shell creation, retained collapsed shell, English typed/catalogue integration, legacy OS receipts, bounded output, manual advancement, managed-project recovery, remote execution workspace/source-folder distinction and bounded first-load metadata discovery with preserved selections. User/model output is inserted as text, not HTML. Accessibility and horizontal-overflow checks run in both screen sizes. The existing `symblic-english.mjs` and construction circuit journeys retain checked grammar, source diagnostics, progress, stale-response protection, recovery and playback coverage in 22 cases, including desktop and phone source-link interaction after opening the instruction circuit. Browser checks start no real agents, councils, model calls, shells or file effects.

The focused English shell has 13 additional isolated journeys in `tests/browser/symblic-focused.mjs`: one-editor layout, five mixed seats, exact checked/team payloads, count/reorder/settings, catalogue-capability refusal, workflow switching, keyboard dispatch, uncertain recovery in English and across Terminal, full tool navigation, and expanded-team accessibility in desktop/light and phone/dark. The native picker, discovered-model and constructor-control suites retain their previous behaviors behind the new disclosure. These are frontend contract tests with synthetic APIs, not evidence of a live provider or completed agent objective.

The installed node runtime has a separate offline compatibility probe:

```sh
python3 integration/host/scripts/check_symblic_node_runtime.py --agentcli ~/.local/share/symblic-node/venv/bin/agentcli --system short
```

It invokes the installed CLI-agent CLI, lists a fixture model, sends native OpenAI-compatible tool calls, saves an exact file in a temporary workspace and ends through the native `complete` tool. Configuration, logs, state and caches are temporary; `HOME` is preserved. Its Python startup guard permits only the exact loopback fixture endpoint. The normal tool allowlist, streaming transport and automatic naming helper are exercised without a real model or account. This establishes CLI/transport/tool compatibility, not model output quality. The full and short system-prompt variants have separate receipts.

For the managed local runtime, add `--local-wrapper ~/.local/share/symblic-node/app/pipeline/src/agentcli-local.js --agentcli-python ~/.local/share/symblic-node/venv/bin/python`. This additionally exercises temporary Ollama metadata, creation of the same-weight 8192-context alias, receipt verification, the actual 1024-token output cap, disabled automatic naming and confirmed source/alias unload. Repeat with `--overflow` to verify that oversized operator text is refused before any generation or file effect. Every Ollama route in this probe is a loopback fixture; it creates no real model alias. Repeat with `--mutate-owner` to register a temporary native `TURN_PRE` hook that changes the first operator objective; the guard must refuse before generation or file effects. Repeat with `--build-handoff` to set a one-call/600-second fixture budget: the first real save must persist, the next generation must be prevented before HTTP, and the process must exit 75 with the standalone `SYMBLIC_BUILD_BUDGET_EXHAUSTED` marker on stderr. The fixture also requires that no completion was claimed and that both models were unloaded.

Repeat with `--prose-continue` to exercise the bounded build's continuation hook against the actual installed CLI-agent runtime. The fixture first returns two prose-only planning/diagnostic replies. Each must prompt continued work on the original operator's unfinished edits and checks using tools; neither may implicitly finish the session. The next two replies call the real `save` and `complete` tools. All four requests must retain the exact same operator-message content, the file must contain the expected bytes, the six-call limit must remain intact, and alias/source unload must be confirmed. Normal the CLI agent behavior outside the opted-in discrete build is unchanged. The installed-wrapper success, overflow-refusal, hook-mutation-refusal, partial-handoff and prose-continuation journeys passed 18, 13, 14, 19 and 25 assertions respectively on node-b (89 assertions across five journeys).

After narrowing the discrete builder's CLI tool set, the two affected installed-runtime journeys were rerun: partial handoff passed 20 assertions and prose continuation passed 26 (46 across the two journeys). Every actual outgoing request exposed `save`, `append`, `shell`, `read` and native `complete`, with `patch` absent. The probe uses this narrower CLI set for bounded build journeys; its ordinary journeys retain the full original tool set. The earlier five-journey receipt remains separate from this focused rerun. These are runtime contract checks, not claims about live model output quality.

The context-pressure fixture is `--context-handoff`. Under a six-call/600-second budget it saves the exact proof file, reads 1601 lines of seeded temporary text through the native `read` tool, and requires exit 75 before a third provider request. The file, original operator text and confirmed model unload must survive; the handoff happens with only two of six calls used. `--discrete-budget` can be combined with `--overflow` or `--mutate-owner` to verify their hard-refusal behavior under the same bounded four-tool contract. All these bounded variants use the four-tool CLI set. Against the raw-context guard revision, seven installed-runtime journeys passed 129 assertions: ordinary overflow 13, ordinary mutation 14, bounded overflow 14, bounded mutation 15, context handoff 27, call-budget handoff 20 and prose continuation 26. The earlier context fixture exposed native reduction before the guard, and its failed receipt was retained; that rerun verified the correction with the same fixture.

Two further probes cover native completion at the budget boundary. `--complete-at-budget` allows exactly two provider calls: real `save`, then native `complete` with empty arguments. `--complete-after-elapsed` delays the final completion response by 10.2 seconds across a ten-second budget, while retaining a six-call allowance. Both require exit 0, no third provider request, unchanged operator text, exact saved contents and confirmed unload. They exposed an early preparation check that incorrectly returned exit 75 after completion. The corrected guard checks call/time admission only before another provider dispatch; its identity and pre-reduction context checks remain in place. The complete current nine-journey run passed **182 assertions in 90.290 seconds** on installed CLI-agent (0.34): the two completion cases contributed 26 and 27 assertions, and the prior seven cases passed again. The failed boundary baseline and earlier overlapping receipts remain separate. These fixtures use only temporary files and a loopback fake provider, and do not establish live model quality.

Static files are live on write. New task APIs and agent placement changes are restart-gated; a successful isolated UI test is not proof that a provider is currently signed in or a fleet model fits. The dated full record distinguishes implementation, isolated verification and live operational evidence.

## Offline component acceptance and release records

The default acceptance command now creates a disposable private filesystem and uses explicit fixture model/catalogue responses:

```sh
python3 -m symblic.os.acceptance --json
python3 -m unittest tests.os.test_symblicos_acceptance
node --test --test-concurrency=1 tests/browser/symblic-terminal.mjs
node --test --test-concurrency=1 tests/browser/symblic-english.mjs tests/browser/symblic-english-construction-circuit.mjs
```

The acceptance report identifies its scope as `isolated_fixture_smoke` and `live_validation: false`. Its 21 checks cover static assets on disk, in-process command dispatch, compilation, complete-sentence intake, filesystem writes and persistence, receipts, exact request replay/refusal, fixture inventory/readiness/capacity contracts, injected shared-catalogue mapping, traversal and symlink escape. The command starts no subprocesses, model providers, network calls, HTTP server, VM or installation. `--scratch-parent` chooses an existing parent for the temporary directory; it never makes that parent the operating-system data store. Temporary state is removed after the run.

Reading a document from disk is labelled a static-asset check. Recreating an engine object is labelled persistence across object recreation. Compiler success is labelled compilation. Fixture responses establish the adapter contract only. Former public helper names suggesting HTTP, browser reconnect, service restart, live model invocation or executable containment remain callable for compatibility but return an explicit unperformed result. They are excluded from the default report. Actual HTTP, browser, restart, admitted agent and provider verification require separate scoped evidence.

`tests/os/test_acceptance.py` has nine isolated regression cases. These enforce the absence of process/network/provider calls, scratch-store separation and cleanup, repeatable counts, failure reporting, truthful legacy helpers, strict release-report consistency, missing-evidence behaviour and explicit temporary manifest output.

`symblic/os/release_manifest.py` assembles prototype metadata and supplied reports. Missing, empty or inconsistent acceptance results are `unverified` and never default to passed. A consistent passing fixture report can establish only `component_tested` for hosted components. Boot, physical installation, live model identity and framework health remain unverified by this writer. Supplied assertions are retained with their provenance rather than promoted to verified state. Hardware values absent from the supplied report remain absent. The explicit manifest writer records the actual source/image hashes when available, writes the file atomically and binds its receipt to that file hash. It performs no installation, boot or model execution.
