"""Import identity (symblic.kernel.identity) and execution pins: loaded-code regression probes.

Each test copies the symblic package into a fresh temporary directory and runs a short script there, so the
copies can be edited, recompiled or shadowed freely. No providers, no network."""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
BUILD = '''
import hashlib
from symblic.kernel import language as S, execution_pins as X
hashes = {n: hashlib.sha256((X.BASE/n).read_bytes()).hexdigest() for n in X.REQUIRED_FILES}
'''
ACCEPT = BUILD + '''
p = X.build('show 5', {}, hashes)
assert X.validate(p, 'show 5', {}) == p
print('ACCEPTED')
'''
REFUSE = BUILD + '''
try:
    X.build('show 5', {}, hashes)
except S.SymblicError as e:
    assert e.kind == 'version', str(e)
    assert 'identity' in e.message or 'bytecode' in e.message, str(e)
    print('REFUSED', e.message)
else:
    raise AssertionError('incorrectly accepted stale/unmarked loaded code')
'''


class LoadedIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(BASE / 'symblic', self.root / 'symblic',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    def run_python(self, script, expected='REFUSED'):
        proc = subprocess.run([sys.executable, '-c', textwrap.dedent(script)],
                              cwd=self.root, text=True, capture_output=True, timeout=180, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(expected, proc.stdout)
        return proc.stdout

    def test_clean_core_helper_and_identity_first_orders(self):
        for imports in ('import symblic.kernel.language\n', 'import symblic.kernel.execution_pins\n',
                        'import symblic.kernel.identity\n', 'import symblic.kernel.epistemic\n'):
            with self.subTest(imports=imports):
                self.run_python(imports + ACCEPT, 'ACCEPTED')

    def test_foreign_module_proxy_does_not_crash_capture_or_validation(self):
        self.run_python('''
import sys, types
class ForeignProxy:
    @property
    def __class__(self):
        return types.ModuleType
proxy = ForeignProxy()
assert isinstance(proxy, types.ModuleType)
assert not issubclass(type(proxy), types.ModuleType)
sys.modules['fixture_foreign_cffi_proxy'] = proxy
''' + ACCEPT, 'ACCEPTED')

    def test_proxy_under_registered_alias_is_refused_without_descriptor_crash(self):
        self.run_python(ACCEPT + '''
import sys, types
class ForeignProxy:
    @property
    def __class__(self):
        return types.ModuleType
sys.modules['fixture.symblic.kernel.epistemic'] = ForeignProxy()
try:
    X.validate(p, 'show 5', {})
except S.SymblicError as e:
    assert e.kind == 'version'
    assert 'not a Python module' in e.message, e.message
    print('REFUSED')
else:
    raise AssertionError('accepted a proxy for a registered module')
''')

    def test_original_preloaded_helper_then_disk_version_change(self):
        self.run_python('''
from symblic.kernel import epistemic as EP
from pathlib import Path
path = Path(EP.__file__)
path.write_text(path.read_text().replace('VERSION = 1', 'VERSION = 2', 1))
Path(EP.__cached__).unlink(missing_ok=True)  # Old cache cannot expose this gap.
assert EP.VERSION == 1
''' + REFUSE)

    def test_identity_helper_itself_preloaded_then_disk_changed(self):
        self.run_python('''
from symblic.kernel import identity as I
from pathlib import Path
p = Path(I.__file__)
p.write_text(p.read_text().replace('VERSION = 1', 'VERSION = 2', 1))
Path(I.__cached__).unlink(missing_ok=True)
assert I.VERSION == 1
''' + REFUSE)

    def test_same_semantic_code_but_changed_comments_still_refuses(self):
        self.run_python('''
from symblic.kernel import epistemic as EP
from pathlib import Path
p = Path(EP.__file__)
p.write_text(p.read_text() + '\\n# exact source changed after import\\n')
''' + REFUSE)

    def test_after_capture_late_helper_load_then_drift_refuses(self):
        self.run_python(BUILD + '''
p = X.build('show 5', {}, hashes)
from symblic.kernel import epistemic as EP
from pathlib import Path
f = Path(EP.__file__)
f.write_text(f.read_text().replace('VERSION = 1', 'VERSION = 2', 1))
try:
    X.validate(p, 'show 5', {})
except S.SymblicError as e:
    assert e.kind == 'version'
    print('REFUSED')
else:
    raise AssertionError('accepted changed disk')
''')

    def test_current_disk_of_loaded_optional_module_is_also_checked(self):
        self.run_python(BUILD + '''
p = X.build('show 5', {}, hashes)
from symblic.providers import applicators as R
assert 'symblic/providers/applicators.py' not in X.REQUIRED_FILES
from pathlib import Path
f = Path(R.__file__)
f.write_text(f.read_text() + '\\n# changed optional loaded source\\n')
try:
    X.validate(p, 'show 5', {})
except S.SymblicError as e:
    assert e.kind == 'version'
    print('REFUSED')
else:
    raise AssertionError('accepted changed optional loaded source')
''')

    def test_stale_accepted_pyc_helper_marks_executing_code_mismatch(self):
        self.run_python('''
import py_compile, os
from pathlib import Path
p = Path('symblic/kernel/epistemic.py')
py_compile.compile(str(p), invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
p.write_text(p.read_text().replace('VERSION = 1', 'VERSION = 2', 1))
from symblic.kernel import epistemic as EP
assert EP.VERSION == 1
assert EP._symblic_import_identity['matched'] is False
''' + REFUSE)

    def test_stale_pyc_of_identity_helper_refuses(self):
        self.run_python('''
import py_compile
from pathlib import Path
p = Path('symblic/kernel/identity.py')
py_compile.compile(str(p), invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
p.write_text(p.read_text().replace('VERSION = 1', 'VERSION = 2', 1))
from symblic.kernel import identity as I
assert I.VERSION == 1 and not I._symblic_import_identity['matched']
''' + REFUSE)

    def test_checked_hash_pyc_refreshes_and_passes(self):
        self.run_python('''
import py_compile
from pathlib import Path
p = Path('symblic/kernel/epistemic.py')
py_compile.compile(str(p), invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
p.write_text(p.read_text().replace('VERSION = 1', 'VERSION = 2', 1))
from symblic.kernel import epistemic as EP
assert EP.VERSION == 2 and EP._symblic_import_identity['matched']
''' + ACCEPT, 'ACCEPTED')

    def test_preloaded_legacy_source_stays_unmarked_after_files_are_updated(self):
        self.run_python('''
from pathlib import Path
p = Path('symblic/kernel/epistemic.py')
original = p.read_text()
rows = original.splitlines(keepends=True)
legacy = ''.join(row for row in rows if not row.startswith(('# Import identity', '_symblic_identity =', '_symblic_import_identity =')))
p.write_text(legacy)
from symblic.kernel import epistemic as EP
assert not hasattr(EP, '_symblic_import_identity')
p.write_text(original)
Path(EP.__cached__).unlink(missing_ok=True)
''' + REFUSE)

    def test_unmarked_canonical_module_refuses(self):
        self.run_python('''
import sys, types
from pathlib import Path
m = types.ModuleType('symblic.kernel.epistemic')
m.__file__ = str(Path('symblic/kernel/epistemic.py').resolve())
m.VERSION = 1                           # what kernel_id() reads from it
sys.modules['symblic.kernel.epistemic'] = m
''' + REFUSE)

    def test_alias_cannot_copy_another_modules_valid_marker(self):
        self.run_python('''
import sys, types
from symblic.kernel import epistemic as EP
m = types.ModuleType('private_alias')
m.__dict__.update(EP.__dict__)
sys.modules['private_alias'] = m
''' + REFUSE)

    def test_unmarked_main_copy_refuses(self):
        self.run_python('''
import sys, types
from pathlib import Path
m = types.ModuleType('__main__')
m.__file__ = str(Path('symblic/kernel/epistemic.py').resolve())
sys.modules['__main__'] = m
''' + REFUSE)

    def test_real_main_execution_is_marked_before_core_import(self):
        path = self.root / 'symblic/kernel/epistemic.py'
        path.write_text(path.read_text() + '\n' + ACCEPT)
        self.run_python("import runpy; runpy.run_module('symblic.kernel.epistemic', run_name='__main__', alter_sys=True)",
                        'ACCEPTED')

    def test_independently_loaded_alias_from_same_source_passes(self):
        self.run_python('''
import sys, importlib.util
from pathlib import Path
p = Path('symblic/kernel/epistemic.py').resolve()
spec = importlib.util.spec_from_file_location('private_alias', p)
m = importlib.util.module_from_spec(spec)
sys.modules['private_alias'] = m
spec.loader.exec_module(m)
''' + ACCEPT, 'ACCEPTED')

    def test_identical_source_other_installation_refuses(self):
        self.run_python('''
import sys, importlib.util, shutil
from pathlib import Path
Path('other/symblic/kernel').mkdir(parents=True)
p = Path('other/symblic/kernel/epistemic.py').resolve()
shutil.copyfile('symblic/kernel/epistemic.py', p)
spec = importlib.util.spec_from_file_location('other_alias', p)
m = importlib.util.module_from_spec(spec)
sys.modules['other_alias'] = m
spec.loader.exec_module(m)
''' + REFUSE)

    def test_invalid_caller_cannot_manufacture_record(self):
        self.run_python('''
import sys
from symblic.kernel import epistemic as EP, identity as I
row = I.record(EP.__file__, sys._getframe().f_code)
assert not row['matched'] and row['reason'] == 'invalid_module_frame'
''' + ACCEPT, 'ACCEPTED')

    def test_capture_failure_remains_sticky_after_bad_alias_removed(self):
        self.run_python('''
import sys, types
from pathlib import Path
m = types.ModuleType('private_alias')
m.__file__ = str(Path('symblic/kernel/epistemic.py').resolve())
sys.modules['private_alias'] = m
from symblic.kernel import language as S, execution_pins as X
assert X._RUNTIME_LOADED_PROBLEMS
sys.modules.pop('private_alias')
''' + REFUSE)

    def test_import_marker_mutation_refuses(self):
        self.run_python('''
from symblic.kernel import epistemic as EP
EP._symblic_import_identity['sha256'] = '0' * 64
''' + REFUSE)

    def test_audit_registry_and_module_count_bounds(self):
        self.run_python('''
from symblic.kernel import identity as I
assert I.audit('.', ['x.py'] * 257, {})
assert I.audit('.', ['../x.py'], {})
I.MAX_MODULES = 0
assert I.audit('.', [], {}) == ('loaded module registry exceeds its finite bound',)
print('BOUNDED')
''', 'BOUNDED')

    def test_source_compile_budget_refuses_before_compile(self):
        self.run_python('''
from symblic.kernel import identity as I
I.MAX_TOTAL_SOURCE_BYTES = 0
from symblic.kernel import epistemic as EP
assert EP._symblic_import_identity['reason'] == 'compile_budget'
''' + REFUSE)


class MarkerInstallation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = BASE / 'tools/scripts/symblic_import_markers.py'
        if not path.is_file():
            raise unittest.SkipTest('the marker installer tools/scripts/symblic_import_markers.py is not present')
        spec = importlib.util.spec_from_file_location('identity_marker_installer', path)
        cls.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.installer)

    def test_marker_is_first_after_docstring_and_future_and_idempotent(self):
        raw = b'#!/usr/bin/env python3\n"""Module description."""\nfrom __future__ import annotations\nimport symblic\n'
        marked = self.installer.marked(raw)
        self.assertLess(marked.index(b'_symblic_import_identity ='), marked.index(b'import symblic\n'))
        self.assertEqual(self.installer.marked(marked), marked)
        compile(marked, '<fixture>', 'exec')

    def test_late_existing_marker_is_not_blessed_by_check(self):
        raw = ('import symblic\n' + self.installer.MARKER).encode()
        with self.assertRaisesRegex(ValueError, 'late or malformed'):
            self.installer.marked(raw)

    def test_marker_only_inside_docstring_is_not_blessed_by_check(self):
        raw = ('"""\n' + self.installer.MARKER + '"""\nimport symblic\n').encode()
        with self.assertRaisesRegex(ValueError, 'late or malformed'):
            self.installer.marked(raw)

    def test_helper_requires_executable_final_self_record(self):
        self.installer.check_helper((BASE / 'symblic/kernel/identity.py').read_bytes())
        for raw in (b'VERSION = 1\n', b'# _symblic_import_identity = record(__file__, sys._getframe().f_code)\n'):
            with self.assertRaisesRegex(ValueError, 'self-record'):
                self.installer.check_helper(raw)


if __name__ == '__main__':
    unittest.main()
