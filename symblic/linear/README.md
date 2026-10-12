# symblic/linear: a solver instead of a model for linear asks

**What this package explores.** A Symblic `ask` normally goes to a language model, and the kernel then checks
the answer against the `ensure` lines anchored to it. When those checks are plain linear arithmetic over the
answer's integer, rational and Boolean fields, a model is not needed: an SMT solver can *construct* an answer
that satisfies them. This package compiles exactly that fragment, lets Z3 propose at most two assignments in
an isolated worker process, and keeps an assignment only after the native kernel has re-checked the original
`ensure` lines on it. The solver never decides anything on its own: its "unsat" and "unique" verdicts are
reported as unverified solver claims.

**Status: prototype, optional.** Z3 is not a dependency of this repository. The compiler and refusal rules are
tested through the constructor tests with fake workers and fake runtimes; the real Z3 path was only run on the
development machine and is not covered by automated tests. In the development notes this prototype is called
"D10"; some recorded profile strings still contain that name.

## The modules

| Module | What it does |
| --- | --- |
| `constructor.py` | The fragment compiler and the host side: `assess()` for a small program, `assess_ask()` for one ask inside a run (used by `symblic/constructor`), `validate_witness()`, the fixed `REASONS` table of refusal codes, and the worker launcher. |
| `worker.py` | The worker process. Reads one JSON request, verifies the pinned Z3 package file by file, applies OS limits, loads exactly that libz3, asks for up to two distinct assignments and prints one JSON reply. Imports only the standard library and the pinned `z3`. |
| `resources.py` | Optional memory admission: reads the cgroup v2 memory facts of the current process and refuses unless it runs in a capped envelope with room for the worker. Starts nothing, writes nothing. |
| `z3-requirements.lock` | The hash-pinned requirement for the optional solver (`z3-solver==4.15.4.0`). |

## What the fragment accepts

`given` scalars, then one `ask` whose type is a Boolean, an integer, a rational number or a record of those
(with optional bounds), then untyped `let` bindings and `ensure` lines. Only `ensure ... else retry` lines that
read the answer become solver constraints; `else warn` lines are evaluated on each candidate afterwards.
Products of two unknowns, division by an unknown, `else fail` checks, named types, ask options and sources,
and everything else is refused before the worker starts, each with its own code (`nonlinear_product`,
`unanchored_hard_check`, ...).

## Trying it with a real solver

The provisioning tool accepts exactly the environment layout `uv venv` writes (its `pyvenv.cfg` fields are
checked one by one), built from the system CPython at `/usr/bin/python3.X`:

```sh
env="$HOME/.local/share/symblic/linear/environments/z3-4.15.4.0-py3.12-v1"   # match your Python minor version
umask 077
uv venv --no-managed-python --no-python-downloads --python /usr/bin/python3.12 "$env"
uv pip install --python "$env/bin/python" --no-deps --require-hashes --link-mode copy \
  -r symblic/linear/z3-requirements.lock
find "$env" -exec chmod go-w -- {} +
```

Then write a review record (`version`, `worker_sha256` of `symblic/linear/worker.py`,
`requirements_lock_sha256` of the lock file, `package_version`) and publish the runtime record:

```sh
/usr/bin/python3.12 -I -S -B tools/scripts/symblic_linear_provision.py inventory review.json
/usr/bin/python3.12 -I -S -B tools/scripts/symblic_linear_provision.py publish review.json
python3 -m symblic.linear.constructor program.sym --enable --runtime ~/.local/share/symblic/linear/runtime.json
```

The provisioning tool reads and hashes files only; it never installs, imports or runs the package. The
details and the refusal rules are in `docs/reference/CONSTRUCTOR-PROVISIONING.md`.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/linear -t .
DASH_TEST=1 python3 -m unittest discover -s tests/constructor -t .
```

Run from the repository root. `tests/linear` checks the provisioning tool against fake environments in
temporary folders; `tests/constructor` exercises the compiler, the refusals and the journaled path with a fake
worker. No test needs Z3.

Further reading: `docs/reference/CONSTRUCTORS.md`, `docs/reference/CONSTRUCTOR-PROVISIONING.md`.
