"""Pure historical artifact reads through the MICA command line; no checker, process or model invocation.

The same reads through the original host's HTTP API are tested in
tests/integration/test_symblic_mica_historical_artifacts_api.py.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from symblic.mica import search as M
from symblic.mica import bundle as B
from symblic.mica import cli as CLI
from symblic.mica import project as P
from tests.mica.test_symblic_mica_cli import bundle_result, RUNTIME


class HistoricalArtifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-history-reader-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.assets = mock.patch.object(B, 'asset_snapshot', return_value={'fixture': b'exact retained compiler'})
        self.assets.start(); self.addCleanup(self.assets.stop)
        self.result = bundle_result()
        for patch in (
            mock.patch.object(M, 'implementation_identity', side_effect=AssertionError('current runtime must not authorize historical bytes')),
            mock.patch.object(B, 'check_bundle', side_effect=AssertionError('reader must not execute a checker')),
            mock.patch.object(B, '_evaluate', side_effect=AssertionError('reader must not start a sandbox')),
        ):
            patch.start(); self.addCleanup(patch.stop)

    def cli_read(self, *, project=False, runtime=RUNTIME):
        args = CLI.parser().parse_args(['artifacts', '--dir', str(self.folder), '--include-text', '--archive'])
        with mock.patch.object(CLI, '_project_manifest', return_value={'identity': {'construction': runtime}} if project else None), \
             mock.patch.object(P, 'read_project_result', return_value=self.result), \
             mock.patch.object(CLI, '_run_records', return_value=(self.folder, {'identity': runtime}, self.result)):
            return CLI.dispatch(args)

    def assert_archive(self, value):
        self.assertEqual(len(value['artifacts']), 2)
        self.assertGreater(value['archive']['bytes'], 0)
        self.assertEqual(value['bundle_sha256'], self.result['bundle']['sha256'])

    def test_request_and_project_cli_reads_use_retained_runtime(self):
        for project in (False, True):
            with self.subTest(project=project):
                self.assert_archive(self.cli_read(project=project))

    def test_wrong_frozen_runtime_is_still_rejected(self):
        with self.assertRaises(ValueError):
            self.cli_read(runtime={'different': 'frozen-source'})

    def test_compiler_asset_drift_is_still_rejected(self):
        with mock.patch.object(B, 'asset_snapshot', return_value={'fixture': b'changed compiler'}):
            with self.assertRaises(ValueError):
                self.cli_read()


if __name__ == '__main__':
    unittest.main()
