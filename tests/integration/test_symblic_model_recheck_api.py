"""Explicit identity inspection is bounded; ordinary polling stays historical."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
    from tests.integration.test_symblic_engine import Handler
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.kernel import run as SR


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class Recheck(unittest.TestCase):
    def test_explicit_route_reads_only_with_fixed_host_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'state.json').write_text(json.dumps({'status': 'done'}))
            prior = {p.name: p.read_bytes() for p in root.iterdir()}
            block = {'version': 1, 'basis': 'fresh_recheck', 'computed_at': 1,
                     'rows_truncated': True, 'checker': {'available': False}}
            with patch.object(E, 'run_dir', return_value=folder) as locate, \
                    patch.object(SR, 'recheck_model_identities', return_value=block, create=True) as inspect, \
                    patch.object(SR, 'Run', side_effect=AssertionError('No runner on read')), \
                    patch.dict(E.launcher, {'active': lambda _: False}):
                E.run_view('000000000001')
                inspect.assert_not_called()
                h = Handler()
                self.assertTrue(E.handle(h, 'POST', 'run/recheck-models',
                                         {'id': '000000000001', 'max_rows': 999999999}))
                self.assertEqual(h.status, 200)
                self.assertEqual(h.sent, {'id': '000000000001', 'model_identity': block})
                inspect.assert_called_once_with(folder, max_rows=2000, max_bytes=4_000_000)
                locate.assert_called_with('000000000001')
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, prior)

    def test_invalid_id_and_old_runtime_refuse_without_rechecking(self):
        with patch.object(SR, 'recheck_model_identities', create=True) as inspect:
            h = Handler()
            E.handle(h, 'POST', 'run/recheck-models', {'id': '../../escape'})
            self.assertEqual(h.status, 400)
            inspect.assert_not_called()
        with patch.object(E, 'run_dir', return_value='/unused'), \
                patch.object(SR, 'recheck_model_identities', None, create=True):
            h = Handler()
            E.handle(h, 'POST', 'run/recheck-models', {'id': '000000000001'})
            self.assertEqual(h.status, 400)
            self.assertIn('server update', h.sent['error'])


if __name__ == '__main__':
    unittest.main()
