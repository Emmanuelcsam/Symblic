"""Pure task-card contracts and portable outputs; no provider, process or store."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from symblic.spec import sheets as SP
from symblic.spec import contracts as C

SHEET = '''# demo.js
Build exact tiny units.
## Shared
Values are integers; quoted Unicode: café ⚙.
## Unit `alpha(x)`
Return x+1.
Examples:
    alpha(2) ==> 3
## Unit `independent()`
Return 9.
Examples:
    independent() ==> 9
## Unit `beta(x)`
Uses: `alpha`
Return alpha(x)+1.
Examples:
    beta(2) ==> 4
## Unit `gamma(x)`
Uses: `beta`
Return beta(x)+1.
Examples:
    gamma(2) ==> 5
## Assemble `demo.js`
    // generated café
    /*UNITS*/
'''
RUNTIME = {'kernel': 'test-only', 'checker': 'a'*64}


def checks(code):
    return [{'scope': 'finite_examples', 'passed': True, 'subject_sha256': C.code_hash(code),
             'checker_sha256': 'a'*64, 'receipt_sha256': 'b'*64}]


def prepared(sheet=SHEET):
    plan = C.plan(SP.parse(sheet)); artifacts = {}
    for ident in plan['order']:
        unit = next(u for u in plan['units'] if u['id'] == ident)
        code = 'function ' + unit['exports'][0] + '() { return 1; }'
        # These are explicitly fake host receipts. The pure helper does not execute JavaScript.
        artifacts[ident] = C.record_artifact(plan, ident, code, artifacts,
                                            runtime_identity=RUNTIME, checks=checks(code))
    return plan, artifacts


class SpecContracts(unittest.TestCase):
    def error(self, code, function, *args, **kwargs):
        with self.assertRaises(C.ContractError) as got:
            function(*args, **kwargs)
        self.assertEqual(got.exception.code, code)
        return got.exception

    def test_plan_stable_ordered_exports_layers_and_complete_contract(self):
        p = C.plan(SP.parse(SHEET)); a, i, b, g = [u['id'] for u in p['units']]
        self.assertEqual(p['layers'], [[a,i],[b],[g]])
        self.assertEqual(p['units'][-1]['closure'], [a,b])
        changed = SP.parse(SHEET); changed['units'][0]['line'] += 100
        self.assertEqual(C.plan(changed), p)
        full = SHEET.replace('Return x+1.', 'Return x+1.\n\n' + 'A'*1000 + '\nException: preserve zero.')
        q = C.plan(SP.parse(full))
        self.assertEqual(q['units'][0]['id'], a)
        self.assertNotEqual(q['units'][0]['contract_sha256'],p['units'][0]['contract_sha256'])
        self.assertIn('Exception: preserve zero.', q['units'][0]['contract']['unit']['body'])

    def test_unknown_uses_requires_explicit_external_name(self):
        sheet = SP.parse(SHEET.replace('Uses: `alpha`', 'Uses: `helper`'))
        self.assertEqual(SP.problems(sheet), [])  # Legacy compiler behavior is unchanged.
        self.error('unknown_use', C.plan, sheet)
        p = C.plan(sheet, externals=['helper'])
        self.assertEqual(p['units'][2]['external_uses'], ['helper'])
        self.assertEqual(p['units'][2]['dependencies'], [])

    def test_cycles_duplicate_exports_and_binding_collisions(self):
        sheet = SP.parse(SHEET); sheet['units'][0]['uses']=['gamma']
        self.error('dependency_cycle', C.plan, sheet)
        sheet = SP.parse(SHEET); sheet['units'][1]['names']=['alpha']
        self.error('exports', C.plan, sheet)
        sheet = SP.parse(SHEET); sheet['units'][0]['names']=['$a']; sheet['units'][1]['names']=['_a']
        self.error('binding_collision', C.plan, sheet)
        sheet = SP.parse(SHEET); sheet['units'][0]['names']=['alpha','alpha']
        self.error('exports', C.plan, sheet)

    def test_unrelated_unit_remains_reusable_after_early_contract_change(self):
        p, artifacts = prepared()
        q = C.plan(SP.parse(SHEET.replace('Return x+1.', 'Return x+2.')))
        states = C.reuse_decisions(q, artifacts, runtime_identity=RUNTIME)
        a, i, b, g = [u['id'] for u in p['units']]
        self.assertEqual([states[x]['state'] for x in (a,i,b,g)], ['recheck','reusable','recheck','recheck'])
        self.assertIn('contract_changed', states[a]['reasons'])
        self.assertIn('dependency_not_reusable', states[g]['reasons'])
        self.assertEqual(artifacts[a]['code'], next(iter(artifacts.values()))['code'])

    def test_changed_dependency_artifact_invalidates_consumers(self):
        p, artifacts = prepared(); a, i, b, g = [u['id'] for u in p['units']]
        code='function alpha() { return 2; }'
        artifacts[a]=C.record_artifact(p,a,code,artifacts,runtime_identity=RUNTIME,checks=checks(code))
        states=C.reuse_decisions(p,artifacts,runtime_identity=RUNTIME)
        self.assertTrue(states[a]['reusable']); self.assertTrue(states[i]['reusable'])
        self.assertIn('dependency_artifact_changed',states[b]['reasons'])
        self.assertFalse(states[g]['reusable'])

    def test_runtime_drift_redo_and_missing_artifacts_are_explicit(self):
        p, artifacts=prepared(); a,i,b,g=[u['id'] for u in p['units']]
        changed=C.reuse_decisions(p,artifacts,runtime_identity={'kernel':'changed'})
        self.assertTrue(all('runtime_changed' in row['reasons'] for row in changed.values()))
        redo=C.reuse_decisions(p,artifacts,runtime_identity=RUNTIME,redo=['alpha'])
        self.assertEqual(redo[a]['state'],'rebuild'); self.assertTrue(redo[i]['reusable'])
        self.assertEqual(redo[b]['state'],'recheck')
        self.error('redo',C.reuse_decisions,p,artifacts,runtime_identity=RUNTIME,redo=['missing'])
        artifacts.pop(a)
        missing=C.reuse_decisions(p,artifacts,runtime_identity=RUNTIME)
        self.assertEqual(missing[a]['reasons'],['missing_artifact'])
        self.assertFalse(missing[g]['reusable'])

    def test_card_has_full_transitive_exact_code_without_unrelated_unit(self):
        p, artifacts=prepared(); a,i,b,g=[u['id'] for u in p['units']]
        card=C.context_card(p,g,artifacts,runtime_identity=RUNTIME,budget=100000)
        self.assertEqual([d['unit_id'] for d in card['payload']['dependencies']],[a,b])
        self.assertNotIn(i,[d['unit_id'] for d in card['payload']['dependencies']])
        self.assertEqual(card['unit_count'],3)
        self.assertEqual(card['utf8_bytes'],len(card['serialized'].encode()))
        self.assertGreater(card['utf8_bytes'],card['characters'])
        self.assertEqual(card['sha256'],hashlib.sha256(card['serialized'].encode()).hexdigest())
        self.assertEqual(json.loads(card['serialized']),card['payload'])
        self.assertTrue(all(d['required'] for d in card['manifest']['included']))
        self.assertEqual(card['manifest']['omitted'],[])

    def test_exact_card_boundary_counts_all_fixed_overhead(self):
        p, artifacts=prepared(); target=p['order'][-1]; fixed=['SYSTEM','schema:{}','wrapper café']
        card=C.context_card(p,target,artifacts,runtime_identity=RUNTIME,budget=100000,fixed_parts=fixed)
        size=card['manifest']['used']
        exact=C.context_card(p,target,artifacts,runtime_identity=RUNTIME,budget=size,fixed_parts=fixed)
        self.assertEqual(exact['manifest']['used'],size)
        failure=self.error('context_budget',C.context_card,p,target,artifacts,runtime_identity=RUNTIME,budget=size-1,fixed_parts=fixed)
        self.assertEqual(failure.details['required'],size)
        self.assertEqual(exact['manifest']['fixed_characters'],sum(map(len,fixed)))
        self.error('budget',C.context_card,p,target,artifacts,runtime_identity=RUNTIME,budget=True)

    def test_missing_or_corrupt_required_value_never_falls_back_to_partial_context(self):
        p, artifacts=prepared(); a=p['order'][0]; target=p['order'][-1]
        artifacts[a]['code']+=' altered'
        self.error('required_dependency',C.context_card,p,target,artifacts,runtime_identity=RUNTIME,budget=100000)
        self.error('assembly_dependencies',C.artifact_manifest,p,artifacts,runtime_identity=RUNTIME)
        decisions=C.reuse_decisions(p,artifacts,runtime_identity=RUNTIME)
        self.assertEqual(decisions[a]['state'],'rebuild')

    def test_host_checks_are_associated_with_exact_code_not_promoted_to_truth(self):
        p=C.plan(SP.parse(SHEET)); ident=p['order'][0]
        for rows in ([],[{'scope':'test','passed':False,'subject_sha256':C.code_hash('x')}],checks('other')):
            self.error('checks',C.record_artifact,p,ident,'x',{},runtime_identity=RUNTIME,checks=rows)
        token=C.record_artifact(p,ident,'x',{},runtime_identity=RUNTIME,checks=checks('x'))
        self.assertEqual(token['code'],'x')  # Pure helper does not pretend this is valid JS.
        self.assertNotIn('truth',token)

    def test_portable_manifest_exact_output_hash_and_recorded_runtime_inspection(self):
        p, artifacts=prepared()
        m=C.artifact_manifest(p,artifacts,runtime_identity=RUNTIME)
        result=C.verify_manifest(m,expected_output_sha256=m['output']['sha256'],expected_manifest_sha256=m['sha256'])
        self.assertTrue(result['ok']); self.assertEqual(result['runtime_current'],'not_checked')
        self.assertEqual(result['authenticity'],'not_established')
        self.assertEqual(C.verify_manifest(m,runtime_identity=RUNTIME)['runtime_current'],'matched')
        self.error('runtime_changed',C.verify_manifest,m,runtime_identity={'kernel':'other'})
        self.error('output_hash',C.verify_manifest,m,expected_output_sha256='0'*64)
        self.error('manifest_identity',C.verify_manifest,m,expected_manifest_sha256='0'*64)
        self.error('output_hash',C.artifact_manifest,p,artifacts,runtime_identity=RUNTIME,expected_output_sha256='0'*64)
        self.assertEqual(m,C.artifact_manifest(p,dict(reversed(list(artifacts.items()))),runtime_identity=RUNTIME))

    def test_manifest_reconstruction_refuses_tampered_plan_exports_and_output(self):
        p, artifacts=prepared(); original=C.artifact_manifest(p,artifacts,runtime_identity=RUNTIME)
        for field in ('output','ordered_exports','plan'):
            m=copy.deepcopy(original)
            if field=='output':m[field]['text']+='\n'
            elif field=='ordered_exports':m[field].reverse()
            else:m[field]['layers'].reverse();m[field]=C._seal({k:v for k,v in m[field].items() if k!='sha256'})
            m=C._seal({k:v for k,v in m.items() if k!='sha256'})
            self.assertRaises(C.ContractError,C.verify_manifest,m)
        m=copy.deepcopy(original);m['version']=True;m=C._seal({k:v for k,v in m.items() if k!='sha256'})
        self.error('schema',C.verify_manifest,m)

    def test_global_and_per_unit_text_are_pinned_but_template_only_changes_assembly(self):
        p, artifacts=prepared()
        for path in ('body','setup','examples','heading'):
            sheet=SP.parse(SHEET)
            if path=='examples':sheet['units'][0][path][0][1]='4'
            else:sheet['units'][0][path]+=' changed'
            q=C.plan(sheet)
            self.assertNotEqual(q['units'][0]['contract_sha256'],p['units'][0]['contract_sha256'])
        sheet=SP.parse(SHEET);sheet['template']['text']+='\n// footer'
        q=C.plan(sheet)
        self.assertTrue(all(r['reusable'] for r in C.reuse_decisions(q,artifacts,runtime_identity=RUNTIME).values()))
        self.assertNotEqual(C.artifact_manifest(p,artifacts,runtime_identity=RUNTIME)['output']['sha256'],
                            C.artifact_manifest(q,artifacts,runtime_identity=RUNTIME)['output']['sha256'])
        sheet=SP.parse(SHEET);sheet['shared']+=' changed'
        self.assertTrue(all(not r['reusable'] for r in C.reuse_decisions(C.plan(sheet),artifacts,runtime_identity=RUNTIME).values()))

    def test_required_hash_contract_does_not_claim_generation_can_find_it(self):
        p, artifacts=prepared(); actual=C.artifact_manifest(p,artifacts,runtime_identity=RUNTIME)['output']['sha256']
        exact=C.plan(SP.parse(SHEET),required_output_sha256=actual)
        self.assertTrue(C.verify_manifest(C.artifact_manifest(exact,artifacts,runtime_identity=RUNTIME))['ok'])
        impossible=C.plan(SP.parse(SHEET),required_output_sha256='0'*64)
        self.error('output_hash',C.artifact_manifest,impossible,artifacts,runtime_identity=RUNTIME)

    def test_bounds_cycles_nonfinite_examples_and_detached_records(self):
        sheet=SP.parse(SHEET); sheet['units'][0]['examples'][0][1]='NaN'
        self.error('examples',C.plan,sheet)
        sheet=SP.parse(SHEET);sheet['units'][0]['body']='\ud800'
        self.error('unicode',C.plan,sheet)
        value=[];value.append(value)
        self.error('cycle',C.plan,value)
        with patch.object(C,'MAX_UNITS',1):self.error('units',C.plan,SP.parse(SHEET))
        with patch.object(C,'MAX_BYTES',10):self.error('byte_limit',C.plan,SP.parse(SHEET))
        p, artifacts=prepared(); card=C.context_card(p,p['order'][-1],artifacts,runtime_identity=RUNTIME,budget=100000)
        card['payload']['dependencies'][0]['code']='changed'
        self.assertNotEqual(artifacts[p['order'][0]]['code'],'changed')
        self.error('template',C.plan,SP.parse(SHEET.replace('/*UNITS*/','/*UNITS*//*UNITS*/')))

    def test_external_scope_request_identity_and_resealed_claims_remain_explicit(self):
        sheet = SP.parse(SHEET.replace('Uses: `alpha`', 'Uses: `helper`'))
        p = C.plan(sheet, externals=['helper'])
        target = p['units'][2]['id']
        first = C.context_card(p, target, {}, runtime_identity=RUNTIME, budget=100000, fixed_parts=['system A'])
        second = C.context_card(p, target, {}, runtime_identity=RUNTIME, budget=100000, fixed_parts=['system B'])
        self.assertEqual(first['manifest']['external_requirements'], ['helper'])
        self.assertEqual(first['sha256'], second['sha256'])
        self.assertNotEqual(first['request_sha256'], second['request_sha256'])
        for value in ('1e999', '-1e999', '[1e999]', '{"x":1e999}'):
            changed = SP.parse(SHEET); changed['units'][0]['examples'][0][1] = value
            self.error('examples', C.plan, changed)
        p, artifacts = prepared(); manifest = C.artifact_manifest(p, artifacts, runtime_identity=RUNTIME)
        manifest['assurance'] = 'independently_verified_universal_truth'
        manifest = C._seal({k:v for k,v in manifest.items() if k != 'sha256'})
        self.error('assurance', C.verify_manifest, manifest)


if __name__=='__main__':unittest.main()
