"""Models construct certificates; general rules check them without solving."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402
from symblic.kernel import embed as embed  # noqa: E402
from symblic.adapters import proof as P  # noqa: E402


A, B = ['atom', 'Socrates is human'], ['atom', 'Socrates is mortal']
PREMISES = {'human': A, 'rule': ['implies', A, B]}
PROOF = {'version': 1, 'proof': ['implies_elim', ['premise', 'rule'], ['premise', 'human']]}


class Apps:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': self.answers[min(len(self.requests)-1, len(self.answers)-1)]}}


class ProofExecution(unittest.TestCase):
    SOURCE = ('use profile=verified.\ngiven premises: Any.\ngiven goal: Any.\n'
              'ask certificate: Any "Construct a proof term of goal from premises." '
              'from premises, goal with effort=low, route=escalate, retries=1\n'
              'let checked = proof_check(premises, goal, certificate).\n'
              'ensure checked.valid else retry.\nshow checked.\n')

    def test_model_constructs_multistep_proof_kernel_does_not_search(self):
        apps = Apps(PROOF)
        with patch.object(S.KB, 'derive', side_effect=AssertionError('no symbolic proof search')):
            result = embed.run(self.SOURCE, inputs={'premises': PREMISES, 'goal': B},
                               applicators=apps, options={'by': 'fake:constructor'})
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(result['calls'], 1)
        self.assertEqual(len(apps.requests), 1)
        checked = next(b['value'] for b in result['bindings'] if b['name'] == 'checked')
        self.assertTrue(checked['valid'])
        self.assertTrue(checked['conditional_on_premises'])
        self.assertEqual(checked['consistency'], 'not_checked')
        self.assertEqual(checked['used_premises'], ['human', 'rule'])

    def test_correct_conclusion_without_derivation_is_rejected_and_repaired(self):
        apps = Apps({'version': 1, 'proof': ['premise', 'invented'], 'conclusion': B}, PROOF)
        result = embed.run(self.SOURCE, inputs={'premises': PREMISES, 'goal': B}, applicators=apps,
                           options={'by': 'fake:constructor'})
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(result['calls'], 2)
        self.assertTrue(result['checks'] if 'checks' in result else result['evidence']['checks'])

    def test_untrusted_certificate_cannot_replace_premises(self):
        forged = {'version': 1, 'proof': ['premise', 'human'], 'premises': {'human': B}}
        apps = Apps(forged)
        result = embed.run(self.SOURCE, inputs={'premises': PREMISES, 'goal': B}, applicators=apps,
                           options={'by': 'fake:constructor'})
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['calls'], 2)
        self.assertNotIn('checked', [b['name'] for b in result['bindings']])

    def test_human_logic_parser_is_available_as_a_builtin(self):
        source = ('let a = proof_parse("\\\"A human statement\\\" implies \\\"Another statement\\\"").\n'
                  'assert a = ["implies", ["atom", "A human statement"], ["atom", "Another statement"]].')
        result = embed.run(source)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(result['calls'], 0)

    def test_human_written_certificate_uses_language_integer_literals(self):
        source = ('let premises = {a: ["atom", "A"]}.\n'
                  'let certificate = {version: 1, proof: ["premise", "a"]}.\n'
                  'assert proof_valid(premises, ["atom", "A"], certificate).')
        result = embed.run(source)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(result['calls'], 0)

    def test_empty_record_literal_and_closed_human_identity_proof(self):
        source = ('use profile=verified.\nlet premises = {:}.\n'
                  'let empty_set = {}.\nassert premises != empty_set.\n'
                  'let a = ["atom", "A"].\n'
                  'let certificate = {version: 1, proof: ["implies_intro", "h", a, ["hypothesis", "h"]]}.\n'
                  'let result = proof_check(premises, ["implies", a, a], certificate).\n'
                  'assert result.valid.\nassert result.used_premises = [].')
        report = embed.run(source)
        self.assertEqual(report['status'], 'done', report.get('error'))
        self.assertEqual(report['calls'], 0)
        self.assertEqual(S.show({}), '{:}')
        self.assertEqual(S.show(frozenset()), '{}')
        self.assertEqual(next(b['value'] for b in report['bindings'] if b['name'] == 'premises'), {})

    def test_checker_charges_host_work_before_processing(self):
        count = []
        def tick():
            count.append(1)
            if len(count) > 10:
                raise S.SymblicError('bounded host work', kind='budget')
        with self.assertRaises(S.SymblicError):
            P.verify(PREMISES, B, PROOF, tick=tick)
        self.assertEqual(len(count), 11)


if __name__ == '__main__':
    unittest.main()
