"""The Z3 runtime inventory tool (tools/scripts/symblic_linear_provision.py) against temporary fixtures.

The tool only reads an already installed environment and publishes a runtime record; these tests build fake
environments in temporary folders. Nothing is installed, imported from the fake package or executed.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'tools/scripts/symblic_linear_provision.py'
spec = importlib.util.spec_from_file_location('provision_fixture', SCRIPT)
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)


def sha(raw): return hashlib.sha256(raw).hexdigest()


class Provision(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        self.repo = self.root / 'repo'; self.host = self.root / 'host'; self.env = self.host / 'environments/env-v1'
        self.site = self.env / 'lib' / f'python{P.PYTHON_MINOR}' / 'site-packages'
        self.python = self.root / 'python'; self.review = self.root / 'review.json'
        for path in (self.repo / 'symblic/linear', self.env / 'bin', self.site / 'z3/lib', self.site / P.PACKAGE_DIRS[1]):
            path.mkdir(parents=True, mode=0o700)
        for path in self.root.rglob('*'):
            if path.is_dir(): path.chmod(0o700)
        self.write(self.python, b'fake interpreter, never executed')
        (self.env / 'bin/python').symlink_to(self.python)
        self.good_cfg = (f'home = {self.python.parent}\nimplementation = CPython\nuv = 0.12.20\n'
                         f'version_info = {P.PYTHON_VERSION}\ninclude-system-site-packages = false\n').encode('ascii')
        self.write(self.env / 'pyvenv.cfg', self.good_cfg)
        self.write(self.repo / 'symblic/linear/worker.py', b'worker source fixture')
        self.write(self.repo / 'symblic/linear/z3-requirements.lock', b'pinned-lock-fixture')
        self.write(self.site / 'z3/__init__.py', b'raise AssertionError("package must not be imported")')
        self.write(self.site / 'z3/lib/libz3.so', b'fake library, never loaded')
        self.write(self.site / P.PACKAGE_DIRS[1] / 'METADATA', b'Name: z3-solver\nVersion: 4.15.4.0\n\n')
        self.write(self.site / P.PACKAGE_DIRS[1] / 'RECORD', b'fixture,')
        self.expected = {'version': 1, 'worker_sha256': sha(b'worker source fixture'),
                         'requirements_lock_sha256': sha(b'pinned-lock-fixture'), 'package_version': '4.15.4.0'}
        self.write(self.review, json.dumps(self.expected).encode())
        # The fixture is inside a shared agent workspace. Model only the trusted
        # ancestor permissions above its private root, without changing those directories.
        ancestors = set(self.root.parents); real_lstat = Path.lstat
        def lstat(path):
            info = real_lstat(path)
            if path in ancestors:
                parts = list(info); parts[0] &= ~0o022; return os.stat_result(parts)
            return info
        for item in (patch.object(P, 'REPO', self.repo), patch.object(P, 'HOST', self.host),
                     patch.object(P, 'ENV', self.env), patch.object(P, 'SYSTEM_PYTHON', self.python),
                     patch.object(Path, 'lstat', lstat)):
            item.start(); self.addCleanup(item.stop)

    @staticmethod
    def write(path, raw):
        path.write_bytes(raw); path.chmod(0o600)

    def test_inventory_exact_keys_complete_payload_and_no_write_or_execution(self):
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        row = P.inventory(self.review)
        self.assertEqual(row['status'], 'inventory'); self.assertEqual(row['package_files'], 4)
        self.assertEqual(set(row['runtime']), {'python', 'python_sha256', 'worker_sha256', 'purelib', 'z3_version', 'package'})
        self.assertEqual(row['runtime']['python_sha256'], sha(self.python.read_bytes()))
        self.assertEqual(row['runtime_sha256'], sha(P._canonical(row['runtime'])))
        self.assertFalse((self.host / 'runtime.json').exists()); self.assertFalse((self.host / '.provision.lock').exists())
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_create_canonical_private_runtime_idempotently_without_rewriting(self):
        result = P.publish(self.review); target = self.host / 'runtime.json'; raw = target.read_bytes()
        self.assertEqual(result['status'], 'published'); self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(P._canonical(json.loads(raw)), raw); before = target.stat().st_mtime_ns
        again = P.publish(self.review); self.assertEqual(again['status'], 'unchanged')
        self.assertEqual(target.stat().st_mtime_ns, before)
        versions = list((self.host / 'revisions').iterdir()); self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0].read_bytes(), raw)

    def test_drift_requires_exact_explicit_replace_and_keeps_both_versions(self):
        P.publish(self.review); target = self.host / 'runtime.json'; before = target.read_bytes()
        self.write(self.site / 'z3/new.py', b'new pinned payload')
        for expected in (None, '0' * 64, 'bad'):
            with self.assertRaises(P.ProvisionError): P.publish(self.review, replace_sha256=expected)
            self.assertEqual(target.read_bytes(), before)
        result = P.publish(self.review, replace_sha256=sha(before)); after = target.read_bytes()
        self.assertNotEqual(after, before); self.assertEqual(result['previous_sha256'], sha(before))
        self.assertEqual({p.read_bytes() for p in (self.host / 'revisions').iterdir()}, {before, after})

    def test_worker_lock_metadata_interpreter_and_package_symlinks_refuse(self):
        worker = self.repo / 'symblic/linear/worker.py'; self.write(worker, b'drift')
        with self.assertRaises(P.ProvisionError): P.inventory(self.review)
        self.write(worker, b'worker source fixture')
        metadata = self.site / P.PACKAGE_DIRS[1] / 'METADATA'; old = metadata.read_bytes()
        self.write(metadata, old.replace(b'4.15.4.0', b'4.15.5.0'))
        with self.assertRaises(P.ProvisionError): P.inventory(self.review)
        self.write(metadata, old)
        (self.site / 'z3/outside.py').symlink_to(worker)
        with self.assertRaises(P.ProvisionError): P.inventory(self.review)
        (self.site / 'z3/outside.py').unlink()
        target = self.env / 'bin/python'; target.unlink(); target.symlink_to(worker)
        with self.assertRaises(P.ProvisionError): P.inventory(self.review)

    def test_directory_permissions_special_files_and_existing_runtime_symlink_refuse(self):
        self.site.chmod(0o770)
        with self.assertRaises(P.ProvisionError): P.inventory(self.review)
        self.site.chmod(0o700)
        fifo = self.site / 'z3/pipe'; os.mkfifo(fifo)
        with self.assertRaises(P.ProvisionError): P.inventory(self.review)
        fifo.unlink()
        (self.host / 'runtime.json').symlink_to(self.review)
        before = self.review.read_bytes()
        with self.assertRaises(P.ProvisionError): P.publish(self.review)
        self.assertEqual(self.review.read_bytes(), before)

    def test_record_bounds_duplicate_fields_wrong_types_and_unknown_fields_refuse(self):
        good = self.review.read_bytes()
        cases = [b'{"version":1,"version":1}', b'[' * 1000 + b']' * 1000, b'x' * 65537]
        for change in ({'version': True}, {'worker_sha256': False}, {'extra': 1}, {'package_version': 'latest'}):
            bad = copy.deepcopy(self.expected); bad.update(change); cases.append(json.dumps(bad).encode())
        for raw in cases:
            self.write(self.review, raw)
            with self.assertRaises(P.ProvisionError): P.inventory(self.review)
        self.write(self.review, good)
        with patch.object(P, 'MAX_FILES', 3), self.assertRaises(P.ProvisionError): P.inventory(self.review)
        with patch.object(P, 'MAX_PACKAGE', 1), self.assertRaises(P.ProvisionError): P.inventory(self.review)
        with patch.object(P, 'MAX_ENTRIES', 1), self.assertRaises(P.ProvisionError): P.inventory(self.review)

    def test_partial_publication_retry_confirms_durability_and_keeps_original_stop(self):
        original = P._sync_dir
        def fail_active(path):
            if path == self.host and (path / 'runtime.json').exists(): raise OSError('fixture after publication')
            return original(path)
        with patch.object(P, '_sync_dir', side_effect=fail_active), self.assertRaises(OSError): P.publish(self.review)
        self.assertTrue((self.host / 'runtime.json').exists())
        self.assertEqual(P.publish(self.review)['status'], 'unchanged')
        class Stop(BaseException): pass
        stop = Stop('original'); real_close = os.close
        def close_fail(fd): real_close(fd); raise OSError('close failed')
        with patch.object(P.os, 'write', side_effect=stop), patch.object(P.os, 'close', side_effect=close_fail):
            with self.assertRaises(Stop) as caught: P._publish_file(self.host / 'other.json', b'{}')
        self.assertIs(caught.exception, stop); self.assertTrue(stop.__notes__)

    def test_existing_malformed_canonical_runtime_never_replaced(self):
        P.publish(self.review); path = self.host / 'runtime.json'; bad = json.loads(path.read_bytes())
        bad['python'] = False; self.write(path, P._canonical(bad)); before = path.read_bytes()
        with self.assertRaises(P.ProvisionError): P.publish(self.review, replace_sha256=sha(before))
        self.assertEqual(path.read_bytes(), before)

    def test_matching_manually_seeded_runtime_is_archived_without_rewrite(self):
        row = P.inventory(self.review); raw = P._canonical(row['runtime'])
        target = self.host / 'runtime.json'; self.write(target, raw); before = target.stat().st_mtime_ns
        self.assertFalse((self.host / 'revisions').exists())
        result = P.publish(self.review)
        self.assertEqual(result['status'], 'unchanged'); self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertEqual((self.host / 'revisions' / result['versioned_records'][0]).read_bytes(), raw)
        with patch.object(P.fcntl, 'flock', side_effect=BlockingIOError()), \
             patch.object(P, 'LOCK_WAIT', 0), self.assertRaisesRegex(P.ProvisionError, 'busy'):
            P.publish(self.review)
        self.assertEqual(target.read_bytes(), raw)

    def test_config_duplicate_normalized_keys_true_values_and_shadow_refuse(self):
        cfg = self.env / 'pyvenv.cfg'
        for tail in (b'include-system-site-packages = true\n',
                     b'include-system-site-packages = True\n',
                     b' Include-System-Site-Packages = false\n',
                     b'home = /other\n'):
            self.write(cfg, self.good_cfg + tail)
            with self.subTest(tail=tail), self.assertRaises(P.ProvisionError): P.publish(self.review)
            self.assertFalse((self.host / 'runtime.json').exists())
            self.assertFalse((self.host / 'revisions').exists())
        self.write(cfg, self.good_cfg)
        shadow = self.env / 'bin/pyvenv.cfg'; self.write(shadow, self.good_cfg)
        with self.assertRaisesRegex(P.ProvisionError, 'Shadow'): P.inventory(self.review)
        shadow.unlink(); shadow.symlink_to(self.root / 'absent')
        with self.assertRaisesRegex(P.ProvisionError, 'Shadow'): P.inventory(self.review)

    def test_config_exact_home_version_layout_and_bounds(self):
        cfg = self.env / 'pyvenv.cfg'
        cases = [self.good_cfg.replace(b'false', b'False'),
                 self.good_cfg.replace(b'false', b'true'),
                 self.good_cfg.replace(b' = ', b'=', 1),
                 self.good_cfg.replace(b'home', b'Home', 1),
                 self.good_cfg.replace(str(self.python.parent).encode(), b'/unreviewed'),
                 self.good_cfg.replace(P.PYTHON_VERSION.encode(), b'0.0.0'),
                 self.good_cfg.replace(b'CPython', b'PyPy'),
                 self.good_cfg.replace(b'uv = 0.12.20', b'uv = arbitrary'),
                 self.good_cfg.replace(b'uv = 0.12.20', b'unknown = 0.12.20'),
                 self.good_cfg.replace(b'false', b'false '),
                 self.good_cfg.replace(b'\n', b'\r\n'),
                 self.good_cfg + b'\n', b'x' * 4097, b'\xff']
        for raw in cases:
            self.write(cfg, raw)
            with self.subTest(raw=raw[:100]), self.assertRaises(P.ProvisionError): P.inventory(self.review)
        for raw in (self.good_cfg, self.good_cfg.rstrip(b'\n'), b'\n'.join(reversed(self.good_cfg.splitlines()))):
            self.write(cfg, raw)
            self.assertEqual(P.inventory(self.review)['environment_configuration_sha256'], sha(raw))

    def test_explicit_replace_is_cas_even_for_identical_candidate(self):
        P.publish(self.review); target = self.host / 'runtime.json'
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.host / 'revisions').iterdir()}
        raw = target.read_bytes(); mtime = target.stat().st_mtime_ns
        with self.assertRaisesRegex(P.ProvisionError, 'Explicit replacement hash'):
            P.publish(self.review, replace_sha256='0' * 64)
        self.assertEqual(target.read_bytes(), raw); self.assertEqual(target.stat().st_mtime_ns, mtime)
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.host / 'revisions').iterdir()})
        self.assertEqual(P.publish(self.review, replace_sha256=sha(raw))['status'], 'unchanged')
        target.unlink()
        with self.assertRaisesRegex(P.ProvisionError, 'absent'):
            P.publish(self.review, replace_sha256=sha(raw))
        self.assertFalse(target.exists())
        self.assertEqual(P.publish(self.review)['status'], 'published')

    def test_permission_drift_before_open_and_during_read_refuses_publication(self):
        target = self.site / 'z3/__init__.py'; real_open = os.open; real_read = os.read
        changed = []
        def opened(path, *args, **kwargs):
            if Path(path) == target and not changed:
                target.chmod(0o666); changed.append(True)
            return real_open(path, *args, **kwargs)
        with patch.object(P.os, 'open', side_effect=opened), self.assertRaises(P.ProvisionError):
            P.publish(self.review)
        self.assertFalse((self.host / 'runtime.json').exists())
        target.chmod(0o600); target_identity = target.stat().st_ino
        changed.clear()
        def read(fd, size):
            result = real_read(fd, size)
            if os.fstat(fd).st_ino == target_identity and not changed:
                target.chmod(0o666); changed.append(True)
            return result
        with patch.object(P.os, 'read', side_effect=read), self.assertRaises(P.ProvisionError):
            P.publish(self.review)
        self.assertFalse((self.host / 'runtime.json').exists())

    def test_import_has_no_io_or_process_actions(self):
        spec = importlib.util.spec_from_file_location('second_provision', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        # Source loading is the only filesystem operation; the module calls no reader/publisher.
        source = SCRIPT.read_text()
        with patch.object(os, 'open', side_effect=AssertionError('import wrote/read a runtime')), \
             patch.object(os, 'mkdir', side_effect=AssertionError('import created a directory')):
            exec(compile(source, str(SCRIPT), 'exec'), module.__dict__)
        self.assertFalse((self.host / 'runtime.json').exists())


if __name__ == '__main__': unittest.main()
