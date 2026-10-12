"""Single-pass claim path: legacy behavior identical to the frozen baseline module.

make_claim and validate_claim are compared with tests/fixtures/symblic_epistemic_baseline_e5aa249c.py,
a byte-exact copy of the module before the change, on generated bounded valid and invalid inputs,
limit boundaries, mutation and alias cases: equal values in the same key order and sharing shape,
or the same exception type, code, message and details. In-memory only: no providers, stores,
workers, network or files beyond reading that fixture.

The frozen oracle covers the six version-1 origins. Version-2 solver proposals
were deliberately added later and have their own contract in
test_symblic_solver_provenance.py; sampling them here would compare different
declared schemas, not detect a regression in the optimized legacy path.
"""
import copy
import hashlib
import importlib.util
import json
import random
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from symblic.kernel import epistemic as E

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'symblic_epistemic_baseline_e5aa249c.py'
BASELINE_SHA256 = 'e5aa249c67c8edcb3f418956c2afa4b084456abfd44644db1b319104835201f0'


def _baseline():
    raw = FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASELINE_SHA256:
        raise AssertionError('the frozen baseline fixture changed')
    spec = importlib.util.spec_from_file_location('_symblic_epistemic_baseline', FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _baseline()


def shape(value):
    """Container sharing signature: index of first visit for every container occurrence."""
    first, order = {}, []

    def visit(item):
        if type(item) in (dict, list):
            key = id(item)
            order.append(first.setdefault(key, len(first)))
            if order[-1] == len(first) - 1 and order.count(order[-1]) == 1:
                for child in (item.values() if type(item) is dict else item):
                    visit(child)
    visit(value)
    return order


def containers(value, found=None):
    found = set() if found is None else found
    if type(value) in (dict, list) and id(value) not in found:
        found.add(id(value))
        for child in (value.values() if type(value) is dict else value):
            containers(child, found)
    return found


def outcome(call):
    try:
        value = call()
    except Exception as error:  # noqa: BLE001 - every exception kind is part of the compared behavior
        return ('error', type(error).__name__, getattr(error, 'code', None), str(error),
                getattr(error, 'details', None))
    return ('value', json.dumps(value, ensure_ascii=False), shape(value))


class Generated:
    """Seeded bounded inputs: JSON values, references and receipts."""

    def __init__(self, seed):
        self.rng = random.Random(seed)

    def text(self):
        alphabet = 'abcXYZ09 _-:/.é漢 "\\\n'
        return ''.join(self.rng.choice(alphabet) for _ in range(self.rng.randint(0, 12)))

    def value(self, depth=0):
        roll = self.rng.random()
        if depth >= 4 or roll < 0.35:
            return self.rng.choice([None, True, False, 0, -7, 2**60, 2**4095, self.text(), ''])
        if roll < 0.65:
            return [self.value(depth + 1) for _ in range(self.rng.randint(0, 4))]
        keys = [self.text() for _ in range(self.rng.randint(0, 4))]
        return {key: self.value(depth + 1) for key in keys}

    def reference(self, index):
        row = {'id': f'claim.{index:03d}', 'revision': self.rng.randint(1, 5),
               'sha256': hashlib.sha256(str(index).encode()).hexdigest()}
        items = list(row.items())
        self.rng.shuffle(items)
        return dict(items)

    def claim_args(self, receipt=E.receipt):
        content = self.value()
        refs = [self.reference(index) for index in self.rng.sample(range(40), self.rng.randint(0, 6))]
        origin = self.rng.choice(sorted(B.ORIGINS))
        status = 'conditional' if origin == 'derived' and self.rng.random() < 0.5 else \
            self.rng.choice(['unknown', 'contested', 'refuted'])
        checks = []
        for _ in range(self.rng.randint(0, 3)):
            scope = self.rng.choice(sorted(E.SCOPES))
            inputs = sorted(refs, key=lambda row: row['id']) if scope == 'encoded_derivation' else \
                self.rng.sample(refs, self.rng.randint(0, len(refs)))
            checks.append(receipt(subject=content, predicate=self.value(), scope=scope,
                                  passed=self.rng.random() < 0.8, inputs=inputs))
        self.rng.shuffle(refs)
        return {'ident': f'claim.{self.rng.randint(0, 999)}', 'content': content, 'origin': origin,
                'revision': self.rng.randint(1, 9), 'dependencies': refs, 'checks': checks,
                'status': status, 'withdrawn': self.rng.random() < 0.2}


def sealed_receipt(*, subject, predicate, scope, passed, inputs):
    """A correctly sealed receipt over exactly these inputs, in the given order (maybe non-canonical)."""
    body = {'version': B.VERSION, 'subject_sha256': B.digest(subject), 'predicate': predicate,
            'predicate_sha256': B.digest(predicate), 'scope': scope, 'passed': passed, 'inputs': inputs}
    return {**body, 'id': B.digest(body)}


def resealed(claim, **fields):
    """A claim changed only in these fields, with its claim digest recomputed (content digest untouched)."""
    row = {**claim, **fields}
    row['sha256'] = B.digest({key: value for key, value in row.items() if key != 'sha256'})
    return row


def single_rule_receipts(args):
    """Receipts that break exactly one claim rule, each sealed so no digest check decides first."""
    content, refs = args['content'], sorted(args['dependencies'], key=lambda row: row['id'])
    undeclared = {'id': 'zz.undeclared', 'revision': 1, 'sha256': '9' * 64}
    out = [[sealed_receipt(subject={'other': 'content'}, predicate={'p': 1}, scope='encoded_schema',
                           passed=True, inputs=refs)],
           [sealed_receipt(subject=content, predicate={'p': 2}, scope='encoded_schema', passed=True,
                           inputs=refs + [undeclared])]]
    if len(refs) >= 2:
        out.append([sealed_receipt(subject=content, predicate={'p': 3}, scope='encoded_schema', passed=True,
                                   inputs=list(reversed(refs)))])
        out.append([sealed_receipt(subject=content, predicate={'p': 4}, scope='encoded_derivation',
                                   passed=True, inputs=refs[:1])])
    if refs:
        repinned = [dict(refs[0], revision=refs[0]['revision'] + 1)] + refs[1:]
        out.append([sealed_receipt(subject=content, predicate={'p': 5}, scope='encoded_schema', passed=True,
                                   inputs=repinned)])
        out.append([sealed_receipt(subject=content, predicate={'p': 6}, scope='encoded_schema', passed=True,
                                   inputs=[refs[0], refs[0]])])
    shared = {'k': 1}
    out.append([sealed_receipt(subject=content, predicate={'a': shared, 'b': shared}, scope='encoded_schema',
                               passed=False, inputs=[])])
    # Field defects behind a valid seal, so the field check itself must decide.
    for field, value in (('scope', 'encoded_truth'), ('passed', 1), ('version', 2)):
        row = sealed_receipt(subject=content, predicate={'p': field}, scope='encoded_schema', passed=True, inputs=[])
        body = {key: item for key, item in row.items() if key != 'id'}
        body[field] = value
        out.append([{**body, 'id': B.digest(body)}])
    bad = {'id': 'bad id', 'revision': 0, 'sha256': 'A' * 64}
    for field in bad:
        if refs:
            wrong = [dict(refs[0], **{field: bad[field]})] + refs[1:]
            out.append([sealed_receipt(subject=content, predicate={'p': 'ref-' + field}, scope='encoded_schema',
                                       passed=True, inputs=wrong)])
    return out


def make(module, args):
    return module.make_claim(args['ident'], args['content'], origin=args['origin'], revision=args['revision'],
                             dependencies=args['dependencies'], checks=args['checks'],
                             status=args['status'], withdrawn=args['withdrawn'])


class ClaimPathEquivalence(unittest.TestCase):
    def test_historical_generator_domain_matches_retained_version_one_contract(self):
        self.assertEqual(B.ORIGINS, E.ORIGINS_V1)
        self.assertEqual({'solver_proposal'}, E.ORIGINS - B.ORIGINS)
        self.assertNotIn('solver_proposal', {Generated(seed).claim_args()['origin'] for seed in range(400)})

    def same(self, call, args_factory):
        """Both modules on independent but identically shaped inputs."""
        expected = outcome(lambda: call(B, args_factory()))
        actual = outcome(lambda: call(E, args_factory()))
        self.assertEqual(actual, expected)
        return expected

    def test_generated_valid_claims_match_values_order_and_sharing(self):
        valid = 0
        # Valid inputs without internal sharing must take the single pass: a match that
        # came from the reference fallback would prove nothing about the new path.
        fallbacks = 0
        with patch.object(E, '_make_claim_reference', wraps=E._make_claim_reference) as made:
            for seed in range(400):
                args = Generated(seed).claim_args()
                result = self.same(make, lambda args=args: copy.deepcopy(args))
                valid += result[0] == 'value'
                if result[0] == 'value':
                    claim = make(B, copy.deepcopy(args))
                    with patch.object(E, '_validate_claim_reference', wraps=E._validate_claim_reference) as checked:
                        self.same(lambda module, row: module.validate_claim(row),
                                  lambda claim=claim: copy.deepcopy(claim))
                    fallbacks += checked.call_count
        self.assertGreater(valid, 200)
        self.assertEqual(made.call_count, 400 - valid)  # only invalid inputs reach the reference checks
        self.assertEqual(fallbacks, 0)

    def mutations(self, args):
        lock = threading.Lock()
        cyclic = []
        cyclic.append(cyclic)
        shared = [1, 2]

        class Sub(dict):
            pass
        refs, checks = args['dependencies'], args['checks']
        yield 'ident', ['', 'x' * 161, 'a b', 1, 1.5, None, 'é', ('t',)]
        yield 'revision', [0, -1, 2**53, True, 1.0, '1', None]
        yield 'origin', ['nope', 1, None]
        yield 'status', ['nope', 'conditional', 2]
        yield 'withdrawn', [0, 1, 'false', None]
        scalar_dict = {'k': 1}
        yield 'content', [0.5, ('a',), {1}, {1: 'a'}, {'a': [0.5]}, '\ud800', 2**4096, Sub(a=1),
                          lock, {'a': lock}, cyclic, {'a': shared, 'b': shared}, 'x' * (E.MAX_BYTES + 1),
                          {'a': scalar_dict, 'b': scalar_dict}, [scalar_dict, [scalar_dict]]]
        yield 'dependencies', [(), 'x', [dict(refs[0], extra=1)] if refs else [{'id': 'a'}],
                               [refs[0], refs[0]] if refs else [Sub(id='a', revision=1, sha256='0' * 64)],
                               [dict(refs[0], sha256='A' * 64)] if refs else [1],
                               [{'id': f'r{i}', 'revision': 1, 'sha256': '0' * 64} for i in range(65)]]
        yield 'checks', [(), 'x', [1], [dict(checks[0], version=2)] if checks else [{}],
                         [checks[0], checks[0]] if checks else [None],
                         [dict(checks[0], scope='encoded_truth')] if checks else [[]],
                         [dict(checks[0], passed=1)] if checks else [()],
                         [dict(checks[0], predicate={'changed': True})] if checks else [{'id': '0' * 64}],
                         [dict(checks[0], inputs=list(reversed(checks[0]['inputs'])))] if checks else [0],
                         [dict(checks[0], subject_sha256='0' * 64)] if checks else [True]]
        yield 'checks', single_rule_receipts(args)

    def test_invalid_inputs_raise_exactly_as_before(self):
        compared = 0
        for seed in range(60):
            base = Generated(1000 + seed).claim_args()
            for field, values in self.mutations(base):
                for value in values:
                    with self.subTest(seed=seed, field=field, value=repr(value)[:60]):
                        def factory(value=value, field=field):
                            # The same objects for both calls keep exotic values (locks, cycles) intact;
                            # neither path may mutate its inputs, which the alias test checks separately.
                            return {**base, field: value}
                        self.same(make, factory)
                        compared += 1
        self.assertGreater(compared, 2000)

    def test_claim_tampering_and_key_orders_validate_exactly_as_before(self):
        shared = {'k': [1]}
        for seed in range(80):
            args = Generated(2000 + seed).claim_args()
            try:
                claim = make(B, copy.deepcopy(args))
            except B.EpistemicError:
                continue
            variants = [dict(reversed(list(claim.items())))]
            for key, value in (('version', 2), ('id', 'bad id'), ('revision', 0), ('origin', 'x'),
                               ('status', 'conditional'), ('withdrawn', 1), ('content', {'other': 1}),
                               ('content_sha256', '0' * 64), ('sha256', claim['sha256'].upper()),
                               ('dependencies', list(reversed(claim['dependencies']))),
                               ('checks', list(reversed(claim['checks']))),
                               ('checks', claim['checks'] + claim['checks'][:1]), ('extra', 1)):
                variants.append({**claim, key: value})
            variants.append({k: v for k, v in claim.items() if k != 'checks'})
            for key in ('dependencies', 'checks'):
                if len(claim[key]) >= 2:  # sealed claims whose only defect is the order
                    variants.append(resealed(claim, **{key: list(reversed(claim[key]))}))
            if claim['checks']:
                variants.append(resealed(claim, checks=claim['checks'] + claim['checks'][:1]))
            scalar = {'k': 1}
            twice = dict(claim, content={'a': scalar, 'b': scalar})
            twice['content_sha256'] = B.digest(twice['content'])
            variants.append(resealed(twice))
            for receipts in single_rule_receipts({'content': claim['content'],
                                                  'dependencies': claim['dependencies']}):
                variants.append(resealed(claim, checks=receipts))
            # Field defects behind a valid claim seal: the field check itself must decide.
            for key, value in (('version', 2), ('id', 'bad id'), ('revision', 0), ('revision', True),
                               ('origin', 'x'), ('status', 'conditional'), ('status', 'nope'),
                               ('withdrawn', 1), ('extra', 1)):
                variants.append(resealed(claim, **{key: value}))
            if claim['dependencies']:
                for key, value in (('revision', 0), ('id', 'bad id'), ('sha256', 'A' * 64)):
                    wrong = [dict(claim['dependencies'][0], **{key: value})] + claim['dependencies'][1:]
                    variants.append(resealed(claim, dependencies=wrong))
            variants.append(resealed(claim, content={'other': 1}))  # content digest now stale
            aliased = dict(claim, content={'a': shared, 'b': shared})
            aliased['content_sha256'] = B.digest(aliased['content'])
            aliased['sha256'] = B.digest({k: v for k, v in aliased.items() if k != 'sha256'})
            variants.append(aliased)
            for variant in variants:
                with self.subTest(seed=seed, variant=sorted(set(variant) ^ set(claim)) or list(variant)[:2]):
                    self.same(lambda module, row: module.validate_claim(row), lambda variant=variant: variant)

    def test_limit_boundaries_match(self):
        def bisect(build, low, high):
            # Largest size the baseline accepts, then probe both sides of it.
            while low < high:
                middle = (low + high + 1) // 2
                try:
                    B.make_claim('bound', build(middle), origin='assumption')
                    low = middle
                except B.EpistemicError:
                    high = middle - 1
            return low
        builds = {'bytes': lambda size: 'x' * size,
                  'nodes': lambda size: [0] * size,
                  'depth': lambda size: self.nested(size)}
        for name, build in builds.items():
            edge = bisect(build, 0, {'bytes': E.MAX_BYTES, 'nodes': E.MAX_NODES, 'depth': 40}[name])
            for size in (edge - 1, edge, edge + 1):
                with self.subTest(limit=name, size=size):
                    self.same(lambda module, content: module.make_claim('bound', content, origin='assumption'),
                              lambda size=size, build=build: build(size))
            claim = B.make_claim('bound', build(edge), origin='assumption')
            self.same(lambda module, row: module.validate_claim(row), lambda claim=claim: claim)

    @staticmethod
    def nested(depth):
        value = 0
        for _ in range(depth):
            value = [value]
        return value

    def test_results_share_nothing_with_inputs_and_inputs_stay_unchanged(self):
        for seed in range(60):
            args = Generated(3000 + seed).claim_args()
            before = copy.deepcopy(args)
            try:
                claim = make(E, args)
            except E.EpistemicError:
                continue
            self.assertEqual(args, before)
            self.assertFalse(containers(claim) & containers(args))
            checked = E.validate_claim(claim)
            self.assertFalse(containers(checked) & containers(claim))
            copy_of_claim = copy.deepcopy(claim)
            if type(checked['content']) in (dict, list):
                checked['content'].clear()
            self.assertEqual(claim, copy_of_claim)

    def test_shared_runtime_references_take_the_single_pass_and_internal_sharing_falls_back(self):
        refs = [{'id': f'binding:{i:03d}', 'revision': 1, 'sha256': f'{i:064x}'} for i in range(8)]
        content = {'name': 'answer', 'line': 3}
        checks = [E.receipt(subject=content, predicate={'kernel': 'k'}, scope='encoded_derivation',
                            passed=True, inputs=refs)]
        with patch.object(E, '_make_claim_reference', side_effect=AssertionError('fell back')):
            claim = E.make_claim('binding:x', content, origin='derived', dependencies=refs, checks=checks)
        with patch.object(E, '_validate_claim_reference', side_effect=AssertionError('fell back')):
            E.validate_claim(claim)
        shared = [1]
        with patch.object(E, '_make_claim_reference', wraps=E._make_claim_reference) as reference:
            E.make_claim('binding:y', {'a': shared, 'b': shared}, origin='assumption')
        self.assertEqual(reference.call_count, 1)


class Text(str):
    """A str subclass: it compares, hashes and JSON-encodes like its text, but is not exact JSON."""


class Number(int):
    """An int subclass with the same properties for integer fields."""


class Sly:
    """A non-JSON value whose comparisons run code: it must never be compared before the type check."""

    def __init__(self, text):
        self.text = text

    def __eq__(self, other):
        raise TypeError('comparison ran custom code')

    __ne__ = __eq__

    def __hash__(self):
        return hash(self.text)


def plain(value):
    """The exact-JSON equivalent a JSONEncoder would encode: subclasses become their base values."""
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if type(value) is list:
        return [plain(item) for item in value]
    if type(value) is dict:
        return {plain(key): plain(item) for key, item in value.items()}
    return value


def sealed_as_plain(row, seal):
    """Recompute the seal field over the plain equivalent, so only exactness can decide.

    A row holding a comparison object anywhere has no plain equivalent; it stays as it is."""
    key = next(key for key in row if key == seal)
    try:
        return {**row, key: B.digest(plain({k: v for k, v in row.items() if k != seal}))}
    except B.EpistemicError:
        return row


class ExactTypeParity(unittest.TestCase):
    """Root review of 66121678: fields checked outside _tree need exact types before any comparison."""

    def setUp(self):
        self.content = {'name': 'answer'}
        self.refs = [{'id': 'claim.001', 'revision': 1, 'sha256': '1' * 64},
                     {'id': 'claim.002', 'revision': 2, 'sha256': '2' * 64}]
        self.receipt = sealed_receipt(subject=self.content, predicate={'p': 1}, scope='encoded_schema',
                                      passed=True, inputs=self.refs)
        self.claim = B.make_claim('c.1', self.content, origin='derived', dependencies=self.refs, checks=[self.receipt])

    def make_with(self, *, checks=None, dependencies=None):
        return lambda module, _=None: module.make_claim(
            'c.1', self.content, origin='derived', dependencies=self.refs if dependencies is None else dependencies,
            checks=[self.receipt] if checks is None else checks)

    def validate(self, claim):
        ClaimPathEquivalence.same(self, lambda module, row: module.validate_claim(row), lambda: claim)

    def make(self, **kwargs):
        ClaimPathEquivalence.same(self, self.make_with(**kwargs), lambda: None)

    def test_content_sha256_str_subclass_in_a_sealed_claim(self):
        self.validate(sealed_as_plain({**self.claim, 'content_sha256': Text(self.claim['content_sha256'])}, 'sha256'))

    def test_predicate_sha256_str_subclass_in_a_sealed_receipt(self):
        self.make(checks=[sealed_as_plain({**self.receipt, 'predicate_sha256': Text(self.receipt['predicate_sha256'])}, 'id')])

    def test_predicate_sha256_str_subclass_inside_a_sealed_claim(self):
        receipt = sealed_as_plain({**self.receipt, 'predicate_sha256': Text(self.receipt['predicate_sha256'])}, 'id')
        self.validate(sealed_as_plain({**self.claim, 'checks': [receipt]}, 'sha256'))

    def test_comparison_object_in_content_sha256(self):
        self.validate({**self.claim, 'content_sha256': Sly(self.claim['content_sha256'])})

    def test_comparison_object_in_predicate_sha256(self):
        receipt = {**self.receipt, 'predicate_sha256': Sly(self.receipt['predicate_sha256'])}
        self.make(checks=[receipt])
        self.validate({**self.claim, 'checks': [receipt]})

    def test_str_subclass_key_in_a_reference_envelope(self):
        renamed = {Text(key) if key == 'id' else key: value for key, value in self.refs[0].items()}
        self.make(dependencies=[renamed, self.refs[1]])
        self.make(checks=[sealed_as_plain({**self.receipt, 'inputs': [renamed, self.refs[1]]}, 'id')])
        self.validate(sealed_as_plain({**self.claim, 'dependencies': [renamed, self.refs[1]]}, 'sha256'))

    def test_str_subclass_key_in_receipt_and_claim_envelopes(self):
        receipt = sealed_as_plain({Text(key) if key == 'scope' else key: value
                                   for key, value in self.receipt.items()}, 'id')
        self.make(checks=[receipt])
        self.validate(sealed_as_plain({**self.claim, 'checks': [receipt]}, 'sha256'))
        self.validate(sealed_as_plain({Text(key) if key == 'withdrawn' else key: value
                                       for key, value in self.claim.items()}, 'sha256'))

    def test_every_field_outside_the_tree_walk_is_exact_before_comparison(self):
        """Sweep every key and scalar value of every envelope the single pass checks itself."""
        def variants(value):
            out = [Sly(str(value))]
            if type(value) is str:
                out.append(Text(value))
            elif type(value) is int:
                out.append(Number(value))
            return out
        receipt_scalars = [key for key, value in self.receipt.items() if key not in ('predicate', 'inputs')]
        claim_scalars = [key for key in self.claim if key not in ('content', 'dependencies', 'checks')]
        compared = 0
        for key in self.receipt:  # receipt envelope keys and scalar values, in make and in a sealed claim
            renamed = sealed_as_plain({Text(k) if k == key else k: v for k, v in self.receipt.items()}, 'id')
            changed = [renamed] + [sealed_as_plain({**self.receipt, key: value}, 'id')
                                   for value in (variants(self.receipt[key]) if key in receipt_scalars else ())]
            for receipt in changed:
                self.make(checks=[receipt])
                self.validate(sealed_as_plain({**self.claim, 'checks': [receipt]}, 'sha256'))
                compared += 2
        for key in self.refs[0]:  # dependency and receipt-input reference keys and values
            for ref in [{Text(k) if k == key else k: v for k, v in self.refs[0].items()}] + \
                    [{**self.refs[0], key: value} for value in variants(self.refs[0][key])]:
                self.make(dependencies=[ref, self.refs[1]])
                self.make(checks=[sealed_as_plain({**self.receipt, 'inputs': [ref, self.refs[1]]}, 'id')])
                self.validate(sealed_as_plain({**self.claim, 'dependencies': [ref, self.refs[1]]}, 'sha256'))
                compared += 3
        for key in self.claim:  # claim envelope keys and scalar values
            changed = [sealed_as_plain({Text(k) if k == key else k: v for k, v in self.claim.items()}, 'sha256')]
            if key in claim_scalars:
                changed += [sealed_as_plain({**self.claim, key: value}, 'sha256') for value in variants(self.claim[key])]
            for claim in changed:
                self.validate(claim)
                compared += 1
        self.assertGreater(compared, 90)


class OperationCounts(unittest.TestCase):
    """The single pass removes the repeated walks, digests and copies."""

    def counted(self, module, args):
        nodes, walks, copies = [0], [0], [0]
        real_json, real_deepcopy = module._json, copy.deepcopy

        def json_counted(value):
            walks[0] += 1
            nodes[0] += _nodes(value)
            return real_json(value)

        def deepcopy_counted(value, memo=None, _nil=[]):
            if memo is None:
                copies[0] += 1
            return real_deepcopy(value, memo)
        validated = [0]
        real_sealed = getattr(module, '_sealed', None)

        def sealed_counted(body, state):
            validated[0] += state[0] + 2  # nodes of the sealed claim: each validated once per call
            return real_sealed(body, state)
        patches = [patch.object(module, '_json', json_counted), patch.object(module.copy, 'deepcopy', deepcopy_counted)]
        if real_sealed is not None:
            patches.append(patch.object(module, '_sealed', sealed_counted))
        for item in patches:
            item.start()
        try:
            claim = make(module, args)
            module.validate_claim(claim)
        finally:
            for item in reversed(patches):
                item.stop()
        return {'walks': walks[0], 'walked_nodes': nodes[0], 'deepcopies': copies[0], 'validated_nodes': validated[0],
                'claim_nodes': _nodes(claim)}

    def test_single_pass_has_no_repeated_walks_or_deep_copies(self):
        for count in (0, 4, 16, 64):
            refs = [{'id': f'binding:{i:048d}', 'revision': 1, 'sha256': f'{i:064x}'} for i in range(count)]
            content = {'name': 'answer', 'name_sha256': 'a' * 64, 'type': 'Int', 'line': 12}
            checks = [E.receipt(subject=content, predicate={'type_sha256': 'b' * 64}, scope='encoded_schema',
                                passed=True, inputs=refs)]
            args = {'ident': 'binding:x', 'content': content, 'origin': 'derived' if refs else 'assumption',
                    'revision': 1, 'dependencies': refs, 'checks': checks, 'status': 'unknown', 'withdrawn': False}
            before, after = self.counted(B, copy.deepcopy(args)), self.counted(E, copy.deepcopy(args))
            with self.subTest(references=count, baseline=before, single_pass=after):
                self.assertEqual((after['walks'], after['deepcopies']), (0, 0))
                self.assertGreaterEqual(before['walks'], 8)
                self.assertGreater(before['deepcopies'], 2 * count)
                # make_claim and validate_claim each validate every claim node exactly once,
                # where the baseline walked the same nodes many times over.
                self.assertEqual(after['validated_nodes'], 2 * after['claim_nodes'])
                self.assertGreaterEqual(before['walked_nodes'], 3 * after['validated_nodes'])


def _nodes(value):
    count = 1
    if type(value) is list:
        count += sum(_nodes(item) for item in value)
    elif type(value) is dict:
        count += sum(1 + _nodes(item) for item in value.values())
    return count


if __name__ == '__main__':
    unittest.main()
