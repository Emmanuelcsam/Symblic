"""Intent store: one private, atomically replaced JSON record per interpreter session.

What it is for
    The host's interpreter kept each intent session (the intent state from symblic.intent.records, its full
    revision history, its jobs, handoffs and model-call budget) in one folder under a root you choose:
    make(root, state, limit) creates it; load(folder) and save(folder, row) read and atomically replace
    record.json (temporary file, fsync, rename, directory fsync) with an integrity hash; locked(folder) is a
    per-folder flock plus an in-process lock. reserve(folder, job_id, app, ...) spends one call of the session's
    budget before every model call: a failed or uncertain call stays spent, and repeated attempts on the same
    content revision draw on a separate, smaller repair allowance. load() never turns a failed read into an
    empty session, and encode() refuses non-finite JSON and records over 8 MB.

Depends on: the standard library (fcntl). Used by: the original host's interpreter API
(integration/host/symblic_intent_api.py). It needs no host itself. Status: prototype; unit tests in
tests/intent/test_symblic_intent_store.py, more through the host API's tests (which skip without the host).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ID_RX = re.compile(r'^[0-9a-f]{12}$')
MAX_BYTES = 8_000_000
_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()


class StoreError(ValueError):
    pass


def identifier(value):
    if not isinstance(value, str) or not ID_RX.fullmatch(value):
        raise StoreError('No such interpreter session.')
    return value


def encode(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                         allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise StoreError('The interpreter record is not finite JSON.') from exc
    if len(raw) > MAX_BYTES:
        raise StoreError('This interpreter session has reached its storage limit; export it and start another.')
    return raw


def sha(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def locked(folder):
    folder = Path(folder)
    key = str(folder.resolve())
    with _GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        fd = os.open(folder / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def load(folder):
    path = Path(folder) / 'record.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('oversize')
        row = json.loads(raw, parse_constant=lambda _s: (_ for _ in ()).throw(ValueError('nonfinite')))
        if not isinstance(row, dict) or row.get('store_version') != 1:
            raise TypeError('version')
        for key in ('state', 'budget', 'jobs', 'history', 'handoffs'):
            if key not in row:
                raise ValueError('incomplete')
        if not isinstance(row['state'], dict) or not isinstance(row['budget'], dict):
            raise TypeError('shape')
        if any(not isinstance(row[k], list) for k in ('jobs', 'history', 'handoffs')):
            raise ValueError('shape')
        budget = row['budget']
        if any(type(budget.get(k)) is not int or budget[k] < 0 for k in ('limit', 'used', 'repair_limit')):
            raise ValueError('budget')
        if not isinstance(budget.get('reservations'), list) or budget['used'] != len(budget['reservations']):
            raise ValueError('reservations')
        if row.get('integrity') != sha({k: v for k, v in row.items() if k != 'integrity'}):
            raise ValueError('integrity')
        return row
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise StoreError('This interpreter record is unreadable or damaged; no job or action was started.') from exc


def save(folder, row):
    """Caller holds locked(folder). Integrity detects damage, not malicious signing."""
    row = {k: v for k, v in row.items() if k != 'integrity'}
    row['integrity'] = sha(row)
    raw = encode(row)
    folder = Path(folder)
    temporary = folder / ('.record-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, folder / 'record.json')
        _fsync_dir(folder)
    finally:
        temporary.unlink(missing_ok=True)


def make(root, state, limit, create_key='', repairs=0):
    root, ident = Path(root), identifier(state['id'])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = root / ident
    with locked(root):
        if folder.exists():
            with locked(folder):
                old = load(folder)
            if create_key and old.get('create_key') == create_key:
                return old
            raise StoreError('The session identity is already in use.')
        folder.mkdir(mode=0o700)
        _fsync_dir(root)
        row = {'store_version': 1, 'state': state, 'created': time.time(), 'updated': time.time(),
               'create_key': create_key, 'budget': {'limit': limit, 'used': 0, 'repair_limit': repairs, 'reservations': []},
               'jobs': [], 'history': [state], 'handoffs': [], 'artifact': None}
        with locked(folder):
            save(folder, row)
        return row


def replace_state(row, state):
    row['state'] = state
    row['history'].append(state)
    row['updated'] = time.time()


def reserve(folder, job_id, app, current_limit, current_repairs):
    """An uncertain/failed dispatch still consumes its reserved call."""
    with locked(folder):
        row = load(folder)
        job = next((j for j in row['jobs'] if j['id'] == job_id), None)
        if not job or job['status'] != 'running':
            raise StoreError('The interpreter job is no longer active.')
        budget = row['budget']
        budget['limit'] = min(budget['limit'], current_limit)
        budget['repair_limit'] = min(budget['repair_limit'], current_repairs)
        repeated = any(r.get('content_revision') == job['content_revision'] and r.get('kind') == job['kind']
                       for r in budget['reservations'])
        if repeated and sum(r.get('repair') is True for r in budget['reservations']) >= budget['repair_limit']:
            save(folder, row)
            raise StoreError('The shared retry/fallback allowance is exhausted; earlier failed calls remain spent.')
        if budget['used'] >= budget['limit']:
            save(folder, row)
            raise StoreError('The shared interpretation and compilation model-call budget is exhausted.')
        budget['reservations'].append({'job': job_id, 'app': str(app)[:200], 'at': time.time(),
                                       'content_revision': job['content_revision'], 'kind': job['kind'], 'repair': repeated})
        budget['used'] += 1
        job['message'] = 'Requested ' + str(app)[:200] + '; waiting for the admitted model runner (call ' + \
                         str(budget['used']) + ' of ' + str(budget['limit']) + ').'
        save(folder, row)
        return budget['used']
