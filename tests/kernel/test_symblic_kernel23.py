"""Symblic 2.3 kernel primitives: numbers(text), the median vote, model families by lineage and the two
check additions (the static lint hook and literal permute/vote/within options).

Kernel only: no model, no network, no stores.
"""

import os
import sys
import types
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import language as S  # noqa: E402


def evaluate(source, budget=None, **bindings):
    env = S.Env()
    for name, value in bindings.items():
        env.vars[name] = S.Binding(name, value)
    parser = S.Parser(S.tokenize(source), 1)
    node = parser.expr()
    parser.finish()
    return S.Kernel(env, S.KB(), budget or S.Budget()).eval(node)


def numbers(text, budget=None):
    return evaluate('numbers(t)', budget, t=text)


def sample(value, order, app='claude:haiku', weight=1):
    return {'value': value, 'hash': S.fingerprint(value), 'weight': weight, 'app': app, 'order': order}


class Numbers(unittest.TestCase):
    def test_the_contract_examples(self):
        self.assertEqual(numbers('Total due: $1,250.00 for 3 items (−5.5%)'), (1250, 3, Fraction(-11, 2)))
        for text in ('v2.3.1', '12,34', '1e5', 'x9'):
            self.assertEqual(numbers(text), (), text)
        self.assertEqual(numbers('800.'), (800,))
        self.assertEqual(numbers('2026-10-03'), (2026, 10, 3))
        self.assertEqual(numbers('10-20'), (10, 20))

    def test_signs_groups_and_boundaries(self):
        self.assertEqual(numbers('-7 and −2 but a-5'), (-7, -2))       # a-5 is one token (review A, 2.3)
        self.assertEqual(numbers('12,345,678 and 1,234,5678'), (12345678,))
        self.assertEqual(numbers('0.5, then 03'), (Fraction(1, 2), 3))
        self.assertEqual(numbers('_4 4_ .5 ,6 7.'), (7,))
        self.assertEqual(numbers('no digits ٣ here'), ())
        self.assertEqual(numbers(''), ())

    def test_values_are_the_kernels_own_numbers(self):
        got = numbers('1250.00 and 5.5')
        self.assertIs(type(got[0]), int)
        self.assertTrue(S.values_equal(got[0], 1250))
        self.assertEqual(S.fingerprint(got[1]), S.fingerprint(evaluate('5.5')))
        self.assertTrue(evaluate('1250 in numbers("$1,250.00")'))
        self.assertTrue(evaluate('5.5 in numbers("rate 5.50%")'))
        self.assertTrue(evaluate('numbers("a 1, b 2") = [1, 2]'))
        self.assertIsInstance(numbers('1 2'), tuple)

    def test_refusals(self):
        with self.assertRaises(S.SymblicError) as ctx:
            evaluate('numbers(5)')
        self.assertEqual(ctx.exception.kind, 'type')
        self.assertIn('numbers needs text', ctx.exception.message)
        with self.assertRaises(S.SymblicError) as ctx:
            numbers('1 ' * 10_001)
        self.assertIn('at most 20000 characters', ctx.exception.message)
        self.assertEqual(numbers('9' + ' ' * 19_999), (9,))

    def test_budget_is_ticked_by_the_text_length(self):
        text = 'x' * 999
        budget = S.Budget(10_000)
        numbers(text, budget)
        used = 10_000 - budget.left
        self.assertGreaterEqual(used, len(text) + 1)
        with self.assertRaises(S.SymblicError) as ctx:
            numbers(text, S.Budget(len(text)))
        self.assertIn('budget', ctx.exception.message)

    def test_registered_and_documented_not_denied(self):
        self.assertIn('numbers', S.BUILTINS)
        self.assertIn('numbers(text)', S.BUILTIN_DOCS['text'])
        self.assertNotIn('numbers', S.EVAL_DENIED)


class Median(unittest.TestCase):
    def test_odd_count_is_the_middle_value(self):
        r = S.consensus_median([sample(v, i) for i, v in enumerate([5, 1, 3])])
        self.assertEqual(r['value'], 3)
        self.assertEqual(r['hash'], S.fingerprint(3))
        self.assertEqual((r['support'], r['total'], r['distinct']), (1, 3, 3))
        self.assertEqual(r['agreement'], round(1 / 3, 4))
        self.assertTrue(r['contested'])
        self.assertFalse(r['tied'])
        self.assertEqual(r['spread'], {'min': '1', 'max': '5', 'mad': '2'})

    def test_even_count_is_the_lower_median_a_given_value(self):
        r = S.consensus_median([sample(v, i) for i, v in enumerate([4, 1, 2, 3])])
        self.assertEqual(r['value'], 2)
        r = S.consensus_median([sample(Fraction(5, 2), 0), sample(Fraction(7, 2), 1)])
        self.assertEqual(r['value'], Fraction(5, 2))

    def test_weights_move_the_median(self):
        r = S.consensus_median([sample(1, 0), sample(2, 1), sample(9, 2, weight=3)])
        self.assertEqual(r['value'], 9)
        self.assertEqual(r['agreement'], 0.6)
        self.assertFalse(r['contested'])
        # exactly half the weight at or below 1: the lower median is 1, but every value up to 5 is as good, so it
        # is a tie and contested (review B, 2026-10-03)
        r = S.consensus_median([sample(1, 0, weight=2), sample(5, 1), sample(6, 2)])
        self.assertEqual(r['value'], 1)
        self.assertEqual(r['agreement'], 0.5)
        self.assertTrue(r['tied'] and r['contested'])

    def test_within_counts_close_answers_as_support(self):
        xs = [sample(v, i) for i, v in enumerate([Fraction(99, 10), 10, Fraction(101, 10), 14])]
        self.assertEqual(S.consensus_median(xs)['agreement'], 0.25)
        r = S.consensus_median(xs, 0.5, Fraction(1, 10))
        self.assertEqual(r['value'], 10)
        self.assertEqual(r['support'], 3)
        self.assertEqual(r['agreement'], 0.75)
        self.assertFalse(r['contested'])
        self.assertEqual(r['within'], '0.1')
        self.assertEqual(S.consensus_median(xs, 0.5, '0.1')['support'], 3)
        self.assertEqual(S.consensus_median(xs, 0.8, '0.1')['contested'], True)
        self.assertEqual(r['spread'], {'min': '9.9', 'max': '14', 'mad': '0.1'})

    def test_families_are_those_of_the_supporters(self):
        xs = [sample(10, 0, 'claude:haiku'), sample(10, 1, 'copilot'), sample(50, 2, 'codex')]
        self.assertEqual(S.consensus_median(xs)['families'], ['anthropic'])
        self.assertEqual(S.consensus_median(xs, 0.5, 40)['families'], ['anthropic', 'openai'])

    def test_returned_keys(self):
        xs = [sample(v, i) for i, v in enumerate([1, 1, 2])]
        r = S.consensus_median(xs)
        base = S.consensus(xs)
        self.assertEqual(set(r), set(base) | {'vote', 'within', 'spread'})
        self.assertEqual(r['vote'], 'median')
        self.assertEqual(r['within'], '0')
        self.assertEqual((r['entropy'], r['entropy_bits'], r['tally']), (base['entropy'], base['entropy_bits'],
                                                                         base['tally']))
        self.assertEqual(S.consensus_median([]), {**S.consensus([]), 'vote': 'median'})

    def test_refusals(self):
        for bad in ('8', True, None, [1]):
            with self.assertRaises(S.SymblicError) as ctx:
                S.consensus_median([sample(1, 0), sample(bad, 1)])
            self.assertEqual(ctx.exception.kind, 'type')
            self.assertIn('vote=median needs numeric answers', ctx.exception.message)
        for bad in (-1, Fraction(-1, 2), '-0.5', 'ten', True, 0.5):
            with self.assertRaises(S.SymblicError) as ctx:
                S.consensus_median([sample(1, 0)], 0.5, bad)
            self.assertEqual(ctx.exception.kind, 'type')


class Families(unittest.TestCase):
    def test_every_row_of_the_lineage_rule(self):
        rows = {
            'claude:haiku': 'anthropic', 'claude:sonnet@node-a+high*2': 'anthropic', 'codex': 'openai',
            'chatgpt': 'openai', 'gemini:pro': 'google', 'agy': S.UNATTRIBUTED, 'kernel': 'kernel',
            'fake': 'fake', 'fake:a': 'fake',
            'copilot:claude-sonnet-4.5': 'anthropic', 'agy:claude-opus': 'anthropic', 'copilot:gpt-5': 'openai',
            'copilot': S.UNATTRIBUTED, 'council': S.UNATTRIBUTED, 'copilot:mystery-1': S.UNATTRIBUTED,
            'ollama:deepseek-r1:1.5b': 'alibaba', 'ollama:deepseek-r1:7b': 'alibaba',
            'ollama:deepseek-r1:14b': 'alibaba', 'ollama:deepseek-r1:32b@node-b': 'alibaba',
            'ollama:deepseek-r1:70b': 'meta', 'ollama:deepseek-r1:671b': 'deepseek',
            'ollama:deepseek-r1:8b': S.UNATTRIBUTED, 'ollama:deepseek-r1:latest': S.UNATTRIBUTED,
            'ollama:deepseek-r1': S.UNATTRIBUTED,
            'ollama:gemma3:4b': 'google', 'ollama:qwen3:4b-instruct@node-b': 'alibaba', 'ollama:llama3.2:1b': 'meta',
            'ollama:granite3.3:2b': 'ibm', 'ollama:phi4': 'microsoft', 'ollama:mistral:7b': 'mistral',
            'ollama:gpt-oss:20b': 'openai', 'OLLAMA:Qwen3:4B': 'alibaba', 'ollama:mystery:1b': S.UNATTRIBUTED,
            'ollama': S.UNATTRIBUTED, 'agy:gemini-3-pro': 'google', 'agy:gpt-oss-120b': 'openai',
            'ollama:phind-codellama': S.UNATTRIBUTED, 'ollama:phi3:mini': 'microsoft',
            'ollama:gpt-j:6b': S.UNATTRIBUTED, 'ollama:gpt-neox': S.UNATTRIBUTED, 'ollama:qwq': S.UNATTRIBUTED,
        }
        for label, family in rows.items():
            self.assertEqual(S.family_of(label), family, label)
        self.assertEqual(S.UNATTRIBUTED, 'unattributed')

    def test_families_of_lists_unattributed_only_alone(self):
        self.assertEqual(S.families_of(['copilot', 'claude:haiku', 'council']), ['anthropic'])
        self.assertEqual(S.families_of(['copilot', 'council']), ['unattributed'])
        self.assertEqual(S.families_of(['codex', 'claude:haiku', 'claude:sonnet']), ['anthropic', 'openai'])
        self.assertEqual(S.families_of([]), [])

    def test_an_unattributed_supporter_adds_no_family(self):
        votes = [sample(8, i, a) for i, a in enumerate(['claude:haiku', 'copilot', 'ollama:deepseek-r1:8b'])]
        r = S.consensus(votes)
        self.assertEqual(r['families'], ['anthropic'])
        self.assertEqual(r['tally'][0]['families'], ['anthropic'])
        alone = S.consensus([sample(8, 0, 'copilot'), sample(8, 1, 'council'), sample(9, 2, 'codex')])
        self.assertEqual(alone['families'], ['unattributed'])
        self.assertEqual([row['families'] for row in alone['tally']], [['unattributed'], ['openai']])


class CheckAdditions(unittest.TestCase):
    def setUp(self):
        self.saved = sys.modules.get('symblic.kernel.diagnose', None)
        self.had = 'symblic.kernel.diagnose' in sys.modules

    def tearDown(self):
        if self.had:
            sys.modules['symblic.kernel.diagnose'] = self.saved
        else:
            sys.modules.pop('symblic.kernel.diagnose', None)

    def stub(self, fn):
        mod = types.ModuleType('symblic.kernel.diagnose')
        if fn is not None:
            mod.static_warnings = fn
        sys.modules['symblic.kernel.diagnose'] = mod
        return mod

    SRC = 'define W as Int in 0..9.\nask x: W "pick a digit"\nensure x >= 0 else retry\n'

    def test_static_warnings_are_added(self):
        seen = {}

        def static_warnings(statements, types_):
            seen['kinds'] = [s.k for s in statements]
            seen['types'] = dict(types_)
            return [{'line': 2, 'message': 'x: its checks accept the empty answer 0', 'code': 'SYM_VACUOUS'}]
        self.stub(static_warnings)
        out = S.check(self.SRC)
        self.assertTrue(out['ok'], out)
        self.assertIn({'line': 2, 'message': 'x: its checks accept the empty answer 0', 'code': 'SYM_VACUOUS'},
                      out['warnings'])
        self.assertEqual(seen['kinds'], ['define', 'ask', 'ensure'])
        self.assertIn('W', seen['types'])

    def test_the_hook_fails_open(self):
        sys.modules['symblic.kernel.diagnose'] = None          # import raises ImportError
        plain = S.check(self.SRC)
        self.assertTrue(plain['ok'], plain)
        self.stub(lambda statements, types_: [])
        self.assertEqual(S.check(self.SRC), plain)
        self.stub(None)                                  # no static_warnings: AttributeError
        self.assertEqual(S.check(self.SRC), plain)

        def broken(statements, types_):
            raise RuntimeError('lint bug')
        self.stub(broken)
        self.assertEqual(S.check(self.SRC), plain)
        self.stub(lambda statements, types_: [{'line': 1}, 'text', {'line': 2, 'message': 'kept'}])
        out = S.check(self.SRC)
        self.assertEqual(out['warnings'], plain['warnings'] + [{'line': 2, 'message': 'kept'}])
        self.assertTrue(out['ok'])

    def errors(self, options, pre=''):
        sys.modules['symblic.kernel.diagnose'] = None
        out = S.check(f'{pre}ask n: Int "How many?" with {options}\n')
        return [e['message'] for e in out['errors'] if e['kind'] == 'syntax']

    def test_literal_permute(self):
        for good in ('permute=2', 'permute=6', 'permute=3.0'):
            self.assertEqual(self.errors(good), [], good)
        for bad in ('permute=1', 'permute=7', 'permute=2.5', 'permute', 'permute="3"', 'permute=three'):
            self.assertEqual(self.errors(bad), ['permute must be an integer from 2 to 6'], bad)
        self.assertEqual(self.errors('permute=k', 'let k = 9\n'), [])           # left to the runtime
        self.assertEqual(self.errors('permute=1 + 1'), [])

    def test_literal_vote_and_within(self):
        for good in ('vote=median', 'vote=auto', 'vote=whole', 'vote="fields"', 'vote=Median, within=0.5',
                     'vote=median, within=0'):
            self.assertEqual(self.errors(good), [], good)
        self.assertEqual(self.errors('vote=mean'), ['vote must be one of auto, whole, fields, median'])
        self.assertEqual(self.errors('vote=whole, within=1'), ['within needs vote=median'])
        self.assertEqual(self.errors('vote=mode, within=1'), ['vote must be one of auto, whole, fields, median',
                                                              'within needs vote=median'])
        self.assertEqual(self.errors('vote=v, within=1', 'let v = "whole"\n'), [])   # left to the runtime
        self.assertEqual(self.errors('within=1'), [])

    def test_permute_and_within_are_ask_options_not_defaults(self):
        self.assertIn('permute', S.ASK_OPTIONS)
        self.assertIn('within', S.ASK_OPTIONS)
        self.assertNotIn('permute', S.USE_OPTIONS)
        self.assertNotIn('within', S.USE_OPTIONS)
        sys.modules['symblic.kernel.diagnose'] = None
        out = S.check('use permute=3\nask n: Int "How many?"\n')
        self.assertFalse(out['ok'])


class Version(unittest.TestCase):
    def test_language_version(self):
        # 2.4 (2026-10-04) added Code answers, js_test/js_run, route=search and spec sheets on top of 2.3
        self.assertEqual(S.VERSION, '2.5')
        self.assertEqual(S.kernel_id()['lang'], '2.5')




class _Node:
    line = 0
    col = 0


def _call(name, *args, steps=200_000):
    return S.BUILTINS[name](S.Kernel(S.Env(), S.KB(), S.Budget(steps)), _Node, *args)


class Quotes(unittest.TestCase):
    """quotes(passage, quote): an exact occurrence as whole words and whole numerals (lexical only)."""

    def test_exact_characters_and_case(self):
        self.assertTrue(_call('quotes', 'The laser gives 1 mW.', '1 mW'))
        self.assertFalse(_call('quotes', 'The laser gives 1 mW.', '1 MW'))
        self.assertFalse(_call('quotes', 'Straße 5', 'STRASSE'))
        self.assertFalse(_call('quotes', 'Total due', 'total due'))
        self.assertTrue(S.BUILTINS['contains'](None, _Node, '1 mW', '1 MW'))     # contains folds case; quotes does not

    def test_white_space_runs_are_one_space(self):
        self.assertTrue(_call('quotes', 'a\n  b\t c', 'a b c'))
        self.assertTrue(_call('quotes', 'first line\nsecond line', '  line second  '))
        self.assertFalse(_call('quotes', 'ab c', 'a b c'))

    def test_an_empty_quote_is_false(self):
        self.assertFalse(_call('quotes', 'abc', ''))
        self.assertFalse(_call('quotes', 'abc', ' \n '))

    def test_a_quote_may_not_cut_a_numeral_or_its_sign(self):
        for passage, quote, expected in [
                ('Total: 120 units', '20', False), ('Total: 120 units', '120', True),
                ('change -5 today', '5', False), ('change -5 today', '-5', True),
                ('change −5 today', '5', False), ('pages 10-20', '20', True), ('x-5', '-5', False),
                ('pi is 3.14', '3', False), ('pi is 3.14', '14', False), ('pi is 3.14', '3.', False),
                ('pi is 3.14.', '3.14', True), ('cost 1,250 USD', '250', False), ('cost 1,250 USD', '1', False),
                ('cost 1,250 USD', '1,250', True), ('mix 3/4 cup', '3', False), ('mix 3/4 cup', '/4', False),
                ('mix 3/4 cup', '3/4', True), ('at 10^3 Hz', '10', False), ('costs $800.', '800', True),
                ('rate 5% a year', '5', True)]:
            with self.subTest(passage=passage, quote=quote):
                self.assertEqual(_call('quotes', passage, quote), expected)

    def test_a_quote_may_not_cut_a_word(self):
        self.assertFalse(_call('quotes', 'an unhappy man', 'happy'))
        self.assertFalse(_call('quotes', 'an unhappy man', 'an un'))
        self.assertTrue(_call('quotes', 'an unhappy man', 'unhappy man'))
        self.assertTrue(_call('quotes', 'He said "no".', '"no"'))

    def test_any_whole_occurrence_counts(self):
        self.assertTrue(_call('quotes', 'item 120, then 20 more', '20'))

    def test_composed_and_decomposed_text_compare_equal(self):
        self.assertTrue(_call('quotes', 'café au lait', 'café'))

    def test_refusals_and_budget(self):
        with self.assertRaises(S.SymblicError) as c:
            _call('quotes', 5, 'x')
        self.assertEqual(c.exception.kind, 'type')
        with self.assertRaises(S.SymblicError):
            _call('quotes', 'x' * 1_000_001, 'x')
        with self.assertRaises(S.SymblicError):                 # every occurrence is inside a word: bounded work
            _call('quotes', 'a' * 5000, 'a', steps=100)
        self.assertIn('quotes', S.BUILTINS)
        self.assertIn('quotes(passage, quote)', S.BUILTIN_DOCS['text'])

    def test_a_program_can_require_a_quoted_number(self):
        ok = S.Kernel(S.Env(), S.KB(), S.Budget(10_000))
        p = S.Parser(S.tokenize('quotes(doc, q) and 120 in numbers(q)'), 1)
        env = S.Env()
        env.vars['doc'] = S.Binding('doc', 'Total: 120 units')
        env.vars['q'] = S.Binding('q', '120 units')
        self.assertIs(ok.eval(p.expr(), env), True)
        env.vars['q'] = S.Binding('q', '20 units')              # cuts the numeral: not a quote
        self.assertIs(ok.eval(S.Parser(S.tokenize('quotes(doc, q) and 20 in numbers(q)'), 1).expr(), env), False)


class NumbersInArithmetic(unittest.TestCase):
    """A numeral that is part of a fraction, a power or an unspaced product is not read: no fragment of it."""

    def test_fractions_powers_and_products(self):
        self.assertEqual(_call('numbers', 'mix 3/4 cup'), ())
        self.assertEqual(_call('numbers', 'on 10/03/2026'), ())
        self.assertEqual(_call('numbers', 'at 10^3 Hz and x^2'), ())
        self.assertEqual(_call('numbers', '2^x'), ())
        self.assertEqual(_call('numbers', '10⁻³ m and 2.5×10 kg'), ())
        self.assertEqual(_call('numbers', '2*3'), ())
        self.assertEqual(_call('numbers', 'km/5 and 24/7'), (5,))

    def test_spaced_arithmetic_is_read_as_written(self):
        self.assertEqual(_call('numbers', '2.5 × 10 units'), (Fraction(5, 2), 10))


class AnySchema(unittest.TestCase):
    def test_any_is_every_json_value(self):
        self.assertEqual(S.json_schema({'k': 'any'}), {})
        self.assertEqual(S.json_schema({'k': 'list', 'of': {'k': 'any'}}), {'type': 'array', 'items': {}})
        self.assertEqual(S.json_schema({'k': 'svg'}), {'type': 'string'})


class Lineage(unittest.TestCase):
    """A distilled model descends from its base weights and from its teacher; families are counted by a largest
    set of supporters whose lineages do not overlap."""

    def test_lineage_of(self):
        self.assertEqual(S.lineage_of('ollama:deepseek-r1:7b'), frozenset({'alibaba', 'deepseek'}))
        self.assertEqual(S.lineage_of('ollama:deepseek-r1:70b@node-a'), frozenset({'meta', 'deepseek'}))
        self.assertEqual(S.lineage_of('ollama:deepseek-r1:671b'), frozenset({'deepseek'}))
        self.assertEqual(S.lineage_of('ollama:deepseek-r1:8b'), frozenset())
        self.assertEqual(S.lineage_of('claude:sonnet'), frozenset({'anthropic'}))
        self.assertEqual(S.lineage_of('copilot'), frozenset())

    def test_a_distill_and_its_base_or_its_teacher_count_once(self):
        self.assertEqual(S.families_of(['ollama:deepseek-r1:7b', 'ollama:qwen3:4b']), ['alibaba'])
        self.assertEqual(S.families_of(['ollama:deepseek-r1:7b', 'ollama:deepseek-r1:671b']), ['deepseek'])
        self.assertEqual(S.families_of(['ollama:deepseek-r1:7b', 'ollama:deepseek-r1:70b']), ['alibaba+deepseek'])

    def test_disjoint_lineages_count_separately(self):
        self.assertEqual(S.families_of(['ollama:deepseek-r1:7b', 'ollama:llama3.2:1b']), ['alibaba+deepseek', 'meta'])
        self.assertEqual(S.families_of(['ollama:deepseek-r1:7b', 'ollama:deepseek-r1:671b', 'ollama:qwen3:4b']),
                         ['alibaba', 'deepseek'])
        self.assertEqual(S.families_of(['claude', 'codex', 'gemini', 'ollama:granite3.3:2b']),
                         ['anthropic', 'google', 'ibm', 'openai'])

    def test_unknown_lineage_adds_nothing(self):
        self.assertEqual(S.families_of(['copilot', 'council']), [S.UNATTRIBUTED])
        self.assertEqual(S.families_of(['copilot', 'claude:sonnet', 'copilot:claude-sonnet-4.5']), ['anthropic'])
        self.assertEqual(S.families_of(['ollama:renamed-model', 'ollama:another']), [S.UNATTRIBUTED])
        self.assertEqual(S.families_of([]), [])

    def test_the_count_in_a_vote(self):
        samples = [{'value': 1, 'hash': S.fingerprint(1), 'weight': 1, 'app': a, 'order': i} for i, a in
                   enumerate(['ollama:deepseek-r1:7b', 'ollama:qwen3:4b', 'copilot'])]
        self.assertEqual(S.consensus(samples)['families'], ['alibaba'])


class LineageLabel(unittest.TestCase):
    """Which label a reply's lineage is read from (the reply's reported model or the requested label)."""

    def test_an_echoed_engine_name_is_not_an_observed_model(self):
        self.assertEqual(S.lineage_label('agy', 'agy'), ('agy', 'requested_app'))
        self.assertEqual(S.family_of('agy'), S.UNATTRIBUTED)
        self.assertEqual(S.lineage_label('codex', 'codex'), ('codex', 'requested_app'))
        self.assertEqual(S.lineage_label('claude:haiku', 'haiku'), ('claude:haiku', 'requested_app'))

    def test_a_known_reported_model_is_used(self):
        self.assertEqual(S.lineage_label('agy', 'claude-opus-4'), ('claude-opus-4', 'observed_model'))
        self.assertEqual(S.lineage_label('copilot', 'gpt-5'), ('gpt-5', 'observed_model'))
        self.assertEqual(S.lineage_label('ollama:llama3.2', 'llama3.2:latest'), ('llama3.2:latest', 'observed_model'))

    def test_a_multi_maker_front_end_reporting_an_unknown_model_has_no_lineage(self):
        self.assertEqual(S.lineage_label('agy', 'internal-7'), ('', 'observed_model'))
        self.assertEqual(S.lineage_label('copilot:gpt-5', 'mystery-x'), ('', 'observed_model'))
        self.assertEqual(S.lineage_label('ollama:qwen3:4b', 'something-else'), ('', 'observed_model'))
        self.assertEqual(S.lineage_label('claude', 'us.anthropic.deployment-3'), ('claude', 'requested_app'))

    def test_an_unknown_agy_adds_no_second_family(self):
        self.assertEqual(S.families_of(['agy', 'claude']), ['anthropic'])
        self.assertEqual(S.families_of(['agy:claude-sonnet-4.5', 'claude']), ['anthropic'])
        self.assertEqual(S.families_of(['agy:gemini-3-pro', 'claude']), ['anthropic', 'google'])



class LexicalReview(unittest.TestCase):
    """The cases of root's lexical review of snapshot A (2026-10-03): numbers() reads no fragment of a scientific
    numeral, a fraction, a product or a power; quotes() cuts no numeral, sign or letter from its marks."""

    NUMBERS = [
        ('$2,345.75; 4 kg; (−0.25%)', (Fraction(9383, 4), 4, Fraction(-1, 4))),
        ('€ 0.00010 and £12.00', (Fraction(1, 10000), 12)),
        ('range 3-7; year 2025-09-30', (3, 7, 2025, 9, 30)),
        ('2 × 10 and 1 / 4 and 2 ^ 3', (2, 10, 1, 4, 2, 3)),
        ('mixed 2 units; 12kg; kg12; x_4; _8', (2,)),
        ('漢2 2漢 ٣ ９ 3٢ ٢3', ()),
        ('NFC café; +7; -0; −1', (7, 0, -1)),
        ('7, end; 8. end', (7, 8)),
        ('1e-3', ()),
        ('1e+3', ()),
        ('1e−3', ()),
        ('1.25E-6', ()),
        ('-1e-3', ()),
        ('2.5×10^-3', ()),
        ('2.5×10^−3', ()),
        ('1/-2', ()),
        ('1/−2', ()),
        ('-1/-2', ()),
        ('1×-2', ()),
        ('1·−2', ()),
        ('1*-2', ()),
        ('12,34', ()),
        ('2.3.4', ()),
        ('1e3', ()),
        ('2/3', ()),
        ('2×3', ()),
        ('2^3', ()),
        ('x^2', ()),
        ('10⁻³', ()),
        ('10⁺³', ()),
        ('2²', ()),
        ('10e٣', ()),
    ]
    QUOTES = [
        ('alpha beta', 'alpha', True),
        ('alphabet', 'alpha', False),
        ('−17', '17', False),
        ('−17', '−17', True),
        ('117', '17', False),
        ('1.75', '.75', False),
        ('1 mW', '1 MW', False),
        ('Café', 'Café', True),
        ('two\n\t words', 'two words', True),
        (' x  y ', 'x y', True),
        ('any', '   ', False),
        ('foo_bar', 'bar', False),
        ('1e-3', '3', False),
        ('1e+3', '3', False),
        ('1e−3', '3', False),
        ('12/−3', '12', False),
        ('2^−3', '2', False),
        ('á̧', 'á', False),
        ('ना', 'न', False),
    ]
    QUOTED_NUMBER = [
        ('1e-3', '1e-3', '3', False),
        ('1e-3', '3', '3', False),
        ('1/−2', '1/−2', '1', False),
        ('Dose: 1.75 mg', '1.75 mg', '7/4', True),
        ('Power: 2 mW', '2 MW', '2', False),
        ('Café has 2\n visitors', 'Café has 2 visitors', '2', True),
    ]

    def test_numbers(self):
        for text, expected in self.NUMBERS:
            with self.subTest(text=text):
                self.assertEqual(_call('numbers', text), expected)

    def test_quotes(self):
        for passage, quote, expected in self.QUOTES:
            with self.subTest(passage=passage, quote=quote):
                self.assertIs(_call('quotes', passage, quote), expected)

    def test_quoted_number(self):
        # text.quoted_number = quotes(passage, quote) and value in numbers(quote)
        for passage, quote, value, expected in self.QUOTED_NUMBER:
            with self.subTest(passage=passage, quote=quote, value=value):
                got = _call('quotes', passage, quote) and Fraction(value) in _call('numbers', quote)
                self.assertIs(got, expected)

    def test_a_letter_with_marks_and_an_identifier_are_whole_tokens(self):
        self.assertEqual(_call('numbers', 'COVID-19 and x-5 and 1E+3 and 1/+2'), ())
        self.assertFalse(_call('quotes', 'COVID-19 cases', '19 cases'))
        self.assertTrue(_call('quotes', 'COVID-19 cases', 'COVID-19 cases'))
        self.assertFalse(_call('quotes', '1e-3 mol', '1e'))
        self.assertTrue(_call('quotes', 'about 1e-3 mol', '1e-3 mol'))



class AdapterCalls(unittest.TestCase):
    """A wrong call to an adapter builtin is told in the program's terms (review B, 2026-10-03)."""

    def test_wrong_argument_counts_and_options_name_the_builtin(self):
        from symblic.kernel import run as SR
        for src, message in [
                ('let r = reconcile([1, 2], [[1, 1]], [1], [1, 1], [1]).', 'reconcile takes 3 to 4 arguments (x, C, d, weights=), not 5'),
                ('let r = ising_energy([1], [[0]]).', 'ising_energy takes 3 arguments (h, J, s), not 2'),
                ('let r = agreement_process([1], [[[1]]], [1]).', 'agreement_process takes 4 arguments (priors, partitions, event, state), not 3'),
                ('let r = common_partition([[[1], [2]]], x=1).', 'common_partition has no option x=')]:
            with self.subTest(src=src):
                rep = SR.Run(src, None, None, {'by': 'kernel'}).execute()
                self.assertEqual((rep['status'], rep['error']['kind'], rep['error']['message']), ('failed', 'type', message))
        rep = SR.Run('let r = reconcile([1, 2], [[1, 1]], [3], weights=[1, 2]).\nshow r.value.\n', None, None,
                     {'by': 'kernel'}).execute()
        self.assertEqual((rep['status'], rep['outputs'][0]['text']), ('done', '[1, 2]'))


class KernelReviewB(unittest.TestCase):
    """Fable's adversarial review of snapshot B, kernel lens (2026-10-03)."""

    def test_spaced_scientific_notation_dashes_groups_and_operators_are_not_read(self):
        for text in ('2.5 × 10^3 kg', '6.02 × 10²³ molecules', '1.6 x 10^-19', '–5 °C', 'temperature ‑5', 'loss of －5',
                     '±5', '1 250 000 people', "1'250'000", '1\u202f000', 'price 3\u200b400 USD', '3÷4', '3⁄4', '3∕4',
                     '10**3', '2**-3'):
            with self.subTest(text=text):
                self.assertEqual(_call('numbers', text), ())
        self.assertEqual(_call('numbers', '10–20'), (10, 20))                  # an en dash between numbers joins them
        self.assertEqual(_call('numbers', '2.5 × 10 units'), (Fraction(5, 2), 10))
        self.assertEqual(_call('numbers', 'in 2026 100 people'), (2026, 100))

    def test_quotes_cut_no_part_of_those(self):
        for passage, quote in (('6.02 × 10²³ molecules', '6.02'), ('–5 °C', '5'), ('1 250 000 people', '250'),
                               ('1 250 000', '250 000'), ('3⁄4', '4'), ('10**3', '10'), ('price 3\u200b400 USD', '3'),
                               ('the dose was 2\u00ad500 mg', '500 mg')):
            with self.subTest(passage=passage, quote=quote):
                self.assertFalse(_call('quotes', passage, quote))
        self.assertTrue(_call('quotes', 'pages 10–20', '20'))
        self.assertTrue(_call('quotes', 'about 1e-3 mol', '1e-3 mol'))

    def test_the_scans_are_linear(self):
        import time
        t0 = time.monotonic()
        self.assertEqual(_call('numbers', '1,' * 10_000), ())
        self.assertTrue(_call('quotes', '1' * 999_990 + ' x', 'x'))
        with self.assertRaises(S.SymblicError):                            # overlapping finds pay for what they read
            _call('quotes', 'a' * 80_000, 'a' * 40_000, steps=200_000)
        self.assertLess(time.monotonic() - t0, 10)                         # minutes to hours before the fix

    def test_an_exact_half_at_the_median_is_a_tie(self):
        def sample(v, o, app='claude:haiku'):
            return {'value': v, 'hash': S.fingerprint(v), 'weight': 1, 'app': app, 'order': o}
        r = S.consensus_median([sample(1, 0), sample(100, 1, 'codex:gpt-5')])
        self.assertEqual((r['value'], r['tied'], r['contested']), (1, True, True))
        r = S.consensus_median([sample(1, 0), sample(2, 1), sample(1000, 2), sample(1001, 3)], 0.5, within=1)
        self.assertEqual((r['tied'], r['contested']), (True, True))
        r = S.consensus_median([sample(1, 0), sample(2, 1)], 0.5, within=1)   # the two medians agree within the tolerance
        self.assertEqual((r['value'], r['tied'], r['contested']), (1, False, False))

    def test_check_is_not_quadratic_in_the_number_of_asks(self):
        import time
        t0 = time.monotonic()
        S.check(''.join('act notify.send with key="k" "x".\n' for _ in range(800)))
        self.assertLess(time.monotonic() - t0, 8)                          # 15.9 s before (2.2 too)


if __name__ == '__main__':
    unittest.main()
