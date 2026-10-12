# Cube reconstruction protocol: exact shape, placement, and agreement

Proposal, 2026-10-02. This is an offline-checked first pass, not a model benchmark
result. Source baseline: `209cac190798285d6bb7f8fbd7f6b14199666fe4`.
Only this document is changed. Integration and any model experiment belong to the
coordinator; this protocol does not authorize launches.

## Question and falsifiable claims

Can independent applicators translate a fully specified cube description into the
same exact embedded boundary mesh? Separate four outcomes for every scheduled attempt:

1. **Syntax/schema:** `symblic.check(source).ok`, then reply decoding and type
   checking. A check pass does not execute assertions or prove geometry.
2. **Geometric validity:** the independent oracle below proves a nondegenerate
   cube with the specified six quadrilateral faces. A valid rectangular box is
   still a failure of this cube predicate; record its failure reason.
3. **Exact target equivalence:** geometric validity plus equality of coordinates
   and boundary cycles after the explicitly allowed reorderings. This is primary.
4. **Cross-agent agreement:** compare answers independently of correctness. Two
   agents can agree on the wrong cube. Missing answers do not agree.

Test the scoped claim “all registered first attempts reconstruct the exact target”:
any missing, error, invalid, or wrong-target attempt falsifies it for this suite.
Also estimate success rates; do not replace the claim with a weaker metric after
seeing failures. A finite all-pass sample cannot establish universal determinism.

## Target and equivalence contract

Use a right-handed Cartesian frame, coordinates in **metres**, origin at the cube
centre, +x right, +y forward, +z up. Side is exactly 2 m, volume 8 m³. Coordinates
are rationals with no tolerance or inferred unit conversion. The baseline solid
is the convex hull of these vertices, including its interior:

```
1=(-1,-1,-1)  2=(-1, 1,-1)  3=( 1,-1,-1)  4=( 1, 1,-1)
5=(-1,-1, 1)  6=(-1, 1, 1)  7=( 1,-1, 1)  8=( 1, 1, 1)
faces = [(1,3,4,2), (5,6,8,7), (1,2,6,5),
         (3,7,8,4), (1,5,7,3), (2,4,8,6)]
edges = [(1,2),(1,3),(1,5),(2,4),(2,6),(3,4),
         (3,7),(4,8),(5,6),(5,7),(6,8),(7,8)]
```

Faces list cyclic boundary vertices, without repeating the first vertex at the
end. The displayed winding is outward. Require exactly eight distinct vertices,
six distinct quadrilateral faces and 1-based integer indices; reject 0-based or
mixed indices even though the current kernel accepts some 0-based meshes. The
answer contains only `vertices` and `faces`. Units/frame belong to the immutable
trial manifest and prompt, not an optional answer field. No triangles, unused
vertices, normals, or implicit faces in this first pass.

| Comparison | Allowed changes | Disallowed changes |
|---|---|---|
| Raw equality (diagnostic) | None; compare original reply bytes | Even whitespace or vertex reordering |
| Primary embedded-target equality | Vertex permutation with matching index remap; face permutation; cyclic shift or reversal of each face | Changed point set or boundary adjacency; scaling; relocation |
| Rigid equivalence (secondary) | Translation, rotation, reflection, plus the above reorderings | Changed side length or topology |
| Cube kind (secondary) | Any nonzero uniform scale and rigid placement | Unequal lengths, shear, collapse, invalid topology |

A rotation/reflection that maps the unlabelled cube onto itself passes primary
because the embedded solid is unchanged. Otherwise it fails primary. A cube has
no intrinsic chirality, so reflections cannot be distinguished from some proper
rotation once labels are ignored; do not claim a handedness test here. Face
winding reversal is accepted and normalized, not interpreted as a negative solid.
Scale is fixed for primary and rigid equivalence. Rational coordinates restrict
exact rotation trials: use explicit rational orthogonal matrices, not rounded
sines/cosines or arbitrary angles. Identical SVGs are not an oracle: projection,
auto-fit and rounding can conceal size/placement differences.

## Independent oracle and proof obligation

Implement the reference below separately from `symblic.adapters.geometry`. It uses only
standard-library rational arithmetic; it does not call `cube`, `is_cube`,
`shape_facts`, `signature`, `canonical_shape`, `congruent`, or `sameness`.
Parsing/type coercion remains a separate, shared front-end and is not certified
by this oracle. For independent raw JSON decoding, use exact decimal parsing,
reject duplicate keys, booleans/nonfinite values and unexpected fields, and turn
decimal tokens into rational values before invoking the oracle. Do not silently
round to fit a target. The code below accepts already exact `int`/`Fraction` values.
For nonterminating rationals in future model trials, specify a numerator/denominator
schema and adapter in advance; the current `Number` JSON reply is not such a schema.

For each proposed corner p and each triple of other vertices, form edge vectors
u,v,w. Require positive equal squared lengths and zero pairwise dot products.
Require the vertex set to be *exactly* the eight subset sums
`p + i*u + j*v + k*w`, for i,j,k in {0,1}. Require each submitted boundary cycle
to be one of the six fixed-bit square boundaries, each appearing once. A sorted
face *set* alone would miss crossed quadrilaterals; compare cycles up to rotation
and reversal, preserving adjacency and face multiplicity.

**Why sufficient:** the Gram matrix is `d*I`, d>0, hence the vectors are linearly
independent and define an orthogonal equal-edge parallelepiped. Its eight subset
sums are distinct cube corners. The six fixed-bit cycles are precisely its six
square facets, so there is no missing, extra, crossed or duplicated facet. This
also implies 12 edges, degree three, two incident faces per edge, connectedness,
Euler characteristic two and nonzero volume. Conversely every rational embedded
cube has a corner and its three incident edge vectors among the enumerated
triples. Thus enumeration is complete for this representation. This proof does
not rely on vertex count, volume, or an unlabelled pairwise-distance multiset.
For two oracle-validated cubes, equal positive squared side length is sufficient
for rigid equivalence: their normalized orthogonal bases are related by an
orthogonal transformation and their corners by a translation.

The current kernel's `congruent` compares distance multisets and face sizes;
`sameness.valid` starts with structural `shape()` acceptance. Neither is the
primary oracle. In particular, replacing a face with a duplicate preserves those
signature fields. Keep kernel/oracle disagreement as a separate diagnostic,
retain the candidate, and review it rather than changing the oracle mid-study.

## Compact current-language examples

A. Explicit baseline and kernel sanity checks, with no applicator:

```sym
program Cube baseline.
let target = {vertices: [[-1,-1,-1],[-1,1,-1],[1,-1,-1],[1,1,-1],[-1,-1,1],[-1,1,1],[1,-1,1],[1,1,1]], faces: [[1,3,4,2],[5,6,8,7],[1,2,6,5],[3,7,8,4],[1,5,7,3],[2,4,8,6]]}.
assert is_cube(target, 2).
assert canonical_shape(target) = canonical_shape(cube(2)).
return target.
```

B. Acquisition template. Preview pauses before the ask, captures its capsule and
schema, and does not evaluate the postcondition. This public baseline example
is not held out. `ensure ... else fail` is a kernel diagnostic; score the retained
answer with the independent oracle even if that ensure fails.

```sym
program Reconstruct cube.
define Mesh as Record {vertices: List of List of Number length 3 length 8, faces: List of List of Int length 4 length 6}.
ask candidate: Mesh "Return the boundary mesh of a cube of side 2 metres centred at (0,0,0), with faces parallel to coordinate planes in a right-handed x-right, y-forward, z-up frame. Use exactly eight vertices and six cyclic quadrilateral faces with 1-based indices. Only vertices and faces; no repeated closing index." by "fake:cube" with context=none, effort=low, votes=1, retries=0, tools=none, seed=101, temperature=0.
ensure is_cube(candidate, 2) else fail.
return candidate.
```

C. A wrong-shape control: a 4×2×1 m rectangular box has the correct 8 m³ volume.
This program should execute successfully *because it asserts rejection*.

```sym
program Equal volume is insufficient.
let target = cube(2).
let box = {vertices: [[2*p[1],p[2],p[3]/2] for p in target.vertices], faces: target.faces}.
assert not is_cube(box).
return box.
```

## Minimal falsifying regression for the core operator

At source baseline `209cac190798285d6bb7f8fbd7f6b14199666fe4`, keep all eight
vertices unchanged and replace face 6 `(2,4,8,6)` with face 1 `(1,3,4,2)`.
The 28 squared pairwise distances remain exactly twelve 4s, twelve 8s and four
12s; face sizes remain six 4s. Thus the current signature-based `congruent`
accepts a boundary with a missing +y face and duplicated -z face. The edge
`(1,3)` now has three incident face occurrences, while `(6,8)` has only one.
This is a concrete topology counterexample, not a claim that two distinct
valid cube point sets share that distance multiset.

D. Minimal executable witness for the core session; `congruent` is intentionally asserted true
to pin the baseline defect. After a core fix this assertion should be inverted
in the integrated regression, not used as the desired contract:

```sym
program Congruence topology counterexample.
let target = cube(2).
let broken = {vertices: target.vertices, faces: [target.faces[1],target.faces[2],target.faces[3],target.faces[4],target.faces[5],target.faces[1]]}.
assert congruent(broken, target).
assert not is_cube(broken).
return broken.
```

The independent `duplicate_face` fixture below rejects this exact mesh. A second
failure mode, `bow_tie`, keeps the correct four corners of a facet but corrupts
their perimeter order. Validating only corner sets or incidence totals is
insufficient: the six permitted cyclic perimeters must also match. The oracle
first proves the vertex geometry and then separately validates those perimeters
and their multiplicity, from which correct incidence follows.

Coordinator-supplied independent root audit (2026-10-02), source snapshot hash
`7276637c32dc0bf07e2a76ba6c16c351545f5e528646342d0976c0763bb364a2`,
also reports `sameness.valid=true`, `similar=true`, `congruent=true`, but
`closed=false` after replacing the last face by the first on both the cube
(face 6) and a tetrahedron (face 4). This snapshot hash is audit provenance,
not the git baseline SHA of this checkout; that audit was supplied by the
coordinator, not rerun here.

For a minimal tetrahedron companion fixture, use vertices
`[(1,1,1),(1,-1,-1),(-1,1,-1),(-1,-1,1)]`, original faces
`[(1,2,3),(1,4,2),(1,3,4),(2,4,3)]`, and broken faces
`[(1,2,3),(1,4,2),(1,3,4),(1,2,3)]`. The cube companion is D above.
Both leave their point clouds exactly unchanged. An integrated regression should
separately expect structural parsing success, point-cloud equality, and failure
of closed-solid validation/equivalence. If `congruent` intentionally means only
point-cloud congruence, its result must be labelled accordingly and gated by
independent boundary validation before any solid-equivalence claim. Merely fixing
the label does not establish that distance-multiset equality is a complete
point-cloud congruence test for arbitrary shapes. The cube-only oracle here
rejects tetrahedra by design; the tetrahedron is a companion core regression,
not evidence that this oracle validates general polyhedra.

## Executable offline reference and adversarial fixtures

Extract this single Python block into a temporary file, run it from the repository
root with `PYTHONPATH=. /usr/bin/python3`, and delete it afterwards. It reads the
three `.sym` blocks above. No model, service, network, saved run, or real applicator
is used; stores are temporary and forbidden launch paths fail closed. One process,
one worker at most, with a 30-second CPU bound. This is a protocol self-check,
not a replacement benchmark or a proposed change to core code.

```python
import itertools as I
import os
from pathlib import Path
import re
import resource
import tempfile
from fractions import Fraction as Q
from unittest.mock import patch

resource.setrlimit(resource.RLIMIT_CPU, (30, 30))

def cycle(xs):
    xs = tuple(xs)
    rev = xs[::-1]
    return min(seq[k:] + seq[:k] for seq in (xs, rev) for k in range(4))

def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))

def dot(a, b):
    return sum(x*y for x, y in zip(a, b))

def key(mesh):
    return (tuple(sorted(mesh['vertices'])),
            tuple(sorted(cycle(tuple(mesh['vertices'][i-1] for i in f))
                         for f in mesh['faces'])))

def oracle(mesh):
    if not isinstance(mesh, dict) or set(mesh) != {'vertices', 'faces'}:
        return None
    V, F = mesh['vertices'], mesh['faces']
    if not isinstance(V, (list, tuple)) or len(V) != 8:
        return None
    if any(not isinstance(p, (list, tuple)) or len(p) != 3 or
           any(type(x) not in (int, Q) for x in p) for p in V):
        return None
    V = tuple(tuple(Q(x) for x in p) for p in V)
    if len(set(V)) != 8 or not isinstance(F, (list, tuple)) or len(F) != 6:
        return None
    if any(not isinstance(f, (list, tuple)) or len(f) != 4 or
           any(type(i) is not int or not 1 <= i <= 8 for i in f) or
           len(set(f)) != 4 for f in F):
        return None
    actual = sorted(cycle(tuple(V[i-1] for i in f)) for f in F)
    bits = tuple(I.product((0, 1), repeat=3))
    for p in V:
        for ends in I.combinations([q for q in V if q != p], 3):
            axes = tuple(sub(q, p) for q in ends)
            d = dot(axes[0], axes[0])
            if d <= 0 or any(dot(a, a) != d for a in axes):
                continue
            if any(dot(a, b) != 0 for a, b in I.combinations(axes, 2)):
                continue
            points = {b: tuple(p[t] + sum(b[j]*axes[j][t] for j in range(3))
                               for t in range(3)) for b in bits}
            if set(points.values()) != set(V):
                continue
            expected = []
            for fixed in range(3):
                free = [j for j in range(3) if j != fixed]
                for value in (0, 1):
                    face = []
                    for a, b in ((0,0), (1,0), (1,1), (0,1)):
                        bit = [0,0,0]
                        bit[fixed] = value
                        bit[free[0]], bit[free[1]] = a, b
                        face.append(points[tuple(bit)])
                    expected.append(cycle(face))
            if actual == sorted(expected):
                return {'side_squared': d, 'embedded_key': key({'vertices': V, 'faces': F})}
    return None

V = ((-1,-1,-1),(-1,1,-1),(1,-1,-1),(1,1,-1),
     (-1,-1,1),(-1,1,1),(1,-1,1),(1,1,1))
F = ((1,3,4,2),(5,6,8,7),(1,2,6,5),(3,7,8,4),(1,5,7,3),(2,4,8,6))
T = {'vertices': V, 'faces': F}

def mesh(fn=lambda x,y,z: (x,y,z), faces=F):
    return {'vertices': tuple(fn(*p) for p in V), 'faces': faces}

valid = {
    'baseline': T,
    'renumber': {'vertices': V[::-1], 'faces': tuple(tuple(9-i for i in f) for f in F)},
    'reverse_cycles': mesh(faces=tuple(f[::-1] for f in F[::-1])),
    'shift_cycles': mesh(faces=tuple(f[1:]+f[:1] for f in F)),
    'translate': mesh(lambda x,y,z: (x+3,y-2,z+Q(1,2))),
    'rotate': mesh(lambda x,y,z: ((3*x-4*y)/Q(5),(4*x+3*y)/Q(5),z)),
    'reflect': mesh(lambda x,y,z: (-x,y,z)),
    'scale': mesh(lambda x,y,z: (2*x,2*y,2*z)),
}
invalid = {
    'duplicate_vertex': {'vertices': V[:-1]+(V[0],), 'faces': F},
    'flat_distinct': mesh(lambda x,y,z: (x+3*z,y,0)),
    'equal_volume_box': mesh(lambda x,y,z: (2*x,y,Q(z,2))),
    'equal_volume_shear': mesh(lambda x,y,z: (x+y,y,z)),
    'rhombohedron': mesh(lambda x,y,z: (x+Q(3,5)*y,Q(4,5)*y,z)),
    'near_cube': mesh(lambda x,y,z: (x,y,z+Q(1,10**9)*(x==y==z==1))),
    'duplicate_face': mesh(faces=F[:-1]+(F[0],)),
    'missing_face': mesh(faces=F[:-1]),
    'bow_tie': mesh(faces=((1,4,3,2),)+F[1:]),
    'bad_index': mesh(faces=((1,3,4,9),)+F[1:]),
    'zero_based': mesh(faces=tuple(tuple(i-1 for i in f) for f in F)),
    'repeat_index': mesh(faces=((1,3,4,1),)+F[1:]),
}
base = oracle(T)
assert base and base['side_squared'] == 4
for name, m in valid.items():
    result = oracle(m)
    assert result, name
    assert (result['embedded_key'] == base['embedded_key']) == (
        name in {'baseline','renumber','reverse_cycles','shift_cycles','reflect'}), name
    assert (result['side_squared'] == 4) == (name != 'scale'), name
for name, m in invalid.items():
    assert oracle(m) is None, name

with tempfile.TemporaryDirectory() as tmp:
    with patch.dict(os.environ, {'AUTOMATION_DATA_DIR': tmp}):
        import symblic as S
        import integration.host.symblic_engine as E
        import symblic.kernel.run as SR
        def forbidden(*args, **kwargs):
            raise AssertionError('Unexpected external effect')
        with patch('socket.socket', side_effect=forbidden), \
             patch('subprocess.Popen', side_effect=forbidden), \
             patch.object(E._PreviewApps, 'call', side_effect=forbidden):
            path = Path('docs/reference/reinforcements/cube-protocol.md')
            snippets = re.findall(r'```sym\n(.*?)```', path.read_text(), re.S)
            assert len(snippets) == 4
            for i, src in enumerate(snippets):
                checked = S.check(src)
                assert checked['ok'], checked
                preview = E.preview({'source': src})
                assert preview['status'] == ('paused' if i == 1 else 'done'), preview
                if i == 1:
                    assert preview['next']['name'] == 'candidate'
            class Fake:
                def call(self, req):
                    answer = {k: [list(row) for row in rows] for k, rows in T.items()}
                    return {'ok': True, 'json': {'answer': answer}, 'ms': 0}
            run = SR.Run(snippets[1], {}, Fake(), {'parallel': 1})
            report = run.execute()
            assert report['status'] == 'done', report
            assert oracle(run.kernel.env.lookup('candidate').value) == base
print('PASS: 4 check/preview snippets, fake reply, 8 positive and 12 negative fixtures')
```

The flat fixture retains eight distinct coplanar points. The shear has determinant
one, hence the same volume as the target. The rhombohedron has three equal-length
basis vectors `(1,0,0)`, `(3/5,4/5,0)`, `(0,0,1)` but a nonzero dot product.
The near-cube perturbation must fail despite being visually invisible. Reordering,
reflection symmetry and a genuine rational rotation provide positive controls;
translation/rotation/scale distinguish primary equality from cube validity.

## Proposed experiment, held-out descriptions, and independence

Freeze oracle, parser/kernel revision, prompt templates, output adapter, policies,
timeouts and a manifest of attempt IDs before any model calls. First validate
all fixtures above; no benchmark interpretation is valid if an oracle control fails.
Keep this public baseline and adversarial fixtures in development, not in the
reported held-out score. Example description families for a coordinator to instantiate
with **new, unrevealed wording and parameters after development freezes**:

| Family | Public illustration, not a held-out test item |
|---|---|
| Plane bounds | “The solid between x=±1, y=±1, z=±1 metres; enumerate boundary cycles.” |
| Centre/side | “A 2 m cube centred at the origin; each face parallel to a coordinate plane.” |
| Corner/basis | “Corner (-1,-1,-1); incident displacements (2,0,0), (0,2,0), (0,0,2) m.” |
| Unit conversion | “Side 200 cm, centre origin, axis-aligned; return coordinates in metres.” |
| Rational frame | “Apply R=[[3/5,-4/5,0],[4/5,3/5,0],[0,0,1]] to the specified corners.” |
| Displaced centre | “Same specified basis/side; centre (3,-2,1/2) metres.” |

Each actual held-out item must fully specify origin, frame, scale, rational
transform and connectivity format. Compute its target from the frozen definition
with independent rational arithmetic, not from a model or the kernel's cube
constructor. Two reviewers should resolve ambiguity before seeing outputs. If
such review is unavailable, label the set provisional. Illustrations printed here
are already exposed and cannot honestly be called held out.

Bounded pilot proposal: six new items (one per family), two frozen models from
different model families, five fresh trials per model/item, two conditions =
120 scheduled attempts. Conditions: the typed Symblic acquisition above and the
same description requesting the same JSON mesh directly, with equivalent output
budget/schema support. Both use the same independent oracle. Pin exact model IDs,
weight digests where available, provider/build, backend, prompt/capsule hash,
requested and effective seed/temperature/effort, grammar settings and tool policy.
Do not substitute a missing model after looking at scores. Execution is future
coordinator work through existing admitted applicators only.

Use new sessions without repository access, tools, examples, retrieved results,
conversation carryover, or other agents' answers. Generate nonoverlapping seed
streams per model/condition; e.g. `100000*model + 10000*condition + 100*item + repeat`
with indices starting at one. These are independently assigned streams, not proof
of statistically independent model errors. Fix temperature=0 where supported;
record unsupported/ignored seed or temperature controls explicitly. Different seeds
at temperature zero are bookkeeping, not guaranteed output diversity. No high/ultra,
voting or repair in the primary pass: `effort=low, votes=1, retries=0`. Randomize
execution order with a separate recorded scheduling seed. Keep predeclared resource
limits (one answer, 4096 output-token cap where supported, 180 s deadline after
admission); record actual provider limits if they differ.

Fresh inference uses separate empty run folders and no reused `calls.jsonl`.
Admission failures or never-started attempts at the predeclared study cutoff stay
in the manifest as missing; they are not silently retried. Infrastructure reruns
are separate labelled rows. A replay condition can intentionally reuse recorded
answers, but is a test of replay machinery, not model reproduction.

## Analysis and reporting plan

Retain per-attempt raw output privately, decoded exact mesh, all four outcomes,
kernel/oracle disagreement, error category, model/settings, item/seed IDs, latency,
tokens, cache/reuse flags and any coercion. No private run histories or measurements
belong in this shared protocol. Classify timeout, refusal, admission failure,
no-output, decoding/schema error, geometric failure and wrong target separately.
An oracle exception is an evaluation error requiring review, never a success.

Primary rate per model/condition is exact-target successes divided by **all 30
scheduled attempts**, including missing and errors. Publish stage pass counts
against that same denominator, plus conditional diagnostic rates with their
explicit denominators. Report per-item results; do not select best seeds or drop
hard descriptions. Compare conditions with paired item/replicate outcomes and
report the success-rate difference. Six items are a small pilot: report uncertainty
by resampling whole items with all models/conditions/repeats together (a fixed-seed
item-cluster bootstrap), flag the low cluster count, and avoid treating 30 repeated
answers as 30 independent task discoveries. Do not pool conditions or model families
for a stronger apparent sample size.

For each matched item/repeat across models, record raw-byte equality, primary
embedded-key agreement, and rigid-equivalence agreement separately. Primary
agreement requires two valid cube outputs and equal embedded keys; rigid agreement
requires two valid cubes and equal squared sides. Divide unconditional rates by
all 30 scheduled pairs; a pair with any missing/error/invalid output contributes
zero. Also show valid-pair conditional rates and coverage. Record “both exact”,
“agree but wrong”, “disagree”, and “unscorable” counts. Identical malformed replies
may have raw agreement, but never geometric agreement. Do not use the kernel's
whole-run fingerprint: it includes unrelated bindings and ordered outputs.
Compare full exact keys; hashes are convenient indexing, not geometric proofs.

Separate follow-up questions: same-seed fresh calls test observed repeatability;
saved-call replay tests reproduction from records; changed prompts, worked examples,
retries or demonstrations test adaptation/learning effects. None establishes that
model weights learned anything unless weights actually changed. Freeze any tuning
on development items, then use a new holdout for adapted variants. Shared training
material, this public cube, model lineage and provider caching remain possible
leakage/correlation sources even with fresh seeds. A perfect finite pilot supports
only the stated models, descriptions, versions and conditions.

## Basis and validation status

[PAL](https://arxiv.org/abs/2211.10435v2) supplies prior art for translating language
into a program and delegating computation to an interpreter; it does not establish
cube equivalence or universal cross-model identity. The oracle proof above is
specific to this proposed representation. [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)
specifies canonical JSON serialization for repeatable hashing, not geometric
correctness. Its ECMAScript number serialization is not Symblic's exact-rational
`#q` encoding; do not describe Symblic's canonicalization as JCS compliance.
See also [SPEC](../SPEC.md) and [PRIOR-ART](../PRIOR-ART.md) for repository context.

Offline validation at the baseline above: all four snippets passed `symblic.check`
and `integration.host.symblic_engine.preview`; the fake reply completed; eight positive and twelve
negative oracle fixtures passed. `bin/devcheck` passed with zero blocking findings
and zero affected test modules. Shellcheck and gitleaks were absent and their
additional checks were skipped; nothing was installed. The embedded reference
block is the focused executable check for this document-only change.

Compatibility observation: an explicit `temperature=0.7` passed preview but failed
the fake run at this baseline with `Fraction is not JSON serializable`; the
checked template uses integer zero. Any future nonintegral-temperature condition
needs a separate coordinator-reviewed compatibility fix and a new frozen baseline.
No live model accuracy, learning, timing, fleet identity or cross-agent reproduction
measurement is claimed by this document.

## Coordinator verification of the newer geometry kernel

After integration, geometry version 2, source SHA-256
`ab7b7d40ed7d85a49e4512e3f05efdbea7dcbab267fe7e513126ab4d0a4388cc`,
rejects both all-face duplication and last-face replacement for cubes and
tetrahedra at `valid_solid`, `similar`, and `congruent`, while preserving
`schema_valid`. The flat zero-volume fixture is not a valid solid; the
homometric collinear point sets do not pass `congruent_points`. A positive
rational rotation plus translation still passes congruence. Negative requested
side lengths are rejected, and `vertices=None` produces a schema error.
These are focused counterexample checks, not a proof for arbitrary polyhedra.

The independent oracle block's eight positive and twelve negative controls
were rerun separately and passed. Snippet D intentionally witnesses the pinned
older baseline defect; its positive `congruent` assertion should fail on the
new kernel. Retain the snippet as baseline evidence, and invert the assertion
when using it as a current regression.

The explicit `temperature=0.7` fake-run failure was independently reproduced
in runner SHA-256 `ab70f28b440f8caa8c3cb7311cc1c54e96c3bff7acaa73cbda2be370a3d558fa`
and sent to the core operator. This verification is bounded to that snapshot.

A later immutable runner snapshot, SHA-256
`036cba552e431b7155521689e7ca82b1f74392464e51a3a3b7bb1373429769dc`,
accepts the same `temperature=0.7` fake run: status `done`, one call, no error.
The preceding failure remains historical snapshot evidence; this specific
compatibility defect is closed in the later tested version.
