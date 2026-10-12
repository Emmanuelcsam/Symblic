"""Runtime identity binds exactly the sandbox and JS bytes used for execution."""
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.js import check as JS
from symblic.kernel import execution_pins as X


class RuntimeAssets(unittest.TestCase):
    def test_asset_hashes_and_version_change_only_in_a_fresh_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            runner, sandbox = Path(folder) / 'runner.js', Path(folder) / 'sandbox.py'
            runner.write_bytes(b'// fixture runner')
            sandbox.write_bytes(b'# fixture sandbox')
            with patch.object(JS, 'RUNNER', str(runner)), patch.object(JS, 'SANDBOX', str(sandbox)), \
                    patch.object(JS, '_assets', {}), patch.object(JS, 'node_version', return_value='fixture'):
                first = JS.VERSION
                self.assertEqual(JS.asset_hashes()['runner'], hashlib.sha256(runner.read_bytes()).hexdigest())
                runner.write_bytes(b'// changed runner')
                with self.assertRaisesRegex(JS.JsError, 'assets changed'):
                    JS.asset_snapshot()
                with self.assertRaisesRegex(JS.JsError, 'assets changed'):
                    _ = JS.VERSION
                with patch.object(JS, '_assets', {}):
                    self.assertNotEqual(first, JS.VERSION)

    def test_snapshot_is_detached_and_missing_assets_never_mean_ready(self):
        with patch.object(JS, '_assets', {}):
            one = JS.asset_snapshot()
            one['runner'] = b'forged'
            self.assertNotEqual(JS.asset_snapshot()['runner'], b'forged')
        with patch.object(JS, 'RUNNER', '/missing/symblic-test-runner.js'), self.assertRaises(JS.JsError):
            JS.asset_snapshot()

    def test_parser_and_license_are_frozen_and_parser_is_pinned(self):
        with patch.object(JS, '_assets', {}):
            assets = JS.asset_snapshot()
            self.assertEqual(assets['parser'], Path(JS.PARSER).read_bytes())
            self.assertEqual(assets['license'], Path(JS.PARSER_LICENSE).read_bytes())
            self.assertEqual(hashlib.sha256(assets['parser']).hexdigest(), JS.PARSER_SHA256)
        with tempfile.TemporaryDirectory() as folder:
            parser, license = Path(folder) / 'acorn.js', Path(folder) / 'LICENSE.txt'
            parser.write_bytes(b'// altered parser')
            with patch.object(JS, 'PARSER', str(parser)), patch.object(JS, '_assets', {}):
                with self.assertRaises(JS.JsError) as caught:
                    JS.asset_snapshot()
                self.assertEqual(caught.exception.kind, 'version')
            license.write_bytes(b'fixture license')
            with patch.object(JS, 'PARSER_LICENSE', str(license)), patch.object(JS, '_assets', {}):
                JS.asset_snapshot()
                license.write_bytes(b'changed license')
                with self.assertRaisesRegex(JS.JsError, 'assets changed'):
                    JS.asset_snapshot()

    def test_missing_parser_or_license_is_unavailable_without_execution(self):
        for name in ('PARSER', 'PARSER_LICENSE'):
            with self.subTest(asset=name), patch.object(JS, name, '/missing/symblic-js-test-asset'), \
                    patch.object(JS.subprocess, 'Popen') as launch:
                self.assertFalse(JS.available())
                with self.assertRaises(JS.JsError) as caught:
                    JS.test('function f(){return 1;}', [('f()', '1')])
                self.assertEqual(caught.exception.kind, 'unavailable')
                launch.assert_not_called()

    def test_execution_snapshot_includes_the_same_asset_registry(self):
        self.assertEqual(X.ASSET_FILES, {'symblic/kernel/process_limits.py', 'symblic/linear/worker.py',
                                         'symblic/sandbox/landlock.py', 'symblic/js/runner.js',
                                         'symblic/js/contract_runner.js', 'symblic/js/normalize.js',
                                         'symblic/js/acorn.js', 'symblic/js/acorn-LICENSE.txt'})
        for name in X.ASSET_FILES:
            self.assertEqual(X._RUNTIME[name], hashlib.sha256((X.BASE / name).read_bytes()).hexdigest())

    def test_expired_recheck_deadline_refuses_before_starting_a_process(self):
        with patch.object(JS, 'available', return_value=True), patch.object(JS.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(JS.JsError, 'aggregate JavaScript recheck time budget') as got:
                JS._js_test(None, None, ['function f(){return 1;}'], [['f()', '1']], deadline=time.monotonic()-1)
            self.assertEqual(got.exception.kind, 'budget')
            launch.assert_not_called()

    @unittest.skipUnless(JS.available(), 'local sandboxed node is unavailable')
    def test_deadline_interrupts_slow_candidate_with_budget_outcome(self):
        start = time.monotonic()
        with self.assertRaisesRegex(JS.JsError, 'aggregate JavaScript recheck time budget') as got:
            JS._js_test(None, None, ['function f(){while(true){}}'], [['f()', '1']], deadline=start+0.2)
        self.assertEqual(got.exception.kind, 'budget')
        self.assertLess(time.monotonic()-start, 5)


if __name__ == '__main__':
    unittest.main()
