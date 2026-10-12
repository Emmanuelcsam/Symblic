"""Old-kernel resumes refuse before relaunch; the host's orchestrator keeps lowered authority."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import host_orchestrator as C
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.kernel import language as S
from symblic.kernel import run as R


class ResumeApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        previous = {**S.kernel_id(), 'id': 'old-kernel', 'lang': '2.4'}
        with mock.patch.object(S, 'kernel_id', return_value=previous):
            report = R.Run('let x = 1.\nshow x.', folder=str(self.folder)).execute()
        self.assertEqual(report['status'], 'done')
        self.state = (self.folder / 'state.json').read_bytes()
        (self.folder / 'meta.json').write_text(json.dumps({'options': {
            'max_calls': 9, 'model_policy': {'max_calls': 9, 'repairs': 4, 'allow_cloud': True}}}))

    def test_symblic_api_preserves_record_and_never_launches(self):
        launch = mock.Mock()
        with mock.patch.object(E, 'run_dir', return_value=str(self.folder)), \
                mock.patch.dict(E.launcher, active=lambda _: False, launch=launch):
            with self.assertRaisesRegex(E.SymblicApiError, 'another kernel|kernel'):
                E.resume_run('test')
        launch.assert_not_called()
        self.assertEqual(self.state, (self.folder / 'state.json').read_bytes())

    def test_orchestrator_preserves_state_and_lowers_budget_before_refusal(self):
        launch = mock.Mock()
        conf = {**C.DEFAULT_SETTINGS, 'routing': {'max_calls': 2, 'repairs': 1, 'allow_cloud': False}}
        with mock.patch.object(C, 'run_dir', return_value=str(self.folder)), \
                mock.patch.object(C, '_idle'), mock.patch.object(C, 'settings', return_value=conf), \
                mock.patch.object(C, '_model_policy', return_value=conf['routing']), \
                mock.patch.object(C, 'warm_route') as warm, mock.patch.dict(C.launcher, launch=launch):
            with self.assertRaisesRegex(C.OrchestratorError, 'kernel'):
                C.resume_run('test', warm=True)
        launch.assert_not_called(); warm.assert_not_called()
        self.assertEqual(self.state, (self.folder / 'state.json').read_bytes())
        saved = json.loads((self.folder / 'meta.json').read_text())
        self.assertEqual(saved['options']['model_policy'], conf['routing'])

    def test_orchestrator_routed_refusal_never_refreshes_or_expands_candidates(self):
        meta = json.loads((self.folder / 'meta.json').read_text())
        meta['options'].update(by='auto', auto_route={'candidates': ['ollama:small@node-f']})
        (self.folder / 'meta.json').write_text(json.dumps(meta))
        with mock.patch.object(C, 'run_dir', return_value=str(self.folder)), \
                mock.patch.object(C, '_idle'), mock.patch.object(C, 'settings', return_value=C.DEFAULT_SETTINGS), \
                mock.patch.object(C, 'warm_route') as warm, mock.patch.dict(C.launcher, launch=mock.Mock()) as hooks:
            with self.assertRaisesRegex(C.OrchestratorError, 'kernel'):
                C.resume_run('test', warm=True)
            hooks['launch'].assert_not_called(); warm.assert_not_called()
        self.assertEqual(self.state, (self.folder / 'state.json').read_bytes())
