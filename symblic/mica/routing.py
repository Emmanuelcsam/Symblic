"""MICA model routing: which local model on which node to ask, ranked from exact identities and past outcomes.

What it is for
    Normalizes the explicit inventory (engine, model, node, optional weight digest, readiness, cost estimates) and
    ranks eligible routes for a unit from retained observations of the same model/node/digest/task class, using a
    Wilson lower bound so a few lucky successes do not dominate.

Depends on: contracts.py. Used by search.py, strategy.py, calibration.py, cli.py and forge.py. Pure.

Details
    Pure local-model ranking from exact identities and retained observations.

    No launch, training or auto-adoption. Wilson scores are a conservative ranking
    heuristic conditional on Bernoulli independence; correlated task observations do
    not establish that assumption. Missing counters and unknown model digests remain
    unknown. Inventory eligibility does not guarantee that a provider will accept a call.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from collections import Counter, defaultdict
import copy
import math
import re

from symblic.mica.contracts import ContractError, digest

VERSION = 1
MAX_INVENTORY = 256
MAX_OBSERVATIONS = 10000
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_NODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
COUNTERS = ('calls', 'latency_ms', 'input_tokens', 'output_tokens')
STATUSES = ('success', 'failed', 'refused', 'timeout', 'unknown')


def _fail(code, message):
    raise ContractError(code, message)


def _text(value, field, limit=200):
    if type(value) is not str or not value.strip() or len(value) > limit or '\x00' in value:
        _fail(field, 'Expected bounded nonempty ' + field + '.')
    return value


def _number(value, field):
    if value is not None and (type(value) is not int or not 0 <= value <= 10**15):
        _fail(field, 'Counters and estimates must be nonnegative exact integers or null.')
    return value


def _identity(row):
    if row.get('engine') != 'ollama':
        _fail('engine', 'Only the registered Ollama local-model lane is supported.')
    model = _text(row.get('model'), 'model')
    node = row.get('node')
    if type(node) is not str or not _NODE.fullmatch(node):
        _fail('node', 'Exact physical node identity is required.')
    sha = row.get('digest')
    if sha is not None and (type(sha) is not str or not _SHA.fullmatch(sha)):
        _fail('digest', 'Model digest must be a lowercase SHA-256 or null.')
    return ('ollama', model, node, sha)


def _identity_dict(key):
    return dict(zip(('engine', 'model', 'node', 'digest'), key))


def normalize_inventory(rows):
    """Validate explicit catalogue facts; omitted readiness stays unavailable."""
    if type(rows) is not list or len(rows) > MAX_INVENTORY:
        _fail('inventory', 'Inventory exceeds its bounded row count.')
    result = []; seen = set()
    required = {'engine', 'model', 'node'}
    optional = {'digest', 'ready', 'available', 'context_chars', 'estimated_cost_units', 'parameters',
                'estimated_latency_ms', 'verifier_ms', 'scheduler_ms',
                'verifier_cost_units', 'scheduler_cost_units'}
    for row in rows:
        if type(row) is not dict or not required <= set(row) or set(row) - required - optional:
            _fail('inventory_fields', 'Missing or unknown inventory fields.')
        key = _identity(row)
        if key in seen:
            _fail('inventory_identity', 'Duplicate exact inventory identity.')
        seen.add(key)
        normalized = {**_identity_dict(key), 'ready': row.get('ready', False),
                      'available': row.get('available', False)}
        for field in ('ready', 'available'):
            if type(normalized[field]) is not bool:
                _fail('inventory', 'Readiness and capacity flags must be explicit booleans.')
        for field in ('context_chars', 'estimated_cost_units', 'parameters', 'estimated_latency_ms',
                      'verifier_ms', 'scheduler_ms', 'verifier_cost_units', 'scheduler_cost_units'):
            normalized[field] = _number(row.get(field), field)
        result.append(normalized)
    digest(result)
    return sorted(result, key=lambda r: (r['engine'], r['model'], r['node'], r['digest'] or ''))


def _observations(rows):
    if type(rows) is not list or len(rows) > MAX_OBSERVATIONS:
        _fail('observations', 'Observations exceed their bounded row count.')
    required = {'observation_id', 'engine', 'model', 'node', 'digest', 'task_class', 'status'}
    optional = {'contract_hash', 'checker_hash', 'calls', 'latency_ms', 'input_tokens', 'output_tokens', 'cached'}
    seen = {}; result = []
    for original in rows:
        if type(original) is not dict or not required <= set(original) or set(original) - required - optional:
            _fail('observation_fields', 'Missing or unknown observation fields.')
        row = copy.deepcopy(original)
        _identity(row); _text(row['observation_id'], 'observation_id'); _text(row['task_class'], 'task_class', 120)
        if row['status'] not in STATUSES:
            _fail('status', 'Unknown observation status.')
        row['cached'] = row.get('cached', False)
        if type(row['cached']) is not bool:
            _fail('cached', 'Cached must be an explicit boolean.')
        for name in ('contract_hash', 'checker_hash'):
            value = row.get(name)
            if value is not None and (type(value) is not str or not _SHA.fullmatch(value)):
                _fail(name, 'Observation pins must be SHA-256 or null.')
            row[name] = value
        for field in COUNTERS:
            row[field] = _number(row.get(field), field)
        fingerprint = digest(row)
        previous = seen.get(row['observation_id'])
        if previous is not None:
            if previous != fingerprint:
                _fail('observation_conflict', 'One observation identity has conflicting contents.')
            continue
        seen[row['observation_id']] = fingerprint
        result.append(row)
    return result


def _wilson_lower(successes, total, z=1.96):
    # Same standard Wilson formula as symblic.bench.bench.wilson, without importing
    # its benchmark/provider orchestration dependencies into this pure helper.
    if not total:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, (centre - radius) / denominator)


def _summary(rows):
    fresh = [r for r in rows if not r['cached']]
    counts = Counter(r['status'] for r in fresh)
    counters = {}
    for field in COUNTERS:
        known = [r[field] for r in fresh if r[field] is not None]
        counters[field] = {'known_sum': sum(known), 'known_observations': len(known),
                           'unknown_observations': len(fresh) - len(known),
                           'complete_sum': sum(known) if len(known) == len(fresh) and fresh else None}
    n = len(fresh)
    return {'observations': n, 'cached_observations': len(rows) - n,
            'successes': counts['success'], 'statuses': {s: counts[s] for s in STATUSES},
            'success_rate': counts['success'] / n if n else None,
            'wilson_lower_bound': _wilson_lower(counts['success'], n), 'z': 1.96,
            'bound_scope': 'ranking_heuristic_conditional_on_independent_Bernoulli_trials',
            'independence': 'not_established', 'unknown_outcomes_charged_as_success': False,
            'measured_counters': counters,
            'contract_hashes': sorted({r['contract_hash'] for r in fresh if r['contract_hash']}),
            'checker_hashes': sorted({r['checker_hash'] for r in fresh if r['checker_hash']}),
            'missing_contract_pins': sum(r['contract_hash'] is None for r in fresh),
            'missing_checker_pins': sum(r['checker_hash'] is None for r in fresh)}


def summarize(observations):
    """Deduplicate exact observations and retain per-identity/task-class totals."""
    rows = _observations(observations)
    groups = defaultdict(list)
    for row in rows:
        groups[(*_identity(row), row['task_class'])].append(row)
    results = []
    for key in sorted(groups, key=lambda k: tuple(x or '' for x in k)):
        results.append({**_identity_dict(key[:4]), 'task_class': key[4], **_summary(groups[key])})
    return {'version': VERSION, 'groups': results, 'unique_observations': len(rows),
            'observations_sha256': digest(rows), 'assurance': 'host_recorded_observations_not_generalization'}


def _costs(row, statistics, probability):
    measurements = statistics['measured_counters']['latency_ms'] if statistics else None
    complete = bool(measurements and measurements['complete_sum'] is not None and statistics['observations'])
    latency = (measurements['complete_sum'] / statistics['observations'] if complete
               else row['estimated_latency_ms'])
    result = {}
    for unit, base, overheads, source in (
            ('milliseconds', latency, (row['verifier_ms'], row['scheduler_ms']),
             'complete_observed_mean_latency' if complete else 'inventory_estimate'),
            ('cost_units', row['estimated_cost_units'], (row['verifier_cost_units'], row['scheduler_cost_units']),
             'inventory_estimate')):
        known = None if base is None else base + sum(x for x in overheads if x is not None)
        expected_known = known / probability if known is not None and probability and probability > 0 else None
        all_known = base is not None and all(x is not None for x in overheads)
        result[unit] = {'base': base, 'verifier': overheads[0], 'scheduler': overheads[1],
                        'source': source, 'success_probability_bound': probability,
                        'expected_known_component_cost': expected_known,
                        'expected_total_cost': expected_known if all_known else None,
                        'complete_components': all_known,
                        'scope': 'cost_ranking_estimate_not_a_measured_total_or_guarantee'}
    return result


def rank_models(contract, inventory, observations):
    """Return eligible candidates, ranked by measured class support then cost.

Cold-start observations never borrow another model/node/digest's successes.
Unknown digests may be dispatched only by the host's existing admission path;
they cannot receive an evidence-derived ranking advantage here. Context facts
remain explicit: an unknown capacity is eligible with an uncertainty marker.
"""
    if type(contract) is not dict:
        _fail('contract', 'A normalized contract is required.')
    from symblic.mica.contracts import _eligibility
    eligibility = _eligibility(contract.get('model_eligibility', {}))
    budget = contract.get('resource_budget', {})
    if type(budget) is not dict:
        _fail('budget', 'Contract resource budget must be an object.')
    context = budget.get('context_chars', 0)
    if type(context) is not int or context < 0:
        _fail('budget', 'Context allowance must be a nonnegative integer.')
    models = normalize_inventory(inventory)
    summaries = summarize(observations)
    by_key = {(*_identity(r), r['task_class']): r for r in summaries['groups']}
    ranked = []
    for row in models:
        if not row['ready'] or not row['available']:
            continue
        if any(eligibility[field] and row[singular] not in eligibility[field]
               for field, singular in (('models', 'model'), ('nodes', 'node'), ('digests', 'digest'))):
            continue
        if row['context_chars'] is not None and row['context_chars'] < context:
            continue
        stats = by_key.get((*_identity(row), eligibility['task_class'])) if row['digest'] else None
        count = stats['observations'] if stats else 0
        if count < eligibility['min_observations']:
            continue
        lower = stats['wilson_lower_bound'] if stats else None
        ranked.append({**row, 'task_class': eligibility['task_class'], 'statistics': copy.deepcopy(stats),
                       'cold_start': not count, 'ranking_lower_bound': lower,
                       'expected_costs': _costs(row, stats, lower),
                       'identity_status': 'digest_supplied' if row['digest'] else 'digest_unavailable',
                       'context_capacity_status': 'known' if row['context_chars'] is not None else 'unknown',
                       'cost_estimate': {'units': row['estimated_cost_units'], 'source': 'inventory_estimate',
                                         'measured': False},
                       'dispatch_admission': 'required_through_existing_registered_provider',
                       'evidence_scope': 'same_exact_identity_and_declared_task_class'})
    # Pick a shared cost dimension before comparing values. Never compare
    # milliseconds for one model with arbitrary caller units for another.
    shared_unit = next((unit for unit in ('milliseconds', 'cost_units')
                        if ranked and all(r['expected_costs'][unit]['base'] is not None for r in ranked)), None)
    for row in ranked:
        row['ranking_cost_unit'] = shared_unit
        row['ranking_expected_cost'] = (row['expected_costs'][shared_unit]['expected_known_component_cost']
                                        if shared_unit else None)
        row['ranking_cost_scope'] = ('expected_known_components_missing_overhead_remains_unknown'
                                     if shared_unit else 'no_shared_cost_dimension')
    def order(row):
        cost = row['ranking_expected_cost']
        return (cost is None, cost if cost is not None else math.inf,
                -(row['ranking_lower_bound'] or 0.0), row['cold_start'],
                row['estimated_cost_units'] if row['estimated_cost_units'] is not None else math.inf,
                row['model'], row['node'], row['digest'] or '')
    ranked.sort(key=order)
    return ranked
