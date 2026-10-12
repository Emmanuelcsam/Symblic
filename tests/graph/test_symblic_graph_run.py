"""Durable graph composition: fake providers/hosts and temporary stores only."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from symblic.js import check as JS

from symblic.graph import planner as G
from symblic.graph import run as R


def policy():
    return {'version': 1, 'routes': [
        {'id': 'Local', 'provider': 'fake', 'model': 'small', 'node': 'node-a', 'local': True},
        {'id': 'Cloud', 'provider': 'claude', 'model': 'sonnet', 'node': 'node-b', 'local': False}],
        'order': ['Cloud', 'Local']}


def node(name, inputs=None, source=None, **fields):
    inputs = {} if inputs is None else inputs
    given = '\n'.join('given ' + key + ': Any.' for key in inputs)
    n = {'id': name, 'inputs': inputs,
         'source': source or given + '\nask answer: Int "Return 2" with effort=low, retries=0.',
         'contract': 'answer is a nonnegative integer under encoded predicates',
         'output_binding': 'answer', 'output_schema': {'type': 'integer'}, 'checks': ['answer >= 0'],
         'allowed': {'routes': ['Local', 'Cloud'], 'providers': ['fake', 'claude'],
                     'models': ['small', 'sonnet'], 'nodes': ['node-a', 'node-b'], 'local_only': True},
         'join': 'require_all', 'effect_risk': 'none', 'retries': 0, 'call_limit': 3,
         'max_calls': 24, 'max_iterations': 32, 'assumptions': ['encoded predicates capture this bounded task']}
    n.update(fields)
    return n


def graph(*nodes, iterations=1, max_calls=100):
    return G.freeze_graph({'id': 'Graph', 'nodes': list(nodes), 'iterations': iterations,
                           'max_calls': max_calls}, policy())


class FakeApps:
    def __init__(self, answer=2):
        self.answer, self.calls = answer, []
        self.lock = threading.Lock()

    def call(self, request):
        with self.lock:
            self.calls.append(request)
            answer = self.answer(request) if callable(self.answer) else self.answer
        if type(answer) is dict and 'ok' in answer:
            return answer
        return {'ok': True, 'json': {'answer': answer}, 'model': request['app']['model'],
                'node': request['app']['node'], 'ms': 0}


CAT = {'fixture.read': {'effect': 'read', 'policy': 'auto', 'params': {'type': 'object', 'properties': {},
       'additionalProperties': False}, 'sensitivity': 'public'},
       'fixture.write': {'effect': 'write-local', 'policy': 'auto', 'idempotent': True,
       'params': {'type': 'object', 'properties': {}, 'additionalProperties': False}, 'sensitivity': 'public'}}


class Host:
    idempotent_by_id = True
    def __init__(self, outcome=None):
        self.cat = copy.deepcopy(CAT)
        self.calls = []
        self.outcome = outcome

    def catalogue(self):
        return copy.deepcopy(self.cat)

    def perform(self, effect, stop):
        self.calls.append(effect)
        return self.outcome if self.outcome is not None else {'status': 'done', 'result': 2, 'receipt': {'fixture': True}}


class Crash(BaseException):
    pass


class GraphRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / 'graph'
        # Kernel identity must not run even node --version in these tests.
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start()
        self.addCleanup(version.stop)
        # Fail the test on ANY attempted external process (including JS).
        self.no_process = patch('subprocess.Popen', side_effect=AssertionError('no external process in graph tests'))
        no_process = self.no_process.start()
        self.addCleanup(self.no_process.stop)
        self.addCleanup(lambda: self.assertFalse(no_process.called))

    def execute(self, frozen, apps=None, **kwargs):
        apps = FakeApps() if apps is None else apps
        return R.GraphRun(frozen, self.folder, apps, **kwargs).execute()

    def test_chain_fanout_join_real_fake_calls_and_idempotent_resume(self):
        a = node('A')
        b = node('B', {'x': {'node': 'A'}}, 'given x: Int.\nlet answer = x + 1.')
        c = node('C', {'x': {'node': 'A'}}, 'given x: Int.\nlet answer = x + 2.')
        join = node('Join', {'b': {'node': 'B'}, 'c': {'node': 'C'}},
                    'given b: Int.\ngiven c: Int.\nlet answer = b + c.', checks=['answer = b + c'])
        frozen = graph(join, c, b, a)
        apps = FakeApps()
        state = self.execute(frozen, apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 1)
        self.assertEqual(state['states'][-1]['result']['value'], 7)
        self.assertEqual(self.execute(frozen, apps), state)
        self.assertEqual(len(apps.calls), 1)
        result = state['states'][0]['result']
        self.assertEqual(result['evidence'][0]['assurance'], 'supported_under_encoded_contract')
        self.assertEqual(result['evidence'][0]['source_truth'], 'contingent')
        self.assertEqual(result['assumptions'], a['assumptions'])
        self.assertTrue((self.folder / 'graph-pins.json').is_file())
        self.assertEqual(len(list((self.folder / 'attempts').iterdir())), 4)

    def test_feedback_iterations(self):
        n = node('A', {'previous': {'node': 'A', 'delay': 1, 'seed': G.envelope(0, 'supported')}},
                 'given previous: Int.\nlet answer = previous + 1.', checks=['answer = previous + 1'])
        state = self.execute(graph(n, iterations=3))
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual([s['result']['value'] for s in state['states']], [1, 2, 3])
        self.assertEqual(state['reserved_calls'], 9)

    def test_typed_unanimous_answer_alone_is_unknown_and_blocks_gate(self):
        a = node('A', checks=[])
        b = node('B', {'x': {'node': 'A'}})
        apps = FakeApps()
        state = self.execute(graph(a, b), apps)
        self.assertEqual(state['status'], 'unresolved')
        self.assertEqual(state['states'][0]['result']['outcome'], 'unknown')
        self.assertEqual(state['states'][1]['status'], 'blocked')
        self.assertEqual(len(apps.calls), 1)

    def test_collect_preserves_failed_input_and_propagates_contested(self):
        a = node('A', source='let answer = -1.')
        collect = node('Collect', {'x': {'node': 'A'}}, 'given x: Any.\nlet answer = 1.', join='collect_unresolved')
        gate = node('Gate', {'x': {'node': 'Collect'}})
        state = self.execute(graph(a, collect, gate))
        self.assertEqual(state['states'][0]['status'], 'failed')
        envelope = state['states'][1]['result']
        self.assertEqual(envelope['outcome'], 'contested')
        self.assertEqual(envelope['provenance'][0]['inputs']['x']['status'], 'failed')
        self.assertEqual(state['states'][2]['status'], 'blocked')

    def test_conditional_binding_and_schema_are_checked(self):
        n = node('A', source='if true.\nlet answer = 2.\nelse.\nlet answer = -1.\nend.')
        self.assertEqual(self.execute(graph(n))['status'], 'succeeded')
        other = Path(self.tmp.name) / 'schema'
        bad = node('A', output_schema={'type': 'string'})
        state = R.GraphRun(graph(bad), other, FakeApps()).execute()
        self.assertEqual(state['states'][0]['status'], 'failed')
        self.assertIn('output schema', state['states'][0]['error'])

    def test_functions_loops_and_pinned_library_imports(self):
        source = ('import order as O.\nfunction twice(n: Int) -> Int = n * 2.\n'
                  'for item in [1, 2].\nshow twice(item).\nend.\n'
                  'let answer = twice(O.total({yy: 1, yn: 1, ny: 0, nn: 1})).')
        state = self.execute(graph(node('A', source=source, checks=['answer = 6'])))
        self.assertEqual(state['status'], 'succeeded', state)
        pins = R._read(next((self.folder / 'attempts').iterdir()) / 'attempt-pins.json')
        self.assertIn('order', pins['execution_pins']['libraries'])
        self.assertIn('symblic/graph/run.py', R._read(self.folder / 'graph-pins.json')['files'])

    def test_source_cloud_override_council_auto_and_tools_never_dispatch(self):
        for by in ('claude:sonnet@node-b', 'council:test@node-a', 'auto'):
            folder = Path(self.tmp.name) / by.split(':')[0]
            n = node('A', source=f'ask answer: Int "answer" with by="{by}", effort=low, retries=0.')
            apps = FakeApps()
            state = R.GraphRun(graph(n), folder, apps).execute()
            self.assertEqual(len(apps.calls), 0, state)
            self.assertEqual(state['states'][0]['status'], 'failed')
        apps = FakeApps()
        n = node('A', source='ask answer: Int "answer" with tools="all", effort=low, retries=0.')
        state = self.execute(graph(n), apps)
        self.assertEqual(len(apps.calls), 0)
        self.assertEqual(state['states'][0]['status'], 'failed')

    def test_declared_local_flag_cannot_hide_cloud_engine(self):
        p = policy()
        p['routes'][1]['local'] = True
        n = node('A')
        frozen = G.freeze_graph({'id': 'Graph', 'nodes': [n], 'iterations': 1, 'max_calls': 3}, p)
        apps = FakeApps()
        with self.assertRaises(R.Unsupported):
            self.execute(frozen, apps)
        self.assertEqual(apps.calls, [])
        self.assertFalse((self.folder / 'graph-events.jsonl').exists())

    def test_error_reply_wrong_route_or_missing_attribution_is_unknown(self):
        for index, reply in enumerate(({'ok': False, 'error': 'error', 'node': 'other'},
                                       {'ok': True, 'json': {'answer': 2}, 'model': 'other', 'node': 'node-a'},
                                       {'ok': True, 'json': {'answer': 2}})):
            apps = FakeApps(reply)
            folder = Path(self.tmp.name) / str(index)
            frozen = graph(node('A', retries=2))
            state = R.GraphRun(frozen, folder, apps).execute()
            self.assertEqual(state['states'][0]['status'], 'unknown', state)
            R.GraphRun(frozen, folder, apps).execute()
            self.assertEqual(len(apps.calls), 1)

    def test_started_crash_before_run_recovers_without_new_reservation(self):
        def crash(stage, action):
            if stage == 'started':
                raise Crash()
        frozen, apps = graph(node('A')), FakeApps()
        with self.assertRaises(Crash):
            self.execute(frozen, apps, checkpoint=crash)
        self.assertEqual(apps.calls, [])
        state = self.execute(frozen, apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(state['reserved_calls'], 3)
        self.assertEqual(len(apps.calls), 1)

    def test_crash_after_durable_result_before_graph_commit(self):
        def crash(stage, action):
            if stage == 'result_saved':
                raise Crash()
        frozen, apps = graph(node('A')), FakeApps()
        with self.assertRaises(Crash):
            self.execute(frozen, apps, checkpoint=crash)
        self.assertEqual(len(apps.calls), 1)
        state = self.execute(frozen, apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 1)
        self.assertEqual(state['reserved_calls'], 3)

    def test_unfinished_model_call_intent_is_never_redispatched(self):
        def crash(request):
            raise Crash()
        frozen, apps = graph(node('A', retries=2)), FakeApps(crash)
        with self.assertRaises(Crash):
            self.execute(frozen, apps)
        state = self.execute(frozen, apps)
        self.assertEqual(state['states'][0]['status'], 'unknown', state)
        self.assertEqual(len(apps.calls), 1)
        self.assertEqual(state['reserved_calls'], 3)

    def test_known_call_outcome_recovers_cache_after_midrun_crash(self):
        frozen, apps = graph(node('A')), FakeApps()
        real_append = R._append
        def crash_after_outcome(store, name, row):
            real_append(store, name, row)
            if name == 'graph-calls.jsonl' and row['kind'] == 'outcome':
                raise Crash()
        with patch.object(R, '_append', side_effect=crash_after_outcome), self.assertRaises(Crash):
            self.execute(frozen, apps)
        state = self.execute(frozen, apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 1)

    def test_all_attempt_budgets_and_known_failure_replay(self):
        n = node('A', source='ask answer: Int "answer" with effort=low, retries=0.',
                 checks=['answer > 0'], call_limit=1, retries=2, max_calls=2)
        frozen = graph(n, max_calls=2)
        apps = FakeApps(-1)
        state = self.execute(frozen, apps)
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(state['states'][0]['status'], 'exhausted', state)
        self.assertEqual(state['reserved_calls'], 2)
        self.execute(frozen, apps)
        self.assertEqual(len(apps.calls), 2)

    def test_effects_require_explicit_durable_host_and_retain_capability(self):
        frozen = graph(node('A', source='observe answer: Int = fixture.read().', effect_risk='read'))
        with self.assertRaises(R.Unsupported):
            self.execute(frozen)
        host = Host()
        state = self.execute(frozen, effects=host)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(host.calls), 1)
        self.execute(frozen, effects=host)
        self.assertEqual(len(host.calls), 1)

    def test_unknown_effect_and_interrupted_effect_never_reperformed(self):
        frozen = graph(node('A', source='act answer: Int = fixture.write().', effect_risk='write'))
        host = Host({'status': 'unknown', 'error': 'may have happened'})
        state = self.execute(frozen, effects=host)
        self.assertEqual(state['states'][0]['status'], 'unknown', state)
        self.execute(frozen, effects=host)
        self.assertEqual(len(host.calls), 1)

    def test_cancel_before_dispatch_and_after_model_call(self):
        stop = threading.Event()
        stop.set()
        frozen = graph(node('A'))
        apps = FakeApps()
        self.assertEqual(self.execute(frozen, apps, stop=stop)['status'], 'canceled')
        self.assertEqual(apps.calls, [])
        stop = threading.Event()
        apps = FakeApps(lambda req: stop.set() or 2)
        folder = Path(self.tmp.name) / 'after'
        state = R.GraphRun(frozen, folder, apps, stop=stop).execute()
        self.assertEqual(state['status'], 'canceled')
        self.assertEqual(len(apps.calls), 1)
        R.GraphRun(frozen, folder, apps).execute()
        self.assertEqual(len(apps.calls), 1)

    def test_tampered_policy_source_and_corrupt_ledger_refused(self):
        frozen = graph(node('A'))
        apps = FakeApps()
        self.execute(frozen, apps)
        changed = copy.deepcopy(frozen['graph'])
        changed['nodes'][0]['source'] += '\nnote changed.'
        with self.assertRaises(G.GraphError):
            self.execute(G.freeze_graph(changed, frozen['policy']), apps)
        changed_policy = copy.deepcopy(frozen['policy'])
        changed_policy['order'].reverse()
        with self.assertRaises(G.GraphError):
            self.execute(G.freeze_graph(frozen['graph'], changed_policy), apps)
        with (self.folder / 'graph-events.jsonl').open('a') as stream:
            stream.write('{bad}\n')
        with self.assertRaises(G.GraphError):
            self.execute(frozen, apps)
        self.assertEqual(len(apps.calls), 1)

    def test_pins_and_started_are_durable_before_nonzero_model_call(self):
        def inspect(request):
            self.assertTrue((self.folder / 'graph-pins.json').is_file())
            rows = R._read(self.folder / 'graph-events.jsonl', lines=True)
            self.assertEqual(rows[-1]['kind'], 'started')
            attempt = next((self.folder / 'attempts').iterdir())
            self.assertTrue((attempt / 'attempt-pins.json').is_file())
            calls = R._read(attempt / 'graph-calls.jsonl', lines=True)
            self.assertEqual(calls[-1]['kind'], 'intent')
            return 2
        state = self.execute(graph(node('A')), FakeApps(inspect))
        self.assertEqual(state['status'], 'succeeded')

    def test_known_failed_call_replay_does_not_reset_or_double_spend_budget(self):
        n = node('A', source='ask answer: Int "answer" with effort=low, retries=1.', call_limit=2)
        apps = FakeApps(lambda request: {'ok': False, 'error': 'fixture refusal', 'ms': 0}
                        if len(apps.calls) == 1 else 2)
        frozen = graph(n)
        real_append = R._append
        def crash(store, name, row):
            real_append(store, name, row)
            if name == 'graph-calls.jsonl' and row['kind'] == 'outcome' and not row['reply']['ok']:
                raise Crash()
        with patch.object(R, '_append', side_effect=crash), self.assertRaises(Crash):
            self.execute(frozen, apps)
        state = self.execute(frozen, apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(state['reserved_calls'], 2)
        self.assertEqual(state['states'][0]['result']['provenance'][0]['issued_calls'], 2)
        self.execute(frozen, apps)
        self.assertEqual(len(apps.calls), 2)

    def test_restart_cannot_create_extra_calls_past_attempt_cap(self):
        n = node('A', source='ask priorAnswer: Int "first" with effort=low, retries=0.\n'
                 'ask answer: Int "second" with effort=low, retries=0.', call_limit=1)
        frozen, apps = graph(n), FakeApps()
        real_append = R._append
        def crash(store, name, row):
            real_append(store, name, row)
            if name == 'graph-calls.jsonl' and row['kind'] == 'outcome':
                raise Crash()
        with patch.object(R, '_append', side_effect=crash), self.assertRaises(Crash):
            self.execute(frozen, apps)
        state = self.execute(frozen, apps)
        self.assertEqual(state['states'][0]['status'], 'failed', state)
        self.assertEqual(len(apps.calls), 1)
        self.assertEqual(state['reserved_calls'], 1)

    def test_graph_retry_budget_includes_attempt_before_restart(self):
        frozen = graph(node('A', call_limit=1, max_calls=2, retries=2), max_calls=2)
        apps = FakeApps(-1)
        def crash(stage, action):
            if stage == 'result_saved':
                raise Crash()
        with self.assertRaises(Crash):
            self.execute(frozen, apps, checkpoint=crash)
        state = self.execute(frozen, apps)
        self.assertEqual(state['states'][0]['status'], 'exhausted', state)
        self.assertEqual(state['reserved_calls'], 2)
        self.assertEqual(len(apps.calls), 2)

    def test_interrupted_effect_intent_is_never_performed_again(self):
        class InterruptedHost(Host):
            def perform(self, effect, stop):
                self.calls.append(effect)
                raise Crash()
        frozen = graph(node('A', source='act answer: Int = fixture.write().', effect_risk='write'))
        host = InterruptedHost()
        with self.assertRaises(Crash):
            self.execute(frozen, effects=host)
        state = self.execute(frozen, effects=host)
        self.assertEqual(state['states'][0]['status'], 'unknown', state)
        self.assertEqual(len(host.calls), 1)
        self.execute(frozen, effects=host)
        self.assertEqual(len(host.calls), 1)

    def test_known_effect_outcome_recovers_through_existing_host_ledger(self):
        frozen = graph(node('A', source='act answer: Int = fixture.write().', effect_risk='write'))
        host = Host()
        real_append = R.FX.Ledger.append
        def crash(ledger, row):
            result = real_append(ledger, row)
            if row['phase'] == 'done':
                raise Crash()
            return result
        with patch.object(R.FX.Ledger, 'append', crash), self.assertRaises(Crash):
            self.execute(frozen, effects=host)
        state = self.execute(frozen, effects=host)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(state['reserved_calls'], 3)

    def test_completed_resume_audits_native_cache_and_attempt_source(self):
        frozen, apps = graph(node('A')), FakeApps()
        self.execute(frozen, apps)
        attempt = next((self.folder / 'attempts').iterdir())
        cache_path = attempt / 'calls.jsonl'
        rows = R._read(cache_path, lines=True)
        original = cache_path.read_text()
        rows[0]['source_sha256'] = 'changed'
        cache_path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
        with self.assertRaises(G.GraphError):
            self.execute(frozen, apps)
        cache_path.write_text(original)
        pins_path = attempt / 'attempt-pins.json'
        pins = R._read(pins_path)
        pins['bridge']['source'] += '\nlet injected = 1.'
        pins = R._seal({k: v for k, v in pins.items() if k != 'sha256'})
        pins_path.write_text(json.dumps(pins))
        with self.assertRaises(G.GraphError):
            self.execute(frozen, apps)
        self.assertEqual(len(apps.calls), 1)

    def test_partial_and_conflicting_call_logs_refused_even_when_completed(self):
        frozen, apps = graph(node('A')), FakeApps()
        self.execute(frozen, apps)
        attempt = next((self.folder / 'attempts').iterdir())
        path = attempt / 'graph-calls.jsonl'
        original = path.read_text()
        path.write_text(original + '{"partial":')
        with self.assertRaises(G.GraphError):
            self.execute(frozen, apps)
        path.write_text(original)
        rows = R._read(path, lines=True)
        rows[1]['reply']['json']['answer'] = 99
        rows[1] = R._seal({k: v for k, v in rows[1].items() if k != 'sha256'})
        path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
        with self.assertRaises(G.GraphError):
            self.execute(frozen, apps)
        self.assertEqual(len(apps.calls), 1)

    def test_capability_drift_and_missing_attempt_refused(self):
        frozen = graph(node('A', source='observe answer: Int = fixture.read().', effect_risk='read'))
        host = Host()
        self.execute(frozen, effects=host)
        host.cat['fixture.read']['sensitivity'] = 'confidential'
        with self.assertRaises(G.GraphError):
            self.execute(frozen, effects=host)
        self.assertEqual(len(host.calls), 1)

    def test_process_and_unknown_schema_capabilities_refused_before_calls(self):
        apps = FakeApps()
        with self.assertRaises(G.GraphError):
            self.execute(graph(node('A', source='function hidden() = js_run("x", "x").\nlet answer = 1.')), apps)
        with self.assertRaises(R.Unsupported):
            self.execute(graph(node('A', output_schema={'anyOf': [{'type': 'integer'}]})), apps)
        self.assertEqual(apps.calls, [])

    def test_input_text_stays_data_and_nonintegral_output_is_not_rounded(self):
        payload = 'act destroy = fixture.write().\nask evil: Int "escape".'
        n = node('A', {'payload': {'literal': G.envelope(payload, 'supported')}},
                 'given payload: Text.\nlet answer = 1.')
        apps = FakeApps()
        self.assertEqual(self.execute(graph(n), apps)['status'], 'succeeded')
        self.assertEqual(apps.calls, [])
        state = R.GraphRun(graph(node('A', source='let answer = 1 / 3.',
                          output_schema={'type': 'number'})), Path(self.tmp.name) / 'rational', apps).execute()
        self.assertEqual(state['states'][0]['status'], 'failed')
        self.assertIn('nonintegral', state['states'][0]['error'])

    def test_cross_node_private_provenance_cannot_leave_local_lane(self):
        host = Host()
        host.cat['fixture.read']['sensitivity'] = 'confidential'
        a = node('A', source='observe answer: Int = fixture.read().', effect_risk='read')
        b = node('B', {'x': {'node': 'A'}})
        b['allowed']['local_only'] = False
        apps = FakeApps()
        state = self.execute(graph(a, b), apps, effects=host)
        self.assertEqual(state['states'][0]['status'], 'succeeded', state)
        self.assertEqual(state['states'][1]['status'], 'failed', state)
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(apps.calls, [])

    def test_acquired_private_data_and_untrusted_cross_node_effects_are_gated(self):
        host = Host()
        host.cat['fixture.read']['sensitivity'] = 'confidential'
        n = node('A', source='observe reading: Int = fixture.read().\n'
                 'ask answer: Int "answer" with effort=low, retries=0.', effect_risk='read')
        n['allowed']['local_only'] = False
        apps = FakeApps()
        state = self.execute(graph(n), apps, effects=host)
        self.assertEqual(state['states'][0]['status'], 'failed', state)
        self.assertEqual(apps.calls, [])
        other = Path(self.tmp.name) / 'untrusted'
        host = Host()
        host.cat['fixture.read']['untrusted'] = True
        a = node('A', source='observe answer: Int = fixture.read().', effect_risk='read')
        b = node('B', {'x': {'node': 'A'}}, 'given x: Any.\nact answer: Int = fixture.write().', effect_risk='write')
        state = R.GraphRun(graph(a, b), other, apps, effects=host).execute()
        self.assertEqual(state['states'][1]['status'], 'failed', state)
        self.assertEqual(len(host.calls), 1)

    def test_contested_model_observation_stops_verified_graph_before_derivation(self):
        a = node('A', source='ask proposal: Int "answer" with effort=low, retries=0, families=2.\n'
                 'let answer = proposal + 0.')
        gate = node('Gate', {'x': {'node': 'A'}})
        apps = FakeApps()
        state = self.execute(graph(a, gate), apps)
        self.assertEqual(state['states'][0]['status'], 'failed', state)
        self.assertIn('did not agree', state['states'][0]['error'])
        self.assertEqual(state['states'][1]['status'], 'blocked')
        saved = R._read(next((self.folder / 'attempts').iterdir()) / 'graph-result.json')
        self.assertEqual(saved['run_report']['execution_profile'], 'verified')
        self.assertEqual(len(apps.calls), 1)

    def test_current_verified_checker_keyword_is_used(self):
        original = R.S.check
        profiles = []
        def check(source, *, execution_profile=None):
            profiles.append(execution_profile)
            return original(source, execution_profile=execution_profile)
        # A fresh static-check cache: an earlier identical check must not hide this call.
        with patch.object(R.S, 'check', check), patch.object(R, '_CHECKS', R._LRU(8)):
            self.assertEqual(self.execute(graph(node('A', source='let answer = 2.')))['status'], 'succeeded')
        self.assertEqual(profiles, ['verified'])

    def test_host_contract_change_after_start_is_refused_before_perform(self):
        host = Host()
        def answer(request):
            host.cat['fixture.write']['sensitivity'] = 'confidential'
            return 2
        n = node('A', source='ask proposal: Int "answer" with effort=low, retries=0.\n'
                 'act answer: Int = fixture.write().', effect_risk='write')
        state = self.execute(graph(n), FakeApps(answer), effects=host)
        self.assertEqual(state['states'][0]['status'], 'failed', state)
        self.assertEqual(host.calls, [])

    def test_runtime_module_pin_drift_refuses_completed_resume(self):
        frozen, apps = graph(node('A')), FakeApps()
        self.execute(frozen, apps)
        with patch.dict(R._GRAPH_HASHES, {'symblic/graph/planner.py': '0' * 64}):
            with self.assertRaises(G.GraphError):
                self.execute(frozen, apps)
        self.assertEqual(len(apps.calls), 1)

    def test_missing_attempt_and_symlinked_private_log_refused(self):
        frozen, apps = graph(node('A')), FakeApps()
        self.execute(frozen, apps)
        attempt = next((self.folder / 'attempts').iterdir())
        pins_path = attempt / 'attempt-pins.json'
        original = pins_path.read_text()
        pins_path.unlink()
        with self.assertRaises(G.GraphError):
            self.execute(frozen, apps)
        pins_path.write_text(original)
        outside = Path(self.tmp.name) / 'outside'
        outside.write_text('private fixture')
        link = attempt / 'unsafe.json'
        link.symlink_to(outside)
        with self.assertRaises(G.GraphError):
            self.execute(frozen, apps)
        self.assertEqual(outside.read_text(), 'private fixture')
        self.assertEqual(len(apps.calls), 1)

    def test_unsupported_cross_attempt_effect_retry_is_explicit(self):
        frozen = graph(node('A', source='act answer: Int = fixture.write().', effect_risk='write', retries=1))
        host = Host()
        with self.assertRaises(R.Unsupported):
            self.execute(frozen, effects=host)
        self.assertEqual(host.calls, [])

    def test_private_loop_acquisition_does_not_lose_its_local_fence(self):
        host = Host()
        host.cat['fixture.read']['sensitivity'] = 'personal'
        n = node('A', source='for item in [1].\nobserve reading: Int = fixture.read().\nend.\n'
                 'ask answer: Int "answer" with effort=low, retries=0.', effect_risk='read')
        n['allowed']['local_only'] = False
        apps = FakeApps()
        state = self.execute(graph(n), apps, effects=host)
        self.assertEqual(state['states'][0]['status'], 'failed', state)
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(apps.calls, [])

    def test_concurrent_instances_dispatch_once(self):
        entered, release = threading.Event(), threading.Event()
        def answer(request):
            entered.set()
            if not release.wait(60):
                raise AssertionError('test did not release fake provider')
            return 2
        frozen, apps = graph(node('A')), FakeApps(answer)
        instances = [R.GraphRun(frozen, self.folder, apps), R.GraphRun(frozen, self.folder, apps)]
        results, failures = [], []
        def execute(instance):
            try:
                results.append(instance.execute())
            except BaseException as exc:
                failures.append(exc)
        threads = [threading.Thread(target=execute, args=(instance,)) for instance in instances]
        threads[0].start()
        self.assertTrue(entered.wait(60))   # generous: graph preparation is slow on a loaded machine
        threads[1].start()
        release.set()
        for thread in threads:
            thread.join(60)
            self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(apps.calls), 1)


if __name__ == '__main__':
    unittest.main()
