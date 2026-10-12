"""Type-count syntax must produce bounded positioned errors, never a provider task."""
import unittest
from unittest import mock
from symblic.kernel import language as S
from symblic.kernel import run as R

CASES = [('List of Int length ', ''), ('Set of Int length ', ''),
         ('List of Text length 2..', ''), ('Set of Text length 2..', ''),
         ('Number to ', ' places'), ('Text up to ', ' words')]


def source(before, value, after, head='ask'):
    return '\n# a line before the declaration\n' + head + ' x: ' + before + value + after + ' "Choose a value".\n'


class CountLiterals(unittest.TestCase):
    def test_fractional_exponent_and_oversized_counts_have_positioned_syntax_errors(self):
        for before, after in CASES:
            for value in ('1.5', '1.0', '1e2', '2e-1', '9' * 4500):
                text = source(before, value, after)
                with self.subTest(type=before, literal=value[:20]):
                    with self.assertRaises(S.SymblicError) as caught:
                        S.parse(text)
                    error = caught.exception
                    self.assertEqual(error.kind, 'syntax')
                    self.assertEqual(error.line, 3)
                    self.assertEqual(error.col, len('ask x: ' + before) + 1)
                    self.assertLess(len(error.message), 90)
                    self.assertIn('integer', error.message)
                    report = S.check(text)
                    self.assertFalse(report['ok'])
                    self.assertEqual(report['errors'][0]['code'], 'SYM_SYNTAX')
                    self.assertEqual(report['errors'][0]['col'], error.col)

    def test_nested_record_types_report_the_actual_bad_count(self):
        text = 'given x: Record {rows: List of Record {name: Text up to 2.5 words}}.\n'
        with self.assertRaises(S.SymblicError) as caught:
            S.parse(text)
        self.assertEqual((caught.exception.line, caught.exception.col), (1, text.index('2.5') + 1))
        self.assertEqual(caught.exception.kind, 'syntax')

    def test_all_typed_statement_heads_keep_errors_structured(self):
        texts = ['given x: List of Int length 1.5.',
                 'let x: List of Int length 1.5 = [1].',
                 'define x: List of Int length 1.5 = [1].',
                 'ask x: List of Int length 1.5 "x".']
        for text in texts:
            with self.subTest(text=text):
                report = S.check(text)
                self.assertFalse(report['ok'])
                self.assertEqual(report['errors'][0]['code'], 'SYM_SYNTAX')

    def test_typo_detection_never_turns_a_malformed_count_into_a_prose_ask(self):
        for before, after in CASES:
            text = source(before, '1.5', after, head='assk')
            with self.subTest(type=before), self.assertRaises(S.SymblicError) as caught:
                S.parse(text)
            self.assertEqual(caught.exception.kind, 'syntax')
            self.assertIn('ask', caught.exception.message)
            report = S.check(text)
            self.assertFalse(report['ok'])

    def test_invalid_counts_fail_before_provider_or_statement_execution(self):
        for head in ('ask', 'assk'):
            apps = mock.Mock()
            text = source('List of Int length ', '1.5', '', head=head)
            report = R.Run(text, {}, apps, {'side_effects': False}).execute()
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['error']['code'], 'SYM_SYNTAX')
            self.assertEqual(report['calls'], 0)
            apps.call.assert_not_called()

    def test_valid_integer_count_types_keep_exact_native_shapes(self):
        rows = [('List of Int length 3', {'k':'list','of':{'k':'int'},'min':3,'max':3}),
                ('Set of Text length 0..4', {'k':'set','of':{'k':'text'},'min':0,'max':4}),
                ('Number to 0 places', {'k':'number','places':0}),
                ('Text up to 7 words', {'k':'text','max_words':7})]
        for typ, expected in rows:
            with self.subTest(type=typ):
                node = S.parse('ask x: ' + typ + ' "x".')['statements'][0]
                self.assertEqual(node.type, expected)

    def test_regular_numbers_and_literal_prose_remain_accepted(self):
        for text in ('let x = 1.5.\nshow x.', 'let x = 1e2.\nshow x.',
                     'ask x: Text "Describe length 1.5 and 1e2 as data".',
                     'Explain why a length of 1.5 can be measured.'):
            with self.subTest(text=text):
                self.assertTrue(S.check(text)['ok'])


if __name__ == '__main__':
    unittest.main()
