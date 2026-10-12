# Finite sheaf and schema transport experiments

`cellular-sheaf` and `finite-schema-transport` calculate supplied finite structures.
Their `catalog()` examples and `run(id, data)` results use the research-experiment
registry contract. They make no provider calls and change no native kernel semantics.

## Local-to-global consistency

A graph vertex carries a vector in a declared basis; each incident edge receives
that vector through a supplied linear restriction matrix. For an edge oriented
from `u` to `v`, the implemented degree-zero coboundary is

```text
delta(x)[edge] = R_v,edge * x_v - R_u,edge * x_u
```

The adapter assembles the block matrix and separately calculates both endpoint
images. It compares their residuals exactly. A compatible vertex assignment
extends to a global section by taking the common image at each edge. This is the
graph case of the cellular-sheaf construction in
[Hansen and Ghrist, §2.2](https://arxiv.org/abs/1808.01513).

The result retains the matrix with row/column labels, every endpoint image,
oriented residuals and their squared Euclidean norm. Changing orientation negates
the relevant residual without changing its squared contribution. Bases and the
coordinate norm are fixed input conventions; arbitrary basis changes need not
preserve that norm. All stalk coordinates use one declared value unit and all
restriction entries are dimensionless; discrepancy has the squared value unit.

This checks an assignment, not a search for a section. A failed assignment does
not imply that no section exists. The adapter supports 1–8 vertices, 0–16 edges,
and dimensions 1–3; parallel edges are allowed and self-loops are refused. No
higher cells, section solver or semantic interpretation is supplied.

## Finite maps and predicates

The four supplied sets `A,B,C,D` contain 1–8 labels each. Total maps are typed as
`forward:A→B`, `backward:B→A`, `left:A→C`, `right:B→D`, and `bottom:C→D`.
Both round trips and the square
`right(forward(a)) = bottom(left(a))` are checked on every declared element.
This is a finite commuting-square calculation motivated by typed tables and
composition in [Spivak, §§4–5](https://arxiv.org/abs/1009.1166), not a general
schema-equivalence or data-migration engine.

Boolean predicate tables supply `P` on `A` and `Q` on `B`. Pullback is
`Q(forward(a))`. The existential image is true when some member of a fiber
satisfies `P`; the universal image is true when every member does. Empty fibers
therefore give false and true respectively. For the supplied predicate pair the
adapter checks both adjunction equivalences:

```text
exists_forward(P) subset Q   iff   P subset pullback_forward(Q)
pullback_forward(Q) subset P iff   Q subset forall_forward(P)
```

Lossy round trips, predicate mismatches and noncommuting squares remain explicit
results with witnesses. Malformed or partial maps refuse. There is no arbitrary
expression evaluator, inferred label meaning or numeric unit conversion.

## Bounds and verification

Input is exact JSON with no floats, cycles, unpaired surrogates or excessive
depth/size. Rational numerators have absolute value at most 1,000,000 and
denominators are at most 1,000,000. Every sheaf addition/multiplication preflights
cross-product bit bounds before execution and charges the 20,000-operation
allowance. The 512-bit guard is conservative: cancellation does not excuse an
oversized proposed intermediate. No partial result is returned after refusal.
Input and result envelopes are bounded at 128 and 512 KiB respectively.

Twelve isolated tests cover exact references, mismatched stalk dimensions,
orientation reversal, parallel/isolated vertices, maximum matrix shape,
corrupted matrix assembly, both inverse laws, empty fibers, every Boolean
predicate pair on two-element sets, and malformed arithmetic/map contracts.
The implementation and tests use no models, network, stores or capability executor.

Code: `symblic/experiments/transport.py` (both experiments, in the registry of
`symblic/experiments/registry.py`); tests: `tests/experiments/test_symblic_experiments_transport.py`.
