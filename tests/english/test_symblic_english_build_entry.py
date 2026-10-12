"""English construction documents ("Build a character animation ...") enter through the shared English compiler,
and symblic.english.authoring records the exact compiler files used. No model, no JavaScript execution.

The host's HTTP `english/check` route case moved to tests/integration/test_symblic_english_routes.py.
"""
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.english import authoring as A
from symblic.english import build as B
from symblic.english import compiler as E

ROOT = Path(E.__file__).resolve().parents[2]          # the repository root


class ConstructionEntry(unittest.TestCase):
    def test_public_english_compiler_dispatches_and_retains_exact_source(self):
        checked = E.check_source(B.EXAMPLE)
        self.assertTrue(checked['ok'], checked)
        self.assertEqual(checked['compiled'], B.compile_source(B.EXAMPLE))
        self.assertEqual(checked['compiled']['source_sha256'], hashlib.sha256(B.EXAMPLE.encode()).hexdigest())
        self.assertTrue(all(not ch.isdigit() for ch in B.EXAMPLE))

    def test_prepare_hashes_both_executing_compiler_files(self):
        compiled = A.prepare({'source': B.EXAMPLE})
        files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                 for name in ('symblic/english/compiler.py', 'symblic/english/build.py')}
        self.assertEqual(compiled['authoring']['compiler_sha256'], A._digest(files))
        self.assertEqual(compiled['authoring']['compiler_version'], B.VERSION)
        self.assertEqual(compiled['authoring']['document'], B.EXAMPLE)
        self.assertTrue(A.checked_authoring(compiled['authoring'], compiled['source']))
        self.assertFalse(compiled['options']['solve'])
        self.assertFalse(compiled['options']['determine'])
        self.assertFalse(compiled['options']['side_effects'])
        self.assertEqual(compiled['options']['constructor'], 'off')

    def test_scalar_compiler_keeps_its_single_source_identity(self):
        compiled = A.prepare({'source': 'Remember value is 3.\nShow value.'})
        self.assertEqual(compiled['authoring']['compiler_sha256'], hashlib.sha256(Path(E.__file__).read_bytes()).hexdigest())
        self.assertEqual(compiled['authoring']['compiler_version'], E.VERSION)

    def test_changed_loaded_support_file_refuses_before_construction(self):
        E.compile_source(B.EXAMPLE)
        original = Path.read_bytes
        def changed(path):
            raw = original(path)
            return raw + b'\n# different source\n' if path.as_posix().endswith('/symblic/english/build.py') else raw
        with patch.object(Path, 'read_bytes', changed), \
                patch.object(B, 'compile_source', side_effect=AssertionError('compiler reached')), \
                self.assertRaisesRegex(ValueError, 'differs from its source'):
            A.prepare({'source': B.EXAMPLE})

    def test_catalog_exposes_english_example_and_preserves_scalar_examples(self):
        examples = A.examples()
        self.assertEqual(examples['matrix-rain']['source'], B.EXAMPLE)
        self.assertTrue(set(E.EXAMPLES).issubset(examples))
        self.assertNotIn('matrix-rain', E.EXAMPLES)



if __name__ == '__main__':
    unittest.main()
