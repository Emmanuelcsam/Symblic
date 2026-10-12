"""The runner inside a portable bundle: verify the bundle, then run its conformance corpus in a closed process.

What it is for
    symblic.portable.export copies this file into every bundle as portable_runner.py. export.verify() starts
    it in a fresh `python3 -I -S -B` child with an empty PATH:

        python3 -I -S -B portable_runner.py MANIFEST_SHA256 [verify|run]

    It refuses to run unless manifest.json hashes to MANIFEST_SHA256, every file matches its manifest entry,
    no extra file is present and the current runtime matches the manifest's runtime description. It then
    limits itself (MEMORY_BYTES address space, CPU_SECONDS of CPU, one CPU), installs an audit hook that refuses sockets,
    subprocesses, writes and reads outside the bundle and the standard library, imports the bundled kernel
    from src/, runs each corpus program with execution pins, the 'verified' profile, no model calls and no
    side effects, and compares the observable outputs with the expected ones. In 'run' mode it also runs one
    pure program read from standard input. It prints one JSON report.

    The same file also provides runtime(), validate_runtime() and runtime_matches(), which export.py uses to
    describe and check target runtimes.

Limits
    The audit hook is a guard against accidental reach-out by the pure kernel, not a security sandbox against
    hostile code (Python audit hooks can be bypassed by native code). /dev/urandom may be read, because
    CPython uses it for random execution IDs on builds without getrandom().

Depends on: the standard library at import; the bundled symblic.kernel modules when main() runs. Status:
tested through tests/portable.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import stat
import sys
import sysconfig
import unicodedata

PROFILE = 'verified-pure-no-provider-no-host-v2'
LEGACY_PROFILE = 'finite-corpus-no-node-no-provider-no-host-v1'
# Resource limits the runner sets on itself before it imports the bundled kernel. The whole corpus needed about
# 13 s of CPU on the development machine (most of it in the kernel's import-identity and pin checks); the limit
# leaves headroom for slower machines. symblic.portable.export.VERIFY_TIMEOUT_SECONDS bounds the wall time.
CPU_SECONDS = 60
MEMORY_BYTES = 512 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def runtime(profile=PROFILE):
    return {'implementation': sys.implementation.name, 'python': platform.python_version(),
            'unicode': unicodedata.unidata_version, 'system': platform.system(),
            'machine': platform.machine(), 'byteorder': sys.byteorder,
            'profile': profile}


def validate_runtime(value):
    """An explicit target description, never a claim of measured conformance."""
    if type(value) is not dict or set(value) != set(runtime()) or any(type(v) is not str for v in value.values()):
        raise ValueError('runtime_schema')
    import re
    if value['implementation'] != 'cpython' or value['system'] != 'Linux' or value['machine'] not in ('x86_64', 'aarch64') or value['byteorder'] != 'little':
        raise ValueError('unsupported_runtime_family')
    if not re.fullmatch(r'3\.(?:11|12|13)\.\d{1,3}', value['python']) or not re.fullmatch(r'\d{1,2}\.\d\.\d', value['unicode']):
        raise ValueError('unsupported_runtime_version')
    if value['profile'] not in (PROFILE, LEGACY_PROFILE):
        raise ValueError('unsupported_runtime_profile')
    return dict(value)


def runtime_matches(expected):
    return validate_runtime(expected) == runtime(expected['profile'])


def _pure_statements(statements):
    allowed = {'program', 'note', 'section', 'use', 'given', 'let', 'show', 'assert', 'expect',
               'fact', 'rule', 'import', 'if', 'for', 'function', 'define', 'term'}
    for statement in statements:
        if statement.k not in allowed:
            raise ValueError('unsupported_statement:' + statement.k)
        if statement.k == 'if':
            for _, body in statement.branches:
                _pure_statements(body)
            _pure_statements(statement.else_body or [])
        elif statement.k == 'for':
            _pure_statements(statement.body)


def _entropy_read(path, mode, flags):
    """CPython's /dev/urandom fallback supplies opaque execution IDs only.

    Permit the exact Linux entropy character device, never aliases, descriptors,
    ordinary host files or writes. Some standalone builds lack getrandom().
    """
    if type(path) not in (str, bytes) or os.fsdecode(path) != '/dev/urandom':
        return False
    if type(flags) is not int or flags & ~(os.O_CLOEXEC | os.O_NOFOLLOW):
        return False
    if mode is not None and (type(mode) is not str or mode not in ('r', 'rb')):
        return False
    try:
        device = os.stat('/dev/urandom', follow_symlinks=False)
        return stat.S_ISCHR(device.st_mode) and device.st_rdev == os.makedev(1, 9)
    except OSError:
        return False


def main():
    root = Path(__file__).resolve().parent
    expected = sys.argv[1] if len(sys.argv) in (2, 3) else ''
    mode = sys.argv[2] if len(sys.argv) == 3 else 'verify'
    if mode not in ('verify', 'run'):
        raise ValueError('unsupported_mode')
    request = None
    if mode == 'run':
        wire = sys.stdin.buffer.read(524289)
        if len(wire) > 524288:
            raise ValueError('request_size')
        request = json.loads(wire)
        if type(request) is not dict or set(request) != {'source', 'inputs'} or type(request['source']) is not str or type(request['inputs']) is not dict:
            raise ValueError('request_schema')
        if len(request['source'].encode()) > 262144:
            raise ValueError('source_size')
    raw = (root/'manifest.json').read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('manifest_mismatch')
    manifest = json.loads(raw)
    if manifest['format'] not in (1, 2) or not runtime_matches(manifest['runtime']):
        raise ValueError('unsupported_runtime')
    if mode == 'run' and manifest['format'] != 2:
        raise ValueError('legacy_bundle_corpus_only')
    names = set(manifest['files'])
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != names | {'manifest.json'}:
        raise ValueError('unexpected_file')
    for name, item in manifest['files'].items():
        path = root/name
        if path.is_symlink() or not path.is_relative_to(root):
            raise ValueError('source_path')
        source = path.read_bytes()
        if len(source) != item['bytes'] or hashlib.sha256(source).hexdigest() != item['sha256']:
            raise ValueError('source_mismatch')
    corpus = json.loads((root/'corpus.json').read_text())
    # No environment-selected or external optional backend can be discovered.
    os.environ.pop('SYMBLIC_NODE', None)
    os.environ['PATH'] = ''
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root/'src'))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    stdlib = Path(sysconfig.get_path('stdlib')).resolve()
    allowed = (root, stdlib)
    denials = []

    def path_allowed(path):
        if isinstance(path, int):
            return False
        try:
            resolved = Path(os.fsdecode(path)).resolve()
            return any(resolved == base or resolved.is_relative_to(base) for base in allowed)
        except (TypeError, ValueError, OSError):
            return False

    def audit(event, args):
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.exec', 'os.fork', 'os.forkpty'):
            denials.append(event)
            raise PermissionError('external_operation_refused')
        if event == 'open':
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
            if writing or not (path_allowed(path) or _entropy_read(path, mode, flags)):
                denials.append('open')
                raise PermissionError('file_access_refused')
        if event in ('os.listdir', 'os.scandir') and not path_allowed(args[0]):
            # Optional backend home-directory discovery is deliberately unavailable.
            raise PermissionError('discovery_refused')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.truncate'):
            denials.append(event)
            raise PermissionError('mutation_refused')

    sys.addaudithook(audit)
    from symblic.kernel import language as S
    from symblic.kernel import execution_pins as X
    from symblic.kernel.run import Run
    if sorted(X.REQUIRED_FILES) != manifest['registry']['required_python'] or sorted(X.ASSET_FILES) != manifest['registry']['assets'] or sorted(X.LIBRARY_FILES) != manifest['registry']['libraries']:
        raise ValueError('registry_mismatch')
    required = {name: manifest['files']['src/'+name]['sha256'] for name in X.REQUIRED_FILES}
    library_paths = {module: path for path, module in X.LIBRARY_FILES.items()}

    def hashes(program):
        """Pin the required kernel files plus only the library modules the program imports (transitively).

        Capturing every library module for every program made each pin build parse all of them again.
        """
        needed, pending = set(), [program]
        while pending:
            for node in S.walk(S.parse(pending.pop())['statements']):
                if node.k == 'import' and not node.saved and node.module in library_paths and node.module not in needed:
                    needed.add(node.module)
                    pending.append((root/'src'/library_paths[node.module]).read_text(encoding='utf-8'))
        return {**required, **{library_paths[module]: manifest['files']['src/'+library_paths[module]]['sha256']
                               for module in needed}}

    kernel = S.kernel_id()
    if '+node-none+' not in kernel['js'] or '+node-none+' not in kernel['js_declarations']:
        raise ValueError('unexpected_backend')

    class NoProviders:
        def call(self, request):
            raise AssertionError('provider_refused')

    class BoundedRun(Run):
        """Host output bounds in addition to the native kernel/OS work bounds."""
        def _output(self, statement, env):
            if len(self.outputs) >= 128:
                raise S.SymblicError('portable output count limit', statement.line, statement.col, 'budget')
            super()._output(statement, env)
            used = getattr(self, '_portable_output_bytes', 0)
            for part in json.JSONEncoder(ensure_ascii=False).iterencode(self.outputs[-1]):
                used += len(part.encode('utf-8'))
                if used > 1048576:
                    self.outputs.pop()
                    raise S.SymblicError('portable output byte limit', statement.line, statement.col, 'budget')
            self._portable_output_bytes = used

    outcomes = []
    for case in corpus:
        source = case['source']
        parsed = S.parse(source)
        _pure_statements(parsed['statements'])
        pins = X.build(source, {}, hashes(source))
        report = Run(source, {}, NoProviders(), {'execution_pins':pins, 'profile':'verified',
            'max_calls':0, 'max_asks':0, 'side_effects':False, 'constructor':'off', 'max_steps':12000}).execute()
        observed = {'status':report['status'], 'calls':report['calls'],
                    'outputs':[row['text'] for row in report['outputs']],
                    'error_code':(report.get('error') or {}).get('code')}
        if observed != case['expected']:
            raise ValueError('conformance_mismatch:'+case['id']+':'+json.dumps(observed))
        outcomes.append({'id':case['id'], 'ok':True, 'observable_sha256':hashlib.sha256(canonical(observed)).hexdigest()})
    user_result = None
    if request is not None:
        source, inputs = request['source'], request['inputs']
        parsed = S.parse(source, execution_profile='verified')
        _pure_statements(parsed['statements'])
        pins = X.build(source, inputs, hashes(source))
        report = BoundedRun(source, inputs, NoProviders(), {'execution_pins': pins, 'profile': 'verified',
            'max_calls': 0, 'max_asks': 0, 'side_effects': False, 'constructor': 'off',
            'max_steps': 200000}).execute()
        user_result = {key: report.get(key) for key in ('status', 'error', 'fingerprint', 'calls', 'outputs', 'warnings')}
        user_result['source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        user_result['inputs_sha256'] = hashlib.sha256(canonical(inputs)).hexdigest()
    imported = []
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if not filename or filename.startswith('<'):
            continue
        path = Path(filename).resolve()
        if path == Path(__file__).resolve():
            continue
        if path.is_relative_to(root/'src'):
            imported.append(path.relative_to(root/'src').as_posix())
        elif not path.is_relative_to(stdlib):
            raise ValueError('external_import:'+name)
    if denials:
        raise ValueError('unexpected_operation_attempt')
    print(json.dumps({'ok':True,'runtime':runtime(manifest['runtime']['profile']),'kernel':kernel,'cases':outcomes,
                      'model_calls':0,'stores':0,'network_calls':0,'subprocess_calls':0,
                      'source_imports':sorted(set(imported)), 'external_source_imports':[],
                      'manifest_sha256':expected, 'source_suite_sha256': hashlib.sha256(canonical({
                          name: row['sha256'] for name, row in manifest['files'].items() if name.startswith('src/')})).hexdigest(),
                      'corpus_sha256': manifest['files']['corpus.json']['sha256'],
                      'observable_suite_sha256': hashlib.sha256(canonical(outcomes)).hexdigest(),
                      'program': user_result},sort_keys=True))


if __name__ == '__main__':
    main()
