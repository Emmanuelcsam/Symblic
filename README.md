# Symblic

Symblic is a small programming language for getting checked work out of language models, including small ones
that run on an ordinary computer. A program is a list of statements. Formal statements (arithmetic, logic rules,
geometry, data) are computed exactly by an interpreter written in Python. Each `ask` statement is sent to a model
in a **fresh context** with a typed answer shape, and **code checks every answer** before the program may use it:
types and ranges, examples, JavaScript run in a sandbox against test cases, exact rational arithmetic, logic rules.
An answer that fails is retried with the failure as feedback, or the run stops and says why.

The model proposes; code decides.

```symblic
ask root: Int in 1..9 "Find the positive integer whose square is nine."
ensure root * root = 9 else retry.
show root.
```

Here the model chooses `root`, the interpreter checks `root * root = 9`, and only a checked value is shown. Every
call is recorded, so a finished run can be replayed with no model. The formal steps are exact: two all-formal test
programs gave the same fingerprints on all eight machines they were run on (x86 and ARM, three Python versions; on
2026-10-02, with an earlier version of the interpreter; this repository reproduces both fingerprints).

> **Status: experimental, and written entirely by AI agents.** Every line of Symblic's code, documents and tests
> was written by AI coding agents directed by one person, almost all of it over about ten days in October 2026. No
> human has reviewed most of it. It was built and measured inside one private machine setup that is not part of
> this repository; the parts that only worked there are marked. Read [Made with AI agents](#made-with-ai-agents) and
> [docs/HONEST-ASSESSMENT.md](docs/HONEST-ASSESSMENT.md) before you rely on anything here.

## What it is good for, and what it is not

Based on what was measured with small local models (details and numbers in
[docs/HONEST-ASSESSMENT.md](docs/HONEST-ASSESSMENT.md)):

- **Good for (measured):** turning a precise specification into many checked builds. A *spec sheet* describes a
  file as small units, each with a contract and examples; a model writes the units one at a time and code decides
  what is kept. The sheet and its tests are the asset; models of a similar size can be swapped, but smaller models
  needed the sheet reworded (numbered steps for 2-3B models, exact code for 1B and below). Seven builds of one 39-unit
  game level by 0.5B to 4B models all passed the same 68-check test harness, and the assessment says how much of the
  code each sheet already contained.
- **Good for (by design):** keeping the exact parts exact. Arithmetic, logic and geometry never go through a model.
- **Probably good for (not measured directly):** letting a stronger planner (a person or a large model) write the
  specification once, and letting free, offline small models carry it out with every step checked; porting code
  where the examples carry over.
- **Not good for:** open-ended work, or any algorithm the person writing the specification could not already state.
  The smaller the model, the more of the answer the specification has to contain: the 1B and 0.5B models only
  succeeded when the sheet gave them the code to copy, so those runs test faithful copying, not ability.
- **Not good for:** debugging unknown code, or anything where writing the code takes less time than writing the
  specification and its checks.
- **Not shown:** that Symblic makes a small model as capable as a large one, or that splitting a task into smaller
  parts helps a model that cannot write the part (in the one measured case it did not).

## Try it in ten minutes

You need Linux and Python 3.12. The interpreter uses only the Python standard library. JavaScript checks also need
Node.js (tested with 22.17; other versions are not refused, but untested; `SYMBLIC_NODE` picks the binary) and
Linux 6.7 or newer (the sandbox uses Landlock network rules); without Node.js or Landlock those checks report
"unavailable" instead of passing.

Get the code (clone this repository with the URL on its GitHub page, or download it) and run these from the
repository folder:

```bash
# 1. No model: check a program, then run one that is decided entirely by the interpreter.
tools/symblic check examples/10-kernel-identity.sym
tools/symblic run examples/10-kernel-identity.sym --max-calls 0      # ends with: done: fingerprint fff6d4efbecb4a3a

# 2. No model: see exactly what a model would be sent for the program above, without sending it.
printf '%s\n' 'ask root: Int in 1..9 "Find the positive integer whose square is nine."' \
              'ensure root * root = 9 else retry.' 'show root.' > root.sym
tools/symblic preview root.sym --by ollama:qwen3:4b-instruct

# 3. No model yet: let a stand-in script answer the ask, so you can see the check and the replay at work.
SYMBLIC_COMMAND_STAND_IN="python3 $PWD/examples/stand-in-answer.py" \
    tools/symblic run root.sym --by command:stand-in --dir run0    # ends with: done: fingerprint ad282d55e1782c53
tools/symblic replay run0                                           # 0 calls (1 replayed): no model, no script

# 4. With a local model: install Ollama (https://ollama.com), then
ollama pull qwen3:4b-instruct
tools/symblic run root.sym --by ollama:qwen3:4b-instruct --dir run1   # asks the model, checks the answer
tools/symblic replay run1                                            # the same run again, no model
```

Step 3's script answers 3 unless you give it another number (`examples/stand-in-answer.py 4` answers 4, and the
check refuses it). Step 4 is the real thing, but note: **nothing in this repository was run against a model while it was being prepared for
publication.** The Ollama applicator was rewritten for publication and is tested only against a fake Ollama server
([symblic/providers/](symblic/providers/README.md)); the measurements in
[docs/HONEST-ASSESSMENT.md](docs/HONEST-ASSESSMENT.md) were made with the original code.

`--by` names an *applicator*: `ollama:MODEL` (an Ollama server; `SYMBLIC_OLLAMA_HOSTS` lists servers, default
`127.0.0.1:11434`) or `command:NAME` (any program you configure as `SYMBLIC_COMMAND_NAME`, for example an agent CLI
or the stand-in above). `fake` answers only for Python callers that pass scripted answers
(`Applicators(fake=FakeApplicators(...))`, as the tests do); from the command line every `fake` call fails on
purpose. See [symblic/providers/](symblic/providers/README.md). More to try:

- [examples/](examples/README.md): small programs, plain-English statement files, delegation tasks and records of
  what small models built, each marked "no model" or "asks a model".
- [kits/kirby/](kits/kirby/README.md): the full spec-sheet kit behind the measurements above (a 39-unit game level,
  a reference implementation, a strict harness, and the seven pages local models built). Its checks run with no model.
- [web/academy/](web/academy/README.md): a self-paced course on the language (lessons with checkpoints, flashcards,
  drills) with a reader for this repository's documents; it runs as static files from a served checkout. Its lessons
  were written by AI agents and have not been reviewed.
- `tools/symblic --help` lists every command.

Run the tests of one package with `DASH_TEST=1 python3 -m unittest discover -s tests/<package> -t .` (for
example `tests/kernel`). They use fake models and temporary folders; no test calls a real model. `DASH_TEST=1`
tells the code it is under test (no systemd scopes, no real kernel builds, no live model inventory). The whole suite
has about 4,560 tests and takes from about 45 minutes to two hours on a 6-core machine, depending on load and on
where temporary files go; [tests/README.md](tests/README.md) says how to run it faster and what is skipped.

## What is in this repository

Every folder below has a README; [symblic/README.md](symblic/README.md) shows how the subpackages fit together.

| Path | What it is |
|---|---|
| [`symblic/kernel/`](symblic/kernel/README.md) | The language: parser, checker, exact evaluator, interpreter, run records, replay. Start here. |
| [`symblic/providers/`](symblic/providers/README.md) | How an `ask` reaches a model: Ollama over HTTP, a configured command, or a fake. |
| [`symblic/js/`](symblic/js/README.md) | The test oracle for model-written JavaScript: runs it against examples in a sandbox (bundles the Acorn parser). |
| [`symblic/sandbox/`](symblic/sandbox/README.md) | A Linux Landlock and seccomp launcher for untrusted programs. |
| [`symblic/adapters/`](symblic/adapters/README.md) | Exact builtins: geometry, drawings, linear algebra, finite logic, proof checking, quantities. |
| [`symblic/lang/`](symblic/lang/README.md) | Functions, routines, modules, tests and the standard library (`library/*.sym`). |
| [`symblic/spec/`](symblic/spec/README.md) | Spec sheets: a file described as units with contracts and examples, built unit by unit. |
| [`symblic/english/`](symblic/english/README.md) | Programs written as short English sentences, each compiled to a checked statement. |
| [`symblic/steps/`](symblic/steps/README.md) | Step constructions: the model only picks the number of the right expression for each step. |
| [`symblic/authoring/`](symblic/authoring/README.md) | Writing aids: workcards, papers (`.symd`), statement tightening, editor diagnostics. |
| [`symblic/delegate/`](symblic/delegate/README.md) | Hand one bounded task (extract, classify, quote, prove one step) to a small agent and get a checked value back. |
| [`symblic/graph/`](symblic/graph/README.md) | Small agent workflows in which every node is a checked program. Prototype. |
| [`symblic/mica/`](symblic/mica/README.md) | Checked assembly of small JavaScript programs from function contracts. Experimental. |
| [`symblic/autogen/`](symblic/autogen/README.md) | Regenerate, split and hand off agent attempts until code accepts them. Experimental. |
| [`symblic/linear/`](symblic/linear/README.md), [`symblic/constructor/`](symblic/constructor/README.md) | A solver (Z3) instead of a model for asks whose checks are linear arithmetic, and its durable journal. Experimental. |
| [`symblic/intent/`](symblic/intent/README.md), [`symblic/forge/`](symblic/forge/README.md) | Recording what was asked, and a requirements workbench, before any code is written. Experimental. |
| [`symblic/inquiry/`](symblic/inquiry/README.md), [`symblic/memory/`](symblic/memory/README.md), [`symblic/policy/`](symblic/policy/README.md) | Choosing the next check, keeping claims between runs, choosing a routing policy honestly. Research prototypes. |
| [`symblic/bench/`](symblic/bench/README.md), [`symblic/experiments/`](symblic/experiments/README.md), [`symblic/distill/`](symblic/distill/README.md) | Measurement runners, finite research experiments, and a fine-tuning pipeline (one tiny pilot, no claim). |
| [`symblic/portable/`](symblic/portable/README.md) | Run the pure interpreter on another machine and compare fingerprints. |
| [`symblic/os/`](symblic/os/README.md) | A prototype command layer driven by Symblic. Not an operating system; its guest image is a stub. |
| [`tools/`](tools/) | Command-line entry points (`tools/symblic`, `symblic-task`, `symblic-workcard`, ...) and scripts. |
| [`examples/`](examples/README.md), [`kits/`](kits/README.md), [`benchmarks/`](benchmarks/README.md) | Programs, complete build kits with harnesses, and benchmark fixtures. |
| [`web/`](web/) | The browser pages (editor, hub, records, and the [Academy](web/academy/README.md), a self-paced course). They were served by the original host; the editor needs its HTTP API, while most of the hub and the Academy work as static files. |
| [`integration/host/`](integration/host/README.md) | Code that only ran inside the original host (HTTP routes, schedulers). Kept for reference; not runnable here. A few host-only features of the packages import it lazily; nothing in the steps above needs it. |
| [`tests/`](tests/README.md) | One folder per package; `tests/integration/` covers host-only code and skips where the host is missing. |
| [`docs/`](docs/README.md) | The language reference, measurements, design records, AI essays, and the [map of old names](docs/MAP.md). |

## Made with AI agents

**Symblic was written by AI.** Every line of its code, its documents and its tests was written by AI coding
agents: Claude models (in Claude Code and in the browser), OpenAI Codex, Google's Gemini models (through the Gemini
and Antigravity command-line agents), Mistral's command-line agent and ChatGPT in the browser. One person directed
them over roughly ten days (2 to 11 October 2026), in plain-language requests, and decided what to keep; that
person did not write or review most of the code. A few files are older (from January and September 2026); see
[docs/MADE-WITH-AI.md](docs/MADE-WITH-AI.md#older-files). The long essays in [`docs/essays/`](docs/essays/README.md)
were generated by Gemini and contain claims that nobody has verified; several documents in `docs/reference` are
corrected versions of them and are labelled as speculative.

What this means for you:

- **Treat it as experimental.** The unit tests pass with fake models (two tests are marked as expected failures
  and some host-only tests skip; see [tests/README.md](tests/README.md)), but tests written by the same agents that
  wrote the code can share their mistakes.
- **Numbers come from small samples**, mostly one run each, on one private set of machines. They are recorded with
  their limits; none is a benchmark result.
- **The documents can overstate.** Where a document and the code disagree, the code wins. The essays are a
  historical record of what the agents claimed, not a description of what exists.

[docs/MADE-WITH-AI.md](docs/MADE-WITH-AI.md) has the full account: which agent did what, how the work was checked,
and which documents are speculative.

## More

- [docs/HONEST-ASSESSMENT.md](docs/HONEST-ASSESSMENT.md): what was measured with local models, with every number
  sourced, and what the results do not show.
- [docs/reference/README.md](docs/reference/README.md): the language reference and design records, grouped by topic;
  [docs/reference/SPEC.md](docs/reference/SPEC.md) is the language specification.
- [CITATIONS.md](CITATIONS.md): the papers, repositories and software Symblic draws on, with verified links.
- [CONTRIBUTING.md](CONTRIBUTING.md): this project is looking for maintainers to take it over.

## License

MIT; see [LICENSE](LICENSE). The bundled Acorn parser (`symblic/js/acorn.js`) is MIT-licensed by its own authors
([`symblic/js/acorn-LICENSE.txt`](symblic/js/acorn-LICENSE.txt)). The choice of license for Symblic itself is the
current maintainer's to confirm.
