"""Notebook API journeys use isolated host run records; never a model or live store."""
import copy
import json
from pathlib import Path

from integration.host import symblic_engine as E
from tests.integration.test_symblic_engine import Base


class MemoryAPI(Base):
    def call_memory(self, action, body=None, query=None):
        return self.call('GET' if body is None else 'POST', 'memory/' + action, body, query=query)

    def create(self, **extra):
        reply = self.call_memory('create', {'title': 'Project knowledge', 'operation_id': 'create-1', **extra})
        self.assertEqual(reply.status, 200, reply.sent)
        return reply.sent

    def change(self, book, operation, **fields):
        return self.call_memory('change', {'id': book['id'], 'command': {
            'operation_id': operation, 'expected_head': book['head'], **fields}})

    def fixture_run(self):
        result = E.start_run({'source': 'use profile=verified.\nlet x = 3.\nlet y = 4.\nshow x.\nshow y.\n'})
        folder = Path(E.run_dir(result['id']))
        state = json.loads((folder / 'state.json').read_text())
        self.assertEqual(state['status'], 'done', state.get('error'))
        ids = {row['content'].get('name'): row['id'] for row in state['epistemic']['claims']}
        return result['id'], folder, state, ids

    def test_owner_revision_closure_conflict_and_fresh_context(self):
        book = self.create()
        duplicate = self.create()
        self.assertTrue(duplicate['idempotent'])
        self.assertEqual(duplicate['head'], book['head'])
        reply = self.change(book, 'add-a', action='add', claim_id='a', content='The input is an integer.')
        self.assertEqual(reply.status, 200, reply.sent); book = reply.sent
        reply = self.change(book, 'add-b', action='add', claim_id='b', content='Apply the integer rule.', depends_on=['a'])
        self.assertEqual(reply.status, 200, reply.sent); book = reply.sent
        context = self.call_memory('context', {'id': book['id'], 'expected_head': book['head'],
                                                'selected_ids': ['b'], 'budget': 24000})
        self.assertEqual(context.status, 200, context.sent)
        self.assertEqual(context.sent['closure_ids'], ['a', 'b'])
        original = copy.deepcopy(book)
        revised = self.change(book, 'revise-a', action='revise', claim_id='a', content='The input is a real number.')
        self.assertEqual(revised.status, 200, revised.sent); book = revised.sent
        stale = self.change(original, 'stale-edit', action='add', claim_id='c', content='stale')
        self.assertEqual(stale.status, 409)
        denied = self.call_memory('context', {'id': book['id'], 'expected_head': book['head'],
                                               'selected_ids': ['b'], 'budget': 24000})
        self.assertEqual(denied.status, 400)
        self.assertEqual(denied.sent['detail']['code'], 'unavailable_support')
        current = self.call_memory('view', query={'id': book['id']}).sent
        self.assertEqual(len(current['history']), 3)
        self.assertEqual(len(self.call_memory('notebooks').sent['notebooks']), 1)

    def test_import_all_subset_empty_and_hash_only(self):
        ident, folder, state, ids = self.fixture_run()
        for label, selected in [('all', None), ('one', [ids['x']]), ('none', [])]:
            body = {'title': label, 'operation_id': label, 'run_id': ident}
            if selected is not None:
                body['selected_ids'] = selected
            reply = self.call_memory('create', body)
            self.assertEqual(reply.status, 200, reply.sent)
            wanted = set(ids.values()) if selected is None else set(selected)
            self.assertEqual({row['id'] for row in reply.sent['claims']}, wanted)
            self.assertEqual(set(reply.sent['values']), wanted)
            self.assertEqual(reply.sent['source']['acquisition_independence'], 'not_assessed')
            self.assertEqual(len(reply.sent['source']['state_sha256']), 64)
        state['outputs'] = []
        (folder / 'state.json').write_text(json.dumps(state))
        book = self.create(operation_id='hash-only', run_id=ident)
        self.assertEqual(len(book['claims']), 2)
        context = self.call_memory('context', {'id': book['id'], 'expected_head': book['head'],
                                                'selected_ids': [ids['x']], 'budget': 24000})
        self.assertEqual(context.status, 200, context.sent)
        self.assertFalse(context.sent['all_referenced_values_available'])

    def test_import_refuses_drift_and_damaged_provenance(self):
        ident, folder, original, ids = self.fixture_run()
        variants = []
        bad = copy.deepcopy(original); bad['kernel']['id'] = 'old'; variants.append(bad)
        bad = copy.deepcopy(original); bad['outputs'] = None; variants.append(bad)
        bad = copy.deepcopy(original); bad['status'] = 'running'; variants.append(bad)
        for bad in variants:
            (folder / 'state.json').write_text(json.dumps(bad))
            reply = self.call_memory('create', {'title': 'refused', 'operation_id': 'bad', 'run_id': ident})
            self.assertEqual(reply.status, 400, reply.sent)
        (folder / 'state.json').write_text(json.dumps(original))
        with (folder / 'program.sym').open('a') as stream:
            stream.write('\nnote Different source revision.\n')
        reply = self.call_memory('create', {'title': 'refused', 'operation_id': 'bad', 'run_id': ident})
        self.assertEqual(reply.status, 400)

    def test_cannot_upload_host_receipts_or_skip_context_head(self):
        book = self.create()
        for forbidden in ('origin', 'checks', 'status'):
            reply = self.change(book, 'forged', action='add', claim_id='forged', content='A claim', **{forbidden: 'derived'})
            self.assertEqual(reply.status, 400)
        for head in (None, '', 'old', 3):
            reply = self.call_memory('context', {'id': book['id'], 'selected_ids': [], 'budget': 24000,
                                                   'expected_head': head})
            self.assertEqual(reply.status, 400)
        reply = self.call_memory('create', {'title': 'forged', 'operation_id': 'forged', 'trusted_claims': []})
        self.assertEqual(reply.status, 400)
