"""Importing a constructor run's claims into a notebook through the original host's notebook API.

Moved from tests/constructor/test_symblic_constructor_run.py. It drives integration/host/symblic_memory_api.py on a
run folder it creates itself, so it needs no host store and runs without the host. Fake applicators and a fake
solver worker; temporary run folders only.
"""
import json
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_memory_api as memory
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

from symblic.constructor import journal as J
from tests.constructor import test_symblic_constructor_run as RUN   # a module, so its TestCase is not collected here
from tests.constructor.test_symblic_constructor_run import OPTIONS, SOURCE, helper


class NotebookImport(unittest.TestCase):
    # Reuse the constructor run fixture without re-running its own tests here.
    setUp = RUN.ConstructorRun.setUp
    run_it = RUN.ConstructorRun.run_it
    assert_done = RUN.ConstructorRun.assert_done

    def test_notebook_import_binds_journal_and_refuses_missing_constructor_evidence(self):
        from types import SimpleNamespace
        run, report, _, _ = self.run_it(fake=helper())
        self.assert_done(report)
        (self.folder / 'program.sym').write_text(SOURCE)
        (self.folder / 'meta.json').write_text(json.dumps({'inputs': {}, 'options': OPTIONS}))
        engine = SimpleNamespace(run_dir=lambda ident: str(self.folder))
        with patch.object(memory, '_engine', return_value=engine):
            claims, _values, _selected, source = memory._read_run('a' * 12, None)
            self.assertIn('constructor_journal_sha256', source)
            self.assertEqual(sum(row['origin'] == 'solver_proposal' for row in claims), 1)
            (self.folder / J.FILE).unlink()
            with self.assertRaisesRegex(ValueError, 'journal'):
                memory._read_run('a' * 12, None)


if __name__ == '__main__':
    unittest.main()
