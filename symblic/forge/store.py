"""Forge store: transactional SQLite persistence for Forge projects, history, artifacts and model jobs.

What it is for
    Store(root) keeps everything in ROOT/forge.sqlite3 (WAL journal, FULL synchronization, private 0700
    folder; a symlinked root or database is refused). create() makes a project; mutate(project_id, revision,
    action, payload, request_id) applies one symblic.forge.core transition under a revision compare-and-swap
    and records it in an append-only event table; repeating the same request_id returns the recorded result
    instead of applying it twice. undo and redo are new events, never deletions. The store also keeps artifact
    bytes, HTTP-level intents and outcomes (api_begin / api_finish), and model jobs (reserve_job, job,
    update_job) for symblic.forge.models.

    The default root is $SYMBLIC_FORGE_DATA, else $XDG_DATA_HOME/symblic/forge (normally
    ~/.local/share/symblic/forge); see default_root(). Nothing is created until the first write.

Depends on: the standard library (sqlite3) and symblic.forge.core (imported when used). Used by: the other
symblic.forge modules and the original host's Forge routes. Status: prototype; tested with temporary folders
(tests/forge). Integrity comes from transactions and hashes; there is no access control here.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid


class StoreError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', value):
        raise StoreError('Invalid persistent identifier.')
    return value


def expected(value):
    if type(value) is not int or value < 0:
        raise StoreError('Send the project revision displayed in this tab.')
    return value


def default_root():
    """Where projects live when no root is given: $SYMBLIC_FORGE_DATA, else $XDG_DATA_HOME/symblic/forge
    (normally ~/.local/share/symblic/forge). Nothing is created until the first write."""
    if os.environ.get('SYMBLIC_FORGE_DATA'):
        return Path(os.environ['SYMBLIC_FORGE_DATA'])
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'symblic' / 'forge'


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else default_root()

    @contextmanager
    def connection(self, write=False):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise StoreError('Forge storage may not be a symlink.', 503)
        path = self.root / 'forge.sqlite3'
        if path.is_symlink():
            raise StoreError('Forge database may not be a symlink.', 503)
        db = sqlite3.connect(path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            os.chmod(path, 0o600)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, undo TEXT NOT NULL, redo TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL, at REAL NOT NULL,
                    action TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL, document TEXT NOT NULL,
                    PRIMARY KEY(project_id, revision), FOREIGN KEY(project_id) REFERENCES projects(id));
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, request_revision INTEGER NOT NULL,
                    status TEXT NOT NULL, document TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id));
                CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project_id, created);
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    document TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id));
                CREATE TABLE IF NOT EXISTS http_requests (
                    id TEXT PRIMARY KEY, digest TEXT NOT NULL, outcome TEXT, created REAL NOT NULL);
            ''')
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _row(db, project_id):
        row = db.execute('SELECT * FROM projects WHERE id=?', (identifier(project_id),)).fetchone()
        if row is None:
            raise StoreError('Project not found.', 404)
        return row

    @staticmethod
    def _replay(db, request_id, request):
        identifier(request_id)
        row = db.execute('SELECT digest,result FROM requests WHERE id=?', (request_id,)).fetchone()
        if row is not None:
            if row['digest'] != digest(request):
                raise StoreError('That action identity already belongs to different content.', 409)
            return json.loads(row['result'])
        return None

    @staticmethod
    def _receipt(db, request_id, request, result):
        db.execute('INSERT INTO requests VALUES (?,?,?,?)',
                   (request_id, digest(request), encode(result), time.time()))
        return result

    @staticmethod
    def _check_revision(row, revision):
        if row['revision'] != expected(revision):
            raise StoreError('This project changed in another operation. Reload its current revision.', 409)

    @staticmethod
    def _event(db, project, action, actor, payload):
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',
                   (project['id'], project['revision'], time.time(), action, actor,
                    encode(payload), encode(project)))

    def create(self, idea, title, template, request_id, *, actor='operator', manifest=None, demonstration=False):
        from symblic.forge import core as C
        request = {'operation': 'create', 'idea': idea, 'title': title,
                   'template': template, 'manifest': manifest, 'demonstration': demonstration}
        with self.connection(True) as db:
            replay = self._replay(db, request_id, request)
            if replay is not None:
                return replay
            project_id = 'forge-' + uuid.uuid4().hex
            project = (C.snake_demo(project_id=project_id) if demonstration else
                       C.import_manifest(manifest) if manifest is not None else
                       C.new_project(idea, title, template, project_id=project_id))
            identifier(project['id'])
            if db.execute('SELECT id FROM projects WHERE id=?', (project['id'],)).fetchone():
                raise StoreError('This project identity already exists. Open it or import into a separate store.', 409)
            now = time.time()
            # Imported revision is retained, including its immutable source references.
            db.execute('INSERT INTO projects VALUES (?,?,?,?,?,?,?)',
                       (project['id'], project['revision'], encode(project), now, now, '[]', '[]'))
            self._event(db, project, 'project.import' if manifest is not None else 'project.create', actor,
                        {'original_idea': project['original_idea'], 'template': template})
            return self._receipt(db, request_id, request, project)

    def get(self, project_id):
        with self.connection() as db:
            return json.loads(self._row(db, project_id)['document'])

    def listing(self):
        with self.connection() as db:
            out = []
            for row in db.execute('SELECT document,updated FROM projects ORDER BY updated DESC'):
                p = json.loads(row['document'])
                out.append({'id': p['id'], 'title': p['title'], 'revision': p['revision'],
                            'active_branch': p['active_branch'], 'updated_at': row['updated']})
            return out

    def mutate(self, project_id, revision, action, payload, request_id, *, actor='operator', trusted=False,
               artifacts=None):
        from symblic.forge import core as C
        request = {'operation': 'mutation', 'id': project_id, 'revision': revision,
                   'action': action, 'payload': payload, 'trusted': trusted, 'artifacts': artifacts}
        with self.connection(True) as db:
            replay = self._replay(db, request_id, request)
            if replay is not None:
                return replay
            row = self._row(db, project_id)
            self._check_revision(row, revision)
            old = json.loads(row['document'])
            undo, redo = json.loads(row['undo']), json.loads(row['redo'])
            if action in ('undo', 'redo'):
                from_stack, to_stack = (undo, redo) if action == 'undo' else (redo, undo)
                if not from_stack:
                    raise StoreError(f'No {action} transition is available.')
                target = from_stack.pop()
                saved = db.execute('SELECT document FROM events WHERE project_id=? AND revision=?',
                                   (project_id, target)).fetchone()
                if saved is None:
                    raise StoreError('History is incomplete; refusing to invent the missing state.', 409)
                to_stack.append(revision)
                project = json.loads(saved['document'])
                project['revision'] = revision + 1
                # Handoffs remain immutable historical records even across undo.
                prior_handoffs = {h['id']: h for h in old.get('handoffs', [])}
                prior_handoffs.update({h['id']: h for h in project.get('handoffs', [])})
                project['handoffs'] = list(prior_handoffs.values())
                C.validate_project(project)
            else:
                project = C.transition(old, action, payload, trusted=trusted)
                if project['revision'] != revision + 1 or project['id'] != project_id:
                    raise StoreError('Invalid engine revision transition.', 500)
                undo.append(revision)
                redo = []
            db.execute('UPDATE projects SET revision=?,document=?,updated=?,undo=?,redo=? WHERE id=?',
                       (project['revision'], encode(project), time.time(), encode(undo), encode(redo), project_id))
            self._event(db, project, action, actor, payload)
            for artifact in artifacts or []:
                if not trusted or artifact.get('source_revision') != revision:
                    raise StoreError('Artifact must be generated by the host against this exact revision.')
                if hashlib.sha256(artifact['text'].encode()).hexdigest() != artifact['sha256']:
                    raise StoreError('Artifact hash does not match its retained bytes.')
                db.execute('INSERT INTO artifacts VALUES (?,?,?,?)',
                           (identifier(artifact['id']), project_id, revision, encode(artifact)))
            return self._receipt(db, request_id, request, project)

    def artifact(self, artifact_id):
        with self.connection() as db:
            row = db.execute('SELECT document FROM artifacts WHERE id=?', (identifier(artifact_id),)).fetchone()
            if row is None:
                raise StoreError('Artifact is not retained in this store; an imported reference is not local content.', 404)
            artifact = json.loads(row['document'])
            if (not isinstance(artifact.get('text'), str) or
                    hashlib.sha256(artifact['text'].encode()).hexdigest() != artifact.get('sha256')):
                raise StoreError('Retained artifact bytes do not match their recorded hash; download refused.', 409)
            if artifact.get('encoding') == 'base64':
                import base64
                try:
                    content = base64.b64decode(artifact['text'], validate=True)
                except ValueError as exc:
                    raise StoreError('Retained attachment bytes are malformed.', 409) from exc
                if (hashlib.sha256(content).hexdigest() != artifact.get('content_sha256') or
                        len(content) != artifact.get('size')):
                    raise StoreError('Retained attachment differs from its original content hash or size.', 409)
            return artifact

    def request(self, request_id):
        with self.connection() as db:
            row = db.execute('SELECT result FROM requests WHERE id=?', (identifier(request_id),)).fetchone()
            http = db.execute('SELECT outcome FROM http_requests WHERE id=?', (request_id,)).fetchone()
            outcome = json.loads(http['outcome']) if http and http['outcome'] else None
            return {'found': row is not None, 'result': json.loads(row['result']) if row else None,
                    'state': 'confirmed' if row else 'failed' if outcome and 'failure' in outcome else
                             'confirmed' if outcome else 'pending' if http else 'missing',
                    'outcome': outcome}

    def api_begin(self, request_id, envelope):
        with self.connection(True) as db:
            identifier(request_id)
            row = db.execute('SELECT * FROM http_requests WHERE id=?', (request_id,)).fetchone()
            if row:
                if row['digest'] != digest(envelope):
                    raise StoreError('This action identity belongs to different submitted content.', 409)
                return False, json.loads(row['outcome']) if row['outcome'] else None
            db.execute('INSERT INTO http_requests VALUES (?,?,NULL,?)', (request_id, digest(envelope), time.time()))
            return True, None

    def api_finish(self, request_id, outcome):
        with self.connection(True) as db:
            db.execute('UPDATE http_requests SET outcome=? WHERE id=? AND outcome IS NULL',
                       (encode(outcome), identifier(request_id)))

    def history(self, project_id, *, before=None, limit=100):
        limit = max(1, min(500, int(limit)))
        with self.connection() as db:
            self._row(db, project_id)
            rows = db.execute('SELECT revision,at,action,actor,payload FROM events '
                              'WHERE project_id=? AND revision<? ORDER BY revision DESC LIMIT ?',
                              (project_id, int(before) if before is not None else 2**63-1, limit)).fetchall()
            return [dict(row) | {'payload': json.loads(row['payload'])} for row in rows]

    def reserve_job(self, project_id, revision, request, request_id):
        envelope = {'operation': 'model', 'id': project_id, 'revision': revision, 'request': request}
        with self.connection(True) as db:
            replay = self._replay(db, request_id, envelope)
            if replay is not None:
                return replay, False
            row = self._row(db, project_id)
            self._check_revision(row, revision)
            count = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','unknown')").fetchone()[0]
            if count >= 3:
                raise StoreError('Three refinement requests are pending. Inspect or resolve them before starting another.', 429)
            now = time.time()
            job = {'id': 'forgejob-' + uuid.uuid4().hex, 'project_id': project_id,
                   'request_revision': revision, 'request': request, 'status': 'queued',
                   'created_at': now, 'updated_at': now, 'outcome': None,
                   'intent': 'A reserved request is never automatically dispatched again.'}
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                       (job['id'], project_id, revision, job['status'], encode(job), now, now))
            return self._receipt(db, request_id, envelope, job), True

    def job(self, job_id):
        with self.connection() as db:
            row = db.execute('SELECT document FROM jobs WHERE id=?', (identifier(job_id),)).fetchone()
            if row is None:
                raise StoreError('Model request not found.', 404)
            return json.loads(row['document'])

    def jobs(self, project_id):
        with self.connection() as db:
            self._row(db, project_id)
            return [json.loads(row['document']) for row in db.execute(
                'SELECT document FROM jobs WHERE project_id=? ORDER BY created DESC LIMIT 100', (project_id,))]

    def update_job(self, job_id, changes, *, only_status=None):
        with self.connection(True) as db:
            row = db.execute('SELECT document FROM jobs WHERE id=?', (identifier(job_id),)).fetchone()
            if row is None:
                raise StoreError('Model request not found.', 404)
            job = json.loads(row['document'])
            if only_status is not None and job['status'] not in only_status:
                raise StoreError('This request already progressed; refusing another dispatch.', 409)
            for key in ('id', 'project_id', 'request_revision', 'request', 'created_at'):
                if key in changes:
                    raise StoreError('Model request identity is immutable.')
            job.update(copy.deepcopy(changes), updated_at=time.time())
            db.execute('UPDATE jobs SET status=?,document=?,updated=? WHERE id=?',
                       (job['status'], encode(job), job['updated_at'], job_id))
            return job
