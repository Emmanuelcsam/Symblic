"""Delegation routes of the original host: its `delegate/...` HTTP API (catalog, compile, run, result, resume)
and the declaration it stores with a run.

Moved from tests/delegate/ (the pure parts stay there and test symblic.delegate). These cases drive
integration/host/symblic_engine.py with the fake store in fake_host_apps.py standing in for the host's run store,
so they run without the host.
"""
import unittest

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
    from tests.integration.test_symblic_engine import Base
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

import copy
import json
from pathlib import Path
from unittest.mock import patch

from symblic.delegate import run as R
from symblic.js import check as JS
from symblic.kernel.run import run_folder
from tests.delegate.test_symblic_delegate import ARITHMETIC
from tests.delegate.test_symblic_delegate_routing import SMALL, TINY, TRANSFORM
from tests.delegate.test_symblic_delegate_proof_card import card_task
from tests.delegate.test_symblic_delegate_proof_focus import prefix


from tests.integration import fake_host_apps  # noqa: E402

# The host's store, faked when the host is absent; see fake_host_apps.py.
setUpModule, tearDownModule = fake_host_apps.module_fixture()


class RoutingAPI(Base):
    def setUp(self):
        super().setUp()
        patcher = patch.object(JS, 'node_version', return_value='test-no-node')
        patcher.start(); self.addCleanup(patcher.stop)

    def test_default_api_runs_native_route_and_returns_bound_identity(self):
        self.apps.answer = lambda app, prompt: {'answer': [1, 1] if app == TINY else [1, 2]}
        started = self.call('POST', 'delegate/run', {'task': TRANSFORM})
        self.assertEqual(started.status, 200, started.sent)
        result = self.call('GET', 'delegate/result', query={'id': started.sent['id']})
        self.assertEqual(result.status, 200, result.sent)
        self.assertTrue(result.sent['accepted'])
        self.assertEqual(result.sent['routing_id'], started.sent['routing_id'])
        self.assertEqual(result.sent['routing']['model_budget']['used'], 2)
        self.assertEqual([row['app']['spec'] for row in self.apps.calls], [TINY, SMALL])
        meta = json.loads(Path(E.run_dir(started.sent['id']), 'meta.json').read_text())
        self.assertEqual(meta['options']['by'], 'auto')
        self.assertEqual(meta['options']['auto_route']['declared_repairs'], 'shared')
        self.assertEqual(meta['delegation']['routing_id'], started.sent['routing_id'])

    def test_exact_list_and_single_string_preserved(self):
        self.assertEqual(E._clean_delegate_by(['fake:a']), ['fake:a'])
        self.apps.answer = lambda app, prompt: {'answer': [1, 2]}
        for by in ('fake:a', ['fake:a'], ['fake:a', 'fake:b']):
            started = self.call('POST', 'delegate/run', {'task': TRANSFORM, 'by': by})
            self.assertEqual(started.status, 200, started.sent)
            meta = json.loads(Path(E.run_dir(started.sent['id']), 'meta.json').read_text())
            self.assertEqual(meta['by'], by)
            self.assertEqual(meta['options']['by'], 'fake:a' if type(by) is str else 'auto')

    def test_bad_raw_routes_refuse_without_launch_or_truncation(self):
        for bad in ([], ['fake:a'] * 13, ['fake:a'] * 17, [None], [{'app': 'fake:a'}], True, 3,
                    ['fake:a', ' fake:a '], 'auto', ['fake:a', 'council']):
            with self.subTest(by=bad):
                response = self.call('POST', 'delegate/run', {'task': TRANSFORM, 'by': bad})
                self.assertEqual(response.status, 400, response.sent)
        self.assertEqual(self.launches, [])
        self.assertEqual(self.apps.calls, [])

    def test_route_option_pin_and_declaration_tampering_refuse(self):
        started = self.call('POST', 'delegate/run', {'task': ARITHMETIC})
        self.assertEqual(started.status, 200, started.sent)
        path = Path(E.run_dir(started.sent['id']), 'meta.json')
        original = json.loads(path.read_text())
        changes = [lambda m: m['options'].update(by='claude:haiku'),
                   lambda m: m['options'].update(auto_route={'candidates': ['claude:haiku']}),
                   lambda m: m['options'].update(max_calls=1),
                   lambda m: m['options'].update(certificate={}),
                   lambda m: m['delegation'].update(routing_id='0' * 64),
                   lambda m: m['delegation']['routing'].update(allow_cloud=True),
                   lambda m: m['options']['execution_pins'].update(sha256='0' * 64)]
        for change in changes:
            value = copy.deepcopy(original); change(value); path.write_text(json.dumps(value))
            response = self.call('GET', 'delegate/result', query={'id': started.sent['id']})
            self.assertEqual(response.status, 400, response.sent)
        self.assertEqual(self.apps.calls, [])

    def test_explicit_cloud_only_by_exact_owner_choice(self):
        self.apps.answer = lambda app, prompt: {'answer': [1, 2]}
        started = self.call('POST', 'delegate/run', {'task': TRANSFORM, 'by': ['claude:haiku']})
        self.assertEqual(started.status, 200, started.sent)
        self.assertTrue(started.sent['routing']['allow_cloud'])
        self.assertEqual(self.apps.calls[0]['app']['spec'], 'claude:haiku')

    def test_resume_and_direct_worker_refuse_changed_policy_before_provider(self):
        started = self.call('POST', 'delegate/run', {'task': ARITHMETIC})
        self.assertEqual(started.status, 200, started.sent)
        folder = Path(E.run_dir(started.sent['id']))
        prior = (folder / 'state.json').read_bytes()
        path = folder / 'meta.json'
        meta = json.loads(path.read_text())
        meta['options']['by'] = 'claude:haiku'
        path.write_text(json.dumps(meta))
        launches = list(self.launches)
        response = self.call('POST', 'resume', {'id': started.sent['id']})
        self.assertEqual(response.status, 400, response.sent)
        self.assertEqual(self.launches, launches)
        with patch('symblic.providers.applicators.Applicators', side_effect=AssertionError('no provider construction')):
            refused = run_folder(str(folder), resume=True)
        self.assertEqual(refused['status'], 'failed')
        self.assertEqual(refused['calls'], 0)
        self.assertTrue((folder / 'delegation-refusal.json').is_file())
        self.assertEqual((folder / 'state.json').read_bytes(), prior)

    def test_legacy_single_string_contract_remains_readable(self):
        task = R.prepare(TRANSFORM, by='fake:a')
        declaration = {key: task[key] for key in ('contract_id', 'template_id', 'output_binding', 'assurance')}
        declaration['request'] = TRANSFORM
        self.assertEqual(E._delegation_contract(declaration, task['source'], task['inputs'], task['options'])['contract_id'],
                         task['contract_id'])
        altered = {**task['options'], 'auto_route': {'candidates': ['claude:haiku']}}
        with self.assertRaises(E.SymblicApiError):
            E._delegation_contract(declaration, task['source'], task['inputs'], altered)


class DelegationAPI(Base):
    def test_catalog_compile_run_and_exact_missing_worker_result(self):
        catalog = self.call('GET', 'delegate/catalog')
        self.assertEqual(len(catalog.sent['templates']), 9)
        checked = self.call('POST', 'delegate/compile', ARITHMETIC)
        self.assertTrue(checked.sent['ok'])
        with patch('integration.host.symblic_engine.start_run', side_effect=lambda body, **kw: {'id':'fixture','body':body,'declaration':kw['delegation']}):
            started = self.call('POST', 'delegate/run', {'task':ARITHMETIC})
        self.assertEqual(started.status, 200, started.sent)
        self.assertEqual(started.sent['declaration']['contract_id'], checked.sent['contract_id'])
        self.assertIn('execution_pins', started.sent['body']['options'])
        self.assertEqual(started.sent['body']['options']['max_calls'], 0)
        self.assertEqual(self.call('POST', 'delegate/run', {'task':{'template':'unknown'}}).status, 400)


class DelegateResult(Base):
    def result(self, ident):
        return self.call('GET', 'delegate/result', query={'id': ident})

    def test_exact_result_and_record_tampering(self):
        started = self.call('POST', 'delegate/run', {'task': ARITHMETIC})
        self.assertEqual(started.status, 200, started.sent)
        ident = started.sent['id']
        result = self.result(ident)
        self.assertEqual(result.status, 200, result.sent)
        self.assertTrue(result.sent['accepted'])
        self.assertEqual(result.sent['result'], {'#q': '1/2'})
        self.assertNotIn('request', result.sent)
        folder = Path(E.run_dir(ident))
        originals = {name: (folder / name).read_text() for name in ('program.sym', 'meta.json', 'state.json')}
        state = json.loads(originals['state.json'])
        meta = json.loads(originals['meta.json'])
        mutations = [
            ('program.sym', originals['program.sym'] + '\nshow 7.\n'),
            ('meta.json', {**meta, 'inputs': {**meta['inputs'], 'left': 9}}),
            ('meta.json', {**meta, 'options': {**meta['options'], 'side_effects': True}}),
            ('meta.json', {**meta, 'delegation': {**meta['delegation'], 'contract_id': '0' * 64}}),
            ('state.json', {**state, 'error': {'message': 'failed'}}),
            ('state.json', {**state, 'kernel': {}}),
            ('state.json', {**state, 'kernel': 'invalid'}),
            ('state.json', {**state, 'bindings': [None]}),
            ('state.json', {**state, 'outputs': {'canonical': 7}}),
            ('meta.json', []),
            ('state.json', {**state, 'outputs': state['outputs'] * 2}),
        ]
        for field, value in [('canonical', 7), ('canonical_version', 999), ('binding', 'other'),
                             ('line', 999), ('kind', 'draw'), ('hash', '0' * 16)]:
            altered = copy.deepcopy(state)
            altered['outputs'][0][field] = value
            mutations.append(('state.json', altered))
        altered = copy.deepcopy(state)
        altered['bindings'] = []
        mutations.append(('state.json', altered))
        for name, value in mutations:
            with self.subTest(name=name, value=value):
                for original, raw in originals.items():
                    (folder / original).write_text(raw)
                (folder / name).write_text(value if isinstance(value, str) else json.dumps(value))
                refused = self.result(ident)
                self.assertEqual(refused.status, 400, refused.sent)
                self.assertNotIn('accepted', refused.sent)

    def test_unfinished_output_is_not_promoted(self):
        started = self.call('POST', 'delegate/run', {'task': ARITHMETIC})
        ident = started.sent['id']
        path = Path(E.run_dir(ident), 'state.json')
        state = json.loads(path.read_text())
        state['status'] = 'stopped'
        path.write_text(json.dumps(state))
        result = self.result(ident)
        self.assertEqual(result.status, 200, result.sent)
        self.assertFalse(result.sent['accepted'])
        self.assertIsNone(result.sent['result'])

    def test_summary_is_transported_without_inventing_missing_observations(self):
        started = self.call('POST', 'delegate/run', {'task': ARITHMETIC})
        ident = started.sent['id']
        path = Path(E.run_dir(ident), 'state.json')
        state = json.loads(path.read_text())
        state.pop('determinism_summary', None)
        path.write_text(json.dumps(state))
        self.assertNotIn('determinism_summary', self.result(ident).sent)
        summary = {'version': 1, 'determined': 2, 'unassessed': 1, 'cloud_accepted': 0}
        state['determinism_summary'] = summary
        path.write_text(json.dumps(state))
        self.assertEqual(self.result(ident).sent['determinism_summary'], summary)


class DelegateCardRoute(unittest.TestCase):
    def test_existing_api_declaration_preserves_card_authority(self):
        body = card_task(prefix({'a': ['atom', 'A']}), ['premise a'], '"A"')
        with patch.object(E, 'start_run', return_value={'ok': True, 'id': 'fake'}) as start:
            result = E.delegate_run({'task': body, 'by': 'fake:a'})
        saved, declaration = start.call_args.args[0], start.call_args.kwargs['delegation']
        self.assertEqual(result['contract_id'], declaration['contract_id'])
        E._delegation_contract(declaration, saved['source'], saved['inputs'], saved['options'])
        forged = copy.deepcopy(saved['inputs']); forged['task_card'][0][1]['formula'] = '"Changed"'
        with self.assertRaises(E.SymblicApiError):
            E._delegation_contract(declaration, saved['source'], forged, saved['options'])


if __name__ == '__main__':
    unittest.main()
