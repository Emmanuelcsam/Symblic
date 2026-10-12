"""Independent finite references, degenerate outcomes and bounded refusal."""
from fractions import Fraction as F
import unittest

from symblic.experiments import sampling as S


def example(name):return next(r['example'] for r in S.catalog() if r['id']==name)


class Sampling(unittest.TestCase):
    def test_exact_oracle_and_seeded_repetition(self):
        data=example('particle_filter')
        result=S.run('particle_filter',data)
        self.assertEqual(result,S.run('particle_filter',data))
        rows=result['results']['steps']
        self.assertEqual(rows[0]['oracle'],['4/5','1/5'])
        self.assertEqual(rows[1]['oracle'],['13/41','28/41'])
        for row in rows:
            self.assertEqual(sum(map(F,row['posterior'])),1)
            self.assertTrue(1<=F(row['effective_sample_size'])<=64)
            self.assertTrue(0<=F(row['total_variation_error'])<=1)
        self.assertEqual(result['results']['categorical_draws'],64*5)

    def test_collapse_and_impossible_observation_are_distinct(self):
        data={'prior':['1/2','1/2'],'transition':[[1,0],[0,1]],'likelihoods':[[1,0]],'particles':1,'seed':0}
        result=S.run('particle_filter',data)['results']
        self.assertEqual(result['status'],'particle_collapse')
        self.assertEqual(result['steps'][0]['oracle'],['1','0'])
        data['likelihoods']=[[0,0]]
        self.assertEqual(S.run('particle_filter',data)['results']['status'],'impossible_observation')

    def test_normalization_and_work_bounds(self):
        for change in ['normalization','particles','steps','likelihood','float']:
            data=example('particle_filter')
            if change=='normalization':data['transition'][0]=[1,1]
            if change=='particles':data['particles']=129
            if change=='steps':data['likelihoods']*=9
            if change=='likelihood':data['likelihoods'][0]=[2,0]
            if change=='float':data['prior']=[0.5,0.5]
            with self.subTest(change=change),self.assertRaises(ValueError):S.run('particle_filter',data)

    def test_ising_degeneracy_and_direct_energy(self):
        result=S.run('ising_search',example('ising_search'))
        self.assertEqual(result['results']['exact_minimum'],'-1')
        self.assertEqual(result['results']['degeneracy'],2)
        self.assertEqual(result['results']['ground_states'],[[-1,-1],[1,1]])
        for row in result['results']['heuristic']:
            self.assertEqual(F(row['energy']),-row['state'][0]*row['state'][1])
            self.assertEqual(F(row['gap_to_exhaustive_minimum']),F(row['energy'])+1)

    def test_nonzero_fields_and_disallowed_couplings(self):
        data={'fields':[2,-3],'couplings':[[0,0],[0,0]],'steps':8,'restarts':2,'seed':1}
        result=S.run('ising_search',data)['results']
        self.assertEqual(result['exact_minimum'],'-5')
        self.assertEqual(result['ground_states'],[[-1,1]])
        data['couplings'][0][1]=1
        with self.assertRaises(ValueError):S.run('ising_search',data)
        data['couplings']=[[1,0],[0,0]]
        with self.assertRaises(ValueError):S.run('ising_search',data)

    def test_codebook_errors_and_energy_difference_reported(self):
        result=S.run('noisy_codebook',example('noisy_codebook'))['results']
        self.assertEqual(result['metrics']['codebook']['symbol_errors'],0)
        self.assertEqual(result['metrics']['baseline']['symbol_errors'],2)
        self.assertEqual(result['metrics']['codebook']['mean_codeword_squared_norm'],'2')
        self.assertEqual(result['metrics']['baseline']['mean_codeword_squared_norm'],'1')

    def test_ties_are_visible_and_rate_mismatch_refuses(self):
        data=example('noisy_codebook')
        data['samples']=[{'symbol':1,'noise':[-1,-1]}]
        result=S.run('noisy_codebook',data)['results']
        self.assertEqual(result['samples']['codebook'][0]['ties'],[0,1])
        self.assertEqual(result['samples']['codebook'][0]['decoded'],0)
        data['baseline'].append([0,0])
        with self.assertRaises(ValueError):S.run('noisy_codebook',data)


if __name__=='__main__':unittest.main()
