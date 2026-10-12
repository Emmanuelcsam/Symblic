"""Bounded inference-method selection: no stores, providers or external processes."""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.inquiry import selection as I


def h(value):
    return I.digest(value)


def ref(ident, revision=1):
    return {'id': ident, 'revision': revision, 'sha256': h([ident, revision])}


def method(ident, cost=2, acquisition='source', interpretation=None, assumption='calibration'):
    return {'id': ident, 'revision': 1, 'implementation_sha256': h(['impl', ident]),
            'acquisition': [ref(acquisition)], 'interpretation': [ref(interpretation or ident + '-reader')],
            'assumptions': [ref(assumption)], 'authorized': True, 'available': True,
            'cost': None if cost is None else {'amount': cost, 'receipt_sha256': h(['cost', ident])}}


def assessment(*methods):
    methods = list(methods) or [method('reader')]
    claim = ref('claim')
    scope = {'id': 'assessment', 'revision': 1, 'claim': claim, 'domain': 'synthetic measurement',
             'units': 'dimensionless', 'outcome_schema_sha256': h('number-schema'),
             'faults': [{'id': f, 'fixture_sha256': h(f)} for f in ('drift', 'reversal', 'omission')],
             'alternatives': [{'id': a, 'definition_sha256': h(a)} for a in ('left', 'right', 'other')]}
    dependencies = {r['id']: r for m in methods for role in ('acquisition', 'interpretation', 'assumptions')
                    for r in m[role]}
    return {'schema': I.ASSESSMENT, 'claim': claim, 'scope': scope, 'scope_sha256': I.scope_digest(scope),
            'dependencies': list(dependencies.values()), 'methods': methods, 'receipts': [],
            'used_receipt_ids': [], 'budget': {'unit': 'measured_milliseconds', 'remaining': 10},
            'support': {'status': 'conditional', 'reason': 'Caller-supplied scoped support.'},
            'inquiry': {'status': 'planned', 'reason': 'Check complementary methods.', 'history': []}}


def receipt(data, ident, method_id=None, faults=None, predictions=None, status='completed', used=False):
    m = next(m for m in data['methods'] if m['id'] == (method_id or data['methods'][0]['id']))
    row = {'id': ident, 'scope_sha256': data['scope_sha256'], 'method_id': m['id'],
           'method_sha256': I.method_digest(m), 'status': status,
           'faults': [{'id': k, 'fixture_sha256': h(k), 'outcome': v,
                       'witness_sha256': h([ident, k, v]) if v in ('caught', 'missed') else None}
                      for k, v in (faults or {}).items()],
           'predictions': [{'id': k, 'definition_sha256': h(k),
                            'outcome_sha256': h(v) if v is not None else None}
                           for k, v in (predictions or {}).items()]}
    data['receipts'].append(row)
    if used:
        data['used_receipt_ids'].append(ident)
    return row


class InquirySelection(unittest.TestCase):
    def test_synthetic_example_observations_and_operation_counts(self):
        data = I.example()
        self.assertEqual(data, I.example())
        before = copy.deepcopy(data)
        out = I.plan(data)
        self.assertEqual(out['baseline']['covered_fault_ids'], ['reversal'])
        self.assertEqual(out['pareto_frontier'], ['b-total', 'c-length'])
        self.assertEqual(out['recommendation']['method_id'], 'b-total')
        self.assertEqual(out['recommendation']['new_fault_ids'], ['drift', 'omission'])
        self.assertEqual(out['recommendation']['cost']['amount'], 8)
        self.assertEqual(out['status'], 'reopen_recommended')
        self.assertEqual(data, before)

    def test_different_readers_share_acquisition_without_fabricating_independence(self):
        data = assessment(method('a'), method('b'))
        receipt(data, 'ra', 'a', {'drift': 'caught'}, used=True)
        receipt(data, 'rb', 'b', {'drift': 'caught'})
        out = I.plan(data)
        self.assertEqual(out['independence'], 'not_established')
        source = next(r for r in out['shared_dependencies'] if r['role'] == 'acquisition')
        self.assertEqual(source['method_ids'], ['a', 'b'])
        self.assertNotEqual(out['methods'][0]['interpretation'], out['methods'][1]['interpretation'])
        self.assertIsNone(out['recommendation'])

    def test_shared_calibration_revision_invalidates_only_dependent_evidence(self):
        data = assessment(method('a'), method('b', assumption='other-calibration'))
        receipt(data, 'ra', 'a', {'drift': 'caught'}, used=True)
        receipt(data, 'rb', 'b', {'reversal': 'caught'})
        data['dependencies'] = [ref('calibration', 2) if r['id'] == 'calibration' else r
                                for r in data['dependencies']]
        out = I.plan(data)
        self.assertEqual(out['support_binding']['stale_used_receipt_ids'], ['ra'])
        self.assertEqual(out['methods'][0]['stale_dependency_ids'], ['calibration'])
        self.assertEqual(out['recommendation']['method_id'], 'b')
        self.assertEqual(out['support'], data['support'])
        self.assertEqual(len(out['planned_receipts']), 2)

    def test_one_hundred_repetitions_add_no_new_fault_coverage(self):
        data = assessment(method('a'), method('b'))
        receipt(data, 'baseline', 'a', {'drift': 'caught'}, used=True)
        for i in range(100):
            receipt(data, 'repeat-' + str(i), 'b', {'drift': 'caught'})
        out = I.plan(data)
        self.assertEqual(out['baseline']['covered_fault_ids'], ['drift'])
        self.assertEqual(out['methods'][1]['new_fault_ids'], [])
        self.assertEqual(len(out['planned_receipts']), 101)
        self.assertIsNone(out['recommendation'])

    def test_failed_timed_out_unavailable_unperformed_remain_denominator_not_coverage(self):
        data = assessment()
        for status in sorted(I._OUTCOMES - {'completed'}):
            receipt(data, status, faults={'drift': 'caught'}, status=status, used=True)
        out = I.plan(data)
        self.assertEqual({r['status'] for r in out['planned_receipts']}, I._OUTCOMES - {'completed'})
        self.assertEqual(out['baseline']['covered_fault_ids'], [])
        self.assertIsNone(out['recommendation'])

    def test_contested_support_and_completed_inquiry_preserve_history_with_new_check(self):
        data = assessment()
        data['support'] = {'status': 'contested', 'reason': 'A new receipt disagrees.'}
        data['inquiry'] = {'status': 'completed', 'reason': 'Earlier bounded inquiry finished.',
                           'history': [{'status': 'stopped', 'reason': 'Earlier resource limit.',
                                        'scope_sha256': h('older-scope')}]}
        receipt(data, 'new', faults={'reversal': 'caught'})
        before = copy.deepcopy(data)
        out = I.plan(data)
        self.assertEqual(out['status'], 'reopen_recommended')
        self.assertEqual(out['support'], data['support'])
        self.assertEqual(out['inquiry'], data['inquiry'])
        self.assertEqual(data, before)

    def test_new_available_method_reopens_budget_stop_without_changing_support(self):
        data = assessment()
        data['inquiry']['status'] = 'stopped'
        data['inquiry']['reason'] = 'No available method in earlier scope.'
        data['support']['status'] = 'supported'
        receipt(data, 'new', faults={'omission': 'caught'})
        data['methods'][0]['available'] = False
        self.assertIsNone(I.plan(data)['recommendation'])
        data['methods'][0]['available'] = True
        out = I.plan(data)
        self.assertEqual(out['status'], 'reopen_recommended')
        self.assertEqual(out['support']['status'], 'supported')

    def test_claim_scope_method_and_fixture_mutations_refuse_stale_receipts(self):
        original = assessment()
        receipt(original, 'r', faults={'drift': 'caught'})
        for mutate, code in (
            (lambda d: d.update(claim=ref('claim', 2)), 'stale_claim'),
            (lambda d: d['scope'].update(units='metres'), 'scope_pin_mismatch'),
            (lambda d: d['receipts'][0].update(scope_sha256=h('other')), 'stale_scope_receipt'),
            (lambda d: d['methods'][0].update(implementation_sha256=h('changed')), 'stale_method_receipt'),
            (lambda d: d['receipts'][0]['faults'][0].update(fixture_sha256=h('other')), 'fault_contract_mismatch'),
        ):
            data = copy.deepcopy(original)
            mutate(data)
            with self.subTest(code=code), self.assertRaises(I.InquiryError) as raised:
                I.plan(data)
            self.assertEqual(raised.exception.code, code)

    def test_empty_coverage_unknown_cost_and_budget_exhaustion_stay_explicit(self):
        data = assessment(method('unknown', cost=None), method('empty'), method('costly', cost=20))
        receipt(data, 'unknown', 'unknown', {'drift': 'caught'})
        receipt(data, 'costly', 'costly', {'reversal': 'caught'})
        out = I.plan(data)
        rows = {r['id']: r for r in out['methods']}
        self.assertIn('cost_unknown', rows['unknown']['reasons'])
        self.assertEqual(rows['empty']['unknown_fault_ids'], ['drift', 'omission', 'reversal'])
        self.assertIn('over_budget', rows['costly']['reasons'])
        self.assertIsNone(out['recommendation'])
        data['methods'][0]['cost'] = {'amount': 1, 'receipt_sha256': h('measured')}
        data['budget']['remaining'] = 0
        self.assertIsNone(I.plan(data)['recommendation'])

    def test_recommendation_never_grants_authority_or_calls_host(self):
        data = assessment()
        receipt(data, 'r', faults={'drift': 'caught'})
        with patch('builtins.open', side_effect=AssertionError('no IO')), \
             patch('subprocess.Popen', side_effect=AssertionError('no process')):
            out = I.plan(data)
        self.assertFalse(out['authorizes_execution'])
        self.assertFalse(out['recommendation']['authorizes_execution'])
        self.assertEqual(out['recommendation']['scope_sha256'], data['scope_sha256'])
        self.assertEqual(out['recommendation']['method_sha256'], I.method_digest(data['methods'][0]))
        data['methods'][0]['authorized'] = False
        self.assertIsNone(I.plan(data)['recommendation'])

    def test_pareto_dominance_uses_sets_not_counts_and_stable_id_selection(self):
        data = assessment(method('a'), method('b'), method('dominated', cost=3), method('superset', cost=2))
        receipt(data, 'a', 'a', {'drift': 'caught'})
        receipt(data, 'b', 'b', {'reversal': 'caught'})
        receipt(data, 'd', 'dominated', {'drift': 'caught'})
        receipt(data, 's', 'superset', {'drift': 'caught', 'omission': 'caught'})
        out = I.plan(data)
        self.assertEqual(out['pareto_frontier'], ['b', 'superset'])
        self.assertEqual(out['recommendation']['method_id'], 'b')

    def test_different_benefits_are_incomparable_even_with_equal_counts(self):
        data = assessment(method('a'), method('b'))
        receipt(data, 'a', 'a', {'drift': 'caught'})
        receipt(data, 'b', 'b', {'reversal': 'caught'})
        self.assertEqual(I.plan(data)['pareto_frontier'], ['a', 'b'])

    def test_discrimination_requires_same_method_observations_and_preserves_unknowns(self):
        data = assessment(method('a'), method('b'), method('c'))
        receipt(data, 'a', 'a', predictions={'left': 'yes'}, used=True)
        receipt(data, 'b', 'b', predictions={'right': 'no'}, used=True)
        receipt(data, 'c', 'c', predictions={'left': 'yes', 'right': 'no', 'other': None})
        out = I.plan(data)
        self.assertEqual(out['baseline']['distinguished_alternative_pairs'], [])
        self.assertEqual(out['recommendation']['new_alternative_pairs'], [['left', 'right']])
        self.assertEqual(out['methods'][2]['unknown_alternative_ids'], ['other'])

    def test_conflicting_same_method_observations_do_not_claim_coverage(self):
        data = assessment()
        receipt(data, 'r1', faults={'drift': 'caught'}, predictions={'left': 'yes', 'right': 'no'})
        receipt(data, 'r2', faults={'drift': 'missed'}, predictions={'left': 'no', 'right': 'no'})
        out = I.plan(data)
        self.assertEqual(out['methods'][0]['conflicting_fault_ids'], ['drift'])
        self.assertEqual(out['methods'][0]['conflicting_alternative_ids'], ['left'])
        self.assertIsNone(out['recommendation'])

    def test_other_method_miss_does_not_erase_baseline_caught_fault(self):
        data = assessment(method('a'), method('b'))
        receipt(data, 'a', 'a', {'drift': 'caught'}, used=True)
        receipt(data, 'b', 'b', {'drift': 'missed'}, used=True)
        self.assertEqual(I.plan(data)['baseline']['covered_fault_ids'], ['drift'])

    def test_running_inquiry_and_withdrawn_claim_refuse_new_recommendations(self):
        data = assessment()
        receipt(data, 'r', faults={'drift': 'caught'})
        data['inquiry']['status'] = 'running'
        self.assertEqual(I.plan(data)['status'], 'await_current_inquiry')
        self.assertIsNone(I.plan(data)['recommendation'])
        data['support']['status'] = 'withdrawn'
        self.assertEqual(I.plan(data)['status'], 'claim_withdrawn')

    def test_repeated_calls_are_identical_and_outputs_are_detached(self):
        data = assessment()
        receipt(data, 'r', faults={'drift': 'caught'})
        one, two = I.plan(data), I.plan(data)
        self.assertEqual(json.dumps(one, sort_keys=True), json.dumps(two, sort_keys=True))
        one['methods'][0]['acquisition'][0]['revision'] = 9
        one['inquiry']['reason'] = 'Changed output'
        self.assertEqual(I.plan(data), two)

    def test_missing_dependency_and_availability_are_not_assumed(self):
        data = assessment()
        receipt(data, 'r', faults={'drift': 'caught'})
        data['dependencies'] = []
        data['methods'][0]['available'] = None
        out = I.plan(data)
        self.assertIn('stale_dependencies', out['methods'][0]['reasons'])
        self.assertIn('availability_unknown', out['methods'][0]['reasons'])
        self.assertIsNone(out['recommendation'])


class InquiryBoundaries(unittest.TestCase):
    def test_duplicate_ids_rejected_at_every_contract_level(self):
        original = assessment()
        receipt(original, 'r', faults={'drift': 'caught'}, predictions={'left': 'yes'}, used=True)
        for path in ('methods', 'receipts', 'dependencies', 'used_receipt_ids', 'scope.faults',
                     'scope.alternatives', 'methods.0.acquisition', 'receipts.0.faults', 'receipts.0.predictions'):
            data = copy.deepcopy(original)
            target = data
            for part in path.split('.'):
                target = target[int(part)] if type(target) is list else target[part]
            target.append(copy.deepcopy(target[0]))
            with self.subTest(path=path), self.assertRaises(I.InquiryError) as raised:
                I.plan(data)
            self.assertEqual(raised.exception.code, 'duplicate_id')

    def test_bools_floats_and_unbounded_integers_cannot_be_costs_or_revisions(self):
        for value in (True, False, 1.0, -1, I.MAX_INT + 1):
            for location in ('remaining', 'cost', 'revision'):
                data = assessment()
                if location == 'remaining':
                    data['budget']['remaining'] = value
                elif location == 'cost':
                    data['methods'][0]['cost']['amount'] = value
                else:
                    data['claim']['revision'] = value
                with self.subTest(value=value, location=location), self.assertRaises(I.InquiryError):
                    I.plan(data)

    def test_boolean_fields_require_actual_booleans(self):
        for field in ('authorized', 'available'):
            for value in (1, 0, 'true', []):
                data = assessment()
                data['methods'][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(I.InquiryError):
                    I.plan(data)

    def test_bounds_cycles_invalid_unicode_and_custom_types_refuse(self):
        cycle = []
        cycle.append(cycle)
        deep = []
        for _ in range(I.MAX_DEPTH + 1):
            deep = [deep]
        for value in (cycle, deep, '\ud800', 'x' * (I.MAX_TEXT + 1), object(), {'a': 1.5}, {1: 'bad'}):
            with self.subTest(kind=type(value).__name__), self.assertRaises(I.InquiryError):
                I.digest(value)
        data = assessment(*[method('m' + str(n)) for n in range(I.MAX_METHODS + 1)])
        with self.assertRaises(I.InquiryError):
            I.plan(data)

    def test_wide_aliases_consume_budget_without_infinite_traversal(self):
        aliased = ['x' * 1000] * 2000
        with self.assertRaises(I.InquiryError) as raised:
            I.digest(aliased)
        self.assertEqual(raised.exception.code, 'byte_limit')

    def test_strict_json_parser_rejects_duplicate_keys_floats_nonfinite_and_truncated(self):
        for raw in ('{"x":1,"x":2}', '{"x":1.0}', '{"x":NaN}', '{"x":Infinity}', '{', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(I.InquiryError):
                I.loads(raw)
        data = assessment()
        self.assertEqual(I.loads(json.dumps(data)), data)

    def test_exact_schema_and_pinned_alternative_definition(self):
        data = assessment()
        receipt(data, 'r', predictions={'left': 'yes'})
        data['receipts'][0]['predictions'][0]['definition_sha256'] = h('changed')
        with self.assertRaises(I.InquiryError) as raised:
            I.plan(data)
        self.assertEqual(raised.exception.code, 'alternative_contract_mismatch')
        data = assessment()
        data['unrecognized'] = True
        with self.assertRaises(I.InquiryError) as raised:
            I.plan(data)
        self.assertEqual(raised.exception.code, 'schema')

    def test_unknown_receipt_cannot_manufacture_baseline_coverage(self):
        data = assessment()
        data['used_receipt_ids'] = ['invented']
        with self.assertRaises(I.InquiryError) as raised:
            I.plan(data)
        self.assertEqual(raised.exception.code, 'unknown_receipt')

    def test_no_witness_no_observed_catch(self):
        data = assessment()
        row = receipt(data, 'r', faults={'drift': 'caught'})
        row['faults'][0]['witness_sha256'] = None
        with self.assertRaises(I.InquiryError) as raised:
            I.plan(data)
        self.assertEqual(raised.exception.code, 'hash')


class InquiryCLI(unittest.TestCase):
    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = I.main(args)
        return status, json.loads(output.getvalue())

    def test_example_to_file_to_plan_and_stdin_refusal(self):
        status, data = self.invoke(['example', '--agent-json'])
        self.assertEqual(status, 0)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'assessment.json'
            target.write_text(json.dumps(data))
            status, result = self.invoke(['plan', str(target), '--agent-json'])
        self.assertEqual(status, 0)
        self.assertEqual(result, I.plan(data))
        status, refusal = self.invoke(['plan', '-'])
        self.assertEqual(status, 1)
        self.assertEqual(refusal['detail']['code'], 'file_path_required')
        self.assertIn('provide its path', refusal['error'])

    def test_refuses_symlink_fifo_oversize_unknown_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'assessment.json'
            link = Path(directory) / 'link.json'
            link.symlink_to(target)
            fifo = Path(directory) / 'fifo'
            os.mkfifo(fifo)
            for raw in ('{"schema":1,"schema":2}', '{"unknown":true}', ' ' * (I.MAX_BYTES + 1)):
                target.write_text(raw)
                self.assertEqual(self.invoke(['plan', str(target)])[0], 1)
            for path in (link, fifo, Path(directory), Path(directory) / 'missing'):
                status, error = self.invoke(['plan', str(path)])
                self.assertEqual(status, 1)
                self.assertFalse(error['ok'])
                self.assertNotIn(directory, json.dumps(error))


if __name__ == '__main__':
    unittest.main()
