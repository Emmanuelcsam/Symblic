"""MICA component library: private, content-addressed reuse of units that already passed their checks.

Depends on: symblic.graph.run, symblic.spec.contracts. Used by search.py (lookup, always rechecked) and
promote.py (publication).

Details
    Private content-addressed component exchange for MICA.

    These records are candidates for reuse, never authority to skip current checks.
    No workers, provider calls, shared public store or importer starts on import.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import fcntl
import hashlib
import os
import re
from contextlib import contextmanager
from pathlib import Path

from symblic.graph import run as G
from symblic.spec import contracts as SC

VERSION = 1
MAX_CANDIDATES = 8
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class LibraryError(ValueError):
    pass


def identity(contract_sha256, dependency_hashes, runtime):
    """The exact key a component is stored under: its contract, complete dependencies and runtime."""
    if (not isinstance(contract_sha256, str) or not _SHA.fullmatch(contract_sha256)
            or type(dependency_hashes) is not list
            or any(type(h) is not str or not _SHA.fullmatch(h) for h in dependency_hashes)):
        raise LibraryError("Component identity requires exact contract and dependency hashes.")
    return G._hash({"contract": contract_sha256, "dependencies": dependency_hashes, "runtime": runtime})


class ComponentLibrary:
    """A private folder of accepted units keyed by exact identity (at most a few variants per key)."""

    def __init__(self, root):
        self.root = Path(root).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise LibraryError("Symlinked component library refused.")
        G._mkdir_private(self.root)
        G._safe_listing(self.root, 20000)
        info = self.root.stat()
        self.root_identity = (info.st_dev, info.st_ino)

    @contextmanager
    def _lock(self):
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise LibraryError("Component library identity changed.")
        info = self.root.stat()
        if (info.st_dev, info.st_ino) != self.root_identity:
            raise LibraryError("Component library directory was replaced.")
        fd = os.open(self.root / ".library.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def candidates(self, key, *, runtime):
        """Stored variants for an exact identity key; the caller rechecks each before any reuse."""
        if type(key) is not str or not _SHA.fullmatch(key):
            raise LibraryError("Invalid component key.")
        with self._lock():
            folder = self.root / key
            if not folder.exists() and not folder.is_symlink():
                return []
            if folder.is_symlink() or not folder.is_dir():
                raise LibraryError("Redirected component folder refused.")
            G._safe_listing(folder, MAX_CANDIDATES)
            result = []
            for path in sorted(folder.iterdir()):
                token = G._unseal(G._read(path))
                code = token.get("code")
                if type(token) is not dict or not isinstance(token.get("contract_sha256"), str) \
                        or not isinstance(token.get("dependency_hashes"), list):
                    raise LibraryError("Component record no longer matches its retained inputs.")
                expected = identity(token["contract_sha256"], token["dependency_hashes"], runtime)
                if (token.get("version") != VERSION or token.get("key") != key or expected != key
                        or token.get("runtime") != runtime or type(code) is not str
                        or len(code.encode("utf-8")) > 400000
                        or token.get("code_sha256") != SC.code_hash(code)
                        or path.name != token["code_sha256"] + ".json"
                        or token.get("assurance") != "TESTED"):
                    raise LibraryError("Component record no longer matches its retained inputs.")
                result.append(token)
            return result

    def publish(self, *, contract_sha256, dependency_hashes, runtime, code):
        """Retain bytes checked by the caller; consumers must independently recheck."""
        key = identity(contract_sha256, dependency_hashes, runtime)
        if type(code) is not str or not code or len(code.encode("utf-8")) > 400000:
            raise LibraryError("Component source must be bounded nonempty text.")
        token = G._seal({"version": VERSION, "key": key, "contract_sha256": contract_sha256,
                         "dependency_hashes": dependency_hashes, "runtime": runtime,
                         "code": code, "code_sha256": SC.code_hash(code), "assurance": "TESTED",
                         "scope": "caller_recorded_checks_require_independent_recheck_on_reuse"})
        with self._lock():
            folder = self.root / key
            if folder.is_symlink():
                raise LibraryError("Redirected component folder refused.")
            G._mkdir_private(folder)
            G._safe_listing(folder, MAX_CANDIDATES)
            paths = list(folder.iterdir())
            name = token["code_sha256"] + ".json"
            path = folder / name
            if path.exists() or path.is_symlink():
                if G._unseal(G._read(path)) != token:
                    raise LibraryError("An immutable component record changed.")
            elif len(paths) >= MAX_CANDIDATES:
                return {"status": "full", "key": key, "retained": False}
            else:
                G._write_json(folder, name, token)
        return {"status": "retained", "key": key, "retained": True, "sha256": token["sha256"]}


SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
