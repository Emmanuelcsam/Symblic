# symblic/authoring: tools for writing Symblic

Everything here helps someone write Symblic text that is precise enough for small models, before or around a run.
Nothing here is required to run a program.

| module | what it does | runs a model? |
|---|---|---|
| `helpers.py` | a catalog of scoped EBNF grammars (`grammar/`: the portable program subset, logic formulas, proof commands) with parser conformance examples; `check` runs the authoritative parser for an entry point and returns its diagnostics; `command_menu` checks caller-written proof commands against a proof session. CLI: `python3 -m symblic.authoring.helpers catalog|export|check|menu` (also `tools/symblic grammar ...`) | no |
| `editor_diagnostics.py` | ranges (UTF-16 offsets, code-point line and column) for an editor to underline, from the native checker, the English compiler or the paper checker | no |
| `paper.py` | executable papers (`.symd`): Markdown whose fenced `symblic` blocks are the program, whose sections become each ask's context and whose definitions become terms; `lint` flags vague quantities; `reproduce` runs the paper with several groups of agents and traces each disagreement back to the paper's line. CLI: `python3 -m symblic.authoring.paper check|compile|reproduce` | only `reproduce` |
| `tighten.py` | the convergence compiler: probe every ask with a panel of models, classify each ask (converged, format, ambiguous, capability, divergent), and have a clarifier model propose a tighter wording that is then tested on a different panel; candidates stay separate from the adopted program | yes |
| `workcards.py` | typed forms that compile to checked programs: `slots` (a template with typed holes), `team` (a builder and named reviewers), `steps` (step constructions, `symblic/steps`); `run_card` runs one and keeps its records | `run` only |

Worked papers are in `docs/reference/papers/`; workcard requests in `examples/workcard-*.json` and
`examples/steps-parcel.json`.

## Status

`helpers.py`, `editor_diagnostics.py`, `paper.py` (compile, check, lint) and `workcards.py` are deterministic and
tested. `paper.reproduce` and `tighten.py` measure models and are experimental: the evidence behind the convergence
compiler is one small pilot (2026-10-02, described in `tighten.py`), and its diagnoses are heuristics. `tighten.py`'s
default clarifier names the `claude` engine, which this repository's applicators reach only through a configured
command (`command:NAME`, see `symblic/providers/applicators.py`).

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/authoring -t .
```

Fake models only. One test runs `tools/symblic grammar catalog`. The host-only adoption route test is
`tests/integration/test_symblic_tighten_api.py` (skipped without that host).
