"""Frontier ladder planner (tools/scripts/symblic_frontier_ladder.py): fixtures, plan, aggregation and refusals.

Nothing here calls a model, runs a benchmark assignment, executes JavaScript or opens
the network. Benchmarks are only frozen into private temporary roots, and status files
are written with the bench's own store helpers.
"""
import ast
import copy
import hashlib
import importlib.util
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path

from symblic.bench import eval_protocol as E
from symblic.mica import bench as B
from symblic.mica import cli as CLI
from symblic.mica import contracts as C
from symblic.mica import routing as R

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'tools' / 'scripts' / 'symblic_frontier_ladder.py'
FIXTURES = REPO / 'benchmarks' / 'frontier'
EVALUATOR = {'kind': 'unit_test_stub_evaluator', 'version': 1}
IMPLEMENTATION = {'kind': 'unit_test_construction_stub', 'version': 1}
DIGEST = hashlib.sha256(b'frontier-ladder-test-digest').hexdigest()
STUB_MODEL = {'primary': ['ollama:unit-test@node-z#unobserved'], 'fallback': [], 'stronger_fallback': [],
              'settings': {}}


def load_script(name='symblic_frontier_ladder_under_test'):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


L = load_script()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    code = L.main(argv, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def ladder():
    manifest = json.loads((FIXTURES / 'ladder.json').read_text())
    return manifest, {row['key']: (row, json.loads((FIXTURES / row['file']).read_text()))
                      for row in manifest['families']}


class TempCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / 'lab').mkdir(mode=0o700)  # the bench creates the root, never its parent
        self.root = self.base / 'lab' / 'experiments'
        self.plan_dir = self.base / 'lab' / 'experiments-plan'

    def tearDown(self):
        self.temp.cleanup()

    def plan_argv(self, *extra, families='F1..F5', seconds=300, calls=8, digest=DIGEST):
        argv = ['plan', '--model', 'qwen2.5:0.5b', '--node', 'node-d', '--root', str(self.root),
                '--budget-seconds', str(seconds), '--max-calls', str(calls), '--families', families]
        if digest:
            argv += ['--digest', digest]
        return argv + list(extra)

    def plan(self, *extra, **kwargs):
        code, out, err = run(self.plan_argv('--json', *extra, **kwargs))
        self.assertEqual(code, 0, out + err)
        return json.loads(out)


class FixtureTests(TempCase):
    def test_manifest_pins_every_fixture_file(self):
        manifest, rows = ladder()
        self.assertEqual(list(rows), ['F1', 'F2', 'F3', 'F4', 'F5', 'F6'])
        self.assertEqual(manifest['default_families'], ['F1', 'F2', 'F3', 'F4', 'F5'])
        self.assertEqual(manifest['split'], 'dev')
        listed = {row['file'] for row, _ in rows.values()} | {'ladder.json'}
        self.assertEqual({p.name for p in FIXTURES.iterdir()}, listed)
        for key, (row, fixture) in rows.items():
            with self.subTest(key):
                raw = (FIXTURES / row['file']).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                self.assertEqual(raw.decode(), json.dumps(fixture, ensure_ascii=True, sort_keys=True, indent=2) + '\n')
                self.assertEqual((row['id'], row['family']), (fixture['id'], fixture['family']))
                self.assertEqual(row['hidden_tests'], len(fixture['hidden_tests']))
                self.assertEqual(row['public_tests'], len(fixture['request']['tests']))
                self.assertEqual(row['exports'], [e['name'] for e in fixture['request']['exports']])
        _, _, loaded = L.load_ladder(FIXTURES)
        self.assertEqual(sorted(loaded), sorted(rows))

    def test_fixtures_are_valid_benchmark_inputs(self):
        manifest, rows = ladder()
        budget = C._budget(manifest['budget'])
        self.assertEqual((budget['wall_seconds'], budget['max_calls']), (300, 8))
        for key, (_, fixture) in rows.items():
            with self.subTest(key):
                self.assertEqual(set(fixture), {'id', 'family', 'split', 'request', 'hidden_tests'})
                self.assertEqual(fixture['split'], 'dev')
                request = fixture['request']
                self.assertEqual(C.normalize_request(request), request)
                self.assertEqual(request['budget'], budget)
                self.assertEqual((request['artifact_format'], request['allowed_outputs']),
                                 ('javascript_script', ['result.js']))
                hidden = fixture['hidden_tests']
                self.assertTrue(20 <= len(hidden) <= 60, len(hidden))
                self.assertEqual(B._hidden(hidden), hidden)
                calls = [call for call, _ in hidden]
                self.assertEqual(len(set(calls)), len(calls))
                self.assertFalse({t['call'] for t in request['tests']} & set(calls))
                rejects = [c for c, expected in hidden if c.startswith('(()=>{try{') and expected == 'true']
                self.assertGreaterEqual(len(rejects), 5)
                self.assertGreaterEqual(len(hidden) - len(rejects), 15)
                for _, expected in hidden:
                    json.loads(expected)

    def test_each_fixture_freezes_all_six_rungs(self):
        _, rows = ladder()
        for key, (_, fixture) in rows.items():
            with self.subTest(key):
                bench = B.MicaBenchmark.freeze(self.root, 'ladder-' + key.lower(), [fixture], model=STUB_MODEL,
                                               budget=fixture['request']['budget'], repetitions=1,
                                               order_seed=20261010, split='dev', evaluator_identity=EVALUATOR)
                assignments = bench.assignments()
                self.assertEqual(sorted(a['arm_id'] for a in assignments), sorted(B.MODES))
                report = bench.report()
                self.assertEqual((report['assigned'], report['completed_receipts']), (6, 0))
                self.assertEqual({r['status'] for r in report['assignments']}, {'pending'})
                self.assertTrue(report['declared_matching']['matched'])
                text = json.dumps(report)
                self.assertFalse([c for c, _ in fixture['hidden_tests'] if c in text])

    def test_one_freeze_accepts_all_families_and_refuses_unequal_budgets(self):
        _, rows = ladder()
        fixtures = [fixture for _, fixture in rows.values()]
        budget = fixtures[0]['request']['budget']
        self.assertEqual(len({json.dumps(f['request']['budget'], sort_keys=True) for f in fixtures}), 1)
        bench = B.MicaBenchmark.freeze(self.root, 'ladder-all', fixtures, model=STUB_MODEL, budget=budget,
                                       split='dev', evaluator_identity=EVALUATOR)
        self.assertEqual(len(bench.assignments()), 36)
        changed = copy.deepcopy(fixtures[1])
        changed['request'] = C.normalize_request({**changed['request'], 'budget': {**budget, 'wall_seconds': 301}})
        with self.assertRaises(B.BenchmarkError) as caught:
            B.MicaBenchmark.freeze(self.root, 'ladder-unequal', [fixtures[0], changed], model=STUB_MODEL,
                                   budget=budget, split='dev', evaluator_identity=EVALUATOR)
        self.assertEqual(str(caught.exception), 'unequal_caller_budgets')


class PlanTests(TempCase):
    def test_plan_json_shape_and_exact_commands(self):
        plan = self.plan()
        self.assertEqual(set(plan), {'version', 'kind', 'scope', 'hypothesis', 'generator', 'model', 'inventory',
                                     'budget', 'starter_budget', 'repetitions', 'split', 'root', 'plan_dir',
                                     'plan_file', 'fixtures', 'seeds', 'rungs', 'families', 'estimate',
                                     'commands', 'confounds', 'limitations', 'plan_sha256'})
        self.assertEqual(plan['model'], {'engine': 'ollama', 'model': 'qwen2.5:0.5b', 'node': 'node-d',
                                         'digest': DIGEST, 'digest_status': 'pinned'})
        rows = plan['inventory']['rows']
        self.assertEqual(R.normalize_inventory(rows), rows)
        minimal = R.normalize_inventory([{'engine': 'ollama', 'model': 'm', 'node': 'node-a'}])[0]
        self.assertEqual(set(rows[0]), set(minimal))
        self.assertEqual(plan['inventory']['row_fields'], list(L.INVENTORY_FIELDS))
        self.assertTrue(all(r['url'].startswith('http://127.0.0.1:8080/api/') for r in plan['inventory']['readiness_routes']))
        self.assertEqual([(r['rung'], r['mode']) for r in plan['rungs']], list(enumerate(B.MODES, 1)))
        ids = [f['experiment_id'] for f in plan['families']]
        for rung in plan['rungs']:
            self.assertEqual(rung['factors'], B.MODE_FACTORS[rung['mode']])
            self.assertEqual(rung['frozen_in'], ids)
        self.assertEqual([f['key'] for f in plan['families']], ['F1', 'F2', 'F3', 'F4', 'F5'])
        _, rows_by_key = ladder()
        for family, freeze, launch in zip(plan['families'], plan['commands']['freeze'], plan['commands']['run']):
            row, fixture = rows_by_key[family['key']]
            self.assertEqual(family['fixture'], str(FIXTURES / row['file']))
            self.assertFalse(family['fixture_copy'])
            self.assertEqual(family['request_sha256'], E.digest(fixture['request']))
            self.assertEqual(sorted(family['mode_order'][0]), sorted(B.MODES))
            argv = freeze['argv']
            self.assertEqual(argv[:3], [str(REPO / 'tools' / 'symblic'), 'mica', 'benchmark'])
            args = CLI.parser().parse_args(argv[2:])
            self.assertEqual((args.command, args.root, args.id, args.fixture, args.inventory),
                             ('benchmark', str(self.root), family['experiment_id'], [family['fixture']],
                              plan['inventory']['path']))
            self.assertEqual((args.repetitions, args.seed, args.split, args.run, args.freeze),
                             (1, family['seed'], 'dev', False, None))
            self.assertTrue(freeze['shell'].startswith('(set -o noclobber; '))
            self.assertTrue(freeze['shell'].endswith('> ' + family['pin_file'] + ')'))
            args = CLI.parser().parse_args(launch['cli_argv'])
            self.assertTrue(args.run)
            self.assertEqual((args.root, args.id, args.inventory), (str(self.root), family['experiment_id'],
                                                                    plan['inventory']['path']))
            self.assertIn('--slice=symblic-work.slice', launch['shell'])
            self.assertIn('--freeze "$FREEZE" --run', launch['shell'])
            self.assertIn(family['pin_file'], launch['shell'])
        estimate = plan['estimate']
        self.assertEqual((estimate['assignments'], estimate['per_assignment_seconds'], estimate['total_seconds']),
                         (30, 420, 12600))
        self.assertEqual([s['estimated_seconds'] for s in estimate['sessions']], [2520] * 5)
        self.assertFalse(any(s['over_hour_bound'] for s in estimate['sessions']))
        self.assertIn('aggregate --plan ' + plan['plan_file'], plan['commands']['aggregate'])
        path = Path(plan['plan_file'])
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(L.load_plan(path), plan)

    def test_planned_orders_equal_the_frozen_benchmark_orders(self):
        plan = self.plan('--repetitions', '2', '--no-write', families='F1,F4')
        _, rows = ladder()
        for family in plan['families']:
            fixture = rows[family['key']][1]
            bench = B.MicaBenchmark.freeze(self.root, family['experiment_id'], [fixture], model=STUB_MODEL,
                                           budget=plan['budget'], repetitions=2, order_seed=family['seed'],
                                           split='dev', evaluator_identity=EVALUATOR)
            order = [a['arm_id'] for a in bench.assignments()]
            self.assertEqual(order, [mode for block in family['mode_order'] for mode in block])

    def test_rungs_are_spread_over_dispatch_positions(self):
        plan = self.plan('--no-write')
        matrix = plan['seeds']['position_matrix']
        self.assertEqual(set(matrix), set(B.MODES))
        self.assertEqual(max(max(row) for row in matrix.values()), 1)
        self.assertTrue(all(sum(row) == 5 for row in matrix.values()))
        self.assertNotIn('position_imbalance', [c['id'] for c in plan['confounds']])
        self.assertEqual(plan['seeds']['families']['F1'], L.DEFAULT_SEED)

    def test_long_budgets_are_flagged_and_use_private_rebudgeted_copies(self):
        plan = self.plan(seconds=1800, calls=24)
        self.assertEqual({k: v for k, v in plan['budget'].items() if k not in ('wall_seconds', 'max_calls')},
                         {k: v for k, v in plan['starter_budget'].items() if k not in ('wall_seconds', 'max_calls')})
        self.assertEqual([s['estimated_seconds'] for s in plan['estimate']['sessions']], [11520] * 5)
        self.assertTrue(all(s['over_hour_bound'] for s in plan['estimate']['sessions']))
        self.assertTrue({'session_exceeds_hour_bound', 'rebudgeted_fixtures'} <= {c['id'] for c in plan['confounds']})
        code, out, err = run(['materialize', '--plan', plan['plan_file'], '--json'])
        self.assertEqual(code, 0, out + err)
        written = json.loads(out)['files']
        self.assertEqual([f['status'] for f in written], ['written'] * 6)
        _, rows = ladder()
        inventory = Path(plan['inventory']['path'])
        self.assertEqual(json.loads(inventory.read_text()), plan['inventory']['rows'])
        for family in plan['families']:
            path = Path(family['fixture'])
            self.assertEqual(path.parent, self.plan_dir / 'fixtures')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), family['fixture_sha256'])
            copy_ = json.loads(path.read_text())
            original = rows[family['key']][1]
            self.assertEqual(copy_['hidden_tests'], original['hidden_tests'])
            self.assertEqual(copy_['request']['budget'], plan['budget'])
            self.assertEqual({k: v for k, v in copy_['request'].items() if k != 'budget'},
                             {k: v for k, v in original['request'].items() if k != 'budget'})
        bench = B.MicaBenchmark.freeze(self.root, 'rebudgeted-f1', [json.loads(Path(plan['families'][0]['fixture']).read_text())],
                                       model=STUB_MODEL, budget=plan['budget'], split='dev', evaluator_identity=EVALUATOR)
        self.assertEqual(len(bench.assignments()), 6)
        code, out, _ = run(['materialize', '--plan', plan['plan_file'], '--json'])
        self.assertEqual([f['status'] for f in json.loads(out)['files']], ['unchanged'] * 6)
        inventory.write_text('[]\n')
        code, out, _ = run(['materialize', '--plan', plan['plan_file'], '--json'])
        self.assertEqual((code, json.loads(out)['error']['code']), (2, 'existing_file'))

    def test_unpinned_digest_is_a_declared_cold_start(self):
        plan = self.plan('--no-write', digest=None)
        self.assertEqual((plan['model']['digest'], plan['model']['digest_status']), (None, 'unpinned_cold_start'))
        self.assertIsNone(plan['inventory']['rows'][0]['digest'])
        self.assertIn('digest_unpinned', [c['id'] for c in plan['confounds']])
        prefixed = self.plan('--no-write', digest='sha256:' + DIGEST)
        self.assertEqual(prefixed['model']['digest'], DIGEST)

    def test_plan_file_is_never_silently_replaced(self):
        first = self.plan()
        code, out, _ = run(self.plan_argv())
        self.assertEqual(code, 0)
        self.assertIn('Plan unchanged: ' + first['plan_file'], out)
        code, out, _ = run(self.plan_argv('--repetitions', '2', '--json'))
        self.assertEqual((code, json.loads(out)['error']['code']), (2, 'existing_file'))
        self.assertEqual(L.load_plan(first['plan_file']), first)
        replaced = self.plan('--repetitions', '2', '--replace')
        self.assertEqual(L.load_plan(first['plan_file'])['repetitions'], 2)
        self.assertNotEqual(replaced['plan_sha256'], first['plan_sha256'])
        edited = json.loads(Path(first['plan_file']).read_text())
        edited['repetitions'] = 3
        Path(first['plan_file']).write_text(json.dumps(edited))
        with self.assertRaises(L.PlanError) as caught:
            L.load_plan(first['plan_file'])
        self.assertEqual(caught.exception.code, 'plan_pin')

    def test_text_output_lists_the_steps_in_order(self):
        code, out, _ = run(self.plan_argv('--no-write'))
        self.assertEqual(code, 0)
        positions = [out.index('Step %d' % n) for n in range(7)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("curl -s 'http://127.0.0.1:8080/api/automation/symblic/mica/inventory'", out)
        self.assertIn('materialize --plan', out)
        self.assertIn('(set -o noclobber; ', out)
        self.assertIn('Plan not written (--no-write).', out)
        self.assertFalse(self.plan_dir.exists())


class AggregateTests(TempCase):
    def setUp(self):
        super().setUp()
        self.plan_data = self.plan(families='F1,F2')
        code, out, err = run(['materialize', '--plan', self.plan_data['plan_file'], '--json'])
        self.assertEqual(code, 0, out + err)
        self.fixtures = ladder()[1]

    def freeze(self, family, *, rows=None, implementation=IMPLEMENTATION):
        fixture = self.fixtures[family['key']][1]
        controls = CLI._model_controls(rows or self.plan_data['inventory']['rows'], implementation)
        bench = B.MicaBenchmark.freeze(self.plan_data['root'], family['experiment_id'], [fixture], model=controls,
                                       budget=self.plan_data['budget'], repetitions=1, order_seed=family['seed'],
                                       split='dev', evaluator_identity=EVALUATOR)
        receipt = {'version': 1, 'status': 'frozen', 'freeze_sha256': bench.freeze_sha256, 'report': bench.report()}
        Path(family['pin_file']).write_text(json.dumps(receipt, sort_keys=True) + '\n')
        return bench

    def settle(self, bench, mode, status=None, *, passed=None, calls=0, wall=None):
        """Write the bench's own intent/outcome files for one assignment; no runner is called."""
        with bench._lock():
            manifest, plan, hidden = bench._load()
        assignment = next(a for a in plan['assignments'] if a['arm_id'] == mode)
        case = plan['cases'][0]
        arm = next(a for a in plan['arms'] if a['id'] == mode)
        intent = bench._intent(assignment, case['input'], arm, plan)
        folder = bench.path / 'runs' / assignment['id']
        B.S._directory(folder, create=True)
        B._write(folder / 'intent.json', intent)
        if status is None:
            return
        runner = {'status': status, 'calls': calls, 'attempts': [], 'evidence': [],
                  'costs': {} if wall is None else {'wall_seconds': wall},
                  'budget_violation': calls > self.plan_data['budget']['max_calls']}
        grade = {'status': 'not_evaluated', 'passed': None, 'scope': 'finite_hidden_tests'}
        if status == 'done':
            text = 'function placeholder(){}'
            runner['output'] = {'file': 'result.js', 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
            total = len(hidden[case['id']])
            failed = 0 if passed else 1
            grade = {'status': 'tested' if passed else 'failed', 'passed': bool(passed), 'scope': 'finite_hidden_tests',
                     'result': {'passed': bool(passed), 'total': total, 'failed': failed}}
        receipt = {'version': B.VERSION, 'assignment_id': assignment['id'], 'freeze_sha256': bench.freeze_sha256,
                   'intent_sha256': E.digest(intent), 'status': status, 'runner': runner, 'grade': grade,
                   'evaluator_sha256': E.digest(manifest['evaluator'])}
        B._write(folder / 'outcome.json', receipt)

    def cells(self, result, key):
        return {c['mode']: c for c in result['cells'] if c['family'] == key}

    def test_table_keeps_every_planned_assignment_in_the_denominator(self):
        f1 = self.plan_data['families'][0]
        bench = self.freeze(f1)
        self.settle(bench, 'static', 'done', passed=True, calls=5, wall=200.5)
        self.settle(bench, 'direct', 'done', passed=False, calls=2, wall=150.25)
        self.settle(bench, 'search', 'exhausted', calls=8, wall=301.0)
        self.settle(bench, 'capability', 'done', passed=True, calls=9, wall=280.0)
        self.settle(bench, 'mica')  # intent without outcome: unknown
        report = bench.report()
        self.assertEqual(report['modes']['mica']['statuses'], {'unknown': 1})
        result = L.aggregate(self.plan_data['plan_file'])
        f1_cells, f2_cells = self.cells(result, 'F1'), self.cells(result, 'F2')
        self.assertEqual({m: (c['passed'], c['assigned']) for m, c in f1_cells.items()},
                         {'direct': (0, 1), 'static': (1, 1), 'decompose_on_failure': (0, 1),
                          'capability': (0, 1), 'search': (0, 1), 'mica': (0, 1)})
        self.assertEqual(f1_cells['mica']['statuses'], {'unknown': 1})
        self.assertEqual(f1_cells['decompose_on_failure']['statuses'], {'pending': 1})
        self.assertEqual((f1_cells['mica']['unresolved'], f1_cells['static']['unresolved']), (1, 0))
        self.assertEqual(f1_cells['static']['calls'], {'observed_total': 5, 'observed_runs': 1, 'unobserved_runs': 0})
        self.assertEqual(f1_cells['mica']['calls']['unobserved_runs'], 1)
        self.assertEqual(f1_cells['static']['wall_seconds']['observed_total'], 200.5)
        self.assertEqual(f1_cells['capability']['calls']['observed_total'], 9)
        self.assertEqual((f1_cells['capability']['budget_exceeded'], f1_cells['static']['budget_exceeded']), (1, 0))
        self.assertEqual(f1_cells['direct']['grade_statuses'], {'failed': 1})
        self.assertEqual({c['statuses']['not_frozen'] for c in f2_cells.values()}, {1})
        self.assertEqual(sum(c['assigned'] for c in result['cells']), 12)
        by_rung = {row['mode']: row for row in result['by_rung']}
        self.assertEqual((by_rung['static']['passed'], by_rung['static']['assigned']), (1, 2))
        self.assertEqual(by_rung['static']['families_with_a_pass'], ['F1'])
        self.assertEqual(by_rung['capability']['passed'], 0)
        first = {row['family']: row['first_rung_with_a_pass'] for row in result['by_family']}
        self.assertEqual(first, {'F1': 2, 'F2': None})
        states = {f['key']: f['state'] for f in result['families']}
        self.assertEqual(states, {'F1': 'reported', 'F2': 'not_frozen'})
        self.assertTrue(result['families'][0]['frozen_controls']['matched'])
        self.assertEqual(result['confounds']['budget_exceeded'], 1)
        self.assertEqual(result['confounds']['runtime_controls_unobserved'], 4)
        text = L.render_aggregate(result)
        self.assertIn('done 1; grade tested 1; over call budget 1', text)
        self.assertIn('unknown 1', text)
        self.assertIn('F2 not_frozen', text)
        self.assertIn('First rung with a hidden pass: F1 static (2); F2 none', text)
        code, out, _ = run(['aggregate', '--plan', self.plan_data['plan_file'], '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['cells'], result['cells'])

    def test_unreadable_and_failed_pins_stay_in_the_denominator(self):
        f1, f2 = self.plan_data['families']
        self.freeze(f1)
        Path(f2['pin_file']).write_text(json.dumps({'ok': False, 'error': {'code': 'fixtures', 'message': 'x'}}))
        result = L.aggregate(self.plan_data['plan_file'], ['%s=%s' % (f1['experiment_id'], '0' * 64)])
        families = {f['key']: f for f in result['families']}
        self.assertEqual(families['F1']['state'], 'unreadable')
        self.assertEqual(families['F2']['state'], 'pin_unreadable')
        self.assertEqual(families['F2']['problem'], {'code': 'pin_missing', 'freeze_error': 'fixtures'})
        self.assertEqual({c['statuses'].get('unreadable') for c in self.cells(result, 'F1').values()}, {1})
        self.assertEqual(sum(c['assigned'] for c in result['cells']), 12)
        self.assertEqual(sum(c['passed'] for c in result['cells']), 0)
        with self.assertRaises(L.PlanError):
            L.aggregate(self.plan_data['plan_file'], ['not-a-pin'])

    def test_printed_freeze_command_freezes_through_the_cli_and_aggregates(self):
        family = self.plan_data['families'][0]
        command = self.plan_data['commands']['freeze'][0]
        self.assertEqual(command['argv'][:2], [str(REPO / 'tools' / 'symblic'), 'mica'])
        out = io.StringIO()
        code = CLI.main(command['argv'][2:], out=out, implementation=IMPLEMENTATION)  # freeze only, no --run
        receipt = json.loads(out.getvalue())
        self.assertEqual((code, receipt['status'], receipt['report']['assigned']), (0, 'frozen', 6))
        Path(command['stdout']).write_text(out.getvalue())
        result = L.aggregate(self.plan_data['plan_file'])
        reported = result['families'][0]
        self.assertEqual((reported['state'], reported['freeze_sha256']), ('reported', receipt['freeze_sha256']))
        self.assertTrue(reported['frozen_controls']['matched'], reported['frozen_controls'])
        self.assertEqual({c['statuses'].get('pending') for c in self.cells(result, 'F1').values()}, {1})
        self.assertEqual(result['construction_implementations'], {'F1': E.digest(IMPLEMENTATION)})
        self.assertNotIn(family['fixture_id'], json.dumps(result['confounds']))

    def test_frozen_controls_that_differ_from_the_plan_are_confounds(self):
        f1, f2 = self.plan_data['families']
        self.freeze(f1)
        other = [dict(self.plan_data['inventory']['rows'][0], digest=hashlib.sha256(b'other').hexdigest())]
        self.freeze(f2, rows=other, implementation={'kind': 'another_build'})
        result = L.aggregate(self.plan_data['plan_file'])
        families = {f['key']: f for f in result['families']}
        self.assertTrue(families['F1']['frozen_controls']['matched'])
        self.assertFalse(families['F2']['frozen_controls']['checks']['inventory'])
        self.assertEqual(result['confounds']['frozen_controls_differ_from_plan'], 1)
        self.assertEqual(result['confounds']['construction_implementation_differs_across_families'], 1)


class ArgumentTests(TempCase):
    def error(self, argv):
        code, out, _ = run(argv + ['--json', '--no-write'] if argv and argv[0] == 'plan' else argv + ['--json'])
        self.assertEqual(code, 2, out)
        return json.loads(out)['error']

    def replace(self, flag, value):
        argv = self.plan_argv()
        if flag in argv:
            argv[argv.index(flag) + 1] = value
        else:
            argv += [flag, value]
        return argv

    def test_invalid_arguments_are_refused(self):
        cases = [('--model', '', 'arguments'), ('--model', 'qwen 0.5b', 'arguments'),
                 ('--node', 'host', 'arguments'), ('--node', 'standby', 'arguments'),
                 ('--node', 'workstation', 'arguments'), ('--node', 'node 04', 'arguments'),
                 ('--budget-seconds', '0', 'arguments'), ('--budget-seconds', '86401', 'arguments'),
                 ('--budget-seconds', 'soon', 'arguments'), ('--max-calls', '0', 'arguments'),
                 ('--max-calls', '10001', 'arguments'), ('--repetitions', '0', 'arguments'),
                 ('--repetitions', '101', 'arguments'), ('--seed', '-1', 'arguments'),
                 ('--digest', DIGEST.upper(), 'arguments'), ('--digest', DIGEST[:63], 'arguments'),
                 ('--digest', 'sha256:' + DIGEST[:63], 'arguments'),
                 ('--families', 'F9', 'families'), ('--families', 'F1,F1', 'families'),
                 ('--families', 'F3..F1', 'families'), ('--families', '', 'families'),
                 ('--root', 'relative/experiments', 'root'), ('--root', str(REPO / 'experiments'), 'root'),
                 ('--root', '/tmp/with space', 'root'), ('--root', '/x', 'root'),
                 ('--plan-dir', str(self.root / 'inside'), 'plan-dir'),
                 ('--plan-dir', str(self.root), 'plan-dir'), ('--tag', 'bad tag', 'tag')]
        for flag, value, expected in cases:
            with self.subTest(flag=flag, value=value):
                self.assertEqual(self.error(self.replace(flag, value))['code'], expected)
        self.assertIn('eligible physical node', self.error(self.replace('--node', 'host'))['message'])
        self.assertEqual(self.error(['plan', '--node', 'node-d'])['code'], 'arguments')
        self.assertEqual(self.error(['aggregate'])['code'], 'arguments')

    def test_execution_is_refused(self):
        for flag in L.REFUSED_FLAGS:
            with self.subTest(flag):
                self.assertEqual(self.error(self.plan_argv(flag))['code'], 'refused_execution')
        self.assertEqual(self.error(['aggregate', '--plan', '/x/y/plan.json', '--run'])['code'], 'refused_execution')

    def test_family_ranges_and_lists(self):
        plan = self.plan('--no-write', families='f1..F3,F6')
        self.assertEqual([f['key'] for f in plan['families']], ['F1', 'F2', 'F3', 'F6'])


class InertTests(unittest.TestCase):
    def test_module_level_is_definitions_and_stdlib_imports_only(self):
        tree = ast.parse(SCRIPT.read_text())
        allowed = {'__future__', 'argparse', 'hashlib', 'json', 'math', 'os', 're', 'shlex', 'stat', 'sys',
                   'collections', 'pathlib'}
        for node in tree.body:
            if isinstance(node, ast.Import):
                self.assertTrue({a.name.split('.')[0] for a in node.names} <= allowed)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module.split('.')[0], allowed)
            elif isinstance(node, ast.If):
                self.assertEqual(ast.unparse(node.test), "__name__ == '__main__'")
            else:
                self.assertIsInstance(node, (ast.Expr, ast.Assign, ast.FunctionDef, ast.ClassDef))
                if isinstance(node, ast.Expr):
                    self.assertIsInstance(node.value, ast.Constant)
        source = SCRIPT.read_text()
        for word in ('subprocess', 'os.system', 'Popen', 'urlopen', 'socket', 'execv'):
            self.assertNotIn(word, source)

    def test_rungs_match_the_benchmark_modes(self):
        self.assertEqual(L.RUNGS, B.MODES)
        self.assertEqual(L.EXCLUDED_NODES, ('host', 'workstation', 'standby'))


if __name__ == '__main__':
    unittest.main()
