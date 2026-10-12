"""Differential owner API uses only supplied candidates and the local sandbox.

Moved from tests/spec/: this exercises the HTTP route of the original host dashboard
(integration/host/symblic_engine.py), not the symblic.spec package. The compare route saves no run, so it runs
wherever that module imports; it is skipped when the module cannot be imported. The pure comparison is tested in
tests/spec/test_symblic_spec_compare.py.
"""
import unittest

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    from integration.host import symblic_engine as E
    from tests.integration.test_symblic_engine import Base
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None

from unittest.mock import patch

from tests.spec.test_symblic_spec_compare import CANDIDATES, SHEET


class DifferentialAPI(Base):
    def test_finite_divergence_yields_unanswered_question_without_dispatch(self):
        with patch.object(E, 'start_run', side_effect=AssertionError('unexpected dispatch')):
            response = self.call('POST', 'spec/compare', {'sheet': SHEET, 'candidates': CANDIDATES,
                                                        'probes': ['f(-7)']})
        self.assertEqual(response.status, 200, response.sent)
        self.assertEqual(response.sent['probes'][0]['status'], 'divergent')
        self.assertIsNone(response.sent['proposed_examples'][0]['expected_json'])
        self.assertEqual(self.apps.calls, [])

    def test_bad_inputs_have_visible_api_errors(self):
        for extra in ({'candidates': []}, {'probes': {}}, {'deadline_seconds': True},
                      {'unknown': True}, {'externals': 9}):
            response = self.call('POST', 'spec/compare', {'sheet': SHEET, 'candidates': CANDIDATES,
                                                        'probes': ['f(-7)'], **extra})
            self.assertEqual(response.status, 400, response.sent)
        for malformed in (None, [], 'wrong'):
            with self.assertRaises(E.SymblicApiError):
                E.spec_compare(malformed)
