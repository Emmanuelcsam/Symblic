"""The QEMU boot check (symblic/os/virtual_boot.py) reports only what it measured.

No VM is started: the launcher returns a stand-in process and every HTTP answer is scripted. The
earlier version of this module reported every check as passed; these tests pin that a check that did
not hold is reported as False, that all_passed is the conjunction of the measured checks, and that the
receipt says success only when everything passed.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/os -t .
"""
import json
import tempfile
import unittest
from unittest.mock import patch

from symblic.os.receipts import get_receipt
from symblic.os.virtual_boot import VirtualBootVerifier


class StandIn:
    def terminate(self):
        pass

    def wait(self):
        return 0


class Page:
    def __init__(self, body, status=200):
        self.body, self.status = body, status

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Boot(unittest.TestCase):
    def run_check(self, root, persisted_after_restart):
        verifier = VirtualBootVerifier(root=root)
        boots = []

        def launch():
            boots.append(len(boots) + 1)
            return StandIn()

        def urlopen(request, timeout=0):
            url = request if isinstance(request, str) else request.full_url
            if url.endswith('/symblic-terminal.html'):
                return Page(b'<h1>SymblicOS Terminal</h1>')               # the stub's fallback page: 27 bytes
            if url.endswith('/terminal/submit'):
                return Page(json.dumps({'type': 'terminal_success'}).encode())
            if url.endswith('/guest/status'):
                persisted = persisted_after_restart if len(boots) == 2 else True
                return Page(json.dumps({'status': 'ok', 'persisted_file': persisted}).encode())
            raise AssertionError(url)

        vitals = {'status': 'online', 'runtime_version': '2.5'}
        with patch.object(verifier, '_launch_vm', side_effect=launch), \
                patch.object(verifier, '_wait_for_service', return_value=vitals), \
                patch('symblic.os.virtual_boot.urllib.request.urlopen', side_effect=urlopen), \
                patch('symblic.os.virtual_boot.time.sleep'):
            return verifier.run_verification()

    def test_unmet_checks_are_reported_false_and_the_receipt_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_check(root, persisted_after_restart=False)
            self.assertEqual({'boot_completion': True, 'browser_access': False, 'deterministic_inspection': True,
                              'file_creation_instruction': True, 'resulting_file_verified': True,
                              'restart_verified': True, 'restart_persistence': False},
                             {k: result[k] for k in ('boot_completion', 'browser_access', 'deterministic_inspection',
                                                     'file_creation_instruction', 'resulting_file_verified',
                                                     'restart_verified', 'restart_persistence')})
            self.assertFalse(result['all_passed'])
            self.assertIn('stub', result['scope'])
            receipt = get_receipt(result['receipt_id'], root + '/receipts')
            self.assertEqual('validation_failure', receipt['result_status'])
            self.assertEqual([True, False, True, True, True, True, False], receipt['validation_results'])


if __name__ == '__main__':
    unittest.main()
