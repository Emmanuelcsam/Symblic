"""Requirement coverage: where, in a program, does each recorded requirement's predicate appear?

What it is for
    After a model compiles an intent (symblic.intent.records) into a Symblic program, the reader wants to know
    which recorded requirements the program actually checks. requirement_coverage(state, source, inputs) parses
    the program, indexes every `assert` and `ensure` by the shape of its condition (predicate_shape: syntax
    without positions, so whitespace does not matter but `120 = total` differs from `total = 120`), looks up
    the predicate of every active requirement, and returns symblic.intent.records.coverage_manifest(...): per
    requirement 'predicate_present', 'proposed_predicate_present' (the predicate came from a model, not the
    owner) or unmapped, with the exact lines and columns.

What it is not
    Presence is not execution: a matching check in a dead branch still counts as present, and every row says
    'execution': 'not_executed'. Nothing is evaluated, and 'intent_fidelity' stays 'unassessed'. Run the program
    and read symblic.intent.requirement_execution for what the checks did.

Depends on: symblic.kernel.language (parse, walk, canon) and symblic.intent.records. Used by: the original
host's interpreter API (integration/host/symblic_intent_api.py), where these functions lived before.
Status: prototype with unit tests (tests/intent/test_symblic_intent_coverage.py).
"""
from __future__ import annotations

import hashlib

from symblic.kernel import language as S
from symblic.intent import records as I


def predicate_shape(value):
    """Position-independent syntax identity, not logical/prose equivalence."""
    if isinstance(value, S.Node):
        return {'node': value.k, 'fields': {key: predicate_shape(item) for key, item in value.__dict__.items()
                                          if key not in ('k', 'line', 'col')}}
    if isinstance(value, (tuple, list)):
        return [predicate_shape(item) for item in value]
    if isinstance(value, dict):
        return {key: predicate_shape(item) for key, item in value.items()}
    return S.canon(value)


def requirement_coverage(state, source, inputs):
    """Locate exact declared predicates without executing a program or provider.

    A dead branch or uncalled routine can contain a match. Locations therefore
    establish presence only, never reachability, passing execution or entailment.
    """
    mappings, locations = {}, {}
    try:
        for node in S.walk(S.parse(source)['statements']):
            if node.k in ('assert', 'ensure'):
                key = I.digest(predicate_shape(node.cond))
                locations.setdefault(key, []).append({'kind': node.k, 'line': node.line, 'col': node.col})
    except (S.SymblicError, RecursionError):
        locations = {}  # Failed syntax has no accepted correspondence.
    for requirement in state['requirements']:
        predicate = requirement['predicate']
        if requirement['status'] != 'active' or not predicate:
            continue
        try:
            nodes = S.parse('assert ' + predicate)['statements']
            if len(nodes) != 1 or nodes[0].k != 'assert' or nodes[0].because is not None or nodes[0].on_fail != 'fail':
                continue
            found = locations.get(I.digest(predicate_shape(nodes[0].cond)), [])
        except (S.SymblicError, RecursionError):
            continue
        mappings[requirement['id']] = [{**item, 'predicate_sha256': hashlib.sha256(predicate.encode()).hexdigest()}
                                        for item in found]
    return I.coverage_manifest(state, source, inputs, mappings)
