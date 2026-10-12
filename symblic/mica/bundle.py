"""MICA module bundles: compiles a construction into pure ES modules and checks them in a sandbox.

What it is for
    For requests with artifact_format "javascript_modules", compiles accepted units into one public entry plus
    one module per unit with exact static imports, then runs the original and module examples in fresh isolated
    Node.js contexts through bundle_runner.js (a trusted asset next to this file), inside the same Landlock/limits
    sandbox the JavaScript checker uses. Also builds a deterministic ZIP for export.

Depends on: symblic.js (check, contract), symblic.spec.contracts, contracts.py; Node.js 22 at run time.
Used by search.py and cli.py.

Details
    Versioned pure-function ES module bundles, independently checked in the JS sandbox.

    This is a compiler/adapter over validated MICA and SC records, not an interpreter.
    Files stay in memory: normalized paths are labels, never filesystem access requests.
    Finite examples are evidence, not a purity, equivalence or universal-correctness proof.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import io
import json
import math
import os
from pathlib import Path
import posixpath
import re
import subprocess
import stat
import tempfile
import time
import zipfile

from symblic.js import check as JS
from symblic.js import contract as JSC
from symblic.mica import contracts as C
from symblic.spec import contracts as SC

VERSION = 1
MAX_BYTES = 400000
MAX_MODULES = 129
MAX_CASES = 200
MAX_BUNDLE_BYTES = 4000000
MAX_REQUEST_BYTES = 2400000
MAX_ARCHIVE_BYTES = 1000000
HERE = Path(__file__).resolve().parent
RUNNER = HERE / 'bundle_runner.js'          # the Node.js harness that runs module checks (trusted asset)
SCOPE = 'finite_original_script_and_actual_strict_es_module_examples'
_assets = {}
_NAME = re.compile(r'[$A-Za-z_][$A-Za-z_0-9]{0,127}\Z')


class BundleError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise BundleError(code, message)


def _json(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail('shape', 'The module artifact must be bounded finite JSON.')
    if len(raw) > MAX_BUNDLE_BYTES:
        _fail('budget', 'The module artifact exceeds its serialized byte bound.')
    return raw


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _seal(value):
    return {**value, 'sha256': _sha(_json(value))}


def asset_snapshot():
    """Extract only the exact trusted immutable prelude; no candidate selects assets."""
    base = JS.asset_snapshot()
    try:
        with RUNNER.open('rb') as stream:
            runner = stream.read(1000001)
        with Path(__file__).open('rb') as stream:
            own = stream.read(1000001)
    except OSError:
        _fail('unsupported', 'Module verifier assets are unavailable.')
    if len(runner) > 1000000 or len(own) > 1000000:
        _fail('budget', 'Module runner exceeds its asset byte bound.')
    if (not _symblic_import_identity.get('matched') or
            _sha(own) != _symblic_import_identity.get('sha256')):
        _fail('version', 'Module compiler source changed; start a fresh worker.')
    prefix, suffix = b'const PRELUDE = `', b'`;\n'
    if base['runner'].count(prefix) != 1:
        _fail('version', 'The trusted JavaScript prelude boundary changed.')
    tail = base['runner'].split(prefix, 1)[1]
    prelude, found, _ = tail.partition(suffix)
    if not found or b'`' in prelude or b'${' in prelude or b'\\' in prelude or len(prelude) > 20000:
        _fail('version', 'The trusted JavaScript prelude needs an explicit adapter update.')
    current = {'runner': runner, 'prelude': prelude, 'sandbox': base['sandbox'],
               'limiter': base['limiter'], 'parser': base['parser'], 'license': base['license'],
               'classic_runner_identity': base['runner']}
    if _assets and current != _assets:
        _fail('version', 'Module verifier assets changed; start a fresh worker.')
    if not _assets:
        _assets.update(current)
    return dict(_assets)


def _module_runtime(node):
    return {'version': VERSION, 'compiler_sha256': _symblic_import_identity['sha256'],
            'node': node, 'assets': {k: _sha(v) for k, v in asset_snapshot().items()},
            'semantics': 'SourceTextModule_ECMAScript2022_strict_closed_static_graph'}


def runtime_identity():
    return _module_runtime(JS.node_version())

def _path(value):
    C._path(value)
    if not value.endswith(('.js', '.mjs')) or value == '__symblic_test__.mjs':
        _fail('path', 'Module files need .js/.mjs paths distinct from the verifier module.')
    return value


def _relative(source, target):
    value = posixpath.relpath(target, posixpath.dirname(source) or '.')
    return value if value.startswith('.') else './' + value


def _imports(source, names, owners, paths):
    groups = {}
    for name in names:
        target = paths[owners[name]]
        groups.setdefault(target, []).append(name)
    return [{'specifier': _relative(source, path), 'path': path, 'names': selected}
            for path, selected in groups.items()]


def _build(request, plan, manifest):
    request = C.normalize_request(request)
    if request['artifact_format'] != 'javascript_modules':
        _fail('format', 'Module compilation requires explicit javascript_modules artifact format.')
    plan = C.validate_plan(request, plan)
    if not SC.verify_manifest(manifest)['ok']:
        _fail('manifest', 'The accepted unit manifest did not verify.')
    native = manifest['plan']
    if native['externals'] or native['sheet']['shared'] or native['sheet']['template']['text'] != '/*UNITS*/':
        _fail('unsupported', 'Module v1 needs a pure units-only assembly with no external setup.')
    by_id = {r['contract_id']: r for r in plan['contracts']}
    ordered = [by_id[ident] for ident in plan['order']]
    by_exports = {tuple(u['exports']): u for u in native['units']}
    if len(by_exports) != len(ordered):
        _fail('manifest', 'MICA and accepted native unit counts differ.')
    linked = {}
    for row in ordered:
        names = row['unit']['names']
        unit = by_exports.get(tuple(names))
        if not unit or unit['contract']['unit'] != row['unit']:
            _fail('manifest', 'MICA contracts and accepted native unit contracts differ.')
        if any(not _NAME.fullmatch(n) or n.startswith('__symblic') for n in names):
            _fail('name', 'Module bindings reserve the __symblic verifier prefix.')
        if row['unit']['setup'].strip():
            _fail('unsupported', 'Module v1 does not reinterpret script setup as module code.')
        if len(row['output_artifacts']) != 1:
            _fail('layout', 'Each module contract must declare exactly one output file.')
        linked[row['contract_id']] = unit
    if [linked[row['contract_id']]['id'] for row in ordered] != native['assembly_order']:
        _fail('manifest', 'MICA and native dependency assembly orders differ.')
    for row in ordered:
        expected = {linked[ident]['id'] for ident in row['dependency_contract_ids']}
        if expected != set(linked[row['contract_id']]['dependencies']):
            _fail('manifest', 'MICA and native dependency edges differ.')
    entry = _path(request['allowed_outputs'][0])
    paths = {row['contract_id']: _path(row['output_artifacts'][0]) for row in ordered}
    all_paths = [entry, *paths.values()]
    if (len(set(all_paths)) != len(all_paths) or
            any(a != b and b.startswith(a + '/') for a in all_paths for b in all_paths)):
        _fail('layout', 'Entry and unit module paths must be distinct nonoverlapping files.')
    if not set(request['allowed_outputs']) <= set(all_paths):
        _fail('layout', 'Every allowed output must be an actual entry or unit module file.')
    owners = {name: row['contract_id'] for row in ordered for name in row['unit']['names']}
    exports = [r['name'] for r in request['exports']]
    if not set(exports) <= owners.keys():
        _fail('exports', 'Each public export must have an accepted unit owner.')
    files = []
    for row in ordered:
        ident = row['contract_id']; unit = linked[ident]; path = paths[ident]
        names = list(dict.fromkeys(re.match(r'[$A-Za-z_][$A-Za-z_0-9]*', used).group(0)
                                   for used in row['unit']['uses']))
        imports = _imports(path, names, owners, paths)
        code = manifest['artifacts'][unit['id']]['code']
        text = ''.join('import {' + ','.join(i['names']) + '} from ' + json.dumps(i['specifier']) + ';\n' for i in imports)
        text += code + '\nexport {' + ','.join(unit['exports']) + '};\n'
        files.append({'path': path, 'role': 'unit', 'contract_id': ident, 'unit_id': unit['id'],
                      'exports': unit['exports'], 'imports': imports, 'text': text,
                      'sha256': _sha(text.encode()), 'utf8_bytes': len(text.encode())})
    imports = _imports(entry, exports, owners, paths)
    text = ''.join('export {' + ','.join(i['names']) + '} from ' + json.dumps(i['specifier']) + ';\n' for i in imports)
    # Export grouping follows first public-owner appearance; explicit surface retains request order.
    surface = [name for item in imports for name in item['names']]
    files.append({'path': entry, 'role': 'entry', 'contract_id': None, 'unit_id': None,
                  'exports': surface, 'imports': imports, 'text': text,
                  'sha256': _sha(text.encode()), 'utf8_bytes': len(text.encode())})
    if len(files) > MAX_MODULES or sum(f['utf8_bytes'] for f in files) > MAX_BYTES:
        _fail('budget', 'Bundle exceeds 129 modules or 400000 aggregate UTF-8 bytes.')
    return request, plan, entry, exports, files


def compile_bundle(request, plan, artifacts, *, runtime_identity, spec_plan=None, deadline=None):
    """Compile exact accepted records. No models, disk outputs, or correctness claim."""
    deadline = JS._effective_deadline(deadline)
    if not JS.available():
        _fail('unsupported', 'Module compilation needs Node and the required original declaration sandbox.')
    request = C.normalize_request(request)
    plan = C.validate_plan(request, plan)
    native = plan['spec_plan'] if spec_plan is None else spec_plan
    manifest = SC.artifact_manifest(native, artifacts, runtime_identity=runtime_identity)
    request, plan, entry, exports, files = _build(request, plan, manifest)
    for unit in native['units']:
        result = JSC.check(artifacts[unit['id']]['code'], {'version': 1, 'exports': {n:'function' for n in unit['exports']}}, deadline=deadline)
        if not result['passed']:
            code = 'budget' if result['status'] == 'budget' else 'unsupported' if result['status'] == 'error' else 'declarations'
            _fail(code, 'Accepted source must independently pass exact function declarations.')
    result = _seal({'kind':'mica_module_bundle', 'version':VERSION, 'request':request, 'plan':plan,
                    'spec_manifest':manifest, 'source_runtime_sha256':SC.digest(runtime_identity),
                    'module_runtime': globals()['runtime_identity'](), 'entry':entry, 'exports':exports,
                    'files':files, 'assurance':'compiled_exact_records_pending_independent_execution', 'scope':SCOPE})
    _json(result)
    return result


def verify_bundle(bundle, *, runtime_identity=None, source_runtime_identity=None):
    """Reconstruct every file/import/path/hash from sealed contracts on every read."""
    _json(bundle)
    keys = {'kind','version','request','plan','spec_manifest','source_runtime_sha256','module_runtime',
            'entry','exports','files','assurance','scope','sha256'}
    if (type(bundle) is not dict or set(bundle) != keys or bundle['kind'] != 'mica_module_bundle' or
            type(bundle['version']) is not int or bundle['version'] != VERSION or
            bundle['sha256'] != _seal({k:v for k,v in bundle.items() if k != 'sha256'})['sha256']):
        _fail('manifest', 'The module bundle shape or seal differs.')
    manifest = bundle['spec_manifest']
    module_runtime = bundle['module_runtime']
    if type(module_runtime) is not dict or (module_runtime.get('node') is not None and
            (type(module_runtime.get('node')) is not str or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', module_runtime['node']))):
        _fail('version', 'The recorded Node version is invalid.')
    if runtime_identity is not None and source_runtime_identity is not None and runtime_identity != source_runtime_identity:
        _fail('version', 'Conflicting source runtime identities were supplied.')
    expected_runtime = runtime_identity if runtime_identity is not None else source_runtime_identity
    if (bundle['scope'] != SCOPE or bundle['assurance'] != 'compiled_exact_records_pending_independent_execution' or
            bundle['source_runtime_sha256'] != manifest['runtime_sha256'] or
            module_runtime != _module_runtime(module_runtime.get('node'))):
        _fail('version', 'The module bundle runtime, scope or assurance differs.')
    SC.verify_manifest(manifest, runtime_identity=expected_runtime)
    request, plan, entry, exports, files = _build(bundle['request'],bundle['plan'],manifest)
    if (request != bundle['request'] or plan != bundle['plan'] or entry != bundle['entry'] or
            exports != bundle['exports'] or files != bundle['files']):
        _fail('manifest', 'Bundle files differ from exact deterministic compilation.')
    return {'ok':True,'sha256':bundle['sha256'],'files':len(files),'utf8_bytes':sum(f['utf8_bytes'] for f in files),
            'authenticity':'not_established','scope':'reconstructed_closed_module_graph'}


def archive(bundle):
    """Return a deterministic directory-preserving ZIP; no candidate or filesystem writes."""
    verify_bundle(bundle)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as zipped:
        for file in bundle['files']:
            info = zipfile.ZipInfo(file['path'], date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            zipped.writestr(info, file['text'].encode('utf-8'))
            if output.tell() > MAX_ARCHIVE_BYTES:
                _fail('budget', 'Module archive exceeds its finite byte bound.')
    result = output.getvalue()
    if len(result) > MAX_ARCHIVE_BYTES:
        _fail('budget', 'Module archive exceeds its finite byte bound.')
    return result


def _cases(bundle):
    manifest = bundle['spec_manifest']; native = manifest['plan']
    units = {u['id']:u for u in native['units']}
    files = {f['unit_id']:f for f in bundle['files'] if f['role'] == 'unit'}
    cases = []
    for ident in native['assembly_order']:
        unit = units[ident]
        imports = [{'specifier':'./' + files[dep]['path'], 'path':files[dep]['path'], 'names':units[dep]['exports']}
                   for dep in [*unit['closure'], ident]]
        for call, expected in unit['contract']['unit']['examples']:
            cases.append({'scope':'unit','unit_id':ident,'imports':imports,'call':call,'expected':expected})
    for row in bundle['request']['tests']:
        cases.append({'scope':'root','unit_id':None,'imports':[{'specifier':'./' + bundle['entry'],
                      'path':bundle['entry'],'names':bundle['exports']}], 'call':row['call'],'expected':row['expected']})
    if not 1 <= len(cases) <= MAX_CASES:
        _fail('budget', 'Module bundle checks require 1..200 total unit and root examples.')
    JS._cases([(r['call'],r['expected']) for r in cases], None)
    return cases


def _evaluate(bundle, cases, *, deadline=None, case_ms=JS.CASE_MS):
    deadline = JS._effective_deadline(deadline)
    if type(case_ms) is not int or not 1 <= case_ms <= JS.CASE_MS:
        _fail('budget', 'Module case timeout must be 1..3000 milliseconds.')
    if not JS.available():
        return {'version':VERSION,'status':'unsupported','reason':'Node and required Landlock isolation are unavailable','results':[]}
    assets = asset_snapshot()
    body = json.dumps({'files':bundle['files'],'cases':cases,'timeout_ms':case_ms},ensure_ascii=False).encode()
    if len(body) > MAX_REQUEST_BYTES:
        _fail('budget', 'Module runner request exceeds its finite byte bound.')
    wall = 15 + len(cases) * (case_ms / 1000 + 1)
    if deadline is not None:
        wall = min(wall,deadline - time.monotonic())
    if wall <= 0:
        _fail('budget', 'Module verification deadline is exhausted.')
    end = time.monotonic() + wall
    if deadline is not None:
        end = min(end,deadline)
    with tempfile.TemporaryDirectory(prefix='symblic-modules-') as scratch:
        for key, name in [('runner','runner.js'),('prelude','prelude.js'),('sandbox','sandbox.py'),
                          ('limiter','limits.py'),('parser','acorn.js'),('license','acorn-LICENSE.txt')]:
            Path(scratch,name).write_bytes(assets[key])
        node = os.path.realpath(JS.node_path()); node_root = os.path.dirname(os.path.dirname(node))
        argv = ['/usr/bin/python3','-I',str(Path(scratch,'limits.py')),'js',str(min(816,max(1,math.ceil(wall)))),str(os.getpid()),'--',
                '/usr/bin/python3','-I',str(Path(scratch,'sandbox.py')),'--require','--no-unix','--net-connect','1',
                '--rx',node_root,'--cwd',scratch,'--',node,'--experimental-vm-modules','--no-warnings',
                f'--max-old-space-size={JS.HEAP_MB}','--disallow-code-generation-from-strings',str(Path(scratch,'runner.js'))]
        env = {'PATH':'/usr/bin:/bin','HOME':scratch,'LANG':'C.UTF-8','TMPDIR':scratch}
        try:
            proc = subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                    cwd=scratch,env=env,start_new_session=True)
        except OSError:
            return {'version':VERSION,'status':'unsupported','reason':'Module sandbox could not start','results':[]}
        try:
            out, err = JS._communicate_bounded(proc,body,deadline=end,max_output_bytes=JS.MAX_OUTPUT_BYTES)
        except subprocess.TimeoutExpired:
            return {'version':VERSION,'status':'inconclusive','reason':'Module verification wall deadline expired','results':[]}
    if proc.returncode == 125 or b'bad option: --experimental-vm-modules' in err:
        return {'version':VERSION,'status':'unsupported','reason':'Required module runtime/isolation unavailable','results':[]}
    if proc.returncode:
        return {'version':VERSION,'status':'inconclusive','reason':'Module child ended without a complete result','results':[]}
    try:
        value = json.loads(out)
    except (ValueError,UnicodeError):
        _fail('protocol','Module runner returned invalid JSON.')
    if (type(value) is not dict or value.get('version') != VERSION or
            value.get('status') not in ('completed','unsupported','invalid','inconclusive') or type(value.get('results')) is not list or
            (value['status'] == 'completed' and len(value['results']) != len(cases))):
        _fail('protocol','Module runner returned an incomplete response.')
    for row in value['results']:
        if type(row) is not dict or type(row.get('ok')) is not bool or (row['ok'] and type(row.get('value')) is not str):
            _fail('protocol','Module runner returned an invalid case result.')
    return value


def check_bundle(bundle, *, deadline=None, case_ms=JS.CASE_MS):
    """Recheck exact declarations, original script examples, and actual module cases."""
    deadline = JS._effective_deadline(deadline)
    if not JS.available():
        return {'passed':False,'status':'unsupported','stage':'module_runtime','scope':SCOPE,
                'reason':'Node and required Landlock isolation are unavailable'}
    verify_bundle(bundle)
    if bundle['module_runtime'] != runtime_identity():
        _fail('version', 'The current module execution runtime differs from the artifact.')
    cases = _cases(bundle)
    native = bundle['spec_manifest']['plan']; artifacts = bundle['spec_manifest']['artifacts']
    units = {u['id']:u for u in native['units']}
    original = []
    for ident in native['assembly_order']:
        unit = units[ident]; code = artifacts[ident]['code']
        declarations = JSC.check(code,{'version':1,'exports':{n:'function' for n in unit['exports']}},deadline=deadline)
        if not declarations['passed']:
            return {'passed':False,'status':'inconclusive' if declarations['status'] in ('budget', 'error') else 'failed',
                    'stage':'original_declarations','unit_id':ident,'scope':SCOPE,'bundle_sha256':bundle['sha256']}
        source = [artifacts[dep]['code'] for dep in [*unit['closure'],ident]]
        checked = JS.test(source,unit['contract']['unit']['examples'],deadline=deadline)
        original.append({'unit_id':ident,**checked})
        if not checked['passed']:
            return {'passed':False,'status':'failed','stage':'original_unit_examples','checks':original,
                    'scope':SCOPE,'bundle_sha256':bundle['sha256']}
    root = JS.test([artifacts[i]['code'] for i in native['assembly_order']],
                   [(r['call'],r['expected']) for r in bundle['request']['tests']],deadline=deadline)
    if not root['passed']:
        return {'passed':False,'status':'failed','stage':'original_root_examples','checks':original,'root':root,
                'scope':SCOPE,'bundle_sha256':bundle['sha256']}
    observed = _evaluate(bundle,cases,deadline=deadline,case_ms=case_ms)
    result = _report(bundle,cases,observed)
    return {**result,'checks':original,'root':root}


def _report(bundle, cases, observed, *, scope=SCOPE):
    verdicts = []
    for case, result in zip(cases,observed['results']):
        matches = False
        if result.get('ok'):
            try:
                matches = JS.same(JS._parse(result['value']),JS._parse(case['expected']))
            except (ValueError,TypeError):
                pass
        verdicts.append({'scope':case['scope'],'unit_id':case['unit_id'],'call':case['call'],
                         'expected':case['expected'],'passed':matches,'observation':result})
    inconclusive = observed['status'] == 'inconclusive' or any(v['observation'].get('kind') in JS.INCONCLUSIVE for v in verdicts)
    passed = observed['status'] == 'completed' and len(verdicts) == len(cases) and all(v['passed'] for v in verdicts)
    status = ('passed' if passed else 'unsupported' if observed['status'] == 'unsupported' else
              'inconclusive' if inconclusive else 'failed')
    return {'passed':passed,'status':status,'stage':'strict_module_examples','total':len(cases),
            'module_checks':verdicts,'runtime_status':observed['status'],
            'reason':observed.get('reason'),'bundle_sha256':bundle['sha256'],'scope':scope}


def check_cases(bundle, cases, *, deadline=None, case_ms=JS.CASE_MS):
    """Score external finite cases against actual entry modules, with no repair/prompt path.

    Caller-owned held-out examples never modify the bundle/request/SC artifacts.
    This receipt concerns only these observations, not acceptance of original tests.
    """
    deadline = JS._effective_deadline(deadline)
    pairs = JS._cases(cases,None)
    for _, expected in pairs:
        C._expected(expected)
    if not JS.available():
        return {'passed':False,'status':'unsupported','stage':'module_runtime',
                'scope':'finite_external_strict_module_examples','reason':'Required module sandbox unavailable'}
    verify_bundle(bundle)
    if bundle['module_runtime'] != runtime_identity():
        _fail('version', 'The current module execution runtime differs from the artifact.')
    selected = [{'scope':'external','unit_id':None,'imports':[{'specifier':'./' + bundle['entry'],
                 'path':bundle['entry'],'names':bundle['exports']}],'call':call,'expected':expected}
                for call,expected in pairs]
    return _report(bundle,selected,_evaluate(bundle,selected,deadline=deadline,case_ms=case_ms),
                   scope='finite_external_strict_module_examples')
