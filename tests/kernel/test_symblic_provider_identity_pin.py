"""Import identity of the Ollama observation module (symblic.providers.ollama_call) and the marker installer.

The module is registered (optional) for execution pins and also runs standalone with the standard library only;
tools/scripts/symblic_import_markers.py installs and checks the identity markers of every registered module."""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.kernel import test_symblic_identity as identity_tests

BASE = Path(__file__).resolve().parents[2]


class ProviderPin(unittest.TestCase):
    setUp = identity_tests.LoadedIdentity.setUp
    run_python = identity_tests.LoadedIdentity.run_python

    def test_controller_import_before_kernel_is_recorded(self):
        self.run_python('from symblic.providers import ollama_call as B\nassert B._symblic_import_identity["matched"]\n' + identity_tests.ACCEPT,
                        'ACCEPTED')

    def test_controller_loaded_code_drift_refuses_even_without_old_cache(self):
        self.run_python('''
from symblic.providers import ollama_call as B
from pathlib import Path
p = Path(B.__file__)
p.write_text(p.read_text().replace('VERSION = 1', 'VERSION = 2', 1))
Path(B.__cached__).unlink(missing_ok=True)
assert B.VERSION == 1
''' + identity_tests.REFUSE)

    def test_optional_provider_absence_keeps_pure_pinned_execution(self):
        self.run_python('from pathlib import Path\nPath("symblic/providers/ollama_call.py").unlink()\n' + identity_tests.ACCEPT,
                        'ACCEPTED')


class Standalone(unittest.TestCase):
    def test_standalone_and_controller_without_symblic_keep_stdlib_interface(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'observer.py'
            shutil.copy2(BASE / 'symblic/providers/ollama_call.py', target)
            proc = subprocess.run([sys.executable, '-I', '-S', str(target)], cwd=folder,
                                  capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertIn('expected --model', proc.stderr)
            self.assertNotIn('ModuleNotFoundError', proc.stderr)
            script = ('import importlib.util; '
                      f's=importlib.util.spec_from_file_location("observer", {str(target)!r}); '
                      'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
                      'assert m.VERSION == 1; assert m.check(None) is None')
            proc = subprocess.run([sys.executable, '-I', '-S', '-c', script], cwd=folder,
                                  capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_installer_checks_controller_marker_position(self):
        spec = importlib.util.spec_from_file_location('marker_installer', BASE / 'tools/scripts/symblic_import_markers.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw = b'"""Observer."""\nfrom __future__ import annotations\nimport json\n'
        marked = module.marked(raw, standalone=True)
        self.assertEqual(module.marked(marked, standalone=True), marked)
        self.assertLess(marked.index(b"if __name__"), marked.index(b'import json'))
        with self.assertRaises(ValueError):
            module.marked(b'import json\n' + module.CONTROLLER_MARKER.encode(), standalone=True)
        with self.assertRaises(ValueError):
            module.marked(module.MARKER.encode(), standalone=True)


class RegistryReadiness(unittest.TestCase):
    """Static rebase checks also run before bulk marker installation."""
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('marker_registry_readiness', BASE / 'tools/scripts/symblic_import_markers.py')
        cls.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.installer)

    def test_current_registry_preserves_proof_command_and_optional_observer(self):
        names = self.installer.registry(BASE)
        self.assertIn('symblic/adapters/proof_command.py', names)
        self.assertIn('symblic/kernel/identity.py', names)
        self.assertIn('symblic/providers/ollama_call.py', names)
        self.assertIn('symblic/constructor/core.py', names)
        # The closed evaluator never imports target runtime code.
        values = self.installer.registry_values(BASE)
        self.assertIn('symblic/kernel/identity.py', values['REQUIRED_FILES'])
        self.assertIn('symblic/adapters/proof_command.py', values['REQUIRED_FILES'])
        self.assertNotIn('symblic/providers/ollama_call.py', values['REQUIRED_FILES'])

    def test_constructor_union_is_static_and_unrelated_source_never_executes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'symblic/kernel').mkdir(parents=True)
            (root / 'symblic/kernel/execution_pins.py').write_text('''
raise RuntimeError('target must never execute')
PYTHON_FILES = frozenset({'symblic/kernel/identity.py', 'optional.py'})
REQUIRED_FILES = frozenset({'symblic/kernel/identity.py'})
_REFORM_FILES = frozenset(['reform.py'])
_CONSTRUCTOR_FILES = frozenset(('constructor.py',))
PYTHON_FILES = PYTHON_FILES | _REFORM_FILES | _CONSTRUCTOR_FILES
REQUIRED_FILES = REQUIRED_FILES | _REFORM_FILES | _CONSTRUCTOR_FILES
''')
            values = self.installer.registry_values(root)
            self.assertEqual({'symblic/kernel/identity.py', 'optional.py', 'reform.py', 'constructor.py'},
                             values['PYTHON_FILES'])
            self.assertNotIn('optional.py', values['REQUIRED_FILES'])

    def test_equivalent_existing_marker_preserves_exact_bytes_but_late_or_duplicate_refuses(self):
        marker = self.installer.MARKER.partition('\n')[2].replace("'", '"').encode()
        raw = b'"""Existing constructor."""\nfrom __future__ import annotations\n' + marker + b'import json\n'
        self.assertEqual(raw, self.installer.marked(raw))
        for malformed in (b'import json\n' + marker, raw + marker,
                          marker.replace(b'.record(', b'.other(')):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                self.installer.marked(malformed)

    def test_dynamic_registry_and_malformed_collections_refuse_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'symblic/kernel').mkdir(parents=True)
            marker = root / 'should-not-exist'
            for expression in (f'__import__("pathlib").Path({str(marker)!r}).touch()',
                               'frozenset({"symblic/kernel/identity.py"}, extra=True)',
                               'frozenset({"symblic/kernel/identity.py"}, {"extra.py"})',
                               'frozenset({("nested.py",)})', '"symblic/kernel/identity.py"',
                               'frozenset({"symblic/kernel/identity.py"}) | missing_name',
                               'frozenset({"symblic/kernel/identity.py", "../escape.py"})'):
                with self.subTest(expression=expression):
                    (root / 'symblic/kernel/execution_pins.py').write_text(
                        'PYTHON_FILES = ' + expression + '\nREQUIRED_FILES = frozenset({"symblic/kernel/identity.py"})\n')
                    with self.assertRaises(ValueError):
                        self.installer.registry(root)
                    self.assertFalse(marker.exists())

    def test_final_registry_marker_plan_is_compileable_without_writes(self):
        for name in sorted(self.installer.registry(BASE)):
            with self.subTest(name=name):
                path = BASE / name
                raw = path.read_bytes()
                after = (self.installer.check_helper(raw) if name == 'symblic/kernel/identity.py' else
                         self.installer.marked(raw, standalone=name in self.installer.STANDALONE_FILES))
                compile(after, str(path), 'exec', dont_inherit=True)
                self.assertEqual(path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
