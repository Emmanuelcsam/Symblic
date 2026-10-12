"""Finite affine construction uses native enumeration, never model answers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from symblic.kernel import language as S
from symblic.js import check as JS
from symblic.mica import deterministic as D
from symblic.mica import native as N
from symblic.mica import search as M
from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request, proposed_unit


def contract(name="affine", parameters=("x",), examples=None):
    return {"unit": {"names": [name], "heading": name + "(" + ",".join(parameters) + ")",
                     "body": "Implement the declared bounded integer affine family.", "uses": [], "setup": "",
                     "examples": examples or [[name + "(0)", "1"], [name + "(1)", "3"]]},
            "construction": {"kind": D.KIND,
                "parameters": [{"name": p, "lo": -10, "hi": 10} for p in parameters],
                "coefficient_bounds": [{"lo": -3, "hi": 3} for _ in parameters],
                "intercept_bounds": {"lo": -4, "hi": 4}},
            "dependency_contract_ids": [], "input_artifacts": [], "permitted_effects": []}


class DeterministicTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mica-affine-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "native"

    def execute(self, value):
        compiled = D.compile_contract(value)
        self.assertEqual(compiled["status"], "supported", compiled)
        source = compiled["source"]
        self.assertTrue(S.check(source, execution_profile="verified")["ok"])
        result = N.execute_kernel(source, self.folder, output_binding="candidate", options=compiled["options"])
        self.assertEqual(result["calls"], 0)
        return result["native_report"], result["output"]

    def test_native_planner_can_select_catalogue_then_construct_without_worker_call(self):
        req = request(max_calls=1)
        req['objective'] = 'Implement integer increment on the inclusive input domain -10 through 10.'
        req['requirements'][0]['text'] = 'Return x plus one for integer x in [-10,10]; reject other inputs.'
        unit = proposed_unit('increment', 'inc', req['requirements'][0]['text'], [['inc(0)', '1'], ['inc(1)', '2']])
        unit['construction'] = contract('inc')['construction']
        apps = FakeApps(lambda call, number: json.dumps({'units': [unit], 'assumptions': []}))
        result = M.MicaRun(req, self.folder, apps, inventory()).execute(mode='static')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertIn('affine_integer_v1', apps.requests[0]['prompt'])
        self.assertNotIn('helper(1)', apps.requests[0]['prompt'])
        decision = result['decisions'][0]
        self.assertEqual((decision['strategy'], decision['calls'], decision['route']), ('native_finite', 0, None))
        self.assertTrue(JS.test(result['output']['text'], [['inc(-9)', '-8'], ['inc(7)', '8']])['passed'])

    def test_native_single_variable_solution_generalizes_within_declared_family(self):
        result, code = self.execute(contract())
        self.assertEqual(result["status"], "done", result.get("error"))
        checked = JS.test(code, [["affine(-10)", "-19"], ["affine(7)", "15"], ["affine(10)", "21"]])
        self.assertTrue(checked["passed"], checked)
        determination = result["determinacy"]["asks"][0]
        self.assertEqual(determination["answered_by"], "kernel")
        self.assertTrue(determination["exhaustive"])
        self.assertEqual(determination["passing_count"], 1)
        self.assertEqual(determination["domain"]["size"], 63)

    def test_native_two_variable_solution_uses_all_coefficients_and_intercept(self):
        value = contract("score", ("x", "y"), [["score(0,0)", "4"], ["score(1,0)", "7"], ["score(0,1)", "2"]])
        result, code = self.execute(value)
        self.assertEqual(result["status"], "done", result.get("error"))
        checked = JS.test(code, [["score(5,-2)", "23"], ["score(-2,4)", "-10"]])
        self.assertTrue(checked["passed"], checked)

    def test_underconstrained_family_does_not_choose_a_favorite_or_call_a_model(self):
        value = contract(examples=[["affine(0)", "1"]])
        result, code = self.execute(value)
        self.assertNotEqual(result["status"], "done", result)
        self.assertIsNone(code)
        self.assertEqual(result["determinacy"]["asks"][0]["status"], "underdetermined")

    def test_inconsistent_examples_only_refute_declared_coefficient_family(self):
        value = contract(examples=[["affine(1)", "1"], ["affine(1)", "2"]])
        result, code = self.execute(value)
        self.assertNotEqual(result["status"], "done", result)
        self.assertIsNone(code)
        row = result["determinacy"]["asks"][0]
        self.assertEqual(row["status"], "contradictory")
        self.assertTrue(row["exhaustive"])
        self.assertEqual(row["passing_count"], 0)
        self.assertIn("declared", result["error"]["message"])

    def test_generated_code_rejects_outside_domain_and_noninteger_inputs(self):
        result, code = self.execute(contract())
        self.assertEqual(result["status"], "done", result)
        for expression in ["affine(11)", "affine(0.5)", "affine('1')", "affine(true)", "affine(NaN)", "affine(Infinity)"]:
            with self.subTest(expression=expression):
                self.assertFalse(JS.test(code, [[expression, "3"]])["passed"])

    def test_fragment_bounds_and_dependencies_are_explicit(self):
        value = contract()
        first = D.normalize(value["construction"], value["unit"])
        self.assertEqual(D.normalize(first, value["unit"]), first)
        variants = []
        large = copy.deepcopy(value); large["construction"]["coefficient_bounds"][0] = {"lo": -64, "hi": 64}
        large["construction"]["intercept_bounds"] = {"lo": -64, "hi": 64}; variants.append(large)
        deps = copy.deepcopy(value); deps["dependency_contract_ids"] = ["other"]; variants.append(deps)
        setup = copy.deepcopy(value); setup["unit"]["setup"] = "let external = 2;"; variants.append(setup)
        opaque = copy.deepcopy(value); opaque["construction"]["source"] = "return process.exit()"; variants.append(opaque)
        for row in variants:
            with self.subTest(row=row):
                refusal = D.compile_contract(row)
                self.assertEqual(refusal["status"], "unsupported")
                self.assertNotIn("source", refusal)

    def test_no_call_or_expression_evaluator_is_used_to_parse_examples(self):
        value = contract()
        for call, expected in [("affine(process.exit())", "0"), ("affine(1+1)", "5"),
                               ("affine(1); evil()", "3"), ("affine(1)", "true"),
                               ("affine(1)", '"3"'), ("affine(1e0)", "3"), ("affine(11)", "23")]:
            with self.subTest(call=call, expected=expected):
                row = copy.deepcopy(value); row["unit"]["examples"] = [[call, expected]]
                self.assertEqual(D.compile_contract(row)["status"], "unsupported")

    def test_invalid_identifiers_or_signature_cannot_inject_source(self):
        value = contract()
        for name in ["x) {evil()}", "while", "x;quit()", "a" * 65]:
            row = copy.deepcopy(value); row["construction"]["parameters"][0]["name"] = name
            self.assertEqual(D.compile_contract(row)["status"], "unsupported")
        value["unit"]["heading"] = "affine(other)"
        self.assertEqual(D.compile_contract(value)["reason"], "signature")

    def test_no_implicit_strategy_or_arbitrary_native_source(self):
        row = contract(); del row["construction"]
        result = D.compile_contract(row)
        self.assertEqual((result["status"], result["reason"]), ("unsupported", "undeclared"))
        compiled = D.compile_contract(contract())
        self.assertNotIn("js_test", compiled["source"])
        self.assertNotIn("eval(", compiled["source"])
        self.assertNotIn("by=ollama", compiled["source"])
        self.assertEqual(compiled["model_calls"], 0)
        self.assertIn("independent", D.compile_contract.__doc__)

    def test_zero_call_native_attempt_replays_and_refuses_changed_source(self):
        compiled = D.compile_contract(contract())
        first = N.execute_kernel(compiled["source"], self.folder, output_binding="candidate", options=compiled["options"])
        self.assertEqual(first["status"], "done", first)
        self.assertEqual(first["calls"], 0)
        second = N.execute_kernel(compiled["source"], self.folder, output_binding="candidate", options=compiled["options"])
        self.assertEqual(second, first)
        with self.assertRaises(ValueError):
            N.execute_kernel(compiled["source"].replace("program Construct", "program Changed"), self.folder,
                              output_binding="candidate", options=compiled["options"])


if __name__ == "__main__":
    unittest.main()
