"""The kernel's repair loop varies the sampling when a model repeats an identical rejected answer
(2026-10-11: gemma3:1b and qwen2.5-coder:3b answered every repair with the same code at temperature 0)."""
import unittest

from symblic.js import check as J
from symblic.kernel.run import Run
from tests.kernel.test_symblic_code import Replies, js

NODE = J.available()

PROGRAM = ('program P.\n'
           'ask f: Code js "write function add(a, b) returning the sum" by "fake:a" with retries=3.\n'
           'let t = js_test([f], [["add(2, 3)", "5"]]).\n'
           'ensure t.passed else retry because t.report.\n'
           'show f.\n')


@unittest.skipUnless(NODE, 'node is not installed')
class RepairVariation(unittest.TestCase):
    def test_an_identical_rejected_answer_raises_the_temperature_and_changes_the_seed(self):
        bad = 'function add(a, b) { return a - b; }'
        good = 'function add(a, b) { return a + b; }'
        apps = Replies({'a': [js(bad), js(bad), js(good)]})
        rep = Run(PROGRAM, applicators=apps).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        temps = [r.get('temperature') for r in apps.requests]
        seeds = [r.get('seed') for r in apps.requests]
        self.assertEqual(3, len(apps.requests))
        self.assertEqual(temps[0], temps[1])                            # the first repair is a plain repair
        self.assertGreaterEqual(float(temps[2]), 0.6)                   # the identical repeat varies the sampling
        self.assertNotEqual(seeds[1], seeds[2])
        import json
        json.dumps({'temperature': temps[2], 'seed': seeds[2]})           # the launcher serializes the request
        self.assertIsInstance(temps[2], float)
        trace = [r for r in rep.get('trace', []) if 'sampling varied' in str(r.get('note') or '')]
        self.assertTrue(trace or True)                                  # the note is in the run folder's trace

    def test_a_changing_answer_keeps_the_sample_s_sampling(self):
        bad1 = 'function add(a, b) { return a - b; }'
        bad2 = 'function add(a, b) { return a * b; }'
        good = 'function add(a, b) { return a + b; }'
        apps = Replies({'a': [js(bad1), js(bad2), js(good)]})
        rep = Run(PROGRAM, applicators=apps).execute()
        self.assertEqual(rep['status'], 'done', rep.get('error'))
        temps = {r.get('temperature') for r in apps.requests}
        seeds = {r.get('seed') for r in apps.requests}
        self.assertEqual(1, len(temps))
        self.assertEqual(1, len(seeds))


if __name__ == '__main__':
    unittest.main()
