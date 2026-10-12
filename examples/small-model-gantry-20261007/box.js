function boxMesh(width, depth, height) {
    const z0 = 0;
    const z1 = height;
    const lowerRing = rectRing(width, depth, z0);
    const upperRing = rectRing(width, depth, z1);
    const lowerOffset = 0;
    const upperOffset = 4;
    const sideTriangles = joinRings(lowerOffset, upperOffset, false);
    const bottomCap = capTriangles(lowerOffset, false);
    const topCap = capTriangles(upperOffset, true);
    return {
        vertices: lowerRing.concat(upperRing),
        triangles: sideTriangles.concat(bottomCap, topCap)
    };
}