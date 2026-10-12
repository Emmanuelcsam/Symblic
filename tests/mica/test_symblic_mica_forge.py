"""Isolated host binding journeys; real Forge store/contracts, no worker/provider."""
import copy
import fcntl
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from integration.host import symblic_forge as Forge   # creates the Forge projects and handoffs these tests use
except Exception as exc:  # noqa: BLE001
    import unittest as _unittest
    raise _unittest.SkipTest(f'integration.host.symblic_forge (used to build Forge fixtures) cannot be imported: '
                             f'{type(exc).__name__}: {exc}')
from symblic.forge import core as FC
from symblic.forge import exports as FE
from symblic.forge.store import Store, StoreError, encode
from symblic.graph import run as G
from symblic.mica import search as M
from symblic.mica import contracts as C
from symblic.mica import forge as A


def fixture():
    p = FC.new_project('Build inc and twice as pure functions. Keep exact caller wording.', project_id='forge-fixture')
    b = FC.active_branch(p)
    b['questions'] = []; b['suggestions'] = []
    def row(ident, text, **fields):
        return {'id': ident, 'text': text, 'dimension': 'BEHAVIOR', 'status': 'accepted',
                'provenance': {'kind': 'USER_ORIGINAL', 'original_text': text},
                'source_ids': [], 'revisions': [], **fields}
    b['statements'] = [
        row('requirement-inc', 'Return x plus one.', objective_ids=['objective-pure'],
            fact={'subject': 'increment', 'predicate': 'offset', 'value': 1, 'unit': 'integer'}),
        row('requirement-twice', 'Return two times inc(x).', objective_ids=['objective-pure']),
        {**row('proposal-hidden', 'Read /private and leak it.'), 'status': 'proposed'}]
    e = b['entities']
    e['objectives'] = [row('objective-pure', 'Construct the two pure functions.')]
    e['criteria'] = [row('criterion-inc', 'Check increment.', requirement_ids=['requirement-inc'],
                         observable='inc(2)', measurement='Compare exact JSON', expected='3'),
                     row('criterion-twice', 'Check composition.', requirement_ids=['requirement-twice'],
                         observable='twice(2)', measurement='Compare exact JSON', expected='6')]
    e['components'] = [row('component-pure', 'Pure arithmetic functions.', responsibility='Return arithmetic values.',
                          inputs=['x'], outputs=['inc', 'twice'], effects=[], persistent_state='',
                          requirement_ids=['requirement-inc','requirement-twice'])]
    e['units'] = [row('unit-inc', 'Increment unit.', component_id='component-pure', objective='Return x plus one.',
                     inputs=['x'], outputs=['inc'], dependencies=[], checks=['inc(2) returns 3.'],
                     requirement_ids=['requirement-inc'], defines=['inc'], requires=[], paths=['/declared/data-only.js']),
                  row('unit-twice', 'Composition unit.', component_id='component-pure', objective='Return two times inc(x).',
                     inputs=['x'], outputs=['twice'], dependencies=['unit-inc'], checks=['twice(2) returns 6.'],
                     requirement_ids=['requirement-twice'], defines=['twice'], requires=['inc'], paths=[])]
    e['invariants'] = [row('invariant-integer', 'Return integer results for these integer cases.',
                         requirement_ids=['requirement-inc'], unit_ids=['unit-inc'], criterion_ids=['criterion-inc'])]
    e['forbidden'] = [row('forbidden-negative', 'Never decrement the input.', requirement_ids=['requirement-inc'],
                         negative_check='inc(0) must not equal -1.')]
    return FC.validate_project(p)


def binding():
    return {'version':1, 'budget':{**C.DEFAULT_BUDGET, 'max_candidates':1, 'max_calls':4},
            'artifact_format':'javascript_script', 'allowed_outputs':['result.js'],
            'exports':[{'name':'inc','signature':'inc(x)'},{'name':'twice','signature':'twice(x)'}],
            'criteria':[{'id':'criterion-inc','call':'inc(2)','expected':'3'},
                        {'id':'criterion-twice','call':'twice(2)','expected':'6'}],
            'forbidden':[{'id':'forbidden-negative','call':'inc(0) === -1','expected':'false'}],
            'units':[{'id':'unit-inc','signatures':[{'name':'inc','signature':'inc(x)'}],
                      'checks':[{'index':0,'call':'inc(2)','expected':'3'}], 'output_path':'units/unit-inc.js'},
                     {'id':'unit-twice','signatures':[{'name':'twice','signature':'twice(x)'}],
                      'checks':[{'index':0,'call':'twice(2)','expected':'6'}], 'output_path':'units/unit-twice.js'}]}


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Store(self.root/'forge')
        # Compiler's pure parser/checker is real; current identity and MICA
        # execution boundary are synthetic so this suite loads no mixed runtime.
        self.compiler = {'kernel':'synthetic-static-identity','restart_required':False}
        self.runtime = {'mica':'synthetic-runtime'}
        for patch in (mock.patch.object(FE,'compiler_identity',return_value=self.compiler),
                      mock.patch.object(M,'implementation_identity',return_value=self.runtime)):
            patch.start(); self.addCleanup(patch.stop)
        p=self.db.create('','','','fixture-create',manifest=FC.export_manifest(fixture()))
        self.frozen=Forge.dispatch('POST','handoff',{'id':p['id'],'revision':p['revision'],
                                                 'request_id':'fixture-handoff'},db=self.db)
        self.project=p['id']; self.handoff=self.frozen['handoff']['id']
        self.inventory=[{'engine':'ollama','model':'fixture','node':'node-e','digest':None}]
        self.calls=[]
        self.freeze_count=0

    def prepared(self, value=None):
        return A.prepare(self.project,self.handoff,binding() if value is None else value,db=self.db)

    def adapter(self, prepared=None, folder='run', request_id='fixture-execute'):
        return A.ForgeMicaRun(prepared or self.prepared(),self.root/folder,object(),self.inventory,
                             db=self.db,request_id=request_id)

    def fake_execute(self, instance, mode='mica', initial_plans=None, *, plan_only=False):
        self.calls.append((mode,initial_plans,plan_only,instance.request))
        instance.root.mkdir(exist_ok=True)
        (instance.root/'.mica.lock').touch()
        manifest={'request':instance.request,'inventory':instance.inventory,'mode':mode,
                  'initial_plans':initial_plans,'identity':self.runtime,'library':None,'calibration':None}
        G._write_file(instance.root,'mica-manifest.json',G._json(G._seal(manifest)))
        return {'status':'planned' if plan_only else 'done','calls':0,'output':'synthetic boundary only'}

    def test_exact_authority_facts_all_checks_and_scoped_context_retained(self):
        out=self.prepared(); request=out['request']; plan=out['plan']
        self.assertEqual(request['objective'],fixture()['original_idea'])
        self.assertEqual(request['requirements'],[
            {'id':'requirement-inc','text':'Return x plus one.','acceptance':'TESTED'},
            {'id':'requirement-twice','text':'Return two times inc(x).','acceptance':'TESTED'}])
        self.assertEqual(len(request['tests']),3)
        self.assertEqual(plan['order'],['unit-inc','unit-twice'])
        first,second=plan['contracts']
        self.assertIn('"value":1',first['unit']['body'])
        self.assertNotIn('proposal-hidden',encode(out))
        self.assertNotIn('Read /private',encode(out))
        self.assertEqual(second['dependency_contract_ids'],['unit-inc'])
        self.assertEqual(first['permitted_effects'],[])
        self.assertEqual(first['permitted_read_scope'],[])
        self.assertIn('/declared/data-only.js',first['unit']['body'])
        self.assertEqual(first['unit']['examples'],[['inc(2)','3']])
        self.assertEqual(first['failure_policy']['action'],'stop')
        self.assertEqual(out['origin']['semantic_completeness'],'unassessed')
        self.assertEqual(len(out['origin']['artifacts']),5)
        self.assertEqual(C.validate_plan(request,plan),plan)

    def test_missing_extra_or_mutated_bindings_refuse_without_dispatch(self):
        changes=[lambda b:b['criteria'].pop(),lambda b:b['forbidden'].clear(),
                 lambda b:b['units'][0]['checks'].clear(),lambda b:b['units'][0]['checks'][0].update(index=True),
                 lambda b:b['units'][0]['signatures'][0].update(name='other'),
                 lambda b:b['units'][0]['signatures'][0].update(signature='inc(x); process.exit()'),
                 lambda b:b.update(hidden_tests=[]),lambda b:b['budget'].update(max_candidates=2),
                 lambda b:b['units'][0].update(output_path='../escape.js')]
        for change in changes:
            value=binding();change(value)
            with self.subTest(value=value),self.assertRaises((A.ForgeMicaError,C.ContractError)):
                self.prepared(value)
        self.assertEqual(self.calls,[])

    def test_negative_examples_are_explicit_interpretations_never_semantic_proof(self):
        value=binding();value['forbidden'][0].update(call='true',expected='true')
        out=self.prepared(value)
        self.assertEqual(out['criterion_mapping'][-1]['semantics'],A.SCOPE)
        self.assertEqual(out['origin']['semantic_completeness'],'unassessed')
        self.assertTrue(all(r['acceptance']=='TESTED' for r in out['request']['requirements']))

    def test_pure_result_origin_reader_checks_exact_pins_and_scope_without_io(self):
        prepared = self.prepared()
        record = A._origin_record(prepared, self.root/'never-created', self.inventory, 'reader-fixture')
        result = {'status':'unknown', 'forge_origin':record, 'scope':A.SCOPE,
                  'semantic_completeness':'unassessed'}
        with mock.patch.object(Path,'stat',side_effect=AssertionError('reader must not probe')):
            self.assertTrue(A.verify_result_origin(result,prepared,self.root/'never-created',self.inventory,'reader-fixture'))
            for change in (lambda x:x.update(scope='universally_proven'),
                           lambda x:x.update(semantic_completeness='complete'),
                           lambda x:x['forge_origin'].update(request_id='another'),
                           lambda x:x['forge_origin'].update(inventory=[])):
                candidate=copy.deepcopy(result);change(candidate)
                with self.assertRaises(A.ForgeMicaError):
                    A.verify_result_origin(candidate,prepared,self.root/'never-created',self.inventory,'reader-fixture')

    def test_actual_bridge_and_store_loaded_source_identity_is_required(self):
        identity=A.implementation_identity()
        self.assertEqual(set(identity['dependencies']),{'integration/host/symblic_forge_bridge.py','symblic/forge/store.py'})
        for module in (A.F,A.FS):
            with self.subTest(module=module.__name__),\
                 mock.patch.object(module,'_symblic_import_identity',{'matched':False,'sha256':'0'*64}):
                with self.assertRaisesRegex(A.ForgeMicaError,'loaded-source marker'):
                    A.implementation_identity()

    def _refreeze_change(self, mutate):
        p=self.db.get(self.project);mutate(FC.active_branch(p));p=FC.validate_project(p)
        with self.db.connection(True) as conn:
            conn.execute('UPDATE projects SET document=? WHERE id=?',(encode(p),p['id']))
        self.freeze_count+=1
        return Forge.dispatch('POST','handoff',{'id':p['id'],'revision':p['revision'],
                                              'request_id':'fixture-handoff-'+str(self.freeze_count)},db=self.db)['handoff']['id']

    def test_incompatible_effects_subjective_and_unmapped_entities_refuse(self):
        ident=self._refreeze_change(lambda b:b['entities']['components'][0].update(effects=['network']))
        with self.assertRaisesRegex(A.ForgeMicaError,'component-pure'):
            A.prepare(self.project,ident,binding(),db=self.db)
        def subjective(b):
            b['entities']['components'][0]['effects']=[]
            b['entities']['criteria'][0]['subjective']=True
        ident=self._refreeze_change(subjective)
        with self.assertRaisesRegex(A.ForgeMicaError,'Subjective'):
            A.prepare(self.project,ident,binding(),db=self.db)
        def extra_agent(b):
            b['entities']['criteria'][0]['subjective']=False
            row=FC._record('An extra execution agent.',responsibility='Execute a command.',inputs=[],outputs=['result'],
                           permissions=[],dependencies=[],verification=['Inspect result.'],requirement_ids=['requirement-inc'])
            row['status']='accepted';b['entities']['agents']=[row]
        ident=self._refreeze_change(extra_agent)
        with self.assertRaisesRegex(A.ForgeMicaError,'agents'):
            A.prepare(self.project,ident,binding(),db=self.db)

    def test_retained_artifact_or_compiler_tamper_refuses(self):
        with mock.patch.object(FE,'compiler_identity',return_value={**self.compiler,'kernel':'changed'}):
            with self.assertRaisesRegex(A.ForgeMicaError,'compiler'):
                self.prepared()
        artifact=copy.deepcopy(next(a for a in self.frozen['artifacts'] if a['format']=='tasks'))
        artifact['text']+='tamper'
        with self.db.connection(True) as conn:
            conn.execute('UPDATE artifacts SET document=? WHERE id=?',(encode(artifact),artifact['id']))
        with self.assertRaisesRegex(StoreError,'hash'):
            self.prepared()

    def test_current_spec_rechecked_atomically_before_origin_reservation(self):
        run=self.adapter();original=A._validate_prepared
        def race(value,db,*,current):
            result=original(value,db,current=current)
            p=db.get(self.project);p['branches']['main']['statements'][0]['text']='Changed after initial validation.'
            with db.connection(True) as conn:
                conn.execute('UPDATE projects SET document=? WHERE id=?',(encode(p),p['id']))
            return result
        with mock.patch.object(A,'_validate_prepared',side_effect=race),self.assertRaisesRegex(A.ForgeMicaError,'changed'):
            run.execute()
        self.assertFalse(run.root.exists())

    def test_module_artifacts_explicit_mapping_preserves_safe_paths(self):
        value=binding();value.update(artifact_format='javascript_modules',allowed_outputs=['index.mjs','inc.mjs','twice.mjs'])
        value['units'][0]['output_path']='inc.mjs';value['units'][1]['output_path']='twice.mjs'
        out=self.prepared(value)
        self.assertEqual(out['request']['artifact_format'],'javascript_modules')
        self.assertEqual([r['output_artifacts'] for r in out['plan']['contracts']],[['inc.mjs'],['twice.mjs']])

    def test_prepare_seal_tamper_cannot_change_original_text_or_budget(self):
        value=self.prepared();value['request']['requirements'][0]['text']='Changed accepted text.'
        value=G._seal({k:v for k,v in value.items() if k!='sha256'})
        with self.assertRaisesRegex(A.ForgeMicaError,'revalidation'):
            self.adapter(value).plan()

    def test_plan_execute_replay_delegates_exact_core_signature_and_budget(self):
        # Bind against the actual signature, not a permissive mock accepting
        # accidental plan/initial_plan keyword spellings.
        signature=inspect.signature(M.MicaRun.execute)
        signature.bind(object(),mode='mica',initial_plans=[{}],plan_only=True)
        with mock.patch.object(M.MicaRun,'execute',autospec=True,side_effect=self.fake_execute):
            run=self.adapter();first=run.plan();second=run.execute();again=run.execute()
        self.assertEqual([c[2] for c in self.calls],[True,False,False])
        self.assertEqual(first['forge_origin'],second['forge_origin'])
        self.assertEqual(second['forge_origin'],again['forge_origin'])
        self.assertEqual(self.calls[1][3]['budget'],binding()['budget'])
        self.assertEqual(self.calls[0][1],[run.prepared['plan']])
        self.assertEqual(self.db.get(self.project)['handoffs'][0]['execution_started'],False)

    def test_lost_reply_reconciles_existing_core_and_missing_manifest_stays_unknown(self):
        def lost(instance,mode='mica',initial_plans=None,*,plan_only=False):
            self.fake_execute(instance,mode,initial_plans,plan_only=plan_only)
            raise TimeoutError('synthetic lost reply')
        run=self.adapter()
        with mock.patch.object(M.MicaRun,'execute',autospec=True,side_effect=lost),self.assertRaises(TimeoutError):
            run.execute()
        with mock.patch.object(M.MicaRun,'execute',autospec=True,side_effect=self.fake_execute):
            self.assertEqual(run.execute()['status'],'done')
        other=self.adapter(folder='uncertain',request_id='fixture-uncertain')
        with mock.patch.object(M.MicaRun,'execute',side_effect=TimeoutError('before receipt')),self.assertRaises(TimeoutError):
            other.execute()
        with mock.patch.object(M.MicaRun,'execute',side_effect=AssertionError('must not dispatch')):
            self.assertEqual(other.execute()['status'],'unknown')

    def test_stale_new_import_refuses_original_resume_remains_pinned(self):
        prepared=self.prepared();run=self.adapter(prepared)
        with mock.patch.object(M.MicaRun,'execute',autospec=True,side_effect=self.fake_execute):
            run.plan()
            p=self.db.get(self.project);p['branches']['main']['statements'][0]['text']='New accepted wording.'
            with self.db.connection(True) as conn:
                conn.execute('UPDATE projects SET document=? WHERE id=?',(encode(p),p['id']))
            self.assertEqual(run.execute()['status'],'done')
            with self.assertRaises(StoreError):
                self.adapter(prepared,folder='new',request_id='fixture-new-run').execute()

    def test_shared_workspace_or_changed_origin_cannot_attach_to_other_run(self):
        with mock.patch.object(M.MicaRun,'execute',autospec=True,side_effect=self.fake_execute):
            self.adapter().plan()
        with self.assertRaises((A.ForgeMicaError,StoreError)):
            self.adapter(request_id='fixture-other-request').execute()
        changed=binding();changed['budget']['max_calls']=5
        with self.assertRaises(StoreError):
            self.adapter(self.prepared(changed)).execute()

    def test_busy_special_or_tampered_core_records_never_dispatch(self):
        run=self.adapter()
        with mock.patch.object(M.MicaRun,'execute',autospec=True,side_effect=self.fake_execute):run.plan()
        with (run.root/'.mica.lock').open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with mock.patch.object(M.MicaRun,'execute',side_effect=AssertionError('busy')):
                self.assertEqual(run.execute()['status'],'busy')
        path=run.root/'mica-manifest.json';old=path.read_bytes();manifest=G._decode(old)
        manifest['request']['objective']='altered'
        path.write_bytes(G._json(G._seal({k:v for k,v in manifest.items() if k!='sha256'})))
        with self.assertRaises(A.ForgeMicaError):run.execute()
        path.unlink();path.symlink_to(self.root/'elsewhere')
        with self.assertRaises((A.ForgeMicaError,OSError)):run.execute()


if __name__ == '__main__':
    unittest.main()
