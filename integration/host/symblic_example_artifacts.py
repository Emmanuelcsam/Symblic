"""HOST-ONLY: explicit checked example downloads under the original host's owner-only Symblic API.

Why it is host-only: it answers through the host's HTTP handler and reads a source-controlled manifest
(docs/symblic/examples/artifacts.json) under the host's path layout. The same manifest is shipped as
examples/artifacts.json, with hashes of this repository's files; the examples themselves are in examples/ of
this repository; open them directly.


No directory listing, arbitrary docs path, execution, model call or mutable store.
The source-controlled manifest pins each downloadable byte sequence.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlencode
import zipfile

ROOT = Path(__file__).resolve().parent
MAX_FILE = 8 * 1024 * 1024
MAX_BUNDLE = 32 * 1024 * 1024
MAX_MANIFEST = 256 * 1024
API = '/api/automation/symblic/examples/'
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,79}\Z')
LEAF = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')
TEXT_SUFFIXES = {'.sym', '.js', '.json', '.md', '.txt', '.py', '.html', '.svg', '.csv', '.css'}


class ArtifactError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _read(relative, limit):
    """Walk fixed repository components by fd; refuse symlinks and special files."""
    parts = ['docs', 'symblic', 'examples', *relative.split('/')]
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(source, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ArtifactError('The declared example file is not a bounded regular file.', 409)
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise ArtifactError('The declared example file exceeds its size limit.', 409)
        return data
    finally:
        os.close(fd)


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate manifest field')
        out[key] = value
    return out


def _manifest():
    try:
        raw = json.loads(_read('artifacts.json', MAX_MANIFEST), object_pairs_hook=_unique_object)
        if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1:
            raise ValueError('manifest version')
        bundles = raw['bundles']
        if not isinstance(bundles, list) or len(bundles) > 32:
            raise ValueError('bundle count')
        seen = set()
        for bundle in bundles:
            bid = bundle['id']
            if not isinstance(bid, str) or not ID.fullmatch(bid) or bid in seen:
                raise ValueError('bundle identity')
            seen.add(bid)
            title = bundle['title']
            if not isinstance(title, str) or not 1 <= len(title) <= 160 or any(ord(c) < 32 for c in title):
                raise ValueError('bundle title')
            examples = bundle['examples']
            if not isinstance(examples, list) or len(examples) > 32 or any(not isinstance(e, str) or not ID.fullmatch(e) for e in examples):
                raise ValueError('example ids')
            files = bundle['files']
            if not isinstance(files, list) or not 1 <= len(files) <= 64:
                raise ValueError('file count')
            names, total = set(), 0
            for entry in files:
                name, path, digest, size = (entry[k] for k in ('name', 'path', 'sha256', 'bytes'))
                if not isinstance(name, str) or not LEAF.fullmatch(name) or name == 'bundle.zip' or name in names:
                    raise ValueError('file name')
                names.add(name)
                # Only this bundle's direct children, or a top-level .sym playback.
                if path != bid + '/' + name and not (path == name and name.endswith('.sym')):
                    raise ValueError('file location')
                if not isinstance(digest, str) or not SHA.fullmatch(digest):
                    raise ValueError('file hash')
                if type(size) is not int or not 0 <= size <= MAX_FILE:
                    raise ValueError('file size')
                total += size
            if total > MAX_BUNDLE:
                raise ValueError('bundle size')
        return bundles
    except (OSError, ValueError, KeyError, TypeError) as from_error:
        raise ArtifactError('Checked example downloads are unavailable: the catalogue needs repair.', 503) from from_error


def _url(bid, name):
    return API + 'artifact?' + urlencode({'id': bid, 'name': name})


def catalogue():
    return {'bundles': [
        {'id': b['id'], 'title': b['title'], 'examples': b['examples'],
         'download_url': _url(b['id'], 'bundle.zip'),
         'files': [{k: f[k] for k in ('name', 'bytes', 'sha256')} | {'url': _url(b['id'], f['name'])}
                   for f in b['files']]}
        for b in _manifest()]}


def _verified(entry):
    try:
        value = _read(entry['path'], MAX_FILE)
    except OSError as exc:
        raise ArtifactError('This declared example file is unavailable.', 409) from exc
    if len(value) != entry['bytes'] or hashlib.sha256(value).hexdigest() != entry['sha256']:
        raise ArtifactError('This example changed after verification; download is paused until its catalogue is updated.', 409)
    return value


def download(bid, name):
    if not isinstance(bid, str) or not ID.fullmatch(bid) or not isinstance(name, str) or not LEAF.fullmatch(name):
        raise ArtifactError('No such example artifact.', 404)
    bundle = next((b for b in _manifest() if b['id'] == bid), None)
    if bundle is None:
        raise ArtifactError('No such example bundle.', 404)
    if name == 'bundle.zip':
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as archive:
            for entry in bundle['files']:
                info = zipfile.ZipInfo(entry['name'], date_time=(2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                archive.writestr(info, _verified(entry))
        return out.getvalue(), bid + '.zip', 'application/zip'
    entry = next((f for f in bundle['files'] if f['name'] == name), None)
    if entry is None:
        raise ArtifactError('No such example artifact.', 404)
    return _verified(entry), name, 'application/octet-stream'


def inspect(args):
    """Read catalogue metadata or a pinned text window; never evaluate artifact text."""
    if not isinstance(args, dict) or set(args) - {'bundle', 'name', 'sha256', 'offset', 'limit'}:
        raise ArtifactError('Unsupported example inspection arguments.')
    bid, name = args.get('bundle'), args.get('name')
    offset, limit = args.get('offset', 0), args.get('limit', 8000)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 12000:
        raise ArtifactError('Use a nonnegative character offset and a limit from 1 to 12000.')
    if 'bundle' not in args:
        if args:
            raise ArtifactError('Select a bundle before selecting a file or text window.')
        return {'bundles': [{k: b[k] for k in ('id', 'title', 'examples')} |
                            {'file_count': len(b['files']), 'download_url': _url(b['id'], 'bundle.zip')}
                            for b in _manifest()]}
    if not isinstance(bid, str) or not ID.fullmatch(bid):
        raise ArtifactError('No such example bundle.', 404)
    bundle = next((b for b in _manifest() if b['id'] == bid), None)
    if bundle is None:
        raise ArtifactError('No such example bundle.', 404)
    if 'name' not in args:
        if set(args) != {'bundle'}:
            raise ArtifactError('Select a file before selecting a hash or text window.')
        return {'id': bid, 'title': bundle['title'], 'examples': bundle['examples'],
                'files': [{k: f[k] for k in ('name', 'bytes', 'sha256')} |
                          {'url': _url(bid, f['name'])} for f in bundle['files']]}
    if not isinstance(name, str) or not LEAF.fullmatch(name):
        raise ArtifactError('No such example artifact.', 404)
    entry = next((f for f in bundle['files'] if f['name'] == name), None)
    if entry is None:
        raise ArtifactError('No such example artifact.', 404)
    if args.get('sha256') != entry['sha256']:
        raise ArtifactError('Select the exact SHA-256 from the bundle catalogue before reading this file.', 409)
    value = _verified(entry)
    metadata = {k: entry[k] for k in ('name', 'bytes', 'sha256')} | {'bundle': bid, 'url': _url(bid, name)}
    if Path(name).suffix.lower() not in TEXT_SUFFIXES:
        return metadata | {'text_available': False, 'reason': 'Binary artifact; use its verified attachment.'}
    try:
        source = value.decode('utf-8')
    except UnicodeDecodeError:
        return metadata | {'text_available': False, 'reason': 'Artifact is not valid UTF-8; use its verified attachment.'}
    if offset > len(source):
        raise ArtifactError('Character offset is beyond the end of this artifact.')
    end = min(len(source), offset + limit)
    return metadata | {'text_available': True, 'text': source[offset:end], 'offset': offset,
                       'characters': len(source), 'next_offset': end if end < len(source) else None,
                       'untrusted': True}


def handle(handler, method, route, data):
    # automation_engine/symblic_engine dispatch occurs behind the owner gate.
    if method != 'GET' or route not in ('examples/artifacts', 'examples/artifact'):
        return False
    try:
        if route == 'examples/artifacts':
            handler.send_json(catalogue(), 200, {'Cache-Control': 'private, no-store'})
        else:
            value, filename, mime = download(handler.get_query_param('id'), handler.get_query_param('name'))
            handler.send_response(200)
            handler.send_header('Content-Type', mime)
            handler.send_header('Content-Length', str(len(value)))
            handler.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
            handler.send_header('Cache-Control', 'private, no-store')
            handler.send_header('X-Content-Type-Options', 'nosniff')
            handler.end_headers()
            handler.wfile.write(value)
    except ArtifactError as exc:
        handler.send_json({'error': str(exc)}, exc.status, {'Cache-Control': 'private, no-store'})
    return True
