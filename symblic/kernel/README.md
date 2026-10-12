# symblic/kernel: the language, the kernel and the interpreter

This package is the core of Symblic. It parses and checks programs, evaluates every formal statement exactly,
sends each `ask` to an applicator (a model, through `symblic/providers`), checks the answers, and records
everything a run did so that it can be resumed, replayed and compared.

Everything here runs with nothing but this repository and Python 3.12 (standard library only). Model calls
happen only through an applicators object you pass in; the tests use fakes.

## The modules

| Module | What it does |
| --- | --- |
| `language.py` | The language and the kernel: `parse`, `check`, the exact evaluator (`Kernel`), types and `coerce`, canonical values and fingerprints, the capsule an applicator is shown (`capsule`), reply parsing (`read_answer`), consensus and model lineage, applicator specs (`parse_applicator`) and `kernel_id()`. No I/O. |
| `run.py` | The interpreter: `Run(source, inputs, applicators, options, folder).execute()`. Calls, repairs, votes, retries, resumes and the run folder. `python3 -m symblic.kernel.run --dir FOLDER` runs a saved program folder. |
| `diagnose.py` | What the kernel can say about a failed check without a model: the repair text a model sees, and warnings about checks that accept any answer. |
| `evidence.py` | Observation records: which applicator answered, which model it reported, its lineage (for counting independent model families). |
| `epistemic.py` | Claim provenance: where each value came from (premise, observation, model proposal, derivation) and how a model's context is packed from those claims. |
| `profiles.py` | Execution profiles (`legacy`, `explicit`, `verified`) and recorded, auditable coercion of answers. |
| `json_schema.py` | The closed JSON Schema subset behind `Code json` answers. |
| `grounding.py` | Source witnesses: checks that a quoted span really is in the source at the stated offsets. |
| `effects.py` | The `observe` and `act` statements: typed calls to capabilities a host provides, at most once, recorded in a ledger. |
| `lockfile.py` | A finished run frozen into one file that replays with no model (`python3 -m symblic.kernel.lockfile`). |
| `certificates.py` | Sealed test outcomes per cohort of applicators, and routing built from them. |
| `execution_pins.py` | A receipt that binds a reviewed program to the exact source files that will run it; refuses drift before any call. |
| `identity.py` | Import identity: proves that the code a process loaded is the code on disk (used by the pins). |
| `process_limits.py` | Child processes with CPU, memory and wall-time limits (kernel-only tests, previews, the JavaScript sandbox). |
| `preview.py` | `tools/symblic preview`: runs a program up to its first `ask` in a bounded child and returns that ask's exact capsule; no model is called. |
| `context_packs.py` | A bounded, read-only summary of a few named source files for an agent task (`python3 -m symblic.kernel.context_packs`). |
| `embed.py` | A small version-pinned API (`check`, `run`) for programs that embed Symblic. |

## How the pieces fit

```
source text ──parse/check (language.py)──► program
                                             │
          Run (run.py) walks the statements ─┤
             formal statement ──► Kernel (language.py): exact value, fingerprint
             ask ──► capsule (language.py) ──► applicators.call(request)   (symblic/providers)
                       ◄── reply ──► read_answer + coerce (language.py, profiles.py)
                       ──► ensure / vote / repair / retry (run.py, diagnose.py)
             observe / act ──► host capability (effects.py)               (only if you supply a host)
             function / routine / import / test ──► symblic/lang
                                             │
             run folder: program.sym, meta.json, trace.jsonl, calls.jsonl, state.json, kernel.json,
                         modules.json, effects.jsonl, artifacts/
                                             │
             lockfile.py (replay with no model) · certificates.py · execution_pins.py + identity.py
```

A run folder is the record of one run. `calls.jsonl` keys every model call by a hash of exactly what was sent,
so a resumed or replayed run reuses answers instead of asking again. `kernel.json` names the kernel that did the
work: a folder recorded by another kernel is never continued silently.

## Kernel identity

`kernel_id()` returns the versions a result depends on (language, canonical form, parser, adapters, the Unicode
database of your Python, the JavaScript adapter's assets and the Node version, ...) and a 16-hex-digit `id`. Two
runs are compared, and a folder is resumed, only under the same `id`. Consequences worth knowing:

- Machines with a different Node.js version (or none) have a different `id`, because JavaScript checks may give
  different results there.
- This public release has a new identity: moving the code into this package changed the hashed asset files.
  Run folders recorded by the private development system cannot be resumed here, and they are not included.

## What is experimental, unmeasured or host-dependent

- `observe` / `act` need a host object that provides capabilities (`options['effects']`); this repository ships
  none. The ledger and flow labels are tested with a fake host only.
- The `delegate` statement needs applicators with a `delegate()` method (an agent runner); the shipped
  applicators have none, so it refuses.
- `run_folder()` and `lockfile.py` validate runs written from English instructions with the English front end's
  pure half, `symblic/english/authoring.py`; nothing in this package imports `integration/host/`.
- Execution pins, import identity and certificates are integrity and compatibility checks. They are not
  signatures, sandboxes or proof of correctness, and their own docstrings say exactly what they do not cover.
- The `verified` profile and the evidence/claim records describe what was checked; they never measure truth or
  model reliability.
- Importing the kernel costs about two to three seconds of CPU in a fresh process (measured on the development
  machine): `execution_pins.py` hashes every registered source file and compiles it once to compare it with the
  cached bytecode, so a later pinned run can refuse stale code. It happens once per process.
- Comments in `language.py` and `run.py` often cite dated design reviews ("2026-10-03 review", "lane C"). They are
  the development history of these rules, kept because they explain why a rule exists.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/kernel -t .
```

Run from the repository root. The suite uses fake applicators, temporary folders and fake hosts; it starts no
model and needs no network. JavaScript tests skip when Node.js or Landlock network rules are not available.
Tests of the original host's API live in `tests/integration` and skip without that host.

Language reference: `docs/reference/SPEC.md`, `docs/reference/LANGUAGE-3.md`, `docs/reference/INTERPRETER.md`,
`docs/reference/EFFECTS.md`, `docs/reference/EXECUTION-PINS.md`.
