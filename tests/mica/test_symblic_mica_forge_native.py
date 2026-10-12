"""Actual native Forge -> MICA journeys, fake provider boundary only.

Run in a coherent source snapshot on a host supporting the existing JS sandbox.
All Forge/native/component stores are temporary. No real model/service call.
"""
import copy
from pathlib import Path
import tempfile
import unittest

try:
    from integration.host import symblic_forge as Forge   # creates the Forge projects and handoffs these tests use
except Exception as exc:  # noqa: BLE001
    import unittest as _unittest
    raise _unittest.SkipTest(f'integration.host.symblic_forge (used to build Forge fixtures) cannot be imported: '
                             f'{type(exc).__name__}: {exc}')
from symblic.forge import core as FC
from symblic.forge import exports as FE
from symblic.forge.store import Store, StoreError, encode
from symblic.mica import search as M
from symblic.mica import forge as A
from tests.mica.test_symblic_mica_execution import FakeApps, inventory
from tests.mica.test_symblic_mica_forge import fixture, binding


class NativeForgeJourneys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-native-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = Store(self.root / 'forge')
        self.inv = inventory(('node-e',))

    def prepare(self, *, modules=False, root_extra_case=False):
        project = fixture()
        value = binding()
        value['budget'].update(wall_seconds=120, retries=0, max_calls=2,
                               max_workers=1, context_chars=24000)
        if modules:
            value.update(artifact_format='javascript_modules', allowed_outputs=['index.mjs', 'inc.mjs', 'twice.mjs'])
            value['units'][0]['output_path'] = 'inc.mjs'
            value['units'][1]['output_path'] = 'twice.mjs'
        if root_extra_case:
            FC.active_branch(project)['entities']['criteria'][0].update(observable='inc(3)', expected='4')
            value['criteria'][0].update(call='inc(3)', expected='4')
        stored = self.db.create('', '', '', 'native-create', manifest=FC.export_manifest(project))
        handoff = Forge.dispatch('POST', 'handoff', {'id': stored['id'], 'revision': stored['revision'],
                    'request_id': 'native-handoff'}, db=self.db)['handoff']
        self.assertEqual(handoff['compiler'], FE.compiler_identity())
        self.assertFalse(handoff['compiler'].get('restart_required'))
        self.project_id = stored['id']
        self.handoff_id = handoff['id']
        prepared = A.prepare(stored['id'], handoff['id'], value, db=self.db)
        self.assertEqual(prepared['origin']['identity']['mica'], M.implementation_identity())
        return prepared

    def runner(self, prepared, apps, *, folder='run', request_id='native-build'):
        return A.ForgeMicaRun(prepared, self.root / folder, apps, self.inv,
                              db=self.db, request_id=request_id)

    @staticmethod
    def correct(req, number):
        if number == 1:
            return 'function inc(x) { return x + 1; }'
        if number == 2:
            return 'function twice(x) { return inc(x) * 2; }'
        raise AssertionError('Unexpected planner, repair or repeated provider call')

    def assert_origin(self, result, prepared, *, folder='run', request_id='native-build'):
        self.assertTrue(A.verify_result_origin(result, prepared, self.root / folder, self.inv, request_id))
        self.assertEqual(result['semantic_completeness'], 'unassessed')

    def success(self, modules):
        prepared = self.prepare(modules=modules)
        apps = FakeApps(self.correct)
        plan = self.runner(prepared, apps).plan()
        self.assertEqual(plan['status'], 'planned', plan)
        self.assertEqual(plan['calls'], 0)
        self.assertEqual(apps.requests, [])
        self.assert_origin(plan, prepared)
        result = self.runner(prepared, apps).execute()
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 2)
        self.assertEqual(len(apps.requests), 2)
        self.assert_origin(result, prepared)
        M.verify_result_artifacts(result, prepared['request'], prepared['origin']['identity']['mica'])
        if modules:
            self.assertIn('bundle', result)
            self.assertEqual(result['module_checks']['status'], 'passed')
        repeated = self.runner(prepared, apps).execute()
        self.assertEqual(repeated, result)
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(self.db.get(self.project_id)['id'], self.project_id)
        # Construction cannot automatically rewrite/accept the original Forge state.
        self.assertEqual(FC.fingerprint(self.db.get(self.project_id)), prepared['origin']['fingerprint'])

    def test_script_two_unit_native_plan_build_and_exact_replay(self):
        self.success(False)

    def test_module_two_unit_native_plan_build_and_exact_replay(self):
        self.success(True)

    def test_original_root_case_rejects_units_that_pass_their_examples(self):
        prepared = self.prepare(root_extra_case=True)
        def provider(req, number):
            if number == 1:
                return 'function inc(x) { return x === 2 ? 3 : 0; }'
            return self.correct(req, number)
        apps = FakeApps(provider)
        result = self.runner(prepared, apps).execute()
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 2, result)
        self.assertEqual(len(apps.requests), 2)
        self.assert_origin(result, prepared)
        repeated = self.runner(prepared, apps).execute()
        self.assertEqual(repeated['status'], result['status'])
        self.assertEqual(len(apps.requests), 2)

    def test_native_unknown_delivery_retains_origin_and_never_redispatches(self):
        prepared = self.prepare()
        apps = FakeApps(lambda req, number: RuntimeError('fixture lost provider acknowledgement'))
        first = self.runner(prepared, apps).execute()
        self.assertEqual(first['status'], 'unknown', first)
        self.assertEqual(first['calls'], 1)
        self.assert_origin(first, prepared)
        second = self.runner(prepared, apps).execute()
        self.assertEqual(second['status'], 'unknown', second)
        self.assertEqual(second['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assert_origin(second, prepared)
        self.assertFalse((self.root / 'run' / 'mica-result.json').exists())

    def test_stale_acceptance_refuses_new_import_but_original_resume_stays_pinned(self):
        prepared = self.prepare()
        apps = FakeApps(self.correct)
        planned = self.runner(prepared, apps).plan()
        self.assertEqual(planned['status'], 'planned', planned)
        changed = copy.deepcopy(self.db.get(self.project_id))
        FC.active_branch(changed)['statements'][0]['text'] = 'A different accepted requirement after planning.'
        with self.db.connection(True) as conn:
            conn.execute('UPDATE projects SET document=? WHERE id=?', (encode(changed), self.project_id))
        with self.assertRaises((A.ForgeMicaError, StoreError)):
            self.runner(prepared, apps, folder='new', request_id='fresh-after-change').execute()
        self.assertEqual(apps.requests, [])
        resumed = self.runner(prepared, apps).execute()
        self.assertEqual(resumed['status'], 'done', resumed)
        self.assertEqual(len(apps.requests), 2)
        self.assert_origin(resumed, prepared)
        self.assertEqual(prepared['request']['requirements'][0]['text'], 'Return x plus one.')


if __name__ == '__main__':
    unittest.main()
