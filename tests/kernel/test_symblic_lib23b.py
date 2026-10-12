"""Symblic 2.3, round 2, lane M: stats.binomial_at_least / binomial_at_most, the order module (order effects
and the QQ gap of two yes/no questions) and the question-order example. Kernel and fake applicators only (no
model, no network, no dashboard)."""

import hashlib
import math
import os
import random
import re
import sys
import threading
import unittest
from fractions import Fraction
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import execution_pins as X  # noqa: E402
from symblic.lang import abstraction as L  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE = os.path.join(ROOT, 'examples', '14-question-order.sym')
ORDER_ITEMS = ['Counts', 'total', 'share_a_yes', 'share_b_yes', 'share_different', 'order_effect_a', 'order_effect_b',
               'qq_gap']
ASK_NAMES = ('ab_a', 'ab_b', 'ba_b', 'ba_a')


class FakeApps:
    """answer(prompt, req) -> a JSON-able answer object. Records every request."""

    def __init__(self, answer):
        self.answer = answer
        self.reqs = []
        self.lock = threading.Lock()

    def call(self, req):
        with self.lock:
            self.reqs.append(req)
        return {'ok': True, 'json': self.answer(req['prompt'], req), 'ms': 1}


def run(src, answer=None, inputs=None, **opts):
    apps = FakeApps(answer) if answer else None
    options = {'by': 'fake:a'}
    options.update(opts)
    r = SR.Run(src, inputs, apps, options)
    return r, r.execute(), apps


def value(r, name):
    return r.kernel.env.lookup(name).value


def counts_text(c):
    return '{' + ', '.join(f'{k}: {c[k]}' for k in ('yy', 'yn', 'ny', 'nn')) + '}'


# Independent references (Python Fractions, not the kernel)

def tail_at_least(k, n, p):
    return sum((math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(max(k, 0), n + 1)), Fraction(0))


def tail_at_most(k, n, p):
    return sum((math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, min(k, n) + 1)), Fraction(0))


def shares(c):
    t = sum(c.values())
    return Fraction(c['yy'] + c['yn'], t), Fraction(c['yy'] + c['ny'], t), Fraction(c['yn'] + c['ny'], t)


def effects(ab, ba):
    (a1, b1, d1), (a2, b2, d2) = shares(ab), shares(ba)
    return a1 - a2, b1 - b2, d1 - d2


def projector(v):
    s = sum(x * x for x in v)
    return [[Fraction(a * b, s) for b in v] for a in v]


def complement(p):
    return [[(1 if i == j else 0) - p[i][j] for j in range(len(p))] for i in range(len(p))]


def apply(p, x):
    return [sum(p[i][j] * x[j] for j in range(len(x))) for i in range(len(p))]


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def norm2(x):
    return sum(c * c for c in x)


def model_counts(psi, pa, pb):
    """The projector model's exact probabilities of each pair of answers in each order (Born rule, the state
    projected by the first answer, then by the second), scaled to integer counts with a common denominator."""
    qa, qb = complement(pa), complement(pb)
    first_then = lambda m1, m2: norm2(apply(m2, apply(m1, psi))) / norm2(psi)   # noqa: E731
    ab = {'yy': first_then(pa, pb), 'yn': first_then(pa, qb), 'ny': first_then(qa, pb), 'nn': first_then(qa, qb)}
    ba = {'yy': first_then(pb, pa), 'yn': first_then(qb, pa), 'ny': first_then(pb, qa), 'nn': first_then(qb, qa)}
    assert sum(ab.values()) == 1 and sum(ba.values()) == 1
    scale = math.lcm(*(x.denominator for x in list(ab.values()) + list(ba.values())))
    return ({k: int(v * scale) for k, v in ab.items()}, {k: int(v * scale) for k, v in ba.items()})


def reviewed(libraries=()):
    names = sorted(X.REQUIRED_FILES) + ['symblic/lang/library/' + n + '.sym' for n in libraries]
    return {name: hashlib.sha256((X.BASE / name).read_bytes()).hexdigest() for name in names}


class Base(unittest.TestCase):
    def setUp(self):
        L.register()             # another suite may have cleared symblic.EXTENSIONS


class Binomial(Base):
    def test_stats_kernel_tests_pass_with_the_binomial_test(self):
        source = L.library_source('stats')
        self.assertTrue(S.check(source)['ok'])
        res = L.run_tests(source)
        self.assertTrue(res['ok'], res)
        self.assertEqual((res['passed'], res['failed'], res['asks']), (4, 0, 0))
        only = L.run_tests(source, only=['binomial tails are exact'])
        self.assertEqual((only['ok'], only['passed']), (True, 1))

    def test_the_functions_are_documented_with_their_purpose(self):
        items = {i['name']: i for i in L.describe_module('stats')['items']}
        self.assertEqual(items['binomial_at_least']['signature'],
                         'function binomial_at_least(k: Int, n: Int in 0..100000, p: Number in 0..1) -> Number')
        self.assertIn('binomial_at_most', items)
        doc = items['binomial_at_least']['doc']
        for phrase in ('18 of 18', 'weak evidence', 'about 0.054', 'not excluded at the 5% level'):
            self.assertIn(phrase, doc)

    def test_hand_checked_values_are_exact(self):
        r, rep, _ = run('import stats.\n'
                        'let a = binomial_at_least(2, 2, 1/2).\nlet b = binomial_at_least(0, 5, 1/3).\n'
                        'let c = binomial_at_most(0, 3, 1/2).\nlet d = binomial_at_least(18, 18, 85/100).\n'
                        'let e = binomial_at_least(18, 18, 0.85).\nlet f = binomial_at_least(2, 3, 1/2).\n')
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(value(r, 'a'), Fraction(1, 4))
        self.assertEqual(value(r, 'b'), 1)
        self.assertIs(type(value(r, 'b')), int)                         # normalised the way the kernel does
        self.assertEqual(value(r, 'c'), Fraction(1, 8))
        self.assertEqual(value(r, 'd'), Fraction(17, 20) ** 18)
        self.assertEqual(value(r, 'e'), value(r, 'd'))                  # 0.85 is the exact decimal 17/20
        self.assertTrue(Fraction(536, 10000) < value(r, 'd') < Fraction(537, 10000))
        self.assertEqual(value(r, 'f'), Fraction(1, 2))

    def test_agrees_with_an_independent_computation_on_random_instances(self):
        rnd = random.Random(2303)
        cases = []
        for _ in range(40):
            n = rnd.randint(0, 24)
            k = rnd.randint(-2, n + 2)
            den = rnd.randint(1, 12)
            cases.append((k, n, Fraction(rnd.randint(0, den), den)))
        cases += [(0, 0, Fraction(0)), (1, 7, Fraction(1)), (7, 7, Fraction(0)), (3, 9, Fraction(1, 2))]
        src = 'import stats.\n' + ''.join(
            f'let x{i} = binomial_at_least({k}, {n}, {p.numerator}/{p.denominator}).\n'
            f'let y{i} = binomial_at_most({k}, {n}, {p.numerator}/{p.denominator}).\n'
            for i, (k, n, p) in enumerate(cases))
        r, rep, _ = run(src)
        self.assertEqual(rep['status'], 'done', rep['error'])
        for i, (k, n, p) in enumerate(cases):
            with self.subTest(k=k, n=n, p=p):
                self.assertEqual(value(r, f'x{i}'), tail_at_least(k, n, p))
                self.assertEqual(value(r, f'y{i}'), tail_at_most(k, n, p))
                self.assertEqual(value(r, f'x{i}') + tail_at_most(k - 1, n, p), 1)
                S.canon(value(r, f'x{i}'))
                self.assertEqual(S.fingerprint(value(r, f'x{i}')), S.fingerprint(S.norm_num(tail_at_least(k, n, p))))

    def test_refusals(self):
        for expr, kind, words in (('binomial_at_least(1, 3, 6/5)', 'type', 'between 0 and 1'),
                                  ('binomial_at_most(1, 3, -1/10)', 'type', 'between 0 and 1'),
                                  ('binomial_at_least(1, -1, 1/2)', 'type', 'between 0 and 100000'),
                                  ('binomial_at_most(1, 100001, 1/2)', 'type', 'between 0 and 100000'),
                                  ('binomial_at_least(1, 3, true)', 'type', 'Bool'),
                                  ('binomial_at_least(true, 3, 1/2)', 'type', 'Bool'),
                                  ('binomial_at_least(1/2, 3, 1/2)', 'type', 'should be Int'),
                                  ('binomial_at_least(1, "3", 1/2)', 'type', 'should be Int'),
                                  ('binomial_at_least(1, 3)', 'type', 'needs p')):
            with self.subTest(expr=expr):
                _, rep, _ = run(f'import stats.\nlet x = {expr}.\n')
                self.assertEqual(rep['status'], 'failed')
                self.assertEqual(rep['error']['kind'], kind, rep['error'])
                self.assertIn(words, rep['error']['message'])

    def test_limits_and_budget(self):
        _, rep, _ = run('import stats.\nlet x = binomial_at_least(0, 20000, 1/2).\n')
        self.assertEqual(rep['status'], 'failed')                       # refused, never rounded
        self.assertIn('digits', rep['error']['message'])
        _, rep, _ = run('import stats.\nlet x = binomial_at_least(10, 30, 1/3).\n', max_steps=60)
        self.assertEqual(rep['status'], 'failed')
        self.assertIn('step budget', rep['error']['message'])


class OrderModule(Base):
    AB = {'yy': 3, 'yn': 1, 'ny': 2, 'nn': 4}
    BA = {'yy': 2, 'yn': 3, 'ny': 1, 'nn': 4}

    def test_it_checks_is_described_and_its_kernel_tests_pass(self):
        source = L.library_source('order')
        self.assertIsNotNone(source)
        self.assertTrue(S.check(source)['ok'])
        res = L.run_tests(source)
        self.assertTrue(res['ok'], res)
        self.assertEqual((res['passed'], res['failed'], res['asks']), (4, 0, 0))
        self.assertIn('order', {m['name'] for m in L.library()})
        described = L.describe_module('order')
        self.assertEqual([i['name'] for i in described['items']], ORDER_ITEMS)
        items = {i['name']: i for i in described['items']}
        self.assertEqual(items['qq_gap']['signature'], 'function qq_gap(ab: Counts, ba: Counts) -> Number')
        self.assertEqual(items['total']['signature'], 'function total(c: Counts) -> Int')
        self.assertIn('Wang and Busemeyer 2013', items['qq_gap']['doc'])
        self.assertIn('does not show that the model is right', items['qq_gap']['doc'])
        self.assertIn('not an order effect', items['order_effect_a']['doc'])
        self.assertIn('whichever question was asked first', described['intro'])

    def test_import_forms_and_hand_checked_values(self):
        ab, ba = counts_text(self.AB), counts_text(self.BA)
        for src in (f'import order.\nlet ea = order_effect_a({ab}, {ba}).\nlet eb = order.order_effect_b({ab}, {ba}).\n'
                    f'let q = order.qq_gap({ab}, {ba}).\nlet t = total({ab}).\nlet c: Counts = {ab}.\n',
                    f'import order as qo.\nlet ea = qo.order_effect_a({ab}, {ba}).\nlet eb = qo.order_effect_b({ab}, {ba}).\n'
                    f'let q = qo.qq_gap({ab}, {ba}).\nlet t = qo.total({ab}).\nlet c: qo.Counts = {ab}.\n',
                    f'import order_effect_a, order_effect_b, qq_gap, total, Counts from order.\n'
                    f'let ea = order_effect_a({ab}, {ba}).\nlet eb = order_effect_b({ab}, {ba}).\n'
                    f'let q = qq_gap({ab}, {ba}).\nlet t = total({ab}).\nlet c: Counts = {ab}.\n'):
            with self.subTest(src=src.splitlines()[0]):
                # S.check resolves a `let x: T` annotation only against the program's own `define`s (it reports
                # "unknown type Counts", as it does for dates' Date), so the typed let is checked at run time only
                untyped = ''.join(line + '\n' for line in src.splitlines() if not line.startswith('let c:'))
                self.assertTrue(S.check(untyped)['ok'], S.check(untyped)['errors'])
                r, rep, _ = run(src)
                self.assertEqual(rep['status'], 'done', rep['error'])
                self.assertEqual(value(r, 'ea'), Fraction(-1, 10))
                self.assertEqual(value(r, 'eb'), Fraction(1, 5))
                self.assertEqual(value(r, 'q'), Fraction(-1, 10))
                self.assertEqual(value(r, 't'), 10)
                self.assertEqual(value(r, 'c'), self.AB)
                self.assertEqual((value(r, 'ea'), value(r, 'eb'), value(r, 'q')), effects(self.AB, self.BA))

    def test_refusals(self):
        good = counts_text(self.AB)
        for expr, kind, words in (('total({yy: 3, yn: -1, ny: 2, nn: 4})', 'check', 'below 0'),
                                  ('share_a_yes({yy: 0, yn: 0, ny: 0, nn: 0})', 'check', 'empty'),
                                  (f'qq_gap({good}, {{yy: 0, yn: 0, ny: 0, nn: 0}})', 'check', 'empty'),
                                  ('total({yy: 3, yn: 1, ny: 2})', 'type', 'lacks the field nn'),
                                  ('total({yy: 3, yn: 1/2, ny: 2, nn: 4})', 'type', 'should be Int'),
                                  ('total({yy: true, yn: 1, ny: 2, nn: 4})', 'type', 'should be Int but is Bool'),
                                  ('total({yy: "3", yn: 1, ny: 2, nn: 4})', 'type', 'should be Int'),
                                  ('total([3, 1, 2, 4])', 'type', 'should be a Record'),
                                  (f'order_effect_a({good})', 'type', 'needs ba')):
            with self.subTest(expr=expr):
                _, rep, _ = run(f'import order.\nlet x = {expr}.\n')
                self.assertEqual(rep['status'], 'failed')
                self.assertEqual(rep['error']['kind'], kind, rep['error'])
                self.assertIn(words, rep['error']['message'])
        r, rep, _ = run('import order.\nlet t = total({yy: 0, yn: 0, ny: 0, nn: 0}).\n')
        self.assertEqual((rep['status'], value(r, 't')), ('done', 0))  # an empty tally has a total

    def test_projector_models_give_no_qq_gap_on_random_rational_instances(self):
        rnd = random.Random(1983)

        def vector(d):
            while True:
                v = [rnd.randint(-3, 3) for _ in range(d)]
                if any(v):
                    return v
        cases, commuting, moved = [], 0, 0
        while len(cases) < 30:
            d = rnd.choice((2, 3))
            pa, pb = projector(vector(d)), projector(vector(d))
            if d == 3 and rnd.random() < 0.5:
                pa = complement(pa)                                         # a rank-2 projector
            if d == 3 and rnd.random() < 0.5:
                pb = complement(pb)
            ab, ba = model_counts(vector(d), pa, pb)
            cases.append((ab, ba, matmul(pa, pb) == matmul(pb, pa)))
        src = 'import order.\n' + ''.join(
            f'let r{i} = [order.order_effect_a({counts_text(ab)}, {counts_text(ba)}), '
            f'order.order_effect_b({counts_text(ab)}, {counts_text(ba)}), order.qq_gap({counts_text(ab)}, {counts_text(ba)})].\n'
            for i, (ab, ba, _c) in enumerate(cases))
        r, rep, _ = run(src)
        self.assertEqual(rep['status'], 'done', rep['error'])
        for i, (ab, ba, commutes) in enumerate(cases):
            with self.subTest(ab=ab, ba=ba):
                got = value(r, f'r{i}')
                self.assertEqual(got, effects(ab, ba))
                self.assertEqual(got[2], 0)                                 # the QQ equality, exactly
                if commutes:
                    self.assertEqual(got, (0, 0, 0))                        # commuting questions: no order effect
                    commuting += 1
                moved += got[0] != 0 or got[1] != 0
        self.assertGreater(moved, 10)                                       # order effects without a QQ gap
        self.assertGreater(len(cases) - commuting, 10)

    def test_arbitrary_tallies_follow_the_definitions(self):
        rnd = random.Random(7)
        cases = []
        while len(cases) < 30:
            ab = {k: rnd.randint(0, 9) for k in ('yy', 'yn', 'ny', 'nn')}
            ba = {k: rnd.randint(0, 9) for k in ('yy', 'yn', 'ny', 'nn')}
            if sum(ab.values()) and sum(ba.values()):
                cases.append((ab, ba))
        src = 'import order.\n' + ''.join(
            f'let r{i} = [share_a_yes({counts_text(ab)}), share_b_yes({counts_text(ab)}), '
            f'share_different({counts_text(ab)}), order_effect_a({counts_text(ab)}, {counts_text(ba)}), '
            f'order_effect_b({counts_text(ab)}, {counts_text(ba)}), qq_gap({counts_text(ab)}, {counts_text(ba)})].\n'
            for i, (ab, ba) in enumerate(cases))
        r, rep, _ = run(src)
        self.assertEqual(rep['status'], 'done', rep['error'])
        for i, (ab, ba) in enumerate(cases):
            with self.subTest(ab=ab, ba=ba):
                got = value(r, f'r{i}')
                self.assertEqual(got, shares(ab) + effects(ab, ba))
                for x in got:
                    S.canon(x)
                    S.fingerprint(x)
        self.assertTrue(any(value(r, f'r{i}')[5] != 0 for i in range(len(cases))))   # a gap is not always 0


def subject(rule):
    """A scripted applicator that answers by ask name: rule(name, sample, first) -> Bool. The sample is the
    request's seed; for the second question, `first` is the earlier answer as the capsule's KNOWN shows it."""
    def answer(prompt, req):
        stmt = prompt.split('STATEMENT', 1)[-1]
        name = re.search(r'ask (\w+) :', stmt).group(1)
        known = re.search(r'^- (ab_a|ba_b) : Bool = (true|false)$', prompt, re.M)
        return {'answer': rule(name, req['seed'], None if known is None else known.group(2) == 'true')}
    return answer


def expected_counts(rule, samples):
    ab = dict.fromkeys(('yy', 'yn', 'ny', 'nn'), 0)
    ba = dict(ab)
    for s in samples:
        a1 = rule('ab_a', s, None)
        b2 = rule('ab_b', s, a1)
        b1 = rule('ba_b', s, None)
        a2 = rule('ba_a', s, b1)
        ab[('y' if a1 else 'n') + ('y' if b2 else 'n')] += 1
        ba[('y' if a2 else 'n') + ('y' if b1 else 'n')] += 1
    return ab, ba


def outputs(rep):
    return {o['label']: o for o in rep['outputs']}


class Example(Base):
    LABELS = ('counts when A was asked first', 'counts when B was asked first',
              'order effect on A: yes share, A first minus B first', 'order effect on B: yes share, A first minus B first',
              'QQ gap: share of different answers, A first minus B first')

    def setUp(self):
        super().setUp()
        with open(EXAMPLE, encoding='utf-8') as f:
            self.src = f.read()

    def test_it_checks_and_is_short(self):
        res = S.check(self.src)
        self.assertTrue(res['ok'], res['errors'])
        self.assertEqual(res['asks'], 4)
        self.assertLess(len(self.src.splitlines()), 50)
        self.assertIn('measures the applicators it is run with', self.src)
        self.assertIn('needs many samples to mean anything', self.src)

    def assert_shows(self, rep, ab, ba):
        out = outputs(rep)
        self.assertEqual(list(out), list(self.LABELS))
        ea, eb, q = effects(ab, ba)
        for label, expected in zip(self.LABELS, (ab, ba, ea, eb, q), strict=True):
            self.assertEqual(out[label]['hash'], S.fingerprint(S.norm_num(expected) if not isinstance(expected, dict)
                                                              else expected), label)

    def test_it_runs_to_done_and_tallies_both_orders(self):
        def rule(name, s, first):                 # agrees with A when A came first; contradicts B when B came first
            return {'ab_a': s <= 4, 'ab_b': first, 'ba_b': s <= 2, 'ba_a': not first if first is not None else None}[name]
        r, rep, apps = run(self.src, subject(rule))
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(value(r, 'ab'), {'yy': 4, 'yn': 0, 'ny': 0, 'nn': 2})
        self.assertEqual(value(r, 'ba'), {'yy': 0, 'yn': 4, 'ny': 2, 'nn': 0})
        out = outputs(rep)
        self.assertEqual(out[self.LABELS[2]]['hash'], S.fingerprint(0))                 # 4/6 - 4/6
        self.assertEqual(out[self.LABELS[3]]['hash'], S.fingerprint(Fraction(1, 3)))    # 4/6 - 2/6
        self.assertEqual(out[self.LABELS[4]]['hash'], S.fingerprint(-1))                # 0 - 1
        self.assert_shows(rep, *expected_counts(rule, range(1, 7)))
        # each sample is a fresh request: 24 calls, none answered from the run's record
        self.assertEqual((rep['asks'], rep['calls'], rep['cached']), (24, 24, 0))
        for name in ASK_NAMES:
            reqs = [q for q in apps.reqs if f'ask {name} :' in q['prompt']]
            self.assertEqual(sorted(q['seed'] for q in reqs), [1, 2, 3, 4, 5, 6], name)
        self.assertEqual({q['temperature'] for q in apps.reqs}, {0.7})

    def test_the_second_ask_sees_the_first_question_and_answer_only(self):
        def rule(name, s, first):
            return s % 2 == 1 if first is None else first
        _, rep, apps = run(self.src, subject(rule))
        self.assertEqual(rep['status'], 'done', rep['error'])
        for q in apps.reqs:
            stmt = q['prompt'].split('STATEMENT', 1)[-1]
            name = re.search(r'ask (\w+) :', stmt).group(1)
            if name in ('ab_a', 'ba_b'):
                self.assertIn('KNOWN: nothing beyond the statement itself.', q['prompt'])
            else:
                earlier = 'ab_a' if name == 'ab_b' else 'ba_b'
                known = re.findall(r'^- (\w+) : Bool = (true|false)$', q['prompt'], re.M)
                self.assertEqual(known, [(earlier, 'true' if q['seed'] % 2 == 1 else 'false')])
                asked_first = 'Is a tomato a fruit?' if name == 'ab_b' else 'Is a tomato a vegetable?'
                self.assertIn(f"You were asked '{asked_first}'", stmt)

    def test_inputs_and_an_independent_tally(self):
        rnd = random.Random(2013)
        samples = list(range(1, 21))
        table = {(n, s, f): rnd.random() < 0.5 for n in ASK_NAMES for s in samples for f in (None, True, False)}
        rule = lambda name, s, first: table[(name, s, first)]       # noqa: E731
        inputs = {'question_a': 'Is it raining?', 'question_b': 'Is the road wet?', 'samples': samples}
        r, rep, apps = run(self.src, subject(rule), inputs)
        self.assertEqual(rep['status'], 'done', rep['error'])
        ab, ba = expected_counts(rule, samples)
        self.assertEqual((value(r, 'ab'), value(r, 'ba')), (ab, ba))
        self.assert_shows(rep, ab, ba)
        self.assertEqual(rep['calls'], 80)
        self.assertTrue(all('Is it raining?' in q['prompt'] or 'Is the road wet?' in q['prompt'] for q in apps.reqs))
        r, rep, apps = run(self.src, subject(rule), {**inputs, 'samples': [3, 5, 8]})
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(sorted({q['seed'] for q in apps.reqs}), [3, 5, 8])
        self.assertEqual(sum(value(r, 'ab').values()), 3)

    def test_repeated_or_missing_samples_are_refused_before_any_call(self):
        for samples in ([1, 1, 2], []):
            with self.subTest(samples=samples):
                _, rep, apps = run(self.src, subject(lambda name, s, first: True), {'samples': samples})
                self.assertEqual(rep['status'], 'failed')
                self.assertIn('assert failed', rep['error']['message'])
                self.assertEqual(apps.reqs, [])


class PinnedExecution(Base):
    SRC = 'import order.\nshow order.qq_gap({yy: 18, yn: 18, ny: 32, nn: 32}, {yy: 49, yn: 1, ny: 49, nn: 1}).\n'

    def skip_without_kernel_files(self):
        absent = sorted(n for n in X.REQUIRED_FILES if not (X.BASE / n).is_file())
        if absent:
            self.skipTest(f'pinned execution needs every required kernel file; absent here: {absent}')

    def test_a_pinned_run_imports_order_from_its_snapshot_once_the_name_is_registered(self):
        self.skip_without_kernel_files()
        libraries = X.LIBRARIES | {'order'}                   # what execution_pins.LIBRARIES must contain
        with patch.object(X, 'LIBRARIES', libraries), \
                patch.object(X, 'LIBRARY_FILES', {f'symblic/lang/library/{n}.sym': n for n in libraries}):
            pins = X.build(self.SRC, {}, reviewed(['order']))
            self.assertEqual(set(pins['libraries']), {'order'})
            with patch.object(L, 'library_source', side_effect=AssertionError('No live library read')):
                rep = SR.Run(self.SRC, {}, None, {'execution_pins': pins}).execute()
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(rep['outputs'][0]['hash'], S.fingerprint(0))

    def test_every_library_file_is_registered_for_pinned_execution(self):
        files = sorted(p.stem for p in (X.BASE / 'symblic/lang/library').glob('*.sym'))
        missing = sorted(set(files) - X.LIBRARIES)
        if 'order' in missing:
            self.skipTest(f'execution_pins.LIBRARIES lacks {missing}: pinned runs refuse those imports, and the '
                          'interpreter hand-off (which pins every symblic/lang/library/*.sym) refuses every program')
        self.assertEqual(missing, [], 'an unregistered library file makes every interpreter hand-off fail')
        with self.subTest('the hand-off build accepts every library file'):
            self.skip_without_kernel_files()
            hashes = reviewed(files)
            X.build('show 1.\n', {}, {**hashes, **{n: hashlib.sha256((X.BASE / n).read_bytes()).hexdigest()
                                                   for n in sorted(X.PYTHON_FILES) if (X.BASE / n).is_file()}})


if __name__ == '__main__':
    unittest.main()
