#!/usr/bin/env python3
"""HOST-ONLY: indexes Symblic documents into the original host's reading app; needs that app's modules and store.

What it did: walked the documentation folder, the master book and the operator's local run reports, split each
document into passages, registered them in the host's reading app (its library database and passage corpus)
and pinned the master book in the operator's reading profile. The reading app (`host_reader`,
`host_reader_store`) and the store helpers (`host_apps`) are host modules that are not part of this
repository. The original also indexed private agent notes; those sources were removed from this copy.
"""

import os
import re
import sys
import time
import glob
import sqlite3
import json

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # the repository
sys.path.insert(0, HERE)

import host_reader as bf            # the host's reading app (not part of this repository)
import host_reader_store as bs      # its passage store
import host_apps                    # the host's store helpers (save_json, store_lock)

MASTER_BOOK_PATH = os.path.join(HERE, 'SYMBLIC_ULTIMATE_MASTER_BOOK.md')
DOCS_DIR = os.path.join(HERE, 'docs')
LIB_DB = bf._db_path()

def clean_title(path: str, text: str) -> str:
    # Look for first markdown heading
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('# '):
            t = line[2:].strip()
            # Clean formatting
            t = re.sub(r'[*_`]', '', t)
            if t:
                return t[:120]
    base = os.path.splitext(os.path.basename(path))[0]
    return base.replace('-', ' ').replace('_', ' ').title()[:120]

def collect_symblic_files():
    candidates = []
    
    # 1. Master book
    if os.path.isfile(MASTER_BOOK_PATH):
        candidates.append(MASTER_BOOK_PATH)

    # 2. the docs/ tree
    if os.path.isdir(DOCS_DIR):
        for root, _, filenames in os.walk(DOCS_DIR):
            for fn in sorted(filenames):
                candidates.append(os.path.join(root, fn))

    # 3. local run reports and findings under ~/.local/state
    state_patterns = [
        os.path.expanduser('~/.local/state/**/*symblic*'),
        os.path.expanduser('~/.local/state/*pilot*/**/*'),
        os.path.expanduser('~/.local/state/**/*findings*'),
    ]
    for p in state_patterns:
        candidates.extend(glob.glob(p, recursive=True))

    valid_files = set()
    for f in candidates:
        if not os.path.isfile(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.md', '.symd', '.sym', '.txt', '.json'):
            # Filter out giant raw caches, virtual environments, node_modules or binary archives
            if any(skip in f for skip in ('.git', '__pycache__', '.venv', 'node_modules', '.tar.gz')):
                continue
            valid_files.add(os.path.realpath(f))

    return sorted(list(valid_files))

def main():
    print(f"Master book path: {MASTER_BOOK_PATH}")
    files = collect_symblic_files()
    print(f"Discovered {len(files)} total Symblic documents in the repository and ~/.local/state.")

    # 1. Update the reading app's library database
    os.makedirs(os.path.dirname(LIB_DB), exist_ok=True)
    db = sqlite3.connect(LIB_DB)
    now = time.time()
    now_ns = time.time_ns()

    all_books_index = bs.books()
    all_passages = []
    have_pids = {p.get('id') for p in bs.corpus()}

    master_bkey = None
    master_info = None

    for path in files:
        rel_path = os.path.relpath(path, HERE) if path.startswith(HERE) else path
        ext = os.path.splitext(path)[1].lower()
        try:
            size = os.path.getsize(path)
        except OSError:
            continue

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except Exception:
            continue

        if len(text.strip()) < 30:
            continue

        is_master = (os.path.realpath(path) == os.path.realpath(MASTER_BOOK_PATH))
        
        if is_master:
            title = "The Definitive Symblic Compendium: Master Book"
            author = "The operator & coding agents"
        else:
            title = clean_title(path, text)
            author = "The operator & coding agents"

        bkey = bf.book_key(path)

        # Update the library row
        db.execute('''
            INSERT OR REPLACE INTO books (
                path, title, author, ext, kind, mime, size, mtime_ns, modified_at,
                cover_path, cover_ref, meta_json, scan_id, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            path, title, author, ext, 'document', 'text/markdown' if ext == '.md' else 'text/plain',
            size, now_ns, now, None, None, json.dumps({'topic': 'symblic', 'rel': rel_path, 'master': is_master}), 'symblic-index', now
        ))

        # Chunk the text
        info = bf._chunks_for(bkey, text)
        chunks = info['chunks']
        words = info['words']

        # Register in the reading app's books
        all_books_index[bkey] = [
            path, title, author, ext, words, len(chunks)
        ]

        if is_master:
            master_bkey = bkey
            master_info = {
                'bkey': bkey,
                'path': path,
                'title': title,
                'author': author,
                'ext': ext,
                'words': words,
                'chunks': len(chunks),
                'text': text
            }

        # Extract passages
        step = max(1, len(chunks) // 10) if len(chunks) > 10 else 1
        for ci in range(0, len(chunks), step):
            off, ln, w = chunks[ci]
            disp = bf.chunk_display(text[off:off + ln])
            if not disp or len(disp) < 40:
                continue
            pid = f"{bkey}-{off:x}"
            if pid in have_pids:
                continue
            have_pids.add(pid)
            all_passages.append({
                'id': pid,
                'book': bkey,
                'path': path,
                'title': title,
                'author': author,
                'ext': ext,
                'offset': off,
                'ci': ci,
                'pct': round(100.0 * off / max(1, len(text)), 1),
                'text': disp,
                'base': 0.95 if is_master else 0.85,
                'keys': ['symblic', 'neuro-symbolic', 'compendium', ext.replace('.', '')]
            })

    db.commit()
    db.close()

    # Save the books index in the reading app's store
    bs.save_books(all_books_index)
    print(f"Updated the books registry: {len(all_books_index)} total books.")

    # Append passages to corpus.sqlite3
    if all_passages:
        added = bs.append_passages(all_passages, cap=60000)
        print(f"Added {added} new Symblic passages to the corpus (total queued: {len(all_passages)}).")
    else:
        print("All Symblic passages already present in the corpus.")

    # 2. Star the Master Book in the reading profile(s)
    if master_bkey and master_info:
        print(f"Starring Master Book '{master_info['title']}' (key: {master_bkey}) in the reading profiles...")
        profiles = ['operator']          # the host's reading profiles
        for prof in profiles:
            p_path = bf._pstate_path(prof)
            with host_apps.store_lock(p_path):
                st = bf._load_pstate(prof)
                
                # Add/Update in shelf with status 'saved' (which makes it starred)
                sh = st['shelf'].setdefault(master_bkey, {})
                sh.update({
                    'st': 'saved',
                    'i': 0,
                    'pct': 0.0,
                    'ts': int(time.time()),
                    'title': master_info['title'],
                    'author': master_info['author'],
                    'ext': master_info['ext'],
                    'n': master_info['chunks'],
                    'words': master_info['words']
                })

                # Add a premier starred quote at the front of saved passages
                master_passage_text = (
                    "THE DEFINITIVE SYMBLIC COMPENDIUM — An exhaustive, unified masterwork documenting "
                    "the complete history, mathematical foundations, architecture, empirical benchmarks, "
                    "adversarial critiques, and unapplied horizons of the Symblic neuro-symbolic ecosystem. "
                    "Integrates the reality principle: sound discrete algebra, zero floating-point drift, "
                    "and deterministic small-model compilation."
                )
                passage_id = f"{master_bkey}-star"
                
                # Deduplicate if already present
                st['saved'] = [s for s in st['saved'] if s.get('id') != passage_id]
                st['saved'].insert(0, {
                    'id': passage_id,
                    'title': master_info['title'],
                    'author': master_info['author'],
                    'text': master_passage_text,
                    'ts': time.time()
                })
                
                host_apps.save_json(p_path, st)
                print(f"  -> Profile '{prof}': Master Book successfully starred and saved passage pinned.")

    print("\nAll Symblic documents indexed and the Master Book starred.")
    return 0

if __name__ == '__main__':
    sys.exit(main())
