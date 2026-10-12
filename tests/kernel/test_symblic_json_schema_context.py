"""Real public request contexts; no hidden fixture, live provider or budget mutation."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from symblic.kernel import language as S
from symblic.kernel import json_schema as J
from symblic.mica import search as M
from symblic.mica import contracts as C
from symblic.mica import native as N
from symblic.mica import routing as R
from symblic.kernel.run import _flat
from tests.mica.test_symblic_mica_execution import ROUTE

FIXTURES = {'arithmetic_collections': 'ef34ddd8ebdc4d13d50f9f2d8b8c02ea863bfc09a0d1a03db485e0dc5dc9b394',
            'strict_json': 'bcf81d931f62196ca8497b856d19e154da7d24c49881947c61b670f66d136a26'}


def public(name):
    raw = (Path(__file__).parent / 'fixtures/mica_json_schema' / (name + '.public-request.json')).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURES[name]
    return json.loads(raw)


def compiled(req):
    prompt = M.plan_prompt(req)
    schema = M.proposal_schema(req)
    source = N.planner_source(prompt, ROUTE, context_chars=req['budget']['context_chars'], schema=schema)
    tree = S.parse(source)
    statements = list(_flat(tree['statements']))
    ask = next(row for row in statements if row.k == 'ask')
    args = (tree['name'], statements.index(ask) + 1, len(statements),
            S.statement_source('proposal', ask.type, prompt), ask.type, 'low', [], [])
    return source, args


class ContextDefault(unittest.TestCase):
    def test_only_omitted_new_request_context_uses_new_default(self):
        self.assertEqual(C.DEFAULT_BUDGET['context_chars'], 32768)
        for name in FIXTURES:
            original = public(name)
            self.assertEqual(C.normalize_request(original)['budget']['context_chars'], 40000)
            omitted = copy.deepcopy(original); omitted['budget'].pop('context_chars')
            self.assertEqual(C.normalize_request(omitted)['budget']['context_chars'], 32768)
            del omitted['budget']
            self.assertEqual(C.normalize_request(omitted)['budget']['context_chars'], 32768)
            for value in (24000, 40000):
                explicit = copy.deepcopy(original); explicit['budget']['context_chars'] = value
                frozen = C.normalize_request(explicit)
                self.assertEqual(C.normalize_request(frozen), frozen)
                self.assertEqual(frozen['budget']['context_chars'], value)

    def test_default_does_not_override_declared_worker_capacity(self):
        worker = {'engine': 'ollama', 'model': 'small', 'node': 'node-i',
                  'ready': True, 'available': True, 'context_chars': 24000}
        contract = {'model_eligibility': {}, 'resource_budget': C.normalize_request(public('strict_json'))['budget']}
        contract['resource_budget']['context_chars'] = C.DEFAULT_BUDGET['context_chars']
        self.assertEqual(R.rank_models(contract, [worker], []), [])
        contract['resource_budget']['context_chars'] = 24000
        self.assertEqual(len(R.rank_models(contract, [worker], [])), 1)

    def test_both_actual_public_task_capsules_fit_new_default_without_truncation(self):
        for name in FIXTURES:
            for artifact_format in ('javascript_script', 'javascript_modules'):
                with self.subTest(name=name, artifact_format=artifact_format):
                    raw = public(name); raw['budget'].pop('context_chars'); raw['artifact_format'] = artifact_format
                    req = C.normalize_request(raw)
                    _, args = compiled(req)
                    cap = S.capsule(*args, profile='verified', budget=req['budget']['context_chars'])
                    full = json.dumps(cap['schema'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                    self.assertEqual(cap['schema'], M.proposal_schema(req))
                    total = len(cap['system']) + len(cap['prompt']) + len(full)
                    self.assertLessEqual(total, 32768)
                    if artifact_format == 'javascript_modules':
                        self.assertGreater(total, 24000)
                    for requirement in req['requirements']:
                        self.assertIn(requirement['text'], cap['prompt'])

    def test_explicit_original_24000_remains_exhausted_before_any_dispatch(self):
        class NoApps:
            calls = 0
            def call(self, _):
                self.calls += 1
                raise AssertionError('An explicit exhausted allowance must not dispatch.')
        with tempfile.TemporaryDirectory(prefix='json-context-default-') as folder:
            for name in FIXTURES:
                with self.subTest(name=name):
                    raw = public(name); raw['budget']['context_chars'] = 24000; raw['artifact_format'] = 'javascript_modules'
                    req = C.normalize_request(raw)
                    source, args = compiled(req)
                    with self.assertRaises(S.SymblicError):
                        S.capsule(*args, profile='verified', budget=24000)
                    apps = NoApps()
                    result = N.execute(source, Path(folder) / name, apps, ROUTE, limit=1, output_binding='proposal')
                    self.assertEqual((result['status'], result['failure'], result['calls']),
                                     ('exhausted', 'RESOURCE_EXHAUSTION', 0))
                    self.assertEqual(apps.calls, 0)
                    self.assertEqual(req['budget']['context_chars'], 24000)


if __name__ == '__main__':
    unittest.main()
