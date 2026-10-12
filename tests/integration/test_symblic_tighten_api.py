"""Owner adoption binds saved audited bytes; no launch or model in tests.

Moved from tests/authoring/: adoption of a tightened program is a route of the original host
(integration/host/symblic_engine.py); it runs here with the fake store in fake_host_apps.py standing in for the
host's run store. symblic.authoring.tighten itself is tested in tests/authoring/.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.authoring import tighten as T


from tests.integration import fake_host_apps  # noqa: E402

# The host's store, faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class Adoption(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.temp.cleanup)
        self.ident = '123456abcdef'
        self.folder = Path(E.tighten_dir()) / self.ident
        self.folder.mkdir()
        self.proposal = T.audit_candidate('ask x: Number "How many?".', 'ask x: Number "How many days in a common year?".')
        self.proposal['status'] = 'done'
        self.save(self.proposal)
        self.owner = SimpleNamespace(is_owner=True, email='fixture@example.test')
        self.request = {'id': self.ident, **{k: self.proposal[k] for k in ('original_sha256', 'candidate_sha256', 'audit_sha256')}}

    def save(self, result):
        (self.folder / 'result.json').write_text(json.dumps(result))

    def test_explicit_owner_choice_records_exact_candidate_without_changing_proposal(self):
        result = E.adopt_tighten(self.request, self.owner)
        self.assertEqual(result['program'], self.proposal['candidate_program'])
        self.assertEqual(result['adoption']['status'], 'adopted')
        self.assertEqual(json.loads((self.folder / 'result.json').read_text()), self.proposal)
        self.assertEqual(json.loads((self.folder / 'adoption.json').read_text()), result)
        self.assertEqual(E.adopt_tighten(self.request, self.owner), result)

    def test_owner_cannot_adopt_stale_or_modified_result(self):
        for key in ('original_sha256', 'candidate_sha256', 'audit_sha256'):
            with self.subTest(key=key), self.assertRaises(E.SymblicApiError):
                E.adopt_tighten({**self.request, key: '0'*64}, self.owner)
        altered = copy.deepcopy(self.proposal)
        altered['candidate_program'] += '\nshow 123.'
        self.save(altered)
        with self.assertRaises(E.SymblicApiError):
            E.adopt_tighten(self.request, self.owner)
        self.assertFalse((self.folder / 'adoption.json').exists())

    def test_nonowner_running_legacy_and_failed_obligations_are_refused(self):
        with self.assertRaises(E.SymblicApiError):
            E.adopt_tighten(self.request, SimpleNamespace(is_owner=False))
        for change in ({'status': 'running'}, {'version': 1}):
            self.save({**self.proposal, **change})
            with self.assertRaises(E.SymblicApiError):
                E.adopt_tighten(self.request, self.owner)
        failed = T.audit_candidate(self.proposal['original_program'], self.proposal['candidate_program'],
            requirements=[{'id':'r','text':'Keep meaning'}],
            obligations=[{'id':'o','kind':'negative','split':'heldout','requirement_ids':['r'],'fixture':{},'expected':False}],
            fidelity_checker=lambda *_: {'status':'fail','reason':'Meaning changed'}, checker_id='fixture-v1')
        self.save({**failed,'status':'done'})
        request = {'id':self.ident,**{k:failed[k] for k in ('original_sha256','candidate_sha256','audit_sha256')}}
        with self.assertRaises(E.SymblicApiError):
            E.adopt_tighten(request, self.owner)

    def test_start_stores_predeclared_requirements_but_no_executable_checker(self):
        requirements=[{'id':'r','text':'Count calendar days'}]
        body={'source':'ask x: Number "How many days?".', 'panel':['fake:a','fake:b'],
              'clarifier':'fake:c','requirements':requirements,'requirement_map':{'x':['r']},
              'allow_meaning_changes':False}
        with patch.dict(E.launcher, {'tighten':lambda *_:{'ok':True}}):
            result=E.start_tighten(body)
        meta=json.loads((Path(E.tighten_dir())/result['id']/'meta.json').read_text())
        self.assertEqual(meta['requirements'],requirements)
        self.assertEqual(meta['requirement_map'],{'x':['r']})
        self.assertFalse(meta['allow_meaning_changes'])
        self.assertNotIn('fidelity_checker',meta)


if __name__ == '__main__':
    unittest.main()
