"""The offline acceptance suite (symblic/os/acceptance.py) and the scoped release manifest
(symblic/os/release_manifest.py): temporary stores only, and every kind of outside work forbidden.

The suite must pass in a private scratch root it removes afterwards, never touch SYMBLICOS_ROOT, start
no process, open no socket or URL, count a failure, and refuse to run once closed; its legacy method
names must answer "Not performed". The manifest must never turn a missing, failed, inconsistent or
merely claimed report into a verified state, and its writer must keep everything under the given root.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/os -t .
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from symblic.os.acceptance import HostedAcceptanceSuite
from symblic.os.release_manifest import build_final_release_manifest, generate_final_release_manifest


def report(*, passed=True, scope='isolated_fixture_smoke'):
    return {'scope': scope, 'live_validation': False, 'all_passed': passed,
            'total_tests': 1, 'passed_tests': int(passed), 'failed_tests': int(not passed),
            'tests': [{'test': 'fixture', 'passed': passed}], 'not_covered': ['live inference']}


class IsolatedAcceptance(unittest.TestCase):
    def test_default_ignores_live_root_and_starts_no_external_work(self):
        with tempfile.TemporaryDirectory() as live:
            marker = Path(live, 'never-touch.txt')
            marker.write_text('original')
            with patch.dict('os.environ', {'SYMBLICOS_ROOT': live}), \
                    patch('subprocess.Popen', side_effect=AssertionError('real process forbidden')) as processes, \
                    patch('socket.create_connection', side_effect=AssertionError('network forbidden')) as sockets, \
                    patch('urllib.request.urlopen', side_effect=AssertionError('HTTP forbidden')) as http:
                with HostedAcceptanceSuite() as suite:
                    scratch = Path(suite.dev_root)
                    self.assertFalse(scratch.is_relative_to(live))
                    result = suite.run_all()
                    self.assertTrue(result['all_passed'], result['tests'])
                    self.assertEqual(16, result['total_tests'])
                    self.assertEqual('isolated_fixture_smoke', result['scope'])
                    self.assertFalse(result['live_validation'])
                    self.assertTrue(result['not_covered'])
                    self.assertTrue(all(row['scope'] == result['scope'] for row in result['tests']))
                self.assertFalse(scratch.exists())
                for blocked in [processes, sockets, http]:
                    blocked.assert_not_called()
            self.assertEqual([marker], list(Path(live).iterdir()))
            self.assertEqual('original', marker.read_text())

    def test_explicit_root_is_a_scratch_parent_and_repeat_run_is_independent(self):
        with tempfile.TemporaryDirectory() as parent:
            marker = Path(parent, 'user-file.txt')
            marker.write_text('preserved')
            with HostedAcceptanceSuite(parent) as suite:
                self.assertNotEqual(Path(parent), Path(suite.dev_root))
                self.assertTrue(Path(suite.dev_root).is_relative_to(parent))
                for _ in range(2):
                    result = suite.run_all()
                    self.assertTrue(result['all_passed'], result['tests'])
            self.assertEqual([marker], list(Path(parent).iterdir()))
            self.assertEqual('preserved', marker.read_text())

    def test_failure_is_counted_and_closed_suite_cannot_recreate_files(self):
        with HostedAcceptanceSuite() as suite:
            with patch.object(suite, 'test_filesystem_creation', return_value=(False, 'fault fixture')):
                result = suite.run_all()
            self.assertFalse(result['all_passed'])
            self.assertEqual(1, result['failed_tests'])
            self.assertEqual(result['total_tests'] - 1, result['passed_tests'])
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            suite.run_all()

    def test_old_misleading_names_never_claim_an_unrun_boundary(self):
        with HostedAcceptanceSuite() as suite:
            for name in ['test_terminal_static_assets', 'test_model_inventory_fixture',
                         'test_terminal_http_loading', 'test_local_model_discovery',
                         'test_one_local_model_invocation', 'test_service_restart',
                         'test_browser_reconnection', 'test_unauthorized_executable_launch']:
                passed, detail = getattr(suite, name)()
                self.assertFalse(passed, name)
                self.assertTrue(detail.startswith('Not performed:'), name)
            names = {row['test'] for row in suite.run_all()['tests']}
            self.assertNotIn('service_restart', names)
            self.assertNotIn('terminal_http_loading', names)
            self.assertNotIn('browser_reconnection', names)
            self.assertNotIn('one_local_model_invocation', names)
            self.assertNotIn('terminal_static_assets', names)
            self.assertNotIn('model_inventory_fixture_mapping', names)


class ScopedManifest(unittest.TestCase):
    def build(self, acceptance=None, **overrides):
        args = dict(hardware_info={}, acceptance_results=acceptance or {}, virtual_boot_results={},
                    physical_inspection={}, models_info={}, frameworks_info={})
        args.update(overrides)
        return build_final_release_manifest(**args)

    def test_missing_reports_do_not_default_to_pass_or_invent_hardware(self):
        result = self.build()
        summary = result['acceptance_suite_summary']
        self.assertFalse(summary['all_passed'])
        self.assertEqual('unverified', summary['status'])
        self.assertEqual(0, summary['tests_run'])
        self.assertIsNone(result['hardware_target']['node_name'])
        self.assertIsNone(result['hardware_target']['ram_gib'])
        for state in result['subsystem_states'].values():
            self.assertEqual('unverified', state['state'])

    def test_complete_fixture_report_is_component_tested_only(self):
        fixture = report()
        fixture['live_validation'] = True  # cannot widen a fixture's declared boundary
        result = self.build(fixture)
        self.assertTrue(result['acceptance_suite_summary']['all_passed'])
        self.assertFalse(result['acceptance_suite_summary']['live_validation'])
        hosted = result['subsystem_states']['hosted_terminal_engine']
        self.assertEqual('component_tested', hosted['state'])
        self.assertFalse(hosted['live_validation'])
        self.assertEqual('isolated_fixture_smoke', hosted['scope'])
        self.assertEqual('unverified', result['subsystem_states']['bootable_virtual_environment']['state'])

    def test_failed_and_inconsistent_reports_cannot_promote_state(self):
        for value in [report(passed=False), {'all_passed': True},
                      {**report(), 'total_tests': 2}, {**report(), 'passed_tests': True},
                      {**report(), 'tests': []}, {**report(), 'all_passed': False}]:
            result = self.build(value)
            self.assertFalse(result['acceptance_suite_summary']['all_passed'])
            self.assertEqual('unverified', result['subsystem_states']['hosted_terminal_engine']['state'])

    def test_supplied_integration_claims_stay_unvalidated_reports(self):
        result = self.build(report(), virtual_boot_results={'verified': True, 'receipt_id': 'unvalidated'},
                            models_info={'models': ['fixture-model'], 'healthy': True, 'digest': 'reported'},
                            frameworks_info={'all_passed': True}, physical_inspection={'state': 'installed'})
        states = result['subsystem_states']
        for name in ['bootable_virtual_environment', 'local_models', 'framework_integrations', 'physical_bare_metal_installation']:
            self.assertEqual('unverified', states[name]['state'])
        self.assertNotIn('verified_digest', states['local_models'])
        self.assertIsNone(states['local_models']['target_node'])
        self.assertEqual('unvalidated', states['bootable_virtual_environment']['virtual_boot_receipt'])
        self.assertEqual({'all_passed': True}, states['framework_integrations']['reported_results'])

    def test_explicit_writer_persists_complete_scope_and_matching_receipt_in_scratch(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as unrelated:
            with patch.dict('os.environ', {'SYMBLICOS_ROOT': unrelated}), \
                    patch('symblic.os.release_manifest.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='fixture-head\n')):
                result = generate_final_release_manifest({}, report(), {}, {}, {}, {}, output_root=root)
            stored = json.loads(Path(root, 'releases', 'symblicos_final_manifest.json').read_text())
            self.assertEqual(result, stored)
            receipt = json.loads(Path(root, 'receipts', result['manifest_receipt_id'] + '.json').read_text())
            self.assertEqual('success', receipt['result_status'])
            self.assertIn('no live subsystem verification', receipt['stdout'])
            self.assertEqual([], list(Path(unrelated).iterdir()))
            self.assertEqual(str(Path(root, 'receipts')), result['receipts_directory'])
            self.assertEqual('fixture-head', result['source_revisions']['git_head'])
            self.assertEqual('isolated_fixture_smoke', stored['acceptance_suite_summary']['scope'])
            self.assertEqual('unverified', stored['subsystem_states']['local_models']['state'])


if __name__ == '__main__':
    unittest.main()
