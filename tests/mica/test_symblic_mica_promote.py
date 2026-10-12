"""MICA Stage IV promotion: fake providers, private stores, real sandboxed JS checks.

No agent, model, remote machine, cloud API, network or live store. The fixture copies the
increment request and FakeApps provider boundary from test_symblic_mica_execution;
every run, pack, component library and receipt lives under a private temp folder.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from unittest import mock

from symblic.graph import run as G
from symblic.js import check as JS
from symblic.mica import search as M
from symblic.mica import checkpack as K
from symblic.mica import contracts as C
from symblic.mica import library as L
from symblic.mica import promote as P


CHECKER = {'kind': 'test-explicit-checker', 'sha256': 'a' * 64}
BAD = 'function inc(x) { return 0; }'
SENTINEL = 'hidden-only-promotion-6c1d'
DOMAIN = [x for x in range(-10, 11) if x != 2]  # every integer in [-10, 10] beyond the public example


def inventory(nodes=('node-a',)):
    return [{'engine': 'ollama', 'model': 'fixture-small', 'node': node, 'digest': None,
             'ready': True, 'available': True, 'context_chars': 65536, 'estimated_cost_units': 1}
            for node in nodes]


def request(**budget):
    return {'version': 1, 'language': 'javascript', 'objective': 'Implement public integer increment.',
            'requirements': [{'id': 'increment', 'text': 'Return the input integer plus one.', 'acceptance': 'TESTED'}],
            'exports': [{'name': 'inc', 'signature': 'inc(x)'}],
            'tests': [{'requirement_ids': ['increment'], 'call': 'inc(2)', 'expected': '3'}],
            'allowed_outputs': ['result.js'], 'assumptions': ['Inputs are integers.'],
            'budget': {'max_calls': 8, 'max_candidates': 2, 'max_units': 8, 'max_workers': 3,
                       'retries': 0, 'context_chars': 24000, 'wall_seconds': 60, **budget}}


class FakeApps:
    """Fake only the provider boundary, retaining complete received prompts."""
    def __init__(self, callback=None, delay=0):
        self.callback = callback or (lambda req, number: 'function inc(x) { return x + 1; }')
        self.delay = delay
        self.requests = []
        self.lock = threading.Lock()
        self.active_by_node = {}
        self.max_active_by_node = {}

    def call(self, req):
        with self.lock:
            self.requests.append({k: copy.deepcopy(v) for k, v in req.items() if k != 'stop'})
            number = len(self.requests)
            node = req['app']['node']
            self.active_by_node[node] = self.active_by_node.get(node, 0) + 1
            self.max_active_by_node[node] = max(self.max_active_by_node.get(node, 0), self.active_by_node[node])
        try:
            if self.delay:
                time.sleep(self.delay)
            output = self.callback(req, number)
            if isinstance(output, BaseException):
                raise output
            if type(output) is dict and 'ok' in output:
                return output
            language = 'json' if 'output_format' in req['prompt'] else 'js'
            return {'ok': True, 'text': output if req.get('schema') is not None else '```' + language + '\n' + output + '\n```',
                    'model': req['app']['model'], 'node': node, 'ms': 1}
        finally:
            with self.lock:
                self.active_by_node[node] -= 1


def declaration(req, *, extra_public=(), extra_hidden=()):
    """Public row restating the original test, an enumerated finite hidden domain, one model proposal."""
    binding = [K.requirement_binding(req, 'increment')]
    def case(ident, visibility, arguments, expected, origin='caller_supplied'):
        return {'id': ident, 'kind': 'case', 'origin': origin, 'visibility': visibility, 'requirements': binding,
                'function': req['exports'][0], 'arguments_json': arguments, 'expected_json': expected}
    checks = [case('restated', 'public', '[2]', '3')]
    checks += [case('domain%d' % i, 'hidden', '[%d]' % x, str(x + 1)) for i, x in enumerate(DOMAIN)]
    checks += [case('wrongpublic%d' % i, 'public', a, e) for i, (a, e) in enumerate(extra_public)]
    checks += [case('extra%d' % i, 'hidden', a, e) for i, (a, e) in enumerate(extra_hidden)]
    # A wrong model proposal: proposals never become acceptance checks.
    checks.append(case('suggested', 'public', '[100]', '"model-only"', origin='model_proposed'))
    return {'version': 1, 'seed': 11, 'evaluation': {'id': 'increment', 'family': 'integer-increment', 'split': 'heldout'},
            'checks': checks}


ROUNDTRIP = 'function encode(value) { return JSON.stringify(value); }\nfunction decode(value) { return JSON.parse(value); }'


def roundtrip_request():
    return {'version': 1, 'language': 'javascript', 'objective': 'Preserve finite JSON values through encode then decode.',
            'requirements': [{'id': 'roundtrip', 'text': 'Decoding an encoded value returns that exact JSON value.',
                              'acceptance': 'TESTED'}],
            'exports': [{'name': 'encode', 'signature': 'encode(value)'}, {'name': 'decode', 'signature': 'decode(value)'}],
            'tests': [{'requirement_ids': ['roundtrip'], 'call': 'decode(encode(7))', 'expected': '7'}],
            'allowed_outputs': ['result.js'], 'assumptions': [],
            'budget': {'max_calls': 8, 'max_candidates': 2, 'max_units': 8, 'max_workers': 3,
                       'retries': 0, 'context_chars': 24000, 'wall_seconds': 60}}


def roundtrip_declaration(req):
    """One public round trip and an exhaustive hidden domain: every array of length 0..2 over -2..2 (31 values)."""
    base = {'origin': 'caller_supplied', 'requirements': [K.requirement_binding(req, 'roundtrip')],
            'encoder': req['exports'][0], 'decoder': req['exports'][1]}
    return {'version': 1, 'seed': 5, 'evaluation': {'id': 'roundtrip', 'family': 'json-arrays', 'split': 'heldout'},
            'checks': [{**base, 'id': 'visible', 'kind': 'round_trip', 'visibility': 'public', 'inputs_json': ['[7,8,9]']},
                       {**base, 'id': 'arrays', 'kind': 'round_trip_domain', 'visibility': 'hidden',
                        'domain': {'kind': 'array', 'lengths': [0, 1, 2],
                                   'elements': {'kind': 'integer_range', 'min': -2, 'max': 2, 'step': 1}}}]}


def receipt_name(receipt):
    return '%s-%s.json' % (receipt['run_id'], receipt['pack_sha256'][:16])


@unittest.skipUnless(JS.available(), 'sandboxed Node unavailable')
class PromotionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory(prefix='mica-promote-fixture-')
        cls.root = Path(cls._temp.name)
        cls.apps = FakeApps()
        cls.run_dir = cls.root / 'run'
        cls.result = M.MicaRun(request(), cls.run_dir, cls.apps, inventory()).execute(mode='direct')
        cls.req = C.normalize_request(request())
        cls.pack = K.freeze(cls.req, declaration(cls.req), CHECKER)

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def setUp(self):
        self.assertEqual(self.result['status'], 'done', self.result)
        self.assertEqual(len(self.apps.requests), 1)
        temp = tempfile.TemporaryDirectory(prefix='mica-promote-case-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.library = self.base / 'library'

    def promote(self, run_dir=None, pack=None, **kwargs):
        pack = pack or self.pack
        kwargs.setdefault('pack_sha256', pack['sha256'])
        return P.promote(run_dir or self.run_dir, pack=pack, library_root=self.library, **kwargs)

    @staticmethod
    def snapshot(path):
        if not path.exists():
            return None
        return {str(p.relative_to(path)): (p.read_bytes() if p.is_file() else 'dir') for p in sorted(path.rglob('*'))}

    def fresh_run(self, name, req=None, apps=None):
        folder = self.base / name
        result = M.MicaRun(req or request(), folder, apps or FakeApps(), inventory()).execute(mode='direct')
        self.assertEqual(result['status'], 'done', result)
        return folder, result

    def test_passing_frozen_pack_publishes_components_and_repeat_is_idempotent(self):
        with mock.patch.object(JS, 'failures', wraps=JS.failures) as checker:
            first = self.promote()
            self.assertEqual(first['status'], 'promoted', first)
            self.assertEqual((first['existing'], first['checked']), (False, True))
            executed = [case for call in checker.call_args_list for case in call.args[1]]
            self.assertEqual(len(executed), 22)
            self.assertIn(['inc(2)', '3'], executed)
            self.assertIn(['inc(...[2])', '3'], executed)
            self.assertIn(['inc(...[-10])', '-9'], executed)
            self.assertNotIn('inc(...[100])', json.dumps(executed))  # proposal excluded
            for call in checker.call_args_list:
                self.assertEqual(call.args[0], self.result['output']['text'])
                self.assertIs(type(call.kwargs['deadline']), float)
            before = self.snapshot(self.library)
            second = self.promote()
            self.assertEqual(checker.call_count, 1)  # the identical repeat reruns no checks
        receipt = first['receipt']
        self.assertEqual(second['status'], 'promoted', second)
        self.assertEqual((second['existing'], second['checked'], second['receipt']), (True, False, receipt))
        self.assertEqual(self.snapshot(self.library), before)
        manifest = json.loads((self.run_dir / 'mica-manifest.json').read_text())
        sealed = json.loads((self.run_dir / 'mica-result.json').read_text())
        self.assertEqual(receipt['run_id'], manifest['run_id'])
        self.assertEqual(receipt['result_sha256'], sealed['sha256'])
        self.assertEqual(receipt['pack_sha256'], self.pack['sha256'])
        self.assertEqual(receipt['cases'], {'public': 2, 'hidden': 20, 'total': 22})
        self.assertIsNone(receipt['finite_domains'])
        self.assertEqual(receipt['request_binding'], 'original_request')
        self.assertEqual(receipt['assurance'], 'TESTED_ON_FROZEN_FINITE_PACK')
        self.assertEqual(receipt['scope'], 'finite checks only: not a proof of general correctness')
        runtime = M.implementation_identity()
        self.assertEqual(receipt['runtime'], runtime)
        self.assertEqual(first['proposals_excluded'], 1)
        # The key is the one any later direct construction of this contract derives.
        view = M.MicaRun(request(), self.base / 'never-executed', FakeApps(), [])
        plan = M.direct_plan(self.req)
        spec = view._sheet_plan(plan)
        contract = view._component_contract_hash(plan['contracts'][0], spec['units'][0]['contract_sha256'])
        key = L.identity(contract, [], runtime)
        self.assertEqual([(c['key'], c['contract_sha256']) for c in receipt['components']], [(key, contract)])
        tokens = L.ComponentLibrary(self.library).candidates(key, runtime=runtime)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]['code'], self.result['output']['text'])
        self.assertEqual(tokens[0]['code_sha256'], receipt['components'][0]['code_sha256'])
        self.assertEqual(tokens[0]['assurance'], 'TESTED')
        path = self.library / 'promotions' / receipt_name(receipt)
        self.assertEqual(Path(first['receipt_file']), path)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(G._unseal(json.loads(path.read_text())), receipt)
        self.assertEqual(P.promotions(self.library), [receipt])

    def test_failing_hidden_or_public_case_refuses_and_writes_nothing(self):
        failing = K.freeze(self.req, declaration(self.req, extra_hidden=[
            ('[%s]' % json.dumps(SENTINEL), json.dumps(SENTINEL))]), CHECKER)
        report = self.promote(pack=failing)
        self.assertEqual((report['status'], report['code']), ('refused', 'checks_failed'), report)
        self.assertEqual([(row['id'], row['visibility']) for row in report['failed']], [('extra0/0', 'hidden')])
        self.assertNotIn(SENTINEL, json.dumps(report))  # hidden rows are reported by ID only
        self.assertEqual(report['cases'], {'public': 2, 'hidden': 21, 'total': 22 + 1})
        self.assertFalse(self.library.exists())
        wrong = K.freeze(self.req, declaration(self.req, extra_public=[('[11]', '13')]), CHECKER)
        visible = self.promote(pack=wrong)
        self.assertEqual(visible['code'], 'checks_failed', visible)
        self.assertEqual(visible['failed'], [{'id': 'wrongpublic0/0', 'visibility': 'public', 'call': 'inc(...[11])',
                                              'expected': '13', 'observed': visible['failed'][0]['observed']}])
        self.assertIn('12', visible['failed'][0]['observed'])
        self.assertFalse(self.library.exists())
        # A populated library and its receipts are left byte-for-byte unchanged by a refusal.
        self.assertEqual(self.promote()['status'], 'promoted')
        before = self.snapshot(self.library)
        again = self.promote(pack=failing)
        self.assertEqual(again['code'], 'checks_failed', again)
        self.assertEqual(self.snapshot(self.library), before)
        self.assertEqual([r['pack_sha256'] for r in P.promotions(self.library)], [self.pack['sha256']])

    def test_rows_beyond_one_checker_batch_share_one_deadline_and_keep_ids(self):
        failing = K.freeze(self.req, declaration(self.req, extra_public=[('[11]', '13')],
                                                 extra_hidden=[('[12]', '0')]), CHECKER)
        with mock.patch.object(JS, 'MAX_CASES', 7), mock.patch.object(JS, 'failures', wraps=JS.failures) as checker:
            report = self.promote(pack=failing)
        self.assertEqual(report['code'], 'checks_failed', report)
        self.assertEqual(report['cases'], {'public': 3, 'hidden': 21, 'total': 24})
        self.assertEqual(sorted((row['id'], row['visibility']) for row in report['failed']),
                         [('extra0/0', 'hidden'), ('wrongpublic0/0', 'public')])
        self.assertEqual(checker.call_count, 4)  # 24 rows in batches of at most 7
        self.assertTrue(all(len(call.args[1]) <= 7 for call in checker.call_args_list))
        self.assertEqual(len({call.kwargs['deadline'] for call in checker.call_args_list}), 1)
        self.assertFalse(self.library.exists())

    def test_concurrent_identical_promotions_write_one_receipt(self):
        reports, errors = [], []
        def worker():
            try:
                reports.append(self.promote())
            except BaseException as exc:  # surfaced below; a thread must not swallow it
                errors.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(120)
        self.assertEqual(errors, [])
        self.assertEqual([r['status'] for r in reports], ['promoted', 'promoted'], reports)
        self.assertEqual(sorted(r['existing'] for r in reports), [False, True])
        self.assertEqual(reports[0]['receipt'], reports[1]['receipt'])
        self.assertEqual(sorted(p.name for p in (self.library / 'promotions').iterdir() if not p.name.startswith('.')),
                         [receipt_name(reports[0]['receipt'])])

    def test_pack_pin_and_regenerated_content_drift_are_refused(self):
        drift = self.promote(pack_sha256='f' * 64)
        self.assertEqual((drift['status'], drift['code'], drift['cause']), ('refused', 'pack', 'pin'), drift)
        changed = copy.deepcopy(self.pack)
        next(r for r in changed['checks'] if r['visibility'] == 'hidden')['expected'] = '"copied candidate result"'
        changed['sha256'] = K._hash({k: v for k, v in changed.items() if k != 'sha256'})
        resealed = self.promote(pack=changed)
        self.assertEqual((resealed['status'], resealed['code'], resealed['cause']), ('refused', 'pack', 'pin'), resealed)
        self.assertEqual(self.promote(pack_sha256='F' * 64)['code'], 'arguments')
        self.assertFalse(self.library.exists())

    def test_tampered_result_or_component_token_is_refused(self):
        run_dir, _ = self.fresh_run('tampered')
        path = run_dir / 'mica-result.json'
        raw = path.read_bytes()
        body = {k: v for k, v in json.loads(raw).items() if k != 'sha256'}
        text = body['output']['text'].replace('x + 1', 'x + 2')
        body['output'] = {**body['output'], 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
        for label, tampered in (('unsealed edit', raw.replace(b'x + 1', b'x + 2')),
                                ('resealed detached output', json.dumps(G._seal(body)).encode())):
            with self.subTest(label):
                path.write_bytes(tampered)
                report = self.promote(run_dir)
                self.assertEqual((report['status'], report['code']), ('refused', 'run_evidence'), report)
        path.write_bytes(raw)
        token_path = next((run_dir / 'components').glob('*.json'))
        token_raw = token_path.read_bytes()
        token = {k: v for k, v in json.loads(token_raw).items() if k != 'sha256'}
        token_path.write_text(json.dumps(G._seal({**token, 'code': BAD})))
        report = self.promote(run_dir)
        self.assertEqual((report['status'], report['code']), ('refused', 'run_evidence'), report)
        self.assertFalse(self.library.exists())
        token_path.write_bytes(token_raw)
        self.assertEqual(self.promote(run_dir)['status'], 'promoted')

    def test_promoted_component_is_reused_by_later_construction_with_zero_calls(self):
        control = FakeApps(lambda req, n: 'function inc(x) { return x + 1; }')
        unpromoted = M.MicaRun(request(), self.base / 'control', control, inventory(),
                               library=self.base / 'empty-library').execute(mode='direct')
        self.assertEqual((unpromoted['status'], len(control.requests)), ('done', 1), unpromoted)
        self.assertEqual(self.promote()['status'], 'promoted')
        apps = FakeApps(lambda req, n: BAD)
        later = M.MicaRun(request(), self.base / 'later', apps, inventory(), library=self.library).execute(mode='direct')
        self.assertEqual(later['status'], 'done', later)
        self.assertEqual(len(apps.requests), 0)
        self.assertEqual((later['calls'], later['calls_reserved_or_spent']), (0, 0))
        self.assertTrue(later['attempts'][0]['decisions'][0]['reused'])
        self.assertEqual(later['output']['text'], self.result['output']['text'])

    def test_listing_ignores_symlink_malformed_and_foreign_entries(self):
        receipt = self.promote()['receipt']
        folder = self.library / 'promotions'
        real = folder / receipt_name(receipt)
        (folder / ('a' * 32 + '-' + 'b' * 16 + '.json')).symlink_to(real)
        (folder / ('c' * 32 + '-' + 'd' * 16 + '.json')).write_text('{"version": 1,')
        (folder / ('e' * 32 + '-' + 'f' * 16 + '.json')).write_bytes(real.read_bytes())  # sealed, named for another run
        (folder / 'notes.txt').write_text('not a receipt')
        self.assertEqual(P.promotions(self.library), [receipt])
        out = io.StringIO()
        self.assertEqual(P.main(['list', '--library', str(self.library)], out=out), 0)
        listed = json.loads(out.getvalue())
        self.assertEqual(listed['receipts'], [receipt])
        self.assertEqual(sorted(row['reason'] for row in listed['ignored']),
                         ['symlink', 'unrecognized_name', 'unverified', 'unverified'])
        self.assertEqual(P.promotions(self.base / 'missing-library'), [])
        moved = self.base / 'moved'
        folder.rename(moved)
        folder.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            P.promotions(self.library)

    def test_existing_receipt_for_another_result_or_pack_is_refused_unchanged(self):
        receipt = self.promote()['receipt']
        path = self.library / 'promotions' / receipt_name(receipt)
        original = path.read_bytes()
        body = {k: v for k, v in receipt.items() if k != 'sha256'}
        altered = json.loads(original); altered['cases']['hidden'] = 21
        variants = (('another result', G._json(G._seal({**body, 'result_sha256': '0' * 64}))),
                    ('another pack', G._json(G._seal({**body, 'pack_sha256': receipt['pack_sha256'][:16] + '0' * 48}))),
                    ('unsealed edit', json.dumps(altered).encode()))
        for label, raw in variants:
            with self.subTest(label):
                path.write_bytes(raw)
                before = self.snapshot(self.library)
                report = self.promote()
                self.assertEqual((report['status'], report['code']), ('refused', 'receipt_conflict'), report)
                self.assertEqual(self.snapshot(self.library), before)
        path.write_bytes(original)
        self.assertTrue(self.promote()['existing'])

    def test_pack_for_another_signature_or_request_is_refused_precisely(self):
        other = request(); other['exports'] = [{'name': 'inc', 'signature': 'inc(value)'}]
        other = C.normalize_request(other)
        report = self.promote(pack=K.freeze(other, declaration(other), CHECKER))
        self.assertEqual((report['status'], report['code']), ('refused', 'signature'), report)
        self.assertIn('inc(value)', report['error'])
        self.assertIn('inc(x)', report['error'])
        changed = request(); changed['requirements'][0]['text'] = 'Return the input integer plus one, exactly.'
        changed = C.normalize_request(changed)
        report = self.promote(pack=K.freeze(changed, declaration(changed), CHECKER))
        self.assertEqual((report['status'], report['code']), ('refused', 'request_binding'), report)
        self.assertIn('requirements', report['error'])
        self.assertFalse(self.library.exists())

    def test_runtime_drift_failed_and_incomplete_runs_are_refused(self):
        drift = self.promote(runtime={**M.implementation_identity(), 'kernel': 'other-kernel'})
        self.assertEqual((drift['status'], drift['code']), ('refused', 'runtime'), drift)
        failed_dir = self.base / 'failed'
        failed = M.MicaRun(request(), failed_dir, FakeApps(lambda req, n: BAD), inventory()).execute(mode='direct')
        self.assertNotEqual(failed['status'], 'done', failed)
        self.assertTrue((failed_dir / 'mica-result.json').exists())
        report = self.promote(failed_dir)
        self.assertEqual((report['status'], report['code']), ('refused', 'not_done'), report)
        planned_dir = self.base / 'planned'
        planned = M.MicaRun(request(), planned_dir, FakeApps(), inventory()).plan(mode='direct')
        self.assertEqual(planned['status'], 'planned', planned)
        report = self.promote(planned_dir)
        self.assertEqual((report['status'], report['code']), ('refused', 'not_done'), report)
        self.assertFalse(self.library.exists())

    def test_inconclusive_checker_is_not_a_verdict_and_writes_nothing(self):
        with mock.patch.object(JS, 'failures', side_effect=JS.JsError('fixture checker resource limit', kind='resource')):
            report = self.promote()
        self.assertEqual((report['status'], report['code'], report['failed']),
                         ('inconclusive', 'verification_unknown', []), report)
        self.assertFalse(self.library.exists())

    def test_run_built_from_public_request_binds_as_public_request(self):
        public = K.public_request(self.pack, expected_sha256=self.pack['sha256'])
        apps = FakeApps()
        run_dir, _ = self.fresh_run('public-run', public, apps)
        report = self.promote(run_dir)
        self.assertEqual(report['status'], 'promoted', report)
        self.assertEqual(report['receipt']['request_binding'], 'public_request')
        self.assertEqual(report['receipt']['cases'], {'public': 2, 'hidden': 20, 'total': 22})
        for row in apps.requests:  # hidden rows never reached construction
            self.assertNotIn('inc(...[-10])', json.dumps(row))

    def test_exhaustive_finite_domain_pack_promotes_or_catches_what_public_tests_miss(self):
        req = C.normalize_request(roundtrip_request())
        pack = K.freeze(req, roundtrip_declaration(req), CHECKER)
        self.assertEqual(pack['counts'], {'original_public': 1, 'generated_public': 1, 'hidden': 31, 'proposals': 0})
        public = K.public_request(pack, expected_sha256=pack['sha256'])
        good, _ = self.fresh_run('roundtrip', public, FakeApps(lambda req, n: ROUNDTRIP))
        report = self.promote(good, pack=pack)
        self.assertEqual(report['status'], 'promoted', report)
        self.assertEqual(report['receipt']['finite_domains'], pack['finite_domains'])
        self.assertEqual(report['receipt']['cases'], {'public': 2, 'hidden': 31, 'total': 33})
        self.assertEqual(report['receipt']['request_binding'], 'public_request')
        # Drops -2 elements: passes every public test, fails exactly the 10 domain arrays holding -2.
        buggy = ROUNDTRIP.replace('return JSON.parse(value);',
                                  'const v = JSON.parse(value); return Array.isArray(v) ? v.filter(x => x !== -2) : v;')
        flawed, _ = self.fresh_run('roundtrip-flawed', public, FakeApps(lambda req, n: buggy))
        before = self.snapshot(self.library)
        refused = self.promote(flawed, pack=pack)
        self.assertEqual((refused['status'], refused['code']), ('refused', 'checks_failed'), refused)
        self.assertEqual(len(refused['failed']), 10)
        self.assertEqual({row['visibility'] for row in refused['failed']}, {'hidden'})
        self.assertTrue(all(set(row) == {'id', 'visibility', 'detail'} for row in refused['failed']))
        self.assertEqual(self.snapshot(self.library), before)

    def test_cli_promote_list_and_structured_errors(self):
        pack_file = self.base / 'pack.json'
        pack_file.write_text(json.dumps(self.pack))
        def run(args):
            out = io.StringIO()
            code = P.main(args, out=out)
            return code, json.loads(out.getvalue())
        args = ['--dir', str(self.run_dir), '--pack', str(pack_file), '--library', str(self.library)]
        code, first = run(['promote', *args, '--freeze', self.pack['sha256']])
        self.assertEqual((code, first['status'], first['existing']), (0, 'promoted', False), first)
        code, again = run([*args, '--freeze', self.pack['sha256']])  # promote is the default command
        self.assertEqual((code, again['status'], again['existing']), (0, 'promoted', True), again)
        code, listed = run(['list', '--library', str(self.library)])
        self.assertEqual((code, listed['receipts']), (0, [first['receipt']]))
        code, refused = run(['promote', *args, '--freeze', 'f' * 64])
        self.assertEqual((code, refused['status'], refused['code']), (1, 'refused', 'pack'), refused)
        code, error = run(['promote', '--dir', str(self.run_dir)])
        self.assertEqual((code, error['ok'], error['error']['code']), (2, False, 'arguments'), error)
        code, usage = run(['--help'])
        self.assertEqual((code, usage['commands'], usage['provider_calls']), (0, ['promote', 'list'], 0))


if __name__ == '__main__':
    unittest.main()
