"""Symblic local beta: configuration, policy, placement, judges, gates, ledger, scheduling and the ladder hook.

Nothing here calls a model, reads a real node, opens the network or starts a lane: every lane command goes to a
fake Env that writes what the real CLI would print. Every ledger, run folder and configuration file is
temporary. The test configuration names nodes node-a, node-b and node-c, reserves node-r and excludes node-x.
"""
import copy
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'symblic' / 'bench' / 'local_beta.py'
FIXTURES = '@repo/symblic/bench/data/local_beta/fixtures/'


def load():
    spec = importlib.util.spec_from_file_location('symblic_local_beta_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load()

SPEC = {'lane': 'spec', 'path': 'sheets/markdown.sheet.md', 'harness': 'harness/markdown-harness.mjs',
        'file': 'markdown.html', 'samples': 2, 'retries': 3, 'rounds': 2}
TEST_CONFIG = {
    'version': 1,
    'models': ['qwen3:4b-instruct', 'phi4-mini', 'gemma3:1b', 'qwen2.5:0.5b', 'qwen2.5-coder:3b', 'granite3.3:2b'],
    'nodes': ['node-a', 'node-b', 'node-c'], 'reserved_nodes': ['node-r'], 'excluded_nodes': ['node-x'],
    'hot_celsius': 80,
    'commands': {'vitals': ['vitals', '{node}'], 'active_runs': ['runs'], 'cancel_run': ['cancel', '{id}'],
                 'research': ['/opt/tools/local-research', '--model', '{model}', '--node', '{node}', '--tools',
                              '{tools}', '--json', '{question}']},
    'search_health_url': 'http://127.0.0.1:9/healthz',
    'fixtures': {
        'markdown-13': {**SPEC, 'units': 13, 'total_seconds': 3600},
        'markdown-fine-37': {**SPEC, 'units': 37, 'total_seconds': 5400},
        'markdown-exact-37': {**SPEC, 'units': 37, 'total_seconds': 5400},
        'four-plus-four': {'lane': 'native', 'path': FIXTURES + 'native/four-plus-four.sym',
                           'expect': {'kernel and model agree': '[8, 8]'}, 'total_seconds': 900},
        'word-problem': {'lane': 'native', 'path': FIXTURES + 'native/word-problem.sym',
                         'expect': {'rolls left': '44'}, 'total_seconds': 900},
        'count-and-prime': {'lane': 'native', 'path': FIXTURES + 'native/count-and-prime.sym',
                            'expect': {'count and primality': '[3, false]'}, 'total_seconds': 900},
        'minutes-split': {'lane': 'native', 'path': FIXTURES + 'native/minutes-split.sym',
                          'expect': {'hours and minutes': '[2, 15]'}, 'total_seconds': 900},
        'change': {'lane': 'english', 'path': FIXTURES + 'english/change.english.txt', 'expect': {'change': '14'},
                   'max_calls': 12, 'wall_seconds': 900},
        'witness-delivery': {'lane': 'delegate', 'path': FIXTURES + 'delegate/witness-delivery.task.json',
                             'expect_result': {'path': ['quote'], 'equals': 'Delivery: Monday\n'}, 'wall_seconds': 900},
        'ladder-F1': {'lane': 'ladder', 'path': '@repo/benchmarks/frontier/ladder.json', 'family': 'F1',
                      'budget_seconds': 900, 'max_calls': 8},
        'doi-alphafold': {'lane': 'research', 'question': 'What is the exact title of the article with DOI X?',
                          'expect': 'Highly accurate protein structure prediction with AlphaFold', 'tools': 4,
                          'wall_seconds': 1200}},
    'batches': {
        'first': {'pairs': ['qwen3:4b-instruct@node-b', 'gemma3:1b@node-a'],
                  'trials': [['native', 'four-plus-four'], ['native', 'word-problem'], ['native', 'count-and-prime'],
                             ['research', 'doi-alphafold'], ['spec', 'markdown-13']]},
        'second': {'items': [['spec', 'markdown-exact-37', 'gemma3:1b@node-a', {'samples': 1, 'retries': 3, 'rounds': 1, 'total_seconds': 3600}],
                             ['spec', 'markdown-exact-37', 'qwen2.5:0.5b@node-b', {'samples': 1, 'retries': 3, 'rounds': 1, 'total_seconds': 3600}],
                             ['spec', 'markdown-fine-37', 'qwen2.5-coder:3b@node-a', {'samples': 1, 'retries': 3, 'rounds': 1, 'total_seconds': 3600}],
                             ['spec', 'markdown-fine-37', 'granite3.3:2b@node-b', {'samples': 1, 'retries': 3, 'rounds': 1, 'total_seconds': 3600}]]}}}
_CONFIG_DIR = tempfile.TemporaryDirectory(prefix='symblic-local-beta-config-')


def setUpModule():
    path = Path(_CONFIG_DIR.name) / 'config.json'
    path.write_text(json.dumps(TEST_CONFIG))
    B.use_config(path)


def tearDownModule():
    _CONFIG_DIR.cleanup()


def report(status='done', outputs=(), error=None, calls=1, bindings=()):
    return {'status': status, 'outputs': list(outputs), 'error': error, 'calls': calls, 'asks': 1, 'cached': 0,
            'fingerprint': 'f' * 16, 'bindings': list(bindings)}


def call_row(node='node-b', ok=True, ms=1000):
    return {'ok': ok, 'app': f'ollama:qwen3:4b-instruct@{node}', 'ms': ms, 'reply': {'node': node},
            'model_identity_raw': {'digest': 'sha256:abc'}}


class FakeEnv:
    """The outside world for one test: a fake clock, fake cluster reads and fake lane commands."""

    def __init__(self, temps=None, runs=None, inventory=None, search=True, lanes=None, delay=0.0, monitored=True):
        self.t = 1_000_000.0
        self._monitored = monitored
        self.temps = temps if temps is not None else {'node-a': 40.0, 'node-b': 40.0}
        self.runs = list(runs or [])
        self.inv = inventory if inventory is not None else {
            'node-a': {'qwen3:4b-instruct', 'gemma3:1b'}, 'node-b': {'qwen3:4b-instruct', 'gemma3:1b'}}
        self.search = search
        self.lanes = lanes or {}
        self.delay = delay
        self.calls, self.cancelled, self.slept = [], [], 0
        self.lock = threading.Lock()
        self.running, self.peak, self.peak_node = 0, 0, {}
        self._per_node = {}

    def now(self):
        with self.lock:
            self.t += 1.0
            return self.t

    def sleep(self, seconds):
        self.slept += seconds
        with self.lock:
            self.t += seconds

    def monitored(self):
        return self._monitored

    def node_vitals(self, node, force=True):
        temp = self.temps.get(node)
        if temp == 'offline':
            return False, None
        if temp == 'raise':
            raise OSError('status down')
        return True, temp

    def active_runs(self):
        return list(self.runs)

    def search_up(self):
        return self.search

    def inventory(self):
        return self.inv

    def cancel_run(self, run_id):
        self.cancelled.append(run_id)
        return True

    def run(self, argv, *, cwd, env, stdout_path, stderr_path, timeout, grace=60):
        kind = kind_of(argv)
        node = next((a.rpartition('@')[2] for a in argv if a.startswith('ollama:')), None) or \
            (argv[argv.index('--node') + 1] if '--node' in argv else None)
        with self.lock:
            self.calls.append({'argv': list(argv), 'env': env, 'kind': kind, 'timeout': timeout})
            self.running += 1
            self.peak = max(self.peak, self.running)
            if node:
                self._per_node[node] = self._per_node.get(node, 0) + 1
                self.peak_node[node] = max(self.peak_node.get(node, 0), self._per_node[node])
        try:
            if self.delay:
                time.sleep(self.delay)
            handler = self.lanes.get(kind) or DEFAULTS.get(kind) or (lambda *_: ('', 0, False, None))
            out, code, timed_out, calls = handler(argv, stdout_path)
            Path(stdout_path).write_text(out if isinstance(out, str) else json.dumps(out))
            Path(stderr_path).write_text('')
            if calls is not None and '--dir' in argv:
                folder = Path(argv[argv.index('--dir') + 1])
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'calls.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in calls))
            return {'exit': code, 'timed_out': timed_out, 'seconds': 1.0}
        finally:
            with self.lock:
                self.running -= 1
                if node:
                    self._per_node[node] -= 1


def kind_of(argv):
    a = [str(x) for x in argv]
    if a[0] == 'bash':
        return 'session'
    if a[1:4] == ['-m', 'symblic.spec.sheets', 'compile']:
        return 'compile'
    if len(a) > 1 and a[1].endswith('.mjs'):
        return 'harness'
    if a[0].endswith('local-research'):
        return 'research'
    if len(a) > 2 and a[1].endswith('symblic_frontier_ladder.py'):
        return 'ladder-' + a[2]
    if a[0].endswith('tools/symblic') and a[1:2] == ['run']:
        return 'run'
    if a[0].endswith('tools/symblic') and a[1:3] == ['english', 'run']:
        return 'english'
    if a[0].endswith('tools/symblic') and a[1:3] == ['delegate', 'run']:
        return 'delegate'
    if a[0].endswith('tools/symblic') and a[1:3] == ['mica', 'benchmark']:
        return 'freeze'
    return 'unknown'


def _node_of(argv):
    app = next((a for a in argv if str(a).startswith('ollama:')), 'ollama:x@node-b')
    return app.rpartition('@')[2]


DEFAULTS = {
    'compile': lambda argv, out: (f'program Build.\nuse by=["{argv[argv.index("--by") + 1]}"], route=search.\n'
                                  '# unit 1 of 2\nask unit_a: Code js "a".\n# unit 2 of 2\n', 0, False, None),
    'run': lambda argv, out: (report(outputs=[{'label': 'rolls left', 'text': '44'},
                                              {'label': 'kernel and model agree', 'text': '[8, 8]'},
                                              {'label': 'count and primality', 'text': '[3, false]'},
                                              {'label': 'markdown.html', 'value': '<script>function render(){}</script>'}]),
                              0, False, [call_row(_node_of(argv))]),
    'english': lambda argv, out: (report(outputs=[{'label': '', 'binding': 'change', 'text': '14'}]), 0, False,
                                  [call_row(_node_of(argv))]),
    'delegate': lambda argv, out: ({'accepted': True, 'status': 'done', 'calls': 1,
                                    'result': {'quote': 'Delivery: Monday\n'}}, 0, False, [call_row(_node_of(argv))]),
    'research': lambda argv, out: ([{'model': 'qwen3:4b-instruct', 'node': argv[argv.index('--node') + 1],
                                     'answer': 'The title is "Highly Accurate Protein Structure Prediction with AlphaFold" [1].',
                                     'steps': [{'call': 'SEARCH: doi', 'result': '...'}], 'sources': [{}], 'seconds': 9}],
                                   0, False, None),
    'harness': lambda argv, out: (json.dumps({'ok': True, 'cases': 500, 'pass': 500, 'fail': 0, 'errors': 0,
                                              'plain': 8, 'plainOf': 8, 'fingerprint': '2662abdb7f298d32'}), 0, False, None),
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'state'
        self.ledger = B.Ledger(self.state / 'ledger.jsonl')

    def trial(self, lane, fixture, env, pair='qwen3:4b-instruct@node-b', **kw):
        model, node = B.parse_pair(pair)
        return B.Trial(lane, fixture, model, node, state=self.state, env=env, ledger=self.ledger, batch='t',
                       poll=30, **kw).run()


class Inert(unittest.TestCase):
    def test_import_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'never-created'
            old = os.environ.get('SYMBLIC_LOCAL_BETA_STATE')
            os.environ['SYMBLIC_LOCAL_BETA_STATE'] = str(target)
            try:
                load()
            finally:
                if old is None:
                    os.environ.pop('SYMBLIC_LOCAL_BETA_STATE', None)
                else:
                    os.environ['SYMBLIC_LOCAL_BETA_STATE'] = old
            self.assertFalse(target.exists())


class Policy(unittest.TestCase):
    def test_only_configured_models_on_configured_nodes(self):
        self.assertEqual(B.check_policy('qwen3:4b-instruct', 'node-b'), ('qwen3:4b-instruct', 'node-b'))
        self.assertEqual(B.check_policy('phi4-mini:latest', 'node-a')[0], 'phi4-mini:latest')
        for model, node in (('qwen2.5:14b', 'node-b'), ('qwen3:4b-instruct', 'node-x'), ('gemma3:1b', 'node-r'),
                            ('gemma3:1b', 'unknown-node')):
            with self.assertRaises(B.PolicyError, msg=(model, node)):
                B.check_policy(model, node)
        self.assertEqual(B.check_policy('gemma3:1b', 'node-r', allow_reserved=True)[1], 'node-r')
        with self.assertRaises(B.PolicyError):
            B.check_policy('gemma3:1b', 'node-x', allow_reserved=True)

    def test_pairs_name_an_ollama_model_never_an_agent(self):
        self.assertEqual(B.parse_pair('gemma3:1b@node-a'), ('gemma3:1b', 'node-a'))
        for bad in ('ollama:gemma3:1b@node-a', 'claude:haiku@node-b', 'codex@node-b', 'command:x@node-b', 'gemma3:1b',
                    '@node-b'):
            with self.assertRaises(B.PolicyError, msg=bad):
                B.parse_pair(bad)

    def test_first_batch_comes_from_the_configuration(self):
        trials = B.batch_trials('first')
        self.assertEqual(len(trials), 10)
        self.assertEqual({(t[2], t[3]) for t in trials}, {('qwen3:4b-instruct', 'node-b'), ('gemma3:1b', 'node-a')})
        lanes = sorted(t[0] for t in trials if t[3] == 'node-b')
        self.assertEqual(lanes, ['native', 'native', 'native', 'research', 'spec'])
        self.assertNotIn('ladder', {t[0] for t in trials})
        self.assertIn(('spec', 'markdown-13'), {(t[0], t[1]) for t in trials})
        with self.assertRaises(B.PolicyError):
            B.batch_trials('no-such-batch')

    def test_relative_and_repository_paths_resolve(self):
        cfg = B.config()
        self.assertEqual(cfg.fixtures['markdown-13']['path'], cfg.origin.parent / 'sheets' / 'markdown.sheet.md')
        self.assertEqual(cfg.fixtures['ladder-F1']['path'], REPO / 'benchmarks' / 'frontier' / 'ladder.json')

    def test_a_malformed_configuration_is_refused(self):
        for change in ({'version': 2}, {'version': True}, {'nodes': []}, {'models': ['a', 'a']}, {'surprise': 1},
                       {'commands': {'shell': ['sh']}}, {'commands': {'vitals': 'vitals {node}'}},
                       {'fixtures': {'f': {'lane': 'unknown'}}}, {'batches': {'b': {'pairs': []}}},
                       {'hot_celsius': 'hot'}, {'search_health_url': 'ftp://x'}):
            with self.subTest(change=change), self.assertRaises(B.PolicyError):
                B.Config({**copy.deepcopy(TEST_CONFIG), **change}, Path(_CONFIG_DIR.name) / 'bad.json')

    def test_command_placeholders_are_filled_and_a_bad_one_is_a_policy_refusal(self):
        cfg = B.Config({**copy.deepcopy(TEST_CONFIG), 'commands': {'vitals': ['probe', '--node={node}', '{{raw}}'],
                                                                   'cancel_run': ['cancel', '{missing}']}},
                       Path(_CONFIG_DIR.name) / 'placeholders.json')
        self.assertEqual(cfg.argv('vitals', node='node-a'), ['probe', '--node=node-a', '{raw}'])
        self.assertIsNone(cfg.argv('research'))
        with self.assertRaises(B.PolicyError):
            cfg.argv('cancel_run', id='x')

    def test_the_shipped_example_configuration_points_at_real_files_that_check(self):
        from symblic.kernel import language as S
        cfg = B.load_config(B.DEFAULT_CONFIG)
        self.assertTrue(cfg.nodes and cfg.models and cfg.batches)
        for name, fx in cfg.fixtures.items():
            if fx['lane'] == 'research':
                self.assertTrue(fx['expect'] and fx['question'], name)
                continue
            self.assertTrue(Path(fx['path']).exists(), name)
            if fx['lane'] == 'native':
                checked = S.check(Path(fx['path']).read_text())
                self.assertTrue(checked['ok'], (name, checked.get('errors')))
        for batch in cfg.batches:
            for lane, fixture, model, node, _ in B.batch_trials(batch, cfg=cfg):
                B.check_policy(model, node, cfg=cfg)
                self.assertEqual(cfg.fixtures[fixture]['lane'], lane)


class Judges(unittest.TestCase):
    def test_native_pass_needs_done_and_the_exact_expected_output(self):
        ok = B.judge_symblic_report(report(outputs=[{'label': 'rolls left', 'text': '44'}]), {'rolls left': '44'})
        self.assertEqual(ok[0], 'pass')
        wrong = B.judge_symblic_report(report(outputs=[{'label': 'rolls left', 'text': '43'}]), {'rolls left': '44'})
        self.assertEqual(wrong[0], 'fail')
        self.assertIn('expected output "rolls left" = 44, got 43', wrong[1])
        missing = B.judge_symblic_report(report(outputs=[]), {'rolls left': '44'})
        self.assertEqual(missing[0], 'fail')
        by_binding = B.judge_symblic_report(report(outputs=[{'label': '', 'binding': 'change', 'text': '14'}]),
                                            {'change': '14'})
        self.assertEqual(by_binding[0], 'pass')

    def test_failure_reason_is_the_first_failing_check_on_one_line(self):
        error = {'kind': 'check', 'line': 31, 'message': (
            "unit_escapeHtml: no search candidate passed its checks in 2 round(s) of 2: ollama:gemma3:1b: failed "
            "encoded predicate: test_escapeHtml.passed\n1 of 6 examples failed:\n- escapeHtml('a & b timeout')\n"
            "  expected \"a &amp; b timeout\"\n  got      \"a & b timeout\"")}
        outcome, reason, _ = B.judge_symblic_report(report(status='failed', error=error))
        self.assertEqual(outcome, 'fail')       # 'timeout' in an example is not a timeout
        self.assertNotIn('\n', reason)
        self.assertTrue(reason.startswith('line 31: unit_escapeHtml: no search candidate passed'))
        self.assertIn("escapeHtml('a & b timeout')", reason)
        self.assertLessEqual(len(reason), B.REASON_CHARS)

    def test_timeouts_and_refusals_keep_their_names(self):
        cases = [({'kind': 'budget', 'message': 'the total Ollama time budget has no remaining 30-second request slot'}, 'timeout'),
                 ({'kind': 'check', 'message': 'hours: ollama:gemma3:1b@node-a did not answer in time'}, 'timeout'),
                 ({'kind': 'check', 'message': 'ask x: Ollama request time budget exhausted'}, 'timeout'),
                 ({'kind': 'model', 'message': 'launch refused: node-b is fenced for a power change'}, 'refused'),
                 ({'kind': 'version', 'message': 'This folder retains English instructions'}, 'refused'),
                 ({'kind': 'budget', 'message': 'max_calls budget of 12 calls is exhausted'}, 'fail'),
                 ({'kind': 'resource', 'message': 'JavaScript check inconclusive: 5 observation(s) could not complete '
                                                  '(timeout: the whole check ran past 50 s). No candidate verdict; no '
                                                  'repair request was made.'}, 'error')]
        for error, want in cases:
            self.assertEqual(B.classify_error(error)[0], want, error)

    def test_spec_pass_needs_the_whole_file_harness(self):
        program = '# unit 1 of 2\n# unit 2 of 2\n'
        done = report(bindings=[{'name': 'unit_a'}, {'name': 'unit_b'}, {'name': 'test_a'}])
        good = B.harness_verdict(json.dumps({'ok': True, 'cases': 500, 'pass': 500, 'fail': 0, 'errors': 0,
                                             'plain': 8, 'plainOf': 8}), 0)
        outcome, _, checks = B.judge_spec(done, program, good)
        self.assertEqual((outcome, checks['units_accepted'], checks['units_total']), ('pass', 2, 2))
        bad = B.harness_verdict(json.dumps({'ok': True, 'cases': 500, 'pass': 497, 'fail': 3, 'errors': 0, 'plain': 8,
                                            'plainOf': 8, 'sample': [{'seed': 4, 'want': '<p>a</p>', 'got': '<p>b</p>'}]}), 0)
        outcome, reason, _ = B.judge_spec(done, program, bad)
        self.assertEqual(outcome, 'fail')
        self.assertIn('harness 497/500', reason)
        self.assertIn('seed 4', reason)
        plain = B.harness_verdict(json.dumps({'ok': True, 'cases': 500, 'pass': 500, 'fail': 0, 'errors': 0,
                                              'plain': 7, 'plainOf': 8}), 0)
        self.assertEqual(B.judge_spec(done, program, plain)[0], 'fail')
        self.assertEqual(B.judge_spec(done, program, None)[0], 'error')
        crashed = B.harness_verdict('Error: boom', 1)
        self.assertEqual(B.judge_spec(done, program, crashed)[0], 'fail')

    def test_research_answer_must_contain_the_expected_string(self):
        want = 'Highly accurate protein structure prediction with AlphaFold'
        hit = [{'answer': 'It is "HIGHLY accurate protein  structure prediction with AlphaFold".', 'steps': [], 'sources': []}]
        self.assertEqual(B.judge_research(hit, want)[0], 'pass')
        miss = [{'answer': 'AlphaFold predicts protein structures [1].', 'steps': [{}], 'sources': [{}]}]
        outcome, reason, _ = B.judge_research(miss, want)
        self.assertEqual(outcome, 'fail')
        self.assertIn('ANSWER lacks', reason)
        self.assertEqual(B.judge_research([{'error': 'qwen on node-b did not answer in time'}], want)[0], 'timeout')
        self.assertEqual(B.judge_research([{'answer': "I'm sorry, I cannot browse.", 'steps': []}], want)[0], 'refused')
        self.assertEqual(B.judge_research(None, want)[0], 'error')

    def test_delegate_acceptance_and_the_expected_value_both_count(self):
        expect = {'path': ['quote'], 'equals': 'Delivery: Monday\n'}
        self.assertEqual(B.judge_delegate({'accepted': True, 'result': {'quote': 'Delivery: Monday\n'}}, expect)[0], 'pass')
        wrong = B.judge_delegate({'accepted': True, 'result': {'quote': 'Order: 7\n'}}, expect)
        self.assertEqual(wrong[0], 'fail')
        self.assertIn('Order: 7', wrong[1])
        self.assertEqual(B.judge_delegate({'accepted': False, 'error': {'message': 'answer outside the enum'}}, expect)[0], 'fail')
        self.assertEqual(B.judge_delegate({'ok': False, 'errors': [{'message': 'Task file exceeds 512 KiB.'}]}, expect)[0], 'refused')
        self.assertEqual(B.judge_delegate({'accepted': True, 'result': 'complaint'}, {'path': [], 'equals': 'complaint'})[0], 'pass')

    def test_ladder_rows_count_only_the_benchs_own_success(self):
        agg = {'cells': [
            {'family': 'F1', 'rung': 1, 'mode': 'direct', 'assigned': 1, 'passed': 1, 'statuses': {'done': 1}},
            {'family': 'F1', 'rung': 2, 'mode': 'static', 'assigned': 1, 'passed': 0, 'statuses': {'exhausted': 1},
             'grade_statuses': {'failed': 1}},
            {'family': 'F1', 'rung': 3, 'mode': 'decompose_on_failure', 'assigned': 1, 'passed': 0, 'statuses': {'unknown': 1}},
            {'family': 'F1', 'rung': 4, 'mode': 'capability', 'assigned': 1, 'passed': 0, 'statuses': {'blocked': 1}}]}
        rows = B.ladder_rows(agg)
        self.assertEqual([r['outcome'] for r in rows], ['pass', 'fail', 'error', 'refused'])
        self.assertEqual(rows[0]['fixture'], 'ladder-F1/1-direct')
        self.assertEqual(B.ladder_rows({'cells': []}), [])


class Trials(Base):
    def test_every_lane_pins_the_model_to_the_node_and_never_an_excluded_one(self):
        env = FakeEnv()
        for lane, fixture in (('native', 'word-problem'), ('english', 'change'), ('delegate', 'witness-delivery'),
                              ('research', 'doi-alphafold'), ('spec', 'markdown-13')):
            row = self.trial(lane, fixture, env)
            self.assertEqual(row['outcome'], 'pass', (lane, row.get('reason')))
        for call in env.calls:
            argv = [str(a) for a in call['argv']]
            self.assertFalse([a for a in argv if a.endswith('@node-x')], argv)
            if '--node' in argv:
                self.assertNotEqual(argv[argv.index('--node') + 1], 'node-x')
            if call['kind'] == 'run' and str(call['argv'][2]).endswith('build.sym'):
                program = Path(call['argv'][2]).read_text()       # the spec lane pins through the compiled program
                self.assertIn('use by=["ollama:qwen3:4b-instruct@node-b"]', program)
            elif call['kind'] in ('compile', 'run', 'english', 'delegate'):
                self.assertIn('ollama:qwen3:4b-instruct@node-b', call['argv'], call['kind'])
            if call['kind'] == 'research':
                self.assertEqual(call['argv'][call['argv'].index('--node') + 1], 'node-b')
            self.assertTrue(call['env']['PYTHONPATH'].startswith(str(REPO)))
        runs = [c for c in env.calls if c['kind'] == 'run']
        limits = json.loads(runs[0]['argv'][runs[0]['argv'].index('--ollama-limits') + 1])
        self.assertEqual((limits['num_predict'], limits['timeout_seconds']), (2048, 900))

    def test_row_has_the_ledger_fields(self):
        row = self.trial('native', 'word-problem', FakeEnv())
        for key in ('lane', 'fixture', 'model', 'node', 'started', 'ended', 'seconds', 'calls', 'outcome', 'evidence',
                    'reason', 'attempt', 'temp_before'):
            self.assertIn(key, row)
        self.assertEqual((row['calls'], row['placement_ok'], row['call_nodes']), (1, True, ['node-b']))
        stored = self.ledger.rows()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]['id'], row['id'])
        self.assertTrue(Path(row['evidence'], 'lane.cmd').exists())

    def test_a_call_off_the_pinned_node_is_an_error(self):
        env = FakeEnv(lanes={'run': lambda argv, out: (report(outputs=[{'label': 'rolls left', 'text': '44'}]), 0, False,
                                                       [call_row('node-c')])})
        row = self.trial('native', 'word-problem', env)
        self.assertEqual(row['outcome'], 'error')
        self.assertTrue(row['reason'].startswith('placement: calls ran on node-c'))

    def test_outer_cap_is_a_timeout_and_cancels_only_this_trials_runs(self):
        env = FakeEnv(lanes={'run': lambda argv, out: ('', -15, True, [call_row()])})
        start = env.t
        env.runs = [{'id': 'mine', 'node': 'node-b', 'kind': 'ollama', 'model': 'qwen3:4b-instruct', 'started': start + 50},
                    {'id': 'older', 'node': 'node-b', 'kind': 'ollama', 'model': 'qwen3:4b-instruct', 'started': start - 500},
                    {'id': 'other-node', 'node': 'node-a', 'kind': 'ollama', 'model': 'qwen3:4b-instruct', 'started': start + 50},
                    {'id': 'other-model', 'node': 'node-b', 'agent_kind': 'ollama', 'model': 'gemma3:1b', 'started': start + 50}]
        # the gate sees the node busy unless the leftover runs appear only after the trial began
        runs, env.runs = env.runs, []
        original = env.run

        def run_then_leftovers(*args, **kw):
            env.runs = runs
            return original(*args, **kw)
        env.run = run_then_leftovers
        row = self.trial('native', 'word-problem', env)
        self.assertEqual(row['outcome'], 'timeout')
        self.assertEqual(env.cancelled, ['mine'])
        self.assertEqual(row['cancelled_runs'], ['mine'])

    def test_hot_busy_offline_and_unreadable_nodes_are_skipped_without_running(self):
        for temps, runs, want in (({'node-b': 81.0}, [], 'above 80'),
                                  ({'node-b': 40.0}, [{'id': 'other', 'node': 'node-b', 'kind': 'ollama',
                                                       'model': 'gemma3:1b'}], 'busy with another model run'),
                                  ({'node-b': 'offline'}, [], 'offline'),
                                  ({'node-b': None}, [], 'temperature unreadable'),
                                  ({'node-b': 'raise'}, [], 'node status unreadable')):
            env = FakeEnv(temps=temps, runs=runs)
            row = self.trial('native', 'word-problem', env, hot_wait=120, busy_wait=120)
            self.assertEqual(row['outcome'], 'skipped', temps)
            self.assertIn(want, row['reason'])
            self.assertEqual(env.calls, [])
        env = FakeEnv(temps={'node-b': 80.0})
        self.assertEqual(self.trial('native', 'word-problem', env)['outcome'], 'pass')   # skip only ABOVE 80 °C

    def test_without_a_vitals_command_an_unknown_temperature_does_not_block(self):
        env = FakeEnv(temps={'node-b': None}, monitored=False)
        row = self.trial('native', 'word-problem', env)
        self.assertEqual((row['outcome'], row['temp_before']), ('pass', None))

    def test_research_is_skipped_when_no_research_command_is_configured(self):
        cfg = B.Config({**copy.deepcopy(TEST_CONFIG), 'commands': {}}, Path(_CONFIG_DIR.name) / 'no-research.json')
        env = FakeEnv()
        model, node = B.parse_pair('qwen3:4b-instruct@node-b')
        row = B.Trial('research', 'doi-alphafold', model, node, state=self.state, env=env, ledger=self.ledger,
                      batch='t', cfg=cfg).run()
        self.assertEqual(row['outcome'], 'skipped')
        self.assertIn('no research command', row['reason'])
        self.assertEqual(env.calls, [])

    def test_an_unreadable_lane_result_is_an_error_with_the_exit_and_stderr(self):
        env = FakeEnv(lanes={'run': lambda argv, out: ('Traceback (most recent call last):', 1, False, None)})
        original = env.run

        def with_stderr(argv, **kw):
            res = original(argv, **kw)
            Path(kw['stderr_path']).write_text('ValueError: boom\n')
            return res
        env.run = with_stderr
        row = self.trial('native', 'word-problem', env)
        self.assertEqual(row['outcome'], 'error')
        self.assertIn('exit 1; stderr: ValueError: boom', row['reason'])

    def test_research_is_skipped_when_search_is_down(self):
        env = FakeEnv(search=False)
        row = self.trial('research', 'doi-alphafold', env)
        self.assertEqual(row['outcome'], 'skipped')
        self.assertIn('search engine', row['reason'])
        self.assertEqual(env.calls, [])

    def test_research_counts_generations_and_checks_placement(self):
        row = self.trial('research', 'doi-alphafold', FakeEnv())
        self.assertEqual((row['outcome'], row['calls'], row['placement_ok']), ('pass', 2, True))

    def test_spec_runs_nothing_when_the_compiled_program_names_another_applicator(self):
        env = FakeEnv(lanes={'compile': lambda argv, out: ('use by=["ollama:qwen3:4b-instruct"], route=search.\n', 0, False, None)})
        row = self.trial('spec', 'markdown-13', env)
        self.assertEqual(row['outcome'], 'error')
        self.assertIn('not only ollama:qwen3:4b-instruct@node-b', row['reason'])
        self.assertEqual([c['kind'] for c in env.calls], ['compile'])

    def test_spec_compile_refusal_and_failed_unit(self):
        env = FakeEnv(lanes={'compile': lambda argv, out: ('', 1, False, None)})
        self.assertEqual(self.trial('spec', 'markdown-13', env)['outcome'], 'refused')
        error = {'kind': 'check', 'line': 9, 'message': 'unit_a: no search candidate passed its checks in 2 round(s) of 2'}
        env = FakeEnv(lanes={'run': lambda argv, out: (report(status='failed', error=error), 1, False, [call_row()] * 3)})
        row = self.trial('spec', 'markdown-13', env)
        self.assertEqual((row['outcome'], row['calls']), ('fail', 3))
        self.assertIn('unit_a', row['reason'])
        self.assertFalse([c for c in env.calls if c['kind'] == 'harness'])

    def test_retries_are_rows_with_their_own_attempt_and_folder(self):
        env = FakeEnv()
        first = self.trial('native', 'four-plus-four', env)
        second = self.trial('native', 'four-plus-four', env)
        self.assertEqual((first['attempt'], second['attempt']), (1, 2))
        self.assertNotEqual(first['evidence'], second['evidence'])
        self.assertEqual(len(self.ledger.rows()), 2)

    def test_an_interrupted_trials_folder_is_never_reused_and_is_reported(self):
        stale = self.state / 'runs' / 't-native-four-plus-four-qwen3-4b-instruct-node-b-a1'
        stale.mkdir(parents=True)
        (stale / 'intent.json').write_text('{}')
        row = self.trial('native', 'four-plus-four', FakeEnv())
        self.assertTrue(row['evidence'].endswith('-a1-r2'))
        self.assertEqual(B.interrupted(self.ledger.rows(), self.state / 'runs', alive=lambda pid: False),
                         ([stale.name], []))
        self.assertEqual(B.interrupted(self.ledger.rows(), self.state / 'runs', alive=lambda pid: True),
                         ([], [stale.name]))
        intent = json.loads((Path(row['evidence']) / 'intent.json').read_text())
        self.assertEqual(intent['pid'], os.getpid())
        # a batch filter hides other batches' rows but never turns them into interrupted trials
        B.Trial('native', 'four-plus-four', 'qwen3:4b-instruct', 'node-b', state=self.state, env=FakeEnv(),
                ledger=self.ledger, batch='u').run()
        only_u = [r for r in self.ledger.rows() if r['batch'] == 'u']
        text = B.render_report(only_u, self.ledger.path, all_rows=self.ledger.rows(), batches=['u'],
                               alive=lambda pid: False)
        self.assertNotIn('Interrupted', text)
        self.assertNotIn(Path(row['evidence']).name, text)
        self.assertIn(stale.name, B.render_report(self.ledger.rows(), self.ledger.path, alive=lambda pid: False))


class Batch(Base):
    def test_one_trial_per_node_at_a_time_and_the_nodes_in_parallel(self):
        env = FakeEnv(delay=0.05)
        rows = B.run_batch(B.batch_trials('first'), state=self.state, env=env, ledger=self.ledger, batch='b')
        self.assertEqual(len(rows), 10)
        self.assertEqual(env.peak_node, {'node-b': 1, 'node-a': 1})
        self.assertEqual(env.peak, 2)
        self.assertEqual(len(self.ledger.rows()), 10)

    def test_batch_refuses_before_anything_starts(self):
        env = FakeEnv()
        for trials in ([('native', 'word-problem', 'gemma3:1b', 'node-x')],
                       [('native', 'word-problem', 'gemma3:1b', 'node-a'), ('ladder', 'ladder-F1', 'gemma3:1b', 'node-a')],
                       [('native', 'markdown-13', 'gemma3:1b', 'node-a')]):
            with self.assertRaises(B.PolicyError):
                B.run_batch(trials, state=self.state, env=env, ledger=self.ledger, batch='b')
        self.assertEqual((env.calls, self.ledger.rows()), ([], []))

    def test_a_model_missing_on_the_node_is_skipped_not_run(self):
        env = FakeEnv(inventory={'node-a': {'qwen3:4b-instruct'}})
        rows = B.run_batch([('native', 'word-problem', 'gemma3:1b', 'node-a')], state=self.state, env=env,
                           ledger=self.ledger, batch='b')
        self.assertEqual(rows[0]['outcome'], 'skipped')
        self.assertIn('not installed on node-a', rows[0]['reason'])
        self.assertEqual(env.calls, [])


class Report(unittest.TestCase):
    def test_scoreboard_counts_started_trials_and_lists_failures_with_reasons(self):
        rows = [{'lane': 'native', 'lane_no': 2, 'fixture': 'a', 'model': 'gemma3:1b', 'node': 'node-a', 'attempt': 1,
                 'outcome': 'pass', 'calls': 1, 'seconds': 10},
                {'lane': 'native', 'lane_no': 2, 'fixture': 'b', 'model': 'gemma3:1b', 'node': 'node-a', 'attempt': 1,
                 'outcome': 'fail', 'reason': 'expected output "x" = 1, got 2', 'calls': 3, 'seconds': 30,
                 'evidence': '/tmp/e'},
                {'lane': 'native', 'lane_no': 2, 'fixture': 'c', 'model': 'gemma3:1b', 'node': 'node-a', 'attempt': 1,
                 'outcome': 'skipped', 'reason': 'node-a at 85 °C'},
                {'lane': 'spec', 'lane_no': 1, 'fixture': 'm', 'model': 'qwen3:4b-instruct', 'node': 'node-b', 'attempt': 1,
                 'outcome': 'timeout', 'reason': 'the build passed the outer cap', 'calls': 20, 'seconds': 4200},
                {'lane': 'native', 'lane_no': 2, 'fixture': 'k', 'model': 'qwen3:4b-instruct', 'node': 'node-b',
                 'attempt': 1, 'outcome': 'pass', 'calls': 0}]
        board = B.scoreboard(rows)
        self.assertEqual(board[(2, 'native')]['gemma3:1b']['pass'], 1)
        text = B.render_report(rows, '/nonexistent/ledger.jsonl')
        line = next(ln for ln in text.splitlines() if ln.startswith('2 native'))
        self.assertIn('1/2 (f1 s1)', line)
        self.assertIn('0/1 (t1)', next(ln for ln in text.splitlines() if ln.startswith('1 spec')))
        self.assertIn('reason: expected output "x" = 1, got 2', text)
        self.assertIn('evidence: /tmp/e', text)
        self.assertIn('Passes with zero model calls', text)
        self.assertEqual(B.render_report([], '/x'), 'No trials yet in /x.')


class SecondBatch(Base):
    def test_second_batch_runs_exact_then_fine_on_each_node_with_one_sample(self):
        items = B.batch_trials('second')
        self.assertEqual([(t[1], t[2], t[3]) for t in items if t[3] == 'node-a'],
                         [('markdown-exact-37', 'gemma3:1b', 'node-a'), ('markdown-fine-37', 'qwen2.5-coder:3b', 'node-a')])
        self.assertEqual([(t[1], t[2], t[3]) for t in items if t[3] == 'node-b'],
                         [('markdown-exact-37', 'qwen2.5:0.5b', 'node-b'), ('markdown-fine-37', 'granite3.3:2b', 'node-b')])
        for t in items:
            self.assertEqual((t[4]['samples'], t[4]['retries'], t[4]['rounds']), (1, 3, 1))
        with self.assertRaises(B.PolicyError):
            B.batch_trials('second', ['gemma3:1b@node-a'])

    def test_item_settings_reach_the_compiler_and_the_row(self):
        env = FakeEnv()
        model, node = 'gemma3:1b', 'node-a'
        row = B.Trial('spec', 'markdown-exact-37', model, node, state=self.state, env=env, ledger=self.ledger,
                      batch='b2', options={'samples': 1, 'retries': 3, 'rounds': 1, 'total_seconds': 3600},
                      batch_name='second').run()
        compile_argv = next(c['argv'] for c in env.calls if c['kind'] == 'compile')
        for flag, value in (('--samples', '1'), ('--retries', '3'), ('--rounds', '1')):
            self.assertEqual(compile_argv[compile_argv.index(flag) + 1], value)
        self.assertEqual(row['settings'], {'samples': 1, 'retries': 3, 'rounds': 1})
        self.assertEqual((row['batch_name'], row['options']['samples']), ('second', 1))
        self.assertEqual(row['limits'], {'num_predict': 2048, 'timeout_seconds': 900, 'total_timeout_seconds': 3600})
        with self.assertRaises(B.PolicyError):
            B.Trial('spec', 'markdown-exact-37', model, node, state=self.state, env=env, ledger=self.ledger,
                    options={'temperature': 1})

    def test_rows_carry_the_code_hashes_and_flag_a_change_during_the_trial(self):
        row = self.trial('native', 'word-problem', FakeEnv())
        for name in ('symblic/bench/local_beta.py', 'symblic/js/normalize.py', 'symblic/kernel/run.py'):
            self.assertRegex(row['code_sha256'][name], r'^[0-9a-f]{64}$')
        self.assertEqual(row['code_changed_during_trial'], [])
        states = iter([{'symblic/kernel/run.py': 'a', 'symblic/js/normalize.py': 'n'},
                       {'symblic/kernel/run.py': 'b', 'symblic/js/normalize.py': 'n'}])
        original = B.code_hashes
        B.code_hashes = lambda root=None: next(states)
        try:
            row = self.trial('native', 'word-problem', FakeEnv())
        finally:
            B.code_hashes = original
        self.assertEqual(row['code_changed_during_trial'], ['symblic/kernel/run.py'])

    def test_first_failing_example_and_the_unit_detail(self):
        error = ("failed encoded predicate: test_escapeHtml.passed\n3 of 6 examples failed:\n- escapeHtml('a & b')\n"
                 "  expected \"a &amp; b\"\n  got      \"a &amp b\"\n- escapeHtml('<')\n  expected \"&lt;\"\n  got \"<\"")
        self.assertEqual(B.first_failure(error), {'call': "escapeHtml('a & b')", 'expected': '"a &amp; b"',
                                                  'got': '"a &amp b"'})
        self.assertEqual(B.first_failure('failed encoded predicate: t.passed\nThe code does not run: SyntaxError: x'),
                         {'error': 'The code does not run: SyntaxError: x'})
        run = Path(self.tmp.name) / 'run'
        run.mkdir()

        def call(sample, temp, seed, text, stmt='unit_escapeHtml', line=31):
            return {'stmt': stmt, 'line': line, 'sample': sample, 'repair': False, 'ok': True,
                    'reply': {'text': text, 'meta': {'determinism': {'temperature': temp, 'seed': seed}}}}
        long_reply = 'function escapeHtml(s) { return s; }' + ' ' * 300
        calls = [call(0, 0, 7, 'function strong(s) {}', stmt='unit_strong', line=12),
                 call(0, 0, 7, long_reply), call(1000, 0, 7, long_reply), call(2000, 0.6, 2007, 'other'),
                 call(3000, 0.6, 5007, 'last reply')]
        (run / 'calls.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in calls))
        trace = [{'kind': 'ask', 'status': 'ok', 'line': 12, 'kernel': {'js_normalize_assets': {'normalize.py': 'abc'}}},
                 {'kind': 'route-attempt', 'status': 'rejected', 'line': 31, 'ask': {'attempt': {'error': error}}},
                 {'kind': 'ask', 'status': 'failed', 'line': 31}]
        (run / 'trace.jsonl').write_text(''.join(json.dumps(t) + '\n' for t in trace))
        per_unit, failed, assets = B.spec_units(run, {'bindings': [{'name': 'unit_strong'}]})
        unit = next(u for u in per_unit if u['unit'] == 'unit_escapeHtml')
        self.assertEqual((unit['calls'], unit['retries'], unit['resampled_retries'], unit['identical'], unit['accepted']),
                         (4, 3, 2, 1, False))
        self.assertTrue(next(u for u in per_unit if u['unit'] == 'unit_strong')['accepted'])
        self.assertEqual((failed['unit'], failed['calls'], failed['reply_head']), ('unit_escapeHtml', 4, 'last reply'))
        self.assertEqual(failed['first_failing_example']['got'], '"a &amp b"')
        self.assertEqual(assets, {'normalize.py': 'abc'})
        rows = [{'lane': 'spec', 'lane_no': 1, 'fixture': 'markdown-exact-37', 'model': 'gemma3:1b', 'node': 'node-a',
                 'attempt': 1, 'outcome': 'fail', 'reason': 'unit_escapeHtml: ...', 'calls': 5, 'seconds': 60,
                 'checks': {'failed_unit': failed, 'per_unit': per_unit, 'units_accepted': 1, 'units_total': 37}}]
        text = B.render_report(rows, '/nonexistent/ledger.jsonl', alive=lambda pid: False)
        self.assertIn("first failing example (last attempt): escapeHtml('a & b') expected \"a &amp; b\" got \"a &amp b\"", text)
        self.assertIn('reply, first 200 characters: "last reply"', text)
        self.assertIn('retries re-sampled (new temperature or seed): 2 of 3', text)
        self.assertEqual(len(B.spec_units(run, {})[1]['reply_head']), len('last reply'))
        # a build that stopped on an inconclusive js_test line names the unit that line checks
        stop = Path(self.tmp.name) / 'stop'
        stop.mkdir()
        (stop / 'program.sym').write_text('program P.\nask unit_codeBodyLines: Code js "x".\n'
                                          'let test_codeBodyLines = js_test([unit_codeBodyLines], []).\n')
        (stop / 'calls.jsonl').write_text(json.dumps(call(0, 0, 7, 'function codeBodyLines(b) {}',
                                                          stmt='unit_codeBodyLines', line=2)) + '\n')
        (stop / 'trace.jsonl').write_text(json.dumps({'kind': 'ask', 'status': 'ok', 'line': 2}) + '\n')
        inconclusive = {'line': 3, 'kind': 'resource', 'message': 'JavaScript check inconclusive: 5 observation(s) '
                        'could not complete (timeout: the whole check ran past 50 s). No candidate verdict.'}
        _, stopped, _ = B.spec_units(stop, {'error': inconclusive})
        self.assertEqual((stopped['unit'], stopped['line'], stopped['reply_head']),
                         ('unit_codeBodyLines', 3, 'function codeBodyLines(b) {}'))
        self.assertIn('inconclusive', stopped['first_failing_example']['error'])
        calls[-1] = call(3000, 0.6, 5007, long_reply * 2)
        (run / 'calls.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in calls))
        self.assertEqual(len(B.spec_units(run, {})[1]['reply_head']), 200)


class Rejudge(Base):
    def test_a_rejudged_row_replaces_the_old_verdict_and_keeps_it_in_the_ledger(self):
        inconclusive = {'line': 9, 'kind': 'resource', 'message': 'JavaScript check inconclusive: 5 observation(s) '
                        'could not complete (timeout: the whole check ran past 50 s). No candidate verdict.'}
        env = FakeEnv(lanes={'run': lambda argv, out: (report(status='failed', error=inconclusive), 1, False, [call_row()])})
        row = self.trial('native', 'word-problem', env)
        self.assertEqual(row['outcome'], 'error')            # today's classifier already says no verdict
        old = dict(row, outcome='timeout', id=row['id'] + '-old')
        self.ledger.append(old)
        new = self.ledger.append(B.rejudge(old))
        self.assertEqual((new['outcome'], new['supersedes'], new['was']['outcome']), ('error', old['id'], 'timeout'))
        counted = B.effective(self.ledger.rows())
        self.assertNotIn(old['id'], {r['id'] for r in counted})
        self.assertIn(new['id'], {r['id'] for r in counted})
        self.assertEqual(len(self.ledger.rows()), 3)
        self.assertEqual(self.ledger.next_attempt('native', 'word-problem', 'qwen3:4b-instruct', 'node-b'), 3)
        text = B.render_report(self.ledger.rows(), self.ledger.path, alive=lambda pid: False)
        self.assertIn('recorded first as TIMEOUT', text)

    def test_a_finished_run_is_never_rejudged(self):
        row = self.trial('native', 'word-problem', FakeEnv())
        with self.assertRaises(B.PolicyError):
            B.rejudge(row)
        with self.assertRaises(B.PolicyError):
            B.rejudge(dict(row, lane='research'))


class Ladder(Base):
    def plan(self, over):
        pin = Path(self.tmp.name) / 'pins' / 'f1.freeze.json'
        pin.parent.mkdir(parents=True, exist_ok=True)
        return {'plan_file': str(Path(self.tmp.name) / 'plan.json'),
                'commands': {'freeze': [{'argv': [str(B.BIN), 'mica', 'benchmark', '--id', 'x'], 'stdout': str(pin)}],
                             'run': [{'over_hour_bound': over, 'estimated_seconds': 6120, 'runtime_max_seconds': 100,
                                      'shell': 'echo session'}]}}

    def env(self, over):
        agg = {'cells': [{'family': 'F1', 'rung': n, 'mode': m, 'assigned': 1, 'passed': int(n == 1),
                          'statuses': {'done': 1} if n == 1 else {'exhausted': 1}}
                         for n, m in enumerate(('direct', 'static', 'decompose_on_failure', 'capability', 'search', 'mica'), 1)]}
        return FakeEnv(lanes={'ladder-plan': lambda argv, out: (self.plan(over), 0, False, None),
                              'ladder-materialize': lambda argv, out: ('ok', 0, False, None),
                              'freeze': lambda argv, out: ({'status': 'frozen', 'freeze_sha256': 'a' * 64}, 0, False, None),
                              'session': lambda argv, out: ('', 0, False, None),
                              'ladder-aggregate': lambda argv, out: (agg, 0, False, None)})

    def test_over_an_hour_needs_explicit_approval_and_freezes_nothing(self):
        env = self.env(over=True)
        row = self.trial('ladder', 'ladder-F1', env)
        self.assertEqual(row['outcome'], 'refused')
        self.assertIn('approve', row['reason'])
        self.assertEqual([c['kind'] for c in env.calls], ['ladder-plan'])

    def test_approved_session_runs_in_order_and_writes_one_row_per_rung(self):
        env = self.env(over=True)
        rows = self.trial('ladder', 'ladder-F1', env, approve_over_hour=True)
        self.assertEqual([c['kind'] for c in env.calls],
                         ['ladder-plan', 'ladder-materialize', 'freeze', 'session', 'ladder-aggregate'])
        self.assertEqual(len(rows), 6)
        self.assertEqual([r['outcome'] for r in rows], ['pass'] + ['fail'] * 5)
        self.assertEqual(len({r['id'] for r in rows}), 6)
        session = next(c for c in env.calls if c['kind'] == 'session')
        self.assertEqual(session['argv'][:2], ['bash', '-c'])
        plan_call = env.calls[0]['argv']
        self.assertEqual(plan_call[plan_call.index('--budget-seconds') + 1], '900')

    def test_an_existing_pin_is_never_overwritten(self):
        env = self.env(over=False)
        pin = Path(self.plan(False)['commands']['freeze'][0]['stdout'])
        pin.write_text('{"retained": true}')
        row = self.trial('ladder', 'ladder-F1', env)
        self.assertEqual(row['outcome'], 'refused')
        self.assertEqual(json.loads(pin.read_text()), {'retained': True})


if __name__ == '__main__':
    unittest.main()
