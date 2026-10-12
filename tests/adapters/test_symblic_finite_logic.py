"""Independent finite interpretations, proof journeys, and hostile input tests."""
import copy
import itertools
import json
import unittest
from unittest.mock import patch

from symblic.adapters import finite_logic as L


def pred(name, *terms):
    return ['pred', name, list(terms)]


def var(name='x', sort='D'):
    return ['var', name, sort]


def const(value, sort='D'):
    return ['const', sort, value]


def certificate(term):
    return {'version': 1, 'proof': term}


def finite_value(f, domains, predicates, propositions, env=None):
    """Independent direct quantified Boolean semantics, no expansion helper."""
    env = {} if env is None else env
    op = f[0]
    if op == 'false':
        return False
    if op == 'atom':
        return propositions[f[1]]
    if op == 'pred':
        args = tuple((t[2], env[t[1]]) if t[0] == 'var' else (t[1], t[2]) for t in f[2])
        return predicates[(f[1], args)]
    if op in ('forall', 'exists'):
        values = [finite_value(f[3], domains, predicates, propositions, dict(env, **{f[1]: v}))
                  for v in domains[f[2]]]
        return all(values) if op == 'forall' else any(values)
    left = finite_value(f[1], domains, predicates, propositions, env)
    right = finite_value(f[2], domains, predicates, propositions, env)
    return {'and': left and right, 'or': left or right, 'implies': not left or right}[op]


def ground_value(f, predicates, propositions):
    if f[0] == 'false':
        return False
    if f[0] == 'atom':
        decoded = json.loads(f[1])
        if decoded[0] == 'proposition':
            return propositions[decoded[1]]
        return predicates[(decoded[1], tuple(map(tuple, decoded[2])))]
    a, b = (ground_value(v, predicates, propositions) for v in f[1:])
    return {'and': a and b, 'or': a or b, 'implies': not a or b}[f[0]]


class FiniteTests(unittest.TestCase):
    def test_independent_exhaustive_finite_interpretations(self):
        for values in ([], ['a'], ['a', 'b']):
            domains = {'D': values}
            px, qx = pred('P', var()), pred('Q', var())
            bodies = [px, qx, ['atom', 'P(x)'], ['false']]
            bodies += [[op, px, qx] for op in ('and', 'or', 'implies')]
            formulas = [[q, 'x', 'D', b] for q in ('forall', 'exists') for b in bodies]
            formulas += [[outer, 'x', 'D', [inner, 'y', 'D', pred('R', var(), var('y'))]]
                         for outer in ('forall', 'exists') for inner in ('forall', 'exists')]
            keys = [(p, (('D', v),)) for p in ('P', 'Q') for v in values]
            keys += [('R', (('D', a), ('D', b))) for a in values for b in values]
            for formula in formulas:
                expanded = L.expand(domains, {}, formula)['goal']
                for bits in itertools.product((False, True), repeat=len(keys) + 1):
                    predicates = dict(zip(keys, bits))
                    propositions = {'P(x)': bits[-1]}
                    self.assertEqual(finite_value(formula, domains, predicates, propositions),
                                     ground_value(expanded, predicates, propositions))

    def test_proof_journeys_forall_instantiation_exists_witness(self):
        d = {'D': ['a', 'b']}
        all_p = ['forall', 'x', 'D', pred('P', var())]
        exists_p = ['exists', 'x', 'D', pred('P', var())]
        pa, pb = pred('P', const('a')), pred('P', const('b'))
        receipt = L.verify(d, {'all': all_p}, pa, certificate(['and_left', ['premise', 'all']]))
        self.assertTrue(receipt['ok'], receipt)
        self.assertTrue(L.verify(d, {'a': pa, 'b': pb}, all_p,
                                certificate(['and_intro', ['premise', 'a'], ['premise', 'b']]))['ok'])
        expanded_b = L.expand(d, {}, pb)['goal']
        term = ['or_left', ['premise', 'a'], expanded_b]
        self.assertTrue(L.verify(d, {'a': pa}, exists_p, certificate(term))['ok'])
        self.assertFalse(L.verify(d, {'a': pa}, exists_p,
                                 certificate(['or_right', ['premise', 'a'], expanded_b]))['ok'])
        self.assertTrue(receipt['conditional_on_domains'])
        self.assertEqual(receipt['proof_receipt']['logic'], 'intuitionistic-propositional-logic')
        self.assertEqual(receipt['consistency'], 'not_checked')

    def test_empty_and_singleton_domains(self):
        goal = ['forall', 'x', 'D', pred('P', var())]
        r = L.verify({'D': []}, {}, goal,
                     certificate(['implies_intro', 'f', ['false'], ['hypothesis', 'f']]))
        self.assertTrue(r['ok'], r)
        self.assertEqual(L.expand({'D': []}, {}, ['exists', 'x', 'D', pred('P', var())])['goal'],
                         ['false'])
        single = L.expand({'D': ['a']}, {}, goal)['goal']
        self.assertEqual(single, L.expand({'D': ['a']}, {}, pred('P', const('a')))['goal'])
        r = L.verify({'D': []}, {'falsehood': ['false']}, ['exists', 'x', 'D', pred('P', var())],
                     certificate(['premise', 'falsehood']))
        self.assertTrue(r['ok'])  # explosion/false is conditional, never consistency evidence

    def test_capture_safety_and_shadowing(self):
        d = {'D': ['x', 'y'], 'E': ['z']}
        source = ['forall', 'x', 'D', ['exists', 'y', 'E', pred('R', var(), var('y', 'E'))]]
        expanded = L.expand(d, {}, source)['goal']
        self.assertEqual(json.loads(expanded[1][1]), ['predicate', 'R', [['D', 'x'], ['E', 'z']]])
        self.assertEqual(json.loads(expanded[2][1]), ['predicate', 'R', [['D', 'y'], ['E', 'z']]])
        bads = [(['forall', 'x', 'D', ['exists', 'x', 'E', pred('P', var('x', 'E'))]], 'shadowing'),
                (pred('P', var()), 'free_variable'),
                (['forall', 'x', 'D', pred('P', var('x', 'E'))], 'variable_domain'),
                (pred('P', const('z')), 'out_of_domain'),
                (['forall', 'x', 'Missing', ['false']], 'undeclared_domain')]
        for f, error in bads:
            with self.assertRaisesRegex(L.FiniteLogicError, '^' + error + '$'):
                L.expand(d, {}, f)
        # Reusing the same binder in separate lexical scopes is allowed.
        f = ['forall', 'x', 'D', pred('P', var())]
        L.expand(d, {}, ['and', f, f])
        # Empty quantifiers do not hide invalid source.
        with self.assertRaisesRegex(L.FiniteLogicError, 'free_variable'):
            L.expand({'D': []}, {}, ['forall', 'x', 'D', pred('P', var('y'))])

    def test_signatures_and_namespaces(self):
        d = {'D': ['a'], 'E': ['a']}
        pa = pred('P', const('a'))
        with self.assertRaisesRegex(L.FiniteLogicError, 'predicate_signature'):
            L.expand(d, {'p': pa}, pred('P', const('a', 'E')))
        with self.assertRaisesRegex(L.FiniteLogicError, 'predicate_signature'):
            L.expand(d, {'p': pa}, pred('P'))
        expanded = L.expand(d, {}, pa)['goal']
        for text in ('P(a)', expanded[1], '∀x P(x)'):
            self.assertNotEqual(L.expand(d, {}, ['atom', text])['goal'], expanded)
        self.assertFalse(L.verify(d, {'p': ['atom', 'P(a)']}, pa, certificate(['premise', 'p']))['ok'])
        self.assertNotEqual(L.expand(d, {}, pa)['goal'],
                            L.expand(d, {}, pred('P', const('a', 'E')))['goal'])

    def test_domain_tampering_source_and_expanded_hashes(self):
        goal = ['forall', 'x', 'D', pred('P', var())]
        premises = {'a': pred('P', const('a'))}
        cert = certificate(['premise', 'a'])
        r = L.verify({'D': ['a']}, premises, goal, cert)
        self.assertTrue(r['ok'])
        changed = L.verify({'D': ['a', 'b']}, premises, goal, cert)
        self.assertFalse(changed['ok'])
        for key in ('domains', 'source', 'expanded_goal'):
            self.assertNotEqual(r['hashes'][key], changed['hashes'][key])
        for key, value in [('domains', {'D': ['a']}), ('goal', premises['a']), ('premises', premises)]:
            self.assertFalse(L.verify({'D': ['a', 'b']}, premises, goal, dict(cert, **{key: value}))['ok'])
        # Domain data irrelevant to this formula still binds the receipt identity.
        extra = L.verify({'D': ['a'], 'E': ['unused']}, premises, goal, cert)
        self.assertTrue(extra['ok'])
        self.assertNotEqual(r['hashes']['judgment'], extra['hashes']['judgment'])
        e1 = L.expand({'D': ['a', 'b']}, {}, goal)
        e2 = L.expand({'D': ['b', 'a']}, {}, goal)
        self.assertNotEqual(e1['hashes']['expanded_goal'], e2['hashes']['expanded_goal'])
        self.assertEqual(r, L.verify({'D': ['a']}, copy.deepcopy(premises), copy.deepcopy(goal), cert))

    def test_preflight_cartesian_and_aggregate_bounds(self):
        nested = pred('P', var('x'), var('y'), var('z'))
        for name in ('z', 'y', 'x'):
            nested = ['forall', name, 'D', nested]
        with patch.object(L, '_join', side_effect=AssertionError('must refuse before expansion')):
            with self.assertRaisesRegex(L.FiniteLogicError, 'expansion_'):
                L.expand({'D': list(map(str, range(100)))}, {}, nested)
        modest = ['forall', 'x', 'D', pred('P', var())]
        with patch.object(L, 'MAX_OUTPUT_NODES', 20):
            with self.assertRaisesRegex(L.FiniteLogicError, 'expansion_nodes'):
                L.expand({'D': ['a', 'b']}, {'one': modest, 'two': modest}, modest)
        with patch.object(L, 'MAX_OUTPUT_BYTES', 1):
            with self.assertRaisesRegex(L.FiniteLogicError, 'expansion_bytes'):
                L.expand({}, {}, ['atom', 'A'])
        with patch.object(L, 'MAX_WORK', 1):
            with self.assertRaisesRegex(L.FiniteLogicError, 'expansion_work'):
                L.expand({}, {}, ['and', ['false'], ['false']])
        with self.assertRaisesRegex(L.FiniteLogicError, 'domain_limit'):
            L.expand({'D': list(map(str, range(L.MAX_DOMAIN + 1)))}, {}, ['false'])

    def test_estimates_cover_actual_output_and_detachment(self):
        domains = {'D': ['a', '雪', '\t"\\']}
        source = ['forall', 'x', 'D', ['exists', 'y', 'D',
                  ['and', pred('R', var(), var('y')), ['atom', 'quoted\n雪']]]]
        result = L.expand(domains, {'p': source}, source)
        formulas = [*result['premises'].values(), result['goal']]
        nodes = 0
        stack = list(formulas)
        while stack:
            item = stack.pop()
            nodes += 1
            if type(item) is list:
                stack.extend(item)
        size = sum(len(json.dumps(f, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
                   for f in formulas)
        self.assertLessEqual(nodes, result['expansion_bounds']['nodes'])
        self.assertLessEqual(size, result['expansion_bounds']['bytes'])
        before = copy.deepcopy(source)
        result['goal'].clear()
        self.assertEqual(source, before)
        self.assertEqual(domains['D'][0], 'a')
        # Member strings are opaque: comma/quote/bracket spellings never merge tuples.
        d = {'D': ['a,b', 'a', 'b', '"], ["']}
        self.assertNotEqual(L.expand(d, {}, pred('P', const('a,b')))['goal'],
                            L.expand(d, {}, pred('P', const('a'), const('b')))['goal'])

    def test_unused_domain_and_source_limits(self):
        with self.assertRaisesRegex(L.FiniteLogicError, 'domain_limit'):
            L.expand({('D' + str(i)): list(map(str, range(128))) for i in range(9)},
                     {}, ['false'])
        with self.assertRaisesRegex(L.FiniteLogicError, 'text_limit'):
            L.expand({'D': ['a' * (L.MAX_TEXT + 1)]}, {}, ['false'])
        with self.assertRaisesRegex(L.FiniteLogicError, 'identifier'):
            L.expand({'D' * (L.MAX_IDENTIFIER + 1): []}, {}, ['false'])
        with patch.object(L, 'MAX_INPUT_BYTES', 20):
            self.assertEqual(L.verify({'Unused': ['value']}, {}, ['false'], {})['error'], 'input_bytes')
        with patch.object(L, 'MAX_INPUT_NODES', 3):
            self.assertEqual(L.verify({}, {}, ['false'], {})['error'], 'input_nodes')

    def test_bad_schemas_unicode_cycles_and_unused_inputs(self):
        bad_domains = [[], {'D': ['a', 'a']}, {'D': [1]}, {'D': ['e\u0301']},
                       {'D': ['\u202ea']}, {'D': ['\ud800']}, {'Ｄ': ['a']}, {'D': ('a',)}]
        for d in bad_domains:
            self.assertFalse(L.verify(d, {}, ['false'], certificate(['premise', 'x']))['ok'])
        malformed = [[], ['atom', 1], ['pred', 'P', [['var', 'x']]],
                     ['pred', 'P', [['const', 'D', 'outside']]], ['forall', 'x', 'D'],
                     ['and', ['false']], ['true'], ['exists', {}, 'D', ['false']],
                     ['pred', 'P', [['var', 'x', []]]]]
        for f in malformed:
            with self.subTest(f=f):
                r = L.verify({'D': []}, {'unused': f}, ['false'], certificate(['premise', 'x']))
                self.assertFalse(r['ok'])
                self.assertIsNone(r['proof_receipt'])
        cycle = []
        cycle.append(cycle)
        self.assertEqual(L.verify({}, {'unused': cycle}, ['false'], {})['error'], 'cycle')
        deep = ['false']
        for _ in range(1000):
            deep = ['and', ['false'], deep]
        self.assertEqual(L.verify({}, {}, deep, {})['error'], 'depth_limit')
        for version in (True, 1.0, 2):
            self.assertFalse(L.verify({}, {}, ['false'], {'version': version, 'proof': []})['ok'])
        class BadList(list):
            def __iter__(self):
                raise AssertionError('custom input executed')
        self.assertFalse(L.verify({'D': BadList(['a'])}, {}, ['false'], {})['ok'])

    def test_wide_aliased_scan_charges_before_retaining_siblings(self):
        value = ['atom', 'A']
        for _ in range(18):
            value = [value] * 256

        class StopBudget(Exception):
            pass

        ticks = []
        def tick(amount):
            ticks.extend([None] * amount)
            if len(ticks) == 3:
                raise StopBudget()

        with self.assertRaises(StopBudget):
            with patch.object(L, 'MAX_INPUT_NODES', 256), patch.object(L, 'MAX_DEPTH', 16):
                L._scan(value, tick=tick)
        self.assertEqual(len(ticks), 3)


class ParserTests(unittest.TestCase):
    def test_controlled_syntax_precedence_quantifier_scope(self):
        f = L.parse_formula('forall x in People: Kind(x:People) implies '
                            'exists y in People: Knows(x:People, y:People)')
        self.assertEqual(f, ['forall', 'x', 'People', ['implies', pred('Kind', var('x', 'People')),
                           ['exists', 'y', 'People', pred('Knows', var('x', 'People'), var('y', 'People'))]]])
        self.assertEqual(L.parse_formula('P(D["a"])'), pred('P', const('a')))
        self.assertEqual(L.parse_formula('"P(D[a])"'), ['atom', 'P(D[a])'])
        self.assertEqual(L.parse_formula('not "a" and "b" or "c" implies "d" implies false'),
                         ['implies', ['or', ['and', ['implies', ['atom', 'a'], ['false']],
                          ['atom', 'b']], ['atom', 'c']], ['implies', ['atom', 'd'], ['false']]])
        self.assertEqual(L.parse_formula('(forall x in D: P(x:D)) and "next"')[0], 'and')
        self.assertEqual(L.parse_formula('P()'), pred('P'))
        L.expand({'People': ['Ada']}, {}, f)

    def test_parser_rejects_ambiguous_or_hostile_syntax(self):
        for text in ('forall x: P(x)', 'P(x)', 'P("Ada")', 'forall x in D P(x:D)',
                     'P(D["a"]', 'Every person is kind', '∀x P(x)', 'P(x:Ｄ)',
                     '"a" "b"', '"e\\u0301"', '"\\ud800"', '"\\u202e"',
                     '\u00a0false', 'not ' * 1000 + 'false', '(' * 1000 + 'false' + ')' * 1000):
            with self.subTest(text=text[:40]), self.assertRaises(L.FiniteLogicError):
                L.parse_formula(text)
        f = L.parse_formula('forall x in D: exists x in D: P(x:D)')
        with self.assertRaisesRegex(L.FiniteLogicError, 'shadowing'):
            L.expand({'D': []}, {}, f)


if __name__ == '__main__':
    unittest.main()
