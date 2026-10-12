function stepSnake(body, dx, dy, grow) {
  const head = [body[0][0] + dx, body[0][1] + dy];
  const newBody = [head];
  const len = body.length;
  const copyEnd = grow ? len : len - 1;
  for (let i = 0; i < copyEnd; i++) {
    newBody.push([body[i][0], body[i][1]]);
  }
  return newBody;
}