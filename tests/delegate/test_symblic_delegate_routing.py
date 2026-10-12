"""Bounded local ladders, shared repairs, exact API policy receipts; fake calls only."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.delegate import contracts as D
from symblic.delegate import run as R
from symblic.kernel import execution_pins as X
from symblic.js import check as JS
from symblic.kernel.run import Run

TINY, SMALL, MID = R.LOCAL_LADDER
TRANSFORM = {'template': 'typed_transform', 'calls': 3, 'params': {
    'instruction': 'Return the two amounts as integers.', 'data': 'first 1, second 2',
    'output_schema': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 2, 'maxItems': 2},
    'checks': [{'op': 'sum_equals', 'path': [], 'expected': 3}]}}
CLASSIFY = {'template': 'enum_classification', 'params': {
    'instruction': 'Choose the color of the item.', 'data': 'a red apple',
    'categories': {'red': 'red items', 'blue': 'blue items'}}}
ARITHMETIC = {'template': 'exact_arithmetic', 'params': {
    'operation': 'add', 'left': {'numerator': 1, 'denominator': 3}, 'right': {'numerator': 1, 'denominator': 6}}}
INCREMENTAL = {'template': 'proof', 'params': {
    'premises': 'p: "A"', 'goal': '"A"', 'certificate_format': 'incremental', 'step_limit': 2}}


def ok(value):
    return {'ok': True, 'json': {'answer': value}, 'node': 'isolated'}


class Provider:
    def __init__(self, script):
        self.script = {label: list(replies) for label, replies in script.items()}
        self.requests = []
        self.cancelled = 0

    def call(self, request):
        label = request['app']['spec']
        self.requests.append(label)
        if not self.script.get(label):
            raise AssertionError('unexpected fake dispatch: ' + label)
        return self.script[label].pop(0)

    def cancel_all(self):
        self.cancelled += 1


class LadderPolicy(unittest.TestCase):
    def setUp(self):
        self.patch = patch.object(JS, 'node_version', return_value='test-no-node')
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_observed_installed_order_and_bound_policy(self):
        self.assertEqual(R.LOCAL_LADDER, ('ollama:llama3.2:1b', 'ollama:granite3.3:2b', 'ollama:qwen3:4b-instruct'))
        task = R.prepare(TRANSFORM)
        self.assertEqual(task['source'], D.compile_task(TRANSFORM)['source'])
        self.assertEqual(task['options']['auto_route'], {'candidates': list(R.LOCAL_LADDER), 'max_calls': 3,
                          'repairs': 0, 'declared_repairs': 'shared', 'allow_cloud': False})
        self.assertEqual(task['options']['max_calls'], 3)
        self.assertEqual(len(task['routing_id']), 64)
        for name in ('symblic/providers/applicators.py', 'symblic/providers/ollama_call.py'):
            if name in X.PYTHON_FILES and (X.BASE / name).is_file():
                self.assertIn(name, task['options']['execution_pins']['python_hashes'])
        self.assertEqual(R.prepare(ARITHMETIC)['routing']['mode'], 'none')

    def test_source_contract_stable_route_identity_changes_with_choice(self):
        tasks = [R.prepare(TRANSFORM, by=by) for by in (None, 'fake:a', ['fake:a'], ['fake:b', 'fake:a'])]
        self.assertEqual(len({t['contract_id'] for t in tasks}), 1)
        self.assertEqual(len({t['routing_id'] for t in tasks}), 4)
        self.assertEqual(tasks[1]['routing']['mode'], 'explicit_single')
        self.assertEqual(tasks[2]['routing']['mode'], 'explicit_list')

    def test_bounded_lists_reject_duplicates_and_nested_routes(self):
        for bad in ([], ['fake:x'] * 2, [' fake:x', 'fake:x'], ['fake:a'] * 13,
                    ['fake:a', 'kernel'], ['fake:a', 'council'], ['fake:a', 3], 'auto'):
            with self.subTest(bad=bad), self.assertRaises((D.ContractError, S.SymblicError)):
                R.prepare(TRANSFORM, by=bad)
        self.assertFalse(R.prepare(TRANSFORM, by=['fake:a', 'fake:b'])['routing']['allow_cloud'])
        self.assertTrue(R.prepare(TRANSFORM, by=['fake:a', 'claude:haiku'])['routing']['allow_cloud'])

    def test_shared_repairs_advance_on_check_failure(self):
        apps = Provider({TINY: [ok([1, 1])], SMALL: [ok([1, 2])]})
        result = R.run_task(TRANSFORM, applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(apps.requests, [TINY, SMALL])
        self.assertEqual(result['calls'], 2)
        self.assertEqual([r['sample_attempts'] for r in result['routing']['attempts']], [1, 1])

    def test_explicit_single_preserves_native_repairs(self):
        apps = Provider({'fake:a': [ok([1, 1]), ok([1, 2])]})
        result = R.run_task(TRANSFORM, applicators=apps, by='fake:a')
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(apps.requests, ['fake:a', 'fake:a'])

    def test_unavailable_fatal_is_charged_but_predispatch_refusal_is_refunded(self):
        fatal = {'ok': False, 'fatal': True, 'error': 'no node has the model'}
        refused = {'ok': False, 'refused': True, 'error': 'power fence'}
        for reply, calls in ((fatal, 3), (refused, 1)):
            with self.subTest(reply=reply):
                apps = Provider({TINY: [reply], SMALL: [reply], MID: [ok([1, 2])]})
                result = R.run_task({**TRANSFORM, 'calls': calls}, applicators=apps)
                self.assertTrue(result['accepted'], result['error'])
                self.assertEqual(apps.requests, list(R.LOCAL_LADDER))
                self.assertEqual(result['calls'], calls)
                self.assertEqual(result['routing']['asks'][0]['reach'], 3)
                self.assertEqual(result['routing']['asks'][0]['full_attempt_budget_reach'], calls)

    def test_all_refusals_are_visible_without_fabricating_model_calls(self):
        refused = {'ok': False, 'refused': True, 'error': 'not admitted'}
        apps = Provider({name: [refused] for name in R.LOCAL_LADDER})
        result = R.run_task(TRANSFORM, applicators=apps)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['calls'], 0)
        self.assertEqual(len(result['routing']['attempts']), 3)
        self.assertTrue(all(row['sample_attempts'] == 0 for row in result['routing']['attempts']))

    def test_total_budget_stops_before_fourth_dispatch(self):
        names = ['fake:' + str(i) for i in range(5)]
        apps = Provider({name: [ok([1, 1])] for name in names})
        result = R.run_task(TRANSFORM, applicators=apps, by=names)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['calls'], 3)
        self.assertEqual(apps.requests, names[:3])
        self.assertTrue(result['routing']['budget_exhausted'])

    def test_incremental_proof_escalates_checked_step_without_search(self):
        bad = {'rule': 'premise', 'args': ['missing'], 'formula': None}
        good = {'rule': 'premise', 'args': ['p'], 'formula': None}
        apps = Provider({TINY: [ok(bad)], SMALL: [ok(good)]})
        with patch.object(S.KB, 'derive', side_effect=AssertionError('no proof search')):
            result = R.run_task(INCREMENTAL, applicators=apps)
        self.assertTrue(result['accepted'], result['error'])
        self.assertEqual(apps.requests, [TINY, SMALL])

    def test_correct_category_membership_does_not_assert_meaning(self):
        result = R.run_task(CLASSIFY, applicators=Provider({TINY: [ok('blue')]}))
        self.assertTrue(result['accepted'])
        self.assertEqual(result['routing']['semantic_correctness'], 'not_established')
        self.assertEqual(result['routing']['assurance_scope'], 'membership_in_caller_categories')

    def test_opt_in_keeps_legacy_declared_retries_and_requires_anchor(self):
        task = R.prepare(TRANSFORM, by=['fake:a', 'fake:b'])
        opts = copy.deepcopy(task['options'])
        del opts['auto_route']['declared_repairs']
        apps = Provider({'fake:a': [ok([1, 1])] * 3})
        result = Run(task['source'], task['inputs'], apps, opts).execute()
        self.assertEqual(result['calls'], 3)
        self.assertEqual(apps.requests, ['fake:a'] * 3)
        source = 'use profile=verified.\nask x: Int "choose" with effort=low, route=escalate\nshow x.\n'
        opts = {'by': 'auto', 'max_calls': 3, 'auto_route': task['options']['auto_route']}
        apps = Provider({})
        result = Run(source, {}, apps, opts).execute()
        self.assertNotEqual(result['status'], 'done')
        self.assertEqual(apps.requests, [])

    def test_durable_call_ceiling_and_cached_reads(self):
        task = R.prepare(TRANSFORM, by=['fake:a', 'fake:b'])
        apps = Provider({'fake:a': [ok([1, 1])], 'fake:b': [ok([1, 2])]})
        with tempfile.TemporaryDirectory() as folder:
            first = Run(task['source'], task['inputs'], apps, task['options'], folder=folder).execute()
            resumed = Run(task['source'], task['inputs'], apps, task['options'], folder=folder).execute()
        self.assertEqual((first['status'], resumed['status']), ('done', 'done'))
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(resumed['calls'], 0)
        self.assertEqual(resumed['model_budget']['used'], 2)
        self.assertEqual(resumed['cached'], 2)

    def test_interrupted_summary_scope_covers_stop_without_error(self):
        task = R.prepare(TRANSFORM)
        native = type('Trace', (), {'trace': []})()
        for status in ('stopped', 'running', 'new', None):
            receipt = R.routing_record(task, native, {'status': status, 'error': None, 'calls': 0})
            self.assertTrue(receipt['interrupted_rung_may_be_omitted'])
        complete = R.routing_record(task, native, {'status': 'done', 'error': None, 'calls': 0})
        self.assertFalse(complete['interrupted_rung_may_be_omitted'])

    def test_cli_repeated_choices_use_exact_list_and_cleanup(self):
        apps = Provider({'fake:a': [ok([1, 1])], 'fake:b': [ok([1, 2])]})
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder, 'task.json'); task.write_text(json.dumps(TRANSFORM))
            output = io.StringIO()
            with patch('symblic.providers.applicators.Applicators', return_value=apps), contextlib.redirect_stdout(output), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = R.main(['run', str(task), '--by', 'fake:a', '--by', 'fake:b', '--agent-json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['routing']['candidates'], ['fake:a', 'fake:b'])
        self.assertEqual(apps.cancelled, 1)



if __name__ == '__main__':
    unittest.main()
