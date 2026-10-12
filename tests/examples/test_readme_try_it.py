"""The no-model steps of the root README's "Try it in ten minutes", run exactly as a reader would run them.

Steps 1 to 3 need no model: the kernel-identity program, the preview of the first ask, and a run whose ask is
answered by examples/stand-in-answer.py through a `command:` applicator, then replayed from its record. Each
command runs tools/symblic in a subprocess inside a temporary folder. Step 4 (a real Ollama model) is not tested.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = str(ROOT / 'tools' / 'symblic')
ROOT_PROGRAM = ('ask root: Int in 1..9 "Find the positive integer whose square is nine."\n'
                'ensure root * root = 9 else retry.\nshow root.\n')


class ReadmeTryIt(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        (self.dir / 'root.sym').write_text(ROOT_PROGRAM, encoding='utf-8')
        self.env = {**os.environ, 'SYMBLIC_PYTHON': sys.executable}

    def cli(self, *args, env=None):
        result = subprocess.run([CLI, *args], cwd=self.dir, env=env or self.env, capture_output=True, text=True,
                                timeout=300, check=False)
        return result.returncode, result.stdout + result.stderr

    def test_step_1_the_kernel_identity_program_gives_its_documented_fingerprint(self):
        code, out = self.cli('run', str(ROOT / 'examples/10-kernel-identity.sym'), '--max-calls', '0')
        self.assertEqual(code, 0, out)
        self.assertIn('done: fingerprint fff6d4efbecb4a3a', out)

    def test_step_2_preview_shows_the_first_ask_and_calls_no_model(self):
        code, out = self.cli('preview', 'root.sym', '--by', 'ollama:qwen3:4b-instruct')
        self.assertEqual(code, 0, out)
        self.assertIn('ollama:qwen3:4b-instruct would be sent, for root (line 1)', out)
        self.assertIn('Find the positive integer whose square is nine.', out)

    def test_step_3_a_stand_in_answers_and_the_record_replays_without_it(self):
        env = {**self.env, 'SYMBLIC_COMMAND_STAND_IN': f'{sys.executable} {ROOT / "examples/stand-in-answer.py"}'}
        code, out = self.cli('run', 'root.sym', '--by', 'command:stand-in', '--dir', 'run0', env=env)
        self.assertEqual(code, 0, out)
        self.assertIn('done: fingerprint ad282d55e1782c53 · 1 asks · 1 calls', out)
        code, out = self.cli('replay', 'run0')                 # no stand-in configured: only the record answers
        self.assertEqual(code, 0, out)
        self.assertIn('done: fingerprint ad282d55e1782c53 · 1 asks · 0 calls (1 replayed)', out)

    def test_step_3_a_wrong_answer_is_refused_by_the_check(self):
        env = {**self.env,
               'SYMBLIC_COMMAND_STAND_IN': f'{sys.executable} {ROOT / "examples/stand-in-answer.py"} 4'}
        code, out = self.cli('run', 'root.sym', '--by', 'command:stand-in', '--dir', 'run1', env=env)
        self.assertNotEqual(code, 0, out)
        self.assertIn('ensure failed: root * root = 9', out)


if __name__ == '__main__':
    unittest.main()
