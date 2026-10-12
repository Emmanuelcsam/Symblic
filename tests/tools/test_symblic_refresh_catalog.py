"""Academy catalog refresh: temporary repositories only, plus read-only checks of the shipped catalog."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[2]
_SCRIPT = REPOSITORY / 'tools/scripts/symblic_refresh_catalog.py'
_SPEC = importlib.util.spec_from_file_location('symblic_refresh_catalog', _SCRIPT)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


class RefreshCatalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='symblic-catalog-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / R.CATALOG
        self.path.parent.mkdir(parents=True)
        self.levels = [{'lvl': 0, 'curated': 'KEEP', 'bites': [
            {'title': 'What an assertion really establishes', 'references': []},
            {'title': 'The denominator and the unit of independence', 'references': []},
            {'title': 'Small spec units and fresh context', 'references': [{'title': 'Example', 'url': '/examples/new.sym'}]}]}]
        self.doc('docs/reference/old.md', '# New title\n\n## Boundary\nBody.\n')
        self.catalog = {'levels': copy.deepcopy(self.levels), 'updated': 'author-date',
                        'sources': [{'url': '/docs/reference/old.md', 'title': 'Old title',
                                     'status': 'Authored scientific limitation', 'sha256': 'stale',
                                     'description': 'Authored description',
                                     'lessons': [{'level': 0, 'bite': 0, 'title': self.levels[0]['bites'][0]['title']}],
                                     'extra': {'keep': True}},
                                    {'url': 'https://example.invalid/original', 'title': 'Authored external source',
                                     'lessons': [], 'status': 'Original'}],
                        'after_sources': {'stable': True}}
        self.write(self.catalog)

    def write(self, catalog):
        self.raw = '/* authored whitespace */\n' + R.MARKER + json.dumps(catalog, indent=2) + ';\n// footer\n'
        self.path.write_text(self.raw)

    def doc(self, relative, text):
        path = self.root / relative
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
        digest = hashlib.sha256((self.root / 'docs/reference/old.md').read_bytes()).hexdigest()
        self.assertEqual(row['sha256'], digest)
        self.assertEqual(row['provenance'], {'kind': 'public_repository_source', 'path': '/docs/reference/old.md',
                                             'sha256': digest, 'indexer': R.INDEXER, 'scope': R.SCOPE})
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

    def test_every_document_root_and_public_format_is_indexed_and_nothing_else(self):
        self.doc('docs/reference/PROOF-TERMS.md', '# Proof terms\n\nContract.\n')
        self.doc('benchmarks/matched-example-v1.json', '{"title":"Synthetic manifest","cases":[]}')
        self.doc('examples/new.sym', 'program Explicit example.\nshow 2.\n')
        self.doc('docs/reference/papers/new.symd', '# Example paper\n```symblic\nshow 2.\n```\n')
        self.doc('kits/demo/sheets/demo.sheet.md', '# Demo sheet\n')
        self.doc('docs/essays/essay.md', '# An essay\n')
        not_indexed = ['docs/reference/ignored.txt', 'README.md', 'symblic/bench/data/package.json', 'web/page.md',
                       'tests/fixtures/case.sym', 'docs/.hidden/note.md', 'examples/__pycache__/cache.json',
                       'kits/node_modules/pkg/README.md', 'examples/.draft.md']
        for relative in not_indexed:
            self.doc(relative, '{"title": "not a public document of the roots"}')
        result = R.refresh(self.root)
        self.assertEqual(result['public_sources'], 7)
        rows = {row['url']: row for row in self.result()['sources']}
        self.assertEqual(result['added'], sorted(set(rows) - {'/docs/reference/old.md', 'https://example.invalid/original'}))
        proof = rows['/docs/reference/PROOF-TERMS.md']
        self.assertEqual(proof['status'], R.NEW_STATUS)
        self.assertIn('conditional on premises', proof['description'])
        self.assertEqual(proof['lessons'][0]['title'], self.levels[0]['bites'][0]['title'])
        dataset = rows['/benchmarks/matched-example-v1.json']
        self.assertEqual(dataset['title'], 'Synthetic manifest')
        self.assertIn('not model-run evidence', dataset['description'])
        example = rows['/examples/new.sym']
        self.assertEqual(example['title'], 'Explicit example')
        self.assertEqual(example['lessons'], [{'level': 0, 'bite': 2, 'title': 'Small spec units and fresh context'}])
        self.assertEqual(rows['/kits/demo/sheets/demo.sheet.md']['title'], 'Demo sheet')
        self.assertIn('not verified', rows['/docs/essays/essay.md']['description'])
        self.assertEqual(rows['/docs/reference/papers/new.symd']['description'], R.DEFAULT_DESCRIPTION)
        for relative in not_indexed:
            self.assertNotIn('/' + relative, rows)
        self.assertFalse(R.refresh(self.root)['stale'])

    def test_new_graph_document_can_be_added_at_final_freeze(self):
        R.refresh(self.root)
        self.doc('docs/reference/AGENT-GRAPHS.md', '# Agent graph runtime\n')
        self.assertEqual(R.refresh(self.root)['added'], ['/docs/reference/AGENT-GRAPHS.md'])
        row = self.result()['sources'][-1]
        self.assertEqual(row['lessons'][0]['title'], 'Small spec units and fresh context')
        self.assertEqual(row['status'], R.NEW_STATUS)

    def test_authored_row_outside_the_document_roots_is_refreshed_but_never_discovered(self):
        self.doc('symblic/bench/data/kept.json', '{"name": "Benchmark data kept beside its code"}')
        self.doc('symblic/bench/data/other.json', '{"name": "Never listed"}')
        self.catalog['sources'].append({'url': '/symblic/bench/data/kept.json', 'title': 'Old', 'sha256': 'stale',
                                        'status': 'Authored', 'lessons': []})
        self.write(self.catalog)
        result = R.refresh(self.root)
        rows = {row['url']: row for row in self.result()['sources']}
        kept = rows['/symblic/bench/data/kept.json']
        self.assertEqual((kept['title'], kept['status']), ('Benchmark data kept beside its code', 'Authored'))
        self.assertEqual(kept['sha256'], hashlib.sha256((self.root / 'symblic/bench/data/kept.json').read_bytes()).hexdigest())
        self.assertNotIn('/symblic/bench/data/other.json', rows)
        self.assertEqual(result['public_sources'], 1)

    def test_authored_rows_cannot_escape_or_name_private_files(self):
        self.doc('private.md', 'PRIVATE DO NOT INDEX')
        self.doc('.env.json', '{"secret": "PRIVATE DO NOT INDEX"}')
        for url in ['/docs/reference/../../private.md', '/docs//reference/old.md', '/.env.json', '/docs/reference/old.py',
                    'docs/reference/old.md', 'http://example.invalid/insecure', '/original.pdf', '/docs/reference',
                    '/examples/__pycache__/cache.json', '']:
            with self.subTest(url=url):
                catalog = copy.deepcopy(self.catalog)
                catalog['sources'].append({'url': url, 'title': 'Hostile', 'lessons': []})
                self.write(catalog)
                with self.assertRaises(ValueError):
                    R.refresh(self.root)
                self.assertEqual(self.path.read_text(), self.raw)
                self.assertNotIn('PRIVATE DO NOT INDEX', self.path.read_text())

    def test_headings_exclude_fenced_examples_and_keep_real_setext_headings(self):
        text = '# Real title\n```python\n# fake heading\n```\n## Boundary ##\n~~~text\n# fake too\n~~~\nSubsection\n----------\n'
        self.assertEqual(R._headings(text), [(1, 'Real title'), (2, 'Boundary'), (2, 'Subsection')])

    def test_nested_sources_key_in_curriculum_does_not_select_wrong_array(self):
        self.catalog['levels'][0]['sources'] = ['authored nesting']
        self.path.write_text(R.MARKER + json.dumps(self.catalog) + ';\n')
        R.refresh(self.root)
        self.assertEqual(self.result()['levels'][0]['sources'], ['authored nesting'])

    def test_linked_private_source_directory_root_or_catalog_refuses_without_reading_or_rewriting(self):
        private = self.root / 'private.md'
        private.write_text('PRIVATE DO NOT INDEX')
        (self.root / 'docs/reference/linked.md').symlink_to(private)
        with self.assertRaisesRegex(ValueError, 'linked content'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)
        (self.root / 'docs/reference/linked.md').unlink()
        (self.root / 'examples').mkdir()
        (self.root / 'examples/linked-directory').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'linked content'):
            R.refresh(self.root)
        (self.root / 'examples/linked-directory').unlink()
        outside = tempfile.TemporaryDirectory(prefix='symblic-outside-')
        self.addCleanup(outside.cleanup)
        (self.root / 'kits').symlink_to(outside.name)
        with self.assertRaisesRegex(ValueError, 'symlinked public documentation roots'):
            R.refresh(self.root)
        (self.root / 'kits').unlink()
        (self.root / 'symblic').mkdir()
        (self.root / 'symblic/data').symlink_to(self.root / 'docs')
        self.catalog['sources'].append({'url': '/symblic/data/reference/old.md', 'title': 'Linked', 'lessons': []})
        self.write(self.catalog)
        with self.assertRaisesRegex(ValueError, 'linked content'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)
        real = self.root / 'catalog-elsewhere.js'
        real.write_text(self.raw)
        self.path.unlink()
        self.path.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'symlinked Academy catalog'):
            R.refresh(self.root)
        self.assertNotIn('PRIVATE DO NOT INDEX', real.read_text())

    def test_missing_authored_source_is_reported_without_silently_deleting_link(self):
        (self.root / 'docs/reference/old.md').unlink()
        with self.assertRaisesRegex(ValueError, r'An authored source row no longer resolves: /docs/reference/old\.md\. '
                                                r'Rename or remove the row'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)

    def test_generated_row_of_a_moved_or_deleted_document_is_dropped_and_reported(self):
        self.doc('docs/reference/POLICY.md', '# Policy\n')
        self.doc('docs/reference/PROOF-TERMS.md', '# Proof terms\n')   # a generated row with an associated lesson
        R.refresh(self.root)
        self.assertEqual(self.result()['sources'][-1]['lessons'][0]['title'], self.levels[0]['bites'][0]['title'])
        moved = self.doc('docs/reference/later/POLICY.md', '# Policy\n')
        (self.root / 'docs/reference/POLICY.md').unlink()
        before = self.path.read_bytes()
        result = R.refresh(self.root, check=True)
        self.assertEqual((result['stale'], result['removed'], result['added']),
                         (True, ['/docs/reference/POLICY.md'], ['/docs/reference/later/POLICY.md']))
        self.assertEqual(self.path.read_bytes(), before)
        R.refresh(self.root)
        urls = [row['url'] for row in self.result()['sources']]
        self.assertNotIn('/docs/reference/POLICY.md', urls)
        self.assertIn('/docs/reference/later/POLICY.md', urls)
        moved.unlink()
        (self.root / 'docs/reference/PROOF-TERMS.md').unlink()
        self.assertEqual(R.refresh(self.root)['removed'],
                         ['/docs/reference/PROOF-TERMS.md', '/docs/reference/later/POLICY.md'])
        current = self.result()
        self.assertEqual([row['url'] for row in current['sources']],
                         ['/docs/reference/old.md', 'https://example.invalid/original'])
        self.assertEqual(current['levels'], self.levels)
        self.assertFalse(R.refresh(self.root)['stale'])

    def test_generated_row_that_a_lesson_links_or_a_person_edited_stops_the_refresh(self):
        self.doc('examples/new.sym', 'program Explicit example.\nshow 2.\n')   # a bite's references link this file
        self.doc('docs/reference/edited.md', '# Edited\n')
        R.refresh(self.root)
        catalog = self.result()
        for row in catalog['sources']:
            if row['url'] == '/docs/reference/edited.md':
                row['description'] = 'A description a person wrote.'
        self.write(catalog)
        (self.root / 'examples/new.sym').unlink()
        with self.assertRaisesRegex(ValueError, r'A generated source row no longer resolves and is not dropped.*: '
                                                r'/examples/new\.sym\. Rename or remove the row'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)
        self.doc('examples/new.sym', 'program Explicit example.\nshow 2.\n')
        (self.root / 'docs/reference/edited.md').unlink()
        with self.assertRaisesRegex(ValueError, r'not dropped.*: /docs/reference/edited\.md\.'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)

    def test_reader_size_limit_and_duplicate_json_fields_fail_before_rewrite(self):
        with patch.object(R, 'MAX_BYTES', 3), self.assertRaisesRegex(ValueError, 'reader limit'):
            R.refresh(self.root)
        self.doc('docs/reference/duplicate.json', '{"title":"first","title":"second"}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            R.refresh(self.root)
        self.assertEqual(self.path.read_text(), self.raw)

    def test_command_line_check_reports_a_needed_refresh_with_exit_status_one(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(R.main(['--root', str(self.root), '--check']), 1)
            self.assertEqual(R.main(['--root', str(self.root)]), 0)
            self.assertEqual(R.main(['--root', str(self.root), '--check']), 0)
        reports = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([r['stale'] for r in reports], [True, True, False])
        self.assertEqual([r['written'] for r in reports], [False, True, False])


class ShippedCatalog(unittest.TestCase):
    """The repository's own catalog (web/academy/symblic-academy-content.js); read only."""

    @classmethod
    def setUpClass(cls):
        cls.raw = (REPOSITORY / R.CATALOG).read_text(encoding='utf-8')
        cls.data = R._catalog(cls.raw)[0]

    def test_every_public_document_is_listed_and_every_listed_file_exists(self):
        urls = [row['url'] for row in self.data['sources']]
        self.assertEqual(len(urls), len(set(urls)))
        missing = sorted(set(R._discover(REPOSITORY)) - set(urls))
        self.assertEqual(missing, [], 'run python3 tools/scripts/symblic_refresh_catalog.py')
        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(url.startswith('https://') or R._document(REPOSITORY, url))

    def test_lesson_links_and_references_point_at_real_bites_and_listed_files(self):
        levels, urls = self.data['levels'], {row['url'] for row in self.data['sources']}
        for row in self.data['sources']:
            for lesson in row['lessons']:
                with self.subTest(url=row['url'], lesson=lesson):
                    self.assertEqual(levels[lesson['level']]['bites'][lesson['bite']]['title'], lesson['title'])
        for level in levels:
            for bite in level['bites']:
                for ref in bite['references']:
                    with self.subTest(bite=bite['title'], url=ref['url']):
                        self.assertTrue(ref['url'].startswith('https://') or ref['url'] in urls)


if __name__ == '__main__':
    unittest.main()
