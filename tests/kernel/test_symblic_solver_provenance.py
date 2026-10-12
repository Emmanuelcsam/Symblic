"""Pure solver-origin contracts and unchanged notebook behavior; no solver/model calls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symblic.kernel import epistemic as E
from symblic.memory import notebooks as M


def legacy():
    path = Path(__file__).parent / 'fixtures/symblic_epistemic_baseline_e5aa249c.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == 'e5aa249c67c8edcb3f418956c2afa4b084456abfd44644db1b319104835201f0'
    spec = importlib.util.spec_from_file_location('_solver_legacy_ep', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD = legacy()


def reseal(claim, **fields):
    row = copy.deepcopy({**claim, **fields})
    row['sha256'] = E.digest({key: value for key, value in row.items() if key != 'sha256'})
    return row


def solver(ident='s', content=None, parents=(), **kwargs):
    content = {'value_sha256': E.digest({'#q': '1/2'}), 'constructor': {'outcome_id': 'synthetic-checked-1'}} \
        if content is None else content
    refs = [E.reference(row) for row in parents]
    checks = kwargs.pop('checks', [E.receipt(subject=content, predicate={'encoded': 'x + x = 1'},
                         scope='encoded_predicate', passed=True, inputs=refs)])
    return E.make_claim(ident, content, origin='solver_proposal', dependencies=refs, checks=checks, **kwargs)


def derive(ident, parents):
    content = {'encoded_conclusion': ident}
    refs = [E.reference(row) for row in parents]
    check = E.receipt(subject=content, predicate={'encoded_rule': 'synthetic_native_check'},
                      scope='encoded_derivation', passed=True, inputs=refs)
    return E.make_claim(ident, content, origin='derived', dependencies=refs, checks=[check])


class SolverSchema(unittest.TestCase):
    def refuse(self, code, call):
        with self.assertRaises(E.EpistemicError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_legacy_claim_receipt_bytes_and_formats_are_exact(self):
        for origin in sorted(OLD.ORIGINS):
            for status in ('unknown', 'contested', 'refuted'):
                content = {'rational': {'#q': '1/2'}, 'text': 'café 日本', 'flags': [False, None]}
                check = E.receipt(subject=content, predicate='finite predicate', scope='encoded_predicate', passed=True, inputs=[])
                self.assertEqual(check, OLD.receipt(subject=content, predicate='finite predicate',
                                                   scope='encoded_predicate', passed=True, inputs=[]))
                args = {'origin': origin, 'checks': [check], 'status': status}
                expected = OLD.make_claim('old', content, **args)
                for make in (E.make_claim, E._make_claim_reference):
                    self.assertEqual(json.dumps(make('old', content, **args), ensure_ascii=False),
                                     json.dumps(expected, ensure_ascii=False))
                self.assertEqual(E._validate_claim_once(expected), expected)
                self.assertEqual(E._validate_claim_reference(expected), expected)
        self.assertEqual(E.VERSION, 1)
        self.assertEqual(E.ORIGINS_V1, OLD.ORIGINS)
        self.assertEqual(E.ORIGINS, OLD.ORIGINS | {'solver_proposal'})

    def test_version_origin_matrix_in_both_validation_paths(self):
        for origin in sorted(E.ORIGINS):
            base = E.make_claim('row', {'v': 1}, origin=origin)
            for version in (0, 1, 2, 3, True, False, '2', 2.0):
                row = {**base, 'version': version} if type(version) is float else reseal(base, version=version)
                valid = type(version) is int and version == (2 if origin == 'solver_proposal' else 1)
                for validate in (E.validate_claim, E._validate_claim_reference):
                    if valid:
                        self.assertEqual(validate(row), row)
                    else:
                        self.refuse('json' if type(version) is float else 'version',
                                    lambda row=row, validate=validate: validate(row))
                if valid:
                    self.assertEqual(E._validate_claim_once(row), row)
                else:
                    with self.assertRaises(E._Decline):
                        E._validate_claim_once(row)

    def test_solver_fast_and_reference_paths_agree_and_detach(self):
        p = E.make_claim('a', 'input', origin='assumption')
        row = solver(parents=[p])
        args = dict(origin=row['origin'], revision=row['revision'], dependencies=row['dependencies'],
                    checks=row['checks'], status=row['status'], withdrawn=row['withdrawn'])
        with patch.object(E, '_make_claim_reference', side_effect=AssertionError('unexpected fallback')):
            self.assertEqual(E.make_claim(row['id'], row['content'], **args), row)
        self.assertEqual(E._make_claim_reference(row['id'], row['content'], **args), row)
        with patch.object(E, '_validate_claim_reference', side_effect=AssertionError('unexpected fallback')):
            detached = E.validate_claim(row)
        detached['content']['constructor']['outcome_id'] = 'changed'
        detached['checks'][0]['predicate']['encoded'] = 'changed'
        self.assertEqual(row['content']['constructor']['outcome_id'], 'synthetic-checked-1')
        self.assertEqual(E.validate_claim(row), row)

    def test_receipt_version_two_is_never_admitted(self):
        row = solver()
        check = copy.deepcopy(row['checks'][0]); check['version'] = 2
        check['id'] = E.digest({key: value for key, value in check.items() if key != 'id'})
        poisoned = reseal(row, checks=[check])
        for validate in (E.validate_claim, E._validate_claim_reference):
            self.refuse('version', lambda validate=validate: validate(poisoned))
        with self.assertRaises(E._Decline):
            E._validate_claim_once(poisoned)

    def test_derivation_receipt_forbidden_even_exact_failed_or_zero_premise(self):
        p = E.make_claim('a', 'input', origin='assumption')
        for parents in ([], [p]):
            for passed in (False, True):
                refs = [E.reference(row) for row in parents]
                check = E.receipt(subject='answer', predicate='author encoded derivation',
                                  scope='encoded_derivation', passed=passed, inputs=refs)
                args = dict(origin='solver_proposal', dependencies=refs, checks=[check])
                for make in (E.make_claim, E._make_claim_reference):
                    self.refuse('receipt', lambda make=make: make('s', 'answer', **args))
                with self.assertRaises(E._Decline):
                    E._make_claim_once('s', 'answer', 'solver_proposal', 1, refs, [check], 'unknown', False)
                row = reseal(solver(content='answer', parents=parents), checks=[check])
                for validate in (E.validate_claim, E._validate_claim_reference):
                    self.refuse('receipt', lambda validate=validate: validate(row))
                with self.assertRaises(E._Decline):
                    E._validate_claim_once(row)

    def test_schema_predicate_checks_do_not_establish_truth_or_uniqueness(self):
        for scope in ('encoded_schema', 'encoded_predicate'):
            for passed in (False, True):
                # Content metadata is data, not an assessment authority.
                content = {'value': 7, 'unique': True, 'solver_says': 'proven', 'confidence': 1}
                check = E.receipt(subject=content, predicate='finite predicate', scope=scope, passed=passed, inputs=[])
                row = solver(content=content, checks=[check])
                assessment = E.evaluate([row])['s']
                self.assertEqual((assessment['status'], assessment['support'], assessment['empirical_truth']),
                                 ('unknown', 'premise', 'not_established'))
                self.assertEqual(assessment['derivation_receipt_ids'], [])
                self.assertEqual(assessment['conditional_on'][0]['origin'], 'solver_proposal')
                self.assertNotIn('unique', assessment)
                self.assertNotIn('confidence', assessment)
        self.refuse('status', lambda: solver(status='conditional'))

    def test_origin_and_distinct_outcome_ids_cannot_collapse_to_model_agreement(self):
        row = solver()
        model = E.make_claim('s', row['content'], origin='model_proposal', checks=row['checks'])
        other = solver(content={**row['content'], 'constructor': {'outcome_id': 'synthetic-checked-2'}})
        self.assertEqual(model['content_sha256'], row['content_sha256'])
        self.assertNotEqual(model['sha256'], row['sha256'])
        self.assertNotEqual(other['sha256'], row['sha256'])
        first, second = solver('a', 0), solver('b', 1)
        assessed = E.evaluate([first, second])
        self.assertEqual([r['status'] for r in assessed.values()], ['unknown', 'unknown'])
        self.assertEqual([r['conditional_on'][0]['origin'] for r in assessed.values()], ['solver_proposal'] * 2)

    def test_wrong_receipt_subject_dependency_and_hash_refuse(self):
        p = E.make_claim('p', 1, origin='assumption')
        row = solver(parents=[p])
        for check in (E.receipt(subject='wrong', predicate='p', scope='encoded_predicate', passed=True, inputs=[]),
                      E.receipt(subject=row['content'], predicate='p', scope='encoded_predicate', passed=True,
                                inputs=[{**E.reference(p), 'revision': 2}])):
            bad = reseal(row, checks=[check])
            self.refuse('receipt', lambda: E.validate_claim(bad))
        self.refuse('hash', lambda: E.validate_claim({**row, 'content': {'changed': True}}))
        self.refuse('hash', lambda: E.validate_claim({**row, 'sha256': '0' * 64}))

    def test_new_origin_retains_byte_depth_and_non_json_bounds(self):
        deep = 0
        for _ in range(E.MAX_DEPTH + 1):
            deep = [deep]
        for value in ('\\' * (E.MAX_BYTES // 2 + 1), deep, E._END, [E._END], {'a': E._END}, 2**4096):
            with self.assertRaises(E.EpistemicError):
                solver(content=value)
        shared = ['x']
        row = solver(content={'a': shared, 'b': shared})
        self.assertIs(row['content']['a'], row['content']['b'])
        self.assertIsNot(row['content']['a'], shared)

    def test_old_reader_refuses_solver_claim_instead_of_misclassifying_it(self):
        with self.assertRaises(OLD.EpistemicError) as caught:
            OLD.validate_claim(solver())
        self.assertEqual(caught.exception.code, 'version')


class SolverSupport(unittest.TestCase):
    def chain(self):
        p = E.make_claim('a', {'unit': 'metres'}, origin='assumption')
        s = solver(parents=[p]); q = derive('q', [s]); r = derive('r', [q])
        return p, s, q, r

    def test_derived_support_retains_solver_and_input_roots(self):
        rows = self.chain(); assessed = E.evaluate(list(rows))
        self.assertEqual(assessed['s']['status'], 'unknown')
        self.assertEqual(assessed['s']['support'], 'premise')
        self.assertEqual(assessed['r']['status'], 'conditional')
        self.assertEqual([r['origin'] for r in assessed['r']['conditional_on']], ['assumption', 'solver_proposal'])
        self.assertEqual(assessed['r']['empirical_truth'], 'not_established')

    def test_changed_or_withdrawn_input_invalidates_entire_chain(self):
        p, s, q, r = self.chain()
        for changed in (E.make_claim('a', {'unit': 'seconds'}, origin='assumption', revision=2),
                        E.make_claim('a', p['content'], origin='assumption', withdrawn=True)):
            result = E.evaluate([changed, s, q, r])
            self.assertFalse(result['s']['admissible'])
            self.assertFalse(result['q']['admissible'])
            self.assertFalse(result['r']['admissible'])
            self.assertEqual(result['s']['issues'][0]['code'], 'stale_dependency')

    def test_solver_revision_withdrawal_refutation_and_missing_input_are_unavailable(self):
        p, s, q, r = self.chain()
        for replacement in (solver(parents=[p], revision=2), solver(parents=[p], withdrawn=True),
                            solver(parents=[p], status='refuted')):
            result = E.evaluate([p, replacement, q, r])
            self.assertFalse(result['q']['admissible'])
            self.assertFalse(result['r']['admissible'])
            self.assertNotEqual(result['r']['status'], 'refuted')
        result = E.evaluate([s, q, r])
        self.assertEqual(result['s']['issues'][0]['code'], 'missing_dependency')
        self.assertFalse(result['r']['admissible'])

    def test_disagreement_retains_alternatives_without_logic_explosion(self):
        s = solver('s', 'A'); other = E.make_claim('other', 'not A', origin='model_proposal')
        q = derive('q', [s])
        conflict = [{'id': 'dispute', 'claims': [E.reference(s), E.reference(other)]}]
        result = E.evaluate([s, other, q], disagreements=conflict)
        self.assertEqual(result['s']['status'], 'contested')
        self.assertEqual(result['other']['status'], 'contested')
        self.assertFalse(result['q']['admissible'])
        self.assertEqual(result['q']['status'], 'unknown')
        self.assertEqual(result['s']['disagreements'][0]['id'], 'dispute')

    def test_context_keeps_complete_roots_and_exact_budget_and_manifest_v1(self):
        rows = list(self.chain())
        kwargs = dict(required=['r'], optional=[], prefix='TASK é', suffix='END', fixed_parts=['SYSTEM', '{}'])
        for unit in ('characters', 'utf8_bytes'):
            card = E.context_manifest(rows, budget=100000, unit=unit, **kwargs)
            self.assertEqual(card['version'], 1)
            self.assertEqual([r['id'] for r in card['included']], ['a', 'q', 'r', 's'])
            self.assertIn('solver_proposal', card['prompt'])
            exact = card['prompt'] + 'SYSTEM{}'
            self.assertEqual(card['used'], len(exact) if unit == 'characters' else len(exact.encode()))
            self.assertEqual(E.context_manifest(rows, budget=card['used'], unit=unit, **kwargs),
                             {**card, 'budget': card['used']})
            with self.assertRaises(E.EpistemicError) as caught:
                E.context_manifest(rows, budget=card['used'] - 1, unit=unit, **kwargs)
            self.assertEqual(caught.exception.code, 'required_context_overflow')

    def test_pure_context_reports_stale_support_instead_of_hiding_it(self):
        p, s, q, r = self.chain()
        p = E.make_claim('a', 'changed', origin='owner_premise', revision=2)
        card = E.context_manifest([p, s, q, r], required=['r'], optional=[], budget=100000,
                                  prefix='', suffix='', fixed_parts=[])
        self.assertIn('stale_dependency', card['prompt'])
        self.assertIn('unavailable', card['prompt'])

    def test_cycles_and_duplicate_ids_cannot_hide_under_new_origin(self):
        row = solver()
        for rows, code in (([row, row], 'duplicate'),
                           ([reseal(row, dependencies=[E.reference(row)])], 'cycle')):
            with self.assertRaises(E.EpistemicError) as caught:
                E.evaluate(rows)
            self.assertEqual(caught.exception.code, code)


class SolverNotebook(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'notebook'; self.serial = 0
        self.s = solver(); self.q = derive('q', [self.s])
        self.initial = M.create(self.path, title='Synthetic checked proposal', operation_id='create',
                                trusted_claims=[self.s, self.q], selected_ids=['q'])

    def change(self, snapshot, action, **fields):
        self.serial += 1
        return M.change(self.path, {'operation_id': f'op{self.serial}', 'expected_head': snapshot['head'],
                                   'action': action, **fields})

    def refuse_context(self, selected):
        with self.assertRaises(M.MemoryError) as caught:
            M.context(self.path, selected_ids=selected, budget=100000)
        self.assertEqual(caught.exception.code, 'unavailable_support')

    def test_import_view_and_fresh_context_preserve_mixed_versions_and_hash_only(self):
        view = M.view(self.path)
        self.assertEqual(view['claims'], self.initial['claims'])
        self.assertEqual({r['id']: r['version'] for r in view['claims']}, {'q': 1, 's': 2})
        card = M.context(self.path, selected_ids=['q'], budget=100000)
        self.assertEqual(card['closure_ids'], ['q', 's'])
        self.assertFalse(card['all_referenced_values_available'])
        self.assertEqual(card['values'], {})
        self.assertEqual(card['assessments']['q']['conditional_on'][0]['origin'], 'solver_proposal')

    def test_existing_version_one_notebook_reopens_without_rewriting_bytes(self):
        path = self.path.parent / 'legacy-notebook'
        old = OLD.make_claim('old', {'kept': 'exact'}, origin='model_proposal')
        with patch.object(M, 'EP', OLD):
            original = M.create(path, title='Original notebook', operation_id='original',
                                trusted_claims=[old], selected_ids=['old'])
        before = (path / M.STORE_FILE).read_bytes()
        reopened = M.view(path)
        for key in ('head', 'claims', 'history', 'assessments', 'disagreements'):
            self.assertEqual(reopened[key], original[key])
        self.assertEqual((path / M.STORE_FILE).read_bytes(), before)

    def test_owner_revision_returns_v1_clears_checks_and_invalidates_descendant(self):
        after = self.change(self.initial, 'revise', claim_id='s', content=self.s['content'])
        row = next(r for r in after['claims'] if r['id'] == 's')
        self.assertEqual((row['version'], row['origin'], row['revision'], row['checks']), (1, 'owner_premise', 2, []))
        self.assertIn(self.s, after['history'])
        self.assertFalse(after['assessments']['q']['admissible'])
        self.refuse_context(['q'])
        card = M.context(self.path, selected_ids=['s'], budget=100000)
        self.assertEqual(card['assessments']['s']['status'], 'unknown')

    def test_withdraw_preserves_solver_origin_as_v2_history_and_disables_context(self):
        after = self.change(self.initial, 'withdraw', claim_id='s')
        row = next(r for r in after['claims'] if r['id'] == 's')
        self.assertEqual((row['version'], row['origin'], row['revision']), (2, 'solver_proposal', 2))
        self.assertTrue(row['withdrawn'])
        self.assertEqual(row['checks'], self.s['checks'])
        self.assertIn(self.s, after['history'])
        self.refuse_context(['s']); self.refuse_context(['q'])

    def test_owner_command_cannot_forge_origin_or_keep_solver_receipts(self):
        before = (self.path / M.STORE_FILE).read_bytes()
        for action, fields in (('add', {'claim_id': 'new', 'content': 7, 'origin': 'solver_proposal'}),
                               ('revise', {'claim_id': 's', 'content': 7, 'checks': self.s['checks']})):
            with self.assertRaises(M.MemoryError) as caught:
                self.change(self.initial, action, **fields)
            self.assertEqual(caught.exception.code, 'schema')
            self.assertEqual((self.path / M.STORE_FILE).read_bytes(), before)

    def test_exact_attachment_does_not_upgrade_origin_or_truth(self):
        with self.assertRaises(M.MemoryError) as caught:
            self.change(self.initial, 'attach_value', claim_id='s', value={'#q': '2/1'})
        self.assertEqual(caught.exception.code, 'value_mismatch')
        after = self.change(self.initial, 'attach_value', claim_id='s', value={'#q': '1/2'})
        self.assertEqual(after['assessments']['s']['status'], 'unknown')
        self.assertEqual(after['assessments']['s']['empirical_truth'], 'not_established')
        self.assertEqual(after['values']['s']['ref'], E.reference(self.s))
        self.assertTrue(M.context(self.path, selected_ids=['s'], budget=100000)['all_referenced_values_available'])

    def test_disagreement_blocks_then_archives_exact_solver_revision(self):
        added = self.change(self.initial, 'add', claim_id='other', content='different answer')
        opposed = self.change(added, 'disagree', disagreement_id='conflict', claim_ids=['s', 'other'])
        self.refuse_context(['q'])
        after = self.change(opposed, 'revise', claim_id='s', content='revised owner statement')
        self.assertEqual(after['disagreements']['active'], [])
        self.assertIn(E.reference(self.s), after['disagreements']['historical'][0]['claims'])
        self.refuse_context(['q'])


class KernelSemanticIdentity(unittest.TestCase):
    def test_ep_format_stays_one_and_semantics_changes_kernel_identity(self):
        from symblic.kernel import language as S
        identity = S.kernel_id()
        self.assertEqual(identity['epistemic'], 1)
        self.assertEqual(identity['epistemic_semantics'], 2)
        self.assertEqual(E.SEMANTIC_VERSION, 2)
        self.assertEqual(identity['constructor_bridge'], 2)
        # Hold every current component fixed and verify the exact semantic pin.
        # Removing fields from today's runtime cannot reconstruct an older
        # deployment after other components (such as the JS adapter) change.
        parts = {k: v for k, v in identity.items() if k not in ('id', 'python')}
        self.assertEqual(hashlib.sha256(S.canon_json(parts).encode()).hexdigest()[:16], identity['id'])
        with patch.object(E, 'SEMANTIC_VERSION', 1):
            previous_semantics = S.kernel_id()
            expected_parts = {**parts, 'epistemic_semantics': 1}
            self.assertEqual({k: v for k, v in previous_semantics.items() if k not in ('id', 'python')},
                             expected_parts)
            self.assertEqual(previous_semantics['id'],
                             hashlib.sha256(S.canon_json(expected_parts).encode()).hexdigest()[:16])
            self.assertNotEqual(previous_semantics['id'], identity['id'])
        self.assertEqual(S.CANON_VERSION, 3)


if __name__ == '__main__':
    unittest.main()
