# symblic/adapters: exact, bounded builtins the kernel can call

An adapter is a small module that gives Symblic programs a family of builtin functions which are computed
exactly by code, never estimated by a model: geometry, drawings, linear algebra, logic and proof checking,
knowledge models, measured quantities. A model may *propose* an argument (a shape, a proof); the adapter
*decides*.

All of them follow the same rules:

- **Exact.** Numbers are Python `int` or `Fraction`; floats are refused. Results are canonical kernel values,
  so their fingerprints are the same on every machine.
- **Bounded.** Every call is charged to the kernel's step budget before the work it pays for, and every input
  has hard size and bit-length limits. Exceeding one is a refusal (`kind='budget'`), never a partial answer.
- **Loaded on first use.** `symblic/kernel/language.py` imports each adapter the first time a program calls one
  of its builtins (the `ADAPTERS` table there, plus small wrappers for `render`, `variational` and `transport`),
  and importing an adapter registers nothing. The one exception is `geometry.py`, which the kernel imports at
  load and which adds its builtins to the kernel's table then.
- **Versioned.** Each module has a `VERSION` that is part of the kernel identity (`kernel_id()`), so a change in
  an adapter's behaviour is a change of the kernel.

## The modules

| Module | Builtins | What it decides |
| --- | --- | --- |
| `geometry.py` | `solid_check`, `is_cube`, `cube`, `congruent`, `congruent_points`, `similar`, `sameness`, `canonical_shape`, `shape_facts`, `shape_signature`, `draw_shape` | Whether a vertex/face record is a valid convex solid, and whether two shapes are similar, congruent or identical, by exact search. |
| `render.py` | `flower`, `rose`, `polygon`, and the `draw` statement | Deterministic SVG: the same arguments give the same bytes everywhere. |
| `variational.py` | `quadratic_minimize`, `quadratic_verify` | The exact minimum of a symmetric positive-definite quadratic, with a re-checkable receipt. |
| `projection.py` | `reconcile` | The least-change adjustment of numbers so that they satisfy linear constraints exactly. |
| `transport.py` | `wasserstein1` | The exact earth mover's distance between two finite 1-D distributions. |
| `discrete.py` | `ising_minimize`, `ising_energy` | Exact ground states of a small Ising model (at most 16 spins), by exhaustive enumeration. |
| `knowledge.py` | `knows_event`, `common_partition`, `common_knowledge`, `posterior_given`, `agreement_process` | Aumann's partition model of knowledge and the Geanakoplos-Polemarchakis announcement process, on finite state sets. |
| `operators.py` | `is_projector`, `commutator`, `commutes`, `ordered_probability` | Exact projector algebra for the projector model of question order. |
| `quantities.py` | `quantity_*` | Interval arithmetic with SI dimensions and declared units. |
| `proof.py` | `proof_check`, `proof_valid`, `proof_parse`, `proof_render` | Proof terms for intuitionistic propositional logic: the trusted checker. |
| `proof_steps.py` | `proof_steps_check`, `proof_steps_valid` | Line-by-line natural-deduction certificates. |
| `proof_session.py` | `proof_session_*` | Building a proof one checked inference at a time, each in a fresh model context. |
| `proof_command.py` | `proof_session_command`, `proof_command_frontier` | A one-line text format for proposing one inference. |
| `finite_logic.py` | `finite_parse`, `finite_expand`, `finite_check`, `finite_steps_check` | Quantified statements over small, explicitly listed domains. |
| `proof_adapter.py` | (all proof builtins) | The bridge that charges the step budget and calls the checkers above. |
| `logic.py` | (Python API: `compile_task`) | Compiles named premises and a goal into a Symblic program in which a model builds a proof and the kernel checks it. |

The JavaScript adapter lives in its own package, `symblic/js`.

## What these results do and do not establish

Each module's docstring ends with a plain statement of its limits. In short: a result is exact *for the input
the program supplied*. That the input encodes the real problem (that the matrices describe a person's beliefs,
that the premises say what the author meant, that a measurement is right) is the author's claim, not something
an adapter checks. The proof checkers never search for proofs; they only check proofs someone else wrote.

The adapters were written for Symblic's own tests and design studies. They are exhaustively tested on small
inputs, but they are not optimized and have not been benchmarked against specialised libraries.

## Tests

```
DASH_TEST=1 python3 -m unittest discover -s tests/adapters -t .
```

The documented examples in `docs/reference/DISCRETE.md`, `KNOWLEDGE.md` and `OPERATORS.md` are run by these
tests, so the documents and the code cannot drift apart silently.
