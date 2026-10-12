"""Trusted independent checker and binary-STL encoder; no mesh construction.

All vertices and faces must come from the accepted model-written native program.
Exact rational arithmetic checks the synthetic dimensions before float32 export.
"""
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite JSON number required')
    return Fraction(str(value))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cavity_overlap(points, width, depth):
    """Exact positive-area overlap with the open cavity's XY rectangle."""
    polygon = [point[:2] for point in points]
    for axis, bound, sign in ((0, -width/2, 1), (0, width/2, -1), (1, -depth/2, 1), (1, depth/2, -1)):
        clipped = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            inside_a, inside_b = sign*(a[axis]-bound) >= 0, sign*(b[axis]-bound) >= 0
            if inside_a:
                clipped.append(a)
            if inside_a != inside_b:
                ratio = (bound-a[axis])/(b[axis]-a[axis])
                clipped.append(tuple(x+ratio*(y-x) for x, y in zip(a, b)))
        polygon = clipped
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1])))/2


def validate(mesh, dimensions):
    require(type(mesh) is dict and set(mesh) == {'vertices', 'triangles'}, 'closed mesh shape')
    width, depth, height, wall, base = map(number, dimensions)
    iw, idepth = width-2*wall, depth-2*wall
    require(min(width, depth, height, wall, base, iw, idepth, height-base) > 0, 'valid cup dimensions')
    require(type(mesh['vertices']) is list and len(mesh['vertices']) == 16, 'sixteen vertices required')
    require(all(type(p) is list and len(p) == 3 for p in mesh['vertices']), 'xyz triples required')
    vertices = [tuple(map(number, p)) for p in mesh['vertices']]
    require(len(set(vertices)) == 16, 'shared vertices must be unique')
    rings = ((width, depth, 0), (width, depth, height), (iw, idepth, height), (iw, idepth, base))
    for ri, (w, d, z) in enumerate(rings):
        expected = ((-w/2, -d/2, z), (w/2, -d/2, z), (w/2, d/2, z), (-w/2, d/2, z))
        require(tuple(vertices[ri*4:ri*4+4]) == expected, 'ring ordering or dimensions differ')
    faces = mesh['triangles']
    require(type(faces) is list and len(faces) == 28, 'twenty-eight triangles required')
    edges, directions, categories, area2 = Counter(), Counter(), Counter(), Counter()
    edge_faces, face_keys = defaultdict(list), set()
    volume6 = Fraction(0)
    for fi, face in enumerate(faces):
        require(type(face) is list and len(face) == 3 and all(type(i) is int and 0 <= i < 16 for i in face), 'triangle indices')
        require(len(set(face)) == 3, 'repeated triangle vertex')
        key = tuple(sorted(face))
        require(key not in face_keys, 'duplicate face')
        face_keys.add(key)
        a, b, c = [vertices[i] for i in face]
        normal = cross(tuple(y-x for x, y in zip(a, b)), tuple(y-x for x, y in zip(a, c)))
        require(dot(normal, normal) > 0, 'zero-area face')
        points = (a, b, c)
        planes = []
        for axis, outer, inner in ((0, width/2, iw/2), (1, depth/2, idepth/2)):
            for sign in (-1, 1):
                if all(p[axis] == sign*outer for p in points):
                    planes.append((f'outer{axis}:{sign}', axis, sign))
                if all(p[axis] == sign*inner and p[2] >= base for p in points):
                    planes.append((f'inner{axis}:{sign}', axis, -sign))
        if all(p[2] == 0 for p in points):
            planes.append(('bottom', 2, -1))
        if all(p[2] == base and abs(p[0]) <= iw/2 and abs(p[1]) <= idepth/2 for p in points):
            planes.append(('floor', 2, 1))
        if all(p[2] == height for p in points):
            require(cavity_overlap(list(points), iw, idepth) == 0, 'a rim face covers the open cavity')
            planes.append(('rim', 2, 1))
        require(len(planes) == 1, 'face must lie on exactly one prescribed material boundary')
        category, axis, sign = planes[0]
        require(sign*normal[axis] > 0 and all(v == 0 for j, v in enumerate(normal) if j != axis), 'outward face orientation')
        categories[category] += 1
        area2[category] += abs(normal[axis])
        volume6 += dot(a, cross(b, c))
        for start, end in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((start, end)))
            edges[edge] += 1
            directions[edge] += 1 if start < end else -1
            edge_faces[edge].append(fi)
    require(set(edges.values()) == {2}, 'each edge requires exactly two incident faces')
    require(set(directions.values()) == {0}, 'shared edges must have opposite orientation')
    require(len(edges) == 42 and 16-len(edges)+28 == 2, 'expected Euler characteristic')
    adjacent = defaultdict(set)
    for x, y in edge_faces.values():
        adjacent[x].add(y)
        adjacent[y].add(x)
    seen, pending = {0}, [0]
    while pending:
        for other in adjacent[pending.pop()] - seen:
            seen.add(other)
            pending.append(other)
    require(len(seen) == 28, 'one edge-connected material boundary required')
    expected_area = {'bottom': width*depth, 'floor': iw*idepth, 'rim': width*depth-iw*idepth}
    for sign in (-1, 1):
        expected_area.update({f'outer0:{sign}': depth*height, f'outer1:{sign}': width*height,
                              f'inner0:{sign}': idepth*(height-base), f'inner1:{sign}': iw*(height-base)})
    require(set(categories) == set(expected_area), 'all material boundary surfaces required')
    for key, area in expected_area.items():
        require(categories[key] == (8 if key == 'rim' else 2), 'surface triangle count: '+key)
        require(area2[key] == 2*area, 'exact surface area: '+key)
    expected_volume = width*depth*height-iw*idepth*(height-base)
    require(volume6 > 0 and volume6 == 6*expected_volume, 'exact positive material volume')
    return {'passed': True, 'vertices': 16, 'triangles': 28, 'edges': 42,
            'signed_volume_mm3': float(volume6/6), 'expected_volume_mm3': float(expected_volume),
            'outer_mm': list(map(float, (width, depth, height))),
            'cavity_mm': list(map(float, (iw, idepth, height-base))),
            'open_interior': True, 'surface_areas_mm2': {k: float(v) for k, v in expected_area.items()},
            'arithmetic': 'exact rational coordinates; no geometric tolerance used'}


def binary_stl(mesh, dimensions):
    """Encode an already validated mesh without repairing or reconstructing it."""
    validate(mesh, dimensions)
    header = b'Symblic Qwen3:4b synthetic rectangular cup; coordinates in mm'
    result = bytearray(header.ljust(80, b'\0'))
    result.extend(struct.pack('<I', len(mesh['triangles'])))
    for face in mesh['triangles']:
        a, b, c = [mesh['vertices'][i] for i in face]
        normal = cross(tuple(y-x for x, y in zip(a, b)), tuple(y-x for x, y in zip(a, c)))
        length = math.sqrt(dot(normal, normal))
        result.extend(struct.pack('<12fH', *(v/length for v in normal), *a, *b, *c, 0))
    return bytes(result)


def verify_stl(data, mesh, dimensions):
    require(len(data) == 1484 and struct.unpack_from('<I', data, 80)[0] == 28, 'binary STL byte/count bounds')
    lookup = {tuple(p): i for i, p in enumerate(mesh['vertices'])}
    faces = []
    for offset in range(84, len(data), 50):
        row = struct.unpack_from('<12fH', data, offset)
        require(row[-1] == 0 and all(math.isfinite(v) for v in row[:-1]), 'finite STL record')
        points = [tuple(row[i:i+3]) for i in (3, 6, 9)]
        require(all(point in lookup for point in points), 'STL vertices differ from accepted mesh')
        face = [lookup[p] for p in points]
        require(face == mesh['triangles'][len(faces)], 'STL face differs from accepted mesh')
        geometric = cross(tuple(y-x for x, y in zip(points[0], points[1])), tuple(y-x for x, y in zip(points[0], points[2])))
        require(dot(geometric, row[:3]) > 0 and abs(dot(row[:3], row[:3])-1) < 1e-6, 'STL normal orientation/length')
        faces.append(face)
    return {**validate({'vertices': mesh['vertices'], 'triangles': faces}, dimensions),
            'stl_bytes': len(data), 'stl_sha256': hashlib.sha256(data).hexdigest()}


def export(mesh_file, dimensions, output):
    mesh = json.loads(Path(mesh_file).read_text())
    data = binary_stl(mesh, dimensions)
    receipt = verify_stl(data, mesh, dimensions)
    with Path(output).open('xb') as stream:
        stream.write(data)
    return receipt
