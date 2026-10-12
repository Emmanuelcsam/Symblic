"""Adversarial kernel regressions: typed identity, lossless logic and bounded exact operations.

No models, network, persisted stores, workers or live dashboard imports.
"""

import os
import subprocess
import sys
import unittest
from decimal import Inexact, ROUND_DOWN, ROUND_UP, localcontext
from fractions import Fraction

from symblic.kernel import language as S
from symblic.kernel import run as SR


def evaluate(source, **bindings):
    env = S.Env()
    for name, value in bindings.items():
        env.vars[name] = S.Binding(name, value)
    parser = S.Parser(S.tokenize(source), 1)
    node = parser.expr()
    parser.finish()
    return S.Kernel(env).eval(node)


class ValueIdentity(unittest.TestCase):
    def test_distinct_observable_text_has_distinct_identity(self):
        for a, b in [('a', ' a'), ('a', 'a '), ('a\nb', 'a\r\nb'), ('é', 'e\u0301')]:
            self.assertFalse(S.values_equal(a, b))
            self.assertNotEqual(S.fingerprint(a), S.fingerprint(b))
        self.assertFalse(evaluate('"a" = "a "'))
        self.assertEqual(evaluate('len({"a", "a "})'), 2)

    def test_bool_number_and_nested_values_stay_distinct_in_sets(self):
        self.assertEqual(evaluate('len({true, 1, false, 0})'), 4)
        self.assertEqual(evaluate('len({[true], [1], {a: true}, {a: 1}})'), 4)
        self.assertTrue(evaluate('true in {true, 1} and 1 in {true, 1}'))
        self.assertFalse(evaluate('true in {1}'))
        self.assertFalse(evaluate('{true} subset {1}'))
        self.assertEqual(evaluate('len({true, 1} minus {true})'), 1)
        self.assertTrue(evaluate('({true, 1} minus {true}) = {1}'))
        self.assertEqual(evaluate('len({true} union {1})'), 2)
        self.assertEqual(evaluate('len({true} intersect {1})'), 0)

    def test_nested_collections_are_legal_set_members(self):
        self.assertEqual(evaluate('len({[{x: 1}], [{x: 1}], [{x: 2}]})'), 2)
        self.assertTrue(evaluate('set([true, 1]) = {true, 1}'))

    def test_typed_set_cardinality_is_enforced(self):
        ty = {'k': 'set', 'of': {'k': 'int'}, 'min': 2, 'max': 2}
        with self.assertRaisesRegex(S.SymblicError, 'items'):
            S.check_value(evaluate('{1}'), ty)

    def test_identity_version_changes(self):
        self.assertEqual(S.CANON_VERSION, 3)
        self.assertEqual(S.kernel_id()['canon'], 3)


class LogicIdentity(unittest.TestCase):
    def run_program(self, source):
        report = SR.Run(source, None, None, {'by': 'kernel'}).execute()
        self.assertEqual(report['status'], 'done', report.get('error'))
        return report

    def query(self, rows, args):
        kb = S.KB()
        for row in rows:
            kb.add_fact('p', row)
        return kb.query('p', args, S.Node('query', 1, 1), S.Kernel(kb=kb))

    def test_facts_do_not_equate_booleans_and_numbers(self):
        self.run_program('fact p(true), p(1), p(false), p(0).\n'
                         'assert len(query p(X)) = 4.\n'
                         'fact only_bool(true).\nassert not holds only_bool(1).\n')

    def test_null_is_a_bound_value_not_a_missing_variable(self):
        self.assertEqual(self.query([(None, 1)], [S.LVar('X'), S.LVar('X')]), ())
        self.assertEqual(self.query([(None, None)], [S.LVar('X'), S.LVar('X')]), (None,))

    def test_json_looking_text_is_not_a_record_or_list(self):
        self.assertFalse(self.query([({'a': 1},)], ['{"a":1}']))
        self.assertEqual(self.query([('[1,2]',)], [S.LVar('X')]), ('[1,2]',))
        self.assertEqual(self.query([('{"a":1}',)], [S.LVar('X')]), ('{"a":1}',))

    def test_record_fields_fractions_and_sets_survive_logic_round_trip(self):
        value = {'#q': '1/2', 'rational': Fraction(1, 2), 'set': S.ValueSet([True, 1])}
        result = self.query([(value,)], [S.LVar('X')])
        self.assertTrue(S.values_equal(result, (value,)))
        self.run_program('fact p({a: 1/2}).\nrule q(X) if p(X).\n'
                         'rule twice(N) if p(X) and N = X.a * 2.\n'
                         'assert query q(X) = [{a: 1/2}].\nassert query twice(N) = [1].\n')

    def test_rule_positive_expressions_need_preceding_binding(self):
        for rule in ['rule q(X) if p(X + 1).', 'rule q(X) if p(X, X + 1).',
                     'rule q(X) if p(Y) and X = X + 1.']:
            checked = S.check(rule)
            self.assertFalse(checked['ok'], rule)
            self.assertIn('unsafe rule', checked['errors'][0]['message'])
        self.run_program('fact p(1), p(2).\nrule q(X) if p(X) and p(X + 1).\n'
                         'assert query q(X) = [1].\n')

    def test_scanning_nonmatching_facts_consumes_budget(self):
        kb = S.KB()
        for i in range(100):
            kb.add_fact('p', (i,))
        with self.assertRaisesRegex(S.SymblicError, 'budget'):
            kb.query('p', [999], S.Node('query', 1, 1), S.Kernel(kb=kb, budget=S.Budget(5)))


class ArithmeticBoundaries(unittest.TestCase):
    def test_numeric_coercion_preserves_unit_ambiguity_as_a_rejection(self):
        for answer in ['26.2 miles', '26.2 km', '50%', '$5', '€5', '-17.77 F', '5 or 6', '1,234', '12,34']:
            with self.subTest(answer=answer), self.assertRaisesRegex(S.SymblicError, 'number only'):
                S.coerce(answer, {'k': 'number'})
        for answer, expected in [(' 26.2 ', Fraction(131, 5)), ('+5', 5), ('.5', Fraction(1, 2)),
                                 ('1e3', 1000), ('1/2', Fraction(1, 2)), ('1.25/2.5', Fraction(1, 2))]:
            self.assertEqual(S.coerce(answer, {'k': 'number'}), expected)

    def test_unit_disagreement_cannot_become_numeric_consensus(self):
        class Units:
            def call(self, request):
                value = '26.2 miles' if request['app']['model'] == 'a' else '26.2 km'
                return {'ok': True, 'json': {'answer': value}, 'ms': 0}
        report = SR.Run('ask d: Number "Distance?" by ["fake:a", "fake:b"] with retries=0, effort=low.',
                        None, Units(), {}).execute()
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['bindings'])

    def test_zero_to_negative_fractional_power_is_undefined(self):
        with self.assertRaisesRegex(S.SymblicError, 'division by zero'):
            evaluate('0 ^ (-1/2)')
        self.assertEqual(evaluate('0 ^ (1/2)'), 0)

    def test_repetition_requires_whole_numbers(self):
        for expression in ['"ab" * 1.5', '[1,2] * 1.5']:
            with self.assertRaisesRegex(S.SymblicError, 'whole number'):
                evaluate(expression)

    def test_division_and_floor_division_enforce_the_digit_limit(self):
        for expression in ['10^3000 / (10^3000-1) / (10^3000-1)',
                           '(10^3000) // (1 / 10^3000)']:
            with self.assertRaisesRegex(S.SymblicError, 'digits'):
                evaluate(expression)

    def test_literal_boundary_is_exact(self):
        self.assertEqual(S.parse_number_literal('1e3999'), 10 ** 3999)
        for literal in ['1e4000', '1e-4000', '1e10000000']:
            with self.assertRaisesRegex(S.SymblicError, 'digits'):
                S.parse_number_literal(literal)

    def test_round_is_exact_for_long_numbers_and_halfway_cases(self):
        self.assertEqual(evaluate('round(10^300, 0)'), 10 ** 300)
        self.assertEqual(evaluate('round(1.005, 2)'), Fraction(101, 100))
        self.assertEqual(evaluate('round(-1.005, 2)'), Fraction(-101, 100))
        self.assertEqual(evaluate('round(1250, -2)'), 1300)
        with self.assertRaisesRegex(S.SymblicError, 'places'):
            evaluate('round(1, 1000000000)')

    def test_long_terminating_decimal_is_displayed_exactly(self):
        value = Fraction(1, 2 ** 300)
        self.assertEqual(Fraction(S.num_text(value)), value)

    def test_builtin_aggregates_stop_at_oversized_intermediates(self):
        with self.assertRaisesRegex(S.SymblicError, 'digits'):
            evaluate('product([10^3000, 10^3000, 0])')

    def test_concatenation_cannot_bypass_sequence_limit(self):
        with self.assertRaisesRegex(S.SymblicError, 'too long'):
            evaluate('("a" * 60000) + ("a" * 60000)')


class AmbientIndependence(unittest.TestCase):
    def test_decimal_precision_rounding_and_traps_do_not_change_results(self):
        expressions = ['radians(1)', '2 ^ 0.3', 'sin(1)', 'sqrt(2)', 'text(1/7)',
                       'flower(petals=3, size=120)']
        baseline = [S.canon_json(evaluate(expr)) for expr in expressions]
        for precision, rounding in [(8, ROUND_DOWN), (60, ROUND_UP)]:
            with localcontext() as ctx:
                ctx.prec = precision
                ctx.rounding = rounding
                ctx.traps[Inexact] = True
                self.assertEqual([S.canon_json(evaluate(expr)) for expr in expressions], baseline)

    def test_hash_seed_does_not_change_logic_or_set_results(self):
        program = ('fact p(true), p(1), p("x"), p("y").\n'
                   'rule q(X) if p(X).\nshow query q(X).\nshow {true, 1, "x", "y"}.\n')
        code = ('from symblic.kernel import run as R\n'
                f'r=R.Run({program!r},None,None,{{"by":"kernel"}}).execute()\n'
                'assert r["status"] == "done", r.get("error")\nprint(r["fingerprint"])\n')
        outputs = set()
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))          # the repository root
        for seed in ['0', '1', '7']:
            result = subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True, text=True,
                                    timeout=20, env={**os.environ, 'PYTHONHASHSEED': seed})
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.add(result.stdout)
        self.assertEqual(len(outputs), 1)


class StaticExtensionChecks(unittest.TestCase):
    def setUp(self):
        self.previous = dict(S.EXTENSIONS)

        def parse(parser, line, col, _program):
            value = parser.expr()
            parser.finish()
            return S.Node('auditfx', line, col, value=value)

        self.extension = S.Extension('auditfx', parse, lambda *_args: self.fail('static check executed an effect'),
                                     reads=lambda node: node.value, klass='effect')
        S.register_extension(self.extension)

    def tearDown(self):
        S.EXTENSIONS.clear()
        S.EXTENSIONS.update(self.previous)

    def test_effect_extension_inside_retry_region_is_rejected(self):
        for body in ['auditfx x.', 'if true then\n auditfx x.\nend.',
                     'for i in [1] do\n auditfx x.\nend.']:
            source = 'ask x: Int "Pick."\n' + body + '\nensure x = 2 else retry.\n'
            checked = S.check(source)
            self.assertFalse(checked['ok'], source)
            errors = [error for error in checked['errors'] if 'repeat an effect' in error['message']]
            self.assertTrue(errors, checked)
            self.assertEqual(errors[0]['code'], 'SYM_CHECK')

    def test_effect_detection_follows_local_calls_transitively(self):
        source = ('routine do_it(x) -> Int do\n auditfx x.\n return x.\nend.\n'
                  'function wrap(x) = do_it(x).\nask x: Int "Pick."\n'
                  'let y = wrap(x).\nensure x = 2 and y = 2 else retry.\n')
        checked = S.check(source)
        self.assertFalse(checked['ok'])
        self.assertTrue(any('call to wrap' in error['message'] for error in checked['errors']))

    def test_declaration_without_effectful_call_is_allowed(self):
        checked = S.check('ask x: Int "Pick."\nroutine later() do\n auditfx 1.\n return 1.\nend.\n'
                          'ensure x = 2 else retry.\n')
        self.assertTrue(checked['ok'], checked['errors'])

    def test_retry_effect_detection_follows_facts_and_rules(self):
        checked = S.check('ask x: Int "Pick."\nfact p(x).\nrule q(X) if p(X).\n'
                          'auditfx x.\nensure holds q(2) else retry.\n')
        self.assertFalse(checked['ok'])
        self.assertTrue(any('repeat an effect' in error['message'] for error in checked['errors']))

    def test_hooks_receive_static_scope_and_run_once_per_program(self):
        scopes, programs = [], []

        def check(node, scope):
            scopes.append(scope)
            return {'message': 'effect is intentionally visible', 'severity': 'warning'}

        def program_check(program):
            programs.append(program['name'])
            return S.SymblicError('program policy rejects this operation', kind='check')

        self.extension.check = check
        self.extension.check_program = program_check
        checked = S.check('program Hooks.\nlet x = 1.\nauditfx x.\nauditfx x.\n')
        self.assertEqual(scopes, [frozenset({'x'}), frozenset({'x'})])
        self.assertEqual(programs, ['Hooks'])
        self.assertFalse(checked['ok'])
        self.assertEqual(len([row for row in checked['warnings'] if row['message'] ==
                              'effect is intentionally visible']), 2)
        self.assertEqual(checked['errors'][0]['code'], 'SYM_CHECK')

    def test_hook_faults_fail_closed_without_escaping_check(self):
        self.extension.check = lambda _node, _scope: 123
        checked = S.check('auditfx 1.')
        self.assertFalse(checked['ok'])
        self.assertIn('check hook failed', checked['errors'][0]['message'])

    def test_effect_extensions_default_to_runner_gates(self):
        self.assertFalse(self.extension.self_gating)


if __name__ == '__main__':
    unittest.main()
