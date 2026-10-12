#!/usr/bin/env python3
"""Refresh the source list of the Academy catalog; never rewrite the authored curriculum.

The Academy page (web/academy/) teaches from an authored curriculum and lists the repository's documents in its
research map. Both live in one catalog, web/academy/symblic-academy-content.js
(`window.SymblicAcademyContent = {...}`). This script keeps the generated half of the source list in step with
the files and leaves every other byte of the catalog as it is:

- every bounded regular file with a public suffix (.md .sym .symd .json) under the document roots docs/,
  examples/, benchmarks/ and kits/ gets a row; new rows are appended with a status that claims no validation;
- every row whose URL is a repository path ("/docs/reference/SPEC.md") gets its title, headings, SHA-256 and
  provenance rewritten from that file, wherever in the repository it is (a few authored rows point at benchmark
  data under symblic/ or at example programs kept as test fixtures);
- when a row's file is gone (moved or deleted), a generated row that nobody has changed is dropped and listed
  under "removed": its status, description and lessons are the ones this script writes, it has no other fields,
  and no lesson links it, so a refresh loses nothing it would not write again for the file's new path. Any other
  row whose file is gone is an error, never a silent deletion: rename or remove that row, and the lesson links to
  it, by hand first;
- rows with external links (https://...) are kept exactly as written.

    python3 tools/scripts/symblic_refresh_catalog.py [--root ROOT] [--catalog FILE] [--check]

Hashes, titles and headings describe source bytes, never scientific validation status.
Existing status, lesson links, descriptions and extra authored fields are preserved.
Folders whose names start with '.' and cache folders (__pycache__, node_modules) are skipped. A symlink under a
document root, a symlinked root, a symlinked catalog and any path through a symlink are refused.
integration/host/symblic_academy_sources.py is the host-only route that served these documents to the page on
the original host; the page in this repository reads them as static files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

MARKER = 'window.SymblicAcademyContent = '
CATALOG = 'web/academy/symblic-academy-content.js'
DOCUMENT_ROOTS = ('docs', 'examples', 'benchmarks', 'kits')
SUFFIXES = {'.md', '.sym', '.symd', '.json'}
SKIPPED_FOLDERS = {'__pycache__', 'node_modules'}
MAX_BYTES = 1024 * 1024
NEW_STATUS = 'Public source / indexed metadata; validation not inferred'
# The fields of a row this script adds; a row with any other field was edited by hand.
GENERATED_FIELDS = {'title', 'headings', 'sha256', 'url', 'status', 'description', 'lessons', 'provenance'}
INDEXER = 'tools/scripts/symblic_refresh_catalog.py'
SCOPE = 'source metadata only; lesson links and status do not certify coverage or validity'
DEFAULT_DESCRIPTION = 'Public repository source; inspect its stated assumptions, version and evidence limits.'
# Deliberate topic-to-existing-lesson links, not generated claims of lesson coverage.
ASSOCIATIONS = {
    'FINITE-LOGIC.md': ('Facts & Rules', 'What an assertion really establishes'),
    'PROOF-TERMS.md': ('What an assertion really establishes', 'Counterexamples, vacuity and specification gaming'),
    'SOURCE-WITNESSES.md': ('Capstone 1: The Automated Invoice Auditor', 'Evidence strength and evidence security'),
    'QUANTITIES.md': ('Exact fractions and measured uncertainty', 'Operational definitions and boundary cases'),
    'MATCHED-EVALUATION.md': ('The denominator and the unit of independence', 'Agreement, correctness and shared mistakes'),
    'matched-example-v1.json': ('The denominator and the unit of independence',),
    'POLICY-LEARNING.md': ('Deterministic selection and preserving good work', 'The denominator and the unit of independence'),
    'REFORM-3.md': ('Two Brains in Your Computer', 'Your research-to-program capstone'),
    'claims.json': ('Evidence strength and evidence security', 'Novelty, prior art and measured contribution'),
}
DESCRIPTIONS = {
    'FINITE-LOGIC.md': 'Finite-domain expansion and proof-checking boundaries; inspect explicit domains, assumptions and resource limits.',
    'PROOF-TERMS.md': 'Propositional proof-term grammar and checking contract; checked derivations remain conditional on premises.',
    'SOURCE-WITNESSES.md': 'Source revision, span and coverage contracts; a source match does not establish external truth.',
    'QUANTITIES.md': 'Explicit dimensions, intervals and quantity provenance; inspect the supported operations and uncertainty assumptions.',
    'MATCHED-EVALUATION.md': 'Frozen comparison protocol, strict scoring and all-assigned accounting; documentation is not a measured performance result.',
    'matched-example-v1.json': 'Synthetic evaluation manifest with placeholder applicators; not model-run evidence or a capability claim.',
    'POLICY-LEARNING.md': 'Bounded candidate-policy selection and held-out evaluation contracts; source metadata does not show measured improvement.',
    'REFORM-3.md': 'Design and integration record; read its dated component evidence and deployment qualifications.',
    'claims.json': 'Public claim registry; indexing preserves the file without independently verifying its entries.',
}
# Defaults for new rows by folder, used when DESCRIPTIONS has no entry for the file name.
FOLDER_DESCRIPTIONS = {
    'docs/essays': 'Speculative essay an AI model wrote while Symblic was built, kept as a historical record; its claims were not verified (see docs/essays/README.md).',
}


class MissingSource(ValueError):
    """A catalog row names a well-formed repository path whose file is gone."""


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('Duplicate catalog/JSON field: ' + key)
        result[key] = value
    return result


def _catalog(raw):
    """Parse inert JSON and locate the sources value so all other bytes survive."""
    if raw.count(MARKER) != 1:
        raise ValueError('Expected one Academy content assignment')
    start = raw.index(MARKER) + len(MARKER)
    decoder = json.JSONDecoder(object_pairs_hook=_pairs)
    data, _ = decoder.raw_decode(raw, start)
    if not isinstance(data, dict) or not isinstance(data.get('sources'), list) or not isinstance(data.get('levels'), list):
        raise ValueError('Academy content needs sources and authored levels')
    pos = start + 1
    while True:
        while raw[pos].isspace() or raw[pos] == ',':
            pos += 1
        if raw[pos] == '}':
            break
        key, pos = decoder.raw_decode(raw, pos)
        while raw[pos].isspace():
            pos += 1
        if raw[pos] != ':':
            raise ValueError('Malformed Academy field')
        pos += 1
        while raw[pos].isspace():
            pos += 1
        value_start = pos
        _, pos = decoder.raw_decode(raw, pos)
        if key == 'sources':
            return data, value_start, pos
    raise ValueError('Missing sources field')


def _headings(text):
    rows, fence, previous = [], None, ''
    for line in text.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if marker:
            token, tail = marker.groups()
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not tail.strip():
                fence = None
            previous = ''
            continue
        if fence:
            continue
        atx = re.match(r'^ {0,3}(#{1,6})[ \t]+(.+?)\s*$', line)
        if atx:
            title = re.sub(r'\s+#+\s*$', '', atx[2]).strip()
            rows.append((len(atx[1]), title))
        elif previous and re.fullmatch(r' {0,3}(?:=+|-+)\s*', line):
            rows.append((1 if line.strip()[0] == '=' else 2, previous.strip()))
        previous = '' if atx or not line.strip() or line.startswith(('    ', '\t', '>')) else line
    return rows


def _metadata(path, data):
    text = data.decode('utf-8')
    headings = _headings(text) if path.suffix in ('.md', '.symd') else []
    fallback = path.stem.replace('-', ' ').replace('_', ' ')
    title = next((title for depth, title in headings if depth == 1), headings[0][1] if headings else fallback)
    if path.suffix == '.sym':
        match = re.search(r'^\s*program\s+(.+?)\.\s*(?:#.*)?$', text, re.M)
        if match:
            title = match[1].strip().strip('"')
    elif path.suffix == '.json':
        parsed = json.loads(text, object_pairs_hook=_pairs)
        if isinstance(parsed, dict):
            title = next((parsed[key] for key in ('title', 'name')
                          if isinstance(parsed.get(key), str) and parsed[key].strip()), title)
    return {'title': title, 'headings': [title for _, title in headings],
            'sha256': hashlib.sha256(data).hexdigest()}


def _bounded(path, url):
    with path.open('rb') as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Public source exceeds Academy reader limit: ' + url)
    return data


def _document(root, url):
    """The repository file an authored catalog URL names, read without following links."""
    if not isinstance(url, str) or not url.startswith('/'):
        raise ValueError('Catalog source is neither a repository path nor an https link: ' + repr(url))
    relative = PurePosixPath(url[1:])
    if (str(relative) != url[1:] or not relative.parts or relative.suffix not in SUFFIXES
            or any(part.startswith('.') or part in SKIPPED_FOLDERS for part in relative.parts)):
        raise ValueError('Catalog source is not a public repository document: ' + url)
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Refuse linked content named by the catalog: ' + url)
    if not path.is_file():
        raise MissingSource('A catalog source no longer resolves: ' + url)
    return path, _bounded(path, url)


def _discover(root):
    """Every public document under the document roots: {url: (metadata, relative path)}, in path order."""
    found = []
    for name in DOCUMENT_ROOTS:
        top = root / name
        if top.is_symlink():
            raise ValueError('Refuse symlinked public documentation roots')
        if not top.is_dir():
            continue
        for current, folders, files in os.walk(top):
            base = Path(current)
            folders[:] = sorted(f for f in folders if not f.startswith('.') and f not in SKIPPED_FOLDERS)
            for entry in [*folders, *files]:
                if (base / entry).is_symlink():
                    raise ValueError('Refuse linked content under the public documentation root')
            for file in files:
                source = base / file
                if file.startswith('.') or source.suffix not in SUFFIXES or not source.is_file():
                    continue
                relative = source.relative_to(root)
                url = '/' + relative.as_posix()
                found.append((url, source, relative))
    discovered = {}
    for url, source, relative in sorted(found):
        discovered[url] = (_metadata(source, _bounded(source, url)), relative)
    return discovered


def _lessons(levels, path):
    url = '/' + path.as_posix()
    wanted = set(ASSOCIATIONS.get(path.name, ()))
    if 'graph' in path.stem.lower():
        wanted.update(('Small spec units and fresh context', 'Agreement, correctness and shared mistakes'))
    result = []
    for li, level in enumerate(levels):
        for bi, bite in enumerate(level.get('bites', [])):
            if bite['title'] in wanted or any(ref.get('url') == url for ref in bite.get('references', [])):
                result.append({'level': li, 'bite': bi, 'title': bite['title']})
    return result


def _description(path):
    if path.name in DESCRIPTIONS:
        return DESCRIPTIONS[path.name]
    folder = path.parent.as_posix()
    return next((text for prefix, text in FOLDER_DESCRIPTIONS.items()
                 if folder == prefix or folder.startswith(prefix + '/')), DEFAULT_DESCRIPTION)


def _generated(row, levels):
    """True for a row this script added and nobody has changed: dropping it, once its file is gone, loses nothing."""
    url = row['url']
    relative = PurePosixPath(url[1:])
    linked = any(ref.get('url') == url for level in levels for bite in level.get('bites', [])
                 for ref in bite.get('references', []))
    return (not linked and set(row) <= GENERATED_FIELDS and row.get('status') == NEW_STATUS
            and row.get('description') == _description(relative) and row.get('lessons') == _lessons(levels, relative))


def _missing(row):
    """The error for a row whose file is gone and that this script must not drop."""
    url = row['url']
    if row.get('status') == NEW_STATUS:
        kind = ('A generated source row no longer resolves and is not dropped, because a lesson links it or its '
                'fields are not the ones this script writes: ')
    else:
        kind = 'An authored source row no longer resolves: '
    return ValueError(kind + url + '. Rename or remove the row, and any lesson references to it, in ' + CATALOG
                      + ', then run this script again.')


def _provenance(url, meta):
    return {'kind': 'public_repository_source', 'path': url, 'sha256': meta['sha256'],
            'indexer': INDEXER, 'scope': SCOPE}


def refresh(root, *, check=False, catalog=None):
    root = Path(root).resolve()
    path = Path(catalog) if catalog else root / CATALOG
    if path.is_symlink():
        raise ValueError('Refuse a symlinked Academy catalog')
    raw = path.read_text(encoding='utf-8')
    data, begin, end = _catalog(raw)
    discovered = _discover(root)
    rows, seen, added, changed, removed = [], set(), [], [], []
    for old in data['sources']:
        url = old.get('url')
        if not isinstance(url, str) or url in seen:
            raise ValueError('Invalid or repeated source URL')
        seen.add(url)
        row = dict(old)
        if not url.startswith('https://'):
            if url in discovered:
                meta = discovered[url][0]
            else:
                try:
                    source, content = _document(root, url)
                except MissingSource:
                    if not _generated(old, data['levels']):
                        raise _missing(old) from None
                    removed.append(url)
                    continue
                meta = _metadata(source, content)
            row.update(meta)
            row['provenance'] = _provenance(url, meta)
        if row != old:
            changed.append(url)
        rows.append(row)
    for url, (meta, relative) in discovered.items():
        if url in seen:
            continue
        rows.append({**meta, 'url': url, 'status': NEW_STATUS, 'description': _description(relative),
                     'lessons': _lessons(data['levels'], relative), 'provenance': _provenance(url, meta)})
        added.append(url)
    replacement = json.dumps(rows, ensure_ascii=False, indent=2).replace('\n', '\n  ')
    updated = raw[:begin] + replacement + raw[end:]
    stale = updated != raw
    if stale and not check:
        # Preserve the original mode and every byte outside the sources value.
        fd, name = tempfile.mkstemp(prefix='.symblic-catalog-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                os.fchmod(handle.fileno(), path.stat().st_mode & 0o777)
                handle.write(updated)
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {'stale': stale, 'added': added, 'updated': changed, 'removed': removed, 'public_sources': len(discovered),
            'catalog_sources': len(rows), 'written': stale and not check}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2],
                        help='Repository root (default: the checkout this script is in)')
    parser.add_argument('--catalog', type=Path, help='Catalog file (default: ROOT/' + CATALOG + ')')
    parser.add_argument('--check', action='store_true', help='Read only; exit 1 when a refresh is needed')
    args = parser.parse_args(argv)
    try:
        result = refresh(args.root, check=args.check, catalog=args.catalog)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))
    return int(args.check and result['stale'])


if __name__ == '__main__':
    raise SystemExit(main())
