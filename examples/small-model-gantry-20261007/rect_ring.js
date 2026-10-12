function rectRing(width, depth, z) {
    const halfWidth = width / 2;
    const halfDepth = depth / 2;
    return [
        [-halfWidth, -halfDepth, z],
        [halfWidth, -halfDepth, z],
        [halfWidth, halfDepth, z],
        [-halfWidth, halfDepth, z]
    ];
}