"""Owner routing and finite experiment HTTP boundaries (integration/host/symblic_experiments_api.py); no real
stores/providers. Runs without the host, except the routing test, which needs the host's router and skips."""
import json
from unittest.mock import patch

from integration.host import symblic_engine as Engine
from symblic.experiments import registry as E
from integration.host import symblic_experiments_api as A
from tests.integration.test_symblic_engine import Base, Handler
from tests.integration import fake_host_apps


class ExperimentAPI(Base):
    def test_non_owner_refused_before_module_load(self):
        host_apps = fake_host_apps.router(self)
        for method, suffix in [('GET','catalog'),('POST','run'),('POST','verify')]:
            handler=Handler()
            handler.path='/api/automation/symblic/experiments/'+suffix
            def deny(_,handler=handler):
                handler.send_json({'error':'Owner only.'},403)
                return False
            handler.require_owner=deny
            with patch.object(host_apps,'_module_for',side_effect=AssertionError('Denied before import')):
                self.assertTrue(host_apps.handle_get(handler) if method=='GET' else host_apps.handle_post(handler,{}))
            self.assertEqual(handler.status,403)

    def request(self,method,route,data=None):
        h=Handler()
        self.assertTrue(A.handle(h,method,route,data))
        self.assertEqual(self.launches,[])
        self.assertEqual(self.apps.calls,[])
        return h

    def test_catalog_run_verify_and_engine_dispatch(self):
        self.assertTrue(callable(Engine.handle))
        catalog=self.call('GET','experiments/catalog').sent
        entry=next(x for x in catalog['experiments'] if x['id']=='circuit_rewrite')
        reply=self.call('POST','experiments/run',{'experiment':entry['id'],'input_json':json.dumps(entry['example'])})
        self.assertEqual(reply.status,200,reply.sent)
        self.assertTrue(reply.sent['output']['results']['equivalent_channels'])
        result=self.call('POST','experiments/verify',{'receipt_json':json.dumps(reply.sent)})
        self.assertEqual(result.status,200,result.sent)
        self.assertTrue(result.sent['ok'])
        self.assertEqual(self.launches,[])
        self.assertEqual(self.apps.calls,[])

    def test_malformed_body_and_raw_json_refuse(self):
        for body in [None,[],{}, {'experiment':'circuit_rewrite','input_json':{}},
                     {'experiment':'circuit_rewrite','input_json':'{}','execute':True},
                     {'experiment':'circuit_rewrite','input_json':'{"qubits":1,"qubits":2}'},
                     {'experiment':'circuit_rewrite','input_json':'[0.5]'},
                     {'experiment':'circuit_rewrite','input_json':'x'*(E.MAX_BYTES+1)}]:
            with self.subTest(body=str(body)[:80]):
                reply=self.request('POST','experiments/run',body)
                self.assertEqual(reply.status,400,reply.sent)

    def test_unknown_actions_refuse_and_output_not_echoed(self):
        for verb,route in [('GET','experiments/run'),('DELETE','experiments/catalog'),('POST','experiments/launch')]:
            self.assertEqual(self.request(verb,route,{}).status,404)
        self.assertFalse(A.handle(Handler(),'GET','other',{}))
        reply=self.request('POST','experiments/run',{'experiment':'private-secret-title','input_json':'{}'})
        self.assertNotIn('private-secret-title',json.dumps(reply.sent))
        self.assertEqual(reply.status,400)
