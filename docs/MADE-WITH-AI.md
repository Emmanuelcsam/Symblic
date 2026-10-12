# Made with AI agents

Symblic was written by AI. This page says what that means, as precisely as the surviving records allow, so that you
can decide how much to trust each part.

## The short version

- **Every line of Symblic's code, documents and tests was written by AI coding agents.** One person directed the
  work in plain-language requests over roughly ten days, from 2 to 11 October 2026 (a few files are older; see
  [Older files](#older-files)), chose what to keep, and ran the machines. That person did not write the code and did
  not review most of it.
- **The agents checked each other, not a human expert.** Reviews were done by other AI agents and by the project's
  own tests. Tests written by the same agents that wrote the code can share their mistakes.
- **The essays are AI writing with unverified claims.** The long essays in [essays/](essays/README.md) were generated
  by Gemini. Several documents in [reference/](reference/README.md) are corrected versions of them; they are still
  speculative and are labelled at the top.
- **Treat Symblic as experimental.** It is published so that others can study it, test it and take it further.

## Who did what

The agents below appear in the records (names as the records give them). The records are incomplete, so this is a
description of roles, not an exact accounting of lines.

| Agent | Role in the records | Where it shows |
|---|---|---|
| **Claude** (Anthropic), mostly through Claude Code | Much of the language, the interpreter, the run records, spec sheets and the game kits, the autogen coordinator, many reference documents, the local-model measurements of 2026-10-11, and this publication pass (moving files, writing these pages). Also hand-answered some benchmark questions as one of the measured "applicators" | [reference/REPORT-2026-10-10.md](reference/REPORT-2026-10-10.md) (the continuation after Codex), [reference/LOCAL-BETA-REPORT-2026-10-11.md](reference/LOCAL-BETA-REPORT-2026-10-11.md), [reference/RESULTS.md](reference/RESULTS.md) §2 |
| **OpenAI Codex** (command-line agent) | The MICA contract-assembly releases, a frozen matched pilot, the prototype OS guest image, and independent audits of canonical forms, geometry, statistics and semantics | [reference/MICA.md](reference/MICA.md), [reference/REPORT-2026-10-10.md](reference/REPORT-2026-10-10.md) §2 and §5, [reference/reinforcements/](reference/reinforcements/), [reference/NOTES-2026-10-02.md](reference/NOTES-2026-10-02.md) |
| **Gemini** (Google), through the Gemini command-line agent and Google's Antigravity agent | The essays in [essays/](essays/README.md) and the first versions of the nine proposal documents reviewed in [reference/REVIEW-2.3.md](reference/REVIEW-2.3.md); reports from a working dialogue on 2026-10-04; and, as the `agy` engine, coding attempts in the autogen demonstrations | [reference/REVIEW-2.3.md](reference/REVIEW-2.3.md), [reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md](reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md) header, [reference/REPORT-2026-10-10.md](reference/REPORT-2026-10-10.md) §6 |
| **Mistral** (Vibe command-line agent) | Coordinated one beta trial on 2026-10-08, writing and running English statement files | [reference/SYMBLIC-CRITICAL-ANALYSIS.md](reference/SYMBLIC-CRITICAL-ANALYSIS.md) §2.1 |
| **ChatGPT** (OpenAI, in the browser) | Design reviews: 24 failure modes of the first autogen design, folded in before coding; one of three critics in the review rounds of an unpublished design (see [README.md](README.md)) | [reference/REPORT-2026-10-10.md](reference/REPORT-2026-10-10.md) §4 |
| **Claude in the browser and in cloud tasks** | Independent reviews (24 defects with reproductions for autogen; 5 for its second version); one of three critics in the same unpublished review rounds | [reference/AUTOGEN.md](reference/AUTOGEN.md) |
| **Small local models** (Qwen, Gemma, Llama, Granite and Phi models through Ollama) | The subjects of the measurements. They also wrote the unit code inside the result pages of [../kits/](../kits/README.md), each unit accepted only by code | [HONEST-ASSESSMENT.md](HONEST-ASSESSMENT.md) |

Several agents often worked at once, in separate checkouts, with one agent reviewing another's work before it was
applied. Some documents name a "peer session" (for example "c2", which built the abstraction layer of functions,
routines and modules in [reference/LANGUAGE-3.md](reference/LANGUAGE-3.md)); these were further agent sessions
working in parallel.

## Older files

Almost all of this repository was written between 2 and 11 October 2026; the language in `symblic/` was started on
2 October. The original host's version history shows a few older files:

- `web/studio/js/symblic/` (`parser.js`, `compiler.js`, `plan.js`, `settings.js`, `constants.js`, `utils.js`): the
  early Symblic text mode of the host's automation canvas, added in January 2026 and changed by only a few lines
  since.
- `web/studio/index.html`, `styles.css`, `js/ui.js`, `js/graph.js`, `js/constants.js` (the host's automation canvas)
  and `web/studio/symblic.html`, `js/symblic.js` (the studio page): first written in January 2026, then largely
  rewritten or extended in October.
- `symblic/sandbox/landlock.py`: adapted from a sandbox launcher that the host first used for another of its
  applications in September 2026.

## How the work was checked

- **Code checks over model claims.** The design rule of Symblic, "the model proposes, code decides", was also the rule
  for its own development: a change counted when tests, a harness or a recorded run said so.
- **Unit tests with fake models.** Each package has tests in [../tests/](../tests/) that run without any model. They
  were written by the same agents as the code.
- **AI reviewers.** Independent agent sessions reviewed designs and code, and their findings were recorded with the
  fix or the reason for refusing it (for example [reference/AUTOGEN.md](reference/AUTOGEN.md) "Review history" and
  [reference/reinforcements/](reference/reinforcements/)).
- **Recorded runs.** Measurements keep their failures in the denominator and say what they do not establish
  ([HONEST-ASSESSMENT.md](HONEST-ASSESSMENT.md)).
- **What did not happen:** no human expert reviewed the code, the mathematics or the security design, and nothing
  was audited by a third party.

## Documents that are AI essays or speculative AI writing

These documents are kept as a historical record of what the agents wrote. Their claims about mathematics, physics,
philosophy, security and performance are **not research results** and have not been verified by anyone outside
this project. Each one is labelled at the top.

| Documents | What they are |
|---|---|
| Everything in [essays/](essays/README.md) (15 essays) | Generated by Gemini through the Antigravity agent, 3 October 2026 and around it. Unreviewed. They describe features that do not exist, cite results nobody checked, and present analogies (string theory, quantum mechanics, fluid dynamics, philosophy) as if they were foundations. |
| [reference/GRAND-UNIFICATION-AND-STRING-THEORY.md](reference/GRAND-UNIFICATION-AND-STRING-THEORY.md), [reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md](reference/PHYSICS-AND-ADVANCED-MATHEMATICS.md), [reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md](reference/QUANTUM-FOUNDATIONS-OF-SYMBLIC.md), [reference/QUANTUM-DETERMINISM-ANALYSIS.md](reference/QUANTUM-DETERMINISM-ANALYSIS.md) | **Speculative AI writing** about string theory, grand unification, quantum mechanics and physics. Corrected by a later agent to separate what exists in code from analogy, but still speculative. Nothing in Symblic depends on these ideas. |
| [reference/HPC-FOUNDATIONS.md](reference/HPC-FOUNDATIONS.md), [reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md](reference/INTERSUBJECTIVITY-AND-HUMAN-COMMUNICATION.md), [reference/EPISTEMIC-IMPROVEMENTS.md](reference/EPISTEMIC-IMPROVEMENTS.md), [reference/CRITIQUE-AND-LIMITATIONS.md](reference/CRITIQUE-AND-LIMITATIONS.md), [reference/INTENSE-CRITIQUE-AND-LIMITATIONS.md](reference/INTENSE-CRITIQUE-AND-LIMITATIONS.md) | The rest of the nine proposal documents, corrected. [reference/REVIEW-2.3.md](reference/REVIEW-2.3.md) records that independent readers found 63 proposals and 120 factual errors in the nine; 12 proposals were built in a reduced form and 32 were rejected. |
| [reference/SYMBLIC-BREAKTHROUGH-COMPENDIUM.md](reference/SYMBLIC-BREAKTHROUGH-COMPENDIUM.md), [reference/THE-OVERALL-BREAKTHROUGH.md](reference/THE-OVERALL-BREAKTHROUGH.md), [reference/NATURAL-LANGUAGE-BRIDGE.md](reference/NATURAL-LANGUAGE-BRIDGE.md), [reference/STUDY-GUIDE.md](reference/STUDY-GUIDE.md), [reference/DEVELOPMENT-AND-USE-CASES.md](reference/DEVELOPMENT-AND-USE-CASES.md) | Corrected versions of essays. More grounded than the originals, still written by AI and unreviewed. |
| [reference/SYMBLIC-COMPLETE-MASTER-RECORD.md](reference/SYMBLIC-COMPLETE-MASTER-RECORD.md), [reference/SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md](reference/SYMBLIC-TOKEN-AND-ARCHITECTURE-REPORT.md), [reference/SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md](reference/SYMBLIC-SYSTEMS-AND-SECURITY-DEEP-DIVE.md), [reference/SYMBLIC-CRITICAL-ANALYSIS.md](reference/SYMBLIC-CRITICAL-ANALYSIS.md) | Reports written by agents about their own working sessions. Their figures are unreplicated. |

The rest of [reference/](reference/README.md) is design notes and records written alongside the code. They are more
reliable than the essays because they were checked against the code at the time, but they too were written by
agents, and some describe features of the original host that are not in this repository.

## The original request

The first request, on 2 October 2026, asked for a language in which "you use structured formal logic and direct
statements and the ai works with each statment", where "if i say four plus four it must always equal 8 nomatter what
agent i use", and where small local models could become far more capable by thinking hard on one statement, wiping
their context, and moving to the next. The full text, lightly edited to remove names of the private system, is in
[reference/NOTES-2026-10-02.md](reference/NOTES-2026-10-02.md) §1. What came of that idea, measured, is in
[HONEST-ASSESSMENT.md](HONEST-ASSESSMENT.md): the formal parts are deterministic; what models answer is not, and
the specification has to carry more of the work the smaller the model is.

## What was changed for publication

This repository was assembled on 2026-10-11 by AI agents from files on the original private machine:

- Every file that mentioned Symblic was copied and arranged into packages ([MAP.md](MAP.md) translates old names).
- Names of people, machines, network addresses, accounts, private paths, the host's other applications and the
  operator's own research were removed or replaced with neutral words: "the operator" for the person who ran it,
  "the host" for the main machine, `node-a` to `node-i` and `node-arm` for the worker machines. Quoted requests mark
  such edits with square brackets.
- Code that only ran inside the original host was moved to [../integration/host/](../integration/host/README.md).
- Passages that summarized a private text supplied for the project were removed; where a whole section went, the
  page says *Edited for publication*.
- A machine-generated inventory of the host's files was removed. LIFE, a never-run design for a self-running system
  on the original host, is kept in its own repository because it describes that private system in detail.
- Nothing was added to the measurements. Where a number is reported here that was only in a private session note, the
  page says so.
