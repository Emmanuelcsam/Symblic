"""Synthetic offline statistics checks: no runner imports, APIs or real stores."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import importlib.util

_SCRIPT = Path(__file__).resolve().parents[2] / 'tools/scripts/symblic_reinforcement_stats.py'
_SPEC = importlib.util.spec_from_file_location('symblic_reinforcement_stats', _SCRIPT)
stats = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stats)


def plan(item='i1', condition='typed', by='ollama:m@node-a', repeat=None):
    p = {'cell': f'identity|{item}|{condition}|{by}' + (f'-r{repeat}' if repeat else ''),
         'suite': 'identity', 'item': item, 'condition': condition, 'by': by, 'models': ['ollama:m']}
    if repeat:
        p['repeat'] = repeat
    return p


def outcome(p, ok=True, correct=True, fingerprint='same', **extra):
    return {'cell': p['cell'], 'ok': ok, 'correct': correct, 'hash': fingerprint, **extra}


class ReinforcementStats(unittest.TestCase):
    def test_unanimity_only_surviving_responders(self):
        ps = [plan(by=f'ollama:m@node-{"abcd"[i - 1]}') for i in range(1, 5)]
        rs = [outcome(ps[0]), outcome(ps[1]), outcome(ps[2], ok=False, correct=False, error='timeout')]
        result = stats.analyze(ps, rs)
        self.assertEqual(result['coverage']['scheduled'], 4)
        self.assertEqual(result['coverage']['missing'], 1)
        self.assertEqual(result['coverage']['failed_or_error'], 1)
        self.assertEqual(result['coverage']['verified_correct_over_scheduled']['rate'], .5)
        a = result['agreement_by_item'][0]
        self.assertTrue(a['survivor_unanimous'])
        self.assertFalse(a['scheduled_panel_unanimous'])
        self.assertEqual(a['fingerprinted_valid'], 2)
        self.assertEqual(a['pairwise_identical_descriptive']['denominator'], 1)

    def test_shared_wrong_answers_are_not_correct(self):
        ps = [plan(by='a'), plan(by='b')]
        result = stats.analyze(ps, [outcome(p, correct=False) for p in ps])
        a = result['agreement_by_item'][0]
        self.assertTrue(a['scheduled_panel_unanimous'])
        self.assertTrue(a['shared_wrong_survivors'])
        self.assertEqual(result['coverage']['correct_over_valid_scored']['rate'], 0)
        self.assertIsNone(result['identity_counts']['independent_model_count'])

    def test_incomplete_matrix_uses_complete_items_only(self):
        ps = [plan(item=i, condition=c) for i in ('i1', 'i2', 'i3') for c in ('direct', 'typed')]
        rs = [outcome(ps[0], correct=False), outcome(ps[1]), outcome(ps[2]),
              outcome(ps[4]), outcome(ps[5], ok=False, error='failure')]
        result = stats.analyze(ps, rs)
        comp = result['matched_comparisons'][0]
        self.assertEqual(comp['complete_matched_items'], ['i1'])
        self.assertEqual(comp['excluded_missing_failed_or_unscored'], ['i2', 'i3'])
        self.assertEqual(comp['paired_descriptive_differences'][0]['right_minus_left_mean'], 1)
        self.assertEqual([x['matched_correct']['denominator'] for x in comp['lanes']], [1, 1])

    def test_unscheduled_lane_and_completely_missing_condition(self):
        ps = [plan(item='i1', condition='direct'), plan(item='i1', condition='typed'),
              plan(item='i2', condition='direct')]
        comp = stats.analyze(ps, [outcome(ps[0])])['matched_comparisons'][0]
        self.assertEqual(comp['excluded_not_scheduled_everywhere'], ['i2'])
        self.assertEqual(comp['complete_matched_items'], [])
        self.assertIsNone(comp['lanes'][0]['matched_correct']['rate'])
        self.assertIsNone(comp['paired_descriptive_differences'][0]['right_minus_left_mean'])

    def test_duplicates_identical_counted_conflicting_rejected(self):
        p = plan()
        r = outcome(p)
        result = stats.analyze([p], [r, dict(r)])
        self.assertEqual(result['identical_duplicate_rows'], 1)
        self.assertEqual(result['coverage']['observed'], 1)
        for change in ({'correct': False}, {'node': 'node-b'}, {'at': 2}, {'ok': False}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'conflicting duplicate'):
                stats.analyze([p], [r, {**r, **change}])

    def test_invalid_planned_cells(self):
        p = plan()
        invalid = [[], [None], [{**p, 'cell': 'wrong'}], [{**p, 'item': 'different'}],
                   [{**p, 'models': []}], [{**p, 'models': ['m', 'm']}],
                   [{**p, 'by': ''}], [{**p, 'repeat': 0}], [p, p],
                   [p, {**p, 'cell': 'identity|i1|alias|app'}]]
        for ps in invalid:
            with self.subTest(plans=ps), self.assertRaises(ValueError):
                stats.analyze(ps, [])

    def test_invalid_outcome_and_plan_metadata(self):
        p = {**plan(), 'node': 'node-a'}
        for r in (outcome(p, ok=1), outcome(p, correct='yes'), outcome(p, fingerprint=3),
                  outcome(p, by='different'), outcome(p, node='node-b'),
                  outcome(p, cell='unplanned')):
            with self.subTest(row=r), self.assertRaises(ValueError):
                stats.analyze([p], [r])

    def test_unknown_scoring_fingerprints_and_error_excluded(self):
        ps = [plan(by=x) for x in ('a', 'b', 'c')]
        rs = [outcome(ps[0], correct=None, fingerprint=None), outcome(ps[1], error='postcondition'),
              outcome(ps[2], correct=None)]
        result = stats.analyze(ps, rs)
        self.assertEqual(result['coverage']['valid'], 2)
        self.assertEqual(result['coverage']['correctness_unknown_valid'], 2)
        self.assertIsNone(result['coverage']['correct_over_valid_scored']['rate'])
        self.assertFalse(result['agreement_by_item'][0]['survivor_unanimous'])
        self.assertEqual(result['agreement_by_item'][0]['fingerprinted_valid'], 1)

    def test_full_identities_repeats_and_opaque_legacy_cell_aliases(self):
        ps = [plan(by='ollama:m@node-a', repeat='r0'), plan(by='ollama:m@node-b', repeat='r0'),
              plan(by='ollama:m@node-a', repeat='r1')]
        ps[0]['cell'] = 'identity|i1|r0|council'
        ps[0]['by'] = 'ollama:m@node-a+ollama:n@node-b'
        ps[0]['models'] = ['ollama:m', 'ollama:n']
        rs = [outcome(p, node=f'node-{"abc"[i]}') for i, p in enumerate(ps)]
        original = copy.deepcopy((ps, rs))
        result = stats.analyze(ps, rs)
        self.assertEqual(result['identity_counts']['distinct_model_labels'], 2)
        self.assertEqual(result['identity_counts']['item_clusters'], 1)
        self.assertEqual(result['identity_counts']['distinct_applicator_labels'], 3)
        self.assertEqual(len(result['cell_identities']), 3)
        self.assertEqual(result['identity_counts']['observed_nodes'], ['node-a', 'node-b', 'node-c'])
        self.assertEqual((ps, rs), original)
        self.assertEqual(result, stats.analyze(list(reversed(ps)), list(reversed(rs))))

    def test_cli_temp_files_and_visible_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            rows = Path(directory) / 'rows.jsonl'
            p = plan()
            manifest.write_text(json.dumps({'schema_version': 1, 'cells': [p]}), encoding='utf-8')
            rows.write_text(json.dumps(outcome(p)) + '\n', encoding='utf-8')
            args = ['--manifest', str(manifest), '--rows', str(rows)]
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(stats.main(args), 0)
            self.assertEqual(json.loads(out.getvalue())['coverage']['valid'], 1)
            rows.write_text('{broken\n', encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(stats.main(args), 2)
            self.assertIn('analysis failed: invalid JSONL at line 1', err.getvalue())
            manifest.write_text('{"schema_version": true}', encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(stats.main(args), 2)


if __name__ == '__main__':
    unittest.main()
