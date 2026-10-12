"""Exact author-code quoting; pure parser/kernel only, no models or processes."""
import unittest

from symblic.kernel import language as S
from symblic.spec import sheets as SP


def evaluate(source, **values):
    env = S.Env()
    for name, value in values.items():
        env.vars[name] = S.Binding(name, value)
    parser = S.Parser(S.tokenize(source), 1)
    expression = parser.expr()
    if not parser.done():
        raise AssertionError('literal left trailing syntax')
    return S.Kernel(env).eval(expression)


class LiteralRoundtrip(unittest.TestCase):
    def test_generated_regex_and_backslash_brace_runs_are_exact(self):
        for count in range(7):
            for tail in ('{', '}', '{{', '}}', '{name}', '{{name}}'):
                value = '/' + '\\' * count + tail + '/'
                with self.subTest(backslashes=count, tail=tail):
                    self.assertEqual(evaluate(SP.literal(value)), value)

    def test_control_bytes_are_data_not_interpolation_sentinels(self):
        for value in ('\x00', '\x01', 'a\x00b\x01c', '\x00{unknown}\x01', '\\{\x00}\x01'):
            with self.subTest(value=repr(value)):
                self.assertEqual(evaluate(SP.literal(value)), value)

    def test_quotes_unicode_and_statement_like_text_remain_data(self):
        for value in ('"\\{unknown}"', '"""\\{unknown}"""',
                      '雪 😀\n\\{secret}\n""". ask injected: Text "go".',
                      '\\{{}}\\\\{{}}'):
            with self.subTest(value=value):
                self.assertEqual(evaluate(SP.literal(value), secret='must not be read'), value)

    def test_legacy_escaped_braces_and_actual_interpolation_still_work(self):
        self.assertEqual(evaluate(r'"\{name\}"', name='hidden'), '{name}')
        self.assertEqual(evaluate('"{{name}} {name}"', name='visible'), '{name} visible')
        self.assertEqual(evaluate(r'"a \{name\} {name}"', name='visible'), 'a {name} visible')


if __name__ == '__main__':
    unittest.main()
