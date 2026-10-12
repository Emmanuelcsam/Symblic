"""Pure versioned root expectation transport and immutable-reader regressions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.mica import proposal as Q
from symblic.mica import project as P
from symblic.mica import contracts as C
from symblic.graph import run as G
from symblic.mica import native as N


OBJECTIVE = 'Implement public increment.'
BUDGET = C._budget({'max_calls': 4})


def proposal(value=2, *, legacy=False):
    row = {'request': {'objective': OBJECTIVE, 'language': 'javascript',
        'requirements': [{'id': 'increment', 'text': 'Return the input plus one.', 'acceptance': 'TESTED'}],
        'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
        'tests': [{'requirement_ids': ['increment'], 'call': 'inc(1)',
                   ('expected' if legacy else 'expected_value'): value}],
        'allowed_outputs': ['result.js'], 'assumptions': []},
        'objective_coverage': [{'clause_id': 'O001', 'requirement_ids': ['increment']}],
        'missing_decisions': []}
    if not legacy:
        row['proposal_version'] = 3
    return row


def lower(raw):
    return P._proposal_with_encoding(raw, OBJECTIVE, ['result.js'], BUDGET)


class EncodingTest(unittest.TestCase):
    def expected(self, raw):
        return lower(raw)[0]['tests'][0]['expected']

    def test_legacy_expected_text_is_unchanged(self):
        value = '{ "x" : [1, 2.5] }'
        raw = json.dumps(proposal(value, legacy=True))
        req, _decisions, _coverage, receipt = lower(raw)
        self.assertEqual(req['tests'][0]['expected'], value)
        self.assertEqual(receipt['transformation'], 'none')
        self.assertEqual(len(P._proposal(raw, OBJECTIVE, ['result.js'], BUDGET)), 3)

    def test_literal_strings_are_never_interpreted_as_json_or_errors(self):
        for value in ('null', '1', '{"x":1}', "{'x':1}", 'Error: expected a string'):
            with self.subTest(value=value):
                result = self.expected(json.dumps(proposal(value)))
                self.assertEqual(json.loads(result), value)
                self.assertTrue(result.startswith('"'))

    def test_value_types_and_nested_values(self):
        for value in (None, False, True, 2, [1, {'z': None, 'a': 'x'}], {'__proto__': 3, 'constructor': 1}):
            with self.subTest(value=value):
                self.assertEqual(json.loads(self.expected(json.dumps(proposal(value)))), value)

    def test_exact_number_lexemes_and_negative_zero_survive(self):
        template = json.dumps(proposal('__NUMBER__'))
        for number in ('-0', '-0.0', '1.234567890123456789', '1e-300', '1E+7', '9007199254740991'):
            with self.subTest(number=number):
                self.assertEqual(self.expected(template.replace('"__NUMBER__"', number)), number)

    def test_escaped_utf16_string_values_remain_json_text(self):
        for value in ('\ud800', '\udc00', '😀', '\x00\n\\"'):
            with self.subTest(value=repr(value)):
                expected = self.expected(json.dumps(proposal(value), ensure_ascii=True))
                self.assertEqual(json.loads(expected), value)
                expected.encode('utf-8')

    def test_duplicate_keys_rejected_in_envelope_and_value(self):
        raw = json.dumps(proposal('__VALUE__'))
        for bad in (raw.replace('"__VALUE__"', '{"x":1,"x":2}'),
                    raw.replace('"proposal_version": 3', '"proposal_version":3,"proposal_version":3')):
            with self.subTest(raw=bad[-100:]):
                with self.assertRaises(P.ProjectError): lower(bad)

    def test_nonfinite_and_overflow_refused(self):
        raw = json.dumps(proposal('__VALUE__'))
        for number in ('NaN', 'Infinity', '-Infinity', '1e309', '-1e309'):
            with self.subTest(number=number):
                with self.assertRaises(P.ProjectError): lower(raw.replace('"__VALUE__"', number))

    def test_fractional_number_outside_expected_value_is_refused(self):
        row = proposal(); row['request']['version'] = 1.0
        with self.assertRaises(P.ProjectError): lower(json.dumps(row))

    def test_versions_and_mixed_encodings_are_explicit(self):
        for version in (None, 2, 3.0, True, '3'):
            row = proposal(); row['proposal_version'] = version
            with self.subTest(version=version), self.assertRaises(P.ProjectError): lower(json.dumps(row))
        row = proposal(); row.pop('proposal_version')
        with self.assertRaises(P.ProjectError): lower(json.dumps(row))
        row = proposal(); row['request']['tests'][0]['expected'] = '2'
        with self.assertRaises(P.ProjectError): lower(json.dumps(row))
        with self.assertRaises(P.ProjectError): lower(json.dumps(proposal(2, legacy=True)))

    def test_malformed_legacy_object_text_is_not_repaired(self):
        with self.assertRaises(C.ContractError): lower(json.dumps(proposal("{'x':1}", legacy=True)))

    def test_bounded_value_and_raw_source(self):
        with self.assertRaises(P.ProjectError): lower(json.dumps(proposal('x' * 12001)))
        with mock.patch.object(Q, 'MAX_BYTES', 32):
            with self.assertRaises(P.ProjectError): lower(json.dumps(proposal()))
        nested = 1
        for _ in range(40): nested = [nested]
        with self.assertRaises(P.ProjectError): lower(json.dumps(proposal(nested)))

    def test_provenance_links_raw_text_and_exact_lowering(self):
        raw = json.dumps(proposal({'z': [1, None], 'a': False}))
        req, _decisions, coverage, receipt = lower(raw)
        expected = req['tests'][0]['expected']
        self.assertEqual(expected, '{"a":false,"z":[1,null]}')
        self.assertEqual(receipt['raw_proposal_sha256'], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(receipt['tests'][0]['lowered_expected_sha256'], hashlib.sha256(expected.encode()).hexdigest())
        self.assertEqual(receipt['semantic_validation'], 'not_performed')
        self.assertFalse(receipt['independent_evidence'])
        self.assertEqual(coverage['semantic_completeness'], 'unassessed')

    def test_original_authority_and_wrong_semantics_are_not_changed(self):
        row = proposal(99)
        self.assertEqual(self.expected(json.dumps(row)), '99')
        row['request']['objective'] += ' Changed.'
        with self.assertRaises(P.ProjectError): lower(json.dumps(row))
        row = proposal(); row['request']['budget'] = {'max_calls': 900}
        with self.assertRaises(P.ProjectError): lower(json.dumps(row))

    def test_prompt_and_identity_pin_versioned_encoding(self):
        prompt = P.root_prompt(OBJECTIVE, ['result.js'])
        self.assertIn('expected_value', prompt)
        self.assertIn('proposal_version', prompt)
        self.assertEqual(P.ROOT_SPEC_VERSION, 3)
        self.assertEqual(P._identity()['proposal_encoding'], Q.identity())
        with mock.patch.object(Q, '_LOADED_SHA256', '0' * 64):
            with self.assertRaises(Q.ProposalEncodingError): P._identity()


class ReceiptReaderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mica-proposal-reader-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = json.dumps(proposal({'answer': 'null'}))
        request, _decisions, coverage, receipt = lower(self.raw)
        self.manifest = {'version': P.VERSION, 'objective': OBJECTIVE, 'budget': {**BUDGET, 'max_calls': 5},
                         'allowed_outputs': ['result.js'], 'identity': {'proposal_encoding': Q.identity()}}
        self.receipt = {**receipt, 'native_attempt': 'root-000', 'native_pins_sha256': 'a' * 64}
        self.token = {'manifest_sha256': G._hash(self.manifest), 'request': request, 'root_calls': 1,
                      'native_pins_sha256': 'a' * 64, 'root_coverage': coverage, 'proposal_encoding': self.receipt}
        self.result = {'status': 'planned', 'manifest_sha256': G._hash(self.manifest), 'request': request,
                       'request_sha256': C.digest(request), 'root_coverage': coverage, 'proposal_encoding': self.receipt}
        self.native = {'status': 'done', 'output': self.raw, 'pins_sha256': 'a' * 64}
        N._put_once(self.root, P.MANIFEST, self.manifest)
        N._put_once(self.root, P.REQUEST, self.token)
        N._put_once(self.root, P.PLAN, self.result)
        G._mkdir_private(self.root / 'root-attempts/root-000')
        N._put_once(self.root / 'root-attempts/root-000', 'mica-native-result.json', self.native)

    def test_read_only_reader_rebuilds_source_lowering(self):
        self.assertEqual(P.read_project_result(self.root)['proposal_encoding'], self.receipt)

    def test_resealed_lowering_claim_cannot_hide_changed_native_output(self):
        changed = {**self.native, 'output': json.dumps(proposal({'answer': 'changed'}))}
        path = self.root / 'root-attempts/root-000/mica-native-result.json'
        path.unlink(); N._put_once(path.parent, path.name, changed)
        with self.assertRaises(P.ProjectError): P.read_project_result(self.root)

    def test_resealed_receipt_cannot_change_expectation_or_drop_encoding(self):
        for tamper in ('digest', 'missing'):
            with self.subTest(tamper=tamper):
                row = copy.deepcopy(self.token)
                report = copy.deepcopy(self.result)
                if tamper == 'digest':
                    row['proposal_encoding']['tests'][0]['lowered_expected_sha256'] = '0' * 64
                    report['proposal_encoding'] = row['proposal_encoding']
                else:
                    row.pop('proposal_encoding'); report.pop('proposal_encoding')
                with self.assertRaises(P.ProjectError):
                    P._verify_proposal_encoding(self.root, self.manifest, row, report)


if __name__ == '__main__':
    unittest.main()
