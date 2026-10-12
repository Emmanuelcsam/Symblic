"""Execution receipts: the durable record of every instruction the OS prototype executes.

A receipt is one JSON object with a fixed set of fields (REQUIRED_RECEIPT_FIELDS): the instruction as
given, what it was classified as, the files it created, read, modified and removed, the processes it
started and stopped, the models it invoked, the checks it ran and their results, stdout/stderr, the
result status (in_progress, success, validation_failure, runtime_failure) and the digest of the Symblic
runtime that executed it. A receipt is written BEFORE any effect (status in_progress) and rewritten when
the instruction ends, so an interrupted operation is visible afterwards and is never replayed.

store_receipt writes <receipts_dir>/<execution_id>.json atomically and appends the same object to
<receipts_dir>/receipts.jsonl (an append-only journal, written under an exclusive lock).
Used by symblic/os/terminal_server.py and the other symblic.os modules. Standard library only, plus
symblic.autogen.durable for the atomic write.
"""
from __future__ import annotations
import hashlib
import json
import re
import fcntl
import os
import socket
import time
import uuid
from typing import Any, Dict, Optional
from symblic.autogen.durable import atomic_json

RUNTIME_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "kernel", "language.py"))

REQUIRED_RECEIPT_FIELDS = (
    "action_category",
    "available_model_digests",
    "compiled_symblic",
    "completion_timestamp",
    "execution_id",
    "files_created",
    "files_modified",
    "files_read",
    "files_removed",
    "final_result",
    "model_identifiers",
    "models_invoked",
    "network_endpoints_contacted",
    "normalized_instruction",
    "original_instruction",
    "processes_started",
    "processes_stopped",
    "result_status",
    "runtime_digest",
    "runtime_version",
    "start_timestamp",
    "stderr",
    "stdout",
    "target_machine_id",
    "validation_checks",
    "validation_results",
)

def compute_runtime_digest(runtime_file: Optional[str] = None) -> str:
    """The sha256 of the Symblic language runtime (symblic/kernel/language.py by default), so a receipt
    says exactly which runtime source produced it."""
    if runtime_file is None:
        runtime_file = RUNTIME_FILE
    if os.path.exists(runtime_file):
        with open(runtime_file, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    return "unknown_runtime_digest"

def create_receipt(
    original_instruction: str,
    action_category: str = "general",
    target_machine_id: Optional[str] = None,
    runtime_version: str = "2.5",
    runtime_digest: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> Dict[str, Any]:
    """A new receipt with every required field (status in_progress). The machine id defaults to this
    machine's hostname."""
    if target_machine_id is None:
        target_machine_id = socket.gethostname()
    if execution_id is None:
        execution_id = f"exec-{uuid.uuid4().hex[:16]}"
    if runtime_digest is None:
        runtime_digest = compute_runtime_digest()

    receipt = {
        "action_category": action_category,
        "available_model_digests": {},
        "compiled_symblic": "",
        "completion_timestamp": 0.0,
        "execution_id": execution_id,
        "files_created": [],
        "files_modified": [],
        "files_read": [],
        "files_removed": [],
        "final_result": None,
        "model_identifiers": [],
        "models_invoked": [],
        "network_endpoints_contacted": [],
        "normalized_instruction": original_instruction.strip(),
        "original_instruction": original_instruction,
        "processes_started": [],
        "processes_stopped": [],
        "result_status": "in_progress",
        "runtime_digest": runtime_digest,
        "runtime_version": runtime_version,
        "start_timestamp": time.time(),
        "stderr": "",
        "stdout": "",
        "target_machine_id": target_machine_id,
        "validation_checks": [],
        "validation_results": [],
    }
    return receipt

def validate_receipt_fields(receipt: Dict[str, Any]) -> None:
    """Validate that required receipt fields exist and cannot silently disappear."""
    missing = [f for f in REQUIRED_RECEIPT_FIELDS if f not in receipt]
    if missing:
        raise ValueError(f"Receipt missing required fields: {missing}")

def serialize_receipt(receipt: Dict[str, Any]) -> str:
    """Deterministically serialize receipt to JSON with sorted keys and UTF-8 encoding."""
    validate_receipt_fields(receipt)
    return json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False)

def serialize_receipt_bytes(receipt: Dict[str, Any]) -> bytes:
    """Deterministic UTF-8 byte serialization."""
    return serialize_receipt(receipt).encode("utf-8")

def store_receipt(receipt: Dict[str, Any], receipts_dir: str) -> str:
    """Save receipt to durable storage as an individual file and index in journal."""
    validate_receipt_fields(receipt)
    os.makedirs(receipts_dir, exist_ok=True)
    execution_id = receipt["execution_id"]
    if not isinstance(execution_id, str) or not re.fullmatch(r"exec-[a-f0-9]{16,32}", execution_id):
        raise ValueError("Invalid execution identifier")
    filepath = os.path.join(receipts_dir, execution_id + ".json")
    atomic_json(filepath, receipt)

    # Append to receipt log journal
    journal_path = os.path.join(receipts_dir, "receipts.jsonl")
    compact_json = json.dumps(receipt, sort_keys=True, ensure_ascii=False)
    with open(journal_path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(compact_json + "\n")
        f.flush()
        os.fsync(f.fileno())

    return filepath

def get_receipt(execution_id: str, receipts_dir: str) -> Optional[Dict[str, Any]]:
    """Retrieve durable execution receipt by identifier."""
    if not isinstance(execution_id, str) or not re.fullmatch(r"exec-[a-f0-9]{16,32}", execution_id):
        raise ValueError("Invalid execution identifier")
    filepath = os.path.join(receipts_dir, f"{execution_id}.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            validate_receipt_fields(data)
            return data
    except Exception:
        return None
