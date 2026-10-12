"""Boots the OS prototype's image in QEMU twice and records what could be observed. EXPERIMENTAL.

VirtualBootVerifier(kernel_path, initrd_path, disk_image_path).run_verification() starts
qemu-system-x86_64 with the image built by image_builder.py, forwards a host port to the guest daemon's
port 8990, and checks, over HTTP from the host:

    boot_completion        the guest daemon answered /api/symblicos/vitals within the timeout
    browser_access         GET /symblic-terminal.html returned a page of more than 1000 bytes
    deterministic_inspection   the vitals say status "online" and runtime "2.5"
    file_creation_instruction  POST /api/symblicos/terminal/submit answered terminal_success
    resulting_file_verified    the guest reports its marker file /mnt/persist/guest_verified.txt exists
    restart_verified       after a second boot the daemon answers again
    restart_persistence    after the second boot the marker file still exists

Read the results with the guest daemon in mind: it is a STUB (see guest_daemon.c) that answers fixed
JSON and writes a fixed marker file whatever it is sent, so these checks show that the image boots and
its network and file system work, not that Symblic runs in the guest. The /init script does not mount
the disk image at /mnt/persist, so restart_persistence is expected to be False. Every result is the
measured value; all_passed is their conjunction, and the receipt says success only when all passed.

Needs qemu-system-x86_64, a kernel image and the built initramfs and disk image. Nothing runs on import.
"""
from __future__ import annotations
import json
import os
import subprocess
import time
import urllib.request
from typing import Any, Dict, Optional

from symblic.os.paths import default_root
from symblic.os.receipts import create_receipt, store_receipt


class VirtualBootVerifier:
    """Verifies the prototype's bootable image inside a QEMU virtual machine (see the module docstring)."""

    def __init__(
        self,
        kernel_path: Optional[str] = None,
        initrd_path: Optional[str] = None,
        disk_image_path: Optional[str] = None,
        host_port: int = 18990,
        memory_mb: int = 1024,
        root: Optional[str] = None,
    ):
        self.root = root or default_root()
        build = os.path.join(self.root, "build")
        self.kernel_path = os.path.abspath(kernel_path or os.path.join(build, "vmlinuz"))
        self.initrd_path = os.path.abspath(initrd_path or os.path.join(build, "image", "initramfs.cpio.gz"))
        self.disk_image_path = os.path.abspath(disk_image_path or os.path.join(build, "image", "symblicos.img"))
        self.host_port = host_port
        self.memory_mb = memory_mb

    def _launch_vm(self) -> subprocess.Popen:
        cmd = [
            "qemu-system-x86_64",
            "-m", f"{self.memory_mb}M",
            "-kernel", self.kernel_path,
            "-initrd", self.initrd_path,
            "-drive", f"file={self.disk_image_path},format=raw,if=virtio",
            "-append", "console=ttyS0 quiet",
            "-nographic",
            "-nic", f"user,model=virtio-net-pci,hostfwd=tcp::{self.host_port}-:8990",
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def _wait_for_service(self, timeout_sec: int = 30) -> Dict[str, Any]:
        start = time.time()
        url = f"http://127.0.0.1:{self.host_port}/api/symblicos/vitals"
        while time.time() - start < timeout_sec:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        return data
            except Exception:
                time.sleep(0.5)
        raise TimeoutError(f"Guest terminal service did not become responsive on port {self.host_port} within {timeout_sec}s")

    def _get_json(self, path: str, timeout: float = 2.0) -> Dict[str, Any]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.host_port}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def run_verification(self) -> Dict[str, Any]:
        # 1. First boot
        proc1 = self._launch_vm()
        try:
            vitals1 = self._wait_for_service(timeout_sec=35)
            boot_ok = vitals1.get("status") == "online"
            inspection_ok = boot_ok and vitals1.get("runtime_version") == "2.5"

            # 2. The terminal document (the daemon serves a fallback heading when the image has no page)
            with urllib.request.urlopen(f"http://127.0.0.1:{self.host_port}/symblic-terminal.html", timeout=2.0) as resp:
                term_html = resp.read()
                browser_doc_ok = resp.status == 200 and len(term_html) > 1000
                browser_doc_len = len(term_html)

            # 3. A creation instruction (the stub daemon ignores its text and writes a fixed marker file)
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.host_port}/api/symblicos/terminal/submit",
                data=json.dumps({"instruction": "touch /mnt/persist/guest_verified.txt", "request_id": "vboot-001"}).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                submit_res = json.loads(resp.read().decode("utf-8"))
            submit_ok = submit_res.get("type") == "terminal_success"

            # 4. The marker file, as the guest reports it
            file_created = self._get_json("/api/symblicos/guest/status").get("persisted_file") is True
        finally:
            proc1.terminate()
            proc1.wait()

        time.sleep(1.0)

        # 5. Second boot: does the service come back, and did the marker file survive?
        proc2 = self._launch_vm()
        try:
            vitals2 = self._wait_for_service(timeout_sec=35)
            restart_service_ok = vitals2.get("status") == "online"
            restart_file_ok = self._get_json("/api/symblicos/guest/status").get("persisted_file") is True
        finally:
            proc2.terminate()
            proc2.wait()

        checks = {
            "boot_completion": boot_ok,
            "browser_access": browser_doc_ok,
            "deterministic_inspection": inspection_ok,
            "file_creation_instruction": submit_ok,
            "resulting_file_verified": file_created,
            "restart_verified": restart_service_ok,
            "restart_persistence": restart_file_ok,
        }
        all_passed = all(checks.values())
        receipt = create_receipt(
            original_instruction="make virtual boot verification",
            action_category="virtual_boot",
            target_machine_id="qemu-x86_64",
        )
        receipt["compiled_symblic"] = "# QEMU virtual boot check (no Symblic source is run in the guest)"
        receipt["result_status"] = "success" if all_passed else "validation_failure"
        receipt["stdout"] = (f"Booted the image twice in QEMU; terminal document {browser_doc_len} bytes; "
                             + ", ".join(f"{name}={value}" for name, value in checks.items()))
        receipt["completion_timestamp"] = time.time()
        receipt["validation_checks"] = list(checks)
        receipt["validation_results"] = list(checks.values())
        store_receipt(receipt, os.path.join(self.root, "receipts"))

        return {**checks, "all_passed": all_passed, "browser_doc_bytes": browser_doc_len,
                "receipt_id": receipt["execution_id"],
                "scope": "the guest daemon is a stub; these checks do not show Symblic running in the guest"}


if __name__ == "__main__":
    print(json.dumps(VirtualBootVerifier().run_verification(), indent=2))
