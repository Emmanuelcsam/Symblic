"""Independent manufactured solutions, KKT checks and invalid transport witnesses."""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from symblic.experiments import numerics as N


def example(key):
    return next(x['example'] for x in N.catalog() if x['id']==key)


class NumericsTests(unittest.TestCase):
    def test_manufactured_error_matches_closed_form_for_even_and_odd_meshes(self):
        data=example('field-refinement');data['intervals']=[3,4,8,16]
        result=N.field_refinement(data)
        for row in result['results']['meshes']:
            count=row['intervals'];a=F(data['amplitude_K'])
            for i,(actual,exact) in enumerate(zip(row['computed_temperature_K'],row['manufactured_temperature_K'])):
                z=F(i,count)
                self.assertEqual(actual-exact,a*z*(1-z)/count**2)
            self.assertTrue(all(x==0 for x in row['discrete_residual_W_per_m3']))
            self.assertTrue(any(x!=0 for x in row['truncation_residual_W_per_m3']))
        self.assertEqual(result['results']['meshes'][-1]['previous_to_current_error_ratio'],4)

    def test_units_scaling_and_negative_amplitude(self):
        data=example('field-refinement');before=N.field_refinement(data)['results']['meshes']
        data.update(length_m=6,conductivity_W_per_m_K=27,amplitude_K=-16)
        after=N.field_refinement(data)['results']['meshes']
        for a,b in zip(before,after):
            self.assertEqual(b['computed_temperature_K'],[-x for x in a['computed_temperature_K']])
            self.assertEqual(b['forcing_W_per_m3'],[-x for x in a['forcing_W_per_m3']])
            self.assertEqual(b['spacing_m'],3*a['spacing_m'])

    def test_bad_native_witness_refuses(self):
        with patch.object(N.V,'verify_quadratic',return_value=False):
            with self.assertRaisesRegex(ValueError,'field_witness_failure'):
                N.run('field-refinement',example('field-refinement'))

    def test_field_bounds_before_solve(self):
        for key,value in [('intervals',[4,33]),('intervals',[4,4]),('intervals',[4,2]),('length_m',0),('conductivity_W_per_m_K',True),('amplitude_K',0)]:
            data=example('field-refinement');data[key]=value
            with patch.object(N.V,'minimize_quadratic',side_effect=AssertionError('must refuse before solver')):
                with self.assertRaises(ValueError):N.run('field-refinement',data)

    def test_full_metric_known_projection(self):
        result=N.spd_reconciliation(example('spd-reconciliation'))
        r=result['results']
        self.assertEqual(r['reconciled'],[F(2,3),F(1,3)])
        self.assertEqual(r['objective_half_squared_metric_distance'],F(5,6))
        self.assertEqual(r['diagonal_metric_baseline'],[F(3,5),F(2,5)])
        self.assertEqual(r['baseline_objective_under_full_metric'],F(21,25))
        for t in [F(-3),F(-1,7),F(1,100),F(2)]:
            y=[r['reconciled'][0]+t,r['reconciled'][1]-t]
            objective=(2*y[0]**2+2*y[0]*y[1]+3*y[1]**2)/2
            self.assertGreater(objective,r['objective_half_squared_metric_distance'])

    def test_reconciliation_keeps_original_and_checks_all_residuals(self):
        data=example('spd-reconciliation');data['original']=[3,-2];old=deepcopy(data)
        r=N.spd_reconciliation(data)['results']
        self.assertEqual(data,old)
        self.assertEqual(r['original'],[3,-2])
        self.assertEqual(r['reconciled'],[3,-2])
        self.assertEqual(r['objective_half_squared_metric_distance'],0)
        self.assertTrue(all(x==0 for x in r['primal_residual']+r['stationarity_residual']))

    def test_invalid_metric_or_constraints_refuse(self):
        for change in [{'metric':[[1,2],[2,1]]},{'metric':[[2,1],[0,3]]},
                       {'constraints':[[1,1],[2,2]],'targets':[1,2]},
                       {'constraints':[[1,1],[2,2]],'targets':[1,3]},
                       {'original':[0]*9}]:
            data=example('spd-reconciliation');data.update(change)
            with self.assertRaises(ValueError):N.run('spd-reconciliation',data)

    def test_diagonal_special_case_matches_existing_projection(self):
        data={'original':[5,0,0],'metric':[[2,0,0],[0,3,0],[0,0,4]],'constraints':[[1,1,1],[1,-1,0]],'targets':[2,0]}
        result=N.spd_reconciliation(data)['results']
        self.assertEqual(result['reconciled'],result['diagonal_metric_baseline'])
        self.assertEqual(result['objective_half_squared_metric_distance'],result['baseline_objective_under_full_metric'])

    def test_transport_positive_certificate_and_nonoptimal_feasible_plan(self):
        data=example('transport-certificate')
        self.assertTrue(N.transport_certificate(data)['results']['optimality_certified'])
        data['plan']=[[0,'1/2'],['1/2',0]]
        r=N.transport_certificate(data)
        self.assertTrue(r['checks']['primal_feasible'])
        self.assertTrue(r['checks']['dual_feasible'])
        self.assertEqual(r['results']['duality_gap'],1)
        self.assertFalse(r['results']['optimality_certified'])

    def test_transport_zero_gap_alone_is_insufficient(self):
        data=example('transport-certificate');data['plan']=[[0,0],[0,0]]
        r=N.transport_certificate(data)
        self.assertTrue(r['checks']['gap_zero'])
        self.assertFalse(r['checks']['primal_feasible'])
        self.assertFalse(r['results']['optimality_certified'])
        data=example('transport-certificate');data['left_dual']=[1,1]
        invalid=N.transport_certificate(data)
        self.assertFalse(invalid['checks']['dual_feasible'])
        self.assertIsNone(invalid['results']['certified_lower_bound'])

    def test_transport_fractional_nonzero_optimum(self):
        data={'left_mass':['1/3','2/3'],'right_mass':[1],'costs':[[2],[3]],'plan':[['1/3'],['2/3']],'left_dual':[2,3],'right_dual':[0],'cost_unit':'USD'}
        r=N.transport_certificate(data)['results']
        self.assertEqual(r['primal_cost'],F(8,3))
        self.assertEqual(r['dual_objective'],F(8,3))
        self.assertTrue(r['optimality_certified'])

    def test_bad_masses_and_unknown_fields_refuse(self):
        for change in [{'left_mass':[1,1]},{'left_mass':[True,0]}, {'costs':[[-1,0],[0,0]]},{'cost_unit':'x\n'}, {'extra':1}]:
            data=example('transport-certificate');data.update(change)
            with self.assertRaises(ValueError):N.run('transport-certificate',data)


if __name__=='__main__':
    unittest.main()
