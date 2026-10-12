"""Pure functions of the tools/symblic-task command line: statements, lint and next_action. No host is needed."""
import unittest

import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / 'tools' / 'symblic-task'

loader = importlib.machinery.SourceFileLoader('symblic_task_cli', str(SCRIPT_PATH))
spec = importlib.util.spec_from_file_location('symblic_task_cli', str(SCRIPT_PATH), loader=loader)
symblic_task_cli = importlib.util.module_from_spec(spec)
sys.modules['symblic_task_cli'] = symblic_task_cli
spec.loader.exec_module(symblic_task_cli)


class TestSymblicTaskCli(unittest.TestCase):
    def test_statements(self):
        self.assertEqual(symblic_task_cli.statements('a\n\n b '), ['a', 'b'])

    def test_lint_empty(self):
        findings = symblic_task_cli.lint([])
        self.assertIsInstance(findings, list)
        self.assertEqual(len(findings), 1)
        level, _line, _msg = findings[0]
        self.assertEqual(level, 'error')

    def test_lint_short(self):
        findings = symblic_task_cli.lint(['short'])
        errors_line_1 = [
            f for f in findings
            if f[0] == 'error' and f[1] == 1
        ]
        self.assertTrue(len(errors_line_1) > 0)

    def test_lint_create_file_warning_verify(self):
        findings = symblic_task_cli.lint(['Create the file a.txt in the folder /home/x with the line hello world'])
        errors = [f for f in findings if f[0] == 'error']
        self.assertEqual(errors, [])
        verify_warnings = [
            f for f in findings
            if f[0] == 'warning' and 'verify statement' in f[2]
        ]
        self.assertTrue(len(verify_warnings) > 0)

    def test_lint_extend_file_warning_keep_existing(self):
        findings = symblic_task_cli.lint(['Extend the file a.js in the folder /home/x so that it exports the function f'])
        keep_warnings = [
            f for f in findings
            if f[0] == 'warning' and 'keeping every existing part' in f[2]
        ]
        self.assertTrue(len(keep_warnings) > 0)

    def test_next_action_completed(self):
        action = symblic_task_cli.next_action({'status': 'completed'}, [])
        self.assertTrue(action.startswith('done'))

    def test_task_summary_next_action_awaiting_review(self):
        task = {
            'id': 't',
            'status': 'active',
            'mode': 'lines',
            'options': {'engine': 'agy', 'node': 'node-i', 'cwd': '/w'},
            'steps': [{'index': 0, 'status': 'awaiting_review', 'instruction': 'x'}],
        }
        summary = symblic_task_cli.task_summary(task)
        self.assertTrue(summary['next_action'].startswith('review'))


if __name__ == '__main__':
    unittest.main()
