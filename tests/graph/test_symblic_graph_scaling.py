"""Graph performance scaling: bounded work per ledger row and per start.

Event folding is linear in ledger rows at a fixed graph width. Each start
rescans the open iteration, so a single wide iteration costs O(width^2) node
evaluations; MAX_NODES (128) bounds that width. Pure planner ledgers and fake
Apps in temporary folders only. Bounds are operation counts plus one generous
wall-clock ratio, so a busy machine cannot fail them while the reviewed
regressions (re-freezing every node and replaying the whole ledger per event,
surface-3/graph-5) do.
"""
from collections import OrderedDict
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from symblic.graph import planner as G
from symblic.graph import run as R
from symblic.js import check as JS
from tests.graph.test_symblic_graph import graph as pure_graph, node as pure_node
from tests.graph.test_symblic_graph_run import FakeApps, graph, node


class Scaling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)
        no_process = patch('subprocess.Popen', side_effect=AssertionError('no external process in graph tests'))
        no_process.start()
        self.addCleanup(no_process.stop)
        for owner, name, value in ((R, '_PINS', R._LRU(8192)), (R, '_CHECKS', R._LRU(1024)),
                                   (G, '_VERIFIED', OrderedDict()), (G, '_COMPILED', OrderedDict())):
            cache = patch.object(owner, name, value)
            cache.start()
            self.addCleanup(cache.stop)

    def counted(self, owner, name):
        calls, real = [], getattr(owner, name)

        def count(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)
        patcher = patch.object(owner, name, side_effect=count, autospec=True) if isinstance(owner, type) else \
            patch.object(owner, name, side_effect=count)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def ledger(self, iterations, width=64):
        frozen = pure_graph(*[pure_node(f'N{i:03d}', max_iterations=32) for i in range(width)],
                            iterations=iterations, max_calls=width * iterations) if iterations > 1 else \
            pure_graph(*[pure_node(f'N{i:03d}') for i in range(width)], max_calls=width)
        replay, rows = G.Replay(frozen), []
        for _ in range(width * iterations):
            action = replay.next_action()
            fields = {key: action[key] for key in ('node', 'iteration', 'attempt')}
            for kind, extra in (('started', {'route': action['route'], 'inputs_hash': G.digest(action['inputs'])}),
                                ('succeeded', {'result': G.envelope(1, 'supported')})):
                row = replay.event(kind, id=f'Event{len(rows)}', **fields, **extra)
                replay.apply(row)
                rows.append(row)
        return frozen, rows

    def test_replay_work_is_linear_in_ledger_rows(self):
        plans = self.counted(G.Replay, '_plan')
        elapsed = {}
        for iterations in (2, 16):
            frozen, rows = self.ledger(iterations)
            timings = []
            for _ in range(3):
                plans.clear()
                started = time.perf_counter()
                state = G.derive(frozen, rows)
                timings.append(time.perf_counter() - started)
                self.assertEqual(state['status'], 'succeeded')
                # One planning pass per start (no blocking here) plus the final report.
                self.assertLessEqual(len(plans), len(rows) // 2 + 2)
            elapsed[iterations] = min(timings)
        # Eight times the rows: linear replay takes about eight times as long; the
        # former re-freeze plus full rescan per row grew with the square.
        self.assertLess(elapsed[16], 32 * max(elapsed[2], 0.005), elapsed)

    def test_planning_work_per_start_is_bounded_by_graph_width(self):
        evaluations = self.counted(G.Replay, '_inputs_for')
        measured = {}
        for width in (16, 32, 64):
            frozen = pure_graph(*[pure_node(f'N{i:03d}') for i in range(width)], max_calls=width)
            _, rows = self.ledger(1, width)
            evaluations.clear()
            self.assertEqual(G.derive(frozen, rows)['status'], 'succeeded')
            starts = len(rows) // 2
            # One evaluation per pending node in the open iteration per start, plus the report.
            self.assertLessEqual(len(evaluations), (starts + 2) * width)
            measured[width] = len(evaluations)
        # Quadratic in width for one wide iteration (documented, bounded by MAX_NODES);
        # a ledger rescan per start would add a factor of the ledger length.
        self.assertLessEqual(measured[64], 20 * measured[16], measured)

    def test_execution_and_resume_bookkeeping_is_linear_in_chain_length(self):
        refreezes = self.counted(G, '_freeze')
        compiles = self.counted(G, '_compile')
        builds = self.counted(R.X, 'build')
        applies = self.counted(G.Replay, 'apply')
        for size in (4, 16):
            nodes = [node('N00', source='let answer = 1.')]
            nodes += [node(f'N{i:02d}', {'x': {'node': f'N{i - 1:02d}'}}, 'given x: Int.\nlet answer = x + 1.')
                      for i in range(1, size)]
            frozen = graph(*nodes, max_calls=3 * size)
            folder = Path(self.tmp.name) / str(size)
            # Identical nodes share templates across graphs; start each size cold.
            G._COMPILED.clear()
            R._PINS.items.clear()
            for counter in (refreezes, compiles, builds, applies):
                counter.clear()
            state = R.GraphRun(frozen, folder, FakeApps()).execute()
            self.assertEqual(state['status'], 'succeeded', state)
            rows = 2 * size
            self.assertEqual(len(refreezes), 0)  # verified once, when frozen
            self.assertEqual(len(compiles), size)  # one template per node; attempts bind inputs
            self.assertLessEqual(len(builds), 2 * size)  # admission and attempt pins per node
            self.assertEqual(len(applies), 2 * rows)  # one validation and one fold per row
            for counter in (refreezes, compiles, builds, applies):
                counter.clear()
            self.assertEqual(R.GraphRun(frozen, folder, FakeApps()).execute(), state)
            self.assertEqual((len(refreezes), len(compiles), len(builds)), (0, 0, 0))
            self.assertEqual(len(applies), rows)  # resume replays the ledger once


if __name__ == '__main__':
    unittest.main()
