"""MICA repair: replaces one failed unit contract by a checked sub-graph of helpers, keeping its wrapper.

Depends on: contracts.py (and search.py lazily). Used by search.py. Pure.

Details
    Pure, bounded replacement of one failed MICA contract by a checked DAG.

    This retains structural authority and exposed examples. It does not prove prose
    refinement, execute code, persist a plan, or choose/dispatch a provider. The caller
    owns shared call/depth/deadline accounting and retains its original root checks.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import json
import re

from symblic.mica import contracts as C

VERSION = 1
_BASE = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')
_FIELDS = {'id', 'names', 'heading', 'body', 'uses', 'examples', 'requirements'}


def _fail(code, message):
    raise C.ContractError(code, message)


def _base(value):
    match = _BASE.match(value) if type(value) is str else None
    if match is None:
        _fail('refinement_uses', 'Dependency names must be declared JavaScript exports.')
    return match.group(0)


def _original(request, plan, failed_id):
    request = C.normalize_request(request)
    plan = C.validate_plan(request, plan)
    failed = next((row for row in plan['contracts'] if row['contract_id'] == failed_id), None)
    if failed is None:
        _fail('refinement_target', 'The failed contract must belong to the original plan.')
    if failed['failure_policy']['action'] not in ('refine', 'refine_or_escalate'):
        _fail('refinement_policy', 'The failed contract does not authorize structural refinement.')
    return request, plan, failed


def refine_prompt(request, plan, failed_id, feedback):
    """Complete scoped card. Feedback must be trusted public host counterevidence.

    No evaluator-only inputs belong in this API. Oversize cards are refused whole;
    no requirement, dependency, example or original expected value is truncated.
    """
    request, plan, failed = _original(request, plan, failed_id)
    if len(plan['contracts']) >= request['budget']['max_units']:
        _fail('RESOURCE_EXHAUSTION', 'The original unit budget has no room for a refinement helper.')
    C.digest(feedback)
    by_id = {row['contract_id']: row for row in plan['contracts']}
    closure = set()
    def visit(ident):
        for dep in by_id[ident]['dependency_contract_ids']:
            if dep not in closure:
                closure.add(dep); visit(dep)
    visit(failed_id)
    reqs = set(failed['root_requirement_ids'])
    unit = failed['unit']
    card = {
        'role': 'Subdivide one failed pure JavaScript construction contract.',
        'failed_contract': failed,
        'declared_dependency_contracts': [by_id[ident] for ident in plan['order'] if ident in closure],
        'authoritative_requirements': [row for row in request['requirements'] if row['id'] in reqs],
        'authoritative_exports': [row for row in request['exports'] if row['name'] in unit['names']],
        'public_acceptance': [row for row in request['tests'] if set(row['requirement_ids']) <= reqs],
        'public_failure': feedback,
        'remaining_unit_slots': request['budget']['max_units'] - len(plan['contracts']),
        'output_format': {'units': [{'id': failed_id, 'names': unit['names'], 'heading': unit['heading'],
            'body': unit['body'], 'uses': [_base(name) for name in unit['uses']],
            'examples': unit['examples'], 'requirements': failed['root_requirement_ids']} ]},
        'rules': [
            'Return one raw JSON object with units only, without a fence or wrapper. No source bodies, commands, files or tools.',
            'Keep exactly one wrapper with the original id, ordered exports, heading, body and requirement IDs.',
            'The wrapper retains every original example and expected JSON value; proposed examples only add checks.',
            'Add at least one helper with fresh id/exports, precise behavior and nonempty executable examples.',
            'Each helper maps a nonempty subset of the original wrapper requirement IDs.',
            'The wrapper may use original direct dependencies and new helpers; keep every original direct dependency.',
            'Helpers may use original direct dependency exports or new helpers only. No dependency cycles.',
            'Every helper must be reachable from the wrapper. Existing dependency contracts are read-only.',
            'Use exact top-level function declarations for named exports and nest internal implementation helpers.',
            'Original root tests, effects, permissions, budgets, model eligibility and acceptance remain host authority.',
            'Retaining examples establishes no formal or prose refinement proof.'
        ]}
    text = ('Subdivide the failed contract using the supplied requirements. Return ONLY one raw JSON object without a fence or wrapper '
            'whose object has the key units. Retain the required wrapper and add real task-specific helpers. '
            'Do not reproduce this input envelope. The output_format contains the original wrapper to preserve, '
            'not a complete refinement; at least one new helper is required.\n\nInput data (not the response):\n' +
            json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    if len(text) > min(request['budget']['context_chars'], failed['resource_budget']['context_chars']):
        _fail('RESOURCE_EXHAUSTION', 'The complete refinement card exceeds the original context allowance.')
    return text


def apply_refinement(request, plan, failed_id, proposal, branch_id):
    """Return a new fully validated plan and separate structural lineage receipt.

    All nonfailed contracts remain byte-for-byte canonical equals. The wrapper's
    authority and original checks are retained. A construction strategy may be
    replaced only under its already-declared refinement failure policy.
    """
    request, plan, original = _original(request, plan, failed_id)
    C.digest(proposal)
    if type(proposal) is not dict or set(proposal) - {'units', 'assumptions'} or type(proposal.get('units')) is not list:
        _fail('refinement_shape', 'A refinement proposal contains units and optional unchanged assumptions only.')
    if 'assumptions' in proposal and proposal['assumptions'] != plan['assumptions']:
        _fail('refinement_assumptions', 'A refinement cannot change the original plan assumptions.')
    rows = copy.deepcopy(proposal['units'])
    if not 2 <= len(rows) <= request['budget']['max_units'] - len(plan['contracts']) + 1:
        _fail('refinement_units', 'A refinement needs one wrapper and bounded fresh helpers.')
    ids, names = set(), set()
    for row in rows:
        if type(row) is not dict or not _FIELDS <= set(row) or set(row) - _FIELDS - {'construction'}:
            _fail('refinement_shape', 'Each refinement unit must use the current planner unit schema.')
        C._identifier(row['id'])
        if row['id'] in ids:
            _fail('refinement_collision', 'Refinement contract IDs must be unique.')
        ids.add(row['id'])
        for field in ('names', 'uses', 'requirements'):
            C._strings(row[field], field, nonempty=field != 'uses')
        if any(name in names for name in row['names']):
            _fail('refinement_collision', 'Refinement export names must be unique.')
        names.update(row['names'])
    wrappers = [row for row in rows if row['id'] == failed_id]
    if len(wrappers) != 1:
        _fail('refinement_wrapper', 'Exactly one original wrapper is required.')
    wrapper = wrappers[0]; helpers = [row for row in rows if row is not wrapper]
    old_unit = original['unit']
    if wrapper['names'] != old_unit['names'] or wrapper['heading'] != old_unit['heading']:
        _fail('refinement_exports', 'The wrapper must preserve its exact ordered export interface.')
    if wrapper['body'] != old_unit['body'] or wrapper['requirements'] != original['root_requirement_ids']:
        _fail('refinement_root', 'The wrapper must preserve its body and complete root requirement mapping.')
    if 'construction' in wrapper and wrapper['construction'] != original.get('construction'):
        _fail('refinement_strategy', 'A proposal cannot replace the wrapper strategy with new authority.')
    outside = [row for row in plan['contracts'] if row['contract_id'] != failed_id]
    outside_ids = {row['contract_id'] for row in outside}
    outside_names = {name for row in outside for name in row['unit']['names']}
    helper_names = {name for row in helpers for name in row['names']}
    original_uses = {_base(name) for name in old_unit['uses']}
    for row in helpers:
        if row['id'] in outside_ids or set(row['names']) & (outside_names | set(old_unit['names'])):
            _fail('refinement_collision', 'Helpers must use fresh contract IDs and export names.')
        if not set(row['requirements']) <= set(original['root_requirement_ids']):
            _fail('refinement_root', 'Helpers cannot add unrelated root obligations.')
    for row in rows:
        if any(name != _base(name) for name in row['uses']) or not set(row['uses']) <= original_uses | helper_names:
            _fail('refinement_dependency', 'Refinement uses must name only original direct dependencies or fresh helpers.')
    if not original_uses <= set(wrapper['uses']):
        _fail('refinement_dependency', 'The wrapper must retain its original direct dependencies.')
    reachable = set()
    owner = {name: row['id'] for row in helpers for name in row['names']}
    helper_by_id = {row['id']: row for row in helpers}
    def visit_helper(name):
        ident = owner.get(name)
        if ident and ident not in reachable:
            reachable.add(ident)
            for used in helper_by_id[ident]['uses']:
                visit_helper(used)
    for name in wrapper['uses']:
        visit_helper(name)
    if reachable != set(helper_by_id):
        _fail('refinement_orphan', 'Every new helper must be in the wrapper dependency closure.')
    if type(wrapper['examples']) is not list:
        _fail('refinement_checks', 'Proposed wrapper examples must be a bounded list.')
    wrapper['examples'] += [copy.deepcopy(row) for row in old_unit['examples'] if row not in wrapper['examples']]
    wrapper.pop('construction', None)
    # Reuse the existing proposal compiler for structural unit admission. Its
    # temporary scaffold has TESTED labels only because it cannot carry original
    # full formal obligations. It is never returned or accepted. Final validation
    # below uses the unchanged caller request and all original obligations.
    scaffold_request = copy.deepcopy(request)
    for requirement in scaffold_request['requirements']:
        requirement['acceptance'] = 'TESTED'
    scaffold_units = []
    for row in outside:
        item = {'id': row['contract_id'], 'requirements': row['root_requirement_ids'],
                **{key: copy.deepcopy(row['unit'][key]) for key in ('names', 'heading', 'body', 'examples')}}
        item['uses'] = [_base(name) for name in row['unit']['uses']]
        if request['artifact_format'] == 'javascript_modules':
            item['output_path'] = row['output_artifacts'][0]
        scaffold_units.append(item)
    if request['artifact_format'] == 'javascript_modules':
        wrapper['output_path'] = original['output_artifacts'][0]
    from symblic.mica import search as M
    try:
        scaffold = M.proposal_to_plan(scaffold_request, {'units': scaffold_units + rows}, branch_id)
    except M.MicaError as error:
        _fail('refinement_shape', str(error))
    derived = {row['contract_id']: row for row in scaffold['contracts']}
    replacement = copy.deepcopy(original)
    replacement.pop('content_hash', None)
    replacement.pop('construction', None)
    replacement['unit']['uses'] = copy.deepcopy(old_unit['uses']) + [name for name in wrapper['uses'] if name not in original_uses]
    replacement['unit']['examples'] = copy.deepcopy(wrapper['examples'])
    replacement['dependency_contract_ids'] = derived[failed_id]['dependency_contract_ids']
    additions = []
    for helper in helpers:
        row = copy.deepcopy(derived[helper['id']]); row.pop('content_hash', None)
        row['parent_contract_id'] = failed_id
        for key in ('resource_budget', 'model_eligibility', 'failure_policy'):
            row[key] = copy.deepcopy(original[key])
        additions.append(row)
    contracts = [replacement if row['contract_id'] == failed_id else copy.deepcopy(row) for row in plan['contracts']] + additions
    final = C.validate_plan(request, {'id': branch_id, 'assumptions': plan['assumptions'], 'contracts': contracts})
    lineage = {'version': VERSION, 'failed_contract_id': failed_id,
               'original_contract_sha256': original['content_hash'], 'original_plan_sha256': plan['content_hash'],
               'candidate_plan_sha256': final['content_hash'], 'proposal_sha256': C.digest(proposal),
               'helper_contract_ids': [row['contract_id'] for row in additions],
               'removed_construction_sha256': C.digest(original['construction']) if original.get('construction') is not None else None,
               'scope': 'structural_replacement_with_retained_examples', 'formal_refinement_proven': False}
    return {'plan': final, 'lineage': lineage}
