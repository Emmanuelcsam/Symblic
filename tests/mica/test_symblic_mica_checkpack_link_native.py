"""Actual native MICA construction and existing hidden grader with pinned linkage."""
import json
from pathlib import Path
import tempfile
import unittest

from symblic.mica import search as M
from symblic.mica import bench as B
from symblic.mica import checkpack as K
from symblic.mica import checkpack_link as H
from tests.mica.test_symblic_mica_checkpack import request, declaration, SENTINEL
from tests.mica.test_symblic_mica_execution import FakeApps, inventory


class LinkedNativeTest(unittest.TestCase):
    def test_linked_freeze_native_construction_hidden_grade_replay_without_exposure(self):
        pack = K.freeze(request(), declaration(), B.js_evaluator_identity())
        fixture = H.linked_fixture(pack, expected_sha256=pack['sha256'])
        model = {'primary':['fixture-small'],'fallback':[],'stronger_fallback':[],'settings':{'temperature':0}}
        apps = FakeApps(lambda req,n:'function encode(value){return value;} function decode(value){return value;}')
        seen = []
        with tempfile.TemporaryDirectory(prefix='mica-linked-native-') as temp:
            path = Path(temp)
            bench = B.MicaBenchmark.freeze(path/'bench','linked',[fixture],model=model,
                budget=fixture['request']['budget'],evaluator_identity=pack['checker_identity'])
            selected = next(row for row in bench.assignments() if row['arm_id']=='direct')
            def runner(**kwargs):
                seen.append(kwargs)
                return M.MicaRun(kwargs['request'],path/'run',apps,inventory(('node-e',))).execute(mode=kwargs['mode'])
            first = bench.run_assignment(selected['id'],runner)
            self.assertEqual(first['status'],'done',first)
            self.assertTrue(first['grade']['passed'],first)
            self.assertEqual(first['runner']['calls'],1)
            self.assertEqual(bench.run_assignment(selected['id'],runner),first)
            self.assertEqual((len(seen),len(apps.requests)),(1,1))
            self.assertNotIn(SENTINEL,json.dumps(seen))
            self.assertNotIn(SENTINEL,json.dumps(apps.requests))
            self.assertNotIn('checkpack',json.dumps(seen))
            report = bench.report()
            self.assertEqual(report['checkpack_provenance'][0]['pack_sha256'],pack['sha256'])
            self.assertNotIn(SENTINEL,json.dumps(report))
            self.assertIn('unassessed',report['checkpack_provenance'][0]['scope'])


if __name__=='__main__':
    unittest.main()
