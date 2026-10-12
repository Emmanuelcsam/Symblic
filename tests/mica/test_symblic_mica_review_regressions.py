"""Reproduce independently reviewed authority, recovery and resource journeys.

Only fake providers and private temporary stores are used. The native/JavaScript
checkers see tiny fixed fixtures; clocks and interruption points are controlled.
"""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.providers import ollama_call as B
from symblic.mica import search as M
from symblic.mica import contracts as C
from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request, proposed_unit


class FixtureCrash(BaseException):
    pass


def full_contract(ident="increment", name="inc", uses=(), dependencies=(), examples=None, body=None):
    return {"contract_id": ident, "root_requirement_ids": ["increment"], "objective": body or "Return x plus one.",
            "dependency_contract_ids": list(dependencies),
            "unit": {"names": [name], "heading": name + "(x)", "body": body or "Return x plus one.",
                     "uses": list(uses), "setup": "", "examples": examples or [[name + "(2)", "3"]]},
            "verification_obligations": [{"kind": "unit_examples", "requirement_ids": ["increment"]}]}


class ReviewRegressionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mica-review-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "run"

    def run_mica(self, apps, req=None, plans=None, mode="static", inv=None):
        return M.MicaRun(req or request(), self.path, apps, inventory() if inv is None else inv).execute(
            mode=mode, initial_plans=plans)

    def sealed(self, req, rows, ident="fixture"):
        return C.validate_plan(req, {"id": ident, "contracts": rows})

    def crash_after_first_component(self, apps, req, plans=None, mode="direct"):
        original = M._put
        interrupted = []
        def put(root, name, value):
            result = original(root, name, value)
            if Path(root).name == "components" and not interrupted:
                interrupted.append(name)
                raise FixtureCrash("fixture interruption immediately after component publication")
            return result
        with mock.patch.object(M, "_put", side_effect=put):
            with self.assertRaises(FixtureCrash):
                self.run_mica(apps, req, plans=plans, mode=mode)
        self.assertEqual(len(interrupted), 1)

    def test_declared_export_is_required_even_when_arithmetic_examples_pass(self):
        req = request(retries=1, max_calls=2)
        # These finite checks intentionally say nothing about the declared name;
        # the independent declaration surface must still require inc.
        req["tests"] = [{"requirement_ids": ["increment"], "call": "1 + 1", "expected": "2"}]
        row = full_contract(examples=[["1 + 1", "2"]])
        plan = self.sealed(req, [row])
        apps = FakeApps(lambda req, number: "function other(x) { return x + 1; }" if number == 1
                        else "function inc(x) { return x + 1; }")
        result = self.run_mica(apps, req, plans=[plan])
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 2)
        self.assertEqual(len(apps.requests), 2)
        self.assertIn("function inc", result["output"]["text"])

    def test_only_scoped_authoritative_requirements_reach_a_dependent_worker(self):
        req = request(max_calls=4)
        relevant, unrelated = "AUTHORITATIVE_INCREMENT_SENTINEL", "UNRELATED_CALLER_RULE_SENTINEL"
        req["requirements"][0]["text"] = relevant + ": Return the integer plus one."
        req["exports"][0]["signature"] = "inc(inputInteger)"
        req["requirements"].append({"id": "other", "text": unrelated + ": Preserve the input.", "acceptance": "TESTED"})
        req["tests"].append({"requirement_ids": ["other"], "call": "unrelated(2)", "expected": "2"})
        units = [proposed_unit("a", "plusOne", "BODY_A: return x plus one.", [["plusOne(2)", "3"]]),
                 proposed_unit("b", "unrelated", "BODY_B: preserve the input.", [["unrelated(2)", "2"]]),
                 proposed_unit("final", "inc", "BODY_C: call plusOne(x).", [["inc(2)", "3"]], ["plusOne"])]
        units[1]["requirements"] = ["other"]
        plan = M.proposal_to_plan(C.normalize_request(req), {"units": units})
        def callback(call, number):
            if "BODY_C" in call["prompt"]:
                return "function inc(x) { return plusOne(x); }"
            if "BODY_B" in call["prompt"]:
                return "function unrelated(x) { return x; }"
            return "function plusOne(x) { return x + 1; }"
        apps = FakeApps(callback)
        result = self.run_mica(apps, req, plans=[plan])
        self.assertEqual(result["status"], "done", result)
        leaf = next(row["prompt"] for row in apps.requests if "BODY_C" in row["prompt"])
        self.assertIn(relevant, leaf)
        self.assertIn("inc(inputInteger)", leaf)
        self.assertNotIn(unrelated, leaf)

    def test_oversized_contract_has_structured_resource_refusal_before_dispatch(self):
        req = request()
        row = full_contract(body="Bounded context fixture. " * 80)
        row["resource_budget"] = {"context_chars": 256}
        apps = FakeApps()
        result = self.run_mica(apps, req, plans=[self.sealed(req, [row])])
        self.assertNotEqual(result["status"], "done", result)
        self.assertEqual(result["failure"], "RESOURCE_EXHAUSTION")
        self.assertEqual(result["calls"], 0)
        self.assertFalse(apps.requests)

    def test_unit_zero_call_allowance_is_not_expanded_to_root_allowance(self):
        req = request(max_calls=3)
        row = full_contract(); row["resource_budget"] = {"max_calls": 0}
        apps = FakeApps()
        result = self.run_mica(apps, req, plans=[self.sealed(req, [row])])
        self.assertNotEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 0)
        self.assertFalse(apps.requests)

    def test_unit_deadline_below_native_floor_prevents_provider_dispatch(self):
        req = request(wall_seconds=60)
        row = full_contract(); row["resource_budget"] = {"wall_seconds": 1}
        apps = FakeApps()
        result = self.run_mica(apps, req, plans=[self.sealed(req, [row])])
        self.assertNotEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 0)
        self.assertFalse(apps.requests)

    def test_unit_deadline_rejects_provider_completion_after_its_own_limit(self):
        req = request(wall_seconds=120)
        row = full_contract(); row["resource_budget"] = {"wall_seconds": 30}
        plan = self.sealed(req, [row])
        actual_time = M.time.time
        offset = [0]
        def callback(call, number):
            offset[0] = 31
            return "function inc(x) { return x + 1; }"
        apps = FakeApps(callback)
        with mock.patch.object(M.time, "time", side_effect=lambda: actual_time() + offset[0]):
            result = self.run_mica(apps, req, plans=[plan])
        self.assertNotEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 1)
        self.assertNotIn("output", result)

    def test_component_recovery_after_original_deadline_cannot_publish_success(self):
        apps = FakeApps(); req = request()
        self.crash_after_first_component(apps, req)
        manifest = M._read(self.path, "mica-manifest.json")
        late = manifest["started_ms"] / 1000 + req["budget"]["wall_seconds"] + 1
        with mock.patch.object(M.time, "time", return_value=late):
            result = self.run_mica(apps, req, mode="direct")
        self.assertEqual(result["status"], "exhausted", result)
        self.assertEqual(result["calls"], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertNotIn("output", result)

    def test_recovery_preserves_original_generation_decision_and_call_origin(self):
        apps = FakeApps(); req = request()
        self.crash_after_first_component(apps, req)
        result = self.run_mica(apps, req, mode="direct")
        self.assertEqual(result["status"], "done", result)
        decision = result["attempts"][0]["decisions"][0]
        self.assertEqual(decision["calls"], 1, decision)
        self.assertFalse(decision["reused"], decision)
        self.assertEqual(result["calls"], 1)
        self.assertEqual(len(apps.requests), 1)

    def test_equal_dependency_code_with_changed_contract_has_distinct_artifact_identity(self):
        req = request(max_calls=8, max_candidates=2)
        helper = full_contract("helper", "plusOne", body="BODY_HELPER: return x plus one.")
        consumer = full_contract("consumer", "inc", ["plusOne"], ["helper"], body="BODY_CONSUMER: call plusOne(x).")
        final = full_contract("last", "q", ["inc"], ["consumer"], [["q(0)", "1"]], "BODY_LAST: call inc(x).")
        first = self.sealed(req, [helper, consumer, final], "first")
        changed = copy.deepcopy(helper)
        changed["objective"] = changed["unit"]["body"] = "BODY_HELPER: use integer addition and return x plus one."
        second = self.sealed(req, [changed, consumer, final], "second")
        last_calls = []
        def callback(call, number):
            prompt = call["prompt"]
            if "BODY_LAST" in prompt:
                last_calls.append(number)
                return "function q(x) { return 0; }" if len(last_calls) == 1 else "function q(x) { return inc(x); }"
            if "BODY_CONSUMER" in prompt:
                return "function inc(x) { return plusOne(x); }"
            return "function plusOne(x) { return x + 1; }"
        apps = FakeApps(callback)
        result = self.run_mica(apps, req, plans=[first, second], mode="mica")
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(len(last_calls), 2)
        self.assertEqual(result["calls"], len(apps.requests))

    def test_affirmative_weight_drift_is_rejected_even_for_unknown_catalogue_digest(self):
        nonce = "1" * 32
        observation = {"version": 1, "model": "fixture-small", "nonce": nonce,
            "before": {"at_ms": 1, "name": "fixture-small", "digest": "sha256:" + "a" * 64, "error": None},
            "after": {"at_ms": 2, "name": "fixture-small", "digest": "sha256:" + "b" * 64, "error": None},
            "response_model": "fixture-small"}
        identity = B.identity(observation, "fixture-small", "node-a", "c" * 64, nonce)
        self.assertEqual(B.check(identity)["status"], "drift")
        apps = FakeApps(lambda req, number: {"ok": True, "text": "```js\nfunction inc(x){return x+1;}\n```",
            "model": "fixture-small", "node": "node-a", "ms": 1, "model_identity": identity})
        result = self.run_mica(apps, mode="direct")
        self.assertNotEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 1)
        self.assertEqual(len(apps.requests), 1)

    def test_declared_affine_unit_builds_without_inventory_or_provider_budget(self):
        req = request(max_calls=0)
        row = full_contract(examples=[["inc(0)", "1"], ["inc(1)", "2"]])
        row["construction"] = {"kind": "affine_integer_v1", "parameters": [{"name": "x", "lo": -10, "hi": 10}],
            "coefficient_bounds": [{"lo": -3, "hi": 3}], "intercept_bounds": {"lo": -3, "hi": 3}}
        plan = self.sealed(req, [row])
        apps = FakeApps(lambda *_: AssertionError("Deterministic lane must not dispatch a provider"))
        result = self.run_mica(apps, req, plans=[plan], inv=[])
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 0)
        self.assertEqual(result["costs"]["provider_calls"], 0)
        self.assertFalse(apps.requests)


if __name__ == "__main__":
    unittest.main()
