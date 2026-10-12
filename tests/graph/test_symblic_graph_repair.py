"""Graph executor repair regressions: stop handling, loaded-code identity, durable writes, ledger capacity, caches.

The labels in the class docstrings (graph-1..5, surface-3/4/9) are the review findings these tests were written
for. Fake applicators and fake effect hosts, temporary folders only; no external process or model, except one
test that runs a private copy of the package in a child interpreter. The host job-runner parts of the same
review (generation fences, worker leases, signals) are in tests/integration/test_symblic_graph_repair_host.py.
"""
from collections import OrderedDict
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import shutil
import textwrap
import threading
import unittest
from unittest.mock import patch

from symblic.graph import planner as G
from symblic.graph import run as R
from symblic.js import check as JS
from tests.graph.test_symblic_graph import graph as pure_graph, node as pure_node
from tests.graph.test_symblic_graph_run import Crash, FakeApps, Host, graph, node

# What Applicators.call returns once its stop is set (symblic.providers.applicators).
STOPPED = {'ok': False, 'error': 'stopped', 'fatal': True}
_REAL_POPEN = subprocess.Popen  # captured before any test forbids external processes


def answering(value, *, first=None):
    """Fake registered Apps: `first(request)` may replace the first reply."""
    count = [0]

    def answer(request):
        count[0] += 1
        if count[0] == 1 and first is not None:
            return first(request)
        return {'ok': True, 'json': {'answer': value}, 'model': request['app']['model'],
                'node': request['app']['node'], 'ms': 0}
    return FakeApps(answer)


class Isolated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'graph'
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)
        no_process = patch('subprocess.Popen', side_effect=AssertionError('no external process in graph tests'))
        popen = no_process.start()
        self.addCleanup(no_process.stop)
        self.addCleanup(lambda: self.assertFalse(popen.called))
        # Fresh bounded caches: counts and cache misses do not depend on test order.
        for owner, name, value in ((R, '_PINS', R._LRU(8192)), (R, '_CHECKS', R._LRU(1024)),
                                   (G, '_VERIFIED', OrderedDict()), (G, '_COMPILED', OrderedDict())):
            cache = patch.object(owner, name, value)
            cache.start()
            self.addCleanup(cache.stop)

    def events(self, folder=None):
        return R._read((folder or self.folder) / 'graph-events.jsonl', lines=True, missing=True)

    def kinds(self, folder=None):
        return [row['kind'] for row in self.events(folder)]

    def journal(self, folder, name):
        return [row['kind'] for row in R._read(folder / 'attempts' / name / 'graph-calls.jsonl', lines=True)]

    def kill_before(self, kind):
        """Simulate a kill (no cleanup) just before a graph event of this kind is appended."""
        real = R._append

        def append(store, name, row):
            if name == 'graph-events.jsonl' and row.get('kind') == kind:
                raise Crash()
            return real(store, name, row)
        return patch.object(R, '_append', side_effect=append)


class StopCausedOutcomes(Isolated):
    """graph-1: a stop-caused outcome is never saved or committed as the node's result."""

    def chain(self, **fields):
        return graph(node('A', **fields),
                     node('B', {'x': {'node': 'A'}}, 'given x: Int.\nlet answer = x + 1.', checks=['answer = x + 1']))

    def test_owner_stop_then_kill_before_cancel_resumes_the_same_attempt(self):
        for retries in (0, 1):
            with self.subTest(retries=retries):
                folder = self.root / f'retries{retries}'
                frozen, stop = self.chain(retries=retries), threading.Event()
                apps = answering(2, first=lambda request: stop.set() or dict(STOPPED))
                with self.kill_before('cancel'), self.assertRaises(Crash):
                    R.GraphRun(frozen, folder, apps, stop=stop).execute()
                attempt = folder / 'attempts' / 'Iter000_A_Attempt01'
                self.assertFalse((attempt / 'graph-result.json').exists())
                self.assertEqual(self.kinds(folder), ['started'])
                self.assertEqual(self.journal(folder, 'Iter000_A_Attempt01'), ['intent', 'interrupted'])
                state = R.GraphRun(frozen, folder, apps).execute()
                self.assertEqual(state['status'], 'succeeded', state)
                self.assertEqual(len(apps.calls), 2)  # the interrupted call is asked again, once
                self.assertEqual(state['reserved_calls'], 6)  # no retry and no new reservation
                self.assertEqual([row['attempt'] for row in state['states']], [1, 1])
                self.assertNotIn('failed', self.kinds(folder))
                self.assertEqual(self.journal(folder, 'Iter000_A_Attempt01'),
                                 ['intent', 'interrupted', 'intent', 'outcome'])
                self.assertEqual(state['states'][0]['result']['provenance'][0]['issued_calls'], 2)
                self.assertEqual(state, G.derive(frozen, self.events(folder)))

    def test_answer_that_arrives_with_the_stop_is_replayed_not_asked_again(self):
        frozen, stop = self.chain(), threading.Event()
        apps = answering(2, first=lambda request: stop.set() or {
            'ok': True, 'json': {'answer': 2}, 'model': request['app']['model'], 'node': request['app']['node'], 'ms': 0})
        with self.kill_before('cancel'), self.assertRaises(Crash):
            R.GraphRun(frozen, self.folder, apps, stop=stop).execute()
        self.assertFalse((self.folder / 'attempts' / 'Iter000_A_Attempt01' / 'graph-result.json').exists())
        state = R.GraphRun(frozen, self.folder, apps).execute()
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 1)
        self.assertEqual(state['reserved_calls'], 6)

    def test_stop_denied_effect_is_not_a_failure_and_is_performed_once_after_resume(self):
        frozen, stop, host = graph(node('A', source='act answer: Int = fixture.write().', effect_risk='write')), \
            threading.Event(), Host()
        with self.kill_before('cancel'), self.assertRaises(Crash):
            R.GraphRun(frozen, self.folder, FakeApps(), stop=stop, effects=host,
                       checkpoint=lambda stage, action: stage == 'started' and stop.set()).execute()
        self.assertEqual(host.calls, [])
        state = R.GraphRun(frozen, self.folder, FakeApps(), effects=host).execute()
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(host.calls), 1)

    def test_completed_cancel_still_closes_the_graph_without_a_node_result(self):
        frozen, stop = self.chain(), threading.Event()
        apps = answering(2, first=lambda request: stop.set() or dict(STOPPED))
        state = R.GraphRun(frozen, self.folder, apps, stop=stop).execute()
        self.assertEqual(state['status'], 'canceled')
        self.assertEqual(self.kinds(), ['started', 'cancel'])
        self.assertEqual(state['states'][0]['status'], 'running')
        self.assertEqual(R.GraphRun(frozen, self.folder, apps).execute(), state)
        self.assertEqual(len(apps.calls), 1)

    def test_interrupted_receipt_cannot_be_turned_into_an_answer(self):
        frozen, stop = self.chain(), threading.Event()
        apps = answering(2, first=lambda request: stop.set() or dict(STOPPED))
        with self.kill_before('cancel'), self.assertRaises(Crash):
            R.GraphRun(frozen, self.folder, apps, stop=stop).execute()
        path = self.folder / 'attempts' / 'Iter000_A_Attempt01' / 'graph-calls.jsonl'
        rows = R._read(path, lines=True)
        rows[1]['reply'] = {'ok': True, 'json': {'answer': 2}, 'model': 'small', 'node': 'node-a', 'ms': 0}
        rows[1] = R._seal({k: v for k, v in rows[1].items() if k != 'sha256'})
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        with self.assertRaises(G.GraphError):
            R.GraphRun(frozen, self.folder, apps).execute()
        self.assertEqual(len(apps.calls), 1)


class LoadedIdentity(Isolated):
    """Pins describe the graph code this process actually loaded, not merely the disk."""

    def test_loaded_graph_modules_must_match_their_pinned_sources(self):
        for owner, field, value in ((G, '_SOURCE_SHA256', '0' * 64), (G, '_SOURCE_LOADED', False),
                                    (R, '_SOURCE_LOADED', False)):
            with self.subTest(module=owner.__name__, field=field), patch.object(owner, field, value):
                with self.assertRaises(G.GraphError) as refused:
                    R.GraphRun(graph(node('A', source='let answer = 1.')), self.root / (owner.__name__ + field),
                               FakeApps()).execute()
                self.assertIn('fresh worker', str(refused.exception))
        self.assertTrue(G._SOURCE_LOADED and R._SOURCE_LOADED)
        self.assertEqual(R.GRAPH_FILES, ('symblic/graph/planner.py', 'symblic/graph/run.py'))

    def test_planner_changed_between_its_import_and_the_runner_import_is_refused(self):
        # A private copy of the whole package (modules, JavaScript assets, library): the kernel identity
        # includes the JavaScript runtime assets even when this graph has no JavaScript statements.
        package = Path(R.__file__).resolve().parents[1]
        tree = self.root / 'tree'
        shutil.copytree(package, tree / 'symblic', ignore=shutil.ignore_patterns('__pycache__'))
        script = textwrap.dedent("""
            import json, sys, tempfile
            from pathlib import Path
            sys.path.insert(0, '.')
            from symblic.js import check as JS
            JS._found['version'] = 'test-no-node'
            from symblic.graph import planner as G
            planner = Path('symblic/graph/planner.py')
            planner.write_text(planner.read_text().replace('MAX_CALLS = 10000', 'MAX_CALLS = 1', 1))
            from symblic.graph import run as R
            route = {'id': 'Local', 'provider': 'fake', 'model': 'small', 'node': 'node-a', 'local': True}
            def node(name, inputs, source):
                return {'id': name, 'inputs': inputs, 'source': source, 'contract': 'c',
                        'output_binding': 'answer', 'output_schema': {'type': 'integer'},
                        'checks': ['answer >= 0'], 'join': 'require_all', 'effect_risk': 'none',
                        'retries': 0, 'call_limit': 1, 'max_calls': 1, 'max_iterations': 1,
                        'allowed': {'routes': ['Local'], 'providers': ['fake'], 'models': ['small'],
                                    'nodes': ['node-a'], 'local_only': True}}
            frozen = G.freeze_graph({'id': 'Graph', 'iterations': 1, 'max_calls': 2, 'nodes': [
                node('A', {}, 'let answer = 1.'), node('B', {'x': {'node': 'A'}}, 'given x: Int.\\nlet answer = x + 1.')]},
                {'version': 1, 'routes': [route], 'order': ['Local']})
            class Apps:
                def call(self, request):
                    raise AssertionError('no dispatch')
            try:
                state = R.GraphRun(frozen, Path(tempfile.mkdtemp()) / 'graph', Apps()).execute()
                print(json.dumps({'status': state['status'], 'reserved_calls': state['reserved_calls']}))
            except G.GraphError as error:
                print(json.dumps({'error': str(error)}))
        """)
        environment = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
        environment.update(PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(self.root))
        with patch('subprocess.Popen', _REAL_POPEN):  # one local interpreter on a private copy
            finished = subprocess.run([sys.executable, '-c', script], cwd=tree, env=environment,
                                      capture_output=True, text=True, timeout=180)
        self.assertEqual(finished.returncode, 0, finished.stderr[-2000:])
        outcome = json.loads(finished.stdout.strip().splitlines()[-1])
        self.assertIn('changed after process import', outcome.get('error', ''), outcome)


class DurableWrites(Isolated):
    """graph-4 and surface-9: fsync before rename, temps never block resume, private folders."""

    def test_temp_is_fsynced_before_rename_and_the_folder_after(self):
        log, real_fsync, real_replace = [], os.fsync, os.replace

        def fsync(descriptor):
            log.append(('fsync', 'folder' if stat.S_ISDIR(os.fstat(descriptor).st_mode) else 'file'))
            return real_fsync(descriptor)

        def replace(source, target):
            log.append(('replace', Path(target).name))
            return real_replace(source, target)
        with patch.object(R.os, 'fsync', fsync), patch.object(R.os, 'replace', replace):
            R._write_json(self.root, 'pins.json', {'pins': 1})
            state = R.GraphRun(graph(node('A')), self.folder, FakeApps()).execute()
        self.assertEqual(log[:3], [('fsync', 'file'), ('replace', 'pins.json'), ('fsync', 'folder')])
        self.assertEqual(state['status'], 'succeeded')
        for name in ('graph-pins.json', 'attempt-pins.json', 'graph-result.json'):
            index = log.index(('replace', name))
            self.assertEqual((log[index - 1], log[index + 1]), (('fsync', 'file'), ('fsync', 'folder')), name)

    def kill_during(self, name):
        real = R._write_file

        def write(folder, target, raw):
            if target == name:
                (Path(folder) / f'.{target}.4242.0123456789abcdef.tmp').write_bytes(raw[:7])
                raise Crash()
            return real(folder, target, raw)
        return patch.object(R, '_write_file', side_effect=write)

    def test_kill_during_first_pins_writes_never_blocks_resume(self):
        for name in ('graph-pins.json', 'attempt-pins.json'):
            with self.subTest(name=name):
                folder, frozen, apps = self.root / name, graph(node('A')), FakeApps()
                with self.kill_during(name), self.assertRaises(Crash):
                    R.GraphRun(frozen, folder, apps).execute()
                self.assertEqual(apps.calls, [])
                self.assertTrue(any(path.name.endswith('.tmp') for path in folder.rglob('*')))
                state = R.GraphRun(frozen, folder, apps).execute()
                self.assertEqual(state['status'], 'succeeded', state)
                self.assertEqual(len(apps.calls), 1)
                self.assertEqual([path for path in folder.rglob('*') if path.name.endswith('.tmp')], [])

    def test_created_directories_are_private_under_a_permissive_umask(self):
        target = self.root / 'deep' / 'graph'
        previous = os.umask(0o002)
        try:
            state = R.GraphRun(graph(node('A'), node('B', {'x': {'node': 'A'}}, 'given x: Int.\nlet answer = x + 1.')),
                               target, FakeApps()).execute()
        finally:
            os.umask(previous)
        self.assertEqual(state['status'], 'succeeded', state)
        directories = [self.root / 'deep', target] + [path for path in target.rglob('*') if path.is_dir()]
        self.assertGreaterEqual(len(directories), 7)
        for path in directories:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700, path)
        for path in target.rglob('*.json'):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path)


class LedgerCapacity(Isolated):
    """surface-4 and graph-5: admitted graphs can be recorded; capacity closes before dispatch."""

    def replayed(self, frozen, executions, value):
        replay, rows = G.Replay(frozen), []
        for index in range(executions):
            action = replay.next_action()
            fields = {key: action[key] for key in ('node', 'iteration', 'attempt')}
            for kind, extra in (('started', {'route': action['route'], 'inputs_hash': G.digest(action['inputs'])}),
                                ('succeeded', {'result': G.envelope(value, 'supported')})):
                row = replay.event(kind, id=f'Event{len(rows)}', **fields, **extra)
                replay.apply(row)
                rows.append(row)
        return replay, rows

    def test_ledger_past_the_former_whole_ledger_snapshot_limit_still_derives(self):
        frozen = pure_graph(*[pure_node(f'N{i:03d}') for i in range(128)], max_calls=128)
        replay, rows = self.replayed(frozen, 128, list(range(400)))
        with self.assertRaises(G.GraphError):
            G.snapshot(rows)  # the former derive refused any ledger beyond one snapshot
        state = G.derive(frozen, rows)
        self.assertEqual(state['status'], 'succeeded')
        self.assertEqual(state, replay.state())

    def test_admission_refuses_worst_cases_the_event_ledger_cannot_record(self):
        many = [pure_node(f'N{i:03d}', retries=1, max_iterations=32) for i in range(128)]
        with self.assertRaises(G.GraphError) as refused:
            pure_graph(*many, iterations=32, max_calls=10000)
        self.assertIn('ledger events', str(refused.exception))
        frozen = pure_graph(*[pure_node(f'N{i:03d}', max_iterations=32) for i in range(128)],
                            iterations=32, max_calls=10000)
        self.assertEqual(G.worst_case_attempts(frozen['graph']), 4096)
        capped = pure_graph(*[pure_node(f'N{i:03d}', retries=8, max_iterations=32) for i in range(128)],
                            iterations=32, max_calls=4000)
        self.assertEqual(G.worst_case_attempts(capped['graph']), 4000)
        self.assertEqual(G.worst_case_attempts({'max_calls': 7, 'iterations': 1, 'nodes': [
            {'call_limit': 3, 'retries': 8, 'max_calls': 100}, {'call_limit': 1, 'retries': 1, 'max_calls': 1}]}), 3)

    def test_runtime_closes_with_capacity_before_dispatch_when_a_completion_would_not_fit(self):
        nodes = [node(f'N{i}') for i in range(5)]
        probe = self.root / 'probe'
        R.GraphRun(graph(nodes[0]), probe, FakeApps()).execute()
        per_attempt = (probe / 'graph-events.jsonl').stat().st_size
        frozen, apps = graph(*nodes), FakeApps()
        limit = R.ROW_RESERVE + R.CLOSING_RESERVE + 2 * per_attempt + per_attempt // 2
        with patch.object(R, 'LEDGER_FILE_BYTES', limit):
            state = R.GraphRun(frozen, self.folder, apps).execute()
            self.assertEqual(state['status'], 'unresolved')
            self.assertEqual(len(apps.calls), 3)
            self.assertEqual(self.kinds()[-1], 'capacity')
            exhausted = [row for row in state['states'] if row['status'] == 'exhausted']
            self.assertEqual(len(exhausted), 2)
            self.assertTrue(all(row['error'] == G.CAPACITY_ERROR for row in exhausted))
            self.assertEqual(R.GraphRun(frozen, self.folder, apps).execute(), state)
        self.assertEqual(len(apps.calls), 3)
        self.assertEqual(state, G.derive(frozen, self.events()))
        self.assertLessEqual((self.folder / 'graph-events.jsonl').stat().st_size, limit)

    def test_completion_row_beyond_the_planner_row_limit_is_recorded_as_failure(self):
        runner = R.GraphRun(graph(node('A', source='let answer = 2.')), self.folder, FakeApps())
        fields = {'node': 'A', 'iteration': 0, 'attempt': 1}
        empty = len(G._encode(G.envelope('', 'supported')))
        large = {'kind': 'succeeded', 'result': G.envelope('x' * (G.MAX_BYTES - empty - 8), 'supported')}
        refused = runner._recordable(large, fields)
        self.assertEqual((refused['kind'], refused['error'], refused['retryable']),
                         ('failed', 'node result exceeds the graph ledger row limit', False))
        small = {'kind': 'succeeded', 'result': G.envelope(2, 'supported')}
        self.assertIs(runner._recordable(small, fields), small)

    def test_attempt_folders_are_bounded_individually_not_by_one_tree_cap(self):
        nodes = [node('N00', source='let answer = 1.')]
        nodes += [node(f'N{i:02d}', {'x': {'node': f'N{i - 1:02d}'}}, 'given x: Int.\nlet answer = x + 1.')
                  for i in range(1, 11)]
        frozen = graph(*nodes)
        state = R.GraphRun(frozen, self.folder, FakeApps()).execute()
        self.assertEqual(state['status'], 'succeeded', state)
        attempts = sorted((self.folder / 'attempts').iterdir())
        for attempt in attempts:
            for index in range(950):
                (attempt / 'artifacts' / f'pad{index}').touch()
        self.assertGreater(sum(1 for _ in self.folder.rglob('*')), 10000)  # the former global cap
        self.assertEqual(R.GraphRun(frozen, self.folder, FakeApps()).execute(), state)
        for index in range(R.ATTEMPT_TREE_LIMIT):
            (attempts[0] / 'artifacts' / f'extra{index}').touch()
        with self.assertRaises(G.GraphError) as refused:
            R.GraphRun(frozen, self.folder, FakeApps()).execute()
        self.assertIn('entry limit', str(refused.exception))

    def test_call_journal_stays_readable_when_a_reply_or_intent_would_not_fit(self):
        apps = FakeApps(lambda request: {'ok': True, 'json': {'answer': 'x' * 500_000},
                                         'model': request['app']['model'], 'node': request['app']['node'], 'ms': 0})
        with patch.object(R, 'MAX_FILE_BYTES', 400_000):
            state = R.GraphRun(graph(node('A')), self.folder, apps).execute()
            self.assertEqual(state['states'][0]['status'], 'failed', state)
            self.assertIn('journal limit', state['states'][0]['error'])
            self.assertEqual(R.GraphRun(graph(node('A')), self.folder, apps).execute(), state)
        self.assertEqual(len(apps.calls), 1)
        other, apps = self.root / 'full', FakeApps()
        with patch.object(R, 'JOURNAL_RESERVE', R.MAX_FILE_BYTES):
            state = R.GraphRun(graph(node('A')), other, apps).execute()
        self.assertEqual(apps.calls, [])
        self.assertIn('journal is full', state['states'][0]['error'])


class NoRepeatedCompilation(Isolated):
    """surface-3: frozen graphs are verified once per identity; list and poll stay cheap."""

    def count(self, owner, name):
        calls, real = [], getattr(owner, name)

        def counted(*args, **kwargs):
            calls.append(name)
            return real(*args, **kwargs)
        patcher = patch.object(owner, name, side_effect=counted)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_derive_verifies_each_frozen_identity_once(self):
        frozen = graph(*[node(f'N{i}', source='let answer = 2.') for i in range(4)])
        G._VERIFIED.clear()
        refreezes = self.count(G, '_freeze')
        for _ in range(5):
            G.derive(frozen, [])
        self.assertEqual(len(refreezes), 1)
        changed = json.loads(json.dumps(frozen))
        changed['graph']['nodes'][0]['source'] = 'let answer = 3.'
        with self.assertRaises(G.GraphError):
            G.derive(changed, [])  # a different identity is verified again, and refused

    def test_compile_template_is_reused_but_bound_inputs_stay_exact(self):
        n = node('A', {'x': {'node': 'A', 'delay': 1, 'seed': G.envelope(0, 'supported')}},
                 'given x: Int.\nlet answer = x + 1.')
        compiles = self.count(G, '_compile')
        first, second = G.compile_node(n, {'x': 1}), G.compile_node(n, {'x': 2})
        self.assertEqual(len(compiles), 1)
        self.assertEqual((first['inputs'], second['inputs']), ({'x': 1}, {'x': 2}))
        self.assertEqual(second['inputs_hash'], G.digest({'x': 2}))
        self.assertEqual({k: v for k, v in first.items() if not k.startswith('inputs')},
                         {k: v for k, v in second.items() if not k.startswith('inputs')})
        with self.assertRaises(G.GraphError):
            G.compile_node(n, {'y': 1})


if __name__ == '__main__':
    unittest.main()
