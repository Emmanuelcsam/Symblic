"""Requires PYTHONPATH to an isolated coherent tested Symblic snapshot."""
import json,tempfile,unittest
from pathlib import Path
from symblic.mica import bench as B
from symblic.mica import contracts as C

from symblic.mica import cli as CLI
class SplitProposalTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
  self.inventory=self.root/'inventory.json';self.inventory.write_text(json.dumps([{'engine':'ollama','model':'fixture','node':'node-c','digest':'a'*64,'ready':True,'available':True}]))
  self.request=C.normalize_request({'objective':'Return input plus one.','requirements':[{'id':'inc','text':'Increment x.','acceptance':'TESTED'}],'exports':[{'name':'inc','signature':'inc(x)'}],'tests':[{'requirement_ids':['inc'],'call':'inc(1)','expected':'2'}],'allowed_outputs':['result.js'],'budget':{'max_calls':2}})
 def args(self,*more):
  return CLI.parser().parse_args(['benchmark','--root',str(self.root/'records'),'--id','trial','--inventory',str(self.inventory),*more])
 def fixture(self,split):
  path=self.root/'fixture.json';path.write_text(json.dumps({'id':'inc','family':'fixture','split':split,'request':self.request,'hidden_tests':[['inc(2)','3']]}));return path
 def run_cli(self,*args):
  return CLI.dispatch(self.args(*args),implementation={'fixture':'fixed'},runtime_factory=lambda *_a,**_kw:self.fail('dispatched'))
 def test_new_default_is_dev_without_any_dispatch(self):
  out=self.run_cli('--fixture',str(self.fixture('dev')))
  b=B.MicaBenchmark(self.root/'records','trial',out['freeze_sha256'])
  self.assertEqual(b._load()[1]['split'],'dev');self.assertEqual(out['report']['assigned'],6)
 def test_explicit_heldout_is_supported(self):
  out=self.run_cli('--fixture',str(self.fixture('heldout')),'--split','heldout')
  self.assertEqual(B.MicaBenchmark(self.root/'records','trial',out['freeze_sha256'])._load()[1]['split'],'heldout')
 def test_old_heldout_manifest_resume_without_split_is_unchanged(self):
  out=self.run_cli('--fixture',str(self.fixture('heldout')),'--split','heldout');pin=out['freeze_sha256']
  before=(self.root/'records/trial/frozen.json').read_bytes()
  resumed=self.run_cli('--freeze',pin)
  self.assertEqual(resumed['freeze_sha256'],pin);self.assertEqual((self.root/'records/trial/frozen.json').read_bytes(),before)
 def test_explicit_resume_split_change_is_rejected_before_dispatch(self):
  out=self.run_cli('--fixture',str(self.fixture('heldout')),'--split','heldout')
  with self.assertRaises(CLI.CliError) as caught:self.run_cli('--freeze',out['freeze_sha256'],'--split','dev')
  self.assertEqual(caught.exception.code,'benchmark_split')
if __name__=='__main__':unittest.main()
