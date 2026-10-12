function determinant(A) {
    const n = A.length;
    if (n === 1) return A[0][0];
    if (n === 2) return A[0][0] * A[1][1] - A[0][1] * A[1][0];
    if (n === 3) {
        const a = A[0][0], b = A[0][1], c = A[0][2];
        const d = A[1][0], e = A[1][1], f = A[1][2];
        const g = A[2][0], h = A[2][1], i = A[2][2];
        return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
    }
    return 0;
}