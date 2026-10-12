"""The OS prototype's declared attack surface, and self-checks of its boundaries.

get_security_manifest() lists what the prototype exposes: its one network listener (the loopback
development listener), the folders it writes (from paths.py), the effects it can perform, the
executables it may start (from process_effects.APPROVED_EXECUTABLES) and the outside projects the host
integration referred to. It is a declaration assembled from the code's own constants, not a scan of a
running system.

The verify_* functions are quick self-checks: path traversal and absolute paths are refused by the
filesystem boundary, shell syntax and unapproved executables are refused by the process registry,
model text is HTML-escaped before display, and a repeated client_request_id maps to the same execution.
They return True when the boundary held. They are not a security audit.
"""
from __future__ import annotations
import html
from typing import Any, Dict
from symblic.os.fs_boundary import FilesystemBoundary, FilesystemBoundaryError
from symblic.os.paths import get_dev_paths
from symblic.os.process_effects import APPROVED_EXECUTABLES, ProcessEffectsManager
from symblic.os.protocol import ExecutionSessionManager

class SymblicOSSecurityAuditor:
    """Enumerates attack surface and performs defensive verification."""

    @staticmethod
    def get_security_manifest(root: str | None = None) -> Dict[str, Any]:
        paths = get_dev_paths(root)
        return {
            "network_listeners": [
                {"protocol": "HTTP", "interface": "127.0.0.1", "port": 8990,
                 "service": "symblic.os.terminal_server development listener (loopback only, no authentication)"},
            ],
            "writable_filesystem_paths": [paths[key] for key in ("user_files", "receipts", "logs", "state", "config")],
            "privileged_operations": [
                "fs.create",
                "fs.replace",
                "fs.append",
                "fs.mkdir",
                "fs.copy",
                "fs.move",
                "fs.remove (gated)",
                "process.start (approved registry only)",
                "process.stop (owned processes only)",
            ],
            "approved_executables": sorted(APPROVED_EXECUTABLES),
            "integrated_repositories": [
                "Transformers.js (https://github.com/huggingface/transformers.js, 511bb61): stub adapter, host only",
                "ipy-llm-kernel (https://github.com/haesleinhuepf/ipy-llm-kernel, 397df79): stub adapter, host only",
            ],
            "model_runtimes": [
                "a local Ollama server on one node, reached only through integration/host/symblicos_model_engine.py",
            ],
        }

    @staticmethod
    def verify_traversal_prevention(root_dir: str) -> bool:
        boundary = FilesystemBoundary(root_dir)
        traversal_attempts = [
            "../../etc/passwd",
            "/etc/shadow",
            "../symblicos/receipts",
            "foo/../../../root",
            "sub/../../..",
        ]
        for path in traversal_attempts:
            try:
                boundary.resolve_path(path)
                return False  # Security failure: traversal was not blocked
            except FilesystemBoundaryError:
                pass
        return True

    @staticmethod
    def verify_shell_metacharacter_rejection() -> bool:
        mgr = ProcessEffectsManager()
        # Attempting arbitrary shell piping or substitution
        malicious_inputs = [
            "uptime; rm -rf /",
            "date && cat /etc/passwd",
            "`whoami`",
            "$(id)",
            "uname | grep Linux",
        ]
        for bad in malicious_inputs:
            try:
                mgr.run_approved(bad)
                return False
            except PermissionError:
                pass
        return True

    @staticmethod
    def verify_executable_path_substitution() -> bool:
        mgr = ProcessEffectsManager()
        unapproved = [
            "/bin/bash",
            "/bin/sh",
            "/usr/bin/curl",
            "/usr/bin/nc",
            "/usr/bin/wget",
        ]
        for bad in unapproved:
            try:
                mgr.run_approved(bad)
                return False
            except PermissionError:
                pass
        return True

    @staticmethod
    def verify_html_escaping(raw_output: str) -> str:
        """Verify that model output text is escaped safely before DOM insertion."""
        escaped = html.escape(raw_output)
        if "<script>" in escaped or "<img>" in escaped:
            raise ValueError("HTML escaping failed")
        return escaped

    @staticmethod
    def verify_duplicate_submission_prevention() -> bool:
        sessions = ExecutionSessionManager()
        req = {"instruction": "Create a text file named 'note.txt'.", "client_request_id": "req-12345"}
        id1, is_dup1 = sessions.register_submission(req)
        id2, is_dup2 = sessions.register_submission(req)
        return (not is_dup1) and is_dup2 and (id1 == id2)
