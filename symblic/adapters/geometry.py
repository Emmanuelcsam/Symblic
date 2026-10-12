"""Exact polyhedra: is a shape a valid solid, is it a cube, are two shapes the same, and a deterministic drawing.

A shape is a record {vertices: [[x, y, z], ...], faces: [[i, j, k, ...], ...]} with 1-based vertex numbers
(0-based lists are detected and accepted). Every test is exact: coordinates are rationals, so squared
lengths, dot products and determinants are exact, and "all edges equal" or "every corner is a right angle"
is decided, not estimated.

Two kinds of validity, never conflated:
  schema_valid  the record parses: 4..200 distinct points, faces of 3+ distinct vertex numbers in range
  valid_solid   `solid()`: every face a flat, strictly convex polygon (no repeated or collinear corners); no two
                faces on the same vertices; every vertex used; every edge on exactly two faces; the faces can be
                oriented consistently and form one connected surface with no pinch vertex; non-zero volume;
                every face's plane is a supporting plane of the vertices (convex); and the enclosed volume
                equals the convex hull's, so the surface wraps the hull exactly once and cannot intersect
                itself. A closed non-convex surface is reported `None` (undecided): self-intersection is not
                tested for it.

Sameness levels, loosest to strictest (`sameness`):
  similar        an exact similarity (rotation, reflection, translation, uniform scale, renumbering) maps the
                 answer's vertices onto the target's and its faces onto the target's faces
  congruent      the same with scale 1
  same_placement the kernel's canonical form is equal (same point set, same faces, any numbering/order)
  identical      the raw record equals the target
`match` finds the map by search over base points (Gram coordinates, exact), so it decides congruence; it is
not the distance-multiset signature, which is only a necessary condition (homometric point sets share it).
A search that exceeds its budget returns None, reported as undecided rather than guessed.

Depends on: symblic.kernel.language, symblic.adapters.render (drawings). Registers its builtins in the kernel's
builtin table when symblic.kernel.language is imported (register(BUILTINS)).
"""

from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from fractions import Fraction

from symblic.kernel import language as S

VERSION = 2          # 2026-10-02: solid validity and exact congruence (v1: schema-only "valid", signature congruence)
MATCH_BUDGET = 60_000


class GeometryError(S.SymblicError):
    pass


def _num(v, where):
    if isinstance(v, bool) or not S.is_num(v):
        raise GeometryError(f'{where} must be a number', kind='type')
    return Fraction(v)


def _seq(v):
    return isinstance(v, (list, tuple))


def shape(value) -> dict:
    """A schema-valid shape: exact vertex coordinates and 0-based faces (internal). Says nothing about whether
    the faces bound a solid; see solid()."""
    if not isinstance(value, dict) or 'vertices' not in value:
        raise GeometryError('a shape is a record {vertices: [[x, y, z], ...], faces: [[1, 2, 3], ...]}', kind='type')
    if not _seq(value['vertices']):
        raise GeometryError('vertices must be a list of [x, y, z] points', kind='type')
    verts = []
    for i, p in enumerate(value['vertices'], 1):
        if isinstance(p, dict):
            p = (p.get('x'), p.get('y'), p.get('z'))
        if not _seq(p) or len(p) != 3:
            raise GeometryError(f'vertex {i} must be [x, y, z]', kind='type')
        verts.append(tuple(_num(c, f'vertex {i}') for c in p))
    if len(verts) < 4 or len(verts) > 200:
        raise GeometryError('a shape needs 4 to 200 vertices', kind='type')
    if len(set(verts)) != len(verts):
        raise GeometryError('two vertices are at the same point', kind='type')
    raw_faces = value.get('faces')
    if raw_faces is None:
        raw_faces = ()
    if not _seq(raw_faces) or not all(_seq(f) for f in raw_faces):
        raise GeometryError('faces must be a list of lists of vertex numbers', kind='type')
    flat = [x for f in raw_faces for x in f]
    for x in flat:
        if isinstance(x, bool) or not S.is_num(x) or S.norm_num(x) != int(x):
            raise GeometryError('face entries must be whole vertex numbers', kind='type')
    base = 0 if flat and min(int(x) for x in flat) == 0 else 1          # 0-based answers are accepted
    faces = []
    for j, f in enumerate(raw_faces, 1):
        idx = [int(x) - base for x in f]
        if len(idx) < 3 or len(set(idx)) != len(idx) or any(not 0 <= k < len(verts) for k in idx):
            raise GeometryError(f'face {j} must list 3 or more different vertex numbers from 1 to {len(verts)}',
                                kind='type')
        faces.append(idx)
    return {'v': verts, 'f': faces}


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _d2(a, b):
    d = _sub(a, b)
    return _dot(d, d)


def _sign(x):
    return (x > 0) - (x < 0)


def edges(sh) -> list:
    out = set()
    for f in sh['f']:
        for a, b in zip(f, f[1:] + f[:1]):
            out.add((min(a, b), max(a, b)))
    return sorted(out)


def _normal(v, face):
    """Newell's normal of a polygon (exact; zero for a degenerate one). Its direction follows the vertex order."""
    n = [Fraction(0)] * 3
    for i in range(len(face)):
        a, b = v[face[i]], v[face[(i + 1) % len(face)]]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return tuple(n)


def _planar(v, face) -> bool:
    n = _normal(v, face)
    return n != (0, 0, 0) and all(_dot(n, _sub(v[k], v[face[0]])) == 0 for k in face)


def _strictly_convex(v, face) -> bool:
    """A flat polygon whose every other corner lies strictly inside each edge's line: convex, simple, no
    repeated or collinear corners (a pentagram or a bow-tie fails)."""
    if not _planar(v, face):
        return False
    n = _normal(v, face)
    k = len(face)
    for i in range(k):
        a, b = v[face[i]], v[face[(i + 1) % k]]
        e = _sub(b, a)
        for j in range(k):
            if j in (i, (i + 1) % k):
                continue
            if _dot(n, _cross(e, _sub(v[face[j]], a))) <= 0:
                return False
    return True


def _right_angles(v, face) -> bool:
    for i in range(len(face)):
        a, b, c = v[face[i - 1]], v[face[i]], v[face[(i + 1) % len(face)]]
        if _dot(_sub(a, b), _sub(c, b)) != 0:
            return False
    return True


def solid(value) -> dict:
    """Is this a solid? Every check is exact; `problems` says what failed, in words."""
    sh = shape(value)
    v, f = sh['v'], sh['f']
    problems = []
    if len(f) < 4:
        problems.append(f'{len(f)} face(s): a solid needs at least 4')
    seen = {}
    for j, face in enumerate(f, 1):
        key = frozenset(face)
        if key in seen:
            problems.append(f'faces {seen[key]} and {j} use the same vertices')
        seen.setdefault(key, j)
        if not _planar(v, face):
            problems.append(f'face {j} is not flat or is degenerate')
        elif not _strictly_convex(v, face):
            problems.append(f'face {j} is not a convex polygon with distinct, non-collinear corners')
    unused = sorted(set(range(len(v))) - {k for face in f for k in face})
    if unused:
        problems.append('vertices not on any face: ' + ', '.join(str(k + 1) for k in unused))
    use = {}
    for j, face in enumerate(f):
        for a, b in zip(face, face[1:] + face[:1]):
            use.setdefault((min(a, b), max(a, b)), []).append(j)
    bad_edges = [(e, len(js)) for e, js in sorted(use.items()) if len(js) != 2]
    for (a, b), n in bad_edges[:4]:
        problems.append(f'edge {a + 1}-{b + 1} is on {n} face(s), not 2')
    closed = bool(f) and not bad_edges
    oriented = connected = pinch_free = False
    volume = Fraction(0)
    flip = {}
    if closed:
        def direction(j, a, b):          # +1 when face j runs a -> b, -1 when it runs b -> a
            face = f[j]
            i = face.index(a)
            return 1 if face[(i + 1) % len(face)] == b else -1
        flip = {0: 1}
        stack, oriented = [0], True
        while stack and oriented:
            j = stack.pop()
            face = f[j]
            for a, b in zip(face, face[1:] + face[:1]):
                for g in use[(min(a, b), max(a, b))]:
                    if g == j:
                        continue
                    want = -flip[j] * direction(j, a, b) * direction(g, a, b)
                    if g not in flip:
                        flip[g] = want
                        stack.append(g)
                    elif flip[g] != want:
                        oriented = False
        connected = len(flip) == len(f)
        if not oriented:
            problems.append('the faces cannot be oriented consistently (one-sided surface)')
        if not connected:
            problems.append('the faces form more than one separate piece')
        pinch_free = True
        for k in range(len(v)):
            around = [j for j, face in enumerate(f) if k in face]
            if not around:
                continue
            reach, todo = {around[0]}, [around[0]]
            while todo:
                j = todo.pop()
                face = f[j]
                i = face.index(k)
                for nb in (face[i - 1], face[(i + 1) % len(face)]):
                    for g in use[(min(k, nb), max(k, nb))]:
                        if g not in reach:
                            reach.add(g)
                            todo.append(g)
            if len(reach) != len(around):
                pinch_free = False
                problems.append(f'vertex {k + 1} is a pinch point (its faces do not form one fan)')
        if oriented and connected:
            for j, face in enumerate(f):
                pts = [v[k] for k in (face if flip[j] == 1 else face[::-1])]
                for i in range(1, len(pts) - 1):
                    volume += _dot(pts[0], _cross(pts[i], pts[i + 1]))
            volume /= 6
            if volume == 0:
                problems.append('the enclosed volume is zero (a flat or folded surface)')
    convex = False
    hull = None
    if not problems:
        out_sign = 1 if volume > 0 else -1
        convex = True
        planes = {}
        for j, face in enumerate(f):
            n = _normal(v, face if flip[j] * out_sign == 1 else face[::-1])          # outward
            p0 = v[face[0]]
            if any(_dot(n, _sub(v[k], p0)) > 0 for k in range(len(v))):
                convex = False                    # a vertex beyond this face's plane: not a supporting plane
                break
            scale = abs(next(c for c in n if c != 0))
            n = tuple(c / scale for c in n)
            planes[(n, _dot(n, p0))] = n
        if convex:
            hull = _hull_volume(v, planes)
            if hull != abs(volume):               # the faces wrap the hull more than once
                convex = False
                problems.append('the faces cover the convex hull more than once')
    valid = False if problems else (True if convex else None)
    return {'schema_valid': True, 'valid_solid': valid, 'problems': problems,
            'closed': closed and oriented and connected and pinch_free and len(seen) == len(f), 'convex': convex, 'volume': abs(volume),
            'euler': len(v) - len(use) + len(f),
            'note': 'closed but not convex: self-intersection is not tested, so validity is undecided'
            if valid is None else ''}


def _hull2(pts):
    """Exact 2D convex hull (monotone chain) of (x, y, index) triples; returns indices counter-clockwise."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return [p[2] for p in pts]

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [p[2] for p in lower[:-1] + upper[:-1]]


def _hull_volume(v, planes) -> Fraction:
    """The volume of the convex hull, from its facet planes (each facet: the 2D hull of the vertices on it),
    as pyramids from the centroid. Exact."""
    c = tuple(sum(p[k] for p in v) / len(v) for k in range(3))
    total = Fraction(0)
    for (n, off) in planes:
        on = [k for k in range(len(v)) if _dot(n, v[k]) == off]
        drop = max(range(3), key=lambda a: abs(n[a]))
        keep = [a for a in range(3) if a != drop]
        ring = _hull2([(v[k][keep[0]], v[k][keep[1]], k) for k in on])
        for i in range(1, len(ring) - 1):
            a, b, d = (_sub(v[ring[0]], c), _sub(v[ring[i]], c), _sub(v[ring[i + 1]], c))
            total += abs(_dot(a, _cross(b, d)))
    return total / 6


def facts(value) -> dict:
    """Exact properties of a shape (a record a program can test with ensure/assert)."""
    sh = shape(value)
    v, f = sh['v'], sh['f']
    es = edges(sh)
    sol = solid(value)
    lengths = sorted({_d2(v[a], v[b]) for a, b in es})
    planar = bool(f) and all(_planar(v, face) for face in f)
    right = all(_right_angles(v, face) for face in f) if f else False
    degree = {}
    for a, b in es:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    return {'vertices': len(v), 'edges': len(es), 'faces': len(f), 'euler': len(v) - len(es) + len(f),
            'face_sizes': tuple(sorted(len(x) for x in f)), 'edge_lengths_squared': tuple(S.norm_num(x) for x in lengths),
            'equal_edges': len(lengths) == 1, 'closed': sol['closed'], 'planar_faces': planar, 'right_angles': right,
            'convex': sol['convex'], 'volume': S.norm_num(sol['volume']), 'valid_solid': sol['valid_solid'] is True,
            'validity_decided': sol['valid_solid'] is not None, 'problems': tuple(sol['problems']), 'degrees': tuple(sorted(set(degree.values())))}


def is_cube(value, side=None) -> bool:
    """A valid solid with 8 vertices, 12 equal edges and 6 square faces (edge = side when given; side > 0)."""
    if side is not None and _num(side, 'side') <= 0:
        raise GeometryError('side must be positive', kind='type')
    try:
        fx = facts(value)
    except GeometryError:
        return False
    ok = (fx['valid_solid'] is True and fx['vertices'] == 8 and fx['edges'] == 12 and fx['faces'] == 6
          and fx['face_sizes'] == (4,) * 6 and fx['equal_edges'] and fx['right_angles'] and fx['degrees'] == (3,))
    if ok and side is not None:
        ok = fx['edge_lengths_squared'][0] == _num(side, 'side') ** 2
    return ok


def signature(value) -> dict:
    """A NECESSARY condition for congruence, not a sufficient one: the vertex count, the sorted multiset of
    squared pairwise distances and the sorted face sizes. Homometric point sets share it without being
    congruent; `match` decides congruence."""
    sh = shape(value)
    v = sh['v']
    d2 = sorted(_d2(v[i], v[j]) for i in range(len(v)) for j in range(i + 1, len(v)))
    return {'vertices': len(v), 'distances_squared': tuple(S.norm_num(x) for x in d2),
            'face_sizes': tuple(sorted(len(x) for x in sh['f']))}


def _basis(v):
    """Indices of an affine basis of the point set (1 to 4 points), chosen in order; exact rank tests."""
    base = [0]
    vecs = []
    for k in range(1, len(v)):
        cand = vecs + [_sub(v[k], v[0])]
        g = [[_dot(a, b) for b in cand] for a in cand]
        if _det(g) != 0:
            base.append(k)
            vecs = cand
            if len(vecs) == 3:
                break
    return base


def _det(m):
    if len(m) == 1:
        return m[0][0]
    if len(m) == 2:
        return m[0][0] * m[1][1] - m[0][1] * m[1][0]
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def _keys(v, base):
    """Each point's coordinates relative to the base: |p - b0|^2 and (p - b0).(bi - b0). Within the base's
    span these determine the point, and the extra squared norm rules out points outside it."""
    b0 = v[base[0]]
    dirs = [_sub(v[b], b0) for b in base[1:]]
    return [(_d2(p, b0),) + tuple(_dot(_sub(p, b0), d) for d in dirs) for p in v]


def match(a, b, scale=False, points_only=False):
    """An exact map from shape a onto shape b: rotation/reflection/translation (and uniform scale when `scale`),
    any renumbering; faces must map onto faces unless `points_only`. True / False, or None when the search
    budget ran out (undecided)."""
    sa, sb = shape(a), shape(b)
    va, vb = sa['v'], sb['v']
    if len(va) != len(vb):
        return False
    if not points_only and sorted(len(x) for x in sa['f']) != sorted(len(x) for x in sb['f']):
        return False
    tot_a = sum(_d2(va[i], va[j]) for i in range(len(va)) for j in range(i + 1, len(va)))
    tot_b = sum(_d2(vb[i], vb[j]) for i in range(len(vb)) for j in range(i + 1, len(vb)))
    if tot_a == 0 or tot_b == 0:
        return False
    k = tot_b / tot_a if scale else Fraction(1)
    if not scale and tot_a != tot_b:
        return False
    base = _basis(va)
    want = sorted(tuple(x * k for x in key) for key in _keys(va, base))
    faces_b = sorted(sorted(x) for x in sb['f'])
    ka = _keys(va, base)
    budget = [MATCH_BUDGET]

    def extend(chosen):
        if budget[0] <= 0:
            return None
        if len(chosen) == len(base):
            budget[0] -= 1
            kb = _keys(vb, chosen)
            if sorted(kb) != want:
                return False
            if points_only:
                return True
            where = {key: i for i, key in enumerate(kb)}
            mapping = [where[tuple(x * k for x in key)] for key in ka]
            return sorted(sorted(mapping[i] for i in face) for face in sa['f']) == faces_b
        m = len(chosen)
        undecided = False
        for c in range(len(vb)):
            if c in chosen:
                continue
            if all(_d2(vb[c], vb[chosen[i]]) == k * _d2(va[base[m]], va[base[i]]) for i in range(m)):
                r = extend(chosen + [c])
                if r:
                    return True
                if r is None:
                    undecided = True
                    if budget[0] <= 0:
                        return None
        return None if undecided else False

    return extend([])


def congruent(a, b):
    """Both are valid solids and an exact rigid motion (reflections allowed) maps one onto the other, faces
    included. None when the search was undecided."""
    try:
        if solid(a)['valid_solid'] is not True or solid(b)['valid_solid'] is not True:
            return False
        return match(a, b)
    except GeometryError:
        return False


def similar(a, b):
    """Both are valid solids and an exact similarity (uniform scale allowed) maps one onto the other."""
    try:
        if solid(a)['valid_solid'] is not True or solid(b)['valid_solid'] is not True:
            return False
        return match(a, b, scale=True)
    except GeometryError:
        return False


def congruent_points(a, b):
    """Point sets only (faces ignored): an exact rigid motion maps a's vertices onto b's."""
    try:
        return match(a, b, points_only=True)
    except GeometryError:
        return False


def canonical(value) -> dict:
    """The kernel's normal form of a shape: vertices sorted by (x, y, z); every face oriented counter-clockwise
    seen from outside and started at its smallest vertex number; faces sorted. Two answers with the same point
    set and faces have the same canonical form however their authors numbered or listed them."""
    sh = shape(value)
    v, f = sh['v'], sh['f']
    order = sorted(range(len(v)), key=lambda i: v[i])
    new = {old: k for k, old in enumerate(order)}
    verts = [v[i] for i in order]
    cx = tuple(sum(p[k] for p in verts) / len(verts) for k in range(3))
    faces = []
    for face in f:
        idx = [new[i] for i in face]
        n = _normal(verts, idx)
        fc = tuple(sum(verts[i][k] for i in idx) / len(idx) for k in range(3))
        if _dot(n, _sub(fc, cx)) < 0:          # normal points inward: reverse to counter-clockwise outside
            idx = idx[::-1]
        m = idx.index(min(idx))
        faces.append(idx[m:] + idx[:m])
    faces.sort()
    return {'vertices': tuple(tuple(S.norm_num(c) for c in p) for p in verts),
            'faces': tuple(tuple(i + 1 for i in face) for face in faces)}


LEVELS = ('schema_valid', 'valid_solid', 'similar', 'congruent', 'same_placement', 'identical')


def sameness(answer, target) -> dict:
    """How close an answer comes to a target solid, loosest to strictest. Every level above schema_valid
    requires a valid solid; `undecided` lists levels whose search ran out of budget."""
    out = {'version': VERSION, **{k: False for k in LEVELS}, 'undecided': ()}
    try:
        shape(answer)
    except GeometryError as e:
        out['error'] = e.message
        return out
    out['schema_valid'] = True
    sol = solid(answer)
    out['valid_solid'] = sol['valid_solid'] is True
    out['problems'] = tuple(sol['problems'][:4])
    if not out['valid_solid']:
        if sol['valid_solid'] is None:
            out['undecided'] = ('valid_solid',)
        return out
    und = []
    sim = similar(answer, target)
    if sim is None:
        und.append('similar')
    out['similar'] = sim is True
    con = match(answer, target) if out['similar'] else False
    if con is None:
        und.append('congruent')
    out['congruent'] = con is True
    out['same_placement'] = out['congruent'] and S.canon_json(canonical(answer)) == S.canon_json(canonical(target))
    out['identical'] = out['same_placement'] and S.canon_json(_value(answer)) == S.canon_json(_value(target))
    out['undecided'] = tuple(und)
    return out


def cube(side=2, center=(0, 0, 0)) -> dict:
    """The reference cube: vertices ordered by z, then x, then y; faces outward counter-clockwise."""
    if _num(side, 'side') <= 0:
        raise GeometryError('side must be positive', kind='type')
    h = Fraction(_num(side, 'side')) / 2
    c = tuple(_num(x, 'center') for x in center)
    verts = [(c[0] + sx * h, c[1] + sy * h, c[2] + sz * h) for sz in (-1, 1) for sx in (-1, 1) for sy in (-1, 1)]
    faces = [[1, 3, 4, 2], [5, 6, 8, 7], [1, 2, 6, 5], [3, 7, 8, 4], [1, 5, 7, 3], [2, 4, 8, 6]]
    return {'vertices': tuple(tuple(S.norm_num(x) for x in p) for p in verts),
            'faces': tuple(tuple(f) for f in faces)}


def tetrahedron() -> dict:
    """The regular tetrahedron on alternate corners of the cube with corners (±1, ±1, ±1): edge 2√2."""
    return canonical({'vertices': ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)),
                      'faces': ((1, 2, 3), (1, 4, 2), (1, 3, 4), (2, 4, 3))})


def octahedron() -> dict:
    """The regular octahedron with vertices (±1, 0, 0), (0, ±1, 0), (0, 0, ±1)."""
    v = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    faces = [(a, b, c) for a in (1, 2) for b in (3, 4) for c in (5, 6)]
    return canonical({'vertices': v, 'faces': tuple(faces)})


def square_pyramid() -> dict:
    """Base: the square with corners (±1, ±1, 0); apex (0, 0, 2)."""
    v = ((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0), (0, 0, 2))
    return canonical({'vertices': v, 'faces': ((1, 2, 3, 4), (1, 2, 5), (2, 3, 5), (3, 4, 5), (4, 1, 5))})


def draw(value, size=None, color=None) -> str:
    """A deterministic isometric wireframe (Decimal maths only; coordinates rounded half-even to 0.01)."""
    from symblic.adapters import render as R
    sh = shape(value)
    sz = R._int(size, 'size', 120, 1200, 400)
    col = R.color(color, 'black')
    from decimal import Decimal, localcontext
    with localcontext() as ctx:
        ctx.prec = 40
        D = Decimal
        c30, s30 = S.dec_cos(S.PI() / 6), S.dec_sin(S.PI() / 6)
        pts = []
        for x, y, z in sh['v']:
            X, Y, Z = S.num_to_dec(x), S.num_to_dec(y), S.num_to_dec(z)
            pts.append(((X - Y) * c30, (X + Y) * s30 - Z))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or D(1)
        scale = (D(sz) * D('0.8')) / span
        ox = D(sz) / 2 - (max(xs) + min(xs)) / 2 * scale
        oy = D(sz) / 2 - (max(ys) + min(ys)) / 2 * scale
        lines = []
        for a, b in edges(sh):
            (x1, y1), (x2, y2) = pts[a], pts[b]
            lines.append(f'<line x1="{R.fmt(ox + x1 * scale)}" y1="{R.fmt(oy + y1 * scale)}" '
                         f'x2="{R.fmt(ox + x2 * scale)}" y2="{R.fmt(oy + y2 * scale)}"/>')
        dots = [f'<circle cx="{R.fmt(ox + x * scale)}" cy="{R.fmt(oy + y * scale)}" r="3"/>' for x, y in pts]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sz} {sz}" width="{sz}" height="{sz}">\n'
            f'<g stroke="{col}" stroke-width="2" stroke-linecap="round">\n' + '\n'.join(lines) + '\n</g>\n'
            f'<g fill="{col}">\n' + '\n'.join(dots) + '\n</g>\n</svg>')


def _value(x):
    """A Python geometry result as a Symblic value (tuples stay tuples, numbers exact)."""
    if isinstance(x, dict):
        return {k: _value(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return tuple(_value(v) for v in x)
    if isinstance(x, Fraction):
        return S.norm_num(x)
    return x


def register(builtins: dict) -> None:
    builtins.update({
        'shape_facts': lambda k, n, s: _value(facts(s)),
        'is_cube': lambda k, n, s, side=None: is_cube(s, side),
        'shape_signature': lambda k, n, s: _value(signature(s)),
        'congruent': lambda k, n, a, b: congruent(a, b),
        'congruent_points': lambda k, n, a, b: congruent_points(a, b),
        'solid_check': lambda k, n, s: _value({**solid(s), 'valid_solid': solid(s)['valid_solid'] is True,
                                               'validity_decided': solid(s)['valid_solid'] is not None}),
        'cube': lambda k, n, side=2, center=(0, 0, 0): _value(cube(side, center)),
        'similar': lambda k, n, a, b: similar(a, b),
        'canonical_shape': lambda k, n, s: _value(canonical(s)),
        'sameness': lambda k, n, a, b: _value(sameness(a, b)),
        'draw_shape': lambda k, n, s, size=None, color=None: S.Svg(draw(s, size, color)),
    })


register(S.BUILTINS)
