"""Own checkouts and the 3-way apply (symblic/autogen/git_checkouts.py) on temporary git repositories.

Covers: the checkout lives beside the project on an autogen/ branch, carries the project's uncommitted
work as its baseline and is adopted by name after a crash; the apply writes added, changed and deleted
files only where the project still holds the baseline (or merges cleanly), refuses everything on any
clash, never commits in the project, and is content-idempotent.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/autogen -t .
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from symblic.autogen import git_checkouts as G

IDENTITY = ['-c', 'user.name=test', '-c', 'user.email=test@localhost']


def git(cwd, *args):
    return subprocess.run(['git', *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class Checkouts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autogen-git-')
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name, 'project')
        self.repo.mkdir()
        (self.repo / 'README.md').write_text('project\n')
        (self.repo / 'lib.py').write_text('a = 1\nb = 2\nc = 3\nd = 4\n')
        (self.repo / 'old.txt').write_text('old\n')
        git(self.repo, 'init', '-q')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'base')
        self.head = git(self.repo, 'rev-parse', 'HEAD').strip()

    def status(self):
        return git(self.repo, 'status', '--porcelain')

    def test_a_checkout_carries_uncommitted_work_as_its_baseline_and_is_adopted_by_name(self):
        (self.repo / 'README.md').write_text('project, edited by the operator\n')    # tracked, uncommitted
        (self.repo / 'notes.txt').write_text('untracked\n')                            # untracked
        (self.repo / '__pycache__').mkdir()
        (self.repo / '__pycache__' / 'x.pyc').write_bytes(b'junk')                     # never carried
        before = self.status()
        info = G.make_checkout(str(self.repo), 'autogen-run-n0-a0')
        self.assertTrue(info['branch'].startswith('autogen/autogen-run-n0-a0-'))
        self.assertTrue(info['worktree'].startswith(str(self.repo) + '.autogen' + os.sep))
        self.assertEqual((str(self.repo), False), (info['main_root'], info['adopted']))
        self.assertNotEqual(self.head, info['base_sha'])                  # the baseline commit
        self.assertEqual(self.head, info['carried']['head'])
        worktree = Path(info['worktree'])
        self.assertEqual('project, edited by the operator\n', (worktree / 'README.md').read_text())
        self.assertEqual('untracked\n', (worktree / 'notes.txt').read_text())
        self.assertFalse((worktree / '__pycache__').exists())
        self.assertEqual(before, self.status())                           # the project is untouched
        again = G.make_checkout(str(self.repo), 'autogen-run-n0-a0')
        self.assertEqual((info['worktree'], info['branch'], True), (again['worktree'], again['branch'], again['adopted']))
        other = G.make_checkout(str(self.repo), 'autogen-run-n0-a1')    # a prefix of another name is not adopted
        self.assertNotEqual(info['worktree'], other['worktree'])
        with self.assertRaises(G.CheckoutError):
            G.make_checkout(str(self.repo), '../escape')
        with self.assertRaises(G.CheckoutError):
            G.make_checkout(tempfile.gettempdir(), 'outside-a-repository')

    def test_the_apply_writes_only_where_the_project_holds_the_baseline(self):
        info = G.make_checkout(str(self.repo), 'apply-n0-a0')
        worktree = Path(info['worktree'])
        (worktree / 'new.py').write_text('print("new")\n')
        (worktree / 'lib.py').write_text('a = 1\nb = 2\nc = 3\nd = 40\n')     # changes the last line
        (worktree / 'old.txt').unlink()
        self.assertEqual('Committed.', G.commit_all(info, 'autogen: attempt'))
        self.assertEqual('Nothing to commit.', G.commit_all(info, 'autogen: again'))
        (self.repo / 'lib.py').write_text('a = 10\nb = 2\nc = 3\nd = 4\n')    # the operator changed the first line
        applied = G.apply_to_project(info)
        self.assertEqual(['lib.py', 'new.py', 'old.txt'], sorted(applied['files']))
        self.assertEqual('a = 10\nb = 2\nc = 3\nd = 40\n', (self.repo / 'lib.py').read_text())   # both changes kept
        self.assertEqual('print("new")\n', (self.repo / 'new.py').read_text())
        self.assertFalse((self.repo / 'old.txt').exists())
        self.assertEqual(self.head, git(self.repo, 'rev-parse', 'HEAD').strip())   # nothing committed in the project
        self.assertEqual([], G.apply_to_project(info)['files'])           # content-idempotent

    def test_a_clash_refuses_the_whole_apply(self):
        info = G.make_checkout(str(self.repo), 'clash-n0-a0')
        worktree = Path(info['worktree'])
        (worktree / 'new.py').write_text('print("new")\n')
        (worktree / 'lib.py').write_text('a = 1\nb = 2\nc = 30\nd = 4\n')
        G.commit_all(info, 'autogen: attempt')
        (self.repo / 'lib.py').write_text('a = 1\nb = 2\nc = 300\nd = 4\n')   # the same line, differently
        with self.assertRaises(G.CheckoutError) as caught:
            G.apply_to_project(info)
        self.assertIn('Nothing was applied: 1 file(s) clash with your checkout: lib.py (1 overlapping change)',
                      str(caught.exception))
        self.assertFalse((self.repo / 'new.py').exists())                  # all or nothing
        self.assertEqual('a = 1\nb = 2\nc = 300\nd = 4\n', (self.repo / 'lib.py').read_text())

    def test_only_autogen_branches_and_committed_work_are_applied(self):
        info = G.make_checkout(str(self.repo), 'guard-n0-a0')
        with self.assertRaises(G.CheckoutError):
            G.apply_to_project({**info, 'branch': 'main'})
        (Path(info['worktree']) / 'lib.py').write_text('changed but not committed\n')
        with self.assertRaises(G.CheckoutError) as caught:
            G.apply_to_project(info)
        self.assertIn('uncommitted changes', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
