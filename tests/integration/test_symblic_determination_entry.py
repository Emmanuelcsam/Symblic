"""Public determination control: fake launcher/provider and temporary run folders only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.kernel import run as R


SOURCE = ('ask n: Int in 1..3 "Select the valid value." with context=none,effort=low,retries=1\n'
          'ensure n = 2 else retry.\nshow n.\n')


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class DeterminationEntry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launch = mock.Mock(return_value={'ok': True})
        root_patch = mock.patch.object(E, 'root', return_value=str(self.root))
        launch_patch = mock.patch.dict(E.launcher, {'launch': self.launch})
        root_patch.start(); launch_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(launch_patch.stop)

    def start(self, options=None, source=SOURCE):
        body = {'source': source, 'by': 'fake:a'}
        if options is not None:
            body['options'] = options
        created = E.start_run(body)
        folder = self.root / 'runs' / created['id']
        meta = json.loads((folder / 'meta.json').read_text())
        return folder, meta

    def test_true_and_false_survive_public_metadata_roundtrip_as_booleans(self):
        for value in (False, True):
            with self.subTest(value=value):
                folder, meta = self.start({'determine': value})
                self.assertIn('determine', meta['options'])
                self.assertIs(meta['options']['determine'], value)
                self.assertTrue((folder / 'program.sym').is_file())
        self.assertEqual(self.launch.call_count, 2)

    def test_absence_preserves_prior_options_without_inserting_a_default(self):
        _, meta = self.start({'parallel': 1})
        self.assertEqual(meta['options'], {'profile': 'legacy', 'by': 'fake:a', 'parallel': 1})
        self.assertNotIn('determine', meta['options'])
        self.assertEqual(self.launch.call_count, 1)

    def test_malformed_values_refuse_before_directories_or_launch(self):
        for value in (None, 0, 1, 0.0, 1.0, 'false', 'true', '', [], {}, [False]):
            with self.subTest(value=value):
                with self.assertRaises(E.SymblicApiError) as caught:
                    self.start({'determine': value})
                self.assertIn('determine', str(caught.exception))
                self.assertEqual(list(self.root.iterdir()), [])
                self.launch.assert_not_called()

    def test_invalid_host_value_is_refused_even_when_source_would_override_it(self):
        with self.assertRaises(E.SymblicApiError):
            self.start({'determine': 'false'}, 'use determine=false.\n' + SOURCE)
        self.assertEqual(list(self.root.iterdir()), [])
        self.launch.assert_not_called()

    def test_persisted_false_disables_both_probes_and_still_checks_real_answers(self):
        folder, meta = self.start({'determine': False})
        class Models:
            def __init__(self):
                self.requests = []
            def call(self, request):
                self.requests.append(request)
                return {'ok': True, 'json': {'answer': 1 if len(self.requests) == 1 else 2}, 'ms': 1}
        models = Models()
        run = R.Run((folder / 'program.sym').read_text(), meta['inputs'], models, meta['options'], folder=str(folder))
        with (mock.patch.object(run, 'determine', side_effect=AssertionError('speculative enumeration')),
              mock.patch.object(run, 'vacuity', side_effect=AssertionError('empty-answer probe')),
              mock.patch.object(run, '_candidate', side_effect=AssertionError('speculative candidate check'))):
            report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(len(models.requests), 2)
        self.assertEqual(run.kernel.env.lookup('n').value, 2)
        self.assertTrue(all(row['reason'] == 'author_disabled' for row in report['determinacy']['asks']))
        self.assertEqual(self.launch.call_count, 1)  # only the public entry's injected launcher

    def test_preview_false_skips_probes_and_true_default_still_assess(self):
        contradictory = SOURCE.replace('n = 2', 'n = 4')
        with (mock.patch.object(R.Run, 'determine', side_effect=AssertionError('speculative enumeration')),
              mock.patch.object(R.Run, 'vacuity', side_effect=AssertionError('empty-answer probe')),
              mock.patch.object(R.Run, '_candidate', side_effect=AssertionError('speculative candidate check')),
              mock.patch.object(E._PreviewApps, 'call', side_effect=AssertionError('provider'))):
            report = E.preview({'source': contradictory, 'options': {'determine': False}})
        self.assertEqual(report['status'], 'paused', report.get('error'))
        self.assertEqual(report['next']['name'], 'n')
        self.assertIsNone(report['error'])
        for body in ({'source': contradictory}, {'source': contradictory, 'options': {'determine': True}}):
            with self.subTest(options=body.get('options')), mock.patch.object(
                    E._PreviewApps, 'call', side_effect=AssertionError('provider')):
                report = E.preview(body)
            self.assertEqual(report['status'], 'failed', report)
            self.assertEqual(report['error']['kind'], 'contradictory')
            self.assertNotIn('next', report)
        self.assertEqual(list(self.root.iterdir()), [])
        self.launch.assert_not_called()

    def test_preview_malformed_boolean_refuses_before_runtime_stores_or_providers(self):
        for value in (None, 0, 1, 0.0, 1.0, 'false', 'true', '', [], {}, [False]):
            with self.subTest(value=value), mock.patch.object(
                    R.Run, '__init__', side_effect=AssertionError('runtime constructed')):
                with self.assertRaises(E.SymblicApiError) as caught:
                    E.preview({'source': SOURCE, 'options': {'determine': value}})
                self.assertIn('determine', str(caught.exception))
            self.assertEqual(list(self.root.iterdir()), [])
            self.launch.assert_not_called()

    def test_persisted_true_retains_default_determination(self):
        folder, meta = self.start({'determine': True})
        models = mock.Mock()
        models.call.return_value = {'ok': True, 'json': {'answer': 2}, 'ms': 1}
        run = R.Run((folder / 'program.sym').read_text(), meta['inputs'], models, meta['options'], folder=str(folder))
        report = run.execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['determinacy']['asks'][0]['status'], 'determined')
        self.assertEqual(models.call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
