"""Autogen: regenerate, split and hand off coding-agent attempts until code accepts the result.

Modules
    policy         the pure decision rules (no I/O): policy validation, statement lint, code-check
                   plans, failure classes, progress, the next action, worker prompts.
    coordinator    AutogenManager: the durable run record, attempts, verdicts by code, promotion.
    runner         the TaskRunner protocol the coordinator launches agents through, evidence
                   helpers, KernelOnlyRunner and the documented FakeTaskRunner.
    kernel_lane    attempts of `local` runs: spec-sheet builds with small local models.
    git_checkouts  own git checkouts per attempt and the 3-way apply of an accepted one.
    workspaces     managed empty git project folders.
    durable        crash-safe JSON writes.

See README.md in this folder for how the pieces fit, what is experimental and what was measured.
Importing this package has no side effects.
"""
