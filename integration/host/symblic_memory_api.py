"""HOST-ONLY: the host's claim-notebook routes and CLI; notebooks live in the host engine's run store.

Why it is host-only: notebooks are kept under the host engine's data root and import claims from the host's
finished run folders (integration/host/symblic_engine.py, whose saves need the host's store module). The
notebook logic itself is pure: symblic/memory/notebooks.py. `tools/symblic memory` reaches this module and
reports the missing host plainly.


No model, effect, worker or import side effect. Host run claims are read from a
finished local record, never from client-provided attestation JSON.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from symblic.kernel import language as S
from symblic.kernel import epistemic as EP
from symblic.memory import notebooks as M

ID = re.compile(r'[0-9a-f]{12}\Z')
OP = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')


def _engine():
    from integration.host import symblic_engine as symblic_engine
    return symblic_engine


def root():
    path = Path(_engine().root()) / 'memory'
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Notebook storage cannot be a symbolic link.')
    return path


def path(ident):
    if type(ident) is not str or not ID.fullmatch(ident):
        raise ValueError('Select a notebook by its exact ID.')
    target = root() / ident
    if target.is_symlink():
        raise ValueError('Notebook storage cannot be a symbolic link.')
    return target


def _keys(body, allowed, required=()):
    if type(body) is not dict or set(body) - set(allowed) or not set(required) <= set(body):
        raise ValueError('Notebook request has missing or unsupported fields.')


def _read_run(ident, selected_ids):
    engine = _engine()
    folder = Path(engine.run_dir(ident))
    def record(name):
        target = folder / name
        if target.is_symlink():
            raise ValueError('A run record cannot be a symbolic link.')
        with target.open('rb') as stream:
            raw = stream.read(M.MAX_FILE_BYTES + 1)
        if len(raw) > M.MAX_FILE_BYTES:
            raise ValueError('The run record exceeds the bounded import limit.')
        parsed = json.loads(raw)
        if type(parsed) is not dict:
            raise ValueError('The run record is damaged.')
        return parsed, hashlib.sha256(raw).hexdigest()
    state, state_hash = record('state.json')
    meta, meta_hash = record('meta.json')

    if state.get('status') not in ('done', 'failed', 'stopped'):
        raise ValueError('Import a finished or stopped run so its claim snapshot is stable.')
    if state.get('kernel') != S.kernel_id():
        raise ValueError('This run uses another kernel. Inspect its original evidence; automatic claim import requires the current kernel.')
    with (folder / 'program.sym').open('rb') as stream:
        source = stream.read(S.MAX_SOURCE * 4 + 1)
    if len(source) > S.MAX_SOURCE * 4:
        raise ValueError('Recorded source exceeds the notebook import limit.')
    source_hash = hashlib.sha256(source).hexdigest()
    registry = state.get('epistemic')
    if type(registry) is not dict or type(registry.get('claims')) is not list:
        raise ValueError('This run has no claim registry to import.')
    if len(registry['claims']) > 10000:
        raise ValueError('Recorded claims exceed the bounded notebook import limit.')
    claims = [EP.validate_claim(claim) for claim in registry['claims']]
    rows = {claim['id']: claim for claim in claims}
    if len(rows) != len(claims):
        raise ValueError('Recorded claim IDs repeat.')
    selected = list(rows) if selected_ids is None else selected_ids
    if (type(selected) is not list or any(type(ident) is not str or ident not in rows for ident in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('Select distinct claim IDs from this run.')
    closure, pending = set(), list(selected)
    while pending:
        item = pending.pop()
        if item in closure or item not in rows:
            continue   # retained missing references remain unavailable support
        closure.add(item)
        pending.extend(ref['id'] for ref in rows[item]['dependencies'])
    # The bounded notebook independently selects and validates the full closure.
    # Its origin labels come only from this host record, never API JSON.
    values = {}
    recorded_outputs = state.get('outputs', [])
    if type(recorded_outputs) is not list:
        raise ValueError('The recorded outputs are damaged.')
    outputs = {}
    for row in recorded_outputs:
        if type(row) is dict and type(row.get('binding')) is str:
            outputs[row['binding']] = row

    for claim in claims:
        if type(claim) is not dict or type(claim.get('content')) is not dict:
            raise ValueError('The recorded claim registry is damaged.')
        content = claim['content']
        if (content.get('source_sha256') != source_hash
                and not (content.get('kind') == 'bounded_lineage_summary' and content.get('source_sha256') is None)):
            raise ValueError('A claim belongs to a different source revision.')
        if claim['id'] not in closure:
            continue
        row = outputs.get(content.get('name'))
        if row and row.get('canonical_version') == S.CANON_VERSION and 'canonical' in row:
            if EP.digest(row['canonical']) == content.get('value_sha256'):
                values[claim['id']] = row['canonical']
    from symblic.kernel import execution_pins as X
    options = meta.get('options', {})
    if type(options) is not dict:
        raise ValueError('Recorded run options are damaged.')
    pins = None
    if 'execution_pins' in options:
        pins = X.validate(options['execution_pins'], source.decode('utf-8'), meta.get('inputs', {}))
    constructor_source = {}
    solver_claims = [row for row in claims if row['id'] in closure and row['origin'] == 'solver_proposal']
    if solver_claims:
        # New trusted imports retain the host journal relationship. The pure
        # envelope alone cannot attest that construction/native checking ran.
        from symblic.constructor import records as records
        from symblic.kernel import evidence as evidence
        from symblic.kernel import run as runner
        config = records.read_config(str(folder))
        journal = records.read_journal(str(folder))
        if config is None or journal is None:
            raise ValueError('Solver proposal import requires its constructor configuration and journal.')
        policy = runner.validate_constructor_options(options)
        if policy['mode'] != config['mode'] or policy['limits'] != config['limits']:
            raise ValueError('Recorded constructor options do not match the journal configuration.')
        snapshot = records.bind_journal(records.validate_journal(journal), config,
            source_sha256=source_hash, input_sha256=evidence.digest(meta.get('inputs', {})),
            kernel_id=state['kernel']['id'])
        for claim in solver_claims:
            records.validate_solver_claim(claim, snapshot)
        constructor_source = {'constructor_journal_sha256': hashlib.sha256(journal.encode('ascii')).hexdigest(),
                              'constructor_configuration_sha256': records.config_hash(config)}
    return [row for row in claims if row['id'] in closure], values, selected, {
        'run_id': ident, 'execution_id': state.get('execution_id'), 'source_sha256': source_hash,
        'state_sha256': state_hash, 'metadata_sha256': meta_hash, 'kernel': state['kernel'],
        'input_sha256': hashlib.sha256(X._json(meta.get('inputs', {}))).hexdigest(),
        'execution_pins_sha256': pins.get('sha256') if pins else None,
        'run_status': state['status'], 'acquisition_independence': 'not_assessed',
        'scope': 'local_host_record_not_authentication', **constructor_source}


def create(body):
    _keys(body, ('title', 'operation_id', 'run_id', 'selected_ids'), ('title', 'operation_id'))
    operation = body['operation_id']
    if type(operation) is not str or not OP.fullmatch(operation):
        raise ValueError('Use a stable operation ID of 1..128 identifier characters.')
    ident = hashlib.sha256(('symblic-memory:' + operation).encode()).hexdigest()[:12]
    claims, values, source = [], {}, None
    selected = body.get('selected_ids')
    if body.get('run_id'):
        claims, values, selected, source = _read_run(body['run_id'], selected)
    elif body.get('selected_ids'):
        raise ValueError('Selected claim IDs require a source run.')
    result = M.create(path(ident), title=body['title'], operation_id=operation,
                      trusted_claims=claims, selected_ids=selected,
                      trusted_values=values, source=source)
    return {'id': ident, **result}


def notebooks():
    # Directory metadata only. Full integrity/support evaluation is on selection,
    # never an eager replay of every notebook on a listing or recurring poll.
    rows = []
    for item in root().iterdir():
        if ID.fullmatch(item.name) and item.is_dir() and not item.is_symlink():
            rows.append({'id': item.name, 'modified': item.stat().st_mtime})
    return {'notebooks': sorted(rows, key=lambda row: (-row['modified'], row['id']))[:200]}


def view(ident):
    return {'id': ident, **M.view(path(ident))}


def change(body):
    _keys(body, ('id', 'command'), ('id', 'command'))
    return {'id': body['id'], **M.change(path(body['id']), body['command'])}


def context(body):
    _keys(body, ('id', 'selected_ids', 'budget', 'prefix', 'suffix', 'fixed_parts', 'unit', 'expected_head'),
          ('id', 'selected_ids', 'budget', 'expected_head'))
    if type(body['expected_head']) is not str or not SHA.fullmatch(body['expected_head']):
        raise ValueError('Context requires the exact displayed notebook head.')
    return {'id': body['id'], **M.context(path(body['id']), **{k: v for k, v in body.items() if k != 'id'})}


def handle(handler, method, route, data):
    if not route.startswith('memory/'):
        return False
    try:
        if method == 'GET' and route == 'memory/notebooks':
            result = notebooks()
        elif method == 'GET' and route == 'memory/view':
            result = view(handler.get_query_param('id'))
        elif method == 'POST' and route == 'memory/create':
            result = create(data)
        elif method == 'POST' and route == 'memory/change':
            result = change(data)
        elif method == 'POST' and route == 'memory/context':
            result = context(data)
        else:
            handler.send_json({'error': 'Unknown notebook action.'}, 404)
            return True
        handler.send_json(result)
    except (ValueError, OSError, S.SymblicError, RecursionError, TypeError, KeyError) as error:
        detail = error.as_dict() if hasattr(error, 'as_dict') else {'message': str(error)}
        handler.send_json({'error': str(error), 'detail': detail}, 409 if getattr(error, 'code', '') == 'conflict' else 400)
    return True


def main(argv=None):
    """Local owner CLI uses the same finite API contracts, never models."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='Persistent Symblic claim notebooks.')
    parser.add_argument('command', choices=('list', 'create', 'view', 'change', 'context'))
    parser.add_argument('input', nargs='?', help='Notebook ID for view; request JSON file for other actions')
    parser.add_argument('--agent-json', '--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            result = notebooks()
        elif args.command == 'view':
            result = view(args.input)
        else:
            if not args.input:
                parser.error('Supply a request JSON file.')
            with Path(args.input).open('rb') as stream:
                raw = stream.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError('Notebook request exceeds 1 MB.')
            body = json.loads(raw)
            result = {'create': create, 'change': change, 'context': context}[args.command](body)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, S.SymblicError, RecursionError, TypeError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), file=sys.stdout)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
