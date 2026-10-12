"""Experiment: ideal Grover search probabilities versus classical sampling with the same oracle-query budget.

Research experiment, no result claimed. This is a classical exact calculation of ideal quantum probabilities,
not execution on a quantum computer and not evidence of an application speed-up (see LIMITS).

Experiment:
    grover-query-comparison  exact ideal success probability per Grover iteration (1-20 qubits, 0-64 iterations),
                             compared with sampling distinct items without replacement

Depends on: ``symblic.experiments.quantum`` (validation helpers). Run through ``symblic.experiments.registry``.
Source: Grover 1997 (SOURCE).
"""

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
from fractions import Fraction as F

from symblic.experiments.quantum import fields, integer, wire

VERSION = 1
DEPENDENCIES = ('symblic.experiments.quantum',)
SOURCE = 'https://arxiv.org/abs/quant-ph/9706033'
LIMITS = [
    'Ideal uniform-state Grover search with a known positive marked-item count, noiseless phase oracle and diffusion.',
    'Counts are oracle queries, not elapsed time or physical gates. Oracle synthesis, memory loading, error correction and hardware cost are unspecified.',
    '1–20 search-register qubits and 0–64 iterations. One final verification query is counted separately; oracle ancilla count is unspecified.',
    'The classical comparator samples distinct uniformly random items, stopping at its first hit; its query budget includes verification.',
    'This is a classical exact calculation of ideal quantum probabilities, not execution on a quantum computer or evidence of an application speedup.',
]


def search(data):
    fields(data, 'qubits marked iterations')
    qubits = integer(data['qubits'], 1, 20)
    size = 2**qubits
    marked = integer(data['marked'], 1, size)
    steps = integer(data['iterations'], 0, 64)
    # Each unmarked amplitude is a/sqrt(N), each marked amplitude b/sqrt(N).
    # All coefficients remain rational, so no floating-point trig is required.
    a = b = F(1)
    rows = []
    for step in range(steps+1):
        probability = F(marked, size)*b*b
        norm = F(size-marked, size)*a*a + probability
        wire([a, b, probability, norm])
        if norm != 1:
            raise ValueError('normalization_failure')
        queries = min(step+1, size)
        miss = F(1)
        for draw in range(queries):
            if draw >= size-marked:
                miss = F(0)
                break
            miss *= F(size-marked-draw, size-draw)
        rows.append({'iterations': step, 'phase_oracle_queries': step,
                     'final_verification_queries': 1, 'total_quantum_queries': step+1,
                     'ideal_success_probability': probability,
                     'classical_query_budget': queries,
                     'classical_success_probability': 1-miss,
                     'state_norm_squared': norm})
        if step < steps:
            mean = ((size-marked)*a-marked*b)/size
            a, b = 2*mean-a, 2*mean+b
    best = max(rows, key=lambda row: row['ideal_success_probability'])
    return {'arithmetic': 'exact rational amplitudes scaled by 1/sqrt(N); exact query counts',
            'results': {'search_space_size': size, 'marked_items': marked,
                        'search_register_qubits': qubits, 'oracle_ancilla_qubits': None,
                        'selected_iterations': steps, 'selected': rows[-1],
                        'trajectory': rows, 'best_within_supplied_iteration_range': best,
                        'classical_expected_queries_until_first_hit': F(size+1, marked+1),
                        'classical_worst_case_queries_until_first_hit': size-marked+1,
                        'physical_gate_count': None, 'runtime_seconds': None},
            'checks': {'every_state_normalized': True, 'known_marked_count_positive': True,
                       'physical_quantum_execution': False},
            'limits': list(LIMITS), 'sources': [SOURCE]}


def catalog():
    return [{'id': 'grover-query-comparison', 'title': 'Grover search and classical query costs',
             'summary': 'Calculate exact ideal search probabilities and compare the same oracle-query budget with sampling without replacement.',
             'example': {'qubits': 4, 'marked': 1, 'iterations': 3},
             'limits': list(LIMITS), 'sources': [SOURCE]}]


def run(experiment_id, data):
    if experiment_id != 'grover-query-comparison':
        raise ValueError('unknown_experiment')
    return wire(search(data))
