"""File effects of the OS prototype: create, locate, read, replace, append, mkdir, list, copy, move,
remove and flush, each inside a FilesystemBoundary and each recorded in a receipt.

Every write goes to a temporary file in the same folder, is fsynced and renamed into place (create uses
a hard link, so it never overwrites an existing file); the folder is fsynced afterwards. Records carry
sha256 digests (before and after for replacements). remove_file requires authorized=True: the caller
must decide explicitly that a destructive effect is wanted. Standard library only."""
from __future__ import annotations
import hashlib
import os
import shutil
import tempfile
from typing import Any, Dict, Optional
from symblic.os.fs_boundary import FilesystemBoundary

def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def compute_file_digest(filepath: str) -> Optional[str]:
    """Compute sha256 digest of file content if it exists."""
    if not os.path.exists(filepath) or os.path.isdir(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

class FileEffectsManager:
    """Executes deterministic filesystem reads and named mutating effects."""

    def __init__(self, boundary: FilesystemBoundary):
        self.boundary = boundary

    def create_file(self, path: str, content: str = "", receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new file within the sandbox."""
        resolved = self.boundary.check_write_permission(path)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        
        # Atomic creation via temp file
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(resolved), prefix=".sym_tmp_")
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.link(temp_path, resolved)
            os.unlink(temp_path)
            sync_directory(os.path.dirname(resolved))
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        digest = compute_file_digest(resolved)
        record = {
            "path": resolved,
            "relative_path": os.path.relpath(resolved, self.boundary.root_dir),
            "size": len(content.encode("utf-8")),
            "sha256": digest,
        }
        if receipt is not None:
            receipt["files_created"].append(record)
        return record

    def locate_file(self, path: str, receipt: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Deterministic discovery of a file."""
        resolved = self.boundary.resolve_path(path)
        if not os.path.exists(resolved):
            return None
        
        digest = compute_file_digest(resolved)
        size = os.path.getsize(resolved)
        record = {
            "path": resolved,
            "relative_path": os.path.relpath(resolved, self.boundary.root_dir),
            "size": size,
            "sha256": digest,
            "is_dir": os.path.isdir(resolved),
        }
        if receipt is not None:
            receipt["files_read"].append(record)
        return record

    def read_file(self, path: str, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Deterministic read of file content."""
        resolved = self.boundary.check_read_permission(path)
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        record = {
            "path": resolved,
            "relative_path": os.path.relpath(resolved, self.boundary.root_dir),
            "content": content,
            "size": len(content.encode("utf-8")),
            "sha256": digest,
        }
        if receipt is not None:
            receipt["files_read"].append(record)
        return record

    def replace_file(self, path: str, content: str, verify: bool = True, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Atomically replace content of a file."""
        resolved = self.boundary.check_write_permission(path)
        before_digest = compute_file_digest(resolved)

        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(resolved), prefix=".sym_tmp_")
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, resolved)
            sync_directory(os.path.dirname(resolved))
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        if verify:
            with open(resolved, "r", encoding="utf-8") as f:
                read_back = f.read()
            if read_back != content:
                raise IOError(f"Read-back verification failed for '{resolved}'")

        after_digest = compute_file_digest(resolved)
        record = {
            "path": resolved,
            "relative_path": os.path.relpath(resolved, self.boundary.root_dir),
            "before_sha256": before_digest,
            "after_sha256": after_digest,
            "size": len(content.encode("utf-8")),
        }
        if receipt is not None:
            receipt["files_modified"].append(record)
        return record

    def append_file(self, path: str, content: str, verify: bool = True, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Atomically append content to an existing file."""
        resolved = self.boundary.check_write_permission(path)
        existing = ""
        if os.path.exists(resolved):
            with open(resolved, "r", encoding="utf-8") as f:
                existing = f.read()
        new_content = existing + content
        return self.replace_file(path, new_content, verify=verify, receipt=receipt)

    def make_directory(self, path: str, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a directory within the sandbox."""
        resolved = self.boundary.check_write_permission(path)
        os.makedirs(resolved, exist_ok=True)
        sync_directory(os.path.dirname(resolved))
        record = {
            "path": resolved,
            "relative_path": os.path.relpath(resolved, self.boundary.root_dir),
            "type": "directory",
        }
        if receipt is not None:
            receipt["files_created"].append(record)
        return record

    def list_directory(self, path: str = ".", receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Deterministic directory listing."""
        resolved = self.boundary.check_read_permission(path)
        entries = sorted(os.listdir(resolved))
        record = {
            "path": resolved,
            "relative_path": os.path.relpath(resolved, self.boundary.root_dir),
            "entries": entries,
            "count": len(entries),
        }
        if receipt is not None:
            receipt["files_read"].append(record)
        return record

    def copy_file(self, src: str, dst: str, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Copy a file within the sandbox."""
        resolved_src = self.boundary.check_read_permission(src)
        resolved_dst = self.boundary.check_write_permission(dst)
        if os.path.isdir(resolved_dst):
            resolved_dst = self.boundary.check_write_permission(os.path.join(resolved_dst, os.path.basename(resolved_src)))
        os.makedirs(os.path.dirname(resolved_dst), exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(resolved_dst), prefix='.sym_tmp_')
        try:
            with os.fdopen(temp_fd, 'wb') as out, open(resolved_src, 'rb') as source:
                shutil.copyfileobj(source, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp_path, resolved_dst)
            sync_directory(os.path.dirname(resolved_dst))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        digest = compute_file_digest(resolved_dst)
        record = {
            "src": resolved_src,
            "dst": resolved_dst,
            "sha256": digest,
        }
        if receipt is not None:
            receipt["files_created"].append({"path": resolved_dst, "sha256": digest})
        return record

    def move_file(self, src: str, dst: str, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Move / rename a file within the sandbox."""
        resolved_src = self.boundary.check_read_permission(src)
        resolved_dst = self.boundary.check_write_permission(dst)
        if os.path.isdir(resolved_dst):
            resolved_dst = self.boundary.check_write_permission(os.path.join(resolved_dst, os.path.basename(resolved_src)))
        os.makedirs(os.path.dirname(resolved_dst), exist_ok=True)
        os.replace(resolved_src, resolved_dst)
        sync_directory(os.path.dirname(resolved_src))
        sync_directory(os.path.dirname(resolved_dst))
        digest = compute_file_digest(resolved_dst)
        record = {
            "src": resolved_src,
            "dst": resolved_dst,
            "sha256": digest,
        }
        if receipt is not None:
            receipt["files_removed"].append({"path": resolved_src})
            receipt["files_created"].append({"path": resolved_dst, "sha256": digest})
        return record

    def remove_file(self, path: str, authorized: bool = False, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Destructive removal, separately gated by explicit authorization."""
        if not authorized:
            raise PermissionError("Destructive file removal is gated and requires explicit authorization")
        resolved = self.boundary.check_write_permission(path)
        if os.path.isdir(resolved):
            shutil.rmtree(resolved)
        elif os.path.exists(resolved):
            os.remove(resolved)
        record = {"path": resolved, "removed": True}
        if receipt is not None:
            receipt["files_removed"].append(record)
        return record

    def flush_file(self, path: Optional[str] = None, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Flush and sync filesystem state."""
        if path:
            resolved = self.boundary.resolve_path(path)
            if os.path.exists(resolved):
                fd = os.open(resolved, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                record = {"path": resolved, "flushed": True}
                if receipt is not None:
                    receipt["validation_checks"].append(f"fsync({resolved})")
                    receipt["validation_results"].append(True)
                return record
        # Sync entire user files directory
        fd = os.open(self.boundary.root_dir, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return {"path": self.boundary.root_dir, "flushed": True}
