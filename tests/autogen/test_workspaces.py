"""Managed project workspaces (symblic/autogen/workspaces.py): temporary roots only.

Covers the committed baseline and idempotent names, refusal to touch unmanaged folders, names and
symlinks that would escape the projects folder, hooks and templates from the environment never
running, retained evidence after a failed initialization, and concurrent creates of one name.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from symblic.autogen.runner import TaskError


class Workspaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def create(self, name):
        from symblic.autogen.workspaces import create_workspace
        return create_workspace(self.root, name, check_host=lambda: None)

    def test_new_project_has_committed_baseline_and_idempotent_name(self):
        first = self.create('snake-game')
        self.assertTrue(first['created'])
        directory = Path(first['cwd'])
        self.assertEqual(first['baseline'], (directory / '.git/refs/heads/main').read_text().strip())
        (directory / 'game.py').write_text('print("preserve")\n')
        again = self.create('snake-game')
        self.assertFalse(again['created'])
        self.assertEqual(first['cwd'], again['cwd'])
        self.assertEqual('print("preserve")\n', (directory / 'game.py').read_text())

    def test_nonmanaged_existing_folder_is_never_initialized(self):
        folder = self.root / 'projects/existing'
        folder.mkdir(parents=True)
        (folder / 'keep.txt').write_text('keep')
        with self.assertRaisesRegex(TaskError, 'Nothing was overwritten'):
            self.create('existing')
        self.assertFalse((folder / '.git').exists())
        self.assertEqual('keep', (folder / 'keep.txt').read_text())

    def test_names_and_symlinks_cannot_escape_managed_projects(self):
        for name in ('../outside', '/tmp/outside', 'space name', '.', '', 'Uppercase'):
            with self.assertRaises(TaskError):
                self.create(name)
        (self.root / 'projects').mkdir()
        (self.root / 'projects/link').symlink_to(self.root)
        with self.assertRaises(TaskError):
            self.create('link')
        self.assertFalse((self.root / '.git').exists())

    def test_injected_git_hooks_and_templates_are_not_executed(self):
        template = self.root / 'template'
        (template / 'hooks').mkdir(parents=True)
        sentinel = self.root / 'hook-ran'
        hook = template / 'hooks/pre-commit'
        hook.write_text('#!/bin/sh\ntouch ' + str(sentinel) + '\n')
        hook.chmod(0o755)
        with patch.dict(os.environ, {'GIT_TEMPLATE_DIR': str(template), 'GIT_CONFIG_COUNT': '1',
                                     'GIT_CONFIG_KEY_0': 'core.hooksPath', 'GIT_CONFIG_VALUE_0': str(template / 'hooks')}):
            result = self.create('safe')
        self.assertTrue(result['created'])
        self.assertFalse(sentinel.exists())

    def test_failed_initialization_keeps_evidence_and_refuses_overwrite(self):
        import subprocess
        with patch('symblic.autogen.workspaces.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['git'])):
            with self.assertRaisesRegex(TaskError, 'retained'):
                self.create('incomplete')
        self.assertTrue((self.root / 'projects/incomplete/.symblic-workspace.json').exists())
        with self.assertRaisesRegex(TaskError, 'Nothing was overwritten'):
            self.create('incomplete')

    def test_same_name_concurrent_creates_one_repo(self):
        results, errors = [], []
        def create():
            try:
                results.append(self.create('concurrent'))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=create) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([], errors)
        self.assertEqual(1, sum(row['created'] for row in results))
        self.assertEqual(1, len({row['baseline'] for row in results}))


if __name__ == '__main__':
    unittest.main()
