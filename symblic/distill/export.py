"""Turn one finished, accepted Symblic run into distillation records, by replaying it locally with no model.

What it is for
    A Symblic run folder (state.json, calls.jsonl, run.lock.json) records every model answer the kernel accepted
    and the native checks it passed. ``export_run`` replays that run from its lock file in a separate child
    process (``symblic.kernel.lockfile.replay``, which refuses any call that is not already recorded and disables
    side effects), captures the exact prompts and native check receipts, and emits one record per accepted scalar
    answer (Int, Bool or String) that passed at least one encoded predicate. Contested, synthesized, feedback-
    or oracle-exposed answers, and answers without an observed pinned model digest, are rejected.

Records feed symblic/distill/datasets.py (``build_dataset``). What a record proves is stated there.

Depends on: ``symblic.kernel.run`` and ``symblic.kernel.lockfile`` (in the capture child only),
``symblic.distill.checkers`` (to capture predicate syntax) and ``symblic.distill.datasets``.
Run through ``python3 -m symblic.distill.cli export-run`` or directly with ``python3 symblic/distill/export.py``.
No provider is imported or called.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


# The module whose replay is the "checker" every exported record names (its sha256 goes into each record).
LOCK_REPLAY_SOURCE = "symblic/kernel/lockfile.py"
CHECKER_ID = "symblic-native-lock-replay"


class ExportError(ValueError):
    """A run that cannot be exported as-is (changed inputs, missing evidence, identity mismatch)."""


def h(data):
    """SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def read_snapshot(path):
    """Bytes of a bounded regular file (no symlinks)."""
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 32_000_000:
        raise ExportError("bounded regular file required")
    with p.open("rb") as stream:
        raw = stream.read(32_000_001)
    if len(raw) > 32_000_000:
        raise ExportError("snapshot file too large")
    return raw


def load(path):
    """JSON from a bounded regular file."""
    return json.loads(read_snapshot(path))


def coherent_inputs(captured, run_dir, lock_file):
    """Reread the run files and refuse when they changed since the capture."""
    paths = {
        "state.json": Path(run_dir) / "state.json",
        "calls.jsonl": Path(run_dir) / "calls.jsonl",
        "lock": Path(lock_file),
    }
    raw = {name: read_snapshot(path) for name, path in paths.items()}
    if {name: h(value) for name, value in raw.items()} != captured.get("input_sha256"):
        raise ExportError("run inputs changed across native capture")
    return raw


def capture_child(repo, run_dir, out, lock_file=None):
    """Child-process half of export_run: replay the lock with no model and write what it observed to `out`."""
    # This isolated CLI process has no live Run instances. Restore even on error.
    sys.path.insert(0, str(Path(repo).resolve()))
    from symblic.kernel import run as SR
    from symblic.kernel import lockfile as L

    lock_file = Path(lock_file or Path(run_dir) / "run.lock.json")
    paths = {
        "state.json": Path(run_dir) / "state.json",
        "calls.jsonl": Path(run_dir) / "calls.jsonl",
        "lock": lock_file,
    }
    raw = {name: read_snapshot(path) for name, path in paths.items()}
    input_pins = {name: h(value) for name, value in raw.items()}
    if len(raw["lock"]) > L.MAX_LOCK_BYTES:
        raise ExportError("native lock too large")
    lock = L._validate(json.loads(raw["lock"]))
    state = json.loads(raw["state.json"])
    if (
        state.get("fingerprint") != lock["fingerprint"]
        or state.get("evidence", {}).get("source_sha256") != lock["source_sha256"]
    ):
        raise ExportError("saved state does not match native lock identity")
    if L._evidence_identity(state.get("evidence")) != L._evidence_identity(
        lock.get("evidence")
    ) or L._evidence_identity(
        L.statements_of(state.get("bindings"), state.get("outputs"))
    ) != L._evidence_identity(lock["statements"]):
        raise ExportError("saved acceptance evidence differs from native lock")
    captured = []
    native_checks = []
    top = SR.S.parse(lock["source"])["statements"]
    top_asks = [node.line for node in top if node.k == "ask"]
    top_checks = [node.line for node in top if node.k in ("ensure", "assert")]
    original = SR.Run

    class CapturingRun(original):
        def _record_check(self, statement, env, passed):
            receipt = super()._record_check(statement, env, passed)
            try:
                from symblic.distill import checkers as NC

                captured_check = NC.capture_check(statement, env, receipt)
                captured_check["top_level"] = statement.line in top_checks
                native_checks.append(captured_check)
            except (ImportError, ValueError) as exc:
                native_checks.append(
                    {"receipt_id": receipt["id"], "unsupported": type(exc).__name__}
                )
            return receipt

        def _call(
            self,
            app,
            system,
            prompt,
            schema,
            sample,
            temperature,
            seed,
            effort,
            tools,
            s,
            **kw,
        ):
            reply = super()._call(
                app,
                system,
                prompt,
                schema,
                sample,
                temperature,
                seed,
                effort,
                tools,
                s,
                **kw,
            )
            captured.append(
                {
                    "key": reply.get("_request_sha256"),
                    "system": system,
                    "user": prompt,
                    "schema": schema,
                    "reply": reply,
                }
            )
            return reply

    SR.Run = CapturingRun
    try:
        result = L.replay(lock)
    finally:
        SR.Run = original
    if not result["ok"] or result["refused"] or result["calls"] != 0:
        raise ExportError(
            "native replay did not reproduce the accepted run without new calls"
        )
    coherent_inputs({"input_sha256": input_pins}, run_dir, lock_file)
    Path(out).write_text(
        json.dumps(
            {
                "capture": captured,
                "input_sha256": input_pins,
                "native_checks": native_checks,
                "native_top_level_asks": top_asks,
                "replay": {
                    k: result[k]
                    for k in [
                        "ok",
                        "fingerprint",
                        "expected",
                        "calls",
                        "cached",
                        "evidence_match",
                    ]
                },
            }
        )
    )


def accepted_records(state, calls, capture, run_id, group_key, checker_sha):
    """(records, rejected) for the accepted scalar answers of one replayed run (see the module docstring)."""
    from symblic.distill import datasets as D

    if state.get("status") != "done":
        raise ExportError("only completed accepted runs can be exported")
    checks = state.get("evidence", {}).get("checks", [])
    src = state["evidence"]["source_sha256"]
    kid = state["kernel"]["id"]
    observed = {r["key"]: r for r in calls if r.get("ok")}
    prompts = {r["key"]: r for r in capture if r["key"]}
    records = []
    rejected = []
    kinds = {"Int": "integer", "Bool": "boolean", "String": "string"}
    for b in state["bindings"]:
        meta = b.get("meta") or {}
        ev = meta.get("evidence") or {}
        if not ev.get("observations"):
            continue
        reason = None
        if b["type"] not in kinds:
            reason = "unsupported_scalar_type"
        elif meta.get("contested") or meta.get("synthesized"):
            reason = "contested_or_synthesized"
        passed = [
            c
            for c in checks
            if c.get("passed") is True
            and c.get("scope") == "encoded_predicate"
            and c.get("source_sha256") == src
            and c.get("kernel", {}).get("id") == kid
            and {"name": b["name"], "hash": b["hash"]} in c.get("bindings", [])
        ]
        if not passed:
            reason = reason or "no_native_predicate_check_for_answer"
        if reason:
            rejected.append({"name": b["name"], "reason": reason})
            continue
        for obs in ev["observations"]:
            if not obs.get("ok") or obs.get("answer_hash") != b["hash"]:
                continue
            if any(
                obs.get(k)
                for k in ["feedback_exposed", "oracle_exposed", "peer_exposed"]
            ):
                rejected.append(
                    {"name": b["name"], "reason": "feedback_or_oracle_exposed"}
                )
                continue
            key = obs["request_sha256"]
            call = observed.get(key)
            cap = prompts.get(key)
            if not call or not cap or call.get("repair"):
                raise ExportError(
                    "accepted observation missing exact original call or replay prompt"
                )
            raw = call.get("model_identity_raw", {})
            ident = call.get("identity_check_at_call", {})
            digest = raw.get("digest", "")
            if (
                raw.get("status") != "observed"
                or not ident.get("validated")
                or not ident.get("pinned")
                or ident.get("refused")
            ):
                raise ExportError("observed pinned model identity required")
            if not digest.startswith("sha256:") or any(
                raw.get(k, {}).get("digest") != digest for k in ["before", "after"]
            ):
                raise ExportError("model bracket digest mismatch")
            value = b["value"]
            answer_sha = D.digest(value)
            if (
                answer_sha[:16] != b["hash"]
                or D.digest(call["reply"].get("json", {}).get("answer")) != answer_sha
            ):
                raise ExportError("native answer/call identity mismatch")
            cm = obs.get("context_manifest", {})
            if h(cap["system"].encode()) != cm.get("system_sha256") or h(
                cap["user"].encode()
            ) != cm.get("prompt_sha256"):
                raise ExportError(
                    "exact prompt hashes disagree with recorded native manifest"
                )
            row = {
                "version": 1,
                "run_id": run_id,
                "source_sha256": src,
                "statement_sha256": obs["statement_sha256"],
                "kernel_id": kid,
                "checker": {
                    "id": CHECKER_ID,
                    "version": 1,
                    "sha256": checker_sha,
                },
                "model": {
                    "requested": call["app"],
                    "observed": raw["model"],
                    "identity": "observed",
                    "digest": digest[7:],
                },
                "prompt": {
                    "system": cap["system"],
                    "user": cap["user"],
                    "sha256": D.digest([cap["system"], cap["user"]]),
                },
                "answer": {
                    "type": kinds[b["type"]],
                    "value": value,
                    "sha256": answer_sha,
                    "fingerprint": b["hash"],
                },
                "acceptance": {
                    "status": "accepted",
                    "vote": "single" if meta.get("votes") == 1 else "uncontested",
                    "determination": ev.get("assurance", "typed_answer"),
                    "checks": [
                        {
                            "id": c["id"],
                            "predicate_sha256": c["predicate_sha256"],
                            "passed": True,
                            "scope": "encoded_predicate",
                            "kernel_id": kid,
                            "predicate": c["predicate"],
                        }
                        for c in passed
                    ],
                },
                "request_sha256": key,
                "capsule_sha256": obs["capsule_sha256"],
                "group_key": group_key,
                "sensitivity": "internal",
            }
            D.build_dataset([row])
            records.append(row)
    return records, rejected


def export_run(repo, run_dir, group_key, lock_file=None):
    """Replay `run_dir` in a child process and return (records, receipt). `group_key` names the task family
    (related items must share it so splits keep them together)."""
    repo = Path(repo).resolve()
    run_dir = Path(run_dir).resolve()
    lock_file = Path(lock_file).resolve() if lock_file else run_dir / "run.lock.json"
    with tempfile.TemporaryDirectory(prefix="symblic-distill-export-") as tmp:
        target = Path(tmp) / "capture.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "_capture",
                "--repo",
                str(repo),
                "--run-dir",
                str(run_dir),
                "--out",
                str(target),
                "--lock-file",
                str(lock_file),
            ],
            capture_output=True,
            timeout=120,
        )
        if proc.returncode:
            raise ExportError(
                "isolated replay refused: "
                + proc.stderr.decode(errors="replace")[-600:]
            )
        captured = load(target)
    raw = coherent_inputs(captured, run_dir, lock_file)
    calls = [json.loads(x) for x in raw["calls.jsonl"].splitlines() if x]
    state = json.loads(raw["state.json"])
    checker = h((repo / LOCK_REPLAY_SOURCE).read_bytes())
    records, rejected = accepted_records(
        state, calls, captured["capture"], run_dir.name, group_key, checker
    )
    return records, {
        "run_id": run_dir.name,
        "replay": captured["replay"],
        "accepted": len(records),
        "rejected": rejected,
        "lock_sha256": captured["input_sha256"]["lock"],
        "input_sha256": {
            f: captured["input_sha256"][f] for f in ["state.json", "calls.jsonl"]
        },
    }


def main(argv=None):
    """Command line: export (records to a new file) or the internal _capture child."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["export", "_capture"])
    p.add_argument("--repo", required=True)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--group-key")
    p.add_argument("--out", required=True)
    p.add_argument("--lock-file")
    a = p.parse_args(argv)
    if a.command == "_capture":
        capture_child(a.repo, a.run_dir, a.out, a.lock_file)
        return 0
    if not a.group_key:
        p.error("--group-key is required: related task families must share it")
    rows, receipt = export_run(a.repo, a.run_dir, a.group_key, a.lock_file)
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(rows, f, ensure_ascii=False)
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ExportError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}), file=sys.stderr)
        sys.exit(2)
