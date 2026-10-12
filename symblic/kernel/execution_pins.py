"""Execution pins: a receipt that binds a reviewed program to the exact source files that will run it.

    pins = build(source, inputs, module_hashes)   # module_hashes: {registry path: sha256} you reviewed
    Run(source, inputs, apps, {'execution_pins': pins}).execute()   # refuses before any call if anything drifted

build() checks the caller's reviewed file hashes against the files on disk (every REQUIRED_FILES entry must be
present), captures the allowed library modules (symblic/lang/library/*.sym) by value, and records the semantic
kernel identity, the program and its exact JSON inputs, and the contracts of the capabilities the program uses.
validate() and prepare() refuse any drift before execution and return a detached JSON receipt.

The registry is fixed below: names are POSIX paths relative to BASE, the directory that holds the symblic
package (for example symblic/kernel/language.py). Every registered module calls symblic.kernel.identity.record()
first thing at import, so the code a process actually loaded is compared with the bytes on disk, and stale
bytecode or a module copied from another installation is refused.

This is a local integrity and compatibility check, not a signature, a code sandbox, or proof of the operator's
intended meaning. Arbitrary host extensions and in-process mutation remain trusted; it is not attestation
against a malicious host.

Depends on: symblic.kernel.language, symblic.kernel.identity, symblic.kernel.effects (capability contracts).
Used by: symblic.kernel.run (the run option `execution_pins`) and the front ends that build receipts.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import _imp
import hashlib
import importlib.util
import json
import marshal
import math
import re
import sys
import types
from pathlib import Path

from symblic.kernel import language as S

VERSION = 2
# Registry names are POSIX paths relative to BASE, the directory that holds the symblic package (the repository
# root of a checkout, or site-packages of an installed copy). Receipts record exactly these names.
BASE = Path(__file__).resolve().parents[2]
# First-party Python modules whose loaded code is bound to its source. REQUIRED_FILES must be hashed into every
# receipt; the others are checked whenever a process has loaded them. Each listed module calls
# symblic.kernel.identity.record() first thing at import (the two `_symblic_import_identity` lines at its top).
REQUIRED_FILES = frozenset({
    # the kernel and its language layer
    'symblic/kernel/language.py', 'symblic/kernel/run.py', 'symblic/kernel/effects.py',
    'symblic/kernel/execution_pins.py', 'symblic/kernel/evidence.py', 'symblic/kernel/certificates.py',
    'symblic/kernel/diagnose.py', 'symblic/kernel/identity.py', 'symblic/kernel/json_schema.py',
    'symblic/kernel/profiles.py', 'symblic/kernel/epistemic.py', 'symblic/kernel/grounding.py',
    'symblic/lang/abstraction.py',
    # exact adapters the kernel's builtins reach
    'symblic/adapters/geometry.py', 'symblic/adapters/variational.py', 'symblic/adapters/transport.py',
    'symblic/adapters/render.py', 'symblic/adapters/discrete.py', 'symblic/adapters/knowledge.py',
    'symblic/adapters/projection.py', 'symblic/adapters/operators.py', 'symblic/adapters/quantities.py',
    'symblic/adapters/proof.py', 'symblic/adapters/proof_steps.py', 'symblic/adapters/finite_logic.py',
    'symblic/adapters/proof_adapter.py', 'symblic/adapters/proof_session.py', 'symblic/adapters/proof_command.py',
    'symblic/adapters/logic.py',
    # the JavaScript adapter
    'symblic/js/check.py', 'symblic/js/normalize.py', 'symblic/js/contract.py',
    # delegation, spec sheets, authoring, constructors and team profiles the runner can load
    'symblic/delegate/contracts.py', 'symblic/delegate/run.py', 'symblic/spec/build.py',
    'symblic/spec/contracts.py', 'symblic/authoring/helpers.py', 'symblic/constructor/core.py',
    'symblic/constructor/journal.py', 'symblic/constructor/records.py', 'symblic/linear/constructor.py',
    'symblic/linear/resources.py', 'symblic/providers/agent_teams.py',
})
PYTHON_FILES = REQUIRED_FILES | frozenset({
    'symblic/intent/records.py', 'symblic/spec/sheets.py', 'symblic/providers/applicators.py',
    'symblic/providers/ollama_call.py',
})
# Library modules (`import units.`) a receipt may capture by value; later executions use the captured text.
LIBRARIES = frozenset({'constants', 'dates', 'graphs', 'kinship', 'lab', 'stats', 'text', 'units', 'records', 'order'})
LIBRARY_FILES = {f'symblic/lang/library/{name}.sym': name for name in LIBRARIES}
# Non-Python executable sources (and the JS parser's license) are bound by the kernel identity and checked
# against the process's initial disk snapshot before any pinned execution.
ASSET_FILES = frozenset({
    'symblic/kernel/process_limits.py', 'symblic/linear/worker.py', 'symblic/sandbox/landlock.py',
    'symblic/js/runner.js', 'symblic/js/contract_runner.js', 'symblic/js/normalize.js', 'symblic/js/acorn.js',
    'symblic/js/acorn-LICENSE.txt',
})
MAX_BYTES = 8_000_000
MAX_NODES = 100_000
MAX_DEPTH = 64
_SHA = re.compile(r'^[0-9a-f]{64}$')
_FIELDS = {'version', 'kernel_id', 'source_sha256', 'input_sha256', 'python_hashes', 'libraries',
           'capabilities', 'sha256'}
_RUNTIME = None
_RUNTIME_PROBLEMS = set()
_RUNTIME_LOADED_PROBLEMS = ()
_COMPILED = {}


def _fail(message):
    raise S.SymblicError('Execution pins: ' + message, kind='version')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    """Version 1 input identity: exact JSON types, exact text, finite numbers."""
    remaining = MAX_NODES
    text_bytes = 0

    def visit(item, depth):
        nonlocal remaining, text_bytes
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            _fail('JSON structure exceeds its finite limit.')
        typ = type(item)
        if item is None or typ is bool:
            return
        if typ is int:
            if item.bit_length() > S.MAX_DIGITS * 4:
                _fail('JSON integer exceeds the kernel digit limit.')
            return
        if typ is float:
            if not math.isfinite(item):
                _fail('nonfinite JSON number.')
            return
        if typ is str:
            if len(item) > MAX_BYTES:
                _fail('JSON text exceeds its finite limit.')
            try:
                text_bytes += len(item.encode('utf-8'))
            except UnicodeError:
                _fail('JSON text is not valid UTF-8.')
            if text_bytes > MAX_BYTES:
                _fail('aggregate JSON text exceeds its finite limit.')
            return
        if typ is list:
            if len(item) > remaining:
                _fail('JSON array exceeds its finite limit.')
            for child in item:
                visit(child, depth + 1)
            return
        if typ is dict:
            if len(item) > remaining:
                _fail('JSON object exceeds its finite limit.')
            for key, child in item.items():
                if type(key) is not str:
                    _fail('JSON keys must be exact strings.')
                visit(key, depth + 1)
                visit(child, depth + 1)
            return
        _fail('inputs and receipts must contain only finite JSON values.')

    visit(value, 0)
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                         allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail('inputs or receipts are not valid finite UTF-8 JSON.')
    if len(raw) > MAX_BYTES:
        _fail('JSON bytes exceed their finite limit.')
    return raw


def snapshot_inputs(inputs):
    """Detach nested caller values before the check and subsequent execution."""
    if type(inputs) is not dict:
        _fail('inputs must be a JSON object.')
    return json.loads(_json(inputs))


def _source_sha(source):
    if type(source) is not str or len(source) > S.MAX_SOURCE:
        _fail('source must be bounded text.')
    try:
        return _sha(source.encode('utf-8'))
    except UnicodeError:
        _fail('source is not valid UTF-8 text.')


def _digest(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _read(name):
    # Callers must first use the fixed registry above: no user-directed paths.
    try:
        path = BASE / name
        if path.is_symlink() or path.parent.is_symlink():
            _fail('a pinned dependency is a symlink: ' + name)
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
    except OSError:
        _fail('a pinned dependency is unreadable: ' + name)
    if len(raw) > MAX_BYTES:
        _fail('a pinned dependency is too large: ' + name)
    return raw


def _bytecode_matches(name, raw):
    """Refuse a cache Python could accept if it encodes another source.

    This covers timestamp collisions and unchecked hash caches. It is a bounded
    compatibility check, not attestation against arbitrary in-process changes.
    """
    path = BASE / name
    cached = Path(importlib.util.cache_from_source(str(path)))
    try:
        with cached.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if len(data) > MAX_BYTES:
        return False
    if len(data) < 16 or data[:4] != importlib.util.MAGIC_NUMBER:
        return True  # Python rejects this cache and compiles source.
    flags = int.from_bytes(data[4:8], 'little')
    if flags & ~3:
        return True
    if flags & 1:
        check_hash = _imp.check_hash_based_pycs != 'never' and (flags & 2 or _imp.check_hash_based_pycs == 'always')
        if check_hash and data[8:16] != importlib.util.source_hash(raw):
            return True
    else:
        try:
            stamp = int(path.stat().st_mtime) & 0xffffffff
        except OSError:
            return False
        if int.from_bytes(data[8:12], 'little') != stamp or int.from_bytes(data[12:16], 'little') != len(raw):
            return True
    key = (name, _sha(raw))
    try:
        expected = _COMPILED.get(key)
        if expected is None:
            expected = compile(raw, str(path), 'exec', dont_inherit=True, optimize=sys.flags.optimize)
            _COMPILED[key] = expected
        code = marshal.loads(data[16:])
        return isinstance(code, types.CodeType) and code == expected
    except (ValueError, TypeError, EOFError, SyntaxError, RecursionError):
        return False


def capture_runtime():
    """Once, during the kernel's initial import, bind its process to disk bytes.

    The deferred flag handles helper-first circular imports. Importing this
    helper into an older, already-running unmarked kernel cannot bless it.
    Modules loaded after the kernel must still match this same process snapshot.
    """
    global _RUNTIME, _RUNTIME_LOADED_PROBLEMS
    if _RUNTIME is not None:
        return
    if not getattr(S, '_EXECUTION_CAPTURE_PENDING', False):
        _fail('this process predates execution pin support; start a fresh worker.')
    snapshot = {}
    for name in PYTHON_FILES | ASSET_FILES:
        if not (BASE / name).is_file():
            continue
        raw = _read(name)
        snapshot[name] = _sha(raw)
        if name in PYTHON_FILES and not _bytecode_matches(name, raw):
            _RUNTIME_PROBLEMS.add(name)
    _RUNTIME = snapshot
    _RUNTIME_LOADED_PROBLEMS = _symblic_identity.audit(BASE, PYTHON_FILES, snapshot)
    S._EXECUTION_CAPTURE_PENDING = False


def _check_loaded_runtime():
    if _RUNTIME is None:
        _fail('this process has no initial kernel file snapshot; start a fresh worker.')
    problems = _RUNTIME_LOADED_PROBLEMS or _symblic_identity.audit(BASE, PYTHON_FILES, _RUNTIME)
    if problems:
        _fail('loaded Python code/bytecode identity is incompatible: ' + problems[0])


def _imports(source, libraries):
    """Reject unsupported imports before even an earlier effect can execute."""
    used = set()
    for text in [source] + [row['source'] for row in libraries.values()]:
        try:
            nodes = S.walk(S.parse(text)['statements'])
            for node in nodes:
                if node.k == 'import' and (node.saved or node.module not in libraries):
                    _fail('saved or uncaptured imports are unavailable in a pinned execution.')
                if node.k in ('observe', 'act'):
                    used.add(node.capability)
        except S.SymblicError as exc:
            if exc.kind == 'version':
                raise
            _fail('a pinned source does not parse: ' + exc.message)
    return used


def _catalogue(rows):
    from symblic.kernel import effects as FX
    if rows is None:
        return {}
    rows = json.loads(_json(rows))
    if type(rows) not in (dict, list):
        _fail('capability metadata must be a JSON registry.')
    items = list(rows.items()) if type(rows) is dict else [
        (row.get('name'), row) if type(row) is dict else (None, row) for row in rows]
    seen = set()
    for name, row in items:
        if type(name) is not str or type(row) is not dict:
            _fail('capability registry contains an invalid or duplicated name.')
        # A host catalogue may also declare legacy bare names such as calc. The effects
        # language cannot address them, and its normalizer excludes them.
        # Preserve duplicate detection for every addressable capability.
        if not FX._CAP_RX.fullmatch(name):
            continue
        if name in seen:
            _fail('capability registry contains an invalid or duplicated name.')
        seen.add(name)
    return json.loads(_json(FX.normalize_catalogue(rows)))


def build(source, inputs, module_hashes, *, capabilities=None):
    """Build from reviewed exact hashes, refusing a change since review.

    Python keys are PYTHON_FILES; library keys are symblic/lang/library/NAME.sym from
    LIBRARY_FILES. Required Python files cannot be omitted. Libraries included
    in the hash map are captured; later executions use these source snapshots.
    """
    _check_loaded_runtime()
    inputs = snapshot_inputs(inputs)
    if type(module_hashes) is not dict or len(module_hashes) > len(PYTHON_FILES) + len(LIBRARY_FILES):
        _fail('module hashes must be a bounded exact registry map.')
    python, libraries = {}, {}
    if not REQUIRED_FILES <= module_hashes.keys():
        _fail('required kernel files are missing from reviewed module hashes.')
    for name, expected in module_hashes.items():
        if type(name) is not str or name not in PYTHON_FILES | LIBRARY_FILES.keys() or not _digest(expected):
            _fail('unknown dependency or invalid digest in reviewed module hashes.')
        raw = _read(name)
        if _sha(raw) != expected:
            _fail('reviewed dependency changed: ' + name)
        if name in PYTHON_FILES:
            python[name] = expected
        else:
            try:
                text = raw.decode('utf-8')
            except UnicodeError:
                _fail('library source is not UTF-8: ' + name)
            _source_sha(text)
            libraries[LIBRARY_FILES[name]] = {'source': text, 'sha256': expected}
    used = _imports(source, libraries)
    catalogue = _catalogue(capabilities)
    if not used <= catalogue.keys():
        _fail('a used capability has no reviewed contract.')
    pins = {'version': VERSION, 'kernel_id': S.kernel_id()['id'],
            'source_sha256': _source_sha(source), 'input_sha256': _sha(_json(inputs)),
            'python_hashes': python, 'libraries': libraries,
            'capabilities': {name: catalogue[name] for name in sorted(used)}}
    pins['sha256'] = _sha(_json(pins))
    return validate(pins, source, inputs)


def validate(pins, source, inputs):
    """Return detached checked pins or raise SYM_VERSION; never read a provider."""
    _check_loaded_runtime()
    pins = json.loads(_json(pins))
    inputs = snapshot_inputs(inputs)
    if type(pins) is not dict or set(pins) != _FIELDS or type(pins['version']) is not int or pins['version'] != VERSION:
        _fail('unknown or malformed receipt version.')
    if not _digest(pins['sha256']) or pins['sha256'] != _sha(_json({k: v for k, v in pins.items() if k != 'sha256'})):
        _fail('receipt integrity differs.')
    if pins['kernel_id'] != S.kernel_id()['id']:
        _fail('semantic kernel identity changed.')
    if pins['source_sha256'] != _source_sha(source) or pins['input_sha256'] != _sha(_json(inputs)):
        _fail('program source or exact input values changed.')
    python, libraries = pins['python_hashes'], pins['libraries']
    if type(python) is not dict or not REQUIRED_FILES <= python.keys() or not python.keys() <= PYTHON_FILES:
        _fail('kernel file registry is missing or unknown.')
    # kernel_id() may have lazily imported additional registered adapters.
    _check_loaded_runtime()
    for name in ASSET_FILES:
        if _RUNTIME.get(name) != _sha(_read(name)):
            _fail('runtime asset changed: ' + name)
    for name, expected in python.items():
        raw = _read(name)
        if not _digest(expected) or _RUNTIME.get(name) != expected or _sha(raw) != expected:
            _fail('kernel dependency changed: ' + name)
        if name in _RUNTIME_PROBLEMS or not _bytecode_matches(name, raw):
            _fail('cached Python bytecode differs from pinned source: ' + name)
    if type(libraries) is not dict or not libraries.keys() <= LIBRARIES:
        _fail('library snapshot registry is invalid.')
    for name, row in libraries.items():
        if type(row) is not dict or set(row) != {'source', 'sha256'} or not _digest(row['sha256']) or \
                _source_sha(row['source']) != row['sha256']:
            _fail('library snapshot integrity differs: ' + name)
    used = _imports(source, libraries)
    capabilities = pins['capabilities']
    if type(capabilities) is not dict or set(capabilities) != used or \
            _json(capabilities) != _json(_catalogue(capabilities)):
        _fail('used capability contracts are missing or malformed.')
    return pins


class _PinnedHost:
    """Keep FX's later metadata lookup on the same checked snapshot."""
    def __init__(self, host, catalogue):
        self._host, self._catalogue = host, catalogue

    def catalogue(self):
        return json.loads(_json(self._catalogue))

    def __getattr__(self, name):
        return getattr(self._host, name)


def prepare(run):
    """Run's first gate: freeze inputs, check pins, then check effect contracts.

    A live host is queried for metadata only, once. Replay requires the matching
    recorded effects catalogue and never consults that host. No capability is
    performed here. The optional run field is not authenticated authorization.
    """
    inputs = snapshot_inputs(run.inputs)
    pins = validate(run.opts['execution_pins'], run.source, inputs)
    expected = pins['capabilities']
    if expected:
        from symblic.kernel import effects as FX
        if run.opts.get('replay'):
            folder = getattr(run.store, 'dir', None)
            if not folder:
                _fail('effect replay has no recorded capability catalogue.')
            try:
                with (Path(folder) / FX.CATALOGUE_FILE).open('rb') as stream:
                    raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    _fail('recorded capability catalogue exceeds its limit.')
                frozen = json.loads(raw)
                if type(frozen) is not dict or type(frozen.get('version')) is not int or frozen['version'] != FX.VERSION:
                    _fail('recorded capability catalogue version is invalid.')
                actual = _catalogue(frozen.get('capabilities'))
            except (OSError, ValueError, TypeError, UnicodeError):
                _fail('recorded capability catalogue is unavailable or damaged.')
        else:
            host = run.opts.get('effects')
            if host is None or not callable(getattr(host, 'catalogue', None)):
                _fail('a used capability has no host metadata.')
            try:
                actual = _catalogue(host.catalogue())
            except S.SymblicError:
                raise
            except Exception:  # noqa: BLE001 - metadata failure is a pre-execution refusal
                _fail('host capability metadata is unavailable.')
        if any(name not in actual or _json(spec) != _json(actual[name]) for name, spec in expected.items()):
            _fail('a used capability contract changed since review.')
        if not run.opts.get('replay'):
            run.opts['effects'] = _PinnedHost(host, actual)
    run.inputs, run._execution_pins = inputs, pins


# The kernel sets this only at its import boundary. In helper-first order the
# kernel returns while this module is partial, then this deferred call captures.
if getattr(S, '_EXECUTION_CAPTURE_PENDING', False):
    capture_runtime()
