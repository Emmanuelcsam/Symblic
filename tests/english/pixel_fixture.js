// TEST-ONLY CANDIDATE. Never supplied to a provider or a compiled source.
function delta(pixel, center) { return pixel - center; }
function square(value) { return value * value; }
function separation(dx, dy) { return square(dx) + square(dy); }
function inside(pixelX, pixelY, cx, cy) { return separation(delta(pixelX, cx), delta(pixelY, cy)) <= 25; }
function nextX(previousX) { if (previousX === null) return 0; if (previousX === 799) return 0; return previousX + 1; }
function bounds(cx, cy) { return {left: Math.max(0, cx - 5), right: Math.min(799, cx + 5), top: Math.max(0, cy - 5), bottom: Math.min(599, cy + 5)}; }
function whitePixels(cx, cy) { const box = bounds(cx, cy); const result = []; for (let y = box.top; y <= box.bottom; y++) { for (let x = box.left; x <= box.right; x++) { if (inside(x, y, cx, cy)) result.push(y * 800 + x); } } return result; }
function clearPixels(buffer) { buffer.fill(0); return buffer; }
function drawPixels(buffer, cx, cy) { const indices = whitePixels(cx, cy); for (const index of indices) buffer[index] = 1; return buffer; }
