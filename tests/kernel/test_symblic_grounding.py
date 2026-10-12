"""Source association counterexamples; no providers, stores or external calls."""
import copy
import unittest

from symblic.kernel import grounding as G


def witness(source, text, offset=0):
    start = source['text'].index(text, offset)
    return G.source_span(source, start, start + len(text))


def invoice(source=None, **kw):
    source = source or G.source_record('invoice', 'Invoice total: 120 dollars. Number of items: 3.')
    args = {'labels': ['Invoice total'], 'region': G.source_span(source, 0, len(source['text'])),
            'separator': '. ', 'prefix': ': ', 'suffix': ' dollars', 'unit': 'dollars'}
    args.update(kw)
    return source, G.field_contract('total', source, **args)


def field_candidate(source, contract, number='120', label='Invoice total'):
    return {'contract_sha256': contract['sha256'], 'label': witness(source, label), 'value': witness(source, number)}


class Sources(unittest.TestCase):
    def test_unicode_offsets_are_codepoints_not_bytes_or_utf16(self):
        source = G.source_record('s', '😀 café total: 20')
        quote = witness(source, 'café')
        self.assertEqual(quote['start'], 2)
        self.assertEqual(quote['end'], 6)
        self.assertEqual(G.check_span(source, quote), quote)
        wrong = copy.deepcopy(quote)
        wrong['start'] = 3  # UTF-16 position after emoji.
        with self.assertRaises(G.GroundingError):
            G.check_span(source, wrong)

    def test_source_revision_and_quote_drift_fail(self):
        source = G.source_record('s', 'Total 120', 1)
        span = witness(source, '120')
        for changed in (G.source_record('s', 'Total 120', 2), G.source_record('s', 'Total 121', 1)):
            with self.assertRaises(G.GroundingError):
                G.check_span(changed, span)
        span['quote'] = '20'
        with self.assertRaises(G.GroundingError):
            G.check_span(source, span)

    def test_outside_empty_and_bool_offsets_fail(self):
        source = G.source_record('s', 'text')
        for start, end in ((-1, 3), (0, 99), (3, 2), (True, 3)):
            with self.assertRaises(G.GroundingError):
                G.source_span(source, start, end)
        with self.assertRaises(G.GroundingError):
            G.check_span(source, G.source_span(source, 0, 0))

    def test_cyclic_deep_and_huge_inputs_fail_bounded(self):
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(G.GroundingError):
            G.digest(cycle)
        with self.assertRaises(G.GroundingError):
            G.source_record('s', 'x' * (G.MAX_SOURCE + 1))
        with self.assertRaises(G.GroundingError):
            G.source_record('s', '\ud800')


class FieldContracts(unittest.TestCase):
    def test_correct_invoice_source_relation_is_accepted_with_limited_assurance(self):
        source, contract = invoice()
        report = G.verify_field(source, contract, field_candidate(source, contract))
        self.assertTrue(report['accepted'])
        self.assertEqual(report['value'], {'source_text': '120', 'numerator': '120', 'denominator': '1'})
        self.assertEqual(report['assurance']['scope'], 'declared_literal_field_template')
        self.assertEqual(report['assurance']['semantic_entailment'], 'not_established')
        self.assertEqual(report['assurance']['source_truth'], 'not_established')

    def test_original_wrong_invoice_referent_is_rejected_even_with_exact_quote(self):
        source, contract = invoice()
        bad = field_candidate(source, contract, number='3')
        report = G.verify_field(source, contract, bad)
        self.assertFalse(report['accepted'])
        self.assertEqual(report['issues'][0]['code'], 'unsupported_relation_unit_or_negation')
        bad['label'] = witness(source, 'Number of items')
        self.assertEqual(G.verify_field(source, contract, bad)['issues'][0]['code'], 'wrong_referent')

    def test_aliases_are_explicit_and_case_sensitive(self):
        source = G.source_record('invoice', 'Amount due: 120 dollars')
        _, contract = invoice(source, labels=['Invoice total', 'Amount due'])
        self.assertTrue(G.verify_field(source, contract, field_candidate(source, contract, label='Amount due'))['accepted'])
        _, narrow = invoice(source)
        report = G.verify_field(source, narrow, field_candidate(source, narrow, label='Amount due'))
        self.assertFalse(report['accepted'])
        self.assertEqual(report['issues'][0]['code'], 'missing_label')

    def test_repeated_labels_are_ambiguous_even_when_values_agree(self):
        source = G.source_record('s', 'Invoice total: 120 dollars. Invoice total: 120 dollars')
        _, contract = invoice(source)
        report = G.verify_field(source, contract, field_candidate(source, contract))
        self.assertFalse(report['accepted'])
        self.assertEqual(report['issues'][0]['code'], 'ambiguous_label')

    def test_explicit_region_and_entity_select_the_correct_invoice(self):
        source = G.source_record('s', 'Alice\nInvoice total: 120 dollars\nBob\nInvoice total: 3 dollars')
        begin = source['text'].index('Bob')
        _, contract = invoice(source, region=G.source_span(source, begin, len(source['text'])),
                              separator='\n', entity=witness(source, 'Bob'))
        candidate = {'contract_sha256': contract['sha256'], 'label': witness(source, 'Invoice total', begin),
                     'value': witness(source, '3', begin)}
        good = G.verify_field(source, contract, candidate)
        self.assertTrue(good['accepted'])
        self.assertEqual(good['entity']['quote'], 'Bob')
        candidate['value'] = witness(source, '120')
        self.assertFalse(G.verify_field(source, contract, candidate)['accepted'])
        changed = G.source_record('s', source['text'].replace('Bob', 'Eve'), 2)
        with self.assertRaises(G.GroundingError):
            G.verify_field(changed, contract, candidate)

    def test_currency_unit_and_sign_are_part_of_exact_contract(self):
        source = G.source_record('s', 'Invoice total: €-120.50 kg')
        _, contract = invoice(source, prefix=': €', suffix=' kg', currency='€', unit='kg', separator='\n')
        report = G.verify_field(source, contract, field_candidate(source, contract, number='-120.50'))
        self.assertTrue(report['accepted'])
        self.assertEqual(report['value']['numerator'], '-241')
        self.assertEqual(report['value']['denominator'], '2')
        bad = field_candidate(source, contract, number='120.50')
        self.assertFalse(G.verify_field(source, contract, bad)['accepted'])
        _, wrong_currency = invoice(source, prefix=': $', suffix=' kg', currency='$', unit='kg', separator='\n')
        self.assertFalse(G.verify_field(source, wrong_currency,
                                       field_candidate(source, wrong_currency, number='-120.50'))['accepted'])
        _, wrong_unit = invoice(source, prefix=': €', suffix=' g', currency='€', unit='g', separator='\n')
        self.assertFalse(G.verify_field(source, wrong_unit,
                                       field_candidate(source, wrong_unit, number='-120.50'))['accepted'])

    def test_negation_and_unmodeled_qualifications_refuse(self):
        for text in ('Not Invoice total: 120 dollars', 'Invoice total: not 120 dollars',
                     'Invoice total: 120 dollars except fees', 'Invoice total: 120 dollars, not 100 dollars'):
            source = G.source_record('s', text)
            _, contract = invoice(source)
            report = G.verify_field(source, contract, field_candidate(source, contract))
            self.assertFalse(report['accepted'], text)
            self.assertIn('negation', report['issues'][0]['code'])

    def test_label_substrings_are_not_anchors(self):
        source = G.source_record('s', 'Invoice totality: 120 dollars')
        _, contract = invoice(source)
        report = G.verify_field(source, contract, field_candidate(source, contract))
        self.assertFalse(report['accepted'])
        self.assertEqual(report['issues'][0]['code'], 'missing_label')

    def test_candidate_cannot_replace_contract(self):
        source, contract = invoice()
        candidate = field_candidate(source, contract)
        candidate['contract_sha256'] = '0' * 64
        self.assertEqual(G.verify_field(source, contract, candidate)['issues'][0]['code'], 'contract_changed')
        candidate = field_candidate(source, contract)
        candidate['labels'] = ['Number of items']
        self.assertEqual(G.verify_field(source, contract, candidate)['issues'][0]['code'], 'schema')

    def test_unsupported_decimal_forms_and_number_limits_refuse(self):
        for amount in ('1,250', '1e3', '3/4', '1' * (G.MAX_NUMBER + 1)):
            source = G.source_record('s', f'Invoice total: {amount} dollars')
            _, contract = invoice(source)
            report = G.verify_field(source, contract, field_candidate(source, contract, number=amount))
            self.assertEqual(report['issues'][0]['code'], 'unsupported_number')

    def test_max_gap_and_source_drift_are_explicit_contract_errors(self):
        source = G.source_record('s', 'Invoice total: 120 dollars')
        with self.assertRaises(G.GroundingError):
            invoice(source, max_gap=1)
        _, contract = invoice(source)
        changed = G.source_record('s', 'Invoice total: 3 dollars', 2)
        with self.assertRaises(G.GroundingError) as raised:
            G.verify_field(changed, contract, field_candidate(source, contract))
        self.assertEqual(raised.exception.code, 'stale_source')


class SummaryContracts(unittest.TestCase):
    def setUp(self):
        self.source = G.source_record('s', 'The alloy contains copper and tin. Except recycled batches may contain lead.')
        self.main = witness(self.source, 'The alloy contains copper and tin.')
        self.exception = witness(self.source, 'Except recycled batches may contain lead.')
        self.contract = G.summary_contract('summary', self.source,
                                           required=[{'id': 'main', 'span': self.main},
                                                     {'id': 'exception', 'span': self.exception}])

    def candidate(self, spans, text=None):
        return {'contract_sha256': self.contract['sha256'], 'spans': spans,
                'text': self.contract['joiner'].join(row['quote'] for row in spans) if text is None else text}

    def test_original_bananas_summary_cannot_pass_exact_render(self):
        report = G.verify_summary(self.source, self.contract,
                                  self.candidate([self.main, self.exception], 'Bananas orbit Jupiter.'))
        self.assertFalse(report['accepted'])
        self.assertEqual(report['issues'][0]['code'], 'unwitnessed_summary_text')

    def test_required_exception_cannot_be_omitted(self):
        report = G.verify_summary(self.source, self.contract, self.candidate([self.main]))
        self.assertFalse(report['accepted'])
        self.assertEqual(report['coverage']['missing'], ['exception'])
        self.assertEqual(report['coverage']['checked'], ['main'])

    def test_exact_render_and_declared_coverage_pass_without_semantic_claim(self):
        report = G.verify_summary(self.source, self.contract, self.candidate([self.main, self.exception]))
        self.assertTrue(report['accepted'])
        self.assertTrue(report['coverage']['complete'])
        self.assertEqual(report['rendered'], self.main['quote'] + '\n…\n' + self.exception['quote'])
        self.assertEqual(report['assurance']['semantic_entailment'], 'not_established')

    def test_covering_span_includes_required_exception(self):
        full = G.source_span(self.source, 0, len(self.source['text']))
        report = G.verify_summary(self.source, self.contract, self.candidate([full]))
        self.assertTrue(report['accepted'])
        self.assertEqual(report['coverage']['missing'], [])

    def test_paraphrase_remains_proposal_even_with_exact_source_links(self):
        report = G.proposed_summary(self.source, 'Bananas orbit Jupiter.', [self.main])
        self.assertEqual(report['origin'], 'model_proposal')
        self.assertEqual(report['status'], 'unknown')
        self.assertTrue(report['source_links_checked'])
        self.assertEqual(report['assurance']['semantic_entailment'], 'not_established')
        self.assertNotIn('accepted', report)

    def test_reordering_duplicates_or_empty_quotes_fail(self):
        for spans in ([self.exception, self.main], [self.main, self.main], [G.source_span(self.source, 0, 0)]):
            report = G.verify_summary(self.source, self.contract, self.candidate(spans))
            self.assertFalse(report['accepted'])


class ItemContracts(unittest.TestCase):
    def setUp(self):
        self.source = G.source_record('s', 'The alloy contains copper and tin.')
        self.catalog = [{'id': 'copper', 'span': witness(self.source, 'copper')},
                        {'id': 'tin', 'span': witness(self.source, 'tin')}]

    def candidate(self, contract, items):
        return {'contract_sha256': contract['sha256'], 'items': items}

    def test_original_empty_metals_cannot_claim_complete_finite_catalog(self):
        contract = G.list_contract('metals', self.source, catalog=self.catalog)
        report = G.verify_items(self.source, contract, self.candidate(contract, []))
        self.assertFalse(report['accepted'])
        self.assertTrue(report['returned_items_supported'])
        self.assertFalse(report['enumeration_complete'])
        self.assertEqual(report['coverage']['missing'], ['copper', 'tin'])

    def test_unknown_catalog_does_not_make_empty_list_complete(self):
        contract = G.list_contract('metals', self.source)
        report = G.verify_items(self.source, contract, self.candidate(contract, []))
        self.assertTrue(report['returned_items_supported'])
        self.assertEqual(report['enumeration_complete'], 'unknown')
        self.assertIn('enumeration_completeness', report['unknown'])
        self.assertEqual(report['coverage']['scope'], 'returned_items_only')

    def test_declared_empty_universe_can_complete_with_empty_answer(self):
        contract = G.list_contract('empty', self.source, catalog=[])
        report = G.verify_items(self.source, contract, self.candidate(contract, []))
        self.assertTrue(report['accepted'])
        self.assertTrue(report['enumeration_complete'])

    def test_required_nonempty_defeats_vacuity_without_claiming_completeness(self):
        contract = G.list_contract('metals', self.source, require_nonempty=True)
        report = G.verify_items(self.source, contract, self.candidate(contract, []))
        self.assertFalse(report['accepted'])
        self.assertEqual(report['issues'][0]['code'], 'required_nonempty')
        self.assertEqual(report['enumeration_complete'], 'unknown')

    def test_exact_catalog_ids_and_spans_pass(self):
        contract = G.list_contract('metals', self.source, catalog=self.catalog)
        report = G.verify_items(self.source, contract, self.candidate(contract, list(reversed(self.catalog))))
        self.assertTrue(report['accepted'])
        self.assertTrue(report['enumeration_complete'])
        self.assertEqual(report['coverage']['checked'], ['copper', 'tin'])

    def test_id_substitution_is_not_catalog_support(self):
        contract = G.list_contract('metals', self.source, catalog=self.catalog)
        wrong = [{'id': 'copper', 'span': witness(self.source, 'tin')}]
        report = G.verify_items(self.source, contract, self.candidate(contract, wrong))
        self.assertTrue(report['returned_items_supported'])
        self.assertFalse(report['accepted'])
        self.assertEqual(report['coverage']['extra'], ['copper'])
        self.assertEqual(report['coverage']['missing'], ['copper', 'tin'])

    def test_duplicate_ids_or_occurrences_cannot_count_twice(self):
        contract = G.list_contract('metals', self.source)
        for bad in ([self.catalog[0], self.catalog[0]],
                    [self.catalog[0], {'id': 'other', 'span': self.catalog[0]['span']}]):
            report = G.verify_items(self.source, contract, self.candidate(contract, bad))
            self.assertFalse(report['accepted'])
            self.assertFalse(report['returned_items_supported'])

    def test_cyclic_candidate_refuses_without_hashing_forever(self):
        contract = G.list_contract('metals', self.source)
        cycle = []
        cycle.append(cycle)
        report = G.verify_items(self.source, contract, self.candidate(contract, cycle))
        self.assertFalse(report['accepted'])
        self.assertEqual(report['issues'][0]['code'], 'limit')
        self.assertEqual(report['candidate_sha256'], '')


class KernelAdapter(unittest.TestCase):
    def test_pure_adapter_charges_budget_and_preserves_kernel_values(self):
        # Import only the pure kernel; no model/provider or operational engine.
        from symblic.kernel import language as S
        kernel = S.Kernel(S.Env(), S.KB(), S.Budget(10000))
        source = G.FUNCTIONS['source_record'](kernel, None, 's', 'Invoice total: 120 dollars')
        span = G.FUNCTIONS['source_span'](kernel, None, source, 15, 18)
        self.assertIsInstance(span, dict)
        self.assertEqual(span['quote'], '120')
        with self.assertRaises(S.SymblicError):
            G.FUNCTIONS['source_record'](S.Kernel(S.Env(), S.KB(), S.Budget(1)), None, 's', 'x' * 2000)

    def test_adapter_builders_and_witness_report_work_end_to_end(self):
        from symblic.kernel import language as S
        kernel = S.Kernel(S.Env(), S.KB(), S.Budget(10000))
        call = lambda name, *args, **kwargs: G.FUNCTIONS[name](kernel, None, *args, **kwargs)
        source = call('source_record', 's', 'Invoice total: 120 dollars')
        region = call('source_span', source, 0, len(source['text']))
        contract = call('source_field_contract', 'invoice', source, ('Invoice total',), region,
                        '\n', ': ', ' dollars', unit='dollars')
        candidate = {'contract_sha256': contract['sha256'],
                     'label': call('source_span', source, 0, 13),
                     'value': call('source_span', source, 15, 18)}
        report = call('verify_source_field', source, contract, candidate)
        self.assertTrue(report['accepted'])
        self.assertEqual(report['coverage']['checked'], ('invoice',))
        S.canon(report)



if __name__ == '__main__':
    unittest.main()
