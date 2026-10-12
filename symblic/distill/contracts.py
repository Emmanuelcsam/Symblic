"""Build the trusted contract bundle that the native scalar checker (checkers.py) evaluates against.

What it is for
    For each dataset item that came from an accepted run, find the run's original program, the accepted ask and
    the closed `ensure`/`assert` predicates that read the answer directly, and store them (with their syntax
    trees and closed context values) as a *contract*. The bundle also pins the kernel id and the SHA-256 of every
    Symblic source file, so the checker refuses to run under any other code. Items whose checks depend on open
    or post-answer context, or are not top-level predicates, are listed as rejected rather than guessed.

Each run is replayed in an isolated child process (export.py ``_capture``) with no model; a run whose files
change between capture and export refuses.

Depends on: ``symblic.distill.checkers``, ``symblic.distill.export``, ``symblic.distill.datasets``.
Run through ``python3 -m symblic.distill.cli export-contracts``. No networking, providers or workers; nothing
is written except the bundle file the caller names.
"""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from symblic.distill import checkers as NC


def build_bundle(repo, run_specs, dataset):
    """The contract bundle for `dataset` from the accepted runs in `run_specs` ([{run_dir, lock_file?}])."""
    from symblic.distill import datasets as D
    from symblic.distill import export as X

    D.verify_dataset(dataset)
    root = Path(repo).resolve()
    runtime_pins = NC.runtime_hashes(root)
    entries = {}
    rejected = []
    receipts = []
    kernel = None
    item_map = {}
    for item in dataset["items"]:
        item_map.setdefault(
            (
                item["provenance"]["source_sha256"],
                item["provenance"]["statement_sha256"],
            ),
            [],
        ).append(item)
    for spec in run_specs:
        run = Path(spec["run_dir"])
        lock_file = Path(spec.get("lock_file") or run / "run.lock.json")
        with tempfile.TemporaryDirectory(prefix="symblic-native-export-") as tmp:
            out = Path(tmp) / "capture.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("export.py")),
                    "_capture",
                    "--repo",
                    str(root),
                    "--run-dir",
                    str(run),
                    "--lock-file",
                    str(lock_file),
                    "--out",
                    str(out),
                ],
                capture_output=True,
                timeout=120,
            )
            if proc.returncode:
                raise NC.NativeContractError(
                    "trusted_native_replay_refused: " + proc.stderr.decode()[-300:]
                )
            capture = json.loads(out.read_text())
        try:
            raw = X.coherent_inputs(capture, run, lock_file)
        except X.ExportError as exc:
            raise NC.NativeContractError("run_inputs_changed_after_capture") from exc
        state = json.loads(raw["state.json"])
        lock = json.loads(raw["lock"])
        kid = state["kernel"]["id"]
        if kernel is None:
            kernel = kid
        if kernel != kid:
            raise NC.NativeContractError("mixed_kernels")
        receipts.append(
            {
                "run_id": run.name,
                "lock_sha256": capture["input_sha256"]["lock"],
                "state_sha256": capture["input_sha256"]["state.json"],
                "replay": capture["replay"],
            }
        )
        available = {
            r["receipt"]["id"]: r for r in capture["native_checks"] if "receipt" in r
        }
        for binding in state["bindings"]:
            obs = (
                (binding.get("meta") or {}).get("evidence", {}).get("observations", [])
            )
            candidates = {o.get("statement_sha256") for o in obs}
            for stmt in candidates:
                for item in item_map.get((lock["source_sha256"], stmt), []):
                    contract = D.native_contract(item)
                    if (
                        contract["kernel_id"] != kid
                        or contract["checker"]["sha256"]
                        != NC.file_hash(root / X.LOCK_REPLAY_SOURCE)
                        or contract["checker"]["id"] != X.CHECKER_ID
                        or contract["checker"]["version"] != 1
                    ):
                        raise NC.NativeContractError(
                            "dataset_checker_or_kernel_mismatch"
                        )
                    key = NC.contract_key(contract)
                    if key in entries:
                        continue
                    predicates = []
                    why = None
                    ty = None
                    for check in item["acceptance"]["checks"]:
                        captured = available.get(check["id"])
                        if (
                            captured is None
                            or not captured.get("top_level")
                            or binding["line"] not in capture["native_top_level_asks"]
                        ):
                            why = "unsupported_or_missing_predicate"
                            break
                        own = captured["bindings"].get(binding["name"])
                        if own is None or own["hash"] != binding["hash"]:
                            why = "answer_not_direct_predicate_input"
                            break
                        if own["line"] != binding["line"]:
                            why = "ambiguous_answer_binding"
                            break
                        ty = own["type"]
                        context = {
                            n: v
                            for n, v in captured["bindings"].items()
                            if n != binding["name"]
                        }
                        if any(
                            v["line"] >= binding["line"]
                            or not v["closed"]
                            or v["class"] != "exact"
                            for v in context.values()
                        ):
                            why = "nonclosed_or_post_answer_context"
                            break
                        receipt = captured["receipt"]
                        if (
                            receipt["predicate_sha256"] != check["predicate_sha256"]
                            or receipt["source_sha256"] != lock["source_sha256"]
                        ):
                            raise NC.NativeContractError(
                                "predicate_provenance_mismatch"
                            )
                        predicates.append(
                            {
                                "ast": captured["ast"],
                                "context": context,
                                "line": receipt["line"],
                                "text": receipt["predicate"],
                                "predicate_sha256": receipt["predicate_sha256"],
                            }
                        )
                    if why:
                        rejected.append({"item_id": item["item_id"], "reason": why})
                        continue
                    entry = {
                        "contract": contract,
                        "source": lock["source"],
                        "name": binding["name"],
                        "ask_line": binding["line"],
                        "type": ty,
                        "predicates": predicates,
                    }
                    entries[key] = entry
    if NC.runtime_hashes(root) != runtime_pins:
        raise NC.NativeContractError("runtime_changed_across_export")
    body = {
        "version": 1,
        "kernel_id": kernel,
        "runtime_root": str(root),
        "runtime_sha256": runtime_pins,
        "dataset_sha256": dataset["dataset_sha256"],
        "contracts": entries,
        "replay_receipts": receipts,
        "rejected": sorted(
            {r["item_id"]: r for r in rejected}.values(), key=lambda r: r["item_id"]
        ),
    }
    return {**body, "bundle_sha256": NC.digest(body)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True)
    p.add_argument("--runs", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    bundle = build_bundle(
        a.repo,
        json.loads(Path(a.runs).read_text()),
        json.loads(Path(a.dataset).read_text()),
    )
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(bundle, f, ensure_ascii=False)
    print(
        json.dumps(
            {
                "status": "written",
                "bundle_sha256": bundle["bundle_sha256"],
                "contracts": len(bundle["contracts"]),
                "rejected": bundle["rejected"],
                "kernel_id": bundle["kernel_id"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
