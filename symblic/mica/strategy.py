"""MICA alternatives: a bounded AND/OR frontier over candidate graphs and worker assignments.

What it is for
    In the search and mica modes, keeps several admitted graphs (OR) whose contracts must all pass (AND), each
    paired with eligible routes, scores them with explicit partial costs, and records every choice so a resumed run
    replays the decision instead of re-ranking it.

Depends on: contracts.py, routing.py. Used by search.py. Pure.

Details
    Bounded AND/OR choice policy; no provider, filesystem, checker or executor.

    OR alternatives pair an admitted graph with eligible fallback-worker choices.
    Every graph requires all its contract children (AND), with the native executor's
    checked reuse/finite-construction/model sequence unchanged. Scores are partial
    conditional estimates, never measured costs or a success/optimality guarantee.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import heapq
import json

from symblic.mica import contracts as C
from symblic.mica import routing as R

VERSION = 1
MAX_FRONTIER = 32
MAX_ROUTES_PER_UNIT = 8
SCOPE = 'bounded_conditional_strategy_heuristic_not_measured_cost_or_optimal_search'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def route(row):
    if row is None:
        return None
    return {'id': row.get('id', 'worker'), 'provider': 'ollama', 'model': row['model'],
            'node': row['node'], 'local': True, 'digest': row.get('digest')}


def _inventory(inventory, observations):
    rows = R.normalize_inventory(inventory)
    for row in rows:
        if row['digest'] is None:
            fresh = [v for v in observations if v['model'] == row['model'] and v['node'] == row['node']
                     and v['digest'] is not None and not v['cached']
                     and not v['observation_id'].startswith('cal/')]
            if fresh:
                row['digest'] = fresh[-1]['digest']
    return rows


def _eligible(contract, inventory, observations, mode):
    rows = R.rank_models(contract, inventory, observations if mode == 'mica' else [])
    if mode == 'search':
        order = {(r['model'], r['node'], r['digest']): i for i, r in enumerate(inventory)}
        rows.sort(key=lambda r: order[(r['model'], r['node'], r['digest'])])
    return rows


def _estimate(rows, allowances):
    dimensions = {}
    for dimension in ('milliseconds', 'cost_units'):
        entries = [r['expected_costs'][dimension] if r is not None else None for r in rows]
        bases = [e['base'] if e is not None else None for e in entries]
        overheads = [e[k] if e is not None else None for e in entries for k in ('verifier', 'scheduler')]
        expected = [e['expected_known_component_cost'] if e is not None else None for e in entries]
        dimensions[dimension] = {
            'known_component_sum': sum(x for x in bases + overheads if x is not None),
            'unknown_components': sum(x is None for x in bases + overheads),
            'all_bases_known': bool(entries) and all(x is not None for x in bases),
            'complete_component_sum': (sum(bases + overheads) if entries and
                                        all(x is not None for x in bases + overheads) else None),
            'expected_known_component_sum': (sum(expected) if entries and all(x is not None for x in expected) else None),
            'component_sources': [e['source'] if e is not None else 'unavailable' for e in entries],
        }
    return {'dimensions': dimensions, 'fallback_call_allowance': sum(allowances),
            'per_child_success_bounds': [r['ranking_lower_bound'] if r is not None else None for r in rows],
            'success_bound_scope': 'router_heuristic_conditional_on_independent_Bernoulli_trials',
            'independence': 'not_established', 'joint_success_probability': None, 'measured': False, 'scope': SCOPE,
            'omitted_work': ['cache_recheck', 'finite_construction', 'native_repairs',
                             'final_assembly_and_checks', 'queue_wait', 'future_expansion_children'],
            'interpretation': 'one conditional fallback attempt per AND child; allowance is a ceiling, not a forecast'}


def _candidate(kind, plan, depth, rows, *, trigger=None, parent=None, generation=0):
    build = kind == 'build'
    contracts = {c['contract_id']: c for c in plan['contracts']} if build else {}
    ids = plan['order'] if build else []
    routes = {ident: route(row) for ident, row in zip(ids, rows)} if build else {}
    allowances = [min(contracts[i]['resource_budget']['max_calls'],
                      contracts[i]['failure_policy']['retries'] + 1) for i in ids] if build else [1]
    authority = {'kind': kind, 'plan_sha256': plan['content_hash'] if build else None,
                 'parent_plan_sha256': parent, 'depth': depth, 'routes': routes,
                 'planner': None if build else route(rows[0]), 'trigger': trigger,
                 'generation': generation}
    return {**authority, 'id': digest(authority), 'and_contracts': ids,
            'score': _estimate(rows, allowances)}


def _variants(plan, depth, options, limit):
    """A bounded Cartesian neighborhood, not enumeration of the full product.

    Start with each independently ranked first route. Expand index-neighbors in
    stable sum-of-indices order. This restricts generation before cost scoring;
    omitted combinations are explicitly reported and no completeness is claimed.
    """
    widths = [len(options[i]) for i in plan['order']]
    first = tuple(0 for _ in widths)
    heap, seen, made = [(0, first)], {first}, 0
    while heap and made < limit:
        _, position = heapq.heappop(heap)
        rows = [options[ident][k] for ident, k in zip(plan['order'], position)]
        yield _candidate('build', plan, depth, rows)
        made += 1
        for i, width in enumerate(widths):
            if position[i] + 1 < width:
                following = position[:i] + (position[i] + 1,) + position[i + 1:]
                if following not in seen:
                    seen.add(following)
                    heapq.heappush(heap, (sum(following), following))


def decide(request, plans, history, inventory, observations, mode, index, *, build_only=False):
    """Return a deterministic, bounded decision using only retained host facts.

    `plans` are already admitted by the caller and are revalidated here. History
    contains immutable prior choices and outcomes. An alternative owns one slot
    across proposal/admission/build. At most one expansion is allowed per slot;
    its admitted graph receives a second, build-only worker-choice receipt.
    """
    request = C.normalize_request(request)
    if mode not in ('mica', 'search') or type(index) is not int or not 0 <= index < request['budget']['max_candidates']:
        raise ValueError('Strategy mode or original candidate bound is invalid.')
    if len(history) != index or len(plans) > request['budget']['max_candidates']:
        raise ValueError('Strategy history or graph count exceeds its original bound.')
    if any(h['result']['status'] in ('unknown', 'stopped', 'blocked', 'exhausted', 'done') for h in history):
        raise ValueError('A terminal or unresolved branch cannot authorize another strategy.')
    R.summarize(observations)
    inventory = _inventory(inventory, observations)
    cap = min(MAX_FRONTIER, request['budget']['max_candidates'])
    tried = {c['id'] for h in history for c in (h['choice'], h.get('build_choice')) if c is not None}
    pending, rejected, pruned, iterators = [], [], [], []
    by_sha = {}
    for record in plans:
        plan = C.validate_plan(request, record['plan'])
        depth = record['depth']
        if type(depth) is not int or not 0 <= depth <= request['budget']['max_depth']:
            raise ValueError('Strategy graph depth exceeds the original bound.')
        sha = plan['content_hash']
        if sha in by_sha:
            raise ValueError('Duplicate strategy graph.')
        by_sha[sha] = plan
        outcomes = [h for h in history if (h.get('build_choice') or h['choice'])['kind'] == 'build'
                    and (h.get('build_choice') or h['choice'])['plan_sha256'] == sha]
        permitted = not outcomes or outcomes[-1]['result'].get('failure_policy') in ('escalate', 'refine_or_escalate')
        if not permitted:
            rejected.append({'plan_sha256': sha, 'reason': 'failure_policy_does_not_allow_worker_escalation'})
            continue
        options, unavailable_escalation = {}, False
        for contract in plan['contracts']:
            eligible = _eligible(contract, inventory, observations, mode)
            if outcomes:
                latest = outcomes[-1]
                applied = latest.get('build_choice') or latest['choice']
                ident = contract['contract_id']
                if ident != latest['result'].get('contract'):
                    # Independent successes keep their assignment; the executor
                    # still decides exact dependency-key reuse and rechecks it.
                    eligible = [r for r in eligible if route(r) == applied['routes'].get(ident)]
                else:
                    failed_routes = [
                        (h.get('build_choice') or h['choice'])['routes'].get(ident)
                        for h in outcomes if h['result'].get('contract') == ident]
                    eligible = [r for r in eligible if route(r) not in failed_routes]
                    if not eligible:
                        unavailable_escalation = True
            take = min(MAX_ROUTES_PER_UNIT, cap) if mode == 'mica' else 1
            options[contract['contract_id']] = eligible[:take] or [None]
            if len(eligible) > take:
                pruned.append({'plan_sha256': sha, 'contract': contract['contract_id'],
                               'reason': 'route_width_bound', 'omitted_count': len(eligible) - take,
                               'eligible_routes_sha256': digest([route(r) for r in eligible])})
        if unavailable_escalation:
            rejected.append({'plan_sha256': sha, 'reason': 'no_remaining_eligible_escalation_worker'})
            continue
        iterator = iter(_variants(plan, depth, options, cap + len(outcomes)))
        iterators.append((sha, iterator))
    # Round-robin graph consideration prevents a single graph from filling the
    # bounded queue before other admitted graphs get their first alternative.
    # This does not establish starvation freedom beyond this finite generation.
    while iterators and len(pending) < cap:
        remaining = []
        for sha, iterator in iterators:
            item = next(iterator, None)
            while item is not None and item['id'] in tried:
                rejected.append({'id': item['id'], 'plan_sha256': sha, 'reason': 'already_executed'})
                item = next(iterator, None)
            if item is not None:
                if len(pending) < cap:
                    pending.append(item)
                else:
                    pruned.append({'id': item['id'], 'plan_sha256': sha, 'reason': 'frontier_width_bound'})
                remaining.append((sha, iterator))
        iterators = remaining
    for sha, _ in iterators:
        pruned.append({'plan_sha256': sha, 'reason': 'unexpanded_cartesian_neighborhood',
                       'omitted_count': None, 'scope': 'unexplored_not_materialized_alternatives'})
    planner_contract = {'objective': request['objective'], 'model_eligibility': {'task_class': 'planning'}}
    planners = _eligible(planner_contract, inventory, observations, mode)
    expansions = []
    if not plans:
        latest = history[-1]['result'] if history else None
        trigger = ({k: latest[k] for k in ('failure', 'contract', 'error', 'failure_policy') if k in latest}
                   if latest else None)
        expansions.append(('propose', None, 0, trigger, len(history)))
    for h in history:
        previous = h.get('plan')
        result = h['result']
        if result['status'] != 'failed':
            continue
        target = next((c for c in (previous or {}).get('contracts', []) if c['contract_id'] == result.get('contract')), None)
        trigger = {k: result[k] for k in ('failure', 'contract', 'error', 'failure_policy') if k in result}
        depth = h['choice']['depth'] + 1
        if target and target['failure_policy']['action'] in ('refine', 'refine_or_escalate'):
            kind = 'refine'
        elif previous is not None and not target:
            kind = 'propose'
        else:
            continue
        if depth > request['budget']['max_depth']:
            rejected.append({'parent_plan_sha256': previous['content_hash'], 'reason': 'original_depth_bound'})
        else:
            expansions.append((kind, previous['content_hash'], depth, trigger, 0))
    for kind, parent, depth, trigger, generation in ([] if build_only else expansions):
        if len(plans) >= cap:
            rejected.append({'kind': kind, 'parent_plan_sha256': parent, 'reason': 'retained_graph_bound'})
            continue
        if not planners:
            rejected.append({'kind': kind, 'parent_plan_sha256': parent, 'reason': 'no_eligible_planner'})
        for row in planners[:min(MAX_ROUTES_PER_UNIT, cap) if mode == 'mica' else 1]:
            candidate = _candidate(kind, None, depth, [row], parent=parent, trigger=trigger, generation=generation)
            if candidate['id'] in tried:
                rejected.append({'id': candidate['id'], 'reason': 'already_executed'})
            else:
                pending.append(candidate)
    # Expansions and materialized graph alternatives share one width bound and
    # one selection policy; expansion costs are partial too (children unknown).
    shared = next((dimension for dimension in ('milliseconds', 'cost_units') if pending and mode == 'mica'
                   and all(c['score']['dimensions'][dimension]['all_bases_known'] for c in pending)), None)
    metric = ('expected_known_component_sum' if shared and all(
        c['score']['dimensions'][shared]['expected_known_component_sum'] is not None for c in pending)
        else 'known_component_sum')
    def order(candidate):
        score = candidate['score']
        cost = score['dimensions'][shared][metric] if shared else 0
        return (cost, score['fallback_call_allowance'], candidate['depth'], candidate['id'])
    pending.sort(key=order)
    for candidate in pending[cap:]:
        pruned.append({'id': candidate['id'], 'reason': 'frontier_width_bound', 'score': candidate['score']})
    pending = pending[:cap]
    return {'version': VERSION, 'scope': SCOPE, 'root_request_sha256': C.digest(request),
            'mode': mode, 'index': index, 'phase': 'build' if build_only else 'choice',
            'limits': {'frontier': cap, 'routes_per_unit': min(MAX_ROUTES_PER_UNIT, cap),
                                                  'candidate_lifecycles': request['budget']['max_candidates'],
                                                  'expansions_per_lifecycle': 1,
                                                  'depth': request['budget']['max_depth']},
            'ranking_dimension': shared, 'ranking_component': metric if shared else None,
            'observations_sha256': R.summarize(observations)['observations_sha256'],
            'candidates': pending, 'selected': pending[0] if pending else None,
            'rejected': rejected, 'pruned': pruned,
            'optimality': 'not_established', 'starvation_freedom': 'not_established'}
