"""Host-only: the original host's run API with constructor options (start policy, resume refusals, routing).

Moved from tests/constructor. These cases drive integration/host/symblic_engine.py and the host's application
router (host_apps), scheduler (automation_engine) and access gate (security_gate), which are not part of this
repository, so they are skipped when those modules are absent. Temporary stores and fake launchers; no
constructor, solver or provider is dispatched.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import automation_engine as AE
    import host_apps
    import security_gate as SG
    from integration.host import symblic_engine as E
    from tests.integration.test_symblic_proof_step_entry import RoutedHandler
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

import symblic.kernel
from symblic.kernel import run as R
from symblic.providers import applicators as A
from symblic.delegate import run as D
from symblic.kernel import execution_pins as X
from tests.delegate.test_symblic_delegate import ARITHMETIC

SOURCE = 'ask n: Int "Choose one integer.".\nshow n.\n'
LIMITS = {'attempts': 2, 'milliseconds': 2000, 'attempt_ms': 1000, 'resource_limit': 10000}


class ConstructorAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/dev/shm')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launch = mock.Mock(return_value={'ok': True})
        self.root_call = mock.Mock(return_value=str(self.root))
        for patch in (mock.patch.object(E, 'root', self.root_call),
                      mock.patch.dict(E.launcher, {'launch': self.launch}),
                      mock.patch.object(A, 'Applicators', side_effect=AssertionError('provider created')),
                      mock.patch.object(AE, '_ensure_started', side_effect=AssertionError('scheduler')),
                      mock.patch.dict(host_apps._modules, {'automation_engine': AE}),
                      mock.patch.object(SG, 'OWNER_EMAILS', {'owner@example.test'})):
            patch.start(); self.addCleanup(patch.stop)

    def body(self, options=None, source=SOURCE):
        result = {'source': source, 'by': 'fake:a'}
        if options is not None:
            result['options'] = options
        return result

    def start(self, options=None, **kwargs):
        result = E.start_run(self.body(options), **kwargs)
        folder = self.root / 'runs' / result['id']
        return result, json.loads((folder / 'meta.json').read_text())

    def refuses(self, options, text=None, source=SOURCE):
        with self.assertRaises(E.SymblicApiError) as caught:
            E.start_run(self.body(options, source))
        if text:
            self.assertIn(text, str(caught.exception))
        self.root_call.assert_not_called(); self.launch.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def routed(self, data, identity=None):
        handler = RoutedHandler('run', identity=identity)
        self.assertTrue(host_apps.handle_post(handler, data))
        return handler

    def test_absence_retains_exact_default_metadata_and_does_not_request_validator(self):
        with mock.patch.object(R, 'validate_constructor_options', side_effect=AssertionError('new policy requested')):
            result, meta = self.start({'parallel': 1})
        self.assertEqual(set(result), {'id', 'title'})
        self.assertEqual(meta['options'], {'profile': 'legacy', 'by': 'fake:a', 'parallel': 1})
        self.assertEqual(self.launch.call_count, 1)

    def test_enabled_modes_normalize_complete_limits_and_host_solve_off(self):
        for mode in ('linear_diagnose', 'linear'):
            for supplied in (None, LIMITS):
                raw = {'constructor': mode, 'determine': False}
                if supplied is not None:
                    raw['constructor_limits'] = copy.deepcopy(supplied)
                old = copy.deepcopy(raw)
                _, meta = self.start(raw)
                expected = R.validate_constructor_options(raw)
                self.assertEqual(meta['options']['constructor'], mode)
                self.assertEqual(meta['options']['constructor_limits'], expected['limits'])
                self.assertIs(meta['options']['determine'], False); self.assertIs(meta['options']['solve'], False)
                self.assertEqual(R.validate_constructor_options(meta['options']), expected)
                self.assertEqual(raw, old)
        self.assertEqual(self.launch.call_count, 4)

    def test_explicit_off_and_limits_only_are_detached_and_preserve_other_options(self):
        for raw in ({'constructor': 'off', 'constructor_limits': dict(LIMITS)},
                    {'constructor_limits': dict(LIMITS)}):
            _, meta = self.start(raw)
            self.assertEqual(meta['options'], {'profile': 'legacy', 'by': 'fake:a', 'constructor': 'off',
                                               'constructor_limits': LIMITS})
            raw['constructor_limits']['attempts'] = 1
            self.assertEqual(meta['options']['constructor_limits']['attempts'], 2)

    def test_invalid_modes_and_runtime_path_names_refuse_before_any_store(self):
        for mode in (None, False, 0, '', 'LINEAR', 'auto', 'off ', [], {}):
            with self.subTest(mode=mode):
                self.refuses({'constructor': mode}, 'constructor')
        for name in ('constructor_runtime', 'constructor_path', 'constructor_worker', 'constructor_', 'constructor_python'):
            for mode in ('off', 'linear'):
                with self.subTest(name=name, mode=mode):
                    self.refuses({'constructor': mode, 'determine': False, name: '/untrusted/path'}, 'unknown constructor')

    def test_exact_limit_types_keys_and_bounds_refuse_before_any_store(self):
        invalid = [None, [], '', {}, {**LIMITS, 'worker': '/untrusted/path'}]
        for key, high in {'attempts': 64, 'milliseconds': 320000, 'attempt_ms': 5000, 'resource_limit': 1000000}.items():
            invalid.append({k: v for k, v in LIMITS.items() if k != key})
            invalid.extend({**LIMITS, key: value} for value in (True, False, 0, -1, high + 1, 1.0, '1'))
        invalid.append({**LIMITS, 'milliseconds': 999})
        class Record(dict):
            pass
        invalid.append(Record(LIMITS))
        for limits in invalid:
            with self.subTest(limits=limits):
                self.refuses({'constructor': 'off', 'constructor_limits': limits}, 'constructor_limits')

    def test_enabled_requires_exact_host_determine_false_and_effectively_off_solve(self):
        for value in (None, True, 0, 'false', [], {}):
            with self.subTest(determine=value):
                self.refuses({'constructor': 'linear', 'determine': value}, 'determine=false')
        self.refuses({'constructor': 'linear'}, 'determine=false', 'use determine=false.\n' + SOURCE)
        for value in (True, 1, 'off', 'false', 'auto', ['false'], {'off': False}):
            with self.subTest(solve=value):
                self.refuses({'constructor': 'linear', 'determine': False, 'solve': value}, 'solve off')

    def test_existing_profile_by_model_and_execution_pins_are_preserved(self):
        hashes = {name: X._sha(X._read(name)) for name in sorted(X.REQUIRED_FILES)}
        pins = X.build(SOURCE, {}, hashes)
        options = {'constructor': 'linear', 'determine': False, 'profile': 'verified', 'max_calls': 3,
                   'parallel': 1, 'model_pins': 'strict', 'execution_pins': pins}
        with mock.patch.object(E, 'strict_model_pins_available', return_value=True):
            _, meta = self.start(options)
        self.assertEqual(meta['options']['profile'], 'verified'); self.assertEqual(meta['options']['by'], 'fake:a')
        self.assertEqual(meta['options']['model_pins'], 'strict'); self.assertEqual(meta['options']['execution_pins'], pins)
        self.assertEqual((meta['options']['max_calls'], meta['options']['parallel']), (3, 1))

    def test_delegation_exact_contract_cannot_gain_constructor_authority(self):
        task = D.prepare(ARITHMETIC)
        declaration = {**{key: task[key] for key in ('contract_id', 'template_id', 'output_binding', 'assurance',
                                                    'routing', 'routing_id')}, 'request': copy.deepcopy(ARITHMETIC)}
        legacy = {key: value for key, value in declaration.items() if key not in ('routing', 'routing_id')}
        for authority in (declaration, legacy):
            for extra in ({'constructor': 'off'}, {'constructor': 'linear', 'determine': False},
                          {'constructor_limits': dict(LIMITS)}):
                with self.subTest(routed='routing' in authority, extra=extra), self.assertRaises(E.SymblicApiError):
                    E.start_run({'source': task['source'], 'inputs': task['inputs'],
                                 'options': {**task['options'], **extra}}, delegation=authority)
                self.root_call.assert_not_called(); self.launch.assert_not_called()
        result = E.delegate_run({'task': ARITHMETIC})
        meta = json.loads((self.root / 'runs' / result['id'] / 'meta.json').read_text())
        self.assertEqual(meta['options'], task['options']); self.assertNotIn('constructor', meta['options'])

    def test_missing_shared_validator_has_restart_refusal_before_store(self):
        stub = types.ModuleType('symblic.kernel.run')
        with mock.patch.dict(sys.modules, {'symblic.kernel.run': stub}), mock.patch.object(symblic.kernel, 'run', stub):
            self.refuses({'constructor': 'off'}, 'update and restart')

    def test_owner_route_maps_policy_errors_and_nonowner_cannot_reach_engine(self):
        for options in ({'constructor_runtime': '/untrusted'}, {'constructor': 'linear'},
                        {'constructor': False}, {'constructor_limits': []}):
            handler = self.routed(self.body(options))
            self.assertEqual(handler.status, 400, handler.sent); self.assertEqual(set(handler.sent), {'error'})
        with mock.patch.object(E, 'start_run', side_effect=AssertionError('nonowner reached engine')):
            handler = self.routed(self.body({'constructor': 'linear', 'determine': False}), SG.Identity(SG.ANONYMOUS))
        self.assertEqual(handler.status, 403); self.root_call.assert_not_called(); self.launch.assert_not_called()
        handler = self.routed(self.body({'constructor': 'linear_diagnose', 'determine': False}))
        self.assertEqual(handler.status, 200, handler.sent); self.assertEqual(self.launch.call_count, 1)

    def test_resume_missing_constructor_records_refuses_before_launch_or_writes(self):
        from symblic.constructor import core as C
        from symblic.constructor import journal as J
        from tests.constructor.test_symblic_constructor_run import Apps, SOURCE as BUILT_SOURCE, fake_runtime, helper

        for mode in ('linear', 'linear_diagnose'):
            for removed in ((J.FILE,), (C.R.CONFIG_FILE,), (J.FILE, C.R.CONFIG_FILE)):
                with self.subTest(mode=mode, removed=removed):
                    started = E.start_run({'source': BUILT_SOURCE, 'by': 'fake:a', 'options': {
                        'constructor': mode, 'determine': False, 'profile': 'verified'}})
                    folder = self.root / 'runs' / started['id']
                    meta = json.loads((folder / 'meta.json').read_text())
                    with mock.patch.object(C, '_runtime', return_value=fake_runtime()), \
                            mock.patch.object(C.L, 'assess_ask', side_effect=helper()):
                        result = R.Run(BUILT_SOURCE, applicators=Apps(), options=meta['options'],
                                       folder=str(folder)).execute()
                    self.assertEqual(result['status'], 'done', result.get('error'))
                    for name in removed:
                        (folder / name).unlink()
                    before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
                    self.launch.reset_mock()
                    with mock.patch.dict(E.launcher, {'active': lambda _id: False}), \
                            mock.patch.object(C, '_runtime', side_effect=AssertionError('runtime read')), \
                            mock.patch.object(C.L, 'assess_ask', side_effect=AssertionError('worker call')):
                        with self.assertRaises(E.SymblicApiError) as caught:
                            E.resume_run(started['id'])
                    self.assertIn('constructor', str(caught.exception).lower())
                    self.launch.assert_not_called()
                    self.assertEqual(before, {str(p.relative_to(folder)): p.read_bytes()
                                              for p in folder.rglob('*') if p.is_file()})

    def test_resume_without_attempts_preserves_constructor_and_ordinary_runs(self):
        for options in ({}, {'constructor': 'linear', 'determine': False}):
            started = E.start_run({'source': 'show 3.', 'options': options})
            folder = self.root / 'runs' / started['id']
            meta = json.loads((folder / 'meta.json').read_text())
            result = R.Run('show 3.', options=meta['options'], folder=str(folder)).execute()
            self.assertEqual(result['status'], 'done', result.get('error'))
            before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
            self.launch.reset_mock()
            with mock.patch.dict(E.launcher, {'active': lambda _id: False}):
                self.assertEqual(E.resume_run(started['id']), {'ok': True})
            self.launch.assert_called_once_with(started['id'], str(folder), True)
            self.assertEqual(before, {str(p.relative_to(folder)): p.read_bytes()
                                      for p in folder.rglob('*') if p.is_file()})

    def test_resume_damaged_marker_refuses_before_launch_or_writes(self):
        for mode in ('linear', 'linear_diagnose'):
            started = E.start_run({'source': SOURCE, 'options': {'constructor': mode, 'determine': False}})
            folder = self.root / 'runs' / started['id']
            for marker in (True, False, 2.0, '2', None, [2], {}, 1, 3):
                with self.subTest(mode=mode, marker=marker):
                    (folder / 'state.json').write_text(json.dumps({
                        'status': 'running', 'constructor_bridge': marker, 'calls': 0, 'asks': 0}))
                    before = {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
                              for p in folder.rglob('*') if p.is_file()}
                    self.launch.reset_mock()
                    with mock.patch.dict(E.launcher, {'active': lambda _id: False}):
                        with self.assertRaises(E.SymblicApiError) as caught:
                            E.resume_run(started['id'])
                    self.assertIn('constructor', str(caught.exception).lower())
                    self.launch.assert_not_called()
                    self.assertEqual(before, {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
                                              for p in folder.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main(verbosity=2)
