"""The preregistered contract pilot (tools/scripts/symblic_contract_pilot.py): isolated stores and injected fake
applicators only, so it runs without any model or host."""
import importlib.util
import json
import tempfile
import threading
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

_SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'scripts' / 'symblic_contract_pilot.py'
_SPEC = importlib.util.spec_from_file_location('symblic_contract_pilot', _SCRIPT)
P = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(P)


class FakeApps:
    def __init__(self, tasks, *, small_wrong=False, fail=False):
        self.tasks = tasks
        self.small_wrong = small_wrong
        self.fail = fail
        self.requests = []
        self.cancelled = False

    def call(self, req):
        self.requests.append(req)
        if self.fail:
            return {'ok': False, 'error': 'synthetic outage', 'fatal': True}
        task = next(item for item in self.tasks if item['question'] in req['prompt'])
        expected = P.reference(task)
        value = float(Fraction(expected['value']))
        if self.small_wrong and req['app']['engine'] == 'ollama':
            value += 1
        return {'ok': True, 'json': {'answer': {'choice': expected['choice'], 'value': value}},
                'node': 'fake-node', 'model': req['app']['model']}

    def cancel_all(self):
        self.cancelled = True


class Pilot(unittest.TestCase):
    def setUp(self):
        # Other live developers can edit files during these fake-only checks.
        # Runtime-change rejection is tested separately with its own replacement.
        frozen = P.IMPORTED_FILES
        context = patch.object(P, 'file_hashes', return_value=frozen)
        context.start()
        self.addCleanup(context.stop)

    def test_seed_freezes_distinct_held_out_instances_and_independent_reference(self):
        a = P.items(41)
        self.assertEqual(a, P.items(41))
        self.assertNotEqual(a, P.items(42))
        self.assertEqual({t['family'] for t in a}, {'basis', 'unit', 'scope'})
        with patch.object(P.S.Kernel, 'eval', side_effect=AssertionError('reference touched Symblic')):
            self.assertEqual([P.reference(t) for t in a], [t['expected'] for t in a])
        # Independently generated scalar answers must satisfy the encoded contract.
        for item in a:
            env = P.S.Env()
            env.vars['answer'] = P.S.Binding('answer', {'choice': item['expected']['choice'],
                                                       'value': Fraction(item['expected']['value'])})
            parser = P.S.Parser(P.S.tokenize(item['predicate']), 1)
            expr = parser.expr()
            parser.finish()
            self.assertTrue(P.S.Kernel(env).eval(expr), item)

    def test_common_scorer_rejects_hedges_bool_number_and_extra_fields(self):
        self.assertEqual(P.normalize('{"choice":"seconds","value":"3/8"}'),
                         P.normalize({'answer': {'choice': 'seconds', 'value': .375}}))
        for value in [True, '2 or 3', float('nan')]:
            with self.assertRaises(ValueError):
                P.normalize({'choice': 'seconds', 'value': value})
        with self.assertRaises(ValueError):
            P.normalize({'choice': 'all', 'value': 1, 'other': 2})

    def test_preparation_calls_no_models_and_is_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            plan = P.prepare(td, seed=8)
            self.assertEqual(len(plan['cells']), 18)
            self.assertEqual(plan['max_total_calls'], 36)
            self.assertEqual(len(P.Ledger(td).rows()), 18)
            self.assertTrue(all(r['event'] == 'assigned' for r in P.Ledger(td).rows()))
            self.assertEqual(P.load_plan(td), plan)
            self.assertEqual(len(list((Path(td) / 'source_snapshot').rglob('*.py'))), len(P.SOURCE_FILES))
            with self.assertRaises(FileExistsError):
                P.prepare(td)
            altered = json.loads((Path(td) / 'plan.json').read_text())
            altered['seed'] += 1
            (Path(td) / 'plan.json').write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                P.load_plan(td)

    def test_changed_runtime_cannot_silently_reuse_results(self):
        with tempfile.TemporaryDirectory() as td:
            P.prepare(td)
            with (patch.object(P, 'file_hashes', return_value={'changed': 'source'}),
                  self.assertRaisesRegex(ValueError, 'changed')):
                P.execute(td, FakeApps([]))

    def test_exact_success_uses_one_call_each_and_every_assignment_survives(self):
        with tempfile.TemporaryDirectory() as td:
            plan = P.prepare(td, seed=9)
            backend = FakeApps(plan['items'])
            summary = P.execute(td, backend)
            self.assertEqual(summary['finished'], 18)
            self.assertEqual(summary['calls'], 18)
            for arm in summary['arms'].values():
                self.assertEqual(arm['first_pass_correct'], 6, summary)
                self.assertEqual(arm['final_correct'], 6, summary)
                self.assertEqual(arm['false_acceptance'], {'count': 0, 'assigned': 6})
                self.assertEqual(arm['actual_placements'][0]['node'], 'fake-node')
                self.assertIsInstance(arm['call_started_at_utc'], str)
                self.assertIsInstance(arm['call_finished_at_utc'], str)
            self.assertTrue(backend.cancelled)
            with self.assertRaisesRegex(ValueError, 'already began'):
                P.execute(td, backend)

    def test_checked_fallback_is_separate_from_small_model_first_pass(self):
        with tempfile.TemporaryDirectory() as td:
            plan = P.prepare(td, seed=10)
            backend = FakeApps(plan['items'], small_wrong=True)
            summary = P.execute(td, backend)
            checked = summary['arms']['checked_escalation']
            self.assertEqual(checked['first_pass_correct'], 0)
            self.assertEqual(checked['final_correct'], 6, summary)
            self.assertEqual(checked['calls'], 12)
            self.assertEqual(summary['calls'], 24)
            for arm in ('natural', 'typed'):
                self.assertEqual(summary['arms'][arm]['final_correct'], 0)
                self.assertEqual(summary['arms'][arm]['false_acceptance'], {'count': 6, 'assigned': 6})
            for req in backend.requests:
                if req['app']['engine'] == 'claude':
                    self.assertNotIn('CHECK REJECTED', req['prompt'])
                    self.assertNotIn('failed encoded predicate', req['prompt'])
                    self.assertNotIn('ensure ', req['prompt'])

    def test_outages_remain_in_all_assigned_denominators(self):
        with tempfile.TemporaryDirectory() as td:
            plan = P.prepare(td, seed=11)
            summary = P.execute(td, FakeApps(plan['items'], fail=True))
            self.assertEqual(summary['assigned'], 18)
            self.assertEqual(summary['finished'], 18)
            self.assertLessEqual(summary['calls'], 36)
            self.assertEqual(sum(a['final_correct'] for a in summary['arms'].values()), 0)

    def test_interrupted_dispatch_is_uncertain_and_never_redispatched(self):
        class Interrupted:
            def call(self, req):
                raise KeyboardInterrupt()

            def cancel_all(self):
                pass

        with tempfile.TemporaryDirectory() as td:
            plan = P.prepare(td, seed=12)
            with self.assertRaises(KeyboardInterrupt):
                P.execute(td, Interrupted())
            summary = P.summarize(plan, P.Ledger(td).rows())
            self.assertEqual(summary['finished'], 18)
            self.assertEqual(len(summary['unknown_after_interruption']), 1)
            self.assertEqual(summary['calls'], 1)
            with self.assertRaisesRegex(ValueError, 'already began'):
                P.execute(td, Interrupted())

    def test_partial_assignment_ledger_fails_before_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            plan = P.prepare(td)
            path = Path(td) / 'ledger.jsonl'
            path.write_text('\n'.join(path.read_text().splitlines()[:-1]) + '\n')
            backend = FakeApps(plan['items'])
            with self.assertRaisesRegex(ValueError, 'assignment ledger'):
                P.execute(td, backend)
            self.assertEqual(backend.requests, [])

    def test_call_cap_and_length_limits_do_not_dispatch_extra_work(self):
        with tempfile.TemporaryDirectory() as td:
            fake = FakeApps([], fail=True)
            apps = P.RecordedApps(fake, P.Ledger(td), {'id': 'test'}, threading.Event())
            self.assertTrue(apps.call({'system': 'x' * (P.MAX_PROMPT_CHARS + 1)})['fatal'])
            self.assertEqual(fake.requests, [])
            for _ in range(5):
                apps.call({'system': '', 'prompt': ''})
            self.assertEqual(len(fake.requests), 2)
            self.assertEqual(apps.calls, 2)

    def test_unsafe_or_nonlocal_primary_lane_is_rejected(self):
        for model in ('chatgpt', 'ollama:llama3.2:1b@host', 'ollama:llama3.2:1b@node-h', 'ollama:llama3.2:1b@workstation'):
            with self.assertRaises(ValueError):
                P.build_plan(models=(model,))
        with self.assertRaises(ValueError):
            P.build_plan(fallback='gemini')


if __name__ == '__main__':
    unittest.main()
