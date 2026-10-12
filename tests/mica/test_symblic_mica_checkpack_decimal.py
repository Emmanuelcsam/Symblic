"""Exact numeric bounds cannot depend on the caller's Decimal arithmetic context."""
from decimal import localcontext, Inexact, Rounded, Overflow, ROUND_DOWN, ROUND_UP
import hashlib
import json
from pathlib import Path
import unittest

from symblic.mica import checkpack as K


class DecimalContexts(unittest.TestCase):
    def test_both_unsafe_boundary_signs_refused_even_with_low_precision(self):
        for precision in (1, 2, 28):
            for rounding in (ROUND_DOWN, ROUND_UP):
                for text in ('9007199254740992', '-9007199254740992'):
                    with self.subTest(precision=precision, rounding=rounding, text=text), localcontext() as ctx:
                        ctx.prec, ctx.rounding = precision, rounding
                        with self.assertRaises(K.CheckPackError) as caught:
                            K._literal(text)
                        self.assertEqual(caught.exception.code, 'number')

    def test_valid_values_and_exact_bounds_survive_decimal_traps(self):
        with localcontext() as ctx:
            ctx.prec, ctx.Emax, ctx.Emin = 1, 2, -2
            for signal in (Inexact, Rounded, Overflow):
                ctx.traps[signal] = True
            for text in ('12', '-12', '9007199254740991', '-9007199254740991', '0.125'):
                with self.subTest(text=text):
                    _, expression = K._literal(text)
                    self.assertEqual(expression, text)

    def test_original_pack_historical_read_preserves_bytes_but_current_pin_refuses(self):
        path = Path(__file__).parent / 'fixtures/checkpack-decimal-original.json'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '0eb7235d8eadaa7722cce3c2e084c51b6268e9981312fc1f04e0c805bd499d89')
        original = json.loads(raw)
        self.assertEqual(original['implementation']['sources']['symblic_mica_checkpack.py'],
                         '9edf9f96e4a171d0e16931e21a827982eb484e37780d74592d72a3252bd54620')
        historical = K.validate(original, expected_sha256=original['sha256'], require_current=False)
        self.assertEqual(historical, original)
        self.assertEqual(historical['public_request']['tests'][-1]['expected'], '12')
        with self.assertRaises(K.CheckPackError) as caught:
            K.validate(original, expected_sha256=original['sha256'])
        self.assertEqual(caught.exception.code, 'identity')
        self.assertEqual(path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
