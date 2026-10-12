"""Private host experiment lifecycle, crash boundaries and exact scoring."""
import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.policy import learning as P
from symblic.policy import store as E


def setup(root, ident='experiment'):
    policies = [{'answer': 0}, {'answer': 42}]
    tf = E.case_fixture({'task': 'training'}, 42, family_hash=P.digest('train-family'))
    hf = E.case_fixture({'task': 'hidden-heldout-input'}, 42, family_hash=P.digest('heldout-family'))
    tp = {'version': 1, 'candidates': [{'sha256': P.digest(p), 'policy': p} for p in policies],
          'baseline': P.digest(policies[0]), 'cases': [tf['case']],
          'budget': {'max_calls': 4, 'max_cost_units': 12},
          'objective': {'max_score': 10, 'score_weight': 10, 'call_weight': 1, 'cost_weight': 1,
                        'unknown_cost': 'reject', 'tie_break': 'policy_sha256_ascending',
                        'min_heldout_gain': 1}}
    hp = {'version': 1, 'training_plan_hash': P.digest(tp), 'cases': [hf['case']]}
    exp = E.PolicyExperiment.freeze(root, ident, tp, hp, [tf], [hf], cost_unit='fixture-units')
    return exp, tp, hp, tf, hf


def outcome(request):
    return {'status': 'done', 'output': request['policy']['answer'],
            'attempts': [{'id': request['assignment_id'] + '.1', 'request_sha256': P.digest(request),
                          'calls': 1, 'cost_units': 2, 'status': 'done'}],
            'checks': [], 'complete': True, 'effects': 'none'}


def execute(exp, stage, runner=outcome):
    return [exp.run_assignment(stage, row['candidate_sha256'], row['case_hash'], runner=runner)
            for row in exp.assignments(stage)]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    path.chmod(0o600)


class PolicyStore(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.exp, self.tp, self.hp, self.tf, self.hf = setup(self.root)
        self.good = P.digest({'answer': 42})
        self.bad = P.digest({'answer': 0})
        self.case = self.tf['case']['case_hash']

    def test_complete_lifecycle_fixed_selection_and_safe_ui_status(self):
        status = self.exp.status()
        self.assertEqual(status['stage'], 'training')
        self.assertEqual(status['assignments']['training']['pending']['count'], 2)
        self.assertNotIn('hidden-heldout-input', json.dumps(status))
        with self.assertRaisesRegex(E.PolicyStoreError, 'heldout_not_open'):
            self.exp.assignments('heldout')
        results = execute(self.exp, 'training')
        self.assertEqual(sorted(x['record']['score'] for x in results), [0, 10])
        chosen = self.exp.seal_training()
        self.assertEqual(chosen['selected']['sha256'], self.good)
        before = {p.name: p.read_bytes() for p in self.exp.path.glob('training-*.json')}
        self.assertEqual(self.exp.status()['stage'], 'heldout')
        execute(self.exp, 'heldout')
        evaluation = self.exp.seal_heldout()
        self.assertTrue(evaluation['improvement'])
        self.assertEqual(evaluation['confidence'], 'not_established')
        self.assertEqual(self.exp.status()['stage'], 'evaluated')
        self.assertEqual(self.exp.status()['evaluation'], evaluation)
        self.assertEqual(self.exp.selection(), chosen)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.exp.path.glob('training-*.json')})
        self.assertEqual(self.exp.seal_heldout(), evaluation)
        for path in self.exp.path.rglob('*'):
            self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_freeze_idempotent_changed_plan_conflicts_and_pins(self):
        again, *_ = setup(self.root)
        self.assertEqual(again.freeze_hash, self.exp.freeze_hash)
        tp = copy.deepcopy(self.tp)
        tp['budget']['max_calls'] = 3
        hp = dict(self.hp, training_plan_hash=P.digest(tp))
        with self.assertRaisesRegex(E.PolicyStoreError, 'immutable_conflict'):
            E.PolicyExperiment.freeze(self.root, 'experiment', tp, hp, [self.tf], [self.hf], cost_unit='fixture-units')
        wrong = E.PolicyExperiment(self.root, 'experiment', expected_freeze_hash='0' * 64)
        with self.assertRaisesRegex(E.PolicyStoreError, 'freeze_pin'):
            wrong.status()
        hp['training_plan_hash'] = '0' * 64
        with self.assertRaisesRegex(E.PolicyStoreError, 'training_plan_pin'):
            E.PolicyExperiment.freeze(self.root, 'new', tp, hp, [self.tf], [self.hf], cost_unit='fixture-units')

    def test_split_and_fixture_mismatch_before_any_run(self):
        hp = dict(self.hp, cases=[self.tf['case']])
        with self.assertRaisesRegex(P.PolicyError, 'split_overlap'):
            E.PolicyExperiment.freeze(self.root, 'new', self.tp, hp, [self.tf], [self.tf], cost_unit='u')
        changed = copy.deepcopy(self.tf)
        changed['expected'] = 9000
        with self.assertRaisesRegex(E.PolicyStoreError, 'fixture_pin'):
            E.PolicyExperiment.freeze(self.root, 'new', self.tp, self.hp, [changed], [self.hf], cost_unit='u')
        self.assertFalse((self.root / 'new').exists())

    def test_no_gold_or_heldout_in_requests_or_training_selection_reads(self):
        requests = []
        def runner(request):
            requests.append(copy.deepcopy(request))
            self.assertNotIn('expected', request)
            self.assertNotIn('hidden-heldout-input', json.dumps(request))
            return outcome(request)
        execute(self.exp, 'training', runner)
        self.exp.seal_training()
        original = E._read
        def read(path):
            self.assertNotIn('heldout', path.name)
            return original(path)
        with patch.object(E, '_read', side_effect=read):
            selection = self.exp.selection()
        self.assertNotIn('hidden-heldout-input', json.dumps(selection))
        self.assertEqual(len(requests), 2)

    def test_idempotent_reopen_and_no_late_dispatch(self):
        calls = []
        def runner(request):
            calls.append(request['assignment_id'])
            return outcome(request)
        first = self.exp.run_assignment('training', self.good, self.case, runner=runner)
        reopen = E.PolicyExperiment(self.root, 'experiment', expected_freeze_hash=self.exp.freeze_hash)
        self.assertEqual(reopen.run_assignment('training', self.good, self.case, runner=runner), first)
        execute(self.exp, 'training', runner)
        self.exp.seal_training()
        self.assertEqual(self.exp.run_assignment('training', self.good, self.case, runner=runner), first)
        self.assertEqual(len(calls), 2)
        with self.assertRaisesRegex(E.PolicyStoreError, 'unassigned_candidate'):
            self.exp.run_assignment('training', '0' * 64, self.case, runner=runner)
        with self.assertRaisesRegex(E.PolicyStoreError, 'unassigned_case'):
            self.exp.run_assignment('training', self.good, '0' * 64, runner=runner)

    def test_runner_failure_in_doubt_no_redispatch_and_explicit_reconciliation(self):
        calls = []
        def crash(request):
            calls.append(request['assignment_id'])
            raise RuntimeError('private provider details')
        with self.assertRaisesRegex(E.PolicyStoreError, '^runner_unresolved$'):
            self.exp.run_assignment('training', self.good, self.case, runner=crash)
        with self.assertRaisesRegex(E.PolicyStoreError, 'assignment_in_doubt'):
            self.exp.run_assignment('training', self.good, self.case, runner=crash)
        self.assertEqual(len(calls), 1)
        status = self.exp.status()['assignments']['training']
        self.assertEqual(status['inflight']['assignment_ids'], calls)
        with self.assertRaisesRegex(E.PolicyStoreError, 'incomplete_assignments'):
            self.exp.seal_training()
        result = self.exp.reconcile_assignment('training', self.good, self.case, resolver=outcome)
        self.assertTrue(result['outcome_file'].startswith('reconciled-'))
        self.assertEqual(result['record']['score'], 10)

    def test_result_publication_crash_recovers_durable_outcome_without_dispatch(self):
        original = E._write_immutable
        calls = []
        def publish(path, value):
            if path.name == 'result.json':
                raise OSError('simulated fsync failure')
            return original(path, value)
        def runner(request):
            calls.append(request['assignment_id'])
            return outcome(request)
        with patch.object(E, '_write_immutable', side_effect=publish), self.assertRaises(OSError):
            self.exp.run_assignment('training', self.good, self.case, runner=runner)
        self.assertEqual(len(list(self.exp.path.glob('assignment-*/outcome.json'))), 1)
        result = self.exp.run_assignment('training', self.good, self.case, runner=runner)
        self.assertEqual(result['record']['score'], 10)
        self.assertEqual(len(calls), 1)

    def test_partial_freeze_recovers_and_published_hardlink_orphan_is_readable(self):
        original = E._write_immutable
        def publish(path, value):
            if path.name == 'frozen.json':
                raise OSError('simulated crash')
            return original(path, value)
        with patch.object(E, '_write_immutable', side_effect=publish), self.assertRaises(OSError):
            setup(self.root, 'partial')
        exp, *_ = setup(self.root, 'partial')
        os.link(exp.path / 'training-plan.json', exp.path / '.pending-crash')
        self.assertEqual(exp.status()['stage'], 'training')

    def test_concurrent_same_assignment_dispatches_once(self):
        entered, release = threading.Event(), threading.Event()
        errors, calls = [], []
        def runner(request):
            calls.append(request['assignment_id'])
            entered.set()
            if not release.wait(5):
                raise TimeoutError()
            return outcome(request)
        def first():
            try:
                self.exp.run_assignment('training', self.good, self.case, runner=runner)
            except Exception as exc:  # noqa: BLE001 - collect failures from a test thread.
                errors.append(exc)
        worker = threading.Thread(target=first)
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaisesRegex(E.PolicyStoreError, 'assignment_in_doubt'):
                self.exp.run_assignment('training', self.good, self.case, runner=runner)
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)
        self.assertEqual(len(calls), 1)

    def test_checks_cannot_grant_wrong_output_and_negative_checks_deny_match(self):
        def checked(request):
            value = outcome(request)
            value['checks'] = [{'scope': 'schema', 'passed': request['candidate_sha256'] == self.bad,
                                'subject_sha256': P.digest(value['output']), 'checker_sha256': P.digest('schema')}]
            return value
        results = execute(self.exp, 'training', checked)
        self.assertTrue(all(row['record']['score'] == 0 for row in results))
        self.assertTrue(all(row['score_receipt']['empirical_truth'] == 'not_established' for row in results))

    def test_exact_json_types_and_candidate_metadata_are_not_evidence(self):
        for output in (True, {'value': 42, 'accepted': True, 'origin': 'KNOWN'}):
            exp, tp, _, tf, _ = setup(self.root, 'typed-' + str(len(list(self.root.iterdir()))))
            candidate = tp['candidates'][1]['sha256']
            def forged(request, output=output):
                value = outcome(request)
                value['output'] = output
                return value
            result = exp.run_assignment('training', candidate, tf['case']['case_hash'], runner=forged)
            self.assertEqual(result['record']['score'], 0)

    def test_all_attempts_charged_and_refusals_remain_denominator(self):
        def runner(request):
            value = outcome(request)
            previous = dict(value['attempts'][0], id=request['assignment_id'] + '.0', status='failed', cost_units=3)
            value['attempts'].insert(0, previous)
            if request['candidate_sha256'] == self.bad:
                value['status'] = 'refused'
            return value
        execute(self.exp, 'training', runner)
        summary = self.exp.seal_training()['receipt']['summaries']
        for candidate in (self.good, self.bad):
            self.assertEqual(summary[candidate]['observed_calls'], 2)
            self.assertEqual(summary[candidate]['known_cost_units'], 5)
            self.assertEqual(summary[candidate]['denominator'], 1)
        self.assertEqual(summary[self.bad]['statuses']['refused'], 1)

    def test_unresolved_or_overbudget_outcomes_preserved_cannot_seal(self):
        mutations = [lambda x: x.update(complete=False), lambda x: x.update(effects='uncertain'),
                     lambda x: x.update(status='uncertain'), lambda x: x['attempts'][0].update(cost_units=None),
                     lambda x: x['attempts'][0].update(calls=5), lambda x: x['attempts'][0].update(cost_units=13),
                     lambda x: x['attempts'][0].update(calls=True)]
        for index, mutate in enumerate(mutations):
            exp, tp, _, tf, _ = setup(self.root, 'rejected-' + str(index))
            candidate = tp['candidates'][1]['sha256']
            def runner(request, mutate=mutate):
                value = outcome(request)
                mutate(value)
                return value
            with self.assertRaises(E.PolicyStoreError):
                exp.run_assignment('training', candidate, tf['case']['case_hash'], runner=runner)
            paths = list(exp.path.glob('assignment-*/outcome.json'))
            self.assertEqual(len(paths), 1)
            original = paths[0].read_bytes()
            with self.assertRaisesRegex(E.PolicyStoreError, 'incomplete_assignments'):
                exp.seal_training()
            fixed = exp.reconcile_assignment('training', candidate, tf['case']['case_hash'], resolver=outcome)
            self.assertEqual(fixed['record']['score'], 10)
            self.assertEqual(paths[0].read_bytes(), original)

    def test_duplicate_attempt_ids_within_and_across_assignments(self):
        def repeated(request):
            value = outcome(request)
            value['attempts'] *= 2
            return value
        with self.assertRaisesRegex(E.PolicyStoreError, 'duplicate_attempt'):
            self.exp.run_assignment('training', self.good, self.case, runner=repeated)
        self.exp.reconcile_assignment('training', self.good, self.case, resolver=outcome)
        first = self.exp.assignments('training')
        good_id = next(row['assignment_id'] for row in first if row['candidate_sha256'] == self.good)
        def reused(request):
            value = outcome(request)
            value['attempts'][0]['id'] = good_id + '.1'
            return value
        with self.assertRaisesRegex(E.PolicyStoreError, 'attempt_reused'):
            self.exp.run_assignment('training', self.bad, self.case, runner=reused)

    def test_forged_selection_recomputed_selfhash_rejected_before_heldout(self):
        execute(self.exp, 'training')
        self.exp.seal_training()
        path = self.exp.path / 'selection.json'
        value = E._read(path)
        value['selection']['selected']['sha256'] = self.bad
        value['selection']['selected']['policy_json'] = json.dumps({'answer': 0}, sort_keys=True, separators=(',', ':'))
        value['selection_sha256'] = P.digest(value['selection'])
        save(path, value)
        calls = []
        with self.assertRaisesRegex(E.PolicyStoreError, 'selection_pin'):
            self.exp.run_assignment('heldout', self.bad, self.hf['case']['case_hash'], runner=lambda req: calls.append(req))
        self.assertFalse(calls)

    def test_changed_pins_during_callback_or_result_tamper_rejected(self):
        def tamper(request):
            data = E._read(self.exp.path / 'training-plan.json')
            data['budget']['max_calls'] += 1
            save(self.exp.path / 'training-plan.json', data)
            return outcome(request)
        with self.assertRaisesRegex(E.PolicyStoreError, 'file_pin'):
            self.exp.run_assignment('training', self.good, self.case, runner=tamper)
        save(self.exp.path / 'training-plan.json', self.tp)
        self.exp.reconcile_assignment('training', self.good, self.case, resolver=outcome)
        path = next(self.exp.path.glob('assignment-*/result.json'))
        value = E._read(path)
        value['record']['score'] = 0
        save(path, value)
        with self.assertRaisesRegex(E.PolicyStoreError, 'result_pin'):
            self.exp.status()

    def test_symlinks_public_directory_noncanonical_files_rejected(self):
        (self.root / 'linked').symlink_to(self.exp.path, target_is_directory=True)
        with self.assertRaisesRegex(E.PolicyStoreError, 'private_directory'):
            E.PolicyExperiment(self.root, 'linked', expected_freeze_hash=self.exp.freeze_hash)
        self.exp.path.chmod(0o755)
        with self.assertRaisesRegex(E.PolicyStoreError, 'private_directory'):
            self.exp.status()
        self.exp.path.chmod(0o700)
        path = self.exp.path / 'training-plan.json'
        path.write_text(json.dumps(self.tp, indent=2))
        with self.assertRaisesRegex(E.PolicyStoreError, 'noncanonical_file'):
            self.exp.status()

    def test_implementation_pins_refuse_disk_process_and_new_worker_drift(self):
        original = E._implementation()
        self.assertEqual(self.exp.status()['implementation_hashes'], original)
        with (patch.dict(E._IMPORTED_HASHES, {'symblic/policy/learning.py': '0' * 64}),
              self.assertRaisesRegex(E.PolicyStoreError, 'implementation_changed_use_fresh_worker')):
            self.exp.status()
        changed = dict(original, **{'symblic/policy/learning.py': '0' * 64})
        calls = []
        with (patch.object(E, '_implementation', return_value=changed),
              self.assertRaisesRegex(E.PolicyStoreError, 'implementation_pin')):
            self.exp.run_assignment('training', self.good, self.case, runner=lambda req: calls.append(req))
        self.assertFalse(calls)
        with (patch('symblic.kernel.execution_pins._bytecode_matches', return_value=False),
              self.assertRaisesRegex(E.PolicyStoreError, 'implementation_bytecode')):
            self.exp.status()

    def test_status_without_audit_tolerates_implementation_drift(self):
        original = E._implementation()
        changed = dict(original, **{'symblic/policy/learning.py': '0' * 64})
        with patch.object(E, '_implementation', return_value=changed):
            with self.assertRaisesRegex(E.PolicyStoreError, 'implementation_pin'):
                self.exp.status(audit_implementation=True)
            status = self.exp.status(audit_implementation=False)
            self.assertFalse(status['implementation_intact'])
            self.assertIn('implementation changed', status['assurance'])

    def test_frozen_host_runtime_contract_and_private_status_projection(self):
        identity = {'runtime': 'pinned-build', 'private-configuration': 'not-for-ui'}
        exp = E.PolicyExperiment.freeze(self.root, 'host', self.tp, self.hp, [self.tf], [self.hf],
                                        cost_unit='fixture-units', host_identity=identity)
        self.assertEqual(exp.assert_host_identity(identity), P.digest(identity))
        status = exp.status()
        self.assertEqual(status['host_identity_sha256'], P.digest(identity))
        self.assertNotIn('not-for-ui', json.dumps(status))
        with self.assertRaisesRegex(E.PolicyStoreError, 'host_identity_pin'):
            exp.assert_host_identity(dict(identity, runtime='changed-build'))
        self.assertEqual(self.exp.assert_host_identity(None), P.digest(None))


if __name__ == '__main__':
    unittest.main()
