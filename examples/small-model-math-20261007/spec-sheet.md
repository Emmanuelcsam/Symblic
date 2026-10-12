# exact-linear.js
Finite exact linear algebra using model-generated units and an unchanged independent Fraction oracle.
## Shared
Inputs are small safe integers. Never mutate any input. Reuse direct dependency functions exactly.
The unique solution format is an array of reduced [numerator, positiveDenominator] pairs, including [integer,1].
For this trial use top-level function declarations, not const exports. Output code only.
## Unit `normalizeFraction(n,d)`
Only the named top-level function declaration is allowed; local functions and const/let are allowed. Reply with only one JavaScript code fence, no explanation. No I/O, global state or input mutation. All arithmetic in tested inputs is within safe integer range. Write function normalizeFraction(n,d). Inputs n,d are integers and d is nonzero. Return a NEW two-element array [numerator,denominator] for n/d reduced by Euclidean greatest common divisor, with positive denominator. For zero numerator return [0,1]. Normalize negative denominator signs. Throw Error if d is zero. Do not use floating approximation.
Examples:
    normalizeFraction(6,8) ==> [3,4]
    normalizeFraction(-6,8) ==> [-3,4]
    normalizeFraction(6,-8) ==> [-3,4]
    normalizeFraction(-6,-8) ==> [3,4]
    normalizeFraction(0,-8) ==> [0,1]
    normalizeFraction(17,13) ==> [17,13]
    (()=>{try{normalizeFraction(1,0);return false;}catch(e){return true;}})() ==> true
## Unit `determinant(A)`
Use only the named top-level function declaration. Local functions and let/const are allowed. Reply with code only, no explanation. No I/O, global state, input mutation, dependency redefinitions, wrapper or module/export. All specified integer arithmetic is within JavaScript safe integer range. Return the exact integer determinant of a square integer matrix A of size 1, 2, or 3. Use the signed determinant formula (or cofactor expansion). A 1 by 1 determinant is its sole element; a 2 by 2 determinant is the first diagonal product minus the second diagonal product. Do not return absolute value, floating approximations or Boolean singularity. Do not alter A or its rows.
Examples:
    determinant([[0]]) ==> 0
    determinant([[7]]) ==> 7
    determinant([[-3]]) ==> -3
    determinant([[1,2],[3,4]]) ==> -2
    determinant([[0,2],[3,4]]) ==> -6
    determinant([[1,2],[2,4]]) ==> 0
    determinant([[1,0,0],[0,1,0],[0,0,1]]) ==> 1
    determinant([[2,1,-1],[-3,-1,2],[-2,1,2]]) ==> -1
    determinant([[0,0,2],[0,3,0],[4,0,0]]) ==> -24
    determinant([[1,2,3],[2,4,6],[0,1,1]]) ==> 0
    determinant([[-2,3,1],[4,-1,2],[0,5,3]]) ==> 10
    determinant(Object.freeze([Object.freeze([0,2]),Object.freeze([3,4])])) ==> -6
## Unit `matrixRank(A)`
Use only the named top-level function declaration. Local functions and let/const are allowed. Reply with code only, no explanation. No I/O, global state, input mutation, dependency redefinitions, wrapper or module/export. All specified integer arithmetic is within JavaScript safe integer range. Return the exact integer rank of a NONEMPTY rectangular integer matrix A with 1 to 3 rows and 1 to 4 columns. Use nonzero minors: when there are 3 rows and at least 3 columns, examine EVERY triple of distinct columns; any nonzero 3 by 3 determinant gives rank 3. Otherwise examine EVERY pair of distinct rows and pair of distinct columns; any nonzero 2 by 2 determinant gives rank 2. Otherwise any nonzero matrix entry gives rank 1; an all-zero matrix gives rank 0. Use the supplied determinant for square minors. A non-leading column may be the only nonzero column. Never assume a rectangular matrix itself has a determinant. Do not alter A or its rows. Prior candidate feedback: matrixRank([[1,2,3],[2,4,6]]) is 1, not 2, because all two-by-two minors are zero. A nonzero entry below a nonzero entry is NOT an independence test. Use the supplied determinant for every square minor. Do not add a separate two-row proportionality heuristic; the same complete two-by-two minor enumeration applies to two or three rows.
Uses: `determinant`
Examples:
    matrixRank([[0]]) ==> 0
    matrixRank([[7]]) ==> 1
    matrixRank([[0,0,0,0]]) ==> 0
    matrixRank([[0,3,0,0]]) ==> 1
    matrixRank([[0],[2],[0]]) ==> 1
    matrixRank([[0,0],[0,0]]) ==> 0
    matrixRank([[1,2,3],[2,4,6]]) ==> 1
    matrixRank([[0,1,0],[0,0,2]]) ==> 2
    matrixRank([[1,2,3,4],[2,4,6,9]]) ==> 2
    matrixRank([[1,0,0,0],[0,1,0,0],[0,0,1,0]]) ==> 3
    matrixRank([[0,1,0,0],[0,0,1,0],[0,0,0,1]]) ==> 3
    matrixRank([[1,2,3,4],[2,4,6,8],[0,1,1,2]]) ==> 2
    matrixRank([[1,2,3,4],[2,4,6,9],[0,1,1,2]]) ==> 3
    matrixRank([[0,0,0,0],[0,0,0,0],[0,0,0,0]]) ==> 0
    matrixRank([[1,2,0],[3,6,0],[2,4,0]]) ==> 1
    matrixRank(Object.freeze([Object.freeze([0,1,0,0]),Object.freeze([0,0,1,0]),Object.freeze([0,0,0,1])])) ==> 3
## Unit `solveLinear(A,b)`
Use only the named top-level function declaration. Local functions and let/const are allowed. Reply with code only, no explanation. No I/O, global state, input mutation, dependency redefinitions, wrapper or module/export. All specified integer arithmetic is within JavaScript safe integer range. Solve A*x=b for a square integer matrix A of size n=1..3 and integer RHS array b of length n. Only three exact result shapes are allowed: {kind:"unique",solution:[[numerator,positiveDenominator],...]} with n reduced fraction PAIRS; {kind:"singular"} for consistent systems with infinitely many solutions; or {kind:"inconsistent"} for no solution. Use supplied determinant(A). If nonzero, use Cramer's rule: for each column j, create a NEW matrix replacing column j of A with b, compute its determinant, then call supplied normalizeFraction(thatDeterminant,originalDeterminant). Put that whole reduced pair in solution[j], not only its numerator. If original determinant is zero, compare matrixRank(A) with matrixRank(the new integer augmented matrix formed by appending b[i] to row i); larger augmented rank means inconsistent, otherwise singular. These matrices contain ordinary integers throughout; only final solution entries are rational pairs. Never modify A, b or any input row. Reuse the supplied helper functions, do not implement elimination or redefine dependencies.
Uses: `normalizeFraction`, `determinant`, `matrixRank`
Examples:
    solveLinear([[2]],[1]) ==> {"kind":"unique","solution":[[1,2]]}
    solveLinear([[0, 2], [3, 4]],[4, 14]) ==> {"kind":"unique","solution":[[2,1],[2,1]]}
    solveLinear([[2, 1], [1, -1]],[1, 2]) ==> {"kind":"unique","solution":[[1,1],[-1,1]]}
    solveLinear([[3, 2], [1, -2]],[1, 0]) ==> {"kind":"unique","solution":[[1,4],[1,8]]}
    solveLinear([[2, 1, -1], [-3, -1, 2], [-2, 1, 2]],[8, -11, -3]) ==> {"kind":"unique","solution":[[2,1],[3,1],[-1,1]]}
    solveLinear([[1, 2], [2, 4]],[3, 6]) ==> {"kind":"singular"}
    solveLinear([[1, 2], [2, 4]],[3, 7]) ==> {"kind":"inconsistent"}
    solveLinear([[0]],[0]) ==> {"kind":"singular"}
    solveLinear([[0]],[1]) ==> {"kind":"inconsistent"}
    solveLinear([[0, 0, 2], [0, 3, 0], [4, 0, 0]],[-3, 2, 7]) ==> {"kind":"unique","solution":[[7,4],[2,3],[-3,2]]}
    solveLinear([[1, 2, 3], [2, 4, 6], [0, 1, 1]],[4, 8, 2]) ==> {"kind":"singular"}
    solveLinear([[1, 2, 3], [2, 4, 6], [0, 1, 1]],[4, 9, 2]) ==> {"kind":"inconsistent"}
    solveLinear([[1, 1, -1], [2, 3, 1], [1, -2, 4]],[0, -1, -11]) ==> {"kind":"unique","solution":[[-3,1],[2,1],[-1,1]]}
    solveLinear([[2, 1, -1], [2, 4, 1], [1, -2, 5]],[-1, 3, -11]) ==> {"kind":"unique","solution":[[-2,1],[2,1],[-1,1]]}
    solveLinear([[3, 1, -1], [2, 5, 1], [1, -2, 6]],[0, 7, -11]) ==> {"kind":"unique","solution":[[-1,1],[2,1],[-1,1]]}
    solveLinear([[4, 1, -1], [2, 6, 1], [1, -2, 7]],[3, 11, -11]) ==> {"kind":"unique","solution":[[0,1],[2,1],[-1,1]]}
    solveLinear([[5, 1, -1], [2, 7, 1], [1, -2, 8]],[8, 15, -11]) ==> {"kind":"unique","solution":[[1,1],[2,1],[-1,1]]}
    solveLinear([[6, 1, -1], [2, 8, 1], [1, -2, 9]],[15, 19, -11]) ==> {"kind":"unique","solution":[[2,1],[2,1],[-1,1]]}
    solveLinear([[7, 1, -1], [2, 9, 1], [1, -2, 10]],[24, 23, -11]) ==> {"kind":"unique","solution":[[3,1],[2,1],[-1,1]]}
    solveLinear(Object.freeze([Object.freeze([2,1]),Object.freeze([1,-1])]),Object.freeze([1,2])) ==> {"kind":"unique","solution":[[1,1],[-1,1]]}
## Assemble `exact-linear.js`
    /*UNITS*/
