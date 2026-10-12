"""CLI seam: temporary Forge state and JSON files, no providers or live stores."""
import copy
import io
import json
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
from symblic.forge.store import Store
from symblic.graph import run as G
from symblic.mica import search as M
from symblic.mica import cli as L
from symblic.mica import forge as A
from symblic.mica import forge_cli as CLI
from tests.mica.test_symblic_mica_forge import fixture, binding


class ForgeCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-cli-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = Store(self.root / 'forge')
        self.compiler = {'kernel':'synthetic-cli-identity','restart_required':False}
        self.runtime = {'mica':'synthetic-cli-runtime'}
        for patch in (mock.patch.object(FE,'compiler_identity',return_value=self.compiler),
                      mock.patch.object(M,'implementation_identity',return_value=self.runtime)):
            patch.start();self.addCleanup(patch.stop)
        stored = self.db.create('', '', '', 'cli-create', manifest=FC.export_manifest(fixture()))
        frozen = Forge.dispatch('POST','handoff',{'id':stored['id'],'revision':stored['revision'],
                          'request_id':'cli-handoff'},db=self.db)
        self.project, self.handoff = stored['id'], frozen['handoff']['id']
        self.prepared = A.prepare(self.project,self.handoff,binding(),db=self.db)
        self.inventory = [{'model':'fixture','engine':'ollama','node':'node-e','ready':True,'available':True}]
        self.files = {}
        for name,value in [('binding',binding()),('prepared',self.prepared),('inventory',self.inventory)]:
            path=self.root/(name+'.json');path.write_text(json.dumps(value));self.files[name]=str(path)
        self.calls=[]

    def args(self, command):
        return [command,self.files['prepared'],'--dir',str(self.root/'run'),
                '--inventory',self.files['inventory'],'--request-id','cli-original-build']

    def invoke(self, args, factory=None):
        stream=io.StringIO()
        code=CLI.main(args,out=stream,runtime_factory=factory,store_factory=lambda _:self.db)
        return code,json.loads(stream.getvalue())

    def factory(self, prepared, directory, inventory, *, db, request_id):
        self.calls.append((copy.deepcopy(prepared),directory,copy.deepcopy(inventory),db,request_id))
        record=A._origin_record(prepared,directory,inventory,request_id)
        class Run:
            def plan(self):return {'status':'planned','calls':0,'forge_origin':record,'scope':A.SCOPE,'semantic_completeness':'unassessed'}
            def execute(self):return {'status':'done','calls':2,'forge_origin':record,'scope':A.SCOPE,'semantic_completeness':'unassessed'}
        return Run()

    def retain_plan(self):
        def core(run, mode='mica', initial_plans=None, *, plan_only=False):
            self.assertEqual(mode,'mica');self.assertTrue(plan_only)
            run.root.mkdir(mode=0o700);(run.root/'.mica.lock').touch()
            manifest={'version':1,'request':run.request,'inventory':run.inventory,'mode':mode,
                      'initial_plans':initial_plans,'identity':self.runtime,'library':None,'calibration':None}
            G._write_file(run.root,'mica-manifest.json',G._json(G._seal(manifest)))
            return {'status':'planned','calls':0}
        with mock.patch.object(M.MicaRun,'execute',autospec=True,side_effect=core):
            A.ForgeMicaRun(self.prepared,self.root/'run',object(),self.inventory,db=self.db,
                          request_id='cli-original-build').plan()

    def test_help_and_prepare_are_inert_and_exact_sealed_binding(self):
        with mock.patch.object(CLI,'_store',side_effect=AssertionError('help must not open store')):
            code,result=self.invoke(['--help'])
        self.assertEqual(code,0)
        self.assertIn('execute is explicit native resume',result['usage'])
        code,result=self.invoke(['prepare',self.project,self.handoff,'--binding',self.files['binding']],self.factory)
        self.assertEqual(code,0,result);self.assertEqual(result,self.prepared)
        self.assertEqual(self.calls,[])

    def test_plan_execute_and_repeat_preserve_exact_authority_budget_and_id(self):
        for command in ('plan','execute','execute'):
            code,result=self.invoke(self.args(command),self.factory)
            self.assertEqual(code,0,result)
            self.assertEqual(result['status'],'planned' if command=='plan' else 'done')
        self.assertEqual(len(self.calls),3)
        for prepared,directory,inventory,db,request_id in self.calls:
            self.assertEqual(prepared,self.prepared)
            self.assertEqual(prepared['request']['budget'],self.prepared['binding']['budget'])
            self.assertEqual(directory,self.root/'run')
            self.assertIs(db,self.db);self.assertEqual(request_id,'cli-original-build')

    def test_bad_input_symlink_and_bad_result_origin_refuse(self):
        linked=self.root/'link.json';linked.symlink_to(self.files['prepared'])
        args=self.args('execute');args[1]=str(linked)
        code,result=self.invoke(args,self.factory)
        self.assertEqual(code,2);self.assertEqual(self.calls,[])
        def bad(*args,**kwargs):
            run=self.factory(*args,**kwargs)
            run.execute=lambda:{'status':'done','forge_origin':{},'scope':'proven'}
            return run
        code,result=self.invoke(self.args('execute'),bad)
        self.assertEqual(code,2);self.assertEqual(result['error']['code'],'origin')

    def test_readers_do_not_dispatch_and_reject_changed_core_or_forge_origin(self):
        self.retain_plan()
        with mock.patch.object(M.MicaRun,'execute',side_effect=AssertionError('read cannot execute')):
            code,result=self.invoke(self.args('status'))
            self.assertEqual(code,0,result);self.assertEqual(result['status'],'incomplete')
            self.assertIn('original plan command returns the validated plan',result['note'])
            self.assertEqual(result['forge_origin']['prepared_sha256'],self.prepared['sha256'])
            path=self.root/'run/mica-manifest.json';manifest=G._unseal(G._read(path))
            manifest.pop('sha256');manifest['request']['objective']='Different root'
            path.write_bytes(G._json(G._seal(manifest)))
            code,result=self.invoke(self.args('status'))
            self.assertEqual(code,2,result);self.assertEqual(result['error']['code'],'origin')
            args=self.args('status');args[-1]='different-request'
            code,result=self.invoke(args)
            self.assertEqual(code,0,result);self.assertEqual(result['status'],'not_started')

    def test_unknown_origin_missing_manifest_is_read_without_relaunch(self):
        self.retain_plan();(self.root/'run/mica-manifest.json').unlink()
        with mock.patch.object(M.MicaRun,'execute',side_effect=AssertionError('read cannot execute')):
            code,result=self.invoke(self.args('status'))
        self.assertEqual(code,0,result);self.assertEqual(result['status'],'unknown')
        self.assertEqual(result['failure'],'UNRESOLVED_EFFECT')

    def test_artifact_reader_uses_original_runtime_after_unrelated_upgrade(self):
        self.retain_plan()
        _,manifest,_=L._run_records(self.root/'run')
        result={'status':'done','bundle':{'fixture':'only core-reader seam'},'assurance':'TESTED'}
        with mock.patch.object(M,'implementation_identity',return_value={'mica':'later'}),\
             mock.patch.object(L,'_run_records',return_value=(self.root/'run',manifest,result)),\
             mock.patch.object(L,'_bundle_artifacts',return_value=([{'file':'index.mjs'}],{})) as helper,\
             mock.patch.object(M.MicaRun,'execute',side_effect=AssertionError('read cannot execute')):
            code,response=self.invoke(self.args('artifacts')+['--include-text','--archive'])
        self.assertEqual(code,0,response)
        self.assertEqual(response['artifacts'],[{'file':'index.mjs'}])
        self.assertEqual(helper.call_args.kwargs['runtime_identity'],self.runtime)
        self.assertTrue(helper.call_args.kwargs['include_archive'])


if __name__=='__main__':
    unittest.main()
