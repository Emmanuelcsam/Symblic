"""Experiments: finite matroids, boundary graph cuts and graph smoothing, computed exactly.

Research experiment, no result claimed. Caller-supplied finite structures only; physical or semantic
interpretations are not inferred from the numbers.

Experiments:
    finite-matroid      validate a finite independence family and compare the greedy weighted basis with every basis
    boundary-graph-cut  compute a supplied graph cut by exact max-flow and by exhaustive partitions
    graph-smoothing     run fixed exact averaging steps and report baseline, energy and distortion

Depends on: the standard library only. Run through ``symblic.experiments.registry``.
Sources: see SOURCES (Edmonds 1971; Bao et al. 2015; others listed per experiment).
"""

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import json
import re
from collections import deque
from fractions import Fraction

VERSION = 1
MAX_GROUND = 8
MAX_BULK = 10
MAX_VERTICES = 16
MAX_EDGES = 64
MAX_STEPS = 64
MAX_BITS = 512
MAX_INPUT_BYTES = 131072
MAX_RESULT_BYTES = 524288
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,31}\Z')
_UNIT = re.compile(r'[A-Za-z][A-Za-z0-9 _./^*-]{0,47}\Z')
_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]{0,6})(?:/[1-9][0-9]{0,6})?\Z')

SOURCES = {
    'finite-matroid': [
        {'title': 'Edmonds, Matroids and the greedy algorithm (1971)',
         'url': 'https://doi.org/10.1007/BF01584082',
         'scope': 'Finite independence and greedy weighted basis optimization.'},
        {'title': 'Adiprasito, Huh and Katz, Hodge Theory for Combinatorial Geometries',
         'url': 'https://arxiv.org/abs/1511.02888',
         'scope': 'Research motivation; this experiment does not implement the Hodge theory.'}],
    'boundary-graph-cut': [
        {'title': 'Bao et al., The Holographic Entropy Cone (2015)',
         'url': 'https://arxiv.org/abs/1505.07839',
         'scope': 'Motivates a weighted boundary graph cut functional.'},
        {'title': 'Ryu and Takayanagi, Holographic Derivation of Entanglement Entropy from AdS/CFT',
         'url': 'https://arxiv.org/abs/hep-th/0603001',
         'scope': 'Physical motivation only; supplied graphs are not identified with physical states.'}],
    'graph-smoothing': [
        {'title': 'Shuman et al., The Emerging Field of Signal Processing on Graphs',
         'url': 'https://arxiv.org/abs/1211.0053',
         'scope': 'Nonnegative weighted graph Laplacian and Dirichlet energy.'}],
}
LIMITS = {
    'finite-matroid': [
        'The complete independent-set family is supplied; this does not learn a dependence oracle.',
        'At most 8 ground elements; axioms and all candidate bases are checked finitely.',
        'No Hodge ring, sheaf compatibility, or theorem beyond this finite input is established.'],
    'boundary-graph-cut': [
        'This is an undirected nonnegative weighted graph-cut model with declared boundary vertices.',
        'At most 6 boundary and 10 bulk vertices, 64 edges, and 1024 exhaustive bulk assignments.',
        'The cut capacity has the supplied weight unit; no AdS geometry, physical entropy, or LLM truth is inferred.'],
    'graph-smoothing': [
        'At most 16 numeric vertices, 64 nonnegative edges, and 64 fixed simultaneous steps.',
        'Weights and step size are dimensionless; values have the caller-declared common unit.',
        'Smoothing can erase useful differences; original values, baseline, and distortion remain visible.',
        'No claim of semantic preservation, prompt-injection defense, physical diffusion, or convergence rate.'],
}


def _fail(code):
    raise ValueError(code)


def _obj(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        _fail('fields')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail('integer_bound')
    return value


def _bounded_json(value, maximum, *, result=False):
    """Charge before serialization, including cycles/types/depth/huge integers."""
    count = 0
    size = 0
    active = set()

    def visit(item, depth):
        nonlocal count, size
        count += 1
        if count > (32768 if result else 8192) or depth > 16:
            _fail('structure_bound')
        typ = type(item)
        if typ in (list, dict):
            if len(item) > 256 or id(item) in active:
                _fail('structure_bound')
            size += 2 + max(0, len(item) - 1)
            active.add(id(item))
            if typ is dict:
                for key, child in item.items():
                    if type(key) is not str or len(key) > 256:
                        _fail('json_key')
                    size += len(json.dumps(key, ensure_ascii=True)) + 1
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(id(item))
        elif typ is str:
            if len(item) > 4096:
                _fail('text_bound')
            try:
                item.encode('utf-8')
            except UnicodeError:
                _fail('unicode')
            size += len(json.dumps(item, ensure_ascii=True))
        elif typ is int:
            if item.bit_length() > MAX_BITS:
                _fail('integer_bound')
            size += len(str(item))
        elif item is None or typ is bool:
            size += 5
        else:
            _fail('json_type')
        if size > maximum:
            _fail('byte_bound')

    visit(value, 0)


def _ids(values, low, high):
    if type(values) is not list or not low <= len(values) <= high:
        _fail('id_bound')
    for value in values:
        if type(value) is not str or not _ID.fullmatch(value):
            _fail('identifier')
    if len(set(values)) != len(values):
        _fail('duplicate_id')
    return list(values)


def _unit(value):
    if type(value) is not str or not _UNIT.fullmatch(value):
        _fail('unit')
    return value


def _q(value):
    if type(value) is int:
        if abs(value) > 1000000:
            _fail('number_bound')
        return Fraction(value)
    if type(value) is not str or not _NUMBER.fullmatch(value):
        _fail('rational')
    numerator, _, denominator = value.partition('/')
    if abs(int(numerator)) > 1000000 or (denominator and int(denominator) > 1000000):
        _fail('number_bound')
    return Fraction(value)


def _guard(value):
    if value.numerator.bit_length() > MAX_BITS or value.denominator.bit_length() > MAX_BITS:
        _fail('arithmetic_bound')
    return value


def _sum(values):
    total = Fraction(0)
    for value in values:
        total = _guard(total + value)
    return total


def _out(value):
    _guard(value)
    return value.numerator if value.denominator == 1 else f'{value.numerator}/{value.denominator}'


def _mask(values, ground):
    values = _ids(values, 0, len(ground))
    if not set(values) <= set(ground):
        _fail('unknown_id')
    return sum(1 << ground.index(value) for value in values)


def _members(mask, ground):
    return [value for index, value in enumerate(ground) if mask & (1 << index)]


def _validate_matroid(family, n):
    if 0 not in family:
        _fail('matroid_empty')
    hereditary = 0
    exchange_pairs = 0
    exchange_candidates = 0
    for mask in sorted(family):
        for i in range(n):
            if mask & (1 << i):
                hereditary += 1
                if mask ^ (1 << i) not in family:
                    _fail('matroid_hereditary')
    for small in sorted(family):
        for large in sorted(family):
            if small.bit_count() >= large.bit_count():
                continue
            exchange_pairs += 1
            found = False
            for i in range(n):
                bit = 1 << i
                if large & bit and not small & bit:
                    exchange_candidates += 1
                    if small | bit in family:
                        found = True
                        break
            if not found:
                _fail('matroid_exchange')
    return {'hereditary_membership_checks': hereditary,
            'exchange_pairs': exchange_pairs, 'exchange_membership_checks': exchange_candidates}


def _matroid(data):
    _obj(data, 'ground independent_sets weights query weight_unit')
    ground = _ids(data['ground'], 1, MAX_GROUND)
    raw = data['independent_sets']
    if type(raw) is not list or not 1 <= len(raw) <= 2 ** len(ground):
        _fail('family_bound')
    masks = [_mask(row, ground) for row in raw]
    if len(set(masks)) != len(masks):
        _fail('duplicate_set')
    family = set(masks)
    query = _mask(data['query'], ground)
    if type(data['weights']) is not dict or set(data['weights']) != set(ground):
        _fail('weights')
    weights = {key: _q(data['weights'][key]) for key in ground}
    unit = _unit(data['weight_unit'])
    _sum(abs(v) for v in weights.values())
    work = _validate_matroid(family, len(ground))
    rank = max(mask.bit_count() for mask in family)
    query_rank = max(mask.bit_count() for mask in family if mask & query == mask)
    chosen = 0
    decisions = []
    for key in sorted(ground, key=lambda key: (-weights[key], ground.index(key))):
        candidate = chosen | (1 << ground.index(key))
        accepted = candidate in family
        decisions.append({'element': key, 'accepted': accepted})
        if accepted:
            chosen = candidate
    bases = [mask for mask in sorted(family) if mask.bit_count() == rank]
    scores = {mask: _sum(weights[key] for key in _members(mask, ground)) for mask in bases}
    optimum = max(scores.values())
    greedy_score = _sum(weights[key] for key in _members(chosen, ground))
    work.update({'greedy_membership_checks': len(ground),
                 'exhaustive_family_scans': len(family), 'exhaustive_bases_scored': len(bases)})
    checks = {'independence_axioms': True, 'greedy_is_basis': chosen in bases,
              'greedy_matches_exhaustive_optimum': greedy_score == optimum}
    if not all(checks.values()):
        _fail('internal_check')
    return {'ground': ground, 'weight_unit': unit,
            'weights': {key: _out(value) for key, value in weights.items()},
            'query': _members(query, ground), 'query_independent': query in family,
            'rank': rank, 'query_rank': query_rank, 'independent_set_count': len(family),
            'greedy': {'basis': _members(chosen, ground), 'weight': _out(greedy_score),
                       'decisions': decisions},
            'exhaustive_baseline': {'optimum_weight': _out(optimum),
                                    'optimal_bases': [_members(mask, ground) for mask in bases
                                                      if scores[mask] == optimum]},
            'work': work}, checks


def _edges(raw, vertices):
    if type(raw) is not list or len(raw) > MAX_EDGES:
        _fail('edge_bound')
    edges = []
    seen = set()
    for row in raw:
        _obj(row, 'u v weight')
        if type(row['u']) is not str or type(row['v']) is not str:
            _fail('edge_vertex')
        if row['u'] not in vertices or row['v'] not in vertices or row['u'] == row['v']:
            _fail('edge_vertex')
        u, v = sorted((vertices.index(row['u']), vertices.index(row['v'])))
        if (u, v) in seen:
            _fail('duplicate_edge')
        seen.add((u, v))
        weight = _q(row['weight'])
        if weight < 0:
            _fail('negative_weight')
        edges.append((u, v, weight))
    _sum(weight for _, _, weight in edges)
    return sorted(edges)


def _cut_capacity(edges, side):
    return _sum(weight for u, v, weight in edges if (u in side) != (v in side))


def _mincut(vertices, edges, source_boundary, sink_boundary):
    """Exact Edmonds-Karp on symmetric capacities; artificial boundary arcs exceed every cut."""
    n = len(vertices)
    source, sink = n, n + 1
    capacity = [[Fraction(0) for _ in range(n + 2)] for _ in range(n + 2)]
    for u, v, weight in edges:
        capacity[u][v] = capacity[v][u] = weight
    infinite = _guard(_sum(weight for _, _, weight in edges) + 1)
    for u in source_boundary:
        capacity[source][u] = infinite
    for u in sink_boundary:
        capacity[u][sink] = infinite
    residual = [row[:] for row in capacity]
    flow = Fraction(0)
    augmentations = searches = edge_scans = 0
    while True:
        searches += 1
        parents = {source: None}
        queue = deque([source])
        while queue and sink not in parents:
            u = queue.popleft()
            for v in range(n + 2):
                edge_scans += 1
                if v not in parents and residual[u][v] > 0:
                    parents[v] = u
                    queue.append(v)
        if sink not in parents:
            reachable = {u for u in parents if u < n}
            return flow, reachable, {'augmentations': augmentations,
                                     'bfs_searches': searches, 'residual_entries_scanned': edge_scans}
        if augmentations >= 4096:
            _fail('work_bound')
        path = []
        v = sink
        while v != source:
            u = parents[v]
            path.append((u, v))
            v = u
        amount = min(residual[u][v] for u, v in path)
        for u, v in path:
            residual[u][v] = _guard(residual[u][v] - amount)
            residual[v][u] = _guard(residual[v][u] + amount)
        flow = _guard(flow + amount)
        augmentations += 1


def _enumerate_cuts(edges, boundary_side, bulk_indices):
    best = None
    witness = None
    ties = 0
    assignments = 1 << len(bulk_indices)
    for mask in range(assignments):
        side = boundary_side | {u for i, u in enumerate(bulk_indices) if mask & (1 << i)}
        score = _cut_capacity(edges, side)
        if best is None or score < best:
            best, witness, ties = score, side, 1
        elif score == best:
            ties += 1
    return best, witness, ties, assignments


def _boundary_cut(data):
    _obj(data, 'boundary bulk edges region weight_unit')
    boundary = _ids(data['boundary'], 2, 6)
    bulk = _ids(data['bulk'], 0, MAX_BULK)
    vertices = boundary + bulk
    if len(set(vertices)) != len(vertices):
        _fail('duplicate_id')
    region = _ids(data['region'], 1, len(boundary) - 1)
    if not set(region) <= set(boundary):
        _fail('unknown_id')
    unit = _unit(data['weight_unit'])
    edges = _edges(data['edges'], vertices)
    source_side = {vertices.index(u) for u in region}
    sink_side = set(range(len(boundary))) - source_side
    flow, side, work = _mincut(vertices, edges, source_side, sink_side)
    best, baseline_side, ties, assignments = _enumerate_cuts(
        edges, source_side, list(range(len(boundary), len(vertices))))
    witness_capacity = _cut_capacity(edges, side)
    checks = {'boundary_condition': source_side <= side and not sink_side & side,
              'flow_equals_cut': flow == witness_capacity,
              'cut_matches_exhaustive_optimum': witness_capacity == best}
    if not all(checks.values()):
        _fail('internal_check')
    work.update({'exhaustive_bulk_assignments': assignments,
                 'exhaustive_edge_checks': assignments * len(edges)})
    return {'model': 'supplied undirected weighted boundary graph',
            'capacity_unit': unit, 'region': [u for u in boundary if u in region],
            'boundary': boundary, 'bulk': bulk,
            'min_cut_capacity': _out(witness_capacity), 'max_flow_value': _out(flow),
            'source_side': [u for i, u in enumerate(vertices) if i in side],
            'sink_side': [u for i, u in enumerate(vertices) if i not in side],
            'crossing_edges': [{'u': vertices[u], 'v': vertices[v], 'weight': _out(weight)}
                               for u, v, weight in edges if (u in side) != (v in side)],
            'exhaustive_baseline': {'capacity': _out(best), 'tied_minimum_partitions': ties,
                                    'source_side': [u for i, u in enumerate(vertices)
                                                    if i in baseline_side]},
            'work': work}, checks


def _energy(values, edges):
    # E = one half of the undirected-edge Dirichlet sum, by declared convention.
    return _guard(_sum(_guard(weight * _guard(_guard(values[u] - values[v]) ** 2))
                       for u, v, weight in edges) / 2)


def _smoothing(data):
    if type(data) is not dict or data.get('mode') not in ('sequence', 'graph'):
        _fail('mode')
    fields = 'mode values alpha steps units'
    _obj(data, fields if data['mode'] == 'sequence' else fields + ' vertices edges')
    _obj(data['units'], 'value edge_weight step')
    value_unit = _unit(data['units']['value'])
    if data['units']['edge_weight'] != 'dimensionless' or data['units']['step'] != 'dimensionless':
        _fail('unit')
    raw = data['values']
    if type(raw) is not list or not 1 <= len(raw) <= MAX_VERTICES:
        _fail('value_bound')
    original = [_q(value) for value in raw]
    steps = _integer(data['steps'], 0, MAX_STEPS)
    alpha = _q(data['alpha'])
    if not 0 <= alpha <= 1:
        _fail('alpha_bound')
    if data['mode'] == 'sequence':
        vertices = [f'v{i + 1}' for i in range(len(raw))]
        edges = [(i, i + 1, Fraction(1)) for i in range(len(raw) - 1)]
    else:
        vertices = _ids(data['vertices'], len(raw), len(raw))
        edges = _edges(data['edges'], vertices)
    n = len(vertices)
    degrees = [_sum(weight for u, v, weight in edges if i in (u, v)) for i in range(n)]
    if _guard(2 * alpha * max(degrees)) > 1:
        _fail('lazy_step_bound')
    matrix = [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]
    for u, v, weight in edges:
        delta = _guard(alpha * weight)
        matrix[u][u] = _guard(matrix[u][u] - delta)
        matrix[v][v] = _guard(matrix[v][v] - delta)
        matrix[u][v] = matrix[v][u] = delta
    stochastic = all(value >= 0 for row in matrix for value in row)
    stochastic = stochastic and all(_sum(row) == 1 for row in matrix)
    stochastic = stochastic and all(_sum(matrix[i][j] for i in range(n)) == 1 for j in range(n))
    initial_sum = _sum(original)
    initial_energy = _energy(original, edges)
    values = original[:]
    trajectory = []
    conservation = monotone = range_preserved = independent_update = True
    last_energy = initial_energy
    for step in range(steps + 1):
        energy = _energy(values, edges)
        total = _sum(values)
        distortion = _sum(_guard(_guard(value - old) ** 2) for value, old in zip(values, original))
        conservation = conservation and total == initial_sum
        monotone = monotone and energy <= last_energy
        range_preserved = range_preserved and min(original) <= min(values) <= max(values) <= max(original)
        trajectory.append({'step': step, 'values': [_out(value) for value in values],
                           'sum': _out(total), 'energy': _out(energy),
                           'squared_distance_from_original': _out(distortion)})
        last_energy = energy
        if step == steps:
            break
        flux_result = values[:]
        for u, v, weight in edges:
            flux = _guard(_guard(alpha * weight) * _guard(values[v] - values[u]))
            flux_result[u] = _guard(flux_result[u] + flux)
            flux_result[v] = _guard(flux_result[v] - flux)
        matrix_result = [_sum(_guard(matrix[i][j] * values[j]) for j in range(n)) for i in range(n)]
        independent_update = independent_update and flux_result == matrix_result
        values = flux_result
    checks = {'nonnegative_doubly_stochastic_update': stochastic,
              'sum_conserved_every_step': conservation, 'energy_nonincreasing_every_step': monotone,
              'initial_value_range_preserved': range_preserved,
              'edge_flux_matches_matrix_every_step': independent_update}
    if not all(checks.values()):
        _fail('internal_check')
    return {'mode': data['mode'], 'vertices': vertices,
            'units': {'value': value_unit, 'sum': value_unit,
                      'energy': f'({value_unit})^2', 'squared_distance': f'({value_unit})^2',
                      'edge_weight': 'dimensionless', 'step': 'dimensionless'},
            'energy_definition': 'E = (1/2) sum over undirected edges of w_uv * (x_u - x_v)^2',
            'original_values': [_out(value) for value in original],
            'unsmoothed_baseline': {'values': [_out(value) for value in original],
                                    'sum': _out(initial_sum), 'energy': _out(initial_energy),
                                    'squared_distance_from_original': 0, 'unchanged_for_steps': steps},
            'alpha': _out(alpha), 'steps': steps,
            'maximum_weighted_degree': _out(max(degrees)),
            'update_matrix': [[_out(value) for value in row] for row in matrix],
            'trajectory': trajectory, 'final_values': [_out(value) for value in values],
            'work': {'edge_flux_updates': len(edges) * steps,
                     'independent_matrix_products': n * n * steps,
                     'energy_edge_terms': len(edges) * (steps + 2)}}, checks


def _examples():
    ground = ['a', 'b', 'c', 'd']
    return {
        'finite-matroid': {'ground': ground,
                           'independent_sets': [_members(mask, ground) for mask in range(16)
                                                if mask.bit_count() <= 2],
                           'weights': {'a': 5, 'b': 4, 'c': 2, 'd': -1},
                           'query': ['a', 'b', 'c'], 'weight_unit': 'score'},
        'boundary-graph-cut': {'boundary': ['A', 'B', 'C'], 'bulk': ['u', 'v'],
                               'edges': [{'u': 'A', 'v': 'u', 'weight': 3},
                                         {'u': 'u', 'v': 'v', 'weight': 2},
                                         {'u': 'v', 'v': 'B', 'weight': 3},
                                         {'u': 'v', 'v': 'C', 'weight': 1}],
                               'region': ['A'], 'weight_unit': 'capacity'},
        'graph-smoothing': {'mode': 'sequence', 'values': [0, 4, 0], 'alpha': '1/4',
                            'steps': 2, 'units': {'value': 'amplitude', 'edge_weight': 'dimensionless',
                                                 'step': 'dimensionless'}},
    }


def catalog():
    descriptions = {
        'finite-matroid': ('Finite matroid independence and weighted basis',
                           'Validate a finite independence family and compare greedy to every basis.'),
        'boundary-graph-cut': ('Boundary and bulk graph cut',
                               'Compute a supplied graph cut by exact max-flow and exhaustive partitions.'),
        'graph-smoothing': ('Graph and sequence smoothing',
                            'Run fixed exact averaging steps with unchanged baseline, energy and distortion.'),
    }
    examples = _examples()
    return [{'id': key, 'title': title, 'summary': summary, 'example': examples[key],
             'sources': [dict(source) for source in SOURCES[key]], 'limits': list(LIMITS[key])}
            for key, (title, summary) in descriptions.items()]


def run(experiment_id, data):
    if type(experiment_id) is not str or experiment_id not in SOURCES:
        _fail('experiment_id')
    _bounded_json(data, MAX_INPUT_BYTES)
    function = {'finite-matroid': _matroid, 'boundary-graph-cut': _boundary_cut,
                'graph-smoothing': _smoothing}[experiment_id]
    results, checks = function(data)
    answer = {'arithmetic': {'kind': 'exact rational', 'input_abs_numerator_max': 1000000,
                             'input_denominator_max': 1000000, 'retained_fraction_bits_max': MAX_BITS,
                             'version': VERSION},
              'results': results, 'checks': checks, 'limits': list(LIMITS[experiment_id]),
              'sources': [dict(source) for source in SOURCES[experiment_id]]}
    _bounded_json(answer, MAX_RESULT_BYTES, result=True)
    return answer
