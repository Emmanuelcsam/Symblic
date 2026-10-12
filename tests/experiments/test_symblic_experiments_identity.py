"""The experiment registry refuses stale code: fresh processes and copied modules, never live edits."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from symblic.experiments import registry as E


# The smallest importable copy of the package for these checks: the registry, one adapter and the identity helpers.
COPIED = ('symblic/__init__.py', 'symblic/kernel/__init__.py', 'symblic/kernel/identity.py',
          'symblic/mica/__init__.py', 'symblic/mica/source_identity.py',
          'symblic/experiments/__init__.py', 'symblic/experiments/registry.py', 'symblic/experiments/quantum.py')
ROOT = Path(E.__file__).resolve().parents[2]


class AdapterIdentity(unittest.TestCase):
    def exercise(self, code):
        # Each check runs in a fresh process against a private copy of the modules, so the live sources are
        # never edited and the copy's own import markers are what the registry inspects.
        with tempfile.TemporaryDirectory() as tmp:
            for name in COPIED:
                target = Path(tmp) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            env = dict(os.environ, PYTHONPATH=tmp)
            result = subprocess.run([sys.executable, '-c', code], cwd=tmp, env=env, text=True, capture_output=True,
                                    timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_loaded_source_drift_refuses_before_execution(self):
        self.exercise("""
from pathlib import Path
from symblic.experiments import registry as E
from symblic.experiments import quantum as Q
E.MODULES=('symblic.experiments.quantum',)
data=next(r['example'] for r in Q.catalog() if r['id']=='circuit_rewrite')
assert E.run('circuit_rewrite',data)['model_calls']==0
p=Path(Q.__file__);p.write_text(p.read_text()+'\\n# changed after import\\n')
try:E.run('circuit_rewrite',data)
except E.ExperimentError as error:assert str(error)=='loaded_adapter_differs'
else:raise AssertionError('stale import accepted')
""")

    def test_stale_unchecked_bytecode_refuses(self):
        self.exercise("""
from pathlib import Path
import py_compile
p=Path('symblic/experiments/quantum.py')
py_compile.compile(str(p),doraise=True,invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
p.write_text(p.read_text().replace('VERSION = 1','VERSION = 2'))
from symblic.experiments import registry as E
E.MODULES=('symblic.experiments.quantum',)
try:E.run('circuit_rewrite',{'qubits':1,'left':[],'right':[]})
except E.ExperimentError as error:assert str(error)=='loaded_adapter_differs'
else:raise AssertionError('stale bytecode accepted')
""")

    def test_source_drift_during_calculation_refuses(self):
        self.exercise("""
from pathlib import Path
from symblic.experiments import registry as E
from symblic.experiments import quantum as Q
E.MODULES=('symblic.experiments.quantum',)
original=Q.run
def changed(kind,data):
 result=original(kind,data)
 p=Path(Q.__file__);p.write_text(p.read_text()+'\\n# during run\\n')
 return result
Q.run=changed
try:E.run('circuit_rewrite',{'qubits':1,'left':[],'right':[]})
except E.ExperimentError as error:assert str(error)=='loaded_adapter_differs'
else:raise AssertionError('mid-run source drift accepted')
""")

    def test_adapter_input_mutation_is_rejected_and_caller_preserved(self):
        self.exercise("""
from symblic.experiments import registry as E
from symblic.experiments import quantum as Q
E.MODULES=('symblic.experiments.quantum',)
original=Q.run
def changed(kind,data):
 result=original(kind,data);data['qubits']=2;return result
Q.run=changed
data={'qubits':1,'left':[],'right':[]}
try:E.run('circuit_rewrite',data)
except E.ExperimentError as error:assert str(error)=='adapter_mutated_input'
else:raise AssertionError('mutation accepted')
assert data['qubits']==1
""")


if __name__=='__main__':unittest.main()
