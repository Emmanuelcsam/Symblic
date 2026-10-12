"""Experiments: finite quantum-probability and tensor models computed with exact rational arithmetic.

Research experiment, no result claimed. These calculations evaluate explicit, caller-supplied finite models;
they do not infer anything about a person's, a model's or a physical system's state.

Experiments (ids as listed by ``python3 -m symblic.experiments.registry list``):
    question_order_fit    fit a two-dimensional projector model of question-order effects on training counts
                          and compare held-out scores with a classical contextual model
    density_measurements  validate a density matrix and a POVM, then compare predictions before and after dephasing
    circuit_rewrite       check exact channel equality of two small circuits (1-2 qubits; H, X, Z, CNOT, SWAP)
    tensor_semantics      contract a supplied subject-relation-object tensor; compare reversal, negation and a
                          one-hot lookup baseline

Rational results stay exact (``Fraction``); any decimal logarithm is computed separately with ``Decimal``.
Also provides the small validation helpers (``fields``, ``integer``, ``q``, ``wire``, ``fail``) that the other
experiment modules reuse.

Depends on: the standard library only. Run through ``symblic.experiments.registry``.
Sources: see ORDER_SOURCE, TENSOR_SOURCE, CIRCUIT_SOURCE and MEASUREMENT_SOURCE below.
"""

# Bind the executing module to its exact first-party source before dependencies.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import re

VERSION = 1
_RATIONAL = re.compile(r'-?\d{1,40}(?:/[1-9]\d{0,39})?\Z')
ORDER_SOURCE = 'https://jbusemey.pages.iu.edu/quantum/PNAS2014.pdf'
TENSOR_SOURCE = 'https://arxiv.org/abs/1003.4394'
CIRCUIT_SOURCE = 'https://arxiv.org/abs/1307.7025'
MEASUREMENT_SOURCE = 'https://cs.uwaterloo.ca/~watrous/TQI/TQI.pdf'


def fail(code):
    raise ValueError(code)


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        fail('schema')


def integer(x, low, high):
    if type(x) is not int or not low <= x <= high:
        fail('integer_bound')
    return x


def q(x):
    if type(x) is int and abs(x) <= 2**53-1:
        return F(x)
    if type(x) is not str or not _RATIONAL.fullmatch(x):
        fail('rational')
    return F(x)


def wire(x):
    if isinstance(x, F):
        if max(x.numerator.bit_length(), x.denominator.bit_length()) > 4096:
            fail('arithmetic_bound')
        return str(x)
    if type(x) is dict:
        return {k: wire(v) for k, v in x.items()}
    if type(x) in (list, tuple):
        return [wire(v) for v in x]
    return x


def matrix(x, n):
    if type(x) is not list or len(x) != n or any(type(r) is not list or len(r) != n for r in x):
        fail('matrix_shape')
    return [[q(a) for a in r] for r in x]


def ident(n):
    return [[F(i == j) for j in range(n)] for i in range(n)]


def transpose(a):
    return [list(r) for r in zip(*a)]


def multiply(a, b):
    return [[sum(x*y for x, y in zip(row, col)) for col in zip(*b)] for row in a]


def subtract(a, b):
    return [[x-y for x, y in zip(ar, br)] for ar, br in zip(a, b)]


def psd2(a):
    return a[0][1] == a[1][0] and a[0][0] >= 0 and a[1][1] >= 0 and a[0][0]*a[1][1] >= a[0][1]**2


def projector(a):
    return a == transpose(a) and multiply(a, a) == a


def probability(state, a, b, yes_a, yes_b):
    first = a if yes_a else subtract(ident(2), a)
    second = b if yes_b else subtract(ident(2), b)
    v = multiply(multiply(second, first), [[s] for s in state])
    return sum(r[0]**2 for r in v) / sum(s*s for s in state)


def counts(value):
    fields(value, 'AB BA')
    result = {}
    for order, row in value.items():
        if type(row) is not list or len(row) != 4:
            fail('counts_shape')
        result[order] = [integer(c, 0, 1_000_000) for c in row]
        if not sum(row):
            fail('empty_counts')
    return result


def score(predictions, observations):
    # Multiclass Brier per individual response, aggregated from cell counts.
    total = sum(sum(r) for r in observations.values())
    brier = sum(c*(sum(p*p for p in predictions[o])+1-2*predictions[o][i])
                for o in observations for i, c in enumerate(observations[o])) / total
    calibration = sum((p-F(c, sum(observations[o])))**2
                      for o in observations for p, c in zip(predictions[o], observations[o])) / 2
    nll = Decimal(0)
    impossible = False
    with localcontext() as ctx:
        ctx.prec = 50
        for order in observations:
            for p, c in zip(predictions[order], observations[order]):
                if c and not p:
                    impossible = True
                elif c:
                    nll -= c*(Decimal(p.numerator)/Decimal(p.denominator)).ln()
        nll /= total
    return {'brier': brier, 'squared_frequency_error': calibration,
            'mean_negative_log_likelihood_nats': None if impossible else str(nll),
            'likelihood_status': 'zero_probability_observed' if impossible else 'finite',
            'observations': total}


def order_fit(data):
    fields(data, 'train heldout candidates smoothing')
    train, heldout = counts(data['train']), counts(data['heldout'])
    alpha = q(data['smoothing'])
    if not 0 <= alpha <= 100:
        fail('smoothing_bound')
    candidates = data['candidates']
    if type(candidates) is not list or not 1 <= len(candidates) <= 32:
        fail('candidate_bound')
    rows = []
    for index, candidate in enumerate(candidates):
        fields(candidate, 'state A B')
        state = candidate['state']
        if type(state) is not list or len(state) != 2:
            fail('state_shape')
        state = [q(x) for x in state]
        if not any(state):
            fail('zero_state')
        a, b = matrix(candidate['A'], 2), matrix(candidate['B'], 2)
        if not projector(a) or not projector(b):
            fail('not_projector')
        predictions = {name: [probability(state, p, r, x, y)
                             for x, y in ((True, True), (True, False), (False, True), (False, False))]
                       for name, p, r in [('AB', a, b), ('BA', b, a)]}
        rows.append({'index': index, 'predictions': predictions, 'training': score(predictions, train)})
    # Selection uses training only; held-out counts are deliberately absent here.
    selected = min(rows, key=lambda row: (row['training']['brier'], row['index']))
    classical = {o: [(F(c)+alpha)/(sum(row)+4*alpha) for c in row] for o, row in train.items()}
    return {'arithmetic': 'exact rational predictions/Brier; Decimal(50) natural logarithms',
            'results': {'selected_candidate': selected['index'], 'selection_metric': 'training_brier',
                        'candidate_training': rows,
                        'projector': {'predictions': selected['predictions'], 'heldout': score(selected['predictions'], heldout)},
                        'classical_contextual': {'predictions': classical, 'training': score(classical, train), 'heldout': score(classical, heldout)},
                        'complexity': {'projector_candidates_examined': len(rows), 'projector_continuous_parameters_fitted': 0,
                                       'classical_free_cell_probabilities': 6},
                        'cell_order': ['first_yes_second_yes', 'first_yes_second_no', 'first_no_second_yes', 'first_no_second_no']},
            'checks': {'probabilities_normalized': all(sum(p)==1 and all(0<=v<=1 for v in p)
                                                       for r in rows for p in r['predictions'].values()),
                       'heldout_used_for_selection': False},
            'limits': ['Two-dimensional real rational projectors; finite candidate selection, not unrestricted quantum fitting.',
                       'Train/heldout separation is caller-declared; synthetic examples measure this calculation, not human cognition.',
                       'Different parameterizations and finite candidate counts are reported separately; no universal model winner.'],
            'sources': [ORDER_SOURCE]}


def measurements(data):
    fields(data, 'density effects')
    rho = matrix(data['density'], 2)
    if not psd2(rho) or rho[0][0]+rho[1][1] != 1:
        fail('density_invalid')
    effects = data['effects']
    if type(effects) is not list or not 1 <= len(effects) <= 16:
        fail('effects_bound')
    effects = [matrix(e, 2) for e in effects]
    if not all(psd2(e) for e in effects):
        fail('effect_not_positive')
    if [[sum(e[i][j] for e in effects) for j in range(2)] for i in range(2)] != ident(2):
        fail('effects_not_normalized')
    diagonal = [[rho[0][0], F(0)], [F(0), rho[1][1]]]
    def probs(density):
        return [sum(density[i][j]*effect[j][i] for i in range(2) for j in range(2)) for effect in effects]
    before, after = probs(rho), probs(diagonal)
    return {'arithmetic': 'exact rational', 'results': {'probabilities': before, 'after_basis_dephasing': after,
            'classical_basis_mixture': after, 'dephased_density': diagonal},
            'checks': {'density_positive_trace_one': True, 'effects_positive_sum_identity': True,
                       'probabilities_normalized': sum(before)==sum(after)==1 and all(0<=v<=1 for v in before+after)},
            'limits': ['Real symmetric 2x2 density matrices and POVMs; computational-basis dephasing is explicitly chosen.',
                       'Predicted probabilities are not passed truth predicates or measured neural states.'],
            'sources': [MEASUREMENT_SOURCE]}


def circuit_matrix(gates, qubits):
    if type(gates) is not list or len(gates) > 32:
        fail('gate_bound')
    n = 2**qubits
    result, h_count = ident(n), 0
    for gate in gates:
        fields(gate, 'gate wires')
        name, wires = gate['gate'], gate['wires']
        if name not in ('H', 'X', 'Z', 'CNOT', 'SWAP') or type(wires) is not list:
            fail('gate_invalid')
        expected = 2 if name in ('CNOT', 'SWAP') else 1
        if len(wires) != expected:
            fail('wires_invalid')
        for w in wires:
            integer(w, 0, qubits-1)
        if len(set(wires)) != expected:
            fail('wires_invalid')
        g = [[F(0) for _ in range(n)] for _ in range(n)]
        for column in range(n):
            bit = (column >> wires[0]) & 1
            if name == 'H':
                g[column & ~(1 << wires[0])][column] = 1
                g[column | (1 << wires[0])][column] = -1 if bit else 1
            elif name == 'Z':
                g[column][column] = -1 if bit else 1
            else:
                row = column
                if name == 'X' or (name == 'CNOT' and bit):
                    row ^= 1 << wires[-1]
                if name == 'SWAP' and bit != ((column >> wires[1]) & 1):
                    row ^= (1 << wires[0]) | (1 << wires[1])
                g[row][column] = 1
        result = multiply(g, result)
        h_count += name == 'H'
    return result, h_count


def circuit_equal(data):
    fields(data, 'qubits left right')
    qubits = integer(data['qubits'], 1, 2)
    a, ha = circuit_matrix(data['left'], qubits)
    b, hb = circuit_matrix(data['right'], qubits)
    n = 2**qubits
    # Compare every matrix-unit channel image, so global phase is irrelevant.
    equal = all(a[i][j]*a[k][l]/(2**ha) == b[i][j]*b[k][l]/(2**hb)
                for i in range(n) for j in range(n) for k in range(n) for l in range(n))
    def norm_ok(m, count):
        return multiply(m, transpose(m)) == [[v*2**count for v in row] for row in ident(n)]
    return {'arithmetic': 'exact rational channel equality; Hadamard normalization retained as powers of two',
            'results': {'equivalent_channels': equal, 'basis_operator_checks': n**4,
                        'left_scaled_matrix': a, 'left_hadamard_count': ha,
                        'right_scaled_matrix': b, 'right_hadamard_count': hb},
            'checks': {'left_unitary': norm_ok(a, ha), 'right_unitary': norm_ok(b, hb)},
            'limits': ['At most two qubits and 32 H/X/Z/CNOT/SWAP gates per circuit; wires are zero-based, least-significant first.',
                       'Checks supplied rewrites by matrix equality; this is not a full ZX parser or a completeness theorem.'],
            'sources': [CIRCUIT_SOURCE]}


def tensor_semantics(data):
    fields(data, 'subject object relation negated expected')
    subject, obj = data['subject'], data['object']
    if type(subject) is not list or type(obj) is not list or not 1 <= len(subject) <= 8 or len(subject) != len(obj):
        fail('vector_shape')
    subject, obj = [q(x) for x in subject], [q(x) for x in obj]
    if any(x<0 for x in subject+obj) or sum(subject)!=1 or sum(obj)!=1:
        fail('noun_distribution')
    relation = matrix(data['relation'], len(subject))
    if any(not 0<=x<=1 for row in relation for x in row) or type(data['negated']) is not bool:
        fail('relation_invalid')
    expected = q(data['expected'])
    if not 0<=expected<=1:
        fail('expected_probability')
    forward = sum(subject[i]*relation[i][j]*obj[j] for i in range(len(subject)) for j in range(len(subject)))
    reverse = sum(obj[i]*relation[i][j]*subject[j] for i in range(len(subject)) for j in range(len(subject)))
    value = 1-forward if data['negated'] else forward
    # Fixed one-hot argmax baseline uses the same supplied vocabulary; no parsing claim.
    si = max(range(len(subject)), key=lambda i: subject[i])
    oi = max(range(len(obj)), key=lambda i: obj[i])
    baseline = relation[si][oi]
    baseline = 1-baseline if data['negated'] else baseline
    return {'arithmetic': 'exact rational finite tensor contraction',
            'results': {'composed_score': value, 'subject_object_reversed_score': 1-reverse if data['negated'] else reverse,
                        'one_hot_lookup_baseline': baseline, 'squared_error': (value-expected)**2,
                        'baseline_squared_error': (baseline-expected)**2, 'contractions': len(subject)**2},
            'checks': {'normalized_nouns': True, 'score_in_unit_interval': 0<=value<=1},
            'limits': ['Supplied finite noun distributions and transitive relation tensor; this does not learn lexical meanings or parse prose.',
                       'Negation is the declared scalar complement, not a complete linguistic negation model.'],
            'sources': [TENSOR_SOURCE]}


_CATALOG = [
    {'id': 'question_order_fit', 'title': 'Question order: fit and compare',
     'summary': 'Select a projector model on training counts and compare held-out scores with a classical contextual model.',
     'example': {'train': {'AB': [12,12,0,0], 'BA': [6,6,6,6]}, 'heldout': {'AB': [20,20,0,0], 'BA': [10,10,10,10]},
                 'smoothing': 1, 'candidates': [{'state':[1,0], 'A':[[1,0],[0,0]], 'B':[['1/2','1/2'],['1/2','1/2']]},
                                                {'state':[1,0], 'A':[[1,0],[0,0]], 'B':[[1,0],[0,0]]}]},
     'sources': [ORDER_SOURCE], 'limits': ['32 candidates, two dimensions, separate caller-supplied train and held-out counts.']},
    {'id': 'density_measurements', 'title': 'Density, measurement and dephasing',
     'summary': 'Validate a density matrix and POVM, then compare predictions before and after explicit dephasing.',
     'example': {'density': [['1/2','1/2'],['1/2','1/2']],
                 'effects': [[['1/2','1/2'],['1/2','1/2']],[['1/2','-1/2'],['-1/2','1/2']]]},
     'sources': [MEASUREMENT_SOURCE], 'limits': ['Real rational 2x2 matrices; at most 16 effects.']},
    {'id': 'circuit_rewrite', 'title': 'Verify a circuit rewrite',
     'summary': 'Check exact channel equality over every basis operator for two supplied finite circuits.',
     'example': {'qubits': 1, 'left': [{'gate':'H','wires':[0]},{'gate':'H','wires':[0]}], 'right': []},
     'sources': [CIRCUIT_SOURCE], 'limits': ['1–2 qubits; H, X, Z, CNOT, SWAP; 32 gates per side.']},
    {'id': 'tensor_semantics', 'title': 'Compose subject, relation and object',
     'summary': 'Contract a supplied relation tensor; compare reversal, negation and a one-hot lookup baseline.',
     'example': {'subject':[1,0], 'object':[0,1], 'relation':[[0,1],[0,0]], 'negated':False, 'expected':1},
     'sources': [TENSOR_SOURCE], 'limits': ['Vocabulary dimension 1–8; supplied numeric meanings only.']},
]
_RUNNERS = {'question_order_fit': order_fit, 'density_measurements': measurements,
            'circuit_rewrite': circuit_equal, 'tensor_semantics': tensor_semantics}


def catalog():
    return deepcopy(_CATALOG)


def run(experiment_id, data):
    if experiment_id not in _RUNNERS:
        fail('unknown_experiment')
    return wire(_RUNNERS[experiment_id](data))
