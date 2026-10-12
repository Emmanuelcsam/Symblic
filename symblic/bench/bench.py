#!/usr/bin/env python3
"""The Symblic benchmark runner: measures what Symblic claims, against ground truth, with real applicators.

    python3 -m symblic.bench.bench --out DIR [--suite identity,arith,logic,flower] [--quick] [--resume]
    python3 -m symblic.bench.bench --out DIR --report-only

Suites (truth for the legacy suites is computed by code; ambiguity uses author-stipulated synthetic intentions):
  identity  single typed statements asked of many applicators, once as a plain prose prompt and once as a
            Symblic ask: does structure make different agents return the SAME canonical answer?
  arith     generated multi-step word problems (GSM-Symbolic style: templates, seeded numbers, some with an
            irrelevant sentence). Conditions per small model: direct prose, a typed ask, translate-then-compute
            (the model writes a formula, the kernel evaluates it) and, with --council, several applicators
            voting on the formula's VALUE (key=eval(it)); --big models answer directly.
  logic     generated family trees told as a shuffled story; questions need several hops. Direct answer vs
            Symblic: the model extracts parent facts, the kernel's Datalog answers.
  flower    essays describing flowers; each applicator extracts a closed FlowerSpec, the kernel draws it.
            Same drawing fingerprint = same reading of the essay.
  shape     describe a solid in four styles (minimal, everyday, technical, technical + kernel checks) and
            judge every answer with the exact geometry checker.
  tighten   rewrite statements that a probe panel disagrees on, then measure agreement on a held-out panel.
  ambiguity separate development/held-out families, ambiguity detection, scripted clarification and exact
            intent fields (ambiguity.py; must run alone).
  matched   frozen direct-versus-typed comparison from a manifest (matched.py; must run alone).

Results are appended to DIR/results.jsonl (resumable: a finished cell is never asked again; a failed cell whose
error looks transient is asked again on the next run) and summarised in DIR/report.md.

Applicators. Every model call goes through ``symblic.providers.applicators.Applicators``: ``ollama:MODEL[@HOST]``
for a local or configured Ollama server, ``command:NAME`` for a CLI agent you configured as SYMBLIC_COMMAND_NAME,
``fake:...`` for dry runs (see symblic/providers/README.md). The defaults below are small local Ollama models;
pass your own lists with --identity-apps, --small, --big, --council, --shape-apps and the --tighten-* options.

Status: measured machinery. The suites' item generators and graders are deterministic and code-checked; the
report states its own limits (heuristic prose grading, shared questions, no binomial intervals). No result
about any particular model is claimed by this file.

Depends on: ``symblic.kernel.language``/``run``, ``symblic.adapters.geometry``/``render`` (shape and flower
suites), ``symblic.authoring.tighten`` (tighten suite). Nothing runs on import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction

from symblic.kernel import language as S
from symblic.kernel import run as SR

# A failed cell whose error matches this is an infrastructure failure, not a model result: asked again next run.
TRANSIENT = re.compile(r'still busy|no capacity|not available|unavailable|stopped|did not answer in time|daemon|node offline|'
                       r'usage limit|rate limit|did not start|not answering|lost', re.I)

# ---------------------------------------------------------------------------
# Suite: identity
# ---------------------------------------------------------------------------

IDENTITY = [
    ('spider', 'Int in 0..20', 'How many legs does a spider have?', 8),
    ('mult', 'Int', 'What is 17 multiplied by 23?', 391),
    ('prime91', 'Bool', 'Is 91 a prime number?', False),
    ('planet', 'one of {mercury, venus, earth, mars, jupiter, saturn, uranus, neptune}',
     'Which planet in our solar system is the largest?', 'jupiter'),
    ('capital', 'one of {sydney, melbourne, canberra, perth, brisbane}', 'What is the capital city of Australia?',
     'canberra'),
    ('water', 'one of {solid, liquid, gas}', 'What state is water in at 25 degrees Celsius and normal air pressure?',
     'liquid'),
    ('sort', 'List of Text length 5', 'Sort these words alphabetically: pear, apple, mango, kiwi, banana.',
     ['apple', 'banana', 'kiwi', 'mango', 'pear']),
    ('vowels', 'Set of one of {a, e, i, o, u}', 'Which vowels appear in the word "education"?',
     ['a', 'e', 'i', 'o', 'u']),
    ('hexagon', 'Int', 'How many diagonals does a convex hexagon have?', 9),
    ('fraction', 'Number to 4 places', 'What is 3/8 written as a decimal?', '0.375'),
    ('syllogism', 'Bool', 'All bloops are razzies and all razzies are lazzies. Are all bloops definitely lazzies?',
     True),
    ('weekday', 'one of {monday, tuesday, wednesday, thursday, friday, saturday, sunday}',
     'If today is Thursday, what day of the week will it be 100 days from today?', 'saturday'),
    ('record', 'Record {element: one of {hydrogen, helium, carbon, oxygen, iron}, protons: Int in 1..30}',
     'Name the element with 8 protons, and give its proton count.', {'element': 'oxygen', 'protons': 8}),
    ('negation', 'Bool', 'Is it false that 2 + 2 is not equal to 5?', False),
    ('count', 'Int in 0..10', 'How many times does the letter r appear in the word "strawberry"?', 3),
    ('order', 'List of one of {cat, mouse, elephant, horse} length 4',
     'Order these animals from lightest to heaviest: cat, mouse, elephant, horse.', ['mouse', 'cat', 'horse', 'elephant']),
]


def identity_items() -> list:
    """The identity suite: fixed questions with a typed answer and a known truth."""
    out = []
    for key, ty, q, truth in IDENTITY:
        out.append({'suite': 'identity', 'item': key, 'type': ty, 'question': q, 'truth': truth})
    return out


# ---------------------------------------------------------------------------
# Suite: arithmetic word problems (generated)
# ---------------------------------------------------------------------------

NOOPS = ['Five of the items are a slightly different colour, which does not change anything.',
         'The weather that day was unusually warm.',
         'A friend once said that numbers like these are easy.',
         'Last year the same thing cost a little more.']


def arith_items(n_per_template: int, seed: int = 20261002) -> list:
    """Each template draws from its own seeded stream and numbers its items 00, 01, ..., so a run with
    n_per_template=3 is exactly the first three of a run with 5 (results carry over)."""
    items = []
    rng = None

    def add(template_id, text, answer):
        noop = rng.random() < 0.35
        if noop:
            parts = text.split('. ')
            parts.insert(max(1, len(parts) - 1), rng.choice(NOOPS).rstrip('.'))
            text = '. '.join(parts)
        k = sum(1 for it in items if it['template'] == template_id)
        items.append({'suite': 'arith', 'item': f'{template_id}-{k:02d}', 'template': template_id,
                      'question': text, 'truth': int(answer) if Fraction(answer).denominator == 1 else answer,
                      'noop': noop})

    rng = random.Random(f'{seed}-bakery')
    for _ in range(n_per_template):
        a, b = rng.randint(6, 15), rng.choice([12, 16, 20, 24, 28])
        q = rng.choice([4, 2])
        p = rng.randint(1, q - 1)
        c = rng.randint(3, 15)
        total = a * b
        add('bakery', f'A baker makes {a} trays of {b} rolls. She sells {p}/{q} of the rolls and gives {c} rolls to a '
                      f'shelter. How many rolls are left?', total - total * p // q - c)
    rng = random.Random(f'{seed}-marbles')
    for _ in range(n_per_template):
        a, b, c, d, e = rng.randint(10, 40), rng.randint(2, 6), rng.randint(5, 12), rng.randint(1, 9), rng.randint(3, 7)
        add('marbles', f'Tom has {a} marbles. He buys {b} bags with {c} marbles in each bag, then loses {d} marbles. '
                       f'He shares the marbles equally among {e} friends, giving each friend as many as possible, and '
                       f'keeps the remainder. How many marbles does Tom keep?', (a + b * c - d) % e)
    rng = random.Random(f'{seed}-train')
    for _ in range(n_per_template):
        b, d = rng.choice([40, 60, 80, 90]), rng.choice([30, 45, 60, 120])
        a, c = b * rng.randint(1, 3) // 2 * 2, d * rng.randint(1, 3)
        if a == 0:
            a = b
        minutes = Fraction(a, b) * 60 + Fraction(c, d) * 60
        add('train', f'A train travels {a} km at {b} km per hour and then {c} km at {d} km per hour. How many minutes '
                     f'does the whole trip take?', minutes)
    rng = random.Random(f'{seed}-shop')
    for _ in range(n_per_template):
        a, b, c, d = rng.randint(2, 9), rng.randint(3, 12), rng.randint(2, 8), rng.randint(1, 5)
        e = (a * c + b * d) + rng.randint(1, 30)
        add('shop', f'Pens cost {a} dollars each and notebooks cost {b} dollars each. Mia buys {c} pens and {d} '
                    f'notebooks and pays with {e} dollars. How many dollars of change does she get?', e - (a * c + b * d))
    rng = random.Random(f'{seed}-tank')
    for _ in range(n_per_template):
        a = rng.choice([200, 400, 500, 800, 1000])
        p = rng.choice([25, 50, 75])
        b = rng.choice([20, 40, 100])
        q = rng.choice([10, 20, 25, 50])
        base = a * p // 100
        b = (20 - base % 20) % 20 + b                 # start is a multiple of 20, so q% of it is whole
        start = base + b
        add('tank', f'A tank holds {a} litres. It is {p}% full. Then {b} litres are added, and after that {q}% of the '
                    f'water in the tank is drained. How many litres of water remain?', start - start * q // 100)
    rng = random.Random(f'{seed}-workers')
    for _ in range(n_per_template):
        c = rng.choice([2, 3, 4, 5, 6])
        a = c * rng.randint(2, 4)                 # a multiple of c, so a*b/c is whole
        b = rng.randint(3, 12)
        add('workers', f'{a} workers can build a wall in {b} days. Working at the same rate, how many days would {c} '
                       f'workers need to build the same wall?', Fraction(a * b, c))
    rng = random.Random(f'{seed}-path')
    for _ in range(n_per_template):
        a, b, c = rng.randint(4, 20), rng.randint(3, 15), rng.randint(1, 3)
        add('path', f'A rectangular garden is {a} metres long and {b} metres wide. A path {c} metres wide runs all the '
                    f'way around the outside of the garden. What is the area of the path in square metres?',
            (a + 2 * c) * (b + 2 * c) - a * b)
    rng = random.Random(f'{seed}-stairs')
    for _ in range(n_per_template):
        a, b, c = rng.randint(3, 9), rng.randint(2, 6), rng.randint(2, 5)
        add('stairs', f'A building has {a} floors. Each floor has {b} flights of stairs, and each flight has {c * 4} '
                      f'steps. Ana climbs from the ground to the top floor and back down once. How many steps does '
                      f'she climb in total?', 2 * a * b * c * 4)
    return [it for it in items if Fraction(it['truth']).denominator == 1]


# ---------------------------------------------------------------------------
# Suite: family logic (generated)
# ---------------------------------------------------------------------------

NAMES = ['Ada', 'Ben', 'Cleo', 'Dov', 'Eli', 'Fay', 'Gus', 'Hana', 'Ivo', 'Jun', 'Kai', 'Lia', 'Max', 'Nia', 'Oto',
         'Pia', 'Quin', 'Rae', 'Sol', 'Tia', 'Uma', 'Vic', 'Wes', 'Xia', 'Yan', 'Zoe']


def logic_items(n: int, seed: int = 4242) -> list:
    """`n` generated family-tree stories with a multi-hop question (descendants, ancestors or cousins)."""
    rng = random.Random(seed)
    items = []
    k = -1
    while len(items) < n:
        k += 1
        names = rng.sample(NAMES, 11)
        sex = {p: rng.choice(['mother', 'father']) for p in names}
        links = []
        gen = [[names[0]], names[1:3], names[3:6], names[6:11]]
        for g in range(1, len(gen)):
            for child in gen[g]:
                links.append((rng.choice(gen[g - 1]), child))
        parents = defaultdict(set)
        children = defaultdict(set)
        for p, c in links:
            parents[c].add(p)
            children[p].add(c)

        def anc(x):
            out, todo = set(), list(parents[x])
            while todo:
                y = todo.pop()
                if y not in out:
                    out.add(y)
                    todo.extend(parents[y])
            return out

        def desc(x):
            out, todo = set(), list(children[x])
            while todo:
                y = todo.pop()
                if y not in out:
                    out.add(y)
                    todo.extend(children[y])
            return out

        def cousins(x):
            out = set()
            for p in parents[x]:
                for g in parents[p]:
                    for q in children[g]:
                        if q != p:
                            out |= children[q]
            return out - {x}

        story = [f'{p} is the {sex[p]} of {c}.' for p, c in links]
        rng.shuffle(story)
        kind = ['descendants', 'ancestors', 'cousins'][len(items) % 3]
        if kind == 'descendants':
            cands = [x for x in gen[1] if len(desc(x)) >= 3]
            who = rng.choice(cands) if cands else None
            truth, q = (desc(who) if who else set()), f'Who are all the descendants of {who} (children, grandchildren and so on)?'
        elif kind == 'ancestors':
            who = rng.choice(gen[3])
            truth, q = anc(who), f'Who are all the ancestors of {who} (parents, grandparents and so on)?'
        else:
            cands = [x for x in gen[3] if len(cousins(x)) >= 2]
            who = rng.choice(cands) if cands else None
            truth, q = (cousins(who) if who else set()), (f'Who are all the first cousins of {who}? (A first cousin is '
                                                            f'a child of a sibling of one of {who}\'s parents; siblings '
                                                            f'share a parent.)')
        if not who or len(truth) < 2:
            continue
        items.append({'suite': 'logic', 'item': f'{kind}-{len(items):02d}', 'kind': kind, 'who': who, 'story': ' '.join(story),
                      'question': q, 'truth': sorted(x.lower() for x in truth), 'links': len(links)})
    return items


LOGIC_RULES = {
    'descendants': ('rule desc(X, Y) if parent(X, Y).\nrule desc(X, Z) if parent(X, Y) and desc(Y, Z).\n'
                    'let answer = query desc({who}, W).\n'),
    'ancestors': ('rule anc(X, Y) if parent(Y, X).\nrule anc(X, Z) if parent(Y, X) and anc(Y, Z).\n'
                  'let answer = query anc({who}, W).\n'),
    'cousins': ('rule sib(A, B) if parent(G, A) and parent(G, B) and A != B.\n'
                'rule cousin(X, Y) if parent(P, X) and parent(Q, Y) and sib(P, Q) and X != Y.\n'
                'let answer = query cousin({who}, W).\n'),
}


# ---------------------------------------------------------------------------
# Suite: flowers
# ---------------------------------------------------------------------------

FLOWER_TYPE = ('Record {petals: Int in 3..24, shape: one of {round, pointed, heart, teardrop, spatula, fringed}, '
               'layers: Int in 1..4, color: one of {red, pink, orange, yellow, gold, white, violet, purple, blue}, '
               'center: one of {brown, gold, yellow, black, green, white}, leaves: Int in 0..6, stem: Bool}')
FLOWERS = [
    ('daisy', 'A daisy-like flower: two rings of narrow, round-tipped white petals, thirteen petals in each ring, around '
              'a yellow centre. It stands on a stem with two leaves.',
     {'petals': 13, 'shape': 'round', 'layers': 2, 'color': 'white', 'center': 'yellow', 'leaves': 2, 'stem': True}),
    ('violet', 'Five violet petals, each shaped like a heart with a notch at its tip, in one ring. The centre is gold. '
               'The flower is shown alone with no stem and no leaves.',
     {'petals': 5, 'shape': 'heart', 'layers': 1, 'color': 'violet', 'center': 'gold', 'leaves': 0, 'stem': False}),
    ('star', 'Its eight orange petals are long and come to a sharp point, arranged in a single ring around a black '
             'centre. A stem carries three leaves.',
     {'petals': 8, 'shape': 'pointed', 'layers': 1, 'color': 'orange', 'center': 'black', 'leaves': 3, 'stem': True}),
    ('carnation', 'A carnation: three layered rings of red petals with fringed, ragged edges, twenty petals per ring, '
                  'and a green centre. It has a stem with one leaf.',
     {'petals': 20, 'shape': 'fringed', 'layers': 3, 'color': 'red', 'center': 'green', 'leaves': 1, 'stem': True}),
    ('poppy', 'Six wide petals, broad at the outer end and narrow at the base like a spoon, coloured pink, in one ring. '
              'The middle is brown. No stem is drawn.',
     {'petals': 6, 'shape': 'spatula', 'layers': 1, 'color': 'pink', 'center': 'brown', 'leaves': 0, 'stem': False}),
    ('blue', 'Four blue teardrop-shaped petals in two rings (so the flower looks like it has eight), around a white '
             'centre, on a stem with four leaves.',
     {'petals': 4, 'shape': 'teardrop', 'layers': 2, 'color': 'blue', 'center': 'white', 'leaves': 4, 'stem': True}),
]


def flower_items() -> list:
    """The flower suite: essays and the exact FlowerSpec each describes."""
    return [{'suite': 'flower', 'item': k, 'question': essay, 'truth': truth} for k, essay, truth in FLOWERS]


# ---------------------------------------------------------------------------
# Suite: shapes (the operator's cube hypothesis: does a more formal description make every agent build the
# same object?)
# ---------------------------------------------------------------------------

ORDER_RULES = ('Number the vertices in ascending order of x, then y, then z. '
               'Write each face as its vertex numbers in counter-clockwise order, seen from outside the solid; '
               'start each face with its smallest vertex number. '
               'Sort the faces in ascending order of their vertex numbers (compare the first number, then the '
               'second, and so on).')


def _steps(lines):
    return '\n'.join(f'{i}. {t}' for i, t in enumerate(lines, 1))


SHAPES = {
    'cube': {
        'minimal': 'Construct a cube.',
        'everyday': ('Construct a cube with edges 2 units long, centred at the origin (0, 0, 0), with every face '
                     'perpendicular to the x, y or z axis.'),
        'technical': _steps([
            'Use a right-handed x, y, z coordinate system. All lengths are in units.',
            'The solid is a cube. Each edge is 2 units long.',
            'The centre of the cube is at (0, 0, 0).',
            'Each face is perpendicular to the x axis, the y axis or the z axis.'] + ORDER_RULES.split('; ')),
    },
    'tetrahedron': {
        'minimal': 'Construct a regular tetrahedron.',
        'everyday': ('Construct a regular tetrahedron centred at the origin, with edges 2√2 units long and one '
                     'vertex at (1, 1, 1).'),
        'technical': _steps([
            'Use a right-handed x, y, z coordinate system. All lengths are in units.',
            'The solid is a regular tetrahedron with 4 vertices and 4 triangular faces.',
            'The vertices are the corners of the cube with corners (±1, ±1, ±1) that have zero or two negative '
            'coordinates.'] + ORDER_RULES.split('; ')),
    },
    'octahedron': {
        'minimal': 'Construct a regular octahedron.',
        'everyday': ('Construct a regular octahedron centred at the origin whose six vertices lie on the x, y and z '
                     'axes, each 1 unit from the origin.'),
        'technical': _steps([
            'Use a right-handed x, y, z coordinate system. All lengths are in units.',
            'The solid is a regular octahedron with 6 vertices and 8 triangular faces.',
            'The vertices are (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1) and (0, 0, -1).',
            'Each face is a triangle of three vertices that lie on three different axes.'] + ORDER_RULES.split('; ')),
    },
    'pyramid': {
        'minimal': 'Construct a square pyramid.',
        'everyday': ('Construct a square pyramid. Its base is a 2 by 2 square in the plane z = 0, centred at the '
                     'origin, with sides parallel to the x and y axes. Its apex is 2 units above the centre of the '
                     'base.'),
        'technical': _steps([
            'Use a right-handed x, y, z coordinate system. All lengths are in units.',
            'The solid is a pyramid with a square base: 5 vertices, 1 square face and 4 triangular faces.',
            'The base corners are (-1, -1, 0), (1, -1, 0), (1, 1, 0) and (-1, 1, 0).',
            'The apex is (0, 0, 2).'] + ORDER_RULES.split('; ')),
    },
}
SHAPE_TYPE = ('Record {vertices: List of (List of Number length 3) length 4..20, '
              'faces: List of (List of Int length 3..8) length 4..24}')
SHAPE_ASK = ('ask solid: Shape "Read the description and construct the solid it describes. Give its vertices as '
             '[x, y, z] coordinates and its faces as lists of vertex numbers; number the vertices from 1." '
             'from description with effort=medium, vote=whole')
SHAPE_SOURCE = ('given description: Text.\ngiven target: Any.\n'
                f'define Shape as {SHAPE_TYPE}.\n' + SHAPE_ASK + '\n'
                'let s = sameness(solid, target).\n'
                'if s.valid_solid then\n  let form = hash(canonical_shape(solid)).\nend.\n'
                'show s.\n')
# The "symblic" style: the technical description plus the end state as kernel checks (rules 14, 17 and 22 of
# RESEARCH-LANGUAGE.md). A failed check re-asks with the reason. Each object's checks admit exactly ONE canonical
# record: the vertex conditions fix the point set, a valid convex solid's faces are its hull facets (face count
# pins the pyramid's square base), and `solid = canonical_shape(solid)` fixes numbering and order. So every
# ACCEPTED answer is identical by construction; what is measured is how many applicators reach acceptance.
SHAPE_COMMON = ('ensure solid_check(solid).valid_solid because solid_check(solid).problems.',)
SHAPE_CHECKS = {
    'cube': ('ensure is_cube(solid, 2) because "the solid must be a cube with every edge 2 units long".',
             'ensure all p in solid.vertices: all c in p: c = 1 or c = -1 because "the cube is centred at the '
             'origin with faces perpendicular to the axes, so every coordinate is 1 or -1".'),
    'tetrahedron': ('ensure len(solid.vertices) = 4 and shape_facts(solid).equal_edges because "a regular '
                    'tetrahedron has 4 vertices and 6 equal edges".',
                    'ensure all p in solid.vertices: all c in p: c = 1 or c = -1 because "each vertex is a corner '
                    'of the cube with corners (±1, ±1, ±1)".',
                    'ensure all p in solid.vertices: product(p) = 1 because "each vertex has zero or two negative '
                    'coordinates".'),
    'octahedron': ('ensure len(solid.vertices) = 6 and len(solid.faces) = 8 because "a regular octahedron has 6 '
                   'vertices and 8 triangular faces".',
                   'ensure all p in solid.vertices: sort(p) = [-1, 0, 0] or sort(p) = [0, 0, 1] because "each '
                   'vertex lies on an axis, 1 unit from the origin".'),
    'pyramid': ('ensure set(solid.vertices) = set([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0], [0, 0, 2]]) '
                'because "the vertices are the four base corners and the apex (0, 0, 2)".',
                'ensure len(solid.faces) = 5 because "the base is one square face and there are 4 triangular '
                'sides".'),
}
SHAPE_ORDER_CHECK = ('ensure solid = canonical_shape(solid) because "number the vertices in ascending order of x, '
                     'then y, then z; write each face counter-clockwise seen from outside, starting at its smallest '
                     'vertex number; sort the faces".')


def shape_source(obj: str, style: str) -> str:
    """The Symblic program for one shape cell; the 'symblic' style adds kernel end-state checks."""
    if style != 'symblic':
        return SHAPE_SOURCE
    checks = SHAPE_COMMON + SHAPE_CHECKS[obj] + (SHAPE_ORDER_CHECK,)
    return ('given description: Text.\ngiven target: Any.\n'
            f'define Shape as {SHAPE_TYPE}.\n' + SHAPE_ASK.replace('vote=whole', 'vote=whole, retries=3') + '\n'
            + '\n'.join(checks) + '\n'
            'let s = sameness(solid, target).\n'
            'let form = hash(canonical_shape(solid)).\n'
            'show s.\n')


SAMENESS = ('schema_valid', 'valid_solid', 'similar', 'congruent', 'same_placement', 'identical')


def versions() -> dict:
    """The checker versions a row was judged under (fingerprints and geometry verdicts changed between them)."""
    from symblic.adapters import geometry as G
    return {'lang': S.VERSION, 'canon': S.CANON_VERSION, 'geometry': G.VERSION}


def rejudge_shape(row: dict) -> dict:
    """A shape row judged again from its stored answer with the current geometry checker (levels, correct and
    form are functions of the answer; the answer is the measurement)."""
    from symblic.adapters import geometry as G
    if row.get('value') is None:
        return {**row, 'levels': {k: False for k in SAMENESS}, 'correct': False, 'judged': G.VERSION}
    answer = G._value(row['value'])
    same = G.sameness(answer, G._value(shape_target(row['object'])))
    form = S.fingerprint(G._value(G.canonical(answer))) if same['valid_solid'] else None
    return {**row, 'levels': {k: bool(same.get(k)) for k in SAMENESS}, 'correct': bool(same['same_placement']),
            'form': form, 'judged': G.VERSION, 'undecided': list(same.get('undecided') or ())}


def shape_target(name):
    """The reference solid for a shape name, built by the geometry adapter."""
    from symblic.adapters import geometry as G
    return {'cube': lambda: G.canonical(G.cube(2)), 'tetrahedron': G.tetrahedron, 'octahedron': G.octahedron,
            'pyramid': G.square_pyramid}[name]()


SHAPE_STYLES = ('minimal', 'everyday', 'technical', 'symblic')


def shape_items(styles=SHAPE_STYLES) -> list:
    """One item per (solid, description style)."""
    out = []
    for obj, texts in SHAPES.items():
        for style in styles:
            text = texts['technical' if style == 'symblic' else style]
            out.append({'suite': 'shape', 'item': f'{obj}-{style}', 'object': obj, 'style': style,
                        'question': text, 'truth': None})
    return out


# ---------------------------------------------------------------------------
# Suite: tighten (the convergence compiler: can measured disagreement be turned into a statement that NEW
# readers answer the same way?)
# ---------------------------------------------------------------------------

# Everyday statements with known competing conventions, plus controls with one reading. No item has a
# ground truth here: the measure is agreement among readers who never saw the rewrite (held-out panel).
TIGHTEN_ITEMS = [
    ('days-in-year', 'Int in 300..400', 'How many days are in a year?', 'ambiguous'),
    ('boiling-point', 'Number', 'What is the boiling point of water?', 'ambiguous'),
    ('marathon', 'Number', 'How long is a marathon?', 'ambiguous'),
    ('tomato', 'one of {fruit, vegetable}', 'Is a tomato a fruit or a vegetable?', 'ambiguous'),
    ('continents', 'Int in 3..9', 'How many continents are there?', 'ambiguous'),
    ('first-weekday', 'one of {monday, tuesday, wednesday, thursday, friday, saturday, sunday}',
     'What is the first day of the week?', 'ambiguous'),
    ('round-half', 'Int', 'Round 2.5 to the nearest whole number.', 'ambiguous'),
    ('zero-natural', 'Bool', 'Is zero a natural number?', 'ambiguous'),
    ('billion-zeros', 'Int in 6..15', 'How many zeros are in one billion?', 'ambiguous'),
    ('date-month', 'one of {january, february, march, april, may, june, july, august, september, october, '
     'november, december}', 'In the date 03/04/2025, which month is it?', 'ambiguous'),
    ('tallest-mountain', 'one of {everest, k2, mauna kea, chimborazo, denali}',
     'What is the tallest mountain on Earth?', 'ambiguous'),
    ('ton-kg', 'Number', 'How many kilograms are in a ton?', 'ambiguous'),
    ('tablespoon', 'Int in 1..6', 'How many teaspoons are in a tablespoon?', 'ambiguous'),
    ('speed-of-light', 'Number', 'What is the speed of light?', 'ambiguous'),
    ('freezing-point', 'Number', 'At what temperature does water freeze?', 'ambiguous'),
    ('weeks-in-year', 'Number', 'How many weeks are in a year?', 'ambiguous'),
    ('primary-colours', 'Set of one of {red, green, blue, yellow, cyan, magenta}', 'What are the primary colours?',
     'ambiguous'),
    ('ounces-pound', 'Int in 10..20', 'How many ounces are in a pound?', 'ambiguous'),
    ('control-spider', 'Int in 0..20', 'How many legs does a spider have?', 'control'),
    ('control-times', 'Int', 'What is 7 times 8?', 'control'),
    ('control-byte', 'Int in 1..64', 'How many bits are in a byte?', 'control'),
    ('control-feet-mile', 'Int', 'How many feet are in a mile?', 'control'),
    ('control-one-prime', 'Bool', 'Is 1 a prime number?', 'control'),
    ('control-ocean', 'one of {atlantic, pacific, indian, arctic, southern}', 'Which is the largest ocean on Earth?',
     'control'),
]


def tighten_source(ty: str, question: str) -> str:
    """A one-ask Symblic program for a tighten item."""
    return f'ask answer: {ty} {json.dumps(question)} with effort=low\nshow answer.\n'


def tighten_items() -> list:
    """Everyday statements with competing conventions, plus single-reading controls (no ground truth)."""
    return [{'suite': 'tighten', 'item': name, 'type': ty, 'question': q, 'kind': kind, 'truth': None}
            for name, ty, q, kind in TIGHTEN_ITEMS]


# ---------------------------------------------------------------------------
# Running cells
# ---------------------------------------------------------------------------

def _num_from_text(text: str):
    m = re.findall(r'ANSWER\s*[:=]\s*\$?\s*(-?[\d,]+(?:\.\d+)?)', text or '', re.I)
    if not m:
        m = re.findall(r'(-?\d[\d,]*(?:\.\d+)?)', text or '')
    if not m:
        return None
    try:
        return S.norm_num(Fraction(m[-1].replace(',', '')))
    except (ValueError, ZeroDivisionError):
        return None


def _names_from_text(text: str) -> list:
    m = re.findall(r'ANSWER\s*[:=]\s*(.+)', text or '', re.I)
    line = m[-1] if m else (text or '').strip().splitlines()[-1] if (text or '').strip() else ''
    words = re.findall(r'[A-Z][a-z]+', line)
    stop = {'None', 'Answer', 'The', 'And'}
    return sorted({w.lower() for w in words if w not in stop})


def _norm_prose(text: str) -> str:
    """Lower case, markup and surrounding punctuation off, runs of space and list separators collapsed;
    a decimal point between digits is kept."""
    t = (text or '').strip().lower()
    t = re.sub(r'[*`_"\'()\[\]]+', ' ', t)
    t = re.sub(r'(?<!\d)[.,;:!?]|[.,;:!?](?!\d)', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


class Bench:
    """One results folder: the cells already finished there, the applicators to ask, and the suite builders.

    A *cell* is one (suite, item, condition, applicator) measurement; its id is 'suite|item|condition|by'.
    """

    def __init__(self, out: str, apps=None, log=print, retry: str = ''):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.path = os.path.join(out, 'results.jsonl')
        self.done = {}
        for row in SR._read_jsonl(self.path):
            if row.get('cell'):
                again = retry and re.search(retry, f'{row["cell"]} {row.get("error") or ""}')
                if not row.get('ok') and (TRANSIENT.search(str(row.get('error') or '')) or again):
                    self.done.pop(row['cell'], None)      # an infrastructure failure is asked again
                    continue
                self.done[row['cell']] = row
        self.lock = threading.Lock()
        self.log = log
        if apps is None:
            from symblic.providers import applicators as providers
            apps = providers.Applicators(owner_label='symblic benchmark', run_id=os.path.basename(out))
        self.apps = apps

    def record(self, row: dict) -> dict:
        """Append one finished cell to results.jsonl (thread-safe)."""
        with self.lock:
            self.done[row['cell']] = row
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
        return row

    # -- primitive runners ------------------------------------------------------------
    def prose(self, by: str, prompt: str, effort: str = 'medium') -> dict:
        """Ask one applicator a plain prose prompt (temperature 0, fixed seed)."""
        app = S.parse_applicator(by)
        req = {'app': app, 'system': 'Answer the question directly and correctly.', 'prompt': prompt, 'schema': None,
               'sample': 0, 'temperature': 0, 'seed': 7, 'effort': {'low': 'low', 'medium': 'medium'}.get(effort, ''),
               'tools': 'none', 'key': ''}
        t0 = time.time()
        r = self.apps.call(req)
        return {'ok': bool(r.get('ok')), 'text': str(r.get('text') or (json.dumps(r['json']) if r.get('json') is not None
                                                                         else '')),
                'error': r.get('error', ''), 'ms': int((time.time() - t0) * 1000), 'node': r.get('node', '')}

    def symblic(self, source: str, by, inputs=None, folder=None) -> dict:
        """Run a Symblic program with applicator(s) `by`; returns the run report plus its trace."""
        t0 = time.time()
        run = SR.Run(source, inputs, self.apps, {'by': by, 'parallel': 6, 'max_asks': 200}, folder=folder)
        rep = run.execute()
        rep['ms'] = int((time.time() - t0) * 1000)
        rep['trace'] = run.trace          # retries and per-statement status (not part of the run report)
        return rep

    def cell(self, cell: str, fn) -> dict:
        """Run one cell unless it already finished; an exception becomes a failed row, never a crash."""
        if cell in self.done:
            return self.done[cell]
        t0 = time.time()
        try:
            row = fn()
        except Exception as e:  # noqa: BLE001
            row = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
        row['cell'] = cell
        row.setdefault('ms', int((time.time() - t0) * 1000))
        row['at'] = time.time()
        self.log(f'{cell}: {"ok" if row.get("ok") else "FAIL"} {row.get("value", "")!s:.60} '
                 f'{"✓" if row.get("correct") else "✗" if row.get("correct") is False else ""} '
                 f'({row["ms"] // 1000}s){" " + str(row.get("error"))[:80] if row.get("error") else ""}')
        return self.record(row)

    # -- suites --------------------------------------------------------------------------
    def identity_cells(self, apps: list) -> list:
        """(cell id, function) pairs: each identity question as prose and as a typed ask, per applicator."""
        cells = []
        for it in identity_items():
            truth_c = S.canon_json(S.coerce(it['truth'], S.resolve_type(_type(it['type']), {})))
            for by in apps:
                def prose_fn(it=it, by=by):
                    r = self.prose(by, f'{it["question"]}\nGive only the answer.', 'low')
                    return {**_base(it, 'prose', by), 'ok': r['ok'], 'value': _norm_prose(r['text'])[:200],
                            'hash': hashlib.sha256(_norm_prose(r['text']).encode()).hexdigest()[:16],
                            'error': r['error'], 'ms': r['ms'], 'node': r['node'],
                            'correct': _prose_correct(r['text'], it['truth']) if r['ok'] else None}

                def sym_fn(it=it, by=by, truth_c=truth_c):
                    src = f'ask answer: {it["type"]} {json.dumps(it["question"])} with effort=low\n'
                    rep = self.symblic(src, by)
                    b = next((x for x in rep['bindings'] if x['name'] == 'answer'), None)
                    return {**_base(it, 'symblic', by), 'ok': rep['status'] == 'done', 'value': b and b['value'],
                            'hash': b and b['hash'], 'error': (rep.get('error') or {}).get('message', ''),
                            'ms': rep['ms'], 'correct': (S.fingerprint(S.coerce(it['truth'], S.resolve_type(
                                _type(it['type']), {}))) == b['hash']) if b else None}
                cells.append((f'identity|{it["item"]}|prose|{by}', prose_fn))
                cells.append((f'identity|{it["item"]}|symblic|{by}', sym_fn))
        return cells

    def arith_cells(self, small: list, big: list, n_per: int, council: list, ultra: bool = False) -> list:
        """Arithmetic cells: direct (all models), typed and formula-then-compute (small), council votes (optional)."""
        cells = []
        for it in arith_items(n_per):
            for by in small + big:
                def direct(it=it, by=by):
                    r = self.prose(by, f'{it["question"]}\nSolve it step by step, then end with a final line '
                                       f'"ANSWER: <number>".')
                    v = _num_from_text(r['text']) if r['ok'] else None
                    return {**_base(it, 'direct', by), 'ok': r['ok'] and v is not None, 'value': S.to_plain(v),
                            'correct': v == it['truth'] if v is not None else False, 'error': r['error'],
                            'ms': r['ms'], 'node': r['node']}
                cells.append((f'arith|{it["item"]}|direct|{by}', direct))
            for by in small:
                def typed(it=it, by=by):
                    src = ('given problem: Text.\nask answer: Number "Solve the problem. The answer is a single number." '
                           'from problem with effort=medium\n')
                    rep = self.symblic(src, by, {'problem': it['question']})
                    b = next((x for x in rep['bindings'] if x['name'] == 'answer'), None)
                    v = _plain_num(b['value']) if b else None
                    return {**_base(it, 'typed', by), 'ok': b is not None, 'value': S.to_plain(v),
                            'correct': v == it['truth'] if v is not None else False,
                            'error': (rep.get('error') or {}).get('message', ''), 'ms': rep['ms']}

                def pal(it=it, by=by):
                    rep = self.symblic(PAL_SOURCE.format(votes=1), by, {'problem': it['question']})
                    return _pal_row(it, 'pal', by, rep)
                cells.append((f'arith|{it["item"]}|typed|{by}', typed))
                cells.append((f'arith|{it["item"]}|pal|{by}', pal))
            if council:
                def pal_council(it=it):
                    rep = self.symblic(PAL_SOURCE.format(votes=len(council)), council, {'problem': it['question']})
                    return _pal_row(it, 'pal-council', '+'.join(council), rep)

                def typed_council(it=it):
                    src = ('given problem: Text.\nask answer: Number "Solve the problem. The answer is a single number." '
                           f'from problem with effort=medium, votes={len(council)}\n')
                    rep = self.symblic(src, council, {'problem': it['question']})
                    b = next((x for x in rep['bindings'] if x['name'] == 'answer'), None)
                    v = _plain_num(b['value']) if b else None
                    return {**_base(it, 'typed-council', '+'.join(council)), 'ok': b is not None, 'value': S.to_plain(v),
                            'correct': v == it['truth'] if v is not None else False,
                            'agreement': (b or {}).get('meta', {}).get('agreement'),
                            'error': (rep.get('error') or {}).get('message', ''), 'ms': rep['ms']}
                def typed_ultra(it=it):
                    src = ('given problem: Text.\nask answer: Number "Solve the problem. The answer is a single number." '
                           f'from problem with effort=ultra, votes={len(council)}\n')
                    rep = self.symblic(src, council, {'problem': it['question']})
                    b = next((x for x in rep['bindings'] if x['name'] == 'answer'), None)
                    v = _plain_num(b['value']) if b else None
                    return {**_base(it, 'typed-ultra-council', '+'.join(council)), 'ok': b is not None,
                            'value': S.to_plain(v), 'correct': v == it['truth'] if v is not None else False,
                            'agreement': (b or {}).get('meta', {}).get('agreement'),
                            'error': (rep.get('error') or {}).get('message', ''), 'ms': rep['ms']}
                cells.append((f'arith|{it["item"]}|pal-council|council', pal_council))
                cells.append((f'arith|{it["item"]}|typed-council|council', typed_council))
                if ultra:
                    cells.append((f'arith|{it["item"]}|typed-ultra-council|council', typed_ultra))
        return cells

    def logic_cells(self, apps: list, n: int) -> list:
        """Family-logic cells: direct answer versus facts extracted by the model and answered by Datalog."""
        cells = []
        for it in logic_items(n):
            for by in apps:
                def direct(it=it, by=by):
                    r = self.prose(by, f'{it["story"]}\n\n{it["question"]}\nThink it through, then end with a final '
                                       f'line "ANSWER: name, name, ..." (or "ANSWER: none").')
                    names = _names_from_text(r['text']) if r['ok'] else []
                    return {**_base(it, 'direct', by), 'ok': r['ok'], 'value': names,
                            'correct': names == it['truth'], 'error': r['error'], 'ms': r['ms']}

                def datalog(it=it, by=by):
                    src = (LOGIC_SOURCE + LOGIC_RULES[it['kind']].format(who=it['who'].lower()) + 'show answer.\n')
                    rep = self.symblic(src, by, {'story': it['story']})
                    out = (rep.get('outputs') or [{}])[0].get('value') if rep.get('outputs') else None
                    names = sorted(str(x) for x in out) if isinstance(out, list) else None
                    return {**_base(it, 'symblic-datalog', by), 'ok': names is not None, 'value': names,
                            'correct': names == it['truth'] if names is not None else False,
                            'error': (rep.get('error') or {}).get('message', ''), 'ms': rep['ms']}
                cells.append((f'logic|{it["item"]}|direct|{by}', direct))
                cells.append((f'logic|{it["item"]}|datalog|{by}', datalog))
        return cells

    def shape_cells(self, apps: list, reps: int = 2, styles=SHAPE_STYLES) -> list:
        """Shape cells: each solid in each description style, `reps` times per applicator."""
        from symblic.adapters import geometry as G
        cells = []
        for it in shape_items(styles):
            target = G._value(shape_target(it['object']))
            target_json = B_plain(target)
            source = shape_source(it['object'], it['style'])
            for by in apps:
                for r in range(reps):
                    def fn(it=it, by=by, target_json=target_json, source=source):
                        rep = self.symblic(source, by, {'description': it['question'], 'target': target_json})
                        s_out = next((o['value'] for o in rep.get('outputs') or [] if o.get('kind') == 'show'), None)
                        form = next((b['value'] for b in rep['bindings'] if b['name'] == 'form'), None)
                        solid = next((b for b in rep['bindings'] if b['name'] == 'solid'), None)
                        levels = {k: bool((s_out or {}).get(k)) for k in SAMENESS}
                        retries = sum(1 for t in rep.get('trace') or [] if t.get('status') == 'retry')
                        return {**_base(it, 'shape', by), 'object': it['object'], 'style': it['style'],
                                'ok': solid is not None, 'accepted': rep.get('status') == 'done',
                                'retries': retries, 'calls': rep.get('calls'), 'levels': levels, 'form': form,
                                'hash': solid and solid['hash'], 'value': solid and solid['value'],
                                'correct': levels['same_placement'],
                                'error': (rep.get('error') or {}).get('message', ''), 'ms': rep['ms']}
                    cells.append((f'shape|{it["item"]}|r{r}|{by}', fn))
        return cells

    def tighten_cells(self, panel: list, heldout: list, clarifier: str, rounds: int = 2) -> list:
        """probe on `panel` -> clarify contested asks with `clarifier` -> probe again; then the original and the
        final statement on `heldout`, applicators that took no part in tightening."""
        from symblic.authoring import tighten as T
        cells = []
        for it in tighten_items():
            def fn(it=it):
                t0 = time.time()
                src = tighten_source(it['type'], it['question'])
                res = T.tighten(src, None, panel, self.apps, clarifier=clarifier, rounds=rounds)

                def held(source):
                    pr = T.probe(source, None, heldout, self.apps)
                    a = pr['asks'][0] if pr['asks'] else {}
                    return {'agreement_all': a.get('agreement_all'), 'agreement_valid': a.get('agreement_valid'),
                            'coverage': a.get('coverage'), 'distinct': a.get('distinct'),
                            'diagnosis': a.get('diagnosis'), 'missing': a.get('missing') or [],
                            'answers': [{k: x.get(k) for k in ('app', 'ok', 'value', 'hash', 'error')}
                                        for x in a.get('answers') or []]}
                before = held(src)
                candidate = res.get('candidate_program', res['program'])
                after = held(candidate) if res['changed'] else before
                rew = [{k: r.get(k) for k in ('round', 'before', 'instruction', 'assumptions', 'leaks_answer', 'ok',
                                              'error')} for r in res['rewrites']]
                return {**_base(it, 'tighten', '+'.join(panel)), 'kind': it['kind'], 'ok': True,
                        'panel': panel, 'heldout': heldout, 'clarifier': clarifier, 'changed': res['changed'],
                        'final': candidate, 'adopted_program': res['program'], 'fidelity': res.get('fidelity'),
                        'adoption': res.get('adoption'), 'candidate_sha256': res.get('candidate_sha256'),
                        'history': res['history'], 'rewrites': rew,
                        'heldout_before': before, 'heldout_after': after, 'correct': None, 'error': '',
                        'ms': int((time.time() - t0) * 1000)}
            cells.append((f'tighten|{it["item"]}|tighten|{len(panel)}', fn))
        return cells

    def flower_cells(self, apps: list) -> list:
        """Flower cells: extract a FlowerSpec from each essay; the kernel draws it and fingerprints the drawing."""
        cells = []
        for it in flower_items():
            for by in apps:
                def fn(it=it, by=by):
                    src = (f'given essay: Text.\ndefine FlowerSpec as {FLOWER_TYPE}.\n'
                           'ask spec: FlowerSpec "Read the essay and give the flower\'s exact specification. Petals '
                           'means petals per ring." from essay with effort=medium\n'
                           'let drawing = flower(spec, rotation=0).\nshow hash(drawing).\n')
                    rep = self.symblic(src, by, {'essay': it['question']})
                    b = next((x for x in rep['bindings'] if x['name'] == 'spec'), None)
                    out = (rep.get('outputs') or [{}])[0].get('value') if rep.get('outputs') else None
                    truth_hash = S.fingerprint(S.Svg(_flower(it['truth'])))
                    return {**_base(it, 'symblic', by), 'ok': b is not None, 'value': b and b['value'],
                            'hash': out, 'correct': out == truth_hash if out else False,
                            'fields': _fields_right(b and b['value'], it['truth']),
                            'error': (rep.get('error') or {}).get('message', ''), 'ms': rep['ms']}
                cells.append((f'flower|{it["item"]}|symblic|{by}', fn))
        return cells

    def run_cells(self, cells: list, workers: int = 8, per_app: int = 2) -> None:
        """Run every unfinished cell on `workers` threads, at most `per_app` at a time per applicator."""
        todo = [(c, f) for c, f in cells if c not in self.done]
        self.log(f'{len(cells)} cells, {len(todo)} to run')
        # interleave applicators so one slow engine does not hold every worker
        by_app = defaultdict(list)
        for c, f in todo:
            by_app[c.split('|')[3]].append((c, f))
        order = []
        while any(by_app.values()):
            for k in sorted(by_app):
                if by_app[k]:
                    order.append(by_app[k].pop(0))
        # one semaphore per applicator, so one slow engine cannot hold every worker
        limits = {c.split('|')[3]: threading.Semaphore(max(1, per_app)) for c, _f in todo}

        def go(cf):
            c, f = cf
            app_key = c.split('|')[3]
            with limits[app_key]:
                return self.cell(c, f)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for fut in as_completed([pool.submit(go, cf) for cf in order]):
                fut.result()


PAL_SOURCE = ('given problem: Text.\n'
              'ask formula: Text "Write ONE arithmetic expression whose value answers the problem. Use only numbers, '
              '+ - * / and parentheses (use // for whole-number division and mod for a remainder). Do not compute it." '
              'from problem with effort=medium, votes={votes}, key=eval(it)\n'
              'let answer = eval(formula).\n')
LOGIC_SOURCE = ('given story: Text.\n'
                'define Link as Record {parent: Text, child: Text}.\n'
                'ask links: List of Link "List every parent-child relation the story states. Use first names exactly '
                'as written." from story with effort=medium\n'
                'for l in links do\n  fact parent(lower(l.parent), lower(l.child)).\nend.\n')


def B_plain(v):
    """A kernel value as plain JSON that from_json reads back to the same exact value."""
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return v
    if S.is_num(v):
        return S.num_text(v) if S.norm_num(v) != int(v) else int(v)
    if isinstance(v, (tuple, list)):
        return [B_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: B_plain(x) for k, x in v.items()}
    return str(v)


def _type(text: str) -> dict:
    p = S.Parser(S.tokenize(text), 1)
    return p.type_expr()


def _base(it: dict, condition: str, by) -> dict:
    return {'suite': it['suite'], 'item': it['item'], 'condition': condition, 'by': by if isinstance(by, str) else
            '+'.join(by), 'truth': it['truth'], 'versions': versions()}


def _plain_num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return S.norm_num(Fraction(str(v)))
    if isinstance(v, str):
        try:
            return S._coerce_num(v.split(' ')[0], 'v')
        except S.SymblicError:
            return None
    return None


def _pal_row(it, condition, by, rep) -> dict:
    b = next((x for x in rep['bindings'] if x['name'] == 'answer'), None)
    f = next((x for x in rep['bindings'] if x['name'] == 'formula'), None)
    v = _plain_num(b['value']) if b else None
    return {**_base(it, condition, by), 'ok': b is not None, 'value': S.to_plain(v), 'formula': f and f['value'],
            'agreement': (f or {}).get('meta', {}).get('agreement'), 'correct': v == it['truth'] if v is not None else False,
            'error': (rep.get('error') or {}).get('message', ''), 'ms': rep['ms']}


def _prose_correct(text: str, truth) -> bool:
    t = _norm_prose(text)
    if isinstance(truth, bool):
        return t.startswith('yes') or t.startswith('true') if truth else t.startswith('no') or t.startswith('false')
    if isinstance(truth, (int, str)) and not isinstance(truth, bool):
        return bool(re.search(rf'(^|\s){re.escape(str(truth).lower())}(\s|$)', t))
    if isinstance(truth, list):
        pos = [t.find(str(x).lower()) for x in truth]
        return all(p >= 0 for p in pos) and pos == sorted(pos)
    if isinstance(truth, dict):
        return all(str(v).lower() in t for v in truth.values())
    return False


def _flower(spec: dict) -> str:
    from symblic.adapters import render as R
    return R.flower(dict(spec), rotation=0)


def _fields_right(value, truth) -> int | None:
    if not isinstance(value, dict):
        return None
    return sum(1 for k, v in truth.items() if value.get(k) == v)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.96):
    """Wilson score interval (low, high) for k successes in n trials."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - r) / d), min(1.0, (c + r) / d))


def pct(k, n) -> str:
    """A rate with its counts. No interval: the answers in a cell share questions and applicators, so they are
    not independent draws and a binomial interval would be too narrow (research report §8.6); intervals come
    from `cluster_boot`, which resamples whole questions."""
    if not n:
        return '—'
    return f'{100 * k / n:.0f}% ({k}/{n})'


def kalpha(units: list) -> float | None:
    """Krippendorff's alpha, nominal, missing answers allowed: `units` is a list of lists of category labels
    (one list per question, one label per valid answer). Questions with fewer than 2 answers are skipped."""
    from collections import Counter
    o = Counter()
    for u in units:
        m = len(u)
        if m < 2:
            continue
        cnt = Counter(u)
        for c in cnt:
            for k in cnt:
                pairs = cnt[c] * (cnt[k] - (1 if c == k else 0))
                if pairs:
                    o[(c, k)] += pairs / (m - 1)
    n_c = Counter()
    for (c, _k), v in o.items():
        n_c[c] += v
    n = sum(n_c.values())
    if n <= 1:
        return None
    d_o = sum(v for (c, k), v in o.items() if c != k)
    d_e = sum(n_c[c] * n_c[k] for c in n_c for k in n_c if c != k) / (n - 1)
    if d_e == 0:
        return 1.0 if d_o == 0 else None
    return 1 - d_o / d_e


def cluster_boot(units: list, stat, draws: int = 2000, seed: int = 7):
    """(estimate, lo, hi): a percentile 95% interval from resampling whole questions with replacement (each
    keeps all of its answers), seeded, so the report is reproducible."""
    import random
    est = stat(units)
    if est is None or len(units) < 2:
        return est, None, None
    rnd = random.Random(seed)
    vals = []
    for _ in range(draws):
        v = stat([units[rnd.randrange(len(units))] for _ in units])
        if v is not None:
            vals.append(v)
    if not vals:
        return est, None, None
    vals.sort()
    return est, vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]


def pair_identity(units: list):
    """Share of answer pairs within each question that are identical (None without pairs)."""
    ok = n = 0
    for u in units:
        for i in range(len(u)):
            for j in range(i + 1, len(u)):
                n += 1
                ok += u[i] == u[j]
    return ok / n if n else None


def boot_text(units: list, stat, scale: float = 100.0, digits: int = 0, suffix: str = '%') -> str:
    """'estimate (95% CI lo-hi, n questions)' from cluster_boot, formatted for the report."""
    est, lo, hi = cluster_boot(units, stat)
    if est is None:
        return '—'
    f = (lambda x: f'{x * scale:.{digits}f}{suffix}')
    return f'{f(est)} (95% CI {f(lo)}–{f(hi)}, {len(units)} questions)' if lo is not None else f(est)


def short_by(by: str) -> str:
    """'ollama:qwen3:4b-instruct@node-a+…' (several voting applicators) -> 'council 5× qwen3:4b-instruct'."""
    parts = str(by).split('+')
    if len(parts) > 1:
        models = {re.sub(r'^ollama:|@.*$', '', p) for p in parts}
        return f'council {len(parts)}× ' + (models.pop() if len(models) == 1 else 'mixed')
    return str(by)


def report(rows: list) -> str:
    """The Markdown report of every recorded cell, one section per suite, with its stated limits."""
    # arithmetic items are '<template>-NN' (per-template streams); rows from an older numbering are left out
    rows = [r for r in rows if r.get('suite') != 'arith' or re.fullmatch(r'[a-z]+-\d{2}', str(r.get('item')))]
    rows = [{**r, 'by': short_by(r.get('by', ''))} for r in rows]
    out = ['# Symblic benchmark results', '', f'Generated {time.strftime("%Y-%m-%d %H:%M")} from {len(rows)} cells.', '',
           'Historical suite/scorer semantics: these records retain their original heuristic grading and observed-cell '
           'denominators. Number/entity extraction and prose normalization do not establish exact correctness. '
           'They are not matched model/information/budget/feedback/validator comparisons. Use the separate matched '
           'evaluation for new controlled evidence; old records are not regraded or rewritten here.', '']
    by_suite = defaultdict(list)
    for r in rows:
        by_suite[r.get('suite')].append(r)
    if by_suite.get('identity'):
        out += ['## Identity: do different agents give the same answer?', '',
                'Same question, two forms: a plain prose prompt (answer text compared after lower-casing and removing '
                'punctuation) and a Symblic typed ask (canonical fingerprint compared). "Unanimous" counts questions '
                'where every applicator that answered gave the identical result.', '']
        rows_i = by_suite['identity']
        for cond in ('prose', 'symblic'):
            sub = [r for r in rows_i if r.get('condition') == cond]
            items = sorted({r['item'] for r in sub})
            unan = pair_ok = pair_n = 0
            for it in items:
                hs = [r.get('hash') for r in sub if r['item'] == it and r.get('ok') and r.get('hash')]
                if hs and len(set(hs)) == 1 and len(hs) >= 2:
                    unan += 1
                for i in range(len(hs)):
                    for j in range(i + 1, len(hs)):
                        pair_n += 1
                        pair_ok += hs[i] == hs[j]
            correct = sum(1 for r in sub if r.get('correct'))
            answered = sum(1 for r in sub if r.get('ok'))
            units = [[r.get('hash') for r in sub if r['item'] == it and r.get('ok') and r.get('hash')] for it in items]
            out.append(f'- **{cond}**: unanimous on {unan}/{len(items)} questions; pairwise identical '
                       f'{pct(pair_ok, pair_n)}, resampling questions {boot_text(units, pair_identity)}; '
                       f'Krippendorff α {boot_text(units, kalpha, 1, 2, "")}; correct {pct(correct, len(sub))}; valid answers '
                       f'{answered}/{len(sub)}.')
        qs = sorted({r['item'] for r in rows_i})
        paired = [([r.get('hash') for r in rows_i if r['item'] == q and r['condition'] == 'prose' and r.get('ok')
                    and r.get('hash')],
                   [r.get('hash') for r in rows_i if r['item'] == q and r['condition'] == 'symblic' and r.get('ok')
                    and r.get('hash')]) for q in qs]

        def diff(units, f=pair_identity):
            a, b = f([u[1] for u in units]), f([u[0] for u in units])
            return None if a is None or b is None else a - b
        est, lo, hi = cluster_boot(paired, diff)
        est_a, lo_a, hi_a = cluster_boot(paired, lambda u: diff(u, kalpha))
        if est is not None and lo is not None:
            out.append(f'- **typed − prose, same questions resampled together**: pairwise identity '
                       f'{100 * est:+.0f} points (95% CI {100 * lo:+.0f} to {100 * hi:+.0f}); α {est_a:+.2f} '
                       f'(95% CI {lo_a:+.2f} to {hi_a:+.2f}); {len(qs)} questions, so the intervals are wide.')
        out += ['', '| applicator | prose correct | Symblic correct | Symblic valid |', '|---|---|---|---|']
        for by in sorted({r['by'] for r in rows_i}):
            p = [r for r in rows_i if r['by'] == by and r['condition'] == 'prose']
            s = [r for r in rows_i if r['by'] == by and r['condition'] == 'symblic']
            out.append(f'| {by} | {sum(1 for r in p if r.get("correct"))}/{len(p)} | '
                       f'{sum(1 for r in s if r.get("correct"))}/{len(s)} | {sum(1 for r in s if r.get("ok"))}/{len(s)} |')
        out.append('')
    if by_suite.get('shape'):
        from symblic.adapters import geometry as G
        rs = [rejudge_shape(r) for r in by_suite['shape']]
        old = sum(1 for r in by_suite['shape'] if (r.get('versions') or {}).get('geometry') != G.VERSION)
        out += ['## Shapes: does a more formal description make every agent build the same solid?', '',
                f'Every answer is judged from its stored record by geometry checker v{G.VERSION}'
                + (f' ({old} rows were recorded under an earlier checker whose "valid" meant only "parses"; their '
                   'levels here are recomputed)' if old else '') + '. Levels, loosest to strictest: parses; valid '
                'solid (closed, consistently oriented, flat convex faces, every vertex used, positive volume, '
                'convex and wrapping its hull once); similar (an exact similarity maps vertices and faces onto the '
                'reference); congruent (the same at scale 1); same placement (the same point set and faces after '
                'the kernel normalises numbering and face order); identical (the raw answer equals the reference).',
                '', '| style | answers | parses | valid solid | similar | congruent | same placement | identical '
                '| distinct objects |', '|---|---|---|---|---|---|---|---|---|']
        for style in SHAPE_STYLES:
            sub = [r for r in rs if r.get('style') == style]
            if not sub:
                continue
            cnt = lambda k: sum(1 for r in sub if (r.get('levels') or {}).get(k))
            per_obj = []
            for obj in SHAPES:
                forms = [r.get('form') for r in sub if r.get('object') == obj and r.get('form')]
                if forms:
                    per_obj.append(f'{obj} {len(set(forms))}')
            out.append(f'| {style} | {len(sub)} | ' + ' | '.join(pct(cnt(k), len(sub)) for k in SAMENESS) +
                       f' | {", ".join(per_obj)} |')
        out += ['', '| applicator | ' + ' | '.join(f'{st} same placement' for st in SHAPE_STYLES)
                + ' |', '|---|---|---|---|---|']
        for by in sorted({r['by'] for r in rs}):
            cells = []
            for style in SHAPE_STYLES:
                sub = [r for r in rs if r['by'] == by and r.get('style') == style]
                cells.append(f'{sum(1 for r in sub if (r.get("levels") or {}).get("same_placement"))}/{len(sub)}')
            out.append(f'| {by} | ' + ' | '.join(cells) + ' |')
        checked = [r for r in rs if r.get('style') == 'symblic']
        if checked:
            acc = [r for r in checked if r.get('accepted')]
            per = {}
            for r in acc:
                per.setdefault(r['object'], set()).add(r.get('form'))
            out += ['', f'Checked style (technical text + kernel end-state checks, re-asked with the failing check, '
                        f'up to 3 retries): {len(acc)}/{len(checked)} answers accepted by the kernel; distinct '
                        'canonical solids among accepted answers: ' +
                        (', '.join(f'{o} {len(v)}' for o, v in sorted(per.items())) or 'none') +
                        '. By construction an accepted answer is the one solid the checks admit; what varies is '
                        'coverage (who reaches acceptance).']
            for by in sorted({r['by'] for r in checked}):
                sub = [r for r in checked if r['by'] == by]
                out.append(f'- {by}: {sum(1 for r in sub if r.get("accepted"))}/{len(sub)} accepted')
        reps = defaultdict(list)
        for r in rs:
            if r.get('hash'):
                reps[(r['by'], r['item'])].append(r['hash'])
        pairs = [v for v in reps.values() if len(v) >= 2]
        if pairs:
            same = sum(1 for v in pairs if len(set(v)) == 1)
            out += ['', f'Self-consistency: the same applicator gave the identical answer twice in {pct(same, len(pairs))} '
                        'of repeated cells.']
        out.append('')
    if by_suite.get('tighten'):
        rs = by_suite['tighten']
        out += ['## Tightening: does a statement rewritten from measured disagreement agree for NEW readers?', '',
                'Each statement was asked of the probe panel (fresh context, temperature 0). Where capable probes '
                'disagreed, a clarifier rewrote it with explicit assumptions (told not to choose the answer; a '
                'rewrite naming the modal answer is flagged and discarded), and the probe panel answered again. '
                'The held-out panel answered the original and the final statement without taking part. Agreement '
                'counts every answer, an invalid one as disagreement. No item here has a ground truth: this '
                'measures agreement, not correctness.', '']
        panel = rs[0].get('panel') or []
        held = rs[0].get('heldout') or []
        out += [f'Probe panel: {", ".join(panel)}. Held-out: {", ".join(held)}. Clarifier: {rs[0].get("clarifier")}.', '',
                '| item | kind | probe diagnosis | rewritten | held-out agreement before → after | held-out distinct '
                'before → after |', '|---|---|---|---|---|---|']
        for r in sorted(rs, key=lambda r: (r.get('kind') != 'ambiguous', r['item'])):
            h0 = (r.get('history') or [{}])[0]
            diag = ((h0.get('asks') or [{}])[0]).get('diagnosis', '?')
            b, a = r.get('heldout_before') or {}, r.get('heldout_after') or {}
            leak = any(x.get('leaks_answer') for x in r.get('rewrites') or [])
            out.append(f'| {r["item"]} | {r.get("kind")} | {diag} | {"yes" if r.get("changed") else "no"}'
                       f'{" (a leaking rewrite was refused)" if leak else ""} | '
                       f'{b.get("agreement_all", 0):.2f} → {a.get("agreement_all", 0):.2f} | '
                       f'{b.get("distinct", "?")} → {a.get("distinct", "?")} |')
        for kind in ('ambiguous', 'control'):
            sub = [r for r in rs if r.get('kind') == kind]
            if not sub:
                continue
            mb = sum((r.get('heldout_before') or {}).get('agreement_all') or 0 for r in sub) / len(sub)
            ma = sum((r.get('heldout_after') or {}).get('agreement_all') or 0 for r in sub) / len(sub)
            ub = sum(1 for r in sub if (r.get('heldout_before') or {}).get('agreement_all') == 1)
            ua = sum(1 for r in sub if (r.get('heldout_after') or {}).get('agreement_all') == 1)
            out.append(f'\n{kind}: {len(sub)} statements, {sum(1 for r in sub if r.get("changed"))} rewritten; held-out '
                       f'mean agreement {mb:.2f} → {ma:.2f}; held-out unanimous {ub} → {ua}.')
        out.append('')
    for suite, title in (('arith', 'Arithmetic word problems (generated, multi-step)'),
                         ('logic', 'Family logic (generated, multi-hop)'),
                         ('flower', 'Flowers from essays')):
        rs = by_suite.get(suite)
        if not rs:
            continue
        out += [f'## {title}', '', '| condition | applicator | correct | median seconds |', '|---|---|---|---|']
        keys = sorted({(r['condition'], r['by']) for r in rs})
        for cond, by in keys:
            sub = [r for r in rs if r['condition'] == cond and r['by'] == by]
            k = sum(1 for r in sub if r.get('correct'))
            secs = sorted(r.get('ms', 0) / 1000 for r in sub)
            med = secs[len(secs) // 2] if secs else 0
            out.append(f'| {cond} | {by} | {pct(k, len(sub))} | {med:.0f} |')
        if suite in ('arith', 'logic') and len(keys) > 1:
            sets = [{r['item'] for r in rs if r['condition'] == c and r['by'] == b} for c, b in keys]
            matched = set.intersection(*sets) if sets else set()
            if matched and any(len(x) != len(matched) for x in sets):
                out += ['', f'On the {len(matched)} items every condition finished (like-for-like):', '',
                        '| condition | applicator | correct |', '|---|---|---|']
                for cond, by in keys:
                    sub = [r for r in rs if r['condition'] == cond and r['by'] == by and r['item'] in matched]
                    out.append(f'| {cond} | {by} | {pct(sum(1 for r in sub if r.get("correct")), len(sub))} |')
        if suite == 'arith':
            noop = [r for r in rs if r.get('noop')]
            if noop:
                out += ['', 'With an irrelevant sentence inserted (GSM-NoOp style):', '']
                for cond, by in keys:
                    sub = [r for r in rs if r['condition'] == cond and r['by'] == by and r.get('noop')]
                    out.append(f'- {cond} / {by}: {pct(sum(1 for r in sub if r.get("correct")), len(sub))}')
        if suite == 'flower':
            out += ['', 'Drawing agreement per essay (applicators whose drawing fingerprint matches the modal one):', '']
            for it in sorted({r['item'] for r in rs}):
                hs = [r.get('hash') for r in rs if r['item'] == it and r.get('hash')]
                if hs:
                    modal = max(set(hs), key=hs.count)
                    out.append(f'- {it}: {hs.count(modal)}/{len(hs)} identical; {sum(1 for r in rs if r["item"] == it and r.get("correct"))} exactly right')
        out.append('')
    return '\n'.join(out)


# Default applicator lists: small local Ollama models (pull them first, or pass your own lists).
SMALL_LOCAL = 'ollama:qwen3:4b-instruct,ollama:llama3.2:1b'
IDENTITY_APPS = 'ollama:qwen3:4b-instruct,ollama:llama3.2:1b,ollama:gemma3:1b'
SHAPE_APPS = 'ollama:qwen3:4b-instruct,ollama:llama3.2:1b,ollama:gemma3:4b,ollama:phi4-mini,ollama:granite3.3:2b'


def parser() -> argparse.ArgumentParser:
    """The command-line options (see the module docstring for the suites)."""
    ap = argparse.ArgumentParser(prog='python3 -m symblic.bench.bench',
                                 description='Measure Symblic against ground truth with real applicators.')
    ap.add_argument('--out', required=True, help='results folder (created; results.jsonl, report.md, log.txt)')
    ap.add_argument('--suite', default='identity,arith,logic,flower',
                    help='comma list of identity, arith, logic, flower, shape, tighten; or ambiguity / matched alone')
    ap.add_argument('--quick', action='store_true', help='a few items per suite (smoke)')
    ap.add_argument('--report-only', action='store_true', help='rewrite report.md from results already in --out')
    ap.add_argument('--resume', action='store_true', help='resume an existing ambiguity assignment without re-asking cells')
    ap.add_argument('--dry-run', action='store_true', help='ambiguity/matched only: freeze assignments, make no model calls')
    ap.add_argument('--matched-manifest', default='', help='frozen direct/typed evaluation manifest; required for a new matched experiment')
    ap.add_argument('--ambiguity-data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'data', 'ambiguity-v1.json'))
    ap.add_argument('--ambiguity-split', choices=('dev', 'heldout'), default='dev')
    ap.add_argument('--ambiguity-apps', default='', help='required explicit applicators for the ambiguity suite')
    ap.add_argument('--ambiguity-conditions', default='direct,typed,clarify,oracle_direct')
    ap.add_argument('--avoid', default='', help='ambiguity: nodes no applicator may name (comma list)')
    ap.add_argument('--workers', type=int, default=8, help='cells run in parallel')
    ap.add_argument('--per-app', type=int, default=2, help='cells run in parallel per applicator')
    ap.add_argument('--shape-apps', default=SHAPE_APPS)
    ap.add_argument('--reps', type=int, default=2, help='repetitions per shape cell (self-consistency)')
    ap.add_argument('--tighten-panel', default=IDENTITY_APPS, help='applicators whose disagreement drives tightening')
    ap.add_argument('--tighten-heldout', default='ollama:granite3.3:2b,ollama:phi4-mini',
                    help='applicators that judge the rewrites and never saw them made (no model in both panels)')
    ap.add_argument('--tighten-clarifier', default='ollama:qwen3:4b-instruct')
    ap.add_argument('--shape-styles', default=','.join(SHAPE_STYLES),
                    help='description styles for the shape suite (symblic = technical text + kernel checks)')
    ap.add_argument('--ultra', action='store_true', help='add the effort=ultra (mixture-of-agents) council condition')
    ap.add_argument('--retry', default='', help='regex: failed cells whose id or error matches are asked again')
    ap.add_argument('--identity-apps', default=IDENTITY_APPS)
    ap.add_argument('--small', default=SMALL_LOCAL, help='models that get every arith/logic condition')
    ap.add_argument('--big', default='', help='models that answer arith/logic directly (e.g. command:claude)')
    ap.add_argument('--council', default='',
                    help='applicators that vote together in the arith council conditions, e.g. '
                         'ollama:qwen3:4b-instruct@node-a,ollama:qwen3:4b-instruct@node-b (empty: no council)')
    ap.add_argument('--arith-per', type=int, default=5)
    ap.add_argument('--logic-n', type=int, default=15)
    return ap


def main(argv=None) -> int:
    """Run the selected suites (or only rebuild the report) and print report.md."""
    ap = parser()
    a = ap.parse_args(argv)
    suites = [s.strip() for s in a.suite.split(',') if s.strip()]
    if 'matched' in suites:
        if suites != ['matched']:
            ap.error('matched uses frozen assignments and must run as the only suite')
        from symblic.bench import matched as matched
        try:
            return matched.main(a)
        except (ValueError, OSError, S.SymblicError) as exc:
            ap.error(str(exc))
    if 'ambiguity' in suites:
        if suites != ['ambiguity']:
            ap.error('ambiguity uses its own fixed assignment and must run as the only suite')
        from symblic.bench import ambiguity as ambiguity
        try:
            return ambiguity.main(a)
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    if a.dry_run:
        ap.error('--dry-run is supported only for --suite ambiguity or matched')
    out = os.path.abspath(a.out)

    def log(text):
        line = f'{time.strftime("%H:%M:%S")} {text}'
        print(line, flush=True)
        with open(os.path.join(out, 'log.txt'), 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    os.makedirs(out, exist_ok=True)
    if a.report_only:
        rows = list(Bench(out, apps=object(), log=log).done.values())
    else:
        b = Bench(out, log=log, retry=a.retry)
        from symblic.providers import applicators as providers
        providers.install_sigterm()        # a stopped bench cancels its in-flight calls
        suites = a.suite.split(',')
        split = lambda s: [x for x in s.split(',') if x]
        cells = []
        if 'identity' in suites:
            cells += b.identity_cells(split(a.identity_apps))
        if 'tighten' in suites:
            cells += b.tighten_cells(split(a.tighten_panel), split(a.tighten_heldout), a.tighten_clarifier)
        if 'shape' in suites:
            cells += b.shape_cells(split(a.shape_apps), a.reps, tuple(split(a.shape_styles)))
        if 'flower' in suites:
            cells += b.flower_cells(split(a.identity_apps))
        if 'logic' in suites:
            cells += b.logic_cells(split(a.small) + split(a.big)[:1], 3 if a.quick else a.logic_n)
        if 'arith' in suites:
            cells += b.arith_cells(split(a.small), split(a.big), 1 if a.quick else a.arith_per, split(a.council),
                                   ultra=a.ultra)
        if a.quick:
            cells = cells[:40]
        b.run_cells(cells, a.workers, a.per_app)
        rows = list(b.done.values())
    text = report(rows)
    with open(os.path.join(out, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(text)
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
