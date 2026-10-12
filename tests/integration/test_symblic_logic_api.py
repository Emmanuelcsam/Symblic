"""The human-logic compiler through the host's owner-only Symblic API (integration/host/symblic_engine.py).

Host-only: the engine module imports the private host dashboard, so these tests skip in this repository.
The compiler itself is tested in tests/adapters/test_symblic_logic.py."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.adapters import logic as L

TASK = {'premises': 'human: "Socrates is human"\nrule: "Socrates is human" implies "Socrates is mortal"',
        'goal': '"Socrates is mortal"', 'calls': 2}


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class Handler:
    def get_query_param(self, _key):
        return ''

    def send_json(self, value, status=200):
        self.value, self.status = value, status


class LogicApi(unittest.TestCase):
    def test_compilation_route_has_no_store_or_launch(self):
        h = Handler()
        with patch.dict(E.launcher, {'launch': lambda *_: self.fail('compile launched')}), \
                patch.object(E, 'root', side_effect=AssertionError('compile accessed live store')):
            self.assertTrue(E.handle(h, 'POST', 'logic/compile', TASK))
        self.assertEqual(h.status, 200)
        self.assertTrue(h.value['check']['ok'])
        self.assertEqual(h.value['options']['max_calls'], 2)

    def test_api_error_is_visible_and_checked_host_profile_prevents_launch(self):
        h = Handler()
        E.handle(h, 'POST', 'logic/compile', {**TASK, 'goal': 'not a formula'})
        self.assertEqual(h.status, 400)
        with patch.dict(E.launcher, {'launch': lambda *_: self.fail('invalid program launched')}):
            with self.assertRaises(E.SymblicApiError):
                E.start_run({'source': 'asertt false.', 'options': {'profile': 'verified'}})

    def test_evidence_includes_read_only_matched_reports(self):
        from symblic.bench import matched as M
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'AUTOMATION_DATA_DIR': folder}):
            experiment = Path(E.bench_dir()) / 'matched-fixture'
            experiment.mkdir(parents=True)
            (experiment / 'matched-plan.json').write_text('{}')
            with patch.object(M, 'load_summary', return_value={'ok': True, 'summary': {'groups': []}, 'markdown': 'Fixture report'}) as load:
                result = E.evidence()
            load.assert_called_once_with(str(experiment))
            self.assertEqual(result['matched'][0]['name'], 'matched-fixture')
            self.assertEqual(result['matched'][0]['markdown'], 'Fixture report')

    def test_existing_run_stores_compiled_profile_and_call_budget(self):
        task = L.compile_task(TASK)
        task['options']['module_logic'] = {'lib:kinship': 'shared'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'AUTOMATION_DATA_DIR': folder}), \
                patch.dict(E.launcher, {'launch': lambda *_: {'ok': True}}):
            response = E.start_run({**task, 'by': 'ollama:qwen3:4b-instruct'})
            meta = fake_host_apps.load_json(os.path.join(E.run_dir(response['id']), 'meta.json'), {})
            self.assertEqual(meta['options']['max_calls'], 2)
            self.assertEqual(meta['options']['profile'], 'verified')
            self.assertEqual(meta['options']['module_logic'], {'lib:kinship': 'shared'})
            self.assertEqual(meta['inputs'], task['inputs'])



if __name__ == '__main__':
    unittest.main()
