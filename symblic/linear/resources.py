"""Memory admission for the linear constructor's solver worker (optional; Linux cgroup v2 only).

What it is for
    Before the linear constructor starts its Z3 worker with combined_memory=True, admit() reads this process's
    own cgroup v2 memory facts (/proc/self/cgroup, memory.max and memory.current of every ancestor) and refuses
    unless the process runs inside a capped envelope of at most 600 MiB, the parent uses at most 256 MiB now,
    and there is room for the worker's 256 MiB address space plus an 88 MiB reserve. Missing or unreadable
    facts refuse (MemoryAdmissionRefused); nothing falls back silently.

What it is not
    It writes no cgroup files, starts no process and reserves nothing: the result is an observation at
    admission time. An address-space cap is not a resident-memory measurement, and page cache is charged by
    the cgroup, not by this check. The constants were chosen after measurements on the development machine
    (profile 'd10-parent-worker-600m-v1'; "D10" is the prototype's name in the development notes).

Depends on: the standard library. Used by: symblic.linear.constructor (memory_guard). Status: prototype; you
need to run the caller in a memory-capped cgroup (for example a systemd scope with MemoryMax=600M) for it to
admit anything.
"""
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

from pathlib import Path
import os

MIB = 1024 * 1024
ENVELOPE_BYTES = 600 * MIB
PARENT_CURRENT_BYTES = 256 * MIB
RESERVE_BYTES = 88 * MIB
# Selected only after measurements; must agree with the worker host default.
WORKER_AS_BYTES = 256 * MIB


class MemoryAdmissionRefused(ValueError):
    pass


def _text(path):
    with path.open('rb') as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise MemoryAdmissionRefused('cgroup field exceeds read bound')
    return raw.decode('ascii').strip()


def _number(text):
    if not text or not text.isascii() or not text.isdigit() or len(text) > 20:
        raise MemoryAdmissionRefused('invalid cgroup integer')
    return int(text)


def memory_snapshot(*, proc_cgroup=Path('/proc/self/cgroup'), root=Path('/sys/fs/cgroup')):
    """Read own cgroup and every limiting ancestor; unavailable facts fail closed."""
    rows = _text(proc_cgroup).splitlines()
    unified = [row[3:] for row in rows if row.startswith('0::')]
    if len(unified) != 1 or not unified[0].startswith('/'):
        raise MemoryAdmissionRefused('exact unified cgroup unavailable')
    parts = Path(unified[0]).parts[1:]
    if len(parts) > 32 or any(part in ('.', '..') for part in parts):
        raise MemoryAdmissionRefused('invalid cgroup path')
    base = root.resolve(strict=True)
    leaf = base.joinpath(*parts).resolve(strict=True)
    if not leaf.is_relative_to(base):
        raise MemoryAdmissionRefused('cgroup escapes root')
    levels = []
    node = leaf
    while node != base:
        limit = _text(node / 'memory.max')
        current = _number(_text(node / 'memory.current'))
        levels.append({'path': str(node), 'max': None if limit == 'max' else _number(limit), 'current': current})
        node = node.parent
    if not levels:
        raise MemoryAdmissionRefused('root scope is not an admitted worker envelope')
    caps = [row for row in levels if row['max'] is not None]
    if not caps:
        raise MemoryAdmissionRefused('memory envelope is uncapped')
    return {'pid': os.getpid(), 'path': str(leaf), 'levels': levels,
            'effective_max': min(row['max'] for row in caps),
            'available': min(max(0, row['max']-row['current']) for row in caps),
            'leaf_current': levels[0]['current'],
            'peak': _number(_text(leaf / 'memory.peak'))}


def admit(*, proc_cgroup=Path('/proc/self/cgroup'), root=Path('/sys/fs/cgroup')):
    """Fixed conservative profile, no caller-selected cap or memory-read bypass."""
    try:
        snapshot = memory_snapshot(proc_cgroup=proc_cgroup, root=root)
    except (OSError, UnicodeError, ValueError) as exc:
        raise MemoryAdmissionRefused('memory facts unavailable: ' + type(exc).__name__) from exc
    if snapshot['effective_max'] > ENVELOPE_BYTES:
        raise MemoryAdmissionRefused('scope must be capped at or below 600MiB')
    if snapshot['leaf_current'] > PARENT_CURRENT_BYTES:
        raise MemoryAdmissionRefused('parent scope current exceeds 256MiB admission allowance')
    if snapshot['available'] < WORKER_AS_BYTES + RESERVE_BYTES:
        raise MemoryAdmissionRefused('insufficient combined headroom')
    return {'profile': 'd10-parent-worker-600m-v1', 'worker_address_space_bytes': WORKER_AS_BYTES,
            'parent_current_ceiling_bytes': PARENT_CURRENT_BYTES, 'reserve_bytes': RESERVE_BYTES,
            'snapshot': snapshot, 'scope': 'admission-time observation; not a future allocation reservation'}
