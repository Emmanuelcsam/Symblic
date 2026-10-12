"""Pure crash-prefix/reconnect protocol fixtures, without external dispatch."""
from copy import deepcopy
import json
import unittest

from symblic.experiments import protocols as P


def example(name):
    return next(row['example'] for row in P.catalog() if row['id'] == name)


def result(name, data):
    return P.run(name, data)['results']


def saga_event(kind, step, action, attempt, outcome=None):
    row = {'id': kind+action+attempt, 'kind': kind, 'step': step, 'action': action, 'attempt': attempt}
    if outcome is not None:
        row.update(outcome=outcome, evidence='3'*64)
    return row


class Acknowledgements(unittest.TestCase):
    name = 'revision-acknowledgements'

    def test_stale_ack_never_satisfies_updated_revision(self):
        data = example(self.name)
        r = result(self.name, data)
        self.assertFalse(r['all_current_revisions_acknowledged'])
        self.assertEqual(r['current_messages'][0]['missing'], ['Worker'])
        self.assertEqual(r['stale_acknowledgements'][0]['revision'], 1)
        receive = {'id': 'Receive2', 'kind': 'receive', 'message': 'Task', 'revision': 2,
                   'digest': '2'*64, 'recipient': 'Worker'}
        data['events'].append(receive)
        self.assertFalse(result(self.name, data)['all_current_revisions_acknowledged'])
        data['events'].append({**receive, 'id': 'Ack2', 'kind': 'ack', 'receipt': 'Receive2'})
        r = result(self.name, data)
        self.assertTrue(r['all_current_revisions_acknowledged'])
        self.assertEqual(len(r['stale_acknowledgements']), 1)

    def test_ack_requires_earlier_exact_receive_tuple(self):
        for change in ('missing', 'after', 'wrong_hash', 'wrong_recipient', 'wrong_revision', 'wrong_receipt'):
            data = example(self.name)
            if change == 'missing': del data['events'][1]
            if change == 'after': data['events'][1], data['events'][2] = data['events'][2], data['events'][1]
            if change == 'wrong_hash': data['events'][2]['digest'] = '0'*64
            if change == 'wrong_recipient': data['events'][2]['recipient'] = 'Other'
            if change == 'wrong_revision': data['events'][2]['revision'] = 2
            if change == 'wrong_receipt': data['events'][2]['receipt'] = 'Publish1'
            with self.subTest(change=change), self.assertRaises(ValueError):
                result(self.name, data)

    def test_duplicate_reconnect_is_idempotent_and_conflict_refuses(self):
        data = example(self.name)
        before = result(self.name, data)
        data['events'] += deepcopy(data['events'])
        after = result(self.name, data)
        self.assertEqual(after['current_messages'], before['current_messages'])
        self.assertEqual(after['acknowledgements'], before['acknowledgements'])
        self.assertEqual(after['replay']['duplicate_events'], 4)
        data['events'][-1]['digest'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'event_id_conflict'):
            result(self.name, data)
        data = example(self.name); row = deepcopy(data['events'][0]); row['revision'] = True
        data['events'].append(row)
        with self.assertRaisesRegex(ValueError, 'event_id_conflict'):
            result(self.name, data)

    def test_crash_after_receive_and_changed_recipient_set(self):
        data = example(self.name)
        data['events'] = data['events'][:2]
        self.assertFalse(result(self.name, data)['all_current_revisions_acknowledged'])
        data = example(self.name)
        data['events'][-1]['recipients'] = ['Worker', 'Second']
        self.assertEqual(result(self.name, data)['current_messages'][0]['missing'], ['Worker', 'Second'])
        data['events'][-1]['revision'] = 3
        with self.assertRaisesRegex(ValueError, 'revision_order'):
            result(self.name, data)


class Resources(unittest.TestCase):
    name = 'one-use-resources'

    def outcome(self, kind='consume_result', outcome='consumed'):
        return {'id': 'Result' if kind == 'consume_result' else 'Resolution', 'kind': kind,
                'resource': 'Ticket', 'attempt': 'Use1', 'outcome': outcome, 'evidence': 'a'*64}

    def test_branch_transfer_and_crash_intent_fence(self):
        data = example(self.name)
        r = result(self.name, data)
        state = r['resources'][0]
        self.assertEqual((state['owner'], state['branch'], state['state']), ('Worker','BranchA','uncertain'))
        self.assertFalse(state['may_plan_new_use'] or state['automatic_redispatch'])
        data['events'] += deepcopy(data['events'])
        self.assertEqual(result(self.name, data)['resources'], r['resources'])
        extra = deepcopy(data['events'][2]); extra.update(id='RetryIntent', attempt='Use2', expected_revision=3)
        data['events'].append(extra)
        with self.assertRaisesRegex(ValueError, 'resource_unavailable'):
            result(self.name, data)

    def test_consumed_is_terminal_and_cannot_reissue(self):
        data = example(self.name); data['events'].append(self.outcome())
        state = result(self.name, data)['resources'][0]
        self.assertEqual(state['state'], 'consumed')
        self.assertFalse(state['may_plan_new_use'])
        duplicate = deepcopy(data['events'][-1]); data['events'].append(duplicate)
        self.assertEqual(result(self.name, data)['resources'][0], state)
        issue = deepcopy(data['events'][0]); issue['id'] = 'Reissue'; data['events'].append(issue)
        with self.assertRaisesRegex(ValueError, 'resource_reissued'):
            result(self.name, data)

    def test_unknown_requires_exact_resolution_and_retains_receipts(self):
        data = example(self.name); data['events'].append(self.outcome(outcome='unknown'))
        self.assertEqual(result(self.name, data)['uncertain_resources'], ['Ticket'])
        data['events'].append(self.outcome(kind='resolve'))
        r = result(self.name, data)
        self.assertEqual(r['resources'][0]['state'], 'consumed')
        self.assertEqual([x['outcome'] for x in r['attempts']['Use1']['receipts']], ['unknown','consumed'])
        wrong = example(self.name); row = self.outcome(kind='resolve'); row['attempt'] = 'Other'; wrong['events'].append(row)
        with self.assertRaisesRegex(ValueError, 'outcome_without_pending_attempt'):
            result(self.name, wrong)

    def test_definite_nonconsumption_allows_only_new_explicit_attempt(self):
        data = example(self.name); data['events'].append(self.outcome(kind='resolve', outcome='not_consumed'))
        state = result(self.name, data)['resources'][0]
        self.assertEqual(state['state'], 'transferred'); self.assertTrue(state['may_plan_new_use'])
        self.assertFalse(state['automatic_redispatch'])
        retry = deepcopy(data['events'][2]); retry.update(id='Retry', expected_revision=state['revision'])
        data['events'].append(retry)
        with self.assertRaisesRegex(ValueError, 'attempt_id_reused'):
            result(self.name, data)
        retry['attempt'] = 'Use2'
        r = result(self.name, data)
        self.assertEqual(r['resources'][0]['state'], 'uncertain')
        self.assertEqual(set(r['attempts']), {'Use1','Use2'})
        stale = self.outcome(kind='resolve', outcome='not_consumed'); stale['id']='OldResolutionAgain'
        data['events'].append(stale)
        with self.assertRaisesRegex(ValueError, 'outcome_without_pending_attempt'):
            result(self.name, data)

    def test_wrong_branch_stale_revision_and_early_outcome_refuse(self):
        for change in ('branch', 'owner', 'revision', 'early', 'bool'):
            data = example(self.name)
            if change == 'branch': data['events'][2]['branch'] = 'Root'
            if change == 'owner': data['events'][2]['owner'] = 'Planner'
            if change == 'revision': data['events'][2]['expected_revision'] = 1
            if change == 'bool': data['events'][2]['expected_revision'] = True
            if change == 'early': data['events'] = data['events'][:2]+[self.outcome()]
            with self.subTest(change=change), self.assertRaises(ValueError):
                result(self.name, data)


class Sagas(unittest.TestCase):
    name = 'saga-compensation-plan'

    def test_reverse_dependencies_and_complete_rollback(self):
        data = example(self.name)
        first = result(self.name, data)
        self.assertEqual([x['compensation_id'] for x in first['ready_compensations']], ['Refund'])
        self.assertEqual([x['compensation_id'] for x in first['reverse_dependency_order']], ['Refund','Release'])
        data['events'] += [saga_event('intent','Charge','Refund','Refund1'), saga_event('outcome','Charge','Refund','Refund1','done')]
        second = result(self.name, data)
        self.assertEqual([x['compensation_id'] for x in second['ready_compensations']], ['Release'])
        self.assertEqual(second['ready_compensations'][0]['requires_compensations'], ['Refund'])
        data['events'] += [saga_event('intent','Reserve','Release','Release1'), saga_event('outcome','Reserve','Release','Release1','done')]
        final = result(self.name, data)
        self.assertTrue(final['rollback_complete']); self.assertEqual(final['ready_compensations'], [])
        self.assertTrue(all(x['outcome']=='done' for x in final['attempts'].values()))

    def test_crash_during_compensation_is_not_redispatched(self):
        data = example(self.name); data['events'].append(saga_event('intent','Charge','Refund','Refund1'))
        before = result(self.name, data)
        self.assertEqual(before['ready_compensations'], [])
        self.assertEqual(before['uncertain_attempts'], [{'step':'Charge','operation':'compensate','attempt':'Refund1'}])
        data['events'] += deepcopy(data['events'])
        self.assertEqual(result(self.name, data)['steps'], before['steps'])
        self.assertFalse(result(self.name, data)['automatic_redispatch'])
        data['rollback'] = False
        replayed = result(self.name, data)
        self.assertFalse(replayed['rollback_requested'])
        self.assertTrue(replayed['rollback_started'] and replayed['rollback_active'])
        data['events'].append(saga_event('resolve','Charge','Refund','Refund1','done'))
        self.assertEqual(result(self.name, data)['ready_compensations'][0]['compensation_id'], 'Release')

    def test_unknown_original_blocks_itself_and_ancestor(self):
        data = example(self.name); data['events'] = data['events'][:-1]
        r = result(self.name, data)
        self.assertEqual(r['ready_compensations'], [])
        self.assertEqual({x['reason'] for x in r['blocked_compensations']}, {'original_outcome_unknown','dependencies_uncompensated'})
        data['events'].append(saga_event('resolve','Charge','Charge','Charge1','not_done'))
        self.assertEqual(result(self.name, data)['ready_compensations'][0]['compensation_id'], 'Release')

    def test_compensation_order_and_action_identity_cannot_be_forged(self):
        for change in ('order', 'wrong_link', 'no_original', 'wrong_attempt'):
            data = example(self.name)
            if change == 'order': data['events'].append(saga_event('intent','Reserve','Release','Release1'))
            if change == 'wrong_link': data['events'].append(saga_event('intent','Charge','Release','Refund1'))
            if change == 'no_original': data['events'] = [saga_event('intent','Charge','Refund','Refund1')]
            if change == 'wrong_attempt': data['events'].append(saga_event('outcome','Charge','Refund','Missing','done'))
            with self.subTest(change=change), self.assertRaises(ValueError):
                result(self.name, data)

    def test_forward_prerequisites_and_no_forward_after_compensation(self):
        data = example(self.name); data['events'] = [data['events'][2]]
        with self.assertRaisesRegex(ValueError, 'forward_prerequisite'):
            result(self.name, data)
        data = example(self.name); data['steps'].append({'id':'Independent','compensation':'UndoIndependent','requires':[]})
        data['events'].append(saga_event('intent','Charge','Refund','Refund1'))
        data['events'].append(saga_event('intent','Independent','Independent','Independent1'))
        with self.assertRaisesRegex(ValueError, 'forward_after_rollback'):
            result(self.name, data)

    def test_known_failed_compensation_can_have_a_new_explicit_attempt(self):
        data = example(self.name)
        data['events'] += [saga_event('intent','Charge','Refund','Refund1'), saga_event('outcome','Charge','Refund','Refund1','not_done')]
        r = result(self.name, data)
        self.assertEqual([x['compensation_id'] for x in r['ready_compensations']], ['Refund'])
        retry = saga_event('intent','Charge','Refund','Refund1'); retry['id']='DifferentIntent'; data['events'].append(retry)
        with self.assertRaisesRegex(ValueError, 'attempt_id_reused'):
            result(self.name, data)
        retry['attempt']='Refund2'
        self.assertEqual(result(self.name, data)['ready_compensations'], [])

    def test_dag_and_id_contracts_refuse(self):
        for change in ('cycle','unknown','samecomp','overlap','many','bool'):
            data = example(self.name)
            if change=='cycle': data['steps'][0]['requires']=['Charge']
            if change=='unknown': data['steps'][0]['requires']=['Unknown']
            if change=='samecomp': data['steps'][1]['compensation']='Release'
            if change=='overlap': data['steps'][0]['compensation']='Charge'
            if change=='many': data['steps']*=9
            if change=='bool': data['rollback']=1
            with self.subTest(change=change), self.assertRaises(ValueError):result(self.name,data)


class Boundaries(unittest.TestCase):
    def test_invalid_json_bounds_and_detachment(self):
        cyclic={};cyclic['x']=cyclic
        for bad in (cyclic, {'events':[{}]*257}, {'x':0.5}, {'x':'\ud800'}, {'x':2**129}):
            with self.subTest(bad=str(bad)[:60]), self.assertRaises(ValueError):
                P.run('revision-acknowledgements',bad)
        for entry in P.catalog():
            data=entry['example'];original=deepcopy(data)
            self.assertEqual(P.run(entry['id'],data),P.run(entry['id'],data))
            self.assertEqual(data,original)
            json.dumps(P.run(entry['id'],data),allow_nan=False)
        P.catalog()[0]['example']['events'].clear()
        self.assertEqual(len(P.catalog()[0]['example']['events']),4)

    def test_empty_streams_and_all_crash_prefixes_are_inert(self):
        for entry in P.catalog():
            for end in range(len(entry['example']['events'])+1):
                data=deepcopy(entry['example']);data['events']=data['events'][:end]
                output=P.run(entry['id'],data)
                self.assertEqual(set(output),{'arithmetic','results','checks','limits','sources'})
                self.assertTrue(all(output['checks'].values()))
        data=example('saga-compensation-plan');data['rollback']=False
        self.assertEqual(result('saga-compensation-plan',data)['ready_compensations'],[])


if __name__=='__main__':
    unittest.main()
