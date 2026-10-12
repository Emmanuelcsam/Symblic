"""Private expander gates: pure snapshots, fake providers and temporary stores."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from symblic.graph import planner as G
from symblic.graph import compose as C
from symblic.graph import run as R
from symblic.js import check as JS
from tests.graph.test_symblic_graph_run import FakeApps, Crash, node, policy


def leaf(name, inputs=None, source=None, **fields):
    return node(name, inputs, source, call_limit=1, max_calls=4, **fields)


def pair_definition():
    return {'nodes': [
        leaf('Draft', {}, 'given x: Int.\nlet answer = x + 1.\n', checks=['answer = x + 1']),
        leaf('Check', {'v': {'node': 'Draft'}}, 'given v: Int.\nlet answer = v * 2.',
             checks=['answer = v * 2'])],
        'inputs': {'request': {'targets': [{'node': 'Draft', 'input': 'x'}]}},
        'outputs': {'answer': {'node': 'Check'}}}


def document(body=None):
    body = pair_definition() if body is None else body
    return {'version': 1, 'id': 'RepeatedPair', 'definitions': {'Pair': body},
            'instances': [{'id': 'First', 'definition': 'Pair', 'sha256': C.definition_digest(body),
                           'inputs': {'request': {'literal': G.envelope(3, 'supported')}}},
                          {'id': 'Second', 'definition': 'Pair', 'sha256': C.definition_digest(body),
                           'inputs': {'request': {'instance': 'First', 'port': 'answer'}}}],
            'nodes': [], 'iterations': 1, 'max_calls': 8}


def repin(doc):
    for instance in doc['instances']:
        instance['sha256'] = C.definition_digest(doc['definitions'][instance['definition']])
    return doc


def semantic_state(state):
    """Compare outcomes; native report hashes also bind run-specific timings."""
    result = {key: state[key] for key in ('status', 'reserved_calls', 'node_calls')}
    result['states'] = []
    for row in state['states']:
        item = {key: row[key] for key in ('node', 'iteration', 'attempt', 'status')}
        item['input_origins'] = {key: value.get('origin') for key, value in row['inputs'].items()}
        if 'result' in row:
            item['result'] = {key: row['result'][key]
                              for key in ('value', 'value_id', 'outcome', 'assumptions', 'independence')}
            item['assurance'] = row['result']['evidence'][0]['assurance']
            item['scope'] = row['result']['evidence'][0]['scope']
        result['states'].append(item)
    return result


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        version = patch.object(JS, 'node_version', return_value='test-no-node')
        version.start(); self.addCleanup(version.stop)
        process = patch('subprocess.Popen', side_effect=AssertionError('no external process'))
        mock = process.start(); self.addCleanup(process.stop)
        self.addCleanup(lambda: self.assertFalse(mock.called))

    def expand(self, doc=None):
        return C.expand_composition(document() if doc is None else doc, policy())

    def run_graph(self, frozen, folder='run', apps=None, **kwargs):
        return R.GraphRun(frozen, self.folder / folder, apps or FakeApps(), **kwargs).execute()

    def test_flat_equivalence_exact_sources_and_no_mutation(self):
        doc = document(); before = copy.deepcopy(doc)
        result = self.expand(doc)
        first_draft, first_check = C._namespace('First', 'Draft'), C._namespace('First', 'Check')
        second_draft, second_check = C._namespace('Second', 'Draft'), C._namespace('Second', 'Check')
        body = doc['definitions']['Pair']
        manual = []
        for ids, incoming in (((first_draft, first_check), {'literal': G.envelope(3, 'supported')}),
                              ((second_draft, second_check), {'node': first_check})):
            a, b = copy.deepcopy(body['nodes'])
            a.update(id=ids[0], inputs={'x': incoming})
            b.update(id=ids[1], inputs={'v': {'node': ids[0]}})
            manual += [a, b]
        expected = G.freeze_graph({'id': doc['id'], 'nodes': manual, 'iterations': 1, 'max_calls': 8}, policy())
        self.assertEqual(result['frozen'], expected)
        self.assertEqual(doc, before)
        apps = FakeApps()
        actual = self.run_graph(result['frozen'], apps=apps)
        handwritten = self.run_graph(expected, folder='manual', apps=apps)
        self.assertEqual(semantic_state(actual), semantic_state(handwritten))
        self.assertEqual(actual['status'], 'succeeded')
        by_id = {row['node']: row for row in actual['states']}
        self.assertEqual(by_id[second_check]['result']['value'], 18)
        self.assertEqual(apps.calls, [])
        self.assertEqual(len(actual['states']), 4)
        self.assertEqual(result['manifest']['ports']['First']['outputs']['answer']['node'], first_check)
        for expanded in result['frozen']['graph']['nodes']:
            local = result['manifest']['nodes'][expanded['id']]['node']
            original = next(row for row in body['nodes'] if row['id'] == local)
            for key in set(original) - {'id', 'inputs'}:
                self.assertEqual(expanded[key], original[key], key)

    def test_fake_calls_completed_resume_and_top_level_connection(self):
        body = pair_definition()
        body['nodes'][0]['source'] = 'given x: Int.\nask answer: Int "Return x" from x with effort=low, retries=0.'
        body['nodes'][0]['checks'] = ['answer >= 0']
        doc = document(body)
        doc['nodes'] = [leaf('Final', {'x': {'instance': 'Second', 'port': 'answer'}},
                              'given x: Int.\nlet answer = x.', checks=['answer = x'])]
        frozen = self.expand(doc)['frozen']; apps = FakeApps(2)
        state = self.run_graph(frozen, apps=apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(self.run_graph(frozen, apps=apps), state)
        self.assertEqual(len(apps.calls), 2)
        final = next(row for row in state['states'] if row['node'] == 'Final')
        self.assertEqual(final['result']['value'], 4)
        self.assertEqual(final['inputs']['x']['origin']['node'], C._namespace('Second', 'Check'))
        self.assertEqual(final['result']['independence'], 'not_established')
        manual = []
        for instance, incoming in [('First', {'literal': G.envelope(3, 'supported')}),
                                   ('Second', {'node': C._namespace('First', 'Check')})]:
            a, b = copy.deepcopy(body['nodes'])
            a.update(id=C._namespace(instance, 'Draft'), inputs={'x': incoming})
            b.update(id=C._namespace(instance, 'Check'), inputs={'v': {'node': a['id']}})
            manual += [a, b]
        final_node = copy.deepcopy(doc['nodes'][0])
        final_node['inputs']['x'] = {'node': C._namespace('Second', 'Check')}
        manual.append(final_node)
        expected = G.freeze_graph({'id': doc['id'], 'nodes': manual, 'iterations': 1, 'max_calls': 8}, policy())
        self.assertEqual(frozen, expected)
        manual_apps = FakeApps(2)
        manual_state = self.run_graph(expected, folder='manual', apps=manual_apps)
        self.assertEqual(semantic_state(state), semantic_state(manual_state))
        self.assertEqual(len(manual_apps.calls), len(apps.calls))

    def test_crash_after_saved_result_replays_without_duplicate_call(self):
        body = {'nodes': [leaf('Ask')], 'inputs': {}, 'outputs': {'answer': {'node': 'Ask'}}}
        doc = document(body)
        for instance in doc['instances']: instance['inputs'] = {}
        frozen = self.expand(doc)['frozen']; apps = FakeApps(2)
        def crash(stage, action):
            if stage == 'result_saved': raise Crash()
        with self.assertRaises(Crash):
            self.run_graph(frozen, apps=apps, checkpoint=crash)
        self.assertEqual(len(apps.calls), 1)
        state = self.run_graph(frozen, apps=apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(apps.calls), 2)
        self.assertEqual(self.run_graph(frozen, apps=apps), state)
        self.assertEqual(len(apps.calls), 2)

    def test_unknown_call_intent_does_not_redispatch(self):
        body = {'nodes': [leaf('Ask')], 'inputs': {}, 'outputs': {'answer': {'node': 'Ask'}}}
        doc = document(body); doc['instances'] = doc['instances'][:1]; doc['instances'][0]['inputs'] = {}
        frozen = self.expand(doc)['frozen']
        apps = FakeApps(lambda _: (_ for _ in ()).throw(Crash()))
        with self.assertRaises(Crash): self.run_graph(frozen, apps=apps)
        state = self.run_graph(frozen, apps=apps)
        self.assertEqual(state['status'], 'unresolved', state)
        self.assertEqual(state['states'][0]['status'], 'unknown')
        self.assertEqual(len(apps.calls), 1)

    def test_cancelled_graph_has_no_new_calls_on_resume(self):
        frozen = self.expand()['frozen']; stop = threading.Event(); stop.set(); apps = FakeApps()
        state = self.run_graph(frozen, stop=stop, apps=apps)
        self.assertEqual(state['status'], 'canceled')
        self.assertEqual(self.run_graph(frozen, apps=apps), state)
        self.assertEqual(apps.calls, [])

    def test_namespace_stable_under_declaration_order_and_collision_refuses(self):
        doc = document(); original = self.expand(doc)
        doc['instances'].reverse(); doc['definitions']['Pair']['nodes'].reverse(); repin(doc)
        reordered = self.expand(doc)
        self.assertEqual(reordered['frozen'], original['frozen'])
        self.assertNotEqual(reordered['manifest']['composition_sha256'], original['manifest']['composition_sha256'])
        with patch.object(C, '_namespace', return_value='Repeated'), self.assertRaisesRegex(G.GraphError, 'collision'):
            self.expand()
        doc = document(); doc['nodes'] = [leaf(C._namespace('First', 'Draft'))]
        with self.assertRaisesRegex(G.GraphError, 'collision'): self.expand(doc)

    def test_digest_drift_and_hidden_budget_or_permission_override_refuse(self):
        for field, value in [('max_calls', 999), ('allowed', {}), ('iterations', 2), ('instances', [])]:
            doc = document(); doc['definitions']['Pair'][field] = value; repin(doc)
            with self.subTest(field=field), self.assertRaises(G.GraphError): self.expand(doc)
        for field, value in [('max_calls', 1), ('allowed', {}), ('effect_risk', 'none')]:
            doc = document(); doc['instances'][0][field] = value
            with self.subTest(instance_field=field), self.assertRaises(G.GraphError): self.expand(doc)
        doc = document(); doc['definitions']['Pair']['nodes'][0]['source'] += '\nshow answer.'
        with self.assertRaisesRegex(G.GraphError, 'digest'): self.expand(doc)

    def test_ports_missing_extra_overwrite_and_untyped_refuse(self):
        doc = document(); del doc['instances'][0]['inputs']['request']
        with self.assertRaises(G.GraphError): self.expand(doc)
        doc = document(); doc['instances'][0]['inputs']['extra'] = {'literal': G.envelope(0)}
        with self.assertRaises(G.GraphError): self.expand(doc)
        doc = document(); doc['definitions']['Pair']['inputs']['request']['targets'] *= 2; repin(doc)
        with self.assertRaisesRegex(G.GraphError, 'duplicate'): self.expand(doc)
        doc = document(); doc['definitions']['Pair']['nodes'][0]['inputs']['x'] = {'literal': G.envelope(1)}; repin(doc)
        with self.assertRaisesRegex(G.GraphError, 'overwriting'): self.expand(doc)
        doc = document(); doc['definitions']['Pair']['nodes'][0]['source'] = 'given x.\nlet answer = x.'; repin(doc)
        with self.assertRaisesRegex(G.GraphError, 'explicit'): self.expand(doc)

    def test_public_fanout_uses_native_type_and_join_identity(self):
        body = pair_definition()
        body['nodes'][1]['inputs'] = {}
        body['inputs']['request']['targets'].append({'node': 'Check', 'input': 'v'})
        result = self.expand(document(body))
        self.assertEqual(result['manifest']['ports']['First']['inputs']['request']['contract']['native_type'], {'k': 'int'})
        body['nodes'][1]['source'] = 'given v: Text.\nlet answer = 1.'
        with self.assertRaisesRegex(G.GraphError, 'contracts differ'): self.expand(document(body))
        body = pair_definition(); body['nodes'][0]['source'] = 'define Count as Int.\ngiven x: Count.\nlet answer = x + 1.'
        self.expand(document(body))

    def test_private_internal_escape_and_missing_outputs_refuse(self):
        for ref in ({'node': C._namespace('First', 'Draft')},
                    {'instance': 'First', 'port': 'Draft'}, {'instance': 'Missing', 'port': 'answer'}):
            doc = document(); doc['instances'][1]['inputs']['request'] = ref
            with self.subTest(ref=ref), self.assertRaises(G.GraphError): self.expand(doc)
        doc = document(); doc['definitions']['Pair']['nodes'][1]['inputs']['v'] = {'node': 'External'}; repin(doc)
        with self.assertRaises(G.GraphError): self.expand(doc)
        doc = document(); doc['definitions']['Pair']['outputs']['answer']['node'] = 'Missing'; repin(doc)
        with self.assertRaises(G.GraphError): self.expand(doc)

    def test_global_cycle_and_delayed_feedback_clock(self):
        body = {'nodes': [leaf('Add', {}, 'given x: Int.\nlet answer = x + 1.', checks=['answer = x + 1'])],
                'inputs': {'request': {'targets': [{'node': 'Add', 'input': 'x'}]}},
                'outputs': {'answer': {'node': 'Add'}}}
        doc = document(body)
        doc['instances'][0]['inputs']['request'] = {'instance': 'Second', 'port': 'answer'}
        with self.assertRaisesRegex(G.GraphError, 'cycle'): self.expand(doc)
        doc['instances'][0]['inputs']['request'].update(delay=1, seed=G.envelope(0, 'supported'))
        doc['iterations'] = 3
        state = self.run_graph(self.expand(doc)['frozen'])
        self.assertEqual(state['status'], 'succeeded', state)
        values = {(r['iteration'], r['node']): r['result']['value'] for r in state['states']}
        self.assertEqual([values[i, C._namespace('Second', 'Add')] for i in range(3)], [2, 4, 6])
        self.assertEqual(state['reserved_calls'], 6)
        del doc['instances'][0]['inputs']['request']['seed']
        with self.assertRaises(G.GraphError): self.expand(doc)

    def test_expansion_and_json_limits_refuse_before_freeze(self):
        doc = document(); doc['instances'] = [dict(doc['instances'][0], id='I' + str(i)) for i in range(33)]
        with patch.object(G, 'freeze_graph', side_effect=AssertionError('not reached')), self.assertRaises(G.GraphError):
            self.expand(doc)
        doc = document(); doc['definitions']['Pair']['nodes'] += [leaf('Extra' + str(i)) for i in range(63)]; repin(doc)
        with patch.object(G, 'freeze_graph', side_effect=AssertionError('not reached')), self.assertRaisesRegex(G.GraphError, 'expanded node'):
            self.expand(doc)
        doc = document(); doc['instances'][0]['inputs']['request'] = {'literal': {'cycle': doc}}
        with self.assertRaises(G.GraphError): self.expand(doc)
        doc = document(); doc['definitions']['Pair']['nodes'][0]['source'] = 'x' * 32769; repin(doc)
        with self.assertRaises(G.GraphError): self.expand(doc)

    def test_all_leaf_failures_and_parent_cap_remain_visible(self):
        body = pair_definition(); body['nodes'].append(leaf('Hidden', {}, 'let answer = 0.', checks=['answer = 1']))
        doc = document(body); doc['instances'] = doc['instances'][:1]
        state = self.run_graph(self.expand(doc)['frozen'])
        self.assertNotEqual(state['status'], 'succeeded')
        hidden = next(r for r in state['states'] if r['node'] == C._namespace('First', 'Hidden'))
        self.assertEqual(hidden['status'], 'failed')
        doc = document(); doc['max_calls'] = 1
        state = self.run_graph(self.expand(doc)['frozen'], folder='budget')
        self.assertEqual(state['reserved_calls'], 1)
        self.assertNotEqual(state['status'], 'succeeded')

    def test_route_and_effect_contracts_preserved_without_permission(self):
        doc = document()
        for node_ in doc['definitions']['Pair']['nodes']:
            node_['allowed']['providers'] = ['claude']
        repin(doc)
        with self.assertRaisesRegex(G.GraphError, 'permitted route'): self.expand(doc)
        doc = document(); body = doc['definitions']['Pair']; body['nodes'][0].update(
            source='given x: Int.\nact answer: Int = fixture.write().', effect_risk='write')
        repin(doc); frozen = self.expand(doc)['frozen']
        self.assertEqual(next(n for n in frozen['graph']['nodes'] if n['id'] == C._namespace('First', 'Draft'))['effect_risk'], 'write')
        apps = FakeApps()
        with self.assertRaisesRegex(R.Unsupported, 'effectful graph'): self.run_graph(frozen, apps=apps)
        self.assertEqual(apps.calls, [])

    def test_manifest_integrity_and_loaded_source_refusal(self):
        result = self.expand(); manifest = result['manifest']; expected = manifest.pop('sha256')
        self.assertEqual(expected, G.digest(manifest))
        result['frozen']['graph']['nodes'][0]['source'] = 'changed'
        self.assertNotEqual(self.expand()['frozen'], result['frozen'])
        with patch.object(C, '_SOURCE_LOADED', False), self.assertRaisesRegex(G.GraphError, 'loaded code'):
            self.expand()

    def test_checked_in_example_has_four_leaves_and_zero_model_calls(self):
        example = json.loads((Path(__file__).resolve().parents[2] / 'examples/reusable-graph.json').read_text())
        expanded = C.expand_composition(example['composition'], example['policy'])
        apps = FakeApps()
        state = self.run_graph(expanded['frozen'], apps=apps)
        self.assertEqual(state['status'], 'succeeded', state)
        self.assertEqual(len(state['states']), 4)
        output = expanded['manifest']['ports']['Second']['outputs']['answer']['node']
        self.assertEqual(next(row for row in state['states'] if row['node'] == output)['result']['value'], 18)
        self.assertEqual(apps.calls, [])


if __name__ == '__main__':
    unittest.main()
