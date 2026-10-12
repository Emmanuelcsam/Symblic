"""Component exchange uses private stores and rechecks actual source on reuse.

Providers are fixed local fakes; no agent, model, remote machine or historical store is used.
"""
import copy
import json
from pathlib import Path
import stat
import tempfile
import unittest

from symblic.graph import run as G
from symblic.js import check as JS
from symblic.mica import search as M
from symblic.mica import contracts as C
from symblic.mica import library as L
from symblic.spec import contracts as SC


CONTRACT = 'a' * 64
DEP_A, DEP_B = 'b' * 64, 'c' * 64
RUNTIME = {'kernel': 'fixture-kernel', 'javascript': 'fixture-checker'}
GOOD = 'function inc(x) { return x + 1; }'
BAD = 'function inc(x) { return 0; }'


def request(max_calls=2):
    return {'version': 1, 'language': 'javascript', 'objective': 'Implement public integer increment.',
            'requirements': [{'id': 'increment', 'text': 'Return the input integer plus one.', 'acceptance': 'TESTED'}],
            'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
            'tests': [{'requirement_ids': ['increment'], 'call': 'inc(2)', 'expected': '3'}],
            'allowed_outputs': ['result.js'], 'assumptions': ['Inputs are integers.'],
            'budget': {'max_calls': max_calls, 'max_candidates': 1, 'max_units': 4,
                       'max_workers': 1, 'retries': 0, 'context_chars': 24000, 'wall_seconds': 60}}


def inventory():
    return [{'engine': 'ollama', 'model': 'fixture-small', 'node': 'node-a', 'digest': None,
             'ready': True, 'available': True, 'context_chars': 24000, 'estimated_cost_units': 1}]


class Apps:
    def __init__(self, source=GOOD):
        self.source, self.calls = source, []

    def call(self, req):
        self.calls.append({k: copy.deepcopy(v) for k, v in req.items() if k != 'stop'})
        return {'ok': True, 'text': '```js\n' + self.source + '\n```',
                'model': req['app']['model'], 'node': req['app']['node'], 'ms': 1}


class LibraryStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mica-library-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.lib = L.ComponentLibrary(self.base / 'components')

    def publish(self, code=GOOD, **kwargs):
        return self.lib.publish(contract_sha256=CONTRACT, dependency_hashes=[DEP_A],
                                runtime=RUNTIME, code=code, **kwargs)

    def test_new_private_store_and_idempotent_immutable_bytes(self):
        first = self.publish()
        path = self.lib.root / first['key'] / (SC.code_hash(GOOD) + '.json')
        initial = path.read_bytes()
        self.assertEqual(stat.S_IMODE(self.lib.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(self.publish(), first)
        self.assertEqual(path.read_bytes(), initial)
        self.assertEqual(self.lib.candidates(first['key'], runtime=RUNTIME)[0]['code'], GOOD)
        second = self.publish(GOOD + '\n')
        self.assertNotEqual(first['sha256'], second['sha256'])
        self.assertEqual(len(self.lib.candidates(first['key'], runtime=RUNTIME)), 2)

    def test_contract_dependency_order_and_runtime_drift_change_identity(self):
        original = L.identity(CONTRACT, [DEP_A, DEP_B], RUNTIME)
        changed = [L.identity('d' * 64, [DEP_A, DEP_B], RUNTIME),
                   L.identity(CONTRACT, [DEP_B, DEP_A], RUNTIME),
                   L.identity(CONTRACT, [DEP_A], RUNTIME),
                   L.identity(CONTRACT, [DEP_A, DEP_B], {**RUNTIME, 'kernel': 'other'})]
        self.assertEqual(len({original, *changed}), 5)
        result = self.publish()
        with self.assertRaises(ValueError):
            self.lib.candidates(result['key'], runtime={**RUNTIME, 'kernel': 'other'})
        self.assertEqual(self.lib.candidates(changed[0], runtime=RUNTIME), [])

    def test_tampered_or_resealed_wrong_code_cannot_retain_identity(self):
        result = self.publish()
        path = self.lib.root / result['key'] / (SC.code_hash(GOOD) + '.json')
        original = json.loads(path.read_text())
        for rehash in (False, True):
            with self.subTest(rehash=rehash):
                changed = {**original, 'code': BAD}
                if rehash:
                    changed = G._seal({k: v for k, v in changed.items() if k != 'sha256'})
                path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    self.lib.candidates(result['key'], runtime=RUNTIME)
                with self.assertRaises(ValueError):
                    self.publish()
                path.write_text(json.dumps(original))

    def test_wrong_contract_dependency_or_record_name_fails_closed(self):
        result = self.publish()
        path = self.lib.root / result['key'] / (SC.code_hash(GOOD) + '.json')
        original = json.loads(path.read_text())
        for field, value in [('contract_sha256', DEP_B), ('dependency_hashes', [DEP_B]),
                             ('runtime', {'kernel': 'other'}), ('assurance', 'PROVEN')]:
            with self.subTest(field=field):
                body = {k: v for k, v in original.items() if k != 'sha256'}
                path.write_text(json.dumps(G._seal({**body, field: value})))
                with self.assertRaises(ValueError):
                    self.lib.candidates(result['key'], runtime=RUNTIME)
        path.write_text(json.dumps(original))
        path.rename(path.with_name('e' * 64 + '.json'))
        with self.assertRaises(ValueError):
            self.lib.candidates(result['key'], runtime=RUNTIME)

    def test_eight_variants_bound_growth_without_evicting_existing_bytes(self):
        results = [self.publish(GOOD + f'\n// variant {i}') for i in range(8)]
        folder = self.lib.root / results[0]['key']
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        self.assertEqual(self.publish(GOOD + '\n// variant 8')['status'], 'full')
        self.assertFalse(self.publish(GOOD + '\n// variant 9')['retained'])
        self.assertTrue(self.publish(GOOD + '\n// variant 0')['retained'])
        self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)
        self.assertEqual(len(self.lib.candidates(results[0]['key'], runtime=RUNTIME)), 8)

    def test_symlinked_root_ancestor_folder_record_and_lock_are_refused(self):
        target = self.base / 'target'; target.mkdir()
        alias = self.base / 'alias'; alias.symlink_to(target, target_is_directory=True)
        for path in (alias, alias / 'nested'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                L.ComponentLibrary(path)
        result = self.publish(); folder = self.lib.root / result['key']
        path = folder / (SC.code_hash(GOOD) + '.json')
        saved = target / 'record.json'; path.rename(saved); path.symlink_to(saved)
        with self.assertRaises(ValueError):
            self.lib.candidates(result['key'], runtime=RUNTIME)
        path.unlink(); saved.rename(path)
        moved = target / 'folder'; folder.rename(moved); folder.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.publish()
        folder.unlink(); moved.rename(folder)
        lock = self.lib.root / '.library.lock'; lock.unlink(); lock.symlink_to(target / 'lock')
        with self.assertRaises((ValueError, OSError)):
            self.publish()

    def test_replaced_ancestor_after_construction_cannot_redirect_new_records(self):
        parent = self.base / 'parent'; root = parent / 'components'
        library = L.ComponentLibrary(root)
        parent.rename(self.base / 'old-parent')
        outside = self.base / 'outside'; (outside / 'components').mkdir(parents=True)
        parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            library.publish(contract_sha256=CONTRACT, dependency_hashes=[], runtime=RUNTIME, code=GOOD)
        self.assertEqual(list((outside / 'components').iterdir()), [])


    def test_replaced_normal_directory_after_construction_is_refused(self):
        root = self.lib.root
        root.rename(self.base / 'original-components')
        root.mkdir()
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(list(root.iterdir()), [])


@unittest.skipUnless(JS.available(), 'sandboxed Node unavailable')
class LibraryExecution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mica-library-journey-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.library = self.base / 'library'

    def run_mica(self, name, apps, req=None, inv=None):
        return M.MicaRun(req or request(), self.base / name, apps,
                         inventory() if inv is None else inv, library=self.library).execute(mode='direct')

    def seed(self, req, code):
        run = M.MicaRun(req, self.base / 'seed-never-executed', Apps(), [], library=self.library)
        plan = M.direct_plan(C.normalize_request(req))
        spec = run._sheet_plan(plan)
        self.assertEqual(len(spec['units']), 1)
        return run.library.publish(contract_sha256=run._component_contract_hash(plan['contracts'][0], spec['units'][0]['contract_sha256']), dependency_hashes=[],
                                   runtime=M.implementation_identity(), code=code)

    def test_compatible_cross_run_reuse_makes_no_provider_calls(self):
        first_apps = Apps(); first = self.run_mica('first', first_apps)
        self.assertEqual(first['status'], 'done', first)
        self.assertEqual(len(first_apps.calls), 1)
        apps = Apps(BAD); second = self.run_mica('second', apps, inv=[])
        self.assertEqual(second['status'], 'done', second)
        self.assertEqual(second['calls'], 0)
        self.assertEqual(apps.calls, [])
        self.assertEqual(first['output']['text'], second['output']['text'])
        self.assertTrue(second['attempts'][0]['decisions'][0]['reused'])

    def test_original_zero_call_budget_accepts_copied_verified_source(self):
        req = request(max_calls=0)
        self.assertTrue(JS.test(GOOD, [('inc(2)', '3')])['passed'])
        self.seed(req, GOOD)
        apps = Apps(BAD); result = self.run_mica('zero-budget', apps, req, inv=[])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 0)
        self.assertEqual(result['calls_reserved_or_spent'], 0)
        self.assertEqual(apps.calls, [])
        self.assertEqual(list((self.base / 'zero-budget' / 'attempts').iterdir()), [])

    def test_invalid_cached_code_blocks_without_route_and_is_never_adopted(self):
        req = request(max_calls=0); self.seed(req, BAD)
        apps = Apps(); result = self.run_mica('no-route', apps, req, inv=[])
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(result['calls'], 0)
        self.assertEqual(apps.calls, [])
        self.assertNotIn('output', result)
        self.assertIn('Cached component failed checks', result['error'])

    def test_invalid_cached_code_can_only_fall_back_with_a_counted_provider_call(self):
        req = request(max_calls=1); self.seed(req, BAD)
        apps = Apps(); result = self.run_mica('repair-cache', apps, req)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.calls), 1)
        self.assertFalse(result['attempts'][0]['decisions'][0]['reused'])


if __name__ == '__main__':
    unittest.main()
