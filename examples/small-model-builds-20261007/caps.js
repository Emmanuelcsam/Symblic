function capTriangles(offset, upward) {
  const a = offset, b = offset + 1, c = offset + 2, d = offset + 3;
  if (upward) return [[a, b, c], [a, c, d]];
  return [[a, c, b], [a, d, c]];
}