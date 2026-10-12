"""Forge health check: a read-only summary of the Forge store for a status page.

check() opens the store's SQLite file read-only and reports how many projects exist and how many model requests
are in the 'unknown' state (they need an explicit decision; nothing replays them). It never launches a provider
and never repairs the ledger. checks() and COVERS are the shape the original host's status page expected
(COVERS names the host module whose health this describes).

Depends on: the standard library and symblic.forge.store. Used by: the original host's status page only.
Status: small and untested here.
"""
from pathlib import Path
import sqlite3

COVERS = ['symblic_forge']


def check():
    from symblic.forge.store import Store
    path = Store().root / 'forge.sqlite3'
    if not path.exists():
        return {'level': 'ok', 'detail': 'Forge is ready; no projects have been created'}
    if path.is_symlink() or path.parent.is_symlink():
        return {'level': 'warn', 'detail': 'Forge ledger path is a symlink; requests will be refused'}
    try:
        with sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=2) as db:
            pending = db.execute("SELECT count(*) FROM jobs WHERE status='unknown'").fetchone()[0]
            count = db.execute('SELECT count(*) FROM projects').fetchone()[0]
        return {'level': 'warn' if pending else 'ok',
                'detail': f'{count} saved Forge projects; {pending} model requests need explicit recovery'}
    except (OSError, sqlite3.Error):
        return {'level': 'warn', 'detail': 'Forge ledger could not be read; no automatic replacement attempted'}


def checks():
    return [{'id': 'symblic-forge.store', 'label': 'Symblic Forge', 'run': check}]
