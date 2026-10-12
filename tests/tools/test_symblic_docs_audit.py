"""Temporary docs only. Native fixtures cannot invoke providers, effects or stores."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'tools/scripts/symblic_docs_audit.py'
spec = importlib.util.spec_from_file_location('docs_audit_under_test', SCRIPT)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class DocsAuditTests(unittest.TestCase):
    def test_instrumented_parser_preserves_stock_fence_coverage_inside_lists(self):
        from markdown_it import MarkdownIt
        text = '1. Item prose.\n   ```symblic\n   assert true.\n   ```\n   More prose.\n   ~~~text\n   words\n   ~~~\n'
        stock = [t for t in MarkdownIt('commonmark', {'maxNesting':64}).parse(text) if t.type == 'fence']
        rows, _ = A.scan_text(text, 'list.md', include_content=True)
        self.assertEqual(len(stock), 2)
        self.assertEqual([(r['opening_line']-1,r['end_line'],r['_content']) for r in rows],
                         [(t.map[0],t.map[1],t.content) for t in stock])

    def test_commonmark_nested_containers_long_fences_and_literal_inner_markers(self):
        text = '> ```symblic\n> let x = 1.\n> ```\n\n- ~~~text\n  prose\n  ~~~~\n\n````markdown\n```symblic\nshow 1.\n```\n````\n'
        rows, candidates = A.scan_text(text, 'fixture.md', include_content=True)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['opening_line'] for r in rows], [1, 5, 9])
        self.assertEqual([r['closing_line'] for r in rows], [3, 7, 13])
        self.assertEqual(rows[0]['_content'], 'let x = 1.\n')
        self.assertIn('```symblic', rows[2]['_content'])
        self.assertEqual(sum(r['role'] == 'literal_fence_content' for r in candidates), 2)
        self.assertEqual(rows[0]['content_sha256'], A.sha(b'> let x = 1.\n'))

    def test_unclosed_empty_and_container_terminated_fences_remain_unclosed(self):
        for text in ('```', '```symblic\nlet x = 1.\n', '~~~text\nunclosed\n',
                     '> ```symblic\n> let x = 1.\noutside\n'):
            with self.subTest(text=text):
                rows, _ = A.scan_text(text, 'unclosed.md')
                self.assertEqual(len(rows), 1)
                self.assertFalse(rows[0]['closed'])
                self.assertIsNone(rows[0]['closing_line'])
                self.assertEqual(rows[0]['status'], 'manual_review')

    def test_crlf_raw_hash_and_normalized_execution_content_stay_distinct(self):
        rows, _ = A.scan_text('```symblic\r\nshow "é".\r\n```\r\n', 'unicode.md', include_content=True)
        self.assertEqual(rows[0]['content_sha256'], A.sha('show "é".\r\n'.encode()))
        self.assertEqual(rows[0]['_content'], 'show "é".\n')
        self.assertNotEqual(rows[0]['content_sha256'], rows[0]['normalized_content_sha256'])

    def test_nonfence_delimiters_are_accounted_without_execution_classification(self):
        text = 'Inline ```` ```symblic ```` example\n\n    ```symblic\n    indented\n    ```\n'
        rows, candidates = A.scan_text(text, 'mentions.md')
        self.assertEqual(rows, [])
        self.assertEqual(len(candidates), 5)
        self.assertTrue(all(row['role'] == 'non_fence_or_manual_review' for row in candidates))

    def test_language_classification_does_not_authorize_execution(self):
        text = '\n'.join('```'+lang+'\nexample\n```' for lang in
                         ['symblic', 'python', 'sh', 'text', 'pseudocode', ''])
        rows, _ = A.scan_text(text, 'classes.md')
        self.assertEqual([row['classification'] for row in rows],
                         ['unknown', 'unknown', 'shell', 'prose', 'proposal', 'unknown'])

    def test_whole_tree_inventory_covers_text_binary_and_hash_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'a.md').write_text('```symblic\nshow 2.\n```\n')
            (root/'b.txt').write_text('~~~text\nother\n~~~\n')
            (root/'binary.png').write_bytes(b'\x89PNG\0\xff')
            saved = A.inventory(root)
            self.assertEqual(saved['coverage']['files'], 3)
            self.assertEqual(saved['coverage']['commonmark_fences'], 2)
            self.assertEqual(saved['coverage']['unaccounted_delimiter_runs'], 0)
            self.assertEqual(saved['files'][2]['status'], 'binary_not_markdown')
            self.assertTrue(A.verify_inventory(root, saved)['ok'])
            (root/'a.md').write_text('```symblic\nshow 3.\n```\n')
            drift = A.verify_inventory(root, saved)
            self.assertFalse(drift['ok'])
            self.assertEqual(drift['changed_paths'], ['a.md'])
            changed = copy.deepcopy(saved);changed['files'][0]['bytes'] += 1
            with self.assertRaisesRegex(ValueError, 'inventory_hash'):
                A.verify_inventory(root, changed)

    def test_symlink_and_bounds_refuse_instead_of_silently_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'real.md').write_text('text')
            (root/'link.md').symlink_to(root/'real.md')
            with self.assertRaisesRegex(ValueError, 'symlink_refused'):
                A.inventory(root)
        with self.assertRaisesRegex(ValueError, 'text_bound'):
            A.scan_text('x'*(A.MAX_FILE_BYTES+1), 'large.md')
        with patch.object(A, 'MAX_CANDIDATES', 1), self.assertRaisesRegex(ValueError, 'delimiter_bound'):
            A.scan_text('inline ``` and ```', 'many.md')

    def test_safe_native_kernel_positive_and_expected_failure(self):
        positive = A.native_case('use profile=verified.\nlet x = 1/3 + 2/3.\nassert x = 1.\nshow x.\n', 'execute')
        self.assertEqual(positive['status'], 'done')
        self.assertEqual(positive['calls'], 0)
        self.assertIsNone(positive['store_folder'])
        negative = A.native_case('assert 1 = 2.\n', 'execute')
        self.assertEqual(negative['status'], 'failed')
        self.assertEqual(negative['error_kind'], 'check')
        syntax = A.native_case('let x = (2 + .\n', 'check')
        self.assertEqual(syntax['status'], 'check_refused')
        self.assertEqual(syntax['error_kind'], 'syntax')

    def test_native_calls_effects_imports_and_dynamic_code_are_refused_before_run(self):
        sources = ['ask x: Int "One".\n', 'observe x = web.search(query="secret").\n',
                   'act x = notes.write(text="secret") with key="one".\n',
                   'import quoted_number from text.\n', 'let x = eval("1+1").\n',
                   'let x = js_test("while(true){}", []).\n', 'use solve=true.\n']
        for source in sources:
            with self.subTest(source=source):
                result = A.native_case(source, 'execute')
                self.assertIn(result['status'], ('refused', 'failed'))
                self.assertEqual(result['calls'], 0)
                self.assertEqual(result['applicator_calls'], 0)
                self.assertEqual(result['effect_calls'], 0)
                self.assertIsNone(result['store_folder'])

    def test_all_manifest_pins_validate_before_any_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'one.md').write_text('```symblic\nassert true.\n```\n')
            row = A.inventory(root)['fences'][0]
            case = {'id':'one','fence_id':row['id'],'content_sha256':row['content_sha256'],
                    'action':'execute','expected_status':'done','expected_error_kind':None}
            manifest = {'schema':'symblic.docs.cases.v1','cases':[case, dict(case,id='bad',content_sha256='0'*64)]}
            with patch.object(A.subprocess, 'run', side_effect=AssertionError('worker should not start')), \
                    self.assertRaisesRegex(ValueError, 'fence_pin_drift'):
                A.run_cases(root, manifest, root)

    def test_invalid_manifest_and_duplicate_json_refuse(self):
        with self.assertRaisesRegex(ValueError, 'duplicate_key'):
            A._json(b'{"cases":[],"cases":[]}')
        with self.assertRaisesRegex(ValueError, 'case_bound'):
            A._manifest({'schema':'symblic.docs.cases.v1','cases':[]})
        with self.assertRaisesRegex(ValueError, 'json_number'):
            A._json(b'{"x":1.5}')

    def test_output_never_overwrites_existing_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'
            A._save(path, {'ok':True})
            with self.assertRaises(FileExistsError):
                A._save(path, {'ok':False})
            self.assertTrue(json.loads(path.read_text())['ok'])


if __name__ == '__main__':
    unittest.main()
