"""Private records: exact configuration bytes, durable publication and strict journal reading."""
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.constructor import journal as J
from symblic.constructor import records as R


def config(**changes):
    out = {'version': 1, 'mode': 'linear', 'selection_policy': 'canonical_min_v1',
           'limits': dict(R.DEFAULT_LIMITS), 'runtime': None,
           'implementation': {name: hashlib.sha256(name.encode()).hexdigest() for name in R.IMPLEMENTATION_FILES}}
    out.update(changes)
    return out


def pins(c):
    return {'source_sha256': 'a' * 64, 'input_sha256': 'b' * 64, 'kernel_id': 'kernel.fixture',
            'kind': 'smt_linear', 'mode': c['mode'], 'selection_policy': c['selection_policy'],
            'implementation_sha256': R.implementation_hash(c),
            'worker_sha256': c['implementation'][R.WORKER_FILE],
            'configuration_sha256': R.config_hash(c),
            'allowance': {k: c['limits'][k] for k in ('attempts', 'milliseconds')}}


def request():
    return {'occurrence': 'ask:fixture', 'item': None, 'contract_sha256': '1' * 64,
            'constants_sha256': '2' * 64, 'dependencies_sha256': '3' * 64,
            'limits': {'milliseconds': 1000, 'resource_limit': 10000, 'address_space_bytes': 268435456}}


def fallback():
    return {'disposition': 'unavailable', 'dispatched': False, 'reaped': None, 'status': 'unavailable',
            'reason': 'fixture_no_worker', 'determination': 'unassessed', 'candidates': [],
            'raw_sha256': None, 'effective_limits': None,
            'costs': {'elapsed_ms': 0, 'solver_rlimit': None, 'validation_steps': 0}, 'evidence': None}


def worker_config(**changes):
    """Structurally pinned fake runtime; no such package or interpreter is opened."""
    c = config(**changes)
    c['runtime'] = {'python': '/not/installed/python', 'purelib': '/not/installed/site-packages',
        'python_sha256': 'a' * 64, 'worker_sha256': c['implementation'][R.WORKER_FILE],
        'z3_version': '4.15.4', 'package': {'z3/__init__.py': 'b' * 64}}
    return c


def full_outcome(req, c, disposition='accepted', milliseconds=500):
    fixed = req['limits']; root = c['runtime']['purelib']
    first = fixed['resource_limit'] // 2 or 1
    cpu = (milliseconds + 999) // 1000 + 1
    lifecycle = {'version': 1, 'request_sha256': '4' * 64, 'dispatched': True, 'reaped': True,
                 'capture_complete': True, 'returncode': 0, 'raw_sha256': 'f' * 64,
                 'request_bytes': 10, 'raw_bytes': 5, 'stdout_observed_bytes': 5, 'stderr_observed_bytes': 0,
                 'requested_milliseconds': milliseconds, 'requested_resource_limit': fixed['resource_limit'],
                 'requested_address_space_bytes': fixed['address_space_bytes']}
    limits = {'requested': {'milliseconds': milliseconds, 'rlimit_total': fixed['resource_limit'],
                            'address_space_bytes': fixed['address_space_bytes']},
              'effective_os': {'address_space_bytes': [fixed['address_space_bytes']] * 2,
                               'cpu_seconds': [cpu, cpu], 'file_bytes': [0, 0],
                               'core_bytes': [0, 0], 'open_files': [64, 64]},
              'z3_applied': {'threads': 1, 'random_seed': 0,
                            'allocated_check_rlimits': [first, fixed['resource_limit'] - first]},
              'private_import_root': root, 'loaded_library': root + '/z3/lib/libz3.so'}
    out = fallback()
    out.update(disposition=disposition, dispatched=True, reaped=True,
               status='unsat' if disposition == 'no_candidate' else 'sat', reason=None,
               candidates=[] if disposition == 'no_candidate' else [7], raw_sha256='f' * 64,
               effective_limits=limits, evidence={'lifecycle': lifecycle})
    return out


class Records(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def test_defaults_are_exact_and_validation_detaches(self):
        c = config(); out = R.validate_config(c)
        self.assertEqual(out, c); out['limits']['attempts'] = 1
        self.assertEqual(c['limits']['attempts'], 16)
        self.assertEqual(R.config_hash(c), hashlib.sha256(J.canonical(c).encode('ascii')).hexdigest())

    def test_exact_fields_limits_and_types_refuse(self):
        base = config()
        bad = [{**base, 'extra': 1}, {**base, 'version': True}, {**base, 'mode': 'auto'},
               {**base, 'selection_policy': 'majority'}, {**base, 'implementation': {'evil.py': 'a' * 64}}]
        for key, ceiling in R.LIMIT_CEILINGS.items():
            bad += [{**base, 'limits': {**base['limits'], key: value}} for value in (True, 0, ceiling + 1, 1.0)]
        bad.append({**base, 'limits': {**base['limits'], 'milliseconds': 1}})
        for c in bad:
            with self.subTest(c=c), self.assertRaises(R.RecordsError):
                R.validate_config(c)

    def test_runtime_validation_is_structural_without_opening_paths(self):
        c = config(); c['runtime'] = {'python': '/not/installed/python', 'purelib': '/not/installed/site-packages',
            'python_sha256': 'a' * 64, 'worker_sha256': c['implementation'][R.WORKER_FILE],
            'z3_version': '4.15.4', 'package': {'z3/__init__.py': 'b' * 64}}
        with patch('os.open', side_effect=AssertionError('runtime filesystem access')):
            self.assertEqual(R.validate_config(c), c)
            self.assertTrue(R.config_hash(c))
        for name in ('/absolute', '../outside', 'z3/../outside', 'z3//alias', 'elsewhere/file'):
            wrong = copy.deepcopy(c); wrong['runtime']['package'] = {name: 'b' * 64}
            with self.assertRaises(R.RecordsError):
                R.validate_config(wrong)
        wrong = copy.deepcopy(c); wrong['runtime']['worker_sha256'] = 'c' * 64
        with self.assertRaises(R.RecordsError):
            R.validate_config(wrong)

    def test_text_and_file_bounds_duplicates_noncanonical_and_deep_refuse(self):
        good = J.canonical(config())
        for raw in (' ' + good, good + '\n', '{"version":1,"version":1}', '{"n":NaN}',
                    '{"n":1.0}', '[' * 2000 + '0' + ']' * 2000, 'x' * 65537, 'é'):
            with self.assertRaises(R.RecordsError):
                R.parse_config(raw)
        (self.folder / R.CONFIG_FILE).write_bytes(b'x' * 65537)
        with self.assertRaises(R.RecordsError):
            R.read_config(self.folder)

    def test_create_exact_bytes_mode_and_idempotent_existing_match(self):
        c = config(); self.assertIsNone(R.read_config(self.folder))
        self.assertEqual(R.save_config(self.folder, c), c)
        path = self.folder / R.CONFIG_FILE
        self.assertEqual(path.read_bytes(), J.canonical(c).encode('ascii'))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(R.save_config(self.folder, c), c)
        self.assertEqual(R.read_config(self.folder), c)
        before = path.read_bytes()
        with self.assertRaises(R.RecordsError):
            R.save_config(self.folder, config(mode='linear_diagnose'))
        self.assertEqual(path.read_bytes(), before)

    def test_symlink_and_special_file_refuse_without_target_write(self):
        target = self.folder / 'unrelated'; target.write_text('untouched')
        path = self.folder / R.CONFIG_FILE; path.symlink_to(target)
        for fn in (lambda: R.read_config(self.folder), lambda: R.save_config(self.folder, config())):
            with self.assertRaises(R.RecordsError): fn()
        self.assertEqual(target.read_text(), 'untouched')
        path.unlink(); os.mkfifo(path)
        with self.assertRaises(R.RecordsError): R.read_config(self.folder)

    def test_failed_presync_never_publishes_and_postsync_retry_confirms_durability(self):
        with patch.object(R.os, 'fsync', side_effect=OSError('fixture')):
            with self.assertRaises(R.RecordsError): R.save_config(self.folder, config())
        self.assertFalse((self.folder / R.CONFIG_FILE).exists())
        with patch.object(R, '_sync_folder', side_effect=OSError('fixture')):
            with self.assertRaises(R.RecordsError): R.save_config(self.folder, config())
        self.assertTrue((self.folder / R.CONFIG_FILE).exists())
        with patch.object(R, '_sync_folder', wraps=R._sync_folder) as synced:
            R.save_config(self.folder, config())
            self.assertEqual(synced.call_count, 1)
        self.assertEqual(list(self.folder.glob('.constructor-config-*')), [])

    def test_journal_strict_and_pin_binding_no_rows_skipped(self):
        c = config(); j = J.Journal(str(self.folder), pins(c))
        self.assertIsNone(R.read_journal(self.folder))
        a = j.begin(request())
        with self.assertRaises(R.RecordsError) as caught: R.read_journal(self.folder)
        self.assertEqual(caught.exception.code, 'unresolved')
        j.complete(a, fallback())
        raw = (self.folder / J.FILE).read_text('ascii')
        self.assertEqual(R.read_journal(self.folder), raw)
        state = R.validate_journal(raw)
        self.assertIs(R.bind_journal(state, c, source_sha256='a' * 64, input_sha256='b' * 64,
                                      kernel_id='kernel.fixture'), state)
        with self.assertRaises(R.RecordsError):
            R.bind_journal(state, c, source_sha256='c' * 64, input_sha256='b' * 64, kernel_id='kernel.fixture')
        for bad in ('', raw[:-1], raw + '\n', raw + '{}\n', raw.replace('"seq":1', '"seq":true', 1)):
            with self.assertRaises(R.RecordsError): R.validate_journal(bad)

    def test_fixed_address_space_profile_is_bound(self):
        c = config(); j = J.Journal(str(self.folder), pins(c))
        req = request(); req['limits']['address_space_bytes'] = 128 * 1024 * 1024
        a = j.begin(req); j.complete(a, fallback())
        state = R.validate_journal(R.read_journal(self.folder))
        with self.assertRaises(R.RecordsError):
            R.bind_journal(state, c, source_sha256='a' * 64, input_sha256='b' * 64, kernel_id='kernel.fixture')

    def test_sync_cleanup_cannot_mask_original_baseexception(self):
        class Stop(BaseException): pass
        actual_close = os.close
        def close_and_fail(fd):
            actual_close(fd); raise OSError('close fixture')
        for method in ('folder', 'existing'):
            (self.folder / R.CONFIG_FILE).write_text(J.canonical(config()))
            original = Stop('original')
            with patch.object(R.os, 'fsync', side_effect=original), \
                 patch.object(R.os, 'close', side_effect=close_and_fail):
                with self.assertRaises(Stop) as caught:
                    if method == 'folder': R._sync_folder(self.folder)
                    else: R._sync_existing(self.folder, self.folder / R.CONFIG_FILE)
            self.assertIs(caught.exception, original)
            self.assertTrue(any('Closing' in note for note in original.__notes__))

    def test_save_unlink_and_close_failures_keep_original_stop(self):
        class Stop(BaseException): pass
        original = Stop('original'); actual_close = os.close
        def close_and_fail(fd):
            actual_close(fd); raise OSError('close fixture')
        with patch.object(R.os, 'write', side_effect=original), \
             patch.object(R.os, 'close', side_effect=close_and_fail), \
             patch.object(R.os, 'unlink', side_effect=OSError('unlink fixture')):
            with self.assertRaises(Stop) as caught: R.save_config(self.folder, config())
        self.assertIs(caught.exception, original)
        self.assertEqual(len(original.__notes__), 2)
        self.assertFalse((self.folder / R.CONFIG_FILE).exists())

    def test_journal_lock_cleanup_preserves_primary_stop(self):
        class Stop(BaseException): pass
        (self.folder / J.LOCK_FILE).touch()
        original = Stop('original'); actual_close = os.close
        def close_and_fail(fd):
            actual_close(fd); raise OSError('close fixture')
        with patch.object(R, '_regular_bytes', side_effect=original), \
             patch.object(R.os, 'close', side_effect=close_and_fail):
            with self.assertRaises(Stop) as caught: R.read_journal(self.folder)
        self.assertIs(caught.exception, original)
        self.assertTrue(any('Closing constructor journal lock' in note for note in original.__notes__))

    def test_full_worker_dispositions_validate_without_runtime_filesystem(self):
        for disposition in ('accepted', 'diagnosed', 'no_candidate'):
            c = worker_config(mode='linear_diagnose' if disposition == 'diagnosed' else 'linear')
            req = request(); out = full_outcome(req, c, disposition)
            with self.subTest(disposition=disposition), patch('os.open', side_effect=AssertionError('runtime read')):
                self.assertIs(R.validate_worker_evidence(out, req), True)
                self.assertIs(R.validate_worker_evidence(out, req, c), True)
        c = worker_config(); req = request(); req['limits']['resource_limit'] = 1
        req['limits']['milliseconds'] = 1001
        out = full_outcome(req, c, milliseconds=1001)
        self.assertEqual(out['effective_limits']['z3_applied']['allocated_check_rlimits'], [1, 0])
        self.assertIs(R.validate_worker_evidence(out, req, c), True)

    def test_partial_dispositions_never_claim_full_capture(self):
        self.assertIs(R.validate_worker_evidence(fallback(), request(), config()), False)
        out = fallback(); out.update(disposition='timeout', status='timeout', dispatched=True, reaped=True,
                                     evidence={'lifecycle': {'capture_complete': False}})
        self.assertIs(R.validate_worker_evidence(out, request(), config()), False)
        out['reaped'] = 1
        with self.assertRaises(R.RecordsError): R.validate_worker_evidence(out, request())

    def test_full_worker_receipt_nested_types_hashes_limits_and_runtime_pin_refuse(self):
        c = worker_config(); req = request(); out = full_outcome(req, c)
        cases = []
        for key, values in {
            'version': [True, 2], 'dispatched': [1, False], 'reaped': [1, False],
            'capture_complete': [1, False], 'returncode': [False, 1],
            'request_sha256': [False, '', 'A' * 64], 'raw_sha256': [False, '0' * 64],
            'requested_milliseconds': [True, 0, 1001], 'requested_resource_limit': [True, 9999],
            'requested_address_space_bytes': [True, 128 * 1024 * 1024]}.items():
            for value in values:
                bad = copy.deepcopy(out); bad['evidence']['lifecycle'][key] = value
                cases.append(bad)
        for path, value in [
            (('requested', 'milliseconds'), True), (('requested', 'rlimit_total'), True),
            (('requested', 'address_space_bytes'), True),
            (('effective_os', 'address_space_bytes'), [268435456, 268435455]),
            (('effective_os', 'cpu_seconds'), [2, 3]), (('effective_os', 'file_bytes'), [False, 0]),
            (('effective_os', 'core_bytes'), [0, 1]), (('effective_os', 'open_files'), [64, True]),
            (('z3_applied', 'threads'), True), (('z3_applied', 'random_seed'), False),
            (('z3_applied', 'allocated_check_rlimits'), [5000, 5001]),
            (('z3_applied', 'allocated_check_rlimits'), [True, 9999]),
            (('loaded_library',), '/other/libz3.so'), (('private_import_root',), 'relative'),
            (('extra',), 1)]:
            bad = copy.deepcopy(out); target = bad['effective_limits']
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value; cases.append(bad)
        bad = copy.deepcopy(out); del bad['effective_limits']['effective_os']; cases.append(bad)
        for i, bad in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(R.RecordsError):
                R.validate_worker_evidence(bad, req, c)
        with self.assertRaises(R.RecordsError): R.validate_worker_evidence(out, req, config())
        changed = copy.deepcopy(c); changed['runtime']['purelib'] = '/changed/private/root'
        with self.assertRaises(R.RecordsError): R.validate_worker_evidence(out, req, changed)
        for value in (True, 0, 5001):
            changed = copy.deepcopy(req); changed['limits']['milliseconds'] = value
            with self.assertRaises(R.RecordsError): R.validate_worker_evidence(out, changed, c)
        with self.assertRaises(R.RecordsError): R.validate_worker_evidence({'x': 'a' * 262145}, req, c)

    def test_bind_journal_checks_all_full_worker_dispositions_without_solver_claim(self):
        for disposition in ('accepted', 'diagnosed', 'no_candidate'):
            folder = self.folder / disposition; folder.mkdir()
            c = worker_config(mode='linear_diagnose' if disposition == 'diagnosed' else 'linear')
            req = request(); out = full_outcome(req, c, disposition)
            out['effective_limits']['z3_applied']['threads'] = True
            j = J.Journal(str(folder), pins(c)); a = j.begin(req); j.complete(a, out)
            state = R.validate_journal(R.read_journal(folder))
            with self.subTest(disposition=disposition), self.assertRaises(R.RecordsError):
                R.bind_journal(state, c, source_sha256='a' * 64, input_sha256='b' * 64,
                               kernel_id='kernel.fixture')

    def test_full_capture_counters_are_exact_complete_and_aggregate_bounded(self):
        req = request(); c = worker_config()
        for disposition in ('accepted', 'diagnosed', 'no_candidate'):
            c['mode'] = 'linear_diagnose' if disposition == 'diagnosed' else 'linear'
            out = full_outcome(req, c, disposition)
            self.assertIs(R.validate_worker_evidence(out, req, c), True)
            for key in ('request_bytes', 'raw_bytes', 'stdout_observed_bytes', 'stderr_observed_bytes'):
                for value in (True, -1, 65537, 1.0, None):
                    bad = copy.deepcopy(out); bad['evidence']['lifecycle'][key] = value
                    with self.subTest(disposition=disposition, key=key, value=value), self.assertRaises(R.RecordsError):
                        R.validate_worker_evidence(bad, req, c)
                bad = copy.deepcopy(out); del bad['evidence']['lifecycle'][key]
                with self.subTest(disposition=disposition, missing=key), self.assertRaises(R.RecordsError):
                    R.validate_worker_evidence(bad, req, c)
            for change in ({'request_bytes': 0}, {'raw_bytes': 0}, {'stdout_observed_bytes': 123},
                           {'raw_bytes': 65536, 'stdout_observed_bytes': 65536, 'stderr_observed_bytes': 1},
                           {'unrecognized_future_field': 0}):
                bad = copy.deepcopy(out); bad['evidence']['lifecycle'].update(change)
                with self.subTest(disposition=disposition, change=change), self.assertRaises(R.RecordsError):
                    R.validate_worker_evidence(bad, req, c)
            boundary = copy.deepcopy(out)
            boundary['evidence']['lifecycle'].update(request_bytes=65536, raw_bytes=65535,
                                                     stdout_observed_bytes=65535, stderr_observed_bytes=1)
            self.assertIs(R.validate_worker_evidence(boundary, req, c), True)
        # Missing counters on a partial timeout still make no full-capture claim.
        partial = fallback(); partial.update(disposition='timeout', status='timeout', dispatched=True, reaped=True,
                                            evidence={'lifecycle': {'capture_complete': False}})
        self.assertIs(R.validate_worker_evidence(partial, req), False)


if __name__ == '__main__':
    unittest.main()
