"""English host integration with an isolated compiler fixture, fake providers and temporary stores.

Host-only (moved from tests/english/): it drives the original host dashboard's HTTP routes, owner gate and
embedded CLI script, and is skipped when that host's modules are absent.

The stub exercises the API/CLI boundary independently of compiler grammar tests. Native runner,
execution pins, validation and replay are real. No service, scheduler, model or solver is started.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import automation_engine as AE
    import host_apps
    import security_gate as SG
    from integration.host import symblic_engine as E
    from integration.host import symblic_english_api as A
    from tests.integration.test_symblic_engine import Handler
    from tests.integration.test_symblic_proof_step_entry import RoutedHandler
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.kernel import language as S
from symblic.providers import applicators as AP
from symblic.english import cli as CLI
from symblic.kernel import execution_pins as X
from symblic.kernel import lockfile as K
from symblic.kernel import run as R

ROOT = Path(__file__).resolve().parents[2]          # the repository root
DOCUMENT = 'Remember selected as 7.\nAsk answer_one to read selected.\nShow answer_one.\n'
NATIVE = '''use profile=verified, determine=false.
let selected = 7.
let unrelated = "UNSELECTED_SECRET_TOKEN".
ask answer_one: Int "Read selected" from selected with retries=2,budget=12000.
ensure answer_one = selected else retry.
ask answer_two: Int "Read answer_one" from answer_one with retries=2,budget=12000.
ensure answer_two = answer_one else retry.
show answer_two.
'''


def snapshot(folder):
    return {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in folder.rglob('*') if p.is_file()}


class Apps:
    def __init__(self):
        self.requests = []

    def call(self, request):
        self.requests.append(copy.deepcopy({key: request.get(key) for key in ('app', 'system', 'prompt', 'schema')}))
        return {'ok': True, 'json': {'answer': 7}, 'model': 'fixture', 'node': 'isolated'}


class EnglishEntry(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = self.root / 'store'
        self.compiler_file = self.root / 'fixture_compiler.py'
        self.compiler_file.write_text('# Explicitly isolated English compiler fixture.\n')
        self.compiler = types.ModuleType('symblic_english')
        self.compiler.__file__ = str(self.compiler_file)
        self.compiler.VERSION = 'fixture-1'
        self.compiler.EXAMPLES = {'fixture': {'title': 'Fixture', 'source': DOCUMENT}}
        self.compiler.compile_source = mock.Mock(side_effect=self.compile_fixture)
        self.launch = mock.Mock(return_value={'ok': True})
        for patch in (mock.patch.dict(sys.modules, {'symblic_english': self.compiler}),
                      # This class deliberately stubs the compiler; real import identity is tested separately.
                      mock.patch.object(A, 'compiler_digest', return_value=hashlib.sha256(self.compiler_file.read_bytes()).hexdigest()),
                      mock.patch.object(E, 'root', return_value=str(self.store)),
                      mock.patch.dict(E.launcher, {'launch': self.launch, 'active': lambda _id: False}),
                      mock.patch.object(AP, 'Applicators', side_effect=AssertionError('real provider factory')),
                      mock.patch.object(AE, '_ensure_started', side_effect=AssertionError('scheduler')),
                      mock.patch.dict(host_apps._modules, {'automation_engine': AE}),
                      mock.patch.object(SG, 'OWNER_EMAILS', {'owner@example.test'}),
                      mock.patch('signal.signal')):
            patch.start()
            self.addCleanup(patch.stop)

    @staticmethod
    def compile_fixture(text, *, retries, max_calls, budget):
        if text == 'invalid statement':
            raise ValueError('Unrecognized English statement on line 1.')
        return {'source': NATIVE, 'inputs': {}, 'options': {'max_calls': max_calls},
                'statements': [{'line': 1, 'text': 'Fixture statement'}], 'source_map': {'1': 1}}

    def body(self, **changes):
        return {'source': DOCUMENT, 'by': 'fake:entry', 'retries': 2, 'max_calls': 2, 'budget': 12000, **changes}

    def call(self, route, body=None, method='POST'):
        handler = Handler()
        self.assertTrue(E.handle(handler, method, 'english/' + route, body if body is not None else self.body()))
        return handler

    def start(self):
        result = self.call('run')
        self.assertEqual(result.status, 200, result.sent)
        return result.sent['id'], self.store / 'runs' / result.sent['id']

    def native_cli(self, args):
        path = ROOT / 'bin/symblic'
        embedded = path.read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, 'argv', ['symblic', *args]), \
                mock.patch.object(sys, 'path', list(sys.path)), \
                mock.patch.dict(os.environ, {'DASHBOARD_DIR': str(ROOT)}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as ended:
            exec(compile(embedded, str(path), 'exec'), {'__name__': '__main__'})
        return ended.exception.code, json.loads(out.getvalue()), err.getvalue()

    def test_check_and_preview_create_no_store_or_provider(self):
        for route in ('check', 'preview'):
            result = self.call(route)
            self.assertEqual(result.status, 200, result.sent)
            self.assertTrue(result.sent['ok'])
        self.launch.assert_not_called()
        self.assertFalse(self.store.exists())
        self.assertEqual(self.compiler.compile_source.call_args.kwargs,
                         {'retries': 2, 'max_calls': 2, 'budget': 12000})

    def test_invalid_fields_or_limits_cannot_compile_or_dispatch(self):
        cases = [None, [], {'source': ''}, self.body(options={}), self.body(constructor='linear'),
                 self.body(runtime='/tmp/executable'), self.body(source=7)]
        for key in ('retries', 'max_calls', 'budget'):
            cases.extend(self.body(**{key: value}) for value in (True, 1.5, '2', None, -1, 100001))
        for body in cases:
            with self.subTest(body=body):
                self.compiler.compile_source.reset_mock()
                handler = Handler()
                self.assertTrue(E.handle(handler, 'POST', 'english/run', body))
                self.assertEqual(handler.status, 400, handler.sent)
                self.compiler.compile_source.assert_not_called()
                self.launch.assert_not_called()
                self.assertFalse(self.store.exists())

    def test_invalid_compiler_result_and_english_error_never_launch(self):
        bad = self.call('run', self.body(source='invalid statement'))
        self.assertEqual(bad.status, 400)
        self.assertIn('line 1', bad.sent['error'])
        with mock.patch.object(self.compiler, 'compile_source', return_value={'source': 'ask (broken', 'options': {}}):
            bad = self.call('run')
        self.assertEqual(bad.status, 400)
        self.launch.assert_not_called()
        self.assertFalse(self.store.exists())

    def test_owner_route_refuses_unverified_identity_before_compiler(self):
        handler = RoutedHandler('english/run', identity=SG.Identity(SG.ANONYMOUS))
        self.assertTrue(host_apps.handle_post(handler, self.body()))
        self.assertEqual(handler.status, 403)
        self.compiler.compile_source.assert_not_called()
        self.launch.assert_not_called()
        self.assertFalse(self.store.exists())

    def test_missing_compiler_reports_restart_without_any_store(self):
        with mock.patch.dict(sys.modules, {'symblic_english': None}):
            result = self.call('check')
        self.assertEqual(result.status, 503)
        self.assertIn('restart', result.sent['error'])
        self.assertFalse(self.store.exists())

    def test_run_saves_exact_instructions_source_identity_and_execution_pins(self):
        ident, folder = self.start()
        meta = json.loads((folder / 'meta.json').read_text())
        self.assertEqual((folder / 'instructions.english').read_text(), DOCUMENT)
        self.assertEqual((folder / 'program.sym').read_text(), NATIVE)
        authoring = meta['authoring']
        self.assertEqual(authoring['document'], DOCUMENT)
        self.assertEqual(authoring['compiler_sha256'], hashlib.sha256(self.compiler_file.read_bytes()).hexdigest())
        self.assertTrue(A.checked_authoring(authoring, NATIVE))
        self.assertEqual(meta['options']['max_calls'], 2)
        self.assertEqual(meta['options']['profile'], 'verified')
        self.assertIs(meta['options']['determine'], False)
        self.assertEqual(meta['options']['constructor'], 'off')
        self.assertFalse(meta['options'].get('side_effects'))
        self.assertEqual(X.validate(meta['options']['execution_pins'], NATIVE, {}), meta['options']['execution_pins'])
        self.launch.assert_called_once_with(ident, str(folder), False)
        for name in ('instructions.english', 'program.sym', 'meta.json'):
            self.assertEqual((folder / name).stat().st_mode & 0o777, 0o600)

    def test_api_saved_instruction_drift_refuses_before_relaunch(self):
        ident, folder = self.start()
        (folder / 'instructions.english').write_text('Changed after compilation.')
        before = snapshot(folder)
        self.launch.reset_mock()
        with self.assertRaises(E.SymblicApiError):
            E.resume_run(ident)
        self.launch.assert_not_called()
        self.assertEqual(snapshot(folder), before)

    def test_api_authoring_metadata_drift_refuses_before_relaunch(self):
        ident, folder = self.start()
        meta = json.loads((folder / 'meta.json').read_text())
        meta['authoring']['document'] = 'Changed original instructions.'
        (folder / 'meta.json').write_text(json.dumps(meta))
        before = snapshot(folder)
        self.launch.reset_mock()
        with self.assertRaises(E.SymblicApiError):
            E.resume_run(ident)
        self.launch.assert_not_called()
        self.assertEqual(snapshot(folder), before)

    def test_cli_native_run_replay_has_fresh_selected_context_and_identical_preview(self):
        compiled = A.prepare(self.body())
        folder = self.root / 'cli-run'
        apps = Apps()
        preview = self.call('preview').sent['preview']
        with contextlib.redirect_stdout(io.StringIO()):
            first = CLI.run_compiled(compiled, folder, 'fake:entry', applicators=apps)
        self.assertEqual(first['status'], 'done', first.get('error'))
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(apps.requests[0]['prompt'], preview['next']['prompt'])
        for request in apps.requests:
            self.assertNotIn('UNSELECTED_SECRET_TOKEN', request['prompt'])
        self.assertNotIn('Read selected', apps.requests[1]['prompt'])
        self.assertIn('answer_one', apps.requests[1]['prompt'])
        self.compiler.compile_source.reset_mock()
        with contextlib.redirect_stdout(io.StringIO()):
            replay = CLI.resume(folder, applicators=apps)
        self.assertEqual(replay['status'], 'done', replay.get('error'))
        self.assertEqual(replay['fingerprint'], first['fingerprint'])
        self.assertEqual(len(apps.requests), 2)
        self.compiler.compile_source.assert_not_called()

    def test_cli_saved_instruction_drift_refuses_before_native_runner(self):
        compiled = A.prepare(self.body())
        folder = self.root / 'cli-run'
        with contextlib.redirect_stdout(io.StringIO()):
            CLI.run_compiled(compiled, folder, 'fake:entry', applicators=Apps())
        (folder / 'instructions.english').write_text('Changed instruction file.')
        before = snapshot(folder)
        with mock.patch.object(R, 'run_folder', side_effect=AssertionError('native runner reached')):
            with self.assertRaises(S.SymblicError):
                CLI.resume(folder, applicators=Apps())
        self.assertEqual(snapshot(folder), before)

    def test_cli_zero_model_budget_fails_visibly_without_provider(self):
        compiled = A.prepare(self.body(max_calls=0))
        apps = Apps()
        with contextlib.redirect_stdout(io.StringIO()):
            result = CLI.run_compiled(compiled, self.root / 'zero', 'fake:entry', applicators=apps)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error']['kind'], 'budget')
        self.assertEqual(apps.requests, [])

    def test_cli_existing_records_are_preserved_before_dispatch(self):
        compiled = A.prepare(self.body())
        folder = self.root / 'saved'
        folder.mkdir()
        (folder / 'owner-record.txt').write_text('retained')
        before = snapshot(folder)
        with mock.patch.object(R, 'run_folder', side_effect=AssertionError('native runner reached')):
            with self.assertRaises(ValueError):
                CLI.run_compiled(compiled, folder, 'fake:entry')
        self.assertEqual(snapshot(folder), before)

    def test_portable_lock_preserves_english_linkage_or_explicitly_refuses(self):
        compiled = A.prepare(self.body())
        folder = self.root / 'portable'
        with contextlib.redirect_stdout(io.StringIO()):
            original = CLI.run_compiled(compiled, folder, 'fake:entry', applicators=Apps())
        self.assertEqual(original['status'], 'done', original.get('error'))
        before = snapshot(folder)
        try:
            lock = K.make_lock(str(folder))
        except K.LockError as error:
            # An explicit unsupported portability boundary may keep the native folder authoritative.
            self.assertRegex(str(error).lower(), r'english')
            self.assertRegex(str(error).lower(), r'retain|keep|resume')
        else:
            self.assertEqual(lock.get('authoring'), compiled['authoring'],
                             'portable native results must not silently discard their English source')
            with mock.patch.object(self.compiler, 'compile_source', side_effect=AssertionError('recompiled on replay')):
                replay = K.replay(lock)
            self.assertTrue(replay['ok'], replay.get('error'))
            self.assertEqual((replay['calls'], replay['refused']), (0, []))
            self.assertEqual(replay.get('recorded_authoring'), compiled['authoring'])
            self.assertTrue(A.checked_authoring(replay['recorded_authoring'], lock['source']))
            altered = copy.deepcopy(lock)
            altered['authoring']['document'] = 'A different instruction.'
            altered['sha256'] = K.lock_hash(altered)
            with self.assertRaises(K.LockError):
                K.replay(altered)
        self.assertEqual(snapshot(folder), before)

    def test_native_replay_checks_english_linkage_and_preserves_original_records(self):
        compiled = A.prepare(self.body())
        folder = self.root / 'native-replay'
        with contextlib.redirect_stdout(io.StringIO()):
            original = CLI.run_compiled(compiled, folder, 'fake:entry', applicators=Apps())
        kept = {name: (folder / name).read_bytes() for name in ('meta.json', 'program.sym', 'instructions.english')}
        code, report, _ = self.native_cli(['replay', str(folder), '--agent-json'])
        self.assertEqual(code, 0, report)
        self.assertEqual(report['fingerprint'], original['fingerprint'])
        self.assertEqual(report['calls'], 0)
        self.assertEqual(kept, {name: (folder / name).read_bytes() for name in kept})
        (folder / 'instructions.english').write_text('Changed original instructions.')
        before = snapshot(folder)
        code, report, _ = self.native_cli(['replay', str(folder), '--agent-json'])
        self.assertEqual(code, 1, report)
        self.assertEqual(report['error']['kind'], 'version')
        self.assertIn('English', report['error']['message'])
        self.assertEqual(snapshot(folder), before)

    def test_native_run_cannot_replace_english_folder_even_if_instruction_file_is_missing(self):
        compiled = A.prepare(self.body())
        folder = self.root / 'native-overwrite'
        source = self.root / 'replacement.sym'
        source.write_text('show 99.')
        with contextlib.redirect_stdout(io.StringIO()):
            CLI.run_compiled(compiled, folder, 'fake:entry', applicators=Apps())
        for missing_instructions in (False, True):
            with self.subTest(missing_instructions=missing_instructions):
                if missing_instructions:
                    (folder / 'instructions.english').unlink()
                before = snapshot(folder)
                code, report, _ = self.native_cli(['run', str(source), '--dir', str(folder), '--agent-json'])
                self.assertEqual(code, 1, report)
                self.assertEqual(report['error']['kind'], 'version')
                self.assertIn('english resume', report['error']['message'])
                self.assertEqual(snapshot(folder), before)


if __name__ == '__main__':
    unittest.main()
