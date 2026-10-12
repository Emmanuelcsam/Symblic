"""Policy integration with graph990 worker leases, using private fake journals."""
import threading
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_policy_api as A
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.policy import graph as G
from tests.integration import test_symblic_policy_repair as repair


from tests.integration import fake_host_apps  # noqa: E402

# The host's store (and fleet records), faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class PolicyLease(unittest.TestCase):
    setUp = repair.PolicyRepair.setUp
    start = repair.PolicyRepair.start
    stale_job = repair.PolicyRepair.stale_job

    def test_constructor_exceptions_release_even_with_retained_tracebacks(self):
        retained = []
        for kind in (RuntimeError, repair.Crash):
            with self.subTest(kind=kind.__name__):
                self.body['acknowledge_heldout_reuse'] = True
                _ident, folder = self.start()
                with patch.object(G, 'GraphPolicyRunner', side_effect=kind('constructor fixture')):
                    try:
                        A.run_job(folder, applicators=self.apps)
                    except kind as error:
                        retained.append(error)
                    else:
                        self.fail('constructor failure should propagate')
                self.assertFalse(A.A.worker_alive(folder))
                self.assertEqual(self.apps.calls, [])
        self.assertEqual(len(retained), 2)

    def test_body_baseexception_releases_but_retains_uncertain_intent(self):
        ident, folder = self.start()
        retained = []
        with patch.object(self.apps, 'call', side_effect=repair.Crash('issued-call fixture')):
            try:
                A.run_job(folder, applicators=self.apps)
            except repair.Crash as error:
                retained.append(error)
        self.assertEqual(len(retained), 1)
        self.assertFalse(A.A.worker_alive(folder))
        view = A.view(ident)
        self.assertFalse(view['can_resume'])
        self.assertIn('automatic redispatch refused', view['error'])
        rows = view['state']['assignments']['training']
        self.assertEqual(rows['inflight']['count'], 1)
        self.assertEqual(sum(row['count'] for row in rows.values()), 2)

    def test_cheap_views_use_worker_lease_and_stop_guard(self):
        ident, folder = self.start()
        stopped, _generation = A.A.begin_job(folder, None, threading.Event(), final=False)
        self.assertIsNotNone(stopped)
        try:
            self.stale_job(folder)
            with patch.object(G, 'GraphPolicyRunner', side_effect=AssertionError('cheap view opened native runtime')):
                view = A.view(ident, audit=False)
                self.assertTrue(view['active'])
                self.assertFalse(view['can_resume'])
                self.assertEqual(A.list_runs()[0]['status'], 'running')
        finally:
            stopped.release()
        self.assertTrue(A.view(ident, audit=False)['can_resume'])
        guard = A.A._acquire(folder / A.A.STOP_LOCK, 0)
        self.assertIsNotNone(guard)
        try:
            view = A.view(ident, audit=False)
            self.assertFalse(view['active'])
            self.assertFalse(view['can_resume'])
        finally:
            A.A._release(guard)
        self.assertTrue(A.view(ident, audit=False)['can_resume'])


if __name__ == '__main__':
    unittest.main()
