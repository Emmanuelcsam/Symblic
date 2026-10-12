"""Constructor-bearing locks: fake/native replay and exact provenance, no solver executable."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import epistemic as EP
from symblic.kernel import evidence as E
from symblic.constructor import journal as J
from symblic.constructor import records as R
from symblic.kernel import lockfile as K
from symblic.kernel import run as SR
from tests.constructor.test_symblic_constructor_records import config, worker_config, pins, request, fallback, full_outcome


SOURCE = 'program ConstructorLock.\nlet n = 7.\nshow n.\n'


class NoModels:
    def call(self, _req):
        raise AssertionError('unexpected provider')


def claim_for(row, req, p, *, change=None):
    native = row['outcome']['evidence']['native_validation']
    ctor = {'version': 1, 'kind': p['kind'], 'mode': p['mode'], 'selection_policy': p['selection_policy'],
            'journal_version': row['v'], 'attempt': row['attempt'], 'attempt_key': row['key'],
            'outcome_sha256': row['sha256'], 'implementation_sha256': p['implementation_sha256'],
            'worker_sha256': p['worker_sha256'], 'configuration_sha256': p['configuration_sha256'],
            'request_sha256': '4' * 64, 'contract_sha256': req['contract_sha256'],
            'selected_index': row['selected'], 'selected_sha256': row['selected_sha256'],
            'native_validation_sha256': E.digest(native), 'kernel_id': p['kernel_id']}
    if change: ctor.update(change)
    content = {'name': 'n', 'name_sha256': hashlib.sha256(b'n').hexdigest(), 'type': 'Int',
               'type_sha256': hashlib.sha256(b'Int').hexdigest(), 'value_sha256': E.digest(7),
               'source_sha256': p['source_sha256'], 'line': 2, 'representation': 'canonical_value_hash_only',
               'constructor': ctor}
    checks = [EP.receipt(subject=content, predicate={'type_sha256': content['type_sha256']},
                         scope='encoded_schema', passed=True, inputs=[])]
    for h in native['predicate_sha256s']:
        predicate = {'kernel': p['kernel_id'], 'source_sha256': p['source_sha256'],
                     'contract_sha256': req['contract_sha256'], 'predicate_sha256': h}
        checks.append(EP.receipt(subject=content, predicate=predicate, scope='encoded_predicate', passed=True, inputs=[]))
    return EP.make_claim('binding:' + E.digest(content)[:48], content, origin='solver_proposal', checks=checks)


class ConstructorLock(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / 'run'; self.folder.mkdir()
        (self.folder / 'program.sym').write_text(SOURCE)
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': {}}))
        self.report = SR.Run(SOURCE, {}, NoModels(), {}, folder=str(self.folder)).execute()
        self.assertEqual(self.report['status'], 'done', self.report.get('error'))
        self.c = worker_config(); self.p = pins(self.c)
        self.p.update(source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
                      input_sha256=E.digest({}), kernel_id=self.report['kernel']['id'])

    def journal(self, accepted=False):
        # Synthetic journal fixtures still declare the exact host policy they
        # represent; an off run plus a linear journal is intentionally invalid.
        options = {'constructor': self.c['mode'], 'constructor_limits': self.c['limits'],
                   'determine': False, 'solve': False}
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': options}))
        R.save_config(self.folder, self.c)
        j = J.Journal(str(self.folder), self.p)
        req = request(); attempt = j.begin(req)
        out = fallback()
        if accepted:
            native = {'version': 1, 'kernel_id': self.p['kernel_id'],
                      'contract_sha256': req['contract_sha256'], 'dependencies_sha256': req['dependencies_sha256'],
                      'schema_sha256': 'a' * 64, 'predicate_sha256s': ['b' * 64],
                      'candidate_sha256s': [E.digest(7)], 'passed': True}
            out = full_outcome(req, self.c)
            out['evidence']['native_validation'] = native
        row = j.complete(attempt, out)['record']
        return row, req

    def solver_report(self, row, req):
        claim = claim_for(row, req, self.p)
        view = EP.evaluate([claim])[claim['id']]
        view['lineage_complete'] = True
        report = copy.deepcopy(self.report)
        report['epistemic'] = {'version': 1, 'empirical_truth': 'not_established',
                               'claims': [claim], 'assessments': [view]}
        report['bindings'][0]['meta']['epistemic'] = {'claim': claim, 'assessment': view,
                                                     'dependency_scope': 'conservative_runtime_reads'}
        self.write_report(report)
        return report

    def write_report(self, report):
        (self.folder / 'state.json').write_text(json.dumps(report))

    def test_ordinary_lock_keeps_version_two_and_exact_old_bytes(self):
        # The lock module as it was before the constructor existed (originally SHA-256 d6baf27e...), with only its
        # imports moved to this package layout; a lock without constructor records must stay byte-identical to it.
        baseline = Path(__file__).parent / 'fixtures/symblic_lock_v2_d6baf27e.py'
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(),
                         'd84137f8710ed330ced911907665165ea19ba5e95b905a2ff444c2cdba47fdfa')
        spec = importlib.util.spec_from_file_location('_lock_before_constructor', baseline)
        old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
        with patch.object(K.time, 'time', return_value=123456.25):
            expected = old.make_lock(str(self.folder)); actual = K.make_lock(str(self.folder))
        self.assertEqual(json.dumps(actual), json.dumps(expected))
        self.assertEqual(actual['symblic_lock'], 2); self.assertNotIn('constructor', actual)
        self.assertTrue(K.replay(actual)['ok'])
        R.save_config(self.folder, self.c)  # An unused configuration alone does not promote the lock.
        with patch.object(K.time, 'time', return_value=123456.25):
            self.assertEqual(K.make_lock(str(self.folder)), expected)

    def test_native_recorded_fallback_replay_uses_recorded_model_only(self):
        from symblic.constructor import core as C
        source = 'ask x: Int "Return seven."\nensure x = 7 else retry.\nshow x.'
        options = {'constructor': 'linear', 'determine': False, 'profile': 'verified',
                   'by': 'fake:seven', 'effort': 'low', 'max_calls': 1}
        folder = self.folder / 'native'; folder.mkdir()
        (folder / 'program.sym').write_text(source)
        (folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': options}))
        class FakeSeven:
            def call(self, _request):
                return {'ok': True, 'json': {'answer': 7}, 'model': 'fake', 'node': 'isolated'}
        with patch.object(C, '_runtime', return_value=None):
            report = SR.Run(source, {}, FakeSeven(), options, folder=str(folder)).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(J.summary(folder)['dispositions'], {'unavailable': 1})
        lock = K.make_lock(str(folder))
        self.assertEqual(lock['symblic_lock'], 3)
        self.assertEqual(lock['constructor']['journal'], (folder / J.FILE).read_text('ascii'))
        self.assertEqual(lock['constructor']['configuration'], (folder / R.CONFIG_FILE).read_text('ascii'))
        path = folder / 'export.lock.json'; K.save_lock(lock, str(path))
        with patch.object(C, '_runtime', side_effect=AssertionError('replay runtime')):
            result = K.replay(K.load_lock(str(path)))
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['constructor_match']); self.assertEqual(result['refused'], [])
        self.assertEqual(result['calls'], 0)

    def test_lock_options_must_match_recorded_constructor_policy(self):
        self.journal()
        lock = K.make_lock(str(self.folder))
        for options in ({}, {'constructor': 'off'}, {'constructor': 'linear', 'determine': True},
                        {'constructor': 'linear_diagnose', 'determine': False},
                        {'constructor': 'linear', 'determine': False,
                         'constructor_limits': {**R.DEFAULT_LIMITS, 'attempts': 1}}):
            with self.subTest(options=options):
                changed = copy.deepcopy(lock); changed['options'] = options
                changed['sha256'] = K.lock_hash(changed)
                with self.assertRaises(K.LockError):
                    K._validate(changed)

    def test_accepted_journal_fake_replay_restores_exact_records_and_options(self):
        row, req = self.journal(accepted=True); report = self.solver_report(row, req)
        lock = K.make_lock(str(self.folder)); observed = {}
        parent = self

        class ReplayReadback:
            def __init__(self, source, inputs, apps, options, *, folder, log):
                observed.update(source=source, inputs=inputs, options=options, folder=folder)
                parent.assertEqual(R.read_journal(folder), lock['constructor']['journal'])
                parent.assertEqual(R.J.canonical(R.read_config(folder)), lock['constructor']['configuration'])
                for name in (R.CONFIG_FILE, J.FILE):
                    parent.assertEqual((Path(folder) / name).stat().st_mode & 0o777, 0o600)
                decision = J.Journal(folder, parent.p, replay=True).lookup(req)
                parent.assertEqual((decision['kind'], decision['value']), ('accepted', 7))

            def execute(self): return copy.deepcopy(report)

        with patch.object(SR, 'Run', ReplayReadback), \
             patch.object(J.Journal, 'begin', side_effect=AssertionError('replay dispatched')), \
             patch.object(J.Journal, 'complete', side_effect=AssertionError('replay wrote outcome')):
            result = K.replay(lock)
        self.assertTrue(result['ok'], result)
        self.assertIs(observed['options']['replay'], True)
        self.assertIs(observed['options']['side_effects'], False)
        self.assertFalse(Path(observed['folder']).exists())

    def test_same_value_changed_origin_lineage_or_outcome_never_matches(self):
        row, req = self.journal(accepted=True); report = self.solver_report(row, req)
        lock = K.make_lock(str(self.folder))
        self.assertTrue(K.drift(lock, report)['same_run'])
        changed = copy.deepcopy(report)
        changed['epistemic']['assessments'][0]['status'] = 'conditional'
        self.assertFalse(K.drift(lock, changed)['constructor_match'])
        model = EP.make_claim('model', report['epistemic']['claims'][0]['content'], origin='model_proposal')
        changed = copy.deepcopy(report)
        view = EP.evaluate([model])[model['id']]
        changed['epistemic'] = {'version': 1, 'empirical_truth': 'not_established', 'claims': [model], 'assessments': [view]}
        changed['bindings'][0]['meta']['epistemic'] = {'claim': model, 'assessment': view,
                                                     'dependency_scope': 'conservative_runtime_reads'}
        result = K.drift(lock, changed)
        self.assertFalse(result['same_run']); self.assertFalse(result['constructor_match'])
        self.assertEqual(result['identical'], result['statements'])  # Value equality is separately visible.

    def test_constructor_identity_bool_int_extra_and_wrong_hash_refuse_even_resealed(self):
        row, req = self.journal(accepted=True)
        state = R.validate_journal(R.read_journal(self.folder))
        good = claim_for(row, req, self.p)
        self.assertEqual(R.validate_solver_claim(good, state), good)
        for change in ({'selected_index': False}, {'version': True}, {'attempt': True},
                       {'outcome_sha256': '0' * 64}, {'request_sha256': '0' * 64},
                       {'configuration_sha256': '0' * 64}, {'native_validation_sha256': '0' * 64},
                       {'replayed': False}):
            with self.subTest(change=change), self.assertRaises(R.RecordsError):
                R.validate_solver_claim(claim_for(row, req, self.p, change=change), state)

    def test_resealed_lifecycle_flags_limits_capture_and_terminal_aliases_refuse(self):
        row, req = self.journal(accepted=True)
        raw = R.read_journal(self.folder)
        for key, value in (('dispatched', 1), ('reaped', 1), ('capture_complete', 1), ('returncode', False),
                           ('returncode', 1), ('raw_sha256', '0' * 64), ('requested_milliseconds', True),
                           ('requested_milliseconds', 1001), ('requested_resource_limit', True),
                           ('requested_resource_limit', 1), ('requested_address_space_bytes', True)):
            # Re-seal all dependent records, so refusal cannot rely on a stale outer digest.
            changed = copy.deepcopy(row); changed['outcome']['evidence']['lifecycle'][key] = value
            changed['sha256'] = J._sha('row', {k: v for k, v in changed.items() if k != 'sha256'})
            altered = '\n'.join(raw.splitlines()[:-1]) + '\n' + J.canonical(changed) + '\n'
            state = R.validate_journal(altered)
            claim = claim_for(changed, req, self.p)
            with self.subTest(key=key, value=value), self.assertRaises(R.RecordsError):
                R.validate_solver_claim(claim, state)
        changed = copy.deepcopy(row)
        changed['outcome']['effective_limits']['requested']['milliseconds'] = True
        changed['sha256'] = J._sha('row', {k: v for k, v in changed.items() if k != 'sha256'})
        altered = '\n'.join(raw.splitlines()[:-1]) + '\n' + J.canonical(changed) + '\n'
        with self.assertRaises(R.RecordsError):
            R.validate_solver_claim(claim_for(changed, req, self.p), R.validate_journal(altered))

    def test_missing_journal_configuration_unresolved_and_symlink_refuse(self):
        row, req = self.journal(accepted=True); self.solver_report(row, req)
        journal = (self.folder / J.FILE).read_bytes(); (self.folder / J.FILE).unlink()
        with self.assertRaises(K.LockError): K.make_lock(str(self.folder))
        (self.folder / J.FILE).write_bytes(journal)
        (self.folder / R.CONFIG_FILE).unlink()
        with self.assertRaises(K.LockError): K.make_lock(str(self.folder))
        target = self.folder / 'unrelated'; target.write_bytes(journal)
        (self.folder / J.FILE).unlink(); (self.folder / J.FILE).symlink_to(target)
        with self.assertRaises(K.LockError): K.make_lock(str(self.folder))

    def test_unresolved_or_repaired_journal_never_exports(self):
        R.save_config(self.folder, self.c); j = J.Journal(str(self.folder), self.p)
        attempt = j.begin(request())
        with self.assertRaises(K.LockError): K.make_lock(str(self.folder))
        j.complete(attempt, fallback())
        torn = b'{"incomplete":'
        with (self.folder / J.FILE).open('ab') as stream: stream.write(torn)
        with self.assertRaises(K.LockError): K.make_lock(str(self.folder))
        J.repair_torn_tail(str(self.folder), hashlib.sha256(torn).hexdigest())
        with self.assertRaisesRegex(K.LockError, 'quarantine packaging'):
            K.make_lock(str(self.folder))

    def test_resealed_input_source_config_pin_and_journal_tampering_refuse(self):
        self.journal(); lock = K.make_lock(str(self.folder))
        for key, value in (('inputs', {'changed': 1}), ('source_sha256', 'c' * 64)):
            bad = copy.deepcopy(lock); bad[key] = value; bad['sha256'] = K.lock_hash(bad)
            with self.assertRaises(K.LockError): K._validate(bad)
        for key, value in (('journal', lock['constructor']['journal'][:-1]),
                           ('journal_sha256', '0' * 64), ('configuration', J.canonical(config(mode='linear_diagnose')))):
            bad = copy.deepcopy(lock); bad['constructor'][key] = value; bad['sha256'] = K.lock_hash(bad)
            with self.assertRaises(K.LockError): K._validate(bad)

    def test_ep_registry_selected_binding_and_bounds_refuse(self):
        row, req = self.journal(accepted=True); self.solver_report(row, req)
        lock = K.make_lock(str(self.folder))
        bad = copy.deepcopy(lock); bad['constructor']['bindings'][0]['hash'] = 'wrong'
        bad['sha256'] = K.lock_hash(bad)
        with self.assertRaises(K.LockError): K._validate(bad)
        bad = copy.deepcopy(lock); bad['constructor']['epistemic']['claims'] *= 2
        bad['constructor']['epistemic']['assessments'] *= 2; bad['sha256'] = K.lock_hash(bad)
        with self.assertRaises(K.LockError): K._validate(bad)
        with patch.object(K, 'MAX_PROVENANCE_BYTES', 1), self.assertRaises(K.LockError): K._validate(lock)
        with patch.object(K, 'MAX_PROVENANCE_ROWS', 0), self.assertRaises(K.LockError): K._validate(lock)

    def test_replay_missing_provenance_or_rewritten_files_is_not_success(self):
        self.journal(); lock = K.make_lock(str(self.folder)); report = self.report
        class DropProvenance:
            def __init__(self, *args, **kwargs): self.folder = kwargs['folder']
            def execute(self):
                result = copy.deepcopy(report); result.pop('epistemic'); return result
        with patch.object(SR, 'Run', DropProvenance):
            result = K.replay(lock)
        self.assertFalse(result['ok']); self.assertFalse(result['constructor_match'])
        class RewriteJournal(DropProvenance):
            def execute(self):
                (Path(self.folder) / J.FILE).write_text('')
                return copy.deepcopy(report)
        with patch.object(SR, 'Run', RewriteJournal):
            result = K.replay(lock)
        self.assertFalse(result['ok']); self.assertFalse(result['constructor_match'])

    def test_restore_cleanup_cannot_mask_original_stop(self):
        class Stop(BaseException): pass
        self.journal(); lock = K.make_lock(str(self.folder))
        destination = self.folder / 'restored'; destination.mkdir()
        actual_close = os.close; original = Stop('original')
        def close_and_fail(fd):
            actual_close(fd); raise OSError('close fixture')
        with patch.object(K.os, 'write', side_effect=original), \
             patch.object(K.os, 'close', side_effect=close_and_fail):
            with self.assertRaises(Stop) as caught:
                K._constructor_restore(lock['constructor'], str(destination))
        self.assertIs(caught.exception, original)
        self.assertTrue(any('Closing restored constructor record' in note for note in original.__notes__))


if __name__ == '__main__':
    unittest.main()
