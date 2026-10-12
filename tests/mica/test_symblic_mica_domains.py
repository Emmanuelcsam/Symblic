"""Bounded data expansion only: no models, candidate execution or private stores."""
import copy
from decimal import localcontext, Inexact, Rounded
import json
import unittest
from unittest import mock

from symblic.mica import checkpack as K
from symblic.mica import domains as D


CHECKER = {'kind': 'declared-test-checker', 'sha256': 'a' * 64}
SENTINEL = 'hidden-domain-7103'


def request():
    return K.C.normalize_request({'objective': 'Preserve each JSON value through the declared encode/decode round trip.',
        'requirements': [{'id': 'roundtrip', 'text': 'Decoding an encoded finite JSON value returns that same JSON value.', 'acceptance': 'TESTED'}],
        'exports': [{'name': 'encode', 'signature': 'encode(value)'}, {'name': 'decode', 'signature': 'decode(value)'}],
        'tests': [{'requirement_ids': ['roundtrip'], 'call': 'decode(encode(7))', 'expected': '7'}],
        'allowed_outputs': ['result.js'], 'budget': {'max_calls': 2, 'max_candidates': 1, 'max_workers': 1,
                                                  'retries': 1, 'context_chars': 24000, 'wall_seconds': 120}})


def declaration(req=None):
    req = req or request()
    common = {'kind': 'round_trip_domain', 'origin': 'caller_supplied',
              'requirements': [K.requirement_binding(req, 'roundtrip')],
              'encoder': req['exports'][0], 'decoder': req['exports'][1]}
    return {'version': 1, 'seed': 19, 'evaluation': {'id': 'domain-trip', 'family': 'finite-domain-trip', 'split': 'heldout'},
        'checks': [{**copy.deepcopy(common), 'id': 'small-arrays', 'visibility': 'public',
                    'domain': {'kind': 'array', 'elements': {'kind': 'integer_range', 'min': -1, 'max': 1, 'step': 1},
                               'lengths': [0, 1, 2, 3]}},
                   {**copy.deepcopy(common), 'id': 'secret', 'visibility': 'hidden',
                    'domain': {'kind': 'enum', 'values_json': [json.dumps(SENTINEL)]}}]}


class DomainTests(unittest.TestCase):
    def test_all_forty_arrays_and_exact_preflight_metrics(self):
        domain = declaration()['checks'][0]['domain']
        result = D.expand_domain(domain)
        self.assertEqual(result, D.expand_domain(domain))
        self.assertEqual(result['cardinality'], 40)
        self.assertEqual(result['values_json'][:4], ['[]', '[-1]', '[0]', '[1]'])
        self.assertEqual(result['values_json'][-1], '[1,1,1]')
        self.assertEqual(len(set(result['values_json'])), 40)
        self.assertEqual(result['total_utf8_bytes'], sum(len(x.encode()) for x in result['values_json']))
        self.assertEqual(result['max_value_depth'], 1)
        self.assertEqual(result['values_sha256'], K._hash(result['values_json']))

    def test_semantic_duplicates_refused_without_ambient_arithmetic(self):
        duplicates = [['1', '1.0'], ['1e1', '10.00'], ['"a"', '"\\u0061"'],
                      ['{"a":1,"b":true}', '{"b":true,"a":1.0}'], ['[]', '[ ]']]
        with localcontext() as ctx:
            ctx.prec = 1; ctx.traps[Inexact] = True; ctx.traps[Rounded] = True
            for values in duplicates:
                with self.subTest(values=values), self.assertRaises(K.CheckPackError) as caught:
                    D.expand_domain({'kind': 'enum', 'values_json': values})
                self.assertEqual(caught.exception.code, 'domain_duplicate')
            result = D.expand_domain({'kind': 'enum', 'values_json': ['1', 'true', '"1"', 'null', '12']})
            self.assertEqual(result['cardinality'], 5)

    def test_all_overflow_and_invalid_domains_refuse_before_products(self):
        large = {'kind': 'array', 'elements': {'kind': 'integer_range', 'min': 0, 'max': 99, 'step': 1}, 'lengths': [3]}
        byte_domain = {'kind': 'array', 'elements': {'kind': 'enum', 'values_json': ['"é"']}, 'lengths': [2]}
        deep = {'kind': 'enum', 'values_json': ['[' * 16 + '0' + ']' * 16]}
        tests = [(large, {}), (byte_domain, {'max_bytes': 5}),
                 ({'kind': 'array', 'elements': deep, 'lengths': [1]}, {}),
                 ({'kind': 'enum', 'values_json': []}, {}),
                 ({'kind': 'integer_range', 'min': 0, 'max': 1, 'step': 0}, {}),
                 ({'kind': 'integer_range', 'min': False, 'max': 1, 'step': 1}, {}),
                 ({'kind': 'integer_range', 'min': 0, 'max': 2**53, 'step': 1}, {}),
                 ({'kind': 'array', 'elements': {'kind': 'enum', 'values_json': ['0']}, 'lengths': [0, 0]}, {})]
        with mock.patch.object(D, '_materialize', side_effect=AssertionError('no product allocation')):
            for domain, limits in tests:
                with self.subTest(domain=domain, limits=limits), self.assertRaises(K.CheckPackError):
                    D.expand_domain(domain, **limits)

    def test_pack_source_recipe_counts_list_hash_and_original_prefix(self):
        req, dec = request(), declaration()
        pack = K.freeze(req, dec, CHECKER)
        self.assertEqual(K.validate(pack), pack)
        self.assertEqual(pack, K.freeze(req, dec, CHECKER))
        self.assertEqual(pack['public_request']['tests'][:1], req['tests'])
        self.assertEqual(pack['public_request']['requirements'], req['requirements'])
        self.assertIn('symblic/mica/domains.py', pack['implementation']['sources'])
        self.assertEqual(pack['finite_domains'][0]['recipe'], dec['checks'][0]['domain'])
        self.assertEqual(pack['finite_domains'][0]['cardinality'], 40)
        self.assertEqual(pack['counts']['generated_public'], 40)
        self.assertNotIn(SENTINEL, json.dumps(K.public_request(pack)))
        self.assertIn(SENTINEL, json.dumps(K.fixture(pack)['hidden_tests']))
        for change in (lambda p: p['finite_domains'][0].update(cardinality=39),
                       lambda p: p['finite_domains'][0].update(values_sha256='b' * 64),
                       lambda p: p['finite_domains'][0]['recipe'].update(lengths=[0]),
                       lambda p: p['checks'][0].update(expected='"invented"')):
            mutated = copy.deepcopy(pack); change(mutated)
            mutated['sha256'] = K._hash({k: v for k, v in mutated.items() if k != 'sha256'})
            with self.assertRaises(K.CheckPackError):
                K.validate(mutated)

    def test_remaining_public_allowance_and_semantic_duplicate_rows_preflight(self):
        req = request(); req['tests'] *= 218
        with mock.patch.object(D, '_materialize', side_effect=AssertionError('no product allocation')):
            with self.assertRaises(K.CheckPackError):
                K.freeze(req, declaration(req), CHECKER)
        dec = declaration(); extra = copy.deepcopy(dec['checks'][0]); extra.update(id='again')
        extra['domain'] = {'kind': 'enum', 'values_json': ['[0.0]']}
        dec['checks'].append(extra)
        with self.assertRaises(K.CheckPackError) as caught:
            K.freeze(request(), dec, CHECKER)
        self.assertEqual(caught.exception.code, 'domain_duplicate')

    def test_hidden_semantic_equivalent_and_changed_helper_identity_refused(self):
        dec = declaration()
        dec['checks'][1]['domain']['values_json'] = ['[0.00]']
        with self.assertRaises(K.CheckPackError) as caught:
            K.freeze(request(), dec, CHECKER)
        self.assertEqual(caught.exception.code, 'exposure')
        pack = K.freeze(request(), declaration(), CHECKER)
        with mock.patch.object(D, '_symblic_import_identity', {**D._symblic_import_identity, 'sha256': 'b' * 64}):
            with self.assertRaises(K.CheckPackError) as caught:
                K.validate(pack)
            self.assertEqual(caught.exception.code, 'identity')

    def test_proposed_domains_and_unknown_authority_never_become_acceptance(self):
        dec = declaration()
        for row in dec['checks']:
            row['origin'] = 'model_proposed'
        pack = K.freeze(request(), dec, CHECKER)
        self.assertEqual(K.public_request(pack), request())
        self.assertEqual(pack['counts']['proposals'], 41)
        with self.assertRaises(K.CheckPackError):
            K.fixture(pack)
        for mutate in (lambda d: d['checks'][0]['requirements'][0].update(text='new authority'),
                       lambda d: d['checks'][0]['encoder'].update(signature='encode(other)'),
                       lambda d: d['checks'][0]['domain'].update(extra='arbitrary')):
            dec = declaration(); mutate(dec)
            with self.assertRaises(ValueError):
                K.freeze(request(), dec, CHECKER)

    def test_plain_legacy_pack_has_no_domain_dependency_or_new_body_field(self):
        req = request(); dec = declaration()
        for row in dec['checks']:
            row['kind'] = 'round_trip'
            row['inputs_json'] = ['"public"'] if row['visibility'] == 'public' else ['"hidden"']
            row.pop('domain')
        with mock.patch.object(D, 'expand_domain', side_effect=AssertionError('legacy must not enumerate')):
            pack = K.freeze(req, dec, CHECKER)
            self.assertEqual(K.validate(pack), pack)
        self.assertNotIn('finite_domains', pack)
        self.assertNotIn('symblic/mica/domains.py', pack['implementation']['sources'])


if __name__ == '__main__':
    unittest.main()
