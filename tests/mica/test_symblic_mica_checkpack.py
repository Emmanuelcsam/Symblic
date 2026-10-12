"""Pure finite generation/provenance/literal checks; no candidate or provider."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from symblic.mica import contracts as C
from symblic.mica import checkpack as K
from symblic.mica import checkpack_cli as CLI


CHECKER = {'kind': 'test-explicit-checker', 'sha256': 'a' * 64}
SENTINEL = 'hidden-only-57bdf00e'


def request():
    return C.normalize_request({'objective': 'Preserve finite JSON values through the declared round trip.',
        'requirements': [{'id': 'roundtrip', 'text': 'Decoding an encoded value returns that exact JSON value. 😀', 'acceptance': 'TESTED'}],
        'exports': [{'name': 'encode', 'signature': 'encode(value)'}, {'name': 'decode', 'signature': 'decode(value)'}],
        'tests': [{'requirement_ids': ['roundtrip'], 'call': 'decode(encode(7))', 'expected': '7'}],
        'allowed_outputs': ['result.js'], 'budget': {'max_calls': 1, 'max_candidates': 1, 'max_workers': 1,
                                                  'retries': 0, 'wall_seconds': 120}})


def declaration(req=None):
    req = req or request()
    base = {'kind': 'round_trip', 'origin': 'caller_supplied', 'requirements': [K.requirement_binding(req, 'roundtrip')],
            'encoder': req['exports'][0], 'decoder': req['exports'][1]}
    return {'version': 1, 'seed': 19, 'evaluation': {'id': 'roundtrip', 'family': 'json-identity', 'split': 'heldout'},
            'checks': [{**base, 'id': 'visible', 'visibility': 'public', 'inputs_json': [
                '{"__proto__":{"polluted":true},"constructor":"data","array":[1,"1",true,null]}',
                '1.25', '"😀"']},
                {**base, 'id': 'heldout', 'visibility': 'hidden', 'inputs_json': [json.dumps(SENTINEL)]},
                {**base, 'id': 'suggested', 'origin': 'model_proposed', 'visibility': 'public',
                 'inputs_json': ['"model-proposed-only-sentinel"']}]}


class CheckPackTest(unittest.TestCase):
    def test_frozen_public_prefix_hidden_partition_proposals_and_replay(self):
        req, dec = request(), declaration()
        with mock.patch('subprocess.Popen', side_effect=AssertionError('no process')), \
             mock.patch('socket.socket', side_effect=AssertionError('no network')):
            pack = K.freeze(req, dec, CHECKER)
            self.assertEqual(pack, K.freeze(req, dec, CHECKER))
            self.assertEqual(K.validate(pack), pack)
            public = K.public_request(pack)
        self.assertEqual(public['tests'][:len(req['tests'])], req['tests'])
        self.assertEqual(public['requirements'], req['requirements'])
        self.assertEqual(public['budget'], req['budget'])
        self.assertNotIn(SENTINEL, json.dumps(public))
        self.assertNotIn('model-proposed-only-sentinel', json.dumps(public))
        fixture = K.fixture(pack)
        self.assertEqual(fixture['split'], 'heldout')
        self.assertEqual(fixture['request'], public)
        self.assertIn(SENTINEL, json.dumps(fixture['hidden_tests']))
        self.assertEqual(pack['counts'], {'original_public': 1, 'generated_public': 3, 'hidden': 1, 'proposals': 1})
        self.assertEqual(pack['semantic_completeness'], 'unassessed')

    def test_unicode_source_witness_original_text_and_signature_are_exact(self):
        req, dec = request(), declaration()
        binding = dec['checks'][0]['requirements'][0]
        self.assertEqual(binding['span']['end'], len(req['requirements'][0]['text']))
        for mutate in (lambda d: d['checks'][0]['requirements'][0].update(text='Different meaning'),
                       lambda d: d['checks'][0]['requirements'][0]['span'].update(end=binding['span']['end'] - 1),
                       lambda d: d['checks'][0]['requirements'][0]['span'].update(revision=2),
                       lambda d: d['checks'][0]['encoder'].update(signature='encode(other)'),
                       lambda d: d['checks'][0]['requirements'][0].update(id='missing')):
            changed = copy.deepcopy(dec); mutate(changed)
            with self.assertRaises(ValueError):
                K.freeze(req, changed, CHECKER)

    def test_json_lowering_preserves_proto_and_numeric_string_distinctions(self):
        dec = declaration(); row = dec['checks'][0]
        row.update(kind='case', function=row.pop('encoder'), arguments_json='[{"__proto__":1,"n":1,"s":"1","b":true}]',
                   expected_json='{"__proto__":1,"n":1,"s":"1","b":true}')
        row.pop('decoder'); row.pop('inputs_json')
        pack = K.freeze(request(), dec, CHECKER)
        call = next(r['call'] for r in pack['checks'] if r['declaration_id'] == 'visible')
        self.assertIn('["__proto__"]:1', call)
        self.assertIn('["n"]:1', call)
        self.assertIn('["s"]:"1"', call)
        self.assertIn('["b"]:true', call)
        self.assertNotIn('JSON.parse', call); self.assertNotIn('JSON.stringify', call)

    def test_unsafe_or_ambiguous_json_is_refused_not_coerced(self):
        for literal in ('9007199254740992', '1e400', '1e-400', '-0', '-0.0', 'NaN',
                        '{"x":1,"x":2}', '"\\ud800"', '1.234567890123456789', '(1+2)'):
            with self.subTest(literal=literal):
                dec = declaration(); dec['checks'][0]['inputs_json'] = [literal]
                with self.assertRaises(ValueError):
                    K.freeze(request(), dec, CHECKER)

    def test_overflow_duplicate_and_unary_limits_are_not_silently_truncated(self):
        for change in (lambda d: d['checks'][0].update(inputs_json=[str(i) for i in range(257)]),
                       lambda d: d['checks'][0].update(inputs_json=['1', '1']),
                       lambda d: d['checks'][0].update(inputs_json=['"' + 'x' * 12000 + '"']),
                       lambda d: d['checks'][0]['decoder'].update(signature='decode(a,b)')):
            dec = declaration(); change(dec)
            with self.assertRaises(ValueError):
                K.freeze(request(), dec, CHECKER)
        req = request(); req['tests'] = req['tests'] * 254
        with self.assertRaises(K.CheckPackError):
            K.freeze(req, declaration(req), CHECKER)

    def test_complete_regeneration_checker_seed_and_split_pins(self):
        pack = K.freeze(request(), declaration(), CHECKER)
        for change in (lambda p: p['checks'][0].update(expected='"copied candidate result"'),
                       lambda p: p['public_request']['tests'].pop(0)):
            changed = copy.deepcopy(pack); change(changed)
            changed['sha256'] = K._hash({k: v for k, v in changed.items() if k != 'sha256'})
            with self.assertRaises(K.CheckPackError):
                K.validate(changed)
        changed = copy.deepcopy(pack); changed['declaration']['evaluation']['split'] = 'dev'
        changed['sha256'] = K._hash({k: v for k, v in changed.items() if k != 'sha256'})
        with self.assertRaises(K.CheckPackError):
            K.validate(changed, expected_sha256=pack['sha256'])
        with self.assertRaises(K.CheckPackError):
            K.validate(pack, current_checker={'kind': 'different'})
        dec = declaration(); dec['seed'] += 1
        self.assertNotEqual(pack['sha256'], K.freeze(request(), dec, CHECKER)['sha256'])

    def test_proposed_checks_never_gain_authority_or_fabricate_hidden_fixture(self):
        dec = declaration()
        for row in dec['checks']:
            row['origin'] = 'model_proposed'
        pack = K.freeze(request(), dec, CHECKER)
        self.assertEqual(K.public_request(pack), request())
        with self.assertRaises(K.CheckPackError):
            K.fixture(pack)

    def test_cli_agent_json_capture_and_public_no_hidden_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in [('request', request()), ('declaration', declaration())]:
                (root / (name + '.json')).write_text(json.dumps(value))
            def run(args):
                out = io.StringIO()
                code = CLI.main(args, out=out, checker_factory=lambda: CHECKER)
                return code, json.loads(out.getvalue())
            code, pack = run(['freeze', str(root/'request.json'), '--declaration', str(root/'declaration.json')])
            self.assertEqual(code, 0, pack)
            (root/'pack.json').write_text(json.dumps(pack))
            code, public = run(['public', str(root/'pack.json'), '--freeze', pack['sha256']])
            self.assertEqual(code, 0, public); self.assertNotIn(SENTINEL, json.dumps(public))
            code, fixture = run(['fixture', str(root/'pack.json'), '--freeze', pack['sha256']])
            self.assertEqual(code, 0, fixture); self.assertIn(SENTINEL, json.dumps(fixture))
            with mock.patch.object(CLI, '_checker', side_effect=AssertionError('inert help')):
                code, help_result = run(['--help'])
                self.assertEqual(code, 0)
                self.assertEqual(set(help_result['declaration_schema']['required']), {'version', 'seed', 'evaluation', 'checks'})


if __name__ == '__main__':
    unittest.main()
