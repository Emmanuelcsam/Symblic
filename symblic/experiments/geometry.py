"""Experiments: symplectic versus explicit integration, and Fisher versus ordinary gradient updates.

Research experiment, no result claimed.

Experiments:
    hamiltonian_integrators  evolve one supplied quadratic Hamiltonian with symplectic and explicit Euler steps
                             and check the exact symplectic and modified-energy identities
    fisher_gradient          update an explicit categorical distribution from training counts with the Fisher
                             (natural) gradient and the ordinary gradient, then score a frozen held-out split

Exact rationals with bounded bit sizes and work counters; no model or host effects.

Depends on: the standard library only. Run through ``symblic.experiments.registry``.
Sources: HAMILTONIAN_SOURCE (Hairer, geometric integration) and FISHER_SOURCE (Amari 1998).
"""
# Bind the executing module to its exact first-party source before dependencies.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
from copy import deepcopy
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction as F
import re

VERSION = 1
MAX_BITS = 512
MAX_WORK = 50_000
_NUMBER = re.compile(r'-?[0-9]{1,40}(?:/[1-9][0-9]{0,39})?\Z')
HAMILTONIAN_SOURCE = 'https://www.unige.ch/~hairer/poly_geoint/intro.pdf'
FISHER_SOURCE = 'https://doi.org/10.1162/089976698300017746'


def fail(code):
    raise ValueError(code)


def fields(data, names):
    if type(data) is not dict or set(data) != set(names.split()):
        fail('schema')


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        fail('integer_bound')
    return value


def number(value):
    if type(value) is int and abs(value) <= 2**53-1:
        return F(value)
    if type(value) is not str or len(value) > 81 or not _NUMBER.fullmatch(value):
        fail('rational')
    result = F(value)
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 128:
        fail('input_bits')
    return result


class Arithmetic:
    def __init__(self):
        self.work = 0

    def checked(self, value):
        self.work += 1
        if self.work > MAX_WORK:
            fail('work_bound')
        if max(value.numerator.bit_length(), value.denominator.bit_length()) > MAX_BITS:
            fail('arithmetic_bound')
        return value

    def add(self, a, b):
        return self.checked(a+b)

    def sub(self, a, b):
        return self.checked(a-b)

    def mul(self, a, b):
        return self.checked(a*b)

    def div(self, a, b):
        if not b:
            fail('zero_divisor')
        return self.checked(a/b)

    def dot(self, a, b):
        total = F(0)
        for x, y in zip(a, b):
            total = self.add(total, self.mul(x, y))
        return total

    def matmul(self, a, b):
        return [[self.dot(row, col) for col in zip(*b)] for row in a]

    def matvec(self, a, b):
        return [self.dot(row, b) for row in a]

    def congruence(self, a, s):
        return self.matmul(transpose(a), self.matmul(s, a))

    def energy(self, s, z):
        return self.div(self.dot(z, self.matvec(s, z)), F(2))

    def pivots(self, a):
        # Exact symmetric elimination; positive pivots certify SPD (no pivoting).
        work = [r[:] for r in a]
        pivots = []
        for i in range(len(work)):
            pivot = work[i][i]
            if pivot <= 0:
                return pivots, False
            pivots.append(pivot)
            for j in range(i+1, len(work)):
                for k in range(i+1, len(work)):
                    work[j][k] = self.sub(work[j][k], self.div(self.mul(work[j][i], work[i][k]), pivot))
        return pivots, True

    def solve(self, a, b):
        work = [row[:] + [value] for row, value in zip(a, b)]
        n = len(b)
        for i in range(n):
            if not work[i][i]:
                fail('singular_metric')
            pivot = work[i][i]
            for k in range(i, n+1):
                work[i][k] = self.div(work[i][k], pivot)
            for j in range(n):
                if j == i:
                    continue
                factor = work[j][i]
                for k in range(i, n+1):
                    work[j][k] = self.sub(work[j][k], self.mul(factor, work[i][k]))
        return [row[-1] for row in work]


def vector(value, n):
    if type(value) is not list or len(value) != n:
        fail('vector_shape')
    return [number(x) for x in value]


def matrix(value, n):
    if type(value) is not list or len(value) != n:
        fail('matrix_shape')
    return [vector(row, n) for row in value]


def transpose(a):
    return [list(row) for row in zip(*a)]


def wire(value):
    if isinstance(value, F):
        return str(value)
    if type(value) is dict:
        return {key: wire(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [wire(item) for item in value]
    return value


def hamiltonian(data, calc):
    fields(data, 'K inverse_mass q0 p0 step steps units')
    if data['units'] != 'dimensionless':
        fail('units')
    if type(data['q0']) is not list or not 1 <= len(data['q0']) <= 4:
        fail('dimension_bound')
    n = len(data['q0'])
    k = matrix(data['K'], n)
    mass = vector(data['inverse_mass'], n)
    q0, p0 = vector(data['q0'], n), vector(data['p0'], n)
    h = number(data['step'])
    steps = integer(data['steps'], 1, 32)
    if k != transpose(k):
        fail('not_symmetric')
    kpivots, positive = calc.pivots(k)
    if not positive or any(x <= 0 for x in mass):
        fail('not_positive_definite')
    if not 0 < h <= 4:
        fail('step_bound')
    size = 2*n
    s = [[F(0) for _ in range(size)] for _ in range(size)]
    j = [[F(0) for _ in range(size)] for _ in range(size)]
    explicit = [[F(i == l) for l in range(size)] for i in range(size)]
    symplectic = deepcopy(explicit)
    for i in range(n):
        s[n+i][n+i] = mass[i]
        j[i][n+i], j[n+i][i] = F(1), F(-1)
        explicit[i][n+i] = symplectic[i][n+i] = calc.mul(h, mass[i])
        for l in range(n):
            s[i][l] = k[i][l]
            explicit[n+i][l] = symplectic[n+i][l] = -calc.mul(h, k[i][l])
            symplectic[i][l] = calc.sub(F(i == l), calc.mul(calc.mul(h, h), calc.mul(mass[i], k[i][l])))
    modified = deepcopy(s)
    for i in range(n):
        for l in range(n):
            cross = -calc.div(calc.mul(h, calc.mul(k[i][l], mass[l])), F(2))
            modified[i][n+l] = modified[n+l][i] = cross
    _, modified_positive = calc.pivots(modified)
    initial_energy = calc.energy(s, q0+p0)
    initial_modified = calc.energy(modified, q0+p0)
    results = {}
    for name, update in [('explicit_euler', explicit), ('symplectic_euler', symplectic)]:
        q, p = q0[:], p0[:]
        rows = [{'step': 0, 'q': q[:], 'p': p[:], 'energy': initial_energy,
                 'energy_error': F(0), 'modified_energy': initial_modified}]
        recurrence_ok = True
        for index in range(1, steps+1):
            next_p = [calc.sub(v, calc.mul(h, force)) for v, force in zip(p, calc.matvec(k, q))]
            momentum = p if name == 'explicit_euler' else next_p
            next_q = [calc.add(v, calc.mul(h, calc.mul(m, pv))) for v, m, pv in zip(q, mass, momentum)]
            recurrence_ok &= next_q+next_p == calc.matvec(update, q+p)
            q, p = next_q, next_p
            energy = calc.energy(s, q+p)
            rows.append({'step': index, 'q': q[:], 'p': p[:], 'energy': energy,
                         'energy_error': calc.sub(energy, initial_energy),
                         'modified_energy': calc.energy(modified, q+p)})
        results[name] = {'trajectory': rows, 'update_matrix': update,
                         'max_absolute_energy_error': max(abs(r['energy_error']) for r in rows),
                         'preserves_symplectic_form': calc.congruence(update, j) == j,
                         'preserves_original_energy_for_all_states': calc.congruence(update, s) == s,
                         'recurrence_matches_matrix': recurrence_ok}
    results.update({'initial_energy': initial_energy, 'stiffness_pivots': kpivots,
                    'modified_quadratic_matrix': modified, 'modified_quadratic_positive_definite': modified_positive,
                    'symplectic_form': j, 'matched_steps': steps, 'step': h, 'units': 'dimensionless'})
    return {'arithmetic': 'exact rational; state order [q,p]; fixed-step kick-then-drift symplectic Euler',
            'results': results,
            'checks': {'stiffness_positive_definite': positive,
                       'symplectic_matrix_identity': calc.congruence(symplectic, j) == j,
                       'modified_quadratic_identity': calc.congruence(symplectic, modified) == modified,
                       'modified_energy_constant_on_trajectory': all(r['modified_energy'] == initial_modified for r in results['symplectic_euler']['trajectory']),
                       'both_recurrences_match_matrices': all(results[x]['recurrence_matches_matrix'] for x in ('explicit_euler', 'symplectic_euler'))},
            'limits': ['Supplied dimensionless separable positive quadratic only, dimension 1–4 and 1–32 matched steps.',
                       'Original energy generally changes; the reported modified quadratic is a separate exact invariant of this finite update.',
                       'An indefinite modified invariant does not bound trajectories. No unconditional stability, Noether law, physical fit or language-state claim.'],
            'sources': [HAMILTONIAN_SOURCE]}


def counts(value, k):
    if type(value) is not list or len(value) != k:
        fail('counts_shape')
    row = [integer(x, 0, 1_000_000) for x in value]
    if not sum(row):
        fail('empty_counts')
    return row


def score(p, observed, calc):
    total = sum(observed)
    frequencies = [F(x, total) for x in observed]
    brier = calc.add(calc.dot(p, p), calc.sub(F(1), calc.mul(F(2), calc.dot(frequencies, p))))
    error = calc.dot([calc.sub(x, y) for x, y in zip(p, frequencies)],
                     [calc.sub(x, y) for x, y in zip(p, frequencies)])
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        loss = -sum(Decimal(c)*(Decimal(v.numerator)/Decimal(v.denominator)).ln()
                    for v, c in zip(p, observed) if c)/Decimal(total)
    return {'mean_negative_log_likelihood_nats_approx': str(loss), 'brier': brier,
            'squared_frequency_error': error, 'observations': total}


def fisher(data, calc):
    fields(data, 'probabilities train heldout step steps regularization')
    supplied = data['probabilities']
    if type(supplied) is not list or not 2 <= len(supplied) <= 6:
        fail('category_bound')
    k = len(supplied)
    initial = vector(supplied, k)
    if any(p <= 0 or p >= 1 for p in initial) or calc.dot(initial, [F(1)]*k) != 1:
        fail('simplex_interior')
    train, heldout = counts(data['train'], k), counts(data['heldout'], k)
    h, ridge = number(data['step']), number(data['regularization'])
    if not 0 < h <= 1 or not 0 <= ridge <= 100:
        fail('step_or_regularization_bound')
    steps = integer(data['steps'], 1, 16)
    target = [F(c, sum(train)) for c in train]
    results = {}
    for name in ('ordinary_gradient', 'natural_gradient'):
        p, rows = initial[:], []
        accepted = 0
        all_residuals_zero = True
        for index in range(1, steps+1):
            gradient = [calc.sub(calc.div(target[-1], p[-1]), calc.div(target[i], p[i])) for i in range(k-1)]
            metric = [[calc.add(calc.div(F(1), p[-1]), calc.div(F(1), p[i]) if i == j else F(0)) for j in range(k-1)] for i in range(k-1)]
            regularized = [[calc.add(v, ridge if i == j else F(0)) for j, v in enumerate(row)] for i, row in enumerate(metric)]
            pivots, full_rank = calc.pivots(metric)
            if not full_rank:
                fail('singular_metric')
            if name == 'natural_gradient':
                direction = calc.solve(regularized, gradient)
                residual = [calc.sub(x, y) for x, y in zip(calc.matvec(regularized, direction), gradient)]
                all_residuals_zero &= not any(residual)
            else:
                direction, residual = gradient, None
            candidate = [calc.sub(p[i], calc.mul(h, direction[i])) for i in range(k-1)]
            candidate.append(calc.sub(F(1), calc.dot(candidate, [F(1)]*(k-1))))
            valid = all(0 < v < 1 for v in candidate)
            row = {'step': index, 'before': p[:], 'gradient': gradient, 'fisher': metric,
                   'fisher_rank': k-1, 'fisher_positive_pivots': pivots,
                   'regularization': ridge if name == 'natural_gradient' else F(0),
                   'direction': direction, 'linear_solve_residual': residual,
                   'candidate': candidate, 'status': 'accepted' if valid else 'boundary_rejected'}
            if valid:
                p, accepted = candidate, accepted+1
            row['after'] = p[:]
            rows.append(row)
        # This evaluation is after the fixed update schedule and cannot select updates.
        results[name] = {'trajectory': rows, 'final_probabilities': p, 'attempted_steps': steps,
                         'accepted_steps': accepted, 'rejected_steps': steps-accepted,
                         'training': score(p, train, calc), 'heldout': score(p, heldout, calc),
                         'linear_solve_residuals_zero': all_residuals_zero if name == 'natural_gradient' else None}
    results.update({'initial_probabilities': initial, 'initial_training': score(initial, train, calc),
                    'initial_heldout': score(initial, heldout, calc), 'step': h, 'matched_attempted_steps': steps,
                    'coordinate_chart': 'theta=p[0:k-1], p[k-1]=1-sum(theta)',
                    'distribution': 'Bernoulli (listed category order)' if k == 2 else 'categorical',
                    'training_frequencies': target, 'parameter_count': k-1})
    return {'arithmetic': 'exact rational gradients, Fisher matrices, directions and Brier; Decimal precision 50 natural logarithms are approximate',
            'results': results,
            'checks': {'heldout_used_for_updates': False, 'same_initial_state_step_and_attempt_budget': True,
                       'natural_linear_solve_residuals_zero': results['natural_gradient']['linear_solve_residuals_zero'],
                       'final_probabilities_in_simplex': all(sum(results[name]['final_probabilities']) == 1 and all(0 < x < 1 for x in results[name]['final_probabilities']) for name in ('ordinary_gradient', 'natural_gradient'))},
            'limits': ['Explicit interior categorical distributions with 2–6 states; Bernoulli is the two-state case. No hidden-state measurement.',
                       'Same probability-coordinate chart, step size and attempted step count; positive ridge changes the exact natural direction into a damped direction.',
                       'Boundary-crossing proposals are rejected without clipping or line search, recorded, and consume one matched attempt.',
                       'Train/heldout separation is caller-declared. Heldout does not select parameters, step sizes, stopping, or a winner.',
                       'Metric rank is checked in k−1 independent coordinates; redundant logits and boundary-singular charts are unsupported. No universal convergence advantage.'],
            'sources': [FISHER_SOURCE]}


_CATALOG = [
    {'id': 'hamiltonian_integrators', 'title': 'Compare symplectic and explicit Euler',
     'summary': 'Evolve the same supplied quadratic and check exact symplectic and modified-energy identities.',
     'example': {'K': [[1]], 'inverse_mass': [1], 'q0': [1], 'p0': [0], 'step': '1/4', 'steps': 12, 'units': 'dimensionless'},
     'sources': [HAMILTONIAN_SOURCE], 'limits': ['Dimension 1–4; fixed 1–32 steps; supplied dimensionless separable positive quadratic.']},
    {'id': 'fisher_gradient', 'title': 'Compare Fisher and ordinary gradient updates',
     'summary': 'Use training counts to update an explicit distribution, then score a frozen held-out split.',
     'example': {'probabilities': ['1/2','1/2'], 'train': [3,1], 'heldout': [2,2], 'step': '1/8', 'steps': 2, 'regularization': 0},
     'sources': [FISHER_SOURCE], 'limits': ['2–6 categories; 1–16 fixed attempted steps; interior probabilities; Decimal50 log scores.']},
]
_RUNNERS = {'hamiltonian_integrators': hamiltonian, 'fisher_gradient': fisher}


def catalog():
    return deepcopy(_CATALOG)


def run(experiment_id, data):
    if type(experiment_id) is not str or experiment_id not in _RUNNERS:
        fail('unknown_experiment')
    calc = Arithmetic()
    result = _RUNNERS[experiment_id](data, calc)
    result['work'] = {'rational_operations': calc.work, 'operation_limit': MAX_WORK,
                      'normalized_rational_bit_limit': MAX_BITS, 'input_rational_bit_limit': 128,
                      'transient_pairwise_integer_bit_bound': 2*MAX_BITS+1}
    return wire(result)
