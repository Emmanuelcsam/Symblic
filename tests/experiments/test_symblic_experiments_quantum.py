"""Finite independent results and negative boundaries; no providers or stores."""
from copy import deepcopy
from fractions import Fraction as F
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from symblic.experiments import registry as E
from symblic.experiments import quantum as Q


def example(name):
    return next(row['example'] for row in Q.catalog() if row['id']==name)


class QuantumExperiments(unittest.TestCase):
    def test_training_selection_and_independent_probabilities(self):
        result = Q.run('question_order_fit', example('question_order_fit'))
        self.assertEqual(result['results']['selected_candidate'], 0)
        p = result['results']['projector']['predictions']
        self.assertEqual(p, {'AB':['1/2','1/2','0','0'], 'BA':['1/4']*4})
        self.assertEqual(result['results']['projector']['heldout']['brier'], '5/8')
        self.assertFalse(result['checks']['heldout_used_for_selection'])

    def test_changed_heldout_does_not_choose_another_candidate(self):
        data = example('question_order_fit')
        before = Q.run('question_order_fit', data)['results']
        data['heldout'] = {'AB':[0,0,0,40], 'BA':[40,0,0,0]}
        after = Q.run('question_order_fit', data)['results']
        self.assertEqual(before['selected_candidate'], after['selected_candidate'])
        self.assertEqual(before['candidate_training'], after['candidate_training'])
        self.assertEqual(after['projector']['heldout']['likelihood_status'], 'zero_probability_observed')
        self.assertIsNone(after['projector']['heldout']['mean_negative_log_likelihood_nats'])

    def test_training_data_can_change_selected_model(self):
        data = example('question_order_fit')
        data['train'] = {'AB':[24,0,0,0], 'BA':[24,0,0,0]}
        self.assertEqual(Q.run('question_order_fit', data)['results']['selected_candidate'], 1)

    def test_classical_count_model_and_log_score(self):
        result = Q.run('question_order_fit', example('question_order_fit'))['results']['classical_contextual']
        self.assertEqual(result['predictions']['AB'], ['13/28','13/28','1/28','1/28'])
        self.assertEqual(result['predictions']['BA'], ['1/4']*4)
        self.assertGreater(F(result['heldout']['brier']), F(5,8))
        self.assertEqual(result['heldout']['likelihood_status'], 'finite')

    def test_wrong_projector_and_invalid_counts_refuse(self):
        for change in ('matrix','counts','zero','large','bool','float'):
            data = example('question_order_fit')
            if change=='matrix': data['candidates'][0]['A']=[[1,1],[0,0]]
            if change=='counts': data['heldout']['AB']=[0,0,0,0]
            if change=='zero': data['candidates'][0]['state']=[0,0]
            if change=='large': data['candidates']*=17
            if change=='bool': data['train']['AB'][0]=True
            if change=='float': data['smoothing']=0.5
            with self.subTest(change=change), self.assertRaises(ValueError):
                Q.run('question_order_fit', data)

    def test_density_measurement_and_dephasing_reference(self):
        result = Q.run('density_measurements', example('density_measurements'))
        self.assertEqual(result['results']['probabilities'], ['1','0'])
        self.assertEqual(result['results']['after_basis_dephasing'], ['1/2','1/2'])
        self.assertTrue(all(result['checks'].values()))

    def test_povm_and_density_refusals(self):
        for change in ('negative','trace','effects','sum'):
            data = example('density_measurements')
            if change=='negative': data['density']=[[1,1],[1,0]]
            if change=='trace': data['density']=[[1,0],[0,1]]
            if change=='effects': data['effects'][0]=[[-1,0],[0,1]]
            if change=='sum': data['effects']=data['effects'][:1]
            with self.subTest(change=change), self.assertRaises(ValueError):
                Q.run('density_measurements', data)

    def test_circuit_equalities_and_non_equality(self):
        g=lambda name,wires:{'gate':name,'wires':wires}
        for qubits,left,right in [(1,[g('H',[0]),g('H',[0])],[]),
                                  (1,[g('H',[0]),g('Z',[0]),g('H',[0])],[g('X',[0])]),
                                  (2,[g('CNOT',[0,1]),g('CNOT',[0,1])],[]),
                                  (2,[g('SWAP',[0,1]),g('SWAP',[0,1])],[])]:
            result=Q.run('circuit_rewrite',{'qubits':qubits,'left':left,'right':right})
            self.assertTrue(result['results']['equivalent_channels'])
            self.assertTrue(all(result['checks'].values()))
        self.assertFalse(Q.run('circuit_rewrite',{'qubits':1,'left':[g('H',[0])],'right':[]})['results']['equivalent_channels'])

    def test_global_phase_and_control_direction(self):
        g=lambda name,wires:{'gate':name,'wires':wires}
        phase=[g('X',[0]),g('Z',[0]),g('X',[0]),g('Z',[0])]
        self.assertTrue(Q.run('circuit_rewrite',{'qubits':1,'left':phase,'right':[]})['results']['equivalent_channels'])
        self.assertFalse(Q.run('circuit_rewrite',{'qubits':2,'left':[g('CNOT',[0,1])],'right':[g('CNOT',[1,0])]})['results']['equivalent_channels'])

    def test_circuit_resource_and_wire_refusals(self):
        for bad in [{'gate':'H','wires':[True]}, {'gate':'H','wires':[[0]]},
                    {'gate':'CNOT','wires':[0,0]}, {'gate':'T','wires':[0]}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Q.run('circuit_rewrite', {'qubits':2,'left':[bad],'right':[]})
        with self.assertRaises(ValueError):
            Q.run('circuit_rewrite',{'qubits':2,'left':[{'gate':'X','wires':[0]}]*33,'right':[]})

    def test_composition_reversal_negation_and_mixture(self):
        data=example('tensor_semantics')
        result=Q.run('tensor_semantics',data)['results']
        self.assertEqual((result['composed_score'],result['subject_object_reversed_score']),('1','0'))
        data['negated']=True
        self.assertEqual(Q.run('tensor_semantics',data)['results']['composed_score'],'0')
        data.update(subject=['1/2','1/2'],negated=False,expected='1/2')
        result=Q.run('tensor_semantics',data)['results']
        self.assertEqual(result['squared_error'],'0')
        self.assertEqual(result['baseline_squared_error'],'1/4')


class RegistryBoundary(unittest.TestCase):
    def setUp(self):
        self.modules=patch.object(E,'MODULES',('symblic.experiments.quantum',))
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_every_example_recomputes_and_tamper_is_detected(self):
        for row in E.catalog()['experiments']:
            receipt=E.run(row['id'],row['example'])
            self.assertTrue(E.verify(receipt)['ok'])
            changed=deepcopy(receipt)
            changed['output']['checks']['invented']=True
            changed['sha256']=E.digest({k:v for k,v in changed.items() if k!='sha256'})
            self.assertFalse(E.verify(changed)['ok'])

    def test_pin_tampering_and_input_drift_are_detected(self):
        receipt=E.run('circuit_rewrite',example('circuit_rewrite'))
        receipt['implementation_sha256']['symblic/experiments/quantum.py']='0'*64
        self.assertFalse(E.verify(receipt)['ok'])
        receipt=E.run('circuit_rewrite',example('circuit_rewrite'))
        receipt['input']['right']=[{'gate':'X','wires':[0]}]
        self.assertFalse(E.verify(receipt)['ok'])

    def test_bool_integer_substitutions_do_not_verify(self):
        original=E.run('circuit_rewrite',example('circuit_rewrite'))
        for key,value in [('model_calls',False),('adapter_version',True)]:
            changed=deepcopy(original);changed[key]=value
            self.assertFalse(E.verify(changed)['ok'])
            changed['sha256']=E.digest({k:v for k,v in changed.items() if k!='sha256'})
            self.assertFalse(E.verify(changed)['ok'])
        changed=deepcopy(original)
        check=next(key for key,value in changed['output']['checks'].items() if value is True)
        changed['output']['checks'][check]=1
        self.assertFalse(E.verify(changed)['ok'])
        changed['sha256']=E.digest({k:v for k,v in changed.items() if k!='sha256'})
        self.assertFalse(E.verify(changed)['ok'])

    def test_duplicate_float_depth_size_cycles_and_private_error(self):
        for raw in ['{"x":1,"x":2}', '[0.1]', 'NaN', '['*30+'0'+']'*30, '"'+'x'*65537+'"']:
            with self.subTest(raw=raw[:20]), self.assertRaises(E.ExperimentError): E.loads(raw)
        cycle=[];cycle.append(cycle)
        with self.assertRaises(E.ExperimentError):E.bounded(cycle)
        with patch.object(Q,'run',side_effect=ValueError('private source secret 123')):
            with self.assertRaisesRegex(E.ExperimentError,'^invalid_experiment_input$'):
                E.run('circuit_rewrite',{})

    def test_cli_stdin_works(self):
        result=subprocess.run([sys.executable,'-m','symblic.experiments.registry','run','circuit_rewrite','-'],
                              input=json.dumps(example('circuit_rewrite')),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout)['experiment'],'circuit_rewrite')


if __name__=='__main__':
    unittest.main()
