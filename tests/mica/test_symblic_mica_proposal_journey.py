"""Run on a coherent staged runtime: complete fake-provider proposal journeys."""
import json
from pathlib import Path
import tempfile
import unittest

from symblic.mica import project as P
from tests.mica.test_symblic_mica_execution import FakeApps, inventory
from tests.mica.test_symblic_mica_project import OBJECTIVE, root_proposal, fixture_reply


class ProposalJourney(unittest.TestCase):
    def test_plan_execute_and_reopen_keep_versioned_lowering_without_new_calls(self):
        def reply(req, number):
            if 'missing_decisions' in req['prompt']:
                row = root_proposal()
                row['proposal_version'] = 3
                return json.dumps(row)
            return fixture_reply(req, number)
        apps = FakeApps(reply)
        with tempfile.TemporaryDirectory(prefix='mica-proposal-journey-') as directory:
            root = Path(directory) / 'project'
            project = P.MicaProject(OBJECTIVE, root, apps, inventory(),
                {'max_calls': 3, 'max_candidates': 2, 'retries': 0, 'wall_seconds': 120}, ['result.js'])
            plan = project.plan()
            self.assertEqual(plan['status'], 'planned', plan)
            self.assertEqual(plan['proposal_encoding']['proposal_version'], 3)
            self.assertEqual(plan['calls'], 2)
            result = project.execute()
            self.assertEqual(result['status'], 'done', result)
            self.assertEqual(result['calls'], 3)
            self.assertEqual(result['proposal_encoding'], plan['proposal_encoding'])
            self.assertEqual(P.read_project_result(root), result)
            self.assertEqual(project.execute(), result)
            self.assertEqual(len(apps.requests), 3)

    def test_plain_code_legacy_answer_still_records_no_transformation(self):
        from symblic.mica import native as N
        from symblic.mica import proposal as Q
        from tests.mica.test_symblic_mica_execution import ROUTE
        row = root_proposal()
        row.pop('proposal_version')
        for case in row['request']['tests']:
            case['expected'] = json.dumps(case.pop('expected_value'))
        apps = FakeApps(lambda req, n: json.dumps(row))
        with tempfile.TemporaryDirectory(prefix='mica-legacy-proposal-journey-') as directory:
            source = N.planner_source('Return the legacy JSON document.', ROUTE)
            result = N.execute(source, Path(directory) / 'native', apps, ROUTE, limit=1, output_binding='proposal')
            self.assertEqual(result['status'], 'done', result)
            _, receipt = Q.decode(result['output'])
            self.assertEqual(receipt['encoding'], 'legacy_expected_json_text')
            self.assertEqual(receipt['transformation'], 'none')
            self.assertEqual(len(apps.requests), 1)


if __name__ == '__main__':
    unittest.main()
