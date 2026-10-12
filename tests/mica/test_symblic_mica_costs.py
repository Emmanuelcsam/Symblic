import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from symblic.mica import costs as T


class CostAccounting(unittest.TestCase):
    def setUp(self):
        self.rows = []

    def emit(self, kind, **fields):
        self.rows.append({'kind': kind, **fields})

    def test_exceptions_keep_measured_cost_and_do_not_change_verdict(self):
        clock = iter([100, 160]); cpu = iter([10, 30])
        with self.assertRaisesRegex(RuntimeError, 'original'):
            with T.measure(self.emit, 'verification', 'fixture', clock=lambda:next(clock), cpu=lambda:next(cpu)):
                raise RuntimeError('original')
        group=T.summarize(self.rows)['groups'][0]
        self.assertEqual(group['raised'],1)
        self.assertEqual(group['counters']['elapsed_ns']['known_sum'],60)
        self.assertEqual(group['counters']['host_thread_cpu_ns']['known_sum'],20)

    def test_nested_exclusive_cost_does_not_double_count_operation(self):
        clock=iter([0,10,30,50]); cpu=iter([0,2,8,10])
        kw={'clock':lambda:next(clock),'cpu':lambda:next(cpu)}
        with T.measure(self.emit,'assembly','outer',**kw):
            with T.measure(self.emit,'verification','inner',**kw): pass
        summary=T.summarize(self.rows)
        self.assertEqual(sum(g['counters']['exclusive_ns']['known_sum'] for g in summary['groups']),50)
        self.assertEqual(sum(g['counters']['exclusive_host_thread_cpu_ns']['known_sum'] for g in summary['groups']),10)
        self.assertEqual(sum(g['counters']['elapsed_ns']['known_sum'] for g in summary['groups']),70)

    def test_interrupted_cost_is_unknown_and_never_zero_total(self):
        self.emit('cost_started',cost_id='a'*32,category='verification',label='killed',version=1)
        summary=T.summarize(self.rows); group=summary['groups'][0]
        self.assertEqual(summary['interrupted'],1)
        self.assertIsNone(group['counters']['elapsed_ns']['completed_span_total'])
        self.assertEqual(group['counters']['elapsed_ns']['known_sum'],0)
        self.assertEqual(T.combine([summary])['interrupted'],1)

    def test_invalid_pair_and_counter_refused(self):
        with T.measure(self.emit,'scheduler','routing'): pass
        for edit in [lambda x:x.append(x[-1]),lambda x:x.reverse(),lambda x:x[1].update(elapsed_ns=True),
                     lambda x:x[1].update(exclusive_ns=x[1]['elapsed_ns']+1),lambda x:x[0].update(version=3)]:
            rows=copy.deepcopy(self.rows);edit(rows)
            with self.assertRaises(ValueError):T.summarize(rows)

    def test_two_threads_keep_separate_nesting_and_explicit_overlap(self):
        barrier=threading.Barrier(2); lock=threading.Lock()
        def emit(kind,**fields):
            with lock:self.emit(kind,**fields)
        def worker():
            with T.measure(emit,'verification','parallel'):
                barrier.wait(timeout=2)
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=3)
        self.assertTrue(all(not t.is_alive() for t in threads))
        summary=T.summarize(self.rows)
        self.assertEqual(summary['completed'],2)
        self.assertIn('may_overlap',summary['wall_semantics'])
        self.assertEqual(summary['coverage'],'partial_instrumented_scopes_only')


class CostRuntime(unittest.TestCase):
    def test_real_checker_and_native_predicates_record_cost_once_on_replay(self):
        from symblic.mica import search as M
        from symblic.mica import native as N
        from tests.mica.test_symblic_mica_execution import FakeApps,inventory,request
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; apps=FakeApps()
            first=M.MicaRun(request(),folder,apps,inventory()).execute(mode='direct')
            self.assertEqual(first['status'],'done',first)
            costs=first['host_costs']; self.assertGreater(costs['completed'],3)
            self.assertEqual(costs['interrupted'],0)
            self.assertGreater(costs['groups'][0]['counters']['elapsed_ns']['known_sum'],0)
            native=next((folder/'attempts').iterdir())
            self.assertGreater(N.cost_summary(native)['completed'],0)
            before=(folder/'mica-events.jsonl').read_bytes()
            second=M.MicaRun(request(),folder,apps,inventory()).execute(mode='direct')
            self.assertEqual(second['host_costs'],costs)
            self.assertEqual(before,(folder/'mica-events.jsonl').read_bytes())
            self.assertEqual(len(apps.requests),1)

    def test_inconclusive_checker_retains_cost_without_false_quality_observation(self):
        from symblic.mica import search as M
        from tests.mica.test_symblic_mica_execution import FakeApps,inventory,request
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'
            with mock.patch.object(M.JSC,'check',return_value={'passed':False,'status':'budget','report':'resource'}):
                result=M.MicaRun(request(),folder,FakeApps(),inventory()).execute(mode='direct')
            self.assertEqual(result['status'],'blocked',result)
            self.assertEqual(result['failure'],'VERIFICATION_UNKNOWN')
            self.assertEqual(result['routing_observations']['unique_observations'],0)
            self.assertEqual(result['calls'],1)
            self.assertEqual(result['host_costs']['groups'][0]['raised'],1)
            self.assertGreater(result['host_costs']['completed'],0)

    def test_native_declaration_scope_preserves_plain_reports_and_resets(self):
        from symblic.kernel import language as S
        from symblic.js import contract as JSC
        from symblic.js import check as JS
        record={'passed':False,'status':'budget','report':'test limit'}
        with mock.patch.object(JSC,'check',return_value=record):
            plain=JSC._js_declarations_check(S.Kernel(),None,'',{'version':1,'exports':{}})
            self.assertEqual(plain['status'],'budget')
            with JSC.require_complete_scope():
                with self.assertRaises(JS.JsError) as caught:
                    JSC._js_declarations_check(S.Kernel(),None,'',{'version':1,'exports':{}})
            self.assertEqual(caught.exception.kind,'resource')
            again=JSC._js_declarations_check(S.Kernel(),None,'',{'version':1,'exports':{}})
            self.assertEqual(again['status'],'budget')

    def test_changed_summary_refused_on_replay_without_new_model_call(self):
        from symblic.mica import search as M
        from tests.mica.test_symblic_mica_execution import FakeApps,inventory,request
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; apps=FakeApps()
            result=M.MicaRun(request(),folder,apps,inventory()).execute(mode='direct')
            self.assertEqual(result['status'],'done')
            result.pop('sha256')
            result['host_costs']['groups'][0]['counters']['elapsed_ns']['known_sum']+=1
            import json
            (folder/'mica-result.json').write_text(json.dumps(M.D._seal(result)))
            with self.assertRaisesRegex(ValueError,'cost summary'):
                M.MicaRun(request(),folder,apps,inventory()).execute(mode='direct')
            self.assertEqual(len(apps.requests),1)

    def test_project_combines_root_and_construction_without_double_counting(self):
        from symblic.mica import project as P
        from tests.mica.test_symblic_mica_execution import FakeApps,inventory,request,proposal
        from tests.mica.test_symblic_mica_project import OBJECTIVE,root_proposal
        import json
        replies=[json.dumps(root_proposal()),json.dumps(proposal()),'function inc(x){return x+1;}']
        with tempfile.TemporaryDirectory() as tmp:
            apps=FakeApps(lambda req,n:replies[n-1])
            result=P.MicaProject(OBJECTIVE,Path(tmp)/'p',apps,inventory(),budget=request()['budget'],allowed_outputs=['result.js']).execute()
            self.assertEqual(result['status'],'done',result)
            roots=[P.N.cost_summary(path) for path in sorted((Path(tmp)/'p'/'root-attempts').iterdir())]
            self.assertEqual(result['host_costs'],T.combine(roots+[result['child']['host_costs']]))
            self.assertEqual(result['host_costs']['coverage'],'partial_instrumented_scopes_only')
            self.assertEqual(result['calls'],3)
