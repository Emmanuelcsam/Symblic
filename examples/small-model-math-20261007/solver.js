function solveLinear(A, b) {
    const n = A.length;
    const det = determinant(A);
    
    if (det !== 0) {
        // Use Cramer's rule: replace column j with b, compute det, normalize
        const solution = [];
        for (let j = 0; j < n; j++) {
            // Create new matrix with column j replaced by b
            const Aj = [...A.map(row => [...row])];
            for (let i = 0; i < n; i++) {
                Aj[i][j] = b[i];
            }
            const detAj = determinant(Aj);
            solution.push(normalizeFraction(detAj, det));
        }
        return { kind: "unique", solution };
    }
    
    // Determinant is zero: check rank of A and augmented matrix
    const rankA = matrixRank(A);
    const augmented = A.map(row => [...row, 0]).map((row, i) => [...row, b[i]]);
    const rankAugmented = matrixRank(augmented);
    
    if (rankAugmented > rankA) {
        return { kind: "inconsistent" };
    } else {
        return { kind: "singular" };
    }
}