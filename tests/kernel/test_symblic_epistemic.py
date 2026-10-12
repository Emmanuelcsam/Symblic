"""Adversarial unit tests; no providers, files, stores, workers or external calls."""
import copy
import unittest

from symblic.kernel import epistemic as E


def premise(ident='p', value='The invoice total is 3.', origin='model_proposal', **kw):
    return E.make_claim(ident, value, origin=origin, **kw)


def derived(ident, value, parents, **kw):
    refs = [E.reference(parent) for parent in parents]
    check = E.receipt(subject=value, predicate={'derivation': ident}, scope='encoded_derivation',
                      passed=True, inputs=refs)
    return E.make_claim(ident, value, origin='derived', dependencies=refs, checks=[check], **kw)


def reseal(row):
    row['sha256'] = E.digest({key: value for key, value in row.items() if key != 'sha256'})
    return row


class ClaimContracts(unittest.TestCase):
    def assertCode(self, code, call):
        with self.assertRaises(E.EpistemicError) as raised:
            call()
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_false_model_number_through_checked_arithmetic_remains_conditional(self):
        number = premise(value={'invoice_total': 3})  # Actual source total is 120.
        plus = derived('with_tax', {'total': '33/10'}, [number])
        final = derived('rounded', {'total': '3'}, [plus])
        view = E.evaluate([number, plus, final])
        self.assertEqual(view['p']['status'], 'unknown')
        self.assertEqual(view['with_tax']['status'], 'conditional')
        self.assertEqual(view['rounded']['conditional_on'][0]['ref'], E.reference(number))
        self.assertEqual(view['rounded']['conditional_on'][0]['origin'], 'model_proposal')
        self.assertTrue(view['rounded']['admissible'])
        self.assertEqual(view['rounded']['empirical_truth'], 'not_established')

    def test_schema_or_predicate_acceptance_cannot_create_derivation(self):
        value = 'Bananas orbit Jupiter.'
        for scope in ('encoded_schema', 'encoded_predicate'):
            check = E.receipt(subject=value, predicate='at most 20 words', scope=scope,
                              passed=True, inputs=[])
            row = E.make_claim('summary', value, origin='derived', checks=[check])
            view = E.evaluate([row])['summary']
            self.assertEqual(view['status'], 'unknown')
            self.assertFalse(view['admissible'])
            self.assertIn(check['id'], view['passed_receipt_ids'])

    def test_owner_and_source_origins_do_not_imply_truth(self):
        rows = [premise(origin=origin, ident=origin) for origin in E.ORIGINS if origin != 'derived']
        for view in E.evaluate(rows).values():
            self.assertEqual(view['status'], 'unknown')
            self.assertEqual(view['support'], 'premise')
            self.assertEqual(view['empirical_truth'], 'not_established')

    def test_unanimous_content_is_not_confidence_or_truth(self):
        a, b = premise('a'), premise('b')
        self.assertEqual(a['content_sha256'], b['content_sha256'])
        view = E.evaluate([a, b])
        self.assertEqual(len(view), 2)
        self.assertTrue(all(row['status'] == 'unknown' for row in view.values()))
        self.assertNotIn('confidence', view['a'])

    def test_dependency_change_invalidates_full_chain(self):
        p = premise(origin='assumption')
        q = derived('q', 6, [p])
        r = derived('r', 7, [q])
        changed = premise(value=120, origin='assumption', revision=2)
        view = E.evaluate([changed, q, r])
        self.assertEqual(view['q']['issues'][0]['code'], 'stale_dependency')
        self.assertEqual(view['r']['issues'][0]['code'], 'unavailable_dependency')
        self.assertFalse(view['r']['admissible'])
        self.assertEqual(view['r']['status'], 'unknown')

    def test_withdrawal_changes_pin_even_same_content_and_revision(self):
        p = premise(origin='assumption')
        q = derived('q', 6, [p])
        withdrawn = premise(origin='assumption', withdrawn=True)
        self.assertEqual(p['content_sha256'], withdrawn['content_sha256'])
        self.assertNotEqual(p['sha256'], withdrawn['sha256'])
        view = E.evaluate([withdrawn, q])
        self.assertFalse(view['p']['admissible'])
        self.assertFalse(view['q']['admissible'])

    def test_refuted_premise_does_not_automatically_refute_conclusion(self):
        p = premise(status='refuted')
        q = derived('q', 'Anything follows?', [p])
        view = E.evaluate([p, q])
        self.assertEqual(view['p']['status'], 'refuted')
        self.assertEqual(view['q']['status'], 'unknown')
        self.assertFalse(view['q']['admissible'])

    def test_conflict_preserves_alternatives_and_blocks_explosion(self):
        p, no_p = premise('p', 'A'), premise('not_p', 'not A')
        arbitrary = derived('z', 'The moon is cheese', [p, no_p])
        conflict = {'id': 'opposition', 'claims': [E.reference(p), E.reference(no_p)]}
        view = E.evaluate([p, no_p, arbitrary], disagreements=[conflict])
        self.assertEqual(view['p']['status'], 'contested')
        self.assertEqual(view['not_p']['status'], 'contested')
        self.assertEqual(len(view['p']['disagreements'][0]['claims']), 2)
        self.assertFalse(view['z']['admissible'])
        self.assertEqual(view['z']['status'], 'unknown')
        self.assertEqual(view['p']['empirical_truth'], 'not_established')

    def test_conflict_rejects_stale_opponent(self):
        a, b = premise('a'), premise('b')
        old = {'id': 'c', 'claims': [E.reference(a), E.reference(b)]}
        b2 = premise('b', 'changed', revision=2)
        self.assertCode('stale', lambda: E.evaluate([a, b2], disagreements=[old]))

    def test_cycle_is_rejected_even_with_stale_hashes(self):
        a, b = premise('a'), premise('b')
        a['dependencies'] = [E.reference(b)]
        a = reseal(a)
        b['dependencies'] = [E.reference(a)]
        b = reseal(b)
        self.assertCode('cycle', lambda: E.evaluate([a, b]))

    def test_missing_parent_is_unavailable_not_true(self):
        p = premise()
        q = derived('q', 3, [p])
        view = E.evaluate([q])['q']
        self.assertFalse(view['admissible'])
        self.assertEqual(view['issues'][0]['code'], 'missing_dependency')

    def test_duplicate_ids_and_dependency_refs_rejected(self):
        p = premise()
        self.assertCode('duplicate', lambda: E.evaluate([p, copy.deepcopy(p)]))
        ref = E.reference(p)
        self.assertCode('duplicate', lambda: E.make_claim('q', 2, origin='derived', dependencies=[ref, ref]))

    def test_duplicate_receipt_ids_rejected(self):
        check = E.receipt(subject=2, predicate=True, scope='encoded_predicate', passed=True, inputs=[])
        self.assertCode('duplicate', lambda: E.make_claim('q', 2, origin='model_proposal', checks=[check, check]))

    def test_receipts_pin_subject_and_exact_inputs(self):
        p, other = premise('p'), premise('other')
        check = E.receipt(subject=3, predicate='p+1', scope='encoded_derivation',
                          passed=True, inputs=[E.reference(p)])
        self.assertCode('receipt', lambda: E.make_claim('q', 4, origin='derived',
                                                       checks=[check], dependencies=[E.reference(p)]))
        self.assertCode('receipt', lambda: E.make_claim('q', 3, origin='derived',
                                                       checks=[check], dependencies=[E.reference(p), E.reference(other)]))

    def test_failed_check_is_not_automatic_refutation(self):
        check = E.receipt(subject='A', predicate='is true', scope='encoded_predicate', passed=False, inputs=[])
        row = E.make_claim('p', 'A', origin='model_proposal', checks=[check])
        self.assertEqual(E.evaluate([row])['p']['status'], 'unknown')

    def test_no_mutation_and_no_custom_json_or_unbounded_shapes(self):
        row = premise(value={'items': [1, 2]})
        copy_row = copy.deepcopy(row)
        E.evaluate([row])
        self.assertEqual(row, copy_row)
        self.assertCode('json', lambda: premise(value=float('nan')))
        self.assertCode('json', lambda: premise(value=(1, 2)))
        self.assertCode('json', lambda: premise(value='\ud800'))
        self.assertCode('limit', lambda: premise(value='x' * (E.MAX_BYTES + 1)))
        deep = 0
        for _ in range(E.MAX_DEPTH + 1):
            deep = [deep]
        self.assertCode('limit', lambda: premise(value=deep))

    def test_tampering_and_unknown_fields_rejected(self):
        row = premise()
        row['origin'] = 'owner_premise'
        self.assertCode('hash', lambda: E.validate_claim(row))
        row = premise()
        row['confidence'] = 1
        self.assertCode('schema', lambda: E.validate_claim(row))


class ContextManifest(unittest.TestCase):
    def pack(self, claims, **kw):
        args = {'required': [], 'optional': [], 'budget': 100000,
                'prefix': 'PROGRAM\nSTATEMENT', 'suffix': 'ANSWER FORMAT',
                'fixed_parts': ['SYSTEM', '{"answer":"integer"}']}
        args.update(kw)
        return E.context_manifest(claims, **args)

    def test_exact_budget_boundary_counts_system_schema_and_separators(self):
        p = premise(value='café')
        packed = self.pack([p], required=['p'])
        actual = len(packed['prompt'].encode()) + len(b'SYSTEM') + len(b'{"answer":"integer"}')
        self.assertEqual(packed['used'], actual)
        self.assertEqual(self.pack([p], required=['p'], budget=actual)['used'], actual)
        with self.assertRaises(E.EpistemicError) as raised:
            self.pack([p], required=['p'], budget=actual - 1)
        self.assertEqual(raised.exception.code, 'required_context_overflow')
        self.assertEqual(raised.exception.details['required'][0]['sha256'], p['sha256'])

    def test_fixed_overhead_alone_can_overflow(self):
        with self.assertRaises(E.EpistemicError) as raised:
            self.pack([], fixed_parts=['x' * 1000], budget=999)
        self.assertEqual(raised.exception.code, 'required_context_overflow')
        self.assertGreater(raised.exception.details['fixed_size'], 999)

    def test_huge_required_row_fails_instead_of_silent_drop(self):
        p = premise(value='x' * 50000)
        with self.assertRaises(E.EpistemicError) as raised:
            self.pack([p], required=['p'], budget=6000)
        self.assertEqual(raised.exception.code, 'required_context_overflow')
        self.assertEqual(raised.exception.details['required'][0]['id'], 'p')
        self.assertNotIn('lower-weight', str(raised.exception))

    def test_required_closure_not_priorities_decides_mandatory(self):
        p = premise('p')
        q = derived('q', 2, [p])
        packed = self.pack([p, q], required=['q'], priorities={'p': -99999})
        self.assertEqual([row['id'] for row in packed['included']], ['p', 'q'])
        self.assertTrue(all(row['required'] for row in packed['included']))
        self.assertIn('model_proposal', packed['prompt'])
        self.assertIn('not_established', packed['prompt'])
        self.assertIn('conditional', packed['prompt'])

    def test_optional_atomic_closure_and_named_omission(self):
        p, q = premise('p', 'x' * 5000), premise('q', 'short')
        packed = self.pack([p, q], optional=['p', 'q'], budget=1500, priorities={'p': 10})
        self.assertEqual([row['id'] for row in packed['included']], ['q'])
        self.assertEqual(packed['omitted'][0]['id'], 'p')
        self.assertEqual(packed['omitted'][0]['sha256'], p['sha256'])
        self.assertEqual(packed['omitted'][0]['reason'], 'optional_context_overflow')

    def test_optional_dependency_chain_is_atomic(self):
        p = premise('p', 'x' * 5000)
        q = derived('q', 2, [p])
        packed = self.pack([p, q], optional=['q'], budget=1500)
        self.assertEqual(packed['included'], [])
        self.assertEqual([row['id'] for row in packed['omitted']], ['p', 'q'])

    def test_order_is_deterministic_across_input_order(self):
        p, q = premise('p'), premise('q')
        first = self.pack([p, q], optional=['p', 'q'])
        second = self.pack([q, p], optional=['q', 'p'])
        self.assertEqual(first, second)

    def test_conflicting_alternative_cannot_be_hidden_from_required_context(self):
        p, q = premise('p', 'A'), premise('q', 'not A')
        disagreement = {'id': 'opposes', 'claims': [E.reference(p), E.reference(q)]}
        packed = self.pack([p, q], required=['p'], disagreements=[disagreement])
        self.assertEqual([row['id'] for row in packed['included']], ['p', 'q'])
        self.assertTrue(all(row['required'] for row in packed['included']))
        self.assertIn('contested', packed['prompt'])

    def test_bytes_and_characters_are_labelled_and_exact(self):
        p = premise(value='é')
        chars = self.pack([p], required=['p'], unit='characters')
        byte = self.pack([p], required=['p'], unit='utf8_bytes')
        self.assertEqual(byte['used'], chars['used'] + 1)
        self.assertEqual(chars['unit'], 'characters')
        self.assertEqual(byte['unit'], 'utf8_bytes')

    def test_duplicate_or_unknown_context_ids_fail(self):
        p = premise()
        for kw in ({'required': ['p', 'p']}, {'required': ['p'], 'optional': ['p']}, {'required': ['unknown']}):
            with self.assertRaises(E.EpistemicError):
                self.pack([p], **kw)


if __name__ == '__main__':
    unittest.main()
