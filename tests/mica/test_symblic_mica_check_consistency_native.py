"""Native planner admission/refeedback journey; fake providers, private stores."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from symblic.mica import search as M
from tests.mica.test_symblic_mica_execution import FakeApps, inventory


class ConsistencyNativeTest(unittest.TestCase):
    def test_wrong_public_oracle_is_rejected_before_worker_then_corrected_plan_executes(self):
        request = {'objective': 'Implement sum and clamp as pure functions.',
            'requirements': [{'id': 'arithmetic', 'text': 'Sum numbers and clamp a number between its bounds.', 'acceptance': 'TESTED'}],
            'exports': [{'name': 'sum', 'signature': 'sum(values)'}, {'name': 'clamp', 'signature': 'clamp(x,lo,hi)'}],
            'tests': [{'requirement_ids': ['arithmetic'], 'call': 'sum([1,2,3])', 'expected': '6'},
                      {'requirement_ids': ['arithmetic'], 'call': 'clamp(12,0,10)', 'expected': '10'}],
            'allowed_outputs': ['result.js'],
            'budget': {'max_calls': 4, 'max_candidates': 2, 'max_units': 2, 'max_workers': 1,
                       'retries': 0, 'wall_seconds': 120, 'context_chars': 24000}}
        corrected = {'assumptions': [], 'units': [
            {'id': 'total', 'names': ['sum'], 'heading': 'sum(values)', 'body': 'Return the sum of the numeric array.',
             'uses': [], 'requirements': ['arithmetic'], 'examples': [['sum([1,2,3])', '6']]},
            {'id': 'bounds', 'names': ['clamp'], 'heading': 'clamp(x,lo,hi)', 'body': 'Clamp x to the inclusive bounds lo and hi.',
             'uses': [], 'requirements': ['arithmetic'], 'examples': [['clamp(12, 0, 10)', '10']]}]}
        wrong = copy.deepcopy(corrected)
        wrong['units'][0]['examples'][0][1] = '{"result":6}'
        wrong['units'][1]['examples'][0][1] = '{"result":"10"}'
        planners, workers = [], []
        def provider(req, number):
            if 'output_format' in req['prompt']:
                planners.append(req['prompt'])
                self.assertEqual(workers, [], 'No worker may be called for a contradictory proposal.')
                if len(planners) == 1:
                    return json.dumps(wrong)
                self.assertIn('INVALID_CONTRACT', req['prompt'])
                self.assertIn('original root test 0', req['prompt'])
                self.assertIn('Original expected JSON: 6', req['prompt'])
                return json.dumps(corrected)
            workers.append(req['prompt'])
            return ('function sum(values) { return values.reduce((a,b)=>a+b,0); }' if 'sum(values)' in req['prompt']
                    else 'function clamp(x,lo,hi) { return Math.min(hi,Math.max(lo,x)); }')
        apps = FakeApps(provider)
        with tempfile.TemporaryDirectory(prefix='mica-consistency-native-') as temp:
            folder = Path(temp)/'run'
            result = M.MicaRun(request, folder, apps, inventory(('node-e',))).execute(mode='mica')
            self.assertEqual(result['status'], 'done', result)
            self.assertEqual(result['calls'], 4)
            self.assertEqual((len(planners), len(workers)), (2, 2))
            self.assertEqual(result['attempts'][0]['failure'], 'INVALID_CONTRACT')
            first = M._read(folder, 'branch-000.json')
            self.assertIsNone(first['plan'])
            self.assertEqual(first['result']['failure'], 'INVALID_CONTRACT')
            accepted = M._read(folder, 'branch-001.json')['plan']
            self.assertEqual(accepted['root_tests'], request['tests'])
            again = M.MicaRun(request, folder, apps, inventory(('node-e',))).execute(mode='mica')
            self.assertEqual(again, result)
            self.assertEqual(len(apps.requests), 4)


if __name__ == '__main__':
    unittest.main()
