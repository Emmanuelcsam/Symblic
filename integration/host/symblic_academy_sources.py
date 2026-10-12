"""HOST-ONLY: the owner-only reader behind the original host's Academy page; needs that page's catalog file.

Why it is host-only: it reads ROOT/symblic-academy-content.js (the catalog of the host's Academy learning page,
not part of this repository; tools/scripts/symblic_refresh_catalog.py maintained it) and answers through the
host's HTTP handler and owner check. It returns one exact catalog entry's text, never a caller-chosen file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 1024 * 1024


def read_source(url: str) -> dict:
    """Read an exact catalog entry, never a caller-selected arbitrary file."""
    raw = (ROOT / 'symblic-academy-content.js').read_text(encoding='utf-8')
    catalog = json.loads(raw.split('window.SymblicAcademyContent = ', 1)[1].rstrip(';\n'))
    entry = next((s for s in catalog['sources'] if s['url'] == url), None)
    relative = PurePosixPath(url.removeprefix('/'))
    if (not entry or not url.startswith('/docs/symblic/')
            or '..' in relative.parts or str(relative) != url[1:]
            or relative.suffix not in ('.md', '.sym', '.symd', '.json')):
        raise ValueError('Source is not in the Academy reading catalog')
    path = ROOT
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Linked files are not available through the Academy reader')
    if not path.resolve().is_relative_to(ROOT / 'docs' / 'symblic'):
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
