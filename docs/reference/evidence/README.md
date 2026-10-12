# Evidence records

Machine-readable records of individual runs, pilots and releases, written by the AI agents that ran them on the
original host (October 2026). Each is cited by the document named in the table. The values, counts and hashes are as
recorded; for publication, paths and machine names were rewritten (each edited file carries a `publication_note`).
Some records cite further evidence files that were not copied into this repository; the citing documents say so.

| File | What it records | Cited by |
|---|---|---|
| `2026-10-03-conformance-v3.json` | The fixed-corpus conformance run across 27 interpreter profiles: identical observable bytes, and what that does not establish | [../RESULTS.md](../RESULTS.md) |
| `2026-10-03-contract-pilot-llama1b.json`, `2026-10-03-contract-pilot-qwen4b.json` | Preregistered contract pilots with llama3.2:1b and qwen3:4b: every event, the summary and the measurement limits | [../RESULTS.md](../RESULTS.md); produced by [tools/scripts/symblic_contract_pilot.py](../../../tools/scripts/symblic_contract_pilot.py) |
| `2026-10-05-reform-install.json` | Installation and scoped live checks of the 5 October reform (language 2.5) | [../REFORM-3.md](../REFORM-3.md), many others |
| `2026-10-05-constructor-recovery-controls.json` | Constructor crash recovery, portable export integrity and optional controls | [../CONSTRUCTORS.md](../CONSTRUCTORS.md), [../CONSTRUCTOR-LOCKS.md](../CONSTRUCTOR-LOCKS.md) |
| `2026-10-05-focused-handoffs.json`, `2026-10-05-proof-obligations.json`, `2026-10-05-proof-task-card.json` | Release records of the proof-step delegation templates | [../REFORM-3.md](../REFORM-3.md) |
| `2026-10-05-obligation-pilot.json`, `2026-10-05-proof-card-pilot.json` | Paired pilots of proof-obligation enforcement and proof task cards | [../MATCHED-EVALUATION.md](../MATCHED-EVALUATION.md), [../AGENT-DELEGATION.md](../AGENT-DELEGATION.md), [../REFORM-3.md](../REFORM-3.md) |
| `2026-10-05-vorticity-construction.json` | One run of the finite energy-witness construction | [../VORTICITY-CONSTRUCTION.md](../VORTICITY-CONSTRUCTION.md), [../RESEARCH-TRANSFER.md](../RESEARCH-TRANSFER.md) |
| `2026-10-06-continuation.json` | Status of a continuation session: kernel, workcards, supervisor, portable runs | [../RESEARCH-ADOPTION.md](../RESEARCH-ADOPTION.md) |
| `2026-10-06-english-dot.json`, `2026-10-06-english-matrix.json` | One Qwen-built moving dot and one Matrix rain from English statements, with independent checks and the physical-display claims that were not verified | [../ENGLISH-STATEMENTS.md](../ENGLISH-STATEMENTS.md), [../START-HERE.md](../START-HERE.md) |
