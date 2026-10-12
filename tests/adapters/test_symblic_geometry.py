"""symblic_geometry: schema validity vs solid validity, exact congruence, and the 2026-10-02 audit fixtures
(duplicate faces, flat surfaces, homometric point sets, negative sides, malformed vertices)."""

import os
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.adapters import geometry as G  # noqa: E402


def moved(shape, rot=None, shift=(0, 0, 0), scale=1, renumber=None):
    """The shape under an exact rotation/reflection matrix, a shift, a scale and a vertex renumbering."""
    rot = rot or ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    pts = [tuple(scale * sum(Fraction(rot[i][j]) * p[j] for j in range(3)) + shift[i] for i in range(3))
           for p in shape['vertices']]
    n = len(pts)
    order = renumber or list(range(n))           # new position k holds old vertex order[k]
    where = {old: k for k, old in enumerate(order)}
    verts = tuple(tuple(S.norm_num(c) for c in pts[old]) for old in order)
    faces = tuple(tuple(where[i - 1] + 1 for i in f) for f in shape['faces'])
    return {'vertices': verts, 'faces': faces}


class Validity(unittest.TestCase):
    def test_reference_solids_are_valid_convex_solids(self):
        for sh in (G.cube(2), G.tetrahedron(), G.octahedron(), G.square_pyramid()):
            sol = G.solid(sh)
            self.assertIs(sol['valid_solid'], True, sol['problems'])
            self.assertTrue(sol['convex'])
            self.assertEqual(sol['euler'], 2)
        self.assertEqual(G.solid(G.cube(2))['volume'], 8)
        self.assertEqual(G.solid(G.square_pyramid())['volume'], Fraction(8, 3))

    def test_duplicate_faces_are_not_a_solid(self):
        c = G.cube(2)
        bad = {**c, 'faces': (c['faces'][0],) * 6}
        same = G.sameness(bad, c)
        self.assertTrue(same['schema_valid'])
        for level in ('valid_solid', 'similar', 'congruent', 'same_placement', 'identical'):
            self.assertFalse(same[level], level)
        self.assertFalse(G.is_cube(bad))
        t = G.tetrahedron()
        bad_t = {**t, 'faces': (t['faces'][0],) * 4}
        self.assertFalse(G.sameness(bad_t, t)['congruent'])
        two = {**t, 'faces': ((1, 2, 3), (1, 2, 3))}
        sol = G.solid(two)
        self.assertIs(sol['valid_solid'], False)
        self.assertFalse(sol['closed'])
        self.assertFalse(sol['convex'])
        self.assertTrue(any('same vertices' in p for p in sol['problems']))
        self.assertTrue(any('not on any face' in p for p in sol['problems']))

    def test_a_flat_closed_surface_has_no_volume(self):
        flat = {'vertices': ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
                'faces': ((1, 2, 3), (1, 3, 4), (1, 4, 2), (2, 4, 3))}
        fx = G.facts(flat)
        self.assertFalse(fx['convex'])
        self.assertFalse(fx['valid_solid'])
        self.assertEqual(fx['volume'], 0)
        same = G.sameness(flat, G.cube(2))
        self.assertTrue(same['schema_valid'])
        self.assertFalse(same['valid_solid'])

    def test_open_nonmanifold_and_pinched_surfaces(self):
        c = G.cube(2)
        self.assertFalse(G.solid({**c, 'faces': c['faces'][:5]})['valid_solid'])        # a box with no lid
        # two tetrahedra sharing one vertex: closed edges, but vertex 1 is a pinch point
        two = {'vertices': ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), (0, -1, 0), (0, 0, -1)),
               'faces': ((1, 3, 2), (1, 2, 4), (1, 4, 3), (2, 3, 4), (1, 5, 6), (1, 7, 5), (1, 6, 7), (5, 7, 6))}
        sol = G.solid(two)
        self.assertIs(sol['valid_solid'], False)
        self.assertTrue(any('pinch' in p for p in sol['problems']))

    def test_degenerate_and_nonconvex_faces(self):
        # a cube face listed with a repeated-direction corner (collinear) is refused
        pts = list(G.cube(2)['vertices']) + [(0, -1, -1)]
        sq = {'vertices': tuple(pts), 'faces': ((1, 9, 3, 4, 2),) + G.cube(2)['faces'][1:]}
        self.assertIs(G.solid(sq)['valid_solid'], False)

    def test_inconsistent_face_orientation_is_still_a_solid(self):
        c = G.cube(2)
        mixed = {**c, 'faces': (c['faces'][0][::-1],) + c['faces'][1:]}
        self.assertIs(G.solid(mixed)['valid_solid'], True)
        self.assertEqual(G.canonical(mixed), G.canonical(c))

    def test_a_concave_solid_is_undecided_not_valid(self):
        # an L-shaped prism: closed and oriented, but not convex
        base = ((0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2))
        verts = tuple((x, y, 0) for x, y in base) + tuple((x, y, 1) for x, y in base)
        faces = [(1, 2, 3, 4), (1, 4, 5, 6), (7, 8, 9, 10), (7, 10, 11, 12)]     # each L split into two convex pieces
        for i in range(6):
            j = (i + 1) % 6
            faces.append((i + 1, j + 1, j + 7, i + 7))
        sol = G.solid({'vertices': verts, 'faces': tuple(faces)})
        self.assertEqual(sol['problems'], [])
        self.assertIsNone(sol['valid_solid'])
        self.assertIn('self-intersection', sol['note'])

    def test_malformed_vertices_are_schema_errors(self):
        for bad in ({'vertices': None, 'faces': ()}, {'vertices': (None, (0, 0, 0), (1, 0, 0), (0, 1, 0))},
                    {'vertices': ((0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))}, {'vertices': 5},
                    {'vertices': ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), 'faces': (5,)}):
            with self.assertRaises(G.GeometryError):
                G.shape(bad)
            self.assertFalse(G.sameness(bad, G.cube(2))['schema_valid'])

    def test_sides_must_be_positive(self):
        self.assertTrue(G.is_cube(G.cube(2), 2))
        self.assertFalse(G.is_cube(G.cube(2), 3))
        for side in (-2, 0):
            with self.assertRaises(G.GeometryError):
                G.is_cube(G.cube(2), side)
            with self.assertRaises(G.GeometryError):
                G.cube(side)


class Congruence(unittest.TestCase):
    QUARTER = ((0, -1, 0), (1, 0, 0), (0, 0, 1))         # 90 degrees about z
    MIRROR = ((-1, 0, 0), (0, 1, 0), (0, 0, 1))

    def test_rigid_motions_reflections_and_renumbering_are_congruent(self):
        for sh in (G.cube(2), G.tetrahedron(), G.octahedron(), G.square_pyramid()):
            n = len(sh['vertices'])
            other = moved(sh, self.QUARTER, (3, -1, Fraction(1, 2)), renumber=list(range(n))[::-1])
            self.assertIs(G.congruent(sh, other), True)
            self.assertIs(G.congruent(sh, moved(sh, self.MIRROR)), True)
            same = G.sameness(other, sh)
            self.assertTrue(same['congruent'])
            self.assertFalse(same['same_placement'])

    def test_scaled_is_similar_not_congruent(self):
        c, big = G.cube(2), G.cube(Fraction(7, 3), (1, 1, 1))
        self.assertIs(G.similar(c, big), True)
        self.assertIs(G.congruent(c, big), False)
        same = G.sameness(big, c)
        self.assertTrue(same['similar'])
        self.assertFalse(same['congruent'])

    def test_homometric_point_sets_are_not_congruent(self):
        xs, ys = (0, 1, 4, 10, 12, 17), (0, 1, 8, 11, 13, 17)
        a = {'vertices': tuple((x, 0, 0) for x in xs), 'faces': ()}
        b = {'vertices': tuple((y, 0, 0) for y in ys), 'faces': ()}
        self.assertEqual(G.signature(a), G.signature(b))         # the necessary condition is shared
        self.assertIs(G.congruent_points(a, b), False)
        self.assertIs(G.congruent_points(a, {'vertices': tuple((17 - x, 0, 0) for x in xs), 'faces': ()}), True)
        self.assertFalse(G.sameness(a, b)['congruent'])

    def test_same_points_different_faces_are_not_congruent_solids(self):
        c = G.cube(2)
        tri = []
        for f in c['faces']:
            tri += [(f[0], f[1], f[2]), (f[0], f[2], f[3])]
        split = {**c, 'faces': tuple(tri)}
        self.assertIs(G.solid(split)['valid_solid'], True)         # a triangulated cube is a solid ...
        self.assertIs(G.congruent_points(c, split), True)
        self.assertFalse(G.is_cube(split))                         # ... but not a cube with square faces
        same = G.sameness(split, c)
        self.assertTrue(same['valid_solid'])
        self.assertFalse(same['congruent'])

    def test_hull_volume_matches_the_reference_solids(self):
        # the "wraps the hull once" rule compares the surface volume with this independent hull volume
        for sh, vol in ((G.cube(2), 8), (G.octahedron(), Fraction(4, 3)), (G.square_pyramid(), Fraction(8, 3)),
                        (G.tetrahedron(), Fraction(8, 3))):
            v = G.shape(sh)['v']
            planes = {}
            for face in G.shape(sh)['f']:
                n = G._normal(v, face)
                sc = abs(next(c for c in n if c != 0))
                n = tuple(c / sc for c in n)
                planes[(n, G._dot(n, v[face[0]]))] = n
            self.assertEqual(G._hull_volume(v, planes), vol)
            self.assertEqual(G.solid(sh)['volume'], vol)

    def test_wrong_shape_with_right_counts(self):
        squashed = G.cube(2)
        squashed = {**squashed, 'vertices': tuple((x, y, z * 2) for x, y, z in squashed['vertices'])}
        self.assertIs(G.solid(squashed)['valid_solid'], True)
        self.assertFalse(G.is_cube(squashed))
        self.assertIs(G.similar(squashed, G.cube(2)), False)

    def test_identical_requires_the_same_record(self):
        c = G.cube(2)
        same = G.sameness(c, c)
        self.assertTrue(all(same[k] for k in G.LEVELS))
        self.assertEqual(same['version'], G.VERSION)


class InPrograms(unittest.TestCase):
    def test_builtins_from_a_program(self):
        from symblic.kernel import run as SR
        src = ('let c = cube(2).\nlet f = shape_facts(c).\nassert f.valid_solid.\nassert is_cube(c, 2).\n'
               'let s = sameness(c, cube(2)).\nassert s.identical.\nshow solid_check(c).volume.\n')
        rep = SR.Run(src, None, None, {}).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        self.assertEqual(rep['outputs'][-1]['value'], 8)


if __name__ == '__main__':
    unittest.main()


class CheckedStyle(unittest.TestCase):
    """The benchmark's checked shape programs (symblic_bench.shape_source(obj, 'symblic')) admit exactly one
    canonical solid per object: the claim behind "every accepted answer is identical"."""

    def run_program(self, obj, answer):
        from symblic.bench import bench as B
        from symblic.kernel import run as SR

        class Fake:
            def call(self, req):
                return {'ok': True, 'json': {'answer': answer}}
        src = B.shape_source(obj, 'symblic').replace('retries=3', 'retries=0')
        target = B.B_plain(G._value(B.shape_target(obj)))
        return SR.Run(src, {'description': 'x', 'target': target}, Fake(), {'by': 'claude:haiku'}).execute()

    def test_the_reference_is_accepted_and_identical(self):
        from symblic.bench import bench as B
        for obj in B.SHAPES:
            ref = B.B_plain(G._value(B.shape_target(obj)))
            rep = self.run_program(obj, ref)
            self.assertEqual(rep['status'], 'done', (obj, rep.get('error')))
            self.assertTrue(rep['outputs'][-1]['value']['identical'], obj)

    def test_every_perturbation_is_rejected(self):
        from symblic.bench import bench as B
        for obj in B.SHAPES:
            ref = G._value(B.shape_target(obj))
            n = len(ref['vertices'])
            variants = {
                'renumbered': moved(ref, renumber=list(range(n))[::-1]),
                'moved': moved(ref, shift=(1, 0, 0)),
                'scaled': moved(ref, scale=2),
                'rotated': moved(ref, ((0, -1, 0), (1, 0, 0), (0, 0, 1))),
                'faces reversed': {**ref, 'faces': tuple(f[::-1] for f in ref['faces'])},
                'a face missing': {**ref, 'faces': ref['faces'][:-1]},
            }
            if obj == 'cube':
                tri = []
                for f in ref['faces']:
                    tri += [(f[0], f[1], f[2]), (f[0], f[2], f[3])]
                variants['triangulated'] = {**ref, 'faces': tuple(tri)}
            for name, v in variants.items():
                if G.canonical(v) == G.canonical(ref) and G._value(v) == ref:
                    continue                       # a symmetry that maps the solid onto itself exactly
                rep = self.run_program(obj, B.B_plain(G._value(v)))
                same = rep['status'] == 'done'
                self.assertFalse(same and G._value(v) != ref, f'{obj}: {name} was accepted')

    def test_the_vertex_conditions_admit_exactly_the_required_points(self):
        # a model count over a grid that contains every point the conditions could admit (they pin each
        # coordinate to -1, 0, 1 or the listed values): the admitted points are exactly as many as the solid
        # must have, so the vertex set is unique
        import itertools
        grid = list(itertools.product(range(-2, 3), repeat=3))
        cube = [p for p in grid if all(c in (1, -1) for c in p)]
        tetra = [p for p in cube if p[0] * p[1] * p[2] == 1]
        octa = [p for p in grid if sorted(p) in ([-1, 0, 0], [0, 0, 1])]
        self.assertEqual((len(cube), len(tetra), len(octa)), (8, 4, 6))
        self.assertEqual({tuple(v) for v in G.cube(2)['vertices']}, set(cube))
        self.assertEqual({tuple(v) for v in G.tetrahedron()['vertices']}, set(tetra))
        self.assertEqual({tuple(v) for v in G.octahedron()['vertices']}, set(octa))
