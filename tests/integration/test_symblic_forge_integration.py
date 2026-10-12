"""Static owner/private registration and real online SQLite backup, fully isolated.

HOST-ONLY: every case reads the original host checkout's own files (its web server's private-data and owner
lists in server.py, the app table in host_apps.py, its navigation page and its backup module, and its
maintenance scripts), none of which is part of this repository. The module is skipped unless
SYMBLIC_HOST_CHECKOUT names such a checkout.
"""
import ast
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest

from symblic.forge.store import Store

ROOT = Path(os.environ.get('SYMBLIC_HOST_CHECKOUT') or Path(__file__).resolve().parents[2])
if not (ROOT / 'server.py').is_file():
    raise unittest.SkipTest('host-only test: reads the original host checkout (its server, store, navigation and backup '
                            'modules), which is not part of this repository; set SYMBLIC_HOST_CHECKOUT to run it')
sys.path.insert(0, str(ROOT))


def literal(filename, name):
    for node in ast.walk(ast.parse((ROOT / filename).read_text())):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(name + ' not found')


class ForgeIntegrationTests(unittest.TestCase):
    def test_owner_api_and_private_artifacts_are_registered(self):
        apps = literal('host_apps.py', 'APPS')
        self.assertIn(('/api/symblic-forge/', 'symblic_forge', True, ()), apps)
        self.assertIn('symblic_forge_data', literal('server.py', '_PRIVATE_DATA_DIRS'))
        self.assertIn('/api/symblic-forge', literal('server.py', '_OWNER_ONLY_PREFIXES'))
        self.assertIn('/symblic_forge_data/', (ROOT / '.gitignore').read_text().splitlines())

    def test_directory_navigation_shared_controls_backup_and_probe_match_real_source(self):
        from scripts.install_command_bar import transform, config
        from scripts.stamp_assets import nav_pages
        source = (ROOT / 'index2.html').read_text()
        rows = json.loads(re.search(r'<script[^>]+id="nav-data"[^>]*>(.*?)</script>', source, re.S).group(1))['pages']
        row = next(r for r in rows if r['href'] == '/symblic-forge')
        # A file row since 2026-10-10: dir "." mounted the whole checkout under /symblic-forge/.
        # The row is hidden from the launcher (the /symblic hub lists Forge) but stays routable.
        self.assertEqual(row.get('file'), 'symblic-forge.html'); self.assertNotIn('dir', row)
        self.assertIs(row.get('hidden'), True)
        self.assertIn('symblic-forge.html', nav_pages(str(ROOT)))
        source = (ROOT / 'symblic-forge.html').read_text()
        self.assertEqual(source, transform(source, 'symblic-forge.html', config()))
        self.assertIn('symblic_forge_data', literal('lifeboat.py', 'TARGET_DIRS'))
        self.assertEqual(literal('symblic_forge_watch.py', 'COVERS'), ['symblic_forge'])

    def test_online_backup_includes_committed_wal_and_restores_real_project(self):
        from lifeboat import _sqlite_consistent_copy
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); store = Store(root / 'original')
            p = store.create('Preserve this exact project', 'Backup fixture', '', 'backup-create-fixture')
            with sqlite3.connect(store.root / 'forge.sqlite3') as keep_open:
                keep_open.execute('PRAGMA journal_mode=WAL')
                keep_open.execute('PRAGMA wal_autocheckpoint=0')
                keep_open.execute('BEGIN')
                keep_open.execute('SELECT revision FROM projects').fetchall()
                p = store.mutate(p['id'], 0, 'project.rename', {'title': 'Committed in WAL'}, 'backup-change-fixture')
                self.assertGreater((store.root / 'forge.sqlite3-wal').stat().st_size, 0)
                restored = Store(root / 'restored'); restored.root.mkdir()
                _sqlite_consistent_copy(str(store.root / 'forge.sqlite3'), str(restored.root / 'forge.sqlite3'))
                self.assertEqual(restored.get(p['id']), p)
                self.assertEqual(len(restored.history(p['id'])), 2)


if __name__ == '__main__':
    unittest.main()
