"""Certificates describe observed tests; no models, stores or external effects."""

import copy
import hashlib
import unittest

from symblic.kernel import language as S
from symblic.kernel import certificates as C
from symblic.lang import abstraction as L

SOURCE = 'function double(n: Int) -> Int = n * 2.\ntest "twice" do\nassert double(2) = 4.\nend.\n'
MODULES = {'lib:units': hashlib.sha256(b'fixed module source').hexdigest()}


def report():
    return {'source_sha256': C.source_hash(SOURCE), 'kernel': S.kernel_id(), 'module_hashes': MODULES.copy(),
            'cohorts': [{'by': 'fake:small', 'passed': 2, 'failed': 0, 'error': None},
                        {'by': 'fake:large', 'passed': 2, 'failed': 0, 'error': None}],
            'tests': [{'title': title, 'passed': 2, 'of': 2,
                       'cohorts': [{'by': by, 'status': 'passed', 'error': None, 'calls': 1}
                                   for by in ('fake:small', 'fake:large')]}
                      for title in ('twice', 'zero')], 'all': True, 'certified': ['twice', 'zero']}


def seal(rep=None, **kwargs):
    return C.make_certificate(SOURCE, report() if rep is None else rep, module_hashes=MODULES, **kwargs)


class Certificates(unittest.TestCase):
    def test_exact_pins_and_explicit_order(self):
        cert = seal(candidates=['fake:large', 'fake:small'])
        table = C.route_table(cert, SOURCE, module_hashes=MODULES)
        self.assertEqual(table['candidates'], ['fake:large', 'fake:small'])
        self.assertEqual(table['scope'], 'observed_tests_only')
        self.assertEqual(table['order_basis'], 'declared')
        self.assertEqual(table['independence'], 'not_established')
        self.assertEqual(table['escalation']['action'], 'next_candidate_then_refuse')
        self.assertEqual(cert['assurance'], 'empirical_test_results')
        self.assertEqual(table['model_freshness'], 'not_established')
        self.assertEqual(cert['model_identity_scope'], 'requested_cohort_labels')

    def test_failed_small_model_escalates_to_passing_one(self):
        rep = report()
        rep['tests'][0]['cohorts'][0]['status'] = 'failed'
        rep['tests'][0]['passed'] = 1
        rep['cohorts'][0].update(passed=1, failed=1)
        table = C.route_table(seal(rep), SOURCE, module_hashes=MODULES)
        self.assertEqual(table['candidates'], ['fake:large'])
        self.assertEqual(table['rejected'][0]['by'], 'fake:small')
        self.assertEqual(table['rejected'][0]['reasons'], ['test_not_passed:twice'])

    def test_empty_tests_never_qualify_despite_all_true(self):
        rep = report()
        rep['tests'] = []
        for row in rep['cohorts']:
            row.update(passed=0, failed=0)
        table = C.route_table(seal(rep), SOURCE, module_hashes=MODULES)
        self.assertEqual(table['candidates'], [])
        self.assertEqual(table['status'], 'escalate')

    def test_empty_cohorts_never_qualify(self):
        rep = report()
        rep.update(cohorts=[], tests=[])
        self.assertEqual(C.route_table(seal(rep), SOURCE, module_hashes=MODULES)['status'], 'escalate')

    def test_unknown_candidate_is_not_qualified(self):
        cert = seal(candidates=['fake:unseen', 'fake:small'])
        table = C.route_table(cert, SOURCE, module_hashes=MODULES)
        self.assertEqual(table['candidates'], ['fake:small'])
        self.assertEqual(table['rejected'][0]['reasons'], ['not_observed'])

    def test_no_legacy_report_provenance_can_be_backfilled(self):
        for key in ('source_sha256', 'kernel', 'module_hashes'):
            with self.subTest(key=key):
                rep = report()
                del rep[key]
                cert = seal(rep)
                self.assertFalse(cert['provenance_complete'])
                self.assertTrue(all(not r['qualified'] for r in cert['candidates']))
                self.assertEqual(C.route_table(cert, SOURCE, module_hashes=MODULES)['status'], 'escalate')

    def test_explicit_empty_module_map_is_supported(self):
        rep = report()
        rep['module_hashes'] = {}
        cert = C.make_certificate(SOURCE, rep, module_hashes={})
        self.assertEqual(C.route_table(cert, SOURCE, module_hashes={})['status'], 'qualified')
        self.assertEqual(C.route_table(cert, SOURCE)['status'], 'escalate')

    def test_missing_current_modules_refuses_qualification(self):
        cert = C.make_certificate(SOURCE, report())
        self.assertFalse(cert['provenance_complete'])

    def test_drift_in_any_pin_refuses(self):
        cert = seal()
        variants = [{'source': SOURCE + '\n', 'module_hashes': MODULES},
                    {'source': SOURCE, 'module_hashes': {}},
                    {'source': SOURCE, 'module_hashes': MODULES,
                     'kernel': {**S.kernel_id(), 'canon': -1}}]
        for kwargs in variants:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(C.route_table(cert, **kwargs)['status'], 'escalate')

    def test_informational_python_change_is_not_semantic_drift(self):
        cert = seal()
        kernel = {**S.kernel_id(), 'python': 'different patch version'}
        self.assertEqual(C.route_table(cert, SOURCE, kernel=kernel, module_hashes=MODULES)['status'], 'qualified')

    def test_content_edit_and_version_change_refused(self):
        for field, value in [('assurance', 'proved'), ('symblic_certificate', 999)]:
            cert = seal()
            cert[field] = value
            self.assertEqual(C.route_table(cert, SOURCE, module_hashes=MODULES)['status'], 'escalate')

    def test_rehashed_summary_cannot_upgrade_bad_evidence(self):
        cert = seal()
        cert['report']['cohorts'][0]['error'] = 'worker crashed'
        cert['sha256'] = C.certificate_hash(cert)
        self.assertEqual(C.route_table(cert, SOURCE, module_hashes=MODULES)['status'], 'escalate')

    def test_duplicate_cohort_and_test_rows_refused(self):
        for location in ('cohorts', 'rows', 'titles'):
            with self.subTest(location=location):
                rep = report()
                if location == 'cohorts':
                    rep['cohorts'].append(copy.deepcopy(rep['cohorts'][0]))
                elif location == 'rows':
                    rep['tests'][0]['cohorts'].append(copy.deepcopy(rep['tests'][0]['cohorts'][0]))
                else:
                    rep['tests'].append(copy.deepcopy(rep['tests'][0]))
                with self.assertRaises(C.CertificateError):
                    seal(rep)

    def test_whitespace_does_not_create_duplicate_cohort(self):
        rep = report()
        rep['cohorts'][1]['by'] = ' fake:small '
        with self.assertRaises(C.CertificateError):
            seal(rep)

    def test_missing_result_and_finished_error_cannot_qualify(self):
        rep = report()
        rep['tests'][0]['cohorts'].pop(0)
        rep['tests'][0].update(passed=1, of=1)
        cert = seal(rep)
        self.assertFalse(cert['candidates'][0]['qualified'])
        rep = report()
        rep['cohorts'][0]['error'] = {'message': 'failed after final test'}
        self.assertFalse(seal(rep)['candidates'][0]['qualified'])

    def test_inconsistent_test_summary_is_refused(self):
        rep = report()
        rep['tests'][0]['passed'] = 500
        with self.assertRaises(C.CertificateError):
            seal(rep)

    def test_wrong_execution_pins_are_refused(self):
        for key, value in [('source_sha256', '0' * 64), ('module_hashes', {}),
                           ('kernel', {**S.kernel_id(), 'id': 'wrong'})]:
            with self.subTest(key=key):
                rep = report()
                rep[key] = value
                with self.assertRaises(C.CertificateError):
                    seal(rep)

    def test_inputs_and_outputs_are_detached(self):
        rep = report()
        cert = seal(rep)
        rep['cohorts'][0]['error'] = 'later edit'
        verified = C.validate_certificate(cert, SOURCE, module_hashes=MODULES)
        verified['candidates'][0]['qualified'] = False
        self.assertTrue(cert['candidates'][0]['qualified'])

    def test_kernel_only_tests_do_not_qualify_an_unexercised_model(self):
        rep = report()
        for test in rep['tests']:
            for row in test['cohorts']:
                row['calls'] = 0
        cert = seal(rep)
        self.assertTrue(all('model_not_exercised' in r['reasons'] for r in cert['candidates']))
        self.assertEqual(C.route_table(cert, SOURCE, module_hashes=MODULES)['status'], 'escalate')

    def test_certification_runner_records_actual_module_pins(self):
        class Fake:
            def call(self, request):
                return {'ok': True, 'json': {'answer': 2}, 'ms': 0}

        source = ('import units.\ntest "extract then convert" do\n'
                  'ask n: Int "Read 2."\nassert convert_length(n, "inch", "cm") = 5.08.\nend.\n')
        rep = L.certify(source, ['fake:small', 'fake:large'], lambda _: Fake())
        self.assertTrue(rep['all'], rep)
        modules = rep['module_hashes']
        self.assertIn('lib:units', modules)
        cert = C.make_certificate(source, rep, module_hashes=modules)
        self.assertEqual(C.route_table(cert, source, module_hashes=modules)['candidates'],
                         ['fake:small', 'fake:large'])
        self.assertEqual(C.route_table(cert, source, module_hashes={})['status'], 'escalate')


if __name__ == '__main__':
    unittest.main()
