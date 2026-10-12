"""Labelled English pixel documents compile through symblic.english.authoring, which keeps the exact document and
pins every file the pixel grammar depends on. No model, no JavaScript execution.

The host's HTTP route cases (check, run, retry of a saved run) moved to tests/integration/test_symblic_english_routes.py.
"""
import copy
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.english import authoring as A
from symblic.english import compiler as E
from symblic.english import pixels as P

ROOT = Path(E.__file__).resolve().parents[2]          # the repository root


class PixelEntry(unittest.TestCase):
    def test_dispatch_preserves_exact_author_document_and_all_statements(self):
        out = A.prepare({'source': P.EXAMPLE})
        self.assertEqual(out['source'], P.compile_source(P.EXAMPLE)['source'])
        self.assertEqual(out['authoring']['document'], P.EXAMPLE)
        self.assertEqual(len(out['statements']), 34)
        self.assertTrue(all(not c.isdigit() for c in P.EXAMPLE))
        self.assertTrue(A.checked_authoring(out['authoring'], out['source']))
        self.assertEqual(out['authoring']['presentation'], out['presentation'])
        self.assertEqual(out['presentation']['kind'], 'binary-pixel-program')
        altered = copy.deepcopy(out['authoring'])
        altered['presentation']['width'] += 1
        self.assertFalse(A.checked_authoring(altered, out['source']))
        for key in ('solve', 'determine', 'side_effects'):
            self.assertFalse(out['options'][key])
        self.assertEqual(out['options']['constructor'], 'off')

    def test_entire_selected_compiler_bundle_is_pinned(self):
        out = A.prepare({'source': P.EXAMPLE})
        from symblic.kernel import execution_pins as execution
        names = {A.COMPILER_FILE} | set(E.compiler_dependencies(P.EXAMPLE)) | A.PIXEL_ASSETS | execution.ASSET_FILES
        hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
        self.assertEqual(out['authoring']['compiler_sha256'], A._digest(hashes))
        original = Path.read_bytes
        for name in (*E.PIXEL_COMPILER_FILES, 'symblic/kernel/language.py', 'symblic/lang/abstraction.py',
                     'symblic/js/check.py', 'symblic/js/contract.py'):
            def changed(path, target=name):
                raw = original(path)
                return raw + b'\n# changed source\n' if path.as_posix().endswith('/' + target) else raw
            with self.subTest(name=name), patch.object(Path, 'read_bytes', changed), \
                    patch.object(P, 'compile_source', side_effect=AssertionError('compiler reached')), \
                    self.assertRaisesRegex(ValueError, 'differs from its source'):
                A.prepare({'source': P.EXAMPLE})

    def test_zero_retries_and_provider_inheritance_survive_public_entry(self):
        out = A.prepare({'source': P.EXAMPLE, 'retries': 0, 'max_calls': 9})
        self.assertEqual(out['options']['max_calls'], 9)
        self.assertIn('retries=0', out['source'])
        self.assertNotIn('ollama:', out['source'])
        self.assertNotIn('openai:', out['source'])


    def test_example_catalog_keeps_prior_lanes(self):
        examples = A.examples()
        self.assertEqual(examples['moving-dot']['source'], P.EXAMPLE)
        self.assertIn('matrix-rain', examples)
        self.assertTrue(set(E.EXAMPLES).issubset(examples))




if __name__ == '__main__':
    unittest.main()
