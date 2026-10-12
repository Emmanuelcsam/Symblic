"""Public metadata indexing without curriculum edits or private source traversal."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import importlib.util

_SCRIPT = Path(__file__).resolve().parents[2] / 'tools/scripts/symblic_refresh_catalog.py'
_SPEC = importlib.util.spec_from_file_location('symblic_refresh_catalog', _SCRIPT)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


class RefreshCatalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='symblic-catalog-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = self.root / 'docs' / 'symblic'
        self.docs.mkdir(parents=True)
        self.path = self.root / 'symblic-academy-content.js'
        self.levels = [{'lvl': 0, 'curated': 'KEEP', 'bites': [
            {'title': 'What an assertion really establishes', 'references': []},
            {'title': 'The denominator and the unit of independence', 'references': []},
            {'title': 'Small spec units and fresh context', 'references': []}]}]
        self.doc('old.md', '# New title\n\n## Boundary\nBody.\n')
        self.catalog = {'levels': copy.deepcopy(self.levels), 'updated': 'author-date',
                        'sources': [{'url': '/docs/symblic/old.md', 'title': 'Old title',
                                     'status': 'Authored scientific limitation', 'sha256': 'stale',
                                     'description': 'Authored description',
                                     'lessons': [{'level': 0, 'bite': 0, 'title': self.levels[0]['bites'][0]['title']}],
                                     'extra': {'keep': True}},
                                    {'url': '/original.pdf', 'title': 'Authored PDF', 'lessons': [], 'status': 'Original'}],
                        'after_sources': {'stable': True}}
        self.raw = '/* authored whitespace */\n' + R.MARKER + json.dumps(self.catalog, indent=2) + ';\n// footer\n'
        self.path.write_text(self.raw)

    def doc(self, name, text):
        path = self.docs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def result(self):
        return R._catalog(self.path.read_text())[0]

    def test_only_source_value_changes_preserving_authored_status_links_and_curriculum(self):
        _, old_start, old_end = R._catalog(self.raw)
        result = R.refresh(self.root)
        updated_raw = self.path.read_text()
        current, start, end = R._catalog(updated_raw)
        self.assertEqual(self.raw[:old_start], updated_raw[:start])
        self.assertEqual(self.raw[old_end:], updated_raw[end:])
        self.assertEqual(current['levels'], self.levels)
        self.assertEqual(current['updated'], 'author-date')
        row = current['sources'][0]
        for key in ('status', 'lessons', 'description', 'extra', 'url'):
            self.assertEqual(row[key], self.catalog['sources'][0][key])
        self.assertEqual(row['title'], 'New title')
        self.assertEqual(row['headings'], ['New title', 'Boundary'])
        self.assertEqual(row['sha256'], hashlib.sha256((self.docs / 'old.md').read_bytes()).hexdigest())
        self.assertEqual(row['provenance']['kind'], 'public_repository_source')
        self.assertEqual(current['sources'][1], self.catalog['sources'][1])
        self.assertTrue(result['written'])

    def test_rerun_is_idempotent_and_check_does_not_write(self):
        before = self.path.read_bytes()
        result = R.refresh(self.root, check=True)
        self.assertTrue(result['stale'])
        self.assertFalse(result['written'])
        self.assertEqual(self.path.read_bytes(), before)
        R.refresh(self.root)
        after = self.path.read_bytes()
        stat = self.path.stat().st_mtime_ns
        self.assertFalse(R.refresh(self.root)['stale'])
        self.assertEqual(self.path.read_bytes(), after)
        self.assertEqual(self.path.stat().st_mtime_ns, stat)

    def test_all_public_formats_added_with_honest_status_and_clear_lesson_links(self):
        self.doc('PROOF-TERMS.md', '# Proof terms\n\nContract.\n')
        self.doc('benchmarks/matched-example-v1.json', '{"title":"Synthetic manifest","cases":[]}')
        self.doc('examples/new.sym', 'program Explicit example.\nshow 2.\n')
        self.doc('papers/new.symd', '# Example paper\n```symblic\nshow 2.\n```\n')
        self.doc('ignored.txt', 'Not a reader format')
        result = R.refresh(self.root)
        self.assertEqual(result['public_sources'], 5)
        rows = {row['url']: row for row in self.result()['sources']}
        proof = rows['/docs/symblic/PROOF-TERMS.md']
        self.assertEqual(proof['status'], R.NEW_STATUS)
        self.assertIn('conditional on premises', proof['description'])
        self.assertEqual(proof['lessons'][0]['title'], self.levels[0]['bites'][0]['title'])
        dataset = rows['/docs/symblic/benchmarks/matched-example-v1.json']
        self.assertEqual(dataset['title'], 'Synthetic manifest')
        self.assertIn('not model-run evidence', dataset['description'])
        self.assertEqual(rows['/docs/symblic/examples/new.sym']['title'], 'Explicit example')
        self.assertNotIn('/docs/symblic/ignored.txt', rows)
        self.assertFalse(R.refresh(self.root)['stale'])

    def test_new_graph_document_can_be_added_at_final_freeze(self):
        R.refresh(self.root)
        self.doc('AGENT-GRAPHS.md', '# Agent graph runtime\n')
        self.assertEqual(R.refresh(self.root)['added'], ['/docs/symblic/AGENT-GRAPHS.md'])
        row = self.result()['sources'][-1]
        self.assertEqual(row['lessons'][0]['title'], 'Small spec units and fresh context')
        self.assertEqual(row['status'], R.NEW_STATUS)

    def test_headings_exclude_fenced_examples_and_keep_real_setext_headings(self):
        text = '# Real title\n```python\n# fake heading\n```\n## Boundary ##\n~~~text\n# fake too\n~~~\nSubsection\n----------\n'
        self.assertEqual(R._headings(text), [(1, 'Real title'), (2, 'Boundary'), (2, 'Subsection')])

    def test_nested_sources_key_in_curriculum_does_not_select_wrong_array(self):
        self.catalog['levels'][0]['sources'] = ['authored nesting']
        self.path.write_text(R.MARKER + json.dumps(self.catalog) + ';\n')
        R.refresh(self.root)
        self.assertEqual(self.result()['levels'][0]['sources'], ['authored nesting'])

    def test_linked_private_source_or_directory_refuses_without_reading_or_rewriting(self):
        private = self.root / 'private.md'
        private.write_text('PRIVATE DO NOT INDEX')
        (self.docs / 'linked.md').symlink_to(private)
        with self.assertRaisesRegex(ValueError, 'linked content'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)
        (self.docs / 'linked.md').unlink()
        (self.docs / 'linked-directory').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'linked content'):
            R.refresh(self.root)
        self.assertNotIn('PRIVATE DO NOT INDEX', self.path.read_text())

    def test_missing_authored_source_is_reported_without_silently_deleting_link(self):
        (self.docs / 'old.md').unlink()
        with self.assertRaisesRegex(ValueError, 'no longer resolves'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)

    def test_reader_size_limit_and_duplicate_json_fields_fail_before_rewrite(self):
        with patch.object(R, 'MAX_BYTES', 3), self.assertRaisesRegex(ValueError, 'reader limit'):
            R.refresh(self.root)
        self.doc('duplicate.json', '{"title":"first","title":"second"}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)


if __name__ == '__main__':
    unittest.main()
