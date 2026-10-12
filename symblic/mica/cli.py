"""Command line for MICA: plan, execute, resume and inspect checked JavaScript constructions (JSON in, JSON out).

    python3 -m symblic.mica.cli --help
    python3 -m symblic.mica.cli inventory > inventory.json        snapshot the configured Ollama hosts (no model call)
    python3 -m symblic.mica.cli validate request.json [--plan plan.json]
    python3 -m symblic.mica.cli plan|execute request.json --dir RUN --inventory inventory.json [--mode mica]
    python3 -m symblic.mica.cli plan|execute --objective "..." --budget budget.json --dir RUN --inventory inventory.json
    python3 -m symblic.mica.cli status|resume|artifacts --dir RUN
    python3 -m symblic.mica.cli benchmark|report ...               frozen construction benchmarks (bench.py)
    python3 -m symblic.mica.cli checkpack|forge|promote ...        see checkpack_cli.py, forge_cli.py, promote.py

Every command prints exactly one JSON document. Execution requires an explicit inventory snapshot: which models on
which nodes may be asked. A node is an Ollama host label from SYMBLIC_OLLAMA_HOSTS (symblic/providers/README.md);
model calls go through symblic.providers.applicators as ``ollama:MODEL@NODE``. Nodes named in
SYMBLIC_MICA_EXCLUDED_NODES (comma-separated) are refused, for example a machine that must not load models.
Hidden benchmark fixtures stay with the evaluator.

Importing this module performs no discovery, provider call, store access or work.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import argparse
import base64
import hashlib
import json
import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

VERSION = 1
MODES = ('direct', 'static', 'decompose_on_failure', 'capability', 'search', 'mica')
COMMANDS = ('capabilities', 'inventory', 'plan', 'validate', 'execute', 'status', 'resume', 'artifacts', 'calibration',
            'benchmark', 'report', 'forge', 'checkpack', 'promote')
FORMATS = ('javascript_script', 'javascript_modules')


class CliError(ValueError):
    """A refused command; `code` is a stable identifier printed in the JSON error."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError('arguments', message)


def parser():
    """The argument parser for every command (errors raise CliError instead of exiting)."""
    p = _Parser(prog='python3 -m symblic.mica.cli', description=__doc__, add_help=False)
    p.add_argument('--help', action='store_true')
    commands = p.add_subparsers(dest='command')
    commands.add_parser('checkpack', add_help=False, help='Freeze finite requirement-bound check data; use checkpack --help.')
    commands.add_parser('forge', add_help=False, help='Construction from an accepted Forge handoff; use forge --help.')
    commands.add_parser('promote', add_help=False, help='Promote a done run whose frozen finite pack passes into the component library; use promote --help.')
    cap = commands.add_parser('capabilities', add_help=False)
    cap.add_argument('--inventory')
    commands.add_parser('inventory', add_help=False,
                        help='Snapshot the configured Ollama hosts as an inventory file (reads /api/tags; no model call).')
    validate = commands.add_parser('validate', add_help=False)
    validate.add_argument('request')
    validate.add_argument('--plan')
    for name in ('plan', 'execute'):
        command = commands.add_parser(name, add_help=False)
        command.add_argument('request', nargs='?')
        objective = command.add_mutually_exclusive_group()
        objective.add_argument('--objective')
        objective.add_argument('--objective-file')
        command.add_argument('--budget')
        command.add_argument('--output', action='append', default=[])
        command.add_argument('--library')
        command.add_argument('--calibration')
        command.add_argument('--format', dest='artifact_format', choices=FORMATS)
        command.add_argument('--dir', required=True)
        command.add_argument('--inventory', required=True)
        command.add_argument('--mode', choices=MODES, default='mica')
        if name == 'execute':
            command.add_argument('--initial-plan')
    for name in ('status', 'resume', 'artifacts'):
        command = commands.add_parser(name, add_help=False)
        command.add_argument('--dir', required=True)
        if name == 'artifacts':
            command.add_argument('--include-text', action='store_true')
            command.add_argument('--archive', action='store_true')
    calibration = commands.add_parser('calibration', add_help=False)
    calibration.add_argument('--run', action='append', required=True)
    bench = commands.add_parser('benchmark', add_help=False)
    bench.add_argument('--root', required=True)
    bench.add_argument('--id', required=True)
    bench.add_argument('--fixture', action='append', default=[])
    bench.add_argument('--inventory', required=True)
    bench.add_argument('--repetitions', type=int, default=1)
    bench.add_argument('--split', choices=('dev', 'heldout'), default=None,
                       help='New benchmarks default to dev; resume retains the frozen split.')
    bench.add_argument('--seed', type=int, default=0)
    bench.add_argument('--freeze')
    bench.add_argument('--run', action='store_true')
    report = commands.add_parser('report', add_help=False)
    report.add_argument('--root', required=True)
    report.add_argument('--id', required=True)
    report.add_argument('--freeze', required=True)
    return p


def _json_file(path, *, max_bytes=2_000_000):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CliError('duplicate_key', 'Duplicate JSON keys are refused.')
            result[key] = value
        return result
    def constant(_):
        raise CliError('json_number', 'Non-finite JSON numbers are refused.')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise CliError('input_file', 'Expected a regular JSON file within its %d byte bound.' % max_bytes)
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise CliError('input_file', 'JSON input exceeds its %d byte bound.' % max_bytes)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def excluded_nodes():
    """Nodes that must never run construction calls: SYMBLIC_MICA_EXCLUDED_NODES (comma-separated)."""
    return {name.strip() for name in os.environ.get('SYMBLIC_MICA_EXCLUDED_NODES', '').split(',') if name.strip()}


def _inventory(path, *, require_ready=False):
    """Read an inventory file: a list of rows, or the object the `inventory` command prints."""
    from symblic.mica import routing as R
    data = _json_file(path)
    if type(data) is dict and set(data) >= {'version', 'inventory'}:
        data = data['inventory']
    rows = R.normalize_inventory(data)
    excluded = excluded_nodes()
    if any(row['node'] in excluded for row in rows):
        raise CliError('inventory_node', 'The inventory names a node excluded by SYMBLIC_MICA_EXCLUDED_NODES.')
    if require_ready and not any(row['ready'] and row['available'] for row in rows):
        raise CliError('inventory_unavailable', 'No explicitly ready worker with available capacity in this snapshot.')
    return rows


def snapshot_inventory(hosts=None, opener=None):
    """Inventory rows for every model each configured Ollama host lists, with the digest it lists.

    Reads each host's /api/tags once (a listing, never a model call). A host whose label is not a plain node name
    (for example the unnamed default '127.0.0.1:11434') is reported in 'skipped' with how to name it."""
    import json as _json
    import urllib.request
    from symblic.mica import routing as R
    from symblic.providers import applicators as P
    from symblic.providers import ollama_call as OC
    hosts = P.ollama_hosts() if hosts is None else hosts
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), OC._NoRedirect())
    rows, skipped = [], []
    for label, host in hosts.items():
        if not R._NODE.fullmatch(label):
            skipped.append({'host': label, 'reason': 'name the host in SYMBLIC_OLLAMA_HOSTS, for example local=' + label})
            continue
        try:
            with opener.open(urllib.request.Request(host['base'] + '/api/tags'), timeout=OC.TAGS_TIMEOUT) as reply:
                tags = _json.loads(reply.read(OC.TAGS_MAX + 1))
        except Exception as exc:  # noqa: BLE001  (an unreachable host is reported, not fatal)
            skipped.append({'host': label, 'reason': 'listing unavailable: ' + type(exc).__name__})
            continue
        for item in (tags.get('models') or []) if isinstance(tags, dict) else []:
            if not isinstance(item, dict) or not isinstance(item.get('name'), str):
                continue
            found = OC.digest_of(item.get('digest'))
            rows.append({'engine': 'ollama', 'model': item['name'], 'node': label,
                         'digest': found.removeprefix('sha256:') if found else None,
                         'ready': True, 'available': True})
    return R.normalize_inventory(rows), skipped


@contextmanager
def _applications(directory):
    from symblic.providers.applicators import Applicators, install_sigterm
    apps = Applicators(owner_label='symblic MICA command line',
                       run_id='mica-' + hashlib.sha256(str(directory).encode()).hexdigest()[:16])
    install_sigterm()
    try:
        yield apps
    finally:
        # Only this process's own outstanding calls are cancelled.
        apps.cancel_all()


@contextmanager
def _runtime(request, directory, inventory, factory=None, *, library=None, calibration=None):
    options = {key: value for key, value in (('library', library), ('calibration', calibration)) if value is not None}
    if factory is not None:
        yield factory(request, directory, inventory, **options)
        return
    from symblic.mica import search as M
    with _applications(directory) as apps:
        yield M.MicaRun(request, directory, apps, inventory, **options)


@contextmanager
def _project_runtime(objective, directory, inventory, budget, outputs, factory=None, *, library=None,
                     calibration=None, artifact_format='javascript_script'):
    options = {key: value for key, value in (('library', library), ('calibration', calibration)) if value is not None}
    if artifact_format != 'javascript_script':
        options['artifact_format'] = artifact_format
    if factory is not None:
        yield factory(objective, directory, inventory, budget, outputs, **options)
        return
    from symblic.mica import project as P
    with _applications(directory) as apps:
        yield P.MicaProject(objective, directory, apps, inventory, budget, outputs, **options)


def _calibration(path):
    from symblic.graph import run as G
    from symblic.mica import search as M
    from symblic.mica import calibration as H
    return H.normalize(_json_file(path, max_bytes=H.MAX_BYTES), G._hash(M.implementation_identity()))


def _bundle_artifacts(result, *, runtime_identity, include_text, include_archive):
    from symblic.mica import bundle as B
    bundle = result['bundle']
    B.verify_bundle(bundle, runtime_identity=runtime_identity)
    checks = result.get('module_checks') or {}
    if checks.get('passed') is not True or checks.get('bundle_sha256') != bundle['sha256']:
        raise CliError('bundle_checks', 'Completed bundle lacks matching successful module checks.')
    artifacts = []
    for file in bundle['files']:
        row = {'file': file['path'], 'sha256': file['sha256'], 'bytes': file['utf8_bytes'],
               'role': file['role'], 'assurance': result.get('assurance', 'TESTED')}
        if include_text:
            row['text'] = file['text']
        artifacts.append(row)
    extra = {'bundle_sha256': bundle['sha256']}
    if include_archive:
        raw = B.archive(bundle)
        extra['archive'] = {'file': 'symblic-modules.zip', 'mime_type': 'application/zip',
                            'sha256': hashlib.sha256(raw).hexdigest(),
                            'bytes': len(raw), 'base64': base64.b64encode(raw).decode('ascii')}
    return artifacts, extra


def _objective_file(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise CliError('objective_file', 'Expected a regular objective text file of at most 65536 bytes.')
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise CliError('objective_file', 'Objective text exceeds 65536 bytes.')
    return raw.decode('utf-8')


def _project_manifest(directory):
    path = Path(directory) / 'project-manifest.json'
    if path.exists() or path.is_symlink():
        from symblic.mica import project as P
        return P.load_project(directory)
    return None


def _run_records(directory):
    """Read only existing sealed records; never infer completion from file presence."""
    from symblic.mica import contracts as C
    from symblic.mica import routing as R

    from symblic.graph import run as G
    from symblic.policy import store as S
    folder = Path(directory)
    if any(parent.is_symlink() for parent in (folder, *folder.parents)):
        raise CliError('run_directory', 'Symlinked construction paths are refused.')
    S._directory(folder)
    raw = G._unseal(G._read(folder / 'mica-manifest.json'))
    manifest = {k: v for k, v in raw.items() if k != 'sha256'}
    if manifest.get('version') != VERSION or manifest.get('mode') not in MODES:
        raise CliError('manifest', 'Unsupported construction manifest.')
    C.normalize_request(manifest['request'])
    R.normalize_inventory(manifest['inventory'])
    result = None
    result_path = folder / 'mica-result.json'
    if result_path.exists() or result_path.is_symlink():
        raw_result = G._unseal(G._read(result_path))
        result = {k: v for k, v in raw_result.items() if k != 'sha256'}
        if result.get('manifest_sha256') != G._hash(manifest):
            raise CliError('result_pin', 'Construction result does not match its frozen manifest.')
        from symblic.mica import search as M
        M.verify_result_artifacts(result, manifest['request'], manifest['identity'])
        M.verify_host_costs(result, folder, manifest['identity'])
    return folder, manifest, result


def _status(directory):
    from symblic.mica import contracts as C

    from symblic.graph import run as G
    folder, manifest, result = _run_records(directory)
    return {'version': VERSION, 'status': result['status'] if result else 'incomplete',
            'mode': manifest['mode'], 'request_sha256': C.digest(manifest['request']),
            'manifest_sha256': G._hash(manifest), 'directory': str(folder),
            'calls': result.get('calls') if result else None,
            'costs': result.get('costs', {}) if result else {},
            'assurance': result.get('assurance') if result else None,
            'note': 'Missing final result is incomplete, not authorization to redispatch unknown calls; resume uses native journals.'}


def _model_controls(inventory, implementation):
    return {'primary': [f"ollama:{r['model']}@{r['node']}#" + (r['digest'] or 'unobserved') for r in inventory],
            'fallback': [], 'stronger_fallback': [],
            'settings': {'inventory': inventory, 'construction_implementation': implementation,
                         'component_library': 'disabled_for_benchmark_assignments',
                         'calibration': 'disabled_for_benchmark_assignments',
                         'sampling_seed': 'not_exposed_by_current_native_adapter'}}


def dispatch(args, *, runtime_factory=None, project_factory=None, implementation=None):
    """Run one parsed command and return its JSON-able result (factories let tests inject fakes)."""
    from symblic.mica import contracts as C
    if args.help or args.command is None:
        return {'version': VERSION, 'commands': list(COMMANDS), 'usage': parser().format_help()}
    if args.command == 'capabilities':
        from symblic.mica import bench as B
        rows = _inventory(args.inventory) if args.inventory else []
        return {'version': VERSION, 'commands': list(COMMANDS), 'modes': list(MODES),
                'mode_factors': B.MODE_FACTORS,
                'language': 'javascript', 'contract_version': C.VERSION,
                'request_fields': ['objective', 'requirements', 'exports', 'tests', 'allowed_outputs', 'budget'],
                'budget_defaults': C.DEFAULT_BUDGET, 'budget_limits': C.BUDGET_LIMITS,
                'inventory': rows, 'inventory_scope': 'explicit_snapshot_not_live_admission',
                'provider_lane': 'symblic.providers.applicators: ollama:MODEL@NODE, local models only',
                'component_reuse': 'optional private --library; exact identities and independent rechecks',
                'artifact_formats': list(FORMATS),
                'archive': 'artifacts --archive returns verified module files as deterministic base64 ZIP; no output paths are written',
                'calibration': 'calibration --run PATH freezes selected terminal evidence; --calibration FILE seeds exact-checker routing, not independent evaluation',
                'deterministic_construction': {'supported': ['affine_integer_v1'],
                    'input': 'native planner catalogue or execute REQUEST --initial-plan PLAN',
                    'scope': 'Explicit bounded affine family; conditional uniqueness, then interface/root checks. No general correctness proof.'},
                'assurance': 'finite tests; formal prose/code correctness not established',
                'root_specification': 'explicit request or budgeted objective synthesis; generated requirements/tests remain model-proposed, not independent truth'}
    if args.command == 'inventory':
        rows, skipped = snapshot_inventory()
        return {'version': VERSION, 'status': 'snapshot', 'inventory': rows, 'skipped': skipped,
                'scope': 'models each configured host listed at this moment; readiness is not admission'}
    if args.command == 'calibration':
        from symblic.mica import calibration as H
        return H.freeze(args.run)
    if args.command == 'validate':
        request = C.normalize_request(_json_file(args.request))
        response = {'version': VERSION, 'status': 'valid_request', 'request': request,
                    'request_sha256': C.digest(request), 'assurance': 'schema_validation'}
        if args.plan:
            plan = C.validate_plan(request, _json_file(args.plan))
            response.update(status='valid_plan', plan=plan, assurance='validated_contract_graph_not_implemented')
        return response
    if args.command in ('plan', 'execute'):
        objective = _objective_file(args.objective_file) if args.objective_file else args.objective
        if bool(args.request) == (objective is not None):
            raise CliError('task_input', 'Supply exactly one request JSON or an objective text/file.')
        # An explicit validated plan may consist entirely of native finite units
        # or rechecked components. The runtime decides whether a model is needed.
        inventory = _inventory(args.inventory, require_ready=not bool(getattr(args, 'initial_plan', None)))
        calibration = _calibration(args.calibration) if args.calibration else None
        if objective is not None:
            if getattr(args, 'initial_plan', None):
                raise CliError('initial_plan_authority', 'An initial plan requires an explicit root request, not an objective proposal.')
            if not args.budget:
                raise CliError('objective_budget', 'Objective synthesis requires an explicit total --budget JSON file.')
            budget = C._budget(_json_file(args.budget))
            artifact_format = args.artifact_format or 'javascript_script'
            outputs = args.output or (['index.mjs'] if artifact_format == 'javascript_modules' else ['result.js'])
            for output in outputs:
                C._path(output)
            if any(a != b and b.startswith(a + '/') for a in outputs for b in outputs):
                raise CliError('output_paths', 'Allowed output files cannot be ancestors of one another.')
            if artifact_format == 'javascript_script' and len(outputs) != 1:
                raise CliError('artifact_format', 'Script output requires exactly one file.')
            if artifact_format == 'javascript_modules' and any(not p.endswith(('.js', '.mjs')) or p == '__symblic_test__.mjs' for p in outputs):
                raise CliError('artifact_format', 'Module output paths must use .js/.mjs and exclude the verifier name.')
            with _project_runtime(objective, args.dir, inventory, budget, outputs, project_factory,
                                  library=args.library, calibration=calibration, artifact_format=artifact_format) as run:
                return run.plan(mode=args.mode) if args.command == 'plan' else run.execute(mode=args.mode)
        if args.budget or args.output or args.artifact_format is not None:
            raise CliError('request_overrides', 'An explicit request already fixes its budget, allowed outputs and artifact format.')
        request = C.normalize_request(_json_file(args.request))
        initial_plans = ([C.validate_plan(request, _json_file(args.initial_plan))]
                         if getattr(args, 'initial_plan', None) else None)
        with _runtime(request, args.dir, inventory, runtime_factory, library=args.library, calibration=calibration) as run:
            return (run.plan(mode=args.mode) if args.command == 'plan'
                    else run.execute(mode=args.mode, initial_plans=initial_plans))
    if args.command == 'resume':
        project = _project_manifest(args.dir)
        if project is not None:
            with _project_runtime(project['objective'], args.dir, project['inventory'], project['budget'],
                                  project['allowed_outputs'], project_factory, library=project.get('library'),
                                  calibration=project.get('calibration'), artifact_format=project.get('artifact_format', 'javascript_script')) as run:
                return run.execute(mode=project['mode'])
        folder, manifest, _ = _run_records(args.dir)
        # Resume must retain the original inventory, strategy, budget and proposals.
        # The applicators still check the configured hosts again on any new call.
        with _runtime(manifest['request'], folder, manifest['inventory'], runtime_factory,
                      library=manifest.get('library'), calibration=manifest.get('calibration')) as run:
            return run.execute(mode=manifest['mode'], initial_plans=manifest.get('initial_plans'))
    if args.command == 'status':
        project = _project_manifest(args.dir)
        if project is not None:
            from symblic.mica import project as P
            report = P.read_project_result(args.dir)
            return {'version': VERSION, 'status': report['status'] if report else 'incomplete',
                    'mode': project['mode'], 'root_requirements': 'model_proposed_not_independent_oracle',
                    'calls': report.get('calls') if report else None,
                    'costs': report.get('costs', {}) if report else {},
                    'assurance': report.get('assurance') if report else None,
                    'provenance': report.get('provenance') if report else None}
        return _status(args.dir)
    if args.command == 'artifacts':
        project = _project_manifest(args.dir)
        if project is not None:
            from symblic.mica import project as P
            result = P.read_project_result(args.dir)
            runtime_identity = project['identity']['construction']
        else:
            _, manifest, result = _run_records(args.dir)
            runtime_identity = manifest['identity']
        artifacts = []
        if result and result.get('status') == 'done':
            if result.get('bundle') is not None:
                artifacts, extra = _bundle_artifacts(result, runtime_identity=runtime_identity,
                    include_text=args.include_text, include_archive=args.archive)
                return {'version': VERSION, 'status': result['status'], 'artifacts': artifacts,
                        'provenance': result.get('provenance'), **extra}
            if args.archive:
                raise CliError('archive_format', 'ZIP export requires a completed JavaScript module bundle.')
            output = result.get('output')
            if (type(output) is not dict or type(output.get('text')) is not str
                    or output.get('sha256') != hashlib.sha256(output['text'].encode()).hexdigest()):
                raise CliError('artifact_pin', 'Output source digest is missing or changed.')
            artifact = {key: output[key] for key in ('file', 'sha256')}
            artifact.update(bytes=len(output['text'].encode()), assurance=result.get('assurance', 'TESTED'))
            if args.include_text:
                artifact['text'] = output['text']
            artifacts.append(artifact)
        return {'version': VERSION, 'status': result['status'] if result else 'incomplete', 'artifacts': artifacts,
                'provenance': result.get('provenance') if result else None}
    if args.command == 'report':
        from symblic.mica import bench as B
        return B.MicaBenchmark(args.root, args.id, args.freeze).report()
    if args.command == 'benchmark':
        from symblic.mica import bench as B
        inventory = _inventory(args.inventory, require_ready=args.run)
        if not inventory:
            raise CliError('inventory_empty', 'Benchmark model controls require an explicit inventory.')
        if implementation is None:
            from symblic.mica import search as M
            implementation = M.implementation_identity()
        controls = _model_controls(inventory, implementation)
        if args.freeze:
            if args.fixture:
                raise CliError('frozen_fixture', 'Resume uses only the already frozen fixture inputs.')
            bench = B.MicaBenchmark(args.root, args.id, args.freeze)
            with bench._lock():
                _, plan, _ = bench._load(current=True)
            if args.split is not None and args.split != plan['split']:
                raise CliError('benchmark_split', 'Resume must preserve the frozen experiment split.')
            if any(arm['controls']['model'] != controls for arm in plan['arms']):
                raise CliError('benchmark_controls', 'Inventory or construction implementation changed after freeze.')
        else:
            if not args.fixture:
                raise CliError('fixtures', 'Supply at least one evaluator-owned fixture file.')
            fixtures = [_json_file(path) for path in args.fixture]
            budget = C.normalize_request(fixtures[0]['request'])['budget']
            bench = B.MicaBenchmark.freeze(args.root, args.id, fixtures, model=controls, budget=budget,
                                            repetitions=args.repetitions, order_seed=args.seed, split=args.split or 'dev')
        if args.run:
            def runner(*, request, mode, assignment, seed, controls):
                del seed  # Current native adapter does not expose deterministic provider sampling.
                if runtime_factory is None:
                    from symblic.mica import search as M
                    if M.implementation_identity() != controls['model']['settings']['construction_implementation']:
                        raise CliError('implementation_pin', 'Construction implementation changed after freeze.')
                directory = bench.path / 'runs' / assignment['id'] / 'native'
                with _runtime(request, directory, inventory, runtime_factory) as run:
                    return run.execute(mode=mode)
            bench.run_all(runner)
        report = bench.report()
        resolved = (report['completed_receipts'] == report['assigned'] and all(
            row['status'] not in ('pending', 'unknown', 'damaged', 'stopped', 'blocked') and row['grade_status'] != 'unknown'
            for row in report['assignments']))
        return {'version': VERSION, 'status': ('evaluated' if resolved else 'incomplete') if args.run else 'frozen',
                'freeze_sha256': bench.freeze_sha256, 'report': report}
    raise CliError('command', 'Unsupported command.')


def main(argv=None, *, out=None, runtime_factory=None, project_factory=None, implementation=None):
    """Entry point: print one JSON document; exit 0 on success, 1 for an unfinished construction, 2 on refusal."""
    stream = out or sys.stdout
    try:
        raw = list(sys.argv[1:] if argv is None else argv)
        if raw and raw[0] == 'checkpack':
            from symblic.mica import checkpack_cli as checkpack_cli
            return checkpack_cli.main(raw[1:], out=stream)
        if raw and raw[0] == 'forge':
            from symblic.mica import forge_cli as forge_cli
            return forge_cli.main(raw[1:], out=stream)
        if raw and raw[0] == 'promote':
            from symblic.mica import promote as promote_cli
            return promote_cli.main(raw[1:], out=stream)
        args = parser().parse_args(raw)
        result = dispatch(args, runtime_factory=runtime_factory, project_factory=project_factory,
                          implementation=implementation)
        code = int(args.command in ('plan', 'execute', 'resume') and result.get('status') not in ('done', 'planned'))
    except KeyboardInterrupt:
        result, code = {'ok': False, 'error': {'code': 'interrupted', 'message': 'Interrupted; inspect durable journals before resume.'}}, 130
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        result, code = {'ok': False, 'error': {'code': getattr(exc, 'code', type(exc).__name__),
                        'message': str(exc)[:1000]}}, 2
    except Exception as exc:  # noqa: BLE001 - command boundary always emits finite JSON diagnostics
        result, code = {'ok': False, 'error': {'code': type(exc).__name__,
                        'message': 'Command failed; retain the run directory and inspect durable status before resume.'}}, 2
    try:
        payload = json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        payload = '{"ok":false,"error":{"code":"invalid_result","message":"Command result is not finite JSON; inspect durable status."}}'
        code = 2
    print(payload, file=stream)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
