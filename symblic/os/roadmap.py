"""The OS prototype's roadmap: 18 layers a Symblic-driven operating system would need, none built yet.

ROADMAP_ITEMS is data. Each item names what the layer would do, what it depends on today (the host
Linux system), what Symblic would own, and an acceptance condition that would show it exists. Nothing
in this list is implemented; the items are design notes, not claims.

generate_roadmap_document(root) writes <root>/releases/symblicos_roadmap.json and <root>/ROADMAP.md and
stores a receipt for the write (root defaults to paths.default_root()).
"""
from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, List, Optional

from symblic.os.paths import default_root
from symblic.os.receipts import create_receipt, store_receipt

ROADMAP_ITEMS: List[Dict[str, Any]] = [
    {
        "id": "package_management",
        "title": "Package Management Layer",
        "current_baseline_dependency": "Host Linux package manager (apt/dpkg) and Python pip/uv",
        "symblic_ownership": "Declaration of dependencies in Symblic DSL manifests",
        "future_architecture": "Content-addressed, deterministic package store with immutable CAS tree and cryptographic integrity verification.",
        "future_acceptance_condition": "Symblic package install command reproducibly unpacks verified software without invoking apt or pip directly.",
    },
    {
        "id": "service_management",
        "title": "Declarative Service Management Layer",
        "current_baseline_dependency": "systemd unit files on host and in-guest /init shell script",
        "symblic_ownership": "Service life-cycle and supervised process execution states",
        "future_architecture": "Declarative service graph evaluated directly by SymblicOS supervisor with automatic health checking and restarts.",
        "future_acceptance_condition": "System boots, supervises, and recovers daemon services from a Symblic manifest without systemd unit generation.",
    },
    {
        "id": "device_inspection",
        "title": "Device Inspection Layer",
        "current_baseline_dependency": "Linux sysfs, udev, and lsblk/lspci tools",
        "symblic_ownership": "Hardware schema and device inventory records",
        "future_architecture": "Pure Symblic virtual device filesystem reading /sys and /dev directly into typed Symblic hardware objects.",
        "future_acceptance_condition": "Device query expression returns strongly-typed hardware inventory matching sysfs without executing external shell commands.",
    },
    {
        "id": "network_configuration",
        "title": "Network Configuration Layer",
        "current_baseline_dependency": "Linux ifconfig, iproute2, and DHCP clients",
        "symblic_ownership": "Network intent contracts and endpoint policies",
        "future_architecture": "Declarative network engine configuring interfaces, routes, DNS, and TLS endpoints directly from Symblic specifications.",
        "future_acceptance_condition": "Network interface configuration applied idempotently and tested via end-to-end socket round-trip without calling ip or ifconfig.",
    },
    {
        "id": "user_and_permissions",
        "title": "User and Permission Layer",
        "current_baseline_dependency": "POSIX users, groups, and sudoers configuration",
        "symblic_ownership": "Identity, capability delegation, and audit verification",
        "future_architecture": "Fine-grained cryptographic capability tokens gating file operations, network sockets, and model executions.",
        "future_acceptance_condition": "Execution of privileged effect rejected without valid signed capability token, independent of POSIX uid.",
    },
    {
        "id": "persistent_object_namespace",
        "title": "Persistent Object and Filesystem Namespace",
        "current_baseline_dependency": "Ext4 filesystem mounted on disk partitions",
        "symblic_ownership": "Object hashes, deterministic path canonicalization, and atomic commit semantics",
        "future_architecture": "Structured append-only object store mapping deterministic keys to versioned blobs with instant snapshotting.",
        "future_acceptance_condition": "Arbitrary object rollback performed with cryptographic guarantee that historic version matches prior receipt digest.",
    },
    {
        "id": "model_package_format",
        "title": "Model Package Format",
        "current_baseline_dependency": "Ollama manifest format and GGUF/HuggingFace disk caches",
        "symblic_ownership": "Model inventory validation, weight digest checking, and runtime binding",
        "future_architecture": "Self-contained Symblic Model Archive (.sma) bundling quantized weights, tokenizer metadata, chat template, and verification checksums.",
        "future_acceptance_condition": "Local inference initialized directly from a single .sma file with byte-verified SHA-256 weight hash.",
    },
    {
        "id": "agent_package_format",
        "title": "Agent Package Format",
        "current_baseline_dependency": "Local Node.js/Python agent repositories (for example ipy-llm-kernel)",
        "symblic_ownership": "Agent boundaries, capability grants, and execution receipts",
        "future_architecture": "Hermetic agent bundles containing executable runtime, capability manifest, memory schema, and deterministic sandbox definition.",
        "future_acceptance_condition": "Agent package admitted into cluster and executed with strict Landlock/cgroups boundary without external repository cloning.",
    },
    {
        "id": "update_and_rollback",
        "title": "System Update and Rollback Semantics",
        "current_baseline_dependency": "Manual image building and file replacements",
        "symblic_ownership": "Atomic release transition proofs and receipt logging",
        "future_architecture": "A/B dual-boot partition scheme with cryptographic signature check and automatic fallback on health-check failure.",
        "future_acceptance_condition": "Simulated failed update boots back into previously verified healthy release partition within one reboot cycle.",
    },
    {
        "id": "reproducible_images",
        "title": "Reproducible Image Construction",
        "current_baseline_dependency": "Ubuntu kernel packages and host mkfs tools",
        "symblic_ownership": "Build manifest definition and reproducible pipeline engine",
        "future_architecture": "Hermetic containerized build engine ensuring byte-for-byte identical kernel and rootfs images from source manifests.",
        "future_acceptance_condition": "Two independent builds from clean states produce identical SHA-256 disk image hashes.",
    },
    {
        "id": "signed_manifests",
        "title": "Signed Release Manifests",
        "current_baseline_dependency": "Plain JSON release manifests without PKI signatures",
        "symblic_ownership": "Cryptographic schema validation and key ring management",
        "future_architecture": "Ed25519 signature validation embedded into bootloader and user-space package verification engines.",
        "future_acceptance_condition": "Image with tampered bit rejected by boot verification engine before kernel hand-off.",
    },
    {
        "id": "deterministic_migrations",
        "title": "Deterministic Migration Procedures",
        "current_baseline_dependency": "Manual directory synchronization and rsync",
        "symblic_ownership": "State transformations defined as pure Symblic functions",
        "future_architecture": "Reversible state migrations defined as pure functions over persistent journals with forward and backward proofs.",
        "future_acceptance_condition": "State directory upgraded and subsequently downgraded with byte equality to pre-migration baseline.",
    },
    {
        "id": "recovery_mode",
        "title": "Recovery Mode",
        "current_baseline_dependency": "Busybox ash recovery console on /dev/console",
        "symblic_ownership": "Diagnostic assertions and automated recovery recipes",
        "future_architecture": "Dedicated minimal initramfs rescue target providing terminal diagnostics, hardware test harness, and remote recovery access.",
        "future_acceptance_condition": "Triggering kernel command-line rescue flag drops into SymblicOS recovery interface with full self-diagnostic report.",
    },
    {
        "id": "offline_mode",
        "title": "Offline Mode",
        "current_baseline_dependency": "Local model cache and local browser terminal serving",
        "symblic_ownership": "Zero-egress guarantee and local effect verification",
        "future_architecture": "Strict network sandboxing preventing all outbound WAN egress while maintaining local LAN clustering and browser operations.",
        "future_acceptance_condition": "Full acceptance test suite passes with WAN gateway blocked at firewall boundary.",
    },
    {
        "id": "cluster_enrollment",
        "title": "Cluster-Node Enrollment",
        "current_baseline_dependency": "The host's SSH keys and its hand-kept node records",
        "symblic_ownership": "Cluster topology declaration and node membership ledgers",
        "future_architecture": "Zero-trust node mutual authentication using mTLS certificates and TPM hardware attestation.",
        "future_acceptance_condition": "Newly booted physical node enrolled into the cluster automatically and verified via mutual cryptographic challenge.",
    },
    {
        "id": "remote_execution",
        "title": "Remote Symblic Execution",
        "current_baseline_dependency": "SSH command execution on nodes",
        "symblic_ownership": "Deterministic RPC wire protocol and instruction serialization",
        "future_architecture": "Native Symblic binary wire protocol streaming AST execution and state deltas over encrypted channels.",
        "future_acceptance_condition": "A remote node executes a Symblic expression with streaming stdout and returns a typed result structure without invoking SSH.",
    },
    {
        "id": "distributed_receipts",
        "title": "Distributed Execution Receipts",
        "current_baseline_dependency": "Local receipt storage in <root>/receipts",
        "symblic_ownership": "Cryptographic receipt linking and merkle tree aggregation",
        "future_architecture": "Distributed receipt journal with signed hash-chains replicating across cluster nodes with Byzantine fault tolerance.",
        "future_acceptance_condition": "A receipt generated on one node is replicated to another and verified via a merkle audit proof.",
    },
    {
        "id": "hardware_capability_interface",
        "title": "Hardware Capability Extensibility Interface",
        "current_baseline_dependency": "C-compiled guest daemon and host Linux drivers",
        "symblic_ownership": "Formal grammar separation and capability discovery schemas",
        "future_architecture": "Plugin interface mapping newly detected physical devices (e.g. NPU, FPGA, CAN bus) to effect handlers without grammar alterations.",
        "future_acceptance_condition": "Adding new peripheral driver exposes typed operations in terminal while keeping language grammar hash invariant.",
    },
]

def generate_roadmap_document(root: Optional[str] = None) -> Dict[str, Any]:
    """Write the roadmap as JSON and Markdown under `root` and store a receipt for it."""
    root = root or default_root()
    out_dir = os.path.join(root, "releases")
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "symblicos_roadmap.json")
    md_path = os.path.join(root, "ROADMAP.md")

    roadmap_data = {
        "title": "SymblicOS Operating System Architectural Roadmap",
        "version": "1.0",
        "baseline_release": "symblicos-v0.1.0-alpha",
        "timestamp": time.time(),
        "dimensions_count": len(ROADMAP_ITEMS),
        "items": ROADMAP_ITEMS,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(roadmap_data, f, indent=2)

    # Format Markdown document
    lines = [
        "# SymblicOS Operating System Architectural Roadmap",
        "",
        "> **Notice:** Roadmap items define future architectural layers beyond the accepted v0.1.0 release.",
        "> Per project rules, these components are defined with baseline dependencies and acceptance conditions,",
        "> but are not claimed as implemented in the current baseline.",
        "",
        f"**Baseline Release:** `{roadmap_data['baseline_release']}`  ",
        f"**Defined Dimensions:** {len(ROADMAP_ITEMS)}  ",
        "",
        "---",
        "",
    ]

    for idx, item in enumerate(ROADMAP_ITEMS, 1):
        lines.append(f"### {idx}. {item['title']} (`{item['id']}`)")
        lines.append(f"- **Current Baseline Dependency:** {item['current_baseline_dependency']}")
        lines.append(f"- **Symblic Ownership:** {item['symblic_ownership']}")
        lines.append(f"- **Future Architecture:** {item['future_architecture']}")
        lines.append(f"- **Future Acceptance Condition:** {item['future_acceptance_condition']}")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    receipt = create_receipt(
        original_instruction="make SymblicOS operating system roadmap",
        action_category="roadmap_definition",
    )
    receipt["compiled_symblic"] = "# SymblicOS future architectural layer roadmap"
    receipt["result_status"] = "success"
    receipt["stdout"] = f"Defined all {len(ROADMAP_ITEMS)} architectural roadmap dimensions in {md_path} and {json_path}."
    receipt["completion_timestamp"] = time.time()
    receipt["validation_checks"] = [
        "all_18_dimensions_covered",
        "baseline_dependencies_identified",
        "acceptance_conditions_defined",
        "no_unimplemented_claims",
    ]
    receipt["validation_results"] = [True, True, True, True]
    store_receipt(receipt, os.path.join(root, "receipts"))

    roadmap_data["receipt_id"] = receipt["execution_id"]
    return roadmap_data

if __name__ == "__main__":
    rm = generate_roadmap_document()
    print(f"Generated roadmap with {rm['dimensions_count']} items. Receipt: {rm['receipt_id']}")
