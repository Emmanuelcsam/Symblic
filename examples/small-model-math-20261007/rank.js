function matrixRank(A) {
    const rows = A.length;
    const cols = A[0].length;

    // Rank 0: all zero matrix
    for (let i = 0; i < rows; i++) {
        for (let j = 0; j < cols; j++) {
            if (A[i][j] !== 0) break;
        }
        if (A[i].some(x => x !== 0)) break;
        if (i === rows - 1) return 0;
    }

    // Case: 1 row
    if (rows === 1) {
        for (let j = 0; j < cols; j++) {
            if (A[0][j] !== 0) return 1;
        }
        return 0;
    }

    // Case: 2 rows
    if (rows === 2) {
        for (let c1 = 0; c1 < cols; c1++) {
            for (let c2 = c1 + 1; c2 < cols; c2++) {
                if (A[0][c1] * A[1][c2] !== A[0][c2] * A[1][c1]) {
                    return 2;
                }
            }
        }
        return 1;
    }

    // Case: 3 rows
    if (rows === 3) {
        // Check all 3x3 minors (all triplets of columns)
        for (let c1 = 0; c1 < cols; c1++) {
            for (let c2 = c1 + 1; c2 < cols; c2++) {
                for (let c3 = c2 + 1; c3 < cols; c3++) {
                    // Extract 3x3 submatrix
                    const sub = [
                        [A[0][c1], A[0][c2], A[0][c3]],
                        [A[1][c1], A[1][c2], A[1][c3]],
                        [A[2][c1], A[2][c2], A[2][c3]]
                    ];
                    if (determinant(sub) !== 0) {
                        return 3;
                    }
                }
            }
        }
        // Check all 2x2 minors (pairs of rows and columns)
        for (let r1 = 0; r1 < rows; r1++) {
            for (let r2 = r1 + 1; r2 < rows; r2++) {
                for (let c1 = 0; c1 < cols; c1++) {
                    for (let c2 = c1 + 1; c2 < cols; c2++) {
                        if (A[r1][c1] * A[r2][c2] !== A[r1][c2] * A[r2][c1]) {
                            return 2;
                        }
                    }
                }
            }
        }
        // All entries zero or no 2x2 or 3x3 nonzero
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                if (A[r][c] !== 0) return 1;
            }
        }
        return 0;
    }

    // Should not reach here given constraints
    return 0;
}