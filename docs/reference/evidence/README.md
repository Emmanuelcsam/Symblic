# Evidence records

Machine-readable records of individual runs, pilots and releases, written by the AI agents that ran them on the
original host (October 2026). Each is cited by the document named in the table. The values, counts and hashes are as
recorded; for publication, paths and machine names were rewritten and host process ids removed (each edited file carries
a `publication_note`). Some records cite further evidence files that were not copied into this repository; the citing
documents say so.

| File | What it records | Cited by |
|---|---|---|
| `2026-10-03-conformance-v3.json` | The fixed-corpus conformance run across 27 interpreter profiles: identical observable bytes, and what that does not establish | [../RESULTS.md](../RESULTS.md) |
| `2026-10-03-contract-pilot-llama1b.json`, `2026-10-03-contract-pilot-qwen4b.json` | Preregistered contract pilots with llama3.2:1b and qwen3:4b: every event, the summary and the measurement limits | [../RESULTS.md](../RESULTS.md); produced by [tools/scripts/symblic_contract_pilot.py](../../../tools/scripts/symblic_contract_pilot.py) |
| `2026-10-05-reform-install.json` | Installation and scoped live checks of the 5 October reform (language 2.5) | [../REFORM-3.md](../REFORM-3.md), many others |
| `2026-10-05-constructor-recovery-controls.json` | Constructor crash recovery, portable export integrity and optional controls | [../CONSTRUCTORS.md](../CONSTRUCTORS.md), [../CONSTRUCTOR-LOCKS.md](../CONSTRUCTOR-LOCKS.md) |
| `2026-10-05-focused-handoffs.json`, `2026-10-05-proof-obligations.json`, `2026-10-05-proof-task-card.json` | Release records of the proof-step delegation templates | [../REFORM-3.md](../REFORM-3.md) |
| `2026-10-05-obligation-pilot.json`, `2026-10-05-proof-card-pilot.json` | Paired pilots of proof-obligation enforcement and proof task cards | [../MATCHED-EVALUATION.md](../MATCHED-EVALUATION.md), [../AGENT-DELEGATION.md](../AGENT-DELEGATION.md), [../REFORM-3.md](../REFORM-3.md) |
| `2026-10-05-graph-composition.json` | Release of reusable graph authoring: composition, checks and a native replay with no model call | [../REFORM-3.md](../REFORM-3.md), [../AGENT-GRAPHS.md](../AGENT-GRAPHS.md) |
| `2026-10-05-parser-repair.json` | Release of native parser revision 1 (syntax depth 60, AST depth 128) and its read-only live checks | [../REFORM-3.md](../REFORM-3.md), [../SPEC.md](../SPEC.md), [../NATURAL-LANGUAGE-BRIDGE.md](../NATURAL-LANGUAGE-BRIDGE.md) |
| `2026-10-05-model-first-delegation.json` | Release of model-first delegation: `determine=false` and the ordinal proof-step template | [../REFORM-3.md](../REFORM-3.md) |
| `2026-10-05-bounded-construction.json` | Release of the shared per-ask allowance for optional determination and empty-answer probes | [../REFORM-3.md](../REFORM-3.md) |
| `2026-10-05-constructors.json` | Installation of the checked linear constructor (Z3) and the authoring tools, with live checks (one session identifier and two process ids removed for publication) | [../CONSTRUCTORS.md](../CONSTRUCTORS.md) |
| `2026-10-05-micro-v2-aggregate.json` | Aggregate of a frozen pilot with three small local models: 144 assignments of micro tasks and whole or incremental proofs | [../REFORM-3.md](../REFORM-3.md) |
| `2026-10-05-proof-command-diagnostic.json` | A one-inference diagnostic, JSON answers against proof commands, with three small models (12 assignments) | [../REFORM-3.md](../REFORM-3.md), [../PROOF-COMMANDS.md](../PROOF-COMMANDS.md) |
| `2026-10-05-command-menu-pilot.json` | A paired pilot of exact-command menus, free text against an enumerated answer (12 assignments), independently regraded | [../REFORM-3.md](../REFORM-3.md), [../AUTHORING-GRAMMAR.md](../AUTHORING-GRAMMAR.md), [../PROOF-COMMANDS.md](../PROOF-COMMANDS.md) |
| `2026-10-05-vorticity-construction.json` | One run of the finite energy-witness construction | [../VORTICITY-CONSTRUCTION.md](../VORTICITY-CONSTRUCTION.md), [../RESEARCH-TRANSFER.md](../RESEARCH-TRANSFER.md) |
| `2026-10-06-continuation.json` | Status of a continuation session: kernel, workcards, supervisor, portable runs | [../RESEARCH-ADOPTION.md](../RESEARCH-ADOPTION.md) |
| `2026-10-06-english-dot.json`, `2026-10-06-english-matrix.json` | One Qwen-built moving dot and one Matrix rain from English statements, with independent checks and the physical-display claims that were not verified | [../ENGLISH-STATEMENTS.md](../ENGLISH-STATEMENTS.md), [../START-HERE.md](../START-HERE.md) |
