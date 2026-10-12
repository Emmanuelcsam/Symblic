"""The OS prototype's bridge to the Symblic compiler: check source, never execute it.

SymblicCompilerBridge().compile(source) parses and checks Symblic source with the kernel's own parser
and checker (symblic.kernel.language.parse and .check; no grammar is re-implemented here) and returns
{'ok', 'exit_code', 'source', 'compiled_repr', 'plan', 'diagnostics', 'runtime_version',
'runtime_digest'}. Diagnostics carry a severity, a message, a line and a column. The terminal engine
(terminal_server.py) uses it for instructions that are Symblic source: such an instruction is compiled
and reported, NOT run. Depends on symblic.kernel.language and symblic.os.receipts (for the runtime
digest).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from symblic.kernel import language as S
from symblic.os.receipts import RUNTIME_FILE, compute_runtime_digest

class CompilationError(ValueError):
    """Raised when Symblic compilation or validation fails."""
    def __init__(self, message: str, diagnostics: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.diagnostics = diagnostics or []

class SymblicCompilerBridge:
    """Invokes authoritative Symblic compiler/parser programmatically without reimplementing grammar."""

    def __init__(self, runtime_file: Optional[str] = None):
        self.runtime_file = runtime_file or RUNTIME_FILE
        self.runtime_version = getattr(S, "VERSION", "2.5")
        self.runtime_digest = compute_runtime_digest(self.runtime_file)

    def compile(self, source: str) -> Dict[str, Any]:
        """Compile and check Symblic source code.
        
        Returns a dictionary containing:
          - ok: bool
          - exit_code: int (0 on success, 1 on failure)
          - source: str (preserved exact user source)
          - compiled_repr: str / dict
          - plan: list of statement steps
          - diagnostics: list of error/warning dicts with line/col
          - runtime_version: str
          - runtime_digest: str
        """
        exact_source = source
        diagnostics = []

        try:
            # 1. Parse with the kernel's parser (raises SymblicError on a syntax error)
            S.parse(source)
            # 2. Check with the kernel's semantic checker
            check_result = S.check(source)
            
            errors = check_result.get("errors") or []
            warnings = check_result.get("warnings") or []

            if errors:
                for err in errors:
                    diag = {
                        "severity": "error",
                        "message": str(err.get("message") or err),
                        "line": err.get("line", 1),
                        "col": err.get("col", 1),
                    }
                    diagnostics.append(diag)
                return {
                    "ok": False,
                    "exit_code": 1,
                    "source": exact_source,
                    "compiled_repr": None,
                    "plan": None,
                    "diagnostics": diagnostics,
                    "runtime_version": self.runtime_version,
                    "runtime_digest": self.runtime_digest,
                }

            for warn in warnings:
                diagnostics.append({
                    "severity": "warning",
                    "message": str(warn.get("message") or warn),
                    "line": warn.get("line", 1),
                    "col": warn.get("col", 1),
                })

            plan = check_result.get("plan", [])
            return {
                "ok": True,
                "exit_code": 0,
                "source": exact_source,
                "compiled_repr": {
                    "name": check_result.get("name", "Untitled"),
                    "profile": check_result.get("profile", {}),
                    "statements_count": len(plan),
                },
                "plan": plan,
                "diagnostics": diagnostics,
                "runtime_version": self.runtime_version,
                "runtime_digest": self.runtime_digest,
            }

        except S.SymblicError as exc:
            line = getattr(exc, "line", 1)
            col = getattr(exc, "col", 1)
            diag = {
                "severity": "error",
                "message": str(exc),
                "line": line,
                "col": col,
            }
            return {
                "ok": False,
                "exit_code": 1,
                "source": exact_source,
                "compiled_repr": None,
                "plan": None,
                "diagnostics": [diag],
                "runtime_version": self.runtime_version,
                "runtime_digest": self.runtime_digest,
            }
        except Exception as exc:
            diag = {
                "severity": "error",
                "message": f"Compilation failed: {str(exc)}",
                "line": 1,
                "col": 1,
            }
            return {
                "ok": False,
                "exit_code": 1,
                "source": exact_source,
                "compiled_repr": None,
                "plan": None,
                "diagnostics": [diag],
                "runtime_version": self.runtime_version,
                "runtime_digest": self.runtime_digest,
            }
