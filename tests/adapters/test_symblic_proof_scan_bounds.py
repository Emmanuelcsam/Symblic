"""Deterministic frontier bounds for aliased adversarial preflight structures."""
import unittest
from unittest.mock import patch

from symblic.adapters import proof as P
from symblic.adapters import proof_steps as W


class ScannerBounds(unittest.TestCase):
    def scan(self, module, value, tick, stats):
        if module is P:
            return P._scan(value, tick, _stats=stats)
        return W._scan(value, lambda amount: [tick() for _ in range(amount)], _stats=stats)

    def test_broad_aliased_chain_uses_depth_not_width_times_depth_frontier(self):
        value = ['atom', 'A']
        for _ in range(18):
            # Reversed traversal enters the shared child immediately; old scans
            # eagerly allocated 256 pending siblings per level before rejecting.
            value = [value] * 256
        for module in (P, W):
            stats, ticks = {}, []
            with (patch.object(module, 'MAX_NODES', 256), patch.object(module, 'MAX_DEPTH', 16),
                  self.assertRaisesRegex(P.ProofError, 'depth_limit')):
                self.scan(module, value, lambda ticks=ticks: ticks.append(1), stats)
            self.assertLessEqual(stats['max_frontier'], 18)
            self.assertLessEqual(len(ticks), 18)

    def test_host_budget_stops_before_allocating_wide_pending_work(self):
        value = [[['atom', 'A']] * 256] * 256
        class StopBudget(Exception):
            pass
        for module in (P, W):
            ticks, stats = [], {}
            def tick(ticks=ticks):
                ticks.append(1)
                if len(ticks) == 3:
                    raise StopBudget()
            with self.assertRaises(StopBudget):
                self.scan(module, value, tick, stats)
            self.assertEqual(len(ticks), 3)
            self.assertLessEqual(stats['max_frontier'], 3)

    def test_shared_subtrees_are_still_charged_per_occurrence_and_cycles_rejected(self):
        leaf = ['atom', 'A']
        value = [leaf] * 10
        for module in (P, W):
            ticks, stats = [], {}
            nodes = self.scan(module, value, lambda ticks=ticks: ticks.append(1), stats)
            self.assertEqual(nodes, 31)
            self.assertEqual(len(ticks), 31)
            self.assertEqual(stats['max_frontier'], 3)
            cycle = []
            cycle.append(cycle)
            with self.assertRaisesRegex(P.ProofError, 'cycle'):
                self.scan(module, cycle, lambda: None, {})


if __name__ == '__main__':
    unittest.main()
