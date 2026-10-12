"""HOST-ONLY: the owner-only route that served the Academy's source documents on the original host.

Why it is host-only: `handle` answers through the host's HTTP handler and owner check, which are not part of this
repository. The catalog it reads, web/academy/symblic-academy-content.js, is in this repository, and
tools/scripts/symblic_refresh_catalog.py keeps its source list current. The Academy page in this repository reads
the documents directly as static files; this route was how the page read them on the host.

`read_source(url)` returns one exact catalog entry's text, never a caller-chosen file. The URL must be a source
listed in the catalog and a normalized repository path under one of the document roots (docs/, examples/,
benchmarks/, kits/) with a public suffix (.md, .sym, .symd, .json); it is read without following symlinks and up
to 1 MiB. The few catalog rows outside those roots (benchmark data under symblic/bench/data/, the grammar
conformance cases and an example program kept as a test fixture) are refused here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
CATALOG = PurePosixPath('web/academy/symblic-academy-content.js')
MARKER = 'window.SymblicAcademyContent = '
DOCUMENT_ROOTS = ('docs', 'examples', 'benchmarks', 'kits')
SUFFIXES = ('.md', '.sym', '.symd', '.json')
MAX_BYTES = 1024 * 1024


def _catalog_sources() -> list:
    raw = (ROOT / CATALOG).read_text(encoding='utf-8')
    start = raw.index(MARKER) + len(MARKER)
    catalog, _ = json.JSONDecoder().raw_decode(raw, start)
    return catalog['sources']


def read_source(url: str) -> dict:
    """Read an exact catalog entry, never a caller-selected arbitrary file."""
    entry = next((s for s in _catalog_sources() if s.get('url') == url), None)
    relative = PurePosixPath(url.removeprefix('/'))
    if (not entry or not url.startswith('/') or not relative.parts or relative.parts[0] not in DOCUMENT_ROOTS
            or '..' in relative.parts or str(relative) != url[1:]
            or any(part.startswith('.') for part in relative.parts)
            or relative.suffix not in SUFFIXES):
        raise ValueError('Source is not in the Academy reading catalog')
    path = ROOT
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Linked files are not available through the Academy reader')
    if not path.resolve().is_relative_to(ROOT / relative.parts[0]):
        raise ValueError('Source is outside the Academy reading catalog')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Source exceeds the Academy reader size limit')
    digest = hashlib.sha256(data).hexdigest()
    return {'title': entry['title'], 'path': url, 'text': data.decode('utf-8'),
            'sha256': digest, 'changed_since_index': digest != entry.get('sha256')}


def handle(handler, method: str) -> bool:
    # The automation prefix also checks ownership; direct calls fail closed.
    if not handler.identity().is_owner:
        handler.send_json({'error': 'Owner access required'}, status=403)
    elif method != 'GET':
        handler.send_json({'error': 'Read-only source endpoint'}, status=405)
    else:
        try:
            result = read_source(handler.get_query_param('path') or '')
        except (ValueError, OSError):
            handler.send_json({'error': 'This source is unavailable in the Academy reading catalog'}, status=404)
        else:
            handler.send_json(result)
    return True
