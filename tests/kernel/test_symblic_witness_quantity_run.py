"""Existing-language integration; fake constructors, local exact checks only."""
import copy
import hashlib
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import execution_pins as X
from symblic.kernel import grounding as G
from symblic.kernel.run import Run


class Apps:
    def __init__(self, *values):
        self.values, self.requests = values, []

    def call(self, request):
        index = len(self.requests)
        self.requests.append(request)
        if not self.values:
            raise AssertionError('No model call is permitted')
        return {'ok': True, 'json': {'answer': self.values[min(index, len(self.values) - 1)]},
                'model': 'fake', 'node': 'isolated'}


def execute(source, inputs=None, apps=None, **options):
    apps = apps or Apps()
    run = Run(source, inputs=inputs, applicators=apps,
              options={'by': 'fake:constructor', 'effort': 'low', 'retries': 0,
                       'profile': 'verified', 'budget': 24000, **options})
    return run, run.execute(), apps


def span(source, text):
    start = source['text'].index(text)
    return G.source_span(source, start, start + len(text))


def invoice():
    source = G.source_record('invoice', 'Invoice total: 120 dollars. Number of items: 3.')
    contract = G.field_contract('total', source, labels=['Invoice total'],
        region=G.source_span(source, 0, len(source['text'])), separator='. ', prefix=': ',
        suffix=' dollars', unit='dollars')
    candidate = {'contract_sha256': contract['sha256'], 'label': span(source, 'Invoice total'),
                 'value': span(source, '120')}
    return source, contract, candidate


class GroundingLanguage(unittest.TestCase):
    def assert_done(self, report):
        self.assertEqual(report['status'], 'done', report.get('error'))

    def test_original_numeric_falsepass_is_rejected_by_declared_field_contract(self):
        source, contract, good = invoice()
        bad = {**good, 'value': span(source, '3')}
        program = ('import text as prose.\ngiven source: Any.\ngiven contract: Any.\n'
                   'given wrong: Any.\ngiven right: Any.\n'
                   'assert prose.quoted_number(source.text, "Number of items: 3", 3).\n'
                   'let rejected=verify_source_field(source,contract,wrong).\n'
                   'let accepted=verify_source_field(source,contract,right).\n'
                   'assert not rejected.accepted and accepted.accepted.\n'
                   'assert accepted.value.numerator="120".\n'
                   'assert accepted.assurance.source_truth="not_established".')
        _, report, apps = execute(program, {'source': source, 'contract': contract, 'wrong': bad, 'right': good})
        self.assert_done(report)
        self.assertEqual(apps.requests, [])

    def test_model_constructs_wrong_then_valid_witness_under_unchanged_caller_contract(self):
        source, contract, good = invoice()
        bad = {**good, 'value': span(source, '3')}
        apps = Apps(bad, good)
        program = ('import text as prose.\ngiven source: Any.\ngiven contract: Any.\n'
                   'let receipt=prose.witnessed_number_in(source,contract).\n'
                   'assert receipt.accepted and receipt.value.numerator="120".')
        run, report, apps = execute(program, {'source': source, 'contract': contract}, apps, retries=1)
        self.assert_done(report)
        self.assertEqual(len(apps.requests), 2)
        self.assertTrue(all(contract['sha256'] in request['prompt'] for request in apps.requests))
        self.assertEqual(S.canon(run.kernel.env.lookup('contract').value), S.canon(contract))
        roots = run.kernel.env.lookup('receipt').meta['epistemic']['assessment']['conditional_on']
        self.assertIn('model_proposal', [root['origin'] for root in roots])

    def test_candidate_cannot_supply_replacement_contract_or_hash(self):
        source, contract, good = invoice()
        replacement = copy.deepcopy(contract)
        replacement['labels'] = ['Number of items']
        for forged in ({**good, 'contract': replacement}, {**good, 'contract_sha256': '0' * 64}):
            with self.subTest(forged=sorted(forged)):
                program = ('given source: Any.\ngiven contract: Any.\ngiven candidate: Any.\n'
                           'let receipt=verify_source_field(source,contract,candidate).\nassert not receipt.accepted.')
                _, report, _ = execute(program, {'source': source, 'contract': contract, 'candidate': forged})
                self.assert_done(report)
        program = ('import text as prose.\ngiven source: Any.\ngiven contract: Any.\n'
                   'let receipt=prose.witnessed_number_in(source,contract).')
        _, report, apps = execute(program, {'source': source, 'contract': contract}, Apps({**good, 'contract': contract}))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(apps.requests), 1)

    def test_summary_hallucination_and_missing_exception_fail(self):
        source = G.source_record('policy', 'Dogs are welcome. Except in the kitchen.')
        first, exception = span(source, 'Dogs are welcome.'), span(source, 'Except in the kitchen.')
        contract = G.summary_contract('policy-summary', source,
                                      required=[{'id': 'exception', 'span': exception}], joiner=' ')
        missing = {'contract_sha256': contract['sha256'], 'spans': [first], 'text': first['quote']}
        invented = {**missing, 'spans': [first, exception], 'text': 'Dogs are allowed everywhere.'}
        good = {**missing, 'spans': [first, exception], 'text': source['text']}
        program = ('given source: Any.\ngiven contract: Any.\ngiven missing: Any.\ngiven invented: Any.\n'
                   'given good: Any.\nassert not verify_source_summary(source,contract,missing).accepted.\n'
                   'assert not verify_source_summary(source,contract,invented).accepted.\n'
                   'assert verify_source_summary(source,contract,good).accepted.')
        _, report, _ = execute(program, {'source': source, 'contract': contract, 'missing': missing,
                                        'invented': invented, 'good': good})
        self.assert_done(report)
        program = ('import text as prose.\ngiven source: Any.\ngiven contract: Any.\n'
                   'let receipt=prose.witnessed_summary_of(source,contract).\nassert receipt.accepted.')
        _, report, apps = execute(program, {'source': source, 'contract': contract}, Apps(missing, good), retries=1)
        self.assert_done(report)
        self.assertEqual(len(apps.requests), 2)

    def test_empty_list_cannot_pass_declared_nonempty_catalog(self):
        source = G.source_record('metals', 'Copper and tin')
        catalog = [{'id': 'copper', 'span': span(source, 'Copper')}, {'id': 'tin', 'span': span(source, 'tin')}]
        contract = G.list_contract('metals', source, catalog=catalog, require_nonempty=True)
        unknown = G.list_contract('unknown', source)
        empty = {'contract_sha256': contract['sha256'], 'items': []}
        unknown_empty = {'contract_sha256': unknown['sha256'], 'items': []}
        good = {'contract_sha256': contract['sha256'], 'items': catalog}
        program = ('given source: Any.\ngiven contract: Any.\ngiven unknown: Any.\ngiven empty: Any.\n'
                   'given unknown_empty: Any.\nlet rejected=verify_source_items(source,contract,empty).\n'
                   'let undecided=verify_source_items(source,unknown,unknown_empty).\n'
                   'assert not rejected.accepted.\nassert undecided.enumeration_complete="unknown".')
        _, report, _ = execute(program, {'source': source, 'contract': contract, 'unknown': unknown,
                                        'empty': empty, 'unknown_empty': unknown_empty})
        self.assert_done(report)
        program = ('import text as prose.\ngiven source: Any.\ngiven contract: Any.\n'
                   'let receipt=prose.witnessed_items_in(source,contract).\nassert receipt.enumeration_complete.')
        _, report, apps = execute(program, {'source': source, 'contract': contract}, Apps(empty, good), retries=1)
        self.assert_done(report)
        self.assertEqual(len(apps.requests), 2)

    def test_source_constructors_native_integer_offsets_and_proposed_summary(self):
        program = ('let source=source_record("s","😀 café",2).\nlet witness=source_span(source,2,6).\n'
                   'assert witness.quote="café".\n'
                   'let proposal=source_proposed_summary(source,"A paraphrase",[witness]).\n'
                   'assert proposal.status="unknown" and proposal.origin="model_proposal".')
        _, report, _ = execute(program)
        self.assert_done(report)

    def test_additive_witness_routine_in_legacy_and_verified_profiles(self):
        source, contract, candidate = invoice()
        program = ('import text as prose.\ngiven source: Any.\ngiven contract: Any.\n'
                   'let receipt=prose.witnessed_number_in(source,contract).\n'
                   'assert receipt.accepted and receipt.assurance.semantic_entailment="not_established".')
        for profile in ('legacy', 'verified'):
            with self.subTest(profile=profile):
                _, report, apps = execute(program, {'source': source, 'contract': contract},
                                          Apps(candidate), profile=profile)
                self.assert_done(report)
                self.assertEqual(report['execution_profile'], profile)
                self.assertEqual(len(apps.requests), 1)


class QuantityLanguage(unittest.TestCase):
    def test_exact_temperature_deltas_intervals_and_overlap(self):
        program = ('let freezing=quantity_convert(quantity_exact(32,"degF"),"degC").\n'
                   'assert freezing.lower=0 and freezing.upper=0.\n'
                   'let difference=quantity_sub(quantity_exact(100,"degC"),freezing).\n'
                   'assert difference.lower=100 and difference.unit.kind="linear".\n'
                   'let heated=quantity_add(freezing,quantity_exact(18,"delta_degF")).\n'
                   'assert heated.lower=10.\n'
                   'let measured=quantity_measure(1.2,0.05,"m").\n'
                   'let centimetres=quantity_convert(measured,"cm").\n'
                   'assert centimetres.lower=115 and centimetres.upper=125.\n'
                   'assert quantity_compare(measured,quantity_exact(1.2,"m")).outcome="indeterminate".\n'
                   'let conservative=quantity_sub(measured,measured).\n'
                   'assert conservative.lower=-0.1 and conservative.upper=0.1.')
        _, report, apps = execute(program)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(apps.requests, [])

    def test_custom_dimension_literals_and_explicit_time(self):
        program = ('let unit=quantity_unit("furlong",[1,0,0,0,0,0,0],201.168).\n'
                   'assert quantity_convert(quantity_exact(1,unit),"m").lower=201.168.\n'
                   'let measurement=quantity_measure(10,1,"cm",{sources:[{id:"ruler",version:"v1",'
                   'observed_at:"2026-10-04T12:00:00Z"}]}).\n'
                   'let temporal=quantity_status(measurement,"2026-10-04T13:00:01Z",max_age_seconds=3600).\n'
                   'assert temporal.freshness="stale" and temporal.observations[1].age_seconds=3601.')
        _, report, _ = execute(program)
        self.assertEqual(report['status'], 'done', report.get('error'))

    def test_dimension_affine_and_zero_crossing_fail_explicitly(self):
        operations = [('quantity_add(quantity_exact(1,"m"),quantity_exact(1,"kg"))', 'dimension'),
                      ('quantity_add(quantity_exact(1,"degC"),quantity_exact(1,"degC"))', 'unit'),
                      ('quantity_mul(quantity_exact(1,"degC"),quantity_exact(1,"m"))', 'unit'),
                      ('quantity_div(quantity_exact(1,"m"),quantity_interval(-1,1,"s"))', 'domain')]
        for expression, kind in operations:
            with self.subTest(expression=expression):
                _, report, apps = execute('let result=' + expression + '.')
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['error']['kind'], kind)
                self.assertEqual(apps.requests, [])

    def test_boolean_dimensions_and_fractional_age_stay_invalid(self):
        for expression in ('quantity_unit("bad",[true,0,0,0,0,0,0])',
                           'quantity_status(quantity_exact(1,"m"),"2026-10-04T12:00:00Z",0.5)'):
            _, report, _ = execute('let result=' + expression + '.')
            self.assertEqual(report['status'], 'failed')


class AdapterPins(unittest.TestCase):
    def test_fixed_lazy_adapters_and_kernel_semantic_versions(self):
        for module, names in [('symblic.kernel.grounding', G.FUNCTIONS),
                              ('symblic.adapters.quantities', {'quantity_unit', 'quantity_compare'})]:
            for name in names:
                self.assertEqual(S.BUILTINS[name]._symblic_adapter, (module, name))
        for key in ('epistemic', 'grounding', 'quantities', 'proof', 'capsule_manifest'):
            self.assertIsNotNone(S.kernel_id()[key])

    def test_all_new_dependencies_are_required_pins_and_drift_refuses_before_model(self):
        added = {'symblic/kernel/epistemic.py', 'symblic/kernel/grounding.py', 'symblic/adapters/quantities.py',
                 'symblic/kernel/profiles.py', 'symblic/adapters/proof.py', 'symblic/adapters/proof_adapter.py'}
        self.assertTrue(added <= X.REQUIRED_FILES <= X.PYTHON_FILES)
        reviewed = {name: hashlib.sha256((X.BASE / name).read_bytes()).hexdigest() for name in X.REQUIRED_FILES}
        program = 'ask result: Int "fixture" by "fake:constructor" with effort=low\n'
        pins = X.build(program, {}, reviewed)
        original = X._read
        for name in sorted(added):
            with self.subTest(name=name), patch.object(X, '_read', side_effect=lambda key, changed=name:
                                                       b'changed' if key == changed else original(key)):
                _, report, apps = execute(program, execution_pins=pins)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['error']['kind'], 'version')
                self.assertEqual(apps.requests, [])


if __name__ == '__main__':
    unittest.main()
