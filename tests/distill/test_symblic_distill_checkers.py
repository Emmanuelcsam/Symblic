"""Pure native fixtures; temporary bundles, no actual run stores/models/providers."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]      # the repository root
NATIVE = Path(os.environ.get("SYMBLIC_NATIVE_TEST_REPO", str(ROOT)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(NATIVE))
from symblic.kernel import language as S
from symblic.kernel import evidence as E
from symblic.distill import checkers as N


class NativeChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = 'program "Native fixture".\nlet floor = 2.\nask candidate: Int "Propose an integer above floor" from floor.\nensure candidate > floor.\n'
        nodes = S.parse(self.source)["statements"]
        ask = next(n for n in nodes if n.k == "ask")
        ensure = next(n for n in nodes if n.k == "ensure")
        self.contract = {
            "source_sha256": hashlib.sha256(self.source.encode()).hexdigest(),
            "statement_sha256": "a" * 64,
            "kernel_id": S.kernel_id()["id"],
            "checker": {"id": "fixture", "version": 1, "sha256": "b" * 64},
            "predicate_sha256s": [E.digest(E.syntax(ensure.cond))],
            "answer_type": "integer",
        }
        context = {
            "floor": {
                "value": N.pack(2),
                "type": N.pack({"k": "int"}),
                "line": 2,
                "class": "exact",
                "closed": True,
                "hash": S.fingerprint(2),
            }
        }
        entry = {
            "contract": self.contract,
            "source": self.source,
            "name": "candidate",
            "ask_line": ask.line,
            "type": N.pack(ask.type),
            "predicates": [
                {
                    "ast": N.pack(ensure.cond),
                    "context": context,
                    "line": ensure.line,
                    "text": "candidate > floor",
                    "predicate_sha256": self.contract["predicate_sha256s"][0],
                }
            ],
        }
        self.bundle = {
            "version": 1,
            "runtime_root": str(NATIVE.resolve()),
            "runtime_sha256": N.runtime_hashes(NATIVE),
            "kernel_id": self.contract["kernel_id"],
            "contracts": {N.contract_key(self.contract): entry},
        }
        self.bundle["bundle_sha256"] = N.digest(self.bundle)

    def entry(self):
        return self.bundle["contracts"][N.contract_key(self.contract)]

    def test_native_truth_not_reference_equality_and_wrong_typed_answers(self):
        # Both 3 and 100 satisfy the actual source predicate; no reference answer is present.
        with mock.patch(
            "socket.socket", side_effect=AssertionError("network forbidden")
        ):
            self.assertTrue(N.evaluate(self.bundle, self.contract, 3)["passed"])
            self.assertTrue(N.evaluate(self.bundle, self.contract, 100)["passed"])
            self.assertFalse(N.evaluate(self.bundle, self.contract, 2)["passed"])
            self.assertFalse(N.evaluate(self.bundle, self.contract, True)["passed"])
            self.assertFalse(N.evaluate(self.bundle, self.contract, "3")["passed"])

    def test_ast_and_source_independently_matched(self):
        original = copy.deepcopy(self.bundle)
        self.entry()["source"] += "let untrusted = 0.\n"
        with self.assertRaisesRegex(N.NativeContractError, "source_digest"):
            N.evaluate(self.bundle, self.contract, 3)
        self.bundle = original
        self.entry()["predicates"][0]["ast"] = N.pack(S.Node("lit", value=True))
        with self.assertRaisesRegex(N.NativeContractError, "source_predicate"):
            N.evaluate(self.bundle, self.contract, 3)

    def test_unsupported_external_function_rejected_before_call(self):
        pred = self.entry()["predicates"][0]
        pred["ast"] = N.pack(S.Node("call", fn="python", args=[], kwargs={}))
        with mock.patch.dict(
            S.BUILTINS, {"python": lambda *a, **k: self.fail("external builtin ran")}
        ):
            with self.assertRaisesRegex(N.NativeContractError, "unsupported_predicate"):
                N.evaluate(self.bundle, self.contract, 3)

    def test_conditionally_executed_predicate_refused(self):
        source = self.source.replace(
            "ensure candidate > floor.",
            "if candidate > 0\n  ensure candidate > floor.\nend.",
        )
        contract = copy.deepcopy(self.contract)
        contract["source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
        bundle = copy.deepcopy(self.bundle)
        entry = copy.deepcopy(self.entry())
        entry["source"] = source
        entry["contract"] = contract
        entry["predicates"][0]["line"] = 5
        bundle["contracts"] = {N.contract_key(contract): entry}
        with self.assertRaisesRegex(N.NativeContractError, "source_predicate"):
            N.evaluate(bundle, contract, 3)

    def test_context_after_answer_or_open_provenance_refused(self):
        for key, value in [("line", 4), ("closed", False), ("class", "structured")]:
            b = copy.deepcopy(self.bundle)
            entry = b["contracts"][N.contract_key(self.contract)]
            entry["predicates"][0]["context"]["floor"][key] = value
            with self.assertRaisesRegex(N.NativeContractError, "nonclosed_context"):
                N.evaluate(b, self.contract, 3)

    def test_stale_kernel_or_runtime_refused(self):
        b = copy.deepcopy(self.bundle)
        b["kernel_id"] = "0" * 16
        with self.assertRaisesRegex(N.NativeContractError, "stale_kernel"):
            N.evaluate(b, self.contract, 3)
        b = copy.deepcopy(self.bundle)
        b["runtime_sha256"]["symblic/kernel/language.py"] = "0" * 64
        with self.assertRaisesRegex(N.NativeContractError, "stale_runtime"):
            N.evaluate(b, self.contract, 3)

    def test_unmarked_imports_do_not_become_semantic_identity_registrations(self):
        # Package __init__ files carry no import marker. Their disk bytes stay pinned, but importing one must
        # not invent an import-marker contract.
        import symblic.mica  # noqa: F401  (loaded on purpose: package modules carry no import marker)
        import symblic.kernel  # noqa: F401

        self.assertIn("symblic/mica/__init__.py", self.bundle["runtime_sha256"])
        self.assertTrue(N.evaluate(self.bundle, self.contract, 3)["passed"])
        self.assertFalse(N.evaluate(self.bundle, self.contract, 2)["passed"])

    def test_full_registered_runtime_coverage_is_required(self):
        # The core kernel files and every marked Symblic module loaded in this process must be pinned.
        for name in ("symblic/kernel/language.py", "symblic/kernel/evidence.py", "symblic/mica/source_identity.py"):
            with self.subTest(name=name):
                bundle = copy.deepcopy(self.bundle)
                bundle["runtime_sha256"].pop(name)
                with self.assertRaisesRegex(N.NativeContractError, "incomplete_native_runtime"):
                    N.evaluate(bundle, self.contract, 3)

    def test_runtime_paths_must_be_repository_relative_sources(self):
        for name in ("../outside.py", "/etc/passwd.py", "symblic/kernel/../kernel/language.py", "README.md"):
            with self.subTest(name=name):
                bundle = copy.deepcopy(self.bundle)
                bundle["runtime_sha256"][name] = "0" * 64
                with self.assertRaisesRegex(N.NativeContractError, "stale_runtime_source"):
                    N.evaluate(bundle, self.contract, 3)

    def test_loaded_registered_identity_still_refuses_tampering(self):
        with mock.patch.object(S, "_symblic_import_identity", {"matched": True}):
            with self.assertRaisesRegex(N.NativeContractError, "loaded_native_identity_mismatch"):
                N.evaluate(self.bundle, self.contract, 3)

    def test_unregistered_api_source_is_still_disk_pinned(self):
        original = N.file_hash
        def changed(path):
            return "0" * 64 if Path(path).as_posix().endswith("symblic/kernel/context_packs.py") else original(path)
        with mock.patch.object(N, "file_hash", side_effect=changed):
            with self.assertRaisesRegex(N.NativeContractError, "stale_runtime_source"):
                N.evaluate(self.bundle, self.contract, 3)

    def test_missing_contract_never_passes(self):
        c = copy.deepcopy(self.contract)
        c["statement_sha256"] = "0" * 64
        with self.assertRaisesRegex(N.NativeContractError, "unregistered_contract"):
            N.evaluate(self.bundle, c, 3)

    def test_durable_bundle_pin_and_isolated_process(self):
        path = Path(self.tmp.name) / "contracts.json"
        path.write_text(json.dumps(self.bundle))
        with mock.patch.object(N.NativeScalarChecker, "bundle_file", path):
            checker = N.NativeScalarChecker()
            self.assertTrue(checker.check(self.contract, 3)["passed"])
            self.assertFalse(checker.check(self.contract, 1)["passed"])
            b = copy.deepcopy(self.bundle)
            b["extra"] = "changed"
            b["bundle_sha256"] = N.digest(
                {k: v for k, v in b.items() if k != "bundle_sha256"}
            )
            path.write_text(json.dumps(b))
            with self.assertRaisesRegex(N.NativeContractError, "bundle_changed"):
                checker.check(self.contract, 3)

    def test_child_limits_do_not_change_parent(self):
        import resource

        before = (
            resource.getrlimit(resource.RLIMIT_CPU),
            resource.getrlimit(resource.RLIMIT_AS),
        )
        result = N._bounded_child("_limits", "unused")
        self.assertLessEqual(result["cpu"][0], 5)
        self.assertLessEqual(result["address_space"][0], 512 * 1024 * 1024)
        self.assertEqual(
            before,
            (
                resource.getrlimit(resource.RLIMIT_CPU),
                resource.getrlimit(resource.RLIMIT_AS),
            ),
        )

    def test_loaded_checker_source_mutation_refuses_identity_and_check(self):
        path = Path(self.tmp.name) / "checker.py"
        raw = Path(N.__file__).read_bytes()
        path.write_bytes(raw)
        namespace = {
            "__name__": "private_checker",
            "__file__": str(path),
            "_SYMBLIC_CHECKER_SOURCE": raw,
        }
        exec(compile(raw, str(path), "exec"), namespace)
        bundle_path = Path(self.tmp.name) / "bundle.json"
        bundle_path.write_text(json.dumps(self.bundle))
        cls = namespace["NativeScalarChecker"]
        cls.bundle_file = bundle_path
        checker = cls()
        path.write_bytes(raw + b"\n# changed after approved load\n")
        for action in [lambda: checker.check(self.contract, 3), checker.identity, cls]:
            with self.assertRaisesRegex(
                namespace["NativeContractError"], "checker_source_changed"
            ):
                action()

    def test_input_ceiling_refuses_before_launch(self):
        with (
            mock.patch.object(N, "MAX_BYTES", 10),
            mock.patch.object(
                N.subprocess, "run", side_effect=AssertionError("must not launch")
            ),
        ):
            with self.assertRaisesRegex(N.NativeContractError, "input_too_large"):
                N._bounded_child("_limits", "unused", {"x": "oversize"})

    def test_capture_snapshot_mutation_refuses(self):
        from symblic.distill import export as X

        run = Path(self.tmp.name) / "run"
        run.mkdir()
        for name in ["state.json", "calls.jsonl", "run.lock.json"]:
            (run / name).write_text("{}")
        pins = {"state.json": X.h(b"{}"), "calls.jsonl": X.h(b"{}"), "lock": X.h(b"{}")}
        captured = {"input_sha256": pins}
        X.coherent_inputs(captured, run, run / "run.lock.json")
        for name in ["state.json", "calls.jsonl", "run.lock.json"]:
            (run / name).write_text('{"changed":true}')
            with self.assertRaisesRegex(X.ExportError, "changed across"):
                X.coherent_inputs(captured, run, run / "run.lock.json")
            (run / name).write_text("{}")

    def test_bundle_digest_tampering_refused(self):
        p = Path(self.tmp.name) / "contracts.json"
        b = copy.deepcopy(self.bundle)
        b["kernel_id"] = "0" * 16
        p.write_text(json.dumps(b))
        with self.assertRaisesRegex(N.NativeContractError, "bundle_digest"):
            N.read_bundle(p)


if __name__ == "__main__":
    unittest.main()
