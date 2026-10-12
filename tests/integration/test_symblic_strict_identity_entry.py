"""Explicit strict policy reaches native execution or refuses before dispatch.

Transport tests inject the capability; lane-C tests own identity enforcement.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from symblic.providers import applicators as A
try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.kernel import run as SR

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'program Identity transport.\nlet value = 7.\nshow value.\n'


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class StrictIdentityEntry(unittest.TestCase):
    def test_api_refuses_bad_policy_and_unavailable_runtime_before_store_or_launch(self):
        with patch.object(E, 'runs_dir', side_effect=AssertionError('Unexpected store creation')), \
                patch.dict(E.launcher, {'launch': lambda *_: self.fail('Unexpected launch')}):
            for value in (None, False, True, {}, [], 1, 'STRICT', 'observe'):
                with self.subTest(value=value), self.assertRaises(E.SymblicApiError):
                    E.start_run({'source': SOURCE, 'options': {'model_pins': value}})
            for version in (None, True, 2, '1'):
                with self.subTest(version=version), patch.object(SR, 'MODEL_IDENTITY_VERSION', version, create=True), \
                        self.assertRaisesRegex(E.SymblicApiError, 'server update'):
                    E.start_run({'source': SOURCE, 'options': {'model_pins': 'strict'}})

    def test_api_records_strict_policy_without_changing_default(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(E, 'runs_dir', return_value=folder), \
                patch.object(SR, 'MODEL_IDENTITY_VERSION', 1, create=True), \
                patch.dict(E.launcher, {'launch': lambda *_: {'ok': True}}):
            for options in ({}, {'model_pins': 'strict'}):
                row = E.start_run({'source': SOURCE, 'options': options})
                saved = json.loads((Path(folder) / row['id'] / 'meta.json').read_text())
                self.assertEqual(saved['options'].get('model_pins'), options.get('model_pins'))

    def test_capability_advertises_only_supported_exact_version(self):
        with patch.object(A, 'engines_status', return_value={}), patch.object(E, 'examples', return_value=[]):
            for version in (None, True, 2, '1', 1):
                with self.subTest(version=version), patch.object(SR, 'MODEL_IDENTITY_VERSION', version, create=True):
                    self.assertIs(E.meta()['features']['strict_model_pins'], type(version) is int and version == 1)

    def cli(self, args, version, native):
        script = (ROOT / 'tools/symblic').read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['symblic', *args]), patch.object(sys, 'path', list(sys.path)), \
                patch.dict(os.environ, {'SYMBLIC_ROOT': str(ROOT)}), \
                patch.object(SR, 'MODEL_IDENTITY_VERSION', version, create=True), \
                patch.object(SR, 'Run', side_effect=native), \
                patch.object(A, 'Applicators', return_value=object()), \
                redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as done:
            exec(compile(script, str(ROOT / 'tools/symblic'), 'exec'), {'__name__': '__main__'})
        return done.exception.code, out.getvalue(), err.getvalue()

    def test_cli_missing_capability_refuses_before_source_record_or_runner(self):
        code, out, _ = self.cli(['run', '/does-not-exist.sym', '--strict-model-pins', '--agent-json'],
                                None, lambda *_args, **_kwargs: self.fail('Unexpected Run'))
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)['accepted'])
        self.assertIn('runtime update', json.loads(out)['error']['message'])
        code, out, err = self.cli(['replay', '/does-not-exist', '--strict-model-pins', '--agent-json'],
                                 1, lambda *_args, **_kwargs: self.fail('Unexpected Run'))
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('replay retains its recorded policy', err)

    def test_cli_passes_explicit_strict_policy_and_default_has_no_override(self):
        class Native:
            def execute(self):
                return {'status': 'done', 'outputs': [], 'calls': 0}
        observed = []
        def native(source, inputs, apps, options, **kwargs):
            observed.append(options)
            return Native()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'program.sym'
            source.write_text(SOURCE)
            for extra in ([], ['--strict-model-pins']):
                code, out, _ = self.cli(['run', str(source), '--agent-json', *extra], 1, native)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)['status'], 'done')
        self.assertNotIn('model_pins', observed[0])
        self.assertEqual(observed[1]['model_pins'], 'strict')
