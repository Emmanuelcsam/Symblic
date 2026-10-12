'use strict';
// Parse only: the top-level declarations of one JavaScript script, with their source ranges, so the kernel can drop
// a candidate's copies of names earlier units already declared (symblic/js/normalize.py). Candidate bytes are never
// passed to eval, vm, Function or require. stdin: {"source": text, "names": [name, ...]} (names may be empty: then
// every top-level declaration is listed). stdout: {"declarations": [{"name", "kind", "start", "end"}, ...]} or
// {"error": text} when the source does not parse.
const acorn = require(process.argv[2]);
const MAX_BYTES = 400000, MAX_TOKENS = 60000;

function names(pattern, out) {
  if (!pattern) return out;
  if (pattern.type === 'Identifier') out.push(pattern.name);
  else if (pattern.type === 'ObjectPattern') for (const p of pattern.properties) names(p.type === 'RestElement' ? p.argument : p.value, out);
  else if (pattern.type === 'ArrayPattern') for (const e of pattern.elements) names(e, out);
  else if (pattern.type === 'AssignmentPattern') names(pattern.left, out);
  else if (pattern.type === 'RestElement') names(pattern.argument, out);
  return out;
}

let data = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { data += chunk; if (data.length > MAX_BYTES * 2) { process.stdout.write(JSON.stringify({error: 'request too large'})); process.exit(0); } });
process.stdin.on('end', () => {
  let req;
  try { req = JSON.parse(data); } catch (e) { process.stdout.write(JSON.stringify({error: 'bad request'})); return; }
  const source = String(req.source || '');
  if (Buffer.byteLength(source, 'utf8') > MAX_BYTES) { process.stdout.write(JSON.stringify({error: 'source too large'})); return; }
  const wanted = Array.isArray(req.names) ? new Set(req.names.map(String)) : null;
  let ast, tokens = 0;
  try {
    ast = acorn.parse(source, {ecmaVersion: 2022, sourceType: 'script', allowHashBang: true,
      onToken() { if (++tokens > MAX_TOKENS) throw new RangeError('too many tokens'); }});
  } catch (e) {
    process.stdout.write(JSON.stringify({error: String(e && e.message || e)}));
    return;
  }
  const out = [];
  for (const node of ast.body) {
    if (node.type === 'FunctionDeclaration' || node.type === 'ClassDeclaration') {
      const name = node.id ? node.id.name : '';
      if (name && (!wanted || wanted.has(name))) out.push({name, kind: node.type === 'ClassDeclaration' ? 'class' : 'function', start: node.start, end: node.end});
    } else if (node.type === 'ExpressionStatement' && node.expression && node.expression.type === 'AssignmentExpression'
               && node.expression.operator === '=' && node.expression.left && node.expression.left.type === 'Identifier') {
      // `listItem = function ...` at top level: not a declaration, so the sandbox's protected bindings swallow it
      // silently while the assembled page executes it (llama3.2:1b, 2026-10-10)
      const name = node.expression.left.name;
      if (!wanted || wanted.has(name)) out.push({name, kind: 'assign', start: node.start, end: node.end});
    } else if (node.type === 'VariableDeclaration') {
      // a declaration is dropped only when every name it binds is a reused one: `const a = 1, b = 2` with only
      // `a` reused stays (the candidate's `b` would be lost otherwise)
      const bound = [];
      for (const d of node.declarations) names(d.id, bound);
      if (bound.length && (!wanted || bound.every((n) => wanted.has(n)))) out.push({name: bound.join(','), kind: node.kind, start: node.start, end: node.end});
    }
  }
  process.stdout.write(JSON.stringify({declarations: out}));
});
