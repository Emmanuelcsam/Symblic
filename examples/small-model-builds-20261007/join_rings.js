function joinRings(lowerOffset, upperOffset, reverse) {
    const result = [];
    for (let i = 0; i < 4; i++) {
        const j = (i + 1) % 4;
        const a = lowerOffset + i;
        const b = lowerOffset + j;
        const c = upperOffset + j;
        const d = upperOffset + i;
        if (!reverse) {
            result.push([a, b, c]);
            result.push([a, c, d]);
        } else {
            result.push([a, c, b]);
            result.push([a, d, c]);
        }
    }
    return result;
}