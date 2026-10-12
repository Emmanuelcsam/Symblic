import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.bench import eval_protocol as E
from symblic.policy import store as S

from symblic.mica import bench as B
from symblic.mica import contracts as C
from symblic.mica import fixtures as F

MODEL = {'primary': ['local-small@pinned-digest'], 'fallback': [], 'stronger_fallback': [],
         'settings': {'temperature': 0, 'context_tokens': 8192}}
EVALUATOR = {'kind': 'unit_test_trusted_callback', 'version': 1, 'oracle': 'exact_fake'}
BUDGET = C._budget({'max_calls': 8, 'max_candidates': 2, 'max_units': 8, 'retries': 1})


def fixture():
    return {'id': 'inc', 'family': 'increment', 'split': 'heldout',
            'request': C.normalize_request({'objective': 'Return input plus one.',
                'requirements': [{'id': 'increment', 'text': 'Return input plus one.', 'acceptance': 'TESTED'}],
                'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
                'tests': [{'requirement_ids': ['increment'], 'call': 'inc(1)', 'expected': '2'}],
                'allowed_outputs': ['result.js'], 'budget': BUDGET}),
            'hidden_tests': [['inc(8675309)', '8675310']]}


def result(source='function inc(x){return x+1}', **extra):
    return {'status': 'done', 'output': {'file': 'result.js', 'text': source,
            'sha256': hashlib.sha256(source.encode()).hexdigest()}, 'calls': 1,
            'attempts': [{'id': 'native-1', 'calls': 1}], 'costs': {}, 'evidence': [], **extra}


def evaluate(source, cases):
    passed = 'x+1' in source
    return {'passed': passed, 'total': len(cases), 'failed': 0 if passed else len(cases),
            'report': 'evaluator_private_8675309'}


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def freeze(self, **kwargs):
        return B.MicaBenchmark.freeze(self.root, 'trial', [fixture()], model=MODEL,
            budget=BUDGET, evaluator_identity=EVALUATOR, **kwargs)

    def dispatch(self, bench, ident, runner):
        return bench.run_assignment(ident, runner, evaluator=evaluate, evaluator_identity=EVALUATOR)

    def test_freeze_all_assignments_and_equal_complete_budgets(self):
        bench = self.freeze(repetitions=2, order_seed=734)
        self.assertEqual(len(bench.assignments()), 12)
        before = B._read(bench.path / 'plan.json')
        seen = []
        def runner(**kwargs):
            self.assertEqual(len(B._read(bench.path / 'plan.json')['assignments']), 12)
            self.assertEqual(kwargs['request']['budget'], BUDGET)
            self.assertEqual(kwargs['controls']['budget'], {'provider_calls': 8, 'caller_budget': BUDGET})
            self.assertNotIn('8675309', json.dumps(kwargs))
            seen.append(copy.deepcopy(kwargs))
            kwargs['request']['objective'] = 'mutated by callback'
            return result()
        report = bench.run_all(runner, evaluator=evaluate, evaluator_identity=EVALUATOR)
        self.assertEqual(before, B._read(bench.path / 'plan.json'))
        self.assertEqual(len(seen), 12)
        self.assertEqual(report['assigned'], 12)
        self.assertTrue(report['declared_matching']['matched'])
        self.assertEqual(report['runtime_matching'], 'unobserved')
        self.assertNotIn('8675309', json.dumps(report))
        for row in report['modes'].values():
            self.assertEqual(row['successes'], 2)
            self.assertEqual(row['costs']['input_tokens']['unobserved_runs'], 2)
            self.assertIsNone(row['costs']['input_tokens']['observed_total'])
        for repeat in (0, 1):
            self.assertEqual(len({r['seed'] for r in seen if r['assignment']['repeat'] == repeat}), 1)

    def test_seeded_counterbalanced_order_and_pin_reopen(self):
        bench = self.freeze(repetitions=6, order_seed=17)
        rows = bench.assignments()
        self.assertEqual(len(rows), 36)
        for mode in B.MODES:
            self.assertEqual(sorted(r['position'] for r in rows if r['arm_id'] == mode), list(range(6)))
        reopened = B.MicaBenchmark(self.root, 'trial', bench.freeze_sha256)
        self.assertEqual(reopened.assignments(), rows)
        with self.assertRaises(B.BenchmarkError):
            B.MicaBenchmark(self.root, 'trial', 'f'*64).assignments()

    def test_unknown_dispatch_never_replayed_even_after_exception(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        calls = []
        def broken(**kwargs):
            calls.append(kwargs)
            raise RuntimeError('possibly delivered')
        first = self.dispatch(bench, ident, broken)
        second = self.dispatch(bench, ident, broken)
        self.assertEqual((first['status'], second['status']), ('unknown', 'unknown'))
        self.assertEqual(len(calls), 1)
        mode = bench.assignments()[0]['arm_id']
        self.assertEqual(bench.report()['modes'][mode]['statuses'], {'unknown': 1})

    def test_process_interruption_leaves_intent_without_redispatch(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        def stopped(**_):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.dispatch(bench, ident, stopped)
        self.assertEqual(self.dispatch(bench, ident, lambda **_: self.fail('replay'))['status'], 'unknown')

    def test_reentrant_concurrent_claim_does_not_dispatch(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        seen = []
        def runner(**_):
            seen.append(self.dispatch(bench, ident, lambda **_: self.fail('duplicate')))
            return result()
        self.dispatch(bench, ident, runner)
        self.assertEqual(seen[0]['status'], 'unknown')
        cached = self.dispatch(bench, ident, lambda **_: self.fail('completed replay'))
        self.assertTrue(cached['grade']['passed'])

    def test_all_failures_in_denominator_and_hidden_not_repair_feedback(self):
        bench = self.freeze()
        calls = []
        def runner(**kwargs):
            calls.append(kwargs)
            if kwargs['mode'] == 'direct':
                return result('function inc(x){return x}')
            return result(status={'static': 'failed', 'decompose_on_failure': 'exhausted',
                                   'capability': 'blocked', 'search': 'unknown', 'mica': 'done'}[kwargs['mode']])
        report = bench.run_all(runner, evaluator=evaluate, evaluator_identity=EVALUATOR)
        self.assertEqual(len(calls), 6)
        self.assertEqual(report['assigned'], 6)
        self.assertEqual(sum(r['successes'] for r in report['modes'].values()), 1)
        self.assertEqual(report['modes']['direct']['grade_statuses'], {'failed': 1})
        self.assertTrue(all('8675309' not in json.dumps(c) for c in calls))

    def test_inconclusive_evaluator_is_not_candidate_failure_or_retry(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        def unavailable(*_):
            raise RuntimeError('sandbox resource unavailable')
        row = bench.run_assignment(ident, lambda **_: result(), evaluator=unavailable,
                                   evaluator_identity=EVALUATOR)
        self.assertEqual(row['grade']['status'], 'unknown')
        self.assertIsNone(row['grade']['passed'])
        self.dispatch(bench, ident, lambda **_: self.fail('retry'))
        report = bench.report()
        mode = bench.assignments()[0]['arm_id']
        self.assertEqual(report['modes'][mode]['successes'], 0)

    def test_information_difference_explicit_and_budget_difference_rejected(self):
        bench = self.freeze(controls_overrides={'static': {'information': {'manual_plan': 'added'}}})
        self.assertEqual(bench.report()['declared_matching']['mismatched_axes'], ['information'])
        self.assertFalse(bench.report()['declared_matching']['matched'])
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(B.BenchmarkError):
            B.MicaBenchmark.freeze(directory, 'trial', [fixture()], model=MODEL, budget=BUDGET,
                evaluator_identity=EVALUATOR, controls_overrides={'mica': {'budget': {'provider_calls': 9}}})
        changed = fixture()
        changed['request']['budget']['max_calls'] = 9
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(B.BenchmarkError):
            B.MicaBenchmark.freeze(directory, 'trial', [changed], model=MODEL, budget=BUDGET,
                                   evaluator_identity=EVALUATOR)

    def test_budget_breach_recorded_not_hidden_and_costs_preserved(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        self.dispatch(bench, ident, lambda **_: result(calls=9, costs={'input_tokens': 92, 'usd': 0,
                       'provider_ms': 400, 'wall_seconds': 1, 'memory_bytes': 1000}))
        report = bench.report()
        mode = bench.assignments()[0]['arm_id']
        self.assertEqual(report['modes'][mode]['successes'], 0)
        self.assertEqual(report['modes'][mode]['costs']['usd']['observed_total'], 0)
        self.assertEqual(report['modes'][mode]['costs']['provider_ms']['observed_total'], 400)
        self.assertEqual(report['modes'][mode]['costs']['wall_seconds']['observed_total'], 1)
        self.assertIsNone(report['modes'][mode]['costs']['memory_bytes']['observed_total'])
        self.assertEqual(report['modes'][mode]['costs']['memory_bytes']['observed_max'], 1000)
        self.assertIn('budget_exceeded', [c['kind'] for c in report['confounds']])

    def test_output_hash_mismatch_is_unknown_no_replay(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        row = result()
        row['output']['sha256'] = 'f'*64
        self.assertEqual(self.dispatch(bench, ident, lambda **_: row)['status'], 'unknown')
        self.dispatch(bench, ident, lambda **_: self.fail('replay'))

    def test_hidden_and_implementation_pin_fail_before_dispatch(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        with self.assertRaises(B.BenchmarkError):
            bench.run_assignment(ident, lambda **_: self.fail('dispatch'), evaluator=evaluate,
                                 evaluator_identity={'kind': 'changed'})
        hidden = S._read(bench.path / 'hidden.json')
        hidden['payload_sha256'] = 'a'*64
        (bench.path / 'hidden.json').write_text(json.dumps(hidden, sort_keys=True, separators=(',', ':')))
        with self.assertRaises(B.BenchmarkError):
            self.dispatch(bench, ident, lambda **_: self.fail('dispatch'))

    def test_public_requests_can_not_leak_split_families(self):
        first, second = fixture(), fixture()
        second.update(id='dev_inc', split='dev')
        with self.assertRaises(E.ProtocolError):
            B.MicaBenchmark.freeze(self.root, 'trial', [first, second], model=MODEL,
                                    budget=BUDGET, evaluator_identity=EVALUATOR)

    def test_complete_host_control_attestations_have_explicit_scope(self):
        bench = self.freeze()
        def runner(**kwargs):
            return result(observed_controls={k: E.digest(v) for k, v in kwargs['controls'].items()})
        report = bench.run_all(runner, evaluator=evaluate, evaluator_identity=EVALUATOR)
        self.assertEqual(report['runtime_matching'], 'host_attested')
        self.assertEqual(report['declared_matching']['scope'], 'declared_controls_only')

    def test_private_store_rejects_symlink_and_public_permissions(self):
        bench = self.freeze()
        path = bench.path / 'runs'
        path.chmod(0o755)
        with self.assertRaises(S.PolicyStoreError):
            self.dispatch(bench, bench.assignments()[0]['id'], lambda **_: self.fail('dispatch'))

    def test_symlink_assignment_folder_refused(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        with tempfile.TemporaryDirectory() as elsewhere:
            (bench.path / 'runs' / ident).symlink_to(elsewhere)
            with self.assertRaises(S.PolicyStoreError):
                self.dispatch(bench, ident, lambda **_: self.fail('dispatch'))

    def test_fractional_metrics_settings_and_long_source_survive_immutable_codec(self):
        model = {**MODEL, 'settings': {'temperature': 0.15}}
        bench = B.MicaBenchmark.freeze(self.root, 'float_trial', [fixture()], model=model,
            budget=BUDGET, evaluator_identity=EVALUATOR)
        source = 'function inc(x){return x+1}\n/*' + 'bounded source ' * 1600 + '*/'
        outcome = self.dispatch(bench, bench.assignments()[0]['id'], lambda **_: result(source,
            costs={'wall_seconds': 1.25, 'latency_ms': 1250.5, 'provider_ms': 920.125, 'cpu_seconds': 0.4}))
        self.assertEqual(outcome['runner']['output']['text'], source)
        replay = self.dispatch(bench, bench.assignments()[0]['id'], lambda **_: self.fail('replay'))
        self.assertEqual(replay, outcome)
        costs = bench.report()['modes'][bench.assignments()[0]['arm_id']]['costs']
        self.assertEqual(costs['wall_seconds']['observed_total'], 1.25)
        self.assertEqual(costs['cpu_seconds']['observed_total'], 0.4)
        self.assertEqual(B._read(bench.path/'plan.json')['arms'][0]['controls']['model'], model)

    def test_extreme_measured_counter_is_unknown_not_nonfinite_report(self):
        bench = self.freeze()
        ident = bench.assignments()[0]['id']
        row = self.dispatch(bench, ident, lambda **_: result(costs={'wall_seconds': 1e308}))
        self.assertEqual(row['status'], 'unknown')
        json.dumps(bench.report(), allow_nan=False)

    def test_import_time_execution_marker_is_required(self):
        with patch.dict(B._symblic_import_identity, {'matched': False}), self.assertRaises(B.BenchmarkError):
            self.freeze()

    def test_stopped_assignment_retained_in_denominator_without_automatic_replay(self):
        bench = self.freeze()
        assignment = bench.assignments()[0]
        stopped = self.dispatch(bench, assignment['id'], lambda **_: result(status='stopped'))
        self.assertEqual(stopped['status'], 'stopped')
        self.assertEqual(self.dispatch(bench, assignment['id'], lambda **_: self.fail('replay')), stopped)
        report = bench.report()
        self.assertEqual(report['modes'][assignment['arm_id']]['statuses'], {'stopped': 1})
        self.assertEqual(report['modes'][assignment['arm_id']]['successes'], 0)


class FixtureTests(unittest.TestCase):
    def test_fixtures_reproducible_distinct_counts_and_valid_requests(self):
        for make in (F.arithmetic_collections, F.strict_json):
            a, b = make(seed=42, generated=3, budget=BUDGET), make(seed=42, generated=3, budget=BUDGET)
            self.assertEqual(a, b)
            self.assertEqual(C.normalize_request(a['request']), a['request'])
            self.assertLessEqual(len(a['hidden_tests']), 200)
            self.assertNotEqual(len(make(generated=1)['hidden_tests']), len(make(generated=5)['hidden_tests']))
        self.assertNotEqual(F.strict_json(seed=1)['hidden_tests'], F.strict_json(seed=2)['hidden_tests'])
        self.assertNotEqual(len(F.strict_json(invalid_generated=1)['hidden_tests']),
                            len(F.strict_json(invalid_generated=5)['hidden_tests']))

    def test_oracle_declared_json_boundaries(self):
        self.assertEqual(F.strict_json_oracle('{"__proto__":1}'), {'__proto__': 1})
        self.assertEqual(F.strict_json_oracle('"\\uD83D\\uDE03"'), '😃')
        self.assertEqual(F.strict_json_oracle(str(F.SAFE)), F.SAFE)
        self.assertIsNone(F.strict_json_oracle(' '*65532+'null'))
        for bad in (' '*65533+'null', '{"a":1,"\\u0061":2}', str(F.SAFE+1), 'NaN',
                    '1e999', '['*33+'0'+']'*33, 'null true', '"raw\nline"'):
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError):
                F.strict_json_oracle(bad)

    def test_demo_files_separate_public_request_and_private_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            F.write_demo_files(directory, budget=BUDGET)
            files = sorted(Path(directory).glob('*.json'))
            self.assertEqual(len(files), 4)
            for path in files:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                value = json.loads(path.read_text())
                self.assertEqual('hidden_tests' in value, '.fixture.' in path.name)

    def test_native_javascript_evaluator_checks_independent_hidden_cases(self):
        from symblic.js import check as JS
        if not JS.available():
            self.skipTest('native JavaScript sandbox unavailable')
        with tempfile.TemporaryDirectory() as directory:
            bench = B.MicaBenchmark.freeze(directory, 'native', [fixture()], model=MODEL, budget=BUDGET)
            assignment = bench.assignments()[0]
            row = bench.run_assignment(assignment['id'], lambda **_: result('function inc(x){return x===1?2:0}'))
            self.assertEqual(row['status'], 'done')
            self.assertEqual(row['grade']['status'], 'failed')
            self.assertEqual(row['grade']['result']['total'], 1)

    def test_native_javascript_arithmetic_fixture_end_to_end(self):
        from symblic.js import check as JS
        if not JS.available():
            self.skipTest('native JavaScript sandbox unavailable')
        source = '''
function clamp(x,lo,hi){return Math.min(hi,Math.max(lo,x))}
function sum(values){return values.reduce((total,x)=>total+x,0)}
function mean(values){return values.length?sum(values)/values.length:null}
function histogram(values){const counts=Object.create(null);for(const value of values){const key=String(value);counts[key]=(counts[key]||0)+1}return counts}
function movingAverage(values,width){const out=[];for(let i=0;i+width<=values.length;i++)out.push(mean(values.slice(i,i+width)));return out}
function summarize(values){return {count:values.length,total:sum(values),mean:mean(values),min:values.length?Math.min(...values):null,max:values.length?Math.max(...values):null,histogram:histogram(values)}}
'''
        test_fixture = F.arithmetic_collections(generated=3)
        checked = JS.test(source, test_fixture['hidden_tests'])
        self.assertTrue(checked['passed'], checked['report'])
        self.assertEqual(checked['total'], len(test_fixture['hidden_tests']))

    def test_native_javascript_plain_json_parse_fails_strict_policy(self):
        from symblic.js import check as JS
        if not JS.available():
            self.skipTest('native JavaScript sandbox unavailable')
        test_fixture = F.strict_json(generated=2, invalid_generated=2)
        checked = JS.test('function parseJSON(text){return JSON.parse(text)}', test_fixture['hidden_tests'])
        self.assertFalse(checked['passed'])
        self.assertGreater(checked['failed'], 3)
        self.assertEqual(checked['total'], len(test_fixture['hidden_tests']))


if __name__ == '__main__':
    unittest.main()
