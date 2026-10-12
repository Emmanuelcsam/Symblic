"""Crash-safe JSON files for the autogen records and the OS prototype's receipts.

What it is for
    Every durable record in this package (an autogen run, a workspace receipt, an OS
    execution receipt) is one JSON file that must never be left half-written. A crash or a
    power loss in the middle of a write leaves either the old file or the new one, never a
    mixture.

How it works
    `atomic_json(path, value)` writes the JSON to a temporary file in the same folder,
    flushes and fsyncs it, renames it over the target (an atomic step on POSIX file systems)
    and then fsyncs the folder so the rename itself survives a power loss. The folder is
    created with mode 0700 when it is missing.

Depends on
    The Python standard library only.

Used by
    symblic.autogen.coordinator (run records), symblic.autogen.workspaces (workspace
    receipts), symblic.os.receipts and symblic.os.release_manifest, and the host
    integration in integration/host/symblicos_tasks.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def atomic_json(path, value) -> None:
    """Write `value` as JSON to `path` atomically (sorted keys, UTF-8, NaN refused)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(value, out, ensure_ascii=False, sort_keys=True, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
