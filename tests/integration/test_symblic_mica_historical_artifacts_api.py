"""Historical MICA artifact reads through the original host's owner-only HTTP API (integration/host).

These tests exercise integration/host/symblic_mica_api.py, which only ran inside the original host system. They
use fakes for every host service and are skipped when that module cannot be imported here.
"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from integration.host import symblic_mica_api as A
    UNAVAILABLE = ''
except Exception as exc:  # noqa: BLE001  (any import failure means the host API cannot be exercised)
    A = None
    UNAVAILABLE = (f'integration.host.symblic_mica_api is unavailable outside the original host: '
                   f'{type(exc).__name__}: {exc}')
from symblic.mica import search as M
from symblic.mica import bundle as B
from symblic.mica import forge as F
from tests.mica.test_symblic_mica_cli import bundle_result, RUNTIME


@unittest.skipIf(A is None, UNAVAILABLE)
class HistoricalApiArtifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-history-api-reader-')
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

    def api_read(self, *, forge=False, runtime=RUNTIME, rebound=False):
        task = {'kind': 'request', 'request': self.result['bundle']['request']}
        result = copy.deepcopy(self.result)
        inventory = []
        if forge:
            prepared = A.G._seal({'origin': {'identity': {'mica': RUNTIME}}, 'request': task['request']})
            task.update(kind='forge', prepared=prepared)
            result.update(forge_origin=F._origin_record(prepared, self.folder/'runtime', inventory, 'mica-012345abcdef'),
                          scope=F.SCOPE, semantic_completeness='unassessed')
            if rebound:
                result['forge_origin']['request_id'] = 'another-origin'
        frozen = {'spec': {'task': task, 'inventory': inventory}, 'implementation': {'construction': runtime}}
        with mock.patch.object(A, 'view', return_value={'result': result, 'status': 'done'}), \
             mock.patch.object(A, '_open', return_value=(self.folder, {}, frozen)):
            return A.artifacts('012345abcdef', include_text=True, include_archive=True)

    def assert_archive(self, value):
        self.assertEqual(len(value['artifacts']), 2)
        self.assertGreater(value['archive']['bytes'], 0)
        self.assertEqual(value['bundle_sha256'], self.result['bundle']['sha256'])

    def test_request_and_forge_api_reads_use_retained_runtime(self):
        for forge in (False, True):
            with self.subTest(forge=forge):
                self.assert_archive(self.api_read(forge=forge))

    def test_wrong_frozen_runtime_is_still_rejected(self):
        with self.assertRaises(ValueError):
            self.api_read(runtime={'different': 'frozen-source'})

    def test_compiler_asset_drift_is_still_rejected(self):
        with mock.patch.object(B, 'asset_snapshot', return_value={'fixture': b'changed compiler'}):
            with self.assertRaises(ValueError):
                self.api_read()

    def test_rebound_forge_origin_is_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'origin'):
            self.api_read(forge=True, rebound=True)


if __name__ == '__main__':
    unittest.main()
