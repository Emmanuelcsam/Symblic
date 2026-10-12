"""CLI termination reaches only owned fake calls; no model, network or service work."""
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.delegate import run as H

WORKER = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from symblic.providers import applicators as symblic_apply
from symblic.delegate import run as H
folder = Path(sys.argv[2])
class Fake:
    def __init__(self, **kwargs): pass
    def call(self, request):
        (folder / 'started').write_text('fake call active')
        while not request['stop'].wait(0.02): pass
        (folder / 'cooperative_cancel').write_text('cancelled')
        return {'ok': False, 'fatal': True, 'error': 'stopped'}
    def cancel_all(self):
        (folder / 'cleanup').write_text('cancelled owned calls')
        return 1
symblic_apply.Applicators = Fake
request = {'template':'typed_transform','calls':1,'params':{
    'instruction':'Copy the number.','data':2,'output_schema':{'type':'integer'}}}
task = folder / 'task.json'; task.write_text(json.dumps(request))
raise SystemExit(H.main(['run',str(task),'--by','ollama:fake','--agent-json']))
'''


class DelegationLifecycle(unittest.TestCase):
    def test_sigterm_and_sigint_reach_owned_provider_and_return_failed_json(self):
        root = str(Path(H.__file__).resolve().parents[2])          # the repository root, for the child's sys.path
        for signum in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=signum), tempfile.TemporaryDirectory() as folder:
                child = subprocess.Popen([sys.executable, '-c', WORKER, root, folder],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                         env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                try:
                    deadline = time.monotonic() + 15
                    while (not Path(folder, 'started').exists() and child.poll() is None
                           and time.monotonic() < deadline):
                        time.sleep(0.02)
                    self.assertTrue(Path(folder, 'started').exists(), 'Fake provider did not start')
                    child.send_signal(signum)
                    stdout, stderr = child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 1, stderr)
                    result = json.loads(stdout)
                    self.assertFalse(result['accepted'])
                    self.assertIsNone(result['result'])
                    self.assertEqual(result['calls'], 1)
                    self.assertTrue(Path(folder, 'cooperative_cancel').exists())
                    self.assertTrue(Path(folder, 'cleanup').exists())
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.communicate()

    def test_exception_cleans_owned_calls_and_restores_signal_handlers(self):
        previous = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)}
        apps = type('Owned', (), {'cancel_all': lambda self: setattr(self, 'cancelled', True)})()
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder, 'task.json'); task.write_text('{}')
            out = io.StringIO()
            with patch('symblic.providers.applicators.Applicators', return_value=apps), \
                    patch.object(H, 'run_task', side_effect=ValueError('injected failure')), \
                    contextlib.redirect_stdout(out):
                status = H.main(['run', str(task), '--agent-json'])
        self.assertEqual(status, 1)
        self.assertFalse(json.loads(out.getvalue())['ok'])
        self.assertTrue(apps.cancelled)
        self.assertEqual({signum: signal.getsignal(signum) for signum in previous}, previous)


if __name__ == '__main__':
    unittest.main()
