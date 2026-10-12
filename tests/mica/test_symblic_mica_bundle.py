"""No providers or shell sessions: fixed functions executed in the required JS sandbox."""
import copy
import json
import io
import stat
import zipfile
import subprocess
import time
import unittest
from unittest import mock

from symblic.js import check as JS
from symblic.mica import bundle as B
from symblic.mica import contracts as C
from symblic.spec import contracts as SC

RUNTIME = {'kernel':'fixture','javascript':'fixture-original-checks'}


def fixture(*, sources=None, root_call='inc(2)', expected='3'):
    request = {'artifact_format':'javascript_modules','objective':'Expose an increment through a helper module.',
               'requirements':[{'id':'increment','text':'Increment integers','acceptance':'TESTED'}],
               'exports':[{'name':'inc','signature':'inc(x)'}],
               'tests':[{'requirement_ids':['increment'],'call':root_call,'expected':expected}],
               'allowed_outputs':['package/index.mjs','package/helpers/add.mjs','package/inc.mjs']}
    contracts = []
    for ident, name, uses, deps, output in [
            ('helper','addOne',[],[],'package/helpers/add.mjs'),
            ('increment','inc',['addOne(x)'],['helper'],'package/inc.mjs')]:
        contracts.append({'contract_id':ident,'root_requirement_ids':['increment'],'objective':'Increment integers',
                          'dependency_contract_ids':deps,'output_artifacts':[output],
                          'unit':{'names':[name],'heading':name+'(x)','body':'Return x + 1',
                                  'uses':uses,'setup':'','examples':[[name+'(2)','3']]},
                          'verification_obligations':[{'kind':'unit_examples','requirement_ids':['increment']}]})
    plan = C.validate_plan(request,{'id':'bundle','contracts':contracts})
    sources = sources or {'addOne':'function addOne(x) {return x+1;}',
                          'inc':'function inc(x) {return addOne(x);}'}
    native = plan['spec_plan']; artifacts = {}
    for ident in native['assembly_order']:
        unit = next(u for u in native['units'] if u['id'] == ident)
        code = sources[unit['exports'][0]]
        artifacts[ident] = SC.record_artifact(native,ident,code,artifacts,runtime_identity=RUNTIME,
            checks=[{'passed':True,'scope':'fixture_receipt_not_authority','subject_sha256':SC.code_hash(code)}])
    return request,plan,artifacts


def compiled(**kwargs):
    request,plan,artifacts = fixture(**kwargs)
    return B.compile_bundle(request,plan,artifacts,runtime_identity=RUNTIME)


@unittest.skipUnless(JS.available(), 'required native sandbox unavailable')
class BundleTests(unittest.TestCase):
    def test_actual_three_files_nested_static_imports_and_independent_checks(self):
        bundle = compiled()
        self.assertEqual(B.verify_bundle(bundle)['files'],3)
        files = {f['path']:f for f in bundle['files']}
        self.assertEqual(files['package/inc.mjs']['imports'][0]['specifier'],'./helpers/add.mjs')
        self.assertIn('export {inc} from "./inc.mjs";',files['package/index.mjs']['text'])
        self.assertNotIn('function',files['package/index.mjs']['text'])
        report = B.check_bundle(bundle)
        self.assertTrue(report['passed'],report)
        self.assertEqual(report['total'],3)
        self.assertTrue(report['root']['passed'])
        self.assertEqual([r['scope'] for r in report['module_checks']],['unit','unit','root'])
        self.assertIn('actual_strict_es_module',report['scope'])

    def test_deterministic_bytes_and_deep_detached_manifest(self):
        request,plan,artifacts = fixture()
        first = B.compile_bundle(request,plan,artifacts,runtime_identity=RUNTIME)
        second = B.compile_bundle(request,plan,artifacts,runtime_identity=RUNTIME)
        self.assertEqual(first,second)
        artifacts.clear(); request['tests'].clear(); plan['contracts'].clear()
        self.assertTrue(B.verify_bundle(first)['ok'])

    def test_every_path_hash_bytes_import_and_dependency_checked_even_if_resealed(self):
        original = compiled()
        mutations = [lambda b:b['files'][0].update(path='../secret.js'),
                     lambda b:b['files'][0].update(text='export function addOne(){return 999;}'),
                     lambda b:b['files'][0].update(sha256='0'*64),
                     lambda b:b['files'][0].update(utf8_bytes=1),
                     lambda b:b['files'][1]['imports'][0].update(path='node:fs'),
                     lambda b:b['files'][1]['imports'][0].update(names=['process']),
                     lambda b:b['files'].pop(),
                     lambda b:b.update(entry='package/inc.mjs'),
                     lambda b:b.update(exports=['addOne']),
                     lambda b:b['module_runtime']['assets'].update(prelude='0'*64)]
        for mutation in mutations:
            changed = copy.deepcopy(original); mutation(changed)
            changed = B._seal({k:v for k,v in changed.items() if k != 'sha256'})
            with self.subTest(mutation=mutation),self.assertRaises((B.BundleError,SC.ContractError)):
                B.verify_bundle(changed)
        with self.assertRaises(SC.ContractError):
            B.verify_bundle(original,source_runtime_identity={'other':'runtime'})

    def test_unmatched_allowed_output_and_entry_unit_collision_refused(self):
        request,plan,artifacts = fixture()
        manifest = SC.artifact_manifest(plan['spec_plan'],artifacts,runtime_identity=RUNTIME)
        request['allowed_outputs'].append('ignored.js')
        with self.assertRaises((B.BundleError,C.ContractError)):
            changed = C.validate_plan(request,{'id':'extra','contracts':plan['contracts']})
            B._build(request,changed,manifest)
        request,plan,_ = fixture(); rows = [{k:v for k,v in copy.deepcopy(r).items() if k != 'content_hash'} for r in plan['contracts']]
        rows[1]['output_artifacts'] = [request['allowed_outputs'][0]]
        with self.assertRaises((B.BundleError,C.ContractError)):
            changed = C.validate_plan(request,{'id':'collision','contracts':rows})
            B._build(request,changed,manifest)

    def test_multiple_unit_outputs_setup_and_reserved_names_refused(self):
        request,plan,artifacts = fixture()
        for update in ('outputs','setup'):
            rows = [{k:v for k,v in copy.deepcopy(r).items() if k != 'content_hash'} for r in plan['contracts']]
            if update == 'outputs': rows[0]['output_artifacts'].append('extra.js'); request2={**request,'allowed_outputs':[*request['allowed_outputs'],'extra.js']}
            else: rows[0]['unit']['setup']='function testHelper(){}'; request2=request
            with self.subTest(update=update),self.assertRaises((B.BundleError,C.ContractError)):
                changed = C.validate_plan(request2,{'id':update,'contracts':rows})
                native = changed['spec_plan']; tokens = {}
                for unit in native['units']:
                    code = artifacts[next(x for x in artifacts if artifacts[x]['exports'] == unit['exports'])]['code']
                    tokens[unit['id']] = SC.record_artifact(native,unit['id'],code,tokens,runtime_identity=RUNTIME,
                        checks=[{'passed':True,'scope':'fixture','subject_sha256':SC.code_hash(code)}])
                B.compile_bundle(request2,changed,tokens,runtime_identity=RUNTIME)

    def test_manifest_receipts_do_not_bypass_original_declarations_or_examples(self):
        with self.assertRaisesRegex(B.BundleError,'exact function'):
            compiled(sources={'addOne':'function addOne(x){return x+1;} function smuggled(){}','inc':'function inc(x){return addOne(x);}'})
        bundle = compiled(sources={'addOne':'function addOne(x){return 0;}','inc':'function inc(x){return addOne(x);}'})
        result = B.check_bundle(bundle)
        self.assertFalse(result['passed']); self.assertEqual(result['stage'],'original_unit_examples')

    def test_actual_module_strict_this_differs_from_classic_finite_examples(self):
        bundle = compiled(sources={'addOne':'function addOne(x){return this === undefined ? 99 : x+1;}',
                                   'inc':'function inc(x){return addOne(x);}'})
        report = B.check_bundle(bundle)
        self.assertTrue(report['root']['passed'])
        self.assertFalse(report['passed']); self.assertEqual(report['status'],'failed')
        self.assertEqual(report['module_checks'][0]['observation']['value'],'99')

    def test_public_entry_hides_private_helper_from_root_examples(self):
        bundle = compiled(root_call='addOne(2)')
        report = B.check_bundle(bundle)
        self.assertTrue(report['root']['passed']); self.assertFalse(report['passed'])
        self.assertEqual(report['module_checks'][-1]['observation']['kind'],'error')

    def test_unit_checks_get_own_and_declared_dependency_exports(self):
        request,plan,artifacts = fixture(); rows=[{k:v for k,v in copy.deepcopy(r).items() if k != 'content_hash'} for r in plan['contracts']]
        rows[1]['unit']['examples'].append(['addOne(4)','5'])
        plan = C.validate_plan(request,{'id':'dependency-check','contracts':rows})
        native=plan['spec_plan']; tokens={}
        for unit in native['units']:
            code=artifacts[unit['id']]['code']
            tokens[unit['id']]=SC.record_artifact(native,unit['id'],code,tokens,runtime_identity=RUNTIME,
                checks=[{'passed':True,'scope':'fixture','subject_sha256':SC.code_hash(code)}])
        result=B.check_bundle(B.compile_bundle(request,plan,tokens,runtime_identity=RUNTIME))
        self.assertTrue(result['passed'],result); self.assertEqual(result['total'],4)

    def test_nested_dynamic_import_and_meta_never_reach_loader(self):
        for body in ('return import("node:fs");','return ()=>import("./missing.mjs");','return import.meta;'):
            code={'addOne':'function addOne(x){'+body+'}','inc':'function inc(x){return addOne(x);}'}
            if 'import.meta' in body:
                # Classic declaration parser rejects import.meta first.
                with self.assertRaises(B.BundleError): compiled(sources=code)
            else:
                bundle=compiled(sources=code)
                result=B._evaluate(bundle,B._cases(bundle))
                self.assertEqual(result['status'],'invalid',result)

    def test_no_host_constructors_process_require_or_error_objects(self):
        bundle=compiled()
        expressions = [
            '[typeof process,typeof require,typeof fetch,typeof WebSocket]',
            '(()=>{try{return ({}).constructor.constructor("return process")()}catch(e){try{return e.constructor.constructor("return process")()}catch(_){return "blocked"}}})()',
            '(()=>{try{return globalThis.constructor.constructor("return process")()}catch(_){return "blocked"}})()',
            '(()=>{try{return __symblicModuleCheck.constructor("return process")()}catch(_){return "blocked"}})()',
        ]
        expected=['["undefined","undefined","undefined","undefined"]','"blocked"','"blocked"','"blocked"']
        cases=B._cases(bundle)
        probe=[{**cases[-1],'call':call,'expected':want} for call,want in zip(expressions,expected)]
        observed=B._evaluate(bundle,probe)
        self.assertEqual(observed['status'],'completed',observed)
        self.assertEqual([r.get('value') for r in observed['results']],expected)

    def test_thrown_hostile_proxy_error_getters_not_invoked_by_host(self):
        bundle=compiled(); base=B._cases(bundle)[-1]
        calls=['(()=>{throw new Proxy({}, {get(){while(true){}},getPrototypeOf(){while(true){}}})})()',
               '(()=>{const e=new Error();Object.defineProperty(e,"message",{get(){while(true){}}});throw e})()']
        result=B._evaluate(bundle,[{**base,'call':call} for call in calls],case_ms=100)
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual([r['kind'] for r in result['results']],['error','error'])

    def test_microtask_and_sync_loops_bounded_and_case_state_fresh(self):
        bundle=compiled(); base=B._cases(bundle)[-1]
        calls=['(()=>{while(true){}})()', '(()=>{Promise.resolve().then(()=>{while(true){}});return 1})()',
               '(()=>{globalThis.secret=1;return 1})()', 'typeof secret']
        started=time.monotonic()
        result=B._evaluate(bundle,[{**base,'call':call} for call in calls],case_ms=50)
        self.assertLess(time.monotonic()-started,3)
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual([r.get('kind') for r in result['results'][:2]],['timeout','timeout'])
        self.assertEqual(result['results'][-1]['value'],'"undefined"')

    def test_candidate_promise_then_mutation_gets_no_host_callable(self):
        bundle=compiled(); base=B._cases(bundle)[-1]
        call='(()=>{Promise.prototype.then=function(a){return a.constructor("return process")()};return 7})()'
        result=B._evaluate(bundle,[{**base,'call':call}],case_ms=100)
        self.assertEqual(result['results'],[{'ok':True,'value':'7'}],result)

    def test_inherited_and_explicit_stricter_deadlines_are_final(self):
        bundle=compiled(); cases=B._cases(bundle)
        with JS.verification_deadline_scope(time.monotonic()-1),self.assertRaisesRegex(B.BundleError,'deadline'):
            B._evaluate(bundle,cases,deadline=time.monotonic()+10)
        with self.assertRaisesRegex(B.BundleError,'deadline'):
            B._evaluate(bundle,cases,deadline=time.monotonic()-1)
        with JS.verification_deadline_scope(time.monotonic()+20):
            with self.assertRaisesRegex(B.BundleError,'deadline'):
                B._evaluate(bundle,cases,deadline=time.monotonic()-1)
        self.assertIsNone(JS._effective_deadline())

    def test_missing_required_runtime_never_falls_back_to_flattened_scripts(self):
        bundle=compiled()
        with mock.patch.object(JS,'available',return_value=False), mock.patch.object(JS,'evaluate') as classic:
            result=B._evaluate(bundle,B._cases(bundle))
            self.assertEqual(B.check_bundle(bundle)['status'],'unsupported')
            request,plan,artifacts=fixture()
            with self.assertRaises(B.BundleError) as caught:
                B.compile_bundle(request,plan,artifacts,runtime_identity=RUNTIME)
            self.assertEqual(caught.exception.code,'unsupported')
        self.assertEqual(result['status'],'unsupported'); classic.assert_not_called()

    def test_process_uses_existing_sandbox_limits_flags_and_finite_pipe(self):
        bundle=compiled(); original=subprocess.Popen; seen=[]
        def observe(argv,**kwargs):
            seen.append((argv,kwargs)); return original(argv,**kwargs)
        with mock.patch.object(B.subprocess,'Popen',side_effect=observe):
            B._evaluate(bundle,B._cases(bundle))
        argv,options=seen[0]
        for arg in ('--require','--no-unix','--net-connect','--experimental-vm-modules','--disallow-code-generation-from-strings'):
            self.assertIn(arg,argv)
        self.assertEqual(argv[argv.index('--net-connect')+1],'1')
        self.assertTrue(options['start_new_session']); self.assertEqual(set(options['env']),{'PATH','HOME','LANG','TMPDIR'})
        self.assertTrue(any(p.endswith('limits.py') for p in argv))


    def test_real_absent_source_text_module_capability_returns_unsupported(self):
        bundle=compiled(); original=subprocess.Popen
        def remove_capability_flag(argv,**kwargs):
            return original([a for a in argv if a != '--experimental-vm-modules'],**kwargs)
        with mock.patch.object(B.subprocess,'Popen',side_effect=remove_capability_flag):
            report=B._evaluate(bundle,B._cases(bundle))
        self.assertEqual(report['status'],'unsupported',report)
        self.assertEqual(report['results'],[])

    def test_static_builtins_unknown_modules_and_empty_declarations_refused(self):
        bundle=compiled(); cases=B._cases(bundle)
        for specifier in ('node:fs','node:net','../../../../etc/passwd','./absent.mjs'):
            changed=copy.deepcopy(bundle); file=changed['files'][0]
            file['text']='import {readFile} from '+json.dumps(specifier)+';\n'+file['text']
            file['imports'].insert(0,{'specifier':specifier,'path':specifier,'names':['readFile']})
            result=B._evaluate(changed,cases)
            self.assertTrue(result['status']=='invalid' or all(not r['ok'] for r in result['results']),result)
        changed=copy.deepcopy(bundle); changed['files'][0]['text']='export {addOne};'
        self.assertEqual(B._evaluate(changed,cases)['status'],'invalid')

    def test_transitive_closure_multi_export_and_declaration_order(self):
        request,old,artifacts=fixture()
        request['allowed_outputs'].append('package/middle.mjs')
        request['exports'] += [{'name':'addOne','signature':'addOne(x)'},{'name':'twice','signature':'twice(x)'}]
        rows=[{k:v for k,v in copy.deepcopy(r).items() if k != 'content_hash'} for r in old['contracts']]
        rows[1]['unit']['names'].append('twice')
        rows[1]['unit']['uses']=['middle(x)']; rows[1]['dependency_contract_ids']=['middle']
        rows[1]['unit']['examples'].extend([['addOne(8)','9'],['middle(4)','5'],['twice(2)','6']])
        middle=copy.deepcopy(rows[0]); middle.update(contract_id='middle',dependency_contract_ids=['helper'],output_artifacts=['package/middle.mjs'])
        middle['unit'].update(names=['middle'],heading='middle(x)',uses=['addOne(x)'],examples=[['middle(2)','3']])
        rows.append(middle)
        plan=C.validate_plan(request,{'id':'transitive','contracts':rows})
        native=plan['spec_plan']; tokens={}
        source={'addOne':'function addOne(x){return x+1;}', 'middle':'function middle(x){return addOne(x);}',
                'inc':'function twice(x){return middle(x)*2;} function inc(x){return middle(x);}'}
        units={u['id']:u for u in native['units']}
        for ident in native['order']:
            unit=units[ident]; code=source[unit['exports'][0]]
            tokens[ident]=SC.record_artifact(native,ident,code,tokens,runtime_identity=RUNTIME,
                checks=[{'passed':True,'scope':'fixture','subject_sha256':SC.code_hash(code)}])
        bundle=B.compile_bundle(request,plan,tokens,runtime_identity=RUNTIME)
        self.assertEqual(bundle['exports'],['inc','addOne','twice'])
        self.assertEqual(len(bundle['files']),4)
        result=B.check_bundle(bundle)
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['total'],7)

    def test_actual_runtime_spec_plan_seam_and_contract_mismatch(self):
        request,plan,artifacts=fixture(); sheet=copy.deepcopy(plan['spec_plan']['sheet'])
        sheet.update(title='MICA checked construction',intro='')
        native=SC.plan(sheet); tokens={}
        for unit in native['units']:
            code=artifacts[unit['id']]['code']
            tokens[unit['id']]=SC.record_artifact(native,unit['id'],code,tokens,runtime_identity=RUNTIME,
                checks=[{'passed':True,'scope':'fixture','subject_sha256':SC.code_hash(code)}])
        with self.assertRaises(SC.ContractError):
            B.compile_bundle(request,plan,tokens,runtime_identity=RUNTIME)
        bundle=B.compile_bundle(request,plan,tokens,runtime_identity=RUNTIME,spec_plan=native)
        self.assertTrue(B.check_bundle(bundle)['passed'])
        sheet['units'][0]['body']='Different contract'
        changed=SC.plan(sheet); tokens={}
        for unit in changed['units']:
            code=artifacts[unit['id']]['code']
            tokens[unit['id']]=SC.record_artifact(changed,unit['id'],code,tokens,runtime_identity=RUNTIME,
                checks=[{'passed':True,'scope':'fixture','subject_sha256':SC.code_hash(code)}])
        with self.assertRaisesRegex(B.BundleError,'contracts differ'):
            B.compile_bundle(request,plan,tokens,runtime_identity=RUNTIME,spec_plan=changed)

    def test_undeclared_helper_not_available_to_unrelated_unit_test(self):
        request,plan,artifacts=fixture(); rows=[{k:v for k,v in copy.deepcopy(r).items() if k!='content_hash'} for r in plan['contracts']]
        rows[1]['unit']['uses']=[]; rows[1]['dependency_contract_ids']=[]
        rows[1]['unit']['examples']=[['addOne(2)','3']]
        plan=C.validate_plan(request,{'id':'missing-use','contracts':rows}); tokens={}
        for unit in plan['spec_plan']['units']:
            code='function '+unit['exports'][0]+'(x){return x+1;}'
            tokens[unit['id']]=SC.record_artifact(plan['spec_plan'],unit['id'],code,tokens,runtime_identity=RUNTIME,
                checks=[{'passed':True,'scope':'fixture','subject_sha256':SC.code_hash(code)}])
        bundle=B.compile_bundle(request,plan,tokens,runtime_identity=RUNTIME)
        report=B._evaluate(bundle,B._cases(bundle))
        self.assertFalse(report['results'][1]['ok'],report)

    def test_realm_throw_proxy_constructor_traps_are_never_called(self):
        bundle=compiled(); base=B._cases(bundle)[-1]
        call='(()=>{throw new Proxy({}, {get(){return ({}).constructor.constructor("return process")()},getPrototypeOf(){return ({}).constructor.constructor("return process")()}})})()'
        result=B._evaluate(bundle,[{**base,'call':call}],case_ms=100)
        self.assertEqual(result['results'],[{'ok':False,'kind':'error','error':'module case threw inside its realm'}])


    def test_pure_read_and_deterministic_archive_never_start_any_runtime(self):
        bundle=compiled()
        with mock.patch.object(JS,'node_version',side_effect=AssertionError('runtime discovery forbidden')), \
                mock.patch.object(B.subprocess,'Popen',side_effect=AssertionError('execution forbidden')):
            self.assertTrue(B.verify_bundle(bundle,runtime_identity=RUNTIME)['ok'])
            first=B.archive(bundle); second=B.archive(bundle)
        self.assertEqual(first,second); self.assertLessEqual(len(first),B.MAX_ARCHIVE_BYTES)
        with zipfile.ZipFile(io.BytesIO(first)) as zipped:
            self.assertEqual(zipped.namelist(),[f['path'] for f in bundle['files']])
            for file,info in zip(bundle['files'],zipped.infolist()):
                self.assertEqual(zipped.read(info.filename).decode(),file['text'])
                self.assertEqual(info.date_time,(1980,1,1,0,0,0)); self.assertEqual(info.compress_type,zipfile.ZIP_STORED)
                self.assertEqual(stat.S_IMODE(info.external_attr>>16),0o644)
                self.assertTrue(stat.S_ISREG(info.external_attr>>16)); self.assertEqual(info.extra,b'')
        changed=copy.deepcopy(bundle); changed['files'][0]['path']='../outside.js'
        changed=B._seal({k:v for k,v in changed.items() if k!='sha256'})
        with self.assertRaises(B.BundleError): B.archive(changed)
        with mock.patch.object(B,'MAX_ARCHIVE_BYTES',1),self.assertRaisesRegex(B.BundleError,'archive'):
            B.archive(bundle)


    def test_parser_depth_resource_limit_is_inconclusive_not_a_candidate_verdict(self):
        bundle=compiled(); base=B._cases(bundle)[-1]
        result=B._evaluate(bundle,[{**base,'call':'(' * 300 + '1' + ')' * 300}])
        # Redundant parentheses do not survive as AST nodes; use nested array nodes.
        self.assertEqual(result['status'],'completed',result)
        result=B._evaluate(bundle,[{**base,'call':'[' * 300 + '1' + ']' * 300}])
        self.assertEqual(result['status'],'inconclusive',result)


    def test_external_held_out_cases_use_actual_entry_only_no_classic_or_mutation(self):
        bundle=compiled(); original=copy.deepcopy(bundle)
        with mock.patch.object(JS,'test',side_effect=AssertionError('no classic scoring')):
            result=B.check_cases(bundle,[['inc(9)','10'],['inc(-2)','-1']])
            hidden_helper=B.check_cases(bundle,[['addOne(2)','3']])
            failed=B.check_cases(bundle,[['inc(2)','999']])
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['scope'],'finite_external_strict_module_examples')
        self.assertFalse(hidden_helper['passed']); self.assertFalse(failed['passed'])
        self.assertEqual(bundle,original)
        strict=compiled(sources={'addOne':'function addOne(x){return this === undefined ? 99 : x+1;}',
                                 'inc':'function inc(x){return addOne(x);}'})
        self.assertTrue(B.check_cases(strict,[['inc(2)','99']])['passed'])
        with JS.verification_deadline_scope(time.monotonic()-1),self.assertRaisesRegex(B.BundleError,'deadline'):
            B.check_cases(bundle,[['inc(1)','2']])
        for cases in ([],[['inc(1)','NaN']], [['inc(1)','{\"a\":1,\"a\":2}']]):
            with self.assertRaises((JS.JsError,C.ContractError)):
                B.check_cases(bundle,cases)

    def test_module_lane_requires_explicit_format_and_reserved_bindings_fail(self):
        request,plan,artifacts=fixture()
        script={**request,'artifact_format':'javascript_script','allowed_outputs':[request['allowed_outputs'][0]]}
        rows=[{k:v for k,v in copy.deepcopy(r).items() if k!='content_hash'} for r in plan['contracts']]
        for row in rows: row['output_artifacts']=['units/'+row['contract_id']+'.js']
        script_plan=C.validate_plan(script,{'id':'script','contracts':rows})
        manifest=SC.artifact_manifest(plan['spec_plan'],artifacts,runtime_identity=RUNTIME)
        with self.assertRaisesRegex(B.BundleError,'explicit javascript_modules'):
            B._build(script,script_plan,manifest)
        rows[0]['unit']['names']=['__symblicInstallModuleCheck']
        rows[0]['unit']['heading']='__symblicInstallModuleCheck(x)'
        rows[0]['unit']['examples']=[['__symblicInstallModuleCheck(2)','3']]
        rows[1]['unit']['uses']=['__symblicInstallModuleCheck(x)']
        restricted={**request,'allowed_outputs':[request['allowed_outputs'][0]]}
        restricted_plan=C.validate_plan(restricted,{'id':'reserved','contracts':rows})
        native=restricted_plan['spec_plan']; tokens={}
        for unit in native['units']:
            code='function '+unit['exports'][0]+'(x){return x+1;}'
            tokens[unit['id']]=SC.record_artifact(native,unit['id'],code,tokens,runtime_identity=RUNTIME,
                checks=[{'passed':True,'scope':'fixture','subject_sha256':SC.code_hash(code)}])
        with self.assertRaisesRegex(B.BundleError,'prefix'):
            B.compile_bundle(restricted,restricted_plan,tokens,runtime_identity=RUNTIME)


    def test_original_declaration_parser_error_stays_inconclusive(self):
        request,plan,artifacts=fixture(); bundle=compiled()
        with mock.patch.object(B.JSC,'check',return_value={'passed':False,'status':'error','report':'fixture parser did not complete'}):
            with self.assertRaises(B.BundleError) as caught:
                B.compile_bundle(request,plan,artifacts,runtime_identity=RUNTIME)
            self.assertEqual(caught.exception.code,'unsupported')
            result=B.check_bundle(bundle)
            self.assertFalse(result['passed']); self.assertEqual(result['status'],'inconclusive')

    def test_request_and_module_bounds_refuse_before_execution(self):
        bundle=compiled(); cases=B._cases(bundle)
        for timeout in (False,0,3001):
            with self.assertRaises(B.BundleError): B._evaluate(bundle,cases,case_ms=timeout)
        with mock.patch.object(B,'MAX_BYTES',1),self.assertRaisesRegex(B.BundleError,'aggregate'):
            B.verify_bundle(bundle)
        with mock.patch.object(B,'MAX_CASES',2),self.assertRaisesRegex(B.BundleError,'total'):
            B._cases(bundle)


if __name__ == '__main__': unittest.main()
