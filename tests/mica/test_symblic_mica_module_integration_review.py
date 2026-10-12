"""Integration review regressions: real tiny runtime, fake providers, isolated stores."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from symblic.mica import search as M
from symblic.mica import bundle as B
from symblic.mica import contracts as C
from symblic.mica import project as P
from tests.mica.test_symblic_mica_execution import FakeApps, inventory, request
from tests.mica.test_symblic_mica_project import root_proposal, OBJECTIVE


class ModuleIntegrationReview(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mica-module-integration-')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.seq=0

    def spec(self):
        return {**request(max_calls=2,max_candidates=1), 'artifact_format':'javascript_modules',
                'allowed_outputs':['public/index.mjs']}

    def completed(self, source='function inc(x){return x+1;}'):
        self.seq+=1
        folder=self.base/('run-'+str(self.seq)); apps=FakeApps(lambda req,n:source)
        run=M.MicaRun(self.spec(),folder,apps,inventory())
        result=run.execute(mode='direct')
        self.assertEqual(result['status'],'done',result)
        self.assertTrue(result['module_checks']['passed'])
        self.assertEqual(len(apps.requests),1)
        return folder,apps,result

    def rewrite(self, path, edit):
        original=M.D._unseal(M.D._read(path))
        value={k:copy.deepcopy(v) for k,v in original.items() if k!='sha256'}
        edit(value)
        path.write_text(json.dumps(M.D._seal(value)),encoding='utf-8')

    def replay(self, folder, apps):
        return M.MicaRun(self.spec(),folder,apps,inventory()).execute(mode='direct')

    def test_stop_during_successful_actual_module_checks_cannot_publish_done(self):
        folder=self.base/'stop'; apps=FakeApps(); stop=threading.Event(); original=B.check_bundle
        def stopped_after_check(*args,**kwargs):
            result=original(*args,**kwargs)
            self.assertTrue(result['passed'],result)
            stop.set()
            return result
        with mock.patch.object(B,'check_bundle',side_effect=stopped_after_check):
            result=M.MicaRun(self.spec(),folder,apps,inventory(),stop=stop).execute(mode='direct')
        self.assertEqual(result['status'],'stopped',result)
        self.assertFalse((folder/'mica-result.json').exists())
        self.assertFalse((folder/'branch-000.json').exists())
        self.assertEqual(len(apps.requests),1)
        resumed=self.replay(folder,apps)
        self.assertEqual(resumed['status'],'done',resumed)
        self.assertEqual(len(apps.requests),1)

    def test_original_deadline_reached_during_checks_is_exhausted(self):
        folder=self.base/'deadline'; apps=FakeApps(); run=M.MicaRun(self.spec(),folder,apps,inventory())
        original=B.check_bundle
        def expire_after_check(*args,**kwargs):
            result=original(*args,**kwargs)
            self.assertTrue(result['passed'],result)
            run.started_monotonic=time.monotonic()-run.budget['wall_seconds']-1
            return result
        with mock.patch.object(B,'check_bundle',side_effect=expire_after_check):
            result=run.execute(mode='direct')
        self.assertEqual(result['status'],'exhausted',result)
        self.assertEqual(result['failure'],'RESOURCE_EXHAUSTION')
        self.assertNotIn('bundle',result)

    def test_valid_crash_window_branch_replays_without_provider_dispatch(self):
        folder,apps,first=self.completed(); (folder/'mica-result.json').unlink()
        second=self.replay(folder,apps)
        self.assertEqual(second['bundle'],first['bundle'])
        self.assertEqual(second['module_checks'],first['module_checks'])
        self.assertEqual(second['calls'],1); self.assertEqual(len(apps.requests),1)

    def test_retained_done_branch_requires_bundle_before_publishing_result(self):
        folder,apps,_=self.completed(); (folder/'mica-result.json').unlink()
        self.rewrite(folder/'branch-000.json',lambda row:row['result'].pop('bundle'))
        with self.assertRaises(ValueError): self.replay(folder,apps)
        self.assertFalse((folder/'mica-result.json').exists()); self.assertEqual(len(apps.requests),1)

    def test_retained_branch_and_final_reject_copied_module_check_receipts(self):
        donor_path,donor_apps,donor=self.completed('function inc(x){return 1+x;}')
        for branch in (True,False):
            with self.subTest(branch=branch):
                folder,apps,first=self.completed()
                self.assertNotEqual(first['bundle']['sha256'],donor['bundle']['sha256'])
                self.assertTrue(donor['module_checks']['passed'])
                if branch:
                    (folder/'mica-result.json').unlink()
                    self.rewrite(folder/'branch-000.json',lambda row:row['result'].update(module_checks=donor['module_checks']))
                else:
                    self.rewrite(folder/'mica-result.json',lambda row:row.update(module_checks=donor['module_checks']))
                with self.assertRaises(ValueError): self.replay(folder,apps)
                self.assertEqual(len(apps.requests),1)
        self.assertEqual(len(donor_apps.requests),1)

    def test_recorded_successful_grade_requires_matching_original_cases_and_values(self):
        folder,apps,result=self.completed(); runtime=M.implementation_identity(); spec=C.normalize_request(self.spec())
        mutations=[lambda r:r['module_checks'].update(status='failed'),
                   lambda r:r['module_checks'].update(scope='external'),
                   lambda r:r['module_checks']['module_checks'][0].update(call='1+1'),
                   lambda r:r['module_checks']['module_checks'][0]['observation'].update(value='999'),
                   lambda r:r['module_checks']['module_checks'].pop()]
        for mutate in mutations:
            broken=copy.deepcopy(result); mutate(broken)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                M.verify_result_artifacts(broken,spec,runtime)
        self.assertEqual(len(apps.requests),1)

    def test_parent_and_nested_deadlines_can_only_shorten_verification(self):
        parent=M.DeadlineStop(threading.Event(),time.time()*1000+5000)
        child=M.DeadlineStop(parent,time.time()*1000+60000)
        self.assertLessEqual(child.monotonic_deadline,parent.monotonic_deadline)
        shorter=M.DeadlineStop(child,time.time()*1000+1000)
        self.assertLess(shorter.monotonic_deadline,child.monotonic_deadline)
        apps=FakeApps(); run=M.MicaRun(self.spec(),self.base/'bounds',apps,inventory(),stop=parent)
        self.assertEqual(run.plan(mode='direct')['status'],'planned')
        self.assertLessEqual(run._check_deadline(),parent.monotonic_deadline)
        self.assertLess(run._check_deadline(time.time()*1000+500),parent.monotonic_deadline)
        self.assertEqual(apps.requests,[])
        self.assertFalse(parent.parent.is_set())
        shorter.set()
        self.assertTrue(parent.parent.is_set())
        self.assertTrue(child.wait(0)); self.assertTrue(shorter.is_set())

    def project(self):
        def reply(req,n):
            if 'missing_decisions' in req['prompt']:
                row=root_proposal(); row['request'].update(allowed_outputs=['public/index.mjs'])  # artifact_format is caller authority; the versioned root schema refuses it in a proposal
                return json.dumps(row)
            return 'function inc(x){return x+1;}'
        folder=self.base/'project'; apps=FakeApps(reply)
        project=P.MicaProject(OBJECTIVE,folder,apps,inventory(),
                              {'max_calls':3,'max_candidates':1,'retries':0,'wall_seconds':60},
                              ['public/index.mjs'],artifact_format='javascript_modules')
        return folder,apps,project

    def test_project_passes_original_deadline_to_child_and_verifier(self):
        folder,apps,project=self.project(); original=M.MicaRun; children=[]
        def capture(*args,**kwargs):
            child=original(*args,**kwargs); children.append(child); return child
        with mock.patch.object(P.M,'MicaRun',side_effect=capture):
            result=project.execute(mode='direct')
        self.assertEqual(result['status'],'done',result); self.assertEqual(len(children),1)
        deadline=result['evidence']['deadline_ms']; child=children[0]
        self.assertIsInstance(child.stop,M.DeadlineStop)
        self.assertEqual(child.stop.deadline_ms,deadline)
        self.assertLessEqual(child._check_deadline(),child.stop.monotonic_deadline)
        self.assertEqual(len(apps.requests),2)

    def test_project_read_rejects_top_level_detached_module_receipt(self):
        folder,apps,project=self.project(); result=project.execute(mode='direct')
        self.assertEqual(result['status'],'done',result)
        self.rewrite(folder/P.RESULT,lambda row:row['module_checks'].update(bundle_sha256='0'*64))
        with self.assertRaises(ValueError): P.read_project_result(folder)
        self.assertEqual(len(apps.requests),2)

    def test_project_read_validates_embedded_child_when_separate_receipt_missing(self):
        folder,apps,project=self.project(); result=project.execute(mode='direct')
        self.assertEqual(result['status'],'done',result)
        (folder/'construction'/'mica-result.json').unlink()
        self.assertEqual(P.read_project_result(folder)['bundle'],result['bundle'])
        def detach(row):
            row['child']['module_checks']['bundle_sha256']='0'*64
            row['module_checks']=copy.deepcopy(row['child']['module_checks'])
        self.rewrite(folder/P.RESULT,detach)
        with self.assertRaises(ValueError): P.read_project_result(folder)
        self.assertEqual(len(apps.requests),2)


    def test_independent_unit_declaration_resource_budget_is_not_interface_failure(self):
        spec=self.spec(); apps=FakeApps(); run=M.MicaRun(spec,self.base/'unit-resource',apps,inventory())
        plan=run.plan(mode='direct')['plan']; contract=plan['contracts'][0]
        with mock.patch.object(M.JSC,'check',return_value={'passed':False,'status':'budget','report':'fixture parser resource bound'}), \
                mock.patch.object(M.JS,'test',side_effect=AssertionError('behavior checks cannot follow inconclusive declarations')):
            result=run._unit_checks('function inc(x){return x+1;}',contract,[],time.time()*1000+60000)
        self.assertEqual(result['status'],'blocked',result)
        self.assertEqual(result['failure'],'VERIFICATION_UNKNOWN')
        self.assertEqual(apps.requests,[])

    def test_blocked_unit_verification_does_not_trigger_planner_repair(self):
        spec=self.spec(); spec['budget']['max_candidates']=2
        apps=FakeApps(); run=M.MicaRun(spec,self.base/'blocked-unit',apps,inventory())
        plan=M.direct_plan(C.normalize_request(spec))
        uncertain={'passed':False,'status':'blocked','failure':'VERIFICATION_UNKNOWN','report':'fixture verifier resource bound'}
        with mock.patch.object(run,'_unit_checks',return_value=uncertain):
            result=run.execute(mode='mica',initial_plans=[plan])
        self.assertEqual(result['status'],'blocked',result)
        self.assertEqual(result['failure'],'VERIFICATION_UNKNOWN')
        self.assertEqual(len(apps.requests),1)
        self.assertEqual(result['costs']['provider_calls'],1)
        self.assertEqual(result['calibration']['fresh_observations'],0)



    def test_stopped_unit_verification_keeps_completed_call_ungraded(self):
        apps=FakeApps(); run=M.MicaRun(self.spec(),self.base/'stop-unit-check',apps,inventory())
        def stopped(*args,**kwargs):
            run.stop.set()
            return {'passed':False,'status':'stopped','calls':0,'error':'fixture caller stop'}
        with mock.patch.object(run,'_unit_checks',side_effect=stopped):
            result=run.execute(mode='direct')
        self.assertEqual(result['status'],'stopped',result)
        self.assertEqual(result['costs']['provider_calls'],1)
        self.assertEqual(result['calibration']['fresh_observations'],0)
        self.assertEqual(len(apps.requests),1)

    def test_inconclusive_cached_component_recheck_never_dispatches_replacement(self):
        library=self.base/'library'; producer_apps=FakeApps()
        producer=M.MicaRun(self.spec(),self.base/'producer',producer_apps,inventory(),library=library).execute(mode='direct')
        self.assertEqual(producer['status'],'done',producer)
        consumer_apps=FakeApps(); consumer=M.MicaRun(self.spec(),self.base/'consumer',consumer_apps,inventory(),library=library)
        uncertain={'passed':False,'status':'blocked','failure':'VERIFICATION_UNKNOWN','report':'fixture cached verifier resource bound'}
        with mock.patch.object(consumer,'_unit_checks',return_value=uncertain) as check:
            result=consumer.execute(mode='direct')
        self.assertGreaterEqual(check.call_count,1)
        self.assertEqual(result['status'],'blocked',result)
        self.assertEqual(result['failure'],'VERIFICATION_UNKNOWN')
        self.assertEqual(result['calls'],0); self.assertEqual(consumer_apps.requests,[])
        self.assertEqual(result['calibration']['fresh_observations'],0)
        self.assertEqual(len(producer_apps.requests),1)

    def test_assembled_declaration_resource_budget_stops_without_false_repair(self):
        apps=FakeApps(); run=M.MicaRun(self.spec(),self.base/'assembly-resource',apps,inventory())
        assembled=[]; original_manifest=M.SC.artifact_manifest; original_check=M.JSC.check
        def manifest(*args,**kwargs):
            result=original_manifest(*args,**kwargs); assembled.append(result['output']['text']); return result
        def declarations(source,*args,**kwargs):
            if assembled:
                return {'passed':False,'status':'budget','report':'fixture assembly parser resource bound'}
            return original_check(source,*args,**kwargs)
        with mock.patch.object(M.SC,'artifact_manifest',side_effect=manifest), mock.patch.object(M.JSC,'check',side_effect=declarations):
            result=run.execute(mode='direct')
        self.assertEqual(result['status'],'blocked',result)
        self.assertEqual(result['failure'],'VERIFICATION_UNKNOWN')
        self.assertEqual(len(apps.requests),1)
        self.assertNotIn('bundle',result)

    def test_model_proposal_assigns_explicit_modules_only_with_caller_authority(self):
        spec=self.spec(); spec['allowed_outputs']+=['units/public.mjs']
        proposed={'units':[{'id':'increment','names':['inc'],'heading':'inc(x)','body':'Return x plus one.',
                           'uses':[],'examples':[['inc(2)','3']],'requirements':['increment'],
                           'output_path':'units/public.mjs'}]}
        plan=M.proposal_to_plan(C.normalize_request(spec),proposed)
        self.assertEqual(plan['contracts'][0]['output_artifacts'],['units/public.mjs'])
        for path in ('../outside.mjs','node:fs','unapproved.mjs',spec['allowed_outputs'][0]):
            bad=copy.deepcopy(proposed); bad['units'][0]['output_path']=path
            with self.subTest(path=path),self.assertRaises(ValueError):
                M.proposal_to_plan(C.normalize_request(spec),bad)
        apps=FakeApps(); result=M.MicaRun(spec,self.base/'layout',apps,inventory()).execute(mode='static',initial_plans=[plan])
        self.assertEqual(result['status'],'done',result)
        self.assertEqual({f['path'] for f in result['bundle']['files']},set(spec['allowed_outputs']))
        self.assertEqual(len(apps.requests),1)


if __name__=='__main__': unittest.main()
