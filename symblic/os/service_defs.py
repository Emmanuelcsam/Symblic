"""systemd unit files and an environment file for running the OS prototype as services (templates).

generate_service_files(config_dir, services_dir, root=..., repo_dir=..., user=...) writes three files
and returns their paths:

    <config_dir>/symblicos.env                    the environment the services read
    <services_dir>/symblicos-terminal.service     runs `python3 -m symblic.os.terminal_server` on loopback
    <services_dir>/symblicos-model.service        a PLACEHOLDER: it only prints a line and sleeps; no
                                                  model gateway exists in this repository

Nothing is installed or started: copying the units into a systemd folder and enabling them is the
operator's decision. The defaults put everything under paths.default_root() and use the current user.
"""
from __future__ import annotations
import getpass
import os
from typing import Dict, Optional

from symblic.os.paths import default_root

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

TERMINAL_SERVICE_TEMPLATE = """[Unit]
Description=Symblic OS prototype: terminal engine (development listener on loopback)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={repo_dir}
EnvironmentFile={root}/config/symblicos.env
ExecStart=/usr/bin/python3 -m symblic.os.terminal_server
Restart=on-failure
RestartSec=5s
StandardOutput=append:{root}/logs/terminal.log
StandardError=append:{root}/logs/terminal.err
LimitNOFILE=65536
KillMode=process

[Install]
WantedBy=multi-user.target
"""

MODEL_SERVICE_TEMPLATE = """[Unit]
Description=Symblic OS prototype: model gateway PLACEHOLDER (prints one line and sleeps; no gateway exists)
After=network.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={repo_dir}
EnvironmentFile={root}/config/symblicos.env
ExecStart=/usr/bin/python3 -c "import time; print('placeholder: no model gateway is implemented'); time.sleep(86400)"
Restart=on-failure
RestartSec=5s
StandardOutput=append:{root}/logs/model_gateway.log
StandardError=append:{root}/logs/model_gateway.err
KillMode=process

[Install]
WantedBy=multi-user.target
"""

ENV_FILE_TEMPLATE = """# Symblic OS prototype environment
SYMBLICOS_ENV=development
SYMBLICOS_ROOT={root}
SYMBLICOS_TERMINAL_PORT=8990
SYMBLICOS_BIND_ADDR=127.0.0.1
SYMBLICOS_TARGET_NODE={target_node}
SYMBLICOS_RUNTIME_VERSION=2.5
"""


def generate_service_files(config_dir: Optional[str] = None, services_dir: Optional[str] = None, *,
                           root: Optional[str] = None, repo_dir: str = REPO_DIR, user: Optional[str] = None,
                           target_node: str = "node-a") -> Dict[str, str]:
    """Write the environment file and the two unit files; return {'env', 'terminal_service', 'model_service'}."""
    root = root or default_root()
    config_dir = config_dir or os.path.join(root, "config")
    services_dir = services_dir or os.path.join(root, "services")
    values = {"root": root, "repo_dir": repo_dir, "user": user or getpass.getuser(), "target_node": target_node}
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(services_dir, exist_ok=True)

    env_path = os.path.join(config_dir, "symblicos.env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(ENV_FILE_TEMPLATE.format(**values))

    term_unit = os.path.join(services_dir, "symblicos-terminal.service")
    with open(term_unit, "w", encoding="utf-8") as f:
        f.write(TERMINAL_SERVICE_TEMPLATE.format(**values))

    model_unit = os.path.join(services_dir, "symblicos-model.service")
    with open(model_unit, "w", encoding="utf-8") as f:
        f.write(MODEL_SERVICE_TEMPLATE.format(**values))

    return {
        "env": env_path,
        "terminal_service": term_unit,
        "model_service": model_unit,
    }
