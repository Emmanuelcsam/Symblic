#!/usr/bin/env python3
"""Install the optional source-navigation tools that tools/symblic-context uses; nothing else changes.

    python3 tools/scripts/install_symblic_tools.py [--home DIR]     (default ~/.local/share/symblic-tools)

Clones grep-ast (https://github.com/Aider-AI/grep-ast) at a pinned commit, creates a virtual environment in
DIR/venv with uv (https://github.com/astral-sh/uv, required) and installs grep-ast plus pinned tree-sitter
packages into it from a temporary archive, so the clone stays clean. It writes DIR/installation.json as a
receipt. No model, global setting or system Python package is touched. tools/symblic-context uses the
environment when it exists and works without it (plain line context instead of grep-ast excerpts).
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPOS = {
    'grep-ast': ('https://github.com/Aider-AI/grep-ast.git', '9a2c49b00852d012dc97850a3c0b3248f15bd043'),
}
DEPS = ['tree-sitter==0.25.2', 'tree-sitter-python==0.25.0',
        'tree-sitter-javascript==0.25.0', 'tree-sitter-typescript==0.23.2',
        'tree-sitter-language-pack==0.10.0', 'pathspec==0.12.1',
        'tree-sitter-c-sharp==0.23.5', 'tree-sitter-embedded-template==0.25.0',
        'tree-sitter-yaml==0.7.2']


def extract_source(archive, destination):
    """Extract only plain files and folders (Python 3.11 has no tarfile filter API): no links, no escaping paths."""
    with tarfile.open(archive) as stream:
        members = stream.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Source archive contains a link, special file or escaping path')
        stream.extractall(destination, members=members)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home() / '.local/share/symblic-tools')
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    uv = shutil.which('uv')
    if not uv:
        raise SystemExit('uv is required; no packages were installed into system Python')
    receipts = {}
    for name, (url, revision) in REPOS.items():
        path = home / 'repos' / name
        if not path.exists():
            subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout', url, str(path)], check=True)
            subprocess.run(['git', '-C', str(path), 'checkout', '--detach', revision], check=True)
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain'], text=True).strip()
        if actual != revision or dirty:
            raise SystemExit(f'{path} is not the clean pinned revision; existing work was preserved')
        receipts[name] = {'url': url, 'revision': revision}
    python = home / 'venv/bin/python'
    if not python.exists():
        subprocess.run([uv, 'venv', '--python', sys.executable, str(home / 'venv')], check=True)
    # Build out of temporary archives, so setuptools cannot dirty the pinned clone.
    with tempfile.TemporaryDirectory(prefix='symblic-tools-build-') as folder:
        builds = []
        for name, (_, revision) in REPOS.items():
            source = home / 'repos' / name
            archive = Path(folder, name + '.tar')
            destination = Path(folder, name)
            destination.mkdir()
            selected = []
            subprocess.run(['git', '-C', str(source), 'archive', '-o', str(archive),
                            revision, *selected], check=True)
            extract_source(archive, destination)
            builds.append(str(destination / selected[0] if selected else destination))
        subprocess.run([uv, 'pip', 'install', '--python', str(python), *DEPS, *builds], check=True)
    receipts['dependencies'] = DEPS
    path = home / 'installation.json'
    path.write_text(json.dumps(receipts, indent=2) + '\n')
    os.chmod(path, 0o600)
    print(f'Installed pinned tools in {home}; run tools/symblic-context doctor')


if __name__ == '__main__':
    main()
