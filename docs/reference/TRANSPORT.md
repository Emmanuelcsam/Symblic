# Exact finite one-dimensional transport

`symblic/adapters/transport.py` compares two explicitly supplied **numeric distributions**.
Its `wasserstein1` operation computes the exact rational Wasserstein-1 distance
after normalizing each distribution to total mass one. It can compare, for
example, two finite distributions of durations measured in the same unit.
It keeps information about spread that a single median discards.
For example, equally weighted samples `[0, 1, 2]` and `[1, 1, 1]` both have
median one, while their Wasserstein-1 distance is exactly `2/3`.

The construction is established optimal transport, not a new metric.
For one-dimensional probability distributions with cumulative functions F and G,
W1 is the integral of `abs(F(x) - G(x))`. For finite support this becomes a sum
over adjacent sorted coordinates: interval width times absolute cumulative mass
difference. See Peyré and Cuturi, *Computational Optimal Transport*, §2.6,
equation (2.35), and the discussion in §6.1.
[Primary book PDF](https://optimaltransport.github.io/pdf/ComputationalOT.pdf)

## Input and result

```python
from fractions import Fraction
from symblic.adapters.transport import wasserstein1

left = [{'at': 0, 'mass': 1}, {'at': 2, 'mass': 1}]
right = [{'at': 1, 'mass': 3}]
assert wasserstein1(left, right) == 1

assert wasserstein1(
    [{'at': Fraction(1, 3), 'mass': 7}],
    [{'at': Fraction(2, 5), 'mass': 2}],
) == Fraction(1, 15)
```

Each distribution must be a list or tuple of records with exactly `at` and `mass`.
Values are native integers or canonical `Fraction` values. Booleans, floats,
nonfinite values, numeric strings, numeric subclasses and extra fields refuse.
Masses must be nonnegative with positive total. Duplicate coordinates merge;
zero-mass atoms are ignored after their coordinates have been validated. Neither
input is mutated. The result is a Symblic native integer or exact rational.

Each input is normalized **independently**. Multiplying all masses on one side by
any positive constant leaves the result unchanged. Therefore this operation does
not compare absolute population sizes, total quantities or unbalanced transport.

Coordinates must already have a shared scale and unit. The result has that
coordinate unit: seconds for durations encoded in seconds, for example.
The function cannot recognize a mixture of seconds and milliseconds from bare
numbers. It does not turn text into coordinates or decide whether an encoding
captures the intended phenomenon.

## Bounds and refusals

```python
wasserstein1(left, right, max_atoms=128, max_bits=4096, max_work=200_000)
```

These defaults are also ceilings. Every limit must be an integer at least one;
booleans refuse. `max_atoms` applies separately to each input before merging or
removing zero masses. Numerators, denominators and unreduced integer intermediates
are bounded by `max_bits`. Sums and products are checked before construction,
including rational arithmetic used by sorting. A representable final distance may
therefore refuse when an intermediate exceeds the selected bound.

`max_work` counts scalar validation and arithmetic, including comparisons. This
deterministic count is not a wall-clock or bit-complexity estimate. An optional
`budget=Symblic.Budget(...)` is charged by the same operations. Input/shape and
local budget failures raise `TransportError`, a `SymblicError`; exhaustion of the
shared kernel budget propagates its normal error. No approximate or partial
distance is returned. Sorting and storage are bounded by at most 256 input atoms
across both distributions. Different representations can require different work
and can encounter different intermediate bounds even if they denote the same
normalized distribution.

The module reuses `symblic.adapters.variational._Work` for the existing checked rational
arithmetic. It does not invoke the quadratic solver. `ARITHMETIC_VERSION` records
that dependency; a core integration must pin both modules' semantic versions.

## Kernel attachment

Importing `symblic.adapters.transport` does not modify the global builtin table.
`register(kernel)` attaches `wasserstein1` to that kernel's `functions` mapping,
idempotently, and refuses a conflicting existing function. Its callback signature
is `(kernel, node, left, right, **limits)` and charges `kernel.budget`.

```python
import symblic.kernel.run as SR
import symblic.adapters.transport as T

run = SR.Run('''
let left = [{at: 0, mass: 1}, {at: 2, mass: 1}].
let right = [{at: 1, mass: 3}].
let distance = wasserstein1(left, right).
assert distance = 1.
show distance.
''')
T.register(run.kernel)
report = run.execute()
assert report['status'] == 'done' and report['calls'] == 0
```

## What the checks establish

Focused tests include known rational answers, exhaustive assignment minima for
small equal-mass particle sets, weighted examples expanded into equal particles,
symmetry, translation, absolute scaling, triangle inequalities, reordered/split
atoms, normalization invariance and hostile type/resource inputs. The assignment
reference enumerates couplings instead of implementing the CDF sweep again.
These are finite tests, not a machine-checked proof of every implementation path.

A distance of zero means equality of the encoded normalized distributions.
It does not establish factual correctness, semantic equivalence, common meaning,
model independence, a consensus decision or that the observations were accurate.
This API supplies a numeric comparison primitive; it makes no model-accuracy,
novelty, embedding-quality or general communication claim.
