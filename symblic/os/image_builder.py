"""Builds the OS prototype's bootable Linux image: a BusyBox root filesystem plus the guest daemon.

EXPERIMENTAL. What the image really contains:
    * BusyBox (copied from the build machine) and a small /init shell script that mounts /proc, /sys
      and /dev, configures QEMU's user-mode network (10.0.2.15) and starts the guest daemon;
    * the guest daemon (guest_daemon.c, compiled statically with gcc), a STUB that answers fixed JSON
      and does not run Symblic (see the comment at the top of guest_daemon.c);
    * a copy of the Symblic language runtime source (symblic/kernel/language.py). It is inert: the
      image has no Python interpreter, so nothing in the guest runs Symblic;
    * the terminal page, only when one is passed in (this repository ships none).

assemble_rootfs() builds the tree and refuses to continue when a file that looks like a secret (.env*,
*.pem, *.key, names containing "secret" or "credential") ended up in it. build_initrd() packs it as an
initramfs (find | cpio | gzip); build_disk_image() makes an ext4 image with `mkfs.ext4 -d`;
create_release_manifest() records sha256 digests. A Linux kernel image (vmlinuz) is not built here: the
operator supplies one at kernel_path. Tools needed on the build machine: busybox, gcc with static libc,
cpio, gzip, mkfs.ext4. Nothing runs on import.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, Optional

from symblic.os.paths import default_root
from symblic.os.receipts import RUNTIME_FILE, compute_runtime_digest

GUEST_DAEMON_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guest_daemon.c")
SECRET_NAME_RX = re.compile(r"^\.env|secret|credential|\.pem$|\.key$", re.I)


class BootableImageBuilder:
    """Constructs the prototype's Linux filesystem tree and its disk and initramfs images."""

    def __init__(self, build_root: Optional[str] = None, kernel_path: Optional[str] = None,
                 terminal_page: Optional[str] = None):
        build = os.path.join(default_root(), "build")
        self.build_root = os.path.abspath(build_root or os.path.join(build, "image"))
        self.rootfs_dir = os.path.join(self.build_root, "rootfs")
        self.image_path = os.path.join(self.build_root, "symblicos.img")
        self.initrd_path = os.path.join(self.build_root, "initramfs.cpio.gz")
        self.manifest_path = os.path.join(self.build_root, "image_manifest.json")
        self.daemon_path = os.path.join(self.build_root, "guest_daemon")
        self.vmlinuz_path = kernel_path or os.path.join(build, "vmlinuz")
        self.terminal_page = terminal_page

    def assemble_rootfs(self) -> Dict[str, Any]:
        """Create the image's filesystem tree under build_root/rootfs (replacing an earlier one)."""
        if os.path.exists(self.rootfs_dir):
            shutil.rmtree(self.rootfs_dir)
        os.makedirs(self.rootfs_dir, exist_ok=True)

        # Standard Linux hierarchy
        for d in ("bin", "sbin", "usr/bin", "usr/sbin", "etc", "proc", "sys", "dev", "run", "tmp", "var", "opt/symblicos", "home/symblicos", "mnt/persist"):
            os.makedirs(os.path.join(self.rootfs_dir, d), exist_ok=True)

        # 1. Install Busybox
        busybox_src = shutil.which("busybox") or "/usr/bin/busybox"
        busybox_dst = os.path.join(self.rootfs_dir, "bin", "busybox")
        shutil.copy2(busybox_src, busybox_dst)
        os.chmod(busybox_dst, 0o755)

        # Create essential symlinks to busybox
        for tool in ("sh", "echo", "cat", "ls", "mkdir", "cp", "mv", "rm", "mount", "umount", "sleep", "ip", "ifconfig", "route", "hostname", "uname", "ps", "grep", "nc", "sed", "awk"):
            link_path = os.path.join(self.rootfs_dir, "bin", tool)
            if not os.path.exists(link_path):
                os.symlink("busybox", link_path)

        components = ["bin/busybox", "init"]
        # 2. The Symblic runtime source (inert in the guest: there is no Python interpreter) and,
        #    when one was given, the terminal page
        shutil.copy2(RUNTIME_FILE, os.path.join(self.rootfs_dir, "opt", "symblicos", "language.py"))
        components.append("opt/symblicos/language.py")
        if self.terminal_page and os.path.exists(self.terminal_page):
            shutil.copy2(self.terminal_page, os.path.join(self.rootfs_dir, "opt", "symblicos", "symblic-terminal.html"))
            components.append("opt/symblicos/symblic-terminal.html")

        # 3. The static guest daemon (a stub; see guest_daemon.c)
        if not os.path.exists(self.daemon_path):
            os.makedirs(self.build_root, exist_ok=True)
            subprocess.run(["gcc", "-static", "-O2", GUEST_DAEMON_SOURCE, "-o", self.daemon_path], check=True)
        daemon_dst = os.path.join(self.rootfs_dir, "opt", "symblicos", "guest_daemon")
        shutil.copy2(self.daemon_path, daemon_dst)
        os.chmod(daemon_dst, 0o755)
        components.append("opt/symblicos/guest_daemon")

        # 4. In-guest /init script
        init_script = """#!/bin/sh
# SymblicOS /init
mount -t proc none /proc
mount -t sysfs none /sys
mount -t devtmpfs none /dev

mkdir -p /dev/pts
mount -t devpts none /dev/pts

# Networking (SLIRP-compatible configuration)
ifconfig lo 127.0.0.1 up
ifconfig eth0 10.0.2.15 netmask 255.255.255.0 up
route add default gw 10.0.2.2 2>/dev/null

echo "=========================================="
echo " Welcome to SymblicOS (Linux-based Kernel) "
echo "=========================================="
echo "Connected node: $(hostname)"
echo "Symblic runtime version: 2.5"

# Launch SymblicOS terminal backend daemon
/opt/symblicos/guest_daemon 8990 &

echo "SymblicOS terminal backend active on port 8990."
echo "Recovery console active on /dev/console."

# Fallback interactive shell on console
exec /bin/sh
"""
        init_path = os.path.join(self.rootfs_dir, "init")
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(init_script)
        os.chmod(init_path, 0o755)

        # 5. Refuse an image that picked up something that looks like a secret of the build machine
        for root, dirs, files in os.walk(self.rootfs_dir):
            for file in files:
                if SECRET_NAME_RX.search(file):
                    raise PermissionError(f"Secret file detected in rootfs: {file}")

        return {
            "rootfs_dir": self.rootfs_dir,
            "components": components,
            "secrets_clean": True,
        }

    def build_initrd(self) -> str:
        """Pack rootfs into an initramfs cpio.gz image for QEMU."""
        cmd = "find . | cpio -H newc -o | gzip -9"
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=self.rootfs_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        with open(self.initrd_path, "wb") as f:
            f.write(res.stdout)
        return self.initrd_path

    def build_disk_image(self, size_mb: int = 100) -> str:
        """Build an ext4 disk image from the rootfs with mkfs.ext4 -d."""
        # Truncate image file
        with open(self.image_path, "wb") as f:
            f.seek((size_mb * 1024 * 1024) - 1)
            f.write(b"\0")

        # Format directly with rootfs contents
        cmd = ["mkfs.ext4", "-F", "-L", "SymblicOS", "-d", self.rootfs_dir, self.image_path]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return self.image_path

    def create_release_manifest(self) -> Dict[str, Any]:
        """Record the sha256 of the disk image, the initramfs, the kernel and the Symblic runtime."""
        with open(self.image_path, "rb") as f:
            img_bytes = f.read()
        img_digest = hashlib.sha256(img_bytes).hexdigest()

        with open(self.initrd_path, "rb") as f:
            initrd_bytes = f.read()
        initrd_digest = hashlib.sha256(initrd_bytes).hexdigest()

        manifest = {
            "release_id": "symblicos-v0.1.0-alpha",
            "architecture": "x86_64",
            "disk_image": {
                "path": self.image_path,
                "format": "raw-ext4",
                "byte_size": len(img_bytes),
                "sha256": img_digest,
            },
            "initramfs": {
                "path": self.initrd_path,
                "byte_size": len(initrd_bytes),
                "sha256": initrd_digest,
            },
            "kernel": {
                "path": self.vmlinuz_path,
                "sha256": _sha256_file(self.vmlinuz_path),
            },
            "symblic_runtime": {
                "version": "2.5",
                "sha256": compute_runtime_digest(),
            },
            "build_timestamp": time.time(),
        }

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest


def _sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()
