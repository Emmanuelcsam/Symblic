"""Execution receipt boundaries: isolated stores, fake hosts, no providers."""
import copy
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import effects as FX
from symblic.kernel import execution_pins as X
from symblic.lang import abstraction as L
from symblic.kernel.run import Run

ROW = {'name': 'fixture.read', 'effect': 'read', 'policy': 'auto', 'params': {'type': 'object',
       'properties': {}, 'additionalProperties': False}, 'untrusted': False, 'sensitivity': 'public',
       'instructs': False, 'egress': False}
EFFECT_SOURCE = 'observe x = fixture.read().\nshow x.text.\n'


def reviewed(libraries=()):
    names = sorted(X.REQUIRED_FILES) + ['symblic/lang/library/' + n + '.sym' for n in libraries]
    return {name: hashlib.sha256((X.BASE / name).read_bytes()).hexdigest() for name in names}


def reseal(pins):
    # A digest is integrity, not authorization: tests may recompute it to reach
    # the independent schema, runtime, input and capability checks beneath it.
    pins['sha256'] = hashlib.sha256(json.dumps({k: v for k, v in pins.items() if k != 'sha256'},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


class Host:
    idempotent_by_id = True

    def __init__(self, rows=None):
        self.rows = copy.deepcopy([ROW] if rows is None else rows)
        self.reads, self.calls = 0, []

    def catalogue(self):
        self.reads += 1
        return copy.deepcopy(self.rows)

    def perform(self, effect, stop):
        self.calls.append(effect)
        return {'status': 'done', 'result': {'text': 'fixture result', 'data': None}}


class Apps:
    def __init__(self):
        self.calls = []

    def call(self, request):
        self.calls.append(request)
        raise AssertionError('No provider is allowed in these tests')


class ExecutionPins(unittest.TestCase):
    def failed_before_execution(self, source, pins, inputs=None, host=None):
        apps = Apps()
        report = Run(source, inputs, apps, {'execution_pins': pins, 'effects': host}).execute()
        self.assertEqual('failed', report['status'], report)
        self.assertEqual('SYM_VERSION', report['error']['code'], report)
        self.assertEqual([], apps.calls)
        self.assertEqual([], report['bindings'])
        if host:
            self.assertEqual([], host.calls)
        return report

    def test_kernel_only_runs_without_host_and_detaches_nested_inputs(self):
        source = 'given x: Any.\nshow x.\n'
        inputs = {'x': {'a': [1, True, None, ' e\u0301 ']}}
        pins = X.build(source, inputs, reviewed())
        run = Run(source, inputs, Apps(), {'execution_pins': pins})
        report = run.execute()
        self.assertEqual('done', report['status'], report)
        self.assertEqual(0, report['calls'])
        self.assertIsNot(run.inputs['x'], inputs['x'])

    def test_raw_source_and_typed_json_inputs_are_exact(self):
        source = 'given x: Any.\nshow x.\n'
        pins = X.build(source, {'x': 1}, reviewed())
        for inputs in ({'x': True}, {'x': 1.0}, {'x': '1'}):
            with self.subTest(inputs=inputs):
                self.failed_before_execution(source, pins, inputs)
        self.failed_before_execution(source + '\n', pins, {'x': 1})

    def test_malformed_or_tampered_receipts_fail_closed(self):
        source = 'show 5.\n'
        pins = X.build(source, {}, reviewed())
        for bad in (None, False, {}, [], {'version': True}, {**pins, 'extra': 1}):
            self.failed_before_execution(source, bad)
        for field, value in [('version', True), ('kernel_id', 'wrong'), ('source_sha256', '0'*64),
                             ('input_sha256', '0'*64)]:
            bad = copy.deepcopy(pins); bad[field] = value; reseal(bad)
            self.failed_before_execution(source, bad)

    def test_build_rejects_non_json_inputs_and_resource_overruns(self):
        for value in ({'x': float('nan')}, {'x': float('inf')}, {1: 'key'}, {'x': (1,)}, {'x': object()}):
            with self.subTest(value=str(value)), self.assertRaises(S.SymblicError):
                X.build('show 5.\n', value, reviewed())
        nested = []
        for _ in range(X.MAX_DEPTH + 2): nested = [nested]
        with self.assertRaises(S.SymblicError): X.snapshot_inputs({'x': nested})
        with patch.object(X, 'MAX_NODES', 5), self.assertRaises(S.SymblicError):
            X.snapshot_inputs({'x': list(range(10))})
        with patch.object(X, 'MAX_BYTES', 100), self.assertRaises(S.SymblicError):
            X.snapshot_inputs({'x': ['a'*60, 'a'*60]})

    def test_fixed_file_registry_and_mandatory_core_hashes(self):
        hashes = reviewed()
        for name in ('../secrets', '/etc/passwd', 'symblic/lang/library/../outside.sym', 'unknown.py'):
            bad = {**hashes, name: '0'*64}
            with self.subTest(name=name), self.assertRaises(S.SymblicError):
                X.build('show 5.\n', {}, bad)
        del hashes['symblic/kernel/language.py']
        with self.assertRaises(S.SymblicError): X.build('show 5.\n', {}, hashes)

    def test_disk_change_refuses_before_even_an_earlier_ask(self):
        source = 'ask x: Number "fixture" by "fake:test".\n'
        pins = X.build(source, {}, reviewed())
        read = X._read
        with patch.object(X, '_read', side_effect=lambda name: b'changed' if name == 'symblic/kernel/run.py' else read(name)):
            self.failed_before_execution(source, pins)

    def test_numeric_transport_implementation_is_required_and_cannot_drift_before_execution(self):
        self.assertIn('symblic/adapters/transport.py', X.REQUIRED_FILES)
        hashes = reviewed()
        with self.assertRaises(S.SymblicError):
            X.build('show 1.\n', {}, {n: h for n, h in hashes.items() if n != 'symblic/adapters/transport.py'})
        source = 'ask x: Number "fixture" by "fake:test".\n'
        pins = X.build(source, {}, hashes)
        read = X._read
        with patch.object(X, '_read', side_effect=lambda name: b'changed' if name == 'symblic/adapters/transport.py' else read(name)):
            self.failed_before_execution(source, pins)

    def test_old_process_cannot_bless_current_disk_hashes(self):
        source = 'show 5.\n'
        pins = X.build(source, {}, reviewed())
        for runtime in (None, {**X._RUNTIME, 'symblic/kernel/language.py': '0'*64}):
            with patch.object(X, '_RUNTIME', runtime):
                self.failed_before_execution(source, pins)
                with self.assertRaises(S.SymblicError): X.build(source, {}, reviewed())
        with patch.object(X, '_RUNTIME', None), patch.object(S, '_EXECUTION_CAPTURE_PENDING', False), \
                self.assertRaises(S.SymblicError):
            X.capture_runtime()

    def test_standard_library_uses_snapshot_never_changed_live_source(self):
        source = 'import units.\nlet answer = convert_length(2, "inch", "cm").\nshow answer.\n'
        pins = X.build(source, {}, reviewed(['units']))
        with tempfile.TemporaryDirectory() as folder:
            # A stale/tampered prior module record cannot override the receipt.
            Path(folder, 'modules.json').write_text(json.dumps({'lib:units': {
                'source': 'function convert_length(x, a, b) = 999.\n', 'sha256': '0'*64}}))
            with patch.object(L, 'library_source', side_effect=AssertionError('No live library read')):
                report = Run(source, {}, Apps(), {'execution_pins': pins}, folder=folder).execute()
        self.assertEqual('done', report['status'], report)
        self.assertEqual('5.08', next(b['value'] for b in report['bindings'] if b['name'] == 'answer'))

    def test_captured_library_corruption_refuses_even_after_resealing(self):
        source = 'import units.\nshow convert_length(1, "inch", "cm").\n'
        pins = X.build(source, {}, reviewed(['units']))
        pins['libraries']['units']['source'] += '\n'
        reseal(pins)
        self.failed_before_execution(source, pins)

    def test_all_standard_modules_capture_and_nested_lab_imports(self):
        pins = X.build('import lab.\nshow additive_dry_basis(100, 1).\n', {}, reviewed(X.LIBRARIES))
        report = Run('import lab.\nshow additive_dry_basis(100, 1).\n', {}, Apps(), {'execution_pins': pins}).execute()
        self.assertEqual('done', report['status'], report)
        self.assertEqual(set(X.LIBRARIES), set(pins['libraries']))

    def test_saved_and_unpinned_imports_refuse_at_build(self):
        for source in ('import "Fixture".\nshow 1.\n', 'import units.\nshow 1.\n'):
            with self.subTest(source=source), self.assertRaises(S.SymblicError):
                X.build(source, {}, reviewed())

    def test_import_after_effect_is_rejected_before_dispatch(self):
        source = EFFECT_SOURCE + 'import "Fixture".\n'
        pins = X.build(EFFECT_SOURCE, {}, reviewed(), capabilities=[ROW])
        pins['source_sha256'] = hashlib.sha256(source.encode()).hexdigest(); reseal(pins)
        self.failed_before_execution(source, pins, host=Host())

    def test_effect_contract_matching_and_single_metadata_lookup(self):
        host = Host()
        pins = X.build(EFFECT_SOURCE, {}, reviewed(), capabilities=[ROW])
        report = Run(EFFECT_SOURCE, {}, Apps(), {'execution_pins': pins, 'effects': host}).execute()
        self.assertEqual('done', report['status'], report)
        self.assertEqual(1, host.reads)
        self.assertEqual(1, len(host.calls))

    def test_legacy_unaddressable_tool_does_not_block_but_duplicate_capability_does(self):
        legacy = {**ROW, 'name': 'calc'}
        pins = X.build(EFFECT_SOURCE, {}, reviewed(), capabilities=[ROW, legacy])
        self.assertEqual({'fixture.read'}, set(pins['capabilities']))
        host = Host([ROW, legacy])
        report = Run(EFFECT_SOURCE, {}, Apps(), {'execution_pins': pins, 'effects': host}).execute()
        self.assertEqual('done', report['status'], report)
        self.assertEqual(1, len(host.calls))
        self.failed_before_execution(EFFECT_SOURCE, pins, host=Host([ROW, ROW, legacy]))

    def test_changed_egress_instructs_or_params_refuses_before_ask(self):
        source = 'ask n: Number "fixture" by "fake:test".\n' + EFFECT_SOURCE
        pins = X.build(source, {}, reviewed(), capabilities=[ROW])
        for key, value in [('egress', True), ('instructs', True), ('policy', 'confirm'),
                           ('params', {'type': 'object', 'required': ['new']})]:
            with self.subTest(key=key):
                self.failed_before_execution(source, pins, host=Host([{**ROW, key: value}]))

    def test_missing_used_contract_and_unavailable_host_refuse(self):
        with self.assertRaises(S.SymblicError): X.build(EFFECT_SOURCE, {}, reviewed())
        pins = X.build(EFFECT_SOURCE, {}, reviewed(), capabilities=[ROW])
        self.failed_before_execution(EFFECT_SOURCE, pins)
        self.failed_before_execution(EFFECT_SOURCE, pins, host=Host([]))

    def test_replay_uses_only_recorded_matching_catalogue(self):
        host = Host()
        pins = X.build(EFFECT_SOURCE, {}, reviewed(), capabilities=[ROW])
        with tempfile.TemporaryDirectory() as folder:
            first = Run(EFFECT_SOURCE, {}, Apps(), {'execution_pins': pins, 'effects': host}, folder=folder).execute()
            self.assertEqual('done', first['status'], first)
            with patch.object(host, 'catalogue', side_effect=AssertionError('No host metadata on replay')), \
                    patch.object(host, 'perform', side_effect=AssertionError('No effect on replay')):
                replay = Run(EFFECT_SOURCE, {}, Apps(), {'execution_pins': pins, 'effects': host, 'replay': True}, folder=folder).execute()
            self.assertEqual('done', replay['status'], replay)
            frozen_path = Path(folder, FX.CATALOGUE_FILE)
            frozen = json.loads(frozen_path.read_text())
            frozen['capabilities']['fixture.read']['instructs'] = True
            frozen_path.write_text(json.dumps(frozen))
            refused = Run(EFFECT_SOURCE, {}, Apps(), {'execution_pins': pins, 'replay': True}, folder=folder).execute()
            self.assertEqual('SYM_VERSION', refused['error']['code'], refused)
        self.assertEqual(1, len(host.calls))

    def test_replay_missing_catalogue_refuses_without_host_probe(self):
        pins = X.build(EFFECT_SOURCE, {}, reviewed(), capabilities=[ROW])
        host = Host()
        with tempfile.TemporaryDirectory() as folder:
            report = Run(EFFECT_SOURCE, {}, Apps(), {'execution_pins': pins, 'replay': True,
                                                   'effects': host}, folder=folder).execute()
        self.assertEqual('SYM_VERSION', report['error']['code'], report)
        self.assertEqual((0, []), (host.reads, host.calls))

    def test_core_first_and_helper_first_in_fresh_processes(self):
        for imports in ('import symblic.kernel.language as S; import symblic.kernel.execution_pins as X',
                        'import symblic.kernel.execution_pins as X; import symblic.kernel.language as S'):
            code = imports + '; assert X._RUNTIME is not None; assert not S._EXECUTION_CAPTURE_PENDING'
            with self.subTest(imports=imports):
                result = subprocess.run([sys.executable, '-c', code], cwd=X.BASE, capture_output=True, text=True,
                                        timeout=120, check=False)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_same_size_timestamp_and_unchecked_hash_bytecode_cannot_bless_changed_source(self):
        for mode in (py_compile.PycInvalidationMode.TIMESTAMP, py_compile.PycInvalidationMode.UNCHECKED_HASH,
                     py_compile.PycInvalidationMode.CHECKED_HASH):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                target = Path(folder)
                shutil.copytree(X.BASE / 'symblic', target / 'symblic',
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                core = target / 'symblic/kernel/language.py'
                py_compile.compile(str(core), doraise=True, invalidation_mode=mode)
                stat = core.stat()
                source = core.read_text()
                self.assertIn('MAX_SOURCE = 400_000', source)
                core.write_text(source.replace('MAX_SOURCE = 400_000', 'MAX_SOURCE = 400_001', 1))
                os.utime(core, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                code = '''import hashlib
from symblic.kernel import language as S, execution_pins as X
hashes = {name: hashlib.sha256((X.BASE/name).read_bytes()).hexdigest() for name in X.REQUIRED_FILES}
try:
    X.build('show 5.\\n', {}, hashes)
except S.SymblicError as e:
    assert e.kind == 'version' and 'bytecode' in e.message, e
    print('refused')
else:
    assert S.MAX_SOURCE == 400001
    print('fresh source')
'''
                result = subprocess.run([sys.executable, '-c', code], cwd=folder, capture_output=True,
                                        text=True, timeout=180, check=False)     # a cold compile on a busy machine
                self.assertEqual(0, result.returncode, result.stderr)
                expected = 'fresh source' if mode == py_compile.PycInvalidationMode.CHECKED_HASH else 'refused'
                self.assertEqual(expected, result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
