function cupMesh(width, depth, height, wall, base) {
    const innerWidth = width - 2 * wall;
    const innerDepth = depth - 2 * wall;
    
    const rectRing = (width, depth, z) => {
        const halfWidth = width / 2;
        const halfDepth = depth / 2;
        return [
            [-halfWidth, -halfDepth, z],
            [halfWidth, -halfDepth, z],
            [halfWidth, halfDepth, z],
            [-halfWidth, halfDepth, z]
        ];
    };
    
    const joinRings = (lowerOffset, upperOffset, reverse) => {
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
    };
    
    const capTriangles = (offset, upward) => {
        const a = offset, b = offset + 1, c = offset + 2, d = offset + 3;
        if (upward) return [[a, b, c], [a, c, d]];
        return [[a, c, b], [a, d, c]];
    };
    
    const vertices = [
        ...rectRing(width, depth, 0),
        ...rectRing(width, depth, height),
        ...rectRing(innerWidth, innerDepth, height),
        ...rectRing(innerWidth, innerDepth, base)
    ];
    
    const triangles = [
        ...joinRings(0, 4, false),
        ...joinRings(4, 8, false),
        ...joinRings(12, 8, true),
        ...capTriangles(0, false),
        ...capTriangles(12, true)
    ];
    
    return { vertices, triangles };
}