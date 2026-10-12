"""Portable bundles: export the pure Symblic kernel as one reproducible zip and check it on another machine.

What it is for
    A Symblic result is only comparable across machines if the same kernel source gives the same observable
    behaviour there. This module packs exactly the source files named by the execution-pins registry
    (symblic/kernel/execution_pins.py: REQUIRED_FILES, ASSET_FILES and the standard-library modules in
    symblic/lang/library/), plus the package markers they need, a fixed conformance corpus of 16 pure
    programs and the runner (runner.py), into a byte-for-byte reproducible zip with a manifest of SHA-256
    hashes. On the target machine, verify() unpacks the zip, re-checks every hash against the manifest digest
    you pass in, and runs the corpus (and optionally one of your own pure programs) in a child Python process
    with no network, no subprocesses, no file writes and no model provider (see runner.py). compare() checks
    that two or more verification reports observed the same sources and the same corpus outputs.

    python3 -m symblic.portable.export build --source-root . --output kernel.zip
    python3 -m symblic.portable.export verify kernel.zip --manifest-sha256 HASH
    python3 -m symblic.portable.export run kernel.zip program.sym --manifest-sha256 HASH [--inputs-json FILE]
    python3 -m symblic.portable.export compare report-a.json report-b.json
    python3 -m symblic.portable.export runtime

What it does not claim
    The manifest digest is integrity, not a signature: get it to the target machine over a channel you
    trust. A matching corpus is evidence about 16 programs on the observed runtimes, not equivalence for every
    program. Bundles target CPython 3.11-3.13 on little-endian Linux (x86_64 or aarch64); a bundle built for
    another runtime is labelled 'unmeasured' until it is verified there. Programs that ask models, use effects,
    run JavaScript or the linear solver are refused inside the bundle.

Depends on: the Python standard library and symblic.portable.runner; it reads (never imports or executes)
the registry declarations in symblic/kernel/execution_pins.py. Status: tested (tests/portable builds, unpacks
and runs real bundles in temporary folders); cross-machine comparison has only been run on the machines the
authors had.
"""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile

from symblic.portable.runner import PROFILE, runtime, runtime_matches, validate_runtime

VERSION = 2
VERIFY_TIMEOUT_SECONDS = 180   # wall-time bound for one verification child (its CPU bound is runner.CPU_SECONDS)
MAX_FILE = 8_000_000
MAX_TOTAL = 16_000_000
MAX_FILES = 100
# Names of the registry declarations read from PINS_MODULE (as data, never executed). Paths in the registry and
# in the bundle are POSIX paths relative to the folder that holds the symblic package.
REGISTRY = {'PYTHON_FILES', 'REQUIRED_FILES', 'ASSET_FILES', 'LIBRARIES'}
PINS_MODULE = 'symblic/kernel/execution_pins.py'
LIBRARY_DIR = 'symblic/lang/library/'
CORPUS = [
 {'id':'rational','source':'let x = 1/10 + 2/10.\nassert x = 3/10.\nshow x.\n','expected':{'status':'done','calls':0,'outputs':['0.3'],'error_code':None}},
 {'id':'typed-set','source':'show len({true,1,false,0}).\n','expected':{'status':'done','calls':0,'outputs':['4'],'error_code':None}},
 {'id':'unicode','source':'show "é" = "é".\nshow "αβ".\n','expected':{'status':'done','calls':0,'outputs':['false','αβ'],'error_code':None}},
 {'id':'datalog','source':'fact edge(a,b), edge(b,c).\nrule reach(X,Y) if edge(X,Y).\nrule reach(X,Z) if edge(X,Y) and reach(Y,Z).\nshow holds reach(a,c).\n','expected':{'status':'done','calls':0,'outputs':['true'],'error_code':None}},
 {'id':'library','source':'import records as records.\nshow records.conflicts({a:1,b:2}, {a:1,b:3}).\n','expected':{'status':'done','calls':0,'outputs':['["b"]'],'error_code':None}},
 {'id':'negative-check','source':'assert 2 + 2 = 5.\nshow 9.\n','expected':{'status':'failed','calls':0,'outputs':[],'error_code':'SYM_CHECK'}},
]
for _id, _source, _outputs in [
    ('branches', 'if false then\n show "bad".\nelif 2 < 3 then\n show "chosen".\nelse\n show "bad".\nend.\n', ['chosen']),
    ('loop-lift', 'for n in 1..4 do\n let square = n*n.\nend.\nshow square.\n', ['[1, 4, 9, 16]']),
    ('boolean', 'show [false implies false, false implies true, true implies false, true implies true].\nshow [false iff false, false iff true, true iff false, true iff true].\n', ['[true, true, false, true]', '[true, false, false, true]']),
    ('quantifiers', 'show all n in 1..4: n > 0.\nshow any n in 1..4: n = 3.\nshow none n in 1..4: n < 0.\n', ['true', 'true', 'true']),
    ('recursive-function', 'function product_to(n: Int) -> Int = if n = 0 then 1 else n * product_to(n - 1).\nshow product_to(6).\n', ['720']),
    ('empty-record', 'show {:}.\nshow {:} = {}.\n', ['{:}', 'false']),
    ('negative-division', 'show [-3 // 2, -3 mod 2].\n', ['[-2, 1]']),
    ('comprehension', 'show [n*n for n in 1..5 if n mod 2 = 1].\n', ['[1, 9, 25]']),
    ('proof-identity', 'let goal = proof_parse(\'"P" implies "P"\').\nlet certificate = {version: 1, proof: ["implies_intro", "h", ["atom", "P"], ["hypothesis", "h"]]}.\nshow proof_valid({:}, goal, certificate).\n', ['true']),
    ('measurement-units', 'let q = quantity_convert(quantity_measure(1.2, 0.05, "m"), "cm").\nshow [q.lower, q.upper].\n', ['[115, 125]']),
]:
    CORPUS.append({'id': _id, 'source': _source,
                   'expected': {'status': 'done', 'calls': 0, 'outputs': _outputs, 'error_code': None}})


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def declared_registry(root):
    """Evaluate only the registry's finite set-literal/union declarations, never source code."""
    values = {}
    def read(node):
        if isinstance(node,ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node,ast.Set) and all(isinstance(item, ast.Constant) and type(item.value) is str
                                            for item in node.elts):
            return frozenset(item.value for item in node.elts)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='frozenset' and len(node.args)==1 and not node.keywords:
            return read(node.args[0])
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.BitOr): return read(node.left)|read(node.right)
        raise ValueError('unsupported_registry_declaration')
    for node in ast.parse((root/PINS_MODULE).read_text()).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in REGISTRY:
            values[node.targets[0].id]=read(node.value)
    if not REGISTRY <= values.keys(): raise ValueError('missing_registry')
    python = sorted(name for name in values['REQUIRED_FILES'] | values['ASSET_FILES'] if name.endswith('.py'))
    # Package markers (__init__.py) of every folder that holds a bundled Python module, so that
    # `import symblic.kernel.language` works inside the unpacked bundle.
    packages = sorted({'/'.join(parts[:depth]) + '/__init__.py' for parts in (name.split('/') for name in python)
                       for depth in range(1, len(parts))})
    return {'required_python':sorted(values['REQUIRED_FILES']), 'assets':sorted(values['ASSET_FILES']),
            'libraries':sorted(LIBRARY_DIR+name+'.sym' for name in values['LIBRARIES']),
            'packages':packages}


def safe_name(name):
    path=PurePosixPath(name)
    if not name or '\\' in name or path.is_absolute() or any(p in ('..','.') for p in path.parts) or path.as_posix()!=name:
        raise ValueError('unsafe_member')


def build(source_root, output, target_runtime=None):
    root=Path(source_root).resolve(); registry=declared_registry(root)
    target = validate_runtime(runtime() if target_runtime is None else target_runtime)
    if target['profile'] != PROFILE:raise ValueError('build_runtime_profile')
    names=sorted(set(sum(registry.values(), [])))
    payload={}
    for name in names:
        safe_name(name);path=root/name
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():raise ValueError('source_not_regular')
        raw=path.read_bytes()
        if len(raw)>MAX_FILE:raise ValueError('source_size')
        payload['src/'+name]=raw
    # Snapshot coherence: refuse a concurrent source change before committing bytes.
    if any((root/name).read_bytes()!=payload['src/'+name] for name in names):raise ValueError('source_changed')
    payload['portable_runner.py']=Path(__file__).with_name('runner.py').read_bytes()
    payload['corpus.json']=canonical(CORPUS)
    manifest={'format':2,'runtime':target,'registry':registry,
              'subset':f'verified bounded pure native programs; {len(CORPUS)}-case conformance corpus',
              'unsupported':['providers','effects','JavaScript execution','linear solver backend','WASM','unmeasured conformance'],
              'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in sorted(payload.items())}}
    manifest_raw=canonical(manifest);payload['manifest.json']=manifest_raw
    if len(payload)>MAX_FILES or sum(map(len,payload.values()))>MAX_TOTAL:raise ValueError('bundle_size')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_STORED) as bundle:
        for name,raw in sorted(payload.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3
            info.external_attr=(stat.S_IFREG|0o444)<<16
            bundle.writestr(info,raw)
    archive=buffer.getvalue()
    with Path(output).open('xb') as stream:stream.write(archive)
    return {'archive_sha256':hashlib.sha256(archive).hexdigest(),'manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),
            'bytes':len(archive),'files':len(payload),'runtime':target,
            'conformance':'unmeasured until verified on the exact target runtime'}


def verify(archive, expected, *, source=None, inputs=None):
    request = None
    if source is not None:
        if type(source) is not str or len(source.encode()) > 262144 or type(inputs if inputs is not None else {}) is not dict:
            raise ValueError('request_schema')
        request = canonical({'source': source, 'inputs': inputs if inputs is not None else {}})
        if len(request) > 524288:
            raise ValueError('request_size')
    if type(expected) is not str or len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected):raise ValueError('manifest_digest')
    if Path(archive).stat().st_size>MAX_TOTAL+100_000:raise ValueError('bundle_size')
    with zipfile.ZipFile(archive) as bundle:
        infos=bundle.infolist()
        if len(infos)>MAX_FILES or len({i.filename for i in infos})!=len(infos) or sum(i.file_size for i in infos)>MAX_TOTAL:raise ValueError('bundle_size')
        for item in infos:
            safe_name(item.filename)
            if item.file_size>MAX_FILE or item.compress_type!=zipfile.ZIP_STORED or stat.S_IFMT(item.external_attr>>16)!=stat.S_IFREG:raise ValueError('member_type')
        contents={item.filename:bundle.read(item) for item in infos}
    raw=contents.get('manifest.json',b'')
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('manifest_mismatch')
    manifest=json.loads(raw)
    if manifest['format'] not in (1, 2) or not runtime_matches(manifest['runtime']):raise ValueError('unsupported_runtime')
    if request is not None and manifest['format'] != 2:raise ValueError('legacy_bundle_corpus_only')
    if set(contents)!=set(manifest['files'])|{'manifest.json'}:raise ValueError('unexpected_file')
    for name,row in manifest['files'].items():
        data=contents[name]
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('source_mismatch')
    with tempfile.TemporaryDirectory(prefix='symblic-portable-') as temporary:
        root=Path(temporary)
        for name,raw in contents.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        env={'PATH':'','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
        argv=[sys.executable,'-I','-S','-B',str(root/'portable_runner.py'),expected]
        if request is not None:argv.append('run')
        proc=subprocess.run(argv,cwd=root,env=env,input=request.decode() if request is not None else None,
                            text=True,capture_output=True,timeout=VERIFY_TIMEOUT_SECONDS)
        if proc.returncode:raise ValueError('conformance_failed:'+proc.stderr[-2000:])
        result=json.loads(proc.stdout)
    return result


def compare(reports):
    """Compare supplied observations; transport/authenticity remains the caller's responsibility."""
    if type(reports) is not list or not 2 <= len(reports) <= 16:
        raise ValueError('report_count')
    keys = ('source_suite_sha256', 'corpus_sha256', 'observable_suite_sha256')
    for report in reports:
        if type(report) is not dict or report.get('ok') is not True or any(type(report.get(k)) is not str or len(report[k]) != 64 for k in keys):
            raise ValueError('report_schema')
        validate_runtime(report['runtime'])
        if any(report.get(k) != 0 for k in ('model_calls', 'stores', 'network_calls', 'subprocess_calls')):
            raise ValueError('report_external_activity')
        if hashlib.sha256(canonical(report['cases'])).hexdigest() != report['observable_suite_sha256']:
            raise ValueError('report_cases_mismatch')
    if any(any(report[k] != reports[0][k] for k in keys) for report in reports[1:]):
        raise ValueError('conformance_mismatch')
    return {'ok': True, 'scope': 'same pinned source and finite corpus observations; no arbitrary-program equivalence',
            'runtimes': [r['runtime'] for r in reports], 'cases': len(reports[0]['cases']),
            **{k: reports[0][k] for k in keys}}


def read_bounded(path, limit):
    with Path(path).open('rb') as stream:
        raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('input_file_size')
    return raw.decode('utf-8')


def main():
    parser=argparse.ArgumentParser(prog='python3 -m symblic.portable.export',
        description='Build, verify, run and compare portable Symblic kernel bundles.')
    sub=parser.add_subparsers(dest='command',required=True)
    build_parser=sub.add_parser('build');build_parser.add_argument('--source-root',required=True);build_parser.add_argument('--output',required=True)
    build_parser.add_argument('--target-runtime',help='JSON runtime description; requires actual target verification')
    check_parser=sub.add_parser('verify');check_parser.add_argument('archive');check_parser.add_argument('--manifest-sha256',required=True)
    run_parser=sub.add_parser('run');run_parser.add_argument('archive');run_parser.add_argument('program');run_parser.add_argument('--manifest-sha256',required=True);run_parser.add_argument('--inputs-json')
    compare_parser=sub.add_parser('compare');compare_parser.add_argument('reports',nargs='+')
    sub.add_parser('runtime')
    args=parser.parse_args()
    if args.command=='build':result=build(args.source_root,args.output,json.loads(read_bounded(args.target_runtime,4096)) if args.target_runtime else None)
    elif args.command=='runtime':result=runtime()
    elif args.command=='compare':result=compare([json.loads(read_bounded(p,1048576)) for p in args.reports])
    elif args.command=='run':result=verify(args.archive,args.manifest_sha256,source=read_bounded(args.program,262144),inputs=json.loads(read_bounded(args.inputs_json,262144)) if args.inputs_json else {})
    else:result=verify(args.archive,args.manifest_sha256)
    print(json.dumps(result,sort_keys=True))
    if args.command=='run' and result['program']['status']!='done':sys.exit(1)


if __name__=='__main__':main()
