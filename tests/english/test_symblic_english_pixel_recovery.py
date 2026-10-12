"""Partial construction recovery uses actual local checks and fake provider replies."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from symblic.kernel import language as S
from symblic.english import pixels as P
from symblic.js import check as J
from symblic.spec import build as B
from symblic.kernel.run import Run

CODES={line.split('(')[0].split()[-1]:line for line in
       Path(__file__).with_name('pixel_fixture.js').read_text().splitlines() if line.startswith('function ')}
OLD='Call bounds(cx,cy). Visit only that inclusive search box'
NEW=('Store the result of bounds(cx,cy) in a local variable named searchBox. All supplied function names, '
     'including bounds and inside, are reserved: never reuse them for a variable, parameter or declaration. '
     'Visit only that inclusive search box')

class Worker:
    def __init__(self, fail=False): self.fail,self.requests=fail,[]
    def call(self,req):
        self.requests.append({k:v for k,v in req.items() if k!='stop'})
        name=re.search(r'ask unit_(\w+)\s',req['prompt']).group(1)
        code=CODES[name]
        if name=='whitePixels' and self.fail: code='function whitePixels(cx,cy){const bounds=bounds(cx,cy);return [];}'
        return {'ok':True,'text':'```js\n'+code+'\n```'}

@unittest.skipUnless(J.available(),'Local JS sandbox unavailable')
class Recovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original=P.compile_source(P.EXAMPLE,retries=0,budget=24000)
        baseline=json.loads(Path(__file__).resolve().parents[1].joinpath('fixtures', 'symblic-english-pixels.json').read_text())
        sheet=baseline['compiled']['pixel_build']['sheet']
        if OLD not in sheet or NEW not in original['pixel_build']['sheet']:raise AssertionError('Narrow wording change not found')
        initial=B.compile_cards(sheet,None,inherit_applicators=True,samples=1,retries=0,rounds=1,budget=24000,
                                declaration_contracts=original['pixel_build']['runtime']['compiler_settings']['declaration_contracts'])
        with tempfile.TemporaryDirectory(prefix='symblic-recovery-first-') as folder:
            Path(folder,'program.sym').write_text(initial['source'])
            worker=Worker(True)
            result=Run(initial['source'],{},worker,{**initial['options'],'by':'fake:fixture'},folder=folder).execute()
            if result['status']!='failed':raise AssertionError(result)
            cls.checkpoint=B.checkpoint(folder,recheck_seconds=60)
        cls.compiled=P.compile_source(P.EXAMPLE,artifacts=cls.checkpoint['artifacts'],retries=0)

    def test_seven_rechecked_artifacts_reused_as_exact_bytes(self):
        c=self.compiled;self.assertEqual(7,c['pixel_build']['kept']);self.assertEqual(2,c['source'].count('\nask '))
        expected={u['binding']:self.checkpoint['artifacts'][u['id']]['code'] for u in self.checkpoint['plan']['units'] if u['id'] in self.checkpoint['artifacts']}
        actual={s.name:''.join(s.value.parts) for s in S.parse(c['source'])['statements'] if s.k=='let' and s.name in expected}
        self.assertEqual(expected,actual)
        for u in c['pixel_build']['units']:
            reused=u['name'] in ['delta','square','nextX','bounds','clearPixels','separation','inside']
            self.assertEqual('reused_artifact' if reused else 'model_request',u['acquisition'])
            self.assertEqual('let' if reused else 'ask',u['binding_kind'])
            self.assertEqual(reused,u['artifact_sha256'] is not None)

    def test_source_maps_cover_kept_literals_and_asserts(self):
        c=self.compiled;plan=S.check(c['source'])['plan'];lines={r['line']:r for r in plan}
        for u in c['pixel_build']['units']:
            mapped=[lines[n] for n in u['native_lines']]
            binding=next(r for r in mapped if r.get('binds')==u['binding'])
            self.assertEqual(u['binding_kind'],binding['kind'])
            guards=[r for r in mapped if r['kind'] in ['assert','ensure']]
            self.assertEqual(5,len(guards));self.assertEqual(0 if u['acquisition']=='reused_artifact' else 3,len([r for r in guards if r['kind']=='ensure']))
            for index in u['clauses']:
                self.assertTrue(set(u['native_lines'])<=set(c['statements'][index-1]['native_lines']))

    def test_recovery_fits_runner_admission_with_seven_retained_units(self):
        # the bounds a run's inputs and source must fit: at most 200 000 characters of JSON inputs (the original
        # host's admission rule, kept as the portability bound) and the kernel's MAX_SOURCE
        c = self.compiled
        self.assertEqual(7, c['pixel_build']['kept'])
        self.assertLessEqual(len(json.dumps(c['inputs'])), 200000)
        self.assertLessEqual(len(c['source']), S.MAX_SOURCE)

    def test_only_two_new_calls_complete_fresh_english_run(self):
        c=self.compiled;worker=Worker()
        with tempfile.TemporaryDirectory(prefix='symblic-recovery-second-') as folder:
            report=Run(c['source'],c['inputs'],worker,{**c['options'],'by':'fake:selected'},folder=folder).execute()
        self.assertEqual('done',report['status'],report.get('error'))
        self.assertEqual(['whitePixels','drawPixels'],[re.search(r'ask unit_(\w+)\s',r['prompt']).group(1) for r in worker.requests])
        self.assertTrue(all(len(r['prompt'])<12000 for r in worker.requests))
        self.assertTrue(all('pixel_vm_parser' not in r['prompt'] and 'function pixelCheck' not in r['prompt'] for r in worker.requests))
        self.assertIn('searchBox',worker.requests[0]['prompt']);self.assertIn('never reuse',worker.requests[0]['prompt'])
        self.assertEqual(3,len(report['outputs']));self.assertEqual('implementation.js',report['outputs'][0]['label'])
        self.assertEqual(S.canon(S.from_json(c['presentation'])),report['outputs'][2]['canonical'])

    def test_changed_code_token_is_never_silently_kept(self):
        artifacts=copy.deepcopy(self.checkpoint['artifacts']);ident=next(iter(artifacts));artifacts[ident]['code']+='\n'
        c=P.compile_source(P.EXAMPLE,artifacts=artifacts)
        unit=next(u for u in c['pixel_build']['plan']['units'] if u['id']==ident)
        meta=next(u for u in c['pixel_build']['units'] if u['binding']==unit['binding'])
        self.assertEqual('model_request',meta['acquisition']);self.assertLess(c['pixel_build']['kept'],7)

    def test_changed_english_configuration_invalidates_prior_contracts(self):
        c=P.compile_source(P.EXAMPLE.replace('three hundred','two hundred'),artifacts=self.checkpoint['artifacts'])
        self.assertEqual(0,c['pixel_build']['kept']);self.assertEqual(9,c['source'].count('\nask '))

    def test_only_white_pixels_and_draw_contracts_changed_and_original_document_stays_exact(self):
        before={u['exports'][0]:u['contract'] for u in self.checkpoint['plan']['units']}
        after={u['exports'][0]:u['contract'] for u in self.compiled['pixel_build']['plan']['units']}
        self.assertEqual(['whitePixels','drawPixels'],[name for name in before if before[name]!=after[name]])
        self.assertEqual(P.parse_source(P.EXAMPLE)[0][33]['text'],self.compiled['statements'][33]['text'])
        self.assertEqual(34,len(self.compiled['presentation']['clause_obligations']))
