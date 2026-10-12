"""Native parser grammar compatibility and bounded hostile-input regressions."""

import random
import re
import unittest
from unittest import mock
from fractions import Fraction

from symblic.kernel import language as S


class CountedText(str):
    """Charge indexed/sliced source characters, independent of wall-clock load."""

    def __new__(cls, text):
        obj = super().__new__(cls, text)
        obj.reads = 0
        return obj

    def __getitem__(self, key):
        self.reads += len(range(*key.indices(len(self)))) if isinstance(key, slice) else 1
        if self.reads > 12 * len(self) + 100:
            raise AssertionError('source character visits exceeded a linear budget')
        return super().__getitem__(key)


class LinearPunctuation(unittest.TestCase):
    def test_suffix_table_matches_original_comment_and_whitespace_rule(self):
        rng = random.Random(6222026)
        examples = ['', '.', '#', '\n#x', '"#".field.', "'#'.field #tail",
                    '\r#x\rY', '.\u00a0#x\n\u2003', '#\n.x #comment\n#end']
        alphabet = 'a.# \t\r\n' + '\u00a0\u2003' + '\\"\''
        examples += [''.join(rng.choice(alphabet) for _ in range(rng.randrange(80)))
                     for _ in range(1500)]
        for text in examples:
            suffixes = S._trivia_suffixes(text)
            for i, actual in enumerate(suffixes):
                expected = not re.sub(r'#[^\n]*', '', text[i:]).strip()
                self.assertEqual(bool(actual), expected, (text, i))

    def test_dots_comments_ranges_decimals_strings_and_positions(self):
        cases = [
            ('a.b. # tail\n# second', [('name', 'a'), ('attr', '.'), ('name', 'b'), ('stop', '.')]),
            ('1..4.', [('num', '1'), ('op', '..'), ('num', '4'), ('stop', '.')]),
            ('1.25e-2.', [('num', '1.25e-2'), ('stop', '.')]),
            ('"#".field.', [('str', '#'), ('attr', '.'), ('name', 'field'), ('stop', '.')]),
            ('"""a#\nb""".field.', [('str', 'a#\nb'), ('attr', '.'), ('name', 'field'), ('stop', '.')]),
            ('x.\u00a0# ignore\n\u2003', [('name', 'x'), ('stop', '.')]),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                tokens = S.tokenize(source, 7)
                self.assertEqual([(t.kind, t.value) for t in tokens], expected)
        tokens = S.tokenize('a\n.b.', 7)
        self.assertEqual([(t.line, t.col) for t in tokens], [(7, 1), (8, 1), (8, 2), (8, 3)])
        for source in ['x. y', 'x.1', 'x. #comment\ny', 'x.\\', 'x.\u00a0y']:
            with self.subTest(source=source), self.assertRaises(S.SymblicError) as caught:
                S.tokenize(source)
            self.assertEqual(caught.exception.kind, 'syntax')

    def test_comment_suffix_and_attribute_visits_are_linear(self):
        for count in [2048, 16362, 50000]:
            text = CountedText('a' + '.a' * count + '\n' + '#\n' * count + '.')
            tokens = S.tokenize(text)
            self.assertEqual(len(tokens), 2 * count + 2)
            self.assertLessEqual(text.reads, 12 * len(text) + 100)
            self.assertEqual(tokens[-1].kind, 'stop')


class BoundedExpressions(unittest.TestCase):
    def test_reported_hostile_shape_has_positioned_syntax_error(self):
        head = 'ask x: Int = "Construct a value".\nensure x = 7 else retry.\nensure (a'
        source = head + '.a' * 16362 + '\n' + '#\n' * 16362 + ') = 1 else retry.\n'
        self.assertLessEqual(len(source), 65536)
        with self.assertRaises(S.SymblicError) as caught:
            S.parse(source)
        self.assertEqual(caught.exception.kind, 'syntax')
        self.assertEqual(caught.exception.line, 3)
        self.assertGreater(caught.exception.col, 0)
        report = S.check(source)
        self.assertFalse(report['ok'])
        self.assertEqual(report['errors'][0]['code'], 'SYM_SYNTAX')

    def test_attribute_index_binary_and_grouped_chains_refuse(self):
        shapes = ['a' + '.a' * 2000, 'a' + '[1]' * 2000,
                  '1' + ' + 1' * 2000,
                  '(a' + '.a' * 80 + ')' + '.a' * 80,
                  '(' + '1 + ' * 80 + '1)' + ' + 1' * 80]
        for shape in shapes:
            with self.subTest(shape=shape[:100]):
                report = S.check('let value = ' + shape + '.')
                self.assertFalse(report['ok'])
                self.assertEqual(report['errors'][0]['code'], 'SYM_SYNTAX')
                self.assertIn('nested too deeply', report['errors'][0]['message'])

    def test_depth_boundary_counts_ast_nodes_not_container_width(self):
        node = S.Parser(S.tokenize('a' + '.a' * (S.MAX_AST_DEPTH - 1)), 1).expr()
        self.assertEqual(node.k, 'attr')
        with self.assertRaises(S.SymblicError):
            S.Parser(S.tokenize('a' + '.a' * S.MAX_AST_DEPTH), 1).expr()
        for source in ['let xs = [' + ','.join('1' for _ in range(2000)) + '].',
                       'assert ' + ' < '.join(str(i) for i in range(2000)) + '.']:
            with self.subTest(prefix=source[:60]):
                self.assertTrue(S.check(source)['ok'])

    def test_nested_grouping_and_recursive_operator_errors_are_structured(self):
        for expr in ['(' * 2000 + '1' + ')' * 2000,
                     'not ' * 2000 + 'true', '- ' * 2000 + '1',
                     'true -> ' * 2000 + 'true', '1 ^ ' * 2000 + '1']:
            with self.subTest(prefix=expr[:60]):
                parser = S.Parser(S.tokenize(expr), 1)
                with self.assertRaises(S.SymblicError) as caught:
                    parser.expr()
                self.assertEqual(parser.depth, 0)
                self.assertEqual(caught.exception.kind, 'syntax')
                self.assertGreater(caught.exception.line, 0)
                self.assertFalse(S.check('let result = ' + expr + '.')['ok'])

    def test_type_entry_depth_is_bounded_for_lists_records_and_groups(self):
        for type_source in ['List of ' * 1200 + 'Int',
                            'Record {field: ' * 1200 + 'Int' + '}' * 1200,
                            '(' * 1200 + 'Int' + ')' * 1200]:
            with self.subTest(prefix=type_source[:60]):
                parser = S.Parser(S.tokenize(type_source), 1)
                with self.assertRaises(S.SymblicError) as caught:
                    parser.type_expr()
                self.assertEqual(parser.type_depth, 0)
                self.assertEqual(caught.exception.kind, 'syntax')
                report = S.check('ask x: ' + type_source + ' = "x".')
                self.assertFalse(report['ok'])
                self.assertEqual(report['errors'][0]['code'], 'SYM_SYNTAX')
        self.assertTrue(S.check('ask x: ' +
                                'List of ' * (S.MAX_DEPTH - 1) + 'Int = "x".')['ok'])
        wide = 'Record {' + ', '.join('field' + str(i) + ': Int' for i in range(1000)) + '}'
        self.assertTrue(S.check('ask x: ' + wide + ' = "x".')['ok'])

    def test_direct_fact_rule_and_postfix_entry_recursion_is_structured(self):
        for source in ['fact ' + 'query ' * 1200 + 'p(1).',
                       'rule p(X) if ' + 'holds ' * 1200 + 'q(X).',
                       'fact ' + 'a' + '.a' * 1200 + '.',
                       'rule p(X) if ' + 'a' + '[1]' * 1200 + '.']:
            with self.subTest(prefix=source[:60]):
                with self.assertRaises(S.SymblicError):
                    S.parse(source)
                self.assertEqual(S.check(source)['errors'][0]['code'], 'SYM_SYNTAX')
        parser = S.Parser(S.tokenize('query ' * 1200 + 'p(1)'), 1)
        with self.assertRaises(S.SymblicError):
            parser.postfix()
        self.assertEqual(parser.postfix_depth, 0)
        self.assertTrue(S.check('fact p(a).\nrule q(X) if p(X).')['ok'])

    def test_rule_comparison_entry_refuses_deep_binary_tree_before_safety_walk(self):
        source = 'rule p(X) if q(X), ' + '1 + ' * 2000 + '1 = 1.'
        with self.assertRaises(S.SymblicError) as caught:
            S.parse(source)
        self.assertEqual(caught.exception.kind, 'syntax')
        self.assertEqual(S.check(source)['errors'][0]['code'], 'SYM_SYNTAX')
        parser = S.Parser(S.tokenize('1 + ' * 2000 + '1 = 1'), 1)
        with self.assertRaises(S.SymblicError):
            parser.comparison()
        self.assertEqual(parser.depth, 0)
        self.assertTrue(S.check('rule p(X) if q(X), ' +
                                ' < '.join(str(i) for i in range(2000)) + '.')['ok'])

    def test_direct_rule_and_fact_entries_validate_only_once(self):
        for entry, source in [('postfix', 'p((1 + 2), q(3))'),
                              ('comparison', 'p((1 + 2), q(3)) = 4')]:
            with self.subTest(entry=entry), mock.patch.object(
                    S, '_check_expression_depth', wraps=S._check_expression_depth) as check_depth:
                parser = S.Parser(S.tokenize(source), 1)
                getattr(parser, entry)()
                self.assertEqual(check_depth.call_count, 1)
                self.assertEqual(parser.depth, 0)

    def test_formal_depth_refusal_never_becomes_implicit_prose_or_model_call(self):
        from symblic.kernel import run as SR

        source = 'let a = 1.\n    ' + 'a + ' * 150 + '1.'
        with self.assertRaises(S.SymblicError) as caught:
            S.parse(source)
        self.assertEqual(caught.exception.line, 2)
        self.assertGreaterEqual(caught.exception.col, 5)
        self.assertFalse(S.check(source)['ok'])
        apps = mock.Mock()
        apps.call.side_effect = AssertionError('a depth refusal must not dispatch a model')
        report = SR.Run(source, None, apps, {'by': 'fake:x'}).execute()
        self.assertNotEqual(report['status'], 'done')
        apps.call.assert_not_called()
        self.assertEqual([n.k for n in S.parse('let a = 1.\na + 1.')['statements']], ['let', 'show'])
        self.assertTrue(S.parse('Explain a pleasant afternoon.')['statements'][0].prose)

    def test_keyword_typo_depth_refusal_never_becomes_prose(self):
        from symblic.kernel import run as SR

        source = 'lett value = ' + '1 + ' * 150 + '1.'
        with self.assertRaises(S.SymblicError) as caught:
            S.parse(source)
        self.assertIn('did you mean `let`', caught.exception.message)
        apps = mock.Mock()
        apps.call.side_effect = AssertionError('a keyword typo must not dispatch a model')
        report = SR.Run(source, None, apps, {'by': 'fake:x'}).execute()
        self.assertNotEqual(report['status'], 'done')
        apps.call.assert_not_called()

    def test_outer_expression_validates_only_once(self):
        with mock.patch.object(S, '_check_expression_depth', wraps=S._check_expression_depth) as check_depth:
            S.Parser(S.tokenize('((1 + 2) * (3 + 4))'), 1).expr()
        self.assertEqual(check_depth.call_count, 1)

    def test_parser_acceptance_boundary_is_in_semantic_identity(self):
        # version 4 (exact backslash and doubled-brace literals) came after this test was written for 3; the test
        # had not been updated in the development tree either
        self.assertEqual(S.PARSER_VERSION, 4)
        self.assertEqual(S.kernel_id()['parser'], S.PARSER_VERSION)
        self.assertEqual(S.kernel_id()['parser_limits'], {'syntax_depth': 60, 'ast_depth': 128})
        self.assertEqual(S.CANON_VERSION, 3)

    def test_66_root_existing_prompt_fixture_is_preserved_without_changes(self):
        from tests.kernel.test_symblic_core_repair_run import PROMPT_PROGRAMS, lineage_run

        source, answers = PROMPT_PROGRAMS['many_roots_feed_context']
        run, report, apps = lineage_run(source, *answers, profile='verified', max_asks=200)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(run.kernel.env.lookup('t').value, 66)
        self.assertEqual(len(apps.requests), 67)

    def test_long_sum_and_AST_boundary_survive_recursive_consumers(self):
        from symblic.kernel import run as SR

        for count in [100, S.MAX_AST_DEPTH]:
            source = 'let value = ' + ' + '.join('1' for _ in range(count)) + '.\nassert value = ' + str(count) + '.'
            apps = mock.Mock()
            apps.call.side_effect = AssertionError('exact arithmetic must not dispatch a model')
            run = SR.Run(source, None, apps, {'by': 'fake:x'})
            report = run.execute()
            self.assertEqual(report['status'], 'done', report.get('error'))
            self.assertEqual(run.kernel.env.lookup('value').value, count)
            apps.call.assert_not_called()
        value = 7
        for _ in range(S.MAX_AST_DEPTH - 1):
            value = {'field': value}
        env = S.Env()
        env.vars['root'] = S.Binding('root', value)
        node = S.Parser(S.tokenize('root' + '.field' * (S.MAX_AST_DEPTH - 1)), 1).expr()
        self.assertEqual(S.free_names(node), {'root'})
        self.assertEqual(S.Kernel(env).eval(node), 7)
        self.assertTrue(S.check('given root: Any.\nlet value = root' +
                                '.field' * (S.MAX_AST_DEPTH - 1) + '.')['ok'])

    def test_regular_field_index_module_call_and_arithmetic_still_evaluate(self):
        env = S.Env()
        cases = [('({a: [3, 4]}).a[2]', 4), ('1 / 3 + 1 / 6', Fraction(1, 2)),
                 ('[1, 2, 3][2]', 2), ('2 ^ 3 ^ 2', 512)]
        for source, value in cases:
            parser = S.Parser(S.tokenize(source), 1)
            node = parser.expr()
            parser.finish()
            self.assertEqual(S.Kernel(env).eval(node), value)
        parser = S.Parser(S.tokenize('g.area(2)'), 1)
        call = parser.expr()
        self.assertEqual((call.k, call.fn, call.args[0].value), ('call', 'g.area', 2))


if __name__ == '__main__':
    unittest.main()
