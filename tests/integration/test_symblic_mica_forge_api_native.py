"""The original host's owner API -> real Forge/core/module checker; fake provider only.

Skipped when integration.host.symblic_mica_api cannot be imported here.
"""
import unittest
from unittest import mock
try:
    from integration.host import symblic_mica_api as A
except Exception as exc:  # noqa: BLE001  (any import failure means the host API cannot be exercised)
    import unittest as _unittest
    raise _unittest.SkipTest(f'integration.host.symblic_mica_api is unavailable outside the original host: '
                             f'{type(exc).__name__}: {exc}')
from tests.mica import test_symblic_mica_forge_native as native
from tests.mica.test_symblic_mica_execution import FakeApps


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture(fleet=True)


class NativeApiJourneys(unittest.TestCase):
    prepare=native.NativeForgeJourneys.prepare
    correct=staticmethod(native.NativeForgeJourneys.correct)

    def setUp(self):
        native.NativeForgeJourneys.setUp(self)
        for patcher in (mock.patch.dict('os.environ',{'AUTOMATION_DATA_DIR':str(self.root/'automation')}),
                        mock.patch.object(A,'_host_ok',return_value=True),
                        mock.patch.object(A,'_forge_store',return_value=self.db),
                        mock.patch.object(A,'launcher',{'launch':self.launch,'active':lambda _:False,'stop':lambda _:True})):
            patcher.start();self.addCleanup(patcher.stop)
        self.launches=[]

    def launch(self,ident,folder,generation):
        self.launches.append(ident)
        A.run_job(folder,applicators=self.apps,generation=generation)
        return {'ok':True}

    def body(self,prepared):
        return {'forge':{'project':self.project_id,'handoff':self.handoff_id,'binding':prepared['binding']},
                'inventory':self.inv,'mode':'mica','idempotency_key':'complete-forge-api'}

    def test_module_plan_execute_reconnect_and_download_keep_original_two_calls(self):
        prepared=self.prepare(modules=True);self.apps=FakeApps(self.correct);body=self.body(prepared)
        checked=A.check(body);body['expected_sha256']=checked['sha256']
        ident=A.start(body,action='plan')['id']
        self.assertEqual(A.view(ident)['status'],'planned')
        self.assertEqual(self.apps.requests,[])
        self.assertTrue(A.start(body,action='plan')['existing'])
        self.assertEqual(len(self.launches),1)
        A.resume(ident,execute=True)
        current=A.view(ident)
        self.assertEqual(current['status'],'done',current)
        self.assertEqual(current['result']['calls'],2)
        self.assertEqual(len(self.apps.requests),2)
        artifact=A.artifacts(ident,include_text=True,include_archive=True)
        self.assertEqual(len(artifact['artifacts']),3)
        self.assertGreater(artifact['archive']['bytes'],100)
        self.assertTrue(A.resume(ident,execute=True)['terminal'])
        self.assertEqual(len(self.apps.requests),2)
        self.assertEqual(len(self.launches),2)

    def test_unresolved_native_api_call_is_retained_and_not_resumed(self):
        prepared=self.prepare();self.apps=FakeApps(lambda req,n:RuntimeError('lost acknowledgement'))
        ident=A.start(self.body(prepared))['id']
        current=A.view(ident)
        self.assertEqual(current['status'],'unknown',current)
        self.assertEqual(current['result']['calls'],1)
        self.assertFalse(current['can_resume'])
        self.assertTrue(A.resume(ident,execute=True)['terminal'])
        self.assertEqual(A.artifacts(ident)['artifacts'],[])
        self.assertEqual(len(self.apps.requests),1)
        self.assertEqual(len(self.launches),1)
