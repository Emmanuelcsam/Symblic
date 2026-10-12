"""The filesystem boundary: every path the OS prototype touches must stay inside one root folder.

FilesystemBoundary(root).resolve_path(path) returns the absolute path or raises FilesystemBoundaryError
when the path escapes the root, either lexically ("../x", an absolute path elsewhere) or through a
symbolic link (including a dangling one). check_read_permission / check_write_permission add the
existence and permission checks. This is a guard for the prototype's own file commands, not a sandbox:
a process the prototype starts is not confined by it. Standard library only."""
from __future__ import annotations
import os

class FilesystemBoundaryError(PermissionError):
    """Raised when an operation attempts to escape the sandboxed filesystem root."""
    pass

class FilesystemBoundary:
    """Enforces sandbox boundary for all SymblicOS filesystem operations."""

    def __init__(self, root_dir: str):
        self.root_dir = os.path.realpath(os.path.abspath(root_dir))
        os.makedirs(self.root_dir, exist_ok=True)

    def resolve_path(self, target_path: str, allow_privileged_system: bool = False) -> str:
        """Resolve, canonicalize and validate target path within the sandbox root.
        
        Rejects directory traversal (..) and symlink escapes outside root_dir.
        """
        if not target_path or not target_path.strip():
            raise FilesystemBoundaryError("Empty path is invalid")

        clean_path = target_path.strip()

        # If absolute and within root, check containment
        if os.path.isabs(clean_path):
            candidate = os.path.abspath(clean_path)
        else:
            candidate = os.path.abspath(os.path.join(self.root_dir, clean_path))

        # Check for lexical containment before resolving symlinks
        common = os.path.commonpath([self.root_dir, candidate])
        if common != self.root_dir and not allow_privileged_system:
            raise FilesystemBoundaryError(f"Path traversal rejected: '{target_path}' escapes root '{self.root_dir}'")

        # realpath also resolves dangling links: exists() alone misses their escape.
        real_target = os.path.realpath(candidate)
        if os.path.commonpath([self.root_dir, real_target]) != self.root_dir and not allow_privileged_system:
            raise FilesystemBoundaryError(f"Symlink target escapes filesystem root: {target_path}")

        return candidate

    def check_read_permission(self, target_path: str, allow_privileged: bool = False) -> str:
        resolved = self.resolve_path(target_path, allow_privileged_system=allow_privileged)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Path does not exist: {resolved}")
        if not os.access(resolved, os.R_OK):
            raise FilesystemBoundaryError(f"Read permission denied: {resolved}")
        return resolved

    def check_write_permission(self, target_path: str, allow_privileged: bool = False) -> str:
        resolved = self.resolve_path(target_path, allow_privileged_system=allow_privileged)
        parent = os.path.dirname(resolved)
        if os.path.exists(resolved):
            if not os.access(resolved, os.W_OK):
                raise FilesystemBoundaryError(f"Write permission denied: {resolved}")
        elif os.path.exists(parent):
            if not os.access(parent, os.W_OK):
                raise FilesystemBoundaryError(f"Parent directory write permission denied: {parent}")
        return resolved
