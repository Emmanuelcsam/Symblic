"""Capability reporting and inconclusive outcomes; never relax the real sandbox."""
import unittest
from unittest.mock import patch

from symblic.sandbox import landlock as sandbox
from symblic.js import check as JS


class Availability(unittest.TestCase):
    def setUp(self):
        self.node = patch.object(JS, 'node_path', return_value='/test/node')
        self.paths = patch.object(JS.os.path, 'exists', return_value=True)
        self.node.start()
        self.paths.start()
        self.addCleanup(self.node.stop)
        self.addCleanup(self.paths.stop)

    def test_node_alone_does_not_claim_a_sandbox_on_old_or_unknown_kernel(self):
        for abi in (0, 1, 2, 3):
            with self.subTest(abi=abi), patch.object(sandbox, 'abi_version', return_value=abi):
                self.assertFalse(JS.available())
        with patch.object(sandbox, 'abi_version', side_effect=OSError('unavailable')):
            self.assertFalse(JS.available())

    def test_supported_abi_only_reads_capability_without_restricting_or_spawning(self):
        with patch.object(sandbox, 'abi_version', return_value=sandbox.NET_ABI), \
                patch.object(sandbox, 'restrict') as restrict, patch.object(JS.subprocess, 'Popen') as launch:
            self.assertTrue(JS.available())
            restrict.assert_not_called()
            launch.assert_not_called()

    def test_missing_node_or_asset_refuses_before_probe(self):
        with patch.object(sandbox, 'abi_version') as probe:
            with patch.object(JS, 'node_path', return_value=None):
                self.assertFalse(JS.available())
            with patch.object(JS.os.path, 'exists', return_value=False):
                self.assertFalse(JS.available())
            probe.assert_not_called()

    def test_unsupported_sandbox_has_no_candidate_verdict_and_never_starts_child(self):
        with patch.object(sandbox, 'abi_version', return_value=3), patch.object(JS.subprocess, 'Popen') as launch:
            with self.assertRaises(JS.JsError) as caught:
                JS.test('throw new Error("must never run")', [('1', '1')])
            self.assertEqual('unavailable', caught.exception.kind)
            self.assertIn('Landlock', str(caught.exception))
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
