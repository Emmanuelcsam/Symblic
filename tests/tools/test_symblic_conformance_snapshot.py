"""Source admission regressions; never launch a provider or load a live runtime."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'tools/scripts/symblic_conformance.py'
spec = importlib.util.spec_from_file_location('isolated_conformance', SCRIPT)
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class SnapshotAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conformance-admission-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.registry = ("REQUIRED_FILES = frozenset({'symblic/kernel/execution_pins.py', 'symblic/kernel/identity.py'})\n"
                         "ASSET_FILES = frozenset({'symblic/js/runner.js'})\n"
                         "LIBRARIES = frozenset({'constants'})\n")
        self.write('symblic/kernel/execution_pins.py', self.registry)
        for name in C.EXTRA_RUNTIME_FILES | {'symblic/kernel/identity.py', 'symblic/js/runner.js',
                C.LIBRARY_PATH.format('constants'), C.IDENTITY_SOURCE, C.SOUNDNESS_SOURCE}:
            self.write(name, '# public source\n')
        for name in ('symblic/__init__.py', 'symblic/kernel/__init__.py', 'symblic/spec/__init__.py',
                     'symblic/js/__init__.py', 'tests/__init__.py', 'tests/kernel/__init__.py'):
            self.write(name, '')        # package markers the snapshot copies with the modules

    def write(self, name, source):
        target = self.repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)

    def test_missing_required_identity_refuses_before_any_worker(self):
        (self.repo / 'symblic/kernel/identity.py').unlink()
        with patch.object(C.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'required public source unavailable: symblic/kernel/identity.py'):
                C.snapshot_and_run(repo=self.repo)
            run.assert_not_called()

    def test_unknown_future_dependency_requires_explicit_review(self):
        self.write('symblic/kernel/execution_pins.py', self.registry + "REQUIRED_FILES = REQUIRED_FILES | {'private_provider.py'}\n")
        self.write('private_provider.py', 'raise AssertionError("must never import")\n')
        with patch.object(C.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'unreviewed execution closure: private_provider.py'):
                C.snapshot_and_run(repo=self.repo)
            run.assert_not_called()

    def test_missing_required_asset_also_refuses_before_worker(self):
        (self.repo / 'symblic/js/runner.js').unlink()
        with patch.object(C.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'required public source unavailable: symblic/js/runner.js'):
                C.snapshot_and_run(repo=self.repo)
            run.assert_not_called()

    def test_unreviewed_library_cannot_expand_snapshot_authority(self):
        self.write('symblic/kernel/execution_pins.py', self.registry + "LIBRARIES = LIBRARIES | {'owner_private'}\n")
        with patch.object(C.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'unreviewed execution closure: owner_private'):
                C.snapshot_and_run(repo=self.repo)
            run.assert_not_called()

    def test_only_declared_libraries_and_required_future_helper_are_copied(self):
        self.write(C.LIBRARY_PATH.format('owner_private'), 'private unrelated source')
        self.write('symblic/kernel/json_schema.py', 'reviewed future helper')
        content, _ = C.snapshot_content(self.repo)
        self.assertNotIn(C.LIBRARY_PATH.format('owner_private'), content)
        self.assertNotIn('symblic/kernel/json_schema.py', content)
        self.write('symblic/kernel/execution_pins.py', self.registry + "REQUIRED_FILES = REQUIRED_FILES | {'symblic/kernel/json_schema.py'}\n")
        content, registry = C.snapshot_content(self.repo)
        self.assertIn('symblic/kernel/json_schema.py', content)
        self.assertIn('symblic/kernel/json_schema.py', registry['REQUIRED_FILES'])

    def test_registry_reader_never_executes_source(self):
        marker = self.repo / 'executed'
        # Unrelated code is parsed but not executed, and a computed declaration is refused.
        raw = f"open({str(marker)!r}, 'w').write('wrong')\n" + self.registry
        self.assertEqual(C.execution_registry(raw)['LIBRARIES'], ['constants'])
        self.assertFalse(marker.exists())
        with self.assertRaisesRegex(RuntimeError, 'unsupported execution registry expression'):
            C.execution_registry(raw + "REQUIRED_FILES = set(__import__('os').listdir('.'))\n")
        with self.assertRaisesRegex(RuntimeError, 'unsupported execution registry assignment'):
            C.execution_registry(raw + "REQUIRED_FILES |= {'unreviewed.py'}\n")
        self.assertFalse(marker.exists())

    def test_symlink_and_special_file_refuse_without_blocking(self):
        target = self.repo / 'symblic/kernel/identity.py'
        target.unlink()
        target.symlink_to(self.repo / 'symblic/kernel/execution_pins.py')
        with self.assertRaisesRegex(RuntimeError, 'symlink refused'):
            C.snapshot_content(self.repo)
        target.unlink()
        os.mkfifo(target)
        with self.assertRaisesRegex(RuntimeError, 'not a bounded regular file'):
            C.snapshot_content(self.repo)

    def test_concurrent_source_change_refuses_snapshot(self):
        original = C.read_public_file
        reads = 0
        def changing(repo, name, **options):
            nonlocal reads
            data = original(repo, name, **options)
            if name == 'symblic/kernel/identity.py':
                reads += 1
                if reads > 1:
                    return data + b'# changed\n'
            return data
        with patch.object(C, 'read_public_file', side_effect=changing):
            with self.assertRaisesRegex(RuntimeError, 'source changed while copying'):
                C.snapshot_content(self.repo)

    def test_child_environment_has_no_live_paths_or_credentials(self):
        with patch.dict(os.environ, {'PYTHONPATH': '/live/checkout', 'HOME': '/owner',
                                     'PROVIDER_TOKEN': 'not-forwarded'}):
            env = C.isolated_env(self.repo, '7')
        self.assertNotIn('PROVIDER_TOKEN', env)
        self.assertNotIn('PYTHONPATH', env)
        self.assertEqual(env['PYTHONHASHSEED'], '7')
        self.assertTrue(Path(env['HOME']).is_relative_to(self.repo))
        self.assertTrue(Path(env['TMPDIR']).is_relative_to(self.repo))
        self.assertEqual(env['PYTHONNOUSERSITE'], '1')

    def test_source_read_byte_limit_is_checked_before_read(self):
        with patch.object(C, 'MAX_FILE_BYTES', 8):
            with self.assertRaisesRegex(RuntimeError, 'not a bounded regular file'):
                C.snapshot_content(self.repo)

    def test_bundle_overflow_stops_before_reading_later_sources(self):
        ceiling = len(SCRIPT.read_bytes()) + len((self.repo / C.IDENTITY_SOURCE).read_bytes()) - 1
        original = C.read_public_file
        visited = []
        def tracked(repo, name, **options):
            visited.append(name)
            return original(repo, name, **options)
        with patch.object(C, 'MAX_BUNDLE_BYTES', ceiling), patch.object(C, 'read_public_file', side_effect=tracked):
            with self.assertRaisesRegex(RuntimeError, 'bundle byte limit'):
                C.snapshot_content(self.repo)
        self.assertNotIn('symblic/kernel/identity.py', visited)


if __name__ == '__main__':
    unittest.main()
