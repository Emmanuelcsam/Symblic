# Exact ground states of a small Ising model

`symblic/adapters/discrete.py` finds the lowest energy of an explicitly supplied Ising model with at most 16
spins by evaluating every state:

\[
E(s)=-\sum_i h_i s_i-\sum_{i<j} J_{ij}\, s_i s_j,\qquad s\in\{-1,+1\}^n .
\]

Every coefficient is an exact rational and every state is evaluated with exact arithmetic, so the
minimum is exact for the supplied numbers. No floating point, annealing, sampling, heuristic or model
is involved.

## Interface

`FUNCTIONS` maps two builtin names to their implementations; the kernel registers them. Importing the
module registers nothing and does no I/O.

- `ising_minimize(h, J)` returns the record described below.
- `ising_energy(h, J, s)` returns the exact energy of one state `s`: a list of n values, each -1 or 1.

`h` is a list of n numbers. `J` is a list of n rows of n numbers, exactly symmetric, with zeros on
the diagonal; `J[i][j]` couples spins i and j and enters the energy once per pair. Both builtins accept
exactly the same `(h, J)`. Python hosts may call `minimize_ising(h, J, budget=None, node=None)` and
`state_energy(h, J, s, budget=None, node=None)` directly.

Sign convention: a positive `J[i][j]` favours equal spins (ferromagnetic), a negative one opposite
spins (antiferromagnetic), and a positive `h[i]` favours `s[i] = 1`. A model written with a sum over
all ordered pairs i ≠ j counts each pair twice; its coupling matrix must be doubled to give the same
energies here. A model with a plus sign in front of a sum needs that sum's coefficients negated. A
problem over 0/1 variables must first be rewritten with x = (1 + s)/2; the constant this produces is
not part of E, so the minimum value then differs from the 0/1 problem's by that constant.

## The result

| Field | Meaning |
| --- | --- |
| `energy` | The minimum of E over all 2^n states, exact: an integer or a fraction |
| `degeneracy` | How many states attain it |
| `states` | Ground states, each a list of -1/+1 by spin, in lexicographic order with -1 < +1; at most 16 of them, the first 16 in that order |
| `truncated` | True when `degeneracy` is above 16; `states` then lists only the first 16 |
| `spins` | n |
| `method` | `"exhaustive"` |

Lexicographic order compares spin 1 first: `[-1, -1, 1]` comes before `[-1, 1, -1]`. With h = 0,
J = 0 and five spins every one of the 32 states is a ground state: `degeneracy` is 32, `states` holds
the 16 states whose first spin is -1, and `truncated` is true.

## Domain, limits and refusals

| Constant | Value | Meaning |
| --- | ---: | --- |
| `MAX_SPINS` | 16 | Number of spins n, at least 1 |
| `MAX_STATES` | 16 | Ground states listed in `states` |
| `MAX_BITS` | 4096 | Bits of every numerator and denominator, of the common denominator of h and J, and of every coefficient multiplied by that common denominator |

These are hard limits; a call cannot raise them. A refusal raises an error of the kind below and
returns nothing, never a partial or approximate answer.

| Kind | Cause |
| --- | --- |
| `type` | A float, bool, Decimal, text, set, record or malformed fraction where a number or spin belongs; a wrong shape or length; no spins at all |
| `budget` | More than 16 spins; a number, the common denominator or a scaled coefficient above 4096 bits |
| `check` | J not exactly symmetric (it is never symmetrized for you); a non-zero diagonal entry; a spin that is not -1 or 1 |
| `runtime` | The internal audit failed: a defect in the module, not in the input |

A Symblic program cannot write a float (decimal literals are exact fractions); the float refusal
protects Python callers. Running out of the kernel's step budget raises the kernel's own error.

## Method and cost

Every coefficient is multiplied by the common denominator of h and J, so every scaled coefficient is
an integer of at most 4096 bits. The walk's sums are larger but bounded: an energy is at most 136 times
the largest scaled coefficient in absolute value at 16 spins (4104 bits), a doubled local field at most
32 times (4101 bits), a neighbour increment 4 times (4098 bits). Two checks build a product before they
compare it with the limit (a scaled coefficient, and the running common denominator), so a refused input
can create one temporary of at most 8192 bits; nothing larger is built. A Gray-code walk visits all 2^n
states, flipping one spin per step; a flip
changes the energy by one addition and the local fields of the flipped spin's neighbours by at most
n - 1 additions. The minimum, the count and the first 16 ground states are collected on the way.
Before a result is returned, every reported state and the walk's final state are evaluated again
term by term with exact fractions; a disagreement raises kind `runtime`. `ising_energy` uses only
the term-by-term evaluation.

Kernel steps are charged before the work they pay for. `ising_minimize` charges n + n² before it
reads the coefficients and 2^n before the walk: 65,808 steps at 16 spins, of the 200,000 a run has
by default. `ising_energy` charges 2n + n² before it reads its inputs and n + n(n-1)/2 before it
evaluates.

Two bounded observations on 2026-10-03 used CPython 3.12.3 on a 6-core desktop CPU (x86_64) under a load
average between 2.5 and 5, adapter version 1, best of three calls at 16 spins in each: a dense
instance with small integer couplings took 0.11 s, a dense instance with 4096-bit coefficients 0.42
to 0.46 s, and h = 0, J = 0 (65,536 ground states) 0.05 s. These are observations on a shared
machine, not guarantees.

## What a result establishes and what it does not

- The minimum is exact for the supplied numbers, because every state is evaluated exactly. It says
  nothing about numbers that were rounded, estimated or measured before they were written into h and
  J.
- Ground states are in general not unique. With h = 0 their count is even: flipping every spin
  leaves each product s_i s_j unchanged, so the flipped copy of a ground state is a different ground
  state. Frustration adds more: the triangle below has six. This is why the result reports
  `degeneracy` and not one state; a program that needs a single state must say how it chooses one.
- The cost doubles with every added spin, so 16 is a hard limit and this is not a method for large
  problems. Finding a ground state of a general Ising spin glass is NP-hard (F. Barahona, "On the
  computational complexity of Ising spin glass models", J. Phys. A: Math. Gen. 15 (1982) 3241-3253);
  no method is known that finds exact ground states in polynomial time on every instance.
- No annealing, sampling, quantum device or heuristic is involved. A result says nothing about what
  an annealer or a sampler would return for the same h and J.
- An encoding of a real problem as h and J is the author's claim and is not checked here. The minimum
  answers the real question only if the encoding is right, including its signs, scale, pair
  convention and the weights of any penalty terms. "Energy" here is the function E, with no unit and
  no physical meaning of its own.

## Example

This program runs in the kernel alone; no model is called.

```symblic
let J = [[0, -1, -1], [-1, 0, -1], [-1, -1, 0]].
let free = ising_minimize([0, 0, 0], J).
let pulled = ising_minimize([1/2, 0, 0], J).
assert free.degeneracy = 6.
assert pulled.energy = -3/2.
assert all s in pulled.states: ising_energy([1/2, 0, 0], J, s) = pulled.energy.
show free.energy.
show free.degeneracy.
show pulled.
```

Three antiferromagnetic bonds on a triangle cannot all be satisfied: each of the six states that are
not all equal leaves exactly one bond unsatisfied, and they share the minimum -1. A field of 1/2 on
spin 1 keeps the three of them with spin 1 at +1. The run ends with status `done` and these `show`
lines:

```text
-1
6
{degeneracy: 3, energy: -1.5, method: "exhaustive", spins: 3, states: [[1, -1, -1], [1, -1, 1], [1, 1, -1]], truncated: false}
```

`show` writes the exact fraction -3/2 as the exact decimal -1.5. A fraction without a finite decimal
is shown as p/q with an approximation, for example `-44/105 (≈-0.419047619048)`; the value in the
record is always the exact fraction.

## Verification

`tests/adapters/test_symblic_discrete.py` covers a ferromagnetic chain (two ground states), the frustrated
triangle (six), a field that makes the ground state unique, rational coefficients worked by hand,
even degeneracy for h = 0, truncation at 16 states with the true count, agreement with an
independent brute force on 40 seeded random instances with n ≤ 8, a planted 16-spin instance, every
refusal and its kind, the bit limits, the exact step charges and their order, the internal audit,
canonical form and fingerprints, and the example above, read from this file and run.
