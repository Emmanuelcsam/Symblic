"""Symblic 2.3 diagnosis helpers (symblic_diagnose): explain, derived names, the empty answer of a type, the static
lints for check, retry exhaustion and option rotation. Kernel only: no model, no network, no store."""

import os
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import diagnose as D  # noqa: E402

SECRET = 987654321


def expr(src):
    p = S.Parser(S.tokenize(src), 1)
    node = p.expr()
    assert p.done(), src
    return node


def env_of(**values):
    env = S.Env()
    for name, value in values.items():
        env.vars[name] = S.Binding(name, value)
    return env


def explain(src, derived, **values):
    return D.explain(expr(src), env_of(**values), S.KB(), set(derived))


def statements(src):
    return S.parse(src)['statements']


class Purity(unittest.TestCase):
    def test_pure_means_kernel_only(self):
        self.assertTrue(D.pure(expr('len(text(n)) + abs(n) > 3 and (all x in xs: x > 0)')))
        self.assertFalse(D.pure(expr('helper(n) > 3')))                  # a user function may call a routine
        self.assertFalse(D.pure(expr('query likes(ann, X)')))

    def test_derived_names_follow_the_answer_only(self):
        src = ('ask n: Int "?"\nlet a = n + 1.\nlet b = a * secret.\nlet c = a * pi.\nlet d = helper(n).\n'
               'let e = b + 1.\nlet f = 3.\n')
        between = statements(src)[1:]
        self.assertEqual(D.derived_names('n', between, S.Env()), {'n', 'a', 'c', 'f'})
        self.assertEqual(D.derived_names('n', between), {'n', 'a', 'f'})      # no env: no constant counts
        shadow = S.Env()
        shadow.vars['pi'] = S.Binding('pi', 'an input')                    # given pi: Text (review A3)
        self.assertEqual(D.derived_names('n', between, shadow), {'n', 'a', 'f'})


class Explain(unittest.TestCase):
    def test_cmp_shows_answer_only_operands_and_no_literal(self):
        self.assertEqual(explain('n * 2 > secret', {'n'}, n=3, secret=SECRET), 'n * 2 = 6')
        self.assertEqual(explain('n > 5', {'n'}, n=3), 'n = 3')
        self.assertEqual(explain('n = secret', {'n'}, n=3, secret=SECRET), 'n = 3')

    def test_and_explains_the_first_false_showable_conjunct(self):
        self.assertEqual(explain('n > 0 and n * 2 > 10 and len(text(n)) > 4', {'n'}, n=3), 'n * 2 = 6')
        # the failing conjunct reads an outside name: it is not evaluated, shown or named
        self.assertEqual(explain('n > 0 and n < secret', {'n'}, n=SECRET + 5, secret=SECRET), '')

    def test_or_explains_each_showable_side(self):
        self.assertEqual(explain('n > 5 or n = secret', {'n'}, n=3, secret=SECRET), 'n = 3')
        self.assertEqual(explain('n > 5 or len(text(n)) > 3', {'n'}, n=3), 'n = 3; len(text(n)) = 1')

    def test_implication_explains_its_right_side(self):
        self.assertEqual(explain('n > 0 -> n * 3 > 10', {'n'}, n=3), 'n * 3 = 9')

    def test_quantifiers(self):
        xs = (1, -2, 3)
        self.assertEqual(explain('all x in xs: x > 0', {'xs'}, xs=xs), 'fails for x = -2 (item 2 of 3)')
        self.assertEqual(explain('all x in xs: x * x < 3', {'xs'}, xs=xs),
                         'fails for x = -2 (item 2 of 3): x * x = 4')
        self.assertEqual(explain('none x in xs: x > 2', {'xs'}, xs=xs), 'holds for x = 3 (item 3 of 3)')
        self.assertEqual(explain('any x in xs: x > 5', {'xs'}, xs=xs), 'no item of xs passes (3 items)')
        # an outside source, or a body that reads an outside name, contributes nothing
        self.assertEqual(explain('all x in limits: x < n', {'n'}, n=3, limits=(SECRET,)), '')
        self.assertEqual(explain('all x in xs: x != secret', {'xs'}, xs=xs, secret=-2), '')

    def test_calls_show_their_answer_only_arguments(self):
        self.assertEqual(explain('contains(t, secret)', {'t'}, t='abc', secret='zebra'), 't = abc')
        self.assertEqual(explain('helper(n + 1, secret)', {'n'}, n=3, secret=SECRET), 'n + 1 = 4')

    def test_other_kinds_errors_and_budget_give_nothing(self):
        self.assertEqual(explain('not (n > 5)', {'n'}, n=9), '')
        self.assertEqual(explain('xs[9] > 0', {'xs'}, xs=(1,)), '')                 # an index error
        self.assertEqual(D.explain(expr('n * 2 > 10'), env_of(n=3), S.KB(), {'n'}, steps=1), '')

    def test_never_binds_into_the_run_environment(self):
        env = env_of(xs=(1, -2))
        D.explain(expr('all x in xs: x > 0'), env, S.KB(), {'xs'})
        self.assertEqual(set(env.vars), {'xs'})

    def test_a_program_that_binds_a_constant_name_gets_nothing(self):
        # `let c = n * pi` counts as derived; with pi bound to an input that would show the input
        self.assertEqual(explain('c < 0', {'n', 'c'}, n=1, c=SECRET, pi=SECRET), '')

    def test_at_most_400_characters_cut_between_pieces(self):
        values = {f't{i}': f'{i}' * 200 for i in range(10)}
        src = ' < '.join(values)
        out = D.explain(expr(src), env_of(**values), S.KB(), set(values))
        self.assertLessEqual(len(out), 400)
        pieces = out.split('; ')
        self.assertGreaterEqual(len(pieces), 2)
        self.assertTrue(all(p.startswith('t') and ' = ' in p for p in pieces))


class Trivial(unittest.TestCase):
    def ty(self, text):
        return S.resolve_type(S.Parser(S.tokenize(text), 1).type_expr(), {})

    def test_each_type(self):
        cases = [('Text', (True, '')), ('List of Int', (True, ())), ('List of Int length 0..3', (True, ())),
                 ('List of Text length 2', (True, ('', ''))), ('List of Bool length 2..4', (False, (False, False))),
                 ('Int', (True, 0)), ('Number', (True, 0)), ('Int in 1..5', (False, 1)), ('Int in -5..5', (False, 0)),
                 ('Number in 0.5..2', (False, Fraction(1, 2))), ('Bool', (False, False)),
                 ('one of {red, blue}', (False, 'red')), ('Record {a: Text, b: Bool}', (True, {'a': '', 'b': False})),
                 ('Record {a: Int in 1..3, b: Bool}', (False, {'a': 1, 'b': False}))]
        for text, want in cases:
            with self.subTest(text):
                got = D.trivial(self.ty(text))
                self.assertEqual(got, want)
                self.assertEqual(S.check_value(got[1], self.ty(text)), got[1])

    def test_sets_and_types_without_an_empty_value(self):
        empty = D.trivial(self.ty('Set of Text'))
        self.assertEqual(empty[0], True)
        self.assertIsInstance(empty[1], S.ValueSet)
        self.assertEqual(len(empty[1]), 0)
        for text in ('Set of Int length 1..3', 'Any', 'Svg', 'Record {a: Set of Int length 2, b: Text}'):
            with self.subTest(text):
                self.assertIsNone(D.trivial(self.ty(text)))


class StaticWarnings(unittest.TestCase):
    def warnings(self, src):
        prog = S.parse(src)
        types = {s.name: s.type for s in prog['statements'] if s.k == 'define'}
        return D.static_warnings(prog['statements'], types)

    def test_a_check_that_accepts_the_empty_answer(self):
        rows = self.warnings('ask name: Text "Name the river."\nlet n = len(name).\nensure n < 100 else retry.\n')
        self.assertEqual(rows, [{'line': 1, 'code': 'SYM_VACUOUS', 'message': 'name: its checks accept the empty '
                                 'answer ""; add a check that an empty answer fails'}])
        rows = self.warnings('define Pair as Record {a: Text, b: Int}.\nask p: Pair "?"\n'
                             'let k: Int = p.b.\nensure k < 10 else retry.\n')
        self.assertEqual([r['line'] for r in rows], [2])
        self.assertIn('{a: "", b: 0}', rows[0]['message'])

    def test_blocks_are_walked(self):
        src = ('let xs = [1, 2].\nfor i in xs do\n  ask a: List of Int "?"\n  ensure len(a) < 9 else retry.\nend.\n'
               'if true then\n  ask b: Text "?"\n  ensure len(b) < 9 else retry.\nend.\n')
        self.assertEqual([r['line'] for r in self.warnings(src)], [3, 7])

    def test_no_finding(self):
        for src in ('ask a: Text "?"\nensure len(a) > 0 else retry.\n',                         # the check works
                    'ask a: Text "?"\nshow a.\nensure len(a) < 9 else retry.\n',              # a statement between
                    'given g: Int = 3.\nask a: Text "?"\nensure len(a) < g else retry.\n',     # an outside name
                    'ask a: Text "?"\nensure helper(a) else retry.\n',                         # not kernel only
                    'ask a: Bool "?"\nensure a or not a else retry.\n',                        # no open part
                    'ask a: Text "?" for each i in [1]\nensure len(a) < 9 else retry.\n',      # for each
                    'ask a: Text "?"\nensure len(a) < 9 else warn.\n'):                        # not a retry check
            with self.subTest(src):
                self.assertEqual(self.warnings(src), [])

    def test_budget_is_shared_and_never_raises(self):
        src = 'ask a: Text "?"\nensure len(a) < 9 and sum(1..60000) > 0 else retry.\n'
        self.assertEqual(self.warnings(src), [])
        self.assertEqual(D.static_warnings([object()], None), [])

    def test_check_reports_it(self):
        out = S.check('ask name: Text "Name the river."\nensure len(name) < 100 else retry.\n')
        self.assertIn('SYM_VACUOUS', [w.get('code') for w in out['warnings']])


class SameKey(unittest.TestCase):
    def setUp(self):
        from symblic.kernel import effects as FX
        self.FX = FX
        FX.set_catalogue(None)
        self.addCleanup(FX.set_catalogue, None)

    def warnings(self, src):
        return [w for w in D.static_warnings(S.parse(src)['statements'], {}) if w['code'] == 'SYM_SAME_KEY']

    def test_two_acts_with_one_literal_key(self):
        src = ('act a = notes.write(text="one") with key="daily".\n'
               'act b = notes.write(text="two") with key="daily".\n')
        self.assertEqual(self.warnings(src), [{'line': 2, 'code': 'SYM_SAME_KEY', 'message':
                         'act notes.write: the key "daily" is also used at line 1; an action with a key happens '
                         "once, so this statement would get that one's outcome"}])
        catalogue = self.FX.normalize_catalogue([{'name': 'notes.write', 'effect': 'write-local', 'policy': 'auto',
                                                  'params': {'type': 'object', 'properties':
                                                             {'text': {'type': 'string'}}}}])
        out = self.FX.check(src, catalogue)
        self.assertIn('SYM_SAME_KEY', [w.get('code') for w in out['warnings']])

    def test_no_warning(self):
        for src in ('act a = notes.write(text="one") with key="daily".\n'
                    'act b = notes.write(text="two") with key="weekly".\n',
                    'act a = notes.write(text="one") with key="daily".\n'
                    'act b = mail.send(to="x") with key="daily".\n',
                    'let d = 1.\nact a = notes.write(text="one") with key="day {d}".\n'
                    'act b = notes.write(text="two") with key="day {d}".\n',
                    'act a = notes.write(text="one").\nact b = notes.write(text="two").\n',
                    'if true then\n  act a = notes.write(text="one") with key="daily".\nelse\n'
                    '  act b = notes.write(text="two") with key="daily".\nend.\n'):
            with self.subTest(src):
                self.assertEqual(self.warnings(src), [])

    def test_same_path_through_blocks(self):
        src = ('act a = notes.write(text="one") with key="daily".\nif true then\n'
               '  act b = notes.write(text="two") with key="daily".\nend.\n')
        self.assertEqual([w['line'] for w in self.warnings(src)], [3])


class Exhaustion(unittest.TestCase):
    def test_patterns(self):
        self.assertIsNone(D.exhaustion([]))
        self.assertIsNone(D.exhaustion(['a']))
        self.assertEqual(D.exhaustion(['a', 'a', 'a']), {'attempts': 3, 'distinct': 1, 'pattern': 'same'})
        self.assertEqual(D.exhaustion(['a', 'b', 'c']), {'attempts': 3, 'distinct': 3, 'pattern': 'different'})
        self.assertEqual(D.exhaustion(['a', 'a', 'b']), {'attempts': 3, 'distinct': 2, 'pattern': 'mixed'})

    def test_texts(self):
        self.assertEqual(D.exhaustion_text({'pattern': 'same'}), 'every attempt gave the same answer, so the check, '
                         'the answer type or the input may be what is wrong')
        self.assertEqual(D.exhaustion_text({'pattern': 'different'}), 'every attempt gave a different answer, so the '
                         'statement may be read in more than one way')
        self.assertEqual(D.exhaustion_text({'pattern': 'mixed'}), '')


class Rotation(unittest.TestCase):
    def test_every_one_of_rotates(self):
        ty = {'k': 'record', 'fields': [
            ['kind', {'k': 'enum', 'options': ['a', 'b', 'c'], 'defs': {'a': 'first'}}],
            ['tags', {'k': 'list', 'of': {'k': 'enum', 'options': ['x', 'y']}}],
            ['n', {'k': 'int'}]]}
        one = D.rotated(ty, 1)
        self.assertEqual(one['fields'][0][1]['options'], ['b', 'c', 'a'])
        self.assertEqual(one['fields'][0][1]['defs'], {'a': 'first'})
        self.assertEqual(one['fields'][1][1]['of']['options'], ['y', 'x'])
        self.assertEqual(one['fields'][2][1], {'k': 'int'})
        self.assertEqual(D.rotated(ty, 4)['fields'][0][1]['options'], ['b', 'c', 'a'])     # 4 mod 3
        self.assertEqual(ty['fields'][0][1]['options'], ['a', 'b', 'c'])                    # a copy
        self.assertEqual(D.rotated(ty, 0), ty)

    def test_has_options(self):
        self.assertTrue(D.has_options({'k': 'enum', 'options': ['a', 'b']}))
        self.assertTrue(D.has_options({'k': 'set', 'of': {'k': 'enum', 'options': ['a', 'b']}}))
        self.assertFalse(D.has_options({'k': 'int'}))
        self.assertFalse(D.has_options({'k': 'record', 'fields': [['t', {'k': 'text'}]]}))


if __name__ == '__main__':
    unittest.main()
