function translatedMesh(mesh, dx, dy, dz) {
  const vertices = mesh.vertices.map(v => [v[0] + dx, v[1] + dy, v[2] + dz]);
  const triangles = mesh.triangles.map(t => [...t]);
  return { vertices, triangles };
}