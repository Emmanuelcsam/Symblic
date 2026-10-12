"""Empty record literals survive table serialization without becoming sets."""
import unittest

from symblic.kernel import language as S
from symblic.lang import abstraction as L


class EmptyRecordLiteral(unittest.TestCase):
    def test_empty_record_round_trip_and_set_distinction(self):
        self.assertEqual(L._check_literal({}), '{:}')
        values = ({}, {'empty': {}, 'nested': ({}, frozenset())}, ({}, {}))
        for value in values:
            with self.subTest(value=value):
                source = L._check_literal(value)
                back = S.Kernel().eval(S.Parser(S.tokenize(source), 1).expr())
                self.assertEqual(S.canon_json(back), S.canon_json(value))
        self.assertNotEqual(S.fingerprint({}), S.fingerprint(frozenset()))
        self.assertEqual(L._check_literal(frozenset()), 'set([])')


if __name__ == '__main__':
    unittest.main()
