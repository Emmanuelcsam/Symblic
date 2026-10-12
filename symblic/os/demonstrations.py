"""Three scripted demonstrations of the OS terminal engine, each checked on disk afterwards.

ExactNoteDemonstration      four English sentences (create, find, write a fixed text, save) and a
                            byte-for-byte check of the resulting note.txt.
GeneralFileVerification     create, find, read, replace, append, copy, move and list, checked on disk,
                            then the temporary files are removed.
RestartPersistenceVerification
                            a new engine object over the same root finds the earlier receipt and the
                            note unchanged. A model check runs only when a callable is passed in
                            (model_check(name) -> bool); otherwise it is reported as not performed and
                            does not count toward all_verified.

These are demonstrations of the bounded English intake (intake.py), not of language understanding:
the sentences must match its fixed patterns exactly. No model is involved unless one is passed in.
"""
from __future__ import annotations
import hashlib
import os
from typing import Any, Callable, Dict, Optional

from symblic.os.terminal_server import SymblicOSTerminalEngine
from symblic.os.receipts import get_receipt

EXACT_NOTE_PAYLOAD = "this is an example note to prove that the agent can find a file read it and rewrite the data of the file using symblic to control the agent"

class ExactNoteDemonstration:
    """Four sentences, then an independent byte-for-byte check of the note on disk."""

    def __init__(self, engine: SymblicOSTerminalEngine):
        self.engine = engine

    def run(self) -> Dict[str, Any]:
        # 1. Create a text file named "note.txt".
        cmd1 = 'Create a text file named "note.txt".'
        res1 = self.engine.execute_instruction(cmd1)
        if res1.get("type") != "terminal_success":
            raise RuntimeError(f"Step 1 failed: {res1}")
        exec1 = res1["execution_id"]

        # 2. Find "note.txt".
        cmd2 = 'Find "note.txt".'
        res2 = self.engine.execute_instruction(cmd2)
        if res2.get("type") != "terminal_success":
            raise RuntimeError(f"Step 2 failed: {res2}")
        exec2 = res2["execution_id"]

        # 3. Find "note.txt" and inside it write "..."
        cmd3 = f'Find "note.txt" and inside it write "{EXACT_NOTE_PAYLOAD}"'
        res3 = self.engine.execute_instruction(cmd3)
        if res3.get("type") != "terminal_success":
            raise RuntimeError(f"Step 3 failed: {res3}")
        exec3 = res3["execution_id"]

        # 4. Save the file.
        cmd4 = "Save the file."
        res4 = self.engine.execute_instruction(cmd4)
        if res4.get("type") != "terminal_success":
            raise RuntimeError(f"Step 4 failed: {res4}")
        exec4 = res4["execution_id"]

        # Physical disk verification independent of the browser
        physical_path = os.path.join(self.engine.paths["user_files"], "note.txt")
        if not os.path.exists(physical_path):
            raise FileNotFoundError(f"Independent disk check: '{physical_path}' does not exist on disk!")

        with open(physical_path, "rb") as f:
            disk_bytes = f.read()

        expected_bytes = EXACT_NOTE_PAYLOAD.encode("utf-8")
        if disk_bytes != expected_bytes:
            raise ValueError(f"Byte mismatch! Disk has {len(disk_bytes)} bytes, expected {len(expected_bytes)} bytes.")

        final_sha256 = hashlib.sha256(disk_bytes).hexdigest()

        return {
            "verified": True,
            "physical_path": physical_path,
            "byte_length": len(disk_bytes),
            "expected_length": len(expected_bytes),
            "byte_equality": True,
            "final_sha256": final_sha256,
            "execution_ids": [exec1, exec2, exec3, exec4],
            "receipts": {
                "create": exec1,
                "find": exec2,
                "write": exec3,
                "save": exec4,
            },
        }


class GeneralFileVerification:
    """The general file commands on a temporary file, each checked on disk."""

    def __init__(self, engine: SymblicOSTerminalEngine):
        self.engine = engine

    def run(self) -> Dict[str, Any]:
        temp_name = "test_verify_artifact.txt"
        temp_copy = "test_verify_copy.txt"
        temp_moved = "test_verify_moved.txt"

        receipt_ids = []

        # 1. Create file
        r1 = self.engine.execute_instruction(f'Create a text file named "{temp_name}".')
        receipt_ids.append(r1["execution_id"])

        # 2. Find file
        r2 = self.engine.execute_instruction(f'Find "{temp_name}".')
        receipt_ids.append(r2["execution_id"])

        # 3. Read file
        r3 = self.engine.execute_instruction(f'Read "{temp_name}".')
        receipt_ids.append(r3["execution_id"])

        # 4. Replace contents
        r4 = self.engine.execute_instruction(f'Find "{temp_name}" and inside it write "initial_content"')
        receipt_ids.append(r4["execution_id"])

        # 5. Append additional text
        r5 = self.engine.execute_instruction(f'Append " extra_appended" to "{temp_name}"')
        receipt_ids.append(r5["execution_id"])

        # 6. Copy file
        r6 = self.engine.execute_instruction(f'Copy "{temp_name}" to "{temp_copy}"')
        receipt_ids.append(r6["execution_id"])

        # 7. Move file
        r7 = self.engine.execute_instruction(f'Move "{temp_copy}" to "{temp_moved}"')
        receipt_ids.append(r7["execution_id"])

        # 8. List directory
        r8 = self.engine.execute_instruction('List directory "."')
        receipt_ids.append(r8["execution_id"])

        # Direct disk verification
        base_dir = self.engine.paths["user_files"]
        p_orig = os.path.join(base_dir, temp_name)
        p_moved = os.path.join(base_dir, temp_moved)

        with open(p_orig, "r", encoding="utf-8") as f:
            c_orig = f.read()
        with open(p_moved, "r", encoding="utf-8") as f:
            c_moved = f.read()

        assert c_orig == "initial_content extra_appended"
        assert c_moved == "initial_content extra_appended"

        # Cleanup only temporary verification artifacts
        self.engine.file_effects.remove_file(temp_name, authorized=True)
        self.engine.file_effects.remove_file(temp_moved, authorized=True)

        return {
            "verified": True,
            "receipt_ids": receipt_ids,
            "final_clean": not os.path.exists(p_orig) and not os.path.exists(p_moved),
        }


class RestartPersistenceVerification:
    """A new engine over the same root: the earlier receipt and note.txt survive (nothing is recreated)."""

    def __init__(self, dev_root: str, previous_exact_receipts: Dict[str, str],
                 model_check: Optional[Callable[[str], bool]] = None, model_name: str = "llama3.2:1b"):
        self.dev_root = dev_root
        self.previous_receipts = previous_exact_receipts
        self.model_check = model_check
        self.model_name = model_name

    def run(self) -> Dict[str, Any]:
        # Emulate restart: create fresh engine instance pointing to existing state
        new_engine = SymblicOSTerminalEngine(self.dev_root)
        
        # Verify receipt persistence
        last_exec_id = self.previous_receipts.get("save")
        rec = get_receipt(last_exec_id, new_engine.paths["receipts"])
        receipt_persisted = rec is not None and rec["execution_id"] == last_exec_id

        # Verify physical file persistence without recreating
        note_path = os.path.join(new_engine.paths["user_files"], "note.txt")
        file_persisted = False
        if os.path.exists(note_path):
            with open(note_path, "rb") as f:
                content = f.read()
            file_persisted = (content == EXACT_NOTE_PAYLOAD.encode("utf-8"))

        # A model health check only when the caller supplies one (the original host passed its own model
        # engine); without it the check is reported as not performed, never as passed.
        model_invoked = bool(self.model_check(self.model_name)) if self.model_check is not None else None

        performed = [receipt_persisted, file_persisted] + ([model_invoked] if model_invoked is not None else [])
        return {
            "receipt_persisted": receipt_persisted,
            "file_persisted": file_persisted,
            "model_invoked": model_invoked,
            "model_check": "performed" if model_invoked is not None else "not performed (no model_check given)",
            "all_verified": all(performed),
        }
