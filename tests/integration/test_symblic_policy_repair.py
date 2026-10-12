"""Private-store regressions for concurrent admission and interrupted native jobs.

Fake Applicators, launchers and crash points only. No real provider, host effect,
systemd command or installed source edit is used.
"""
import copy
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.graph import run as R
from symblic.js import check as JS
try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_policy_api as A
    from tests.integration.test_symblic_policy_api import Apps, fixture
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.policy import graph as G
from symblic.policy import learning as P
from symblic.policy import store as E


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class Crash(BaseException):
    pass


class PolicyRepair(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.apps, self.launches = Apps(), []
        for patcher in (
            patch.dict(os.environ, {'AUTOMATION_DATA_DIR': str(self.root)}),
            patch.object(JS, 'node_version', return_value='test-no-node'),
            patch('subprocess.Popen', side_effect=AssertionError('no external process')),
            patch.dict(A.launcher, {'active': lambda _: False, 'stop': lambda _: True,
                'launch': lambda ident, folder, generation: self.launches.append((ident, folder, generation)) or {'ok': True}}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.body = fixture()

    def start(self):
        ident = A.start(self.body)['id']
        return ident, A._folder(ident)

    def stale_job(self, folder):
        record = A.A.read_job(folder)
        A.A._save(folder, 'job.json', {**record, 'updated': 0})

    def test_concurrent_starts_check_and_reserve_under_one_lock(self):
        barrier, original, results = threading.Barrier(2), A.prepare, []
        def synchronized(*args, **kwargs):
            prepared = original(*args, **kwargs)
            barrier.wait(10)
            return prepared
        def start():
            try:
                results.append(('ok', A.start(self.body)))
            except Exception as error:  # noqa: BLE001 - collect thread failures for assertions
                results.append(('refused', error))
        with patch.object(A, 'prepare', side_effect=synchronized):
            threads = [threading.Thread(target=start) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(20)
                self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(item[0] for item in results), ['ok', 'refused'])
        self.assertEqual(len(self.launches), 1)
        refused = next(value for kind, value in results if kind == 'refused')
        self.assertEqual(refused.status, 409)
        self.assertIn('acknowledge', str(refused))
        self.assertEqual(len(E._read(A._heldout_registry_path())), 1)

    def test_crash_after_reservation_retains_possible_exposure(self):
        with patch.object(E.PolicyExperiment, 'freeze', side_effect=Crash()), self.assertRaises(Crash):
            A.start(self.body)
        rows = E._read(A._heldout_registry_path())
        self.assertEqual(len(rows), 1)
        self.assertFalse(list(A._root().glob('*/frozen.json')))
        self.assertEqual(A.check(self.body)['prior_heldout_uses'], [rows[0]['experiment']])
        with self.assertRaises(A.A.ApiError):
            A.start(self.body)
        self.assertEqual(self.launches, [])

    def test_registry_capacity_refuses_without_deleting_history(self):
        def case(index):
            return [E.case_fixture({'input': index}, index, family_hash=P.digest(['family', index]))]
        with patch.object(A, 'MAX_REGISTRY_ENTRIES', 2):
            for index in range(2):
                A._reserve_heldout_use(str(index) * 12, case(index), acknowledge=False)
            path = A._heldout_registry_path()
            original = path.read_bytes()
            with self.assertRaises(A.A.ApiError):
                A._reserve_heldout_use('2' * 12, case(2), acknowledge=False)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(A._find_heldout_reuse(case(0)), ['0' * 12])

    def test_registry_structure_and_directory_bounds_fail_closed(self):
        root = A._root()
        for index in range(3):
            (root / ('extra-' + str(index))).touch()
        with patch.object(A, 'MAX_REGISTRY_ROOT_ENTRIES', 2), self.assertRaises(A.A.ApiError):
            A.check(self.body)
        path = A._heldout_registry_path()
        path.write_text('[null]')
        path.chmod(0o600)
        with self.assertRaises(A.A.ApiError):
            A.check(self.body)

    def test_registry_read_errors_are_not_an_empty_exposure_history(self):
        with patch.object(A, '_root', side_effect=OSError('fixture read unavailable')), self.assertRaises(OSError):
            A.check(self.body)

    def test_reconciliation_checks_frozen_plan_hashes(self):
        _ident, folder = self.start()
        A._heldout_registry_path().unlink()
        path = folder / 'heldout-plan.json'
        hp = E._read(path)
        hp['cases'] = []
        R._write_json(folder, path.name, hp)
        with self.assertRaises(A.A.ApiError) as refused:
            A.check(self.body)
        self.assertIn('manifest', str(refused.exception))
        self.assertFalse(A._heldout_registry_path().exists())

    def test_registry_lock_and_file_symlinks_are_refused(self):
        root = A._root()
        unrelated = self.root / 'unrelated'
        unrelated.write_text('unchanged')
        link = root / '.heldout_registry.lock'
        link.symlink_to(unrelated)
        with self.assertRaises(OSError):
            A.check(self.body)
        self.assertEqual(unrelated.read_text(), 'unchanged')
        link.unlink()
        A._heldout_registry_path().symlink_to(unrelated)
        with self.assertRaises(A.A.ApiError):
            A.check(self.body)

    def test_limits_and_strict_ack_refuse_before_case_compilation(self):
        oversized = copy.deepcopy(self.body)
        oversized['budget'] = {'max_calls': 10000, 'max_cost_units': 10000}
        for body in (oversized, {**self.body, 'acknowledge_heldout_reuse': 1}):
            with patch.object(G, 'validate_case', side_effect=AssertionError('late refusal')), self.assertRaises(A.A.ApiError):
                A.prepare(body)

    def test_preinitialization_crashes_resume_same_assignment_without_reset(self):
        for point in ('before_request', 'before_graph_pins', 'during_graph_pins'):
            with self.subTest(point=point):
                # Distinct task families avoid treating this recovery fixture as an acknowledged rerun.
                self.body = fixture()
                for stage in ('training', 'heldout'):
                    self.body[stage][0]['family'] += point
                    self.body[stage][0]['input']['graph']['id'] += point.replace('_', '')
                ident, folder = self.start()
                calls_before = len(self.apps.calls)
                if point == 'before_request':
                    crashing = patch.object(G.GraphPolicyRunner, '__call__', side_effect=Crash())
                elif point == 'before_graph_pins':
                    crashing = patch.object(R.GraphRun, 'execute', side_effect=Crash())
                else:
                    original = R._write_file
                    def write(root, name, raw, original=original):
                        if name == 'graph-pins.json':
                            (Path(root) / '.graph-pins.json.4242.aabb.tmp').write_bytes(raw[:5])
                            raise Crash()
                        return original(root, name, raw)
                    crashing = patch.object(R, '_write_file', side_effect=write)
                with crashing, self.assertRaises(Crash):
                    A.run_job(folder, applicators=self.apps)
                self.assertEqual(len(self.apps.calls), calls_before)
                intents = list(folder.glob('assignment-*/intent.json'))
                self.assertEqual(len(intents), 1)
                original_intent = intents[0].read_bytes()
                self.stale_job(folder)
                self.assertTrue(A.view(ident)['can_resume'])
                A.resume(ident)
                state = A.run_job(folder, applicators=self.apps)
                self.assertEqual(state['stage'], 'evaluated')
                self.assertEqual(intents[0].read_bytes(), original_intent)
                self.assertEqual(len(self.apps.calls) - calls_before, 4)
                self.assertFalse(list(folder.glob('**/*archive*')))
                for result in folder.glob('assignment-*/result.json'):
                    row = E._read(result)
                    self.assertEqual(sum(attempt['calls'] for attempt in row['record']['attempts']), 1)

    def test_preinitialization_never_ignores_an_unexplained_call_journal(self):
        ident, folder = self.start()
        with patch.object(G.GraphPolicyRunner, '__call__', side_effect=Crash()), self.assertRaises(Crash):
            A.run_job(folder, applicators=self.apps)
        intent = E._read(next(folder.glob('assignment-*/intent.json')))
        root = folder / 'graph-runtime' / intent['assignment_id']
        root.mkdir(parents=True, mode=0o700)
        (folder / 'graph-runtime').chmod(0o700)
        E._write_immutable(root / 'policy-request.json', intent)
        runtime = root / 'runtime'
        runtime.mkdir(mode=0o700)
        (runtime / 'graph-calls.jsonl').write_text('{"kind":"intent"}\n')
        self.stale_job(folder)
        view = A.view(ident)
        self.assertFalse(view['can_resume'])
        self.assertIn('unexplained', view['error'])
        self.assertEqual(self.apps.calls, [])

    def test_preinitialization_bounds_temps_before_runtime_directory_exists(self):
        _ident, folder = self.start()
        with patch.object(G.GraphPolicyRunner, '__call__', side_effect=Crash()), self.assertRaises(Crash):
            A.run_job(folder, applicators=self.apps)
        request = E._read(next(folder.glob('assignment-*/intent.json')))
        root = folder / 'graph-runtime' / request['assignment_id']
        root.mkdir(parents=True, mode=0o700)
        root.parent.chmod(0o700)
        for index in range(3):
            (root / ('.pending-' + str(index))).touch()
        runner = G.GraphPolicyRunner(root.parent, self.apps)
        with patch.object(R, 'ROOT_TREE_LIMIT', 2):
            allowed, reason = runner.is_recoverable(request)
        self.assertFalse(allowed)
        self.assertIn('entry limit', reason)
        self.assertEqual(self.apps.calls, [])

    def test_live_disk_drift_preserves_recorded_view_but_refuses_audit(self):
        ident, _folder = self.start()
        original = E._source_bytes
        def changed(name):
            data = original(name)
            return data + b'\n# changed\n' if name == 'symblic/policy/learning.py' else data
        with patch.object(E, '_source_bytes', side_effect=changed):
            cheap = A.view(ident, audit=False)
            self.assertNotEqual(cheap['status'], 'unavailable')
            self.assertFalse(cheap['state']['implementation_intact'])
            self.assertEqual(A.view(ident)['status'], 'unavailable')
            with patch.object(E.PolicyExperiment, 'status', side_effect=AssertionError('list audited')):
                self.assertEqual(A.list_runs()[0]['id'], ident)

    def test_loaded_policy_source_identity_is_not_replaced_by_late_disk_snapshot(self):
        with patch.object(P, '_SOURCE_SHA256', '0' * 64), self.assertRaises(E.PolicyStoreError):
            E._implementation()

    def test_cheap_inflight_view_and_list_never_open_native_runtime(self):
        ident, folder = self.start()
        with patch.object(G.GraphPolicyRunner, '__call__', side_effect=Crash()), self.assertRaises(Crash):
            A.run_job(folder, applicators=self.apps)
        self.stale_job(folder)
        with patch.object(G.GraphPolicyRunner, 'is_recoverable', side_effect=AssertionError('cheap runtime audit')):
            self.assertEqual(A.view(ident, audit=False)['assurance'], 'recorded')
            self.assertEqual(A.list_runs()[0]['id'], ident)


if __name__ == '__main__':
    unittest.main()
