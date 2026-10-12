"""D16 bookkeeping optimizations: exact parity of the faster claim path with the code it replaces.

The iterative claim encoder must accept, reject and encode exactly as the recursive one (same first error), a
precomputed receipt predicate digest must give the same receipt and can never pass a claim when wrong, and the
runner's digest memo is per run, pure and equal to recomputation. No model, host or folder."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from symblic.kernel import epistemic as EP  # noqa: E402
from symblic.kernel import evidence as E  # noqa: E402
from symblic.kernel import run as SR  # noqa: E402


def recursive_json(value):
    """The recursive walk D16 replaced, verbatim, as the reference."""
    count = 0

    def walk(item, depth):
        nonlocal count
        count += 1
        if count > EP.MAX_NODES or depth > EP.MAX_DEPTH:
            EP._fail('limit', 'JSON structure exceeds the node/depth limit')
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            if item.bit_length() > 4096:
                EP._fail('limit', 'Integer exceeds 4096 bits; use canonical exact text')
            return
        if type(item) is str:
            if len(item) > EP.MAX_BYTES:
                EP._fail('limit', 'Text exceeds the claim limit')
            try:
                item.encode('utf-8')
            except UnicodeEncodeError:
                EP._fail('json', 'Unpaired Unicode surrogates are not supported')
            return
        if type(item) is list:
            for child in item:
                walk(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for key, child in item.items():
                walk(key, depth + 1)
                walk(child, depth + 1)
            return
        EP._fail('json', 'Content must be exact JSON (no floats, tuples or custom objects)')

    walk(value, 0)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > EP.MAX_BYTES:
        EP._fail('limit', 'Encoded claim exceeds the byte limit')
    return encoded


def outcome(fn, value):
    try:
        return ('ok', fn(value))
    except EP.EpistemicError as exc:
        return ('error', exc.code, str(exc))


def nested(depth, leaf=1):
    value = leaf
    for _ in range(depth):
        value = [value]
    return value


def hostile_values():
    cyclic = []
    cyclic.append(cyclic)
    yield from (None, True, 0, -5, 2**4096 - 1, 2**4096, 'ascii', 'é ß 日本', '\ud800', 'a' * EP.MAX_BYTES,
                'a' * (EP.MAX_BYTES + 1), 'é' * (EP.MAX_BYTES // 2 + 1), 1.5, (1, 2), {1: 'x'}, {'a': 1.0},
                [1, 2.0, 'x' * (EP.MAX_BYTES + 1)], ['\ud800', 1.5], [{'k': (1,)}, 2**4097],
                nested(EP.MAX_DEPTH), nested(EP.MAX_DEPTH + 1), nested(EP.MAX_DEPTH + 1, 1.5), cyclic,
                list(range(EP.MAX_NODES - 1)), list(range(EP.MAX_NODES)), [[i] for i in range(EP.MAX_NODES // 2)],
                {'b': [1, {'c': '\udfff'}], 'a': 1.5}, {'z': None, 'y': [True, False], 'x': {'w': 'v'}},
                ['é' * 1000] * 140)


class EncoderParity(unittest.TestCase):
    def test_iterative_walk_accepts_rejects_and_encodes_like_the_recursive_one(self):
        for value in hostile_values():
            with self.subTest(value=repr(value)[:60]):
                self.assertEqual(outcome(EP._json, value), outcome(recursive_json, value))

    def test_digest_is_unchanged_for_accepted_values(self):
        for value in hostile_values():
            if outcome(recursive_json, value)[0] == 'ok':
                import hashlib
                self.assertEqual(EP.digest(value), hashlib.sha256(recursive_json(value).encode('utf-8')).hexdigest())


def wide_values():
    """Root's D16 review (WIDTH-PROBE): wide containers over and under MAX_NODES, and early invalid values before a
    huge width, whose reported error must stay the recursive walk's first one."""
    width = 100_000
    yield 'list over the node limit', [None] * width
    yield 'list accepted', [None] * 10_000
    yield 'early float before width', [1.5] + [None] * width
    yield 'early surrogate before width', [None] * 10 + ['\ud800'] + [None] * width
    yield 'dict over the node limit', {f'k{i}': None for i in range(width)}
    yield 'dict accepted', {f'k{i}': i for i in range(5_000)}
    yield 'early float in a wide dict', {'a': 1.5, **{f'k{i}': None for i in range(width)}}
    yield 'non-str key in a wide dict', {**{f'k{i}': None for i in range(width)}, 7: None}
    yield 'wide list inside a list', [[None] * width]
    yield 'depth error before width', [nested(EP.MAX_DEPTH + 1)] + [None] * width
    yield 'node limit before a late float', [None] * width + [1.5]


def traced_peak(fn, value):
    import tracemalloc
    tracemalloc.start()
    try:
        outcome(fn, value)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


class WideContainers(unittest.TestCase):
    def test_wide_and_early_invalid_values_give_the_recursive_first_error(self):
        for label, value in wide_values():
            with self.subTest(label):
                self.assertEqual(outcome(EP._json, value), outcome(recursive_json, value))

    def test_memory_stays_bounded_by_depth_not_width(self):
        # The iterative walk must not queue a wide container whole (v1 held 6.29 MB for 100,000 Nones); it reads
        # one child at a time, like the recursion. The input is built before tracing.
        for label, value in wide_values():
            with self.subTest(label):
                # one untraced call of each first: whichever runs first otherwise pays ~100 KB of one-time warm-up
                outcome(EP._json, value)
                outcome(recursive_json, value)
                ours, reference = traced_peak(EP._json, value), traced_peak(recursive_json, value)
                if outcome(recursive_json, value)[0] == 'ok':
                    self.assertLessEqual(ours, reference + 16384, (ours, reference))
                else:
                    self.assertLessEqual(ours, 16384, (ours, reference))


class PrecomputedPredicate(unittest.TestCase):
    SUBJECT = {'name': 'c', 'value_sha256': 'a' * 64}
    PREDICATE = {'kernel': 'k', 'operation_sha256': 'b' * 64}

    def test_a_correct_precomputed_digest_gives_the_same_receipt(self):
        plain = EP.receipt(subject=self.SUBJECT, predicate=self.PREDICATE, scope='encoded_derivation', passed=True,
                           inputs=[])
        given = EP.receipt(subject=self.SUBJECT, predicate=self.PREDICATE, scope='encoded_derivation', passed=True,
                           inputs=[], predicate_sha256=EP.digest(self.PREDICATE))
        self.assertEqual(plain, given)

    def test_a_wrong_precomputed_digest_cannot_pass_a_claim(self):
        forged = EP.receipt(subject=self.SUBJECT, predicate=self.PREDICATE, scope='encoded_derivation', passed=True,
                            inputs=[], predicate_sha256='0' * 64)
        with self.assertRaises(EP.EpistemicError):
            EP.make_claim('binding:test', self.SUBJECT, origin='derived', checks=[forged])


class RunMemo(unittest.TestCase):
    LOOP = 'use profile=verified.\nfor a in 1..5 do\n  let c = a * 2.\nend.\nshow c.\n'

    def test_the_memo_is_per_run_and_not_shared(self):
        one, two = SR.Run(self.LOOP), SR.Run(self.LOOP)
        self.assertIsNot(one._digest_memo, two._digest_memo)
        one.execute()
        self.assertTrue(one._digest_memo)
        self.assertEqual(two._digest_memo, {})

    def test_memoized_digests_equal_recomputation_and_no_key_is_a_parsed_node(self):
        run = SR.Run(self.LOOP)
        run.execute()
        for key, value in run._digest_memo.items():
            if type(key) is str:
                self.assertEqual(value, E.digest(key))
                continue
            self.assertIs(type(key), tuple, key)
            kind = key[0]
            predicate = {'type-predicate': lambda k: {'type_sha256': k[1]},
                         'derivation-predicate': lambda k: {'kernel': k[1], 'operation_sha256': k[2]},
                         'grouping-predicate': lambda k: {'kernel': k[1], 'operation': 'lineage_grouping'}}[kind](key)
            self.assertEqual(value, EP.digest(predicate))
            self.assertTrue(all(type(part) is str for part in key), key)    # values only: never a node or its id

    # Native critic (review-d16-native/MUTATION-PROBE.json): symblic_lang rewrites a nested routine's return after
    # its first declaration, so the `for` statement's syntax changes between outer(0) and outer(1). A memo keyed by
    # the parsed node kept f3c84ee... where the true derivation is ce01468...; v3 caches nothing keyed by a node.
    MUTATING = ('use profile=verified.\nroutine outer(n: Int) -> Int do\n  for i in [1] do\n    if n > 0 then\n'
                '      routine late() -> Int do\n        return 7.\n      end.\n    end.\n    let val = n.\n  end.\n'
                '  return first(val).\nend.\nlet first_result = outer(0).\nlet second_result = outer(1).\n'
                'show [first_result, second_result].\n')

    def test_a_statement_rewritten_after_first_use_keeps_exact_provenance(self):
        from unittest import mock

        def snapshot(run):
            return json.dumps([run._epistemic_claims, run._epistemic_views,
                               [{k: v for k, v in row.items() if k not in ('at', 'ms', 'seconds')} for row in run.trace]],
                              sort_keys=True, default=str)

        memo = SR.Run(self.MUTATING)
        self.assertEqual(memo.execute()['status'], 'done')
        patches = [mock.patch.object(SR.Run, '_text_digest', lambda self, text: E.digest(text)),
                   mock.patch.object(SR.Run, '_predicate_digest', lambda self, predicate, key: EP.digest(predicate))]
        if hasattr(SR.Run, '_statement_derivation'):        # an earlier candidate's node-keyed memo (v1, v2)
            patches.append(mock.patch.object(SR.Run, '_statement_derivation', lambda self, statement: E.syntax(statement)))
        for patch in patches:
            patch.start()
        try:
            plain = SR.Run(self.MUTATING)
            self.assertEqual(plain.execute()['status'], 'done')
        finally:
            for patch in patches:
                patch.stop()
        self.assertEqual(snapshot(memo), snapshot(plain))

    def test_a_retry_rollback_leaves_claims_identical_to_a_fresh_computation(self):
        src = ('use profile=verified.\nask x: Int in 0..10 "Pick." with retries=2\n'
               'ensure x = 3 else retry because "three".\nshow x.\n')

        class Apps:
            def call(self, req):
                return {'ok': True, 'json': {'answer': 0}, 'model': 'fake', 'node': 'n', 'ms': 1}

        runs = [SR.Run(src, {}, Apps(), {'parallel': 1}) for _ in range(2)]
        for run in runs:
            run.execute()
        self.assertEqual(json.dumps(runs[0]._epistemic_claims, sort_keys=True),
                         json.dumps(runs[1]._epistemic_claims, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
