"""Finite construction with a fake provider reading only each request's selected data."""
import ast
import copy
from fractions import Fraction
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import language as S
from symblic.kernel import run as R
from symblic.adapters import variational as V

SOURCE = (Path(__file__).resolve().parents[2] / 'examples/vorticity-construction.sym').read_text()
COEFFICIENTS = {'a11': (1, 1), 'a12': (1, 2), 'a13': (1, 3),
                'a22': (2, 2), 'a23': (2, 3), 'a33': (3, 3)}
SIGNED_NUMERATOR = 'The numerator may be negative, zero, or positive; ONLY the denominator must be positive.'
RATIONAL_TASKS = {'pivot1', 'lower21', 'pivot2', 'lower32', 'pivot3',
                  'forward1', 'forward2', 'forward3', 'diagonal1', 'diagonal2', 'diagonal3'}
SUBSTITUTION_CONTEXT = {
    'forward1': {'b1'}, 'forward2': {'b2', 'l21', 'y1'}, 'forward3': {'b3', 'l32', 'y2'},
    'diagonal1': {'y1', 'd1'}, 'diagonal2': {'y2', 'd2'}, 'diagonal3': {'y3', 'd3'},
    'x3': {'z3'}, 'x2': {'z2', 'l32', 'x3'}, 'x1': {'z1', 'l21', 'x2'},
}
CONTEXT_ROW = re.compile(r'^- (\w+) : [^=]+ = (.*)$', re.M)


def numeric_literal(text):
    """Read printed numeric/list literals only; never evaluate Python or a provider program."""
    def read(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return Fraction(node.value)
        if isinstance(node, ast.List):
            return [read(child) for child in node.elts]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -read(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return read(node.left) / read(node.right)
        raise AssertionError('Unexpected selected numeric literal: ' + text)
    return read(ast.parse(text, mode='eval').body)


class Worker:
    """Test-only arithmetic from capsule inputs, with explicit rejection injections."""
    def __init__(self, wrong_once=False, stale_solution=None, wrong_task=None):
        self.requests = []
        self.wrong_once = wrong_once
        self.stale_solution = stale_solution
        self.wrong_task = wrong_task

    def call(self, request):
        prompt = request['prompt']
        context, statement = prompt.split('CONTEXT', 1)[1].split('STATEMENT:', 1)
        values = {name: numeric_literal(value) for name, value in CONTEXT_ROW.findall(context)}
        name = re.search(r'\bask\s+(\w+)\s*:', statement).group(1)
        self.requests.append({'name': name, 'values': copy.deepcopy(values), 'prompt': prompt,
                              'effort': request['effort'], 'messages': request.get('messages')})
        if name in COEFFICIENTS:
            a, b = COEFFICIENTS[name]
            answer = sum(x * weight * y for x, weight, y in
                         zip(values[f'column{a}'], values['weights'], values[f'column{b}']))
            if self.wrong_once and len(self.requests) == 1:
                answer += 1
        elif name == 'pivot1':
            answer = values['A'][0][0]
        elif name == 'lower21':
            answer = values['A'][1][0] / values['d1']
        elif name == 'pivot2':
            answer = values['A'][1][1] - values['l21'] ** 2 * values['d1']
        elif name == 'lower32':
            answer = values['A'][2][1] / values['d2']
        elif name == 'pivot3':
            answer = values['A'][2][2] - values['l32'] ** 2 * values['d2']
        elif name == 'forward1':
            answer = values['b1']
        elif name == 'forward2':
            answer = values['b2'] - values['l21'] * values['y1']
        elif name == 'forward3':
            answer = values['b3'] - values['l32'] * values['y2']
        elif name.startswith('diagonal'):
            index = name[-1]
            answer = values['y' + index] / values['d' + index]
        elif name == 'x3':
            answer = values['z3']
        elif name == 'x2':
            answer = values['z2'] - values['l32'] * values['x3']
        elif name == 'x1':
            answer = values['z1'] - values['l21'] * values['x2']
        else:
            raise AssertionError('Unexpected task ' + name)
        if self.wrong_task == name and sum(r['name'] == name for r in self.requests) == 1:
            answer += 1
        if name in {'x1', 'x2', 'x3'} and self.stale_solution is not None:
            answer = Fraction(self.stale_solution[int(name[-1]) - 1])
        if name in COEFFICIENTS or name in {'x1', 'x2', 'x3'}:
            self.assert_integer(answer)
            answer = int(answer)
        else:
            answer = {'numerator': answer.numerator, 'denominator': answer.denominator}
        return {'ok': True, 'json': {'answer': answer}, 'model': 'fake-selected-arithmetic', 'node': 'isolated'}

    @staticmethod
    def assert_integer(value):
        if value.denominator != 1:
            raise AssertionError('Coefficient fixture expected an integer')


class VorticityConstruction(unittest.TestCase):
    def run_source(self, worker, source=SOURCE, max_calls=30):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(V, '_solve', side_effect=AssertionError('solver forbidden')), \
                patch.object(V, '_ldlt', side_effect=AssertionError('factorization forbidden')), \
                patch.object(V, 'minimize_quadratic', side_effect=AssertionError('minimizer forbidden')):
            report = R.Run(source, {}, worker, {'by': 'fake:fixture', 'max_calls': max_calls,
                                               'determine': False, 'solve': False, 'constructor': 'off'},
                           folder=folder).execute()
        return report

    def test_model_parts_pass_checked_energy_and_boundary_contract(self):
        self.assertTrue(S.check(SOURCE)['ok'])
        worker = Worker()
        source = SOURCE.replace('let incidence', 'let secret = "UNSELECTED_SENTINEL_VALUE".\nlet incidence', 1)
        report = self.run_source(worker, source)
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual((20, 20), (report['calls'], len(worker.requests)))
        self.assertEqual([0, 1, 2, 1, 0], report['outputs'][0]['value'])
        witness = report['outputs'][1]['value']
        self.assertEqual([0, 0, 0], witness['residual'])
        self.assertEqual(-2, witness['min_energy'])
        for request in worker.requests:
            self.assertEqual('medium', request['effort'])
            self.assertIsNone(request['messages'])
            self.assertNotIn('UNSELECTED_SENTINEL_VALUE', request['prompt'])
            if request['name'] in RATIONAL_TASKS:
                self.assertIn(SIGNED_NUMERATOR, request['prompt'])
            if request['name'] in SUBSTITUTION_CONTEXT:
                self.assertEqual(SUBSTITUTION_CONTEXT[request['name']], set(request['values']))
        for request in worker.requests[:6]:
            a, b = COEFFICIENTS[request['name']]
            self.assertEqual({f'column{a}', f'column{b}', 'weights'}, set(request['values']))
        # A correct scalar round cannot hide an assembly error from the original incidence check.
        broken = SOURCE.replace('[[a11,a12,a13],[a12,a22,a23],[a13,a23,a33]]',
                                '[[a11,a12,a13],[a12,a22,a23],[a13,a12,a33]]')
        broken_worker = Worker()
        broken_report = self.run_source(broken_worker, broken.replace('weights = [1,1,1,1]', 'weights = [1,1,2,1]'))
        self.assertEqual('failed', broken_report['status'])
        self.assertEqual(6, len(broken_worker.requests), 'assembly must fail before any pivot ask')
        self.assertEqual([], broken_report['outputs'])

    def test_wrong_coefficient_is_retried_before_other_parts(self):
        worker = Worker(wrong_once=True)
        report = self.run_source(worker)
        self.assertEqual('done', report['status'], report.get('error'))
        self.assertEqual(21, report['calls'])
        self.assertEqual(['a11', 'a11', 'a12'], [r['name'] for r in worker.requests[:3]])
        self.assertEqual(worker.requests[0]['values'], worker.requests[1]['values'])
        self.assertEqual([0, 1, 2, 1, 0], report['outputs'][0]['value'])

    @staticmethod
    def factor_diagnostic():
        ask = next(line for line in SOURCE.splitlines() if line.startswith('ask lower32:'))
        return '\n'.join([
            'program Signed rational factor prompt diagnostic.',
            'use profile=verified, determine=false, solve=false.',
            'note Targeted prompt diagnostic with declared synthetic inputs; not a completed physics construction.',
            'let A = [[2,-1,0],[-1,2,-1],[0,-1,2]].',
            'let d2 = 3/2.',
            'define RationalPart as Record {numerator: Int, denominator: Int in 1..100}.',
            '', ask,
            'let l32 = lower32.numerator / lower32.denominator.',
            'ensure l32 * d2 = A[3][2] else retry.',
            'show lower32.', 'show l32.', '',
        ])

    def test_factor_diagnostic_accepts_negative_zero_and_positive_numerators(self):
        for edge in [-1, 0, 1]:
            with self.subTest(edge=edge):
                source = self.factor_diagnostic().replace(
                    '[[2,-1,0],[-1,2,-1],[0,-1,2]]',
                    f'[[2,-1,0],[-1,2,{edge}],[0,{edge},2]]')
                worker = Worker()
                report = self.run_source(worker, source, max_calls=2)
                self.assertEqual('done', report['status'], report.get('error'))
                self.assertEqual(1, report['calls'])
                self.assertEqual(['lower32'], [r['name'] for r in worker.requests])
                request = worker.requests[0]
                self.assertEqual({'A', 'd2'}, set(request['values']))
                self.assertIn(SIGNED_NUMERATOR, request['prompt'])
                self.assertIsNone(request['messages'])
                expected = Fraction(edge) / Fraction(3, 2)
                self.assertEqual({'numerator': expected.numerator, 'denominator': expected.denominator},
                                 report['outputs'][0]['value'])

    def test_factor_diagnostic_rejects_unrequested_absolute_value(self):
        class UnsignedWorker(Worker):
            def call(self, request):
                result = super().call(request)
                answer = result['json']['answer']
                answer['numerator'] = abs(answer['numerator'])
                return result

        worker = UnsignedWorker()
        report = self.run_source(worker, self.factor_diagnostic(), max_calls=2)
        self.assertEqual('failed', report['status'])
        self.assertEqual(2, report['calls'])
        self.assertEqual(['lower32', 'lower32'], [r['name'] for r in worker.requests])
        self.assertEqual('check', report['error']['kind'])
        self.assertEqual([], report['outputs'])
        self.assertEqual(worker.requests[0]['values'], worker.requests[1]['values'])

    @staticmethod
    def substitution_diagnostic():
        prefix = 'program Atomic substitution prompt diagnostic.\nuse profile=verified, determine=false, solve=false.\nnote Targeted nine-ask substitution diagnostic with declared synthetic A, b, L, and D; not a completed physics construction.\nlet A = [[2,-1,0],[-1,2,-1],[0,-1,2]].\nlet b = [0,2,0].\nlet L = [[1,0,0],[-1/2,1,0],[0,-2/3,1]].\nlet D = [2,3/2,4/3].\nlet indices = [1,2,3].\nlet l21 = L[2][1].\nlet l32 = L[3][2].\nlet d1 = D[1].\nlet d2 = D[2].\nlet d3 = D[3].\ndefine RationalPart as Record {numerator: Int, denominator: Int in 1..100}.\n\n'
        block = SOURCE[SOURCE.index('let b1 ='):SOURCE.index('let residual =')]
        return prefix + block + (
            'let residual = [sum([A[i][j] * solution[j] for j in indices]) - b[i] for i in indices].\n'
            'ensure residual = [0,0,0] else retry.\nshow solution.\nshow residual.\n')

    def test_nine_ask_diagnostic_uses_only_required_scalars_and_handles_changed_integer_load(self):
        for rhs, expected in [(2, [1, 2, 1]), (4, [2, 4, 2])]:
            with self.subTest(rhs=rhs):
                worker = Worker()
                source = self.substitution_diagnostic().replace('b = [0,2,0]', f'b = [0,{rhs},0]')
                report = self.run_source(worker, source, max_calls=18)
                self.assertEqual('done', report['status'], report.get('error'))
                self.assertEqual(9, report['calls'])
                self.assertEqual(list(SUBSTITUTION_CONTEXT), [r['name'] for r in worker.requests])
                for request in worker.requests:
                    self.assertEqual(SUBSTITUTION_CONTEXT[request['name']], set(request['values']))
                    self.assertEqual('medium', request['effort'])
                    self.assertIsNone(request['messages'])
                self.assertEqual(expected, report['outputs'][0]['value'])
                self.assertEqual([0, 0, 0], report['outputs'][1]['value'])

    def test_wrong_forward_diagonal_and_backward_scalars_retry_before_dependents(self):
        for name in ['forward2', 'diagonal2', 'x2']:
            with self.subTest(name=name):
                worker = Worker(wrong_task=name)
                report = self.run_source(worker)
                self.assertEqual('done', report['status'], report.get('error'))
                self.assertEqual(21, report['calls'])
                positions = [i for i, r in enumerate(worker.requests) if r['name'] == name]
                self.assertEqual([positions[0], positions[0] + 1], positions)
                self.assertEqual(worker.requests[positions[0]]['values'], worker.requests[positions[1]]['values'])
                self.assertEqual([0, 1, 2, 1, 0], report['outputs'][0]['value'])

    def test_global_residual_rejects_incorrect_assembly_after_all_scalar_checks(self):
        worker = Worker()
        source = SOURCE.replace('let solution = [x1,x2,x3].', 'let solution = [x1,x1,x3].')
        report = self.run_source(worker, source)
        self.assertEqual('failed', report['status'])
        self.assertEqual(21, report['calls'])
        self.assertEqual(['x1', 'x1'], [r['name'] for r in worker.requests[-2:]])
        self.assertEqual('check', report['error']['kind'])
        self.assertEqual([], report['outputs'])

    def test_changed_load_cannot_reuse_the_old_solution(self):
        original = self.run_source(Worker())
        self.assertEqual('done', original['status'], original.get('error'))
        worker = Worker(stale_solution=original['outputs'][0]['value'][1:-1])
        report = self.run_source(worker, SOURCE.replace('loads = [0,-2,0]', 'loads = [0,-4,0]'))
        self.assertEqual('failed', report['status'])
        self.assertEqual(19, report['calls'])
        self.assertEqual(['x3', 'x3'], [r['name'] for r in worker.requests[-2:]])
        self.assertEqual(Fraction(2), worker.requests[-1]['values']['z3'])
        self.assertEqual('check', report['error']['kind'])
        self.assertEqual([], report['outputs'])


if __name__ == '__main__':
    unittest.main()
