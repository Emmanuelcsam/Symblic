"""MICA from Forge: runs an accepted Forge handoff (a frozen specification) through MicaRun.

What it is for
    Forge (symblic/forge) is Symblic's specification workshop. Once a pure-function handoff is accepted there,
    this adapter checks an explicit binding (every criterion mapped to a finite JavaScript example) and runs the
    fixed plan through the existing MicaRun journal; it never lets a new planner replace the accepted design.

Depends on: symblic.forge (core, exports, store), integration.host.symblic_forge_bridge.frozen (a pure read of a
frozen handoff from the Forge store), symblic.graph.run, search.py, contracts.py, routing.py,
source_identity.py. Run by forge_cli.py (and, in the original host, by an owner-only HTTP API).

Details
    Explicit frozen Forge contracts -> existing MICA; no prose oracle or executor.

    Only a trusted caller may use the binding/dispatch APIs. Caller-supplied
    examples express an interpretation, not semantic completeness of Forge prose.
    This module never accepts a Forge proposal, launches a worker, or reads a path
    declared by project prose. Execution delegates to MicaRun's original journal.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from integration.host import symblic_forge_bridge as F
from symblic.forge import core as FC
from symblic.forge import exports as FE
from symblic.forge import store as FS
from symblic.forge.store import encode, identifier
from symblic.graph import run as G
from symblic.mica import search as M
from symblic.mica import contracts as C
from symblic.mica import routing as R
from symblic.mica import source_identity as I

VERSION = 1
MAX_ARTIFACT_BYTES = 2_000_000
SCOPE = 'owner_bound_finite_examples_semantic_completeness_unassessed'
_LOADED_SHA = _symblic_import_identity['sha256']


class ForgeMicaError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise ForgeMicaError(code, message)


def _keys(row, names):
    if type(row) is not dict or set(row) != set(names):
        _fail('fields', 'Missing or unexpected explicit binding fields.')


def _by_id(rows, field='id'):
    if type(rows) is not list or len(rows) > 256:
        _fail('bound', 'Binding collection exceeds 256 rows.')
    result = {}
    for row in rows:
        if type(row) is not dict or type(row.get(field)) is not str or row[field] in result:
            _fail('identity', 'Binding identities must be present and unique.')
        result[row[field]] = row
    return result


def _exact_ids(actual, expected, label):
    if set(actual) != set(expected):
        _fail('coverage', label + ' must bind every accepted identity exactly once.')


def _signature(name, signature):
    if type(name) is not str or not C._NAME.fullmatch(name) or type(signature) is not str:
        _fail('signature', 'A unit signature must name a JavaScript function.')
    match = re.fullmatch(re.escape(name) + r'\(([^()]*)\)', signature)
    parameters = [p.strip() for p in match[1].split(',')] if match and match[1].strip() else []
    if not match or any(not C._NAME.fullmatch(p) for p in parameters) or len(set(parameters)) != len(parameters):
        _fail('signature', 'Use exact functionName(arg,...) signatures with unique simple parameters.')


def _json(text):
    if type(text) is not str or len(text.encode('utf-8')) > MAX_ARTIFACT_BYTES:
        _fail('artifact_bound', 'Frozen artifact exceeds the adapter byte limit.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('artifact_json', 'Duplicate frozen artifact key.')
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=pairs,
                          parse_constant=lambda _: _fail('artifact_json', 'Nonfinite artifact JSON.'))
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ForgeMicaError):
            raise
        _fail('artifact_json', 'Frozen artifact is not bounded JSON.')


def _regular_bytes(path, maximum=MAX_ARTIFACT_BYTES):
    """Bounded regular-file read; refuse special files before opening a reader."""
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        _fail('path', 'Symlinked retained path refused.')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            _fail('path', 'Retained file is not a bounded regular file.')
        with os.fdopen(os.dup(descriptor), 'rb') as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        if (len(raw) > maximum or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            _fail('path', 'Retained file changed during the bounded read.')
        return raw
    finally:
        os.close(descriptor)


def implementation_identity():
    """The Forge adapter, Forge compiler, binding dependencies and MICA implementation a binding depends on."""
    path = Path(__file__)
    if hashlib.sha256(_regular_bytes(path)).hexdigest() != _LOADED_SHA:
        _fail('identity', 'Forge MICA adapter changed; use a fresh process.')
    problems = I.audit({I.relative_path(path): _LOADED_SHA})
    if problems:
        _fail('identity', 'Forge MICA loaded source identity refused.')
    compiler = FE.compiler_identity()
    if compiler.get('restart_required'):
        _fail('identity', 'Forge compiler/exporter requires restart.')
    dependencies = {}
    for module in (F, FS):
        source = Path(module.__file__)
        name = I.relative_path(source)
        marker = getattr(module, '_symblic_import_identity', {})
        expected = marker.get('sha256')
        if (marker.get('matched') is not True or
                hashlib.sha256(_regular_bytes(source)).hexdigest() != expected or
                I.audit({name: expected})):
            _fail('identity', 'Forge binding dependency changed or lacks an actual loaded-source marker: ' + name)
        dependencies[name] = expected
    return {'adapter': _LOADED_SHA, 'forge': compiler, 'dependencies': dependencies,
            'mica': M.implementation_identity()}


def _accepted_authority(project):
    branch = FC.active_branch(project)
    # Retain human text/facts and exact links, not full transcript/revision history.
    def authority(row):
        return {k: copy.deepcopy(v) for k, v in row.items()
                if k != 'revisions'}
    return {'original_idea': project['original_idea'],
            'requirements': [authority(r) for r in FE.accepted(branch['statements'])],
            'entities': {k: [authority(r) for r in FE.accepted(rows)] for k, rows in branch['entities'].items()},
            'scope': copy.deepcopy(branch['scope']), 'definitions': copy.deepcopy(branch['definitions']),
            'vocabulary': copy.deepcopy(branch['vocabulary'])}


def prepare(project_id, handoff_id, binding, *, db, current=True):
    """Read a retained handoff and validate owner-authored executable bindings.

    `current=False` is reserved for replay of an already retained adapter origin.
    It does not grant authority to start a fresh run from an obsolete handoff.
    """
    C._bounded(binding)
    _keys(binding, ('version', 'budget', 'artifact_format', 'allowed_outputs', 'exports',
                    'criteria', 'forbidden', 'units'))
    if type(binding['version']) is not int or binding['version'] != VERSION:
        _fail('version', 'Unsupported executable binding version.')
    if type(binding['budget']) is not dict or set(binding['budget']) != set(C.DEFAULT_BUDGET):
        _fail('budget', 'Supply every original MICA budget field explicitly.')
    if binding['budget']['max_candidates'] != 1:
        _fail('budget', 'This exact Forge unit mapping supports one plan; set max_candidates=1 explicitly.')
    identity = implementation_identity()
    _, handoff, artifacts, _ = F.frozen(project_id, handoff_id, db=db, current=current)
    if identity['forge'] != handoff['compiler']:
        _fail('compiler', 'Frozen Forge compiler differs from the current loaded compiler.')
    for artifact in artifacts:
        if len(artifact['text'].encode('utf-8')) > MAX_ARTIFACT_BYTES:
            _fail('artifact_bound', 'Frozen artifact exceeds the adapter byte limit.')
    by_format = {a['format']: a for a in artifacts}
    manifest = _json(by_format['manifest']['text'])
    _keys(manifest, ('format', 'project', 'fingerprint'))
    if manifest['format'] != 'symblic-forge-manifest/1':
        _fail('manifest', 'Unsupported retained Forge manifest.')
    project = FC.validate_project(manifest['project'])
    if (project['id'] != project_id or project['revision'] != handoff['source_revision'] or
            project['active_branch'] != handoff['branch_id'] or
            FC.fingerprint(project) != handoff['fingerprint'] or manifest['fingerprint'] != handoff['fingerprint']):
        _fail('lineage', 'Retained manifest and frozen handoff disagree.')
    cards = _json(by_format['tasks']['text'])
    if cards != FE.task_cards(project) or _json(by_format['sheet']['text']) != FE.spec_sheet(project):
        _fail('lineage', 'Retained task or sheet authority differs from the frozen manifest.')
    if by_format['construction']['text'] != FE.construction_plan(project):
        _fail('lineage', 'Retained human construction text differs from its manifest.')
    branch = FC.active_branch(project)
    authority = _accepted_authority(project)
    entities = authority['entities']
    for kind in ('agents', 'models', 'cluster', 'dependencies', 'architectures'):
        if entities[kind]:
            _fail('unsupported_entities', 'Accepted ' + kind + ' need an explicit adapter; nothing was dropped.')
    components = _by_id(entities['components'])
    for component in components.values():
        if component.get('effects') or component.get('persistent_state', '').strip():
            _fail('effects', 'Accepted component ' + component['id'] + ' requests effects or persistent state incompatible with pure functions.')
    if any(row.get('subjective') for row in entities['criteria']):
        _fail('subjective', 'Subjective accepted criteria cannot be executed by this pure-function adapter.')
    requirements = _by_id(authority['requirements'])
    for ident in requirements:
        C._identifier(ident)  # Preserve IDs or refuse, never silently rename.
    tests = []; mappings = []
    for kind in ('criteria', 'forbidden'):
        accepted = _by_id(entities[kind])
        supplied = _by_id(binding[kind])
        _exact_ids(supplied, accepted, kind)
        for ident, row in accepted.items():
            candidate = supplied[ident]
            _keys(candidate, ('id', 'call', 'expected'))
            tests.append({'requirement_ids': copy.deepcopy(row['requirement_ids']),
                          'call': candidate['call'], 'expected': candidate['expected']})
            mappings.append({'kind': kind, 'forge_id': ident, 'root_test_index': len(tests) - 1,
                             'semantics': SCOPE})
    request = C.normalize_request({'objective': project['original_idea'],
        'requirements': [{'id': r['id'], 'text': r['text'], 'acceptance': 'TESTED'} for r in requirements.values()],
        'exports': binding['exports'], 'tests': tests, 'budget': binding['budget'],
        'artifact_format': binding['artifact_format'], 'allowed_outputs': binding['allowed_outputs'],
        'assumptions': []})
    supplied_units = _by_id(binding['units'])
    cards_by_id = _by_id(cards)
    _exact_ids(supplied_units, cards_by_id, 'units')
    unit_exports = {}; signatures = {}
    for ident, card in cards_by_id.items():
        item = supplied_units[ident]
        _keys(item, ('id', 'signatures', 'checks', 'output_path'))
        C._identifier(ident)
        supplied_signatures = _by_id(item['signatures'], 'name')
        _exact_ids(supplied_signatures, card['defines'], 'unit signatures')
        if not supplied_signatures:
            _fail('exports', 'Every Forge unit must declare at least one function symbol.')
        for name, signature in supplied_signatures.items():
            _keys(signature, ('name', 'signature'))
            _signature(name, signature['signature'])
            if name in unit_exports:
                _fail('exports', 'Duplicate accepted function export.')
            unit_exports[name] = ident; signatures[name] = signature['signature']
        if card['component_id'] not in components:
            _fail('component', 'Unit component must be accepted.')
    for exported in request['exports']:
        if exported['name'] not in signatures or signatures[exported['name']] != exported['signature']:
            _fail('exports', 'Public signature must equal its explicit accepted-unit binding.')
    contracts = []
    for ident, card in cards_by_id.items():
        item = supplied_units[ident]
        examples = item['checks']
        if type(examples) is not list or len(examples) != len(card['verification']):
            _fail('checks', 'Every original unit check needs an explicit indexed example.')
        for index, example in enumerate(examples):
            _keys(example, ('index', 'call', 'expected'))
            if type(example['index']) is not int or example['index'] != index:
                _fail('checks', 'Unit check order/index differs from frozen prose.')
        dependencies = card['dependencies']
        if any(dep not in cards_by_id for dep in dependencies):
            _fail('dependency', 'Only accepted unit dependencies are supported.')
        if any(name not in unit_exports for name in card['requires']):
            _fail('dependency', 'Required symbols must be functions of declared units.')
        if {unit_exports[name] for name in card['requires']} != set(dependencies):
            _fail('dependency', 'Declared requires and unit dependency IDs must agree exactly.')
        C._path(item['output_path'])
        scoped = {'unit': card, 'component': components[card['component_id']],
                  'scope': branch['scope'], 'definitions': branch['definitions'], 'vocabulary': branch['vocabulary']}
        # Literal accepted data preserves words/facts; it grants no filesystem/effect authority.
        body = card['objective'] + '\nFrozen accepted contract data:\n' + encode(scoped)
        contracts.append({'contract_id': ident, 'root_requirement_ids': [r['id'] for r in card['requirements']],
            'objective': card['objective'], 'dependency_contract_ids': list(dependencies),
            'output_artifacts': [item['output_path']], 'permitted_effects': [],
            'failure_policy': {'action': 'stop', 'retries': request['budget']['retries']},
            'unit': {'names': list(card['defines']), 'heading': ', '.join(signatures[n] for n in card['defines']),
                     'body': body, 'uses': [signatures[n] for n in card['requires']], 'setup': '',
                     'examples': [[e['call'], e['expected']] for e in examples]},
            'verification_obligations': [{'kind': 'unit_examples', 'requirement_ids': [r['id'] for r in card['requirements']]}]})
    plan = C.validate_plan(request, {'id': 'forge_bound', 'contracts': contracts, 'assumptions': []})
    origin = {'project': project_id, 'handoff': handoff_id, 'source_revision': handoff['source_revision'],
        'branch_id': handoff['branch_id'], 'fingerprint': handoff['fingerprint'],
        'artifacts': [{k: a[k] for k in ('id', 'format', 'sha256', 'source_revision')} for a in artifacts],
        'accepted_authority': authority, 'binding_sha256': C.digest(binding),
        'binding_provenance': 'explicit_owner_supplied', 'semantic_completeness': 'unassessed',
        'scope': SCOPE, 'identity': identity}
    return G._seal({'version': VERSION, 'binding': copy.deepcopy(binding), 'request': request,
                    'plan': plan, 'origin': origin, 'criterion_mapping': mappings})


def _workspace(folder):
    path = Path(folder)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        _fail('path', 'Supply an absolute nonsymlink construction folder.')
    path = Path(os.path.abspath(path))
    if path.exists() and not path.is_dir():
        _fail('path', 'Construction folder is not a directory.')
    return path


def _validate_prepared(value, db, *, current):
    G._unseal(value)
    _keys(value, ('version', 'binding', 'request', 'plan', 'origin', 'criterion_mapping', 'sha256'))
    expected = prepare(value['origin']['project'], value['origin']['handoff'], value['binding'], db=db, current=current)
    if expected != value:
        _fail('prepared', 'Prepared binding differs from complete retained-source revalidation.')
    return expected


def _origin_record(prepared, folder, inventory, request_id):
    """Pure lexical receipt construction, never resolve/stat a reader's folder."""
    G._unseal(prepared)
    path = Path(folder)
    if not path.is_absolute() or '..' in path.parts:
        _fail('path', 'Origin folder must be an absolute normalized path.')
    return {'request_id': identifier(request_id), 'folder': os.path.abspath(path),
            'prepared_sha256': prepared['sha256'], 'inventory': R.normalize_inventory(inventory),
            'identity': prepared['origin']['identity']}


def verify_result_origin(result, prepared, folder, inventory, request_id):
    """Check exact frozen origin/finite scope; no source read, probe or dispatch.

    This does not authenticate a host owner or replace prepared-source validation
    and MICA's native/artifact audits. Callers supply their retained original pins.
    """
    expected = _origin_record(prepared, folder, inventory, request_id)
    if (type(result) is not dict or result.get('forge_origin') != expected or
            result.get('scope') != SCOPE or result.get('semantic_completeness') != 'unassessed'):
        _fail('origin', 'Result differs from the original Forge origin or finite-example scope.')
    return True


class ForgeMicaRun:
    """Owner host wrapper; the existing MicaRun exclusively owns dispatch/replay.

    The Forge immutable receipt pins folder, binding, inventory and implementation
    before entering core. No duplicate executor, budget clock or call ledger.
    """
    def __init__(self, prepared, folder, applicators, inventory, *, db, request_id, stop=None):
        self.prepared = copy.deepcopy(prepared)
        self.root = _workspace(folder)
        self.apps = applicators; self.inventory = R.normalize_inventory(inventory)
        self.db = db; self.request_id = identifier(request_id); self.stop = stop

    def plan(self):
        """Freeze the accepted Forge plan without building anything."""
        return self.execute(plan_only=True)

    def execute(self, *, plan_only=False):
        if type(plan_only) is not bool:
            _fail('mode', 'plan_only must be Boolean.')
        _workspace(self.root)
        key = 'mica-origin-' + hashlib.sha256(self.request_id.encode()).hexdigest()
        envelope = {'operation': 'forge-mica/1', 'request_id': self.request_id,
                    'folder': str(self.root), 'prepared': self.prepared, 'inventory': self.inventory}
        with self.db.connection() as conn:
            prior = self.db._replay(conn, key, envelope)
        prepared = _validate_prepared(self.prepared, self.db, current=prior is None)
        # Even historical replay must rehash artifacts and verify original pins.
        record = _origin_record(prepared, self.root, self.inventory, self.request_id)
        with self.db.connection(True) as conn:
            prior = self.db._replay(conn, key, envelope)
            fresh = prior is None
            if fresh:
                if self.root.exists() and any(self.root.iterdir()):
                    _fail('path', 'A fresh Forge run requires an empty workspace.')
                # One existing transaction checks accepted state and binds the
                # folder. Never nest another Store connection inside its writer.
                current = json.loads(self.db._row(conn, prepared['origin']['project'])['document'])
                if (current['active_branch'] != prepared['origin']['branch_id'] or
                        FC.fingerprint(current) != prepared['origin']['fingerprint']):
                    _fail('stale', 'Accepted Forge specification changed before reserving this build.')
                folder_key = 'mica-folder-' + hashlib.sha256(str(self.root).encode()).hexdigest()
                folder_prior = self.db._replay(conn, folder_key, envelope)
                if folder_prior is None:
                    self.db._receipt(conn, folder_key, envelope, record)
                elif folder_prior != record:
                    _fail('origin', 'Construction folder belongs to another Forge request.')
                self.db._receipt(conn, key, envelope, record)
            elif prior != record:
                _fail('origin', 'Original immutable Forge MICA receipt differs.')
        manifest_path = self.root / 'mica-manifest.json'
        if not fresh and not manifest_path.exists() and not manifest_path.is_symlink():
            return {'status': 'unknown', 'failure': 'UNRESOLVED_EFFECT', 'request_id': self.request_id,
                    'error': 'Original launch has no retained core manifest; no dispatch was repeated.',
                    'forge_origin': copy.deepcopy(record), 'scope': SCOPE,
                    'semantic_completeness': 'unassessed'}
        if manifest_path.exists() or manifest_path.is_symlink():
            if fresh:
                _fail('origin', 'Unexpected core manifest appeared after the new origin was reserved.')
            # Read only the named core manifest under its existing shared lock.
            import fcntl
            lock_path = self.root / '.mica.lock'
            fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    _fail('path', 'Core lock is not a regular file.')
                try:
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {'status': 'busy', 'request_id': self.request_id, 'scope': SCOPE,
                            'forge_origin': copy.deepcopy(record), 'semantic_completeness': 'unassessed',
                            'error': 'The existing core runner owns this workspace; no new dispatch.'}
                manifest = G._unseal(G._decode(_regular_bytes(manifest_path)))
                if (manifest.get('request') != prepared['request'] or manifest.get('inventory') != self.inventory or
                        manifest.get('initial_plans') != [prepared['plan']] or manifest.get('mode') != 'mica' or
                        manifest.get('identity') != prepared['origin']['identity']['mica'] or
                        manifest.get('library') is not None or manifest.get('calibration') is not None):
                    _fail('origin', 'Existing core manifest differs from the original Forge binding.')
            finally:
                os.close(fd)
        run = M.MicaRun(prepared['request'], self.root, self.apps, self.inventory, stop=self.stop)
        result = run.execute(mode='mica', initial_plans=[prepared['plan']], plan_only=plan_only)
        return {**result, 'forge_origin': copy.deepcopy(record), 'scope': SCOPE,
                'semantic_completeness': 'unassessed'}
