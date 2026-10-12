"""The autogen lane of the tools/symblic-task command line: request bodies, rendering, wait, lint delegation.

request() is stubbed: no host, agent runner, store or agent is touched, so these run without the host. Statement files live under tempfile.
"""
import unittest

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / 'tools' / 'symblic-task'

loader = importlib.machinery.SourceFileLoader('symblic_task_cli_autogen', str(SCRIPT_PATH))
spec = importlib.util.spec_from_file_location('symblic_task_cli_autogen', str(SCRIPT_PATH), loader=loader)
cli = importlib.util.module_from_spec(spec)
sys.modules['symblic_task_cli_autogen'] = cli
spec.loader.exec_module(cli)
REAL_REQUEST = cli.request     # CliCase stubs request(); one test drives the real one over a fake opener
STUCK_HINT = ('resume: symblic-task autogen resume autogen-' + 'a' * 24 + ' [--agents-max N] [--wall-seconds S] '
              'after changing the statement, the checks or the catalogue')

GOOD = ('Create the file a.txt in the folder {ws} containing the single line alpha and nothing else\n'
        'Create the file b.txt in the folder {ws} containing the single line beta, then verify both and write verify.txt\n')


class Recorder:
    """Stands in for request(): records every call, answers from canned responses per route."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = dict(responses or {})

    def __call__(self, route, body=None, query=None):
        self.calls.append((route, body, query))
        answer = self.responses.get(route, {})
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def run_row(**over):
    row = {
        'id': 'autogen-' + 'a' * 24, 'client_request_id': 'ag-1', 'status': 'active', 'error': '',
        'created': 1760000000.0, 'updated': 1760000100.0,
        'base': {'engine': 'agy', 'model': '', 'effort': '', 'node': 'host', 'cwd': '/w', 'context_note': '',
                 'headless': True},
        'lines': ['Create the file a.txt in the folder /w with alpha', 'Create the files b.js and c.js in the folder /w'],
        'budget': {'agents_started': 4, 'agents_max': 24, 'deadline': 1760021600.0},
        'order': ['n0', 'n1'],
        'nodes': [
            {'id': 'n0', 'index': 0, 'parent': None, 'depth': 0, 'statement': 'Create the file a.txt in the folder /w with alpha',
             'status': 'accepted', 'winner': 'n0-a1', 'children': [], 'generation': 0, 'attempts': [
                 {'id': 'n0-a0', 'kind': 'candidate', 'strategy': 'fresh', 'engine': 'agy', 'node': 'host', 'model': '',
                  'generation': 0, 'task_id': 't-0', 'status': 'failed', 'failure': 'NO_OUTPUT', 'error': '',
                  'verdict': {'passed': False, 'checks': [
                      {'kind': 'exists', 'file': 'a.txt', 'passed': False, 'public': True, 'output': 'a.txt was not created'},
                      {'kind': 'hidden', 'passed': False, 'public': False, 'output': 'SECRET-HIDDEN-OUTPUT'}]}},
                 {'id': 'n0-a1', 'kind': 'regen', 'strategy': 'feedback', 'engine': 'agy', 'node': 'host', 'model': '',
                  'generation': 0, 'task_id': 't-1', 'status': 'accepted', 'failure': None,
                  'verdict': {'passed': True, 'checks': [{'kind': 'exists', 'file': 'a.txt', 'passed': True, 'public': True}]}}]},
            {'id': 'n1', 'index': 1, 'parent': None, 'depth': 0, 'statement': 'Create the files b.js and c.js in the folder /w',
             'status': 'split', 'winner': 'n1-a2', 'children': ['n1.0', 'n1.1'], 'generation': 0, 'attempts': [
                 {'id': 'n1-a2', 'kind': 'planner', 'strategy': 'split', 'engine': 'agy', 'node': 'host',
                  'task_id': 't-2', 'status': 'accepted', 'failure': None}]},
            {'id': 'n1.0', 'index': 0, 'parent': 'n1', 'depth': 1, 'statement': 'Create the file b.js in the folder /w',
             'status': 'accepted', 'winner': 'n1.0-a0', 'children': [], 'generation': 0, 'attempts': [
                 {'id': 'n1.0-a0', 'kind': 'candidate', 'strategy': 'fresh', 'engine': 'agy', 'node': 'host',
                  'task_id': 't-3', 'status': 'accepted'}]},
            {'id': 'n1.1', 'index': 1, 'parent': 'n1', 'depth': 1, 'statement': 'Create the file c.js in the folder /w',
             'status': 'pending', 'winner': '', 'children': [], 'generation': 0, 'attempts': [
                 {'id': 'n1.1-a0', 'kind': 'candidate', 'strategy': 'fresh', 'engine': 'claude', 'node': 'node-a',
                  'task_id': 't-4', 'status': 'running'}]},
        ],
        'final': None, 'resume_required': False,
    }
    row.update(over)
    return row


def stuck_row():
    """An until_done run whose last node ran out of novel actions: unlimited agents, no clock."""
    row = run_row(status='stuck', error='Statement n1.1 is stuck: no eligible strategy remains: CHECK_FAILURE',
                  budget={'agents_started': 9, 'agents_max': 0, 'deadline': None}, policy={'until_done': True})
    node = row['nodes'][3]
    node.update(status='stuck', stale=2, progress={'files': ['c.js'], 'checks': 1, 'done': 0},
                error='no eligible strategy remains: CHECK_FAILURE; every novel action at this subdivision was tried')
    node['attempts'][0].update(status='failed', failure='CHECK_FAILURE')
    return row


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='symblic-cli-autogen-')
        self.ws = os.path.join(self.tmp.name, 'ws')
        os.makedirs(os.path.join(self.ws, '.git'))
        self.lines_file = os.path.join(self.tmp.name, 'lines.txt')
        with open(self.lines_file, 'w', encoding='utf-8') as f:
            f.write(GOOD.format(ws=self.ws))
        self.rec = Recorder({'autogen/start': {'run': run_row(status='queued'), 'duplicate': False},
                             'tasks/start': {'task': {'id': 'task-1', 'status': 'queued'}, 'duplicate': False}})
        patches = [mock.patch.object(cli, 'request', self.rec), mock.patch.object(cli, '_POLICY', cli._POLICY)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(argv)
        return rc, out.getvalue()


class TestAutogenStart(CliCase):
    def test_autogen_start_posts_policy_and_lines(self):
        rc, out = self.main([
            'start', '--lines', self.lines_file, '--cwd', self.ws, '--node', 'node-a', '--engine', 'claude',
            '--model', 'opus', '--candidates', '2', '--regenerate', '3', '--decompose', '1', '--children', '3',
            '--handoff', '2', '--agents-max', '12', '--attempt-seconds', '900', '--wall-seconds', '7200',
            '--strategies', 'fresh, feedback,other_node', '--check', '0:test -f a.txt', '--check', '0:grep -q alpha a.txt',
            '--check', '1:true', '--final', 'test -f verify.txt', '--final', 'true', '--hidden', 'test -s b.txt',
            '--no-syntax', '--allow-no-change', '--id', 'ag-test-1'])
        self.assertEqual(rc, cli.OK, out)
        self.assertEqual(len(self.rec.calls), 1)
        route, body, query = self.rec.calls[0]
        self.assertEqual(route, 'autogen/start')
        self.assertIsNone(query)
        self.assertEqual(set(body), {'client_request_id', 'instruction', 'node', 'cwd', 'context_note', 'headless',
                                     'autogen', 'engine', 'model'})
        self.assertNotIn('mode', body)
        self.assertEqual(body['client_request_id'], 'ag-test-1')
        self.assertEqual(body['instruction'], '\n'.join(cli.statements(GOOD.format(ws=self.ws))))
        self.assertEqual((body['node'], body['cwd'], body['engine'], body['model']), ('node-a', self.ws, 'claude', 'opus'))
        self.assertIs(body['headless'], True)
        self.assertEqual(body['autogen'], {
            'candidates': 2, 'regenerate': 3, 'depth': 1, 'children': 3, 'generations': 2, 'agents_max': 12,
            'attempt_seconds': 900, 'wall_seconds': 7200, 'strategies': ['fresh', 'feedback', 'other_node'],
            'checks': {'0': ['test -f a.txt', 'grep -q alpha a.txt'], '1': ['true']},
            'final': ['test -f verify.txt', 'true'], 'hidden': ['test -s b.txt'],
            'syntax': False, 'require_change': False})
        self.assertIn('follow: symblic-task autogen wait autogen-' + 'a' * 24, out)

    def test_autogen_flag_alone_uses_defaults_headless_and_checkout_note(self):
        rc, out = self.main(['start', '--lines', self.lines_file, '--root', self.ws, '--autogen', '--engine', 'agy'])
        self.assertEqual(rc, cli.OK, out)
        route, body, _ = self.rec.calls[0]
        self.assertEqual(route, 'autogen/start')
        self.assertEqual(body['autogen'], {})
        self.assertIs(body['headless'], True)
        self.assertEqual(body['cwd'], self.ws)
        self.assertEqual(body['engine'], 'agy')
        # candidates live in own checkouts: the note maps the project folder onto the checkout,
        # never the plain folder lock that would send them into the owner's copy
        self.assertTrue(body['context_note'].startswith(cli.AUTOGEN_FOLDER.format(cwd=self.ws)))
        self.assertIn(cli.CHECKOUT_LOCK, body['context_note'])
        self.assertNotIn(cli.FOLDER_LOCK.format(root=self.ws), body['context_note'])
        for key in ('mode', 'auto', 'worktree', 'parallel', 'auto_next'):
            self.assertNotIn(key, body)

    def test_instruction_text_runs_autogen_with_lint(self):
        rc, _ = self.main(['start', '--instruction', GOOD.format(ws=self.ws), '--cwd', self.ws, '--candidates', '1'])
        self.assertEqual(rc, cli.OK)
        self.assertEqual(self.rec.calls[0][1]['instruction'].count('\n'), 1)
        rc, out = self.main(['start', '--instruction', 'too short', '--cwd', self.ws, '--autogen'])
        self.assertEqual(rc, cli.REFUSED)
        self.assertIn('error line 1', out)
        self.assertEqual(len(self.rec.calls), 1)

    def test_no_headless_and_perpetual(self):
        rc, _ = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--perpetual', '600', '--no-headless'])
        self.assertEqual(rc, cli.OK)
        body = self.rec.calls[0][1]
        self.assertIs(body['headless'], False)
        self.assertEqual(body['autogen'], {'perpetual': True, 'interval_seconds': 600})

    def test_lint_errors_refuse_before_any_request(self):
        with open(self.lines_file, 'w', encoding='utf-8') as f:
            f.write('short\n')
        rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--autogen'])
        self.assertEqual(rc, cli.REFUSED)
        self.assertIn('error line 1', out)
        self.assertEqual(self.rec.calls, [])

    def test_bad_check_flags_refuse(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            for check in ('5:true', 'true', 'x:true', '0:'):
                rc = cli.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--check', check])
                self.assertEqual(rc, cli.USAGE, check)
            rc = cli.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--candidates', 'two'])
            self.assertEqual(rc, cli.USAGE)
        self.assertIn('--check 5: there are 2 statement(s), indexed from 0', err.getvalue())
        self.assertEqual(self.rec.calls, [])

    def test_plain_task_flags_refused_with_autogen(self):
        for extra in (['--parallel', '2'], ['--worktree'], ['--auto-next'], ['--no-auto'], ['--mode', 'agent']):
            rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--autogen'] + extra)
            self.assertEqual(rc, cli.USAGE, extra)
            self.assertIn('does not apply to an autogen run', out)
        self.assertEqual(self.rec.calls, [])

    def test_workspace_and_id_length_required(self):
        rc, out = self.main(['start', '--lines', self.lines_file, '--autogen'])
        self.assertEqual(rc, cli.USAGE)
        self.assertIn('name the workspace', out)
        rc, _ = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--autogen', '--id', 'x' * 121])
        self.assertEqual(rc, cli.USAGE)
        self.assertEqual(self.rec.calls, [])

    def test_policy_module_normalize_refusal_stops_start(self):
        def normalize(spec):
            raise ValueError('candidates must be from 1 to 4; 9 was given.')
        cli._POLICY = types.SimpleNamespace(lint=lambda lines, root='': [], normalize=normalize)
        rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--candidates', '9'])
        self.assertEqual(rc, cli.USAGE)
        self.assertIn('autogen policy refused: candidates must be from 1 to 4', out)
        self.assertEqual(self.rec.calls, [])

    def test_json_output(self):
        rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--autogen', '--json'])
        self.assertEqual(rc, cli.OK)
        import json
        data = json.loads(out)
        self.assertEqual(data['id'], 'autogen-' + 'a' * 24)
        self.assertFalse(data['duplicate'])
        self.assertEqual(data['run']['status'], 'queued')

    def test_v2_flags_map_to_policy_keys(self):
        rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--until-done', '--designer',
                             '--no-self-split', '--novelty-limit', '3', '--saturation', '4'])
        self.assertEqual(rc, cli.OK, out)
        route, body, _ = self.rec.calls[0]
        self.assertEqual(route, 'autogen/start')
        self.assertEqual(body['autogen'], {'until_done': True, 'designer': True, 'self_split': False,
                                           'novelty_limit': 3, 'saturation': 4})

    def test_each_v2_flag_alone_starts_an_autogen_run(self):
        cases = ((['--until-done'], {'until_done': True}), (['--designer'], {'designer': True}),
                 (['--no-self-split'], {'self_split': False}), (['--novelty-limit', '1'], {'novelty_limit': 1}),
                 (['--saturation', '0'], {'saturation': 0}))      # a given 0 is sent, not dropped as falsy
        for extra, policy in cases:
            del self.rec.calls[:]
            rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws] + extra)
            self.assertEqual(rc, cli.OK, (extra, out))
            self.assertEqual([c[0] for c in self.rec.calls], ['autogen/start'], extra)
            self.assertEqual(self.rec.calls[0][1]['autogen'], policy, extra)

    def test_parse_v2_flags(self):
        opts, args = cli.parse(['start', '--until-done', '--designer', '--no-self-split', '--novelty-limit', '3',
                                '--saturation', '0'])
        self.assertEqual(args, ['start'])
        self.assertEqual(opts, {'until_done': True, 'designer': True, 'no_self_split': True, 'novelty_limit': '3',
                                'saturation': '0'})
        self.assertTrue(cli.autogen_requested(opts))

    def test_zero_means_unlimited_only_with_until_done(self):
        self.rec.responses['autogen/start'] = {
            'run': run_row(status='queued', policy={'until_done': True},
                           budget={'agents_started': 0, 'agents_max': 0, 'deadline': None}), 'duplicate': False}
        rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--agents-max', '0',
                             '--wall-seconds', '0', '--until-done'])
        self.assertEqual(rc, cli.OK, out)
        self.assertEqual(self.rec.calls[0][1]['autogen'], {'agents_max': 0, 'wall_seconds': 0, 'until_done': True})
        self.assertIn('agents_max unlimited  until done', out)
        # without --until-done the shared policy refuses 0 before any request (the server applies the same rule)
        for flag in ('--agents-max', '--wall-seconds'):
            del self.rec.calls[:]
            rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, flag, '0'])
            self.assertEqual(rc, cli.USAGE, flag)
            self.assertIn('0 means unlimited and needs until_done true', out)
            self.assertEqual(self.rec.calls, [])

    def test_until_done_caps_are_sent_only_when_given(self):
        # --until-done alone sends no cap, so the policy's until_done default applies: unlimited agents, no clock
        rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--until-done'])
        self.assertEqual(rc, cli.OK, out)
        sent = self.rec.calls[0][1]['autogen']
        self.assertEqual(sent, {'until_done': True})
        policy = cli.policy_module().normalize(sent)
        self.assertEqual((policy['agents_max'], policy['wall_seconds']), (0, 0))
        # an explicit cap is sent as given and honoured as a safety cap
        del self.rec.calls[:]
        self.rec.responses['autogen/start'] = {
            'run': run_row(status='queued', policy={'until_done': True},
                           budget={'agents_started': 0, 'agents_max': 30, 'deadline': 1760021600.0}), 'duplicate': False}
        rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--until-done',
                             '--agents-max', '30', '--wall-seconds', '7200'])
        self.assertEqual(rc, cli.OK, out)
        sent = self.rec.calls[0][1]['autogen']
        self.assertEqual(sent, {'agents_max': 30, 'wall_seconds': 7200, 'until_done': True})
        policy = cli.policy_module().normalize(sent)
        self.assertEqual((policy['agents_max'], policy['wall_seconds']), (30, 7200))
        self.assertIn('agents_max 30  until done', out)

    def test_out_of_range_v2_values_refused_before_any_request(self):
        for extra, message in ((['--novelty-limit', '0'], 'novelty_limit must be from 1 to 8'),
                               (['--saturation', '17'], 'saturation must be from 0 to 16')):
            rc, out = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--until-done'] + extra)
            self.assertEqual(rc, cli.USAGE, extra)
            self.assertIn('autogen policy refused: ' + message, out)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--novelty-limit', 'x']),
                             cli.USAGE)
        self.assertIn('--novelty-limit needs a whole number', err.getvalue())
        self.assertEqual(self.rec.calls, [])

    def test_usage_documents_v2_flags(self):
        rc, out = self.main(['--help'])
        self.assertEqual(rc, cli.OK)
        for text in ('[--until-done] [--designer] [--no-self-split] [--novelty-limit N] [--saturation N]',
                     'One agent per line is the default (--candidates 1)', '--until-done removes the clock and count caps',
                     'unless you give --agents-max/--wall-seconds explicitly', 'until the checks pass or the', 'reopen a',
                     'resume RUN_ID [--agents-max N] [--wall-seconds S]', "resume's flags raise a spent cap"):
            self.assertIn(text, out)


class TestPlainStartUnchanged(CliCase):
    def test_plain_start_posts_tasks_start_unchanged(self):
        rc, out = self.main(['start', '--lines', self.lines_file, '--root', self.ws, '--id', 'plain-1'])
        self.assertEqual(rc, cli.OK, out)
        route, body, _ = self.rec.calls[0]
        self.assertEqual(route, 'tasks/start')
        self.assertEqual(body, {
            'client_request_id': 'plain-1', 'instruction': '\n'.join(cli.statements(GOOD.format(ws=self.ws))),
            'mode': 'lines', 'node': 'host', 'cwd': self.ws, 'auto': True, 'worktree': False, 'engine': 'agy',
            'context_note': cli.FOLDER_LOCK.format(root=self.ws)})
        self.assertIn('follow: symblic-task wait task-1', out)

    def test_plain_start_flags(self):
        rc, _ = self.main(['start', '--lines', self.lines_file, '--cwd', self.ws, '--headless', '--auto-next',
                           '--parallel', '2', '--worktree', '--no-auto', '--no-headless'])
        self.assertEqual(rc, cli.OK)
        route, body, _ = self.rec.calls[0]
        self.assertEqual(route, 'tasks/start')
        self.assertTrue(body['headless'] and body['auto_next'] and body['worktree'])
        self.assertEqual((body['parallel'], body['auto']), (2, False))
        self.assertEqual(body['context_note'], cli.CHECKOUT_LOCK)
        self.assertNotIn('autogen', body)

    def test_parse_repeatable_and_existing(self):
        opts, args = cli.parse(['autogen', 'get', 'X', '--check', '0:a', '--check', '1:b', '--final', 'f',
                                '--max', '5', '--json', '--tasks', '--autogen', '--no-syntax'])
        self.assertEqual(args, ['autogen', 'get', 'X'])
        self.assertEqual(opts['check'], ['0:a', '1:b'])
        self.assertEqual(opts['final'], ['f'])
        self.assertEqual(opts['max'], '5')
        self.assertTrue(opts['json'] and opts['tasks'] and opts['autogen'] and opts['no_syntax'])


class TestRendering(CliCase):
    def test_show_run_tree(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.show_run(run_row())
        text = out.getvalue()
        lines = text.splitlines()
        self.assertIn('active', lines[0])
        self.assertIn('workspace /w', lines[0])
        self.assertIn('budget: agents 4/24', text)
        self.assertIn('n0  accepted  winner n0-a1', text)
        self.assertIn('n0-a0 candidate/fresh failed NO_OUTPUT  agy@host', text)
        self.assertIn('check exists a.txt: a.txt was not created', text)
        self.assertIn('n0-a1 regen/feedback accepted', text)
        self.assertNotIn('SECRET-HIDDEN-OUTPUT', text)
        self.assertIn('check hidden : (hidden)', text)
        self.assertIn('n1  split  winner n1-a2  -> n1.0, n1.1', text)
        # depth indentation: children are indented under their parent, after it and before the end
        n1 = next(i for i, x in enumerate(lines) if x.strip().startswith('n1  split'))
        n10 = next(i for i, x in enumerate(lines) if x.strip().startswith('n1.0  accepted'))
        indent = lambda s: len(s) - len(s.lstrip())
        self.assertGreater(n10, n1)
        self.assertEqual(indent(lines[n10]), indent(lines[n1]) + 2)
        self.assertIn('n1.1-a0 candidate/fresh running  claude@node-a', text)
        self.assertIn('task: t-4', text)
        self.assertTrue(lines[-1].startswith('  next: wait: n1.1 has 1 attempt running'), lines[-1])

    def test_show_run_with_tasks_final_and_failure(self):
        row = run_row(status='failed', error='Every statement was accepted, but a final check failed: make test',
                      final={'checks': [{'kind': 'final', 'command': 'true', 'passed': True, 'output': ''},
                                        {'kind': 'final', 'command': 'make test', 'passed': False, 'output': 'x\nFAILED 2'}],
                             'passed': False},
                      tasks={'t-4': {'steps': [{'url': '/terminal?session=9'}]}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.show_run(row)
        text = out.getvalue()
        self.assertIn('final: 1/2 check(s) passed', text)
        self.assertIn('failed: make test: FAILED 2', text)
        self.assertIn('terminal: /terminal?session=9', text)
        self.assertIn('next: failed: Every statement was accepted, but a final check failed: make test', text)

    def test_run_next(self):
        self.assertTrue(cli.run_next(run_row(status='completed')).startswith('done: every statement accepted'))
        self.assertEqual(cli.run_next(run_row(status='cancelled')), 'done: cancelled')
        self.assertEqual(cli.run_next(run_row(status='failed', error='Statement n0 failed: x')), 'failed: Statement n0 failed: x')
        self.assertIn('autogen resume', cli.run_next(run_row(status='unknown', error='Coordinator interrupted')))
        self.assertTrue(cli.run_next(run_row(resume_required=True)).startswith('resume:'))
        self.assertEqual(cli.run_next(run_row(status='stuck', error='Statement n0 is stuck: x')), STUCK_HINT)

    def test_status_line(self):
        line = cli.run_status_line(run_row())
        self.assertEqual(line, 'active n0:accepted(2 attempts) n1:split(1 attempt) n1.0:accepted(1 attempt) '
                               'n1.1:pending(1 attempt)')

    def test_get_list_control_routes(self):
        self.rec.responses.update({'autogen/get': {'run': run_row()}, 'autogen': {'runs': [run_row(), run_row(status='failed')]},
                                   'autogen/control': {'run': run_row(status='cancelled')}})
        rc, _ = self.main(['autogen', 'get', 'autogen-' + 'a' * 24, '--tasks'])
        self.assertEqual(rc, cli.OK)
        self.assertEqual(self.rec.calls[-1], ('autogen/get', None, {'id': 'autogen-' + 'a' * 24, 'tasks': '1'}))
        rc, out = self.main(['autogen', 'list', '--status', 'failed'])
        self.assertEqual(rc, cli.OK)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn('failed', out)
        self.assertIn('1/2', out)
        rc, out = self.main(['autogen', 'cancel', 'autogen-' + 'a' * 24])
        self.assertEqual(rc, cli.OK)
        self.assertEqual(self.rec.calls[-1], ('autogen/control', {'id': 'autogen-' + 'a' * 24, 'action': 'cancel'}, None))
        self.assertIn('next: done: cancelled', out)
        rc, _ = self.main(['autogen', 'resume', 'autogen-' + 'a' * 24])
        self.assertEqual(self.rec.calls[-1][1]['action'], 'resume')
        self.assertEqual(self.main(['autogen', 'nope'])[0], cli.USAGE)
        self.assertEqual(self.main(['autogen', 'get'])[0], cli.USAGE)

    def render(self, row):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.show_run(row)
        return out.getvalue()

    def test_show_run_stuck_prints_resume_hint_and_unlimited_budget(self):
        text = self.render(stuck_row())
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith('autogen-' + 'a' * 24 + '  stuck  '), lines[0])
        self.assertEqual(lines[1], '  budget: agents 9/unlimited  until done')
        self.assertNotIn('deadline', text)
        self.assertIn('n1.1  stuck  stale 2  progress files 1 checks 1 done 0  Create the file c.js', text)
        self.assertEqual((text.count('stale '), text.count('progress ')), (1, 1))   # other nodes print as before
        self.assertIn('error: Statement n1.1 is stuck', text)
        self.assertEqual(lines[-1], '  next: ' + STUCK_HINT)

    def test_budget_lines(self):
        text = self.render(run_row())
        self.assertEqual(text.splitlines()[1], f'  budget: agents 4/24  deadline {cli._when(1760021600.0)}')
        for word in ('until done', 'unlimited', 'stale', 'progress', 'items'):
            self.assertNotIn(word, text)
        # until_done with a clock but no agent cap, and with an agent cap but no clock
        row = run_row(budget={'agents_started': 4, 'agents_max': 0, 'deadline': 1760021600.0}, policy={'until_done': True})
        self.assertEqual(self.render(row).splitlines()[1],
                         f'  budget: agents 4/unlimited  deadline {cli._when(1760021600.0)}  until done')
        row = run_row(budget={'agents_started': 4, 'agents_max': 30, 'deadline': None}, summary={'until_done': True})
        self.assertEqual(self.render(row).splitlines()[1], '  budget: agents 4/30  until done')

    def test_perpetual_node_shows_items_total(self):
        node = dict(run_row()['nodes'][0], status='pending', winner='', generation=5, perpetual=True, items_total=37)
        row = run_row(nodes=[node], order=['n0'], lines=[node['statement']])
        self.assertIn('n0  pending  gen 5  items 37  Create the file a.txt', self.render(row))
        node['items_total'] = 0                      # a lane that has found nothing yet still shows its count
        self.assertIn('n0  pending  gen 5  items 0  Create the file a.txt', self.render(row))

    def test_run_view_carries_v2_fields(self):
        view = cli.run_view(stuck_row())
        self.assertIs(view['until_done'], True)
        node = next(n for n in view['nodes'] if n['id'] == 'n1.1')
        self.assertEqual((node['stale'], node['progress'], node['items_total'], node['perpetual']),
                         (2, {'files': 1, 'checks': 1, 'done': 0}, 0, False))
        self.assertEqual(view['budget'], {'agents_started': 9, 'agents_max': 0, 'deadline': None})
        self.assertTrue(view['next_action'].startswith('resume: symblic-task autogen resume'))
        self.assertIs(cli.run_view(run_row())['until_done'], False)
        self.assertEqual(cli.run_view(run_row())['nodes'][0]['progress'], {'files': 0, 'checks': 0, 'done': 0})

    def test_list_and_json_show_unlimited_agents(self):
        self.rec.responses['autogen'] = {'runs': [stuck_row(), run_row()]}
        rc, out = self.main(['autogen', 'list', '--status', 'stuck'])
        self.assertEqual(rc, cli.OK)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn('agents 9/unlimited', out)
        rc, out = self.main(['autogen', 'list', '--json'])
        self.assertEqual([r['status'] for r in json.loads(out)], ['stuck', 'active'])

    def test_catalog_prints_v2_limits_defaults_and_switches(self):
        P = cli.policy_module()
        self.assertIsNotNone(P)
        catalog = json.loads(json.dumps({     # the route's payload (symblicos_engine autogen/catalog), as JSON
            'version': P.VERSION, 'limits': P.LIMITS, 'defaults': P.DEFAULTS,
            'strategies': list(P.WIRED_STRATEGIES), 'all_strategies': list(P.STRATEGIES),
            'failure_classes': list(P.FAILURE_CLASSES), 'handoff_file': P.HANDOFF_FILE,
            'checkpoint_file': P.CHECKPOINT_FILE}))
        self.rec.responses['autogen/catalog'] = catalog
        rc, out = self.main(['autogen', 'catalog'])
        self.assertEqual(rc, cli.OK)
        for key in ('novelty_limit', 'saturation', 'agents_max', 'wall_seconds'):
            low, high = P.LIMITS[key]
            self.assertIn(f'  {key:17} {low}-{high}  default {P.DEFAULTS[key]}', out)
        switches = next(x for x in out.splitlines() if x.startswith('switches:'))
        for key in ('until_done', 'designer', 'self_split'):
            self.assertIn(f'{key} {"true" if P.DEFAULTS[key] else "false"}', switches)
        self.assertIn('until_done: agents_max and wall_seconds default to 0 (unlimited) unless given', out)
        rc, out = self.main(['autogen', 'catalog', '--json'])
        self.assertEqual(json.loads(out)['defaults']['novelty_limit'], P.DEFAULTS['novelty_limit'])
        # a host still serving the v1 catalogue: no until_done note
        self.rec.responses['autogen/catalog'] = {'limits': {'candidates': [1, 4]}, 'defaults': {'candidates': 1, 'syntax': True},
                                                 'strategies': ['fresh'], 'failure_classes': []}
        rc, out = self.main(['autogen', 'catalog'])
        self.assertEqual(rc, cli.OK)
        self.assertIn('switches: syntax true', out)
        self.assertNotIn('until_done', out)

    def test_node_line_shows_handoff_stale_integrations_and_integration_attempts(self):
        row = run_row(policy={'until_done': True})
        parent = row['nodes'][1]
        parent.update(status='pending', winner='', integrations=1, handoff_stale=2)
        parent['attempts'].append({
            'id': 'n1-i1', 'kind': 'integration', 'strategy': 'integration', 'engine': 'agy', 'node': 'host',
            'model': '', 'generation': 0, 'task_id': '', 'status': 'failed', 'failure': 'CHECK_FAILURE',
            'error': 'children accepted, parent checks failed: node test.js',
            'verdict': {'passed': False, 'checks': [{'kind': 'command', 'command': 'node test.js', 'passed': False,
                                                     'public': True, 'output': 'AssertionError: sum is wrong'}]}})
        text = self.render(row)
        self.assertIn('n1  pending  -> n1.0, n1.1  handoff stale 2  integrations 1  Create the files b.js', text)
        self.assertIn('    n1-i1 integration check failed\n', text)
        self.assertIn('check command node test.js: AssertionError: sum is wrong', text)
        self.assertNotIn('integration/integration', text)
        self.assertEqual((text.count('handoff stale'), text.count('integrations ')), (1, 1))   # zero counts stay hidden
        node = next(n for n in cli.run_view(row)['nodes'] if n['id'] == 'n1')
        self.assertEqual((node['handoff_stale'], node['integrations']), (2, 1))
        self.assertEqual((cli.run_view(run_row())['nodes'][0]['handoff_stale'],
                          cli.run_view(run_row())['nodes'][0]['integrations']), (0, 0))


class TestWait(CliCase):
    def wait(self, responses, *extra):
        self.rec.responses['autogen/get'] = responses
        with mock.patch.object(cli.time, 'sleep') as sleep:
            rc, out = self.main(['autogen', 'wait', 'autogen-' + 'a' * 24] + list(extra))
        return rc, out, sleep

    def test_wait_until_completed(self):
        done = run_row(status='completed', nodes=[dict(run_row()['nodes'][0])], order=['n0'])
        rc, out, _ = self.wait([{'run': run_row()}, {'run': run_row()}, {'run': done}])
        self.assertEqual(rc, cli.OK)
        changes = [x for x in out.splitlines() if x[:2].isdigit()]
        self.assertEqual(len(changes), 2)          # one line per status change, not per poll
        self.assertIn('completed n0:accepted(2 attempts)', changes[-1])
        self.assertIn('next: done:', out)
        self.assertEqual(len(self.rec.calls), 3)

    def test_wait_failed_and_cancelled_exit_refused(self):
        for status in ('failed', 'cancelled', 'unknown'):
            rc, out, _ = self.wait([{'run': run_row(status=status, error='boom')}])
            self.assertEqual(rc, cli.REFUSED, status)

    def test_wait_tolerates_host_restart(self):
        down = cli.ApiError('not answering', cli.NO_ANSWER)
        rc, out, _ = self.wait([down, down, {'run': run_row(status='completed')}])
        self.assertEqual(rc, cli.OK)
        self.assertIn('host not answering; retrying', out)

    def test_wait_raises_on_refusal(self):
        self.rec.responses['autogen/get'] = [cli.ApiError('HTTP 404: Unknown autogen run id.', cli.REFUSED)]
        with mock.patch.object(cli.time, 'sleep'), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['autogen', 'wait', 'autogen-' + 'b' * 24]), cli.REFUSED)

    def test_wait_stops_when_coordinator_absent_twice(self):
        rc, out, _ = self.wait([{'run': run_row(resume_required=True)}, {'run': run_row()},
                                {'run': run_row(resume_required=True)}, {'run': run_row(resume_required=True)}])
        self.assertEqual(rc, cli.OK)
        self.assertEqual(len(self.rec.calls), 4)
        self.assertIn('next: resume:', out)

    def test_wait_max_reached(self):
        rc, out, _ = self.wait([{'run': run_row()}], '--max', '0.000001')
        self.assertEqual(rc, cli.TIMED_OUT)
        self.assertIn('still going', out)

    def test_wait_stops_on_stuck_with_resume_hint(self):
        rc, out, _ = self.wait([{'run': run_row()}, {'run': stuck_row()}, {'run': run_row()}])
        self.assertEqual(rc, cli.REFUSED)            # not every statement was accepted
        self.assertEqual(len(self.rec.calls), 2)     # stuck is terminal: no further poll
        self.assertIn('stuck n0:accepted(2 attempts)', out)
        self.assertIn('n1.1:stuck(1 attempt)', out)
        self.assertIn('next: ' + STUCK_HINT, out)


class TestResumeExtend(CliCase):
    RID = 'autogen-' + 'a' * 24

    def resume(self, *extra, run=None):
        self.rec.responses['autogen/control'] = {'run': run if run is not None else run_row(status='queued')}
        return self.main(['autogen', 'resume', self.RID] + list(extra))

    def test_extend_flags_send_only_the_given_keys(self):
        cases = (([], None), (['--agents-max', '40'], {'agents_max': 40}), (['--wall-seconds', '0'], {'wall_seconds': 0}),
                 (['--agents-max', '0', '--wall-seconds', '7200'], {'agents_max': 0, 'wall_seconds': 7200}))
        for extra, extend in cases:
            rc, out = self.resume(*extra)
            self.assertEqual(rc, cli.OK, (extra, out))
            body = {'id': self.RID, 'action': 'resume', **({'extend': extend} if extend is not None else {})}
            self.assertEqual(self.rec.calls[-1], ('autogen/control', body, None), extra)

    def test_applied_extension_shows_the_new_budget(self):
        row = run_row(status='queued', policy={'until_done': True, 'agents_max': 40, 'wall_seconds': 0},
                      budget={'agents_started': 24, 'agents_max': 40, 'deadline': None})
        rc, out = self.resume('--agents-max', '40', '--wall-seconds', '0', run=row)
        self.assertEqual(rc, cli.OK, out)
        self.assertIn('  budget: agents 24/40  until done\n', out)
        self.assertNotIn('note:', out)

    def test_extension_the_run_does_not_carry_is_reported(self):
        # a run that was not stuck: the server resumes it and leaves its budget as it was
        rc, out = self.resume('--agents-max', '40', '--wall-seconds', '7200', run=run_row(status='active'))
        self.assertEqual(rc, cli.OK, out)
        self.assertEqual(out.splitlines()[-1], 'note: agents_max, wall_seconds not changed: an extension applies only '
                                               'when a stuck run is resumed')
        rc, out = self.main(['autogen', 'resume', self.RID, '--agents-max', '40', '--json'])
        self.assertEqual(json.loads(out)['status'], 'active')        # --json output stays pure JSON

    def test_spent_cap_409_prints_the_server_message_verbatim(self):
        message = ('The agents_max cap you gave this run is spent; resume with extend {"agents_max": N} '
                   '(0 lifts it under until_done) or start a new run with a higher cap.')
        sent = []

        class Opener:                       # the real request() over a fake transport: no socket is opened
            def open(self, req, timeout=None):
                sent.append((req.get_method(), req.full_url, json.loads(req.data.decode('utf-8'))))
                raise urllib.error.HTTPError(req.full_url, 409, 'Conflict', {},
                                             io.BytesIO(json.dumps({'error': message}).encode('utf-8')))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, 'request', REAL_REQUEST), mock.patch.object(cli, 'OPENER', Opener()), \
                mock.patch.object(cli, 'BASE', cli.DEFAULT_URL), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            rc = cli.main(['autogen', 'resume', self.RID])
        self.assertEqual(rc, cli.REFUSED)
        self.assertEqual(sent, [('POST', cli.DEFAULT_URL + '/api/symblicos/autogen/control',
                                 {'id': self.RID, 'action': 'resume'})])
        self.assertEqual(err.getvalue().splitlines(),
                         [message, f'with this CLI: symblic-task autogen resume {self.RID} --agents-max N'])
        self.assertEqual(out.getvalue(), '')

    def test_other_409_is_printed_verbatim_without_the_flag_hint(self):
        message = 'The autogen record is unreadable; nothing was changed.'
        self.rec.responses['autogen/control'] = cli.ApiError('HTTP 409: ' + message, cli.REFUSED, {'error': message},
                                                              status=409)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc, out = self.main(['autogen', 'resume', self.RID, '--wall-seconds', '3600'])
        self.assertEqual(rc, cli.REFUSED)
        self.assertEqual(err.getvalue().splitlines(), [message])
        self.assertEqual(self.rec.calls[-1][1]['extend'], {'wall_seconds': 3600})

    def test_bad_extension_flags(self):
        refusal = 'extend.agents_max 0 (unlimited) needs until_done true.'
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc, out = self.main(['autogen', 'cancel', self.RID, '--agents-max', '5'])
            self.assertEqual(rc, cli.USAGE)
            self.assertIn('extend a resume', out)
            rc, _ = self.main(['autogen', 'resume', self.RID, '--wall-seconds', 'soon'])
            self.assertEqual(rc, cli.USAGE)
            self.assertEqual(self.rec.calls, [])
            self.rec.responses['autogen/control'] = cli.ApiError('HTTP 400: ' + refusal, cli.REFUSED, {'error': refusal},
                                                                  status=400)
            rc, _ = self.main(['autogen', 'resume', self.RID, '--agents-max', '0'])
            self.assertEqual(rc, cli.REFUSED)
        self.assertIn('--wall-seconds needs a whole number', err.getvalue())
        self.assertIn('symblic-task: HTTP 400: ' + refusal, err.getvalue())   # other refusals keep the usual line
        self.assertEqual([c[1]['extend'] for c in self.rec.calls], [{'agents_max': 0}])


class TestLintDelegation(CliCase):
    def test_lint_delegates_to_the_autogen_policy(self):
        seen = []

        def fake_lint(lines, root=''):
            seen.append((list(lines), root))
            return [['warning', 1, 'from the shared policy']]
        cli._POLICY = types.SimpleNamespace(lint=fake_lint)
        self.assertEqual(cli.lint(['Create the file a.txt somewhere'], '/r'), [('warning', 1, 'from the shared policy')])
        self.assertEqual(seen, [(['Create the file a.txt somewhere'], '/r')])
        rc, out = self.main(['lint', self.lines_file])
        self.assertEqual(rc, cli.OK)
        self.assertIn('warning line 1: from the shared policy', out)

    def test_local_lint_is_the_fallback(self):
        cli._POLICY = False
        lines = ['Create the file a.txt in the folder /home/x with the line hello world']
        self.assertEqual(cli.lint(lines), cli.local_lint(lines))
        self.assertEqual(cli.lint(['short'])[0][:2], ('error', 1))

    def test_policy_module_imports_checkout_copy_without_leaving_sys_path(self):
        cli._POLICY = None
        before = list(sys.path)
        module = cli.policy_module()
        self.assertEqual(sys.path, before)
        self.assertIsNotNone(module)
        self.assertEqual(Path(module.__file__).resolve(), ROOT / 'symblic' / 'autogen' / 'policy.py')
        self.assertEqual(cli.CHECKOUT_ROOT, str(ROOT))
        self.assertTrue(callable(module.lint))

    def test_unimportable_module_falls_back(self):
        cli._POLICY = None
        with mock.patch.dict(sys.modules, {'symblic.autogen.policy': None}):   # None in sys.modules makes import fail
            self.assertIsNone(cli.policy_module())
        self.assertIs(cli._POLICY, False)


if __name__ == '__main__':
    unittest.main()
