"""Which exact code a benchmark result depends on: SHA-256 digests of source files, keyed by repository path.

What it is for
    A benchmark plan or ledger row records the digests of the files its result depends on, so a result can be
    attributed to one version of the code and a resumed run refuses to mix versions. Keys are POSIX paths relative
    to the directory that contains the ``symblic`` package (for example ``symblic/kernel/run.py``), the same names
    ``symblic.kernel.execution_pins`` uses.

    file_sha256(path)   digest of one repository file, or None when it is missing or unreadable
    code_pins(paths)    {path: digest or None} for several files
    kernel_files()      the kernel's own registry: every required Python file and standard-library module

These are disk digests only. For "is the code *running* in this process the code on disk", see
``symblic.mica.source_identity``.

Depends on: ``symblic.kernel.execution_pins`` (only inside ``kernel_files``). Nothing runs on import.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

# The directory that contains the `symblic` package (the repository root in a checkout).
ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 8_000_000


def _checked(path: str) -> str:
    pure = PurePosixPath(path)
    if type(path) is not str or pure.is_absolute() or '..' in pure.parts or '\\' in path or not path:
        raise ValueError(f'not a repository-relative path: {path!r}')
    return path


def file_sha256(path: str) -> str | None:
    """SHA-256 of ROOT/path (a regular, non-symlinked file of at most MAX_BYTES), or None."""
    source = ROOT / _checked(path)
    try:
        if source.is_symlink():
            return None
        with source.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
    except OSError:
        return None
    return hashlib.sha256(raw).hexdigest() if len(raw) <= MAX_BYTES else None


def code_pins(paths) -> dict:
    """{path: sha256 or None} for each repository-relative path, in sorted order."""
    return {path: file_sha256(path) for path in sorted(set(paths))}


def kernel_files() -> frozenset:
    """Every file the kernel registers as part of an execution: required Python modules and library sources."""
    from symblic.kernel import execution_pins as X
    return frozenset(X.REQUIRED_FILES) | frozenset(X.LIBRARY_FILES)
