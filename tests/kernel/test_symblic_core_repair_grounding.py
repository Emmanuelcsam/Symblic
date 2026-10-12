"""Core-repair regressions for source witnesses (epistemic-4/6/7); no providers, stores or external calls."""
import copy
import unittest

from symblic.kernel import language as S
from symblic.kernel import grounding as G
from symblic.kernel.run import Run


class Apps:
    """Fake constructor: the i-th call gets values[i] (the last repeats); records every request."""

    def __init__(self, *values):
        self.values, self.requests = values, []

    def call(self, request):
        index = len(self.requests)
        self.requests.append(request)
        if not self.values:
            raise AssertionError('No model call is permitted')
        return {'ok': True, 'json': {'answer': self.values[min(index, len(self.values) - 1)]},
                'model': 'fake', 'node': 'isolated'}


def span(source, start, end):
    return G.source_span(source, start, end)


def field_case(text, separator, label, value, *, prefix=': ', suffix='', region=None, value_at=None):
    """(source, contract, candidate) for a one-label literal field; value_at overrides the value start."""
    source = G.source_record('invoice', text)
    region = region or span(source, 0, len(text))
    contract = G.field_contract('total', source, labels=[label], region=region, separator=separator,
                                prefix=prefix, suffix=suffix)
    at = text.index(label)
    start = at + len(label) + len(prefix) if value_at is None else value_at
    candidate = {'contract_sha256': contract['sha256'], 'label': span(source, at, at + len(label)),
                 'value': span(source, start, start + len(value))}
    return source, contract, candidate


def codes(report):
    return [issue.get('code') for issue in report['issues']]


class FieldNumberBoundary(unittest.TestCase):
    """epistemic-4: a declared separator, region end or suffix inside a numeric token never truncates it."""

    def refused(self, *args, **kwargs):
        source, contract, candidate = field_case(*args, **kwargs)
        report = G.verify_field(source, contract, candidate)
        self.assertFalse(report['accepted'], report.get('value'))
        self.assertNotIn('value', report)
        return report

    def accepted(self, *args, **kwargs):
        source, contract, candidate = field_case(*args, **kwargs)
        report = G.verify_field(source, contract, candidate)
        self.assertTrue(report['accepted'], report['issues'])
        return report

    def test_thousands_separator_equal_to_field_separator_refuses_both_spans(self):
        # Before the repair the truncated span '1' was accepted with numerator 1.
        self.assertEqual(codes(self.refused('Total: 1,200, Items: 3', ',', 'Total', '1')),
                         ['ambiguous_number_boundary'])
        self.assertEqual(codes(self.refused('Total: 1,200, Items: 3', ',', 'Total', '1,200')),
                         ['ambiguous_number_boundary'])

    def test_decimal_point_equal_to_field_separator_refuses(self):
        self.assertEqual(codes(self.refused('Price: 3.75. Qty: 2.', '.', 'Price', '3')),
                         ['ambiguous_number_boundary'])
        self.assertEqual(codes(self.refused('Balance: -40.5;Fee: 2', '.', 'Balance', '-40')),
                         ['ambiguous_number_boundary'])

    def test_separator_starting_with_a_digit_cannot_eat_the_last_digit(self):
        self.assertEqual(codes(self.refused('Total: 120', '0', 'Total', '12')), ['ambiguous_number_boundary'])

    def test_locale_grouping_marks_are_number_joiners(self):
        for mark in ("'", '’', '\u00a0', '\u202f', '\u2009', '_'):
            with self.subTest(mark=repr(mark)):
                self.refused(f'Total: 1{mark}200; Items: 3', mark, 'Total', '1')

    def test_region_end_inside_a_number_refuses(self):
        text = 'Total: 1234; Items: 3'
        source = G.source_record('invoice', text)
        report = self.refused(text, ';', 'Total', '12', region=span(source, 0, text.index('34')))
        self.assertEqual(codes(report), ['ambiguous_number_boundary'])

    def test_declared_suffix_starting_inside_the_number_refuses(self):
        report = self.refused('Rate: 5.25 percent', ';', 'Rate', '5', suffix='.25 percent')
        self.assertEqual(codes(report), ['ambiguous_number_boundary'])

    def test_numeral_operators_between_digits_join_one_number(self):
        # Review e4-2: the kernel reads 3/4, 2×10, 3·5 and 3÷4 as one numeral (quotes() refuses "3 inside 3/4",
        # numbers() skips both operands). Before the fix a separator or suffix there accepted the left operand.
        for mark in ('/', '⁄', '∕', '·', '×', '÷', '*'):
            with self.subTest(mark=mark):
                text = f'Qty: 3{mark}4; Items: 2'
                self.assertEqual(codes(self.refused(text, mark, 'Qty', '3')), ['ambiguous_number_boundary'])
                self.assertEqual(codes(self.refused(text, ';', 'Qty', '3', suffix=f'{mark}4')),
                                 ['ambiguous_number_boundary'])
        # An operator that no digit follows still ends the field: 3/hr, 5× faster.
        self.assertEqual(self.accepted('Rate: 3/hr; Items: 2', '/', 'Rate', '3')['value']['numerator'], '3')
        self.assertEqual(self.accepted('Gain: 5× faster', ';', 'Gain', '5', suffix='× faster')
                         ['value']['numerator'], '5')
        # The joiners copy the kernel's operator set; a kernel change must be mirrored here.
        self.assertEqual(G._NUMERAL_OPERATORS, frozenset(S._OPERATORS))

    def test_superscripts_fractions_exponents_and_powers_continue_the_number(self):
        # Review e4-3: a suffix that starts with a number character (², ½, ⅞), an exponent (e5, E-3) or a power
        # (^3, **3, ⁻³) continues the written number; before the fix 10², 3½ and 1e5 were accepted as 10, 3, 1.
        for text, value, suffix in (('Area: 10²; x', '10', '²'), ('Qty: 3½; x', '3', '½'),
                                    ('Qty: 7⅞; x', '7', '⅞'), ('N: 1e5; x', '1', 'e5'),
                                    ('N: 2.5E-3; x', '2.5', 'E-3'), ('N: 4e+2; x', '4', 'e+2'),
                                    ('N: 10^3; x', '10', '^3'), ('N: 10**3; x', '10', '**3'),
                                    ('N: 10⁻³; x', '10', '⁻³'), ('N: 12Ⅻ; x', '12', 'Ⅻ')):
            with self.subTest(text=text):
                label = text.split(':')[0]
                self.assertEqual(codes(self.refused(text, ';', label, value, suffix=suffix)),
                                 ['ambiguous_number_boundary'])
        # Units that merely start with e/E, spaced units and CJK multiplier units stay expressible.
        for text, value, suffix in (('Energy: 5eV; x', '5', 'eV'), ('Cost: 2EUR; x', '2', 'EUR'),
                                    ('Area: 3 m²; x', '3', ' m²'), ('Price: 5万元; x', '5', '万元')):
            with self.subTest(text=text):
                self.accepted(text, ';', text.split(':')[0], value, suffix=suffix)

    def test_unambiguous_separators_keep_working(self):
        report = self.accepted('Price: 3.75. Qty: 2.', '. ', 'Price', '3.75')
        self.assertEqual((report['value']['numerator'], report['value']['denominator']), ('15', '4'))
        self.assertEqual(self.accepted('Price: 3. Qty: 2.', '.', 'Price', '3')['value']['numerator'], '3')
        self.assertEqual(self.accepted('Qty: 3,Total: 120', ',', 'Qty', '3')['value']['numerator'], '3')
        self.assertEqual(self.accepted('Total: 1, 200 more', ',', 'Total', '1')['value']['numerator'], '1')
        self.assertEqual(self.accepted('Balance: -40.5;Fee: 2', ';', 'Balance', '-40.5')['value']['numerator'],
                         '-81')
        # Units attached without a space stay expressible through the literal suffix.
        self.assertEqual(self.accepted('Mass: 120kg; Items: 3', ';', 'Mass', '120', suffix='kg')
                         ['value']['numerator'], '120')
        # ASCII whitespace and line breaks end a numeric token.
        self.assertEqual(self.accepted('Total: 120\n45 apples', '\n', 'Total', '120')['value']['numerator'],
                         '120')

    def test_witnessed_number_in_cannot_converge_on_a_truncated_span(self):
        source, contract, right = field_case('Total: 1,200, Items: 3', ',', 'Total', '1,200')
        wrong = copy.deepcopy(right)
        wrong['value'] = span(source, right['value']['start'], right['value']['start'] + 1)
        apps = Apps(right, wrong)
        program = ('import text as prose.\ngiven source: Any.\ngiven contract: Any.\n'
                   'let receipt=prose.witnessed_number_in(source,contract).\n')
        run = Run(program, inputs={'source': source, 'contract': contract}, applicators=apps,
                  options={'by': 'fake:constructor', 'effort': 'low', 'retries': 1, 'profile': 'verified',
                           'budget': 24000})
        report = run.execute()
        self.assertEqual(report['status'], 'failed', 'a truncated number must not be accepted')
        self.assertEqual(len(apps.requests), 2)
        self.assertIsNone(run.kernel.env.lookup('receipt'))
        self.assertIn('ambiguous_number_boundary', apps.requests[1]['prompt'])


def summary_case(text, required, *, joiner='\n…\n'):
    source = G.source_record('notice', text)
    rows = [{'id': ident, 'span': span(source, text.index(quote), text.index(quote) + len(quote))}
            for ident, quote in required]
    return source, G.summary_contract('s', source, required=rows, joiner=joiner)


def summarize(source, contract, spans):
    candidate = {'contract_sha256': contract['sha256'], 'spans': spans,
                 'text': contract['joiner'].join(row['quote'] for row in spans)}
    return G.verify_summary(source, contract, candidate)


class SummaryWholeTokens(unittest.TestCase):
    """epistemic-6: extractive spans start and end at whole-word and whole-numeral boundaries."""

    TEXT = 'The bridge is unsafe for trucks. Inspection due 2027.'

    def setUp(self):
        self.source, self.contract = summary_case(self.TEXT, [('inspection', 'Inspection due 2027.')])
        self.required = span(self.source, self.TEXT.index('Inspection'), len(self.TEXT))

    def at(self, quote, offset=0, length=None):
        start = self.TEXT.index(quote) + offset
        return span(self.source, start, start + (len(quote) - offset if length is None else length))

    def test_span_cut_inside_a_word_cannot_invert_meaning(self):
        # Before the repair: accepted, complete coverage, rendered 'safe for trucks.\n…\nInspection due 2027.'
        report = summarize(self.source, self.contract, [self.at('unsafe for trucks.', 2), self.required])
        self.assertFalse(report['accepted'])
        self.assertEqual(codes(report), ['partial_token'])
        self.assertNotIn('rendered', report)
        ends_inside = summarize(self.source, self.contract, [self.at('The bridge is unsafe', 0, 17), self.required])
        self.assertEqual(codes(ends_inside), ['partial_token'])

    def test_numerals_and_signs_are_whole_tokens(self):
        cut_year = summarize(self.source, self.contract, [self.at('The bridge'), self.at('2027.', 1)])
        # The code, not just the refusal: the preimage refused this for an unrelated reason (missing_required_spans).
        self.assertEqual(codes(cut_year), ['partial_token'])
        for text, quote, offset, length in (('Pi is 3.14 today.', '3.14 today.', 0, 1),
                                            ('Pi is 3.14 today.', '3.14 today.', 2, None),
                                            ('Pi is 3.14 today.', '3.14 today.', 1, None),
                                            ('Low: -5 C overnight.', '-5 C overnight.', 1, None),
                                            ('Paid 1,250 dollars.', '1,250 dollars.', 2, None)):
            with self.subTest(text=text, offset=offset):
                source, contract = summary_case(text, [])
                start = text.index(quote) + offset
                end = start + (len(quote) - offset if length is None else length)
                self.assertEqual(codes(summarize(source, contract, [span(source, start, end)])), ['partial_token'])

    def test_contractions_hyphenated_words_and_combining_marks_are_not_split(self):
        for text, start_quote, offset, length in (("The bridge can't carry trucks.", "The bridge can't", 0, 14),
                                                  ('Non-toxic paint only.', 'Non-toxic paint only.', 4, None),
                                                  ('The café closed.', 'The café', 0, 8)):
            with self.subTest(text=text):
                source, contract = summary_case(text, [])
                start = text.index(start_quote) + offset
                end = start + (len(start_quote) - offset if length is None else length)
                self.assertEqual(codes(summarize(source, contract, [span(source, start, end)])), ['partial_token'])

    def test_numeral_cuts_follow_the_kernel_quotes_rule(self):
        # Review e6-1: every row was an exact extraction with complete coverage after the first fix, while the
        # kernel's quotes() refuses each span: fractions, digit groups, powers, scientific notation, products and
        # dash signs. Runs of white space read as one space, as quotes() reads a passage.
        quotes = S.BUILTINS['quotes']
        kernel, node = S.Kernel(), S.Node('call', 1, 1)
        for text, quote, offset, length in (('Mix 3/4 cup of water.', 'Mix 3/4', 0, 5),
                                            ('Mix 3/4 cup of water.', '3/4 cup of water.', 2, None),
                                            ('Population 1 250 000 people.', '1 250 000 people.', 2, None),
                                            ('Population 1  250\n000 people.', '1  250\n000 people.', 3, None),
                                            ('Area is 10^3 m2 here.', 'Area is 10^3', 0, 10),
                                            ('Dose 1.5×10^3 units.', 'Dose 1.5×10^3', 0, 8),
                                            ('Dose 2.5 x 10^3 units.', 'Dose 2.5 x 10^3', 0, 8),
                                            ('N is 6.02 × 10²³ here.', 'N is 6.02 × 10²³', 0, 9),
                                            ('Load 2×10 kg each.', '10 kg each.', 0, None),
                                            ('Low: －5 C tonight.', '5 C tonight.', 0, None),
                                            ('Low: ﹣5 C tonight.', '5 C tonight.', 0, None),
                                            ('Low: –5 C tonight.', '5 C tonight.', 0, None)):
            with self.subTest(text=text, offset=offset, length=length):
                source, contract = summary_case(text, [])
                start = text.index(quote) + offset
                end = start + (len(quote) - offset if length is None else length)
                self.assertFalse(quotes(kernel, node, text, text[start:end]))
                self.assertEqual(codes(summarize(source, contract, [span(source, start, end)])), ['partial_token'])

    def test_every_numeral_cut_quotes_refuses_is_refused(self):
        # Parity sweep (review e6-1): each span that occurs once in its passage and does not start or end with
        # white space, which the kernel's quotes() refuses, is refused here too (spans may be refused more
        # strictly here: intra-word apostrophes and hyphens, and the number joiners quotes() does not know).
        quotes = S.BUILTINS['quotes']
        kernel, node = S.Kernel(), S.Node('call', 1, 1)
        passages = ('Mix 3/4 cup, 1/-2 or 12/−3 now.', 'Dates 10/04/2026 and 3÷4 or 3⁄4 or 3∕4.',
                    'Pop 1 250 000 or 1 250 or 1 250 or 1 250 or 1\'250 or 1’250 ok.',
                    'Sci 1e-3, 1.25E+6, 6.02 × 10²³, 2.5 x 10^3, 4·10^2 and 1.5×10**3.',
                    'Pow 10^3, x^2, 10**3, 10⁻³ and 2×10 or 1*-2 then.',
                    'Signs -5, −5, +5, –5, ±5, －5, ﹣5, ‑5 and 10–20, 10-20 too.',
                    'Pi 3.14, $1,250.00 for 3 (−5.5%) v2.3.1 12,34 x9 COVID-19.')
        checked = 0
        for text in passages:
            for i in range(len(text)):
                for j in range(i + 1, min(len(text), i + 16) + 1):
                    piece = text[i:j]
                    if piece != piece.strip() or text.find(piece) != i or text.find(piece, i + 1) >= 0:
                        continue
                    if quotes(kernel, node, text, piece):
                        continue
                    checked += 1
                    with self.subTest(text=text, span=piece):
                        with self.assertRaises(G.GroundingError) as refused:
                            G._whole_token_spans(text, [{'start': i, 'end': j}])
                        self.assertEqual(refused.exception.code, 'partial_token')
        self.assertGreater(checked, 1000)

    def test_dash_handling_matches_quotes_where_documented(self):
        # Review e6-3 (documentation): an ASCII hyphen, U+2010 or U+2011 between two word characters joins one
        # token (non-toxic, 10-20), so a cut after it is refused, which is stricter than quotes(). An en dash
        # between two numerals is a range (10–20) whose ends are separate numerals, and an en dash between two
        # words (non–toxic) is not a joiner: both are accepted, as quotes() accepts them. A dash or ± directly
        # before a numeral with no digit before it is a sign: a cut after it is refused, as in quotes().
        for text, quote, accepted in (('Use 10–20 mg daily.', '20 mg daily.', True),
                                      ('Use non–toxic paint.', 'toxic paint.', True),
                                      ('Use 10-20 mg daily.', '20 mg daily.', False),
                                      ('It is not-safe here.', 'safe here.', False),
                                      ('Low: –5 C tonight.', '5 C tonight.', False),
                                      ('Low: ±5 C tonight.', '5 C tonight.', False)):
            with self.subTest(text=text):
                source, contract = summary_case(text, [])
                start = text.index(quote)
                report = summarize(source, contract, [span(source, start, start + len(quote))])
                self.assertEqual(report['accepted'], accepted, report['issues'])

    def test_whole_word_extraction_still_accepted(self):
        report = summarize(self.source, self.contract, [self.at('The bridge is unsafe for trucks.'), self.required])
        self.assertTrue(report['accepted'], report['issues'])
        self.assertTrue(report['coverage']['complete'])
        # Punctuation, whitespace and source edges are boundaries; quotes may start or end with them.
        report = summarize(self.source, self.contract, [self.at(' unsafe for'), self.at('trucks. Inspection due 2027.')])
        self.assertTrue(report['accepted'], report['issues'])

    def test_caller_declared_boundaries_remain_authoritative(self):
        source, contract = summary_case(self.TEXT, [('odd', 'safe for trucks.')])
        start = self.TEXT.index('safe for trucks.')
        report = summarize(source, contract, [span(source, start, start + len('safe for trucks.'))])
        self.assertTrue(report['accepted'], report['issues'])


class ItemsWholeTokens(unittest.TestCase):
    """epistemic-6 for item spans without a catalog."""

    def test_uncatalogued_item_cannot_be_a_word_fragment(self):
        text = 'Alloy contains copper.'
        source = G.source_record('alloy', text)
        contract = G.list_contract('metals', source, require_nonempty=True)
        i = text.index('copper')
        report = G.verify_items(source, contract, {'contract_sha256': contract['sha256'],
                                                   'items': [{'id': 'm1', 'span': span(source, i, i + 5)}]})
        self.assertFalse(report['accepted'])
        self.assertFalse(report['returned_items_supported'])
        self.assertEqual(codes(report), ['partial_token'])
        whole = G.verify_items(source, contract, {'contract_sha256': contract['sha256'],
                                                  'items': [{'id': 'm1', 'span': span(source, i, i + 6)}]})
        self.assertTrue(whole['accepted'], whole['issues'])

    def test_uncatalogued_item_cannot_be_a_numeral_fragment(self):
        # Review e6-1: '250 000' out of '1 250 000' and '4 cup' out of '3/4 cup' were accepted after the first fix.
        for text, quote in (('Count 1 250 000 units', '250 000'), ('Mix 3/4 cup', '4 cup'),
                            ('Dose 1.5×10^3 units', '1.5')):
            with self.subTest(text=text):
                report = items_report(text, [('a', (quote,))])
                self.assertEqual(codes(report), ['partial_token'])
                self.assertFalse(report['returned_items_supported'])

    def test_hyphenated_compounds_split_only_through_a_catalog(self):
        # Review e6-2 (behaviour change, recorded in the notes): without a catalog an item cannot be one part of a
        # hyphenated compound ('lead' out of 'lead-free' inverts it). A caller catalog declaring the parts stays
        # authoritative, and the whole compound remains one item.
        text = 'Alloy is copper-nickel.'
        self.assertEqual(codes(items_report(text, [('a', ('copper',)), ('b', ('nickel',))])), ['partial_token'])
        self.assertEqual(codes(items_report('Use lead-free solder.', [('a', ('lead',))])), ['partial_token'])
        self.assertTrue(items_report(text, [('a', ('copper-nickel',))])['accepted'])
        catalog = [('a', ('copper',)), ('b', ('nickel',))]
        report = items_report(text, catalog, catalog=catalog)
        self.assertTrue(report['accepted'], report['issues'])


def items_report(text, quotes, catalog=None, require_nonempty=True):
    source = G.source_record('alloy', text)

    def witness(quote, start=None):
        start = text.index(quote) if start is None else start
        return span(source, start, start + len(quote))

    declared = None if catalog is None else [{'id': ident, 'span': witness(*quote)} for ident, quote in catalog]
    contract = G.list_contract('metals', source, catalog=declared, require_nonempty=require_nonempty)
    items = [{'id': ident, 'span': witness(*quote)} for ident, quote in quotes]
    return G.verify_items(source, contract, {'contract_sha256': contract['sha256'], 'items': items})


class ItemsOverlap(unittest.TestCase):
    """epistemic-7: one source occurrence never counts as several supported items."""

    def test_overlapping_spans_of_one_occurrence_are_refused(self):
        # Before the repair: accepted, returned_items_supported=True, count 2.
        report = items_report('Alloy contains copper.', [('m1', ('copper',)), ('m2', ('coppe',))])
        self.assertFalse(report['accepted'])
        self.assertFalse(report['returned_items_supported'])
        self.assertEqual(codes(report), ['overlap'])
        self.assertNotIn('items', report)
        nested = items_report('Alloy contains stainless steel.',
                              [('m1', ('stainless steel',)), ('m2', ('steel',))])
        self.assertEqual(codes(nested), ['overlap'])
        reordered = items_report('Alloy contains stainless steel.',
                                 [('m2', ('steel',)), ('m1', ('stainless steel',))])
        self.assertEqual(codes(reordered), ['overlap'])

    def test_distinct_occurrences_and_adjacent_items_still_count(self):
        text = 'Alloy contains copper,tin and copper.'
        report = items_report(text, [('a', ('copper',)), ('b', ('tin',)), ('c', ('copper', text.rindex('copper')))])
        self.assertTrue(report['accepted'], report['issues'])
        self.assertEqual(len(report['items']), 3)
        self.assertEqual(report['enumeration_complete'], 'unknown')

    def test_caller_declared_overlapping_catalog_remains_satisfiable(self):
        catalog = [('ss', ('stainless steel',)), ('st', ('steel',))]
        report = items_report('Alloy contains stainless steel.', catalog, catalog=catalog)
        self.assertTrue(report['accepted'], report['issues'])
        self.assertIs(report['enumeration_complete'], True)


if __name__ == '__main__':
    unittest.main()
