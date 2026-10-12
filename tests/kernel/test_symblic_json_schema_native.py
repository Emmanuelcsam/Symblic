"""Actual native lifecycle with fake provider boundary and isolated stores."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from symblic.kernel import language as S
from symblic.kernel import execution_pins as X
from symblic.kernel import json_schema as J
from symblic.kernel import run as SR
from symblic.mica import search as M
from symblic.mica import native as N
from symblic.mica import project as P
from symblic.mica import proposal as Q
from tests.mica.test_symblic_mica_execution import inventory, request, proposal, ROUTE
from tests.kernel.test_symblic_json_schema import declared, obj


class RawApps:
    def __init__(self, answer):
        self.answer = answer
        self.requests = []
        self.lock = threading.Lock()

    def call(self, req):
        with self.lock:
            self.requests.append({k: copy.deepcopy(v) for k, v in req.items() if k != 'stop'})
            number = len(self.requests)
        value = self.answer(req, number)
        if isinstance(value, BaseException):
            raise value
        if type(value) is dict:
            return value
        return {'ok': True, 'text': value, 'model': req['app'].get('model', ''),
                'node': req['app'].get('node', ''), 'ms': 1}


def root_reply(objective='Implement public integer increment.'):
    req = request()
    for field in ('budget', 'version'):
        req.pop(field)
    for case in req['tests']:
        case['expected_value'] = json.loads(case.pop('expected'))
    req['objective'] = objective
    return {'proposal_version': 3, 'request': req,
            'objective_coverage': [{'clause_id': 'O001', 'requirement_ids': ['increment']}], 'missing_decisions': []}


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='json-schema-native-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'run'

    def test_exact_source_schema_reply_and_completed_replay(self):
        schema = obj({'answer': {}})
        raw = ' \r\n{"answer":0.100000000000000000000000000001}\r\n'
        source = N.planner_source('Return the declared document.', ROUTE, schema=schema)
        apps = RawApps(lambda req, n: raw)
        result = N.execute(source, self.root, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['output'], raw)
        self.assertEqual(apps.requests[0]['schema'], schema)
        self.assertEqual(N.execute(source, self.root, apps, ROUTE, limit=1, output_binding='proposal'), result)
        self.assertEqual(len(apps.requests), 1)
        pins = M._read(self.root, 'mica-native-pins.json')
        self.assertEqual(pins['source_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertIn('symblic/kernel/json_schema.py', pins['execution_pins']['python_hashes'])

    def test_unknown_does_not_replay_or_allow_changed_schema(self):
        apps = RawApps(lambda req, n: RuntimeError('fixture lost acknowledgement'))
        source = N.planner_source('Return JSON.', ROUTE, schema=obj({'x': {'type': 'string'}}))
        first = N.execute(source, self.root, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(first['status'], 'unknown', first)
        self.assertEqual(N.execute(source, self.root, apps, ROUTE, limit=1, output_binding='proposal')['status'], 'unknown')
        changed = N.planner_source('Return JSON.', ROUTE, schema=obj({'x': {'type': 'integer'}}))
        with self.assertRaises((N.NativeError, ValueError)):
            N.execute(changed, self.root, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(len(apps.requests), 1)

    def test_context_counts_full_schema_and_refuses_before_dispatch(self):
        schema = obj({'x': {'type': 'string'}})
        source = N.planner_source('Return JSON.', ROUTE, schema=schema, context_chars=256)
        apps = RawApps(lambda req, n: self.fail('context overflow must not dispatch'))
        result = N.execute(source, self.root, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(result['status'], 'exhausted', result)
        self.assertEqual(result['failure'], 'RESOURCE_EXHAUSTION')
        self.assertEqual(len(apps.requests), 0)

    def test_only_raw_reply_text_admitted(self):
        apps = RawApps(lambda req, n: {'ok': True, 'json': {'answer': '{}'}, 'model': ROUTE['model'], 'node': ROUTE['node']})
        result = N.execute(N.planner_source('Return JSON.', ROUTE, schema={}), self.root, apps, ROUTE,
                           limit=1, output_binding='proposal')
        self.assertEqual(result['status'], 'failed', result)
        self.assertIsNone(result['output'])

    def test_resource_validation_is_ungraded_without_retry(self):
        apps = RawApps(lambda req, n: '{"x":1}')
        source = N.planner_source('Return JSON.', ROUTE, schema=obj({'x': {'type': 'integer'}}))
        source = source.replace('retries=0', 'retries=2')
        with mock.patch.object(J, 'MAX_STEPS', 0):
            result = N.execute(source, self.root, apps, ROUTE, limit=3, output_binding='proposal')
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(result['failure'], 'VERIFICATION_UNKNOWN')
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(result['calls'], 1)

    def test_vote_search_escalation_and_repairs_use_same_declared_schema(self):
        schema = obj({'x': {'type': 'integer'}})
        label = S.type_label(declared(schema))
        for route in ('vote', 'search', 'escalate'):
            source = ('use profile=verified, context=none.\n' +
                      'ask answer: ' + label + ' "Return x one." by ["fake:a", "fake:b"] with effort=low, retries=1, route=' + route +
                      (', samples=1, rounds=1' if route == 'search' else '') + '.\n' + ('ensure len(answer) > 0 else retry.\n' if route in ('search', 'escalate') else '') + 'show answer.\n')
            apps = RawApps(lambda req, n: '{"x":true}' if n == 1 else '{"x":1}')
            run = SR.Run(source, applicators=apps, folder=str(self.root / route), options={'parallel': 1})
            report = run.execute()
            self.assertEqual(report['status'], 'done', (route, report))
            self.assertGreaterEqual(len(apps.requests), 2)
            for req in apps.requests:
                self.assertEqual(req['schema'], schema)
                self.assertNotIn('whole code in one fenced block', req['prompt'])
            self.assertTrue(any('raw JSON document' in req['prompt'] for req in apps.requests[1:]))

    def test_schema_changes_call_identity(self):
        args = ({'engine': 'fake', 'model': 'a'}, 'system', 'prompt')
        one = SR.call_key(*args, {'type': 'string'}, 1, 0, 7)
        two = SR.call_key(*args, {'type': 'integer'}, 1, 0, 7)
        self.assertNotEqual(one, two)

    def test_native_project_and_graph_execute_and_reopen(self):
        def answer(req, n):
            if 'missing_decisions' in req['prompt']:
                return json.dumps(root_reply())
            if 'output_format' in req['prompt']:
                return json.dumps(proposal())
            return 'function inc(x) { return x + 1; }'
        apps = RawApps(answer)
        project = P.MicaProject('Implement public integer increment.', self.root, apps, inventory(),
            {'max_calls': 3, 'max_candidates': 2, 'retries': 0, 'wall_seconds': 120}, ['result.js'])
        planned = project.plan()
        self.assertEqual(planned['status'], 'planned', planned)
        self.assertEqual(planned['calls'], 2)
        self.assertIsNotNone(apps.requests[0]['schema'])
        self.assertIsNotNone(apps.requests[1]['schema'])
        result = project.execute()
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['proposal_encoding']['proposal_version'], 3)
        self.assertEqual(P.read_project_result(self.root), result)
        self.assertEqual(project.execute(), result)
        self.assertEqual(len(apps.requests), 3)

    def test_valid_shape_cannot_change_owner_objective(self):
        bad = root_reply('Implement a different problem.')
        J.validate(json.dumps(bad), P.root_proposal_schema())
        apps = RawApps(lambda req, n: json.dumps(bad))
        project = P.MicaProject('Implement public integer increment.', self.root, apps, inventory(),
            {'max_calls': 2, 'max_candidates': 1, 'retries': 0, 'wall_seconds': 60}, ['result.js'])
        result = project.execute('direct')
        self.assertNotEqual(result['status'], 'done')
        self.assertEqual(result['last_failure']['failure'], 'INVALID_ROOT_REQUEST')
        self.assertEqual(len(apps.requests), 1)

    def test_root_expected_number_text_reaches_encoding_without_float_roundtrip(self):
        raw = json.dumps(root_reply()).replace('"expected_value": 3', '"expected_value": 0.100000000000000000000000000001')
        apps = RawApps(lambda req, n: raw)
        source = N.planner_source('Return a root proposal.', ROUTE, schema=P.root_proposal_schema())
        result = N.execute(source, self.root, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(result['status'], 'done', result)
        decoded, receipt = Q.decode(result['output'])
        self.assertEqual(decoded['request']['tests'][0]['expected'], '0.100000000000000000000000000001')
        self.assertEqual(receipt['raw_proposal_sha256'], hashlib.sha256(raw.encode()).hexdigest())


if __name__ == '__main__':
    unittest.main()
