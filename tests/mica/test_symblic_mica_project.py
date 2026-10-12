"""Whole objective journeys with native journals and fake providers."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from symblic.mica import project as P
from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request, proposal


OBJECTIVE = "Implement public integer increment."


def root_proposal():
    row = request()
    row.pop("budget")
    row.pop("version")
    for case in row["tests"]:
        case["expected_value"] = json.loads(case.pop("expected"))
    return {"proposal_version": 3, "request": row, "objective_coverage": [{'clause_id': 'O001', 'requirement_ids': ['increment']}],
            "missing_decisions": []}


def fixture_reply(req, number):
    prompt = req["prompt"]
    if "missing_decisions" in prompt:
        return json.dumps(root_proposal())
    if "output_format" in prompt:
        return json.dumps(proposal())
    return "function inc(x) { return x + 1; }"


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mica-project-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "project"

    def project(self, apps, objective=OBJECTIVE, stop=None, **budget):
        return P.MicaProject(objective, self.path, apps, inventory(),
                             {"max_calls": 4, "max_candidates": 2, "retries": 0,
                              "wall_seconds": 120, **budget}, ["result.js"], stop=stop)

    def test_objective_build_preserves_authority_provenance_and_exact_calls(self):
        apps = FakeApps(fixture_reply)
        project = self.project(apps)
        result = project.execute(mode="direct")
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(result["objective"], OBJECTIVE)
        self.assertEqual(result["request"]["objective"], OBJECTIVE)
        self.assertEqual(result["request"]["budget"]["max_calls"], 3)
        self.assertEqual((result["calls"], result["root_calls"], result["construction_calls"]), (2, 1, 1))
        self.assertEqual(result["assurance"], "TESTED_MODEL_PROPOSED_CHECKS")
        self.assertEqual(result["provenance"]["acceptance_tests"], "model_proposed_not_independent")
        self.assertIsNone(result["provenance"]["caller_acceptance_tests"])
        coverage = result['root_coverage']
        self.assertEqual(coverage['structural_coverage'], 'complete')
        self.assertEqual(coverage['semantic_completeness'], 'unassessed')
        self.assertEqual(coverage['clauses'][0]['text'], OBJECTIVE)
        self.assertEqual(coverage['requirements'][0]['public_test_indices'], [0])
        self.assertEqual(P.read_project_result(self.path), result)
        self.assertEqual(project.execute(mode="direct"), result)
        self.assertEqual(len(apps.requests), 2)
        self.assertEqual(result["costs"]["provider_ms"], 2)
        self.assertIsNone(result["costs"]["input_tokens"])

    def test_plan_then_execute_does_not_repeat_root_or_plan_generation(self):
        apps = FakeApps(fixture_reply)
        planned = self.project(apps, max_calls=3).plan()
        self.assertEqual(planned["status"], "planned", planned)
        self.assertEqual(planned["calls"], 2)
        result = self.project(apps, max_calls=3).execute()
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 3)
        self.assertEqual(result["request"]["budget"]["max_calls"], 2)
        self.assertEqual(len(apps.requests), 3)
        self.assertEqual(P.read_project_result(self.path), result)

    def test_unknown_root_delivery_never_runs_child_or_redispatches(self):
        apps = FakeApps(lambda req, n: RuntimeError("fixture acknowledgement lost"))
        first = self.project(apps).execute(mode="direct")
        self.assertEqual(first["status"], "unknown", first)
        self.assertEqual(first["calls"], 1)
        self.assertEqual(self.project(apps).execute(mode="direct")["status"], "unknown")
        self.assertEqual(len(apps.requests), 1)
        self.assertFalse((self.path / "construction").exists())
        self.assertFalse((self.path / P.RESULT).exists())

    def test_root_generation_consumes_original_call_allowance(self):
        apps = FakeApps(fixture_reply)
        result = self.project(apps, max_calls=1).execute(mode="direct")
        self.assertEqual(result["calls"], 1)
        self.assertEqual(result["request"]["budget"]["max_calls"], 0)
        self.assertNotEqual(result["status"], "done")
        self.assertEqual(len(apps.requests), 1)
        self.assertEqual(self.project(apps, max_calls=1).execute(mode="direct"), result)
        self.assertEqual(len(apps.requests), 1)

    def test_invalid_root_is_repaired_with_public_validation_failure(self):
        root_calls = []
        def callback(req, n):
            if "missing_decisions" in req["prompt"]:
                root_calls.append(req["prompt"])
                row = root_proposal()
                if len(root_calls) == 1:
                    row["request"]["budget"] = {"max_calls": 10000}
                return json.dumps(row)
            return fixture_reply(req, n)
        apps = FakeApps(callback)
        result = self.project(apps, max_calls=3).execute(mode="direct")
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 3)
        self.assertIn("MODEL_OUTPUT_ERROR", root_calls[1])
        self.assertEqual(result["request"]["budget"]["max_calls"], 1)

    def test_model_cannot_change_original_objective_or_output_authority(self):
        for field, value in (("objective", "Implement a different problem."),
                             ("allowed_outputs", ["elsewhere.js"])):
            with self.subTest(field=field):
                self.path = Path(self.temp.name) / field
                row = root_proposal(); row["request"][field] = value
                apps = FakeApps(lambda req, n: json.dumps(row))
                result = self.project(apps, max_candidates=1).execute(mode="direct")
                self.assertNotEqual(result["status"], "done", result)
                self.assertEqual(result["last_failure"]["failure"], "INVALID_ROOT_REQUEST")
                self.assertEqual(len(apps.requests), 1)
                self.assertFalse((self.path / "construction").exists())

    def test_consequential_missing_decision_is_explicit_without_approval(self):
        row = {"proposal_version": 3, "request": None, 'objective_coverage': [], "missing_decisions": [{"id": "policy", "question": "Which conflicting rule wins?",
                   "why_consequential": "The requested outputs disagree for the same input."}]}
        apps = FakeApps(lambda req, n: json.dumps(row))
        result = self.project(apps).execute(mode="direct")
        self.assertEqual(result["status"], "missing_decisions", result)
        self.assertEqual(result["missing_decisions"], row["missing_decisions"])
        self.assertEqual(result["calls"], 1)
        self.assertFalse((self.path / "construction").exists())
        self.assertNotIn("approval", result)
        self.assertEqual(self.project(apps).execute(mode="direct"), result)

    def test_frozen_original_budget_cannot_be_enlarged_on_resume(self):
        apps = FakeApps(fixture_reply)
        self.project(apps, max_calls=3).plan(mode="direct")
        with self.assertRaises(ValueError):
            self.project(apps, max_calls=4).execute(mode="direct")
        with self.assertRaises(ValueError):
            self.project(apps, max_calls=3, objective="Altered original objective.").execute(mode="direct")
        self.assertEqual(len(apps.requests), 1)

    def test_original_deadline_survives_planning_and_new_object_on_resume(self):
        apps = FakeApps(fixture_reply)
        planned = self.project(apps).plan(mode="direct")
        self.assertEqual(planned["status"], "planned", planned)
        frozen = P.load_project(self.path)
        elapsed_time = frozen["started_ms"] / 1000 + frozen["budget"]["wall_seconds"] + 1
        with mock.patch.object(P.time, "time", return_value=elapsed_time):
            result = self.project(apps).execute(mode="direct")
        self.assertNotEqual(result["status"], "done", result)
        self.assertEqual(result["calls"], 1)
        self.assertEqual(len(apps.requests), 1)

    def test_zero_budget_or_preexisting_stop_performs_no_provider_call(self):
        apps = FakeApps(fixture_reply)
        result = self.project(apps, max_calls=0).execute(mode="direct")
        self.assertEqual(result["status"], "exhausted", result)
        self.assertEqual(result["calls"], 0)
        self.path = Path(self.temp.name) / "stopped"
        stop = threading.Event(); stop.set()
        stopped = self.project(apps, stop=stop).execute(mode="direct")
        self.assertEqual(stopped["calls"], 0)
        self.assertEqual(stopped["status"], "stopped")
        self.assertFalse((self.path / P.RESULT).exists())
        self.assertFalse(apps.requests)

    def test_root_wall_allowance_below_provider_minimum_is_structured_without_dispatch(self):
        apps = FakeApps(fixture_reply)
        result = self.project(apps, wall_seconds=1).execute(mode="direct")
        self.assertEqual(result["status"], "exhausted", result)
        self.assertEqual(result["failure"], "RESOURCE_EXHAUSTION")
        self.assertEqual(result["calls"], 0)
        self.assertFalse(apps.requests)

    def test_stopped_root_call_stays_charged_and_resumes_in_next_bounded_attempt(self):
        stop = threading.Event()
        def callback(req, number):
            if number == 1:
                stop.set()
                return {"ok": False, "fatal": True, "error": "fixture provider acknowledged cancellation",
                        "model": req["app"]["model"], "node": req["app"]["node"], "ms": 1}
            return fixture_reply(req, number)
        apps = FakeApps(callback)
        result = self.project(apps, stop=stop, max_calls=3).execute(mode="direct")
        self.assertEqual(result["status"], "stopped", result)
        self.assertEqual(result["calls"], 1)
        self.assertEqual(len(apps.requests), 1)
        self.assertFalse((self.path / P.RESULT).exists())
        self.assertFalse((self.path / "root-attempts" / "root-001").exists())
        result = self.project(apps, max_calls=3).execute(mode="direct")
        self.assertEqual(result["status"], "done", result)
        self.assertEqual((result["calls"], result["root_calls"], result["construction_calls"]), (3, 2, 1))
        self.assertEqual(len(apps.requests), 3)
        journal = self.path / "root-attempts" / "root-000" / "graph-calls.jsonl"
        phases = [json.loads(line)["kind"] for line in journal.read_text().splitlines()]
        self.assertEqual(phases, ["intent", "interrupted"])

    def test_native_root_journal_is_audited_even_for_complete_project_replay(self):
        apps = FakeApps(fixture_reply)
        result = self.project(apps).execute(mode="direct")
        self.assertEqual(result["status"], "done", result)
        path = self.path / "root-attempts" / "root-000" / "graph-calls.jsonl"
        path.write_text(path.read_text() + "{incomplete\n")
        with self.assertRaises(ValueError):
            self.project(apps).execute(mode="direct")
        self.assertEqual(len(apps.requests), 2)

    def test_no_ambient_hidden_tests_or_files_enter_specification_context(self):
        hidden = "PRIVATE_EVALUATOR_SENTINEL_22aae991"
        (Path(self.temp.name) / "heldout-tests.json").write_text(json.dumps({"private": hidden}))
        apps = FakeApps(fixture_reply)
        result = self.project(apps).execute(mode="direct")
        self.assertEqual(result["status"], "done", result)
        self.assertNotIn(hidden, json.dumps(apps.requests))
        self.assertNotIn(hidden, json.dumps(result))

    def test_component_library_is_frozen_and_passed_to_construction(self):
        apps = FakeApps(fixture_reply)
        library = Path(self.temp.name) / "library"
        project = P.MicaProject(OBJECTIVE, self.path, apps, inventory(), {"max_calls": 3, "retries": 0},
                                ["result.js"], library=library)
        result = project.execute(mode="direct")
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(P.load_project(self.path)["library"], str(library))
        manifest = P._read(self.path / "construction", "mica-manifest.json")
        self.assertEqual(manifest["library"], str(library))
        with self.assertRaises(ValueError):
            P.MicaProject(OBJECTIVE, self.path, apps, inventory(), {"max_calls": 3, "retries": 0},
                           ["result.js"], library=None).execute(mode="direct")

    def test_placeholder_root_is_charged_repaired_and_never_constructed(self):
        roots = []
        def callback(call, number):
            if 'missing_decisions' in call['prompt']:
                roots.append(call['prompt'])
                row = root_proposal()
                if len(roots) == 1:
                    row['request']['requirements'][0]['text'] = 'Concrete required behavior.'
                return json.dumps(row)
            return fixture_reply(call, number)
        apps = FakeApps(callback)
        result = self.project(apps, max_calls=3).execute(mode='direct')
        self.assertEqual(result['status'], 'done', result)
        self.assertEqual((result['calls'], result['root_calls'], result['construction_calls']), (3, 2, 1))
        self.assertIn('template placeholder', roots[1])
        self.assertNotEqual(result['request']['requirements'][0]['text'], 'Concrete required behavior.')
        self.assertEqual(self.project(apps, max_calls=3).execute(mode='direct'), result)
        self.assertEqual(len(apps.requests), 3)

    def test_read_receipt_rechecks_coverage_even_after_valid_outer_resealing(self):
        apps = FakeApps(fixture_reply)
        result = self.project(apps).execute(mode='direct')
        self.assertEqual(result['status'], 'done', result)
        token = P._read(self.path, P.REQUEST)
        token['root_coverage']['clauses'][0]['text'] = 'Different objective.'
        body = P._body(token)
        (self.path / P.REQUEST).write_text(json.dumps({**body, 'sha256': P.G._hash(body)}))
        with self.assertRaises(P.ProjectError):
            P.read_project_result(self.path)
        self.assertEqual(len(apps.requests), 2)


class RootAdequacyTest(unittest.TestCase):
    """Pure deterministic admission; no native execution or provider boundary."""
    def decode(self, row, objective=OBJECTIVE):
        return P._proposal(json.dumps(row), objective, ['result.js'], P.C._budget({}))

    def multi(self):
        objective = 'Return the input integer plus one.\nPreserve negative inputs.'
        row = root_proposal(); row['request']['objective'] = objective
        row['request']['requirements'].append({'id': 'negative', 'text': 'Negative inputs return the next integer.', 'acceptance': 'TESTED'})
        row['request']['tests'].append({'requirement_ids': ['negative'], 'call': 'inc(-2)', 'expected_value': -1})
        row['objective_coverage'].append({'clause_id': 'O002', 'requirement_ids': ['negative']})
        return objective, row

    def test_unicode_spans_and_quoted_decimal_code_are_exact(self):
        objective = '  Preserve 😀 and use 3.14.\nKeep "a. b" and `f(1.2); g()` unchanged.\nDo not split ```x.y();\nz()``` code.  '
        clauses = P.objective_clauses(objective)
        self.assertEqual(len(clauses), 3)
        for clause in clauses:
            self.assertEqual(objective[clause['start']:clause['end']], clause['text'])
            self.assertEqual(clause['text_sha256'], P.C.digest(clause['text']))
        covered = set()
        for clause in clauses:
            covered.update(range(clause['start'], clause['end']))
        self.assertTrue(all(index in covered or char.isspace() for index, char in enumerate(objective)))
        self.assertEqual(P.objective_clauses(objective), clauses)
        with self.assertRaises(P.ProjectError):
            P.objective_clauses('\n'.join('Clause.' for _ in range(P.MAX_OBJECTIVE_CLAUSES + 1)))

    def test_missing_clause_and_unmapped_requirement_are_rejected(self):
        objective, row = self.multi()
        missing = copy.deepcopy(row); missing['objective_coverage'].pop()
        with self.assertRaises(P.ProjectError):
            self.decode(missing, objective)
        unmapped = copy.deepcopy(row); unmapped['objective_coverage'][1]['requirement_ids'] = ['increment']
        with self.assertRaises(P.ProjectError):
            self.decode(unmapped, objective)
        _, decisions, receipt = self.decode(row, objective)
        self.assertEqual(decisions, [])
        self.assertEqual(receipt['structural_coverage'], 'complete')
        self.assertEqual(receipt['semantic_correspondence'], 'unassessed')
        self.assertEqual(receipt['independent_acceptance'], 'not_established')
        self.assertEqual([part['public_test_indices'] for part in receipt['requirements']], [[0], [1]])

    def test_placeholder_and_prompt_schema_copies_are_rejected(self):
        for text in ('Concrete required behavior.', 'TBD', '<requirement>'):
            row = root_proposal(); row['request']['requirements'][0]['text'] = text
            with self.subTest(text=text), self.assertRaises(P.ProjectError):
                self.decode(row)
        full_prompt = P.root_prompt(OBJECTIVE, ['result.js'])
        self.assertTrue(full_prompt.startswith('Produce a new task-specific'))
        prompt = json.loads(full_prompt.split(P.ROOT_INPUT_MARKER, 1)[1])
        self.assertNotIn('Concrete required behavior.', json.dumps(prompt))
        self.assertNotIn('compute(1)', json.dumps(prompt))
        self.assertEqual(set(prompt['output_format']['required']),
                         {'proposal_version', 'request', 'objective_coverage', 'missing_decisions'})
        self.assertEqual(prompt['output_format']['properties']['proposal_version'], {'const': 3})
        for copied in (prompt, prompt['output_format']):
            with self.assertRaises(P.ProjectError):
                self.decode(copied)

    def test_malformed_coverage_cannot_mint_provenance_or_proof(self):
        original = root_proposal()
        variants = [[], [{'clause_id': 'O999', 'requirement_ids': ['increment']}],
                    [{'clause_id': 'O001', 'requirement_ids': ['unknown']}],
                    [{'clause_id': 'O001', 'requirement_ids': []}],
                    original['objective_coverage'] * 2,
                    [{'clause_id': 'O001', 'requirement_ids': ['increment'], 'proven': True}],
                    [{'clause_id': 'O001', 'requirement_ids': ['increment'], 'origin': 'owner'}]]
        for coverage in variants:
            row = copy.deepcopy(original); row['objective_coverage'] = coverage
            with self.subTest(coverage=coverage), self.assertRaises((P.ProjectError, P.C.ContractError)):
                self.decode(row)
        row = copy.deepcopy(original); row['request']['requirements'][0]['origin'] = 'owner'
        with self.assertRaises(P.C.ContractError):
            self.decode(row)

    def test_coverage_cannot_omit_requirement_tests_or_relabel_model_checks(self):
        objective, row = self.multi(); row['request']['tests'].pop()
        with self.assertRaises(P.C.ContractError):
            self.decode(row, objective)
        row = root_proposal()
        req, _, receipt = self.decode(row)
        self.assertEqual(req['objective'], OBJECTIVE)
        self.assertEqual(receipt['requirements'][0]['origin'], 'model_proposed')
        # A syntactically complete model mapping is still no semantic proof,
        # even when its supplied behavior clearly disagrees with the objective.
        row['request']['requirements'][0]['text'] = 'Always return zero.'
        _, _, incomplete_semantics = self.decode(row)
        self.assertEqual(incomplete_semantics['semantic_completeness'], 'unassessed')

    def test_explicit_caller_exports_cannot_be_replaced_with_generic_compute(self):
        objective = ('Build a library.\nRequired public functions and behavior:\n'
                     'inc(x) returns x plus one.\nidentity(value) returns value unchanged.')
        declarations = P.required_public_exports(objective)
        self.assertEqual([(row['name'], row['signature']) for row in declarations],
                         [('inc', 'inc(x)'), ('identity', 'identity(value)')])
        for row in declarations:
            self.assertEqual(objective[row['start']:row['end']], row['text'])
            self.assertEqual(row['origin'], 'caller_explicit_signature')
        row = root_proposal(); row['request']['objective'] = objective
        row['request']['exports'].append({'name': 'identity', 'signature': 'identity(value)'})
        row['objective_coverage'] = [{'clause_id': clause['id'], 'requirement_ids': ['increment']}
                                     for clause in P.objective_clauses(objective)]
        _, _, receipt = self.decode(row, objective)
        self.assertEqual(receipt['caller_exports'], declarations)
        for exports in ([{'name': 'compute', 'signature': 'compute(input)'}],
                        [{'name': 'inc', 'signature': 'inc(x)'}, {'name': 'identity', 'signature': 'identity()'}]):
            changed = copy.deepcopy(row); changed['request']['exports'] = exports
            with self.subTest(exports=exports), self.assertRaises(P.ProjectError):
                self.decode(changed, objective)
        self.assertEqual(P.required_public_exports('Discuss inc(x) as an example, not a declared interface.'), [])


if __name__ == "__main__":
    unittest.main()
