"""Composition routes of the original host: `graph/compose` and `graph/composition-example` HTTP API.

These cases drive integration/host/symblic_engine.py and integration/host/symblic_graph_api.py with the fake store
in fake_host_apps.py standing in for the host's run store, so they run without the host. The command line and the
expander itself are tested in tests/graph/test_symblic_graph_compose_entry.py and test_symblic_graph_compose.py.
"""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
    from integration.host import symblic_graph_api as A
    from tests.integration.test_symblic_graph_api import Apps, Handler
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

from symblic.graph import compose as C
from symblic.js import check as JS

ROOT = Path(__file__).resolve().parents[2]


from tests.integration import fake_host_apps  # noqa: E402

# The host's store, faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class ComposeEntry(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.enter(patch.dict(os.environ, {'AUTOMATION_DATA_DIR': str(self.folder), 'DASHBOARD_DIR': str(ROOT)}))
        self.enter(patch.object(JS, 'node_version', return_value='entry-no-node'))
        self.enter(patch('subprocess.Popen', side_effect=AssertionError('no external process')))
        self.body = C.example()

    def enter(self, context):
        result = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return result

    def api(self, method, route, body=None, owner=True):
        handler = Handler(owner=owner)
        self.assertTrue(E.handle(handler, method, route, body))
        return handler

    def test_owner_compose_and_example_are_read_only_and_exact(self):
        before = copy.deepcopy(self.body)
        with (patch.object(A, '_root', side_effect=AssertionError('no store')),
              patch.object(A, 'start', side_effect=AssertionError('no launch'))):
            # The main owner-routed engine path, including its actual producer.
            for method, route, body in [('POST', 'graph/compose', self.body), ('GET', 'graph/composition-example', None)]:
                self.assertEqual(self.api(method, route, body, owner=False).status, 403)
            response = self.api('POST', 'graph/compose', self.body)
            self.assertEqual(response.status, 200, response.value)
            self.assertEqual(self.api('GET', 'graph/composition-example').value, self.body)
        native = C.expand_composition(self.body['composition'], self.body['policy'])
        self.assertEqual(response.value['draft'], {k: native['frozen'][k] for k in ('graph', 'policy')})
        self.assertEqual(response.value['manifest'], native['manifest'])
        self.assertEqual(response.value['check']['graph_hash'], native['frozen']['graph_hash'])
        self.assertEqual(response.value['check']['nodes'], 4)
        self.assertEqual(self.body, before)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_web_admission_rejects_effects_but_pure_authoring_retains_them(self):
        body = copy.deepcopy(self.body)
        definition = next(iter(body['composition']['definitions'].values()))
        definition['nodes'][0]['effect_risk'] = 'write'
        for instance in body['composition']['instances']:
            instance['sha256'] = C.definition_digest(body['composition']['definitions'][instance['definition']])
        generic = C.compose(body)
        self.assertTrue(any(row['effect_risk'] == 'write' for row in generic['draft']['graph']['nodes']))
        with patch.object(A, '_root', side_effect=AssertionError('no store')):
            response = self.api('POST', 'graph/compose', body)
        self.assertEqual(response.status, 400)
        self.assertIn('effect host', response.value['error'])

    def test_compose_does_not_start_and_later_explicit_flat_run_keeps_native_recovery(self):
        response = A.compose(self.body)
        self.assertEqual(list(self.folder.iterdir()), [])
        draft = response['draft']
        checked = A.check(draft)
        calls, launches = Apps(), []
        def launch(ident, folder, generation):
            launches.append(ident)
            A.run_job(folder, applicators=calls, generation=generation)
            return {'ok': True}
        with patch.dict(A.launcher, {'launch': launch, 'active': lambda _: False, 'stop': lambda _: True}):
            run = A.start({**draft, 'expected_graph_hash': checked['graph_hash'],
                           'expected_policy_hash': checked['policy_hash']})
            value = A.view(run['id'])
            self.assertEqual(value['state']['status'], 'succeeded', value)
            output = response['manifest']['ports']['Second']['outputs']['answer']['node']
            final = next(row for row in value['state']['nodes'] if row['node'] == output)
            self.assertEqual(final['result']['value'], 18)
            self.assertTrue(A.resume(run['id'])['terminal'])
            self.assertEqual(launches, [run['id']])
            saved = json.loads((A._folder(run['id']) / 'frozen.json').read_text())
            self.assertNotIn('composition', saved)
        self.assertEqual(calls.calls, [])

    def test_bad_composition_preserves_draft_and_never_creates_store(self):
        body = copy.deepcopy(self.body)
        body['composition']['instances'][0]['sha256'] = '0' * 64
        before = copy.deepcopy(body)
        with patch.object(A, '_root', side_effect=AssertionError('no store')):
            result = self.api('POST', 'graph/compose', body)
        self.assertEqual(result.status, 400)
        self.assertEqual(body, before)
        self.assertEqual(list(self.folder.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
