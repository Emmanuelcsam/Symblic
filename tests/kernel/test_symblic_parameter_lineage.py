"""Parameter values retain caller provenance without inventing premise roots.

Only injected responses and in-memory Run objects; no stores or real providers.
"""
import threading
import unittest

from symblic.kernel import epistemic as EP
from symblic.kernel import run as R


class Replies:
    def __init__(self, *values):
        self.values, self.requests, self.lock = values, [], threading.Lock()

    def call(self, request):
        with self.lock:
            index = len(self.requests)
            self.requests.append(request)
        if not self.values:
            raise AssertionError('This program must make no provider call')
        return {'ok': True, 'json': {'answer': self.values[min(index, len(self.values) - 1)]},
                'model': 'fake', 'node': 'isolated'}


def execute(source, *values, **options):
    apps = Replies(*values)
    run = R.Run(source, applicators=apps, options={'by': 'fake:constructor', **options})
    return run, run.execute(), apps


def envelope(run, name):
    return run.kernel.env.lookup(name).meta['epistemic']


class ParameterLineage(unittest.TestCase):
    def checked(self, source, *values, **options):
        run, report, apps = execute(source, *values, **options)
        self.assertEqual(report['status'], 'done', report.get('error'))
        claims = report['epistemic']['claims']
        self.assertEqual([claim['content'].get('name') for claim in claims
                          if claim['origin'] == 'assumption'], [], 'Parameters must not mint assumptions')
        expected = EP.evaluate(claims)
        actual = envelope(run, 'result')['assessment']
        self.assertEqual({key: actual[key] for key in expected[actual['id']]}, expected[actual['id']])
        return run, report, apps

    def test_function_argument_keeps_model_root_without_parameter_assumption(self):
        run, _, apps = self.checked('ask x: Int "number" with effort=low\n'
                                   'function twice(n: Int) -> Int = n * 2.\n'
                                   'let result = twice(x).\n', 4, profile='verified')
        roots = envelope(run, 'result')['assessment']['conditional_on']
        self.assertEqual([row['ref']['id'] for row in roots], [envelope(run, 'x')['claim']['id']])
        self.assertEqual(len(apps.requests), 1)

    def test_routine_literal_is_derived_without_any_external_premise(self):
        run, _, apps = self.checked('routine twice(n: Int) -> Int do\nreturn n * 2.\nend\n'
                                   'let result = twice(3).\n', profile='verified')
        self.assertEqual(run.kernel.env.lookup('result').value, 6)
        self.assertEqual(envelope(run, 'result')['assessment']['conditional_on'], [])
        self.assertEqual(apps.requests, [])

    def test_routine_and_memo_keep_original_argument_root(self):
        run, _, apps = self.checked('ask x: Int "number" with effort=low\n'
                                   'routine twice(n: Int) -> Int do\nreturn n * 2.\nend\n'
                                   'let initial_result = twice(x).\nlet result = twice(x).\n', 4, profile='verified')
        roots = envelope(run, 'result')['assessment']['conditional_on']
        self.assertEqual(roots, envelope(run, 'initial_result')['assessment']['conditional_on'])
        self.assertEqual([row['ref']['id'] for row in roots], [envelope(run, 'x')['claim']['id']])
        self.assertEqual(len(apps.requests), 1)

    def test_explicit_parameter_context_derives_from_original_argument(self):
        run, report, apps = self.checked('ask x: Int "number" with effort=low\n'
                                        'routine obtain(n: Int) -> Int do\n'
                                        'ask z: Int "Use the parameter" from n with effort=low\n'
                                        'return z.\nend\nlet result = obtain(x).\n', 4, 5, profile='verified')
        parameters = [c for c in report['epistemic']['claims'] if c['content'].get('name') == 'n']
        self.assertEqual(len(parameters), 1)
        self.assertEqual(parameters[0]['origin'], 'derived')
        roots = envelope(run, 'result')['assessment']['conditional_on']
        self.assertIn(envelope(run, 'x')['claim']['id'], [r['ref']['id'] for r in roots])
        self.assertEqual(len(apps.requests), 2)
        self.assertIn('model_proposal', apps.requests[-1]['prompt'])

    def test_contested_argument_remains_inadmissible_through_routine(self):
        run, _, _ = self.checked('ask x: Int "number" with votes=2, strict=false, effort=low\n'
                                 'routine twice(n: Int) -> Int do\nreturn n * 2.\nend\n'
                                 'let result = twice(x).\n', 4, 5, profile='legacy')
        view = envelope(run, 'result')['assessment']
        self.assertFalse(view['admissible'])
        self.assertIn('contested', [row['status'] for row in view['conditional_on']])


if __name__ == '__main__':
    unittest.main()
