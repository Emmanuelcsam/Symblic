"""Coach-to-build contracts: the coach route, the real compiler and isolated local stores.

The proposals go through the coach route of the original host's Forge route handler
(integration/host/symblic_forge.py). That module imports without the host and is given a local store here;
if it ever stops importing on its own, these tests are skipped.
"""
import copy
import tempfile
import unittest

try:  # the route handler lives with the host files; it needs no host for these routes
    from integration.host import symblic_forge as API
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.forge import coach as Coach
from symblic.forge import core as C
from symblic.forge import exports as E
from symblic.forge.store import Store, StoreError


class CoachConstructionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-coach-construction-')
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.p = self.store.create('Make a precisely specified movement step', '', '', 'create_request')
        self.p = self.store.mutate(self.p['id'], 0, 'entity.propose', {'kind': 'components', 'entity': {
            'text': 'Snake movement', 'responsibility': 'Compute one pure movement step',
            'inputs': ['body cells', 'direction'], 'outputs': ['next body cells']}}, 'component_request')
        self.component = C.active_branch(self.p)['entities']['components'][0]['id']
        self.p = self.store.mutate(self.p['id'], 1, 'entity.accept',
                                   {'kind': 'components', 'id': self.component}, 'accept_component')
        self.fields = {'text': 'Compute one movement step.', 'input': 'body=[(2,2),(1,2)], direction=right',
                       'output': 'next body cells in snake/src/state.js',
                       'check': 'For the supplied body, return [(3,2),(2,2)] without mutating the input.',
                       'context': ['Only the supplied body and direction; no rendering or hidden history'],
                       'source_ids': [], 'construction': {'component_id': self.component,
                                                         'dependencies': [], 'paths': ['snake/src/state.js']}}

    def propose(self, request_id='propose_request'):
        return API.dispatch('POST', 'coach/propose', {'id': self.p['id'], 'revision': self.p['revision'],
                            'request_id': request_id, **self.fields}, db=self.store)

    def test_atomic_proposals_retain_exact_contract_and_do_not_export_until_accepted(self):
        self.fields['edited_text'] = Coach.preview(self.p, self.fields)['after'] + '\nPreserve exact integer cells.'
        result = self.propose()
        branch = C.active_branch(result['project'])
        statement, unit = branch['statements'][-1], branch['entities']['units'][-1]
        self.assertEqual([statement['status'], unit['status']], ['proposed', 'proposed'])
        self.assertEqual(statement['text'], self.fields['edited_text'])
        self.assertEqual(unit['requirement_ids'], [statement['id']])
        self.assertEqual(unit['source_ids'], [statement['id']])
        self.assertEqual(unit['inputs'], [self.fields['input'], *self.fields['context']])
        self.assertEqual(unit['checks'], [self.fields['check']])
        self.assertEqual(unit['objective'], self.fields['edited_text'])
        self.assertEqual(unit['paths'], ['snake/src/state.js'])
        self.assertEqual(E.task_cards(result['project']), [])
        self.assertFalse(result['analysis']['readiness']['ready'])
        self.assertEqual(self.propose()['project'], result['project'], 'Same intent is idempotent')
        p = C.transition(result['project'], 'statement.accept', {'id': statement['id']})
        p = C.transition(p, 'entity.accept', {'kind': 'units', 'id': unit['id']})
        card = E.task_cards(p)[0]
        self.assertEqual(card['requirements'][0]['text'], self.fields['edited_text'])
        self.assertEqual(card['verification'], [self.fields['check']])
        checked = E.validate(p)
        self.assertTrue(checked['ok'], checked['diagnostics'])
        self.assertFalse(checked['verification']['executed'])
        self.assertIn('context=none', checked['source'])
        self.assertIn('snake/src/state.js', checked['source'])

    def test_invalid_component_dependency_or_hidden_input_never_partially_proposes(self):
        before = copy.deepcopy(self.p)
        for change in ({'construction': {'component_id': 'missing'}},
                       {'construction': {'component_id': self.component, 'dependencies': ['missing']}},
                       {'construction': {'component_id': self.component, 'accepted': True}},
                       {'input': 'the whole conversation'}, {'check': ''}):
            with self.subTest(change=change), self.assertRaises((C.ForgeError, StoreError)):
                API.dispatch('POST', 'coach/propose', {'id': self.p['id'], 'revision': self.p['revision'],
                    'request_id': 'bad_request', **self.fields, **change}, db=self.store)
            self.assertEqual(self.store.get(self.p['id']), before)

    def test_proposed_component_and_proposed_dependencies_are_not_silently_accepted(self):
        p = C.transition(self.p, 'entity.propose', {'kind': 'components', 'entity': {
            'text': 'Unreviewed component', 'responsibility': 'Unreviewed', 'inputs': [], 'outputs': ['x']}})
        identifier = C.active_branch(p)['entities']['components'][-1]['id']
        with self.assertRaisesRegex(C.ForgeError, 'accepted component'):
            Coach.preview(p, {**self.fields, 'construction': {'component_id': identifier}})
        result = self.propose()
        unit = C.active_branch(result['project'])['entities']['units'][-1]['id']
        with self.assertRaisesRegex(C.ForgeError, 'accepted units'):
            Coach.preview(result['project'], {**self.fields, 'construction': {
                'component_id': self.component, 'dependencies': [unit]}})


if __name__ == '__main__':
    unittest.main()
