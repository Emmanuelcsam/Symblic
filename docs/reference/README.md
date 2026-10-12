# Reference documents

The language reference, design records, measurements and research notes written while Symblic was built
(2 to 11 October 2026). **Every document here was written by AI agents**
([../MADE-WITH-AI.md](../MADE-WITH-AI.md)). Read them with these points in mind:

- **The code wins.** These documents were written alongside the code on the original private host. Where one
  disagrees with the code in this repository or with a package README, the code and the README are right.
- **Host-only features.** Many documents describe the original host's web pages, scheduler, agent runner and worker
  machines (called "the host", "the fleet runner", "the agent hub" and `node-a` to `node-i` here). Those parts are not
  in this repository; documents that are mostly about them are marked **(host)** below.
- **Old paths and line numbers.** File paths were rewritten to the new layout ([../MAP.md](../MAP.md)) wherever they
  could be resolved. Quoted line numbers (`language.py:4880`) refer to the files before the move.
- **Private records.** Paths under `~/.local/state/`, `automation_data/` and similar point to run records on the
  original host. They are cited so a figure can be traced; they are not part of this repository.
- **Speculative AI writing** is labelled at the top of each such document and listed in its own section below.
- File names are kept as they were, because code and tests refer to them.

## Start here

| Document | What it is |
|---|---|
| [SPEC.md](SPEC.md) | The language specification (version 2.5): statements, types, asks, checks, kernel, runs. The main reference. |
| [START-HERE.md](START-HERE.md) | A first program and examples of useful projects; the interface parts describe the host's web page. **(host)** |
| [AUTHORING-GRAMMAR.md](AUTHORING-GRAMMAR.md) | The `grammar` commands: current syntax, options, bounds and checked examples. |
| [grammar/](grammar/README.md) | EBNF for formulas, the program subset and proof commands. |
| [NOTES-2026-10-02.md](NOTES-2026-10-02.md) | The original request, what the first two days built and measured, and the answers given then. |
| [2026-10-06-full-symblic.md](2026-10-06-full-symblic.md) | A long consolidated record of 6 October: the host's terminal, agents, commands and history. **(host)** |

## The language

| Document | What it is |
|---|---|
| [LANGUAGE-3.md](LANGUAGE-3.md) | Functions, routines, modules, tests, `.symd` papers and lockfiles (the abstraction layer). |
| [papers/](papers/README.md) | Worked `.symd` papers: a cube, a recipe, a furnace schedule, a slurry. |
| [ENGLISH-STATEMENTS.md](ENGLISH-STATEMENTS.md) | Plain-English statements and the native programs they compile to. |
| [EFFECTS.md](EFFECTS.md) | `observe` and `act`: typed calls to host capabilities, at most once, with a ledger. |
| [STRUCTURED-JSON.md](STRUCTURED-JSON.md) | Declared JSON output shapes for `Code json` answers. |
| [COMPACT-CAPSULES.md](COMPACT-CAPSULES.md) | A shorter presentation of provenance in what a model is shown. |
| [EVIDENCE.md](EVIDENCE.md) | Evidence records: acquisition modes, sources, assumptions; what assurance they give. |
| [EPISTEMIC-MEMORY.md](EPISTEMIC-MEMORY.md) | Notebooks that keep claims between runs with their provenance. |
| [SOURCE-WITNESSES.md](SOURCE-WITNESSES.md) | Checking that quoted spans really are in the source. |
| [EXECUTION-PINS.md](EXECUTION-PINS.md) | Receipts that bind a reviewed program to the exact code that will run it. |
| [EDITOR.md](EDITOR.md) | Underlines and the instruction circuit in the browser editor. **(host)** |

## Building with small models

| Document | What it is |
|---|---|
| [SPEC-SHEETS.md](SPEC-SHEETS.md) | Spec sheets: a file as small units with contracts and examples, built unit by unit; the Tetris record. |
| [JS.md](JS.md), [JS-CONTRACTS.md](JS-CONTRACTS.md) | How model-written JavaScript is tested in a sandbox; optional declaration contracts. |
| [DIFFERENTIAL-SPECS.md](DIFFERENTIAL-SPECS.md) | Comparing passing candidates on extra probes to find under-specified units. |
| [STEPS.md](STEPS.md), [STEPS-EVIDENCE.md](STEPS-EVIDENCE.md) | Step constructions (the model picks the number of an expression) and what the test achieved. |
| [WORKCARDS.md](WORKCARDS.md) | Typed workcards: fill-the-hole tasks and builder/reviewer roles. |
| [TASK-CARDS.md](TASK-CARDS.md) | Task cards and portable builds. |
| [AGENT-CARD.md](AGENT-CARD.md) | How another agent can use Symblic's command line. |
| [AGENT-DELEGATION.md](AGENT-DELEGATION.md) | Reusable delegation templates: hand one bounded task to a small agent. |
| [EXPENSE-HANDOFF.md](EXPENSE-HANDOFF.md) | A worked hand-off between agents with pinned inputs and exact replay. |
| [LOCAL-ROUTING.md](LOCAL-ROUTING.md) | Choosing the next local model after a detectable failure. |
| [GRAPH-COMPOSITION.md](GRAPH-COMPOSITION.md), [AGENT-GRAPHS.md](AGENT-GRAPHS.md) | Reusable graph fragments; contracted agent graphs and their runtime. |
| [MICA.md](MICA.md), [MICA-SOURCES.md](MICA-SOURCES.md), [MICA-SOURCES.json](MICA-SOURCES.json) | Checked assembly of small JavaScript programs, and the 22 repositories whose methods it adapts. |
| [CAPABILITY-COMPILER.md](CAPABILITY-COMPILER.md) | A design and research plan: Symblic as a compiler of capabilities from small models. |
| [AUTOGEN.md](AUTOGEN.md), [RECURSION.md](RECURSION.md) | Autogen: regenerate, split and hand off agent attempts; the `until_done` rules and the papers they follow. **(host)** for the agent runs |
| [LOCAL-AUTOGEN.md](LOCAL-AUTOGEN.md) | Autogen on the kernel lane with light local models. |
| [INTERPRETER.md](INTERPRETER.md) | From an idea to a checked program through an intent record. **(host)** |
| [FORGE.md](FORGE.md), [FORGE-ACCEPTANCE.md](FORGE-ACCEPTANCE.md) | The requirements workbench and its 154-unit acceptance map. |
| [SUPERVISOR.md](SUPERVISOR.md) | Durable workflows of native programs on the host's scheduler. **(host)** |

## Exact builtins, logic and proofs

| Document | What it is |
|---|---|
| [VARIATIONAL.md](VARIATIONAL.md) | Exact finite quadratic minimization with an independent check. |
| [TRANSPORT.md](TRANSPORT.md) | Exact one-dimensional transport distance. |
| [DISCRETE.md](DISCRETE.md) | Exact ground states of a small Ising model (its example is run by the tests). |
| [KNOWLEDGE.md](KNOWLEDGE.md) | Knowledge on a finite set of states (partition model; its example is run by the tests). |
| [PROJECTION.md](PROJECTION.md) | The nearest values that satisfy linear constraints. |
| [OPERATORS.md](OPERATORS.md) | Exact finite operators and the probabilities of ordered questions (its example is run by the tests). |
| [QUANTITIES.md](QUANTITIES.md) | Exact quantities with units and measurement intervals. |
| [FINITE-LOGIC.md](FINITE-LOGIC.md) | Logic over explicit finite domains. |
| [PROOF-TERMS.md](PROOF-TERMS.md), [PROOF-STEPS.md](PROOF-STEPS.md), [PROOF-COMMANDS.md](PROOF-COMMANDS.md), [INCREMENTAL-PROOFS.md](INCREMENTAL-PROOFS.md) | Checked proof terms, flat natural-deduction certificates, one command per inference, and proof sessions with one inference per fresh context. |
| [PROOF-TASK-CARD.md](PROOF-TASK-CARD.md), [PROOF-STEP-DELEGATION.md](PROOF-STEP-DELEGATION.md), [PROOF-OBLIGATION-DELEGATION.md](PROOF-OBLIGATION-DELEGATION.md), [PROOF-FOCUS-DELEGATION.md](PROOF-FOCUS-DELEGATION.md) | Handing single proof steps and obligations to fresh agents. |
| [CONSTRUCTORS.md](CONSTRUCTORS.md), [CONSTRUCTOR-CLI.md](CONSTRUCTOR-CLI.md), [CONSTRUCTOR-LOCKS.md](CONSTRUCTOR-LOCKS.md), [CONSTRUCTOR-PROVISIONING.md](CONSTRUCTOR-PROVISIONING.md), [SOLVER-PROVENANCE.md](SOLVER-PROVENANCE.md) | Answering linear asks with a solver (Z3) instead of a model: runtime, command line, records, installation and provenance. |
| [VORTICITY-CONSTRUCTION.md](VORTICITY-CONSTRUCTION.md) | A finite energy-witness construction, built one checked part at a time (a synthetic example, not a fluid simulation). |
| [PORTABLE-FINITE.md](PORTABLE-FINITE.md) | Running the pure kernel on other machines and comparing results. |

## Measurements and records

Summarized, with sources, in [../HONEST-ASSESSMENT.md](../HONEST-ASSESSMENT.md).

| Document | What it is |
|---|---|
| [RESULTS.md](RESULTS.md) | The measurement ledger through version 2.4, each result with its method and limits. |
| [LOCAL-BETA-REPORT-2026-10-11.md](LOCAL-BETA-REPORT-2026-10-11.md) | The small-model ladder of 2026-10-11 and the game-level builds, failures included. |
| [LOCAL-BETA.md](LOCAL-BETA.md) | The beta matrix runner for light local models. **(host)** for placement |
| [REPORT-2026-10-10.md](REPORT-2026-10-10.md) | What was built and measured on 10 October: autogen, the frontier ladder, a matched pilot. |
| [FRONTIER-LADDER.md](FRONTIER-LADDER.md) | One frozen small model, one budget, six compiler strategies; the commands are the host's. **(host)** |
| [MATCHED-EVALUATION.md](MATCHED-EVALUATION.md) | A frozen comparison of a direct request against one typed Symblic capsule. |
| [AMBIGUITY-BENCH.md](AMBIGUITY-BENCH.md) | A benchmark for recognizing and resolving an ambiguous request. |
| [DISTILLATION.md](DISTILLATION.md) | The fine-tuning pipeline and its one small pilot. |
| [EXPERIMENTS.md](EXPERIMENTS.md), [CONTEXT-EXPERIMENTS.md](CONTEXT-EXPERIMENTS.md), [PROTOCOL-EXPERIMENTS.md](PROTOCOL-EXPERIMENTS.md), [RESEARCH-GEOMETRY.md](RESEARCH-GEOMETRY.md) | Finite research experiments with exact receipts. |
| [POLICY-LEARNING.md](POLICY-LEARNING.md), [POLICY-EXPERIMENTS.md](POLICY-EXPERIMENTS.md) | Choosing a routing policy from frozen candidates without fooling yourself. |
| [INQUIRY.md](INQUIRY.md) | Choosing the next evidence method for a claim. |
| [DOCUMENTATION-CONFORMANCE.md](DOCUMENTATION-CONFORMANCE.md), [documentation-cases.json](documentation-cases.json) | Which code examples in these documents are executed, and their pinned cases. |
| [2026-10-08-symblic-beta-review.md](2026-10-08-symblic-beta-review.md) | A beta review of 8 October. **(host)** |
| [evidence/](evidence/) | Machine-readable records of individual runs and releases (JSON). |
| [kernel-identity.json](kernel-identity.json), [claims.json](claims.json), [2026-10-07-forge-integrations-evidence.json](2026-10-07-forge-integrations-evidence.json) | Cross-machine kernel fingerprints, the claim ledger of the 5 October reform, the Forge release record. |
| [reinforcements/](reinforcements/) | Independent audits by other agent sessions: benchmark, communication, contracts, the cube protocol, semantics. |

## Research behind the design

| Document | What it is |
|---|---|
| [PRIOR-ART.md](PRIOR-ART.md) | A survey of related work (prompt languages, controlled languages, solvers, decomposition, small models, determinism) and what Symblic can and cannot claim. |
| [RESEARCH-AGREEMENT.md](RESEARCH-AGREEMENT.md) | Research on getting different models to give the same answer; 23 engineering rules. |
| [RESEARCH-LANGUAGE.md](RESEARCH-LANGUAGE.md) | Logic, philosophy of language and controlled languages; can a description force the same result from any reader? |
| [RESEARCH-ADOPTION.md](RESEARCH-ADOPTION.md), [RESEARCH-TRANSFER.md](RESEARCH-TRANSFER.md) | Which research ideas were adopted, and how fresh-context construction carries over. |
| [REFORM-3.md](REFORM-3.md) | The 5 October reform: executable statements, conditional evidence and agent networks. |
| [REVIEW-2.3.md](REVIEW-2.3.md) | What nine AI-written proposal documents proposed, the 120 factual errors found in them, and what was built. |

## Critiques

| Document | What it is |
|---|---|
| [CRITIQUE-AND-LIMITATIONS.md](CRITIQUE-AND-LIMITATIONS.md) | A critical review of Symblic's contracts and usefulness (AI-written, revised). |
| [INTENSE-CRITIQUE-AND-LIMITATIONS.md](INTENSE-CRITIQUE-AND-LIMITATIONS.md) | Counterexamples and unresolved limits (AI-written, revised). |
| [SYMBLIC-CRITICAL-ANALYSIS.md](SYMBLIC-CRITICAL-ANALYSIS.md) | An agent's own analysis of a beta trial and the project's viability. |

## Speculative AI writing

Kept as a record of what the agents wrote. Not research results; see [../MADE-WITH-AI.md](../MADE-WITH-AI.md). The
originals are in [../essays/](../essays/README.md).

| Document | What it is |
|---|---|
| [GRAND-UNIFICATION-AND-STRING-THEORY.md](GRAND-UNIFICATION-AND-STRING-THEORY.md) | Mathematics and physics (string theory, dualities) proposed as research for Symblic. Speculative. |
| [PHYSICS-AND-ADVANCED-MATHEMATICS.md](PHYSICS-AND-ADVANCED-MATHEMATICS.md) | Mathematical physics proposed as borrowings for Symblic. Speculative. |
| [QUANTUM-FOUNDATIONS-OF-SYMBLIC.md](QUANTUM-FOUNDATIONS-OF-SYMBLIC.md), [QUANTUM-DETERMINISM-ANALYSIS.md](QUANTUM-DETERMINISM-ANALYSIS.md) | Quantum logic, quantum probability and determinism, related to Symblic. Speculative. |
| [HPC-FOUNDATIONS.md](HPC-FOUNDATIONS.md) | Running Symblic on supercomputers and training with verifiable rewards. Proposals, none built as proposed. |
| [INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md](INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md), [EPISTEMIC-IMPROVEMENTS.md](EPISTEMIC-IMPROVEMENTS.md) | Philosophy of communication and epistemic logic proposed for the language. Speculative. |
| [SYMBLIC-BREAKTHROUGH-COMPENDIUM.md](SYMBLIC-BREAKTHROUGH-COMPENDIUM.md), [THE-OVERALL-BREAKTHROUGH.md](THE-OVERALL-BREAKTHROUGH.md) | Broad syntheses of the project; the titles are the original agent's. |
| [NATURAL-LANGUAGE-BRIDGE.md](NATURAL-LANGUAGE-BRIDGE.md), [STUDY-GUIDE.md](STUDY-GUIDE.md), [DEVELOPMENT-AND-USE-CASES.md](DEVELOPMENT-AND-USE-CASES.md) | A guide to thinking in Symblic, a tutorial and a roadmap; corrected, but AI-written. |
| [SYMBLIC-COMPLETE-MASTER-RECORD.md](SYMBLIC-COMPLETE-MASTER-RECORD.md), [SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md](SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md), [SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md](SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md) | Reports from a working dialogue of agents on 4 October; unreplicated figures. |

## Interfaces of the original host

| Document | What it is |
|---|---|
| [TERMINAL.md](TERMINAL.md) | The host's Symblic terminal page. **(host)** |
| [BROWSER-PROVIDERS.md](BROWSER-PROVIDERS.md) | ChatGPT and Gemini through a browser on the host, as typed providers. **(host)** |

## Images

`symblic-logo.svg` and the `symblic-minimal-*.svg` logo studies (commutative diagram, Frege, Gentzen, Quine, Tarski,
turnstile). Some documents mention PNG or JPEG versions and two further studies that are not in this repository.
