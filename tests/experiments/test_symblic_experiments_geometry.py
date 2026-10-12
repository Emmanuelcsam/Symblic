"""Independent finite references and refusal boundaries; no models/stores."""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import json
import unittest
from unittest.mock import patch

from symblic.experiments import geometry as G


def example(name):
    return next(row['example'] for row in G.catalog() if row['id'] == name)


class GeometryExperiments(unittest.TestCase):
    def test_harmonic_one_step_independent_reference(self):
        data = example('hamiltonian_integrators')
        data.update(step='1/2', steps=1)
        out = G.run('hamiltonian_integrators', data)
        sym = out['results']['symplectic_euler']
        exp = out['results']['explicit_euler']
        self.assertEqual(sym['trajectory'][1]['q'], ['3/4'])
        self.assertEqual(sym['trajectory'][1]['p'], ['-1/2'])
        self.assertEqual(sym['trajectory'][1]['energy'], '13/32')
        self.assertEqual(exp['trajectory'][1]['energy'], '5/8')
        self.assertEqual(sym['trajectory'][1]['modified_energy'], '1/2')
        self.assertTrue(sym['preserves_symplectic_form'])
        self.assertFalse(exp['preserves_symplectic_form'])
        self.assertFalse(sym['preserves_original_energy_for_all_states'])
        self.assertTrue(all(out['checks'].values()))

    def test_energy_growth_reference_and_finite_drift(self):
        data = example('hamiltonian_integrators')
        out = G.run('hamiltonian_integrators', data)['results']
        h, steps = F(data['step']), data['steps']
        self.assertEqual(F(out['explicit_euler']['trajectory'][-1]['energy']), F(1,2)*(1+h*h)**steps)
        self.assertLess(F(out['symplectic_euler']['max_absolute_energy_error']), F(out['explicit_euler']['max_absolute_energy_error']))

    def test_coupled_unequal_mass_reference(self):
        data = {'K': [[2,-1],[-1,2]], 'inverse_mass': [2,'1/2'], 'q0': [1,2], 'p0': [-1,1], 'step':'1/4','steps':3,'units':'dimensionless'}
        out = G.run('hamiltonian_integrators', data)
        q, p = [F(1),F(2)], [F(-1),F(1)]
        for row in out['results']['symplectic_euler']['trajectory'][1:]:
            # Independent expanded equations, not production matrix helpers.
            p = [p[0]-F(1,4)*(2*q[0]-q[1]), p[1]-F(1,4)*(-q[0]+2*q[1])]
            q = [q[0]+F(1,2)*p[0], q[1]+F(1,8)*p[1]]
            self.assertEqual([F(x) for x in row['q']], q)
            self.assertEqual([F(x) for x in row['p']], p)
            self.assertEqual(F(row['energy']), q[0]**2-q[0]*q[1]+q[1]**2+p[0]**2+F(1,4)*p[1]**2)
        self.assertTrue(all(out['checks'].values()))

    def test_unstable_large_step_retains_honest_invariant(self):
        data = example('hamiltonian_integrators')
        data.update(step=3, steps=4)
        out = G.run('hamiltonian_integrators', data)
        self.assertFalse(out['results']['modified_quadratic_positive_definite'])
        self.assertTrue(out['checks']['modified_quadratic_identity'])
        self.assertGreater(F(out['results']['symplectic_euler']['max_absolute_energy_error']), 100)

    def test_bernoulli_fisher_reference_and_log_score(self):
        data = example('fisher_gradient'); data['steps'] = 1
        out = G.run('fisher_gradient', data)['results']
        ordinary, natural = out['ordinary_gradient'], out['natural_gradient']
        self.assertEqual(natural['trajectory'][0]['fisher'], [['4']])
        self.assertEqual(natural['trajectory'][0]['gradient'], ['-1'])
        self.assertEqual(natural['trajectory'][0]['direction'], ['-1/4'])
        self.assertEqual(ordinary['final_probabilities'], ['5/8','3/8'])
        self.assertEqual(natural['final_probabilities'], ['17/32','15/32'])
        self.assertEqual(natural['heldout']['brier'], '257/512')
        with localcontext() as ctx:
            ctx.prec = 50
            expected = -((Decimal(17)/32).ln()+(Decimal(15)/32).ln())/2
        self.assertLess(abs(Decimal(natural['heldout']['mean_negative_log_likelihood_nats_approx'])-expected), Decimal('1e-48'))

    def test_categorical_natural_direction_equals_probability_minus_frequency(self):
        data = {'probabilities':['1/2','1/3','1/6'], 'train':[1,1,1], 'heldout':[2,1,1], 'step':'1/2','steps':1,'regularization':0}
        out = G.run('fisher_gradient', data)['results']['natural_gradient']
        self.assertEqual(out['trajectory'][0]['fisher'], [['8','6'],['6','9']])
        self.assertEqual(out['trajectory'][0]['direction'], ['1/6','0'])
        self.assertEqual(out['final_probabilities'], ['5/12','1/3','1/4'])
        self.assertEqual(out['trajectory'][0]['linear_solve_residual'], ['0','0'])
        self.assertEqual(out['trajectory'][0]['fisher_rank'], 2)

    def test_regularization_changes_direction_not_claimed_fisher(self):
        data = example('fisher_gradient'); data.update(steps=1, regularization=4)
        row = G.run('fisher_gradient', data)['results']['natural_gradient']['trajectory'][0]
        self.assertEqual(row['fisher'], [['4']])
        self.assertEqual(row['regularization'], '4')
        self.assertEqual(row['direction'], ['-1/8'])
        self.assertEqual(row['linear_solve_residual'], ['0'])

    def test_heldout_is_not_used_for_updates_or_stopping(self):
        data = example('fisher_gradient')
        before = G.run('fisher_gradient', data)['results']
        data['heldout'] = [0,10]
        after = G.run('fisher_gradient', data)['results']
        for method in ('ordinary_gradient','natural_gradient'):
            self.assertEqual(before[method]['trajectory'], after[method]['trajectory'])
            self.assertEqual(before[method]['training'], after[method]['training'])
            self.assertNotEqual(before[method]['heldout'], after[method]['heldout'])

    def test_rejected_boundary_steps_are_visible_and_counted(self):
        data = example('fisher_gradient'); data.update(train=[1,0], step=1, steps=2)
        out = G.run('fisher_gradient', data)['results']
        for method in ('ordinary_gradient','natural_gradient'):
            self.assertEqual(out[method]['accepted_steps'], 0)
            self.assertEqual(out[method]['rejected_steps'], 2)
            self.assertEqual(out[method]['final_probabilities'], ['1/2','1/2'])
            self.assertEqual([r['status'] for r in out[method]['trajectory']], ['boundary_rejected']*2)

    def test_scalar_shape_domain_and_schema_refusals(self):
        for field, value in [('K',[[0]]), ('K',[[1,0]]), ('inverse_mass',[0]), ('q0',[True]), ('p0',[0.0]), ('step','²'), ('step','1/0'), ('step','1e-3'), ('steps',33), ('units','meters')]:
            data=example('hamiltonian_integrators'); data[field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError): G.run('hamiltonian_integrators', data)
        for field,value in [('probabilities',[0,1]),('probabilities',['1/3','1/3']),('train',[0,0]),('train',[True,1]),('heldout',[1]),('steps',17),('regularization',-1)]:
            data=example('fisher_gradient');data[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): G.run('fisher_gradient',data)
        for invalid in [[], None, {'private':'secret'}]:
            with self.assertRaisesRegex(ValueError,'^schema$'): G.run('fisher_gradient',invalid)
        for invalid in [[],None,'unknown']:
            with self.assertRaisesRegex(ValueError,'^unknown_experiment$'): G.run(invalid,{})

    def test_bit_work_limits_and_no_echo(self):
        data=example('hamiltonian_integrators');data.update(K=[[2**53-1]],step=4,steps=32)
        with self.assertRaisesRegex(ValueError,'^arithmetic_bound$'):G.run('hamiltonian_integrators',data)
        with patch.object(G,'MAX_WORK',10), self.assertRaisesRegex(ValueError,'^work_bound$'):
            G.run('hamiltonian_integrators',example('hamiltonian_integrators'))
        data=example('fisher_gradient'); data['step']='private secret'
        with self.assertRaisesRegex(ValueError,'^rational$'):G.run('fisher_gradient',data)

    def test_catalog_isolated_json_and_identity(self):
        self.assertTrue(G._symblic_import_identity['matched'])
        initial=G.catalog(); changed=G.catalog();changed[0]['example']['K'][0][0]=0
        self.assertEqual(G.catalog(),initial)
        for item in initial:
            data=deepcopy(item['example']);out=G.run(item['id'],data)
            self.assertEqual(data,item['example'])
            self.assertEqual(out,G.run(item['id'],data))
            json.dumps(out,allow_nan=False)
            self.assertLess(out['work']['rational_operations'],G.MAX_WORK)


if __name__=='__main__':
    unittest.main()
