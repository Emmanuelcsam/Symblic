"""Field-vote admission regressions; fake providers and memory-only runtimes."""
import unittest
from symblic.kernel import language as S
from symblic.kernel.run import Run


def samples(values, weights=None):
    weights = weights or [1] * len(values)
    return [{'value': v, 'hash': S.fingerprint(v), 'weight': w,
             'app': 'fake:' + chr(97 + i), 'order': i}
            for i, (v, w) in enumerate(zip(values, weights))]


def shape(*names):
    return {'k': 'record', 'fields': [[name, {'k': 'int'}] for name in names]}


class FakeApps:
    def __init__(self):
        self.calls = []

    def call(self, req):
        self.calls.append(req)
        return {'ok': True, 'json': {'answer': {'x': 1 if req['app']['model'] == 'a' else 2}},
                'model': req['app']['model'], 'node': req['app']['node'], 'ms': 0}


class FieldVoteRegression(unittest.TestCase):
    def test_equal_field_tie_is_contested(self):
        result = S.consensus_fields(samples([{'x': 1}, {'x': 2}]), shape('x'), 0.5)
        self.assertTrue(result['contested'])
        self.assertTrue(result['tied'])
        self.assertTrue(result['fields']['x']['contested'])
        self.assertTrue(result['fields']['x']['tied'])

    def test_whole_tie_does_not_override_decisive_fields(self):
        result = S.consensus_fields(samples([{'x': 1, 'y': 1, 'z': 0},
                                             {'x': 1, 'y': 0, 'z': 1},
                                             {'x': 0, 'y': 1, 'z': 1}]), shape('x', 'y', 'z'))
        self.assertEqual(result['value'], {'x': 1, 'y': 1, 'z': 1})
        self.assertFalse(result['contested'])
        self.assertFalse(result['tied'])
        self.assertTrue(result['tied_whole'])
        self.assertEqual(result['support'], 0)

    def test_rounded_display_cannot_pass_threshold(self):
        rows = samples([{'x': 1}, {'x': 2}], [599951, 400049])
        result = S.consensus_fields(rows, shape('x'), 0.599975)
        self.assertEqual(result['agreement'], 0.6)
        self.assertTrue(result['contested'])
        self.assertFalse(result['tied'])

    def test_rounded_display_cannot_refuse_threshold(self):
        rows = samples([{'x': 1}, {'x': 2}], [600049, 399951])
        result = S.consensus_fields(rows, shape('x'), 0.600025)
        self.assertEqual(result['agreement'], 0.6)
        self.assertFalse(result['contested'])
        self.assertFalse(result['tied'])

    def test_strict_runtime_refuses_tie_before_binding(self):
        apps = FakeApps()
        source = ('use profile=verified.\ngroup voters = ["fake:a", "fake:b"].\n'
                  'ask choice: Record {x: Int} "Return the fixture choice." by voters '
                  'with effort=low, vote=fields, determine=false, solve=false, retries=0.\n')
        runner = Run(source, {}, apps, {'parallel': 1})
        result = runner.execute()
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error']['kind'], 'check')
        self.assertIn('tie', result['error']['message'])
        self.assertIsNone(runner.kernel.env.lookup('choice'))

    def test_legacy_runtime_keeps_tie_visible(self):
        apps = FakeApps()
        source = ('group voters = ["fake:a", "fake:b"].\n'
                  'ask choice: Record {x: Int} "Return the fixture choice." by voters '
                  'with effort=low, vote=fields, determine=false, solve=false, retries=0.\n')
        runner = Run(source, {}, apps, {'parallel': 1})
        result = runner.execute()
        self.assertEqual(result['status'], 'done')
        self.assertTrue(runner.kernel.env.lookup('choice').meta['contested'])
        self.assertTrue(any(row.get('status') == 'contested' for row in runner.trace))

    def test_semantic_identity_pins_vote_policy(self):
        self.assertEqual(S.kernel_id()['vote_policy'], 1)


if __name__ == '__main__':
    unittest.main()
