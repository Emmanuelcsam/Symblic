"""Snapshot and check a finite Symblic corpus without models or network calls.

    python3 tools/scripts/symblic_conformance.py --output /tmp/symblic-conformance.json

Copies a whitelist of source files into an isolated temporary directory, verifies
hashes, and checks three hash seeds across three ambient Decimal contexts. Each
worker has one-CPU affinity, a 768 MiB address-space cap, and a 90-second CPU cap.
A passing result proves only equality of this fixed corpus's observable bytes;
Unicode kernel identities and Python versions remain explicit in every receipt.
"""
import argparse
import ast
import decimal
import hashlib
import json
import os
import platform
import resource
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Reviewed public source closure, not a recursive filesystem scan or permission
# to import the live checkout. A new required runtime file must be reviewed here.
PUBLIC_RUNTIME_FILES = frozenset({
    'symblic/kernel/language.py', 'symblic/kernel/run.py', 'symblic/kernel/evidence.py', 'symblic/lang/abstraction.py',
    'symblic/adapters/geometry.py', 'symblic/adapters/render.py', 'symblic/kernel/effects.py',
    'symblic/kernel/embed.py', 'symblic/kernel/execution_pins.py', 'symblic/kernel/diagnose.py',
    'symblic/kernel/certificates.py', 'symblic/js/check.py', 'symblic/adapters/variational.py',
    'symblic/adapters/transport.py', 'symblic/adapters/discrete.py', 'symblic/adapters/knowledge.py',
    'symblic/adapters/projection.py', 'symblic/adapters/operators.py', 'symblic/kernel/epistemic.py',
    'symblic/kernel/grounding.py', 'symblic/adapters/quantities.py', 'symblic/kernel/profiles.py',
    'symblic/adapters/proof.py', 'symblic/adapters/proof_steps.py', 'symblic/adapters/finite_logic.py',
    'symblic/adapters/proof_adapter.py', 'symblic/adapters/logic.py', 'symblic/kernel/identity.py',
    'symblic/adapters/proof_session.py', 'symblic/adapters/proof_command.py', 'symblic/delegate/contracts.py',
    'symblic/delegate/run.py', 'symblic/spec/sheets.py', 'symblic/spec/build.py',
    'symblic/spec/contracts.py', 'symblic/js/contract.py', 'symblic/authoring/helpers.py',
    'symblic/constructor/core.py', 'symblic/constructor/journal.py',
    'symblic/constructor/records.py', 'symblic/linear/constructor.py',
    'symblic/linear/resources.py', 'symblic/providers/agent_teams.py',
    'symblic/kernel/process_limits.py', 'symblic/linear/worker.py', 'symblic/js/runner.js',
    'symblic/sandbox/landlock.py', 'symblic/js/contract_runner.js',
    'symblic/js/acorn.js', 'symblic/js/acorn-LICENSE.txt',
    'symblic/js/normalize.py', 'symblic/js/normalize.js',
    # Reviewed inert dependency of the pending typed-JSON parser. Do not copy
    # or claim it is installed unless execution_pins.REQUIRED_FILES declares it.
    'symblic/kernel/json_schema.py',
})
EXTRA_RUNTIME_FILES = frozenset({'symblic/kernel/embed.py', 'symblic/spec/sheets.py',
                               'symblic/js/normalize.py', 'symblic/js/normalize.js'})
PUBLIC_LIBRARIES = frozenset({'constants', 'dates', 'graphs', 'kinship', 'lab',
                              'stats', 'text', 'units', 'records', 'order'})
REGISTRY_SOURCE = 'symblic/kernel/execution_pins.py'       # the execution-pins registry, read as literals only
LIBRARY_PATH = 'symblic/lang/library/{}.sym'
IDENTITY_SOURCE = 'examples/10-kernel-identity.sym'
SOUNDNESS_SOURCE = 'tests/kernel/test_symblic_soundness.py'
REGISTRY_NAMES = frozenset({'REQUIRED_FILES', 'ASSET_FILES', 'LIBRARIES',
                            '_REFORM_FILES', '_CONSTRUCTOR_FILES'})
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_BYTES = 16 * 1024 * 1024


def read_public_file(repo, name, *, remaining=None):
    """Bounded regular-file read; neither source nor directory symlinks grant authority."""
    path = Path(repo)
    parts = Path(name).parts
    if not parts or Path(name).is_absolute() or any(p in ('.', '..') for p in parts) or '\\' in name:
        raise RuntimeError('invalid public source path: ' + name)
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise RuntimeError('public source symlink refused: ' + name)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise RuntimeError('required public source unavailable: ' + name) from error
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise RuntimeError('public source is not a bounded regular file: ' + name)
        if remaining is not None and before.st_size > remaining:
            raise RuntimeError('public snapshot exceeds bundle byte limit')
        limit = MAX_FILE_BYTES if remaining is None else min(MAX_FILE_BYTES, remaining)
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(raw) > limit or (before.st_size, before.st_mtime_ns, before.st_ino) != (
                after.st_size, after.st_mtime_ns, after.st_ino):
            raise RuntimeError('public source changed or exceeds limit: ' + name)
    return raw


def execution_registry(raw):
    """Read only literal set declarations/unions, never execute or import source."""
    values = {}

    def literal(node):
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
            if any(not isinstance(n, ast.Constant) or type(n.value) is not str for n in node.elts):
                raise RuntimeError('execution registry must contain literal strings')
            return frozenset(n.value for n in node.elts)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'frozenset' and len(node.args) == 1 and not node.keywords):
            return literal(node.args[0])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return literal(node.left) | literal(node.right)
        raise RuntimeError('unsupported execution registry expression; review the source closure')

    for statement in ast.parse(raw, filename=REGISTRY_SOURCE).body:
        stored = {n.id for n in ast.walk(statement)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)} & REGISTRY_NAMES
        if isinstance(statement, ast.Assign):
            targets = [n.id for n in statement.targets if isinstance(n, ast.Name)]
            relevant = set(targets) & REGISTRY_NAMES
            if relevant:
                if len(targets) != 1 or len(statement.targets) != 1:
                    raise RuntimeError('unsupported execution registry assignment')
                values[targets[0]] = literal(statement.value)
                continue
        if stored:
            raise RuntimeError('unsupported execution registry assignment; review the source closure')
    if not {'REQUIRED_FILES', 'ASSET_FILES', 'LIBRARIES'} <= set(values):
        raise RuntimeError('execution registry is incomplete')
    return {key: sorted(values[key]) for key in ('REQUIRED_FILES', 'ASSET_FILES', 'LIBRARIES')}


def snapshot_content(repo, driver=None):
    """Fail before launching a worker if the reviewed runtime closure is incomplete."""
    registry_raw = read_public_file(repo, REGISTRY_SOURCE)
    registry = execution_registry(registry_raw)
    required = set(registry['REQUIRED_FILES']) | set(registry['ASSET_FILES']) | EXTRA_RUNTIME_FILES
    unknown = required - PUBLIC_RUNTIME_FILES
    if unknown or set(registry['LIBRARIES']) - PUBLIC_LIBRARIES:
        raise RuntimeError('unreviewed execution closure: ' + ', '.join(sorted(
            unknown | (set(registry['LIBRARIES']) - PUBLIC_LIBRARIES))))
    names = required | {LIBRARY_PATH.format(name) for name in registry['LIBRARIES']}
    names |= {SOUNDNESS_SOURCE, IDENTITY_SOURCE}
    # The package markers the copied modules need to import as packages (they hold only docstrings).
    names |= {str(Path(*Path(name).parts[:depth]) / '__init__.py') for name in names
              if name.endswith('.py') and Path(name).parts[0] in ('symblic', 'tests')
              for depth in range(1, len(Path(name).parts))}
    driver = Path(driver or __file__)
    driver_raw = read_public_file(driver.parent, driver.name, remaining=MAX_BUNDLE_BYTES)
    content, size = {}, len(driver_raw)
    for name in sorted(names):
        raw = read_public_file(repo, name, remaining=MAX_BUNDLE_BYTES - size)
        content[name] = raw
        size += len(raw)
    if content.get(REGISTRY_SOURCE) != registry_raw or any(
            read_public_file(repo, name) != value for name, value in content.items()):
        raise RuntimeError('source changed while copying; retry after edits settle')
    content['identity.sym'] = content.pop(IDENTITY_SOURCE)
    if read_public_file(driver.parent, driver.name) != driver_raw:
        raise RuntimeError('driver changed while copying; retry after edits settle')
    content['conformance_driver.py'] = driver_raw
    return content, registry


def isolated_env(folder, seed=None):
    """No inherited credentials, provider endpoints, private HOME or Python path."""
    folder = Path(folder)
    for name in ('home', 'config', 'data', 'cache', 'tmp'):
        (folder / '_isolated' / name).mkdir(parents=True, exist_ok=True)
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
           'HOME': str(folder / '_isolated/home'), 'TMPDIR': str(folder / '_isolated/tmp'),
           'XDG_CONFIG_HOME': str(folder / '_isolated/config'),
           'XDG_DATA_HOME': str(folder / '_isolated/data'),
           'XDG_CACHE_HOME': str(folder / '_isolated/cache'),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    if seed is not None:
        env['PYTHONHASHSEED'] = str(seed)
    return env


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def child(profile):
    if profile != 'default':
        ctx = decimal.getcontext()
        ctx.prec = 8 if profile == 'narrow' else 60
        ctx.rounding = decimal.ROUND_DOWN if profile == 'narrow' else decimal.ROUND_UP
        ctx.traps[decimal.Inexact] = True
        ctx.Emax, ctx.Emin = (20, -20) if profile == 'narrow' else (999, -999)
    from symblic.kernel import language as S
    from symblic.kernel import run as SR
    from symblic.adapters import finite_logic as FL
    from symblic.adapters import logic as Logic
    from symblic.adapters import proof as P
    from symblic.adapters import proof_steps as W
    def evaluate(expression):
        parser = S.Parser(S.tokenize(expression), 1)
        node = parser.expr()
        parser.finish()
        return S.Kernel().eval(node)
    expressions = [
        '1/10 + 2/10', '2^521-1', 'round(1.005,2)', 'round(-1.005,2)',
        'len({true,1,false,0})', '{true,1,"x","y",{a:1},[true]}',
        'radians(1)', '2 ^ 0.3', 'sin(1)', 'sqrt(2)', 'text(1/7)',
        '"a" = "a "', '"é" = "é"',
        'flower(petals=3,size=120)', 'polygon(sides=11,color="teal")',
    ]
    values = {expr: S.canon_json(evaluate(expr)) for expr in expressions}
    source = (ROOT / 'identity.sym').read_text()
    report = SR.Run(source, options={'by': 'kernel', 'side_effects': False, 'max_calls': 0}).execute()
    assert report['status'] == 'done', report.get('error')
    typed_source = 'fact p(true),p(1),p("[1,2]"),p(null).\nrule q(X) if p(X).\nshow query q(X).\n'
    typed = SR.Run(typed_source, options={'by': 'kernel', 'max_calls': 0}).execute()
    assert typed['status'] == 'done', typed.get('error')
    atom = ['atom', 'A']
    nested = P.verify({'a': atom}, atom, {'version': 1, 'proof': ['premise', 'a']})
    flat = W.verify({'a': atom}, atom, {
        'version': 1,
        'steps': [{'id': 'p', 'rule': 'premise', 'args': ['a'], 'formula': None}],
        'result': 'p',
    })
    assert nested['ok'] and flat['ok']
    domain = {'People': ['Ada']}
    finite_formula = FL.parse_formula('Kind(People["Ada"])')
    finite = FL.verify(domain, {'kind': finite_formula}, finite_formula,
                       {'version': 1, 'proof': ['premise', 'kind']})
    assert finite['ok'], finite
    compiled = Logic.compile_task({
        'premises': 'p: "A"', 'goal': '"A"', 'certificate_format': 'steps', 'calls': 1,
    })
    assert compiled['formalization']['certificate_format'] == 'steps'
    # Output bytes only: do not compare mixed runtime kernel fingerprints as one identity claim.
    outputs = [{k: row[k] for k in ('kind', 'label', 'value', 'text', 'svg') if k in row}
               for row in report['outputs']]
    payload = {'values': values, 'identity_outputs': outputs,
               'typed_outputs': [{k: row[k] for k in ('kind', 'value', 'text') if k in row}
                                 for row in typed['outputs']],
               'nested_proof': nested, 'flat_proof': flat, 'finite_proof': finite,
               'logic_compile': compiled['formalization']}
    return {'profile': profile, 'hash_seed': os.environ.get('PYTHONHASHSEED'),
            'python': platform.python_version(), 'machine': platform.machine(), 'kernel': S.kernel_id(),
            'observable_sha256': sha(canonical(payload)),
            'expression_sha256': {expr: sha(value) for expr, value in values.items()},
            'svg_sha256': [sha(row['svg']) for row in outputs if 'svg' in row],
            'run_fingerprint': report['fingerprint'], 'calls': report['calls']}



def snapshot_and_run(output=None, *, repo=None):
    repo = Path(repo) if repo is not None else Path(__file__).resolve().parents[2]   # this file is tools/scripts/...
    content, registry = snapshot_content(repo)
    manifest = {'format': 1, 'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'files': {name: hashlib.sha256(value).hexdigest() for name, value in content.items()},
                'execution_registry': registry}
    with tempfile.TemporaryDirectory(prefix='symblic-conformance-') as directory:
        folder = Path(directory)
        for name, value in content.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        (folder / 'input_manifest.json').write_text(json.dumps(manifest, sort_keys=True))
        env = isolated_env(folder)
        proc = subprocess.run([sys.executable, '-S', str(folder / 'conformance_driver.py'), '--bundle'],
                              cwd=folder, env=env, capture_output=True, text=True, timeout=300, check=False)
        if not (folder / 'receipt.json').exists():
            raise RuntimeError('conformance worker failed before receipt: ' + proc.stderr[-3000:])
        receipt = json.loads((folder / 'receipt.json').read_text())
    receipt['manifest'] = manifest
    receipt['snapshot'] = 'immutable whitelisted temporary copy; no installed/live modules reloaded'
    if output:
        destination = Path(output).expanduser()
        with destination.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
        print(canonical({'output': str(destination), 'matrix_same_observables': receipt['matrix_same_observables'],
                         'soundness_returncode': receipt['tests']['returncode'],
                         'input_manifest_sha256': receipt['input_manifest_sha256']}))
    else:
        print(canonical(receipt))
    return proc.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=('default', 'narrow', 'wide'), help=argparse.SUPPRESS)
    parser.add_argument('--bundle', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--soundness', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--output', help='write a new JSON receipt; existing files are never overwritten')
    args = parser.parse_args()
    if not args.case and not args.bundle and not args.soundness:
        sys.exit(snapshot_and_run(args.output))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    if args.soundness:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_symblic_soundness.py',
                                                    top_level_dir=str(ROOT))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    if args.case:
        print(canonical(child(args.case)))
        return
    manifest = json.loads((ROOT / 'input_manifest.json').read_text())
    files = {name: hashlib.sha256(read_public_file(ROOT, name)).hexdigest() for name in manifest['files']}
    assert files == manifest['files'], 'bundle file hash mismatch'
    registry = execution_registry(read_public_file(ROOT, REGISTRY_SOURCE))
    assert registry == manifest['execution_registry'], 'bundle execution registry mismatch'
    assert set(registry['REQUIRED_FILES']) | set(registry['ASSET_FILES']) <= set(files), 'incomplete bundle closure'
    rows = []
    for seed in ('0', '1', '7'):
        for profile in ('default', 'narrow', 'wide'):
            env = isolated_env(ROOT, seed)
            proc = subprocess.run([sys.executable, '-S', str(Path(__file__)), '--case', profile],
                                  cwd=ROOT, env=env, capture_output=True, text=True, timeout=90, check=False)
            if proc.returncode:
                rows.append({'hash_seed': seed, 'profile': profile, 'error': proc.stderr[-4000:],
                             'returncode': proc.returncode})
            else:
                rows.append(json.loads(proc.stdout))
    tests = subprocess.run([sys.executable, '-S', str(Path(__file__)), '--soundness'], cwd=ROOT,
                           capture_output=True, text=True, timeout=90, check=False,
                           env=isolated_env(ROOT))
    result = {'format': 1, 'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'node': platform.node(), 'python': platform.python_version(), 'machine': platform.machine(),
              'files': files, 'input_manifest_sha256': sha(canonical(manifest)), 'matrix': rows,
              'tests': {'returncode': tests.returncode, 'stdout': tests.stdout, 'stderr': tests.stderr},
              'matrix_same_observables': len({r.get('observable_sha256') for r in rows}) == 1
                  and all(r.get('observable_sha256') for r in rows),
              'limits': 'Fixed corpus only. Compare runtime fingerprints only under identical kernel IDs; Unicode may differ.'}
    (ROOT / 'receipt.json').write_text(json.dumps(result, sort_keys=True, indent=2))
    print(canonical(result))
    if not result['matrix_same_observables'] or tests.returncode:
        sys.exit(1)


if __name__ == '__main__':
    main()
