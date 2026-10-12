import hashlib
import base64
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from symblic.mica import cli as CLI
from symblic.mica import contracts as C
from symblic.mica import routing as R

from symblic.graph import run as G
from symblic.spec import contracts as SC

RUNTIME = {'test': 1}

INVENTORY = [{'engine': 'ollama', 'model': 'test-local:1b', 'node': 'node-d', 'digest': 'a'*64,
              'ready': True, 'available': True, 'context_chars': 24000}]


def request():
    return C.normalize_request({'objective': 'Return input plus one.',
        'requirements': [{'id': 'increment', 'text': 'Return input plus one.', 'acceptance': 'TESTED'}],
        'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
        'tests': [{'requirement_ids': ['increment'], 'call': 'inc(1)', 'expected': '2'}],
        'allowed_outputs': ['result.js'], 'budget': {'max_calls': 4, 'max_candidates': 2}})


def result():
    source = 'function inc(x){return x+1}'
    manifest = script_manifest(source)
    return {'status': 'done', 'output': {'file': 'result.js', 'text': source,
            'sha256': hashlib.sha256(source.encode()).hexdigest(), 'utf8_bytes': len(source.encode())}, 'calls': 1,
            'attempts': [{'id': 'a', 'calls': 1}], 'costs': {'input_tokens': 11},
            'evidence': [], 'assurance': 'TESTED', 'manifest': manifest, 'checks': {'passed': True}}


def script_manifest(source):
    native = SC.plan({'title': 'fixture', 'intro': '', 'shared': '', 'units': [{'names': ['inc'], 'heading': 'inc(x)',
        'body': 'Return input plus one.', 'uses': [], 'setup': '', 'examples': [['inc(1)', '2']]}],
        'template': {'file': 'result.js', 'text': '/*UNITS*/', 'note': ''}})
    ident = native['units'][0]['id']
    artifact = SC.record_artifact(native, ident, source, {}, runtime_identity=RUNTIME,
              checks=[{'scope': 'fixture_host_receipt', 'passed': True, 'subject_sha256': SC.code_hash(source)}])
    return SC.artifact_manifest(native, {ident: artifact}, runtime_identity=RUNTIME)


def calibration():
    """Sealed portable evidence fixture, including legitimate Wilson floats."""
    from symblic.mica import calibration as H
    sha, checker, key = 'c' * 64, G._hash(RUNTIME), 'build-000-increment'
    ident = 'cal/' + sha + '/' + key
    observations = R._observations([{'observation_id': ident, 'engine': 'ollama', 'model': 'test-local:1b',
        'node': 'node-d', 'digest': 'a' * 64, 'task_class': 'javascript_unit', 'status': 'failed',
        'checker_hash': checker, 'contract_hash': 'd' * 64, 'calls': 1, 'cached': False}])
    source = {'kind': 'construction', 'path': '/fixture/explicit-run', 'manifest_sha256': sha,
              'result_sha256': 'e' * 64, 'checker_hash': checker, 'status': 'failed',
              'events_sha256': 'f' * 64, 'event_count': 3, 'event_observations': 1,
              'calls': 1, 'excluded_observations': [], 'seed_calibration_sha256': None, 'seed_observations': 0,
              'native_attempts': [{'attempt': key, 'role': 'construction', 'pins_sha256': '1' * 64,
              'result_sha256': '2' * 64, 'journal_sha256': '3' * 64, 'provider_evidence_sha256': '4' * 64,
              'calls': 1, 'status': 'failed', 'observation_id': ident}]}
    snapshot = G._seal({'kind': 'mica_calibration_snapshot', 'version': 1, 'checker_hash': checker,
        'scope': H.SCOPE, 'sources': [source], 'observations': observations,
        'counts': H._counts([source], observations), 'summary': R.summarize(observations)})
    return H.normalize(snapshot, checker)


def bundle_result():
    """Pure retained-host-receipt fixture; no candidate execution is claimed."""
    from symblic.mica import bundle as B
    req = C.normalize_request({**request(), 'artifact_format': 'javascript_modules',
                               'allowed_outputs': ['package/index.mjs', 'package/inc.mjs']})
    contract = {'contract_id': 'increment', 'root_requirement_ids': ['increment'],
        'objective': 'Return input plus one.', 'output_artifacts': ['package/inc.mjs'],
        'unit': {'names': ['inc'], 'heading': 'inc(x)', 'body': 'Return input plus one.',
                 'uses': [], 'setup': '', 'examples': [['inc(1)', '2']]},
        'verification_obligations': [{'kind': 'unit_examples', 'requirement_ids': ['increment']}]}
    plan = C.validate_plan(req, {'id': 'fixture', 'contracts': [contract]})
    native = plan['spec_plan']; uid = native['units'][0]['id']; code = 'function inc(x){return x+1}'
    artifact = SC.record_artifact(native, uid, code, {}, runtime_identity=RUNTIME,
               checks=[{'scope': 'fixture_host_receipt', 'passed': True, 'subject_sha256': SC.code_hash(code)}])
    manifest = SC.artifact_manifest(native, {uid: artifact}, runtime_identity=RUNTIME)
    req, plan, entry, exports, files = B._build(req, plan, manifest)
    bundle = B._seal({'kind': 'mica_module_bundle', 'version': B.VERSION, 'request': req, 'plan': plan,
        'spec_manifest': manifest, 'source_runtime_sha256': SC.digest(RUNTIME),
        'module_runtime': B._module_runtime(None), 'entry': entry, 'exports': exports, 'files': files,
        'assurance': 'compiled_exact_records_pending_independent_execution', 'scope': B.SCOPE})
    cases = B._cases(bundle)
    checks = B._report(bundle, cases, {'status': 'completed', 'results': [
        {'ok': True, 'value': row['expected']} for row in cases]})
    return {**result(), 'output': manifest['output'], 'manifest': manifest,
            'bundle': bundle, 'module_checks': checks}


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.request_file = self.write('request.json', request())
        self.inventory_file = self.write('inventory.json', INVENTORY)
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        path = self.path / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return str(path)

    def invoke(self, args, **kwargs):
        output = io.StringIO()
        code = CLI.main(args, out=output, **kwargs)
        return code, json.loads(output.getvalue())

    def factory(self, req, directory, inventory):
        outer = self
        class Run:
            def plan(self, mode):
                outer.calls.append(('plan', req, directory, inventory, mode))
                return {'status': 'planned', 'calls': 1}

            def execute(self, mode, initial_plans=None):
                outer.calls.append(('execute', req, directory, inventory, mode, initial_plans))
                return result()
        return Run()

    def make_run(self, *, completed=True):
        folder = self.path / 'native'
        folder.mkdir(mode=0o700)
        manifest = {'version': 1, 'request': request(), 'inventory': R.normalize_inventory(INVENTORY),
                    'mode': 'mica', 'initial_plans': [], 'identity': {'test': 1}, 'started_ms': 1}
        (folder / 'mica-manifest.json').write_text(json.dumps(G._seal(manifest)))
        (folder / 'mica-manifest.json').chmod(0o600)
        if completed:
            outcome = {**result(), 'manifest_sha256': G._hash(manifest)}
            (folder / 'mica-result.json').write_text(json.dumps(G._seal(outcome)))
            (folder / 'mica-result.json').chmod(0o600)
        return folder

    def test_capabilities_and_help_are_json_without_runtime_import(self):
        with patch.dict('sys.modules', {'symblic.mica.search': None, 'symblic.providers.applicators': None}):
            code, value = self.invoke(['capabilities'])
            self.assertEqual(code, 0)
            self.assertEqual(value['commands'], list(CLI.COMMANDS))
            self.assertEqual(value['inventory'], [])
            self.assertIn('root_specification', value)
            self.assertEqual(value['artifact_formats'], list(CLI.FORMATS))
            self.assertIn('calibration', value)
            self.assertEqual(self.invoke(['--help'])[0], 0)
            self.assertEqual(self.invoke(['not-a-command'])[0], 2)

    def test_validate_pure_explicit_request_and_duplicate_key_refusal(self):
        with patch.dict('sys.modules', {'symblic.mica.search': None, 'symblic.providers.applicators': None}):
            code, value = self.invoke(['validate', self.request_file])
        self.assertEqual(code, 0)
        self.assertEqual(value['request'], request())
        malformed = self.path / 'duplicate.json'
        malformed.write_text('{"objective":1,"objective":2}')
        self.assertEqual(self.invoke(['validate', str(malformed)])[1]['error']['code'], 'duplicate_key')

    def test_plan_and_execute_use_same_native_workflow(self):
        folder = str(self.path / 'run')
        for command in ('plan', 'execute'):
            code, value = self.invoke([command, self.request_file, '--dir', folder,
                    '--inventory', self.inventory_file, '--mode', 'search'], runtime_factory=self.factory)
            self.assertEqual(code, 0)
            self.assertEqual(value['status'], 'planned' if command == 'plan' else 'done')
        self.assertEqual([r[0] for r in self.calls], ['plan', 'execute'])
        self.assertTrue(all(r[1] == request() and r[2] == folder and r[4] == 'search' for r in self.calls))

    def test_execution_refuses_missing_readiness_and_an_excluded_node(self):
        with patch.dict('os.environ', {'SYMBLIC_MICA_EXCLUDED_NODES': 'node-x, node-y'}):
            for updates in ({'ready': False}, {'available': False}, {'node': 'node-x'}):
                path = self.write('bad-inventory.json', [{**INVENTORY[0], **updates}])
                code, _ = self.invoke(['execute', self.request_file, '--dir', str(self.path/'run'),
                                       '--inventory', path], runtime_factory=self.factory)
                self.assertEqual(code, 2)
        self.assertFalse(self.calls)

    def test_inventory_snapshot_reads_listings_only_and_names_unnamed_hosts(self):
        from symblic.mica import cli as L
        tags = {'models': [{'name': 'fixture-small:1b', 'digest': 'a' * 64},
                           {'name': 'fixture-other', 'digest': 'not-a-digest'}]}

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Opener:
            def __init__(self):
                self.urls = []

            def open(self, request, timeout):
                self.urls.append(request.full_url)
                return Reply(json.dumps(tags).encode())

        opener = Opener()
        hosts = {'node-a': {'base': 'http://127.0.0.1:9', 'hostport': '127.0.0.1:9'},
                 '127.0.0.1:11434': {'base': 'http://127.0.0.1:11434', 'hostport': '127.0.0.1:11434'}}
        rows, skipped = L.snapshot_inventory(hosts, opener)
        self.assertEqual(opener.urls, ['http://127.0.0.1:9/api/tags'])
        self.assertEqual([(r['model'], r['node'], r['digest']) for r in rows],
                         [('fixture-other', 'node-a', None), ('fixture-small:1b', 'node-a', 'a' * 64)])
        self.assertEqual([s['host'] for s in skipped], ['127.0.0.1:11434'])
        path = self.write('snapshot.json', {'version': 1, 'status': 'snapshot', 'inventory': rows, 'skipped': skipped})
        self.assertEqual(L._inventory(path), rows)

    def test_status_artifacts_verify_hash_and_do_not_run_models(self):
        from symblic.mica import search as M
        folder = self.make_run()
        with patch.dict('sys.modules', {'symblic.providers.applicators': None}), \
                patch.object(M, 'MicaRun', side_effect=AssertionError('reader constructed a runtime')):
            code, value = self.invoke(['status', '--dir', str(folder)])
            self.assertEqual((code, value['status']), (0, 'done'))
            _, artifacts = self.invoke(['artifacts', '--dir', str(folder)])
            self.assertNotIn('text', artifacts['artifacts'][0])
            _, artifacts = self.invoke(['artifacts', '--dir', str(folder), '--include-text'])
            self.assertIn('function inc', artifacts['artifacts'][0]['text'])
        raw = json.loads((folder/'mica-result.json').read_text())
        raw['output']['text'] = 'changed'
        (folder/'mica-result.json').write_text(json.dumps(raw))
        self.assertEqual(self.invoke(['artifacts', '--dir', str(folder)])[0], 2)

    def test_resume_preserves_frozen_request_mode_inventory(self):
        folder = self.make_run(completed=False)
        self.assertEqual(self.invoke(['status', '--dir', str(folder)])[1]['status'], 'incomplete')
        code, value = self.invoke(['resume', '--dir', str(folder)], runtime_factory=self.factory)
        self.assertEqual((code, value['status']), (0, 'done'))
        self.assertEqual(self.calls[0][1], request())
        self.assertEqual(self.calls[0][3], R.normalize_inventory(INVENTORY))
        self.assertEqual(self.calls[0][4:], ('mica', []))

    def test_benchmark_freeze_report_and_exact_control_resume(self):
        fixture = {'id': 'inc', 'family': 'test_inc', 'split': 'heldout', 'request': request(),
                   'hidden_tests': [['inc(893)', '894']]}
        fixture_file = self.write('fixture.json', fixture)
        root = str(self.path/'benchmarks')
        base = ['benchmark', '--root', root, '--id', 'test', '--inventory', self.inventory_file, '--split', 'heldout']
        implementation = {'unit_test': 'pinned-runtime-v1'}
        code, frozen = self.invoke(base + ['--fixture', fixture_file], implementation=implementation)
        self.assertEqual(code, 0)
        self.assertEqual(frozen['status'], 'frozen')
        self.assertEqual(frozen['report']['assigned'], 6)
        pin = frozen['freeze_sha256']
        self.assertFalse(self.calls)
        code, report = self.invoke(['report', '--root', root, '--id', 'test', '--freeze', pin])
        self.assertEqual((code, report['completed_receipts']), (0, 0))
        code, _ = self.invoke(base + ['--freeze', pin], implementation={'unit_test': 'changed'})
        self.assertEqual(code, 2)
        code, evaluated = self.invoke(base + ['--freeze', pin, '--run'], implementation=implementation,
                                       runtime_factory=self.factory)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(evaluated['report']['completed_receipts'], 6)
        self.assertEqual(sum(m['successes'] for m in evaluated['report']['modes'].values()), 6)
        self.assertTrue(all('893' not in json.dumps(call[1]) for call in self.calls))

    def test_json_file_symlink_refused_before_runtime(self):
        link = self.path/'link.json'
        link.symlink_to(self.request_file)
        code, _ = self.invoke(['execute', str(link), '--dir', str(self.path/'run'),
                                '--inventory', self.inventory_file], runtime_factory=self.factory)
        self.assertEqual(code, 2)
        self.assertFalse(self.calls)

    def test_objective_plan_execute_use_project_budget_and_allowed_outputs(self):
        budget_file = self.write('budget.json', {'max_calls': 7, 'wall_seconds': 200})
        objective_file = self.path/'objective.txt'
        objective_file.write_text('Construct a checked arithmetic library.')
        seen = []
        def factory(objective, directory, inventory, budget, outputs):
            seen.append((objective, directory, inventory, budget, outputs))
            return self.factory(request(), directory, inventory)
        for mode in ('plan', 'execute'):
            code, value = self.invoke([mode, '--objective-file', str(objective_file), '--budget', budget_file,
                '--output', 'library.js', '--dir', str(self.path/'project'), '--inventory', self.inventory_file],
                project_factory=factory)
            self.assertEqual(code, 0)
            self.assertIn(value['status'], ('planned', 'done'))
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(row[0] == objective_file.read_text() and row[3]['max_calls'] == 7
                            and row[3]['wall_seconds'] == 200 and row[4] == ['library.js'] for row in seen))
        code, _ = self.invoke(['execute', '--objective', 'Goal', '--dir', str(self.path/'p'),
                                '--inventory', self.inventory_file], project_factory=factory)
        self.assertEqual(code, 2)
        self.assertEqual(len(seen), 2)

    def test_ambiguous_input_and_request_budget_overrides_refused(self):
        base = ['execute', self.request_file, '--dir', str(self.path/'r'), '--inventory', self.inventory_file]
        self.assertEqual(self.invoke(base + ['--objective', 'other'], runtime_factory=self.factory)[0], 2)
        budget = self.write('budget.json', {'max_calls': 999})
        self.assertEqual(self.invoke(base + ['--budget', budget], runtime_factory=self.factory)[0], 2)
        self.assertFalse(self.calls)

    def test_optional_library_is_passed_and_resume_keeps_frozen_path(self):
        seen = []
        def factory(req, directory, inventory, *, library=None):
            seen.append(library)
            return self.factory(req, directory, inventory)
        library = str(self.path/'components')
        code, _ = self.invoke(['execute', self.request_file, '--dir', str(self.path/'r'),
                              '--inventory', self.inventory_file, '--library', library], runtime_factory=factory)
        self.assertEqual(code, 0)
        folder = self.make_run(completed=False)
        raw = json.loads((folder/'mica-manifest.json').read_text())
        body = {k: v for k, v in raw.items() if k != 'sha256'}
        body['library'] = library
        (folder/'mica-manifest.json').write_text(json.dumps(G._seal(body)))
        self.assertEqual(self.invoke(['resume', '--dir', str(folder)], runtime_factory=factory)[0], 0)
        self.assertEqual(seen, [library, library])

    def test_nonfinite_callback_result_still_produces_json_error(self):
        class Broken:
            def execute(self, **_):
                return {**result(), 'costs': {'latency_ms': float('nan')}}
        code, value = self.invoke(['execute', self.request_file, '--dir', str(self.path/'r'),
            '--inventory', self.inventory_file], runtime_factory=lambda *_: Broken())
        self.assertEqual((code, value['error']['code']), (2, 'invalid_result'))

    def test_initial_plan_is_validated_forwarded_and_retained_exactly_on_resume(self):
        plan = {'id': 'explicit', 'contracts': [{
            'contract_id': 'increment', 'root_requirement_ids': ['increment'],
            'objective': 'Return input plus one.',
            'unit': {'names': ['inc'], 'heading': 'inc(x)', 'body': 'Return input plus one.',
                     'uses': [], 'setup': '', 'examples': [['inc(1)', '2']]},
            'verification_obligations': [{'kind': 'unit_examples', 'requirement_ids': ['increment']}]}]}
        expected = [C.validate_plan(request(), plan)]
        path = self.write('plan.json', plan)
        inventory_file = self.write('empty-inventory.json', [])
        code, _ = self.invoke(['execute', self.request_file, '--initial-plan', path,
                              '--dir', str(self.path/'explicit'), '--inventory', inventory_file],
                             runtime_factory=self.factory)
        self.assertEqual(code, 0)
        self.assertEqual(self.calls[0][0], 'execute')
        self.assertEqual(self.calls[0][-1], expected)
        self.assertEqual(self.calls[0][3], [])
        folder = self.make_run(completed=False)
        raw = json.loads((folder/'mica-manifest.json').read_text())
        manifest = {k: v for k, v in raw.items() if k != 'sha256'}
        manifest['initial_plans'] = expected
        (folder/'mica-manifest.json').write_text(json.dumps(G._seal(manifest)))
        self.assertEqual(self.invoke(['resume', '--dir', str(folder)], runtime_factory=self.factory)[0], 0)
        self.assertEqual(self.calls[1][-1], expected)
        self.assertEqual([row[0] for row in self.calls], ['execute', 'execute'])

    def test_initial_plan_cannot_replace_objective_or_bypass_requirement_validation(self):
        bad = self.write('bad-plan.json', {'id': 'wrong', 'contracts': []})
        args = ['execute', self.request_file, '--initial-plan', bad,
                '--dir', str(self.path/'explicit'), '--inventory', self.inventory_file]
        self.assertEqual(self.invoke(args, runtime_factory=self.factory)[0], 2)
        budget = self.write('budget.json', request()['budget'])
        args = ['execute', '--objective', 'Return input plus one.', '--budget', budget,
                '--initial-plan', bad, '--dir', str(self.path/'p'), '--inventory', self.inventory_file]
        code, error = self.invoke(args, runtime_factory=self.factory)
        self.assertEqual((code, error['error']['code']), (2, 'initial_plan_authority'))
        self.assertFalse(self.calls)


    def test_calibration_command_is_explicit_read_only_and_requires_selected_runs(self):
        from symblic.mica import calibration as H
        expected = calibration()
        with patch.object(H, 'freeze', return_value=expected) as freeze, \
                patch.object(CLI, '_applications', side_effect=AssertionError('unexpected provider')):
            code, output = self.invoke(['calibration', '--run', '/fixture/one', '--run', '/fixture/two'])
        self.assertEqual((code, output), (0, expected))
        freeze.assert_called_once_with(['/fixture/one', '/fixture/two'])
        self.assertEqual(self.invoke(['calibration'])[0], 2)

    def test_calibration_file_is_checked_and_exact_seed_survives_resume(self):
        from symblic.mica import search as M
        seed = calibration(); seed_file = self.write('calibration.json', seed); seen = []
        def factory(req, directory, inventory, **options):
            seen.append(options)
            return self.factory(req, directory, inventory)
        args = ['execute', self.request_file, '--dir', str(self.path/'r'),
                '--inventory', self.inventory_file, '--calibration', seed_file]
        with patch.object(M, 'implementation_identity', return_value=RUNTIME):
            self.assertEqual(self.invoke(args, runtime_factory=factory)[0], 0)
        folder = self.make_run(completed=False)
        manifest = G._read(folder/'mica-manifest.json'); manifest.pop('sha256'); manifest['calibration'] = seed
        (folder/'mica-manifest.json').write_text(json.dumps(G._seal(manifest)))
        self.assertEqual(self.invoke(['resume', '--dir', str(folder)], runtime_factory=factory)[0], 0)
        self.assertEqual(seen, [{'calibration': seed}, {'calibration': seed}])
        with patch.object(M, 'implementation_identity', return_value={'changed': True}):
            self.assertEqual(self.invoke(args, runtime_factory=factory)[0], 2)
        self.assertEqual(len(seen), 2)

    def test_objective_format_is_frozen_and_explicit_request_overrides_refuse(self):
        seen = []
        def project(objective, directory, inventory, budget, outputs, **options):
            seen.append((objective, outputs, options))
            return self.factory(request(), directory, inventory)
        budget = self.write('budget.json', request()['budget'])
        args = ['execute', '--objective', 'Build a module library.', '--format', 'javascript_modules',
                '--budget', budget, '--inventory', self.inventory_file, '--dir', str(self.path/'project')]
        self.assertEqual(self.invoke(args, project_factory=project)[0], 0)
        self.assertEqual(seen[0][1:], (['index.mjs'], {'artifact_format': 'javascript_modules'}))
        frozen = {'version': 1, 'objective': seen[0][0], 'budget': request()['budget'],
                  'allowed_outputs': ['index.mjs'], 'inventory': R.normalize_inventory(INVENTORY),
                  'mode': 'mica', 'artifact_format': 'javascript_modules', 'library': None, 'calibration': None}
        folder = self.path/'project'; folder.mkdir()
        (folder/'project-manifest.json').write_text(json.dumps(G._seal(frozen)))
        self.assertEqual(self.invoke(['resume', '--dir', str(folder)], project_factory=project)[0], 0)
        self.assertEqual(seen[0], seen[1])
        explicit = ['execute', self.request_file, '--format', 'javascript_script',
                    '--inventory', self.inventory_file, '--dir', str(self.path/'r')]
        self.assertEqual(self.invoke(explicit, runtime_factory=self.factory)[0], 2)

    def test_module_artifacts_verify_all_files_and_explicit_archive_without_path_writes(self):
        from symblic.mica import search as M
        from symblic.mica import bundle as B
        with patch.object(B, 'asset_snapshot', return_value={'fixture': b'exact trusted asset'}), \
                patch.object(M, 'implementation_identity', return_value=RUNTIME):
            value = bundle_result(); folder = self.make_run()
            manifest = G._read(folder/'mica-manifest.json'); manifest.pop('sha256')
            manifest['request'] = value['bundle']['request']
            (folder/'mica-manifest.json').write_text(json.dumps(G._seal(manifest)))
            value['manifest_sha256'] = G._hash(manifest)
            (folder/'mica-result.json').write_text(json.dumps(G._seal(value)))
            code, summary = self.invoke(['artifacts', '--dir', str(folder)])
            self.assertEqual(code, 0, summary)
            self.assertEqual(len(summary['artifacts']), 2)
            self.assertNotIn('archive', summary)
            self.assertTrue(all('text' not in row for row in summary['artifacts']))
            code, output = self.invoke(['artifacts', '--dir', str(folder), '--include-text', '--archive'])
            self.assertEqual(code, 0, output)
            raw = base64.b64decode(output['archive']['base64'])
            self.assertEqual(output['archive']['sha256'], hashlib.sha256(raw).hexdigest())
            with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
                self.assertEqual(set(zipped.namelist()), {row['file'] for row in output['artifacts']})
                for row in output['artifacts']:
                    self.assertEqual(zipped.read(row['file']), row['text'].encode())
            self.assertFalse((folder/'package').exists())
            value['module_checks']['module_checks'].pop()
            (folder/'mica-result.json').write_text(json.dumps(G._seal(value)))
            self.assertEqual(self.invoke(['artifacts', '--dir', str(folder), '--archive'])[0], 2)


if __name__ == '__main__':
    unittest.main()
