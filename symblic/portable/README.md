# symblic/portable: run the pure kernel on another machine and compare

**What this package explores.** Symblic's results are exact values with fingerprints, so the same program should
give the same observable output on any machine that runs the same kernel source. This package tests that claim
in a small, honest way: it exports the kernel's pinned source files as one reproducible zip, runs a fixed corpus
of 16 pure programs inside the unpacked bundle in a closed child process, and compares the reports from
different machines.

**Status: tested, with a small measurement.** The tests build, unpack and run real bundles. During development,
an earlier snapshot of this code (before the move into this package layout) passed all 16 corpus cases on three
Linux machines: CPython 3.12.3 on x86_64, 3.13.5 on x86_64 and 3.13.5 on aarch64. This package layout has only
been verified on the machine it was prepared on. A matching corpus is evidence about those 16 programs on
those runtimes, not a proof that every program behaves identically everywhere.

## The modules

| Module | What it does |
| --- | --- |
| `export.py` | `build()` writes the reproducible zip; `verify()` unpacks it into a temporary folder and runs the runner as a child process; `compare()` checks several verification reports against each other. Also the command line. |
| `runner.py` | Copied into every bundle as `portable_runner.py`. Checks every hash, limits itself (memory, CPU, one core), refuses network, subprocesses and writes through a Python audit hook, then runs the corpus (and optionally your program) with execution pins and no model provider. Also `runtime()` and `validate_runtime()`. |

## What goes into a bundle

- The files named by the registry in `symblic/kernel/execution_pins.py` (`REQUIRED_FILES`, `ASSET_FILES`)
  and the standard-library modules in `symblic/lang/library/`. The registry is read as data (its finite set
  literals), never executed. The package markers (`__init__.py`) of those folders are added so the kernel
  imports inside the bundle.
- `corpus.json`: 16 programs with their expected outputs (exact rationals, Unicode identity, Datalog, a library
  import, a deliberately failing assertion, branches, loops, quantifiers, recursion, a checked proof, unit
  conversion and more; see `CORPUS` in `export.py`).
- `manifest.json`: the runtime the bundle targets and the SHA-256 and size of every file. Its own SHA-256 is
  what you pass to `verify`.

Inside the bundle, programs that use `ask`, `observe`/`act`, JavaScript or the linear solver are refused.

## Command line

```
python3 -m symblic.portable.export runtime > runtime.json
python3 -m symblic.portable.export build --source-root . --output kernel.zip
python3 -m symblic.portable.export verify kernel.zip --manifest-sha256 HASH_PRINTED_BY_BUILD > here.json
python3 -m symblic.portable.export run kernel.zip program.sym --manifest-sha256 HASH [--inputs-json inputs.json]
python3 -m symblic.portable.export compare here.json there.json
```

To target another machine, run `runtime` there and pass the file to `build --target-runtime`. Supported
targets: CPython 3.11 to 3.13 on little-endian Linux, x86_64 or aarch64. A bundle built for a runtime you have
not verified on is labelled "unmeasured".

## Limits worth knowing

- The manifest digest proves integrity, not origin. Move it to the other machine over a channel you trust.
- The audit hook keeps the pure kernel from reaching out by accident. It is not a sandbox for hostile code.
- One verification needed about 13 s of CPU on the development machine; the runner allows 60 s of CPU
  (`runner.CPU_SECONDS`) and `verify` waits at most 180 s (`export.VERIFY_TIMEOUT_SECONDS`).
- Bundles made from different source trees, Python versions or Unicode versions have different kernel
  identities; run folders are never resumed across identities.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/portable -t .
```

Run from the repository root. The suite builds and runs about ten real bundles, so it takes a few minutes.
It needs no network and no model.

Further reading: `docs/reference/PORTABLE-FINITE.md`.
