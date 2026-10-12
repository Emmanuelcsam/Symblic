"""Tests of symblic/autogen/policy.py: pure functions only, no stores, no network.

Every case gives concrete inputs and the exact expected output. The one file read is the
command line tools/symblic-task, loaded as a module (inert on import) to prove that its lint
rules match the policy's; those parity tests are skipped when the command line cannot be loaded.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path

from symblic.autogen import policy as P

ROOT = Path(__file__).resolve().parents[2]          # the repository root
CLI = ROOT / 'tools' / 'symblic-task'
FOLDER = '/srv/symblic/projects/beta-graphview'
NOW = 100000.0

# Real statements from two demo builds (see web/hub/records/), with the project folder renamed.
GRAPH_VERIFY = ('Run node --check in the folder /srv/symblic/projects/beta-graphview on exactly the five '
                'files vault-data.js, graph-engine.js, graph-render.js, graph-input.js and graph-ui.js and create the '
                'file verify.txt in the folder /srv/symblic/projects/beta-graphview with exactly five lines, '
                'each in the format filename: pass or filename: followed by the exact error message.')
GRAPH_README = ('Create the file README.md in the folder /srv/symblic/projects/beta-graphview with three '
                'parts: the exact way to open the app, the list of every implemented feature naming the file that '
                'implements it, and a statement that the note dataset is fictional.')
KIRBY_HTML = ('Create the file kirby.html in the folder /srv/symblic/projects/beta-kirby with the title '
              'Kirby animation test, a centered canvas exactly nine hundred sixty by five hundred forty pixels, a flat '
              'ground line across its bottom quarter, a simple sky and ground coloring, and no other elements. It loads '
              'exactly kirby.js from the same folder and then calls startKirby with the canvas. It references no '
              'external resource.')
KIRBY_VERIFY = ('Run node --check in the folder /srv/symblic/projects/beta-kirby on the file kirby.js and '
                'create the file verify.txt in that folder with exactly one line in the format kirby.js: pass or '
                'kirby.js: followed by the exact error message, then create the file README.md in that folder '
                'describing the exact key controls and every animation state.')


def policy(**spec):
    engines = spec.pop('_engines', ())
    nodes = spec.pop('_nodes', ())
    return P.normalize(spec, engines=engines, nodes=nodes)


def budget(started=0, maximum=24, deadline=NOW + 3600):
    return {'agents_started': started, 'agents_max': maximum, 'deadline': deadline}


def attempt(i, status='failed', failure=None, strategy='fresh', kind='candidate', **extra):
    row = {'id': f'n0-a{i}', 'status': status, 'failure': failure, 'strategy': strategy, 'kind': kind,
           'generation': 0, 'started': NOW - 100, 'finished': NOW - 50}
    row.update(extra)
    return row


def node(*attempts, **extra):
    row = {'id': 'n0', 'statement': 'Create the file app.js in the folder /home/p/x exporting run()',
           'depth': 0, 'status': 'pending', 'attempts': list(attempts), 'children': [], 'generation': 0,
           'perpetual': False, 'last_fingerprint': '', 'engine': 'agy', 'node': 'orchestrator'}
    row.update(extra)
    return row


def load_cli():
    loader = importlib.machinery.SourceFileLoader('_symblic_task_cli_under_test', str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------ normalize

class NormalizeTests(unittest.TestCase):
    def test_defaults(self):
        got = P.normalize({})
        for key, value in P.DEFAULTS.items():
            self.assertEqual(got[key], value, key)
        self.assertEqual(got['version'], P.VERSION)
        self.assertEqual(got['engines'], [])
        self.assertEqual(got['nodes'], [])
        self.assertEqual(len(got['sha256']), 64)
        self.assertEqual(P.normalize(None)['sha256'], got['sha256'])
        self.assertEqual(P.normalize(True)['sha256'], got['sha256'])
        self.assertEqual(P.normalize({'version': 1})['sha256'], got['sha256'])

    def test_not_an_object_refused(self):
        for bad in (False, [], 'yes', 3):
            with self.assertRaises(P.AutogenError) as ctx:
                P.normalize(bad)
            self.assertEqual(ctx.exception.status, 400)

    def test_every_limit_inclusive_and_exclusive(self):
        for key, (low, high) in P.LIMITS.items():
            base = {'regenerate': 0} if key in ('agents_max', 'candidates') else {}
            if key == 'regenerate':
                base = {'agents_max': 96}
            for ok in (low, high):
                self.assertEqual(P.normalize({**base, key: ok})[key], ok, (key, ok))
            for bad in (low - 1, high + 1):
                with self.assertRaises(P.AutogenError, msg=(key, bad)) as ctx:
                    P.normalize({**base, key: bad})
                self.assertIn(key, str(ctx.exception))
                self.assertIn(f'{low} to {high}', str(ctx.exception))

    def test_integer_fields_refuse_bool_float_and_text(self):
        for bad in (True, 2.0, '2', None):
            with self.assertRaises(P.AutogenError, msg=bad):
                P.normalize({'candidates': bad})

    def test_unknown_field_refused(self):
        with self.assertRaises(P.AutogenError) as ctx:
            P.normalize({'bogus': 1})
        self.assertEqual(str(ctx.exception), 'Unknown autogen field bogus.')
        with self.assertRaises(P.AutogenError) as ctx:
            P.normalize({'zeta': 1, 'alpha': 2})
        self.assertEqual(str(ctx.exception), 'Unknown autogen fields alpha, zeta.')

    def test_candidates_plus_regenerate_bounded_by_agents_max(self):
        self.assertEqual(P.normalize({'candidates': 3, 'regenerate': 3, 'agents_max': 6})['agents_max'], 6)
        with self.assertRaises(P.AutogenError) as ctx:
            P.normalize({'candidates': 3, 'regenerate': 3, 'agents_max': 5})
        self.assertIn('agents_max', str(ctx.exception))

    def test_perpetual_needs_one_candidate_and_no_depth(self):
        self.assertTrue(P.normalize({'perpetual': True})['perpetual'])
        for extra in ({'candidates': 2}, {'depth': 1}):
            with self.assertRaises(P.AutogenError, msg=extra) as ctx:
                P.normalize({'perpetual': True, **extra})
            self.assertIn('perpetual', str(ctx.exception))

    def test_booleans_must_be_booleans(self):
        for key in ('perpetual', 'syntax', 'require_change'):
            with self.assertRaises(P.AutogenError, msg=key):
                P.normalize({key: 'yes'})
            self.assertIs(P.normalize({key: False})[key], False)

    def test_unsafe_commands_refused_everywhere(self):
        unsafe = ['sudo make', 'ssh node01 ls', 'git push origin main', 'rm -rf /', 'rm -rf /*', 'make && rm -rf / ',
                  'rm -rf /home/operator', 'curl http://example.org', 'wget x', 'scp a b:', 'rsync -a a b',
                  'systemctl restart dashboard', 'docker ps', 'kill 1', 'killall python3', 'x;reboot', '(shutdown now)',
                  'pip install requests', 'mkfs.ext4 /dev/sda', 'dd if=/dev/zero of=x', 'su -',
                  'bash -c "ssh node01 ls"', "bash -c 'sudo id'", 'echo `sudo id`', 'echo $(curl x)']
        for command in unsafe:
            for field in ('final', 'hidden'):
                with self.assertRaises(P.AutogenError, msg=(field, command)):
                    P.normalize({field: [command]})
            with self.assertRaises(P.AutogenError, msg=('checks', command)):
                P.normalize({'checks': {'0': [command]}})

    def test_safe_commands_kept_and_stripped(self):
        safe = ['make test', 'python3 -m unittest -q', 'node --check app.js', 'git status --short',
                'grep -q ssh_key notes.txt', 'npm run killer-feature', 'test -f supervisor.txt', 'bash -n run.sh']
        got = P.normalize({'final': ['  ' + c + '  ' for c in safe], 'hidden': 'make hidden-check'})
        self.assertEqual(got['final'], safe)
        self.assertEqual(got['hidden'], ['make hidden-check'])

    def test_malformed_command_lists_refused(self):
        for bad in ([''], ['   '], [3], ['a\0b'], ['x' * 2001], {'a': 1}):
            with self.assertRaises(P.AutogenError, msg=bad):
                P.normalize({'final': bad})
        self.assertEqual(P.normalize({'final': None})['final'], [])

    def test_strategies_dedup_and_validation(self):
        self.assertEqual(P.normalize({'strategies': ['feedback', 'fresh', 'feedback', 'fresh']})['strategies'],
                         ['feedback', 'fresh'])
        for bad in ([], ['magic'], 'fresh', ['fresh', 3]):
            with self.assertRaises(P.AutogenError, msg=bad):
                P.normalize({'strategies': bad})

    def test_checks_keys(self):
        got = P.normalize({'checks': {'0': ['make a'], '12': 'make b'}})
        self.assertEqual(got['checks'], {'0': ['make a'], '12': ['make b']})
        for bad in ({'a': ['x']}, {'-1': ['x']}, {'²': ['make']}, {'1.0': ['x']}, ['make']):
            with self.assertRaises(P.AutogenError, msg=bad):
                P.normalize({'checks': bad})

    def test_checks_key_with_leading_zero_reaches_its_statement(self):
        # "01" must not be accepted and then silently never run.
        got = P.normalize({'checks': {'01': ['make test']}})
        self.assertEqual(got['checks'], {'1': ['make test']})
        plan = P.plan_checks('Create the file a.py in the folder /home/p/x', 1, got)
        self.assertIn({'kind': 'command', 'command': 'make test', 'public': True}, plan['checks'])
        with self.assertRaises(P.AutogenError):
            P.normalize({'checks': {'1': ['make a'], '01': ['make b']}})

    def test_sha256_independent_of_engines_and_nodes(self):
        spec = {'candidates': 2, 'strategies': ['fresh', 'other_engine']}
        a = P.normalize(spec)
        b = P.normalize(spec, engines=['agy', 'claude', 'agy', 7], nodes=['orchestrator', 'node01', 'node01'])
        self.assertEqual(a['sha256'], b['sha256'])
        self.assertEqual(b['engines'], ['agy', 'claude'])
        self.assertEqual(b['nodes'], ['orchestrator', 'node01'])
        self.assertNotEqual(a['sha256'], P.normalize({'candidates': 3})['sha256'])
        self.assertEqual(a['sha256'], P.digest({k: v for k, v in a.items() if k not in ('engines', 'nodes', 'sha256')}))

    def test_digest_is_canonical(self):
        self.assertEqual(P.digest({'a': 1, 'b': [1, 2]}), P.digest({'b': [1, 2], 'a': 1}))
        with self.assertRaises(ValueError):
            P.digest({'x': float('nan')})


# ------------------------------------------------------------------------------ lint parity

LINT_CORPUS = [
    'Create the file app.js in the folder /home/p/x exporting run() and nothing else',
    'Create the file app.js exporting run()',
    'too short line',
    'Please create the file app.js in the folder /home/p/x',
    'It should create the file app.js in the folder /home/p/x',
    'The file app.js in the folder /home/p/x needs a run() export',
    'Extend the file app.js in the folder /home/p/x with a stop() export',
    'Extend the file app.js in the folder /home/p/x with a stop() export, keeping every existing part',
    'Update the file app.js in the folder /home/p/x like above',
    'Write the file notes.md under the folder /srv/data with the previous results',
    'Verify the file app.js in the folder /home/p/x and write verify.txt with one line',
    'Create the file big.txt in the folder /home/p/x ' + 'with many words ' * 100,
    '42 is not a verb; create the file a.js in the folder /home/p/x',
]


class LintParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CLI.exists():
            raise unittest.SkipTest('tools/symblic-task is absent')
        try:
            cls.cli = load_cli()
        except Exception as exc:  # noqa: BLE001 - a command line that cannot load is reported, not failed here
            raise unittest.SkipTest(f'tools/symblic-task cannot be loaded as a module: {type(exc).__name__}: {exc}')

    def same(self, lines, root=''):
        # tools/symblic-task's lint delegates to symblic.autogen.policy.lint when it can import it; its own
        # rules (local_lint, the fallback when the import fails) must give the same findings.
        own = getattr(self.cli, 'local_lint', self.cli.lint)
        self.assertEqual(P.lint(lines, root), own(lines, root), (lines, root))
        self.assertEqual(P.lint(lines, root), [tuple(f) for f in self.cli.lint(lines, root)], (lines, root))

    def test_constants_match(self):
        self.assertEqual((P.MAX_LINES, P.MAX_CHARS), (self.cli.MAX_LINES, self.cli.MAX_CHARS))
        self.assertTrue(set(self.cli.VERBS) <= set(P.VERBS))

    def test_same_findings_for_the_same_lines(self):
        for root in ('', '/home/p/x'):
            self.same([], root)
            for line in LINT_CORPUS:
                self.same([line], root)
            self.same(LINT_CORPUS, root)
            self.same([LINT_CORPUS[0]] * (P.MAX_LINES + 1), root)
            self.same(['Create the file a.txt in the folder /home/p/x ' + 'w' * 1400] * 45, root)
            self.same([GRAPH_VERIFY, GRAPH_README, KIRBY_HTML, KIRBY_VERIFY], root)

    def test_concrete_findings(self):
        findings = P.lint(['too short line'])
        self.assertIn(('error', 1, 'shorter than 20 characters: one full self-contained statement per line'), findings)
        self.assertEqual(P.lint([]), [('error', 0, 'no statements: the file has no nonblank line')])
        self.assertEqual([f for f in P.lint([KIRBY_VERIFY]) if f[0] == 'error'], [])
        self.assertEqual(P.lint([GRAPH_VERIFY]), [])  # verify line with .txt, folder named, verb first

    def test_checkout_lock_matches_the_cli(self):
        # the coordinator prepends the same lock tools/symblic-task gives own-checkout workers
        self.assertEqual(P.CHECKOUT_LOCK, self.cli.CHECKOUT_LOCK)

    def test_autogen_only_verbs_match_the_cli(self):
        # tools/symblic-task's fallback VERBS carries the autogen verbs (index/monitor/watch/collect/
        # summarize/summarise/research/scan) so the two lints agree even when the import fails.
        self.same(['Monitor the file log.txt in the folder /home/p/x and append new lines'])


# ------------------------------------------------------------------------------ statement files

class StatementFilesTests(unittest.TestCase):
    def test_real_statements(self):
        self.assertEqual(P.statement_files(GRAPH_VERIFY), {
            'files': ['vault-data.js', 'graph-engine.js', 'graph-render.js', 'graph-input.js', 'graph-ui.js',
                      'verify.txt'], 'folder': FOLDER})
        self.assertEqual(P.statement_files(GRAPH_README), {'files': ['README.md'], 'folder': FOLDER})
        self.assertEqual(P.statement_files(KIRBY_HTML),
                         {'files': ['kirby.html', 'kirby.js'], 'folder': '/srv/symblic/projects/beta-kirby'})
        self.assertEqual(P.statement_files(KIRBY_VERIFY)['files'], ['kirby.js', 'verify.txt', 'README.md'])

    def test_and_lists_and_names_containing_and(self):
        self.assertEqual(P.statement_files('Create the files a.js, b.js, and c.js in the folder /home/p/x')['files'],
                         ['a.js', 'b.js', 'c.js'])
        self.assertEqual(P.statement_files('Create the files a.js and b.css in the folder /home/p/x')['files'],
                         ['a.js', 'b.css'])
        self.assertEqual(
            P.statement_files('Create the files band.css and command.py and handler.js in the folder /home/p/x')['files'],
            ['band.css', 'command.py', 'handler.js'])
        self.assertEqual(P.statement_files('Create the file handler.js in the folder /home/p/x')['files'], ['handler.js'])

    def test_bare_file_names(self):
        self.assertEqual(P.statement_files('Make index.html load app.js and style.css in the folder /home/p/x')['files'],
                         ['index.html', 'app.js', 'style.css'])
        self.assertEqual(P.statement_files('Create the file app.js.')['files'], ['app.js'])

    def test_relative_subpath_kept_without_duplicate_basename(self):
        self.assertEqual(P.statement_files('Create the file src/app.js in the folder /home/p/x')['files'], ['src/app.js'])
        self.assertEqual(P.statement_files('Create the file ../escape.js in the folder /home/p/x')['files'], [])

    def test_no_false_matches(self):
        for text in ('Write a short note, e.g. a summary, i.e. the gist, etc. in the folder /home/p/x',
                     'Use version 1.2 of the protocol and Node 22.x in the folder /home/p/x',
                     'Update the profile settings.toml in the folder /home/p/x',
                     'Mention no real person, file or personal data in the folder /home/p/x'):
            self.assertEqual(P.statement_files(text)['files'], [], text)

    def test_folder(self):
        self.assertEqual(P.statement_files('Create the file a.js in the folder /home/p/x/.')['folder'], '/home/p/x')
        self.assertEqual(P.statement_files('Create the file a.js into the folder /a/b, then stop')['folder'], '/a/b')
        self.assertEqual(P.statement_files('Create the file a.js under the folder /a/b; then stop')['folder'], '/a/b')
        self.assertEqual(P.statement_files('Create the file a.js')['folder'], '')
        self.assertEqual(P.statement_files(''), {'files': [], 'folder': ''})


# ------------------------------------------------------------------------------ plan checks

class PlanChecksTests(unittest.TestCase):
    def kinds(self, plan):
        return [(c['kind'], c.get('file') or c.get('command')) for c in plan['checks']]

    def test_exists_and_syntax_by_extension(self):
        pol = policy()
        plan = P.plan_checks('Create the files a.py, b.json, c.sh, d.mjs, e.txt and f.md in the folder /home/p/x', 0, pol)
        self.assertEqual(self.kinds(plan), [('exists', 'a.py'), ('syntax', 'a.py'), ('exists', 'b.json'), ('syntax', 'b.json'),
                                            ('exists', 'c.sh'), ('syntax', 'c.sh'), ('exists', 'd.mjs'), ('syntax', 'd.mjs'),
                                            ('exists', 'e.txt'), ('exists', 'f.md')])
        argv = {c['file']: c['argv'] for c in plan['checks'] if c['kind'] == 'syntax'}
        self.assertEqual(argv['c.sh'], ['bash', '-n', 'c.sh'])
        self.assertEqual(argv['d.mjs'], ['node', '--check', 'd.mjs'])
        self.assertEqual(argv['a.py'][-1], 'a.py')
        self.assertEqual(argv['b.json'][-1], 'b.json')
        self.assertTrue(all(c['public'] for c in plan['checks']))
        self.assertFalse(plan['read_only'])
        self.assertEqual(plan['folder'], '/home/p/x')

    def test_syntax_off(self):
        plan = P.plan_checks('Create the file a.py in the folder /home/p/x', 0, policy(syntax=False))
        self.assertEqual(self.kinds(plan), [('exists', 'a.py')])

    def test_read_only_verbs_skip_exists(self):
        plan = P.plan_checks('Read the file notes.md in the folder /home/p/x and summarize it in chat', 0, policy())
        self.assertEqual(plan['checks'], [])
        self.assertTrue(plan['read_only'])
        plan = P.plan_checks('Check the file app.js in the folder /home/p/x for unused globals', 0, policy())
        self.assertEqual(self.kinds(plan), [('syntax', 'app.js')])

    def test_read_only_verbs_that_also_create(self):
        plan = P.plan_checks(KIRBY_VERIFY, 3, policy())
        self.assertEqual(self.kinds(plan), [('exists', 'kirby.js'), ('syntax', 'kirby.js'), ('exists', 'verify.txt'),
                                            ('exists', 'README.md')])
        self.assertTrue(plan['read_only'])
        plan = P.plan_checks(GRAPH_VERIFY, 6, policy())
        self.assertIn(('exists', 'verify.txt'), self.kinds(plan))

    def test_inflected_create_verbs_count(self):
        # A verify statement that "writes verify.txt" must still prove verify.txt exists.
        for verb in ('writes', 'creates', 'records', 'appends', 'produces', 'generates'):
            text = f'Verify the five scripts in the folder /home/p/x with node --check and {verb} verify.txt'
            plan = P.plan_checks(text, 0, policy())
            self.assertEqual(self.kinds(plan), [('exists', 'verify.txt')], verb)

    def test_operator_commands_by_index(self):
        pol = policy(checks={'1': ['make test', 'node --check app.js']})
        text = 'Create the file app.js in the folder /home/p/x'
        self.assertEqual(self.kinds(P.plan_checks(text, 0, pol)), [('exists', 'app.js'), ('syntax', 'app.js')])
        self.assertEqual(self.kinds(P.plan_checks(text, 1, pol)),
                         [('exists', 'app.js'), ('syntax', 'app.js'), ('command', 'make test'), ('command', 'node --check app.js')])


# ------------------------------------------------------------------------------ classify

def done_task(warning=None, status='completed', error='', **extra):
    evidence = {'warning': warning} if warning else {}
    return {'status': status, 'error': error, 'steps': [{'status': 'completed', 'evidence': evidence}], **extra}


def verdict(*checks, files_changed=1, passed=None):
    rows = [{'kind': k, 'passed': ok, 'public': k != 'hidden'} for k, ok in checks]
    return {'passed': all(c['passed'] for c in rows) if passed is None else passed, 'checks': rows,
            'files_changed': files_changed}


class ClassifyTests(unittest.TestCase):
    def test_every_failure_class(self):
        cases = {
            'CANCELLED': (done_task(status='cancelled'), None, None),
            'TIMEOUT': (done_task(status='cancelled'), None, None),
            'UNKNOWN': (done_task(status='unknown'), None, None),
            'REFUSAL': (done_task(status='failed', error='The agent refused its own launch: no'), None, None),
            'INFRASTRUCTURE': (done_task(status='failed', error='claude is not installed on node01'), None, None),
            'CLAIM_MISMATCH': (done_task(warning='claimed 3 files; 0 changed'), verdict(('exists', True), ('claim', False)), None),
            'NO_OUTPUT': (done_task(), verdict(('exists', False), ('syntax', False)), None),
            'SYNTAX': (done_task(), verdict(('exists', True), ('syntax', False), ('command', False)), None),
            'CHECK_FAILURE': (done_task(), verdict(('exists', True), ('syntax', True), ('command', False)), None),
            'CONTEXT_EXHAUSTED': (done_task(), verdict(('exists', False)), {'valid': True, 'done': ['a'], 'left': ['b'], 'files': []}),
            'HIDDEN_FAILURE': (done_task(), verdict(('exists', True), ('hidden', False)), None),
            'FETCH_FAILURE': (done_task(), verdict(('fetch', False), files_changed=None), None),
            'CONFLICT': None,          # assigned by the coordinator at promotion, never by classify
        }
        seen = {'CONFLICT'}
        for expected, case in cases.items():
            if case is None:
                continue
            task, ver, handoff = case
            got = P.classify(task, ver, handoff=handoff, timeout_requested=expected == 'TIMEOUT')
            self.assertEqual(got, expected)
            seen.add(got)
        self.assertEqual(seen, set(P.FAILURE_CLASSES))

    def test_passed_verdict_is_none(self):
        self.assertIsNone(P.classify(done_task(), verdict(('exists', True), ('command', True))))
        self.assertIsNone(P.classify(None, {'passed': True, 'checks': []}))

    def test_failed_text_variants(self):
        self.assertEqual(P.classify(done_task(status='failed', error='Admission refused: busy'), None), 'REFUSAL')
        self.assertEqual(P.classify(done_task(status='failed', error='admission queue full'), None), 'INFRASTRUCTURE')
        self.assertEqual(P.classify(done_task(status='failed', error='boom'), None), 'INFRASTRUCTURE')

    def test_files_changed_zero_after_passing_checks(self):
        self.assertEqual(P.classify(done_task(), verdict(('exists', True), ('change', False), files_changed=0)), 'NO_OUTPUT')

    def test_invalid_handoff_is_not_context_exhausted(self):
        self.assertEqual(P.classify(done_task(), verdict(('command', False)), handoff={'valid': False}), 'CHECK_FAILURE')

    def test_hidden_and_fetch_failures_have_their_own_classes(self):
        # D19: they used to read UNKNOWN, which then spent a feedback slot with nothing to feed back
        self.assertEqual(P.classify(done_task(), verdict(('exists', True), ('hidden', False))), 'HIDDEN_FAILURE')
        self.assertEqual(P.classify(done_task(), verdict(('fetch', False), files_changed=None)), 'FETCH_FAILURE')
        self.assertEqual(P.classify(done_task(), None), 'UNKNOWN')
        self.assertEqual(P.classify(None, None), 'UNKNOWN')


# ------------------------------------------------------------------------------ next strategy

class NextStrategyTests(unittest.TestCase):
    def pol(self, **kw):
        kw.setdefault('_engines', ['agy', 'claude'])
        kw.setdefault('_nodes', ['orchestrator', 'node01'])
        return policy(**kw)

    def test_infrastructure_moves_machine_never_feedback(self):
        n = node(attempt(0, failure='INFRASTRUCTURE'))
        for last in ('INFRASTRUCTURE', 'REFUSAL', 'TIMEOUT'):
            self.assertEqual(P.next_strategy(n, self.pol(), [last]), ('other_node', {'node': 'node01'}), last)
        self.assertEqual(P.next_strategy(n, self.pol(_nodes=['orchestrator']), ['INFRASTRUCTURE']),
                         ('other_engine', {'engine': 'claude'}))
        self.assertEqual(P.next_strategy(n, self.pol(_nodes=['orchestrator'], _engines=['agy']), ['INFRASTRUCTURE']),
                         ('fresh', {}))
        only_feedback = self.pol(strategies=['feedback'])
        self.assertEqual(P.next_strategy(n, only_feedback, ['INFRASTRUCTURE']), ('fresh', {}))

    def test_feedback_first_after_semantic_failures(self):
        n = node(attempt(0, failure='SYNTAX'))
        for last in ('SYNTAX', 'CHECK_FAILURE', 'CLAIM_MISMATCH', 'NO_OUTPUT'):
            self.assertEqual(P.next_strategy(n, self.pol(), [last]), ('feedback', {}), last)
        # fresh is the fallback after every other eligible name, not the first pick (item 4)
        self.assertEqual(P.next_strategy(n, self.pol(strategies=['fresh', 'other_node']), ['SYNTAX']),
                         ('other_node', {'node': 'node01'}))
        self.assertEqual(P.next_strategy(n, self.pol(strategies=['fresh', 'other_node'], _nodes=['orchestrator']), ['SYNTAX']),
                         ('fresh', {}))

    def test_feedback_at_most_twice(self):
        n = node(attempt(0, failure='SYNTAX'), attempt(1, failure='SYNTAX', strategy='feedback', kind='regen'))
        self.assertEqual(P.next_strategy(n, self.pol(regenerate=8), ['SYNTAX', 'SYNTAX']), ('feedback', {}))
        n['attempts'].append(attempt(2, failure='SYNTAX', strategy='feedback', kind='regen'))
        self.assertEqual(P.next_strategy(n, self.pol(regenerate=8), ['SYNTAX'] * 3), ('other_node', {'node': 'node01'}))
        self.assertIsNone(P.next_strategy(n, self.pol(strategies=['feedback'], regenerate=8), ['SYNTAX'] * 3))

    def test_other_engine_and_node_skipped_without_alternatives(self):
        n = node(attempt(0, failure='UNKNOWN'))
        pol = self.pol(strategies=['other_engine', 'other_node', 'fresh'], _engines=['agy'], _nodes=['orchestrator'])
        self.assertEqual(P.next_strategy(n, pol, ['UNKNOWN']), ('fresh', {}))
        pol = self.pol(strategies=['other_engine', 'other_node'], _engines=['agy'], _nodes=['orchestrator'])
        self.assertIsNone(P.next_strategy(n, pol, ['UNKNOWN']))

    def test_stronger_model_needs_a_list(self):
        # normalize refuses the strategy until a ladder is wired (D18); the rotation logic stays
        pol = self.pol(regenerate=2)
        pol['strategies'] = ['stronger_model']
        n = node(attempt(0, failure='CHECK_FAILURE'))
        self.assertIsNone(P.next_strategy(n, pol, ['CHECK_FAILURE']))
        n['stronger_models'] = ['m-big', 'm-huge']
        self.assertEqual(P.next_strategy(n, pol, ['CHECK_FAILURE']), ('stronger_model', {'model': 'm-big'}))
        n['attempts'].append(attempt(1, failure='CHECK_FAILURE', strategy='stronger_model', kind='regen'))
        self.assertEqual(P.next_strategy(n, pol, ['CHECK_FAILURE'] * 2), ('stronger_model', {'model': 'm-huge'}))
        n['attempts'].append(attempt(2, failure='CHECK_FAILURE', strategy='stronger_model', kind='regen'))
        self.assertIsNone(P.next_strategy(n, pol, ['CHECK_FAILURE'] * 3))

    def test_overrides_cycle(self):
        pol = self.pol(strategies=['other_engine'], regenerate=4, _engines=['agy', 'claude', 'codex'])
        n = node(attempt(0, failure='UNKNOWN'))
        self.assertEqual(P.next_strategy(n, pol, ['UNKNOWN']), ('other_engine', {'engine': 'claude'}))
        n['attempts'].append(attempt(1, failure='UNKNOWN', strategy='other_engine', kind='regen'))
        self.assertEqual(P.next_strategy(n, pol, ['UNKNOWN'] * 2), ('other_engine', {'engine': 'codex'}))
        n['attempts'].append(attempt(2, failure='UNKNOWN', strategy='other_engine', kind='regen'))
        self.assertEqual(P.next_strategy(n, pol, ['UNKNOWN'] * 3), ('other_engine', {'engine': 'claude'}))
        pol = self.pol(strategies=['other_node'], regenerate=4, _nodes=['orchestrator', 'node01', 'node02'])
        n = node(attempt(0, failure='UNKNOWN'), attempt(1, failure='UNKNOWN', strategy='other_node', kind='regen'))
        self.assertEqual(P.next_strategy(n, pol, ['UNKNOWN'] * 2), ('other_node', {'node': 'node02'}))


# ------------------------------------------------------------------------------ decide

class DecideTests(unittest.TestCase):
    def test_stop_on_terminal_nodes(self):
        for status in ('accepted', 'failed', 'split'):
            self.assertEqual(P.decide(node(status=status), policy(), budget(), NOW),
                             {'action': 'stop', 'reason': f'node is {status}'})

    def test_launch_respects_budget(self):
        self.assertEqual(P.decide(node(), policy(candidates=3), budget(), NOW)['count'], 3)
        self.assertEqual(P.decide(node(), policy(candidates=3), budget(started=22), NOW)['count'], 2)
        self.assertEqual(P.decide(node(), policy(candidates=3), budget(started=24), NOW)['action'], 'fail')
        self.assertEqual(P.decide(node(), policy(), budget(deadline=NOW), NOW)['action'], 'fail')

    def test_accept(self):
        n = node(attempt(0, failure='SYNTAX'), attempt(1, status='accepted'), attempt(2, status='accepted'))
        self.assertEqual(P.decide(n, policy(), budget(), NOW)['action'], 'accept')
        self.assertEqual(P.decide(n, policy(), budget(), NOW)['attempt'], 'n0-a1')

    def test_wait_and_timeout_ids(self):
        pol = policy(attempt_seconds=600)
        n = node(attempt(0, status='running', started=NOW - 10), attempt(1, status='queued', started=None))
        got = P.decide(n, pol, budget(), NOW)
        self.assertEqual(got['action'], 'wait')
        self.assertNotIn('timeout', got)
        n = node(attempt(0, status='running', started=NOW - 601), attempt(1, status='running', started=NOW - 10))
        got = P.decide(n, pol, budget(), NOW)
        self.assertEqual((got['action'], got['timeout']), ('wait', ['n0-a0']))

    def test_wall_deadline_cancels_running_attempts(self):
        pol = policy(attempt_seconds=14400, wall_seconds=300)
        n = node(attempt(0, status='running', started=NOW - 10), attempt(1, status='queued', started=None))
        got = P.decide(n, pol, budget(deadline=NOW - 1), NOW)
        self.assertEqual((got['action'], got['timeout']), ('wait', ['n0-a0', 'n0-a1']))

    def test_regenerate_with_fingerprint(self):
        n = node(attempt(0, failure='SYNTAX'))
        got = P.decide(n, policy(), budget(started=1), NOW)
        self.assertEqual(got['action'], 'regenerate')
        self.assertEqual((got['strategy'], got['overrides']), ('feedback', {}))
        self.assertEqual(got['fingerprint'], P.fingerprint(n, 'feedback', 'SYNTAX'))

    def test_identical_fingerprint_refused(self):
        pol = policy(strategies=['other_engine'], regenerate=3, _engines=['agy', 'claude'])
        n = node(attempt(0, failure='SYNTAX'), attempt(1, failure='SYNTAX', kind='regen', strategy='other_engine'))
        n['fingerprints'] = [P.fingerprint(n, 'other_engine', 'SYNTAX', {'engine': 'claude'})]
        self.assertEqual(P.decide(n, pol, budget(started=2), NOW)['action'], 'fail')
        pol = policy(strategies=['other_engine'], regenerate=3, depth=1, _engines=['agy', 'claude'])
        self.assertEqual(P.decide(n, pol, budget(started=2), NOW)['action'], 'decompose')
        n['fingerprints'] = [P.fingerprint(n, 'other_engine', 'CHECK_FAILURE', {'engine': 'claude'})]
        self.assertEqual(P.decide(n, pol, budget(started=2), NOW)['action'], 'regenerate')

    def test_fresh_is_exempt_from_the_cycle_rule_and_honours_regenerate(self):
        # R11 second run: strategies ['fresh'] with a stable failure used to stop after one regeneration
        pol = policy(strategies=['fresh'], regenerate=8, candidates=1)
        n = node()
        trace = []
        for i in range(12):
            got = P.decide(n, pol, budget(started=len(n['attempts']), maximum=96), NOW)
            trace.append(got['action'])
            if got['action'] not in ('launch', 'regenerate'):
                break
            if got['action'] == 'regenerate':
                n['fingerprints'] = n.get('fingerprints', []) + [got['fingerprint']]
            n['attempts'].append(attempt(i, failure='CHECK_FAILURE', strategy=got.get('strategy', 'fresh')))
        self.assertEqual(['launch'] + ['regenerate'] * 8 + ['fail'], trace)

    def test_cycle_detection_sees_every_earlier_fingerprint(self):
        # Section 3 / R11 first run: alternating classes defeated a last-fingerprint-only comparison
        pol = policy(strategies=['other_node'], regenerate=8, _nodes=['orchestrator', 'node01'])
        n = node(attempt(0, failure='CHECK_FAILURE'))
        first = P.decide(n, pol, budget(started=1), NOW)
        self.assertEqual(('regenerate', 'other_node'), (first['action'], first['strategy']))
        n['fingerprints'] = [first['fingerprint'], P.fingerprint(n, 'other_node', 'SYNTAX', {'node': 'node01'})]
        n['last_fingerprint'] = n['fingerprints'][-1]
        n['attempts'] += [attempt(1, failure='SYNTAX', strategy='other_node'), attempt(2, failure='CHECK_FAILURE', strategy='other_node')]
        self.assertEqual('fail', P.decide(n, pol, budget(started=3), NOW)['action'])

    def test_a_repeated_fingerprint_moves_to_the_next_strategy(self):
        # item 4: a cycle on one strategy asks next_strategy again without it, instead of giving up
        pol = policy(strategies=['other_node', 'other_engine'], regenerate=4, _nodes=['orchestrator', 'node01'], _engines=['agy', 'claude'])
        n = node(attempt(0, failure='CHECK_FAILURE'))
        n['fingerprints'] = [P.fingerprint(n, 'other_node', 'CHECK_FAILURE', {'node': 'node01'})]
        got = P.decide(n, pol, budget(started=1), NOW)
        self.assertEqual(('regenerate', 'other_engine', {'engine': 'claude'}), (got['action'], got['strategy'], got['overrides']))

    def test_other_placements_are_tried_before_fail(self):
        # unknown-7: regenerate=4 with engines and nodes used to go feedback, fresh, fail
        pol = policy(regenerate=4, _engines=['claude', 'codex'], _nodes=['orchestrator', 'node09'])
        n = node(engine='claude', node='orchestrator')
        seen = []
        for i in range(8):
            got = P.decide(n, pol, budget(started=len(n['attempts'])), NOW)
            if got['action'] not in ('launch', 'regenerate'):
                break
            seen.append(got.get('strategy', 'fresh'))
            if got['action'] == 'regenerate':
                n['fingerprints'] = n.get('fingerprints', []) + [got['fingerprint']]
            n['attempts'].append(attempt(i, failure='CHECK_FAILURE', strategy=got.get('strategy', 'fresh')))
        self.assertEqual(['fresh', 'feedback', 'other_node', 'other_engine', 'fresh'], seen)

    def test_feedback_exempt_from_cycle_refusal(self):
        n = node(attempt(0, failure='SYNTAX'), attempt(1, failure='SYNTAX', strategy='feedback', kind='regen'))
        n['last_fingerprint'] = P.fingerprint(n, 'feedback', 'SYNTAX')
        got = P.decide(n, policy(strategies=['feedback'], regenerate=3), budget(started=2), NOW)
        self.assertEqual((got['action'], got['strategy']), ('regenerate', 'feedback'))

    def test_decompose_needs_depth_and_semantic_failure(self):
        exhausted = dict(candidates=1, regenerate=0)
        n = node(attempt(0, failure='CHECK_FAILURE'))
        self.assertEqual(P.decide(n, policy(depth=1, **exhausted), budget(started=1), NOW)['action'], 'decompose')
        self.assertEqual(P.decide(n, policy(depth=0, **exhausted), budget(started=1), NOW)['action'], 'fail')
        deep = node(attempt(0, failure='CHECK_FAILURE'), depth=1)
        self.assertEqual(P.decide(deep, policy(depth=1, **exhausted), budget(started=1), NOW)['action'], 'fail')
        refused = node(attempt(0, failure='CHECK_FAILURE'), split_refused=True)
        self.assertEqual(P.decide(refused, policy(depth=1, **exhausted), budget(started=1), NOW)['action'], 'fail')
        infra = node(attempt(0, failure='INFRASTRUCTURE'))
        self.assertEqual(P.decide(infra, policy(depth=1, **exhausted), budget(started=1), NOW)['action'], 'fail')
        one_syntax = node(attempt(0, failure='SYNTAX'))
        self.assertEqual(P.decide(one_syntax, policy(depth=1, **exhausted), budget(started=1), NOW)['action'], 'fail')
        two_syntax = node(attempt(0, failure='SYNTAX'), attempt(1, failure='SYNTAX'))
        self.assertEqual(P.decide(two_syntax, policy(depth=1, candidates=2, regenerate=0), budget(started=2), NOW)['action'],
                         'decompose')

    def test_one_planner_per_node(self):
        n = node(attempt(0, failure='CHECK_FAILURE'), attempt(1, failure='UNKNOWN', strategy='split', kind='planner'))
        got = P.decide(n, policy(depth=1, candidates=1, regenerate=0), budget(started=2), NOW)
        self.assertEqual(got['action'], 'fail')

    def test_handoff(self):
        pol = policy(generations=3)
        n = node(attempt(0, status='handoff'))
        self.assertEqual(P.decide(n, pol, budget(started=1), NOW),
                         {'action': 'handoff', 'generation': 1, 'from': 'n0-a0',
                          'reason': 'worker checkpointed near its context limit; spawn its successor'})
        n['generation'] = 3
        self.assertEqual(P.decide(n, pol, budget(started=1), NOW)['reason'], 'handoff generations exhausted')
        n['generation'] = 1
        self.assertEqual(P.decide(n, pol, budget(started=24), NOW)['action'], 'fail')
        # a successor names its predecessor (`from`), as every coordinator handoff launch does
        later = node(attempt(0, status='handoff'), attempt(1, failure='SYNTAX', kind='handoff', strategy='handoff', **{'from': 'n0-a0'}))
        self.assertNotEqual(P.decide(later, pol, budget(started=2), NOW)['action'], 'handoff')

    def test_perpetual(self):
        pol = policy(perpetual=True, generations=3, interval_seconds=900)
        self.assertEqual(P.decide(node(perpetual=True), pol, budget(), NOW)['action'], 'perpetual_next')
        self.assertEqual(P.decide(node(perpetual=True), pol, budget(), NOW)['generation'], 1)
        n = node(attempt(0, status='generation_done', kind='perpetual', finished=NOW - 10), perpetual=True, generation=1)
        self.assertEqual(P.decide(n, pol, budget(started=1), NOW),
                         {'action': 'wait', 'until': NOW - 10 + 900, 'reason': 'perpetual interval not elapsed'})
        n['attempts'][0]['finished'] = NOW - 900
        self.assertEqual(P.decide(n, pol, budget(started=1), NOW)['generation'], 2)
        self.assertEqual(P.decide(n, pol, budget(started=24), NOW)['action'], 'fail')
        n['generation'] = 3
        self.assertEqual(P.decide(n, pol, budget(started=24), NOW)['action'], 'accept')
        self.assertIsNone(P.decide(n, pol, budget(started=24), NOW)['attempt'])

    def test_fail_on_exhausted_budget_or_deadline(self):
        n = node(attempt(0, failure='SYNTAX'))
        self.assertEqual(P.decide(n, policy(), budget(started=24), NOW)['reason'], 'budget or deadline exhausted')
        self.assertEqual(P.decide(n, policy(), budget(started=1, deadline=NOW), NOW)['action'], 'fail')

    def test_fail_when_waves_used(self):
        n = node(attempt(0, failure='SYNTAX'), attempt(1, failure='CHECK_FAILURE', kind='regen', strategy='feedback'))
        got = P.decide(n, policy(candidates=1, regenerate=1), budget(started=2), NOW)
        self.assertEqual(got, {'action': 'fail', 'reason': 'no eligible strategy remains: SYNTAX, CHECK_FAILURE'})

    def test_every_action_is_declared(self):
        self.assertEqual(set(P.ACTIONS), {'wait', 'launch', 'design', 'accept', 'regenerate', 'decompose', 'handoff', 'stuck',
                                          'perpetual_next', 'fail', 'stop'})


# ------------------------------------------------------------------------------ split

PARENT = 'Create the files a.js and b.js in the folder /home/p/x, with a.js exporting run() and b.js calling it'


class SplitTests(unittest.TestCase):
    def test_split_prompt(self):
        text = P.split_prompt(PARENT, '/home/p/x', policy(children=5), 1)
        self.assertIn(P.SPLIT_FILE, text)
        self.assertIn('/home/p/x', text)
        self.assertIn('between 2 and 5 lines', text)
        self.assertIn('(depth 1)', text)
        self.assertTrue(text.endswith(PARENT))

    def test_valid_split(self):
        text = ('Create the file a.js in the folder /home/p/x exporting run()\n\n'
                'Create the file b.js in the folder /home/p/x calling run() from a.js\n')
        lines, errors = P.parse_split(text, PARENT, '/home/p/x', policy())
        self.assertEqual(errors, [])
        self.assertEqual(lines, ['Create the file a.js in the folder /home/p/x exporting run()',
                                 'Create the file b.js in the folder /home/p/x calling run() from a.js'])

    def test_line_count(self):
        one = 'Create the files a.js and b.js in the folder /home/p/x exporting run()'
        lines, errors = P.parse_split(one, PARENT, '/home/p/x', policy())
        self.assertEqual(lines, [])
        self.assertIn('the split has 1 lines; it needs 2 to 4', errors)
        many = '\n'.join(f'Create the file f{i}.js and a.js and b.js in the folder /home/p/x' for i in range(3))
        self.assertIn('the split has 3 lines; it needs 2 to 2', P.parse_split(many, PARENT, '/home/p/x', policy(children=2))[1])
        self.assertIn('the split has 0 lines; it needs 2 to 4', P.parse_split('', PARENT, '/home/p/x', policy())[1])

    def test_lint_errors(self):
        text = 'Create the file a.js in the folder /home/p/x and b.js\nshort b.js'
        lines, errors = P.parse_split(text, PARENT, '/home/p/x', policy())
        self.assertEqual(lines, [])
        self.assertIn('line 2: shorter than 20 characters: one full self-contained statement per line', errors)

    def test_dropped_files(self):
        text = ('Create the file a.js in the folder /home/p/x exporting run()\n'
                'Create the file c.js in the folder /home/p/x calling run()')
        errors = P.parse_split(text, PARENT, '/home/p/x', policy())[1]
        self.assertIn('the split drops files the statement names: b.js', errors)

    def test_folder_required_and_must_be_the_workspace(self):
        text = ('Create the file a.js exporting run() and nothing more\n'
                'Create the file b.js in the folder /home/p/x calling run()')
        self.assertIn('every split line must name the absolute folder', P.parse_split(text, PARENT, '/home/p/x', policy())[1])
        text = ('Create the file a.js in the folder /tmp/elsewhere exporting run()\n'
                'Create the file b.js in the folder /home/p/x calling run()')
        self.assertIn('every split line must name the absolute folder', P.parse_split(text, PARENT, '/home/p/x', policy())[1])

    def test_identical_line_refused(self):
        text = PARENT.upper() + '.\nCreate the file b.js in the folder /home/p/x calling run()'
        errors = P.parse_split(text, PARENT, '/home/p/x', policy())[1]
        self.assertIn('a split line repeats the statement it should replace', errors)


# ------------------------------------------------------------------------------ prompts and checkpoints

class PromptTests(unittest.TestCase):
    def test_worker_suffix(self):
        short = P.worker_suffix(policy(generations=1, self_split=False), 0, '/home/p/x')
        self.assertNotIn(P.CHECKPOINT_FILE, short)
        self.assertIn('Only files on disk count', short)
        self.assertEqual(len(short.splitlines()), 1)
        # the default policy lets a worker propose its own subdivision instead of partial work
        selfsplit = P.worker_suffix(policy(generations=1), 0, '/home/p/x')
        self.assertIn(P.SPLIT_FILE, selfsplit)
        self.assertNotIn(P.CHECKPOINT_FILE, selfsplit)
        for pol in (policy(generations=3), policy(generations=1, perpetual=True)):
            text = P.worker_suffix(pol, 0, '/home/p/x')
            self.assertIn(P.CHECKPOINT_FILE, text)
            self.assertIn(P.HANDOFF_FILE, text)
            self.assertNotIn('/home/p/x', text)             # D6: the working folder, never the project path
            self.assertIn(P.WORKING_FOLDER, text)
            self.assertIn('"version": 1', text)
            self.assertLess(len(text), 1000)

    def test_handoff_prompt(self):
        cp = {'done': ['wrote a.js'], 'left': ['write b.js'], 'files': ['a.js']}
        text = P.handoff_prompt('Create the file b.js in the folder /home/p/x', cp, 2)
        self.assertIn('generation 2', text)
        self.assertIn('checkpoint', text)
        self.assertIn('Done: wrote a.js', text)
        self.assertIn('Left: write b.js', text)
        self.assertIn('Files it touched: a.js', text)
        self.assertTrue(text.endswith('Create the file b.js in the folder /home/p/x'))
        empty = P.handoff_prompt('S' * 30, {}, 1)
        self.assertIn('nothing recorded', empty)
        self.assertIn('everything not listed as done', empty)
        huge = {'done': ['d' * 500] * 100, 'left': ['l' * 500] * 100, 'files': ['f' * 100] * 100}
        self.assertLess(len(P.handoff_prompt('S' * 30, huge, 1)), 1500 + 1500 + 800 + 600)

    def test_perpetual_prompt(self):
        text = P.perpetual_prompt('Index the folder /home/p/notes', {'done': ['a.md'], 'left': ['b.md']}, 4, 900)
        self.assertIn('Perpetual generation 4', text)
        self.assertIn(P.CHECKPOINT_FILE, text)
        self.assertIn(P.HANDOFF_FILE, text)
        self.assertIn('Earlier done: a.md.', text)
        self.assertIn('Cursor: b.md.', text)
        start = P.perpetual_prompt('Index the folder /home/p/notes', None, 1, 900)
        self.assertIn('Earlier done: none.', start)
        self.assertIn('Cursor: start.', start)
        huge = {'done': ['d' * 500] * 100, 'left': ['l' * 500] * 100}
        self.assertLess(len(P.perpetual_prompt('S' * 30, huge, 1, 60)), 1500 + 1500 + 700)


class CheckpointTests(unittest.TestCase):
    def valid(self, **over):
        value = {'version': 1, 'done': ['a'], 'left': ['b'], 'files': ['a.js']}
        value.update(over)
        return value

    def test_bad_json_and_shape(self):
        self.assertEqual(P.checkpoint_valid('{nope', ['a.js']), {'valid': False, 'reason': 'checkpoint is not JSON'})
        self.assertEqual(P.checkpoint_valid('[]', [])['reason'], 'checkpoint lacks version 1')
        no_version = self.valid()
        del no_version['version']
        self.assertEqual(P.checkpoint_valid(json.dumps(no_version), ['a.js'])['reason'], 'checkpoint lacks version 1')
        self.assertEqual(P.checkpoint_valid(self.valid(version=2), ['a.js'])['reason'], 'checkpoint lacks version 1')
        for key in ('done', 'left', 'files'):
            self.assertEqual(P.checkpoint_valid(self.valid(**{key: 'a'}), ['a.js'])['reason'],
                             f'checkpoint {key} must be a list of strings')
            self.assertFalse(P.checkpoint_valid(self.valid(**{key: [1]}), ['a.js'])['valid'])
            missing = self.valid()
            del missing[key]
            self.assertFalse(P.checkpoint_valid(missing, ['a.js'])['valid'])

    def test_files_must_exist(self):
        got = P.checkpoint_valid(self.valid(files=['a.js', 'ghost.js']), ['a.js'])
        self.assertEqual(got, {'valid': False, 'reason': 'checkpoint names files absent from the workspace: ghost.js'})
        self.assertFalse(P.checkpoint_valid(self.valid(), None)['valid'])

    def test_nothing_done_nor_left(self):
        got = P.checkpoint_valid(self.valid(done=[], left=[]), ['a.js'])
        self.assertEqual(got['reason'], 'checkpoint records nothing done and nothing left')

    def test_valid_forms(self):
        expected = {'valid': True, 'done': ['a'], 'left': ['b'], 'files': ['a.js']}
        self.assertEqual(P.checkpoint_valid(json.dumps(self.valid()), ['a.js']), expected)
        self.assertEqual(P.checkpoint_valid(json.dumps(self.valid()).encode(), ['a.js']), expected)
        self.assertEqual(P.checkpoint_valid(self.valid(), ['a.js']), expected)
        self.assertTrue(P.checkpoint_valid(self.valid(files=['src/app.js']), ['src/app.js'])['valid'])
        self.assertFalse(P.checkpoint_valid(self.valid(files=['src/app.js']), ['app.js'])['valid'])  # D9: exact path only
        self.assertTrue(P.checkpoint_valid(self.valid(done=[], files=[]), [])['valid'])
        big = P.checkpoint_valid(self.valid(done=['x'] * 100, left=['y'] * 100), ['a.js'])
        self.assertEqual((len(big['done']), len(big['left'])), (64, 64))


class FeedbackTests(unittest.TestCase):
    def test_public_failures_only(self):
        ver = {'passed': False, 'checks': [
            {'kind': 'exists', 'file': 'a.js', 'passed': False, 'public': True, 'output': 'a.js was not created'},
            {'kind': 'command', 'command': 'make ok', 'passed': True, 'public': True, 'output': 'PASSED-OUTPUT'},
            {'kind': 'hidden', 'passed': False, 'public': False, 'output': 'SECRET-ORACLE expected 42'},
            {'kind': 'command', 'command': 'make test', 'passed': False, 'public': True, 'output': 'FAIL: test_run'},
            {'kind': 'fetch', 'passed': False, 'public': False, 'output': 'node unreachable'},
        ]}
        note = P.feedback_note('S', ver, policy())
        self.assertIn('- exists a.js: a.js was not created', note)
        self.assertIn('- command make test: FAIL: test_run', note)
        self.assertNotIn('SECRET-ORACLE', note)
        self.assertNotIn('PASSED-OUTPUT', note)
        self.assertNotIn('node unreachable', note)

    def test_empty_when_only_hidden_failed(self):
        ver = {'checks': [{'kind': 'hidden', 'passed': False, 'public': False, 'output': 'x'}]}
        self.assertEqual(P.feedback_note('S', ver, policy()), '')
        self.assertEqual(P.feedback_note('S', None, policy()), '')

    def test_truncated(self):
        ver = {'checks': [{'kind': 'command', 'command': f'make t{i}', 'passed': False, 'public': True, 'output': 'E' * 5000}
                          for i in range(10)]}
        self.assertEqual(len(P.feedback_note('S', ver, policy(feedback_chars=200))), 200)
        long_note = P.feedback_note('S', ver, policy(feedback_chars=6000))
        self.assertEqual(len(long_note), 6000)
        self.assertNotIn('E' * 801, long_note)


class SummaryTests(unittest.TestCase):
    def test_shape(self):
        run = {'id': 'autogen-' + 'a' * 24, 'status': 'active', 'error': None,
               'budget': {'agents_started': 3, 'agents_max': 24},
               'nodes': [node(attempt(0, failure='SYNTAX'), attempt(1, status='accepted'), statement='C' * 150,
                              status='accepted', winner='n0-a1', generation=1),
                         {'id': 'n1', 'statement': 'Create the file b.js in the folder /home/p/x', 'status': 'pending'}]}
        got = P.summary(run)
        self.assertEqual(set(got), {'id', 'status', 'error', 'agents_started', 'agents_max', 'nodes', 'until_done'})
        self.assertEqual((got['error'], got['agents_started'], got['agents_max']), ('', 3, 24))
        self.assertEqual({k: v for k, v in got['nodes'][0].items() if k not in ('stale', 'progress', 'items_total')},
                         {'id': 'n0', 'depth': 0, 'status': 'accepted', 'statement': 'C' * 100,
                                           'attempts': 2, 'accepted': 1, 'failed': ['SYNTAX'], 'generation': 1,
                                           'children': [], 'winner': 'n0-a1'})
        self.assertEqual(got['nodes'][1]['attempts'], 0)
        self.assertEqual(got['nodes'][1]['winner'], '')
        self.assertEqual(P.summary({}), {'id': None, 'status': None, 'error': '', 'agents_started': 0,
                                         'agents_max': 0, 'nodes': [], 'until_done': False})


class FingerprintTests(unittest.TestCase):
    def test_fingerprint(self):
        n = node()
        same = node(attempt(0), engine='claude')
        self.assertEqual(P.fingerprint(n, 'fresh', 'SYNTAX'), P.fingerprint(same, 'fresh', 'SYNTAX'))
        self.assertNotEqual(P.fingerprint(n, 'fresh', 'SYNTAX'), P.fingerprint(n, 'feedback', 'SYNTAX'))
        self.assertNotEqual(P.fingerprint(n, 'fresh', 'SYNTAX'), P.fingerprint(n, 'fresh', 'NO_OUTPUT'))
        self.assertNotEqual(P.fingerprint(n, 'fresh', 'SYNTAX'), P.fingerprint(node(depth=1), 'fresh', 'SYNTAX'))



# ------------------------------------------------------------------------------ review findings (2026-10-10)

class LocalizationTests(unittest.TestCase):
    """D6: every attempt runs in its own checkout, so its instruction never names the project folder."""

    def test_folder_mentions_become_the_working_folder(self):
        text = P.localize('Create the file app.py in the folder /home/p/x with main(), then run it in /home/p/x.', '/home/p/x')
        self.assertEqual('Create the file app.py in ' + P.WORKING_FOLDER + ' with main(), then run it in '
                         + P.WORKING_FOLDER + '.', text)
        self.assertNotIn('/home/p/x', text)

    def test_paths_below_the_folder_become_relative(self):
        self.assertEqual('Extend the file src/app.py keeping every existing part.',
                         P.localize('Extend the file /home/p/x/src/app.py keeping every existing part.', '/home/p/x'))

    def test_other_folders_and_longer_names_are_untouched(self):
        for text in ('Read the folder /home/p/xy and /home/p/x.bak', 'Copy /srv/data into the result'):
            self.assertEqual(text, P.localize(text, '/home/p/x'))
        self.assertEqual('same', P.localize('same', ''))

    def test_delocalize_maps_planner_lines_back(self):
        line = 'Create the file a.js in the current working folder exporting run()'
        self.assertEqual('Create the file a.js in the folder /home/p/x exporting run()', P.delocalize(line, '/home/p/x'))
        full = 'Create the file b.js in ' + P.WORKING_FOLDER + ' calling run()'
        self.assertEqual('Create the file b.js in the folder /home/p/x calling run()', P.delocalize(full, '/home/p/x'))
        for line in (P.localize(PARENT, '/home/p/x'),):
            self.assertEqual(PARENT, P.delocalize(line, '/home/p/x'))

    def test_prompts_name_no_project_folder(self):
        pol = policy(generations=3)
        self.assertNotIn('/home/p/x', P.split_prompt('S' * 30, '/home/p/x', pol, 0))
        self.assertIn(P.WORKING_FOLDER, P.split_prompt('S' * 30, '/home/p/x', pol, 0))
        self.assertNotIn('/home/p/x', P.worker_suffix(pol, 0, '/home/p/x'))


class StatementFileFindingsTests(unittest.TestCase):
    def test_statement_files_keeps_directory_components(self):
        # review test 6 (D13)
        self.assertEqual(['src/a.py', 'src/b.py'],
                         P.statement_files('Create the files src/a.py and src/b.py in the folder /home/u/p.')['files'])
        self.assertEqual(['src/app.py', 'lib/util.py'],
                         P.statement_files('Make src/app.py import lib/util.py in the folder /home/u/p')['files'])
        lines, errors = P.parse_split(
            'Create the file src/a.py in the folder /home/u/p with function f returning 1.\n'
            'Create the file verify.txt in the folder /home/u/p recording PASS after importing src.a.',
            'Create the files src/a.py and src/b.py in the folder /home/u/p with functions f and g.', '/home/u/p', policy())
        self.assertEqual([], lines)
        self.assertIn('the split drops files the statement names: src/b.py', errors)

    def test_prose_runtime_names_are_not_files(self):
        # review test 7 (D13)
        text = 'Create the file server.js in the folder /home/u/p serving index.html with node.js.'
        self.assertEqual(['server.js', 'index.html'], P.statement_files(text)['files'])
        self.assertNotIn('node.js', [c.get('file') for c in P.plan_checks(text, 0, policy())['checks']])
        for name in ('Next.js', 'vue.js', 'three.js', 'd3.js'):
            self.assertEqual(['app.js'], P.statement_files(f'Create the file app.js in the folder /home/u/p using {name}')['files'])
        self.assertEqual(['three.js'], P.statement_files('Create the file three.js in the folder /home/u/p')['files'])


class PlanVerbTests(unittest.TestCase):
    def kinds(self, plan):
        return [(c['kind'], c.get('file') or c.get('command'), bool(c.get('changed'))) for c in plan['checks']]

    def test_delete_and_remove_plan_absent_checks(self):
        # item 3: a correct deletion used to fail exists/syntax forever
        for verb in ('Delete', 'Remove'):
            plan = P.plan_checks(f'{verb} the file old.js in the folder /p/x because nothing imports it', 0, policy())
            self.assertEqual([('absent', 'old.js', False)], self.kinds(plan))
        # removing PART of a file is an edit of that file
        plan = P.plan_checks('Remove the function legacy from the file app.js in the folder /p/x, keeping every existing part', 0, policy())
        self.assertEqual([('exists', 'app.js', True), ('syntax', 'app.js', False)], self.kinds(plan))

    def test_rename_and_move_check_only_the_destination(self):
        plan = P.plan_checks('Rename the file a.js to b.js in the folder /p/x', 0, policy())
        self.assertEqual([('exists', 'b.js', True), ('syntax', 'b.js', False)], self.kinds(plan))
        plan = P.plan_checks('Move the file src/a.py to the file lib/a.py in the folder /p/x', 0, policy())
        self.assertEqual([('exists', 'lib/a.py', True), ('syntax', 'lib/a.py', False)], self.kinds(plan))

    def test_primary_files_must_change_bare_mentions_only_exist(self):
        # item 2: KIRBY_HTML creates kirby.html and only loads kirby.js
        plan = P.plan_checks(KIRBY_HTML, 0, policy())
        self.assertEqual([('exists', 'kirby.html', True), ('exists', 'kirby.js', False), ('syntax', 'kirby.js', False)],
                         self.kinds(plan))
        verify = P.plan_checks(KIRBY_VERIFY, 3, policy())   # read-only verbs never require a change
        self.assertFalse(any(c.get('changed') for c in verify['checks']))


class V2ProgressTests(unittest.TestCase):
    def test_done_list_alone_is_never_progress(self):
        best = {'files': ['a.py'], 'checks': 2, 'done': 1}
        self.assertFalse(P.is_progress(best, {'files': ['a.py'], 'checks': 2, 'done': 9}))
        self.assertTrue(P.is_progress(best, {'files': ['a.py', 'b.py'], 'checks': 2, 'done': 0}))
        self.assertTrue(P.is_progress(best, {'files': ['a.py'], 'checks': 3, 'done': 0}))

    def test_named_files_bound_changed_paths(self):
        verdict = {'checks': [], 'changed': ['junk.txt', 'a.py', 'sub/b.py']}
        self.assertEqual(['a.py', 'junk.txt', 'sub/b.py'], P.progress_metrics(verdict)['files'])
        self.assertEqual(['a.py', 'sub/b.py'], P.progress_metrics(verdict, named=['a.py', 'b.py'])['files'])

    def test_stall_measures_are_derived_from_the_attempts(self):
        node = {'attempts': [
            {'kind': 'candidate', 'status': 'failed', 'failure': 'NO_OUTPUT', 'progress': {'new': True}},
            {'kind': 'regen', 'status': 'failed', 'failure': 'INFRASTRUCTURE'},          # another machine's problem
            {'kind': 'regen', 'status': 'failed', 'failure': 'TIMEOUT'},                 # hung: counts
            {'kind': 'planner', 'status': 'failed', 'failure': 'NO_OUTPUT'},             # not work
            {'kind': 'regen', 'status': 'failed', 'failure': 'CHECK_FAILURE', 'progress': {'new': False}},
            {'kind': 'handoff', 'status': 'handoff', 'progress': {'new': False}},
        ]}
        self.assertEqual(3, P.stale_count(node))
        self.assertEqual(1, P.handoff_stale(node))
        self.assertFalse(P.recent_progress(node))
        node['attempts'].append({'kind': 'regen', 'status': 'failed', 'failure': 'SYNTAX', 'progress': {'new': True}})
        self.assertEqual((0, 0, True), (P.stale_count(node), P.handoff_stale(node), P.recent_progress(node)))
        node['attempts'].append({'kind': 'regen', 'status': 'running'})
        self.assertTrue(P.recent_progress(node))                        # a running attempt is not yet evidence

    def test_a_spent_budget_at_a_stalled_handoff_is_terminal_not_a_split(self):
        node = {'status': 'pending', 'depth': 0, 'perpetual': False, 'handoffs': 2, 'planners': 0, 'attempts': [
            {'id': 'n0-a0', 'kind': 'candidate', 'status': 'handoff', 'progress': {'new': True}},
            {'id': 'n0-a1', 'kind': 'handoff', 'status': 'handoff', 'from': 'n0-a0', 'progress': {'new': False}},
            {'id': 'n0-a2', 'kind': 'handoff', 'status': 'handoff', 'from': 'n0-a1', 'progress': {'new': False}},
        ]}
        for until in (True, False):
            policy = P.normalize({'until_done': until, 'agents_max': 3, 'generations': 2, 'depth': 1})
            decision = P.decide(node, policy, {'agents_started': 3, 'agents_max': 3, 'deadline': None}, 0)
            self.assertEqual('stuck' if until else 'fail', decision['action'], until)
            self.assertIn('exhausted at a handoff', decision['reason'])
            decision = P.decide(node, policy, {'agents_started': 2, 'agents_max': 3, 'deadline': None}, 0)
            self.assertEqual(('decompose', True, 'n0-a2'), (decision['action'], decision.get('remaining'), decision.get('from')))

    def test_a_probe_exit_counts_only_as_a_real_failing_run(self):
        self.assertTrue(P.design_probe_ok(1))
        self.assertTrue(P.design_probe_ok(123, 'main: missing'))
        for rc in (0, 124, 125, 126, 127, 137):
            self.assertFalse(P.design_probe_ok(rc), rc)
        self.assertFalse(P.design_probe_ok(1, 'landlock: refusing to run unsandboxed'))
        self.assertFalse(P.design_probe_ok(1, 'symblic_sandbox: unknown argument \'--x\''))   # any launcher prefix
        self.assertTrue(P.design_probe_ok(1, 'main: FAIL expected 2 got 3'))

    def test_quotas_count_the_current_rotation_only(self):
        policy = P.normalize({'strategies': ['feedback', 'other_node', 'fresh'], 'regenerate': 2}, nodes=['orchestrator', 'node09'])
        node = {'engine': 'claude', 'node': 'orchestrator', 'attempts': [{'strategy': 'fresh'}, {'strategy': 'feedback'},
                                                                    {'strategy': 'other_node'}, {'strategy': 'fresh'}]}
        self.assertEqual(('fresh', {}), P.next_strategy(node, policy, ['NO_OUTPUT']))     # feedback and other_node spent
        node['rotation_start'] = 4
        self.assertEqual(('feedback', {}), P.next_strategy(node, policy, ['NO_OUTPUT']))


class CheckpointItemObjectsTests(unittest.TestCase):
    def test_item_objects_reduce_to_their_doi_url_or_title(self):
        raw = json.dumps({'version': 1, 'done': ['batch 1'], 'left': ['batch-2'], 'files': ['sources.md'], 'items': [
            {'title': 'Modular sensors', 'doi': '10.1038/s41565-024-01804-0', 'year': 2024},
            {'title': 'Only a title', 'year': 2023},
            {'url': 'https://example.org/p', 'title': 'Paged'},
            'plain text item',
        ]})
        out = P.checkpoint_valid(raw, ['sources.md'])
        self.assertTrue(out['valid'])
        self.assertEqual(['10.1038/s41565-024-01804-0 | Modular sensors', 'Only a title',
                          'https://example.org/p | Paged', 'plain text item'], out['items'])
        self.assertEqual(['doi:10.1038/s41565-024-01804-0', 'text:only a title', 'url:example.org/p',
                          'text:plain text item'], [P.items_key(x) for x in out['items']])
        self.assertEqual(P.items_key('https://www.example.org/p/#top'), P.items_key('http://example.org/p | Other title'))
        bad = json.dumps({'version': 1, 'done': ['x'], 'left': ['y'], 'files': [], 'items': [{'year': 2024}]})
        self.assertFalse(P.checkpoint_valid(bad, [])['valid'])
        worse = json.dumps({'version': 1, 'done': ['x'], 'left': ['y'], 'files': [], 'items': [42]})
        self.assertFalse(P.checkpoint_valid(worse, [])['valid'])


class FindingPolicyTests(unittest.TestCase):
    def test_normalize_refuses_stronger_model_until_wired(self):
        # D18
        with self.assertRaises(P.AutogenError) as ctx:
            P.normalize({'strategies': ['fresh', 'stronger_model']})
        self.assertIn('stronger_model is not available yet', str(ctx.exception))
        self.assertIn('stronger_model', P.STRATEGIES)

    def test_perpetual_attempt_is_never_accepted(self):
        # D1 / R6: an 'accepted' attempt on a perpetual node does not end the lane
        pol = policy(perpetual=True, generations=5, interval_seconds=60)
        n = node(attempt(0, status='accepted', kind='perpetual', finished=NOW - 100), perpetual=True, generation=1)
        self.assertEqual('perpetual_next', P.decide(n, pol, budget(started=1), NOW)['action'])

    def test_handoff_from_an_earlier_candidate_is_continued(self):
        # review test 10 (D10)
        pol = policy(candidates=2, regenerate=2, generations=3)
        n = node(attempt(0, status='handoff'), attempt(1, failure='CHECK_FAILURE'))
        got = P.decide(n, pol, budget(started=2), NOW)
        self.assertEqual(('handoff', 'n0-a0', 1), (got['action'], got['from'], got['generation']))

    def test_handoff_generations_are_counted_per_node(self):
        # item 5 / unknown-6: a regeneration reset node.generation to 0 and re-opened the cap
        pol = policy(generations=2)
        n = node(attempt(0, status='handoff', generation=0), generation=0, handoffs=2)
        self.assertEqual('handoff generations exhausted', P.decide(n, pol, budget(started=3), NOW)['reason'])

    def test_failed_planner_refuses_further_decomposition(self):
        # review test 8 (D8): the coordinator sets split_refused when a planner fails
        pol = policy(candidates=1, regenerate=0, depth=1, strategies=['fresh'])
        n = node(attempt(0, failure='CHECK_FAILURE'))
        self.assertEqual('decompose', P.decide(n, pol, budget(started=1), NOW)['action'])
        n['attempts'].append(attempt(1, failure='UNKNOWN', kind='planner', strategy='split'))
        n['split_refused'] = True
        got = P.decide(n, pol, budget(started=2), NOW)
        self.assertEqual('fail', got['action'])
        self.assertEqual('no eligible strategy remains: CHECK_FAILURE; the split was refused', got['reason'])

    def test_conflict_retries_once_on_the_same_placement_then_fails(self):
        # D15: a promotion conflict is the workspace's, not the engine's
        pol = policy(candidates=1, regenerate=0, _engines=['agy', 'claude'], _nodes=['orchestrator', 'node01'])
        n = node(attempt(0, failure='CONFLICT', engine='agy', node='orchestrator', error='apply conflicts: app.js'))
        got = P.decide(n, pol, budget(started=1), NOW)
        self.assertEqual(('regenerate', 'conflict_retry', {'engine': 'agy', 'node': 'orchestrator'}),
                         (got['action'], got['strategy'], got['overrides']))
        n['attempts'].append(attempt(1, failure='CONFLICT', engine='agy', node='orchestrator', kind='regen',
                                     strategy='conflict_retry', error='apply conflicts: app.js'))
        got = P.decide(n, pol, budget(started=2), NOW)
        self.assertEqual('fail', got['action'])
        self.assertIn('apply conflicts: app.js', got['reason'])
        self.assertIn('CONFLICT', P.NON_SEMANTIC)          # never counted toward decomposition

    def test_hidden_failure_never_uses_feedback_and_fetch_moves_machine(self):
        pol = policy(_engines=['agy', 'claude'], _nodes=['orchestrator', 'node01'])
        n = node(attempt(0, failure='HIDDEN_FAILURE'))
        self.assertNotEqual('feedback', P.next_strategy(n, pol, ['HIDDEN_FAILURE'])[0])
        self.assertEqual(('other_node', {'node': 'node01'}), P.next_strategy(n, pol, ['FETCH_FAILURE']))

    def test_perpetual_failures_are_capped_and_rotate_placement(self):
        # item 6: a failing lane used to relaunch every interval until agents_max
        pol = policy(perpetual=True, generations=5, regenerate=1, interval_seconds=60, _nodes=['orchestrator', 'node01'])
        done = attempt(0, status='generation_done', kind='perpetual', finished=NOW - 500)
        n = node(done, attempt(1, failure='INFRASTRUCTURE', kind='perpetual', finished=NOW - 100), perpetual=True, generation=1)
        got = P.decide(n, pol, budget(started=2), NOW)
        self.assertEqual(('perpetual_next', 2, {'node': 'node01'}), (got['action'], got['generation'], got['overrides']))
        n['attempts'].append(attempt(2, failure='INFRASTRUCTURE', kind='perpetual', finished=NOW - 100))
        got = P.decide(n, pol, budget(started=3), NOW)
        self.assertEqual('fail', got['action'])
        self.assertIn('2 generation(s) in a row', got['reason'])

    def test_unknown_or_failed_tasks_are_never_a_pass(self):
        # item 1 / D24: a vacuous plan (no checks) passed whatever the task status was
        vacuous = {'passed': True, 'checks': [], 'files_changed': None}
        self.assertEqual('UNKNOWN', P.classify(done_task(status='unknown'), vacuous))
        self.assertEqual('CANCELLED', P.classify(done_task(status='cancelled'), vacuous))
        self.assertEqual('REFUSAL', P.classify(done_task(status='failed', error='The agent refused its own launch'), vacuous))
        self.assertIsNone(P.classify(done_task(), vacuous))

    def test_checkpoint_with_nothing_left_is_not_a_handoff(self):
        # D9 / C10
        cp = P.checkpoint_valid('{"version":1,"done":["wrote hello.py"],"left":[],"files":[]}', [])
        self.assertTrue(cp['valid'])
        self.assertEqual('NO_OUTPUT', P.classify(done_task(), verdict(('exists', False)), handoff=cp))

    def test_feedback_lists_allowed_kinds_only(self):
        # D11 / section 4: a planner's split error never reaches a code worker
        ver = {'checks': [{'kind': 'split', 'passed': False, 'public': True, 'output': 'the split has 1 lines'},
                          {'kind': 'fetch', 'passed': False, 'public': True, 'output': 'node unreachable'}]}
        self.assertEqual('', P.feedback_note('S', ver, policy()))

    def test_fingerprint_includes_overrides(self):
        n = node()
        self.assertNotEqual(P.fingerprint(n, 'other_node', 'INFRASTRUCTURE', {'node': 'node02'}),
                            P.fingerprint(n, 'other_node', 'INFRASTRUCTURE', {'node': 'node03'}))
        self.assertEqual(P.fingerprint(n, 'fresh', 'SYNTAX'), P.fingerprint(n, 'fresh', 'SYNTAX', {}))

    def test_unsafe_list_is_advisory_but_catches_the_end_of_string(self):
        # D21: documented as advisory; `rm -rf /` at the very end is refused
        self.assertTrue(P.UNSAFE_COMMAND.search('make clean; rm -rf /'))
        self.assertIn('Advisory only', Path(P.__file__).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()


class UnproductiveSplitTests(unittest.TestCase):
    """A split child that never beats its parent's evidence is not split again (2026-10-11: a 3B model
    recursed four levels on cellsOf, each child accepting the one unit its parent had)."""

    def _child(self, parent_units, own_units, **extra):
        a0 = attempt(0, failure='NO_OUTPUT', progress={'new': False, 'files': [], 'checks': 0, 'units': own_units})
        a1 = attempt(1, failure='NO_OUTPUT', strategy='feedback', kind='regen',
                     progress={'new': False, 'files': [], 'checks': 0, 'units': own_units})
        a2 = attempt(2, failure='NO_OUTPUT', strategy='other_node', kind='regen',
                     progress={'new': False, 'files': [], 'checks': 0, 'units': own_units})
        return node(a0, a1, a2, id='n0.0', depth=1, parent='n0', sheet=True, stale=3,
                    progress={'files': [], 'checks': 0, 'done': 0, 'units': own_units},
                    parent_progress={'files': [], 'checks': 0, 'done': 0, 'units': parent_units}, **extra)

    def test_a_child_with_no_progress_over_its_parent_is_never_decomposed(self):
        pol = policy(until_done=True)
        got = P.decide(self._child(1, 1), pol, budget(maximum=0), NOW)
        self.assertNotEqual(got['action'], 'decompose', got)
        if got['action'] == 'stuck':
            self.assertIn('made no progress over its parent', got['reason'])

    def test_a_child_that_beat_its_parent_may_still_be_decomposed(self):
        pol = policy(until_done=True)
        got = P.decide(self._child(1, 3), pol, budget(maximum=0), NOW)
        self.assertEqual(got['action'], 'decompose', got)

    def test_a_root_node_is_unaffected(self):
        self.assertFalse(P.unproductive_split(node()))
        self.assertFalse(P.unproductive_split(node(parent_progress={})))
        self.assertTrue(P.unproductive_split(node(parent_progress={'units': 2, 'files': [], 'checks': 0},
                                                  progress={'units': 2, 'files': [], 'checks': 0})))
        self.assertFalse(P.unproductive_split(node(parent_progress={'units': 2, 'files': [], 'checks': 0},
                                                   progress={'units': 2, 'files': ['a.js'], 'checks': 0})))
