"""Strict optional catalog selection through pure, CLI and owner API entry points."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

try:  # host-only: these modules belong to the private host dashboard Symblic was built in
    import automation_engine as AE
    import host_apps
    import security_gate as SG
    from integration.host import symblic_engine as E
    from tests.integration.test_symblic_engine import Base, Handler
except ImportError as missing:
    if (missing.name or '').split('.')[0] in ('symblic', 'integration', 'tests'):
        raise                       # a module of this repository failed to import: a bug, not a missing host
    raise unittest.SkipTest(f'host-only test: needs {missing.name!r}, which is not part of this repository '
                            '(see integration/host/README.md)') from None
from symblic.providers import applicators as symblic_apply
from symblic.delegate import contracts as D
from symblic.delegate import run as H
from tests.integration.test_symblic_proof_step_entry import RoutedHandler, cli

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def nodes(value):
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from nodes(child)
    elif type(value) is list:
        for child in value:
            yield from nodes(child)


class FocusedCatalog(unittest.TestCase):
    def test_catalog_preserves_frozen_v8_branches_and_all_prior_contracts(self):
        baseline = json.loads((FIXTURES / 'symblic_catalog_v8_parity.json').read_text())
        current = D.catalog()
        self.assertEqual(current['version'], 9)
        prior = copy.deepcopy(current)
        prior['version'] = 8
        self.assertEqual(prior['templates'].pop()['template_id'], 'symblic.delegate/proof_step_card/9')
        prior['request_schema']['oneOf'].pop()
        self.assertTrue(prior['semantic_validation'].pop(-2).startswith('proof_step_card '))
        self.assertEqual(prior, baseline['catalog'])
        self.assertEqual(json.dumps(prior, ensure_ascii=False).encode(),
                         json.dumps(baseline['catalog'], ensure_ascii=False).encode())
        count = 0
        for name in ('symblic_delegate_v7_parity.json',):
            for row in json.loads((FIXTURES / name).read_text())['fixtures']:
                self.assertEqual(D.compile_task(row['request']), row['compiled'])
                count += 1
        self.assertEqual(count, 31)

    def test_every_exact_schema_branch_and_only_required_definitions_remain(self):
        full = D.catalog()
        self.assertEqual(set(D._CATALOG_FOCUS), set(D.TEMPLATE_VERSIONS))
        for row in full['templates']:
            name = row['id']
            with self.subTest(template=name), patch.object(D, 'compile_task', side_effect=AssertionError('No compilation')), \
                    patch.object(H, 'Run', side_effect=AssertionError('No execution')):
                focused = D.catalog(name)
            self.assertEqual(focused['selected_template'], name)
            self.assertEqual(focused['templates'], [row])
            self.assertEqual(focused['version'], full['version'])
            selected = next(schema for schema in full['request_schema']['oneOf']
                            if schema['properties']['template']['const'] == name)
            self.assertEqual(focused['request_schema']['oneOf'], [selected])
            defs = focused['request_schema'].get('$defs', {})
            self.assertEqual(set(defs), {'output_schema'} if name == 'typed_transform' else set())
            for item in nodes(focused['request_schema']):
                if '$ref' in item:
                    self.assertTrue(item['$ref'].startswith('#/$defs/'))
                    self.assertIn(item['$ref'].split('/')[-1], defs)
            if defs:
                self.assertEqual(defs, full['request_schema']['$defs'])
            self.assertTrue(focused['assurance'])
            self.assertEqual(focused['semantic_validation'][-1], full['semantic_validation'][-1])
            self.assertLess(len(json.dumps(focused).encode()), len(json.dumps(full).encode()))

    def test_selected_assurance_bounds_and_defaults_are_specific(self):
        for name in D.TEMPLATE_VERSIONS:
            focused = D.catalog(name)
            self.assertEqual(focused['bounds'], {'json_bytes': 524288, 'json_depth': 24,
                                                'json_nodes': 20000, 'string_characters': 131072})
            self.assertEqual(focused['defaults'], {'calls': 0 if name == 'exact_arithmetic' else 3,
                              'context_budget': 24000, 'max_steps': 200000, 'capsule': 'full'})
        self.assertEqual(D.catalog('proof')['default_overrides'],
                         [{'when': {'params.certificate_format': 'incremental'}, 'calls': 32}])
        self.assertNotIn('default_overrides', D.catalog('typed_transform'))
        self.assertIn('classification accuracy', D.catalog('enum_classification')['assurance'])
        self.assertIn('free-assumption set', D.catalog('proof_step_obligation')['assurance'])
        self.assertIn('full original session', D.catalog('proof_step_focus')['assurance'])
        self.assertEqual(D.catalog('proof_step_focus')['semantic_validation'],
                         [D.catalog()['semantic_validation'][index] for index in (4, 5, 6, -1)])
        self.assertNotIn('proof_step_obligation', '\n'.join(D.catalog('exact_arithmetic')['semantic_validation']))
        self.assertEqual(D.catalog(template='proof'), D.catalog('proof'))
        for fixture_name in ('symblic_delegate_v5_parity.json', 'symblic_delegate_v6_parity.json',
                             'symblic_catalog_v7_parity.json'):
            for row in json.loads((FIXTURES / fixture_name).read_text())['fixtures']:
                task = {key: copy.deepcopy(row['request'][key]) for key in ('template', 'params')}
                compiled = D.compile_task(task)
                focus = D.catalog(task['template'])
                calls = focus['defaults']['calls']
                if task['template'] == 'proof' and task['params'].get('certificate_format') == 'incremental':
                    calls = focus['default_overrides'][0]['calls']
                self.assertEqual(compiled['options']['max_calls'], calls)
                self.assertEqual(compiled['options']['max_steps'], focus['defaults']['max_steps'])
                self.assertEqual(compiled['options']['capsule'], focus['defaults']['capsule'])
                self.assertEqual(compiled['limits']['context_characters'], focus['defaults']['context_budget'])

    def test_unknown_malformed_and_subclass_selectors_never_fall_back(self):
        class Name(str):
            pass
        for value in (None, False, 0, 1, [], {}, ['proof'], '', ' ', 'proof ', 'Proof', 'all',
                      'proof,proof_step', 'unknown', 'proof\x00', 'proof\n', 'π', 'x' * 100000,
                      Name('proof')):
            with self.subTest(kind=type(value).__name__), self.assertRaises(D.ContractError) as caught:
                D.catalog(value)
            self.assertEqual(caught.exception.code, 'catalog_selector')
            self.assertEqual(caught.exception.path, 'template')

    def test_focused_results_are_detached_from_future_full_and_focused_catalogs(self):
        before = D.catalog()
        focused = D.catalog('typed_transform')
        original = copy.deepcopy(focused)
        focused['templates'][0]['id'] = 'changed'
        focused['request_schema']['$defs']['output_schema']['oneOf'].clear()
        focused['defaults']['calls'] = 0
        focused['semantic_validation'].clear()
        self.assertEqual(D.catalog(), before)
        self.assertEqual(D.catalog('typed_transform'), original)

    def test_cli_full_and_all_focused_catalogs_use_no_provider_or_runner(self):
        with patch.object(symblic_apply, 'Applicators', side_effect=AssertionError('No provider')), \
                patch.object(H, 'Run', side_effect=AssertionError('No runner')):
            for name in (None, *D.TEMPLATE_VERSIONS):
                arguments = ['catalog', '--agent-json']
                if name is not None:
                    arguments += ['--template', name]
                status, text, error = cli(arguments)
                self.assertEqual(status, 0, error)
                self.assertEqual(json.loads(text), D.catalog() if name is None else D.catalog(name))
                self.assertEqual(text, json.dumps(json.loads(text), ensure_ascii=False, default=str) + '\n')

    def test_cli_unknown_duplicate_or_misplaced_selector_refuses_before_file_or_provider(self):
        bad = [['catalog', '--template', value, '--agent-json'] for value in ('', 'Proof', 'proof ', 'unknown')]
        bad += [['catalog', '--template', 'proof', '--template', 'proof', '--agent-json'],
                ['catalog', '--template', 'proof', '--template', 'exact_arithmetic', '--agent-json']]
        bad += [[command, '/not/a/task.json', '--template', 'proof', '--agent-json']
                for command in ('check', 'compile', 'run')]
        with patch.object(symblic_apply, 'Applicators', side_effect=AssertionError('No provider')):
            for arguments in bad:
                status, text, _ = cli(arguments)
                self.assertEqual(status, 1, arguments)
                result = json.loads(text)
                self.assertFalse(result['ok'])
                self.assertEqual(result['errors'][0]['code'], 'catalog_selector')
                self.assertNotIn('templates', result)
            for arguments in (['catalog', '--template'], ['catalog', '--template', '--agent-json']):
                with self.assertRaises(SystemExit) as caught:
                    cli(arguments)
                self.assertEqual(caught.exception.code, 2)


class CatalogFocusAPI(Base):
    def setUp(self):
        super().setUp()
        for target in (patch.dict(host_apps._modules, {'automation_engine': AE}),
                       patch.object(AE, '_ensure_started', side_effect=AssertionError('No scheduler')),
                       patch.object(SG, 'OWNER_EMAILS', {'owner@example.test'})):
            target.start(); self.addCleanup(target.stop)

    def routed(self, suffix='', identity=None):
        handler = RoutedHandler('delegate/catalog', identity=identity)
        handler.path += suffix
        self.assertTrue(host_apps.handle_get(handler))
        return handler

    def assert_no_work(self):
        self.assertEqual(self.apps.calls, [])
        self.assertEqual(self.launches, [])
        self.assertEqual(list(Path(self.tmp).rglob('*')), [])

    def test_owner_default_all_names_and_percent_encoding_return_exact_catalog_without_work(self):
        with patch.object(D, 'compile_task', side_effect=AssertionError('No compiler')):
            for suffix in ('', '?'):
                result = self.routed(suffix)
                self.assertEqual(result.status, 200)
                self.assertEqual(result.sent, D.catalog())
            for name in D.TEMPLATE_VERSIONS:
                result = self.routed('?template=' + name)
                self.assertEqual(result.status, 200, result.sent)
                self.assertEqual(result.sent, D.catalog(name))
            result = self.routed('?%74emplate=%70roof_step_obligation')
            self.assertEqual(result.status, 200)
            self.assertEqual(result.sent, D.catalog('proof_step_obligation'))
        self.assert_no_work()

    def test_raw_query_blanks_duplicates_unknowns_malformed_and_bounds_refuse(self):
        suffixes = ['?template=', '?template', '?template=proof&template=proof',
                    '?template=proof&%74emplate=proof_step', '?template=unknown', '?template=Proof',
                    '?template=proof+', '?template=%FF', '?template=%GG', '?template=proof%00',
                    '?template=proof%0a', '?template=proof&', '?&template=proof', '?Template=proof',
                    '?templates=proof', '?template=proof&ignored=x', '?ignored=x',
                    '?template=' + 'x' * 1025, '?' + '&'.join(['template=proof'] * 9)]
        for suffix in suffixes:
            with self.subTest(query=suffix[:80]):
                response = self.routed(suffix)
                self.assertEqual(response.status, 400, response.sent)
                self.assertTrue(response.sent['error'])
                self.assertNotIn('templates', response.sent)
        self.assert_no_work()

    def test_owner_gate_precedes_even_malformed_selector_and_ignores_forged_header(self):
        with patch.object(E, 'handle', side_effect=AssertionError('Nonowner reached engine')):
            for identity in (SG.Identity(SG.ANONYMOUS), SG.Identity(SG.VERIFIED, 'guest@example.test'),
                             SG.Identity(SG.ANONYMOUS, 'owner@example.test')):
                for suffix in ('', '?template=proof_step_obligation', '?template=%FF', '?template=&template=proof'):
                    self.assertEqual(self.routed(suffix, identity).status, 403)
        self.assert_no_work()

    def test_embedded_query_handlers_refuse_nontext_without_coercion(self):
        for value in (False, 1, [], ['proof'], {'template': 'proof'}, ''):
            handler = Handler({'template': value})
            self.assertTrue(E.handle(handler, 'GET', 'delegate/catalog', {}))
            self.assertEqual(handler.status, 400)
            self.assertNotIn('templates', handler.sent)
        handler = Handler({'template': 'proof'})
        self.assertTrue(E.handle(handler, 'GET', 'delegate/catalog', {}))
        self.assertEqual(handler.sent, D.catalog('proof'))
        self.assert_no_work()


if __name__ == '__main__':
    unittest.main()
