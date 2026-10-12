"""MICA execution journeys: fake providers, private stores, real JS gates.

No agent, model, cloud API or live store. The local existing JavaScript sandbox
runs only fixed tiny fixture programs, including deliberately incorrect answers.
"""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from symblic.mica import search as M
from symblic.mica import contracts as C
from symblic.mica import native as N


ROUTE = {'id': 'fixture', 'provider': 'ollama', 'model': 'fixture-small', 'node': 'node-a', 'local': True}


def inventory(nodes=('node-a',)):
    return [{'engine': 'ollama', 'model': 'fixture-small', 'node': node, 'digest': None,
             'ready': True, 'available': True, 'context_chars': 65536, 'estimated_cost_units': 1}
            for node in nodes]


def request(**budget):
    return {'version': 1, 'language': 'javascript', 'objective': 'Implement public integer increment.',
            'requirements': [{'id': 'increment', 'text': 'Return the input integer plus one.', 'acceptance': 'TESTED'}],
            'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
            'tests': [{'requirement_ids': ['increment'], 'call': 'inc(2)', 'expected': '3'}],
            'allowed_outputs': ['result.js'], 'assumptions': ['Inputs are integers.'],
            'budget': {'max_calls': 8, 'max_candidates': 2, 'max_units': 8, 'max_workers': 3,
                       'retries': 0, 'context_chars': 24000, 'wall_seconds': 60, **budget}}


def proposed_unit(ident, name, body, examples, uses=()):
    return {'id': ident, 'names': [name], 'heading': name + '(x)', 'body': body, 'uses': list(uses),
            'examples': examples, 'requirements': ['increment']}


def proposal():
    return {'units': [proposed_unit('increment', 'inc', 'Return x plus one.', [['inc(2)', '3']])], 'assumptions': []}


class FakeApps:
    """Fake only the provider boundary, retaining complete received prompts."""
    def __init__(self, callback=None, delay=0):
        self.callback = callback or (lambda req, number: 'function inc(x) { return x + 1; }')
        self.delay = delay
        self.requests = []
        self.lock = threading.Lock()
        self.active_by_node = {}
        self.max_active_by_node = {}

    def call(self, req):
        with self.lock:
            self.requests.append({k: copy.deepcopy(v) for k, v in req.items() if k != 'stop'})
            number = len(self.requests)
            node = req['app']['node']
            self.active_by_node[node] = self.active_by_node.get(node, 0) + 1
            self.max_active_by_node[node] = max(self.max_active_by_node.get(node, 0), self.active_by_node[node])
        try:
            if self.delay:
                time.sleep(self.delay)
            output = self.callback(req, number)
            if isinstance(output, BaseException):
                raise output
            if type(output) is dict and 'ok' in output:
                return output
            language = 'json' if 'output_format' in req['prompt'] else 'js'
            return {'ok': True, 'text': output if req.get('schema') is not None else '```' + language + '\n' + output + '\n```',
                    'model': req['app']['model'], 'node': node, 'ms': 1}
        finally:
            with self.lock:
                self.active_by_node[node] -= 1


class ExecutionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-execution-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'run'

    def run_mica(self, app, req=None, mode='direct', plans=None, inv=None):
        return M.MicaRun(req or request(), self.path, app, inventory() if inv is None else inv).execute(
            mode=mode, initial_plans=plans)

    def test_native_ollama_generate_timeout_is_not_a_model_format_error(self):
        result = {'status': 'failed', 'error': {'kind': 'runtime',
            'message': 'no applicator gave a valid answer for proposal (ollama@node-c: transient: '
                       'ollama request failed: the generate request ran out of time)'}}
        self.assertEqual(M.failure_class(result), 'MODEL_TIMEOUT')
        self.assertEqual(M.failure_class({'status': 'failed', 'error': {'kind': 'syntax', 'message': 'bad JSON'}}),
                         'SYNTAX_ERROR')

    def test_planner_source_executes_without_search_routing(self):
        source = N.planner_source('Return a JSON object describing a fixture.', ROUTE)
        self.assertNotIn('route=search', source)
        apps = FakeApps(lambda req, n: '{"fixture":true}')
        result = N.execute(source, self.path, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(json.loads(result['output']), {'fixture': True})
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(apps.requests[0]['tools'], 'none')

    def test_planner_uses_declared_context_allowance_without_truncation(self):
        prompt = 'Return a JSON fixture from this complete source context. ' + ('known fact; ' * 600)
        apps = FakeApps(lambda req, n: '{"fixture":true}')
        source = N.planner_source(prompt, ROUTE, context_chars=24000)
        result = N.execute(source, self.path, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(len(apps.requests), 1)
        self.assertIn('known fact; ' * 600, apps.requests[0]['prompt'])
        small = FakeApps(lambda req, n: '{"fixture":true}')
        denied = N.execute(N.planner_source(prompt, ROUTE, context_chars=6000), self.path.parent / 'small',
                           small, ROUTE, limit=1, output_binding='proposal')
        self.assertNotEqual(denied['status'], 'done')
        self.assertEqual(small.requests, [])

    def test_no_dispatch_resource_refusal_is_not_empirical_model_failure(self):
        run = M.MicaRun(request(), self.path, FakeApps(), inventory())
        run._observe('not-dispatched', {'content_hash': 'a' * 64, 'model_eligibility': {'task_class': 'implementation'}},
                     ROUTE, {'status': 'failed', 'calls': 0, 'error': {'kind': 'context'}}, accepted=False)
        self.assertEqual(run.observations, [])
        self.assertFalse(self.path.exists())

    def test_direct_success_and_replay_make_exactly_one_provider_call(self):
        apps = FakeApps()
        first = self.run_mica(apps)
        self.assertEqual(first['status'], 'done', first)
        self.assertEqual(first['calls'], 1)
        self.assertIn('function inc', first['output']['text'])
        self.assertEqual(first['assurance'], 'TESTED')
        second = self.run_mica(apps)
        self.assertEqual(second, first)
        self.assertEqual(len(apps.requests), 1)

    def test_pinned_model_digest_cannot_succeed_without_observed_measurement(self):
        route = {**ROUTE, 'digest': 'a' * 64}
        source = N.planner_source('Return one JSON fixture.', route)
        apps = FakeApps(lambda req, n: '{"fixture":true}')
        result = N.execute(source, self.path, apps, route, limit=1, output_binding='proposal')
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        repeated = N.execute(source, self.path, apps, route, limit=1, output_binding='proposal')
        self.assertEqual(repeated['status'], result['status'])
        self.assertEqual(len(apps.requests), 1)

    def test_pinned_model_timeout_without_manifest_keeps_provider_failure(self):
        from symblic.providers import ollama_call as B
        route = {**ROUTE, 'digest': 'a' * 64}
        source = N.planner_source('Return one JSON fixture.', route)
        apps = FakeApps(lambda req, n: {'ok': False,
            'error': 'transient: ollama request failed (curl exit 28): the generate request ran out of time',
            'model': route['model'], 'node': route['node'], 'ms': 300000,
            'model_identity': B.unavailable('ollama', route['model'], 'launcher_reported_no_observation', route['node'])})
        result = N.execute(source, self.path, apps, route, limit=1, output_binding='proposal')
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(M.failure_class(result), 'MODEL_TIMEOUT')
        self.assertNotIn('identity conflicts', json.dumps(result['error']))
        self.assertEqual(result['calls'], 1)
        repeated = N.execute(source, self.path, apps, route, limit=1, output_binding='proposal')
        self.assertEqual(repeated, result)
        self.assertEqual(len(apps.requests), 1)

    def test_plan_then_run_reuses_the_same_root_budget_and_proposal(self):
        apps = FakeApps(lambda req, n: json.dumps(proposal()) if 'output_format' in req['prompt']
                        else 'function inc(x) { return x + 1; }')
        req = request(max_calls=2)
        planned = M.MicaRun(req, self.path, apps, inventory()).plan(mode='mica')
        self.assertEqual(planned['status'], 'planned', planned)
        self.assertEqual(planned['calls'], 1)
        result = self.run_mica(apps, req, mode='mica')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 2)
        self.assertEqual(len(apps.requests), 2)

    def test_crash_after_completed_branch_recovers_when_no_call_budget_remains(self):
        class FixtureCrash(BaseException):
            pass
        apps = FakeApps(); req = request(max_calls=1)
        original = M._put
        def interrupted(root, name, value):
            if name == 'mica-result.json':
                raise FixtureCrash('fixture interruption before terminal publication')
            return original(root, name, value)
        with mock.patch.object(M, '_put', side_effect=interrupted):
            with self.assertRaises(FixtureCrash):
                self.run_mica(apps, req)
        self.assertEqual(len(apps.requests), 1)
        result = self.run_mica(apps, req)
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)

    def test_unknown_delivery_stays_unknown_and_never_redispatches(self):
        apps = FakeApps(lambda req, n: RuntimeError('fixture lost acknowledgement'))
        first = self.run_mica(apps, request(retries=1))
        self.assertEqual(first['status'], 'unknown', first)
        self.assertEqual(len(apps.requests), 1)
        second = self.run_mica(apps, request(retries=1))
        self.assertEqual(second['status'], 'unknown', second)
        self.assertEqual(len(apps.requests), 1)
        # Reservations are not observed calls; they need separate reporting.
        self.assertEqual(second['calls'], 1)
        self.assertFalse((self.path / 'mica-result.json').exists())

    def test_later_parallel_unknown_prevents_earlier_pending_dispatch_on_resume(self):
        class FixtureCrash(BaseException):
            pass
        later_dispatched = threading.Event()
        def callback(req, number):
            if 'BODY_B' in req['prompt']:
                later_dispatched.set()
                raise RuntimeError('fixture later branch acknowledgement lost')
            raise AssertionError('Earlier pending branch must never reach the provider')
        apps = FakeApps(callback)
        req = request(max_calls=4)
        plan = self.parallel_plan(req)
        original = N.execute
        def interrupted(source, folder, *args, **kwargs):
            if Path(folder).name == 'build-000-a':
                self.assertTrue(later_dispatched.wait(5), 'Later parallel fixture failed to dispatch')
                raise FixtureCrash('interruption before earlier branch native dispatch')
            return original(source, folder, *args, **kwargs)
        with mock.patch.object(N, 'execute', side_effect=interrupted):
            with self.assertRaises(FixtureCrash):
                self.run_mica(apps, req, mode='static', plans=[plan], inv=inventory(('node-a', 'node-b')))
        self.assertEqual(len(apps.requests), 1)
        result = self.run_mica(apps, req, mode='static', plans=[plan], inv=inventory(('node-a', 'node-b')))
        self.assertEqual(result['status'], 'unknown', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)

    def test_native_frozen_source_route_and_inputs_refuse_changed_attempt(self):
        source = N.planner_source('Return one JSON fixture.', ROUTE).replace('ask proposal:', 'given seed: Int.\nask proposal:')
        apps = FakeApps(lambda req, n: '{"fixture":true}')
        original = N.execute(source, self.path, apps, ROUTE, limit=1, output_binding='proposal', inputs={'seed': 1})
        self.assertEqual(original['status'], 'done', original)
        variations = [(source.replace('one JSON fixture', 'another JSON fixture'), ROUTE, {'seed': 1}),
                      (source, {**ROUTE, 'node': 'node-b'}, {'seed': 1}),
                      (source, ROUTE, {'seed': 2})]
        for changed, route, inputs in variations:
            with self.subTest(source=changed, route=route, inputs=inputs):
                with self.assertRaises(ValueError):
                    N.execute(changed, self.path, apps, route, limit=1, output_binding='proposal', inputs=inputs)
        self.assertEqual(len(apps.requests), 1)

    def test_corrupt_call_journal_cannot_retain_cached_success(self):
        source = N.planner_source('Return one JSON fixture.', ROUTE)
        apps = FakeApps(lambda req, n: '{"fixture":true}')
        result = N.execute(source, self.path, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(result['status'], 'done', result)
        journal = self.path / 'graph-calls.jsonl'
        journal.write_text(journal.read_text() + '{incomplete\n')
        with self.assertRaises(ValueError):
            N.execute(source, self.path, apps, ROUTE, limit=1, output_binding='proposal')
        self.assertEqual(len(apps.requests), 1)

    def test_bad_planner_graph_uses_next_bounded_alternative(self):
        planner_calls = []
        def callback(req, n):
            if 'output_format' in req['prompt']:
                planner_calls.append(req['prompt'])
                return json.dumps({'units': []} if len(planner_calls) == 1 else proposal())
            return 'function inc(x) { return x + 1; }'
        apps = FakeApps(callback)
        result = self.run_mica(apps, request(max_candidates=2), mode='mica')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 3)
        self.assertEqual(len(planner_calls), 2)
        self.assertIn('MODEL_OUTPUT_ERROR', planner_calls[1])
        self.assertEqual(result['attempts'][0]['failure'], 'MODEL_OUTPUT_ERROR')

    def test_native_repair_receives_public_counterexample_then_passes(self):
        apps = FakeApps(lambda req, n: 'function inc(x) { return x; }' if n == 1 else 'function inc(x) { return x + 1; }')
        result = self.run_mica(apps, request(retries=1))
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 2)
        self.assertEqual(len(apps.requests), 2)
        self.assertIn('inc(2)', apps.requests[1]['prompt'])
        self.assertNotEqual(apps.requests[0]['prompt'], apps.requests[1]['prompt'])

    def test_root_acceptance_rejects_candidate_that_passes_its_own_examples(self):
        proposed = proposal(); proposed['units'][0]['examples'] = [['inc(0)', '0']]
        proposed['units'][0]['body'] = 'Return zero.'
        req = request(max_candidates=1)
        plan = M.proposal_to_plan(C.normalize_request(req), proposed)
        apps = FakeApps(lambda req, n: 'function inc(x) { return 0; }')
        result = self.run_mica(apps, req, mode='static', plans=[plan])
        self.assertNotEqual(result['status'], 'done', result)
        self.assertEqual(result['attempts'][0]['failure'], 'INTEGRATION_FAILURE')
        self.assertEqual(len(apps.requests), 1)
        self.assertNotIn('output', result)

    def test_call_budget_counts_every_failed_repair_and_never_oversubscribes(self):
        apps = FakeApps(lambda req, n: 'function inc(x) { return 0; }')
        result = self.run_mica(apps, request(max_calls=1, retries=2, max_candidates=3))
        self.assertNotEqual(result['status'], 'done', result)
        self.assertLessEqual(len(apps.requests), 1)
        self.assertEqual(result['calls'], len(apps.requests))

    def parallel_plan(self, req):
        return M.proposal_to_plan(C.normalize_request(req), {'units': [
            proposed_unit('a', 'plusOne', 'BODY_A: return x plus one.', [['plusOne(2)', '3']]),
            proposed_unit('b', 'unrelated', 'BODY_B: unrelated fixture.', [['unrelated(2)', '2']]),
            proposed_unit('final', 'inc', 'BODY_C: call plusOne(x).', [['inc(2)', '3']], ['plusOne'])]})

    def fixture_callback(self, req, n):
        prompt = req['prompt']
        if 'BODY_C' in prompt:
            return 'function inc(x) { return plusOne(x); }'
        if 'BODY_B' in prompt:
            return 'function unrelated(x) { /*UNRELATED_BRANCH_SENTINEL*/ return x; }'
        if 'BODY_A' in prompt:
            return 'function plusOne(x) { /*DECLARED_DEPENDENCY_SENTINEL*/ return x + 1; }'
        raise AssertionError('Unexpected fixture prompt')

    def test_multiworker_single_node_serializes_provider_dispatch(self):
        req = request(max_calls=4)
        apps = FakeApps(self.fixture_callback, delay=0.2)
        result = self.run_mica(apps, req, mode='static', plans=[self.parallel_plan(req)])
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(apps.max_active_by_node['node-a'], 1)
        self.assertEqual(len(apps.requests), 3)

    def test_dependency_capsule_contains_declared_closure_only(self):
        req = request(max_calls=4)
        apps = FakeApps(self.fixture_callback)
        result = self.run_mica(apps, req, mode='static', plans=[self.parallel_plan(req)], inv=inventory(('node-a', 'node-b')))
        self.assertEqual(result['status'], 'done', result)
        final = next(r['prompt'] for r in apps.requests if 'BODY_C' in r['prompt'])
        self.assertIn('DECLARED_DEPENDENCY_SENTINEL', final)
        self.assertNotIn('UNRELATED_BRANCH_SENTINEL', final)
        self.assertNotIn('BODY_B', final)

    def test_unrelated_local_evaluator_file_never_enters_provider_context(self):
        hidden = 'EVALUATOR_ONLY_SECRET_FIXTURE_4fac39'
        (Path(self.temp.name) / 'heldout.json').write_text(json.dumps({'test': hidden}))
        apps = FakeApps()
        result = self.run_mica(apps)
        self.assertEqual(result['status'], 'done', result)
        self.assertTrue(apps.requests)
        for row in apps.requests:
            self.assertNotIn(hidden, json.dumps(row))


if __name__ == '__main__':
    unittest.main()
