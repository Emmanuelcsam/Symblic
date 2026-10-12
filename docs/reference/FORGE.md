# Symblic Forge

Symblic Forge is the separate requirements and ideation application at **/symblic-forge (a page of the original host)**, implemented from `idesign1.txt` through `idesign5.txt`. It turns an incomplete intention into reviewed requirements, engineering contracts and a frozen build handoff. The operator accepts decisions. Models propose. The existing Symblic parser and checker determine native syntax validity.

The existing Symblic Terminal (a page of the original host), language editor (a page of the original host) and normal terminal (a page of the original host) retain their execution roles. Forge does not execute the project it describes. Asking a selected model for a proposal is an explicit, separate operation with tools disabled. A generated construction unit is an instruction artifact, not evidence that implementation or its tests have run.

## Start with an idea

1. Enter an intention such as `I want to create a simple snake game` and press Enter. Shift+Enter inserts a newline. Original text, including spacing and line breaks, is retained.
2. Answer the current bounded question, accept a suggested answer, edit it first, or defer the decision. For Snake, the first unresolved decision is the rendering approach, with concrete alternatives.
3. Review the proposed atomic statements. **Accept statement** makes a statement authoritative. Accepting a suggested answer first records the answer and creates proposals; it does not bypass requirement review.
4. Continue refinement. **Thinking tools** holds creative lenses and team configuration. The **Specification & engineering workspace** opens one selected view; its complete view list stays collapsed until needed. Every state change is saved with an expected revision and a durable action identity.
5. Add objectives, observable acceptance criteria, architecture, components and isolated implementation units. Inspect readiness and compiler diagnostics. Export or freeze a handoff when the specification is ready.

**New** opens the idea/title/template form. Templates activate appropriate question coverage without accepting requirements. Available templates cover web applications, games, AI agents, clusters, operating systems, scientific work, hardware and research. Classification also recognizes desktop, CLI, embedded, electronics, robotics, data pipelines, mechanical and mixed intentions; classification is advisory and adds question coverage rather than project facts.

**Project… → Load Snake demonstration** creates a separate, explicitly labelled example with recorded choices. It never modifies the current project or implements Snake. Normal new Snake projects have zero accepted defaults. The demonstration supplies accepted rules, criteria, architecture and three isolated construction units so exports and readiness can be inspected end to end.

## Authority, provenance and history

Each statement, question, answer, suggestion, objective, criterion, component, unit and other engineering record has a stable identity. Display position is never identity. Records retain original source text, source identifiers and revisions. **Originating decisions** follows the source chain; **Inspect** shows the complete record. Rationale is stored separately from executable requirement text.

Provenance distinguishes operator originals, operator answers, model questions, model suggestions, accepted/edited suggestions, deterministic consequences, imported material and compiler information. Edits to accepted requirements return the changed version to proposal review. Removing a requirement retains its history. Explicit bulk acceptance is available in Proposed. A proposed replacement offers a before/after review; its separate acceptance action removes the original from active requirements without erasing its record.

Assumptions remain in quarantine until explicitly accepted as requirements. Replacing an assumption leaves the replacement proposed. The parking lot does not affect the accepted specification; promotion creates a proposal. Scope has separate in-scope, out-of-scope and undecided collections. Definitions and vocabulary aliases preserve the operator's names rather than silently renaming accepted text.

Snapshots retain the project’s branch states without recursively copying older snapshots. Restoring a snapshot first saves a safety snapshot. Branches support independent refinement, symmetric comparison and explicit selection of statements to merge as proposals. Undo and redo are new recorded transitions; they never delete audit history. A divergent edit clears the redo chain. Previously frozen handoffs and their artifact bytes remain historical evidence after later changes.

## Modes and controls

| Control | Behavior |
| --- | --- |
| DEEP | One independent consequential decision at a time |
| RAPID | Up to five currently independent questions |
| EXPLORE | Up to three alternatives with explicit choices |
| PRECISION | Prioritizes quantities, units, tolerances, interfaces and observable checks |
| CHALLENGE | Exposes contradictions and questions accepted design choices |
| Focus | Collapses engineering workspace and keeps the active decision prominent |
| Overview | Shows dimension coverage, blockers and engineering links |
| Skip animation | Reveals complete stored text immediately |
| Clear transcript | Clears only the visible trail; changes no project data |

The typewriter effect is presentation only. Complete text is available immediately to assistive technology and copy/export operations. Reduced-motion preference disables animation. Visibility and focus pause the decorative caret. Controls have visible keyboard focus, mobile text inputs of at least 16px, and responsive layouts.

Enter submits the primary input; Shift+Enter inserts a line. Ctrl/Cmd+K opens the command palette. Alt+Up/Down moves between suggested answers, Alt+A accepts the highlighted suggestion and Alt+D defers the current question. Dialogs and incompatible form controls isolate shortcuts. Explicit statement acceptance remains separate from suggestion acceptance.

| Command | Purpose |
| --- | --- |
| `/status`, `/spec`, `/proposed` | Readiness, accepted requirements, proposed requirements |
| `/questions`, `/conflicts`, `/assumptions`, `/completeness` | Decision ledger, contradictions, quarantine, dimension coverage |
| `/objectives`, `/architecture`, `/components`, `/units` | Engineering structure and isolated construction units |
| `the agent hub`, `/models`, `/cluster`, `/tests` | Proposed agent/model/node plans and acceptance criteria |
| `/invariants`, `/forbidden`, `/evidence`, `/scope` | Global constraints, negative checks, evidence and scope |
| `/parked`, `/vocabulary`, `/history`, `/search` | Parking lot, definitions/aliases, audit, project search |
| `/source`, `/exports`, `/jobs` | Native source, artifacts, proposal request receipts |
| `/new`, `/rename TITLE` | New project form or rename current project |
| `/idea TEXT`, `/park TEXT` | Propose an additional requirement or park an idea |
| `/snapshot NAME`, `/snapshots` | Save or inspect snapshots |
| `/branch NAME`, `/branches`, `/compare FIRST SECOND` | Branch creation, navigation and comparison |
| `/mode DEEP`, `/focus`, `/overview` | Refinement and presentation modes |
| `/accept ID`, `/reject ID` | Explicitly accept or reject a proposed statement |
| `/question ID`, `/defer ID` | Select or defer a question; omitted defer ID uses current question |
| `/model QUESTIONER` | Configure an explicit role request |
| `/validate` | Check generated native source with the installed compiler |
| `/validate SOURCE` | Check the exact supplied native source separately |
| `/export FORMAT` | Export manifest, brief, prompt, construction, tasks, sheet or symblic |
| `/undo`, `/redo`, `/recover`, `/skip`, `/clear`, `/help` | History, uncertain request recovery, presentation and help |

## Engineering workspace

Questions are grouped by engineering dimension and ordered by severity. Selection, deferral, reopening, explicit dismissal, splitting and research-needed state retain their original records. **Why this question**, **Why this suggestion** and **Compare suggestions** expose the decision, source and optional alternatives. Explanations are bounded project reasoning, not hidden model chain-of-thought.

The catalogue covers universal purpose/user/input/output/interface/behavior/state/platform/hardware/model/agent/cluster constraints and applicable graphical, game, AI, agent, cluster, hardware, data, networking, security, failure, performance, testing and scientific questions. Domain-specific questions activate when relevant. An operator can activate dimensions or mark a dimension not applicable with a reason. No chosen numeric value is silently invented.

Typed engineering records include:

- **Objectives:** measurable purpose and optional parent-objective hierarchy.
- **Criteria:** requirement IDs, observable outcome, measurement method and expected result. Subjective criteria must explicitly say so.
- **Architecture candidates:** supporting requirements, components, tradeoffs and unresolved choices. Acceptance selects a candidate explicitly.
- **Components:** responsibility, inputs, outputs, dependencies, state and effects.
- **Units:** component, objective, explicit inputs/outputs/dependencies/checks, supporting requirements, forbidden assumptions, names defined/required and paths.
- **Agents:** responsibility, inputs/outputs, permissions, dependencies and verification. This is a plan, not an agent launch.
- **Models and cluster plans:** exact model app/policy/schema, required node capabilities, placement, concurrency, memory/storage, synchronization and failure reassignment.
- **Invariants and forbidden behavior:** requirement/unit/criterion links and negative checks.
- **Evidence:** requirements, measurements/results, URLs or inert retained attachments; explicit inventory snapshots and proposed compiler repairs have typed structures.

The dependency graph and isolated-worker checks identify cycles, unavailable declared inputs, missing dependencies and checks, and orphaned requirements/components. Task capsules use declared requirements and dependencies; they do not inherit the full discussion. Deterministic quantity checks retain units and source IDs. Ordinary width/height answers with explicit `px`, `pixel` or `pixels` are parsed deterministically, including the stated `eight hundred pixels` and `six hundred pixels` example. Their 480,000 px² consequence appears only after both proposals are accepted. Ambiguous or unsupported quantities remain exact text for review. Accepted prompt, native-source and task exports carry the saved fact labels and units alongside the original wording, so short answers keep their width/height meaning. Memory/storage and complete accepted inventory comparisons can flag infeasibility. Cached discovery is labelled incomplete, so absence from a cache is not proof that a required model is unavailable.

Contradiction checks operate on explicit structured facts and known decision keys, including incompatible values and ordering/resource constraints. They are not a universal semantic theorem prover over arbitrary prose. The model critic can propose additional conflicts or counterexamples, but it cannot resolve them by rewriting accepted text. Conflict controls support keeping a side, proposing a replacement or recording an explicit compatibility condition.

Readiness combines unresolved mandatory decisions, structured conflicts, graph/unit problems, requirement coverage and accepted engineering structure. A score or colour cannot override blockers. Lifecycle states are IDEA, EXPLORING, DEFINING, ARCHITECTING, PLANNING, READY, EXPORTED and EXECUTION_TRANSFERRED. The operator changes lifecycle explicitly. Historical state labels are not evidence that execution occurred; frozen handoffs explicitly record that execution has not started.

## Models and controlled context

**Ask agents** opens a configurable team for this prompt. Choose **1–24 members**, add, duplicate, remove or reorder rows, and mix providers, models and devices. Increasing the count copies the final row with a fresh member identity; it does not force three Qwen agents. Each member has an exact engine/model/node, optional supported effort, your own role, characteristics and instructions. Checked/proposal Ollama members additionally support temperature and seed. Unsupported settings refuse instead of being silently discarded. The catalogue shows actual provider and device inventories; cached availability is rechecked by admission at execution. A missing device or model is never silently replaced.

The common task focus remains **IDEATOR**, **QUESTIONER**, **CRITIC** or **SPECIFIER**; it defines the structured response contract, independently of each member’s custom role. Deterministic validation always uses the installed compiler. The provider registry supplies node-specific Ollama names and exact applicators such as `ollama:qwen3:4b-instruct@node-f`. Cloud/CLI/web context sharing must be selected explicitly for that request. No cloud model is chosen by default. Composite coding agents use their native project workflow; listing an agent does not manufacture a tool-free typed adapter for it.

Each request freezes role, the complete ordered team and profiles, strategy, revision, branch, semantic fingerprint, member context hashes and private validation snapshot. Only the selected project context is sent. Accepted requirements form the common context; selected metadata and the active question are explicit. The critic does not receive the full brainstorming transcript. Source revisions and private snapshots retained for validation are not automatically sent to models. Per-project team drafts survive reload without dispatch. Explicit teams do not inherit an old role’s fallback models; legacy app/fallback configurations remain supported for old clients.

Choose **independent proposals** or **proposals followed by critique**. Independent calls receive fresh, explicit context. Critique adds a second fresh pass over the frozen validated first-pass proposals; oversized peer context refuses rather than silently truncating. Team calls run sequentially through admitted native paths, with tools disabled; choosing 24 members is not a promise of 24 simultaneous devices. Repeated instances of the same model retain distinct member identities, instructions and caches. Partial successes and each member’s error remain visible. Select several successful outcomes and import them in one revision transaction. Import creates proposals; agreement and vote-weight metadata never accept a Forge requirement.

Proposal purposes include ordinary refinement, ideation, precise specification, edge cases, optional engineering improvements, mapped simplification, before/after normalization and compiler repair. Improvement proposals preserve objectives unless the operator explicitly changes them. Simplification and normalization identify their original statement through `replaces_id` and source IDs. A compiler repair references the exact source SHA-256, diagnostic index, Unicode code-point range, replacement and affected statements. Preview does not change accepted requirements; the operator explicitly checks the candidate with the current compiler.

Responses must satisfy bounded structured JSON contracts. Hidden reasoning fields, invented IDs, malformed values, extra authority fields and invalid entities are refused. A response to an old revision remains inspectable but cannot be adopted into a changed branch. Importing model output creates proposals only.

There are at most three queued/running/unknown Forge proposal jobs. A worker claims a queued request once and records each intent before dispatch. Browser reload polls retained state; it never launches a model again. An ambiguous dispatch remains unknown for explicit inspection/recovery. **Stop owned request** targets only that request’s orchestration service through the existing lifecycle helpers. No general shell endpoint is added.

## Idea workshop and spec writing coach

**Thinking tools → Explore possibilities** opens eight lenses: smallest useful version, user journey, representation, boundaries, failure/recovery, resource fit, verification and alternatives. Each presents concrete alternatives, tradeoffs and edge-case questions. Explore a selected lens with your configured team, park an idea without changing accepted scope, or move directly into the writing coach. Examples are labelled teaching material, not inferred project decisions.

**Shape this instruction** teaches one atomic step through five explicit fields: one action, inputs, expected output, observable check and bounded context. Name actual artifacts, paths, formats, units or expected results; use an explicit “none” when appropriate. Broad prior-conversation requests are refused. A deterministic preview explains the structure, preserves exact numbers and paths, flags subjective or multi-action wording and shows missing fields. It calls no model. **Ask agents to help specify** is a separate explicit request with the selected team.

**Learn from examples** contains eleven editable teaching drafts: a Snake step, CSV validation, interrupted-save recovery, code repair, a responsive website component, exact math, a labelled chart, a command-line program, a dependency schedule, a dimensioned cup/STL and a bounded machine-motion model. **Use example** fills the coach for review without saving a requirement or starting work. These are synthetic instruction and export examples; actual model output, generated artifacts and executed checks require separate receipts. Engineering list fields preserve commas and bracketed prose as data; use one value per line or a JSON list when a value itself contains a newline.

Review or edit the five-line human instruction. **Add as a proposal** saves the exact reviewed text without accepting it. **Prepare a construction unit** additionally connects it to an accepted component, explicitly selected accepted dependencies and optional target paths. If no component exists, a focused form proposes one; accept that component before returning to the retained coach draft. The instruction and linked unit are then proposed together in one transaction and shown together for separate acceptance. Inputs, output, checks, paths and the reviewed requirement survive task-card, construction and native-source export. Compiler-valid source is generated separately from the human coaching block. Form completeness and static compilation never claim its behavioral checks ran or that the project is implemented.

## Exports, validation and handoff

| Format | Contents |
| --- | --- |
| `manifest` | Complete project schema, accepted/proposed state, histories, branches, snapshots and semantic fingerprint |
| `brief` | Human-readable accepted design and unresolved work |
| `prompt` | Accepted requirement text without proposal/history material |
| `construction` | Bounded human instructions ending in `Finish this step.` |
| `tasks` | Explicit task cards with dependencies, inputs, outputs, checks, criteria and applicable invariants/forbidden behavior |
| `sheet` | Structured accepted specification sheet; it is not falsely labelled the separate historical Markdown JS-sheet grammar |
| `symblic` | Current native syntax, validated against the actual installed compiler |

The human `Ask the model to make … / Use only … / Check … / Finish this step.` construction plan is retained separately from native syntax. Accepted unit paths and declared/required symbols are retained exactly in task cards, sheets, construction instructions and native ask capsules. Construction labels quote these values as JSON strings so embedded newlines and quotes remain data; the export never opens or executes a declared path. Native export creates exact literal bindings and Text asks with explicit `from` dependencies under `profile=verified, context=none, determine=false, solve=false`. Prose verification remains an explicit observable instruction; it is not fabricated into an executable test predicate. Native source mapping connects diagnostic lines to requirement/unit IDs.

Each retained artifact includes exact bytes, SHA-256, source revision and semantic fingerprint. Native validation includes the actual compiler identity and source hashes. The running exporter pins its seven parser/checker/core/catalog/export source files when loaded. Health reports loaded hashes separately from current disk hashes. Validation refuses HTTP 503 if they differ or change during a check; restart the dashboard before requesting a new receipt. A saved historical validation is never silently relabelled with a newer compiler. Custom editor source is checked exactly but is not proof that the generated accepted project passed. A native artifact rejected by the compiler is not exported with a valid badge. Imports preserve historical receipt metadata while removing current compiler/handoff authority.

**Freeze build handoff** requires structural readiness, rechecks generated source with the current compiler, then saves immutable manifest/native source/task cards/specification sheet/construction artifacts in the same transaction as the handoff receipt. Later edits retain the old handoff and require another audit for a new handoff. No build is dispatched. Use the separate execution interfaces deliberately when ready to implement the plan.

In **Exports → Frozen handoffs → Run frozen plan in Symblic**, review the retained native artifact and
choose an exact local Ollama model and call budget, then press **Start native run**. This separate
execution action imports the original `.sym` bytes into the existing Symblic runner. It does not
recompile the prose into another language, substitute a newer specification, write the declared target
paths, or claim that prose checks ran. Native Text answers retain the unit artifacts and native evidence;
inspect the linked run and validate its outputs before using them. There is no proprietary-model fallback.
The visible local-model limits default to 2,048 reply tokens, 8,192 context tokens, 300 seconds per call
and 900 seconds from the first model dispatch across the run. Edit them before starting when the unit
needs a different budget; exact limits enter the frozen request and native execution policy.

The original Forge handoff remains a nonexecuting frozen record. A separate native run receipt binds
its handoff ID, artifact SHA-256, source revision, fingerprint, compiler identity, selected model and
effective runtime pins/budget. The existing private Forge ledger records the exact request and launch
provenance before the native launcher runs; the native folder retains the same independent origin marker.
Changed artifacts, a newer accepted specification, or compiler drift refuse a new import. Reusing an
identical request returns its original receipt. A lost launch reply remains unknown and is never blindly
dispatched again; **Recover pending action** reads that receipt and the native handle. Resume verifies
the frozen bytes and original policy instead of trusting editable run metadata alone.

The host executor and the full-mode the autonomous agents workstation can inspect the same retained handoffs through
the operator-only `forge.handoff` the fleet runner read. Supply `project` to list bounded handoff IDs, then `handoff`
and optionally `artifact`, `offset` and `limit` to read verified artifact windows. Hash/compiler lineage
describes host integrity; project prose stays untrusted. This read never starts a run or accepts a
requirement. Scoped gateway tokens cannot acquire this private untrusted capability.

## Persistence and API

Private state is `symblic_forge_data/forge.sqlite3`, overridable by `SYMBLIC_FORGE_DATA` for isolated environments. The database uses SQLite WAL, FULL synchronization, revision CAS and transactions. Tables retain projects, append-only events, exact action receipts, HTTP intents/outcomes, model requests and artifact bytes. Project documents contain only the schema fields; timestamps belong to ledger metadata.

Directories/database are private; symlink database paths are refused. Data and API routes are registered through the central registrar, including operator checks, static private-data exclusions, navigation, backup classification and read-only health monitoring. Worker imports are inert. Only explicit model start creates a bounded `a systemd slice for work` orchestration service on the permitted host.

All routes use `/api/symblic-forge/` and require the operator gate:

| Method/routes | Contract |
| --- | --- |
| GET `health`, `catalog`, `models` | Schema/compiler health, typed controls, cached model and node metadata |
| GET `projects`, `project?id=ID` | Project navigation and derived state |
| GET `history?id=ID&before=REV`, `search?id=ID&q=TEXT` | Audit pagination and project search |
| GET `compare?id=ID&first=BRANCH&second=BRANCH` | Symmetric branch comparison |
| GET `request?id=REQUEST`, `job?id=JOB`, `artifact?id=ARTIFACT` | Retained outcomes and immutable bytes |
| POST `project/create`, `project/import`, `demo` | Explicit new/import/example project |
| POST `action` | `{id,revision,action,payload,request_id}` validated transition |
| POST `validate`, `export`, `handoff` | Current compiler check, exact artifact or frozen nonexecuting handoff |
| POST `inventory`, `inventory/attach` | Explicit metadata discovery or proposed captured evidence |
| POST `evidence/file` | Bounded filename and base64 content; creates proposed evidence atomically |
| POST `repair/preview` | Exact retained diagnostic repair preview; no acceptance or execution |
| POST `model/start`, `model/adopt`, `model/recover`, `model/stop` | Explicit proposal lifecycle |
| GET `coach`; POST `coach/preview`, `coach/propose` | Creative lenses, non-mutating contract preview, proposed instruction and optional linked construction unit |

The separate operator execution API stays under `/api/automation/symblic/`: GET `forge/handoff` inspects
the exact handoff/artifact, POST `forge/run` requires
`{project,handoff,artifact,artifact_sha256,source_revision,by,max_calls,ollama_limits,request_id}`, and GET
`forge/request?id=REQUEST` recovers its receipt without dispatch. `by` is one explicit local Ollama
applicator; `max_calls` is an integer from 1 to 200. Loading the page, refreshing, exporting and inspecting
any of these records never launches work.

All state-changing requests carry a stable request ID; project changes also carry the displayed revision. Repeating an identical confirmed request returns its outcome. Changing content under the same ID is refused. An intent without a confirmed outcome is not automatically repeated. Client recovery performs read-only receipt reconciliation and retains the identity of uncertain requests. Conflicting tabs must reload rather than overwrite newer state.

Public `action` cannot forge compiler, export, handoff or model artifact receipts. Evidence uploads accept bounded UTF-8 TXT/JSON/CSV or signature-checked PDF/PNG/JPEG; active HTML/SVG is refused. Downloads are inert attachments. Text is rendered with DOM text nodes, never HTML evaluation. Files stay private and are not sent to a model merely because they were attached.

Operational bounds are explicit: 8 MB HTTP transaction, 16 MiB schema serialization, bounded individual text/collection sizes, 2 MB attachment, 48,000-character selected model context, 100,000-character proposal result and up to three simultaneous unresolved proposal requests. These are admission limits, not token counts or a claimed model context capacity. Continued refinement has no arbitrary conversation-round cap; large projects must remain within the declared storage/request limits.

## Verification and source map

[FORGE-ACCEPTANCE.md](FORGE-ACCEPTANCE.md) maps the five input documents to implementation and checks. The [2026-10-07 release evidence](2026-10-07-forge-integrations-evidence.json) records exact source/compiler digests, tests and live observations separately. Isolated checks use temporary stores and fake every model, node, worker and external service. Native compiler tests run the actual pure parser/checker without executing asks.

```sh
bin/devtest --workers 1 tests.forge.test_symblic_forge_core tests.forge.test_symblic_forge_exports tests.forge.test_symblic_forge_models tests.integration.test_symblic_forge_api
CHROME_BIN=/path/to/cached/chromium node --test tests/browser/symblic-forge.mjs
```

The browser suite uses real page assets and a temporary Python API/core fixture. It checks authority, edited suggestions, provenance, branch/snapshot/reload recovery, native validation, engineering views, model request nonreplay, explicit stop, evidence uploads, phone layout, reduced motion, complete text, XSS-as-data and accessibility. Heavy final checks and live results belong in the release receipt, not inferred from installation.

| Source | Responsibility |
| --- | --- |
| `symblic-forge.html`, `.css`, `.js` | Minimal page, drawers, explicit action forms, keyboard and receipt recovery |
| `symblic/forge/catalog.py` | Domains, dimensions, independent decision catalogue and typed entity fields |
| `symblic/forge/core.py` | Pure transitions, authority, provenance, branches/snapshots, graph, readiness and fingerprints |
| `symblic/forge/store.py` | Transactional private persistence, CAS, audit, action receipts, jobs and artifact bytes |
| `integration/host/symblic_forge.py` | Operator API, host-only receipts and controlled lifecycle orchestration |
| `symblic/forge/models.py` | Explicit role contexts, native applicators, strict proposals and stale-result handling |
| `symblic/forge/coach.py` | Atomic instruction teaching, bounded context and explicit construction-unit preparation |
| `symblic/providers/agent_teams.py`, `symblic-team-editor.js/css` | Shared exact team contract, capabilities and collapsible member controls |
| `symblic/forge/exports.py` | Accepted exports, exact native lowering, compiler/source mapping and identity |
| `symblic/forge/watch.py` | Read-only private-ledger health; no probes or automatic repairs |

The original host also offered other execution capabilities (not part of this repository). Forge ideation never invokes them silently; they were used only after the operator had chosen what to build.
