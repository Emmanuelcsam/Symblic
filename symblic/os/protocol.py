"""The terminal's wire protocol: JSON messages between a client and the OS terminal engine.

A client sends a submit request (instruction, client_request_id, mode); the engine answers with an ack
carrying its execution_id, numbered progress events, and one terminal event (terminal_success or
terminal_failure) that carries the durable receipt (symblic/os/receipts.py). A reconnecting client asks
by execution_id. ExecutionSessionManager is an in-memory helper that binds a client_request_id to one
instruction and mode and hands out increasing sequence numbers; the real terminal engine
(symblic/os/terminal_server.py) gets its duplicate protection from durable receipts instead.
Pure Python, no I/O."""
from __future__ import annotations
import json
import threading
import time
import uuid
from typing import Any, Dict, Optional

class TerminalProtocolError(ValueError):
    """Raised when wire message encoding or validation fails."""
    pass

def encode_request(
    instruction: str,
    client_request_id: Optional[str] = None,
    mode: str = "auto",
) -> Dict[str, Any]:
    """Encode client submission request object."""
    if not isinstance(instruction, str):
        raise TerminalProtocolError("instruction must be a string")
    return {
        "type": "submit",
        "instruction": instruction,
        "client_request_id": client_request_id or f"req-{uuid.uuid4().hex[:12]}",
        "mode": mode,
        "timestamp": time.time(),
    }

def encode_ack(
    execution_id: str,
    client_request_id: str,
    instruction: str,
) -> Dict[str, Any]:
    """Encode initial server acknowledgement with assigned execution_id."""
    return {
        "type": "ack",
        "execution_id": execution_id,
        "client_request_id": client_request_id,
        "instruction": instruction,
        "timestamp": time.time(),
    }

def encode_event(
    execution_id: str,
    sequence: int,
    stage: str,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Encode monotonically ordered progress event."""
    return {
        "type": "progress",
        "execution_id": execution_id,
        "sequence": sequence,
        "stage": stage,
        "message": message,
        "payload": payload or {},
        "timestamp": time.time(),
    }

def encode_terminal_success(
    execution_id: str,
    sequence: int,
    receipt: Dict[str, Any],
    summary: str = "Operation completed",
) -> Dict[str, Any]:
    """Encode terminal success event with durable receipt."""
    return {
        "type": "terminal_success",
        "execution_id": execution_id,
        "sequence": sequence,
        "summary": summary,
        "receipt": receipt,
        "timestamp": time.time(),
    }

def encode_terminal_failure(
    execution_id: str,
    sequence: int,
    receipt: Dict[str, Any],
    error_type: str,
    error_message: str,
) -> Dict[str, Any]:
    """Encode terminal failure event with failure diagnostics."""
    return {
        "type": "terminal_failure",
        "execution_id": execution_id,
        "sequence": sequence,
        "error_type": error_type,
        "error_message": error_message,
        "receipt": receipt,
        "timestamp": time.time(),
    }

def encode_reconnect_request(execution_id: str) -> Dict[str, Any]:
    """Encode reconnect query to retrieve receipt and status of existing execution."""
    return {
        "type": "reconnect_query",
        "execution_id": execution_id,
        "timestamp": time.time(),
    }

class ExecutionSessionManager:
    """In-memory protocol helper; terminal execution uses durable receipt locks."""

    def __init__(self):
        self._seen_requests: dict[str, str] = {}  # client_request_id -> execution_id
        self._execution_results: dict[str, dict] = {} # execution_id -> final event
        self._execution_sequences: dict[str, int] = {} # execution_id -> latest sequence
        self._request_payloads: dict[str, str] = {}
        self._lock = threading.RLock()

    def register_submission(self, req: Dict[str, Any]) -> tuple[str, bool]:
        """Returns (execution_id, is_duplicate). If duplicate, returns existing id."""
        client_req_id = req.get("client_request_id")
        payload = json.dumps({key: req.get(key) for key in ('instruction', 'mode')}, sort_keys=True)
        with self._lock:
            if client_req_id and client_req_id in self._seen_requests:
                if self._request_payloads[client_req_id] != payload:
                    raise TerminalProtocolError('Request id belongs to a different instruction or mode')
                return self._seen_requests[client_req_id], True
            exec_id = f"exec-{uuid.uuid4().hex[:16]}"
            if client_req_id:
                self._seen_requests[client_req_id] = exec_id
                self._request_payloads[client_req_id] = payload
            self._execution_sequences[exec_id] = 0
            return exec_id, False

    def next_sequence(self, execution_id: str) -> int:
        with self._lock:
            seq = self._execution_sequences.get(execution_id, 0) + 1
            self._execution_sequences[execution_id] = seq
            return seq

    def record_final(self, execution_id: str, final_event: Dict[str, Any]) -> None:
        with self._lock:
            self._execution_results[execution_id] = final_event

    def get_final(self, execution_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._execution_results.get(execution_id)
