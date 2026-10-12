"""Forge source through the original host's MICA HTTP API job lifecycle (integration/host), isolated host adapters.

Skipped when integration.host.symblic_mica_api cannot be imported here.
"""
import copy
from pathlib import Path
from unittest import mock
try:
    from integration.host import symblic_mica_api as A
except Exception as exc:  # noqa: BLE001  (any import failure means the host API cannot be exercised)
    import unittest as _unittest
    raise _unittest.SkipTest(f'integration.host.symblic_mica_api is unavailable outside the original host: '
                             f'{type(exc).__name__}: {exc}')
from symblic.mica import forge as F
from symblic.mica import routing as R
from tests.integration import test_symblic_mica_api as base
result, request, INVENTORY, RUNTIME = base.result, base.request, base.INVENTORY, base.RUNTIME


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture(fleet=True)


class ForgeApiTests(base.ApiTests):
    def setUp(self):
        super().setUp()
        self.prepared = A.G._seal({'request':request(), 'plan':{'contracts':[]},
                                  'origin':{'identity':{'adapter':'fixture'},'project':'project-fixture','handoff':'handoff-fixture'}})
        self.forge_calls=[]
        for patcher in (mock.patch.object(F,'prepare',return_value=self.prepared),
                        mock.patch.object(A,'_forge_store',return_value=object()),
                        mock.patch.object(A,'_implementation',return_value={'isolated_fixture':1,'construction':RUNTIME,
                                                                          'forge_adapter':self.prepared['origin']['identity']})):
            patcher.start();self.addCleanup(patcher.stop)

    def forge_body(self, **updates):
        return {'forge':{'project':'project-fixture','handoff':'handoff-fixture','binding':{'version':1}},
                'inventory':copy.deepcopy(INVENTORY),'idempotency_key':'api-forge-fixture',**updates}

    def launch(self,ident,folder,generation):
        self.launches.append((ident,folder,generation))
        A.run_job(folder,applicators=object(),generation=generation,runtime_factory=self.factory,
                  project_factory=self.project_factory,forge_factory=self.forge_factory)
        return {'ok':True}

    def forge_factory(self,prepared,folder,apps,inventory,*,db,request_id,stop):
        outer=self
        class Run:
            def result(self,action):
                outer.forge_calls.append((action,prepared,str(folder),inventory,request_id))
                return {**result('planned' if action=='plan' else outer.next_status),
                        'forge_origin':F._origin_record(prepared,folder,inventory,request_id),
                        'semantic_completeness':'unassessed','scope':F.SCOPE}
            def plan(self): return self.result('plan')
            def execute(self): return self.result('execute')
        return Run()

    def test_forge_owner_gate_precedes_preparation_or_store(self):
        with mock.patch.object(A,'_forge_store',side_effect=AssertionError('store forbidden')):
            self.assertEqual(self.invoke('mica/check',method='POST',body=self.forge_body(),owner=False)[0],403)
            self.assertEqual(self.invoke('mica/plan',method='POST',body=self.forge_body(),owner=False)[0],403)
        self.assertEqual(self.forge_calls,[])

    def test_forge_fixed_plan_execute_and_lost_reply_are_idempotent(self):
        body=self.forge_body();checked=A.check(body)
        self.assertEqual(checked['spec']['task']['request'],self.prepared['request'])
        body['expected_sha256']=checked['sha256']
        ident=A.start(body,action='plan')['id']
        self.assertTrue(A.start(body,action='plan')['existing'])
        self.assertEqual(len(self.forge_calls),1)
        self.assertTrue(A.view(ident)['can_execute'])
        A.resume(ident,execute=True)
        self.assertEqual(A.view(ident)['status'],'done')
        self.assertEqual([c[0] for c in self.forge_calls],['plan','execute'])
        self.assertEqual(self.forge_calls[0][1:],self.forge_calls[1][1:])
        self.assertEqual(self.forge_calls[0][-1],'mica-'+ident)
        self.assertTrue(A.resume(ident)['terminal'])
        self.assertEqual(len(self.forge_calls),2)
        self.assertEqual(A.artifacts(ident,include_text=True)['artifacts'][0]['file'],'result.js')

    def test_forge_exact_fields_and_no_runtime_override(self):
        invalid=[{'request':request()},{'objective':'extra'},{'budget':request()['budget']},
                 {'artifact_format':'javascript_modules'},{'allowed_outputs':['other.js']},
                 {'calibration':{}},{'reuse_components':True},{'mode':'direct'},
                 {'folder':'/tmp/untrusted'}, {'forge':{'project':'project-fixture','handoff':'handoff-fixture','binding':{},'folder':'/tmp'}}]
        for change in invalid:
            with self.subTest(change=change),self.assertRaises(ValueError):A.check(self.forge_body(**change))
        self.assertEqual(self.forge_calls,[])

    def test_forge_origin_tamper_prevents_artifact_read(self):
        ident=A.start(self.forge_body())['id'];current=A.view(ident)
        current['result']['forge_origin']['request_id']='other-request'
        with mock.patch.object(A,'view',return_value=current):
            with self.assertRaisesRegex(ValueError,'origin'):
                A.artifacts(ident,include_text=True)

    def test_forge_unknown_delivery_remains_blocked_on_reconnect(self):
        self.next_status='unknown';ident=A.start(self.forge_body())['id']
        for _ in range(2):
            self.assertEqual(A.view(ident)['status'],'unknown')
            self.assertTrue(A.resume(ident,execute=True)['terminal'])
        self.assertEqual(len(self.forge_calls),1)

    def test_forge_worker_identity_mismatch_prevents_adapter_entry(self):
        held=[]
        with mock.patch.dict(A.launcher,{'launch':lambda i,f,g:held.append((i,f,g)) or {'ok':True}}):
            A.start(self.forge_body())
        ident,folder,generation=held[0]
        with mock.patch.object(A,'_implementation',return_value={'construction':RUNTIME,'forge_adapter':{'changed':True}}):
            with self.assertRaisesRegex(ValueError,'implementation changed'):
                A.run_job(folder,applicators=object(),generation=generation,forge_factory=self.forge_factory)
        self.assertEqual(self.forge_calls,[])
