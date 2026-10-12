"""HOST-ONLY module, fakes only: the OS prototype's model engine (integration/host/symblicos_model_engine.py).

The model call goes through the provider module, which is replaced by a mock; nothing reaches a model.
Covers the exact prompt handed to the provider, the exact READY health rule, the capacity plan refusing
unknown sizes, and the refusal to fall back to an unregistered model.
Run: DASH_TEST=1 python3 -m unittest discover -s tests/integration -t .
"""
import unittest
from unittest.mock import patch


class Models(unittest.TestCase):
    def test_invocation_uses_admitted_adapter_with_exact_prompt(self):
        from integration.host.symblicos_model_engine import SymblicOSModelEngine
        model = SymblicOSModelEngine('node-test')
        model.registry['qwen:test'] = {'digest': None}
        with patch('symblic.autogen.runner.execution_fence'), patch('symblic.providers.applicators.Applicators') as factory:
            factory.return_value.call.return_value = {'ok': True, 'text': 'answer', 'node': 'node-test'}
            result = model.invoke_model_adapter('qwen:test', "Keep 'quotes' and $(text) literal")
        call = factory.return_value.call.call_args.args[0]
        self.assertEqual("Keep 'quotes' and $(text) literal", call['prompt'])
        self.assertEqual('node-test', call['app']['node'])
        self.assertEqual('ollama', call['app']['engine'])
        self.assertEqual('answer', result['response'])

    def test_health_requires_exact_ready_response(self):
        from integration.host.symblicos_model_engine import SymblicOSModelEngine
        model = SymblicOSModelEngine('node-test')
        with patch.object(model, '_call', return_value={'ok': True, 'text': 'not ready'}):
            self.assertFalse(model.verify_local_model_health('qwen:test')['healthy'])
        with patch.object(model, '_call', return_value={'ok': True, 'text': 'READY'}):
            self.assertTrue(model.verify_local_model_health('qwen:test')['healthy'])

    def test_capacity_unknown_does_not_claim_all_fit(self):
        from integration.host.symblicos_model_engine import SymblicOSModelEngine
        plan = SymblicOSModelEngine().capacity_plan([{'identifier': 'qwen', 'size_bytes': None}], 100000)
        self.assertEqual('blocked', plan['status'])
        self.assertIsNone(plan['required_total_bytes'])

    def test_unlisted_model_never_falls_back(self):
        from integration.host.symblicos_model_engine import SymblicOSModelEngine
        model = SymblicOSModelEngine()
        with patch.object(model, '_call', side_effect=AssertionError('must not dispatch')):
            for local in (True, False):
                with self.assertRaisesRegex(RuntimeError, 'No fallback'):
                    model.invoke_model_adapter('missing', 'prompt', require_local=local)


class Inventory(unittest.TestCase):
    def test_the_registry_comes_from_the_given_hub_only(self):
        from integration.host.symblicos_model_engine import SymblicOSModelEngine
        with self.assertRaisesRegex(RuntimeError, 'needs the host'):
            SymblicOSModelEngine('node-a').build_registry()

        class Hub:
            LOCAL_NODE = 'host'

            @staticmethod
            def fleet_nodes():
                return [{'id': 'node-a', 'online': True, 'models': [{'name': 'qwen3:4b-instruct', 'size': 2500}]},
                        {'id': 'host', 'online': True, 'models': [{'name': 'tiny:1b'}]}]
        engine = SymblicOSModelEngine('node-a', hub=Hub())
        self.assertEqual(['qwen3:4b-instruct'], list(engine.build_registry()))
        self.assertEqual(['tiny:1b'], [row['identifier'] for row in engine.inventory_host()])


if __name__ == '__main__':
    unittest.main()
