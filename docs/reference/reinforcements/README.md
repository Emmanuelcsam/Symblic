# Reinforcements: independent audits

Audits written by separate AI agent sessions (recorded as Codex helper sessions) that were asked to find defects in
one part of Symblic, offline, with bounded effort. Confirmed defects were fixed in the code or recorded with the reason
they were not; [../NOTES-2026-10-02.md](../NOTES-2026-10-02.md) summarizes what they found. Like everything here,
they were written by AI agents and not reviewed by a human expert.

| File | What it audits |
|---|---|
| [benchmark-review.md](benchmark-review.md) | The benchmark statistics: denominators, intervals, what a table may claim (its manifest is checked by `tools/scripts/symblic_reinforcement_stats.py`) |
| [communication-review.md](communication-review.md) | Whether the specification alone lets a fresh reader write correct programs |
| [contract-audit.md](contract-audit.md) | The kernel's contracts, against focused tests (`tests/kernel/test_symblic_reinforcement_contracts.py`) |
| [cube-protocol.md](cube-protocol.md) | An exact protocol for checking that agents reconstructed the same cube |
| [semantics-review.md](semantics-review.md) | The language semantics, from a compiler-design point of view |
