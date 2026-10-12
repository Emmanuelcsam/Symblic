"""Import identity: prove that the Python code a process is running is the code on disk.

Each registered module (see symblic.kernel.execution_pins.PYTHON_FILES) starts with two lines:

    _symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
    _symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

record() compares the module's executing code object with a fresh compilation of the exact source bytes and
keeps the result with the module's globals. audit(base, names, expected) then checks every loaded registered
module (aliases and __main__ included) against the caller's initial snapshot of the source hashes and
against the current disk. Registry names are POSIX paths relative to `base`. No provider, store or network.

This detects stale loaded code, accepted stale bytecode, unmarked loaded copies and copies from another
installation. It is a local compatibility gate, not protection against a malicious Python host,
monkeypatching, custom importers lying about execution, or races in the operating system. A compile and hash
match is not semantic correctness or authenticated provenance.

Depends on: the standard library only (it must import first). Used by: every registered module and by
symblic.kernel.execution_pins.
"""
from __future__ import annotations

import hashlib
import os
import sys
import types
from pathlib import Path

VERSION = 1
MAX_SOURCE_BYTES = 8_000_000
MAX_TOTAL_SOURCE_BYTES = 64_000_000
MAX_RECORDS = 256
MAX_MODULES = 32_768
MAX_FILES = 256
MARKER = '_symblic_import_identity'
_records = {}
_compiled = {}
_total_source_bytes = 0


def record(path, module_code):
    """Record the actual calling module frame; a mismatch remains inspectable.

    Returning an invalid record lets ordinary imports finish. Execution pins
    subsequently refuse it; importing a legacy module alone does not promise a
    pinned execution. Entries are bounded and never replaced for other globals.
    """
    global _total_source_bytes
    frame = sys._getframe(1)
    namespace = frame.f_globals
    result = {'version': VERSION, 'path': '', 'sha256': None, 'matched': False,
              'reason': 'invalid_module_frame'}
    try:
        if (type(path) is not str or len(path) > 4096 or
                type(module_code) is not types.CodeType or module_code is not frame.f_code or
                module_code.co_name != '<module>' or namespace.get('__file__') != path):
            return result
        if len(_records) >= MAX_RECORDS and id(namespace) not in _records:
            result['reason'] = 'record_budget'
            return result
        source = Path(path)
        result['path'] = str(source.resolve())
        if source.suffix != '.py' or source.is_symlink() or source.parent.is_symlink():
            result['reason'] = 'source_path'
        else:
            with source.open('rb') as stream:
                raw = stream.read(MAX_SOURCE_BYTES + 1)
            if len(raw) > MAX_SOURCE_BYTES:
                result['reason'] = 'source_budget'
            else:
                result['sha256'] = hashlib.sha256(raw).hexdigest()
                key = (result['sha256'], module_code.co_filename, sys.flags.optimize)
                expected = _compiled.get(key)
                if expected is None:
                    if len(_compiled) >= MAX_RECORDS or _total_source_bytes + len(raw) > MAX_TOTAL_SOURCE_BYTES:
                        result['reason'] = 'compile_budget'
                    else:
                        _total_source_bytes += len(raw)
                        expected = compile(raw, module_code.co_filename, 'exec',
                                           dont_inherit=True, optimize=sys.flags.optimize)
                        _compiled[key] = expected
                if expected is not None:
                    result['matched'] = module_code == expected
                    result['reason'] = 'matched' if result['matched'] else 'executing_bytecode_differs'
    except (OSError, ValueError, SyntaxError, TypeError, RecursionError):
        result['reason'] = 'source_unavailable_or_uncompilable'
    finally:
        del frame
    # Retaining globals also prevents id reuse and copied-marker impersonation.
    _records[id(namespace)] = (namespace, result.copy())
    return result


def _valid_name(name):
    """A registry name: a relative POSIX path of a .py file under the audit base, without '.' or '..' parts."""
    return (type(name) is str and 0 < len(name) <= 128 and name.endswith('.py') and '\\' not in name
            and '\0' not in name and not name.startswith('/')
            and all(part not in ('', '.', '..') for part in name.split('/')))


def _source_path(path):
    """The source file a module's __file__ stands for: a cached or sourceless .pyc maps to its .py."""
    if path.endswith('.pyc'):
        head, tail = os.path.split(path)
        if os.path.basename(head) == '__pycache__':
            head = os.path.dirname(head)
        path = os.path.join(head, tail.split('.', 1)[0] + '.py')
    return path


def audit(base, filenames, expected):
    """Return bounded diagnostics for loaded copies; an empty tuple means pass.

    ``filenames`` are registry names: POSIX paths relative to ``base`` (for the
    kernel, ``base`` is the directory that holds the ``symblic`` package and a
    name looks like ``symblic/kernel/language.py``). A loaded module belongs to a
    name when its file is ``base/name``, when its file path ends with ``/name``
    (a copy from another installation, which is refused), or when its dotted
    alias spells the name (``symblic.kernel.language``).

    ``expected`` is the host's initial disk hash map, not user attestation. Files
    absent from sys.modules are covered by the host's separate disk/cache checks.
    Aliases from the same exact source path are allowed when independently marked.
    An identical module copied from another installation is conservatively refused.
    """
    if (type(filenames) not in (set, frozenset, list, tuple) or len(filenames) > MAX_FILES or
            type(expected) is not dict or len(expected) > MAX_FILES * 2 or
            not all(_valid_name(name) for name in filenames)):
        return ('identity registry is invalid or exceeds its finite bound',)
    if len(sys.modules) > MAX_MODULES:
        return ('loaded module registry exceeds its finite bound',)
    try:
        modules = tuple(sys.modules.items())
        directory = Path(base).resolve()
    except (RuntimeError, OSError, ValueError, TypeError):
        return ('loaded module registry or source directory is unavailable',)
    names = frozenset(filenames)
    by_tail = {}
    for name in names:
        by_tail.setdefault(name.rsplit('/', 1)[-1], []).append(name)
    root = os.path.join(str(directory), '')

    def registered(path, alias):
        """The registry name a loaded module stands for, by its file first and then by its alias; or None."""
        if type(path) is str and 0 < len(path) <= 4096 and '\0' not in path:
            source = os.path.normpath(_source_path(os.path.abspath(path)))
            if source.startswith(root):
                relative = source[len(root):].replace(os.sep, '/')
                if relative in names:
                    return relative
            slashed = source.replace(os.sep, '/')
            for name in by_tail.get(slashed.rsplit('/', 1)[-1], ()):
                if slashed.endswith('/' + name):
                    return name
        if type(alias) is str and 0 < len(alias) <= 4096:
            dotted = alias.replace('.', '/') + '.py'
            for name in by_tail.get(dotted.rsplit('/', 1)[-1], ()):
                if dotted == name or dotted.endswith('/' + name):
                    return name
        return None

    problems = []
    seen = set()
    current_hashes = {}
    bytes_read = 0
    for alias, module in modules:
        # Some CFFI libraries expose __class__ as ModuleType without a module layout.
        # Inspect the real type, so the module descriptor is used only on modules.
        if not issubclass(type(module), types.ModuleType):
            if registered(None, alias) is not None:
                problems.append('registered module is not a Python module: ' + str(alias)[:256])
            continue
        namespace = types.ModuleType.__getattribute__(module, '__dict__')
        name = registered(namespace.get('__file__'), alias)
        if name is None or id(namespace) in seen:
            continue
        seen.add(id(namespace))
        if len(seen) > MAX_RECORDS:
            return ('loaded registered copies exceed their finite bound',)
        row = _records.get(id(namespace))
        diagnostic = 'loaded Python identity differs: ' + name + ' (' + str(alias)[:256] + ')'
        if row is None or row[0] is not namespace:
            problems.append(diagnostic + ': unmarked module globals')
            continue
        saved = row[1]
        if namespace.get(MARKER) != saved:
            problems.append(diagnostic + ': import marker changed or absent')
        elif not saved['matched']:
            problems.append(diagnostic + ': ' + saved['reason'])
        elif saved['path'] != str(directory / name):
            problems.append(diagnostic + ': different source installation')
        elif saved['sha256'] != expected.get(name):
            problems.append(diagnostic + ': loaded source differs from initial disk snapshot')
        else:
            if name not in current_hashes:
                try:
                    source = directory / name
                    if source.is_symlink() or source.parent.is_symlink():
                        raise ValueError('symlink')
                    with source.open('rb') as stream:
                        raw = stream.read(min(MAX_SOURCE_BYTES, MAX_TOTAL_SOURCE_BYTES - bytes_read) + 1)
                    bytes_read += len(raw)
                    if len(raw) > MAX_SOURCE_BYTES or bytes_read > MAX_TOTAL_SOURCE_BYTES:
                        return ('loaded source audit exceeds its finite byte bound',)
                    current_hashes[name] = hashlib.sha256(raw).hexdigest()
                except (OSError, ValueError):
                    current_hashes[name] = None
            if current_hashes[name] != saved['sha256']:
                problems.append(diagnostic + ': loaded source differs from current disk bytes')
    return tuple(sorted(set(problems)))


# This module has no first-party dependency; it records its own actual frame once.
_symblic_import_identity = record(__file__, sys._getframe().f_code)
