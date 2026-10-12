"""The original host's write-page constructor controls (the meta feature marker and page payloads).

Moved from tests/constructor. These cases drive integration/host/symblic_engine.py with the fake store in
fake_host_apps.py standing in for the host's run store, so they run without the host. Temporary stores, a fake
launcher and a provider factory that fails if touched: no worker, solver or model runs.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

import symblic.kernel
from symblic.kernel import run as R
from symblic.providers import applicators as A

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'given base: Int = 10.\nask next: Int "Construct the next integer.".\nensure next = base + 1 else retry.\nshow next.\n'
SOLVER_MODULES = ('symblic.constructor.core', 'symblic.constructor.journal', 'symblic.linear.constructor',
                  'symblic.linear.worker', 'symblic.linear.resources', 'z3')


from tests.integration import fake_host_apps  # noqa: E402

# The host's store, faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class Marker(unittest.TestCase):
    def test_meta_reports_exact_read_only_api_marker(self):
        with mock.patch.object(A, 'engines_status', return_value={}):
            features = E.meta()['features']
        self.assertEqual(features['constructor_options'], {
            'version': 1, 'modes': ['off', 'linear_diagnose', 'linear'],
            'requires': {'determine': False, 'solve': False}, 'max_calls': [0, 10000]})
        self.assertIn('strict_model_pins', features)

    def test_marker_is_false_when_runner_lacks_the_validator(self):
        stub = types.ModuleType('symblic.kernel.run')
        with mock.patch.dict(sys.modules, {'symblic.kernel.run': stub}), mock.patch.object(symblic.kernel, 'run', stub):
            self.assertIs(E.constructor_options_feature(), False)
        stub.validate_constructor_options = 'not callable'
        with mock.patch.dict(sys.modules, {'symblic.kernel.run': stub}), mock.patch.object(symblic.kernel, 'run', stub):
            self.assertIs(E.constructor_options_feature(), False)

    def test_marker_is_false_when_runner_cannot_import(self):
        with mock.patch.dict(sys.modules, {'symblic.kernel.run': None}), mock.patch.object(symblic.kernel, 'run', None):
            self.assertIs(E.constructor_options_feature(), False)

    def test_meta_marker_loads_no_solver_or_constructor_module(self):
        probe = ('import sys, json\nfrom integration.host import symblic_engine as E\nE.constructor_options_feature()\n'
                 'print(json.dumps(sorted(sys.modules)))')
        done = subprocess.run([sys.executable, '-c', probe], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=60, check=True)
        loaded = set(json.loads(done.stdout))
        self.assertEqual([m for m in SOLVER_MODULES if m in loaded], [])


class PagePayloads(unittest.TestCase):
    """The page's exact `options` objects are accepted (enabled) or left untouched (off)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launch = mock.Mock(return_value={'ok': True})
        for patch in (mock.patch.object(E, 'root', mock.Mock(return_value=str(self.root))),
                      mock.patch.dict(E.launcher, {'launch': self.launch}),
                      mock.patch.object(A, 'Applicators', side_effect=AssertionError('provider created'))):
            patch.start(); self.addCleanup(patch.stop)

    def start(self, options):
        result = E.start_run({'source': SOURCE, 'inputs': {}, 'by': 'fake:a', 'title': '', 'options': options})
        return json.loads((self.root / 'runs' / result['id'] / 'meta.json').read_text())['options']

    def test_off_payload_never_requests_the_validator(self):
        with mock.patch.object(R, 'validate_constructor_options', side_effect=AssertionError('policy requested')):
            options = self.start({'side_effects': False})
        self.assertEqual(options, {'profile': 'legacy', 'by': 'fake:a'})

    def test_enabled_payloads_keep_exact_mode_zero_budget_and_solve_off(self):
        for mode in ('linear', 'linear_diagnose'):
            for calls in (0, 7, 10000):
                with self.subTest(mode=mode, calls=calls):
                    options = self.start({'side_effects': False, 'constructor': mode, 'determine': False,
                                          'solve': False, 'max_calls': calls})
                    self.assertEqual(options['constructor'], mode)
                    self.assertIs(options['determine'], False)
                    self.assertIs(options['solve'], False)
                    self.assertEqual(options['max_calls'], calls)
                    self.assertEqual(options['constructor_limits'], R.validate_constructor_options(
                        {'constructor': mode, 'determine': False})['limits'])

    def test_server_refuses_what_the_page_never_sends(self):
        for bad in ({'constructor': 'linear'},                                     # determine missing
                    {'constructor': 'linear', 'determine': False, 'solve': 'off'},   # 'off' text reads as on
                    {'constructor': 'z3', 'determine': False},
                    {'constructor': 'linear', 'determine': False, 'constructor_worker': '/usr/bin/python3'}):
            with self.subTest(bad=bad), self.assertRaises(E.SymblicApiError):
                E.start_run({'source': SOURCE, 'by': 'fake:a', 'options': bad})
        self.launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
