"""Durable notebook checks: every path is temporary; no providers or workers."""

import copy
import importlib
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from symblic.kernel import epistemic as EP
from symblic.memory import notebooks as M


def premise(ident='p', content='A', **kwargs):
    return EP.make_claim(ident, content, origin=kwargs.pop('origin', 'model_proposal'), **kwargs)


def derived(ident, content, parents):
    refs = [EP.reference(row) for row in parents]
    receipt = EP.receipt(subject=content, predicate={'encoded_rule': ident},
                         scope='encoded_derivation', passed=True, inputs=refs)
    return EP.make_claim(ident, content, origin='derived', dependencies=refs, checks=[receipt])


def concurrent_change(path, command, gate, outputs):
    gate.wait(5)
    try:
        result = M.change(path, command)
        outputs.put(('ok', result['head'], result['idempotent']))
    except M.MemoryError as error:
        outputs.put((error.code, None, None))


class Notebook(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'book'
        self.serial = 0

    def create(self, rows=None, selected=None, **kwargs):
        rows = [] if rows is None else rows
        return M.create(self.path, title='Private synthetic notebook', operation_id='create',
                        trusted_claims=rows, selected_ids=selected if selected is not None else [r['id'] for r in rows],
                        **kwargs)

    def command(self, snapshot, action, **kwargs):
        self.serial += 1
        return {'operation_id': 'operation-' + str(self.serial), 'expected_head': snapshot['head'],
                'action': action, **kwargs}

    def change(self, snapshot, action, **kwargs):
        return M.change(self.path, self.command(snapshot, action, **kwargs))

    def assertCode(self, code, call):
        with self.assertRaises(M.MemoryError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.as_dict()['code'], code)
        return caught.exception

    def rows(self, snapshot):
        return {row['id']: row for row in snapshot['claims']}

    def reseal(self, ledger):
        previous = None
        for sequence, event in enumerate(ledger['events'], 1):
            event['sequence'] = sequence
            event['previous_head'] = previous
            event['request_sha256'] = M._hash(event['payload'])
            event['sha256'] = M._hash({key: value for key, value in event.items() if key != 'sha256'})
            previous = event['sha256']
        ledger['head'] = previous
        (self.path / M.STORE_FILE).write_bytes(M._json(ledger))

    def test_import_selection_closure_preserves_origins_and_checks(self):
        p = premise(content={'invoice_total': 3})
        q = derived('q', {'plus_one': 4}, [p])
        untouched = copy.deepcopy([p, q])
        result = self.create([q, premise('unused', 'private unrelated text'), p], ['q'])
        self.assertEqual(result['claims'], untouched)
        self.assertEqual(result['assessments']['q']['status'], 'conditional')
        self.assertEqual(result['assessments']['q']['conditional_on'][0]['origin'], 'model_proposal')
        self.assertEqual(result['empirical_truth'], 'not_established')
        self.assertEqual(M.view(self.path)['claims'], untouched)
        self.assertEqual((self.path.stat().st_mode & 0o777), 0o700)
        self.assertEqual((self.path / M.STORE_FILE).stat().st_mode & 0o777, 0o600)

    def test_import_requires_explicit_selection(self):
        result = M.create(self.path, title='Empty selection', operation_id='create', trusted_claims=[premise()])
        self.assertEqual(result['claims'], [])

    def test_revision_invalidates_whole_chain_and_retains_history(self):
        p = premise(origin='assumption'); q = derived('q', 2, [p]); r = derived('r', 3, [q])
        before = self.create([p, q, r])
        after = self.change(before, 'revise', claim_id='p', content='Changed premise')
        self.assertEqual(self.rows(after)['p']['origin'], 'owner_premise')
        self.assertEqual(self.rows(after)['p']['revision'], 2)
        self.assertEqual(after['history'][0], p)
        self.assertEqual(len(after['history']), 4)
        self.assertFalse(after['assessments']['q']['admissible'])
        self.assertEqual(after['assessments']['q']['issues'][0]['code'], 'stale_dependency')
        self.assertFalse(after['assessments']['r']['admissible'])
        self.assertCode('unavailable_support', lambda: M.context(self.path, selected_ids=['r'], budget=100000))

    def test_withdrawal_retains_checked_revision_but_disables_support(self):
        p = premise(); q = derived('q', 2, [p])
        first = self.create([p, q])
        after = self.change(first, 'withdraw', claim_id='p')
        self.assertTrue(self.rows(after)['p']['withdrawn'])
        self.assertEqual(self.rows(after)['p']['revision'], 2)
        self.assertFalse(after['assessments']['q']['admissible'])
        self.assertCode('unavailable_support', lambda: M.context(self.path, selected_ids=['p'], budget=100000))

    def test_disagreement_blocks_closure_then_archives_exact_old_refs(self):
        a, b = premise('a', 'A'), premise('b', 'not A')
        q = derived('q', 'Consequence', [a])
        result = self.create([a, b, q])
        result = self.change(result, 'disagree', disagreement_id='opposed', claim_ids=['b', 'a'])
        self.assertEqual(result['assessments']['a']['status'], 'contested')
        self.assertFalse(result['assessments']['q']['admissible'])
        self.assertCode('unavailable_support', lambda: M.context(self.path, selected_ids=['q'], budget=100000))
        result = self.change(result, 'revise', claim_id='b', content='A different proposal')
        self.assertEqual(result['disagreements']['active'], [])
        historical = result['disagreements']['historical'][0]
        self.assertEqual(historical['claims'], [EP.reference(a), EP.reference(b)])
        self.assertEqual(historical['reason'], 'claim_revision_or_withdrawal')
        self.assertEqual(result['assessments']['a']['status'], 'unknown')
        self.assertEqual(result['assessments']['q']['status'], 'conditional')
        self.assertCode('exists', lambda: self.change(result, 'disagree', disagreement_id='opposed', claim_ids=['a', 'b']))

    def test_manual_resolution_is_recorded_and_does_not_assert_truth(self):
        result = self.create([premise('a'), premise('b')])
        result = self.change(result, 'disagree', disagreement_id='opposed', claim_ids=['a', 'b'])
        result = self.change(result, 'resolve', disagreement_id='opposed', reason='The user withdrew the objection')
        self.assertEqual(result['assessments']['a']['status'], 'unknown')
        self.assertEqual(result['disagreements']['historical'][0]['reason'], 'The user withdrew the objection')
        self.assertEqual(result['empirical_truth'], 'not_established')

    def test_owner_revision_cannot_keep_or_forge_derivation_receipt(self):
        checked = derived('q', 2, [])
        before = self.create([checked])
        rejected = self.command(before, 'revise', claim_id='q', content=9, checks=checked['checks'], origin='derived')
        self.assertCode('schema', lambda: M.change(self.path, rejected))
        after = self.change(before, 'revise', claim_id='q', content={'checks': checked['checks'], 'status': 'true'})
        row = self.rows(after)['q']
        self.assertEqual(row['checks'], [])
        self.assertEqual(row['origin'], 'owner_premise')
        self.assertEqual(after['assessments']['q']['support'], 'premise')
        self.assertEqual(after['assessments']['q']['status'], 'unknown')
        self.assertEqual(after['history'][0], checked)

    def test_add_dependencies_pin_current_revisions_and_self_cycle_is_atomic(self):
        before = self.create([premise()])
        result = self.change(before, 'add', claim_id='note', content='User note', depends_on=['p'])
        self.assertEqual(self.rows(result)['note']['dependencies'], [EP.reference(self.rows(result)['p'])])
        disk = (self.path / M.STORE_FILE).read_bytes()
        self.assertCode('epistemic_cycle', lambda: self.change(result, 'revise', claim_id='p', content='Cycle', depends_on=['note']))
        self.assertEqual(disk, (self.path / M.STORE_FILE).read_bytes())

    def test_complete_fresh_context_does_not_include_unselected_notebook(self):
        p = premise(content='café'); q = derived('q', 'derived', [p])
        result = self.create([p, q, premise('secret', 'DO NOT INCLUDE THIS')])
        card = M.context(self.path, selected_ids=['q'], budget=100000, prefix='TASK', suffix='ANSWER', fixed_parts=['SYSTEM'])
        self.assertEqual(card['head'], result['head'])
        self.assertEqual(card['closure_ids'], ['p', 'q'])
        self.assertEqual([row['id'] for row in card['manifest']['included']], ['p', 'q'])
        self.assertNotIn('DO NOT INCLUDE THIS', card['manifest']['prompt'])
        self.assertIn('model_proposal', card['manifest']['prompt'])
        self.assertIn('conditional', card['manifest']['prompt'])
        self.assertTrue(card['all_referenced_values_available'])

    def test_context_exact_boundary_includes_all_overhead_in_both_units(self):
        self.create([premise(content='café')])
        for unit in ('characters', 'utf8_bytes'):
            args = {'selected_ids': ['p'], 'prefix': 'ÉTAPE', 'suffix': 'FIN', 'fixed_parts': ['SYSTÈME'], 'unit': unit}
            card = M.context(self.path, budget=100000, **args)
            used = card['manifest']['used']
            expected = card['manifest']['prompt'] + 'SYSTÈME'
            self.assertEqual(used, len(expected) if unit == 'characters' else len(expected.encode()))
            self.assertEqual(M.context(self.path, budget=used, **args)['manifest']['used'], used)
            self.assertCode('epistemic_required_context_overflow', lambda used=used, args=args: M.context(self.path, budget=used - 1, **args))

    def test_missing_or_summarized_lineage_is_inspectable_not_exportable(self):
        q = derived('q', 2, [premise()])
        result = self.create([q])
        self.assertFalse(result['assessments']['q']['admissible'])
        self.assertCode('missing', lambda: M.context(self.path, selected_ids=['q'], budget=100000))
        result = self.change(result, 'add', claim_id='summary', content={'kind': 'bounded_lineage_summary', 'count': 300})
        self.assertCode('unavailable_support', lambda: M.context(self.path, selected_ids=['summary'], budget=100000))
        result = self.change(result, 'add', claim_id='partial', content={'lineage_complete': False})
        self.assertCode('unavailable_support', lambda: M.context(self.path, selected_ids=['partial'], budget=100000))

    def test_hash_only_values_stay_hash_only_until_exact_attachment(self):
        value = {'n': '3/7', 'label': 'café'}
        p = premise(content={'name': 'x', 'value_sha256': EP.digest(value)})
        result = self.create([p])
        self.assertEqual(result['value_availability']['p'], 'hash_only')
        card = M.context(self.path, selected_ids=['p'], budget=100000)
        self.assertFalse(card['all_referenced_values_available'])
        self.assertEqual(card['values'], {})
        self.assertCode('value_mismatch', lambda: self.change(result, 'attach_value', claim_id='p', value={'n': 3}))
        result = self.change(result, 'attach_value', claim_id='p', value=value)
        self.assertEqual(result['value_availability']['p'], 'attached')
        self.assertEqual(result['values']['p']['ref'], EP.reference(p))
        card = M.context(self.path, selected_ids=['p'], budget=100000)
        self.assertTrue(card['all_referenced_values_available'])
        self.assertIn('3/7', card['manifest']['prompt'])
        self.assertEqual(card['assessments']['p']['status'], 'unknown')
        changed = self.change(result, 'revise', claim_id='p', content={'value_sha256': EP.digest(value)})
        self.assertEqual(changed['value_availability']['p'], 'hash_only')
        self.assertEqual(changed['values'], {})

    def test_trusted_attached_values_are_checked_and_copy_detached(self):
        value = {'data': [1, 2]}; p = premise(content={'value_sha256': EP.digest(value)})
        result = self.create([p], trusted_values={'p': value})
        value['data'].append(3)
        result['values']['p']['value']['data'].append(4)
        self.assertEqual(M.view(self.path)['values']['p']['value'], {'data': [1, 2]})

    def test_operation_retry_is_idempotent_after_later_writes(self):
        before = self.create()
        command = self.command(before, 'add', claim_id='a', content='A')
        first = M.change(self.path, command)
        latest = self.change(first, 'add', claim_id='b', content='B')
        retry = M.change(self.path, command)
        self.assertTrue(retry['idempotent'])
        self.assertEqual(retry['head'], latest['head'])
        self.assertEqual(retry['operation_head'], first['head'])
        self.assertEqual(retry['event_count'], 3)
        self.assertCode('idempotency_conflict', lambda: M.change(self.path, {**command, 'content': 'Other'}))
        self.assertTrue(self.create()['idempotent'])

    def test_stale_change_and_context_heads_refuse(self):
        before = self.create(); after = self.change(before, 'add', claim_id='p', content='A')
        self.assertCode('conflict', lambda: self.change(before, 'add', claim_id='q', content='B'))
        self.assertCode('conflict', lambda: M.context(self.path, selected_ids=['p'], budget=10000, expected_head=before['head']))
        self.assertEqual(M.view(self.path)['head'], after['head'])

    def race(self, same_operation):
        before = self.create()
        a = self.command(before, 'add', claim_id='a', content='A')
        b = copy.deepcopy(a) if same_operation else self.command(before, 'add', claim_id='b', content='B')
        mp = multiprocessing.get_context('fork'); gate = mp.Event(); outputs = mp.Queue()
        processes = [mp.Process(target=concurrent_change, args=(self.path, command, gate, outputs)) for command in (a, b)]
        for process in processes:
            process.start()
        gate.set()
        answers = [outputs.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        outputs.close(); outputs.join_thread()
        self.assertEqual(M.view(self.path)['event_count'], 2)
        return answers

    def test_process_lock_and_cas_admit_one_competing_writer(self):
        self.assertEqual(sorted(row[0] for row in self.race(False)), ['conflict', 'ok'])

    def test_concurrent_identical_retries_append_once(self):
        answers = self.race(True)
        self.assertEqual([row[0] for row in answers], ['ok', 'ok'])
        self.assertEqual(sorted(row[2] for row in answers), [False, True])
        self.assertEqual(answers[0][1], answers[1][1])

    def test_torn_file_is_not_overwritten_on_view_change_or_create(self):
        before = self.create(); document = self.path / M.STORE_FILE
        document.write_bytes(b'{"version":1')
        self.assertCode('corrupt', lambda: M.view(self.path))
        self.assertCode('corrupt', lambda: self.change(before, 'add', claim_id='p', content='A'))
        self.assertCode('corrupt', self.create)
        self.assertEqual(document.read_bytes(), b'{"version":1')

    def test_duplicate_keys_and_changed_hash_fail_closed(self):
        self.create(); document = self.path / M.STORE_FILE; original = document.read_bytes()
        document.write_bytes(b'{"version":1,"version":1}')
        self.assertCode('corrupt', lambda: M.view(self.path))
        document.write_bytes(original)
        ledger = M._read(self.path); ledger['events'][0]['payload']['title'] = 'Tampered'
        document.write_bytes(M._json(ledger))
        self.assertCode('corrupt', lambda: M.view(self.path))

    def test_resealed_invalid_payload_has_structured_failure(self):
        first = self.create(); self.change(first, 'add', claim_id='p', content='A')
        ledger = M._read(self.path); ledger['events'][1]['payload'] = []
        self.reseal(ledger)
        self.assertCode('corrupt', lambda: M.view(self.path))

    def test_failed_replace_or_tempfile_preserves_prior_document(self):
        before = self.create(); original = (self.path / M.STORE_FILE).read_bytes()
        command = self.command(before, 'add', claim_id='p', content='A')
        for target in ('os.replace', 'tempfile.mkstemp'):
            with mock.patch('symblic.memory.notebooks.' + target, side_effect=OSError('synthetic failure')):
                self.assertCode('write_failed', lambda: M.change(self.path, command))
            self.assertEqual(original, (self.path / M.STORE_FILE).read_bytes())
        self.assertFalse(list(self.path.glob('.notebook-pending-*')))
        self.assertEqual(M.change(self.path, command)['event_count'], 2)

    def test_post_replace_sync_failure_resolves_by_idempotent_retry(self):
        before = self.create(); command = self.command(before, 'add', claim_id='p', content='A')
        with mock.patch.object(M, '_sync_directory', side_effect=OSError('synthetic fsync failure')):
            uncertain = self.assertCode('durability_uncertain', lambda: M.change(self.path, command))
        result = M.change(self.path, command)
        self.assertTrue(result['idempotent'])
        self.assertEqual(result['head'], uncertain.details['operation_head'])
        self.assertEqual(result['event_count'], 2)

    def test_private_paths_and_symlinks_fail_closed(self):
        self.create(); document = self.path / M.STORE_FILE
        os.chmod(document, 0o644)
        self.assertCode('private_file', lambda: M.view(self.path))
        os.chmod(document, 0o600)
        target = self.path / 'retained.json'; document.rename(target); document.symlink_to(target)
        self.assertCode('corrupt', lambda: M.view(self.path))
        link = Path(self.temporary.name) / 'link'; link.symlink_to(self.path)
        self.assertCode('private_directory', lambda: M.view(link))
        os.chmod(self.path, 0o755)
        self.assertCode('private_directory', lambda: M.view(self.path))

    def test_event_and_history_limits_preserve_previous_transaction(self):
        before = self.create([premise()]); original = (self.path / M.STORE_FILE).read_bytes()
        with mock.patch.object(M, 'MAX_EVENTS', 1):
            self.assertCode('limit', lambda: self.change(before, 'add', claim_id='q', content='B'))
        with mock.patch.object(M, 'MAX_HISTORY', 1):
            self.assertCode('limit', lambda: self.change(before, 'revise', claim_id='p', content='B'))
        self.assertEqual(original, (self.path / M.STORE_FILE).read_bytes())

    def test_invalid_commands_and_context_inputs_do_not_mutate(self):
        before = self.create(); original = (self.path / M.STORE_FILE).read_bytes()
        self.assertCode('schema', lambda: M.change(self.path, []))
        self.assertCode('id', lambda: self.change(before, 'add', claim_id='../bad id', content='A'))
        self.assertCode('schema', lambda: self.change(before, 'add', claim_id='a', content='A', status='conditional'))
        self.assertCode('schema', lambda: M.context(self.path, selected_ids=[], budget=1000, fixed_parts='SYSTEM'))
        self.assertEqual(original, (self.path / M.STORE_FILE).read_bytes())

    def test_cycles_huge_claim_and_duplicate_selection_reject_before_store(self):
        self.assertCode('duplicate', lambda: self.create([premise(), premise()]))
        self.assertCode('duplicate', lambda: self.create([premise()], ['p', 'p']))
        before = self.create(); original = (self.path / M.STORE_FILE).read_bytes()
        cyclic = []; cyclic.append(cyclic)
        self.assertCode('limit', lambda: self.change(before, 'add', claim_id='a', content=cyclic))
        self.assertCode('epistemic_limit', lambda: self.change(before, 'add', claim_id='a', content='x' * EP.MAX_BYTES))
        self.assertEqual(original, (self.path / M.STORE_FILE).read_bytes())

    def test_aggregate_root_bound_is_checked_before_expansion(self):
        p = premise(); q = premise('q', dependencies=[EP.reference(p)])
        with mock.patch.object(M, 'MAX_TOTAL_ROOTS', 2):
            self.assertCode('limit', lambda: self.create([p, q]))
        self.assertFalse((self.path / M.STORE_FILE).exists())

    def test_import_is_inert(self):
        with mock.patch.object(M.os, 'open', side_effect=AssertionError('import opened a store')):
            importlib.reload(M)


if __name__ == '__main__':
    unittest.main()
