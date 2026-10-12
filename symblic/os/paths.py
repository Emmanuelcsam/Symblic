"""Where the OS prototype keeps its files: one root folder with a fixed set of subfolders.

The root is the SYMBLICOS_ROOT environment variable when it is set, else ~/symblicos. Every other
module of symblic.os takes its folders from here (or from a root passed in explicitly), so a test or
a second installation only has to point at another root. Nothing is created on import; call
ensure_dev_directories() to create the tree.

    <root>/user_files   the only folder the terminal engine's file commands may touch
    <root>/receipts     one JSON receipt per executed instruction, plus receipts.jsonl
    <root>/state        locks and the autogen/task state of a host that embeds this package
    <root>/build/image  the bootable image's root filesystem and disk images (image_builder)
    <root>/releases     the roadmap and the scoped release manifest
    ...                 config, logs, models, repos, web, tests, adapters, services (reserved)

NODE_INSTALL_ROOT is where the same tree would live on another machine (a node) when the prototype
is installed there; nothing in this repository installs it.
"""
from __future__ import annotations

import os


def default_root() -> str:
    """SYMBLICOS_ROOT, else ~/symblicos (read at call time, so tests can redirect it)."""
    return os.environ.get('SYMBLICOS_ROOT') or os.path.join(os.path.expanduser('~'), 'symblicos')


DEV_ROOT = default_root()                       # the root as it was when this module was imported
NODE_INSTALL_ROOT = os.environ.get('SYMBLICOS_NODE_ROOT') or '/opt/symblicos'
RECEIPTS_DIR = os.path.join(DEV_ROOT, 'receipts')
USER_FILES_DIR = os.path.join(DEV_ROOT, 'user_files')

# Subdirectories required for clean segregation
SUBDIRECTORIES = [
    "src",
    "config",
    "state",
    "receipts",
    "logs",
    "models/manifests",
    "models/data",
    "repos",
    "web",
    "tests",
    "adapters",
    "services",
    "user_files",
    "build/image",
    "releases",
]


def get_dev_paths(root: str | None = None) -> dict[str, str]:
    """{'root': ..., 'user_files': ..., 'build_image': ..., ...}: absolute paths under `root`."""
    root = root or default_root()
    paths = {"root": os.path.abspath(root)}
    for sub in SUBDIRECTORIES:
        key = sub.replace("/", "_")
        paths[key] = os.path.abspath(os.path.join(root, sub))
    return paths


def get_node_paths(root: str = NODE_INSTALL_ROOT) -> dict[str, str]:
    """The same tree under a node's install root (paths only; nothing is checked or created)."""
    paths = {"root": root}
    for sub in SUBDIRECTORIES:
        key = sub.replace("/", "_")
        paths[key] = f"{root}/{sub}"
    return paths


def ensure_dev_directories(root: str | None = None) -> dict[str, str]:
    """Create every folder of the tree under `root` (default_root() when None) and return the paths."""
    paths = get_dev_paths(root)
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths
