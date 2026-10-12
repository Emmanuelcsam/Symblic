# symblic/lang: functions, routines, modules and tests

`abstraction.py` adds four statements to the language (they are registered when `symblic.kernel.language` is
imported) and the standard library in `library/`.

```
function area(side: Number) -> Number = side ^ 2.               # one exact kernel expression

routine colour_of(thing: Text) -> one of {red, green, blue} do  # a typed model call with its own checks
  ask c: one of {red, green, blue} "What colour is {thing}?" with effort=high
  ensure c != blue else retry.
  return c.
end.

import units.                                                    # library/units.sym
import stats as st.                                              # qualified: st.variance(...)
import c_to_f, f_to_c from units.                                # selected names

test "a unit square has area 1" do
  assert area(1) = 1.
end.
```

- A **function** is decided by the kernel and may recurse (bounded depth). In the `verified` profile it cannot
  reach a model, even through another function.
- A **routine** runs its statements in a fresh scope; its asks go through the normal capsule, vote, replay and
  `ensure ... else retry` path. Within one run the same arguments return the recorded value without asking again.
- A **module** is a program that only declares things. Its source and SHA-256 are recorded in the run folder
  (`modules.json`), so a resumed or replayed run uses exactly the module it started with.
- A **test** is skipped in a normal run and run in its own scope by the `test` command.

## The standard library (`library/`)

| Module | Contents |
| --- | --- |
| `constants` | The SI defining constants as exact rationals, and exact derived ones. |
| `dates` | Proleptic Gregorian calendar arithmetic: leap years, day numbers, weekdays, adding days. |
| `units` | Exact conversions of length, mass, volume, pressure, energy and temperature, and term definitions that pin what each unit means. |
| `stats` | Exact variance, standard deviation, agreement measures (modal share, entropy, Fleiss' kappa) and exact binomial tails. |
| `records` | Field-by-field comparison of two records. |
| `graphs` | Reachability, cycles and undirected links over `edge` facts (Datalog). |
| `kinship` | Family relations derived from `parent` facts (Datalog). |
| `lab` | Laboratory recipe conventions (w/w, w/v, dry-weight basis, STP) and the arithmetic that follows from them. |
| `order` | Shares, order effects and the QQ gap for two yes/no questions asked in both orders. |
| `text` | Routines for everyday language work (yes/no, choose one, count, quote-checked numbers and items, bounded summaries) and source-witness helpers. These call models. |

Each module carries its own `test` blocks. Tests that call models (in `text`) need applicators; the kernel-only
tests run anywhere.

## Command line

```
python3 -m symblic.lang.abstraction lib                          # list the library
python3 -m symblic.lang.abstraction doc units                    # one module's names and notes
python3 -m symblic.lang.abstraction test units                   # kernel-only tests of a module or a file
python3 -m symblic.lang.abstraction test text --by ollama:qwen3:4b
python3 -m symblic.lang.abstraction certify text --cohort ollama:qwen3:4b --cohort command:my-agent
python3 -m symblic.lang.abstraction crystallise FILE --routine NAME --domain '[...]' --by ollama:qwen3:4b
```

`certify` runs a module's tests once per cohort of applicators (and can seal the outcome as a certificate,
see `symblic/kernel/certificates.py`); `crystallise` compiles a routine's agreed answers over a finite list of
inputs into a plain kernel function. Both call models through `symblic/providers`.

## Not included

`import "Saved name"` imports a program saved in the original host's program store; without that host there
are no saved programs, so such an import fails with a clear error. The `job` command was how the host's web
page started certify and crystallise jobs; it still works from the command line with a job folder.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/lang -t .
```
