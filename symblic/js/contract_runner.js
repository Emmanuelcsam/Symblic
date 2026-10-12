'use strict';
// Parse only. Candidate bytes are never passed to eval, vm, Function or require.
// This trusted runner and pinned Acorn are copied into the existing sandbox.
const acorn = require('./acorn.js');
const MAX_BYTES = 500000, MAX_TOKENS = 50000, MAX_NODES = 50000, MAX_DEPTH = 128;
const KINDS = new Set(['function', 'class', 'const', 'let', 'var']);
const IDENTIFIER = /^[$A-Z_a-z][$\w]{0,127}$/;
const result = {passed: false, status: 'invalid', declarations: [], diagnostics: [], truncated: false};
let count = 0;
function diagnostic(code, node, name = null) {
  if (result.diagnostics.length >= 32) { result.truncated = true; return; }
  result.diagnostics.push({code, line: node && node.loc ? node.loc.start.line : null,
    column: node && node.loc ? node.loc.start.column + 1 : null, name});
}
function bound(code) { const e = new Error(code); e.contractBudget = code; throw e; }
function scan(ast) {
  const pending = [[ast, 0]];
  while (pending.length) {
    const [value, depth] = pending.pop();
    if (!value || typeof value !== 'object') continue;
    if (value.type) {
      count += 1;
      if (count > MAX_NODES) bound('ast_node_limit');
      if (depth > MAX_DEPTH) bound('ast_depth_limit');
    }
    for (const key of Object.keys(value)) {
      if (key === 'loc' || key === 'regex' || (key === 'value' && value.type === 'Literal')) continue;
      const child = value[key];
      if (Array.isArray(child)) {
        for (let i = child.length - 1; i >= 0; i--) pending.push([child[i], depth + 1]);
      } else if (child && typeof child === 'object') pending.push([child, depth + 1]);
    }
  }
}
// This is the optional passive-loading policy, not a general JavaScript purity proof.
function passive(node) {
  if (!node) return true;
  switch (node.type) {
    case 'Literal': case 'FunctionExpression': case 'ArrowFunctionExpression': return true;
    case 'UnaryExpression':
      return ['+', '-'].includes(node.operator) && node.argument.type === 'Literal' &&
        ['number', 'bigint'].includes(typeof node.argument.value);
    case 'TemplateLiteral': return node.expressions.length === 0;
    case 'ArrayExpression': return node.elements.every(value => !value || passive(value));
    case 'ObjectExpression': return node.properties.every(property => property.type === 'Property' &&
      !property.computed && property.kind === 'init' && !property.shorthand && passive(property.value));
    case 'ClassExpression': return passiveClass(node);
    default: return false;
  }
}
function passiveClass(node) {
  if (node.superClass) return false;
  return node.body.body.every(member => !member.computed && member.type !== 'StaticBlock' &&
    (member.type === 'MethodDefinition' ||
      (member.type === 'PropertyDefinition' && (!member.static || passive(member.value)))));
}
function inspect(request) {
  if (!request || typeof request.source !== 'string' || request.source.length > 400000 ||
      !request.exports || Array.isArray(request.exports) || typeof request.exports !== 'object') {
    diagnostic('request_shape'); return;
  }
  const expected = Object.keys(request.exports);
  if (expected.length > 128 || expected.some(name => !IDENTIFIER.test(name) || !KINDS.has(request.exports[name]))) {
    diagnostic('contract_shape'); return;
  }
  const ast = acorn.parse(request.source, {ecmaVersion: 2022, sourceType: 'script', locations: true,
    allowHashBang: false, allowReturnOutsideFunction: false,
    onToken() { if (++count > MAX_TOKENS) bound('token_limit'); }});
  count = 0;
  scan(ast);
  const seen = new Set();
  function declare(node, name, kind) {
    if (!IDENTIFIER.test(name)) { diagnostic('unsupported_identifier', node); return; }
    if (result.declarations.length >= 128) bound('declaration_limit');
    result.declarations.push({name, kind, line: node.loc.start.line, column: node.loc.start.column + 1});
    if (seen.has(name)) diagnostic('duplicate_name', node, name);
    seen.add(name);
    if (!Object.hasOwn(request.exports, name)) diagnostic('unexpected_name', node, name);
    else if (request.exports[name] !== kind) diagnostic('wrong_kind', node, name);
  }
  for (const node of ast.body) {
    if (node.type === 'EmptyStatement' || (node.type === 'ExpressionStatement' && node.directive === 'use strict')) continue;
    if (node.type === 'FunctionDeclaration') declare(node, node.id.name, 'function');
    else if (node.type === 'ClassDeclaration') {
      declare(node, node.id.name, 'class');
      if (!passiveClass(node)) diagnostic('active_class_definition', node, node.id.name);
    } else if (node.type === 'VariableDeclaration') {
      for (const item of node.declarations) {
        if (item.id.type !== 'Identifier') { diagnostic('destructuring_declaration', item); continue; }
        declare(item, item.id.name, node.kind);
        if (!passive(item.init)) diagnostic('active_initializer', item, item.id.name);
      }
    } else diagnostic('top_level_statement', node);
  }
  for (const name of expected) if (!seen.has(name)) diagnostic('missing_name', null, name);
  result.passed = result.diagnostics.length === 0 && !result.truncated;
  result.status = result.passed ? 'accepted' : 'invalid';
}
let bytes = 0, chunks = [], oversized = false;
process.stdin.on('data', chunk => {
  bytes += chunk.length;
  if (bytes > MAX_BYTES) { oversized = true; chunks = []; } else if (!oversized) chunks.push(chunk);
});
process.stdin.on('end', () => {
  try {
    if (oversized) bound('input_byte_limit');
    inspect(JSON.parse(Buffer.concat(chunks).toString('utf8')));
  } catch (error) {
    if (error.contractBudget || error instanceof RangeError) {
      result.status = 'budget'; diagnostic(error.contractBudget || 'parser_depth_limit');
    } else if (error instanceof SyntaxError) {
      diagnostic('syntax_error', error.loc ? {loc: {start: error.loc}} : null);
    } else { result.status = 'error'; diagnostic('parser_error'); }
    result.passed = false;
  }
  process.stdout.write(JSON.stringify(result));
});
