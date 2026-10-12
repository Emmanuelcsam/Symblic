"""Frozen pack lineage with strict private envelopes and unchanged manual fixtures."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.mica import bench as B
from symblic.mica import checkpack as K
from symblic.mica import checkpack_cli as CLI
from symblic.mica import checkpack_link as H
from tests.mica.test_symblic_mica_bench import MODEL, EVALUATOR, result, evaluate
from tests.mica.test_symblic_mica_checkpack import request, declaration, SENTINEL


class CheckPackLinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mica-checkpack-link-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pack = K.freeze(request(), declaration(), EVALUATOR)
        self.fixture = H.linked_fixture(self.pack, expected_sha256=self.pack['sha256'])

    def freeze(self, fixture=None, ident='linked'):
        return B.MicaBenchmark.freeze(self.root, ident, [fixture or self.fixture], model=MODEL,
            budget=self.fixture['request']['budget'], evaluator_identity=EVALUATOR)

    def dispatch(self, bench, runner, evaluator=evaluate):
        return bench.run_assignment(bench.assignments()[0]['id'], runner,
                                   evaluator=evaluator, evaluator_identity=EVALUATOR)

    def replace_sidecar(self, bench, value):
        # Explicit attacker simulation in this test's private temporary store.
        path = bench.path/'checkpacks.json'
        path.unlink()
        B._write(path, value)

    def test_link_rebuilds_full_pack_and_manual_fixture_schema_is_unchanged(self):
        ordinary = K.fixture(self.pack)
        self.assertEqual({k: v for k, v in self.fixture.items() if k != 'checkpack'}, ordinary)
        link = H.validate_fixture(self.fixture, current_checker=EVALUATOR)
        self.assertEqual(link['pack_sha256'], self.pack['sha256'])
        self.assertEqual(link['pack']['original_request'], self.pack['original_request'])
        self.assertEqual(link['pack']['declaration'], self.pack['declaration'])
        linked = self.freeze()
        self.assertEqual(set(B._read(linked.path/'frozen.json')['files']), {'plan.json','hidden.json','checkpacks.json'})
        manual = self.freeze(ordinary, 'manual')
        self.assertEqual(set(B._read(manual.path/'frozen.json')['files']), {'plan.json','hidden.json'})
        self.assertNotIn('checkpack_provenance', manual.report())
        receipt = linked.report()['checkpack_provenance'][0]
        self.assertEqual(receipt['pack_sha256'], self.pack['sha256'])
        self.assertNotIn(SENTINEL, json.dumps(linked.report()))
        self.assertIn('unassessed', receipt['scope'])

    def test_wrong_expected_values_pack_witness_checker_and_extra_fields_refuse(self):
        mutations = []
        changed = copy.deepcopy(self.fixture); changed['hidden_tests'][0][1] = '999'; mutations.append(changed)
        changed = copy.deepcopy(self.fixture); changed['request']['tests'][0]['expected'] = '999'; mutations.append(changed)
        changed = copy.deepcopy(self.fixture); changed['checkpack']['extra'] = True; mutations.append(changed)
        changed = copy.deepcopy(self.fixture); changed['extra'] = True; mutations.append(changed)
        changed = copy.deepcopy(self.fixture); changed['checkpack']['implementation']['extra'] = True
        changed['checkpack']['sha256'] = K.C.digest({k:v for k,v in changed['checkpack'].items() if k != 'sha256'})
        mutations.append(changed)
        changed = copy.deepcopy(self.fixture)
        changed['checkpack']['pack']['declaration']['checks'][0]['requirements'][0]['span']['quote'] = 'invented source'
        mutations.append(changed)
        for index, changed in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises((B.BenchmarkError, ValueError)):
                    self.freeze(changed, 'bad'+str(index))
                self.assertFalse((self.root/('bad'+str(index))/'frozen.json').exists())
        with self.assertRaises(H.LinkError):
            H.validate_fixture(self.fixture, current_checker={'kind':'different'})
        with self.assertRaises(K.CheckPackError):
            H.linked_fixture(self.pack, expected_sha256='f'*64)

    def test_fully_resealed_wrong_fixture_still_cannot_replace_derived_pack_fixture(self):
        changed = copy.deepcopy(self.fixture)
        changed['hidden_tests'][0][1] = '999'
        link = changed['checkpack']
        link['fixture_sha256'] = K.C.digest({k:v for k,v in changed.items() if k != 'checkpack'})
        link['sha256'] = K.C.digest({k:v for k,v in link.items() if k != 'sha256'})
        with self.assertRaises(H.LinkError):
            H.validate_fixture(changed, current_checker=EVALUATOR)

    def test_loaded_helper_source_marker_cannot_be_replaced_by_disk_hash_alone(self):
        with mock.patch.dict(H._symblic_import_identity, {'matched':False}):
            with self.assertRaises(H.LinkError):
                H.linked_fixture(self.pack, expected_sha256=self.pack['sha256'])

    def test_historical_report_uses_retained_pins_but_current_dispatch_refuses_drift(self):
        bench = self.freeze()
        expected = bench.report()
        with mock.patch.object(H, '_identity', side_effect=AssertionError('historical code must not probe current identity')), \
             mock.patch.object(K, '_identity', side_effect=AssertionError('historical code must not probe current generator')):
            self.assertEqual(bench.report(), expected)
        with mock.patch.object(H, '_identity', return_value={'changed':'helper'}):
            with self.assertRaises(B.BenchmarkError):
                self.dispatch(bench, lambda **_: self.fail('must refuse before runner'))

    def test_pre_dispatch_tamper_refuses_without_provider_or_evaluator(self):
        bench = self.freeze()
        data = B._read(bench.path/'checkpacks.json')
        data['links'][self.fixture['id']]['pack_sha256'] = 'f'*64
        self.replace_sidecar(bench, data)
        with self.assertRaises(B.BenchmarkError):
            self.dispatch(bench, lambda **_: self.fail('tampered fixture must not dispatch'))

    def test_tamper_during_runner_prevents_grading_and_unknown_never_redispatches(self):
        bench = self.freeze(); original = B._read(bench.path/'checkpacks.json')
        calls = []
        def runner(**kwargs):
            self.assertNotIn(SENTINEL, json.dumps(kwargs))
            self.assertNotIn('checkpack', json.dumps(kwargs))
            calls.append(kwargs)
            changed = copy.deepcopy(original); changed['version'] = 2
            self.replace_sidecar(bench, changed)
            return result()
        result_row = self.dispatch(bench, runner, lambda *_: self.fail('cannot grade after link corruption'))
        self.assertEqual(result_row['status'], 'unknown')
        self.assertEqual(result_row['reason'], 'checkpack_provenance_revalidation_failed')
        self.assertNotIn('grade', result_row)
        self.replace_sidecar(bench, original)
        replay = self.dispatch(bench, lambda **_: self.fail('cannot replay unknown delivery'))
        self.assertEqual(replay['status'], 'unknown')
        self.assertEqual(len(calls), 1)
        self.assertEqual(bench.report()['completed_receipts'], 0)

    def test_checker_change_after_runner_refuses_before_hidden_grade(self):
        bench = self.freeze(); checks = []
        # Default evaluator identity is deliberately changed between the initial
        # dispatch admission and the immediately pre-grading identity read.
        with mock.patch.object(B, 'js_evaluator_identity', side_effect=[EVALUATOR, {'kind':'drift'}]), \
             mock.patch.object(B, '_js_evaluate', side_effect=AssertionError('no grading')):
            row = bench.run_assignment(bench.assignments()[0]['id'], lambda **kw: checks.append(kw) or result())
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(row['reason'], 'checkpack_provenance_revalidation_failed')
        self.assertEqual(len(checks), 1)

    def test_report_rechecks_link_file_pin_after_loaded_manifest(self):
        bench = self.freeze()
        real_read = B._read
        reads = []
        def read(path):
            value = real_read(path)
            if Path(path).name == 'checkpacks.json':
                reads.append(path)
                if len(reads) == 2:
                    value = copy.deepcopy(value)
                    value['links'][self.fixture['id']]['pack_sha256'] = 'f' * 64
            return value
        with mock.patch.object(B, '_read', side_effect=read):
            with self.assertRaisesRegex(B.BenchmarkError, 'file_pin'):
                bench.report()
        self.assertEqual(len(reads), 2)

    def test_linked_fixture_agent_cli_is_explicit_and_default_fixture_stays_plain(self):
        path = self.root/'pack.json'; path.write_text(json.dumps(self.pack))
        def command(name):
            out = io.StringIO()
            code = CLI.main([name,str(path),'--freeze',self.pack['sha256']], out=out,
                            checker_factory=lambda:EVALUATOR)
            self.assertEqual(code, 0, out.getvalue())
            return json.loads(out.getvalue())
        self.assertEqual(command('fixture'), K.fixture(self.pack))
        linked = command('linked-fixture')
        self.assertEqual(linked, self.fixture)
        self.assertIn(SENTINEL, json.dumps(linked))  # Evaluator-owned file only.
        self.assertNotIn(SENTINEL, json.dumps(command('public')))


if __name__ == '__main__':
    unittest.main()
