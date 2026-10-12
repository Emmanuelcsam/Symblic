"""Native handoff and durable workflow tests; all stores, launches and clocks isolated.

HOST-ONLY: integration/host/symblic_supervisor.py runs its steps through the original host's runner and
scheduler (host_runner, host_planner, host_sched, host_triggers, host_tools, host_store, host_bridge), which
are not part of this repository, so these tests are skipped when those modules cannot be imported.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:  # host-only: these modules belong to the private host system Symblic was built in
    import host_runner as C
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.kernel import effects as FX
from symblic.kernel import run as SR
from integration.host import symblic_supervisor as W
from integration.host import symblic_supervisor_api as A

SOURCE = 'let result = 2 + 3.\nassert result = 5.\nshow result.\n'


def definition(steps=None):
    return {'version': 1, 'name': 'Exact workflow fixture', 'state': {'ready': False, 'count': 0},
            'max_parallel': 2, 'steps': steps or [{'id': 'calculate', 'kind': 'run', 'source': SOURCE, 'deadline_s': 120}]}


class NoModels:
    def call(self, req):
        raise AssertionError('No real or fake model call in a pure native fixture')


class Journey(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.now = 1000.0
        self.triggers = {}
        self.launches = []
        self.execute = False
        self.native = self.base / 'native'
        self.store = self.base / 'workflows'
        self.store.mkdir()
        conf = {**copy.deepcopy(C.DEFAULT_SETTINGS), 'routing': {'max_calls': 2, 'allow_cloud': False, 'repairs': 0}}
        def ensure(row):
            self.triggers.setdefault(row['key'], {**copy.deepcopy(row), 'enabled': row.get('enabled', True)})
            return {'errors': {}}
        def enable(key, value):
            if key not in self.triggers:
                return False
            self.triggers[key]['enabled'] = value
            return True
        scheduler = {'ensure': ensure, 'enable': enable, 'get': lambda key: self.triggers.get(key),
                     'id': lambda key: 't_' + W.digest(key)[:12], 'drop': lambda key: self.triggers.pop(key, None)}
        def launch(unit, command):
            folder = Path(command[-1])
            self.launches.append(folder.name)
            if self.execute:
                meta = json.loads((folder / 'meta.json').read_text())
                run = SR.Run((folder / 'program.sym').read_text(), meta['inputs'], NoModels(),
                             {**meta['options'], 'parallel': 1}, folder=None)
                result = run.execute()
                (folder / 'state.json').write_text(json.dumps(result))
            return {'ok': True}
        def active(unit):
            folder = self.native / 'runs' / unit.removeprefix('runner-')
            try:
                status = json.loads((folder / 'state.json').read_text()).get('status')
            except (ValueError, OSError):
                status = None
            return status not in ('done', 'failed') and not self.execute
        for obj, name, value in (
            (W, 'root', lambda: self.store), (W, 'clock', lambda: self.now),
            (C, 'root', lambda: str(self.native)), (C, 'catalogue_rows', lambda: []),
            (C, 'settings', lambda: copy.deepcopy(conf)), (C, 'scheduler', scheduler),
            (C, 'check', lambda source: FX.check(source, [])),
            (C, 'launcher', {'launch': launch, 'active': active, 'stop': lambda *_: True}),
        ):
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch('socket.socket', side_effect=AssertionError('No network in supervisor tests'))
        p.start()
        self.addCleanup(p.stop)

    def new(self, steps=None, token='create-fixture'):
        return W.create(definition(steps), token)

    def complete(self, native_id, status='done', phases=()):
        folder = self.native / 'runs' / native_id
        (folder / 'state.json').write_text(json.dumps({'status': status, 'fingerprint': 'fixture',
                                                      'error': {'message': 'fixture failure'} if status == 'failed' else None}))
        (folder / FX.LEDGER).write_text(''.join(json.dumps({'id': str(i), 'kind': 'act', 'phase': phase}) + '\n'
                                               for i, phase in enumerate(phases)))

    def test_native_start_actual_kernel_and_join_persistent_counter(self):
        self.execute = True
        v = self.new([{'id': 'a', 'kind': 'run', 'source': SOURCE},
                      {'id': 'b', 'kind': 'run', 'source': SOURCE},
                      {'id': 'join', 'kind': 'join', 'after': ['a', 'b']},
                      {'id': 'state', 'kind': 'set', 'after': ['join'], 'changes': {'count': {'increment': 1}}}])
        v = W.start(v['id'], 'start-once')
        self.assertEqual(len(self.launches), 2)
        self.assertEqual(v['jobs'][-1]['steps']['join']['status'], 'pending')
        self.assertTrue(v['pulse']['enabled'])
        v = W.tick(v['id'])
        self.assertEqual(v['jobs'][-1]['status'], 'done')
        self.assertEqual(v['state']['count'], 1)
        self.assertFalse(v['pulse']['enabled'])
        native = C.run_view(self.launches[0])
        self.assertEqual(native['status'], 'done')
        self.assertIn('5', native['report']['outputs'][0]['text'])
        self.assertEqual(native['options']['execution_pins'], v['frozen']['a']['options']['execution_pins'])
        W.start(v['id'], 'start-once')
        self.assertEqual(len(self.launches), 2)
        self.assertEqual(W.view(v['id'])['state']['count'], 1)

    def test_lost_reply_never_resubmits_and_reconcile_requires_exact_identity(self):
        v = self.new()
        actual = C.start_run
        def lost(body, **kwargs):
            actual(body, **kwargs)
            raise OSError('connection lost after native launch')
        with patch.object(C, 'start_run', side_effect=lost):
            v = W.start(v['id'], 'start-once')
        job = v['jobs'][-1]
        self.assertEqual(job['steps']['calculate']['status'], 'unknown')
        self.assertEqual(len(self.launches), 1)
        W.start(v['id'], 'start-once')
        W.tick(v['id'])
        self.assertEqual(len(self.launches), 1)
        wrong = actual({'source': SOURCE, 'inputs': {}})['id']
        with self.assertRaises(W.SupervisorError):
            W.reconcile(v['id'], job['id'], 'calculate', wrong)
        v = W.reconcile(v['id'], job['id'], 'calculate', self.launches[0])
        self.assertEqual(v['jobs'][-1]['steps']['calculate']['native_id'], self.launches[0])
        self.assertEqual(len(self.launches), 2)  # the separately created wrong fixture, never a workflow retry

    def test_crash_after_persisted_intent_is_unknown_without_submission(self):
        v = self.new()
        def crash(_body, **_kwargs):
            raise KeyboardInterrupt('simulate process death')
        with patch.object(C, 'start_run', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                W.start(v['id'], 'start-once')
        v = W.view(v['id'])
        self.assertEqual(v['jobs'][0]['steps']['calculate']['status'], 'submitting')
        v = W.tick(v['id'])
        self.assertEqual(v['jobs'][0]['steps']['calculate']['status'], 'unknown')
        self.assertEqual(self.launches, [])

    def test_deadline_and_uncertain_effect_do_not_activate_compensation(self):
        v = self.new([{'id': 'a', 'kind': 'run', 'source': SOURCE, 'deadline_s': 10},
                      {'id': 'undo', 'kind': 'run', 'source': SOURCE, 'on_failure': 'a'}])
        v = W.start(v['id'], 'start')
        self.now += 20
        v = W.tick(v['id'])
        self.assertEqual(v['jobs'][0]['steps']['a']['status'], 'overdue')
        self.assertEqual(v['jobs'][0]['steps']['undo']['status'], 'pending')
        self.assertFalse(v['pulse']['enabled'])
        self.complete(self.launches[0], 'failed', ['unknown'])
        v = W.tick(v['id'])
        self.assertNotEqual(v['jobs'][0]['steps']['a']['status'], 'failed')
        self.assertEqual(len(self.launches), 1)
        self.complete(self.launches[0], 'failed', ['done'])
        # A definite failed native run may have completed earlier effects. The
        # owner's explicit compensating program is a new, separately journaled run.
        v = W.tick(v['id'])
        self.assertEqual(v['jobs'][0]['steps']['a']['status'], 'failed')
        self.assertEqual(len(self.launches), 2)

    def test_bounded_wait_state_revision_and_persistent_state_across_firings(self):
        v = self.new([{'id': 'wait', 'kind': 'wait', 'until': {'state': 'ready', 'equals': True}, 'within_s': 60},
                      {'id': 'increment', 'kind': 'set', 'after': ['wait'], 'changes': {'count': {'increment': 1}}}])
        v = W.start(v['id'], 'first')
        with self.assertRaises(W.Conflict):
            W.mutate(v['id'], v['revision'] - 1, 'state', 'state', {'ready': True})
        v = W.mutate(v['id'], v['revision'], 'state', 'state', {'ready': True})
        self.assertEqual(v['jobs'][0]['status'], 'done')
        self.assertEqual(v['state']['count'], 1)
        W.mutate(v['id'], -1, 'state', 'state', {'ready': True})  # retry same identity
        v = W.start(v['id'], 'second')
        self.assertEqual(v['state']['count'], 2)
        self.assertEqual(self.launches, [])

    def test_wait_timeout_is_definite_local_failure_and_handler_runs(self):
        v = self.new([{'id': 'wait', 'kind': 'wait', 'until': {'state': 'ready', 'equals': True}, 'within_s': 10},
                      {'id': 'record', 'kind': 'set', 'on_failure': 'wait', 'changes': {'timed_out': {'set': True}}}])
        v = W.start(v['id'], 'once')
        self.now += 11
        v = W.tick(v['id'])
        self.assertEqual(v['state']['timed_out'], True)
        self.assertEqual(v['jobs'][0]['status'], 'failed')
        self.assertFalse(v['pulse']['enabled'])

    def test_overlap_recorded_and_parallel_bound(self):
        v = self.new([{'id': name, 'kind': 'run', 'source': SOURCE} for name in ['a', 'b', 'c']])
        v = W.start(v['id'], 'one')
        self.assertEqual(len(self.launches), 2)
        v = W.start(v['id'], 'two')
        self.assertEqual(v['jobs'][1]['status'], 'skipped')
        self.assertEqual(v['jobs'][1]['reason'], 'previous_firing_unfinished')
        self.complete(self.launches[0])
        W.tick(v['id'])
        self.assertEqual(len(self.launches), 3)

    def test_metadata_only_trusted_scheduler_firing_and_duplicate_delivery(self):
        v = self.new()
        v = W.schedule(v['id'], '*/5 * * * *', True, v['revision'])
        ctx = {'trigger': v['schedule']['trigger'], 'mission': 'mission-fixture', 'step': 'step-fixture',
               'origin': {'payload': {'instruction': 'malicious injected text'}}}
        self.assertFalse(W.fire_tool({'workflow': v['id'], 'trigger': ctx['trigger']})['ok'])
        result = W.fire_tool({'workflow': v['id']}, ctx)
        self.assertTrue(result['ok'], result)
        self.assertTrue(W.fire_tool({'workflow': v['id']}, ctx)['ok'])
        self.assertEqual(len(self.launches), 1)
        row = W.view(v['id'])
        self.assertEqual(len(row['jobs']), 1)
        self.assertNotIn('malicious', json.dumps(row))
        native = C.run_view(self.launches[0])
        self.assertEqual(native['inputs'], {})

    def test_owner_disabled_pulse_is_respected_until_explicit_resume(self):
        v = W.start(self.new()['id'], 'once')
        self.triggers[v['pulse']['key']]['enabled'] = False
        v = W.tick(v['id'])
        self.assertIn('owner disabled', v['clock_error'])
        self.assertFalse(self.triggers[v['pulse']['key']]['enabled'])
        v = W.mutate(v['id'], v['revision'], 'resume', 'pause', False)
        self.assertTrue(self.triggers[v['pulse']['key']]['enabled'])
        self.assertNotIn('clock_error', v)

    def test_pause_does_not_stop_native_and_blocks_new_dispatch(self):
        v = W.start(self.new()['id'], 'once')
        v = W.mutate(v['id'], v['revision'], 'pause', 'pause', True)
        self.assertFalse(v['pulse']['enabled'])
        v = W.start(v['id'], 'while-paused')
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(v['jobs'][-1]['reason'], 'workflow_paused')

    def test_simulation_never_launches_or_saves_and_unknown_is_default(self):
        spec = definition([{'id': 'a', 'kind': 'run', 'source': SOURCE},
                           {'id': 'undo', 'kind': 'set', 'on_failure': 'a', 'changes': {'undo': {'set': True}}}])
        result = W.simulate(spec)
        self.assertTrue(result['simulation'])
        self.assertFalse(result['executed'])
        self.assertEqual(result['steps']['a']['status'], 'unknown')
        self.assertEqual(result['steps']['undo']['status'], 'pending')
        self.assertEqual(list(self.store.iterdir()), [])
        self.assertEqual(self.launches, [])
        result = W.simulate(spec, {'a': 'failed'})
        self.assertEqual(result['state']['undo'], True)

    def test_create_identity_and_exact_definition_are_immutable(self):
        v = self.new()
        self.assertEqual(self.new()['id'], v['id'])
        with self.assertRaises(W.Conflict):
            W.create({**definition(), 'name': 'changed'}, 'create-fixture')
        with self.assertRaises(W.SupervisorError):
            W.create(definition([{'id': 'a', 'kind': 'run', 'source': 'let x = (.'}]), 'bad')
        self.assertEqual(self.launches, [])

    def test_cycle_unknown_fields_and_nonfinite_refused(self):
        for spec in [definition([{'id': 'a', 'kind': 'join', 'after': ['a']}]),
                     {**definition(), 'arbitrary_host_executor': 'shell'},
                     definition([{'id': 'a', 'kind': 'delay', 'seconds': float('nan')}])]:
            with self.subTest(spec=spec):
                with self.assertRaises(W.SupervisorError):
                    W.validate(spec)

    def test_metadata_event_attachment_rechecks_frozen_trigger_and_never_takes_payload(self):
        v = self.new()
        trigger = {'id': 't_abcdef012345', 'kind': 'file', 'spec': {'path': '/synthetic'},
                   'action': {'type': 'mission.start', 'kind': 'single',
                              'spec': {'tool': 'runner.supervise', 'args': {'workflow': v['id']}}}}
        with patch.object(W, 'lookup_trigger', return_value=trigger):
            v = W.bind_trigger(v['id'], trigger['id'], v['revision'])
            ctx = {'trigger': trigger['id'], 'mission': 'event-mission', 'step': 'event-step',
                   'origin': {'payload': {'source': 'untrusted text'}}}
            result = W.fire_tool({'workflow': v['id']}, ctx)
            self.assertTrue(result['ok'], result)
            row = W.view(v['id'])
            self.assertEqual(row['jobs'][0]['origin']['trigger'], trigger['id'])
            self.assertNotIn('untrusted text', json.dumps(row))
            trigger['spec']['path'] = '/changed'
            self.assertFalse(W.fire_tool({'workflow': v['id']}, {**ctx, 'step': 'new-step'})['ok'])
            self.assertEqual(len(self.launches), 1)

    def test_clock_install_failure_prevents_native_dispatch_and_remains_recoverable(self):
        v = self.new()
        with patch.dict(C.scheduler, {'ensure': lambda _row: {'errors': {'clock': 'fixture unavailable'}}}):
            v = W.start(v['id'], 'once')
            self.assertIn('could not install', v['clock_error'])
            self.assertEqual(self.launches, [])
        v = W.mutate(v['id'], v['revision'], 'resume', 'pause', False)
        self.assertEqual(len(self.launches), 1)
        self.assertNotIn('clock_error', v)

    def test_pin_refusal_precedes_native_submission_and_has_definite_receipt(self):
        v = self.new()
        with patch.object(C, '_checked_pins', side_effect=C.RunnerError('fixture version drift')):
            v = W.start(v['id'], 'once')
        rec = v['jobs'][0]['steps']['calculate']
        self.assertEqual(rec['status'], 'failed')
        self.assertTrue(rec['refused_before_submission'])
        self.assertNotIn('submission', rec)
        self.assertEqual(self.launches, [])

    def test_scheduler_accepts_both_real_trigger_definitions(self):
        import host_sched as BS
        import host_triggers as BT
        v = W.start(self.new()['id'], 'once')
        v = W.schedule(v['id'], '*/5 * * * *', True, v['revision'])
        for record in self.triggers.values():
            key, fields = BS._system_fields(BT, record)
            normalized = BT.normalize(dict(fields, enabled=True), 1800000000.0)
            self.assertEqual(normalized['kind'], 'cron')
            self.assertIn(normalized['action']['spec']['tool'], ('runner.supervise', 'runner.supervisor_tick'))
            self.assertTrue(key.startswith('symblic.'))

    def test_strict_native_journals_and_raw_status_fence_compensation_without_mutation(self):
        cases = [
            ('effects.jsonl', b'{"id":"e","phase":"unknown"}\n'),
            ('effects.jsonl', b'{"id":"e","phase":"done"}'),
            ('effects.jsonl', b'{"id":"e","phase":"future_phase"}\n'),
            ('effects.jsonl', b'not-json\n'),
            ('effects.jsonl', b'{"id":"e","id":"other","phase":"done"}\n'),
            ('delegate-effects.jsonl', b'{"key":"d","phase":"intent"}\n'),
            ('delegate-effects.jsonl', b'{"key":"d","phase":"done"}'),
            ('state.json', b'{"status":"invented_terminal"}'),
            ('state.json', b'{"status":"failed",'),
        ]
        for i, (name, content) in enumerate(cases):
            with self.subTest(name=name, content=content):
                v = self.new([{'id':'a','kind':'run','source':SOURCE},
                              {'id':'undo','kind':'set','on_failure':'a','changes':{'compensated':{'set':True}}}], token='strict-'+str(i))
                v = W.start(v['id'], 'start')
                native_id = self.launches[-1]
                self.complete(native_id, 'failed')
                path = self.native / 'runs' / native_id / name
                path.write_bytes(content)
                v = W.tick(v['id'])
                self.assertEqual(v['jobs'][0]['steps']['a']['status'], 'unknown')
                self.assertEqual(v['jobs'][0]['steps']['undo']['status'], 'pending')
                self.assertNotIn('compensated', v['state'])
                self.assertEqual(path.read_bytes(), content, 'inspection must never repair/truncate original bytes')

    def test_unreadable_native_ledger_never_means_failed(self):
        v = W.start(self.new()['id'], 'once')
        self.complete(self.launches[-1], 'failed')
        original = W._native_bytes
        def read(path, *args):
            if path.name == 'effects.jsonl':
                raise PermissionError('fixture inaccessible ledger')
            return original(path, *args)
        with patch.object(W, '_native_bytes', side_effect=read):
            v = W.tick(v['id'])
        self.assertEqual(v['jobs'][0]['steps']['calculate']['status'], 'unknown')

    def test_enabled_but_replaced_pulse_refuses_new_dispatch(self):
        v = W.start(self.new()['id'], 'once')
        self.triggers[v['pulse']['key']]['action']['spec']['tool'] = 'different.tool'
        v = W.tick(v['id'])
        self.assertIn('recovery pulse changed', v['clock_error'])
        self.assertEqual(len(self.launches), 1)

    def test_reconciliation_and_polling_refuse_broader_native_authority(self):
        cases = [('mode','full'), ('side_effects',True), ('max_effects',200),
                 ('model_policy',{'max_calls':99,'repairs':0,'allow_cloud':False})]
        for i, (key,value) in enumerate(cases):
            with self.subTest(key=key):
                v = self.new([{'id':'a','kind':'run','source':SOURCE,
                               'options':{'mode':'guarded','side_effects':False,'max_effects':2}}], token='authority-'+str(i))
                v = W.start(v['id'], 'once')
                rec = v['jobs'][0]['steps']['a']
                path = self.native/'runs'/rec['native_id']/'meta.json'
                meta = json.loads(path.read_text())
                self.assertEqual(meta['options']['max_effects'],2)
                meta['options'][key] = value
                path.write_text(json.dumps(meta))
                v = W.tick(v['id'])
                self.assertEqual(v['jobs'][0]['steps']['a']['status'],'unknown')
                with self.assertRaises(W.SupervisorError):
                    W.reconcile(v['id'],v['jobs'][0]['id'],'a',rec['native_id'])

    def test_schedule_enable_failure_is_unknown_and_lower_effect_limit_is_validated(self):
        v = self.new()
        with patch.dict(C.scheduler, {'enable': lambda *_args: False}):
            v = W.schedule(v['id'],'* * * * *',True,v['revision'])
        self.assertEqual(v['schedule']['status'],'unknown')
        self.assertIn('did not confirm',v['schedule']['error'])
        for limit in (0, True, 501, '2'):
            with self.assertRaises(C.RunnerError):
                C.start_run({'source':SOURCE,'options':{'max_effects':limit}})
        native=C.start_run({'source':SOURCE,'options':{'max_effects':500}})
        self.assertEqual(C.run_view(native['id'])['options']['max_effects'],200)

    def test_actual_scheduler_clock_store_dispatch_and_native_receipt_end_to_end(self):
        import time
        import host_store as Store
        import host_sched as BS
        import host_tools as BT
        import host_bridge as Bridge
        self.execute = True
        self.now = time.time()
        store = Store.Store(str(self.base/'scheduler'))
        self.addCleanup(store.close)
        registry = {}
        for declaration in C.SCHEDULER_TOOLS:
            if declaration['name'] not in ('runner.supervise','runner.supervisor_tick'):
                continue
            row = copy.deepcopy(declaration)
            name, summary, params, effect, policy, impl = [row.pop(k) for k in ('name','summary','params','effect','policy','impl')]
            registry[name] = BT.make_tool(name,summary,params,effect,policy,getattr(C,impl),module='runner',**row)
        scheduler = {'ensure':C._trigger_ensure,'enable':C._trigger_enable,'get':C._trigger_get,
                     'id':C._trigger_id,'drop':C._trigger_drop}
        crossed = []
        def bridge_call(service,name,args,ctx):
            self.assertEqual(service,'tool_impl')
            crossed.append(copy.deepcopy(ctx))
            return BT.run_declared_impl(name,args,ctx)
        with patch.object(Bridge,'is_remote',return_value=True), patch.object(Bridge,'call',side_effect=bridge_call), \
                patch.object(Store,'store',return_value=store), patch.object(BS,'clock',side_effect=lambda:self.now), \
                patch.object(BS,'_approval_key',return_value=None), patch.object(BS,'_run_post',return_value=None), \
                patch.object(BS,'_freeze',side_effect=lambda kind,spec,*_:(spec,{})), \
                patch.object(BS,'_clean_origin',side_effect=lambda value:(value,None)), \
                patch.object(BT,'registry',return_value=registry), patch.object(C,'scheduler',scheduler):
            v=self.new()
            v=W.schedule(v['id'],'* * * * *',True,v['revision'])
            self.assertEqual(v['schedule']['status'],'installed')
            trigger=store.get('triggers',v['schedule']['trigger'])
            self.now=trigger['next_fire']+0.01
            counts={'fired':0,'skipped':0,'errors':0}
            BS._tick_triggers(self.now,counts)
            self.assertEqual(counts['fired'],1,counts)
            def dispatch_pending():
                for step in store.select('steps',"status='pending'"):
                    mission=store.get('missions',step['mission'])
                    self.assertTrue(BS._dispatch(mission,step,self.now,BS.DEFAULT_SETTINGS,[]))
                    self.assertEqual(store.get('steps',step['id'])['status'],'done',store.get('steps',step['id']))
            dispatch_pending()
            v=W.view(v['id'])
            self.assertEqual(len(v['jobs']),1)
            self.assertEqual(len(self.launches),1)
            self.assertEqual(v['jobs'][0]['origin']['trigger'],trigger['id'])
            v=W.schedule(v['id'],'* * * * *',False,v['revision'])
            pulse=store.get('triggers',v['pulse']['trigger'])
            self.now=max(self.now+1,pulse['next_fire']+0.01)
            BS._tick_triggers(self.now,counts)
            dispatch_pending()
            v=W.view(v['id'])
            self.assertEqual(v['jobs'][0]['status'],'done',v.get('clock_error'))
            self.assertFalse(v['pulse']['enabled'])
            self.assertEqual(len(store.select('fires')),2)
            self.assertEqual(len(store.select('events',"kind='tool.call'")),2)
            self.assertTrue(all(m['status']=='done' for m in store.select('missions')))
            self.assertFalse(any(t['enabled'] for t in store.select('triggers')))
            self.assertEqual({c['trigger'] for c in crossed},{v['schedule']['trigger'],v['pulse']['trigger']})
            self.assertTrue(all('origin' not in c and 'approved' not in c for c in crossed))

    def test_context_bridge_keeps_only_scheduler_trigger_identifier(self):
        import host_tools as BT
        ctx={'mission':'m_fixture','step':'s_fixture','idem':'once','trigger':'t_abcdef012345',
             'origin':{'payload':'untrusted event contents'},'event':{'source':'outside'},
             'payload':{'program':'outside'},'approved':{'by':'owner'}}
        self.assertEqual(BT._ctx_across(ctx),{key:ctx[key] for key in ('mission','step','idem','trigger')})
        self.assertNotIn('trigger',BT._ctx_across({'args':{'trigger':'t_abcdef012345'}}))

    def test_http_owner_boundary_and_stale_revision(self):
        class Handler:
            def __init__(self):
                self.allowed = False
                self.answers = []
            def require_owner(self, _):
                return self.allowed
            def send_json(self, body, status=200):
                self.answers.append((body, status))
            def get_query_param(self, _):
                return ''
        h = Handler()
        self.assertTrue(A.handle(h, 'POST', 'supervisor/create', {}))
        self.assertEqual(h.answers, [])
        with patch('person.require', return_value=True):
            h.allowed = True
            self.assertTrue(A.handle(h, 'POST', 'supervisor/create', {'definition': definition(), 'request_id': 'api'}))
            v = h.answers[-1][0]
            A.handle(h, 'POST', 'supervisor/state', {'id': v['id'], 'revision': -1, 'request_id': 'state', 'changes': {'ready': True}})
            self.assertEqual(h.answers[-1][1], 409)


if __name__ == '__main__':
    unittest.main()
