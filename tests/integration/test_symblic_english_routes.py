"""Host-only English routes: the original host dashboard's `english/...` HTTP API and its retry of saved runs.

Moved from tests/english/ (the pure parts stay there and test symblic.english.authoring and the CLI). These cases
drive integration/host/symblic_english_api.py and integration/host/symblic_engine.py, which need the original host
dashboard, so they are skipped when that host's modules are absent.
"""
import unittest

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    # The fake store (fake_host_apps.py) is not enough here: the host copy of the English API pins its compiler by
    # the original flat file names (symblic_english.py, ...), so these routes only work inside the original host.
    import host_apps  # noqa: F401  (the host's store module: these routes save and read runs)
    from integration.host import symblic_engine as ENGINE
    from integration.host import symblic_engine as E
    from integration.host import symblic_english_api as A
    from tests.integration.test_symblic_engine import Handler as EngineHandler
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

import contextlib
import copy
import io
import json
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.english import build as B
from symblic.english import pixels as P
from symblic.js import check as JS
from symblic.js import check as J
from symblic.spec import build as BUILD
from symblic.kernel.run import Run
from symblic.providers import applicators as AP
from tests.english.test_symblic_english_construction_recovery import FailingWorker
from tests.english.test_symblic_english_runtime import FALLING


class Handler:
    def get_query_param(self, _name):
        return ''

    def send_json(self, value, status=200):
        self.value, self.status = value, status


class ConstructionRoute(unittest.TestCase):
    def test_owner_module_check_never_dispatches_a_run_or_js(self):
        handler = Handler()
        with patch.object(ENGINE, 'start_run', side_effect=AssertionError('run dispatched')), \
                patch.object(ENGINE, 'preview', side_effect=AssertionError('preview dispatched')), \
                patch.object(JS, 'evaluate', side_effect=AssertionError('JavaScript executed')):
            self.assertTrue(ENGINE.handle(handler, 'POST', 'english/check', {'source': B.EXAMPLE}))
        self.assertEqual(handler.status, 200, handler.value)
        self.assertTrue(handler.value['ok'])
        self.assertTrue(S.check(handler.value['source'])['ok'])


class PixelRoute(unittest.TestCase):
    def test_check_has_no_execution_or_provider_side_effect(self):
        handler = Handler()
        with patch.object(ENGINE, 'start_run', side_effect=AssertionError('run dispatched')), \
                patch.object(ENGINE, 'preview', side_effect=AssertionError('preview dispatched')), \
                patch.object(JS, 'evaluate', side_effect=AssertionError('JavaScript executed')):
            self.assertTrue(ENGINE.handle(handler, 'POST', 'english/check', {'source': P.EXAMPLE}))
        self.assertEqual(handler.status, 200, handler.value)
        self.assertTrue(handler.value['ok'])
        self.assertTrue(S.check(handler.value['source'])['ok'])

    def test_real_run_preparation_fits_transport_and_persists_pinned_host_inputs(self):
        handler = Handler()
        launches = []
        def launch(run_id, folder, resume):
            launches.append((run_id, folder, resume))
            return {'ok': True}
        with tempfile.TemporaryDirectory() as store, \
                patch.object(ENGINE, 'root', return_value=store), \
                patch.dict(ENGINE.launcher, launch=launch), \
                patch.object(JS, 'evaluate', side_effect=AssertionError('source preparation executed code')):
            A.handle(handler, 'POST', 'english/run', {
                'source': P.EXAMPLE, 'by': 'ollama:qwen3:4b-instruct@fixture'})
            self.assertEqual(200, handler.status, handler.value)
            self.assertEqual(1, len(launches))
            run_id, folder, resume = launches[0]
            self.assertFalse(resume)
            self.assertEqual(handler.value['id'], run_id)
            path = Path(folder)
            meta = json.loads(path.joinpath('meta.json').read_text())
            source = path.joinpath('program.sym').read_text()
            self.assertEqual(P.EXAMPLE, path.joinpath('instructions.english').read_text())
            self.assertEqual(meta['inputs'], ENGINE._clean_inputs(meta['inputs']))
            self.assertTrue(meta['inputs'])
            self.assertLessEqual(len(source), S.MAX_SOURCE)
            self.assertTrue(A.checked_authoring(meta['authoring'], source))
            self.assertIn('execution_pins', meta['options'])


class PixelRetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = A.prepare({'source': P.EXAMPLE})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.folder.joinpath('instructions.english').write_text(P.EXAMPLE)
        self.saved = {'status': 'failed', 'source': self.compiled['source'],
                      'meta': {'authoring': copy.deepcopy(self.compiled['authoring'])}}
        self.request = {'source': P.EXAMPLE, 'keep': 'abcdef123456',
                        'by': 'ollama:qwen3:4b-instruct@fixture', 'budget': 12000,
                        'retries': 0, 'max_calls': 2}
        for patcher in (patch.object(ENGINE, 'run_dir', return_value=str(self.folder)),
                        patch.object(ENGINE, 'run_view', side_effect=lambda _id: copy.deepcopy(self.saved)),
                        patch.dict(ENGINE.launcher, active=lambda _id: False)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_retry_rechecks_locally_and_preserves_exact_authoring_and_provider(self):
        handler = Handler()
        captured = {}

        def start(body, *, authoring):
            captured.update(body=body, authoring=authoring)
            return {'id': '123456abcdef'}

        with patch.object(BUILD, 'checkpoint', return_value={'artifacts': {}}) as checkpoint, \
                patch.object(ENGINE, 'start_run', side_effect=start), \
                patch.object(JS, 'evaluate', side_effect=AssertionError('unexpected execution')):
            self.assertTrue(A.handle(handler, 'POST', 'english/run', self.request))
        self.assertEqual(handler.status, 200, handler.value)
        checkpoint.assert_called_once_with(str(self.folder), complete=False, recheck_seconds=30)
        self.assertEqual(captured['body']['by'], self.request['by'])
        self.assertEqual(captured['authoring']['document'], P.EXAMPLE)
        self.assertEqual(captured['authoring']['reuse'], {
            'from_run': self.request['keep'], 'kept': 0, 'scope': 'locally_rechecked_model_work'})
        self.assertTrue(A.checked_authoring(captured['authoring'], captured['body']['source']))
        self.assertIn('execution_pins', captured['body']['options'])
        self.assertTrue(captured['body']['inputs'])
        self.assertEqual(handler.value['reuse'], captured['authoring']['reuse'])

    def test_check_and_preview_never_accept_retry_or_execute_checkpoint(self):
        for route in ('english/check', 'english/preview'):
            with self.subTest(route=route), patch.object(BUILD, 'checkpoint', side_effect=AssertionError('recheck')):
                handler = Handler()
                A.handle(handler, 'POST', route, self.request)
                self.assertEqual(handler.status, 400)

    def test_nonterminal_or_active_saved_work_is_not_reused(self):
        for status in ('new', 'starting', 'running', 'lost'):
            self.saved['status'] = status
            with self.subTest(status=status), patch.object(BUILD, 'checkpoint', side_effect=AssertionError('recheck')), \
                    self.assertRaisesRegex(ValueError, 'finished or stopped'):
                A.prepare_retry(self.request)
        self.saved['status'] = 'failed'
        with patch.dict(ENGINE.launcher, active=lambda _id: True), \
                self.assertRaisesRegex(ValueError, 'finished or stopped'):
            A.prepare_retry(self.request)

    def test_tampered_or_changed_document_refuses_before_recheck(self):
        with patch.object(BUILD, 'checkpoint', side_effect=AssertionError('recheck')):
            with self.assertRaisesRegex(ValueError, 'exact saved English'):
                A.prepare_retry({**self.request, 'source': P.EXAMPLE + '\n'})
            self.folder.joinpath('instructions.english').write_text(P.EXAMPLE + '\n')
            with self.assertRaises(S.SymblicError):
                A.prepare_retry(self.request)
            self.folder.joinpath('instructions.english').write_text(P.EXAMPLE)
            self.saved['source'] += '\n'
            with self.assertRaisesRegex(ValueError, 'valid English pixel'):
                A.prepare_retry(self.request)

    def test_client_artifacts_and_invalid_ids_refuse_without_recheck(self):
        for updates in ({'artifacts': {}}, {'keep': '../abcdef123456'}, {'keep': None}):
            with self.subTest(updates=updates), patch.object(BUILD, 'checkpoint', side_effect=AssertionError('recheck')), \
                    self.assertRaises(ValueError):
                A.prepare_retry({**self.request, **updates})

    def test_saved_run_changed_during_recheck_is_refused(self):
        def changed(*_args, **_kwargs):
            self.saved['status'] = 'running'
            return {'artifacts': {}}
        with patch.object(BUILD, 'checkpoint', side_effect=changed), \
                self.assertRaisesRegex(ValueError, 'changed during'):
            A.prepare_retry(self.request)


class RuntimeRoute(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.launch = mock.Mock(return_value={'ok': True})
        for patch_ in (mock.patch.object(E, 'root', return_value=str(self.root / 'api')),
                       mock.patch.dict(E.launcher, {'launch': self.launch, 'active': lambda _id: False}),
                       mock.patch.object(AP, 'Applicators', side_effect=AssertionError('real model factory')),
                       mock.patch('signal.signal')):
            patch_.start()
            self.addCleanup(patch_.stop)

    def test_real_compiler_http_keeps_exact_policy_and_positions_invalid_input_without_launch(self):
        handler = EngineHandler()
        self.assertTrue(E.handle(handler, 'POST', 'english/run', {'source': FALLING, 'by': 'fake:falling',
                                                               'max_calls': 0, 'retries': 5, 'budget': 9000}))
        self.assertEqual(handler.status, 200, handler.sent)
        folder = self.root / 'api/runs' / handler.sent['id']
        meta = json.loads((folder / 'meta.json').read_text())
        self.assertEqual(meta['options']['max_calls'], 0)
        source = (folder / 'program.sym').read_text()
        self.assertEqual(source.count('retries=5, budget=9000.'), 6)
        self.assertEqual(meta['authoring']['document'], FALLING)
        self.launch.reset_mock()
        handler = EngineHandler()
        E.handle(handler, 'POST', 'english/run', {'source': 'Remember n is 1.\nDo magic.\n'})
        self.assertEqual(handler.status, 400, handler.sent)
        self.assertEqual(handler.sent['errors'][0]['line'], 2)
        self.launch.assert_not_called()


@unittest.skipUnless(J.available(), 'Sandboxed JavaScript runtime is unavailable')
class ApiRetry(unittest.TestCase):
    def prepare_partial_run(self, folder):
        from integration.host import symblic_english_api as api
        prepared = api.prepare({'source': B.EXAMPLE, 'retries': 0, 'max_calls': 12})
        Path(folder, 'program.sym').write_text(prepared['source'])
        Path(folder, 'instructions.english').write_text(B.EXAMPLE)
        worker = FailingWorker(4)
        options = {**prepared['options'], 'by': 'fake:fixture', 'parallel': 1}
        report = Run(prepared['source'], {}, worker, options, folder=folder).execute()
        self.assertEqual('failed', report['status'])
        return api, prepared

    def test_prepare_retry_keeps_the_accepted_prefix_under_the_same_keep_key(self):
        from integration.host import symblic_engine as engine
        with tempfile.TemporaryDirectory(prefix='symblic-construction-api-') as folder:
            api, prepared = self.prepare_partial_run(folder)
            view = {'status': 'failed', 'source': prepared['source'],
                    'meta': {'authoring': prepared['authoring']}}
            with mock.patch.object(engine, 'run_view', return_value=view), \
                    mock.patch.object(engine, 'run_dir', return_value=folder), \
                    mock.patch.object(engine, 'launcher', {'active': lambda run_id: False}):
                recovered = api.prepare_retry({'keep': '0123456789ab', 'source': B.EXAMPLE,
                                              'retries': 0, 'max_calls': 12})
            self.assertEqual(3, recovered['construction']['kept'])
            self.assertEqual(6, recovered['source'].count('\nask '))
            self.assertEqual({'from_run': '0123456789ab', 'kept': 3,
                              'scope': 'locally_rechecked_model_work'},
                             recovered['authoring']['reuse'])

    def test_prepare_retry_refuses_an_edited_document(self):
        from integration.host import symblic_engine as engine
        with tempfile.TemporaryDirectory(prefix='symblic-construction-api-') as folder:
            api, prepared = self.prepare_partial_run(folder)
            view = {'status': 'failed', 'source': prepared['source'],
                    'meta': {'authoring': prepared['authoring']}}
            with mock.patch.object(engine, 'run_view', return_value=view), \
                    mock.patch.object(engine, 'run_dir', return_value=folder), \
                    mock.patch.object(engine, 'launcher', {'active': lambda run_id: False}):
                with self.assertRaisesRegex(ValueError, 'preserve the exact saved English document'):
                    api.prepare_retry({'keep': '0123456789ab',
                                       'source': B.EXAMPLE.replace('Matrix rain', 'Emerald curtains'),
                                       'retries': 0, 'max_calls': 12})

    def test_prepare_retry_refuses_a_run_of_another_lane(self):
        from integration.host import symblic_engine as engine
        with tempfile.TemporaryDirectory(prefix='symblic-construction-api-') as folder:
            api, prepared = self.prepare_partial_run(folder)
            view = {'status': 'failed', 'source': 'show 1.',
                    'meta': {'authoring': {**prepared['authoring'], 'source': 'show 1.'}}}
            with mock.patch.object(engine, 'run_view', return_value=view), \
                    mock.patch.object(engine, 'run_dir', return_value=folder), \
                    mock.patch.object(engine, 'launcher', {'active': lambda run_id: False}):
                with self.assertRaisesRegex(ValueError, 'no valid English construction authoring record'):
                    api.prepare_retry({'keep': '0123456789ab', 'source': B.EXAMPLE,
                                       'retries': 0, 'max_calls': 12})


if __name__ == '__main__':
    unittest.main()
