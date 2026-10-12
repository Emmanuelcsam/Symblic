"""Public 13-function parcel journey; fake construction and zero-call artifacts."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from symblic.steps import recovery as A
from symblic.authoring import workcards as W
from symblic.kernel.run import Run

ROOT = Path(__file__).resolve().parents[2]          # the repository root
PUBLIC_REQUEST = ROOT / 'examples/steps-parcel.json'
PUBLIC_INPUTS = ROOT / 'examples/steps-parcel-inputs.json'
REFERENCE_EXPRESSIONS = {
    'parcel_area': 'length * width',
    'parcel_volume': 'parcel_area(length,width) * height',
    'dimensional_weight': 'ceil(volume / divisor)',
    'billable_weight': 'max(actual,dimensional)',
    'billing_units': 'ceil(weight / increment)',
    'base_charge': 'units * rate',
    'is_oversized': 'longest > limit',
    'oversize_charge': 'if oversized then fee else 0',
    'parcel_subtotal': 'base + extra',
    'parcel_discount': 'if subtotal >= threshold then min(promotion,subtotal) else 0',
    'taxable_charge': 'subtotal - discount',
    'sales_tax': 'ceil(amount * numerator / denominator)',
    'parcel_total': 'taxable + tax',
}


class ParcelProposals:
    def __init__(self, request, wrong):
        self.steps = request['steps']
        self.wrong = wrong
        self.step_indexes = []

    def call(self, request):
        cards = [row['name'] for row in request['context_manifest']['included']
                 if re.fullmatch(r'brick_card_\d+', row['name'])]
        if len(cards) != 1:
            raise AssertionError('Each proposal must receive exactly one step card')
        index = int(cards[0].rsplit('_', 1)[1])
        self.step_indexes.append(index)
        step = self.steps[index]
        expression = REFERENCE_EXPRESSIONS[step['name']]
        if self.wrong:
            expression = next(choice for choice in step['choices'] if choice != expression)
        return {'ok': True, 'json': {'answer': expression}}


class NoModels:
    def __init__(self):
        self.calls = 0

    def call(self, request):
        self.calls += 1
        raise AssertionError('The assembled parcel program must never call a model')


class ParcelConstruction(unittest.TestCase):
    def test_public_request_and_complete_fake_journeys(self):
        request = json.loads(PUBLIC_REQUEST.read_text())
        inputs = json.loads(PUBLIC_INPUTS.read_text())
        self.assertEqual(len(request['steps']), 13)
        self.assertEqual({step['name'] for step in request['steps']}, set(REFERENCE_EXPRESSIONS))
        choices = {step['name']: step['choices'].index(REFERENCE_EXPRESSIONS[step['name']]) + 1
                   for step in request['steps']}
        for wrong in (False, True):
            with self.subTest(all_model_proposals_wrong=wrong), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary) / 'construction'
                proposals = ParcelProposals(request, wrong)
                result = W.run_card(request, kind='steps', folder=folder, by='fake:parcel',
                                    applicators=proposals, retries=0, finite_fallback=True)
                self.assertEqual(result['status'], 'done', result.get('error') or result['report'].get('error'))
                self.assertEqual(proposals.step_indexes, list(range(13)))
                self.assertEqual(result['report']['asks'], 13)
                self.assertEqual(result['report']['calls'], 13)
                self.assertEqual(result['choices'], choices)
                self.assertEqual(result['model_selected_steps'], 0 if wrong else 13)
                self.assertEqual(result['finite_selected_steps'], 13 if wrong else 0)
                self.assertEqual(result['selection_origins'], {
                    name: 'finite_fallback' if wrong else 'model' for name in REFERENCE_EXPRESSIONS})
                self.assertEqual(result['finite_trials'], sum(choices.values()) if wrong else 0)

                recovered = A.from_folder(folder)
                self.assertTrue(recovered['accepted'])
                self.assertEqual(recovered['choices'], choices)
                self.assertEqual(recovered['selection_origins'], result['selection_origins'])
                artifact = recovered['artifact']
                self.assertEqual((folder / 'assembled.sym').read_text(), artifact['source'])
                no_models = NoModels()
                report = Run(artifact['source'], inputs, no_models, artifact['options'],
                             folder=str(Path(temporary) / 'artifact')).execute()
                self.assertEqual(report['status'], 'done', report.get('error'))
                self.assertEqual(report['asks'], 0)
                self.assertEqual(report['calls'], 0)
                self.assertEqual(no_models.calls, 0)
                self.assertEqual(len(report['outputs']), 1)
                output = report['outputs'][0]['value']
                self.assertEqual(output['count'], 3)
                self.assertEqual([row['total'] for row in output['quotes']], [80, 173, 0])
                self.assertEqual(output['total'], 253)


if __name__ == '__main__':
    unittest.main()
