#!/usr/bin/env python3
"""HOST-ONLY: provisions a worker node of the original host's cluster; needs its staged bundle and job runner.

What it did: run inside a staged bundle (copied to a node by the host's admitted job runner) containing the
host's three-agent pipeline tool (pipeline/), one reviewed wheel of a third-party terminal agent
(wheels/agentcli*.whl), the context tools and their installer, it created ~/.local/share/symblic-node,
installed the wheel into a virtual environment with uv, ran tools/scripts/install_symblic_tools.py and wrote
small command wrappers into ~/.local/bin. It never copies accounts, histories, SSH keys or browser data, and it
preserves existing command wrappers it did not write. The terminal agent's real package name is replaced by
the placeholder `agentcli` in this copy; the bundle layout is the host's own.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def install(bundle: Path) -> dict:
    home = Path.home()
    destination = home / '.local/share/symblic-node'
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    uv = shutil.which('uv') or str(home / '.local/bin/uv')
    if not os.access(uv, os.X_OK):
        raise RuntimeError('Node uv is unavailable; install through the existing node tooling first')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is unavailable')
    version = subprocess.check_output([node, '--version'], text=True).strip()
    if int(version.lstrip('v').split('.')[0]) < 18:
        raise RuntimeError('The three-agent pipeline requires Node.js 18 or newer')
    wheels = list((bundle / 'wheels').glob('agentcli-*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Bundle must contain exactly one reviewed agentcli wheel')
    python = destination / 'venv/bin/python'
    if not python.exists():
        subprocess.run([uv, 'venv', '--python', sys.executable, str(destination / 'venv')], check=True)
    subprocess.run([uv, 'pip', 'install', '--python', str(python), str(wheels[0])], check=True)
    app = destination / 'app'
    app.mkdir(exist_ok=True, mode=0o700)
    for name in ('pipeline', 'tools'):
        shutil.copytree(bundle / name, app / name, dirs_exist_ok=True)
    shutil.copytree(bundle / 'symblic', app / 'symblic', dirs_exist_ok=True)   # the package (context packs)
    if (bundle / 'mistral_vibe.py').is_file():
        shutil.copy2(bundle / 'mistral_vibe.py', app / 'mistral_vibe.py')
    env = dict(os.environ, PATH=str(home / '.local/bin') + ':' + os.environ.get('PATH', '/usr/bin:/bin'))
    subprocess.run([sys.executable, str(app / 'tools/scripts/install_symblic_tools.py')], env=env, check=True)
    bindir = home / '.local/bin'
    bindir.mkdir(parents=True, exist_ok=True)
    marker = '# managed by install_symblic_node.py\n'
    wrappers = {
        'agentcli': [str(destination / 'venv/bin/agentcli')],
        'agentcli-local': [node, str(app / 'pipeline/src/agentcli-local.js')],
        'pipeline': [node, str(app / 'pipeline/bin/pipeline.js')],
        'symblic-context': [sys.executable, str(app / 'tools/symblic-context')],
    }
    import shlex
    for name, argv in wrappers.items():
        path = bindir / name
        if path.exists() or path.is_symlink():
            if path.is_symlink() or marker not in path.read_text(errors='replace'):
                raise RuntimeError(f'Preserved existing unowned command {path}; integrate it explicitly')
        preamble = ''
        if name in ('agentcli', 'agentcli-local'):
            preamble = 'export PATH=' + shlex.quote(str(destination / 'venv/bin')) + ':"$PATH"\n'
        if name == 'agentcli-local':
            preamble += 'export SYMBLIC_AGENTCLI_PYTHON=' + shlex.quote(str(python)) + '\n'
        path.write_text('#!/bin/sh\n' + marker + preamble + 'exec ' + shlex.join(argv) + ' "$@"\n')
        path.chmod(0o755)
    for argv in ([str(bindir / 'pipeline'), '--help'], [str(bindir / 'agentcli'), '--version'], [str(bindir / 'agentcli-local'), '--help'],
                 [str(bindir / 'symblic-context'), 'doctor']):
        subprocess.run(argv, env=env, check=True, stdout=subprocess.DEVNULL, timeout=30)
    receipt = {'ok': True, 'nodejs': version, 'agentcli_wheel_sha256': hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
               'commands': {name: str(bindir / name) for name in wrappers},
               'scope': 'runtime binaries only; no model execution or account transfer'}
    (destination / 'installation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (destination / 'installation.json').chmod(0o600)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    print(json.dumps(install(parser.parse_args().bundle.resolve())))
