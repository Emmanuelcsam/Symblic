# Constructing a finite energy witness

Select **Discrete vorticity construction** in the native Write examples, or run:

```sh
tools/symblic run examples/vorticity-construction.sym --by ollama:qwen3:4b-instruct --max-calls 30 --dir /tmp/vorticity-run
```

This applies the energy construction in the supplied *Energy method for the
vorticity equation* to a declared, dimensionless finite graph. It is a small
model-construction task with an independent exact checker. The continuum
equation is `div(y grad(phi)) = Omega`, with positive `y = mn/B²`, prescribed
potential on a nonempty boundary part and zero normal derivative elsewhere.
Its weak form gives a negative source load; the energy is
`integral(y |grad(phi)|² / 2 + phi Omega)`.

The example chooses five equally spaced vertices, zero endpoint potentials,
four unit edge weights and interior source loads `[0,-2,0]`. The reduced
incidence matrix `D` maps three interior potentials to four edge differences.
The finite stiffness is `A = transpose(D) W D` and `b = -loads`, so the reduced
energy is `xᵀ A x / 2 - bᵀ x`. The sign of `b` is part of the check.

Twenty fresh model tasks construct six independent coefficients of the symmetric
stiffness matrix, five nontrivial LDL factors/pivots, and nine scalar substitution
values that determine the three interior potentials.
Each coefficient ask receives only its one or two selected incidence columns and
the weights. It constructs one scalar weighted dot product. The host extracts
columns and assembles the model's checked coefficients into the symmetric matrix;
it does not supply a stiffness answer to the worker. Before the first factor ask,
an independent assertion checks every assembled entry against the original
incidence matrix and weights.

Every ask uses medium effort and receives named inputs only. Coefficient identities,
the complete matrix identity, factor identities, positive pivots, the stationary
residual and the final quadratic witness are checked. A failed check retries its
generating task once. The thirty-call host budget includes these corrections.
The model constructs the answer: determination, solving and the optional
constructor are disabled. The shared quadratic checker verifies the supplied
factorization without computing it. Expected fixture answers below are not sent
in coefficient requests.

The rational record has an unrestricted signed integer numerator and a denominator
in `1..100`. All rational-factor and substitution instructions explicitly say the numerator may be
negative, zero, or positive, and only the denominator must be positive. The three
pivot tasks still require a positive pivot through their equations and independent
checks; off-diagonal factor entries retain their required signs. No expected
numeric factor answer is inserted into a construction prompt.

The final solve is also decomposed. Each worker constructs one value from only
its named scalar inputs; prompts explicitly request multiplication then subtraction,
division, or copying those selected values. The host checks the defining identity
before the next worker can use it:

| Value | Exact check | Selected inputs |
|---|---|---|
| `y1` | `y1 = b1` | `b1` |
| `y2` | `y2 + l21*y1 = b2` | `b2, l21, y1` |
| `y3` | `y3 + l32*y2 = b3` | `b3, l32, y2` |
| `z1` | `d1*z1 = y1` | `y1, d1` |
| `z2` | `d2*z2 = y2` | `y2, d2` |
| `z3` | `d3*z3 = y3` | `y3, d3` |
| `x3` | `x3 = z3` | `z3` |
| `x2` | `x2 + l32*x3 = z2` | `z2, l32, x3` |
| `x1` | `x1 + l21*x2 = z1` | `z1, l21, x2` |

The first six substitution answers use signed rational records. The three
backward answers use `Int` for this declared integer-solution fixture. The host
extracts `b1,b2,b3`, converts rational records to exact numbers and assembles the
accepted answers into `solution`; it does not calculate substitution answers.
The full `A*solution-b` check and quadratic witness verification remain independent
of those local identities. Changing the problem can require a rational solution
type and corresponding author contract.

For the checked fixture, the full potential is `[0,1,2,1,0]`, its residual is zero,
and its reduced energy is `-2`. The fake provider derives replies from the selected
request data. Tests inject a wrong coefficient, corrupt matrix assembly, reject wrong forward,
diagonal and backward proposals, and catch a corrupted assembled solution. A load
change to `[0,-4,0]` has the integer solution `[2,4,2]` and rejects retained old
backward answers through their identities. Solving/factorization
functions raise if invoked. These tests establish the construction/checking path,
not small-model success. Real model performance must be recorded separately.

The earlier three-row version failed its first row check in admitted Qwen 4B run
`315f88648e42`: both attempted rows were rejected, and no factor or solution was
reached. Scalar run `8219c94f2275` then passed all six coefficients, the independent
matrix check, and the first three factor entries. Its two `lower32` proposals
both returned positive `2/3`; the exact identity required negative `2/3`, so the
run stopped after eleven calls with no solution or final outputs. Both failures
remain retained. The generic repeated-answer diagnostic does not establish an
error in the author-held identity.

The signed-numerator diagnostic `f00de8fbac95` then passed its one synthetic
factor task in one fresh call and replayed from its lock with zero model calls.
The subsequent complete signed-factor run `0731a75ff11c` passed all eleven
coefficient/factor tasks, but its solution vectors `[1,1,1]` and `[1,0,1]` both
failed the full residual check. It stopped after thirteen fresh calls with no
final potential, energy or witness. Those requests contained the correct selected
`A,b,L,D`; all three failed whole-program records remain retained.

The nine scalar substitution tasks address that remaining construction boundary.
The admitted substitution diagnostic `09d7ff1df692` completed nine tasks in ten
fresh calls: its first `forward3` proposal was rejected and its correction passed.
Its synthetic `A,b,L,D` were declared inputs, so that result establishes the
substitution path only. Its recorded lock replay used zero model calls.

The complete twenty-task construction then succeeded in admitted Qwen 3 4B run
`ae4e46820f83` on 5 October 2026. All twenty fresh calls passed their checks on the
first attempt, with no cached prefix or repairs, in 1348.82 seconds. The model
constructed all coefficients, factors and scalar substitution answers from their
selected inputs. The final potential was `[0,1,2,1,0]`, the residual `[0,0,0]`, and
the exact minimum energy `-2`. The witness passed factorization, positive-pivot,
stationarity, symmetry and unique-minimum checks for this finite quadratic.
All twenty retained provider requests were audited for their exact selected
contexts and unchanged model settings. The portable lock replay completed with
zero model calls, twenty recorded replies, and matching fingerprint
`4f8ee53abdc44057`. The three earlier whole-program failures remain retained;
this is one positive fixture result, not a general accuracy estimate. The
[source and run receipt](evidence/2026-10-05-vorticity-construction.json) records
its pins, canonical witness and replay result.

This finite connected graph with fixed endpoints has a positive definite reduced
operator. It does not establish continuum convergence, dimensional plasma
calibration, a GPU implementation or general pure-Neumann solvability. Those
extensions need their own geometry, units, compatibility conditions and validation.
