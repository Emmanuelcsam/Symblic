"""Experiments: cellular-sheaf consistency and finite schema/predicate transport, computed exactly.

Research experiment, no result claimed. Supplied finite structures only; no solving, providers, stores or effects.

Experiments:
    cellular-sheaf           compare endpoint restrictions with an exact coboundary matrix and keep each disagreement
                             (checks a supplied assignment; does not solve for a global section)
    finite-schema-transport  check supplied inverse maps, predicate pullbacks, fiber quantifiers and one commuting
                             square on finite labelled sets

Depends on: the standard library only. Run through ``symblic.experiments.registry``.
Sources: see SOURCES (Hansen and Ghrist; Spivak, Functorial Data Migration).
"""
# Import identity must precede first-party imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from copy import deepcopy
from fractions import Fraction as F
import json
import re

VERSION = 1
MAX_BITS = 512
MAX_WORK = 20000
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,31}\Z')
_UNIT = re.compile(r'[A-Za-z][A-Za-z0-9 _./^*-]{0,47}\Z')
_Q = re.compile(r'-?(?:0|[1-9][0-9]{0,6})(?:/[1-9][0-9]{0,6})?\Z')
SOURCES = {
    'cellular-sheaf': [{'title': 'Hansen and Ghrist, Toward a Spectral Theory of Cellular Sheaves',
        'url': 'https://arxiv.org/abs/1808.01513', 'scope': 'Graph stalks, restrictions and degree-zero coboundary.'}],
    'finite-schema-transport': [{'title': 'Spivak, Functorial Data Migration',
        'url': 'https://arxiv.org/abs/1009.1166', 'scope': 'Finite tables, typed maps and commuting squares; no general migration engine.'}],
}
LIMITS = {
    'cellular-sheaf': ['At most 8 vertices, 16 oriented edges and stalk dimensions 1..3; no self-loops, parallel edges allowed.',
        'Fixed bases, dimensionless restriction matrices and one common caller-declared value unit.',
        'Checks the supplied assignment for global-section compatibility. It does not solve for a section or infer that none exists.',
        'Squared discrepancy uses the declared coordinate Euclidean norm; it is not invariant under arbitrary changes of basis.',
        'No higher cells, Hodge theorem, semantic agreement or empirical-truth inference.'],
    'finite-schema-transport': ['Four named finite sets of 1..8 labels and five supplied total maps; predicates are Boolean tables.',
        'Pullback is composition; existential/universal pushforwards quantify over fibers, including empty fibers.',
        'Round trips and one commuting square are checked exhaustively on the declared domains.',
        'Adjunction checks apply to the supplied predicate pair. No general category equivalence, schema synthesis or arbitrary predicate evaluation.',
        'Labels have no inferred physical units or semantics; no numeric unit conversion is performed.'],
}


def _fail(code):
    raise ValueError(code)


def _bounded(value, maximum):
    count = size = 0
    active = set()
    def visit(item, depth):
        nonlocal count, size
        count += 1
        if count > 20000 or depth > 16:
            _fail('structure_bound')
        typ = type(item)
        if typ in (dict, list):
            if id(item) in active or len(item) > 128:
                _fail('structure_bound')
            active.add(id(item)); size += 2 + max(0, len(item)-1)
            if typ is dict:
                for key, child in item.items():
                    if type(key) is not str or len(key) > 128:
                        _fail('json_key')
                    visit(key, depth+1); size += 1; visit(child, depth+1)
            else:
                for child in item:
                    visit(child, depth+1)
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
            _fail('exact_json_required')
        if size > maximum:
            _fail('byte_bound')
    visit(value, 0)


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        _fail('schema')


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        _fail('identifier')
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail('integer_bound')
    return value


def _q(value):
    if type(value) is int:
        _integer(value, -1000000, 1000000)
    elif type(value) is not str or not _Q.fullmatch(value):
        _fail('rational')
    else:
        numerator, _, denominator = value.partition('/')
        if abs(int(numerator)) > 1000000 or (denominator and int(denominator) > 1000000):
            _fail('rational_bound')
    result = F(value)
    if abs(result.numerator) > 1000000 or result.denominator > 1000000:
        _fail('rational_bound')
    return result


def _out(value):
    if type(value) is F:
        return value.numerator if value.denominator == 1 else str(value)
    if type(value) is list:
        return [_out(item) for item in value]
    if type(value) is dict:
        return {key: _out(item) for key, item in value.items()}
    return value


class _Work:
    def __init__(self):
        self.used = 0

    def charge(self):
        self.used += 1
        if self.used > MAX_WORK:
            _fail('arithmetic_work_bound')

    def add(self, a, b):
        self.charge()
        if not a:
            return b
        if not b:
            return a
        top = max(a.numerator.bit_length()+b.denominator.bit_length(),
                  b.numerator.bit_length()+a.denominator.bit_length())+1
        bottom = a.denominator.bit_length()+b.denominator.bit_length()
        if max(top, bottom) > MAX_BITS:
            _fail('arithmetic_bits_bound')
        return a+b

    def mul(self, a, b):
        self.charge()
        if not a or not b:
            return F(0)
        if max(a.numerator.bit_length()+b.numerator.bit_length(),
               a.denominator.bit_length()+b.denominator.bit_length()) > MAX_BITS:
            _fail('arithmetic_bits_bound')
        return a*b

    def dot(self, a, b):
        total = F(0)
        for x, y in zip(a, b):
            total = self.add(total, self.mul(x, y))
        return total


def _matrix(value, rows, cols):
    if type(value) is not list or len(value) != rows or any(type(row) is not list or len(row) != cols for row in value):
        _fail('restriction_shape')
    return [[_q(x) for x in row] for row in value]


def _read_sheaf(data):
    _fields(data, 'vertices edges value_unit')
    if type(data['value_unit']) is not str or not _UNIT.fullmatch(data['value_unit']):
        _fail('unit')
    vertices, edges = data['vertices'], data['edges']
    if type(vertices) is not list or not 1 <= len(vertices) <= 8:
        _fail('vertex_bound')
    if type(edges) is not list or len(edges) > 16:
        _fail('edge_bound')
    values = {}
    for vertex in vertices:
        _fields(vertex, 'id value')
        name = _id(vertex['id'])
        if name in values:
            _fail('duplicate_vertex')
        vector = vertex['value']
        if type(vector) is not list or not 1 <= len(vector) <= 3:
            _fail('stalk_dimension')
        values[name] = [_q(x) for x in vector]
    parsed, ids = [], set()
    for edge in edges:
        _fields(edge, 'id tail head dimension tail_map head_map')
        name, tail, head = (_id(edge[key]) for key in ('id', 'tail', 'head'))
        if name in ids:
            _fail('duplicate_edge')
        ids.add(name)
        if tail not in values or head not in values or tail == head:
            _fail('edge_endpoints')
        dimension = _integer(edge['dimension'], 1, 3)
        parsed.append({'id': name, 'tail': tail, 'head': head, 'dimension': dimension,
            'tail_map': _matrix(edge['tail_map'], dimension, len(values[tail])),
            'head_map': _matrix(edge['head_map'], dimension, len(values[head]))})
    return values, parsed


def _coboundary(values, edges):
    columns = [(name, coordinate) for name, vector in values.items() for coordinate in range(len(vector))]
    indexed = {key: at for at, key in enumerate(columns)}
    rows, labels = [], []
    for edge in edges:
        for coordinate in range(edge['dimension']):
            row = [F(0)]*len(columns)
            for endpoint, sign in [('tail', -1), ('head', 1)]:
                for j, coefficient in enumerate(edge[endpoint+'_map'][coordinate]):
                    row[indexed[edge[endpoint], j]] = -coefficient if sign < 0 else coefficient
            rows.append(row); labels.append({'edge': edge['id'], 'coordinate': coordinate})
    return rows, [{'vertex': name, 'coordinate': coordinate} for name, coordinate in columns], labels


def _sheaf(data):
    values, edges = _read_sheaf(data)  # Validate every shape/limit before matrix work.
    work = _Work()
    matrix, columns, rows = _coboundary(values, edges)
    assignment = [x for vector in values.values() for x in vector]
    matrix_residual = [work.dot(row, assignment) for row in matrix]
    direct, local = [], []
    for edge in edges:
        tail = [work.dot(row, values[edge['tail']]) for row in edge['tail_map']]
        head = [work.dot(row, values[edge['head']]) for row in edge['head_map']]
        residual = [work.add(h, -t) for h, t in zip(head, tail)]
        direct.extend(residual)
        local.append({'id': edge['id'], 'tail_image': tail, 'head_image': head,
                      'residual': residual, 'compatible': tail == head})
    if direct != matrix_residual:
        _fail('coboundary_internal_check')
    energy = work.dot(direct, direct)
    compatible = all(row['compatible'] for row in local)
    if compatible != (not any(matrix_residual)) or compatible != (energy == 0):
        _fail('compatibility_internal_check')
    return {'orientation': 'tail negative, head positive', 'vertex_values': values,
            'columns': columns, 'rows': rows, 'coboundary_matrix': matrix,
            'assignment': assignment, 'coboundary_residual': matrix_residual,
            'edge_checks': local, 'global_section': compatible,
            'squared_discrepancy': energy, 'norm': 'sum of squared edge-coordinate residuals',
            'units': {'value': data['value_unit'], 'restriction': 'dimensionless',
                      'residual': data['value_unit'], 'squared_discrepancy': '('+data['value_unit']+')^2'},
            'work': {'arithmetic_operations': work.used, 'dense_matrix_terms': len(rows)*len(columns)}}, \
           {'independent_edge_and_matrix_agree': True, 'zero_residual_iff_compatible': True,
            'nonnegative_squared_discrepancy': energy >= 0, 'supplied_assignment_is_global_section': compatible}


def _set(value):
    if type(value) is not list or not 1 <= len(value) <= 8:
        _fail('finite_set_bound')
    result = [_id(x) for x in value]
    if len(set(result)) != len(result):
        _fail('duplicate_element')
    return result


def _map(value, domain, codomain):
    if type(value) is not dict or set(value) != set(domain):
        _fail('total_map_domain')
    if any(type(x) is not str or x not in codomain for x in value.values()):
        _fail('map_codomain')
    return dict(value)


def _predicate(value, domain):
    if type(value) is not dict or set(value) != set(domain) or any(type(x) is not bool for x in value.values()):
        _fail('predicate_table')
    return dict(value)


def _schema(data):
    _fields(data, 'sets maps predicates')
    _fields(data['sets'], 'A B C D'); _fields(data['maps'], 'forward backward left right bottom')
    _fields(data['predicates'], 'A B')
    sets = {name: _set(values) for name, values in data['sets'].items()}
    types = {'forward': ('A', 'B'), 'backward': ('B', 'A'), 'left': ('A', 'C'),
             'right': ('B', 'D'), 'bottom': ('C', 'D')}
    maps = {name: _map(data['maps'][name], sets[source], sets[target]) for name, (source, target) in types.items()}
    p, q = (_predicate(data['predicates'][name], sets[name]) for name in ('A', 'B'))
    forward, backward = maps['forward'], maps['backward']
    round_a = {a: backward[forward[a]] for a in sets['A']}
    round_b = {b: forward[backward[b]] for b in sets['B']}
    pullback = {a: q[forward[a]] for a in sets['A']}
    fibers = {b: [a for a in sets['A'] if forward[a] == b] for b in sets['B']}
    existential = {b: any(p[a] for a in fiber) for b, fiber in fibers.items()}
    universal = {b: all(p[a] for a in fiber) for b, fiber in fibers.items()}
    preservation = {a: p[a] == pullback[a] for a in sets['A']}
    square = [{'element': a, 'right_after_forward': maps['right'][forward[a]],
               'bottom_after_left': maps['bottom'][maps['left'][a]],
               'commutes': maps['right'][forward[a]] == maps['bottom'][maps['left'][a]]} for a in sets['A']]
    def included(lhs, rhs):
        return all(not lhs[key] or rhs[key] for key in lhs)
    existential_lhs, existential_rhs = included(existential, q), included(p, pullback)
    universal_lhs, universal_rhs = included(pullback, p), included(q, universal)
    if existential_lhs != existential_rhs or universal_lhs != universal_rhs:
        _fail('predicate_adjoint_internal_check')
    return {'sets': sets, 'map_types': {name: {'domain': source, 'codomain': target} for name, (source, target) in types.items()},
            'maps': maps, 'roundtrip_A': round_a, 'roundtrip_B': round_b,
            'left_inverse': all(a == value for a, value in round_a.items()),
            'right_inverse': all(b == value for b, value in round_b.items()),
            'predicates': {'A': p, 'B': q}, 'pullback_B_to_A': pullback,
            'fibers': fibers, 'existential_A_to_B': existential, 'universal_A_to_B': universal,
            'predicate_preserved': all(preservation.values()), 'predicate_checks': preservation,
            'naturality_square': square, 'square_commutes': all(row['commutes'] for row in square),
            'square_equation': 'right composed with forward = bottom composed with left, on A',
            'predicate_adjunctions': {'existential_image_subset_B': existential_lhs,
                'A_subset_pullback': existential_rhs, 'pullback_subset_A': universal_lhs,
                'B_subset_universal_image': universal_rhs},
            'units': 'symbolic labels and Boolean predicates; no inferred numeric conversion',
            'work': {'roundtrip_elements': len(sets['A'])+len(sets['B']),
                     'fiber_membership_tests': len(sets['A'])*len(sets['B']),
                     'naturality_elements': len(sets['A'])}}, \
           {'all_maps_total_and_typed': True, 'existential_adjunction_for_supplied_pair': True,
            'universal_adjunction_for_supplied_pair': True, 'exhaustive_declared_domains': True,
            'forward_backward_are_inverses': all(a == v for a, v in round_a.items()) and all(b == v for b, v in round_b.items()),
            'supplied_predicate_preserved': all(preservation.values()),
            'supplied_square_commutes': all(row['commutes'] for row in square)}


def catalog():
    sheaf = {'vertices': [{'id': 'a', 'value': [1, 2]}, {'id': 'b', 'value': [3]}],
        'edges': [{'id': 'ab', 'tail': 'a', 'head': 'b', 'dimension': 1,
                   'tail_map': [[1, 1]], 'head_map': [[1]]}], 'value_unit': 'signal'}
    schema = {'sets': {'A': ['a0', 'a1'], 'B': ['b0', 'b1'], 'C': ['c0', 'c1'], 'D': ['d0', 'd1']},
        'maps': {'forward': {'a0': 'b0', 'a1': 'b1'}, 'backward': {'b0': 'a0', 'b1': 'a1'},
                 'left': {'a0': 'c0', 'a1': 'c1'}, 'right': {'b0': 'd0', 'b1': 'd1'},
                 'bottom': {'c0': 'd0', 'c1': 'd1'}},
        'predicates': {'A': {'a0': True, 'a1': False}, 'B': {'b0': True, 'b1': False}}}
    rows = [('cellular-sheaf', 'Check local-to-global sheaf consistency',
             'Compare endpoint restrictions with an exact coboundary matrix and retain each disagreement.', sheaf),
            ('finite-schema-transport', 'Transport finite schemas and predicates',
             'Check supplied inverse maps, predicate pullbacks/fiber quantifiers and a commuting square.', schema)]
    return [{'id': ident, 'title': title, 'summary': summary, 'example': example,
             'sources': deepcopy(SOURCES[ident]), 'limits': list(LIMITS[ident])}
            for ident, title, summary, example in rows]


def run(experiment_id, data):
    if type(experiment_id) is not str or experiment_id not in SOURCES:
        _fail('experiment_id')
    _bounded(data, 131072)
    results, checks = (_sheaf if experiment_id == 'cellular-sheaf' else _schema)(data)
    answer = {'arithmetic': {'kind': 'exact rational and finite Boolean tables', 'max_bits': MAX_BITS,
                'max_arithmetic_operations': MAX_WORK, 'version': VERSION},
        'results': _out(results), 'checks': checks, 'limits': list(LIMITS[experiment_id]),
        'sources': deepcopy(SOURCES[experiment_id])}
    _bounded(answer, 524288)
    return answer
