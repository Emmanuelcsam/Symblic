"""Command line for Forge-bound MICA constructions: prepare, plan, execute, status, artifacts.

Run as `python3 -m symblic.mica.cli forge ...`. Depends on forge.py, cli.py, symblic.forge.store.

Details
    Explicit caller-supplied Forge bindings through MICA's existing construction lifecycle.

    prepare emits a sealed JSON object. Keep that object, inventory, directory and
    request ID for plan/execute; repeating execute is explicit native resume. Generic
    mica status/artifacts read core evidence without Forge-origin attestation; this
    module's status/artifacts also check the original Forge receipt. No new executor,
    call store, model planner, acceptance action or implicit output-file write.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

from symblic.mica import cli as L
from symblic.mica import forge as A
from symblic.graph import run as G


COMMANDS = ('prepare', 'plan', 'execute', 'status', 'artifacts')


def parser():
    p = L._Parser(prog='python3 -m symblic.mica.cli forge', description=__doc__, add_help=False)
    p.add_argument('--help', action='store_true')
    commands = p.add_subparsers(dest='command')
    prepare = commands.add_parser('prepare', add_help=False)
    prepare.add_argument('project')
    prepare.add_argument('handoff')
    prepare.add_argument('--binding', required=True)
    prepare.add_argument('--store')
    for name in COMMANDS[1:]:
        command = commands.add_parser(name, add_help=False)
        command.add_argument('prepared')
        command.add_argument('--dir', required=True)
        command.add_argument('--inventory', required=True)
        command.add_argument('--request-id', required=True)
        command.add_argument('--store')
        if name == 'artifacts':
            command.add_argument('--include-text', action='store_true')
            command.add_argument('--archive', action='store_true')
    return p


def _input(path):
    return A._json(A._regular_bytes(path).decode('utf-8'))


def _store(path, factory):
    if factory is not None:
        return factory(path)
    from symblic.forge.store import Store
    db = Store(path)
    root = db.root.absolute()
    if any(parent.is_symlink() for parent in (root, *root.parents)):
        raise L.CliError('store_path', 'Symlinked Forge storage is refused.')
    if not (root / 'forge.sqlite3').is_file():
        raise L.CliError('store_missing', 'An existing Forge store containing the frozen handoff is required.')
    return db


@contextmanager
def _runtime(prepared, directory, inventory, db, request_id, factory):
    if factory is not None:
        yield factory(prepared, directory, inventory, db=db, request_id=request_id)
        return
    with L._applications(directory) as apps:
        yield A.ForgeMicaRun(prepared, directory, apps, inventory, db=db, request_id=request_id)


def read_result(prepared, directory, inventory, db, request_id):
    """Existing receipt + shared core lock; never enter MicaRun.execute."""
    from integration.host import symblic_forge_bridge as F
    from symblic.mica import calibration as H
    folder = A._workspace(directory)
    G._unseal(prepared)
    origin = prepared['origin']
    _, handoff, artifacts, _ = F.frozen(origin['project'], origin['handoff'], db=db, current=False)
    refs = [{key: a[key] for key in ('id', 'format', 'sha256', 'source_revision')} for a in artifacts]
    if (refs != origin['artifacts'] or handoff['fingerprint'] != origin['fingerprint'] or
            handoff['source_revision'] != origin['source_revision'] or
            handoff['branch_id'] != origin['branch_id'] or handoff['compiler'] != origin['identity']['forge']):
        raise L.CliError('origin', 'Original Forge artifacts or compiler receipt changed.')
    record = A._origin_record(prepared, folder, inventory, request_id)
    envelope = {'operation': 'forge-mica/1', 'request_id': record['request_id'],
                'folder': str(folder), 'prepared': prepared, 'inventory': record['inventory']}
    key = 'mica-origin-' + hashlib.sha256(record['request_id'].encode()).hexdigest()
    with db.connection() as conn:
        prior = db._replay(conn, key, envelope)
    if prior is None:
        return {'status': 'not_started', 'scope': A.SCOPE, 'semantic_completeness': 'unassessed',
                'note': 'No original Forge dispatch receipt; this reader starts no work.'}
    if prior != record:
        raise L.CliError('origin', 'Original Forge dispatch receipt differs.')
    labels = {'forge_origin': copy.deepcopy(record), 'scope': A.SCOPE, 'semantic_completeness': 'unassessed'}
    manifest_path = folder / 'mica-manifest.json'
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return {'status': 'unknown', 'failure': 'UNRESOLVED_EFFECT', **labels,
                'note': 'Origin receipt has no retained core manifest; no dispatch was repeated.'}
    with H._locked(folder, '.mica.lock'):
        _, manifest, result = L._run_records(folder)
        if (manifest['request'] != prepared['request'] or manifest['inventory'] != record['inventory'] or
                manifest.get('initial_plans') != [prepared['plan']] or manifest.get('mode') != 'mica' or
                manifest.get('identity') != origin['identity']['mica'] or
                manifest.get('library') is not None or manifest.get('calibration') is not None):
            raise L.CliError('origin', 'Core manifest differs from the frozen Forge binding.')
        # Existing core readers validate retained artifact pins and host-cost
        # evidence; a missing result stays incomplete and never executes again.
        result = ({**result, **labels} if result else {'status': 'incomplete', **labels,
                  'note': 'No terminal core result. The original plan command returns the validated plan; execute with the same inputs explicitly resumes through native journals.'})
        A.verify_result_origin(result, prepared, folder, inventory, request_id)
        return result


def dispatch(args, *, runtime_factory=None, store_factory=None):
    if args.help or args.command is None:
        return {'version': 1, 'commands': list(COMMANDS), 'usage': parser().format_help(),
                'scope': A.SCOPE, 'semantic_completeness': 'unassessed'}
    db = _store(args.store, store_factory)
    if args.command == 'prepare':
        return A.prepare(args.project, args.handoff, _input(args.binding), db=db)
    prepared = _input(args.prepared)
    G._unseal(prepared)
    inventory = L._inventory(args.inventory)
    directory = Path(os.path.abspath(args.dir))
    if args.command in ('plan', 'execute'):
        with _runtime(prepared, directory, inventory, db, args.request_id, runtime_factory) as run:
            result = run.plan() if args.command == 'plan' else run.execute()
        A.verify_result_origin(result, prepared, directory, inventory, args.request_id)
        return result
    result = read_result(prepared, directory, inventory, db, args.request_id)
    labels = {key: result[key] for key in ('forge_origin', 'scope', 'semantic_completeness') if key in result}
    if args.command == 'status':
        return {key: value for key, value in result.items() if key in
                ('status', 'failure', 'calls', 'costs', 'host_costs', 'assurance', 'note', *labels)}
    artifacts, extra = [], {}
    if result.get('status') == 'done':
        if result.get('bundle') is not None:
            artifacts, extra = L._bundle_artifacts(result, include_text=args.include_text,
                include_archive=args.archive, runtime_identity=prepared['origin']['identity']['mica'])
        else:
            if args.archive:
                raise L.CliError('archive_format', 'ZIP export requires a completed JavaScript module bundle.')
            output = result['output']
            if output.get('sha256') != hashlib.sha256(output['text'].encode()).hexdigest():
                raise L.CliError('artifact_pin', 'Output source digest changed.')
            row = {'file': output['file'], 'sha256': output['sha256'], 'bytes': len(output['text'].encode()),
                   'assurance': result.get('assurance', 'TESTED')}
            if args.include_text:
                row['text'] = output['text']
            artifacts.append(row)
    return {'status': result['status'], 'artifacts': artifacts, **labels, **extra}


def main(argv=None, *, out=None, runtime_factory=None, store_factory=None):
    stream = out or sys.stdout
    try:
        args = parser().parse_args(argv)
        result = dispatch(args, runtime_factory=runtime_factory, store_factory=store_factory)
        code = int(args.command in ('plan', 'execute') and result.get('status') not in ('planned', 'done'))
    except KeyboardInterrupt:
        result, code = {'ok': False, 'error': {'code': 'interrupted', 'message': 'Inspect the original native journals before explicit resume.'}}, 130
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        result, code = {'ok': False, 'error': {'code': getattr(exc, 'code', type(exc).__name__), 'message': str(exc)[:1000]}}, 2
    except Exception as exc:
        result, code = {'ok': False, 'error': {'code': type(exc).__name__, 'message': 'Forge command failed; retain the original inputs and inspect durable evidence.'}}, 2
    try:
        encoded = json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        encoded, code = '{"ok":false,"error":{"code":"invalid_result"}}', 2
    print(encoded, file=stream)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
