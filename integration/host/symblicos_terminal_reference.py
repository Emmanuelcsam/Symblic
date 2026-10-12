"""HOST-ONLY: the pinned reference audit of the original host's terminal page.

Why this file is in integration/host/
    It checks the original host dashboard's terminal.html against a sha256 pinned when the OS
    prototype's terminal was designed, and lists the page's stylesheets, scripts, the behaviors the
    prototype meant to keep and the host back-end features it must not inherit. That page is not part
    of this repository, so audit_current_terminal() raises FileNotFoundError anywhere else. It is kept
    as the written record of those design constraints.
"""
from __future__ import annotations
import hashlib
import os
import re
from typing import Any, Dict

# Initial recorded hash of terminal.html
TERMINAL_HTML_EXPECTED_SHA256 = "2d066afe5fc15149c37c089de16742d23a75135da443a94bb87e9b7dd2619571"

def audit_current_terminal(repo_root: str) -> Dict[str, Any]:
    terminal_path = os.path.join(repo_root, "terminal.html")
    if not os.path.exists(terminal_path):
        raise FileNotFoundError(f"terminal.html not found at {terminal_path}")

    with open(terminal_path, "rb") as f:
        content_bytes = f.read()
    current_sha256 = hashlib.sha256(content_bytes).hexdigest()

    if current_sha256 != TERMINAL_HTML_EXPECTED_SHA256:
        raise ValueError(
            f"terminal.html has changed! Expected {TERMINAL_HTML_EXPECTED_SHA256}, got {current_sha256}"
        )

    content_str = content_bytes.decode("utf-8")

    # Extract stylesheets
    css_deps = re.findall(r'<link\s+rel="stylesheet"\s+href="([^"]+)"', content_str)
    # Extract scripts
    js_deps = re.findall(r'<script\s+src="([^"]+)"', content_str)

    # Visual and interaction behaviors to preserve
    preserved_behaviors = [
        "Dark theme palette and header navigation bar",
        "Connection status badge in header",
        "Single-line primary composer bar with Enter submission",
        "Keyboard navigation and command history (Up/Down arrow traversal)",
        "Mobile responsive touch layout and scrolling",
        "Text escaping to prevent HTML injection",
    ]

    # Backend dependencies that MUST NOT be inherited
    backend_exclusions = [
        "the host's terminal-multiplexer session back end",
        "Raw shell subprocess spawning (/bin/bash execution)",
        "Unauthenticated access header bypasses",
        "Arbitrary shell piping",
    ]

    return {
        "path": terminal_path,
        "byte_size": len(content_bytes),
        "sha256": current_sha256,
        "css_dependencies": css_deps,
        "js_dependencies": js_deps,
        "preserved_behaviors": preserved_behaviors,
        "backend_exclusions": backend_exclusions,
        "byte_identical": True,
    }
