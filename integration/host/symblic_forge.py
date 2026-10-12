"""HOST-ONLY: the host's `/api/symblic-forge/` routes and job launcher for Forge projects.

Why it is host-only: it keeps projects in the host's private store, launches each model job as a transient
systemd unit through integration/host/symblic_engine.py, reads the engine/model catalogue from the host's
task engine (integration/host/symblicos_tasks.py) and registers a read-only tool with the host's tool
registry (`host_tools`, not part of this repository). The Forge itself (symblic/forge/) is pure and works
without the host.

Owner-only Symblic Forge: explicit ideation, durable state, no project execution.

The only executable dispatch is a separately requested, tool-free model proposal
through native Symblic applicators. Validation and exports never dispatch work.
"""
from __future__ import annotations

import hashlib
import base64
import json
from pathlib import Path
import time

from symblic.forge import core as C
from symblic.forge import catalog as Catalog
from symblic.forge import exports as Exports
from symblic.forge import models as Models
from symblic.forge import coach as Coach
from symblic.providers import agent_teams as Teams
from symblic.forge.store import Store, StoreError, expected, identifier

PREFIX = '/api/symblic-forge/'
# Declarations the host's tool registry (host_tools) loaded: a read-only view for the host's agents.
HOST_TOOLS = [
    {'name': 'forge.handoff', 'summary': 'Inspect hash-verified frozen Forge handoffs and bounded artifact text; never starts execution.',
     'params': {'type': 'object', 'additionalProperties': False, 'required': ['project'], 'properties': {
         'project': {'type': 'string', 'minLength': 1, 'maxLength': 120},
         'handoff': {'type': 'string', 'maxLength': 120}, 'artifact': {'type': 'string', 'maxLength': 120},
         'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 12000}}},
     'returns': {'type': 'object'}, 'effect': 'read', 'policy': 'auto', 'sensitivity': 'personal',
     'caller': 'owner', 'mcp': False, 'readonly': True, 'untrusted': True, 'timeout': 30, 'resource': 'io',
     'retry': {'idempotent': True, 'reconcile': 'rerun'}, 'impl': 'handoff_for_tool',
     'catalog': 'GET /api/symblic-forge/artifact',
     'examples': [{'args': {'project': 'forge-example'}, 'why': 'Find retained handoff IDs, then inspect an exact artifact'}]}
]


def handoff_for_tool(args, ctx):
    import host_tools as bt
    from integration.host import symblic_forge_bridge as symblic_forge_bridge
    try:
        value = symblic_forge_bridge.inspect(args)
    except StoreError as exc:
        raise bt.ToolError(str(exc)) from None
    return bt.result('Frozen Forge plan and verified artifact lineage; execution not started by this read.', value)


def store():
    return Store()


def view(project, db=None):
    return {'project': project, 'analysis': C.analyze(project), 'fingerprint': C.fingerprint(project),
            'jobs': (db or store()).jobs(project['id'])}


def _launch(job_id):
    from symblic.autogen.runner import execution_fence as host_check
    host_check()
    from integration.host import symblic_engine as symblic_engine
    return symblic_engine._launch_unit('symblic-forge-' + identifier(job_id),
                                      ['-m', 'symblic.forge.models', '--job', job_id])


def _active(job_id):
    from integration.host import symblic_engine as symblic_engine
    return symblic_engine._systemd_active('', unit='symblic-forge-' + identifier(job_id))


def _stop(job_id):
    from integration.host import symblic_engine as symblic_engine
    return symblic_engine._systemd_stop('', unit='symblic-forge-' + identifier(job_id))


launcher = {'launch': _launch, 'active': _active, 'stop': _stop}


def environment(refresh=False):
    from integration.host.symblicos_tasks import catalog
    payload = catalog(refresh=refresh)
    from symblic.kernel import language as S
    # The terminal registry calls these engines local/gpt; native Symblic calls
    # them ollama/chatgpt. Preserve model identifiers and per-node placement.
    payload['models']['chatgpt'] = payload['models'].get('gpt', [])
    local = {row['id']: row for row in payload['models'].get('local', []) if row.get('id')}
    placements = []
    for node in payload.get('nodes', []):
        for row in node.get('models', []):
            name = row if isinstance(row, str) else row.get('name') if isinstance(row, dict) else None
            if not isinstance(name, str) or not name:
                continue
            local.setdefault(name, {'id': name, 'title': name})
            placements.append({'app': 'ollama:' + name + '@' + node['id'], 'node': node['id'],
                               'model': name, 'ready': node.get('ready', {}).get('ollama') is True})
    payload['models']['ollama'] = list(local.values())
    payload['native_placements'] = placements
    payload['typed_engines'] = [{'id': key, 'title': S.ENGINE_TITLES.get(key, key)}
                                for key in S.ENGINES if key not in ('kernel', 'fake')]
    payload['team_capabilities'] = Teams.capability_catalog(payload)
    payload['nodes'] = payload['team_capabilities']['nodes']
    return payload


def inventory():
    # Explicit discovery only. No import-time probes and no attachment to intent.
    import cluster_engine
    return {'requested_at': time.time(), 'nodes': environment(refresh=True)['nodes'],
            'capacity': cluster_engine.capacity_view(),
            'meaning': 'Observed hardware is separate from the accepted conceptual node plan.'}


def _body(data):
    if not isinstance(data, dict):
        raise StoreError('Submit a JSON object.')
    if len(json.dumps(data, ensure_ascii=False)) > 8_000_000:
        raise StoreError('Request exceeds the 8 MB project transaction limit.', 413)
    return data


def _revision(data):
    return expected(data.get('revision'))


def _request(data):
    return identifier(data.get('request_id'))


def _project(data, db):
    project = db.get(data.get('id'))
    if project['revision'] != _revision(data):
        raise StoreError('The project changed. Reload before continuing.', 409)
    return project


def _export_metadata(artifact):
    out = {key: artifact[key] for key in ('id', 'sha256', 'fingerprint', 'source_revision')}
    out['kind'] = artifact['format']
    if 'validation' in artifact:
        out['compileridentity'] = artifact['validation']['compiler']
    return out


def _dispatch(method, route, data=None, query=None, *, db=None):
    """Testable owner-gated handler body; HTTP gate lives in handle below."""
    db, query = db or store(), query or {}
    if method == 'GET':
        if route == 'health':
            return {'ok': True, 'schema': 'symblic-forge/1', 'execution': 'ideation_only',
                    'compiler': Exports.compiler_identity()}
        if route == 'catalog':
            return {'catalog': Catalog.catalog()}
        if route == 'models':
            return environment(refresh=query.get('refresh') == '1')
        if route == 'projects':
            return {'projects': db.listing()}
        if route == 'project':
            return view(db.get(query.get('id')), db)
        if route == 'coach':
            return {'coach': Coach.overview(db.get(query.get('id')))}
        if route == 'history':
            return {'history': db.history(query.get('id'), before=query.get('before'), limit=query.get('limit', 100))}
        if route == 'request':
            return db.request(query.get('id'))
        if route == 'job':
            return {'job': db.job(query.get('id'))}
        if route == 'artifact':
            return {'artifact': db.artifact(query.get('id'))}
        if route == 'search':
            return {'results': C.search(db.get(query.get('id')), query.get('q', ''))}
        if route == 'compare':
            return {'comparison': C.compare_branches(db.get(query.get('id')), query.get('first'), query.get('second'))}
        raise StoreError('Forge route not found.', 404)
    if method != 'POST':
        raise StoreError('Method not allowed.', 405)
    data = _body(data)
    if route == 'project/create':
        return view(db.create(data.get('idea', ''), data.get('title', ''), data.get('template', ''), _request(data)), db)
    if route == 'project/import':
        return view(db.create('', '', '', _request(data), manifest=data.get('manifest')), db)
    if route == 'demo':
        return view(db.create('', '', '', _request(data), demonstration=True), db)
    if route == 'evidence/file':
        p = _project(data, db)
        attachment, fields = evidence_file(data, p)
        updated = db.mutate(p['id'], p['revision'], 'entity.propose',
                            {'kind': 'evidence', 'entity': fields}, _request(data),
                            trusted=True, artifacts=[attachment])
        return {**view(updated, db), 'attachment': {k: v for k, v in attachment.items() if k != 'text'}}
    if route == 'action':
        action = data.get('action')
        if not isinstance(action, str) or action in ('model.artifact', 'model.artifacts', 'validation.record', 'handoff.record', 'export.record'):
            raise StoreError('That transition requires a retained host artifact, not a browser claim.')
        # A READY transition that requires a Symblic artifact always rechecks the
        # current compiler, rather than trusting imported or historical metadata.
        if action == 'lifecycle.set' and data.get('payload', {}).get('state') == 'READY':
            p = _project(data, db)
            old = C.active_branch(p).get('validation')
            if old and (not Exports.validate(p)['ok'] or old.get('fingerprint') != C.fingerprint(p)):
                raise StoreError('Validate the current accepted source before marking this project READY.')
        p = db.mutate(data.get('id'), _revision(data), action, data.get('payload', {}), _request(data))
        return view(p, db)
    if route == 'validate':
        p = _project(data, db)
        validation = Exports.validate(p, data.get('source'))
        updated = db.mutate(p['id'], p['revision'], 'validation.record', {'result': validation},
                            _request(data), trusted=True)
        return {**view(updated, db), 'validation': validation}
    if route == 'export':
        p = _project(data, db)
        artifact = Exports.artifact(p, data.get('format', 'manifest'))
        artifact['id'] = 'artifact-' + hashlib.sha256(_request(data).encode()).hexdigest()[:32]
        updated = db.mutate(p['id'], p['revision'], 'export.record', {'artifact': _export_metadata(artifact)},
                            _request(data), trusted=True, artifacts=[artifact])
        return {**view(updated, db), 'artifact': artifact}
    if route == 'handoff':
        p = _project(data, db)
        analysis = C.analyze(p)
        if analysis['readiness'].get('ready') is not True:
            raise StoreError('Resolve the visible mandatory readiness issues before freezing a build handoff.', 409)
        validation = Exports.validate(p)
        if not validation['ok']:
            raise StoreError('The current compiler rejected this generated handoff.', 409)
        artifacts = []
        for kind in ('manifest', 'symblic', 'tasks', 'sheet', 'construction'):
            artifact = Exports.artifact(p, kind)
            artifact['id'] = 'artifact-' + hashlib.sha256((_request(data) + ':' + kind).encode()).hexdigest()[:32]
            artifacts.append(artifact)
        handoff = {'id': 'handoff-' + hashlib.sha256(_request(data).encode()).hexdigest()[:32],
                   'source_revision': p['revision'], 'fingerprint': C.fingerprint(p),
                   'branch_id': p['active_branch'], 'status': 'frozen',
                   'artifacts': [_export_metadata(a) for a in artifacts], 'compiler': validation['compiler'],
                   'execution_started': False}
        updated = db.mutate(p['id'], p['revision'], 'handoff.record', {'handoff': handoff},
                            _request(data), trusted=True, artifacts=artifacts)
        return {**view(updated, db), 'handoff': handoff, 'artifacts': artifacts}
    if route == 'inventory':
        return inventory()
    if route == 'inventory/attach':
        p = _project(data, db)
        observed = environment(refresh=True)
        models = sorted({engine + (':' + item['id'] if item.get('id') else '')
                         for engine, items in observed.get('models', {}).items()
                         for item in items if isinstance(item, dict) and isinstance(item.get('id', ''), str)})
        nodes = [{'id': row['id'], 'models': [item if isinstance(item, str) else item['name']
                  for item in row.get('models', []) if isinstance(item, str) or isinstance(item, dict) and isinstance(item.get('name'), str)]
                  if isinstance(row.get('models'), list) else []}
                 for row in observed.get('nodes', []) if isinstance(row.get('id'), str)]
        evidence = {'text': 'Explicitly captured model and node catalogue; availability is observational, not a deployment promise.',
                    'evidence_type': 'inventory', 'inventory': {'models': models, 'nodes': nodes, 'complete': False,
                    'source': 'Cached native provider catalogue and registered node discovery; not a complete per-node installation audit.'},
                    'captured_at': time.time(), 'requirement_ids': []}
        updated = db.mutate(p['id'], p['revision'], 'entity.propose', {'kind': 'evidence', 'entity': evidence}, _request(data))
        return view(updated, db)
    if route == 'repair/preview':
        p = _project(data, db)
        return {'repair': C.repair_candidate(p, data.get('evidence_id'))}
    if route in ('coach/preview', 'coach/propose'):
        p = _project(data, db)
        fields = {key: data[key] for key in ('text', 'input', 'output', 'check', 'context', 'source_ids', 'lens', 'edited_text', 'construction')
                  if key in data}
        preview = Coach.preview(p, fields)
        if route == 'coach/preview':
            return {'preview': preview}
        updated = db.mutate(p['id'], p['revision'], 'coach.propose', fields, _request(data))
        return {**view(updated, db), 'preview': preview}
    if route == 'model/start':
        from symblic.autogen.runner import execution_fence as host_check
        host_check()
        p = _project(data, db)
        request = Models.build_request(p, data.get('role'), apps=data.get('apps'),
                                       question_id=data.get('question_id'), metadata=data.get('metadata'),
                                       instruction=data.get('instruction', ''), refinement_intent=data.get('refinement_intent', 'refine'),
                                       team=data.get('team'), strategy=data.get('strategy', 'independent'),
                                       allow_cloud=data.get('allow_cloud', False), lens=data.get('lens', ''))
        job, fresh = db.reserve_job(p['id'], p['revision'], request, _request(data))
        if fresh:
            try:
                result = launcher['launch'](job['id'])
                if not result.get('ok'):
                    job = db.update_job(job['id'], {'status': 'unknown', 'error': str(result.get('error'))[:1000]},
                                        only_status=('queued',))
            except Exception as exc:
                job = db.job(job['id'])
                if job['status'] == 'queued':
                    job = db.update_job(job['id'], {'status': 'unknown', 'error': str(exc)[:1000]},
                                        only_status=('queued',))
        return {'job': job, 'duplicate': not fresh}
    if route == 'model/adopt':
        job = db.job(data.get('job_id'))
        if job['project_id'] != data.get('id') or job['status'] not in ('completed', 'partial'):
            raise StoreError('Only retained successful outcomes of a completed or partial current job can be imported for review.', 409)
        p = _project(data, db)
        if p['revision'] != job['request_revision'] or p['active_branch'] != job['request']['branch_id']:
            raise StoreError('This response is stale. Inspect it or request a new refinement against current state.', 409)
        indices = data.get('indices', [data.get('index', 0)])
        if (type(indices) is not list or not 1 <= len(indices) <= 48 or any(type(i) is not int or not 0 <= i < len(job['outcomes']) for i in indices)
                or len(set(indices)) != len(indices)):
            raise StoreError('Select a retained model proposal.')
        artifacts = [job['outcomes'][index]['artifact'] for index in indices]
        updated = db.mutate(p['id'], p['revision'], 'model.artifacts', {'artifacts': artifacts}, _request(data))
        return view(updated, db)
    if route in ('model/recover', 'model/stop'):
        job = db.job(data.get('job_id'))
        if job['project_id'] != data.get('id'):
            raise StoreError('This request belongs to another project.', 409)
        if job['status'] not in ('queued', 'running', 'unknown'):
            return {'job': job}
        if route == 'model/stop':
            if not launcher['stop'](job['id']):
                raise StoreError('The worker stop was not confirmed; its request remains retained.', 409)
            try:
                job = db.update_job(job['id'], {'status': 'cancelled', 'error': 'Operator stopped the owned proposal worker.'},
                                    only_status=('queued', 'running', 'unknown'))
            except StoreError:
                job = db.job(job['id'])
        elif not launcher['active'](job['id']):
            try:
                job = db.update_job(job['id'], {'status': 'unknown', 'error': 'No active worker was observed. '
                                              'A prior model call may have occurred; this request will not be replayed.'},
                                    only_status=('queued', 'running', 'unknown'))
            except StoreError:
                job = db.job(job['id'])  # A terminal worker receipt won the probe race.
        return {'job': job}
    raise StoreError('Forge route not found.', 404)


def evidence_file(data, project):
    """Bounded inert attachment bytes. Never serve uploaded HTML/SVG or run parsers."""
    filename = data.get('filename')
    encoded = data.get('content_b64')
    if not isinstance(filename, str) or not filename or len(filename) > 200 or '/' in filename or '\\' in filename:
        raise StoreError('Use a plain filename of at most 200 characters.')
    if not isinstance(encoded, str) or len(encoded) > 2_670_000:
        raise StoreError('Evidence files are limited to 2 MB.', 413)
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise StoreError('Evidence is not valid base64.') from exc
    if not content or len(content) > 2_000_000:
        raise StoreError('Evidence files must contain 1–2,000,000 bytes.', 413)
    suffix = Path(filename).suffix.lower()
    signatures = {'.pdf': (b'%PDF-', 'application/pdf'), '.png': (b'\x89PNG\r\n\x1a\n', 'image/png'),
                  '.jpg': (b'\xff\xd8\xff', 'image/jpeg'), '.jpeg': (b'\xff\xd8\xff', 'image/jpeg')}
    if suffix in signatures:
        magic, media_type = signatures[suffix]
        if not content.startswith(magic):
            raise StoreError('Evidence file signature does not match its extension.')
    elif suffix in ('.txt', '.json', '.csv'):
        try:
            decoded = content.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise StoreError('Text evidence must use UTF-8.') from exc
        if '\x00' in decoded or decoded.lstrip().lower().startswith(('<svg', '<html', '<!doctype')):
            raise StoreError('Active document content is not accepted as text evidence.')
        if suffix == '.json':
            json.loads(decoded, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON evidence')))
        media_type = {'.txt': 'text/plain', '.json': 'application/json', '.csv': 'text/csv'}[suffix]
    else:
        raise StoreError('Attach UTF-8 TXT/JSON/CSV, PDF, PNG, or JPEG evidence.')
    artifact_id = 'artifact-' + hashlib.sha256(_request(data).encode()).hexdigest()[:32]
    content_hash = hashlib.sha256(content).hexdigest()
    artifact = {'id': artifact_id, 'format': 'evidence', 'encoding': 'base64', 'text': encoded,
                'sha256': hashlib.sha256(encoded.encode()).hexdigest(), 'content_sha256': content_hash,
                'fingerprint': C.fingerprint(project), 'source_revision': project['revision'],
                'filename': filename, 'media_type': media_type, 'size': len(content)}
    fields = {'text': 'Attached evidence: ' + filename, 'evidence_type': 'file',
              'file_artifact_id': artifact_id, 'filename': filename, 'sha256': content_hash,
              'media_type': media_type, 'size': len(content), 'requirement_ids': []}
    return artifact, fields


def dispatch(method, route, data=None, query=None, *, db=None):
    """Exactly identified HTTP actions also survive a lost post-commit reply."""
    db = db or store()
    if method != 'POST' or route == 'inventory':
        return _dispatch(method, route, data, query, db=db)
    data = _body(data)
    request_id = _request(data)
    fresh, outcome = db.api_begin(request_id, {'route': route, 'data': data})
    if not fresh:
        if outcome is not None:
            if 'failure' in outcome:
                raise StoreError(outcome['failure'], outcome['status'])
            return {**outcome['result'], 'duplicate': True}
        committed = db.request(request_id)
        if committed['found']:
            result = committed['result']
            if result.get('schema') == 'symblic-forge/1':
                answer = view(db.get(result['id']), db)
                if route == 'export':
                    artifact_id = 'artifact-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
                    answer['artifact'] = db.artifact(artifact_id)
                elif route == 'validate':
                    answer['validation'] = C.active_branch(result)['validation']
                elif route == 'handoff':
                    handoff_id = 'handoff-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
                    answer['handoff'] = next(h for h in result['handoffs'] if h['id'] == handoff_id)
                    answer['artifacts'] = [db.artifact(a['id']) for a in answer['handoff']['artifacts']]
            elif result.get('id', '').startswith('forgejob-'):
                answer = {'job': db.job(result['id'])}
            else:
                raise StoreError('The action receipt is incomplete; no automatic repetition is permitted.', 409)
            db.api_finish(request_id, {'result': answer})
            return {**answer, 'duplicate': True}
        raise StoreError('That action has a durable intent but no confirmed outcome. Inspect the project; '
                         'it will not be automatically repeated.', 409)
    try:
        answer = _dispatch(method, route, data, query, db=db)
    except (ValueError, KeyError, TypeError) as exc:
        db.api_finish(request_id, {'failure': str(exc), 'status': getattr(exc, 'status', 400)})
        raise
    db.api_finish(request_id, {'result': answer})
    return answer


def handle(handler, method, path, data):
    if not handler.require_owner('Symblic Forge project intentions and model context'):
        return True
    route = path.partition('?')[0].removeprefix(PREFIX).strip('/')
    try:
        query = {key: handler.get_query_param(key) for key in ('id', 'q', 'first', 'second', 'before', 'limit', 'refresh')}
        query = {key: value for key, value in query.items() if value not in (None, '')}
        handler.send_json(dispatch(method, route, data, query))
    except (ValueError, KeyError, TypeError) as exc:
        handler.send_json({'error': str(exc)}, getattr(exc, 'status', 400))
    return True
