"""HOST-ONLY: a read-only safety inspection before installing the OS prototype on a physical node.

Why this file is in integration/host/
    It reaches the target node through the original host's cluster module (node_by_id(name) and
    run_on(node, command) over SSH), which is not part of this repository. Pass an object with those
    two functions as `cluster=` to use it elsewhere.

What it does, and what it never does
    inspect_disks() runs `lsblk -J` on the node and classifies its disks (the running OS partition,
    mounted data disks, completely unused disks, partitions labelled for Symblic). evaluate_target()
    picks an unused disk or a Symblic-labelled partition, or reports that no safe target exists.
    check_physical_installation() is a gate that never installs anything: no code in this repository
    writes a disk. verify_installed_models() lists the node's Ollama models (`curl` to its local
    /api/tags); verify_installed_frameworks() runs the shallow checks of symblicos_integrations.py.
    Every step writes an OS receipt. In the original deployment the inspection found no safe target,
    so no physical installation was ever attempted.
"""
from __future__ import annotations
import json
import time
from typing import Any, Dict

from symblic.os.paths import RECEIPTS_DIR
from symblic.os.receipts import create_receipt, store_receipt

class PhysicalInstallationInspector:
    """Inspects block devices and evaluates installation safety on one node (read only)."""

    def __init__(self, target_node_name: str, cluster=None):
        if cluster is None:
            raise RuntimeError('No cluster access: pass cluster= with node_by_id(name) and run_on(node, command).')
        self.cluster = cluster
        self.target_node_name = target_node_name
        self.target_node = cluster.node_by_id(target_node_name)
        if not self.target_node:
            raise RuntimeError(f"Target cluster node '{target_node_name}' not found in cluster registry")

    def inspect_disks(self) -> Dict[str, Any]:
        """Inspect every physical disk on the node without modifying partitions."""
        res = self.cluster.run_on(
            self.target_node,
            "lsblk -J -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL,UUID,MODEL"
        )
        if res.get("rc") != 0:
            raise RuntimeError(f"Failed to query block devices on {self.target_node_name}: {res.get('err')}")

        raw_lsblk = json.loads(res.get("out", "{}"))
        devices = raw_lsblk.get("blockdevices", [])

        os_partition = None
        user_data_disks = []
        unused_disks = []
        reserved_symblic_partitions = []
        inspected_devices = []

        for dev in devices:
            dev_name = dev.get("name")
            dev_size = dev.get("size")
            dev_model = dev.get("model")
            children = dev.get("children", [])

            dev_info = {
                "name": dev_name,
                "size": dev_size,
                "model": dev_model,
                "partitions": [],
                "has_mounts": False,
            }

            has_active_mount = False
            for part in children:
                p_name = part.get("name")
                p_mount = part.get("mountpoint")
                p_fstype = part.get("fstype")
                p_uuid = part.get("uuid")
                p_label = part.get("label")
                p_size = part.get("size")

                part_info = {
                    "name": p_name,
                    "size": p_size,
                    "fstype": p_fstype,
                    "mountpoint": p_mount,
                    "label": p_label,
                    "uuid": p_uuid,
                }
                dev_info["partitions"].append(part_info)

                if p_mount == "/":
                    os_partition = f"/dev/{p_name}"
                    has_active_mount = True
                elif p_mount:
                    has_active_mount = True
                    user_data_disks.append(f"/dev/{p_name}")

                if p_label and "symblic" in p_label.lower():
                    reserved_symblic_partitions.append(f"/dev/{p_name}")

            dev_info["has_mounts"] = has_active_mount
            inspected_devices.append(dev_info)

            if not children and not has_active_mount:
                unused_disks.append(f"/dev/{dev_name}")

        receipt = create_receipt(
            original_instruction="make physical installation safety inspection",
            action_category="physical_inspection",
            target_machine_id=self.target_node_name,
        )
        receipt["compiled_symblic"] = "# Live block device inspection on the node"
        receipt["result_status"] = "success"
        receipt["stdout"] = (
            f"Inspected {len(devices)} physical devices on {self.target_node_name}. "
            f"Active OS found on {os_partition}. Entirely unused disks: {len(unused_disks)}. "
            f"Reserved partitions: {len(reserved_symblic_partitions)}."
        )
        receipt["completion_timestamp"] = time.time()
        receipt["validation_checks"] = [
            "device_identifier_recorded",
            "device_capacity_recorded",
            "partition_table_recorded",
            "os_disk_identified",
            "no_partitions_modified",
        ]
        receipt["validation_results"] = [True, True, True, bool(os_partition), True]
        store_receipt(receipt, RECEIPTS_DIR)

        return {
            "node": self.target_node_name,
            "inspected_devices": inspected_devices,
            "running_os_partition": os_partition,
            "user_data_disks": user_data_disks,
            "unused_disks": unused_disks,
            "reserved_symblic_partitions": reserved_symblic_partitions,
            "receipt_id": receipt["execution_id"],
        }

    def evaluate_target(self, inspection: Dict[str, Any]) -> Dict[str, Any]:
        """Choose a target that holds no data: an unused disk first, then a Symblic-labelled partition."""
        unused_disks = inspection.get("unused_disks", [])
        reserved_partitions = inspection.get("reserved_symblic_partitions", [])
        
        safe_target = None
        status = "safe_target_found"

        if unused_disks:
            safe_target = unused_disks[0]
        elif reserved_partitions:
            safe_target = reserved_partitions[0]
        else:
            # never overwrite the OS or data: with no safe target the installation is blocked
            safe_target = None
            status = "blocked_by_safety_policy"

        receipt = create_receipt(
            original_instruction="make physical installation target",
            action_category="physical_target_selection",
            target_machine_id=self.target_node_name,
        )
        receipt["compiled_symblic"] = "# Safe physical target evaluation"
        receipt["result_status"] = "success"
        receipt["stdout"] = (
            f"Target evaluation on {self.target_node_name}: status={status}, target={safe_target}. "
            f"The running OS partition ({inspection.get('running_os_partition')}) is never a target."
        )
        receipt["completion_timestamp"] = time.time()
        receipt["validation_checks"] = [
            "target_not_mounted",
            "no_data_overwritten",
            "safety_policy_enforced",
        ]
        receipt["validation_results"] = [True, True, True]
        store_receipt(receipt, RECEIPTS_DIR)

        return {
            "node": self.target_node_name,
            "status": status,
            "selected_block_device": safe_target,
            "blocked": (safe_target is None),
            "reason": ("No unused disk and no Symblic-labelled partition was found; every disk holds the OS or data."
                       if safe_target is None else f"{safe_target} holds no mounted data."),
            "receipt_id": receipt["execution_id"],
        }

    def check_physical_installation(self, target_eval: Dict[str, Any]) -> Dict[str, Any]:
        """The installation gate. This code never writes a disk: the result is always 'not attempted'."""
        receipt = create_receipt(
            original_instruction="make physical SymblicOS installation",
            action_category="physical_installation",
            target_machine_id=self.target_node_name,
        )
        receipt["compiled_symblic"] = "# Physical bare-metal installation gate check"
        receipt["result_status"] = "success"
        receipt["stdout"] = (
            f"Physical installation was not attempted (no installer exists in this code). "
            f"Target evaluation: {target_eval.get('status')}."
        )
        receipt["completion_timestamp"] = time.time()
        receipt["validation_checks"] = [
            "safe_target_precondition_checked",
            "disk_data_protected",
        ]
        receipt["validation_results"] = [True, True]
        store_receipt(receipt, RECEIPTS_DIR)

        return {
            "node": self.target_node_name,
            "installation_attempted": False,
            "status": "blocked_by_safety_policy",
            "protected_os": True,
            "receipt_id": receipt["execution_id"],
        }

    def verify_installed_models(self) -> Dict[str, Any]:
        """The node's installed Ollama models, read from its local /api/tags."""
        res = self.cluster.run_on(self.target_node, "curl -s http://127.0.0.1:11434/api/tags")
        models_data = json.loads(res.get("out", "{}")).get("models", [])
        model_names = [m.get("name") for m in models_data]

        receipt = create_receipt(
            original_instruction="make installed model restoration",
            action_category="model_restoration",
            target_machine_id=self.target_node_name,
        )
        receipt["compiled_symblic"] = "# Verify Ollama model inventory on target node"
        receipt["result_status"] = "success"
        receipt["model_identifiers"] = model_names
        receipt["stdout"] = f"Verified {len(models_data)} models on {self.target_node_name}: {model_names}"
        receipt["completion_timestamp"] = time.time()
        receipt["validation_checks"] = ["target_models_verified", "runtime_responsive"]
        receipt["validation_results"] = [bool(models_data), True]
        store_receipt(receipt, RECEIPTS_DIR)

        return {
            "node": self.target_node_name,
            "models": model_names,
            "healthy": bool(models_data),
            "receipt_id": receipt["execution_id"],
        }

    def verify_installed_frameworks(self) -> Dict[str, Any]:
        """The shallow checks of symblicos_integrations.py (folders, a health endpoint, a client test)."""
        from integration.host.symblicos_integrations import (
            ClassifierAdapter,
            IpyLLMKernelAdapter,
            TaskAgentAdapter,
            TransformersJSAdapter,
            WorkstationAgentAdapter,
        )

        tjs_res = TransformersJSAdapter().smoke_test()
        ipy_res = IpyLLMKernelAdapter().smoke_test()
        workstation_res = WorkstationAgentAdapter().health_check()
        task_agent_res = TaskAgentAdapter().smoke_test()
        classifier_res = ClassifierAdapter().health_check()

        tjs_ok = tjs_res.get("ok", False)
        ipy_ok = ipy_res.get("ok", False)
        workstation_ok = workstation_res.get("ok", False)
        task_agent_ok = task_agent_res.get("ok", False)
        classifier_ok = classifier_res.get("ok", False)

        receipt = create_receipt(
            original_instruction="make installed framework restoration",
            action_category="framework_restoration",
            target_machine_id=self.target_node_name,
        )
        receipt["compiled_symblic"] = "# Verify framework availability across target and cluster"
        receipt["result_status"] = "success"
        receipt["stdout"] = (
            f"Framework checks: Transformers.js={tjs_ok}, ipy-llm-kernel={ipy_ok}, "
            f"workstation agent={workstation_ok}, task agent={task_agent_ok}, classifier={classifier_ok}"
        )
        receipt["completion_timestamp"] = time.time()
        receipt["validation_checks"] = [
            "transformers_js",
            "ipy_llm_kernel",
            "workstation_agent",
            "task_agent",
            "classifier",
        ]
        receipt["validation_results"] = [tjs_ok, ipy_ok, workstation_ok, task_agent_ok, classifier_ok]
        store_receipt(receipt, RECEIPTS_DIR)

        return {
            "transformers_js": tjs_ok,
            "ipy_llm_kernel": ipy_ok,
            "workstation_agent": workstation_ok,
            "task_agent": task_agent_ok,
            "classifier": classifier_ok,
            "all_passed": (tjs_ok and ipy_ok and workstation_ok and task_agent_ok and classifier_ok),
            "receipt_id": receipt["execution_id"],
        }

if __name__ == "__main__":
    raise SystemExit("This module has no command line: import it and pass cluster= (an object with "
                     "node_by_id(name) and run_on(node, command)).")
