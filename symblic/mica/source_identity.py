"""Source pins for receipts: which exact files of this checkout produced a result, checked against loaded code.

What it is for
    MICA, the experiment registry and the distillation checker write the SHA-256 of the source files they ran
    into their receipts. A receipt is only meaningful if the code that actually executed is the code those
    digests name. This module is a small convenience layer over ``symblic.kernel.identity``:

        pin(module)            -> ('symblic/mica/search.py', sha256) for one loaded, marked module
        pins(modules)          -> {repository-relative path: sha256} for several modules
        audit({path: sha256})  -> () when every loaded copy of each file is marked, unchanged since import and
                                  identical to the expected digest; otherwise a sorted tuple of problem strings

    Paths are relative to the directory that contains the ``symblic`` package (the repository root of a
    checkout), the same names ``symblic.kernel.execution_pins`` uses for its registry.

How the markers work
    Every first-party module starts with::

        _symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
        _symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

    ``record`` hashes the module's source bytes and compares the code object being executed with a fresh
    compile of exactly those bytes, so a stale ``.pyc`` or a file edited after import is detected.
    ``symblic.kernel.identity.audit`` then checks every loaded copy of a registered file against an expected
    digest and the current disk bytes; ``audit`` below is that check with this checkout's root filled in.

Limits
    A local consistency gate: it catches stale code after an edit, two installations mixed in one process, and
    bytecode that does not match its source. It is not a defence against a malicious Python process, monkey
    patching or a custom importer that lies about what it executed.

Depends on: ``symblic.kernel.identity`` only. Nothing runs on import except this module's own marker.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
from pathlib import Path, PurePosixPath

VERSION = 1
# The directory that contains the `symblic` package (the repository root in a checkout).
ROOT = Path(__file__).resolve().parent.parent.parent
MAX_SOURCE_BYTES = 8_000_000
MARKER = getattr(_symblic_identity, 'MARKER', '_symblic_import_identity')


class IdentityError(ValueError):
    """A loaded module cannot be pinned: no genuine marker, changed on disk, or outside this installation."""


def relative_path(path) -> str:
    """'/abs/.../symblic/mica/search.py' -> 'symblic/mica/search.py' (refuses files outside this installation)."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        raise IdentityError(f'{resolved} is outside this Symblic installation ({ROOT})') from None


def check_relative(path) -> str:
    """Validate a stored repository-relative source path: POSIX, below the root, a .py file, no '..'."""
    if type(path) is not str or not path or len(path) > 128:
        raise IdentityError('source path must be a non-empty string of at most 128 characters')
    pure = PurePosixPath(path)
    if (pure.is_absolute() or '..' in pure.parts or '.' in pure.parts or '\\' in path or pure.suffix != '.py'
            or pure.as_posix() != path):
        raise IdentityError(f'not a repository-relative Python source path: {path!r}')
    return path


def file_sha256(path) -> str:
    """SHA-256 of a regular, non-symlinked source file of at most MAX_SOURCE_BYTES."""
    source = Path(path)
    if source.is_symlink() or source.parent.is_symlink():
        raise IdentityError(f'symlinked source refused: {source}')
    try:
        with source.open('rb') as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        raise IdentityError(f'source unreadable: {source} ({type(exc).__name__})') from None
    if len(raw) > MAX_SOURCE_BYTES:
        raise IdentityError(f'source exceeds {MAX_SOURCE_BYTES} bytes: {source}')
    return hashlib.sha256(raw).hexdigest()


def audit(expected) -> tuple:
    """Check every loaded copy of the expected files; () means pass.

    ``expected`` maps repository-relative paths to SHA-256 digests. A file that is not loaded in this process is
    not a problem here (callers that need it check disk bytes themselves, as ``pin`` does).
    """
    if type(expected) is not dict:
        return ('identity registry is invalid',)
    try:
        for path in expected:
            check_relative(path)
    except IdentityError as exc:
        return (str(exc),)
    return _symblic_identity.audit(ROOT, tuple(sorted(expected)), dict(expected))


def pin(module):
    """(repository-relative path, sha256) of a loaded module whose marker matches its unchanged source file."""
    name = getattr(module, '__name__', '?')
    found = getattr(module, MARKER, None)
    if type(found) is not dict or found.get('matched') is not True or type(found.get('sha256')) is not str:
        raise IdentityError(f'{name}: no matched import marker ({(found or {}).get("reason", "absent")})')
    path = relative_path(found['path'])
    if file_sha256(ROOT / path) != found['sha256']:
        raise IdentityError(f'{name}: source on disk changed since import')
    problems = audit({path: found['sha256']})
    if problems:
        raise IdentityError(f'{name}: {problems[0]}')
    return path, found['sha256']


def pins(modules) -> dict:
    """{repository-relative path: sha256} for each module (see pin)."""
    result = {}
    for module in modules:
        path, digest = pin(module)
        result[path] = digest
    return result
