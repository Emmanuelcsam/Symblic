"""symblic_lock: freeze a finished run, replay it with no model, detect edits and measure drift. Fake
applicators and temporary folders only."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S
from symblic.lang import abstraction as L
from symblic.kernel import lockfile as K
from symblic.kernel import run as SR

PROGRAM = '''program Locked.
import units.
routine colour_of(thing: Text) -> one of {red, green, yellow} with effort=high do
  ask c: one of {red, green, yellow} "What colour is {thing}?"
  return c.
end.
given thing: Text = "banana".
let c1 = colour_of(thing).
let cm = convert_length(2, "inch", "cm").
ask n: Int in 1..10 "How many letters are in the word 'red'?"
show [c1, cm, n].
'''


class FakeApps:
    def __init__(self, answer):
        self.answer, self.reqs, self.lock = answer, [], threading.Lock()

    def call(self, req):
        with self.lock:
            self.reqs.append(req)
        return {'ok': True, 'json': self.answer(req['prompt']), 'ms': 1}


def answer_with(colour):
    return lambda p: {'answer': colour if 'colour' in p else 3}


class Lock(unittest.TestCase):
    def setUp(self):
        L.register()
        self.tmp = tempfile.mkdtemp()
        self.folder = os.path.join(self.tmp, 'run')
        os.makedirs(self.folder)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def finished_run(self, source=PROGRAM, colour='yellow', inputs=None):
        with open(os.path.join(self.folder, 'program.sym'), 'w') as f:
            f.write(source)
        with open(os.path.join(self.folder, 'meta.json'), 'w') as f:
            json.dump({'inputs': inputs or {}, 'options': {'by': 'fake:a'}}, f)
        apps = FakeApps(answer_with(colour))
        run = SR.Run(source, inputs or {}, apps, {'by': 'fake:a'}, folder=self.folder)
        return run.execute(), apps

    def test_lock_replays_exactly_with_no_model(self):
        rep, apps = self.finished_run()
        self.assertEqual(rep['status'], 'done', rep['error'])
        self.assertEqual(len(apps.reqs), 3 + 1)                     # effort=high in the routine, then n
        lock = K.make_lock(self.folder)
        self.assertEqual(lock['fingerprint'], rep['fingerprint'])
        names = [s['name'] for s in lock['statements']]
        self.assertIn('length_in_m', names)                          # import units binds its constants
        self.assertEqual([n for n in names if n in ('thing', 'c1', 'cm', 'n')], ['thing', 'c1', 'cm', 'n'])
        self.assertEqual(next(s for s in lock['statements'] if s['name'] == 'c1')['class'], 'closed')
        self.assertIn('lib:units', lock['modules'])
        path = os.path.join(self.tmp, 'locked.lock.json')
        K.save_lock(lock, path)
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), '0o600')
        again = K.load_lock(path)
        res = K.replay(again, source=PROGRAM)
        self.assertTrue(res['ok'], res)
        self.assertEqual((res['calls'], res['refused']), (0, []))
        self.assertEqual(res['fingerprint'], rep['fingerprint'])

    def test_a_replay_never_reaches_a_model(self):
        self.finished_run()
        lock = K.make_lock(self.folder)
        lock['calls'] = lock['calls'][:-1]                           # one answer missing
        lock['sha256'] = K.lock_hash(lock)                           # a valid, incomplete record
        res = K.replay(lock)
        self.assertFalse(res['ok'])
        self.assertEqual(len(res['refused']), 1)

    def test_edits_and_other_programs_are_refused(self):
        self.finished_run()
        lock = K.make_lock(self.folder)
        path = os.path.join(self.tmp, 'l.json')
        K.save_lock(lock, path)
        with open(path) as f:
            data = json.load(f)
        data['fingerprint'] = '0' * 16
        with open(path, 'w') as f:
            json.dump(data, f)
        with self.assertRaises(K.LockError):
            K.load_lock(path)
        with self.assertRaises(K.LockError):
            K.replay(lock, source=PROGRAM + 'show 1.\n')

    def test_an_unfinished_run_cannot_be_locked(self):
        rep, _ = self.finished_run(source='ask n: Int "Count." with by="fake:a"\nassert n = 99.\n')
        self.assertEqual(rep['status'], 'failed')
        with self.assertRaises(K.LockError):
            K.make_lock(self.folder)

    def test_drift_shows_what_new_agents_answered_differently(self):
        self.finished_run(colour='yellow')
        lock = K.make_lock(self.folder)
        fresh = SR.Run(PROGRAM, {}, FakeApps(answer_with('green')), {'by': 'fake:b'}).execute()
        d = K.drift(lock, fresh)
        self.assertFalse(d['same_run'])
        changed = {r['name'] for r in d['changed']}
        self.assertIn('c1', changed)
        self.assertNotIn('cm', changed)                             # exact: the kernel's, never drifts
        self.assertEqual(d['model_statements'], 2)
        self.assertEqual(d['model_identical'], 1)                    # n still agrees
        same = SR.Run(PROGRAM, {}, FakeApps(answer_with('yellow')), {'by': 'fake:c'}).execute()
        self.assertTrue(K.drift(lock, same)['same_run'])

    def test_the_lock_keeps_the_module_the_run_used(self):
        saved = {'Lib': 'function bump(x) = x + 1.\n'}
        old = L.saved_source
        L.saved_source = lambda name: saved.get(name)
        try:
            rep, _ = self.finished_run(source='import "Lib".\nlet y = bump(1).\nshow y.\n')
            self.assertEqual(rep['status'], 'done', rep['error'])
            lock = K.make_lock(self.folder)
            saved['Lib'] = 'function bump(x) = x + 100.\n'
            res = K.replay(lock)
            self.assertTrue(res['ok'], res)
        finally:
            L.saved_source = old

    def test_in_memory_edits_are_checked_before_execution(self):
        self.finished_run()
        lock = K.make_lock(self.folder)
        lock['options']['side_effects'] = True
        with patch.object(SR, 'Run') as run, self.assertRaisesRegex(K.LockError, 'hash'):
            K.replay(lock)
        run.assert_not_called()

    def test_kernel_drift_refuses_replay_and_comparison(self):
        rep, _ = self.finished_run()
        lock = K.make_lock(self.folder)
        changed = {**S.kernel_id(), 'canon': -1}
        with patch.object(S, 'kernel_id', return_value=changed), self.assertRaisesRegex(K.LockError, 'kernel'):
            K.replay(lock)
        with self.assertRaisesRegex(K.LockError, 'kernel'):
            K.drift(lock, {**rep, 'kernel': changed})

    def test_missing_original_kernel_cannot_be_backfilled(self):
        self.finished_run()
        path = os.path.join(self.folder, 'state.json')
        with open(path) as f:
            state = json.load(f)
        del state['kernel']
        with open(path, 'w') as f:
            json.dump(state, f)
        with self.assertRaisesRegex(K.LockError, 'kernel'):
            K.make_lock(self.folder)

    def test_legacy_lock_is_not_silently_upgraded(self):
        self.finished_run()
        lock = K.make_lock(self.folder)
        lock['symblic_lock'] = 1
        lock['sha256'] = K.lock_hash(lock)
        with self.assertRaisesRegex(K.LockError, 'version'):
            K.replay(lock)

    def test_source_and_module_internal_hashes_are_checked(self):
        self.finished_run()
        for target in ('source', 'module'):
            with self.subTest(target=target):
                lock = K.make_lock(self.folder)
                if target == 'source':
                    lock['source'] += '\nshow 999.\n'
                else:
                    lock['modules']['lib:units']['source'] += '\nlet tampered = 1.\n'
                lock['sha256'] = K.lock_hash(lock)
                with self.assertRaisesRegex(K.LockError, 'hash'):
                    K.replay(lock)

    def test_binding_evidence_and_checks_are_preserved(self):
        source = 'ask n: Int "Count." with by="fake:a"\nassert n = 3.\nshow n.\n'
        rep, _ = self.finished_run(source=source)
        self.assertEqual(rep['status'], 'done', rep['error'])
        lock = K.make_lock(self.folder)
        self.assertTrue(lock['provenance_recorded'])
        self.assertEqual(lock['evidence'], rep['evidence'])
        self.assertTrue(lock['checks'])
        self.assertEqual(lock['statements'][0]['evidence'], rep['bindings'][0]['meta']['evidence'])
        result = K.replay(lock)
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['evidence_match'])
        self.assertEqual(result['recorded_evidence'], rep['evidence'])
        self.assertEqual(result['recorded_checks'], lock['checks'])

    def test_altered_receipt_cannot_pass_replay_even_if_lock_rehashed(self):
        self.finished_run(source='let n = 3.\nassert n = 3.\n')
        lock = K.make_lock(self.folder)
        lock['evidence']['checks'][0]['passed'] = False
        receipt = lock['evidence']['checks'][0]
        receipt['id'] = hashlib.sha256(json.dumps({k: v for k, v in receipt.items() if k != 'id'},
                                                sort_keys=True, ensure_ascii=False,
                                                separators=(',', ':')).encode()).hexdigest()
        lock['sha256'] = K.lock_hash(lock)
        result = K.replay(lock)
        self.assertFalse(result['ok'])
        self.assertFalse(result['evidence_match'])

    def test_same_semantic_kernel_preserves_original_runtime_receipts(self):
        self.finished_run(source='let n = 3.\nassert n = 3.\n')
        lock = K.make_lock(self.folder)
        original = lock['evidence']['checks'][0]
        changed = {**S.kernel_id(), 'python': 'another compatible runtime'}
        with patch.object(S, 'kernel_id', return_value=changed):
            result = K.replay(lock)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['recorded_evidence']['checks'][0], original)
        self.assertNotEqual(result['report']['evidence']['checks'][0]['id'], original['id'])

    def test_receipt_hash_corruption_is_refused(self):
        self.finished_run(source='let n = 3.\nassert n = 3.\n')
        lock = K.make_lock(self.folder)
        lock['evidence']['checks'][0]['id'] = 'wrong'
        lock['sha256'] = K.lock_hash(lock)
        with self.assertRaisesRegex(K.LockError, 'receipt'):
            K.replay(lock)

    def test_replay_forces_effects_off_and_has_no_event_callbacks(self):
        self.finished_run()
        lock = K.make_lock(self.folder)
        lock['options'].update(side_effects=True, on_event='untrusted callback', event_sink='untrusted sink')
        lock['sha256'] = K.lock_hash(lock)
        original = SR.Run
        options = []

        def construct(source, inputs, apps, opts, **kwargs):
            options.append(opts)
            return original(source, inputs, apps, opts, **kwargs)

        with patch.object(SR, 'Run', side_effect=construct):
            result = K.replay(lock)
        self.assertTrue(result['ok'], result)
        self.assertTrue(options[0]['replay'])
        self.assertFalse(options[0]['side_effects'])
        self.assertNotIn('on_event', options[0])
        self.assertNotIn('event_sink', options[0])

    def test_delegate_cannot_execute_during_replay(self):
        # Construct a finished effect record without ever invoking a real delegate.
        source = 'delegate job = "Do nothing" to "triad".\n'
        self.finished_run(source='let x = 1.\n')
        lock = K.make_lock(self.folder)
        lock['source'] = source
        lock['source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        lock['evidence']['source_sha256'] = lock['source_sha256']
        lock['options']['side_effects'] = True
        lock['sha256'] = K.lock_hash(lock)
        with patch.object(K._NoModels, 'delegate', side_effect=AssertionError('must not dispatch')):
            result = K.replay(lock)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'failed')

    def test_nested_route_options_survive_lock(self):
        opts = {'route_table': {'candidates': ['fake:a'], 'scope': 'observed_tests_only'},
                'on_event': lambda _: None, 'stop': threading.Event(), 'effects': {'host': 'untrusted'},
                'effects_ledger': '/never/read/a/live/ledger'}
        kept = K._portable_options(opts)
        self.assertEqual(kept, {'route_table': opts['route_table']})

    def effect_run(self, source, apps=None, options=None):
        with open(os.path.join(self.folder, 'program.sym'), 'w') as f:
            f.write(source)
        with open(os.path.join(self.folder, 'meta.json'), 'w') as f:
            json.dump({'options': {'side_effects': True}}, f)
        report = SR.Run(source, applicators=apps, folder=self.folder,
                        options={'side_effects': True, **(options or {})}).execute()
        self.assertEqual(report['status'], 'done', report)
        return K.make_lock(self.folder)

    def test_delegate_lock_reuses_exact_ledger_without_dispatch(self):
        class Delegate:
            def delegate(self, target, task, options):
                return {'id': 'fake-agent', 'engine': target, 'status': 'started'}
        lock = self.effect_run('delegate job = "Do nothing" to "triad".\nshow job.id.', Delegate())
        with open(os.path.join(self.folder, 'delegate-effects.jsonl'), newline='') as f:
            original = f.read()
        self.assertEqual(lock['effect_ledgers']['delegate-effects.jsonl'], original)
        with patch.object(K._NoModels, 'delegate', side_effect=AssertionError('must not dispatch')):
            result = K.replay(lock)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['refused'], [])

    def test_delegate_lock_with_missing_or_pending_receipt_cannot_dispatch(self):
        class Delegate:
            def delegate(self, target, task, options):
                return {'id': 'fake-agent', 'engine': target, 'status': 'started'}
        original = self.effect_run('delegate job = "Do nothing" to "triad".', Delegate())
        for mode in ('missing', 'pending'):
            with self.subTest(mode=mode):
                lock = json.loads(json.dumps(original))
                if mode == 'missing':
                    lock['effect_ledgers'] = {}
                else:
                    first = lock['effect_ledgers']['delegate-effects.jsonl'].splitlines()[0]
                    lock['effect_ledgers']['delegate-effects.jsonl'] = first + '\n'
                lock['sha256'] = K.lock_hash(lock)
                with patch.object(K._NoModels, 'delegate', side_effect=AssertionError('must not dispatch')):
                    result = K.replay(lock)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error']['kind'], 'uncertain')

    def test_effect_ledger_edits_are_covered_by_lock_hash(self):
        self.finished_run(source='let x=1.')
        lock = K.make_lock(self.folder)
        lock['effect_ledgers']['effects.jsonl'] = '{}\n'
        with patch.object(SR, 'Run') as run, self.assertRaisesRegex(K.LockError, 'hash'):
            K.replay(lock)
        run.assert_not_called()

    def test_effect_ledger_names_cannot_escape_replay_folder(self):
        self.finished_run(source='let x=1.')
        lock = K.make_lock(self.folder)
        lock['effect_ledgers']['../unrelated.jsonl'] = '{}\n'
        lock['sha256'] = K.lock_hash(lock)
        with patch.object(SR, 'Run') as run, self.assertRaisesRegex(K.LockError, 'ledger'):
            K.replay(lock)
        run.assert_not_called()

    def test_capability_ledger_replays_without_host_and_preserves_evidence(self):
        from symblic.kernel import effects as F
        class Host:
            def __init__(self):
                self.calls = 0
            def perform(self, effect, stop):
                self.calls += 1
                return {'status': 'done', 'result': 7, 'receipt': 'fake-receipt'}
        host = Host()
        with patch.object(F, '_CATALOGUE', None):
            lock = self.effect_run('observe value: Int = fake.read().\nshow value.',
                                   options={'effects': host})
            with open(os.path.join(self.folder, 'effects.jsonl'), newline='') as f:
                self.assertEqual(lock['effect_ledgers']['effects.jsonl'], f.read())
            result = K.replay(lock)
        self.assertEqual(host.calls, 1)
        self.assertTrue(result['ok'], result)
        original = lock['statements'][0]['evidence']
        replayed = result['report']['bindings'][0]['meta']['evidence']
        self.assertFalse(original['replayed'])
        self.assertTrue(replayed['replayed'])
        self.assertEqual(original['effect_id'], replayed['effect_id'])

    def test_effect_catalogue_survives_replay_without_original_host(self):
        from symblic.kernel import effects as F
        class Host:
            def catalogue(self):
                return {'fake.read': {'effect': 'read', 'family': 'sensor', 'untrusted': True,
                                      'sensitivity': 'private', 'params': {'type': 'object'}}}
            def perform(self, effect, stop):
                return {'status': 'done', 'result': 7}
        with patch.object(F, '_CATALOGUE', None):
            lock = self.effect_run('observe value: Int = fake.read().\nshow value.',
                                   options={'effects': Host()})
            with open(os.path.join(self.folder, F.CATALOGUE_FILE), newline='') as f:
                self.assertEqual(lock['effect_catalogue'], f.read())
            captured = []
            original_run = SR.Run
            def construct(*args, **kwargs):
                with open(os.path.join(kwargs['folder'], F.CATALOGUE_FILE), newline='') as f:
                    captured.append(f.read())
                return original_run(*args, **kwargs)
            with patch.object(SR, 'Run', side_effect=construct):
                result = K.replay(lock)
        self.assertEqual(captured, [lock['effect_catalogue']])
        self.assertTrue(result['ok'], result)
        evidence = result['report']['bindings'][0]['meta']['evidence']
        self.assertTrue(evidence['untrusted'])
        self.assertEqual(evidence['sensitivity'], 'private')
        self.assertEqual(evidence['declaration']['mode'], 'capability:sensor')

    def test_program_scope_replay_uses_run_receipts_after_external_ledger_deleted(self):
        from symblic.kernel import effects as F
        class Host:
            def __init__(self):
                self.calls = 0
            def perform(self, effect, stop):
                self.calls += 1
                return {'status': 'done', 'result': 'fake-outcome'}
        host = Host()
        shared = os.path.join(self.tmp, 'shared-effects.jsonl')
        with patch.object(F, '_CATALOGUE', None):
            lock = self.effect_run('act done = fake.write() with scope="program", key="once".\nshow done.',
                                   options={'effects': host, 'effects_ledger': shared})
            os.unlink(shared)
            result = K.replay(lock)
        self.assertEqual(host.calls, 1)
        self.assertFalse(os.path.exists(shared))
        self.assertTrue(result['ok'], result)

    def test_malformed_frozen_catalogue_is_refused_before_replay(self):
        self.finished_run(source='let x=1.')
        lock = K.make_lock(self.folder)
        for catalogue in ('{torn', '{}', {'capabilities': {}}):
            with self.subTest(catalogue=catalogue):
                lock['effect_catalogue'] = catalogue
                lock['sha256'] = K.lock_hash(lock)
                with patch.object(SR, 'Run') as run, self.assertRaisesRegex(K.LockError, 'catalogue'):
                    K.replay(lock)
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
