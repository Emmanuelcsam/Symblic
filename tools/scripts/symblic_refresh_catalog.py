#!/usr/bin/env python3
"""Refresh only the Academy public source list; never rewrite authored curriculum.

Host-only in practice: the Academy was a learning page of the original host system. Its catalog,
ROOT/symblic-academy-content.js (`window.SymblicAcademyContent = {...}`), is not part of this repository, and
its source URLs use the host's path layout (/docs/symblic/NAME). integration/host/symblic_academy_sources.py
served those sources to the page. The script is kept with its tests (tests/tools/) as a worked example of
refreshing generated metadata without touching authored fields.

    python3 tools/scripts/symblic_refresh_catalog.py --root ROOT [--check]

Reads bounded regular files under ROOT/docs/symblic with the reader's public suffixes.
Hashes/title/headings describe source bytes, never scientific validation status.
Existing status, lesson links, descriptions and extra authored fields are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

MARKER = 'window.SymblicAcademyContent = '
SUFFIXES = {'.md', '.sym', '.symd', '.json'}
MAX_BYTES = 1024 * 1024
NEW_STATUS = 'Public source / indexed metadata; validation not inferred'
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


def refresh(root, *, check=False):
    root = Path(root).resolve()
    path = root / 'symblic-academy-content.js'
    if path.is_symlink():
        raise ValueError('Refuse a symlinked Academy catalog')
    raw = path.read_text(encoding='utf-8')
    catalog, begin, end = _catalog(raw)
    public = root / 'docs' / 'symblic'
    if (root / 'docs').is_symlink() or public.is_symlink():
        raise ValueError('Refuse symlinked public documentation roots')
    discovered = {}
    for source in sorted(public.rglob('*')):
        if source.is_symlink():
            raise ValueError('Refuse linked content under the public documentation root')
        if not source.is_file() or source.suffix not in SUFFIXES:
            continue
        with source.open('rb') as handle:
            data = handle.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Public source exceeds Academy reader limit: ' + str(source.relative_to(root)))
        relative = source.relative_to(root)
        discovered['/' + relative.as_posix()] = (_metadata(source, data), relative)
    rows, seen, added, changed = [], set(), [], []
    for old in catalog['sources']:
        url = old.get('url')
        if not isinstance(url, str) or url in seen:
            raise ValueError('Invalid or repeated source URL')
        seen.add(url)
        row = dict(old)
        if url.startswith('/docs/symblic/'):
            if url not in discovered:
                raise ValueError('An authored source link no longer resolves: ' + url)
            meta, relative = discovered[url]
            row.update(meta)
            row['provenance'] = {'kind': 'public_repository_source', 'path': url,
                                 'sha256': meta['sha256'], 'indexer': 'tools/scripts/symblic_refresh_catalog.py',
                                 'scope': 'source metadata only; lesson links and status do not certify coverage or validity'}
        if row != old:
            changed.append(url)
        rows.append(row)
    for url, (meta, relative) in discovered.items():
        if url in seen:
            continue
        rows.append({**meta, 'url': url, 'status': NEW_STATUS,
                     'description': DESCRIPTIONS.get(relative.name, 'Public repository source; inspect its stated assumptions, version and evidence limits.'),
                     'lessons': _lessons(catalog['levels'], relative),
                     'provenance': {'kind': 'public_repository_source', 'path': url,
                                    'sha256': meta['sha256'], 'indexer': 'tools/scripts/symblic_refresh_catalog.py',
                                    'scope': 'source metadata only; lesson links and status do not certify coverage or validity'}})
        added.append(url)
    replacement = json.dumps(rows, ensure_ascii=False, indent=2).replace('\n', '\n  ')
    updated = raw[:begin] + replacement + raw[end:]
    stale = updated != raw
    if stale and not check:
        # Preserve the original mode and every byte outside the sources value.
        fd, name = tempfile.mkstemp(prefix='.symblic-catalog-', suffix='.tmp', dir=root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                os.fchmod(handle.fileno(), path.stat().st_mode & 0o777)
                handle.write(updated)
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {'stale': stale, 'added': added, 'updated': changed, 'public_sources': len(discovered),
            'catalog_sources': len(rows), 'written': stale and not check}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--check', action='store_true', help='Read only; exit 1 when a refresh is needed')
    args = parser.parse_args(argv)
    try:
        result = refresh(args.root, check=args.check)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))
    return int(args.check and result['stale'])


if __name__ == '__main__':
    raise SystemExit(main())
