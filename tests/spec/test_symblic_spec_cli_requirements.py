"""Saved byte-identity requirements and private creation; fake checkers/providers only."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from symblic.spec import build as B
from tests.spec.test_symblic_spec_cli import CODE, SHEET, Fake


class Requirements(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.compiled = B.compile_cards(SHEET, ['fake:child'])
        self.artifacts = {'unit_' + name: code for name, code in CODE.items()}
        plan = self.compiled['plan']
        units = {row['id']: row for row in plan['units']}
        self.output = plan['sheet']['template']['text'].replace(
            B.SP.PLACEHOLDER, '\n\n'.join(CODE[units[ident]['exports'][0]] for ident in plan['assembly_order']))
        self.expected = B.C.code_hash(self.output)

    def record(self, requirement='absent', *, plan_requirement=None):
        folder = self.root / ('record-' + str(len(list(self.root.iterdir()))))
        folder.mkdir()
        compiled = B.compile_cards(SHEET, ['fake:child'], required_output_sha256=plan_requirement)
        (folder / 'program.sym').write_text(compiled['source'])
        if requirement != 'absent':
            (folder / 'meta.json').write_text(json.dumps({'task_cards': {'expected_output_sha256': requirement}}))
        return folder

    def checkpoint(self, folder, *, units=None, **kwargs):
        accepted = self.artifacts if units is None else units
        with patch.object(B.SP, 'accepted_units', return_value=accepted), \
                patch.object(B.JS, '_js_test', return_value={'passed': True}) as checker:
            value = B.checkpoint(folder, **kwargs)
        return value, checker.call_count

    def test_initial_records_are_0600_before_first_content_fsync(self):
        folder = self.root / 'public-parent'; folder.mkdir(mode=0o755)
        modes, real_sync = [], os.fsync
        def sync(fd):
            info = os.fstat(fd)
            if stat.S_ISREG(info.st_mode):
                modes.append(stat.S_IMODE(info.st_mode))
            real_sync(fd)
        prior = os.umask(0o022)
        try:
            with patch('symblic.providers.applicators.Applicators', return_value=Fake()), patch('symblic.kernel.run.Run') as run, \
                    patch('os.fsync', side_effect=sync):
                run.return_value.execute.return_value = {'status': 'failed', 'calls': 0, 'error': None}
                B._run_cards(self.compiled, folder=folder)
        finally:
            os.umask(prior)
        self.assertEqual(modes, [0o600] * 3)
        for name in ('program.sym', 'compiler.json', 'meta.json'):
            self.assertEqual(stat.S_IMODE((folder / name).stat().st_mode), 0o600)

    def test_compilation_pins_requirement_into_source_plan(self):
        compiled = B.compile_cards(SHEET, ['fake:child'], required_output_sha256=self.expected)
        self.assertEqual(compiled['plan']['required_output_sha256'], self.expected)
        self.assertNotEqual(compiled['plan']['sha256'], self.compiled['plan']['sha256'])
        self.assertIn(self.expected, compiled['source'])
        self.assertEqual(compiled['options'], self.compiled['options'])
        self.assertEqual(compiled['settings'], self.compiled['settings'])

    def test_run_enforces_source_requirement_without_repeated_argument(self):
        compiled = B.compile_cards(SHEET, ['fake:child'], required_output_sha256='0' * 64)
        with patch('symblic.providers.applicators.Applicators', return_value=Fake()), patch('symblic.kernel.run.Run') as run:
            run.return_value.execute.return_value = {'status': 'done', 'calls': 0, 'error': None}
            run.return_value.kernel.env.lookup.return_value = SimpleNamespace(value=self.output)
            result = B._run_cards(compiled)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['native_status'], 'done')
        self.assertEqual(result['expected_output_sha256'], '0' * 64)
        self.assertEqual(result['observed_output_sha256'], self.expected)
        self.assertIsNone(result['output'])

    def test_conflicting_run_requirement_refuses_before_provider(self):
        compiled = B.compile_cards(SHEET, ['fake:child'], required_output_sha256=self.expected)
        with patch('symblic.providers.applicators.Applicators') as app, self.assertRaisesRegex(B.SP.SheetError, 'conflicts'):
            B._run_cards(compiled, expected_output_sha256='0' * 64)
        app.assert_not_called()

    def test_saved_hash_cannot_be_omitted_at_checkpoint_or_manifest(self):
        for complete in (False, True):
            with self.subTest(complete=complete), self.assertRaisesRegex(B.SP.SheetError, 'required output'):
                self.checkpoint(self.record('0' * 64), complete=complete)

    def test_conflicting_override_or_record_refuses_before_local_checks(self):
        for saved, source, requested in [(self.expected, None, '0' * 64),
                                          (None, self.expected, '0' * 64),
                                          ('0' * 64, self.expected, None)]:
            with self.subTest(saved=saved, source=source, requested=requested):
                folder = self.record(saved, plan_requirement=source)
                with patch.object(B.JS, '_js_test') as checker, \
                        self.assertRaisesRegex(B.SP.SheetError, 'conflicts'):
                    B.checkpoint(folder, expected_output_sha256=requested)
                checker.assert_not_called()

    def test_partial_checkpoint_retains_pending_requirement_for_missing_units(self):
        result, checks = self.checkpoint(self.record(self.expected), units={'unit_double': CODE['double']})
        self.assertEqual(checks, 1)
        self.assertEqual(result['plan']['required_output_sha256'], self.expected)
        self.assertEqual(result['output_hash_check'], {'required_sha256': self.expected,
                         'observed_sha256': None, 'status': 'pending_incomplete'})
        self.assertEqual(len(result['artifacts']), 1)
        self.assertEqual(len(result['skipped']), 2)

    def test_complete_checkpoint_and_manifest_bind_saved_requirement(self):
        folder = self.record(self.expected)
        partial, _ = self.checkpoint(folder)
        self.assertEqual(partial['output_hash_check']['status'], 'matched')
        manifest, _ = self.checkpoint(folder, complete=True)
        self.assertEqual(manifest['plan']['required_output_sha256'], self.expected)
        self.assertTrue(B.C.verify_manifest(manifest)['ok'])
        self.assertEqual(manifest['output']['text'], self.output)
        with self.assertRaises(B.C.ContractError):
            B.C.verify_manifest(manifest, expected_output_sha256='0' * 64)

    def test_source_bound_requirement_survives_absent_metadata(self):
        folder = self.record(plan_requirement='0' * 64)
        with self.assertRaisesRegex(B.SP.SheetError, 'required output'):
            self.checkpoint(folder, complete=True)

    def test_legacy_no_hash_records_still_export(self):
        for requirement in ('absent', None):
            with self.subTest(requirement=requirement):
                manifest, _ = self.checkpoint(self.record(requirement), complete=True)
                self.assertIsNone(manifest['plan']['required_output_sha256'])
                self.assertEqual(manifest['output']['text'], self.output)
                self.assertTrue(B.C.verify_manifest(manifest)['ok'])

    def test_malformed_saved_requirement_refuses_instead_of_disappearing(self):
        for bad in (True, 12, 'ABC', [], {}):
            with self.subTest(bad=bad):
                folder = self.record(bad)
                with patch.object(B.JS, '_js_test') as checker, self.assertRaises(B.SP.SheetError):
                    B.checkpoint(folder)
                checker.assert_not_called()

    def test_damaged_or_deep_metadata_is_a_bounded_visible_refusal(self):
        for raw in ('{', '[]', '{"task_cards":[]}', '[' * 2000 + '0' + ']' * 2000):
            with self.subTest(raw_prefix=raw[:30]):
                folder = self.record()
                (folder / 'meta.json').write_text(raw)
                with patch.object(B.JS, '_js_test') as checker, self.assertRaises(B.SP.SheetError):
                    B.checkpoint(folder)
                checker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
