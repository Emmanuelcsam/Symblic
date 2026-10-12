"""Experiments: replay of message/resource event ledgers and inert compensation planning.

Research experiment, no result claimed. Stateless replay of a caller-supplied ordered ledger: nothing is
delivered, leased or compensated, and evidence hashes are caller-declared, not verified outcomes.

Experiments:
    revision-acknowledgements  replay receive/ack records and list recipients still missing the current revision
    one-use-resources          replay ownership transfers; an interrupted consumption stays fenced as uncertain
    saga-compensation-plan     link original and compensation identities in reverse dependency order, keeping
                               unknown outcomes unknown (after Garcia-Molina and Salem, Sagas, 1987)

Depends on: the standard library only. Run through ``symblic.experiments.registry``.
"""
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from copy import deepcopy
import json
import re

VERSION = 1
MAX_EVENTS = 256
MAX_ENTITIES = 16
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,47}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
SOURCES = [{'title': 'Existing Symblic effect identity and recovery contract', 'path': 'docs/reference/EFFECTS.md'},
           {'title': 'Existing graph intent/outcome recovery contract', 'path': 'docs/reference/AGENT-GRAPHS.md'}]
SAGA_SOURCE = {'title': 'Garcia-Molina and Salem, Sagas (1987)',
               'url': 'https://www.cs.princeton.edu/research/techreps/598',
               'scope': 'Primary compensation/logging reference; this adapter computes an inert finite plan, not a database transaction guarantee.'}
LIMITS = ['Stateless replay of a caller-supplied ordered ledger; no persistence, authentication or proof of external delivery.',
          'Event IDs identify exact content. Erased or invented histories and aliases for the same real resource cannot be detected.',
          'At most 256 input events, 16 logical messages/resources/steps, and eight recipients or prerequisites.',
          'All plans are inert data. No messages, resource leases, host calls or compensation actions are performed.',
          'Evidence hashes are caller-declared references, not independently verified external outcomes.']


def _fail(code):
    raise ValueError(code)


def _sources(experiment_id):
    return deepcopy(SOURCES + ([SAGA_SOURCE] if experiment_id == 'saga-compensation-plan' else []))


def _bounded(value, maximum):
    size = count = 0
    active = set()
    def visit(item, depth):
        nonlocal size, count
        count += 1
        if count > 20000 or depth > 16:
            _fail('structure_bound')
        typ = type(item)
        if typ in (dict, list):
            if len(item) > 512 or id(item) in active:
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
            if item.bit_length() > 128:
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


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        _fail('digest')
    return value


def _integer(value, low=1, high=1000000):
    if type(value) is not int or not low <= value <= high:
        _fail('integer_bound')
    return value


def _names(value, low=0, high=8):
    if type(value) is not list or not low <= len(value) <= high:
        _fail('name_list_bound')
    result = [_id(x) for x in value]
    if len(set(result)) != len(result):
        _fail('duplicate_name')
    return result


def _events(value):
    if type(value) is not list or len(value) > MAX_EVENTS:
        _fail('event_bound')
    seen, rows, duplicates = {}, [], []
    for row in value:
        if type(row) is not dict or 'id' not in row or 'kind' not in row:
            _fail('event_schema')
        ident = _id(row['id']); _id(row['kind'])
        encoded = json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        if ident in seen:
            if encoded != seen[ident]:
                _fail('event_id_conflict')
            duplicates.append(ident)
        else:
            seen[ident] = encoded; rows.append(deepcopy(row))
    return rows, {'unique_events': len(rows), 'duplicate_events': len(duplicates), 'duplicate_ids': duplicates}


def _acknowledgements(data):
    _fields(data, 'events')
    events, replay = _events(data['events'])
    messages, received, acks = {}, {}, []
    for row in events:
        kind = row['kind']
        fields = {'publish': 'id kind message revision digest recipients',
                  'receive': 'id kind message revision digest recipient',
                  'ack': 'id kind message revision digest recipient receipt'}
        if kind not in fields:
            _fail('ack_event_kind')
        _fields(row, fields[kind]); message = _id(row['message'])
        revision = _integer(row['revision']); digest = _sha(row['digest'])
        if kind == 'publish':
            recipients = _names(row['recipients'], 1)
            if message not in messages:
                if len(messages) >= MAX_ENTITIES:
                    _fail('message_bound')
                messages[message] = {}
            versions = messages[message]
            if revision != len(versions)+1:
                _fail('revision_order')
            versions[revision] = {'digest': digest, 'recipients': recipients}
            continue
        recipient = _id(row['recipient'])
        published = messages.get(message, {}).get(revision)
        if not published or digest != published['digest'] or recipient not in published['recipients']:
            _fail('revision_tuple_not_published')
        identity = (message, revision, digest, recipient)
        if kind == 'receive':
            received[row['id']] = identity
        else:
            receipt = _id(row['receipt'])
            if received.get(receipt) != identity:
                _fail('ack_without_matching_receive')
            acks.append({'event': row['id'], 'message': message, 'revision': revision,
                         'digest': digest, 'recipient': recipient, 'receipt': receipt})
    current, stale = [], []
    for message in sorted(messages):
        revision = len(messages[message]); published = messages[message][revision]
        acked = {row['recipient'] for row in acks if row['message'] == message and row['revision'] == revision}
        missing = [recipient for recipient in published['recipients'] if recipient not in acked]
        current.append({'message': message, 'revision': revision, **published,
                        'acknowledged': sorted(acked), 'missing': missing, 'complete': not missing})
    for row in acks:
        if row['revision'] != len(messages[row['message']]):
            stale.append(row)
    return {'current_messages': current, 'acknowledgements': acks, 'stale_acknowledgements': stale,
            'receive_records': len(received), 'replay': replay,
            'all_current_revisions_acknowledged': all(row['complete'] for row in current)}, \
           {'acks_have_prior_exact_receive': True, 'stale_acks_excluded_from_current': True,
            'event_ids_exactly_idempotent': True}


def _resources(data):
    _fields(data, 'events')
    events, replay = _events(data['events'])
    resources, attempts = {}, {}
    schemas = {'issue': 'id kind resource branch owner',
               'transfer': 'id kind resource from_branch from_owner to_branch to_owner expected_revision',
               'consume_intent': 'id kind resource branch owner expected_revision attempt',
               'consume_result': 'id kind resource attempt outcome evidence',
               'resolve': 'id kind resource attempt outcome evidence'}
    for row in events:
        kind = row['kind']
        if kind not in schemas:
            _fail('resource_event_kind')
        _fields(row, schemas[kind]); resource = _id(row['resource'])
        if kind == 'issue':
            if resource in resources:
                _fail('resource_reissued')
            if len(resources) >= MAX_ENTITIES:
                _fail('resource_bound')
            resources[resource] = {'resource': resource, 'branch': _id(row['branch']),
                'owner': _id(row['owner']), 'revision': 1, 'state': 'issued',
                'available_state': 'issued', 'attempt': None, 'history': [row['id']]}
            continue
        if resource not in resources:
            _fail('resource_not_issued')
        state = resources[resource]
        if kind in ('transfer', 'consume_intent'):
            expected = _integer(row['expected_revision'])
            if expected != state['revision']:
                _fail('resource_revision_mismatch')
            if state['state'] not in ('issued', 'transferred'):
                _fail('resource_unavailable')
            branch_key, owner_key = ('from_branch', 'from_owner') if kind == 'transfer' else ('branch', 'owner')
            if (_id(row[branch_key]), _id(row[owner_key])) != (state['branch'], state['owner']):
                _fail('resource_owner_mismatch')
            if kind == 'transfer':
                target = (_id(row['to_branch']), _id(row['to_owner']))
                if target == (state['branch'], state['owner']):
                    _fail('transfer_same_owner')
                state.update(branch=target[0], owner=target[1], state='transferred', available_state='transferred')
            else:
                attempt = _id(row['attempt'])
                if attempt in attempts:
                    _fail('attempt_id_reused')
                attempts[attempt] = {'resource': resource, 'branch': state['branch'], 'owner': state['owner'],
                                     'outcome': 'unknown', 'intent': row['id'], 'receipts': []}
                state.update(state='uncertain', attempt=attempt)
        else:
            attempt = _id(row['attempt']); outcome = row['outcome']; _sha(row['evidence'])
            if outcome not in (('consumed', 'not_consumed') if kind == 'resolve' else ('consumed', 'not_consumed', 'unknown')):
                _fail('resource_outcome')
            if state['state'] != 'uncertain' or state['attempt'] != attempt:
                _fail('outcome_without_pending_attempt')
            attempts[attempt]['outcome'] = outcome
            attempts[attempt]['receipts'].append({'event': row['id'], 'kind': kind, 'outcome': outcome, 'evidence': row['evidence']})
            if outcome != 'unknown':
                state.update(state='consumed' if outcome == 'consumed' else state['available_state'], attempt=None)
        state['revision'] += 1; state['history'].append(row['id'])
    rows = []
    for key in sorted(resources):
        state = resources[key]
        rows.append({**state, 'may_plan_new_use': state['state'] in ('issued', 'transferred'),
                     'automatic_redispatch': False})
    return {'resources': rows, 'attempts': attempts, 'replay': replay,
            'uncertain_resources': [row['resource'] for row in rows if row['state'] == 'uncertain']}, \
           {'one_owner_per_logical_resource': True, 'unknown_attempts_block_new_use': True,
            'consumed_resources_not_reissued': True, 'event_ids_exactly_idempotent': True}


def _steps(value):
    if type(value) is not list or not 1 <= len(value) <= MAX_ENTITIES:
        _fail('step_bound')
    steps, compensation_ids = {}, set()
    for row in value:
        _fields(row, 'id compensation requires')
        step, compensation = _id(row['id']), _id(row['compensation'])
        if step in steps or compensation in compensation_ids:
            _fail('duplicate_step_or_compensation')
        steps[step] = {'compensation': compensation, 'requires': _names(row['requires'])}
        compensation_ids.add(compensation)
    if set(steps) & compensation_ids:
        _fail('original_compensation_id_overlap')
    for step, row in steps.items():
        if step in row['requires'] or not set(row['requires']) <= set(steps):
            _fail('step_dependency')
    pending, ordered = set(steps), []
    while pending:
        ready = sorted(step for step in pending if set(steps[step]['requires']) <= set(ordered))
        if not ready:
            _fail('step_cycle')
        ordered.extend(ready); pending.difference_update(ready)
    return steps, ordered


def _saga(data):
    _fields(data, 'steps events rollback')
    if type(data['rollback']) is not bool:
        _fail('rollback_boolean')
    steps, order = _steps(data['steps'])
    events, replay = _events(data['events'])
    states = {step: {'forward': 'pending', 'compensate': 'pending', 'forward_attempt': None,
                     'compensate_attempt': None} for step in steps}
    dependents = {step: sorted(other for other, row in steps.items() if step in row['requires']) for step in steps}
    attempts, rolling = {}, False

    def compensation_blockers(step):
        blocked = []
        for child in dependents[step]:
            child_state = states[child]
            if child_state['forward'] == 'uncertain':
                blocked.append({'step': child, 'reason': 'dependent_original_unknown'})
            elif child_state['forward'] == 'done' and child_state['compensate'] != 'done':
                blocked.append({'step': child, 'reason': 'dependent_not_compensated'})
        return blocked

    for row in events:
        kind = row['kind']
        if kind not in ('intent', 'outcome', 'resolve'):
            _fail('saga_event_kind')
        _fields(row, 'id kind step action attempt' if kind == 'intent' else 'id kind step action attempt outcome evidence')
        step, action, attempt = (_id(row[key]) for key in ('step', 'action', 'attempt'))
        if step not in steps:
            _fail('unknown_step')
        if action == step:
            operation = 'forward'
        elif action == steps[step]['compensation']:
            operation = 'compensate'
        else:
            _fail('action_link_mismatch')
        state = states[step]; pending_key = operation+'_attempt'
        if kind == 'intent':
            if attempt in attempts:
                _fail('attempt_id_reused')
            if state[operation] not in ('pending', 'not_done'):
                _fail('action_not_ready')
            if operation == 'forward':
                if rolling:
                    _fail('forward_after_rollback')
                if any(states[parent]['forward'] != 'done' for parent in steps[step]['requires']):
                    _fail('forward_prerequisite')
            else:
                if state['forward'] != 'done':
                    _fail('compensation_without_done_original')
                if compensation_blockers(step):
                    _fail('compensation_dependency')
                rolling = True
            state[operation] = 'uncertain'; state[pending_key] = attempt
            attempts[attempt] = {'step': step, 'action': action, 'operation': operation,
                                 'intent': row['id'], 'outcome': 'unknown', 'receipts': []}
        else:
            outcome = row['outcome']; _sha(row['evidence'])
            if outcome not in (('done', 'not_done') if kind == 'resolve' else ('done', 'not_done', 'unknown')):
                _fail('saga_outcome')
            if state[operation] != 'uncertain' or state[pending_key] != attempt:
                _fail('outcome_without_pending_attempt')
            attempts[attempt]['outcome'] = outcome
            attempts[attempt]['receipts'].append({'event': row['id'], 'kind': kind,
                                                 'outcome': outcome, 'evidence': row['evidence']})
            if outcome != 'unknown':
                state[operation] = outcome; state[pending_key] = None
    rollback = data['rollback'] or rolling
    plan, blocked, rows = [], [], []
    for step in order:
        state = states[step]
        rows.append({'step': step, 'compensation': steps[step]['compensation'],
                     'requires': steps[step]['requires'], **state})
    if rollback:
        for step in reversed(order):
            state = states[step]
            if state['forward'] == 'uncertain':
                blocked.append({'step': step, 'reason': 'original_outcome_unknown', 'attempt': state['forward_attempt']})
            elif state['forward'] == 'done' and state['compensate'] != 'done':
                reasons = compensation_blockers(step)
                if state['compensate'] == 'uncertain':
                    blocked.append({'step': step, 'reason': 'compensation_outcome_unknown', 'attempt': state['compensate_attempt']})
                elif reasons:
                    blocked.append({'step': step, 'reason': 'dependencies_uncompensated', 'dependencies': reasons})
                else:
                    plan.append({'original_id': step, 'compensation_id': steps[step]['compensation'],
                        'requires_compensations': [steps[child]['compensation'] for child in dependents[step]
                                                   if states[child]['forward'] == 'done'],
                        'needs_new_attempt_id': True, 'inert': True})
    unknown = [{'step': step, 'operation': operation, 'attempt': state[operation+'_attempt']}
               for step, state in states.items() for operation in ('forward', 'compensate')
               if state[operation] == 'uncertain']
    return {'steps': rows, 'attempts': attempts, 'replay': replay, 'rollback_requested': data['rollback'],
            'rollback_started': rolling, 'rollback_active': rollback,
            'reverse_dependency_order': [{'original_id': step, 'compensation_id': steps[step]['compensation']}
                                         for step in reversed(order)],
            'ready_compensations': plan, 'blocked_compensations': blocked, 'uncertain_attempts': unknown,
            'automatic_redispatch': False,
            'rollback_complete': rollback and not unknown and all(state['forward'] != 'done' or state['compensate'] == 'done'
                                                                 for state in states.values())}, \
           {'compensations_link_exact_originals': True, 'reverse_dependencies_enforced': True,
            'unknown_intents_not_redispatched': True, 'event_ids_exactly_idempotent': True}


def catalog():
    digest = '1'*64
    ack = {'events': [
        {'id': 'Publish1', 'kind': 'publish', 'message': 'Task', 'revision': 1, 'digest': digest, 'recipients': ['Worker']},
        {'id': 'Receive1', 'kind': 'receive', 'message': 'Task', 'revision': 1, 'digest': digest, 'recipient': 'Worker'},
        {'id': 'Ack1', 'kind': 'ack', 'message': 'Task', 'revision': 1, 'digest': digest, 'recipient': 'Worker', 'receipt': 'Receive1'},
        {'id': 'Publish2', 'kind': 'publish', 'message': 'Task', 'revision': 2, 'digest': '2'*64, 'recipients': ['Worker']}]}
    resource = {'events': [
        {'id': 'Issue', 'kind': 'issue', 'resource': 'Ticket', 'branch': 'Root', 'owner': 'Planner'},
        {'id': 'Transfer', 'kind': 'transfer', 'resource': 'Ticket', 'from_branch': 'Root', 'from_owner': 'Planner',
         'to_branch': 'BranchA', 'to_owner': 'Worker', 'expected_revision': 1},
        {'id': 'UseIntent', 'kind': 'consume_intent', 'resource': 'Ticket', 'branch': 'BranchA',
         'owner': 'Worker', 'expected_revision': 2, 'attempt': 'Use1'}]}
    saga = {'steps': [{'id': 'Reserve', 'compensation': 'Release', 'requires': []},
                      {'id': 'Charge', 'compensation': 'Refund', 'requires': ['Reserve']}], 'rollback': True,
            'events': [{'id': 'StartReserve', 'kind': 'intent', 'step': 'Reserve', 'action': 'Reserve', 'attempt': 'Reserve1'},
                       {'id': 'DoneReserve', 'kind': 'outcome', 'step': 'Reserve', 'action': 'Reserve', 'attempt': 'Reserve1',
                        'outcome': 'done', 'evidence': digest},
                       {'id': 'StartCharge', 'kind': 'intent', 'step': 'Charge', 'action': 'Charge', 'attempt': 'Charge1'},
                       {'id': 'DoneCharge', 'kind': 'outcome', 'step': 'Charge', 'action': 'Charge', 'attempt': 'Charge1',
                        'outcome': 'done', 'evidence': digest}]}
    rows = [('revision-acknowledgements', 'Acknowledge the exact revision',
             'Replay receive/ack records and expose recipients still missing the current revision.', ack),
            ('one-use-resources', 'Track a one-use resource across branches',
             'Replay ownership transfers and keep interrupted consumption fenced as uncertain.', resource),
            ('saga-compensation-plan', 'Plan compensation after partial work',
             'Link original and compensation identities, respecting reverse dependencies and unknown outcomes.', saga)]
    return [{'id': ident, 'title': title, 'summary': summary, 'example': example,
             'sources': _sources(ident), 'limits': list(LIMITS)} for ident, title, summary, example in rows]


def run(experiment_id, data):
    runners = {'revision-acknowledgements': _acknowledgements, 'one-use-resources': _resources,
               'saga-compensation-plan': _saga}
    if type(experiment_id) is not str or experiment_id not in runners:
        _fail('experiment_id')
    _bounded(data, 131072)
    results, checks = runners[experiment_id](data)
    answer = {'arithmetic': {'kind': 'exact finite event/state replay', 'units': 'logical events and revisions', 'version': VERSION},
              'results': results, 'checks': checks, 'limits': list(LIMITS), 'sources': _sources(experiment_id)}
    _bounded(answer, 524288)
    return answer
