"""Experiments: seeded particle filtering, Ising energy search and noisy-codebook decoding.

Research experiment, no result claimed.

Experiments:
    particle_filter  a seeded bootstrap particle filter on a finite hidden-state model, with effective sample size
                     and its error against the exact finite posterior
    ising_search     seeded single-spin descent on a small Ising energy compared with exhaustive optimisation,
                     keeping every degenerate minimum and the energy gap
    noisy_codebook   decode supplied noisy vectors against two equal-rate codebooks and compare distortion,
                     ambiguity and energy

Random draws use Python's seeded ``random.Random``; probabilities stay exact rationals.

Depends on: ``symblic.experiments.quantum`` (validation helpers). Run through ``symblic.experiments.registry``.
Sources: SMC_SOURCE (Doucet and Johansen), ISING_SOURCE (Lucas, Ising formulations), CODE_SOURCE.
"""

# Bind the executing module to its exact first-party source before dependencies.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
from copy import deepcopy
from fractions import Fraction as F
from math import lcm
import platform
import random

from symblic.experiments.quantum import fields, integer, q, wire, fail

VERSION = 1
DEPENDENCIES = ('symblic.experiments.quantum',)
SMC_SOURCE = 'https://www.stats.ox.ac.uk/~doucet/doucet_johansen_tutorialPF.pdf'
ISING_SOURCE = 'https://arxiv.org/abs/1302.5843'
CODE_SOURCE = 'https://arxiv.org/abs/1603.04246'


def vector(value, minimum=1, maximum=16):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        fail('vector_bound')
    return [q(x) for x in value]


def distribution(value, size=None):
    result=vector(value)
    if size is not None and len(result)!=size:
        fail('distribution_shape')
    if any(x<0 for x in result) or sum(result)!=1:
        fail('probability_normalization')
    return result


def weighted_draw(rng, probabilities):
    common=1
    for p in probabilities:
        common=lcm(common,p.denominator)
        if common.bit_length()>4096:
            fail('arithmetic_bound')
    weights=[p.numerator*(common//p.denominator) for p in probabilities]
    selected=rng.randrange(sum(weights))
    for index, weight in enumerate(weights):
        if selected<weight:
            return index
        selected-=weight
    fail('sampling_internal')


def particle_filter(data):
    fields(data,'prior transition likelihoods particles seed')
    prior=distribution(data['prior']);n=len(prior)
    transition=data['transition']
    if type(transition) is not list or len(transition)!=n:
        fail('transition_shape')
    transition=[distribution(row,n) for row in transition]
    likelihoods=data['likelihoods']
    if type(likelihoods) is not list or not 1<=len(likelihoods)<=16:
        fail('step_bound')
    likelihoods=[vector(row,n,n) for row in likelihoods]
    if any(not 0<=x<=1 for row in likelihoods for x in row):
        fail('likelihood_bound')
    count=integer(data['particles'],1,128)
    seed=integer(data['seed'],0,2**32-1)
    rng=random.Random(seed)
    particles=[weighted_draw(rng,prior) for _ in range(count)]
    oracle=prior
    rows=[];status='completed';draws=count
    for index, likelihood in enumerate(likelihoods):
        predicted=[sum(oracle[i]*transition[i][j] for i in range(n)) for j in range(n)]
        exact_weights=[p*l for p,l in zip(predicted,likelihood)]
        normalizer=sum(exact_weights)
        if not normalizer:
            status='impossible_observation'
            rows.append({'step':index+1,'status':status,'exact_predictive':predicted})
            break
        oracle=[p/normalizer for p in exact_weights]
        # Bootstrap proposal is the declared transition. Resampling after each
        # observation resets prior particle weights to uniform.
        particles=[weighted_draw(rng,transition[p]) for p in particles];draws+=count
        weights=[likelihood[p] for p in particles]
        total=sum(weights)
        if not total:
            status='particle_collapse'
            rows.append({'step':index+1,'status':status,'oracle':oracle})
            break
        weights=[w/total for w in weights]
        posterior=[sum(w for p,w in zip(particles,weights) if p==state) for state in range(n)]
        ess=1/sum(w*w for w in weights)
        rows.append({'step':index+1,'status':'weighted','posterior':posterior,'oracle':oracle,
                     'effective_sample_size':ess,'total_variation_error':sum(abs(a-b) for a,b in zip(posterior,oracle))/2})
        wire(rows[-1])  # Refuse bit growth before another step.
        particles=[particles[weighted_draw(rng,weights)] for _ in range(count)];draws+=count
    return {'arithmetic':'exact rational weights and oracle; seeded discrete sampling',
            'results':{'status':status,'steps':rows,'categorical_draws':draws,'seed':seed,
                       'random_engine':'Python random.Random '+platform.python_version()},
            'checks':{'transition_rows_normalized':True,'no_model_votes_used':True},
            'limits':['16 states, 16 observation steps, 128 particles; transition occurs before each likelihood.',
                      'Finite bootstrap filter with multinomial resampling; ESS and oracle error measure this supplied model only.',
                      'Particle collapse and impossible observations remain separate recorded outcomes.'],
            'sources':[SMC_SOURCE]}


def ising_search(data):
    fields(data,'fields couplings seed steps restarts')
    h=vector(data['fields'],1,10);n=len(h)
    rows=data['couplings']
    if type(rows) is not list or len(rows)!=n:
        fail('coupling_shape')
    j=[vector(row,n,n) for row in rows]
    if any(j[i][i] or any(j[i][k]!=j[k][i] for k in range(n)) for i in range(n)):
        fail('coupling_symmetry_diagonal')
    steps=integer(data['steps'],1,256);restarts=integer(data['restarts'],1,16)
    seed=integer(data['seed'],0,2**32-1);rng=random.Random(seed)
    def energy(state):
        return sum(a*s for a,s in zip(h,state))+sum(j[i][k]*state[i]*state[k] for i in range(n) for k in range(i+1,n))
    exact=[]
    for code in range(2**n):
        state=[1 if code&(1<<i) else -1 for i in range(n)]
        exact.append((energy(state),state))
    minimum=min(row[0] for row in exact)
    ground=[row[1] for row in exact if row[0]==minimum]
    attempts=[]
    for _ in range(restarts):
        state=[rng.choice([-1,1]) for _ in range(n)];best=energy(state);accepted=0
        for _ in range(steps):
            at=rng.randrange(n);candidate=state[:];candidate[at]*=-1
            value=energy(candidate)
            if value<=best:
                state,best=candidate,value;accepted+=1
        attempts.append({'state':state,'energy':best,'gap_to_exhaustive_minimum':best-minimum,'accepted_moves':accepted})
    selected=min(range(restarts),key=lambda i:(attempts[i]['energy'],i))
    return {'arithmetic':'exact rational energies; seeded random single-spin descent',
            'results':{'selected_restart':selected,'heuristic':attempts,'exact_minimum':minimum,'degeneracy':len(ground),
                       'ground_states':ground[:16],'ground_states_truncated':len(ground)>16,
                       'exhaustive_states':2**n,'proposals':steps*restarts,'seed':seed,
                       'random_engine':'Python random.Random '+platform.python_version()},
            'checks':{'all_reported_candidates_rechecked':all(energy(r['state'])==r['energy'] for r in attempts),
                       'gaps_nonnegative':all(r['gap_to_exhaustive_minimum']>=0 for r in attempts)},
            'limits':['At most 10 spins; energy is sum(h_i*s_i)+sum_{i<j}(J_ij*s_i*s_j).',
                      'This implements classical seeded descent and exhaustive certification, not annealing hardware or a quantum speedup.',
                      'The exhaustive baseline supplies the gap; heuristic search alone does not certify optimality.'],
            'sources':[ISING_SOURCE]}


def codebook(data):
    fields(data,'codebook baseline samples')
    def readbook(value):
        if type(value) is not list or not 2<=len(value)<=64:
            fail('codebook_bound')
        result=[vector(v,1,24) for v in value]
        if any(len(v)!=len(result[0]) for v in result) or len({tuple(v) for v in result})!=len(result):
            fail('codebook_shape_or_duplicate')
        return result
    book,baseline=readbook(data['codebook']),readbook(data['baseline'])
    if len(book)!=len(baseline) or len(book[0])!=len(baseline[0]):
        fail('baseline_rate_dimension_mismatch')
    samples=data['samples']
    if type(samples) is not list or not 1<=len(samples)<=128:
        fail('sample_bound')
    d=len(book[0]);decoded={'codebook':[],'baseline':[]}
    def distance(a,b):return sum((x-y)**2 for x,y in zip(a,b))
    for sample in samples:
        fields(sample,'symbol noise')
        symbol=integer(sample['symbol'],0,len(book)-1);noise=vector(sample['noise'],d,d)
        for label,codes in [('codebook',book),('baseline',baseline)]:
            noisy=[a+b for a,b in zip(codes[symbol],noise)]
            distances=[distance(noisy,c) for c in codes]
            best=min(distances);ties=[i for i,x in enumerate(distances) if x==best]
            selected=ties[0]
            decoded[label].append({'symbol':symbol,'decoded':selected,'ties':ties,'correct':selected==symbol,
                                   'noise_squared_norm':distance(noise,[F(0)]*d),
                                   'reconstruction_squared_error':distance(codes[symbol],codes[selected])})
    metrics={}
    for label,codes in [('codebook',book),('baseline',baseline)]:
        rows=decoded[label]
        metrics[label]={'symbol_errors':sum(not r['correct'] for r in rows),'tied_decodes':sum(len(r['ties'])>1 for r in rows),
                        'mean_reconstruction_squared_error':sum(r['reconstruction_squared_error'] for r in rows)/len(rows),
                        'minimum_pair_squared_distance':min(distance(codes[i],codes[j]) for i in range(len(codes)) for j in range(i)),
                        'mean_codeword_squared_norm':sum(distance(c,[F(0)]*d) for c in codes)/len(codes)}
    return {'arithmetic':'exact rational nearest-neighbor distances',
            'results':{'metrics':metrics,'samples':decoded,'dimension':d,'symbols':len(book),
                       'fixed_symbol_bits':(len(book)-1).bit_length(),'distance_evaluations':2*len(samples)*len(book)},
            'checks':{'matched_rate_and_dimension':True,'identical_supplied_noise':True},
            'limits':['At most 64 supplied codewords, dimension24, 128 noise samples; ties choose the first index and remain visible.',
                      'Equal rate/dimension does not ensure equal transmit energy; codeword norms are reported.',
                      'Generic finite codebook experiment; no E8/Leech optimality, arbitrary semantic accuracy or new packing theorem is claimed.'],
            'sources':[CODE_SOURCE]}


_CATALOG=[
 {'id':'particle_filter','title':'Particle inference with an exact reference',
  'summary':'Run a seeded bootstrap particle filter and inspect effective sample size and exact finite-model error.',
  'example':{'prior':['1/2','1/2'],'transition':[['3/4','1/4'],['1/4','3/4']],
             'likelihoods':[['4/5','1/5'],['1/5','4/5']],'particles':64,'seed':17},
  'sources':[SMC_SOURCE],'limits':['16 states/steps, 128 particles; supplied transition and likelihoods.']},
 {'id':'ising_search','title':'Search an Ising energy and check its gap',
  'summary':'Compare seeded single-spin descent with exhaustive optimization, retaining degenerate minima.',
  'example':{'fields':[0,0],'couplings':[[0,-1],[-1,0]],'steps':16,'restarts':4,'seed':7},
  'sources':[ISING_SOURCE],'limits':['10 spins; 256 proposals per restart; 16 restarts.']},
 {'id':'noisy_codebook','title':'Compare error-correcting representations',
  'summary':'Decode supplied noisy vectors against two equal-rate codebooks; compare distortion, ambiguity and energy.',
  'example':{'codebook':[[-1,-1],[1,1]],'baseline':[[-1,0],[1,0]],
             'samples':[{'symbol':0,'noise':['6/5',0]},{'symbol':1,'noise':['-6/5',0]}]},
  'sources':[CODE_SOURCE],'limits':['64 codewords, dimension24, 128 declared noise samples.']},
]
_RUNNERS={'particle_filter':particle_filter,'ising_search':ising_search,'noisy_codebook':codebook}


def catalog():return deepcopy(_CATALOG)


def run(experiment_id,data):
    if experiment_id not in _RUNNERS:fail('unknown_experiment')
    return wire(_RUNNERS[experiment_id](data))
