"""Studio-to-Symblic journeys with fake applicators and temporary stores only.

HOST-ONLY: these journeys drive the original host's automation engine (`automation_engine`, the backend of the
automation studio in web/studio/: its Symblic node, the Send to Studio handoff and its run center), which is not
part of this repository, so the module is skipped when that engine cannot be imported.
"""

import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host system Symblic was built in
    import automation_engine as AE
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.providers import applicators as symblic_apply


class MemoryContext:
    def get(self, _key):
        return []

    def set(self, _key, _value):
        pass


class FakeApps:
    """Records semantic provider/delegation requests without starting any worker."""

    def __init__(self, answer='hello'):
        self.answer = answer
        self.requests = []
        self.delegations = []
        self.delegation_error = ''

    def call(self, request):
        self.requests.append(request)
        return {'ok': True, 'json': {'answer': self.answer}, 'ms': 0}

    def delegate(self, target, task, options):
        self.delegations.append((target, task, options))
        if self.delegation_error:
            return {'error': self.delegation_error}
        return {'id': 'fake-triad', 'engine': target, 'link': '/agents#fake-triad'}


class StudioSymblicNodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='studio-symblic-tests-')
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'AUTOMATION_DATA_DIR': self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = patch.object(AE, 'load_config', return_value={})
        self.config.start()
        self.addCleanup(self.config.stop)
        self.apps = FakeApps()
        self.app_factory = patch.object(symblic_apply, 'Applicators', return_value=self.apps)
        self.constructor = self.app_factory.start()
        self.addCleanup(self.app_factory.stop)

    def make_run(self, use_llm=True):
        run = AE.Run('fake-studio-run', {'id': 'fake-workflow', 'graph': {'nodes': {}, 'edges': []}},
                     {'useLLM': use_llm, 'contextPolicy': 'isolated'}, view=MemoryContext())
        self.assertTrue(run.log_path.startswith(self.tmp.name + os.sep))
        self.assertTrue(run.index_path.startswith(self.tmp.name + os.sep))
        return run

    @staticmethod
    def node(kind, **data):
        return {'id': 'step', 'type': kind, 'title': kind.title(), 'data': data}

    def test_agent_returns_typed_answer_from_rendered_workflow_prompt(self):
        run = self.make_run()
        run.last_output = 'earlier result'
        run.vars['subject'] = 'flowers'
        output = run.run_node(self.node('agent', by='fake:one', effort='low',
                                        prompt='Explain {{subject}} after {{last_output}}'))
        self.assertEqual(output, 'hello')
        self.assertEqual(run.steps[-1]['status'], 'done')
        self.assertEqual(self.constructor.call_args.kwargs['run_id'], 'studio-fake-studio-run')
        self.assertEqual(len(self.apps.requests), 1)
        request = self.apps.requests[0]
        self.assertIn('Explain flowers after earlier result', request['prompt'])
        self.assertEqual(request['app']['engine'], 'fake')
        self.assertEqual(request['app']['model'], 'one')
        self.assertIs(request['stop'], run.stop_event)
        self.assertEqual(request['schema']['properties']['answer']['type'], 'string')

    def test_council_uses_chosen_template_and_returns_the_answer(self):
        run = self.make_run()
        output = run.run_node(self.node('council', template='chosen-panel', effort='low',
                                        prompt='Choose the next step'))
        self.assertEqual(output, 'hello')
        self.assertEqual(run.steps[-1]['status'], 'done')
        self.assertEqual(len(self.apps.requests), 1)
        self.assertEqual(self.apps.requests[0]['app']['engine'], 'council')
        self.assertEqual(self.apps.requests[0]['app']['model'], 'chosen-panel')

    def test_triad_handoff_records_id_for_following_workflow_steps(self):
        run = self.make_run()
        run.vars['task'] = 'inspect a supplied fixture'
        output = run.run_node(self.node('triad', task='Please {{task}}', cwd='/fake/checkout'))
        self.assertEqual(run.steps[-1]['status'], 'done')
        self.assertEqual(self.apps.delegations,
                         [('triad', 'Please inspect a supplied fixture', {'cwd': '/fake/checkout'})])
        self.assertIn('fake-triad', output)
        self.assertEqual(run.variables(self.node('log'))['vars.triad_agent'], 'fake-triad')
        self.assertEqual(self.apps.requests, [])

    def test_failed_triad_handoff_is_visible_and_does_not_publish_agent_id(self):
        run = self.make_run()
        self.apps.delegation_error = 'no capacity'
        self.assertEqual(run.run_node(self.node('triad', task='fixture task')), '')
        self.assertEqual(run.steps[-1]['status'], 'error')
        self.assertIn('no capacity', run.steps[-1]['error'])
        self.assertNotIn('triad_agent', run.vars)

    def test_exact_program_consumes_workflow_inputs_and_exports_bindings(self):
        run = self.make_run()
        run.vars['initial'] = '4'
        source = 'given initial: Int.\nlet total = initial + 4.\nshow total.\n'
        output = run.run_node(self.node('symblic', source=source))
        self.assertEqual(run.steps[-1]['status'], 'done', run.steps[-1]['error'])
        self.assertEqual(output, '8')
        self.assertEqual(json.loads(run.vars['symblic_total']), 8)
        self.assertEqual(json.loads(run.vars['symblic_initial']), 4)
        self.assertRegex(run.vars['symblic_fingerprint'], r'^[a-f0-9]{16,64}$')
        self.assertEqual(self.apps.requests, [])
        self.assertEqual(self.apps.delegations, [])

    def test_disabled_model_steps_never_construct_an_applicator(self):
        for kind in ('agent', 'council', 'symblic'):
            with self.subTest(kind=kind):
                run = self.make_run(use_llm=False)
                self.assertEqual(run.run_node(self.node(kind, prompt='fixture', source='show 4.\n')),
                                 'LLM disabled.')
                self.assertEqual(run.steps[-1]['status'], 'done')
        self.constructor.assert_not_called()
        self.assertEqual(self.apps.requests, [])
        self.assertEqual(self.apps.delegations, [])

    def test_cancelled_program_starts_no_model_requests(self):
        run = self.make_run()
        run.stop_event.set()
        output = run.run_node(self.node('agent', prompt='fixture', by='fake:one', effort='low'))
        self.assertEqual(output, '')
        self.assertEqual(run.steps[-1]['status'], 'error')
        self.assertIn('stopped', run.steps[-1]['error'])
        self.assertEqual(self.apps.requests, [])
        self.assertEqual(self.apps.delegations, [])

    def test_invalid_formal_program_is_visible_and_exports_no_partial_results(self):
        run = self.make_run()
        output = run.run_node(self.node('symblic', source='let total = 4 + 4.\nassert total = 9.\n'))
        self.assertEqual(output, '')
        self.assertEqual(run.steps[-1]['status'], 'error')
        self.assertIn('line 2', run.steps[-1]['error'])
        self.assertNotIn('symblic_total', run.vars)
        self.assertNotIn('symblic_fingerprint', run.vars)
        self.assertEqual(self.apps.requests, [])

    def test_node_finishes_without_extra_orchestration_threads(self):
        run = self.make_run()
        before = set(threading.enumerate())
        output = run.run_node(self.node('agent', prompt='fixture', by='fake:one', effort='low'))
        self.assertEqual(output, 'hello')
        self.assertEqual(set(threading.enumerate()) - before, set())


if __name__ == '__main__':
    unittest.main()
