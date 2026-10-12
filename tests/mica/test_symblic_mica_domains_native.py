"""Frozen generated checks through the existing native builder and hidden grader."""
import json
from pathlib import Path
import tempfile
import unittest

from symblic.mica import search as M
from symblic.mica import bench as B
from symblic.mica import checkpack as K
from symblic.mica import checkpack_link as L
from tests.mica.test_symblic_mica_domains import request, declaration, SENTINEL
from tests.mica.test_symblic_mica_execution import FakeApps, inventory


class DomainNative(unittest.TestCase):
    def test_extra_frozen_cases_reject_example_only_answer_then_repair_without_hidden_leak(self):
        req = request()
        pack = K.freeze(req, declaration(req), B.js_evaluator_identity())
        fixture = L.linked_fixture(pack, expected_sha256=pack['sha256'])
        model = {'primary': ['fixture-small'], 'fallback': [], 'stronger_fallback': [],
                 'settings': {'temperature': 0}}
        wrong = 'function encode(value){return value;} function decode(value){return 7;}'
        right = 'function encode(value){return value;} function decode(value){return value;}'
        apps = FakeApps(lambda call, number: wrong if number == 1 else right)
        seen = []
        with tempfile.TemporaryDirectory(prefix='mica-domains-native-') as temp:
            root = Path(temp)
            bench = B.MicaBenchmark.freeze(root / 'bench', 'domain-cases', [fixture], model=model,
                budget=fixture['request']['budget'], evaluator_identity=pack['checker_identity'])
            assignment = next(row for row in bench.assignments() if row['arm_id'] == 'direct')
            def runner(**kwargs):
                seen.append(kwargs)
                self.assertEqual(kwargs['request']['tests'][:len(req['tests'])], req['tests'])
                return M.MicaRun(kwargs['request'], root / 'run', apps, inventory(('node-e',))).execute(mode=kwargs['mode'])
            first = bench.run_assignment(assignment['id'], runner)
            self.assertEqual(first['status'], 'done', first)
            self.assertEqual(first['runner']['calls'], 2, first)
            self.assertTrue(first['grade']['passed'], first)
            self.assertEqual(len(apps.requests), 2)
            self.assertIn('40 of 41 examples failed', apps.requests[1]['prompt'])
            self.assertIn('decode(encode(', apps.requests[1]['prompt'])
            self.assertNotIn(SENTINEL, json.dumps(apps.requests))
            self.assertNotIn(SENTINEL, json.dumps(seen))
            self.assertEqual(bench.run_assignment(assignment['id'], runner), first)
            self.assertEqual((len(apps.requests), len(seen)), (2, 1))
            report = bench.report()
            self.assertEqual(report['checkpack_provenance'][0]['pack_sha256'], pack['sha256'])
            self.assertIn('symblic/mica/domains.py', report['checkpack_provenance'][0]['implementation']['generator']['sources'])
            self.assertNotIn(SENTINEL, json.dumps(report))


if __name__ == '__main__':
    unittest.main()
