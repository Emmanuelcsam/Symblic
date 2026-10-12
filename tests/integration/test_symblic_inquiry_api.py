"""Pure inquiry HTTP contract (integration/host/symblic_inquiry_api.py) and owner-routed engine integration, without
stores. Runs without the host, except the routing test, which needs the host's application router and skips."""
import json
from unittest.mock import patch

from integration.host import symblic_engine as E
from symblic.inquiry import selection as I
from integration.host import symblic_inquiry_api as A
from tests.integration.test_symblic_engine import Base, Handler
from tests.integration import fake_host_apps


class InquiryAPI(Base):
    def test_dispatch_denies_non_owner_before_loading_inquiry(self):
        host_apps = fake_host_apps.router(self)
        for method, suffix in (('GET', 'example'), ('POST', 'plan')):
            handler = Handler()
            handler.path = '/api/automation/symblic/inquiry/' + suffix
            def deny(_, handler=handler):
                handler.send_json({'error': 'Owner only.'}, 403)
                return False
            handler.require_owner = deny
            with patch.object(host_apps, '_module_for', side_effect=AssertionError('Denied before import')):
                handled = (host_apps.handle_get(handler) if method == 'GET'
                           else host_apps.handle_post(handler, {'assessment': I.example()}))
            self.assertTrue(handled)
            self.assertEqual(handler.status, 403)

    def request(self, method, route, body=None):
        handler = Handler()
        self.assertTrue(A.handle(handler, method, route, body))
        self.assertEqual(self.launches, [])
        self.assertEqual(self.apps.calls, [])
        return handler

    def test_example_and_both_request_forms_return_same_plan(self):
        example = self.request('GET', 'inquiry/example')
        self.assertEqual(example.status, 200)
        self.assertEqual(example.sent['kind'], 'synthetic_fixture')
        data = example.sent['assessment']
        with patch.object(E, 'start_run', side_effect=AssertionError('No execution')):
            for body in ({'assessment': data}, {'assessment_json': json.dumps(data)}):
                reply = self.request('POST', 'inquiry/plan', body)
                self.assertEqual(reply.status, 200, reply.sent)
                self.assertEqual(reply.sent, I.plan(data))
                self.assertFalse(reply.sent['authorizes_execution'])

    def test_unknown_fields_actions_verbs_and_non_object_inputs_refuse(self):
        for body in (None, [], '', 3, True, {}, {'assessment': I.example(), 'execute': True},
                     {'assessment': I.example(), 'assessment_json': '{}'},
                     {'assessment_json': {}}, {'assessment': {'unknown': True}}):
            reply = self.request('POST', 'inquiry/plan', body)
            self.assertEqual(reply.status, 400, reply.sent)
        for method, route in (('GET', 'inquiry/plan'), ('POST', 'inquiry/example'),
                              ('POST', 'inquiry/run'), ('DELETE', 'inquiry/plan')):
            reply = self.request(method, route, {})
            self.assertEqual(reply.status, 404)
        self.assertFalse(A.handle(Handler(), 'GET', 'other/example', None))

    def test_raw_duplicates_floats_bounds_and_stale_scope_refuse_without_input_echo(self):
        for raw in ('{"x":1,"x":2}', '{"cost":1.25}', ' ' * (I.MAX_BYTES + 1)):
            reply = self.request('POST', 'inquiry/plan', {'assessment_json': raw})
            self.assertEqual(reply.status, 400)
            self.assertFalse(reply.sent['ok'])
        data = I.example()
        data['receipts'][0]['scope_sha256'] = I.digest('old')
        reply = self.request('POST', 'inquiry/plan', {'assessment': data})
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.sent['detail']['code'], 'stale_scope_receipt')
        self.assertNotIn(data['receipts'][0]['scope_sha256'], json.dumps(reply.sent))

    def test_engine_routes_example_plan_unknown_and_refused_inputs(self):
        example = self.call('GET', 'inquiry/example')
        self.assertEqual(example.status, 200, example.sent)
        reply = self.call('POST', 'inquiry/plan', {'assessment': example.sent['assessment']})
        self.assertEqual(reply.status, 200, reply.sent)
        self.assertEqual(reply.sent['recommendation']['method_id'], 'b-total')
        self.assertEqual(self.call('POST', 'inquiry/plan', {'unknown': True}).status, 400)
        self.assertEqual(self.call('POST', 'inquiry/execute', {}).status, 404)
        self.assertEqual(self.launches, [])
        self.assertEqual(self.apps.calls, [])
