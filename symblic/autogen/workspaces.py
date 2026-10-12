"""Managed project workspaces: empty git repositories that autogen runs may work in.

What it is for
    An autogen run (symblic/autogen/coordinator.py) needs a git project folder: attempts work in their
    own checkouts of it and accepted results are applied back into it. create_workspace(root, name)
    makes one at <root>/projects/<name>: a fresh repository with one empty baseline commit and a
    receipt file (.symblic-workspace.json) that says it is managed. Calling it again with the same
    name returns the same workspace; a folder of that name that is not a complete managed workspace
    is never touched.

Safety
    The repository is initialized with git's user configuration, hooks and templates switched off,
    so nothing from the calling environment (hooks, signing keys, credentials, templates) runs or
    leaks into it. A per-name lock makes concurrent creates of the same name produce one repository.

Depends on
    git and the Python standard library; symblic.autogen.runner (TaskError, execution_fence) and
    symblic.autogen.durable (atomic_json).
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from symblic.autogen.durable import atomic_json
from symblic.autogen.runner import TaskError, execution_fence

NAME = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
MARKER = '.symblic-workspace.json'


def create_workspace(root, name, *, check_host=execution_fence):
    """Create (or return) the managed workspace <root>/projects/<name>. Returns {'cwd', 'path', 'name',
    'created', 'baseline'}; raises TaskError (409 for an unmanaged or incomplete folder of that name,
    503 when git is missing or initialization failed, with the folder kept for inspection)."""
    check_host()
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise TaskError('Use a project name of 1–64 lowercase letters, digits, hyphens or underscores; start with a letter or digit.')
    git = shutil.which('git')
    if not git:
        raise TaskError('Git is unavailable; no project was created.', 503)
    root = Path(root).resolve()
    projects = root / 'projects'
    locks = root / 'state' / 'workspaces'
    projects.mkdir(parents=True, exist_ok=True)
    locks.mkdir(parents=True, exist_ok=True)
    if projects.is_symlink() or projects.resolve().parent != root:
        raise TaskError('The managed projects directory must remain inside the state root.', 409)
    directory = projects / name
    marker = directory / MARKER
    with (locks / (name + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.lexists(directory):
            try:
                if directory.is_symlink() or not directory.is_dir() or marker.is_symlink():
                    raise ValueError('unmanaged path')
                receipt = json.loads(marker.read_text())
                if (not isinstance(receipt, dict) or receipt.get('format') != 'symblic-workspace-1' or
                        receipt.get('status') != 'ready' or receipt.get('name') != name or
                        receipt.get('cwd') != str(directory) or (directory / '.git').is_symlink() or
                        not (directory / '.git').is_dir() or
                        not re.fullmatch(r'[a-f0-9]{40,64}', str(receipt.get('baseline', '')))):
                    raise ValueError('incomplete marker')
            except (OSError, ValueError):
                raise TaskError('This name already exists without a complete managed-workspace receipt. Nothing was overwritten; inspect that folder or choose another name.', 409) from None
            return {'cwd': str(directory), 'path': str(directory), 'name': name, 'created': False,
                    'baseline': receipt['baseline']}
        directory.mkdir(mode=0o700)  # Exclusive creation; no pre-existing folder is initialized.
        parent_fd = os.open(projects, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        receipt = {'format': 'symblic-workspace-1', 'name': name, 'cwd': str(directory),
                   'status': 'creating', 'created': time.time()}
        atomic_json(marker, receipt)
        # A new empty repository never inherits user hooks, templates, signing,
        # credentials or Git config from the calling service's environment.
        env = {'PATH': os.defpath, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
               'GIT_TERMINAL_PROMPT': '0'}
        prefix = [git, '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                  '-c', 'core.fsync=all', '-c', 'core.fsyncMethod=fsync',
                  '-c', 'init.templateDir=', '-c', 'user.name=Symblic Workspace',
                  '-c', 'user.email=symblic@localhost']

        def run(*args):
            return subprocess.run(prefix + list(args), cwd=directory, env=env, capture_output=True,
                                  text=True, timeout=30, check=True).stdout.strip()
        try:
            run('init', '--quiet', '--initial-branch=main')
            info = directory / '.git' / 'info'
            info.mkdir(exist_ok=True)
            (info / 'exclude').write_text(MARKER + '\n')
            run('commit', '--quiet', '--allow-empty', '-m', 'Initialize Symblic workspace')
            baseline = run('rev-parse', '--verify', 'HEAD')
            if not re.fullmatch(r'[a-f0-9]{40,64}', baseline):
                raise ValueError('Git did not return a baseline commit')
            receipt.update(status='ready', baseline=baseline)
            atomic_json(marker, receipt)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            receipt.update(status='incomplete', error=type(exc).__name__)
            atomic_json(marker, receipt)
            raise TaskError('Project initialization did not complete. Its folder and receipt were retained for inspection; nothing was overwritten.', 503) from None
        return {'cwd': str(directory), 'path': str(directory), 'name': name, 'created': True,
                'baseline': baseline}
