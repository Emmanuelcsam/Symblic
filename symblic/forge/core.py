"""Forge, the state machine: a requirements project where models propose and only the operator accepts.

What it is for
    The Forge turns an incomplete intention ("I want a simple snake game") into reviewed requirements,
    engineering structure (objectives, criteria, architecture, components, isolated construction units, agent,
    model and machine plans, invariants, forbidden behaviour, evidence) and a frozen build handoff. A project is
    one JSON document (new_project) with branches, snapshots, handoffs and exports; every change is
    transition(project, action, payload), which validates and returns a new document or raises ForgeError and
    leaves the old one untouched. ACTIONS lists the ~60 transitions: answering and deferring questions,
    proposing and accepting statements, quarantining assumptions, resolving conflicts, editing entities,
    snapshots, branches and merges, model artifacts, validation and export records.

    The authority rule is the point of the design: a model can only *propose* (statements, suggestions,
    entities); an accepted requirement exists only after an explicit operator transition, and edits to an
    accepted item send it back to review without erasing its history. analyze(project) reports readiness,
    blockers, contradictions and dimension coverage; fingerprint(project) pins the accepted semantics;
    snake_demo() builds a labelled demonstration project.

What it is not
    No persistence, model call, compiler run, file access or external action happens here. The caller (the
    store in symblic.forge.store) owns revisions, timestamps and the audit trail.

Depends on: the standard library and symblic.forge.catalog. Used by: every other symblic.forge module and the
original host's Forge routes (integration/host/symblic_forge.py). Status: prototype; tested by
tests/forge/test_symblic_forge_core.py. The Forge's web page belonged to the original host and is not shipped.
User guide: docs/reference/FORGE.md.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math
import re
import uuid

from symblic.forge import catalog as C

MAX_TEXT = 40000
MAX_ITEMS = 5000
MAX_BYTES = 16 * 1024 * 1024
ID = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,95}\Z')
STATEMENT_FIELDS = {'text', 'dimension', 'fact', 'objective_ids', 'mandatory', 'rationale', 'condition', 'replaces_id'}
COMMON = {'id', 'text', 'status', 'dimension', 'provenance', 'source_ids', 'revisions'}
PROJECT_FIELDS = {'schema', 'id', 'revision', 'title', 'original_idea', 'active_branch', 'branches', 'snapshots', 'handoffs', 'exports'}
BRANCH_FIELDS = {'id', 'name', 'parent_id', 'base_snapshot_id', 'lifecycle', 'mode', 'domains',
    'active_dimensions', 'not_applicable', 'statements', 'questions', 'answers', 'suggestions', 'assumptions',
    'entities', 'scope', 'parked', 'vocabulary', 'definitions', 'settings', 'validation'}
ACTIONS = frozenset('''project.rename lifecycle.set mode.set presentation.set dimensions.set dimension.not_applicable
settings.set question.activate question.defer question.reopen question.dismiss question.research question.answer question.split
suggestion.accept suggestion.reject statement.propose statement.accept statement.accept_many statement.accept_replacement statement.edit
statement.reject statement.remove statement.rationale assumption.propose assumption.accept assumption.reject
assumption.replace conflict.resolve entity.propose entity.accept entity.edit entity.reject entity.remove
scope.set idea.park idea.promote vocabulary.add definition.add snapshot.create snapshot.restore branch.create
branch.switch branch.merge import.text model.artifact model.artifacts coach.propose validation.record handoff.record export.record'''.split())


class ForgeError(ValueError):
    """A refused pure state transition; callers retain the prior state."""


def _require(condition, message):
    if not condition:
        raise ForgeError(message)


def _text(value, *, empty=False, limit=MAX_TEXT):
    _require(type(value) is str and (empty or bool(value.strip())) and len(value) <= limit
             and '\0' not in value, 'Expected bounded nonempty text' if not empty else 'Expected bounded text')
    return value


def _id(value):
    _require(type(value) is str and ID.fullmatch(value), 'Invalid stable identifier')
    return value


def _new(prefix):
    return prefix + '_' + uuid.uuid4().hex


def _keys(value, required=(), optional=()):
    _require(type(value) is dict and set(required) <= set(value)
             and set(value) <= set(required) | set(optional), 'Unexpected or missing fields')


def _list(value, *, maximum=MAX_ITEMS):
    _require(type(value) is list and len(value) <= maximum, 'Expected bounded list')
    return value


def _strings(value, *, identifiers=False):
    for item in _list(value):
        (_id if identifiers else _text)(item)
    return value


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _json(value):
    try:
        def check(item, depth=0):
            if depth > 64:
                raise ValueError('JSON nesting exceeds 64 levels')
            if type(item) is dict:
                if not all(type(key) is str for key in item):
                    raise ValueError('JSON keys must be strings')
                for child in item.values():
                    check(child, depth + 1)
            elif type(item) is list:
                for child in item:
                    check(child, depth + 1)
            elif type(item) not in (str, int, float, bool, type(None)):
                raise ValueError('Non-JSON value')
        check(value)
        raw = _canonical(value)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ForgeError('Expected finite, acyclic JSON state') from exc
    _require(len(raw.encode('utf-8')) <= MAX_BYTES, 'Project exceeds the bounded state size')
    return json.loads(raw)


def _provenance(kind, text, **extra):
    return {'kind': kind, 'original_text': text, **extra}


def _validate_provenance(value):
    _keys(value, ('kind', 'original_text'), ('role', 'model', 'source_branch', 'request_revision', 'identity'))
    _require(value['kind'] in C.PROVENANCE, 'Unknown provenance category')
    _text(value['original_text'], empty=True)
    if 'role' in value:
        _require(value['role'] in C.ROLES or value['role'] == 'VALIDATOR', 'Unknown artifact role')
    for key in ('model', 'source_branch'):
        if key in value:
            _text(value[key])
    if 'request_revision' in value:
        _require(type(value['request_revision']) is int and value['request_revision'] >= 0, 'Invalid request revision')
    if 'identity' in value:
        _validate_model_identity(value['identity'])


def _validate_model_identity(value):
    """Retained attribution, never current availability or acceptance authority."""
    _keys(value, ('member', 'team_sha256', 'context_sha256', 'phase'), ('model_identity', 'node'))
    from symblic.providers import agent_teams as Teams
    _require(Teams.normalize_member(value['member'], lane='forge') == value['member'], 'Invalid retained member profile')
    for key in ('team_sha256', 'context_sha256'):
        _require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]), 'Invalid proposal identity digest')
    _require(value['phase'] in ('proposal', 'critique'), 'Invalid proposal phase')
    if 'model_identity' in value:
        _require(type(value['model_identity']) is dict and len(_canonical(value['model_identity'])) <= 16000,
                 'Invalid bounded model identity receipt')
    if value.get('node') is not None:
        _text(value['node'], limit=64)


def _validate_fact(value):
    _keys(value, ('subject', 'predicate', 'value'), ('unit', 'tolerance', 'condition'))
    _text(value['subject'], limit=256)
    _text(value['predicate'], limit=256)
    _require(type(value['value']) in (str, int, float, bool, list, dict) or value['value'] is None, 'Invalid fact value')
    for key in ('unit', 'condition'):
        if key in value:
            _text(value[key], empty=True, limit=1000)
    if 'tolerance' in value:
        _require(type(value['tolerance']) in (int, float, str), 'Invalid explicit tolerance')


def _validate_record(row, fields=()):
    _keys(row, COMMON, fields)
    _id(row['id']); _text(row['text']); _strings(row['source_ids'], identifiers=True)
    _require(row['status'] in C.STATUSES, 'Unknown record state')
    _require(row['dimension'] in C.DIMENSIONS, 'Unknown engineering dimension')
    _validate_provenance(row['provenance'])
    for rev in _list(row['revisions']):
        _keys(rev, ('revision', 'before', 'action'))
        _require(type(rev['revision']) is int and rev['revision'] >= 0, 'Invalid revision history')
        _require(type(rev['before']) is dict, 'Invalid retained previous state')
        _text(rev['action'], limit=80)
    if 'fact' in row:
        _validate_fact(row['fact'])
    if 'objective_ids' in row:
        _strings(row['objective_ids'], identifiers=True)
    if 'replaces_id' in row:
        _id(row['replaces_id'])
    if 'mandatory' in row:
        _require(type(row['mandatory']) is bool, 'Mandatory is an explicit boolean')
    for key in ('rationale', 'condition'):
        if key in row:
            _text(row[key], empty=True)
    if row['status'] == 'accepted':
        _require(row['provenance']['kind'] not in ('MODEL_QUESTION', 'MODEL_SUGGESTION', 'SYSTEM_DERIVED'),
                 'Non-authoritative material cannot be accepted without an operator transition')


def _validate_settings(settings):
    _keys(settings, ('roles', 'presentation'))
    _require(settings['presentation'] in ('FOCUS', 'OVERVIEW'), 'Unknown presentation mode')
    _keys(settings['roles'], C.ROLES)
    for cfg in settings['roles'].values():
        _keys(cfg, ('app', 'allow_cloud', 'fallback'))
        _text(cfg['app'], empty=True, limit=512)
        _require(type(cfg['allow_cloud']) is bool, 'Cloud permission must be explicit')
        _strings(cfg['fallback'])
        _require(len(cfg['fallback']) <= 8 and len(set(cfg['fallback'])) == len(cfg['fallback']), 'Invalid explicit fallback list')
        for app in cfg['fallback']:
            _text(app, limit=512)


def _known_ids(project, branch):
    result = {project['id'], branch['id']} | set(project['branches'])
    for key in ('statements', 'questions', 'answers', 'suggestions', 'assumptions', 'parked', 'vocabulary', 'definitions'):
        result.update(row['id'] for row in branch[key])
    for values in branch['entities'].values():
        result.update(row['id'] for row in values)
    return result


def _validate_branch(branch, project, *, snapshot=False):
    _keys(branch, BRANCH_FIELDS)
    _id(branch['id']); _text(branch['name'], limit=120)
    _require(branch['lifecycle'] in C.LIFECYCLES and branch['mode'] in C.MODES, 'Unknown project lifecycle or refinement mode')
    for key in ('parent_id', 'base_snapshot_id'):
        if branch[key] is not None:
            _id(branch[key])
    _strings(branch['domains']); _require(set(branch['domains']) <= set(C.DOMAINS), 'Unknown project domain')
    _strings(branch['active_dimensions'])
    _require(len(branch['active_dimensions']) == len(set(branch['active_dimensions']))
             and set(branch['active_dimensions']) <= set(C.DIMENSIONS), 'Invalid active dimensions')
    _require(type(branch['not_applicable']) is dict and set(branch['not_applicable']) <= set(C.DIMENSIONS), 'Invalid dimension exclusions')
    for reason in branch['not_applicable'].values():
        _text(reason)
    _validate_settings(branch['settings'])
    _keys(branch['entities'], C.ENTITY_SCHEMAS)
    seen = set()
    def unique(row):
        _require(row['id'] not in seen, 'Duplicate entity identifier within branch')
        seen.add(row['id'])
    for key, fields in [('statements', STATEMENT_FIELDS - {'text', 'dimension'}), ('assumptions', set())]:
        for row in _list(branch[key]):
            _validate_record(row, fields); unique(row)
    for kind, rows in branch['entities'].items():
        for row in _list(rows):
            _validate_record(row, C.ENTITY_SCHEMAS[kind]['fields']); unique(row)
            _entity_fields(kind, row)
            if row['status'] == 'accepted':
                _entity_contract(kind, row)
    for q in _list(branch['questions']):
        _keys(q, ('id', 'key', 'dimension', 'text', 'severity', 'status', 'reason', 'source_ids', 'suggestion_ids', 'depends_on', 'mandatory'), ('provenance',))
        _id(q['id']); unique(q); _text(q['key'], limit=256); _text(q['text']); _text(q['reason'], empty=True)
        _require(q['dimension'] in C.DIMENSIONS and q['severity'] in C.SEVERITIES
                 and q['status'] in C.QUESTION_STATUSES and type(q['mandatory']) is bool, 'Invalid question state')
        for key in ('source_ids', 'suggestion_ids', 'depends_on'):
            _strings(q[key], identifiers=key != 'depends_on')
        if 'provenance' in q:
            _validate_provenance(q['provenance'])
    for answer in _list(branch['answers']):
        _keys(answer, ('id', 'question_id', 'text', 'provenance'), ('source_suggestion_id',))
        _id(answer['id']); unique(answer); _id(answer['question_id']); _text(answer['text']); _validate_provenance(answer['provenance'])
    for s in _list(branch['suggestions']):
        _keys(s, ('id', 'question_id', 'text', 'status', 'provenance'), ('value', 'tradeoffs'))
        _id(s['id']); unique(s); _id(s['question_id']); _text(s['text']); _validate_provenance(s['provenance'])
        _require(s['status'] in ('proposed', 'accepted', 'rejected'), 'Invalid suggestion state')
        if 'tradeoffs' in s:
            _strings(s['tradeoffs'])
    for row in _list(branch['parked']):
        _keys(row, ('id', 'text', 'status')); _id(row['id']); unique(row); _text(row['text'])
        _require(row['status'] in ('parked', 'proposed'), 'Invalid parked state')
    for row in _list(branch['vocabulary']):
        _keys(row, ('id', 'name', 'aliases')); _id(row['id']); unique(row); _text(row['name']); _strings(row['aliases'])
    for row in _list(branch['definitions']):
        _keys(row, ('id', 'term', 'text', 'source_ids')); _id(row['id']); unique(row); _text(row['term']); _text(row['text']); _strings(row['source_ids'], identifiers=True)
    _keys(branch['scope'], ('in_scope', 'out_of_scope', 'undecided_scope'))
    for values in branch['scope'].values():
        _strings(values)
    known = _known_ids(project, branch)
    questions = {q['id']: q for q in branch['questions']}
    suggestions = {s['id']: s for s in branch['suggestions']}
    for row in branch['statements'] + branch['assumptions'] + branch['questions'] + branch['definitions'] + [r for values in branch['entities'].values() for r in values]:
        _require(set(row.get('source_ids', [])) <= known, 'Unknown source lineage identifier')
    for q in branch['questions']:
        _require(all(s in suggestions and suggestions[s]['question_id'] == q['id'] for s in q['suggestion_ids']), 'Invalid question suggestion link')
    for row in branch['answers'] + branch['suggestions']:
        _require(row['question_id'] in questions, 'Unknown source question')
    for row in branch['answers']:
        if row.get('source_suggestion_id'):
            _require(row['source_suggestion_id'] in suggestions and suggestions[row['source_suggestion_id']]['question_id'] == row['question_id'], 'Unknown source suggestion')
    record_ids = {r['id'] for r in branch['statements']}
    kind_ids = {kind: {r['id'] for r in rows} for kind, rows in branch['entities'].items()}
    for row in branch['statements']:
        _require(set(row.get('objective_ids', [])) <= kind_ids['objectives'], 'Unknown objective reference')
        if 'replaces_id' in row:
            _require(row['replaces_id'] in record_ids and row['replaces_id'] != row['id'], 'Unknown original statement for proposal comparison')
    for kind, rows in branch['entities'].items():
        for row in rows:
            for field, targets in [('requirement_ids', record_ids), ('unit_ids', kind_ids['units']),
                                   ('criterion_ids', kind_ids['criteria']), ('dependencies', known)]:
                _require(set(row.get(field, [])) <= targets, 'Unknown ' + field + ' reference')
            if 'component_id' in row:
                _require(row['component_id'] in kind_ids['components'], 'Unknown component reference')
            if 'parent_objective_id' in row:
                _require(row['parent_objective_id'] in kind_ids['objectives'] and row['parent_objective_id'] != row['id'], 'Invalid parent objective')
            if 'repair' in row:
                _validate_repair(row['repair'], branch)
            if kind == 'dependencies':
                for field in ('source', 'target'):
                    if field in row:
                        _require(row[field] in known, 'Unknown dependency endpoint')
    if branch['validation'] is not None:
        _require(type(branch['validation']) is dict, 'Invalid validation receipt')
    if not snapshot:
        _require(branch['parent_id'] is None or branch['parent_id'] in project['branches'], 'Unknown parent branch')
        _require(branch['base_snapshot_id'] is None or branch['base_snapshot_id'] in project['snapshots'], 'Unknown baseline snapshot')


def validate_project(project):
    value = _json(project)
    _keys(value, PROJECT_FIELDS)
    _require(value['schema'] == C.SCHEMA, 'Unsupported Forge schema')
    _id(value['id']); _text(value['title'], limit=200); _text(value['original_idea'])
    _require(type(value['revision']) is int and value['revision'] >= 0, 'Invalid project revision')
    _require(type(value['branches']) is dict and 1 <= len(value['branches']) <= 64, 'Invalid branch collection')
    _require(type(value['snapshots']) is dict and len(value['snapshots']) <= 256, 'Invalid snapshot collection')
    _id(value['active_branch'])
    _require(value['active_branch'] in value['branches'], 'Unknown active branch')
    for identifier, branch in value['branches'].items():
        _require(type(branch) is dict, 'Invalid branch object')
        _require(identifier == branch.get('id'), 'Branch key does not match identity')
        _validate_branch(branch, value)
    for identifier, snapshot in value['snapshots'].items():
        _keys(snapshot, ('id', 'name', 'branch_id', 'source_revision', 'branch', 'fingerprint'), ('branch_states',))
        _require(identifier == snapshot['id'], 'Snapshot identity mismatch')
        _id(identifier); _id(snapshot['branch_id']); _text(snapshot['name'], limit=200)
        _require(type(snapshot['source_revision']) is int and snapshot['source_revision'] >= 0, 'Invalid snapshot revision')
        _require(type(snapshot['fingerprint']) is str and re.fullmatch('[0-9a-f]{64}', snapshot['fingerprint']), 'Invalid snapshot fingerprint')
        _validate_branch(snapshot['branch'], value, snapshot=True)
        if 'branch_states' in snapshot:
            _require(type(snapshot['branch_states']) is dict and len(snapshot['branch_states']) <= 64, 'Invalid frozen branch states')
            _require(snapshot['branch_id'] in snapshot['branch_states'], 'Snapshot active branch is missing')
            _require(snapshot['branch_states'][snapshot['branch_id']] == snapshot['branch'], 'Snapshot active branch copies disagree')
            for key, frozen_branch in snapshot['branch_states'].items():
                _require(type(frozen_branch) is dict and frozen_branch.get('id') == key, 'Invalid frozen branch identity')
                _validate_branch(frozen_branch, value, snapshot=True)
        pinned = {**value, 'active_branch': snapshot['branch']['id'], 'branches': {snapshot['branch']['id']: snapshot['branch']}}
        _require(snapshot['fingerprint'] == fingerprint(pinned), 'Snapshot semantic fingerprint mismatch')
    for handoff in _list(value['handoffs'], maximum=256):
        _require(type(handoff) is dict, 'Invalid retained handoff')
    seen_exports = set()
    for row in _list(value['exports'], maximum=MAX_ITEMS):
        _validate_export(row)
        _require(row['id'] not in seen_exports, 'Duplicate exported artifact identity')
        seen_exports.add(row['id'])
    return value


def active_branch(project):
    return project['branches'][project['active_branch']]


def _seed_questions(project, branch):
    keys = {q['key'] for q in branch['questions']}
    for item in C.questions_for(project['original_idea'], branch['domains'], branch['active_dimensions']):
        if item['key'] in keys:
            continue
        qid = 'q_' + hashlib.sha256((project['id'] + '\0' + item['key']).encode()).hexdigest()[:24]
        q = {k: deepcopy(v) for k, v in item.items() if k != 'suggestions'}
        q.update(id=qid, status='open', source_ids=[project['id']], suggestion_ids=[])
        for index, text in enumerate(item['suggestions']):
            sid = qid.replace('q_', 's_', 1) + '_' + str(index)
            branch['suggestions'].append({'id': sid, 'question_id': qid, 'text': text, 'status': 'proposed',
                'provenance': _provenance('SYSTEM_DERIVED', text), 'tradeoffs': C.suggestion_tradeoffs(item['key'], text)})
            q['suggestion_ids'].append(sid)
        branch['questions'].append(q)


def _refinement_questions(project, branch):
    keys = {q['key'] for q in branch['questions']}
    for row in _accepted(branch):
        key = 'challenge.' + row['id']
        if branch['mode'] == 'CHALLENGE' and key not in keys:
            branch['questions'].append({'id': _new('q'), 'key': key,
                'text': 'What observable counterexample or limitation would invalidate: ' + row['text'],
                'dimension': row['dimension'], 'severity': 'HIGH', 'status': 'open',
                'reason': 'Challenge an accepted decision without changing it.', 'source_ids': [row['id']],
                'suggestion_ids': [], 'depends_on': [], 'mandatory': False})
        for word in ('simple', 'fast', 'robust', 'scalable', 'intuitive', 'minimal'):
            key = 'clarify.' + row['id'] + '.' + word
            if key not in keys and re.search(r'\b' + word + r'\b', row['text'], re.I):
                branch['questions'].append({'id': _new('q'), 'key': key, 'text': f'Which observable constraint defines “{word}” in this requirement?',
                    'dimension': row['dimension'], 'severity': 'MEDIUM', 'status': 'open', 'reason': 'An accepted statement contains an imprecise adjective.',
                    'source_ids': [row['id']], 'suggestion_ids': [], 'depends_on': [], 'mandatory': False})
        fact = row.get('fact', {})
        key = 'units.' + row['id']
        if key not in keys and type(fact.get('value')) in (int, float) and not fact.get('unit') and any(
                token in fact.get('predicate', '').lower() for token in ('width', 'height', 'memory', 'voltage', 'power', 'interval', 'speed', 'duration')):
            branch['questions'].append({'id': _new('q'), 'key': key, 'text': 'What unit applies to ' + fact['predicate'] + '?',
                'dimension': row['dimension'], 'severity': 'HIGH', 'status': 'open', 'reason': 'An explicit physical or timing quantity lacks a unit.',
                'source_ids': [row['id']], 'suggestion_ids': [], 'depends_on': [], 'mandatory': True})


def _expand_domains(project, branch):
    additions = []
    for row in _accepted(branch):
        fact = row.get('fact', {})
        key = fact.get('predicate')
        if key not in ('agents', 'cluster', 'models', 'visual', 'platform'):
            continue
        value = str(fact.get('value', '')).strip().lower()
        if value.startswith(('no ', 'none', 'one machine', 'single machine')):
            continue
        domain = {'agents': 'agent', 'cluster': 'cluster', 'models': 'ai', 'visual': 'web'}.get(key)
        if key == 'platform':
            domain = 'web' if 'browser' in value or 'web' in value else None
        if domain and domain not in branch['domains']:
            additions.append(domain)
    for domain in dict.fromkeys(additions):
        branch['domains'].append(domain)
        branch['active_dimensions'] = list(dict.fromkeys(branch['active_dimensions'] + C.active_dimensions([domain])))
    if additions:
        _seed_questions(project, branch)


def _split_question(branch, question, texts):
    _strings(texts)
    _require(2 <= len(texts) <= 20, 'Split into two to twenty explicit independent questions')
    _require(all(text.count('?') <= 1 for text in texts), 'Each child must contain one independent question')
    question['status'] = 'dismissed'
    question['reason'] = 'Split explicitly into independent questions; original wording retained.'
    for text in texts:
        child = deepcopy(question)
        child.update(id=_new('q'), text=text, key=_new('split'), status='open', source_ids=[question['id']], suggestion_ids=[])
        branch['questions'].append(child)


def new_project(idea, title='', template='', *, project_id=None):
    _text(idea)
    _text(title, empty=True, limit=200)
    _text(template, empty=True, limit=100)
    _require(not template or template in C.TEMPLATES, 'Unknown project template')
    domains = C.classify(idea, template)
    branch = {'id': 'main', 'name': 'Main', 'parent_id': None, 'base_snapshot_id': None,
        'lifecycle': 'IDEA', 'mode': 'DEEP', 'domains': domains, 'active_dimensions': C.active_dimensions(domains),
        'not_applicable': {}, 'statements': [], 'questions': [], 'answers': [], 'suggestions': [],
        'assumptions': [], 'entities': {kind: [] for kind in C.ENTITY_SCHEMAS},
        'scope': {'in_scope': [], 'out_of_scope': [], 'undecided_scope': []}, 'parked': [],
        'vocabulary': [], 'definitions': [], 'settings': {'roles': {role: {'app': '', 'allow_cloud': False, 'fallback': []}
        for role in C.ROLES}, 'presentation': 'FOCUS'}, 'validation': None}
    project = {'schema': C.SCHEMA, 'id': project_id or _new('forge'), 'revision': 0,
        'title': title or ' '.join(idea.split())[:100], 'original_idea': idea, 'active_branch': 'main',
        'branches': {'main': branch}, 'snapshots': {}, 'handoffs': [], 'exports': []}
    _seed_questions(project, branch)
    _snapshot(project, 'Original idea')
    return validate_project(project)


def _find(rows, identifier):
    _id(identifier)
    row = next((r for r in rows if r['id'] == identifier), None)
    _require(row is not None, 'Unknown entity identifier')
    return row


def _history(project, row, action):
    prior = {k: deepcopy(v) for k, v in row.items() if k != 'revisions'}
    row['revisions'].append({'revision': project['revision'], 'before': prior, 'action': action})


def _record(text, dimension='PURPOSE', *, kind='USER_ORIGINAL', source_ids=(), provenance=None, **fields):
    _text(text)
    _require(dimension in C.DIMENSIONS, 'Unknown engineering dimension')
    return {'id': _new('r'), 'text': text, 'status': 'proposed', 'dimension': dimension,
        'provenance': provenance or _provenance(kind, text), 'source_ids': list(source_ids), 'revisions': [], **deepcopy(fields)}


def _accept(project, row):
    _require(row['status'] == 'proposed', 'Only an explicit proposal may be accepted')
    _history(project, row, 'accept')
    row['status'] = 'accepted'
    prior_kind = row['provenance']['kind']
    if prior_kind in ('MODEL_SUGGESTION', 'MODEL_QUESTION', 'SYSTEM_DERIVED'):
        row['provenance']['kind'] = 'USER_ACCEPTED_SUGGESTION'


def _pixel_answer(question, text):
    """Recognize explicit simple pixel quantities, never infer units or parse prose.

    The bounded English cardinal grammar covers zero through nine hundred and
    ninety-nine. Unsupported/ambiguous input stays exact text for explicit review.
    """
    if question['key'] not in ('viewport.width', 'viewport.height'):
        return None
    match = re.fullmatch(r'\s*(.+?)\s*(?:px|pixels?)\s*', text, re.I)
    if not match:
        return None
    number = match[1].strip().lower()
    if len(number) <= 100 and re.fullmatch(r'(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)', number):
        value = float(number) if '.' in number else int(number)
        if math.isfinite(value) and Decimal(str(value)) == Decimal(number):
            return value
        return None
    if not re.fullmatch(r'[a-z]+(?:(?:\s+|-)[a-z]+)*', number):
        return None
    ones = dict(zip(('zero one two three four five six seven eight nine ten eleven twelve '
                     'thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split(), range(20)))
    tens = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))
    words = number.replace('-', ' ').split()

    def under_hundred(tokens):
        if len(tokens) == 1:
            return ones.get(tokens[0], tens.get(tokens[0]))
        if len(tokens) == 2 and tokens[0] in tens and 1 <= ones.get(tokens[1], -1) <= 9:
            return tens[tokens[0]] + ones[tokens[1]]
        return None

    if len(words) >= 2 and 1 <= ones.get(words[0], -1) <= 9 and words[1] == 'hundred':
        remainder = words[2:]
        if not remainder:
            return ones[words[0]] * 100
        if remainder[0] == 'and':
            remainder = remainder[1:]
        tail = under_hundred(remainder)
        return ones[words[0]] * 100 + tail if tail is not None and tail > 0 else None
    return under_hundred(words)


def _answer(project, branch, question, text, suggestion=None):
    _text(text)
    _require(question['status'] not in ('answered', 'dismissed'), 'Question must be reopened before another answer')
    provenance = _provenance('USER_ANSWER', text)
    if suggestion:
        _require(suggestion['status'] == 'proposed', 'Suggestion is no longer proposed')
        provenance = _provenance('USER_ACCEPTED_SUGGESTION' if text == suggestion['text'] else 'USER_EDITED_SUGGESTION',
                                 suggestion['text'])
        suggestion['status'] = 'accepted'
    answer = {'id': _new('answer'), 'question_id': question['id'], 'text': text, 'provenance': provenance}
    if suggestion:
        answer['source_suggestion_id'] = suggestion['id']
    branch['answers'].append(answer)
    question['status'] = 'answered'
    fact = {'subject': 'project', 'predicate': question['key'], 'value': text}
    pixels = _pixel_answer(question, text)
    if pixels is not None:
        fact.update(value=pixels, unit='px')
    # Preserve answer bytes exactly. This visible proposal is not silently accepted.
    branch['statements'].append(_record(text, question['dimension'], provenance=deepcopy(provenance),
        source_ids=[question['id'], answer['id']], fact=fact, mandatory=question['mandatory'], objective_ids=[], rationale=''))


def _entity_contract(kind, row):
    for field in C.ENTITY_SCHEMAS[kind]['required']:
        _require(field in row, f'{kind} requires {field}')
        value = row[field]
        _require(value is not None and (not isinstance(value, str) or bool(value.strip())), f'{kind} requires explicit {field}')
        if field in ('requirement_ids', 'checks', 'outputs', 'verification', 'components', 'tradeoffs', 'capabilities'):
            _require(bool(value), f'{kind} requires nonempty {field}')
    if kind == 'dependencies':
        _id(row['source']); _id(row['target'])
        _require(row['kind'] in ('runtime', 'build', 'data', 'control'), 'Unknown dependency kind')
    if kind == 'units':
        broad = r'(?:all\s+(?:prior|previous)\s+context|(?:the\s+)?whole\s+conversation|everything\s+above|(?:the\s+)?project\s+so\s+far)'
        for value in row.get('inputs', []):
            _require(not re.fullmatch(r'(?:use\s+)?' + broad + r'[.!]?', value.strip(), re.I),
                     'Construction units require named inputs; implicit prior conversation is forbidden')
        _require(not re.match(r'^\s*use\s+' + broad + r'(?:\W|$)', row.get('objective', ''), re.I),
                 'Construction units may not request implicit prior conversation')
    for name in ('requirement_ids', 'unit_ids', 'criterion_ids', 'dependencies'):
        if name in row:
            _strings(row[name], identifiers=True)
    for name in ('inputs', 'outputs', 'checks', 'verification', 'forbidden_assumptions', 'defines', 'requires', 'paths'):
        if name in row:
            _strings(row[name])
    if kind == 'criteria':
        for name in ('observable', 'measurement', 'expected'):
            _text(row[name])
        _require(row['observable'].strip().lower() not in ('works correctly', 'looks good')
                 or row.get('subjective') is True, 'Acceptance criteria require an observable condition')


def _entity_fields(kind, row):
    identifiers = {'requirement_ids', 'unit_ids', 'criterion_ids', 'dependencies'}
    arrays = {'inputs', 'outputs', 'checks', 'verification', 'forbidden_assumptions', 'defines', 'requires', 'paths',
              'components', 'tradeoffs', 'unresolved', 'effects', 'permissions', 'capabilities'}
    for key in C.ENTITY_SCHEMAS[kind]['fields']:
        if key not in row:
            continue
        value = row[key]
        if key in identifiers:
            _strings(value, identifiers=True)
        elif key in arrays:
            _strings(value)
        elif key in ('component_id', 'source', 'target', 'parent_objective_id', 'node_id'):
            _id(value)
        elif key == 'captured_at':
            _require(type(value) in (int, float) and value >= 0, 'Inventory capture time must be explicit nonnegative seconds')
        elif key == 'inventory':
            _validate_inventory(value)
        elif key == 'repair':
            _require(type(value) is dict, 'Expected structured compiler repair proposal')
        elif key == 'subjective':
            _require(type(value) is bool, 'Subjective criterion flag must be boolean')
        elif key in ('size', 'memory_bytes', 'storage_bytes'):
            _require(type(value) is int and value >= 0, 'Evidence size must be a nonnegative byte count')
        elif key == 'concurrency':
            _require(type(value) is int and value >= 1, 'Concurrency must be a positive explicit integer')
        elif key in ('output_schema', 'model_placement', 'task_placement'):
            _require(type(value) in (dict, str), 'Expected explicit schema, placement map or description')
        else:
            _text(value, empty=key in ('persistent_state', 'policy', 'result'))


def _validate_inventory(value):
    _keys(value, (), ('models', 'nodes', 'complete', 'source'))
    _require('models' in value or 'nodes' in value, 'Inventory needs explicit observed models or nodes')
    _strings(value.get('models', []))
    if 'complete' in value:
        _require(type(value['complete']) is bool, 'Inventory completeness must be explicit')
    if 'source' in value:
        _text(value['source'])
    seen = set()
    for node in _list(value.get('nodes', [])):
        _keys(node, ('id', 'models'), ('online', 'memory_bytes', 'storage_bytes'))
        _id(node['id']); _strings(node['models'])
        _require(node['id'] not in seen, 'Duplicate inventory node')
        seen.add(node['id'])
        if 'online' in node:
            _require(type(node['online']) is bool, 'Node online state must be explicit')
        for key in ('memory_bytes', 'storage_bytes'):
            if key in node:
                _require(type(node[key]) is int and node[key] >= 0, 'Capacity must be a nonnegative byte count')


def _validate_repair(value, branch, *, current=False):
    _keys(value, ('source_sha256', 'start', 'end', 'replacement', 'diagnostic_index', 'statement_ids'))
    _require(type(value['source_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['source_sha256']), 'Invalid repair source hash')
    _require(type(value['start']) is int and type(value['end']) is int and 0 <= value['start'] <= value['end'] <= 400000, 'Invalid exact repair region')
    _require(type(value['diagnostic_index']) is int and value['diagnostic_index'] >= 0, 'Invalid diagnostic reference')
    _text(value['replacement'], empty=True); _strings(value['statement_ids'], identifiers=True)
    known = {r['id'] for r in branch['statements']} | {r['id'] for r in branch['entities']['units']}
    _require(set(value['statement_ids']) <= known, 'Repair references an unknown statement')
    if current:
        receipt = branch['validation'] or {}
        source = receipt.get('source')
        _require(type(source) is str and hashlib.sha256(source.encode()).hexdigest() == value['source_sha256'], 'Repair source has changed')
        _require(value['end'] <= len(source), 'Repair region exceeds the exact source')
        _require(value['end'] - value['start'] <= 8000 and len(value['replacement']) <= 8000,
                 'Repair proposals must remain within an explicit 8,000-character region')
        diagnostics = receipt.get('diagnostics', {}).get('diagnostics', [])
        _require(value['diagnostic_index'] < len(diagnostics), 'Repair diagnostic is unavailable')
        diagnostic = diagnostics[value['diagnostic_index']]
        _require(diagnostic.get('severity') == 'error', 'A compiler repair must reference an actual error')
        line = diagnostic.get('line')
        if type(line) is int and 1 <= line <= len(source.splitlines()):
            lines = source.splitlines(keepends=True)
            low = sum(len(part) for part in lines[:line - 1]); high = low + len(lines[line - 1])
            _require(value['start'] <= high and value['end'] >= low, 'Repair does not touch the diagnostic source line')


def repair_candidate(project, evidence_id):
    p = validate_project(project)
    branch = active_branch(p)
    row = _find(branch['entities']['evidence'], evidence_id)
    _require(row.get('evidence_type') == 'compiler_repair' and 'repair' in row, 'Choose a compiler repair proposal')
    _validate_repair(row['repair'], branch, current=True)
    repair = row['repair']; source = branch['validation']['source']
    return {'source': source[:repair['start']] + repair['replacement'] + source[repair['end']:],
        'source_sha256': repair['source_sha256'], 'offset_encoding': 'unicode_code_points', 'evidence_id': evidence_id,
        'changed_region': {'start': repair['start'], 'end': repair['end'], 'replacement': repair['replacement']},
        'validated': False, 'scope': 'Proposed editor source only; recheck with the current compiler before accepting.'}


def _snapshot(project, name):
    _text(name, limit=200)
    branch = active_branch(project)
    identifier = _new('snapshot')
    project['snapshots'][identifier] = {'id': identifier, 'name': name, 'branch_id': branch['id'],
        'source_revision': project['revision'], 'branch': deepcopy(branch), 'branch_states': deepcopy(project['branches']),
        'fingerprint': fingerprint(project)}
    return identifier


def _accepted(branch, kind='statements'):
    return [r for r in (branch[kind] if kind == 'statements' else branch['entities'][kind]) if r['status'] == 'accepted']


def requirement_text(row):
    """Retain exact requirement wording and its explicit fact context in handoffs."""
    return row['text'] + ('\nAccepted fact: ' + _canonical(row['fact']) if 'fact' in row else '')


def semantic_payload(project):
    branch = active_branch(project)
    records = _accepted(branch) + [r for k in C.ENTITY_SCHEMAS for r in _accepted(branch, k)]
    ignored = {'id', 'status', 'provenance', 'source_ids', 'revisions', 'rationale', 'captured_at', 'replaces_id'}
    references = {'objective_ids', 'requirement_ids', 'component_id', 'parent_objective_id', 'dependencies', 'unit_ids', 'criterion_ids', 'source', 'target'}
    # Cross-links use content identities, not random storage UUIDs.
    names = {r['id']: hashlib.sha256(_canonical({k: v for k, v in r.items() if k not in ignored | references}).encode()).hexdigest()
             for r in records}
    def semantic(row):
        result = {}
        for key, value in row.items():
            if key in ignored:
                continue
            if key in references:
                value = [names.get(x, 'unresolved:' + x) for x in value] if isinstance(value, list) else names.get(value, 'unresolved:' + str(value))
            result[key] = deepcopy(value)
        return result
    return {'requirements': sorted([semantic(r) for r in _accepted(branch)], key=_canonical),
        'entities': {kind: sorted([semantic(r) for r in _accepted(branch, kind)], key=_canonical) for kind in C.ENTITY_SCHEMAS},
        'scope': {k: sorted(v) for k, v in branch['scope'].items() if k != 'undecided_scope'},
        'definitions': sorted([{'term': r['term'], 'text': r['text']} for r in branch['definitions']], key=_canonical),
        'vocabulary': sorted([{'name': r['name'], 'aliases': sorted(r['aliases'])} for r in branch['vocabulary']], key=_canonical),
        'not_applicable': deepcopy(branch['not_applicable'])}


def fingerprint(project):
    return hashlib.sha256(_canonical(semantic_payload(project)).encode('utf-8')).hexdigest()


def _invalidate(project, old_fingerprint):
    branch = active_branch(project)
    if fingerprint(project) != old_fingerprint and branch['validation']:
        branch['validation']['current'] = False
        branch['validation']['stale'] = True
    if fingerprint(project) != old_fingerprint and branch['lifecycle'] in ('READY', 'EXPORTED', 'EXECUTION_TRANSFERRED'):
        branch['lifecycle'] = 'DEFINING'


def _propose(project, branch, fields, *, kind='USER_ORIGINAL', source_ids=(), provenance=None):
    _keys(fields, ('text',), STATEMENT_FIELDS - {'text'})
    data = deepcopy(fields)
    text = data.pop('text')
    dimension = data.pop('dimension', 'PURPOSE')
    row = _record(text, dimension, kind=kind, source_ids=source_ids, provenance=provenance, **data)
    branch['statements'].append(row)
    return row


def _entity_propose(branch, kind, fields, *, provenance=None, source_ids=()):
    _require(kind in C.ENTITY_SCHEMAS, 'Unknown entity collection')
    _keys(fields, ('text',), set(C.ENTITY_SCHEMAS[kind]['fields']) | {'dimension'})
    data = deepcopy(fields)
    if 'repair' in data:
        _require(kind == 'evidence' and data.get('evidence_type') == 'compiler_repair', 'Repair must be a compiler repair evidence proposal')
        _validate_repair(data['repair'], branch, current=True)
    text = data.pop('text'); dimension = data.pop('dimension', 'COMPONENTS')
    row = _record(text, dimension, provenance=provenance, source_ids=source_ids, **data)
    branch['entities'][kind].append(row)
    return row


def _model_artifact(project, branch, payload):
    _keys(payload, ('role', 'model', 'revision'), ('questions', 'statements', 'assumptions', 'entities', 'identity'))
    _require(payload['role'] in C.ROLES, 'Unknown model role')
    _text(payload['model'], limit=512)
    _require(type(payload['revision']) is int and payload['revision'] == project['revision'], 'Model artifact is stale')
    if 'identity' in payload:
        _validate_model_identity(payload['identity'])
    known = _known_ids(project, branch)
    def provenance(text, kind='MODEL_SUGGESTION'):
        return _provenance(kind, text, role=payload['role'], model=payload['model'], request_revision=payload['revision'],
                           **({'identity': deepcopy(payload['identity'])} if 'identity' in payload else {}))
    def sources(row):
        result = row.get('source_ids', [])
        _strings(result, identifiers=True)
        _require(set(result) <= known, 'Model artifact references unknown source IDs')
        return result
    for fields in _list(payload.get('statements', [])):
        _keys(fields, ('text',), (STATEMENT_FIELDS - {'text'}) | {'source_ids'})
        _propose(project, branch, {k: v for k, v in fields.items() if k != 'source_ids'},
                 source_ids=sources(fields), provenance=provenance(fields['text']))
    for fields in _list(payload.get('assumptions', [])):
        _keys(fields, ('text',), ('source_ids', 'dimension'))
        branch['assumptions'].append(_record(fields['text'], fields.get('dimension', 'PURPOSE'),
            source_ids=sources(fields), provenance=provenance(fields['text'])))
    for fields in _list(payload.get('entities', [])):
        _keys(fields, ('kind', 'entity'), ('source_ids',))
        _entity_propose(branch, fields['kind'], fields['entity'], source_ids=sources(fields),
                        provenance=provenance(fields['entity']['text']))
    for fields in _list(payload.get('questions', [])):
        _keys(fields, ('text', 'dimension'), ('source_ids', 'severity', 'reason', 'suggestions'))
        _require(fields['dimension'] in C.DIMENSIONS, 'Unknown question dimension')
        severity = fields.get('severity', 'MEDIUM')
        _require(severity in C.SEVERITIES, 'Unknown severity')
        qid = _new('q')
        q = {'id': qid, 'key': qid, 'text': _text(fields['text']), 'dimension': fields['dimension'],
             'severity': severity, 'status': 'open', 'mandatory': False,
             'reason': _text(fields.get('reason', ''), empty=True), 'source_ids': sources(fields),
             'depends_on': [], 'suggestion_ids': [], 'provenance': provenance(fields['text'], 'MODEL_QUESTION')}
        for choice in _list(fields.get('suggestions', [])):
            if isinstance(choice, str):
                text, tradeoffs = _text(choice), []
            else:
                _keys(choice, ('text',), ('tradeoffs',))
                text, tradeoffs = _text(choice['text']), _strings(choice.get('tradeoffs', []))
            sid = _new('suggestion')
            branch['suggestions'].append({'id': sid, 'question_id': qid, 'text': text, 'status': 'proposed',
                'provenance': provenance(text), 'tradeoffs': tradeoffs})
            q['suggestion_ids'].append(sid)
        branch['questions'].append(q)
        if fields['text'].count('?') > 1:
            pieces = [part for part in re.findall(r'[^?]+\??', fields['text']) if part.strip()]
            _split_question(branch, q, pieces)


def transition(project, action, payload=None, *, trusted=False):
    """Return a new state or refuse atomically. trusted is a host-only call argument."""
    _require(type(action) is str and action in ACTIONS, 'Unsupported Forge action')
    p = validate_project(project)
    data = _json(payload if payload is not None else {})
    _require(type(data) is dict, 'Action payload must be an object')
    branch = active_branch(p)
    old_fingerprint = fingerprint(p)
    prior_branch = branch['id']
    prior_decisions = {r['fact']['predicate'] for r in _accepted(branch) if r.get('fact')}
    if action == 'project.rename':
        _keys(data, ('title',)); p['title'] = _text(data['title'], limit=200)
    elif action == 'lifecycle.set':
        _keys(data, ('state',)); state = data['state']
        _require(state in C.LIFECYCLES, 'Unknown lifecycle')
        if state in ('READY', 'EXPORTED', 'EXECUTION_TRANSFERRED'):
            _require(analyze(p)['readiness']['ready'], 'Readiness blockers remain')
        if state == 'EXPORTED':
            _require(any(r['fingerprint'] == old_fingerprint and not r.get('historical') for r in p['exports']), 'No current host export receipt')
        if state == 'EXECUTION_TRANSFERRED':
            _require(any(r.get('fingerprint') == old_fingerprint and not r.get('historical') for r in p['handoffs']), 'No current host handoff receipt')
        branch['lifecycle'] = state
    elif action in ('mode.set', 'presentation.set'):
        _keys(data, ('mode',)); values = C.MODES if action == 'mode.set' else ('FOCUS', 'OVERVIEW')
        _require(data['mode'] in values, 'Unknown mode')
        (branch if action == 'mode.set' else branch['settings'])['mode' if action == 'mode.set' else 'presentation'] = data['mode']
    elif action == 'dimensions.set':
        _keys(data, ('dimensions',)); _strings(data['dimensions'])
        _require(set(data['dimensions']) <= set(C.DIMENSIONS), 'Unknown dimension')
        branch['active_dimensions'] = list(dict.fromkeys(data['dimensions']))
        _seed_questions(p, branch)
    elif action == 'dimension.not_applicable':
        _keys(data, ('dimension', 'reason')); _require(data['dimension'] in C.DIMENSIONS, 'Unknown dimension')
        branch['not_applicable'][data['dimension']] = _text(data['reason'])
    elif action == 'settings.set':
        _keys(data, ('roles',)); _require(type(data['roles']) is dict and set(data['roles']) <= set(C.ROLES), 'Unknown role')
        branch['settings']['roles'].update(deepcopy(data['roles']))
    elif action == 'question.split':
        _keys(data, ('id', 'questions')); _split_question(branch, _find(branch['questions'], data['id']), data['questions'])
    elif action.startswith('question.'):
        _keys(data, ('id', 'text') if action == 'question.answer' else ('id', 'reason') if action in ('question.dismiss', 'question.research') else ('id',))
        q = _find(branch['questions'], data['id'])
        if action == 'question.answer':
            _answer(p, branch, q, data['text'])
        else:
            if action == 'question.activate':
                for other in branch['questions']:
                    if other['status'] == 'active':
                        other['status'] = 'open'
            q['status'] = {'question.activate': 'active', 'question.defer': 'deferred', 'question.reopen': 'open',
                           'question.dismiss': 'dismissed', 'question.research': 'needs_research'}[action]
            if 'reason' in data:
                q['reason'] = _text(data['reason'])
    elif action.startswith('suggestion.'):
        _keys(data, ('id',), ('text',) if action == 'suggestion.accept' else ())
        row = _find(branch['suggestions'], data['id'])
        _require(row['status'] == 'proposed', 'Suggestion is no longer proposed')
        if action == 'suggestion.accept':
            _answer(p, branch, _find(branch['questions'], row['question_id']), data.get('text', row['text']), row)
        else:
            row['status'] = 'rejected'
    elif action == 'statement.propose':
        _propose(p, branch, data)
    elif action == 'statement.accept_many':
        _keys(data, ('ids',)); _strings(data['ids'], identifiers=True)
        _require(data['ids'] and len(set(data['ids'])) == len(data['ids']), 'Select distinct proposed statements')
        for identifier in data['ids']:
            _accept(p, _find(branch['statements'], identifier))
    elif action == 'statement.accept_replacement':
        _keys(data, ('id',))
        row = _find(branch['statements'], data['id'])
        _require(row.get('replaces_id'), 'Proposal does not name the original statement')
        original = _find(branch['statements'], row['replaces_id'])
        _require(original['status'] == 'accepted', 'Original statement is no longer accepted')
        _accept(p, row)
        _history(p, original, action); original['status'] = 'removed'
    elif action.startswith('statement.'):
        allowed = STATEMENT_FIELDS if action == 'statement.edit' else {'text'} if action == 'statement.rationale' else set()
        _keys(data, ('id',), allowed)
        row = _find(branch['statements'], data['id'])
        if action == 'statement.accept':
            _accept(p, row)
        else:
            _history(p, row, action)
            if action == 'statement.edit':
                _require('text' in data, 'Editing requires the exact replacement text')
                row.update({k: deepcopy(v) for k, v in data.items() if k != 'id'})
                row['status'] = 'proposed'
                row['provenance']['kind'] = 'USER_EDITED_SUGGESTION'
            elif action == 'statement.rationale':
                row['rationale'] = _text(data['text'], empty=True)
            else:
                row['status'] = 'rejected' if action == 'statement.reject' else 'removed'
    elif action == 'assumption.propose':
        _keys(data, ('text',), ('source_ids',))
        branch['assumptions'].append(_record(data['text'], source_ids=data.get('source_ids', [])))
    elif action.startswith('assumption.'):
        _keys(data, ('id', 'text') if action == 'assumption.replace' else ('id',), () if action == 'assumption.replace' else ('text',))
        row = _find(branch['assumptions'], data['id'])
        _require(row['status'] == 'proposed', 'Assumption is no longer proposed')
        _history(p, row, action)
        if action == 'assumption.reject':
            row['status'] = 'rejected'
        elif action == 'assumption.replace':
            row['text'] = _text(data['text'])
            row['provenance']['kind'] = 'USER_EDITED_SUGGESTION'
        else:
            text = data.get('text', row['text'])
            _text(text)
            row['status'] = 'accepted'
            row['provenance']['kind'] = 'USER_ACCEPTED_SUGGESTION'
            proposal = _record(text, row['dimension'], source_ids=[row['id']],
                provenance=_provenance('USER_ACCEPTED_SUGGESTION' if text == row['text'] else 'USER_EDITED_SUGGESTION', row['text']))
            _accept(p, proposal)
            branch['statements'].append(proposal)
    elif action == 'conflict.resolve':
        _keys(data, ('ids', 'resolution'), ('text', 'condition'))
        _strings(data['ids'], identifiers=True)
        _require(len(data['ids']) == 2 and len(set(data['ids'])) == 2, 'Resolve exactly two distinct statements')
        rows = [_find(branch['statements'], i) for i in data['ids']]
        _require(all(r['status'] == 'accepted' for r in rows), 'Conflict resolution requires accepted statements')
        resolution = data['resolution']
        _require(resolution in ('keep_first', 'keep_second', 'replace', 'conditional'), 'Unknown conflict resolution')
        if resolution == 'conditional':
            _text(data.get('condition'))
            _history(p, rows[1], action)
            rows[1]['condition'] = data['condition']
            if 'fact' in rows[1]:
                rows[1]['fact']['condition'] = data['condition']
        else:
            for i, row in enumerate(rows):
                if (resolution == 'keep_first' and i == 0) or (resolution == 'keep_second' and i == 1):
                    continue
                _history(p, row, action); row['status'] = 'removed'
            if resolution == 'replace':
                replacement = _record(_text(data.get('text')), rows[0]['dimension'], source_ids=data['ids'])
                _accept(p, replacement); branch['statements'].append(replacement)
    elif action == 'entity.propose':
        _keys(data, ('kind', 'entity')); _entity_propose(branch, data['kind'], data['entity'])
    elif action.startswith('entity.'):
        _keys(data, ('kind', 'id', 'changes') if action == 'entity.edit' else ('kind', 'id'))
        _require(data['kind'] in C.ENTITY_SCHEMAS, 'Unknown entity collection')
        row = _find(branch['entities'][data['kind']], data['id'])
        if action == 'entity.accept':
            _entity_contract(data['kind'], row); _accept(p, row)
        else:
            _history(p, row, action)
            if action == 'entity.edit':
                _keys(data['changes'], (), {'text', 'dimension'} | set(C.ENTITY_SCHEMAS[data['kind']]['fields']))
                row.update(deepcopy(data['changes'])); row['status'] = 'proposed'; row['provenance']['kind'] = 'USER_EDITED_SUGGESTION'
            else:
                row['status'] = 'rejected' if action == 'entity.reject' else 'removed'
    elif action == 'scope.set':
        _keys(data, ('collection', 'text')); _require(data['collection'] in branch['scope'], 'Unknown scope collection')
        text = _text(data['text'])
        # Moving a scope statement is explicit and leaves the previous state in store audit.
        for values in branch['scope'].values():
            if text in values:
                values.remove(text)
        branch['scope'][data['collection']].append(text)
    elif action == 'idea.park':
        _keys(data, ('text',)); branch['parked'].append({'id': _new('parked'), 'text': _text(data['text']), 'status': 'parked'})
    elif action == 'idea.promote':
        _keys(data, ('id',)); row = _find(branch['parked'], data['id'])
        _require(row['status'] == 'parked', 'Idea already promoted')
        row['status'] = 'proposed'; branch['statements'].append(_record(row['text'], source_ids=[row['id']]))
    elif action == 'vocabulary.add':
        _keys(data, ('name', 'aliases')); _text(data['name']); _strings(data['aliases'])
        branch['vocabulary'].append({'id': _new('vocabulary'), **deepcopy(data)})
    elif action == 'definition.add':
        _keys(data, ('term', 'text'), ('source_ids',)); _text(data['term']); _text(data['text'])
        branch['definitions'].append({'id': _new('definition'), 'source_ids': [], **deepcopy(data)})
    elif action == 'snapshot.create':
        _keys(data, ('name',)); _snapshot(p, data['name'])
    elif action == 'snapshot.restore':
        _keys(data, ('id',)); _require(data['id'] in p['snapshots'], 'Unknown snapshot')
        saved = deepcopy(p['snapshots'][data['id']])
        _snapshot(p, 'Before restoring ' + saved['name'])
        states = saved.get('branch_states', {saved['branch_id']: saved['branch']})
        for identifier, restored in states.items():
            if restored['validation']:
                restored['validation']['current'] = False
            p['branches'][identifier] = restored
        p['active_branch'] = saved['branch_id']
    elif action == 'branch.create':
        _keys(data, ('name',), ('snapshot_id',)); _text(data['name'], limit=120)
        sid = data.get('snapshot_id')
        if sid:
            _require(sid in p['snapshots'], 'Unknown snapshot')
        else:
            sid = _snapshot(p, 'Branch baseline: ' + data['name'])
        copied = deepcopy(p['snapshots'][sid]['branch'])
        identifier = _new('branch')
        copied.update(id=identifier, name=data['name'], parent_id=branch['id'], base_snapshot_id=sid)
        p['branches'][identifier] = copied; p['active_branch'] = identifier
    elif action == 'branch.switch':
        _keys(data, ('id',)); _require(data['id'] in p['branches'], 'Unknown branch'); p['active_branch'] = data['id']
    elif action == 'branch.merge':
        _keys(data, ('source_id', 'statement_ids')); _strings(data['statement_ids'], identifiers=True)
        _require(data['source_id'] in p['branches'] and data['source_id'] != branch['id'], 'Choose another source branch')
        for identifier in data['statement_ids']:
            row = _find(p['branches'][data['source_id']]['statements'], identifier)
            _require(row['status'] == 'accepted', 'Only accepted source decisions can be proposed for merge')
            fields = {k: deepcopy(v) for k, v in row.items() if k in STATEMENT_FIELDS and k != 'objective_ids'}
            _propose(p, branch, fields, provenance=_provenance('IMPORTED', row['text'], source_branch=data['source_id']))
    elif action == 'import.text':
        _keys(data, ('text',)); _propose(p, branch, {'text': _text(data['text'])}, kind='IMPORTED')
    elif action == 'model.artifact':
        _model_artifact(p, branch, data)
    elif action == 'model.artifacts':
        _keys(data, ('artifacts',))
        artifacts = _list(data['artifacts'], maximum=48)
        _require(bool(artifacts), 'Select at least one retained proposal')
        # All artifacts target the same original revision. One transaction imports
        # the selection, preserving independent sources without accepting any.
        for artifact in artifacts:
            _model_artifact(p, branch, artifact)
    elif action == 'coach.propose':
        from symblic.forge import coach as Coach
        preview = Coach.preview(p, data)
        _require(preview['complete'], 'Fill the explicit instruction, input, output, check and bounded context before proposing.')
        statement = _propose(p, branch, {'text': preview['after'], 'dimension': 'BEHAVIOR'},
                             source_ids=preview['source_ids'], provenance=_provenance('SYSTEM_DERIVED', preview['before']))
        if preview['construction'] is not None:
            unit = {**preview['construction'], 'requirement_ids': [statement['id']]}
            _entity_propose(branch, 'units', unit, source_ids=[statement['id'], *preview['source_ids']],
                            provenance=_provenance('SYSTEM_DERIVED', preview['before']))
    elif action == 'validation.record':
        _require(trusted is True, 'Only the host compiler may record validation')
        _keys(data, ('result',)); result = _json(data['result'])
        _require(type(result) is dict and type(result.get('ok')) is bool, 'Compiler result requires an explicit boolean')
        _require(result.get('fingerprint') == old_fingerprint, 'Compiler result is stale')
        _require(result.get('source_revision') == p['revision'], 'Compiler revision is stale')
        branch['validation'] = {**result, 'current': True, 'historical': False, 'stale': False}
    elif action == 'export.record':
        _require(trusted is True, 'Only the host may record exported bytes')
        _keys(data, ('artifact',)); artifact = deepcopy(data['artifact']); _validate_export(artifact)
        _require(artifact['fingerprint'] == old_fingerprint and artifact['source_revision'] == p['revision'], 'Export receipt is stale')
        _require(not any(r['id'] == artifact['id'] for r in p['exports']), 'Duplicate export identifier')
        artifact['historical'] = False; p['exports'].append(artifact)
    elif action == 'handoff.record':
        _require(trusted is True, 'Only the host may record execution handoff')
        _keys(data, ('handoff',)); handoff = deepcopy(data['handoff'])
        _require(type(handoff) is dict and handoff.get('fingerprint') == old_fingerprint, 'Handoff fingerprint is stale')
        _require(analyze(p)['readiness']['ready'], 'Handoff requires current readiness')
        handoff['historical'] = False; p['handoffs'].append(handoff)
    _expand_domains(p, active_branch(p))
    _refinement_questions(p, active_branch(p))
    current_branch = active_branch(p)
    if current_branch['id'] == prior_branch:
        current_decisions = {r['fact']['predicate'] for r in _accepted(current_branch) if r.get('fact')}
        for question in current_branch['questions']:
            if question['key'] in prior_decisions - current_decisions and question['status'] == 'answered':
                question['status'] = 'open'
    _invalidate(p, old_fingerprint)
    p['revision'] += 1
    return validate_project(p)


def _validate_export(row):
    _keys(row, ('id', 'kind', 'sha256', 'fingerprint', 'source_revision'), ('compileridentity', 'historical'))
    _id(row['id']); _text(row['kind'], limit=120)
    for key in ('sha256', 'fingerprint'):
        _require(type(row[key]) is str and re.fullmatch('[0-9a-f]{64}', row[key]), 'Invalid artifact digest')
    _require(type(row['source_revision']) is int and row['source_revision'] >= 0, 'Invalid export revision')
    if 'historical' in row:
        _require(type(row['historical']) is bool, 'Invalid artifact authority')
    if 'compileridentity' in row:
        _require(type(row['compileridentity']) in (str, dict), 'Invalid compiler identity')


def _conflicts(branch):
    records = _accepted(branch)
    groups = {}
    conflicts = []
    for row in records:
        fact = row.get('fact')
        if fact:
            key = (fact['subject'], fact['predicate'], fact.get('condition', row.get('condition', '')))
            groups.setdefault(key, []).append(row)
    for key, rows in groups.items():
        for index, first in enumerate(rows):
            for second in rows[index + 1:]:
                a, b = first['fact'], second['fact']
                if _canonical((a['value'], a.get('unit', ''))) != _canonical((b['value'], b.get('unit', ''))):
                    conflicts.append({'id': 'conflict_' + hashlib.sha256((first['id'] + second['id']).encode()).hexdigest()[:24],
                        'statement_ids': [first['id'], second['id']], 'severity': 'BLOCKING', 'kind': 'fact_disagreement',
                        'message': f"Different explicit values for {key[0]}.{key[1]} under the same condition.",
                        'condition': key[2], 'dimension': first['dimension']})
    return conflicts


def _graph(branch):
    records = _accepted(branch) + [r for k in C.ENTITY_SCHEMAS for r in _accepted(branch, k)]
    known = {r['id'] for r in records}
    nodes = [{'id': r['id'], 'label': r['text'], 'dimension': r['dimension']} for r in records]
    edges = []
    for row in records:
        for field, kind in [('objective_ids', 'objective'), ('requirement_ids', 'requirement'), ('dependencies', 'dependency'),
                            ('unit_ids', 'invariant-unit'), ('criterion_ids', 'invariant-check')]:
            for target in row.get(field, []):
                edges.append({'source': row['id'], 'target': target, 'kind': kind})
        if row.get('component_id'):
            edges.append({'source': row['id'], 'target': row['component_id'], 'kind': 'component'})
        if row.get('parent_objective_id'):
            edges.append({'source': row['id'], 'target': row['parent_objective_id'], 'kind': 'objective-parent'})
    for row in _accepted(branch, 'dependencies'):
        edges.append({'source': row['source'], 'target': row['target'], 'kind': row['kind']})
    # Only scheduling dependency edges establish build cycles, not traceability links.
    adjacent = {identifier: [] for identifier in known}
    for edge in edges:
        if edge['kind'] in ('dependency', 'build', 'data', 'control', 'runtime', 'objective-parent') and edge['source'] in adjacent:
            adjacent[edge['source']].append(edge['target'])
    # Iterative traversal avoids recursion failure on a valid, long unit chain.
    visiting, visited, cycles, order = set(), set(), [], []
    for identifier in sorted(known):
        if identifier in visited:
            continue
        stack = [(identifier, iter(adjacent.get(identifier, [])))]
        path = [identifier]
        visiting.add(identifier)
        while stack:
            node, targets = stack[-1]
            target = next(targets, None)
            if target is None:
                stack.pop(); path.pop(); visiting.discard(node); visited.add(node); order.append(node)
            elif target in visiting:
                cycle = path[path.index(target):] + [target]
                if cycle not in cycles:
                    cycles.append(cycle)
            elif target not in visited:
                visiting.add(target); path.append(target)
                stack.append((target, iter(adjacent.get(target, []))))
    return {'nodes': nodes, 'edges': edges, 'cycles': cycles, 'order': order,
            'dangling': [e for e in edges if e['source'] not in known or e['target'] not in known]}


def _derived(branch):
    """Only explicit structured numeric facts enter these partial checks."""
    facts = {}
    for row in _accepted(branch):
        if 'fact' in row and not row['fact'].get('condition', row.get('condition')):
            facts.setdefault(row['fact']['predicate'], []).append((row, row['fact']))
    derived = []
    def numeric(key):
        pairs = facts.get(key, [])
        # An unresolved alternative never becomes an arithmetic input by last-write wins.
        identities = {_canonical((fact['subject'], fact['value'], fact.get('unit'))) for _, fact in pairs}
        pair = pairs[0] if len(identities) == 1 else None
        if pair and type(pair[1]['value']) in (int, float) and math.isfinite(pair[1]['value']):
            return pair
        return None
    width, height = numeric('viewport.width'), numeric('viewport.height')
    if width and height and width[1]['subject'] == height[1]['subject'] and width[1].get('unit') == height[1].get('unit') == 'px':
        derived.append({'id': 'derived_viewport_area', 'text': 'Viewport area', 'value': width[1]['value'] * height[1]['value'],
            'unit': 'px²', 'source_ids': [width[0]['id'], height[0]['id']], 'provenance': 'SYSTEM_DERIVED', 'authoritative': False})
    scale = {'B': 1, 'KiB': 1024, 'MiB': 1024 ** 2, 'GiB': 1024 ** 3, 'TiB': 1024 ** 4,
             'kB': 1000, 'MB': 1000 ** 2, 'GB': 1000 ** 3, 'TB': 1000 ** 4}
    for resource in ('memory', 'storage'):
        needed, available = numeric(resource + '.required'), numeric(resource + '.available')
        if needed and available and needed[1]['subject'] == available[1]['subject']:
            a, b = needed[1], available[1]
            comparable = a.get('unit') == b.get('unit') and bool(a.get('unit'))
            if a.get('unit') in scale and b.get('unit') in scale:
                required, capacity = a['value'] * scale[a['unit']], b['value'] * scale[b['unit']]
                comparable = True
            else:
                required, capacity = a['value'], b['value']
            if comparable:
                derived.append({'id': 'derived_' + resource + '_feasibility', 'text': 'Explicit ' + resource + ' request fits explicit capacity',
                    'value': 0 <= required <= capacity, 'unit': 'B' if a.get('unit') in scale and b.get('unit') in scale else a['unit'],
                    'source_ids': [needed[0]['id'], available[0]['id']], 'provenance': 'SYSTEM_DERIVED', 'authoritative': False})
    inventories = [r for r in _accepted(branch, 'evidence') if r.get('evidence_type') == 'inventory' and r.get('inventory')]
    for model in _accepted(branch, 'models'):
        app = model['app']
        if not app.startswith('ollama:'):
            continue
        identity = app[len('ollama:'):]
        name, sep, node = identity.rpartition('@')
        if not sep:
            name, node = identity, ''
        for inventory in inventories:
            observed = inventory['inventory']
            nodes = [r for r in observed.get('nodes', []) if not node or r['id'] == node]
            names = set(observed.get('models', [])) if not node else set()
            for row in nodes:
                if row.get('online') is not False:
                    names.update(row['models'])
            present = name in names or app in names
            derived.append({'id': 'derived_model_' + model['id'] + '_' + inventory['id'],
                'text': 'Required model presence in explicitly attached inventory',
                'value': True if present else False if observed.get('complete') is True else None,
                'source_ids': [model['id'], inventory['id']], 'provenance': 'SYSTEM_DERIVED', 'authoritative': False,
                'scope': 'Captured accepted inventory only; current live availability is not asserted.'})
    for plan in _accepted(branch, 'cluster'):
        if not plan.get('node_id'):
            continue
        for inventory in inventories:
            node = next((r for r in inventory['inventory'].get('nodes', []) if r['id'] == plan['node_id']), None)
            if node is None:
                continue
            for resource in ('memory_bytes', 'storage_bytes'):
                if resource in plan and resource in node:
                    derived.append({'id': 'derived_inventory_capacity_' + resource + '_' + plan['id'] + '_' + inventory['id'],
                        'text': 'Explicit node resource request fits captured capacity',
                        'value': plan[resource] * plan.get('concurrency', 1) <= node[resource], 'unit': 'B',
                        'source_ids': [plan['id'], inventory['id']], 'provenance': 'SYSTEM_DERIVED', 'authoritative': False,
                        'scope': 'Per-job requirement multiplied by explicit concurrency; captured capacity is not a live reservation.'})
    return derived


def _unit_checks(branch):
    units = {r['id']: r for r in _accepted(branch, 'units')}
    results = []
    for identifier, row in units.items():
        available = set(row.get('inputs', [])) | set(row.get('defines', []))
        missing_dependencies = []
        for dep in row.get('dependencies', []):
            if dep in units:
                available.update(units[dep].get('outputs', []))
                available.update(units[dep].get('defines', []))
            else:
                missing_dependencies.append(dep)
        missing = sorted(set(row.get('requires', [])) - available)
        results.append({'id': identifier, 'ok': not missing and not missing_dependencies and bool(row.get('checks')),
            'missing_symbols': missing, 'missing_dependencies': missing_dependencies,
            'scope': 'Declared symbols and explicit unit dependencies only; no source execution or general prose proof.'})
    return results


def analyze(project):
    """Derived, non-authoritative views; checks never manufacture acceptance."""
    p = validate_project(project)
    branch = active_branch(p)
    accepted = _accepted(branch)
    entities = {k: _accepted(branch, k) for k in C.ENTITY_SCHEMAS}
    conflicts = _conflicts(branch)
    graph = _graph(branch)
    unit_checks = _unit_checks(branch)
    accepted_keys = {r['fact']['predicate'] for r in accepted if r.get('fact')}
    accepted_by_id = {r['id']: r for r in accepted}
    excluded = branch['not_applicable']
    questions = []
    for original in branch['questions']:
        q = deepcopy(original)
        q['applicable'] = q['dimension'] in branch['active_dimensions'] and q['dimension'] not in excluded
        q['decision_accepted'] = q['key'] in accepted_keys
        if q['key'].startswith('units.'):
            row = accepted_by_id.get(q['key'][len('units.'):])
            q['decision_accepted'] = bool(row and row.get('fact', {}).get('unit'))
        elif q['key'].startswith('clarify.'):
            _, identifier, word = q['key'].split('.', 2)
            row = accepted_by_id.get(identifier)
            if row and not re.search(r'\b' + re.escape(word) + r'\b', row['text'], re.I):
                q['decision_accepted'] = True
        q['waiting_for'] = [key for key in q['depends_on'] if key not in accepted_keys]
        questions.append(q)
    rank = {severity: i for i, severity in enumerate(C.SEVERITIES)}
    candidates = [q for q in questions if q['applicable'] and q['status'] in ('open', 'active') and not q['waiting_for']]
    mode = branch['mode']
    snake = 'snake' in p['original_idea'].lower()
    precision_dimensions = {'UNITS', 'PHYSICAL_DIMENSIONS', 'POWER', 'PERFORMANCE', 'ACCEPTANCE', 'VIEWPORT', 'FRAME_TIMING'}
    def priority(q):
        special = 0 if snake and q['key'] == 'rendering' else 1
        if mode == 'PRECISION':
            special = 0 if q['dimension'] in precision_dimensions else 1
        elif mode == 'EXPLORE':
            special = 0 if q['suggestion_ids'] else 1
        elif mode == 'CHALLENGE':
            special = 0 if q['key'].startswith('challenge.') else 1
        return (q['status'] != 'active', special, rank[q['severity']], not q['mandatory'], q['key'])
    candidates.sort(key=priority)
    next_question = deepcopy(candidates[0]) if candidates else None
    presentation_questions = deepcopy(candidates[:5 if mode == 'RAPID' else 3 if mode in ('EXPLORE', 'CHALLENGE') else 1])
    if conflicts:
        conflict = conflicts[0]
        next_question = {'id': conflict['id'], 'kind': 'conflict', 'text': conflict['message'],
                         'statement_ids': conflict['statement_ids'], 'severity': 'BLOCKING', 'dimension': conflict['dimension']}
        presentation_questions = [deepcopy(next_question)]
    criteria_coverage = {r['id']: [c['id'] for c in entities['criteria'] if r['id'] in c.get('requirement_ids', [])] for r in accepted}
    objective_ids = {r['id'] for r in entities['objectives']}
    traceability = []
    orphans = []
    for row in accepted:
        objectives = [i for i in row.get('objective_ids', []) if i in objective_ids]
        item = {'requirement_id': row['id'], 'objective_ids': objectives, 'criterion_ids': criteria_coverage[row['id']],
            'component_ids': [r['id'] for r in entities['components'] if row['id'] in r.get('requirement_ids', [])],
            'unit_ids': [r['id'] for r in entities['units'] if row['id'] in r.get('requirement_ids', [])],
            'evidence_ids': [r['id'] for r in entities['evidence'] if row['id'] in r.get('requirement_ids', [])]}
        traceability.append(item)
        if not objectives:
            orphans.append({'id': row['id'], 'kind': 'requirement_without_objective'})
        if row.get('mandatory', True) and not item['criterion_ids']:
            orphans.append({'id': row['id'], 'kind': 'mandatory_requirement_without_criterion'})
    for kind in ('architectures', 'components', 'units', 'agents', 'models', 'cluster', 'invariants', 'forbidden'):
        for row in entities[kind]:
            if not row.get('requirement_ids'):
                orphans.append({'id': row['id'], 'kind': kind + '_without_requirement'})
    unresolved = [q for q in questions if q['applicable'] and (q['mandatory'] or q['severity'] == 'BLOCKING')
                  and not q['decision_accepted'] and q['status'] != 'dismissed']
    blockers = []
    def block(code, message, ids=()):
        blockers.append({'code': code, 'message': message, 'source_ids': list(ids)})
    if not entities['objectives']:
        block('objectives', 'Accept at least one explicit objective.')
    if not accepted:
        block('requirements', 'Accept explicit atomic requirements.')
    if unresolved:
        block('questions', 'Mandatory decisions remain unanswered or unaccepted.', [q['id'] for q in unresolved])
    if conflicts:
        block('conflicts', 'Resolve conflicting accepted facts.', [i for c in conflicts for i in c['statement_ids']])
    for orphan in orphans:
        if orphan['kind'] in ('requirement_without_objective', 'mandatory_requirement_without_criterion', 'units_without_requirement'):
            block(orphan['kind'], 'Link this requirement to an objective and an observable acceptance criterion.', [orphan['id']])
    if graph['cycles']:
        block('dependency_cycle', 'Resolve cyclic build/runtime dependencies.', [i for c in graph['cycles'] for i in c])
    if graph['dangling']:
        block('unaccepted_dependency', 'Accept referenced dependencies before readiness.', [e['target'] for e in graph['dangling']])
    for check in unit_checks:
        if not check['ok']:
            block('unit_isolation', 'An isolated unit has undeclared inputs, dependencies or checks.', [check['id']])
    for row in entities['architectures']:
        if row.get('unresolved'):
            block('architecture_unresolved', 'Resolve selected architecture questions.', [row['id']])
    for row in entities['invariants']:
        if not row.get('unit_ids') or not row.get('criterion_ids'):
            block('invariant_coverage', 'Link each global invariant to affected units and observable criteria.', [row['id']])
    for row in entities['forbidden']:
        if not row.get('negative_check'):
            block('forbidden_check', 'Define a negative check for each forbidden behavior.', [row['id']])
    if not entities['units']:
        block('construction_units', 'Accept verified construction units before planning is ready.')
    for result in _derived(branch):
        if (result['id'] in ('derived_memory_feasibility', 'derived_storage_feasibility') or result['id'].startswith('derived_inventory_capacity_')) and result['value'] is False:
            block('resource_capacity', 'Explicit requested memory/storage exceeds explicit available capacity.', result['source_ids'])
        if result['id'].startswith('derived_model_') and result['value'] is False:
            block('required_model_unavailable', 'An accepted required model is absent from the accepted complete inventory snapshot.', result['source_ids'])
    receipt = branch['validation']
    compiler_current = bool(receipt and receipt.get('ok') is True and receipt.get('current') is True
        and receipt.get('generated') is True
        and not receipt.get('historical') and not receipt.get('stale') and receipt.get('fingerprint') == fingerprint(p))
    completeness = []
    for dimension in branch['active_dimensions']:
        qs = [q for q in questions if q['dimension'] == dimension]
        count = sum(q['decision_accepted'] for q in qs)
        completeness.append({'dimension': dimension, 'accepted_decisions': count, 'questions': len(qs),
            'open': sum(q['applicable'] and not q['decision_accepted'] and q['status'] != 'dismissed' for q in qs),
            'not_applicable': dimension in excluded, 'reason': excluded.get(dimension, '')})
    construction = []
    for unit in entities['units']:
        construction.append({'id': unit['id'], 'Name': unit['text'], 'Requirement': unit['objective'],
            'Use only': list(unit['inputs']) + list(unit['dependencies']), 'Check': list(unit['checks']),
            'Finish': list(unit['outputs']), 'forbidden_assumptions': unit.get('forbidden_assumptions', [])})
    return {'counts': {'accepted': len(accepted), 'proposed': sum(r['status'] == 'proposed' for r in branch['statements']),
             'questions': len(questions), 'unresolved': len(unresolved), 'conflicts': len(conflicts), 'units': len(entities['units'])},
        'questions': questions, 'next_question': next_question, 'presentation_questions': presentation_questions,
        'mode': mode, 'conflicts': conflicts, 'derived': _derived(branch),
        'completeness': completeness, 'readiness': {'ready': not blockers, 'blockers': blockers,
            'summary': {'blocking_ambiguities': sum(q['severity'] == 'BLOCKING' for q in unresolved),
                'high_ambiguities': sum(q['applicable'] and q['severity'] == 'HIGH' and not q['decision_accepted'] and q['status'] != 'dismissed' for q in questions),
                'contradictions': len(conflicts), 'missing_criteria': sum(o['kind'] == 'mandatory_requirement_without_criterion' for o in orphans),
                'failed_units': sum(not row['ok'] for row in unit_checks)},
            'compiler_current': compiler_current, 'scope': 'Structural design readiness; compiler validity is a separate host receipt.'},
        'graph': graph, 'traceability': traceability, 'orphans': orphans, 'unit_checks': unit_checks,
        'construction_units': construction, 'accepted_prompt': '\n'.join(requirement_text(r) for r in accepted),
        'analysis_scope': 'Explicit structured facts, declared links and contracts. Free-form semantic completeness requires review.'}


def export_manifest(project):
    p = validate_project(project)
    return {'format': 'symblic-forge-manifest/1', 'project': p, 'fingerprint': fingerprint(p)}


def import_manifest(value):
    value = _json(value)
    _keys(value, ('format', 'project', 'fingerprint'))
    _require(value['format'] == 'symblic-forge-manifest/1', 'Unsupported manifest format')
    project = validate_project(value['project'])
    _require(value['fingerprint'] == fingerprint(project), 'Manifest semantic fingerprint mismatch')
    # A browser-supplied receipt is history, never proof from this host compiler.
    branches = list(project['branches'].values()) + [s['branch'] for s in project['snapshots'].values()]
    branches += [b for s in project['snapshots'].values() for b in s.get('branch_states', {}).values()]
    for branch in branches:
        if branch['validation'] is not None:
            branch['validation'].update(current=False, historical=True)
        if branch['lifecycle'] in ('READY', 'EXPORTED', 'EXECUTION_TRANSFERRED'):
            branch['lifecycle'] = 'DEFINING'
    for row in project['exports'] + project['handoffs']:
        row['historical'] = True
    return validate_project(project)


def compare_branches(project, first_id, second_id):
    p = validate_project(project)
    _require(first_id in p['branches'] and second_id in p['branches'], 'Unknown comparison branch')
    left, right = p['branches'][first_id], p['branches'][second_id]
    def by_content(rows):
        return {_canonical({k: v for k, v in row.items() if k in STATEMENT_FIELDS}): row['id'] for row in rows}
    a, b = by_content(_accepted(left)), by_content(_accepted(right))
    merged = deepcopy(left)
    merged['statements'] = _accepted(left) + _accepted(right)
    def entity_content(rows):
        return sorted([{k: v for k, v in row.items() if k not in {'id', 'provenance', 'revisions', 'source_ids'}} for row in rows], key=_canonical)
    return {'first_id': first_id, 'second_id': second_id, 'common': [{'first': a[k], 'second': b[k]} for k in sorted(a.keys() & b.keys())],
        'only_first': [a[k] for k in sorted(a.keys() - b.keys())], 'only_second': [b[k] for k in sorted(b.keys() - a.keys())],
        'conflicts': _conflicts(merged), 'entities': {kind: {'first': _accepted(left, kind), 'second': _accepted(right, kind),
        'different': entity_content(_accepted(left, kind)) != entity_content(_accepted(right, kind))}
        for kind in ('architectures', 'agents', 'cluster', 'criteria')}}


def search(project, query):
    p = validate_project(project)
    term = _text(query, limit=1000).casefold()
    result = []
    for branch in p['branches'].values():
        collections = {key: branch[key] for key in ('statements', 'questions', 'answers', 'assumptions', 'parked', 'definitions')}
        collections.update(branch['entities'])
        for kind, rows in collections.items():
            for row in rows:
                if term in _canonical(row).casefold():
                    result.append({'branch_id': branch['id'], 'kind': kind, 'id': row['id'], 'text': row['text'], 'status': row.get('status', '')})
    return result


def snake_demo(*, project_id=None):
    """Explicit sample decisions, not a game, live test, or default interpretation."""
    p = new_project('I want to create a simple snake game',
                    'Snake demonstration — explicit example decisions', 'game', project_id=project_id)
    branch = active_branch(p)
    objective = _entity_propose(branch, 'objectives', {'text': 'Demonstration objective: specify a reproducible browser Snake game before implementing it.',
                                                    'measure': 'Every chosen rule has an observable acceptance criterion.'})
    _accept(p, objective)
    decisions = {
        'purpose': 'Provide a single-player grid Snake game as a specification example; this project does not contain the game implementation.',
        'behavior': 'On each simulation tick move the snake one grid cell in its current direction, apply food growth and then evaluate the end conditions.',
        'platform': 'Run the future game in a modern browser with JavaScript and HTML; installation and external services are unnecessary.',
        'acceptance': 'Complete the explicitly listed observable rule, rendering, control, restart and isolation checks before accepting an implementation.',
        'rendering': 'Render the game with HTML canvas 2D using minimal solid-color rectangles; do not use a game engine or external assets.',
        'viewport.width': 'The canvas viewport width is exactly 800 pixels.',
        'viewport.height': 'The canvas viewport height is exactly 600 pixels.',
        'game.world': 'Use a 40-column by 30-row rectangular grid with square cells measuring 20 pixels on each side.',
        'game.start': 'Show a start screen with the title, controls and Start button; the snake remains stationary until play begins.',
        'game.start_control': 'Start play with Enter or the Start button.',
        'game.initial': 'Start with three horizontal segments at grid cells (20,15), (19,15), (18,15), with the head moving right.',
        'game.keys': 'Use arrow keys and WASD; ignore immediate reversal into the current neck and consume at most one direction change per simulation tick.',
        'game.movement': 'Move exactly one cell per fixed simulation tick; rendering refresh does not determine the simulation speed.',
        'game.interval': 'Use a fixed simulation interval of 150 milliseconds.',
        'game.food': 'Place exactly one food cell on an unoccupied grid cell using an injected random-number source; declare victory when no unoccupied cell remains.',
        'game.growth': 'Collecting food adds one segment by retaining the previous tail during that simulation tick.',
        'game.score': 'Start the score at zero and add exactly one point per collected food cell.',
        'game.wall': 'Crossing any grid boundary ends the run as a loss; boundaries do not wrap.',
        'game.body': 'Moving into an occupied body cell ends the run as a loss; moving into the tail cell is allowed only when that tail moves away on the same non-growth tick.',
        'game.end': 'On loss or full-grid victory, stop simulation, display the outcome and final score, and keep the board visible.',
        'game.restart': 'Restart returns score, snake, direction, pending input and food to a valid new-run state; remove the previous timer before starting another.',
        'agents': 'This example proposes separate logic, rendering/input and verification construction responsibilities; no agent is launched by loading the example.',
        'cluster': 'These construction units may use one admitted machine or independent admitted nodes under the same artifact revision; node/model selection remains an explicit execution choice.',
        'background': 'Use a black background, green snake, red food and white score text with visible contrast.',
        'game.random': 'Permit food randomness through an injected random-number source.',
        'game.seed': 'Use a deterministic seeded random-number fixture for repeatable rule tests; gameplay may use a fresh seed.',
        'game.persistence': 'Do not persist score or game state after closing the page.',
        'game.pause': 'Provide a Pause/Resume control that suspends simulation without resetting score or snake state.',
        'game.touch': 'Provide labelled directional touch buttons with targets at least 44 CSS pixels wide and tall.',
    }
    for key, text in decisions.items():
        q = next(q for q in branch['questions'] if q['key'] == key)
        _answer(p, branch, q, text)
        row = branch['statements'][-1]
        row['objective_ids'] = [objective['id']]
        row['provenance']['kind'] = 'IMPORTED'
        row['provenance']['original_text'] = 'Explicit Snake demonstration decision: ' + text
        if key in ('viewport.width', 'viewport.height', 'game.interval'):
            row['fact'].update(value={'viewport.width': 800, 'viewport.height': 600, 'game.interval': 150}[key],
                               unit='ms' if key == 'game.interval' else 'px')
        _accept(p, row)
        criterion = _entity_propose(branch, 'criteria', {'text': 'Check example decision: ' + key,
            'requirement_ids': [row['id']], 'observable': text,
            'measurement': 'Inspect the implementation and run a deterministic fixture for this exact stated behavior.',
            'expected': 'The observation matches every value and condition in the linked example decision.'})
        _accept(p, criterion)
    reqs = [r['id'] for r in _accepted(branch)]
    components = []
    for name, responsibility, inputs, outputs in [
            ('Rules', 'Advance deterministic Snake state independently of rendering and real time.', ['state', 'direction', 'random_value'], ['next_state']),
            ('Interface', 'Render accepted state and translate keyboard/touch controls into bounded input.', ['state', 'control_event'], ['direction', 'frame']),
            ('Verification', 'Check chosen game rules and browser interactions with explicit fixtures.', ['next_state', 'frame'], ['check_results'])]:
        row = _entity_propose(branch, 'components', {'text': name, 'responsibility': responsibility,
            'inputs': inputs, 'outputs': outputs, 'requirement_ids': reqs, 'dependencies': [], 'persistent_state': 'None outside an active game session.', 'effects': []})
        _accept(p, row); components.append(row)
    unit_ids = []
    for index, component in enumerate(components):
        dependencies = unit_ids[:1] if index else []
        row = _entity_propose(branch, 'units', {'text': 'Implement and check ' + component['text'].lower(),
            'component_id': component['id'], 'requirement_ids': reqs, 'objective': component['responsibility'],
            'inputs': component['inputs'], 'outputs': component['outputs'], 'dependencies': dependencies,
            'checks': ['Verify every linked acceptance criterion relevant to this component with deterministic fixtures; report actual results.'],
            'forbidden_assumptions': ['Do not infer new gameplay rules, external services, agent permissions or node placement.'],
            'defines': component['outputs'], 'requires': component['inputs'], 'paths': []})
        _accept(p, row); unit_ids.append(row['id'])
    architecture = _entity_propose(branch, 'architectures', {'text': 'Example architecture: deterministic state reducer with separate canvas/input and verification components.',
        'requirement_ids': reqs, 'components': [r['text'] for r in components],
        'tradeoffs': ['Canvas gives explicit pixel geometry; accessibility uses labelled surrounding DOM controls.',
                     'A fixed simulation clock makes rules reproducible while rendering remains independently scheduled.'], 'unresolved': []})
    _accept(p, architecture)
    branch['scope']['in_scope'] = ['Specified Snake gameplay, canvas rendering, accessible controls and isolated verification.']
    branch['scope']['out_of_scope'] = ['Multiplayer, cloud accounts, remote score storage, automatic model or agent execution.']
    branch['not_applicable'].update({'AUDIO_DESIGN': 'The example explicitly contains no audio.',
        'HARDWARE': 'No specialized hardware beyond a browser input/display device is required.'})
    branch['lifecycle'] = 'PLANNING'
    _snapshot(p, 'Explicit accepted Snake example plan')
    return validate_project(p)
