"""Author-owned exact oracle for finite n<=3 synthetic systems; never a candidate."""
from fractions import Fraction

def expected(matrix, rhs):
    n=len(matrix)
    if not 1<=n<=3 or len(rhs)!=n or any(len(row)!=n for row in matrix):
        raise ValueError('Only square 1..3 systems are covered')
    rows=[[Fraction(x) for x in row]+[Fraction(b)] for row,b in zip(matrix,rhs)]
    pivots=[]
    for col in range(n):
        start=len(pivots)
        pivot=next((i for i in range(start,n) if rows[i][col]),None)
        if pivot is None:continue
        rows[start],rows[pivot]=rows[pivot],rows[start]
        scale=rows[start][col]
        rows[start]=[x/scale for x in rows[start]]
        for i in range(n):
            if i!=start:
                scale=rows[i][col]
                rows[i]=[x-scale*y for x,y in zip(rows[i],rows[start])]
        pivots.append(col)
    if any(not any(row[:-1]) and row[-1] for row in rows):return {'kind':'inconsistent'}
    if len(pivots)<n:return {'kind':'singular'}
    values=[Fraction(0) for _ in range(n)]
    for index,col in enumerate(pivots):values[col]=rows[index][-1]
    return {'kind':'unique','solution':[[x.numerator,x.denominator] for x in values]}

def validate(cases,observed):
    if not isinstance(observed,list) or len(observed)!=len(cases):raise ValueError('Wrong result count')
    kinds={}
    for index,(case,row) in enumerate(zip(cases,observed)):
        want=expected(case['matrix'],case['rhs'])
        if row!=want:raise ValueError('Case '+str(index)+' differs from exact Fraction oracle')
        kinds[row['kind']]=kinds.get(row['kind'],0)+1
        if row['kind']=='unique':
            for fraction in row['solution']:
                if len(fraction)!=2 or any(type(x) is not int for x in fraction) or fraction[1]<=0:raise ValueError('Noncanonical rational')
                value=Fraction(*fraction)
                if [value.numerator,value.denominator]!=fraction:raise ValueError('Unreduced rational')
            values=[Fraction(*v) for v in row['solution']]
            for coefficients,b in zip(case['matrix'],case['rhs']):
                if sum((a*x for a,x in zip(coefficients,values)),Fraction(0))!=b:raise ValueError('Nonzero exact residual')
    return {'passed':True,'finite_cases':len(cases),'classifications':kinds,'oracle':'Python Fraction with exact residual and reduced rational checks'}
