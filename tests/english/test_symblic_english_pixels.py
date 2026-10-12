"""Isolated compiler/runner evidence, with test-only fake model replies."""
import copy
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from symblic.kernel import language as S
from symblic.english import compiler as E
from symblic.english import pixels as P
from symblic.js import check as J
from symblic.spec import sheets as SP
from symblic.spec import build as BUILD
from symblic.kernel.run import Run

CANDIDATES = {line.split('(')[0].split()[-1]:line for line in
              Path(__file__).with_name('pixel_fixture.js').read_text().splitlines() if line.startswith('function ')}
SMALL_SHEET = '''# example.js
## Unit `next(x)`
Return x plus one.
Examples:
    next(0) ==> 1
## Assemble `example.js`
    /*UNITS*/
'''


class Replies:
    def __init__(self, wrong_first=False):
        self.requests = []
        self.wrong_first = wrong_first

    def call(self, req):
        self.requests.append(copy.deepcopy({k:v for k,v in req.items() if k != 'stop'}))
        name = re.search(r'ask unit_(\w+)\s', req['prompt']).group(1)
        code = CANDIDATES[name]
        if self.wrong_first and len(self.requests) == 1:
            code = 'function delta(pixel,center) { return center-pixel; }'
        return {'ok':True,'text':'```js\n' + code + '\n```','model':'fake','node':'fixture','ms':1}


class Compiler(unittest.TestCase):
    def test_original_source_and_every_clause_are_retained(self):
        out = P.compile_source(P.EXAMPLE)
        self.assertEqual(hashlib.sha256(P.EXAMPLE.encode()).hexdigest(), out['source_sha256'])
        self.assertEqual(34,len(out['statements']))
        self.assertEqual([],out['pixel_build']['unmapped_statements'])
        self.assertNotRegex(P.EXAMPLE,r'\d|[{}\[\]_=<>`"]')
        for stmt in out['statements']:
            self.assertEqual(stmt['text'], P.EXAMPLE.splitlines()[stmt['line']-1][stmt['col']-1:stmt['end_col']])
            self.assertTrue(stmt['native_lines'])
        self.assertTrue(S.check(out['source'],execution_profile='verified')['ok'])

    def test_configuration_comes_from_english_quantities(self):
        source = P.EXAMPLE.replace('three hundred','two hundred')
        out = P.compile_source(source)
        self.assertEqual(200,out['presentation']['center_y'])
        self.assertEqual(800,out['presentation']['width'])
        self.assertEqual(600,out['presentation']['height'])
        self.assertEqual(480000,out['presentation']['buffer']['count'])

    def test_inconsistent_quantities_refused_at_original_statement(self):
        for before,after,line in [('twenty-five','twenty-four',29),('four hundred eighty thousand','four hundred seventy thousand',9),('radius of five','radius of six',29)]:
            with self.subTest(before=before), self.assertRaises(E.EnglishError) as error:
                P.compile_source(P.EXAMPLE.replace(before,after,1))
            self.assertEqual(error.exception.line,line)

    def test_unknown_or_missing_or_duplicate_obligations_refuse(self):
        for source in [P.EXAMPLE + '\nDo anything else.\n', P.EXAMPLE.replace('must be copied directly','may be discarded'), P.EXAMPLE.replace('STATEMENT TEN:','STATEMENT ELEVEN:'), P.EXAMPLE.replace(P.EXAMPLE.split('\n\n')[1]+'\n\n','')]:
            with self.subTest(source=source[:30]), self.assertRaises(E.EnglishError):
                P.compile_source(source)

    def test_model_bodies_not_supplied_and_host_only_assembly(self):
        with mock.patch.object(J,'_js_test',side_effect=AssertionError('compile executed JS')):
            out = P.compile_source(P.EXAMPLE)
        self.assertEqual(9,out['source'].count('\nask unit_'))
        self.assertEqual('not_supplied',out['pixel_build']['candidate_bodies'])
        for body in CANDIDATES.values():
            self.assertNotIn(body,out['source'])
        self.assertEqual('/*UNITS*/',out['pixel_build']['plan']['sheet']['template']['text'])
        self.assertNotIn('by=',out['source'].splitlines()[2])
        self.assertNotIn('by',out['options'])

    def test_all_unit_checks_and_actual_dependency_closures_are_mapped(self):
        out = P.compile_source(P.EXAMPLE)
        for u in out['pixel_build']['units']:
            text = [out['source'].splitlines()[n-1] for n in u['native_lines']]
            self.assertEqual(1,len([s for s in text if s.startswith('ask ')]))
            self.assertEqual(4,len([s for s in text if ' = js_test(' in s]))
            self.assertEqual(1,len([s for s in text if ' = js_declarations_check(' in s]))
        plan = out['pixel_build']['plan']
        rows = {row['id']: row for row in plan['units']}
        for index, ident in enumerate(plan['order']):
            expected = rows[ident]['binding']
            unit = next(u for u in out['pixel_build']['units'] if u['binding'] == expected)
            associated = [out['source'].splitlines()[n-1] for n in unit['native_lines']]
            self.assertTrue(any(line.startswith(f'let assembly_check_{index} =') for line in associated))
            self.assertTrue(any(line.startswith(f'let output_check_{index} =') for line in associated))
        self.assertEqual(['bounds','inside'],out['presentation']['dependencies']['whitePixels'])
        self.assertEqual([],out['presentation']['dependencies']['clearPixels'])
        self.assertEqual(['whitePixels'],out['presentation']['dependencies']['drawPixels'])

    def test_physical_claims_stay_explicit_and_unverified(self):
        out = P.compile_source(P.EXAMPLE)
        p=out['presentation']
        self.assertEqual('unverified',p['physical_status'])
        self.assertEqual({'numerator':1,'denominator':60},p['delay_seconds'])
        self.assertEqual('implementation.js',p['implementation_label'])
        self.assertFalse(p['future_frame_precomputation'])
        self.assertEqual(['compute_column','clear','draw','present','presentation_opportunity','delay'],p['sequence'])
        self.assertEqual(list(range(1,35)),[r['statement'] for r in p['clause_obligations']])
        for row in p['clause_obligations']:
            self.assertEqual(out['statements'][row['statement']-1]['text'],row['text'])
            self.assertIn(row['status'],['physical_unverified','not_run'])
            self.assertTrue(row['software_checks_are_not_physical_proof'])

    def test_timer_requires_the_exact_english_ordinal(self):
        for denominator in ['sixty', 'zero sixty', 'sixty zero', 'one sixtieth']:
            with self.subTest(denominator=denominator), self.assertRaises(E.EnglishError):
                P.compile_source(P.EXAMPLE.replace('one sixtieth of a second', 'one ' + denominator + ' of a second'))

    def test_generated_program_fits_runner_input_and_source_limits(self):
        # 200 000 characters of JSON inputs (the original host's admission rule) and the kernel's MAX_SOURCE
        out = P.compile_source(P.EXAMPLE)
        self.assertLessEqual(len(json.dumps(out['inputs'])), 200000)
        self.assertLessEqual(len(out['source']), S.MAX_SOURCE)
        self.assertEqual(['pixel_vm_boot'], list(out['inputs']))
        native = S.parse(out['source'])['statements']
        parser = next(row for row in native if row.k == 'let' and row.name == 'pixel_vm_parser')
        self.assertEqual('str', parser.value.k)
        self.assertTrue(all(type(piece) is str for piece in parser.value.parts))
        expected = out['pixel_build']['client_vm']['assets']['parser']['sha256']
        self.assertEqual(expected, hashlib.sha256(''.join(parser.value.parts).encode()).hexdigest())

    def test_options_and_matching(self):
        self.assertTrue(P.is_source(P.EXAMPLE))
        self.assertFalse(P.is_source('Build a character animation Matrix rain.'))
        for opts in [{'retries':True},{'max_calls':-1},{'budget':1}]:
            with self.assertRaises(E.EnglishError): P.compile_source(P.EXAMPLE,**opts)
        self.assertIn('budget=12000',P.compile_source(P.EXAMPLE)['source'])

    def test_explicit_generic_routing_stays_default_and_inheritance_is_opt_in(self):
        default=BUILD.compile_cards(SMALL_SHEET,['fake:chosen'])
        self.assertIn('by=["fake:chosen"]',default['source'])
        inherited=BUILD.compile_cards(SMALL_SHEET,None,inherit_applicators=True,retries=0)
        self.assertNotIn('by=',inherited['source'])
        self.assertIn('retries=0',inherited['source'])
        for apps,opts in [(None,{}),(['fake:chosen'],{'inherit_applicators':True}),(['fake:chosen'],{'retries':0}), (None,{'inherit_applicators':1})]:
            with self.assertRaises(SP.SheetError): BUILD.compile_cards(SMALL_SHEET,apps,**opts)


@unittest.skipUnless(J.available(),'Local sandboxed JS unavailable')
class Runtime(unittest.TestCase):
    def test_fake_worker_full_native_journey(self):
        compiled=P.compile_source(P.EXAMPLE,retries=0,max_calls=9)
        worker=Replies()
        with tempfile.TemporaryDirectory(prefix='symblic-dot-fixture-') as folder:
            report=Run(compiled['source'],compiled['inputs'],worker,{**compiled['options'],'by':'fake:selected'},folder=folder).execute()
        self.assertEqual('done',report['status'],report.get('error'))
        self.assertEqual(9,len(worker.requests))
        self.assertEqual('implementation.js',report['outputs'][0]['label'])
        self.assertEqual(P._white(0,300,compiled['pixel_build']['config']),report['outputs'][1]['canonical'])
        self.assertEqual(S.canon(S.from_json(compiled['presentation'])),report['outputs'][2]['canonical'])
        self.assertTrue(all(r.get('app') == S.parse_applicator('fake:selected') for r in worker.requests), [sorted(r) for r in worker.requests])
        self.assertTrue(all(len(r['prompt'])<12000 for r in worker.requests))
        self.assertNotIn('STATEMENT THIRTY-TWO',worker.requests[0]['prompt'])
        self.assertEqual(['pixel_vm_boot'],list(compiled['inputs']))
        self.assertTrue(all('function pixelCheck' not in r['prompt'] for r in worker.requests))
        self.assertTrue(all('pixel_vm_parser' not in r['prompt'] for r in worker.requests))
        for req in worker.requests:
            self.assertEqual([],req['context_manifest']['omitted'])

    def test_bad_candidate_fails_without_host_replacement(self):
        compiled=P.compile_source(P.EXAMPLE,retries=0,max_calls=9)
        worker=Replies(wrong_first=True)
        with tempfile.TemporaryDirectory(prefix='symblic-dot-fixture-') as folder:
            report=Run(compiled['source'],compiled['inputs'],worker,{**compiled['options'],'by':'fake:selected'},folder=folder).execute()
        self.assertEqual('failed',report['status'])
        self.assertEqual(1,len(worker.requests))
        self.assertEqual([],report['outputs'])

    def test_bad_boundaries_clear_and_draw_rejected_by_visible_checks(self):
        units=P._units(P.parse_source(P.EXAMPLE)[1])
        mutations={
            'inside':CANDIDATES['inside'].replace('<= 25','< 25'),
            'nextX':CANDIDATES['nextX'].replace('=== 799','=== 798'),
            'clearPixels':'function clearPixels(buffer){return [];}',
            'drawPixels':CANDIDATES['drawPixels'].replace('const indices', 'buffer.fill(0); const indices'),
        }
        for name,body in mutations.items():
            unit=next(u for u in units if u['name']==name)
            code=[body if key==name else value for key,value in CANDIDATES.items()]
            cases=[{'call':call,'expect':json.loads(expected)} for call,expected in unit['examples']]
            with self.subTest(name=name):
                self.assertFalse(J.test(code,cases)['passed'])
