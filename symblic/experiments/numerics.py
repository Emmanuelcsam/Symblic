"""Experiments: refined field solutions, SPD-metric reconciliation and transport-plan certificates.

Research experiment, no result claimed.

Experiments:
    field-refinement       solve a manufactured steady heat field with units and exact boundaries, check independent
                           stencil residuals and the error under mesh refinement
    spd-reconciliation     project supplied observations onto affine constraints using a symmetric positive-definite
                           metric, then check feasibility and stationarity independently
    transport-certificate  check a supplied finite transport plan: mass balance, dual inequalities, exact optimality gap

These adapters run native Symblic programs, so the registry also requires the kernel's loaded-runtime identity
check (USES_NATIVE_KERNEL).

Depends on: ``symblic.kernel.language``, ``symblic.adapters.variational``, ``symblic.adapters.projection`` and
``symblic.experiments.quantum``. Run through ``symblic.experiments.registry``.
Sources: FIELD_SOURCE (MIT 18.086), KKT_SOURCE (Boyd and Vandenberghe, Convex Optimization).
"""

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)
from copy import deepcopy
from fractions import Fraction as F

from symblic.kernel import language as S
from symblic.adapters import variational as V
from symblic.adapters import projection as P
from symblic.experiments.quantum import fields, integer, q, wire

VERSION = 1
USES_NATIVE_KERNEL = True
# Pinned in every receipt (see registry._identity); the rest of the native kernel is covered by the kernel's
# own loaded-runtime check, which USES_NATIVE_KERNEL turns on.
DEPENDENCIES = ('symblic.experiments.quantum', 'symblic.kernel.language', 'symblic.kernel.execution_pins',
                'symblic.adapters.variational', 'symblic.adapters.projection')
FIELD_SOURCE = 'https://math.mit.edu/classes/18.086/2007/'
KKT_SOURCE = 'https://web.stanford.edu/~boyd/cvxbook/'


def vector(value, minimum=1, maximum=8):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError('vector_bound')
    return [q(item) for item in value]


def matrix(value, rows, columns):
    if type(value) is not list or len(value) != rows:
        raise ValueError('matrix_shape')
    return [vector(row, columns, columns) for row in value]


def dot(left, right, work):
    result = F(0)
    for a,b in zip(left,right):
        result = work.add(result,work.mul(a,b))
    return result


def field_refinement(data):
    fields(data,'length_m conductivity_W_per_m_K amplitude_K intervals')
    length, conductivity, amplitude = (q(data[key]) for key in ('length_m','conductivity_W_per_m_K','amplitude_K'))
    if length <= 0 or conductivity <= 0 or amplitude == 0:
        raise ValueError('positive_length_conductivity_nonzero_amplitude')
    levels = data['intervals']
    if type(levels) is not list or not 2 <= len(levels) <= 4:
        raise ValueError('refinement_levels')
    levels = [integer(n,2,32) for n in levels]
    if levels != sorted(set(levels)):
        raise ValueError('increasing_unique_intervals')
    rows=[]
    for intervals in levels:
        size = intervals-1; h = length/intervals
        scale = conductivity/(h*h)
        A = [[scale*(2 if i==j else -1 if abs(i-j)==1 else 0) for j in range(size)] for i in range(size)]
        coordinates = [F(i,intervals) for i in range(1,intervals)]
        forcing = [-conductivity*amplitude/(length*length)*(2-12*z+12*z*z) for z in coordinates]
        exact = [amplitude*z*z*(1-z)*(1-z) for z in coordinates]
        wire([A,forcing,exact])
        solved = V.minimize_quadratic(A,forcing)
        if not V.verify_quadratic(A,forcing,solved):
            raise ValueError('field_witness_failure')
        values=[F(0),*solved['x'],F(0)]
        # Independent nearest-neighbour stencil, including both Dirichlet endpoints.
        residual = [scale*(2*values[i]-values[i-1]-values[i+1])-forcing[i-1] for i in range(1,intervals)]
        errors = [abs(a-b) for a,b in zip(values[1:-1],exact)]
        truncation = [A[i][i]*exact[i]+sum(A[i][j]*exact[j] for j in range(size) if j!=i)-forcing[i] for i in range(size)]
        max_error=max(errors)
        rows.append({'intervals':intervals,'spacing_m':h,
                     'coordinates_m':[h*i for i in range(intervals+1)],
                     'computed_temperature_K':values,'manufactured_temperature_K':[F(0),*exact,F(0)],
                     'forcing_W_per_m3':forcing,'discrete_residual_W_per_m3':residual,
                     'truncation_residual_W_per_m3':truncation,
                     'max_error_K':max_error,'error_over_normalized_spacing_squared_K':max_error*intervals**2,
                     'previous_to_current_error_ratio':rows[-1]['max_error_K']/max_error if rows and max_error else None,
                     'witness_checks':solved['checks']})
    return {'arithmetic':'exact rational finite differences; no floating-point solver',
            'results':{'equation':'-k d²u/dx² = f(x)',
                       'manufactured_solution':'u(x) = amplitude_K * (x/L)^2 * (1-x/L)^2',
                       'boundary_conditions':{'u(0)_K':0,'u(L)_K':0},'meshes':rows},
            'checks':{'every_discrete_residual_zero':all(not x for row in rows for x in row['discrete_residual_W_per_m3']),
                      'both_boundary_values_exact':True,'independent_quadratic_witness':True},
            'limits':['Constant-conductivity one-dimensional steady heat equation with a manufactured signed source and temperature relative to boundary value.',
                      'SI inputs: length in metres, conductivity in W/(m K), temperature in kelvin; forcing and residual in W/m³.',
                      '2–4 meshes with 2–32 intervals, exact zero Dirichlet endpoints. Refinement measures this polynomial fixture, not arbitrary PDE convergence or a physical device.',
                      'The algebraic residual can be zero while discretization error is nonzero. This experiment reports both.',
                      'Native quadratic solver enforces its 4096-bit and 200000-operation cap per mesh; no external solver, model or hardware run.'],
            'sources':[FIELD_SOURCE]}


def spd_reconciliation(data):
    fields(data,'original metric constraints targets')
    original=vector(data['original']);n=len(original)
    metric=matrix(data['metric'],n,n)
    constraints=data['constraints']
    if type(constraints) is not list or not 1<=len(constraints)<=n:
        raise ValueError('constraint_bound')
    count=len(constraints);C=matrix(constraints,count,n);d=vector(data['targets'],count,count)
    work=V._Work(8,4096,200000)
    metric,_=V._problem(metric,[0]*n,work)
    lower,diagonal=V._ldlt(metric,work)
    columns=[V._solve(lower,diagonal,row,work) for row in C]
    gram=[[dot(a,b,work) for b in columns] for a in C]
    residual=[work.sub(dot(row,original,work),target) for row,target in zip(C,d)]
    gl,gd=V._ldlt(gram,work)
    multipliers=V._solve(gl,gd,residual,work)
    correction=[dot([col[i] for col in columns],multipliers,work) for i in range(n)]
    value=[work.sub(old,change) for old,change in zip(original,correction)]
    delta=[work.sub(new,old) for old,new in zip(original,value)]
    primal=[work.sub(dot(row,value,work),target) for row,target in zip(C,d)]
    stationarity=[work.add(dot(row,delta,work),dot([c[i] for c in C],multipliers,work)) for i,row in enumerate(metric)]
    if any(primal) or any(stationarity):
        raise ValueError('kkt_verification_failure')
    objective=work.div(dot(delta,[dot(row,delta,work) for row in metric],work),F(2))
    diagonal_only=P.reconcile(original,C,d,[metric[i][i] for i in range(n)])
    baseline=[F(x) for x in diagonal_only['value']]
    moved=[work.sub(new,old) for old,new in zip(original,baseline)]
    baseline_objective=work.div(dot(moved,[dot(row,moved,work) for row in metric],work),F(2))
    return {'arithmetic':'exact rational SPD constrained quadratic; dimensionless supplied metric',
            'results':{'original':original,'reconciled':value,'correction':delta,'multipliers':multipliers,
                       'original_constraint_residual':residual,'primal_residual':primal,'stationarity_residual':stationarity,
                       'objective_half_squared_metric_distance':objective,
                       'diagonal_metric_baseline':baseline,'baseline_objective_under_full_metric':baseline_objective,
                       'full_metric_checked_operations_excluding_diagonal_baseline':work.used},
            'checks':{'metric_positive_definite':True,'constraints_independent':True,
                      'primal_feasible':True,'kkt_stationary':True,
                      'no_worse_than_diagonal_baseline_under_full_metric':objective<=baseline_objective},
            'limits':['1–8 coordinates and 1–n independent affine constraint rows; metric must be symmetric positive definite.',
                      'Minimizes (y-x)^T M (y-x)/2 exactly. The diagonal baseline is assessed using the same full objective.',
                      'Inputs are dimensionless or pre-normalized by the caller. No latent metric is inferred and an adjusted value is not a new measurement.',
                      'Original observations remain in the receipt; dependent or inconsistent constraint systems refuse.'],
            'sources':[KKT_SOURCE]}


def transport_certificate(data):
    fields(data,'left_mass right_mass costs plan left_dual right_dual cost_unit')
    left=vector(data['left_mass']);right=vector(data['right_mass']);n=len(left);m=len(right)
    cost=matrix(data['costs'],n,m);plan=matrix(data['plan'],n,m)
    u=vector(data['left_dual'],n,n);v=vector(data['right_dual'],m,m)
    unit=data['cost_unit']
    if type(unit) is not str or not 1<=len(unit)<=80 or any(ord(c)<32 for c in unit):
        raise ValueError('cost_unit')
    if any(x<0 for x in left+right) or sum(left)!=1 or sum(right)!=1 or any(x<0 for row in cost for x in row):
        raise ValueError('transport_probability_cost_domain')
    row_residual=[sum(row)-mass for row,mass in zip(plan,left)]
    col_residual=[sum(plan[i][j] for i in range(n))-right[j] for j in range(m)]
    primal=not any(row_residual+col_residual) and all(x>=0 for row in plan for x in row)
    slack=[[cost[i][j]-u[i]-v[j] for j in range(m)] for i in range(n)]
    dual=all(x>=0 for row in slack for x in row)
    cost_value=sum(cost[i][j]*plan[i][j] for i in range(n) for j in range(m))
    dual_value=sum(a*b for a,b in zip(left,u))+sum(a*b for a,b in zip(right,v))
    gap=cost_value-dual_value
    return {'arithmetic':'exact rational primal/dual finite Kantorovich certificate',
            'results':{'supplied_plan':plan,'row_mass_residual':row_residual,'column_mass_residual':col_residual,
                       'dual_slacks':slack,'primal_cost':cost_value,'dual_objective':dual_value,'certified_lower_bound':dual_value if dual else None,
                       'duality_gap':gap,'cost_unit':unit,'optimality_certified':primal and dual and gap==0},
            'checks':{'primal_feasible':primal,'dual_feasible':dual,'gap_zero':gap==0},
            'limits':['1–8 atoms on each side with normalized nonnegative masses; supplied nonnegative ground-cost matrix.',
                      'Checks a supplied plan and dual potentials. A feasible plan plus feasible dual and zero gap certifies its finite optimum.',
                      'Nonzero gap leaves optimality unestablished; invalid witnesses remain visibly invalid. This adapter does not search for a plan.',
                      'Cost units are caller declarations and no metric, embedding or semantic fidelity is inferred.'],
            'sources':[KKT_SOURCE]}


_ENTRIES=[
    {'id':'field-refinement','title':'Check a field across refined meshes','summary':'Solve a manufactured steady heat field with units, exact boundaries, independent stencil residuals and refinement errors.',
     'example':{'length_m':2,'conductivity_W_per_m_K':3,'amplitude_K':16,'intervals':[4,8,16]},'sources':[FIELD_SOURCE]},
    {'id':'spd-reconciliation','title':'Reconcile observations with a full metric','summary':'Project supplied observations onto affine constraints using an SPD metric and independently check feasibility and stationarity.',
     'example':{'original':[0,0],'metric':[[2,1],[1,3]],'constraints':[[1,1]],'targets':[1]},'sources':[KKT_SOURCE]},
    {'id':'transport-certificate','title':'Check an optimal transport plan','summary':'Check supplied finite transport mass balances, dual inequalities and exact optimality gap.',
     'example':{'left_mass':['1/2','1/2'],'right_mass':['1/2','1/2'],'costs':[[0,1],[1,0]],'plan':[['1/2',0],[0,'1/2']],'left_dual':[0,0],'right_dual':[0,0],'cost_unit':'metres'},'sources':[KKT_SOURCE]},
]


def catalog():
    return deepcopy(_ENTRIES)


def run(experiment_id,data):
    functions={'field-refinement':field_refinement,'spd-reconciliation':spd_reconciliation,'transport-certificate':transport_certificate}
    if experiment_id not in functions:
        raise ValueError('unknown_experiment')
    try:
        return wire(functions[experiment_id](data))
    except S.SymblicError:
        raise ValueError('finite_numerical_domain_or_budget') from None
