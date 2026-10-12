#!/usr/bin/env python3
"""Inventory an already installed private solver; explicit owner publication only.

No subprocesses, network, package imports or installation. Import never provisions. The
fixed paths are host administration, never values supplied by a Symblic program.
Run with a trusted system Python using -I -S -B. File pins are trusted-host
integrity records, not proof that an interpreter or solver executed correctly.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

VERSION = 1
PACKAGE_VERSION = '4.15.4.0'
Z3_VERSION = '4.15.4'
PYTHON_MINOR = f'{sys.version_info.major}.{sys.version_info.minor}'
PYTHON_VERSION = '.'.join(map(str, sys.version_info[:3]))
REPO = Path(__file__).resolve().parents[2]   # the repository root (this file is tools/scripts/...)
HOST = Path.home() / '.local/share/symblic/linear'
ENV = HOST / 'environments' / f'z3-{PACKAGE_VERSION}-py{PYTHON_MINOR}-v1'
SYSTEM_PYTHON = Path(f'/usr/bin/python{PYTHON_MINOR}')
PACKAGE_DIRS = ('z3', f'z3_solver-{PACKAGE_VERSION}.dist-info')
MAX_JSON = 65536
MAX_FILE = 40_000_000
MAX_PACKAGE = 64_000_000
MAX_FILES = 256
MAX_ENTRIES = 1024
LOCK_WAIT = 2.0
HEX = re.compile(r'[0-9a-f]{64}\Z')


class ProvisionError(ValueError):
    pass


def _fail(message):
    raise ProvisionError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _cleanup(action, primary):
    try:
        action()
    except BaseException as error:
        if primary is None:
            raise
        try:
            primary.add_note('Provisioning cleanup also failed: ' + type(error).__name__)
        except BaseException:
            pass


def _directory(path):
    path = Path(path)
    if not path.is_absolute() or len(str(path)) > 4096:
        _fail('Host directories require bounded absolute paths')
    for parent in reversed((path, *path.parents)):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
            _fail('Directory must be real and controlled by this owner or root: ' + str(parent))
    return path


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(path, limit, *, missing=False, root_owner=False):
    """Bounded exact regular-file read, refusing symlinks and group/other writes."""
    path = Path(path)
    try:
        before = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise
    owners = (0, os.getuid()) if root_owner else (os.getuid(),)
    if not stat.S_ISREG(before.st_mode) or before.st_uid not in owners or before.st_mode & 0o022:
        _fail('Expected a non-writable-by-others regular file: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    primary = None
    try:
        opened = os.fstat(fd)
        if _file_identity(opened) != _file_identity(before) or opened.st_size > limit:
            _fail('File changed or exceeds its size bound: ' + str(path))
        chunks, count = [], 0
        while count <= limit:
            part = os.read(fd, min(65536, limit + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
        after = os.fstat(fd)
        if count > limit or _file_identity(opened) != _file_identity(after):
            _fail('File changed or exceeds its size bound: ' + str(path))
        return b''.join(chunks)
    except BaseException as error:
        primary = error
        raise
    finally:
        _cleanup(lambda: os.close(fd), primary)


def _pairs(rows):
    out = {}
    for key, value in rows:
        if key in out:
            _fail('Duplicate JSON key')
        out[key] = value
    return out


def _number(_text):
    _fail('Only exact integer JSON numbers are permitted')


def _json(raw):
    if type(raw) is not bytes or len(raw) > MAX_JSON:
        _fail('JSON record exceeds 64 KiB')
    try:
        return json.loads(raw.decode('ascii'), object_pairs_hook=_pairs, parse_float=_number, parse_constant=_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ProvisionError('Invalid bounded ASCII JSON record') from error


def _canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    except (ValueError, TypeError, RecursionError) as error:
        raise ProvisionError('Invalid canonical record') from error
    if len(raw) > MAX_JSON:
        _fail('Canonical record exceeds 64 KiB')
    return raw


def _hex(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _runtime_shape(data):
    keys = {'python', 'python_sha256', 'worker_sha256', 'purelib', 'z3_version', 'package'}
    if type(data) is not dict or set(data) != keys or data['z3_version'] != Z3_VERSION:
        _fail('Invalid existing runtime fields or solver version')
    for key in ('python', 'purelib'):
        value = data[key]
        if type(value) is not str or not 1 <= len(value) <= 4096 or '\0' in value or not Path(value).is_absolute():
            _fail('Invalid existing runtime path')
    if not _hex(data['python_sha256']) or not _hex(data['worker_sha256']):
        _fail('Invalid existing runtime source pin')
    package = data['package']
    if type(package) is not dict or not 1 <= len(package) <= MAX_FILES:
        _fail('Invalid existing runtime package map')
    for name, digest in package.items():
        if type(name) is not str or not 1 <= len(name) <= 4096 or '\0' in name or not _hex(digest):
            _fail('Invalid existing runtime package pin')
        path = Path(name)
        if path.is_absolute() or not path.parts or path.parts[0] not in PACKAGE_DIRS or '..' in path.parts or str(path) != name:
            _fail('Invalid existing runtime package path')
    return data


def review(path):
    raw = _read(path, MAX_JSON)
    data = _json(raw)
    if type(data) is not dict or set(data) != {'version', 'worker_sha256', 'requirements_lock_sha256', 'package_version'} \
            or type(data['version']) is not int or data['version'] != VERSION \
            or not _hex(data['worker_sha256']) or not _hex(data['requirements_lock_sha256']) \
            or data['package_version'] != PACKAGE_VERSION:
        _fail('Review record must name exact version, worker, requirements lock and package version')
    return data, _sha(raw)


def _venv_config(raw):
    """Admit the documented uv layout, not arbitrary Python configuration text."""
    if type(raw) is not bytes or not raw or len(raw) > 4096:
        _fail('Invalid bounded pyvenv.cfg')
    try:
        text = raw.decode('ascii')
    except UnicodeError as error:
        raise ProvisionError('pyvenv.cfg must use the reviewed ASCII layout') from error
    # Python normalizes key case/whitespace and accepts last-wins duplicates.
    # Require one unambiguous canonical spelling instead, before interpreting it.
    rows = text.split('\n')
    if rows[-1] == '':
        rows.pop()
    values = {}
    allowed = {'home', 'implementation', 'uv', 'version_info', 'include-system-site-packages'}
    if len(rows) != len(allowed):
        _fail('pyvenv.cfg must contain exactly the five reviewed uv fields')
    for row in rows:
        key, separator, value = row.partition(' = ')
        if separator != ' = ' or key not in allowed or key in values or not value \
                or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            _fail('Ambiguous, duplicate or unknown pyvenv.cfg field')
        values[key] = value
    if values['home'] != str(SYSTEM_PYTHON.parent) or values['implementation'] != 'CPython' \
            or values['version_info'] != PYTHON_VERSION:
        _fail('pyvenv.cfg must name the fixed trusted system CPython home and exact version')
    if values['include-system-site-packages'] != 'false':
        _fail('Private environment must exclude system site-packages')
    if re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}', values['uv']) is None:
        _fail('pyvenv.cfg must contain a bounded uv release version')
    return values


def inventory(review_path):
    """Read fixed locations only; do not execute an interpreter or import its packages."""
    expected, review_sha = review(review_path)
    _directory(HOST); _directory(ENV)
    python = ENV / 'bin/python'
    _directory(python.parent)
    resolved = python.resolve(strict=True)
    if resolved != SYSTEM_PYTHON:
        _fail('Private environment must use the fixed system interpreter: ' + str(SYSTEM_PYTHON))
    interpreter = _read(resolved, 64_000_000, root_owner=True)
    if os.path.lexists(ENV / 'bin/pyvenv.cfg'):
        _fail('Shadow bin/pyvenv.cfg is not permitted')
    cfg = _read(ENV / 'pyvenv.cfg', 4096)
    _venv_config(cfg)
    purelib = _directory(ENV / 'lib' / f'python{PYTHON_MINOR}' / 'site-packages')
    worker = _read(REPO / 'symblic/linear/worker.py', 1_000_000)
    lock = _read(REPO / 'symblic/linear/z3-requirements.lock', MAX_JSON)
    if _sha(worker) != expected['worker_sha256'] or _sha(lock) != expected['requirements_lock_sha256']:
        _fail('Worker or requirements lock differs from the owner review record')
    package, total, visited = {}, 0, 0
    pending = [(purelib / name, 0) for name in PACKAGE_DIRS]
    while pending:
        directory, depth = pending.pop()
        _directory(directory)
        if depth > 16:
            _fail('Package directory depth exceeds 16')
        with os.scandir(directory) as entries:
            for entry in entries:
                visited += 1
                if visited > MAX_ENTRIES:
                    _fail('Package inventory exceeds its entry bound')
                path = Path(entry.path); info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    _fail('Package symlinks are not permitted')
                if entry.name == '__pycache__' and stat.S_ISDIR(info.st_mode):
                    continue  # The worker deliberately ignores bytecode cache directories.
                if stat.S_ISDIR(info.st_mode):
                    pending.append((path, depth + 1))
                    continue
                if not stat.S_ISREG(info.st_mode) or len(package) >= MAX_FILES or len(str(path)) > 4096:
                    _fail('Package inventory has special files or exceeds its file/path bound')
                raw = _read(path, min(MAX_FILE, MAX_PACKAGE - total))
                total += len(raw)
                package[str(path.relative_to(purelib))] = _sha(raw)
    required = {'z3/__init__.py', 'z3/lib/libz3.so', PACKAGE_DIRS[1] + '/METADATA', PACKAGE_DIRS[1] + '/RECORD'}
    if not required <= package.keys():
        _fail('Required Z3 package payload is missing')
    metadata = _read(purelib / PACKAGE_DIRS[1] / 'METADATA', MAX_JSON).decode('utf-8').split('\n\n', 1)[0].splitlines()
    if [line for line in metadata if line.startswith('Name:')] != ['Name: z3-solver'] or \
            [line for line in metadata if line.startswith('Version:')] != ['Version: ' + PACKAGE_VERSION]:
        _fail('Installed distribution metadata does not match z3-solver==' + PACKAGE_VERSION)
    runtime = {'python': str(python), 'python_sha256': _sha(interpreter), 'worker_sha256': _sha(worker),
               'purelib': str(purelib), 'z3_version': Z3_VERSION, 'package': dict(sorted(package.items()))}
    raw = _canonical(_runtime_shape(runtime))
    return {'version': VERSION, 'status': 'inventory', 'scope': 'recorded_file_identity_only_no_execution',
            'runtime': runtime, 'runtime_sha256': _sha(raw), 'review_sha256': review_sha,
            'requirements_lock_sha256': _sha(lock), 'environment_configuration_sha256': _sha(cfg),
            'package_files': len(package), 'package_bytes': total}


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    primary = None
    try:
        os.fsync(fd)
    except BaseException as error:
        primary = error
        raise
    finally:
        _cleanup(lambda: os.close(fd), primary)


def _publish_file(path, raw, *, replace=False):
    fd, temporary = tempfile.mkstemp(prefix='.runtime-', dir=path.parent)
    primary = None
    try:
        inner = None
        try:
            pending = memoryview(raw)
            while pending:
                count = os.write(fd, pending)
                if count <= 0:
                    raise OSError('No write progress')
                pending = pending[count:]
            os.fsync(fd)
        except BaseException as error:
            inner = error
            raise
        finally:
            _cleanup(lambda: os.close(fd), inner)
        if replace:
            os.replace(temporary, path)
            temporary = None
        else:
            os.link(temporary, path, follow_symlinks=False)
        _sync_dir(path.parent)
    except BaseException as error:
        primary = error
        raise
    finally:
        if temporary is not None:
            _cleanup(lambda: os.unlink(temporary), primary)


def _sync_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    primary = None
    try:
        os.fsync(fd)
    except BaseException as error:
        primary = error
        raise
    finally:
        _cleanup(lambda: os.close(fd), primary)


def _history(folder, raw):
    path = folder / ('runtime.' + _sha(raw) + '.json')
    old = _read(path, MAX_JSON, missing=True)
    if old is not None:
        if old != raw:
            _fail('Versioned runtime record already has different bytes')
        _sync_file(path); _sync_dir(folder)
    else:
        _publish_file(path, raw)
    return path.name


def publish(review_path, *, replace_sha256=None):
    """Explicit admin action. No writes occur through inventory or on import."""
    if replace_sha256 is not None and not _hex(replace_sha256):
        _fail('Replacement requires the exact existing runtime SHA-256')
    _directory(HOST)
    fd = os.open(HOST / '.provision.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    primary = None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            _fail('Invalid private provisioning lock')
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    _fail('Provisioning lock is busy')
                time.sleep(.01)
        result = inventory(review_path); raw = _canonical(result['runtime'])
        target = HOST / 'runtime.json'; old = _read(target, MAX_JSON, missing=True)
        if old is not None:
            parsed = _json(old)
            if _canonical(_runtime_shape(parsed)) != old:
                _fail('Existing runtime is not an exact canonical runtime record; preserve it for explicit recovery')
            if replace_sha256 is not None and replace_sha256 != _sha(old):
                _fail('Explicit replacement hash differs from the active runtime, even if candidate bytes match')
            if old == raw:
                # Explicit publication also archives a matching manually seeded record.
                history = HOST / 'revisions'
                history.mkdir(mode=0o700, exist_ok=True); _directory(history); _sync_dir(HOST)
                version = _history(history, raw)
                _sync_file(target); _sync_dir(HOST)
                return {**result, 'status': 'unchanged', 'previous_sha256': _sha(old),
                        'versioned_records': [version]}
            if replace_sha256 != _sha(old):
                _fail('Different runtime already exists; replacement requires --replace-sha256 of its exact bytes')
        elif replace_sha256 is not None:
            _fail('Cannot replace an absent runtime')
        history = HOST / 'revisions'
        history.mkdir(mode=0o700, exist_ok=True); _directory(history); _sync_dir(HOST)
        versions = []
        if old is not None:
            versions.append(_history(history, old))
        versions.append(_history(history, raw))
        if _read(target, MAX_JSON, missing=True) != old:
            _fail('Active runtime changed before publication')
        _publish_file(target, raw, replace=old is not None)
        return {**result, 'status': 'published', 'previous_sha256': _sha(old) if old is not None else None,
                'versioned_records': versions}
    except BaseException as error:
        primary = error
        raise
    finally:
        _cleanup(lambda: os.close(fd), primary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inventory', 'publish'))
    parser.add_argument('review', type=Path, help='owner review JSON naming worker/requirements hashes and package version')
    parser.add_argument('--replace-sha256', help='publish only: deliberate exact-current-hash replacement, preserving history')
    args = parser.parse_args(argv)
    try:
        if args.command == 'inventory' and args.replace_sha256 is not None:
            _fail('Inventory never replaces runtime records')
        result = inventory(args.review) if args.command == 'inventory' else publish(args.review, replace_sha256=args.replace_sha256)
        print(json.dumps({'ok': True, **result}, sort_keys=True))
        return 0
    except (ProvisionError, OSError, UnicodeError, RecursionError) as error:
        print(json.dumps({'ok': False, 'error': {'kind': 'provision', 'message': str(error)}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
