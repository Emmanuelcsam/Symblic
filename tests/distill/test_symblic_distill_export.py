"""Exporter boundary checks: fake records only, no live stores or provider calls."""

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from symblic.distill import datasets as D
from symblic.distill import export as E


class ExportTests(unittest.TestCase):
    def fixture(self):
        fp = D.digest(7)[:16]
        key = "1" * 64
        src = "2" * 64
        kid = "3" * 16
        digest = "4" * 64
        cap = {
            "key": key,
            "system": "Return JSON.",
            "user": "What is 3 + 4?",
            "schema": {},
            "reply": {},
        }
        obs = {
            "ok": True,
            "answer_hash": fp,
            "request_sha256": key,
            "statement_sha256": "5" * 64,
            "capsule_sha256": "6" * 64,
            "context_manifest": {
                "system_sha256": hashlib.sha256(cap["system"].encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(cap["user"].encode()).hexdigest(),
            },
        }
        check = {
            "passed": True,
            "scope": "encoded_predicate",
            "source_sha256": src,
            "kernel": {"id": kid},
            "bindings": [{"name": "a", "hash": fp}],
            "id": "7" * 64,
            "predicate_sha256": "8" * 64,
            "predicate": "a = 7",
        }
        state = {
            "status": "done",
            "kernel": {"id": kid},
            "evidence": {"source_sha256": src, "checks": [check]},
            "bindings": [
                {
                    "name": "a",
                    "value": 7,
                    "hash": fp,
                    "type": "Int",
                    "meta": {
                        "votes": 1,
                        "evidence": {
                            "observations": [obs],
                            "assurance": "typed_answer",
                        },
                    },
                }
            ],
        }
        call = {
            "key": key,
            "ok": True,
            "app": "ollama:fake@node",
            "reply": {"json": {"answer": 7}},
            "model_identity_raw": {
                "status": "observed",
                "model": "fake",
                "digest": "sha256:" + digest,
                "before": {"digest": "sha256:" + digest},
                "after": {"digest": "sha256:" + digest},
            },
            "identity_check_at_call": {
                "validated": True,
                "pinned": True,
                "refused": False,
            },
        }
        return state, [call], [cap]

    def export(self, args):
        return E.accepted_records(*args, "fake-run", "arithmetic-family", "9" * 64)

    def test_strict_observed_checked_scalar(self):
        rows, rejected = self.export(self.fixture())
        self.assertEqual(len(rows), 1)
        self.assertFalse(rejected)
        self.assertEqual(
            rows[0]["prompt"]["sha256"], D.digest(["Return JSON.", "What is 3 + 4?"])
        )
        self.assertEqual(rows[0]["sensitivity"], "internal")
        D.build_dataset(rows)

    def test_wrong_binding_check_is_not_acceptance(self):
        a = self.fixture()
        a[0]["evidence"]["checks"][0]["bindings"][0]["hash"] = "0" * 16
        rows, rejected = self.export(a)
        self.assertFalse(rows)
        self.assertEqual(rejected[0]["reason"], "no_native_predicate_check_for_answer")

    def test_observed_identity_drift_and_fabricated_prompt_refused(self):
        for field in ["digest", "prompt", "answer", "pinned"]:
            with self.subTest(field=field):
                a = self.fixture()
                if field == "digest":
                    a[1][0]["model_identity_raw"]["after"]["digest"] = (
                        "sha256:" + "0" * 64
                    )
                if field == "prompt":
                    a[2][0]["user"] += " changed"
                if field == "answer":
                    a[1][0]["reply"]["json"]["answer"] = False
                if field == "pinned":
                    a[1][0]["identity_check_at_call"]["pinned"] = False
                with self.assertRaises(E.ExportError):
                    self.export(a)

    def test_oracle_peer_and_feedback_exposures_excluded(self):
        for field in ["oracle_exposed", "peer_exposed", "feedback_exposed"]:
            a = self.fixture()
            a[0]["bindings"][0]["meta"]["evidence"]["observations"][0][field] = True
            rows, rejected = self.export(a)
            self.assertFalse(rows)
            self.assertEqual(rejected[0]["reason"], "feedback_or_oracle_exposed")

    def test_refuses_missing_call_and_missing_capture(self):
        for i in [1, 2]:
            a = list(self.fixture())
            a[i] = []
            with self.assertRaises(E.ExportError):
                self.export(a)

    def test_rejects_contested_and_unsupported_answers(self):
        a = self.fixture()
        a[0]["bindings"][0]["meta"]["contested"] = True
        self.assertFalse(self.export(a)[0])
        a = copy.deepcopy(self.fixture())
        a[0]["bindings"][0]["type"] = "Record"
        self.assertFalse(self.export(a)[0])


if __name__ == "__main__":
    unittest.main()
