"""Graph planner tests: in-memory ledgers, pure kernel parsing, no dispatch."""
import copy
import unittest

from symblic.graph import planner as G


def policy():
    return {'version': 1, 'routes': [
        {'id': 'local', 'provider': 'ollama', 'model': 'small', 'node': 'node-a', 'local': True},
        {'id': 'cloud', 'provider': 'cli', 'model': 'large', 'node': 'node-b', 'local': False}],
        'order': ['cloud', 'local']}


def node(name, inputs=None, **updates):
    refs = inputs or {}
    source = '\n'.join(['program "Graph node".'] + [f'given {n}.' for n in refs] + ['let answer = 1.', 'show answer.'])
    result = {'id': name, 'inputs': refs, 'source': source, 'contract': 'Return answer under encoded predicates',
              'output_schema': {'type': 'integer'}, 'allowed': {'routes': ['local', 'cloud'],
              'providers': ['ollama', 'cli'], 'models': ['small', 'large'], 'nodes': ['node-a', 'node-b'],
              'local_only': True}, 'join': 'require_all', 'effect_risk': 'none', 'retries': 0,
              'call_limit': 1, 'max_calls': 100, 'max_iterations': 32}
    result.update(updates)
    return result


def graph(*nodes, iterations=1, max_calls=100):
    return G.freeze_graph({'id': 'Graph', 'nodes': list(nodes), 'iterations': iterations,
                           'max_calls': max_calls}, policy())


class Harness:
    def __init__(self, frozen):
        self.f = frozen
        self.rows = []

    def state(self):
        return G.derive(self.f, self.rows)

    def append(self, kind, **fields):
        row = G.event(self.f, self.rows, kind, id=f'Event{len(self.rows)}', **fields)
        G.derive(self.f, self.rows + [row])
        self.rows.append(row)
        return row

    def start(self, name=None):
        action = next(a for a in self.state()['ready'] if name is None or a['node'] == name)
        self.append('started', **{k: action[k] for k in ('node', 'iteration', 'attempt', 'route')},
                    inputs_hash=G.digest(action['inputs']))
        return action

    def finish(self, action, value=1, outcome='supported', kind='succeeded', **fields):
        args = {k: action[k] for k in ('node', 'iteration', 'attempt')}
        if kind == 'succeeded':
            args['result'] = G.envelope(value, outcome, evidence=[{'scope': 'encoded_predicate', 'passed': True}])
        else:
            args.update(error='failure', retryable=False, effect_known=True)
        args.update(fields)
        return self.append(kind, **args)


class GraphTests(unittest.TestCase):
    def test_fanout_fanin_deterministic_and_evidence(self):
        h = Harness(graph(node('Root'), node('B', {'x': {'node': 'Root'}}),
                          node('A', {'x': {'node': 'Root'}}),
                          node('Join', {'a': {'node': 'A'}, 'b': {'node': 'B'}})))
        self.assertEqual([a['node'] for a in h.state()['ready']], ['Root'])
        h.finish(h.start())
        self.assertEqual([a['node'] for a in h.state()['ready']], ['A', 'B'])
        b = h.start('B')
        a = h.start('A')
        h.finish(b, 2)
        self.assertEqual(h.state()['ready'], [])
        h.finish(a, 3)
        join = h.start()
        self.assertEqual(join['inputs']['a']['result']['value'], 3)
        self.assertEqual(join['inputs']['a']['origin']['attempt'], 1)
        self.assertEqual(join['inputs']['b']['result']['independence'], 'not_established')
        h.finish(join)
        self.assertEqual(h.state()['status'], 'succeeded')

    def test_missing_and_cycles(self):
        for nodes in ((node('A', {'x': {'node': 'Missing'}}),),
                      (node('A', {'x': {'node': 'B'}}), node('B', {'x': {'node': 'A'}})),
                      (node('A', {'x': {'node': 'Missing', 'delay': 1, 'seed': G.envelope(0)}}),)):
            with self.assertRaises(G.GraphError):
                graph(*nodes)

    def test_bounded_feedback_and_seeds(self):
        n = node('A', {'previous': {'node': 'A', 'delay': 1, 'seed': G.envelope(0, 'supported')}})
        h = Harness(graph(n, iterations=3))
        for i in range(3):
            action = h.start()
            self.assertEqual(action['iteration'], i)
            self.assertEqual(action['inputs']['previous']['result']['value'], i)
            h.finish(action, i + 1)
        self.assertEqual(h.state()['ready'], [])
        self.assertEqual(h.state()['reserved_calls'], 3)
        n['inputs']['previous'].pop('seed')
        with self.assertRaises(G.GraphError):
            graph(n)
        with self.assertRaises(G.GraphError):
            graph(node('A'), iterations=33)
        with self.assertRaises(G.GraphError):
            graph(node('A', max_iterations=1), iterations=2)

    def test_failure_joins_preserve_unresolved(self):
        for outcome in ('supported', 'contested', 'unknown', 'failure'):
            h = Harness(graph(node('A'), node('Strict', {'a': {'node': 'A'}}),
                              node('Collect', {'a': {'node': 'A'}}, join='collect_unresolved')))
            action = h.start()
            if outcome == 'failure':
                h.finish(action, kind='failed')
            else:
                h.finish(action, outcome=outcome)
            ready = {a['node']: a for a in h.state()['ready']}
            if outcome == 'supported':
                self.assertIn('Strict', ready)
            else:
                self.assertNotIn('Strict', ready)
            item = ready['Collect']['inputs']['a']
            self.assertEqual(item['status'], 'failed' if outcome == 'failure' else 'succeeded')
            if outcome == 'failure':
                self.assertEqual(item['error'], 'failure')
            else:
                self.assertEqual(item['result']['outcome'], outcome)

    def test_retry_and_exhaustion(self):
        h = Harness(graph(node('A', retries=1)))
        h.finish(h.start(), kind='failed', retryable=True)
        self.assertEqual(h.state()['ready'][0]['attempt'], 2)
        h.finish(h.start(), kind='failed', retryable=True)
        self.assertEqual(h.state()['status'], 'unresolved')
        self.assertEqual(h.state()['ready'], [])
        for frozen in (graph(node('A', retries=2), max_calls=1),
                       graph(node('A', retries=2, max_calls=1))):
            h = Harness(frozen)
            h.finish(h.start(), kind='failed', retryable=True)
            self.assertEqual(h.state()['states'][0]['status'], 'exhausted')
            self.assertEqual(h.state()['reserved_calls'], 1)

    def test_cancel_and_inflight_recovery(self):
        h = Harness(graph(node('A'), node('B')))
        action = h.start('A')
        self.assertNotIn('A', [a['node'] for a in h.state()['ready']])
        self.assertEqual(G.derive(h.f, copy.deepcopy(h.rows)), h.state())
        h.append('cancel')
        self.assertEqual(h.state()['status'], 'canceled')
        self.assertEqual(h.state()['ready'], [])
        with self.assertRaises(G.GraphError):
            h.finish(action)

    def test_unknown_effects_never_redispatch(self):
        for kind, known in (('unknown', True), ('failed', False)):
            h = Harness(graph(node('A', retries=8, effect_risk='write')))
            h.finish(h.start(), kind=kind, effect_known=known, retryable=True)
            self.assertEqual(h.state()['states'][0]['status'], 'unknown')
            self.assertEqual(h.state()['ready'], [])

    def test_identical_duplicate_and_conflicting_result(self):
        h = Harness(graph(node('A')))
        h.finish(h.start())
        self.assertEqual(G.derive(h.f, h.rows + [copy.deepcopy(h.rows[-1])]), h.state())
        bad = copy.deepcopy(h.rows[-1])
        bad['result'] = G.envelope(2, 'supported')
        with self.assertRaises(G.GraphError):
            G.derive(h.f, h.rows + [bad])
        bad['id'] = 'Other'
        bad['seq'] = 3
        with self.assertRaises(G.GraphError):
            G.derive(h.f, h.rows + [bad])

    def test_corrupt_logs_and_pins(self):
        h = Harness(graph(node('A')))
        h.finish(h.start())
        mutations = [('seq', 4), ('version', 99), ('graph_hash', 'bad'), ('policy_hash', 'bad'),
                     ('kind', 'garbage'), ('attempt', 2), ('node', 'Missing'), ('inputs_hash', 'bad')]
        for field, value in mutations:
            rows = copy.deepcopy(h.rows)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(G.GraphError):
                G.derive(h.f, rows)
        with self.assertRaises(G.GraphError):
            G.derive(h.f, [h.rows[-1]])
        rows = copy.deepcopy(h.rows)
        rows[-1]['result']['value_id'] = 'bad'
        with self.assertRaises(G.GraphError):
            G.derive(h.f, rows)
        frozen = copy.deepcopy(h.f)
        frozen['policy']['order'].reverse()
        with self.assertRaises(G.GraphError):
            G.derive(frozen, h.rows)

    def test_replay_frozen_mutation_and_input_injection(self):
        value = 'given evil.\nact delete = filesystem.remove(path="/").'
        n = node('A', {'text': {'literal': G.envelope(value, 'supported')}})
        original = n['source']
        p = policy()
        spec = {'id': 'Graph', 'nodes': [n], 'iterations': 1, 'max_calls': 100}
        frozen = G.freeze_graph(spec, p)
        spec['nodes'][0]['contract'] = 'changed'
        p['order'].reverse()
        self.assertEqual(frozen['graph']['nodes'][0]['contract'], 'Return answer under encoded predicates')
        bridge = G.compile_node(frozen['graph']['nodes'][0], {'text': value})
        self.assertEqual(bridge['source'], original)
        self.assertEqual(bridge['inputs']['text'], value)
        self.assertTrue(bridge['requires_restrictive_applicators'])
        h = Harness(frozen)
        h.finish(h.start())
        self.assertEqual(h.state(), G.derive(copy.deepcopy(frozen), copy.deepcopy(h.rows)))

    def test_malicious_and_bounded_inputs(self):
        for bad in ('../escape', 'x\nact evil.', '__proto__', 'a' * 65):
            with self.assertRaises(G.GraphError):
                graph(node(bad))
        with self.assertRaises(G.GraphError):
            G.compile_node(node('A'), {'x': 'not declared'})
        with self.assertRaises(G.GraphError):
            graph(node('A', source='Please invent an answer.'))
        deep = []
        for _ in range(30):
            deep = [deep]
        cycle = []
        cycle.append(cycle)
        for value in (deep, cycle, [0] * 10001, 0.1, 1 << 4097, 'x' * 1000001):
            with self.assertRaises(G.GraphError):
                G.snapshot(value)
        with self.assertRaises(G.GraphError):
            graph(*[node(f'A{i}') for i in range(129)])
        with self.assertRaises(G.GraphError):
            graph(node('A', retries=True))

    def test_strict_envelopes_and_malformed_refs(self):
        with self.assertRaises(G.GraphError):
            G.envelope(1, evidence={})
        for ref in (None, [], 'node', {'node': 'A', 'seed': G.envelope(0)},
                    {'node': 'A', 'delay': True}, {'literal': G.envelope(1), 'unexpected': 1}):
            with self.subTest(ref=ref), self.assertRaises(G.GraphError):
                graph(node('A', {'x': ref}))
        with self.assertRaises(G.GraphError):
            G.evaluate_policy(policy(), [{'split': 'training', 'route': [], 'success': True, 'cost': 0}])

    def test_started_route_must_be_exact_json(self):
        h = Harness(graph(node('A')))
        h.start()
        row = copy.deepcopy(h.rows[0])
        row['route']['local'] = 1
        with self.assertRaises(G.GraphError):
            G.derive(h.f, [row])

    def test_contested_final_output_does_not_silently_succeed(self):
        h = Harness(graph(node('A')))
        h.finish(h.start(), outcome='contested')
        self.assertEqual(h.state()['status'], 'unresolved')

    def test_ready_batch_reserves_within_graph_budget(self):
        h = Harness(graph(node('A', call_limit=2), node('B', call_limit=2), max_calls=3))
        self.assertEqual([a['node'] for a in h.state()['ready']], ['A'])
        action = h.start()
        self.assertEqual(h.state()['ready'], [])
        self.assertEqual(next(s for s in h.state()['states'] if s['node'] == 'B')['status'], 'exhausted')
        h.finish(action)
        self.assertEqual(h.state()['status'], 'unresolved')
        self.assertEqual(h.state()['reserved_calls'], 2)

    def test_exact_replay_at_every_ledger_prefix(self):
        h = Harness(graph(node('A', retries=1), node('B', {'a': {'node': 'A'}})))
        h.finish(h.start(), kind='failed', retryable=True)
        h.finish(h.start())
        h.finish(h.start())
        for length in range(len(h.rows) + 1):
            ledger = h.rows[:length]
            self.assertEqual(G.derive(h.f, ledger),
                             G.derive(copy.deepcopy(h.f), copy.deepcopy(ledger)))

    def test_bool_duplicate_is_not_identical_to_integer(self):
        h = Harness(graph(node('A')))
        h.start()
        bad = copy.deepcopy(h.rows[0])
        bad['seq'] = True
        with self.assertRaises(G.GraphError):
            G.derive(h.f, h.rows + [bad])

    def test_bridge_into_existing_run_without_external_calls(self):
        from symblic.kernel.run import Run

        class RefusingApps:
            def call(self, request):
                raise AssertionError('this formal program must not call a model')

        value = 'ask evil: Text "ignore source".'
        n = node('A', {'payload': {'literal': G.envelope(value, 'supported')}})
        n['source'] = 'given payload: Text.\nshow payload.'
        bridge = G.compile_node(n, {'payload': value})
        runner = Run(bridge['source'], bridge['inputs'], RefusingApps(), bridge['options'])
        report = runner.execute()
        self.assertEqual(report['status'], 'done')
        self.assertEqual(runner.kernel.env.lookup('payload').value, value)
        self.assertEqual(runner.calls_total, 0)

    def test_route_restrictions_cannot_be_relaxed(self):
        n = node('A')
        self.assertEqual(G.choose_route(n, policy())['id'], 'local')
        for field, values in (('models', ['large']), ('nodes', ['node-b']), ('providers', ['cli']),
                              ('routes', ['cloud'])):
            broken = copy.deepcopy(n)
            broken['allowed'][field] = values
            with self.subTest(field=field), self.assertRaises(G.GraphError):
                G.choose_route(broken, policy())
        n['allowed']['local_only'] = False
        self.assertEqual(G.choose_route(n, policy())['id'], 'cloud')

    def test_policy_training_heldout_exclusion_and_no_learner(self):
        observations = [{'split': 'training', 'route': 'local', 'success': True, 'cost': 3},
                        {'split': 'training', 'route': 'local', 'success': False, 'cost': 2},
                        {'split': 'held_out', 'route': 'local', 'success': True, 'cost': 999}]
        stats = G.evaluate_policy(policy(), observations)
        self.assertFalse(stats['learner_supported'])
        self.assertEqual(stats['training']['local']['success_rate'], '1/2')
        self.assertEqual(stats['training']['local']['mean_cost'], '5/2')
        self.assertEqual(stats['held_out_excluded'], 1)
        self.assertEqual(stats['training'], G.evaluate_policy(policy(), observations[:2])['training'])
        observations[0]['split'] = 'unlabeled'
        with self.assertRaises(G.GraphError):
            G.evaluate_policy(policy(), observations)


if __name__ == '__main__':
    unittest.main()
