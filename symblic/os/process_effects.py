"""Process effects of the OS prototype: run only approved executables, stop only processes it started.

APPROVED_EXECUTABLES maps a short name to one executable path; run_approved(name, args) runs it with an
argument list (never a shell), a timeout, and records it in a receipt. A name that is not in the
registry, or a path that is not one of its values, is refused, so shell syntax such as "uptime; rm -rf /"
is just an unknown name. terminate_owned(pid) stops only processes this manager started.
inspect_processes() lists running processes with `ps` (read only). Standard library only."""
from __future__ import annotations
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

APPROVED_EXECUTABLES = {
    "uptime": "/usr/bin/uptime",
    "df": "/usr/bin/df",
    "uname": "/usr/bin/uname",
    "free": "/usr/bin/free",
    "date": "/usr/bin/date",
    "whoami": "/usr/bin/whoami",
    "hostname": "/usr/bin/hostname",
    "python3": "/usr/bin/python3",
    "node": "/usr/bin/node",
    "symblic": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tools", "symblic")),
}

class ProcessEffectsManager:
    """Manages approved process execution with PID tracking and bounded termination."""

    def __init__(self, approved_registry: Optional[Dict[str, str]] = None):
        self.registry = dict(APPROVED_EXECUTABLES)
        if approved_registry:
            self.registry.update(approved_registry)
        self._owned_processes: dict[int, subprocess.Popen] = {}

    def inspect_processes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Deterministic inspection of running host processes."""
        cmd = ["ps", "-eo", "pid,user,comm,args", "--no-headers"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        procs = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 3)
            if len(parts) >= 3:
                pid = int(parts[0])
                user = parts[1]
                comm = parts[2]
                args = parts[3] if len(parts) > 3 else comm
                # Filter kernel threads
                if not args.startswith("["):
                    procs.append({
                        "pid": pid,
                        "user": user,
                        "comm": comm,
                        "args": args,
                        "owned_by_symblicos": pid in self._owned_processes,
                    })
                    if len(procs) >= limit:
                        break
        return procs

    def run_approved(
        self,
        command_name: str,
        args: Optional[List[str]] = None,
        timeout: float = 30.0,
        receipt: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an approved process with structured argument arrays (no shell)."""
        if command_name not in self.registry:
            resolved = shutil.which(command_name)
            # Only allow if resolved path is explicitly in registry values
            if not resolved or resolved not in self.registry.values():
                raise PermissionError(f"Process '{command_name}' is not in the approved executable registry")
            exe_path = resolved
        else:
            exe_path = self.registry[command_name]

        if not os.path.exists(exe_path):
            found = shutil.which(command_name)
            if found:
                exe_path = found
            else:
                raise FileNotFoundError(f"Approved executable '{exe_path}' not found on host")

        arg_list = [exe_path] + (args or [])
        start_t = time.time()
        
        # Execute without shell, structured arguments only
        proc = subprocess.Popen(
            arg_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        self._owned_processes[proc.pid] = proc

        if receipt is not None:
            proc_rec = {
                "executable": exe_path,
                "arguments": args or [],
                "pid": proc.pid,
                "start_time": start_t,
            }
            receipt["processes_started"].append(proc_rec)

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            rc = -9
        finally:
            self._owned_processes.pop(proc.pid, None)

        record = {
            "executable": exe_path,
            "args": args or [],
            "pid": proc.pid,
            "exit_code": rc,
            "stdout": stdout,
            "stderr": stderr,
            "duration_s": time.time() - start_t,
        }

        if receipt is not None:
            receipt["stdout"] += stdout
            receipt["stderr"] += stderr

        return record

    def terminate_owned(self, pid: int, receipt: Optional[Dict[str, Any]] = None) -> bool:
        """Terminate a process started by SymblicOS. Rejects termination of unrelated host processes."""
        if pid not in self._owned_processes:
            raise PermissionError(f"PID {pid} is not owned by SymblicOS. Unrelated host processes cannot be terminated.")
        
        proc = self._owned_processes.pop(pid)
        try:
            proc.terminate()
            proc.wait(timeout=5.0)
        except Exception:
            proc.kill()
            proc.wait(timeout=2.0)
            
        if receipt is not None:
            receipt["processes_stopped"].append({"pid": pid, "terminated": True})
        return True
