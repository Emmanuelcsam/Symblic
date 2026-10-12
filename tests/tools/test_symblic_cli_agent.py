"""Installed CLI entrypoint emits one JSON document; no model or external action."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class AgentCLI(unittest.TestCase):
    def cli(self, command, source):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'task.sym'); path.write_text(source)
            env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
            env.pop('DASHBOARD_DIR', None)
            result = subprocess.run([str(ROOT / 'tools/symblic'), command, str(path), '--agent-json'],
                                    cwd=folder, env=env, text=True, capture_output=True, timeout=30)
            return result, json.loads(result.stdout)

    def test_check_is_structured_success_or_failure_with_locations(self):
        result, data = self.cli('check', 'let answer = 8.\nshow answer.\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(data['ok'])
        result, data = self.cli('check', 'use profile=verified.\nasertt false.\n')
        self.assertEqual(result.returncode, 1)
        self.assertFalse(data['ok'])
        self.assertTrue(data['errors'][0]['line'])

    def test_preview_has_exact_manifest_and_no_provider_is_called(self):
        result, data = self.cli('preview', 'ask x: Int "Return 8" by "fake:a".\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Return 8', data['next']['prompt'])

    def test_kernel_run_keeps_progress_out_of_json_stdout(self):
        result, data = self.cli('run', 'let answer = 1/3 * 3.\nshow answer.\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(data['calls'], 0)
        self.assertEqual(data['outputs'][0]['text'], '1')

