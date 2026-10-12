"""Experiment: grow an integer arithmetic graph on training cases, freeze it, then test held-out inputs.

Research experiment, no result claimed.

Experiment:
    integer-graph-adaptation  bounded exact synthesis of a small integer DAG for the declared synthetic target
                              f(x, y) = x*x + y. Training (positive x) selects mutation parents; the final graph
                              is frozen before the held-out cases (negative x) are evaluated. The generated native
                              Symblic graphs run in memory with no provider or capability.

This tests adaptation within one known arithmetic target. It is not task-family generalisation, neural
learning or an empirical claim (see LIMITS).

Depends on: ``symblic.graph.planner`` (native graph compiler), ``symblic.policy.learning`` (frozen
training/held-out comparison) and ``symblic.kernel.run`` (exact execution). Run through
``symblic.experiments.registry``.
"""

# Bind the executing module to its exact first-party source before dependencies.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
import copy
import json

from symblic.graph import planner as G
from symblic.policy import learning as P
from symblic.kernel.run import Run

VERSION = 1
USES_NATIVE_KERNEL = True
# Pinned in every receipt (see registry._identity); the rest of the native kernel is covered by the kernel's
# own loaded-runtime check, which USES_NATIVE_KERNEL turns on.
DEPENDENCIES = ('symblic.graph.planner', 'symblic.policy.learning', 'symblic.kernel.language', 'symblic.kernel.run',
                'symblic.kernel.execution_pins')
EXPERIMENT = 'integer-graph-adaptation'
MAX_CASES = 8
MAX_ROUNDS = 2
MAX_CANDIDATES = 15
LIMITS = [
    'Exact, dimensionless integer DAG synthesis for the declared target x*x+y only.',
    'Two mutation rounds, at most 15 candidates, two arithmetic nodes per candidate and eight cases per split.',
    'Training uses positive x; heldout uses negative x. This is within the same known arithmetic target, not unseen task-family generalization.',
    'No model, capability, deployment, durable graph recovery, neural learning or empirical truth claim.',
    'Policy receipts retain their host-declared measurement qualifier; exact outputs are independently compared with the fixture formula.',
]
SOURCES = [
    {'title': 'Native graph planner and compiler', 'path': 'symblic/graph/planner.py'},
    {'title': 'Native exact execution', 'path': 'symblic/kernel/run.py'},
    {'title': 'Frozen training and heldout policy comparison', 'path': 'symblic/policy/learning.py'},
    {'title': 'Authored synthetic target', 'formula': 'f(x,y)=x*x+y', 'units': 'dimensionless'},
]
EXAMPLE = {'training': [{'x': 2, 'y': 1}, {'x': 3, 'y': 2}, {'x': 4, 'y': 3}],
           'heldout': [{'x': -2, 'y': 3}, {'x': -3, 'y': 1}, {'x': -4, 'y': 2}]}


class ExperimentError(ValueError):
    """Stable refusal before any native graph execution."""


class _NoCalls:
    def call(self, _request):
        raise RuntimeError('arithmetic experiment forbids provider calls')


def catalog():
    return copy.deepcopy([{'id': EXPERIMENT, 'title': 'Generate and test an integer graph',
        'summary': 'Grow arithmetic nodes using training cases, freeze the graph, then compare heldout inputs.',
        'example': EXAMPLE, 'sources': SOURCES, 'limits': LIMITS}])


def _data(data):
    try:
        P.digest(data)  # Reject cycles, non-exact JSON and excess structure before copying.
    except P.PolicyError as exc:
        raise ExperimentError('bounded_exact_json_required') from exc
    if type(data) is not dict or set(data) != {'training', 'heldout'}:
        raise ExperimentError('training_and_heldout_required')
    clean = copy.deepcopy(data)
    for split, rows in clean.items():
        if type(rows) is not list or not 1 <= len(rows) <= MAX_CASES:
            raise ExperimentError('case_limit')
        seen = set()
        for row in rows:
            if type(row) is not dict or set(row) != {'x', 'y'}:
                raise ExperimentError('case_schema')
            if any(type(row[k]) is not int or abs(row[k]) > 20 for k in ('x', 'y')):
                raise ExperimentError('bounded_integer_inputs_required')
            if (split == 'training' and row['x'] <= 0) or (split == 'heldout' and row['x'] >= 0):
                raise ExperimentError('declared_input_region_overlap')
            pair = (row['x'], row['y'])
            if pair in seen:
                raise ExperimentError('duplicate_case')
            seen.add(pair)
    return clean


def _seed():
    return {'version': VERSION, 'kind': 'integer-dag', 'nodes': [], 'output': 'X'}


def _mutations(parent):
    """Only the parent topology is visible here; no case data or labels."""
    old = parent['output']
    mutations = [('square', [old])]
    mutations += [(op, [old, other]) for op in ('add', 'subtract', 'multiply') for other in ('X', 'Y')]
    for op, args in mutations:
        child = copy.deepcopy(parent)
        node_id = 'N' + str(len(child['nodes']) + 1)
        child['nodes'].append({'id': node_id, 'type': 'Int', 'op': op, 'args': args})
        child['output'] = node_id
        yield child, {'operation': 'append_node', 'operator': op, 'arguments': args}


def _native_graph(candidate, inputs):
    """Deterministic conversion of our closed typed grammar to existing graph schema."""
    route = {'id': 'Exact', 'provider': 'fixture', 'model': 'exact_integer', 'node': 'inprocess', 'local': True}
    policy = {'version': 1, 'routes': [route], 'order': ['Exact']}
    allowed = {'routes': ['Exact'], 'providers': ['fixture'], 'models': ['exact_integer'],
               'nodes': ['inprocess'], 'local_only': True}
    nodes = []
    def append(name, refs, expression):
        source = '\n'.join(['use profile=verified.'] + [f'given {key}.' for key in refs]
                           + [f'let answer = {expression}.', 'show answer.'])
        nodes.append({'id': name, 'inputs': refs, 'source': source,
            'contract': 'Compute the declared exact integer expression from named inputs.',
            'output_binding': 'answer', 'output_schema': {'type': 'integer'},
            'allowed': copy.deepcopy(allowed), 'join': 'require_all', 'effect_risk': 'none',
            'retries': 0, 'call_limit': 1, 'max_calls': 1, 'max_iterations': 1})
    for name, key in [('X', 'x'), ('Y', 'y')]:
        append(name, {'a': {'literal': G.envelope(inputs[key], 'supported',
                 assumptions=[{'scope': 'synthetic_fixture_input'}])}}, 'a')
    for node in candidate['nodes']:
        refs = {name: {'node': value} for name, value in zip(('a', 'b'), node['args'])}
        expression = {'square': 'a*a', 'add': 'a+b', 'subtract': 'a-b', 'multiply': 'a*b'}[node['op']]
        append(node['id'], refs, expression)
    # Graph reservations are node-attempt allowances, not provider calls. Actual Run has max_calls=0.
    return G.freeze_graph({'id': 'ArithmeticFixture', 'nodes': nodes, 'iterations': 1,
                           'max_calls': len(nodes)}, policy)


def _execute(candidate, inputs):
    frozen = _native_graph(candidate, inputs)
    replay = G.Replay(frozen)
    spec = {n['id']: n for n in frozen['graph']['nodes']}
    values, native_runs = {}, 0
    while (action := replay.next_action()) is not None:
        fields = {key: action[key] for key in ('node', 'iteration', 'attempt')}
        replay.apply(replay.event('started', id=f'Event{replay.next_seq}', **fields,
            route=action['route'], inputs_hash=G.digest(action['inputs'])))
        supplied = {key: item['result']['value'] for key, item in action['inputs'].items()}
        bridge = G.compile_node(spec[action['node']], supplied)
        runner = Run(bridge['source'], supplied, _NoCalls(), {'profile': 'verified', 'max_calls': 0,
                     'max_steps': 2000, 'side_effects': False, 'constructor': 'off',
                     'determine': False, 'solve': False})
        report = runner.execute()
        if report['status'] != 'done' or report['calls'] != 0 or len(report['outputs']) != 1:
            raise ExperimentError('native_arithmetic_execution_failed')
        value = report['outputs'][0]['value']
        if type(value) is not int or abs(value) > 1_000_000:
            raise ExperimentError('native_integer_result_required')
        values[action['node']] = value
        native_runs += 1
        replay.apply(replay.event('succeeded', id=f'Event{replay.next_seq}', **fields,
            result=G.envelope(value, 'supported', evidence=[{'scope': 'native_exact_arithmetic',
                                                          'calls': 0}])))
    state = replay.state()
    if state['status'] != 'succeeded':
        raise ExperimentError('native_graph_incomplete')
    return {'value': values[candidate['output']], 'arithmetic_nodes': len(candidate['nodes']),
            'native_node_runs': native_runs, 'provider_calls': 0,
            'graph_hash': frozen['graph_hash'], 'policy_hash': frozen['policy_hash']}


def _cases(rows, split):
    # Groups are declared input regions, never independent task families.
    region = 'positive_x' if split == 'training' else 'negative_x'
    return [{'case_hash': P.digest({'fixture_case': row}),
             'family_hash': P.digest({'declared_input_region': region}),
             'input_hash': P.digest(row), 'exposure_hashes': []} for row in rows]


def _plan(candidates, baseline, cases):
    return {'version': 1, 'candidates': [{'sha256': key, 'policy': candidates[key]}
            for key in sorted(candidates)], 'baseline': baseline, 'cases': cases,
            'budget': {'max_calls': 0, 'max_cost_units': MAX_ROUNDS},
            'objective': {'max_score': 2000, 'score_weight': 3, 'call_weight': 0, 'cost_weight': 1,
                'unknown_cost': 'reject', 'tie_break': 'policy_sha256_ascending', 'min_heldout_gain': 0}}


def _measure(candidates, rows, cases, cache):
    records, observations = [], []
    for key in sorted(candidates):
        for row, case in zip(rows, cases):
            cache_key = (key, case['input_hash'])
            reused = cache_key in cache
            if not reused:
                cache[cache_key] = _execute(candidates[key], row)
            result = cache[cache_key]
            target = row['x'] * row['x'] + row['y']
            error = abs(result['value'] - target)
            records.append({'candidate': key, 'case': case['case_hash'], 'status': 'success',
                'score': max(0, 2000-error), 'attempts': [{'calls': 0, 'cost_units': result['arithmetic_nodes']}]})
            observations.append({'candidate': key, 'case': case['case_hash'], 'inputs': row,
                'target': target, 'absolute_error': error, 'exact': error == 0,
                'reused_exact_evaluation': reused, **result})
    return records, observations


def _train(rows):
    """Heldout values/metadata cannot enter mutation or training selection."""
    seed = _seed()
    baseline = P.digest(seed)
    candidates, cache, lineage, rounds = {baseline: seed}, {}, [], []
    cases, parent = _cases(rows, 'training'), seed
    for round_id in range(1, MAX_ROUNDS+1):
        parent_hash = P.digest(parent)
        for child, mutation in _mutations(parent):
            key = P.digest(child)
            if key not in candidates:
                candidates[key] = child
                lineage.append({'candidate': key, 'parent': parent_hash, 'round': round_id, **mutation})
        if len(candidates) > MAX_CANDIDATES:
            raise ExperimentError('candidate_limit')
        plan = _plan(candidates, baseline, cases)
        records, observations = _measure(candidates, rows, cases, cache)
        selection = P.select(plan, records, expected_plan_hash=P.digest(plan), expected_records_hash=P.digest(records))
        parent = json.loads(selection['selected']['policy_json'])
        rounds.append({'round': round_id, 'parent': parent_hash,
            'candidate_count': len(candidates), 'selected': selection['selected']['sha256'],
            'training_plan_hash': P.digest(plan), 'training_records_hash': P.digest(records)})
    return {'candidates': candidates, 'lineage': lineage, 'rounds': rounds, 'plan': plan,
            'records': records, 'observations': observations, 'selection': selection,
            'executed_native_nodes': sum(r['native_node_runs'] for r in cache.values()),
            'executed_arithmetic_nodes': sum(r['arithmetic_nodes'] for r in cache.values())}


def run(experiment_id, data):
    if experiment_id != EXPERIMENT:
        raise ExperimentError('unknown_experiment')
    clean = _data(data)
    training = _train(clean['training'])
    plan, records, selection = (training[key] for key in ('plan', 'records', 'selection'))
    # This receipt is complete before any heldout output is computed.
    frozen = {'training_plan': P.digest(plan), 'training_records': P.digest(records),
              'selection': P.digest(selection)}
    heldout_plan = {'version': 1, 'training_plan_hash': frozen['training_plan'],
                    'cases': _cases(clean['heldout'], 'heldout')}
    P.validate_split(plan['cases'], heldout_plan['cases'])
    selected = selection['selected']['sha256']
    compared = {key: training['candidates'][key] for key in {selected, plan['baseline']}}
    heldout_records, observations = _measure(compared, clean['heldout'], heldout_plan['cases'], {})
    pins = {**frozen, 'heldout_plan': P.digest(heldout_plan), 'heldout_records': P.digest(heldout_records)}
    heldout = P.evaluate_heldout(plan, records, selection, heldout_plan, heldout_records, pins=pins)
    return {'arithmetic': {'kind': 'exact_integer', 'units': 'dimensionless', 'target': 'x*x+y',
                'score': 'max(0,2000-absolute_error)', 'utility': '3*score-arithmetic_nodes',
                'cost_unit': 'one executed arithmetic DAG node', 'provider_calls': 0},
        'results': {'version': VERSION, 'experiment': EXPERIMENT, 'training': training,
            'freeze': frozen, 'heldout_plan': heldout_plan, 'heldout_records': heldout_records,
            'heldout_observations': observations, 'heldout': heldout,
            'native_selected_graph': _native_graph(training['candidates'][selected], {'x': 0, 'y': 0}),
            'native_selected_graph_role': 'Zero-input presentation instance; scored execution graph hashes are in observations.',
            'scoring_cost_units': 'Logical arithmetic-node cost per evaluation, including reused exact results; work records actual executions.',
            'work': {'training_native_nodes': training['executed_native_nodes'],
                'training_arithmetic_nodes': training['executed_arithmetic_nodes'],
                'heldout_native_nodes': sum(row['native_node_runs'] for row in observations),
                'heldout_arithmetic_nodes': sum(row['arithmetic_nodes'] for row in observations)}},
        'checks': {'frozen_before_heldout': True, 'heldout_reselection': False,
            'native_graph_schema': True, 'native_arithmetic_execution': True, 'provider_calls': 0,
            'split_grouping': 'declared_positive_vs_negative_input_regions_same_target'},
        'limits': copy.deepcopy(LIMITS), 'sources': copy.deepcopy(SOURCES)}
