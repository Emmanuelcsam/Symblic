"""The command line's spec-sheet start (tools/symblic-task start --sheet ...) and its autogen view.

tools/symblic-task is a client of an HTTP API that only the original host served; these tests
replace its `request` function, so nothing is sent anywhere. They pin the request body the
coordinator receives for a sheet run and the per-attempt unit counts the command line prints.
The whole module is skipped when the command line cannot be loaded as a module.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from tests.autogen.test_kernel_lane import SHEET

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'tools' / 'symblic-task'


def load_cli():
    loader = importlib.machinery.SourceFileLoader('symblic_task_cli_sheets', str(CLI))
    spec = importlib.util.spec_from_file_location('symblic_task_cli_sheets', str(CLI), loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules['symblic_task_cli_sheets'] = module
    spec.loader.exec_module(module)
    return module


try:
    cli = load_cli()
    CLI_ERROR = ''
except Exception as exc:  # noqa: BLE001 - reported as the skip reason
    cli, CLI_ERROR = None, f'{type(exc).__name__}: {exc}'


@unittest.skipIf(cli is None, f'tools/symblic-task cannot be loaded as a module: {CLI_ERROR}')
class SheetCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autogen-kernel-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.ws = os.path.join(self.tmp.name, 'ws')
        os.makedirs(os.path.join(self.ws, '.git'))
        self.sheet = os.path.join(self.tmp.name, 'handoff.sheet.md')
        Path(self.sheet).write_text(SHEET)
        self.calls = []
        run = {'id': 'autogen-' + 'c' * 24, 'status': 'queued', 'budget': {'agents_started': 0, 'agents_max': 0},
               'policy': {'until_done': True}, 'nodes': [], 'lines': [SHEET]}

        def request(route, body=None, query=None):
            self.calls.append((route, body, query))
            return {'run': run, 'duplicate': False}
        patcher = mock.patch.object(cli, 'request', request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_start_sheet_sends_the_file_verbatim_as_one_local_statement(self):
        code, out = self.main(['start', '--sheet', self.sheet, '--root', self.ws, '--model', 'qwen3:4b-instruct',
                               '--node', 'node09', '--autogen', '--until-done', '--check', '0:node test.js', '--id', 'tetris-1'])
        self.assertEqual(cli.OK, code, out)
        route, body, _ = self.calls[0]
        self.assertEqual('autogen/start', route)
        self.assertEqual({'client_request_id': 'tetris-1', 'instruction': SHEET, 'sheet': True, 'engine': 'local',
                          'model': 'qwen3:4b-instruct', 'node': 'node09', 'cwd': self.ws, 'context_note': '', 'headless': True,
                          'autogen': {'until_done': True, 'checks': {'0': ['node test.js']}}}, body)
        self.assertIn('spec sheet handoff.js on node09 via ollama:qwen3:4b-instruct', out)

    def test_sheet_refusals_happen_before_any_request(self):
        bad = os.path.join(self.tmp.name, 'bad.sheet.md')
        Path(bad).write_text(SHEET.replace('Examples:\n    ready() ==> "ready"\n', ''))
        base = ['start', '--sheet', self.sheet, '--root', self.ws, '--model', 'qwen3:4b-instruct', '--node', 'node09']
        cases = [
            (base + ['--lines', self.sheet], cli.USAGE, '--sheet takes the place of --lines'),
            (base[:5] + ['--node', 'node09'], cli.USAGE, '--sheet needs --model'),
            (base[:7], cli.USAGE, '--sheet needs --node'),
            (base + ['--engine', 'claude'], cli.USAGE, 'runs on the local kernel lane'),
            (base + ['--parallel', '2'], cli.USAGE, '--parallel does not apply to a spec sheet'),
            (base + ['--check', '1:node t.js'], cli.USAGE, 'there are 1 statement(s)'),
        ]
        # the command line checks a sheet locally only when it can import the sheet parser; otherwise the
        # coordinator refuses it (tests/autogen/test_kernel_lane.py covers that refusal)
        if cli.sheet_problems(Path(bad).read_text()) is not None:
            cases.append((['start', '--sheet', bad, '--root', self.ws, '--model', 'm', '--node', 'node09'], cli.REFUSED,
                          'error: unit ready() has no examples'))
        for argv, want, text in cases:
            with self.subTest(text=text):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code, out = self.main(argv)
                self.assertEqual(want, code, out + err.getvalue())
                self.assertIn(text, out + err.getvalue())
        self.assertEqual([], self.calls)

    def test_autogen_get_shows_units_per_kernel_attempt(self):
        attempt = {'id': 'n0-a0', 'kind': 'candidate', 'strategy': 'fresh', 'status': 'failed', 'failure': 'NO_OUTPUT',
                   'engine': 'local', 'node': 'node09', 'model': 'qwen3:4b-instruct', 'task_id': '',
                   'kernel': {'mode': 'build', 'units_accepted': 2, 'units_total': 3, 'stalled': 'next', 'run_dir': '/r/n0-a0'}}
        planner = {'id': 'n0-a1', 'kind': 'planner', 'strategy': 'split', 'status': 'running', 'engine': 'local',
                   'node': 'node09', 'kernel': {'mode': 'split', 'unit': 'next', 'heading': 'next(x)', 'run_dir': '/r/n0-a1'}}
        run = {'id': 'autogen-' + 'd' * 24, 'status': 'active', 'base': {'engine': 'local', 'node': 'node09', 'cwd': '/w',
               'model': 'qwen3:4b-instruct'}, 'lines': [SHEET], 'budget': {'agents_started': 2, 'agents_max': 0, 'deadline': None},
               'order': ['n0'], 'nodes': [{'id': 'n0', 'parent': None, 'depth': 0, 'status': 'pending', 'statement': SHEET,
                                           'progress': {'files': [], 'checks': 0, 'done': 0, 'units': 2},
                                           'attempts': [attempt, planner]}]}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.show_run(run)
        text = out.getvalue()
        self.assertIn('n0-a0 candidate/fresh failed NO_OUTPUT  local@node09 qwen3:4b-instruct  units 2/3 (stopped at next)', text)
        self.assertIn('n0-a1 planner/split running  local@node09  split next(x)', text)
        self.assertIn('build: /r/n0-a1 (log /r/n0-a1.log)', text)
        self.assertIn('units 2', text)
        self.assertIn('n0  pending  progress files 0 checks 0 done 0 units 2  spec sheet handoff.js (3 units)', text)
        view = cli.run_view(run)['nodes'][0]
        self.assertEqual({'mode': 'build', 'units': 2, 'total': 3, 'stalled': 'next', 'unit': '', 'run_dir': '/r/n0-a0'},
                         view['attempts'][0]['kernel'])
        self.assertEqual(2, view['progress']['units'])


if __name__ == '__main__':
    unittest.main()
