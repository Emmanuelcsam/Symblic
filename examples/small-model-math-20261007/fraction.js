function normalizeFraction(n, d) {
    if (d === 0) throw new Error();
    const gcd = (a, b) => b === 0 ? Math.abs(a) : gcd(b, a % b);
    const g = gcd(Math.abs(n), Math.abs(d));
    const num = n / g;
    const den = d / g;
    if (den < 0) {
        return [-num, -den];
    }
    return [num, den];
}