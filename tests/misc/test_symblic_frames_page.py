"""The frame validator of the studio page (web/studio/symblic-frames.js), run through Node.js.

tests/symblic_frames_check.js loads the page module in a `node:vm` context and checks that character-grid frames
are validated exactly (bounds, duplicate cells, single characters, payloads never echoed in errors). It needs
only Node.js and the page file; the test is skipped when Node.js is not installed.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class FramesPage(unittest.TestCase):
    def test_frame_validation_groups_pass(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node is not installed')
        result = subprocess.run([node, str(ROOT / 'tests/symblic_frames_check.js')],
                                capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'\d+ focused validation groups passed')


if __name__ == '__main__':
    unittest.main()
