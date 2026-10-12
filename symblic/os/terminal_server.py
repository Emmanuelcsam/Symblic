"""The OS prototype's terminal engine, and a loopback-only development listener for it.

SymblicOSTerminalEngine(dev_root).execute_instruction(text, client_request_id) is the core of the OS
prototype. It accepts two kinds of instruction:

  * a whole English sentence from the fixed list in intake.py ("Create a text file named "a.txt"."),
    executed as one bounded effect: a file effect inside <root>/user_files (file_effects.py), a
    process listing (process_effects.py), a model inventory (only when one was passed in), or
    system vitals;
  * Symblic source (starting with program, let, ask, act, observe, assert or show), which is only
    compiled and checked (compiler_bridge.py), never run.

Anything else is refused with no side effect. Every instruction gets a durable receipt
(receipts.py) written before any effect; the execution id is derived from the client_request_id, so
the same request after a crash or from a second engine object returns the stored result instead of
repeating the effect, and an interrupted one is reported, never replayed. One effect runs at a time
(a file lock in <root>/state).

run_server() starts a development HTTP listener on 127.0.0.1 (port 8990 by default) with three JSON
routes: GET /api/symblicos/vitals, GET /api/symblicos/receipt?id=..., POST
/api/symblicos/terminal/submit. It refuses any request that is not from loopback, names another
Host, carries a foreign Origin, or was forwarded by a tunnel (a CF-RAY header): a loopback socket is
not proof of a local user when a tunnel connects from localhost. It has no authentication and serves
no web page; it is meant for local experiments only.

Run it: python3 -m symblic.os.terminal_server   (state under SYMBLICOS_ROOT, default ~/symblicos)
"""
from __future__ import annotations
import http.server
import fcntl
import hashlib
import ipaddress
import re
import uuid
import json
import os
import socket
import socketserver
import time
import urllib.parse
from typing import Any, Dict, Optional

from symblic.os.paths import ensure_dev_directories
from symblic.os.receipts import create_receipt, store_receipt, get_receipt, compute_runtime_digest
from symblic.os.protocol import (
    encode_terminal_success,
    encode_terminal_failure,
)
from symblic.os.compiler_bridge import SymblicCompilerBridge
from symblic.os.intake import parse_imperative_sentence
from symblic.os.fs_boundary import FilesystemBoundary
from symblic.os.file_effects import FileEffectsManager
from symblic.os.process_effects import ProcessEffectsManager

DEFAULT_TERMINAL_PORT = 8990

class SymblicOSTerminalEngine:
    """Executes bounded OS instructions with durable receipts (see the module docstring).

    dev_root         the state root (paths.default_root() when None); its tree is created.
    model_inventory  optional callable returning a JSON-serializable model inventory for the
                     "inspect models" sentence; without one that sentence is refused.
    """

    def __init__(self, dev_root: Optional[str] = None, model_inventory=None):
        self.paths = ensure_dev_directories(dev_root)
        self.model_inventory = model_inventory
        self.boundary = FilesystemBoundary(self.paths["user_files"])
        self.file_effects = FileEffectsManager(self.boundary)
        self.proc_effects = ProcessEffectsManager()
        self.compiler = SymblicCompilerBridge()
        self.hostname = socket.gethostname()
        self.runtime_version = self.compiler.runtime_version
        self.runtime_digest = compute_runtime_digest()

    def get_history(self, limit=100):
        """Retained receipts, including interrupted operations; never re-execute them."""
        from pathlib import Path
        files = sorted(Path(self.paths["receipts"]).glob("exec-*.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)[:limit]
        return [row for path in files if (row := get_receipt(path.stem, self.paths["receipts"]))]

    def execute_instruction(self, instruction: str, client_request_id: Optional[str] = None) -> Dict[str, Any]:
        """Persist exact request before effects; cross-process duplicate calls never repeat."""
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 60000 or "\0" in instruction:
            raise ValueError("Enter an instruction between 1 and 60000 characters")
        request_id = client_request_id or "req-" + uuid.uuid4().hex
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", request_id):
            raise ValueError("Invalid client_request_id")
        exec_id = "exec-" + hashlib.sha256(request_id.encode()).hexdigest()[:32]
        lock_path = os.path.join(self.paths["receipts"], exec_id + ".lock")
        with open(lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            receipt_path = os.path.join(self.paths["receipts"], exec_id + ".json")
            if os.path.exists(receipt_path):
                receipt = get_receipt(exec_id, self.paths["receipts"])
                if receipt is None:
                    raise ValueError("Receipt is unreadable; refusing to replay the operation")
                if receipt["original_instruction"] != instruction:
                    raise ValueError("This request id belongs to a different instruction")
                if receipt["result_status"] == "success":
                    return encode_terminal_success(exec_id, 2, receipt, receipt["stdout"])
                error = receipt["stderr"] or "Prior execution was interrupted. Inspect durable files; it will not be replayed."
                return encode_terminal_failure(exec_id, 2, receipt, receipt["result_status"], error)
            with open(os.path.join(self.paths['state'], 'effects.lock'), 'a') as effects_lock:
                fcntl.flock(effects_lock, fcntl.LOCK_EX)
                return self._execute_once(instruction, request_id, exec_id)

    def _execute_once(self, instruction, client_request_id, exec_id):
        receipt = create_receipt(
            original_instruction=instruction,
            target_machine_id=self.hostname,
            runtime_version=self.runtime_version,
            runtime_digest=self.runtime_digest,
            execution_id=exec_id,
        )

        receipt["client_request_id"] = client_request_id
        store_receipt(receipt, self.paths["receipts"])

        clean_text = instruction.strip()
        
        # Check if it is an imperative English instruction
        intent_obj = parse_imperative_sentence(clean_text)

        # Check if it is explicit Symblic syntax
        is_symblic_syntax = any(
            clean_text.startswith(kw) for kw in ("program ", "let ", "ask ", "act ", "observe ", "assert ", "show ")
        )

        if not is_symblic_syntax and intent_obj.intent != "unsupported":
            receipt["action_category"] = f"imperative_{intent_obj.intent}"
            receipt["normalized_instruction"] = intent_obj.intent
            receipt["intent"] = intent_obj.to_dict()
            receipt["validation_checks"].append("Bounded OS intent; executed by filesystem/process adapter, not a compiled Symblic program")

            try:
                if intent_obj.intent == "create_file":
                    res = self.file_effects.create_file(intent_obj.path or "file.txt", content="", receipt=receipt)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = f"Created file '{res['relative_path']}' ({res['size']} bytes)"
                    receipt["final_result"] = res
                elif intent_obj.intent == "locate_file":
                    res = self.file_effects.locate_file(intent_obj.path or "file.txt", receipt=receipt)
                    if res:
                        receipt["result_status"] = "success"
                        receipt["stdout"] = f"Located '{res['relative_path']}' (size: {res['size']} bytes, sha256: {res['sha256']})"
                        receipt["final_result"] = res
                    else:
                        receipt["result_status"] = "runtime_failure"
                        receipt["stderr"] = f"File '{intent_obj.path}' not found."
                        receipt["final_result"] = None
                elif intent_obj.intent == "read_file":
                    res = self.file_effects.read_file(intent_obj.path or "file.txt", receipt=receipt)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = res["content"]
                    receipt["final_result"] = res
                elif intent_obj.intent == "write_file":
                    res = self.file_effects.replace_file(
                        intent_obj.path or "file.txt",
                        content=intent_obj.payload or "",
                        verify=True,
                        receipt=receipt,
                    )
                    receipt["result_status"] = "success"
                    receipt["stdout"] = f"Updated '{res['relative_path']}' ({res['size']} bytes, sha256: {res['after_sha256']})"
                    receipt["final_result"] = res
                elif intent_obj.intent == "append_file":
                    res = self.file_effects.append_file(
                        intent_obj.path or "file.txt",
                        content=intent_obj.payload or "",
                        verify=True,
                        receipt=receipt,
                    )
                    receipt["result_status"] = "success"
                    receipt["stdout"] = f"Appended to '{res['relative_path']}' ({res['size']} bytes)"
                    receipt["final_result"] = res
                elif intent_obj.intent == "make_directory":
                    res = self.file_effects.make_directory(intent_obj.path or "dir", receipt=receipt)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = f"Created directory '{res['relative_path']}'"
                    receipt["final_result"] = res
                elif intent_obj.intent == "list_directory":
                    res = self.file_effects.list_directory(intent_obj.path or ".", receipt=receipt)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = "\n".join(res["entries"]) if res["entries"] else "(empty directory)"
                    receipt["final_result"] = res
                elif intent_obj.intent == "copy_file":
                    res = self.file_effects.copy_file(intent_obj.path or "", intent_obj.destination_path or "", receipt=receipt)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = f"Copied '{intent_obj.path}' to '{intent_obj.destination_path}'"
                    receipt["final_result"] = res
                elif intent_obj.intent == "move_file":
                    res = self.file_effects.move_file(intent_obj.path or "", intent_obj.destination_path or "", receipt=receipt)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = f"Moved '{intent_obj.path}' to '{intent_obj.destination_path}'"
                    receipt["final_result"] = res
                elif intent_obj.intent == "remove_file":
                    # The typed sentence itself is the explicit authorization the destructive
                    # adapter gates on; the receipt records it verbatim under "intent".
                    located = self.file_effects.locate_file(intent_obj.path or "", receipt=None)
                    if not located:
                        receipt["result_status"] = "runtime_failure"
                        receipt["stderr"] = f"File '{intent_obj.path}' not found."
                        receipt["final_result"] = None
                    elif located.get("is_dir"):
                        receipt["result_status"] = "validation_failure"
                        receipt["stderr"] = "The bounded delete intent covers files only; directories are not removed."
                    else:
                        res = self.file_effects.remove_file(intent_obj.path or "", authorized=True, receipt=receipt)
                        receipt["result_status"] = "success"
                        receipt["stdout"] = f"Removed '{located['relative_path']}' (sha256: {located['sha256']})"
                        receipt["final_result"] = res
                elif intent_obj.intent == "flush_file":
                    res = self.file_effects.flush_file(intent_obj.path, receipt=receipt)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = f"Flushed persistent changes to disk ({res['path']})"
                    receipt["final_result"] = res
                elif intent_obj.intent == "inspect_process":
                    res = self.proc_effects.inspect_processes(limit=20)
                    receipt["result_status"] = "success"
                    receipt["stdout"] = "\n".join(f"{p['pid']}\t{p['user']}\t{p['comm']}\t{p['args'][:50]}" for p in res)
                    receipt["final_result"] = res
                elif intent_obj.intent == "inspect_system":
                    vitals = {"hostname": self.hostname, "runtime": self.runtime_version, "time": time.ctime()}
                    receipt["result_status"] = "success"
                    receipt["stdout"] = json.dumps(vitals, indent=2)
                    receipt["final_result"] = vitals
                elif intent_obj.intent == "inspect_model":
                    if self.model_inventory is None:
                        receipt["result_status"] = "validation_failure"
                        receipt["stderr"] = ("No model inventory is configured for this engine "
                                             "(SymblicOSTerminalEngine(model_inventory=...)).")
                    else:
                        models = self.model_inventory()
                        receipt["result_status"] = "success"
                        receipt["stdout"] = json.dumps(models, ensure_ascii=False)
                        receipt["final_result"] = {"nodes": models, "scope": "Inventory; no health inference performed"}
                else:
                    receipt["result_status"] = "validation_failure"
                    receipt["stderr"] = f"Intent '{intent_obj.intent}' execution unhandled."
            except Exception as exc:
                receipt["result_status"] = "runtime_failure"
                receipt["stderr"] = str(exc)

        elif is_symblic_syntax:
            receipt["action_category"] = "symblic_compiler"
            compile_res = self.compiler.compile(clean_text)
            if not compile_res["ok"]:
                receipt["result_status"] = "validation_failure"
                receipt["stderr"] = "\n".join(f"[{d['severity']}] line {d.get('line')}:{d.get('col')} {d['message']}" for d in compile_res["diagnostics"])
            else:
                receipt["result_status"] = "success"
                receipt["compiled_symblic"] = json.dumps(compile_res["compiled_repr"])
                receipt["stdout"] = f"Symblic compiled successfully ({len(compile_res['plan'])} statements)"
                receipt["final_result"] = compile_res["compiled_repr"]
        else:
            # Unsupported instruction -> produce zero side effects
            receipt["action_category"] = "unsupported_instruction"
            receipt["result_status"] = "validation_failure"
            receipt["stderr"] = f"Unsupported instruction: '{instruction}'. Expected valid Symblic source or bounded imperative English sentence."

        receipt["completion_timestamp"] = time.time()
        store_receipt(receipt, self.paths["receipts"])

        final_seq = 2
        if receipt["result_status"] == "success":
            final_event = encode_terminal_success(exec_id, final_seq, receipt, summary=receipt["stdout"])
        else:
            err_kind = "validation_failure" if receipt["result_status"] == "validation_failure" else "runtime_failure"
            final_event = encode_terminal_failure(exec_id, final_seq, receipt, err_kind, receipt["stderr"])

        return final_event


class SymblicOSTerminalHandler(http.server.BaseHTTPRequestHandler):
    """The development listener's JSON routes (loopback only; see the module docstring)."""

    engine: Optional[SymblicOSTerminalEngine] = None
    ROUTES = {'GET': ['/api/symblicos/vitals', '/api/symblicos/receipt?id=EXECUTION_ID'],
              'POST': ['/api/symblicos/terminal/submit {"instruction": ..., "client_request_id": ...}']}

    def _local_request(self):
        """The development listener has no authentication: loopback clients only, with a matching Host,
        no foreign Origin and no tunnel header (a tunnel connects from localhost too)."""
        host = self.headers.get('Host', '')
        try:
            hostname = urllib.parse.urlsplit('http://' + host).hostname
            local = ipaddress.ip_address(self.client_address[0]).is_loopback
            origin = self.headers.get('Origin')
            valid_origin = not origin or urllib.parse.urlsplit(origin).netloc == host
            if local and hostname in ('localhost', '127.0.0.1', '::1') and not self.headers.get('CF-RAY') and valid_origin:
                return True
        except ValueError:
            pass
        self.send_error(403, 'This development listener answers local requests only')
        return False

    def do_GET(self):
        if not self._local_request():
            return
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            body = json.dumps({"service": "symblic-os terminal (development listener)", "routes": self.ROUTES}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/symblicos/vitals":
            vitals = {
                "hostname": self.engine.hostname if self.engine else socket.gethostname(),
                "runtime_version": self.engine.runtime_version if self.engine else None,
                "profile": "Bounded OS commands",
                "status": "online" if self.engine else "uninitialized",
            }
            body = json.dumps(vitals).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/symblicos/receipt":
            qs = urllib.parse.parse_qs(url.query)
            exec_id = qs.get("id", [""])[0]
            if exec_id and self.engine:
                rec = get_receipt(exec_id, self.engine.paths["receipts"])
                if rec:
                    body = json.dumps(rec).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            self.send_error(404, "Receipt not found")
        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        if not self._local_request():
            return
        url = urllib.parse.urlparse(self.path)
        if url.path == "/api/symblicos/terminal/submit":
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self.send_error(400, 'Invalid content length')
                return
            if not 0 < length <= 256000 or self.headers.get_content_type() != 'application/json':
                self.send_error(400, 'A bounded application/json body is required')
                return
            raw_body = self.rfile.read(length)
            try:
                data = json.loads(raw_body.decode("utf-8"))
                instruction = data.get("instruction", "")
                client_id = data.get("client_request_id")
                if self.engine:
                    res = self.engine.execute_instruction(instruction, client_request_id=client_id)
                else:
                    res = {"error": "Engine uninitialized"}
                body = json.dumps(res).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_error(500, str(exc))
        else:
            self.send_error(404, "Endpoint not found")

    def log_message(self, format, *args):
        # Quiet standard HTTP logging
        pass

def run_server(port: int = DEFAULT_TERMINAL_PORT, bind_address: str = "127.0.0.1", dev_root: Optional[str] = None):
    """Serve the engine on loopback until interrupted (development only: no authentication)."""
    if bind_address not in ('127.0.0.1', 'localhost'):
        raise ValueError('The development listener binds loopback only')
    engine = SymblicOSTerminalEngine(dev_root=dev_root)
    SymblicOSTerminalHandler.engine = engine

    server = socketserver.TCPServer((bind_address, port), SymblicOSTerminalHandler)
    server.allow_reuse_address = True
    print(f"SymblicOS terminal server listening on http://{bind_address}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()

if __name__ == "__main__":
    run_server()
