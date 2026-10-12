# Exact finite operators and question order

`symblic/adapters/operators.py` gives the kernel four exact computations on small real rational matrices: whether a
matrix is an orthogonal projector, the commutator of two matrices, whether they commute, and the probability
of a sequence of yes/no answers under the projector model of question order. That model is Busemeyer and
Wang's quantum-probability account of order effects: a question is a projector, a "yes" projects the state
onto the projector's range, a "no" onto its orthogonal complement, and the probability of a sequence of
answers is the squared length that is left, as a fraction of the state's. All arithmetic is exact and rational. There is no floating point,
no fitting, no sampling and no model call.

## What is computed

| Builtin | Result |
| --- | --- |
| `is_projector(P)` | Bool: `P` is symmetric and `P*P = P` |
| `commutator(A, B)` | the matrix `A*B - B*A`, a list of rows |
| `commutes(A, B)` | Bool: `A*B - B*A` is the zero matrix |
| `ordered_probability(state, answers)` | the exact probability of the answers, in the order given |

For `ordered_probability`, `answers` is a list of records `{projector: P, yes: Bool}` in the order the
questions are asked. Answer i applies `M_i = P_i` when `yes` is true and `M_i = I - P_i` when it is false, and

```
ordered_probability(state, answers) = |M_k ... M_1 state|^2 / |state|^2
```

where `|v|^2` is the sum of the squares of the entries. The state need not be normalised: multiplying it by a
non-zero rational does not change the result. Every projector must pass `is_projector`; each `M_i` is then an
orthogonal projector too, so the result lies between 0 and 1.

Result shapes: `is_projector` and `commutes` return a Bool. `commutator` returns n rows of n numbers, rows and
entries in index order. `ordered_probability` returns one number. Numbers are normalised as the kernel does
it: integers when whole (a probability of 0 or 1 is an integer), exact fractions otherwise. `S.canon` and
`S.fingerprint` accept every result.

## Domain and refusals

A matrix is a list of rows (lists or tuples), square, of dimension 1..8. A state is a list of 1..8 entries,
of the same dimension as every projector it meets. Entries are integers or exact fractions. Floats (even
integral or infinite ones), Bools, Decimal values, text, numeric subclasses and malformed `Fraction` internals
are refused: a binary approximation is never reinterpreted as the rational the author meant. A Symblic
literal such as `0.1` is already exact (1/10).

`is_projector` answers `false` for a square matrix that is not exactly symmetric or does not satisfy
`P*P = P`. The oblique projector `[[1, 1], [0, 0]]` satisfies `P*P = P` but is not symmetric, so it is not an
orthogonal projector. `commutator` and `commutes` take any two square rational matrices of one dimension.
`ordered_probability` refuses an answer whose matrix is not an orthogonal projector; the message names the
answer and the property that fails. The four builtins take positional arguments only.

| Kind | When |
| --- | --- |
| `type` | a wrong shape or size, a dimension mismatch, an entry that is not an exact number, an answer that is not a record with exactly the fields `projector` and `yes`, a `yes` that is not a Bool, a wrong number of arguments, any named option |
| `check` | the zero state; an answer whose matrix is not symmetric or does not satisfy `P*P = P` |
| `budget` | a numerator or denominator above the bit limit, in an input or in an intermediate; the work limit |
| `runtime` | the module's own work count exceeded its charge: a defect, not reachable by an input |

Errors are `OperatorError`, a `SymblicError`; a program sees the kind and the line of the call.

## Limits and budget

| Constant | Value | Meaning |
| --- | ---: | --- |
| `MAX_DIMENSION` | 8 | rows and columns of a matrix; entries of the state |
| `MAX_ANSWERS` | 8 | answers in one `ordered_probability` call (at least one) |
| `MAX_BITS` | 4096 | numerator and denominator of every input and of every unreduced intermediate |
| `MAX_WORK` | 10000 | work units one call may be charged |

Shapes and sizes are checked first. The whole charge of a call is then taken from the kernel's step budget at
once, before any entry is read. For dimension n and k answers:

| Builtin | Charge, in work units (kernel steps) |
| --- | --- |
| `is_projector` | n²(n + 2) |
| `commutator`, `commutes` | 2n² + 4n³ |
| `ordered_probability` | 5n + 1 + k(n³ + 4n² + n) |

A unit is one entry validation or one exact rational operation; comparisons are not counted. The largest call
the size limits admit, `ordered_probability` with n = 8 and 8 answers, is charged 6249 units, about 3% of a
run's default budget of 200000 steps. `MAX_WORK` is therefore not reached by any call today; it bounds the
charge if the size limits are ever raised. The charge is the worst case for the shapes: `commutes` stops at
the first non-zero entry, `is_projector` at the first entry that fails, and a "yes" needs n fewer operations
than a "no", but the charge stays the same. The module counts its units as it works and refuses rather than
do more than it was charged. Exhausting the kernel budget raises the kernel's own error, not `OperatorError`.

Integer products and sums are checked against `MAX_BITS` before they are built, after cross-cancelling. A
small result can therefore be refused when an intermediate would be too large: `is_projector([[2^3000]])`
refuses (kind `budget`) rather than answering `false`. Bit sizes grow with every answer applied. One
observation on 2026-10-03: in the largest generated test call (n = 8, eight answers, projectors spanned by
integer vectors with entries in -3..3), no integer the module built had more than 351 bits. The work units
are operation counts, not wall-clock guarantees.

## What the model predicts

Let A and B be the projectors of questions A and B and s the state. Joint probabilities are labelled by
question, not by position: with B asked first, "A yes, B no" is the sequence B no, then A yes. The following
hold for every state and every pair of orthogonal projectors; the tests check each of them exactly.

- **The four joint probabilities of one order sum to 1.** B and I - B split every vector into orthogonal
  parts, so the squared lengths add up; the same holds for A.
- **Commuting projectors have no order effect.** If AB = BA, then each of A and I - A commutes with each of B
  and I - B, so the product for answers taken in one order equals the product for the other order, and every
  joint probability is the same in both orders.
- **Non-commuting projectors can have one.** P(A yes) with A asked first, minus P(A yes) with B asked first,
  is sᵀ(AB + BA - 2BAB)s / sᵀs. That symmetric matrix is zero only when AB = BA, so for non-commuting
  projectors some state shows a difference, and one of the form e_i or e_i + e_j does (e_i is the i-th unit
  vector). Example:
  A = [[1, 0], [0, 0]], B = [[1/2, 1/2], [1/2, 1/2]], s = (2, 1): P(A yes) is 4/5 when A is asked first and
  1/2 when B is asked first.
- **The QQ equality.** With A asked first, the probability that the two answers agree is
  sᵀ(ABA + (I - A)(I - B)(I - A))s / sᵀs, and that matrix expands to I - A - B + AB + BA, which is symmetric
  in A and B. So P(A yes, B no) + P(A no, B yes), the probability that the answers differ, is the same in
  both orders, also when the order changes P(A yes). In the example above it is 1/2 in both orders. Wang and
  Busemeyer (2013) derived this as an a priori prediction of the model that has no free parameter; Wang,
  Solloway, Shiffrin and Busemeyer (2014) examined it on survey data.

These are consequences of the model's assumptions, which are also what the function computes: one projector
stands for a question in both orders, there is one pure state, and each answer replaces the state by its
projection before the next question is asked.

## What it does not establish

This computes what the projector model PREDICTS for matrices the author supplies. It does not fit projectors
or a state to data, and it does not test the model. It does not show that a person or a language model
follows the model, and a language model's hidden state is not a quantum state: nothing here reads a model's
internals, and a vector of activations is not a state that answers project.

Unequal conditional probabilities, P(B|A) ≠ P(A|B), are ordinary probability and are not an order effect.
In classical probability the two share a numerator, the joint probability, over different denominators,
P(A) and P(B). Commuting projectors behave classically: with A = diag(1, 1, 0), B = diag(1, 0, 0) and
s = (1, 1, 1), every joint probability is the same in both orders, and still P(B|A) = 1/2 and P(A|B) = 1.
An order effect compares the answer to one question across the two orders.

Data that satisfy the QQ equality do not show that the model is right; a clear violation on enough samples
speaks against the model with the assumptions above. Encoding real questions as matrices is the author's
claim, not checked here. The algebra has real symmetric matrices only: complex Hermitian projectors, mixed
states (density matrices) and measurements that are not projective are not represented.

## Example (kernel only)

```symblic
program Question order in the projector model.
note Kernel only. A and B project onto the lines through (1, 0) and (1, 1); the state is (2, 1).
let A = [[1, 0], [0, 0]].
let B = [[1/2, 1/2], [1/2, 1/2]].
let state = [2, 1].
assert is_projector(A) and is_projector(B).
assert not commutes(A, B).
show commutator(A, B) as "A*B - B*A".
let a_yes = {projector: A, yes: true}.
let a_no = {projector: A, yes: false}.
let b_yes = {projector: B, yes: true}.
let b_no = {projector: B, yes: false}.
let a_first = ordered_probability(state, [a_yes]).
let a_second = ordered_probability(state, [b_yes, a_yes]) + ordered_probability(state, [b_no, a_yes]).
let differ_ab = ordered_probability(state, [a_yes, b_no]) + ordered_probability(state, [a_no, b_yes]).
let differ_ba = ordered_probability(state, [b_no, a_yes]) + ordered_probability(state, [b_yes, a_no]).
assert a_first = 4/5 and a_second = 1/2.
assert differ_ab = differ_ba.
show a_first as "P(A yes), A asked first".
show a_second as "P(A yes), B asked first".
show differ_ab as "P(the answers differ), either order".
```

Saved to a file, `tools/symblic run FILE --by kernel --max-calls 0` runs it without asking a model. Its `show`
statements print, in order (value hashes left out):

```text
show A*B - B*A (line 8): [[0, 0.5], [-0.5, 0]]
show P(A yes), A asked first (line 19): 0.8
show P(A yes), B asked first (line 20): 0.5
show P(the answers differ), either order (line 21): 0.5
```

The run ends `done` with 0 asks and 0 calls. From Python, `symblic.kernel.run.Run(source, None, None,
{'by': 'kernel'}).execute()` returns the same values in `report['outputs']`.

## Integration

`symblic/kernel/language.py` maps the four builtin names to this module in its fixed `ADAPTERS` table. The first call imports
the module; `kernel_id()` records its `VERSION` (1) under `operators`, so a change of version changes the
kernel identity; a deployment without the module refuses the builtins with kind `unavailable`. Importing the
module registers, reads and writes nothing. From Python, `is_projector`, `commutator`, `commutes` and
`ordered_probability` take the same arguments plus an optional `budget` (a `Budget`) and `node`.

## Focused verification

`tests/adapters/test_symblic_operators.py` checks, exactly: projectors and non-projectors by hand (including the oblique
projector), commutators by hand, one question as `sᵀPs / sᵀs`, all eight joint probabilities of the example
pair by hand; on five non-commuting pairs in dimensions 2 to 4, the order effect on A against
sᵀ(AB + BA - 2BAB)s / sᵀs and the QQ equality against I - A - B + AB + BA; on six commuting pairs, equal joint
probabilities in both orders; the sum of the four joint probabilities; the unequal conditionals without an
order effect; 40 seeded random instances against an independent computation that multiplies the matrices
before applying them; the largest admitted call; every refusal kind; the exact charge, its timing and its
exhaustion; canonical form; the program above, run through the kernel with no model call.

These are finite exact checks of the implementation on chosen and generated inputs, not a machine-checked
proof.

## References

- Wang, Z., and Busemeyer, J. R. (2013). A quantum question order model supported by empirical tests of an a
  priori and precise prediction. *Topics in Cognitive Science* 5(4), 689–710.
- Wang, Z., Solloway, T., Shiffrin, R. M., and Busemeyer, J. R. (2014). Context effects produced by question
  orders reveal quantum nature of human judgments. *Proceedings of the National Academy of Sciences* 111(26),
  9431–9436.
